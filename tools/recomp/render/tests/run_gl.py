"""Run authored Windows OpenGL target-allocation checks without any game inputs.

Requires a Windows driver supporting OpenGL4.1 and four samples. The fixture
queries driver-selected storage and compares retained colour and depth occlusion.
It also exercises a simulated legal two-to-four sample round-up.
It deliberately injects one unsupported-framebuffer response to check fallback.
Default outputs are ignored local files; --out may select an external private folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', required=True, help='Windows C++17 compiler executable')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This context fixture uses Windows WGL; use the CPU runner on other platforms.')
    here = Path(__file__).resolve().parent
    repo = here.parents[3]
    out = (args.out or repo / 'local/gl-target-tests').resolve()
    try:
        relative = out.relative_to(repo)
    except ValueError:
        pass
    else:
        if not relative.parts or relative.parts[0] != 'local':
            parser.error('--out inside the checkout must be under ignored local/')
    out.mkdir(parents=True, exist_ok=True)
    render = here.parent
    win = render.parent / 'app/win'
    sources = [render / 'backend_gl.cpp', render / 'texpack.cpp',
               win / 'wgl.cpp', here / 'gl_target_samples_test.cpp']
    executable = out / 'gl_target_samples_test.exe'
    command = [args.cxx, '-std=c++17', '-O2', '-fno-strict-aliasing',
               '-ffp-contract=off', '-frounding-math', '-DNOMINMAX', '-DRTA_NO_QIMAGE', '-static',
               '-I', str(render), '-I', str(win)]
    command += [str(p) for p in sources]
    command += ['-o', str(executable), '-lopengl32', '-lgdi32', '-luser32', '-lpthread']
    report = {'scope': 'Authored actual-GL sample allocation/image preservation; no game or physical control qualification',
              'sources_sha256': {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'phases': []}
    for phase, argv, timeout in [('compile', command, 120),
                                  ('test', [str(executable)], 30),
                                  ('test-rounded-samples', [str(executable), '--round-two-to-four'], 30)]:
        result = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                                timeout=timeout)
        report['phases'].append({'phase': phase, 'argv': argv, 'exit': result.returncode,
                                 'stdout': result.stdout, 'stderr': result.stderr})
        (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
