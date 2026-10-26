// remaster_model.gdshader - the game's own figures remastered (model_remaster.gd, look.remaster_models).
//
// The mesh is the figure's own bind-pose mesh subdivided (RtaRemaster), skinned by the game's pose every frame; its
// colour is the game's own texture (the art pack's 4x picture where there is one), read with the very coordinates and
// texture state the game's draw has (st_scale, tex_offset, tex_size), and two maps derived from it on this machine: a
// normal map and ORM (r cavity, g roughness, b metal).  The light is er_armour.gdshader's - the level's ambient given
// form, the scene's lights, a metal's sky, the haze - and the game's own light on the figure (its torches, poison, hit
// flash: game_*, per figure: each figure has its own materials - the world's draws fill the instance-uniform
// buffer), so that the body and the Elden Ring / Tripo pieces fitted over it are lit alike.
//
// The classes of the texels (RtaRemaster.derive_maps) are lit each as what it is: METAL dark in its diffuse and bright in
// its highlight, which takes the metal's own colour and Fresnel's white at the rim, with a highlight of the sky's key even
// where no lamp lights it; SKIN with a soft warm band where light turns to shadow (light that has gone under the skin and
// come out redder), its shadows warmer, its highlight broad and weak; HAIR and FUR with a sheen along the strand
// (Kajiya-Kay: two highlights shifted along the hair, the second coloured by it; the strand's direction is the texture's
// own streaks), fur's broader and softer; CLOTH and STONE rough and nearly without a highlight.  AUX: r skin, g hair,
// b/a the strand's doubled angle in the picture; ORM a: fur.
shader_type spatial;
render_mode blend_mix, depth_draw_always, cull_disabled, ambient_light_disabled, fog_disabled, specular_schlick_ggx;

#include "res://shaders/atmosphere.gdshaderinc"

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mr_tex : hint_default_white, filter_linear_mipmap, repeat_enable;     // r: cavity, g: roughness, b: metal
uniform bool has_normal = false;
uniform bool has_mr = false;
uniform sampler2D aux_tex : hint_default_black, filter_linear_mipmap, repeat_enable;   // r skin, g hair, b/a strand (doubled angle)
uniform bool has_aux = false;
// a two-pass packet whose first pass is its own colour (albedo_tex): the second pass's picture over it, as the game blends
// it (a face's paint: brows, lips, eyes)
uniform sampler2D over_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool has_over = false;
uniform vec2 over_st = vec2(1.0);
uniform vec2 over_offset = vec2(0.0);
uniform vec2 over_size = vec2(1.0);
uniform int over_alpha_from = 0;
uniform float over_ta0 = 1.0;
// a two-pass packet whose first pass is an environment map (the players' sheen): that map, by the direction of the
// surface as the camera sees it (a sphere map), and this pass blended over it as the game blends it - GS (A - B) * C + D,
// A B D: 0 this pass, 1 the map, 2 nothing; C: 0 this pass's alpha, 1 the map's (1), 2 FIX
uniform sampler2D env_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform bool has_env = false;
uniform ivec4 blend_abcd = ivec4(0, 1, 0, 1);
uniform float blend_fix = 1.0;

vec3 gs_pick(int k, vec3 cs, vec3 cd) {
	return k == 0 ? cs : (k == 1 ? cd : vec3(0.0));
}
uniform float sss = 1.0;                // of skin's warm band
uniform float sheen_amount = 1.0;       // of the strands' sheen
uniform float spec_amount = 1.0;        // of the highlights
uniform float shrink = 0.0;
uniform float lift = 0.0;               // units a decal is drawn above the surface it lies on             // units the surface is drawn inside itself (under a fitted outfit: no poke-through)
uniform vec2 st_scale = vec2(1.0);
uniform vec2 tex_offset = vec2(0.0);
uniform vec2 tex_size = vec2(1.0);
uniform int alpha_from = 0;             // 0 the texture's (128 = opaque), 1 a constant (ta0), 2 none
uniform float ta0 = 1.0;
uniform float cut = -1.0;               // alpha test: drawn where alpha >= cut (< 0: no test)
uniform bool see_behind = false;        // the game draws it as itself plus what is behind it by its alpha: dark texels of
                                        // high alpha are mostly what is behind (lashes, brows): not drawn
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
uniform vec4 game_sh[9];                // the game's own light on this figure this frame by direction (RtaRemaster.light_sh)
uniform bool has_sh = false;
uniform float game_match = 1.0;         // 1: the figure as bright as the game's own (its light, as the game lights it, is the
                                        // diffuse), the scene's lights giving form and highlights over it; 0: lit as the outfits
uniform float scene_keep = 1.0;
uniform float game_dir_sign = 1.0;
uniform int debug_view = 0;             // (tests) 1: the game's light, 2: the normal, 3: skin / strands / metal      // (tests) the game's sun and fill directions turned round        // (game_match) how much of the scene's lights' diffuse is kept
global uniform vec4 rta_model;
global uniform vec4 rta_model_rim;

varying vec3 v_world;
varying float v_skin;
varying float v_hair;
varying float v_fur;
varying vec3 v_strand;
varying vec3 v_base;
varying float v_metal;                    // the colour the highlights take (ALBEDO is scaled down under game_match)

// the sky's and the haze's colours are stored values (as the game's are): the level's pieces add the haze before they turn
// to linear light (gs_draw.gdshaderinc), so this does too - added as it is, linear, a far figure came out washed to the
// haze's colour (as er_ruin.gdshader)
vec3 lin(vec3 c) {
	return pow((clamp(c, vec3(0.0), vec3(1.0)) + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
}

void vertex() {
	VERTEX -= NORMAL * (shrink - lift);
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

// the highlight of a strand (Kajiya-Kay) about tangent t, half vector hv
float strand_spec(vec3 t, vec3 hv, float e) {
	float th = dot(t, hv);
	return pow(sqrt(max(1.0 - th * th, 0.0)), e);
}

float ggx(float nh, float rough) {
	float a2 = pow(max(rough, 0.12), 4.0);
	return a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
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
	if (see_behind && alpha > 0.5 && dot(a.rgb, vec3(0.299, 0.587, 0.114)) < 0.18) {
		discard;
	}
	ALPHA = 1.0;
	vec3 base = clamp(a.rgb * gain, vec3(0.0), vec3(1.0));
	if (has_env) {
		// (stored values, as the game blends them)
		vec2 suv = NORMAL.xy * vec2(0.5, -0.5) + 0.5;
		vec3 cd = texture(env_tex, suv).rgb;
		float as_ = alpha_from == 0 ? a.a * (255.0 / 128.0) : (alpha_from == 1 ? ta0 : 1.0);
		float c = blend_abcd.z == 0 ? as_ : (blend_abcd.z == 1 ? 1.0 : blend_fix);
		vec3 cs = pow(base, vec3(1.0 / 2.2));
		cd = pow(cd, vec3(1.0 / 2.2));
		vec3 r = (gs_pick(blend_abcd.x, cs, cd) - gs_pick(blend_abcd.y, cs, cd)) * c + gs_pick(blend_abcd.w, cs, cd);
		base = pow(clamp(r, vec3(0.0), vec3(1.0)), vec3(2.2));
	}
	if (has_over) {
		vec4 ov = texture(over_tex, (UV * over_st + over_offset) / over_size);
		float oa = over_alpha_from == 0 ? ov.a * (255.0 / 128.0) : (over_alpha_from == 1 ? over_ta0 : 1.0);
		base = mix(base, clamp(ov.rgb * gain, vec3(0.0), vec3(1.0)), clamp(oa, 0.0, 1.0));
	}
	float rough = 0.75;
	float metal = 0.0;
	float cav = 1.0;
	float fur = 0.0;
	if (has_mr) {
		vec4 mr = texture(mr_tex, uv);
		cav = mix(1.0, mr.r, cavity);
		rough = clamp(mr.g, 0.12, 1.0);
		metal = mr.b * metal_amount;
		fur = mr.a;
	}
	float skin = 0.0;
	float hair = 0.0;
	vec3 strand = TANGENT;
	if (has_aux) {
		vec4 ax = texture(aux_tex, uv);
		skin = ax.r;
		hair = ax.g;
		vec2 d2 = ax.ba * 2.0 - 1.0;
		float th = 0.5 * atan(d2.y, d2.x);
		// the picture's +v is down; BINORMAL points up it
		strand = normalize(TANGENT * cos(th) - BINORMAL * sin(th));
	}
	v_skin = skin;
	v_hair = hair;
	v_fur = fur;
	v_strand = strand;
	// a metal's colour is in its highlight, not its diffuse: darker, more saturated base
	base = mix(base, base * base * 1.35, metal * 0.55 * (1.0 - game_match));     // (not where the figure is to be as bright as the game's)
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
	SPECULAR = mix(0.4, 0.22, smoothstep(0.8, 0.95, rough)) * mix(1.0, 0.75, skin);
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
	// skin's shadows are warmer (light that went under it comes out red): its occlusion takes less red than blue
	vec3 occl_c = mix(vec3(occl), pow(vec3(occl), vec3(0.6, 1.0, 1.2)), skin * sss);
	amb *= mix(vec3(1.0), hemi * keyed * occl_c, form);
	vec3 to_eye = normalize(CAMERA_POSITION_WORLD - v_world);
	vec3 r = reflect(-to_eye, n_world);
	float fres = pow(1.0 - clamp(dot(n_world, to_eye), 0.0, 1.0), 4.0);
	// the sky as a metal mirrors it, its colour taken half out: a blue sky (or a cave's dark blue one) would turn every
	// steel plate blue, where the game's own figures keep the colours they were painted in
	vec3 sky_c = lin(rta_sky(r));
	vec3 sky = mix(vec3(dot(sky_c, vec3(0.2126, 0.7152, 0.0722))), sky_c, 0.45) * rta_light_ambient.rgb;
	vec3 f0 = mix(vec3(0.04), base, metal);
	vec3 refl = sky * (f0 + (vec3(1.0) - f0) * fres) * (1.0 - rough * 0.75) * sky_reflect * (0.25 + 0.75 * metal) * cav;
	// the sky's key, even where no lamp lights the figure: a metal's highlight, the strands' sheen
	// (where the game lights the figure, its own sun is the key: the highlights sit where its light comes from)
	bool game_key = game_amb.a > 0.5 && game_match > 0.0;
	vec3 key_w = game_key ? game_sun_dir.xyz : normalize(rta_sky_sun.xyz + vec3(0.0, 0.0, 0.35));
	vec3 key_v = normalize((VIEW_MATRIX * vec4(key_w, 0.0)).xyz);
	vec3 key_h = normalize(key_v + VIEW);
	float key_face = game_key ? clamp(dot(n_view, key_v) * 2.0, 0.0, 1.0) : clamp(dot(n_view, key_v) * 0.5 + 0.5, 0.0, 1.0);
	vec3 key_col = (game_key ? game_sun.rgb / 128.0 * 1.6 : rta_light_ambient.rgb) * spec_amount * cav;
	float vh = clamp(dot(VIEW, key_h), 0.0, 1.0);
	vec3 key_f = f0 + (vec3(1.0) - f0) * pow(1.0 - vh, 5.0);
	// (a dielectric's key highlight broad and faint: on a bumpy hide a sharp one sparkles like frost)
	refl += key_col * key_f * min(ggx(max(dot(n_view, key_h), 0.0), max(rough, mix(0.45, 0.2, metal))), 12.0) * key_face * mix(0.008, 0.22, metal);
	float strands = clamp(hair + fur, 0.0, 1.0);
	if (strands > 0.01) {
		vec3 t = normalize(strand - n_view * dot(n_view, strand));
		float hairy = hair / max(hair + fur, 0.001);
		float s1 = strand_spec(normalize(t + n_view * 0.1), key_h, mix(14.0, 70.0, hairy));
		float s2 = strand_spec(normalize(t - n_view * 0.15), key_h, mix(5.0, 18.0, hairy));
		refl += key_col * (s1 * mix(0.06, 0.16, hairy) + s2 * 0.12 * base) * key_face * strands * sheen_amount;
	}
	float dist = length(v_world - CAMERA_POSITION_WORLD);
	float h = rta_haze(dist, v_world.z);
	vec3 haze = lin(rta_haze_colour((v_world - CAMERA_POSITION_WORLD) / max(dist, 0.001)));
	vec3 to_eye_v = normalize(VIEW);
	float rim = pow(1.0 - clamp(abs(dot(n_view, to_eye_v)), 0.0, 1.0), 3.0);
	float clothy = max(smoothstep(0.7, 0.9, rough), fur);
	vec3 rim_light = mix(0.3, sheen, clothy) * mix(1.0, 0.6, skin) * rim * rta_model_rim.rgb * rta_model.x * (0.35 + 0.65 * key_wrap) * mix(vec3(0.35), base, 0.65) * occl;
	vec3 tint = vec3(1.0);
	vec3 lg = vec3(1.0);
	bool has_game = game_amb.a > 0.5 || has_sh;
	if (has_sh) {
		// the game's light as its vertex program gave it to this figure's corners this frame, at this surface's normal
		vec3 n = n_world;
		lg = game_sh[0].rgb + game_sh[1].rgb * n.y + game_sh[2].rgb * n.z + game_sh[3].rgb * n.x + game_sh[4].rgb * n.x * n.y
			+ game_sh[5].rgb * n.y * n.z + game_sh[6].rgb * (3.0 * n.z * n.z - 1.0) + game_sh[7].rgb * n.x * n.z
			+ game_sh[8].rgb * (n.x * n.x - n.y * n.y);
		lg = clamp(lg, vec3(0.0), vec3(255.0 / 128.0));
		tint = mix(vec3(1.0), lg, game_light);
	} else if (has_game) {
		vec3 L = game_amb.rgb;
		L += max(dot(n_world, game_sun_dir.xyz * game_dir_sign), 0.0) * game_sun.rgb;
		L += max(dot(n_world, game_fill_dir.xyz * game_dir_sign), 0.0) * game_fill.rgb;
		L += max(dot(n_world, normalize(game_p0_pos.xyz - v_world + vec3(0.0, 0.0, 1e-3))), 0.0) * game_p0.rgb;
		L += max(dot(n_world, normalize(game_p1_pos.xyz - v_world + vec3(0.0, 0.0, 1e-3))), 0.0) * game_p1.rgb;
		lg = clamp(L, vec3(0.0), vec3(255.0)) / 128.0;
		tint = mix(vec3(1.0), lg, game_light);
	}
	vec3 lit = (amb + refl + rim_light) * tint;
	ALBEDO = base * (1.0 - h) * tint * cav;
	v_base = ALBEDO;
	v_metal = metal;
	EMISSION = lit * (1.0 - h) + haze * h;
	if (has_game && game_match > 0.0) {
		// the figure as the game's own draws of it are drawn here (gs_draw.gdshaderinc): the game's texture times its light
		// in stored (gamma) values, clamped there per channel (a light brighter than the colour can take goes white, as
		// in the game); that times the level's ambient is what arrives where no lamp does, and the scene's lights add
		// their share of it as of the game's own figures - shaped here by this surface's folds and cavities, with the
		// reflections, the rim and the highlights over it
		float shape = mix(1.0, hemi * occl, form * 0.6);
		vec3 occ = mix(vec3(1.0), occl_c / max(occl, 0.001), skin * sss);
		vec3 g = clamp(pow(base, vec3(1.0 / 2.2)) * lg, vec3(0.0), vec3(1.0));
		vec3 lgl = min(pow(lg, vec3(2.2)), vec3(1.5));
		vec3 own = pow(clamp(g * rta_light_ambient.rgb, vec3(0.0), vec3(1.0)), vec3(2.2));
		vec3 matched = own * shape * occ * cav + (refl * 0.8 + rim_light * 0.6) * lgl;
		EMISSION = mix(EMISSION, matched * (1.0 - h) + haze * h, game_match);
		ALBEDO = mix(ALBEDO, pow(g, vec3(2.2)) * shape * occ * cav * (1.0 - h), game_match) * mix(1.0, scene_keep, game_match);
		// (the game's own figure has its metal's colour in its diffuse: a scene light's diffuse is kept on metal, its
		// highlight takes the metal's colour all the same: v_metal)
		METALLIC = metal * mix(1.0, 0.35, game_match);
	}
	if (debug_view == 1) { EMISSION = has_game ? lg * 0.5 : vec3(1.0, 0.0, 1.0); ALBEDO = vec3(0.0); }
	if (debug_view == 2) { EMISSION = n_world * 0.5 + 0.5; ALBEDO = vec3(0.0); }
	if (debug_view == 3) { EMISSION = vec3(skin, hair + fur, metal); ALBEDO = vec3(0.0); }
}

void light() {
	float facing = dot(NORMAL, LIGHT);
	float wrap = LIGHT_IS_DIRECTIONAL ? mix(clamp(facing * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap) * clamp(facing * 0.5 + 0.75, 0.0, 1.0)
		: clamp(facing * 0.6 + 0.4, 0.0, 1.0);
	vec3 diff = vec3(wrap);
	// skin: a soft warm band where the light turns to shadow, the lit side a little less red (what scattered went there)
	float band = smoothstep(-0.45, 0.05, facing) * (1.0 - smoothstep(0.05, 0.6, facing));
	diff = mix(diff, wrap * vec3(0.97, 0.93, 0.9) + vec3(0.2, 0.06, 0.03) * band * sss, v_skin);
	DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * diff;
	vec3 hv = normalize(VIEW + LIGHT);
	float strands = clamp(v_hair + v_fur, 0.0, 1.0);
	vec3 spec = vec3(0.0);
	if (facing > 0.0) {
		float nh = max(dot(NORMAL, hv), 0.0);
		float vh = clamp(dot(VIEW, hv), 0.0, 1.0);
		vec3 f0 = mix(vec3(0.04), v_base, v_metal);
		vec3 f = f0 + (vec3(1.0) - f0) * pow(1.0 - vh, 5.0);
		// a metal catches the light: its highlight is the whole of its light; skin's broad and weak
		spec = f * min(ggx(nh, ROUGHNESS), 40.0) * facing * mix(0.28, 0.9, METALLIC) * mix(1.0, 0.6, v_skin);
	}
	if (strands > 0.01) {
		vec3 t = normalize(v_strand - NORMAL * dot(NORMAL, v_strand));
		float hairy = v_hair / max(v_hair + v_fur, 0.001);
		float lit = smoothstep(-0.15, 0.35, facing);
		float s1 = strand_spec(normalize(t + NORMAL * 0.1), hv, mix(14.0, 80.0, hairy));
		float s2 = strand_spec(normalize(t - NORMAL * 0.15), hv, mix(5.0, 20.0, hairy));
		vec3 kk = (vec3(s1) * mix(0.12, 0.3, hairy) + s2 * 0.25 * v_base) * lit * sheen_amount;
		spec = mix(spec, kk, strands);
	}
	SPECULAR_LIGHT += ATTENUATION * LIGHT_COLOR * spec * spec_amount;
}
