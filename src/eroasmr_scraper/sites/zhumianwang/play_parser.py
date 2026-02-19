"""Parser for zhumianwang.com play pages (download links)."""

import re
from bs4 import BeautifulSoup


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
