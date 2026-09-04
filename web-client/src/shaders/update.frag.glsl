// Update fragment shader - moves particles based on wind velocity
precision highp float;

uniform sampler2D u_particles;
uniform sampler2D u_wind;
uniform sampler2D u_coords;
uniform vec2 u_wind_res;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
uniform vec2 u_coords_range_lon;
uniform vec2 u_coords_range_lat;
uniform float u_rand_seed;
uniform float u_speed_factor;
uniform float u_drop_rate;
uniform float u_drop_rate_bump;

varying vec2 v_tex_pos;

// Pseudo-random number generator
float rand(const vec2 co) {
    float t = dot(vec2(12.9898, 78.233), co);
    return fract(sin(t) * (4375.85453 + t));
}

float decode16(float high, float low) {
    float h = floor(high * 255.0 + 0.5);
    float l = floor(low * 255.0 + 0.5);
    return (h * 256.0 + l) / 65535.0;
}

vec2 decodeLonLat(vec2 uv) {
    vec4 encoded = texture2D(u_coords, clamp(uv, 0.0, 1.0));
    float lon = mix(u_coords_range_lon.x, u_coords_range_lon.y, decode16(encoded.r, encoded.g));
    float lat = mix(u_coords_range_lat.x, u_coords_range_lat.y, decode16(encoded.b, encoded.a));
    return vec2(lon, lat);
}

void main() {
    // Read current particle state
    vec4 color = texture2D(u_particles, v_tex_pos);
    
    vec2 pos = vec2(
        color.r / 255.0 + color.b,
        color.g / 255.0 + color.a
    );
    
    // Sample wind velocity at current position (with bilinear interpolation)
    vec2 wind_sample = texture2D(u_wind, pos).rg;
    vec2 velocity = mix(u_wind_min, u_wind_max, wind_sample);
    float speed = length(velocity);
    
    // Move particles in earth-relative lon/lat space, then convert that
    // displacement back into WRF texture space with a local grid Jacobian.
    vec2 texel = 1.0 / max(u_wind_res, vec2(1.0));
    vec2 lonLat = decodeLonLat(pos);
    vec2 lonLatDx = decodeLonLat(pos + vec2(texel.x, 0.0));
    vec2 lonLatDy = decodeLonLat(pos + vec2(0.0, texel.y));
    vec2 dLonLatDx = lonLatDx - lonLat;
    vec2 dLonLatDy = lonLatDy - lonLat;

    float latRad = radians(clamp(lonLat.y, -80.0, 80.0));
    float cosLat = max(cos(latRad), 0.15);
    vec2 targetLonLatDelta = vec2(
        velocity.x / cosLat,
        velocity.y
    ) * 0.0022 * u_speed_factor;

    float det = dLonLatDx.x * dLonLatDy.y - dLonLatDy.x * dLonLatDx.y;
    vec2 offset = vec2(0.0);
    if (abs(det) > 0.0000001) {
        offset = vec2(
            (targetLonLatDelta.x * dLonLatDy.y - dLonLatDy.x * targetLonLatDelta.y) / det,
            (dLonLatDx.x * targetLonLatDelta.y - targetLonLatDelta.x * dLonLatDx.y) / det
        ) * texel;
    }
    pos = pos + clamp(offset, vec2(-0.02), vec2(0.02));

    // Domain margin — respawn instead of wrapping (finite-area WRF domain)
    const float margin = 0.02;
    vec2 seed = (pos + v_tex_pos) * u_rand_seed;
    if (pos.x < margin || pos.x > 1.0 - margin || pos.y < margin || pos.y > 1.0 - margin) {
        pos = vec2(rand(seed + 1.3), rand(seed + 2.1));
        pos = margin + pos * (1.0 - 2.0 * margin);
    }
    
    // Random particle reset to prevent accumulation
    
    // Faster particles have higher reset probability
    float speed_normalized = speed / length(u_wind_max);
    float drop_rate = u_drop_rate + speed_normalized * u_drop_rate_bump;
    
    float drop = step(1.0 - drop_rate, rand(seed));
    
    // Generate random new position
    vec2 random_pos = vec2(rand(seed + 1.3), rand(seed + 2.1));
    random_pos = margin + random_pos * (1.0 - 2.0 * margin);
    
    // Use new position if dropping
    pos = mix(pos, random_pos, drop);
    
    gl_FragColor = vec4(
        fract(pos * 255.0),
        floor(pos * 255.0) / 255.0
    );
}
