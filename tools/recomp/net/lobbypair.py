#!/usr/bin/env python3
"""lobbypair.py - two copies of the game through the lobby into one game, and a comparison.

  export RTA_DISC="/path/to/your/disc image.iso"
  python3 tools/recomp/net/lobbypair.py run OUT [--host native|app] [--join native|app]
          [--play FRAMES] [--level NAME --play2 FRAMES] [--seed N] [--pace HZ] [--limit SECONDS]

One copy hosts a game named with a code, the other joins it by that code; both go there
by themselves (the one-step online: tools/recomp/net/online.cpp, or the emulator-based
application's own).  `native` is local/recomp-out/bin/rta_native_online; `window` is the
native window program local/recomp-out/bin/rta_app in a small silent test window titled
"AGENT TEST - native online"; `app` is the emulator-based application (tools/play-net/play.sh, a silent background test window,
driven over its control socket).  The lobby server is the one on this computer, and a
native copy is started with net-local-only=1: it sends nothing beyond this computer.

What the script of each copy does after the one-step driver has brought it to the game's
character screens: a new character the first time (class shown first, default looks, the
20 points into the first row, a three-letter name), the character used last after that
(the driver takes it by itself); in the room the host waits for the other player's
character and presses Start; then FRAMES vertical blanks of drawn input (walking out and
back, fight and potion buttons - no "use", so nobody starts a conversation); with --level
the pending level name is written in one lockstep tick on both copies (native copies:
`tick-do`), and --play2 more frames are played there.

Player names are made up per run directory and kept there (OUT/host/name, OUT/join/name);
passwords are made by the one-step driver and never leave its file.  Native copies write
the rig's tick log; `run` ends with `tools/rig/compare.py ticks` over the two.  Exit code
0: both copies ended by their script.
"""
import argparse
import glob
import os
import random
import shutil
import string
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'rig'))

A_LOBBY = '0x506160'        # the lobby state: 5 game list, 6 a game's room, 12 in game
A_PAGE = '0x8e2c02'         # the character screens' page: 1 class, 2 looks, 3 points, 4 name
A_KNOWN = '[0x50613c]+0x740'        # the lobby client's table of other players: ident of the first (-1: nobody)
A_KNOWN_CHOSEN = '[0x50613c]+0x782'  # +0x42 of that record: 0xff until the other player has a character


def new_character_lines():
    lines = ['until %s:u8 == 1 timeout 9000' % A_PAGE, 'wait 90',
             'tapuntil cross 60 %s:u8 == 2 timeout 1800' % A_PAGE, 'wait 90',
             'tapuntil cross 60 %s:u8 == 3 timeout 1800' % A_PAGE, 'wait 90']
    lines += ['tap right 8 8'] * 20
    lines += ['wait 30', 'tapuntil cross 60 %s:u8 == 4 timeout 1800' % A_PAGE, 'wait 90']
    lines += ['tap cross 8 12'] * 3 + ['tap down 8 12'] * 6 + ['tap right 8 12'] * 5 + ['tap cross 8', 'wait 60']
    return lines


def play_lines(frames, seed):
    """Drawn input for `frames` vertical blanks: legs out and back, fight and potion buttons."""
    rng = random.Random(seed)
    events = []                                    # (frame, order, line)
    at = 0
    directions = ['0 128', '255 128', '128 0', '128 255', '0 0', '255 255', '0 255', '255 0']
    opposite = {0: 1, 1: 0, 2: 3, 3: 2, 4: 5, 5: 4, 6: 7, 7: 6}
    while at < frames:
        d, leg = rng.randrange(8), rng.randrange(20, 70)
        for way in (d, opposite[d]):
            events.append((at, 0, 'stick L %s' % directions[way]))
            at += leg
        events.append((at, 0, 'stick L 128 128'))
        at += rng.randrange(5, 40)
    table = [('cross', 60, 2, 8), ('circle', 10, 2, 20), ('triangle', 10, 2, 20), ('r1', 10, 10, 40), ('l1', 4, 2, 4),
             ('r2', 8, 2, 4), ('l2', 8, 2, 4)]
    for button, rate, hold_min, hold_span in table:
        frame = 0
        while frame < frames:
            frame += max(1, int(rng.expovariate(rate / 1000.0)))
            hold = hold_min + rng.randrange(hold_span + 1)
            if frame + hold >= frames:
                break
            events.append((frame, 1, 'press %s' % button))
            events.append((frame + hold, 2, 'release %s' % button))
            frame += hold + 2
    events.sort()
    lines, now = [], 0
    for frame, _, line in events:
        if frame >= frames:
            break
        if frame > now:
            lines.append('wait %d' % (frame - now))
            now = frame
        lines.append(line)
    if frames > now:
        lines.append('wait %d' % (frames - now))
    lines += ['stick L 128 128', 'release cross+circle+triangle+r1+l1+r2+l2']
    return lines


def script_lines(role, new_character, args):
    lines = ['# written by lobbypair.py: %s' % role, 'until %s:u32 == 5 timeout 15000' % A_LOBBY]
    if new_character:
        lines += new_character_lines()
    lines += ['until %s:u32 == 6 timeout 15000' % A_LOBBY, 'echo in-the-room']
    if role == 'host':
        lines += ['until %s:s8 != -1 timeout 30000' % A_KNOWN, 'echo somebody-joined',
                  'until %s:u8 != 255 timeout 12000' % A_KNOWN_CHOSEN, 'echo their-character-is-chosen',
                  'wait %d' % args.room_wait, 'tapuntil cross 120 %s:u32 == 12 timeout 3000' % A_LOBBY]
    lines += ['until %s:u32 == 12 timeout 30000' % A_LOBBY, 'until g_levelName:str8 == hub timeout 6000',
              'until g_netFrame:s32 >= 200 timeout 6000', 'echo launched',
              'show g_netFrame:s32 g_numPlayers:s32 g_lobbyLaunch:s32 g_levelName:str12']
    if args.idle:
        lines += ['echo no-input', 'wait %d' % args.play]       # nothing is pressed: what do the players do by themselves?
    else:
        lines += play_lines(args.play, args.seed + (0 if role == 'host' else 1000))
    if args.level:
        lines += ['echo waiting-for-level', 'until g_levelName:str8 == %s timeout 12000' % args.level,
                  'until g_players+0x43d8:u32 != 0 timeout 6000', 'wait 240', 'echo in-level']
        lines += ['wait %d' % args.play2] if args.idle else play_lines(args.play2, args.seed + (500 if role == 'host' else 1500))
    lines += ['wait 120', 'show g_netFrame:s32 g_levelName:str12 g_checksumFailed:u8 g_expectedChecksums:crc32 g_receivedChecksums:crc32', 'app online', 'app net peers', 'quit']
    return lines


def compare_samples(samples_path, ticks_path, own_slot):
    """Each sample of the emulator copy (taken at a vertical blank: the tick counter already
    stands at the next tick) against the native copy's tick-log row of the tick before."""
    if not (os.path.exists(samples_path) and os.path.exists(ticks_path)):
        print('samples: nothing to compare (%s)' % ('no samples' if not os.path.exists(samples_path) else 'no tick log'))
        return
    rows = {}
    with open(ticks_path) as source:
        head = source.readline().rstrip('\n').split('\t')
        for line in source:
            fields = line.rstrip('\n').split('\t')
            if len(fields) == len(head):
                row = dict(zip(head, fields))
                rows[int(row['net'])] = row
    same = {0: 0, -1: 0}
    different, missing, first = 0, 0, None
    with open(samples_path) as source:
        head = source.readline().rstrip('\n').split('\t')
        # the sampled copy's own player stands at its predicted position between ticks
        # (net_predictLocalPlayer runs once per drawn frame), so its position is counted apart
        own = ['p%d%s' % (own_slot, axis) for axis in 'xyz']
        columns = [name for name in head if name != 'net' and name not in own]
        predicted = 0
        for line in source:
            sample = dict(zip(head, line.rstrip('\n').split('\t')))
            tick = int(sample['net'])
            found = None
            for offset in (-1, 0):
                row = rows.get(tick + offset)
                if row and all(row.get(name) is None or row[name].lstrip('0').lower() == sample[name].lstrip('0').lower()
                               or row[name] == sample[name] for name in columns):
                    found = offset
                    break
            if found is not None:
                same[found] += 1
                row = rows[tick + found]
                if any(row.get(name) is not None and row[name].lstrip('0').lower() != sample[name].lstrip('0').lower() for name in own):
                    predicted += 1
            elif tick - 1 not in rows and tick not in rows:
                missing += 1
            else:
                different += 1
                if first is None:
                    row = rows.get(tick - 1) or rows.get(tick)
                    first = (tick, [(name, sample[name], row.get(name)) for name in columns
                                    if row.get(name) is not None and row[name].lstrip('0').lower() != sample[name].lstrip('0').lower()])
    print('samples of the emulator copy against the native copy\'s tick log: %d equal in every column (%d at the tick before the '
          'counter, %d at the counter), %d different, %d outside the log; in %d of the equal ones its own player stood at a predicted '
          'position' % (same[-1] + same[0], same[-1], same[0], different, missing, predicted))
    if first:
        print('  first different sample: counter %d: %s' % (first[0], '; '.join('%s %s / %s' % item for item in first[1][:8])))


def make_name(directory):
    path = os.path.join(directory, 'name')
    if os.path.exists(path):
        return open(path).read().strip()
    name = 'Nt' + ''.join(random.choice(string.ascii_lowercase) for _ in range(5)) + str(random.randrange(10, 99))
    with open(path, 'w') as sink:
        sink.write(name + '\n')
    return name


def symbol_files():
    return [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv')))


def start_native(role, out, code, args, window=False):
    import rig as riglib
    directory = os.path.join(out, role)
    os.makedirs(directory, exist_ok=True)
    name = make_name(directory)
    new_character = not os.path.exists(os.path.join(directory, 'online-character'))
    slot = 0 if role == 'host' else 1
    watches = riglib.tick_watches(slot)[1::2] + ['lobby=g_lobbyLaunch:s32', 'chkfail=g_checksumFailed:u8', 'l_chkexp=g_expectedChecksums:crc32', 'l_chkrcv=g_receivedChecksums:crc32'] + args.tick_watch
    watch_file = os.path.join(out, role + '.watch.txt')
    with open(watch_file, 'w') as sink:
        sink.write('\n'.join(watches) + '\n')
    script = os.path.join(out, role + '.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(script_lines(role, new_character, args)) + '\n')
    tick_do = os.path.join(out, 'tick-do.txt')
    if window:
        # the window program: a small test window behind the others, silent, paced by its display
        command = ['nice', '-n', '10', os.path.join(OUT, 'bin', 'rta_app'), '--test', 'native online', '--window', '320x240',
                   '--disc', os.environ['RTA_DISC'], '--data', directory, '--script', script, '--']
    else:
        program = args.join_program if (role == 'join' and args.join_program) else args.program
        command = ['nice', '-n', '10', os.path.join(OUT, 'bin', program), 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'),
                   '--disc', os.environ['RTA_DISC'], '--card', os.path.join(directory, 'card')]
        for path in symbol_files():
            command += ['--sym', path]
    options = {'net-data': directory, 'net-local-only': '1', 'online': '%s:%s' % ('host' if role == 'host' else 'join', code),
               'online-name': name, 'online-person': '0', 'net-log': os.path.join(directory, 'net.log'),
               'tick-log': os.path.join(out, role + '.tick.tsv'), 'tick-watch-file': watch_file, 'tick-do': tick_do,
               'net-pace': str(args.pace)}
    for key, value in options.items():
        command += ['--opt', '%s=%s' % (key, value)]
    command += ([] if window else ['--script', script]) + ['--seconds', str(args.limit)] + args.native_arg
    log = open(os.path.join(out, role + '.out'), 'w')
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)


def run(args):
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('name the disc image with RTA_DISC')
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    code = 'T' + ''.join(random.choice(string.ascii_uppercase) for _ in range(5))
    with open(os.path.join(out, 'tick-do.txt'), 'w') as sink:
        if args.level:
            sink.write('%d poke g_pendingLevel %s\n' % (args.level_tick or (400 + args.play + 500), args.level))
        for item in args.tick_do:
            sink.write(item + '\n')
    kinds = {'host': args.host, 'join': args.join}
    started = time.time()
    processes = {}
    for role in ('host', 'join'):
        if kinds[role] in ('native', 'window'):
            processes[role] = start_native(role, out, code, args, kinds[role] == 'window')
        else:
            import lobbyapp
            processes[role] = lobbyapp.start(role, out, code, args)
        if role == 'host':
            time.sleep(args.stagger)
    codes = {}
    for role, process in processes.items():
        try:
            codes[role] = process.wait(timeout=args.limit + 60)
        except subprocess.TimeoutExpired:
            process.kill()
            codes[role] = -9
    print('code %s; host (%s) exit %s, join (%s) exit %s; %.0f s; load %s' % (
        code, kinds['host'], codes['host'], kinds['join'], codes['join'], time.time() - started, os.getloadavg()[0]))
    for role in ('host', 'join'):
        path = os.path.join(out, role + '.out')
        if not os.path.exists(path):
            continue
        keep = ('[frame', '[tick', '[net] WARNING', '[net] the player', 'online: stage', 'net: ', 'TIMED OUT', 'timed out', 'stopped', 'run ended')
        for line in open(path, errors='replace'):
            if line.startswith(keep) or 'out of sync' in line.lower():
                print('  %s: %s' % (role, line.rstrip()[:230]))
    a, b = os.path.join(out, 'host.tick.tsv'), os.path.join(out, 'join.tick.tsv')
    if kinds['host'] != 'app' and kinds['join'] != 'app':
        subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'compare.py'), 'ticks', a, b])
    else:
        for role in ('host', 'join'):
            other = 'join' if role == 'host' else 'host'
            if kinds[role] == 'app' and kinds[other] != 'app':
                compare_samples(os.path.join(out, role + '.samples.tsv'), os.path.join(out, other + '.tick.tsv'), 0 if role == 'host' else 1)
    return 0 if all(c == 0 for c in codes.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('run')
    p.add_argument('out')
    p.add_argument('--host', choices=('native', 'window', 'app'), default='native')
    p.add_argument('--join', choices=('native', 'window', 'app'), default='native')
    p.add_argument('--program', default='rta_native_online')
    p.add_argument('--join-program', help='another headless program for the joining copy (a build with another patch set)')
    p.add_argument('--play', type=int, default=1800)
    p.add_argument('--idle', action='store_true', help='no input at all after the launch: --play frames of waiting')
    p.add_argument('--level', help='a level name written into g_pendingLevel in one lockstep tick on both copies')
    p.add_argument('--level-tick', type=int)
    p.add_argument('--play2', type=int, default=1800)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--pace', type=float, default=59.94)
    p.add_argument('--room-wait', type=int, default=180, help='frames the host waits in the room after the other player has a character')
    p.add_argument('--stagger', type=float, default=1.0, help='seconds between the two starts')
    p.add_argument('--limit', type=int, default=600)
    p.add_argument('--tick-watch', action='append', default=[])
    p.add_argument('--tick-do', action='append', default=[],
                   help='a line for the native copies\' tick-do file: "<tick> poke32 <expression> <number>" and the like')
    p.add_argument('--native-arg', action='append', default=[])
    p.add_argument('--app-linger', type=float, default=5.0, help='seconds an emulator copy stays after its input ended')
    args = parser.parse_args()
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
