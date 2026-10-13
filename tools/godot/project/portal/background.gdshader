shader_type canvas_item;
// background.gdshader - what is behind the portal when the game is not: a night-blue
// depth, slow mist, a low warm light as from a fire out of sight, and a few sparks rising.
// All arithmetic; no texture.  `dim` lets the game's own picture (blurred by backdrop.gdshader
// underneath) show through when it runs behind the portal.

uniform vec2 size = vec2(1920.0, 1080.0);
uniform float dim = 1.0;            // 1: opaque; lower: the layer underneath shows through
uniform float warmth = 1.0;
uniform vec4 top : source_color = vec4(0.035, 0.043, 0.071, 1.0);
uniform vec4 bottom : source_color = vec4(0.016, 0.018, 0.027, 1.0);

float hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int k = 0; k < 4; k++) {
		v += a * noise(p);
		p = p * 2.03 + vec2(17.0, 9.0);
		a *= 0.5;
	}
	return v;
}

// sparks: one per cell of a grid that scrolls upward, each with its own speed, sway and life
float sparks(vec2 uv, float aspect, float scale, float speed, float t) {
	vec2 p = vec2(uv.x * aspect, uv.y) * scale;
	p.y += t * speed;
	vec2 cell = floor(p);
	vec2 f = fract(p);
	float r = hash(cell);
	if (r < 0.80) {
		return 0.0;
	}
	vec2 at = vec2(0.2 + 0.6 * hash(cell + 3.1), 0.2 + 0.6 * hash(cell + 7.7));
	at.x += sin(t * (0.6 + r) + r * 40.0) * 0.12;
	float d = length(f - at);
	float flicker = 0.6 + 0.4 * sin(t * (2.0 + 5.0 * r) + r * 90.0);
	return smoothstep(0.050, 0.0, d) * flicker;
}

void fragment() {
	vec2 uv = UV;
	float aspect = size.x / max(size.y, 1.0);
	vec3 col = mix(top.rgb, bottom.rgb, smoothstep(0.0, 1.0, uv.y));
	// mist: two layers drifting against each other
	vec2 q = vec2(uv.x * aspect, uv.y);
	float m1 = fbm(q * 1.6 + vec2(TIME * 0.012, -TIME * 0.006));
	float m2 = fbm(q * 3.1 + vec2(-TIME * 0.016, TIME * 0.004) + 31.0);
	float mist = smoothstep(0.35, 0.95, m1 * 0.65 + m2 * 0.35);
	col += vec3(0.050, 0.065, 0.110) * mist * (0.55 + 0.45 * uv.y);
	// the low warm light, off to the right
	vec2 fire = vec2(0.74 * aspect, 1.12);
	float glow = exp(-length((q - fire) * vec2(0.55, 1.25)) * 1.9);
	col += vec3(0.50, 0.21, 0.07) * glow * 0.55 * warmth * (0.90 + 0.10 * sin(TIME * 0.7) * m2);
	// a cool light high on the left
	float cool = exp(-length((q - vec2(0.12 * aspect, -0.10)) * vec2(0.6, 1.0)) * 2.4);
	col += vec3(0.07, 0.11, 0.21) * cool * 0.7;
	// sparks, more of them near the warm light
	float rise = smoothstep(0.15, 1.0, uv.y) * (0.35 + 0.65 * smoothstep(0.25, 0.85, uv.x));
	float s = sparks(uv, aspect, 9.0, 0.050, TIME) + 0.6 * sparks(uv + 0.37, aspect, 15.0, 0.032, TIME + 20.0);
	col += vec3(1.0, 0.62, 0.26) * s * rise * 0.55 * warmth;
	// the corners fall away
	vec2 c = uv - 0.5;
	float vig = smoothstep(0.95, 0.25, length(c * vec2(1.05, 1.25)));
	col *= mix(0.55, 1.0, vig);
	// a little grain against banding
	col += (hash(uv * size + fract(TIME)) - 0.5) * 0.012;
	COLOR = vec4(col, dim);
}
