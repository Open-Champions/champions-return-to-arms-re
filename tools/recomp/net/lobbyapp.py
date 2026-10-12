"""lobbyapp.py - the emulator-based application as one copy of a lobby pair (for lobbypair.py).

It is started as a silent background test window (tools/play-net/play.sh ... --rta-test),
goes online by itself (--rta-online host:CODE or join:CODE) and is driven over its control
socket (tools/play-net/ctl.py) through the same steps a native copy's script takes: a new
character the first time, Start for a host, drawn input.  It has no tick log, so what it
leaves for the comparison is samples: at intervals one batch of control commands reads the
lockstep tick, the shared seed, both players' positions as raw bits, hit points, gold and
experience, and the game's own checksum verdict (OUT/<role>.samples.tsv).  lobbypair.py
looks each sample up in the native copy's tick log.
"""
import os
import random
import string
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'play-net'))

G_PLAYERS, RECORD = 0x4d8af0, 0x4c30
SAMPLE = [('net', '0x4027ac', 's32'), ('seed', '0x404464', 'x32'), ('level', '0x41b721', 'str12'), ('nplayers', '0x4d8ae0', 's32')]
for n in (0, 1):
    obj = '[0x%x]' % (G_PLAYERS + n * RECORD + 0x43d8)
    rec = G_PLAYERS + n * RECORD
    SAMPLE += [('p%dx' % n, obj + '+0x10', 'x32'), ('p%dy' % n, obj + '+0x14', 'x32'), ('p%dz' % n, obj + '+0x18', 'x32'),
               ('p%dhp' % n, '0x%x' % (rec + 0xac), 'x32'), ('p%dgold' % n, '0x%x' % (rec + 0xe4), 's32'),
               ('p%dexp' % n, '0x%x' % (rec + 0x5c), 's32')]
SAMPLE += [('chkfail', '0x4f7144', 'u8'), ('net2', '0x4027ac', 's32')]


class AppCopy:
    def __init__(self, role, out, code, args):
        import lobbypair
        self.role, self.out, self.code, self.args = role, out, code, args
        self.directory = os.path.join(out, role + '-app')
        os.makedirs(self.directory, exist_ok=True)
        self.name = lobbypair.make_name(self.directory)
        self.new_character = not os.path.exists(os.path.join(self.directory, 'online-character'))
        # a unix socket path has to be short
        self.socket_path = os.path.join('/tmp', 'rta-lp-%d-%s.sock' % (os.getpid(), role))
        self.log = open(os.path.join(out, role + '.out'), 'w')
        command = ['nice', '-n', '19', os.path.join(ROOT, 'tools', 'play-net', 'play.sh'), '--data', self.directory, '--',
                   '--rta-test', 'native online (emulator partner)', '--rta-control', self.socket_path,
                   '--rta-online', '%s:%s' % ('host' if role == 'host' else 'join', code), '--rta-online-name', self.name]
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT)
        self.code_out = None
        self.play_lines = lobbypair.play_lines
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def say(self, text):
        self.log.write('[driver] %s\n' % text)
        self.log.flush()

    def peek(self, expression, kind):
        return self.control.ok('peek %s %s' % (expression, kind))

    def number(self, expression, kind='u32'):
        try:
            return int(self.peek(expression, kind), 16 if kind.startswith('x') else 10)
        except ValueError:
            return -1

    def wait_for(self, what, test, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.process.poll() is not None:
                raise RuntimeError('the application ended while waiting for ' + what)
            if test():
                self.say('%s (tick %d)' % (what, self.number('0x4027ac', 's32')))
                return
            time.sleep(0.5)
        raise RuntimeError('timed out waiting for ' + what)

    def tap_until(self, button, test, seconds, what):
        end = time.time() + seconds
        while time.time() < end:
            if test():
                self.say(what)
                return
            self.control.ok('tap %s 10 50' % button)
        raise RuntimeError('timed out pressing %s for %s' % (button, what))

    def sample(self, sink):
        lines = ['peek %s %s' % (expression, kind) for _, expression, kind in SAMPLE]
        self.control.file.write('\n'.join(lines) + '\n')
        self.control.file.flush()
        values = []
        for _ in SAMPLE:
            answer = self.control.file.readline().rstrip('\n')
            values.append(answer[3:] if answer.startswith('ok') else '?')
        if values[0] == values[-1]:         # the batch ran inside one vertical blank
            sink.write('\t'.join(values[:-1]) + '\n')
            sink.flush()
            return True
        return False

    def drive(self):
        import ctl
        page = lambda: self.number('0x8e2c02', 'u8')
        lobby = lambda: self.number('0x506160', 'u32')
        end = time.time() + 90
        while not os.path.exists(self.socket_path):
            if time.time() > end:
                raise RuntimeError('no control socket')
            time.sleep(0.5)
        self.control = ctl.Control(self.socket_path, timeout=600)
        self.wait_for('the game list', lambda: lobby() == 5, 300)
        if self.new_character:
            self.wait_for('the character screens', lambda: page() == 1, 300)
            time.sleep(2)
            self.tap_until('cross', lambda: page() == 2, 60, 'class taken')
            time.sleep(2)
            self.tap_until('cross', lambda: page() == 3, 60, 'looks taken')
            time.sleep(2)
            # The 20 points have to be spent before cross leaves the page; cross before that
            # brings a notice that takes another cross.  These screens lose short presses
            # (docs/issues/live-rig.md 19.3), so: more presses than points, then cross, and
            # again when the page has not changed.
            for attempt in range(10):
                for _ in range(30 if attempt == 0 else 10):
                    self.control.ok('tap right 12 12')
                self.control.ok('tap cross 12 90')
                if page() == 4:
                    break
                self.control.ok('tap cross 12 40')
            else:
                raise RuntimeError('the ability points could not be spent')
            self.say('points spent')
            self.control.ok('wait 90')
            # the name: three letters, then DONE.  The keyboard's cursor is the word at
            # 0x8e2ba0: row * 10 + column, the bottom row 60 to 63, then -2 (SPACE), -1 (DONE)
            cursor = lambda: self.number('0x8e2ba0', 's32')
            for _ in range(3):
                self.control.ok('tap cross 10 14')
            for _ in range(40):
                at = cursor()
                if at == -1:
                    break
                self.control.ok('tap down 10 14' if 0 <= at < 60 else 'tap right 10 14')
            else:
                raise RuntimeError('the name keyboard\'s cursor does not reach DONE (at %d)' % cursor())
            self.tap_until('cross', lambda: page() != 4 or lobby() in (5, 6), 60, 'name done')
        self.wait_for('the room', lambda: lobby() == 6, 400)
        if self.role == 'host':
            self.wait_for('somebody joined', lambda: self.number('[0x50613c]+0x740', 'u8') != 255, 600)
            self.wait_for('their character is chosen', lambda: self.number('[0x50613c]+0x782', 'u8') != 255, 300)
            time.sleep(3)
            self.tap_until('cross', lambda: lobby() == 12, 120, 'started')
        self.wait_for('in game', lambda: lobby() == 12, 900)
        self.wait_for('the hub', lambda: self.peek('0x41b721', 'str8') == 'hub', 300)
        self.wait_for('tick 200', lambda: self.number('0x4027ac', 's32') >= 200, 300)
        with open(os.path.join(self.out, self.role + '.samples.tsv'), 'w') as sink:
            sink.write('\t'.join(name for name, _, _ in SAMPLE[:-1]) + '\n')
            lines = self.play_lines(self.args.play, self.args.seed + (0 if self.role == 'host' else 1000))
            taken = 0
            for index, line in enumerate(lines):
                words = line.split()
                if words[0] == 'stick':
                    line = 'stick l %s %s' % (words[2], words[3])
                self.control.ok(line)
                if index % 25 == 0 and self.sample(sink):
                    taken += 1
            self.control.ok('stick l 128 128')
            self.control.ok('release all')
            for _ in range(20):
                self.control.ok('wait 20')
                if self.sample(sink):
                    taken += 1
        self.say('%d samples; tick %d; checksum failed %d; peers: %s' % (
            taken, self.number('0x4027ac', 's32'), self.number('0x4f7144', 'u8'), self.control.ok('peers')))
        self.say('online: ' + self.control.ok('online'))

    def run(self):
        try:
            self.drive()
            self.code_out = 0
        except Exception as error:      # the driver's own failure is the run's result
            self.say('FAILED: %s' % error)
            self.code_out = 3
        finally:
            # hold the game for the other copy's last frames, then end the application
            time.sleep(self.args.app_linger)
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            subprocess.run(['pkill', '-f', self.socket_path], capture_output=True)
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)

    def wait(self, timeout=None):
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise subprocess.TimeoutExpired('app', timeout)
        return self.code_out

    def kill(self):
        self.process.kill()
        subprocess.run(['pkill', '-f', self.socket_path], capture_output=True)


def start(role, out, code, args):
    return AppCopy(role, out, code, args)
