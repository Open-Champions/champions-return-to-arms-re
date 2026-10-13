#!/usr/bin/env python3
"""session.py - one scripted session from its script to the compared result.

  python3 tools/recomp/proof/session.py NAME vet     [--ticks N]   # native alone: does the script get through?
  python3 tools/recomp/proof/session.py NAME rig     [--frames N]  # the original in the rig
  python3 tools/recomp/proof/session.py NAME native  [--capture]   # the translation on the rig's controller bytes
  python3 tools/recomp/proof/session.py NAME compare               # tick for tick; writes result.txt

A session is an entry of local/recomp-out/proof/sessions.json: {"class": 0..6, "levels":
"a,b,c", "die": "a", "ticks": 480, "seed": 1} (tour.py's options) or {"script": FILE}.
Everything goes to local/recomp-out/proof/cmp/NAME/ (cmp.py); `native` runs the
instrumented runtime (bin/rta_proof) and leaves hits.tsv there - every entry point with
the number of times it was reached - and with --capture the entry states of the functions
in want.txt under local/recomp-out/proof/real/NAME/ for realproof.py.
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmp as cmpmod                            # noqa: E402

ROOT = cmpmod.ROOT
PROOF = os.path.join(ROOT, 'local', 'recomp-out', 'proof')
NATIVE = os.environ.get('PROOF_NATIVE') or os.path.join(PROOF, 'build', 'bin', 'rta_proof')    # built from the snapshot (build_proof.py)
# besides rigcompare's columns: the 32 sound-sequence slots and the equipment-model cache of
# the first player, two places outside the compared simulation state that follow the
# machines' own sound and disc timing (docs/issues/native-proof.md, part 1)
DEFAULT_WATCHES = ['sseq=0x871a68:crc2432', 'eqcache=0x866388:crc88']


DUMP_MARK = 77                  # the first marker value; the n-th image of a session is armed by DUMP_MARK + n


def with_dumps(path, spec, out):
    """A session with "dumps": ["level:tick", ...] gets a memory image on both machines
    at the same tick of each: the rig writes it inside its tick hook (`ontick M dump`),
    armed when the script pokes the marker M into g_netFrame (unused offline); the row of
    the rig's log that shows M first says at which episode and tick, and the native run
    writes its image there (--opt proof-dump).  The poke is put after the first `until
    g_simFrame >= T` of the level's part of the script with T at or after the tick."""
    dumps = spec.get('dumps') or []
    if not dumps:
        return path
    lines = open(path).read().split('\n')
    head = []
    for n, item in enumerate(dumps):
        level, tick = item.split(':')
        mark = DUMP_MARK + n
        head.append('ontick %d dump 0 0x2000000 %s' % (mark, os.path.join(out, 'rig-dump-%d.bin' % mark)))
        inside = False
        for at, line in enumerate(lines):
            if line.startswith('# ---- '):
                inside = line == '# ---- %s ----' % level
            words = line.split()
            if inside and words[:3] == ['until', 'g_simFrame:u32', '>='] and int(words[3]) >= int(tick) and \
                    not lines[at + 1].startswith(('poke', 'echo')):
                lines.insert(at + 1, 'poke 0x%x:s32 %d' % (0x4027AC, mark))
                break
        else:
            raise SystemExit('no place for the image %s in %s' % (item, path))
    target = os.path.join(out, 'session-dumps.rig')
    with open(target, 'w') as sink:
        sink.write('\n'.join(head + lines))
    return target


def script_of(name, spec, out, ticks=None):
    return with_dumps(script_base(name, spec, out, ticks), spec, out)


def script_base(name, spec, out, ticks=None):
    if 'script' in spec:
        return os.path.join(ROOT, spec['script'])
    path = os.path.join(out, 'session.rig')
    command = [sys.executable, os.path.join(HERE, 'tour.py'), '--out', path, '--class', str(spec.get('class', 6)),
               '--levels', spec['levels'], '--ticks', str(ticks or spec.get('ticks', 480)), '--seed', str(spec.get('seed', 1))]
    if spec.get('die'):
        command += ['--die', spec['die']]
    if spec.get('plain'):
        command.append('--plain')
    if spec.get('presses') is not None:
        command += ['--presses', str(spec['presses'])]
    subprocess.run(command, check=True, capture_output=True)
    return path


def poke_bytes(kind, value):
    if kind in ('s8', 'u8'):
        return struct.pack('<b' if kind == 's8' else '<B', int(value, 0))
    if kind in ('s16', 'u16'):
        return struct.pack('<h' if kind == 's16' else '<H', int(value, 0))
    if kind in ('s32', 'u32'):
        return struct.pack('<i' if kind == 's32' else '<I', int(value, 0))
    if kind == 'x32':
        return struct.pack('<I', int(value, 16))
    if kind == 'f32':
        return struct.pack('<f', float(value))
    if kind.startswith('hex'):
        return bytes.fromhex(value)
    if kind.startswith('str'):
        return value.encode('latin1') + b'\0'
    raise ValueError('poke type %s' % kind)


def replay_pokes(script, out, shift):
    """The script without its announced poke groups, and the file that tells the native run
    when to apply them: at the tick the rig applied them.  Returns (script path, pokes path)."""
    lines = open(script).read().split('\n')
    groups, kept, current = {}, [], None
    for line in lines:
        words = line.split()
        if words[:1] == ['echo'] and words[1:2] == ['@P']:
            current = int(words[2])
            groups[current] = []
            kept.append(line)
        elif words[:1] == ['ontick']:
            continue                            # the rig's own: a memory dump inside a tick
        elif words[:1] == ['poke'] and current is not None:
            target, kind = words[1].rsplit(':', 1)
            groups[current].append((int(target, 0), poke_bytes(kind, words[2])))
        else:
            if words and not line.startswith('#'):
                current = None
            kept.append(line)
    ran = {}
    for line in open(os.path.join(out, 'boot-rig.out'), errors='replace'):
        m = re.match(r'\[frame (\d+)\] @P (\d+)', line)
        if m:
            ran[int(m.group(2))] = int(m.group(1))
    rows = []                                   # (rig frame, episode, tick, frame of the tick)
    with open(os.path.join(out, 'boot-rig.tsv')) as source:
        header = source.readline().rstrip('\n').split('\t')
        sim = header.index('sim')
        episode, last, frame = 0, 0, 0
        for line in source:
            row = line.split('\t', sim + 2)
            if len(row) < sim + 2:
                continue
            tick = int(row[sim])
            if tick < last:
                episode += 1
            frame = frame + 1 if tick == last else 0
            last = tick
            rows.append((int(row[0]), episode, tick, frame))
    frames = [r[0] for r in rows]
    import bisect
    stripped = os.path.join(out, 'session-native.rig')
    with open(stripped, 'w') as sink:
        sink.write('\n'.join(kept))
    pokes = os.path.join(out, 'pokes.txt')
    missing = 0
    with open(pokes, 'w') as sink:
        for number in sorted(groups):
            if number not in ran:
                missing += 1
                continue
            # The rig ran the group at the blank that begins frame `ran[number]`: after the row
            # logged in the frame before, before the row logged in that frame (row N).  Where
            # in that frame's work the blank fell - before or after the tick's simulation
            # step - differs from frame to frame.  The native run applies the group at its
            # frame hook, which follows the logging of a row:
            #   a write that ends the level: after the last row of the level, so that both
            #     machines leave after the same tick;
            #   any other: after row N, so that the first simulation step that sees the
            #     written values is the same when the rig's blank fell after the step (what
            #     the rig's logs show: a written value stands unchanged in row N).  The
            #     native log then shows the write one row late - one tick of difference in
            #     the written columns, listed as "write rows" by summary.py - and nothing
            #     after it.  --poke-shift -1 applies them a row earlier.
            at = bisect.bisect_left(frames, ran[number])
            if at == 0:
                missing += 1
                continue
            if at >= len(rows) or rows[at][1] != rows[at - 1][1]:
                at -= 1
            else:
                at = max(0, min(len(rows) - 1, at + shift))
            _, episode, tick, frame = rows[at]
            if tick == 0 and episode >= 4 and os.environ.get('PROOF_DROP_LOAD_WRITES'):
                missing += 1                    # an experiment: leave such a group out
                continue
            if tick == 0 and episode >= 4:
                # written while a level loads (the script ran on through a level change the
                # game made): the load takes fewer frames here, so the row's frame number
                # would never come; apply at the start of the load instead
                frame = min(frame, 1)
            for addr, blob in groups[number]:
                sink.write('%d %d %d %x %s\n' % (episode, tick, frame, addr, blob.hex()))
    print('%d groups of memory writes, %d the rig did not reach' % (len(groups), missing))
    return stripped, pokes


COSMETIC = 'cosmetic=0x404460:x32'
INIT_COUNTER_SITE = 0x19D1E0        # engine_init: the cosmetic seed is taken from the CPU cycle counter


def first_seed(path):
    """The cosmetic seed in the first row of a tick log whose simulation tick is 1."""
    with open(path) as source:
        header = source.readline().rstrip('\n').split('\t')
        sim, seed = header.index('sim'), header.index('cosmetic')
        for line in source:
            row = line.rstrip('\n').split('\t')
            if len(row) > max(sim, seed) and row[sim] == '1':
                return int(row[seed], 16)
    raise SystemExit('no row with tick 1 in %s' % path)


def init_counter(out):
    """The value the rig's machine read from the cycle counter in engine_init.

    engine_init seeds the cosmetic generator from that read and builds the noise table
    (math_buildNoiseTable) from it; lights that flicker (Torch_run) take their radius and
    position from the table, and those are fields of objects in the pool.  The rig's log
    shows the seed only after start-up has drawn from it, but every draw is one step of a
    linear generator, so the logged seed is a*counter + b (mod 2^32): two short native runs
    with the counter forced to 0 and 1 give a and b, and the rig's seed gives its counter."""
    cache = os.path.join(PROOF, 'init-counter.txt')
    if os.path.exists(cache):
        a, b = (int(x, 16) for x in open(cache).read().split())
    else:
        seeds = []
        work = os.path.join(PROOF, 'init-counter')
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, 'watch.txt'), 'w') as sink:
            sink.write('sim=0x44fdcc:u32\n%s\n' % COSMETIC)
        with open(os.path.join(work, 'wait.rig'), 'w') as sink:
            sink.write('wait 120\nquit\n')
        for value in (0, 1, 2):
            log = os.path.join(work, 'log-%d.tsv' % value)
            env = dict(os.environ, RTA_NATIVE=NATIVE, RTA_NICE='19')
            subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), 'native.py'), 'boot', '--card', os.path.join(work, 'card'),
                            '--script', os.path.join(work, 'wait.rig'), '--watch-file', os.path.join(work, 'watch.txt'), '--log', log,
                            '--count-at', '%x=%x' % (INIT_COUNTER_SITE, value)], capture_output=True, env=env, cwd=ROOT)
            seeds.append(first_seed(log))
        a, b = (seeds[1] - seeds[0]) & 0xFFFFFFFF, seeds[0]
        if (2 * a + b) & 0xFFFFFFFF != seeds[2] or not a & 1:
            raise SystemExit('the start-up seed is not a linear function of the counter: %s' % ['%08x' % s for s in seeds])
        with open(cache, 'w') as sink:
            sink.write('%08x %08x\n' % (a, b))
    seed = first_seed(os.path.join(out, 'boot-rig.tsv'))
    return ((seed - b) * pow(a, -1, 1 << 32)) & 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('name')
    parser.add_argument('step', choices=('vet', 'rig', 'native', 'compare'))
    parser.add_argument('--ticks', type=int)
    parser.add_argument('--frames', type=int, default=40000)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--native-opt', action='append', default=[], help='native: one more --opt KEY=VALUE for the runtime (proof_rt.cpp: proof-watch=..., proof-watch-ticks=...); repeatable')
    parser.add_argument('--no-last-tick-fix', action='store_true', help='native: do not add the bytes of the tick that ended each level to the replay file (cmp.py, last_tick_fix)')
    parser.add_argument('--per', type=int, default=3)
    parser.add_argument('--poke-shift', type=int, default=0, help='native: apply the memory writes this many displayed frames later (or, negative, earlier) than the first row the rig logged after it ran them')
    args = parser.parse_args()
    spec = json.load(open(os.path.join(PROOF, 'sessions.json')))[args.name]
    import rigcompare
    if args.step == 'vet':
        out = os.path.join(PROOF, 'vet', args.name)
        os.makedirs(out, exist_ok=True)
        script = script_of(args.name, spec, out, args.ticks)
        card = os.path.join(out, 'card')
        subprocess.run(['rm', '-rf', card])
        env = dict(os.environ, RTA_NATIVE=NATIVE, RTA_NICE='19')
        done = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), 'native.py'),
                               'boot', '--card', card, '--script', script, '--opt', 'proof-hits=' + os.path.join(out, 'hits.tsv')],
                              capture_output=True, text=True, errors='replace', env=env, cwd=ROOT)
        with open(os.path.join(out, 'native.out'), 'w') as sink:
            sink.write(done.stdout + done.stderr)
        for line in (done.stdout + done.stderr).splitlines():
            if 'g_levelName@' in line or line.startswith(('proof:', 'rta_native', 'frames=')) or ('TIMEOUT' in line and 'g_simFrame' not in line):
                print(line[:170])
        return 0
    native_args = ['--opt', 'proof-hits=' + os.path.join(cmpmod.BASE, args.name, 'hits.tsv')]
    if args.capture:
        real = os.path.join(PROOF, 'real', args.name)
        os.makedirs(real, exist_ok=True)
        native_args += ['--opt', 'proof-capture=' + real, '--opt', 'proof-want=' + os.path.join(PROOF, 'want.txt'),
                        '--opt', 'proof-per=%d' % args.per]
    out = os.path.join(cmpmod.BASE, args.name)
    os.makedirs(out, exist_ok=True)
    script = script_of(args.name, spec, out)
    for item in args.native_opt:
        native_args += ['--opt', item]
    if args.step == 'native':
        # a script that made the rig write a memory image inside a tick (`ontick 77 dump`,
        # armed by `poke 0x4027ac:s32 77`): the native run writes its image at the same tick
        head, episodes = rigcompare.episodes_of(os.path.join(out, 'boot-rig.tsv'))
        marker = head.index('net')
        wanted, seen = [], set()
        for number, (_level, rows, _again) in enumerate(episodes):
            for t in sorted(rows):
                mark = rows[t][1][marker]
                if mark.isdigit() and int(mark) >= DUMP_MARK and mark not in seen:
                    seen.add(mark)
                    name = 'native-dump-%s.bin' % mark if spec.get('dumps') else 'native-dump.bin'
                    wanted.append('%d:%d:%s' % (number, t, os.path.join(out, name)))
        if wanted:
            native_args += ['--opt', 'proof-dump=' + ','.join(wanted)]
    if args.step == 'native':
        native_args += ['--count-at', '%x=%08x' % (INIT_COUNTER_SITE, init_counter(out))]
    if args.step == 'native' and 'echo @P' in open(script).read():
        script, pokes = replay_pokes(script, out, args.poke_shift)
        native_args += ['--opt', 'proof-pokes=' + pokes]
    cmpmod.setup(args.name, NATIVE, watches=spec.get('watch', DEFAULT_WATCHES), native_args=native_args if args.step == 'native' else (),
                 fix_last_tick=not args.no_last_tick_fix)
    if args.step == 'rig':
        sys.argv = ['rigcompare', 'boot-rig', '--script', script, '--more', '0', '--frames', str(args.frames)]
        return rigcompare.main()
    if args.step == 'native':
        sys.argv = ['rigcompare', 'boot-native', '--script', script, '--more', '0', '--replay']
        return rigcompare.main()
    sys.argv = ['rigcompare', 'boot-compare']
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = rigcompare.main()
    text = buffer.getvalue()
    with open(os.path.join(out, 'result.txt'), 'w') as sink:
        sink.write(text)
    for line in text.splitlines():
        if not line.startswith(('  identical at', '  first common')):
            print(line[:230])
    return code


if __name__ == '__main__':
    sys.exit(main())
