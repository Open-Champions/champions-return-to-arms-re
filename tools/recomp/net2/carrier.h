// carrier.h - the datagrams of a game started from a room: one UDP socket, a route to every
// other player (straight, found by hole punching, or through the service's relay), and the
// eight bytes in front of every datagram that say whose it is.
//
// On the wire (all numbers little-endian; docs/issues/native-rendezvous.md, "Datagrams"):
//
//   'N' '2' kind slot  session(4)  ...
//
//   kind 0x01  GAME     slot = the sender's player number; then the game's own datagram
//        0x02  PROBE    slot = the sender's; then nonce(8)          "can you hear me"
//        0x03  ANSWER   slot = the sender's; then the nonce(8)      "I heard you"
//        0x10  RELAY    slot = the player it is for; then key(8), then the game's datagram -
//                       sent to the service, which passes it on as
//        0x11  RELAYED  slot = the sender's; then the game's datagram
//        0x20  HELLO    slot 0, session 0; then key(8): to the service, which learns the
//                       address this socket is seen at and answers
//        0x21  SEEN     slot 0, session 0; then ip(4, a.b.c.d) port(2): "this is how I see you"
//
// The tunnel (docs/issues/native-rendezvous.md, "The fallback"): on a network that lets no
// UDP through to the service, HELLO and RELAY are not sent as datagrams but handed to the
// session (tunnel_out), which sends them in its TCP conversation as `dg d=<hex>`; what the
// service sends back that way (SEEN, RELAYED) is given to inject().  Straight routes to
// other players are still tried over UDP.
//
// The game is given made-up addresses: player k is 10.77.0.(k+1), port 4000, on every
// machine alike.  It never sees a real address, so nothing in its launch code can mistake
// one player for another (docs/issues/three-players.md, cause 1) and a route can change
// from relay to straight without the game knowing.
#pragma once
#include "session.h"

#include <cstdint>
#include <deque>
#include <string>
#include <vector>

namespace n2 {

const uint8_t KIND_GAME = 0x01, KIND_PROBE = 0x02, KIND_ANSWER = 0x03, KIND_RELAY = 0x10, KIND_RELAYED = 0x11,
              KIND_HELLO = 0x20, KIND_SEEN = 0x21;
const size_t HEAD = 8;
const size_t MOST = 2048;               // the game's largest datagram is 1984 bytes (0x7c0)
const uint32_t GAME_NET = 0x0A4D0001;   // 10.77.0.1: player 0, as the game is told
const uint16_t GAME_PORT = 4000;

struct Endpoint {
    uint32_t ip = 0;                    // host byte order
    uint16_t port = 0;
    bool operator==(const Endpoint& o) const { return ip == o.ip && port == o.port; }
    bool set() const { return ip != 0 && port != 0; }
};
bool parse_endpoint(const std::string& text, Endpoint& out);    // "a.b.c.d:port" (a name is looked up)
std::string endpoint_text(const Endpoint& e);

enum { RELAY_AUTO = 0, RELAY_FORCE = 1, RELAY_NEVER = 2 };

struct Carrier {
    Carrier();
    ~Carrier();
    // the socket: opened on the first call; "" or "0.0.0.0:0" any address, any port
    bool open(const std::string& bind_to, std::string& problem);
    void close();
    bool is_open() const;
    Endpoint local() const;

    // a session: forgets the routes of the one before
    void begin(uint32_t session, int count, int my_slot);
    void end();                         // datagrams of the game are no longer carried
    bool active() const { return count_ > 0; }
    void fixed(int slot, const Endpoint& where);                        // a known address: no punching
    void candidates(int slot, const std::vector<Endpoint>& where);      // punch toward these
    void relay(const Endpoint& service, const uint8_t key[8]);          // the fallback
    void policy(int relay_policy) { policy_ = relay_policy; }

    void poll(int64_t now_ms);          // reads the socket, probes, decides routes
    bool send(int to_slot, const uint8_t* data, size_t size);
    int receive(int& from_slot, uint8_t* into, size_t capacity);       // bytes; -1: nothing waits

    // to the service from the same socket (so that it sees the address players must send to)
    void hello(const Endpoint& service, const uint8_t key[8]);
    Endpoint seen_as() const { return seen_; }      // what the service answered; unset until then
    bool answered(int64_t now_ms) const { return answered_at_ && now_ms - answered_at_ <= 8000; }
    void reset_seen() { answered_at_ = 0; seen_ = Endpoint{}; }

    // the tunnel: hello and relay in the session's conversation instead of UDP
    void tunnel(bool on) { tunnel_ = on; if (!on) tunnel_out.clear(); }
    bool tunnelled() const { return tunnel_; }
    std::deque<std::vector<uint8_t>> tunnel_out;    // whole datagrams for the service, oldest first
    void inject(const uint8_t* data, size_t size, int64_t now_ms);     // one the service sent in the conversation
    uint64_t tunnelled_out = 0, tunnelled_in = 0;

    int route(int slot) const;          // NET2_ROUTE_*
    int rtt(int slot) const;
    bool routes_ready() const;          // every other player has a route that is not "trying"
    std::string text() const;           // one line for a log
    uint64_t sent = 0, received = 0, relayed_out = 0, relayed_in = 0, strays = 0;

  private:
    struct Peer {
        int state = NET2_ROUTE_NONE;
        Endpoint direct;
        std::vector<Endpoint> tries;
        int64_t since = 0, last_probe = 0, last_heard = 0;
        uint64_t nonces[16] = {0};      // the probes in flight: an answer may come after the next probe has gone
        int64_t sent_at[16] = {0};
        unsigned next = 0;
        int rtt = -1;
    };
    struct Datagram { int from; std::vector<uint8_t> data; };
    int fd_ = -1;
    uint32_t session_ = 0;
    int count_ = 0, me_ = 0, policy_ = RELAY_AUTO;
    Peer peers_[NET2_PLAYERS];
    Endpoint service_, seen_;
    uint8_t key_[8] = {0};
    bool relay_ok_ = false, tunnel_ = false, no_udp_ = false;
    int64_t answered_at_ = 0;           // the last valid reply in this service connection
    std::deque<Datagram> queue_;
    void take(const Endpoint& from, bool from_service, const uint8_t* in, size_t got, int64_t now);
    void raw(const Endpoint& to, uint8_t kind, uint8_t slot, uint32_t session, const uint8_t* a, size_t an, const uint8_t* b = nullptr, size_t bn = 0);
};

}  // namespace n2
