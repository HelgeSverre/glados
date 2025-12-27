# GLaDOS TTS

# Default recipe shows available commands
default:
    @just --list

# Google Drive file ID for models (from https://github.com/R2D2FISH/glados-tts)
models_file_id := "1TRJtctjETgVVD5p7frSVPmgw8z8FFtjD"

# Install dependencies and download models
[group('setup')]
setup: install download-models
    @echo "Setup complete. Run 'just serve' to start the web server."

# Install Python dependencies with uv
[group('setup')]
install:
    uv venv
    uv pip install -r requirements.txt

# Download and extract models from Google Drive
[group('setup')]
download-models:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -d "models" ] && [ -f "models/glados-new.pt" ]; then
        echo "Models already downloaded"
        exit 0
    fi
    echo "Downloading models from Google Drive..."
    uv pip install gdown
    uv run gdown "{{models_file_id}}" -O models.zip
    echo "Extracting models..."
    unzip -o models.zip
    rm models.zip
    echo "Models ready"

# Start web server
[group('dev')]
serve:
    uv run python web/server.py

# Say something in GLaDOS's voice
[group('dev')]
say text:
    uv run python glados.py "{{text}}"

# Have GLaDOS respond to you (AI mode with Claude)
[group('dev')]
speak text:
    uv run python glados.py --ai "{{text}}"

# Clean up generated audio files
[group('dev')]
clean:
    rm -f output.wav glados-tts/output.wav
    rm -f web/audio/*.wav

# Build Docker image
[group('docker')]
docker-build:
    docker compose build

# Start Docker container
[group('docker')]
docker-up:
    docker compose up

# Start Docker container in background
[group('docker')]
docker-up-detached:
    docker compose up -d

# Stop Docker container
[group('docker')]
docker-down:
    docker compose down

# View Docker logs
[group('docker')]
docker-logs:
    docker compose logs -f

# === Voice Generator ===

# Setup voice generator (install Bun dependencies)
[group('voice')]
voice-setup:
    cd voice-generator && bun install
    mkdir -p voice-generator/data
    mkdir -p voice-generator/public/audio

# Start voice generator web server
[group('voice')]
voice-serve:
    cd voice-generator && bun run start

# Start voice generator web server (development mode with hot reload)
[group('voice')]
voice-dev:
    cd voice-generator && bun run dev

# Start voice generator TTS worker
[group('voice')]
voice-worker:
    uv run python voice-generator/worker/processor.py

# Start both voice generator services (web + worker)
[group('voice')]
voice-start:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting Voice Generator..."
    echo "Web server: http://localhost:3000"

    # Start worker in background
    uv run python voice-generator/worker/processor.py &
    WORKER_PID=$!

    # Trap to kill worker on exit
    trap "kill $WORKER_PID 2>/dev/null" EXIT

    # Start web server (foreground)
    cd voice-generator && bun run start

# Clean voice generator audio files and database
[group('voice')]
voice-clean:
    rm -f voice-generator/public/audio/*.wav
    rm -f voice-generator/data/glados-voice.db
    rm -f voice-generator/data/glados-voice.db-wal
    rm -f voice-generator/data/glados-voice.db-shm