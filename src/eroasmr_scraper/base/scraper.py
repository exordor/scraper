"""Abstract scraper protocol for site-specific scrapers."""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any

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
