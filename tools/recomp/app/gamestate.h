/* gamestate.h - what an interface needs to know about the running game, as one plain C struct.
 *
 * A host that draws its own HUD (tools/godot/project/hud, or the native application) calls
 * rta_gs_update() once per displayed frame with the machine's main memory (32 MB, as
 * rta::memory() or rtag_memory() hand it out) and reads the result.  The reader NEVER
 * writes into the game and calls none of its code: it only follows the game's own data
 * (the player records, the object lists, a few globals of the HUD).  It keeps a little of
 * its own between calls - what the last frame looked like - to tell what happened in
 * between (damage, heals, kills, experience, gold, pickups) and to give every creature a
 * number that stays the same while it lives.
 *
 * Where each field comes from is said beside it: the address or offset, and the row of
 * FINDINGS.md or the document that established it ("Ran" = also seen on the running game
 * here, docs/issues/native-hud.md).  Offsets "+0x.." are into the player record
 * (g_players 0x4d8af0 + slot x 0x4c30, docs/player.md) unless "object" is said (the
 * GameObject / Creature / Player object, docs/objects.md, docs/creatures.md).
 *
 * Text (names of characters, classes, creatures, items, levels, prompts) is copied out of
 * the game's memory as it stands there at that moment; none of it is stored in this file.
 *
 * Call it while the game's thread stands still (at a vertical blank: rtag_step() has
 * returned, or from the frame hook of the native application).  C, no dependencies; the
 * same file is compiled into the Godot extension and can be compiled into the runtime.
 */
#ifndef RTA_GAMESTATE_H
#define RTA_GAMESTATE_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RTA_GS_VERSION 1
#define RTA_GS_PLAYERS 4
#define RTA_GS_CREATURES 64
#define RTA_GS_EVENTS 48
#define RTA_GS_STATUS 10
#define RTA_GS_SLOTS 2
#define RTA_GS_TEXT 32
#define RTA_GS_CHAT_LINES 6

/* ---- status effects ------------------------------------------------------------------ */
enum {
    RTA_GS_ST_NONE = 0,
    RTA_GS_ST_BURN = 1,         /* object +0x340, float seconds (docs/creatures.md "Second timers") */
    RTA_GS_ST_CHILL = 2,        /* object +0x344 */
    RTA_GS_ST_SHOCK = 3,        /* object +0x348 */
    RTA_GS_ST_POISON = 4,       /* object +0x34c */
    RTA_GS_ST_DOT2 = 5,         /* object +0x350: the second damage-over-time timer */
    RTA_GS_ST_STUN = 6,         /* object +0x31c, s16 frames (frame timers) */
    RTA_GS_ST_ROOT = 7,         /* object +0x314, s16 frames, -1 = until released */
    RTA_GS_ST_CHARM = 8,        /* object +0x312, s16 frames, -1 = permanent */
    RTA_GS_ST_SLOW = 9,         /* object +0x2fc slow amount 0..60 (from chill or status counter 7) */
    RTA_GS_ST_PROTECTED = 10,   /* object +0x4b4 spawn protection, record +0x4c27 hit immunity (players) */
    RTA_GS_ST_ENCHANT = 11,     /* a timed modifier of an equipped item: item +0x24 {id, value, ?, frames}[4] */
    RTA_GS_ST_HEALING = 12,     /* record +0xb4: healing still to be delivered by a potion */
    RTA_GS_ST_MANA = 13,        /* record +0xc8: mana still to be delivered by a potion */
    RTA_GS_ST_COUNTER = 14      /* one of the 16 status counters at object +0x36c (index in `detail`) */
};

typedef struct rta_gs_status {
    uint8_t kind;               /* RTA_GS_ST_* */
    uint8_t detail;             /* COUNTER: index 0..15; ENCHANT: modifier id; SLOW: amount 0..60 */
    uint16_t pad;
    float seconds;              /* time left in seconds (frames / 60); < 0: no end known */
    float seconds_most;         /* the largest value seen since it started (for a ring that empties); kept by the reader */
} rta_gs_status;

/* ---- quick slots: the two abilities bound to the ability buttons ------------------------ */
typedef struct rta_gs_slot {
    uint8_t filled;             /* an ability is bound: record +0x4a84 / +0x4a85 (index into the 15 ability records, s8, < 0 none) */
    uint8_t kind;               /* ability +0x25: 0 one cast, 1 held, 2 timed, 7 instant, 8 through the ranged attack (docs/player.md) */
    int16_t skill_id;           /* ability +0x20 */
    int16_t rank;               /* record +0x4b08 {id, rank}[48], the rank of that skill id */
    int16_t index;              /* which of the 15 ability records (+0x4440 + index x 0x68) */
    float mana_cost;            /* ability +0x2c (the older inline abilities; 999 = needs full mana); < 0 when the cost is not in data */
    float cooldown;             /* seconds left: object +0x4ae (s16 frames, one cooldown for all abilities of the player) */
    float cooldown_most;        /* ability +0x22 (s16 frames): what the cooldown starts from */
    uint8_t active;             /* this ability is being cast or held now (object +0x58c == 5 and record +0x4a60 == slot) */
    uint8_t enough_mana;        /* mana >= mana_cost (1 when the cost is unknown) */
    uint8_t pad[2];
    char name[RTA_GS_TEXT];     /* the skill's name as the game's skill table has it */
} rta_gs_slot;

/* ---- a player ---------------------------------------------------------------------------- */
typedef struct rta_gs_player {
    uint8_t present;            /* slot < g_numPlayers (0x4d8ae0) and the record has a name */
    uint8_t local;              /* this machine's own: offline every slot; in a net game see gamestate.cpp is_local() */
    uint8_t alive;              /* object != 0 and object flag 0x8 clear and health > 0 (docs/objects.md flags) */
    uint8_t in_menu;            /* object flag 0x400000: a menu of this player is open (game message 2, docs/ui.md) */
    uint8_t level;              /* +0x59 s8 */
    uint8_t level_acknowledged; /* +0x58 s8: lower than level = a level-up is waiting in the character screen */
    uint8_t stat_points;        /* +0xec s8 */
    uint8_t weapon_class;       /* +0x4a86: 0 one hand, 1/2 two hand, 3 long, 4 bow, 5 unarmed, 6 thrown, 7 dual */
    uint8_t selector_open;      /* the game's quick-cast selector is up for this player: g_spellSelectorAlpha 0x86a8d8[slot] > 0 (hud_spellSelect 0x1dd270) */
    int8_t selector_position;   /* the position highlighted there: 0..7 clockwise from up, -1 none (0x4f66b8[slot]) */
    uint8_t pad[2];
    int32_t class_index;        /* +0x50 */
    int32_t skill_points;       /* +0xe8 */
    float health, health_max;   /* +0xac, +0xb0 (FINDINGS G3; Ran) */
    float mana, mana_max;       /* +0xc0, +0xc4 (FINDINGS G3; Ran) */
    float health_coming;        /* +0xb4: healing a potion still delivers (docs/player.md; live-rig 4c) */
    float mana_coming;          /* +0xc8 */
    int32_t experience;         /* +0x5c */
    int32_t experience_base;    /* the table 0x41b554[level_acknowledged]: where this level's bar starts (hud_drawPlayerStatus 0x1d9cd4) */
    int32_t experience_next;    /* the table 0x41b558[level_acknowledged]: where it ends */
    int32_t gold;               /* +0xe4 */
    int32_t gold_coming;        /* gold picked up and still flying to the counter: g_goldFloaters + g_goldPending (docs/ui.md) */
    int32_t health_potions;     /* bag 2 (+0x2540, count +0x3740): quantities of the nine health potion kinds (player_countPotions 0x1ba5f8) */
    int32_t mana_potions;       /* the same for the nine mana potion kinds */
    int32_t ammunition;         /* quantity of the item in equipment slot 8 (+0x4410), 0 without */
    int32_t action_state;       /* object +0x58c: 0 ranged, 1 melee, 2 neutral, 3 staggered, 4 dead, 5 casting, 8 blocking ... (docs/player.md) */
    uint32_t object;            /* +0x43d8: guest address of the Player object, 0 while there is none */
    uint32_t target_uid;        /* the creature this player's attack is aimed at (object +0x234), 0 none */
    float position[3];          /* object +0x10: x, y on the ground, z up; the feet */
    float height;               /* object +0x20: height extent */
    float facing;               /* object +0x38 (u16, 65536 = a full turn) as radians, the heading in the ground plane */
    float screen[3];            /* a point above the head in the picture: x, y 0..1 from the top left, z = distance along the view (<= 0: behind) */
    uint32_t status_count;
    rta_gs_status status[RTA_GS_STATUS];
    rta_gs_slot slot[RTA_GS_SLOTS];
    char name[RTA_GS_TEXT];     /* +0x00 char[0x20] */
    char class_name[RTA_GS_TEXT];   /* the class row's name in the game's class table */
    char weapon[RTA_GS_TEXT];   /* the name of the item at +0x4434[active set +0x4a7c], as its definition has it */
} rta_gs_player;

/* ---- a creature near the players --------------------------------------------------------- */
enum {
    RTA_GS_CF_HOSTILE = 1,      /* an enemy of the players (see gamestate.cpp hostile()) */
    RTA_GS_CF_BOSS = 2,         /* boss rank 2: the game shows its own boss meter for it */
    RTA_GS_CF_MINIBOSS = 4,     /* creature flag bit 0 (MiniBoss property), boss rank 1 */
    RTA_GS_CF_DEAD = 8,         /* object flag 0x8 or AI state 0x14 */
    RTA_GS_CF_TARGETED = 16,    /* some player's attack is aimed at it (that player's object +0x234) */
    RTA_GS_CF_AGGRO = 32,       /* its own target (object +0x234) is a player; which one: target_slot */
    RTA_GS_CF_ATTACKING = 64,   /* AI state 6..15 (docs/creatures.md "AI state") */
    RTA_GS_CF_FRIENDLY = 128,   /* object flag 0x1000000 / creature flag 0x4000000, or a charmed helper on the players' team */
    RTA_GS_CF_NAMED = 256,      /* has a ShowName (object +0x368): can be talked to */
    RTA_GS_CF_INERT = 512,      /* object +0x231 != 0: hidden, waiting or frozen - takes no damage, picks no target */
    RTA_GS_CF_ONSCREEN = 1024,  /* screen[] lies inside the picture */
    RTA_GS_CF_MARKED = 2048     /* creature flag 0x80000000000 (script showOnMap): the game's own map shows it; kept in the list up to 3840 away */
};

typedef struct rta_gs_creature {
    uint32_t uid;               /* stays the same while this creature lives; never 0; not reused within a run */
    uint32_t object;            /* guest address (stable while alive: a pool block) */
    uint32_t flags;             /* RTA_GS_CF_* */
    int8_t target_slot;         /* the player slot it is after, -1 none */
    uint8_t boss_rank;          /* 0, 1 (mini boss), 2 (boss) */
    int16_t ai_state;           /* object +0x232 */
    float health, health_max;   /* object +0x228, +0x22c */
    float position[3];          /* object +0x10 */
    float height;               /* object +0x20: height extent (the top of the model above the feet) */
    float radius;               /* object +0x1c */
    float facing;               /* object +0x38 as radians */
    float screen[3];            /* a point just above the head, as rta_gs_player.screen */
    uint32_t status_count;
    rta_gs_status status[4];
    char name[RTA_GS_TEXT];     /* the name the game itself would show: see gamestate.cpp creature_name() */
} rta_gs_creature;

/* ---- what happened since the last call --------------------------------------------------- */
enum {
    RTA_GS_EV_DAMAGE_DEALT = 1, /* a creature lost health: amount, uid, position (its head) */
    RTA_GS_EV_DAMAGE_TAKEN = 2, /* a player lost health: amount, slot; position = where the one who did it stands (the player's last
                                   attacker, object +0x2e4; the player's own head when there is none), uid = that creature */
    RTA_GS_EV_HEAL = 3,         /* a player (slot) or a creature (uid) gained health other than by slow regeneration */
    RTA_GS_EV_MISS = 4,         /* reserved: needs a hook in the damage function, see docs/issues/native-hud.md */
    RTA_GS_EV_EXPERIENCE = 5,   /* a player's experience grew: amount, slot */
    RTA_GS_EV_GOLD = 6,         /* a player picked up or was paid gold: amount, slot */
    RTA_GS_EV_LEVEL_UP = 7,     /* a player's level grew: amount = the new level, slot */
    RTA_GS_EV_ITEM = 8,         /* a player received an item: text = its name, amount = quantity, slot */
    RTA_GS_EV_KILL = 9,         /* a creature died: uid, text = its name, position */
    RTA_GS_EV_PLAYER_DIED = 10, /* slot */
    RTA_GS_EV_MANA_SPENT = 11,  /* reserved */
    RTA_GS_EV_ITEM_LOST = 12    /* an item left the bags (used, dropped, sold): text, amount, slot */
};

typedef struct rta_gs_event {
    uint8_t kind;               /* RTA_GS_EV_* */
    int8_t slot;                /* player slot, -1 when it is not about a player */
    uint8_t heavy;              /* DAMAGE_*: a large share of the victim's health at once */
    uint8_t pad;
    uint32_t uid;               /* creature, 0 when it is not about one */
    float amount;
    float position[3];          /* world: where to show it */
    char text[RTA_GS_TEXT];
} rta_gs_event;

/* ---- something usable within reach ------------------------------------------------------- */
enum {
    RTA_GS_USE_NONE = 0, RTA_GS_USE_OTHER = 1, RTA_GS_USE_DOOR = 2, RTA_GS_USE_CHEST = 3, RTA_GS_USE_SAVEPOINT = 4,
    RTA_GS_USE_SHOP = 5, RTA_GS_USE_GATE = 6, RTA_GS_USE_TALK = 7, RTA_GS_USE_ITEM = 8, RTA_GS_USE_LEVER = 9,
    RTA_GS_USE_PORTAL = 10
};

typedef struct rta_gs_prompt {
    uint8_t active;             /* the game shows its own prompt for the local player this frame */
    uint8_t kind;               /* RTA_GS_USE_*: by the class of the object */
    int8_t slot;
    uint8_t pad;
    uint32_t object;            /* guest address of what would be used, 0 unknown */
    float position[3];
    uint32_t button;            /* libpad mask of the use button of that slot (g_btnUse 0x41b9c0[slot]) */
    char text[64];              /* the game's own prompt text as it stands in memory */
} rta_gs_prompt;

/* ---- the camera the frame is drawn with ---------------------------------------------------- */
/* By default the game's own camera, read from memory (g_cameraPos 0x44f038, g_cameraMatrix 0x44f110,
 * g_projScale 0x44f108; docs/issues/native-first-person.md section 2).  A build with the view modes of
 * tools/recomp/app/fpview.h puts another camera in place for the draw pass only and puts the game's
 * words back, so memory never shows it: such a host hands the frame's view in with rta_gs_set_view() (in Godot:
 * RtaMachine.get_view(), the rtag_view of the frame, which has this layout; a native host fills it from fpview::view()).
 * A view handed in without a camera (forward all zero: the overhead view runs no view code) gives the mode only;
 * the camera is then read from memory as before. */
enum { RTA_GS_VIEW_OVERHEAD = 0, RTA_GS_VIEW_ACTION = 1, RTA_GS_VIEW_CHASE = 2, RTA_GS_VIEW_SHOULDER = 3, RTA_GS_VIEW_FIRST = 4 };

typedef struct rta_gs_view {
    int32_t mode;               /* the view selected (RTA_GS_VIEW_*, the numbers of fpview::Mode) */
    int32_t shown;              /* the view this frame is closest to */
    float blend;                /* 0 the game's own camera .. 1 the selected view */
    uint8_t active;             /* drawn with a camera that is not the game's own */
    uint8_t fallback;           /* a view is selected but the game's camera has the frame */
    uint8_t hide_player;        /* the local player's model is left out (first person) */
    uint8_t have_head;
    char fallback_why[16];      /* "cutscene", "dialogue", "menu", "death", "load", ... */
    float eye[3], forward[3], up[3], right[3];
    float fov;                  /* vertical field of view, degrees (the game's own: 50) */
    float head[3];              /* the local player's eye point */
    float yaw;                  /* heading the camera looks along in the ground plane, radians: atan2(forward.y, forward.x) */
} rta_gs_view;

/* ---- the whole state ----------------------------------------------------------------------- */
enum {
    RTA_GS_PH_FRONTEND = 1,     /* the front end runs (title, menus before a game) */
    RTA_GS_PH_LEVEL = 2,        /* a level is loaded and a player object exists */
    RTA_GS_PH_LOADING = 4,      /* a level change is in progress */
    RTA_GS_PH_PAUSED = 8,       /* g_paused 0x41b4f4 */
    RTA_GS_PH_PAUSE_MENU = 16,  /* the pause menu is open */
    RTA_GS_PH_MENU = 32,        /* a game screen of this machine is up: inventory, shop, character sheet (g_localMenuOpen 0x41b69d) */
    RTA_GS_PH_CUTSCENE = 64,    /* g_cutsceneActive 0x44fcd0 */
    RTA_GS_PH_DIALOGUE = 128,   /* a conversation or a help / notice box is open */
    RTA_GS_PH_GATE_MENU = 256,  /* the jump-gate or the mission menu */
    RTA_GS_PH_FADE = 512,       /* g_hudFade 0x4f66ac is above half.  The level is kept between fades and the overlay is only drawn in
                                   frames in which something steps it, so this alone does not say the picture is dark (Ran: set all through the first level) */
    RTA_GS_PH_DEAD = 1024,      /* every local player is dead */
    RTA_GS_PH_CAMERA_HELD = 2048 /* the game's camera is not in follow mode (camera +0x34 != 1): the game hides its own HUD then */
};

enum {
    RTA_GS_NET_OK = 0,
    RTA_GS_NET_STALLED = 1,     /* no simulation tick for more than half a second (0x40279c > 30): waiting for the others */
    RTA_GS_NET_DESYNC = 2,      /* a peer's "out of sync" byte is set (peer +0x44d7; FINDINGS D1): net_notice_slot says who */
    RTA_GS_NET_CHECKSUM = 3,    /* g_checksumFailed 0x4f7144 (docs/ui.md P9) */
    RTA_GS_NET_LEAVING = 4,     /* g_netExitCountdown 0x4f6948 runs: this machine is about to leave the game */
    RTA_GS_NET_LOST = 5         /* the stall is longer than 1200 frames, or this machine was dropped (0x4027a0) */
};

typedef struct rta_gamestate {
    uint32_t version;           /* RTA_GS_VERSION */
    uint32_t struct_size;
    uint64_t updates;           /* calls of rta_gs_update so far */
    uint32_t sim_tick;          /* g_simFrame 0x44fdcc (FINDINGS V28) */
    uint32_t phase;             /* RTA_GS_PH_* */
    uint32_t hud_hidden;        /* the game would not draw its own player status this frame (the tests at the top of hud_drawPlayerStatus) */
    char level[16];             /* g_levelName 0x41b721 (FINDINGS V2): the level's own short name */
    char level_title[48];       /* a readable title when the game holds one, else empty */

    /* players */
    int32_t player_count;       /* g_numPlayers 0x4d8ae0 */
    int32_t local_slot;         /* the first local player's slot, -1 none */
    rta_gs_player player[RTA_GS_PLAYERS];

    /* creatures within reach of the players (the objects the game itself runs every frame) */
    int32_t creature_count;
    int32_t creatures_dropped;  /* more than RTA_GS_CREATURES were there: the farthest were left out */
    rta_gs_creature creature[RTA_GS_CREATURES];
    uint32_t boss_uid;          /* the creature the game's own boss meter is about, 0 none */

    /* what happened since the last call */
    int32_t event_count;
    int32_t events_dropped;
    rta_gs_event event[RTA_GS_EVENTS];

    rta_gs_prompt prompt;

    /* the game's own one-line HUD message (hud_showMessage 0x1d92a0) */
    char message[128];
    int32_t message_frames;     /* frames it still shows, 0 none */

    /* the objective the game's own compass points at (script showCompass, hud_setCompassTarget 0x1df668) */
    uint8_t compass_on;
    uint8_t pad0[3];
    float compass_target[3];

    rta_gs_view view;
    float aspect;               /* the shape the 3-D view is drawn in (set by the host; 4/3 when not) */

    /* online */
    uint8_t online;             /* g_networkMode 0x402791 */
    uint8_t net_notice;         /* RTA_GS_NET_* */
    int8_t net_notice_slot;     /* the player it is about, -1 */
    uint8_t pad1;
    int32_t net_stall_frames;   /* the stall counter 0x40279c: displayed frames without a tick */
    int32_t net_exit_frames;    /* g_netExitCountdown 0x4f6948 */
    int32_t chat_count;
    char chat[RTA_GS_CHAT_LINES][96];   /* "name: text", oldest first: the game's own log 0x8e8ac8 (8 x 0x7e bytes), lines younger than 601 ticks */
    int8_t chat_slot[RTA_GS_CHAT_LINES];   /* who said it */
    uint8_t pad2[2];
} rta_gamestate;

typedef struct rta_gs_reader rta_gs_reader;     /* what the reader keeps between calls */

rta_gs_reader* rta_gs_create(void);
void rta_gs_destroy(rta_gs_reader* reader);
/* Fill the state from `ram` (32 MB of main memory, read only).  The pointer returned is the reader's own
 * struct and stays valid until the next call or rta_gs_destroy. */
const rta_gamestate* rta_gs_update(rta_gs_reader* reader, const uint8_t* ram);
const rta_gamestate* rta_gs_state(const rta_gs_reader* reader);
/* The shape of the 3-D view (width / height; widescreen scales the horizontal projection, tools/recomp/app/gfx_rt.cpp). */
void rta_gs_set_aspect(rta_gs_reader* reader, float aspect);
/* The frame's camera from a host that has view modes; NULL: back to the game's own camera read from memory. */
void rta_gs_set_view(rta_gs_reader* reader, const rta_gs_view* view);
/* The picture a list shows is one simulation tick older than the memory read at the same blank (the game sends a
 * frame's packets at the start of the next).  frames = 1 (default) makes every screen[] the one that belongs to
 * the picture shown; 0: of the memory as it is now. */
void rta_gs_set_screen_delay(rta_gs_reader* reader, int frames);
/* World position -> the picture: out[0], out[1] in 0..1 from the top left, out[2] the distance along the view.
 * Returns 0 when the point is behind the camera. */
int rta_gs_project(const rta_gs_reader* reader, const float world[3], float out[3]);
/* Microseconds the last rta_gs_update took (the reader measures itself). */
double rta_gs_cost_usec(const rta_gs_reader* reader);

#ifdef __cplusplus
}
#endif
#endif
