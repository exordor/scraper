"""Zhumianwang-specific models."""

from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail, BaseTag, BaseRelatedVideo


class Region(str, Enum):
    """Video region/origin."""
    CHINA = "中国"
    KOREA = "韩国"
    JAPAN = "日本"
    WESTERN = "欧美"
    UNKNOWN = "未知"


class MemberStatus(str, Enum):
    """Member access status."""
    FREE = "free"
    MEMBER = "member"
    UNKNOWN = "unknown"


class Video(BaseVideo):
    """Video metadata from zhumianwang.com list page."""

    site_id: str = "zhumianwang"

    # Author info
    author: str | None = None

    # Date info
    published_date: str | None = None

    # Member status
    member_status: MemberStatus = MemberStatus.UNKNOWN

    @field_validator("slug", mode="before")
    @classmethod
    def extract_slug(cls, v: Any) -> str:
        """Extract slug from URL if needed."""
        if isinstance(v, str):
            # Handle /asmr/42813.html format
            v = v.replace(".html", "")
            return v.rstrip("/").split("/")[-1]
        return str(v)


class VideoDetail(Video, BaseVideoDetail):
    """Extended video metadata from zhumianwang.com detail page."""

    # Region/origin
    region: Region = Region.UNKNOWN

    # Year of production
    year: int | None = None

    # Update time
    update_time: str | None = None

    # Play link (encoded)
    play_url: str | None = None

    # Download links (requires login)
    download_url: str | None = None
    audio_download_url: str | None = None


class Tag(BaseTag):
    """Tag entity for zhumianwang.com."""
    tag_url: str | None = None


class RelatedVideo(BaseRelatedVideo):
    """Related video from zhumianwang.com recommendations."""
    member_status: MemberStatus = MemberStatus.UNKNOWN
