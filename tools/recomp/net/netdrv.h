// netdrv.h - the native build's network, as the rest of an application sees it.
//
// netdrv.cpp supplies the game's entries into Sony's network library and into the network
// configuration clients (tools/recomp/net/hle-online.txt) on host sockets; online.cpp
// drives the game's own screens to the lobby (the "one-step online" of the emulator-based
// application, tools/play-net/src/RtaOnline.cpp, linked as it is).  Both are set up from
// the game's main() by themselves; an application only links them and passes options:
//
//   --opt net-server=ADDRESS     the lobby server: IPv4 address or host name (left out,
//                                "localhost" or a loop-back address: a server on this computer)
//   --opt net-server-public=A    the server's public address, when it hands that out and
//                                you are on its own network (normally found by itself)
//   --opt net-data=DIR           where the saved login, the character used last and this
//                                copy's made-up address are kept (default: app-data beside bin/)
//   --opt net-card=DIR           the memory card directory (default: <net-data>/card); the
//                                network setting is written to its mc0 when it is missing
//   --opt net-netcnf=0           do not write the network setting
//   --opt net-addr=198.19.x.y    the machine's own-network address (default: made once, kept)
//   --opt net-loopback=on|off    other copies on this computer are reached through the
//                                loop-back interface (default: on when the server is here)
//   --opt net-ports=0            do not ask for host UDP ports with the game's numbers
//   --opt net-set-quiet=1        do not tell the other players this copy's patch set
//   --opt net-local-only=1       tests: nothing is sent to an address that is not this
//                                computer's
//   --opt net-pace=HZ            a program without a window: vertical blanks per second of
//                                real time (default 59.94; 0: as fast as it goes)
//   --opt net-log=FILE           one line per event (addresses, ports, sizes; never text)
//   --opt net-log-all=1          every library call in that file
//   --opt tick-log=FILE --opt tick-watch-file=FILE   the rig's tick log (tests)
//   --opt online=lobby|host[:CODE]|join:CODE[+choose]   go online by itself from power-on
//   --opt online-name=NAME[,NAME...]   tests: the player name(s), instead of asking
//   --opt online-person=0        nobody can answer a question (a background test)
//
// docs/issues/native-online.md has the design and what was run.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace rtanet {

struct Peer {
    uint32_t ip = 0;            // as the host sees it, host byte order
    uint16_t port = 0;
    bool set_known = false;     // it has said which patch set it has
    uint32_t patch_set = 0;
    uint16_t patch_words = 0;
    int64_t heard_ms = 0, silent_ms = 0;
};

struct Info {
    bool configured = false;
    std::string server_text;    // the server in words
    std::string server_key;     // what the logins are saved under: the address as given
    uint32_t server_ip = 0;     // as the host reaches it
    uint32_t guest_server_ip = 0;   // as the game is told
    uint32_t guest_ip = 0;      // the machine's own-network address
    bool loopback_peers = false;
    uint32_t patch_set = 0;     // FNV-1a of the fix set's words, as the application shows it
    unsigned patch_words = 0;
    std::string data_dir, card_dir;
    uint64_t tcp_connections = 0, tcp_out = 0, tcp_in = 0;
    uint64_t udp_to_server = 0, udp_from_server = 0, udp_to_peers = 0, udp_from_peers = 0, dropped = 0;
};

void setup();                           // idempotent; from the game's main()
void per_blank(uint64_t number);        // once per vertical blank, on the game's thread
const Info& info();
std::vector<Peer> peers();
std::string ip_text(uint32_t ip);
void log(const char* format, ...);      // to net-log and, for the lines worth it, the terminal
void say(const char* format, ...);      // always to the terminal as well
void drop_tcp();                        // tests: the line to the server is cut

// online.cpp
void online_install();                  // from the game's main(), after setup()
std::string online_note();              // one line for a status display; empty: nothing to say
std::string online_report();            // stage and outcome in words; never a name or a password

// An application with a window may take these over (set before rta::run); without them a
// name is asked for on the terminal and the code is printed there.
extern void (*ask_name)(const std::string& why);        // answer with give_name / decline_name
extern void (*show_code)(const std::string& code);
extern void (*show_note)(const std::string& note);      // when the note changes
void give_name(const std::string& name);
void decline_name();
std::string check_name(const std::string& name);        // empty: fine

}  // namespace rtanet
