// Draw fragment shader - Windy.com-style particle trail rendering
precision mediump float;

uniform sampler2D u_wind;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
uniform sampler2D u_color_ramp;

varying vec2 v_particle_pos;
varying float v_speed_t;  // Pre-calculated speed ratio from vertex shader
varying float v_in_bounds; // 1.0 if in bounds, 0.0 otherwise

void main() {
    // Discard particles outside data bounds
    if (v_in_bounds < 0.5) {
        discard;
    }
    
    // Speed-based color from ramp texture (Windy-style)
    vec3 wColor = texture2D(u_color_ramp, vec2(v_speed_t, 0.5)).rgb;
    
    // Faster particles are brighter/more opaque
    float velocity_alpha = 0.78 + v_speed_t * 0.22;
    
    vec3 final_color = wColor;
    float final_alpha = velocity_alpha;
    
    // Very transparent particles should not be rendered
    if (final_alpha < 0.01) {
        discard;
    }
    
    gl_FragColor = vec4(final_color, final_alpha);
}
