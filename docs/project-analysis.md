# eroasmr-scraper 项目解析

## 1. 项目结构

```
eroasmr-scraper/
├── src/eroasmr_scraper/          # 核心源码
│   ├── __init__.py               # 包入口，导出公共 API
│   ├── config.py                 # 配置管理
│   ├── models.py                 # 数据模型
│   ├── parser.py                 # HTML 解析
│   ├── storage.py                # 数据存储
│   └── scraper.py                # 爬虫核心
├── tests/                        # 测试
├── main.py                       # CLI 入口
├── pyproject.toml                # 项目配置
└── data/videos.db                # SQLite 数据库
```

## 2. 设计思路

### 原子化模块设计

每个模块职责单一，便于测试和维护：

| 模块 | 职责 | 依赖 |
|------|------|------|
| `config.py` | 读取配置（环境变量、.env） | pydantic-settings |
| `models.py` | 定义数据结构 | pydantic |
| `parser.py` | **纯函数**：HTML → 结构化数据 | beautifulsoup4, lxml |
| `storage.py` | 所有数据库操作 | sqlite-utils |
| `scraper.py` | 协调 HTTP 请求和数据流 | httpx, 上述所有 |

### 两阶段抓取（懒加载）

```
Phase 1: 列表页抓取 → 基础信息 (title, url, duration, views)
         ↓
Phase 2: 详情页抓取 → 完整信息 (tags, description, related)
```

**好处：**
- 可以先快速建立索引，后续按需补充详情
- 失败时可以只重试失败的阶段
- 支持断点续爬

### 增量更新策略

```python
# 正向模式: 从最新开始，遇到已存在则停止
for page in range(1, total):
    if video_exists(slug):
        break  # 停止

# 反向模式: 从最旧开始，适合完整归档
for page in range(total, 0, -1):
    # 继续抓取
```

## 3. 关键技术

### 异步 HTTP (httpx)

```python
# 配置连接池和超时
limits = httpx.Limits(max_connections=3, max_keepalive_connections=2)
timeout = httpx.Timeout(connect=5.0, read=30.0)

async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
    html = await client.get(url)
```

**关键配置：**
- `max_connections=3`: 限制并发连接数，避免被封
- `timeout`: 连接 5 秒，读取 30 秒
- `follow_redirects=True`: 自动跟随重定向

### HTML 解析 (BeautifulSoup + lxml)

```python
# 使用 lxml 解析器（比 html.parser 快）
soup = BeautifulSoup(html, "lxml")

# CSS 选择器提取数据
articles = soup.select("article")
for article in articles:
    title = article.select_one("h2 a").get_text()
    url = article.select_one("h2 a")["href"]
```

**解析器函数（纯函数）：**

```python
def parse_list_page(html: str, base_url: str) -> list[Video]:
    """纯函数：输入 HTML，输出结构化数据"""
    soup = BeautifulSoup(html, "lxml")
    videos = []
    for article in soup.select("article"):
        video = Video(title=..., slug=..., ...)
        videos.append(video)
    return videos
```

### 数据验证 (Pydantic)

```python
class Video(BaseModel):
    title: str
    slug: str
    video_url: str
    likes: int = 0
    views: int = 0
    scraped_at: datetime = Field(default_factory=datetime.now)

class VideoDetail(Video):
    description: str | None = None
    tags: list[Tag] = []
    # ... 更多字段
```

**好处：**
- 类型安全
- 自动验证
- IDE 自动补全

### SQLite 存储 (sqlite-utils)

```python
# 批量插入，忽略重复
db["videos"].insert_all(records, ignore=True, batch_size=100)

# 按条件查询
rows = db["videos"].rows_where("slug = ?", [slug], limit=1)

# 导出 CSV
db["videos"].to_csv("videos.csv")
```

**为什么不直接用 upsert？**

sqlite-utils 的 `upsert_all(pk="slug")` 在表主键为 `id` 时会有问题。解决方案：
1. 使用 `insert_all(ignore=True)` 处理重复
2. 更新时使用原生 SQL `UPDATE ... WHERE slug = ?`

## 4. 数据流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   httpx     │────▶│   parser    │────▶│   models    │
│  (HTTP请求)  │     │ (HTML解析)   │     │ (数据验证)   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │  storage    │
                                        │  (SQLite)   │
                                        └─────────────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   export    │
                                        │ (Neo4j CSV) │
                                        └─────────────┘
```

## 5. 知识图谱 Schema

### 节点类型

```cypher
// 视频
(:Video {
    id: INT,
    title: STRING,
    slug: STRING,
    views: INT,
    likes: INT,
    duration: STRING,
    description: STRING
})

// 标签
(:Tag {id: INT, name: STRING, slug: STRING})

// 分类
(:Category {id: INT, name: STRING, slug: STRING})
```

### 关系类型

```cypher
// 视频-标签
(Video)-[:HAS_TAG]->(Tag)

// 视频-分类
(Video)-[:BELONGS_TO]->(Category)

// 相关视频
(Video)-[:RELATED_TO {position: INT}]->(Video)
```

### SQLite 表映射

| SQLite 表 | Neo4j 节点/关系 |
|-----------|----------------|
| `videos` | Video 节点 |
| `tags` | Tag 节点 |
| `categories` | Category 节点 |
| `video_tags` | HAS_TAG 关系 |
| `video_categories` | BELONGS_TO 关系 |
| `video_related` | RELATED_TO 关系 |

## 6. 反爬策略

| 策略 | 实现 | 配置 |
|------|------|------|
| 请求延迟 | 随机延迟 | `delay_min=1.5, delay_max=3.0` |
| 并发限制 | 连接池 | `max_connections=3` |
| 重试机制 | 指数退避 | `max_retries=3` |
| User-Agent | 模拟浏览器 | Chrome UA |
| 失败队列 | 记录重试 | `failed_urls` 表 |

### 重试逻辑

```python
for attempt in range(max_retries + 1):
    try:
        response = await client.get(url)
        return response.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:  # Rate limited
            wait_time = 2 ** attempt * 5   # 5, 10, 20 秒
            await asyncio.sleep(wait_time)
        elif e.response.status_code >= 500:
            wait_time = 2 ** attempt       # 1, 2, 4 秒
            await asyncio.sleep(wait_time)
```

## 7. CLI 命令

```bash
# 全量抓取
python main.py full                    # 所有页面
python main.py full --pages 1-10       # 指定范围
python main.py full --reverse          # 从最旧开始
python main.py full --no-details       # 只抓列表页

# 增量更新
python main.py update                  # 从最新开始
python main.py update --reverse        # 从上次位置继续

# 数据管理
python main.py stats                   # 查看统计
python main.py retry                   # 重试失败 URL
python main.py clear-progress          # 清除进度

# 导出
python main.py export --format neo4j   # 导出 Neo4j CSV
python main.py export --format jsonl   # 导出 JSONL
```

## 8. 环境变量配置

```bash
# .env 文件
EROASMR_HTTP__DELAY_MIN=1.5
EROASMR_HTTP__DELAY_MAX=3.0
EROASMR_HTTP__MAX_CONNECTIONS=3
EROASMR_DB__PATH=data/videos.db
EROASMR_SCRAPER__REVERSE=false
LOG_LEVEL=INFO
```

## 9. 扩展建议

### 添加新字段

1. 在 `models.py` 添加字段
2. 在 `parser.py` 解析字段
3. 在 `storage.py` 更新 SQL

### 添加新数据源

1. 在 `parser.py` 添加新解析函数
2. 在 `scraper.py` 添加抓取逻辑

### 接入其他图数据库

1. 修改 `export` 命令
2. 生成对应格式的 CSV

## 10. 常见问题

### Q: 为什么每页只有 10 个视频？

网站的分页是动态加载的，HTML 中只包含部分视频。完整抓取需要分析 API 或使用无头浏览器。

### Q: 相关视频关系为 0？

"You May Be Interested In" 区域的 HTML 结构需要进一步分析，可能需要调整 `parse_detail_page` 中的选择器。

### Q: 如何加速抓取？

1. 减少 `delay_min` 和 `delay_max`（有被封风险）
2. 增加 `max_connections`（有被封风险）
3. 使用 `--no-details` 跳过详情页
