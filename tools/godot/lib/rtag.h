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

#define RTAG_API_VERSION 6

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
    const char* view;           /* the camera view to start in: "overhead" (the game's own, default), "action", "chase",
                                   "shoulder", "first" (tools/recomp/app/fpview.h); rtag_set_option("view", ...) changes it */
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
/* Optional since version 6: rtag_has("rumble"). Snapshot the latest motors for local port 0 or 1.
 * small is the raw 8-bit command (any nonzero means the weak motor is fully on); large is strong amplitude 0..255.
 * generation advances per command, including repeats, and once for the neutral stop/exit release. Reads do not consume.
 * All outputs are optional; 1 = valid port of a started machine, 0 = unavailable/invalid (outputs zeroed).
 * Thread-safe against game writes and stop; after stop/exit every snapshot stays neutral. Hosts own device mapping,
 * focus/hotplug safety and final physical release. Older libraries may omit this symbol. No ABI structure changes. */
int rtag_rumble(int port, uint8_t* small, uint8_t* large, uint64_t* generation);

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
    /* ... and the mesh packets drawn with this draw's state: rtag_scene::pieces from scene_piece_first.  Their
     * complete geometry (rtag_scene_piece::full_first) is what a host that has a real camera should draw
     * instead of the list's own triangles. */
    uint32_t scene_piece_first, scene_piece_count;
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
    /* The packet's complete geometry (rtag_scene::full): every triangle of its strip, three corners each - also
     * the ones the vertex program dropped whole near the eye or off screen, which are not in the draw list
     * (`count` is 0 for a packet all of whose triangles were dropped).  `command`: the draw whose state it is
     * drawn with (the draw its list vertices are in, or that of the packet before it of the same object), -1 none. */
    uint32_t full_first, full_count;
    int32_t command;
} rtag_scene_piece;

typedef struct rtag_scene_full {
    float x, y, z;              /* world space */
    float nx, ny, nz;           /* the game's normal, world space */
    float u, v;                 /* texels, as rtag_vertex s, t with q = 1 */
    uint8_t r, g, b, a;         /* the colour the game's vertex program computed (its light) */
} rtag_scene_full;

typedef struct rtag_scene {
    const rtag_scene_vertex* vertices;
    uint32_t vertex_count;
    const float* normals;       /* three per vertex, world space, unit length; zero where there is none */
    const rtag_scene_piece* pieces;
    uint32_t piece_count;
    const rtag_scene_full* full;
    uint32_t full_count;
    uint32_t valid;             /* 1: the camera below was found this frame */
    float world_to_view[16];    /* row-major 4 x 4: the game's camera (world to view space) */
    float view_to_clip[16];     /* the game's projection (view to its clip space) */
    float world_to_screen[16];  /* the matrix the vertex programs were handed: world to GS screen units */
    float camera_position[3];
    float fov_y_degrees, near_plane, far_plane;
} rtag_scene;

/* The camera a frame was drawn with (tools/recomp/app/fpview.h, fpview::View): which view is selected and
 * shown, and where the camera is.  With a view other than "overhead" the game itself builds, culls and sends
 * the frame for that camera, so the frame's scene (rtag_scene) is already seen from here.  The first fields,
 * up to and including `yaw`, are laid out as rta_gs_view of tools/recomp/app/gamestate.h. */
enum { RTAG_VIEW_OVERHEAD = 0, RTAG_VIEW_ACTION = 1, RTAG_VIEW_CHASE = 2, RTAG_VIEW_SHOULDER = 3, RTAG_VIEW_FIRST = 4 };
typedef struct rtag_view {
    int32_t mode;               /* the view selected */
    int32_t shown;              /* the view this frame is closest to (a transition, a fallback) */
    float blend;                /* 0 the game's own camera .. 1 the selected view */
    uint8_t active;             /* drawn with a camera that is not the game's own */
    uint8_t fallback;           /* a view is selected but the game's camera has the frame */
    uint8_t hide_player;        /* the local player's model is left out (first person) */
    uint8_t have_head;          /* `head` is the pose's head joint (else feet + eye height) */
    char fallback_why[16];      /* "cutscene", "dialogue", "menu", ... */
    float eye[3], forward[3], up[3], right[3];     /* world space: z up */
    float fov;                  /* vertical field of view, degrees (the game's own: 50) */
    float head[3];              /* the local player's eye point */
    float yaw;                  /* heading in the ground plane, radians: atan2(forward.y, forward.x) */
    /* ---- beyond rta_gs_view ---- */
    float near_plane, far_plane;
    float player[3];            /* the local player's position (feet) */
    float facing;               /* the character's heading, degrees */
    float look_pitch;           /* degrees */
    uint8_t have_player, valid; /* valid: the library has the view modes and a draw pass has run */
    uint8_t pad[2];
    uint32_t tick;              /* g_simFrame when the frame was drawn */
} rtag_view;

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
    rtag_view view;                     /* the camera this frame's list was built for */
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
/* rtag_release (optional): let the machine go for one blank and return at once - the frame is taken later with
 * rtag_poll (a host that lets blanks go ahead of the pictures that show them: Godot's display rate) */
int rtag_release(void);
/* The machine lets itself go: hz > 0 on the library's clock at that rate (59.94 is the console's), hz < 0
 * as fast as it can while frames are taken, 0 back to rtag_step.  Frames must still be taken, in order
 * (a list names the textures made by the lists before it); the machine waits when three are not. */
void rtag_run(double hz);

/* ---- options while it runs ----------------------------------------------------------- */
/* From any thread; 1 when the key is one of:
 *   "view"                   a view by name (overhead, action, chase, shoulder, first): eased in over a third of a second.
 *                            The look inputs are the controller's own: the right stick turns the game's camera as it
 *                            always did, and a view that looks up and down takes the stick's y (fpview.h).
 *   "view.<mode>.<name>"     a setting of a view (fov, distance, height, pitch, eye_height, ... : fpview.h)
 *   "aspect"                 the shape of the 3-D view as a number, width / height ("1.7778"); 4:3 at the least
 *   "music_volume"           0..1: the game's music alone (speech and effects stay); refused by a library whose sound core lacks it
 *   "controls.<name>"        a setting of the look controls (fpcontrols.h); "controls" = "off" | "on": the library leaves
 *                            the controller rows alone / translates them in the look views (default on)
 *   "game_hud_text"          "off": also the game's boss meter, its one-line message and its prompt box are left out
 *                            (refused by a library whose translation does not wrap those two draw functions)
 *   "game_hud"               "off": the game's own HUD layer (player status, gold, compass, minimap, spell selector) is
 *                            left out of the frames, for a host that draws its own; "on" (default)
 */
int rtag_set_option(const char* key, const char* value);

/* ---- the controls of the views that look along the ground (optional functions) ------------
 * tools/recomp/app/fpcontrols.h, when the library was built with it (rtag_has("controls")): in chase, shoulder and
 * first person the right stick and the pointer are the look (the game camera's yaw, a pitch of the picture), and
 * the character is turned to where the player looks - all by ordinary controller rows, the simulation is told
 * nothing new.  The library does this by itself with the controller it is given (rtag_set_pad); a host adds the
 * pointer, and may show what the controls know (rtag_controls: fpcontrols::Hud, field for field).
 * These functions were added after version 6 of the interface without changing it: a host looks them up by name
 * and does without them when the library is older. */
typedef struct rtag_mark {
    uint8_t valid, pad[3];
    uint32_t object;            /* guest address of the creature */
    float x, y, z, distance, bearing, hp, hp_max;
} rtag_mark;
typedef struct rtag_threat {
    uint32_t object;
    float x, y, z, distance, bearing;
    uint8_t targets_me, attacking, in_view, pad;
} rtag_threat;
typedef struct rtag_controls {
    uint32_t struct_size;       /* sizeof(rtag_controls), set by the caller */
    uint32_t tick;
    uint64_t blank;
    int32_t view;
    uint8_t look, playing, ranged, aligning, reticle, usable, wants_pointer, pad;
    int32_t slot;
    uint32_t player;
    float x, y, z, look_heading, look_pitch, facing, facing_error;
    int32_t state, weapon_class;
    rtag_mark melee, shot, locked;
    int32_t usable_kind, usable_fade;
    uint32_t usable_object;
    float usable_x, usable_y, usable_z, usable_bearing;
    char usable_text[96];
    int32_t threat_count, behind;
    rtag_threat threats[16];
    uint32_t swings, hits_dealt, hits_taken, deaths, respawns;
    float last_hit_bearing, last_hit_amount;
} rtag_controls;
int rtag_controls_hud(rtag_controls* out);      /* 1: filled (as of the last controller read); 0: no controls in this library */
void rtag_mouse(float dx, float dy, float wheel);       /* pointer motion since the last call (right and down positive), wheel steps (up positive) */
void rtag_mouse_button(int button, int down);           /* 0 left, 1 right, 2 middle, 3 and 4 the side buttons */

/* ---- the world for a camera inside it (optional function) ---------------------------------
 * tools/recomp/app/fpworld.h and render/worldfill.h, when the library was built with them (rtag_has("world")): at a
 * level load the library makes geometry the level does not have - a ceiling over the walked floor of a walled level,
 * a skirt of ground beyond the level's outer rim - from the level's own terrain (none of it is the game's art; how
 * it looks is the host's: a vertex has a position, a normal, world-space texture coordinates and a grey level).
 * With the scene tap (RTAG_LISTS_SCENE / scene3d) the library leaves its cut at the near plane and its textures in
 * perspective off - the host draws the packets' complete geometry itself - and the host draws the fill.  A ceiling is
 * for a camera under it.  rtag_set_option("world", "views|off|always"), "world.ceilings" / "world.skirts" = auto|on|off.
 * Added after version 6 of the interface without changing it: looked up by name. */
enum { RTAG_FILL_CEILING = 1, RTAG_FILL_SKIRT = 2, RTAG_FILL_RIM = 3 };   /* RIM: under a floor's edge over nothing (worldfill.h FILL_RIM) */
typedef struct rtag_fill_vertex {
    float position[3];          /* world space, z up, the game's units */
    float normal[3];            /* a ceiling's looks down, a skirt's up */
    float uv[2];                /* world x, y / 64 */
    uint8_t rgba[4];            /* grey level: a ceiling 255 at a wall, less away from it; a skirt's alpha 128 at the rim, 0 outside */
} rtag_fill_vertex;
typedef struct rtag_fill_mesh {
    uint8_t kind, pad[3];       /* RTAG_FILL_CEILING, RTAG_FILL_SKIRT or RTAG_FILL_RIM */
    uint32_t first, count;      /* vertices[first .. first + count): triangles, three vertices each */
    float bounds[6];            /* min x, y, z, max x, y, z */
} rtag_fill_mesh;
typedef struct rtag_fill {
    uint64_t serial;            /* another level or other options: another number - rebuild only when it changes */
    const char* level;          /* the level's name */
    const rtag_fill_vertex* vertices;
    uint32_t vertex_count, mesh_count;
    const rtag_fill_mesh* meshes;   /* blocks of 128 x 128 units, each with its box */
    float bounds[6];
} rtag_fill;
/* 1: `out` describes the fill of the level that is loaded; its pointers stay valid until the next call of this
 * function or rtag_stop.  0: none (a level that gets none, no level yet, or a library without it).  Any thread. */
int rtag_fill_get(rtag_fill* out);

/* ---- what the emulator-based build calls each texture (optional: rtag_has("texture_names")) -----------
 * For a host that draws pictures in place of the game's textures (an art pack: a folder of PNG files named
 * "<figure>-<palette>-p<format>-<width>x<height>.png", figures as 16 hexadecimal digits, of a whole multiple of
 * that size, covering the texels from the texture's corner; tools/recomp/render/texpack.h).  Parallel to the
 * textures of the frame taken last (rtag_frame.textures, same order); `named` 0: the texture was made before
 * naming was on (scene mode, or rtag_set_option("name_textures", "1")).  Returns the number written.  Same
 * thread as rtag_poll; added without a change of RTAG_API_VERSION (the frame's own records are as they were). */
typedef struct rtag_texture_name {
    uint32_t id;
    int32_t named;
    uint64_t figure, palette_figure;
    uint32_t format;
    int32_t sent_width, sent_height;    /* the smallest rectangle from the corner that holds every texel sent */
    int32_t named_width, named_height;  /* the size TEX0 names */
} rtag_texture_name;
uint32_t rtag_texture_names(rtag_texture_name* out, uint32_t max);

/* ---- a room of our own (optional) ------------------------------------------------------
 * When rtag_has("net2") (the fix-set library, built with tools/recomp/net and net2): the library contains the network
 * driver, the session client of tools/recomp/net2/session.h and the direct launch of net2/game.h, and exports their
 * plain-C functions under their own names (net2_open, net2_game_attach, net2_game_choose, net2_game_status, ...) - the
 * one copy of net2 in the process: a host (the portal) looks them up in this library and does not link its own.  The
 * portal's part: net2_open, then net2_game_attach(n) once; the library follows that room by itself (launches when the
 * room starts).  docs/issues/native-rendezvous.md 5.1.  The stand-alone way: rtag_start with the runtime arguments
 * "--opt net2=host | join:CODE" (and net2-name, net2-service) takes the machine into a room by itself from power-on. */

/* ---- the skeletons of the frame (optional: rtag_has("skeletons"); added after version 6 without changing it) --------
 * With the scene tap (config.scene3d): for every animated model drawn this frame, the skeleton the game's own animation
 * code posed it with, and the bind-pose mesh its packets were made from - what a host needs to draw the figure itself,
 * re-posed (a Godot Skeleton3D, Skin and ArrayMesh), or something else in its place.  tools/godot/lib/skeleton_export.h
 * says where each number comes from.  Matrices are row-major 3 x 4 [R | t] for column vectors (p' = R p + t), in the
 * game's world (z up, its units).
 *   skin[j]   bind-pose model space -> world: what the game's vertex program transformed the joint's vertices with
 *             (its joint matrix taken back through the inverse of the view-projection).
 *   bind[j]   the joint's origin in the bind pose, model space (the clip's bind offset, negated); the bind pose has
 *             every joint's axes along the model's.
 *   joint[j]  the posed joint in the world: skin[j] with the origin moved to bind[j] (= skin[j] x T(bind[j])).
 * So a Skeleton3D with bone j's rest T(bind[j] - bind[parent[j]]), a Skin with bind pose T(-bind[j]), and bone j's
 * global pose joint[j] skins the sources exactly as the game did. */
typedef struct rtag_skeleton {
    uint32_t object;            /* the first rtag_scene_piece::object drawn with this pose (a figure may be several objects) */
    uint32_t pose;              /* the pose's number this frame (the game's pose buffer, drawn); objects with one pose are one figure */
    uint32_t state, clip;       /* guest addresses: the animation state the pose belongs to, the clip whose skeleton it has */
    uint32_t buffer;            /* guest address of the pose buffer */
    int32_t joint_count;        /* 1 .. 64; 0: the structure was not found (skin[] is still valid for 64 joints) */
    int8_t parent[64];          /* -1: a root */
    uint8_t depth[64];          /* the clip's depth list */
    float bind[64][3];
    float skin[64][12];
    float joint[64][12];
    float scale;                /* the figure's scale in the world (the length of skin[0]'s first column) */
    float pose_error;           /* largest difference between the skin matrices and the pose buffer through one object
                                   matrix, in world units (the check that joint j of the buffer is matrix j of the program) */
} rtag_skeleton;
typedef struct rtag_skin_source {   /* one vertex of a packet as the program was given it (render::TapSource) */
    float position[3];          /* bind-pose model space */
    float normal[3];
    uint8_t joint[4];           /* 0 .. 63 */
    uint8_t weight[4];          /* of 255 */
} rtag_skin_source;
typedef struct rtag_skin_piece {    /* parallel to rtag_scene::pieces */
    int32_t skeleton;           /* index into rtag_skeletons::skeletons, -1: none */
    uint32_t source_first, source_count;
    float slot0[12];            /* joint matrix 0 of the piece in the world (a rigid model's own matrix: a weapon in a hand) */
} rtag_skin_piece;
typedef struct rtag_skeleton_player {  /* one of the game's players, as of the draw pass the frame shows */
    int32_t slot;               /* 0 .. 3 (0 .. 7 in a game of five to eight) */
    uint32_t object;            /* guest address of its creature (player record +0x43d8) */
    uint32_t state;             /* its animation state (object +0x114): rtag_skeleton::state of the poses that draw it */
    int32_t character_class;    /* record +0x50: 0 barbarian, 1 cleric, 2 shadowknight, 3 ranger, 4 wizard, 5 berserker, 6 shaman */
    int32_t weapon_class;       /* the weapon in hand by the Hardcore mode's classes (soulscombat.h WC_*): 0 none, 1 dagger,
                                   2 sword, 3 axe, 4 mace, 5 great weapon, 6 spear, 7 staff, 8 bow; -1 not known (built without it) */
    uint32_t weapon_item;       /* guest address of the item record in hand, 0 none */
} rtag_skeleton_player;
typedef struct rtag_skeletons {
    uint32_t struct_size;       /* sizeof(rtag_skeletons), set by the caller */
    uint32_t skeleton_count, piece_count, source_count, full_count;
    const rtag_skeleton* skeletons;
    const rtag_skin_piece* pieces;      /* piece_count == rtag_scene::piece_count */
    const rtag_skin_source* sources;
    const uint16_t* full_source;        /* per rtag_scene::full corner: which source of its piece (source_first + this) */
    uint32_t poses_seen, poses_matched; /* figures: poses uploaded / found again in the program's joint matrices */
    /* added later (filled when struct_size reaches them): the players present - read on the game's thread with the poses */
    uint32_t player_count;
    rtag_skeleton_player players[4];
    /* added later again (filled when struct_size reaches them): a game of five to eight's players past the first four
       (docs/issues/native-8-players.md); player_count then counts them too (up to 8: players[0..3], then these) */
    rtag_skeleton_player players_more[4];
} rtag_skeletons;
/* 1: filled for the frame taken last (pointers valid until the next frame is taken); 0: none (no scene, an older library).
 * Same thread as rtag_poll. */
int rtag_skeletons_get(rtag_skeletons* out);

/* ---- the film playing now (optional: added after version 6 without changing it) ---------------
 * tools/recomp/app/film.cpp: while the game's film player has a film open, its key (the FNV-1a hash of the first
 * 65,536 bytes of the stream since the player's last reset - tools/install/films.py names its enlarged copies so;
 * 0 while fewer were fed) and the picture handed out last (display order since that reset, -1 none yet).  For a host
 * that shows an enlarged copy in its place: presentation only.  1: a film is open; 0: none (or no films linked). */
typedef struct rtag_film {
    uint64_t key;
    int32_t picture, width, height, pad;
} rtag_film;
int rtag_film_now(rtag_film* out);

/* ---- sound --------------------------------------------------------------------------- */
/* Exactly `frames` frames of interleaved 16-bit stereo at 48 kHz (silence where there is nothing).  With
 * RTAG_SOUND_PULL this call is the sound side's clock: call it from the device's thread, at the device's rate. */
void rtag_audio_pull(int16_t* stereo, int frames);

/* ---- the machine's memory and figures ------------------------------------------------ */
const uint8_t* rtag_memory(void);       /* main memory, read only (rtag_memory_size bytes; 32 MB); NULL before the start */
/* the size of rtag_memory (optional, added after version 6): 32 MB, or 64 MB in a library built for rooms of up to
   eight (RTA_GODOT_PARTY8=1, rt/ramsize.h); a host that finds no such function takes 32 MB */
uint32_t rtag_memory_size(void);
/* where the game's tables sized for four are while they are moved for a game of up to eight (optional, added after
   version 6; tools/recomp/rt/moved.h): a host that reads rtag_memory at the game's fixed addresses maps them through
   these (party8_at) - delta null: nothing is moved.  The pointers stay valid for the life of the machine. */
typedef struct rtag_moved {
    const uint32_t* delta;              /* per table: added to an address inside it; null while nothing is moved */
    const uint32_t (*spans)[2];         /* per table: [lo, hi) of its old place */
    uint32_t tables;                    /* the slots of both arrays (moved.h PARTY8_TABLES) */
    uint32_t wide;                      /* 1 in a game of five to eight (moved.h g_party8_wide) */
} rtag_moved;
int rtag_moved_get(rtag_moved* out);
uint64_t rtag_fields(void);             /* vertical blanks since power-on */
/* One line of key=value figures: blanks, processor time of the process and of the decoder, queue, sound. */
const char* rtag_info(void);
int rtag_ended(void);                   /* 1 once the machine has ended */
int rtag_exit_code(void);               /* the runtime's: 0 done, 3 a script condition timed out or it stopped on something it cannot do */

/* ---- the tester's kit (tools/recomp/app/testerkit.h; optional functions, added after version 6) ----------------
 * The library keeps the last 60 s of the tick log and of the input record (rings, always), and from rtag_start a
 * crash handler that writes a report into <data_dir>/reports.  The host draws the box and the build line
 * (tools/godot/project/testerkit.gd).  Strings stay valid until the next call of the same function; "" when the library
 * was built without the kit.  No upload: the reports stay on the player's computer. */
const char* rtag_report_begin(const char* host_lines);  /* take a report now; returns its folder (the host writes
                                                           <folder>/screenshot.png itself); host_lines: "key = value" lines
                                                           for its about.txt (the host's settings), may be NULL */
const char* rtag_report_finish(const char* folder, const char* text, int keep);   /* the player's text (may be ""); keep 0
                                                           drops it.  Returns the zip's path ("" when dropped or failed) */
const char* rtag_build_line(void);      /* "RTA <commit> <date>  fixes <set>  <platform>" */
double rtag_frame_since_release_ms(void);   /* ... and how long ago the game was let go into that frame (its controller read) */
double rtag_frame_age_ms(void);        /* how long ago the frame taken last (rtag_poll) was finished by the decoder; -1 none.  For a host
                                         * that times its releases (Godot's display rate: how long a blank takes from its release to its frame) */
const char* rtag_report_told(void);     /* after rtag_start: what to tell the player about a crash report of the run before ("" none) */

/* End the run: the game's thread prints the runtime's report at its next blank and stands still for good.
 * Returns when that has happened (or after 2 s).  The process may then exit. */
void rtag_stop(void);

#ifdef __cplusplus
}
#endif
#endif
