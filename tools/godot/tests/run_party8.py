"""Run production Windows party8 relocation and opt-in trap against authored memory.

python tools/godot/tests/run_party8.py --cxx COMPILER --out PRIVATE_NEW_DIRECTORY
No game, translation or display is needed; each exception probe runs in a bounded child.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This fixture exercises the Windows adapter; use a Windows host.')
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    out = args.out.resolve()
    if out.is_relative_to(repo) and not out.is_relative_to(repo / 'local'):
        parser.error('Keep binaries/logs under ignored local/ or outside the repository.')
    out.mkdir(parents=True, exist_ok=False)
    app, rt, render = (repo / 'tools/recomp' / p for p in ['app', 'rt', 'render'])
    binary = out / 'party8_windows_test.exe'
    command = [args.cxx, '-std=c++17', '-O2', '-DRAM_SIZE=0x04000000u', '-DRECOMP_RELOC_DYN',
               '-I', str(app), '-I', str(rt), '-I', str(render),
               str(here / 'party8_windows_test.cpp'), str(app / 'party8.cpp'),
               '-o', str(binary), '-static', '-pthread']
    built = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'compile.log').write_text(built.stdout + built.stderr)
    report = {'compile_command': command, 'compile_exit': built.returncode, 'cases': [],
              'scope': 'authored tables only; production move, dynamic helpers and Win32 diagnostics'}
    if built.returncode == 0:
        for mode, expected in [('normal', 0), ('trap', 70), ('unrelated', 0)]:
            try:
                run = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
                log = run.stdout + run.stderr
                passed = run.returncode == expected and 'FAIL ' not in log
                if mode == 'trap':
                    passed &= 'party8: TRAP:' in log and 'TRAP_WAS_MISSED' not in log
                if mode == 'unrelated':
                    passed &= 'UNRELATED_HANDLER_REACHED' in log and 'party8: TRAP:' not in log
                result = {'mode': mode, 'exit': run.returncode, 'timeout': False, 'passed': passed}
            except subprocess.TimeoutExpired as error:
                log = str(error)
                result = {'mode': mode, 'exit': None, 'timeout': True, 'passed': False}
            (out / (mode + '.log')).write_text(log)
            report['cases'].append(result)
    else:
        print(built.stderr)
    report['passed'] = built.returncode == 0 and all(c['passed'] for c in report['cases'])
    (out / 'run-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
