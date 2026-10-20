#!/usr/bin/env python3
"""build.py - build rta_app: the native game in a window, with picture, sound and input.

  python3 tools/recomp/app/build.py            # local/recomp-out/bin/rta_app
  python3 tools/recomp/app/build.py --original # local/recomp-out/bin/rta_app_orig: the game as it is on the disc
  options: --opt -O1|-O2   --qt DIR (default /opt/homebrew/opt/qtbase)
           --pnach FILE --sections FILE   the fix set (defaults below)
           --no-game          do not translate and compile the game first (link what is there)
           --no-translation   interpret VU1 even when a translation of its programs exists
           --as NAME          the program's name in local/recomp-out/bin (default rta_app or
                              rta_app_orig).  A build that is to be checked before it becomes
                              the program people start is made as rta_app_next and moved over
                              rta_app afterwards (mv is atomic; the program finds the workspace
                              from the directory it lies in, so it must be made in bin/)

One program from five parts:
  the translated game   rta_app: translated with the suggested fix set applied - the word
                        patches of patches/SLUS-20973_4028A55F.pnach in the sections named in
                        tools/play-net/sections-suggested.txt, what every other build of the
                        game here runs with (recomp.py --pnach, into local/recomp-out/gen-app;
                        objects in obj-rta_native_fix, and a headless bin/rta_native_fix as a
                        by-product).  rta_app_orig (--original): the shared translation of
                        the unpatched executable (gen, obj-run) - the one that is compared
                        tick for tick with the original in the rig.
  the runtime           tools/recomp/rt/ (runtime, iop, script, host) - as it is now
  the renderer          tools/recomp/render/ (vu1, vif1, gs, renderer, the OpenGL backend,
                        and the VU1 programs translated to C++ when
                        local/recomp-out/gen-vu/vu1_fast.cpp and vu1_translated.cpp exist)
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
sys.path.insert(0, RECOMP)
import genfiles  # noqa: E402  (the translation's own list of files)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')

RENDER_CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp', 'worldfill.cpp']
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
    parser.add_argument('--original', action='store_true', help='the unpatched game: rta_app_orig from the shared translation')
    parser.add_argument('--pnach', default=os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach'))
    parser.add_argument('--sections', default=os.path.join(ROOT, 'tools', 'play-net', 'sections-suggested.txt'))
    parser.add_argument('--no-game', action='store_true')
    parser.add_argument('--no-translation', action='store_true')
    parser.add_argument('--as', dest='as_name', default='')
    parser.add_argument('--extra-pnach', action='append', default=[], help='more word patches for the translation: a proposal under test (app/fp-proposed.pnach)')
    args = parser.parse_args()
    rt = os.path.join(RECOMP, 'rt')
    render = os.path.join(RECOMP, 'render')
    sound = os.path.join(RECOMP, 'sound')
    if args.original:
        args.name, args.gen, args.game_objects = 'rta_app_orig', os.path.join(OUT, 'gen'), os.path.join(OUT, 'obj-run')
        translate, game = [], ['run', '--gen', args.gen]
    else:
        args.name, args.gen, args.game_objects = 'rta_app', os.path.join(OUT, 'gen-app'), os.path.join(OUT, 'obj-rta_native_fix')
        translate = ['--out', args.gen, '--pnach', args.pnach, '--sections', args.sections,
                     '--hle-add', os.path.join(HERE, 'hle-app.txt')]
        # the network (tools/recomp/net, docs/issues/native-online.md): the library entries of
        # hle-online.txt are left to its driver, and the local sign-in patch - a file kept
        # outside the repository - is applied when it is there (nothing of it is printed)
        translate += ['--hle-add', os.path.join(RECOMP, 'net', 'hle-online.txt')]
        signin = os.environ.get('RTA_SIGNIN_PATCH', os.path.join(ROOT, 'local', 'SLUS-20973_4028A55F_signin.pnach'))
        if os.path.isfile(signin):
            translate += ['--extra-pnach', signin]
        for extra in args.extra_pnach:
            translate += ['--extra-pnach', extra]
        game = ['run', '--gen', args.gen, '--name', 'rta_native_fix']
    if not args.no_game:
        result = subprocess.run([sys.executable, os.path.join(RECOMP, 'recomp.py')] + translate, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout[-3000:] + result.stderr[-3000:])
            return result.returncode
        for line in result.stdout.splitlines():
            if line.startswith(('patched', 'warning', 'entangled', 'instructions emitted as rt_unimpl', 'transfer targets')):
                print('recomp: ' + line)
        result = subprocess.run([sys.executable, os.path.join(RECOMP, 'build.py')] + game)
        if result.returncode != 0:
            return result.returncode
    objdir = os.path.join(OUT, 'obj-' + (args.as_name or args.name).replace('rta_', ''))   # a build under another name keeps its own objects
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
    # the VU1 microprograms translated ahead of time (render/vu1_translate.py writes the file
    # into local/recomp-out/gen-vu/; docs/issues/native-render-speed.md)
    fast = os.path.join(OUT, 'gen-vu', 'vu1_fast.cpp')
    jobs.append((fast if os.path.exists(fast) and not args.no_translation else os.path.join(render, 'vu1_fast_none.cpp'), render_flags, 'r_'))
    jobs.append((os.path.join(render, 'backend_gl.cpp'), render_flags + qt_flags, 'r_'))
    jobs.append((os.path.join(render, 'texpack.cpp'), render_flags + qt_flags, 'r_'))
    jobs += [(os.path.join(rt, n), rt_flags, 'rt_') for n in RUNTIME]
    jobs.append((os.path.join(sound, 'sound_rta.cpp'), rt_flags + ['-I', sound], 'rt_'))
    jobs.append((os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'))
    jobs.append((os.path.join(HERE, 'gfx_rt.cpp'), rt_flags + ['-I', HERE], 'a_'))
    # the view modes (fpview.h; docs/issues/native-first-person.md)
    jobs.append((os.path.join(HERE, 'fpview.cpp'), rt_flags + ['-I', HERE], 'a_'))
    # the world for a camera inside it (fpworld.h; docs/issues/native-first-person-world.md)
    jobs.append((os.path.join(HERE, 'fpworld.cpp'), rt_flags + ['-I', HERE, '-I', render], 'a_'))
    # the controls of the look views (plain C++: the Windows program compiles the same file)
    jobs.append((os.path.join(HERE, 'fpcontrols.cpp'), ['-std=c++17', args.opt, '-Wall', '-I', HERE, '-I', rt], 'a_'))
    # the souls-style combat mode (soulscombat.h; docs/issues/native-souls-combat.md): reaches the game's memory and its overlay the frame list
    jobs.append((os.path.join(HERE, 'soulscombat.cpp'), rt_flags + ['-I', HERE, '-I', render], 'a_'))
    jobs.append((os.path.join(HERE, 'look_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', HERE, '-I', rt], 'a_'))
    if not args.original:
        # the films: the library entry points of hle-app.txt, which only this translation leaves open
        jobs.append((os.path.join(HERE, 'film.cpp'), rt_flags + ['-I', HERE], 'a_'))
        # the network: the driver, the one-step online (the emulator build's own file, linked
        # as it is) and its questions on the window
        net = os.path.join(RECOMP, 'net')
        jobs += [(os.path.join(net, n), rt_flags, 'n_') for n in ('netdrv.cpp', 'online.cpp')]
        jobs.append((os.path.join(ROOT, 'tools', 'play-net', 'src', 'RtaOnline.cpp'), rt_flags, 'n_'))
        jobs.append((os.path.join(net, 'online_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', net], 'n_'))
        # a room of our own and the direct launch (tools/recomp/net2, docs/issues/native-rendezvous.md):
        # the session client and its datagrams need nothing of the game; launch.cpp calls into it
        net2 = os.path.join(RECOMP, 'net2')
        plain = ['-std=c++17', args.opt, '-Wall', '-I', net2]
        # (tls.cpp: the link to the service inside TLS, with the system's Network and Security frameworks)
        jobs += [(os.path.join(net2, n), plain, 'n2_') for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp',
                                                                    'tls.cpp', 'cardchars.cpp', 'clicmd.cpp')]
        jobs.append((os.path.join(net2, 'launch.cpp'), rt_flags + ['-I', net2], 'n2_'))
    jobs.append((os.path.join(HERE, 'app_main.cpp'), app_flags + qt_flags, 'a_'))
    jobs.append((os.path.join(HERE, 'pad_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', HERE, '-I', rt], 'a_'))
    jobs.append((os.path.join(HERE, 'present_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', HERE], 'a_'))
    jobs.append((os.path.join(HERE, 'help_mac.mm'), ['-std=c++17', args.opt, '-Wall', '-fobjc-arc', '-I', HERE, '-I', rt], 'a_'))
    # the game's objects are those of the translation's files (genfiles.py), never a listing of
    # the object directory: a stray copy there ("c_003 2.o", as a file synchroniser leaves
    # them) is not one of them and must not be linked a second time
    link = genfiles.objects(args.gen, args.game_objects)
    missing = [p for p in link if not os.path.exists(p)]
    if missing:
        print('the game is not compiled: %s is missing (run without --no-game)' % os.path.relpath(missing[0], ROOT))
        return 1
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
    out = os.path.join(OUT, 'bin', args.as_name or args.name)
    # linked beside its place and moved there: a copy that is running or being started by
    # somebody else never sees a half-written file
    final, out = out, out + '.link%d' % os.getpid()
    frameworks = sum((['-framework', f] for f in ('QtCore', 'QtGui', 'GameController', 'AppKit', 'Foundation', 'CoreVideo', 'CoreGraphics',
                                                     'Metal', 'QuartzCore', 'IOSurface', 'OpenGL', 'Network', 'Security')), [])
    result = subprocess.run(['clang++', '-o', out] + objects + link + ['-F', qtlib] + frameworks + ['-Wl,-rpath,' + qtlib, '-lpthread'],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED\n' + result.stderr[:6000])
        if os.path.exists(out):
            os.remove(out)
        return 1
    os.replace(out, final)
    print('compiled %d of %d files; linked %s' % (len(todo), len(jobs), final))
    return 0


if __name__ == '__main__':
    sys.exit(main())
