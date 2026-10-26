// Synthetic links exercise the actual queues without a service or game files.
#include "tls.cpp"
#include "session_net.cpp"
#include "../app/guestmap.h"

#include <cassert>

namespace {
struct Link : n2::TlsLink {
    std::string input, output;
    size_t at = 0, chunk = 8192, read_bytes = 0;
    bool repeat = false, blocked = false, eof = false;
    void start(uint32_t, uint16_t, const std::string&, const std::string&) override {}
    int state() override { return READY; }
    int send(const char* data, size_t size) override {
        if (blocked) return AGAIN;
        size_t n = std::min(size, chunk);
        output.append(data, n);
        return (int)n;
    }
    int recv(char* data, size_t size) override {
        if (repeat && at == input.size()) at = 0;
        if (at == input.size()) return eof ? 0 : AGAIN;
        size_t n = std::min(std::min(size, chunk), input.size() - at);
        memcpy(data, input.data() + at, n);
        at += n;
        read_bytes += n;
        return (int)n;
    }
    std::string problem() override { return "synthetic link"; }
    std::string summary() override { return "synthetic link"; }
};

std::string frame(const std::string& payload, uint8_t opcode = 2) {
    std::string out(1, (char)(0x80 | opcode));
    size_t n = payload.size();
    if (n < 126) out += (char)n;
    else if (n < 65536) { out += (char)126; out += (char)(n >> 8); out += (char)n; }
    else { out += (char)127; for (int k = 7; k >= 0; k--) out += (char)((uint64_t)n >> (8 * k)); }
    return out + payload;
}

void ws_bounds() {
    auto* under = new Link;
    n2::WsLink ws(under, "/net2");
    ws.phase = 2;
    under->input = frame(std::string(8191, 'x') + '\n');
    under->repeat = true;
    char buffer[8192];
    for (int i = 0; i < 100; i++) {
        assert(ws.recv(buffer, sizeof buffer) == sizeof buffer);
        assert(std::string(buffer, sizeof buffer) == std::string(8191, 'x') + '\n');
        assert(ws.in.size() + ws.data.size() <= n2::WsLink::RECEIVE_BYTES);
        if (!ws.data.empty()) {
            size_t before = under->read_bytes;
            assert(ws.state() == n2::TlsLink::READY);
            assert(ws.send("request\n", 8) == 8);
            assert(under->read_bytes == before);
        }
    }
    printf("PASS WebSocket: 100 reads, state/send backpressure, receive budget\n");

    auto* large_under = new Link;
    n2::WsLink large(large_under, "/net2");
    large.phase = 2;
    std::string payload(1u << 20, 'z'), received;
    large_under->input = frame(payload);
    large_under->eof = true;
    for (int i = 0; i < 300; i++) {
        int got = large.recv(buffer, sizeof buffer);
        assert(got != n2::TlsLink::LOST);
        if (got > 0) received.append(buffer, (size_t)got);
        assert(large.in.size() + large.data.size() <= n2::WsLink::RECEIVE_BYTES);
        if (got == 0) break;
    }
    assert(received == payload);
    assert(large.recv(buffer, sizeof buffer) == 0);
    auto* big_under = new Link;
    n2::WsLink big(big_under, "/net2");
    big.phase = 2;
    big_under->input = frame(payload + 'z');
    assert(big.state() == n2::TlsLink::FAILED);
    printf("PASS WebSocket: maximum frame, oversized frame, bytes before EOF\n");

    auto* split_under = new Link;
    n2::WsLink split(split_under, "/net2");
    split.phase = 2;
    split_under->chunk = 1;
    split_under->input = frame("first\n", 1) + frame("second\n", 0);
    split_under->eof = true;
    received.clear();
    for (int i = 0; i < 50; i++) {
        int got = split.recv(buffer, 3);
        if (got > 0) received.append(buffer, (size_t)got);
        if (got == 0) break;
    }
    assert(received == "first\nsecond\n");
    printf("PASS WebSocket: split headers, continuation bytes and small reads\n");

    auto* ping_under = new Link;
    n2::WsLink ping(ping_under, "/net2");
    ping.phase = 2;
    ping_under->blocked = true;
    ping_under->input = frame(std::string(125, 'p'), 9);
    ping_under->repeat = true;
    for (int i = 0; i < 200; i++) {
        int state = ping.state();
        assert(ping.out.size() <= n2::WsLink::OUTPUT_BYTES);
        if (state == n2::TlsLink::FAILED) break;
    }
    assert(ping.state() == n2::TlsLink::FAILED);
    printf("PASS WebSocket: blocked pong flood fails within output budget\n");

    auto* send_under = new Link;
    n2::WsLink send(send_under, "/net2");
    send.phase = 2;
    send_under->blocked = true;
    std::string bytes(16384, 'b');
    int sent = 0;
    while (send.send(bytes.data(), bytes.size()) > 0) {
        assert(++sent <= 16);
        assert(send.out.size() <= n2::WsLink::OUTPUT_BYTES);
    }
    assert(send.state() == n2::TlsLink::READY);
    send_under->blocked = false;
    send.pump();
    std::string decoded;
    for (size_t at = 0; at < send_under->output.size();) {
        const std::string& wire = send_under->output;
        assert((uint8_t)wire[at] == 0x82 && (uint8_t)wire[at + 1] == 0xfe);
        size_t n = (uint8_t)wire[at + 2] * 256u + (uint8_t)wire[at + 3];
        for (size_t i = 0; i < n; i++) decoded += (char)(wire[at + 8 + i] ^ wire[at + 4 + (i & 3)]);
        at += n + 8;
    }
    assert(decoded == std::string((size_t)sent * bytes.size(), 'b'));
    assert(send.send("next", 4) == 4);
    printf("PASS WebSocket: frame overhead bounded, partial writes preserve payloads\n");

    auto* upgrade_under = new Link;
    upgrade_under->input = "HTTP/1.1 101 Switching Protocols\r\n\r\n";
    n2::WsLink upgrade(upgrade_under, "/net2");
    assert(upgrade.state() == n2::TlsLink::READY);
    assert(upgrade_under->output.find("GET /net2 HTTP/1.1\r\n") == 0);
    n2::WsLink request(new Link, std::string(n2::WsLink::OUTPUT_BYTES, 'x'));
    assert(request.state() == n2::TlsLink::FAILED && request.out.empty());
    printf("PASS WebSocket: oversized upgrade request refused before enqueue\n");
}

Link* online(net2impl::Net& net, bool blocked = false) {
    auto* link = new Link;
    link->blocked = blocked;
    net.tls.reset(link);
    net.fatal = false;
    net.stage = net2impl::Net::ONLINE;
    net.s.me.link = NET2_LINK_ONLINE;
    net.last_heard = net.last_ping = net2impl::steady_ms();
    return link;
}

void carrier_bounds() {
    uint8_t seen[] = {'N', '2', n2::KIND_SEEN, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0};
    n2::Carrier c;
    c.inject(seen, sizeof seen, 1000);
    assert(c.answered(9000));
    assert(!c.answered(9001));
    c.inject(seen, n2::HEAD, 10000);
    assert(!c.answered(10000));
    seen[3] = 1;
    c.inject(seen, sizeof seen, 11000);
    seen[3] = 0;
    seen[4] = 1;
    c.inject(seen, sizeof seen, 12000);
    seen[4] = 0;
    assert(!c.answered(12000));
    c.inject(seen, sizeof seen, 13000);
    assert(c.answered(13000));
    c.close();
    assert(!c.answered(13000) && !c.seen_as().set());
    printf("PASS carrier: reply expiry, malformed replies, close reset\n");

    setenv("RTA_NET2_TEST_NO_UDP", "0", 1);
    n2::Carrier udp;
    setenv("RTA_NET2_TEST_NO_UDP", "1", 1);
    std::string problem;
    assert(udp.open("", problem));
    sock::Handle server = sock::udp(), stranger = sock::udp();
    sockaddr_in address = sock::address_of(INADDR_LOOPBACK, 0);
    assert(::bind(server, (sockaddr*)&address, sizeof address) == 0);
    socklen_t length = sizeof address;
    assert(getsockname(server, (sockaddr*)&address, &length) == 0);
    n2::Endpoint endpoint{INADDR_LOOPBACK, ntohs(address.sin_port)};
    uint8_t key[8] = {0};
    udp.hello(endpoint, key);
    auto reply = [&](sock::Handle sender, size_t size, int64_t at, uint64_t strays) {
        sockaddr_in to = sock::address_of(INADDR_LOOPBACK, udp.local().port);
        assert(::sendto(sender, seen, size, 0, (sockaddr*)&to, sizeof to) == (ssize_t)size);
        for (int i = 0; i < 200; i++) {
            udp.poll(at);
            if (udp.answered(at) || udp.strays >= strays) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    };
    reply(stranger, sizeof seen, 1000, 1);
    assert(!udp.answered(1000) && udp.strays == 1);
    reply(server, n2::HEAD, 1500, 2);
    assert(!udp.answered(1500) && udp.strays == 2);
    reply(server, sizeof seen, 2000, 3);
    assert(udp.answered(2000));
    assert(getsockname(stranger, (sockaddr*)&address, &length) == 0);
    udp.hello({INADDR_LOOPBACK, ntohs(address.sin_port)}, key);
    assert(!udp.answered(2000));
    udp.close();
    sock::close(server);
    sock::close(stranger);
    printf("PASS carrier: only a complete reply from the current service counts (local UDP)\n");

    net2_config config{};
    net2impl::Net net(config);
    online(net);
    assert(net.carrier_.open("", problem));
    net.carrier_.begin(1, 2, 0);
    net.carrier_.fixed(1, {INADDR_LOOPBACK, 1});
    int64_t now = net2impl::steady_ms();
    net.carrier_.inject(seen, sizeof seen, now);
    net.last_hello = now;
    net.drop_link("synthetic reconnect");
    assert(!net.carrier_.answered(now) && !net.carrier_.seen_as().set());
    assert(net.last_hello == 0 && net.udp_since == 0);
    assert(net.carrier_.active() && net.carrier_.route(1) == NET2_ROUTE_DIRECT);
    online(net);
    net.have_key = true;
    net.s.room.state = NET2_ROOM_OPEN;
    net.udp_since = now - 9000;
    net.poll();
    assert(net.carrier_.tunnelled());
    assert(net.set("udp", "udp") == NET2_OK);
    net.poll();
    assert(!net.carrier_.tunnelled());
    assert(net.set("udp", "tunnel") == NET2_OK);
    net.carrier_.inject(seen, sizeof seen, now);
    net.poll();
    assert(net.carrier_.tunnelled());
    assert(net.set("udp", "udp") == NET2_OK);
    assert(net.set("udp", "auto") == NET2_OK);
    net.carrier_.inject(seen, sizeof seen, now - 9000);
    net.s.room.state = NET2_ROOM_NONE;
    net.poll();
    assert(net.udp_since == 0);
    net.s.room.state = NET2_ROOM_OPEN;
    net.poll();
    assert(!net.carrier_.tunnelled());
    net.udp_since = now - 9000;
    net.poll();
    assert(net.carrier_.tunnelled());
    printf("PASS session: reconnect and expired UDP fall back; new rooms get a fresh probe window\n");
    printf("PASS session: direct routes and forced UDP/tunnel modes preserved\n");
}

void session_bounds() {
    net2_config config{};
    net2impl::Net net(config);
    Link* link = online(net, true);
    assert(net.send_line(std::string(net2impl::OUTPUT_BYTES - 1, 'x')));
    assert(net.outbuf.size() == net2impl::OUTPUT_BYTES);
    assert(net.request("ping") == NET2_ERR_OFFLINE);
    assert(!net.linked() && net.outbuf.empty() && net.pending.empty());
    assert(net.s.me.link == NET2_LINK_CONNECTING);
    printf("PASS session: exact output limit, one over fails, request reports failure\n");

    online(net, true);
    for (int round = 0; round < 100 && net.linked(); round++) {
        for (int i = 0; i < 60; i++) net.carrier_.tunnel_out.emplace_back(n2::MOST + 16, (uint8_t)i);
        net.send_tunnel();
        assert(net.outbuf.size() <= net2impl::OUTPUT_BYTES);
    }
    assert(!net.linked() && net.carrier_.tunnel_out.empty());
    printf("PASS tunnel: repeated blocked batches fail without growth or invalid iteration\n");

    link = online(net);
    link->chunk = 17;
    std::string expected;
    for (int i = 0; i < 512; i++) {
        std::vector<uint8_t> bytes(n2::MOST + 16);
        for (size_t k = 0; k < bytes.size(); k++) bytes[k] = (uint8_t)(i + k);
        expected += "dg d=" + net2impl::hex(bytes.data(), bytes.size()) + '\n';
        net.carrier_.tunnel_out.push_back(std::move(bytes));
    }
    net.send_tunnel();
    assert(net.linked() && net.carrier_.tunnel_out.empty() && net.outbuf.empty());
    assert(link->output == expected);
    printf("PASS tunnel: 512 maximum datagrams retain every byte and ordering through partial writes\n");
}
}  // namespace

int main() {
    // Only the explicit local UDP probe sends datagrams; session probes use synthetic links.
    setenv("RTA_NET2_TEST_NO_UDP", "1", 1);
    static_assert(guestmap::at(0xE0000).hi == 0xE0058, "soak extent");
    static_assert(guestmap::at(0xFF000).hi == 0x100000, "RPC extent");
    static_assert(guestmap::disjoint(), "guest blocks");
    ws_bounds();
    carrier_bounds();
    session_bounds();
    printf("PASS guest map: full soak and RPC extents, no overlaps\n");
    return 0;
}
