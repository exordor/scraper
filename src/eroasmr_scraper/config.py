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


class PipelineConfig(BaseModel):
    """Pipeline configuration for download/upload."""

    # Disk space management
    min_free_space_gb: float = Field(default=5.0, description="Minimum free space in GB before pausing downloads")
    max_disk_usage_percent: float = Field(default=90.0, description="Maximum disk usage percentage before pausing")
    max_pending_files: int = Field(default=3, description="Maximum files waiting for upload before pausing downloads")

    # Parallel processing
    max_upload_workers: int = Field(default=2, description="Number of parallel upload threads")
    use_parallel: bool = Field(default=True, description="Use parallel upload mode")

    # Cleanup
    delete_after_upload: bool = Field(default=True, description="Delete local files after successful upload")
    delete_only_if_all_success: bool = Field(default=True, description="Only delete when ALL uploads succeed")


class TelegramConfig(BaseModel):
    """Telegram upload configuration."""

    upload_service_url: str = "http://localhost:8000"
    tenant_id: str | None = None  # Legacy: single tenant ID
    tenant_ids: list[str] = []  # Multiple tenant IDs for round-robin load balancing
    caption_template: str = "<b>{title}</b>\n\n{description}\n\nDuration: {duration}"  # Variables: {title}, {slug}, {description}, {duration}
    parse_mode: str = "HTML"
    # Path mapping for Docker integration: local_path -> container_path
    # Maps downloads to telegram-upload-service container path
    file_path_map: dict[str, str] = {"/root/telegram-upload-service/data/downloads": "/app/data/downloads"}


class EroAsmrSiteConfig(BaseModel):
    """EroAsmr site-specific configuration."""

    enabled: bool = True
    base_url: str = "https://eroasmr.com"
    http: HttpConfig = HttpConfig()


class ZhumianwangSiteConfig(BaseModel):
    """Zhumianwang site-specific configuration."""

    enabled: bool = True
    base_url: str = "https://www.zhumianzhan.com"
    http: HttpConfig = HttpConfig(base_url="https://www.zhumianzhan.com")
    # Playwright authentication for download links
    requires_auth: bool = True
    cookie_domain: str = ".www.zhumianzhan.com"


class SitesConfig(BaseModel):
    """Multi-site configuration."""

    eroasmr: EroAsmrSiteConfig = EroAsmrSiteConfig()
    zhumianwang: ZhumianwangSiteConfig = ZhumianwangSiteConfig()


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SCRAPER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Multi-site configuration
    sites: SitesConfig = SitesConfig()
    default_site: str = "eroasmr"

    # Legacy support - these now delegate to sites.eroasmr
    http: HttpConfig = HttpConfig()
    db: DatabaseConfig = DatabaseConfig()
    scraper: ScraperConfig = ScraperConfig()
    telegram: TelegramConfig = TelegramConfig()
    pipeline: PipelineConfig = PipelineConfig()

    # Logging
    log_level: str = "INFO"

    def get_site_config(self, site_id: str) -> EroAsmrSiteConfig | ZhumianwangSiteConfig:
        """Get configuration for a specific site.

        Args:
            site_id: Site identifier (e.g., 'eroasmr', 'zhumianwang')

        Returns:
            Site configuration object
        """
        if site_id == "zhumianwang":
            return self.sites.zhumianwang
        return self.sites.eroasmr


# Global settings instance
settings = Settings()
