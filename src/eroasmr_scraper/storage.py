"""SQLite storage layer using sqlite-utils."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlite_utils import Database

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import (
    Category,
    FailedUrl,
    RelatedVideo,
    ScrapeProgress,
    Tag,
    Video,
    VideoDetail,
)


class VideoStorage:
    """SQLite storage manager for video metadata."""

    def __init__(self, db_path: str | None = None):
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file. Defaults to settings value.
        """
        self.db_path = db_path or settings.db.path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.db_path)
        self._setup_tables()

    def _setup_tables(self) -> None:
        """Create database tables if not exist."""
        # Videos table
        self.db["videos"].create(
            columns={
                "id": int,
                "title": str,
                "slug": str,
                "video_url": str,
                "thumbnail_url": str,
                "duration": str,
                "duration_seconds": int,
                "likes": int,
                "views": int,
                "views_raw": str,
                "excerpt": str,
                "description": str,
                "author": str,
                "author_url": str,
                "author_videos_count": int,
                "comment_count": int,
                "published_at": str,
                "created_at": str,
                "updated_at": str,
                "scraped_at": str,
                "detail_scraped_at": str,
            },
            pk="id",
            not_null={"title", "slug", "video_url"},
            if_not_exists=True,
        )

        # Create indexes
        self.db["videos"].create_index(["slug"], unique=True, if_not_exists=True)
        self.db["videos"].create_index(["video_url"], unique=True, if_not_exists=True)
        self.db["videos"].create_index(["scraped_at"], if_not_exists=True)

        # Tags table
        self.db["tags"].create(
            columns={
                "id": int,
                "name": str,
                "slug": str,
                "tag_url": str,
            },
            pk="id",
            not_null={"name", "slug"},
            if_not_exists=True,
        )
        self.db["tags"].create_index(["slug"], unique=True, if_not_exists=True)
        self.db["tags"].create_index(["name"], if_not_exists=True)

        # Categories table
        self.db["categories"].create(
            columns={
                "id": int,
                "name": str,
                "slug": str,
                "category_url": str,
                "video_count": int,
            },
            pk="id",
            not_null={"name", "slug"},
            if_not_exists=True,
        )
        self.db["categories"].create_index(["slug"], unique=True, if_not_exists=True)

        # Video-Tags relationship
        self.db["video_tags"].create(
            columns={
                "video_id": int,
                "tag_id": int,
            },
            pk=("video_id", "tag_id"),
            if_not_exists=True,
        )

        # Video-Categories relationship
        self.db["video_categories"].create(
            columns={
                "video_id": int,
                "category_id": int,
            },
            pk=("video_id", "category_id"),
            if_not_exists=True,
        )

        # Related videos relationship
        self.db["video_related"].create(
            columns={
                "source_video_id": int,
                "related_video_id": int,
                "position": int,
                "related_title": str,
                "related_slug": str,
                "scraped_at": str,
            },
            pk=("source_video_id", "related_video_id"),
            if_not_exists=True,
        )
        self.db["video_related"].create_index(["source_video_id"], if_not_exists=True)
        self.db["video_related"].create_index(["related_video_id"], if_not_exists=True)

        # Scrape progress table
        self.db["scrape_progress"].create(
            columns={
                "id": int,
                "mode": str,
                "phase": str,
                "last_page": int,
                "last_video_id": int,
                "total_pages": int,
                "last_updated": str,
            },
            pk="id",
            if_not_exists=True,
        )

        # Failed URLs table
        self.db["failed_urls"].create(
            columns={
                "id": int,
                "url": str,
                "url_type": str,
                "error": str,
                "retry_count": int,
                "created_at": str,
            },
            pk="id",
            if_not_exists=True,
        )

        # Enable foreign keys
        self.db.execute("PRAGMA foreign_keys = ON")

    # ============================================
    # Video operations
    # ============================================

    def upsert_videos(self, videos: list[Video]) -> int:
        """Insert or update videos in batch.

        Args:
            videos: List of Video objects

        Returns:
            Number of videos inserted/updated
        """
        records = []
        for v in videos:
            records.append({
                "slug": v.slug,
                "title": v.title,
                "video_url": v.video_url,
                "thumbnail_url": v.thumbnail_url,
                "duration": v.duration,
                "duration_seconds": v.duration_seconds,
                "likes": v.likes,
                "views": v.views,
                "views_raw": v.views_raw,
                "excerpt": v.excerpt,
                "scraped_at": v.scraped_at.isoformat(),
                "updated_at": datetime.now().isoformat(),
            })

        if not records:
            return 0

        self.db["videos"].upsert_all(
            records,
            pk="slug",
            batch_size=settings.db.batch_size,
        )
        return len(records)

    def upsert_video_detail(self, video: VideoDetail) -> None:
        """Insert or update video with full details.

        Args:
            video: VideoDetail object
        """
        self.db["videos"].upsert(
            {
                "slug": video.slug,
                "title": video.title,
                "video_url": video.video_url,
                "thumbnail_url": video.thumbnail_url,
                "duration": video.duration,
                "duration_seconds": video.duration_seconds,
                "likes": video.likes,
                "views": video.views,
                "views_raw": video.views_raw,
                "excerpt": video.excerpt,
                "description": video.description,
                "author": video.author,
                "author_url": video.author_url,
                "author_videos_count": video.author_videos_count,
                "comment_count": video.comment_count,
                "published_at": video.published_at,
                "detail_scraped_at": video.detail_scraped_at.isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            pk="slug",
        )

    def video_exists(self, slug: str) -> bool:
        """Check if video exists in database.

        Args:
            slug: Video slug

        Returns:
            True if video exists
        """
        try:
            self.db["videos"].get(slug)
            return True
        except sqlite3.OperationalError:
            return False
        except KeyError:
            return False

    def get_video_by_slug(self, slug: str) -> dict | None:
        """Get video by slug.

        Args:
            slug: Video slug

        Returns:
            Video record or None
        """
        try:
            return dict(self.db["videos"].get(slug))
        except (KeyError, sqlite3.OperationalError):
            return None

    def get_video_id(self, slug: str) -> int | None:
        """Get video database ID by slug.

        Args:
            slug: Video slug

        Returns:
            Video ID or None
        """
        try:
            row = self.db["videos"].get(slug)
            return row["id"]
        except (KeyError, sqlite3.OperationalError):
            return None

    def get_videos_without_details(self, limit: int = 100) -> list[dict]:
        """Get videos that haven't had detail page scraped.

        Args:
            limit: Maximum number to return

        Returns:
            List of video records
        """
        return list(
            self.db["videos"]
            .rows_where("detail_scraped_at IS NULL", limit=limit)
        )

    # ============================================
    # Tag operations
    # ============================================

    def upsert_tag(self, tag: Tag) -> int:
        """Insert or update tag and return ID.

        Args:
            tag: Tag object

        Returns:
            Tag ID
        """
        self.db["tags"].upsert(
            {
                "slug": tag.slug,
                "name": tag.name,
                "tag_url": tag.tag_url,
            },
            pk="slug",
        )
        return self.db["tags"].get(tag.slug)["id"]

    def get_tag_id(self, slug: str) -> int | None:
        """Get tag ID by slug."""
        try:
            return self.db["tags"].get(slug)["id"]
        except (KeyError, sqlite3.OperationalError):
            return None

    # ============================================
    # Category operations
    # ============================================

    def upsert_category(self, category: Category) -> int:
        """Insert or update category and return ID.

        Args:
            category: Category object

        Returns:
            Category ID
        """
        self.db["categories"].upsert(
            {
                "slug": category.slug,
                "name": category.name,
                "category_url": category.category_url,
                "video_count": category.video_count,
            },
            pk="slug",
        )
        return self.db["categories"].get(category.slug)["id"]

    def get_category_id(self, slug: str) -> int | None:
        """Get category ID by slug."""
        try:
            return self.db["categories"].get(slug)["id"]
        except (KeyError, sqlite3.OperationalError):
            return None

    # ============================================
    # Relationship operations
    # ============================================

    def add_video_tag(self, video_slug: str, tag_slug: str) -> None:
        """Add video-tag relationship.

        Args:
            video_slug: Video slug
            tag_slug: Tag slug
        """
        video_id = self.get_video_id(video_slug)
        tag_id = self.get_tag_id(tag_slug)

        if video_id and tag_id:
            try:
                self.db["video_tags"].insert(
                    {"video_id": video_id, "tag_id": tag_id},
                    pk=("video_id", "tag_id"),
                    ignore=True,
                )
            except sqlite3.IntegrityError:
                pass  # Already exists

    def add_video_category(self, video_slug: str, category_slug: str) -> None:
        """Add video-category relationship."""
        video_id = self.get_video_id(video_slug)
        category_id = self.get_category_id(category_slug)

        if video_id and category_id:
            try:
                self.db["video_categories"].insert(
                    {"video_id": video_id, "category_id": category_id},
                    pk=("video_id", "category_id"),
                    ignore=True,
                )
            except sqlite3.IntegrityError:
                pass

    def add_related_video(
        self, source_slug: str, related: RelatedVideo, related_video_id: int | None = None
    ) -> None:
        """Add related video relationship.

        Args:
            source_slug: Source video slug
            related: RelatedVideo object
            related_video_id: ID of related video (if known)
        """
        source_id = self.get_video_id(source_slug)

        if not source_id:
            return

        # If related video doesn't exist yet, create placeholder
        if not related_video_id:
            # Check if related video exists
            related_video_id = self.get_video_id(related.slug)
            if not related_video_id:
                # Create placeholder video
                self.db["videos"].insert(
                    {
                        "slug": related.slug,
                        "title": related.title,
                        "video_url": related.video_url,
                        "thumbnail_url": related.thumbnail_url,
                        "scraped_at": datetime.now().isoformat(),
                    },
                    pk="slug",
                    ignore=True,
                )
                related_video_id = self.get_video_id(related.slug)

        if source_id and related_video_id:
            try:
                self.db["video_related"].upsert(
                    {
                        "source_video_id": source_id,
                        "related_video_id": related_video_id,
                        "position": related.position,
                        "related_title": related.title,
                        "related_slug": related.slug,
                        "scraped_at": datetime.now().isoformat(),
                    },
                    pk=("source_video_id", "related_video_id"),
                )
            except sqlite3.IntegrityError:
                pass

    # ============================================
    # Progress tracking
    # ============================================

    def save_progress(self, progress: ScrapeProgress) -> None:
        """Save scraping progress.

        Args:
            progress: ScrapeProgress object
        """
        self.db["scrape_progress"].upsert(
            {
                "id": 1,
                "mode": progress.mode,
                "phase": progress.phase,
                "last_page": progress.last_page,
                "last_video_id": progress.last_video_id,
                "total_pages": progress.total_pages,
                "last_updated": progress.last_updated.isoformat(),
            },
            pk="id",
        )

    def get_progress(self) -> ScrapeProgress | None:
        """Get current scraping progress.

        Returns:
            ScrapeProgress or None
        """
        try:
            row = self.db["scrape_progress"].get(1)
            return ScrapeProgress(
                mode=row["mode"],
                phase=row["phase"],
                last_page=row["last_page"],
                last_video_id=row["last_video_id"],
                total_pages=row["total_pages"],
                last_updated=datetime.fromisoformat(row["last_updated"]),
            )
        except (KeyError, sqlite3.OperationalError):
            return None

    def clear_progress(self) -> None:
        """Clear scraping progress."""
        try:
            self.db["scrape_progress"].delete(1)
        except sqlite3.OperationalError:
            pass

    # ============================================
    # Failed URL tracking
    # ============================================

    def add_failed_url(self, failed: FailedUrl) -> None:
        """Record failed URL for retry.

        Args:
            failed: FailedUrl object
        """
        self.db["failed_urls"].insert(
            {
                "url": failed.url,
                "url_type": failed.url_type,
                "error": failed.error,
                "retry_count": failed.retry_count,
                "created_at": failed.created_at.isoformat(),
            }
        )

    def get_failed_urls(self, limit: int = 100) -> list[dict]:
        """Get failed URLs for retry.

        Args:
            limit: Maximum number to return

        Returns:
            List of failed URL records
        """
        return list(
            self.db["failed_urls"]
            .rows_where("retry_count < 3", limit=limit, order_by="created_at")
        )

    def increment_retry_count(self, url: str) -> None:
        """Increment retry count for a failed URL."""
        self.db.execute(
            "UPDATE failed_urls SET retry_count = retry_count + 1 WHERE url = ?",
            [url],
        )

    def remove_failed_url(self, url: str) -> None:
        """Remove successfully retried URL."""
        self.db["failed_urls"].delete_where("url = ?", [url])

    # ============================================
    # Statistics
    # ============================================

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            "videos": self.db["videos"].count,
            "videos_with_details": self.db["videos"].count_where(
                "detail_scraped_at IS NOT NULL"
            ),
            "tags": self.db["tags"].count,
            "categories": self.db["categories"].count,
            "video_tags": self.db["video_tags"].count,
            "video_related": self.db["video_related"].count,
            "failed_urls": self.db["failed_urls"].count,
        }

    # ============================================
    # Export
    # ============================================

    def export_for_neo4j(self, output_dir: str) -> dict[str, str]:
        """Export data as CSV files for Neo4j import.

        Args:
            output_dir: Directory to write CSV files

        Returns:
            Dictionary mapping entity names to file paths
        """
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        files = {}

        # Export videos
        videos_file = output_path / "videos.csv"
        self.db["videos"].to_csv(str(videos_file))
        files["videos"] = str(videos_file)

        # Export tags
        tags_file = output_path / "tags.csv"
        self.db["tags"].to_csv(str(tags_file))
        files["tags"] = str(tags_file)

        # Export categories
        categories_file = output_path / "categories.csv"
        self.db["categories"].to_csv(str(categories_file))
        files["categories"] = str(categories_file)

        # Export video_tags relationships
        video_tags_file = output_path / "video_tags.csv"
        self.db["video_tags"].to_csv(str(video_tags_file))
        files["video_tags"] = str(video_tags_file)

        # Export video_categories relationships
        video_categories_file = output_path / "video_categories.csv"
        self.db["video_categories"].to_csv(str(video_categories_file))
        files["video_categories"] = str(video_categories_file)

        # Export video_related relationships
        video_related_file = output_path / "video_related.csv"
        self.db["video_related"].to_csv(str(video_related_file))
        files["video_related"] = str(video_related_file)

        return files
