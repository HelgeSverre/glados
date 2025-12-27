# GLaDOS TTS

# Google Drive file ID for models (from https://github.com/R2D2FISH/glados-tts)
models_file_id := "1TRJtctjETgVVD5p7frSVPmgw8z8FFtjD"

# Install dependencies and download models
setup: install download-models
    @echo "Setup complete. Run 'just serve' to start the web server."

# Install Python dependencies with uv
install:
    uv venv
    uv pip install -r requirements.txt

# Download and extract models from Google Drive
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
serve:
    uv run python web/server.py

# Say something in GLaDOS's voice
say text:
    uv run python glados.py "{{text}}"

# Have GLaDOS respond to you (AI mode with Claude)
speak text:
    uv run python glados.py --ai "{{text}}"

# Clean up generated audio files
clean:
    rm -f output.wav glados-tts/output.wav
    rm -f web/audio/*.wav

# Build Docker image
docker-build:
    docker compose build

# Start Docker container
docker-up:
    docker compose up

# Start Docker container in background
docker-up-detached:
    docker compose up -d

# Stop Docker container
docker-down:
    docker compose down

# View Docker logs
docker-logs:
    docker compose logs -f
