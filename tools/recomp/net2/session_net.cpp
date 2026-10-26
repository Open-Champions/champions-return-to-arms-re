// session_net.cpp - the body of session.h that talks to the rendezvous service
// (tools/rendezvous/rendezvous.py; the wire format is in docs/issues/native-rendezvous.md).
//
// Identity.  The first start makes 32 random bytes - the device secret - and keeps them in
// <data_dir>/net2-identity.key (mode 0600).  That file IS the player: copy it to another
// computer and the player is there; lose it and the player is gone (the friends would have
// to be asked again).  The service never gets the secret.  It gets, once, at registration,
//     verifier = HMAC-SHA256(secret, "rta-net2 verifier v1")
// and derives the player id from it; afterwards every connection is proven with
//     proof = HMAC-SHA256(verifier, nonce of this connection + "login").
// What that is and is not: it is not a public-key signature (neither C++ nor Python has
// one in its standard library, and none is written here).  Whoever reads the registration
// on the wire, or the service's file, holds the verifier and could log in as that player.
// A proof read off the wire is worth nothing (the nonce is new for every connection).
// So a service on the Internet has its TCP conversation inside TLS (tls.h: the operating
// system's own TLS, the certificate checked against the system's trust store and the host
// name; plain text only for this computer and a LAN unless told otherwise) - what the
// identity guards is a display name and a friends list.
//
// One TCP connection (lines of text, inside TLS or not), one UDP socket (carrier.h: hello,
// punching, the game's datagrams, the relay).  Nothing blocks: a host name is looked up on
// a thread of its own, everything else is polled.
//
// The fallback (docs/issues/native-rendezvous.md, "The fallback"), for networks that let
// HTTPS out but break TLS to an unknown port, or let no UDP out:
//   - the link: when the direct link (TLS to host:41900) fails before it is up, the next try
//     is the same conversation as a WebSocket on the service's web server,
//     wss://<host>:443/net2 (tls.h ws_link), and so on in turn; a link that came up stays
//     on its way.  "transport" auto | direct | ws (RTA_NET2_TRANSPORT, net2_set), the
//     WebSocket's address "ws" (RTA_NET2_WS, or "wss://host[:port]/path" as the service).
//   - the datagrams: when the service has answered none of this socket's hellos 8 s after
//     the first, hello and relay go in the conversation as `dg d=<hex>` lines (carrier.h,
//     the tunnel), and the relay carries the game.  "udp" auto | tunnel | udp
//     (RTA_NET2_UDP, net2_set).  Tests: RTA_NET2_RELAY=force|never (as net2_set "relay").
#include "carrier.h"
#include "hash.h"
#include "session_impl.h"
#include "tls.h"

#include "../net/sock.h"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <thread>

#include <sys/stat.h>

namespace net2impl {
namespace {

const char* SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-,:";

std::string hex(const uint8_t* data, size_t size) {
    static const char* digits = "0123456789abcdef";
    std::string out;
    for (size_t i = 0; i < size; i++) { out += digits[data[i] >> 4]; out += digits[data[i] & 15]; }
    return out;
}
bool unhex(const std::string& text, uint8_t* out, size_t size) {
    if (text.size() != size * 2) return false;
    for (size_t i = 0; i < size; i++) {
        unsigned v;
        if (sscanf(text.c_str() + i * 2, "%2x", &v) != 1) return false;
        out[i] = (uint8_t)v;
    }
    return true;
}
std::string enc(const std::string& value) {
    std::string out;
    char part[4];
    for (unsigned char c : value) {
        if (strchr(SAFE, c) && c) out += (char)c;
        else { snprintf(part, sizeof part, "%%%02X", c); out += part; }
    }
    return out;
}
std::string dec(const std::string& text) {
    std::string out;
    for (size_t i = 0; i < text.size(); i++) {
        unsigned v;
        if (text[i] == '%' && i + 3 <= text.size() && sscanf(text.c_str() + i + 1, "%2x", &v) == 1 &&
            isxdigit((unsigned char)text[i + 1]) && isxdigit((unsigned char)text[i + 2])) {
            out += (char)v;
            i += 2;
        } else out += text[i];
    }
    return out;
}

typedef std::map<std::string, std::string> Fields;
struct Line {
    std::string verb;
    Fields f;
    std::string get(const char* key) const { auto it = f.find(key); return it == f.end() ? "" : it->second; }
    long num(const char* key) const { return atol(get(key).c_str()); }
};
bool parse_line(const std::string& text, Line& out) {
    std::istringstream words(text);
    std::string word;
    if (!(words >> out.verb)) return false;
    while (words >> word) {
        size_t eq = word.find('=');
        if (eq == std::string::npos || eq == 0) return false;
        out.f[word.substr(0, eq)] = dec(word.substr(eq + 1));
    }
    return true;
}

struct Resolve {            // a host name, looked up off the polling thread
    std::atomic<int> state{0};      // 0 under way, 1 found, 2 not found
    uint32_t ip = 0;
};

struct Net : Backend {
    // set-up
    std::string data_dir, service_text, host_name, first_name, build;
    uint16_t port = 0;
    bool local_only = false;
    uint32_t fix_set = 0;
    uint16_t fix_words = 0;
    uint8_t arith_can = 0, arith_does = 0;
    // identity
    uint8_t secret[32] = {0}, verifier[32] = {0};
    bool have_secret = false, registered_once = false;
    // the link
    sock::Handle fd = sock::NONE;              // the plain link; or
    std::unique_ptr<n2::TlsLink> tls;           // the link inside TLS
    int tls_rule = n2::TLS_AUTO;
    std::string tls_trust;                      // "" the system's trust store; else the only certificates trusted
    enum { WAY_AUTO, WAY_DIRECT, WAY_WS };
    int transport = WAY_AUTO;
    std::string ws_host, ws_path = "/net2";     // the WebSocket's address when it was named ("ws")
    uint16_t ws_port = 0;
    bool ws_tls = true, ws_named = false;
    bool on_ws = false, link_ws = false, ws_told = false;      // the next try / this link is the WebSocket
    enum { UDP_AUTO, UDP_TUNNEL, UDP_ONLY };
    int udp_mode = UDP_AUTO;
    int64_t udp_since = 0;
    bool tunnel_told = false;
    bool linked() const { return fd != sock::NONE || tls != nullptr; }
    enum { IDLE, RESOLVING, CONNECTING, GREETING, PROVING, ONLINE } stage = IDLE;
    std::shared_ptr<Resolve> resolving;
    n2::Endpoint service;
    std::string inbuf, outbuf;
    int64_t next_try = 0, last_heard = 0, last_ping = 0, last_hello = 0, stage_since = 0;
    int tries = 0;
    bool synced = false, fatal = false, tried_register = false;
    unsigned n = 0;
    struct Pending { std::string verb, note; };
    std::map<unsigned, Pending> pending;
    // datagrams
    n2::Carrier carrier_;
    std::string bind_to;
    uint8_t udp_key[8] = {0};
    bool have_key = false, local_sent = false;
    int relay_policy = n2::RELAY_AUTO;
    // a room snapshot and a start being received
    bool in_room_block = false, in_start_block = false;
    net2_room_t incoming{};
    net2_session_t starting{};
    std::vector<std::vector<n2::Endpoint>> start_eps;
    int my_phase = 0;
    bool want_character = false;

    explicit Net(const net2_config& config) {
        sock::start();
        data_dir = config.data_dir ? config.data_dir : "";
        first_name = config.name && *config.name && name_problem(config.name).empty() ? config.name : "Player";
        build = config.build ? config.build : "";
        local_only = config.local_only != 0;
        fix_set = config.fix_set;
        fix_words = config.fix_words;
        arith_can = config.arith_can;
        arith_does = config.arith_does;
        service_text = config.service ? config.service : "";
        put(s.me.name, first_name);
        put(s.me.service, service_text);
        s.me.link = NET2_LINK_CONNECTING;
        put(s.me.problem, "Connecting...");
        // "tls://host:port" and "plain://host:port" say how; "host:port" leaves it to the rule (tls.h)
        std::string address = service_text;
        if (const char* env = getenv("RTA_NET2_WS"))
            if (*env) set_ws(env);
        if (address.compare(0, 6, "wss://") == 0 || address.compare(0, 5, "ws://") == 0) {
            // the service named by its WebSocket: the datagrams go to the same host's port 41900
            set_ws(address);
            transport = WAY_WS;
            address = ws_host + ":41900";
        }
        if (const char* env = getenv("RTA_NET2_TRANSPORT"))
            if (*env) transport = way_of(env, transport);
        if (const char* env = getenv("RTA_NET2_UDP"))
            if (*env) udp_mode = udp_of(env, udp_mode);
        if (const char* env = getenv("RTA_NET2_RELAY"))     // tests: this copy's routes (force | never | auto), as net2_set "relay"
            if (*env) relay_policy = std::string(env) == "force" ? n2::RELAY_FORCE : std::string(env) == "never" ? n2::RELAY_NEVER : n2::RELAY_AUTO;
        if (address.compare(0, 6, "tls://") == 0) { tls_rule = n2::TLS_ON; address = address.substr(6); }
        else if (address.compare(0, 8, "plain://") == 0) { tls_rule = n2::TLS_OFF; address = address.substr(8); }
        if (const char* env = getenv("RTA_NET2_TLS"))
            if (*env && n2::tls_rule(env) >= 0) tls_rule = n2::tls_rule(env);
        if (const char* env = getenv("RTA_NET2_TLS_CA")) tls_trust = env;
        size_t colon = address.rfind(':');
        port = colon == std::string::npos ? 0 : (uint16_t)atoi(address.c_str() + colon + 1);
        host_name = colon == std::string::npos ? address : address.substr(0, colon);
        if (!port || host_name.empty()) stop_for_good("The service's address must be host:port (it is \"" + service_text + "\").");
        load_identity();
    }
    ~Net() override {
        if (linked()) { send_line("leave n=0"); flush(); close_link(); }
    }

    // ---- identity ------------------------------------------------------------------------
    std::string identity_path() const { return data_dir.empty() ? "" : data_dir + "/net2-identity.key"; }
    void derive() {
        static const char* label = "rta-net2 verifier v1";
        n2::hmac_sha256(secret, 32, (const uint8_t*)label, strlen(label), verifier);
        uint8_t digest[32];
        std::string material = "rta-net2 id v1";
        material.append((const char*)verifier, 32);
        n2::sha256((const uint8_t*)material.data(), material.size(), digest);
        put(s.me.id, hex(digest, 16));
    }
    void load_identity() {
        std::string path = identity_path();
        if (!path.empty()) {
            std::ifstream file(path);
            std::string text;
            while (std::getline(file, text))
                if (text.compare(0, 7, "secret=") == 0 && unhex(text.substr(7, 64), secret, 32)) have_secret = true;
        }
        if (have_secret) { derive(); return; }
        if (!n2::random_bytes(secret, 32)) { stop_for_good("This computer gave no random numbers: no identity can be made."); return; }
        have_secret = true;
        s.me.new_identity = 1;
        derive();
        save_identity();
    }
    void save_identity() {
        std::string path = identity_path();
        if (path.empty()) return;
        std::string temporary = path + ".new";
        {
            std::ofstream file(temporary, std::ios::trunc);
            file << "rta-net2 identity v1\n"
                 << "# This file is the player: whoever has it is this player. Copy it to move to another computer; do not share it.\n"
                 << "secret=" << hex(secret, 32) << "\n";
        }
        chmod(temporary.c_str(), 0600);
        if (rename(temporary.c_str(), path.c_str()) != 0) s.event(NET2_EV_NOTICE, 0, "The identity could not be saved in " + data_dir + ": it will be new at the next start.");
    }

    // ---- the link ------------------------------------------------------------------------
    static int way_of(const std::string& v, int otherwise) {
        return v == "auto" ? WAY_AUTO : v == "direct" ? WAY_DIRECT : (v == "ws" || v == "wss" || v == "websocket") ? WAY_WS : otherwise;
    }
    static int udp_of(const std::string& v, int otherwise) {
        return v == "auto" ? UDP_AUTO : v == "tunnel" ? UDP_TUNNEL : (v == "udp" || v == "direct") ? UDP_ONLY : otherwise;
    }
    bool set_ws(const std::string& url) {      // "wss://host[:port][/path]" or "ws://..."
        std::string rest;
        bool secure;
        if (url.compare(0, 6, "wss://") == 0) { secure = true; rest = url.substr(6); }
        else if (url.compare(0, 5, "ws://") == 0) { secure = false; rest = url.substr(5); }
        else return false;
        size_t slash = rest.find('/');
        std::string where = slash == std::string::npos ? rest : rest.substr(0, slash);
        std::string path = slash == std::string::npos ? "/net2" : rest.substr(slash);
        size_t colon = where.rfind(':');
        uint16_t p = secure ? 443 : 80;
        if (colon != std::string::npos) { p = (uint16_t)atoi(where.c_str() + colon + 1); where = where.substr(0, colon); }
        if (where.empty() || !p) return false;
        ws_host = where;
        ws_port = p;
        ws_path = path;
        ws_tls = secure;
        ws_named = true;
        return true;
    }
    // the WebSocket may be tried: it was named, or the direct link is TLS to a host name (the
    // service's web server is then wss://<the same host>/net2)
    bool ws_possible() const { return ws_named || n2::tls_wanted(tls_rule, host_name); }
    std::string ws_text() const {
        if (ws_named) return std::string(ws_tls ? "wss://" : "ws://") + ws_host + ":" + std::to_string(ws_port) + ws_path;
        return "wss://" + host_name + ":443/net2";
    }
    void stop_for_good(const std::string& why) {
        fatal = true;
        drop_link(why, false);
        s.me.link = NET2_LINK_OFF;
    }
    void close_link() {
        if (fd != sock::NONE) sock::close(fd);
        fd = sock::NONE;
        tls.reset();
    }
    void drop_link(const std::string& why, bool retry = true) {
        close_link();
        bool was_online = stage == ONLINE;
        bool before_up = stage >= CONNECTING && stage < ONLINE;
        stage = IDLE;
        inbuf.clear();
        outbuf.clear();
        pending.clear();
        synced = false;
        have_key = false;
        local_sent = false;
        in_room_block = in_start_block = false;
        put(s.me.problem, why);
        int link = retry && !fatal ? NET2_LINK_CONNECTING : NET2_LINK_OFF;
        if (s.me.link != link || was_online) { s.me.link = link; s.event(NET2_EV_LINK, 0, why); }
        if (was_online) {
            // what the service told is stale: friends are shown as they were, offline
            for (auto& f : s.friends) { if (f.presence != NET2_OFFLINE) f.last_seen = unix_now(); f.presence = NET2_OFFLINE; f.room[0] = 0; f.joinable = 0; f.invited_me = 0; }
            s.invites.clear();
            s.event(NET2_EV_FRIENDS);
            s.event(NET2_EV_INVITE);
            if (s.room.state != NET2_ROOM_NONE) {
                // the service puts a player whose link is gone out of its room; a game that
                // runs goes on over the straight routes it has
                bool playing = s.room.state == NET2_ROOM_IN_GAME || s.room.state == NET2_ROOM_STARTING;
                s.room = net2_room_t{};
                my_phase = 0;
                s.event(NET2_EV_ROOM);
                s.event(NET2_EV_NOTICE, 0, playing ? "The link to the service is gone. The game goes on with the players it reaches directly."
                                                   : "The link to the service is gone: you are out of the room.");
            }
        }
        int64_t wait = tries < 1 ? 1000 : tries < 3 ? 3000 : tries < 6 ? 10000 : 30000;
        tries++;
        udp_since = 0;
        carrier_.tunnel_out.clear();
        if (retry && before_up && transport == WAY_AUTO && ws_possible()) {
            // the link did not come up this way: the other way next (the WebSocket at once)
            on_ws = !on_ws;
            if (on_ws) wait = 300;
        }
        next_try = steady_ms() + wait;
    }
    void begin_connect() {
        stage_since = steady_ms();
        unsigned a, b, c, d;
        char tail;
        if (sscanf(host_name.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) == 4 && a < 256 && b < 256 && c < 256 && d < 256) {
            service.ip = (a << 24) | (b << 16) | (c << 8) | d;
            open_socket();
        } else if (host_name == "localhost") {
            service.ip = 0x7F000001;
            open_socket();
        } else {
            resolving = std::make_shared<Resolve>();
            std::shared_ptr<Resolve> job = resolving;
            std::string name = host_name;
            std::thread([job, name] {
                uint32_t ip = 0;
                bool ok = sock::resolve(name, ip);
                job->ip = ip;
                job->state = ok ? 1 : 2;
            }).detach();
            stage = RESOLVING;
        }
    }
    void open_socket() {
        service.port = port;
        if (local_only) {
            std::set<uint32_t> own;
            sock::own_addresses(own);
            if ((service.ip >> 24) != 127 && !own.count(service.ip)) { stop_for_good("The service is not on this computer (local only)."); return; }
        }
        link_ws = transport == WAY_WS || (transport == WAY_AUTO && on_ws && ws_possible());
        if (link_ws) {
            std::string where = ws_named ? ws_host : host_name;
            uint16_t at = ws_named ? ws_port : 443;
            uint32_t ip = service.ip;
            if (where != host_name) {
                unsigned a, b, c, d;
                char tail;
                if (sscanf(where.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) == 4 && a < 256 && b < 256 && c < 256 && d < 256) ip = (a << 24) | (b << 16) | (c << 8) | d;
                else if (where == "localhost") ip = 0x7F000001;
                else if (!sock::resolve(where, ip)) { drop_link("The name " + where + " is not known."); return; }
            }
            tls.reset(n2::ws_link(ws_named && !ws_tls ? n2::plain_link() : n2::tls_link(), ws_named ? ws_path : "/net2"));
            tls->start(ip, at, where, tls_trust);
            stage = CONNECTING;
            return;
        }
        if (n2::tls_wanted(tls_rule, host_name)) {
            tls.reset(n2::tls_link());
            tls->start(service.ip, service.port, host_name, tls_trust);
            stage = CONNECTING;
            return;
        }
        fd = sock::tcp();
        if (fd == sock::NONE) { drop_link("No socket: " + sock::error_text(sock::error())); return; }
        int r = sock::connect(fd, service.ip, service.port);
        if (r == sock::FAILED) { drop_link("The service at " + service_text + " cannot be reached: " + sock::error_text(sock::error())); return; }
        stage = CONNECTING;
    }
    void send_line(const std::string& text) {
        if (!linked()) return;
        outbuf += text;
        outbuf += '\n';
    }
    void flush() {
        while (linked() && !outbuf.empty()) {
            int sent = tls ? tls->send(outbuf.data(), outbuf.size()) : sock::send(fd, outbuf.data(), outbuf.size());
            if (sent == sock::LOST) { drop_link("The link to the service was lost."); return; }
            if (sent <= 0) return;
            outbuf.erase(0, (size_t)sent);
        }
    }
    int request(const std::string& verb, const std::string& fields = "", const std::string& note = "") {
        if (stage != ONLINE) return s.error(NET2_ERR_OFFLINE, "There is no link to the service.");
        n++;
        pending[n] = Pending{verb, note};
        send_line(verb + " n=" + std::to_string(n) + (fields.empty() ? "" : " " + fields));
        return NET2_OK;
    }

    // ---- what the service says -------------------------------------------------------------
    static void character_of(const Line& l, net2_character& c) {
        put(c.name, l.get("cname"));
        put(c.cls, l.get("ccls"));
        c.level = (int32_t)l.num("clevel");
    }
    template <class T> static T* find_id(std::vector<T>& list, const std::string& id) {
        for (auto& item : list)
            if (id == item.id) return &item;
        return nullptr;
    }
    template <class T> static bool drop_id(std::vector<T>& list, const std::string& id) {
        size_t before = list.size();
        list.erase(std::remove_if(list.begin(), list.end(), [&](const T& item) { return id == item.id; }), list.end());
        return before != list.size();
    }

    void on_line(const Line& l) {
        const std::string& v = l.verb;
        if (v == "dg") {                                // a datagram of the tunnel
            const std::string& text = l.get("d");
            std::vector<uint8_t> data(text.size() / 2);
            if (text.size() % 2 || !unhex(text, data.data(), data.size())) return;
            carrier_.inject(data.data(), data.size(), steady_ms());
            return;
        }
        if (v == "hi") {
            uint8_t nonce[16];
            if (!unhex(l.get("nonce"), nonce, 16)) { drop_link("The service answered something else."); return; }
            if (l.num("v") != 1) { stop_for_good("The service speaks another version: this program is too old or too new for it."); return; }
            if (tried_register || (s.me.new_identity && !registered_once)) {
                send_line("register v=1 verifier=" + hex(verifier, 32) + " name=" + enc(first_name));
            } else {
                uint8_t message[21], proof[32];
                memcpy(message, nonce, 16);
                memcpy(message + 16, "login", 5);
                n2::hmac_sha256(verifier, 32, message, 21, proof);
                send_line("login id=" + std::string(s.me.id) + " proof=" + hex(proof, 32));
            }
            stage = PROVING;
        } else if (v == "welcome") {
            stage = ONLINE;
            tries = 0;
            tried_register = false;
            registered_once = true;
            put(s.me.id, l.get("id"));
            put(s.me.name, l.get("name"));
            put(s.me.friend_code, l.get("code"));
            have_key = unhex(l.get("udp"), udp_key, 8);
            if (!want_character) character_of(l, s.me.character);
            s.me.problem[0] = 0;
            s.me.link = NET2_LINK_ONLINE;
            s.friends.clear(); s.requests.clear(); s.blocked.clear(); s.recent.clear(); s.invites.clear();
            char copy[96];
            snprintf(copy, sizeof copy, "fix=%08x words=%u can=%u does=%u", fix_set, fix_words, arith_can, arith_does);
            n++;
            send_line("copy n=" + std::to_string(n) + " " + copy);
            if (want_character) set_character(&s.me.character);
        } else if (v == "synced") {
            synced = true;
            s.sort_friends();
            s.event(NET2_EV_LINK);
            s.event(NET2_EV_ME);
            s.event(NET2_EV_FRIENDS);
            s.event(NET2_EV_REQUESTS);
            s.event(NET2_EV_RECENT);
        } else if (v == "bye") {
            long code = l.num("code");
            std::string text = l.get("text");
            if (stage == PROVING && code == NET2_ERR_NOT_FOUND && !tried_register) {
                // this service does not know the device (a new service, or everything was deleted): register
                tried_register = true;
                tries = 0;
                drop_link("Registering with the service...");
                next_try = steady_ms();
                return;
            }
            if (stage == PROVING && code == NET2_ERR_REFUSED) { stop_for_good("The service does not accept this identity: " + text); return; }
            drop_link(text.empty() ? "The service closed the link." : "The service closed the link: " + text);
            if (code == NET2_ERR_LIMIT) next_try = steady_ms() + 30000;
        } else if (v == "ok" || v == "err") {
            unsigned number = (unsigned)l.num("n");
            auto it = pending.find(number);
            if (it == pending.end()) return;
            Pending p = it->second;
            pending.erase(it);
            if (v == "err") {
                if ((p.verb == "host" || p.verb == "join" || p.verb == "joinf") && s.room.state == NET2_ROOM_JOINING) { s.room = net2_room_t{}; s.event(NET2_EV_ROOM); }
                s.error((int)l.num("code"), l.get("text"));
            } else if (p.verb == "fadd") {
                s.event(NET2_EV_NOTICE, 0, l.num("friends") ? "You are friends now." : "Asked. They have to accept.");
            } else if (p.verb == "name") {
                put(s.me.name, l.get("name"));
                s.event(NET2_EV_ME);
            } else if (p.verb == "invite") {
                s.event(NET2_EV_NOTICE, 0, "Invited.");
            }
        } else if (v == "friend") {
            std::string id = l.get("id");
            net2_friend* f = find_id(s.friends, id);
            if (!f) { s.friends.push_back(net2_friend{}); f = &s.friends.back(); }
            put(f->id, id);
            put(f->name, l.get("name"));
            put(f->friend_code, l.get("code"));
            f->presence = (int)l.num("p");
            put(f->room, l.get("room"));
            f->joinable = (int)l.num("join");
            f->room_players = (int)l.num("players");
            put(f->level, l.get("level"));
            f->since = l.num("since");
            f->last_seen = l.num("seen");
            character_of(l, f->character);
            f->invited_me = (int)l.num("inv");
            f->is_friend = 1;
            if (synced) { s.sort_friends(); s.event(NET2_EV_FRIENDS, 0, "", l.get("name"), id); }
        } else if (v == "unfriend") {
            if (drop_id(s.friends, l.get("id"))) s.event(NET2_EV_FRIENDS);
            if (net2_friend* r = find_id(s.recent, l.get("id"))) { r->is_friend = 0; s.event(NET2_EV_RECENT); }
        } else if (v == "request") {
            std::string id = l.get("id");
            net2_request* r = find_id(s.requests, id);
            bool fresh = !r;
            if (!r) { s.requests.push_back(net2_request{}); r = &s.requests.back(); }
            put(r->id, id);
            put(r->name, l.get("name"));
            put(r->friend_code, l.get("code"));
            r->incoming = (int)l.num("in");
            r->when = l.num("when");
            if (synced) s.event(NET2_EV_REQUESTS, 0, fresh && r->incoming ? std::string(r->name) + " wants to be your friend." : "", r->name, id);
        } else if (v == "unrequest") {
            if (drop_id(s.requests, l.get("id"))) s.event(NET2_EV_REQUESTS);
        } else if (v == "blocked") {
            std::string id = l.get("id");
            if (!find_id(s.blocked, id)) {
                net2_friend b{};
                put(b.id, id);
                put(b.name, l.get("name"));
                s.blocked.push_back(b);
            }
            if (synced) s.event(NET2_EV_FRIENDS);
        } else if (v == "unblocked") {
            if (drop_id(s.blocked, l.get("id"))) s.event(NET2_EV_FRIENDS);
        } else if (v == "recent") {
            std::string id = l.get("id");
            drop_id(s.recent, id);
            net2_friend r{};
            put(r.id, id);
            put(r.name, l.get("name"));
            put(r.friend_code, l.get("code"));
            r.last_seen = l.num("when");
            r.is_friend = (int)l.num("friend");
            r.request_sent = (int)l.num("asked");
            character_of(l, r.character);
            s.recent.insert(s.recent.begin(), r);       // newest first (the service sends oldest first at login)
            if (synced) s.event(NET2_EV_RECENT);
        } else if (v == "unrecent") {
            if (drop_id(s.recent, l.get("id"))) s.event(NET2_EV_RECENT);
        } else if (v == "invite") {
            std::string id = l.get("id");
            s.invites.erase(std::remove_if(s.invites.begin(), s.invites.end(), [&](const net2_invite_t& i) { return id == i.from_id; }), s.invites.end());
            net2_invite_t inv{};
            put(inv.from_id, id);
            put(inv.from_name, l.get("name"));
            put(inv.room, l.get("room"));
            inv.room_players = (int)l.num("players");
            character_of(l, inv.character);
            inv.when = l.num("when");
            s.invites.push_back(inv);
            s.event(NET2_EV_INVITE, 0, std::string(inv.from_name) + " invites you to a game.", inv.from_name, id, inv.room);
        } else if (v == "uninvite") {
            std::string id = l.get("id");
            size_t before = s.invites.size();
            s.invites.erase(std::remove_if(s.invites.begin(), s.invites.end(), [&](const net2_invite_t& i) { return id == i.from_id; }), s.invites.end());
            if (before != s.invites.size()) s.event(NET2_EV_INVITE);
        } else if (v == "room") {
            in_room_block = true;
            incoming = net2_room_t{};
            put(incoming.code, l.get("code"));
            std::string state = l.get("state");
            incoming.state = state == "none" ? NET2_ROOM_NONE : state == "started" ? NET2_ROOM_STARTING : NET2_ROOM_OPEN;
            incoming.my_slot = (int)l.num("slot");
            incoming.host_slot = (int)l.num("host");
            put(incoming.options.level, l.get("level"));
            incoming.options.difficulty = (int)l.num("diff");
            incoming.options.mode = (int)l.num("mode");
            incoming.options.mission = (int)l.num("mission");
            incoming.options.kill_limit = (int)l.num("kills");
            incoming.options.open_to = (int)l.num("open");
        } else if (v == "member" && in_room_block) {
            if (incoming.count >= NET2_PLAYERS) return;
            net2_member& m = incoming.members[incoming.count++];
            m.slot = (int)l.num("slot");
            put(m.id, l.get("id"));
            put(m.name, l.get("name"));
            character_of(l, m.character);
            m.ready = (int)l.num("ready");
            m.phase = (int)l.num("phase");
            m.host = m.slot == incoming.host_slot;
            m.me = m.slot == incoming.my_slot;
            m.is_friend = (int)l.num("friend");
            m.fix_set = (uint32_t)strtoul(l.get("fix").c_str(), nullptr, 16);
            m.fix_words = (uint16_t)l.num("words");
            m.arith_can = (uint8_t)l.num("can");
            m.arith_does = (uint8_t)l.num("does");
            m.rtt_ms = -1;
        } else if (v == "roomend" && in_room_block) {
            in_room_block = false;
            take_room();
        } else if (v == "chat") {
            if (s.room.state == NET2_ROOM_NONE || s.room.state == NET2_ROOM_JOINING) {
                // lines said before I came arrive ahead of the first snapshot: kept for it
                early_chat.push_back({(uint32_t)l.num("n"), l.get("from"), l.get("text")});
                return;
            }
            s.chat_line(l.get("from"), l.get("text"), (uint32_t)l.num("n"));
        } else if (v == "start") {
            in_start_block = true;
            starting = net2_session_t{};
            starting.session = (uint32_t)strtoul(l.get("session").c_str(), nullptr, 16);
            starting.count = 0;
            starting.my_slot = (int)l.num("slot");
            starting.host_slot = (int)l.num("host");
            starting.seed = (uint32_t)strtoul(l.get("seed").c_str(), nullptr, 10);
            put(starting.options.level, l.get("level"));
            starting.options.difficulty = (int)l.num("diff");
            starting.options.mode = (int)l.num("mode");
            starting.options.mission = (int)l.num("mission");
            starting.options.kill_limit = (int)l.num("kills");
            start_eps.assign(NET2_PLAYERS, {});
        } else if (v == "peer" && in_start_block) {
            int slot = (int)l.num("slot");
            if (slot < 0 || slot >= NET2_PLAYERS) return;
            put(starting.players[slot].id, l.get("id"));
            put(starting.players[slot].name, l.get("name"));
            character_of(l, starting.players[slot].character);
            if (slot + 1 > starting.count) starting.count = slot + 1;
            std::istringstream list(l.get("eps"));
            std::string one;
            while (std::getline(list, one, ',')) {
                n2::Endpoint e;
                if (n2::parse_endpoint(one, e)) start_eps[(size_t)slot].push_back(e);
            }
        } else if (v == "startend" && in_start_block) {
            in_start_block = false;
            take_start();
        } else if (v == "notice") {
            s.event(NET2_EV_NOTICE, 0, l.get("text"));
        } else if (v == "deleted") {
            // everything about this player is gone there; here the identity file goes too and a
            // new, unregistered player takes its place
            std::string path = identity_path();
            if (!path.empty()) remove(path.c_str());
            s.friends.clear(); s.requests.clear(); s.blocked.clear(); s.recent.clear(); s.invites.clear();
            s.room = net2_room_t{};
            s.me.character = net2_character{};
            want_character = false;
            s.event(NET2_EV_DELETED, 0, "Everything the service held about you is deleted.");
            have_secret = false;
            registered_once = false;
            s.me.new_identity = 0;
            first_name = "Player";
            load_identity();                            // a new secret: a new player
            put(s.me.name, first_name);
            s.me.friend_code[0] = 0;
            tries = 0;
            drop_link("Starting again as a new player...");
            next_try = steady_ms() + 200;
            s.event(NET2_EV_ME); s.event(NET2_EV_FRIENDS); s.event(NET2_EV_REQUESTS); s.event(NET2_EV_RECENT); s.event(NET2_EV_INVITE); s.event(NET2_EV_ROOM);
        }
    }

    struct Early { uint32_t n; std::string from, text; };
    std::vector<Early> early_chat;

    void take_room() {
        bool was_none = s.room.state == NET2_ROOM_NONE || s.room.state == NET2_ROOM_JOINING;
        if (incoming.state == NET2_ROOM_NONE) {
            if (s.room.state != NET2_ROOM_NONE) {
                s.room = net2_room_t{};
                my_phase = 0;
                early_chat.clear();
                s.event(NET2_EV_ROOM);
            }
            return;
        }
        // the chat and the routes are this side's own: kept across snapshots
        incoming.chat_count = was_none ? 0 : s.room.chat_count;
        if (!was_none) memcpy(incoming.chat, s.room.chat, sizeof incoming.chat);
        int phase = 0;
        for (int i = 0; i < incoming.count; i++) {
            net2_member& m = incoming.members[i];
            if (m.me) { phase = m.phase; m.route = NET2_ROUTE_SELF; m.rtt_ms = 0; }
        }
        my_phase = phase;
        // "started" for the room; for me: starting until my game runs, open again when mine is over
        if (incoming.state == NET2_ROOM_STARTING) incoming.state = phase == 2 ? NET2_ROOM_IN_GAME : phase == 1 ? NET2_ROOM_STARTING : NET2_ROOM_OPEN;
        s.room = incoming;
        s.room_checks();
        update_routes(false);
        if (was_none) {
            for (const Early& e : early_chat) s.chat_line(e.from, e.text, e.n);
            early_chat.clear();
        }
        s.event(NET2_EV_ROOM, 0, "", "", "", s.room.code);
    }

    void take_start() {
        starting.valid = 1;
        s.session = starting;
        std::string problem;
        if (!carrier_.open(bind_to, problem)) { s.error(NET2_ERR_SERVICE, problem); return; }
        carrier_.begin(starting.session, starting.count, starting.my_slot);
        carrier_.policy(relay_policy);
        n2::Endpoint udp_service = service;
        carrier_.relay(udp_service, udp_key);
        for (int slot = 0; slot < starting.count; slot++)
            if (slot != starting.my_slot) carrier_.candidates(slot, start_eps[(size_t)slot]);
        my_phase = 1;
        s.room.state = NET2_ROOM_STARTING;
        update_routes(false);
        s.event(NET2_EV_START, 0, "", "", "", s.room.code);
    }

    void update_routes(bool tell) {
        if (!carrier_.active()) return;
        bool changed = false;
        for (int i = 0; i < s.room.count; i++) {
            net2_member& m = s.room.members[i];
            if (m.me) continue;
            int route = carrier_.route(m.slot), rtt = carrier_.rtt(m.slot);
            if (route != m.route) changed = true;
            m.route = route;
            m.rtt_ms = rtt;
        }
        if (changed && tell) s.event(NET2_EV_ROOM, 0, "", "", "", s.room.code);
    }

    // ---- Backend ---------------------------------------------------------------------------
    void poll() override {
        int64_t now = steady_ms();
        if (fatal) return;
        if (stage == IDLE) {
            if (now >= next_try) begin_connect();
        } else if (stage == RESOLVING) {
            int state = resolving->state;
            if (state == 1) { service.ip = resolving->ip; open_socket(); }
            else if (state == 2) drop_link("The name " + host_name + " is not known.");
            else if (now - stage_since > 15000) drop_link("The name " + host_name + " was not answered.");
        } else if (stage == CONNECTING && tls) {
            int r = tls->state();
            if (r == n2::TlsLink::READY) { stage = GREETING; last_heard = now; }
            else if (r == n2::TlsLink::FAILED) drop_link((link_ws ? "No link to the service over HTTPS (" + ws_text() + "): " : std::string("No secure link to the service: ")) + tls->problem());
            else if (now - stage_since > 15000) drop_link(link_ws ? "The service's web server (" + ws_text() + ") does not answer." : "The service at " + service_text + " does not answer (TLS).");
        } else if (stage == CONNECTING) {
            int r = sock::connect_check(fd);
            if (r == sock::CONNECTED) { stage = GREETING; last_heard = now; }
            else if (r == sock::FAILED) drop_link("The service at " + service_text + " does not answer: " + sock::error_text(sock::error()));
            else if (now - stage_since > 10000) drop_link("The service at " + service_text + " does not answer.");
        }
        if (linked() && stage >= GREETING) {
            char buffer[8192];
            for (int rounds = 0; rounds < 16 && linked(); rounds++) {
                int got = tls ? tls->recv(buffer, sizeof buffer) : sock::recv(fd, buffer, sizeof buffer);
                if (got == sock::AGAIN) break;
                if (got <= 0) {
                    // what came with the close is still read (a "bye" says why)
                    read_lines();
                    if (linked()) drop_link(tls && got < 0 && !tls->problem().empty() ? tls->problem() : "The link to the service was lost.");
                    break;
                }
                inbuf.append(buffer, (size_t)got);
                last_heard = now;
                read_lines();
            }
            if (linked() && stage == ONLINE) {
                if (now - last_ping > 20000) { last_ping = now; n++; send_line("ping n=" + std::to_string(n)); }
                if (now - last_heard > 60000) drop_link("The service has gone quiet.");
            } else if (linked() && now - last_heard > 15000) drop_link("The service does not answer.");
            flush();
        }
        // datagrams: while in a room the service must know where this socket is seen
        if (stage == ONLINE && have_key && s.room.state != NET2_ROOM_NONE && s.room.state != NET2_ROOM_JOINING) {
            std::string problem;
            if (!carrier_.is_open() && !carrier_.open(bind_to, problem)) {
                if (!udp_problem_told) { udp_problem_told = true; s.error(NET2_ERR_SERVICE, problem); }
            } else {
                // no answer to any hello for 8 s: this network lets no UDP through to the service, and
                // the datagrams go in the conversation (the tunnel)
                if (udp_since == 0) udp_since = now;
                bool tunnel = udp_mode == UDP_TUNNEL || (udp_mode == UDP_AUTO && !carrier_.answered() && now - udp_since > 8000);
                if (tunnel && !carrier_.tunnelled()) {
                    carrier_.tunnel(true);
                    last_hello = 0;
                    if (udp_mode == UDP_AUTO && !tunnel_told) {
                        tunnel_told = true;
                        s.event(NET2_EV_NOTICE, 0, "The service does not hear this computer's datagrams (UDP is blocked on this network): the game's go through the service's link instead.");
                    }
                }
                int64_t every = s.room.state == NET2_ROOM_OPEN ? 3000 : 1000;
                if (now - last_hello > every) { last_hello = now; carrier_.hello(service, udp_key); }
                if (!local_sent) {
                    local_sent = true;
                    std::set<uint32_t> own;
                    sock::own_addresses(own);
                    std::string list;
                    int count = 0;
                    uint16_t local_port = carrier_.local().port;
                    uint32_t bound_ip = carrier_.local().ip;
                    for (uint32_t ip : own) {
                        if ((ip >> 24) == 127 || (ip >> 16) == 0xA9FE || count >= 3) continue;      // not loop-back, not link-local
                        // not the shared address space 100.64.0.0/10 (carrier-grade NAT, and the address range of VPNs such as
                        // Tailscale): two players on one VPN would otherwise take it as a straight route nobody asked for
                        // (docs/issues/native-rendezvous.md, "Two networks"); kept only when the socket is bound to it
                        if ((ip >> 22) == 0x191 && ip != bound_ip) continue;
                        n2::Endpoint e;
                        e.ip = ip;
                        e.port = local_port;
                        list += (list.empty() ? "" : ",") + n2::endpoint_text(e);
                        count++;
                    }
                    n++;
                    send_line("local n=" + std::to_string(n) + " eps=" + enc(list));
                }
            }
        }
        if (carrier_.is_open()) {
            carrier_.poll(now);
            update_routes(true);
            send_tunnel();
        }
        if (stage == ONLINE && link_ws && transport == WAY_AUTO && !ws_told) {
            ws_told = true;
            s.event(NET2_EV_NOTICE, 0, "The direct link to the service does not get through on this network: connected through its web server (HTTPS) instead.");
        }
    }
    bool udp_problem_told = false;

    // the tunnel's datagrams, as lines of the conversation (also called by the game's sends: tunnel_send)
    void send_tunnel() {
        if (carrier_.tunnel_out.empty()) return;
        if (stage == ONLINE)
            for (const std::vector<uint8_t>& d : carrier_.tunnel_out) send_line("dg d=" + hex(d.data(), d.size()));
        carrier_.tunnel_out.clear();
        flush();
    }

    void read_lines() {
        size_t end;
        while (linked() && (end = inbuf.find('\n')) != std::string::npos) {
            std::string text = inbuf.substr(0, end);
            inbuf.erase(0, end + 1);
            Line l;
            if (parse_line(text, l)) on_line(l);
        }
        if (inbuf.size() > 65536) drop_link("The service sent something that is not a line.");
    }

    int set_name(const std::string& name) override {
        first_name = name;
        if (stage != ONLINE) { put(s.me.name, name); s.event(NET2_EV_ME); return NET2_OK; }      // used when the link comes up as a new player
        return request("name", "name=" + enc(name));
    }
    int set_character(const net2_character* c) override {
        s.me.character = c ? *c : net2_character{};
        want_character = true;
        if (stage != ONLINE) return NET2_OK;            // sent when the link is up
        n++;
        send_line("char n=" + std::to_string(n) + " name=" + enc(s.me.character.name) + " cls=" + enc(s.me.character.cls) + " level=" + std::to_string(s.me.character.level));
        return NET2_OK;
    }
    int set_game(const std::string& level) override {
        if (stage != ONLINE) return NET2_OK;
        n++;
        send_line("game n=" + std::to_string(n) + " level=" + enc(level));
        return NET2_OK;
    }
    int delete_everything() override { return request("delete"); }
    int friend_add(const std::string& code) override { return request("fadd", "code=" + code); }
    int friend_op(const char* op, const std::string& id) override {
        std::string what = op;
        const char* verb = what == "add-id" ? "fadd" : what == "accept" ? "faccept" : what == "decline" ? "fdecline" : what == "remove" ? "fremove" : what == "block" ? "block" : "unblock";
        return request(verb, "id=" + id);
    }
    int invite(const std::string& id) override { return request("invite", "id=" + id); }
    int invite_answer(const std::string& id, bool accept) override {
        std::string room;
        for (auto& i : s.invites)
            if (id == i.from_id) room = i.room;
        if (room.empty()) return s.error(NET2_ERR_NOT_FOUND, "That invitation is gone.");
        if (!accept) return request("idismiss", "id=" + id);
        return join(room);
    }
    static std::string option_fields(const net2_options& o) {
        return "level=" + enc(o.level) + " diff=" + std::to_string(o.difficulty) + " mode=" + std::to_string(o.mode) + " mission=" + std::to_string(o.mission) +
               " kills=" + std::to_string(o.kill_limit) + " open=" + std::to_string(o.open_to);
    }
    int joining(int r) {
        if (r == NET2_OK) { s.room = net2_room_t{}; s.room.state = NET2_ROOM_JOINING; early_chat.clear(); s.event(NET2_EV_ROOM); }
        return r;
    }
    int host(const net2_options& options) override { return joining(request("host", option_fields(options))); }
    int join(const std::string& code) override { return joining(request("join", "code=" + code)); }
    int join_friend(const std::string& id) override { return joining(request("joinf", "id=" + id)); }
    int chat(const std::string& text) override { return request("chat", "text=" + enc(text)); }
    int ready(bool ready) override { return request("ready", ready ? "v=1" : "v=0"); }
    int set_options(const net2_options& options) override { return request("opts", option_fields(options)); }
    int kick(int slot) override { return request("kick", "slot=" + std::to_string(slot)); }
    int start() override { return request("start"); }
    int leave() override {
        if (s.room.state == NET2_ROOM_NONE) return NET2_OK;
        carrier_.end();
        s.session = net2_session_t{};
        if (stage != ONLINE) { s.room = net2_room_t{}; s.event(NET2_EV_ROOM); return NET2_OK; }
        return request("leave");
    }
    int game_state(const std::string& level, bool running) override {
        if (!running) {
            bool was = my_phase != 0;
            carrier_.end();
            s.session.valid = 0;
            my_phase = 0;
            if (s.room.state == NET2_ROOM_STARTING || s.room.state == NET2_ROOM_IN_GAME) {
                s.room.state = NET2_ROOM_OPEN;
                for (int i = 0; i < s.room.count; i++)
                    if (!s.room.members[i].me) { s.room.members[i].route = NET2_ROUTE_NONE; s.room.members[i].rtt_ms = -1; }
                s.event(NET2_EV_ROOM, 0, "", "", "", s.room.code);
            }
            if (was) s.event(NET2_EV_GAME_OVER, 0, "", "", "", s.room.code);
            if (stage == ONLINE && was) { n++; send_line("gstate n=" + std::to_string(n) + " v=0"); }
            return NET2_OK;
        }
        if (my_phase == 0) return NET2_ERR_STATE;
        my_phase = 2;
        s.room.state = NET2_ROOM_IN_GAME;
        s.event(NET2_EV_ROOM, 0, "", "", "", s.room.code);
        if (stage == ONLINE) { n++; send_line("gstate n=" + std::to_string(n) + " v=1 level=" + enc(level)); }
        return NET2_OK;
    }
    n2::Carrier* carrier() override { return &carrier_; }
    int debug(const std::string& what, std::string& out) override {
        if (what == "udp" || what == "routes") out = carrier_.is_open() ? carrier_.text() : "no UDP socket yet";
        else if (what == "link") {
            static const char* STAGES[] = {"idle", "resolving", "connecting", "greeting", "proving", "online"};
            out = std::string("stage ") + STAGES[stage] + ", service " + service_text + ", tls " +
                  (n2::tls_wanted(tls_rule, host_name) ? "on" : "off") + " (rule " + n2::tls_rule_text(tls_rule) + ")" +
                  (tls && stage >= GREETING ? ": " + tls->summary() : "") + ", " + std::to_string(pending.size()) + " requests open, try " + std::to_string(tries) +
                  ", via " + (linked() && link_ws ? "websocket " + ws_text() : linked() ? std::string("direct") : std::string("-")) +
                  " (transport " + (transport == WAY_WS ? "ws" : transport == WAY_DIRECT ? "direct" : "auto") + "), udp " +
                  (carrier_.tunnelled() ? "tunnel" : "direct") + " (" + (udp_mode == UDP_TUNNEL ? "tunnel" : udp_mode == UDP_ONLY ? "udp" : "auto") + ")";
        } else if (what.compare(0, 9, "tls-rule ") == 0) {
            // tests: would this link's rule put a service written so inside TLS (nothing is sent)
            std::string address = what.substr(9);
            int rule = tls_rule;
            if (address.compare(0, 6, "tls://") == 0) { rule = n2::TLS_ON; address = address.substr(6); }
            else if (address.compare(0, 8, "plain://") == 0) { rule = n2::TLS_OFF; address = address.substr(8); }
            size_t colon = address.rfind(':');
            out = std::string("tls ") + (n2::tls_wanted(rule, colon == std::string::npos ? address : address.substr(0, colon)) ? "on" : "off");
        } else if (what.compare(0, 5, "send ") == 0) {
            // tests: one datagram to a player of the started session, as the game would send it
            int slot = atoi(what.c_str() + 5);
            size_t space = what.find(' ', 5);
            std::string text = space == std::string::npos ? "" : what.substr(space + 1);
            out = carrier_.send(slot, (const uint8_t*)text.data(), text.size()) ? "sent" : "not sent";
        } else if (what == "recv") {
            // tests: the next datagram that arrived for the game, "from <slot>: <text>", or "nothing"
            uint8_t buffer[n2::MOST];
            int from = 0;
            int got = carrier_.receive(from, buffer, sizeof buffer);
            if (got < 0) { carrier_.poll(steady_ms()); got = carrier_.receive(from, buffer, sizeof buffer); }
            out = got < 0 ? "nothing" : "from " + std::to_string(from) + ": " + std::string((const char*)buffer, (size_t)got);
        } else return NET2_ERR_ARGUMENT;
        return NET2_OK;
    }
    int set(const std::string& key, const std::string& value) override {
        if (key == "relay") {
            relay_policy = value == "force" ? n2::RELAY_FORCE : value == "never" ? n2::RELAY_NEVER : n2::RELAY_AUTO;
            carrier_.policy(relay_policy);
            return NET2_OK;
        }
        if (key == "bind") {            // the UDP socket's own address:port (tests; before the first room)
            if (carrier_.is_open()) return NET2_ERR_STATE;
            bind_to = value;
            return NET2_OK;
        }
        if (key == "udp") {             // the datagrams: auto | tunnel | udp
            int mode = udp_of(value, -1);
            if (mode < 0) return NET2_ERR_ARGUMENT;
            udp_mode = mode;
            if (mode == UDP_ONLY) carrier_.tunnel(false);
            return NET2_OK;
        }
        if (key == "transport" || key == "ws") {       // how the link is made: it is made again
            if (key == "transport") {
                int way = way_of(value, -1);
                if (way < 0) return NET2_ERR_ARGUMENT;
                transport = way;
            } else if (!set_ws(value)) return NET2_ERR_ARGUMENT;
            on_ws = false;
            if (linked() && !fatal) { drop_link("Connecting again (" + key + " changed)..."); tries = 0; next_try = steady_ms(); }
            return NET2_OK;
        }
        if (key == "tls" || key == "tls-ca") {         // how the link is made: it is made again
            if (key == "tls") {
                int rule = n2::tls_rule(value);
                if (rule < 0) return NET2_ERR_ARGUMENT;
                tls_rule = rule;
            } else tls_trust = value;
            if (linked() && !fatal) { drop_link("Connecting again (" + key + " changed)..."); tries = 0; next_try = steady_ms(); }
            return NET2_OK;
        }
        if (key == "copy") {            // what this copy says about itself, said again ("fix=%08x words=%u": the souls mode's room option)
            unsigned long set = 0, words = 0;
            if (sscanf(value.c_str(), "fix=%lx words=%lu", &set, &words) != 2) return NET2_ERR_ARGUMENT;
            fix_set = (uint32_t)set;
            fix_words = (uint16_t)words;
            if (stage == ONLINE) {
                char copy[96];
                snprintf(copy, sizeof copy, "fix=%08x words=%u can=%u does=%u", fix_set, fix_words, arith_can, arith_does);
                n++;
                send_line("copy n=" + std::to_string(n) + " " + copy);
            }
            return NET2_OK;
        }
        if (key == "mock-speed") return NET2_OK;
        return NET2_ERR_ARGUMENT;
    }
};

}  // namespace

Backend* make_service(const net2_config& config) { return new Net(config); }

}  // namespace net2impl
