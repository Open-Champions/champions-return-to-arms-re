#!/usr/bin/env python3
"""build_linux.py - build the native game for Linux, x86-64 and aarch64.

  python3 tools/recomp/app/build_linux.py                 # on Linux: this machine's architecture
  python3 tools/recomp/app/build_linux.py --docker both   # on a Mac: the same inside an Ubuntu 24.04
                                                          # container (colima profile `rta`), for
                                                          # arm64 (aarch64) and amd64 (x86-64, Rosetta)
  options: --docker arm64|amd64|both   --context NAME (docker context; default colima-rta)
           --original     also the unpatched game (rta_app_orig: the program of the rig comparison)
           --no-game      do not translate the game again first (recomp.py)
           --no-net       rta_app without the network
           --opt -O1|-O2  --jobs N (default 8)

What it makes, in local/recomp-out/linux/<arch>/ (docs/issues/native-linux.md says what was run):
  rta_app       the game in a window: SDL2 (window, OpenGL 4.1 core context, keyboard, mouse, game
                controllers, sound device), app/linux/linux_main.cpp, render/backend_gl.cpp unchanged
                (app/linux/glsdl.h stands in for Qt's two classes), render/texpack.cpp with
                render/png_read.h; the network: net/netdrv.cpp over net/sock.h's BSD body, the
                one-step online, a room of our own (net2) with TLS through the system's OpenSSL
  rta_app_orig  (--original) the unpatched game, no network: the rig comparison's program
  rta_native    the machine with nothing attached (app/linux/headless_main.cpp)
  fpcheck       the game's floating-point operations as a table of checksums (app/win/fpcheck.cpp)
  ../rta-linux-<arch>/   the folder a tester gets: the programs, play.sh, online.sh, server.txt,
                README.txt (app/linux/), boot-check.rig

Toolchain (Ubuntu/Debian): apt install clang python3 libsdl2-dev libssl-dev - the container's
Dockerfile is written by --docker into local/recomp-out/linux/docker/ (FROM ubuntu:24.04, Docker
Hub's official image; nothing else is pulled).  libstdc++ and libgcc are linked in
(-static-libstdc++ -static-libgcc); SDL2, OpenSSL 3 and the C library are the system's.

The generated game code (local/recomp-out/linux/gen-app, gen-orig; made by recomp.py from your
own disc's executable) and everything built from it stay under local/recomp-out/; nothing derived
from the game belongs in the repository.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_win as bw  # noqa: E402  (the translation, the compile and link helpers, the check script)

ROOT, RECOMP, OUT = bw.ROOT, bw.RECOMP, bw.OUT
LINUX = os.path.join(OUT, 'linux')
LSRC = os.path.join(HERE, 'linux')
RT, RENDER, SOUND, NET, NET2 = bw.RT, bw.RENDER, bw.SOUND, bw.NET, bw.NET2
FP = bw.FP
DOCKERFILE = """FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \\
    clang g++ make python3 pkg-config libsdl2-dev libssl-dev \\
    xvfb xauth libgl1-mesa-dri libgl1 libegl1 mesa-utils ca-certificates file binutils \\
    && rm -rf /var/lib/apt/lists/*
"""
ARCHES = {'arm64': 'aarch64', 'amd64': 'x86_64'}


def run_docker(args, rest):
    """The build inside the container, once per architecture; the tree is mounted at its own path."""
    os.makedirs(os.path.join(LINUX, 'docker'), exist_ok=True)
    open(os.path.join(LINUX, 'docker', 'Dockerfile'), 'w').write(DOCKERFILE)
    # the translation once, here, for both architectures (the same files)
    for original in ([False, True] if args.original else [False]):
        args.original_now = original
        ns = argparse.Namespace(original=original, no_game=args.no_game, no_net=args.no_net,
                                gen=os.path.join(LINUX, 'gen-orig' if original else 'gen-app'))
        if not bw.translate(ns):
            return 1
    docker = ['docker', '--context', args.context]
    code = 0
    for arch in (['arm64', 'amd64'] if args.docker == 'both' else [args.docker]):
        image = 'rta-linux:' + arch
        if subprocess.run(docker + ['image', 'inspect', image], capture_output=True).returncode != 0:
            built = subprocess.run(docker + ['build', '--platform', 'linux/' + arch, '-t', image, os.path.join(LINUX, 'docker')])
            if built.returncode != 0:
                return built.returncode
        command = docker + ['run', '--rm', '--platform', 'linux/' + arch, '--user', '%d:%d' % (os.getuid(), os.getgid()),
                            '-e', 'HOME=/tmp', '-v', '%s:%s' % (ROOT, ROOT), '-w', ROOT, image,
                            'python3', '-B', os.path.join(HERE, 'build_linux.py'), '--no-game'] + rest
        print('docker (%s): %s' % (arch, ' '.join(command[-6:])))
        code = subprocess.run(command).returncode or code
    return code


def build(args):
    arch = platform.machine()
    if arch == 'arm64':
        arch = 'aarch64'
    out = os.path.join(LINUX, arch)
    os.makedirs(out, exist_ok=True)
    cxx = [shutil.which('clang++') or 'clang++']
    print('toolchain: %s on Linux %s' % (subprocess.run(cxx + ['--version'], capture_output=True, text=True).stdout.splitlines()[0], arch))
    sdl = subprocess.run(['pkg-config', '--cflags', 'sdl2'], capture_output=True, text=True).stdout.split() or ['-I/usr/include/SDL2', '-D_REENTRANT']
    opt = args.opt or '-O2'
    ok = True
    for original in ([False, True] if args.original else [False]):
        args.original_build = original
        gen = os.path.join(LINUX, 'gen-orig' if original else 'gen-app')
        ns = argparse.Namespace(original=original, no_game=args.no_game, no_net=args.no_net, gen=gen)
        if not bw.translate(ns):
            return 1
        net = not original and not args.no_net
        objdir = os.path.join(LINUX, 'obj-%s%s' % (arch, '-orig' if original else ''))
        os.makedirs(objdir, exist_ok=True)
        rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + FP + ['-I', RT, '-I', gen]
        render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + FP + ['-I', RENDER]
        app_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function', '-I', HERE, '-I', LSRC, '-I', RENDER, '-I', RT] + sdl
        search = [HERE, LSRC, RENDER, RT, SOUND, NET, NET2, gen]
        game = bw.game_jobs(gen, objdir, rt_flags)
        runtime = bw.source_jobs([(os.path.join(RT, n), rt_flags, 'rt_') for n in bw.RUNTIME + ['host_posix.cpp']], objdir, search)
        headless = bw.source_jobs([(os.path.join(RT, 'sound_null.cpp'), rt_flags, 'rt_'),
                                   (os.path.join(LSRC, 'headless_main.cpp'), rt_flags + ['-I', HERE], 'h_'),
                                   (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'h_')], objdir, search)
        fpcheck = bw.source_jobs([(os.path.join(HERE, 'win', 'fpcheck.cpp'), rt_flags, 'f_')], objdir, search)
        translation = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
        vu1 = translation if os.path.exists(translation) else os.path.join(RENDER, 'vu1_none.cpp')
        fast = os.path.join(OUT, 'gen-vu', 'vu1_fast.cpp')
        vu1_fast = fast if os.path.exists(fast) else os.path.join(RENDER, 'vu1_fast_none.cpp')
        film = not original and os.path.exists(bw.FILM) and os.path.exists(bw.FILM_HLE)
        app = bw.source_jobs(
            [(os.path.join(RENDER, n), render_flags, 'r_') for n in bw.RENDER_CORE] + [(vu1, render_flags, 'r_'), (vu1_fast, render_flags, 'r_'),
             # backend_gl.cpp against app/linux's two Qt headers (glsdl.h)
             (os.path.join(RENDER, 'backend_gl.cpp'), render_flags + ['-I', LSRC], 'r_'),
             (os.path.join(RENDER, 'texpack.cpp'), render_flags + ['-DRTA_NO_QIMAGE'], 'r_'),
             (os.path.join(SOUND, 'sound_rta.cpp'), rt_flags + ['-I', SOUND, '-DRTA_SDL_AUDIO'] + sdl, 'rt_'),
             (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
             (os.path.join(HERE, 'gfx_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
             (os.path.join(LSRC, 'linux_main.cpp'), app_flags + (['-DRTA_NET', '-I', NET] if net else []), 'a_'),
             (os.path.join(LSRC, 'glsdl.cpp'), app_flags, 'a_'),
             (os.path.join(LSRC, 'pad_linux.cpp'), app_flags, 'a_'),
             (os.path.join(HERE, 'fpcontrols.cpp'), app_flags, 'a_'),
             (os.path.join(HERE, 'fpview.cpp'), rt_flags + ['-I', HERE], 'a_'),
             (os.path.join(HERE, 'fpworld.cpp'), rt_flags + ['-I', HERE, '-I', RENDER], 'a_')] +
            ([(os.path.join(NET, 'netdrv.cpp'), rt_flags, 'n_'),
              (os.path.join(NET, 'online.cpp'), rt_flags, 'n_'),
              (bw.ONLINE, rt_flags, 'n_')] +
             [(os.path.join(NET2, n), ['-std=c++17', opt, '-Wall', '-I', NET2, '-include', 'algorithm', '-DRTA_OPENSSL'], 'n2_')
              for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp', 'tls.cpp', 'cardchars.cpp', 'clicmd.cpp')] +
             [(os.path.join(NET2, 'launch.cpp'), rt_flags + ['-I', NET2], 'n2_')] if net else []) +
            ([(bw.FILM, rt_flags + ['-I', HERE, '-include', 'ctime'], 'a_')] if film else []), objdir, search)
        jobs = game + runtime + app + ([] if original else headless + fpcheck)
        if not bw.compile_all(jobs, cxx, args.jobs):
            return 1
        objs = lambda group: [j[2] for j in group]
        static = ['-static-libstdc++', '-static-libgcc', '-Wl,-Map,%s' % os.path.join(objdir, 'rta_app.map')]
        libs = ['-lSDL2'] + (['-lssl', '-lcrypto'] if net else []) + ['-lpthread', '-ldl']
        name = 'rta_app_orig' if original else 'rta_app'
        ok = bw.link(cxx + static, objs(game) + objs(runtime) + objs(app), libs, os.path.join(out, name)) and ok
        if not original:
            ok = bw.link(cxx + ['-static-libstdc++', '-static-libgcc'], objs(game) + objs(runtime) + objs(headless), ['-lpthread'],
                         os.path.join(out, 'rta_native')) and ok
            ok = bw.link(cxx + ['-static-libstdc++', '-static-libgcc'], objs(fpcheck), [], os.path.join(out, 'fpcheck')) and ok
    if ok:
        package(arch, out)
    return 0 if ok else 1


def package(arch, out):
    """local/recomp-out/linux/rta-linux-<arch>: what a tester gets."""
    target = os.path.join(LINUX, 'rta-linux-' + arch)
    os.makedirs(target, exist_ok=True)
    for name in ('rta_app', 'rta_native', 'fpcheck'):
        if os.path.exists(os.path.join(out, name)):
            shutil.copy2(os.path.join(out, name), os.path.join(target, name))
    for name in ('play.sh', 'online.sh', 'server.txt'):
        source, dest = os.path.join(LSRC, name), os.path.join(target, name)
        if not os.path.exists(source) or (name == 'server.txt' and os.path.exists(dest)):
            continue                                    # the tester's (or the builder's) address stays
        shutil.copyfile(source, dest)
        if name.endswith('.sh'):
            os.chmod(dest, 0o755)
    write_readme(arch, target)
    bw.write_check_script(os.path.join(target, 'boot-check.rig'))
    print('the folder to give a tester: ' + os.path.relpath(target, ROOT))


def write_readme(arch, target):
    """README.txt with this build's figures: what the Mac prints for the same checks
    (local/recomp-out/linux/reference/, made by the Mac's runs: fpcheck-mac.txt, boot-check-mac.txt,
    patch-set.txt)."""
    import re
    ref = os.path.join(LINUX, 'reference')
    values = {'@ARCH@': arch, '@FPCHECK@': '(not made yet)', '@FRAMES_LINE@': '(not made yet)', '@VU0_LINE@': '(not made yet)',
              '@PATCH_SET@': '(not made yet)'}
    path = os.path.join(ref, 'fpcheck-mac.txt')
    if os.path.exists(path):
        for line in open(path, errors='replace'):
            if 'must agree everywhere' in line:
                values['@FPCHECK@'] = line.split()[-1]
    path = os.path.join(ref, 'boot-check-mac.txt')
    if os.path.exists(path):
        for line in open(path, errors='replace'):
            found = re.match(r'(frames=\d+) wall=.*(fields=\d+ units=\d+)', line)
            if found:
                values['@FRAMES_LINE@'] = '%s wall=...: ... %s' % found.groups()
            if line.startswith('VU0:'):
                values['@VU0_LINE@'] = line.strip()
    path = os.path.join(ref, 'patch-set.txt')
    if os.path.exists(path):
        values['@PATCH_SET@'] = open(path).read().strip()
    text = open(os.path.join(LSRC, 'README.txt')).read()
    for key, value in values.items():
        text = text.replace(key, value)
    open(os.path.join(target, 'README.txt'), 'w').write(text)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker', choices=('arm64', 'amd64', 'both'))
    parser.add_argument('--context', default='colima-rta')
    parser.add_argument('--original', action='store_true')
    parser.add_argument('--no-game', action='store_true')
    parser.add_argument('--no-net', action='store_true')
    parser.add_argument('--opt')
    parser.add_argument('--jobs', type=int, default=8)
    args, rest = parser.parse_known_args()
    args.jobs = max(1, min(8, args.jobs))
    if args.docker:
        passed = [a for a in sys.argv[1:] if a not in ('--docker', args.docker, '--context', args.context, '--no-game')]
        return run_docker(args, passed)
    if not sys.platform.startswith('linux'):
        sys.exit('build_linux.py builds on Linux; on a Mac give --docker arm64|amd64|both')
    return build(args)


if __name__ == '__main__':
    sys.exit(main())
