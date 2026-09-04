FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.4

ARG BUILD_VERSION=dev
ARG BUILD_SHA=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Maritime Platform Backend" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${BUILD_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV BUILD_VERSION=$BUILD_VERSION
ENV BUILD_SHA=$BUILD_SHA
ENV BUILD_DATE=$BUILD_DATE

# Install Python and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    libeccodes0 \
    libeccodes-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

# Temp cache dirs
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
RUN mkdir -p /tmp/matplotlib /tmp/numba_cache && \
    chown -R appuser:appgroup /tmp/matplotlib /tmp/numba_cache

WORKDIR /app

# Install Python deps – rasterio builds against system GDAL already in this image
ENV GDAL_CONFIG=/usr/bin/gdal-config
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/ready || exit 1

ENV GUNICORN_WORKERS=1

USER root
RUN chmod +x /app/docker-entrypoint.sh && chown appuser:appgroup /app/docker-entrypoint.sh
USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]
