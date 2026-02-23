# 已知问题与优化方向

## 1. 已知问题

### 1.1 线程安全问题

**问题描述**:
sqlite-utils 库不是线程安全的。当从 asyncio 的 `run_in_executor` 中多线程访问数据库时，可能出现 `tuple index out of range` 错误。

**影响范围**:
- `TelegramUploader._get_caption()` 中的 `storage.get_video_by_slug()`
- 并行管道中多个上传 worker 同时访问数据库

**当前解决方案**:
```python
def _get_caption(self, slug: str) -> str:
    try:
        video = self.storage.get_video_by_slug(video_slug)
        if video:
            # 使用 video 数据
    except Exception as e:
        logger.warning("Failed to get video metadata for caption: %s", e)
        # 使用默认值
```

**建议优化**:
1. 使用线程锁保护数据库访问
2. 切换到支持并发的数据库连接池
3. 在管道开始时预加载所有视频元数据到内存

---

### 1.2 大文件处理

**问题描述**:
Telegram 本地 Bot API 限制文件大小为 2GB，超过此限制的文件需要分割。

**影响范围**:
- 大型视频文件（如 3.9GB 的视频）

**当前解决方案**:
```python
MAX_FILE_SIZE = 1900 * 1024 * 1024  # 1900MB，安全边界

def _split_video(self, file_path: Path) -> list[Path]:
    # 使用 ffmpeg -c copy 无重编码分割
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_time),
        "-i", str(file_path), "-t", str(part_duration),
        "-c", "copy", "-avoid_negative_ts", "1",
        str(part_path)
    ])
```

**已知限制**:
- 分割点可能不在关键帧，导致轻微的画面问题
- 分片后文件名变化，需要额外管理
- Caption 需要标注分片序号

**建议优化**:
1. 使用 `-ss` 在输入前进行快速定位
2. 考虑使用 `ffmpeg -c:v libx264` 重新编码确保精确分割
3. 添加分割文件清理机制

---

### 1.3 Caption 生成

**问题描述**:
当视频元数据不完整时，caption 模板变量可能为 `None`。

**影响范围**:
- 新抓取但详情未完成的视频
- 元数据字段缺失的视频

**当前解决方案**:
```python
# 使用 str(value or "") 确保替换值是字符串
caption = caption.replace("{title}", str(title or ""))
caption = caption.replace("{duration}", str(duration or ""))
caption = caption.replace("{description}", str(description or ""))
```

**建议优化**:
1. 使用 Pydantic 模型验证，确保字段有默认值
2. 添加 caption 模板变量验证
3. 支持更丰富的模板语法（如 Jinja2）

---

### 1.4 音频文件 Slug 处理

**问题描述**:
助眠网音频文件使用 `{slug}_audio` 命名，但元数据存储在 `{slug}` 下。

**影响范围**:
- 音频文件 caption 生成

**当前解决方案**:
```python
def _get_caption(self, slug: str) -> str:
    # 对于音频文件，去掉 _audio 后缀
    video_slug = slug.replace("_audio", "")
```

**建议优化**:
1. 在数据库中为音频文件创建独立记录
2. 或在下载时将音频元数据也保存到视频记录

---

### 1.5 环境变量前缀不一致

**问题描述**:
早期使用 `EROASMR_` 前缀，后改为 `SCRAPER_`，可能导致配置混乱。

**影响范围**:
- .env 文件配置
- 部署脚本

**当前状态**:
统一使用 `SCRAPER_` 前缀。

**建议优化**:
1. 在文档中明确说明
2. 添加配置验证警告
3. 支持向后兼容的前缀

---

### 1.6 代理单点故障

**问题描述**:
香港代理服务器是单一节点，故障时无法访问助眠网 CDN。

**影响范围**:
- 助眠网视频下载

**建议优化**:
1. 配置备用代理
2. 实现代理池
3. 添加自动切换机制

---

## 2. 性能优化

### 2.1 下载并发

**当前状态**:
- 顺序下载，一次一个文件

**优化方向**:
```python
# 使用 asyncio 并发下载
async def download_concurrent(slugs, max_concurrent=3):
    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_limit(slug):
        async with semaphore:
            await download_video(slug)

    await asyncio.gather(*[download_with_limit(s) for s in slugs])
```

---

### 2.2 数据库查询优化

**当前状态**:
- 每次查询都是独立的 SQL

**优化方向**:
1. 添加索引:
```sql
CREATE INDEX idx_videos_site_status ON videos(site_id, download_status);
CREATE INDEX idx_downloads_status ON downloads(status);
```

2. 批量查询减少数据库往返

3. 使用连接池

---

### 2.3 内存使用

**当前状态**:
- 队列大小固定（下载 10，上传 20）

**优化方向**:
1. 根据可用内存动态调整队列大小
2. 实现更精细的背压控制
3. 添加内存使用监控

---

### 2.4 网络连接复用

**当前状态**:
- 每次请求创建新连接

**优化方向**:
```python
# 使用 httpx 连接池
client = httpx.Client(
    limits=httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5,
    ),
    timeout=httpx.Timeout(...)
)
```

---

## 3. 功能增强

### 3.1 断点续传

**当前状态**:
- 不支持下载中断后续传

**优化方向**:
```python
def download_with_resume(url, output_path):
    # 检查已下载的大小
    if output_path.exists():
        downloaded = output_path.stat().st_size
        headers = {"Range": f"bytes={downloaded}-"}
    else:
        headers = {}

    # 继续下载
    with open(output_path, "ab") as f:
        for chunk in client.stream("GET", url, headers=headers):
            f.write(chunk)
```

---

### 3.2 多上传目标

**当前状态**:
- 仅支持 Telegram

**优化方向**:
1. 实现 Google Drive 上传器
2. 实现 S3 兼容存储上传器
3. 实现本地 NAS 上传器

```python
class S3Uploader(Uploader):
    @property
    def storage_type(self) -> str:
        return "s3"

    def upload(self, file_path, slug, **kwargs):
        s3_client.upload_file(str(file_path), self.bucket, f"{slug}.mp4")
```

---

### 3.3 进度持久化

**当前状态**:
- 进度仅在内存中

**优化方向**:
1. 定期保存进度到文件
2. 重启后恢复进度
3. 支持暂停/恢复

---

### 3.4 Web Dashboard

**当前状态**:
- 仅 CLI 界面

**优化方向**:
1. 实时进度显示
2. 统计图表
3. 手动控制（暂停、恢复、跳过）
4. 日志查看

---

### 3.5 自动重试策略

**当前状态**:
- 手动重试

**优化方向**:
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(httpx.RequestError),
)
def download_with_retry(url, output_path):
    ...
```

---

## 4. 代码质量

### 4.1 测试覆盖

**当前状态**:
- 缺少单元测试

**优化方向**:
```
tests/
├── test_parser.py
├── test_scraper.py
├── test_downloader.py
├── test_uploader.py
├── test_pipeline.py
└── fixtures/
    ├── sample_list_page.html
    └── sample_detail_page.html
```

---

### 4.2 类型注解

**当前状态**:
- 部分代码缺少类型注解

**优化方向**:
1. 添加完整的类型注解
2. 使用 mypy 进行类型检查
3. 在 CI 中集成类型检查

---

### 4.3 日志结构化

**当前状态**:
- 纯文本日志

**优化方向**:
```python
import structlog

logger = structlog.get_logger()
logger.info("download_started", slug=slug, url=url, expected_size=size)
```

---

### 4.4 错误追踪

**当前状态**:
- 错误记录在日志中

**优化方向**:
1. 集成 Sentry 或类似服务
2. 结构化错误报告
3. 自动告警

---

## 5. 运维改进

### 5.1 健康检查

**优化方向**:
```bash
# 添加健康检查端点
uv run python main.py health-check

# 检查项:
# - 数据库连接
# - 磁盘空间
# - 上传服务状态
# - 代理连接
```

---

### 5.2 监控指标

**优化方向**:
```python
# Prometheus 指标
videos_scraped = Counter("videos_scraped_total", "Videos scraped")
downloads_total = Counter("downloads_total", "Downloads")
downloads_failed = Counter("downloads_failed_total", "Failed downloads")
upload_duration = Histogram("upload_duration_seconds", "Upload duration")
```

---

### 5.3 自动清理

**优化方向**:
```python
# 定期清理旧文件
def cleanup_old_files(days=30):
    """清理 30 天前的已完成下载"""
    cutoff = datetime.now() - timedelta(days=days)
    for file in download_dir.glob("*.mp4"):
        if file.stat().st_mtime < cutoff.timestamp():
            file.unlink()
```

---

## 6. 优先级建议

### 高优先级 (P0)
1. 线程安全问题 - 影响稳定性
2. 数据库索引 - 影响性能

### 中优先级 (P1)
1. 断点续传 - 提升用户体验
2. 自动重试策略 - 提升可靠性
3. 测试覆盖 - 保证代码质量

### 低优先级 (P2)
1. Web Dashboard - 增强功能
2. 多上传目标 - 扩展性
3. 结构化日志 - 运维便利

---

## 7. 版本规划

### v1.1 - 稳定性改进
- 修复线程安全问题
- 添加数据库索引
- 改进错误处理

### v1.2 - 性能优化
- 并发下载
- 连接池
- 批量数据库操作

### v1.3 - 功能增强
- 断点续传
- 多上传目标
- 自动重试

### v2.0 - 重大更新
- Web Dashboard
- 结构化日志
- 完整测试覆盖
- 监控集成
