// scene_export.h - the 3-D scene for the host (rtag_scene of rtag.h).  scene_export.cpp says how;
// this is what rtag.cpp needs of it.
#pragma once
#include "rtag.h"
#include "renderer.h"
#include "skeleton_export.h"

#include <cstdint>
#include <vector>

namespace scene {

struct Frame {
    std::vector<rtag_scene_vertex> vertices;    // one per vertex of the list (meaningful for the draws `known` names)
    std::vector<float> normals;                 // three per vertex of the list; zero = none
    std::vector<uint8_t> known;                 // per draw: 0 not part of the scene, 1 put back by its depth, 2 from the programs' inputs
    std::vector<rtag_scene_piece> pieces;
    std::vector<rtag_scene_full> full;
    std::vector<uint32_t> piece_first, piece_count;     // per draw: its pieces
    skel::Frame skeletons;                      // the skeletons the pieces were posed with (skeleton_export.h)
    bool valid = false;
    float world_to_view[16], view_to_clip[16], world_to_screen[16], camera_position[3];
    float fov_y = 0, near_plane = 0, far_plane = 0;
    void clear() { vertices.clear(); normals.clear(); known.clear(); pieces.clear(); full.clear(); piece_first.clear(); piece_count.clear(); skeletons.clear(); valid = false; }
};

void install(render::Renderer& renderer);               // before the game starts: the tap (core/render/scene_tap.h)
void set_aspect(double aspect);                         // the shape of the 3-D view the game was asked for
// The game's thread, before a transfer to VIF1 is handed on: the camera block as VIF1 codes to send ahead of it
// (empty when there is nothing to say).
void before_transfer(const uint8_t* ram, std::vector<uint32_t>& codes);
void at_blank(const uint8_t* ram, uint64_t number);     // the game's thread, at a vertical blank
// The game's thread, when a draw pass has returned and its camera is still in place (fpview's call-out): the camera
// block is taken now - the game puts its own camera back right after - with the projection's near and far plane.
void drawn(const uint8_t* ram, float near_plane, float far_plane);
void take(render::FrameList& list, Frame& out);         // the decoder's thread, when a list is closed
void fill(const Frame& frame, rtag_scene& view, rtag_draw* draws, size_t count);   // the host's thread
void report();

}  // namespace scene
