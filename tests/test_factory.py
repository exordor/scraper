"""Tests for scraper factory."""

import pytest
from eroasmr_scraper.factory import ScraperFactory


class TestScraperFactory:
    def test_list_sites_empty_initially(self):
        """Factory should start with no sites registered."""
        # Reset for test isolation
        factory = ScraperFactory()
        factory._registry.clear()
        assert factory.list_sites() == []
