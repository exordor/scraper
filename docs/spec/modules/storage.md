# 存储层 (storage.py)

## 1. 概述

存储层使用 `sqlite-utils` 库操作 SQLite 数据库，提供：
- 视频元数据存储
- 下载状态跟踪
- 上传位置记录
- 多站点支持

## 2. VideoStorage 类

### 2.1 初始化

```python
class VideoStorage:
    def __init__(
        self,
        db_path: str = "data/videos.db",
        site_id: str = "eroasmr"
    ):
        self.db_path = db_path
        self.site_id = site_id
        self.db = sqlite_utils.Database(db_path)
        self._init_tables()
```

### 2.2 表初始化

```python
def _init_tables(self):
    # 视频表
    self.db["videos"].create({
        "slug": str,
        "site_id": str,
        "title": str,
        "thumbnail_url": str,
        "duration": str,
        "duration_seconds": int,
        "view_count": int,
        "like_count": int,
        "comment_count": int,
        "author": str,
        "excerpt": str,
        "description": str,
        "play_url": str,
        "download_url": str,
        "audio_download_url": str,
        "created_at": str,
        "updated_at": str,
        "detail_scraped_at": str,
    }, pk="slug", if_not_exists=True)

    # 下载状态表
    self.db["downloads"].create({
        "slug": str,
        "site_id": str,
        "status": str,  # pending, downloading, completed, failed
        "local_path": str,
        "file_size": int,
        "audio_path": str,
        "audio_size": int,
        "error_message": str,
        "downloaded_at": str,
    }, pk="slug", if_not_exists=True)

    # 存储位置表
    self.db["storage_locations"].create({
        "id": int,
        "slug": str,
        "site_id": str,
        "storage_type": str,  # telegram, google_drive, etc.
        "location_id": str,
        "location_url": str,
        "metadata": str,  # JSON
        "uploaded_at": str,
    }, pk="id", if_not_exists=True)
```

## 3. 核心方法

### 3.1 视频操作

```python
def upsert_video(self, video: BaseVideo) -> None:
    """插入或更新视频记录"""
    record = video.model_dump()
    record["site_id"] = self.site_id
    self.db["videos"].insert(record, pk="slug", replace=True)

def get_video_by_slug(self, slug: str) -> dict | None:
    """根据 slug 获取视频"""
    try:
        return self.db["videos"].get(slug)
    except NotFoundError:
        return None

def get_videos_without_details(self, limit: int = 100) -> list[dict]:
    """获取未抓取详情的视频"""
    return list(self.db["videos"].rows_where(
        "detail_scraped_at IS NULL AND site_id = ?",
        [self.site_id],
        limit=limit
    ))
```

### 3.2 下载状态管理

```python
def get_pending_downloads(
    self,
    limit: int | None = None,
    include_failed: bool = False
) -> list[str]:
    """获取待下载视频列表"""
    conditions = ["site_id = ?"]
    params = [self.site_id]

    if include_failed:
        conditions.append("(status IS NULL OR status = 'failed')")
    else:
        conditions.append("status IS NULL")

    # 排除已上传的
    conditions.append("""
        slug NOT IN (
            SELECT slug FROM storage_locations
            WHERE storage_type = 'telegram'
        )
    """)

    query = f"""
        SELECT slug FROM videos
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    return [row["slug"] for row in self.db.query(query, params)]

def mark_downloading(self, slug: str) -> None:
    """标记为下载中"""
    self.update_download_status(slug, DownloadStatus.DOWNLOADING)

def mark_completed(
    self,
    slug: str,
    local_path: str,
    file_size: int,
    audio_path: str | None = None,
    audio_size: int | None = None
) -> None:
    """标记下载完成"""
    self.update_download_status(
        slug, DownloadStatus.COMPLETED,
        local_path=local_path,
        file_size=file_size,
        audio_path=audio_path,
        audio_size=audio_size
    )

def mark_failed(self, slug: str, error: str) -> None:
    """标记下载失败"""
    self.update_download_status(
        slug, DownloadStatus.FAILED,
        error_message=error
    )
```

### 3.3 上传位置管理

```python
def add_storage_location(self, location: StorageLocation) -> None:
    """添加存储位置记录"""
    record = location.model_dump()
    record["site_id"] = self.site_id
    record["uploaded_at"] = datetime.now().isoformat()
    if record.get("metadata"):
        record["metadata"] = json.dumps(record["metadata"])
    self.db["storage_locations"].insert(record)
```

## 4. 数据模型

### 4.1 DownloadStatus 枚举

```python
class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 4.2 StorageLocation 模型

```python
@dataclass
class StorageLocation:
    slug: str
    site_id: str
    storage_type: str      # telegram, google_drive, etc.
    location_id: str       # message_id, file_id, etc.
    location_url: str | None
    metadata: dict | None  # 额外信息
```

## 5. 查询示例

### 5.1 统计查询

```python
# 获取站点统计
def get_site_stats(self) -> dict:
    videos = self.db["videos"].count_where("site_id = ?", [self.site_id])
    completed = self.db["downloads"].count_where(
        "site_id = ? AND status = ?", [self.site_id, "completed"]
    )
    failed = self.db["downloads"].count_where(
        "site_id = ? AND status = ?", [self.site_id, "failed"]
    )
    uploaded = self.db["storage_locations"].count_where(
        "site_id = ? AND storage_type = ?", [self.site_id, "telegram"]
    )
    return {
        "videos": videos,
        "downloaded": completed,
        "failed": failed,
        "uploaded": uploaded,
    }
```

### 5.2 复杂查询

```python
# 获取最近上传的视频
def get_recent_uploads(self, limit: int = 10) -> list[dict]:
    return list(self.db.query("""
        SELECT v.slug, v.title, s.location_url, s.uploaded_at
        FROM videos v
        JOIN storage_locations s ON v.slug = s.slug
        WHERE v.site_id = ? AND s.storage_type = 'telegram'
        ORDER BY s.uploaded_at DESC
        LIMIT ?
    """, [self.site_id, limit]))
```

## 6. 线程安全注意事项

### 6.1 当前问题

`sqlite-utils` 的 `Database` 对象在多线程环境下可能出现问题：

```python
# 在线程池中执行时可能出错
result = await loop.run_in_executor(
    None,
    lambda: self.storage.get_video_by_slug(slug)
)
# 错误: tuple index out of range
```

### 6.2 解决方案（待实现）

1. **线程本地存储**: 每个线程创建独立的数据库连接
2. **连接池**: 使用连接池管理数据库连接
3. **锁机制**: 添加读写锁保护数据库操作

## 7. 数据库文件位置

```
eroasmr-scraper/
└── data/
    └── videos.db      # 主数据库文件
```

### 7.1 备份建议

```bash
# 备份数据库
cp data/videos.db data/videos.db.backup

# 导出为 SQL
sqlite3 data/videos.db .dump > backup.sql
```

## 8. 性能考虑

1. **索引**: slug 作为主键自动索引
2. **批量操作**: 使用 batch_size 控制批量插入大小
3. **WAL 模式**: 可考虑启用 Write-Ahead Logging 提高并发性能
