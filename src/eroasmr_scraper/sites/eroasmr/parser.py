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
