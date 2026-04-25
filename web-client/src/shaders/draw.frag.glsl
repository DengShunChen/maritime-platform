// Draw fragment shader - Windy.com-style particle rendering
// Soft radial falloff with glow effect
// Particles outside data bounds are discarded
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
    
    // Calculate distance from center of point sprite (0.0 = center, 1.0 = edge)
    vec2 point_coord = gl_PointCoord - vec2(0.5);
    float dist = length(point_coord) * 2.0;
    
    // Discard pixels outside the circle
    if (dist > 1.0) {
        discard;
    }
    
    // SHARPER falloff for Windy-style "hair" lines
    // Old: smoothstep(0.0, 1.0, dist) -> very fuzzy
    // New: smoothstep(0.7, 1.0, dist) -> crisper edge, softer center
    float alpha = 1.0 - smoothstep(0.7, 1.0, dist);
    
    // Windy Style: White particles
    // We use speed to control Opacity/Brightness, not Color
    vec3 wColor = vec3(1.0, 1.0, 1.0);
    
    // Faster particles are brighter/more opaque
    // v_speed_t is 0..1
    float velocity_alpha = 0.4 + v_speed_t * 0.6; // Min 0.4, Max 1.0
    
    vec3 final_color = wColor;
    float final_alpha = alpha * velocity_alpha;
    
    // Very transparent particles should not be rendered
    if (final_alpha < 0.01) {
        discard;
    }
    
    gl_FragColor = vec4(final_color, final_alpha);
}
