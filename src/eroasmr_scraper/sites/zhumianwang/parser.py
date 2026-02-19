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
