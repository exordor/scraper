"""Video downloader using httpx with direct URL extraction."""

import io
import json
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

# Proxy configuration for zhumianwang CDN (Hong Kong server)
ZHUMIANWANG_PROXY = "http://202.155.141.121:3128"

# Zhumianwang play parser - lazy import to avoid circular deps
_zhumianwang_parser = None


def _get_zhumianwang_parser():
    """Lazy load zhumianwang parser."""
    global _zhumianwang_parser
    if _zhumianwang_parser is None:
        from eroasmr_scraper.sites.zhumianwang.play_parser import ZhumianwangPlayParser
        _zhumianwang_parser = ZhumianwangPlayParser()
    return _zhumianwang_parser


# Cache for zhumianwang cookies
_zhumianwang_cookies: dict | None = None


def _load_zhumianwang_cookies() -> dict | None:
    """Load zhumianwang cookies from cookies.json file."""
    global _zhumianwang_cookies
    if _zhumianwang_cookies is not None:
        return _zhumianwang_cookies

    # Try multiple possible locations for cookies.json
    possible_paths = [
        # Project root relative to this file (src/eroasmr_scraper/downloader.py)
        Path(__file__).parent.parent.parent.parent / "data" / "cookies.json",
        # Current working directory
        Path.cwd() / "data" / "cookies.json",
        # Direct path
        Path("/root/eroasmr-scraper/data/cookies.json"),
    ]

    cookies_file = None
    for path in possible_paths:
        if path.exists():
            cookies_file = path
            break

    if not cookies_file:
        logger.warning("Zhumianwang cookies file not found in: %s", [str(p) for p in possible_paths])
        return None

    try:
        cookies_list = json.loads(cookies_file.read_text())
        # Convert to dict format for httpx
        _zhumianwang_cookies = {
            c["name"]: c["value"]
            for c in cookies_list
            if "zhumian" in c.get("domain", "")
        }
        logger.info("Loaded %d zhumianwang cookies", len(_zhumianwang_cookies))
        return _zhumianwang_cookies
    except Exception as e:
        logger.error("Failed to load zhumianwang cookies: %s", e)
        return None


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

    def _fetch_zhumianwang_play_page(self, play_url: str) -> tuple[str | None, str | None]:
        """Fetch zhumianwang play page and extract download URLs.

        Args:
            play_url: URL to the play page (e.g., /v_play/xxx.html)

        Returns:
            Tuple of (video_url, audio_url) or (None, None) if failed
        """
        cookies = _load_zhumianwang_cookies()
        if not cookies:
            return None, None

        # Build full URL if needed
        if not play_url.startswith("http"):
            play_url = f"https://www.zhumianzhan.com{play_url}"

        headers = {
            "User-Agent": settings.http.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.zhumianzhan.com/",
        }

        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(play_url, cookies=cookies, headers=headers)
                if response.status_code != 200:
                    logger.error("Failed to fetch play page: HTTP %d", response.status_code)
                    return None, None

                # Parse download URLs from play page
                parser = _get_zhumianwang_parser()
                result = parser.parse_play_page(response.text)
                return result.video_download_url, result.audio_download_url

        except Exception as e:
            logger.error("Error fetching zhumianwang play page: %s", e)
            return None, None

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
        use_proxy: bool = False,
    ) -> tuple[bool, str | None]:
        """Download file with progress support.

        Args:
            client: HTTP client
            url: File URL
            output_path: Output file path
            task_id: Rich progress task ID (optional)
            use_proxy: If True, use zhumianwang proxy for CDN access

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Use proxy client for zhumianwang CDN URLs
            download_client = client
            if use_proxy and "video.zklhy.com" in url:
                download_client = httpx.Client(
                    proxy=ZHUMIANWANG_PROXY,
                    timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0),
                    follow_redirects=True,
                )
                logger.info("Using HK proxy for zhumianwang CDN: %s", url[:60])

            # Use stream for large files
            with download_client.stream("GET", url) as response:
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
        self, slug: str, task_id: int | None = None, include_audio: bool = False
    ) -> tuple[bool, str | None]:
        """Download a single video.

        For eroasmr.com: Fetches video page and extracts URL.
        For zhumianwang: Uses pre-scraped download_url from database.

        Args:
            slug: Video slug
            task_id: Rich progress task ID (optional)
            include_audio: If True, also download audio file (zhumianwang only)

        Returns:
            Tuple of (success, error_message)
        """
        # Check if already in archive
        if self._is_in_archive(slug):
            logger.info("Already downloaded (archive): %s", slug)
            return True, None

        # Check if video exists in database
        video = self.storage.get_video_by_slug(slug)
        if not video:
            return False, f"Video not found in database: {slug}"

        site_id = video.get("site_id", "eroasmr")

        # Mark as downloading
        self.storage.mark_downloading(slug)

        with self._get_client() as client:
            video_url = None
            audio_url = None

            # Get download URLs based on site
            if site_id == "zhumianwang":
                # Fetch play page with cookies to get download URLs
                play_url = video.get("play_url")
                if not play_url:
                    error_msg = "No play_url in database for zhumianwang video"
                    self.storage.mark_failed(slug, error_msg)
                    return False, error_msg

                logger.info("Fetching zhumianwang play page: %s", play_url)
                video_url, audio_url = self._fetch_zhumianwang_play_page(play_url)

                if not video_url:
                    error_msg = "Failed to extract download URL from play page"
                    self.storage.mark_failed(slug, error_msg)
                    return False, error_msg

                logger.debug("Extracted video URL: %s", video_url[:80] if video_url else None)
            else:
                # eroasmr: Fetch video page and extract URL
                logger.info("Fetching video page: %s", slug)
                html = self._fetch_video_page(client, slug)

                if not html:
                    error_msg = "Failed to fetch video page"
                    self.storage.mark_failed(slug, error_msg)
                    return False, error_msg

                video_url = self._extract_video_url(html)

                if not video_url:
                    error_msg = "Could not find video source URL in page"
                    self.storage.mark_failed(slug, error_msg)
                    return False, error_msg

            logger.debug("Found video URL: %s", video_url)

            # Download video file
            output_path = self.output_dir / f"{slug}.mp4"

            # Use proxy for zhumianwang CDN
            use_proxy = site_id == "zhumianwang"

            logger.info("Downloading video: %s", slug)
            success, error = self._download_file(client, video_url, output_path, task_id, use_proxy=use_proxy)

            if not success:
                self.storage.mark_failed(slug, error)
                # Clean up partial file
                if output_path.exists():
                    output_path.unlink()
                return False, error

            # Download audio file if requested (zhumianwang only)
            audio_path = None
            if include_audio and audio_url and site_id == "zhumianwang":
                audio_path = self.output_dir / f"{slug}.mp3"
                logger.info("Downloading audio: %s", slug)
                audio_success, audio_error = self._download_file(client, audio_url, audio_path, task_id, use_proxy=True)

                if not audio_success:
                    logger.warning("Failed to download audio for %s: %s", slug, audio_error)
                    # Don't fail the whole download, just log the warning
                    audio_path = None

            # Verify and save
            file_size = output_path.stat().st_size
            relative_path = f"downloads/{slug}.mp4"

            # Store audio path if downloaded
            if audio_path and audio_path.exists():
                audio_size = audio_path.stat().st_size
                self.storage.mark_completed(slug, relative_path, file_size, audio_path=f"downloads/{slug}.mp3", audio_size=audio_size)
            else:
                self.storage.mark_completed(slug, relative_path, file_size)

            self._save_to_archive(slug)

            logger.info("Downloaded: %s (%.2f MB)", slug, file_size / 1024 / 1024)

            return True, None

    def download_audio(self, slug: str, task_id: int | None = None) -> tuple[bool, str | None]:
        """Download audio file for a video (zhumianwang only).

        Args:
            slug: Video slug
            task_id: Rich progress task ID (optional)

        Returns:
            Tuple of (success, error_message)
        """
        # Check if video exists in database
        video = self.storage.get_video_by_slug(slug)
        if not video:
            return False, f"Video not found in database: {slug}"

        site_id = video.get("site_id", "eroasmr")
        if site_id != "zhumianwang":
            return False, "Audio download only supported for zhumianwang"

        audio_url = video.get("audio_download_url")
        if not audio_url:
            return False, "No audio_download_url in database"

        output_path = self.output_dir / f"{slug}.mp3"

        # Skip if already exists
        if output_path.exists():
            logger.info("Audio already exists: %s", slug)
            return True, None

        with self._get_client() as client:
            logger.info("Downloading audio: %s", slug)
            success, error = self._download_file(client, audio_url, output_path, task_id, use_proxy=True)

            if not success:
                if output_path.exists():
                    output_path.unlink()
                return False, error

            file_size = output_path.stat().st_size
            logger.info("Downloaded audio: %s (%.2f MB)", slug, file_size / 1024 / 1024)

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
