// er_armour.gdshader - the local outfit pieces of er_layer.gd (look.er_models = on), drawn among the game's own draws.
//
// The world's draws are all in Godot's transparent pass (RtaDrawer::place), so a piece is too: it writes ALPHA (1 where
// it is drawn) and its depth.  What made the first pieces look wrong (docs/issues/native-er-layer.md, round 4):
//   - cards (fur, feathers, tatters, hair) were alpha-BLENDED with their depth written, in no order: the texels round a
//     card are white in the textures, so every card showed white streaks where it lay over another.  Here a card is cut
//     (alpha tested: drawn whole or not at all), its edge kept from thinning out with distance (the cut is lowered by
//     the mip level), so nothing is blended and the order does not matter;
//   - the converter mirrored x, so a part's triangles may be wound the other way: er_fit.gd turns them so the front is
//     the outside (a turned-in triangle was lit from behind: the near-black body);
//   - the outfit's textures are made for another game's lighting (image-based light everywhere): here the light is the
//     level's own, as the game's draws take it - the colour times rta_light_ambient where the sun does not reach, the
//     sun with the same wrap as the game's models (gs_draw.gdshaderinc), the haze of atmosphere.gdshaderinc - and a
//     metal gets the sky round it as its reflection (there are no reflections of Godot's in this scene).
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, ambient_light_disabled, fog_disabled, specular_schlick_ggx;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mr_tex : hint_default_white, filter_linear_mipmap, repeat_enable;     // g: roughness, b: metalness (glTF)
uniform vec4 albedo_colour : source_color = vec4(1.0);
uniform bool has_normal = false;
uniform bool has_mr = false;
uniform float cut = -1.0;               // alpha test: drawn where alpha >= cut (< 0: no test)
uniform float metal_amount = 0.6;       // of the metal map's strength
uniform float gain = 1.3;               // the outfit's colours lifted to sit beside the game's painted ones
uniform float fill = 1.0;               // of the level's ambient (rta_light_ambient) where the sun does not reach
uniform float floor_light = 0.10;       // and a little everywhere, so that nothing goes flat black in a dark level
uniform float sun_wrap = 0.55;          // how much of the sun a surface turned away from it still gets (the game's: 0.72)
uniform float sky_reflect = 0.55;       // how much of the sky round it a metal shows
uniform bool flip = false;              // the triangles are wound with the outside at the back (a model not fitted by er_fit.gd)

varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	if (flip) {
		NORMAL = -NORMAL;
	}
	vec4 a = texture(albedo_tex, UV) * albedo_colour;
	if (cut >= 0.0) {
		// the cut lowered with the mip level: a card's coverage stays as it is close up when it is far away
		float lod = textureQueryLod(albedo_tex, UV).y;
		float c = cut * clamp(1.0 - 0.12 * lod, 0.45, 1.0);
		if (a.a < c) {
			discard;
		}
	}
	ALPHA = 1.0;
	vec3 base = clamp(a.rgb * gain, vec3(0.0), vec3(1.0));
	float rough = 0.7;
	float metal = 0.0;
	if (has_mr) {
		vec4 mr = texture(mr_tex, UV);
		rough = clamp(mr.g, 0.18, 1.0);
		metal = mr.b * metal_amount;
	}
	if (has_normal) {
		NORMAL_MAP = texture(normal_tex, UV).rgb;
		NORMAL_MAP_DEPTH = 1.0;
	}
	ALBEDO = base;
	ROUGHNESS = rough;
	METALLIC = metal;
	SPECULAR = 0.35;
	// what arrives where the sun does not: the level's ambient, as the game's own surfaces take it, and a floor
	vec3 amb = base * (rta_light_ambient.rgb * fill + vec3(floor_light)) * (1.0 - 0.6 * metal);
	// a metal reflects the sky round it (the world's normal and view; z is up)
	vec3 n_world = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 to_eye = normalize(CAMERA_POSITION_WORLD - v_world);
	vec3 r = reflect(-to_eye, n_world);
	float fres = pow(1.0 - clamp(dot(n_world, to_eye), 0.0, 1.0), 4.0);
	vec3 sky = rta_sky(r) * rta_light_ambient.rgb;     // (as dark as the level's ambient: a cave's metal does not shine with the sky)
	vec3 f0 = mix(vec3(0.04), base, metal);
	vec3 refl = sky * (f0 + (vec3(1.0) - f0) * fres) * (1.0 - rough * 0.75) * sky_reflect * (0.25 + 0.75 * metal);
	// the haze between the eye and the piece, as the world's (atmosphere.gdshaderinc)
	float dist = length(v_world - CAMERA_POSITION_WORLD);
	float h = rta_haze(dist, v_world.z);
	vec3 haze = rta_haze_colour((v_world - CAMERA_POSITION_WORLD) / max(dist, 0.001));
	ALBEDO = base * (1.0 - h);
	EMISSION = (amb + refl) * (1.0 - h) + haze * h;
}

void light() {
	float facing = dot(NORMAL, LIGHT);
	float wrap = LIGHT_IS_DIRECTIONAL ? mix(clamp(facing * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap) * clamp(facing * 0.5 + 0.75, 0.0, 1.0)
		: clamp(facing * 0.6 + 0.4, 0.0, 1.0);
	DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * wrap;
	// a highlight (GGX) on the side the light comes from
	if (facing > 0.0) {
		vec3 hv = normalize(VIEW + LIGHT);
		float nh = max(dot(NORMAL, hv), 0.0);
		float a2 = pow(max(ROUGHNESS, 0.18), 4.0);
		float d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
		vec3 f0 = mix(vec3(0.04), ALBEDO, METALLIC);
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * f0 * d * facing * 0.25;
	}
}
