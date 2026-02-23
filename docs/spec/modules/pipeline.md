# 管道模块 (pipeline.py, parallel_pipeline.py)

## 1. 概述

管道模块负责协调下载和上传流程，提供两种模式：
- **顺序管道** (pipeline.py): 下载后立即上传
- **并行管道** (parallel_pipeline.py): 生产者-消费者模式

## 2. 顺序管道 (DownloadUploadPipeline)

### 2.1 类设计

```python
class DownloadUploadPipeline:
    def __init__(
        self,
        storage: VideoStorage,
        downloader: VideoDownloader,
        uploaders: list[Uploader],
        delete_after_upload: bool = True,
        min_free_space_gb: float = 5.0,
        max_pending_files: int = 3,
    ):
        self.storage = storage
        self.downloader = downloader
        self.uploaders = [u for u in uploaders if u.is_ready()]
        self.delete_after_upload = delete_after_upload
        self.min_free_space_gb = min_free_space_gb
        self.max_pending_files = max_pending_files
```

### 2.2 执行流程

```python
def process_all(self, limit: int | None = None) -> dict:
    """顺序处理所有待下载视频"""
    pending = self.storage.get_pending_downloads(limit)

    for slug in pending:
        # 1. 检查磁盘空间
        if self._get_disk_free_gb() < self.min_free_space_gb:
            break

        # 2. 下载
        success, error = self.downloader.download_video(slug)

        if not success:
            continue

        # 3. 上传到所有配置的上传器
        file_path = self.downloader.output_dir / f"{slug}.mp4"
        for uploader in self.uploaders:
            result = uploader.upload(file_path, slug)

            if result.success:
                # 记录存储位置
                self.storage.add_storage_location(...)

        # 4. 清理
        if self.delete_after_upload:
            file_path.unlink()
```

### 2.3 特点

- 简单可靠
- 内存占用低
- 顺序执行，易于调试
- 适合少量文件

## 3. 并行管道 (ParallelPipeline)

### 3.1 类设计

```python
class ParallelPipeline:
    def __init__(
        self,
        storage: VideoStorage,
        downloader: VideoDownloader,
        uploaders: list[Uploader],
        download_queue_size: int = 10,
        upload_queue_size: int = 20,
        upload_workers: int = 3,
        max_pending_uploads: int = 50,
        min_disk_free_gb: float = 5.0,
        delete_after_upload: bool = True,
        delete_only_if_all_success: bool = True,
    ):
        # 队列
        self.download_queue = asyncio.Queue(maxsize=download_queue_size)
        self.upload_queue = asyncio.Queue(maxsize=upload_queue_size)

        # 上传结果追踪
        self._upload_results: dict[str, dict[str, UploadResult]] = {}
        self._results_lock = asyncio.Lock()

        # 统计
        self.stats = PipelineStats()
```

### 3.2 数据模型

```python
@dataclass
class DownloadTask:
    """下载完成的任务"""
    slug: str
    file_path: Path
    file_size: int
    thumbnail_path: Path | None = None
    audio_path: Path | None = None  # 助眠网音频
    error: str | None = None

@dataclass
class UploadTask:
    """待上传的任务"""
    slug: str
    file_path: Path
    uploader: Uploader
    thumbnail_path: Path | None = None
    site_id: str = "eroasmr"

@dataclass
class PipelineStats:
    """统计信息"""
    total: int = 0
    downloaded: int = 0
    download_failed: int = 0
    uploaded: int = 0
    upload_failed: int = 0
    files_deleted: int = 0
```

### 3.3 执行流程

```
┌────────────────────────────────────────────────────────────────────┐
│                     Parallel Pipeline                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────┐                                                │
│  │ _download_     │  Producer                                      │
│  │ producer       │                                                │
│  └───────┬────────┘                                                │
│          │                                                         │
│          ▼  DownloadTask                                           │
│  ┌────────────────┐                                                │
│  │ download_queue │  asyncio.Queue(maxsize=10)                     │
│  └───────┬────────┘                                                │
│          │                                                         │
│          ▼                                                         │
│  ┌────────────────┐                                                │
│  │ _download_to_  │  Dispatcher                                    │
│  │ upload_        │  - 创建视频上传任务                             │
│  │ dispatcher     │  - 创建音频上传任务（如果有）                    │
│  └───────┬────────┘                                                │
│          │                                                         │
│          ▼  UploadTask                                             │
│  ┌────────────────┐                                                │
│  │ upload_queue   │  asyncio.Queue(maxsize=20)                     │
│  └───────┬────────┘                                                │
│          │                                                         │
│          ├─────────────────┬─────────────────┐                     │
│          ▼                 ▼                 ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │_upload_      │  │_upload_      │  │_upload_      │  Consumers  │
│  │consumer #1   │  │consumer #2   │  │consumer #3   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 3.4 生产者 (下载)

```python
async def _download_producer(self, slugs, progress, task_id):
    """下载生产者"""
    for slug in slugs:
        # 检查暂停文件
        while self._is_paused():
            await asyncio.sleep(10)

        # 检查磁盘空间
        if self._get_disk_free_gb() < self.min_disk_free_gb:
            # 等待上传释放空间
            while self._get_disk_free_gb() < self.min_disk_free_gb:
                await asyncio.sleep(10)

        # 检查待上传数量
        if self._get_pending_upload_count() >= self.max_pending_uploads:
            while self._get_pending_upload_count() >= self.max_pending_uploads:
                await asyncio.sleep(5)

        # 在线程池中执行下载
        loop = asyncio.get_event_loop()
        success, error = await loop.run_in_executor(
            None,
            lambda: self.downloader.download_video(slug, include_audio=True)
        )

        if success:
            task = DownloadTask(slug=slug, file_path=..., ...)
            await self.download_queue.put(task)

    # 发送结束信号
    await self.download_queue.put(None)
```

### 3.5 调度器

```python
async def _download_to_upload_dispatcher(self):
    """将下载任务转换为上传任务"""
    while True:
        task = await self.download_queue.get()

        if task is None:
            # 结束信号，通知所有消费者
            for _ in self.uploaders:
                for _ in range(self.upload_workers):
                    await self.upload_queue.put(None)
            break

        # 获取 site_id
        video = self.storage.get_video_by_slug(task.slug)
        site_id = video.get("site_id", "eroasmr") if video else "eroasmr"

        # 创建视频上传任务
        for uploader in self.uploaders:
            upload_task = UploadTask(
                slug=task.slug,
                file_path=task.file_path,
                uploader=uploader,
                site_id=site_id,
            )
            await self.upload_queue.put(upload_task)

        # 创建音频上传任务（助眠网）
        if task.audio_path and task.audio_path.exists():
            for uploader in self.uploaders:
                audio_task = UploadTask(
                    slug=f"{task.slug}_audio",
                    file_path=task.audio_path,
                    uploader=uploader,
                    site_id=site_id,
                )
                await self.upload_queue.put(audio_task)
```

### 3.6 消费者 (上传)

```python
async def _upload_consumer(self, uploader, progress, task_id):
    """上传消费者"""
    while True:
        task = await self.upload_queue.get()

        if task is None:
            break

        # 在线程池中执行上传
        result = await loop.run_in_executor(
            None,
            lambda: uploader.upload(task.file_path, task.slug, ...)
        )

        # 记录结果
        async with self._results_lock:
            if task.slug not in self._upload_results:
                self._upload_results[task.slug] = {}
            self._upload_results[task.slug][uploader.storage_type] = result

        if result.success:
            # 记录存储位置
            self.storage.add_storage_location(...)
            self.stats.uploaded += 1
        else:
            self.stats.upload_failed += 1

        # 检查是否可以删除文件
        await self._maybe_delete_file(task.slug, task.file_path)
```

## 4. 背压控制

### 4.1 磁盘空间监控

```python
def _get_disk_free_gb(self) -> float:
    import shutil
    stat = shutil.disk_usage(self.downloader.output_dir)
    return stat.free / (1024 ** 3)
```

### 4.2 暂停文件

```python
def _get_pause_file(self) -> Path:
    return self.downloader.output_dir.parent / ".pause_downloads"

def _is_paused(self) -> bool:
    return self._get_pause_file().exists()
```

外部监控脚本可以创建 `.pause_downloads` 文件来暂停下载。

### 4.3 待上传计数

```python
def _get_pending_upload_count(self) -> int:
    return self.stats.downloaded - self.stats.uploaded - self.stats.upload_failed
```

## 5. 文件清理

```python
async def _maybe_delete_file(self, slug, file_path, thumbnail_path=None):
    """在条件满足时删除文件"""
    if not self.delete_after_upload:
        return

    async with self._results_lock:
        results = self._upload_results.get(slug, {})

        # 检查是否所有上传器都完成了
        if len(results) < len(self.uploaders):
            return

        # 确定是否删除
        if self.delete_only_if_all_success:
            should_delete = all(r.success for r in results.values())
        else:
            should_delete = any(r.success for r in results.values())

        if should_delete and file_path.exists():
            file_path.unlink()
            self.stats.files_deleted += 1
```

## 6. 运行入口

```python
async def run(self, limit: int | None = None, retry_failed: bool = False) -> dict:
    """运行并行管道"""
    slugs = self.storage.get_pending_downloads(limit=limit, include_failed=retry_failed)
    self.stats.total = len(slugs)

    with Progress(...) as progress:
        tasks = [
            asyncio.create_task(self._download_producer(slugs, progress, dl_task)),
            asyncio.create_task(self._download_to_upload_dispatcher()),
            # 多个上传消费者
            *[asyncio.create_task(self._upload_consumer(u, progress, task_id))
              for u in self.uploaders
              for _ in range(self.upload_workers)]
        ]
        await asyncio.gather(*tasks)

    return self.stats.to_dict()
```

## 7. 对比

| 特性 | 顺序管道 | 并行管道 |
|------|---------|---------|
| 下载并发 | 1 | 1 |
| 上传并发 | 1 | N workers |
| 内存占用 | 低 | 中等 |
| 实现复杂度 | 简单 | 复杂 |
| 适用场景 | 少量文件 | 大量文件 |
| 吞吐量 | 低 | 高 |
