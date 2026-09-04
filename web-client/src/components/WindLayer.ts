

import maplibregl from 'maplibre-gl';

interface WindPoint {
  lon: number;
  lat: number;
  u: number;
  v: number;
}

interface Particle {
  lon: number;
  lat: number;
  age: number;
  speedMult: number;
}

interface WindData {
  points: WindPoint[];
  bounds: number[];
}

interface WindGridCell {
  u: number;
  v: number;
  count: number;
}

export class WindLayer {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  particles: Particle[] = [];
  width: number = 0;
  height: number = 0;
  private dpr: number = 1;
  animationFrameId: number | null = null;
  map: maplibregl.Map;
  windData: WindPoint[] | null = null;

  // Config
  numParticles = 5000;
  maxAge = 120;
  speedFactor = 30; // Seconds per frame for visual speed (tuned)
  fadeOpacity = 0.93; // Higher = longer trails
  particleLineWidth = 1.1;

  constructor(map: maplibregl.Map) {
    this.map = map;
    this.canvas = document.createElement('canvas');
    this.canvas.style.position = 'absolute';
    this.canvas.style.top = '0';
    this.canvas.style.left = '0';
    this.canvas.style.pointerEvents = 'none'; // Click through
    this.canvas.style.zIndex = '10'; // Above map, below UI (which is 1000)

    const container = map.getCanvasContainer();
    container.appendChild(this.canvas);

    this.ctx = this.canvas.getContext('2d')!;

    this.resize();

    // Listen to map events
    this.map.on('resize', this.handleResize.bind(this));
    this.map.on('moveend', this.resetParticles.bind(this));
    this.map.on('zoomend', this.resetParticles.bind(this));
  }

  resize() {
    const rect = this.map.getCanvas().getBoundingClientRect();
    this.dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = Math.max(1, Math.round(rect.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * this.dpr));
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  handleResize() {
    this.resize();
    this.clearCanvas();
    this.initParticles();
  }

  updateData(data: WindData) {
    this.windData = data.points;
    this.grid = null;
    this.tuneParticleCount(data.points.length);
    this.buildGrid();
    this.initParticles();
  }

  async loadWindData(timeIndex: number, level: number = 0): Promise<void> {
    const res = await fetch(`/api/wind_data?time=${timeIndex}&level=${level}&max_points=18000`);
    if (!res.ok) throw new Error('Failed to fetch wind data');
    this.updateData(await res.json());
  }

  tuneParticleCount(pointCount: number) {
    const target = Math.round(pointCount / 8);
    const clamped = Math.max(500, Math.min(4000, target));
    this.numParticles = clamped;
  }

  initParticles() {
    this.particles = [];
    for (let i = 0; i < this.numParticles; i++) {
      this.particles.push(this.createRandomParticle());
    }
  }

  createRandomParticle(): Particle {
    if (this.windData && this.windData.length > 0) {
      const mapBounds = this.map.getBounds();
      let base = this.windData[Math.floor(Math.random() * this.windData.length)];

      for (let tries = 0; tries < 12; tries++) {
        const candidate = this.windData[Math.floor(Math.random() * this.windData.length)];
        if (
          candidate.lon >= mapBounds.getWest() && candidate.lon <= mapBounds.getEast() &&
          candidate.lat >= mapBounds.getSouth() && candidate.lat <= mapBounds.getNorth()
        ) {
          base = candidate;
          break;
        }
      }

      const lonJitter = Math.max(0.02, (this.maxLon - this.minLon) / this.gridWidth * 0.35);
      const latJitter = Math.max(0.02, (this.maxLat - this.minLat) / this.gridHeight * 0.35);
      return {
        lon: base.lon + (Math.random() - 0.5) * lonJitter,
        lat: base.lat + (Math.random() - 0.5) * latJitter,
        age: Math.random() * this.maxAge,
        speedMult: 0.55 + Math.random() * 0.9
      };
    }

    const bounds = this.getParticleBounds();
    return {
      lon: bounds.minLon + Math.random() * (bounds.maxLon - bounds.minLon),
      lat: bounds.minLat + Math.random() * (bounds.maxLat - bounds.minLat),
      age: Math.random() * this.maxAge,
      speedMult: 0.5 + Math.random()
    };
  }

  start() {
    this.resize();
    if (!this.animationFrameId) {
      this.animate();
    }
  }

  stop() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    this.clearCanvas();
  }

  // Find nearest wind vector (Note: This is O(N) naive implementation. For prod use a Grid/Quadtree)
  // We will optimize heavily by just finding one random neighbor or pre-baking a grid.
  // Optimization: The data seems to be a grid. We can map lat/lon -> index.


  // Optimized Grid Lookup
  grid: WindGridCell[][] | null = null;
  gridWidth = 180;
  gridHeight = 120;
  minLon = 0; maxLon = 0; minLat = 0; maxLat = 0;

  buildGrid() {
    if (!this.windData) return;

    this.grid = Array.from({ length: this.gridWidth }, () =>
      Array.from({ length: this.gridHeight }, () => ({ u: 0, v: 0, count: 0 }))
    );

    let minLon = Infinity, maxLon = -Infinity;
    let minLat = Infinity, maxLat = -Infinity;

    for (const p of this.windData) {
      if (p.lon < minLon) minLon = p.lon;
      if (p.lon > maxLon) maxLon = p.lon;
      if (p.lat < minLat) minLat = p.lat;
      if (p.lat > maxLat) maxLat = p.lat;
    }

    this.minLon = minLon;
    this.maxLon = maxLon;
    this.minLat = minLat;
    this.maxLat = maxLat;

    // Fill grid
    for (const p of this.windData) {
      const x = Math.floor((p.lon - this.minLon) / (this.maxLon - this.minLon) * (this.gridWidth - 1));
      const y = Math.floor((p.lat - this.minLat) / (this.maxLat - this.minLat) * (this.gridHeight - 1));
      if (x >= 0 && x < this.gridWidth && y >= 0 && y < this.gridHeight) {
        const cell = this.grid[x][y];
        cell.u += p.u;
        cell.v += p.v;
        cell.count += 1;
      }
    }

    for (let x = 0; x < this.gridWidth; x++) {
      for (let y = 0; y < this.gridHeight; y++) {
        const cell = this.grid[x][y];
        if (cell.count > 0) {
          cell.u /= cell.count;
          cell.v /= cell.count;
        }
      }
    }
  }

  getGridVector(lng: number, lat: number) {
    if (!this.grid) return null;
    const x = Math.floor((lng - this.minLon) / (this.maxLon - this.minLon) * (this.gridWidth - 1));
    const y = Math.floor((lat - this.minLat) / (this.maxLat - this.minLat) * (this.gridHeight - 1));

    if (x >= 0 && x < this.gridWidth && y >= 0 && y < this.gridHeight) {
      const cell = this.grid[x][y];
      if (cell.count > 0) return cell;
    }
    return null;
  }

  animate() {
    this.render();
    this.animationFrameId = requestAnimationFrame(this.animate.bind(this));
  }

  clearCanvas() {
    this.ctx.clearRect(0, 0, this.width, this.height);
  }

  setParams(options: { fadeOpacity?: number; speedFactor?: number; particleSize?: number }) {
    if (options.fadeOpacity !== undefined) this.fadeOpacity = options.fadeOpacity;
    if (options.speedFactor !== undefined) this.speedFactor = 9000 * options.speedFactor;
    if (options.particleSize !== undefined) this.particleLineWidth = Math.max(0.8, options.particleSize * 0.55);
  }

  setColorScheme(scheme: string) {
    void scheme;
    // Canvas wind particles intentionally use Windy-style white strokes.
  }

  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  destroy() {
    this.stop();
    this.canvas.remove();
  }

  getParticleBounds() {
    if (this.minLon === this.maxLon || this.minLat === this.maxLat) {
      return { minLon: -180, maxLon: 180, minLat: -85, maxLat: 85 };
    }

    const dataBounds = {
      minLon: this.minLon,
      maxLon: this.maxLon,
      minLat: this.minLat,
      maxLat: this.maxLat
    };

    const mapBounds = this.map.getBounds();
    const minLon = Math.max(dataBounds.minLon, mapBounds.getWest());
    const maxLon = Math.min(dataBounds.maxLon, mapBounds.getEast());
    const minLat = Math.max(dataBounds.minLat, mapBounds.getSouth());
    const maxLat = Math.min(dataBounds.maxLat, mapBounds.getNorth());

    if (minLon >= maxLon || minLat >= maxLat) {
      return dataBounds;
    }

    return { minLon, maxLon, minLat, maxLat };
  }

  resetParticles() {
    if (!this.windData) return;
    this.clearCanvas();
    this.initParticles();
  }

  render() {
    if (!this.grid) {
      this.buildGrid(); // Ensure grid exists
    }

    // Fade out fade trails
    this.ctx.globalCompositeOperation = 'destination-in';
    this.ctx.fillStyle = `rgba(0, 0, 0, ${this.fadeOpacity})`;
    this.ctx.fillRect(0, 0, this.width, this.height);

    this.ctx.globalCompositeOperation = 'source-over';
    this.ctx.lineCap = 'round';

    // Current map bounds for efficient culling?
    // We calculate position in Mercator 0..1 then project to screen pixels

    for (const p of this.particles) {
      if (p.age > this.maxAge) {
        Object.assign(p, this.createRandomParticle());
      }

      const screenPos = this.map.project([p.lon, p.lat]);

      // Move
      const vector = this.getGridVector(p.lon, p.lat);
      if (!vector) {
        Object.assign(p, this.createRandomParticle());
        continue;
      }

      // Simple Euler integration
      // Delta Lon ~ U / cos(lat)
      // Delta Lat ~ V
      // Scaling factor arbitrary for visual "nice-ness"
      const seconds = this.speedFactor * p.speedMult;
      const metersToDeg = 1 / 111000;
      const latRad = (p.lat * Math.PI) / 180;
      const dLon = (vector.u * seconds * metersToDeg) / Math.cos(latRad);
      const dLat = (vector.v * seconds * metersToDeg);

      const nextLon = p.lon + dLon;
      const nextLat = p.lat + dLat;
      const nextScreenPos = this.map.project([nextLon, nextLat]);
      const speed = Math.sqrt(vector.u * vector.u + vector.v * vector.v);

      if (
        screenPos.x >= -40 && screenPos.x <= this.width + 40 &&
        screenPos.y >= -40 && screenPos.y <= this.height + 40 &&
        nextScreenPos.x >= -40 && nextScreenPos.x <= this.width + 40 &&
        nextScreenPos.y >= -40 && nextScreenPos.y <= this.height + 40
      ) {
        const alpha = Math.max(0.35, Math.min(0.9, 0.35 + speed / 28));
        this.ctx.strokeStyle = 'rgba(0, 22, 26, 0.22)';
        this.ctx.lineWidth = this.particleLineWidth + 1.1;
        this.ctx.beginPath();
        this.ctx.moveTo(screenPos.x, screenPos.y);
        this.ctx.lineTo(nextScreenPos.x, nextScreenPos.y);
        this.ctx.stroke();

        this.ctx.strokeStyle = `rgba(245, 250, 248, ${alpha})`;
        this.ctx.lineWidth = this.particleLineWidth;
        this.ctx.beginPath();
        this.ctx.moveTo(screenPos.x, screenPos.y);
        this.ctx.lineTo(nextScreenPos.x, nextScreenPos.y);
        this.ctx.stroke();
      }

      p.lon = nextLon;
      p.lat = nextLat; // V increases latitude (north)

      p.age++;

      // Reset if out of data bounds
      if (p.lon < this.minLon || p.lon > this.maxLon || p.lat < this.minLat || p.lat > this.maxLat) {
        p.age = this.maxAge + 1; // Kill it
      }
    }
  }
}
