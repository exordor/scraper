"""Abstract parser protocol for site-specific parsers."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail, BaseTag, BaseRelatedVideo


class ListPageResult(BaseModel):
    """Result of parsing a list page."""
    videos: list[BaseVideo]
    total_pages: int | None = None


class DetailPageResult(BaseModel):
    """Result of parsing a detail page."""
    video_detail: BaseVideoDetail
    tags: list[BaseTag] = []
    related_videos: list[BaseRelatedVideo] = []
    extra: dict[str, Any] = {}


class BaseSiteParser(ABC):
    """Abstract base class for site parsers with common utilities."""

    site_id: str
    base_url: str

    @abstractmethod
    def parse_list_page(self, html: str) -> ListPageResult:
        """Parse video list from list page HTML."""
        pass

    @abstractmethod
    def parse_detail_page(self, html: str, video: BaseVideo) -> DetailPageResult:
        """Parse video detail page for extended metadata."""
        pass

    @abstractmethod
    def is_404_page(self, html: str) -> bool:
        """Check if the page is a 404 error page."""
        pass

    @abstractmethod
    def parse_total_pages(self, html: str) -> int | None:
        """Parse total number of pages from pagination."""
        pass

    @staticmethod
    def parse_duration(duration_str: str | None) -> int | None:
        """Parse duration string to seconds."""
        return parse_duration(duration_str)

    @staticmethod
    def parse_slug_from_url(url: str) -> str:
        """Extract slug from URL."""
        return parse_slug_from_url(url)


def parse_duration(duration_str: str | None) -> int | None:
    """Parse duration string to seconds.

    Args:
        duration_str: Duration string like "07:11", "1:23:45", "29.19", or "11\"59"

    Returns:
        Duration in seconds, or None if parsing fails
    """
    if not duration_str:
        return None

    # Normalize separators: replace . and " with :
    normalized = duration_str.strip().replace(".", ":").replace('"', ":")

    parts = normalized.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        try:
            return int(minutes) * 60 + int(seconds)
        except ValueError:
            return None
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        try:
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        except ValueError:
            return None
    return None


def parse_slug_from_url(url: str) -> str:
    """Extract slug from URL.

    Args:
        url: Full or partial URL

    Returns:
        Slug (last path segment)
    """
    return url.rstrip("/").split("/")[-1]
