// skeleton_export.h - the skeletons of a frame for the host (rtag_skeletons of rtag.h).
//
// Where the numbers come from (docs/spec/animation.md, docs/spec/render-pipeline.md 4.7):
//
//   - The game's own animation code builds a pose per animated object into a pose buffer (anim_buildPose 0x16ed40:
//     the clip's tracks blended, composed down the hierarchy by the VU0 program; 0x620 bytes, 64 joints of three s16
//     rows: rotation x 4096, translation x 64).  For drawing, anim_emitPose 0x16f880 stamps the buffer and the draw
//     list sends it to VU1 straight from that buffer (a REF tag whose data is the buffer: an UNPACK, then MSCAL 0x3a).
//     Each joint's matrix takes BIND-POSE model-space points to posed model space.
//   - On the game's thread, when a draw pass has returned (scene_export.cpp's drawn()), the pose buffers stamped with
//     this pass's g_drawFrame (0x44fdd0) are the poses it drew.  Each is recorded - its matrices, its owner (the
//     animation state, +0x610), the owner's top track's clip and that clip's skeleton: depth list (+0x10) and bind
//     offsets (+0x0c) - as one batch under a number, and the number travels with the camera block in the VIF stream
//     (render::TapFrame::batch).  (In the front end the pose reaches VU1 by a REF tag to the buffer; in a level it does
//     not pass the DMA hook that way: found 2026-10-22.  The stamp holds in both.)
//   - On the decoder's thread the scene tap has, per skinned object, the 64 joint matrices the program made (pose x the
//     object's transform: object -> clip) and the packets drawn with them; the packets' sources are the bind-pose
//     vertices with their joints and weights.  Here the joint matrices are taken back through the inverse of the
//     view-projection into the world (skin), and the object is tied to the pose of its batch that is these matrices
//     through one object matrix (pose_error: how far, in world units; 0.05 at most).
//
// Nothing here changes what the game computes: it only reads memory.
#pragma once
#include "rtag.h"

#include <cstdint>
#include <vector>

namespace render { struct TapFrame; }

namespace skel {

struct Frame {
    std::vector<rtag_skeleton> skeletons;
    std::vector<rtag_skin_piece> pieces;        // parallel to scene::Frame::pieces
    std::vector<rtag_skin_source> sources;
    std::vector<uint16_t> full_source;
    std::vector<rtag_skeleton_player> players;  // the game's players at the pass (their animation states tie them to poses)
    uint32_t poses_seen = 0, poses_matched = 0;
    void clear() { skeletons.clear(); pieces.clear(); sources.clear(); full_source.clear(); players.clear(); poses_seen = poses_matched = 0; }
};

void install();                                 // before the game starts
// The game's thread, when a draw pass has returned: the poses it drew, kept under a number (returned; 0 none) that goes
// to the decoder with the camera block (render::TapFrame::batch).
uint32_t drawn(const uint8_t* ram);
// The decoder's thread: from the tap's frame, for the pieces scene::take handed on (`kept`: per tap piece, 1 when it
// is in scene::Frame::pieces, in order).
void build(const render::TapFrame& tap, const std::vector<uint8_t>& kept, Frame& out);
void fill(const Frame& frame, rtag_skeletons& out);
void report();

}  // namespace skel
