# eroasmr-scraper

Video metadata scraper for eroasmr.com with download and upload pipeline support.

## Features

- Full and incremental scraping modes
- Reverse scraping (oldest to newest)
- SQLite storage with sqlite-utils
- Neo4j CSV export for knowledge graph construction
- Video download with resume support
- Download-upload pipeline framework
- Extensible uploader system (Telegram, Google Drive, etc.)

## Installation

```bash
uv sync
```

## CLI Commands

### Scraping Commands

```bash
# Test scrape (first 3 pages)
eroasmr-scraper full --pages 1-3

# Full scrape (reverse - oldest first)
eroasmr-scraper full --reverse

# Incremental update
eroasmr-scraper update

# Continue from last position (oldest-first mode)
eroasmr-scraper update --reverse

# Retry failed URLs
eroasmr-scraper retry

# Refresh duration values (when parser is fixed)
eroasmr-scraper refresh-durations
eroasmr-scraper refresh-durations --pages 1-10
```

### Statistics & Verification

```bash
# View database statistics
eroasmr-scraper stats

# Verify data integrity
eroasmr-scraper verify

# View download statistics
eroasmr-scraper download-stats

# Show uploader status
eroasmr-scraper uploaders
```

### Export Commands

```bash
# Export for Neo4j
eroasmr-scraper export --format neo4j

# Export to JSONL
eroasmr-scraper export --format jsonl --output videos.jsonl
```

### Download Commands

```bash
# Download all pending videos
eroasmr-scraper download

# Download with limit
eroasmr-scraper download --limit 10

# Retry failed downloads
eroasmr-scraper download --retry

# Custom output directory
eroasmr-scraper download -o ./my_videos

# Reset download status (for server migration)
eroasmr-scraper reset-downloads
eroasmr-scraper reset-downloads --yes  # Skip confirmation
```

### Pipeline Commands

```bash
# Download and upload (deletes local files after success)
eroasmr-scraper pipeline

# Process with limit
eroasmr-scraper pipeline --limit 10

# Keep local files after upload
eroasmr-scraper pipeline --keep

# Custom output directory
eroasmr-scraper pipeline -o ./videos -n 5

# Retry failed downloads
eroasmr-scraper pipeline --retry
```

### Parallel Pipeline Commands

```bash
# Run parallel download-upload (recommended for large batches)
eroasmr-scraper parallel

# Process with limit
eroasmr-scraper parallel --limit 100

# Keep local files after upload
eroasmr-scraper parallel --keep

# Larger queue size for faster throughput
eroasmr-scraper parallel --queue-size 20
```

### Utility Commands

```bash
# Clear scraping progress (for fresh start)
eroasmr-scraper clear-progress

# Show version
eroasmr-scraper --version
```

## Command Options

### `full` - Full Scrape

| Option | Description |
|--------|-------------|
| `--pages`, `-p` | Page range (e.g., '1-10' or '5') |
| `--reverse`, `-r` | Scrape from oldest to newest |
| `--no-details` | Skip detail page scraping |
| `--verbose` | Enable debug logging |

### `update` - Incremental Update

| Option | Description |
|--------|-------------|
| `--reverse`, `-r` | Continue from last position |
| `--no-details` | Skip detail page scraping |
| `--verbose` | Enable debug logging |

### `download` - Download Videos

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output directory (default: data/downloads) |
| `--limit`, `-n` | Maximum number of videos to download |
| `--retry` | Retry failed downloads |
| `--verbose`, `-v` | Enable debug logging |

### `pipeline` - Download-Upload Pipeline

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output directory (default: data/downloads) |
| `--limit`, `-n` | Maximum number of videos to process |
| `--retry` | Retry failed downloads |
| `--keep`, `-k` | Keep local files after upload |
| `--verbose`, `-v` | Enable debug logging |

### `parallel` - Parallel Download-Upload Pipeline

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output directory (default: data/downloads) |
| `--limit`, `-n` | Maximum number of videos to process |
| `--retry` | Retry failed downloads |
| `--keep`, `-k` | Keep local files after upload |
| `--queue-size` | Max items in download queue (default: 10) |
| `--verbose`, `-v` | Enable debug logging |

### `export` - Export Data

| Option | Description |
|--------|-------------|
| `--format`, `-f` | Export format: neo4j, jsonl (default: neo4j) |
| `--output`, `-o` | Output directory/file |

## Data Directory Structure

```
data/
├── videos.db              # SQLite database
├── downloads/             # Downloaded video files
│   └── {slug}.mp4
└── download_archive.txt   # yt-dlp archive for resume
```

## License

MIT
