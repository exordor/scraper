"""Pydantic data models for video metadata."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Video(BaseModel):
    """Video metadata from list page."""

    title: str
    slug: str
    video_url: str
    thumbnail_url: str | None = None

    # Duration
    duration: str | None = None  # "MM:SS" or "HH:MM:SS"
    duration_seconds: int | None = None

    # Statistics
    likes: int = 0
    views: int = 0
    views_raw: str | None = None  # Original "19.86K Views"

    # Text content
    excerpt: str | None = None

    # Timestamps
    scraped_at: datetime = Field(default_factory=datetime.now)

    @field_validator("slug", mode="before")
    @classmethod
    def extract_slug(cls, v: Any) -> str:
        """Extract slug from URL if needed."""
        if isinstance(v, str):
            # Remove trailing slash and extract last segment
            return v.rstrip("/").split("/")[-1]
        return str(v)


class VideoDetail(Video):
    """Extended video metadata from detail page."""

    # Full description
    description: str | None = None

    # Author info
    author: str | None = None
    author_url: str | None = None
    author_videos_count: int | None = None

    # Comments
    comment_count: int = 0

    # Timestamps
    published_at: str | None = None
    detail_scraped_at: datetime = Field(default_factory=datetime.now)


class Tag(BaseModel):
    """Tag entity."""

    name: str
    slug: str
    tag_url: str | None = None


class Category(BaseModel):
    """Category entity."""

    name: str
    slug: str
    category_url: str | None = None
    video_count: int = 0


class RelatedVideo(BaseModel):
    """Related video reference from 'You May Be Interested In' section."""

    title: str
    slug: str
    video_url: str
    thumbnail_url: str | None = None
    position: int = 0  # Position in recommendation list (1-4)


class ScrapeProgress(BaseModel):
    """Scraping progress state."""

    mode: str  # 'full' or 'incremental'
    phase: str  # 'list' or 'detail'
    last_page: int = 0
    last_video_id: int = 0
    total_pages: int | None = None
    last_updated: datetime = Field(default_factory=datetime.now)


class FailedUrl(BaseModel):
    """Record of failed URL for retry."""

    url: str
    url_type: str  # 'list' or 'detail'
    error: str | None = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
