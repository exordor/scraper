"""Pydantic Settings configuration for the scraper."""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HttpConfig(BaseModel):
    """HTTP client configuration."""

    base_url: str = "https://eroasmr.com"
    delay_min: float = Field(default=1.5, description="Minimum request delay (seconds)")
    delay_max: float = Field(default=3.0, description="Maximum request delay (seconds)")
    timeout_connect: float = 5.0
    timeout_read: float = 30.0
    timeout_write: float = 5.0
    timeout_pool: float = 10.0
    max_connections: int = Field(default=3, description="Maximum concurrent connections")
    max_keepalive: int = 2
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


class DatabaseConfig(BaseModel):
    """Database configuration."""

    path: str = "data/videos.db"
    batch_size: int = 100  # Batch insert size


class ScraperConfig(BaseModel):
    """Scraper behavior configuration."""

    start_page: int = 1
    end_page: int | None = None  # None means auto-detect
    save_interval: int = 10  # Save progress every N pages
    reverse: bool = False  # Scrape from last page (oldest) to first (newest)


class TelegramConfig(BaseModel):
    """Telegram upload configuration."""

    upload_service_url: str = "http://localhost:8000"
    tenant_id: str | None = None
    caption_template: str = "<b>{title}</b>\n\n{description}\n\nDuration: {duration}"  # Variables: {title}, {slug}, {description}, {duration}
    parse_mode: str = "HTML"
    # Path mapping for Docker integration: local_path -> container_path
    # Example: {"data/downloads": "/app/data/downloads"}
    file_path_map: dict[str, str] = {}


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EROASMR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    http: HttpConfig = HttpConfig()
    db: DatabaseConfig = DatabaseConfig()
    scraper: ScraperConfig = ScraperConfig()
    telegram: TelegramConfig = TelegramConfig()

    # Logging
    log_level: str = "INFO"


# Global settings instance
settings = Settings()
