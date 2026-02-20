"""Telegram uploader using the Telegram Upload Service API."""

import logging
import subprocess
import os
from pathlib import Path

import httpx

from eroasmr_scraper.config import settings
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.uploader import UploadResult, Uploader

logger = logging.getLogger(__name__)

# Maximum file size for Telegram (in bytes) - 1900MB to be safe under 2GB limit
MAX_FILE_SIZE = 1900 * 1024 * 1024


class TelegramUploader(Uploader):
    """Upload videos to Telegram via the Upload Service API."""

    def __init__(
        self,
        upload_service_url: str | None = None,
        tenant_id: str | None = None,
        caption_template: str | None = None,
        parse_mode: str | None = None,
        file_path_map: dict[str, str] | None = None,
        storage: VideoStorage | None = None,
    ):
        """Initialize Telegram uploader.

        Args:
            upload_service_url: URL of the Telegram Upload Service
            tenant_id: Tenant ID for the upload service
            caption_template: Template for video caption with {title}, {slug}, {duration}
            parse_mode: Parse mode for caption (HTML, Markdown, or None)
            file_path_map: Mapping from local paths to container paths for Docker integration
            storage: VideoStorage instance for getting video metadata
        """
        self.upload_service_url = upload_service_url or settings.telegram.upload_service_url
        self.tenant_id = tenant_id or settings.telegram.tenant_id
        self.caption_template = caption_template or settings.telegram.caption_template
        self.parse_mode = parse_mode or settings.telegram.parse_mode
        self.file_path_map = file_path_map if file_path_map is not None else settings.telegram.file_path_map
        self.storage = storage

    @property
    def storage_type(self) -> str:
        """Return the storage type identifier."""
        return "telegram"

    def is_ready(self) -> bool:
        """Check if Telegram uploader is configured."""
        return bool(self.tenant_id and self.upload_service_url)

    def _map_file_path(self, file_path: Path) -> str:
        """Map local file path to container path if configured.

        Args:
            file_path: Local file path

        Returns:
            Mapped path (or original if no mapping configured)
        """
        # Resolve to absolute path for mapping
        path_str = str(file_path.resolve())
        for local_prefix, container_prefix in self.file_path_map.items():
            if path_str.startswith(local_prefix):
                return path_str.replace(local_prefix, container_prefix, 1)
        return path_str

    def _get_video_metadata(self, slug: str) -> dict:
        """Get video metadata from storage.

        Args:
            slug: Video slug

        Returns:
            Dict with thumbnail_url, duration_seconds, width, height
        """
        metadata = {
            "thumbnail_url": None,
            "duration": None,
            "width": None,
            "height": None,
        }

        if self.storage:
            video = self.storage.get_video_by_slug(slug)
            if video:
                metadata["thumbnail_url"] = video.get("thumbnail_url")
                metadata["duration"] = video.get("duration_seconds")
                # width and height would need to be extracted from video file
                # or stored during scraping - currently not available

        return metadata

    def _get_caption(self, slug: str) -> str:
        """Generate caption from video metadata.

        Args:
            slug: Video slug (may have _audio suffix for audio files)

        Returns:
            Formatted caption string
        """
        caption = self.caption_template

        # Always replace slug (use original slug for display)
        caption = caption.replace("{slug}", slug)

        # Default replacements in case metadata lookup fails
        title = slug
        duration = ""
        description = ""

        # For audio files, strip _audio suffix to get video slug
        video_slug = slug.replace("_audio", "")

        if self.storage:
            try:
                video = self.storage.get_video_by_slug(video_slug)
                if video:
                    title = video.get("title", video_slug)
                    duration = video.get("duration") or ""
                    # Handle description - use excerpt if description is empty
                    description = video.get("description") or video.get("excerpt") or ""
                    # Truncate description if too long (Telegram limit is 1024 chars for captions)
                    if len(description) > 800:
                        description = description[:797] + "..."
            except Exception as e:
                logger.warning("Failed to get video metadata for caption: %s", e)

        caption = caption.replace("{title}", title)
        caption = caption.replace("{duration}", duration)
        caption = caption.replace("{description}", description)

        return caption

    def _split_video(self, file_path: Path, max_size: int = MAX_FILE_SIZE) -> list[Path]:
        """Split video into parts if it exceeds max size.

        Args:
            file_path: Path to the video file
            max_size: Maximum size per part in bytes

        Returns:
            List of paths to split parts (or original file if no split needed)
        """
        file_size = file_path.stat().st_size

        if file_size <= max_size:
            return [file_path]

        # Calculate number of parts needed
        num_parts = (file_size + max_size - 1) // max_size

        logger.info(
            "File %s (%.1f MB) exceeds limit (%.1f MB), splitting into %d parts",
            file_path.name,
            file_size / 1024 / 1024,
            max_size / 1024 / 1024,
            num_parts,
        )

        # Get video duration using ffprobe
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(file_path)
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            total_duration = float(result.stdout.strip())
        except Exception as e:
            logger.error("Failed to get video duration: %s", e)
            return [file_path]

        # Calculate duration per part
        part_duration = total_duration / num_parts

        # Split video using ffmpeg
        parts = []
        base_name = file_path.stem
        ext = file_path.suffix
        output_dir = file_path.parent

        for i in range(num_parts):
            start_time = i * part_duration
            part_path = output_dir / f"{base_name}_part{i+1}{ext}"

            logger.info("Creating part %d/%d: %s", i + 1, num_parts, part_path.name)

            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-ss", str(start_time),
                        "-i", str(file_path),
                        "-t", str(part_duration),
                        "-c", "copy",  # Stream copy, no re-encoding
                        "-avoid_negative_ts", "1",
                        str(part_path)
                    ],
                    capture_output=True,
                    check=True,
                )
                parts.append(part_path)
            except subprocess.CalledProcessError as e:
                logger.error("Failed to split video part %d: %s", i + 1, e.stderr.decode() if e.stderr else str(e))
                # Clean up any created parts
                for p in parts:
                    p.unlink(missing_ok=True)
                return [file_path]

        logger.info("Split complete: %d parts created", len(parts))
        return parts

    def _upload_single(
        self,
        file_path: Path,
        slug: str,
        caption: str,
        thumbnail_path: Path | None = None,
        metadata: dict | None = None,
    ) -> UploadResult:
        """Upload a single file to Telegram.

        Args:
            file_path: Path to the file
            slug: Video slug
            caption: Caption for the message
            thumbnail_path: Path to thumbnail file
            metadata: Video metadata dict

        Returns:
            UploadResult with upload status
        """
        # Use synchronous upload endpoint
        url = f"{self.upload_service_url}/api/v1/upload/"

        # Map local path to container path if configured
        remote_file_path = self._map_file_path(file_path)

        # Map thumbnail path if provided
        remote_thumbnail_path = None
        if thumbnail_path:
            remote_thumbnail_path = self._map_file_path(thumbnail_path)

        # Build payload with all available metadata
        payload = {
            "tenant_id": self.tenant_id,
            "file_path": remote_file_path,
            "caption": caption,
            "parse_mode": self.parse_mode,
        }

        # Add thumbnail if available
        if remote_thumbnail_path:
            payload["thumbnail_path"] = remote_thumbnail_path
        elif metadata and metadata.get("thumbnail_url"):
            payload["thumbnail_url"] = metadata["thumbnail_url"]

        # Add video metadata if available
        if metadata:
            if metadata.get("duration"):
                payload["duration"] = metadata["duration"]
            if metadata.get("width"):
                payload["width"] = metadata["width"]
            if metadata.get("height"):
                payload["height"] = metadata["height"]

        try:
            with httpx.Client(timeout=600.0) as client:
                response = client.post(url, json=payload)

            if response.status_code != 200:
                return UploadResult(
                    success=False,
                    error=f"Upload service error: {response.status_code} - {response.text}",
                )

            result = response.json()

            if result.get("status") == "completed" and result.get("result"):
                upload_result = result["result"]
                return UploadResult(
                    success=True,
                    location_id=str(upload_result.get("message_id")),
                    location_url=upload_result.get("message_link"),
                    metadata={
                        "chat_id": upload_result.get("chat_id"),
                        "public_link": upload_result.get("public_link"),
                        "job_id": result.get("job_id"),
                    },
                )
            else:
                error = result.get("error", {})
                return UploadResult(
                    success=False,
                    error=error.get("message", "Unknown upload error"),
                    metadata={"error_code": error.get("code")},
                )

        except httpx.TimeoutException:
            return UploadResult(
                success=False,
                error="Upload timed out",
            )
        except Exception as e:
            return UploadResult(
                success=False,
                error=f"Upload failed: {e}",
            )

    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        """Upload file to Telegram via the Upload Service.

        Automatically splits large files (>2GB) into parts.

        Args:
            file_path: Path to the video file (local or mapped to container)
            slug: Video slug for reference
            **kwargs: Additional parameters (caption, thumbnail_path, etc.)

        Returns:
            UploadResult with upload status and location info
        """
        if not self.is_ready():
            return UploadResult(
                success=False,
                error="Telegram uploader not configured (missing tenant_id or service URL)",
            )

        if not file_path.exists():
            return UploadResult(
                success=False,
                error=f"File not found: {file_path}",
            )

        caption = kwargs.get("caption") or self._get_caption(slug)
        thumbnail_path = kwargs.get("thumbnail_path")

        # Get video metadata
        metadata = self._get_video_metadata(slug)

        # Check if file needs to be split
        file_size = file_path.stat().st_size
        parts = self._split_video(file_path)
        is_split = len(parts) > 1

        # Upload part(s)
        all_results = []
        for i, part_path in enumerate(parts):
            if is_split:
                # Add part indicator to caption
                part_caption = f"{caption}\n\n📹 Part {i + 1}/{len(parts)}"
            else:
                part_caption = caption

            logger.info("Uploading %s (part %d/%d)", part_path.name, i + 1, len(parts))
            result = self._upload_single(
                part_path,
                f"{slug}_part{i+1}" if is_split else slug,
                part_caption,
                thumbnail_path,
                metadata,
            )
            all_results.append(result)

            # Clean up split part after upload
            if is_split and part_path != file_path:
                try:
                    part_path.unlink()
                    logger.debug("Cleaned up split part: %s", part_path)
                except Exception as e:
                    logger.warning("Failed to clean up split part %s: %s", part_path, e)

        # Determine overall result
        successful = [r for r in all_results if r.success]
        failed = [r for r in all_results if not r.success]

        if len(successful) == len(all_results):
            # All parts uploaded successfully
            if is_split:
                return UploadResult(
                    success=True,
                    location_id=successful[0].location_id,
                    location_url=successful[0].location_url,
                    metadata={
                        "parts": len(parts),
                        "message_ids": [r.location_id for r in successful],
                    },
                )
            return successful[0]
        elif len(successful) > 0:
            # Partial success
            return UploadResult(
                success=True,
                location_id=successful[0].location_id,
                location_url=successful[0].location_url,
                metadata={
                    "parts_uploaded": len(successful),
                    "parts_failed": len(failed),
                    "error": "; ".join(r.error or "Unknown error" for r in failed),
                },
            )
        else:
            # All failed
            return UploadResult(
                success=False,
                error="; ".join(r.error or "Unknown error" for r in failed),
            )
