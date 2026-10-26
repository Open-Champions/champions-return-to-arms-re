// carrier.cpp - see carrier.h.
#include "carrier.h"

#include "../net/sock.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>

namespace n2 {

namespace {
const int64_t PROBE_EVERY_MS = 200;     // while a route is being tried
const int64_t DECIDE_AFTER_MS = 2500;   // no answer by then: the relay (when there is one)
const int64_t GIVE_UP_MS = 12000;       // probes stop; a straight route found later is still taken
const int64_t KEEP_PROBE_MS = 5000;     // a straight route in use is measured now and then

uint64_t random64() {
    static std::mt19937_64 gen{std::random_device{}() ^ (uint64_t)std::chrono::steady_clock::now().time_since_epoch().count()};
    return gen();
}
void put32(uint8_t* p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
uint32_t get32(const uint8_t* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }
}  // namespace

bool parse_endpoint(const std::string& text, Endpoint& out) {
    size_t colon = text.rfind(':');
    if (colon == std::string::npos) return false;
    std::string host = text.substr(0, colon);
    int port = atoi(text.c_str() + colon + 1);
    if (port <= 0 || port > 65535) return false;
    unsigned a, b, c, d;
    char tail;
    uint32_t ip = 0;
    if (sscanf(host.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) == 4 && a < 256 && b < 256 && c < 256 && d < 256)
        ip = (a << 24) | (b << 16) | (c << 8) | d;
    else if (host == "localhost") ip = 0x7F000001;
    else if (!sock::resolve(host, ip)) return false;
    out.ip = ip;
    out.port = (uint16_t)port;
    return true;
}

std::string endpoint_text(const Endpoint& e) {
    char text[32];
    snprintf(text, sizeof text, "%u.%u.%u.%u:%u", e.ip >> 24, (e.ip >> 16) & 255, (e.ip >> 8) & 255, e.ip & 255, e.port);
    return text;
}

Carrier::Carrier() {
    // tests: a network that lets no UDP out (every datagram this socket would send is dropped)
    const char* test = getenv("RTA_NET2_TEST_NO_UDP");
    no_udp_ = test && *test && *test != '0';
}
Carrier::~Carrier() { close(); }

bool Carrier::open(const std::string& bind_to, std::string& problem) {
    if (fd_ != -1) return true;
    sock::start();
    Endpoint where;
    if (!bind_to.empty() && !parse_endpoint(bind_to, where)) {
        // "a.b.c.d:0" does not parse as an endpoint with a port: take the address alone
        size_t colon = bind_to.rfind(':');
        Endpoint probe;
        if (colon == std::string::npos || !parse_endpoint(bind_to.substr(0, colon) + ":1", probe)) { problem = "cannot listen on " + bind_to; return false; }
        where.ip = probe.ip;
        where.port = (uint16_t)atoi(bind_to.c_str() + colon + 1);
    }
    sock::Handle fd = sock::udp();
    if (fd == sock::NONE) { problem = "no UDP socket: " + sock::error_text(sock::error()); return false; }
    sockaddr_in address = sock::address_of(where.ip, where.port);
    if (::bind(fd, (const sockaddr*)&address, sizeof address) != 0) {
        problem = "cannot listen on " + (bind_to.empty() ? std::string("a UDP port") : bind_to) + ": " + sock::error_text(sock::error());
        sock::close(fd);
        return false;
    }
    sock::non_blocking(fd);
    sock::receive_buffer(fd, 512 * 1024);
    fd_ = (int)fd;
    return true;
}

void Carrier::close() {
    if (fd_ != -1) sock::close((sock::Handle)fd_);
    fd_ = -1;
    reset_seen();
    end();
}
bool Carrier::is_open() const { return fd_ != -1; }

Endpoint Carrier::local() const {
    Endpoint e;
    if (fd_ == -1) return e;
    sockaddr_in address{};
    socklen_t size = sizeof address;
    if (getsockname((sock::Handle)fd_, (sockaddr*)&address, &size) == 0) {
        e.ip = ntohl(address.sin_addr.s_addr);
        e.port = ntohs(address.sin_port);
    }
    return e;
}

void Carrier::begin(uint32_t session, int count, int my_slot) {
    session_ = session;
    count_ = count < 0 ? 0 : count > NET2_PLAYERS ? NET2_PLAYERS : count;
    me_ = my_slot;
    for (Peer& p : peers_) p = Peer();
    if (me_ >= 0 && me_ < NET2_PLAYERS) peers_[me_].state = NET2_ROUTE_SELF;
    queue_.clear();
    relay_ok_ = false;
}

void Carrier::end() {
    count_ = 0;
    session_ = 0;
    queue_.clear();
    for (Peer& p : peers_) p = Peer();
}

void Carrier::fixed(int slot, const Endpoint& where) {
    if (slot < 0 || slot >= NET2_PLAYERS || slot == me_) return;
    peers_[slot].state = NET2_ROUTE_DIRECT;
    peers_[slot].direct = where;
}

void Carrier::candidates(int slot, const std::vector<Endpoint>& where) {
    if (slot < 0 || slot >= NET2_PLAYERS || slot == me_) return;
    Peer& p = peers_[slot];
    p.tries.clear();
    for (const Endpoint& e : where)
        if (e.set() && p.tries.size() < 6) p.tries.push_back(e);
    p.state = NET2_ROUTE_TRYING;
    p.since = 0;
    p.last_probe = 0;
}

void Carrier::relay(const Endpoint& service, const uint8_t key[8]) {
    service_ = service;
    memcpy(key_, key, 8);
    relay_ok_ = service.set();
}

void Carrier::raw(const Endpoint& to, uint8_t kind, uint8_t slot, uint32_t session, const uint8_t* a, size_t an, const uint8_t* b, size_t bn) {
    if (fd_ == -1 || HEAD + an + bn > MOST + 32) return;
    bool to_tunnel = tunnel_ && (kind == KIND_HELLO || kind == KIND_RELAY);
    if (!to_tunnel && !to.set()) return;
    uint8_t out[MOST + 64];
    out[0] = 'N';
    out[1] = '2';
    out[2] = kind;
    out[3] = slot;
    put32(out + 4, session);
    if (an) memcpy(out + HEAD, a, an);
    if (bn) memcpy(out + HEAD + an, b, bn);
    if (to_tunnel) {
        if (tunnel_out.size() < 512) tunnel_out.emplace_back(out, out + HEAD + an + bn);
        tunnelled_out++;
        return;
    }
    if (no_udp_) return;
    sock::send_to((sock::Handle)fd_, out, HEAD + an + bn, to.ip, to.port);
}

void Carrier::inject(const uint8_t* data, size_t size, int64_t now) {
    if (size > MOST + 64) return;
    tunnelled_in++;
    take(service_, true, data, size, now);
}

void Carrier::hello(const Endpoint& service, const uint8_t key[8]) {
    if (!(service_ == service)) reset_seen();
    service_ = service;
    raw(service, KIND_HELLO, 0, 0, key, 8);
}

bool Carrier::send(int to_slot, const uint8_t* data, size_t size) {
    if (to_slot < 0 || to_slot >= count_ || to_slot == me_ || size > MOST) return false;
    Peer& p = peers_[to_slot];
    if (p.state == NET2_ROUTE_DIRECT) {
        raw(p.direct, KIND_GAME, (uint8_t)me_, session_, data, size);
        sent++;
        return true;
    }
    if ((p.state == NET2_ROUTE_RELAY || p.state == NET2_ROUTE_TRYING) && relay_ok_ && policy_ != RELAY_NEVER) {
        // while a straight route is still being tried the relay already carries the game:
        // nothing waits for the punching
        raw(service_, KIND_RELAY, (uint8_t)to_slot, session_, key_, 8, data, size);
        sent++;
        relayed_out++;
        return true;
    }
    return false;
}

int Carrier::receive(int& from_slot, uint8_t* into, size_t capacity) {
    if (queue_.empty()) return -1;
    Datagram& d = queue_.front();
    size_t size = d.data.size() < capacity ? d.data.size() : capacity;
    memcpy(into, d.data.data(), size);
    from_slot = d.from;
    queue_.pop_front();
    return (int)size;
}

void Carrier::take(const Endpoint& from, bool from_service, const uint8_t* in, size_t got, int64_t now) {
    if (got < HEAD || in[0] != 'N' || in[1] != '2') { strays++; return; }
    uint8_t kind = in[2];
    int slot = in[3];
    uint32_t session = get32(in + 4);
    const uint8_t* body = in + HEAD;
    size_t size = got - HEAD;
    if (kind == KIND_SEEN) {
        if (from_service && size == 6 && slot == 0 && session == 0) {
            answered_at_ = now;
            // in the tunnel the port is 0: the service saw no UDP socket, only the address
            if (size >= 6 && (body[4] | body[5])) { seen_.ip = ((uint32_t)body[0] << 24) | (body[1] << 16) | (body[2] << 8) | body[3]; seen_.port = (uint16_t)(body[4] | (body[5] << 8)); }
        } else strays++;
        return;
    }
    if (count_ == 0 || session != session_ || slot < 0 || slot >= count_ || slot == me_) { strays++; return; }
    Peer& p = peers_[slot];
    if (kind == KIND_GAME || kind == KIND_RELAYED) {
        if (kind == KIND_RELAYED && !from_service) { strays++; return; }
        if (queue_.size() < 1024) queue_.push_back(Datagram{slot, std::vector<uint8_t>(body, body + size)});
        received++;
        if (kind == KIND_RELAYED) relayed_in++;
        else p.last_heard = now;
    } else if (kind == KIND_PROBE) {
        if (policy_ == RELAY_FORCE || size < 8) return;
        raw(from, KIND_ANSWER, (uint8_t)me_, session_, body, 8);
        // a probe from an address not on the list: the address their router gave this path
        bool known = false;
        for (const Endpoint& e : p.tries) known |= e == from;
        if (!known && p.tries.size() < 8 && p.state != NET2_ROUTE_DIRECT) p.tries.push_back(from);
    } else if (kind == KIND_ANSWER) {
        if (policy_ == RELAY_FORCE || size < 8) return;
        uint64_t nonce;
        memcpy(&nonce, body, 8);
        int found = -1;
        for (int k = 0; k < 16; k++)
            if (nonce && p.nonces[k] == nonce) found = k;
        if (found < 0) return;
        p.rtt = (int)(now - p.sent_at[found]);
        p.nonces[found] = 0;
        p.last_heard = now;
        if (p.state != NET2_ROUTE_DIRECT) {
            p.direct = from;
            p.state = NET2_ROUTE_DIRECT;
        }
    } else strays++;
}

void Carrier::poll(int64_t now) {
    if (fd_ == -1) return;
    uint8_t in[MOST + 64];
    for (int n = 0; n < 256; n++) {
        Endpoint from;
        int got = sock::recv_from((sock::Handle)fd_, in, sizeof in, from.ip, from.port);
        if (got < 0) break;
        if (no_udp_) continue;
        take(from, from == service_, in, (size_t)got, now);
    }
    for (int slot = 0; slot < count_; slot++) {
        if (slot == me_) continue;
        Peer& p = peers_[slot];
        // nothing to punch toward (a player whose datagrams come in its conversation): the relay
        if (p.state == NET2_ROUTE_TRYING && p.tries.empty() && relay_ok_ && policy_ != RELAY_NEVER) p.state = NET2_ROUTE_RELAY;
        if (p.state == NET2_ROUTE_NONE || p.tries.empty()) continue;
        if (p.since == 0) p.since = now;
        if (policy_ == RELAY_FORCE) {
            if (p.state == NET2_ROUTE_TRYING) p.state = relay_ok_ ? NET2_ROUTE_RELAY : NET2_ROUTE_NONE;
            continue;
        }
        int64_t age = now - p.since;
        if (p.state == NET2_ROUTE_TRYING && age > DECIDE_AFTER_MS && relay_ok_ && policy_ != RELAY_NEVER) p.state = NET2_ROUTE_RELAY;
        int64_t every = p.state == NET2_ROUTE_DIRECT ? KEEP_PROBE_MS : PROBE_EVERY_MS;
        if (p.state != NET2_ROUTE_DIRECT && age > GIVE_UP_MS) continue;
        if (now - p.last_probe < every) continue;
        p.last_probe = now;
        unsigned k = p.next++ % 16;
        uint64_t nonce = random64() | 1;
        p.nonces[k] = nonce;
        p.sent_at[k] = now;
        if (p.state == NET2_ROUTE_DIRECT) raw(p.direct, KIND_PROBE, (uint8_t)me_, session_, (const uint8_t*)&nonce, 8);
        else
            for (const Endpoint& e : p.tries) raw(e, KIND_PROBE, (uint8_t)me_, session_, (const uint8_t*)&nonce, 8);
    }
}

int Carrier::route(int slot) const { return slot >= 0 && slot < NET2_PLAYERS ? peers_[slot].state : NET2_ROUTE_NONE; }
int Carrier::rtt(int slot) const { return slot >= 0 && slot < NET2_PLAYERS ? peers_[slot].rtt : -1; }

bool Carrier::routes_ready() const {
    for (int slot = 0; slot < count_; slot++)
        if (slot != me_ && peers_[slot].state != NET2_ROUTE_DIRECT && peers_[slot].state != NET2_ROUTE_RELAY) return false;
    return count_ > 0;
}

std::string Carrier::text() const {
    static const char* NAMES[] = {"none", "trying", "direct", "relay", "self"};
    std::string out;
    char part[96];
    snprintf(part, sizeof part, "session %08x, %d players, I am %d, socket %s", session_, count_, me_, endpoint_text(local()).c_str());
    out = part;
    if (seen_.set()) out += ", seen as " + endpoint_text(seen_);
    if (tunnel_) {
        snprintf(part, sizeof part, ", tunnel (%llu out, %llu in)", (unsigned long long)tunnelled_out, (unsigned long long)tunnelled_in);
        out += part;
    }
    for (int slot = 0; slot < count_; slot++) {
        if (slot == me_) continue;
        const Peer& p = peers_[slot];
        snprintf(part, sizeof part, "; player %d %s", slot, NAMES[p.state]);
        out += part;
        if (p.state == NET2_ROUTE_DIRECT) out += " " + endpoint_text(p.direct);
        if (p.rtt >= 0) { snprintf(part, sizeof part, " %d ms", p.rtt); out += part; }
    }
    snprintf(part, sizeof part, "; %llu sent (%llu by relay), %llu received (%llu by relay), %llu strays", (unsigned long long)sent,
             (unsigned long long)relayed_out, (unsigned long long)received, (unsigned long long)relayed_in, (unsigned long long)strays);
    out += part;
    return out;
}

}  // namespace n2
