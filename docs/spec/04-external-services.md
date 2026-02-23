# 外部服务集成

## 1. 概述

eroasmr-scraper 依赖多个外部服务：

- **Telegram Upload Service** - 独立的上传服务，处理 Telegram 文件上传
- **香港代理服务器** - 用于访问中国大陆 CDN
- **Telegram Bot API Server** - 本地 Bot API 服务器（由 Upload Service 管理）

## 2. Telegram Upload Service

### 2.1 服务架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Telegram Upload Service                           │
│                    (localhost:8000)                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│  │   FastAPI   │     │   Redis     │     │  Telegram   │          │
│  │   Server    │────►│   Queue     │────►│  Bot API    │          │
│  │  :8000      │     │   :6379     │     │  (Local)    │          │
│  └─────────────┘     └─────────────┘     └─────────────┘          │
│         │                                         │                 │
│         │                                         │                 │
│         ▼                                         ▼                 │
│  ┌─────────────┐                         ┌─────────────┐          │
│  │  Database   │                         │  Telegram   │          │
│  │  (SQLite)   │                         │  Servers    │          │
│  └─────────────┘                         └─────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 部署位置

```
/root/telegram-upload-service/
├── docker-compose.yml
├── .env
├── data/
│   ├── bot_api/          # Bot API 数据目录
│   ├── downloads/        # 上传文件目录
│   └── redis/            # Redis 持久化
└── src/
    └── ...
```

### 2.3 API 端点

#### 同步上传 (推荐)

```http
POST /api/v1/upload/
Content-Type: application/json

{
  "tenant_id": "4d6e8863-4d30-4e65-9455-92b49d21b67c",
  "file_path": "/app/data/downloads/video.mp4",
  "caption": "视频标题",
  "parse_mode": "HTML",
  "thumbnail_path": "/app/data/downloads/thumb.jpg",
  "duration": 1234
}
```

**响应**:

```json
{
  "status": "completed",
  "job_id": "uuid",
  "result": {
    "message_id": 456,
    "chat_id": -1003721657778,
    "message_link": "https://t.me/c/3721657778/456",
    "public_link": null
  }
}
```

#### 异步上传

```http
POST /api/v1/async-upload/
```

返回 job_id，通过 WebSocket 或轮询获取结果。

#### 任务状态

```http
GET /api/v1/jobs/{job_id}
```

### 2.4 配置

**环境变量**:

```bash
# .env 文件
BOT_TOKEN=your-bot-token
API_ID=your-api-id
API_HASH=your-api-hash
CHANNEL_ID=-1003721657778

# Docker 路径映射
HOST_DOWNLOADS_PATH=/root/telegram-upload-service/data/downloads
CONTAINER_DOWNLOADS_PATH=/app/data/downloads
```

**docker-compose.yml**:

```yaml
services:
  bot-api:
    image: aiogram/telegram-bot-api:latest
    volumes:
      - ./data/bot_api:/var/lib/telegram-bot-api
    environment:
      - TELEGRAM_API_ID=${API_ID}
      - TELEGRAM_API_HASH=${API_HASH}
    command: --local  # 允许本地文件路径

  upload-service:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data/downloads:/app/data/downloads
    depends_on:
      - redis
      - bot-api

  redis:
    image: redis:alpine
    volumes:
      - ./data/redis:/data
```

### 2.5 租户系统

Upload Service 支持多租户：

```python
# 租户配置
tenant_id = "4d6e8863-4d30-4e65-9455-92b49d21b67c"
channel_id = -1003721657778  # FileUP 频道
```

每个租户可以配置：
- 目标频道/群组
- 上传限制
- Caption 模板

### 2.6 错误处理

| 错误代码 | 描述 | 处理方式 |
|---------|------|---------|
| 401 | 租户认证失败 | 检查 tenant_id |
| 404 | 文件不存在 | 检查文件路径 |
| 413 | 文件过大 | 分割后上传 |
| FILE_PARTS_INVALID | 分片无效 | 重试 |
| Timeout | 上传超时 | 增加超时或重试 |

## 3. 香港代理服务器

### 3.1 用途

助眠网的 CDN (video.zklhy.com) 位于中国大陆：
- 美国服务器无法直接访问
- 需要通过香港代理转发请求

### 3.2 服务器配置

**Squid 配置** (`/etc/squid/squid.conf`):

```squid
# 监听端口
http_port 3128

# 允许的客户端 IP
acl allowed_clients src 104.234.26.3

# 访问控制
http_access allow allowed_clients
http_access deny all

# 禁用缓存（只做代理）
cache deny all

# 日志
access_log /var/log/squid/access.log squid
```

### 3.3 连接信息

```python
ZHUMIANWANG_PROXY = "http://202.155.141.121:3128"
```

### 3.4 使用方式

```python
def _download_file(self, url, output_path, use_proxy=False):
    if use_proxy and "video.zklhy.com" in url:
        client = httpx.Client(
            proxy=ZHUMIANWANG_PROXY,
            timeout=httpx.Timeout(
                connect=30.0,
                read=600.0,  # 10 分钟读取超时
                write=30.0,
                pool=30.0
            ),
            follow_redirects=True,
        )
        logger.info("Using HK proxy for zhumianwang CDN")
```

### 3.5 故障排查

```bash
# 测试代理连通性
curl -x http://202.155.141.121:3128 https://video.zklhy.com/test.mp4 -I

# 检查 Squid 日志
ssh hk-server "tail -f /var/log/squid/access.log"

# 检查服务状态
ssh hk-server "systemctl status squid"
```

## 4. Telegram Bot API (本地)

### 4.1 为什么使用本地 Bot API

官方 Telegram Bot API 限制：
- 文件大小限制：50 MB

本地 Bot API 限制：
- 文件大小限制：2 GB

### 4.2 部署方式

由 Telegram Upload Service 的 Docker Compose 管理：

```yaml
services:
  bot-api:
    image: aiogram/telegram-bot-api:latest
    volumes:
      - ./data/bot_api:/var/lib/telegram-bot-api
    environment:
      - TELEGRAM_API_ID=${API_ID}
      - TELEGRAM_API_HASH=${API_HASH}
    command: --local
```

### 4.3 获取 API 凭证

1. 访问 https://my.telegram.org
2. 登录并创建应用
3. 获取 `api_id` 和 `api_hash`

### 4.4 文件大小处理

```
┌─────────────────────────────────────────────────────────────────────┐
│                     File Size Handling                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  文件大小 <= 50 MB  ─────────────► 官方 Bot API 可用                │
│                                                                     │
│  50 MB < 文件大小 <= 2 GB  ─────► 本地 Bot API 必需                 │
│                                                                     │
│  2 GB < 文件大小  ─────────────► 分割后上传                         │
│                                (ffmpeg -c copy)                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 5. 文件路径映射

### 5.1 Docker 路径问题

Upload Service 运行在 Docker 容器中，路径与宿主机不同：

```
宿主机路径:
/root/telegram-upload-service/data/downloads/video.mp4

容器内路径:
/app/data/downloads/video.mp4
```

### 5.2 配置映射

```python
# config.py
class TelegramConfig(BaseModel):
    file_path_map: dict[str, str] = {
        "/root/telegram-upload-service/data/downloads": "/app/data/downloads"
    }
```

### 5.3 路径转换

```python
def _map_file_path(self, file_path: Path) -> str:
    """将本地路径映射到容器路径"""
    path_str = str(file_path.resolve())

    for local_prefix, container_prefix in self.file_path_map.items():
        if path_str.startswith(local_prefix):
            return path_str.replace(local_prefix, container_prefix, 1)

    return path_str
```

## 6. 网络架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Network Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                      US Server (104.234.26.3)                        │  │
│   │                                                                     │  │
│   │   eroasmr-scraper ─────────► Telegram Upload Service               │  │
│   │        │                      (localhost:8000)                      │  │
│   │        │                            │                               │  │
│   │        │                            ▼                               │  │
│   │        │                     Local Bot API                          │  │
│   │        │                            │                               │  │
│   │        │                            ▼                               │  │
│   │        │                     Telegram Servers                       │  │
│   │        │                                                            │  │
│   │        │         助眠网 CDN 下载                                    │  │
│   │        ▼                                                            │  │
│   │   ┌─────────┐                                                      │  │
│   │   │ httpx   │──────► HK Proxy (202.155.141.121:3128)              │  │
│   │   │ client  │              │                                       │  │
│   │   └─────────┘              ▼                                       │  │
│   │                    video.zklhy.com (CDN)                           │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 7. 服务管理

### 7.1 启动服务

```bash
# 启动 Telegram Upload Service
cd /root/telegram-upload-service
docker compose up -d

# 检查服务状态
docker compose ps

# 查看日志
docker compose logs -f upload-service
```

### 7.2 健康检查

```bash
# 检查 Upload Service
curl http://localhost:8000/health

# 检查 Redis
redis-cli ping

# 检查 Bot API
curl http://localhost:8081/
```

### 7.3 故障恢复

```bash
# 重启服务
docker compose restart

# 清理队列
redis-cli FLUSHDB

# 检查磁盘空间
df -h /root/telegram-upload-service/data
```

## 8. 安全考虑

### 8.1 凭证管理

```bash
# 不要提交的文件
.env
cookies.json

# 使用环境变量
export SCRAPER_TELEGRAM__TENANT_ID=xxx
```

### 8.2 代理安全

- 仅允许特定 IP 访问
- 不缓存敏感内容
- 记录访问日志

### 8.3 API 安全

- tenant_id 作为认证凭证
- 仅监听 localhost
- 敏感操作需要验证

## 9. 监控和日志

### 9.1 日志位置

```
eroasmr-scraper 日志:
  - stdout/stderr (由 systemd 或 tmux 捕获)

Telegram Upload Service 日志:
  - docker compose logs upload-service

Squid 代理日志:
  - /var/log/squid/access.log (香港服务器)
```

### 9.2 关键指标

- 上传成功率
- 平均上传时间
- 代理响应时间
- 磁盘使用率
- 队列长度

### 9.3 告警条件

- 连续 3 次上传失败
- 代理连接超时
- 磁盘使用率 > 90%
- 服务无响应
