// gs.h - the Graphics Synthesizer as this game uses it, modelled at the level of what a
// draw means, not of video memory.
//
// Input: GIF packets on the three paths (VU1's XGKICK, VIF1 DIRECT, the GIF channel) and
// the privileged registers.  Output: a FrameList (backend.h).
//
//  - A surface the game draws into is a render target, known by its base pointer.  Its
//    size is what the scissor says; a surface as large as the picture is drawn at the
//    output resolution, so the 3-D scene never exists at 1280 x 448.
//  - A texture is what the game sent: the rectangles transferred to an address, in the
//    format they were sent in, read back in the format the draw names.  It is known by a
//    hash of those bytes, so the 340 textures the game sends again every frame cost a hash
//    and nothing else.  Its size is the part that was sent, not the 1024 x 1024 that TEX0
//    names for interface art.  No video memory is kept between textures: a rectangle that
//    was never sent reads as zero, never as what lay there before.
//  - The half-line interlace offset in XYOFFSET is dropped, and interface art stored as
//    two stacked field pictures is sampled as the woven picture (DrawCmd::weave_half).
//  - A sprite's texture coordinates are moved back by half a pixel: the GS samples at a
//    pixel's corner, the graphics APIs at its centre.
#pragma once
#include "backend.h"
#include "layout.h"

#include <cstdint>
#include <functional>
#include <map>
#include <set>
#include <unordered_map>
#include <vector>

namespace render {

struct GsStats {
    uint64_t packets = 0, reg_writes = 0, prims = 0, vertices = 0, uploads = 0, upload_bytes = 0;
    uint64_t textures_made = 0, texture_hits = 0, texture_missing = 0, commands = 0, finish = 0;
    uint64_t copies = 0, unknown_regs = 0;
    double kick_ms = 0, path3_ms = 0;   // processor time inside xgkick() and gif(2, ...), when Gs::time_paths is set
    uint64_t textures_freed = 0, textures_held = 0, texture_bytes = 0;      // held: now; bytes: RGBA bytes of the held ones
    uint64_t copies_skipped = 0;        // local-to-local transfers that were not a copy from a surface
    uint64_t surface_uploads = 0;       // rectangles sent straight into a displayed buffer
    uint64_t fogged = 0;                // primitives drawn with fogging
    uint64_t targets_held = 0, targets_freed = 0;
    // Primitives drawn with a piece of GS state this model does not apply or only
    // approximates, by kind (Gs::APPROX_NAMES): what a scene needs is known by counting.
    uint64_t approx[16] = {0};
};
enum { AP_AFAIL, AP_DATE, AP_DST_ALPHA, AP_FBA, AP_PABE, AP_FOG_UNUSED, AP_AA1, AP_FBMSK, AP_COLCLAMP, AP_REGION_REPEAT, AP_SELF_TEXTURE, AP_COUNT };

class Gs {
  public:
    Gs();
    FrameList frame;                    // being built
    GsStats stats;
    bool weave = true;                  // sample two-field interface art as one picture
    bool name_textures = false;         // work out the emulator-based build's name of every texture made (TextureData::named)
    bool no_interlace = true;           // drop the half-line of XYOFFSET
    int trace = 0;                      // > 0: print draws to stderr
    bool time_paths = false;
    std::function<void()> on_far_vertex;    // debugging (RTA_GS_FAR): a vertex far outside every surface was drawn
    bool log_display = false;           // print display register changes and surface sizes to stderr
    int debug_entry = 0;                // the VU1 entry last started (for the trace)
    static const char* const APPROX_NAMES[AP_COUNT];
    // A texture nothing drew with for this many frames is freed (0: never).  It is made
    // again from what the game sends if a draw names it later.
    uint32_t texture_keep_frames = 600;
    uint64_t texture_budget = 96u << 20;    // bytes of RGBA held before idle textures go early
    // Asked once per new texture: the size of the picture in the texture at this TBP0, from
    // the game's own header (false: not known).
    std::function<bool(uint32_t tbp, int& width, int& height)> picture_size;
    // Asked once per address when a draw names a texture nothing was sent for: send it
    // (through gif(3, ...)) if the machine still has it.
    std::function<bool(uint32_t tbp)> restore_texture;

    // GIF data, whole quadwords.  path 0 = XGKICK (from VU1 memory), 1 = DIRECT, 2 = GIF channel,
    // 3 = the renderer itself (restore_texture)
    void gif(int path, const uint32_t* words, size_t quadwords);
    void xgkick(const uint8_t* vu_data, uint32_t qword);
    void privileged(uint32_t address, uint64_t value);
    // A note from the game side, carried in the VIF1 stream as a NOP code with 0xA5..0xA7 in
    // its NUM field (tools/recomp/app/gfx_rt.cpp): 0xA5 who made the packets that follow (a
    // mark for the layout of the 2-D layer), 0xA6 and 0xA7 the halves of the widescreen factor.
    void note(uint32_t kind, uint32_t value);
    Layout layout;                      // the 2-D layer of a wide picture
    // Close the frame being built: names what the display shows.  The caller takes `frame`
    // and calls begin_frame() before feeding more.
    void end_frame(uint64_t number);
    void begin_frame();

  private:
    // ---- registers ----
    uint64_t reg[0x64];
    uint64_t pmode = 0, smode2 = 0, dispfb[2] = {0, 0}, display[2] = {0, 0};
    struct Queued { uint32_t x, y, z; float s, t, q; uint32_t u, v; uint8_t rgba[4]; uint8_t fog; };
    uint8_t cur_fog = 0;                // the FOG register's coefficient (for vertices that carry none)
    Queued vq[3];
    int vcount = 0;
    float cur_s = 0, cur_t = 0, cur_q = 1, st_q = 1;
    uint32_t cur_u = 0, cur_v = 0;
    uint8_t cur_rgba[4] = {0, 0, 0, 0x80};
    uint32_t prim = 0;
    bool state_dirty = true;
    // ---- GIF tag state per path ----
    struct Path { uint64_t regs = 0; uint32_t nloop = 0, nreg = 0, flg = 0, at = 0; bool eop = false; };
    Path paths[4];
    void xgkick_draw(const uint32_t* buffer, uint32_t used, uint32_t qword);
    void write(uint32_t address, uint64_t value);
    void packed(uint32_t descriptor, const uint32_t* q);
    void reglist(uint32_t descriptor, uint64_t value);
    void kick(bool draw);
    // A whole PACKED run of triangles, strips or fans (what VU1 kicks is nearly all of
    // this kind): the same registers, queue and vertices as packed() and kick() make of
    // it one quadword at a time.  False: not a run it takes; nothing was done.
    bool triangle_run(const uint32_t* data, uint32_t nloop, uint32_t nreg, uint64_t regs);
    std::vector<Vertex> run_vertices;   // where a run puts its vertices before they are added to the list
  public:
    bool fast_runs = true;              // false: every quadword through packed() (the reference; RTA_GS_SLOW)
    bool copy_kicks = false;            // true: a kicked packet is copied out of VU1 memory first (the reference; RTA_GS_SLOW)
  private:
    // ---- drawing ----
    DrawCmd cur;                        // state of the command being filled
    bool have_cmd = false;
    void rebuild_state();
    void emit_vertex(const Queued& v, const DrawCmd& c, float s, float t, float q, const uint8_t* rgba, uint32_t z, uint8_t fog = 255);
    float ofx = 0, ofy = 0, zscale = 1.0f / 65536.0f;
    bool cmd_fst = true, cmd_iip = true, cmd_tme = false;
    int cur_path = 1;                   // the path whose data is being read
    uint32_t prim_serial = 0;           // counts writes of PRIM (one strip, fan or run of sprites)
    uint32_t note_high = 0;
    bool cur_wide = false;              // the state draws into the 1280-wide 3-D buffer
    // Whether what a display buffer holds came from the 3-D buffer (the present pass) or
    // was put there directly (pixels sent or drawn straight into it): the picture has the
    // view's shape in the first case and is 4:3 in the second, whatever the view is.
    std::map<uint32_t, bool> from_view;
    // ---- render targets ----
    struct Target { uint32_t id = 0; int width = 0, height = 0; uint64_t serial = 0; bool announced = false; uint32_t fbw = 0, psm = 0; uint64_t last_used = 0; };
    void free_unused_targets();
    std::map<uint32_t, Target> targets;                 // by FBP
    std::map<uint32_t, uint64_t> display_fbps[2];       // buffers DISPFB1/2 have named, and at which frame last
    uint64_t frames_ended = 0;
    unsigned circuits_on = 0;                           // PMODE.EN1/EN2 as ever set
    bool display_size(uint32_t fbp, int& width, int& height) const;
    uint32_t next_target = 1;
    Target& target_at(uint32_t fbp, int width, int height);
    // ---- transfers and textures ----
    struct Rect { uint32_t psm, bw; int x, y, w, h; size_t offset, bytes; uint32_t bw_raw; };
    struct UploadSet { std::vector<Rect> rects; std::vector<uint8_t> data; uint64_t hash = 0, serial = 0; bool used = false; };
    std::map<uint32_t, UploadSet> sets;                 // by destination base pointer
    uint8_t set_at[0x4000] = {0};                       // 1 where `sets` has an entry (start_transfer asks it block by block)
    std::map<std::pair<uint64_t, uint64_t>, std::vector<uint32_t>> written_blocks;     // start_transfer: the blocks a kind of rectangle writes, sorted
    uint64_t serial = 1;
    struct Transfer { bool active = false; uint32_t dbp = 0; size_t rect = 0, got = 0; bool to_surface = false; } xfer;
    // Pixels the game sends straight into a displayed buffer (the film player: 16 x 16
    // pieces of a decoded picture, 1,120 a picture): collected per buffer and drawn into
    // the surface as one picture when the frame ends or something else uses the surface.
    struct Canvas { int width = 0, height = 0, x0 = 0, y0 = 0, x1 = 0, y1 = 0; std::vector<uint32_t> pixels; };
    std::map<uint32_t, Canvas> canvases;                // by block
    std::vector<uint32_t> transient_textures;           // made for one frame's uploads: freed with the next frame
    void upload_to_surface(uint32_t block, const Rect& r, const uint8_t* bytes);
    void flush_uploads();
    void start_transfer();
    void image_data(const uint8_t* bytes, size_t count);
    struct Texture { uint32_t id; int width, height, picture_height; bool height_known; uint64_t last_used = 0; };
    void free_unused_textures();
    uint32_t cur_approx = 0;            // AP_ bits of the state being drawn with
    std::set<uint32_t> restore_tried;
    int cur_picture_height = 0;
    std::unordered_map<uint64_t, Texture> textures;     // by content key
    uint32_t next_texture = 1;
    Texture* texture_for(uint64_t tex0, uint64_t texa);
    void name_texture(TextureData& out, const UploadSet& set, const uint32_t* palette, int entries, uint32_t psm, uint32_t tbw_raw, uint32_t cpsm,
                      int named_w, int named_h);
    bool palette_of(const UploadSet& set, uint32_t cpsm, uint32_t* out, int entries);
};

}  // namespace render
