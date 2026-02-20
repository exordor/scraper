"""Parallel download-upload pipeline using producer-consumer pattern."""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from eroasmr_scraper.downloader import VideoDownloader
from eroasmr_scraper.models import StorageLocation
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.uploader import UploadResult, Uploader

logger = logging.getLogger(__name__)


@dataclass
class DownloadTask:
    """Task representing a downloaded file ready for upload."""

    slug: str
    file_path: Path
    file_size: int
    thumbnail_path: Path | None = None
    audio_path: Path | None = None  # For zhumianwang audio
    error: str | None = None


@dataclass
class UploadTask:
    """Task representing a file to upload."""

    slug: str
    file_path: Path
    uploader: Uploader
    thumbnail_path: Path | None = None
    site_id: str = "eroasmr"  # Default site_id
    uploader: Uploader
    thumbnail_path: Path | None = None


@dataclass
class PipelineStats:
    """Statistics for the parallel pipeline."""

    total: int = 0
    downloaded: int = 0
    download_failed: int = 0
    uploaded: int = 0
    upload_failed: int = 0
    files_deleted: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "download_failed": self.download_failed,
            "uploaded": self.uploaded,
            "upload_failed": self.upload_failed,
            "files_deleted": self.files_deleted,
        }


class ParallelPipeline:
    """Parallel download-upload pipeline.

    Uses producer-consumer pattern:
    - Downloader produces tasks (downloaded files)
    - Uploaders consume tasks and upload to platforms
    - Both run concurrently

    Example:
        storage = VideoStorage()
        downloader = VideoDownloader(storage, Path("data/downloads"))
        uploaders = [TelegramUploader(...), GoogleDriveUploader(...)]

        pipeline = ParallelPipeline(
            storage=storage,
            downloader=downloader,
            uploaders=uploaders,
        )

        # Run pipeline
        stats = await pipeline.run(limit=100)
    """

    def __init__(
        self,
        storage: VideoStorage,
        downloader: VideoDownloader,
        uploaders: list[Uploader],
        download_queue_size: int = 10,
        upload_queue_size: int = 20,
        upload_workers: int = 3,
        max_pending_uploads: int = 50,
        min_disk_free_gb: float = 5.0,
        delete_after_upload: bool = True,
        delete_only_if_all_success: bool = True,
    ):
        """Initialize parallel pipeline.

        Args:
            storage: VideoStorage instance
            downloader: VideoDownloader instance
            uploaders: List of Uploader instances
            download_queue_size: Max items in download queue (backpressure)
            upload_queue_size: Max items in upload queue
            upload_workers: Number of concurrent upload workers per uploader
            max_pending_uploads: Max files waiting to be uploaded before pausing downloads
            min_disk_free_gb: Minimum free disk space in GB before pausing
            delete_after_upload: Delete local files after upload
            delete_only_if_all_success: Only delete if ALL uploads succeed
        """
        self.storage = storage
        self.downloader = downloader
        self.uploaders = [u for u in uploaders if u.is_ready()]
        self.delete_after_upload = delete_after_upload
        self.delete_only_if_all_success = delete_only_if_all_success
        self.upload_workers = upload_workers
        self.max_pending_uploads = max_pending_uploads
        self.min_disk_free_gb = min_disk_free_gb

        # Queues
        self.download_queue: asyncio.Queue[DownloadTask | None] = asyncio.Queue(
            maxsize=download_queue_size
        )
        self.upload_queue: asyncio.Queue[UploadTask | None] = asyncio.Queue(
            maxsize=upload_queue_size
        )

        # Track upload results per slug
        self._upload_results: dict[str, dict[str, UploadResult]] = {}
        self._results_lock = asyncio.Lock()

        # Statistics
        self.stats = PipelineStats()

        # Control
        self._stop_event = asyncio.Event()

    def _get_disk_free_gb(self) -> float:
        """Get free disk space in GB."""
        import shutil
        stat = shutil.disk_usage(self.downloader.output_dir)
        return stat.free / (1024 ** 3)

    def _get_pause_file(self) -> Path:
        """Get path to the pause file."""
        # Pause file is in the project root (parent of output dir)
        return self.downloader.output_dir.parent / ".pause_downloads"

    def _is_paused(self) -> bool:
        """Check if downloads are paused via pause file."""
        return self._get_pause_file().exists()

    def _get_pending_upload_count(self) -> int:
        """Get count of downloaded files waiting to be uploaded."""
        return self.stats.downloaded - self.stats.uploaded - self.stats.upload_failed

    async def _download_producer(
        self,
        slugs: list[str],
        progress: Progress,
        task_id: int,
    ) -> None:
        """Download videos and put them in the queue.

        Args:
            slugs: List of video slugs to download
            progress: Rich Progress instance
            task_id: Progress task ID
        """
        for i, slug in enumerate(slugs):
            if self._stop_event.is_set():
                break

            # Check for pause file (external disk monitor can create this)
            while self._is_paused():
                logger.info("Downloads paused via pause file. Waiting...")
                progress.update(
                    task_id,
                    description="[yellow]⏸ Downloads paused (disk monitor). Waiting...[/yellow]",
                )
                await asyncio.sleep(10)

            # Check disk space before downloading
            disk_free = self._get_disk_free_gb()
            if disk_free < self.min_disk_free_gb:
                logger.warning(
                    "Low disk space (%.1fGB < %.1fGB). Waiting for uploads...",
                    disk_free, self.min_disk_free_gb
                )
                progress.update(
                    task_id,
                    description=f"[yellow]Low disk ({disk_free:.1f}GB). Waiting...[/yellow]",
                )
                # Wait for uploads to complete and free up space
                while self._get_disk_free_gb() < self.min_disk_free_gb:
                    await asyncio.sleep(10)
                    if self._get_pending_upload_count() == 0:
                        break  # No more uploads pending, disk is still low

            # Check pending uploads limit
            pending = self._get_pending_upload_count()
            if pending >= self.max_pending_uploads:
                logger.info(
                    "Too many pending uploads (%d >= %d). Waiting...",
                    pending, self.max_pending_uploads
                )
                progress.update(
                    task_id,
                    description=f"[yellow]Pending uploads: {pending}. Waiting...[/yellow]",
                )
                while self._get_pending_upload_count() >= self.max_pending_uploads:
                    await asyncio.sleep(5)

            progress.update(
                task_id,
                description=f"[cyan]DL: {slug[:30]}[/cyan]",
                completed=i,
            )

            # Check if this is zhumianwang for audio download
            video = self.storage.get_video_by_slug(slug)
            site_id = video.get("site_id", "eroasmr") if video else "eroasmr"
            include_audio = site_id == "zhumianwang"

            # Run download in thread pool (sync function)
            loop = asyncio.get_event_loop()
            success, error = await loop.run_in_executor(
                None,
                lambda s=slug, ia=include_audio: self.downloader.download_video(s, include_audio=ia),
            )

            if success:
                file_path = self.downloader.output_dir / f"{slug}.mp4"
                file_size = file_path.stat().st_size if file_path.exists() else 0

                # Check for audio file (zhumianwang)
                audio_path = self.downloader.output_dir / f"{slug}.mp3"
                if not audio_path.exists():
                    audio_path = None

                # Also download thumbnail
                thumbnail_path = await loop.run_in_executor(
                    None,
                    self.downloader.download_thumbnail,
                    slug,
                )

                task = DownloadTask(
                    slug=slug,
                    file_path=file_path,
                    file_size=file_size,
                    thumbnail_path=thumbnail_path,
                    audio_path=audio_path,
                )

                await self.download_queue.put(task)
                self.stats.downloaded += 1

                audio_info = " + audio" if audio_path else ""
                progress.update(
                    task_id,
                    description=f"[green]✓ DL: {slug[:30]}{audio_info}[/green]",
                )
            else:
                self.stats.download_failed += 1
                progress.update(
                    task_id,
                    description=f"[red]✗ DL: {slug[:30]}[/red]",
                )
                logger.error("Download failed: %s - %s", slug, error)

            # Delay between downloads
            if i < len(slugs) - 1:
                delay = random.uniform(2.0, 4.0)
                await asyncio.sleep(delay)

        # Signal end of downloads
        await self.download_queue.put(None)
        progress.update(task_id, completed=len(slugs), description="[green]Download complete[/green]")

    async def _download_to_upload_dispatcher(self) -> None:
        """Take downloaded files and create upload tasks for each uploader."""

        while True:
            task = await self.download_queue.get()

            if task is None:
                # End of downloads, signal end to all upload workers
                for _ in self.uploaders:
                    for _ in range(self.upload_workers):
                        await self.upload_queue.put(None)
                break

            if task.error:
                continue

            # Get site_id from video record
            video = self.storage.get_video_by_slug(task.slug)
            site_id = video.get("site_id", "eroasmr") if video else "eroasmr"

            # Create upload task for video file
            for uploader in self.uploaders:
                upload_task = UploadTask(
                    slug=task.slug,
                    file_path=task.file_path,
                    uploader=uploader,
                    thumbnail_path=task.thumbnail_path,
                    site_id=site_id,
                )
                await self.upload_queue.put(upload_task)

            # Create upload task for audio file if present (zhumianwang)
            if task.audio_path and task.audio_path.exists():
                for uploader in self.uploaders:
                    audio_task = UploadTask(
                        slug=f"{task.slug}_audio",
                        file_path=task.audio_path,
                        uploader=uploader,
                        thumbnail_path=None,  # No thumbnail for audio
                        site_id=site_id,
                    )
                    await self.upload_queue.put(audio_task)

    async def _upload_consumer(
        self,
        uploader: Uploader,
        progress: Progress,
        task_id: int,
    ) -> None:
        """Upload files from the queue.

        Args:
            uploader: Uploader instance
            progress: Rich Progress instance
            task_id: Progress task ID
        """
        while True:
            task = await self.upload_queue.get()

            if task is None:
                break

            if task.uploader.storage_type != uploader.storage_type:
                # Put back for other consumer
                await self.upload_queue.put(task)
                await asyncio.sleep(0.1)
                continue

            progress.update(
                task_id,
                description=f"[yellow]UL {uploader.storage_type}: {task.slug[:25]}[/yellow]",
            )

            try:
                # Run upload in thread pool (sync function with kwargs)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: uploader.upload(
                        task.file_path,
                        task.slug,
                        thumbnail_path=task.thumbnail_path,
                    ),
                )

                # Store result
                async with self._results_lock:
                    if task.slug not in self._upload_results:
                        self._upload_results[task.slug] = {}
                    self._upload_results[task.slug][uploader.storage_type] = result

                if result.success:
                    # Record to storage_locations
                    location = StorageLocation(
                        slug=task.slug,
                        site_id=task.site_id,
                        storage_type=uploader.storage_type,
                        location_id=result.location_id or "",
                        location_url=result.location_url,
                        metadata=result.metadata,
                    )
                    # Run DB operation in thread pool
                    await loop.run_in_executor(
                        None,
                        self.storage.add_storage_location,
                        location,
                    )

                    self.stats.uploaded += 1
                    progress.update(
                        task_id,
                        description=f"[green]✓ UL {uploader.storage_type}: {task.slug[:25]}[/green]",
                    )
                    logger.info(
                        "Upload to %s success: %s -> %s",
                        uploader.storage_type,
                        task.slug,
                        result.location_url or result.location_id,
                    )
                else:
                    self.stats.upload_failed += 1
                    progress.update(
                        task_id,
                        description=f"[red]✗ UL {uploader.storage_type}: {task.slug[:25]}[/red]",
                    )
                    logger.error(
                        "Upload to %s failed: %s - %s",
                        uploader.storage_type,
                        task.slug,
                        result.error,
                    )

            except Exception as e:
                logger.exception(
                    "Unexpected error uploading %s to %s: %s",
                    task.slug,
                    uploader.storage_type,
                    e,
                )
                self.stats.upload_failed += 1

                # Record failure
                async with self._results_lock:
                    if task.slug not in self._upload_results:
                        self._upload_results[task.slug] = {}
                    self._upload_results[task.slug][uploader.storage_type] = UploadResult(
                        success=False,
                        error=str(e),
                    )

            # Check if we can delete the file
            await self._maybe_delete_file(task.slug, task.file_path, task.thumbnail_path)

    async def _maybe_delete_file(
        self, slug: str, file_path: Path, thumbnail_path: Path | None = None
    ) -> None:
        """Delete file if all uploads are complete and successful.

        Args:
            slug: Video slug
            file_path: Path to the file
            thumbnail_path: Path to the thumbnail file (optional)
        """
        if not self.delete_after_upload:
            return

        async with self._results_lock:
            results = self._upload_results.get(slug, {})

            # Check if all uploaders have reported
            if len(results) < len(self.uploaders):
                return

            # Check if we should delete
            should_delete = False
            if self.delete_only_if_all_success:
                should_delete = all(r.success for r in results.values())
            else:
                should_delete = any(r.success for r in results.values())

            if should_delete and file_path.exists():
                try:
                    file_path.unlink()
                    self.stats.files_deleted += 1
                    logger.info("Deleted local file: %s", file_path)
                except OSError as e:
                    logger.warning("Failed to delete %s: %s", file_path, e)

            # Also delete thumbnail if exists
            if should_delete and thumbnail_path and thumbnail_path.exists():
                try:
                    thumbnail_path.unlink()
                    logger.debug("Deleted thumbnail: %s", thumbnail_path)
                except OSError as e:
                    logger.warning("Failed to delete thumbnail %s: %s", thumbnail_path, e)

    async def run(
        self,
        limit: int | None = None,
        retry_failed: bool = False,
    ) -> dict[str, int]:
        """Run the parallel pipeline.

        Args:
            limit: Maximum number of videos to process
            retry_failed: If True, also retry failed downloads

        Returns:
            Dictionary with statistics
        """
        # Get pending downloads
        slugs = self.storage.get_pending_downloads(
            limit=limit, include_failed=retry_failed
        )

        self.stats.total = len(slugs)

        if not slugs:
            logger.info("No pending videos to process")
            return self.stats.to_dict()

        if not self.uploaders:
            logger.warning("No uploaders configured")
            return self.stats.to_dict()

        logger.info(
            "Starting parallel pipeline: %d videos, %d uploaders",
            len(slugs),
            len(self.uploaders),
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            # Create progress tasks
            dl_task = progress.add_task(
                "[cyan]Downloading[/cyan]",
                total=len(slugs),
            )
            ul_tasks = {}
            for uploader in self.uploaders:
                ul_tasks[uploader.storage_type] = progress.add_task(
                    f"[yellow]Uploading to {uploader.storage_type}[/yellow]",
                    total=len(slugs),
                )

            # Create tasks
            tasks = []

            # Download producer
            tasks.append(
                asyncio.create_task(
                    self._download_producer(slugs, progress, dl_task)
                )
            )

            # Dispatcher
            tasks.append(
                asyncio.create_task(self._download_to_upload_dispatcher())
            )

            # Upload consumers (multiple workers per uploader for parallel uploads)
            for uploader in self.uploaders:
                for worker_id in range(self.upload_workers):
                    tasks.append(
                        asyncio.create_task(
                            self._upload_consumer(
                                uploader,
                                progress,
                                ul_tasks[uploader.storage_type],
                            )
                        )
                    )

            # Wait for all tasks
            await asyncio.gather(*tasks)

            # Update final progress
            for storage_type, task_id in ul_tasks.items():
                progress.update(task_id, completed=len(slugs))

        logger.info(
            "Pipeline complete: downloaded=%d, upload_success=%d, upload_failed=%d",
            self.stats.downloaded,
            self.stats.uploaded,
            self.stats.upload_failed,
        )

        return self.stats.to_dict()

    def stop(self) -> None:
        """Signal the pipeline to stop."""
        self._stop_event.set()
