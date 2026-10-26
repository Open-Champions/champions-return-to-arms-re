#!/usr/bin/env python3
"""lobbyparty.py - two to four native copies through a lobby server on this computer into one
game, several launches in a row, and what happens to the game afterwards.

  export RTA_DISC="/path/to/your/disc image.iso"
  python3 -B tools/recomp/net/lobbyparty.py OUT --players 3 [--kinds window,native,native]
          [--launches K] [--play FRAMES] [--level NAME --play2 FRAMES] [--tick-do "LINE"]
          [--scenario plain|drop|hostquit|leave|late] [--server ADDRESS] [--port-shift N]

A companion of lobbypair.py (two copies, also the emulator application) for games of three
and four and for the things a game of two does not show.  The copies are `native` (the
headless program) or `window` (the window program in a small silent test window titled
"AGENT TEST - native online"); the first one hosts by a made-up code, the others join by
it, all through the one-step online (online.cpp).  Every copy is given the server
explicitly - this computer's own address - and net-local-only=1; the script reads each
copy's first line and stops unless it names this computer.  --port-shift N is for a second
server instance whose ports are the usual ones plus N (netdrv.h).

Scenarios (what the copies do once the game runs; FRAMES are vertical blanks):
  plain     drawn input for --play frames; with --level the pending level name is written in
            one lockstep tick on every copy and --play2 more frames are played there
  drop      after --play frames the LAST joiner's process is killed; the others play on for
            --play2 frames and say what they see (player count, the dropped flags)
  hostquit  the same with the HOST's process killed
  leave     after --play frames every copy leaves by the pause menu (see leave_lines), is
            back at the lobby's game list, and the same processes host and join again:
            --rounds times, with socket, thread and memory counts of each process per round
  late      one joiner fewer goes in; the last copy waits at the lobby's game list and asks for the
            game by its code when it has started (the original does not let anybody into a game
            in progress: a started game is in no list)

Programs: $RTA_NATIVE_ONLINE (default local/recomp-out/bin/rta_native_online) and
$RTA_NATIVE_APP (default local/recomp-out/bin/rta_app).  Names are made up per OUT and kept
(OUT/<role>/name); the password is the one-step driver's and never leaves its file.
Each launch's logs go to OUT/run<k>/; one result line per launch is added to OUT/results.txt.
Exit code 0: every launch had every copy in the level and no tick column differing.
"""
import argparse
import glob
import os
import random
import re
import shutil
import string
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
sys.path.insert(0, HERE)
import lobbypair  # noqa: E402  (new_character_lines, play_lines)

A_LOBBY = '0x506160'
ROLES = ['host', 'j1', 'j2', 'j3']


def own_address():
    return subprocess.run(['ipconfig', 'getifaddr', 'en0'], capture_output=True, text=True).stdout.strip()


def known(k, offset=0):
    """the lobby client's table of other players: record k (ident -1: nobody; +0x42 0xff: no character yet)"""
    return '[0x50613c]+0x%x' % (0x740 + 0xa8 * k + offset)


def watches(n):
    record = lambda i: 'g_players+%d' % (i * 0x4C30)
    peer = lambda i: 'g_peers+%d' % (i * 0x44E0)
    # the twelve button tables: one column for four players; in a game of five to eight each table is moved on its
    # own with room for eight (tools/recomp/app/party8-ranges.txt): a column per table
    buttons = ['btnmaps=0x41b980:crc192'] if n <= 4 else ['btn%d=0x%x:crc%d' % (k, 0x41b980 + 0x10 * k, 4 * n) for k in range(12)]
    specs = ['net=g_netFrame:s32', 'seed=g_randSeed:x32', 'level=g_levelName:str12', 'nplayers=g_numPlayers:s32'] + buttons + [
             # this machine's own sync hash of the previous tick (its player number is the byte at 0x402a39)
             'prevhash=g_peers+([0x402a39]&255)*0x44e0+0x18ac+((g_netFrame-1)&0xff)*12+8:x32',
             'l_inp=g_localInputFrame:s32', 'l_drawframe=g_drawFrame:u32', 'l_lobby=%s:u32' % A_LOBBY]
    for i in range(n):
        obj = '[%s+0x43d8]' % record(i)
        specs += ['p%dx=%s+0x10:x32' % (i, obj), 'p%dy=%s+0x14:x32' % (i, obj), 'p%dz=%s+0x18:x32' % (i, obj),
                  'p%dstate=%s+0x58c:s32' % (i, obj), 'p%dhp=%s+0xac:x32' % (i, record(i)),
                  'p%dgold=%s+0xe4:s32' % (i, record(i)), 'p%dexp=%s+0x5c:s32' % (i, record(i)),
                  'oos%d=%s+0x44d7:u8' % (i, peer(i)), 'l_dropped%d=%s+0x44d5:u8' % (i, peer(i))]
    return specs


STATUS = ('show g_netFrame:s32 g_numPlayers:s32 g_levelName:str12 g_checksumFailed:u8 %s:u32 g_inFrontend:u8 ' % A_LOBBY
          + ' '.join('%s+0x44d5:u8 %s+0x44d7:u8' % (('g_peers+%d' % (i * 0x44E0),) * 2) for i in range(4)))


def brief(line):
    """a `show` line without the addresses: name=value ..."""
    return re.sub(r'@[0-9a-f]{8}', '', line)


def to_room_lines(role, new_character, n, args, first=True):
    """from the game list (the one-step driver is on its way) into the room; the host presses Start"""
    lines = ['until %s:u32 == 5 timeout 15000' % A_LOBBY] if first else []
    if new_character:
        lines += lobbypair.new_character_lines()
    lines += ['until %s:u32 == 6 timeout 15000' % A_LOBBY, 'echo in-the-room']
    if role == 'host':
        for k in range(n - 1):
            lines += ['until %s:s8 != -1 timeout 40000' % known(k), 'echo joined-%d' % (k + 1),
                      'until %s:u8 != 255 timeout 20000' % known(k, 0x42), 'echo character-%d' % (k + 1)]
        lines += ['wait %d' % args.room_wait, 'echo pressing-start', 'tapuntil cross 120 %s:u32 == 12 timeout 3000' % A_LOBBY]
    else:
        for k in range(n - 1):
            lines += ['until %s:s8 != -1 timeout 60000' % known(k), 'until %s:u8 != 255 timeout 30000' % known(k, 0x42)]
        lines += ['echo all-known']
        if role in args.stall:
            # this joiner stands still across the host's Start (the host presses it --room-wait frames after it
            # has seen everybody): it takes START late, when the others have disconnected already
            lines += ['wait %d' % max(1, args.room_wait - 120), 'app net stall %d' % args.stall_ms]
    # the launch tables (docs/issues/three-players.md): players, own number, the address and port tables,
    # and each player's launch record (address, port, state, flags) at the start and three times after
    table = ' '.join(['0x402a37:u8', '0x402a39:u8'] + ['0x%x:x32' % (0x402b3b + 4 * i) for i in range(4)] + ['0x%x:u32' % (0x402b5c + 4 * i) for i in range(4)])
    records = 'show ' + ' '.join('0x%x:x32 0x%x:u32 0x%x:u8 0x%x:u8 0x%x:u8' % (0x402ba4 + 0x144 * i, 0x402bc8 + 0x144 * i, 0x402bec + 0x144 * i,
                                                                             0x402bed + 0x144 * i, 0x402bf4 + 0x144 * i) for i in range(4))
    lines += ['until %s:u32 == 12 timeout 40000' % A_LOBBY, 'echo launch-tables', 'show ' + table, records, 'wait 30', records, 'wait 120', records,
              'wait 300', records, 'until g_levelName:str8 == hub timeout 3600', 'echo in-hub',
              'until g_netFrame:s32 >= 200 timeout 6000', 'echo launched', STATUS]
    return lines


def leave_lines(role):
    """The original way out of a running game: Start opens the pause menu (Return to Game, Use Gate
    Scroll, Load Game - grey, skipped -, Options..., for the host Kick Player, Exit Game), Exit Game asks
    "Exit Game? Yes / No" with No under the cursor, and the machine is back at the lobby's game list."""
    downs = 4 if role == 'host' else 3
    return (['echo leaving', 'tap start 10 60'] + ['tap down 10 30'] * downs + ['tap cross 10 60', 'tap left 10 30', 'tap cross 10 30',
            'until %s:u32 == 5 timeout 3600' % A_LOBBY, 'echo back-at-the-game-list', STATUS, 'app net sockets'])


def script_lines(role, index, new_character, n, args):
    seeds = {'host': 0, 'j1': 1000, 'j2': 2000, 'j3': 3000}
    in_game = n - 1 if args.scenario == 'late' else n
    last = ROLES[n - 1]
    lines = ['# written by lobbyparty.py: %s, scenario %s' % (role, args.scenario)]
    if args.scenario == 'late' and role == last:
        # at the lobby's game list while the others start their game; then it asks for the game by its
        # code: the one-step driver looks for the code in the lobby's list for two minutes and says so
        lines += ['until %s:u32 == 5 timeout 15000' % A_LOBBY, 'echo at-the-list', 'wait %d' % args.late_wait,
                  'show %s:u32 [[0x506144]+0x314]+0x60:u16' % A_LOBBY, 'echo asking-for-the-game', 'app online start join:%CODE6%',
                  'wait 7800', 'show %s:u32 [[0x506144]+0x314]+0x60:u16' % A_LOBBY, 'app online', 'echo done', 'quit']
        return lines
    lines += to_room_lines(role, new_character, in_game, args)
    play = (lambda frames, salt: ['wait %d' % frames]) if args.idle else (lambda frames, salt: lobbypair.play_lines(frames, args.seed + seeds[role] + salt))
    lines += play(args.play, 0)
    if args.scenario == 'plain':
        if args.level:
            lines += ['echo waiting-for-level', 'until g_levelName:str8 == %s timeout 12000' % args.level,
                      'until g_players+0x43d8:u32 != 0 timeout 6000', 'wait 240', 'echo in-level'] + play(args.play2, 500)
    elif args.scenario in ('drop', 'hostquit'):
        victim = last if args.scenario == 'drop' else 'host'
        if role == victim:
            lines += ['echo ready-to-be-killed', 'wait 100000']
        else:
            lines += ['echo other-about-to-go', STATUS]
            for k in range(8):
                lines += play(args.play2 // 8, 100 + k) + [STATUS, 'app shot %RUN%/' + role + '-after-%d.png' % k]
            lines += ['echo survivor-done']
    elif args.scenario == 'leave':
        # the last joiner leaves by the pause menu, 600 frames later the one before it, ...; the host is
        # put back to the game list by the game when it is alone.  Then the same processes host and
        # join again, by a new code.
        for r in range(args.rounds):
            if role == 'host':
                lines += ['echo waiting-to-be-alone', 'until %s:u32 == 5 timeout %d' % (A_LOBBY, 900 * n + 3600), 'echo back-at-the-game-list', STATUS, 'app net sockets']
            else:
                lines += ['wait %d' % (600 * (n - 1 - index))] + leave_lines(role)
            if r + 1 < args.rounds:
                lines += ['wait %d' % (600 * index + (300 if role == 'host' else 900)), 'app online start %s:%s%d' % ('host' if role == 'host' else 'join', '%CODE%', r + 1)]
                lines += to_room_lines(role, False, n, args, first=False) + play(args.play, 10 * (r + 1))
    lines += ['wait 120', STATUS, 'app online', 'app net peers', 'app net sockets', 'echo done', 'quit']
    return lines


def make_name(directory):
    path = os.path.join(directory, 'name')
    if os.path.exists(path):
        return open(path).read().strip()
    name = 'Np' + ''.join(random.choice(string.ascii_lowercase) for _ in range(5)) + str(random.randrange(10, 99))
    with open(path, 'w') as sink:
        sink.write(name + '\n')
    return name


def start(role, index, kind, out, run, code, n, args):
    directory = os.path.join(out, role)
    os.makedirs(directory, exist_ok=True)
    name = make_name(directory)
    new_character = not os.path.exists(os.path.join(directory, 'online-character'))
    watch_file = os.path.join(run, role + '.watch.txt')
    with open(watch_file, 'w') as sink:
        sink.write('\n'.join(watches(n) + args.tick_watch) + '\n')
    script = os.path.join(run, role + '.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(script_lines(role, index, new_character, n, args)).replace('%CODE6%', code).replace('%CODE%', code[:5]).replace('%RUN%', run) + '\n')
    symbols = []
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        symbols += ['--sym', path]
    if kind == 'window':
        program = os.environ.get('RTA_NATIVE_APP', os.path.join(OUT, 'bin', 'rta_app'))
        command = [program, '--test', 'native online', '--window', '320x240', '--disc', os.environ['RTA_DISC'], '--data', directory,
                   '--script', script, '--control', os.path.join(run, role + '.sock'), '--']
    else:
        program = os.environ.get('RTA_NATIVE_ONLINE', os.path.join(OUT, 'bin', 'rta_native_online'))
        command = [program, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--disc', os.environ['RTA_DISC'],
                   '--card', os.path.join(directory, 'card')] + symbols + ['--script', script]
    late = args.scenario == 'late' and role == ROLES[n - 1]
    options = {'net-server': args.server, 'net-data': directory, 'net-local-only': '1',
               'online': 'lobby' if late else '%s:%s' % ('host' if role == 'host' else 'join', code), 'online-name': name, 'online-person': '0',
               'net-log': os.path.join(run, role + '.net.log'), 'tick-log': os.path.join(run, role + '.tick.tsv'),
               'tick-watch-file': watch_file, 'tick-do': os.path.join(run, 'tick-do.txt'), 'net-pace': str(args.pace)}
    if args.port_shift:
        options['net-port-shift'] = str(args.port_shift)
    if args.log_all:
        options['net-log-all'] = '1'
    for item in args.opt:
        key, _, value = item.partition('=')
        options[key] = value
    for key, value in options.items():
        command += ['--opt', '%s=%s' % (key, value)]
    command += ['--seconds', str(args.limit)]
    log = open(os.path.join(run, role + '.out'), 'w')
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, preexec_fn=lambda: os.nice(10))
    process.late = late
    return process


def server_line(path):
    try:
        for line in open(path, errors='replace'):
            if 'server ' in line and 'own-network address' in line:
                return line.strip()
    except OSError:
        pass
    return None


def said(path, word):
    try:
        return any(('] ' + word) in line for line in open(path, errors='replace'))
    except OSError:
        return False


def resources(pid):
    """open files, of them sockets, threads, resident kilobytes of one process (this user's own)"""
    try:
        listing = subprocess.run(['lsof', '-nP', '-p', str(pid)], capture_output=True, text=True).stdout.splitlines()[1:]
        sockets = sum(1 for line in listing if ' IPv4 ' in line or ' IPv6 ' in line or ' unix ' in line)
        threads = len(subprocess.run(['ps', '-M', '-p', str(pid)], capture_output=True, text=True).stdout.splitlines()) - 1
        rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
        return '%d files, %d sockets, %d threads, %s kB' % (len(listing), sockets, threads, rss or '?')
    except OSError:
        return '?'


def sampler(processes, run, stop):
    with open(os.path.join(run, 'resources.txt'), 'w') as sink:
        while not stop.wait(args_sample_period):
            for role, process in processes.items():
                if process.poll() is None:
                    sink.write('%s %s: %s\n' % (time.strftime('%H:%M:%S'), role, resources(process.pid)))
            sink.flush()


args_sample_period = 20.0


def split_games(path):
    """the tick log as one file per game played (the tick number starts again): the files' paths"""
    try:
        source = open(path)
    except OSError:
        return []
    head = source.readline()
    games, last = [], None
    for line in source:
        fields = line.split('\t')
        if len(fields) < 3 or not fields[1].lstrip('-').isdigit():
            continue
        tick = int(fields[1])
        if last is None or tick < last:
            games.append([])
        games[-1].append(line)
        last = tick
    if len(games) <= 1:
        return [path] if games else []
    paths = []
    for k, rows in enumerate(games):
        paths.append('%s.game%d.tsv' % (path[:-4], k + 1))
        with open(paths[-1], 'w') as sink:
            sink.write(head + ''.join(rows))
    return paths


def story(path, n):
    """what a tick log tells: levels, deaths (hit points reaching 0), and the reload after everybody died"""
    import struct
    try:
        source = open(path)
    except OSError:
        return ''
    head = source.readline().rstrip('\n').split('\t')
    levels, deaths, reloads, dead, all_dead = [], 0, 0, [False] * n, False
    for line in source:
        fields = line.rstrip('\n').split('\t')
        if len(fields) != len(head):
            continue
        row = dict(zip(head, fields))
        if not levels or levels[-1] != row['level']:
            levels.append(row['level'])
        try:
            now = [struct.unpack('<f', struct.pack('<I', int(row['p%dhp' % i], 16)))[0] <= 0 for i in range(n)]
        except (KeyError, ValueError):
            continue
        deaths += sum(1 for i in range(n) if now[i] and not dead[i])
        if all_dead and not any(now):
            reloads += 1
        all_dead = all(now) if any(now) else False if not all_dead else all_dead and all(now)
        dead = now
    return 'levels %s, %d deaths, %d reloads after everybody died' % ('>'.join(levels), deaths, reloads)


def one_launch(out, number, kinds, args):
    n = args.players
    roles = ROLES[:n]
    run = os.path.join(out, 'run%d' % number)
    if os.path.isdir(run):
        shutil.rmtree(run)
    os.makedirs(run)
    code = 'T' + ''.join(random.choice(string.ascii_uppercase) for _ in range(5))
    with open(os.path.join(run, 'tick-do.txt'), 'w') as sink:
        if args.level and args.scenario == 'plain':
            sink.write('%d poke g_pendingLevel %s\n' % (args.level_tick or (400 + args.play + 300), args.level))
        for item in args.tick_do:
            sink.write(item + '\n')
    mine = own_address()
    started = time.time()
    processes = {}
    codes = {}
    stop = threading.Event()
    pids = open(os.path.join(out, 'pids'), 'w')
    try:
        for index, role in enumerate(roles):
            processes[role] = start(role, index, kinds[index], out, run, code, n, args)
            pids.write('%d\n' % processes[role].pid)
            pids.flush()
            line = None
            for _ in range(300):
                line = server_line(os.path.join(run, role + '.out'))
                if line or processes[role].poll() is not None:
                    break
                time.sleep(0.1)
            if not line or ('this computer' not in line and mine not in line) or 'nothing is sent beyond this computer' not in line:
                raise SystemExit('%s does not name this computer as its server: %r - stopping' % (role, line))
            time.sleep(args.stagger)
        threading.Thread(target=sampler, args=(processes, run, stop), daemon=True).start()
        victim = {'drop': roles[-1], 'hostquit': 'host'}.get(args.scenario)
        deadline = time.time() + args.limit + 60
        while time.time() < deadline and any(p.poll() is None for p in processes.values()):
            if victim and processes[victim].poll() is None and said(os.path.join(run, victim + '.out'), 'ready-to-be-killed') \
                    and all(said(os.path.join(run, r + '.out'), 'other-about-to-go') for r in roles if r != victim):
                time.sleep(2.0)
                processes[victim].kill()
                print('killed %s (pid %d) at %.0f s' % (victim, processes[victim].pid, time.time() - started))
            time.sleep(0.5)
        for role, process in processes.items():
            codes[role] = process.poll() if process.poll() is not None else -9
    finally:
        stop.set()
        for process in processes.values():
            if process.poll() is None:
                process.kill()
        pids.close()
    texts = {r: open(os.path.join(run, r + '.out'), errors='replace').read() for r in roles}
    in_game = [r for r in roles if not getattr(processes.get(r), 'late', False)]
    launched = {r: '] launched' in texts[r] for r in in_game}
    done = {r: '] done' in texts[r] or '] survivor-done' in texts[r] for r in roles}
    keep = ('[frame', '[tick', '[net] WARNING', 'online: stage', 'online: ', 'net: ', 'TIMED OUT', 'timed out', 'stopped', 'run ended', 'NOT ANSWERED')
    for role in roles:
        # the whole story of a copy that did not get through; of the others the lines that matter
        whole = args.verbose or not done[role] or not launched.get(role, True)
        if not launched.get(role, True):
            for line in texts[role].splitlines():
                if '] 0x402a37' in line or '] 0x402ba4' in line or '[game] Terminating' in line or '[game] Got START' in line or '[game] Lost' in line:
                    print('  %s: %s' % (role, brief(line.rstrip())[:400]))
        for line in texts[role].splitlines():
            if (whole and (any(k in line for k in keep) or 'NOT SENT' in line)) or 'out of sync' in line.lower() or '[net] WARNING' in line \
                    or 'NOT ANSWERED' in line or 'library sockets' in line or '] g_netFrame' in line or 'TIMED OUT' in line or 'timed out' in line:
                print('  %s: %s' % (role, brief(line.rstrip())[:330]))
    # a copy that played several games in one run (scenario leave) has them one after another in its
    # tick log, each counting its ticks from 1: they are compared game by game
    games = {r: split_games(os.path.join(run, r + '.tick.tsv')) for r in in_game}
    ticks = []
    same = True
    for k in range(max([len(g) for g in games.values()] or [0])):
        for i in range(len(in_game)):
            for j in range(i + 1, len(in_game)):
                if k >= len(games[in_game[i]]) or k >= len(games[in_game[j]]):
                    continue
                result = subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'compare.py'), 'ticks', games[in_game[i]][k], games[in_game[j]][k]],
                                        capture_output=True, text=True).stdout
                found = re.search(r'compared (\d+)', result)
                equal = 'no shared column differs' in result
                same = same and equal
                ticks.append('%s%s/%s %s%s' % ('game %d ' % (k + 1) if k or len(games[in_game[i]]) > 1 else '', in_game[i], in_game[j], found.group(1) if found else '?', '' if equal else ' DIFFER'))
                if not equal:
                    print('--- %s against %s\n%s' % (in_game[i], in_game[j], result[:1500]))
    line = '%s launch %d (%s; %s) code %s load %.0f %.0f s | launched %s | script done %s | ticks in step: %s | %s' % (
        time.strftime('%H:%M:%S'), number, ','.join(kinds[:n]), args.scenario, code, os.getloadavg()[0], time.time() - started,
        ' '.join('%s=%s' % (r, 'yes' if launched[r] else 'NO') for r in in_game),
        ' '.join('%s=%s' % (r, 'yes' if done[r] else 'no(exit %s)' % codes.get(r)) for r in roles), '; '.join(ticks) or 'none',
        story(os.path.join(run, 'host.tick.tsv'), len(in_game)))
    print(line)
    with open(os.path.join(out, 'results.txt'), 'a') as sink:
        sink.write(line + '\n')
    return all(launched.values()) and same


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out')
    parser.add_argument('--players', type=int, default=3)
    parser.add_argument('--kinds', default='', help='native or window per copy, host first (default: all native)')
    parser.add_argument('--launches', type=int, default=1)
    parser.add_argument('--scenario', choices=('plain', 'drop', 'hostquit', 'leave', 'late'), default='plain')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--stall', default='', help='joiners (j1,j2,...) that stand still across the host\'s Start')
    parser.add_argument('--stall-ms', type=int, default=5000)
    parser.add_argument('--late-wait', type=int, default=5800, help='late: frames the last copy waits at the game list before it asks for the game')
    parser.add_argument('--server', default=None)
    parser.add_argument('--port-shift', type=int, default=0)
    parser.add_argument('--play', type=int, default=1800)
    parser.add_argument('--level')
    parser.add_argument('--level-tick', type=int)
    parser.add_argument('--play2', type=int, default=1800)
    parser.add_argument('--idle', action='store_true')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--pace', type=float, default=59.94)
    parser.add_argument('--room-wait', type=int, default=240)
    parser.add_argument('--stagger', type=float, default=1.0)
    parser.add_argument('--limit', type=int, default=600)
    parser.add_argument('--log-all', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--opt', action='append', default=[])
    parser.add_argument('--tick-watch', action='append', default=[])
    parser.add_argument('--tick-do', action='append', default=[])
    args = parser.parse_args()
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('name the disc image with RTA_DISC')
    mine = own_address()
    if not args.server:
        args.server = mine
    if args.server != mine and args.server not in ('127.0.0.1', 'localhost'):
        raise SystemExit('the server must be this computer (%s), not %s' % (mine, args.server))
    args.stall = [r for r in args.stall.split(',') if r]
    kinds = [k for k in args.kinds.split(',') if k] or []
    kinds += ['native'] * (4 - len(kinds))
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    good = True
    for number in range(1, args.launches + 1):
        good = one_launch(out, number, kinds, args) and good
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
