// rta_net2_api.h - where RtaNet2's net2_* functions come from (tools/recomp/net2/session.h, game.h).
//
// There must be ONE session object in the process (docs/issues/native-rendezvous.md 5.1): the game library
// carries net2 - the session client, the carrier of the game's datagrams and the direct launch (launch.cpp, which
// follows the room of the object given to net2_game_attach) - and exports its plain-C functions under their own
// names.  So by default (CMake option RTA_GODOT_NET2_SERVICE=ON: RTA_GODOT_NET2_LIBRARY) the extension compiles
// none of net2 and takes the functions from the loaded game library by name.  With the option OFF it compiles its
// own copy of the session code with NET2_NO_SERVICE - the mock only, no socket code, no game - for tests of the
// portal without a game library.  Either way rta_net2.cpp calls through this table.
#pragma once
#include "game.h"
#include "session.h"

#include <string>

// every function RtaNet2 calls; all of them must be there
#define RTA_NET2_FUNCTIONS(F)                                                                                                   \
    F(net2_open) F(net2_close) F(net2_poll) F(net2_next_event) F(net2_me) F(net2_set_name) F(net2_set_character) F(net2_set_game) \
    F(net2_local_characters) F(net2_delete_everything) F(net2_friends) F(net2_recent) F(net2_blocked) F(net2_requests)           \
    F(net2_friend_add) F(net2_friend_add_id) F(net2_friend_accept) F(net2_friend_decline) F(net2_friend_remove) F(net2_block)    \
    F(net2_unblock) F(net2_invites) F(net2_invite) F(net2_invite_accept) F(net2_invite_dismiss) F(net2_room) F(net2_host)        \
    F(net2_join) F(net2_join_friend) F(net2_chat) F(net2_ready) F(net2_set_options) F(net2_kick) F(net2_start) F(net2_leave)     \
    F(net2_session) F(net2_game_state) F(net2_debug) F(net2_set) F(net2_error_text)
// the game's side (game.h): only a game library has them
#define RTA_NET2_GAME_FUNCTIONS(F) \
    F(net2_game_attach) F(net2_game_status) F(net2_game_choose) F(net2_game_launch) F(net2_game_stop)

struct RtaNet2Api {
#define RTA_NET2_MEMBER(name) decltype(&::name) name = nullptr;
    RTA_NET2_FUNCTIONS(RTA_NET2_MEMBER)
    RTA_NET2_GAME_FUNCTIONS(RTA_NET2_MEMBER)
#undef RTA_NET2_MEMBER
    bool ready = false;
    bool from_library = false;          // the game library's (one session object per process) - else the extension's own mock
    std::string error;
};
