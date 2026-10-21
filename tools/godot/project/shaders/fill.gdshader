shader_type spatial;
// fill.gdshader - the ceilings and skirts the library generates for a level (tools/recomp/render/worldfill.h), as
// RtaDrawer draws them in scene mode (extension/src/rta_fill.cpp says where everything comes from).
//
// A vertex brings: its world position (the mesh is in the world's axes, z up), its normal (CUSTOM1: a ceiling's looks
// down, a skirt's up), and CUSTOM0 = (world x / 64, world y / 64, grey, alpha): grey is 1 at a wall and 150/255 at 200
// units from it (ceilings), alpha 1 at the rim and 0 at the skirt's outer edge.
//
// The colour is a SWATCH of the level's own texture (cut where a wall meets the ceiling, or from the lid at the rim),
// tiled mirrored so that it has no seams, brought to one brightness (`gain`) and darkened (`darken`); a ceiling gets a
// crease where it meets the wall and is darker toward the middle of a hall.  As in gs_draw.gdshaderinc's GS_LIT: what
// arrives without a light is put in as the surface's own light (EMISSION), the lights add to it (light()), colours are
// stored values (to_linear), and the haze of atmosphere.gdshaderinc lies over it.
render_mode blend_premul_alpha, depth_draw_always, cull_disabled, specular_disabled, fog_disabled, ambient_light_disabled;

#include "res://shaders/fill.gdshaderinc"
