#!/usr/bin/env python3
"""Checks a relay (relay.py) from outside, as a page would use it, and times its path.

    check.py --selftest
        Starts a stand-in lobby server (a TCP port that echoes, a UDP port that notes what
        arrives) and a relay of its own on this computer, and goes through everything the
        relay promises: the two kinds of TCP destination, what is refused, the UDP socket
        the stand-in sees, datagrams from one session to another, the players outside (who
        is reached and who is not, with stand-in players on this computer), the limits.

    check.py ws://127.0.0.1:8975/relay
    check.py wss://HOST/PATH/relay --origin https://HOST [--gateway-port 40810]
        A running relay. Opens two sessions; asks for one TCP connection to the lobby
        server's gateway port and closes it again WITHOUT SENDING A BYTE (no request, no
        log-in); asks for a destination that must be refused; sends datagrams from one
        session to the other and back and times them. Nothing is sent to the lobby
        server's discovery port, and nothing to any address outside the relay.

Standard library only. Figures: "ping" is one message to the relay and its answer;
"player to player" is a datagram from session A through the relay to session B and one
back - what one exchange between two browser players costs when both are where this
computer is.
"""
import argparse
import base64
import os
import socket
import ssl
import statistics
import struct
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
HELLO, TCP_OPEN, TCP_DATA, TCP_SHUT, TCP_CLOSE, UDP_OPEN, UDP_SEND, UDP_CLOSE, PING = range(1, 10)
WELCOME, TCP_OPENED, R_TCP_DATA, TCP_EOF, TCP_CLOSED, UDP_BOUND, UDP_RECV, PONG, NOTICE = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x89, 0x8A


class Gone(Exception):
    pass


class Client:
    """One WebSocket connection to the relay, as a browser makes it."""

    def __init__(self, url, origin=None, timeout=10.0, headers=(), receive_buffer=0):
        parts = urlparse(url)
        secure = parts.scheme == "wss"
        port = parts.port or (443 if secure else 80)
        if receive_buffer:  # a page on a thin line: set before the connection is made
            raw = socket.socket()
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer)
            raw.settimeout(timeout)
            raw.connect((parts.hostname, port))
        else:
            raw = socket.create_connection((parts.hostname, port), timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) if secure else raw
        key = base64.b64encode(os.urandom(16)).decode()
        request = "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n" % (parts.path or "/", parts.netloc, key)
        if origin:
            request += "Origin: %s\r\n" % origin
        for name, value in headers:  # what a web server in front adds, or what a client writes itself
            request += "%s: %s\r\n" % (name, value)
        self.sock.sendall((request + "\r\n").encode())
        self.buffer = b""
        head = b""
        while b"\r\n\r\n" not in head:
            piece = self.sock.recv(4096)
            if not piece:
                raise Gone("closed during the handshake")
            head += piece
        head, _, self.buffer = head.partition(b"\r\n\r\n")
        self.status = head.split(b"\r\n")[0].decode("latin-1")
        if " 101 " not in self.status:
            raise Gone(self.status)
        self.notices = []

    def send(self, kind, payload=b""):
        data = bytes((kind,)) + payload
        mask = os.urandom(4)
        n = len(data)
        head = bytes((0x82, 0x80 | n)) if n < 126 else bytes((0x82, 0x80 | 126)) + struct.pack(">H", n) if n < 65536 else bytes((0x82, 0x80 | 127)) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(data)))

    def _frame(self):
        """A whole frame out of the buffer: (opcode, payload), or None when it is not all there."""
        b = self.buffer
        if len(b) < 2:
            return None
        n, at = b[1] & 0x7F, 2
        if n == 126:
            if len(b) < 4:
                return None
            n, at = struct.unpack(">H", b[2:4])[0], 4
        elif n == 127:
            if len(b) < 10:
                return None
            n, at = struct.unpack(">Q", b[2:10])[0], 10
        if len(b) < at + n:
            return None
        self.buffer = b[at + n:]
        return b[0] & 0x0F, b[at:at + n]

    def recv(self, timeout=5.0):
        """(kind, payload), or None when nothing came in time. Notices are kept aside."""
        deadline = time.monotonic() + timeout
        while True:
            got = self._frame()
            if got is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.sock.settimeout(left)
                try:
                    piece = self.sock.recv(65536)
                except (socket.timeout, ssl.SSLWantReadError):
                    return None
                if not piece:
                    raise Gone("the relay closed the connection")
                self.buffer += piece
                continue
            opcode, data = got
            if opcode == 8:
                raise Gone("closed by the relay (code %d)" % (struct.unpack(">H", data[:2])[0] if len(data) >= 2 else 0))
            if opcode != 2 or not data:
                continue
            if data[0] == NOTICE:
                self.notices.append((data[1], data[2:].decode("utf-8", "replace")))
                continue
            return data[0], data[1:]

    def expect(self, kind, timeout=5.0):
        deadline = time.monotonic() + timeout
        while True:
            got = self.recv(max(0.01, deadline - time.monotonic()))
            if got is None:
                raise Gone("no message of kind %02x within %.0f s" % (kind, timeout))
            if got[0] == kind:
                return got[1]

    def hello(self):
        self.send(HELLO, b"\x01")
        version, lobby, own, idle, largest = struct.unpack(">BIIHH", self.expect(WELCOME))
        return {"version": version, "lobby": lobby, "own": own, "idle": idle, "largest": largest}

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def ip_text(number):
    return "%d.%d.%d.%d" % (number >> 24, (number >> 16) & 255, (number >> 8) & 255, number & 255)


def figures(samples):
    samples = sorted(samples)
    return "median %.2f ms, 95th %.2f ms, worst %.2f ms (n=%d)" % (statistics.median(samples), samples[int(len(samples) * 0.95) - 1], samples[-1], len(samples))


def ping_times(client, count=200, gap=0.01):
    times = []
    for i in range(count):
        start = time.perf_counter()
        client.send(PING, struct.pack(">I", i))
        client.expect(PONG)
        times.append((time.perf_counter() - start) * 1000)
        time.sleep(gap)
    return times


def player_to_player(a, b, own, size=64, count=200, gap=0.01):
    """A datagram of 'size' bytes from session a to session b and one back, timed."""
    a.send(UDP_OPEN, b"\x00")
    b.send(UDP_OPEN, b"\x00")
    port_a = struct.unpack(">BH", a.expect(UDP_BOUND))[1]
    port_b = struct.unpack(">BH", b.expect(UDP_BOUND))[1]

    def datagram(client, body, timeout=2.0):
        """The datagram with this content, whatever else arrives before it: its sender."""
        deadline = time.monotonic() + timeout
        while True:
            got = client.expect(UDP_RECV, max(0.01, deadline - time.monotonic()))
            if got[7:] == body:
                return struct.unpack(">BIH", got[:7])[1:]

    # The relay hands a datagram to a page only when that page wants to hear from the
    # sender: here, when it has sent to it itself. So each sends to the other once; the
    # first of the two is not handed over (a relay from before that rule hands it over).
    a.send(UDP_SEND, struct.pack(">BIH", 0, own, port_b) + b"meet a")
    a.send(PING, b"met")
    a.expect(PONG)
    b.send(UDP_SEND, struct.pack(">BIH", 0, own, port_a) + b"meet b")
    datagram(a, b"meet b", 5)
    times = []
    lost = 0
    for i in range(count):
        body = struct.pack(">I", i) + bytes(size - 4)
        start = time.perf_counter()
        a.send(UDP_SEND, struct.pack(">BIH", 0, own, port_b) + body)
        try:
            address, port = datagram(b, body)
            if (address, port) != (own, port_a):
                raise Gone("the datagram came from %s:%d, not from the sender's socket %s:%d" % (ip_text(address), port, ip_text(own), port_a))
            b.send(UDP_SEND, struct.pack(">BIH", 0, own, port_a) + body)
            datagram(a, body)
            times.append((time.perf_counter() - start) * 1000)
        except Gone as error:
            if "came from" in str(error):
                raise
            lost += 1
        time.sleep(gap)
    return times, lost, (port_a, port_b)


def check_running(args):
    load = os.getloadavg()[0]
    a = Client(args.url, args.origin)
    welcome = a.hello()
    b = Client(args.url, args.origin)
    b.hello()
    print("session opened: relay version %d; lobby server %s; the relay is %s to it; idle limit %d s; largest message %d bytes"
          % (welcome["version"], ip_text(welcome["lobby"]), ip_text(welcome["own"]), welcome["idle"], welcome["largest"]))
    # one TCP connection to the gateway port, opened and closed, nothing sent
    a.send(TCP_OPEN, struct.pack(">HIH", 1, welcome["lobby"], args.gateway_port))
    conn, status = struct.unpack(">HB", a.expect(TCP_OPENED, 15))
    a.send(TCP_CLOSE, struct.pack(">H", 1))
    print("TCP to the lobby server's gateway port %d: %s (closed again without sending anything)" % (args.gateway_port, "connected" if status == 0 else "NOT connected, status %d" % status))
    ok = status == 0
    # what must be refused
    a.send(TCP_OPEN, struct.pack(">HIH", 2, welcome["lobby"], 22))
    refused_port = struct.unpack(">HB", a.expect(TCP_OPENED))[1]
    a.send(TCP_OPEN, struct.pack(">HIH", 3, 0x01010101, args.gateway_port))
    refused_host = struct.unpack(">HB", a.expect(TCP_OPENED))[1]
    a.send(UDP_SEND, struct.pack(">BIH", 1, 0x7F000002, 53) + b"x")
    a.send(PING, b"end")
    a.expect(PONG)
    refused_udp = any("datagram" in text for _, text in a.notices)
    print("refused, as it must be: TCP to another port of the lobby server: %s; TCP to another host: %s; a datagram to an address no player can have: %s"
          % ("yes" if refused_port == 1 else "NO (status %d)" % refused_port, "yes" if refused_host == 1 else "NO (status %d)" % refused_host, "yes" if refused_udp else "NO"))
    ok = ok and refused_port == 1 and refused_host == 1 and refused_udp
    pings = ping_times(a, args.count)
    print("ping (this computer -> relay -> back):       %s" % figures(pings))
    times, lost, _ = player_to_player(a, b, welcome["own"], count=args.count)
    print("player to player and back, through the relay: %s%s" % (figures(times) if times else "nothing arrived", ", %d lost" % lost if lost else ""))
    print("(load average of this computer while measuring: %.1f)" % load)
    a.close()
    b.close()
    return ok and bool(times)


# ---- the self-test ------------------------------------------------------------------------

class StandIn:
    """A lobby server's ports with nothing behind them: TCP echoes, UDP notes the sender."""

    def __init__(self, address):
        self.tcp = socket.socket()
        self.tcp.bind((address, 0))
        self.tcp.listen(8)
        self.tcp_port = self.tcp.getsockname()[1]
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind((address, 0))
        self.udp_port = self.udp.getsockname()[1]
        self.udp.settimeout(3)
        self.received = bytearray()  # every byte any connection has sent it
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            conn, _ = self.tcp.accept()
            threading.Thread(target=self.echo, args=(conn,), daemon=True).start()

    def echo(self, conn):
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                self.received += data
                if data.endswith(b"hang up"):
                    break
                conn.sendall(data)
        except OSError:
            pass
        conn.close()


def lobby_message(kind, body, reply=True, result=0):
    """A lobby server's message as it is on the wire (docs/lobby-protocol.md section 2)."""
    payload = struct.pack("<HI", kind, 7 if reply else 0) + (struct.pack("<I", result) if reply else b"") + body
    return struct.pack(">I", len(payload) + 4) + payload


def request(kind, body=b"", track=1):
    """A request as the game sends it to the lobby server: length, kind, tracking number, version, body."""
    payload = struct.pack("<HII", kind, track, 6) + body
    return struct.pack(">I", len(payload) + 4) + payload


def lobby_open(client, conn, lobby_int, port):
    """A connection of the page to the lobby server: the relay's status (0: connected)."""
    client.send(TCP_OPEN, struct.pack(">HIH", conn, lobby_int, port))
    while True:
        number, status = struct.unpack(">HB", client.expect(TCP_OPENED))
        if number == conn:
            return status


def echoed(client, conn, size, timeout=6.0):
    """What the stand-in lobby sent back on a connection (it echoes what reaches it), up to
    'size' bytes; False when the relay closed the connection instead; None when neither."""
    head, got, deadline = struct.pack(">H", conn), b"", time.monotonic() + timeout
    while len(got) < size:
        message = client.recv(max(0.01, deadline - time.monotonic()))
        if message is None:
            return None
        if message[0] == R_TCP_DATA and message[1][:2] == head:
            got += message[1][2:]
        elif message[0] in (TCP_CLOSED, TCP_EOF) and message[1][:2] == head:
            return False
    return got


def passes(client, conn, message, timeout=6.0):
    """Sends bytes on a connection to the lobby: did they get there and come back?"""
    client.send(TCP_DATA, struct.pack(">H", conn) + message)
    return echoed(client, conn, len(message), timeout) == message


def nstr(text):
    return struct.pack("<I", len(text)) + text.encode()


def wstr(text):
    return struct.pack("<I", len(text)) + text.encode("utf-16-le")


def wants_in(own_network, observed):
    """Notification 0x65: a player wants into this player's game - its own-network pair, then the pair the server observed."""
    return lobby_message(0x65, nstr(own_network[0]) + struct.pack("<I", own_network[1]) + nstr(observed[0]) + struct.pack("<I", observed[1]), reply=False)


def game_list(games):
    """Reply 0x55: eight arrays; games are (own-network pair, observed pair)."""
    count = struct.pack("<I", len(games))
    body = count + b"".join(wstr("01,00,00,00,01|game %d at 203.0.113.%d" % (i, i)) for i in range(len(games)))
    body += count + b"".join(wstr("1") for _ in games) + count + b"".join(struct.pack("<I", 100 + i) for i in range(len(games)))
    body += count + b"".join(struct.pack("<I", 3) + b"\xff\x00\xfe" for _ in games)
    body += count + b"".join(wstr(g[0][0]) for g in games) + count + b"".join(struct.pack("<I", g[0][1]) for g in games)
    body += count + b"".join(wstr(g[1][0]) for g in games) + count + b"".join(struct.pack("<I", g[1][1]) for g in games)
    return lobby_message(0x55, body)


def start_relay(lobby, address, *more):
    listen = socket.socket()
    listen.bind(("127.0.0.1", 0))
    port = listen.getsockname()[1]
    listen.close()
    relay = subprocess.Popen([sys.executable, os.path.join(HERE, "relay.py"), "--lobby", address, "--listen", "127.0.0.1:%d" % port, "--tcp-ports", str(lobby.tcp_port),
                              "--udp-port", str(lobby.udp_port), "--test-loopback", "--per-address", "3", "--origin", "http://test.invalid", "--max-message", "2048", "--silent", "6",
                              "--new-sessions", "200"] + list(more),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return relay, "ws://127.0.0.1:%d/relay" % port


class Outside:
    """A stand-in for a player outside the relay: a UDP socket on this computer."""

    def __init__(self, address):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((address, 0))
        self.pair = self.sock.getsockname()
        self.address = address

    def send(self, data, port):
        self.sock.sendto(data, (self.address, port))

    def recv(self, timeout=0.4):
        self.sock.settimeout(timeout)
        try:
            return self.sock.recvfrom(2048)
        except socket.timeout:
            return None


def said_by_lobby(client, conn, message):
    """The stand-in echoes: what the page sends on its lobby connection comes back as the server's words."""
    client.send(TCP_DATA, struct.pack(">H", conn) + message)
    got = b""
    while len(got) < len(message):
        got += client.expect(R_TCP_DATA)[2:]


def parser_checks(check):
    sys.path.insert(0, HERE)
    import relay as program
    pair = lambda text, port: (struct.unpack(">I", socket.inet_aton(text))[0], port)
    listed = game_list([(("192.168.0.9", 4000), ("198.51.100.7", 4001)), (("10.0.0.2", 4002), ("203.0.113.9", 50123))])
    found_by_name = lobby_message(0x57, wstr("Test") + struct.pack("<I", 5) + wstr("192.168.0.9") + struct.pack("<I", 4000) + wstr("198.51.100.8") + struct.pack("<I", 4003))
    chat = lobby_message(0x0F, nstr("198.51.100.99") + struct.pack("<I", 4000) + nstr("198.51.100.99") + struct.pack("<I", 4000), reply=False)
    stream = listed + chat + found_by_name + wants_in(("192.168.0.9", 4000), ("198.51.100.20", 4004)) + lobby_message(0x55, struct.pack("<8I", *[0] * 8), result=1)
    reader = program.LobbyReader()
    whole = reader.feed(stream)
    wanted = [pair("198.51.100.7", 4001), pair("203.0.113.9", 50123), pair("198.51.100.8", 4003), pair("198.51.100.20", 4004)]
    check("lobby messages: the observed address of a listed game's host, of a game found by name and of a player who wants in are read; own-network addresses, texts and other messages are not", whole == wanted, repr(whole))
    reader, pieces = program.LobbyReader(), []
    for i in range(len(stream)):
        pieces.extend(reader.feed(stream[i:i + 1]))
    check("lobby messages: the same when they arrive a byte at a time", pieces == wanted)
    reader = program.LobbyReader()
    odd = reader.feed(lobby_message(0x65, b"\xff" * 9, reply=False) + lobby_message(0x55, struct.pack("<I", 4000000)) + lobby_message(0x99, bytes(70000)) + wants_in(("x", 1), ("198.51.100.21", 4000)) + wants_in(("x", 1), ("not an address", 4000)))
    check("lobby messages: a message that is not as expected names nobody and the next one is still read", odd == [pair("198.51.100.21", 4000)], repr(odd))


def selftest():
    address = "127.0.0.1"  # the stand-in is on this computer and nothing leaves it
    lobby = StandIn(address)
    # --lan: the stand-in players are on this computer, which is not a public address
    relay, url = start_relay(lobby, address, "--lan")
    results = []

    def check(name, good, detail=""):
        results.append(good)
        print("%-4s %s%s" % ("ok" if good else "FAIL", name, (": " + detail) if detail and not good else ""))

    try:
        lobby_int = struct.unpack(">I", socket.inet_aton(address))[0]
        for what, target, origin, wanted in (("another path", url + "x", "http://test.invalid", "404"), ("a page from elsewhere", url, "http://other.invalid", "403"), ("no origin", url, None, "403")):
            try:
                Client(target, origin)
                check("refused: " + what, False)
            except Gone as error:
                check("refused: " + what, wanted in str(error), str(error))
        a = Client(url, "http://test.invalid")
        welcome = a.hello()
        check("welcome names the lobby server and this host", welcome["lobby"] == lobby_int and welcome["own"] == lobby_int)
        # TCP: there and back, the end from the server's side, the end from ours
        a.send(TCP_OPEN, struct.pack(">HIH", 1, lobby_int, lobby.tcp_port))
        check("TCP to the lobby port connects", struct.unpack(">HB", a.expect(TCP_OPENED)) == (1, 0))
        check("TCP bytes go there and come back", passes(a, 1, request(0x42, b"hello lobby")))
        a.send(TCP_DATA, struct.pack(">H", 1) + request(0x42, b"hang up"))
        check("the server's close arrives as an end", a.expect(TCP_EOF) == struct.pack(">H", 1))
        a.send(TCP_CLOSE, struct.pack(">H", 1))
        a.send(TCP_OPEN, struct.pack(">HIH", 2, lobby_int, lobby.tcp_port + 1 if lobby.tcp_port < 65535 else 1))
        check("TCP to another port is refused", struct.unpack(">HB", a.expect(TCP_OPENED)) == (2, 1))
        a.send(TCP_OPEN, struct.pack(">HIH", 3, 0x7F000002, lobby.tcp_port))
        check("TCP to another address is refused", struct.unpack(">HB", a.expect(TCP_OPENED)) == (3, 1))
        # UDP: the stand-in sees the session's socket; a datagram to anywhere else is refused
        a.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, lobby.udp_port) + b"discovery")
        bound = struct.unpack(">BH", a.expect(UDP_BOUND))
        data, sender = lobby.udp.recvfrom(100)
        check("the lobby server sees the datagram from the session's socket", data == b"discovery" and sender == (address, bound[1]), "%r from %r, socket %r" % (data, sender, bound))
        a.send(UDP_SEND, struct.pack(">BIH", 0, 0xE0000001, 53) + b"x")
        a.send(UDP_SEND, struct.pack(">BIH", 0, 0x7F000002, lobby.udp_port) + b"x")
        a.send(PING, b"1")
        a.expect(PONG)
        check("datagrams to addresses no player can have are refused and said so", sum("datagram" in text for _, text in a.notices) == 2, repr(a.notices))
        b = Client(url, "http://test.invalid")
        b.hello()
        # page to page: handed over only when the receiving page wants to hear from the sender
        c = Client(url, "http://test.invalid")
        c.hello()
        b.send(UDP_OPEN, b"\x00")
        port_b = struct.unpack(">BH", b.expect(UDP_BOUND))[1]
        c.send(UDP_OPEN, b"\x00")
        port_c = struct.unpack(">BH", c.expect(UDP_BOUND))[1]
        a.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, port_b) + b"unasked")
        a.send(PING, b"2")
        a.expect(PONG)
        check("a page alone cannot make another page receive: its datagram for a page that has not sent to it is not handed over", b.recv(0.4) is None)
        b.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, bound[1]) + b"asked")
        check("... until that page has sent to it as well", a.expect(UDP_RECV, 2) == struct.pack(">BIH", 0, lobby_int, port_b) + b"asked")
        lobby_open(b, 1, lobby_int, lobby.tcp_port)
        said_by_lobby(b, 1, wants_in((address, 1), (address, port_c)))
        c.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, port_b) + b"named")
        check("a page the lobby server named to another page is heard there at once", b.expect(UDP_RECV, 2) == struct.pack(">BIH", 0, lobby_int, port_c) + b"named")
        b.send(TCP_CLOSE, struct.pack(">H", 1))
        c.close()
        times, lost, ports = player_to_player(a, b, lobby_int, count=50, gap=0)
        check("datagrams go from one session to the other and back, with the sender's socket as their source", len(times) == 50 and lost == 0)
        check("the first session's socket is the one the lobby server saw", ports[0] == bound[1])
        # players outside: a path opens when the lobby server named the address, or when each has sent to the other
        mine = ports[0]
        to = lambda player, data: a.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, player.pair[1]) + data)
        heard = lambda player, data: a.expect(UDP_RECV, 2) == struct.pack(">BIH", 0, lobby_int, player.pair[1]) + data
        one, two, three, four = Outside(address), Outside(address), Outside(address), Outside(address)
        to(one, b"anyone there")
        check("a page alone opens no path: what it sends to an address nobody named is not sent", one.recv() is None)
        one.send(b"here", mine)
        check("... until that address has sent as well: its datagram is passed on, with its address", heard(one, b"here"))
        to(one, b"hello")
        check("... and the page's next one arrives there, from the session's socket", one.recv() == (b"hello", (address, mine)))
        to(one, bytes(1600))
        to(one, b"small")
        check("a datagram larger than any the game sends a player is not sent on", one.recv() == (b"small", (address, mine)))
        two.send(b"knock", mine)
        check("a stranger alone opens no path: a datagram from outside is not passed on", a.recv(0.5) is None)
        to(two, b"come in")
        got = two.recv()
        two.send(b"thanks", mine)
        check("... until the page has sent to it as well", got == (b"come in", (address, mine)) and heard(two, b"thanks"))
        a.send(TCP_OPEN, struct.pack(">HIH", 5, lobby_int, lobby.tcp_port))
        a.expect(TCP_OPENED)
        said_by_lobby(a, 5, wants_in((address, four.pair[1]), (address, three.pair[1])))
        to(three, b"welcome")
        got = three.recv()
        three.send(b"joining", mine)
        check("an address the lobby server named (the observed one) is reached at once, and answers", got == (b"welcome", (address, mine)) and heard(three, b"joining"))
        to(four, b"welcome")
        check("the own-network address in the same message is not taken", four.recv() is None)
        a.send(TCP_CLOSE, struct.pack(">H", 5))
        parser_checks(check)
        # without --lan only public addresses are reached; with --pages-only nobody outside
        plain, plain_url = start_relay(lobby, address)
        try:
            p = Client(plain_url, "http://test.invalid")
            p.hello()
            p.send(UDP_OPEN, b"\x00")
            there = struct.unpack(">BH", p.expect(UDP_BOUND))[1]
            five = Outside(address)
            p.send(TCP_OPEN, struct.pack(">HIH", 1, lobby_int, lobby.tcp_port))
            p.expect(TCP_OPENED)
            said_by_lobby(p, 1, wants_in((address, five.pair[1]), (address, five.pair[1])) + wants_in(("192.168.0.9", five.pair[1]), ("192.168.0.9", five.pair[1])))
            five.send(b"knock", there)
            p.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, five.pair[1]) + b"x")
            check("without --lan nothing passes to or from an address that is not public, named or not", five.recv() is None and p.recv(0.3) is None)
            p.close()
        finally:
            plain.terminate()
            plain.communicate(timeout=5)
        a.send(PING, b"2")  # the first relay drops a page it does not hear
        a.expect(PONG)
        only, only_url = start_relay(lobby, address, "--pages-only")
        try:
            p = Client(only_url, "http://test.invalid")
            p.hello()
            p.send(UDP_OPEN, b"\x00")
            there = struct.unpack(">BH", p.expect(UDP_BOUND))[1]
            six = Outside(address)
            six.send(b"knock", there)
            p.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, six.pair[1]) + b"x")
            p.send(UDP_SEND, struct.pack(">BIH", 0, 0x7F000002, six.pair[1]) + b"x")
            p.send(PING, b"1")
            p.expect(PONG)
            check("with --pages-only nothing passes to or from outside, and a datagram for another host is refused and said so",
                  six.recv() is None and p.recv(0.3) is None and sum("players of this relay" in text for _, text in p.notices) == 1, repr(p.notices))
            p.close()
        finally:
            only.terminate()
            only.communicate(timeout=5)
        timing = "timing on this computer (load %.1f): ping %s\n" % (os.getloadavg()[0], figures(ping_times(a, 100, 0.002)))
        timing += "                                    player to player and back %s" % figures(times)
        # limits
        b.close()
        time.sleep(0.3)
        b = Client(url, "http://test.invalid")
        b.hello()
        c = Client(url, "http://test.invalid")
        c.hello()
        try:
            d = Client(url, "http://test.invalid")
            d.send(HELLO, b"\x01")
            d.recv(2)
            check("a fourth session from one address is not taken", False)
        except Gone:
            check("a fourth session from one address is not taken", True)
        try:
            d = Client(url, "http://test.invalid", headers=[("X-Real-IP", "198.51.100.77"), ("X-Forwarded-For", "198.51.100.77")])
            d.send(HELLO, b"\x01")
            d.recv(2)
            check("... nor one that claims another address in a header: this relay was not told of a web server in front", False)
        except Gone:
            check("... nor one that claims another address in a header: this relay was not told of a web server in front", True)
        try:
            c.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, lobby.udp_port) + bytes(3000))
            c.recv(2)
            check("a message that is too large ends the session", False)
        except (Gone, OSError):
            check("a message that is too large ends the session", True)
        try:
            b.recv(9)
            check("a page that says nothing is dropped", False)
        except Gone:
            check("a page that says nothing is dropped", True)
        a.close()
    except Exception:
        relay.terminate()
        print(relay.communicate(timeout=5)[0][-1500:])
        raise
    finally:
        relay.terminate()
        output = relay.communicate(timeout=5)[0]
    check("the relay ended cleanly", "relay: stopped" in output, output[-400:])
    counted = [line for line in output.splitlines() if line.find("session 1 ") > 0 and "ended" in line]
    check("the relay's log counts what it did not send and did not pass on", bool(counted) and "3 path(s)" in counted[0] and " 2 not sent (no path), 1 not passed on (no path)" in counted[0], counted[0] if counted else output[-600:])
    print("relay log: %d lines; %d session(s) opened" % (len(output.splitlines()), output.count(" opened;")))
    print(timing)
    return all(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", help="ws:// or wss:// address of a running relay")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--origin", help="the page's origin, when the relay asks for one")
    parser.add_argument("--gateway-port", type=int, default=40810)
    parser.add_argument("--count", type=int, default=200, help="exchanges to time (default 200)")
    args = parser.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if not args.url:
        parser.error("give the relay's address, or --selftest")
    try:
        sys.exit(0 if check_running(args) else 1)
    except Gone as error:
        sys.exit("check.py: %s" % error)


if __name__ == "__main__":
    main()
