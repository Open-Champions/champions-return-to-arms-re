// gs_draw.gdshaderinc - one draw of the game's draw list, as a Godot spatial shader.
//
// The list (tools/godot/lib/rtag.h, rtag_draw) is what the game's Graphics Synthesizer was
// asked to draw: triangles already projected to the screen, with a texture, a texture
// function, an alpha test, a depth test and a blend equation per draw.  RtaDrawer
// (tools/godot/extension/src/rta_drawer.cpp) makes one mesh instance per draw and one
// material per distinct state; this file is the shader of all of them.  The variants are
// chosen by defines the drawer puts in front of it:
//   GS_BLEND_SUB        destination minus source (else: source + destination x (1 - A))
//   GS_DEPTH_ALWAYS     no depth test          GS_DEPTH_INVERTED   passes where the default test fails
//   GS_DEPTH_WRITE      writes depth
//   GS_LINEAR           the texture is filtered    GS_REPEAT   it repeats on both axes
//   GS_WORLD            scene mode: the vertex is a world position under Godot's camera (see below)
//   GS_LIT              ... and Godot's sun and lamps decide how much of the game's colour arrives (below)
//   GS_NORMALS          ... the mesh has the game's own normals      GS_CASTER   a twin that only throws a shadow
//   GS_NOFOG            ... the haze of atmosphere.gdshaderinc leaves it alone (the game's sky dome)
//
// Colours are carried in the GS's units as in tools/recomp/render/backend_gl.cpp, whose
// fragment shader this follows line for line: 0..255, with 128 = 1.0 for alpha and for the
// colour a texture is multiplied by.
// ("shader_type spatial;" is put in front, before the defines, by the drawer.)

#ifdef GS_CASTER
// a twin of an opaque draw of the scene that only goes into Godot's shadow maps
render_mode unshaded, cull_disabled;
#else
#ifdef GS_BLEND_SUB
render_mode blend_sub;
#else
render_mode blend_premul_alpha;
#endif
#ifdef GS_DEPTH_ALWAYS
render_mode depth_test_disabled;
#endif
#ifdef GS_DEPTH_INVERTED
render_mode depth_test_inverted;
#endif
#ifdef GS_DEPTH_WRITE
render_mode depth_draw_always;
#else
render_mode depth_draw_never;
#endif
#ifdef GS_WORLD
#ifdef GS_LIT
render_mode cull_disabled, specular_disabled, fog_disabled, ambient_light_disabled;
#else
render_mode unshaded, cull_disabled, shadows_disabled, fog_disabled;
#endif
#else
render_mode unshaded, cull_disabled, skip_vertex_transform, shadows_disabled, fog_disabled;
#endif
#endif

#ifdef GS_LINEAR
#ifdef GS_REPEAT
uniform sampler2D tex : filter_linear, repeat_enable;
#else
uniform sampler2D tex : filter_linear, repeat_disable;
#endif
#else
#ifdef GS_REPEAT
uniform sampler2D tex : filter_nearest, repeat_enable;
#else
uniform sampler2D tex : filter_nearest, repeat_disable;
#endif
#endif

uniform vec2 target_size = vec2(1280.0, 448.0);    // the surface's logical size: vertex positions are in these pixels
uniform vec2 target_scale = vec2(1.0, 1.0);        // real pixels per logical pixel
uniform float flip_y = 1.0;                         // -1: turn the surface over
uniform vec4 scissor = vec4(0.0, 0.0, 65536.0, 65536.0);   // x0, y0, x1, y1 in real pixels, x1/y1 exclusive
uniform int textured = 0;
uniform int tfx = 0;
uniform int tcc = 0;
uniform vec2 st_scale = vec2(1.0, 1.0);
uniform vec2 tex_size = vec2(1.0, 1.0);
uniform vec2 tex_offset = vec2(0.0, 0.0);
uniform float tex_flip = 0.0;                       // 1: the texture is a surface stored bottom up
uniform ivec2 wrap_mode = ivec2(0, 0);
uniform vec4 region = vec4(0.0);
uniform float weave_half = 0.0;
uniform vec4 texa = vec4(0.0);                      // mode (0 none, 1 24 bit, 2 16 bit), ta0, ta1, aem
uniform vec4 fog_colour = vec4(0.0);                // 0..255, on
uniform int atst = 1;
uniform float aref = 0.0;
uniform vec4 blend = vec4(0.0, 1.0, 0.0, 0.0);      // source: coefficient of C, constant; destination: the same
uniform int blend_c = 2;                            // 0 source alpha, 1 destination alpha (taken as 1), 2 fix
uniform float fix = 1.0;
uniform float mask_rgb = 0.0;                       // 1: the colour is not written
#ifdef GS_WORLD
uniform float depth_bias = 0.0;                     // toward the camera, in clip space: what lies on a surface is drawn on it
#ifndef GS_CASTER
#include "res://shaders/atmosphere.gdshaderinc"
varying vec3 v_world;
varying float v_haze;                               // 0: the surface as it is .. 1: lost in the haze
#endif
#endif

varying vec3 v_st;
varying float v_fog;
varying vec2 v_pos;
varying vec4 v_col;

void vertex() {
	v_st = CUSTOM0.xyz;
	v_fog = CUSTOM0.w;
	v_col = COLOR * 255.0;
#ifdef GS_WORLD
	// VERTEX is where the vertex was in the world before the game projected it
	// (tools/godot/lib/scene_tap.cpp).  The camera is Godot's: while it follows the game's,
	// MODELVIEW and PROJECTION do here what the vertex program did there; moved, they show
	// the same scene from somewhere else.
	// Texture coordinates: the list's are (S, T, Q) to be divided per pixel after a straight
	// interpolation across the screen.  Here the rasteriser interpolates with the perspective
	// of Godot's camera, so the division is done at the vertex and the texel position itself is
	// interpolated - right from any camera.  (What the game sends with Q = 1, nearly all of the
	// scene, it maps without perspective; this maps it with: a difference of a texel or two on
	// large triangles seen at a slant.)
	if (abs(CUSTOM0.z) > 1e-12) v_st = vec3(CUSTOM0.xy / CUSTOM0.z, 1.0);
#ifdef GS_NORMALS
	NORMAL = CUSTOM1.xyz;                               // the game's own normal (the mesh is in world space)
#endif
	v_pos = vec2(0.0);
#ifndef GS_CASTER
	v_world = VERTEX;
#endif
	POSITION = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0));
	POSITION.z += depth_bias * POSITION.w;
#else
	v_pos = VERTEX.xy;
	POSITION = vec4(VERTEX.x / target_size.x * 2.0 - 1.0, (VERTEX.y / target_size.y * 2.0 - 1.0) * flip_y, VERTEX.z * 2.0 - 1.0, 1.0);
#endif
}

float gs_wrap(float c, int mode, float lo, float hi, float size) {
	if (mode == 2) return clamp(c, lo, hi + 0.999);
	if (mode == 3) return float((int(floor(c)) & int(lo)) | int(hi)) + fract(c);
#ifndef GS_REPEAT
	if (mode == 0) return c - floor(c / size) * size;      // repeats on this axis only
#endif
	return c;
}

vec3 to_linear(vec3 c) {
#ifdef GS_STORED_COLOURS
	// The Compatibility renderer takes ALBEDO for an sRGB colour: it converts it to linear
	// light, and back when it writes the pixel - each way with a fast approximation
	// (x(x(0.3053x + 0.6822) + 0.0125), and 1.055 x^(1/2.4) - 0.055), so that the round trip
	// lowers dark values (10 of 255 comes back as 4).  The GS's colours are the stored ones
	// and have to arrive as they are: what goes in here is the colour whose round trip is c -
	// the second approximation inverted exactly, the first by three steps of Newton's method.
	vec3 light = pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4));
	vec3 x = c;
	for (int k = 0; k < 3; k++) {
		vec3 f = x * (x * (x * 0.305306011 + 0.682171111) + 0.012522878) - light;
		vec3 slope = x * (x * 0.915918033 + 1.364342222) + 0.012522878;
		x = clamp(x - f / slope, 0.0, 1.0);
	}
	return mix(x, vec3(0.0), lessThan(c, vec3(0.002)));
#else
	return c;
#endif
}

void fragment() {
#ifndef GS_WORLD
	vec2 px = v_pos * target_scale;
	if (px.x < scissor.x || px.x >= scissor.z || px.y < scissor.y || px.y >= scissor.w) discard;
#endif
	vec4 c = v_col;
	if (textured != 0) {
		vec2 tc = v_st.xy / v_st.z * st_scale;
		if (weave_half > 0.0) {
			float line = floor(tc.y);
			tc.y = floor(line * 0.5) + mod(line, 2.0) * weave_half + 0.5;
		}
		tc.x = gs_wrap(tc.x, wrap_mode.x, region.x, region.y, tex_size.x);
		tc.y = gs_wrap(tc.y, wrap_mode.y, region.z, region.w, tex_size.y);
		vec2 uv = (tc + tex_offset) / tex_size;
		if (tex_flip > 0.5) uv.y = 1.0 - uv.y;
		vec4 t = textureLod(tex, uv, 0.0) * 255.0;
		if (texa.x > 0.5) {
			bool black = texa.w > 0.5 && t.r + t.g + t.b < 0.5;
			t.a = (texa.x > 1.5 && t.a >= 127.5) ? texa.z : (black ? 0.0 : texa.y);
		}
		if (tfx == 0) {
			c.rgb = min(t.rgb * v_col.rgb / 128.0, 255.0);
			c.a = tcc != 0 ? min(t.a * v_col.a / 128.0, 255.0) : v_col.a;
		} else if (tfx == 1) {
			c.rgb = t.rgb;
			c.a = tcc != 0 ? t.a : v_col.a;
		} else {
			c.rgb = min(t.rgb * v_col.rgb / 128.0 + v_col.a, 255.0);
			c.a = tcc == 0 ? v_col.a : (tfx == 2 ? min(t.a + v_col.a, 255.0) : t.a);
		}
	}
	if (fog_colour.w > 0.5) c.rgb = c.rgb * v_fog + fog_colour.rgb * (1.0 - v_fog);
	if (atst != 1) {
		bool pass = true;
		float a = floor(c.a + 0.01);
		if (atst == 0) pass = false;
		else if (atst == 2) pass = a < aref;
		else if (atst == 3) pass = a <= aref;
		else if (atst == 4) pass = a == aref;
		else if (atst == 5) pass = a >= aref;
		else if (atst == 6) pass = a > aref;
		else pass = a != aref;
		if (!pass) discard;
	}
#ifdef GS_CASTER
	ALBEDO = vec3(0.0);
#else
	// blend: colour = source x |sc x F + sk|  (+ or -)  destination x |dc x F + dk|
	float factor = blend_c == 0 ? c.a / 128.0 : (blend_c == 1 ? 1.0 : fix);
	float source = abs(blend.x * factor + blend.y);     // an alpha above 0x80 makes it more than 1: the product is what is clamped
	float destination = clamp(abs(blend.z * factor + blend.w), 0.0, 1.0);
	vec3 rgb = clamp(c.rgb / 255.0 * source, 0.0, 1.0);
	if (mask_rgb > 0.5) { rgb = vec3(0.0); destination = 1.0; }
	vec3 haze = vec3(0.0);
#ifdef GS_WORLD
	vec3 to_surface = v_world - CAMERA_POSITION_WORLD;
	float dist = length(to_surface);
#ifdef GS_NEARFADE
	// A sprite the game sized for a camera far overhead (a glow, a spark, a puff) is drawn as large on the screen
	// however near it is: one at the eye would cover the picture.  It thins out as it comes up to the eye.
	float keep = smoothstep(18.0, 75.0, dist);
	rgb *= keep;
	destination = mix(1.0, destination, keep);
#endif
#ifndef GS_NOFOG
	// The haze: what is drawn fades, and the haze's own colour comes in its place as far as this draw covers
	// what is behind it (an additive glow only fades; an opaque wall becomes haze).
	float f = rta_haze(dist, v_world.z);
	haze = rta_haze_colour(to_surface / max(dist, 0.001)) * f * (1.0 - destination);
	rgb *= 1.0 - f;
#endif
#endif
#ifdef GS_LIT
	// The colour the game drew - its texture times its own vertex light - is the surface's
	// colour here; Godot's ambient light and lights (light() below) say how much of it
	// arrives.  The normal is the triangle's own: the list carries none.
#ifdef GS_NORMALS
	// the game's, interpolated: smooth, per pixel.  The renderer turns the normal of a triangle seen from
	// behind; the game's triangles are wound either way (no program tests winding), so that is undone.
	NORMAL = normalize(FRONT_FACING ? NORMAL : -NORMAL);
#else
	vec3 flat_normal = normalize(cross(dFdy(VERTEX), dFdx(VERTEX)));
	NORMAL = dot(flat_normal, VIEW) < 0.0 ? -flat_normal : flat_normal;
#endif
	ROUGHNESS = 1.0;
	METALLIC = 0.0;
	// Without Godot's ambient light (ambient_light_disabled): what arrives where no light reaches is put in as the
	// surface's own light - the game's colour times rta_light_ambient, and the haze - so that it is exact in stored
	// values; the sun's pass then adds its share of ALBEDO (light() below).
	ALBEDO = to_linear(rgb);
	EMISSION = to_linear(clamp(rgb * rta_light_ambient.rgb + haze, 0.0, 1.0));
#else
	ALBEDO = to_linear(clamp(rgb + haze, 0.0, 1.0));
#endif
#ifdef GS_BLEND_SUB
	ALPHA = 1.0;                                        // destination - source
#else
	ALPHA = 1.0 - destination;                          // source + destination x (1 - alpha)
#endif
#endif
}

#ifdef GS_LIT
// A directional light gives its colour where its shadow map says the surface is lit - all
// of it where the mesh has no normals (the game's own shading is in the colour already),
// by the game's own normal where it has (sun_wrap):
// with an ambient energy of 1 - e and a sun of energy e the picture is the game's where
// the sun reaches, and darker by e in a shadow.  A point light is added on top, by distance
// and by the triangle's facing.
uniform float sun_wrap = 0.72;                      // how much of the sun a surface turned away from it still gets (1: all of it)
void light() {
	float facing = dot(NORMAL, LIGHT);
#ifdef GS_NORMALS
	if (LIGHT_IS_DIRECTIONAL) DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * mix(clamp(facing * 0.5 + 0.5, 0.0, 1.0), 1.0, sun_wrap);
	else DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * clamp(facing * 0.6 + 0.4, 0.0, 1.0);
#else
	if (LIGHT_IS_DIRECTIONAL) DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI;
	else DIFFUSE_LIGHT += ATTENUATION * LIGHT_COLOR / PI * (0.35 + 0.65 * max(facing, 0.0));
#endif
}
#endif
