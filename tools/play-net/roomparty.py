#!/usr/bin/env python3
"""roomparty.py - the Mac application (this project's Play!) and the native program in one room
of our own rendezvous service, playing one lockstep game: the proof runs of
docs/issues/app-rendezvous.md.

  export RTA_DISC="/path/to/your/disc image.iso"
  python3 -B tools/play-net/roomparty.py OUT --copies app,native [--play FRAMES] [--level NAME --play2 FRAMES]
          [--relay force|never|mixed] [--external --service-address HOST --port N] [--app PATH] [--program PATH]
          [--app-start lobby|title [--signin-patch FILE]] [--menu-start]

--copies: two to four of "app", "native" and "godot", the first is the host. An app copy is the application
built under local/ (--app, default local/app-rv/build/.../Play), started off to the side as a test
window (--rta-test) with a control socket, a data folder of its own and --rta-room; a native copy is
tools/recomp/net2/n2party.py's (headless, $RTA_NATIVE_NET2 or --program), started by that file's own
start_copy. A godot copy is the Godot game scene (tools/godot/project/main.gd, the project staged under
$RTA_GODOT_OUT, default local/godot-spike) with that native copy's script and runtime options, as
--edition says (default classic: the portal's Classic choice). A rendezvous service of this run's own on 127.0.0.1 is started (tools/rendezvous) unless
--external names one already running.

Every copy boots by itself into the room (the host's code is read from its output), makes a new
character on the game's own screens (the app's are pressed through its control socket here, the
native copies' by their script), the host starts when all are in and ready, drawn input is played
for --play frames; with --level the pending level name is written in one lockstep tick on every copy
(the native program's tick-do and the application's --rta-tick-do, the same file) and --play2 more
frames are played there.  --level A,B,C: one level after the other, each --level-every ticks after
the one before. Compared: every pair of tick logs (tools/rig/compare.py ticks). One result
line goes to OUT/results.txt. Exit code 0: every copy in the level and no column differing.

The application is given the sections of tools/play-net/sections-suggested.txt that the native
program's translation carries (--sections, default: all of the file), and never the sign-in patch.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recomp', 'net2'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recomp', 'net'))
import ctl          # noqa: E402
import n2party      # noqa: E402  (start_copy, script_lines, room_code, own_address)
import lobbypair    # noqa: E402  (new_character_lines, play_lines)
import lobbyparty   # noqa: E402  (watches, split_games, story)

ROLES = ['host', 'j1', 'j2', 'j3']
A_PAGE, A_CHOSEN = 0x8e2c02, 0x4fbbe2
DEFAULT_APP = os.path.join(ROOT, 'local', 'app-rv', 'build', 'Source', 'ui_qt', 'Play.app', 'Contents', 'MacOS', 'Play')


def symbols():
    table = {}
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        for line in open(path, errors='replace'):
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 2 and re.fullmatch(r'[0-9a-fA-F]{6,8}', parts[0]) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', parts[1]):
                table.setdefault(parts[1], int(parts[0], 16))
    return table


SYMBOLS = symbols()


def numeric(expression):
    """names to numbers: the application knows no names"""
    return re.sub(r'\b[A-Za-z_][A-Za-z0-9_]*\b', lambda m: '0x%x' % SYMBOLS[m.group(0)] if m.group(0) in SYMBOLS else m.group(0), expression)


def typed(text):
    """'expr:type' (the last colon outside brackets)"""
    depth, colon = 0, -1
    for i, ch in enumerate(text):
        depth += ch in '[(' and 1 or (-1 if ch in '])' else 0)
        if ch == ':' and depth == 0:
            colon = i
    return (text, 'x32') if colon < 0 else (text[:colon], text[colon + 1:])


def write_watch(path, n):
    with open(path, 'w') as sink:
        for spec in lobbyparty.watches(n):
            name, _, rest = spec.partition('=')
            expression, kind = typed(rest)
            sink.write('%s=%s:%s\n' % (name, numeric(expression), kind))


def write_tick_do(source, path):
    with open(path, 'w') as sink:
        for line in open(source):
            words = line.split(None, 3)
            if len(words) >= 3 and words[1] in ('poke', 'poke32'):
                words[2] = numeric(words[2])
            sink.write(' '.join(words).rstrip('\n') + '\n')


class AppCopy:
    """one copy of the application, worked through its control socket"""

    def __init__(self, role, index, n, out, run, room, args):
        self.role, self.index, self.n, self.args, self.run_dir = role, index, n, args, run
        self.directory = os.path.join(out, role + '-app')
        os.makedirs(self.directory, exist_ok=True)
        self.socket_path = '/tmp/rrv-%d-%s.sock' % (os.getpid(), role)
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        self.out_path = os.path.join(run, role + '.out')
        self.log = open(self.out_path, 'w')
        watch = os.path.join(run, role + '.watch.app.txt')
        write_watch(watch, n)
        tick_do = os.path.join(run, 'tick-do.app.txt')
        write_tick_do(os.path.join(run, 'tick-do.txt'), tick_do)
        relay = args.relay if args.relay in ('force', 'never') else ('force' if args.relay == 'mixed' and index == n - 1 else '')
        # --app-start: the host is not sent to the room at power-on but asks for it through the menu
        # Room (the control socket's "ui room host") from the lobby's log-in screen or from the title
        self.menu = role == 'host' and bool(args.app_start)
        where = []
        if not self.menu:
            where = ['--rta-room', 'host' if role == 'host' else 'join:' + room]
        elif args.app_start in ('lobby', 'lobby-net'):
            # online by itself from power-on, as the packaged application is; no name is given, so it
            # stops at the lobby's log-in screen (nothing is typed there, no account)
            where = ['--rta-online', 'lobby'] + (['--rta-extra-patch', args.signin_patch] if args.signin_patch else [])
        command = [args.app, '--rta-data', self.directory, '--disc', os.environ['RTA_DISC'],
                   '--rta-patch-file', os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach'), '--rta-patch-sections', '@' + args.sections_file,
                   '--rta-test', 'room proof %s %s' % (os.path.basename(out), role), '--rta-control', self.socket_path] + where + [
                   '--rta-room-service', '%s:%d' % (args.service_address, args.port),
                   '--rta-room-name', role.capitalize() + ' app ' + os.path.basename(out)[:10], '--rta-room-log', os.path.join(run, role + '.room.log'),
                   '--rta-tick-log', os.path.join(run, role + '.tick.tsv'), '--rta-tick-watch', watch, '--rta-tick-do', tick_do, '--rta-room-once']
        if not args.external:
            command += ['--rta-room-local']
        if role == 'host' and not args.menu_start:
            command += ['--rta-room-start', str(n)]
        if relay:
            command += ['--rta-room-relay', relay]
        command += args.app_arg
        self.process = subprocess.Popen(['nice', '-n', str(args.nice)] + command, stdout=self.log, stderr=subprocess.STDOUT)
        self.control = None
        self.done = False
        self.launched = False
        self.error = ''
        self.thread = threading.Thread(target=self.drive, daemon=True)
        self.thread.start()

    def say(self, text):
        self.log.write('[driver] %s\n' % text)
        self.log.flush()

    def send(self, line):
        answer = self.control.send(line)
        if not answer.startswith('ok'):
            self.say('%s -> %s' % (line, answer))
        return answer

    def value(self, expression, kind):
        answer = self.control.send('peek %s %s' % (numeric(expression), kind))
        return answer[3:] if answer.startswith('ok') else None

    def test(self, expression, kind, op, want):
        got = self.value(expression, kind)
        if got is None:
            return False
        if kind.startswith('str'):
            return (got == want) if op == '==' else (got != want)
        number = int(got, 16) if kind.startswith('x') else int(got)
        want_number = int(want, 0)
        return {'==': number == want_number, '!=': number != want_number, '>=': number >= want_number, '<=': number <= want_number,
                '>': number > want_number, '<': number < want_number}[op]

    def until(self, condition, seconds, button=None):
        target, op, want = condition.split()
        expression, kind = typed(target)
        end = time.time() + seconds
        while time.time() < end:
            if self.process.poll() is not None:
                raise RuntimeError('the application ended (exit status %s)' % self.process.returncode)
            if self.test(expression, kind, op, want):
                return True
            if button:
                self.send('tap %s 6 %d' % (button, max(1, button_gap)))
            else:
                time.sleep(0.25)
        raise RuntimeError('timed out: %s' % condition)

    def line(self, text):
        """one line of the native program's script language, done through the control socket"""
        words = text.split()
        if not words or words[0].startswith('#'):
            return
        verb = words[0]
        if verb == 'until':
            match = re.match(r'until (.+?) timeout (\d+)', text)
            self.until(match.group(1), int(match.group(2)) / 59.94 * self.args.slow)
        elif verb == 'tapuntil':
            match = re.match(r'tapuntil (\S+) (\d+) (.+?) timeout (\d+)', text)
            global button_gap
            button_gap = int(match.group(2))
            self.until(match.group(3), int(match.group(4)) / 59.94 * self.args.slow, button=match.group(1))
        elif verb == 'stick':
            self.send('stick %s %s %s' % (words[1].lower(), words[2], words[3]))
        elif verb in ('tap', 'press', 'release', 'wait'):
            self.send(text)
        elif verb == 'app' and words[1] == 'net2' and words[2] == 'chat':
            self.send('room chat ' + ' '.join(words[3:]))
        elif verb in ('echo', 'show'):
            self.say(text)
        else:
            self.say('(not done here: %s)' % text)

    def drive(self):
        try:
            end = time.time() + 120
            while not os.path.exists(self.socket_path):
                if time.time() > end or self.process.poll() is not None:
                    raise RuntimeError('no control socket')
                time.sleep(0.5)
            self.control = ctl.Control(self.socket_path, timeout=900)
            args = self.args
            if self.menu:
                self.ask_by_menu()
            self.say('waiting for the character screens')
            self.until('0x%x:u8 == 1' % A_PAGE, 900 * args.slow)
            self.send('room chat hello from the application, %s' % self.role)
            for text in n2party.character_lines():
                self.line(text)
            self.say('character chosen; waiting for the launch')
            if self.role == 'host' and args.menu_start:
                self.start_by_menu()
            self.until('0x402793:u8 == 1', 900 * args.slow)
            self.until('g_levelName:str8 != intro', 300 * args.slow)
            self.until('g_netFrame:s32 >= 200', 300 * args.slow)
            self.launched = True
            self.say('launched: %s' % self.send('room status'))
            seed = {'host': 0, 'j1': 1000, 'j2': 2000, 'j3': 3000}[self.role] + 7
            for text in lobbypair.play_lines(args.play, args.seed + seed):
                self.line(text)
            for k, name in enumerate(level_list(args)):
                self.say('waiting for the level %s' % name)
                self.until('g_levelName:str16 == %s' % name, 600 * args.slow)
                self.until('g_players+0x43d8:u32 != 0', 300 * args.slow)
                self.send('wait 240')
                self.say('in the level %s' % name)
                for text in lobbypair.play_lines(args.play2, args.seed + seed + 500 + 100 * k):
                    self.line(text)
            self.send('wait 120')
            self.say('done: %s' % self.send('room status'))
            if self.role == 'host' and args.rehost:
                self.rehost()
            self.done = True
        except Exception as problem:  # noqa: BLE001 - a test driver says what went wrong and ends
            self.error = str(problem)
            self.say('STOPPED: %s' % problem)
            try:
                if self.control:
                    self.say('status: %s' % self.control.send('room status'))
            except Exception:  # noqa: BLE001
                pass

    def ask_by_menu(self):
        """the menu Room's Host a room, from where --app-start says"""
        args = self.args
        end = time.time() + 300 * args.slow
        if args.app_start in ('lobby', 'lobby-net'):
            # lobby: its log-in screen; lobby-net: its network screen, before the network is up
            mark = 'online: the log-in screen (state 2' if args.app_start == 'lobby' else 'online: the network setting screen (state 0'
            self.say('waiting for the lobby\'s %s' % ('log-in screen' if args.app_start == 'lobby' else 'network screen'))
            while mark not in open(self.out_path, errors='replace').read():
                if time.time() > end or self.process.poll() is not None:
                    raise RuntimeError('"%s" was not reached' % mark)
                time.sleep(0.05 if args.app_start == 'lobby-net' else 0.5)
            if args.app_start == 'lobby':
                time.sleep(args.lobby_wait)
        else:
            self.say('waiting for the title screen (cross through the card questions and logos)')
            global button_gap
            button_gap = 50
            self.until('0x41b510:u8 == 1', 300 * args.slow, button='cross')
            self.until('0x4f6b78:u32 == 0', 60 * args.slow)
            self.until('0x4d8a10:f32 >= 1', 60 * args.slow)
            time.sleep(3)
        self.say('where the game is: front-end state %s, lobby state %s' % (self.value('0x4f6b78', 'u32'), self.value('0x506160', 'u32')))
        self.say('ui room info -> %s' % self.control.send('ui room info'))
        self.say('ui room host -> %s' % self.control.send('ui room host'))
        # the menu as it is drawn while the room is on its way, each change once
        said, end = '', time.time() + 60
        while time.time() < end:
            menu = self.control.send('ui room info')
            if menu != said:
                self.say('ui room info -> %s' % menu)
                said = menu
            if '[Start the game (choose your character first) (greyed)]' in menu and 'Room ' in menu and 'title screen' not in menu:
                break
            time.sleep(0.1)
        self.menu_log_until = time.time() + 120

    def rehost(self):
        """--rehost: in the level of the game just played, Leave the room and Host a room again through
        the menu: the game is started again from the disc and the new room's character screens open"""
        self.say('ui room leave -> %s' % self.control.send('ui room leave'))
        time.sleep(2.0)
        self.say('ui room host -> %s' % self.control.send('ui room host'))
        asked, said, end = time.time(), '', time.time() + 300 * self.args.slow
        while time.time() < end:
            menu = self.control.send('ui room info')
            if menu != said:
                self.say('ui room info -> %s' % menu)
                said = menu
            page = self.value('0x%x' % A_PAGE, 'u8')
            if page == '1' and 'Room ' in menu and 'character screens are up' in open(self.out_path, errors='replace').read().split('ui room host')[-1]:
                self.say('rehost: the new room\'s character screens are up %.0f s after Host a room' % (time.time() - asked))
                self.rehosted = True
                return
            time.sleep(0.5)
        raise RuntimeError('rehost: the character screens of the new room did not come up')

    def start_by_menu(self):
        """the menu Room's Start the game, when it is no longer greyed"""
        end = time.time() + 900 * self.args.slow
        said = ''
        while time.time() < end:
            if self.process.poll() is not None:
                raise RuntimeError('the application ended (exit status %s)' % self.process.returncode)
            menu = self.control.send('ui room info')
            if menu != said:
                self.say('ui room info -> %s' % menu)
                said = menu
            if '[Start the game]' in menu:
                self.say('ui room start -> %s' % self.control.send('ui room start'))
                time.sleep(1.0)
                self.say('ui room info -> %s' % self.control.send('ui room info'))
                return
            time.sleep(1.0)
        raise RuntimeError('Start the game stayed greyed')

    def stop(self):
        try:
            if self.control:
                self.control.send('quit')
        except Exception:  # noqa: BLE001
            pass
        for _ in range(20):
            if self.process.poll() is not None:
                break
            time.sleep(0.5)
        self.quit_kind = 'exit %s' % self.process.returncode if self.process.poll() is not None else 'killed (did not end in 10 s)'
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)


button_gap = 60


def room_code_from(path, process, seconds=300):
    end = time.time() + seconds
    while time.time() < end and process.poll() is None:
        try:
            found = re.search(r'(?:net2|room): ROOM CODE ([A-Z2-9]{5})', open(path, errors='replace').read())
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.3)
    return None


def start_service(out, args):
    data = os.path.join(out, 'service')
    os.makedirs(data, exist_ok=True)
    log = open(os.path.join(out, 'service.log'), 'a')
    command = [sys.executable, '-u', args.service_program, '--data', data, '--port', str(args.port), '--bind', '127.0.0.1', '--status-every', '30']
    if args.service_address != '127.0.0.1':
        command += ['--bind', args.service_address]
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, preexec_fn=lambda: os.nice(10))
    time.sleep(1.0)
    if process.poll() is not None:
        raise SystemExit('the service did not start: see %s' % os.path.join(out, 'service.log'))
    return process


def start_native(role, index, out, run, room, n, args):
    """n2party's native copy; with --native-window the window program (tools/recomp/app, rta_app) off-screen
    instead of the headless one, with the same script and the same runtime options"""
    if not args.native_window:
        return n2party.start_copy(role, index, out, run, room, n, args)
    real = n2party.subprocess.Popen

    def popen(command, **kw):
        # [program, 'boot', '--elf', ELF, '--disc', ISO, '--card', CARD, --sym ..., --script S, --opt ..., --seconds N]
        rest = command[1:]
        disc = rest[rest.index('--disc') + 1]
        card = rest[rest.index('--card') + 1]
        script = rest[rest.index('--script') + 1]
        runtime = [w for i, w in enumerate(rest) if i >= rest.index('--card') + 2 and w != '--script' and w != script]
        window = [args.native_window, '--disc', disc, '--data', os.path.dirname(card), '--offscreen', '--test', 'room proof ' + role, '--script', script, '--'] + runtime
        return real(window, **kw)
    n2party.subprocess.Popen = popen
    try:
        return n2party.start_copy(role, index, out, run, room, n, args)
    finally:
        n2party.subprocess.Popen = real


def level_list(args):
    return [name for name in (args.level or '').split(',') if name]


def with_levels(args):
    """n2party's script for a native or Godot copy, with every level of --level waited for and played in
    (n2party itself knows one level)"""
    names = level_list(args)
    original = n2party.script_lines

    def lines(role, index, n, a):
        out = original(role, index, n, a)
        if not names:
            return out
        tail = len(out) - 1 - out[::-1].index('wait 120')
        seed = args.seed + {'host': 0, 'j1': 1000, 'j2': 2000, 'j3': 3000}[role]
        more = []
        for k, name in enumerate(names):
            more += ['echo waiting-for-level %s' % name, 'until g_levelName:str16 == %s timeout 12000' % name,
                     'until g_players+0x43d8:u32 != 0 timeout 6000', 'wait 240', 'echo in-level %s' % name]
            more += lobbypair.play_lines(args.play2, seed + 500 + 100 * k)
        return out[:tail] + more + out[tail:]
    return lines


def start_godot(role, index, out, run, room, n, args):
    """a copy that is the Godot game scene: n2party's script and runtime options, the game drawn by Godot (scene
    mode) as the portal's --edition choice has it, in a small test window"""
    godot_out = os.path.abspath(os.environ.get('RTA_GODOT_OUT', os.path.join(ROOT, 'local', 'godot-spike')))
    godot = os.environ.get('RTA_GODOT', os.path.join(ROOT, 'local', 'godot-spike', 'deps', 'godot-editor', 'Godot.app', 'Contents', 'MacOS', 'Godot'))
    real = n2party.subprocess.Popen

    def popen(command, **kw):
        rest = command[1:]
        disc = rest[rest.index('--disc') + 1]
        card = rest[rest.index('--card') + 1]
        script = rest[rest.index('--script') + 1]
        runtime = [w for i, w in enumerate(rest) if i >= rest.index('--card') + 2 and w != '--script' and w != script]
        env = dict(kw.pop('env', None) or os.environ)
        for key, name in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
            env[key] = os.path.join(godot_out, 'godot-home', name)
            os.makedirs(env[key], exist_ok=True)
        env['RTA_CWD'] = ROOT
        env['RTA_TEST_OFFSCREEN'] = '1'
        window = [godot, '--path', os.path.join(godot_out, 'project'), '--', '--disc', disc, '--data', os.path.dirname(card),
                  '--mode', 'scene', '--edition', args.edition, '--test', 'room proof ' + role, '--script', script]
        if args.godot_frame_log:
            window += ['--frame-log', os.path.join(run, role + '.frames.csv')]
        return real(window + ['--'] + runtime, env=env, **kw)
    n2party.subprocess.Popen = popen
    try:
        return n2party.start_copy(role, index, out, run, room, n, args)
    finally:
        n2party.subprocess.Popen = real


def native_args(args, n):
    a = argparse.Namespace(**vars(args))
    a.tls = False
    a.players = n
    a.scenario = 'plain'
    a.rounds = 2
    a.idle = False
    a.level_option = None
    a.level = None              # the levels are added by with_levels
    a.opt = args.opt
    a.tick_watch = []
    a.limit = args.limit
    return a


def one_run(out, number, args):
    kinds = args.copies.split(',')
    n = len(kinds)
    roles = ROLES[:n]
    run = os.path.join(out, 'run%d' % number)
    if os.path.isdir(run):
        shutil.rmtree(run)
    os.makedirs(run)
    with open(os.path.join(run, 'tick-do.txt'), 'w') as sink:
        for k, name in enumerate(level_list(args)):
            sink.write('%d poke g_pendingLevel %s\n' % ((args.level_tick or (400 + args.play + 300)) + k * args.level_every, name))
    started = time.time()
    copies, room = {}, None
    nargs = native_args(args, n)
    pids = open(os.path.join(out, 'pids'), 'a')

    def start(role, index):
        if kinds[index] == 'app':
            copy = AppCopy(role, index, n, out, run, room, args)
            pids.write('%d\n' % copy.process.pid)
            return copy
        if kinds[index] == 'godot':
            process = start_godot(role, index, out, run, room or '', n, nargs)
            pids.write('%d\n' % process.pid)
            return process
        process = start_native(role, index, out, run, room or '', n, nargs)
        pids.write('%d\n' % process.pid)
        return process

    try:
        copies['host'] = start('host', 0)
        pids.flush()
        host_process = copies['host'].process if kinds[0] == 'app' else copies['host']
        room = room_code_from(os.path.join(run, 'host.room.log' if kinds[0] == 'app' else 'host.out'), host_process)
        if not room:
            raise RuntimeError('the host did not open a room')
        print('room %s' % room)
        for index, role in enumerate(roles[1:], 1):
            copies[role] = start(role, index)
            pids.flush()
            time.sleep(args.stagger)
        deadline = time.time() + args.limit + 120
        while time.time() < deadline:
            busy = False
            for role, kind in zip(roles, kinds):
                if kind == 'app':
                    busy = busy or (copies[role].thread.is_alive())
                else:
                    busy = busy or copies[role].poll() is None
            if not busy:
                break
            time.sleep(1.0)
    except RuntimeError as problem:
        print('run %d: %s' % (number, problem))
    finally:
        for role, kind in zip(roles, kinds):
            if role not in copies:
                continue
            if kind == 'app':
                copies[role].stop()
            elif copies[role].poll() is None:
                copies[role].kill()
                copies[role].wait()
        pids.close()
    # what happened
    launched, done = {}, {}
    for role, kind in zip(roles, kinds):
        text = open(os.path.join(run, role + '.out'), errors='replace').read() if os.path.exists(os.path.join(run, role + '.out')) else ''
        if kind == 'app':
            launched[role] = role in copies and copies[role].launched
            done[role] = role in copies and copies[role].done
            for line in text.splitlines():
                if '[driver]' in line or 'room:' in line and ('WARNING' in line or 'launch' in line or 'started' in line or 'refused' in line):
                    print('  %s: %s' % (role, line[:400]))
        else:
            launched[role] = '] launched' in text
            done[role] = '] done' in text
            for line in text.splitlines():
                if 'net2: launch' in line or 'net2: the room started' in line or 'WARNING' in line or 'TIMEOUT' in line or 'carrier:' in line:
                    print('  %s: %s' % (role, lobbyparty.brief(line.rstrip())[:400]))
    # how each application copy ended at "quit" (docs/issues/app-rendezvous.md, the quit after a room)
    quits = []
    for role, kind in zip(roles, kinds):
        if kind == 'app' and role in copies:
            text = open(os.path.join(run, role + '.out'), errors='replace').read()
            crashed = 'recursive_mutex' in text or 'terminating due to' in text
            quits.append('%s=%s%s' % (role, getattr(copies[role], 'quit_kind', '?'), ' CRASH' if crashed else ''))
    games = {r: lobbyparty.split_games(os.path.join(run, r + '.tick.tsv')) for r in roles}
    ticks, same = [], True
    for i in range(n):
        for j in range(i + 1, n):
            a, b = games[roles[i]], games[roles[j]]
            if not a or not b:
                ticks.append('%s/%s none' % (roles[i], roles[j]))
                same = False
                continue
            result = subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'compare.py'), 'ticks', a[0], b[0]], capture_output=True, text=True).stdout
            found = re.search(r'compared (\d+)', result)
            equal = 'no shared column differs' in result
            same = same and equal
            ticks.append('%s(%s)/%s(%s) %s%s' % (roles[i], kinds[i], roles[j], kinds[j], found.group(1) if found else '?', '' if equal else ' DIFFER'))
            if not equal:
                print('--- %s against %s\n%s' % (roles[i], roles[j], result[:1500]))
    line = '%s run %d (%s; relay %s; service %s%s) room %s load %.0f %.0f s | launched %s | done %s | ticks in step: %s | quit: %s | %s' % (
        time.strftime('%H:%M:%S'), number, args.copies, args.relay or 'auto', 'external' if args.external else args.service_address,
        ('; host from the %s by the menu' % args.app_start if args.app_start else '') + ('; Start the game by the menu' if args.menu_start else ''), room, os.getloadavg()[0], time.time() - started,
        ' '.join('%s=%s' % (r, 'yes' if launched[r] else 'NO') for r in roles), ' '.join('%s=%s' % (r, 'yes' if done[r] else 'no') for r in roles),
        '; '.join(ticks) or 'none', ' '.join(quits) or '-', lobbyparty.story(os.path.join(run, 'host.tick.tsv'), n))
    print(line)
    with open(os.path.join(out, 'results.txt'), 'a') as sink:
        sink.write(line + '\n')
    return all(launched.values()) and same and bool(ticks) and not any('CRASH' in q or 'killed' in q for q in quits)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out')
    parser.add_argument('--copies', default='app,native')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--relay', choices=('', 'force', 'never', 'mixed'), default='')
    parser.add_argument('--service-address', default='127.0.0.1')
    parser.add_argument('--external', action='store_true', help='use a service already running at --service-address:--port')
    parser.add_argument('--port', type=int, default=41987)
    parser.add_argument('--service-program', default=os.path.join(ROOT, 'tools', 'rendezvous', 'rendezvous.py'), help='the service started for the run')
    parser.add_argument('--app', default=DEFAULT_APP)
    parser.add_argument('--app-arg', action='append', default=[])
    parser.add_argument('--program', help='the native program (default: n2party.py\'s)')
    parser.add_argument('--native-window', help='the native window program (rta_app) for the native copies, off-screen, instead of the headless one')
    parser.add_argument('--app-start', choices=('', 'lobby', 'lobby-net', 'title'), default='', help='an application host asks for its room through the menu Room ("ui room host") from the lobby\'s log-in screen (online by itself from power-on, no name given) or from the title screen, not at power-on')
    parser.add_argument('--signin-patch', help='with --app-start lobby: the sign-in patch the lobby needs (never in the repository)')
    parser.add_argument('--lobby-wait', type=float, default=5.0, help='seconds at the lobby\'s log-in screen before the room is asked for')
    parser.add_argument('--rehost', action='store_true', help='after the game, the application host leaves the room in the level and hosts a new one through the menu (the way back to the title from a level)')
    parser.add_argument('--menu-start', action='store_true', help='the application host starts the game through the menu Room ("ui room start") when that entry is no longer greyed')
    parser.add_argument('--sections', default=os.path.join(HERE, 'sections-suggested.txt'), help='the application\'s patch sections')
    parser.add_argument('--drop-section', action='append', default=[], help='a section of --sections the native translation does not carry')
    parser.add_argument('--play', type=int, default=1800)
    parser.add_argument('--level')
    parser.add_argument('--level-tick', type=int)
    parser.add_argument('--level-every', type=int, default=2400, help='with --level A,B,...: lockstep ticks from one level change to the next')
    parser.add_argument('--edition', default='classic', help='the godot copies: classic or remastered (portal/edition.gd)')
    parser.add_argument('--godot-frame-log', action='store_true', help='the godot copies write their frame log (main.gd --frame-log) beside the tick logs')
    parser.add_argument('--play2', type=int, default=1800)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--pace', type=float, default=59.94)
    parser.add_argument('--stagger', type=float, default=2.0)
    parser.add_argument('--limit', type=int, default=1500)
    parser.add_argument('--slow', type=float, default=3.0, help='time-outs of the scripts are stretched by this (a loaded computer)')
    parser.add_argument('--nice', type=int, default=10)
    parser.add_argument('--opt', action='append', default=[], help='--opt KEY=VALUE for the native copies')
    args = parser.parse_args()
    n2party.script_lines = with_levels(args)
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('name the disc image with RTA_DISC')
    kinds = args.copies.split(',')
    if not 2 <= len(kinds) <= 4 or any(k not in ('app', 'native', 'godot') for k in kinds):
        raise SystemExit('--copies: two to four of app, native and godot')
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    sections = [line.rstrip('\n') for line in open(args.sections) if line.strip() and not line.startswith('#')]
    for name in args.drop_section:
        if name not in sections:
            raise SystemExit('not a section of %s: %s' % (args.sections, name))
        sections.remove(name)
    args.sections_file = os.path.join(out, 'sections.txt')
    with open(args.sections_file, 'w') as sink:
        sink.write('\n'.join(sections) + '\n')
    service = None if args.external else start_service(out, args)
    if service:
        with open(os.path.join(out, 'pids'), 'a') as pids:
            pids.write('%d\n' % service.pid)
    good = True
    try:
        for number in range(1, args.runs + 1):
            good = one_run(out, number, args) and good
    finally:
        if service:
            service.send_signal(2)
            try:
                service.wait(5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
