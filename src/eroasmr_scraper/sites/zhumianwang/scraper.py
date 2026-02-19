"""Async scraper for zhumianwang.com."""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import httpx

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import FailedUrl, ScrapeProgress
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.sites.zhumianwang.parser import ZhumianwangParser
from eroasmr_scraper.sites.zhumianwang.play_parser import ZhumianwangPlayParser
from eroasmr_scraper.sites.zhumianwang.models import Video, VideoDetail, Tag, RelatedVideo

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base scraper exception."""

    pass


class RateLimitError(ScraperError):
    """Rate limit exceeded."""

    pass


class ZhumianwangScraper:
    """Async scraper for zhumianwang.com video metadata.

    Three-phase scraping:
    1. List pages - basic video info (no auth needed)
    2. Detail pages - full metadata (no auth needed)
    3. Play pages - download links (requires login cookies)
    """

    site_id = "zhumianwang"

    def __init__(self, storage: VideoStorage | None = None):
        """Initialize scraper.

        Args:
            storage: VideoStorage instance. Created if not provided.
        """
        self.storage = storage or VideoStorage(site_id=self.site_id)
        self.settings = settings
        self.parser = ZhumianwangParser()
        self.play_parser = ZhumianwangPlayParser()
        self._total_pages: int | None = None
        self._cookies: dict[str, str] | None = None

    def _get_site_config(self):
        """Get site-specific configuration."""
        return settings.sites.zhumianwang

    def _get_client(self, with_cookies: bool = False) -> httpx.AsyncClient:
        """Create configured HTTP client.

        Args:
            with_cookies: If True, load cookies for authenticated requests

        Returns:
            Configured AsyncClient
        """
        site_config = self._get_site_config()

        limits = httpx.Limits(
            max_connections=self.settings.http.max_connections,
            max_keepalive_connections=self.settings.http.max_keepalive,
        )

        timeout = httpx.Timeout(
            connect=self.settings.http.timeout_connect,
            read=self.settings.http.timeout_read,
            write=self.settings.http.timeout_write,
            pool=self.settings.http.timeout_pool,
        )

        headers = {
            "User-Agent": self.settings.http.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": site_config.base_url,
        }

        cookies = None
        if with_cookies:
            cookies = self._load_cookies()

        return httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers=headers,
            cookies=cookies,
            follow_redirects=True,
        )

    def _load_cookies(self) -> dict[str, str]:
        """Load cookies from file for authenticated requests."""
        if self._cookies is not None:
            return self._cookies

        cookie_file = Path("data/cookies.json")
        if not cookie_file.exists():
            logger.warning("Cookie file not found: %s", cookie_file)
            return {}

        try:
            with open(cookie_file) as f:
                cookie_list = json.load(f)

            # Convert to dict format for httpx
            self._cookies = {c["name"]: c["value"] for c in cookie_list}
            logger.info("Loaded %d cookies from %s", len(self._cookies), cookie_file)
            return self._cookies
        except Exception as e:
            logger.error("Failed to load cookies: %s", e)
            return {}

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
        """Fetch URL with exponential backoff retry.

        Args:
            client: HTTP client
            url: URL to fetch
            max_retries: Maximum retries (default from settings)

        Returns:
            HTML content

        Raises:
            ScraperError: If all retries fail
        """
        max_retries = max_retries or self.settings.http.max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                await self._delay()
                response = await client.get(url)
                response.raise_for_status()
                return response.text

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited
                    wait_time = 2**attempt * 5  # 5, 10, 20 seconds
                    logger.warning("Rate limited, waiting %ds", wait_time)
                    await asyncio.sleep(wait_time)
                    last_error = RateLimitError(f"Rate limited: {url}")
                elif e.response.status_code >= 500:
                    # Server error, retry
                    wait_time = 2**attempt
                    logger.warning(
                        "Server error %d, retry %d/%d: %s",
                        e.response.status_code,
                        attempt + 1,
                        max_retries,
                        url,
                    )
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    # Client error, don't retry
                    raise ScraperError(f"HTTP {e.response.status_code}: {url}") from e

            except httpx.RequestError as e:
                wait_time = 2**attempt
                logger.warning(
                    "Request error, retry %d/%d: %s - %s",
                    attempt + 1,
                    max_retries,
                    url,
                    e,
                )
                await asyncio.sleep(wait_time)
                last_error = e

        raise ScraperError(f"Failed after {max_retries} retries: {url}") from last_error

    def _build_list_url(self, page: int) -> str:
        """Build list page URL.

        Args:
            page: Page number

        Returns:
            Full URL
        """
        base_url = self._get_site_config().base_url
        if page == 1:
            return f"{base_url}/qbasmr/"
        return f"{base_url}/qbasmr/page/{page}/"

    async def detect_total_pages(self, client: httpx.AsyncClient) -> int:
        """Detect total number of pages.

        Args:
            client: HTTP client

        Returns:
            Total number of pages
        """
        if self._total_pages is not None:
            return self._total_pages

        # Fetch first page
        url = self._build_list_url(1)
        html = await self._fetch_with_retry(client, url)
        total = self.parser.parse_total_pages(html)

        if total is None:
            # Default estimate based on known site size
            logger.warning("Could not detect total pages, using default 642")
            total = 642

        self._total_pages = total
        logger.info("Detected %d total pages", total)
        return total

    async def scrape_list_page(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[dict]:
        """Scrape single list page.

        Args:
            client: HTTP client
            page: Page number

        Returns:
            List of video dicts
        """
        url = self._build_list_url(page)
        logger.debug("Fetching list page %d: %s", page, url)

        html = await self._fetch_with_retry(client, url)

        if self.parser.is_404_page(html):
            logger.warning("Page %d returned 404", page)
            return []

        result = self.parser.parse_list_page(html)
        videos = result.videos
        logger.info("Parsed %d videos from page %d", len(videos), page)

        # Validate parsed data and log warnings for missing fields
        for v in videos:
            if v.duration is None:
                logger.warning("Missing duration: %s", v.slug)

        return [v.model_dump() for v in videos]

    async def scrape_detail_page(
        self,
        client: httpx.AsyncClient,
        video: dict,
    ) -> dict | None:
        """Scrape video detail page for full metadata.

        Args:
            client: HTTP client
            video: Basic video dict from list page

        Returns:
            Extended video dict with details, or None if failed
        """
        url = video["video_url"]
        logger.debug("Fetching detail page: %s", url)

        try:
            html = await self._fetch_with_retry(client, url)

            if self.parser.is_404_page(html):
                logger.warning("Video detail not found: %s", url)
                return None

            # Create Video object for parsing
            video_obj = Video(**video)
            result = self.parser.parse_detail_page(html, video_obj)

            detail = result.video_detail

            result_dict = detail.model_dump()
            result_dict["_tags"] = [t.model_dump() for t in result.tags]
            result_dict["_related"] = [r.model_dump() for r in result.related_videos]

            return result_dict

        except ScraperError as e:
            logger.error("Failed to scrape detail %s: %s", url, e)
            self.storage.add_failed_url(FailedUrl(
                url=url,
                url_type="detail",
                error=str(e),
                site_id=self.site_id,
            ))
            return None

    async def scrape_play_page(
        self,
        client: httpx.AsyncClient,
        play_url: str,
        video_slug: str,
    ) -> tuple[str | None, str | None]:
        """Scrape play page for download links.

        Args:
            client: HTTP client (with cookies)
            play_url: Play page URL
            video_slug: Video slug for logging

        Returns:
            Tuple of (video_download_url, audio_download_url)
        """
        if not play_url:
            return None, None

        logger.debug("Fetching play page for %s: %s", video_slug, play_url)

        try:
            html = await self._fetch_with_retry(client, play_url)
            result = self.play_parser.parse_play_page(html)

            if result.video_download_url:
                logger.info("Found download URL for %s", video_slug)
            else:
                logger.warning("No download URL found for %s", video_slug)

            return result.video_download_url, result.audio_download_url

        except ScraperError as e:
            logger.error("Failed to scrape play page %s: %s", play_url, e)
            self.storage.add_failed_url(FailedUrl(
                url=play_url,
                url_type="play",
                error=str(e),
                site_id=self.site_id,
            ))
            return None, None

    async def scrape_full(
        self,
        start_page: int = 1,
        end_page: int | None = None,
        reverse: bool = False,
        with_details: bool = True,
        with_downloads: bool = False,
    ) -> AsyncIterator[dict]:
        """Full scrape mode - scrape all pages.

        Args:
            start_page: Starting page number
            end_page: Ending page number (auto-detect if None)
            reverse: If True, scrape from last page to first (oldest to newest)
            with_details: If True, also scrape detail pages
            with_downloads: If True, also scrape play pages for download links (requires auth)

        Yields:
            Progress updates
        """
        async with self._get_client() as client:
            # Detect total pages
            total_pages = await self.detect_total_pages(client)

            # Determine page range
            if end_page is None:
                end_page = total_pages

            if reverse:
                # Scrape from oldest to newest
                pages = range(end_page, start_page - 1, -1)
                logger.info("Starting full scrape (reverse): pages %d to %d", end_page, start_page)
            else:
                # Scrape from newest to oldest
                pages = range(start_page, end_page + 1)
                logger.info("Starting full scrape: pages %d to %d", start_page, end_page)

            # Save initial progress
            progress = ScrapeProgress(
                mode="full",
                phase="list",
                last_page=start_page if not reverse else end_page,
                total_pages=total_pages,
                site_id=self.site_id,
            )
            self.storage.save_progress(progress)

            total_videos = 0
            total_new = 0

            # Phase 1: List pages
            for page_num in pages:
                videos = await self.scrape_list_page(client, page_num)

                if not videos:
                    logger.warning("No videos found on page %d", page_num)
                    continue

                # Check for new videos (for incremental logic)
                new_videos = []
                for v in videos:
                    if not self.storage.video_exists(v["slug"]):
                        new_videos.append(v)

                # Save videos
                video_objs = [Video(**v) for v in videos]
                self.storage.upsert_videos(video_objs)

                total_videos += len(videos)
                total_new += len(new_videos)

                # Update progress
                progress.last_page = page_num
                progress.last_video_id = total_videos
                self.storage.save_progress(progress)

                yield {
                    "type": "page",
                    "page": page_num,
                    "total_pages": total_pages,
                    "videos_found": len(videos),
                    "new_videos": len(new_videos),
                    "total_videos": total_videos,
                    "total_new": total_new,
                }

            # Phase 2: Detail pages
            if with_details:
                progress.phase = "detail"
                self.storage.save_progress(progress)

                videos_without_details = self.storage.get_videos_without_details(
                    limit=10000  # Large limit to get all
                )

                detail_count = 0
                for video in videos_without_details:
                    detail = await self.scrape_detail_page(client, video)

                    if detail:
                        # Save video detail
                        detail_obj = VideoDetail(**{k: v for k, v in detail.items() if not k.startswith("_")})
                        self.storage.upsert_video_detail(detail_obj)

                        # Save tags
                        for tag in detail.get("_tags", []):
                            tag_obj = Tag(**tag)
                            self.storage.upsert_tag(tag_obj)
                            self.storage.add_video_tag(video["slug"], tag["slug"])

                        # Save related videos
                        for rel in detail.get("_related", []):
                            rel_obj = RelatedVideo(**rel)
                            self.storage.add_related_video(video["slug"], rel_obj)

                        detail_count += 1

                    if detail_count % self.settings.scraper.save_interval == 0:
                        yield {
                            "type": "detail_progress",
                            "details_scraped": detail_count,
                            "total_details": len(videos_without_details),
                        }

                # Phase 3: Play pages for download links
                if with_downloads:
                    progress.phase = "download"
                    self.storage.save_progress(progress)

                    # Get videos with play_url but no download_url
                    videos_for_download = list(self.storage.db["videos"].rows_where(
                        "play_url IS NOT NULL AND download_url IS NULL AND site_id = ?",
                        [self.site_id]
                    ))

                    if videos_for_download:
                        logger.info("Scraping %d play pages for download links", len(videos_for_download))
                        async with self._get_client(with_cookies=True) as auth_client:
                            download_count = 0
                            for video in videos_for_download:
                                video_url, audio_url = await self.scrape_play_page(
                                    auth_client,
                                    video["play_url"],
                                    video["slug"],
                                )

                                if video_url or audio_url:
                                    # Update video with download URLs using raw SQL with commit
                                    with self.storage.db.conn:
                                        self.storage.db.conn.execute(
                                            """
                                            UPDATE videos SET
                                                download_url = ?,
                                                audio_download_url = ?,
                                                updated_at = ?
                                            WHERE slug = ?
                                            """,
                                            [
                                                video_url,
                                                audio_url,
                                                datetime.now().isoformat(),
                                                video["slug"],
                                            ],
                                        )
                                    download_count += 1

                                if download_count % self.settings.scraper.save_interval == 0:
                                    yield {
                                        "type": "download_progress",
                                        "downloads_scraped": download_count,
                                        "total_downloads": len(videos_for_download),
                                    }

                yield {
                    "type": "complete",
                    "total_videos": total_videos,
                    "total_details": detail_count,
                }
            else:
                yield {
                    "type": "complete",
                    "total_videos": total_videos,
                    "total_details": 0,
                }

    async def scrape_incremental(
        self,
        with_details: bool = True,
        reverse: bool = False,
    ) -> AsyncIterator[dict]:
        """Incremental update - scrape only new videos.

        Stops when encountering an existing video (if not reverse).
        For reverse mode, scrapes from oldest unchecked page.

        Args:
            with_details: If True, also scrape detail pages
            reverse: If True, continue from last checked position

        Yields:
            Progress updates
        """
        async with self._get_client() as client:
            total_pages = await self.detect_total_pages(client)

            # Get previous progress
            progress = self.storage.get_progress()

            if reverse and progress:
                # Continue from last position (for oldest-first scraping)
                start_page = progress.last_page
                pages = range(start_page, 0, -1)  # Go towards page 1
                logger.info("Starting incremental scrape (reverse): from page %d", start_page)
            else:
                # Start from page 1 (newest)
                start_page = 1
                pages = range(1, total_pages + 1)
                logger.info("Starting incremental scrape from newest")

            # Save initial progress
            progress = ScrapeProgress(
                mode="incremental",
                phase="list",
                last_page=start_page,
                total_pages=total_pages,
                site_id=self.site_id,
            )
            self.storage.save_progress(progress)

            total_new = 0
            stop_reason: str | None = None

            for page_num in pages:
                videos = await self.scrape_list_page(client, page_num)

                if not videos:
                    continue

                # Check for existing videos
                new_videos = []
                found_existing = False
                for v in videos:
                    if self.storage.video_exists(v["slug"]):
                        found_existing = True
                        logger.debug("Found existing video %s", v["slug"])
                    else:
                        new_videos.append(v)

                # Save new videos if any were found
                if new_videos:
                    video_objs = [Video(**v) for v in new_videos]
                    self.storage.upsert_videos(video_objs)
                    total_new += len(new_videos)

                    # Update progress
                    progress.last_page = page_num
                    self.storage.save_progress(progress)

                    yield {
                        "type": "page",
                        "page": page_num,
                        "new_videos": len(new_videos),
                        "total_new": total_new,
                    }

                # Stop if we found existing videos (we've reached old content)
                if found_existing and not reverse:
                    logger.info(
                        "Found existing videos, stopping after page %d (collected %d new)",
                        page_num,
                        len(new_videos),
                    )
                    stop_reason = "found_existing"
                    break

                if not new_videos and not reverse:
                    stop_reason = "all_exist"
                    break

            # Phase 2: Detail pages for videos without details
            if with_details:
                progress.phase = "detail"
                self.storage.save_progress(progress)

                videos_without_details = self.storage.get_videos_without_details()

                detail_count = 0
                for video in videos_without_details:
                    detail = await self.scrape_detail_page(client, video)

                    if detail:
                        detail_obj = VideoDetail(**{k: v for k, v in detail.items() if not k.startswith("_")})
                        self.storage.upsert_video_detail(detail_obj)

                        # Save relationships
                        for tag in detail.get("_tags", []):
                            tag_obj = Tag(**tag)
                            self.storage.upsert_tag(tag_obj)
                            self.storage.add_video_tag(video["slug"], tag["slug"])

                        for rel in detail.get("_related", []):
                            rel_obj = RelatedVideo(**rel)
                            self.storage.add_related_video(video["slug"], rel_obj)

                        detail_count += 1

                yield {
                    "type": "complete",
                    "total_new": total_new,
                    "total_details": detail_count,
                    "stop_reason": stop_reason,
                }
            else:
                yield {
                    "type": "complete",
                    "total_new": total_new,
                    "total_details": 0,
                    "stop_reason": stop_reason,
                }
