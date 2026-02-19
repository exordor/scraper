"""Video metadata models (backward compatibility)."""

from eroasmr_scraper.sites.eroasmr.models import (
    Video,
    VideoDetail,
    Tag,
    Category,
    RelatedVideo,
)
from eroasmr_scraper.base.models import (
    ScrapeProgress,
    FailedUrl,
    VideoDownload,
    StorageLocation,
    DownloadStatus,
)

__all__ = [
    "Video",
    "VideoDetail",
    "Tag",
    "Category",
    "RelatedVideo",
    "ScrapeProgress",
    "FailedUrl",
    "VideoDownload",
    "StorageLocation",
    "DownloadStatus",
]
