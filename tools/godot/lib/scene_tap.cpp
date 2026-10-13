// scene_tap.cpp - see scene_tap.h.  (Stage 4 of docs/issues/native-godot.md; until it is
// written the tap gives nothing.)
#include "scene_tap.h"

#include <cstring>

namespace scene {

void install(render::Renderer&) {}
void at_blank(const uint8_t*, uint64_t) {}
void take(render::FrameList&, Frame& out) { out.clear(); }
void fill(const Frame&, rtag_scene& view, rtag_draw*, size_t) { memset(&view, 0, sizeof view); }
void report() {}

}  // namespace scene
