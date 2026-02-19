"""Tests for base models."""

import pytest
from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail, BaseTag


class TestBaseModels:
    def test_base_video_requires_site_id(self):
        """BaseVideo should require site_id."""
        with pytest.raises(Exception):  # ValidationError
            BaseVideo(
                title="Test Video",
                slug="test-video",
                video_url="https://example.com/video/test",
            )

    def test_base_video_with_site_id(self):
        """BaseVideo should work with site_id."""
        video = BaseVideo(
            title="Test Video",
            slug="test-video",
            video_url="https://example.com/video/test",
            site_id="test_site",
        )
        assert video.title == "Test Video"
        assert video.site_id == "test_site"

    def test_base_tag(self):
        """BaseTag should have name and slug."""
        tag = BaseTag(name="Test Tag", slug="test-tag")
        assert tag.name == "Test Tag"
        assert tag.slug == "test-tag"
