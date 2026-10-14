/* session.h - the native build's own way into an online game: who I am, my friends, a room,
 * and the start of a game.  No SOE screen, no account, no password.
 *
 * Plain C.  Nothing here blocks: every call returns at once, the work is done in
 * net2_poll() (call it once per displayed frame, or at least ten times a second), and
 * whatever happened since comes back as events (net2_next_event) and as snapshots
 * (net2_me, net2_friends, net2_room ...).  One object, one thread: call everything from
 * the thread that polls.
 *
 * Two bodies behind the same calls:
 *   the service  tools/rendezvous/rendezvous.py (docs/issues/native-rendezvous.md has the
 *                wire format): identity by a device secret, friends, presence, invites,
 *                rooms by code, UDP hole punching and relay.
 *   the mock     config.mock = 1 (or service "mock"): fake friends, requests, an invite,
 *                a room that fills, chats, gets ready and starts - all made locally, no
 *                socket is opened.  For building screens before, or without, a service.
 *
 * What a screen does with it:
 *   net2_config c; memset(&c, 0, sizeof c); c.struct_size = sizeof c;
 *   c.data_dir = ".../player data"; c.service = "127.0.0.1:41900";    // or c.mock = 1
 *   net2* n = net2_open(&c);
 *   every frame:  net2_poll(n);  net2_event e;  while (net2_next_event(n, &e)) { ... }
 *                 net2_me / net2_friends / net2_requests / net2_invites / net2_room to draw
 *   buttons:      net2_host, net2_join, net2_chat, net2_ready, net2_start, net2_leave,
 *                 net2_friend_add, net2_friend_accept, net2_invite, net2_invite_accept ...
 *   NET2_EV_START: the room's game begins - in a program that contains the game the launch
 *                 itself is done by tools/recomp/net2/launch.cpp (it listens to the same
 *                 object); a screen only has to get out of the way.
 *
 * Text is UTF-8, always terminated, cut to the sizes below.  A player's name is a label:
 * anybody may call themselves anything; the player is the id.
 */
#ifndef RTA_NET2_SESSION_H
#define RTA_NET2_SESSION_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NET2_API_VERSION 1

#define NET2_ID 33              /* a player id: 32 hex digits + 0 */
#define NET2_NAME 32            /* a display name: at most 24 bytes are kept by the service */
#define NET2_FRIEND_CODE 12     /* "K7QF-2MXD" */
#define NET2_ROOM_CODE 8        /* "H4KQ7" */
#define NET2_TEXT 160           /* a chat line (120 bytes kept), a notice, an error */
#define NET2_LEVEL 24           /* a level's name as the game has it ("hub", "drunare") */
#define NET2_CLASS 24
#define NET2_PLAYERS 4          /* the game's limit */
#define NET2_CHAT_LINES 32      /* what a room keeps */

typedef struct net2 net2;       /* one connection to the service (or one mock) */

/* ---- set-up ------------------------------------------------------------------------- */
typedef struct net2_config {
    uint32_t struct_size;       /* sizeof(net2_config): lets the struct grow */
    const char* data_dir;       /* the player's data folder: "net2-identity.key" is made here on the
                                   first start (mode 0600) and read afterwards.  Moving to another
                                   computer = copying that one file.  NULL: nothing is kept (a new
                                   player at every start) */
    const char* service;        /* "host:port" of the rendezvous service.  NULL or "": the mock when
                                   `mock` is set; otherwise the environment variable RTA_NET2_SERVICE,
                                   then the first line of <data_dir>/net2-service.txt, then the built-in
                                   default (none yet: where the service runs is the owner's decision -
                                   until then everything says OFFLINE and net2_me().problem says why) */
    int mock;                   /* 1: the mock described above; `service` is ignored */
    const char* name;           /* the display name to register with on the very first start
                                   (later: net2_set_name); NULL: "Player" */
    /* what this copy of the game is, told to a room so that a mismatch is shown before the
       start (0 = not known: a portal without the game inside leaves them 0) */
    uint32_t fix_set;           /* the fix-set figure (FNV-1a of the patch words) */
    uint16_t fix_words;
    uint8_t arith_can;          /* bit 0: the console's arithmetic, bit 1: a browser's */
    uint8_t arith_does;         /* 0 the console's, 1 a browser's */
    const char* build;          /* a label for logs: "rta_app 2026-10-13" */
    int local_only;             /* tests: refuse a service that is not on this computer */
} net2_config;

net2* net2_open(const net2_config* config);     /* never NULL */
void net2_close(net2* n);
void net2_poll(net2* n);                        /* never blocks */

/* ---- what happened ------------------------------------------------------------------ */
enum {
    NET2_EV_NONE = 0,
    NET2_EV_LINK,               /* the link to the service changed: net2_me().link */
    NET2_EV_ME,                 /* my name / friend code / id changed or arrived */
    NET2_EV_FRIENDS,            /* the friends list or somebody's presence changed */
    NET2_EV_REQUESTS,           /* friend requests changed (text: the name, when one came in) */
    NET2_EV_INVITE,             /* an invitation came in (text: who; code: the room) or went away */
    NET2_EV_RECENT,             /* the recent-players list changed */
    NET2_EV_ROOM,               /* the room changed: members, ready marks, options, routes, state */
    NET2_EV_CHAT,               /* a chat line (text: the line, who: the sender's name) */
    NET2_EV_START,              /* the host started: net2_room().state is NET2_ROOM_STARTING and
                                   net2_session() is valid */
    NET2_EV_GAME_OVER,          /* the game of this room ended on this machine (back in the room, or out) */
    NET2_EV_NOTICE,             /* something to tell the player in words (text) */
    NET2_EV_ERROR,              /* a request was refused or failed (text says why; code: NET2_ERR_*) */
    NET2_EV_DELETED             /* net2_delete_everything() was carried out */
};
enum {
    NET2_OK = 0,
    NET2_ERR_OFFLINE = -1,      /* no link to the service */
    NET2_ERR_ARGUMENT = -2,     /* empty, too long, not a code ... */
    NET2_ERR_STATE = -3,        /* not in a room, not the host, already in a room ... */
    NET2_ERR_LIMIT = -4,        /* too many, too fast (the service's limits) */
    NET2_ERR_NOT_FOUND = -5,    /* no such room / player / friend code */
    NET2_ERR_FULL = -6,         /* the room has four players */
    NET2_ERR_REFUSED = -7,      /* blocked, not joinable, the game has started */
    NET2_ERR_SERVICE = -8       /* the service said something else (text) */
};
typedef struct net2_event {
    int type;                   /* NET2_EV_* */
    int code;                   /* NET2_ERR_* for an error, else 0 */
    char who[NET2_NAME];        /* a player's name, where there is one */
    char who_id[NET2_ID];
    char room[NET2_ROOM_CODE];  /* a room code, where there is one */
    char text[NET2_TEXT];
} net2_event;
int net2_next_event(net2* n, net2_event* out);  /* 1: *out filled; 0: nothing more */

/* ---- me ------------------------------------------------------------------------------ */
enum { NET2_LINK_OFF = 0, NET2_LINK_CONNECTING = 1, NET2_LINK_ONLINE = 2 };

typedef struct net2_character {
    char name[NET2_NAME];       /* as the game shows it */
    char cls[NET2_CLASS];       /* the class row's name ("Barbarian"); a label */
    int32_t level;              /* 0: not known */
} net2_character;

typedef struct net2_me_t {
    int link;                   /* NET2_LINK_* */
    int mock;                   /* 1: this is the mock */
    char id[NET2_ID];           /* empty until the service has answered once */
    char name[NET2_NAME];
    char friend_code[NET2_FRIEND_CODE];     /* read it out to a friend: "K7QF-2MXD" */
    char service[64];           /* where the link goes, in words */
    char problem[NET2_TEXT];    /* why the link is not up, in words; empty when it is */
    net2_character character;   /* what I told the service I am playing */
    int new_identity;           /* 1: the identity file was made in this run (a first start) */
} net2_me_t;
void net2_me(net2* n, net2_me_t* out);

int net2_set_name(net2* n, const char* name);           /* 3..24 bytes; a label */
/* The character I am playing (name, class, level: read from the game - gamestate.h's local
   player - or from the card).  NULL: none.  The service passes it on as a label. */
int net2_set_character(net2* n, const net2_character* character);
/* Where I am, for my friends: "in a game" with the level's name, or (NULL / "") not in one.
   In a room / online / offline the service knows by itself. */
int net2_set_game(net2* n, const char* level);
/* The characters saved on this computer's memory card (for a "characters I have" list):
   the characters in the save slots under card_dir - the native program's <data>/card, the
   emulator application's <data>/vfs.  Read from the files; no game needed; nothing is
   sent.  Returns how many were written to out (0: no saved game there yet - a character
   is on the card once the player has saved at a save point).  The mock, asked with a NULL
   card_dir, gives three made-up ones. */
int net2_local_characters(net2* n, const char* card_dir, net2_character* out, int max);
/* Everything the service holds about me - name, friend links both ways, requests, blocks,
   recent players, presence - is deleted there, and the identity file here.  Answered with
   NET2_EV_DELETED; after it this object is a new, unregistered player. */
int net2_delete_everything(net2* n);

/* ---- friends, presence ---------------------------------------------------------------- */
enum { NET2_OFFLINE = 0, NET2_ONLINE = 1, NET2_IN_ROOM = 2, NET2_IN_GAME = 3 };

typedef struct net2_friend {
    char id[NET2_ID];
    char name[NET2_NAME];
    char friend_code[NET2_FRIEND_CODE];
    int presence;               /* NET2_OFFLINE .. NET2_IN_GAME */
    char room[NET2_ROOM_CODE];  /* IN_ROOM: the room's code, when it may be joined from the list */
    int joinable;               /* IN_ROOM: 1 = net2_join_friend() will work (open to friends, not full) */
    int room_players;           /* IN_ROOM / IN_GAME: how many are in it */
    char level[NET2_LEVEL];     /* IN_GAME: the level's name */
    int64_t since;              /* IN_ROOM / IN_GAME / ONLINE: since when, seconds since 1970 */
    int64_t last_seen;          /* OFFLINE: when last online, seconds since 1970 (0: never seen) */
    net2_character character;   /* what they say they are playing (empty name: nothing said) */
    int invited_me;             /* 1: an invitation from them is waiting (net2_invites) */
    int is_friend;              /* recent players: 1 = already a friend */
    int request_sent;           /* recent players: 1 = I have asked already */
} net2_friend;
int net2_friends(net2* n, net2_friend* out, int max);   /* online first, then by name; returns the count */
int net2_recent(net2* n, net2_friend* out, int max);    /* people I was in a game with, newest first */
int net2_blocked(net2* n, net2_friend* out, int max);   /* id and name only */

typedef struct net2_request {
    char id[NET2_ID];
    char name[NET2_NAME];
    char friend_code[NET2_FRIEND_CODE];
    int incoming;               /* 1: they ask me (accept / decline); 0: I asked them (waiting) */
    int64_t when;
} net2_request;
int net2_requests(net2* n, net2_request* out, int max);

int net2_friend_add(net2* n, const char* friend_code);  /* asks; they must accept ("K7QF2MXD" or "k7qf-2mxd" too) */
int net2_friend_add_id(net2* n, const char* id);        /* the same for somebody on the recent list */
int net2_friend_accept(net2* n, const char* id);
int net2_friend_decline(net2* n, const char* id);
int net2_friend_remove(net2* n, const char* id);        /* both directions; the other side is not told */
int net2_block(net2* n, const char* id);                /* removes the friendship; they see me offline,
                                                           cannot ask, invite or join me by the list */
int net2_unblock(net2* n, const char* id);

/* ---- invitations ---------------------------------------------------------------------- */
typedef struct net2_invite_t {
    char from_id[NET2_ID];
    char from_name[NET2_NAME];
    char room[NET2_ROOM_CODE];
    int room_players;
    net2_character character;   /* the inviter's */
    int64_t when;
} net2_invite_t;
int net2_invites(net2* n, net2_invite_t* out, int max);
int net2_invite(net2* n, const char* friend_id);        /* to my room; they get NET2_EV_INVITE */
int net2_invite_accept(net2* n, const char* from_id);   /* one press: joins that room */
int net2_invite_dismiss(net2* n, const char* from_id);

/* ---- a room ---------------------------------------------------------------------------- */
enum {
    NET2_ROOM_NONE = 0,
    NET2_ROOM_JOINING = 1,      /* asked for (host or join), no answer yet */
    NET2_ROOM_OPEN = 2,         /* in it: chat, ready marks */
    NET2_ROOM_STARTING = 3,     /* the host pressed start: the machines are finding each other */
    NET2_ROOM_IN_GAME = 4       /* the game runs */
};
enum { NET2_ROUTE_NONE = 0, NET2_ROUTE_TRYING = 1, NET2_ROUTE_DIRECT = 2, NET2_ROUTE_RELAY = 3, NET2_ROUTE_SELF = 4 };
enum { NET2_OPEN_CODE = 0,      /* whoever has the code */
       NET2_OPEN_FRIENDS = 1 }; /* and: my friends see it as joinable and may walk in */

typedef struct net2_options {
    char level[NET2_LEVEL];     /* where the game starts; "" = the game's own start (the hub).  A name of
                                   the game's level table ("drunare"): the first level is that one */
    int difficulty;             /* the game's own four: 1 easy, 2 normal, 3 hard, 4 harder (its menu keys
                                   menu_easy2 .. menu_harder2); 0 = normal.  The game lets a host choose
                                   only what its own memory card has unlocked: more is cut down by it */
    int mode;                   /* the game's own three: 0 play missions (the campaign, co-operative),
                                   1 arena co-operative, 2 arena versus */
    int open_to;                /* NET2_OPEN_* */
    int mission;                /* mode 0: 0 = from the hub as the host's progress has it; 1..13 the
                                   game's "menu_mis1".."menu_mis13" (what its own net menu offers a host) */
    int kill_limit;             /* mode 2: 5, 10 or 25 (the game's own three); 0 = 5 */
} net2_options;

typedef struct net2_member {
    int slot;                   /* 0..3: the player number in the game; the host of a new room is 0 */
    char id[NET2_ID];
    char name[NET2_NAME];
    net2_character character;
    int ready;
    int host;
    int me;
    int is_friend;
    uint32_t fix_set;           /* what their copy said about itself; 0 = said nothing */
    uint16_t fix_words;
    uint8_t arith_can, arith_does;
    int route;                  /* NET2_ROUTE_*: how this machine reaches them (after start) */
    int rtt_ms;                 /* measured on that route; -1 not yet */
    int phase;                  /* 0 in the room, 1 the game was started for them, 2 their game runs */
} net2_member;

typedef struct net2_chat_line {
    uint32_t number;            /* counts up in the room */
    char from[NET2_NAME];       /* empty: a line of the room itself ("... joined") */
    char text[NET2_TEXT];
} net2_chat_line;

typedef struct net2_room_t {
    int state;                  /* NET2_ROOM_* */
    char code[NET2_ROOM_CODE];
    int count;
    int my_slot, host_slot;
    net2_member members[NET2_PLAYERS];      /* `count` of them, by slot */
    net2_options options;
    int all_ready;              /* everybody but the host has the mark (the host's start is its mark) */
    int mismatch;               /* 1: the copies would fall out of step - do not start (warning says why) */
    char warning[NET2_TEXT];
    int chat_count;             /* lines kept, oldest first */
    net2_chat_line chat[NET2_CHAT_LINES];
} net2_room_t;
void net2_room(net2* n, net2_room_t* out);

int net2_host(net2* n, const net2_options* options);    /* a new room; its code arrives with NET2_EV_ROOM */
int net2_join(net2* n, const char* code);
int net2_join_friend(net2* n, const char* friend_id);   /* their joinable room, from the list */
int net2_chat(net2* n, const char* text);
int net2_ready(net2* n, int ready);
int net2_set_options(net2* n, const net2_options* options);     /* host only */
int net2_kick(net2* n, int slot);                       /* host only, before the start */
int net2_start(net2* n);                                /* host only; everybody gets NET2_EV_START */
int net2_leave(net2* n);

/* ---- the game that was started ---------------------------------------------------------- */
/* The same on every machine of the room (but for my_slot): this is what the direct launch
   (tools/recomp/net2/launch.cpp) hands to the game. */
typedef struct net2_session_t {
    int valid;
    uint32_t session;           /* a number for this start; also marks the datagrams */
    int count, my_slot, host_slot;
    struct {
        char id[NET2_ID];
        char name[NET2_NAME];
        net2_character character;
    } players[NET2_PLAYERS];
    net2_options options;
    uint32_t seed;              /* 0: the game's own (a net game starts its shared seed at 0) */
} net2_session_t;
void net2_session(net2* n, net2_session_t* out);
/* The program tells the room what became of the start: the game runs (level name), or it
   is over / the launch failed (NULL).  Presence follows. */
int net2_game_state(net2* n, const char* level);

/* ---- tests ------------------------------------------------------------------------------ */
/* One line of text a test or a debug overlay can ask for: "link", "udp", "routes", "limits". */
int net2_debug(net2* n, const char* what, char* out, int size);
/* key=value settings for tests: "relay=force" (never use a direct route), "relay=never",
   "mock-speed=4" ... returns NET2_ERR_ARGUMENT for a key it does not know. */
int net2_set(net2* n, const char* key, const char* value);
const char* net2_error_text(int code);

#ifdef __cplusplus
}
#endif
#endif
