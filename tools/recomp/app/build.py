#!/usr/bin/env python3
"""build.py - build rta_app: the native game in a window, with picture, sound and input.

  python3 tools/recomp/app/build.py            # local/recomp-out/bin/rta_app
  options: --opt -O1|-O2   --qt DIR (default /opt/homebrew/opt/qtbase)   --gen DIR
           --no-game          do not bring the translated game's objects up to date first
           --no-translation   interpret VU1 even when a translation of its main program exists
           --name NAME        program name (default rta_app; objects in obj-<NAME>)

One program from five parts:
  the translated game   objects from local/recomp-out/obj-run (python3 tools/recomp/build.py
                        run makes them; this script runs that first unless --no-game)
  the runtime           tools/recomp/rt/ (runtime, iop, script, host) - as it is now
  the renderer          tools/recomp/render/ (vu1, vif1, gs, renderer, the OpenGL backend,
                        and the VU1 main program translated to C++ when
                        local/recomp-out/gen-vu/vu1_translated.cpp exists)
  the sound library     tools/recomp/sound/sound_rta.cpp in place of rt/sound_null.cpp
  the application       this directory: window, pacing, keyboard, game controller

Uses the compiler and the Qt 6 already on the machine; nothing is downloaded.  Everything
written goes to local/recomp-out/ (obj-app/, bin/).
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')

RENDER_CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']
RUNTIME = ['runtime.cpp', 'iop.cpp', 'script.cpp', 'host_posix.cpp']


def includes_of(source, dirs, seen=None):
    """The headers (and .cpp files) a source includes with quotes, followed through."""
    seen = set() if seen is None else seen
    try:
        text = open(source).read()
    except OSError:
        return []
    for name in re.findall(r'^#include "([^"]+)"', text, re.M):
        for d in [os.path.dirname(source)] + dirs:
            path = os.path.normpath(os.path.join(d, name))
            if os.path.exists(path):
                if path not in seen:
                    seen.add(path)
                    includes_of(path, dirs, seen)
                break
    return sorted(seen)


def newer(source, target, extra):
    if not os.path.exists(target):
        return True
    stamp = os.path.getmtime(target)
    return any(os.path.getmtime(p) > stamp for p in [source] + extra)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--qt', default='/opt/homebrew/opt/qtbase')
    parser.add_argument('--gen', default=os.path.join(OUT, 'gen'))
    parser.add_argument('--game-objects', default=os.path.join(OUT, 'obj-run'))
    parser.add_argument('--no-game', action='store_true')
    parser.add_argument('--no-translation', action='store_true')
    parser.add_argument('--name', default='rta_app')
    args = parser.parse_args()
    rt = os.path.join(RECOMP, 'rt')
    render = os.path.join(RECOMP, 'render')
    sound = os.path.join(RECOMP, 'sound')
    if not args.no_game:
        result = subprocess.run([sys.executable, os.path.join(RECOMP, 'build.py'), 'run', '--gen', args.gen])
        if result.returncode != 0:
            return result.returncode
    objdir = os.path.join(OUT, 'obj-' + args.name.replace('rta_', ''))
    os.makedirs(objdir, exist_ok=True)
    os.makedirs(os.path.join(OUT, 'bin'), exist_ok=True)
    qtlib = os.path.join(args.qt, 'lib')
    qt_flags = ['-F', qtlib] + sum((['-I', os.path.join(qtlib, m + '.framework', 'Headers')] for m in ('QtCore', 'QtGui')), [])
    render_flags = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math', '-Wall',
                    '-Wno-unused-function', '-I', render]
    rt_flags = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math',
                '-I', rt, '-I', args.gen]
    app_flags = ['-std=c++17', args.opt, '-Wall', '-Wno-unused-function', '-I', HERE, '-I', render, '-I', rt]
    jobs = [(os.path.join(render, n), render_flags, 'r_') for n in RENDER_CORE]
    translation = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
    if os.path.exists(translation) and not args.no_translation:
        jobs.append((translation, render_flags, 'r_'))
    else:
        jobs.append((os.path.join(render, 'vu1_none.cpp'), render_flags, 'r_'))
    jobs.append((os.path.join(render, 'backend_gl.cpp'), render_flags + qt_flags, 'r_'))
    jobs += [(os.path.join(rt, n), rt_flags, 'rt_') for n in RUNTIME]
    jobs.append((os.path.join(sound, 'sound_rta.cpp'), rt_flags + ['-I', sound], 'rt_'))
    jobs.append((os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'))
    jobs.append((os.path.join(HERE, 'app_main.cpp'), app_flags + qt_flags, 'a_'))
    jobs.append((os.path.join(HERE, 'pad_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', HERE, '-I', rt], 'a_'))
    link = [os.path.join(args.game_objects, n) for n in sorted(os.listdir(args.game_objects))
            if n.endswith('.o') and (n.startswith('c_') or n in ('table.o', 'hle_weak.o'))]
    objects = []
    todo = []
    for source, flags, prefix in jobs:
        target = os.path.join(objdir, prefix + os.path.splitext(os.path.basename(source))[0] + '.o')
        objects.append(target)
        stamp = target + '.flags'
        if newer(source, target, includes_of(source, [HERE, render, rt, sound])) or not os.path.exists(stamp) \
                or open(stamp).read() != ' '.join(flags):
            todo.append((source, flags, target, stamp))

    def compile_one(job):
        source, flags, target, stamp = job
        result = subprocess.run(['nice', '-n', '10', 'clang++'] + flags + ['-c', source, '-o', target], capture_output=True, text=True)
        if result.returncode == 0:
            open(stamp, 'w').write(' '.join(flags))
        return source, result.returncode, result.stderr

    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for source, code, err in pool.map(compile_one, todo):
            if code != 0:
                failed = True
                print('FAILED %s\n%s' % (source, err[:6000]))
            elif err.strip():
                print(err[:3000])
    if failed:
        return 1
    out = os.path.join(OUT, 'bin', args.name)
    frameworks = sum((['-framework', f] for f in ('QtCore', 'QtGui', 'GameController', 'AppKit', 'Foundation')), [])
    result = subprocess.run(['clang++', '-o', out] + objects + link + ['-F', qtlib] + frameworks + ['-Wl,-rpath,' + qtlib, '-lpthread'],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED\n' + result.stderr[:6000])
        return 1
    print('compiled %d of %d files; linked %s' % (len(todo), len(jobs), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
