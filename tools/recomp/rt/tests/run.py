#!/usr/bin/env python3
"""Synthetic kernel regression; no game assets, window or audio device.

python3 tools/recomp/rt/tests/run.py [--baseline REV] [--sanitize]

The optional baseline is read with git show, without changing the worktree. Valid
execution must produce identical RAM and scheduling traces. The injected bad link
must fault in the baseline and be diagnosed in the current runtime.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rt = here.parent
    repo = rt.parents[2]
    with tempfile.TemporaryDirectory(prefix='rta-g11-kernel-') as directory:
        work = Path(directory)

        def build(name, source=None):
            exe = work / name
            command = ['clang++', '-std=c++17', '-O1' if args.sanitize else '-O2', '-g', '-fno-strict-aliasing',
                       '-fwrapv', '-ffp-contract=off', '-frounding-math', '-pthread',
                       '-I', str(here), '-I', str(rt)]
            if args.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            if source:
                command += ['-DRTA_RUNTIME_SOURCE="' + str(source) + '"']
            command += [str(here / 'kernel.cpp')]
            command += [str(rt / file) for file in ('iop.cpp', 'script.cpp', 'host_posix.cpp', 'sound_null.cpp')]
            subprocess.run(command + ['-o', str(exe)], check=True, timeout=90)
            return exe

        def run(exe, case):
            result = subprocess.run([str(exe), case, str(work / (exe.name + '.ram')),
                                     str(work / 'card')], capture_output=True, text=True, timeout=10)
            return result

        current = build('current')
        for case in ('valid', 'last-slot', 'bad-head', 'bad-next', 'cycle', 'bad-pick', 'bad-link', 'bad-rotate'):
            result = run(current, case)
            expected = 0 if case in ('valid', 'last-slot') else 3
            assert result.returncode == expected, (case, result.returncode, result.stdout, result.stderr)
            if expected:
                assert 'invalid thread ready queue:' in result.stderr, (case, result.stderr)
            assert 'runtime error:' not in result.stderr and 'ERROR: AddressSanitizer' not in result.stderr, result.stderr
            print(case + ': PASS')
        current_ram = (work / 'current.ram').read_bytes()
        print('RAM and scheduling trace sha256:', hashlib.sha256(current_ram).hexdigest())
        if args.baseline:
            source = work / 'runtime-baseline.cpp'
            source.write_bytes(subprocess.check_output(
                ['git', 'show', args.baseline + ':tools/recomp/rt/runtime.cpp'], cwd=repo))
            baseline = build('baseline', source)
            result = run(baseline, 'valid')
            assert result.returncode == 0, (result.stdout, result.stderr)
            assert 'runtime error:' not in result.stderr and 'ERROR: AddressSanitizer' not in result.stderr, result.stderr
            assert (work / 'baseline.ram').read_bytes() == current_ram, 'valid execution changed'
            print('baseline valid execution: byte-identical RAM and scheduling trace')
            result = run(baseline, 'bad-next')
            assert result.returncode != 0, 'baseline did not reproduce the bad-link fault'
            if args.sanitize:
                assert 'ERROR: AddressSanitizer' in result.stderr, result.stderr
            else:
                assert result.returncode < 0, (result.returncode, result.stderr)
            print('baseline injected bad link: reproduced memory fault')


if __name__ == '__main__':
    main()
