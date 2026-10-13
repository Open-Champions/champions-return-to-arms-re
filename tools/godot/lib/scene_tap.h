// scene_tap.h - the 3-D scene before the game's projection (rtag_scene of rtag.h).
// scene_tap.cpp says how; this is what rtag.cpp needs of it.
#pragma once
#include "rtag.h"
#include "renderer.h"

#include <cstdint>
#include <vector>

namespace scene {

// What one frame's tap gives: a world position for every vertex of the draw list that the
// main vertex programs made (parallel to FrameList::vertices; `known` says which).
struct Frame {
    std::vector<rtag_scene_vertex> vertices;    // one per vertex of the list, or empty
    std::vector<uint8_t> known;                 // 1 where the entry above is a world position
    bool valid = false;
    float world_to_view[16], view_to_clip[16], world_to_screen[16], camera_position[3];
    float fov_y = 0, near_plane = 0, far_plane = 0;
    void clear() { vertices.clear(); known.clear(); valid = false; }
};

void install(render::Renderer& renderer);               // before the game starts
void at_blank(const uint8_t* ram, uint64_t number);     // the game's thread, at a vertical blank: the camera of the frame just built
void take(render::FrameList& list, Frame& out);         // the decoder's thread, when a list is closed
void fill(const Frame& frame, rtag_scene& view, rtag_draw* draws, size_t count);   // the host's thread
void report();

}  // namespace scene
