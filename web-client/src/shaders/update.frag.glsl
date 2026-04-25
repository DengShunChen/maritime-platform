// Update fragment shader - moves particles based on wind velocity
precision highp float;

uniform sampler2D u_particles;
uniform sampler2D u_wind;
uniform vec2 u_wind_res;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
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

void main() {
    // Read current particle state
    vec4 color = texture2D(u_particles, v_tex_pos);
    
    // Decode position from RGBA (high precision encoding)
    vec2 pos = vec2(
        color.r / 255.0 + color.b,
        color.g / 255.0 + color.a
    );
    
    // Sample wind velocity at current position (with bilinear interpolation)
    vec2 wind_sample = texture2D(u_wind, pos).rg;
    vec2 velocity = mix(u_wind_min, u_wind_max, wind_sample);
    float speed = length(velocity);
    
    // Move particle based on velocity
    // Note: Implicit assumption that grid is roughly uniform physically (Lambert)
    // So U/V (m/s) map directly to X/Y grid delta
    vec2 offset = velocity * 0.00005 * u_speed_factor;
    
    // Wrap position to [0, 1]
    pos = fract(1.0 + pos + offset);
    
    // Random particle reset to prevent accumulation
    vec2 seed = (pos + v_tex_pos) * u_rand_seed;
    
    // Faster particles have higher reset probability
    float speed_normalized = speed / length(u_wind_max);
    float drop_rate = u_drop_rate + speed_normalized * u_drop_rate_bump;
    
    float drop = step(1.0 - drop_rate, rand(seed));
    
    // Generate random new position
    vec2 random_pos = vec2(rand(seed + 1.3), rand(seed + 2.1));
    
    // Use new position if dropping
    pos = mix(pos, random_pos, drop);
    
    // Encode position back to RGBA
    gl_FragColor = vec4(
        fract(pos * 255.0),
        floor(pos * 255.0) / 255.0
    );
}
