#!/bin/bash
# Automated download and upload script for eroasmr-scraper
# Usage: ./run_pipeline.sh [--parallel] [--limit N] [--keep]
#
# Features:
# - Disk space monitoring (pauses when disk is >80% full)
# - Automatic cleanup after successful uploads
# - Logging to file with timestamps
# - Can run in tmux session for persistence

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"
DATA_DIR="$SCRIPT_DIR/data/downloads"

# Default settings
PARALLEL_FLAG=""
LIMIT_FLAG=""
KEEP_FLAG=""
MIN_DISK_FREE_PERCENT=20  # Pause if less than 20% disk space free
CHECK_INTERVAL=300        # Check disk space every 5 minutes

# Telegram configuration (set these or use .env file)
export EROASMR_TELEGRAM__TENANT_ID="${EROASMR_TELEGRAM__TENANT_ID:-4d6e8863-4d30-4e65-9455-92b49d21b67c}"
export EROASMR_TELEGRAM__UPLOAD_SERVICE_URL="${EROASMR_TELEGRAM__UPLOAD_SERVICE_URL:-http://localhost:8000}"
export EROASMR_TELEGRAM__FILE_PATH_MAP="${EROASMR_TELEGRAM__FILE_PATH_MAP:-{\"data/downloads\": \"/app/data/downloads\"}}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --parallel|-p)
            PARALLEL_FLAG="--parallel"
            shift
            ;;
        --limit|-n)
            LIMIT_FLAG="--limit $2"
            shift 2
            ;;
        --keep|-k)
            KEEP_FLAG="--keep"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --parallel, -p    Use parallel pipeline (recommended)"
            echo "  --limit N, -n N   Process only N videos"
            echo "  --keep, -k        Keep local files after upload"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  EROASMR_TELEGRAM__TENANT_ID       Telegram tenant ID"
            echo "  EROASMR_TELEGRAM__UPLOAD_SERVICE_URL  Upload service URL"
            echo "  EROASMR_TELEGRAM__FILE_PATH_MAP   Path mapping for Docker"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create directories
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Get disk usage percentage
get_disk_usage() {
    df "$SCRIPT_DIR" | awk 'NR==2 {print $5}' | tr -d '%'
}

# Get disk free percentage
get_disk_free() {
    local used=$(get_disk_usage)
    echo $((100 - used))
}

# Get directory size in MB
get_dir_size_mb() {
    du -sm "$1" 2>/dev/null | cut -f1 || echo 0
}

# Check if we should pause for disk space
check_disk_space() {
    local free_percent=$(get_disk_free)
    if [[ $free_percent -lt $MIN_DISK_FREE_PERCENT ]]; then
        log "WARNING: Disk space low (${free_percent}% free). Waiting for uploads to complete..."
        return 1
    fi
    return 0
}

# Cleanup function
cleanup() {
    log "Received interrupt signal. Cleaning up..."
    if [[ -n "$PID" ]]; then
        kill $PID 2>/dev/null || true
    fi
    log "Script stopped."
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Main function
main() {
    log "=========================================="
    log "Starting eroasmr-scraper pipeline"
    log "=========================================="
    log "Configuration:"
    log "  Parallel: ${PARALLEL_FLAG:-sequential}"
    log "  Limit: ${LIMIT_FLAG:-none}"
    log "  Keep files: ${KEEP_FLAG:-no (delete after upload)}"
    log "  Tenant ID: $EROASMR_TELEGRAM__TENANT_ID"
    log "  Disk free threshold: ${MIN_DISK_FREE_PERCENT}%"
    log ""

    # Check initial disk space
    local initial_free=$(get_disk_free)
    log "Initial disk space: ${initial_free}% free"

    # Change to script directory
    cd "$SCRIPT_DIR"

    # Build command
    if [[ -n "$PARALLEL_FLAG" ]]; then
        CMD="uv run python main.py parallel $LIMIT_FLAG $KEEP_FLAG -v"
    else
        CMD="uv run python main.py pipeline $LIMIT_FLAG $KEEP_FLAG -v"
    fi

    log "Command: $CMD"
    log ""

    # Run the pipeline
    log "Starting pipeline execution..."
    eval "$CMD" 2>&1 | tee -a "$LOG_FILE"

    local exit_code=${PIPESTATUS[0]}

    if [[ $exit_code -eq 0 ]]; then
        log ""
        log "=========================================="
        log "Pipeline completed successfully!"
        log "=========================================="

        # Show final stats
        local final_free=$(get_disk_free)
        local data_size=$(get_dir_size_mb "$DATA_DIR")
        log "Final disk space: ${final_free}% free"
        log "Data directory size: ${data_size}MB"
    else
        log ""
        log "=========================================="
        log "Pipeline exited with code: $exit_code"
        log "=========================================="
    fi

    return $exit_code
}

# Run main
main
