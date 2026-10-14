#!/usr/bin/env python3
"""rendezvous.py - the meeting place of the native build's own online play.

No accounts, no passwords, no e-mail.  A player is a device secret (the client keeps it in
one small file); the service knows its verifier and gives the player an id, a display name
(a label) and a friend code that can be read out loud.  On top of that: friends (asked by
code, accepted by the other side), presence with the character a friend is playing,
invitations, rooms that are hosted and joined by a short code, chat lines and ready marks
in a room, and the start of a game - every machine of the room gets the same session
description and the addresses the service SAW the others' UDP sockets at, to punch through
their routers; when two machines cannot reach each other the service relays their
datagrams (only between members of one started room, rate-limited).

  python3 tools/rendezvous/rendezvous.py --data DIR [--port 41900] [--bind 127.0.0.1]...
          [--limit NAME=VALUE]... [--quiet] [--status-every SECONDS]

  --bind    an address to listen on; may be given several times.  Default 127.0.0.1 only.
            0.0.0.0 (every address of the machine) is refused unless --public is given:
            putting the service on the Internet is a decision, not a default.
  --port    one number for both: TCP (the conversation) and UDP (hello, relay).
  --data    the directory of the one file the service keeps, rendezvous.db (SQLite);
            ":memory:" keeps nothing.
  --limit   one of LIMITS below, for a test that wants to hit it.

Standard library only.  docs/issues/native-rendezvous.md has the wire format, what is
stored and for how long, and the limits; tools/rendezvous/check.py is the self-test.
"""
import argparse
import hashlib
import hmac
import os
import secrets
import selectors
import socket
import sqlite3
import struct
import sys
import time

VERSION = 1
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'    # no I, O, 0, 1: a code can be read out
SAFE = set(b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-,:')

LIMITS = {
    # connections
    'connections': 2000,            # at once, all told
    'connections_per_address': 12,  # at once, from one address
    'line_bytes': 1024,             # one line of the conversation
    'lines_per_second': 20,         # per connection, sustained ...
    'lines_burst': 60,              # ... and at once
    'login_seconds': 10,            # a connection that has not logged in by then is closed
    'idle_seconds': 90,             # a connection that says nothing for so long is closed (clients ping every 20 s)
    'output_bytes': 262144,         # waiting to be read by a client; more: it is closed
    # identity
    'registrations_per_hour': 10,   # new players from one address
    'bad_logins_per_minute': 10,    # from one address
    # players
    'name_bytes': 24,
    'label_bytes': 24,              # a character's name, a class, a level's name
    'friends': 200,                 # per player
    'requests_open': 20,            # friend requests of one player not yet answered
    'requests_per_hour': 10,
    'blocks': 500,
    'recent': 50,                   # recent players kept per player
    'invites_per_hour': 30,
    'invite_repeat_seconds': 10,    # the same friend again
    'invite_seconds': 600,          # an invitation that nobody answered goes away
    # rooms
    'rooms': 5000,
    'rooms_per_address': 4,
    'room_idle_seconds': 7200,      # an open room in which nothing happens
    'room_game_seconds': 43200,     # a started game the service still knows of
    'bad_joins_per_minute': 10,     # wrong codes from one connection (codes are not to be guessed)
    'chat_bytes': 120,
    'chat_per_second': 1,
    'chat_burst': 5,
    'chat_kept': 32,
    'start_hello_seconds': 30,      # every member's UDP socket must have been seen this recently
    # datagrams
    'hello_per_second': 10,         # from one address
    'seen_seconds': 60,             # an address seen by hello is forgotten after this
    'relay_per_second': 150,        # datagrams from one member, sustained ...
    'relay_burst': 300,
    'relay_bytes_per_second': 262144,
    'datagram_bytes': 2048 + 16,
    # what is kept on disk
    'player_days': 400,             # a player not seen for so long is deleted with everything about it
    'request_days': 30,             # a friend request nobody answered
    'recent_days': 90,
}

E_ARGUMENT, E_STATE, E_LIMIT, E_NOT_FOUND, E_FULL, E_REFUSED, E_SERVICE = -2, -3, -4, -5, -6, -7, -8


def now():
    return time.monotonic()


def enc(value):
    """A value of a line: bytes outside a small safe set become %XX."""
    if isinstance(value, bool):
        value = int(value)
    data = str(value).encode('utf-8')
    return ''.join(chr(b) if b in SAFE else '%%%02X' % b for b in data)


def dec(text):
    out = bytearray()
    i = 0
    raw = text.encode('utf-8', 'replace')
    while i < len(raw):
        if raw[i] == 0x25 and i + 3 <= len(raw):
            try:
                out.append(int(raw[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(raw[i])
        i += 1
    return out.decode('utf-8', 'replace')


def line(verb, **fields):
    return verb + ''.join(' %s=%s' % (k, enc(v)) for k, v in fields.items() if v is not None)


def parse(text):
    words = text.split(' ')
    fields = {}
    for word in words[1:]:
        if not word:
            continue
        key, sep, value = word.partition('=')
        if not sep or not key or len(fields) >= 24:
            return None, None
        fields[key] = dec(value)
    return words[0], fields


def clean(text, most):
    """A label or a chat line: control characters out, cut to `most` bytes of UTF-8."""
    text = ''.join(' ' if (ord(ch) < 0x20 or ord(ch) == 0x7f) else ch for ch in text).strip()
    data = text.encode('utf-8')[:most]
    return data.decode('utf-8', 'ignore').strip()


def name_ok(name):
    data = name.encode('utf-8')
    return 3 <= len(data) <= LIMITS['name_bytes'] and name == clean(name, LIMITS['name_bytes'])


def make_code(length):
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def code_normal(text, length):
    text = text.upper().replace('-', '').replace(' ', '')
    return text if len(text) == length and all(ch in ALPHABET for ch in text) else ''


def shown(code):
    return code[:4] + '-' + code[4:] if len(code) == 8 else code


def is_hex(text, length):
    return len(text) == length and all(ch in '0123456789abcdef' for ch in text)


def player_id(verifier):
    return hashlib.sha256(b'rta-net2 id v1' + verifier).hexdigest()[:32]


class Bucket:
    """So many per second, so many at once."""

    def __init__(self, rate, burst):
        self.rate, self.burst, self.have, self.at = float(rate), float(burst), float(burst), now()

    def take(self, amount=1.0):
        t = now()
        self.have = min(self.burst, self.have + (t - self.at) * self.rate)
        self.at = t
        if self.have < amount:
            return False
        self.have -= amount
        return True


class Window:
    """So many in a stretch of time (per hour, per minute), for a key."""

    def __init__(self):
        self.times = {}

    def take(self, key, most, seconds):
        t = now()
        times = [x for x in self.times.get(key, ()) if t - x < seconds]
        ok = len(times) < most
        if ok:
            times.append(t)
        if times:
            self.times[key] = times
        else:
            self.times.pop(key, None)
        return ok

    def sweep(self, seconds=3600):
        t = now()
        for key in [k for k, v in self.times.items() if not v or t - v[-1] > seconds]:
            del self.times[key]


class Store:
    """What is kept: players, friend links, requests, blocks, recent players.  Nothing else."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL' if path != ':memory:' else 'PRAGMA journal_mode=MEMORY')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY, verifier BLOB NOT NULL, name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE, created INTEGER NOT NULL, seen INTEGER NOT NULL,
                cname TEXT NOT NULL DEFAULT '', ccls TEXT NOT NULL DEFAULT '', clevel INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS friends (a TEXT NOT NULL, b TEXT NOT NULL, since INTEGER NOT NULL, PRIMARY KEY (a, b));
            CREATE TABLE IF NOT EXISTS requests (src TEXT NOT NULL, dst TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY (src, dst));
            CREATE TABLE IF NOT EXISTS blocks (a TEXT NOT NULL, b TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY (a, b));
            CREATE TABLE IF NOT EXISTS recent (a TEXT NOT NULL, b TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY (a, b));
        ''')

    def q(self, sql, *args):
        return self.db.execute(sql, args).fetchall()

    def player(self, pid):
        rows = self.q('SELECT id, verifier, name, code, seen, cname, ccls, clevel FROM players WHERE id = ?', pid)
        if not rows:
            return None
        r = rows[0]
        return {'id': r[0], 'verifier': bytes(r[1]), 'name': r[2], 'code': r[3], 'seen': r[4], 'cname': r[5], 'ccls': r[6], 'clevel': r[7]}

    def by_code(self, code):
        rows = self.q('SELECT id FROM players WHERE code = ?', code)
        return rows[0][0] if rows else None

    def create(self, verifier, name):
        pid = player_id(verifier)
        if self.player(pid):
            return None
        while True:
            code = make_code(8)
            if not self.by_code(code):
                break
        t = int(time.time())
        self.q('INSERT INTO players (id, verifier, name, code, created, seen) VALUES (?, ?, ?, ?, ?, ?)', pid, verifier, name, code, t, t)
        return pid

    def are_friends(self, a, b):
        return bool(self.q('SELECT 1 FROM friends WHERE a = ? AND b = ?', a, b))

    def friends(self, a):
        return [r[0] for r in self.q('SELECT b FROM friends WHERE a = ?', a)]

    def blocked(self, a, b):
        """a has blocked b"""
        return bool(self.q('SELECT 1 FROM blocks WHERE a = ? AND b = ?', a, b))

    def delete_player(self, pid):
        for sql in ('DELETE FROM friends WHERE a = ? OR b = ?', 'DELETE FROM requests WHERE src = ? OR dst = ?',
                    'DELETE FROM blocks WHERE a = ? OR b = ?', 'DELETE FROM recent WHERE a = ? OR b = ?'):
            self.q(sql, pid, pid)
        self.q('DELETE FROM players WHERE id = ?', pid)

    def purge(self):
        t = int(time.time())
        gone = [r[0] for r in self.q('SELECT id FROM players WHERE seen < ?', t - LIMITS['player_days'] * 86400)]
        for pid in gone:
            self.delete_player(pid)
        self.q('DELETE FROM requests WHERE at < ?', t - LIMITS['request_days'] * 86400)
        self.q('DELETE FROM recent WHERE at < ?', t - LIMITS['recent_days'] * 86400)
        return len(gone)


class Conn:
    def __init__(self, sock, address):
        self.sock, self.address = sock, address
        self.inbuf, self.outbuf = b'', bytearray()
        self.nonce = secrets.token_bytes(16)
        self.pid = None
        self.opened = self.heard = now()
        self.lines = Bucket(LIMITS['lines_per_second'], LIMITS['lines_burst'])
        self.chat = Bucket(LIMITS['chat_per_second'], LIMITS['chat_burst'])
        self.relay = Bucket(LIMITS['relay_per_second'], LIMITS['relay_burst'])
        self.relay_bytes = Bucket(LIMITS['relay_bytes_per_second'], LIMITS['relay_bytes_per_second'])
        self.udp_key = secrets.token_bytes(8)
        self.seen = None            # (ip, port) the UDP socket was seen at
        self.seen_at = 0.0
        self.local = []             # what the client says its own addresses are: [(ip, port)]
        self.copy = (0, 0, 0, 0)    # fix set, words, arithmetic it can do, arithmetic it does
        self.room = None
        self.level = ''             # "in a game": the level's name
        self.since = int(time.time())
        self.bad_joins = 0
        self.closing = False
        self.wants_write = False


class Member:
    def __init__(self, conn):
        self.conn = conn
        self.ready = False
        self.phase = 0              # 0 in the room, 1 the game was started for it, 2 its game runs


class Room:
    def __init__(self, code, options):
        self.code, self.options = code, options
        self.members = []           # by slot; the host is the first
        self.started = False
        self.session = 0
        self.touched = now()
        self.chat = []              # (number, name, text)
        self.chat_number = 0
        self.address = None         # the address it was made from, for the per-address limit
        self.invited = set()        # player ids that were invited: they may walk in


class Service:
    def __init__(self, store, quiet=False):
        self.store, self.quiet = store, quiet
        self.sel = selectors.DefaultSelector()
        self.listeners, self.udp = [], []
        self.conns = {}             # socket -> Conn
        self.online = {}            # player id -> Conn
        self.rooms = {}             # code -> Room
        self.keys = {}              # udp key -> Conn
        self.invites = {}           # (from id, to id) -> (room code, when)
        self.per_address = {}
        self.windows = {name: Window() for name in ('register', 'bad_login', 'request', 'invite', 'invite_same', 'bad_join', 'hello', 'room')}
        self.hello = {}
        self.counts = {'connections': 0, 'refused': 0, 'lines': 0, 'limited': 0, 'registered': 0, 'logins': 0, 'rooms': 0, 'starts': 0,
                       'hello': 0, 'relayed': 0, 'relay_dropped': 0, 'relay_bytes': 0, 'stray': 0, 'deleted': 0}
        self.last_sweep = now()

    def log(self, text):
        if not self.quiet:
            print(time.strftime('%H:%M:%S ') + text, flush=True)

    # ---- sockets -------------------------------------------------------------------------
    def listen(self, address, port):
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind((address, port))
        tcp.listen(64)
        tcp.setblocking(False)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((address, tcp.getsockname()[1]))
        udp.setblocking(False)
        self.sel.register(tcp, selectors.EVENT_READ, ('listen', None))
        self.sel.register(udp, selectors.EVENT_READ, ('udp', None))
        self.listeners.append(tcp)
        self.udp.append(udp)
        return tcp.getsockname()[1]

    def close_all(self):
        for conn in list(self.conns.values()):
            self.drop(conn, tell=False)
        for sock in self.listeners + self.udp:
            try:
                self.sel.unregister(sock)
            except (KeyError, ValueError):
                pass
            sock.close()
        self.listeners, self.udp = [], []

    def accept(self, listener):
        try:
            sock, address = listener.accept()
        except OSError:
            return
        ip = address[0]
        if len(self.conns) >= LIMITS['connections'] or self.per_address.get(ip, 0) >= LIMITS['connections_per_address']:
            self.counts['refused'] += 1
            try:
                sock.sendall((line('bye', code=E_LIMIT, text='Too many connections.') + '\n').encode())
            except OSError:
                pass
            sock.close()
            return
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        conn = Conn(sock, ip)
        self.conns[sock] = conn
        self.keys[conn.udp_key] = conn
        self.per_address[ip] = self.per_address.get(ip, 0) + 1
        self.counts['connections'] += 1
        self.sel.register(sock, selectors.EVENT_READ, ('conn', conn))
        self.send(conn, line('hi', v=VERSION, nonce=conn.nonce.hex()))

    def send(self, conn, text):
        if conn.closing:
            return
        conn.outbuf += text.encode('utf-8') + b'\n'
        if len(conn.outbuf) > LIMITS['output_bytes']:
            self.drop(conn)
            return
        self.flush(conn)

    def flush(self, conn):
        try:
            if conn.outbuf:
                sent = conn.sock.send(conn.outbuf)
                del conn.outbuf[:sent]
        except BlockingIOError:
            pass
        except OSError:
            self.drop(conn)
            return
        want = bool(conn.outbuf)
        if want != conn.wants_write and conn.sock in self.conns:
            conn.wants_write = want
            self.sel.modify(conn.sock, selectors.EVENT_READ | (selectors.EVENT_WRITE if want else 0), ('conn', conn))

    def drop(self, conn, tell=True, why=None):
        if conn.sock not in self.conns:
            return
        if why and not conn.closing:
            try:
                conn.sock.send((line('bye', code=why[0], text=why[1]) + '\n').encode())
            except OSError:
                pass
        conn.closing = True
        del self.conns[conn.sock]
        self.keys.pop(conn.udp_key, None)
        self.per_address[conn.address] -= 1
        if self.per_address[conn.address] <= 0:
            del self.per_address[conn.address]
        try:
            self.sel.unregister(conn.sock)
        except (KeyError, ValueError):
            pass
        try:
            conn.sock.close()
        except OSError:
            pass
        if conn.pid and self.online.get(conn.pid) is conn:
            if conn.room:
                self.leave_room(conn, said=False)
            del self.online[conn.pid]
            self.store.q('UPDATE players SET seen = ? WHERE id = ?', int(time.time()), conn.pid)
            for key in [k for k in self.invites if conn.pid in k]:
                self.end_invite(key)
            if tell:
                self.presence_changed(conn.pid)

    def read(self, conn):
        try:
            data = conn.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError:
            data = b''
        if not data:
            self.drop(conn)
            return
        conn.inbuf += data
        while conn.sock in self.conns:
            cut = conn.inbuf.find(b'\n')
            if cut < 0:
                if len(conn.inbuf) > LIMITS['line_bytes']:
                    self.drop(conn, why=(E_LIMIT, 'A line was too long.'))
                return
            raw, conn.inbuf = conn.inbuf[:cut], conn.inbuf[cut + 1:]
            if len(raw) > LIMITS['line_bytes']:
                self.drop(conn, why=(E_LIMIT, 'A line was too long.'))
                return
            if not conn.lines.take():
                self.counts['limited'] += 1
                self.drop(conn, why=(E_LIMIT, 'Too many lines at once.'))
                return
            conn.heard = now()
            self.counts['lines'] += 1
            try:
                text = raw.decode('utf-8').rstrip('\r')
            except UnicodeDecodeError:
                self.drop(conn, why=(E_ARGUMENT, 'That was not text.'))
                return
            verb, fields = parse(text)
            if verb is None:
                self.drop(conn, why=(E_ARGUMENT, 'That line was not understood.'))
                return
            self.handle(conn, verb, fields)

    # ---- the conversation ----------------------------------------------------------------
    def answer(self, conn, fields, err=0, text='', **more):
        if err:
            self.send(conn, line('err', n=fields.get('n', '0'), code=err, text=text))
        else:
            self.send(conn, line('ok', n=fields.get('n', '0'), **more))

    def handle(self, conn, verb, f):
        if conn.pid is None:
            if verb == 'register':
                return self.do_register(conn, f)
            if verb == 'login':
                return self.do_login(conn, f)
            if verb == 'ping':
                return self.answer(conn, f)
            return self.drop(conn, why=(E_STATE, 'Log in first.'))
        handler = getattr(self, 'cmd_' + verb, None) if verb.isalpha() else None
        if handler is None:
            return self.answer(conn, f, E_ARGUMENT, 'Unknown request.')
        handler(conn, f)

    def do_register(self, conn, f):
        verifier, name = f.get('verifier', ''), clean(f.get('name', '') or 'Player', LIMITS['name_bytes'])
        if not is_hex(verifier, 64) or not name_ok(name):
            return self.drop(conn, why=(E_ARGUMENT, 'That registration cannot be right.'))
        verifier = bytes.fromhex(verifier)
        pid = player_id(verifier)
        if self.store.player(pid):
            # a known device registering again proves itself like a login would
            return self.drop(conn, why=(E_STATE, 'This device is registered: log in.'))
        if not self.windows['register'].take(conn.address, LIMITS['registrations_per_hour'], 3600):
            self.counts['limited'] += 1
            return self.drop(conn, why=(E_LIMIT, 'Too many new players from this address. Try again later.'))
        self.store.create(verifier, name)
        self.counts['registered'] += 1
        self.welcome(conn, pid, new=1)

    def do_login(self, conn, f):
        pid, proof = f.get('id', ''), f.get('proof', '')
        player = self.store.player(pid) if is_hex(pid, 32) else None
        good = False
        if player and is_hex(proof, 64):
            want = hmac.new(player['verifier'], conn.nonce + b'login', hashlib.sha256).digest()
            good = hmac.compare_digest(want, bytes.fromhex(proof))
        if not good:
            if not self.windows['bad_login'].take(conn.address, LIMITS['bad_logins_per_minute'], 60):
                self.counts['limited'] += 1
            # the same answer for "no such player" and "wrong proof"; an unknown id may register
            return self.drop(conn, why=(E_NOT_FOUND if not player else E_REFUSED, 'unknown' if not player else 'That is not this player.'))
        self.counts['logins'] += 1
        self.welcome(conn, pid, new=0)

    def welcome(self, conn, pid, new):
        old = self.online.get(pid)
        if old is not None and old is not conn:
            self.drop(old, tell=False, why=(E_STATE, 'This player has logged in from somewhere else.'))
        conn.pid = pid
        conn.nonce = secrets.token_bytes(16)        # a proof is good once
        self.online[pid] = conn
        conn.since = int(time.time())
        self.store.q('UPDATE players SET seen = ? WHERE id = ?', conn.since, pid)
        p = self.store.player(pid)
        self.send(conn, line('welcome', id=pid, name=p['name'], code=shown(p['code']), udp=conn.udp_key.hex(), new=new,
                             cname=p['cname'], ccls=p['ccls'], clevel=p['clevel']))
        for other in self.store.friends(pid):
            self.send(conn, self.friend_line(pid, other))
        for src, dst, at in self.store.q('SELECT src, dst, at FROM requests WHERE src = ? OR dst = ?', pid, pid):
            self.send(conn, self.request_line(pid, src, dst, at))
        for other, in self.store.q('SELECT b FROM blocks WHERE a = ?', pid):
            q = self.store.player(other)
            self.send(conn, line('blocked', id=other, name=q['name'] if q else ''))
        for other, at in self.store.q('SELECT b, at FROM recent WHERE a = ? ORDER BY at', pid):
            self.send(conn, self.recent_line(pid, other, at))
        self.send(conn, 'synced')
        self.presence_changed(pid)

    # ---- presence ------------------------------------------------------------------------
    def presence(self, viewer, pid):
        """What `viewer` may know of `pid` now: (state, room code, joinable, players, level, since)."""
        conn = self.online.get(pid)
        if conn is None or self.store.blocked(pid, viewer):
            return 0, '', 0, 0, '', 0
        room = conn.room
        if room is None:
            return 1, '', 0, 0, '', conn.since
        member = self.member(room, conn)
        if room.started and member is not None and member.phase:
            return 3, '', 0, len(room.members), conn.level, conn.since
        joinable = int(room.options['open'] == 1 and not room.started and len(room.members) < 4 and
                       not self.store.blocked(room.members[0].conn.pid, viewer))
        return 2, room.code if joinable else '', joinable, len(room.members), '', conn.since

    def friend_line(self, viewer, pid):
        p = self.store.player(pid)
        state, code, joinable, players, level, since = self.presence(viewer, pid)
        hidden = self.store.blocked(pid, viewer)
        return line('friend', id=pid, name=p['name'], code=shown(p['code']), p=state, room=code, join=joinable, players=players, level=level,
                    since=since, seen=0 if hidden else p['seen'], cname='' if hidden else p['cname'], ccls='' if hidden else p['ccls'],
                    clevel=0 if hidden else p['clevel'], inv=int((pid, viewer) in self.invites))

    def request_line(self, viewer, src, dst, at):
        other = dst if src == viewer else src
        p = self.store.player(other)
        return line('request', id=other, name=p['name'] if p else '', code=shown(p['code']) if p else '', **{'in': int(dst == viewer)}, when=at)

    def recent_line(self, viewer, pid, at):
        p = self.store.player(pid)
        if not p:
            return line('unrecent', id=pid)
        asked = bool(self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', viewer, pid))
        return line('recent', id=pid, name=p['name'], code=shown(p['code']), when=at, friend=int(self.store.are_friends(viewer, pid)),
                    asked=int(asked), cname=p['cname'], ccls=p['ccls'], clevel=p['clevel'])

    def presence_changed(self, pid):
        """Tell the friends of `pid` who are online."""
        for other in self.store.friends(pid):
            conn = self.online.get(other)
            if conn is not None:
                self.send(conn, self.friend_line(other, pid))

    def room_presence(self, room):
        for member in room.members:
            self.presence_changed(member.conn.pid)

    # ---- me ------------------------------------------------------------------------------
    def cmd_ping(self, conn, f):
        self.answer(conn, f)

    def cmd_name(self, conn, f):
        name = f.get('name', '')
        if not name_ok(name):
            return self.answer(conn, f, E_ARGUMENT, 'A name has 3 to 24 characters of plain text.')
        self.store.q('UPDATE players SET name = ? WHERE id = ?', name, conn.pid)
        self.answer(conn, f, name=name)
        self.presence_changed(conn.pid)
        if conn.room:
            self.room_changed(conn.room)

    def cmd_char(self, conn, f):
        try:
            level = max(0, min(999, int(f.get('level', '0') or 0)))
        except ValueError:
            level = 0
        cname, ccls = clean(f.get('name', ''), LIMITS['label_bytes']), clean(f.get('cls', ''), LIMITS['label_bytes'])
        self.store.q('UPDATE players SET cname = ?, ccls = ?, clevel = ? WHERE id = ?', cname, ccls, level, conn.pid)
        self.answer(conn, f)
        self.presence_changed(conn.pid)
        if conn.room:
            self.room_changed(conn.room)

    def cmd_copy(self, conn, f):
        try:
            conn.copy = (int(f.get('fix', '0'), 16) & 0xffffffff, int(f.get('words', '0')) & 0xffff, int(f.get('can', '0')) & 3, int(f.get('does', '0')) & 1)
        except ValueError:
            return self.answer(conn, f, E_ARGUMENT, 'That is not a description of a copy.')
        self.answer(conn, f)
        if conn.room:
            self.room_changed(conn.room)

    def cmd_local(self, conn, f):
        out = []
        for part in f.get('eps', '').split(',')[:4]:
            host, sep, port = part.partition(':')
            try:
                socket.inet_aton(host)
                port = int(port)
            except (OSError, ValueError):
                continue
            if sep and host.count('.') == 3 and 0 < port < 65536:
                out.append((host, port))
        conn.local = out
        self.answer(conn, f)

    def cmd_game(self, conn, f):
        conn.level = clean(f.get('level', ''), LIMITS['label_bytes'])
        self.answer(conn, f)
        self.presence_changed(conn.pid)

    def cmd_delete(self, conn, f):
        pid = conn.pid
        if conn.room:
            self.leave_room(conn, said=True)
        friends = self.store.friends(pid)
        asked = [r[0] for r in self.store.q('SELECT src FROM requests WHERE dst = ? UNION SELECT dst FROM requests WHERE src = ?', pid, pid)]
        knew = [r[0] for r in self.store.q('SELECT a FROM recent WHERE b = ?', pid)]
        for key in [k for k in self.invites if pid in k]:
            self.end_invite(key)
        self.store.delete_player(pid)
        self.counts['deleted'] += 1
        for other in set(friends):
            c = self.online.get(other)
            if c is not None:
                self.send(c, line('unfriend', id=pid))
        for other in set(asked):
            c = self.online.get(other)
            if c is not None:
                self.send(c, line('unrequest', id=pid))
        for other in set(knew):
            c = self.online.get(other)
            if c is not None:
                self.send(c, line('unrecent', id=pid))
        self.send(conn, line('deleted', n=f.get('n', '0')))
        del self.online[pid]
        conn.pid = None
        self.drop(conn, tell=False)

    # ---- friends -------------------------------------------------------------------------
    def tell(self, pid, text):
        conn = self.online.get(pid)
        if conn is not None:
            self.send(conn, text)

    def make_friends(self, a, b):
        t = int(time.time())
        self.store.q('DELETE FROM requests WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)', a, b, b, a)
        self.store.q('INSERT OR IGNORE INTO friends (a, b, since) VALUES (?, ?, ?)', a, b, t)
        self.store.q('INSERT OR IGNORE INTO friends (a, b, since) VALUES (?, ?, ?)', b, a, t)
        for x, y in ((a, b), (b, a)):
            self.tell(x, line('unrequest', id=y))
            if x in self.online:
                self.tell(x, self.friend_line(x, y))
                at = self.store.q('SELECT at FROM recent WHERE a = ? AND b = ?', x, y)
                if at:
                    self.tell(x, self.recent_line(x, y, at[0][0]))

    def cmd_fadd(self, conn, f):
        me = conn.pid
        if 'code' in f:
            code = code_normal(f['code'], 8)
            if not code:
                return self.answer(conn, f, E_ARGUMENT, 'A friend code is eight letters and digits, like K7QF-2MXD.')
            other = self.store.by_code(code)
        else:
            other = f.get('id', '') if is_hex(f.get('id', ''), 32) and self.store.player(f.get('id', '')) else None
        if other == me:
            return self.answer(conn, f, E_ARGUMENT, 'That is your own friend code.')
        if not self.windows['request'].take(me, LIMITS['requests_per_hour'], 3600):
            self.counts['limited'] += 1
            return self.answer(conn, f, E_LIMIT, 'Too many friend requests. Try again later.')
        # a wrong code and a player who has blocked me read the same
        if other is None or self.store.blocked(other, me):
            return self.answer(conn, f, E_NOT_FOUND, 'Nobody has that friend code.')
        if self.store.are_friends(me, other):
            return self.answer(conn, f, E_STATE, 'You are friends already.')
        if self.store.blocked(me, other):
            return self.answer(conn, f, E_STATE, 'You have blocked that player.')
        if self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', other, me):
            self.make_friends(me, other)                    # they had asked: that is an acceptance
            return self.answer(conn, f, friends=1)
        if self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', me, other):
            return self.answer(conn, f, friends=0)
        if len(self.store.friends(me)) >= LIMITS['friends']:
            return self.answer(conn, f, E_LIMIT, 'Your friends list is full.')
        if self.store.q('SELECT COUNT(*) FROM requests WHERE src = ?', me)[0][0] >= LIMITS['requests_open']:
            return self.answer(conn, f, E_LIMIT, 'Too many of your requests are still waiting.')
        t = int(time.time())
        self.store.q('INSERT INTO requests (src, dst, at) VALUES (?, ?, ?)', me, other, t)
        self.send(conn, self.request_line(me, me, other, t))
        self.tell(other, self.request_line(other, me, other, t))
        if self.store.q('SELECT 1 FROM recent WHERE a = ? AND b = ?', me, other):
            self.send(conn, self.recent_line(me, other, self.store.q('SELECT at FROM recent WHERE a = ? AND b = ?', me, other)[0][0]))
        self.answer(conn, f, friends=0)

    def other_of(self, conn, f):
        other = f.get('id', '')
        return other if is_hex(other, 32) and other != conn.pid else None

    def cmd_faccept(self, conn, f):
        other = self.other_of(conn, f)
        if not other or not self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', other, conn.pid):
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such request.')
        if len(self.store.friends(conn.pid)) >= LIMITS['friends'] or len(self.store.friends(other)) >= LIMITS['friends']:
            return self.answer(conn, f, E_LIMIT, 'A friends list is full.')
        self.make_friends(conn.pid, other)
        self.answer(conn, f)

    def cmd_fdecline(self, conn, f):
        other = self.other_of(conn, f)
        if not other:
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such request.')
        # declining what they asked, or taking back what I asked; the other side is told nothing
        # when it is declined (their request simply stays unanswered on their screen until it expires)
        mine = self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', conn.pid, other)
        theirs = self.store.q('SELECT 1 FROM requests WHERE src = ? AND dst = ?', other, conn.pid)
        if not mine and not theirs:
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such request.')
        self.store.q('DELETE FROM requests WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)', conn.pid, other, other, conn.pid)
        self.send(conn, line('unrequest', id=other))
        if mine:
            self.tell(other, line('unrequest', id=conn.pid))
        self.answer(conn, f)

    def unfriend(self, a, b, tell_b):
        self.store.q('DELETE FROM friends WHERE (a = ? AND b = ?) OR (a = ? AND b = ?)', a, b, b, a)
        self.tell(a, line('unfriend', id=b))
        if tell_b:
            self.tell(b, line('unfriend', id=a))
        for key in ((a, b), (b, a)):
            if key in self.invites:
                self.end_invite(key)

    def cmd_fremove(self, conn, f):
        other = self.other_of(conn, f)
        if not other or not self.store.are_friends(conn.pid, other):
            return self.answer(conn, f, E_NOT_FOUND, 'That is not one of your friends.')
        self.unfriend(conn.pid, other, tell_b=True)
        self.answer(conn, f)

    def cmd_block(self, conn, f):
        other = self.other_of(conn, f)
        if not other or not self.store.player(other):
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such player.')
        if self.store.q('SELECT COUNT(*) FROM blocks WHERE a = ?', conn.pid)[0][0] >= LIMITS['blocks']:
            return self.answer(conn, f, E_LIMIT, 'Your block list is full.')
        was_friend = self.store.are_friends(conn.pid, other)
        self.store.q('INSERT OR IGNORE INTO blocks (a, b, at) VALUES (?, ?, ?)', conn.pid, other, int(time.time()))
        self.store.q('DELETE FROM requests WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)', conn.pid, other, other, conn.pid)
        self.send(conn, line('unrequest', id=other))
        self.tell(other, line('unrequest', id=conn.pid))
        if was_friend:
            self.unfriend(conn.pid, other, tell_b=True)
        self.send(conn, line('blocked', id=other, name=self.store.player(other)['name']))
        self.answer(conn, f)

    def cmd_unblock(self, conn, f):
        other = self.other_of(conn, f)
        if not other:
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such player.')
        self.store.q('DELETE FROM blocks WHERE a = ? AND b = ?', conn.pid, other)
        self.send(conn, line('unblocked', id=other))
        self.answer(conn, f)

    # ---- invitations -----------------------------------------------------------------------
    def end_invite(self, key):
        self.invites.pop(key, None)
        src, dst = key
        self.tell(dst, line('uninvite', id=src))
        if dst in self.online and self.store.are_friends(dst, src):
            self.tell(dst, self.friend_line(dst, src))

    def cmd_invite(self, conn, f):
        other = self.other_of(conn, f)
        room = conn.room
        if room is None or room.started:
            return self.answer(conn, f, E_STATE, 'You are not in a room that is open.')
        if not other or not self.store.are_friends(conn.pid, other):
            return self.answer(conn, f, E_NOT_FOUND, 'Only a friend can be invited.')
        if not self.windows['invite_same'].take((conn.pid, other), 1, LIMITS['invite_repeat_seconds']) or \
                not self.windows['invite'].take(conn.pid, LIMITS['invites_per_hour'], 3600):
            self.counts['limited'] += 1
            return self.answer(conn, f, E_LIMIT, 'Too many invitations. Wait a moment.')
        target = self.online.get(other)
        if target is None or self.store.blocked(other, conn.pid):
            return self.answer(conn, f, E_REFUSED, 'That friend is not online.')
        if target.room is room:
            return self.answer(conn, f, E_STATE, 'That friend is in the room already.')
        room.invited.add(other)
        self.invites[(conn.pid, other)] = (room.code, now())
        p = self.store.player(conn.pid)
        self.send(target, line('invite', id=conn.pid, name=p['name'], room=room.code, players=len(room.members), cname=p['cname'], ccls=p['ccls'],
                               clevel=p['clevel'], when=int(time.time())))
        self.send(target, self.friend_line(other, conn.pid))
        self.answer(conn, f)

    def cmd_idismiss(self, conn, f):
        other = self.other_of(conn, f)
        if not other or (other, conn.pid) not in self.invites:
            return self.answer(conn, f, E_NOT_FOUND, 'That invitation is gone.')
        self.end_invite((other, conn.pid))
        self.answer(conn, f)

    # ---- rooms -----------------------------------------------------------------------------
    @staticmethod
    def member(room, conn):
        for m in room.members:
            if m.conn is conn:
                return m
        return None

    @staticmethod
    def options_of(f, old=None):
        o = dict(old) if old else {'level': '', 'diff': 0, 'mode': 0, 'mission': 0, 'kills': 0, 'open': 0}
        if 'level' in f:
            o['level'] = clean(f['level'], LIMITS['label_bytes'])
        for key, most in (('diff', 9), ('mode', 9), ('mission', 99), ('kills', 99), ('open', 1)):
            if key in f:
                try:
                    o[key] = max(0, min(most, int(f[key])))
                except ValueError:
                    pass
        return o

    def room_lines(self, room, conn):
        o = room.options
        mine = self.member(room, conn)
        out = [line('room', code=room.code, state='started' if room.started else 'open', slot=room.members.index(mine), host=0, count=len(room.members),
                    level=o['level'], diff=o['diff'], mode=o['mode'], mission=o['mission'], kills=o['kills'], open=o['open'])]
        for slot, m in enumerate(room.members):
            p = self.store.player(m.conn.pid)
            out.append(line('member', slot=slot, id=m.conn.pid, name=p['name'], ready=int(m.ready), phase=m.phase, fix='%08x' % m.conn.copy[0],
                            words=m.conn.copy[1], can=m.conn.copy[2], does=m.conn.copy[3], cname=p['cname'], ccls=p['ccls'], clevel=p['clevel'],
                            friend=int(self.store.are_friends(conn.pid, m.conn.pid))))
        out.append('roomend')
        return out

    def room_changed(self, room):
        room.touched = now()
        for m in room.members:
            for text in self.room_lines(room, m.conn):
                self.send(m.conn, text)

    def room_say(self, room, name, text):
        room.chat_number += 1
        room.chat.append((room.chat_number, name, text))
        del room.chat[:-LIMITS['chat_kept']]
        for m in room.members:
            self.send(m.conn, line('chat', n=room.chat_number, **{'from': name}, text=text))

    def enter(self, conn, room):
        conn.room = room
        room.members.append(Member(conn))
        for key in [k for k in self.invites if k[1] == conn.pid]:
            self.end_invite(key)                            # in a room: the invitations are answered
        name = self.store.player(conn.pid)['name']
        for number, who, text in room.chat:
            self.send(conn, line('chat', n=number, **{'from': who}, text=text))
        self.room_changed(room)
        self.room_say(room, '', name + ' joined.')
        self.room_presence(room)

    def cmd_host(self, conn, f):
        if conn.room:
            return self.answer(conn, f, E_STATE, 'Leave the room you are in first.')
        mine = sum(1 for r in self.rooms.values() if r.address == conn.address)
        if len(self.rooms) >= LIMITS['rooms'] or mine >= LIMITS['rooms_per_address']:
            self.counts['limited'] += 1
            return self.answer(conn, f, E_LIMIT, 'Too many rooms. Try again later.')
        while True:
            code = make_code(5)
            if code not in self.rooms:
                break
        room = Room(code, self.options_of(f))
        room.address = conn.address
        self.rooms[code] = room
        self.counts['rooms'] += 1
        self.answer(conn, f, code=code)
        self.enter(conn, room)

    def join(self, conn, f, room, by_friend=None):
        if room is None or self.store.blocked(room.members[0].conn.pid, conn.pid):
            conn.bad_joins += 1
            if not self.windows['bad_join'].take(id(conn), LIMITS['bad_joins_per_minute'], 60):
                self.counts['limited'] += 1
                return self.drop(conn, why=(E_LIMIT, 'Too many wrong room codes.'))
            return self.answer(conn, f, E_NOT_FOUND, 'There is no such room.')
        if room.started:
            return self.answer(conn, f, E_REFUSED, 'That game has already started.')
        if len(room.members) >= 4:
            return self.answer(conn, f, E_FULL, 'That room is full.')
        if by_friend is not None and room.options['open'] != 1 and conn.pid not in room.invited:
            return self.answer(conn, f, E_REFUSED, 'That room is by code or invitation only.')
        self.answer(conn, f, code=room.code)
        self.enter(conn, room)

    def cmd_join(self, conn, f):
        if conn.room:
            return self.answer(conn, f, E_STATE, 'Leave the room you are in first.')
        code = code_normal(f.get('code', ''), 5)
        if not code:
            return self.answer(conn, f, E_ARGUMENT, 'A room code is five letters and digits, like H4KQ7.')
        self.join(conn, f, self.rooms.get(code))

    def cmd_joinf(self, conn, f):
        if conn.room:
            return self.answer(conn, f, E_STATE, 'Leave the room you are in first.')
        other = self.other_of(conn, f)
        friend = self.online.get(other) if other and self.store.are_friends(conn.pid, other) else None
        if friend is None or friend.room is None or self.store.blocked(other, conn.pid):
            return self.answer(conn, f, E_REFUSED, 'That friend is not in a room you can walk into.')
        self.join(conn, f, friend.room, by_friend=other)

    def cmd_chat(self, conn, f):
        room = conn.room
        text = clean(f.get('text', ''), LIMITS['chat_bytes'])
        if room is None:
            return self.answer(conn, f, E_STATE, 'You are not in a room.')
        if not text:
            return self.answer(conn, f, E_ARGUMENT, 'Nothing to say.')
        if not conn.chat.take():
            self.counts['limited'] += 1
            return self.answer(conn, f, E_LIMIT, 'Too many lines. Wait a moment.')
        room.touched = now()
        self.answer(conn, f)
        self.room_say(room, self.store.player(conn.pid)['name'], text)

    def cmd_ready(self, conn, f):
        room = conn.room
        if room is None or room.started:
            return self.answer(conn, f, E_STATE, 'You are not in a room that is open.')
        self.member(room, conn).ready = f.get('v', '1') != '0'
        self.answer(conn, f)
        self.room_changed(room)

    def host_room(self, conn, f):
        room = conn.room
        if room is None or room.started:
            self.answer(conn, f, E_STATE, 'You are not in a room that is open.')
            return None
        if room.members[0].conn is not conn:
            self.answer(conn, f, E_STATE, 'Only the host can do that.')
            return None
        return room

    def cmd_opts(self, conn, f):
        room = self.host_room(conn, f)
        if room is None:
            return
        room.options = self.options_of(f, room.options)
        self.answer(conn, f)
        self.room_changed(room)
        self.room_presence(room)

    def cmd_kick(self, conn, f):
        room = self.host_room(conn, f)
        if room is None:
            return
        try:
            slot = int(f.get('slot', '-1'))
        except ValueError:
            slot = -1
        if slot <= 0 or slot >= len(room.members):
            return self.answer(conn, f, E_NOT_FOUND, 'Nobody is in that place.')
        victim = room.members[slot].conn
        self.answer(conn, f)
        self.send(victim, line('notice', text='The host sent you out of the room.'))
        self.leave_room(victim, said=True, why='was sent out of the room')

    def cmd_start(self, conn, f):
        room = self.host_room(conn, f)
        if room is None:
            return
        if len(room.members) < 2:
            return self.answer(conn, f, E_STATE, 'A game needs at least two players.')
        waiting = [self.store.player(m.conn.pid)['name'] for m in room.members[1:] if not m.ready]
        if waiting:
            return self.answer(conn, f, E_STATE, 'Not ready yet: ' + ', '.join(waiting) + '.')
        t = now()
        unseen = [self.store.player(m.conn.pid)['name'] for m in room.members
                  if m.conn.seen is None or t - m.conn.seen_at > LIMITS['start_hello_seconds']]
        if unseen:
            return self.answer(conn, f, E_STATE, 'No datagram has arrived yet from: ' + ', '.join(unseen) + '. Try again in a moment.')
        room.started = True
        room.session = secrets.randbits(32) | 1
        room.touched = t
        self.counts['starts'] += 1
        self.answer(conn, f)
        ts = int(time.time())
        for a in room.members:
            for b in room.members:
                if a is not b:
                    self.store.q('INSERT OR REPLACE INTO recent (a, b, at) VALUES (?, ?, ?)', a.conn.pid, b.conn.pid, ts)
                    extra = [r[0] for r in self.store.q('SELECT b FROM recent WHERE a = ? ORDER BY at DESC LIMIT -1 OFFSET ?', a.conn.pid, LIMITS['recent'])]
                    for gone in extra:
                        self.store.q('DELETE FROM recent WHERE a = ? AND b = ?', a.conn.pid, gone)
                        self.send(a.conn, line('unrecent', id=gone))
                    self.send(a.conn, self.recent_line(a.conn.pid, b.conn.pid, ts))
        o = room.options
        for slot, m in enumerate(room.members):
            m.phase = 1
            m.ready = False
            c = m.conn
            self.send(c, line('start', session='%08x' % room.session, count=len(room.members), slot=slot, host=0, seed=0, level=o['level'],
                              diff=o['diff'], mode=o['mode'], mission=o['mission'], kills=o['kills']))
            for other_slot, other in enumerate(room.members):
                p = self.store.player(other.conn.pid)
                eps = []
                if other is not m:
                    eps = ['%s:%d' % other.conn.seen] + ['%s:%d' % e for e in other.conn.local if e != other.conn.seen][:3]
                self.send(c, line('peer', slot=other_slot, id=other.conn.pid, name=p['name'], eps=','.join(eps), cname=p['cname'], ccls=p['ccls'],
                                  clevel=p['clevel']))
            self.send(c, 'startend')
        self.room_changed(room)
        self.room_say(room, '', 'The game is starting.')
        self.room_presence(room)

    def cmd_gstate(self, conn, f):
        room = conn.room
        if room is None or not room.started:
            return self.answer(conn, f, E_STATE, 'No game was started here.')
        m = self.member(room, conn)
        running = f.get('v', '0') == '1'
        m.phase = 2 if running else 0
        conn.level = clean(f.get('level', ''), LIMITS['label_bytes']) if running else ''
        conn.since = int(time.time())
        self.answer(conn, f)
        self.reopen_if_over(room)
        self.room_changed(room)
        self.room_presence(room)

    def reopen_if_over(self, room):
        if room.started and all(m.phase == 0 for m in room.members):
            room.started = False
            room.session = 0
            for m in room.members:
                m.ready = False
            self.room_say(room, '', 'The game is over. The room is open again.')

    def cmd_leave(self, conn, f):
        if conn.room:
            self.leave_room(conn, said=True)
        self.answer(conn, f)

    def leave_room(self, conn, said, why='left'):
        room = conn.room
        conn.room = None
        conn.level = ''
        name = self.store.player(conn.pid)['name'] if self.store.player(conn.pid) else '?'
        room.members = [m for m in room.members if m.conn is not conn]
        for key in [k for k in self.invites if k[0] == conn.pid]:
            self.end_invite(key)
        if said and conn.sock in self.conns:
            self.send(conn, line('room', code='', state='none', slot=0, host=0, count=0))
            self.send(conn, 'roomend')
        if not room.members:
            del self.rooms[room.code]
        else:
            self.reopen_if_over(room)
            self.room_changed(room)                         # the first member left is the host now
            self.room_say(room, '', '%s %s.' % (name, why))
            self.room_presence(room)
        if conn.pid in self.online:
            self.presence_changed(conn.pid)

    # ---- datagrams ---------------------------------------------------------------------------
    def datagram(self, sock):
        try:
            data, address = sock.recvfrom(4096)
        except (BlockingIOError, OSError):
            return False
        if len(data) < 16 or len(data) > LIMITS['datagram_bytes'] or data[:2] != b'N2':
            self.counts['stray'] += 1
            return True
        kind, slot = data[2], data[3]
        session = struct.unpack_from('<I', data, 4)[0]
        conn = self.keys.get(bytes(data[8:16]))
        if conn is None or conn.pid is None:
            self.counts['stray'] += 1                       # nothing is answered to somebody we do not know
            return True
        if kind == 0x20:
            t = now()
            if not self.windows['hello'].take(address[0], LIMITS['hello_per_second'] * 10, 10):
                self.counts['limited'] += 1
                return True
            conn.seen, conn.seen_at = address, t
            self.counts['hello'] += 1
            try:
                sock.sendto(b'N2\x21\x00\x00\x00\x00\x00' + socket.inet_aton(address[0]) + struct.pack('<H', address[1]), address)
            except OSError:
                pass
        elif kind == 0x10:
            room = conn.room
            if room is None or not room.started or session != room.session or slot >= len(room.members):
                self.counts['relay_dropped'] += 1
                return True
            me = self.member(room, conn)
            target = room.members[slot].conn
            # only from the address this member was seen at, only to an address the other one said hello from
            if target is conn or conn.seen != address or target.seen is None or now() - target.seen_at > LIMITS['seen_seconds']:
                self.counts['relay_dropped'] += 1
                return True
            if not conn.relay.take() or not conn.relay_bytes.take(len(data)):
                self.counts['relay_dropped'] += 1
                self.counts['limited'] += 1
                return True
            out = b'N2\x11' + bytes([room.members.index(me)]) + data[4:8] + data[16:]
            try:
                sock.sendto(out, target.seen)
                self.counts['relayed'] += 1
                self.counts['relay_bytes'] += len(out)
            except OSError:
                self.counts['relay_dropped'] += 1
        else:
            self.counts['stray'] += 1
        return True

    # ---- the clock ---------------------------------------------------------------------------
    def sweep(self):
        t = now()
        for conn in list(self.conns.values()):
            if conn.pid is None and t - conn.opened > LIMITS['login_seconds']:
                self.drop(conn, why=(E_STATE, 'Too slow.'))
            elif t - conn.heard > LIMITS['idle_seconds']:
                self.drop(conn, why=(E_STATE, 'Nothing heard for too long.'))
            elif conn.seen is not None and t - conn.seen_at > LIMITS['seen_seconds']:
                conn.seen = None
        for room in list(self.rooms.values()):
            limit = LIMITS['room_game_seconds'] if room.started else LIMITS['room_idle_seconds']
            if t - room.touched > limit:
                for m in list(room.members):
                    self.send(m.conn, line('notice', text='The room was closed: nothing happened in it for a long time.'))
                    self.leave_room(m.conn, said=True, why='left')
        for key, (code, at) in list(self.invites.items()):
            if t - at > LIMITS['invite_seconds'] or code not in self.rooms or self.rooms[code].started:
                self.end_invite(key)
        for window in self.windows.values():
            window.sweep()

    def status(self):
        c = self.counts
        return ('%d connections (%d players online), %d rooms (%d started); since start: %d connections, %d refused, %d lines, %d registered, '
                '%d logins, %d rooms, %d starts, %d hello, %d relayed (%d bytes), %d relay dropped, %d limited, %d strays, %d deleted'
                % (len(self.conns), len(self.online), len(self.rooms), sum(1 for r in self.rooms.values() if r.started), c['connections'],
                   c['refused'], c['lines'], c['registered'], c['logins'], c['rooms'], c['starts'], c['hello'], c['relayed'], c['relay_bytes'],
                   c['relay_dropped'], c['limited'], c['stray'], c['deleted']))

    def step(self, timeout=0.25):
        for key, mask in self.sel.select(timeout):
            kind, conn = key.data
            if kind == 'listen':
                self.accept(key.fileobj)
            elif kind == 'udp':
                for _ in range(256):
                    if not self.datagram(key.fileobj):
                        break
            else:
                if mask & selectors.EVENT_WRITE and conn.sock in self.conns:
                    self.flush(conn)
                if mask & selectors.EVENT_READ and conn.sock in self.conns:
                    self.read(conn)
        if now() - self.last_sweep > 1.0:
            self.last_sweep = now()
            self.sweep()


def main():
    parser = argparse.ArgumentParser(description='The rendezvous service of the native build (docs/issues/native-rendezvous.md).')
    parser.add_argument('--data', required=True, help='directory of rendezvous.db, or :memory:')
    parser.add_argument('--port', type=int, default=41900)
    parser.add_argument('--bind', action='append', help='an address to listen on (default 127.0.0.1); may be repeated')
    parser.add_argument('--public', action='store_true', help='allow --bind 0.0.0.0')
    parser.add_argument('--limit', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--status-every', type=float, default=0)
    args = parser.parse_args()
    for item in args.limit:
        name, _, value = item.partition('=')
        if name not in LIMITS:
            parser.error('no limit is called %s (see LIMITS in the file)' % name)
        LIMITS[name] = type(LIMITS[name])(value)
    binds = args.bind or ['127.0.0.1']
    if not args.public and any(b in ('0.0.0.0', '', '*') for b in binds):
        parser.error('--bind 0.0.0.0 listens on every address of this machine: say --public if that is meant')
    if args.data == ':memory:':
        store = Store(':memory:')
    else:
        os.makedirs(args.data, exist_ok=True)
        store = Store(os.path.join(args.data, 'rendezvous.db'))
        try:
            os.chmod(os.path.join(args.data, 'rendezvous.db'), 0o600)
        except OSError:
            pass
    service = Service(store, args.quiet)
    purged = store.purge()
    for address in binds:
        port = service.listen(address, args.port)
        service.log('listening on %s, TCP and UDP port %d' % (address, port))
    if purged:
        service.log('%d players not seen for %d days were deleted' % (purged, LIMITS['player_days']))
    last_status = last_purge = now()
    try:
        while True:
            service.step()
            if args.status_every and now() - last_status >= args.status_every:
                last_status = now()
                service.log(service.status())
            if now() - last_purge > 86400:
                last_purge = now()
                store.purge()
    except KeyboardInterrupt:
        pass
    finally:
        service.log('ending: ' + service.status())
        service.close_all()
    return 0


if __name__ == '__main__':
    sys.exit(main())
