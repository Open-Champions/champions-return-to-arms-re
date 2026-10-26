// er_ruin.gdshader - the Elden Ring world layer's rebuild (er_world.gd, look.er_rebuild): an Elden Ring piece fitted over a
// shape of the level, or the level's own shape in an Elden Ring material (tools/godot/er_world_fit.py; the drawer leaves the
// game's own shape out: set_world_hide).
//
// Lit exactly as the level's own pieces are (gs_draw.gdshaderinc, GS_LIT with GS_NORMALS): a colour in the game's stored
// values - what the game drew there, its texture's mean times its own vertex light, carried per corner (COLOR, from the
// fitter) - times the piece's own carving, then the level's ambient light and the haze added in stored values before the
// colour turns linear, and the sun by the same wrap.  So a piece darkens, takes the haze and turns from the sun as the level's
// surfaces round it do (gate 4: lit by a light model of its own, the pale marble stayed bright in back light).
// A metal (gold): its colour the game's light there over the shape's mean, so it too darkens in shade; on top a brushed,
// soft highlight from the scene's lights and the sky in its face.  Where it lies on a carving: a relief's raised parts (COLOR.a,
// made per vertex by the fitter from the mesh, smooth across its triangles) through a threshold that widens with the screen
// footprint, so the edge of the gilding stays smooth near and far.
// In the transparent pass at the place of the draws it stands in for (like every world draw: RtaDrawer::place), depth tested
// and written.
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, ambient_light_disabled, fog_disabled;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D albedo_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;   // stored values
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_albedo = true;
uniform bool has_normal = false;
uniform bool flip_green = true;         // the pieces' normal maps have y down
uniform bool game_light = false;        // COLOR holds the game's colour per corner (else: the texture times tint)
uniform vec3 tint = vec3(1.0);          // (without game_light) the game's shape's colour over the piece's own
uniform float gain = 1.0;
uniform float bump = 1.0;
uniform float sun_wrap = 0.72;          // as the level's pieces (gs_draw.gdshaderinc light(), GS_NORMALS)
uniform float direct_gain = 1.0;        // the scene's lights only (a frieze as pale as the game's step in front light, as dark in shade)
// the piece's own carving over the game's colour: its texture's light and dark round its local mean (contrast), and as much
// of its own hue as own_hue says (0: the game's hue, 1: the texture's colour as it is)
uniform float contrast = 1.0;
uniform float own_hue = 0.25;
uniform float detail = 1.0;             // how much of the carving (0: the game's colour alone, a plain surface)
// the colour the recipe lays the texture in instead (a marble, a gold: the old recolour)
uniform vec3 recolour = vec3(1.0);              // (stored values, as every colour here)
uniform float recolour_amount = 0.0;
uniform float recolour_detail = 1.0;
// weathering: grime near the foot, moss in patches on what faces up, the relief's crests a little worn
uniform float ground_z = -1.0e9;
uniform float grime_height = 9.0;
uniform float grime = 0.2;
uniform vec3 moss_colour = vec3(0.30, 0.36, 0.16);
uniform float moss = 0.0;
uniform float moss_scale = 0.035;
uniform float edge_wear = 0.15;
uniform float riser_dark = 0.0;
// a step's crisp edge (a riser: COLOR.a its height, 0 at the foot .. 1 at the top edge): a worn, pale nosing along the top
// (nosing_w of the height) and a dark line in the crease at the foot (foot_w), each edge as sharp as a pixel at any distance
uniform float nosing = 0.0;
uniform float nosing_w = 0.18;
uniform float foot_ao = 0.0;
uniform float foot_w = 0.22;
// the carving read at play distance: the texture's dark (its cuts) darker as in a cavity, its crests lighter as worn edges
// (round the local mean: the brightness kept); and its contrast raised with distance as the mip maps flatten it
uniform float cavity = 0.0;
uniform float crest = 0.0;
uniform float far_contrast = 1.0;
uniform vec2 far_range = vec2(250.0, 900.0);
// metal
uniform float metallic = 0.0;           // the whole surface (a moulding, a trim)
uniform sampler2D metal_tex : hint_default_white, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_metal = false;
uniform int metal_channel = 0;
uniform vec2 metal_range = vec2(0.0, 1.0);
uniform sampler2D mask_tex : hint_default_black, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_mask = false;
uniform float mask_polish = 0.0;
uniform float metal_wear = 0.0;        // a worn inlay: patches where the gold has gone and the stone under it shows
uniform float gild = 0.0;               // the relief's raised parts in metal (COLOR.a over gild_at)
uniform float gild_at = 0.5;
uniform float gild_soft = 0.08;         // the edge's half width at least (it widens with the footprint)
uniform vec3 metal_colour = vec3(0.80, 0.58, 0.26);
uniform float metal_gain = 1.0;
uniform float metal_diffuse = 0.85;     // the share of a metal's colour lit as the stone is (a worn, painted gold); the rest its sheen
uniform vec3 light_ref = vec3(0.5);     // the game's mean colour over the shape (a metal's light is the game's light over it)
uniform float metal_sheen = 0.35;       // the sky in a metal's face
uniform float stone_sheen = 0.0;        // the sky in a polished stone's face (the game's environment-mapped pass on a shaft): its hue in shade
uniform float glint = 0.6;              // a metal's highlight from the level's lights
uniform float rough_along = 0.22;       // the brushed highlight: narrow along the brushing, broad across it
uniform float rough_across = 0.55;
global uniform vec4 rta_model;

varying vec3 v_world;
varying vec4 v_game;
varying vec3 v_brush;                   // (view space) the brushing's direction, for light()
varying float v_metal;

vec3 lin(vec3 c) {
	return pow((clamp(c, vec3(0.0), vec3(1.0)) + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

float lum(vec3 c) {
	return dot(c, vec3(0.3, 0.59, 0.11));
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
	v_game = COLOR;
}

void fragment() {
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	ALPHA = 1.0;
	// the carving: the texture round its local mean (stored values)
	vec3 a = has_albedo ? texture(albedo_tex, UV).rgb : vec3(0.5);
	vec3 local_mean = has_albedo ? textureLod(albedo_tex, UV, 7.0).rgb : vec3(0.5);
	float eye_dist = length(v_world - CAMERA_POSITION_WORLD);
	float k_contrast = contrast * mix(1.0, far_contrast, smoothstep(far_range.x, far_range.y, eye_dist));
	vec3 carved = max(local_mean + (a - local_mean) * k_contrast, vec3(0.0));
	if (recolour_amount > 0.0) {
		float d = mix(1.0, lum(carved) / max(lum(local_mean), 0.03), recolour_detail);
		carved = mix(carved, recolour * d, recolour_amount);
		local_mean = mix(local_mean, recolour, recolour_amount);
	}
	vec3 rel = carved / max(vec3(lum(local_mean)), vec3(0.03));               // ~1: the carving's light and dark, its own colour
	vec3 rel_grey = vec3(lum(rel));
	vec3 rel_mix = mix(vec3(1.0), mix(rel_grey, rel, own_hue), detail);
	if (cavity > 0.0 || crest > 0.0) {
		// the cuts as cavities (squared: the deep ones darkest), the crests a little worn; the two balance round the mean
		float r = rel_grey.x;
		float cut = clamp(1.0 - r, 0.0, 1.0);
		float top = clamp(r - 1.0, 0.0, 1.0);
		rel_mix *= (1.0 - cavity * cut * (0.6 + 0.8 * cut)) * (1.0 + crest * top);
		rel_mix *= 1.0 + cavity * 0.05 - crest * 0.06;
	}
	vec3 game = game_light ? v_game.rgb * gain : local_mean * tint * gain;
	float relief = game_light ? v_game.a : 0.0;
	vec3 s = game * rel_mix;
	// normal map
	vec3 nm_t = vec3(0.0, 0.0, 1.0);
	if (has_normal) {
		vec3 nm = texture(normal_tex, UV).rgb;
		if (flip_green) {
			nm.g = 1.0 - nm.g;
		}
		NORMAL_MAP = nm;
		NORMAL_MAP_DEPTH = bump;
		nm_t = nm * 2.0 - 1.0;
	}
	vec3 n_geo_world = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	// weathering
	s *= 1.0 + edge_wear * (relief - 0.5) * 0.5;
	s *= 1.0 - riser_dark * (1.0 - abs(n_geo_world.z));
	if (nosing > 0.0 || foot_ao > 0.0) {
		float fw = max(fwidth(relief), 0.002);
		float nose = smoothstep(1.0 - nosing_w - fw, 1.0 - nosing_w + fw, relief);
		float foot = 1.0 - smoothstep(foot_w - fw, foot_w + fw, relief);
		// the cavity of the normal map deepens the crease's shadow; the nosing is worn smooth
		s *= (1.0 + nosing * nose) * (1.0 - foot_ao * foot * (0.75 + 0.25 * (1.0 - nm_t.z)));
	}
	float low = 1.0 - smoothstep(0.0, grime_height, v_world.z - ground_z);
	s *= 1.0 - grime * low * (0.6 + 0.4 * vnoise(v_world.xy * 0.2));
	float patches = smoothstep(0.45, 0.8, vnoise(v_world.xy * moss_scale + vec2(3.1, 7.7)) * 0.7 + vnoise(v_world.xy * moss_scale * 4.0) * 0.3);
	float up = smoothstep(0.55, 0.92, n_geo_world.z);
	float crack = (1.0 - smoothstep(0.35, 0.95, nm_t.z)) * smoothstep(0.3, 0.6, vnoise(v_world.xy * 0.3));
	float mossy = clamp(patches * up + crack * 0.6 + low * 0.5 * patches, 0.0, 1.0) * moss;
	s = mix(s, moss_colour * lum(game) * 2.0 * (0.75 + 0.5 * lum(a)), mossy);
	// metal: where, and its colour - the game's light here over the shape's mean (dark where the game is dark)
	float metal = metallic;
	if (has_metal) {
		float mv = texture(metal_tex, UV)[clamp(metal_channel, 0, 3)];
		metal = max(metal, smoothstep(metal_range.x, metal_range.y, mv));
	}
	if (gild > 0.0) {
		// a soft edge that widens with the footprint (mip-aware: far away it averages instead of flickering)
		float w = max(gild_soft, fwidth(relief) * 1.5);
		metal = max(metal, gild * smoothstep(gild_at - w, gild_at + w, relief));
	}
	metal *= 1.0 - mossy;
	if (metal_wear > 0.0) {
		float wn = vnoise(v_world.xy * 0.35 + vec2(v_world.z * 0.2, 1.7)) * 0.65 + vnoise(v_world.xy * 1.4) * 0.35;
		metal *= 1.0 - metal_wear * smoothstep(0.52, 0.68, wn);
	}
	float lit_here = game_light ? clamp(lum(v_game.rgb) / max(lum(light_ref), 0.02), 0.2, 2.5) : 1.0;
	vec3 gold = metal_colour * metal_gain * lit_here * clamp(mix(1.0, rel_grey.x, 0.35 * detail), 0.75, 1.25);
	// the brushing: round the piece (horizontal on what stands), for the highlight in light(); its fine streaks along it
	vec3 brush_w = cross(vec3(0.0, 0.0, 1.0), n_geo_world);
	brush_w = dot(brush_w, brush_w) < 1e-4 ? vec3(1.0, 0.0, 0.0) : normalize(brush_w);
	vec3 brush_across = cross(n_geo_world, brush_w);
	float streak = vnoise(vec2(dot(v_world, brush_w) * 0.04, dot(v_world, brush_across) * 2.5)) * 0.6
		+ vnoise(vec2(dot(v_world, brush_w) * 0.1, dot(v_world, brush_across) * 7.0)) * 0.4;
	gold *= 0.88 + 0.24 * streak;
	vec3 c = clamp(mix(s, gold * metal_diffuse, metal), vec3(0.0), vec3(1.0));
	v_metal = metal;
	v_brush = normalize((VIEW_MATRIX * vec4(brush_w, 0.0)).xyz);
	// as the level's pieces: no specular of their own, the ambient and the haze in stored values (gs_draw.gdshaderinc GS_LIT)
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	SPECULAR = 0.0;
	float dist = length(v_world - CAMERA_POSITION_WORLD);
	float h = rta_haze(dist, v_world.z);
	vec3 haze = rta_haze_colour((v_world - CAMERA_POSITION_WORLD) / max(dist, 0.001)) * h;
	ALBEDO = lin(c * (1.0 - h));
	EMISSION = lin(clamp(c * (1.0 - h) * rta_light_ambient.rgb + haze, vec3(0.0), vec3(1.0)));
	if (stone_sheen > 0.0) {
		// a polished stone: the sky in its face, soft (its colour the sky's), as dark as the game's light here
		vec3 n_s = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
		vec3 e_s = normalize(CAMERA_POSITION_WORLD - v_world);
		vec3 sky_s = rta_sky(normalize(reflect(-e_s, n_s)));
		float f_s = 0.35 + 0.65 * pow(1.0 - clamp(dot(n_s, e_s), 0.0, 1.0), 2.0);
		EMISSION += lin(clamp(sky_s * lum(game) * stone_sheen * f_s * (1.0 - metal), vec3(0.0), vec3(1.0))) * (1.0 - h);
	}
	if (metal > 0.0) {
		// the sky in a metal's face, blurred across the brushing (three looks), under the level's ambient and as dark as the
		// game's light here
		vec3 n_world = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
		vec3 to_eye = normalize(CAMERA_POSITION_WORLD - v_world);
		vec3 r = reflect(-to_eye, n_world);
		vec3 across = normalize(cross(r, brush_w) + vec3(1e-4));
		vec3 sky = (rta_sky(normalize(r)) + rta_sky(normalize(r + across * 0.35)) + rta_sky(normalize(r - across * 0.35))) / 3.0;
		float fres = pow(1.0 - clamp(dot(n_world, to_eye), 0.0, 1.0), 5.0);
		vec3 sheen = gold * mix(vec3(1.0), vec3(lum(gold)) * 1.6, fres * 0.5) * sky * rta_light_ambient.rgb * metal_sheen * lit_here;
		EMISSION += lin(clamp(sheen, vec3(0.0), vec3(1.0))) * metal * (1.0 - h);
	}
}

void light() {
	float facing = dot(NORMAL, LIGHT);
	// the level's own wrap (gs_draw.gdshaderinc light(), GS_NORMALS)
	float wrap = LIGHT_IS_DIRECTIONAL ? mix(clamp(facing * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap) : clamp(facing * 0.6 + 0.4, 0.0, 1.0);
	// a face turned from the sun lies in its own shadow, as the level's do (their twins throw it on them; a piece laid a
	// little in front of the game's own face is not reached by that shadow)
	float self_shade = LIGHT_IS_DIRECTIONAL ? smoothstep(-0.1, 0.15, facing) : 1.0;
	DIFFUSE_LIGHT += ATTENUATION * self_shade * LIGHT_COLOR / PI * wrap * direct_gain;
	if (v_metal > 0.0 && facing > 0.0) {
		// a brushed metal's highlight (anisotropic GGX, Burley), soft and in its own colour; none in the piece's shadow
		vec3 hv = normalize(VIEW + LIGHT);
		vec3 t = normalize(v_brush - NORMAL * dot(v_brush, NORMAL));
		vec3 b = cross(NORMAL, t);
		float th = dot(t, hv);
		float bh = dot(b, hv);
		float nh = max(dot(NORMAL, hv), 0.0);
		float ax = rough_along;
		float ay = rough_across;
		float k = th * th / (ax * ax) + bh * bh / (ay * ay) + nh * nh;
		float d = 1.0 / (PI * ax * ay * k * k);
		float spec = min(d, 8.0) * facing * 0.25;
		SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * ALBEDO * spec * v_metal * glint;
	}
}
