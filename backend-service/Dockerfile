FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.4

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
  CMD curl -f http://localhost:5000/health || exit 1

CMD ["gunicorn", "--log-file", "-", "--access-logfile", "-", "--log-level", "info", \
     "--workers", "2", "--timeout", "60", "-b", "0.0.0.0:5000", "app_v2:app"]
