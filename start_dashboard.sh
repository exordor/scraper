#!/bin/bash
# Start the web dashboard
# Usage: ./start_dashboard.sh [--port 8080] [--host 0.0.0.0]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-8080}"
HOST="${2:-0.0.0.0}"

echo "Starting EroASMR Scraper Dashboard..."
echo "URL: http://localhost:$PORT"
echo ""
echo "Press Ctrl+C to stop"
echo ""

uv run python -c "from eroasmr_scraper.web_dashboard import run_dashboard; run_dashboard(host='$HOST', port=$PORT)"
