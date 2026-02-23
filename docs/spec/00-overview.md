# eroasmr-scraper 项目规格文档

## 文档版本
- **版本**: 1.0.0
- **日期**: 2026-02-20
- **状态**: 活跃开发中

---

## 1. 项目概述

### 1.1 项目目标

eroasmr-scraper 是一个多站点视频元数据爬虫，具有下载和上传管道功能。主要目标：

1. **元数据采集** - 从多个 ASMR 视频网站爬取视频元数据
2. **视频下载** - 支持代理访问、认证登录、断点续传
3. **自动上传** - 将下载的视频上传到 Telegram 频道
4. **并行处理** - 使用生产者-消费者模式实现高效的下载上传流水线

### 1.2 支持的站点

| 站点 | URL | 特点 |
|------|-----|------|
| EroAsmr | eroasmr.com | 公开站点，无需认证 |
| 助眠网 | zhumianwang.com | 需要登录，有独立音频文件，CDN 需要代理访问 |

### 1.3 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.12+ | 主要开发语言 |
| 异步 | asyncio | 并发处理 |
| HTTP | httpx | HTTP 客户端，支持 HTTP/2 |
| 数据库 | SQLite + sqlite-utils | 轻量级存储 |
| 配置 | Pydantic Settings | 类型安全的配置管理 |
| CLI | Typer + Rich | 命令行界面和进度显示 |
| 解析 | BeautifulSoup4 + lxml | HTML 解析 |
| 认证 | Playwright | Cookie 获取（需登录站点）|
| 外部服务 | Telegram Bot API | 视频上传 |
| 代理 | Squid (HK Server) | CDN 访问代理 |

---

## 2. 目录结构

```
eroasmr-scraper/
├── src/eroasmr_scraper/          # 主包
│   ├── __init__.py               # 版本信息
│   ├── cli.py                    # CLI 入口点
│   ├── config.py                 # Pydantic 配置
│   ├── factory.py                # 爬虫工厂
│   ├── models.py                 # 通用模型导出
│   ├── storage.py                # SQLite 存储层
│   ├── downloader.py             # 视频下载器
│   ├── pipeline.py               # 顺序管道
│   ├── parallel_pipeline.py      # 并行管道
│   ├── uploader.py               # 上传器基类
│   ├── telegram_uploader.py      # Telegram 上传实现
│   ├── web_dashboard.py          # FastAPI 监控
│   │
│   ├── base/                     # 抽象基类
│   │   ├── __init__.py
│   │   ├── models.py             # 基础数据模型
│   │   ├── parser.py             # 解析器接口
│   │   └── scraper.py            # 爬虫接口
│   │
│   ├── sites/                    # 站点实现
│   │   ├── __init__.py
│   │   ├── eroasmr/              # EroAsmr 站点
│   │   │   ├── __init__.py
│   │   │   ├── models.py         # 站点特定模型
│   │   │   ├── parser.py         # HTML 解析
│   │   │   └── scraper.py        # 爬虫实现
│   │   │
│   │   └── zhumianwang/          # 助眠网站点
│   │       ├── __init__.py
│   │       ├── models.py         # 站点特定模型
│   │       ├── parser.py         # 列表/详情解析
│   │       ├── play_parser.py    # 播放页解析（下载链接）
│   │       └── scraper.py        # 爬虫实现
│   │
│   └── auth/                     # 认证模块
│       ├── __init__.py
│       └── playwright_auth.py    # Playwright Cookie 获取
│
├── data/                         # 数据目录
│   ├── videos.db                 # SQLite 数据库
│   ├── cookies.json              # 认证 Cookie
│   ├── downloads/                # 下载文件
│   └── download_archive.txt      # 下载归档
│
├── logs/                         # 日志目录
│   ├── pipeline_*.log            # 管道日志
│   └── scraper_*.log             # 爬虫日志
│
├── docs/                         # 文档
│   └── spec/                     # 规格文档
│
├── scripts/                      # 辅助脚本
│   └── split_large_files.sh      # 大文件分割
│
├── .env                          # 环境变量
├── .env.example                  # 环境变量示例
├── pyproject.toml                # 项目配置
└── uv.lock                       # 依赖锁定
```

---

## 3. 快速开始

### 3.1 安装

```bash
# 使用 uv 安装依赖
cd eroasmr-scraper
uv sync
```

### 3.2 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置
vim .env
```

关键配置：
```bash
# Telegram 上传服务
SCRAPER_TELEGRAM__TENANT_ID=your-tenant-id
SCRAPER_TELEGRAM__UPLOAD_SERVICE_URL=http://localhost:8000
```

### 3.3 基本命令

```bash
# 查看帮助
uv run eroasmr-scraper --help

# 完整爬取（列表 + 详情）
uv run eroasmr-scraper full --site zhumianwang

# 运行并行管道（下载 + 上传）
uv run eroasmr-scraper parallel --site zhumianwang --output /path/to/downloads

# 查看上传器状态
uv run eroasmr-scraper uploaders
```

---

## 4. 核心功能

### 4.1 元数据爬取
- 列表页解析：提取视频基本信息
- 详情页解析：提取完整元数据（标签、分类、相关视频）
- 增量更新：只爬取新内容

### 4.2 视频下载
- 多线程下载支持
- 代理访问（助眠网 CDN）
- Cookie 认证
- 进度显示
- 断点续传（通过归档文件）

### 4.3 上传管道
- 顺序管道：下载后逐个上传
- 并行管道：生产者-消费者模式
- 大文件分割：超过 2GB 自动分割
- Caption 生成：从元数据自动生成

### 4.4 监控
- Web Dashboard（FastAPI）
- 实时进度显示
- 统计信息

---

## 5. 相关文档索引

| 文档 | 描述 |
|------|------|
| [01-architecture.md](01-architecture.md) | 系统架构设计 |
| [modules/config.md](modules/config.md) | 配置系统 |
| [modules/storage.md](modules/storage.md) | 存储层 |
| [modules/scraper.md](modules/scraper.md) | 爬虫模块 |
| [modules/downloader.md](modules/downloader.md) | 下载模块 |
| [modules/pipeline.md](modules/pipeline.md) | 管道模块 |
| [modules/uploader.md](modules/uploader.md) | 上传模块 |
| [03-multi-site.md](03-multi-site.md) | 多站点支持 |
| [04-external-services.md](04-external-services.md) | 外部服务集成 |
| [05-cli-commands.md](05-cli-commands.md) | CLI 命令参考 |
| [06-known-issues.md](06-known-issues.md) | 已知问题与优化方向 |
