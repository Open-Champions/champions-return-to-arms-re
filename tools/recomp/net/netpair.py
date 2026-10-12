#!/usr/bin/env python3
"""netpair.py - lockstep games with the native build: images, pairs, cross-play, comparison.

  # 1. two memory images (one per machine) and two rig states, all of the same instant of
  #    a running pair game, from a pair of rig states (tools/rig/examples/pair-start.rig):
  python3 tools/recomp/net/netpair.py snapshot local/recomp-out/net/img1 \
      --a-state local/rig-out/run1/a.zip --b-state local/rig-out/run1/b.zip

  # 2. a pair: each machine is `native` (rta_native_net resumed from its image) or `rig`
  #    (an rta_rig runner loading its state); they are joined by the rig's link
  python3 tools/recomp/net/netpair.py run local/recomp-out/net/nn --img local/recomp-out/net/img1 \
      --a native --b native --script my.rig --bus delay=3,jitter=3,loss=50,seed=1
  python3 tools/recomp/net/netpair.py run local/recomp-out/net/nr --img ... --a native --b rig ...
  python3 tools/recomp/net/netpair.py run local/recomp-out/net/rr --img ... --a rig --b rig ...
  #    --udp BASE joins two native machines by host UDP on 127.0.0.1 instead
  #    --boot starts both from power-on with the boot argument --net (no --img):
  python3 tools/recomp/net/netpair.py run local/recomp-out/net/boot1 --boot --a native --b native \
      --program rta_native_net-live --script tools/rig/examples/pair-start.rig

  # 3. the tick logs, by tools/rig/compare.py
  python3 tools/recomp/net/netpair.py compare local/recomp-out/net/nn

Needs RTA_DISC for the rig machines.  Rig runners are started under `nice -n 19`; a pair
is two processes.  Everything written is game data and belongs under local/.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'rig'))
import rig as riglib   # noqa: E402  (tools/rig/rig.py: runner command, default tick columns, addresses)

LOOP_HEAD = 0x322B48
REGS = ('at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 '
        'gp sp fp ra').split()
LINK_DIR = os.environ.get('RTA_LINK_DIR') or __import__('tempfile').gettempdir()


def read_ticks(path):
    rows = [line.rstrip('\n').split('\t') for line in open(path)]
    return rows[0], rows[1:]


def rig_pair(out_dir, args, data_root):
    env = dict(os.environ, RTA_LINK_DIR=LINK_DIR, RTA_PAIR_DATA=data_root, RTA_PAIR_GRACE='60')
    command = ['nice', '-n', '19', sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'rig.py'), 'pair', out_dir] + args
    return subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=env)


def snapshot(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    data_root = os.path.join(out, 'data-')
    prelude = open(args.prelude).read().rstrip('\n').split('\n') if args.prelude else []
    common = ['--a-load', args.a_state, '--b-load', args.b_state, '--tick-at', '0x%x' % LOOP_HEAD]
    if args.bus:
        common += ['--bus', args.bus]

    # probe: at which frame does each machine pass the loop head, and with which tick number?
    probe = os.path.join(out, 'probe')
    script = os.path.join(out, 'probe.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(prelude + ['echo snapshot-mark', 'wait %d' % (args.settle + 30)]) + '\n')
    done = rig_pair(probe, common + ['--script', script], data_root)
    logs = {m: read_ticks(os.path.join(probe, m + '.tick.tsv')) for m in 'ab'}
    marks = [int(n) for m in 'ab' for n in re.findall(r'\[frame (\d+)\] snapshot-mark',
                                                      open(os.path.join(probe, m + '.out'), errors='replace').read())]
    if len(marks) != 2:
        print(done.stdout[-2000:])
        raise SystemExit('the prelude did not finish on both machines')
    after = max(marks) + args.settle
    first = {}
    for m, (header, rows) in logs.items():
        net = header.index('net')
        seen = set()
        first[m] = {}
        for row in rows:
            if row[net] not in seen:
                seen.add(row[net])
                first[m][int(row[0])] = int(row[net])
    frames = sorted(f for f in first['a'] if f in first['b'] and f >= after)
    if not frames:
        print(done.stdout[-2000:])
        raise SystemExit('no frame at which both machines pass the loop head with a new tick number')
    frame = frames[0]
    ticks = {m: first[m][frame] for m in 'ab'}
    print('probe: frame %d, machine A at tick %d, machine B at tick %d' % (frame, ticks['a'], ticks['b']))

    # the run again (a pair of rig runs repeats exactly), now writing the images and states
    lines = list(prelude)
    for m in 'ab':
        tag, tick = m.upper() + ':', ticks[m]
        lines += ['%s ontick %d dump 0 0x2000000 %s' % (tag, tick, os.path.join(out, m + '-ram.bin')),
                  '%s ontick %d dump 0x70000000 0x4000 %s' % (tag, tick, os.path.join(out, m + '-spr.bin')),
                  '%s ontick %d show %s' % (tag, tick, ' '.join('$%s:u8' % r for r in REGS))]
    lines += ['at %d' % frame]
    script = os.path.join(out, 'snapshot.rig')
    with open(script, 'w') as sink:
        sink.write('\n'.join(lines) + '\n')
    take = os.path.join(out, 'take')
    extra = []
    for m in 'ab':
        for command in ('save %s' % os.path.join(out, m + '.zip'), 'wait 4'):
            extra += ['--%s-arg' % m, '--do', '--%s-arg' % m, command]
    done = rig_pair(take, common + ['--script', script] + extra, data_root)
    for m in 'ab':
        text = open(os.path.join(take, m + '.out'), errors='replace').read()
        found = dict(re.findall(r'\$(\w+)@([0-9a-f]{8})=', text))
        if len(found) != len(REGS):
            print(text[-1500:])
            raise SystemExit('machine %s did not report its registers' % m.upper())
        with open(os.path.join(out, m + '-regs.txt'), 'w') as sink:
            for name in REGS:
                sink.write('%s %s\n' % (name, found[name]))
        # the second run must be the first one again, as far as it goes
        header, rows = read_ticks(os.path.join(take, m + '.tick.tsv'))
        _, probe_rows = logs[m]
        same = all(a == b for a, b in zip(rows, probe_rows[:len(rows)]))
        dumped = [row for row in rows if int(row[0]) == frame and int(row[header.index('net')]) == ticks[m]]
        print('machine %s: image at frame %d, tick %d; second run %s the first over %d loop passes%s' % (
            m.upper(), frame, ticks[m], 'repeats' if same else 'DOES NOT REPEAT', len(rows), '' if dumped else '; DUMP ROW MISSING'))
        for name in (m + '-ram.bin', m + '-spr.bin', m + '.zip'):
            if not os.path.exists(os.path.join(out, name)):
                raise SystemExit('missing ' + name)
    with open(os.path.join(out, 'info.txt'), 'w') as sink:
        sink.write('frame %d\ntick_a %d\ntick_b %d\na_state %s\nb_state %s\nbus %s\n' % (
            frame, ticks['a'], ticks['b'], args.a_state, args.b_state, args.bus or ''))
    return 0


def run(args):
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    img = os.path.abspath(args.img) if args.img else None
    if not args.boot and not img:
        raise SystemExit('run needs --img DIR, or --boot')
    kinds = {'A': args.a, 'B': args.b}
    link = os.path.join(LINK_DIR, 'nn-%d.sock' % os.getpid())
    symbols = riglib.symbol_files()
    script = os.path.abspath(args.script) if args.script else None
    processes = []
    for letter in 'AB':
        address, slot, mode = riglib.PAIR[letter]
        low = letter.lower()
        watches = riglib.tick_watches(slot)[1::2]
        if args.columns == 'small':     # a long soak: the columns the game itself hashes, and its verdict
            keep = ('net=', 'seed=', 'level=', 'nplayers=', 'prevhash=', 'p0x=', 'p0y=', 'p0z=', 'p1x=', 'p1y=', 'p1z=',
                    'p0hp=', 'p1hp=', 'p0state=', 'p1state=', 'p0exp=', 'p1exp=', 'oos0=', 'oos1=', 'l_dropped0=', 'l_dropped1=')
            watches = [w for w in watches if w.startswith(keep)]
        watches += args.tick_watch
        own = [v.replace('%M', low) for v in (args.a_arg if letter == 'A' else args.b_arg)]
        if kinds[letter] == 'native':
            watch_file = os.path.join(out, low + '.watch.txt')
            with open(watch_file, 'w') as sink:
                sink.write('\n'.join(watches) + '\n')
            env = dict(os.environ, RTA_NET_ADDR=address, RTA_NET_MACHINE=letter, RTA_NET_SYM=':'.join(symbols),
                       RTA_NET_TICKLOG=os.path.join(out, low + '.tick.tsv'), RTA_NET_WATCH=watch_file,
                       RTA_NET_LOG=os.path.join(out, low + '.net.log'))
            if args.udp:
                env['RTA_NET_UDP'] = str(args.udp)
            else:
                env['RTA_NET_LINK'] = '%s:%s' % (mode, link)
            if args.bus:
                env['RTA_NET_BUS'] = args.bus
            if script:
                env['RTA_NET_SCRIPT'] = script
            if args.frames:
                env['RTA_NET_FRAMES'] = str(args.frames)
            if args.pace is not None:
                env['RTA_NET_PACE'] = str(args.pace)
            program = args.program if os.path.isabs(args.program) else os.path.join(OUT, 'bin', args.program)
            words = os.path.join(OUT, 'gen-net' + os.path.basename(program)[len('rta_native_net'):], 'patch-words.txt')
            if os.path.exists(words):
                env['RTA_NET_PATCH'] = words
            # a paced instance sleeps between frames, and macOS stretches the sleeps of a
            # niced process to hundreds of milliseconds on a busy machine: only the
            # unpaced (link) instances, which are bound by the processor, are niced
            polite = [] if args.udp else ['nice', '-n', '19']
            if args.boot:
                # from power-on through the developer LAN start; each machine has its own card
                card = os.path.join(out, 'card-' + low)
                if not os.path.isdir(card):
                    shutil.copytree(os.path.join(args.cards + low, 'vfs'), card)
                env['RTA_NET_ARG'] = '--net'
                env['RTA_NET_ALLOW_LEVEL'] = '1'
                command = polite + [program, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--card', card] + own
            else:
                command = polite + [program, 'resume', '--ram', os.path.join(img, low + '-ram.bin'),
                                    '--spr', os.path.join(img, low + '-spr.bin'), '--regs', os.path.join(img, low + '-regs.txt'),
                                    '--entry', '%x' % LOOP_HEAD] + own
        else:
            if args.udp:
                raise SystemExit('--udp joins native machines only')
            rig_args = ['--machine', letter, '--net-shim', address, '--link', '%s:%s' % (mode, link),
                        '--net-log', os.path.join(out, low + '.net.log'), '--tick-log', os.path.join(out, low + '.tick.tsv')]
            if args.boot:
                data = os.path.join(out, 'data-' + low)
                if not os.path.isdir(data):
                    shutil.copytree(args.cards + low, data)
                rig_args += ['--data', data, '--arg', '--net']
            else:
                rig_args += ['--data', os.path.join(img, 'data-' + low), '--load', os.path.join(img, low + '.zip')]
            for watch in watches:
                rig_args += ['--tick-watch', watch]
            if args.bus:
                rig_args += ['--bus', args.bus]
            if script:
                rig_args += ['--script', script]
            if args.frames:
                rig_args += ['--frames', str(args.frames)]
            env = dict(os.environ)
            command = ['nice', '-n', '19'] + riglib.runner_command(rig_args + own)
        sink = open(os.path.join(out, low + '.out'), 'w')
        processes.append((letter, subprocess.Popen(command, stdout=sink, stderr=subprocess.STDOUT, env=env, cwd=ROOT), sink))
    start = time.time()
    deadline = None
    while any(p.poll() is None for _, p, _ in processes):
        if deadline is None and any(p.poll() is not None for _, p, _ in processes):
            deadline = time.time() + args.grace
        if (deadline is not None and time.time() > deadline) or (args.timeout and time.time() - start > args.timeout):
            for _, p, _ in processes:
                if p.poll() is None:
                    p.kill()
        time.sleep(0.2)
    status = 0
    for letter, process, sink in processes:
        code = process.wait()
        sink.close()
        # 6: the other machine ended first; 7: a level change the runtime could not load;
        # -13: a rig machine was writing to a native one that had just ended
        if code not in (0, 6, 7, -13):
            status = code
        lines = [l for l in open(sink.name, errors='replace').read().splitlines() if 'CMIPSAnalysis' not in l]
        print('== machine %s (%s), exit code %d' % (letter, kinds[letter], code))
        keep = [l for l in lines if l.startswith(('net shim:', '[', 'resumed', 'rta_native', 'netshim', 'frames=', 'the ', 'thread'))]
        print('\n'.join(l[:400] for l in keep[-args.tail:]))
    print('wall %.1f s' % (time.time() - start))
    if not args.no_compare:
        compare(args)
    return status


def compare(args):
    out = os.path.abspath(args.out)
    done = subprocess.run([sys.executable, '-I', '-B', os.path.join(ROOT, 'tools', 'rig', 'compare.py'), 'ticks',
                           os.path.join(out, 'a.tick.tsv'), os.path.join(out, 'b.tick.tsv')], capture_output=True, text=True, cwd=ROOT)
    print((done.stdout + done.stderr).rstrip()[-3000:])
    return done.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snapshot')
    p.add_argument('out')
    p.add_argument('--a-state', required=True)
    p.add_argument('--b-state', required=True)
    p.add_argument('--settle', type=int, default=90, help='frames to run before the images are taken')
    p.add_argument('--prelude', help='script lines to run first (a level change, for example)')
    p.add_argument('--bus')
    p = sub.add_parser('run')
    p.add_argument('out')
    p.add_argument('--img', help='directory written by `snapshot`')
    p.add_argument('--boot', action='store_true', help='start both machines from power-on with the boot argument --net')
    p.add_argument('--cards', default=os.path.join(ROOT, 'local', 'rig-out', 'pair-'),
                   help='with --boot: prefix of the two emulator data directories (…a, …b) whose memory cards are copied')
    p.add_argument('--a', choices=('native', 'rig'), default='native')
    p.add_argument('--b', choices=('native', 'rig'), default='native')
    p.add_argument('--program', default='rta_native_net')
    p.add_argument('--script')
    p.add_argument('--bus')
    p.add_argument('--udp', type=int, help='base port: host UDP on 127.0.0.1 instead of the link')
    p.add_argument('--pace', type=float)
    p.add_argument('--frames', type=int)
    p.add_argument('--tick-watch', action='append', default=[])
    p.add_argument('--columns', choices=('all', 'small'), default='all',
                   help='tick-log columns: the rig launcher\'s full set, or a small set for long soaks')
    p.add_argument('--a-arg', action='append', default=[])
    p.add_argument('--b-arg', action='append', default=[])
    p.add_argument('--grace', type=float, default=30, help='seconds the second machine gets after the first has ended')
    p.add_argument('--timeout', type=float, default=0)
    p.add_argument('--tail', type=int, default=8)
    p.add_argument('--no-compare', action='store_true')
    p = sub.add_parser('compare')
    p.add_argument('out')
    args = parser.parse_args()
    return {'snapshot': snapshot, 'run': run, 'compare': compare}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
