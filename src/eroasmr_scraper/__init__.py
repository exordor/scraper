"""eroasmr-scraper: Video metadata scraper with Neo4j export support."""

__version__ = "0.1.0"

from eroasmr_scraper.config import Settings
from eroasmr_scraper.models import Video, VideoDetail

__all__ = ["__version__", "Settings", "Video", "VideoDetail"]
