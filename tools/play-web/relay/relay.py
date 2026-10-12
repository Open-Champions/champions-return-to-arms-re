#!/usr/bin/env python3
"""The relay of the browser build: what stands in for the sockets a web page does not have.

A page of the browser build (tools/play-web) opens ONE WebSocket connection to this
program. Through it the emulated console's network (tools/play-net/src/RtaNet.cpp,
compiled into the page) asks for what the desktop application does with sockets of its
own:

  TCP   connections to the lobby server - to the configured lobby host and the configured
        ports only (the gateway port and the lobby port), nothing else;
  UDP   one socket here per UDP port the console uses, kept for the session and used for
        every destination. The lobby server sees a browser player at this host's address
        and that socket's port, exactly as it sees a desktop player's router. A datagram
        may go to two kinds of destination only: the lobby server's discovery port, and
        the UDP socket of another session of this relay (browser players play with
        browser players; such a datagram is handed over inside this program). Nothing
        that arrives from outside on those sockets is passed on to a page.

So this is not a proxy to anywhere: a page can reach the lobby server and the other
pages, and that is all.

    relay.py --lobby 192.0.2.10                        # ws://127.0.0.1:8975/relay
    relay.py --lobby 192.0.2.10 --listen 127.0.0.1:8975 --path /relay \\
             --origin https://play.example --trust-proxy

Python 3.8 or later, standard library only (the WebSocket handshake and framing are
written out below: RFC 6455, binary messages, no extensions). It listens on a loop-back
address by default: put a web server in front for TLS (a page served over https may only
open wss://) and let it hand the connection on (README.md beside this file).

Messages (one per binary WebSocket message; numbers big-endian):

  page -> relay                               relay -> page
  01 HELLO      u8 version (1)                81 WELCOME    u8 version, u32 lobby address,
  02 TCP_OPEN   u16 id, u32 address, u16 port               u32 this relay's address, u16 idle
  03 TCP_DATA   u16 id, bytes                               seconds, u16 largest message
  04 TCP_SHUT   u16 id   (no more to send)    82 TCP_OPENED u16 id, u8 status (0 connected,
  05 TCP_CLOSE  u16 id                                      1 not allowed, 2 refused, 3 timed
  06 UDP_OPEN   u8 socket                                   out, 4 unreachable, 5 too many)
  07 UDP_SEND   u8 socket, u32 address,       83 TCP_DATA   u16 id, bytes
                u16 port, bytes               84 TCP_EOF    u16 id   (the server sends no more)
  08 UDP_CLOSE  u8 socket                     85 TCP_CLOSED u16 id   (gone)
  09 PING       up to 16 bytes                86 UDP_BOUND  u8 socket, u16 port (here)
                                              87 UDP_RECV   u8 socket, u32 address, u16 port, bytes
                                              89 PONG       the same bytes
                                              8A NOTICE     u8 code, text (why something was
                                                            refused, or why the session ends)
"""
import argparse
import asyncio
import base64
import hashlib
import ipaddress
import signal
import socket
import struct
import sys
import time

VERSION = 1
HELLO, TCP_OPEN, TCP_DATA, TCP_SHUT, TCP_CLOSE, UDP_OPEN, UDP_SEND, UDP_CLOSE, PING = range(1, 10)
WELCOME, TCP_OPENED, R_TCP_DATA, TCP_EOF, TCP_CLOSED, UDP_BOUND, UDP_RECV, PONG, NOTICE = 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x89, 0x8A
OK, NOT_ALLOWED, REFUSED, TIMED_OUT, UNREACHABLE, TOO_MANY = range(6)
# NOTICE codes
N_FULL, N_ADDRESS_FULL, N_IDLE, N_PROTOCOL, N_NOT_ALLOWED, N_TOO_MUCH, N_STOPPING = range(1, 8)

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_TCP = 4          # connections of one session at a time (the game has one or two)
MAX_UDP = 8          # UDP sockets of one session (the game uses one of its ports 4000-4004)
WRITE_HIGH = 1 << 20  # bytes waiting for a page before its datagrams are dropped


def log(text):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + text, flush=True)


def ip_int(text):
    return int(ipaddress.IPv4Address(text))


def ip_text(number):
    return str(ipaddress.IPv4Address(number))


class Stop(Exception):
    """The session ends: a NOTICE code and words for the page and the log."""

    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


class Bucket:
    """So many units a second, with a reserve of twice that."""

    def __init__(self, rate):
        self.rate = rate
        self.level = rate * 2.0
        self.at = time.monotonic()

    def take(self, units=1):
        now = time.monotonic()
        self.level = min(self.rate * 2.0, self.level + (now - self.at) * self.rate)
        self.at = now
        if self.level < units:
            return False
        self.level -= units
        return True


def frame(opcode, payload):
    n = len(payload)
    if n < 126:
        head = bytes((0x80 | opcode, n))
    elif n < 65536:
        head = bytes((0x80 | opcode, 126)) + struct.pack(">H", n)
    else:
        head = bytes((0x80 | opcode, 127)) + struct.pack(">Q", n)
    return head + payload


async def read_frame(reader, largest):
    """One frame from a browser: (opcode, payload). Browsers mask what they send."""
    head = await reader.readexactly(2)
    opcode, n = head[0] & 0x0F, head[1] & 0x7F
    if head[0] & 0x70 or not head[0] & 0x80 or not head[1] & 0x80:
        raise Stop(N_PROTOCOL, "a WebSocket frame this relay does not take (extension bits, fragment, or not masked)")
    if n == 126:
        n = struct.unpack(">H", await reader.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", await reader.readexactly(8))[0]
    if n > largest:
        raise Stop(N_PROTOCOL, "a message of %d bytes (the largest taken is %d)" % (n, largest))
    key = await reader.readexactly(4)
    data = await reader.readexactly(n)
    if n:
        mask = (key * (n // 4 + 1))[:n]
        data = (int.from_bytes(data, "big") ^ int.from_bytes(mask, "big")).to_bytes(n, "big")
    return opcode, data


class Tcp:
    def __init__(self):
        self.writer = None
        self.task = None
        self.shut = False


class Udp:
    def __init__(self, sock, port):
        self.sock = sock
        self.port = port


class Session:
    def __init__(self, relay, reader, writer, address, number):
        self.relay, self.reader, self.writer = relay, reader, writer
        self.address, self.number = address, number
        self.tcp, self.udp = {}, {}
        self.greeted = False
        self.closed = False
        self.last_use = time.monotonic()
        self.messages = Bucket(relay.args.message_rate)
        self.bytes = Bucket(relay.args.byte_rate)
        self.counts = {"tcp": 0, "tcp_out": 0, "tcp_in": 0, "udp_lobby": 0, "udp_peer": 0, "udp_in": 0, "udp_dropped": 0, "refused": 0}
        self.noticed = set()

    # ---- to the page
    def send(self, kind, payload=b""):
        if self.closed:
            return False
        try:
            self.writer.write(frame(2, bytes((kind,)) + payload))
        except (ConnectionError, RuntimeError, OSError):
            return False
        return True

    def notice(self, code, text):
        self.send(NOTICE, bytes((code,)) + text.encode("utf-8")[:300])

    def waiting(self):
        return self.writer.transport.get_write_buffer_size()

    # ---- the session
    async def run(self):
        relay = self.relay
        why = "the page closed the connection"
        try:
            while True:
                try:
                    opcode, data = await asyncio.wait_for(read_frame(self.reader, relay.args.max_message), relay.args.silent)
                except asyncio.TimeoutError:
                    raise Stop(N_IDLE, "nothing heard from the page for %d seconds" % relay.args.silent)
                if opcode == 8:
                    break
                if opcode == 9:
                    self.writer.write(frame(10, data))
                    continue
                if opcode == 10:
                    continue
                if opcode != 2 or not data:
                    raise Stop(N_PROTOCOL, "not a binary message")
                self.message(data[0], data[1:])
        except Stop as stop:
            why = str(stop)
            self.notice(stop.code, why)
        except asyncio.IncompleteReadError:
            why = "the connection to the page ended without a goodbye"
        except (ConnectionError, OSError) as error:
            why = "the connection to the page was lost (%s)" % (type(error).__name__ + (": " + str(error) if str(error) else ""))
        except (struct.error, IndexError):
            why = "a message too short for its kind"
            self.notice(N_PROTOCOL, why)
        finally:
            self.close(why)

    def close(self, why):
        if self.closed:
            return
        for conn in self.tcp.values():
            self.tcp_drop(conn)
        self.tcp.clear()
        for sock_id in list(self.udp):
            self.udp_close(sock_id)
        try:
            self.writer.write(frame(8, struct.pack(">H", 1000)))
            self.writer.close()
        except (ConnectionError, RuntimeError, OSError):
            pass
        self.closed = True
        self.relay.gone(self)
        c = self.counts
        log("session %d (%s) ended: %s; %d TCP connection(s), %d bytes to the lobby, %d from it; datagrams: %d to the lobby, %d to players, %d from players, %d dropped, %d refused"
            % (self.number, self.address, why, c["tcp"], c["tcp_out"], c["tcp_in"], c["udp_lobby"], c["udp_peer"], c["udp_in"], c["udp_dropped"], c["refused"]))

    def idle(self):
        """Nothing open towards the lobby and nothing sent for the idle time."""
        return not self.tcp and time.monotonic() - self.last_use > self.relay.args.idle

    def message(self, kind, body):
        relay = self.relay
        if not self.greeted:
            if kind != HELLO or len(body) < 1 or body[0] != VERSION:
                raise Stop(N_PROTOCOL, "the page speaks another version of the relay's messages")
            self.greeted = True
            self.send(WELCOME, struct.pack(">BIIHH", VERSION, relay.lobby_int, relay.own_int, min(relay.args.idle, 65535), relay.args.max_message))
            return
        if kind == PING:
            self.send(PONG, body[:16])
            return
        if not self.messages.take() or not self.bytes.take(len(body)):
            if kind == UDP_SEND:
                self.counts["udp_dropped"] += 1  # a datagram too many is lost, as on any line
                return
            raise Stop(N_TOO_MUCH, "more data than a game sends")
        self.last_use = time.monotonic()
        if kind == UDP_SEND:
            sock_id, address, port = struct.unpack(">BIH", body[:7])
            self.udp_send(sock_id, address, port, body[7:])
        elif kind == TCP_DATA:
            conn = self.tcp.get(struct.unpack(">H", body[:2])[0])
            if conn and conn.writer and not conn.shut:
                conn.writer.write(body[2:])
                self.counts["tcp_out"] += len(body) - 2
                if conn.writer.transport.get_write_buffer_size() > WRITE_HIGH:
                    raise Stop(N_TOO_MUCH, "the lobby server does not take the data as fast as the page sends it")
        elif kind == TCP_OPEN:
            conn_id, address, port = struct.unpack(">HIH", body[:8])
            self.tcp_open(conn_id, address, port)
        elif kind == TCP_SHUT:
            conn = self.tcp.get(struct.unpack(">H", body[:2])[0])
            if conn and conn.writer and not conn.shut:
                conn.shut = True
                try:
                    conn.writer.write_eof()
                except (OSError, RuntimeError):
                    pass
        elif kind == TCP_CLOSE:
            conn = self.tcp.pop(struct.unpack(">H", body[:2])[0], None)
            if conn:
                self.tcp_drop(conn)
        elif kind == UDP_OPEN:
            known = body[0] in self.udp
            entry = self.udp_get(body[0])
            if known:  # asked again: told again
                self.send(UDP_BOUND, struct.pack(">BH", body[0], entry.port))
        elif kind == UDP_CLOSE:
            self.udp_close(body[0])
        else:
            raise Stop(N_PROTOCOL, "a message of a kind this relay does not know (%d)" % kind)

    def refuse(self, what):
        self.counts["refused"] += 1
        if what not in self.noticed and len(self.noticed) < 8:
            self.noticed.add(what)
            self.notice(N_NOT_ALLOWED, what)
            log("session %d (%s): refused: %s" % (self.number, self.address, what))

    # ---- TCP: to the lobby server only
    def tcp_open(self, conn_id, address, port):
        relay = self.relay
        if conn_id in self.tcp:
            raise Stop(N_PROTOCOL, "a TCP connection number used twice")
        if address != relay.lobby_int or port not in relay.tcp_ports:
            self.refuse("a TCP connection to %s:%d (only the lobby server's own ports are reached)" % (ip_text(address), port))
            self.send(TCP_OPENED, struct.pack(">HB", conn_id, NOT_ALLOWED))
            return
        if len(self.tcp) >= MAX_TCP:
            self.send(TCP_OPENED, struct.pack(">HB", conn_id, TOO_MANY))
            return
        conn = self.tcp[conn_id] = Tcp()
        conn.task = asyncio.ensure_future(self.tcp_run(conn_id, conn, port))

    async def tcp_run(self, conn_id, conn, port):
        relay = self.relay
        status = OK
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(relay.lobby_text, port), relay.args.connect_timeout)
        except asyncio.TimeoutError:
            status = TIMED_OUT
        except ConnectionRefusedError:
            status = REFUSED
        except OSError:
            status = UNREACHABLE
        if status != OK:
            if self.tcp.get(conn_id) is conn:
                del self.tcp[conn_id]
            self.send(TCP_OPENED, struct.pack(">HB", conn_id, status))
            return
        conn.writer = writer
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.counts["tcp"] += 1
        self.send(TCP_OPENED, struct.pack(">HB", conn_id, OK))
        head = struct.pack(">H", conn_id)
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    self.send(TCP_EOF, head)
                    return  # the page closes it when the console has
                self.counts["tcp_in"] += len(data)
                self.last_use = time.monotonic()
                self.send(R_TCP_DATA, head + data)
                await self.writer.drain()
        except (ConnectionError, OSError):
            if self.tcp.get(conn_id) is conn:
                del self.tcp[conn_id]
                self.tcp_drop(conn, cancel=False)
                self.send(TCP_CLOSED, head)

    def tcp_drop(self, conn, cancel=True):
        if cancel and conn.task and not conn.task.done():
            conn.task.cancel()
        if conn.writer:
            try:
                conn.writer.close()
            except (OSError, RuntimeError):
                pass

    # ---- UDP: one socket here per socket of the console's network
    def udp_get(self, sock_id):
        entry = self.udp.get(sock_id)
        if entry:
            return entry
        if sock_id >= MAX_UDP or len(self.udp) >= MAX_UDP:
            raise Stop(N_PROTOCOL, "more UDP sockets than a game uses")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)  # nothing is read from it
        except OSError:
            pass
        sock.bind(("0.0.0.0", 0))
        entry = self.udp[sock_id] = Udp(sock, sock.getsockname()[1])
        self.relay.ports[entry.port] = (self, sock_id)
        self.send(UDP_BOUND, struct.pack(">BH", sock_id, entry.port))
        return entry

    def udp_close(self, sock_id):
        entry = self.udp.pop(sock_id, None)
        if entry:
            self.relay.ports.pop(entry.port, None)
            entry.sock.close()

    def udp_send(self, sock_id, address, port, data):
        relay = self.relay
        entry = self.udp_get(sock_id)
        if address == relay.lobby_int and port == relay.args.udp_port:
            # the discovery datagram: the lobby server learns this socket's address from it
            try:
                entry.sock.sendto(data, (relay.lobby_text, port))
                self.counts["udp_lobby"] += 1
            except OSError:
                self.counts["udp_dropped"] += 1
            return
        if address == relay.own_int:
            # another player of this relay (or nobody: a port that is not open loses the datagram)
            target = relay.ports.get(port)
            if target is None:
                self.counts["udp_dropped"] += 1
                return
            other, other_sock = target
            if other.waiting() > WRITE_HIGH:
                self.counts["udp_dropped"] += 1
                return
            self.counts["udp_peer"] += 1
            other.counts["udp_in"] += 1
            other.send(UDP_RECV, struct.pack(">BIH", other_sock, relay.own_int, entry.port) + data)
            return
        self.refuse("a datagram to %s:%d (only the lobby server and players of this relay are reached)" % (ip_text(address), port))


class Relay:
    def __init__(self, args):
        self.args = args
        info = socket.getaddrinfo(args.lobby, None, socket.AF_INET, socket.SOCK_STREAM)
        self.lobby_text = info[0][4][0]
        self.lobby_int = ip_int(self.lobby_text)
        if ipaddress.IPv4Address(self.lobby_text).is_loopback and not args.test_loopback:
            sys.exit("relay.py: --lobby is a loop-back address. The lobby server would then see every player at 127.0.0.1 "
                     "and tell the others to look for them there. Give this computer's network address instead.")
        if args.own_address:
            own = args.own_address
        else:
            # the address this host has towards the lobby server: what the server will see
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect((self.lobby_text, args.udp_port))
            own = probe.getsockname()[0]
            probe.close()
        self.own_text, self.own_int = own, ip_int(own)
        self.tcp_ports = set()
        for part in args.tcp_ports.split(","):
            low, _, high = part.partition("-")
            self.tcp_ports.update(range(int(low), int(high or low) + 1))
        self.sessions = set()
        self.ports = {}  # UDP port here -> (session, its socket number)
        self.count = 0

    def gone(self, session):
        self.sessions.discard(session)

    async def client(self, reader, writer):
        args = self.args
        peer = writer.get_extra_info("peername") or ("?", 0)
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def answer(status, text):
            body = (text + "\n").encode()
            writer.write(("HTTP/1.1 %s\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (status, len(body))).encode() + body)
            writer.close()

        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            lines = head.decode("latin-1").split("\r\n")
            method, target, _ = lines[0].split(" ", 2)
            headers = {}
            for line in lines[1:]:
                name, colon, value = line.partition(":")
                if colon:
                    headers[name.strip().lower()] = value.strip()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, ValueError, OSError):
            writer.close()
            return
        if method != "GET" or target.split("?")[0] != args.path:
            answer("404 Not Found", "not here")
            return
        key = headers.get("sec-websocket-key", "")
        if headers.get("upgrade", "").lower() != "websocket" or headers.get("sec-websocket-version") != "13" or not key:
            answer("426 Upgrade Required", "this is the relay of the browser build: a WebSocket connection is wanted")
            return
        if args.origin and headers.get("origin") not in args.origin:
            answer("403 Forbidden", "not from this page")
            return
        address = peer[0]
        if args.trust_proxy and address in ("127.0.0.1", "::1"):
            try:
                address = str(ipaddress.ip_address(headers.get("x-real-ip", address)))
            except ValueError:
                pass
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        self.count += 1
        session = Session(self, reader, writer, address, self.count)
        full = None
        if len(self.sessions) >= args.max_sessions:
            full = (N_FULL, "the relay is full (%d players); try again later" % len(self.sessions))
        elif sum(1 for other in self.sessions if other.address == address) >= args.per_address:
            full = (N_ADDRESS_FULL, "there are %d pages online from your address already, which is as many as the relay takes" % args.per_address)
        if full:
            session.notice(*full)
            log("session %d (%s) not taken: %s" % (session.number, address, full[1]))
            try:
                writer.write(frame(8, struct.pack(">H", 1013)))
                writer.close()
            except (ConnectionError, OSError):
                pass
            return
        self.sessions.add(session)
        log("session %d (%s) opened; %d open" % (session.number, address, len(self.sessions)))
        await session.run()

    async def sweep(self):
        while True:
            await asyncio.sleep(15)
            for session in list(self.sessions):
                if session.idle():
                    session.notice(N_IDLE, "nothing was sent for %d minutes; the page connects again when the game goes online" % (self.args.idle // 60))
                    session.close("idle")

    async def main(self):
        args = self.args
        host, _, port = args.listen.rpartition(":")
        server = await asyncio.start_server(self.client, host or "127.0.0.1", int(port), limit=8192)
        log("relay: listening on %s%s; lobby server %s (TCP ports %s, UDP %d); this host is %s to it; at most %d sessions, %d from one address%s"
            % (args.listen, args.path, self.lobby_text, args.tcp_ports, args.udp_port, self.own_text, args.max_sessions, args.per_address,
               ("; pages from " + ", ".join(args.origin)) if args.origin else "; pages from anywhere (no --origin)"))
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        for name in ("SIGTERM", "SIGINT"):
            try:
                loop.add_signal_handler(getattr(signal, name), lambda: stop.done() or stop.set_result(None))
            except (NotImplementedError, RuntimeError):
                pass
        sweeper = asyncio.ensure_future(self.sweep())
        await stop
        sweeper.cancel()
        server.close()
        for session in list(self.sessions):
            session.notice(N_STOPPING, "the relay is being stopped")
            session.close("the relay is stopping")
        log("relay: stopped")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lobby", required=True, help="the lobby server, as an address of four numbers or a name; not a loop-back address")
    parser.add_argument("--listen", default="127.0.0.1:8975", help="address:port to listen on (default 127.0.0.1:8975)")
    parser.add_argument("--path", default="/relay", help="the path a page asks for (default /relay); anything else is 404")
    parser.add_argument("--origin", action="append", default=[], help="a page origin that may use the relay (https://host); may be given several times; none: any")
    parser.add_argument("--trust-proxy", action="store_true", help="take the player's address from X-Real-IP when the connection comes from this host (a web server in front)")
    parser.add_argument("--tcp-ports", default="40810,40910", help="the lobby server's TCP ports that may be reached (default 40810,40910: gateway and lobby)")
    parser.add_argument("--udp-port", type=int, default=10101, help="the lobby server's discovery port (default 10101)")
    parser.add_argument("--own-address", help="this host's address as the lobby server sees it (default: found by asking the system)")
    parser.add_argument("--test-loopback", action="store_true", help="for tests of the relay itself: take a loop-back address for --lobby (no game can be played through such a relay)")
    parser.add_argument("--max-sessions", type=int, default=64)
    parser.add_argument("--per-address", type=int, default=4, help="sessions from one address at a time (default 4)")
    parser.add_argument("--idle", type=int, default=900, help="seconds without use, and without a connection to the lobby, after which a session is closed (default 900)")
    parser.add_argument("--silent", type=int, default=60, help="seconds without any message from the page (it pings) after which the session is closed (default 60)")
    parser.add_argument("--max-message", type=int, default=8192, help="largest message taken, in bytes (default 8192)")
    parser.add_argument("--message-rate", type=float, default=600, help="messages a second from one page (default 600; twice that for a moment)")
    parser.add_argument("--byte-rate", type=float, default=262144, help="bytes a second from one page (default 262144)")
    parser.add_argument("--connect-timeout", type=float, default=10)
    args = parser.parse_args()
    try:
        asyncio.run(Relay(args).main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
