#!/usr/bin/env bash
# Starts LiveKit server + frontend in the background, then runs the agent in the
# foreground of this same terminal — so the conversation transcript and per-component
# timing (VAD/STT/LLM/TTS) keep printing here, exactly like the old "Terminal 2".
#
# Ctrl+C in this terminal stops everything (agent + LiveKit + frontend).

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
CONDA_ENV="kotai"
mkdir -p "$LOG_DIR"

PIDS=()

cleanup() {
    echo ""
    echo "🛑 Stopping background services started by this script..."
    for pid in "${PIDS[@]:-}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

port_open() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- 3<&-
}

wait_for_port() {
    local port=$1 name=$2 tries=30
    for ((i = 0; i < tries; i++)); do
        if port_open "$port"; then
            echo "✅ $name is up (port $port)"
            return 0
        fi
        sleep 1
    done
    echo "⚠️  $name didn't come up on port $port within ${tries}s — check $LOG_DIR/"
    return 1
}

# Make sure `conda` is usable even in a non-interactive shell.
if ! command -v conda >/dev/null 2>&1; then
    for conda_sh in "$HOME/miniconda/etc/profile.d/conda.sh" \
                    "$HOME/miniconda3/etc/profile.d/conda.sh" \
                    "$HOME/anaconda3/etc/profile.d/conda.sh"; do
        [ -f "$conda_sh" ] && source "$conda_sh" && break
    done
fi

if port_open 11434; then
    echo "✅ Ollama already running (port 11434)"
else
    echo "🚀 Starting Ollama (no service/process found on port 11434)..."
    ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    PIDS+=("$!")
    wait_for_port 11434 "Ollama" || tail -n 20 "$LOG_DIR/ollama.log"
fi

echo "🚀 Starting LiveKit server..."
livekit-server --dev > "$LOG_DIR/livekit.log" 2>&1 &
PIDS+=("$!")
wait_for_port 7880 "LiveKit server" || tail -n 20 "$LOG_DIR/livekit.log"

echo "🚀 Starting frontend (pnpm dev)..."
(cd "$ROOT_DIR/frontend" && pnpm dev) > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=("$!")
wait_for_port 3000 "Frontend" || tail -n 20 "$LOG_DIR/frontend.log"

echo ""
echo "🎙️  Starting agent — conversation + timing print below (Ctrl+C to stop everything):"
echo "-----------------------------------------------------------------------------"
cd "$ROOT_DIR/backend"
conda run -n "$CONDA_ENV" --no-capture-output python agent.py dev
