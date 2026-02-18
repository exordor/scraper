"""Base uploader interface for video upload to various platforms."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UploadResult:
    """Result of an upload operation.

    Attributes:
        success: Whether the upload succeeded
        location_id: Platform-specific unique identifier (e.g., message_id, file_id)
        location_url: Publicly accessible URL if available
        error: Error message if failed
        metadata: Additional platform-specific information
    """

    success: bool
    location_id: str | None = None
    location_url: str | None = None
    error: str | None = None
    metadata: dict | None = field(default_factory=dict)


class Uploader(ABC):
    """Abstract base class for video uploaders.

    Subclasses must implement:
        - storage_type: Property returning the platform identifier
        - upload(): Method to upload a file
        - is_ready(): Check if the uploader is properly configured

    Example:
        class TelegramUploader(Uploader):
            @property
            def storage_type(self) -> str:
                return "telegram"

            def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
                # Implementation using Telegram API
                ...
    """

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """Return the storage type identifier.

        This is used to identify the platform in storage_locations table.
        Examples: "telegram", "google_drive", "aliyun", "s3"
        """
        pass

    @abstractmethod
    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        """Upload a video file to the platform.

        Args:
            file_path: Path to the video file
            slug: Video slug for reference
            **kwargs: Additional platform-specific parameters

        Returns:
            UploadResult with upload status and location info
        """
        pass

    def is_ready(self) -> bool:
        """Check if the uploader is properly configured and ready to use.

        Override this method to validate credentials and configuration.

        Returns:
            True if the uploader can be used, False otherwise
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(storage_type={self.storage_type})"


class MockUploader(Uploader):
    """Mock uploader for testing purposes.

    Does not actually upload files, just simulates success.
    """

    @property
    def storage_type(self) -> str:
        return "mock"

    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        """Simulate upload without actual network call."""
        if not file_path.exists():
            return UploadResult(
                success=False,
                error=f"File not found: {file_path}",
            )

        return UploadResult(
            success=True,
            location_id=f"mock_{slug}",
            location_url=f"https://mock.example.com/video/{slug}",
            metadata={"file_size": file_path.stat().st_size},
        )

    def is_ready(self) -> bool:
        return True
