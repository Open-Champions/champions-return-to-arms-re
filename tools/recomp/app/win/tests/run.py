#!/usr/bin/env python3
"""Build and run the native Windows input regressions; no game inputs are needed.

From the repository root, on Windows:
  python tools/recomp/app/win/tests/run.py --cxx C:/toolchains/bin/x86_64-w64-mingw32-clang++.exe --out C:/private/input-tests

The default output is ignored local/win-input-tests. Nothing is installed.
The rumble test uses fake XInput callbacks and cannot drive a physical motor.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent
ROOT = APP.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', required=True, help='Native Windows MinGW clang++ or g++')
    parser.add_argument('--out', type=Path, default=ROOT / 'local' / 'win-input-tests',
                        help='Private output directory; inside this repository, use local/')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Run this native executable test on Windows.')
    compiler = shutil.which(args.cxx)
    if not compiler:
        parser.error('The selected compiler was not found: ' + args.cxx)
    out = args.out.expanduser().resolve()
    local = ROOT / 'local'
    if out == ROOT or (ROOT in out.parents and out != local and local not in out.parents):
        parser.error('Keep private build outputs under local/ or outside the repository.')
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for name in ('input_state_test', 'pad_rumble_test', 'pad_mapping_test'):
        exe = out / (name + '.exe')
        command = [compiler, '-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off', '-static',
                   '-I', str(APP.parent / 'rt'), '-I', str(APP),
                   str(HERE / (name + '.cpp')), '-o', str(exe), '-luser32', '-lkernel32']
        report = {'name': name, 'compile_command': command, 'run_command': [str(exe)]}
        try:
            build = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (out / (name + '.compile.txt')).write_text(build.stdout + build.stderr, encoding='utf-8')
            report['compile_exit'] = build.returncode
            if build.returncode == 0:
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
                (out / (name + '.txt')).write_text(run.stdout + run.stderr, encoding='utf-8')
                report['run_exit'] = run.returncode
                print(run.stdout + run.stderr, end='')
            else:
                print(build.stdout + build.stderr, end='')
        except (OSError, subprocess.TimeoutExpired) as error:
            report['error'] = str(error)
        reports.append(report)
    (out / 'input-test-results.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    return int(any(report.get('compile_exit') != 0 or report.get('run_exit') != 0 for report in reports))


if __name__ == '__main__':
    raise SystemExit(main())
