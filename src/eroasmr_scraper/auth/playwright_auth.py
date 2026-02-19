"""Playwright-based cookie authentication."""

import json
from pathlib import Path
from typing import Any


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
