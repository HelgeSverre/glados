FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"

# Copy Python dependencies and TTS engine files
COPY requirements.txt ./
COPY glados.py engine.py ./
COPY utils/ utils/
COPY glados-tts/ glados-tts/

# Create venv and install Python dependencies
RUN uv venv && uv pip install -r requirements.txt

# Download TTS models
RUN uv pip install gdown && \
    uv run gdown "1TRJtctjETgVVD5p7frSVPmgw8z8FFtjD" -O models.zip && \
    unzip -o models.zip && \
    rm models.zip

# Copy voice generator files
COPY voice-generator/package.json voice-generator/
COPY voice-generator/tsconfig.json voice-generator/
COPY voice-generator/src/ voice-generator/src/
COPY voice-generator/worker/ voice-generator/worker/
COPY voice-generator/public/ voice-generator/public/

# Install Bun dependencies
RUN cd voice-generator && bun install

# Create data directories
RUN mkdir -p voice-generator/data voice-generator/public/audio

# Copy and setup entrypoint
COPY voice-generator/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose web server port
EXPOSE 3000

# Environment variables
ENV PORT=3000

ENTRYPOINT ["/docker-entrypoint.sh"]
