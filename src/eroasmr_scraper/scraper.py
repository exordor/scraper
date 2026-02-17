"""Core async scraping logic."""

import asyncio
import logging
import random
from typing import AsyncIterator

import httpx

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import FailedUrl, ScrapeProgress
from eroasmr_scraper.parser import (
    is_404_page,
    parse_detail_page,
    parse_list_page,
    parse_total_pages,
)
from eroasmr_scraper.storage import VideoStorage

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base scraper exception."""

    pass


class RateLimitError(ScraperError):
    """Rate limit exceeded."""

    pass


class EroAsmrScraper:
    """Async scraper for eroasmr.com video metadata."""

    def __init__(self, storage: VideoStorage | None = None):
        """Initialize scraper.

        Args:
            storage: VideoStorage instance. Created if not provided.
        """
        self.storage = storage or VideoStorage()
        self.settings = settings
        self._total_pages: int | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Create configured HTTP client.

        Returns:
            Configured AsyncClient
        """
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
            "Accept-Language": "en-US,en;q=0.5",
        }

        return httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        )

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
        if page == 1:
            return f"{self.settings.http.base_url}/new-videos/"
        return f"{self.settings.http.base_url}/new-videos/page/{page}/"

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
        total = parse_total_pages(html)

        if total is None:
            # Default estimate
            logger.warning("Could not detect total pages, using default 198")
            total = 198

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

        if is_404_page(html):
            logger.warning("Page %d returned 404", page)
            return []

        videos = parse_list_page(html, self.settings.http.base_url)
        logger.info("Parsed %d videos from page %d", len(videos), page)

        # Validate parsed data and log warnings for missing fields
        for v in videos:
            if v.duration is None:
                logger.warning("Missing duration: %s", v.slug)
            if v.duration_seconds is None:
                logger.warning("Missing duration_seconds: %s", v.slug)
            if v.views == 0:
                logger.warning("Missing views: %s", v.slug)

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

            if is_404_page(html):
                logger.warning("Video detail not found: %s", url)
                return None

            # Create Video object for parsing
            from eroasmr_scraper.models import Video

            video_obj = Video(**video)
            detail, tags, categories, related = parse_detail_page(
                html, video_obj, self.settings.http.base_url
            )

            result = detail.model_dump()
            result["_tags"] = [t.model_dump() for t in tags]
            result["_categories"] = [c.model_dump() for c in categories]
            result["_related"] = [r.model_dump() for r in related]

            return result

        except ScraperError as e:
            logger.error("Failed to scrape detail %s: %s", url, e)
            self.storage.add_failed_url(FailedUrl(
                url=url,
                url_type="detail",
                error=str(e),
            ))
            return None

    async def scrape_full(
        self,
        start_page: int = 1,
        end_page: int | None = None,
        reverse: bool = False,
        with_details: bool = True,
    ) -> AsyncIterator[dict]:
        """Full scrape mode - scrape all pages.

        Args:
            start_page: Starting page number
            end_page: Ending page number (auto-detect if None)
            reverse: If True, scrape from last page to first (oldest to newest)
            with_details: If True, also scrape detail pages

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
            )
            self.storage.save_progress(progress)

            total_videos = 0
            total_new = 0

            for page_num in pages:
                await self._delay()

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
                from eroasmr_scraper.models import Video

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
                    await self._delay()

                    detail = await self.scrape_detail_page(client, video)

                    if detail:
                        # Save video detail
                        from eroasmr_scraper.models import VideoDetail

                        detail_obj = VideoDetail(**{k: v for k, v in detail.items() if not k.startswith("_")})
                        self.storage.upsert_video_detail(detail_obj)

                        # Save tags
                        for tag in detail.get("_tags", []):
                            from eroasmr_scraper.models import Tag

                            tag_obj = Tag(**tag)
                            self.storage.upsert_tag(tag_obj)
                            self.storage.add_video_tag(video["slug"], tag["slug"])

                        # Save categories
                        for cat in detail.get("_categories", []):
                            from eroasmr_scraper.models import Category

                            cat_obj = Category(**cat)
                            self.storage.upsert_category(cat_obj)
                            self.storage.add_video_category(video["slug"], cat["slug"])

                        # Save related videos
                        for rel in detail.get("_related", []):
                            from eroasmr_scraper.models import RelatedVideo

                            rel_obj = RelatedVideo(**rel)
                            self.storage.add_related_video(video["slug"], rel_obj)

                        detail_count += 1

                    if detail_count % self.settings.scraper.save_interval == 0:
                        yield {
                            "type": "detail_progress",
                            "details_scraped": detail_count,
                            "total_details": len(videos_without_details),
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
            )
            self.storage.save_progress(progress)

            total_new = 0
            stop_reason: str | None = None

            for page_num in pages:
                await self._delay()

                videos = await self.scrape_list_page(client, page_num)

                if not videos:
                    continue

                # Check for existing videos
                # Process ALL videos on the page to handle cases where new videos
                # might be interleaved with existing ones (e.g., pinned content)
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
                    from eroasmr_scraper.models import Video

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
                # This handles the case where page 1 has both new and old videos
                if found_existing and not reverse:
                    logger.info(
                        "Found existing videos, stopping after page %d (collected %d new)",
                        page_num,
                        len(new_videos),
                    )
                    stop_reason = "found_existing"
                    break

                # No existing videos means all content is new, continue to next page
                if not new_videos and not reverse:
                    # Edge case: page had no videos at all
                    stop_reason = "all_exist"
                    break

            # Phase 2: Detail pages for videos without details
            if with_details:
                progress.phase = "detail"
                self.storage.save_progress(progress)

                videos_without_details = self.storage.get_videos_without_details()

                detail_count = 0
                for video in videos_without_details:
                    await self._delay()

                    detail = await self.scrape_detail_page(client, video)

                    if detail:
                        from eroasmr_scraper.models import VideoDetail

                        detail_obj = VideoDetail(**{k: v for k, v in detail.items() if not k.startswith("_")})
                        self.storage.upsert_video_detail(detail_obj)

                        # Save relationships
                        for tag in detail.get("_tags", []):
                            from eroasmr_scraper.models import Tag

                            tag_obj = Tag(**tag)
                            self.storage.upsert_tag(tag_obj)
                            self.storage.add_video_tag(video["slug"], tag["slug"])

                        for cat in detail.get("_categories", []):
                            from eroasmr_scraper.models import Category

                            cat_obj = Category(**cat)
                            self.storage.upsert_category(cat_obj)
                            self.storage.add_video_category(video["slug"], cat["slug"])

                        for rel in detail.get("_related", []):
                            from eroasmr_scraper.models import RelatedVideo

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

    async def retry_failed(self) -> AsyncIterator[dict]:
        """Retry failed URLs.

        Yields:
            Progress updates
        """
        failed_urls = self.storage.get_failed_urls()

        if not failed_urls:
            yield {"type": "complete", "retried": 0, "success": 0}
            return

        async with self._get_client() as client:
            success_count = 0

            for record in failed_urls:
                await self._delay()

                url = record["url"]
                url_type = record["url_type"]

                try:
                    html = await self._fetch_with_retry(client, url)

                    if url_type == "list":
                        videos = parse_list_page(html, self.settings.http.base_url)
                        from eroasmr_scraper.models import Video

                        video_objs = [Video(**v) for v in videos]
                        self.storage.upsert_videos(video_objs)

                    # Success - remove from failed list
                    self.storage.remove_failed_url(url)
                    success_count += 1

                    yield {
                        "type": "retry_success",
                        "url": url,
                    }

                except ScraperError as e:
                    self.storage.increment_retry_count(url)
                    logger.error("Retry failed for %s: %s", url, e)

                    yield {
                        "type": "retry_failed",
                        "url": url,
                        "error": str(e),
                    }

            yield {
                "type": "complete",
                "retried": len(failed_urls),
                "success": success_count,
            }

    async def refresh_durations(
        self,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> AsyncIterator[dict]:
        """Refresh duration values for all existing videos.

        Re-scrapes list pages and updates duration fields.

        Args:
            start_page: Starting page number
            end_page: Ending page number (auto-detect if None)

        Yields:
            Progress updates
        """
        from eroasmr_scraper.models import Video

        async with self._get_client() as client:
            # Detect total pages
            total_pages = await self.detect_total_pages(client)

            if end_page is None:
                end_page = total_pages

            logger.info(
                "Starting duration refresh: pages %d to %d",
                start_page,
                end_page,
            )

            total_processed = 0

            for page_num in range(start_page, end_page + 1):
                await self._delay()

                videos = await self.scrape_list_page(client, page_num)

                if not videos:
                    logger.warning("No videos found on page %d", page_num)
                    continue

                # Upsert videos with update_existing=True to update duration
                video_objs = [Video(**v) for v in videos]
                self.storage.upsert_videos(video_objs, update_existing=True)

                total_processed += len(videos)

                yield {
                    "type": "page",
                    "page": page_num,
                    "total_pages": total_pages,
                    "videos_processed": len(videos),
                    "total_processed": total_processed,
                }

            yield {
                "type": "complete",
                "total_processed": total_processed,
            }
