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
// the weathering of a ruin (gate 3: the plain pieces read flatter than the game's painted ones): the texture's own carving
// lifted from its local mean, worn light on the outer edges and dark in the inner corners (a step reads as a step), grime
// near the ground, moss in patches on what faces up and in the cracks
uniform float contrast = 1.35;
uniform float edge_wear = 0.45;
uniform float ground_z = -1.0e9;       // the piece's foot (world z), set by er_world.gd
uniform float grime_height = 9.0;
uniform float grime = 0.35;
uniform vec3 moss_colour : source_color = vec3(0.30, 0.36, 0.16);
uniform float moss = 0.45;
uniform float moss_scale = 0.035;
// the material the recipe may give a surface (er_world_fit.py "surfaces"): a metal (gold: its colour the reflection's, its
// own light a glint), a colour the texture's carving is laid in (marble, gold), a mask map's polish
uniform float metallic = 0.0;
uniform sampler2D metal_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_metal = false;
uniform int metal_channel = 0;         // which of the metal map's channels (a mask map's band lines: green)
uniform vec2 metal_range = vec2(0.0, 1.0);   // that channel's values from no metal to all metal
uniform vec3 metal_colour : source_color = vec3(0.80, 0.58, 0.26);
uniform float metal_colour_amount = 0.0;    // where a metal map makes metal, that metal's colour (gold inlaid in a stone)
uniform vec3 recolour : source_color = vec3(1.0);
uniform float recolour_amount = 0.0;
uniform float recolour_detail = 1.0;   // how strongly the texture's own light and dark stay in the new colour
uniform sampler2D mask_tex : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_mask = false;
uniform float mask_polish = 0.0;       // the mask's red: polished (smoother) where it is bright (a marble's veins)
uniform float metal_sheen = 1.0;       // the sky in a metal's face
uniform float glint = 1.0;             // a metal's highlight from the level's lights
uniform float gild = 0.0;              // the carving's raised edges gilt (metal on the outer bends of the geometry: a relief's
                                       // figures and mouldings picked out in the metal colour)
uniform float riser_dark = 0.0;        // faces that stand up (a step's riser) darker than those facing up: the steps read
global uniform vec4 rta_model;

varying vec3 v_world;

// the sky's and the haze's colours are stored values (as the game's are): the level's pieces add the haze before they turn
// to linear light (gs_draw.gdshaderinc), so this does too - added as it is, linear, it came out far too pale
vec3 lin(vec3 c) {
	return pow((clamp(c, vec3(0.0), vec3(1.0)) + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = fract(sin(dot(i, vec2(127.1, 311.7))) * 43758.5453);
	float b = fract(sin(dot(i + vec2(1.0, 0.0), vec2(127.1, 311.7))) * 43758.5453);
	float c = fract(sin(dot(i + vec2(0.0, 1.0), vec2(127.1, 311.7))) * 43758.5453);
	float d = fract(sin(dot(i + vec2(1.0, 1.0), vec2(127.1, 311.7))) * 43758.5453);
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
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
	vec3 local_mean = textureLod(albedo_tex, UV, 6.0).rgb;
	vec3 carved = max(local_mean + (a.rgb - local_mean) * contrast, vec3(0.0));
	if (recolour_amount > 0.0) {
		float lum_here = dot(carved, vec3(0.3, 0.59, 0.11));
		float lum_mean = max(dot(local_mean, vec3(0.3, 0.59, 0.11)), 0.03);
		float detail = mix(1.0, lum_here / lum_mean, recolour_detail);
		carved = mix(carved, recolour * detail, recolour_amount);
	}
	vec3 base = clamp(carved * tint * gain, vec3(0.0), vec3(1.0));
	float metal = metallic;
	if (has_metal) {
		float mv = texture(metal_tex, UV)[clamp(metal_channel, 0, 3)];
		metal *= smoothstep(metal_range.x, metal_range.y, mv);
		float lum_m = dot(base, vec3(0.3, 0.59, 0.11)) / max(dot(local_mean * tint * gain, vec3(0.3, 0.59, 0.11)), 0.03);
		base = mix(base, clamp(metal_colour * mix(1.0, lum_m, 0.6), vec3(0.0), vec3(1.0)), metal * metal_colour_amount);
	}
	float polish = has_mask ? texture(mask_tex, UV).r * mask_polish : 0.0;
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
	// weathering (see the uniforms): the geometry's own bend from the screen derivatives (as remaster_model.gdshader)
	vec3 n_geo = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 n_geo_world = n_geo;
	vec3 n_up = normalize((INV_VIEW_MATRIX * vec4(n_view, 0.0)).xyz);
	vec3 dpx = dFdx(v_world);
	vec3 dpy = dFdy(v_world);
	float bend = (dot(dFdx(n_geo), dpx) / max(dot(dpx, dpx), 1e-6) + dot(dFdy(n_geo), dpy) / max(dot(dpy, dpy), 1e-6)) * 0.5;
	float convex = smoothstep(0.02, 0.5, bend);
	float concave = smoothstep(0.02, 0.5, -bend);
	base *= 1.0 + edge_wear * (0.6 * convex - concave);
	if (gild > 0.0) {
		float g = clamp(smoothstep(0.1, 0.9, convex) * gild, 0.0, 1.0);
		float lum_g = dot(base, vec3(0.3, 0.59, 0.11)) / max(dot(local_mean * tint * gain, vec3(0.3, 0.59, 0.11)), 0.03);
		base = mix(base, clamp(metal_colour * mix(1.0, lum_g, 0.5), vec3(0.0), vec3(1.0)), g);
		metal = max(metal, g);
	}
	base *= 1.0 - riser_dark * (1.0 - abs(n_geo_world.z));
	float low = 1.0 - smoothstep(0.0, grime_height, v_world.z - ground_z);
	base *= 1.0 - grime * low * (0.6 + 0.4 * vnoise(v_world.xy * 0.2));
	float patches = smoothstep(0.45, 0.8, vnoise(v_world.xy * moss_scale + vec2(3.1, 7.7)) * 0.7 + vnoise(v_world.xy * moss_scale * 4.0) * 0.3);
	float up = smoothstep(0.55, 0.92, n_up.z);
	float crack = (1.0 - fold) * smoothstep(0.3, 0.6, vnoise(v_world.xy * 0.3));
	float mossy = clamp(patches * up + crack * 0.6 + low * 0.5 * patches, 0.0, 1.0) * moss;
	vec3 moss_base = moss_colour * (0.75 + 0.5 * dot(a.rgb, vec3(0.3, 0.59, 0.11)));
	base = clamp(mix(base, moss_base, mossy), vec3(0.0), vec3(1.0));
	float rough = clamp(rough_base + 0.15 * mossy - 0.15 * convex - polish, 0.05, 1.0);
	ROUGHNESS = rough;
	METALLIC = metal * (1.0 - mossy);
	SPECULAR = 0.3;
	vec3 amb = base * (rta_light_ambient.rgb * fill + vec3(floor_light)) * (1.0 - METALLIC * 0.85);
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
	vec3 refl = sky * (0.04 + 0.96 * fres) * (1.0 - rough * 0.75) * sky_reflect * 0.25;
	// a metal: the sky and the level's light in its face, in its own colour (gold), whiter at a grazing angle; its edges,
	// which face the light from every side, the brightest (the gold trim reads as gold from afar)
	vec3 env = (sky + rta_light_ambient.rgb * 0.6) * (1.0 - rough * 0.6);
	vec3 metal_refl = env * mix(base, vec3(1.0), fres * 0.6) * metal_sheen * (1.0 + 0.8 * convex);
	refl = mix(refl, metal_refl, METALLIC);
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
	DIFFUSE_LIGHT *= 1.0 - METALLIC * 0.85;
	if (facing > 0.0) {
		vec3 hv = normalize(VIEW + LIGHT);
		float nh = max(dot(NORMAL, hv), 0.0);
		float a2 = pow(max(ROUGHNESS, 0.15), 4.0);
		float d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * 0.04 * d * facing * 0.3 * (1.0 - METALLIC);
		// a metal's highlight in its own colour, with a broad sheen under it (a worn gold catches the light over its form)
		float broad = pow(nh, 6.0);
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * ALBEDO * (min(d, 12.0) * 0.35 + broad * 0.6) * facing * METALLIC * glint;
	}
}
