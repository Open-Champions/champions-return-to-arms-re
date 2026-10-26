#!/usr/bin/env python3
"""check.py - the self-test of the rendezvous service (rendezvous.py).

    python3 tools/rendezvous/check.py [--work DIR] [--keep] [-v]

Starts services of its own on this computer (127.0.0.1, ports chosen by the system, their
one file under --work, default a new directory under the system's temporary directory) and
goes through everything the service promises, as clients would: identity (register, prove,
a wrong proof, a proof used twice, one player twice), names, friends (ask by code, accept,
decline, remove, block), presence and character labels, invitations, rooms (host, join by
code, by friend, by invitation; chat, ready, options, kick, start, the session description,
game over, a second start, the host leaving), the datagrams (hello, the address seen, the
relay and everything it refuses), every limit hit on purpose, what is on disk, what
survives a restart, and deletion; then the same conversation inside TLS (a test
certificate authority and certificates made for this run with the openssl program, in the
work directory, trusted by nothing but this test).  Nothing is sent to any other machine.

Prints one line per check and "N of N checks passed"; the exit code is 0 when all passed.
Standard library only.
"""
import argparse
import hashlib
import hmac
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rendezvous as R  # noqa: E402  (enc, dec, parse, line: the wire format is the service's own)

VERBOSE = False


class Checks:
    def __init__(self):
        self.passed = self.failed = 0

    def __call__(self, name, ok, detail=''):
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        if VERBOSE or not ok:
            print('%s  %s%s' % ('ok  ' if ok else 'FAIL', name, (' - ' + str(detail)) if detail and not ok else ''), flush=True)
        return ok


def test_certificates(work):
    """A certificate authority of this test alone and three server certificates it signs,
    made with the openssl program: 'localhost' (names localhost and 127.0.0.1), 'wrong'
    (names only wrong-name.invalid) and 'stranger' (signed by another authority).  Returns
    the paths {'ca', 'localhost', 'localhost.key', ...}; nothing is installed anywhere."""
    folder = os.path.join(work, 'pki')
    os.makedirs(folder, exist_ok=True)
    tool = shutil.which('openssl')
    if not tool:
        raise RuntimeError('the openssl program is needed to make the test certificates')
    config = os.path.join(folder, 'test.cnf')
    with open(config, 'w') as f:
        f.write('[req]\ndistinguished_name = dn\nprompt = no\n[dn]\nCN = rta-net2 test\n'
                '[ca]\nbasicConstraints = critical, CA:TRUE\nkeyUsage = critical, keyCertSign, cRLSign\nsubjectKeyIdentifier = hash\n'
                '[leaf]\nbasicConstraints = critical, CA:FALSE\nkeyUsage = critical, digitalSignature\nextendedKeyUsage = serverAuth\n'
                'subjectKeyIdentifier = hash\nauthorityKeyIdentifier = keyid\nsubjectAltName = @names\n'
                '[names]\nDNS.1 = localhost\nIP.1 = 127.0.0.1\n'
                '[wrongleaf]\nbasicConstraints = critical, CA:FALSE\nkeyUsage = critical, digitalSignature\nextendedKeyUsage = serverAuth\n'
                'subjectKeyIdentifier = hash\nauthorityKeyIdentifier = keyid\nsubjectAltName = DNS:wrong-name.invalid\n')

    def run(*arguments):
        result = subprocess.run([tool] + list(arguments), capture_output=True, text=True, cwd=folder)
        if result.returncode != 0:
            raise RuntimeError('openssl %s: %s' % (arguments[0], result.stderr[-500:]))

    def key(name):
        run('ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', name + '.key')

    def authority(name, cn):
        key(name)
        run('req', '-x509', '-new', '-key', name + '.key', '-sha256', '-days', '30', '-subj', '/CN=' + cn, '-config', config,
            '-extensions', 'ca', '-out', name + '.pem')

    def leaf(name, ca, section):
        key(name)
        run('req', '-new', '-key', name + '.key', '-subj', '/CN=' + name, '-config', config, '-out', name + '.csr')
        run('x509', '-req', '-in', name + '.csr', '-CA', ca + '.pem', '-CAkey', ca + '.key', '-set_serial', '0x' + secrets.token_hex(8),
            '-days', '30', '-sha256', '-extfile', config, '-extensions', section, '-out', name + '.crt')
        with open(os.path.join(folder, name + '.pem'), 'w') as out:      # the chain a server gives: its own, then the authority's
            out.write(open(os.path.join(folder, name + '.crt')).read() + open(os.path.join(folder, ca + '.pem')).read())

    authority('ca', 'rta-net2 test authority')
    authority('otherca', 'some other authority')
    leaf('localhost', 'ca', 'leaf')
    leaf('wrong', 'ca', 'wrongleaf')
    leaf('stranger', 'otherca', 'leaf')
    paths = {}
    for name in ('ca', 'otherca', 'localhost', 'wrong', 'stranger'):
        paths[name] = os.path.join(folder, name + '.pem')
        paths[name + '.key'] = os.path.join(folder, name + '.key')
    return paths


def client_context(ca, **more):
    context = ssl.create_default_context(cafile=ca)
    for key, value in more.items():
        setattr(context, key, value)
    return context


class Service:
    """One rendezvous.py process on 127.0.0.1."""

    def __init__(self, data, *limits, tls=None, more=(), port=0, files=None):
        self.out = tempfile.TemporaryFile(mode='w+')
        command = [sys.executable, '-u', os.path.join(HERE, 'rendezvous.py'), '--data', data, '--port', str(port), '--bind', '127.0.0.1'] + list(more)
        if tls:
            command += ['--tls-cert', tls[0], '--tls-key', tls[1]]
        for item in limits:
            command += ['--limit', item]
        def few_files():
            import resource
            resource.setrlimit(resource.RLIMIT_NOFILE, (files, files))
        self.process = subprocess.Popen(command, stdout=self.out, stderr=subprocess.STDOUT, preexec_fn=few_files if files else None)
        self.port = 0
        for _ in range(200):
            self.out.seek(0)
            found = re.search(r'TCP and UDP port (\d+)', self.out.read())
            if found:
                self.port = int(found.group(1))
                break
            if self.process.poll() is not None:
                break
            time.sleep(0.05)
        if not self.port:
            self.out.seek(0)
            raise RuntimeError('the service did not start: ' + self.out.read())

    def stop(self):
        if self.process.poll() is None:
            self.process.send_signal(2)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.out.seek(0)
        text = self.out.read()
        self.out.close()
        return text


class WsSock:
    """A socket's sendall/recv/settimeout/close over a WebSocket (a client's frames are masked)."""

    def __init__(self, sock, real_ip=None, path='/net2'):
        self.sock, self.buf = sock, b''
        key = secrets.token_bytes(16).hex()[:22] + '=='
        head = 'GET %s HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n' % (path, key)
        if real_ip:
            head += 'X-Real-IP: %s\r\n' % real_ip
        sock.sendall((head + '\r\n').encode())
        reply = b''
        while b'\r\n\r\n' not in reply:
            data = sock.recv(4096)
            if not data:
                break
            reply += data
        self.status, _, self.buf = reply.partition(b'\r\n\r\n')
        self.accept = re.search(rb'Sec-WebSocket-Accept: (\S+)', self.status)
        self.expected = __import__('base64').b64encode(hashlib.sha1(key.encode() + R.WS_GUID).digest())
        self.frames = bytearray(self.buf)
        self.buf = b''

    def frame(self, payload, opcode=2, masked=True):
        n = len(payload)
        head = bytes([0x80 | opcode]) + (bytes([(0x80 if masked else 0) | n]) if n < 126 else bytes([(0x80 if masked else 0) | 126]) + struct.pack('!H', n))
        if not masked:
            return head + payload
        mask = secrets.token_bytes(4)
        return head + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(payload))

    def sendall(self, data):
        self.sock.sendall(self.frame(data))

    def settimeout(self, t):
        self.sock.settimeout(t)

    def recv(self, size):
        while True:
            if len(self.frames) >= 2:
                n, at = self.frames[1] & 0x7f, 2
                if n == 126 and len(self.frames) >= 4:
                    n, at = struct.unpack_from('!H', self.frames, 2)[0], 4
                elif n == 127 and len(self.frames) >= 10:
                    n, at = struct.unpack_from('!Q', self.frames, 2)[0], 10
                if n < 126 or at > 2:
                    if len(self.frames) >= at + n:
                        opcode = self.frames[0] & 0x0f
                        payload = bytes(self.frames[at:at + n])
                        del self.frames[:at + n]
                        if opcode == 8:
                            return b''
                        if opcode in (1, 2) and payload:
                            return payload
                        continue
            data = self.sock.recv(65536)
            if not data:
                return b''
            self.frames += data

    def close(self):
        self.sock.close()


class Player:
    """A client: one TCP connection, one UDP socket, the device secret."""

    def __init__(self, port, name=None, secret=None, connect=True, tls=None, host='127.0.0.1', ws=None):
        self.ws = ws                # WebSocket: ('tcp', port) or ('unix', path, X-Real-IP or None)
        self.port, self.name = port, name
        self.tls, self.host = tls, host     # an ssl.SSLContext: the conversation inside TLS, the certificate checked for `host`
        self.secret = secret or secrets.token_bytes(32)
        self.verifier = hmac.new(self.secret, b'rta-net2 verifier v1', hashlib.sha256).digest()
        self.id = R.player_id(self.verifier)
        self.sock = None
        self.buf = b''
        self.lines = []             # (verb, fields) not yet looked at
        self.n = 0
        self.welcome = None
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(('127.0.0.1', 0))
        self.udp.settimeout(1.0)
        self.key = b''
        self.closed = None          # the 'bye' fields, when the service said one
        if connect:
            self.connect()

    def connect(self):
        if self.ws and self.ws[0] == 'unix':
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect(self.ws[1])
        else:
            self.sock = socket.create_connection((self.host, self.ws[1] if self.ws else self.port), 5)
        if self.tls:
            self.sock = self.tls.wrap_socket(self.sock, server_hostname='localhost' if self.host == '127.0.0.1' else self.host)
        self.sock.settimeout(5)
        if self.ws:
            self.sock = WsSock(self.sock, real_ip=self.ws[2] if self.ws[0] == 'unix' else None)
            if b' 101 ' not in self.sock.status:
                self.closed = {'status': self.sock.status.decode('latin-1')}
                return None
        self.buf, self.lines, self.closed = b'', [], None
        hi = self.expect('hi', 'bye')
        if hi[0] == 'bye':
            self.closed = hi[1]
            return None
        self.nonce = bytes.fromhex(hi[1]['nonce'])
        return hi

    def raw(self, text):
        try:
            self.sock.sendall(text.encode('utf-8') + b'\n')
            return True
        except OSError:
            return False

    def pump(self, timeout):
        self.sock.settimeout(timeout)
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return True
        except OSError:
            return False
        if not data:
            return False
        self.buf += data
        while b'\n' in self.buf:
            raw, self.buf = self.buf.split(b'\n', 1)
            verb, fields = R.parse(raw.decode('utf-8'))
            if verb == 'bye':
                self.closed = fields
            self.lines.append((verb, fields))
        return True

    def expect(self, *verbs, timeout=5.0, where=None):
        """The next line with one of these verbs (lines before it stay for later looks)."""
        end = time.time() + timeout
        seen = 0
        while True:
            for i in range(seen, len(self.lines)):
                verb, fields = self.lines[i]
                if verb in verbs and (where is None or where(fields)):
                    del self.lines[i]
                    return verb, fields
            seen = len(self.lines)
            left = end - time.time()
            if left <= 0 or not self.pump(min(left, 0.25)):
                # one more look at what came with the close
                for i in range(len(self.lines)):
                    if self.lines[i][0] in verbs and (where is None or where(self.lines[i][1])):
                        return self.lines.pop(i)
                return None, {}

    def drain(self, quiet=0.15):
        """Everything that has arrived, once nothing more comes for `quiet` seconds."""
        while True:
            before = len(self.lines) + len(self.buf)
            if not self.pump(quiet) or len(self.lines) + len(self.buf) == before:
                break
        out, self.lines = self.lines, []
        return out

    def take_snapshot(self):
        """The oldest whole room snapshot among the lines: (room fields, [member fields]) or None."""
        for start, (verb, room) in enumerate(self.lines):
            if verb != 'room':
                continue
            members = []
            for end in range(start + 1, len(self.lines)):
                verb, fields = self.lines[end]
                if verb == 'member':
                    members.append(fields)
                elif verb == 'roomend':
                    # the lines of the snapshot go, and with them stray pieces of older ones
                    kept = [l for i, l in enumerate(self.lines) if not (start <= i <= end and l[0] in ('room', 'member', 'roomend'))]
                    self.lines = [l for i, l in enumerate(kept) if not (i < start and l[0] in ('member', 'roomend'))]
                    return room, members
            return None
        return None

    def ask(self, verb, **fields):
        self.n += 1
        n = str(self.n)
        if not self.raw(R.line(verb, n=n, **fields)):
            return 'gone', {}
        kind, answer = self.expect('ok', 'err', 'deleted', 'bye', where=lambda f: f.get('n', n) == n)
        return kind, answer

    def register(self, name=None):
        self.raw(R.line('register', v=1, verifier=self.verifier.hex(), name=name or self.name or 'Player'))
        return self.take_welcome()

    def login(self, proof=None, pid=None):
        proof = proof or hmac.new(self.verifier, self.nonce + b'login', hashlib.sha256).digest()
        self.raw(R.line('login', id=pid or self.id, proof=proof.hex()))
        return self.take_welcome()

    def take_welcome(self):
        verb, fields = self.expect('welcome', 'bye')
        if verb != 'welcome':
            return None
        self.welcome = fields
        self.key = bytes.fromhex(fields['udp'])
        self.code = fields['code']
        self.expect('synced')
        return fields

    def hello(self, sock=None, to='127.0.0.1'):
        (sock or self.udp).sendto(b'N2\x20\x00\x00\x00\x00\x00' + self.key, (to, self.port))
        try:
            data, _ = (sock or self.udp).recvfrom(4096)
        except socket.timeout:
            return None
        if data[:3] != b'N2\x21' or len(data) != 14:
            return None
        return socket.inet_ntoa(data[8:12]), struct.unpack_from('<H', data, 12)[0]

    def tunnel(self, data):
        """A datagram in the conversation (the fallback when UDP does not get through)."""
        return self.raw('dg d=' + data.hex())

    def tunnel_hello(self):
        self.tunnel(b'N2\x20\x00\x00\x00\x00\x00' + self.key)
        verb, f = self.expect('dg')
        data = bytes.fromhex(f.get('d', '')) if verb == 'dg' else b''
        if data[:3] != b'N2\x21' or len(data) != 14:
            return None
        return socket.inet_ntoa(data[8:12]), struct.unpack_from('<H', data, 12)[0]

    def tunnel_heard(self, timeout=1.0):
        verb, f = self.expect('dg', timeout=timeout)
        return bytes.fromhex(f.get('d', '')) if verb == 'dg' else None

    def relay(self, session, to_slot, payload, key=None, sock=None):
        (sock or self.udp).sendto(b'N2\x10' + bytes([to_slot]) + struct.pack('<I', session) + (key or self.key) + payload, ('127.0.0.1', self.port))

    def heard(self, timeout=0.5):
        self.udp.settimeout(timeout)
        try:
            data, address = self.udp.recvfrom(4096)
        except socket.timeout:
            return None
        return data

    def room(self):
        """The newest whole room snapshot among the lines received: (fields, members) or None."""
        self.drain()
        return None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
        self.udp.close()


def snapshot(player, timeout=3.0, until=None):
    """Waits for a room snapshot (room ... roomend) and returns (room fields, [member fields])."""
    end = time.time() + timeout
    last = None
    while True:
        got = player.take_snapshot()
        if got is not None:
            last = got
            if until is None or until(*got):
                return got
            continue
        left = end - time.time()
        if left <= 0 or not player.pump(min(left, 0.2)):
            got = player.take_snapshot()
            if got is not None and (until is None or until(*got)):
                return got
            return last if until is None else None


def new_player(port, name):
    p = Player(port, name)
    p.register()
    return p


def befriend(a, b):
    a.ask('fadd', code=b.code)
    b.expect('request')
    b.ask('faccept', id=a.id)
    a.expect('friend', where=lambda f: f['id'] == b.id)
    b.expect('friend', where=lambda f: f['id'] == a.id)


def identity_checks(check, port):
    a = Player(port, 'Alice')
    w = a.register()
    check('register: welcome with an id, a friend code and a datagram key', bool(w) and w['id'] == a.id and re.fullmatch(r'[A-Z2-9]{4}-[A-Z2-9]{4}', w['code']) and len(w['udp']) == 16 and w['new'] == '1', w)
    check('register: the name is the one asked for', w and w['name'] == 'Alice')
    check('the friend code has no letters that are misheard (I, O, 0, 1)', w and not set(w['code']) & set('IO01'))
    kind, _ = a.ask('ping')
    check('ping is answered', kind == 'ok')
    a2 = Player(port, secret=a.secret)
    w2 = a2.login()
    check('login with the same device secret: the same player', bool(w2) and w2['id'] == a.id and w2['code'] == w['code'] and w2['new'] == '0', w2)
    check('one player twice: the first connection is told and closed', a.expect('bye')[0] == 'bye')
    a3 = Player(port, secret=a.secret)
    check('a wrong proof is refused', a3.login(proof=secrets.token_bytes(32)) is None and a3.closed and a3.closed['code'] == str(R.E_REFUSED), a3.closed)
    a4 = Player(port, secret=a.secret)
    old_proof = hmac.new(a.verifier, a.nonce + b'login', hashlib.sha256).digest()
    check('a proof made for another connection is refused (a nonce is used once)', a4.login(proof=old_proof) is None)
    b = Player(port)
    check('an unknown id cannot log in', b.login() is None and b.closed['code'] == str(R.E_NOT_FOUND), b.closed)
    c = Player(port, secret=a.secret)
    check('a registered device cannot register again', c.register('Mallory') is None)
    d = Player(port)
    d.raw(R.line('host', n=1))
    check('nothing is done before the login', d.expect('bye')[0] == 'bye')
    e = Player(port)
    e.raw(R.line('register', v=1, verifier='zz', name='Eve'))
    check('a registration that is not a verifier is refused', e.expect('bye')[0] == 'bye')
    e2 = Player(port)
    e2.raw(R.line('register', v=1, verifier=e2.verifier.hex(), name='x'))
    check('a registration with a name of one letter is refused', e2.expect('bye')[0] == 'bye')
    # names
    kind, ans = a2.ask('name', name='Alice the Second')
    check('a name can be changed', kind == 'ok' and ans.get('name') == 'Alice the Second')
    check('a name of two letters is refused', a2.ask('name', name='ab')[0] == 'err')
    check('a name of 25 letters is refused', a2.ask('name', name='a' * 25)[0] == 'err')
    check('a name with a line break in it is refused', a2.ask('name', name='ab\ncd')[0] == 'err')
    kind, ans = a2.ask('name', name='Zoë ★')
    check('a name may be any text (UTF-8)', kind == 'ok' and ans.get('name') == 'Zoë ★', ans)
    check('an unknown request is answered with an error, not a close', a2.ask('frobnicate')[0] == 'err' and a2.ask('ping')[0] == 'ok')
    check('a name with an invisible right-to-left override in it is refused (it could pass for another name)',
          a2.ask('name', name='Alice\u202eecilA')[0] == 'err')
    kind, ans = a2.ask('name', name='Bob\u200b\u200bby')
    check('zero-width characters are not part of a name', kind == 'err', ans)
    for p in (a, a2, a3, a4, b, c, d, e, e2):
        p.close()


def friend_checks(check, port):
    a, b, c = new_player(port, 'Anna'), new_player(port, 'Bert'), new_player(port, 'Cleo')
    kind, ans = a.ask('fadd', code=b.code.lower().replace('-', ''))
    check('ask by friend code (typed in lower case, without the dash)', kind == 'ok' and ans.get('friends') == '0', ans)
    verb, f = a.expect('request')
    check('the asker sees the request as waiting', verb == 'request' and f['id'] == b.id and f['in'] == '0' and f['name'] == 'Bert', f)
    verb, f = b.expect('request')
    check('the other side gets the request with the asker\'s name and code', verb == 'request' and f['id'] == a.id and f['in'] == '1' and f['code'] == a.code, f)
    check('nobody is a friend before the other side accepts', not [l for l in a.drain() + b.drain() if l[0] == 'friend'])
    check('asking twice changes nothing', a.ask('fadd', code=b.code)[0] == 'ok' and a.expect('request', timeout=0.3)[0] is None)
    check('a wrong code: nobody', a.ask('fadd', code='ZZZZ-ZZZZ')[1].get('code') == str(R.E_NOT_FOUND))
    check('not a code at all', a.ask('fadd', code='hello')[1].get('code') == str(R.E_ARGUMENT))
    check('my own code', a.ask('fadd', code=a.code)[1].get('code') == str(R.E_ARGUMENT))
    check('accepting a request that does not exist', c.ask('faccept', id=a.id)[0] == 'err')
    check('accept', b.ask('faccept', id=a.id)[0] == 'ok')
    fa = a.expect('friend', where=lambda f: f['id'] == b.id)[1]
    fb = b.expect('friend', where=lambda f: f['id'] == a.id)[1]
    check('both sides now have a friend, shown online', fa.get('p') == '1' and fb.get('p') == '1' and fa.get('name') == 'Bert', (fa, fb))
    check('the request is gone on both sides', a.expect('unrequest')[0] == 'unrequest' and b.expect('unrequest')[0] == 'unrequest')
    check('asking a friend again: already friends', a.ask('fadd', code=b.code)[1].get('code') == str(R.E_STATE))
    # asking each other at once is an acceptance
    a.ask('fadd', code=c.code)
    kind, ans = c.ask('fadd', code=a.code)
    check('two players who ask each other are friends at once', kind == 'ok' and ans.get('friends') == '1' and a.expect('friend', where=lambda f: f['id'] == c.id)[0] == 'friend')
    a.drain(), b.drain(), c.drain()
    # decline
    b.ask('fadd', code=c.code)
    c.expect('request')
    check('decline', c.ask('fdecline', id=b.id)[0] == 'ok' and c.expect('unrequest')[0] == 'unrequest')
    check('the asker is not told of a decline', b.expect('unrequest', timeout=0.4)[0] is None)
    check('the asker can take a request back', b.ask('fadd', code=c.code)[0] == 'ok' and c.expect('request')[0] == 'request' and
          b.ask('fdecline', id=c.id)[0] == 'ok' and c.expect('unrequest')[0] == 'unrequest')
    a.drain(), b.drain(), c.drain()
    # presence
    kind, _ = b.ask('char', name='Bertram the Bold', cls='Barbarian', level=34)
    f = a.expect('friend', where=lambda f: f['id'] == b.id)[1]
    check('a friend\'s character (name, class, level) is passed on', kind == 'ok' and f.get('cname') == 'Bertram the Bold' and f.get('ccls') == 'Barbarian' and f.get('clevel') == '34', f)
    b.ask('char', name='x' * 80, cls='y\tz', level=100000)
    f = a.expect('friend', where=lambda f: f['id'] == b.id)[1]
    check('labels are cut and cleaned (24 bytes, no control characters, level at most 999)', len(f.get('cname', '')) == 24 and f.get('ccls') == 'y z' and f.get('clevel') == '999', f)
    b.close()
    f = a.expect('friend', where=lambda f: f['id'] == b.id)[1]
    check('a friend who goes away is shown offline with a last-seen time', f.get('p') == '0' and abs(int(f.get('seen', 0)) - time.time()) < 10, f)
    b2 = Player(port, secret=b.secret)
    b2.login()
    f = a.expect('friend', where=lambda f: f['id'] == b.id)[1]
    check('and online again when it is back', f.get('p') == '1')
    b2.lines = []
    b3 = Player(port, secret=b.secret)
    b3.login()
    b = b3
    check('presence is not told to somebody who is not a friend', c.expect('friend', where=lambda f: f['id'] == b.id, timeout=0.4)[0] is None)
    # remove
    check('remove a friend', a.ask('fremove', id=b.id)[0] == 'ok' and a.expect('unfriend')[1].get('id') == b.id and b.expect('unfriend')[1].get('id') == a.id)
    check('removing somebody who is not a friend', a.ask('fremove', id=b.id)[0] == 'err')
    # block
    befriend(a, b)
    a.drain(), b.drain()
    check('block', a.ask('block', id=b.id)[0] == 'ok')
    check('a blocked friend is no friend any more, on both sides', a.expect('unfriend')[1].get('id') == b.id and b.expect('unfriend')[1].get('id') == a.id)
    check('the blocker has it on its list', a.expect('blocked')[1].get('id') == b.id)
    check('the blocked player cannot ask again, and is told only "nobody"', b.ask('fadd', code=a.code)[1].get('code') == str(R.E_NOT_FOUND))
    check('nor does the blocker ask by mistake', a.ask('fadd', code=b.code)[1].get('code') == str(R.E_STATE))
    check('unblock', a.ask('unblock', id=b.id)[0] == 'ok' and a.expect('unblocked')[1].get('id') == b.id)
    check('after that they can be friends again', b.ask('fadd', code=a.code)[0] == 'ok' and a.expect('request')[0] == 'request')
    a.ask('faccept', id=b.id)
    a.drain(), b.drain()
    # a block between people who stay friends cannot be: but a pending request is dropped by it
    d = new_player(port, 'Dora')
    d.ask('fadd', code=a.code)
    a.expect('request')
    a.ask('block', id=d.id)
    check('blocking drops a request that was waiting, on both sides', a.expect('unrequest')[1].get('id') == d.id and d.expect('unrequest')[1].get('id') == a.id)
    for p in (a, b, c, d, b2):
        p.close()


def eight_checks(check, port):
    """A room of up to eight (option size, docs/issues/native-8-players.md A.8): only while every copy can play one."""
    names = ['Hosty', 'Anna', 'Bobo', 'Cyra', 'Dina', 'Eddy', 'Flora', 'Gusto', 'Halle']
    ps = [new_player(port, n) for n in names]
    for p in ps:
        p.ask('copy', fix='27f61e1d', words=0x1000 | 91, can=3, does=0)
    plain = new_player(port, 'Oldie')
    plain.ask('copy', fix='27f61e1d', words=91, can=3, does=0)
    kind, ans = ps[0].ask('host', level='', diff=1, open=0, size=8)
    code = ans.get('code', '')
    room, members = snapshot(ps[0]) or (None, [])
    check('a room of up to eight says so (size=8, holds 8)', kind == 'ok' and room and room.get('size') == '8' and room.get('cap') == '8', room)
    joins = [p.ask('join', code=code)[0] for p in ps[1:4]]
    check('players 2 to 4 join', joins == ['ok'] * 3, joins)
    snapshot(ps[0], until=lambda r, m: len(m) == 4)
    got = plain.ask('join', code=code)
    check('a fifth player whose copy cannot play eight is refused: the room is full', got[1].get('code') == str(R.E_FULL), got)
    for p in ps[4:8]:
        got = p.ask('join', code=code)
        check('player %d of eight joins' % (ps.index(p) + 1), got[0] == 'ok', got)
    room, members = snapshot(ps[0], until=lambda r, m: len(m) == 8) or (None, [])
    check('eight players, in the order they came', room is not None and [m['name'] for m in members] == names[:8], members)
    check('a ninth: the room is full', ps[8].ask('join', code=code)[1].get('code') == str(R.E_FULL))
    for p in ps[:8]:
        p.ask('leave')
    # a room that did not ask for more stays at four, whatever the copies can do
    qs = ps[:5]
    for p in qs:
        p.drain()
    kind, ans = qs[0].ask('host', level='', diff=1, open=0)
    code = ans.get('code', '')
    room, members = snapshot(qs[0], until=lambda r, m: r.get('code') == code) or (None, [])
    check('a room that did not ask for more holds four (cap=4)', room and room.get('size') == '0' and room.get('cap') == '4', room)
    for p in qs[1:4]:
        p.ask('join', code=code)
    snapshot(qs[0], until=lambda r, m: len(m) == 4)
    got = qs[4].ask('join', code=code)
    check('... and a fifth is refused', got[1].get('code') == str(R.E_FULL), got)
    for p in qs[:4]:
        p.ask('leave')
    for p in ps + [plain]:
        p.close()


def room_checks(check, port):
    a, b, c, d, e = [new_player(port, n) for n in ('Hosta', 'Jon', 'Kim', 'Lee', 'Max')]
    for p in (a, b, c, d, e):
        p.ask('copy', fix='27f61e1d', words=91, can=3, does=0)
    kind, ans = a.ask('host', level='', diff=2, open=0)
    code = ans.get('code', '')
    check('host: a room code of five letters and digits', kind == 'ok' and re.fullmatch(r'[A-Z2-9]{5}', code), ans)
    room, members = snapshot(a)
    check('the host is player 1 of its room', room['code'] == code and room['state'] == 'open' and room['slot'] == '0' and room['diff'] == '2' and
          len(members) == 1 and members[0]['id'] == a.id and members[0]['fix'] == '27f61e1d' and members[0]['words'] == '91', (room, members))
    check('hosting twice is refused', a.ask('host')[1].get('code') == str(R.E_STATE))
    check('join by a wrong code', b.ask('join', code='ZZZZZ')[1].get('code') == str(R.E_NOT_FOUND))
    check('join by something that is not a code', b.ask('join', code='no')[1].get('code') == str(R.E_ARGUMENT))
    check('join by code (lower case)', b.ask('join', code=code.lower())[0] == 'ok')
    room, members = snapshot(b, until=lambda r, m: len(m) == 2)
    check('the joiner is player 2 and sees both', room['slot'] == '1' and [m['name'] for m in members] == ['Hosta', 'Jon'], (room, members))
    room, members = snapshot(a, until=lambda r, m: len(m) == 2)
    check('the host sees the joiner', len(members) == 2 and members[1]['id'] == b.id)
    verb, f = a.expect('chat', where=lambda f: f['text'].startswith('Jon'))
    check('the room says who joined', verb == 'chat' and f['from'] == '' and f['text'] == 'Jon joined.', f)
    # chat
    check('a chat line', b.ask('chat', text='hello there  ')[0] == 'ok')
    fa = a.expect('chat', where=lambda f: f['from'] == 'Jon')[1]
    fb = b.expect('chat', where=lambda f: f['from'] == 'Jon')[1]
    check('everybody in the room gets it, with the sender\'s name, trimmed', fa.get('text') == 'hello there' and fb.get('text') == 'hello there' and fa.get('n') == fb.get('n'), (fa, fb))
    b.ask('chat', text='x' * 500)
    check('a long line is cut to 120 bytes', len(a.expect('chat', where=lambda f: f['from'] == 'Jon')[1].get('text', '')) == 120)
    check('an empty line is refused', b.ask('chat', text='   ')[0] == 'err')
    check('chat outside a room is refused', c.ask('chat', text='anyone?')[1].get('code') == str(R.E_STATE))
    b.ask('chat', text='tab\there % = & ü')
    check('odd characters arrive as they were sent (control characters become blanks)', a.expect('chat', where=lambda f: f['from'] == 'Jon')[1].get('text') == 'tab here % = & ü')
    # a later joiner gets the lines that were said
    c.ask('join', code=code)
    said = []
    while True:
        verb, f = c.expect('chat', timeout=0.5)
        if verb is None:
            break
        said.append(f['text'])
    check('somebody who joins later gets what was said', 'hello there' in said and 'Kim joined.' in said, said)
    d.ask('join', code=code)
    check('a fifth player: the room is full', e.ask('join', code=code)[1].get('code') == str(R.E_FULL))
    room, members = snapshot(a, until=lambda r, m: len(m) == 4)
    check('four players, in the order they came', [m['name'] for m in members] == ['Hosta', 'Jon', 'Kim', 'Lee'])
    # ready, options, start
    check('only the host changes the options', b.ask('opts', level='drunare')[1].get('code') == str(R.E_STATE))
    a.ask('opts', level='drunare', diff=3, open=1)
    room, members = snapshot(d, until=lambda r, m: r['level'] == 'drunare')
    check('options reach everybody', room and room['diff'] == '3' and room['open'] == '1')
    check('only the host starts', b.ask('start')[1].get('code') == str(R.E_STATE))
    kind, ans = a.ask('start')
    check('no start while somebody is not ready', kind == 'err' and 'Jon' in ans.get('text', ''), ans)
    for p in (b, c, d):
        p.ask('ready', v=1)
    room, members = snapshot(a, until=lambda r, m: all(x['ready'] == '1' for x in m[1:]))
    check('ready marks reach the host', room is not None)
    kind, ans = a.ask('start')
    check('no start before a datagram of every player has been seen', kind == 'err' and 'datagram' in ans.get('text', ''), ans)
    seen = {}
    for p in (a, b, c, d):
        seen[p] = p.hello()
    check('hello: the service answers with the address it saw', all(seen[p] == ('127.0.0.1', p.udp.getsockname()[1]) for p in seen), seen)
    for p in (a, b, c, d):
        p.ask('local', eps='192.168.1.50:%d,203.0.113.7:4000,10.0.0.9:4000,not-an-address:1' % p.udp.getsockname()[1])
    for p in (a, b, c, d):
        p.drain()
    check('start', a.ask('start')[0] == 'ok')
    starts = {}
    for p in (a, b, c, d):
        verb, s = p.expect('start')
        peers = []
        while True:
            verb, f = p.expect('peer', 'startend', timeout=2)
            if verb != 'peer':
                break
            peers.append(f)
        starts[p] = (s, peers)
    sessions = {starts[p][0].get('session') for p in starts}
    check('everybody gets the same session number', len(sessions) == 1 and None not in sessions and int(next(iter(sessions)), 16) != 0, sessions)
    check('everybody gets its own player number, the host 0', [starts[p][0]['slot'] for p in (a, b, c, d)] == ['0', '1', '2', '3'] and all(starts[p][0]['count'] == '4' and starts[p][0]['host'] == '0' for p in starts))
    check('everybody gets the same options and seed', len({(s['level'], s['diff'], s['mode'], s['seed']) for s, _ in starts.values()}) == 1 and starts[a][0]['level'] == 'drunare')
    same = [[(f['slot'], f['id'], f['name']) for f in peers] for _, peers in starts.values()]
    check('everybody gets the same list of players', all(x == same[0] for x in same) and [x[1] for x in same[0]] == [a.id, b.id, c.id, d.id])
    eps_b_from_a = [f for f in starts[a][1] if f['id'] == b.id][0]['eps'].split(',')
    check('for every other player: the address the service saw, then what the player said its own addresses are (private ones only)',
          eps_b_from_a[0] == '127.0.0.1:%d' % b.udp.getsockname()[1] and eps_b_from_a[1:] == ['192.168.1.50:%d' % b.udp.getsockname()[1], '10.0.0.9:4000'], eps_b_from_a)
    check('no address is given for oneself', [f for f in starts[a][1] if f['id'] == a.id][0]['eps'] == '')
    session = int(starts[a][0]['session'], 16)
    check('a started room cannot be joined', e.ask('join', code=code)[1].get('code') == str(R.E_REFUSED))
    check('nor started again', a.ask('start')[1].get('code') == str(R.E_STATE))
    # the relay
    for p in (a, b, c, d):
        p.udp.settimeout(0.3)
        try:
            while True:
                p.udp.recvfrom(4096)
        except socket.timeout:
            pass
    a.relay(session, 2, b'game datagram from the host')
    got = c.heard()
    check('relay: a datagram for player 3 arrives there, marked as from player 1', got == b'N2\x11\x00' + struct.pack('<I', session) + b'game datagram from the host', got)
    check('relay: nobody else gets it', b.heard(0.2) is None and d.heard(0.1) is None)
    d.relay(session, 0, b'x' * 1984)
    got = a.heard()
    check('relay: the game\'s largest datagram (1,984 bytes) passes', got is not None and len(got) == 8 + 1984 and got[3] == 3)
    a.relay(session ^ 5, 1, b'wrong session')
    check('relay: a wrong session number is dropped', b.heard(0.2) is None)
    a.relay(session, 1, b'wrong key', key=secrets.token_bytes(8))
    check('relay: an unknown key is dropped', b.heard(0.2) is None)
    a.relay(session, 0, b'to myself')
    check('relay: nothing to oneself', a.heard(0.2) is None)
    a.relay(session, 7, b'no such player')
    check('relay: no such player', all(p.heard(0.05) is None for p in (b, c, d)))
    other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    other.bind(('127.0.0.1', 0))
    a.relay(session, 1, b'from another socket', sock=other)
    check('relay: only from the address the member was seen at', b.heard(0.2) is None)
    e.hello()
    e.relay(session, 1, b'from somebody who is not in the room')
    check('relay: only between members of the room', b.heard(0.2) is None)
    other.sendto(b'N2\x20\x00\x00\x00\x00\x00' + secrets.token_bytes(8), ('127.0.0.1', port))
    other.settimeout(0.3)
    try:
        other.recvfrom(100)
        answered = True
    except socket.timeout:
        answered = False
    check('a hello with an unknown key gets no answer (nothing goes to an address that did not ask)', not answered)
    other.sendto(b'hello?', ('127.0.0.1', port))
    other.sendto(b'N2' + b'\xff' * 30, ('127.0.0.1', port))
    try:
        other.recvfrom(100)
        answered = True
    except socket.timeout:
        answered = False
    check('rubbish gets no answer', not answered)
    other.close()
    # the game runs, ends; the room opens again
    for p in (a, b, c, d):
        p.ask('gstate', v=1, level='drunare')
    room, members = snapshot(a, until=lambda r, m: all(x['phase'] == '2' for x in m))
    check('every machine reports its game running', room is not None and room['state'] == 'started')
    for p in (b, c, d):
        p.ask('gstate', v=0)
    room, members = snapshot(a, until=lambda r, m: [x['phase'] for x in m] == ['2', '0', '0', '0'])
    check('while one machine still plays the room stays started', room is not None and room['state'] == 'started')
    a.ask('gstate', v=0)
    room, members = snapshot(b, until=lambda r, m: r['state'] == 'open')
    check('when the game is over on every machine the room is open again, nobody ready', room is not None and all(x['ready'] == '0' for x in members))
    a.relay(session, 1, b'after the game')
    check('relay: nothing once the game is over', b.heard(0.2) is None)
    for p in (b, c, d):
        p.ask('ready', v=1)
        p.hello()
    a.hello()
    for p in (a, b, c, d):
        p.drain()
    check('a second start in the same room', a.ask('start')[0] == 'ok')
    s2 = a.expect('start')[1]
    check('with a new session number', s2.get('session') not in sessions and s2.get('count') == '4', s2)
    for p in (a, b, c, d):
        p.ask('gstate', v=0)
    # kick, leave, host migration
    for p in (a, b, c, d):
        p.drain()
    check('only the host sends somebody out', b.ask('kick', slot=2)[1].get('code') == str(R.E_STATE))
    check('the host sends player 4 out', a.ask('kick', slot=3)[0] == 'ok')
    room, members = snapshot(d, until=lambda r, m: r['state'] == 'none')
    check('who is sent out is told and has no room', room is not None and d.expect('notice')[0] == 'notice')
    room, members = snapshot(a, until=lambda r, m: len(m) == 3)
    check('the others see three players', room is not None and [m['name'] for m in members] == ['Hosta', 'Jon', 'Kim'])
    check('the host cannot send itself out', a.ask('kick', slot=0)[0] == 'err')
    a.ask('leave')
    room, members = snapshot(b, until=lambda r, m: len(m) == 2)
    check('the host leaves: the next player is the host and player 1', room is not None and room['slot'] == '0' and members[0]['id'] == b.id and snapshot(c, until=lambda r, m: len(m) == 2)[0]['slot'] == '1')
    check('the new host can change the options', b.ask('opts', diff=1)[0] == 'ok')
    c.close()
    room, members = snapshot(b, until=lambda r, m: len(m) == 1)
    check('a player whose connection goes away leaves the room', room is not None)
    b.ask('leave')
    check('an empty room is gone', e.ask('join', code=code)[1].get('code') == str(R.E_NOT_FOUND))
    for p in (a, b, d, e):
        p.close()


def presence_and_invite_checks(check, port):
    a, b, c = new_player(port, 'Ada'), new_player(port, 'Ben'), new_player(port, 'Cyd')
    befriend(a, b)
    befriend(a, c)
    for p in (a, b, c):
        p.drain()
    code = a.ask('host', open=0)[1]['code']
    f = b.expect('friend', where=lambda f: f['id'] == a.id)[1]
    check('a friend in a room by code only: "in a room", no code, not joinable', f.get('p') == '2' and f.get('room') == '' and f.get('join') == '0' and f.get('players') == '1', f)
    check('walking into a room that is by code only is refused', b.ask('joinf', id=a.id)[1].get('code') == str(R.E_REFUSED))
    a.ask('opts', open=1)
    f = b.expect('friend', where=lambda f: f['id'] == a.id and f['join'] == '1')[1]
    check('a room open to friends: joinable, with its code', f.get('room') == code and f.get('p') == '2', f)
    check('a friend walks in from the list', b.ask('joinf', id=a.id)[0] == 'ok')
    f = c.expect('friend', where=lambda f: f['id'] == a.id and f['players'] == '2')[1]
    check('the others see the room fill', f.get('join') == '1')
    d = new_player(port, 'Dee')
    check('somebody who is not a friend cannot walk in', d.ask('joinf', id=a.id)[1].get('code') == str(R.E_REFUSED))
    # invitations
    a.ask('opts', open=0)
    for p in (a, b, c):
        p.drain()
    check('invite a friend', a.ask('invite', id=c.id)[0] == 'ok')
    verb, f = c.expect('invite')
    check('the friend gets the invitation: who, which room, how many are in it', verb == 'invite' and f['id'] == a.id and f['name'] == 'Ada' and f['room'] == code and f['players'] == '2', f)
    check('the friends list marks who invited', c.expect('friend', where=lambda f: f['id'] == a.id)[1].get('inv') == '1')
    check('inviting the same friend again at once is refused (rate)', a.ask('invite', id=c.id)[1].get('code') == str(R.E_LIMIT))
    check('only a friend can be invited', a.ask('invite', id=d.id)[1].get('code') == str(R.E_NOT_FOUND))
    check('nobody is invited from outside a room', c.ask('invite', id=a.id)[1].get('code') == str(R.E_STATE))
    check('one press: the invited friend joins by the code of the invitation', c.ask('join', code=f['room'])[0] == 'ok')
    check('and the invitation is gone', c.expect('uninvite')[1].get('id') == a.id)
    c.ask('leave')
    time.sleep(0.05)
    for p in (a, b, c):
        p.drain()
    check('an invited friend may also walk in from the list although the room is by code', c.ask('joinf', id=a.id)[0] == 'ok')
    c.ask('leave')
    # dismiss
    e = new_player(port, 'Eli')
    befriend(b, e)
    b.ask('invite', id=e.id)
    e.expect('invite')
    check('dismiss an invitation', e.ask('idismiss', id=b.id)[0] == 'ok' and e.expect('uninvite')[1].get('id') == b.id)
    check('dismissing it twice', e.ask('idismiss', id=b.id)[0] == 'err')
    # in a game
    for p in (a, b):
        p.hello()
    b.ask('ready', v=1)
    for p in (a, b, c):
        p.drain()
    a.ask('start')
    f = c.expect('friend', where=lambda f: f['id'] == a.id and f['p'] == '3')[1]
    check('a friend whose game was started: "in a game"', f.get('room') == '' and f.get('join') == '0', f)
    a.ask('gstate', v=1, level='hub')
    f = c.expect('friend', where=lambda f: f['id'] == a.id and f['level'] == 'hub')[1]
    check('with the level\'s name and since when', f.get('p') == '3' and abs(int(f.get('since', 0)) - time.time()) < 10 and f.get('players') == '2', f)
    check('walking into a started game is refused', c.ask('joinf', id=a.id)[0] == 'err')
    a.ask('gstate', v=0)
    b.ask('gstate', v=0)
    f = c.expect('friend', where=lambda f: f['id'] == a.id and f['p'] == '2')[1]
    check('after the game: in a room again', bool(f))
    # recent players
    r = a.expect('recent', where=lambda f: f['id'] == b.id)[1]
    check('people I was in a game with are on my recent list', r.get('name') == 'Ben' and r.get('friend') == '1', r)
    a.ask('leave'), b.ask('leave')
    x, y = new_player(port, 'Xan'), new_player(port, 'Yul')
    for p in (x, y):
        p.hello()
    code2 = x.ask('host')[1]['code']
    y.ask('join', code=code2)
    y.ask('ready', v=1)
    x.ask('start')
    r = x.expect('recent', where=lambda f: f['id'] == y.id)[1]
    check('a stranger from a game is on the recent list: name and code, not yet a friend', r.get('friend') == '0' and r.get('asked') == '0' and r.get('code') == y.code, r)
    check('a recent player can be asked by one press', x.ask('fadd', id=y.id)[0] == 'ok' and y.expect('request')[1].get('id') == x.id)
    check('and the recent list then says "asked"', x.expect('recent', where=lambda f: f['id'] == y.id)[1].get('asked') == '1')
    y.ask('faccept', id=x.id)
    check('and "friend" once accepted', x.expect('recent', where=lambda f: f['id'] == y.id and f['friend'] == '1')[0] == 'recent')
    # a blocked player gets no presence
    for p in (a, b, c):
        p.drain()
    a.ask('block', id=c.id)
    c.expect('unfriend')
    a.ask('name', name='Ada Again')
    a.ask('char', name='Adara', cls='Wizard', level=5)
    check('a blocked player hears nothing more of the blocker', c.expect('friend', where=lambda f: f['id'] == a.id, timeout=0.5)[0] is None)
    code3 = a.ask('host', open=1)[1]['code']
    check('and cannot join the blocker\'s room even with the code ("no such room")', c.ask('join', code=code3)[1].get('code') == str(R.E_NOT_FOUND))
    for p in (a, b, c, d, e, x, y):
        p.close()


def stored_checks(check, work):
    data = os.path.join(work, 'stored')
    service = Service(data)
    a, b, c = new_player(service.port, 'Sara'), new_player(service.port, 'Theo'), new_player(service.port, 'Uma')
    befriend(a, b)
    a.ask('char', name='Saranyel', cls='Wood Elf Ranger', level=21)
    c.ask('fadd', code=a.code)
    a.ask('block', id=c.id)
    code = a.ask('host')[1]['code']
    b.ask('join', code=code)
    b.ask('chat', text='a line that must not be kept ZQXJ')
    a.hello(), b.hello()
    for p in (a, b, c):
        p.close()
    service.stop()
    path = os.path.join(data, 'rendezvous.db')
    db = sqlite3.connect(path)
    tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
    check('on disk: five tables and nothing else', tables == ['blocks', 'friends', 'players', 'recent', 'requests'], tables)
    columns = [r[1] for r in db.execute('PRAGMA table_info(players)')]
    check('a player on disk: id, verifier, name, friend code, two times, the character label', columns == ['id', 'verifier', 'name', 'code', 'created', 'seen', 'cname', 'ccls', 'clevel'], columns)
    db.close()
    blob = b''
    for name in os.listdir(data):
        blob += open(os.path.join(data, name), 'rb').read()
    check('no address is on disk', b'127.0.0.1' not in blob)
    check('no chat line is on disk', b'ZQXJ' not in blob)
    check('no device secret is on disk (the service never had one)', a.secret not in blob and a.secret.hex().encode() not in blob)
    check('the file is the owner\'s alone (mode 0600)', (os.stat(path).st_mode & 0o777) == 0o600)
    # a restart
    service = Service(data)
    a2 = Player(service.port, secret=a.secret)
    w = a2.login()
    friends = [l for l in a2.lines if l[0] == 'friend']
    blocked = [l for l in a2.lines if l[0] == 'blocked']
    check('after a restart: the same player, name and friend code', bool(w) and w['name'] == 'Sara' and w['code'] == a.code and w['cname'] == 'Saranyel', w)
    a2 = Player(service.port, secret=a.secret)
    a2.sock.settimeout(5)
    a2.raw(R.line('login', id=a2.id, proof=hmac.new(a2.verifier, a2.nonce + b'login', hashlib.sha256).digest().hex()))
    got = []
    while True:
        verb, f = a2.expect('friend', 'blocked', 'synced', 'welcome')
        if verb in (None, 'synced'):
            break
        got.append((verb, f))
    check('the list sent at login: one friend (offline, last seen), one blocked player',
          [v for v, _ in got] == ['welcome', 'friend', 'blocked'] and got[1][1]['id'] == b.id and got[1][1]['p'] == '0' and got[2][1]['id'] == c.id, got)
    check('rooms do not survive a restart', a2.ask('join', code=code)[1].get('code') == str(R.E_NOT_FOUND))
    # deletion
    b2 = Player(service.port, secret=b.secret)
    b2.login()
    b2.drain()
    kind, _ = a2.ask('delete')
    check('delete everything: answered', kind == 'deleted')
    check('the friend is told the friendship is gone', b2.expect('unfriend')[1].get('id') == a.id)
    a3 = Player(service.port, secret=a.secret)
    check('the deleted player cannot log in any more', a3.login() is None and a3.closed['code'] == str(R.E_NOT_FOUND))
    a4 = Player(service.port, secret=a.secret)
    w = a4.register('Sara')
    check('the same device can start again as a new player with a new friend code', bool(w) and w['new'] == '1' and w['code'] != a.code, w)
    for p in (a2, a3, a4, b2):
        p.close()
    service.stop()
    db = sqlite3.connect(path)
    rows = sum(db.execute('SELECT COUNT(*) FROM %s WHERE %s' % (t, w), (a.id,) * w.count('?')).fetchone()[0]
               for t, w in (('friends', 'a = ? OR b = ?'), ('requests', 'src = ? OR dst = ?'), ('blocks', 'a = ? OR b = ?'), ('recent', 'a = ? OR b = ?')))
    check('nothing of the deleted player is left in the friend, request, block and recent tables', rows == 0, rows)
    # retention
    old = int(time.time()) - 401 * 86400
    db.execute('UPDATE players SET seen = ? WHERE id = ?', (old, c.id))
    db.execute('INSERT OR REPLACE INTO requests (src, dst, at) VALUES (?, ?, ?)', (b.id, 'f' * 32, int(time.time()) - 31 * 86400))
    db.commit()
    db.close()
    service = Service(data)
    text = service.stop()
    db = sqlite3.connect(path)
    check('a player not seen for 400 days is deleted when the service starts', db.execute('SELECT COUNT(*) FROM players WHERE id = ?', (c.id,)).fetchone()[0] == 0 and 'were deleted' in text, text)
    check('a friend request nobody answered for 30 days is deleted', db.execute('SELECT COUNT(*) FROM requests WHERE dst = ?', ('f' * 32,)).fetchone()[0] == 0)
    db.close()


def limit_checks(check, work):
    # --- lines ---
    service = Service(':memory:', 'lines_burst=15', 'lines_per_second=5', 'login_seconds=1', 'idle_seconds=2', 'connections_per_address=6',
                      'registrations_per_hour=4', 'bad_logins_per_minute=3')
    port = service.port
    a = new_player(port, 'Limit')
    a.raw('chat n=1 text=' + 'x' * 2000)
    check('a line longer than 1,024 bytes: the connection is closed with a reason', a.expect('bye')[1].get('code') == str(R.E_LIMIT))
    a.close()
    a = Player(port, secret=a.secret)
    a.login()
    a.sock.sendall(b'x' * 3000)
    check('3,000 bytes without a line end: closed', a.expect('bye')[1].get('code') == str(R.E_LIMIT))
    a.close()
    a = Player(port, secret=a.secret)
    a.login()
    a.sock.sendall(b''.join(b'ping n=%d\n' % i for i in range(40)))
    check('forty lines at once (15 allowed): closed', a.expect('bye')[1].get('code') == str(R.E_LIMIT))
    a.close()
    a = Player(port, secret=a.secret)
    a.login()
    a.raw('ping\x00 n==1 =')
    verb, _ = a.expect('bye', 'err', 'ok')
    check('a line that is not in the format: closed or refused, the service goes on', verb in ('bye', 'err'))
    a.close()
    a = Player(port, secret=a.secret)
    a.login()
    a.sock.sendall(b'\xff\xfe\xfd\n')
    check('bytes that are not text: closed', a.expect('bye')[0] == 'bye')
    a.close()
    # --- time ---
    slow = Player(port)
    t0 = time.time()
    check('a connection that does not log in within the time is closed', slow.expect('bye', timeout=4)[0] == 'bye' and time.time() - t0 < 3.5)
    slow.close()
    idle = Player(port, secret=a.secret)
    idle.login()
    t0 = time.time()
    check('a connection that says nothing for too long is closed', idle.expect('bye', timeout=6)[0] == 'bye' and 1.5 < time.time() - t0 < 5)
    idle.close()
    # --- connections per address ---
    many = [Player(port) for _ in range(6)]
    extra = Player(port)
    check('a seventh connection from one address (6 allowed) is refused', extra.closed is not None and extra.closed.get('code') == str(R.E_LIMIT), extra.closed)
    for p in many + [extra]:
        p.close()
    time.sleep(0.3)
    # --- registrations ---
    results = []
    for i in range(6):
        p = Player(port, 'New%d' % i)
        results.append(p.register() is not None)
        p.close()
    check('new players from one address: four an hour (one was made before), then refused', results == [True, True, True, False, False, False], results)
    # --- wrong proofs ---
    for i in range(5):
        p = Player(port, secret=a.secret)
        p.login(proof=secrets.token_bytes(32))
        p.close()
    p = Player(port, secret=a.secret)
    check('a right proof still works after wrong ones (they are counted, the player is not locked out)', p.login() is not None)
    p.close()
    text = service.stop()
    check('the service ended with a summary and no error', 'ending:' in text and 'Traceback' not in text, text[-600:])

    # --- friends, invitations, chat, rooms, joins ---
    service = Service(':memory:', 'requests_per_hour=3', 'friends=2', 'requests_open=2', 'chat_burst=3', 'chat_per_second=1', 'rooms_per_address=2',
                      'bad_joins_per_minute=3', 'registrations_per_hour=100', 'connections_per_address=40', 'invites_per_hour=2', 'invite_repeat_seconds=0',
                      'recent=2', 'blocks=1')
    port = service.port
    a = new_player(port, 'Asker')
    others = [new_player(port, 'Other%d' % i) for i in range(6)]
    results = [a.ask('fadd', code=o.code)[0] for o in others[:4]]
    check('friend requests: three an hour, of which two may wait unanswered; the rest is refused', results == ['ok', 'ok', 'err', 'err'], results)
    kind, ans = a.ask('fadd', code='ZZZZ-ZZZZ')
    check('and so is guessing friend codes', kind == 'err' and ans.get('code') == str(R.E_LIMIT), ans)
    b = new_player(port, 'Popular')
    fans = [new_player(port, 'Fan%d' % i) for i in range(3)]
    for fan in fans:
        fan.ask('fadd', code=b.code)
    results = [b.ask('faccept', id=fan.id)[0] for fan in fans]
    check('a friends list is full at its limit (2 here)', results == ['ok', 'ok', 'err'], results)
    # chat
    code = b.ask('host')[1]['code']
    results = [b.ask('chat', text='line %d' % i)[1].get('code', 'ok') for i in range(6)]
    check('chat: a burst of three, then "wait a moment"', results[:3] == ['ok'] * 3 and str(R.E_LIMIT) in results[3:], results)
    time.sleep(1.2)
    check('and a line again a second later', b.ask('chat', text='later')[0] == 'ok')
    # invitations
    befr = fans[0]
    results = [b.ask('invite', id=befr.id)[1].get('code', 'ok') for _ in range(3)]
    check('invitations: two an hour here, the third refused', results == ['ok', 'ok', str(R.E_LIMIT)], results)
    # rooms per address
    hosts = [others[0], others[1], others[2]]
    results = [h.ask('host')[0] for h in hosts]
    check('rooms from one address: two here (one exists), so the second new one is refused', results == ['ok', 'err', 'err'], results)
    # wrong room codes
    guesser = others[3]
    results = []
    for i in range(5):
        kind, ans = guesser.ask('join', code='ZZZZ%s' % 'ABCDE'[i])
        results.append(kind)
    check('guessing room codes: three wrong ones a minute, then the connection is closed', results[:3] == ['err'] * 3 and 'bye' in results[3:], results)
    # block list
    check('a block list is full at its limit (1 here)', others[4].ask('block', id=a.id)[0] == 'ok' and others[4].ask('block', id=b.id)[1].get('code') == str(R.E_LIMIT))
    for p in [a, b] + others + fans:
        p.close()
    text = service.stop()
    check('the second service ended without an error', 'Traceback' not in text, text[-600:])

    # --- the relay's limits ---
    service = Service(':memory:', 'relay_per_second=20', 'relay_burst=30', 'hello_per_second=2', 'seen_seconds=2', 'start_hello_seconds=30',
                      'room_idle_seconds=2', 'invite_seconds=1')
    port = service.port
    a, b, c = new_player(port, 'Ray'), new_player(port, 'Sol'), new_player(port, 'Tia')
    code = a.ask('host')[1]['code']
    b.ask('join', code=code)
    a.hello(), b.hello()
    b.ask('ready', v=1)
    a.drain()
    a.ask('start')
    session = int(a.expect('start')[1]['session'], 16)
    for i in range(100):
        a.relay(session, 1, b'burst %03d' % i)
    got = 0
    while b.heard(0.3) is not None:
        got += 1
    check('relay: of 100 datagrams at once about 30 pass (the burst), the rest are dropped', 28 <= got <= 40, got)
    a.relay(session, 1, b'x' * 3000)
    check('relay: a datagram larger than any of the game\'s is dropped', b.heard(0.3) is None)
    time.sleep(1.0)
    a.relay(session, 1, b'after a second')
    check('relay: and carried again a second later', b.heard(0.5) is not None)
    answers = 0
    c.udp.settimeout(0.05)
    for _ in range(40):
        c.udp.sendto(b'N2\x20\x00\x00\x00\x00\x00' + c.key, ('127.0.0.1', port))
    time.sleep(0.3)
    try:
        while True:
            c.udp.recvfrom(100)
            answers += 1
    except (socket.timeout, BlockingIOError):
        pass
    check('hello: at most 20 in ten seconds from one address here; 40 sent', 0 < answers <= 20, answers)
    time.sleep(2.6)
    a.relay(session, 1, b'to an address that has gone stale')
    check('relay: nothing to an address whose hello is older than the limit (2 s here)', b.heard(0.3) is None)
    a.ask('gstate', v=0), b.ask('gstate', v=0)
    # an idle room is closed
    a.drain()
    time.sleep(3.2)
    room = snapshot(a, timeout=2, until=lambda r, m: r['state'] == 'none')
    check('a room in which nothing happens is closed after its time (2 s here), and its players are told', room is not None)
    for p in (a, b, c):
        p.close()
    text = service.stop()
    check('the third service ended without an error', 'Traceback' not in text, text[-600:])
    found = re.search(r'(\d+) relayed \((\d+) bytes\), (\d+) relay dropped, (\d+) limited', text)
    check('its summary counts what was relayed, dropped and limited', bool(found) and int(found.group(3)) >= 60 and int(found.group(4)) >= 60, text[-300:])


def own_lan_address():
    """This computer's address toward a LAN, or None (nothing is sent: a UDP socket is only aimed)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('192.0.2.1', 9))
        ip = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    if not ip or ip.startswith('127.') or ip == '0.0.0.0':
        return None
    import ipaddress
    return ip if ipaddress.ip_address(ip).is_private else None   # on a server the route goes out a public address


def exposure_checks(check, work):
    """The limits added for strangers on the Internet (docs/issues/native-rendezvous-tls.md)."""
    service = Service(':memory:', 'connects_per_minute=5', 'registrations_per_hour=100', 'registrations_per_hour_all=3')
    port = service.port
    players = [Player(port) for _ in range(5)]
    sixth = Player(port)
    check('new connections from one address: five a minute here, the sixth is refused with a reason',
          sixth.closed is not None and sixth.closed.get('code') == str(R.E_LIMIT), sixth.closed)
    results = [p.register('Reg%d' % i) is not None for i, p in enumerate(players[:4])]
    check('new players from everywhere together: three an hour here, then refused', results == [True, True, True, False], results)
    for p in players + [sixth]:
        p.close()
    service.stop()

    service = Service(':memory:', 'registrations_per_hour=100', 'connections_per_address=40', 'requests_incoming=2', 'updates_burst=3',
                      'updates_per_second=1', 'bad_joins_per_minute=3', 'requests_per_hour=100')
    port = service.port
    target = new_player(port, 'Wanted')
    askers = [new_player(port, 'Asker%d' % i) for i in range(3)]
    results = [a.ask('fadd', code=target.code)[1].get('code', 'ok') for a in askers]
    check('friend requests waiting for one player: two here, the third asker is told to wait', results == ['ok', 'ok', str(R.E_LIMIT)], results)
    results = [target.ask('char', name='Changer', cls='Wizard', level=i)[1].get('code', 'ok') for i in range(5)]
    check('changes that every friend is told of (name, character, level ...): a burst of three here, then "wait a moment"',
          results[:3] == ['ok'] * 3 and str(R.E_LIMIT) in results[3:], results)
    g1, g2 = askers[0], askers[1]
    results = [g1.ask('join', code='ZZZZA')[0], g1.ask('join', code='ZZZZB')[0], g2.ask('join', code='ZZZZC')[0], g2.ask('join', code='ZZZZD')[0]]
    check('wrong room codes are counted per address, not per connection: the fourth from the second connection closes it',
          results[:3] == ['err'] * 3 and results[3] in ('bye', 'gone'), results)
    for p in [target] + askers:
        p.close()
    text = service.stop()
    check('that service ended without an error', 'Traceback' not in text, text[-600:])

    # a process that may open few files: the connections are capped below that, so accept() never runs out
    service = Service(':memory:', 'connections_per_address=100', 'connects_per_minute=1000', files=96)
    port = service.port
    many = [Player(port) for _ in range(32)]
    extra = Player(port)
    check('a process allowed 96 open files takes 32 connections and refuses the 33rd in words (no busy loop at the limit)',
          all(p.closed is None for p in many) and extra.closed is not None and extra.closed.get('code') == str(R.E_LIMIT), extra.closed)
    for p in many + [extra]:
        p.close()
    text = service.stop()
    check('it said its cap when it started', 'at most 32 connections at once' in text, text[:300])

    lan = own_lan_address()
    if lan is None:
        print('note: no LAN address on this computer: the check of a hello from another address was not made', flush=True)
        return
    free = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    free.bind((lan, 0))
    number = free.getsockname()[1]
    free.close()
    service = Service(':memory:', more=['--bind', lan], port=number)
    port = service.port
    p = Player(port, 'Lanny', host=lan)
    p.register()
    p.udp.close()
    p.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    p.udp.bind(('127.0.0.1', 0))
    p.udp.settimeout(0.5)
    check('a hello with a right key from another IP address than its player\'s TCP connection gets no answer and is not taken',
          p.hello(to='127.0.0.1') is None)
    p.udp.close()
    p.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    p.udp.bind((lan, 0))
    p.udp.settimeout(1.0)
    check('from the same address it is answered', p.hello(to=lan) == (lan, p.udp.getsockname()[1]))
    p.close()
    text = service.stop()
    check('the service counts the hello from another address', re.search(r'[1-9]\d* hellos from another address', text) is not None, text[-300:])


def tls_checks(check, work):
    try:
        pki = test_certificates(work)
    except RuntimeError as e:
        return check('test certificates made with the openssl program', False, e)
    check('test certificates made with the openssl program (an authority of this test alone)', True)
    trusting = client_context(pki['ca'])
    service = Service(':memory:', 'registrations_per_hour=100', 'login_seconds=2', tls=(pki['localhost'], pki['localhost.key']))
    port = service.port
    a = Player(port, 'Tess', tls=trusting)
    check('TLS: the greeting comes inside TLS, the certificate checked for the name localhost', a.nonce is not None and a.sock.version() in ('TLSv1.2', 'TLSv1.3'),
          a.sock.version())
    w = a.register()
    check('TLS: a registration (the verifier) and its welcome', bool(w) and w['name'] == 'Tess', w)
    a2 = Player(port, secret=a.secret, tls=trusting)
    check('TLS: a login with a proof', a2.login() is not None and a2.welcome['id'] == a.id)
    b = Player(port, 'Theo', tls=trusting)
    b.register()
    code = a2.ask('host')[1].get('code', '')
    check('TLS: a room, joined by its code', bool(code) and b.ask('join', code=code)[0] == 'ok')
    b.ask('chat', text='said inside TLS')
    check('TLS: a chat line reaches the room', a2.expect('chat', where=lambda f: f.get('text') == 'said inside TLS')[0] == 'chat')
    a2.hello(), b.hello()
    b.ask('ready', v=1)
    a2.drain()
    a2.ask('start')
    session = int(a2.expect('start')[1].get('session', '0'), 16)
    b.drain()
    a2.relay(session, 1, b'a datagram while the conversation is inside TLS')
    check('TLS: the UDP side is the same (hello, the relay)', b.heard() == b'N2\x11\x00' + struct.pack('<I', session) + b'a datagram while the conversation is inside TLS')
    b.raw('chat n=1 text=' + 'x' * 2000)
    check('TLS: a line that is too long: closed with the reason, inside TLS', b.expect('bye')[1].get('code') == str(R.E_LIMIT))
    # what does not get in
    plain = socket.create_connection(('127.0.0.1', port), 5)
    plain.settimeout(3)
    plain.sendall(b'ping n=1\n')
    try:
        got = plain.recv(4096)
    except (socket.timeout, OSError):
        got = b''
    check('a client in plain text gets nothing readable (no greeting, no answer) and is closed', b'hi ' not in got and b'ok' not in got, got[:80])
    plain.close()
    try:
        Player(port, tls=client_context(pki['otherca']))
        refused = False
    except ssl.SSLError:
        refused = True
    check('a client that trusts another authority refuses the service\'s certificate', refused)
    try:
        Player(port, tls=client_context(pki['ca']), host='127.0.0.1').sock.close()
        named = True
    except ssl.SSLError:
        named = False
    check('(the certificate also names 127.0.0.1, so a client may check it for the address)', named)
    old = client_context(pki['ca'])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        old.maximum_version = ssl.TLSVersion.TLSv1_1
        old.minimum_version = ssl.TLSVersion.TLSv1
    try:
        Player(port, tls=old)
        refused = False
    except (ssl.SSLError, OSError):
        refused = True
    check('a client that offers nothing newer than TLS 1.1 is refused', refused)
    silent = socket.create_connection(('127.0.0.1', port), 5)
    silent.settimeout(5)
    t0 = time.time()
    try:
        gone = silent.recv(100) == b''
    except (socket.timeout, OSError):
        gone = True
    check('a connection that never starts the handshake is closed after the login time (2 s here)', gone and time.time() - t0 < 4.5, time.time() - t0)
    silent.close()
    for p in (a, a2, b):
        p.close()
    # a certificate read again on SIGHUP
    folder = os.path.join(work, 'reload')
    os.makedirs(folder, exist_ok=True)
    cert, keyfile = os.path.join(folder, 'cert.pem'), os.path.join(folder, 'key.pem')
    shutil.copy(pki['localhost'], cert)
    shutil.copy(pki['localhost.key'], keyfile)
    text = service.stop()
    check('the TLS service ended without an error and counted its handshakes', 'Traceback' not in text and re.search(r'[1-9]\d* TLS handshakes \([1-9]\d* failed\)', text) is not None, text[-400:])
    service = Service(':memory:', tls=(cert, keyfile))
    shutil.copy(pki['wrong'], cert)
    shutil.copy(pki['wrong.key'], keyfile)
    service.process.send_signal(signal.SIGHUP)
    time.sleep(0.6)
    try:
        Player(service.port, tls=trusting)
        refused = False
    except ssl.SSLError:
        refused = True
    check('SIGHUP: the certificate is read again (here one for another name, which a client then refuses)', refused)
    shutil.copy(pki['localhost'], cert)
    shutil.copy(pki['localhost.key'], keyfile)
    service.process.send_signal(signal.SIGHUP)
    time.sleep(0.6)
    p = Player(service.port, tls=trusting)
    check('and back: a client gets in again', p.nonce is not None)
    p.close()
    text = service.stop()
    check('the service said so in its log', text.count('certificate read again') == 2, text[-400:])
    # partial TLS writes: a client that reads slowly gets every line, in order
    service = Service(':memory:', 'lines_burst=5000', 'lines_per_second=5000', 'chat_burst=5000', 'chat_per_second=5000', 'output_bytes=16777216',
                      'registrations_per_hour=100', tls=(pki['localhost'], pki['localhost.key']))
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    slow = Player(service.port, 'Slow', tls=trusting, connect=False)
    raw.connect(('127.0.0.1', service.port))
    slow.sock = trusting.wrap_socket(raw, server_hostname='localhost')
    slow.sock.settimeout(5)
    slow.nonce = bytes.fromhex(slow.expect('hi')[1]['nonce'])
    slow.register()
    slow.ask('host')
    slow.drain()
    count = 2500
    slow.sock.sendall(b''.join(b'chat text=%05d%s\n' % (i, b'y' * 100) for i in range(count)))
    time.sleep(1.0)
    texts = []
    end = time.time() + 30
    while len(texts) < count and time.time() < end:
        verb, f = slow.expect('chat', timeout=2)
        if verb is None:
            break
        if f.get('from') == 'Slow':
            texts.append(f['text'][:5])
    check('TLS: 2,500 chat lines (300 kB) to a client that reads slowly arrive whole and in order', texts == ['%05d' % i for i in range(count)],
          (len(texts), texts[:3], texts[-3:]))
    slow.close()
    text = service.stop()
    check('that service ended without an error', 'Traceback' not in text, text[-600:])
    # starting
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--bind', '192.0.2.1', '--port', '0'],
                             capture_output=True, text=True, timeout=20)
    check('an address reachable from the Internet without TLS is refused (unless --plain)', process.returncode != 0 and '--plain' in process.stderr and
          'TLS' in process.stderr, process.stderr[-300:])
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--bind', '0.0.0.0', '--public', '--port', '0'],
                             capture_output=True, text=True, timeout=20)
    check('so is every address (0.0.0.0) with --public but without TLS', process.returncode != 0 and '--plain' in process.stderr, process.stderr[-300:])
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--port', '0', '--tls-cert', pki['localhost'],
                              '--tls-key', pki['wrong.key']], capture_output=True, text=True, timeout=20)
    check('a certificate with a key that is not its own: refused at the start, in words', process.returncode != 0 and 'cannot be used' in process.stderr,
          process.stderr[-300:])
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--port', '0', '--tls-cert', pki['localhost']],
                             capture_output=True, text=True, timeout=20)
    check('a certificate without its key: refused', process.returncode != 0 and 'go together' in process.stderr)


def ws_checks(check, work):
    """The conversation as a WebSocket (behind a web server on 443, or on a port of its own) and
    the datagrams carried in it (the fallback for networks that break TLS to unknown ports or
    block UDP)."""
    unix = os.path.join(tempfile.mkdtemp(prefix='rv-ws-'), 'ws.sock')       # short: a Unix socket's path has a limit
    service = Service(':memory:', 'registrations_per_hour=1000', 'connections_per_address=3', 'connects_per_minute=1000',
                      more=('--ws-unix', unix, '--ws-bind', '127.0.0.1:0'))
    port = service.port
    service.out.seek(0)
    found = re.search(r'WebSocket on 127\.0\.0\.1, TCP port (\d+)', service.out.read())
    ws_port = int(found.group(1)) if found else 0
    check('WebSocket: the service says where it takes it (a Unix socket for the web server, a TCP port)', ws_port > 0 and os.path.exists(unix))
    players = []
    try:
        a = Player(port, 'Wanda', ws=('tcp', ws_port))
        players.append(a)
        check('WebSocket: the upgrade is answered (101, the right Sec-WebSocket-Accept), then the greeting in a frame',
              b' 101 ' in a.sock.status and a.sock.accept is not None and a.sock.accept.group(1) == a.sock.expected and a.nonce is not None, a.sock.status)
        check('WebSocket: register and welcome', bool(a.register()))
        check('WebSocket: a request and its answer', a.ask('ping')[0] == 'ok')
        b = Player(port, 'Wolf', ws=('unix', unix, '198.51.100.7'))
        players.append(b)
        check('WebSocket behind the web server (Unix socket): registered', bool(b.register()))
        nobody = Player(port, 'NoReal', connect=False, ws=('unix', unix, None))
        try:
            nobody.connect()
            gone = nobody.sock.recv(100) == b''
        except OSError:
            gone = True
        nobody.close()
        check('behind the web server without X-Real-IP: closed (the address is not known)', gone)
        same = []
        for i in range(3):
            q = Player(port, 'Same%d' % i, connect=False, ws=('unix', unix, '198.51.100.7'))
            try:
                q.connect()
            except OSError:
                pass
            same.append(q)
        refused = 0
        for q in same:
            try:
                q.sock.settimeout(1)
                refused += q.nonce is None or q.sock.recv(100) == b''
            except (OSError, AttributeError):
                refused += 1
        other = Player(port, 'OtherAddress', ws=('unix', unix, '198.51.100.8'))
        players.append(other)
        check('the limit per address counts X-Real-IP: the 4th from one address is refused, another address gets in (3 at once here)',
              refused >= 1 and other.nonce is not None, refused)
        for q in same:
            q.close()
        bad = socket.create_connection(('127.0.0.1', ws_port), 5)
        bad.settimeout(3)
        bad.sendall(b'GET /net2 HTTP/1.1\r\nHost: x\r\n\r\n')
        check('a request that is not a WebSocket upgrade: 400 and closed', bad.recv(200).startswith(b'HTTP/1.1 400'))
        bad.close()
        c = Player(port, 'Unmasked', ws=('tcp', ws_port))
        c.sock.sock.sendall(c.sock.frame(b'ping n=1\n', masked=False))
        check('an unmasked frame from a client: closed', c.sock.recv(100) == b'')
        c.close()
        d = Player(port, 'Early', ws=('tcp', ws_port))
        d.raw('dg d=4e3220000000000000000000000000000000')
        check('a datagram in the conversation before a login: closed', d.expect('bye')[1].get('code') == str(R.E_STATE))
        d.close()
        # ---- the tunnel: datagrams in the conversation, between a WebSocket player and a UDP one ----
        e = Player(port, 'Udo')
        players.append(e)
        e.register()
        code = b.ask('host')[1].get('code', '')
        e.ask('join', code=code)
        a.ask('join', code=code)
        seen = b.tunnel_hello()
        check('tunnel: a hello in the conversation is answered in it, with the player\'s own address (X-Real-IP) and port 0', seen == ('198.51.100.7', 0), seen)
        check('tunnel: and over a WebSocket on a port of its own', a.tunnel_hello() == ('127.0.0.1', 0))
        check('and a UDP player beside them as ever', e.hello() is not None)
        e.ask('ready', v=1), a.ask('ready', v=1)
        b.drain()
        check('the room starts: a tunnelled player counts as seen', b.ask('start')[0] == 'ok')
        starts = {}
        for p in (b, e, a):
            verb, st = p.expect('start')
            peers = []
            while True:
                verb, f = p.expect('peer', 'startend', timeout=2)
                if verb != 'peer':
                    break
                peers.append(f)
            starts[p] = (st, peers)
        session = int(starts[b][0]['session'], 16)
        eps = {f['name']: f.get('eps', '') for f in starts[e][1]}
        check('a tunnelled player has no address in the start description (nobody punches to it: the relay carries it)',
              eps.get('Wolf') == '' and eps.get('Wanda') == '', eps)
        e.relay(session, 0, b'udp to tunnel')
        got = b.tunnel_heard()
        check('relay: from UDP into the conversation', got == b'N2\x11\x01' + struct.pack('<I', session) + b'udp to tunnel', got)
        b.tunnel(b'N2\x10\x01' + struct.pack('<I', session) + b.key + b'tunnel to udp')
        check('relay: from the conversation to UDP', e.heard() == b'N2\x11\x00' + struct.pack('<I', session) + b'tunnel to udp')
        b.tunnel(b'N2\x10\x02' + struct.pack('<I', session) + b.key + b'tunnel to tunnel')
        got = a.tunnel_heard()
        check('relay: from one conversation to another', got == b'N2\x11\x00' + struct.pack('<I', session) + b'tunnel to tunnel', got)
        b.tunnel(b'N2\x10\x01' + struct.pack('<I', session) + e.key + b'with a key not its own')
        check('tunnel: a datagram with another player\'s key is nobody\'s', e.heard(0.4) is None)
        big = b'N2\x10\x01' + struct.pack('<I', session) + b.key + b'y' * 2100
        b.tunnel(big)
        check('tunnel: a datagram larger than any of the game\'s is dropped', e.heard(0.4) is None)
        b.raw('dg d=' + 'ab' * 2200)
        check('tunnel: a line longer than any datagram: closed', b.expect('bye')[1].get('code') == str(R.E_LIMIT))
    finally:
        for p in players:
            p.close()
        text = service.stop()
    check('the WebSocket service ended without an error, and counts the links and the tunnelled datagrams', 'Traceback' not in text and
          re.search(r'[1-9]\d* WebSocket links, [1-9]\d* datagrams in / [1-9]\d* out by tunnel', text) is not None, text[-800:])
    check('its Unix socket is gone after it', not os.path.exists(unix))
    # inside TLS on a port of its own (as nginx would put it on 443)
    try:
        pki = test_certificates(os.path.join(work, 'ws-tls'))
    except RuntimeError as e:
        return check('test certificates for the WebSocket inside TLS', False, e)
    service = Service(':memory:', more=('--ws-bind', '127.0.0.1:0'), tls=(pki['localhost'], pki['localhost.key']))
    service.out.seek(0)
    found = re.search(r'WebSocket on 127\.0\.0\.1, TCP port (\d+), TLS', service.out.read())
    try:
        t = Player(service.port, 'Wes', tls=client_context(pki['ca']), ws=('tcp', int(found.group(1)) if found else 1))
        check('WebSocket inside TLS (wss): the upgrade, the greeting and a registration', b' 101 ' in t.sock.status and bool(t.register()))
        t.close()
    finally:
        text = service.stop()
    check('and that service ended without an error', 'Traceback' not in text, text[-600:])


def start_checks(check):
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--bind', '0.0.0.0', '--port', '0'],
                             capture_output=True, text=True, timeout=20)
    check('the service refuses to listen on every address unless --public is said', process.returncode != 0 and '--public' in process.stderr, process.stderr[-200:])
    process = subprocess.run([sys.executable, os.path.join(HERE, 'rendezvous.py'), '--data', ':memory:', '--limit', 'nonsense=1'], capture_output=True, text=True, timeout=20)
    check('an unknown limit is an error', process.returncode != 0)
    # the wire format's own round trip
    for text in ['plain', 'two words', 'a=b&c%d', 'Zoë ★', '', '100%', '%zz', 'tab\there']:
        verb, fields = R.parse(R.line('x', v=text))
        if fields.get('v') != text:
            return check('the line format carries any text (%r)' % text, False, fields)
    check('the line format carries any text', True)
    check('a line with a field that has no "=" is not understood', R.parse('x broken')[0] is None)


def main():
    global VERBOSE
    parser = argparse.ArgumentParser()
    parser.add_argument('--work')
    parser.add_argument('--keep', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    VERBOSE = args.verbose
    work = args.work or tempfile.mkdtemp(prefix='rendezvous-check-')
    os.makedirs(work, exist_ok=True)
    check = Checks()
    started = time.time()
    try:
        start_checks(check)
        service = Service(':memory:', 'registrations_per_hour=1000', 'connections_per_address=64', 'requests_per_hour=1000')
        try:
            identity_checks(check, service.port)
            friend_checks(check, service.port)
            room_checks(check, service.port)
            presence_and_invite_checks(check, service.port)
        finally:
            text = service.stop()
        check('the service ran through all of it without an error', 'Traceback' not in text, text[-1500:])
        service = Service(':memory:', 'registrations_per_hour=1000', 'connections_per_address=64', 'requests_per_hour=1000')
        try:
            eight_checks(check, service.port)
        finally:
            text = service.stop()
        check('... and through the rooms of eight', 'Traceback' not in text, text[-3000:])
        stored_checks(check, work)
        limit_checks(check, work)
        exposure_checks(check, work)
        tls_checks(check, work)
        ws_checks(check, work)
    finally:
        if not args.keep and not args.work:
            shutil.rmtree(work, ignore_errors=True)
    print('%d of %d checks passed (%.0f s)' % (check.passed, check.passed + check.failed, time.time() - started))
    return 0 if check.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
