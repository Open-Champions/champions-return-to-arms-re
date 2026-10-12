#!/usr/bin/env python3
"""Checks a relay (relay.py) from outside, as a page would use it, and times its path.

    check.py --selftest
        Starts a stand-in lobby server (a TCP port that echoes, a UDP port that notes what
        arrives) and a relay of its own on this computer, and goes through everything the
        relay promises: the two kinds of TCP destination, what is refused, the UDP socket
        the stand-in sees, datagrams from one session to another, the limits.

    check.py ws://127.0.0.1:8975/relay
    check.py wss://HOST/PATH/relay --origin https://HOST [--gateway-port 40810]
        A running relay. Opens two sessions; asks for one TCP connection to the lobby
        server's gateway port and closes it again WITHOUT SENDING A BYTE (no request, no
        log-in); asks for a destination that must be refused; sends datagrams from one
        session to the other and back and times them. Nothing is sent to the lobby
        server's discovery port.

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

    def __init__(self, url, origin=None, timeout=10.0):
        parts = urlparse(url)
        secure = parts.scheme == "wss"
        port = parts.port or (443 if secure else 80)
        raw = socket.create_connection((parts.hostname, port), timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parts.hostname) if secure else raw
        key = base64.b64encode(os.urandom(16)).decode()
        request = "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n" % (parts.path or "/", parts.netloc, key)
        if origin:
            request += "Origin: %s\r\n" % origin
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
    times = []
    lost = 0
    for i in range(count):
        body = struct.pack(">I", i) + bytes(size - 4)
        start = time.perf_counter()
        a.send(UDP_SEND, struct.pack(">BIH", 0, own, port_b) + body)
        try:
            sock, address, port = struct.unpack(">BIH", b.expect(UDP_RECV, 2)[:7])
            if (address, port) != (own, port_a):
                raise Gone("the datagram came from %s:%d, not from the sender's socket %s:%d" % (ip_text(address), port, ip_text(own), port_a))
            b.send(UDP_SEND, struct.pack(">BIH", 0, own, port_a) + body)
            a.expect(UDP_RECV, 2)
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
    a.send(UDP_SEND, struct.pack(">BIH", 1, 0x01010101, 53) + b"x")
    a.send(PING, b"end")
    a.expect(PONG)
    refused_udp = any("datagram" in text for _, text in a.notices)
    print("refused, as it must be: TCP to another port of the lobby server: %s; TCP to another host: %s; a datagram to another host: %s"
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
                if data == b"hang up":
                    break
                conn.sendall(data)
        except OSError:
            pass
        conn.close()


def selftest():
    address = "127.0.0.1"  # the stand-in is on this computer and nothing leaves it
    lobby = StandIn(address)
    listen = socket.socket()
    listen.bind(("127.0.0.1", 0))
    port = listen.getsockname()[1]
    listen.close()
    relay = subprocess.Popen([sys.executable, os.path.join(HERE, "relay.py"), "--lobby", address, "--listen", "127.0.0.1:%d" % port, "--tcp-ports", str(lobby.tcp_port),
                              "--udp-port", str(lobby.udp_port), "--test-loopback", "--per-address", "3", "--origin", "http://test.invalid", "--max-message", "2048", "--silent", "4"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = "ws://127.0.0.1:%d/relay" % port
    results = []

    def check(name, good, detail=""):
        results.append(good)
        print("%-4s %s%s" % ("ok" if good else "FAIL", name, (": " + detail) if detail and not good else ""))

    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
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
        a.send(TCP_DATA, struct.pack(">H", 1) + b"hello lobby")
        check("TCP bytes go there and come back", a.expect(R_TCP_DATA) == struct.pack(">H", 1) + b"hello lobby")
        a.send(TCP_DATA, struct.pack(">H", 1) + b"hang up")
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
        a.send(UDP_SEND, struct.pack(">BIH", 0, 0x08080808, 53) + b"x")
        a.send(UDP_SEND, struct.pack(">BIH", 0, 0x7F000002, lobby.udp_port) + b"x")
        a.send(PING, b"1")
        a.expect(PONG)
        check("datagrams to other hosts are refused and said so", sum("datagram" in text for _, text in a.notices) == 2, repr(a.notices))
        b = Client(url, "http://test.invalid")
        b.hello()
        times, lost, ports = player_to_player(a, b, lobby_int, count=50, gap=0)
        check("datagrams go from one session to the other and back, with the sender's socket as their source", len(times) == 50 and lost == 0)
        check("the first session's socket is the one the lobby server saw", ports[0] == bound[1])
        # nothing from outside reaches a page
        outside = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        outside.sendto(b"from outside", (address, ports[0]))
        outside.close()
        check("a datagram from outside is not passed on", a.recv(0.5) is None)
        timing = "timing on this computer (load %.1f): ping %s\n" % (os.getloadavg()[0], figures(ping_times(a, 100, 0.002)))
        timing += "                                    player to player and back %s" % figures(times)
        # limits
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
            c.send(UDP_SEND, struct.pack(">BIH", 0, lobby_int, lobby.udp_port) + bytes(3000))
            c.recv(2)
            check("a message that is too large ends the session", False)
        except (Gone, OSError):
            check("a message that is too large ends the session", True)
        try:
            b.recv(6)
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
