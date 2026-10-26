// remaster_model.gdshader - the game's own figures remastered (model_remaster.gd, look.remaster_models).
//
// The mesh is the figure's own bind-pose mesh subdivided (RtaRemaster), skinned by the game's pose every frame; its
// colour is the game's own texture (the art pack's 4x picture where there is one), read with the very coordinates and
// texture state the game's draw has (st_scale, tex_offset, tex_size), and two maps derived from it on this machine: a
// normal map and ORM (r cavity, g roughness, b metal).  The light is er_armour.gdshader's - the level's ambient given
// form, the scene's lights, a metal's sky, the haze - and the game's own light on the figure (its torches, poison, hit
// flash: game_*, per figure: each figure has its own materials - the world's draws fill the instance-uniform
// buffer), so that the body and the Elden Ring / Tripo pieces fitted over it are lit alike.
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, ambient_light_disabled, fog_disabled, specular_schlick_ggx;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mr_tex : hint_default_white, filter_linear_mipmap, repeat_enable;     // r: cavity, g: roughness, b: metal
uniform bool has_normal = false;
uniform bool has_mr = false;
uniform vec2 st_scale = vec2(1.0);
uniform vec2 tex_offset = vec2(0.0);
uniform vec2 tex_size = vec2(1.0);
uniform int alpha_from = 0;             // 0 the texture's (128 = opaque), 1 a constant (ta0), 2 none
uniform float ta0 = 1.0;
uniform float cut = -1.0;               // alpha test: drawn where alpha >= cut (< 0: no test)
uniform float bump = 1.0;               // of the normal map
uniform float metal_amount = 1.0;
uniform float gain = 1.0;
uniform float fill = 1.0;
uniform float floor_light = 0.08;
uniform float sun_wrap = 0.55;
uniform float sky_reflect = 0.5;
uniform float form = 1.0;
uniform float fold_dark = 0.45;
uniform float sheen = 0.45;
uniform float cavity = 1.0;             // of the ORM's cavity
uniform bool flip = false;
uniform vec4 game_amb = vec4(0.0);
uniform vec4 game_sun_dir = vec4(0.0, 0.0, 1.0, 0.0);
uniform vec4 game_sun = vec4(0.0);
uniform vec4 game_fill_dir = vec4(0.0, 0.0, 1.0, 0.0);
uniform vec4 game_fill = vec4(0.0);
uniform vec4 game_p0_pos = vec4(0.0);
uniform vec4 game_p0 = vec4(0.0);
uniform vec4 game_p1_pos = vec4(0.0);
uniform vec4 game_p1 = vec4(0.0);
uniform float game_light = 1.0;
global uniform vec4 rta_model;
global uniform vec4 rta_model_rim;

varying vec3 v_world;

// the sky's and the haze's colours are stored values (as the game's are): the level's pieces add the haze before they turn
// to linear light (gs_draw.gdshaderinc), so this does too - added as it is, linear, a far figure came out washed to the
// haze's colour (as er_ruin.gdshader)
vec3 lin(vec3 c) {
	return pow((clamp(c, vec3(0.0), vec3(1.0)) + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	if (flip) {
		NORMAL = -NORMAL;
	}
	vec2 uv = (UV * st_scale + tex_offset) / tex_size;
	vec4 a = texture(albedo_tex, uv);
	float alpha = alpha_from == 0 ? a.a * (255.0 / 128.0) : (alpha_from == 1 ? ta0 : 1.0);
	if (cut >= 0.0) {
		float lod = textureQueryLod(albedo_tex, uv).y;
		if (alpha < cut * clamp(1.0 - 0.12 * lod, 0.45, 1.0)) {
			discard;
		}
	}
	ALPHA = 1.0;
	vec3 base = clamp(a.rgb * gain, vec3(0.0), vec3(1.0));
	float rough = 0.75;
	float metal = 0.0;
	float cav = 1.0;
	if (has_mr) {
		vec3 mr = texture(mr_tex, uv).rgb;
		cav = mix(1.0, mr.r, cavity);
		rough = clamp(mr.g, 0.15, 1.0);
		metal = mr.b * metal_amount;
	}
	vec3 n_view = NORMAL;
	float fold = 1.0;
	if (has_normal) {
		vec3 nm = texture(normal_tex, uv).rgb;
		NORMAL_MAP = nm;
		NORMAL_MAP_DEPTH = bump;
		vec3 nt = nm * 2.0 - 1.0;
		nt.xy *= bump;
		nt.z = sqrt(max(1.0 - dot(nt.xy, nt.xy), 0.0));
		n_view = normalize(TANGENT * nt.x + BINORMAL * nt.y + NORMAL * nt.z);
		fold = smoothstep(0.35, 0.95, nt.z);
	}
	ROUGHNESS = rough;
	METALLIC = metal;
	SPECULAR = 0.4;
	vec3 amb = base * (rta_light_ambient.rgb * fill + vec3(floor_light)) * (1.0 - 0.6 * metal) * cav;
	vec3 n_world = normalize((INV_VIEW_MATRIX * vec4(n_view, 0.0)).xyz);
	vec3 n_geo = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	float hemi = mix(0.62, 1.0, n_world.z * 0.5 + 0.5);
	float key_wrap = clamp(dot(n_world, normalize(rta_sky_sun.xyz)) * 0.5 + 0.5, 0.0, 1.0);
	float keyed = mix(1.0, 0.8 + 0.34 * key_wrap * key_wrap, clamp(rta_model.y, 0.0, 1.0));
	vec3 dpx = dFdx(v_world);
	vec3 dpy = dFdy(v_world);
	float bend = (dot(dFdx(n_geo), dpx) / max(dot(dpx, dpx), 1e-6) + dot(dFdy(n_geo), dpy) / max(dot(dpy, dpy), 1e-6)) * 0.5;
	float concave = smoothstep(0.0, 0.6, -bend);
	float occl = (1.0 - fold_dark * (1.0 - fold) * 0.8) * (1.0 - fold_dark * 0.6 * concave);
	amb *= mix(1.0, hemi * keyed * occl, form);
	vec3 to_eye = normalize(CAMERA_POSITION_WORLD - v_world);
	vec3 r = reflect(-to_eye, n_world);
	float fres = pow(1.0 - clamp(dot(n_world, to_eye), 0.0, 1.0), 4.0);
	vec3 sky = lin(rta_sky(r)) * rta_light_ambient.rgb;
	vec3 f0 = mix(vec3(0.04), base, metal);
	vec3 refl = sky * (f0 + (vec3(1.0) - f0) * fres) * (1.0 - rough * 0.75) * sky_reflect * (0.25 + 0.75 * metal) * cav;
	float dist = length(v_world - CAMERA_POSITION_WORLD);
	float h = rta_haze(dist, v_world.z);
	vec3 haze = lin(rta_haze_colour((v_world - CAMERA_POSITION_WORLD) / max(dist, 0.001)));
	vec3 to_eye_v = normalize(VIEW);
	float rim = pow(1.0 - clamp(abs(dot(n_view, to_eye_v)), 0.0, 1.0), 3.0);
	float clothy = smoothstep(0.7, 0.9, rough);
	vec3 rim_light = mix(0.3, sheen, clothy) * rim * rta_model_rim.rgb * rta_model.x * (0.35 + 0.65 * key_wrap) * mix(vec3(0.35), base, 0.65) * occl;
	vec3 tint = vec3(1.0);
	if (game_amb.a > 0.5) {
		vec3 L = game_amb.rgb;
		L += max(dot(n_world, game_sun_dir.xyz), 0.0) * game_sun.rgb;
		L += max(dot(n_world, game_fill_dir.xyz), 0.0) * game_fill.rgb;
		L += max(dot(n_world, normalize(game_p0_pos.xyz - v_world + vec3(0.0, 0.0, 1e-3))), 0.0) * game_p0.rgb;
		L += max(dot(n_world, normalize(game_p1_pos.xyz - v_world + vec3(0.0, 0.0, 1e-3))), 0.0) * game_p1.rgb;
		tint = mix(vec3(1.0), clamp(L, vec3(0.0), vec3(255.0)) / 128.0, game_light);
	}
	vec3 lit = (amb + refl + rim_light) * tint;
	ALBEDO = base * (1.0 - h) * tint * cav;
	EMISSION = lit * (1.0 - h) + haze * h;
}

void light() {
	float facing = dot(NORMAL, LIGHT);
	float wrap = LIGHT_IS_DIRECTIONAL ? mix(clamp(facing * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap) * clamp(facing * 0.5 + 0.75, 0.0, 1.0)
		: clamp(facing * 0.6 + 0.4, 0.0, 1.0);
	DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * wrap;
	if (facing > 0.0) {
		vec3 hv = normalize(VIEW + LIGHT);
		float nh = max(dot(NORMAL, hv), 0.0);
		float a2 = pow(max(ROUGHNESS, 0.15), 4.0);
		float d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
		vec3 f0 = mix(vec3(0.04), ALBEDO, METALLIC);
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * f0 * d * facing * 0.3;
	}
}
