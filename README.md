# eroasmr-scraper

Video metadata scraper for eroasmr.com with Neo4j export support.

## Features

- Full and incremental scraping modes
- Reverse scraping (oldest to newest)
- SQLite storage with sqlite-utils
- Neo4j CSV export for knowledge graph construction
- Async HTTP with rate limiting

## Installation

```bash
uv sync
```

## Usage

```bash
# Test scrape (first 3 pages)
python main.py full --pages 1-3

# Full scrape (reverse - oldest first)
python main.py full --reverse

# Incremental update
python main.py update

# View statistics
python main.py stats

# Export for Neo4j
python main.py export --format neo4j
```

## License

MIT
