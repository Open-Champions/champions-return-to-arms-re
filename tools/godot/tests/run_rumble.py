"""Compile/run the production rumble handoff with authored commands and racing callbacks.

python tools/godot/tests/run_rumble.py --cxx COMPILER --out PRIVATE_NEW_DIRECTORY
No disc, game translation, Godot editor, display or physical controller is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    out = args.out.resolve()
    if out.is_relative_to(repo) and not out.is_relative_to(repo / 'local'):
        parser.error('Keep generated binaries under ignored local/ or outside the repository.')
    out.mkdir(parents=True, exist_ok=False)
    suffix = '.exe' if sys.platform == 'win32' else ''
    shared_suffix = '.dll' if sys.platform == 'win32' else '.so'
    binary = out / ('rumble_state_test' + suffix)
    loader = out / ('rumble_loader_test' + suffix)
    older, modern = out / ('older' + shared_suffix), out / ('modern' + shared_suffix)
    flags = [args.cxx, '-std=c++17', '-O2', '-pthread']
    static = ['-static'] if sys.platform == 'win32' else []
    include = ['-I', str(here.parent / 'lib')]
    commands = [
        flags + [str(here / 'rumble_state_test.cpp'), '-o', str(binary)] + static,
        flags + ['-shared', '-fPIC', str(here / 'rumble_api_stub.cpp'), '-o', str(older)] + static,
        flags + ['-shared', '-fPIC', '-DTEST_WITH_RUMBLE', str(here / 'rumble_api_stub.cpp'), '-o', str(modern)] + static,
        flags + include + [str(here / 'rumble_loader_test.cpp'), '-o', str(loader)] + static + ([] if sys.platform == 'win32' else ['-ldl']),
    ]
    report = {'scope': 'production handoff and optional-symbol loader; authored commands/ABI stubs; no gameplay or physical vibration qualification',
              'builds': [], 'runs': [], 'passed': True}
    for index, command in enumerate(commands):
        build = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (out / ('compile-%d.log' % index)).write_text(build.stdout + build.stderr)
        report['builds'].append({'command': command, 'exit': build.returncode})
        if build.returncode != 0:
            report['passed'] = False
            print(build.stderr)
            break
    if report['passed']:
        for index, command in enumerate([[str(binary)], [str(loader), str(older), str(modern)]]):
            run = subprocess.run(command, capture_output=True, text=True, timeout=30)
            (out / ('runtime-%d.log' % index)).write_text(run.stdout + run.stderr)
            report['runs'].append({'command': command, 'exit': run.returncode, 'output': run.stdout})
            report['passed'] &= run.returncode == 0
        report['sha256'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (binary, loader, older, modern)}
    (out / 'run-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
