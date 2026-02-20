#!/bin/bash
# Monitor zhumianwang scraper and start parallel pipeline in PARALLEL mode
# Pipeline starts when detail phase begins, not when scraping completes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Monitoring zhumianwang scraper (PARALLEL MODE)..."
echo "Pipeline will start when detail phase begins."
echo ""

pipeline_started=false

while true; do
    # Check if scraper session is still running
    if ! tmux has-session -t zhumianwang-scraper 2>/dev/null; then
        echo ""
        echo "[$(date '+%H:%M:%S')] Scraper session ended."
        if [ "$pipeline_started" = false ]; then
            echo "Starting pipeline now..."
            break
        else
            echo "Pipeline already running. Done monitoring."
            exit 0
        fi
    fi

    # Capture last 50 lines
    output=$(tmux capture-pane -t zhumianwang-scraper -p -S -50 2>/dev/null)

    # Check for detail phase or completion - start pipeline immediately
    if [ "$pipeline_started" = false ]; then
        if echo "$output" | grep -q "Details:"; then
            echo ""
            echo "[$(date '+%H:%M:%S')] Detail phase detected! Starting pipeline in parallel..."
            pipeline_started=true

            # Kill old pipeline session if exists
            tmux kill-session -t zhumianwang-pipeline 2>/dev/null

            # Start parallel pipeline
            tmux new-session -d -s zhumianwang-pipeline \
                "cd $SCRIPT_DIR && uv run eroasmr-scraper parallel --site zhumianwang --verbose 2>&1 | tee logs/pipeline_\$(date +%Y%m%d_%H%M%S).log"

            echo "Pipeline started in tmux session: zhumianwang-pipeline"
        fi
    fi

    # Check current progress
    current_page=$(echo "$output" | grep -oE "Page [0-9]+/[0-9]+" | tail -1)
    detail_progress=$(echo "$output" | grep -oE "Details: [0-9]+/[0-9]+" | tail -1)

    if [ -n "$detail_progress" ]; then
        echo -ne "\r[$(date '+%H:%M:%S')] Detail: $detail_progress | Pipeline: running    "
    elif [ -n "$current_page" ]; then
        echo -ne "\r[$(date '+%H:%M:%S')] List: $current_page | Pipeline: waiting        "
    fi

    # Check for completion
    if echo "$output" | grep -q "Complete!\|Scraping complete"; then
        echo ""
        echo "[$(date '+%H:%M:%S')] Scraping complete!"

        if [ "$pipeline_started" = false ]; then
            echo "Starting pipeline now..."
            break
        else
            echo "Pipeline continues running in background."
            exit 0
        fi
    fi

    sleep 5
done

echo ""
echo "=========================================="
echo "Starting parallel download-upload pipeline"
echo "=========================================="

# Kill old pipeline session if exists
tmux kill-session -t zhumianwang-pipeline 2>/dev/null

# Start parallel pipeline
tmux new-session -d -s zhumianwang-pipeline \
    "cd $SCRIPT_DIR && uv run eroasmr-scraper parallel --site zhumianwang --verbose 2>&1 | tee logs/pipeline_\$(date +%Y%m%d_%H%M%S).log"

echo "Pipeline started in tmux session: zhumianwang-pipeline"
echo "To view: tmux attach -t zhumianwang-pipeline"
echo "To detach: Ctrl+B then D"
