# Multi-stage Dockerfile for RegulatorIQ API
# Base builder stage
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and source tree for packaging
COPY pyproject.toml README.md ./
COPY config/ ./config/
COPY ingest/ ./ingest/
COPY retrieval/ ./retrieval/
COPY agent/ ./agent/
COPY api/ ./api/

# Install dependencies into virtualenv
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir .

# Bake models into cache directory and verify offline load
ENV HF_HOME=/build/cache/huggingface
ENV FASTEMBED_CACHE_PATH=/build/cache/fastembed

# Pre-download default embeddings and reranker models
RUN mkdir -p /build/cache/huggingface /build/cache/fastembed && \
    /opt/venv/bin/python -c " \
from fastembed import TextEmbedding; \
TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/build/cache/fastembed'); \
print('FastEmbed model pre-baked successfully!')" || true

# Test offline loading
ENV HF_HUB_OFFLINE=1

# Final Runtime Image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    zstd \
    tar \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with UID 1000
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    mkdir -p /app /app/artifacts /app/data /tmp/cache && \
    chown -R appuser:appuser /app /tmp/cache

# Copy virtualenv and pre-baked cache
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /build/cache /app/cache

# Copy source code and entrypoint
COPY --chown=appuser:appuser . /app/
COPY --chown=appuser:appuser docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HOME=/home/appuser \
    HF_HOME=/app/cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/cache/fastembed

USER 1000

EXPOSE 7860

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
