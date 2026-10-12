#!/usr/bin/env python3
"""build_proof.py - the programs of tools/recomp/proof, built in directories of their own.

  python3 tools/recomp/proof/build_proof.py translate   # recomp.py -> gen-proof-src, instrument.py -> gen-proof
  python3 tools/recomp/proof/build_proof.py runtime     # bin/rta_proof: the headless runtime with the entry hook
  python3 tools/recomp/proof/build_proof.py driver      # bin/proof_driver: recorded states through the translation
  options: --jobs N

Everything is compiled by tools/recomp/build.py from the runtime's sources as they are;
nothing under tools/recomp/rt is changed.  Objects: local/recomp-out/obj-rta_proof and
obj-proof_test; generated code: local/recomp-out/gen-proof-src (plain) and gen-proof
(with the hook).
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
    parser.add_argument('what', choices=('translate', 'runtime', 'driver'))
    parser.add_argument('--jobs', type=int, default=6)
    args = parser.parse_args()
    plain, hooked = os.path.join(OUT, 'gen-proof-src'), os.path.join(OUT, 'gen-proof')
    py = sys.executable
    if args.what == 'translate':
        return run([py, os.path.join(RECOMP, 'recomp.py'), '--out', plain]) or run([py, os.path.join(HERE, 'instrument.py'), '--gen', plain, '--out', hooked])
    if args.what == 'runtime':
        return run([py, os.path.join(RECOMP, 'build.py'), 'run', '--gen', hooked, '--name', 'rta_proof', '--jobs', str(args.jobs),
                    '--extra', os.path.join(HERE, 'proof_rt.cpp')])
    # the driver: the test build of the plain translation, with proof_driver.cpp in place of rt/test_driver.cpp
    code = run([py, os.path.join(RECOMP, 'build.py'), 'test', '--gen', plain, '--name', 'proof_test', '--jobs', str(args.jobs)])
    if code:
        return code
    objdir = os.path.join(OUT, 'obj-proof_test')
    flags = open(os.path.join(objdir, 'flags.txt')).read().split()
    target = os.path.join(objdir, 'proof_driver.o')
    code = run(['clang++'] + flags + ['-c', os.path.join(HERE, 'proof_driver.cpp'), '-o', target])
    if code:
        return code
    objects = [os.path.join(objdir, n) for n in sorted(os.listdir(objdir)) if n.endswith('.o') and not n.startswith('rt_') and n != 'proof_driver.o']
    return run(['clang++', '-o', os.path.join(OUT, 'bin', 'proof_driver'), target] + objects + ['-lpthread'])


if __name__ == '__main__':
    sys.exit(main())
