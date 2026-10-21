#!/usr/bin/env python3
"""build_lib_win.py - the game library of the Godot application (librta_game.dll) for Windows x86-64.

  python3 tools/godot/build_lib_win.py                # on a Mac (brew install mingw-w64) or on Windows (llvm-mingw
                                                      # or MSYS2 on the PATH, as tools/recomp/app/build_win.py)
  options: --compiler clang|gcc (build_win.py's choice)   --no-game-objects (compile the translated game into this
           script's own directory even when build_win.py's objects are current)   --opt -O1|-O2   --jobs N (default 8)
  RTA_GODOT_OUT=DIR: the build directory (relative to the repository or absolute; default local/godot-r7).

The Windows twin of `tools/godot/build.py lib` and build_lib_linux.py: the same sources, flags and exported functions
(build.py's EXPORTS and NET2_EXPORTS, written into a module-definition file), linked as a DLL with everything static
(-static: libstdc++, libgcc and winpthreads inside; it needs only Windows' own DLLs).  What it takes:
  OUT/src/recomp/                    build.py's snapshot of tools/recomp (no snapshot: tools/recomp itself)
  local/recomp-out/win/gen-app/      the game translated for Windows (tools/recomp/app/build_win.py) and, when
  local/recomp-out/win/obj-<tag>/    current, that build's objects of it
  tools/godot/lib/                   rtag.cpp, host_godot.cpp (its Windows half), scene_export.cpp, audio_host.inc,
                                     gl_offscreen_win.cpp (a hidden window and a WGL core context)
  tools/recomp/app/win/              wgl.cpp / wgl.h and the two Qt-named headers backend_gl.cpp is compiled against
What it makes, in OUT/windows/: librta_game.dll, and obj/ (the other objects, the .def file, the map).
Nothing derived from the game leaves local/.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(ROOT, 'tools', 'recomp', 'app')
os.environ['RTA_GODOT_OUT'] = os.path.join(ROOT, os.environ.get('RTA_GODOT_OUT') or os.path.join('local', 'godot-r7'))
sys.path.insert(0, APP)
import build_win as bw  # noqa: E402  (find_toolchain, game_jobs, source_jobs, compile_all, link, WIN_DEFINES: read only)


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gb = _load('rta_godot_build', os.path.join(HERE, 'build.py'))   # EXPORTS, NET2_EXPORTS, RENDER_CORE, RUNTIME, OUT, SRC, SNAP

LIB = os.path.join(HERE, 'lib')
WINSRC = os.path.join(APP, 'win')
GEN = os.path.join(ROOT, 'local', 'recomp-out', 'win', 'gen-app')
WINDOWS = os.path.join(gb.OUT, 'windows')
LIBS = ['-lopengl32', '-lgdi32', '-luser32', '-lole32', '-lwinmm', '-lshell32', '-lpthread'] + bw.NET_LIBS


def has(path, word):
    try:
        return word in open(path, errors='replace').read()
    except OSError:
        return False


def game_objects(cxx, tag, rt_flags, args):
    """The translated game's objects: build_win.py's when current (the same flags), else our own."""
    theirs = os.path.join(ROOT, 'local', 'recomp-out', 'win', 'obj-' + tag)
    if not args.no_game_objects:
        jobs = bw.game_jobs(GEN, theirs, rt_flags)
        line = ' '.join(cxx + rt_flags)
        current = all(os.path.exists(target) and os.path.exists(target + '.flags') and open(target + '.flags').read() == line and
                      all(os.path.getmtime(p) <= os.path.getmtime(target) for p in [source] + deps if os.path.exists(p))
                      for source, _, target, deps in jobs)
        if current:
            print('the translated game: %d objects of build_win.py (%s)' % (len(jobs), os.path.relpath(theirs, ROOT)))
            return [j[2] for j in jobs]
        print('build_win.py\'s objects of the game are missing, older than the translation or made with other flags: compiling them here')
    own = os.path.join(WINDOWS, 'obj-game-' + tag)
    os.makedirs(own, exist_ok=True)
    jobs = bw.game_jobs(GEN, own, rt_flags)
    if not bw.compile_all(jobs, cxx, args.jobs):
        return None
    return [j[2] for j in jobs]


def build(args):
    snap, vu, online = gb.SNAP, os.path.join(gb.SRC, 'gen-vu'), os.path.join(gb.SRC, 'play-net', 'src', 'RtaOnline.cpp')
    if not os.path.isdir(snap):
        snap, vu, online = os.path.join(ROOT, 'tools', 'recomp'), os.path.join(ROOT, 'local', 'recomp-out', 'gen-vu'), bw.ONLINE
        print('no snapshot in %s: compiling tools/recomp as it is' % os.path.relpath(gb.SNAP, ROOT))
    if not os.path.exists(os.path.join(GEN, 'funcs.h')):
        print('no Windows translation of the game (%s): python3 tools/recomp/app/build_win.py' % os.path.relpath(GEN, ROOT))
        return 1
    cxx, linker, _, what = bw.find_toolchain(args.compiler)
    tag = 'clang' if 'clang' in os.path.basename(cxx[0]) else 'gcc'
    print('toolchain: ' + what)
    objdir = os.path.join(WINDOWS, 'obj-' + tag)
    os.makedirs(objdir, exist_ok=True)
    rt, render, sound, app, net, net2 = (os.path.join(snap, p) for p in ('rt', 'render', 'sound', 'app', 'net', 'net2'))
    opt, fp, wd = args.opt, bw.FP, bw.WIN_DEFINES
    # the game's objects are build_win.py's: the runtime flags are exactly its own (its RT and GEN paths)
    game_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + fp + wd + ['-I', bw.RT, '-I', GEN]
    rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + fp + wd + ['-I', rt, '-I', GEN]
    render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + fp + wd + ['-I', render]
    lib_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + fp + wd + ['-I', LIB, '-I', app, '-I', render, '-I', rt,
                                                                                 '-DRTA_PNG_NO_ZLIB']
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
    sources.append((os.path.join(render, 'backend_gl.cpp'), render_flags + ['-I', WINSRC], 'r_'))         # against wgl.h's Qt classes
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
        sources.append((os.path.join(app, 'fpcontrols.cpp'), ['-std=c++17', opt, '-Wall'] + wd + ['-I', app, '-I', rt], 'a_'))
        if os.path.exists(os.path.join(app, 'soulscombat.cpp')):
            sources.append((os.path.join(app, 'soulscombat.cpp'), rt_flags + ['-I', app, '-I', render], 'a_'))
            lib_flags.append('-DRTAG_HAVE_SOULS')
        if os.path.exists(os.path.join(app, 'fpaim.cpp')):
            sources.append((os.path.join(app, 'fpaim.cpp'), rt_flags + ['-I', app], 'a_'))
            lib_flags.append('-DRTAG_HAVE_AIM')
    else:
        lib_flags.append('-DRTAG_NO_CONTROLS')
    if os.path.exists(bw.FILM) and os.path.exists(bw.FILM_HLE):
        sources.append((os.path.join(app, 'film.cpp'), rt_flags + ['-I', app, '-include', 'ctime'], 'a_'))
    has_net2 = os.path.exists(os.path.join(net2, 'launch.cpp')) and has(os.path.join(net, 'netdrv.cpp'), 'net2hook') and os.path.exists(online)
    if has_net2:
        sources += [(os.path.join(net, n), rt_flags, 'n_') for n in ('netdrv.cpp', 'online.cpp')]
        sources.append((online, rt_flags + ['-include', os.path.join(net, 'posix_win.h')], 'n_'))
        # the one-step online's Windows file calls (private and replaced files); its questions on a window are never attached here
        sources.append((os.path.join(net, 'online_win.cpp'), ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + wd + ['-I', net, '-I', rt], 'n_'))
        plain = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + wd + ['-I', net2, '-include', 'algorithm']     # tls.cpp: SChannel
        sources += [(os.path.join(net2, n), plain, 'n2_') for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp', 'tls.cpp',
                                                                     'cardchars.cpp', 'clicmd.cpp') if os.path.exists(os.path.join(net2, n))]
        sources.append((os.path.join(net2, 'launch.cpp'), rt_flags + ['-I', net2], 'n2_'))
        lib_flags.append('-DRTAG_HAVE_NET2')
    sources.append((os.path.join(LIB, 'rtag.cpp'), lib_flags, 'g_'))
    sources.append((os.path.join(LIB, 'scene_export.cpp'), lib_flags, 'g_'))
    sources.append((os.path.join(LIB, 'gl_offscreen_win.cpp'), lib_flags + ['-I', WINSRC], 'g_'))
    sources.append((os.path.join(WINSRC, 'wgl.cpp'), lib_flags + ['-I', WINSRC], 'g_'))
    search = [LIB, WINSRC, app, render, rt, sound, net, net2, GEN, vu]
    jobs = bw.source_jobs(sources, objdir, search)
    if not bw.compile_all(jobs, cxx, args.jobs):
        return 1
    game = game_objects(cxx, tag, game_flags, args)
    if game is None:
        return 1
    names = gb.EXPORTS + (gb.NET2_EXPORTS if has_net2 else [])
    definition = os.path.join(objdir, 'librta_game.def')
    open(definition, 'w').write('LIBRARY librta_game.dll\nEXPORTS\n' + ''.join('    %s\n' % n for n in names))
    os.makedirs(WINDOWS, exist_ok=True)
    final = os.path.join(WINDOWS, 'librta_game.dll')
    temporary = final + '.link%d' % os.getpid()
    command = linker + ['-shared', '-static', '-s', '-Wl,-Map,' + os.path.join(objdir, 'librta_game.map'), definition]
    if not bw.link(command, [j[2] for j in jobs] + game, LIBS, temporary):
        if os.path.exists(temporary):
            os.remove(temporary)
        return 1
    os.replace(temporary, final)
    # what the DLL exports, by its export table (objdump of the MinGW binutils)
    objdump = 'x86_64-w64-mingw32-objdump'
    shown = subprocess.run([objdump, '-p', final], capture_output=True, text=True).stdout if bw.shutil.which(objdump) else ''
    if '[Ordinal/Name Pointer] Table' in shown:          # GNU objdump's listing (another objdump: no check)
        table = shown.split('[Ordinal/Name Pointer] Table', 1)[-1]
        exported = set(re.findall(r'\]\s+[0-9a-f]{4} (\w+)', table))
        lost = sorted(set(names) - exported)
        dlls = sorted(set(re.findall(r'DLL Name: (\S+)', shown)))
        print('%s: %d functions exported%s; needs %s' % (os.path.relpath(final, ROOT), len(exported & set(names)),
                                                          ' (MISSING: %s)' % ' '.join(lost) if lost else '', ' '.join(dlls)))
        if lost:
            return 1
    return 0


def main():
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', choices=('clang', 'gcc'))
    parser.add_argument('--no-game-objects', action='store_true')
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    args.jobs = max(1, min(8, args.jobs))
    return build(args)


if __name__ == '__main__':
    sys.exit(main())
