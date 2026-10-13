shader_type spatial;
// sky.gdshader - the sky of scene mode: a sphere round the camera, drawn before everything else of the
// 3-D surface (project/scene_view.gd makes it; the colours are atmosphere.gdshaderinc's rta_sky).
// The game's own dome, where a level has one, is drawn over it by the game's own draws.
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never, shadows_disabled, fog_disabled, blend_premul_alpha, skip_vertex_transform;

#include "res://shaders/atmosphere.gdshaderinc"

varying vec3 v_dir;

void vertex() {
	v_dir = VERTEX;                                     // the sphere is in the world's axes (z up), centred on the eye
	POSITION = PROJECTION_MATRIX * vec4(mat3(VIEW_MATRIX) * VERTEX, 1.0);
	POSITION.z = POSITION.w * 0.5;                      // inside the depth range whatever the planes are
}

vec3 stored(vec3 c) {
	// the renderer takes ALBEDO for linear light and stores 1.055 x^(1/2.4) - 0.055 of it (gs_draw.gdshaderinc,
	// to_linear): what goes in is the colour whose stored value is c
	vec3 light = pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
	vec3 x = c;
	for (int k = 0; k < 3; k++) {
		vec3 f = x * (x * (x * 0.305306011 + 0.682171111) + 0.012522878) - light;
		vec3 slope = x * (x * 0.915918033 + 1.364342222) + 0.012522878;
		x = clamp(x - f / slope, 0.0, 1.0);
	}
	return mix(x, vec3(0.0), lessThan(c, vec3(0.002)));
}

void fragment() {
	vec3 c = rta_sky(normalize(v_dir));
	c += (rta_hash(FRAGCOORD.xy) - 0.5) * (1.5 / 255.0);        // no bands in a slow gradient
	ALBEDO = stored(clamp(c, 0.0, 1.0));
	ALPHA = 1.0;
}
