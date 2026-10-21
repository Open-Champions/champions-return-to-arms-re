shader_type spatial;
// fill_skirt.gdshader - the skirts of fill.gdshader (kind 2), drawn as a background: as the OpenGL program does since
// docs/issues/native-first-person-world.md 8.8 (cause 3), a skirt writes no depth.  It is drawn before the first piece of the
// level (rta_fill.cpp, "order"), so whatever of the level lies behind it - the lava sea below the cliffs of firbonus, which
// the terrain the skirt is made from does not have - is drawn over it afterwards; it is seen only where nothing of the
// level is drawn, as if it lay at the farthest depth.
render_mode blend_premul_alpha, depth_draw_never, cull_disabled, specular_disabled, fog_disabled, ambient_light_disabled;

#include "res://shaders/fill.gdshaderinc"
