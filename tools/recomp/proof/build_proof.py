#!/usr/bin/env python3
"""build_proof.py - the programs of tools/recomp/proof, built in directories of their own.

  python3 tools/recomp/proof/build_proof.py translate   # recomp.py -> gen-proof-src, instrument.py -> gen-proof
  python3 tools/recomp/proof/build_proof.py runtime     # bin/rta_proof: the headless runtime with the entry hook
  python3 tools/recomp/proof/build_proof.py driver      # bin/proof_driver: recorded states through the translation
  options: --jobs N

  options: --jobs N, --snap DIR, --define NAME (repeatable)

Since 2026-10-13 everything is built from a SNAPSHOT of the translator and the runtime
(`snapshot` copies tools/recomp/{rt,recomp.py,build.py,hle.txt,entries.txt} to
local/recomp-out/proof/snap/recomp; the runtime's keeper changes tools/recomp/rt while
proof runs are under way, and a proof must name the sources it was built from).  The
snapshot's build.py is used as a module with its directories pointed at the snapshot and
at local/recomp-out/proof/build: generated code in build/gen-src (plain) and build/gen
(with the hook), objects in build/obj-*, programs in build/bin (rta_proof, proof_driver).
Nothing under tools/recomp/rt is changed.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')


def run(command):
    print('+ ' + ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) else c for c in command), flush=True)
    return subprocess.run(['nice', '-n', '15'] + command, cwd=ROOT).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('what', choices=('snapshot', 'translate', 'runtime', 'driver'))
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--snap', default=os.path.join(OUT, 'proof', 'snap', 'recomp'))
    parser.add_argument('--define', action='append', default=[])
    parser.add_argument('--name', help='runtime: another program name (default rta_proof)')
    args = parser.parse_args()
    build = os.path.join(OUT, 'proof', 'build')
    plain, hooked = os.path.join(build, 'gen-src'), os.path.join(build, 'gen')
    py = sys.executable
    snap = os.path.abspath(args.snap)
    if args.what == 'snapshot':
        import shutil
        if os.path.exists(snap):
            raise SystemExit('%s exists; a snapshot is taken once (move it away to take another)' % snap)
        os.makedirs(snap)
        shutil.copytree(os.path.join(RECOMP, 'rt'), os.path.join(snap, 'rt'))
        for name in ('recomp.py', 'build.py', 'hle.txt', 'entries.txt'):
            shutil.copy2(os.path.join(RECOMP, name), snap)
        return 0
    # the snapshot's build.py, told where it is and where to write
    shim = ('import sys, os; sys.path.insert(0, %r); import build; build.HERE = %r; build.OUT = %r; '
            'sys.argv = ["build.py"] + sys.argv[1:]; sys.exit(build.main())' % (snap, snap, build))
    defines = [x for d in args.define for x in ('--define', d)]
    if args.what == 'translate':
        return run([py, os.path.join(snap, 'recomp.py'), '--out', plain, '--hle', os.path.join(snap, 'hle.txt'),
                    '--entries', os.path.join(snap, 'entries.txt'), '--elf', os.path.join(ROOT, 'SLUS_209.73'),
                    '--funcs', os.path.join(ROOT, 'ghidra_funcs.tsv')]) or \
            run([py, os.path.join(HERE, 'instrument.py'), '--gen', plain, '--out', hooked])
    if args.what == 'runtime':
        return run([py, '-c', shim, 'run', '--gen', hooked, '--name', args.name or 'rta_proof', '--jobs', str(args.jobs),
                    '--extra', os.path.join(HERE, 'proof_rt.cpp')] + defines)
    # the driver: the test build of the plain translation, with proof_driver.cpp in place of rt/test_driver.cpp
    code = run([py, '-c', shim, 'test', '--gen', plain, '--name', 'proof_test', '--jobs', str(args.jobs)] + defines)
    if code:
        return code
    objdir = os.path.join(build, 'obj-proof_test')
    flags = open(os.path.join(objdir, 'flags.txt')).read().split()
    target = os.path.join(objdir, 'proof_driver.o')
    code = run(['clang++'] + flags + ['-c', os.path.join(HERE, 'proof_driver.cpp'), '-o', target])
    if code:
        return code
    objects = [os.path.join(objdir, n) for n in sorted(os.listdir(objdir)) if n.endswith('.o') and not n.startswith('rt_') and n != 'proof_driver.o']
    return run(['clang++', '-o', os.path.join(build, 'bin', 'proof_driver'), target] + objects + ['-lpthread'])


if __name__ == '__main__':
    sys.exit(main())
