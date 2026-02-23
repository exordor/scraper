# 上传模块 (uploader.py, telegram_uploader.py)

## 1. 概述

上传模块定义了上传器接口和 Telegram 上传实现，负责将下载的文件上传到目标平台。

## 2. 基类 (uploader.py)

### 2.1 Uploader 抽象类

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass
class UploadResult:
    """上传结果"""
    success: bool
    location_id: str | None = None      # 平台特定 ID
    location_url: str | None = None     # 可访问 URL
    error: str | None = None
    metadata: dict | None = None        # 额外信息

class Uploader(ABC):
    """上传器基类"""

    @property
    @abstractmethod
    def storage_type(self) -> str:
        """存储类型标识（如 'telegram', 'google_drive'）"""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """检查上传器是否配置就绪"""
        pass

    @abstractmethod
    def upload(
        self,
        file_path: Path,
        slug: str,
        **kwargs
    ) -> UploadResult:
        """上传文件

        Args:
            file_path: 文件路径
            slug: 视频 slug
            **kwargs: 额外参数（caption, thumbnail_path 等）

        Returns:
            UploadResult
        """
        pass
```

### 2.2 MockUploader

用于测试的模拟上传器：

```python
class MockUploader(Uploader):
    @property
    def storage_type(self) -> str:
        return "mock"

    def is_ready(self) -> bool:
        return True

    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        return UploadResult(
            success=True,
            location_id=f"mock-{slug}",
            location_url=f"https://mock.example.com/video/{slug}",
        )
```

## 3. TelegramUploader (telegram_uploader.py)

### 3.1 初始化

```python
class TelegramUploader(Uploader):
    def __init__(
        self,
        upload_service_url: str | None = None,
        tenant_id: str | None = None,
        caption_template: str | None = None,
        parse_mode: str | None = None,
        file_path_map: dict[str, str] | None = None,
        storage: VideoStorage | None = None,
    ):
        self.upload_service_url = upload_service_url or settings.telegram.upload_service_url
        self.tenant_id = tenant_id or settings.telegram.tenant_id
        self.caption_template = caption_template or settings.telegram.caption_template
        self.parse_mode = parse_mode or settings.telegram.parse_mode
        self.file_path_map = file_path_map or settings.telegram.file_path_map
        self.storage = storage
```

### 3.2 配置项

| 配置 | 默认值 | 描述 |
|------|--------|------|
| upload_service_url | http://localhost:8000 | 上传服务地址 |
| tenant_id | None | 租户 ID |
| caption_template | `{title}\n\n{description}...` | Caption 模板 |
| parse_mode | HTML | 解析模式 |
| file_path_map | 本地路径→容器路径 | Docker 路径映射 |

### 3.3 Caption 生成

```python
def _get_caption(self, slug: str) -> str:
    """生成 Caption"""
    caption = self.caption_template

    # 替换 slug
    caption = caption.replace("{slug}", slug)

    # 默认值
    title = slug
    duration = ""
    description = ""

    # 对于音频文件，去掉 _audio 后缀
    video_slug = slug.replace("_audio", "")

    # 从数据库获取元数据
    if self.storage:
        try:
            video = self.storage.get_video_by_slug(video_slug)
            if video:
                title = video.get("title") or video_slug
                duration = video.get("duration") or ""
                description = video.get("description") or video.get("excerpt") or ""

                # 截断过长的描述
                if len(description) > 800:
                    description = description[:797] + "..."
        except Exception as e:
            logger.warning("Failed to get video metadata for caption: %s", e)

    # 确保替换值是字符串
    caption = caption.replace("{title}", str(title or ""))
    caption = caption.replace("{duration}", str(duration or ""))
    caption = caption.replace("{description}", str(description or ""))

    return caption
```

### 3.4 文件路径映射

用于 Docker 环境的路径转换：

```python
def _map_file_path(self, file_path: Path) -> str:
    """将本地路径映射到容器路径"""
    path_str = str(file_path.resolve())

    for local_prefix, container_prefix in self.file_path_map.items():
        if path_str.startswith(local_prefix):
            return path_str.replace(local_prefix, container_prefix, 1)

    return path_str

# 示例配置
file_path_map = {
    "/root/telegram-upload-service/data/downloads": "/app/data/downloads"
}
```

## 4. 大文件分割

### 4.1 分割逻辑

Telegram 本地 Bot API 限制文件大小为 2GB，超过需要分割：

```python
MAX_FILE_SIZE = 1900 * 1024 * 1024  # 1900MB，安全边界

def _split_video(self, file_path: Path, max_size: int = MAX_FILE_SIZE) -> list[Path]:
    """分割视频文件"""
    file_size = file_path.stat().st_size

    if file_size <= max_size:
        return [file_path]

    # 计算需要的分片数
    num_parts = (file_size + max_size - 1) // max_size

    # 获取视频时长
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
        capture_output=True, text=True, check=True
    )
    total_duration = float(result.stdout.strip())

    # 计算每分片时长
    part_duration = total_duration / num_parts

    # 使用 ffmpeg 分割
    parts = []
    for i in range(num_parts):
        start_time = i * part_duration
        part_path = output_dir / f"{base_name}_part{i+1}{ext}"

        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", str(file_path),
            "-t", str(part_duration),
            "-c", "copy",  # 无重编码
            "-avoid_negative_ts", "1",
            str(part_path)
        ], capture_output=True, check=True)

        parts.append(part_path)

    return parts
```

### 4.2 分割上传流程

```python
def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
    # 检查并分割
    parts = self._split_video(file_path)
    is_split = len(parts) > 1

    all_results = []
    for i, part_path in enumerate(parts):
        if is_split:
            part_caption = f"{caption}\n\n📹 Part {i + 1}/{len(parts)}"
        else:
            part_caption = caption

        result = self._upload_single(part_path, slug, part_caption, ...)
        all_results.append(result)

        # 清理分片
        if is_split and part_path != file_path:
            part_path.unlink()

    # 汇总结果
    successful = [r for r in all_results if r.success]
    failed = [r for r in all_results if not r.success]

    # ...
```

## 5. 上传 API 调用

### 5.1 请求格式

```python
def _upload_single(self, file_path, slug, caption, thumbnail_path, metadata):
    url = f"{self.upload_service_url}/api/v1/upload/"

    payload = {
        "tenant_id": self.tenant_id,
        "file_path": self._map_file_path(file_path),
        "caption": caption,
        "parse_mode": self.parse_mode,
    }

    # 添加缩略图
    if thumbnail_path:
        payload["thumbnail_path"] = self._map_file_path(thumbnail_path)
    elif metadata and metadata.get("thumbnail_url"):
        payload["thumbnail_url"] = metadata["thumbnail_url"]

    # 添加视频元数据
    if metadata:
        if metadata.get("duration"):
            payload["duration"] = metadata["duration"]

    with httpx.Client(timeout=600.0) as client:
        response = client.post(url, json=payload)
```

### 5.2 响应处理

```python
result = response.json()

if result.get("status") == "completed" and result.get("result"):
    upload_result = result["result"]
    return UploadResult(
        success=True,
        location_id=str(upload_result.get("message_id")),
        location_url=upload_result.get("message_link"),
        metadata={
            "chat_id": upload_result.get("chat_id"),
            "public_link": upload_result.get("public_link"),
        },
    )
else:
    error = result.get("error", {})
    return UploadResult(
        success=False,
        error=error.get("message", "Unknown upload error"),
    )
```

## 6. 错误处理

### 6.1 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| 401 Unauthorized | tenant_id 错误 | 检查配置 |
| 404 Not Found | 文件路径错误 | 检查路径映射 |
| 413 Too Large | 文件超过限制 | 自动分割 |
| FILE_PARTS_INVALID | 分片上传失败 | 重试 |
| Timeout | 网络问题 | 重试 |

### 6.2 错误返回

```python
except httpx.TimeoutException:
    return UploadResult(success=False, error="Upload timed out")

except Exception as e:
    return UploadResult(success=False, error=f"Upload failed: {e}")
```

## 7. 扩展新上传器

### 7.1 实现步骤

1. 继承 `Uploader` 基类
2. 实现 `storage_type` 属性
3. 实现 `is_ready()` 方法
4. 实现 `upload()` 方法
5. 在 CLI 中注册

### 7.2 示例：Google Drive

```python
class GoogleDriveUploader(Uploader):
    @property
    def storage_type(self) -> str:
        return "google_drive"

    def is_ready(self) -> bool:
        return bool(self.credentials)

    def upload(self, file_path: Path, slug: str, **kwargs) -> UploadResult:
        # 使用 Google Drive API 上传
        # ...
        return UploadResult(
            success=True,
            location_id=file_id,
            location_url=f"https://drive.google.com/file/d/{file_id}",
        )
```
