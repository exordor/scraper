"""Parser for zhumianwang.com play pages (download links)."""

import base64
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup


@dataclass
class PlayPageResult:
    """Result of parsing a play page."""

    video_download_url: str | None = None
    audio_download_url: str | None = None


class ZhumianwangPlayParser:
    """Parser for zhumianwang.com play pages (requires login).

    The play page contains download URLs encoded in JavaScript variables:
    - var vvvvvv = "base64_encoded_video_url"
    - var vvvvvvv = "base64_encoded_audio_url"

    These need to be decoded using base64 to get the actual URLs like:
    https://video.zklhy.com/sv/{id}/{id}.mp4?auth_key=...
    """

    def parse_play_page(self, html: str) -> PlayPageResult:
        """Parse play page for download links.

        Args:
            html: HTML content of play page (must be logged in)

        Returns:
            PlayPageResult with download URLs
        """
        video_download_url = None
        audio_download_url = None

        # Method 1: Extract from JavaScript variables (primary method)
        # Pattern: var vvvvvv = "base64_string" (6 v's for video)
        video_match = re.search(r'var\s+vvvvvv\s*=\s*["\']([^"\']+)["\']', html)
        if video_match:
            base64_video = video_match.group(1)
            video_download_url = self._decode_base64_url(base64_video)

        # Pattern: var vvvvvvv = "base64_string" (7 v's for audio)
        audio_match = re.search(r'var\s+vvvvvvv\s*=\s*["\']([^"\']+)["\']', html)
        if audio_match:
            base64_audio = audio_match.group(1)
            audio_download_url = self._decode_base64_url(base64_audio)

        # Method 2: Fallback - look for direct links in href attributes
        if not video_download_url:
            soup = BeautifulSoup(html, "lxml")
            for link in soup.select("a[href*='video.zklhy.com']"):
                href = link.get("href", "")
                if ".mp4" in href:
                    video_download_url = href
                    break

        # Method 3: Fallback - look for download buttons by text
        if not video_download_url:
            soup = BeautifulSoup(html, "lxml")
            for elem in soup.find_all(string=re.compile(r"视频下载")):
                parent = elem.parent
                # Check parent and ancestors for links
                for ancestor in [parent] + list(parent.parents)[:3]:
                    if ancestor and ancestor.name == "a":
                        href = ancestor.get("href", "")
                        if href and href.startswith("http"):
                            video_download_url = href
                            break
                        # Check onclick for base64 URL
                        onclick = ancestor.get("onclick", "")
                        url_match = re.search(r"['\"](https?://[^'\"]+)['\"]", onclick)
                        if url_match:
                            video_download_url = url_match.group(1)
                            break

        # Audio download fallback
        if not audio_download_url:
            soup = BeautifulSoup(html, "lxml")
            for elem in soup.find_all(string=re.compile(r"音频下载")):
                parent = elem.parent
                for ancestor in [parent] + list(parent.parents)[:3]:
                    if ancestor and ancestor.name == "a":
                        href = ancestor.get("href", "")
                        if href and href.startswith("http"):
                            audio_download_url = href
                            break

        return PlayPageResult(
            video_download_url=video_download_url,
            audio_download_url=audio_download_url,
        )

    def _decode_base64_url(self, base64_str: str) -> str | None:
        """Decode a base64 encoded URL.

        Args:
            base64_str: Base64 encoded URL string

        Returns:
            Decoded URL or None if decoding fails
        """
        try:
            # Add padding if needed
            padding = 4 - len(base64_str) % 4
            if padding != 4:
                base64_str += "=" * padding

            decoded = base64.b64decode(base64_str).decode("utf-8")
            return decoded
        except Exception:
            return None

    def is_free_video(self, html: str) -> bool:
        """Check if video is free (not member-only)."""
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
