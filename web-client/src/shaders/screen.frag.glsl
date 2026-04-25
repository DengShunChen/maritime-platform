// Screen fragment shader - fades the previous frame for trail effect
precision mediump float;

uniform sampler2D u_screen;
uniform float u_opacity;
uniform vec2 u_screen_offset;

varying vec2 v_tex_pos;

void main() {
    vec2 pos = v_tex_pos - u_screen_offset;
    
    // Check bounds strictly to prevent wrapping artifacts
    if (pos.x < 0.0 || pos.x > 1.0 || pos.y < 0.0 || pos.y > 1.0) {
        gl_FragColor = vec4(0.0);
        return;
    }
    
    vec4 color = texture2D(u_screen, pos);
    // Fade the color to create trails
    gl_FragColor = vec4(color.rgb, color.a * u_opacity);
}
