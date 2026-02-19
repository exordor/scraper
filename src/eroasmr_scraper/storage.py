"""SQLite storage layer using sqlite-utils."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlite_utils import Database
from sqlite_utils.db import NotFoundError

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import (
    Category,
    DownloadStatus,
    FailedUrl,
    RelatedVideo,
    ScrapeProgress,
    StorageLocation,
    Tag,
    Video,
    VideoDetail,
    VideoDownload,
)


class VideoStorage:
    """SQLite storage manager for video metadata."""

    def __init__(self, db_path: str | None = None, site_id: str = "eroasmr"):
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file. Defaults to settings value.
            site_id: Site identifier for multi-site support
        """
        self.db_path = db_path or settings.db.path
        self.site_id = site_id
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # Use check_same_thread=False for thread-safe access in parallel pipeline
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db = Database(conn)
        self._setup_tables()

    def _setup_tables(self) -> None:
        """Create database tables if not exist."""
        # Videos table
        self.db["videos"].create(
            columns={
                "id": int,
                "site_id": str,
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
        self.db["videos"].create_index(["site_id"], if_not_exists=True)

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
                "site_id": str,
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
                "site_id": str,
                "url": str,
                "url_type": str,
                "error": str,
                "retry_count": int,
                "created_at": str,
            },
            pk="id",
            if_not_exists=True,
        )

        # Downloads table - track video download status
        self.db["downloads"].create(
            columns={
                "slug": str,
                "site_id": str,
                "status": str,
                "local_path": str,
                "file_size": int,
                "error_message": str,
                "downloaded_at": str,
            },
            pk="slug",
            not_null={"slug", "status"},
            if_not_exists=True,
        )
        self.db["downloads"].create_index(["status"], if_not_exists=True)
        self.db["downloads"].create_index(["site_id"], if_not_exists=True)

        # Storage locations table - track uploaded locations (future extension)
        self.db["storage_locations"].create(
            columns={
                "id": int,
                "slug": str,
                "storage_type": str,
                "location_id": str,
                "location_url": str,
                "metadata": str,  # JSON
                "uploaded_at": str,
            },
            pk="id",
            not_null={"slug", "storage_type", "location_id"},
            if_not_exists=True,
        )
        self.db["storage_locations"].create_index(["slug"], if_not_exists=True)
        self.db["storage_locations"].create_index(
            ["slug", "storage_type"], unique=True, if_not_exists=True
        )

        # Enable foreign keys
        self.db.execute("PRAGMA foreign_keys = ON")

    # ============================================
    # Video operations
    # ============================================

    def upsert_videos(self, videos: list[Video], update_existing: bool = True) -> int:
        """Insert or update videos in batch.

        Args:
            videos: List of Video objects
            update_existing: If True, update existing records; if False, ignore duplicates

        Returns:
            Number of videos inserted/updated
        """
        records = []
        for v in videos:
            # Get site_id from video if available, otherwise use storage's site_id
            video_site_id = getattr(v, 'site_id', self.site_id)
            records.append({
                "slug": v.slug,
                "site_id": video_site_id,
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

        # Use insert_all with replace=True to update existing records
        # This works because slug has a unique index
        self.db["videos"].insert_all(
            records,
            replace=update_existing,
            batch_size=settings.db.batch_size,
        )
        return len(records)

    def upsert_video_detail(self, video: VideoDetail) -> None:
        """Insert or update video with full details.

        Args:
            video: VideoDetail object
        """
        video_site_id = getattr(video, 'site_id', self.site_id)

        # Check if video exists
        if self.video_exists(video.slug):
            # Update existing record
            self.db.execute(
                """
                UPDATE videos SET
                    title = ?,
                    video_url = ?,
                    thumbnail_url = ?,
                    duration = ?,
                    duration_seconds = ?,
                    likes = ?,
                    views = ?,
                    views_raw = ?,
                    excerpt = ?,
                    description = ?,
                    author = ?,
                    author_url = ?,
                    author_videos_count = ?,
                    comment_count = ?,
                    published_at = ?,
                    detail_scraped_at = ?,
                    updated_at = ?
                WHERE slug = ?
                """,
                [
                    video.title,
                    video.video_url,
                    video.thumbnail_url,
                    video.duration,
                    video.duration_seconds,
                    video.likes,
                    video.views,
                    video.views_raw,
                    video.excerpt,
                    video.description,
                    video.author,
                    video.author_url,
                    video.author_videos_count,
                    video.comment_count,
                    video.published_at,
                    video.detail_scraped_at.isoformat(),
                    datetime.now().isoformat(),
                    video.slug,
                ],
            )
        else:
            # Insert new record
            self.db["videos"].insert(
                {
                    "slug": video.slug,
                    "site_id": video_site_id,
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
                    "scraped_at": video.scraped_at.isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )

    def video_exists(self, slug: str, site_id: str | None = None) -> bool:
        """Check if video exists in database.

        Args:
            slug: Video slug
            site_id: Optional site filter (uses self.site_id if not provided)

        Returns:
            True if video exists
        """
        filter_site_id = site_id or self.site_id
        rows = list(self.db["videos"].rows_where(
            "slug = ? AND site_id = ?",
            [slug, filter_site_id],
            limit=1
        ))
        return len(rows) > 0

    def get_video_by_slug(self, slug: str, site_id: str | None = None) -> dict | None:
        """Get video by slug.

        Args:
            slug: Video slug
            site_id: Optional site filter

        Returns:
            Video record or None
        """
        filter_site_id = site_id or self.site_id
        rows = list(self.db["videos"].rows_where(
            "slug = ? AND site_id = ?",
            [slug, filter_site_id],
            limit=1
        ))
        return rows[0] if rows else None

    def get_video_id(self, slug: str, site_id: str | None = None) -> int | None:
        """Get video database ID by slug.

        Args:
            slug: Video slug
            site_id: Optional site filter

        Returns:
            Video ID or None
        """
        filter_site_id = site_id or self.site_id
        rows = list(self.db["videos"].rows_where(
            "slug = ? AND site_id = ?",
            [slug, filter_site_id],
            select="id",
            limit=1
        ))
        return rows[0]["id"] if rows else None

    def get_videos_without_details(self, limit: int = 100, site_id: str | None = None) -> list[dict]:
        """Get videos that haven't had detail page scraped.

        Args:
            limit: Maximum number to return
            site_id: Optional site filter

        Returns:
            List of video records
        """
        filter_site_id = site_id or self.site_id
        return list(
            self.db["videos"]
            .rows_where("detail_scraped_at IS NULL AND site_id = ?", [filter_site_id], limit=limit)
        )

    def update_video_duration(
        self, slug: str, duration: str | None, duration_seconds: int | None
    ) -> bool:
        """Update duration fields for an existing video.

        Args:
            slug: Video slug
            duration: Duration string (e.g., "07:11")
            duration_seconds: Duration in seconds

        Returns:
            True if updated, False if video not found
        """
        if not self.video_exists(slug):
            return False

        self.db.execute(
            """
            UPDATE videos SET
                duration = ?,
                duration_seconds = ?,
                updated_at = ?
            WHERE slug = ?
            """,
            [duration, duration_seconds, datetime.now().isoformat(), slug],
        )
        return True

    def update_videos_duration(self, videos: list[Video]) -> int:
        """Batch update duration for existing videos.

        Args:
            videos: List of Video objects with updated duration

        Returns:
            Number of videos updated
        """
        updated = 0
        for v in videos:
            if self.update_video_duration(v.slug, v.duration, v.duration_seconds):
                updated += 1
        return updated

    def get_videos_count(self, site_id: str | None = None) -> int:
        """Get total video count.

        Args:
            site_id: Optional site filter
        """
        filter_site_id = site_id or self.site_id
        return self.db["videos"].count_where("site_id = ?", [filter_site_id])

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
        self.db["tags"].insert(
            {
                "slug": tag.slug,
                "name": tag.name,
                "tag_url": tag.tag_url,
            },
            ignore=True,
        )
        return self.get_tag_id(tag.slug) or 0

    def get_tag_id(self, slug: str) -> int | None:
        """Get tag ID by slug."""
        rows = list(self.db["tags"].rows_where("slug = ?", [slug], select="id", limit=1))
        return rows[0]["id"] if rows else None

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
        self.db["categories"].insert(
            {
                "slug": category.slug,
                "name": category.name,
                "category_url": category.category_url,
                "video_count": category.video_count,
            },
            ignore=True,
        )
        return self.get_category_id(category.slug) or 0

    def get_category_id(self, slug: str) -> int | None:
        """Get category ID by slug."""
        rows = list(self.db["categories"].rows_where("slug = ?", [slug], select="id", limit=1))
        return rows[0]["id"] if rows else None

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
        progress_site_id = getattr(progress, 'site_id', self.site_id)
        self.db["scrape_progress"].upsert(
            {
                "id": 1,
                "site_id": progress_site_id,
                "mode": progress.mode,
                "phase": progress.phase,
                "last_page": progress.last_page,
                "last_video_id": progress.last_video_id,
                "total_pages": progress.total_pages,
                "last_updated": progress.last_updated.isoformat(),
            },
            pk="id",
        )

    def get_progress(self, site_id: str | None = None) -> ScrapeProgress | None:
        """Get current scraping progress.

        Args:
            site_id: Optional site filter

        Returns:
            ScrapeProgress or None
        """
        filter_site_id = site_id or self.site_id
        try:
            row = self.db["scrape_progress"].get(1)
            # Check if site_id matches
            if row.get("site_id") and row["site_id"] != filter_site_id:
                return None
            return ScrapeProgress(
                site_id=row.get("site_id", filter_site_id),
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
        failed_site_id = getattr(failed, 'site_id', self.site_id)
        self.db["failed_urls"].insert(
            {
                "site_id": failed_site_id,
                "url": failed.url,
                "url_type": failed.url_type,
                "error": failed.error,
                "retry_count": failed.retry_count,
                "created_at": failed.created_at.isoformat(),
            }
        )

    def get_failed_urls(self, limit: int = 100, site_id: str | None = None) -> list[dict]:
        """Get failed URLs for retry.

        Args:
            limit: Maximum number to return
            site_id: Optional site filter

        Returns:
            List of failed URL records
        """
        filter_site_id = site_id or self.site_id
        return list(
            self.db["failed_urls"]
            .rows_where("retry_count < 3 AND site_id = ?", [filter_site_id], limit=limit, order_by="created_at")
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

    def get_stats(self, site_id: str | None = None) -> dict[str, Any]:
        """Get database statistics.

        Args:
            site_id: Optional site filter

        Returns:
            Dictionary of statistics
        """
        filter_site_id = site_id or self.site_id
        return {
            "site_id": filter_site_id,
            "videos": self.db["videos"].count_where("site_id = ?", [filter_site_id]),
            "videos_with_details": self.db["videos"].count_where(
                "detail_scraped_at IS NOT NULL AND site_id = ?",
                [filter_site_id]
            ),
            "tags": self.db["tags"].count,
            "categories": self.db["categories"].count,
            "video_tags": self.db["video_tags"].count,
            "video_related": self.db["video_related"].count,
            "failed_urls": self.db["failed_urls"].count_where("site_id = ?", [filter_site_id]),
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
        import csv
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        files = {}

        def table_to_csv(table_name: str, filename: str) -> str:
            """Export table to CSV file."""
            filepath = output_path / filename
            rows = list(self.db[table_name].rows)
            if rows:
                with open(filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                # Create empty file with no headers
                open(filepath, "w").close()
            return str(filepath)

        # Export all tables
        files["videos"] = table_to_csv("videos", "videos.csv")
        files["tags"] = table_to_csv("tags", "tags.csv")
        files["categories"] = table_to_csv("categories", "categories.csv")
        files["video_tags"] = table_to_csv("video_tags", "video_tags.csv")
        files["video_categories"] = table_to_csv("video_categories", "video_categories.csv")
        files["video_related"] = table_to_csv("video_related", "video_related.csv")

        return files

    # ============================================
    # Download operations
    # ============================================

    def get_pending_downloads(
        self, limit: int | None = None, include_failed: bool = False, site_id: str | None = None
    ) -> list[str]:
        """Get slugs of videos pending download.

        Args:
            limit: Maximum number to return
            include_failed: If True, also include failed downloads for retry
            site_id: Optional site filter

        Returns:
            List of video slugs
        """
        filter_site_id = site_id or self.site_id

        # Get all video slugs for this site ordered by id (insertion order)
        all_slugs = [
            row["slug"]
            for row in self.db["videos"].rows_where("site_id = ?", [filter_site_id], order_by="id")
        ]

        # Get already downloaded slugs for this site
        if include_failed:
            downloaded_slugs = set(
                row["slug"]
                for row in self.db["downloads"].rows_where(
                    "status IN ('completed', 'downloading') AND site_id = ?",
                    [filter_site_id]
                )
            )
        else:
            downloaded_slugs = set(
                row["slug"]
                for row in self.db["downloads"].rows_where("site_id = ?", [filter_site_id])
            )

        # Filter and limit
        pending = [s for s in all_slugs if s not in downloaded_slugs]
        if limit:
            pending = pending[:limit]
        return pending

    def get_download_record(self, slug: str) -> dict | None:
        """Get download record by slug.

        Args:
            slug: Video slug

        Returns:
            Download record or None
        """
        rows = list(self.db["downloads"].rows_where("slug = ?", [slug], limit=1))
        return rows[0] if rows else None

    def init_download(self, slug: str, site_id: str | None = None) -> None:
        """Initialize a download record (if not exists).

        Args:
            slug: Video slug
            site_id: Optional site identifier
        """
        download_site_id = site_id or self.site_id
        self.db["downloads"].upsert(
            {
                "slug": slug,
                "site_id": download_site_id,
                "status": DownloadStatus.PENDING.value,
            },
            pk="slug",
        )

    def update_download_status(
        self,
        slug: str,
        status: DownloadStatus,
        local_path: str | None = None,
        file_size: int | None = None,
        error_message: str | None = None,
        site_id: str | None = None,
    ) -> None:
        """Update download status.

        Args:
            slug: Video slug
            status: New status
            local_path: Local file path (on completion)
            file_size: File size in bytes (on completion)
            error_message: Error message (on failure)
            site_id: Optional site identifier
        """
        download_site_id = site_id or self.site_id
        record: dict[str, Any] = {
            "slug": slug,
            "site_id": download_site_id,
            "status": status.value,
        }

        if status == DownloadStatus.COMPLETED:
            record["local_path"] = local_path
            record["file_size"] = file_size
            record["downloaded_at"] = datetime.now().isoformat()
        elif status == DownloadStatus.FAILED:
            record["error_message"] = error_message

        # Use insert with replace=True instead of upsert for reliability
        self.db["downloads"].insert(record, pk="slug", replace=True)

    def mark_downloading(self, slug: str) -> None:
        """Mark download as in progress."""
        self.update_download_status(slug, DownloadStatus.DOWNLOADING)

    def mark_completed(self, slug: str, local_path: str, file_size: int) -> None:
        """Mark download as completed."""
        self.update_download_status(
            slug, DownloadStatus.COMPLETED, local_path, file_size
        )

    def mark_failed(self, slug: str, error_message: str) -> None:
        """Mark download as failed."""
        self.update_download_status(slug, DownloadStatus.FAILED, error_message=error_message)

    def get_download_stats(self, site_id: str | None = None) -> dict[str, int]:
        """Get download statistics.

        Args:
            site_id: Optional site filter

        Returns:
            Dictionary with counts by status
        """
        filter_site_id = site_id or self.site_id
        stats = {
            "total_videos": self.db["videos"].count_where("site_id = ?", [filter_site_id]),
            "pending": self.db["downloads"].count_where("status = 'pending' AND site_id = ?", [filter_site_id]),
            "downloading": self.db["downloads"].count_where("status = 'downloading' AND site_id = ?", [filter_site_id]),
            "completed": self.db["downloads"].count_where("status = 'completed' AND site_id = ?", [filter_site_id]),
            "failed": self.db["downloads"].count_where("status = 'failed' AND site_id = ?", [filter_site_id]),
        }
        stats["not_started"] = stats["total_videos"] - sum(
            [stats["pending"], stats["downloading"], stats["completed"], stats["failed"]]
        )
        return stats

    # ============================================
    # Storage location operations (future extension)
    # ============================================

    def add_storage_location(self, location: StorageLocation) -> None:
        """Add a storage location record.

        Args:
            location: StorageLocation object
        """
        import json

        self.db["storage_locations"].insert(
            {
                "slug": location.slug,
                "storage_type": location.storage_type,
                "location_id": location.location_id,
                "location_url": location.location_url,
                "metadata": json.dumps(location.metadata) if location.metadata else None,
                "uploaded_at": location.uploaded_at.isoformat(),
            }
        )

    def get_storage_locations(self, slug: str) -> list[dict]:
        """Get all storage locations for a video.

        Args:
            slug: Video slug

        Returns:
            List of storage location records
        """
        return list(self.db["storage_locations"].rows_where("slug = ?", [slug]))
