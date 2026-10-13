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
//
// Colours are carried in the GS's units as in tools/recomp/render/backend_gl.cpp, whose
// fragment shader this follows line for line: 0..255, with 128 = 1.0 for alpha and for the
// colour a texture is multiplied by.
shader_type spatial;

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
render_mode cull_disabled, diffuse_lambert, specular_disabled, fog_disabled;
#else
render_mode unshaded, cull_disabled, shadows_disabled, fog_disabled;
#endif
#else
render_mode unshaded, cull_disabled, skip_vertex_transform, shadows_disabled, fog_disabled;
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
uniform float flip_y = 1.0;                         // -1: the surface is drawn bottom up
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
uniform float lit_amount = 0.0;                     // scene mode: how much of Godot's light the surface takes
uniform float depth_bias = 0.0;
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
	// VERTEX is the world position the game's own projection was applied to; Godot's camera
	// follows the game's, so MODELVIEW / PROJECTION do here what the vertex program did there.
	v_pos = vec2(0.0);
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
	// the renderer converts what a spatial shader gives it from linear light to sRGB before it
	// is written and blended; the GS's colours are the stored ones, so they go in inverted
	return mix(pow((c + vec3(0.055)) * (1.0 / 1.055), vec3(2.4)), c * (1.0 / 12.92), lessThan(c, vec3(0.04045)));
}

void fragment() {
#ifndef GS_WORLD
	vec2 px = v_pos * target_scale;
	if (px.x < scissor.x || px.x >= scissor.z || px.y < scissor.y || px.y >= scissor.w) discard;
#else
	vec2 px = FRAGCOORD.xy;
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
	// blend: colour = source x |sc x F + sk|  (+ or -)  destination x |dc x F + dk|
	float factor = blend_c == 0 ? c.a / 128.0 : (blend_c == 1 ? 1.0 : fix);
	float source = clamp(abs(blend.x * factor + blend.y), 0.0, 1.0);
	float destination = clamp(abs(blend.z * factor + blend.w), 0.0, 1.0);
	vec3 rgb = clamp(c.rgb / 255.0, 0.0, 1.0) * source;
	if (mask_rgb > 0.5) { rgb = vec3(0.0); destination = 1.0; }
#ifdef GS_BLEND_SUB
	// destination - source x alpha
	ALBEDO = to_linear(rgb);
	ALPHA = 1.0;
#else
	// source + destination x (1 - alpha)
#ifdef GS_LIT
	ALBEDO = to_linear(rgb);
#else
	ALBEDO = to_linear(rgb);
#endif
	ALPHA = 1.0 - destination;
#endif
}
