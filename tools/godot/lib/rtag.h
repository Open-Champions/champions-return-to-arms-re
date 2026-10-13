/* rtag.h - the translated game as a library: a small C interface.
 *
 * The library (tools/godot/build.py lib) is the translated game, its runtime, the
 * renderer's processor side (VIF1, VU1, the GS model) and the sound core of
 * tools/recomp, with nothing of a window in it.  A host - a Godot extension, the test
 * program host_main.cpp, anything that can call C - starts the machine, lets it go one
 * vertical blank at a time or on its own clock, gives it the controllers, takes each
 * frame's draw list (or the picture the library's own OpenGL renderer drew off screen)
 * and asks for the sound.
 *
 * One machine per process: the translated game keeps its state in globals, so a second
 * rtag_start() after rtag_stop() is refused.  Every function may be called from any
 * thread, but frames are meant to be taken by one thread (pointers in an rtag_frame stay
 * valid until that thread takes the next one), and rtag_audio_pull() by one (the host's
 * sound thread).
 *
 * Nothing here is derived from the game; the library built from it is, and stays local.
 */
#ifndef RTAG_H
#define RTAG_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RTAG_API_VERSION 4

/* ---- start ------------------------------------------------------------------------- */
enum { RTAG_SOUND_NONE = 0, RTAG_SOUND_PULL = 1, RTAG_SOUND_MACHINE = 2 };

typedef struct rtag_config {
    uint32_t struct_size;       /* sizeof(rtag_config): a host built against an older header is refused */
    const char* disc;           /* your disc image of SLUS-20973 v2.00, read in place */
    const char* data_dir;       /* memory cards go to <data_dir>/card; made if missing */
    const char* workspace;      /* optional: the directory holding SLUS_209.73, names.tsv and symbols/ (names for scripts) */
    const char* elf;            /* optional: the executable; default <workspace>/SLUS_209.73, else copied out of the disc into data_dir */
    const char* script;         /* optional: a script in the rig's language (tools/rig); "app shot FILE.png" lines are honoured */
    /* the picture */
    int lists;                  /* 1: frames carry their draw list (vertices, draws, textures, targets) */
    int picture_width;          /* > 0: the library's own OpenGL renderer draws every list off screen at this size ... */
    int picture_height;
    int picture_every_frame;    /* ... and 1: every frame carries the picture as RGBA; 0: only "app shot" pictures are read back */
    int samples, anisotropy, mipmaps;   /* of that renderer: 0/2/4/8 samples per pixel, 1..16, 0/1 */
    double aspect;              /* shape of the 3-D view, width / height; 0 = 4:3 (the console's) */
    int scene3d;                /* 1: frames carry the 3-D scene before projection (rtag_scene; see rtag_frame) */
    /* sound, 48 kHz 16 bit stereo */
    int sound;                  /* RTAG_SOUND_NONE: the chip runs, nothing is kept;
                                   RTAG_SOUND_PULL: the sound side runs on the host's clock - whoever calls
                                       rtag_audio_pull() drives it, as the console's sound processor runs by itself;
                                   RTAG_SOUND_MACHINE: rendered on the machine's clock (the same run gives the same
                                       sound) into a ring rtag_audio_pull() reads */
    double gain;                /* 0..1 applied to what rtag_audio_pull() hands out */
    /* the machine */
    int emulator_timing;        /* 1: the I/O processor answers as slowly as a console's (default: fast loading) */
    int films;                  /* 1: the films play (when the library was built with the film decoder) */
    int argc;                   /* more arguments for the runtime, as after "--" of rta_app: [boot|resume] --opt k=v ... */
    const char* const* argv;
} rtag_config;

/* 0: started.  Negative: -1 bad argument, -2 no disc image, -3 no executable, -4 already started once. */
int rtag_start(const rtag_config* config);
int rtag_api_version(void);
/* 1 when the library holds the game with the fix set, 0 the game as it is on the disc; and the films, the 3-D scene tap. */
int rtag_has(const char* feature);      /* "fixes", "films", "picture", "scene3d", "network" */

/* ---- controllers -------------------------------------------------------------------- */
/* libpad's bits (1 = held): select 0x0001, L3 0x0002, R3 0x0004, start 0x0008, up 0x0010, right 0x0020,
 * down 0x0040, left 0x0080, L2 0x0100, R2 0x0200, L1 0x0400, R1 0x0800, triangle 0x1000, circle 0x2000,
 * cross 0x4000, square 0x8000.  Sticks 0..255, 128 at rest. */
typedef struct rtag_pad {
    uint16_t buttons;
    uint8_t lx, ly, rx, ry;
} rtag_pad;
void rtag_set_pad(int port, const rtag_pad* pad);       /* held until set again; read at the next vertical blank */

/* ---- a frame ------------------------------------------------------------------------ */
/* One vertex of the draw list: position in pixels of its target's logical size (1280 x 448 for the 3-D
 * surface), origin top left, z 0..1 with larger = nearer; texture coordinates (s, t, q): texel = (s/q, t/q)
 * x st_scale; colour and alpha as the GS has them (0x80 = 1.0); fog 255 = none. */
typedef struct rtag_vertex {
    float x, y, z;
    float s, t, q;
    uint8_t r, g, b, a;
    uint8_t fog, pad[3];
} rtag_vertex;

enum { RTAG_DRAW = 0, RTAG_COPY = 1 };
enum { RTAG_TRIANGLES = 0, RTAG_LINES = 1, RTAG_POINTS = 2 };
enum { RTAG_WRAP_REPEAT = 0, RTAG_WRAP_CLAMP = 1, RTAG_WRAP_REGION_CLAMP = 2, RTAG_WRAP_REGION_REPEAT = 3 };

/* One draw with its complete state: render::DrawCmd of tools/recomp/render/backend.h, field for field
 * (that header says what each means). */
typedef struct rtag_draw {
    uint8_t kind, prim;
    uint8_t made_by;            /* 0 kicked by VU1 (the 3-D scene), 1 built on the CPU, 2 sprites */
    uint8_t scissor_moved;
    uint32_t first, count;      /* vertices */
    uint32_t target;
    int32_t scissor[4];
    float scissor_x[2];
    uint32_t texture;           /* 0 = none */
    uint8_t tex_is_target, linear, wrap_s, wrap_t;
    float tex_size[2], tex_offset[2], st_scale[2], region[4];
    uint32_t tex_missing;
    uint8_t texa_mode, ta0, ta1, aem;
    uint8_t tfx, tcc;
    uint8_t alpha_test, atst, aref, afail;
    uint8_t depth_test, ztst, depth_write;
    uint8_t blend, ba, bb, bc, bd, fix;
    uint8_t mask_rgb, mask_a;
    uint8_t fog, fog_colour[3];
    float weave_half, weave_base;
    int32_t copy_src[4], copy_dst[4];
    /* with scene3d: the first vertex of this draw in the scene's vertex list, or -1 (see rtag_scene) */
    int32_t scene_first;
    /* ... and where its world positions are from: RTAG_SCENE_DEPTH put back by the 16-bit depth (no normals),
     * RTAG_SCENE_EXACT from the vertex programs' inputs (normals in rtag_scene::normals) */
    int32_t scene_kind;
} rtag_draw;
enum { RTAG_SCENE_NONE = 0, RTAG_SCENE_DEPTH = 1, RTAG_SCENE_EXACT = 2 };

typedef struct rtag_texture {
    uint32_t id;
    int32_t width, height;
    const uint8_t* rgba;        /* rows top to bottom; alpha as the GS has it (0x80 = 1.0) */
} rtag_texture;

typedef struct rtag_target {
    uint32_t id;
    int32_t width, height;      /* logical */
    int32_t screen;             /* a surface the size of the picture: meant to be drawn at output resolution */
} rtag_target;

/* The 3-D scene before the game's projection (config.scene3d): for every vertex of the draws that make up
 * the 3-D scene - what the vertex programs kicked and what the CPU projected into the 3-D surface with a
 * depth test - where it was in the world (scene_tap.cpp turns the projection round).  Parallel to the draw
 * list: a draw with scene_first >= 0 has `count` scene vertices from there, one per vertex of the draw, in
 * the same order; the list's own vertices still carry colour and texture coordinates. */
typedef struct rtag_scene_vertex {
    float x, y, z;              /* world space, the game's units */
    float w;                    /* its distance along the game camera's view axis */
} rtag_scene_vertex;

/* One mesh packet as a vertex program drew it (core/render/scene_tap.h): `count` vertices of the list from
 * `first`, three per triangle.  `mesh` is a figure over the packet's own data - the same packet of the same
 * file has the same figure in every frame; `occurrence` counts earlier packets with that figure in the frame;
 * `object` changes with every set-up, so packets with one number are one draw of one object. */
typedef struct rtag_scene_piece {
    uint64_t mesh;
    uint32_t occurrence, object;
    uint32_t first, count;
    uint8_t kind;               /* 1 level chunk, 2 model */
    uint8_t flags;              /* 1 two-pass program, 2 its first (environment-map) pass, 4 skinned, 8 mirrored, 16 clip flag */
    uint8_t entry, pad;
} rtag_scene_piece;

typedef struct rtag_scene {
    const rtag_scene_vertex* vertices;
    uint32_t vertex_count;
    const float* normals;       /* three per vertex, world space, unit length; zero where there is none */
    const rtag_scene_piece* pieces;
    uint32_t piece_count;
    uint32_t valid;             /* 1: the camera below was found this frame */
    float world_to_view[16];    /* row-major 4 x 4: the game's camera (world to view space) */
    float view_to_clip[16];     /* the game's projection (view to its clip space) */
    float world_to_screen[16];  /* the matrix the vertex programs were handed: world to GS screen units */
    float camera_position[3];
    float fov_y_degrees, near_plane, far_plane;
} rtag_scene;

typedef struct rtag_frame {
    uint64_t number;            /* the vertical blank this frame was closed at, counted from power-on */
    uint32_t sim_tick;          /* the game's simulation tick counter at that blank */
    uint32_t flags;             /* RTAG_FRAME_* */
    /* the draw list (config.lists) */
    const rtag_vertex* vertices;
    uint32_t vertex_count;
    const rtag_draw* draws;
    uint32_t draw_count;
    const rtag_texture* textures;       /* new this frame: make them before any draw runs */
    uint32_t texture_count;
    const rtag_target* targets;         /* new or resized this frame */
    uint32_t target_count;
    const uint32_t* dead_textures;
    uint32_t dead_texture_count;
    const uint32_t* dead_targets;
    uint32_t dead_target_count;
    uint32_t show_target;               /* what the display circuit reads; 0 = nothing */
    int32_t show_rect[4];               /* x, y, width, height in that target's logical pixels */
    float aspect;                       /* the shape the picture is meant to be seen in */
    /* the picture of the library's own renderer (config.picture_width; every frame or at "app shot") */
    const uint8_t* picture;             /* RGBA, rows top to bottom; NULL when not read back */
    int32_t picture_width, picture_height;
    /* pictures a script asked for at this blank ("app shot FILE"): the library has written FILE itself when
     * its own renderer runs; a host that draws the list may write its own picture beside it */
    const char* const* shots;
    uint32_t shot_count;
    /* "app <text>" lines of the script that are not the library's own (shot, stats): for the host - a key to
     * press through its own input system, say.  They belong to this blank. */
    const char* const* host_commands;
    uint32_t host_command_count;
    const rtag_scene* scene;            /* NULL without config.scene3d */
} rtag_frame;
enum { RTAG_FRAME_LEVEL = 1 /* a level is running (not the front end) */ };

/* ---- going -------------------------------------------------------------------------- */
/* The machine stands at every vertical blank until it is let go.
 * rtag_step: set both controllers (NULL: leave them), let the machine go for one blank, and wait up to
 * wait_ms (negative: as long as it takes) for the next finished frame.
 * Returns 1 and *frame when there is one, 0 when none came in time (take it with rtag_poll later), -1 when
 * the machine has ended (the script said quit, the game stopped) and nothing is left to take. */
int rtag_step(const rtag_pad* pads, int wait_ms, const rtag_frame** frame);
int rtag_poll(int wait_ms, const rtag_frame** frame);
/* The machine lets itself go: hz > 0 on the library's clock at that rate (59.94 is the console's), hz < 0
 * as fast as it can while frames are taken, 0 back to rtag_step.  Frames must still be taken, in order
 * (a list names the textures made by the lists before it); the machine waits when three are not. */
void rtag_run(double hz);

/* ---- sound --------------------------------------------------------------------------- */
/* Exactly `frames` frames of interleaved 16-bit stereo at 48 kHz (silence where there is nothing).  With
 * RTAG_SOUND_PULL this call is the sound side's clock: call it from the device's thread, at the device's rate. */
void rtag_audio_pull(int16_t* stereo, int frames);

/* ---- the machine's memory and figures ------------------------------------------------ */
const uint8_t* rtag_memory(void);       /* 32 MB of main memory, read only; NULL before the start */
uint64_t rtag_fields(void);             /* vertical blanks since power-on */
/* One line of key=value figures: blanks, processor time of the process and of the decoder, queue, sound. */
const char* rtag_info(void);
int rtag_ended(void);                   /* 1 once the machine has ended */
int rtag_exit_code(void);               /* the runtime's: 0 done, 3 a script condition timed out or it stopped on something it cannot do */

/* End the run: the game's thread prints the runtime's report at its next blank and stands still for good.
 * Returns when that has happened (or after 2 s).  The process may then exit. */
void rtag_stop(void);

#ifdef __cplusplus
}
#endif
#endif
