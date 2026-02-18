# Telegram Upload Service Design

## Context

A standalone microservice for uploading files to Telegram via Local Bot API server. The service supports:
- Multi-tenant configuration (multiple bots/channels)
- Large file uploads up to 2GB via Local Bot API
- Both sync and async upload modes
- Webhook callbacks with message links

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Docker Compose Stack                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              telegram-bot-api (Official Docker Image)            │    │
│  │              Port: 8081 • Supports up to 2GB files               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                   ▲                                      │
│                                   │ HTTP API                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Telegram Upload Service                        │    │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐   │    │
│  │  │  FastAPI    │───▶│   Redis     │───▶│  Celery Worker      │   │    │
│  │  │  REST API   │    │   Broker    │    │  (Upload Processor) │   │    │
│  │  │  Port: 8000 │    │  Port: 6379 │    │                     │   │    │
│  │  └─────────────┘    └─────────────┘    └─────────────────────┘   │    │
│  │         │                   │                      │             │    │
│  │         ▼                   ▼                      ▼             │    │
│  │  ┌─────────────┐    ┌─────────────┐                              │    │
│  │  │  SQLite     │    │  SQLite     │                              │    │
│  │  │  (Tenants)  │    │  (Results)  │                              │    │
│  │  └─────────────┘    └─────────────┘                              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI |
| Task Queue | Celery + Redis |
| Database | SQLite |
| Bot API | Local Telegram Bot API (Docker) |
| HTTP Client | httpx |
| File Handling | aiofiles |

## Features

| Feature | Details |
|---------|---------|
| **File Input** | URL download, local file path, direct upload |
| **Large Files** | Up to 2GB via Local Bot API server |
| **Upload Modes** | Sync (immediate) and Async (queued via Celery) |
| **Albums** | Multi-file album uploads |
| **Topics/Threads** | Support for supergroup topic messages |
| **Rich Messages** | Caption with HTML/Markdown parsing |
| **Multi-tenant** | Multiple bots/channels per service instance |
| **Callbacks** | Webhook notifications on completion |
| **Message Links** | Returns channel/message links after upload |

## Project Structure

```
telegram-upload-service/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings and configuration
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py          # Dependencies (get_db, get_tenant)
│   │   ├── tenants.py       # Tenant CRUD endpoints
│   │   ├── upload.py        # Upload endpoints
│   │   └── jobs.py          # Job status endpoints
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py
│   │   ├── job.py
│   │   └── error.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── telegram.py      # Telegram Bot API client
│   │   ├── downloader.py    # File download from URL
│   │   ├── callback.py      # Webhook callback sender
│   │   └── storage.py       # SQLite operations
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── celery_app.py    # Celery configuration
│   │   └── upload.py        # Upload task definitions
│   │
│   └── utils/
│       ├── __init__.py
│       └── file_utils.py    # File path validation, etc.
│
├── data/
│   ├── app.db               # Tenant & job database
│   └── temp/                # Temp files during upload
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_tenants.py
    ├── test_upload.py
    └── test_tasks.py
```

## Data Models

### Tenant
```python
class Tenant(BaseModel):
    id: str  # UUID
    name: str
    bot_token: str
    api_base_url: str = "http://telegram-bot-api:8081"
    default_chat_id: int
    default_topic_id: int | None = None
    callback_url: str | None = None
    callback_headers: dict[str, str] | None = None
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
```

### Upload Job
```python
class UploadJob(BaseModel):
    id: str  # UUID
    tenant_id: str
    status: Literal["pending", "processing", "completed", "failed"]

    # File input (one of these)
    file_url: str | None = None
    file_path: str | None = None

    # Upload options
    chat_id: int | None = None  # Uses tenant default if None
    topic_id: int | None = None
    caption: str | None = None
    parse_mode: Literal["HTML", "Markdown", "MarkdownV2"] | None = None

    # Result
    message_id: int | None = None
    message_link: str | None = None
    public_link: str | None = None
    error: ErrorInfo | None = None

    # Tracking
    retry_count: int = 0
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
```

## REST API

### Base URL
`http://localhost:8000/api/v1`

### Endpoints

#### Tenant Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tenants` | List all tenants |
| POST | `/tenants` | Create a new tenant |
| GET | `/tenants/{tenant_id}` | Get tenant details |
| PUT | `/tenants/{tenant_id}` | Update tenant |
| DELETE | `/tenants/{tenant_id}` | Delete tenant |

#### Upload Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Sync upload (waits for completion) |
| POST | `/upload/async` | Async upload (returns job_id) |
| POST | `/upload/album` | Sync album upload |
| POST | `/upload/album/async` | Async album upload |
| GET | `/jobs/{job_id}` | Get upload job status |
| GET | `/jobs` | List jobs (filter by tenant, status) |

### Request/Response Examples

#### Upload Request (URL-based)
```json
{
  "tenant_id": "tenant-001",
  "file_url": "https://example.com/video.mp4",
  "caption": "My Video",
  "parse_mode": "HTML"
}
```

#### Upload Request (Local Path)
```json
{
  "tenant_id": "tenant-001",
  "file_path": "/data/downloads/video.mp4",
  "chat_id": -1001234567890,
  "topic_id": 123,
  "caption": "My Video"
}
```

#### Job Status Response
```json
{
  "job_id": "abc123",
  "status": "completed",
  "tenant_id": "tenant-001",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:32:15Z",
  "result": {
    "message_id": 12345,
    "chat_id": -1001234567890,
    "message_link": "https://t.me/c/1234567890/12345",
    "public_link": "https://t.me/mychannel/12345"
  },
  "error": null
}
```

## Error Handling

### Error Codes
| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TENANT_NOT_FOUND` | 404 | Tenant ID doesn't exist |
| `FILE_NOT_FOUND` | 404 | Local file path doesn't exist |
| `FILE_URL_UNREACHABLE` | 502 | Failed to download from URL |
| `PATH_NOT_ALLOWED` | 403 | File path outside allowed directories |
| `UPLOAD_FAILED` | 500 | Telegram upload failed |
| `FILE_TOO_LARGE` | 413 | File exceeds 2GB limit |
| `INVALID_FILE_TYPE` | 400 | Unsupported file type |
| `RATE_LIMITED` | 429 | Telegram rate limit hit |

### Retry Configuration
```python
class Settings(BaseSettings):
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 60  # seconds
    RETRY_BACKOFF: float = 2.0  # exponential backoff multiplier
```

## Callback Webhook

### Callback Payload (Success)
```json
{
  "event": "upload.completed",
  "job_id": "abc123",
  "tenant_id": "tenant-001",
  "timestamp": "2024-01-15T10:32:15Z",
  "result": {
    "message_id": 12345,
    "chat_id": -1001234567890,
    "message_link": "https://t.me/c/1234567890/12345",
    "public_link": "https://t.me/mychannel/12345"
  }
}
```

### Callback Payload (Failure)
```json
{
  "event": "upload.failed",
  "job_id": "abc123",
  "tenant_id": "tenant-001",
  "timestamp": "2024-01-15T10:32:15Z",
  "error": {
    "code": "UPLOAD_FAILED",
    "message": "File too large"
  }
}
```

## Configuration

### Environment Variables
```bash
# App
APP_NAME=telegram-upload-service
DEBUG=false
ALLOWED_FILE_DIRS=["/data/downloads", "/tmp/uploads"]

# Database
DATABASE_URL=sqlite:///data/app.db

# Redis
REDIS_URL=redis://redis:6379/0

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=db+sqlite:///data/celery_results.db

# Telegram Bot API Server (local)
TELEGRAM_API_URL=http://telegram-bot-api:8081

# Retry Settings
MAX_RETRIES=3
RETRY_DELAY=60
RETRY_BACKOFF=2.0
```

### Docker Compose
```yaml
services:
  telegram-bot-api:
    image: aiogram/telegram-bot-api
    environment:
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
    ports:
      - "8081:8081"
    volumes:
      - telegram-bot-api-data:/var/lib/telegram-bot-api

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  upload-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - TELEGRAM_API_URL=http://telegram-bot-api:8081
    volumes:
      - ./data:/app/data
    depends_on:
      - redis
      - telegram-bot-api

  celery-worker:
    build: .
    command: celery -A app.tasks.celery_app worker --loglevel=info
    environment:
      - REDIS_URL=redis://redis:6379/0
      - TELEGRAM_API_URL=http://telegram-bot-api:8081
    volumes:
      - ./data:/app/data
    depends_on:
      - redis
      - telegram-bot-api

volumes:
  telegram-bot-api-data:
```

## Verification

1. **Unit Tests**: Run `pytest` to verify all components
2. **API Tests**: Test endpoints with `httpie` or `curl`
3. **Integration Test**: Create tenant, upload file, verify callback
4. **Load Test**: Test concurrent uploads with multiple jobs

## Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "celery[redis]>=5.3.0",
    "httpx>=0.26.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sqlite-utils>=3.36.0",
    "aiofiles>=23.2.0",
    "python-multipart>=0.0.6",
]
```
