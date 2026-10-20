// hooks.h - the four places where tools/recomp/net/netdrv.cpp lets tools/recomp/net2 in
// (the lines are tools/recomp/net2/net2.patch).  Each is a pointer that is null in a
// program that does not link net2/launch.cpp: such a program behaves as before.
//
//   blank        once per vertical blank, on the thread that reads the controller (sockets
//                are looked at here; no game code may be called)
//   tasks        before every pass of the game's run tasks (tasks_run 0x3226e4), on the
//                game's main thread with its register context: the one place from which
//                net2 calls the game's own functions.  `from_tick` is true for the call
//                made by net_frameLoop (one lockstep tick), false for the main loop's own
//                call (front end, offline play)
//   udp_owns     true: net2 carries the datagrams of this UDP port of the game (a game
//                started from a net2 room); netdrv then neither sends nor receives on it
//   udp_send / udp_receive   the two directions; addresses are the game's (host byte order)
#pragma once
#include <cstddef>
#include <cstdint>

struct Ctx;

namespace net2hook {
inline void (*blank)(uint64_t number) = nullptr;
inline void (*tasks)(Ctx* c, bool from_tick) = nullptr;
inline void (*after)(Ctx* c, bool from_tick) = nullptr;       // the same pass has returned
inline bool (*udp_owns)(uint16_t game_port) = nullptr;
inline int32_t (*udp_send)(uint16_t game_port, const uint8_t* data, uint32_t length, uint32_t dest_ip, uint16_t dest_port) = nullptr;
inline bool (*udp_receive)(uint16_t game_port, uint8_t* buffer, size_t capacity, size_t& size, uint32_t& shown_ip, uint16_t& from_port) = nullptr;
// The souls-style combat mode (tools/recomp/app/soulscombat.h), a room option: null in a program without it.
//   souls_wanted   1 / 0: what this copy is set to (folded into the copy's description: fix_words bit 0x8000)
//   souls_want     a joiner takes the host's choice
//   souls_figure   folded into the copy's fix-set figure while the mode is wanted (its numbers must be the same everywhere)
//   souls_room     the launched game's mode (1 / 0), or -1 when the room's game is over
inline int (*souls_wanted)() = nullptr;
inline void (*souls_want)(bool on) = nullptr;
inline uint32_t (*souls_figure)() = nullptr;
inline void (*souls_room)(int on) = nullptr;
}  // namespace net2hook
