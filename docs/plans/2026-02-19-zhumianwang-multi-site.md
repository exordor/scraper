# Zhumianwang Multi-Site Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend eroasmr-scraper to support multi-site scraping with zhumianwang.com, including authenticated download link extraction.

**Architecture:** Abstract Factory pattern with base classes for models/parsers/scrapers, site-specific implementations in `sites/` subdirectories, Playwright-based cookie authentication for download links.

**Tech Stack:** Python 3.11+, pydantic-settings, httpx, BeautifulSoup4, sqlite-utils, Playwright (for auth)

---

## Task 1: Create Base Infrastructure - Directory Structure

**Files:**
- Create: `src/eroasmr_scraper/base/__init__.py`

**Step 1: Create base directory**

Run:
```bash
cd /Users/jlw/code/python/eroasmr-scraper
mkdir -p src/eroasmr_scraper/base
mkdir -p src/eroasmr_scraper/sites/eroasmr
mkdir -p src/eroasmr_scraper/sites/zhumianwang
mkdir -p src/eroasmr_scraper/auth
```

**Step 2: Create base/__init__.py**

```python
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
```

**Step 3: Commit**

```bash
git add src/eroasmr_scraper/base/__init__.py
git commit -m "feat: create base directory structure for multi-site support"
```

---

## Task 2: Create Base Models

**Files:**
- Create: `src/eroasmr_scraper/base/models.py`
- Test: `tests/test_base_models.py`

**Step 1: Write failing test**

```python
# tests/test_base_models.py
"""Tests for base models."""

import pytest
from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail, BaseTag


class TestBaseModels:
    def test_base_video_requires_site_id(self):
        """BaseVideo should require site_id."""
        with pytest.raises(Exception):  # ValidationError
            BaseVideo(
                title="Test Video",
                slug="test-video",
                video_url="https://example.com/video/test",
            )

    def test_base_video_with_site_id(self):
        """BaseVideo should work with site_id."""
        video = BaseVideo(
            title="Test Video",
            slug="test-video",
            video_url="https://example.com/video/test",
            site_id="test_site",
        )
        assert video.title == "Test Video"
        assert video.site_id == "test_site"

    def test_base_tag(self):
        """BaseTag should have name and slug."""
        tag = BaseTag(name="Test Tag", slug="test-tag")
        assert tag.name == "Test Tag"
        assert tag.slug == "test-tag"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create base/models.py**

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_base_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/eroasmr_scraper/base/models.py tests/test_base_models.py
git commit -m "feat: add base models for multi-site support"
```

---

## Task 3: Create Base Parser

**Files:**
- Create: `src/eroasmr_scraper/base/parser.py`
- Test: `tests/test_base_parser.py`

**Step 1: Write failing test**

```python
# tests/test_base_parser.py
"""Tests for base parser."""

import pytest
from eroasmr_scraper.base.parser import BaseSiteParser, parse_duration, parse_slug_from_url


class TestParseDuration:
    def test_parse_mm_ss(self):
        """Parse MM:SS format."""
        assert parse_duration("07:11") == 431

    def test_parse_hh_mm_ss(self):
        """Parse HH:MM:SS format."""
        assert parse_duration("1:23:45") == 5025

    def test_parse_none(self):
        """Parse None returns None."""
        assert parse_duration(None) is None

    def test_parse_dot_separator(self):
        """Parse dot separator format."""
        assert parse_duration("29.19") == 1759


class TestParseSlugFromUrl:
    def test_parse_from_url(self):
        """Extract slug from URL."""
        assert parse_slug_from_url("https://example.com/video/my-slug/") == "my-slug"

    def test_parse_from_partial(self):
        """Extract slug from partial URL."""
        assert parse_slug_from_url("/video/my-slug") == "my-slug"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_base_parser.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create base/parser.py**

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_base_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/eroasmr_scraper/base/parser.py tests/test_base_parser.py
git commit -m "feat: add base parser with utility functions"
```

---

## Task 4: Create Base Scraper

**Files:**
- Create: `src/eroasmr_scraper/base/scraper.py`

**Step 1: Create base/scraper.py**

```python
"""Abstract scraper protocol for site-specific scrapers."""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx

from eroasmr_scraper.base.parser import BaseSiteParser


class BaseSiteScraper(ABC):
    """Abstract base class for site scrapers with shared HTTP logic."""

    site_id: str
    parser: BaseSiteParser
    settings: Any
    _total_pages: int | None = None

    def __init__(self, storage: Any = None):
        """Initialize scraper with optional storage."""
        self.storage = storage
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    def build_list_url(self, page: int) -> str:
        """Build list page URL for given page number."""
        pass

    @abstractmethod
    def get_site_settings(self) -> Any:
        """Get site-specific settings."""
        pass

    def _get_client(self, settings: Any = None) -> httpx.AsyncClient:
        """Create configured HTTP client."""
        if self._client is None:
            s = settings or self.settings
            limits = httpx.Limits(
                max_connections=s.http.max_connections,
                max_keepalive_connections=s.http.max_keepalive,
            )
            timeout = httpx.Timeout(
                connect=s.http.timeout_connect,
                read=s.http.timeout_read,
                write=s.http.timeout_write,
                pool=s.http.timeout_pool,
            )
            self._client = httpx.AsyncClient(
                limits=limits,
                timeout=timeout,
                headers={"User-Agent": s.http.user_agent},
                follow_redirects=True,
            )
        return self._client

    async def _delay(self) -> None:
        """Apply random delay between requests."""
        delay = random.uniform(
            self.settings.http.delay_min,
            self.settings.http.delay_max,
        )
        await asyncio.sleep(delay)

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        max_retries: int | None = None,
    ) -> str:
        """Fetch URL with exponential backoff retry."""
        retries = max_retries or self.settings.http.max_retries

        for attempt in range(retries + 1):
            try:
                await self._delay()
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited - exponential backoff
                    wait_time = (2**attempt) * 5
                    await asyncio.sleep(wait_time)
                elif e.response.status_code >= 500:
                    # Server error - retry
                    if attempt < retries:
                        await asyncio.sleep((2**attempt) * 2)
                        continue
                    raise
                else:
                    raise
            except httpx.RequestError:
                if attempt < retries:
                    await asyncio.sleep((2**attempt) * 2)
                    continue
                raise

        raise RuntimeError(f"Failed to fetch {url} after {retries} retries")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/base/scraper.py
git commit -m "feat: add base scraper with HTTP utilities"
```

---

## Task 5: Create Factory Module

**Files:**
- Create: `src/eroasmr_scraper/factory.py`
- Test: `tests/test_factory.py`

**Step 1: Write failing test**

```python
# tests/test_factory.py
"""Tests for scraper factory."""

import pytest
from eroasmr_scraper.factory import ScraperFactory


class TestScraperFactory:
    def test_list_sites_empty_initially(self):
        """Factory should start with no sites registered."""
        # Reset for test isolation
        factory = ScraperFactory()
        factory._registry.clear()
        assert factory.list_sites() == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_factory.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Create factory.py**

```python
"""Factory for creating site-specific scrapers."""

from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from eroasmr_scraper.base.scraper import BaseSiteScraper


class ScraperFactory:
    """Factory for creating site-specific scraper instances."""

    _registry: dict[str, Type["BaseSiteScraper"]] = {}

    @classmethod
    def register(cls, site_id: str, scraper_class: Type["BaseSiteScraper"]) -> None:
        """Register a scraper class for a site."""
        cls._registry[site_id] = scraper_class

    @classmethod
    def create(cls, site_id: str, storage: any = None) -> "BaseSiteScraper":
        """Create a scraper instance for a site."""
        if site_id not in cls._registry:
            raise ValueError(
                f"Unknown site: {site_id}. Available: {list(cls._registry.keys())}"
            )
        scraper_class = cls._registry[site_id]
        return scraper_class(storage=storage)

    @classmethod
    def list_sites(cls) -> list[str]:
        """List all registered sites."""
        return list(cls._registry.keys())


def register_scraper(site_id: str):
    """Decorator to auto-register a scraper class."""
    def decorator(cls: Type["BaseSiteScraper"]) -> Type["BaseSiteScraper"]:
        ScraperFactory.register(site_id, cls)
        return cls
    return decorator
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_factory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/eroasmr_scraper/factory.py tests/test_factory.py
git commit -m "feat: add scraper factory for multi-site support"
```

---

## Task 6: Migrate eroasmr to sites/eroasmr/ - Models

**Files:**
- Create: `src/eroasmr_scraper/sites/__init__.py`
- Create: `src/eroasmr_scraper/sites/eroasmr/__init__.py`
- Create: `src/eroasmr_scraper/sites/eroasmr/models.py`

**Step 1: Create sites/__init__.py**

```python
"""Site-specific scraper implementations."""
```

**Step 2: Create sites/eroasmr/__init__.py**

```python
"""EroAsmr site implementation."""

from eroasmr_scraper.sites.eroasmr.models import Video, VideoDetail, Tag, Category, RelatedVideo
from eroasmr_scraper.sites.eroasmr.parser import EroAsmrParser
from eroasmr_scraper.sites.eroasmr.scraper import EroAsmrScraper

__all__ = [
    "Video",
    "VideoDetail",
    "Tag",
    "Category",
    "RelatedVideo",
    "EroAsmrParser",
    "EroAsmrScraper",
]
```

**Step 3: Create sites/eroasmr/models.py**

```python
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
```

**Step 4: Commit**

```bash
git add src/eroasmr_scraper/sites/__init__.py src/eroasmr_scraper/sites/eroasmr/__init__.py src/eroasmr_scraper/sites/eroasmr/models.py
git commit -m "refactor: create eroasmr site-specific models"
```

---

## Task 7: Migrate eroasmr Parser

**Files:**
- Create: `src/eroasmr_scraper/sites/eroasmr/parser.py`

**Step 1: Create sites/eroasmr/parser.py (copy from existing parser.py)**

```python
"""HTML parsing functions for eroasmr.com."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from eroasmr_scraper.base.parser import BaseSiteParser, ListPageResult, DetailPageResult
from eroasmr_scraper.sites.eroasmr.models import (
    Category,
    RelatedVideo,
    Tag,
    Video,
    VideoDetail,
)


class EroAsmrParser(BaseSiteParser):
    """Parser for eroasmr.com."""

    site_id = "eroasmr"
    base_url = "https://eroasmr.com"

    def parse_list_page(self, html: str) -> ListPageResult:
        """Parse video list from list page HTML."""
        soup = BeautifulSoup(html, "lxml")
        videos: list[Video] = []

        articles = soup.select("article")

        for article in articles:
            title_elem = article.select_one("h2 a, h3 a, .entry-title a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            video_url = title_elem.get("href", "")
            if video_url and not video_url.startswith("http"):
                video_url = urljoin(self.base_url, video_url)

            slug = self.parse_slug_from_url(video_url)

            img_elem = article.select_one("img")
            thumbnail_url = img_elem.get("src") or img_elem.get("data-src") if img_elem else None

            duration_elem = article.select_one(".video-duration")
            duration = duration_elem.get_text(strip=True) if duration_elem else None
            duration_seconds = self.parse_duration(duration)

            likes_elem = article.select_one(".video-like-counter")
            likes_text = likes_elem.get_text(strip=True) if likes_elem else "0"
            likes = int(re.search(r"\d+", likes_text).group()) if re.search(r"\d+", likes_text) else 0

            views_elem = article.select_one(".post-views")
            if not views_elem:
                views_elem = article.select_one(".entry-meta")
            views_raw = views_elem.get_text(strip=True) if views_elem else None
            views = self._parse_views(views_raw)

            excerpt_elem = article.select_one(".excerpt, .entry-summary, p")
            excerpt = excerpt_elem.get_text(strip=True) if excerpt_elem else None

            video = Video(
                title=title,
                slug=slug,
                video_url=video_url,
                thumbnail_url=thumbnail_url,
                duration=duration,
                duration_seconds=duration_seconds,
                likes=likes,
                views=views,
                views_raw=views_raw,
                excerpt=excerpt,
            )
            videos.append(video)

        total_pages = self.parse_total_pages(html)
        return ListPageResult(videos=videos, total_pages=total_pages)

    def parse_detail_page(self, html: str, video: Video) -> DetailPageResult:
        """Parse video detail page for extended metadata."""
        soup = BeautifulSoup(html, "lxml")

        desc_elem = soup.select_one(".entry-content, .description, .video-description, article p")
        description = desc_elem.get_text(strip=True) if desc_elem else None

        author_elem = soup.select_one(".author, .posted-by, [class*='author']")
        author = author_elem.get_text(strip=True) if author_elem else None
        author_url = None
        if author_elem and author_elem.name == "a":
            author_url = author_elem.get("href")
            if author_url and not author_url.startswith("http"):
                author_url = urljoin(self.base_url, author_url)

        comment_elem = soup.select_one(".comments-count, .comment-count, [class*='comment']")
        comment_count = 0
        if comment_elem:
            match = re.search(r"\d+", comment_elem.get_text())
            if match:
                comment_count = int(match.group())

        date_elem = soup.select_one("time, .date, .published, [class*='date']")
        published_at = date_elem.get("datetime") or date_elem.get_text(strip=True) if date_elem else None

        tags: list[Tag] = []
        tag_elems = soup.select(".tags a, .video-tags a, a[href*='video-tag'], [rel='tag']")
        for tag_elem in tag_elems:
            tag_name = tag_elem.get_text(strip=True)
            tag_url = tag_elem.get("href", "")
            if tag_url and not tag_url.startswith("http"):
                tag_url = urljoin(self.base_url, tag_url)
            tag_slug = self.parse_slug_from_url(tag_url)
            tags.append(Tag(name=tag_name, slug=tag_slug, tag_url=tag_url))

        categories: list[Category] = []
        cat_elems = soup.select(".categories a, .video-category a, a[href*='video-category']")
        for cat_elem in cat_elems:
            cat_name = cat_elem.get_text(strip=True)
            cat_url = cat_elem.get("href", "")
            if cat_url and not cat_url.startswith("http"):
                cat_url = urljoin(self.base_url, cat_url)
            cat_slug = self.parse_slug_from_url(cat_url)
            categories.append(Category(name=cat_name, slug=cat_slug, category_url=cat_url))

        related_videos: list[RelatedVideo] = []
        related_section = soup.find(string=re.compile(r"You May Be Interested", re.IGNORECASE))
        if related_section:
            container = related_section.find_parent("div", class_=re.compile(r"related|interest", re.IGNORECASE))
            if not container:
                container = related_section.find_parent()

            if container:
                related_articles = container.select("article, .video-item, .related-video, a[href*='/video/']")
                for idx, article in enumerate(related_articles[:4]):
                    title_elem = article.select_one("a[title], a[href*='/video/']") or article
                    if title_elem.name == "a":
                        rel_title = title_elem.get("title") or title_elem.get_text(strip=True)
                        rel_url = title_elem.get("href", "")
                    else:
                        rel_title = title_elem.get_text(strip=True)[:100]
                        link = title_elem.select_one("a")
                        rel_url = link.get("href", "") if link else ""

                    if rel_url and not rel_url.startswith("http"):
                        rel_url = urljoin(self.base_url, rel_url)

                    if "/video/" in rel_url:
                        rel_slug = self.parse_slug_from_url(rel_url)
                        img = article.select_one("img")
                        rel_thumb = img.get("src") if img else None

                        related_videos.append(RelatedVideo(
                            title=rel_title,
                            slug=rel_slug,
                            video_url=rel_url,
                            thumbnail_url=rel_thumb,
                            position=idx + 1,
                        ))

        video_detail = VideoDetail(
            title=video.title,
            slug=video.slug,
            video_url=video.video_url,
            thumbnail_url=video.thumbnail_url,
            duration=video.duration,
            duration_seconds=video.duration_seconds,
            likes=video.likes,
            views=video.views,
            views_raw=video.views_raw,
            excerpt=video.excerpt,
            description=description,
            author=author,
            author_url=author_url,
            comment_count=comment_count,
            published_at=published_at,
        )

        return DetailPageResult(
            video_detail=video_detail,
            tags=tags,
            related_videos=related_videos,
            extra={"categories": [c.model_dump() for c in categories]},
        )

    def is_404_page(self, html: str) -> bool:
        """Check if the page is a 404 error page."""
        soup = BeautifulSoup(html, "lxml")

        title = soup.select_one("title")
        if title and "404" in title.get_text():
            return True

        body = soup.select_one("body")
        if body and "404" in body.get("class", []):
            return True

        error_elem = soup.select_one(".error-404, .not-found, [class*='error']")
        if error_elem:
            return True

        return False

    def parse_total_pages(self, html: str) -> int | None:
        """Parse total number of pages from pagination."""
        soup = BeautifulSoup(html, "lxml")

        pagination = soup.select_one(".pagination, .nav-links, .page-numbers")
        if pagination:
            page_links = pagination.select("a.page-numbers, a.page-numbers:not(.next):not(.prev)")
            if page_links:
                for link in reversed(page_links):
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        return int(text)

        last_link = soup.select_one("a.last, a[href*='page']:last-of-type")
        if last_link:
            href = last_link.get("href", "")
            match = re.search(r"page/(\d+)", href)
            if match:
                return int(match.group(1))

        return None

    @staticmethod
    def _parse_views(views_str: str | None) -> int:
        """Parse views string to integer."""
        if not views_str:
            return 0

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
```

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/sites/eroasmr/parser.py
git commit -m "refactor: create eroasmr site-specific parser"
```

---

## Task 8: Create Zhumianwang Models

**Files:**
- Create: `src/eroasmr_scraper/sites/zhumianwang/__init__.py`
- Create: `src/eroasmr_scraper/sites/zhumianwang/models.py`

**Step 1: Create sites/zhumianwang/__init__.py**

```python
"""Zhumianwang site implementation."""

from eroasmr_scraper.sites.zhumianwang.models import Video, VideoDetail, Tag, Region, MemberStatus
from eroasmr_scraper.sites.zhumianwang.parser import ZhumianwangParser

__all__ = [
    "Video",
    "VideoDetail",
    "Tag",
    "Region",
    "MemberStatus",
    "ZhumianwangParser",
]
```

**Step 2: Create sites/zhumianwang/models.py**

```python
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
```

**Step 3: Commit**

```bash
git add src/eroasmr_scraper/sites/zhumianwang/__init__.py src/eroasmr_scraper/sites/zhumianwang/models.py
git commit -m "feat: add zhumianwang site models"
```

---

## Task 9: Create Zhumianwang Parser

**Files:**
- Create: `src/eroasmr_scraper/sites/zhumianwang/parser.py`
- Test: `tests/test_zhumianwang_parser.py`

**Step 1: Write test with real HTML sample**

```python
# tests/test_zhumianwang_parser.py
"""Tests for zhumianwang parser with real HTML samples."""

import pytest
from eroasmr_scraper.sites.zhumianwang.parser import ZhumianwangParser
from eroasmr_scraper.sites.zhumianwang.models import Region, MemberStatus


@pytest.fixture
def parser():
    return ZhumianwangParser()


class TestZhumianwangParser:
    def test_parse_duration_hh_mm_ss(self, parser):
        """Parse HH:MM:SS format."""
        assert parser.parse_duration("00:21:55") == 1315

    def test_parse_duration_mm_ss(self, parser):
        """Parse MM:SS format."""
        assert parser.parse_duration("10:21") == 621

    def test_region_detection(self, parser):
        """Region should be detected from URL patterns."""
        # This will be tested with real HTML samples
        pass
```

**Step 2: Create sites/zhumianwang/parser.py**

```python
"""HTML parsing functions for zhumianwang.com."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from eroasmr_scraper.base.parser import BaseSiteParser, ListPageResult, DetailPageResult
from eroasmr_scraper.sites.zhumianwang.models import (
    Video,
    VideoDetail,
    Tag,
    RelatedVideo,
    Region,
    MemberStatus,
)


class ZhumianwangParser(BaseSiteParser):
    """Parser for zhumianwang.com."""

    site_id = "zhumianwang"
    base_url = "https://zhumianwang.com"

    def parse_list_page(self, html: str) -> ListPageResult:
        """Parse video list from list page HTML.

        List page URL: /qbasmr/page/{n}
        """
        soup = BeautifulSoup(html, "lxml")
        videos: list[Video] = []

        # Find video cards in main content area
        video_cards = soup.select("ul > li")

        for card in video_cards:
            # Skip non-video items (like pagination info)
            link = card.select_one("a[href*='/asmr/']")
            if not link:
                continue

            # Title and URL
            title_elem = link
            title = title_elem.get("title") or title_elem.get_text(strip=True)[:200]
            video_url = title_elem.get("href", "")
            if video_url and not video_url.startswith("http"):
                video_url = urljoin(self.base_url, video_url)

            # Skip if not a video URL
            if "/asmr/" not in video_url:
                continue

            slug = self.parse_slug_from_url(video_url)

            # Thumbnail
            img_elem = card.select_one("img")
            thumbnail_url = None
            if img_elem:
                thumbnail_url = img_elem.get("src") or img_elem.get("data-src")
                if thumbnail_url and not thumbnail_url.startswith("http"):
                    thumbnail_url = urljoin(self.base_url, thumbnail_url)

            # Duration (format: HH:MM:SS or MM:SS)
            duration = None
            duration_elems = card.select("span, div")
            for elem in duration_elems:
                text = elem.get_text(strip=True)
                if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", text):
                    duration = text
                    break
            duration_seconds = self.parse_duration(duration)

            # Author
            author_elem = card.select_one("a[href*='/author/'], a[href^='/'][href$='/']")
            author = None
            if author_elem and author_elem != title_elem:
                author = author_elem.get_text(strip=True)
                # Verify it's an author link (short text, not title)
                if len(author) > 30:
                    author = None

            # Try to find author in paragraph after title
            if not author:
                for p in card.select("p"):
                    text = p.get_text(strip=True)
                    if text and len(text) < 30 and not re.match(r"\d{4}-\d{2}-\d{2}", text):
                        author = text
                        break

            # Date
            published_date = None
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", card.get_text())
            if date_match:
                published_date = date_match.group(1)

            # Member status
            member_status = MemberStatus.FREE
            card_text = card.get_text()
            if "会员" in card_text:
                member_status = MemberStatus.MEMBER

            video = Video(
                title=title,
                slug=slug,
                video_url=video_url,
                thumbnail_url=thumbnail_url,
                duration=duration,
                duration_seconds=duration_seconds,
                author=author,
                published_date=published_date,
                member_status=member_status,
            )
            videos.append(video)

        total_pages = self.parse_total_pages(html)
        return ListPageResult(videos=videos, total_pages=total_pages)

    def parse_detail_page(self, html: str, video: Video) -> DetailPageResult:
        """Parse video detail page for extended metadata.

        Detail page URL: /asmr/{id}.html
        """
        soup = BeautifulSoup(html, "lxml")

        # Description
        desc_elem = soup.select_one(".entry-content, .content, .video-desc, article p")
        description = desc_elem.get_text(strip=True) if desc_elem else None

        # Region (中国/韩国/日本/欧美)
        region = Region.UNKNOWN
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            if "/hg" in href or "韩国" in link.get_text():
                region = Region.KOREA
                break
            elif "/rb" in href or "日本" in link.get_text():
                region = Region.JAPAN
                break
            elif "/zg" in href or "中国" in link.get_text():
                region = Region.CHINA
                break
            elif "/om" in href or "欧美" in link.get_text():
                region = Region.WESTERN
                break

        # Year
        year = None
        for link in soup.select("a[href*='y']"):
            href = link.get("href", "")
            match = re.search(r"/(\d{4})y", href)
            if match:
                year = int(match.group(1))
                break

        # Update time
        update_time = None
        time_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", html)
        if time_match:
            update_time = time_match.group(1)

        # Play URL
        play_url = None
        play_elem = soup.select_one("a[href*='v_play']")
        if play_elem:
            play_url = play_elem.get("href")
            if play_url and not play_url.startswith("http"):
                play_url = urljoin(self.base_url, play_url)

        # Tags
        tags: list[Tag] = []
        for tag_elem in soup.select("a[href*='asmr_movie_bt_tags']"):
            tag_name = tag_elem.get_text(strip=True)
            tag_url = tag_elem.get("href", "")
            if tag_url and not tag_url.startswith("http"):
                tag_url = urljoin(self.base_url, tag_url)
            tag_slug = self.parse_slug_from_url(tag_url)
            if tag_name and tag_slug:
                tags.append(Tag(name=tag_name, slug=tag_slug, tag_url=tag_url))

        # Related videos
        related_videos: list[RelatedVideo] = []
        related_section = soup.select_one(".related, .recommend")
        if related_section:
            for idx, item in enumerate(related_section.select("li")):
                link = item.select_one("a[href*='/asmr/']")
                if not link:
                    continue

                rel_title = link.get("title") or link.get_text(strip=True)[:100]
                rel_url = link.get("href", "")
                if rel_url and not rel_url.startswith("http"):
                    rel_url = urljoin(self.base_url, rel_url)

                if "/asmr/" in rel_url:
                    rel_slug = self.parse_slug_from_url(rel_url)
                    img = item.select_one("img")
                    rel_thumb = img.get("src") if img else None

                    # Check member status
                    rel_status = MemberStatus.FREE
                    if "会员" in item.get_text():
                        rel_status = MemberStatus.MEMBER

                    related_videos.append(RelatedVideo(
                        title=rel_title,
                        slug=rel_slug,
                        video_url=rel_url,
                        thumbnail_url=rel_thumb,
                        position=idx + 1,
                        member_status=rel_status,
                    ))

        video_detail = VideoDetail(
            title=video.title,
            slug=video.slug,
            video_url=video.video_url,
            thumbnail_url=video.thumbnail_url,
            duration=video.duration,
            duration_seconds=video.duration_seconds,
            author=video.author,
            published_date=video.published_date,
            member_status=video.member_status,
            description=description,
            region=region,
            year=year,
            update_time=update_time,
            play_url=play_url,
        )

        return DetailPageResult(
            video_detail=video_detail,
            tags=tags,
            related_videos=related_videos[:15],  # Limit to 15 related
        )

    def is_404_page(self, html: str) -> bool:
        """Check if the page is a 404 error page."""
        soup = BeautifulSoup(html, "lxml")

        title = soup.select_one("title")
        if title and "404" in title.get_text():
            return True

        error_elem = soup.select_one(".error-404, .not-found, [class*='error']")
        if error_elem:
            return True

        return False

    def parse_total_pages(self, html: str) -> int | None:
        """Parse total number of pages from pagination.

        Expected: 642 total pages
        """
        soup = BeautifulSoup(html, "lxml")

        # Try to find last page link
        for link in soup.select("a[href*='/page/']"):
            text = link.get_text(strip=True)
            if text == "»":
                href = link.get("href", "")
                match = re.search(r"/page/(\d+)", href)
                if match:
                    return int(match.group(1))

        # Try numbered pagination
        pagination = soup.select_one(".pagination, .page-nav, .pages")
        if pagination:
            page_links = pagination.select("a")
            if page_links:
                for link in reversed(page_links):
                    text = link.get_text(strip=True)
                    if text.isdigit():
                        return int(text)

        return None
```

**Step 3: Run tests**

Run: `pytest tests/test_zhumianwang_parser.py -v`

**Step 4: Commit**

```bash
git add src/eroasmr_scraper/sites/zhumianwang/parser.py tests/test_zhumianwang_parser.py
git commit -m "feat: add zhumianwang parser for list and detail pages"
```

---

## Task 10: Create Play Parser for Download Links

**Files:**
- Create: `src/eroasmr_scraper/sites/zhumianwang/play_parser.py`
- Test: `tests/test_play_parser.py`

**Step 1: Create play_parser.py**

```python
"""Parser for zhumianwang.com play pages (download links)."""

import re
from bs4 import BeautifulSoup

from eroasmr_scraper.sites.zhumianwang.models import VideoDetail


class PlayPageResult:
    """Result of parsing a play page."""

    def __init__(
        self,
        video_download_url: str | None = None,
        audio_download_url: str | None = None,
    ):
        self.video_download_url = video_download_url
        self.audio_download_url = audio_download_url


class ZhumianwangPlayParser:
    """Parser for zhumianwang.com play pages (requires login)."""

    def parse_play_page(self, html: str) -> PlayPageResult:
        """Parse play page for download links.

        The download links are buttons that open new tabs with the actual
        download URLs like:
        https://video.zklhy.com/sv/{id}/{id}.mp4?auth_key=...

        Args:
            html: HTML content of play page (must be logged in)

        Returns:
            PlayPageResult with download URLs
        """
        soup = BeautifulSoup(html, "lxml")

        video_download_url = None
        audio_download_url = None

        # Find download buttons by text
        for elem in soup.find_all(string=re.compile(r"视频下载|下载")):
            parent = elem.parent
            if parent and parent.name == "a":
                href = parent.get("href", "")
                if href and "video.zklhy.com" in href:
                    video_download_url = href
                    break
            # Check if it's a clickable div/button
            for sibling in elem.parent.find_next_siblings():
                if sibling.name == "a" and sibling.get("href", "").startswith("http"):
                    video_download_url = sibling.get("href")
                    break

        # Alternative: look for links in new tab format
        if not video_download_url:
            for link in soup.select("a[href*='video.zklhy.com']"):
                href = link.get("href", "")
                if ".mp4" in href:
                    video_download_url = href
                    break

        # Audio download
        for elem in soup.find_all(string=re.compile(r"音频下载")):
            parent = elem.parent
            if parent and parent.name == "a":
                href = parent.get("href", "")
                if href and ("audio" in href or ".mp3" in href):
                    audio_download_url = href
                    break

        return PlayPageResult(
            video_download_url=video_download_url,
            audio_download_url=audio_download_url,
        )

    def is_free_video(self, html: str) -> bool:
        """Check if video is free (not member-only)."""
        soup = BeautifulSoup(html, "lxml")

        # Look for "免费" badge or text
        if "免费" in html:
            return True

        # Look for member-only indicators
        if "会员可看" in html or "仅能听音频" in html:
            return False

        return True

    def extract_video_id_from_play_url(self, play_url: str) -> str | None:
        """Extract video ID from play URL.

        Play URL format: /v_play/bXZfNDI4MTMtbm1fMQ==.html
        The ID is base64 encoded.
        """
        match = re.search(r"/v_play/([^/]+)\.html", play_url)
        if match:
            return match.group(1)
        return None
```

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/sites/zhumianwang/play_parser.py
git commit -m "feat: add play page parser for download links"
```

---

## Task 11: Create Authentication Module

**Files:**
- Create: `src/eroasmr_scraper/auth/__init__.py`
- Create: `src/eroasmr_scraper/auth/playwright_auth.py`

**Step 1: Create auth/__init__.py**

```python
"""Authentication utilities."""

from eroasmr_scraper.auth.playwright_auth import PlaywrightAuth

__all__ = ["PlaywrightAuth"]
```

**Step 2: Create auth/playwright_auth.py**

```python
"""Playwright-based cookie authentication."""

import json
import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class CookieData(BaseModel):
    """Cookie data structure."""
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    http_only: bool = False


class PlaywrightAuth:
    """Manage authentication via Playwright browser cookies."""

    def __init__(self, cookie_file: str = "data/cookies.json"):
        """Initialize auth manager.

        Args:
            cookie_file: Path to save/load cookies
        """
        self.cookie_file = Path(cookie_file)
        self._cookies: list[dict] = []

    def load_cookies(self, site_id: str) -> list[dict]:
        """Load cookies from file for a specific site.

        Args:
            site_id: Site identifier (e.g., 'zhumianwang')

        Returns:
            List of cookie dictionaries
        """
        if not self.cookie_file.exists():
            return []

        with open(self.cookie_file, "r") as f:
            data = json.load(f)

        return data.get(site_id, [])

    def save_cookies(self, site_id: str, cookies: list[dict]) -> None:
        """Save cookies to file for a specific site.

        Args:
            site_id: Site identifier
            cookies: List of cookie dictionaries from Playwright
        """
        # Ensure directory exists
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data
        data = {}
        if self.cookie_file.exists():
            with open(self.cookie_file, "r") as f:
                data = json.load(f)

        # Update cookies for site
        data[site_id] = cookies

        # Save
        with open(self.cookie_file, "w") as f:
            json.dump(data, f, indent=2)

    def cookies_to_header(self, cookies: list[dict]) -> str:
        """Convert cookies to HTTP Cookie header format.

        Args:
            cookies: List of cookie dictionaries

        Returns:
            Cookie header string
        """
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def cookies_to_httpx_format(self, cookies: list[dict]) -> dict[str, str]:
        """Convert cookies to httpx format.

        Args:
            cookies: List of cookie dictionaries

        Returns:
            Dictionary of cookie name -> value
        """
        return {c["name"]: c["value"] for c in cookies}

    async def extract_cookies_from_browser(
        self,
        browser_context: Any,
        domain: str,
    ) -> list[dict]:
        """Extract cookies from a Playwright browser context.

        Args:
            browser_context: Playwright BrowserContext
            domain: Domain to filter cookies (e.g., '.zhumianwang.com')

        Returns:
            List of cookie dictionaries
        """
        cookies = await browser_context.cookies()

        # Filter by domain
        filtered = [
            c for c in cookies
            if domain in c.get("domain", "")
        ]

        return filtered

    def has_valid_cookies(self, site_id: str) -> bool:
        """Check if valid cookies exist for a site.

        Args:
            site_id: Site identifier

        Returns:
            True if cookies file has cookies for this site
        """
        cookies = self.load_cookies(site_id)
        return len(cookies) > 0
```

**Step 3: Commit**

```bash
git add src/eroasmr_scraper/auth/__init__.py src/eroasmr_scraper/auth/playwright_auth.py
git commit -m "feat: add Playwright authentication module"
```

---

## Task 12: Update Storage for Multi-Site

**Files:**
- Modify: `src/eroasmr_scraper/storage.py`

**Step 1: Add site_id parameter to VideoStorage**

Key changes to `storage.py`:
1. Add `site_id` parameter to `__init__`
2. Add `site_id` column to videos table
3. Filter all queries by `site_id`

This is a modification task - read the existing file first and add the changes.

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/storage.py
git commit -m "feat: add site_id support to storage"
```

---

## Task 13: Update Config for Multi-Site

**Files:**
- Modify: `src/eroasmr_scraper/config.py`

**Step 1: Add multi-site configuration**

Key changes:
1. Add `ZhumianwangSiteConfig` class
2. Add `SitesConfig` with eroasmr and zhumianwang
3. Change env prefix to `SCRAPER_` (with backward compat)
4. Add `default_site` setting

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/config.py
git commit -m "feat: add multi-site configuration"
```

---

## Task 14: Update CLI for Multi-Site

**Files:**
- Modify: `src/eroasmr_scraper/cli.py`

**Step 1: Add --site parameter to commands**

Key changes:
1. Add `SiteChoice` type with `--site/-s` option
2. Add `sites` command to list available sites
3. Add `login` command for cookie-based auth
4. Update all commands to use `--site` parameter

**Step 2: Commit**

```bash
git add src/eroasmr_scraper/cli.py
git commit -m "feat: add --site parameter to CLI commands"
```

---

## Task 15: Add Re-exports for Backward Compatibility

**Files:**
- Modify: `src/eroasmr_scraper/models.py`
- Modify: `src/eroasmr_scraper/parser.py`
- Modify: `src/eroasmr_scraper/scraper.py`

**Step 1: Update models.py to re-export from sites/eroasmr**

```python
"""Video metadata models (backward compatibility)."""

from eroasmr_scraper.sites.eroasmr.models import (
    Video,
    VideoDetail,
    Tag,
    Category,
    RelatedVideo,
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
```

**Step 2: Update parser.py**

```python
"""HTML parsing functions (backward compatibility)."""

from eroasmr_scraper.sites.eroasmr.parser import (
    EroAsmrParser,
    parse_duration,
    parse_views,
    parse_slug_from_url,
    parse_list_page,
    parse_detail_page,
    parse_total_pages,
    is_404_page,
    parse_video_source,
)

__all__ = [
    "EroAsmrParser",
    "parse_duration",
    "parse_views",
    "parse_slug_from_url",
    "parse_list_page",
    "parse_detail_page",
    "parse_total_pages",
    "is_404_page",
    "parse_video_source",
]
```

**Step 3: Commit**

```bash
git add src/eroasmr_scraper/models.py src/eroasmr_scraper/parser.py
git commit -m "refactor: add backward-compatible re-exports"
```

---

## Task 16: Integration Test

**Files:**
- Test: `tests/test_zhumianwang_integration.py`

**Step 1: Write integration test**

```python
# tests/test_zhumianwang_integration.py
"""Integration tests for zhumianwang scraper."""

import pytest
import httpx
from eroasmr_scraper.sites.zhumianwang.parser import ZhumianwangParser
from eroasmr_scraper.sites.zhumianwang.models import Region, MemberStatus


@pytest.fixture
def parser():
    return ZhumianwangParser()


@pytest.fixture
def real_list_html():
    """Fetch real list page HTML."""
    resp = httpx.get("https://zhumianwang.com/qbasmr/", timeout=30)
    return resp.text


class TestZhumianwangIntegration:
    @pytest.mark.integration
    def test_parse_real_list_page(self, parser, real_list_html):
        """Parse real list page and verify structure."""
        result = parser.parse_list_page(real_list_html)

        assert len(result.videos) > 0, "Should find videos on list page"

        # Check first video has required fields
        video = result.videos[0]
        assert video.title, "Video should have title"
        assert video.slug, "Video should have slug"
        assert video.video_url, "Video should have URL"
        assert "/asmr/" in video.video_url, "URL should be video page"

    @pytest.mark.integration
    def test_parse_total_pages(self, parser, real_list_html):
        """Parse total pages from real page."""
        total = parser.parse_total_pages(real_list_html)
        assert total is not None, "Should find total pages"
        assert total > 600, f"Expected 600+ pages, got {total}"
```

**Step 2: Run integration test**

Run: `pytest tests/test_zhumianwang_integration.py -v -m integration`

**Step 3: Commit**

```bash
git add tests/test_zhumianwang_integration.py
git commit -m "test: add zhumianwang integration tests"
```

---

## Execution Options

Plan complete and saved to `docs/plans/2026-02-19-zhumianwang-multi-site.md`.

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
