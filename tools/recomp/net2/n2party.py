#!/usr/bin/env python3
"""n2party.py - two to four native copies through the rendezvous service on this computer
into one game: a room by code, the game's own character screens, chat, start, lockstep
ticks compared, and what happens afterwards.  The proof runs of docs/issues/native-rendezvous.md.

  export RTA_DISC="/path/to/your/disc image.iso"
  python3 -B tools/recomp/net2/n2party.py OUT --players 3 [--launches K] [--play FRAMES]
          [--level NAME --play2 FRAMES] [--scenario plain|drop|hostquit|again] [--relay force|never|mixed]
          [--service-address 127.0.0.1|<this computer's LAN address>] [--external] [--tls] [--program PATH]
          [--kind native|window] [--offscreen] [--limit SECONDS]

Windows loopback (PowerShell; RTA_DISC names your own disc; OUT is private test storage):
  python -B tools/recomp/net2/n2party.py OUT --players 2 --kind window --offscreen `
    --program local/recomp-out/win/rta-windows/rta_app.exe --play 600 --limit 120
Add --relay force for a separate trial through the local service's relay. Both copies use
fresh individual cards under OUT on a first run; use a new OUT for an independent trial.
The default service and carrier bind to 127.0.0.1. This tests the native rendezvous/direct
launch adapter (launch.cpp sets the network tables and calls the game's launch routines),
then ordinary character-menu and gamepad inputs. It does not test the original lobby.
Omit --level and --tick-do for a trial without gameplay-memory setup writes.

Starts a rendezvous service of its own (tools/rendezvous/rendezvous.py, on 127.0.0.1 and,
with --service-address, on this computer's LAN address; nothing else) - or, with --external,
uses one already running at --service-address:--port - then the copies:
headless programs that contain the game and tools/recomp/net2/launch.cpp ($RTA_NATIVE_NET2,
default local/recomp-net2/bin/n2_headless).  The first hosts (`--opt net2=host`); its room
code is read from its output and the others join by it.  Every copy boots to the title
screen by itself, makes a character on the game's own screens (the script presses the
buttons a person would), is marked ready by launch.cpp, and the host starts when all are in.

Scenarios (FRAMES are vertical blanks):
  plain     drawn input for --play frames; with --level the pending level name is written in
            one lockstep tick on every copy and --play2 more frames are played there
  drop      after --play frames the LAST joiner's process is killed; the others play on
  hostquit  the same with the HOST's process
  again     after --play frames every copy leaves by the pause menu, is back at the title
            screen, makes a character again and the host starts a second game in the same
            room: --rounds games in the same processes
--relay: force = every copy's routes go through the service's relay; mixed = the last copy's
only; never = no relay (default: punch, relay as the fallback).
--tls: the service of its own has its TCP conversation inside TLS, with certificates made
for the run (tools/rendezvous/check.py's test authority, in OUT/pki; nothing else trusts
it); the copies reach it as tls://localhost:PORT and trust that authority only
(RTA_NET2_TLS_CA).  With --external and a host name the copies use TLS by themselves.

Compared: every pair of tick logs (tools/rig/compare.py ticks: seed, level, player count,
button maps, every player's position, state, hit points, gold, experience, out-of-step
flags, own sync hash), game by game.  One result line per launch goes to OUT/results.txt.
Exit code 0: every requested game launched, every script completed successfully (except
the deliberately killed copy in a drop scenario), every peer recorded all requested games,
and every compared pair had positive confirmed-frame coverage with no shared column differing.
"""
import argparse
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'recomp', 'net'))
import lobbypair   # noqa: E402  (new_character_lines, play_lines)
import lobbyparty  # noqa: E402  (watches, split_games, story, brief)

ROLES = ['host', 'j1', 'j2', 'j3']
A_PAGE, A_CHOSEN = '0x8e2c02', '0x4fbbe2'
STATUS = ('show g_netFrame:s32 g_numPlayers:s32 g_levelName:str12 g_inFrontend:u8 0x402791:u8 '
          + ' '.join('%s+0x44d5:u8 %s+0x44d7:u8' % (('g_peers+%d' % (i * 0x44E0),) * 2) for i in range(4)))


def own_addresses():
    """Local IPv4 addresses only; never substitute a public service address."""
    found = set()
    try:
        found.update(row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM))
    except OSError:
        pass
    if os.name != 'nt':
        try:
            address = subprocess.run(['ipconfig', 'getifaddr', 'en0'], capture_output=True, text=True).stdout.strip()
            if address:
                found.add(address)
        except OSError:
            pass
    return found


def child_options():
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NO_WINDOW}
    return {'preexec_fn': lambda: os.nice(10)}


def stop_service(service):
    if service.poll() is None:
        if os.name == 'nt':
            service.terminate()
        else:
            service.send_signal(2)
    try:
        service.wait(5)
    except subprocess.TimeoutExpired:
        service.kill()
        service.wait()


def load_average():
    try:
        return '%.0f' % os.getloadavg()[0]
    except (AttributeError, OSError):
        return 'unavailable'


def comparison_result(output, returncode):
    found = re.search(r'compared (\d+)', output)
    count = int(found.group(1)) if found else 0
    return count, returncode == 0 and count > 0 and 'no shared column differs' in output


def copies_finished(roles, done, codes, victim=None, killed=False, ready=False):
    """Drop scenarios expect one deliberate kill; every other copy must finish normally."""
    if not all(done.get(r, False) and codes.get(r) == 0 for r in roles if r != victim):
        return False
    return victim is None or (killed and ready and codes.get(victim) not in (None, 0))



def have_expected_games(games, wanted):
    return wanted > 0 and bool(games) and all(len(paths) >= wanted for paths in games.values())


def character_lines():
    """The game's character screens, as a person would walk them for a new character."""
    return (['until %s:u8 == 0 timeout 12000' % A_CHOSEN] + lobbypair.new_character_lines() +
            ['until %s:u8 == 1 timeout 3000' % A_CHOSEN, 'echo character-chosen'])


def leave_lines(role):
    """Start opens the pause menu; Exit Game is the last entry (the first active machine has one
    entry more, Kick Player); "Exit Game? Yes / No" has No under the cursor."""
    downs = 4 if role == 'host' else 3
    return (['echo leaving', 'tap start 10 60'] + ['tap down 10 30'] * downs + ['tap cross 10 60', 'tap left 10 30', 'tap cross 10 30',
            'until g_inFrontend:u8 == 1 timeout 3600', 'echo back-at-the-title', STATUS])


def to_game_lines():
    table = ' '.join(['0x402a37:u8', '0x402a39:u8'] + ['0x%x:x32' % (0x402b3b + 4 * i) for i in range(4)] + ['0x%x:u32' % (0x402b5c + 4 * i) for i in range(4)])
    return ['until 0x402793:u8 == 1 timeout 30000', 'echo launch-tables', 'show ' + table,
            'until g_levelName:str8 != intro timeout 6000', 'echo in-level', 'until g_netFrame:s32 >= 200 timeout 6000', 'echo launched', STATUS,
            'app net2 status']


def script_lines(role, index, n, args):
    seeds = {'host': 0, 'j1': 1000, 'j2': 2000, 'j3': 3000}
    last = ROLES[n - 1]
    play = (lambda frames, salt: ['wait %d' % frames]) if args.idle else (lambda frames, salt: lobbypair.play_lines(frames, args.seed + seeds[role] + salt))
    lines = ['# written by n2party.py: %s, scenario %s' % (role, args.scenario)]
    # in the room, with the character screens just up: a line of chat before anybody is ready
    lines += ['until %s:u8 == 1 timeout 12000' % A_PAGE, 'app net2 chat hello from %s' % role]
    lines += character_lines() + to_game_lines() + play(args.play, 0)
    if args.scenario == 'plain':
        if args.level:
            lines += ['echo waiting-for-level', 'until g_levelName:str8 == %s timeout 12000' % args.level,
                      'until g_players+0x43d8:u32 != 0 timeout 6000', 'wait 240', 'echo in-second-level'] + play(args.play2, 500)
    elif args.scenario in ('drop', 'hostquit'):
        victim = last if args.scenario == 'drop' else 'host'
        if role == victim:
            lines += ['echo ready-to-be-killed', 'wait 100000']
        else:
            lines += ['echo other-about-to-go', STATUS]
            for k in range(8):
                lines += play(args.play2 // 8, 100 + k) + [STATUS]
            lines += ['echo survivor-done']
    elif args.scenario == 'again':
        for r in range(1, args.rounds):
            # the last joiner leaves first, the one before it 600 frames later ...; the host, alone, is put back by the game
            if role == 'host':
                lines += ['echo waiting-to-be-alone', 'until g_inFrontend:u8 == 1 timeout %d' % (900 * n + 3600), 'echo back-at-the-title', STATUS]
            else:
                lines += ['wait %d' % (600 * (n - 1 - index))] + leave_lines(role)
            lines += ['app net2 room'] + character_lines() + to_game_lines() + play(args.play, 10 * r)
    lines += ['wait 120', STATUS, 'app net2 status', 'app net2 room', 'app net2 debug udp', 'echo done', 'quit']
    return lines


def start_service(out, args):
    data = os.path.join(out, 'service')
    os.makedirs(data, exist_ok=True)
    log = open(os.path.join(out, 'service.log'), 'a')
    command = [sys.executable, '-u', os.path.join(ROOT, 'tools', 'rendezvous', 'rendezvous.py'), '--data', data, '--port', str(args.port),
               '--bind', '127.0.0.1', '--status-every', '30']
    if args.service_address != '127.0.0.1':
        command += ['--bind', args.service_address]
    if args.tls:
        command += ['--tls-cert', args.pki['localhost'], '--tls-key', args.pki['localhost.key']]
    for item in args.limit_service:
        command += ['--limit', item]
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **child_options())
    time.sleep(1.0)
    if process.poll() is not None:
        raise SystemExit('the service did not start: see %s' % os.path.join(out, 'service.log'))
    return process


def start_copy(role, index, out, run, room, n, args):
    directory = os.path.join(out, role)
    os.makedirs(directory, exist_ok=True)
    watch_file = os.path.join(run, role + '.watch.txt')
    with open(watch_file, 'w') as sink:
        sink.write('\n'.join(lobbyparty.watches(n) + args.tick_watch) + '\n')
    script = os.path.join(run, role + '.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(script_lines(role, index, n, args)) + '\n')
    symbols = []
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        symbols += ['--sym', path]
    if args.kind == 'window':
        default = os.path.join(ROOT, 'local', 'recomp-out', 'win', 'rta-windows', 'rta_app.exe') if os.name == 'nt' else os.path.join(ROOT, 'local', 'recomp-out', 'bin', 'rta_app')
        program = args.program or os.environ.get('RTA_NATIVE_APP', default)
        command = [program, '--test', 'native rendezvous', '--window', '320x240', '--disc', os.environ['RTA_DISC'],
                   '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--data', directory, '--no-settings', '--no-sound',
                   '--unpaced', '--script', script, '--no-log']
        if args.offscreen:
            command += ['--offscreen']
        command += ['--'] + symbols
    else:
        program = args.program or os.environ.get('RTA_NATIVE_NET2', os.path.join(ROOT, 'local', 'recomp-net2', 'bin', 'n2_headless'))
        command = [program, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--disc', os.environ['RTA_DISC'],
                   '--card', os.path.join(directory, 'card')] + symbols + ['--script', script]
    relay = args.relay if args.relay in ('force', 'never') else ('force' if args.relay == 'mixed' and index == n - 1 else '')
    options = {'net-data': directory, 'net-local-only': '0' if args.external else '1', 'online-person': '0', 'net-pace': str(args.pace),
               'net-log': os.path.join(run, role + '.net.log'), 'tick-log': os.path.join(run, role + '.tick.tsv'),
               'tick-watch-file': watch_file, 'tick-do': os.path.join(run, 'tick-do.txt'),
               'net2': 'host' if role == 'host' else 'join:' + room,
               'net2-service': ('tls://localhost:%d' % args.port) if args.tls and not args.external else '%s:%d' % (args.service_address, args.port),
               'net2-name': role.capitalize() + ' of ' + os.path.basename(out)[:12], 'net2-data': directory, 'net2-players': str(n),
               'net2-log': os.path.join(run, role + '.net2.log'), 'net2-again': '1' if args.scenario == 'again' else '0'}
    if args.service_address == '127.0.0.1' and not args.external:
        options['net2-bind'] = '127.0.0.1:0'
    if relay:
        options['net2-relay'] = relay
    if args.level_option and role == 'host':
        options['net2-level'] = args.level_option
    for item in args.opt:
        key, _, value = item.partition('=')
        options[key] = value
    for key, value in options.items():
        command += ['--opt', '%s=%s' % (key, value)]
    command += ['--seconds', str(args.limit)]
    log = open(os.path.join(run, role + '.out'), 'w')
    env = dict(os.environ)
    if args.tls and not args.external:
        env['RTA_NET2_TLS_CA'] = args.pki['ca']
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, **child_options())


def said(path, word):
    try:
        return any(word in line for line in open(path, errors='replace'))
    except OSError:
        return False


def room_code(path, process, seconds=120):
    end = time.time() + seconds
    while time.time() < end and process.poll() is None:
        try:
            found = re.search(r'net2: ROOM CODE ([A-Z2-9]{5})', open(path, errors='replace').read())
        except OSError:
            found = None
        if found:
            return found.group(1)
        time.sleep(0.3)
    return None


def one_launch(out, number, args):
    n = args.players
    roles = ROLES[:n]
    run = os.path.join(out, 'run%d' % number)
    if os.path.isdir(run):
        shutil.rmtree(run)
    os.makedirs(run)
    with open(os.path.join(run, 'tick-do.txt'), 'w') as sink:
        if args.level and args.scenario == 'plain':
            sink.write('%d poke g_pendingLevel %s\n' % (args.level_tick or (400 + args.play + 300), args.level))
        for item in args.tick_do:
            sink.write(item + '\n')
    started = time.time()
    processes, codes = {}, {}
    pids = open(os.path.join(out, 'pids'), 'a')
    room = None
    killed = None
    victim = {'drop': roles[-1], 'hostquit': 'host'}.get(args.scenario)
    try:
        processes['host'] = start_copy('host', 0, out, run, '', n, args)
        pids.write('%d\n' % processes['host'].pid)
        pids.flush()
        room = room_code(os.path.join(run, 'host.out'), processes['host'])
        if not room:
            raise RuntimeError('the host did not open a room')
        for index, role in enumerate(roles[1:], 1):
            processes[role] = start_copy(role, index, out, run, room, n, args)
            pids.write('%d\n' % processes[role].pid)
            pids.flush()
            time.sleep(args.stagger)
        deadline = time.time() + args.limit + 60
        while time.time() < deadline and any(p.poll() is None for p in processes.values()):
            if victim and processes[victim].poll() is None and said(os.path.join(run, victim + '.out'), '] ready-to-be-killed') \
                    and all(said(os.path.join(run, r + '.out'), '] other-about-to-go') for r in roles if r != victim):
                time.sleep(2.0)
                processes[victim].kill()
                killed = victim
                print('killed %s (pid %d) at %.0f s' % (victim, processes[victim].pid, time.time() - started))
            time.sleep(0.5)
        for role, process in processes.items():
            codes[role] = process.poll() if process.poll() is not None else -9
    except RuntimeError as problem:
        print('launch %d: %s' % (number, problem))
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.kill()
                process.wait()
        pids.close()
    texts = {r: open(os.path.join(run, r + '.out'), errors='replace').read() if os.path.exists(os.path.join(run, r + '.out')) else '' for r in roles}
    launched = {r: texts[r].count('] launched') for r in roles}
    done = {r: ('] done' in texts[r] or '] survivor-done' in texts[r]) and 'TIMEOUT' not in texts[r] for r in roles}
    for role in roles:
        whole = args.verbose or not done[role] or not launched[role]
        for line in texts[role].splitlines():
            if (whole and (line.startswith('net2:') or '[frame' in line or 'TIMEOUT' in line)) or 'out of sync' in line.lower() or 'WARNING' in line \
                    or 'net2: launch' in line or 'net2: the room started' in line or 'carrier:' in line or 'TIMEOUT' in line or 'net2: the game is over' in line \
                    or 'net2: the launch did not' in line:
                print('  %s: %s' % (role, lobbyparty.brief(line.rstrip())[:420]))
    games = {r: lobbyparty.split_games(os.path.join(run, r + '.tick.tsv')) for r in roles}
    wanted = args.rounds if args.scenario == 'again' else 1
    ticks, same = [], have_expected_games(games, wanted)
    for k in range(max([len(g) for g in games.values()] or [0])):
        for i in range(n):
            for j in range(i + 1, n):
                if k >= len(games[roles[i]]) or k >= len(games[roles[j]]):
                    same = False
                    continue
                result = subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'compare.py'), 'ticks', games[roles[i]][k], games[roles[j]][k]],
                                        capture_output=True, text=True)
                count, equal = comparison_result(result.stdout, result.returncode)
                same = same and equal
                ticks.append('%s%s/%s %s%s' % ('game %d ' % (k + 1) if len(games[roles[i]]) > 1 else '', roles[i], roles[j], count, '' if equal else ' DIFFER'))
                if not equal:
                    print('--- %s against %s\n%s' % (roles[i], roles[j], result.stdout[:1500]))
    routes = []
    for role in roles:
        found = re.findall(r'carrier: .*?; (player .*?); \d+ sent \((\d+) by relay\), (\d+) received \((\d+) by relay\)', texts[role])
        if found:
            routes.append('%s[%s | relayed out %s in %s]' % (role, found[-1][0], found[-1][1], found[-1][3]))
    line = '%s launch %d (%d players; %s; relay %s; service %s) room %s load %s %.0f s | launched %s | script done %s | ticks in step: %s | %s | routes: %s' % (
        time.strftime('%H:%M:%S'), number, n, args.scenario, args.relay or 'auto', args.service_address, room, load_average(), time.time() - started,
        ' '.join('%s=%s' % (r, 'yes' if launched[r] >= wanted else ('%d of %d' % (launched[r], wanted) if launched[r] else 'NO')) for r in roles),
        ' '.join('%s=%s' % (r, 'yes' if done[r] else 'no(exit %s)' % codes.get(r)) for r in roles), '; '.join(ticks) or 'none',
        lobbyparty.story(os.path.join(run, 'host.tick.tsv'), n), ' '.join(routes) or '?')
    print(line)
    with open(os.path.join(out, 'results.txt'), 'a') as sink:
        sink.write(line + '\n')
    finished = copies_finished(roles, done, codes, victim, killed == victim if victim else False,
                               '] ready-to-be-killed' in texts[victim] if victim else False)
    return finished and all(launched[r] >= wanted for r in roles) and same and bool(ticks)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out')
    parser.add_argument('--players', type=int, default=2)
    parser.add_argument('--launches', type=int, default=1)
    parser.add_argument('--scenario', choices=('plain', 'drop', 'hostquit', 'again'), default='plain')
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--relay', choices=('', 'force', 'never', 'mixed'), default='')
    parser.add_argument('--service-address', default='127.0.0.1', help='127.0.0.1 (default) or this computer\'s LAN address')
    parser.add_argument('--external', action='store_true', help='use a service already running at --service-address:--port (e.g. on a server) instead of starting one')
    parser.add_argument('--port', type=int, default=41977)
    parser.add_argument('--tls', action='store_true', help='the service of its own inside TLS, with certificates made for the run')
    parser.add_argument('--limit-service', action='append', default=[], metavar='NAME=VALUE', help='a limit of the service, to hit it')
    parser.add_argument('--program')
    parser.add_argument('--kind', choices=('native', 'window'), default='native', help='native headless program (default) or the window application')
    parser.add_argument('--offscreen', action='store_true', help='window kind: never show the test window')
    parser.add_argument('--play', type=int, default=1800)
    parser.add_argument('--level')
    parser.add_argument('--level-tick', type=int)
    parser.add_argument('--level-option', help='the host\'s room option "start in this level" (net2-level)')
    parser.add_argument('--play2', type=int, default=1800)
    parser.add_argument('--idle', action='store_true')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--pace', type=float, default=59.94)
    parser.add_argument('--stagger', type=float, default=1.0)
    parser.add_argument('--limit', type=int, default=600)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--opt', action='append', default=[])
    parser.add_argument('--tick-watch', action='append', default=[])
    parser.add_argument('--tick-do', action='append', default=[])
    args = parser.parse_args()
    if not os.environ.get('RTA_DISC'):
        raise SystemExit('name the disc image with RTA_DISC')
    if not 2 <= args.players <= 4:
        raise SystemExit('two to four players')
    if args.launches <= 0 or args.rounds <= 0:
        parser.error('--launches and --rounds must be positive')
    if args.offscreen and args.kind != 'window':
        parser.error('--offscreen requires --kind window')
    if not args.external and args.service_address != '127.0.0.1' and args.service_address not in own_addresses():
        raise SystemExit('the service must be on this computer (127.0.0.1 or a local IPv4 address), not %s' % args.service_address)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    if args.tls and not args.external:
        sys.path.insert(0, os.path.join(ROOT, 'tools', 'rendezvous'))
        import check as service_checks         # the test authority of the service's self-test
        args.pki = service_checks.test_certificates(out)
    service = None if args.external else start_service(out, args)
    if service:
        with open(os.path.join(out, 'pids'), 'a') as pids:
            pids.write('%d\n' % service.pid)
    good = True
    try:
        for number in range(1, args.launches + 1):
            good = one_launch(out, number, args) and good
    finally:
        if service:
            stop_service(service)
            with open(os.path.join(out, 'service.log'), errors='replace') as source:
                tail = source.read().splitlines()[-1:]
            print('service: %s' % (tail[0] if tail else '?'))
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
