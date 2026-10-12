#!/usr/bin/env python3
"""standin_compare.py - the x86-64 build of the game against the arm64 build, and both against the rig.

  python3 tools/recomp/app/win/standin_compare.py [--script FILE.rig] [--dump-tick N ...]

A Windows program cannot be run on the Mac; the same sources built for macOS x86-64 can
(under Rosetta).  build_win.py --standin builds local/recomp-out/win/standin/rta_native_x64
and, from the same sources at the same moment, rta_native_arm64.  This runs each of them
exactly as `rigcompare.py boot-native --replay` runs the native build - the controller
bytes of the rig's log, tick for tick, the rig's session seeds - but into its own
directory (win/standin/rig-x64, rig-arm64; the shared local/recomp-out/rig is only read:
boot-rig.tsv and boot-rig-breaks.log are copied from it), then

  1. compares the two tick logs byte for byte (every watch column at every logged frame),
  2. compares the memory images written at the --dump-tick ticks byte for byte,
  3. runs `rigcompare.py boot-compare` on each: the comparison with the original in the rig.

Needs RTA_DISC and a rig log (rigcompare.py boot-rig) for the same script.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(os.path.dirname(RECOMP))
STANDIN = os.path.join(ROOT, 'local', 'recomp-out', 'win', 'standin')
RIG = os.path.join(ROOT, 'local', 'recomp-out', 'rig')

RUNNER = '''
import sys
sys.path.insert(0, %(recomp)r)
import rigcompare
rigcompare.OUT = %(out)r
sys.argv = ['rigcompare.py'] + %(argv)r
sys.exit(rigcompare.main())
'''


def rigcompare(out, argv, binary=None):
    env = dict(os.environ)
    if binary:
        env['RTA_NATIVE'] = binary
    code = RUNNER % {'recomp': RECOMP, 'out': out, 'argv': argv}
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, cwd=ROOT)
    return done.stdout + done.stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--script', default=os.path.join(ROOT, 'local', 'recomp-out', 'fight3.rig'))
    parser.add_argument('--dump-tick', type=int, action='append', default=[])
    parser.add_argument('--only-compare', action='store_true', help='do not run the two builds again')
    args = parser.parse_args()
    ticks = args.dump_tick or [300, 3900]
    outs = {}
    for arch in ('arm64', 'x64'):
        binary = os.path.join(STANDIN, 'rta_native_' + arch)
        out = outs[arch] = os.path.join(STANDIN, 'rig-' + arch)
        if not os.path.exists(binary):
            sys.exit('no %s: run build_win.py --standin' % binary)
        if args.only_compare:
            continue
        os.makedirs(out, exist_ok=True)
        for name in ('boot-rig.tsv', 'boot-rig-breaks.log'):
            shutil.copyfile(os.path.join(RIG, name), os.path.join(out, name))
        argv = ['boot-native', '--script', args.script, '--replay'] + sum((['--dump-tick', str(t)] for t in ticks), [])
        text = rigcompare(out, argv, binary)
        print('== %s: boot-native\n%s' % (arch, '\n'.join(text.strip().splitlines()[-4:])))
    a, b = (os.path.join(outs[arch], 'boot-native.tsv') for arch in ('arm64', 'x64'))
    la, lb = open(a, 'rb').read(), open(b, 'rb').read()
    rows = la.count(b'\n')
    if la == lb:
        print('tick logs: identical, %d rows, %d bytes' % (rows, len(la)))
    else:
        ra, rb = la.split(b'\n'), lb.split(b'\n')
        first = next((i for i, (x, y) in enumerate(zip(ra, rb)) if x != y), min(len(ra), len(rb)))
        print('tick logs DIFFER: %d and %d rows, first differing row %d' % (len(ra) - 1, len(rb) - 1, first))
        if first < min(len(ra), len(rb)):
            header = ra[0].split(b'\t')
            cols = [header[i].decode() for i, (x, y) in enumerate(zip(ra[first].split(b'\t'), rb[first].split(b'\t'))) if x != y and i < len(header)]
            print('  columns that differ there: ' + ', '.join(cols))
    for tick in ticks:
        pa, pb = (os.path.join(outs[arch], 'boot-native-tick%d.bin' % tick) for arch in ('arm64', 'x64'))
        if not (os.path.exists(pa) and os.path.exists(pb)):
            print('memory at tick %d: not written by both (%s, %s)' % (tick, os.path.exists(pa), os.path.exists(pb)))
            continue
        da, db = open(pa, 'rb').read(), open(pb, 'rb').read()
        if da == db:
            print('memory at tick %d: identical, %d bytes' % (tick, len(da)))
        else:
            diff = [i for i in range(0, min(len(da), len(db)), 4) if da[i:i + 4] != db[i:i + 4]]
            print('memory at tick %d DIFFERS in %d words; first at %s' % (tick, len(diff), ', '.join('0x%x' % i for i in diff[:12])))
    for arch in ('arm64', 'x64'):
        text = rigcompare(outs[arch], ['boot-compare'])
        open(os.path.join(outs[arch], 'boot-compare.txt'), 'w').write(text)
        print('== %s: boot-compare (whole text in %s)' % (arch, os.path.relpath(os.path.join(outs[arch], 'boot-compare.txt'), ROOT)))
    ca, cb = (open(os.path.join(outs[arch], 'boot-compare.txt')).read() for arch in ('arm64', 'x64'))
    print('boot-compare texts of the two: %s' % ('identical' if ca == cb else 'DIFFERENT'))
    print(cb[-3000:])
    return 0


if __name__ == '__main__':
    sys.exit(main())
