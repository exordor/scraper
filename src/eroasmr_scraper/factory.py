"""Factory for creating site-specific scrapers."""

from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from eroasmr_scraper.base.scraper import BaseSiteScraper


class ScraperFactory:
    """Factory for creating site-specific scraper instances."""

    _registry: dict[str, Type["BaseSiteScraper"]] = {}

    @classmethod
    def register(cls, site_id: str, scraper_class: Type["BaseSiteScraper"]) -> None:
        """Register a scraper class for a site."""
        cls._registry[site_id] = scraper_class

    @classmethod
    def create(cls, site_id: str, storage: any = None) -> "BaseSiteScraper":
        """Create a scraper instance for a site."""
        if site_id not in cls._registry:
            raise ValueError(
                f"Unknown site: {site_id}. Available: {list(cls._registry.keys())}"
            )
        scraper_class = cls._registry[site_id]
        return scraper_class(storage=storage)

    @classmethod
    def list_sites(cls) -> list[str]:
        """List all registered sites."""
        return list(cls._registry.keys())


def register_scraper(site_id: str):
    """Decorator to auto-register a scraper class."""
    def decorator(cls: Type["BaseSiteScraper"]) -> Type["BaseSiteScraper"]:
        ScraperFactory.register(site_id, cls)
        return cls
    return decorator
