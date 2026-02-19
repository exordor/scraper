"""EroAsmr-specific models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail, BaseTag, BaseRelatedVideo


class Video(BaseVideo):
    """Video metadata from eroasmr.com list page."""

    site_id: str = "eroasmr"

    # Statistics (site-specific)
    likes: int = 0
    views: int = 0
    views_raw: str | None = None

    # Text content
    excerpt: str | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def extract_slug(cls, v: Any) -> str:
        """Extract slug from URL if needed."""
        if isinstance(v, str):
            return v.rstrip("/").split("/")[-1]
        return str(v)


class VideoDetail(Video, BaseVideoDetail):
    """Extended video metadata from eroasmr.com detail page."""

    author_url: str | None = None
    author_videos_count: int | None = None
    comment_count: int = 0
    published_at: str | None = None


class Tag(BaseTag):
    """Tag entity for eroasmr.com."""
    tag_url: str | None = None


class Category(BaseModel):
    """Category entity for eroasmr.com."""
    name: str
    slug: str
    category_url: str | None = None
    video_count: int = 0


class RelatedVideo(BaseRelatedVideo):
    """Related video from eroasmr.com."""
    pass
