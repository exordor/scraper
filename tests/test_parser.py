"""Tests for HTML parser functions."""

import pytest

from eroasmr_scraper.parser import (
    parse_duration,
    parse_list_page,
    parse_slug_from_url,
    parse_views,
)


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_parse_mm_ss(self) -> None:
        """Parse MM:SS format."""
        assert parse_duration("07:11") == 431
        assert parse_duration("00:30") == 30
        assert parse_duration("59:59") == 3599

    def test_parse_hh_mm_ss(self) -> None:
        """Parse HH:MM:SS format."""
        assert parse_duration("1:23:45") == 5025
        assert parse_duration("2:00:00") == 7200

    def test_parse_none(self) -> None:
        """Handle None input."""
        assert parse_duration(None) is None

    def test_parse_empty(self) -> None:
        """Handle empty string."""
        assert parse_duration("") is None
        assert parse_duration("   ") is None

    def test_parse_invalid(self) -> None:
        """Handle invalid format."""
        assert parse_duration("invalid") is None
        assert parse_duration("abc:def") is None


class TestParseViews:
    """Tests for parse_views function."""

    def test_parse_simple_number(self) -> None:
        """Parse simple number."""
        assert parse_views("1234 Views") == 1234
        assert parse_views("500 views") == 500

    def test_parse_k_suffix(self) -> None:
        """Parse K (thousand) suffix."""
        assert parse_views("19.86K Views") == 19860
        assert parse_views("1K Views") == 1000
        assert parse_views("2.5K Views") == 2500

    def test_parse_m_suffix(self) -> None:
        """Parse M (million) suffix."""
        assert parse_views("1.5M Views") == 1_500_000
        assert parse_views("1M Views") == 1_000_000

    def test_parse_none(self) -> None:
        """Handle None input."""
        assert parse_views(None) == 0

    def test_parse_empty(self) -> None:
        """Handle empty string."""
        assert parse_views("") == 0

    def test_parse_no_number(self) -> None:
        """Handle string without number."""
        assert parse_views("No views") == 0


class TestParseSlugFromUrl:
    """Tests for parse_slug_from_url function."""

    def test_full_url(self) -> None:
        """Extract slug from full URL."""
        assert parse_slug_from_url("https://eroasmr.com/video/test-video/") == "test-video"

    def test_relative_url(self) -> None:
        """Extract slug from relative URL."""
        assert parse_slug_from_url("/video/my-video/") == "my-video"

    def test_no_trailing_slash(self) -> None:
        """Handle URL without trailing slash."""
        assert parse_slug_from_url("/video/test") == "test"

    def test_root_url(self) -> None:
        """Handle root URL."""
        assert parse_slug_from_url("/") == ""


class TestParseListPage:
    """Tests for parse_list_page function."""

    def test_parse_single_video(self) -> None:
        """Parse single video from HTML with real website structure."""
        html = """
        <article>
            <h2><a href="https://eroasmr.com/video/test-video/">Test Video Title</a></h2>
            <img src="https://example.com/thumb.jpg" />
            <span class="video-duration">10:30</span>
            <span class="video-like-counter">50</span>
            <span class="post-views">1.5K Views</span>
            <p class="excerpt">This is a test description</p>
        </article>
        """
        videos = parse_list_page(html)

        assert len(videos) == 1
        video = videos[0]

        assert video.title == "Test Video Title"
        assert video.slug == "test-video"
        assert video.video_url == "https://eroasmr.com/video/test-video/"
        assert video.thumbnail_url == "https://example.com/thumb.jpg"
        assert video.duration == "10:30"
        assert video.duration_seconds == 630
        assert video.likes == 50
        assert video.views == 1500

    def test_parse_multiple_videos(self) -> None:
        """Parse multiple videos from HTML."""
        html = """
        <article><h2><a href="/video/video-1/">Video 1</a></h2></article>
        <article><h2><a href="/video/video-2/">Video 2</a></h2></article>
        <article><h2><a href="/video/video-3/">Video 3</a></h2></article>
        """
        videos = parse_list_page(html)

        assert len(videos) == 3
        assert videos[0].slug == "video-1"
        assert videos[1].slug == "video-2"
        assert videos[2].slug == "video-3"

    def test_parse_empty_page(self) -> None:
        """Handle page with no videos."""
        html = "<html><body><p>No videos here</p></body></html>"
        videos = parse_list_page(html)

        assert len(videos) == 0

    def test_relative_url_resolution(self) -> None:
        """Resolve relative URLs with base_url."""
        html = """
        <article>
            <h2><a href="/video/relative-video/">Relative Video</a></h2>
        </article>
        """
        videos = parse_list_page(html, base_url="https://eroasmr.com")

        assert videos[0].video_url == "https://eroasmr.com/video/relative-video/"
