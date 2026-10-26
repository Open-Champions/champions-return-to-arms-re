shader_type spatial;
// sky.gdshader - the sky of scene mode: a sphere round the camera, drawn before everything else of the
// 3-D surface (project/scene_view.gd makes it; the colours are atmosphere.gdshaderinc's rta_sky).
// The game's own dome, where a level has one, is drawn over it by the game's own draws.
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never, shadows_disabled, fog_disabled, blend_premul_alpha, skip_vertex_transform;

#include "res://shaders/atmosphere.gdshaderinc"

varying vec3 v_dir;
// the Elden Ring world layer's cloud layer (er_world.gd): the owner's own Elden Ring cloud picture laid over the sky as a
// far ceiling, tinted by this level's own sky (its zenith and horizon colours, its sun), drifting slowly.
// rta_er_sky: x amount (0 none), y how much the level's sky tints the clouds, z drift speed, w scale
global uniform vec4 rta_er_sky;
global uniform sampler2D rta_er_clouds : filter_linear_mipmap_anisotropic, repeat_enable;

void vertex() {
	v_dir = VERTEX;                                     // the sphere is in the world's axes (z up), centred on the eye
	POSITION = PROJECTION_MATRIX * vec4(mat3(VIEW_MATRIX) * VERTEX, 1.0);
	POSITION.z = POSITION.w * 0.5;                      // inside the depth range whatever the planes are
}

vec3 stored(vec3 c) {
#if CURRENT_RENDERER != RENDERER_COMPATIBILITY
	// Forward+ / Mobile: ALBEDO is linear light and the picture is stored with the exact sRGB curve - the inverse is exact
	return pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
#endif
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
	vec3 dir = normalize(v_dir);
	vec3 c = rta_sky(dir);
	if (rta_er_sky.x > 0.0 && dir.z > 0.0) {
		vec2 uv = dir.xy / (dir.z + 0.08) * 0.11 * rta_er_sky.w + vec2(TIME * rta_er_sky.z, TIME * rta_er_sky.z * 0.37);
		vec4 cl = texture(rta_er_clouds, uv);
		float cover = cl.a * smoothstep(0.0, 0.22, dir.z) * rta_er_sky.x;
		// where the level has a painted dome, the clouds begin above its upper edge (the dome goes over into this sky
		// there: gs_draw.gdshaderinc GS_NOFOG) - no line where the dome ends
		if (rta_sky_zenith.a > 0.0) cover *= smoothstep(rta_sky_zenith.a, rta_sky_zenith.a + 0.2, asin(clamp(dir.z, -1.0, 1.0)));
		// lit by the level's own sun from the side it is on, in the level's own colours
		vec3 sun_dir = normalize(rta_sky_sun.xyz);
		float toward = pow(clamp(dot(dir, sun_dir) * 0.5 + 0.5, 0.0, 1.0), 3.0);
		vec3 own = cl.rgb;
		float lum = dot(own, vec3(0.3, 0.59, 0.11));
		vec3 sky_lit = c * (0.75 + 0.9 * lum) + rta_sky_sun_colour.rgb * toward * 0.35 * lum;
		vec3 cloud = mix(own, sky_lit, rta_er_sky.y);
		// a sky that is dark stays dark: the clouds no brighter than the sky they are in allows
		float sky_lum = max(dot(c, vec3(0.3, 0.59, 0.11)), 0.0);
		cloud *= mix(0.35, 1.0, smoothstep(0.04, 0.35, sky_lum));
		c = mix(c, cloud, clamp(cover, 0.0, 1.0));
	}
	c += (rta_hash(FRAGCOORD.xy) - 0.5) * (1.5 / 255.0);        // no bands in a slow gradient
	ALBEDO = stored(clamp(c, 0.0, 1.0));
	ALPHA = 1.0;
}
