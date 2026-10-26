shader_type spatial;
// er_grass.gdshader - the Elden Ring world layer's grass (er_world.gd): one tuft of crossed cards per instance of a
// MultiMesh, on the grass-class ground of the level (points from RtaDrawer.get_grass).
//   INSTANCE_CUSTOM: x the point's own number (0..1), y its distance share (0 at the eye .. 1 at the radius), z the
//                    ground's facing (normal z)
//   COLOR:           the ground's colour there as the game drew it (texel x the game's vertex light; 0..1 stored values)
// The card's picture (the owner's Elden Ring grass) gives the shape (alpha) and the fine colour; the ground's colour gives
// the tone, so the grass is the level's own colour where it grows.  It sways in a wind of its own, thins out by distance
// the way the drawer thins the points (no tuft pops: it shrinks away first), is lit as the level's pieces are (the sun's
// shadow, Godot's lights: gs_draw.gdshaderinc GS_LIT) and hazed as they are.
// The world's draws are all in Godot's transparent pass, in the list's order (RtaDrawer::place): the grass is too (it writes
// ALPHA, cut out by discard, and depth), drawn after the level's draws (er_world.gd: its sorting offset)
render_mode blend_mix, depth_draw_always, cull_disabled, specular_disabled, fog_disabled, ambient_light_disabled;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D blades : filter_linear_mipmap_anisotropic, repeat_disable;
uniform float wind = 1.0;
uniform float sun_wrap = 0.75;

varying vec3 v_world;
varying vec3 v_ground;
varying float v_height;
varying float v_fade;

float keep_at(float share) {
	// as get_grass (rta_world.cpp): all out to a third of the radius, then down to a quarter at its edge
	return share < 0.33 ? 1.0 : 1.0 - 0.75 * smoothstep(0.33, 1.0, share);
}

void vertex() {
	float seed = INSTANCE_CUSTOM.x;
	float share = INSTANCE_CUSTOM.y;
	// shrinks away before the point is dropped
	v_fade = clamp((keep_at(share) - seed) / 0.06, 0.0, 1.0) * (1.0 - smoothstep(0.92, 1.0, share));
	vec3 local = VERTEX;
	local.z *= v_fade;
	v_height = VERTEX.z;
	vec3 base = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	vec3 world = (MODEL_MATRIX * vec4(local, 1.0)).xyz;
	// the wind: a slow wave across the field and a quick flutter, bending the top of each card
	float t = TIME * wind;
	float wave = sin(dot(base.xy, vec2(0.006, 0.004)) + t * 1.3) * 0.6 + sin(dot(base.xy, vec2(-0.013, 0.009)) + t * 2.1 + seed * 6.28) * 0.4;
	float bend = v_height * v_height;
	float tall = length(MODEL_MATRIX[2].xyz);
	world.xy += vec2(0.7, 0.45) * wave * bend * tall * 0.22;
	world.z -= abs(wave) * bend * tall * 0.05;
	v_world = world;
	v_ground = COLOR.rgb;
	POSITION = PROJECTION_MATRIX * (VIEW_MATRIX * vec4(world, 1.0));
	NORMAL = normalize((VIEW_MATRIX * vec4(0.0, 0.0, 1.0, 0.0)).xyz);
}

vec3 to_linear(vec3 c) {
	return pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

void fragment() {
	vec4 b = texture(blades, UV);
	// the blades' edges kept sharp at a distance (the mip maps would melt them into a blob): the alpha re-scaled by its own
	// rate of change round the cut
	float a = (b.a - 0.4) / max(fwidth(b.a), 1e-4) + 0.5;
	if (v_fade <= 0.0 || a < 0.5) discard;
	// the card's fine colour over the ground's tone: its own colour divided by its mean
	vec3 mean = max(textureLod(blades, vec2(0.5), 12.0).rgb / max(textureLod(blades, vec2(0.5), 12.0).a, 0.05), vec3(0.05));
	vec3 detail = clamp(b.rgb / mean, vec3(0.3), vec3(1.9));
	// darker in the tuft, lighter at the tips, as grass is
	float shade = mix(0.9, 1.4, smoothstep(0.0, 1.0, v_height));
	vec3 rgb = clamp(v_ground * detail * shade, 0.0, 1.0);
	vec3 to_surface = v_world - CAMERA_POSITION_WORLD;
	float dist = length(to_surface);
	float f = rta_haze(dist, v_world.z);
	vec3 haze = rta_haze_colour(to_surface / max(dist, 0.001)) * f;
	rgb *= 1.0 - f;
	ALBEDO = to_linear(rgb);
	EMISSION = to_linear(clamp(rgb * rta_light_ambient.rgb + haze, 0.0, 1.0));
	ROUGHNESS = 1.0;
	ALPHA = 1.0;
}

void light() {
	if (LIGHT_IS_DIRECTIONAL) DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * mix(clamp(dot(NORMAL, LIGHT) * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap);
	else DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * 0.7;
}
