"""Integration tests - validate parser against real website."""

import pytest

from eroasmr_scraper.parser import parse_list_page


@pytest.fixture
def real_html():
    """Fetch real page HTML from eroasmr.com."""
    import httpx

    resp = httpx.get("https://eroasmr.com/new-videos/", timeout=30)
    return resp.text


class TestParseRealPage:
    """Tests using real website HTML."""

    def test_parse_real_page_returns_videos(self, real_html: str) -> None:
        """Verify parser extracts videos from real page."""
        videos = parse_list_page(real_html)
        assert len(videos) > 0, "Should parse at least one video"

    def test_parse_real_page_extracts_duration(self, real_html: str) -> None:
        """Verify all videos have valid duration from real page."""
        videos = parse_list_page(real_html)

        for v in videos:
            assert v.duration is not None, f"Missing duration for {v.slug}"
            assert v.duration_seconds is not None, f"Missing duration_seconds for {v.slug}"
            assert v.duration_seconds > 0, f"Invalid duration_seconds for {v.slug}"

    def test_parse_real_page_extracts_views(self, real_html: str) -> None:
        """Verify all videos have valid views from real page."""
        videos = parse_list_page(real_html)

        for v in videos:
            assert v.views > 0, f"Missing views for {v.slug}: got {v.views}"
            assert v.views_raw is not None, f"Missing views_raw for {v.slug}"

    def test_parse_real_page_extracts_likes(self, real_html: str) -> None:
        """Verify all videos have valid likes from real page."""
        videos = parse_list_page(real_html)

        for v in videos:
            assert v.likes >= 0, f"Invalid likes for {v.slug}: got {v.likes}"

    def test_parse_real_page_extracts_title(self, real_html: str) -> None:
        """Verify all videos have valid title from real page."""
        videos = parse_list_page(real_html)

        for v in videos:
            assert v.title, f"Missing title for {v.slug}"
            assert len(v.title) > 0, f"Empty title for {v.slug}"

    def test_parse_real_page_extracts_slug(self, real_html: str) -> None:
        """Verify all videos have valid slug from real page."""
        videos = parse_list_page(real_html)

        for v in videos:
            assert v.slug, f"Missing slug"
            assert "/" not in v.slug, f"Invalid slug format: {v.slug}"
