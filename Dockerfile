# ============================================================================
# DeskSearch — Dockerfile
# ============================================================================
# Runs the DeskSearch web server in a container.  The index data is stored
# in a volume mounted at /data so it persists across restarts.
#
# Build:
#   docker build -t desksearch .
#
# Run:
#   docker run -d \
#     -p 3777:3777 \
#     -v desksearch-data:/data \
#     -v ~/Documents:/docs:ro \
#     desksearch
#
# Then open http://localhost:3777 in your browser.
#
# Index a folder inside the container:
#   docker exec <container> desksearch index /docs
#
# Environment variables:
#   DESKSEARCH_DATA_DIR   Override data directory (default: /data)
#   DESKSEARCH_HOST       Bind host (default: 0.0.0.0)
#   DESKSEARCH_PORT       Bind port (default: 3777)
# ============================================================================

FROM python:3.11-slim

LABEL org.opencontainers.image.title="DeskSearch"
LABEL org.opencontainers.image.description="Private semantic search for your local files"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/wshuai190/desksearch"

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Install DeskSearch
# ---------------------------------------------------------------------------
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install in a single layer — no dev extras needed in prod
RUN pip install --no-cache-dir -e "." \
    && pip install --no-cache-dir huggingface_hub

# ---------------------------------------------------------------------------
# Pre-download the embedding model so the image is self-contained
# (skip with --build-arg SKIP_MODEL_DOWNLOAD=1 if you want a smaller image)
# ---------------------------------------------------------------------------
ARG SKIP_MODEL_DOWNLOAD=0
RUN if [ "$SKIP_MODEL_DOWNLOAD" = "0" ]; then \
      python -c "from desksearch.indexer.embedder import Embedder; Embedder('all-MiniLM-L6-v2')"; \
    fi

# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
# Data directory: mount a volume here to persist your index
ENV DESKSEARCH_DATA_DIR=/data
ENV DESKSEARCH_HOST=0.0.0.0
ENV DESKSEARCH_PORT=3777

# Health check — curl the search API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$DESKSEARCH_PORT/api/v1/health')" || exit 1

VOLUME ["/data"]
EXPOSE 3777

# ---------------------------------------------------------------------------
# Entrypoint — write a tiny config then start the server
# ---------------------------------------------------------------------------
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["serve"]
