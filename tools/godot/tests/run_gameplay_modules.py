"""Compile/run production cinematic and party-scaling wrappers with authored memory and callbacks.

python tools/godot/tests/run_gameplay_modules.py --cxx COMPILER --out PRIVATE_NEW_DIRECTORY
No game executable, generated translation, disc, engine or display is needed.
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
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    out = args.out.resolve()
    if out.is_relative_to(repo) and not out.is_relative_to(repo / 'local'):
        parser.error('Keep generated binaries under ignored local/ or outside the repository.')
    out.mkdir(parents=True, exist_ok=False)
    # Only these independently authored declarations are needed by the two production HLE wrappers.
    (out / 'funcs.h').write_text('struct Ctx; void orig_00199944(Ctx*); void orig_0010a620(Ctx*);\n')
    app, rt = repo / 'tools/recomp/app', repo / 'tools/recomp/rt'
    binary = out / ('gameplay_modules_test.exe' if sys.platform == 'win32' else 'gameplay_modules_test')
    command = [args.cxx, '-std=c++17', '-O2', '-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math',
               '-I', str(app), '-I', str(rt), '-I', str(out), str(here / 'gameplay_modules_test.cpp')]
    command += [str(app / name) for name in ('cinematic.cpp', 'cinematic_hle.cpp', 'partyscale.cpp', 'partyscale_hle.cpp')]
    command += ['-o', str(binary), '-pthread']
    if sys.platform == 'win32':
        command += ['-static']
    build = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'compile.log').write_text(build.stdout + build.stderr)
    report = {'compile_command': command, 'compile_exit': build.returncode,
              'scope': 'real production wrappers; authored guest state and original callbacks, no gameplay qualification'}
    if build.returncode == 0:
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        (out / 'runtime.log').write_text(run.stdout + run.stderr)
        report.update(exit=run.returncode, output=run.stdout, passed=run.returncode == 0)
    else:
        report['passed'] = False
        print(build.stderr)
    (out / 'run-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
