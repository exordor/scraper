"""Tests for storage operations."""

import tempfile
from pathlib import Path

import pytest

from eroasmr_scraper.models import Tag, Video
from eroasmr_scraper.storage import VideoStorage


@pytest.fixture
def temp_storage() -> VideoStorage:
    """Create temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = VideoStorage(str(db_path))
        yield storage


class TestVideoStorage:
    """Tests for VideoStorage class."""

    def test_upsert_videos(self, temp_storage: VideoStorage) -> None:
        """Test inserting videos."""
        videos = [
            Video(
                title="Test Video 1",
                slug="test-video-1",
                video_url="https://example.com/video/test-video-1/",
            ),
            Video(
                title="Test Video 2",
                slug="test-video-2",
                video_url="https://example.com/video/test-video-2/",
            ),
        ]

        count = temp_storage.upsert_videos(videos)

        assert count == 2
        assert temp_storage.video_exists("test-video-1")
        assert temp_storage.video_exists("test-video-2")

    def test_upsert_duplicate(self, temp_storage: VideoStorage) -> None:
        """Test upserting duplicate video updates existing."""
        video = Video(
            title="Original Title",
            slug="test-video",
            video_url="https://example.com/video/test-video/",
            likes=10,
        )
        temp_storage.upsert_videos([video])

        # Update with new data
        updated_video = Video(
            title="Updated Title",
            slug="test-video",
            video_url="https://example.com/video/test-video/",
            likes=20,
        )
        temp_storage.upsert_videos([updated_video])

        # Should have updated, not duplicated
        assert temp_storage.get_video_by_slug("test-video")["likes"] == 20
        stats = temp_storage.get_stats()
        assert stats["videos"] == 1

    def test_video_exists(self, temp_storage: VideoStorage) -> None:
        """Test video existence check."""
        assert not temp_storage.video_exists("nonexistent")

        video = Video(
            title="Test",
            slug="test-video",
            video_url="https://example.com/video/test-video/",
        )
        temp_storage.upsert_videos([video])

        assert temp_storage.video_exists("test-video")

    def test_get_video_by_slug(self, temp_storage: VideoStorage) -> None:
        """Test retrieving video by slug."""
        video = Video(
            title="Test Video",
            slug="test-video",
            video_url="https://example.com/video/test-video/",
            likes=100,
            views=500,
        )
        temp_storage.upsert_videos([video])

        result = temp_storage.get_video_by_slug("test-video")

        assert result is not None
        assert result["title"] == "Test Video"
        assert result["likes"] == 100
        assert result["views"] == 500

    def test_upsert_tag(self, temp_storage: VideoStorage) -> None:
        """Test inserting tags."""
        tag = Tag(name="ASMR", slug="asmr", tag_url="/video-tag/asmr/")

        tag_id = temp_storage.upsert_tag(tag)

        assert tag_id is not None
        assert temp_storage.get_tag_id("asmr") == tag_id

    def test_get_stats(self, temp_storage: VideoStorage) -> None:
        """Test statistics retrieval."""
        videos = [
            Video(
                title=f"Video {i}",
                slug=f"video-{i}",
                video_url=f"https://example.com/video/video-{i}/",
            )
            for i in range(5)
        ]
        temp_storage.upsert_videos(videos)

        stats = temp_storage.get_stats()

        assert stats["videos"] == 5
        assert stats["videos_with_details"] == 0  # No details scraped yet

    def test_export_for_neo4j(self, temp_storage: VideoStorage) -> None:
        """Test Neo4j CSV export."""
        video = Video(
            title="Test Video",
            slug="test-video",
            video_url="https://example.com/video/test-video/",
        )
        temp_storage.upsert_videos([video])

        tag = Tag(name="ASMR", slug="asmr")
        temp_storage.upsert_tag(tag)
        temp_storage.add_video_tag("test-video", "asmr")

        with tempfile.TemporaryDirectory() as tmpdir:
            files = temp_storage.export_for_neo4j(tmpdir)

            assert "videos" in files
            assert "tags" in files
            assert Path(files["videos"]).exists()
            assert Path(files["tags"]).exists()
