// fill.gdshaderinc - the body of fill.gdshader (ceilings) and fill_skirt.gdshader (skirts): the two differ only in their
// render_mode (a skirt writes no depth: docs/issues/native-godot.md, "Ceilings and skirts").  See fill.gdshader.

#include "res://shaders/atmosphere.gdshaderinc"

uniform int kind = 1;                   // 1 ceiling, 2 skirt, 3 rim (under a floor's edge over nothing; drawn as a skirt)
uniform int has_swatch = 0;
uniform sampler2D swatch : filter_linear_mipmap, repeat_enable;
uniform float gain = 1.0;               // the swatch to the mean brightness of the level's swatches
uniform float darken = 0.42;            // how much of that a ceiling keeps
uniform float scale = 1.0;              // swatch repeats per 64 units (rta_fill.cpp: the wall's own texel density)

varying vec3 v_world;
varying vec3 v_normal;
varying vec4 v_fill;

void vertex() {
	v_world = VERTEX;
	v_normal = CUSTOM1.xyz;
	NORMAL = CUSTOM1.xyz;
	v_fill = CUSTOM0;
}

vec3 to_linear(vec3 c) {
#if CURRENT_RENDERER != RENDERER_COMPATIBILITY
	// Forward+ / Mobile: ALBEDO is linear light and the picture is stored with the exact sRGB curve - the inverse is exact
	return pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
#endif
	// gs_draw.gdshaderinc: the colour whose round trip through the renderer's sRGB approximation is c
	vec3 l = pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
	vec3 x = c;
	for (int k = 0; k < 3; k++) {
		vec3 f = x * (x * (x * 0.305306011 + 0.682171111) + 0.012522878) - l;
		vec3 slope = x * (x * 0.915918033 + 1.364342222) + 0.012522878;
		x = clamp(x - f / slope, 0.0, 1.0);
	}
	return mix(x, vec3(0.0), lessThan(c, vec3(0.002)));
}

float value_noise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(rta_hash(i), rta_hash(i + vec2(1.0, 0.0)), u.x), mix(rta_hash(i + vec2(0.0, 1.0)), rta_hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void fragment() {
	vec3 to_surface = v_world - CAMERA_POSITION_WORLD;
	float dist = length(to_surface);
	// a ceiling is seen from below only (render/gs.cpp, Gs::draw_fill): a camera above it looks through
	if (kind == 1 && dot(to_surface, v_normal) >= 0.0) discard;
	vec3 base;
	vec2 tile = v_fill.xy * scale;
	if (has_swatch != 0) {
		// mirrored, so that it has no seam where it repeats; and a second sampling turned and scaled over it, so that the
		// repeats of a small patch do not stand in rows (the texture's bytes are the game's stored values)
		vec2 m = abs(fract(tile * 0.5) * 2.0 - 1.0);
		vec2 turned = mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8)) * tile * 0.61 + vec2(0.37, 0.71);
		vec2 m2 = abs(fract(turned * 0.5) * 2.0 - 1.0);
		base = mix(texture(swatch, m).rgb, texture(swatch, m2).rgb, 0.45) * gain;
	} else {
		float n = value_noise(tile * 3.0) * 0.6 + value_noise(tile * 9.0) * 0.4;
		base = vec3(0.30, 0.27, 0.24) * (0.75 + 0.5 * n);
	}
	vec3 rgb;
	float alpha = 1.0;
	if (kind == 1) {
		// how far the wall is: grey 1 at it, 150/255 at 200 units
		float wall = clamp((1.0 - v_fill.z) / (105.0 / 255.0), 0.0, 1.0) * 200.0;
		float crease = mix(0.40, 1.0, smoothstep(0.0, 34.0, wall));
		float hall = mix(1.0, 0.70, smoothstep(30.0, 200.0, wall));
		float grey = dot(base, vec3(0.30, 0.59, 0.11));
		rgb = mix(vec3(grey), base, 0.72) * darken * crease * hall;      // in shadow: a little less colour
	} else {
		alpha = clamp(v_fill.w, 0.0, 1.0);
		rgb = base;
		if (kind == 3) rgb *= v_fill.z * 0.9;          // a rim: the underside of the ground, darker away from the edge (grey 150 .. 90)
	}
	// the haze, as for the level's own draws - a ceiling a little less: it is seen at a slant, above what lies at that distance
	float f = rta_haze(kind == 1 ? dist * 0.72 : dist, v_world.z);
	vec3 haze = rta_haze_colour(to_surface / max(dist, 0.001)) * f;
	rgb *= 1.0 - f;
	NORMAL = normalize(FRONT_FACING ? NORMAL : -NORMAL);
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	vec3 own = kind == 1 ? rgb : rgb * rta_light_ambient.rgb;  // a ceiling keeps its own (dark) colour; a skirt is lit as the ground
	ALBEDO = to_linear(clamp(rgb, 0.0, 1.0)) * alpha;
	EMISSION = to_linear(clamp(own + haze, 0.0, 1.0)) * alpha;
	ALPHA = alpha;
}

void light() {
	// the sun does not reach a ceiling (it is not on the sun's layer either); a point light by distance and facing
	if (LIGHT_IS_DIRECTIONAL) {
		if (kind != 1) DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * mix(clamp(dot(NORMAL, LIGHT) * 0.5 + 0.5, 0.0, 1.0), 1.0, 0.72);
	} else {
		DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * clamp(dot(NORMAL, LIGHT) * 0.6 + 0.4, 0.0, 1.0);
	}
}
