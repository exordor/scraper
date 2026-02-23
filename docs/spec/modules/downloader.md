# 下载模块 (downloader.py)

## 1. 概述

VideoDownloader 负责从视频站点下载视频文件，支持：
- 多站点下载（EroAsmr、助眠网）
- 代理访问（助眠网 CDN）
- 认证支持（Cookie）
- 进度显示
- 断点续传（通过归档文件）

## 2. VideoDownloader 类

### 2.1 初始化

```python
class VideoDownloader:
    def __init__(
        self,
        storage: VideoStorage,
        output_dir: Path,
        archive_file: Path | None = None,
        sleep_interval: tuple[float, float] = (2.0, 4.0),
        progress: Progress | None = None,
    ):
        self.storage = storage
        self.output_dir = output_dir
        self.archive_file = archive_file or output_dir.parent / "download_archive.txt"
        self.sleep_interval = sleep_interval
        self.progress = progress
        self._archive: set[str] = set()

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 加载归档
        self._load_archive()
```

### 2.2 核心方法

```python
def download_video(
    self,
    slug: str,
    task_id: int | None = None,
    include_audio: bool = False
) -> tuple[bool, str | None]:
    """下载单个视频

    Args:
        slug: 视频 slug
        task_id: Rich progress task ID
        include_audio: 是否下载音频（助眠网）

    Returns:
        (success, error_message)
    """
```

## 3. 代理配置

### 3.1 香港代理

助眠网的 CDN（video.zklhy.com）在中国大陆，美国服务器无法直接访问，需要通过香港代理：

```python
# 代理服务器配置
ZHUMIANWANG_PROXY = "http://202.155.141.121:3128"

def _download_file(self, client, url, output_path, task_id, use_proxy=False):
    download_client = client

    if use_proxy and "video.zklhy.com" in url:
        download_client = httpx.Client(
            proxy=ZHUMIANWANG_PROXY,
            timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0),
            follow_redirects=True,
        )
        logger.info("Using HK proxy for zhumianwang CDN: %s", url[:60])
```

### 3.2 代理服务器配置

香港服务器 Squid 配置：

```
# /etc/squid/squid.conf
http_port 3128
acl allowed_clients src 104.234.26.3  # 美国服务器 IP
http_access allow allowed_clients
http_access deny all
cache deny all
```

## 4. 助眠网特殊处理

### 4.1 播放页解析

助眠网的下载链接不在视频详情页，需要访问播放页获取：

```python
def _fetch_zhumianwang_play_page(self, play_url: str) -> tuple[str | None, str | None]:
    """获取助眠网下载链接

    Args:
        play_url: 播放页 URL（如 /v_play/xxx.html）

    Returns:
        (video_url, audio_url)
    """
    cookies = _load_zhumianwang_cookies()

    # 构建完整 URL
    if not play_url.startswith("http"):
        play_url = f"https://zhumianwang.com{play_url}"

    response = client.get(play_url, cookies=cookies, headers=headers)

    # 解析下载链接
    parser = ZhumianwangPlayParser()
    result = parser.parse_play_page(response.text)

    return result.video_download_url, result.audio_download_url
```

### 4.2 Cookie 管理

```python
def _load_zhumianwang_cookies() -> dict | None:
    """从 cookies.json 加载助眠网 Cookie"""
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "data" / "cookies.json",
        Path.cwd() / "data" / "cookies.json",
        Path("/root/eroasmr-scraper/data/cookies.json"),
    ]

    for path in possible_paths:
        if path.exists():
            cookies_list = json.loads(path.read_text())
            return {
                c["name"]: c["value"]
                for c in cookies_list
                if "zhumianwang.com" in c.get("domain", "")
            }
    return None
```

### 4.3 音频下载

助眠网有独立的音频文件：

```python
# 在 download_video 中
if include_audio and audio_url and site_id == "zhumianwang":
    audio_path = self.output_dir / f"{slug}.mp3"
    logger.info("Downloading audio: %s", slug)
    audio_success, audio_error = self._download_file(
        client, audio_url, audio_path, task_id, use_proxy=True
    )

    if not audio_success:
        logger.warning("Failed to download audio for %s: %s", slug, audio_error)
        # 不失败整个下载，只记录警告
        audio_path = None
```

## 5. 下载流程

### 5.1 流程图

```
┌─────────────────┐
│    开始下载     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 检查是否在归档  │────►│  是：跳过       │
└────────┬────────┘     └─────────────────┘
         │ 否
         ▼
┌─────────────────┐
│ 获取视频元数据  │
│ (从数据库)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 标记为下载中    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 判断站点类型    │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│EroAsmr│ │助眠网 │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
┌───────┐ ┌───────────────┐
│直接提取│ │解析播放页获取 │
│视频URL │ │视频+音频URL   │
└───┬───┘ └───────┬───────┘
    │             │
    └──────┬──────┘
           ▼
┌─────────────────┐
│   下载视频文件  │
│  (可能用代理)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 下载音频文件    │
│ (助眠网，可选)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   下载缩略图    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   标记完成      │
│   更新数据库    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   添加到归档    │
└─────────────────┘
```

## 6. 错误处理

### 6.1 下载失败

```python
if not success:
    self.storage.mark_failed(slug, error)
    # 清理部分下载的文件
    if output_path.exists():
        output_path.unlink()
    return False, error
```

### 6.2 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| HTTP 403 | CDN 拒绝 | 检查代理配置 |
| HTTP 404 | 文件不存在 | 标记失败 |
| 超时 | 网络问题 | 重试 |
| 磁盘空间不足 | 存储满 | 清理或等待 |
| 不完整下载 | 连接中断 | 重试 |

## 7. 进度显示

```python
def download_all(self, limit=None, retry_failed=False):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        self.progress = progress

        for slug in pending:
            task = progress.add_task(f"[cyan]{slug[:40]}[/cyan]")
            success, error = self.download_video(slug, task)

            if success:
                progress.update(task, description=f"[green]✓[/green] {slug}")
            else:
                progress.update(task, description=f"[red]✗[/red] {slug}: {error}")
```

## 8. 缩略图下载

```python
def download_thumbnail(self, slug: str) -> Path | None:
    """下载缩略图

    缩略图会被调整为最大 320px（Telegram Bot API 要求）

    Args:
        slug: 视频 slug

    Returns:
        缩略图路径或 None
    """
    video = self.storage.get_video_by_slug(slug)
    if not video or not video.get("thumbnail_url"):
        return None

    output_path = self.output_dir / f"{slug}_thumb.jpg"

    # 跳过已存在的
    if output_path.exists():
        return output_path

    response = client.get(thumbnail_url, follow_redirects=True)

    # 调整大小
    img = Image.open(io.BytesIO(response.content))
    max_dimension = 320
    if max(img.size) > max_dimension:
        ratio = max_dimension / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # 转换为 RGB（JPEG 需要）
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.save(output_path, "JPEG", quality=85)
    return output_path
```

## 9. 归档机制

```python
def _load_archive(self):
    """加载归档文件到内存"""
    if self.archive_file.exists():
        with open(self.archive_file) as f:
            self._archive = set(line.strip() for line in f if line.strip())

def _save_to_archive(self, slug: str):
    """添加 slug 到归档"""
    self._archive.add(slug)
    with open(self.archive_file, "a") as f:
        f.write(f"{slug}\n")

def _is_in_archive(self, slug: str) -> bool:
    """检查是否已在归档中"""
    return slug in self._archive
```

## 10. 配置参数

| 参数 | 默认值 | 描述 |
|------|--------|------|
| output_dir | data/downloads | 输出目录 |
| archive_file | download_archive.txt | 归档文件 |
| sleep_interval | (2.0, 4.0) | 下载间隔范围（秒） |
| timeout | 300s | 下载超时 |
