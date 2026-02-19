#!/bin/bash
# Master script to start everything
# Usage: ./start_all.sh [--pipeline] [--dashboard] [--port 8080]
#
# This script starts:
# 1. Web dashboard (port 8080 by default)
# 2. Pipeline in continuous mode (if --pipeline flag is set)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default settings
START_PIPELINE=false
START_DASHBOARD=true
DASHBOARD_PORT=8080
BATCH_SIZE=5

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --pipeline|-p)
            START_PIPELINE=true
            shift
            ;;
        --dashboard|-d)
            START_DASHBOARD=true
            shift
            ;;
        --no-dashboard)
            START_DASHBOARD=false
            shift
            ;;
        --port)
            DASHBOARD_PORT="$2"
            shift 2
            ;;
        --batch-size|-b)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --pipeline, -p       Start pipeline in continuous mode"
            echo "  --dashboard, -d      Start web dashboard (default)"
            echo "  --no-dashboard       Don't start dashboard"
            echo "  --port PORT          Dashboard port (default: 8080)"
            echo "  --batch-size N, -b N Videos per batch (default: 5)"
            echo "  --help, -h           Show this help"
            echo ""
            echo "Examples:"
            echo "  $0 --pipeline                    # Start dashboard + pipeline"
            echo "  $0 --pipeline --port 9000        # Custom port"
            echo "  $0                               # Dashboard only"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Check tmux
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed. Run: apt install tmux"
    exit 1
fi

echo "=========================================="
echo "EroASMR Scraper Launcher"
echo "=========================================="
echo ""

# Export environment variables
export EROASMR_TELEGRAM__TENANT_ID="${EROASMR_TELEGRAM__TENANT_ID:-4d6e8863-4d30-4e65-9455-92b49d21b67c}"
export EROASMR_TELEGRAM__UPLOAD_SERVICE_URL="${EROASMR_TELEGRAM__UPLOAD_SERVICE_URL:-http://localhost:8000}"
export EROASMR_TELEGRAM__FILE_PATH_MAP="${EROASMR_TELEGRAM__FILE_PATH_MAP:-{\"data/downloads\": \"/app/data/downloads\"}}"

echo "Configuration:"
echo "  Tenant ID: $EROASMR_TELEGRAM__TENANT_ID"
echo "  Upload Service: $EROASMR_TELEGRAM__UPLOAD_SERVICE_URL"
echo ""

# Kill existing sessions
for session in eroasmr-dashboard eroasmr-pipeline; do
    if tmux has-session -t $session 2>/dev/null; then
        echo "Killing existing session: $session"
        tmux kill-session -t $session 2>/dev/null || true
    fi
done

# Start dashboard
if [[ "$START_DASHBOARD" == "true" ]]; then
    echo "Starting web dashboard on port $DASHBOARD_PORT..."
    tmux new-session -d -s eroasmr-dashboard -c "$SCRIPT_DIR" \
        "uv run python -c \"from eroasmr_scraper.web_dashboard import run_dashboard; run_dashboard(port=$DASHBOARD_PORT)\"; exec bash"
    echo "  Dashboard URL: http://localhost:$DASHBOARD_PORT"
    echo "  Session: eroasmr-dashboard"
fi

# Start pipeline
if [[ "$START_PIPELINE" == "true" ]]; then
    echo ""
    echo "Starting continuous pipeline (batch size: $BATCH_SIZE)..."
    tmux new-session -d -s eroasmr-pipeline -c "$SCRIPT_DIR" \
        "bash $SCRIPT_DIR/run_continuous.sh --parallel --batch-size $BATCH_SIZE; exec bash"
    echo "  Session: eroasmr-pipeline"
fi

echo ""
echo "=========================================="
echo "Started!"
echo "=========================================="
echo ""
echo "Tmux sessions:"
tmux ls 2>/dev/null || echo "  (none)"
echo ""
echo "Commands:"
echo "  Attach to dashboard: tmux attach -t eroasmr-dashboard"
echo "  Attach to pipeline:  tmux attach -t eroasmr-pipeline"
echo "  List sessions:       tmux ls"
echo "  Kill all:            tmux kill-session -t eroasmr-dashboard; tmux kill-session -t eroasmr-pipeline"
echo ""

if [[ "$START_DASHBOARD" == "true" ]]; then
    echo "Open dashboard: http://localhost:$DASHBOARD_PORT"
fi
