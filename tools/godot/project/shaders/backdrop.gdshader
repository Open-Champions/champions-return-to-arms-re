shader_type spatial;
// backdrop.gdshader - a ground for a level that has none to show (scene_view.gd "backdrop"): some arenas, entered
// alone, put the character where the game draws no level at all (it stands in the clear colour).  A wide plane at the
// character's feet, laid as flagstones in a colour made from the level's own sky, fading into the haze; a soft
// patch under the character.  Nothing of the game's art is in it: it is drawn by this shader.
render_mode unshaded, cull_disabled, depth_draw_always, shadows_disabled, fog_disabled, blend_premul_alpha;

#include "res://shaders/atmosphere.gdshaderinc"

uniform vec3 stone = vec3(0.32, 0.30, 0.28);        // the flagstones' colour (stored values)
uniform vec3 feet = vec3(0.0);                      // the character's feet (world)
varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

vec3 stored(vec3 c) {
	return pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

void fragment() {
	vec2 p = v_world.xy / 56.0;
	vec2 row = vec2(p.x + 0.5 * mod(floor(p.y), 2.0), p.y);       // a running bond
	vec2 cell = floor(row);
	vec2 f = fract(row);
	float tone = 0.82 + 0.3 * rta_hash(cell);
	float edge = min(min(f.x, 1.0 - f.x), min(f.y, 1.0 - f.y));
	float grout = smoothstep(0.015, 0.06, edge);
	float grain = 0.93 + 0.14 * rta_hash(floor(v_world.xy / 3.0));
	vec3 c = stone * tone * grain * mix(0.45, 1.0, grout);
	float d = length(v_world.xy - feet.xy);
	c *= 1.0 - 0.45 * (1.0 - smoothstep(6.0, 34.0, d));          // the character's own shadow, soft
	vec3 to_surface = v_world - CAMERA_POSITION_WORLD;
	float dist = length(to_surface);
	float far = smoothstep(260.0, 2400.0, dist);
	c = mix(c, rta_haze_colour(to_surface / max(dist, 0.001)), far);
	ALBEDO = stored(clamp(c, 0.0, 1.0));
	ALPHA = 1.0;                                        // in the ordered pass: after the sky, before every draw of the list
}
