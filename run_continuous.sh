#!/bin/bash
# Continuous pipeline runner with disk space management
# Usage: ./run_continuous.sh [--batch-size N] [--min-disk-free P]
#
# This script continuously processes videos in batches, pausing when
# disk space is low. It's designed to run for extended periods.
#
# Features:
# - Processes videos in configurable batches
# - Pauses when disk space drops below threshold
# - Resumes when disk space is available
# - Automatic retry with exponential backoff
# - Detailed logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/continuous_$(date +%Y%m%d_%H%M%S).log"

# Configuration
BATCH_SIZE="${BATCH_SIZE:-5}"           # Videos per batch
MIN_DISK_FREE="${MIN_DISK_FREE:-15}"    # Minimum % free disk space
WAIT_LOW_DISK="${WAIT_LOW_DISK:-600}"   # Wait seconds when disk is low
WAIT_BETWEEN_BATCHES="${WAIT_BETWEEN_BATCHES:-60}"  # Wait between batches
MAX_RETRIES="${MAX_RETRIES:-3}"         # Max retries per batch
OUTPUT_DIR=""                            # Output directory for downloads

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --batch-size|-b)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --min-disk-free|-d)
            MIN_DISK_FREE="$2"
            shift 2
            ;;
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --batch-size N, -b N    Process N videos per batch (default: 5)"
            echo "  --min-disk-free P, -d P Pause when disk free < P% (default: 15)"
            echo "  --output DIR, -o DIR    Output directory for downloads"
            echo "  --help, -h              Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  BATCH_SIZE              Videos per batch"
            echo "  MIN_DISK_FREE           Minimum disk free %"
            echo "  WAIT_LOW_DISK           Seconds to wait when disk is low (default: 600)"
            echo "  WAIT_BETWEEN_BATCHES    Seconds between batches (default: 60)"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Create directories
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Get disk free percentage
get_disk_free() {
    df "$SCRIPT_DIR" | awk 'NR==2 {gsub(/%/, "", $5); print 100 - $5}'
}

# Get pending download count
get_pending_count() {
    cd "$SCRIPT_DIR"
    uv run python -c "
from eroasmr_scraper.storage import VideoStorage
storage = VideoStorage()
print(len(storage.get_pending_downloads()))
" 2>/dev/null || echo "0"
}

# Get download stats
get_download_stats() {
    cd "$SCRIPT_DIR"
    uv run python -c "
from eroasmr_scraper.storage import VideoStorage
storage = VideoStorage()
stats = storage.get_download_stats()
print(f'Total: {stats[\"total_videos\"]}, Completed: {stats[\"completed\"]}, Failed: {stats[\"failed\"]}, Pending: {stats[\"not_started\"] + stats[\"pending\"]}')
" 2>/dev/null || echo "Stats unavailable"
}

# Run a single batch
run_batch() {
    local batch_num=$1
    log "=========================================="
    log "Batch #$batch_num - Processing $BATCH_SIZE videos"
    log "=========================================="

    cd "$SCRIPT_DIR"

    # Build command with optional output directory
    local cmd="uv run python main.py pipeline --limit $BATCH_SIZE -v"
    if [[ -n "$OUTPUT_DIR" ]]; then
        cmd="$cmd --output $OUTPUT_DIR"
    fi
    log "Running: $cmd"

    if eval "$cmd" 2>&1 | tee -a "$LOG_FILE"; then
        return 0
    else
        return 1
    fi
}

# Main loop
main() {
    log "=========================================="
    log "Starting continuous pipeline"
    log "=========================================="
    log "Configuration:"
    log "  Batch size: $BATCH_SIZE videos"
    log "  Min disk free: ${MIN_DISK_FREE}%"
    log "  Wait on low disk: ${WAIT_LOW_DISK}s"
    log "  Wait between batches: ${WAIT_BETWEEN_BATCHES}s"
    log "  Max retries: $MAX_RETRIES"
    log ""

    local batch_num=0
    local consecutive_failures=0

    while true; do
        # Check disk space
        local disk_free=$(get_disk_free)
        log "Disk space: ${disk_free}% free"

        if [[ $disk_free -lt $MIN_DISK_FREE ]]; then
            log "WARNING: Disk space low (${disk_free}% < ${MIN_DISK_FREE}%)"
            log "Waiting ${WAIT_LOW_DISK}s for space to free up..."
            sleep $WAIT_LOW_DISK
            continue
        fi

        # Check if there are pending downloads
        local pending=$(get_pending_count)
        log "Pending downloads: $pending"

        if [[ $pending -eq 0 ]]; then
            log "No pending downloads. Waiting 60s before checking again..."
            log "Download stats: $(get_download_stats)"
            sleep 60
            continue
        fi

        # Run batch with retry
        local retry_count=0
        local success=false

        while [[ $retry_count -lt $MAX_RETRIES ]]; do
            batch_num=$((batch_num + 1))
            if run_batch $batch_num; then
                success=true
                consecutive_failures=0
                break
            else
                retry_count=$((retry_count + 1))
                consecutive_failures=$((consecutive_failures + 1))
                if [[ $retry_count -lt $MAX_RETRIES ]]; then
                    local wait_time=$((30 * retry_count))
                    log "Batch failed (attempt $retry_count/$MAX_RETRIES). Retrying in ${wait_time}s..."
                    sleep $wait_time
                fi
            fi
        done

        if [[ "$success" == "false" ]]; then
            log "ERROR: Batch failed after $MAX_RETRIES attempts"
            log "Consecutive failures: $consecutive_failures"

            if [[ $consecutive_failures -ge 5 ]]; then
                log "Too many consecutive failures. Waiting 5 minutes before continuing..."
                sleep 300
                consecutive_failures=0
            fi
        fi

        # Show stats
        log ""
        log "Download stats: $(get_download_stats)"
        log ""

        # Wait before next batch
        log "Waiting ${WAIT_BETWEEN_BATCHES}s before next batch..."
        sleep $WAIT_BETWEEN_BATCHES
    done
}

# Set up signal handlers
trap 'log "Received interrupt. Exiting..."; exit 0' SIGINT SIGTERM

# Run main
main
