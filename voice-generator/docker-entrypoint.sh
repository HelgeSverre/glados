#!/bin/bash
set -e

echo "=========================================="
echo "GLaDOS Voice Generator - Docker Container"
echo "=========================================="

# Ensure data directories exist
mkdir -p /app/voice-generator/data
mkdir -p /app/voice-generator/public/audio

# Start TTS worker in background
echo "Starting TTS worker..."
cd /app
uv run python voice-generator/worker/processor.py &
WORKER_PID=$!
echo "Worker started (PID: $WORKER_PID)"

# Trap signals for graceful shutdown
cleanup() {
    echo "Shutting down..."
    kill $WORKER_PID 2>/dev/null || true
    wait $WORKER_PID 2>/dev/null || true
    echo "Goodbye."
    exit 0
}
trap cleanup SIGTERM SIGINT

# Start Bun web server in foreground
echo "Starting web server on port ${PORT:-3000}..."
cd /app/voice-generator
exec bun run src/index.ts
