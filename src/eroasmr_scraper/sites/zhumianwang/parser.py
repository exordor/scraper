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

        # Description - look for section containing "ASMR介绍" or "ASMR Details"
        description = None
        for section in soup.find_all(["div", "section", "article"]):
            section_text = section.get_text()
            if "ASMR介绍" in section_text or "ASMR Details" in section_text or "介绍" in section_text[:50]:
                # Found the description section, get paragraph text
                paragraphs = section.find_all("p")
                if paragraphs:
                    desc_parts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 10:  # Skip very short paragraphs
                            desc_parts.append(text)
                    if desc_parts:
                        description = " ".join(desc_parts[:3])  # Take first 3 paragraphs
                        description = description[:2000]  # Limit length
                        break

        # Fallback: try common description selectors
        if not description:
            desc_elem = soup.select_one(".entry-content, .content, .video-desc, article p")
            if desc_elem:
                description = desc_elem.get_text(strip=True)[:2000]

        # Region (中国/韩国/日本/欧美) - look specifically in video info section
        # Find "地区：" text and get the following link
        region = Region.UNKNOWN
        page_text = soup.get_text()
        if "地区：韩国" in page_text or "地区:韩国" in page_text:
            region = Region.KOREA
        elif "地区：日本" in page_text or "地区:日本" in page_text:
            region = Region.JAPAN
        elif "地区：中国" in page_text or "地区:中国" in page_text:
            region = Region.CHINA
        elif "地区：欧美" in page_text or "地区:欧美" in page_text:
            region = Region.WESTERN
        else:
            # Fallback: look for region links after "地区：" label
            for li in soup.select("li"):
                li_text = li.get_text()
                if "地区" in li_text:
                    # Found the region list item
                    region_link = li.select_one("a[href*='/hg'], a[href*='/rb'], a[href*='/zg'], a[href*='/om']")
                    if region_link:
                        href = region_link.get("href", "")
                        if "/hg" in href:
                            region = Region.KOREA
                        elif "/rb" in href:
                            region = Region.JAPAN
                        elif "/zg" in href:
                            region = Region.CHINA
                        elif "/om" in href:
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

        # Related videos - look for section containing "相关推荐" or "精选ASMR"
        related_videos: list[RelatedVideo] = []
        related_section = None

        # Find the related videos section by text content
        for section in soup.find_all(["div", "section", "ul"]):
            section_text = section.get_text()[:100]  # Check first 100 chars
            if "相关推荐" in section_text or "精选ASMR" in section_text or "推荐" in section_text:
                related_section = section
                break

        # Fallback to class-based selectors
        if not related_section:
            related_section = soup.select_one(".related, .recommend, .related-posts")

        if related_section:
            for idx, item in enumerate(related_section.select("li")):
                link = item.select_one("a[href*='/asmr/']")
                if not link:
                    continue

                rel_title = link.get("title") or link.get_text(strip=True)[:100]
                rel_url = link.get("href", "")
                if rel_url and not rel_url.startswith("http"):
                    rel_url = urljoin(self.base_url, rel_url)

                # Skip article URLs (they have underscore like /asmr_43050.html)
                if "/asmr_" in rel_url:
                    continue

                if "/asmr/" in rel_url:
                    # Extract slug from URL like /asmr/33867.html -> 33867
                    rel_slug_match = re.search(r"/asmr/(\d+)\.html", rel_url)
                    if rel_slug_match:
                        rel_slug = rel_slug_match.group(1)
                    else:
                        rel_slug = self.parse_slug_from_url(rel_url).replace(".html", "")

                    img = item.select_one("img")
                    rel_thumb = None
                    if img:
                        rel_thumb = img.get("src") or img.get("data-src")
                        if rel_thumb and not rel_thumb.startswith("http"):
                            rel_thumb = urljoin(self.base_url, rel_thumb)

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
