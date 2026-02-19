"""Base classes for multi-site scraper."""

from eroasmr_scraper.base.models import (
    BaseVideo,
    BaseVideoDetail,
    BaseTag,
    BaseRelatedVideo,
    ScrapeProgress,
    FailedUrl,
)
from eroasmr_scraper.base.parser import BaseSiteParser
from eroasmr_scraper.base.scraper import BaseSiteScraper

__all__ = [
    "BaseVideo",
    "BaseVideoDetail",
    "BaseTag",
    "BaseRelatedVideo",
    "ScrapeProgress",
    "FailedUrl",
    "BaseSiteParser",
    "BaseSiteScraper",
]
