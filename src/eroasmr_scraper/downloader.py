"""Video downloader using httpx with direct URL extraction."""

import io
import logging
import random
import time
from pathlib import Path

import httpx
from PIL import Image
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import DownloadStatus
from eroasmr_scraper.parser import parse_video_source
from eroasmr_scraper.storage import VideoStorage

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Video downloader using httpx with direct URL extraction."""

    def __init__(
        self,
        storage: VideoStorage,
        output_dir: Path,
        archive_file: Path | None = None,
        sleep_interval: tuple[float, float] = (2.0, 4.0),
        progress: Progress | None = None,
    ):
        """Initialize downloader.

        Args:
            storage: VideoStorage instance
            output_dir: Directory to save downloaded videos
            archive_file: Path to archive file (stores downloaded slugs)
            sleep_interval: (min, max) seconds to wait between downloads
            progress: Rich Progress instance for displaying progress
        """
        self.storage = storage
        self.output_dir = output_dir
        self.archive_file = archive_file or output_dir.parent / "download_archive.txt"
        self.sleep_interval = sleep_interval
        self.progress = progress

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load archive
        self._archive: set[str] = set()
        self._load_archive()

    def _load_archive(self) -> None:
        """Load archive file into memory."""
        if self.archive_file.exists():
            with open(self.archive_file) as f:
                self._archive = set(line.strip() for line in f if line.strip())

    def _save_to_archive(self, slug: str) -> None:
        """Add slug to archive file."""
        self._archive.add(slug)
        with open(self.archive_file, "a") as f:
            f.write(f"{slug}\n")

    def _is_in_archive(self, slug: str) -> bool:
        """Check if slug is in archive."""
        return slug in self._archive

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers matching the scraper's client fingerprint."""
        return {
            "User-Agent": settings.http.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def _get_client(self) -> httpx.Client:
        """Create configured HTTP client."""
        return httpx.Client(
            headers=self._get_headers(),
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
        )

    def _fetch_video_page(self, client: httpx.Client, slug: str) -> str | None:
        """Fetch video detail page HTML.

        Args:
            client: HTTP client
            slug: Video slug

        Returns:
            HTML content or None if failed
        """
        url = f"{settings.http.base_url}/video/{slug}/"
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d fetching video page %s", e.response.status_code, url)
            return None
        except httpx.RequestError as e:
            logger.error("Request error fetching video page %s: %s", url, e)
            return None

    def _extract_video_url(self, html: str) -> str | None:
        """Extract video source URL from page HTML.

        Args:
            html: HTML content

        Returns:
            Video URL or None if not found
        """
        return parse_video_source(html)

    def _download_file(
        self,
        client: httpx.Client,
        url: str,
        output_path: Path,
        task_id: int | None = None,
    ) -> tuple[bool, str | None]:
        """Download file with progress support.

        Args:
            client: HTTP client
            url: File URL
            output_path: Output file path
            task_id: Rich progress task ID (optional)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Use stream for large files
            with client.stream("GET", url) as response:
                response.raise_for_status()

                # Get file size
                total_size = int(response.headers.get("content-length", 0))

                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):  # 64KB chunks
                        f.write(chunk)

                        # Update progress bar if available
                        if self.progress and task_id is not None:
                            self.progress.update(
                                task_id, completed=response.num_bytes_downloaded
                            )

                # Verify download
                actual_size = output_path.stat().st_size
                if total_size and actual_size != total_size:
                    return False, f"Incomplete download: {actual_size}/{total_size} bytes"

                return True, None

        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}"
        except httpx.RequestError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Unexpected error: {e}"

    def download_video(
        self, slug: str, task_id: int | None = None
    ) -> tuple[bool, str | None]:
        """Download a single video.

        Args:
            slug: Video slug
            task_id: Rich progress task ID (optional)

        Returns:
            Tuple of (success, error_message)
        """
        # Check if already in archive
        if self._is_in_archive(slug):
            logger.info("Already downloaded (archive): %s", slug)
            return True, None

        # Check if video exists in database
        if not self.storage.video_exists(slug):
            return False, f"Video not found in database: {slug}"

        # Mark as downloading
        self.storage.mark_downloading(slug)

        with self._get_client() as client:
            # Step 1: Fetch video page
            logger.info("Fetching video page: %s", slug)
            html = self._fetch_video_page(client, slug)

            if not html:
                error_msg = "Failed to fetch video page"
                self.storage.mark_failed(slug, error_msg)
                return False, error_msg

            # Step 2: Extract video URL
            video_url = self._extract_video_url(html)

            if not video_url:
                error_msg = "Could not find video source URL in page"
                self.storage.mark_failed(slug, error_msg)
                return False, error_msg

            logger.debug("Found video URL: %s", video_url)

            # Step 3: Download video file
            output_path = self.output_dir / f"{slug}.mp4"

            logger.info("Downloading video: %s", slug)
            success, error = self._download_file(client, video_url, output_path, task_id)

            if not success:
                self.storage.mark_failed(slug, error)
                # Clean up partial file
                if output_path.exists():
                    output_path.unlink()
                return False, error

            # Step 4: Verify and save
            file_size = output_path.stat().st_size
            relative_path = f"downloads/{slug}.mp4"

            self.storage.mark_completed(slug, relative_path, file_size)
            self._save_to_archive(slug)

            logger.info("Downloaded: %s (%.2f MB)", slug, file_size / 1024 / 1024)

            return True, None

    def download_thumbnail(self, slug: str) -> Path | None:
        """Download thumbnail for a video.

        Resizes thumbnail to max 320px (Telegram Bot API requirement).

        Args:
            slug: Video slug

        Returns:
            Path to downloaded thumbnail or None if failed
        """
        # Get video metadata
        video = self.storage.get_video_by_slug(slug)
        if not video or not video.get("thumbnail_url"):
            logger.debug("No thumbnail URL for %s", slug)
            return None

        thumbnail_url = video["thumbnail_url"]
        output_path = self.output_dir / f"{slug}_thumb.jpg"

        # Skip if already exists
        if output_path.exists():
            return output_path

        try:
            with self._get_client() as client:
                response = client.get(thumbnail_url, follow_redirects=True)
                if response.status_code == 200:
                    # Resize image to max 320px (Telegram requirement)
                    img = Image.open(io.BytesIO(response.content))

                    # Calculate new size maintaining aspect ratio
                    max_dimension = 320
                    if max(img.size) > max_dimension:
                        ratio = max_dimension / max(img.size)
                        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                        img = img.resize(new_size, Image.Resampling.LANCZOS)

                    # Convert to RGB if necessary (for JPEG)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")

                    # Save as JPEG
                    img.save(output_path, "JPEG", quality=85)
                    logger.debug("Downloaded thumbnail: %s (%dx%d)",
                                 slug, img.size[0], img.size[1])
                    return output_path
                else:
                    logger.warning("Failed to download thumbnail for %s: HTTP %d",
                                   slug, response.status_code)
                    return None
        except Exception as e:
            logger.warning("Failed to download thumbnail for %s: %s", slug, e)
            return None

    def download_all(
        self,
        limit: int | None = None,
        retry_failed: bool = False,
    ) -> dict[str, int]:
        """Download all pending videos.

        Args:
            limit: Maximum number of videos to download
            retry_failed: If True, also retry failed downloads

        Returns:
            Dictionary with download statistics
        """
        pending = self.storage.get_pending_downloads(limit, include_failed=retry_failed)

        stats = {
            "total": len(pending),
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }

        if not pending:
            logger.info("No pending downloads")
            return stats

        logger.info("Starting download of %d videos", len(pending))

        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=None,  # Use default console
        ) as progress:
            self.progress = progress

            for i, slug in enumerate(pending, 1):
                # Add task for this download
                task = progress.add_task(f"[cyan]{slug[:40]}[/cyan]", total=None)

                success, error = self.download_video(slug, task)

                if success:
                    stats["completed"] += 1
                    progress.update(task, description=f"[green]✓[/green] {slug[:40]}")
                else:
                    stats["failed"] += 1
                    progress.update(
                        task, description=f"[red]✗[/red] {slug[:40]}: {error}"
                    )
                    logger.warning("Failed (%d/%d): %s - %s", i, len(pending), slug, error)

                # Apply delay between downloads
                if i < len(pending):
                    delay = random.uniform(self.sleep_interval[0], self.sleep_interval[1])
                    logger.debug("Waiting %.1f seconds before next download", delay)
                    time.sleep(delay)

        logger.info(
            "Download complete: %d completed, %d failed",
            stats["completed"],
            stats["failed"],
        )

        return stats
