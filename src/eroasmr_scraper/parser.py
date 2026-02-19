"""HTML parsing functions (backward compatibility)."""

import re

from eroasmr_scraper.sites.eroasmr.parser import (
    EroAsmrParser,
)
from eroasmr_scraper.base.parser import (
    parse_duration,
    parse_slug_from_url,
)


def parse_views(views_str: str | None) -> int:
    """Parse views string to integer.

    Args:
        views_str: Views string like "19.86K Views" or "1.5M Views"

    Returns:
        Views as integer
    """
    if not views_str:
        return 0

    # Extract number and suffix
    match = re.search(r"([\d.]+)\s*([KM]?)", views_str, re.IGNORECASE)
    if not match:
        return 0

    number_str, suffix = match.groups()
    try:
        number = float(number_str)
    except ValueError:
        return 0

    multiplier = 1
    if suffix.upper() == "K":
        multiplier = 1_000
    elif suffix.upper() == "M":
        multiplier = 1_000_000

    return int(number * multiplier)


# Re-export the class methods as functions for backward compatibility
def parse_list_page(html: str, base_url: str = "https://eroasmr.com"):
    """Parse video list from list page HTML."""
    parser = EroAsmrParser()
    result = parser.parse_list_page(html)
    return result.videos


def parse_detail_page(html: str, video, base_url: str = "https://eroasmr.com"):
    """Parse video detail page for extended metadata."""
    parser = EroAsmrParser()
    result = parser.parse_detail_page(html, video)
    return result.video_detail, result.tags, [], result.related_videos


def parse_total_pages(html: str):
    """Parse total number of pages from pagination."""
    parser = EroAsmrParser()
    return parser.parse_total_pages(html)


def is_404_page(html: str):
    """Check if the page is a 404 error page."""
    parser = EroAsmrParser()
    return parser.is_404_page(html)


def parse_video_source(html: str):
    """Parse video source URL from detail page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    # Try video > source first
    video = soup.select_one("video")
    if video:
        # Check video src attribute
        src = video.get("src")
        if src:
            return src

        # Check source tags
        source = video.select_one("source")
        if source:
            return source.get("src")

    # Try to find in script tags (some sites embed URL in JS)
    scripts = soup.select("script")
    for script in scripts:
        text = script.string or ""
        # Look for common video URL patterns
        matches = re.findall(r'(https?://[^\s"\'<>]+\.(?:mp4|m3u8|webm))', text)
        if matches:
            return matches[0]

    return None


__all__ = [
    "EroAsmrParser",
    "parse_duration",
    "parse_slug_from_url",
    "parse_views",
    "parse_list_page",
    "parse_detail_page",
    "parse_total_pages",
    "is_404_page",
    "parse_video_source",
]
