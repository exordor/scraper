"""Telegram uploader using the Telegram Upload Service API."""

import logging
from pathlib import Path

import httpx

from eroasmr_scraper.config import settings
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.uploader import UploadResult, Uploader

logger = logging.getLogger(__name__)


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
            slug: Video slug

        Returns:
            Formatted caption string
        """
        caption = self.caption_template

        # Always replace slug
        caption = caption.replace("{slug}", slug)

        if self.storage:
            video = self.storage.get_video_by_slug(slug)
            if video:
                caption = caption.replace("{title}", video.get("title", slug))
                caption = caption.replace("{duration}", video.get("duration") or "")
                # Handle description - use excerpt if description is empty
                description = video.get("description") or video.get("excerpt") or ""
                # Truncate description if too long (Telegram limit is 1024 chars for captions)
                if len(description) > 800:
                    description = description[:797] + "..."
                caption = caption.replace("{description}", description)

        return caption

    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        """Upload file to Telegram via the Upload Service.

        Uses synchronous upload endpoint to get immediate result.

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
        elif metadata.get("thumbnail_url"):
            payload["thumbnail_url"] = metadata["thumbnail_url"]

        # Add video metadata if available
        if metadata.get("duration"):
            payload["duration"] = metadata["duration"]
        if metadata.get("width"):
            payload["width"] = metadata["width"]
        if metadata.get("height"):
            payload["height"] = metadata["height"]

        try:
            with httpx.Client(timeout=600.0) as client:  # 10 min timeout for large files
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
