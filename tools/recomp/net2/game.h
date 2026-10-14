/* game.h - the direct launch: the game's own lockstep session started from a small
 * description, with no lobby screen.  For a program that contains the translated game
 * (tools/recomp/net2/launch.cpp is linked into it; a portal without the game does not need
 * this file).
 *
 * How it goes (docs/issues/native-rendezvous.md, "The direct launch"):
 *   - the game stands at its title screen;
 *   - net2_game_choose(): the game's own character screens come up (make a character, or
 *     "Import" one from this machine's memory card) - no account, no lobby;
 *   - net2_game_launch(): the game's own launch handshake (the one a lobby game runs after
 *     Start: each machine sends the others its character) between the players of the
 *     description, then the first level loads and the lockstep game runs;
 *   - when the game is over the machine is back at its title screen and the next
 *     net2_game_choose / net2_game_launch can follow.
 * All calls are requests: they return at once and are carried out by the game's own
 * thread at its next pass; net2_game_status() says where things are.
 */
#ifndef RTA_NET2_GAME_H
#define RTA_NET2_GAME_H
#include "session.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    NET2_GAME_BOOTING = 0,      /* the game has not reached its title screen yet */
    NET2_GAME_TITLE = 1,        /* at the title screen: nothing chosen */
    NET2_GAME_CHOOSING = 2,     /* the game's character screens are up */
    NET2_GAME_CHOSEN = 3,       /* a character is chosen: a launch can follow */
    NET2_GAME_LAUNCHING = 4,    /* the launch handshake runs */
    NET2_GAME_LOADING = 5,      /* launched: the first level loads */
    NET2_GAME_RUNNING = 6,      /* lockstep ticks run */
    NET2_GAME_BUSY = 7          /* the game is somewhere else (an offline game, the old lobby) */
};

typedef struct net2_game_status_t {
    int phase;                  /* NET2_GAME_* */
    int launches;               /* launches that reached a level, in this run of the program */
    int failed;                 /* 1: the last launch or choice ended without a game (text says why) */
    char text[NET2_TEXT];       /* where things are, in words */
    net2_character character;   /* CHOSEN and later: the local player's character, read from the game */
    char level[NET2_LEVEL];     /* RUNNING: the level's name */
    uint32_t tick;              /* RUNNING: the lockstep tick */
    int players;                /* RUNNING: players still in the game */
    int difficulty_unlocked;    /* the highest difficulty the game's own menu would offer a host on this
                                   machine (1 on a new memory card; its options record 0x4f8f38) */
} net2_game_status_t;
void net2_game_status(net2_game_status_t* out);

/* The game's character screens.  `as_host` only decides what the game shows around them. */
int net2_game_choose(int as_host);

/* One player of a direct launch by fixed addresses (no service): where its datagrams go. */
typedef struct net2_direct_player {
    char name[NET2_NAME];
    char address[48];           /* "192.168.1.20:41930" */
} net2_direct_player;
typedef struct net2_direct {
    uint32_t session;           /* any number, the same on every machine */
    int count, my_slot, host_slot;
    net2_direct_player players[NET2_PLAYERS];
    net2_options options;
    char bind[48];              /* this machine's own "address:port" to listen on ("" = players[my_slot]) */
} net2_direct;
int net2_game_launch_direct(const net2_direct* description);

/* The launch of a room's game: the description and the routes come from the session object
   (after NET2_EV_START).  launch.cpp does this by itself for the object given to
   net2_game_attach(); a host program only calls attach once. */
void net2_game_attach(net2* n);
int net2_game_launch(net2* n);

/* Leave: a launch under way is cancelled; a running game is left as the pause menu's
   "Exit Game" leaves it. */
int net2_game_stop(void);

#ifdef __cplusplus
}
#endif
#endif
