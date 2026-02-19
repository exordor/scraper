#!/bin/bash
# Disk space monitor for eroasmr-scraper pipeline
# Pauses downloads when disk space is low, stops pipeline only if critical
#
# Usage: ./check_disk_space.sh [--min-free GB] [--critical-free GB] [--interval SECONDS]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/disk_monitor.log"
PAUSE_FILE="$SCRIPT_DIR/.pause_downloads"

# Default values
MIN_FREE_GB="${MIN_FREE_GB:-15}"        # Pause downloads below this
CRITICAL_FREE_GB="${CRITICAL_FREE_GB:-5}" # Stop pipeline below this
CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
PIPELINE_SESSION="pipeline"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --min-free|-m)
            MIN_FREE_GB="$2"
            shift 2
            ;;
        --critical-free|-c)
            CRITICAL_FREE_GB="$2"
            shift 2
            ;;
        --interval|-i)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --session|-s)
            PIPELINE_SESSION="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --min-free GB, -m GB     Pause downloads below this (default: 15)"
            echo "  --critical-free GB, -c GB Stop pipeline below this (default: 5)"
            echo "  --interval SEC, -i SEC   Check interval in seconds (default: 60)"
            echo "  --session NAME, -s NAME  Tmux session name (default: pipeline)"
            echo "  --help, -h               Show this help message"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Get free disk space in GB
get_free_gb() {
    df -BG /root | awk 'NR==2 {gsub(/G/, "", $4); print $4}'
}

# Pause downloads (create pause file)
pause_downloads() {
    if [[ ! -f "$PAUSE_FILE" ]]; then
        log "PAUSING downloads - creating pause file"
        touch "$PAUSE_FILE"
    fi
}

# Resume downloads (remove pause file)
resume_downloads() {
    if [[ -f "$PAUSE_FILE" ]]; then
        log "RESUMING downloads - removing pause file"
        rm -f "$PAUSE_FILE"
    fi
}

# Stop pipeline completely
stop_pipeline() {
    log "CRITICAL: Stopping pipeline session: $PIPELINE_SESSION"
    rm -f "$PAUSE_FILE"  # Clean up pause file

    # Send Ctrl+C to the tmux session
    tmux send-keys -t "$PIPELINE_SESSION" C-c 2>/dev/null || true

    # Wait a moment
    sleep 2

    # Kill the session if it still exists
    if tmux has-session -t "$PIPELINE_SESSION" 2>/dev/null; then
        log "Killing tmux session: $PIPELINE_SESSION"
        tmux kill-session -t "$PIPELINE_SESSION" 2>/dev/null || true
    fi

    log "Pipeline stopped due to critical disk space"
}

# Check if pipeline is running
is_pipeline_running() {
    tmux has-session -t "$PIPELINE_SESSION" 2>/dev/null
}

# Main monitoring loop
log "=========================================="
log "Starting disk space monitor"
log "=========================================="
log "Configuration:"
log "  Pause downloads below: ${MIN_FREE_GB}GB"
log "  Stop pipeline below: ${CRITICAL_FREE_GB}GB"
log "  Check interval: ${CHECK_INTERVAL}s"
log "  Pipeline session: $PIPELINE_SESSION"
log ""

while true; do
    # Get current free space
    FREE_GB=$(get_free_gb)

    # Log current status
    log "Disk free: ${FREE_GB}GB (pause: ${MIN_FREE_GB}GB, critical: ${CRITICAL_FREE_GB}GB)"

    # Check if critical - stop everything
    if [[ $FREE_GB -lt $CRITICAL_FREE_GB ]]; then
        log "CRITICAL: Disk space critical! ${FREE_GB}GB < ${CRITICAL_FREE_GB}GB"

        if is_pipeline_running; then
            stop_pipeline
            log "Waiting for disk space to recover before you can restart..."
        fi

    # Check if low - pause downloads only
    elif [[ $FREE_GB -lt $MIN_FREE_GB ]]; then
        log "LOW: Disk space low! ${FREE_GB}GB < ${MIN_FREE_GB}GB"

        if is_pipeline_running; then
            pause_downloads
            log "Downloads paused. Uploads continue. Waiting for space to free up..."
        fi

    # Disk space OK - resume if paused
    else
        resume_downloads

        if [[ $FREE_GB -lt $((MIN_FREE_GB + 5)) ]]; then
            log "Disk space recovering: ${FREE_GB}GB"
        fi
    fi

    # Check if pipeline session exists
    if ! is_pipeline_running; then
        log "Pipeline session not found. Monitor continuing..."
    fi

    sleep "$CHECK_INTERVAL"
done
