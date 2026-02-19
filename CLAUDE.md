# CLAUDE.md - eroasmr-scraper

Multi-site video metadata scraper with download and upload pipeline support.

## Supported Sites

| Site | URL | Features |
|------|-----|----------|
| EroAsmr | eroasmr.com | Full metadata, tags, categories |
| 助眠网 | zhumianwang.com | Full metadata, download links (requires login) |

## Core Principles

### 1. Multi-Site Architecture

Abstract factory pattern for site implementations:

```
base/           → Abstract classes (BaseSiteParser, BaseSiteScraper, BaseVideo)
sites/eroasmr/  → EroAsmr implementation
sites/zhumianwang/ → Zhumianwang implementation
factory.py      → ScraperFactory for site registration
```

**Guidelines:**
- Each site has its own `models.py`, `parser.py`, `scraper.py`
- Site-specific fields (e.g., `region`, `download_url`) use optional types
- Storage uses `site_id` column to distinguish data sources

### 2. Atomic Functions

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `config.py` | Multi-site configuration | pydantic-settings |
| `base/models.py` | Base data models | pydantic |
| `sites/{site}/models.py` | Site-specific models | pydantic |
| `sites/{site}/parser.py` | HTML parsing (pure functions) | beautifulsoup4, lxml |
| `storage.py` | Database operations (with site_id) | sqlite-utils |
| `factory.py` | Scraper factory | - |

### 3. Lazy Loading

Two-phase scraping for efficiency:

```
Phase 1: List pages → Basic info (title, URL, duration, views)
Phase 2: Detail pages → Full metadata (tags, description, related)
Phase 3: Play pages → Download links (zhumianwang only, requires login)
```

### 4. Incremental & Reverse Scraping

```bash
# Forward mode: stop at first existing video
eroasmr-scraper update

# Reverse mode: scrape oldest-first, continue from last position
eroasmr-scraper update --reverse
```

## Development

### Setup

```bash
cd ~/code/python/eroasmr-scraper
uv sync
```

### Commands

```bash
# List available sites
uv run eroasmr-scraper sites

# Full scrape (default site: eroasmr)
uv run eroasmr-scraper full --pages 1-3

# Scrape specific site
uv run eroasmr-scraper full --site zhumianwang --pages 1-3
uv run eroasmr-scraper full -s zhumianwang -p 1-3

# View statistics
uv run eroasmr-scraper stats
uv run eroasmr-scraper stats --site zhumianwang

# Export to Neo4j
uv run eroasmr-scraper export --format neo4j --output ./neo4j_import/
```

### Code Quality

```bash
# Format and lint
uv run ruff format . && uv run ruff check .

# Type check
uv run mypy src/

# Run tests
uv run pytest
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/eroasmr_scraper

# Run specific test
uv run pytest tests/test_parser.py -v
```

## Project Structure

```
src/eroasmr_scraper/
├── base/                    # Abstract base classes
│   ├── models.py           # BaseVideo, BaseVideoDetail, etc.
│   ├── parser.py           # BaseSiteParser
│   └── scraper.py          # BaseSiteScraper
├── sites/                   # Site-specific implementations
│   ├── eroasmr/
│   │   ├── models.py
│   │   └── parser.py
│   └── zhumianwang/
│       ├── models.py
│       ├── parser.py
│       └── play_parser.py  # Download link extraction
├── auth/                    # Authentication modules
│   └── playwright_auth.py  # Playwright cookie extraction
├── factory.py              # ScraperFactory
├── storage.py              # SQLite storage with site_id
├── config.py               # Multi-site configuration
├── cli.py                  # Typer CLI commands
├── downloader.py           # Video download logic
├── pipeline.py             # Download-upload pipeline
└── parallel_pipeline.py    # Parallel processing
```

## Architecture

```
HTTP Request → HTML → SiteParser → Pydantic Model → SQLite Storage (with site_id)
                                    ↓
                            Neo4j Export (CSV)
```

## Adding New Sites

1. Create `src/eroasmr_scraper/sites/{site_id}/` directory
2. Implement `models.py` with Video/VideoDetail inheriting from base models
3. Implement `parser.py` with Parser inheriting from BaseSiteParser
4. Register in `factory.py`
5. Add configuration in `config.py`

## Git Conventions

Use Conventional Commits:

```
feat(scraper): add zhumianwang site support
fix(parser): handle missing duration field
docs: update README with multi-site usage
test(zhumianwang): add parser tests
refactor(storage): add site_id column support
```
