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

// Decode 16-bit normalized value from 2 bytes (high, low) in [0,1] range
float decode16(float high, float low) {
    // high and low are 0..1 from texture
    // Convert back to 0..255 space then to 16 bit integer
    float h = floor(high * 255.0 + 0.5);
    float l = floor(low * 255.0 + 0.5);
    float val = h * 256.0 + l;
    return val / 65535.0; // Normalize back to 0..1
}




void main() {
    // Calculate texture coordinates for this particle
    vec2 tex_coord = vec2(
        fract(a_index / u_particles_res),
        floor(a_index / u_particles_res) / u_particles_res
    );
    
    // Decode position from RGBA (normalized 0-1 in wind texture space)
    vec4 color = texture2D(u_particles, tex_coord);
    v_particle_pos = vec2(
        color.r / 255.0 + color.b,
        color.g / 255.0 + color.a
    );
    
    // Check if particle is within data bounds
    v_in_bounds = 1.0; 
    
    // Sample wind velocity to determine speed
    vec2 velocity = mix(u_wind_min, u_wind_max, texture2D(u_wind, v_particle_pos).rg);
    float speed = length(velocity);
    float speed_max = length(u_wind_max);
    float speed_ratio = clamp(speed / speed_max, 0.0, 1.0);
    v_speed_t = speed_ratio;
    
    // === MAP LOCATION LOOKUP ===
    // Use v_particle_pos to sample the coordinate texture
    vec4 coordsData = texture2D(u_coords, v_particle_pos);
    
    // Decode Lon/Lat from texture
    // R/G = Lon (Normalized within X-Coords-Lon-Range)
    // B/A = Lat (Normalized within X-Coords-Lat-Range)
    float lonNorm = decode16(coordsData.r, coordsData.g);
    float latNorm = decode16(coordsData.b, coordsData.a);
    
    // Map to real degrees
    float lon = mix(u_coords_range_lon.x, u_coords_range_lon.y, lonNorm);
    float lat = mix(u_coords_range_lat.x, u_coords_range_lat.y, latNorm);
    
    // If coords texture is missing (0,0,0,0 everywhere or uniform 0), we might get garbage.
    // Fallback? If u_coords_range_lon is 0,0, logic breaks.
    // We assume backend always provides valid ranges if texture provides data.
    
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
        // Dynamic point size
        float size_factor = 0.8 + v_speed_t * 0.6;
        
        gl_PointSize = u_point_size * size_factor; 
    }
}
