#!/usr/bin/env python3
"""build.py - build the renderer's programs.

  python3 tools/recomp/render/build.py replay     # rta_replay: plays a recorded stream
  python3 tools/recomp/render/build.py app        # rta_render: the native game with a window
  options: --opt -O1|-O2   --qt DIR (default /opt/homebrew/opt/qtbase)   --gen DIR   --rt DIR
           --no-translation

The VU1 main program runs translated when local/recomp-out/gen-vu/vu1_translated.cpp exists:
  local/recomp-out/bin/rta_replay <stream> --translate-vu local/recomp-out/gen-vu/vu1_translated.cpp
then build again.

Objects go to local/recomp-out/obj-render/, programs to local/recomp-out/bin/.  Uses the
compiler and the Qt 6 already on the machine; nothing is downloaded.  `app` links the
translated game's objects from local/recomp-out/obj-run/ (python3 tools/recomp/build.py run
makes them) and compiles the runtime's sources from tools/recomp/rt/ itself.
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')

CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']
GL = ['backend_gl.cpp']


def includes_of(source, dirs, seen=None):
    """The headers a source file includes with quotes, followed through, found in `dirs`."""
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
    parser.add_argument('what', choices=['replay', 'app'])
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--qt', default='/opt/homebrew/opt/qtbase')
    parser.add_argument('--gen', default=os.path.join(OUT, 'gen'))
    parser.add_argument('--rt', default=os.path.join(ROOT, 'tools', 'recomp', 'rt'))
    parser.add_argument('--no-translation', action='store_true', help='interpret VU1 even when a translation exists')
    parser.add_argument('--game-objects', default=os.path.join(OUT, 'obj-run'))
    args = parser.parse_args()
    objdir = os.path.join(OUT, 'obj-render')
    os.makedirs(objdir, exist_ok=True)
    os.makedirs(os.path.join(OUT, 'bin'), exist_ok=True)
    qtlib = os.path.join(args.qt, 'lib')
    qt_flags = ['-F', qtlib] + sum((['-I', os.path.join(qtlib, m + '.framework', 'Headers')] for m in ('QtCore', 'QtGui')), [])
    base = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math', '-Wall',
            '-Wno-unused-function', '-I', HERE]
    jobs = [(os.path.join(HERE, n), base, 'r_') for n in CORE]
    # the VU1 main program translated to C++ (rta_replay <stream> --translate-vu writes it;
    # derived from the game, so it lives under local/), or nothing: then all is interpreted
    translation = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
    if os.path.exists(translation) and not args.no_translation:
        jobs.append((translation, base, 'r_'))
    else:
        jobs.append((os.path.join(HERE, 'vu1_none.cpp'), base, 'r_'))
    jobs += [(os.path.join(HERE, n), base + qt_flags, 'r_') for n in GL]
    link = []
    if args.what == 'replay':
        jobs.append((os.path.join(HERE, 'replay_main.cpp'), base + qt_flags, 'r_'))
        program = 'rta_replay'
    else:
        rt_flags = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math',
                    '-I', args.rt, '-I', args.gen]
        jobs.append((os.path.join(HERE, 'app_main.cpp'), base + qt_flags + ['-I', args.rt, '-I', args.gen, '-w'], 'r_'))
        for n in sorted(os.listdir(args.rt)):
            if n.endswith('.cpp') and n not in ('main_headless.cpp', 'test_driver.cpp', 'host_win32.cpp', 'snap_main.cpp'):
                jobs.append((os.path.join(args.rt, n), rt_flags, 'rt_'))
        link += [os.path.join(args.game_objects, n) for n in sorted(os.listdir(args.game_objects))
                 if n.endswith('.o') and (n.startswith('c_') or n in ('table.o', 'hle_weak.o'))]
        program = 'rta_render'
    objects = []
    todo = []
    for source, flags, prefix in jobs:
        target = os.path.join(objdir, prefix + os.path.basename(source)[:-4] + '.o')
        objects.append(target)
        stamp = target + '.flags'
        if newer(source, target, includes_of(source, [HERE, args.rt])) or not os.path.exists(stamp) or open(stamp).read() != ' '.join(flags):
            todo.append((source, flags, target, stamp))

    def compile_one(job):
        source, flags, target, stamp = job
        result = subprocess.run(['clang++'] + flags + ['-c', source, '-o', target], capture_output=True, text=True)
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
    out = os.path.join(OUT, 'bin', program)
    result = subprocess.run(['clang++', '-o', out] + objects + link + ['-F', qtlib, '-framework', 'QtCore', '-framework', 'QtGui',
                             '-Wl,-rpath,' + qtlib, '-lpthread'], capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED\n' + result.stderr[:6000])
        return 1
    print('linked %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
