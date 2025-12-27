FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install just
RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY requirements.txt justfile ./
COPY glados.py engine.py ./
COPY utils/ utils/
COPY glados-tts/ glados-tts/
COPY web/ web/

# Create venv and install dependencies
RUN uv venv && uv pip install -r requirements.txt

# Download models
RUN uv pip install gdown && \
    uv run gdown "1TRJtctjETgVVD5p7frSVPmgw8z8FFtjD" -O models.zip && \
    unzip -o models.zip && \
    rm models.zip

# Expose port
EXPOSE 8765

# Set environment for Docker (bind to all interfaces)
ENV GLADOS_HOST=0.0.0.0
ENV GLADOS_PORT=8765

# Run the server
CMD ["uv", "run", "python", "web/server.py"]
