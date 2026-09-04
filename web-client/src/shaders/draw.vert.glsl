// Draw vertex shader - positions particles based on encoded state texture
// Windy.com-style: dynamic point size based on wind speed
// Particles outside data bounds are hidden by setting position off-screen
// NOW WITH BILINEAR INTERPOLATION FOR CURVILINEAR GRIDS (REAL)
precision highp float;

attribute float a_index;

uniform sampler2D u_particles;
uniform sampler2D u_wind;
uniform sampler2D u_coords; // [NEW] Coordinate texture
uniform float u_particles_res;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
uniform float u_point_size;  // Base point size
uniform vec4 u_data_bounds;  // minLon, minLat, maxLon, maxLat (in normalized 0-1 space)

// Map projection uniforms
uniform mat4 u_matrix;       // MapLibre projection matrix
uniform vec2 u_lon_range;    // minLon, maxLon (Fallback)
uniform vec2 u_lat_range;    // minLat, maxLat (Fallback)
uniform vec2 u_wind_res;     // Grid resolution (width, height)

uniform vec2 u_coords_range_lon; // minLon, maxLon (Real)
uniform vec2 u_coords_range_lat; // minLat, maxLat (Real)

varying vec2 v_particle_pos;
varying float v_speed_t;  // Speed ratio for fragment shader
varying float v_in_bounds; // 1.0 if in bounds, 0.0 otherwise

// Constants
const float PI = 3.141592653589793;
const float WORLD_SIZE = 512.0;  // MapLibre uses 512 tile size

// Convert longitude to Mercator X (normalized 0-1)
float lonToMercatorX(float lon) {
    return (lon + 180.0) / 360.0;
}

// Convert latitude to Mercator Y (normalized 0-1, Y increases downward in MapLibre)
float latToMercatorY(float lat) {
    // Clamp to Mercator limits
    float clampedLat = clamp(lat, -85.0511287798, 85.0511287798);
    float latRad = clampedLat * PI / 180.0;
    // Standard Web Mercator Y (0 at top, PI at bottom in relative units)
    float y = log(tan(PI / 4.0 + latRad / 2.0));
    return (0.5 - y / (2.0 * PI));
}

float decode16(float high, float low) {
    float h = floor(high * 255.0 + 0.5);
    float l = floor(low * 255.0 + 0.5);
    float val = h * 256.0 + l;
    return val / 65535.0;
}

vec2 decodeLonLat(vec2 uv) {
    vec4 coordsData = texture2D(u_coords, clamp(uv, 0.0, 1.0));
    float lon = mix(u_coords_range_lon.x, u_coords_range_lon.y, decode16(coordsData.r, coordsData.g));
    float lat = mix(u_coords_range_lat.x, u_coords_range_lat.y, decode16(coordsData.b, coordsData.a));
    return vec2(lon, lat);
}

vec2 windToTextureOffset(vec2 pos, vec2 velocity, float scale) {
    vec2 texel = 1.0 / max(u_wind_res, vec2(1.0));
    vec2 lonLat = decodeLonLat(pos);
    vec2 lonLatDx = decodeLonLat(pos + vec2(texel.x, 0.0));
    vec2 lonLatDy = decodeLonLat(pos + vec2(0.0, texel.y));
    vec2 dLonLatDx = lonLatDx - lonLat;
    vec2 dLonLatDy = lonLatDy - lonLat;

    float latRad = radians(clamp(lonLat.y, -80.0, 80.0));
    float cosLat = max(cos(latRad), 0.15);
    vec2 targetLonLatDelta = vec2(velocity.x / cosLat, velocity.y) * scale;

    float det = dLonLatDx.x * dLonLatDy.y - dLonLatDy.x * dLonLatDx.y;
    if (abs(det) <= 0.0000001) {
        return vec2(0.0);
    }
    vec2 offsetInTexels = vec2(
        (targetLonLatDelta.x * dLonLatDy.y - dLonLatDy.x * targetLonLatDelta.y) / det,
        (dLonLatDx.x * targetLonLatDelta.y - targetLonLatDelta.x * dLonLatDx.y) / det
    );
    return offsetInTexels * texel;
}




void main() {
    float particle_index = floor(a_index * 0.5);
    float segment_endpoint = mod(a_index, 2.0);

    vec2 tex_coord = vec2(
        fract(particle_index / u_particles_res),
        floor(particle_index / u_particles_res) / u_particles_res
    );

    vec4 color = texture2D(u_particles, tex_coord);
    vec2 current_pos = vec2(
        color.r / 255.0 + color.b,
        color.g / 255.0 + color.a
    );
    vec2 velocity = mix(u_wind_min, u_wind_max, texture2D(u_wind, current_pos).rg);
    vec2 trail_offset = clamp(windToTextureOffset(current_pos, velocity, 0.042), vec2(-0.045), vec2(0.045));
    vec2 previous_pos = current_pos - trail_offset;
    v_particle_pos = mix(previous_pos, current_pos, segment_endpoint);

    // Hide particles near texture edges (finite WRF domain)
    const float margin = 0.02;
    v_in_bounds = (
        v_particle_pos.x > margin && v_particle_pos.x < 1.0 - margin &&
        v_particle_pos.y > margin && v_particle_pos.y < 1.0 - margin
    ) ? 1.0 : 0.0;

    float speed = length(velocity);
    float speed_max = length(u_wind_max);
    float speed_ratio = clamp(speed / speed_max, 0.0, 1.0);
    v_speed_t = speed_ratio;

    vec2 lonLat = decodeLonLat(v_particle_pos);
    float lon = lonLat.x;
    float lat = lonLat.y;

    // Mercator projection
    float mercX = lonToMercatorX(lon);
    float mercY = latToMercatorY(lat);

    // MapLibre provides u_matrix that transforms Mercator [0, 1] to Clip Space
    gl_Position = u_matrix * vec4(mercX, mercY, 0.0, 1.0);

    // If out of bounds or wind is zero, hide the particle
    if (speed_ratio < 0.01) {
         gl_PointSize = 0.0;
         gl_Position = vec4(2.0, 2.0, 0.0, 1.0); // Off-screen
    } else {
        gl_PointSize = max(1.0, u_point_size * 0.35);
    }
}
