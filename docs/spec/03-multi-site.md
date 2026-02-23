# 多站点支持设计

## 1. 概述

eroasmr-scraper 采用可扩展的多站点架构，支持从不同的视频站点抓取内容。当前支持两个站点：

- **EroAsmr** (eroasmr.com) - 主要站点
- **助眠网** (zhumianwang.com) - 中国站点，需要特殊处理

## 2. 架构设计

### 2.1 继承体系

```
BaseModel (Pydantic)
├── BaseVideo
│   ├── EroAsmrVideo
│   └── ZhumianwangVideo
├── BaseVideoDetail
│   ├── EroAsmrVideoDetail
│   └── ZhumianwangVideoDetail
├── BaseTag
│   ├── EroAsmrTag
│   └── ZhumianwangTag
└── BaseCategory
    ├── EroAsmrCategory
    └── ZhumianwangCategory

BaseSiteParser (ABC)
├── EroAsmrParser
└── ZhumianwangParser
    └── ZhumianwangPlayParser (播放页解析)

BaseSiteScraper (ABC)
├── EroAsmrScraper
└── ZhumianwangScraper
```

### 2.2 目录结构

```
src/eroasmr_scraper/sites/
├── __init__.py
├── base/
│   ├── __init__.py
│   ├── scraper.py      # BaseSiteScraper
│   ├── parser.py       # BaseSiteParser
│   └── models.py       # BaseVideo, BaseVideoDetail, etc.
├── eroasmr/
│   ├── __init__.py
│   ├── scraper.py      # EroAsmrScraper
│   ├── parser.py       # EroAsmrParser
│   └── models.py       # EroAsmrVideo, etc.
└── zhumianwang/
    ├── __init__.py
    ├── scraper.py      # ZhumianwangScraper
    ├── parser.py       # ZhumianwangParser
    ├── play_parser.py  # 播放页解析器
    ├── models.py       # ZhumianwangVideo, etc.
    └── auth/
        └── playwright_auth.py  # 认证辅助
```

## 3. 基类定义

### 3.1 BaseVideo

```python
from pydantic import BaseModel
from datetime import datetime

class BaseVideo(BaseModel):
    """视频基础信息（列表页）"""

    slug: str                      # URL 标识
    title: str                     # 标题
    thumbnail_url: str | None      # 缩略图
    duration: str | None           # 时长
    view_count: int | None         # 观看数
    like_count: int | None         # 点赞数
    author: str | None             # 作者
    excerpt: str | None            # 摘要
    site_id: str                   # 站点 ID
    tags: list[str] = []           # 标签列表
    categories: list[str] = []     # 分类列表
```

### 3.2 BaseVideoDetail

```python
class BaseVideoDetail(BaseVideo):
    """视频详情（详情页）"""

    description: str | None        # 完整描述
    play_url: str | None           # 播放页 URL
    download_url: str | None       # 下载链接
    audio_download_url: str | None # 音频下载链接（助眠网）
    created_at: datetime | None    # 发布时间
    detail_scraped_at: datetime | None  # 详情抓取时间
```

### 3.3 BaseSiteScraper

```python
from abc import ABC, abstractmethod
from typing import Iterator

class BaseSiteScraper(ABC):
    """站点爬虫基类"""

    def __init__(
        self,
        site_id: str,
        base_url: str,
        http_config: HttpConfig,
    ):
        self.site_id = site_id
        self.base_url = base_url
        self.http_config = http_config
        self._client: httpx.Client | None = None

    @property
    @abstractmethod
    def site_name(self) -> str:
        """站点名称"""
        pass

    @abstractmethod
    def scrape_video_list(self, page: int) -> list[BaseVideo]:
        """抓取视频列表页"""
        pass

    @abstractmethod
    def scrape_video_detail(self, slug: str) -> BaseVideoDetail | None:
        """抓取视频详情页"""
        pass

    def full_scrape(
        self,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> Iterator[BaseVideoDetail]:
        """完整爬取流程"""
        # 1. 抓取列表页获取基本视频信息
        # 2. 抓取详情页获取完整信息
        # 3. 保存到数据库
        pass
```

### 3.4 BaseSiteParser

```python
class BaseSiteParser(ABC):
    """HTML 解析器基类"""

    @abstractmethod
    def parse_video_list(self, html: str) -> list[BaseVideo]:
        """解析视频列表页"""
        pass

    @abstractmethod
    def parse_video_detail(self, html: str) -> BaseVideoDetail | None:
        """解析视频详情页"""
        pass

    @abstractmethod
    def get_max_page(self, html: str) -> int:
        """获取最大页数"""
        pass
```

## 4. 站点差异

### 4.1 EroAsmr

```python
class EroAsmrScraper(BaseSiteScraper):
    site_id = "eroasmr"
    site_name = "EroAsmr"
    base_url = "https://eroasmr.com"

    # 特点：
    # - 无需认证
    # - 下载链接直接在详情页
    # - 标准的列表/详情页结构
```

**页面结构**:
- 列表页: `/page/{n}`
- 详情页: `/{slug}.html`
- 下载链接: 详情页直接包含

### 4.2 助眠网

```python
class ZhumianwangScraper(BaseSiteScraper):
    site_id = "zhumianwang"
    site_name = "助眠网"
    base_url = "https://zhumianwang.com"

    # 特点：
    # - 需要登录认证
    # - 下载链接在播放页，不在详情页
    # - 有独立的音频文件
    # - CDN 在中国，需要香港代理
```

**页面结构**:
- 列表页: `/video/list-0-{n}.html`
- 详情页: `/vdetail/{slug}.html`
- 播放页: `/v_play/{id}.html`
- CDN: `video.zklhy.com`（需要代理）

### 4.3 助眠网特殊处理

#### 播放页解析

```python
class ZhumianwangPlayParser:
    """解析助眠网播放页获取下载链接"""

    def parse_play_page(self, html: str) -> PlayPageResult:
        """
        从播放页提取:
        - video_download_url: 视频下载链接
        - audio_download_url: 音频下载链接
        """
        # 播放页包含 JavaScript 代码
        # 提取类似以下的 URL:
        # - https://video.zklhy.com/xxx.mp4
        # - https://video.zklhy.com/xxx.mp3
        pass
```

#### Cookie 认证

```python
def _load_zhumianwang_cookies() -> dict | None:
    """从 cookies.json 加载助眠网 Cookie"""
    cookies_list = json.loads(cookies_path.read_text())
    return {
        c["name"]: c["value"]
        for c in cookies_list
        if "zhumianwang.com" in c.get("domain", "")
    }
```

#### 香港代理

助眠网的 CDN 在中国大陆，美国服务器无法直接访问：

```python
ZHUMIANWANG_PROXY = "http://202.155.141.121:3128"  # 香港 Squid 代理

def _download_file(self, url, output_path, use_proxy=False):
    if use_proxy and "video.zklhy.com" in url:
        client = httpx.Client(
            proxy=ZHUMIANWANG_PROXY,
            timeout=httpx.Timeout(connect=30.0, read=600.0),
        )
```

## 5. 工厂模式

### 5.1 ScraperFactory

```python
class ScraperFactory:
    """爬虫工厂"""

    _scrapers: dict[str, type[BaseSiteScraper]] = {}

    @classmethod
    def register(cls, site_id: str, scraper_class: type[BaseSiteScraper]):
        """注册爬虫"""
        cls._scrapers[site_id] = scraper_class

    @classmethod
    def create(cls, site_id: str, **kwargs) -> BaseSiteScraper:
        """创建爬虫实例"""
        if site_id not in cls._scrapers:
            raise ValueError(f"Unknown site: {site_id}")

        site_config = settings.get_site_config(site_id)
        return cls._scrapers[site_id](
            site_id=site_id,
            base_url=site_config.base_url,
            http_config=site_config.http,
            **kwargs
        )

    @classmethod
    def list_sites(cls) -> list[str]:
        """列出所有支持的站点"""
        return list(cls._scrapers.keys())
```

### 5.2 自动注册

```python
# 在 sites/__init__.py 中
from eroasmr_scraper.sites.eroasmr import EroAsmrScraper
from eroasmr_scraper.sites.zhumianwang import ZhumianwangScraper

ScraperFactory.register("eroasmr", EroAsmrScraper)
ScraperFactory.register("zhumianwang", ZhumianwangScraper)
```

## 6. 配置系统

### 6.1 站点配置结构

```python
class SitesConfig(BaseModel):
    """多站点配置"""
    eroasmr: EroAsmrSiteConfig = EroAsmrSiteConfig()
    zhumianwang: ZhumianwangSiteConfig = ZhumianwangSiteConfig()

class Settings(BaseSettings):
    sites: SitesConfig = SitesConfig()
    default_site: str = "eroasmr"

    def get_site_config(self, site_id: str) -> SiteConfig:
        """获取站点配置"""
        return getattr(self.sites, site_id)
```

### 6.2 环境变量

```bash
# 选择默认站点
SCRAPER_DEFAULT_SITE=zhumianwang

# 启用/禁用站点
SCRAPER_SITES__EROASMR__ENABLED=false
SCRAPER_SITES__ZHUMIANWANG__ENABLED=true

# 站点特定 HTTP 配置
SCRAPER_SITES__ZHUMIANWANG__HTTP__DELAY_MIN=2.0
SCRAPER_SITES__ZHUMIANWANG__HTTP__TIMEOUT_READ=60.0
```

## 7. CLI 集成

### 7.1 站点选择

```python
@app.command()
def scrape(
    site: str = typer.Option("eroasmr", "--site", "-s"),
    pages: int = typer.Option(1, "--pages", "-p"),
):
    scraper = ScraperFactory.create(site)
    # ...
```

### 7.2 命令示例

```bash
# 抓取 EroAsmr
uv run python main.py scrape --site eroasmr --pages 5

# 抓取助眠网
uv run python main.py scrape --site zhumianwang --pages 10

# 完整抓取（列表 + 详情）
uv run python main.py full --site zhumianwang --pages 5

# 下载并上传
uv run python main.py parallel --site zhumianwang --limit 50
```

## 8. 添加新站点

### 8.1 步骤

1. 创建站点目录: `src/eroasmr_scraper/sites/newsite/`
2. 实现数据模型: `models.py`
3. 实现解析器: `parser.py`
4. 实现爬虫: `scraper.py`
5. 添加配置: 更新 `config.py`
6. 注册工厂: 更新 `sites/__init__.py`

### 8.2 模板

```python
# sites/newsite/models.py
from eroasmr_scraper.sites.base.models import BaseVideo, BaseVideoDetail

class NewSiteVideo(BaseVideo):
    # 添加站点特有字段
    pass

class NewSiteVideoDetail(BaseVideoDetail):
    # 添加站点特有字段
    pass

# sites/newsite/parser.py
from eroasmr_scraper.sites.base.parser import BaseSiteParser

class NewSiteParser(BaseSiteParser):
    def parse_video_list(self, html: str) -> list[NewSiteVideo]:
        # 使用 BeautifulSoup 或 lxml 解析
        pass

    def parse_video_detail(self, html: str) -> NewSiteDetail | None:
        pass

# sites/newsite/scraper.py
from eroasmr_scraper.sites.base.scraper import BaseSiteScraper

class NewSiteScraper(BaseSiteScraper):
    site_id = "newsite"
    site_name = "New Site"
    base_url = "https://newsite.com"

    def scrape_video_list(self, page: int) -> list[BaseVideo]:
        pass

    def scrape_video_detail(self, slug: str) -> BaseVideoDetail | None:
        pass
```

## 9. 数据隔离

### 9.1 数据库

所有站点共用同一数据库，通过 `site_id` 字段区分：

```sql
SELECT * FROM videos WHERE site_id = 'zhumianwang';
SELECT * FROM downloads WHERE site_id = 'zhumianwang';
```

### 9.2 Storage 类

```python
class VideoStorage:
    def __init__(self, site_id: str = "eroasmr"):
        self.site_id = site_id

    def get_pending_downloads(self, limit=None):
        """获取待下载视频（按 site_id 过滤）"""
        query = "SELECT slug FROM videos WHERE site_id = ? AND ..."
        return self.db.query(query, [self.site_id])
```

## 10. 注意事项

### 10.1 站点特性对比

| 特性 | EroAsmr | 助眠网 |
|------|---------|--------|
| 需要认证 | 否 | 是 |
| 代理访问 | 否 | 是 (CDN) |
| 音频文件 | 无 | 有 |
| 播放页解析 | 不需要 | 需要 |
| 下载链接位置 | 详情页 | 播放页 |

### 10.2 常见问题

1. **认证过期**: 助眠网 Cookie 需要定期更新
2. **代理不稳定**: 香港代理可能偶尔超时
3. **CDN 限速**: 大文件下载可能被限速
4. **页面结构变化**: 需要定期检查解析器是否有效
