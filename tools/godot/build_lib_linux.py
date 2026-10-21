#!/usr/bin/env python3
"""build_lib_linux.py - the game library of the Godot application (librta_game) for Linux.

  python3 tools/godot/build_lib_linux.py --arch arm64          # on a Mac: inside the Ubuntu container
                                                               # (docker context colima-rta), aarch64
  python3 tools/godot/build_lib_linux.py --arch x86_64         # ... x86-64 (emulated: slow); amd64 is the same
  python3 tools/godot/build_lib_linux.py --arch both
  python3 tools/godot/build_lib_linux.py --here                # on Linux: this machine, no docker (the default
                                                               # there when no --arch is given)
  options: --context NAME (docker context; default colima-rta)   --image NAME (default rta-linux:<arch>)
           --pic-game     compile the translated game again, position-independent, into this script's own
                          directory, even when tools/recomp/app/build_linux.py's objects are there and current
           --no-test      do not load the library afterwards (dlopen, rtag_api_version, rtag_has)
           --opt -O1|-O2  --jobs N (default 8)
  RTA_GODOT_OUT=DIR: the build directory (relative to the repository or absolute; default local/godot-r7).

The Linux twin of `tools/godot/build.py lib` (build_lib): the same sources, flags and exported
functions (build.py's EXPORTS and NET2_EXPORTS lists), linked as a shared object.  What it takes:
  OUT/src/recomp/                    build.py's snapshot of tools/recomp (`build.py snapshot`): the runtime,
                                     the renderer, the sound, the app files, net and net2 (no snapshot:
                                     tools/recomp itself, local/recomp-out/gen-vu, tools/play-net/src)
  OUT/src/gen-vu/, OUT/src/play-net/ the VU1 programs translated ahead of time, the one-step online
  local/recomp-out/linux/gen-app/    the game translated for Linux (tools/recomp/app/build_linux.py)
  tools/godot/lib/                   rtag.cpp, host_godot.cpp, scene_export.cpp, audio_host.inc, and
                                     gl_offscreen_linux.cpp (an OpenGL 4.1 core context through EGL, no window)
  tools/recomp/app/linux/            glsdl.h and the two Qt-named headers backend_gl.cpp is compiled against
The translated game: build_linux.py's objects (local/recomp-out/linux/obj-<arch>) when they are newer
than the translation - the toolchain's default is position-independent executable code, which links
into a shared object as long as no symbol of it is exported (the version script below exports only
the library's own functions; -z text proves no relocation is left in the code) - else (or with
--pic-game) compiled with -fPIC into OUT/linux/obj-<arch>-pic.

What it makes, in OUT/linux/:
  <arch>/librta_game.so   libstdc++ and libgcc linked in; OpenSSL 3, zlib and the C library are the
                          system's; libEGL is opened at run time (no EGL: no pictures of its own)
  obj-<arch>/             the objects of everything else, and the dlopen test
Nothing derived from the game leaves local/.
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(ROOT, 'tools', 'recomp', 'app')
# the build directory: RTA_GODOT_OUT (relative to the repository or absolute), else local/godot-r7
os.environ['RTA_GODOT_OUT'] = os.path.join(ROOT, os.environ.get('RTA_GODOT_OUT') or os.path.join('local', 'godot-r7'))
sys.path.insert(0, APP)
import build_win as bw  # noqa: E402  (game_jobs, source_jobs, compile_all, link: read only, nothing of it is changed)


def _load(name, path):
    # by its path: build_win puts tools/recomp (which has a build.py of its own) first on sys.path
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gb = _load('rta_godot_build', os.path.join(HERE, 'build.py'))   # EXPORTS, NET2_EXPORTS, RENDER_CORE, RUNTIME, OUT, SRC, SNAP

LIB = os.path.join(HERE, 'lib')
LSRC = os.path.join(APP, 'linux')
GEN = os.path.join(ROOT, 'local', 'recomp-out', 'linux', 'gen-app')
LINUX = os.path.join(gb.OUT, 'linux')
DOCKER_ARCH = {'arm64': 'arm64', 'aarch64': 'arm64', 'amd64': 'amd64', 'x86_64': 'amd64'}
TEST = r'''
#include <dlfcn.h>
#include <stdio.h>
int main(int argc, char** argv) {
    void* h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!h) { printf("dlopen FAILED: %s\n", dlerror()); return 1; }
    int (*version)(void) = (int (*)(void))dlsym(h, "rtag_api_version");
    int (*has)(const char*) = (int (*)(const char*))dlsym(h, "rtag_has");
    if (!version || !has) { printf("dlsym FAILED: %s\n", dlerror()); return 1; }
    printf("dlopen ok: rtag_api_version() = %d\n", version());
    const char* features[] = {"fixes", "films", "picture", "scene3d", "network"};
    for (int i = 0; i < 5; i++) printf("  rtag_has(\"%s\") = %d\n", features[i], has(features[i]));
    printf("  net2_open %s\n", dlsym(h, "net2_open") ? "exported" : "not exported");
    return 0;
}
'''


def run_docker(args):
    docker = ['docker', '--context', args.context]
    passed = [a for a in sys.argv[1:] if a not in ('--arch', args.arch, '--context', args.context, '--image', args.image or '')]
    passed = [a for a in passed if not a.startswith(('--arch=', '--context=', '--image='))]
    code = 0
    for arch in (['arm64', 'amd64'] if args.arch == 'both' else [DOCKER_ARCH[args.arch]]):
        image = args.image or 'rta-linux:' + arch
        if subprocess.run(docker + ['image', 'inspect', image], capture_output=True).returncode != 0:
            print('no image %s in the docker context %s: python3 tools/recomp/app/build_linux.py --docker %s makes it' % (image, args.context, arch))
            return 1
        command = docker + ['run', '--rm', '--platform', 'linux/' + arch, '--user', '%d:%d' % (os.getuid(), os.getgid()),
                            '-e', 'HOME=/tmp', '-e', 'RTA_GODOT_OUT=' + gb.OUT, '-e', 'RTA_BUILD_ID=' + bw.buildid.build_id(), '-v', '%s:%s' % (ROOT, ROOT), '-w', ROOT, image,
                            'python3', '-B', os.path.abspath(__file__), '--here'] + passed
        print('docker (%s, %s): build_lib_linux.py %s' % (arch, image, ' '.join(passed)))
        code = subprocess.run(command).returncode or code
    return code


def has(path, word):
    try:
        return word in open(path, errors='replace').read()
    except OSError:
        return False


def game_objects(arch, rt_flags, args):
    """The translated game's objects: build_linux.py's when current, else our own position-independent ones."""
    pic = os.path.join(LINUX, 'obj-%s-pic' % arch)
    theirs = os.path.join(ROOT, 'local', 'recomp-out', 'linux', 'obj-' + arch)
    if not args.pic_game:
        jobs = bw.game_jobs(GEN, theirs, rt_flags)
        current = all(os.path.exists(target) and all(os.path.getmtime(p) <= os.path.getmtime(target) for p in [source] + deps if os.path.exists(p))
                      for source, _, target, deps in jobs)
        if current:
            print('the translated game: %d objects of build_linux.py (%s)' % (len(jobs), os.path.relpath(theirs, ROOT)))
            return [j[2] for j in jobs]
        print('build_linux.py\'s objects of the game are missing or older than the translation: compiling them with -fPIC')
    os.makedirs(pic, exist_ok=True)
    jobs = bw.game_jobs(GEN, pic, rt_flags)
    if not bw.compile_all(jobs, ['clang++'], args.jobs):
        return None
    return [j[2] for j in jobs]


def build(args):
    arch = platform.machine()
    arch = 'aarch64' if arch == 'arm64' else arch
    snap, vu, online = gb.SNAP, os.path.join(gb.SRC, 'gen-vu'), os.path.join(gb.SRC, 'play-net', 'src', 'RtaOnline.cpp')
    if not os.path.isdir(snap):
        # a fresh machine: tools/recomp as it is (tools/godot/recomp.patch holds no hunk now; with one, take the snapshot)
        snap, vu, online = os.path.join(ROOT, 'tools', 'recomp'), os.path.join(ROOT, 'local', 'recomp-out', 'gen-vu'), bw.ONLINE
        print('no snapshot in %s: compiling tools/recomp as it is' % os.path.relpath(gb.SNAP, ROOT))
    if not os.path.exists(os.path.join(GEN, 'funcs.h')):
        print('no Linux translation of the game (%s): python3 tools/recomp/app/build_linux.py --docker arm64' % os.path.relpath(GEN, ROOT))
        return 1
    out = os.path.join(LINUX, arch)
    objdir = os.path.join(LINUX, 'obj-' + arch)
    os.makedirs(out, exist_ok=True)
    os.makedirs(objdir, exist_ok=True)
    print('toolchain: %s on Linux %s' % (subprocess.run(['clang++', '--version'], capture_output=True, text=True).stdout.splitlines()[0], arch))
    rt, render, sound, app, net, net2 = (os.path.join(snap, p) for p in ('rt', 'render', 'sound', 'app', 'net', 'net2'))
    opt, fp, pic = args.opt, bw.FP, ['-fPIC']
    render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + fp + pic + ['-I', render]
    rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + fp + pic + ['-I', rt, '-I', GEN]
    lib_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + fp + pic + ['-I', LIB, '-I', app, '-I', render, '-I', rt]
    # what the snapshot's core can do, as build.py decides it (the music's own volume, the second HUD group, the world)
    if has(os.path.join(sound, 'drivers.cpp'), 'rta_sound_set_music_gain'):
        lib_flags.append('-DRTAG_HAVE_MUSIC_GAIN')
    funcs = os.path.join(GEN, 'funcs.h')
    hud_text = has(os.path.join(render, 'gs.h'), 'hide_text') and has(funcs, 'orig_001d93b0')
    if hud_text:
        lib_flags.append('-DRTAG_HAVE_HUD_TEXT')
    gfx_flags = rt_flags + ['-I', app] + ([] if hud_text else ['-DRTA_NO_HUD_TEXT_HOOKS'])
    world = has(os.path.join(app, 'fpworld.cpp'), 'install') and has(funcs, 'orig_001868a4')
    if world:
        lib_flags.append('-DRTAG_HAVE_WORLD')
    sources = [(os.path.join(render, n), render_flags, 'r_') for n in gb.RENDER_CORE + ['scene_tap.cpp'] if os.path.exists(os.path.join(render, n))]
    translated, fast = os.path.join(vu, 'vu1_translated.cpp'), os.path.join(vu, 'vu1_fast.cpp')
    sources.append((translated if os.path.exists(translated) else os.path.join(render, 'vu1_none.cpp'), render_flags, 'r_'))
    sources.append((fast if os.path.exists(fast) else os.path.join(render, 'vu1_fast_none.cpp'), render_flags, 'r_'))
    sources.append((os.path.join(render, 'backend_gl.cpp'), render_flags + ['-I', LSRC], 'r_'))         # against glsdl.h's Qt classes
    sources.append((os.path.join(render, 'texpack.cpp'), render_flags + ['-DRTA_NO_QIMAGE'], 'r_'))
    sources += [(os.path.join(rt, n), rt_flags, 'rt_') for n in gb.RUNTIME]
    sources.append((os.path.join(LIB, 'host_godot.cpp'), rt_flags, 'rt_'))
    sources.append((os.path.join(sound, 'sound_rta.cpp'), rt_flags + ['-I', sound, '-I', LIB, '-DRTA_AUDIO_HOST="audio_host.inc"'], 'rt_'))
    sources.append((os.path.join(app, 'app_rt.cpp'), rt_flags + ['-I', app], 'a_'))
    sources.append((os.path.join(app, 'gfx_rt.cpp'), gfx_flags, 'a_'))
    if os.path.exists(os.path.join(app, 'fpview.cpp')):
        sources.append((os.path.join(app, 'fpview.cpp'), rt_flags + ['-I', app], 'a_'))
    if world:
        sources.append((os.path.join(app, 'fpworld.cpp'), rt_flags + ['-I', app, '-I', render], 'a_'))
    if os.path.exists(os.path.join(app, 'fpcontrols.cpp')):
        sources.append((os.path.join(app, 'fpcontrols.cpp'), ['-std=c++17', opt, '-Wall'] + pic + ['-I', app, '-I', rt], 'a_'))
        if os.path.exists(os.path.join(app, 'soulscombat.cpp')):
            sources.append((os.path.join(app, 'soulscombat.cpp'), rt_flags + ['-I', app, '-I', render], 'a_'))
            lib_flags.append('-DRTAG_HAVE_SOULS')
        if os.path.exists(os.path.join(app, 'fpaim.cpp')):         # aiming by looking (fpaim.h): needs the controls too
            sources.append((os.path.join(app, 'fpaim.cpp'), rt_flags + ['-I', app], 'a_'))
            lib_flags.append('-DRTAG_HAVE_AIM')
    if os.path.exists(os.path.join(app, 'testerkit.cpp')):         # the tester's kit (app/testerkit.h): reports, the build line
        sources.append((os.path.join(app, 'testerkit.cpp'), rt_flags + ['-I', app, '-I', render, bw.buildid.define()], 'a_'))
        lib_flags.append('-DRTAG_HAVE_TESTERKIT')
    else:
        lib_flags.append('-DRTAG_NO_CONTROLS')
    # the films' entries are left to app/film.cpp when the translation was made with them (build_linux.py's rule)
    if os.path.exists(bw.FILM) and os.path.exists(bw.FILM_HLE):
        sources.append((os.path.join(app, 'film.cpp'), rt_flags + ['-I', app, '-include', 'ctime'], 'a_'))
    has_net2 = os.path.exists(os.path.join(net2, 'launch.cpp')) and has(os.path.join(net, 'netdrv.cpp'), 'net2hook') and os.path.exists(online)
    if has_net2:
        sources += [(os.path.join(net, n), rt_flags, 'n_') for n in ('netdrv.cpp', 'online.cpp')]
        sources.append((online, rt_flags, 'n_'))
        plain = ['-std=c++17', opt, '-Wall'] + pic + ['-I', net2, '-include', 'algorithm', '-DRTA_OPENSSL']    # tls.cpp: the system's OpenSSL
        sources += [(os.path.join(net2, n), plain, 'n2_') for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp', 'tls.cpp',
                                                                     'cardchars.cpp', 'clicmd.cpp') if os.path.exists(os.path.join(net2, n))]
        sources.append((os.path.join(net2, 'launch.cpp'), rt_flags + ['-I', net2], 'n2_'))
        lib_flags.append('-DRTAG_HAVE_NET2')
    sources.append((os.path.join(LIB, 'rtag.cpp'), lib_flags, 'g_'))
    sources.append((os.path.join(LIB, 'scene_export.cpp'), lib_flags, 'g_'))
    sources.append((os.path.join(LIB, 'gl_offscreen_linux.cpp'), lib_flags + ['-I', LSRC], 'g_'))
    search = [LIB, LSRC, app, render, rt, sound, net, net2, GEN, vu]
    jobs = bw.source_jobs(sources, objdir, search)
    if not bw.compile_all(jobs, ['clang++'], args.jobs):
        return 1
    game = game_objects(arch, rt_flags, args)
    if game is None:
        return 1
    exports = os.path.join(objdir, 'exports.map')
    names = gb.EXPORTS + (gb.NET2_EXPORTS if has_net2 else [])
    open(exports, 'w').write('{\n  global:\n%s  local: *;\n};\n' % ''.join('    %s;\n' % n for n in names))
    final = os.path.join(out, 'librta_game.so')
    command = ['clang++', '-shared', '-static-libstdc++', '-static-libgcc', '-Wl,--version-script,' + exports, '-Wl,-Bsymbolic',
               '-Wl,-z,defs', '-Wl,-z,text', '-Wl,-z,noexecstack', '-Wl,-soname,librta_game.so']
    libs = (['-lssl', '-lcrypto'] if has_net2 else []) + ['-lz', '-lpthread', '-ldl', '-lm']
    temporary = final + '.link%d' % os.getpid()
    if not bw.link(command, [j[2] for j in jobs] + game, libs, temporary):
        if os.path.exists(temporary):
            os.remove(temporary)
        return 1
    os.replace(temporary, final)
    exported = subprocess.run(['nm', '-D', '--defined-only', final], capture_output=True, text=True).stdout.split('\n')
    exported = sorted(line.split()[-1] for line in exported if re.search(r' T ', line))
    lost = sorted(set(names) - set(exported))
    print('%s: %d functions exported%s%s' % (os.path.relpath(final, ROOT), len(exported), ' (MISSING: %s)' % ' '.join(lost) if lost else '',
                                              '; others: %s' % ' '.join(sorted(set(exported) - set(names))) if set(exported) - set(names) else ''))
    if lost:
        return 1
    if not args.no_test:
        source, program = os.path.join(objdir, 'dlopen_test.c'), os.path.join(objdir, 'dlopen_test')
        open(source, 'w').write(TEST)
        made = subprocess.run(['clang', '-O1', source, '-o', program, '-ldl'], capture_output=True, text=True)
        if made.returncode != 0:
            print('dlopen test FAILED to compile\n' + made.stderr)
            return 1
        result = subprocess.run([program, final], capture_output=True, text=True)
        print(result.stdout.rstrip() + (('\n' + result.stderr.rstrip()) if result.stderr.strip() else ''))
        if result.returncode != 0:
            return 1
    return 0


def main():
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=('arm64', 'aarch64', 'amd64', 'x86_64', 'both'))
    parser.add_argument('--here', action='store_true', help='build on this Linux machine (no docker)')
    parser.add_argument('--context', default='colima-rta')
    parser.add_argument('--image')
    parser.add_argument('--pic-game', action='store_true')
    parser.add_argument('--no-test', action='store_true')
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    args.jobs = max(1, min(8, args.jobs))
    on_linux = sys.platform.startswith('linux')
    if args.here or (on_linux and not args.arch):
        if not on_linux:
            sys.exit('--here builds on Linux only; on a Mac give --arch arm64|x86_64|both (docker)')
        machine = DOCKER_ARCH.get(platform.machine())
        if args.arch and args.arch != 'both' and DOCKER_ARCH[args.arch] != machine:
            sys.exit('--here builds for this machine (%s), not %s' % (platform.machine(), args.arch))
        return build(args)
    if not args.arch:
        sys.exit('on a Mac give --arch arm64|x86_64|both (built inside docker)')
    return run_docker(args)


if __name__ == '__main__':
    sys.exit(main())
