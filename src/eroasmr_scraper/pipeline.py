"""Download-upload pipeline for processing videos."""

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

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
class VideoProcessResult:
    """Result of processing a single video through the pipeline.

    Attributes:
        slug: Video slug
        downloaded: Whether download succeeded
        audio_downloaded: Whether audio download succeeded
        upload_results: Dict mapping storage_type to UploadResult
        audio_upload_results: Dict mapping storage_type to UploadResult for audio
        download_error: Download error message if failed
        local_file_deleted: Whether local file was cleaned up
        audio_file_deleted: Whether audio file was cleaned up
    """

    slug: str
    downloaded: bool = False
    audio_downloaded: bool = False
    upload_results: dict[str, UploadResult] = field(default_factory=dict)
    audio_upload_results: dict[str, UploadResult] = field(default_factory=dict)
    download_error: str | None = None
    local_file_deleted: bool = False
    audio_file_deleted: bool = False


class DownloadUploadPipeline:
    """Pipeline that downloads videos and uploads them to multiple platforms.

    The pipeline follows a "download then upload" pattern:
    1. Download video using VideoDownloader
    2. Upload to all registered uploaders (in parallel if possible)
    3. Record successful uploads in storage_locations table
    4. Optionally delete local file after successful uploads

    Example:
        storage = VideoStorage()
        downloader = VideoDownloader(storage, Path("data/downloads"))
        telegram = TelegramUploader(bot_token="...", chat_id="...")
        gdrive = GoogleDriveUploader(credentials_path="...")

        pipeline = DownloadUploadPipeline(
            storage=storage,
            downloader=downloader,
            uploaders=[telegram, gdrive],
        )

        # Process single video
        result = pipeline.process_video("video-slug")

        # Process all pending videos
        stats = pipeline.process_all(limit=10)
    """

    def __init__(
        self,
        storage: VideoStorage,
        downloader: VideoDownloader,
        uploaders: list[Uploader],
        delete_after_upload: bool = True,
        delete_only_if_all_success: bool = True,
    ):
        """Initialize the pipeline.

        Args:
            storage: VideoStorage instance for database operations
            downloader: VideoDownloader instance for downloading videos
            uploaders: List of Uploader instances for uploading to different platforms
            delete_after_upload: Whether to delete local files after upload
            delete_only_if_all_success: If True, only delete when ALL uploads succeed
        """
        self.storage = storage
        self.downloader = downloader
        self.uploaders = uploaders
        self.delete_after_upload = delete_after_upload
        self.delete_only_if_all_success = delete_only_if_all_success

        # Filter out uploaders that are not ready
        self._active_uploaders = [u for u in uploaders if u.is_ready()]

        if len(self._active_uploaders) < len(self.uploaders):
            skipped = len(self.uploaders) - len(self._active_uploaders)
            logger.warning(
                "%d uploader(s) skipped due to missing configuration", skipped
            )

    def _upload_to_all(
        self, file_path: Path, slug: str, thumbnail_path: Path | None = None
    ) -> dict[str, UploadResult]:
        """Upload file to all active uploaders.

        Args:
            file_path: Path to the video file
            slug: Video slug
            thumbnail_path: Path to the thumbnail file (optional)

        Returns:
            Dict mapping storage_type to UploadResult
        """
        results: dict[str, UploadResult] = {}

        for uploader in self._active_uploaders:
            try:
                logger.info(
                    "Uploading %s to %s", slug, uploader.storage_type
                )
                result = uploader.upload(file_path, slug, thumbnail_path=thumbnail_path)
                results[uploader.storage_type] = result

                if result.success:
                    logger.info(
                        "Upload to %s successful: %s",
                        uploader.storage_type,
                        result.location_url or result.location_id,
                    )
                else:
                    logger.error(
                        "Upload to %s failed: %s",
                        uploader.storage_type,
                        result.error,
                    )

            except Exception as e:
                logger.exception(
                    "Unexpected error uploading to %s: %s",
                    uploader.storage_type,
                    e,
                )
                results[uploader.storage_type] = UploadResult(
                    success=False, error=str(e)
                )

        return results

    def _record_uploads(
        self, slug: str, upload_results: dict[str, UploadResult]
    ) -> None:
        """Record successful uploads in storage_locations table.

        Args:
            slug: Video slug
            upload_results: Dict of upload results
        """
        for storage_type, result in upload_results.items():
            if result.success:
                location = StorageLocation(
                    slug=slug,
                    storage_type=storage_type,
                    location_id=result.location_id or "",
                    location_url=result.location_url,
                    metadata=result.metadata,
                )
                self.storage.add_storage_location(location)
                logger.debug(
                    "Recorded upload location for %s: %s",
                    slug,
                    storage_type,
                )

    def _should_delete_local(
        self, upload_results: dict[str, UploadResult]
    ) -> bool:
        """Determine if local file should be deleted.

        Args:
            upload_results: Dict of upload results

        Returns:
            True if local file should be deleted
        """
        if not self.delete_after_upload:
            return False

        if not upload_results:
            return False

        if self.delete_only_if_all_success:
            return all(r.success for r in upload_results.values())
        else:
            # Delete if at least one upload succeeded
            return any(r.success for r in upload_results.values())

    def process_video(self, slug: str, include_audio: bool = True) -> VideoProcessResult:
        """Process a single video: download -> upload -> cleanup.

        Args:
            slug: Video slug
            include_audio: If True, also process audio files (zhumianwang only)

        Returns:
            VideoProcessResult with processing details
        """
        result = VideoProcessResult(slug=slug)

        # Check if this is zhumianwang (for audio support)
        video = self.storage.get_video_by_slug(slug)
        site_id = video.get("site_id", "eroasmr") if video else "eroasmr"
        should_download_audio = include_audio and site_id == "zhumianwang"

        # Step 1: Download video (and audio for zhumianwang)
        success, error = self.downloader.download_video(slug, include_audio=should_download_audio)

        if not success:
            result.download_error = error
            logger.error("Download failed for %s: %s", slug, error)
            return result

        result.downloaded = True

        # Step 2: Get file paths
        file_path = self.downloader.output_dir / f"{slug}.mp4"
        audio_path = self.downloader.output_dir / f"{slug}.mp3"

        if not file_path.exists():
            result.download_error = f"Downloaded file not found: {file_path}"
            logger.error(result.download_error)
            return result

        # Check if audio was downloaded
        if should_download_audio and audio_path.exists():
            result.audio_downloaded = True

        # Step 2b: Download thumbnail
        thumbnail_path = self.downloader.download_thumbnail(slug)

        # Step 3: Upload video to all platforms
        upload_results = self._upload_to_all(file_path, slug, thumbnail_path=thumbnail_path)
        result.upload_results = upload_results

        # Step 3b: Upload audio to all platforms (if downloaded)
        if result.audio_downloaded:
            audio_upload_results = self._upload_to_all(audio_path, f"{slug}_audio", thumbnail_path=None)
            result.audio_upload_results = audio_upload_results

        # Step 4: Record successful uploads
        self._record_uploads(slug, upload_results)
        if result.audio_downloaded:
            self._record_uploads(f"{slug}_audio", result.audio_upload_results)

        # Step 5: Optionally delete local files
        if self._should_delete_local(upload_results):
            try:
                file_path.unlink()
                result.local_file_deleted = True
                logger.info("Deleted local file: %s", file_path)
            except OSError as e:
                logger.warning("Failed to delete local file %s: %s", file_path, e)
            # Also delete thumbnail
            if thumbnail_path and thumbnail_path.exists():
                try:
                    thumbnail_path.unlink()
                    logger.debug("Deleted thumbnail: %s", thumbnail_path)
                except OSError as e:
                    logger.warning("Failed to delete thumbnail %s: %s", thumbnail_path, e)

        # Delete audio file if all uploads succeeded
        if result.audio_downloaded and self._should_delete_local(result.audio_upload_results):
            try:
                audio_path.unlink()
                result.audio_file_deleted = True
                logger.info("Deleted audio file: %s", audio_path)
            except OSError as e:
                logger.warning("Failed to delete audio file %s: %s", audio_path, e)

        return result

    def process_all(
        self,
        limit: int | None = None,
        retry_failed: bool = False,
        delay: tuple[float, float] = (2.0, 4.0),
    ) -> dict[str, int]:
        """Process all pending videos through the pipeline.

        Args:
            limit: Maximum number of videos to process
            retry_failed: If True, also retry failed downloads
            delay: (min, max) seconds to wait between videos

        Returns:
            Statistics dict with counts
        """
        pending = self.storage.get_pending_downloads(
            limit=limit, include_failed=retry_failed
        )

        stats = {
            "total": len(pending),
            "downloaded": 0,
            "upload_success": 0,
            "upload_partial": 0,
            "upload_failed": 0,
            "download_failed": 0,
        }

        if not pending:
            logger.info("No pending videos to process")
            return stats

        logger.info(
            "Starting pipeline for %d videos with %d uploaders",
            len(pending),
            len(self._active_uploaders),
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("Processing...", total=len(pending))

            for i, slug in enumerate(pending, 1):
                progress.update(
                    task,
                    description=f"[cyan]{slug[:35]}[/cyan]",
                    completed=i - 1,
                )

                result = self.process_video(slug)

                if result.downloaded:
                    stats["downloaded"] += 1

                    # Count upload results
                    successful = sum(
                        1 for r in result.upload_results.values() if r.success
                    )
                    total = len(result.upload_results)

                    if successful == total and total > 0:
                        stats["upload_success"] += 1
                        status = "[green]✓[/green]"
                    elif successful > 0:
                        stats["upload_partial"] += 1
                        status = "[yellow]◐[/yellow]"
                    else:
                        stats["upload_failed"] += 1
                        status = "[red]✗[/red]"

                    progress.update(
                        task,
                        description=f"{status} {slug[:35]}",
                    )
                else:
                    stats["download_failed"] += 1
                    progress.update(
                        task,
                        description=f"[red]✗[/red] {slug[:35]}: {result.download_error}",
                    )

                # Apply delay between videos
                if i < len(pending):
                    wait_time = random.uniform(delay[0], delay[1])
                    time.sleep(wait_time)

            progress.update(task, completed=len(pending))

        logger.info(
            "Pipeline complete: %d downloaded, %d uploaded, %d partial, %d failed",
            stats["downloaded"],
            stats["upload_success"],
            stats["upload_partial"],
            stats["upload_failed"],
        )

        return stats

    def get_uploader_status(self) -> dict[str, bool]:
        """Get status of all registered uploaders.

        Returns:
            Dict mapping storage_type to ready status
        """
        return {
            uploader.storage_type: uploader.is_ready()
            for uploader in self.uploaders
        }
