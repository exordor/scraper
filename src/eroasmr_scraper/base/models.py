"""Base models shared across all sites."""

from abc import ABC
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DownloadStatus(str, Enum):
    """Download status for videos."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseVideo(BaseModel, ABC):
    """Base video model - site-specific implementations extend this."""

    title: str
    slug: str
    video_url: str
    thumbnail_url: str | None = None
    duration: str | None = None
    duration_seconds: int | None = None
    site_id: str  # Identifier for which site this video belongs to
    scraped_at: datetime = Field(default_factory=datetime.now)


class BaseVideoDetail(BaseModel, ABC):
    """Base video detail model - site-specific implementations extend this."""

    description: str | None = None
    author: str | None = None
    detail_scraped_at: datetime = Field(default_factory=datetime.now)


class BaseTag(BaseModel):
    """Base tag entity."""
    name: str
    slug: str


class BaseRelatedVideo(BaseModel):
    """Base related video reference."""
    title: str
    slug: str
    video_url: str
    thumbnail_url: str | None = None
    position: int = 0


class ScrapeProgress(BaseModel):
    """Scraping progress state."""
    site_id: str  # Which site this progress belongs to
    mode: str  # 'full' or 'incremental'
    phase: str  # 'list', 'detail', or 'play'
    last_page: int = 0
    last_video_id: int = 0
    total_pages: int | None = None
    last_updated: datetime = Field(default_factory=datetime.now)


class FailedUrl(BaseModel):
    """Record of failed URL for retry."""
    site_id: str
    url: str
    url_type: str  # 'list', 'detail', or 'play'
    error: str | None = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class VideoDownload(BaseModel):
    """Download record for tracking video download status."""
    slug: str
    site_id: str
    status: DownloadStatus = DownloadStatus.PENDING
    local_path: str | None = None
    file_size: int | None = None
    error_message: str | None = None
    downloaded_at: datetime | None = None


class StorageLocation(BaseModel):
    """Network storage location for uploaded videos."""
    slug: str
    site_id: str
    storage_type: str
    location_id: str
    location_url: str | None = None
    metadata: dict[str, Any] | None = None
    uploaded_at: datetime = Field(default_factory=datetime.now)
