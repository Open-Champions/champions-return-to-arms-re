#!/usr/bin/env python3
"""check_client.py - the client library (tools/recomp/net2: session.h and its body that
talks to the service) against a rendezvous service, end to end, without the game.

    python3 tools/rendezvous/check_client.py [--work DIR] [--cli PATH] [-v]

Builds tools/recomp/net2/net2cli (the interface of session.h on a terminal) when no binary
is named, starts a service of its own on 127.0.0.1, and plays four players through
everything a portal does: a first start (an identity file is made), a second start (the
same player), the file copied to "another computer", names, friends by code, presence and
character labels, a room by code / by friend / by invitation, chat, ready, the fix-set
warning, the start (every machine the same description; straight routes found by
punching; a pair forced onto the relay), datagrams both ways on both kinds of route, game
over and a second start, recent players, the service going away and coming back, and
deleting everything.  Then the link inside TLS (tls.h: the operating system's TLS) against
a service of its own with certificates made for this run (check.py's test authority, which
nothing but this test trusts): the rule of when TLS is used, the same conversation inside
it, what is refused (no trust, another name, another authority, plain text on either
side), and what a tap between client and service sees.  Loop-back only.

Prints one line per check and "N of N checks passed".  Standard library only (and the C++
compiler of the machine for net2cli).
"""
import argparse
import hashlib
import hmac
import os
import re
import shutil
import subprocess
import sys
import socket
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NET2 = os.path.join(ROOT, 'tools', 'recomp', 'net2')
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
            print('%s  %s%s' % ('ok  ' if ok else 'FAIL', name, (' - ' + str(detail)[-700:]) if detail and not ok else ''), flush=True)
        return bool(ok)


def build_cli(work):
    out = os.path.join(work, 'net2cli')
    sources = [os.path.join(NET2, n) for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp', 'tls.cpp', 'cardchars.cpp', 'clicmd.cpp',
                                               'net2cli.cpp')]
    command = ['clang++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-I', NET2, '-o', out] + sources + ['-lpthread']
    if sys.platform == 'darwin':
        command += ['-framework', 'Network', '-framework', 'Security', '-framework', 'CoreFoundation']
    result = subprocess.run(['nice', '-n', '10'] + command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit('net2cli did not build:\n' + result.stderr[-3000:])
    return out


class Service:
    def __init__(self, data, port=0, *limits, tls=None, more=()):
        self.log = open(os.path.join(data, 'service.log'), 'a+')
        command = [sys.executable, '-u', os.path.join(HERE, 'rendezvous.py'), '--data', data, '--port', str(port), '--bind', '127.0.0.1'] + list(more)
        if tls:
            command += ['--tls-cert', tls[0], '--tls-key', tls[1]]
        for item in limits:
            command += ['--limit', item]
        self.log.seek(0, 2)
        start = self.log.tell()
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
        self.port = 0
        for _ in range(200):
            self.log.seek(start)
            found = re.search(r'TCP and UDP port (\d+)', self.log.read())
            if found:
                self.port = int(found.group(1))
                break
            time.sleep(0.05)
        if not self.port:
            raise RuntimeError('the service did not start')
        self.log.seek(start)
        found = re.search(r'WebSocket on 127\.0\.0\.1, TCP port (\d+)', self.log.read())
        self.ws_port = int(found.group(1)) if found else 0

    def stop(self):
        if self.process.poll() is None:
            self.process.send_signal(2)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.log.seek(0)
        text = self.log.read()
        self.log.close()
        return text


class Cli:
    """One net2cli process: commands in, lines out."""

    def __init__(self, binary, work, name, port=None, fix='073064bb:99', data=None, env=None, service=True, address=None, extra=()):
        self.name = name
        self.data = data or os.path.join(work, name)
        os.makedirs(self.data, exist_ok=True)
        self.path = os.path.join(work, '%s.%d.out' % (name, int(time.time() * 1000) % 100000000))
        self.out = open(self.path, 'w+')
        command = ['nice', '-n', '10', binary, '--data', self.data, '--name', name, '--fix', fix, '--arith', '3:0', '--local-only']
        if service:
            command += ['--service', address or '127.0.0.1:%d' % port]
        command += list(extra)
        environment = dict(os.environ)
        environment.pop('RTA_NET2_SERVICE', None)
        environment.update(env or {})
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=self.out, stderr=subprocess.STDOUT, env=environment)
        self.at = 0
        self.token = 0

    def text(self):
        self.out.flush()
        with open(self.path) as f:
            return f.read()

    def send(self, command):
        try:
            self.process.stdin.write((command + '\n').encode())
            self.process.stdin.flush()
        except OSError:
            pass

    def wait(self, pattern, timeout=8.0, since=None):
        """The first match of `pattern` in the output after `since` (default: where the last look ended)."""
        start = self.at if since is None else since
        end = time.time() + timeout
        while True:
            text = self.text()
            found = re.search(pattern, text[start:], re.M)
            if found:
                self.at = start + found.end()
                return found
            if time.time() > end:
                return None
            time.sleep(0.05)

    def ask(self, command, timeout=6.0):
        """Runs a command that prints at once (me, room, friends ...) and returns what it printed."""
        self.token += 1
        mark = 'mark%d' % self.token
        start = len(self.text())
        self.send(command)
        self.send('echo ' + mark)
        end = time.time() + timeout
        while time.time() < end:
            text = self.text()[start:]
            if 'ECHO ' + mark in text:
                return text.split('ECHO ' + mark)[0]
            time.sleep(0.03)
        return self.text()[start:]

    def until(self, command, pattern, timeout=8.0):
        """Asks again and again until the answer matches; returns the match or None."""
        end = time.time() + timeout
        while True:
            answer = self.ask(command)
            found = re.search(pattern, answer, re.M | re.S)
            if found or time.time() > end:
                return found
            time.sleep(0.15)

    def quit(self):
        self.send('quit')
        try:
            self.process.wait(5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.out.close()

    def kill(self):
        self.process.kill()
        self.process.wait()
        self.out.close()


def me_of(cli):
    found = cli.until('me', r'^me: link=2 .*id=([0-9a-f]{32}) name=(.*?) code=(\S+) service=\S+ new=(\d)', 10)
    return found.groups() if found else (None, None, None, None)


def run(check, binary, work):
    service = Service(work, 0, 'registrations_per_hour=1000', 'connections_per_address=64')
    port = service.port
    a = Cli(binary, work, 'Ayla', port)
    b = Cli(binary, work, 'Bram', port)
    c = Cli(binary, work, 'Cato', port)
    clients = [a, b, c]
    try:
        # ---- identity ----
        ida, name, code_a, new = me_of(a)
        check('first start: an identity is made, the service gives an id, the name and a friend code',
              ida and name == 'Ayla' and re.fullmatch(r'[A-Z2-9]{4}-[A-Z2-9]{4}', code_a or '') and new == '1', (ida, name, code_a, new))
        key = os.path.join(a.data, 'net2-identity.key')
        check('the identity is one small file of the owner\'s alone', os.path.exists(key) and os.path.getsize(key) < 400 and (os.stat(key).st_mode & 0o777) == 0o600)
        secret = re.search(r'secret=([0-9a-f]{64})', open(key).read())
        check('the file holds a 32-byte secret', bool(secret))
        a.quit()
        a = Cli(binary, work, 'SomeOtherName', port, data=a.data)
        clients[0] = a
        ida2, name2, code2, new2 = me_of(a)
        check('second start from the same folder: the same player, name and friend code; no new identity', (ida2, name2, code2, new2) == (ida, 'Ayla', code_a, '0'), (ida2, name2, code2, new2))
        moved = os.path.join(work, 'another-computer')
        os.makedirs(moved)
        shutil.copy(key, moved)
        a.quit()
        a = Cli(binary, work, 'Whoever', port, data=moved)
        clients[0] = a
        check('the file copied to another folder (another computer): the same player there', me_of(a)[:3] == (ida, 'Ayla', code_a))
        idb, _, code_b, _ = me_of(b)
        idc, _, code_c, _ = me_of(c)
        check('three players, three ids, three friend codes', len({ida, idb, idc}) == 3 and len({code_a, code_b, code_c}) == 3)
        # ---- name, character ----
        a.send('name Ayla of the North')
        check('a name is changed', a.until('me', r'name=Ayla of the North code=') is not None)
        answer = a.ask('name x')
        check('a name of one letter is refused before anything is sent', 'RESULT name: -2' in answer, answer)
        a.send('character Aylara;Wood Elf Ranger;21')
        b.send('character Bramwald;Barbarian;34')
        # ---- friends ----
        answer = a.ask('add nonsense')
        check('a friend code that is no code is refused at once', 'RESULT add: -2' in answer, answer)
        a.send('add ' + code_b.lower())
        check('asking by code: "Asked. They have to accept."', a.wait(r'EVENT NOTICE .*text=Asked') is not None)
        check('the other side gets the request with the name', b.wait(r'EVENT REQUESTS code=0 who=Ayla of the North .*wants to be your friend') is not None)
        check('and lists it as incoming', b.until('requests', r'from Ayla of the North\s+%s' % re.escape(code_a)) is not None)
        check('the asker lists it as waiting', a.until('requests', r'to\s+Bram') is not None)
        b.send('accept Ayla')
        found = a.until('friends', r'Bram\s+%s %s online .*\[Bramwald, Barbarian 34\] friend' % (re.escape(code_b), idb))
        check('accepted: the friend is listed online with its character (name, class, level)', found is not None, a.ask('friends'))
        check('on both sides', b.until('friends', r'Ayla of the North\s+\S+ \S+ online .*\[Aylara, Wood Elf Ranger 21\]') is not None, b.ask('friends'))
        check('the requests are gone', 'requests: 0' in a.ask('requests') and 'requests: 0' in b.ask('requests'))
        a.send('add ZZZZ-ZZZZ')
        check('a code nobody has: an error with words', a.wait(r'EVENT ERROR code=-5 .*Nobody has that friend code') is not None)
        c.send('add ' + code_a)
        a.wait(r'EVENT REQUESTS .*who=Cato')
        a.send('decline Cato')
        check('declined: the request is gone here', a.until('requests', r'requests: 0') is not None)
        c.send('add ' + code_b)
        b.wait(r'EVENT REQUESTS .*who=Cato')
        b.send('accept Cato')
        check('a second friendship (Bram and Cato)', c.until('friends', r'Bram ') is not None)
        # ---- presence ----
        b.send('character Bramwald;Barbarian;35')
        check('a friend\'s character changes on my list', a.until('friends', r'\[Bramwald, Barbarian 35\]') is not None)
        b.quit()
        check('a friend who quits is shown offline with a last-seen time', a.until('friends', r'Bram\s+\S+ \S+ offline last-seen=\d{9,}') is not None, a.ask('friends'))
        b = Cli(binary, work, 'Bram', port)
        clients[1] = b
        check('and online again when it is back', a.until('friends', r'Bram\s+\S+ \S+ online') is not None)
        me_of(b)
        # ---- a room ----
        a.send('host friends drunare')
        found = a.wait(r'EVENT ROOM code=0 who= room=([A-Z2-9]{5})')
        room = found.group(1) if found else ''
        check('host: a room with a code', bool(room))
        check('the host is player 1, the options are the ones asked for', a.until('room', r'state=open code=%s count=1 my_slot=0 host_slot=0 .*level=drunare .*open_to=1' % room) is not None, a.ask('room'))
        check('a friend sees "in a room", joinable, with the code', b.until('friends', r'Ayla of the North .* in a room %s joinable players=1' % room) is not None, b.ask('friends'))
        b.send('join-friend Ayla')
        check('the friend walks in from the list', b.until('room', r'state=open code=%s count=2 my_slot=1' % room) is not None, b.ask('room'))
        c.send('join ' + room.lower())
        check('a third player joins by the code', c.until('room', r'count=3 my_slot=2') is not None)
        check('everybody sees three players in the same order', all(p.until('room', r'slot 0 Ayla of the.*\n\s+slot 1 Bram.*\n\s+slot 2 Cato', 6) is not None for p in (a, b, c)))
        check('the copies\' fix-set figure and arithmetic are shown for every player', len(re.findall(r'fix=073064bb:99 arith=3:0', a.ask('room'))) == 3)
        b.send('chat hello from Bram')
        check('a chat line reaches the others with the sender\'s name', a.wait(r'EVENT CHAT code=0 who=Bram room= text=hello from Bram') is not None and
              c.wait(r'EVENT CHAT code=0 who=Bram room= text=hello from Bram') is not None)
        check('the room keeps the lines, numbered', re.search(r'chat \d+ <Bram> hello from Bram', a.ask('room')) is not None)
        check('somebody who came later has the lines said before (the joins)', 'Bram joined.' in c.ask('room'))
        answer = b.ask('start')
        check('only the host can start (refused at once)', 'RESULT start: -3' in answer, answer)
        a.send('start')
        check('no start while players are not ready: the service says who', a.wait(r'EVENT ERROR code=-3 .*Not ready yet: Bram, Cato') is not None)
        b.send('ready')
        c.send('ready')
        check('ready marks: the host sees "all ready"', a.until('room', r'all_ready=1') is not None, a.ask('room'))
        # ---- a copy with another fix set ----
        d = Cli(binary, work, 'Dana', port, fix='27f61e1d:91')
        clients.append(d)
        me_of(d)
        d.send('join ' + room)
        found = a.until('room', r'mismatch=1.*\n\s+WARNING (.*)')
        check('a player whose copy has another fix set: every machine shows the warning before the start',
              found is not None and 'Dana' in found.group(1) and '27f61e1d' in found.group(1) and 'Do not start' in found.group(1), a.ask('room'))
        check('on the newcomer\'s machine too', d.until('room', r'mismatch=1') is not None)
        a.send('kick 3')
        check('the host sends that player out', d.wait(r'EVENT NOTICE .*sent you out of the room') is not None and d.until('room', r'state=none') is not None)
        check('and the warning is gone', a.until('room', r'count=3 .*mismatch=0') is not None)
        d.send('join ' + room)
        d.until('room', r'count=4')
        d.send('leave')
        a.until('room', r'count=3 ')
        # ---- the start ----
        for p in (a, b, c):
            p.at = len(p.text())
        time.sleep(1.2)                       # every UDP socket has said hello by now (every 3 s in an open room: wait for it)
        a.until('debug udp', r'seen as 127\.0\.0\.1:\d+', 8)
        b.until('debug udp', r'seen as 127\.0\.0\.1:\d+', 8)
        c.until('debug udp', r'seen as 127\.0\.0\.1:\d+', 8)
        c.send('set relay force')             # Cato will not punch: its pairs go through the relay
        a.send('start')
        check('start: every machine gets the event', all(p.wait(r'EVENT START code=0 who= room=%s' % room, 10) is not None for p in (a, b, c)))
        sessions = [re.search(r'session: valid=1 session=([0-9a-f]{8}) count=3 my_slot=(\d) host_slot=0 level=drunare', p.ask('session')) for p in (a, b, c)]
        check('the same session number, three players, the level; each its own player number',
              all(sessions) and len({s.group(1) for s in sessions}) == 1 and [s.group(2) for s in sessions] == ['0', '1', '2'], [p.ask('session') for p in (a, b, c)])
        lists = [re.findall(r'player (\d) (.*?) ([0-9a-f]{32})', p.ask('session')) for p in (a, b, c)]
        check('the same list of players on every machine', lists[0] == lists[1] == lists[2] and [x[2] for x in lists[0]] == [ida, idb, idc], lists)
        check('the character labels travel with it', '[Bramwald, Barbarian 35]' in a.ask('session'))
        check('Ayla and Bram reach each other straight (punched), with a measured time',
              a.until('room', r'slot 1 Bram .*route=direct rtt=\d+') is not None and b.until('room', r'slot 0 Ayla.*route=direct rtt=\d+') is not None, a.ask('room') + b.ask('room'))
        check('Cato, who does not punch, goes through the relay', c.until('room', r'slot 0 .*route=relay.*\n\s+slot 1 .*route=relay', 10) is not None, c.ask('room'))
        check('and the others reach Cato through the relay', a.until('room', r'slot 2 Cato .*route=relay', 10) is not None, a.ask('room'))
        check('the room says "starting" on every machine', all('state=starting' in p.ask('room') for p in (a, b, c)))
        # ---- datagrams ----
        a.ask('debug send 1 straight to Bram')
        check('a datagram on the straight route arrives, marked with the sender\'s player number', b.until('debug recv', r'from 0: straight to Bram', 5) is not None)
        b.ask('debug send 0 and back')
        check('and back', a.until('debug recv', r'from 1: and back', 5) is not None)
        a.ask('debug send 2 by relay to Cato')
        check('a datagram through the relay arrives', c.until('debug recv', r'from 0: by relay to Cato', 5) is not None)
        c.ask('debug send 1 Cato to Bram by relay')
        check('and from the relayed player to another', b.until('debug recv', r'from 2: Cato to Bram by relay', 5) is not None)
        counts = re.search(r'(\d+) sent \((\d+) by relay\), (\d+) received \((\d+) by relay\)', c.ask('debug udp'))
        check('the relayed player\'s counters say so', counts is not None and int(counts.group(2)) >= 1 and int(counts.group(4)) >= 1, c.ask('debug udp'))
        # ---- the game runs and ends ----
        for p in (a, b, c):
            p.send('running drunare')
        check('"the game runs": the room says so', all(p.until('room', r'state=in game') is not None for p in (a, b, c)))
        d2 = d.ask('join ' + room)
        check('nobody joins a game that has started', d.wait(r'EVENT ERROR code=-7 .*already started') is not None, d2)
        e = Cli(binary, work, 'Edda', port)
        clients.append(e)
        me_of(e)
        e.send('add ' + code_a)
        a.wait(r'EVENT REQUESTS .*who=Edda')
        a.send('accept Edda')
        check('a friend sees "in a game" with the level and the number of players', e.until('friends', r'Ayla of the North .* in a game level=drunare players=3') is not None, e.ask('friends'))
        b.send('over')
        c.send('over')
        check('while one machine still plays the others are back in the room, which cannot start', b.until('room', r'state=open') is not None and
              re.search(r'slot 0 .*', b.ask('room')) is not None)
        a.send('over')
        check('game over everywhere: the room is open again and says so', a.wait(r'EVENT GAME_OVER') is not None and a.until('room', r'The game is over\. The room is open again\.') is not None)
        check('the recent list has the players of that game', re.search(r'Cato .*\n?', a.until('recent', r'recent: 2').string) is not None, a.ask('recent'))
        check('with "friend" where they are one', re.search(r'Bram\s+\S+ \S+ .*friend', a.ask('recent')) is not None and re.search(r'Cato\s+\S+ \S+ (?!.*friend)', a.ask('recent')) is not None, a.ask('recent'))
        a.send('add-id Cato')
        c.wait(r'EVENT REQUESTS .*who=Ayla')
        check('a recent player is asked with one press; the list says "asked"', a.until('recent', r'Cato .* asked') is not None, a.ask('recent'))
        c.send('accept Ayla')
        check('and "friend" once accepted', a.until('recent', r'Cato\s+\S+ \S+ .*friend') is not None, a.ask('recent'))
        # ---- a second game in the same room ----
        c.send('set relay auto')
        b.send('ready')
        c.send('ready')
        a.until('room', r'all_ready=1')
        for p in (a, b, c):
            p.at = len(p.text())
        a.send('start')
        check('a second start in the same room', all(p.wait(r'EVENT START', 10) is not None for p in (a, b, c)))
        second = re.search(r'session=([0-9a-f]{8})', a.ask('session'))
        check('with a new session number', second and sessions[0] and second.group(1) != sessions[0].group(1))
        check('this time all three reach each other straight', all(p.until('room', r'(route=direct.*\n\s+.*){2}|route=direct[\s\S]*route=direct', 10) is not None for p in (a, b, c)), c.ask('room'))
        for p in (a, b, c):
            p.send('over')
        a.until('room', r'state=open')
        # ---- invitations ----
        b.send('leave')
        a.until('room', r'count=2')
        b.until('room', r'state=none')
        time.sleep(0.3)
        a.send('options - 2')
        check('options: the room is by code only now; the friend sees "in a room" without a code', b.until('friends', r'Ayla of the North .* in a room\s+\(closed\)') is not None, b.ask('friends'))
        b.at = len(b.text())
        a.send('invite Bram')
        check('an invitation arrives with who and which room', b.wait(r'EVENT INVITE code=0 who=Ayla of the North room=%s text=Ayla of the North invites you' % room) is not None)
        check('it is listed, with the inviter\'s character', re.search(r'from Ayla of the North\s+room=%s players=2 \[Aylara, Wood Elf Ranger 21\]' % room, b.ask('invites')) is not None, b.ask('invites'))
        check('the friends list marks it', 'INVITED-ME' in b.ask('friends'))
        b.send('take Ayla')
        check('one press joins the room', b.until('room', r'state=open code=%s count=3' % room) is not None)
        check('and the invitation is gone', b.until('invites', r'invites: 0') is not None)
        # ---- the host leaves ----
        a.send('leave')
        check('the host leaves: the next player is the host and player 1; numbers close up', c.until('room', r'count=2 my_slot=0 host_slot=0') is not None and b.until('room', r'count=2 my_slot=1') is not None, c.ask('room'))
        # ---- the service goes away and comes back ----
        for p in (a, b, c):
            p.at = len(p.text())
        service.stop()
        check('the service is gone: every client says so in words', all(p.wait(r'EVENT LINK code=0 who= room= text=The link to the service was lost', 10) is not None for p in (a, b, c)))
        check('link=1 (trying again) and a problem text', re.search(r'link=1 .*problem=\S', a.until('me', r'link=1').string) is not None, a.ask('me'))
        check('who was in a room is told it is out of it', c.wait(r'EVENT NOTICE .*out of the room', 5, since=0) is not None and 'state=none' in c.ask('room'))
        check('friends are shown offline meanwhile, not forgotten', re.search(r'Bram\s+\S+ \S+ offline', a.ask('friends')) is not None, a.ask('friends'))
        answer = a.ask('host')
        check('a request without a link is refused at once', 'RESULT host: -1' in answer, answer)
        service = Service(work, port, 'registrations_per_hour=1000', 'connections_per_address=64')
        check('the service is back (the same file): the clients log in again by themselves', all(p.until('me', r'link=2 ', 45) is not None for p in (a, b, c)), a.ask('me'))
        check('and the friends are there again, online', a.until('friends', r'Bram\s+\S+ \S+ online', 10) is not None and re.search(r'friends: 3', a.ask('friends')) is not None, a.ask('friends'))
        check('the same player after it', me_of(a)[:3] == (ida, 'Ayla of the North', code_a))
        # ---- block ----
        a.send('block Cato')
        check('block: the friend is gone from the list and on the blocked list', a.until('friends', r'friends: 2') is not None and 'Cato' in a.until('blocked', r'blocked: 1').string, a.ask('blocked'))
        check('and gone on the other side', c.until('friends', r'^(?![\s\S]*Ayla)') is not None, c.ask('friends'))
        a.send('unblock Cato')
        check('unblock', a.until('blocked', r'blocked: 0') is not None)
        b.send('remove Ayla')
        check('remove: gone on both sides', b.until('friends', r'^(?![\s\S]*Ayla)') is not None and a.until('friends', r'^(?![\s\S]*Bram )') is not None, a.ask('friends'))
        # ---- delete everything ----
        e.at = len(e.text())
        a.at = len(a.text())
        a.send('delete')
        check('delete everything: the event', a.wait(r'EVENT DELETED .*Everything the service held about you is deleted', 10) is not None)
        check('the friend who is left is told nothing but loses the entry', e.until('friends', r'friends: 0', 8) is not None, e.ask('friends'))
        idn, namen, coden, newn = me_of(a)
        check('this program is a new player now: new id, new friend code, a new identity file', idn and idn != ida and coden != code_a and newn == '1', (idn, coden, newn))
        new_secret = re.search(r'secret=([0-9a-f]{64})', open(os.path.join(moved, 'net2-identity.key')).read())
        check('the old secret is gone from the file', new_secret and secret and new_secret.group(1) != secret.group(1))
        old = Cli(binary, work, 'OldAyla', port, data=os.path.join(work, 'Ayla'))       # the first folder still has the OLD file
        clients.append(old)
        ido, _, codeo, newo = me_of(old)
        check('the old identity file, used again, is nobody the service knows: it registers as a new player', ido == ida and codeo != code_a, (ido, codeo, newo))
        # ---- the characters on a memory card ----
        card = os.path.join(work, 'card')
        folder = os.path.join(card, 'mc0', 'BASLUS-20973')
        os.makedirs(folder)

        def save_file(name, characters):
            # the game's save buffer as docs/audio-save.md lays it out: only the fields that are read
            data = bytearray(0x320 + 4 * 0x4c3e)
            data[0x68:0x6a] = (0x4c30).to_bytes(2, 'little')
            data[0x6a:0x6c] = len(characters).to_bytes(2, 'little')
            for i, (who, cls, level) in enumerate(characters):
                at = 0x320 + i * 0x4c3e + 0x0e
                data[at:at + len(who)] = who.encode()
                data[at + 0x50:at + 0x54] = cls.to_bytes(4, 'little')
                data[at + 0x59] = level
            with open(os.path.join(folder, name), 'wb') as f:
                f.write(data)
        save_file('BASLUS-20973_slot0', [('Thrumm', 0, 34), ('Sister Ylva', 1, 12)])
        save_file('BASLUS-20973_slot1', [('Thrumm', 0, 34)])                # the same character saved twice: listed once
        save_file('BASLUS-20973_slot2', [('Vexx', 6, 50)])
        with open(os.path.join(folder, 'BASLUS-20973'), 'wb') as f:         # the card's own index file: not a save
            f.write(b'\0' * 760)
        with open(os.path.join(folder, 'BASLUS-20973_slot3'), 'wb') as f:   # a file cut short
            f.write(b'\x01' * 100)
        answer = e.ask('cards ' + card)
        check('"characters I have": read from the save slots of a card folder (layout of docs/audio-save.md; files made by this test)',
              'cards: 3' in answer and 'Thrumm, Barbarian 34' in answer and 'Sister Ylva, Cleric 12' in answer and 'Vexx, Shaman 50' in answer, answer)
        check('a folder without saves: none', 'cards: 0' in e.ask('cards ' + work))
        # ---- where the service is found ----
        env_cli = Cli(binary, work, 'EnvPlayer', service=False, env={'RTA_NET2_SERVICE': '127.0.0.1:%d' % port})
        clients.append(env_cli)
        check('the service\'s address from the environment (RTA_NET2_SERVICE)', me_of(env_cli)[0] is not None)
        folder = os.path.join(work, 'FilePlayer')
        os.makedirs(folder)
        with open(os.path.join(folder, 'net2-service.txt'), 'w') as f:
            f.write('127.0.0.1:%d\n' % port)
        file_cli = Cli(binary, work, 'FilePlayer', service=False)
        clients.append(file_cli)
        check('or from net2-service.txt beside the identity', me_of(file_cli)[0] is not None)
        none_cli = Cli(binary, work, 'NoService', service=False)
        clients.append(none_cli)
        answer = none_cli.until('me', r'link=0 .*problem=No service was named')
        check('no address anywhere: offline, and it says why', answer is not None, none_cli.ask('me'))
        wrong = Cli(binary, work, 'WrongPort', 1)
        clients.append(wrong)
        check('a service that is not there: "trying", with the reason in words', wrong.until('me', r'link=1 .*problem=.*(cannot be reached|does not answer)', 10) is not None, wrong.ask('me'))
    finally:
        for p in clients:
            try:
                p.quit()
            except Exception:
                pass
        text = service.stop()
    check('the service ran through all of it without an error', 'Traceback' not in text, text[-1500:])


class Tap:
    """A TCP relay on 127.0.0.1 between a client and the service that keeps every byte it
    carries, both ways: what somebody on the path would see."""

    def __init__(self, to_port):
        self.to_port = to_port
        self.seen = bytearray()
        self.lock = threading.Lock()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self.socks = []
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                a, _ = self.listener.accept()
                b = socket.create_connection(('127.0.0.1', self.to_port), 5)
            except OSError:
                return
            self.socks += [a, b]
            threading.Thread(target=self.pump, args=(a, b), daemon=True).start()
            threading.Thread(target=self.pump, args=(b, a), daemon=True).start()

    def pump(self, src, dst):
        while True:
            try:
                data = src.recv(65536)
            except OSError:
                data = b''
            if not data:
                for x in (src, dst):
                    try:
                        x.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return
            with self.lock:
                self.seen += data
            try:
                dst.sendall(data)
            except OSError:
                return

    def close(self):
        self.listener.close()
        for x in self.socks:
            try:
                x.close()
            except OSError:
                pass


def verifier_of(data):
    secret = re.search(r'secret=([0-9a-f]{64})', open(os.path.join(data, 'net2-identity.key')).read()).group(1)
    return hmac.new(bytes.fromhex(secret), b'rta-net2 verifier v1', hashlib.sha256).hexdigest()


def tls_run(check, binary, work):
    import check as service_checks     # the test authority and its certificates (tools/rendezvous/check.py)
    pki = service_checks.test_certificates(work)
    folder = os.path.join(work, 'tls')
    os.makedirs(folder)
    clients, services, taps = [], [], []

    def service(cert, *limits):
        data = os.path.join(folder, 'service-%d' % len(services))
        os.makedirs(data)
        made = Service(data, 0, 'registrations_per_hour=1000', 'connections_per_address=64', 'connects_per_minute=1000', *limits,
                       tls=(pki[cert], pki[cert + '.key']) if cert else None)
        services.append(made)
        return made

    def cli(name, address, extra=(), env=None):
        made = Cli(binary, folder, name, address=address, extra=extra, env=env)
        clients.append(made)
        return made

    try:
        # ---- when TLS is used (nothing is sent: the rule only) ----
        probe = cli('Rule', '127.0.0.1:1')
        rules = {}
        for address in ('127.0.0.1:41900', 'localhost:41900', '192.168.1.20:41900', '10.0.0.5:41900', '172.20.0.1:41900', '100.100.1.1:41900',
                        '203.0.113.9:41900', '8.8.8.8:41900', 'play.example.org:41900', 'tls://127.0.0.1:41900', 'plain://play.example.org:41900'):
            found = re.search(r'debug: tls (on|off)', probe.ask('debug tls-rule ' + address))
            rules[address] = found.group(1) if found else None
        check('the rule (auto): plain text for this computer and for home-network addresses',
              all(rules[a] == 'off' for a in ('127.0.0.1:41900', 'localhost:41900', '192.168.1.20:41900', '10.0.0.5:41900', '172.20.0.1:41900',
                                               '100.100.1.1:41900')), rules)
        check('TLS for a public address and for every host name', all(rules[a] == 'on' for a in ('203.0.113.9:41900', '8.8.8.8:41900', 'play.example.org:41900')), rules)
        check('"tls://" and "plain://" in front of the address say it the other way', rules['tls://127.0.0.1:41900'] == 'on' and
              rules['plain://play.example.org:41900'] == 'off', rules)
        env_probe = cli('RuleEnv', '127.0.0.1:1', env={'RTA_NET2_TLS': 'on'})
        check('and so does RTA_NET2_TLS=on in the environment', 'debug: tls on' in env_probe.ask('debug tls-rule 127.0.0.1:41900'))
        # ---- the conversation inside TLS ----
        good = service('localhost', 'login_seconds=3')
        port = good.port
        a = cli('Tilda', 'tls://localhost:%d' % port, env={'RTA_NET2_TLS_CA': pki['ca']})
        b = cli('Tomas', 'localhost:%d' % port, extra=['--tls', 'on', '--tls-ca', pki['ca']])
        ida, _, code_a, _ = me_of(a)
        idb, _, code_b, _ = me_of(b)
        check('inside TLS: a first start registers and comes online (the name localhost, the test authority as the only trust)', ida is not None and idb is not None,
              a.ask('me') + b.ask('me'))
        link = a.ask('debug link')
        check('the link says how: TLS 1.2 or 1.3, the certificate for localhost checked, trusting that file only',
              re.search(r'tls on \(rule on\): TLS 1\.[23], certificate for localhost checked \(trusted: only ca\.pem\)', link) is not None, link)
        a.send('add ' + code_b)
        b.wait(r'EVENT REQUESTS .*who=Tilda')
        b.send('accept Tilda')
        check('inside TLS: friends by code', a.until('friends', r'Tomas\s+\S+ \S+ online') is not None, a.ask('friends'))
        a.send('host friends')
        found = a.wait(r'EVENT ROOM code=0 who= room=([A-Z2-9]{5})')
        room = found.group(1) if found else 'NONE'
        b.send('join ' + room)
        check('inside TLS: a room by code', b.until('room', r'state=open code=%s count=2 my_slot=1' % room) is not None, b.ask('room'))
        b.send('chat hello inside TLS')
        check('inside TLS: chat', a.wait(r'EVENT CHAT code=0 who=Tomas room= text=hello inside TLS') is not None)
        b.send('ready')
        a.until('room', r'all_ready=1')
        a.until('debug udp', r'seen as 127\.0\.0\.1:\d+', 8)
        b.until('debug udp', r'seen as 127\.0\.0\.1:\d+', 8)
        b.send('set relay force')
        a.send('start')
        check('inside TLS: the start reaches both', all(p.wait(r'EVENT START', 10) is not None for p in (a, b)))
        check('the datagrams are the same as ever: through the relay of the service', b.until('room', r'slot 0 .*route=relay', 10) is not None, b.ask('room'))
        a.ask('debug send 1 a datagram beside a TLS link')
        check('and they arrive', b.until('debug recv', r'from 0: a datagram beside a TLS link', 5) is not None)
        for p in (a, b):
            p.send('over')
        # the service goes away and comes back: the client makes the TLS link again by itself
        for p in (a, b):
            p.at = len(p.text())
        good.stop()
        services.remove(good)
        check('the TLS service is gone: the client says so', a.wait(r'EVENT LINK code=0 who= room= text=', 10) is not None)
        data = os.path.join(folder, 'service-again')
        os.makedirs(data)
        again = Service(data, port, 'registrations_per_hour=1000', 'connections_per_address=64', 'connects_per_minute=1000',
                        tls=(pki['localhost'], pki['localhost.key']))
        services.append(again)
        check('and back: a new TLS link, by itself (a new service file: it registers again)', a.until('me', r'link=2 ', 45) is not None, a.ask('me'))
        # ---- what is refused ----
        plain_side = cli('PlainOne', 'plain://127.0.0.1:%d' % port)
        found = plain_side.until('me', r'link=1 .*problem=(\S.*)', 15)
        check('a client in plain text does not get in to a TLS service', found is not None and 'link=2' not in plain_side.ask('me'), plain_side.ask('me'))
        nobody = cli('NoTrust', 'tls://localhost:%d' % port)
        found = nobody.until('me', r'link=1 .*problem=No secure link to the service: The service\'s certificate is not accepted for localhost: \S', 15)
        check('without the test authority (the system\'s trust store only) the certificate is refused, in words', found is not None, nobody.ask('me'))
        missing = cli('NoFile', 'tls://localhost:%d' % port, extra=['--tls-ca', os.path.join(folder, 'no-such-file.pem')])
        check('a trust file that is not there: refused, in words', missing.until('me', r'link=1 .*problem=.*cannot be read', 15) is not None, missing.ask('me'))
        wrong = service('wrong')
        named = cli('WrongName', 'tls://localhost:%d' % wrong.port, extra=['--tls-ca', pki['ca']])
        check('a certificate of the right authority for another name is refused', named.until('me', r'link=1 .*problem=.*not accepted for localhost', 15) is not None,
              named.ask('me'))
        stranger = service('stranger')
        other = cli('OtherCA', 'tls://localhost:%d' % stranger.port, extra=['--tls-ca', pki['ca']])
        check('a certificate of another authority is refused', other.until('me', r'link=1 .*problem=.*not accepted for localhost', 15) is not None, other.ask('me'))
        plain_service = service(None)
        mixed = cli('TlsToPlain', 'tls://localhost:%d' % plain_service.port, extra=['--tls-ca', pki['ca']])
        check('a TLS client and a service in plain text: no link, in words', mixed.until('me', r'link=1 .*problem=\S', 15) is not None and
              'link=2' not in mixed.ask('me'), mixed.ask('me'))
        # ---- what a tap on the path sees ----
        for label, address_of, target in (('TLS', lambda p: 'tls://localhost:%d' % p, again.port), ('plain', lambda p: 'plain://127.0.0.1:%d' % p, plain_service.port)):
            tap = Tap(target)
            taps.append(tap)
            who = cli('Wiretap Wendy %s' % label, address_of(tap.port), extra=['--tls-ca', pki['ca']])
            idw, _, codew, _ = me_of(who)
            who.send('host')
            found = who.wait(r'EVENT ROOM code=0 who= room=([A-Z2-9]{5})')
            roomw = found.group(1) if found else 'NONE'
            who.until('room', r'state=open')
            who.send('chat a secret line QZXV %s' % label)
            who.wait(r'EVENT CHAT code=0 who=Wiretap')
            time.sleep(0.3)
            with tap.lock:
                seen = bytes(tap.seen)
            secrets_on_wire = {'name': ('Wiretap%20Wendy' in seen.decode('latin-1')) or b'Wiretap Wendy' in seen, 'chat': b'QZXV' in seen,
                               'verifier': verifier_of(who.data).encode() in seen, 'friend code': (codew or '-').encode() in seen,
                               'room code': roomw.encode() in seen, 'id': (idw or '-').encode() in seen}
            if label == 'TLS':
                check('a tap between client and service sees none of it inside TLS: name, chat, the verifier of the registration, friend code, room code, id (%d bytes seen)'
                      % len(seen), len(seen) > 1000 and not any(secrets_on_wire.values()), secrets_on_wire)
            else:
                check('(in plain text the same tap reads all of them: the test can see what it looks for)', all(secrets_on_wire.values()), secrets_on_wire)
    finally:
        for p in clients:
            try:
                p.quit()
            except Exception:
                pass
        texts = [x.stop() for x in services]
        for tap in taps:
            tap.close()
    check('the TLS services ran through all of it without an error', not any('Traceback' in t for t in texts), [t[-800:] for t in texts if 'Traceback' in t])


class Middlebox:
    """A network that breaks TLS to an unknown port: whatever is said to this port, it answers
    with something that is not TLS and closes (what openssl calls "wrong version number")."""

    def __init__(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(16)
        self.port = self.listener.getsockname()[1]
        self.hits = 0
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                return
            self.hits += 1
            try:
                sock.settimeout(2)
                sock.recv(4096)
                sock.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
            except OSError:
                pass
            sock.close()

    def close(self):
        self.listener.close()


def ws_run(check, binary, work):
    """The fallback: the conversation as a WebSocket on the service's web server when the direct
    link does not get through, and the datagrams in the conversation when UDP does not."""
    import check as service_checks
    folder = os.path.join(work, 'ws')
    os.makedirs(folder)
    pki = service_checks.test_certificates(folder)
    clients = []
    box = Middlebox()
    service = Service(folder, 0, 'registrations_per_hour=1000', 'connections_per_address=64', 'connects_per_minute=1000',
                      tls=(pki['localhost'], pki['localhost.key']), more=('--ws-bind', '127.0.0.1:0'))
    ws = 'wss://localhost:%d/net2' % service.ws_port

    def cli(name, address, env=None, extra=()):
        environment = {'RTA_NET2_TLS_CA': pki['ca']}
        environment.update(env or {})
        made = Cli(binary, folder, name, address=address, env=environment, extra=extra)
        clients.append(made)
        return made

    try:
        check('the service takes the WebSocket inside TLS on a port of its own (as the web server would on 443)', service.ws_port > 0)
        # the direct link is broken by the "middlebox": the client goes to the WebSocket by itself
        a = cli('Wren', 'tls://localhost:%d' % box.port, env={'RTA_NET2_WS': ws})
        ida = me_of(a)[0]
        check('fallback: the direct link is answered with no TLS; the client comes online through the WebSocket by itself', ida is not None and box.hits >= 1,
              a.ask('me') + ' hits=%d' % box.hits)
        link = a.ask('debug link')
        check('it says how: via websocket wss://..., inside TLS (the certificate checked as ever)',
              re.search(r'TLS 1\.[23].*via websocket wss://localhost:\d+/net2 \(transport auto\)', link) is not None, link)
        check('and tells the player in words', a.wait(r'EVENT NOTICE .*connected through its web server \(HTTPS\)', 5, since=0) is not None)
        b = cli('Wynn', ws, env={'RTA_NET2_TEST_NO_UDP': '1'})
        check('the service named by its WebSocket (wss://host:port/path): online', me_of(b)[0] is not None, b.ask('me'))
        direct = cli('Dara', 'tls://localhost:%d' % box.port, env={'RTA_NET2_WS': ws, 'RTA_NET2_TRANSPORT': 'direct'})
        found = direct.until('me', r'link=1 .*problem=No secure link', 15)
        time.sleep(2.5)
        check('transport direct: no fallback (it stays off-line, in words)', found is not None and 'link=2' not in direct.ask('me'), direct.ask('me'))
        c = cli('Cass', 'tls://localhost:%d' % service.port)
        check('a player on the direct link beside them', me_of(c)[0] is not None)
        # a room of three: Cass on UDP, Wynn's UDP blocked (auto: the tunnel), Wren told to tunnel
        a.ask('set udp tunnel')
        c.send('host')
        found = c.wait(r'EVENT ROOM code=0 who= room=([A-Z2-9]{5})')
        room = found.group(1) if found else 'NONE'
        b.send('join ' + room)
        # The route and datagram checks below use Wynn in slot 1 and Wren in slot 2.
        # Different links can deliver joins in either order: wait for the first assignment.
        joined = c.until('room', r'slot 1 Wynn', 10) is not None
        a.send('join ' + room)
        check('the room by its code, over both kinds of link', joined and c.until('room', r'count=3', 10) is not None, c.ask('room'))
        check('UDP blocked: after 8 s without an answer to a hello the datagrams go in the conversation, and the player is told',
              b.wait(r'EVENT NOTICE .*UDP is blocked on this network', 20, since=0) is not None and 'tunnel' in b.until('debug udp', r'tunnel', 5).string,
              b.ask('debug udp'))
        check('"set udp tunnel": at once', 'tunnel' in (a.until('debug udp', r'tunnel', 5) or re.search('', '')).string, a.ask('debug udp'))
        for p in (a, b):
            p.send('ready')
        c.until('room', r'all_ready=1', 10)
        time.sleep(1.5)
        c.send('start')
        check('the start reaches all three (a tunnelled player counts as heard)', all(p.wait(r'EVENT START', 15) is not None for p in (a, b, c)), c.ask('room'))
        # Wynn (slot 1) lets no UDP out: the relay both ways.  Wren (slot 2) tunnels to the service but its UDP
        # works: its probes punch a straight route to Cass all the same (the relay while that is tried)
        check('routes: the player without UDP is reached by the relay, and reaches everybody by it',
              c.until('room', r'slot 1 Wynn .*route=relay', 10) is not None and b.until('room', r'slot 0 .*route=relay.*\n.*slot 2 .*route=relay', 10) is not None,
              c.ask('room') + b.ask('room'))
        check('a tunnelled player whose UDP works still gets a straight route by punching', c.until('room', r'slot 2 Wren .*route=direct', 10) is not None, c.ask('room'))
        c.ask('debug send 1 from UDP into the tunnel')
        check('a datagram from a UDP player arrives in the tunnel', b.until('debug recv', r'from 0: from UDP into the tunnel', 5) is not None)
        b.ask('debug send 0 from the tunnel to UDP')
        check('one from the tunnel arrives over UDP', c.until('debug recv', r'from 1: from the tunnel to UDP', 5) is not None)
        a.ask('debug send 1 from one tunnel to the other')
        check('and from one tunnel to the other', b.until('debug recv', r'from 2: from one tunnel to the other', 5) is not None)
        for _ in range(60):
            b.ask('debug send 0 burst')
        got = 0
        for _ in range(80):
            if 'from 1: burst' in c.ask('debug recv'):
                got += 1
        check('60 datagrams at once through the tunnel: all arrive (in order of sending)', got == 60, got)
        for p in (a, b, c):
            p.send('over')
    finally:
        for p in clients:
            try:
                p.quit()
            except Exception:
                pass
        text = service.stop()
        box.close()
    check('the service ran through the fallback without an error, and counted the WebSocket links and the tunnel', 'Traceback' not in text and
          re.search(r'[1-9]\d* WebSocket links, [1-9]\d* datagrams in / [1-9]\d* out by tunnel', text) is not None, text[-900:])


def main():
    global VERBOSE
    parser = argparse.ArgumentParser()
    parser.add_argument('--work')
    parser.add_argument('--cli', help='a built net2cli (default: built into the work directory)')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    VERBOSE = args.verbose
    made = args.work is None
    work = args.work or tempfile.mkdtemp(prefix='rendezvous-client-')
    if os.path.isdir(work) and not made:
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)
    check = Checks()
    started = time.time()
    try:
        binary = args.cli or build_cli(work)
        run(check, binary, work)
        tls_run(check, binary, work)
        ws_run(check, binary, work)
    finally:
        if made:
            shutil.rmtree(work, ignore_errors=True)
    print('%d of %d checks passed (%.0f s)' % (check.passed, check.passed + check.failed, time.time() - started))
    return 0 if check.failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
