# CLI 命令参考

## 1. 概述

eroasmr-scraper 使用 Typer 构建 CLI，提供完整的视频抓取、下载、上传功能。

**入口点**: `main.py`

```bash
uv run python main.py [command] [options]
```

## 2. 全局选项

```bash
uv run python main.py --help          # 显示帮助
uv run python main.py --version       # 显示版本
uv run python main.py --verbose       # 详细输出
uv run python main.py --debug         # 调试模式
```

## 3. 抓取命令

### 3.1 scrape - 抓取列表页

抓取视频列表，保存基本信息到数据库。

```bash
uv run python main.py scrape [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--pages`, `-p` | int | 1 | 抓取页数 |
| `--start-page` | int | 1 | 起始页 |
| `--end-page` | int | None | 结束页 |
| `--reverse` | bool | False | 从最后一页开始 |
| `--save-interval` | int | 10 | 保存间隔（页） |

**示例**:

```bash
# 抓取 EroAsmr 前 5 页
uv run python main.py scrape --site eroasmr --pages 5

# 抓取助眠网全部页面
uv run python main.py scrape --site zhumianwang --end-page 100

# 从最后一页向前抓取
uv run python main.py scrape --site zhumianwang --pages 10 --reverse
```

### 3.2 detail - 抓取详情页

抓取视频详情，补充完整元数据。

```bash
uv run python main.py detail [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--limit` | int | None | 限制数量 |
| `--force` | bool | False | 强制重新抓取 |

**示例**:

```bash
# 抓取所有缺失详情的视频
uv run python main.py detail --site zhumianwang

# 强制重新抓取前 10 个
uv run python main.py detail --site zhumianwang --limit 10 --force
```

### 3.3 full - 完整抓取

列表页 + 详情页的完整抓取流程。

```bash
uv run python main.py full [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--pages`, `-p` | int | 1 | 抓取页数 |
| `--start-page` | int | 1 | 起始页 |

**示例**:

```bash
# 完整抓取助眠网 5 页
uv run python main.py full --site zhumianwang --pages 5
```

## 4. 下载命令

### 4.1 download - 下载视频

下载视频文件到本地。

```bash
uv run python main.py download [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--limit` | int | None | 限制数量 |
| `--include-audio` | bool | True | 包含音频（助眠网） |
| `--retry` | bool | False | 重试失败的 |

**示例**:

```bash
# 下载待下载的视频
uv run python main.py download --site zhumianwang --limit 10

# 重试失败的视频
uv run python main.py download --site zhumianwang --retry
```

## 5. 上传命令

### 5.1 upload - 上传文件

上传已下载的文件到目标平台。

```bash
uv run python main.py upload [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--limit` | int | None | 限制数量 |
| `--uploader`, `-u` | str | telegram | 上传器类型 |

**示例**:

```bash
# 上传到 Telegram
uv run python main.py upload --site zhumianwang --uploader telegram
```

### 5.2 uploaders - 查看上传器状态

```bash
uv run python main.py uploaders [OPTIONS]

Options:
  --site, -s  站点 ID [default: eroasmr]
```

**输出示例**:

```
Configured Uploaders:
──────────────────────────────────────────────────────────
  • telegram
    - Ready: ✓
    - Service URL: http://localhost:8000
    - Tenant ID: 4d6e8863-...
──────────────────────────────────────────────────────────
```

## 6. 管道命令

### 6.1 pipeline - 顺序管道

下载后立即上传的顺序处理。

```bash
uv run python main.py pipeline [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--limit` | int | None | 限制数量 |
| `--keep` | bool | False | 保留本地文件 |
| `--retry` | bool | False | 重试失败的 |

**示例**:

```bash
# 处理 10 个视频
uv run python main.py pipeline --site zhumianwang --limit 10

# 保留文件（不删除）
uv run python main.py pipeline --site zhumianwang --limit 10 --keep
```

### 6.2 parallel - 并行管道

生产者-消费者模式的并行处理（推荐用于大量文件）。

```bash
uv run python main.py parallel [OPTIONS]
```

**选项**:

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--site`, `-s` | str | eroasmr | 站点 ID |
| `--limit` | int | None | 限制数量 |
| `--keep` | bool | False | 保留本地文件 |
| `--workers` | int | 3 | 上传工作线程数 |
| `--retry` | bool | False | 重试失败的 |
| `--verbose`, `-v` | bool | False | 详细输出 |

**示例**:

```bash
# 并行处理 50 个视频
uv run python main.py parallel --site zhumianwang --limit 50

# 使用 5 个上传线程
uv run python main.py parallel --site zhumianwang --workers 5

# 详细输出
uv run python main.py parallel --site zhumianwang --limit 10 -v
```

## 7. 数据库命令

### 7.1 stats - 查看统计

```bash
uv run python main.py stats [OPTIONS]

Options:
  --site, -s  站点 ID [default: eroasmr]
```

**输出示例**:

```
Database Statistics (zhumianwang):
──────────────────────────────────────────────────────────
  Videos:        1,234
  Downloaded:      567
  Pending:         667
  Failed:           12
  Uploaded:        550
──────────────────────────────────────────────────────────
  Storage Locations:
    telegram:      550
──────────────────────────────────────────────────────────
```

### 7.2 db-migrate - 数据库迁移

```bash
uv run python main.py db-migrate
```

### 7.3 db-reset - 重置数据库

```bash
uv run python main.py db-reset [OPTIONS]

Options:
  --confirm  确认重置
```

## 8. 工具命令

### 8.1 check - 检查系统状态

```bash
uv run python main.py check [OPTIONS]

Options:
  --site, -s  站点 ID [default: eroasmr]
```

**检查项**:
- 数据库连接
- 下载目录
- 磁盘空间
- 上传器状态
- 网络连接

### 8.2 clean - 清理文件

```bash
uv run python main.py clean [OPTIONS]

Options:
  --site, -s    站点 ID [default: eroasmr]
  --orphans     清理孤立文件
  --failed      清理失败记录
  --all         清理全部
```

### 8.3 cookies - 管理 Cookies

```bash
# 验证 Cookie 有效性
uv run python main.py cookies verify --site zhumianwang

# 显示 Cookie 信息
uv run python main.py cookies info --site zhumianwang
```

## 9. 配置命令

### 9.1 config - 显示配置

```bash
uv run python main.py config [OPTIONS]

Options:
  --site, -s  显示站点配置
```

**输出示例**:

```yaml
Settings:
  default_site: zhumianwang
  log_level: INFO
  db:
    path: data/videos.db
  telegram:
    upload_service_url: http://localhost:8000
    tenant_id: 4d6e8863-***
    parse_mode: HTML
```

## 10. 使用场景

### 10.1 新站点初始化

```bash
# 1. 检查系统状态
uv run python main.py check --site zhumianwang

# 2. 完整抓取元数据
uv run python main.py full --site zhumianwang --pages 10

# 3. 查看统计
uv run python main.py stats --site zhumianwang

# 4. 开始下载上传
uv run python main.py parallel --site zhumianwang --limit 50
```

### 10.2 定期增量更新

```bash
# 1. 抓取新视频
uv run python main.py scrape --site zhumianwang --pages 5

# 2. 抓取新详情
uv run python main.py detail --site zhumianwang

# 3. 处理待下载
uv run python main.py parallel --site zhumianwang
```

### 10.3 处理失败任务

```bash
# 1. 查看统计
uv run python main.py stats --site zhumianwang

# 2. 重试下载
uv run python main.py download --site zhumianwang --retry

# 3. 或重新处理
uv run python main.py parallel --site zhumianwang --retry
```

### 10.4 后台运行

```bash
# 使用 tmux
tmux new -s scraper
uv run python main.py parallel --site zhumianwang

# 分离: Ctrl+B, D
# 重新连接: tmux attach -t scraper
```

## 11. 环境变量

### 11.1 配置覆盖

```bash
# 设置默认站点
export SCRAPER_DEFAULT_SITE=zhumianwang

# 设置日志级别
export SCRAPER_LOG_LEVEL=DEBUG

# 设置 Telegram 配置
export SCRAPER_TELEGRAM__TENANT_ID=xxx
export SCRAPER_TELEGRAM__UPLOAD_SERVICE_URL=http://localhost:8000
```

### 11.2 .env 文件

```bash
# .env
SCRAPER_DEFAULT_SITE=zhumianwang
SCRAPER_LOG_LEVEL=INFO
SCRAPER_TELEGRAM__TENANT_ID=4d6e8863-4d30-4e65-9455-92b49d21b67c
SCRAPER_TELEGRAM__UPLOAD_SERVICE_URL=http://localhost:8000
SCRAPER_TELEGRAM__CAPTION_TEMPLATE=<b>{title}</b>\n\n{description}
```

## 12. 退出码

| 退出码 | 含义 |
|-------|------|
| 0 | 成功 |
| 1 | 一般错误 |
| 2 | 配置错误 |
| 3 | 网络错误 |
| 4 | 数据库错误 |
| 5 | 用户取消 |
