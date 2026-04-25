FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.4

# Install Python tools and eccodes
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    libeccodes0 \
    libeccodes-dev \
    libhdf5-dev \
    libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user
RUN groupadd --system etlgroup && useradd --system --gid etlgroup etluser

# Cache dirs
ENV MPLCONFIGDIR=/tmp/matplotlib
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
ENV GDAL_CONFIG=/usr/bin/gdal-config
RUN mkdir -p /tmp/matplotlib /tmp/numba_cache /cog && \
    chown -R etluser:etlgroup /tmp/matplotlib /tmp/numba_cache /cog

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R etluser:etlgroup /app

USER etluser

# Default: convert all grib2 in /data to /cog
CMD ["python3", "convert_grib2_to_cog.py", "/data", "--cog-root", "/cog"]
