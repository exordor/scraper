# CLAUDE.md - eroasmr-scraper

Video metadata scraper for eroasmr.com with Neo4j export support.

## Core Principles

### 1. Atomic Functions

Each function does one thing well:

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Configuration management | pydantic-settings |
| `models.py` | Data models | pydantic |
| `parser.py` | HTML parsing (pure functions) | beautifulsoup4, lxml |
| `storage.py` | Database operations | sqlite-utils |
| `scraper.py` | Scraping orchestration | httpx, all above |

**Guidelines:**
- Parser functions are pure: input HTML → output structured data
- Storage methods handle all database operations
- Scraper coordinates HTTP requests and data flow

### 2. Lazy Loading

Two-phase scraping for efficiency:

```
Phase 1: List pages → Basic info (title, URL, duration, views)
Phase 2: Detail pages → Full metadata (tags, description, related)
```

**Usage:**
```python
# Quick scan without details
python main.py full --pages 1-10 --no-details

# Full scrape with details
python main.py full --pages 1-10
```

### 3. Incremental Updates

Avoid redundant scraping:

```python
# Forward mode: stop at first existing video
python main.py update

# Reverse mode: continue from last position
python main.py update --reverse
```

### 4. Reverse Scraping

By default, videos are listed newest-first. Use `--reverse` to scrape oldest-first:

```python
# Scrape from oldest (page 198) to newest (page 1)
python main.py full --reverse

# Continue incremental from last position
python main.py update --reverse
```

## Development

### Setup

```bash
cd ~/code/python/eroasmr-scraper
uv sync
```

### Commands

```bash
# Full scrape (first 3 pages)
python main.py full --pages 1-3

# Full scrape with reverse (oldest first)
python main.py full --reverse

# Incremental update
python main.py update

# View statistics
python main.py stats

# Export to Neo4j
python main.py export --format neo4j --output ./neo4j_import/
```

### Code Quality

```bash
# Format and lint
ruff format . && ruff check .

# Type check
mypy src/

# Run tests
pytest
```

## Git Conventions

Use Conventional Commits:

```
feat(scraper): add reverse scraping mode
fix(parser): handle missing duration field
docs: update README with CLI usage
test(parser): add unit tests for list page parser
refactor(storage): optimize batch inserts
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/eroasmr_scraper

# Run specific test
pytest tests/test_parser.py -v
```

## Architecture

```
HTTP Request → HTML → Parser → Pydantic Model → SQLite Storage
                                    ↓
                            Neo4j Export (CSV)
```

### Data Flow

1. **Scraper** fetches HTML via httpx
2. **Parser** extracts structured data (pure functions)
3. **Models** validate with Pydantic
4. **Storage** persists to SQLite via sqlite-utils
5. **Export** generates Neo4j-compatible CSVs
