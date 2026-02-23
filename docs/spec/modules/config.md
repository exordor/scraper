# 配置系统 (config.py)

## 1. 概述

配置系统使用 Pydantic Settings 实现，支持：
- 类型安全的配置验证
- 环境变量覆盖
- 嵌套配置结构
- 默认值支持

## 2. 配置类结构

```python
Settings                          # 主配置类
├── sites: SitesConfig            # 多站点配置
│   ├── eroasmr: EroAsmrSiteConfig
│   │   └── http: HttpConfig
│   └── zhumianwang: ZhumianwangSiteConfig
│       └── http: HttpConfig
├── http: HttpConfig              # 通用 HTTP 配置
├── db: DatabaseConfig            # 数据库配置
├── scraper: ScraperConfig        # 爬虫配置
├── telegram: TelegramConfig      # Telegram 配置
├── pipeline: PipelineConfig      # 管道配置
├── default_site: str             # 默认站点
└── log_level: str                # 日志级别
```

## 3. 配置类详情

### 3.1 HttpConfig

```python
class HttpConfig(BaseModel):
    base_url: str = "https://eroasmr.com"
    delay_min: float = 1.5          # 最小请求延迟（秒）
    delay_max: float = 3.0          # 最大请求延迟（秒）
    timeout_connect: float = 5.0    # 连接超时
    timeout_read: float = 30.0      # 读取超时
    timeout_write: float = 5.0      # 写入超时
    timeout_pool: float = 10.0      # 连接池超时
    max_connections: int = 3        # 最大并发连接
    max_keepalive: int = 2          # 最大保持连接
    max_retries: int = 3            # 最大重试次数
    user_agent: str = "Mozilla/5.0 ..."
```

### 3.2 DatabaseConfig

```python
class DatabaseConfig(BaseModel):
    path: str = "data/videos.db"    # 数据库文件路径
    batch_size: int = 100           # 批量插入大小
```

### 3.3 ScraperConfig

```python
class ScraperConfig(BaseModel):
    start_page: int = 1             # 起始页
    end_page: int | None = None     # 结束页（None=自动检测）
    save_interval: int = 10         # 保存间隔（页）
    reverse: bool = False           # 是否从最后一页开始
```

### 3.4 PipelineConfig

```python
class PipelineConfig(BaseModel):
    min_free_space_gb: float = 5.0  # 最小剩余空间（GB）
    max_disk_usage_percent: float = 90.0  # 最大磁盘使用率
    max_pending_files: int = 3      # 最大等待上传文件数
    max_upload_workers: int = 2     # 上传工作线程数
    use_parallel: bool = True       # 使用并行模式
    delete_after_upload: bool = True  # 上传后删除本地文件
    delete_only_if_all_success: bool = True  # 仅全部成功时删除
```

### 3.5 TelegramConfig

```python
class TelegramConfig(BaseModel):
    upload_service_url: str = "http://localhost:8000"
    tenant_id: str | None = None    # 租户 ID
    caption_template: str = "<b>{title}</b>\n\n{description}\n\nDuration: {duration}"
    parse_mode: str = "HTML"
    file_path_map: dict[str, str] = {
        "/root/telegram-upload-service/data/downloads": "/app/data/downloads"
    }
```

### 3.6 站点配置

```python
class EroAsmrSiteConfig(BaseModel):
    enabled: bool = True
    base_url: str = "https://eroasmr.com"
    http: HttpConfig = HttpConfig()

class ZhumianwangSiteConfig(BaseModel):
    enabled: bool = True
    base_url: str = "https://zhumianwang.com"
    http: HttpConfig = HttpConfig(base_url="https://zhumianwang.com")
    requires_auth: bool = True
    cookie_domain: str = ".zhumianwang.com"
```

## 4. 环境变量

### 4.1 命名规则

```
SCRAPER__[SECTION]__[FIELD]
SCRAPER__[SITE]__[SECTION]__[FIELD]
```

### 4.2 示例

```bash
# 通用配置
SCRAPER_LOG_LEVEL=DEBUG
SCRAPER_DEFAULT_SITE=zhumianwang

# HTTP 配置
SCRAPER_HTTP__DELAY_MIN=2.0
SCRAPER_HTTP__DELAY_MAX=4.0
SCRAPER_HTTP__TIMEOUT_READ=60.0

# 数据库配置
SCRAPER_DB__PATH=data/videos.db

# Telegram 配置
SCRAPER_TELEGRAM__TENANT_ID=4d6e8863-4d30-4e65-9455-92b49d21b67c
SCRAPER_TELEGRAM__UPLOAD_SERVICE_URL=http://localhost:8000
SCRAPER_TELEGRAM__CAPTION_TEMPLATE=<b>{title}</b>

# 管道配置
SCRAPER_PIPELINE__MIN_FREE_SPACE_GB=10.0
SCRAPER_PIPELINE__MAX_UPLOAD_WORKERS=3
SCRAPER_PIPELINE__DELETE_AFTER_UPLOAD=false

# 站点特定配置
SCRAPER_SITES__ZHUMIANWANG__ENABLED=true
SCRAPER_SITES__ZHUMIANWANG__HTTP__DELAY_MIN=2.0
```

## 5. 使用方法

### 5.1 获取配置实例

```python
from eroasmr_scraper.config import settings

# 访问配置
print(settings.default_site)
print(settings.http.delay_min)
print(settings.telegram.tenant_id)

# 获取站点配置
site_config = settings.get_site_config("zhumianwang")
print(site_config.base_url)
```

### 5.2 在代码中使用

```python
class VideoDownloader:
    def __init__(self):
        # 使用配置
        self.delay = random.uniform(
            settings.http.delay_min,
            settings.http.delay_max
        )
        self.timeout = httpx.Timeout(
            connect=settings.http.timeout_connect,
            read=settings.http.timeout_read,
        )
```

## 6. 配置优先级

1. **环境变量** - 最高优先级
2. **.env 文件** - 次高优先级
3. **代码默认值** - 最低优先级

## 7. 验证

Pydantic 会自动验证配置类型：

```python
# 错误示例 - 会抛出 ValidationError
SCRAPER_HTTP__DELAY_MIN=not_a_number  # 类型错误
SCRAPER_PIPELINE__MAX_UPLOAD_WORKERS=-1  # 可能需要添加约束
```

## 8. 最佳实践

1. **敏感信息**: 使用环境变量，不要提交到代码库
2. **开发环境**: 使用 `.env` 文件
3. **生产环境**: 使用环境变量或配置管理工具
4. **文档化**: 在 `.env.example` 中记录所有可配置项
