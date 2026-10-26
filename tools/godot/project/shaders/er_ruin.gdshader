// er_ruin.gdshader - the Elden Ring world layer's rebuild (er_world.gd, look.er_rebuild): an Elden Ring ruin piece fitted
// over a shape of the level (tools/godot/er_world_fit.py; the drawer leaves the game's own shape out: set_world_hide).
//
// The piece's own albedo and normal map (the owner's local files), its colour drawn towards the colour the game gave the
// shape it stands in for (tint: that shape's texture mean with the game's vertex light, over the piece's own mean), lit as
// remaster_model.gdshader lights the game's figures - the level's ambient given form, the scene's lights, the sky in its
// sheen, the haze - so that it sits in the level's light like the pieces around it.  In the transparent pass at the place
// of the draws it stands in for (like every world draw: RtaDrawer::place), depth tested and written.
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, ambient_light_disabled, fog_disabled, specular_schlick_ggx;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_normal = false;
uniform bool flip_green = true;         // the pieces' normal maps have y down
uniform vec3 tint = vec3(1.0);          // what the colour is drawn by (the game's shape's colour over the piece's own)
uniform float bump = 1.0;
uniform float gain = 1.3;              // (measured on the hub: the game's own pieces come out about this much brighter in their light)
uniform float fill = 1.0;
uniform float floor_light = 0.08;
uniform float sun_wrap = 0.55;
uniform float sky_reflect = 0.12;
uniform float form = 1.0;
uniform float fold_dark = 0.45;
uniform float rough_base = 0.8;
global uniform vec4 rta_model;

varying vec3 v_world;

// the sky's and the haze's colours are stored values (as the game's are): the level's pieces add the haze before they turn
// to linear light (gs_draw.gdshaderinc), so this does too - added as it is, linear, it came out far too pale
vec3 lin(vec3 c) {
	return pow((clamp(c, vec3(0.0), vec3(1.0)) + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	vec4 a = texture(albedo_tex, UV);
	ALPHA = 1.0;
	vec3 base = clamp(a.rgb * tint * gain, vec3(0.0), vec3(1.0));
	vec3 n_view = NORMAL;
	float fold = 1.0;
	if (has_normal) {
		vec3 nm = texture(normal_tex, UV).rgb;
		if (flip_green) {
			nm.g = 1.0 - nm.g;
		}
		NORMAL_MAP = nm;
		NORMAL_MAP_DEPTH = bump;
		vec3 nt = nm * 2.0 - 1.0;
		nt.xy *= bump;
		nt.z = sqrt(max(1.0 - dot(nt.xy, nt.xy), 0.0));
		n_view = normalize(TANGENT * nt.x + BINORMAL * nt.y + NORMAL * nt.z);
		fold = smoothstep(0.35, 0.95, nt.z);
	}
	ROUGHNESS = rough_base;
	METALLIC = 0.0;
	SPECULAR = 0.3;
	vec3 amb = base * (rta_light_ambient.rgb * fill + vec3(floor_light));
	vec3 n_world = normalize((INV_VIEW_MATRIX * vec4(n_view, 0.0)).xyz);
	float hemi = mix(0.62, 1.0, n_world.z * 0.5 + 0.5);
	float key_wrap = clamp(dot(n_world, normalize(rta_sky_sun.xyz)) * 0.5 + 0.5, 0.0, 1.0);
	float keyed = mix(1.0, 0.8 + 0.34 * key_wrap * key_wrap, clamp(rta_model.y, 0.0, 1.0));
	float occl = 1.0 - fold_dark * (1.0 - fold) * 0.8;
	amb *= mix(1.0, hemi * keyed * occl, form);
	vec3 to_eye = normalize(CAMERA_POSITION_WORLD - v_world);
	vec3 r = reflect(-to_eye, n_world);
	float fres = pow(1.0 - clamp(dot(n_world, to_eye), 0.0, 1.0), 5.0);
	vec3 sky = lin(rta_sky(r)) * rta_light_ambient.rgb;
	vec3 refl = sky * (0.04 + 0.96 * fres) * (1.0 - rough_base * 0.75) * sky_reflect * 0.25;
	float dist = length(v_world - CAMERA_POSITION_WORLD);
	float h = rta_haze(dist, v_world.z);
	vec3 haze = lin(rta_haze_colour((v_world - CAMERA_POSITION_WORLD) / max(dist, 0.001)));
	ALBEDO = base * (1.0 - h) * occl;
	EMISSION = (amb + refl) * (1.0 - h) + haze * h;
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
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * 0.04 * d * facing * 0.3;
	}
}
