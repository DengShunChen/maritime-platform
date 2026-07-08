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
    
    // Move particle based on velocity (texture UV space)
    vec2 offset = velocity * 0.00005 * u_speed_factor;
    pos = pos + offset;

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
    
    // Use new position if dropping
    pos = mix(pos, random_pos, drop);
    
    // Encode position back to RGBA
    gl_FragColor = vec4(
        fract(pos * 255.0),
        floor(pos * 255.0) / 255.0
    );
}
