/**
 * WebGL Wind Layer
 * 
 * GPU-accelerated wind particle visualization following the Windy.com / mapbox/webgl-wind approach.
 * Supports 100,000+ particles at 60fps using ping-pong texture buffers.
 */

import maplibregl from 'maplibre-gl';

// Shader sources - imported as raw strings
import drawVertSource from '../shaders/draw.vert.glsl?raw';
import drawFragSource from '../shaders/draw.frag.glsl?raw';
import quadVertSource from '../shaders/quad.vert.glsl?raw';
import updateFragSource from '../shaders/update.frag.glsl?raw';
import screenFragSource from '../shaders/screen.frag.glsl?raw';

export interface WindLayerOptions {
  numParticles?: number;       // Number of particles (will be squared to nearest power of 2)
  fadeOpacity?: number;        // Trail fade opacity (0.9-0.999)
  speedFactor?: number;        // Animation speed multiplier
  dropRate?: number;           // Base particle reset probability
  dropRateBump?: number;       // Additional reset rate for fast particles
  particleSize?: number;       // Point size in pixels
}

interface WindMetadata {
  uMin: number;
  uMax: number;
  vMin: number;
  vMax: number;
  bounds: [number, number, number, number]; // minLon, minLat, maxLon, maxLat
  width: number;
  height: number;
}

export class WebGLWindLayer implements maplibregl.CustomLayerInterface {
  public id: string;
  public type = 'custom' as const;
  public renderingMode = '2d' as const;

  private map: maplibregl.Map | null = null;
  private gl: WebGLRenderingContext | null = null;

  // Options
  private _fadeOpacity: number = 0.90;
  private speedFactor: number = 0.5;
  private dropRate: number = 0.003;
  private dropRateBump: number = 0.01;
  private _particleSize: number = 1.5;

  // Data
  private windTexture: WebGLTexture | null = null;
  private windMetadata: WindMetadata | null = null;
  private coordsTexture: WebGLTexture | null = null; // [NEW] Coordinate texture
  private coordsMetadata: { lonMin: number, lonMax: number, latMin: number, latMax: number } | null = null; // [NEW]
  private particleStateTexture0: WebGLTexture | null = null;
  private particleStateTexture1: WebGLTexture | null = null;
  private colorRampTexture: WebGLTexture | null = null;

  // Programs
  private drawProgram: WebGLProgram | null = null;
  private updateProgram: WebGLProgram | null = null;
  private screenProgram: WebGLProgram | null = null;

  // Buffers
  private quadBuffer: WebGLBuffer | null = null;
  private particleIndexBuffer: WebGLBuffer | null = null;

  // Framebuffer for particle updates and trails
  private framebuffer: WebGLFramebuffer | null = null;
  private screenTexture: WebGLTexture | null = null;
  private backgroundTexture: WebGLTexture | null = null;

  // State
  private numParticles: number = 65536;
  private particleRes: number;
  private currentColormap: string = 'viridis';
  private isActive: boolean = false;
  private timeIndex: number = -1;

  // Trail correction state
  private lastMapCenter: maplibregl.LngLat | null = null;
  private lastMapZoom: number = 0;

  constructor(options: WindLayerOptions & { id: string }) {
    this.id = options.id;

    // Apply options
    if (options.numParticles) {
      this.numParticles = options.numParticles;
    }
    // Round to power of 2 for texture size
    this.particleRes = Math.ceil(Math.sqrt(this.numParticles));
    this.particleRes = Math.pow(2, Math.ceil(Math.log2(this.particleRes)));
    this.numParticles = this.particleRes * this.particleRes;

    if (options.fadeOpacity !== undefined) this._fadeOpacity = options.fadeOpacity;
    if (options.speedFactor !== undefined) this.speedFactor = options.speedFactor;
    if (options.dropRate !== undefined) this.dropRate = options.dropRate;
    if (options.dropRateBump !== undefined) this.dropRateBump = options.dropRateBump;
    if (options.particleSize !== undefined) this._particleSize = options.particleSize;
  }

  public onAdd(map: maplibregl.Map, gl: WebGLRenderingContext): void {
    this.map = map;
    this.gl = gl;

    this.initWebGL();
    this.resizeScreenTextures();
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  public onRemove(_map: maplibregl.Map, _gl: WebGLRenderingContext): void {
    this.destroy();
    this.map = null;
    this.gl = null;
  }

  private initWebGL(): void {
    if (!this.gl) return;
    const gl = this.gl;

    // Create shader programs
    this.drawProgram = this.createProgram(drawVertSource, drawFragSource);
    this.updateProgram = this.createProgram(quadVertSource, updateFragSource);
    this.screenProgram = this.createProgram(quadVertSource, screenFragSource);

    // Create buffers
    this.quadBuffer = this.createQuadBuffer();
    this.particleIndexBuffer = this.createParticleIndexBuffer();

    // Create framebuffer
    this.framebuffer = gl.createFramebuffer();

    // Initialize particle state textures
    this.initParticleTextures();
  }

  private resizeScreenTextures(): void {
    if (!this.gl || !this.map) return;

    const canvas = this.map.getCanvas();
    const gl = this.gl;

    // Cleanup old textures
    if (this.screenTexture) gl.deleteTexture(this.screenTexture);
    if (this.backgroundTexture) gl.deleteTexture(this.backgroundTexture);

    // Create new textures matching canvas size
    this.screenTexture = this.createTexture(
      gl.NEAREST, null, canvas.width, canvas.height
    );
    this.backgroundTexture = this.createTexture(
      gl.NEAREST, null, canvas.width, canvas.height
    );

    // Initialize them with transparent black
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.backgroundTexture, 0);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.screenTexture, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  private createShader(type: number, source: string): WebGLShader | null {
    const gl = this.gl!;
    const shader = gl.createShader(type);
    if (!shader) return null;

    gl.shaderSource(shader, source);
    gl.compileShader(shader);

    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error('Shader compile error:', gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }

    return shader;
  }

  private createProgram(vertSource: string, fragSource: string): WebGLProgram | null {
    const gl = this.gl!;
    const vertShader = this.createShader(gl.VERTEX_SHADER, vertSource);
    const fragShader = this.createShader(gl.FRAGMENT_SHADER, fragSource);

    if (!vertShader || !fragShader) return null;

    const program = gl.createProgram();
    if (!program) return null;

    gl.attachShader(program, vertShader);
    gl.attachShader(program, fragShader);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(program));
      return null;
    }

    return program;
  }

  private createQuadBuffer(): WebGLBuffer | null {
    const gl = this.gl!;
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      0, 0, 1, 0, 0, 1,
      0, 1, 1, 0, 1, 1
    ]), gl.STATIC_DRAW);
    return buffer;
  }

  private createParticleIndexBuffer(): WebGLBuffer | null {
    const gl = this.gl!;
    const indices = new Float32Array(this.numParticles);
    for (let i = 0; i < this.numParticles; i++) {
      indices[i] = i;
    }
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    return buffer;
  }

  private initParticleTextures(): void {
    const gl = this.gl!;

    // Create random initial particle positions
    const particleData = new Uint8Array(this.numParticles * 4);
    for (let i = 0; i < this.numParticles; i++) {
      // Encode random position in [0, 1] range
      const x = Math.random();
      const y = Math.random();

      // High precision encoding: RG = fractional, BA = integer
      particleData[i * 4 + 0] = Math.floor(256 * (x * 256 - Math.floor(x * 256)));  // R
      particleData[i * 4 + 1] = Math.floor(256 * (y * 256 - Math.floor(y * 256)));  // G
      particleData[i * 4 + 2] = Math.floor(x * 256);  // B
      particleData[i * 4 + 3] = Math.floor(y * 256);  // A
    }

    this.particleStateTexture0 = this.createTexture(
      gl.NEAREST, particleData, this.particleRes, this.particleRes
    );
    this.particleStateTexture1 = this.createTexture(
      gl.NEAREST, particleData, this.particleRes, this.particleRes
    );
  }

  private createTexture(filter: number, data: Uint8Array | null, width: number, height: number): WebGLTexture | null {
    const gl = this.gl!;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    return texture;
  }

  public start(): void {
    this.isActive = true;
    if (this.map) this.map.triggerRepaint();
  }

  public stop(): void {
    this.isActive = false;
  }

  public clear(): void {
    // Optional
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  public render(_gl: WebGLRenderingContext, matrix: any): void {
    if (!this.isActive || !this.windTexture || !this.windMetadata) return;

    // Check if resize is needed (naive check)
    const canvas = this.map!.getCanvas();
    if (this.screenTexture && (canvas.width !== this.map!.getCanvas().width || canvas.height !== this.map!.getCanvas().height)) {
      this.resizeScreenTextures();
    }

    const gl = this.gl!;

    // Save current framebuffer (MapLibre's buffer)
    const originalFramebuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);

    // Disable depth test for our 2D operations to avoid z-fighting
    const depthEnabled = gl.getParameter(gl.DEPTH_TEST);
    if (depthEnabled) {
      gl.disable(gl.DEPTH_TEST);
    }

    // 1. Update particles (physics)
    this.updateParticles();

    // 2. Draw particles (render)
    this.drawParticles(matrix, originalFramebuffer);

    // Restore depth test if it was enabled
    if (depthEnabled) {
      gl.enable(gl.DEPTH_TEST);
    }

    // 3. Ping-pong buffers
    const temp = this.particleStateTexture0;
    this.particleStateTexture0 = this.particleStateTexture1;
    this.particleStateTexture1 = temp;

    // Trigger next frame
    if (this.map) {
      this.map.triggerRepaint();
    }
  }

  private updateParticles(): void {
    const gl = this.gl!;
    if (!this.updateProgram || !this.windMetadata) return;

    gl.useProgram(this.updateProgram);

    // Bind framebuffer to write to particle state texture 1
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.particleStateTexture1, 0);
    gl.viewport(0, 0, this.particleRes, this.particleRes);

    // Bind particle state texture 0 as input
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.particleStateTexture0);
    gl.uniform1i(gl.getUniformLocation(this.updateProgram, 'u_particles'), 0);

    // Bind wind texture
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.windTexture);
    gl.uniform1i(gl.getUniformLocation(this.updateProgram, 'u_wind'), 1);

    // Set uniforms
    gl.uniform2f(gl.getUniformLocation(this.updateProgram, 'u_wind_res'),
      this.windMetadata.width, this.windMetadata.height);
    gl.uniform2f(gl.getUniformLocation(this.updateProgram, 'u_wind_min'),
      this.windMetadata.uMin, this.windMetadata.vMin);
    gl.uniform2f(gl.getUniformLocation(this.updateProgram, 'u_wind_max'),
      this.windMetadata.uMax, this.windMetadata.vMax);
    gl.uniform1f(gl.getUniformLocation(this.updateProgram, 'u_rand_seed'), Math.random());
    gl.uniform1f(gl.getUniformLocation(this.updateProgram, 'u_speed_factor'), this.speedFactor);
    gl.uniform1f(gl.getUniformLocation(this.updateProgram, 'u_drop_rate'), this.dropRate);
    gl.uniform1f(gl.getUniformLocation(this.updateProgram, 'u_drop_rate_bump'), this.dropRateBump);

    // Draw fullscreen quad
    this.drawQuad(this.updateProgram);
  }

  private drawParticles(matrix: number[], targetFramebuffer: WebGLFramebuffer | null): void {
    const gl = this.gl!;
    if (!this.drawProgram || !this.screenProgram || !this.windMetadata) return;

    const canvas = this.map!.getCanvas();

    // === STEP 1: Draw faded previous frame to screen texture (trail effect) ===
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.screenTexture, 0);
    gl.viewport(0, 0, canvas.width, canvas.height); // Use actual canvas dims

    gl.useProgram(this.screenProgram);

    // Fade the background texture
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.backgroundTexture);
    gl.uniform1i(gl.getUniformLocation(this.screenProgram, 'u_screen'), 0);
    gl.uniform1f(gl.getUniformLocation(this.screenProgram, 'u_opacity'), this._fadeOpacity);

    // Calculate screen offset for trail correction
    let dx = 0;
    let dy = 0;
    let opacity = this._fadeOpacity; // Default opacity

    if (this.map && this.lastMapCenter) {
      const currentZoom = this.map.getZoom();
      if (Math.abs(currentZoom - this.lastMapZoom) > 0.001) {
        opacity = 0.0; // Reset trails on zoom
      } else {
        const prevCenterInCurrentView = this.map.project(this.lastMapCenter);
        const container = this.map.getContainer();
        const logicalW = container.offsetWidth;
        const logicalH = container.offsetHeight;

        dx = (prevCenterInCurrentView.x - logicalW / 2) / logicalW;
        dy = -(prevCenterInCurrentView.y - logicalH / 2) / logicalH;
      }
    }

    // Update state for next frame
    if (this.map) {
      this.lastMapCenter = this.map.getCenter();
      this.lastMapZoom = this.map.getZoom();
    }

    gl.uniform1f(gl.getUniformLocation(this.screenProgram, 'u_opacity'), opacity);
    gl.uniform2f(gl.getUniformLocation(this.screenProgram, 'u_screen_offset'), dx, dy);

    // Enable blending for trails? screen shader mixes. 
    // Usually we just draw quad overwriting screenTexture.
    // screen frag does: color = mix(backgroundColor, vec4(0), 1-opacity) ...

    gl.disable(gl.BLEND); // Screen pass overwrites
    this.drawQuad(this.screenProgram);


    // === STEP 2: Draw new particles on top ===
    gl.useProgram(this.drawProgram);

    // Bind particle state texture
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.particleStateTexture0);
    gl.uniform1i(gl.getUniformLocation(this.drawProgram, 'u_particles'), 0);

    // Bind wind texture for coloring
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.windTexture);
    gl.uniform1i(gl.getUniformLocation(this.drawProgram, 'u_wind'), 1);

    // Bind color ramp
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, this.colorRampTexture);
    gl.uniform1i(gl.getUniformLocation(this.drawProgram, 'u_color_ramp'), 2);

    // Bind coords texture [NEW]
    if (this.coordsTexture) {
      gl.activeTexture(gl.TEXTURE3);
      gl.bindTexture(gl.TEXTURE_2D, this.coordsTexture);
      gl.uniform1i(gl.getUniformLocation(this.drawProgram, 'u_coords'), 3);
    }

    // Bind ranges
    if (this.windMetadata) {
      gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_lon_range'),
        this.windMetadata.bounds[0], this.windMetadata.bounds[2]); // minLon, maxLon
      gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_lat_range'),
        this.windMetadata.bounds[1], this.windMetadata.bounds[3]); // minLat, maxLat

      gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_wind_res'),
        this.windMetadata.width, this.windMetadata.height);
    }

    // Bind coord ranges [NEW]
    if (this.coordsMetadata) {
      gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_coords_range_lon'),
        this.coordsMetadata.lonMin, this.coordsMetadata.lonMax);
      gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_coords_range_lat'),
        this.coordsMetadata.latMin, this.coordsMetadata.latMax);
    }

    // Set uniforms
    gl.uniform1f(gl.getUniformLocation(this.drawProgram, 'u_particles_res'), this.particleRes);
    gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_wind_min'),
      this.windMetadata.uMin, this.windMetadata.vMin);
    gl.uniform2f(gl.getUniformLocation(this.drawProgram, 'u_wind_max'),
      this.windMetadata.uMax, this.windMetadata.vMax);
    gl.uniform1f(gl.getUniformLocation(this.drawProgram, 'u_point_size'), this._particleSize);

    // MapLibre Matrix!
    gl.uniformMatrix4fv(gl.getUniformLocation(this.drawProgram, 'u_matrix'), false, matrix);

    // Draw particles as points
    gl.bindBuffer(gl.ARRAY_BUFFER, this.particleIndexBuffer);
    const indexAttr = gl.getAttribLocation(this.drawProgram, 'a_index');
    gl.enableVertexAttribArray(indexAttr);
    gl.vertexAttribPointer(indexAttr, 1, gl.FLOAT, false, 0, 0);

    // Enable blending for particles
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    gl.drawArrays(gl.POINTS, 0, this.numParticles);

    gl.disable(gl.BLEND); // Disable blend before next pass if needed

    // Unbind framebuffer -> Return to MapLibre's main framebuffer
    gl.bindFramebuffer(gl.FRAMEBUFFER, targetFramebuffer);

    // === STEP 3: Copy screen texture to MapLibre's framebuffer ===
    gl.viewport(0, 0, canvas.width, canvas.height);

    gl.useProgram(this.screenProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.screenTexture);
    gl.uniform1i(gl.getUniformLocation(this.screenProgram, 'u_screen'), 0);

    // Reset offset for final composite (we already shifted in step 1)
    gl.uniform2f(gl.getUniformLocation(this.screenProgram, 'u_screen_offset'), 0, 0);
    gl.uniform1f(gl.getUniformLocation(this.screenProgram, 'u_opacity'), 1.0);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    this.drawQuad(this.screenProgram);

    gl.disable(gl.BLEND);

    // Swap screen and background textures for next frame
    const temp = this.backgroundTexture;
    this.backgroundTexture = this.screenTexture;
    this.screenTexture = temp;
  }

  private drawQuad(program: WebGLProgram): void {
    const gl = this.gl!;

    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
    const posAttr = gl.getAttribLocation(program, 'a_pos');
    gl.enableVertexAttribArray(posAttr);
    gl.vertexAttribPointer(posAttr, 2, gl.FLOAT, false, 0, 0);

    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  public setParams(options: Partial<WindLayerOptions>): void {
    if (options.fadeOpacity !== undefined) this._fadeOpacity = options.fadeOpacity;
    if (options.speedFactor !== undefined) this.speedFactor = options.speedFactor;
    if (options.dropRate !== undefined) this.dropRate = options.dropRate;
    if (options.dropRateBump !== undefined) this.dropRateBump = options.dropRateBump;
    if (options.particleSize !== undefined) this._particleSize = options.particleSize;
  }

  public getCanvas(): HTMLCanvasElement | null {
    return this.map ? this.map.getCanvas() : null;
  }

  public async loadWindData(timeIndex: number): Promise<void> {
    if (this.timeIndex === timeIndex && this.windTexture && this.coordsTexture) return;
    this.timeIndex = timeIndex;

    try {
      // 1. Fetch Metadata
      const metaRes = await fetch(`/api/wind_texture?time=${timeIndex}&metadata=true`);
      if (!metaRes.ok) throw new Error('Failed to fetch wind metadata');
      const metadata = await metaRes.json();

      this.windMetadata = {
        uMin: metadata.uMin,
        uMax: metadata.uMax,
        vMin: metadata.vMin,
        vMax: metadata.vMax,
        bounds: metadata.bounds, // [minLon, minLat, maxLon, maxLat]
        width: metadata.width,
        height: metadata.height
      };

      // 2. Fetch Wind Texture Image
      const image = new Image();
      image.crossOrigin = 'Anonymous';
      image.src = `/api/wind_texture?time=${timeIndex}`;
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error('Failed to load wind texture image'));
      });

      // 3. Fetch Coords Texture Image
      const coordsImage = new Image();
      coordsImage.crossOrigin = 'Anonymous';
      coordsImage.src = `/api/coords_texture?time=${timeIndex}`;

      const coordsRes = await fetch(`/api/coords_texture?time=${timeIndex}`);
      if (!coordsRes.ok) throw new Error('Failed to fetch coords texture');
      const coordsBlob = await coordsRes.blob();
      const coordsUrl = URL.createObjectURL(coordsBlob);

      const lonRange = coordsRes.headers.get('X-Coords-Lon-Range')?.split(',').map(Number);
      const latRange = coordsRes.headers.get('X-Coords-Lat-Range')?.split(',').map(Number);

      if (lonRange && latRange) {
        this.coordsMetadata = {
          lonMin: lonRange[0],
          lonMax: lonRange[1],
          latMin: latRange[0],
          latMax: latRange[1]
        };
      }

      coordsImage.src = coordsUrl;
      await new Promise<void>((resolve, reject) => {
        coordsImage.onload = () => resolve();
        coordsImage.onerror = () => reject(new Error('Failed to load coords texture image'));
      });

      // Upload to GPU
      if (this.gl) {
        const gl = this.gl;

        // Wind Texture
        if (this.windTexture) gl.deleteTexture(this.windTexture);
        this.windTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, this.windTexture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);

        // Coords Texture
        if (this.coordsTexture) gl.deleteTexture(this.coordsTexture);
        this.coordsTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, this.coordsTexture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, coordsImage);
      }

    } catch (e) {
      console.error('Error loading wind data:', e);
      throw e;
    }
  }

  public setColorScheme(scheme: string): void {
    if (this.currentColormap === scheme && this.colorRampTexture) return;
    this.currentColormap = scheme;

    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 1;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const grad = ctx.createLinearGradient(0, 0, 256, 0);

    if (scheme === 'viridis') {
      grad.addColorStop(0, '#440154');
      grad.addColorStop(0.25, '#3b528b');
      grad.addColorStop(0.5, '#21918c');
      grad.addColorStop(0.75, '#5ec962');
      grad.addColorStop(1, '#fde725');
    } else if (scheme === 'magma') {
      grad.addColorStop(0, '#000004');
      grad.addColorStop(0.25, '#51127c');
      grad.addColorStop(0.5, '#b73779');
      grad.addColorStop(0.75, '#fc8961');
      grad.addColorStop(1, '#fcfdbf');
    } else {
      grad.addColorStop(0, 'black');
      grad.addColorStop(1, 'white');
    }

    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 1);

    const data = new Uint8Array(ctx.getImageData(0, 0, 256, 1).data);

    if (this.gl) {
      const gl = this.gl;
      if (this.colorRampTexture) gl.deleteTexture(this.colorRampTexture);

      this.colorRampTexture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.colorRampTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    }
  }

  public destroy(): void {
    this.stop();

    if (this.gl) {
      this.gl.deleteTexture(this.windTexture);
      this.gl.deleteTexture(this.colorRampTexture);
      this.gl.deleteTexture(this.particleStateTexture0);
      this.gl.deleteTexture(this.particleStateTexture1);
      this.gl.deleteTexture(this.screenTexture);
      this.gl.deleteTexture(this.backgroundTexture);
      this.gl.deleteBuffer(this.quadBuffer);
      this.gl.deleteBuffer(this.particleIndexBuffer);
      this.gl.deleteFramebuffer(this.framebuffer);
      this.gl.deleteProgram(this.drawProgram);
      this.gl.deleteProgram(this.updateProgram);
      this.gl.deleteProgram(this.screenProgram);
    }
  }
}
