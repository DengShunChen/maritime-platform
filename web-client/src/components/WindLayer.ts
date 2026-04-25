

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

export class WindLayer {
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  particles: Particle[] = [];
  windGrid: WindPoint[][] = []; // roughly grid indexed
  width: number = 0;
  height: number = 0;
  animationFrameId: number | null = null;
  map: maplibregl.Map;
  windData: WindPoint[] | null = null;

  // Config
  numParticles = 5000;
  maxAge = 120;
  speedFactor = 30; // Seconds per frame for visual speed (tuned)
  fadeOpacity = 0.93; // Higher = longer trails

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
    this.width = this.map.getCanvas().width;
    this.height = this.map.getCanvas().height;
    this.canvas.width = this.width;
    this.canvas.height = this.height;
    this.canvas.style.width = this.map.getCanvas().style.width;
    this.canvas.style.height = this.map.getCanvas().style.height;
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
    const bounds = this.getParticleBounds();
    return {
      lon: bounds.minLon + Math.random() * (bounds.maxLon - bounds.minLon),
      lat: bounds.minLat + Math.random() * (bounds.maxLat - bounds.minLat),
      age: Math.random() * this.maxAge,
      speedMult: 0.5 + Math.random()
    };
  }

  start() {
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
  grid: { u: number, v: number }[][] | null = null;
  gridWidth = 100;
  gridHeight = 100;
  minLon = 0; maxLon = 0; minLat = 0; maxLat = 0;

  buildGrid() {
    if (!this.windData) return;

    this.grid = Array(this.gridWidth).fill(null).map(() => Array(this.gridHeight).fill({ u: 0, v: 0 }));

    // Find bounds
    // Find bounds
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
        this.grid[x][y] = { u: p.u, v: p.v };
      }
    }
  }

  getGridVector(lng: number, lat: number) {
    if (!this.grid) return { u: 0, v: 0 };
    const x = Math.floor((lng - this.minLon) / (this.maxLon - this.minLon) * (this.gridWidth - 1));
    const y = Math.floor((lat - this.minLat) / (this.maxLat - this.minLat) * (this.gridHeight - 1));

    if (x >= 0 && x < this.gridWidth && y >= 0 && y < this.gridHeight) {
      return this.grid[x][y];
    }
    return { u: 0, v: 0 };
  }

  animate() {
    this.render();
    this.animationFrameId = requestAnimationFrame(this.animate.bind(this));
  }

  clearCanvas() {
    this.ctx.clearRect(0, 0, this.width, this.height);
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
    this.ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'; // Particle color

    // Current map bounds for efficient culling?
    // We calculate position in Mercator 0..1 then project to screen pixels

    for (const p of this.particles) {
      if (p.age > this.maxAge) {
        Object.assign(p, this.createRandomParticle());
      }

      // Get screen position

      // We interpret p.x/p.y as relative to map center? NO.
      // Let's treat p.x/p.y as LNG/LAT directly? Easier.
      // If p is Lng/Lat, we project to screen.

      // RE-DESIGN: Store particles as {lon, lat}.
      const screenPos = this.map.project([p.lon, p.lat]);

      // Draw
      if (screenPos.x >= 0 && screenPos.x <= this.width && screenPos.y >= 0 && screenPos.y <= this.height) {
        // Larger particles for better visibility
        this.ctx.fillRect(screenPos.x, screenPos.y, 4, 4);
      }

      // Move
      const vector = this.getGridVector(p.lon, p.lat);

      // Simple Euler integration
      // Delta Lon ~ U / cos(lat)
      // Delta Lat ~ V
      // Scaling factor arbitrary for visual "nice-ness"
      const seconds = this.speedFactor * p.speedMult;
      const metersToDeg = 1 / 111000;
      const latRad = (p.lat * Math.PI) / 180;
      const dLon = (vector.u * seconds * metersToDeg) / Math.cos(latRad);
      const dLat = (vector.v * seconds * metersToDeg);

      p.lon += dLon;
      p.lat += dLat; // V increases latitude (north)

      p.age++;

      // Reset if out of data bounds
      if (p.lon < this.minLon || p.lon > this.maxLon || p.lat < this.minLat || p.lat > this.maxLat) {
        p.age = this.maxAge + 1; // Kill it
      }
    }
  }
}
