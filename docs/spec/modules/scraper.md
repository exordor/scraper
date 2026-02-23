# 爬虫模块 (sites/)

## 1. 概述

爬虫模块采用工厂模式设计，支持多站点扩展：

```
sites/
├── __init__.py
├── eroasmr/
│   ├── __init__.py
│   ├── models.py      # 数据模型
│   ├── parser.py      # HTML 解析
│   └── scraper.py     # 爬虫实现
└── zhumianwang/
    ├── __init__.py
    ├── models.py
    ├── parser.py
    ├── play_parser.py # 播放页解析
    └── scraper.py
```

## 2. 基类设计

### 2.1 BaseSiteParser

```python
# base/parser.py
from abc import ABC, abstractmethod

class BaseSiteParser(ABC):
    """站点解析器基类"""

    @abstractmethod
    def parse_video_list(self, html: str) -> list[dict]:
        """解析视频列表页"""
        pass

    @abstractmethod
    def parse_video_detail(self, html: str) -> dict:
        """解析视频详情页"""
        pass

    @abstractmethod
    def parse_video_source(self, html: str) -> str | None:
        """解析视频源地址"""
        pass
```

### 2.2 BaseSiteScraper

```python
# base/scraper.py
from abc import ABC, abstractmethod

class BaseSiteScraper(ABC):
    """站点爬虫基类"""

    def __init__(self, storage: VideoStorage):
        self.storage = storage
        self.parser = self._get_parser()

    @abstractmethod
    def _get_parser(self) -> BaseSiteParser:
        """获取解析器实例"""
        pass

    @abstractmethod
    async def scrape_list_page(
        self,
        client: httpx.AsyncClient,
        page: int
    ) -> list[BaseVideo]:
        """爬取列表页"""
        pass

    @abstractmethod
    async def scrape_detail_page(
        self,
        client: httpx.AsyncClient,
        video: dict
    ) -> dict | None:
        """爬取详情页"""
        pass

    async def scrape_full(
        self,
        start_page: int = 1,
        end_page: int | None = None
    ) -> None:
        """完整爬取流程"""
        # 1. 爬取列表页
        # 2. 爬取详情页
        # 3. 保存到数据库
        pass
```

## 3. EroAsmr 实现

### 3.1 数据模型

```python
# sites/eroasmr/models.py
from pydantic import BaseModel
from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail

class EroAsmrVideo(BaseVideo):
    """EroAsmr 视频列表项"""
    slug: str
    title: str
    thumbnail_url: str
    duration: str
    view_count: int
    like_count: int

class EroAsmrVideoDetail(BaseVideoDetail):
    """EroAsmr 视频详情"""
    slug: str
    title: str
    thumbnail_url: str
    duration: str
    duration_seconds: int
    view_count: int
    like_count: int
    comment_count: int
    author: str
    excerpt: str
    description: str
    download_url: str | None

class EroAsmrTag(BaseModel):
    slug: str
    name: str
    count: int

class EroAsmrCategory(BaseModel):
    slug: str
    name: str

class RelatedVideo(BaseModel):
    slug: str
    title: str
    thumbnail_url: str
    duration: str
```

### 3.2 解析器

```python
# sites/eroasmr/parser.py
from bs4 import BeautifulSoup

class EroAsmrParser(BaseSiteParser):
    def parse_video_list(self, html: str) -> list[EroAsmrVideo]:
        soup = BeautifulSoup(html, 'lxml')
        videos = []

        for item in soup.select('.video-item'):
            video = EroAsmrVideo(
                slug=self._extract_slug(item),
                title=item.select_one('.title').text.strip(),
                thumbnail_url=item.select_one('img')['src'],
                duration=item.select_one('.duration').text,
                view_count=self._parse_count(item, '.views'),
                like_count=self._parse_count(item, '.likes'),
            )
            videos.append(video)

        return videos

    def parse_video_detail(self, html: str) -> EroAsmrVideoDetail:
        soup = BeautifulSoup(html, 'lxml')

        return EroAsmrVideoDetail(
            slug=self._extract_slug(soup),
            title=soup.select_one('h1').text.strip(),
            # ... 其他字段解析
            download_url=self._extract_video_url(soup),
        )

    def _extract_video_url(self, soup: BeautifulSoup) -> str | None:
        # 从 script 标签或 source 元素提取
        source = soup.select_one('video source')
        return source['src'] if source else None
```

### 3.3 爬虫

```python
# sites/eroasmr/scraper.py
class EroAsmrScraper(BaseSiteScraper):
    def _get_parser(self) -> EroAsmrParser:
        return EroAsmrParser()

    async def scrape_list_page(
        self,
        client: httpx.AsyncClient,
        page: int
    ) -> list[EroAsmrVideo]:
        url = f"{settings.http.base_url}/page/{page}/"
        response = await client.get(url)
        return self.parser.parse_video_list(response.text)

    async def scrape_detail_page(
        self,
        client: httpx.AsyncClient,
        video: dict
    ) -> dict | None:
        url = f"{settings.http.base_url}/video/{video['slug']}/"
        response = await client.get(url)
        return self.parser.parse_video_detail(response.text).model_dump()
```

## 4. Zhumianwang 实现

### 4.1 特殊处理

助眠网需要额外处理：

1. **认证**: 需要 Cookie 才能访问
2. **代理**: CDN 需要通过香港代理访问
3. **音频**: 有独立的音频文件

### 4.2 Play Parser

```python
# sites/zhumianwang/play_parser.py
class ZhumianwangPlayParser:
    """解析播放页获取下载链接"""

    def parse_play_page(self, html: str) -> PlayPageResult:
        soup = BeautifulSoup(html, 'lxml')

        # 从 JavaScript 中提取下载链接
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'downloadUrl' in script.string:
                video_url = self._extract_url(script.string, 'video')
                audio_url = self._extract_url(script.string, 'audio')
                return PlayPageResult(
                    video_download_url=video_url,
                    audio_download_url=audio_url,
                )

        return PlayPageResult()

    def _extract_url(self, js_content: str, media_type: str) -> str | None:
        # 正则匹配下载链接
        import re
        pattern = rf'{media_type}Url["\']?\s*[:=]\s*["\']([^"\']+)["\']'
        match = re.search(pattern, js_content)
        return match.group(1) if match else None
```

### 4.3 认证处理

```python
# auth/playwright_auth.py
from playwright.async_api import async_playwright

async def get_zhumianwang_cookies() -> list[dict]:
    """使用 Playwright 获取登录 Cookie"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 导航到登录页面
        await page.goto('https://zhumianwang.com/login')

        # 等待用户手动登录或使用保存的会话
        # ...

        cookies = await context.cookies()
        await browser.close()

        return cookies
```

## 5. 工厂模式

### 5.1 ScraperFactory

```python
# factory.py
_scraper_registry: dict[str, type[BaseSiteScraper]] = {}

def register_scraper(site_id: str):
    """装饰器：注册爬虫"""
    def decorator(cls):
        _scraper_registry[site_id] = cls
        return cls
    return decorator

class ScraperFactory:
    @staticmethod
    def create(site_id: str, storage: VideoStorage) -> BaseSiteScraper:
        """创建爬虫实例"""
        if site_id not in _scraper_registry:
            raise ValueError(f"Unknown site: {site_id}")

        return _scraper_registry[site_id](storage)

    @staticmethod
    def list_sites() -> list[str]:
        """列出所有可用站点"""
        return list(_scraper_registry.keys())
```

### 5.2 注册爬虫

```python
# sites/zhumianwang/scraper.py
@register_scraper("zhumianwang")
class ZhumianwangScraper(BaseSiteScraper):
    # ...

# sites/eroasmr/scraper.py
@register_scraper("eroasmr")
class EroAsmrScraper(BaseSiteScraper):
    # ...
```

## 6. 扩展新站点

### 6.1 步骤

1. 创建站点目录: `sites/newsite/`
2. 定义数据模型: `models.py`
3. 实现解析器: `parser.py`
4. 实现爬虫: `scraper.py`
5. 注册爬虫: 使用 `@register_scraper("newsite")`
6. 添加配置: 在 `config.py` 中添加站点配置

### 6.2 模板

```python
# sites/newsite/models.py
from eroasmr_scraper.base.models import BaseVideo, BaseVideoDetail

class NewSiteVideo(BaseVideo):
    # 站点特有字段
    pass

class NewSiteVideoDetail(BaseVideoDetail):
    # 站点特有字段
    pass

# sites/newsite/scraper.py
@register_scraper("newsite")
class NewSiteScraper(BaseSiteScraper):
    def _get_parser(self):
        return NewSiteParser()

    async def scrape_list_page(self, client, page):
        # 实现列表页爬取
        pass

    async def scrape_detail_page(self, client, video):
        # 实现详情页爬取
        pass
```

## 7. 错误处理

### 7.1 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| HTTP 403 | 被反爬 | 增加延迟、更换 UA |
| HTTP 404 | 页面不存在 | 跳过、记录 |
| 超时 | 网络问题 | 重试 |
| 解析失败 | 页面结构变化 | 记录、告警 |

### 7.2 Failed URLs 记录

```python
def record_failed_url(self, url: str, error: str) -> None:
    """记录失败的 URL"""
    self.storage.db["failed_urls"].insert({
        "url": url,
        "error": error,
        "failed_at": datetime.now().isoformat(),
        "site_id": self.storage.site_id,
    })
```
