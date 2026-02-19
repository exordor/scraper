#!/bin/bash
# Start pipeline in a tmux session for persistence
# Usage: ./start_tmux.sh [--parallel] [--limit N] [--keep]
#
# This script starts the pipeline in a tmux session that continues
# running even after you disconnect from the terminal.
#
# To attach to the session: tmux attach -t eroasmr
# To detach from session: Ctrl+B then D
# To list sessions: tmux ls
# To kill session: tmux kill-session -t eroasmr

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_NAME="eroasmr"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed."
    echo "Install it with: apt install tmux"
    exit 1
fi

# Check if session already exists
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists."
    echo ""
    echo "Options:"
    echo "  1. Attach to existing session: tmux attach -t $SESSION_NAME"
    echo "  2. Kill and restart: tmux kill-session -t $SESSION_NAME && $0 $@"
    exit 1
fi

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Start new tmux session
echo "Starting pipeline in tmux session '$SESSION_NAME'..."
echo ""
echo "Useful commands:"
echo "  Attach to session:  tmux attach -t $SESSION_NAME"
echo "  Detach from session: Ctrl+B then D"
echo "  List sessions:      tmux ls"
echo "  Kill session:       tmux kill-session -t $SESSION_NAME"
echo "  View log file:      tail -f $SCRIPT_DIR/logs/pipeline_*.log"
echo ""

# Run the pipeline script in tmux
tmux new-session -d -s $SESSION_NAME -c "$SCRIPT_DIR" \
    "bash $SCRIPT_DIR/run_pipeline.sh $@; exec bash"

echo "Pipeline started in background."
echo "Attach to see progress: tmux attach -t $SESSION_NAME"
