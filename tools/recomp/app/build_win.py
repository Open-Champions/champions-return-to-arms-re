#!/usr/bin/env python3
"""build_win.py - build the native game for Windows x86-64 (and the x86-64 stand-in for macOS).

  python3 tools/recomp/app/build_win.py              # everything into local/recomp-out/win/
  python3 tools/recomp/app/build_win.py --headless   # fpcheck.exe and rta_native.exe only
  python3 tools/recomp/app/build_win.py --standin    # the same sources for macOS x86-64 (runs under
                                                     # Rosetta): win/standin/rta_native_x64, recomp_test_x64,
                                                     # fpcheck_x64, and rta_native_arm64, fpcheck_arm64 as
                                                     # the controls from the same sources
  options: --compiler clang|gcc   (default clang when it can target Windows, see below)
           --original             the unpatched game (gen/) instead of the fix set (gen-app/)
           --no-game              do not translate the game again first (recomp.py, about 2 s)
           --opt -O1|-O2          --jobs N (default 8, never more: other jobs share the machine)
           --symbols              keep the symbol table in the programs (default: stripped; a map
                                  of each program is written beside its objects either way)

What it makes (docs/issues/native-windows.md says what was proven and what was not run):
  rta_app.exe      the game in a window: Win32 window, OpenGL 4.1 core through WGL, XInput
                   and keyboard, WASAPI (app/win_main.cpp, app/pad_win.cpp, app/win/*,
                   sound/audio_out_win.cpp, render/backend_gl.cpp unchanged)
  rta_native.exe   the machine with nothing attached (app/win/headless_main.cpp): boots and runs scripts
  fpcheck.exe      the game's floating-point operations as a table of checksums (app/win/fpcheck.cpp)
  play.bat, README.txt  for the person who tests (copied from app/win/)

Toolchain.  On macOS: `brew install mingw-w64` (GCC, binutils, the MinGW-w64 headers and
libraries, UCRT).  --compiler clang compiles with the Mac's own clang++ for the target
x86_64-w64-mingw32 against that sysroot and links with the MinGW g++ driver: the same
compiler and the same x86-64 code generator as the stand-in that is run under Rosetta.
--compiler gcc compiles with x86_64-w64-mingw32-g++.  On Windows itself (MSYS2 UCRT64 or
CLANG64 shell: `pacman -S mingw-w64-ucrt-x86_64-gcc python`) the compiler is g++ or clang++
from the PATH - that path of this script has not been run.
Everything is linked statically (-static): the .exe needs only DLLs that are part of
Windows 10 and later.

The generated game code (local/recomp-out/win/gen-app, made here by recomp.py from your own
disc's executable, with the fix set app/build.py applies) and everything built from it stay
under local/recomp-out/; nothing derived from the game belongs in the repository.
"""
import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
WIN = os.path.join(OUT, 'win')
RT, RENDER, SOUND, WINSRC = (os.path.join(RECOMP, 'rt'), os.path.join(RECOMP, 'render'), os.path.join(RECOMP, 'sound'),
                             os.path.join(HERE, 'win'))
ON_WINDOWS = os.name == 'nt'
NICE = [] if ON_WINDOWS else ['nice', '-n', '10']

# The flags of tools/recomp/build.py and app/build.py.  -ffp-contract=off: no fused
# multiply-add; -frounding-math: the rounding mode is changed at run time (toward zero).
FP = ['-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math']
WIN_DEFINES = ['-D_WIN32_WINNT=0x0A00', '-DWINVER=0x0A00', '-D_USE_MATH_DEFINES', '-DNOMINMAX', '-DWIN32_LEAN_AND_MEAN']
RENDER_CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']
RUNTIME = ['runtime.cpp', 'iop.cpp', 'script.cpp']
WIN_LIBS = ['-lopengl32', '-lgdi32', '-luser32', '-lole32', '-lwinmm', '-lavrt', '-lshell32', '-ldwmapi']


def includes_of(source, dirs, seen=None):
    """The files a source includes with quotes, followed through."""
    seen = set() if seen is None else seen
    try:
        text = open(source, errors='replace').read()
    except OSError:
        return []
    for name in re.findall(r'^\s*#\s*include "([^"]+)"', text, re.M):
        for d in [os.path.dirname(source)] + dirs:
            path = os.path.normpath(os.path.join(d, name))
            if os.path.exists(path):
                if path not in seen:
                    seen.add(path)
                    includes_of(path, dirs, seen)
                break
    return sorted(seen)


def find_toolchain(want):
    """(compile command, link command, windres, description) for Windows x86-64."""
    if ON_WINDOWS:
        cxx = shutil.which('clang++' if want == 'clang' else 'g++') or shutil.which('g++') or shutil.which('clang++')
        if not cxx:
            sys.exit('no g++ or clang++ on the PATH (MSYS2: pacman -S mingw-w64-ucrt-x86_64-gcc)')
        return [cxx], [cxx], shutil.which('windres'), 'on Windows: ' + cxx
    gxx = shutil.which('x86_64-w64-mingw32-g++')
    if not gxx:
        sys.exit('x86_64-w64-mingw32-g++ is not installed (macOS: brew install mingw-w64)')
    windres = shutil.which('x86_64-w64-mingw32-windres')
    # <prefix>/toolchain-x86_64 holds x86_64-w64-mingw32/{include,lib} and lib/gcc: what clang needs as a sysroot
    sysroot = os.path.dirname(os.path.dirname(os.path.realpath(gxx)))
    if want != 'gcc' and shutil.which('clang++'):
        cxx = ['clang++', '--target=x86_64-w64-mingw32', '--sysroot=' + sysroot, '-femulated-tls']
        probe = subprocess.run(cxx + ['-x', 'c++', '-std=c++17', '-fsyntax-only', '-'], input='#include <thread>\nint main(){}\n',
                               capture_output=True, text=True)
        if probe.returncode == 0:
            return cxx, [gxx], windres, 'clang++ for x86_64-w64-mingw32 (sysroot %s), linked by %s' % (sysroot, os.path.basename(gxx))
        if want == 'clang':
            sys.exit('this clang++ cannot compile for x86_64-w64-mingw32:\n' + probe.stderr[:2000])
    # GCC: SSE2 scalar arithmetic is its default on x86-64; said anyway, the build depends on it
    return [gxx, '-mfpmath=sse', '-msse2'], [gxx], windres, os.path.basename(gxx)


def compile_all(jobs, cxx, max_jobs):
    """jobs: (source, flags, object, dependencies).  Returns False when one failed."""
    todo = []
    for source, flags, target, deps in jobs:
        stamp = target + '.flags'
        line = ' '.join(cxx + flags)
        stale = not os.path.exists(target) or not os.path.exists(stamp) or open(stamp).read() != line
        if not stale:
            at = os.path.getmtime(target)
            stale = any(os.path.getmtime(p) > at for p in [source] + list(deps) if os.path.exists(p))
        if stale:
            todo.append((source, flags, target, stamp, line))
    start = time.time()

    def one(job):
        source, flags, target, stamp, line = job
        if source.endswith('.rc'):
            command = flags + [source, '-O', 'coff', '-o', target]
        else:
            command = NICE + cxx + flags + ['-c', source, '-o', target]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            open(stamp, 'w').write(line)
        return source, result.returncode, result.stderr, '-w' in flags

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_jobs) as pool:
        for source, code, err, quiet in pool.map(one, todo):
            if code != 0:
                failed += 1
                print('FAILED %s\n%s' % (source, err[:5000]))
            elif err.strip() and not quiet:
                print(err[:1500])
    print('compiled %d of %d files in %.0f s%s' % (len(todo), len(jobs), time.time() - start, ' (%d FAILED)' % failed if failed else ''))
    return failed == 0


def link(command, objects, libs, out):
    result = subprocess.run(command + ['-o', out] + objects + libs, capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED %s\n%s' % (out, result.stderr[:6000]))
        return False
    # clang and GCC pad the name strings of type information differently; ld says so for every
    # one it merges with libstdc++'s copy ("duplicate section ... has different size") and keeps one
    lines = [l for l in result.stderr.splitlines() if l.strip()]
    padding = [l for l in lines if 'duplicate section' in l and '.rdata$_ZTS' in l]
    other = [l for l in lines if l not in padding]
    print('linked %s (%d bytes)%s%s' % (os.path.relpath(out, ROOT), os.path.getsize(out),
                                        '; %d type-name sections merged with a different padding' % len(padding) if padding else '',
                                        '; warnings:\n' + '\n'.join(other)[:1500] if other else ''))
    return True


def game_jobs(gen, objdir, flags):
    deps = [os.path.join(RT, n) for n in ('recomp.h', 'fpu.h', 'mmi.h')] + [os.path.join(gen, 'funcs.h')]
    return [(os.path.join(gen, n), flags, os.path.join(objdir, 'g_' + n[:-4] + '.o'), deps)
            for n in sorted(os.listdir(gen)) if n.endswith('.cpp')]


def source_jobs(sources, objdir, search):
    """sources: (path, flags, prefix)."""
    return [(path, flags, os.path.join(objdir, prefix + os.path.splitext(os.path.basename(path))[0] + '.o'), includes_of(path, search))
            for path, flags, prefix in sources]


def translate(args):
    """The game translated into this build's own directory (win/gen-app or win/gen-orig).

    Other builds translate into local/recomp-out/gen-app whenever they run; a copy of our own
    cannot change under a compile.  recomp.py writes into a scratch directory and only files
    whose content changed are taken over, so an unchanged translation recompiles nothing."""
    if args.no_game and os.path.exists(os.path.join(args.gen, 'funcs.h')):
        return True
    scratch = args.gen + '.new'
    shutil.rmtree(scratch, ignore_errors=True)
    command = [sys.executable, os.path.join(RECOMP, 'recomp.py'), '--out', scratch]
    if not args.original:
        command += ['--pnach', os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach'),
                    '--sections', os.path.join(ROOT, 'tools', 'play-net', 'sections-suggested.txt')]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-3000:] + result.stderr[-3000:])
        return False
    os.makedirs(args.gen, exist_ok=True)
    changed = 0
    for name in os.listdir(scratch):
        new, old = os.path.join(scratch, name), os.path.join(args.gen, name)
        if not os.path.exists(old) or open(new, 'rb').read() != open(old, 'rb').read():
            shutil.copyfile(new, old)
            changed += 1
    for name in os.listdir(args.gen):
        if not os.path.exists(os.path.join(scratch, name)):
            os.remove(os.path.join(args.gen, name))
    shutil.rmtree(scratch, ignore_errors=True)
    print('translated the game into %s (%d files changed)' % (os.path.relpath(args.gen, ROOT), changed))
    return True


def build_standin(args):
    """The same sources for macOS x86-64, with the Mac's compiler: what can be run here."""
    if sys.platform != 'darwin':
        sys.exit('--standin is for a Mac (it builds x86-64 programs that run under Rosetta)')
    out = os.path.join(WIN, 'standin')
    os.makedirs(out, exist_ok=True)
    args.original, args.gen = True, os.path.join(WIN, 'gen-orig')    # the unpatched game: the one compared with the rig
    if not translate(args):
        return False
    gen = args.gen
    ok = True
    # run: the headless runtime, for x86-64 and - from the same sources at the same moment, as the
    # control it is compared with - for arm64; test: the driver of difftest.py for x86-64
    for name, arch, defines, opt, sources in (
            ('run', 'x86_64', [], '-O2', RUNTIME + ['host_posix.cpp', 'sound_null.cpp', 'main_headless.cpp']),
            ('run', 'arm64', [], '-O2', RUNTIME + ['host_posix.cpp', 'sound_null.cpp', 'main_headless.cpp']),
            ('test', 'x86_64', ['-DRECOMP_TEST', '-DFPU_PS2'], '-O1', ['test_driver.cpp'])):
        short = 'x64' if arch == 'x86_64' else arch
        cxx = ['clang++', '-arch', arch]
        objdir = os.path.join(WIN, 'obj-standin-%s-%s' % (name, short))
        os.makedirs(objdir, exist_ok=True)
        flags = ['-std=c++17', args.opt or opt, '-fwrapv', '-w'] + FP + ['-I', RT, '-I', gen] + defines
        jobs = game_jobs(gen, objdir, flags) + source_jobs([(os.path.join(RT, s), flags, 'rt_') for s in sources], objdir, [RT, gen])
        if not compile_all(jobs, cxx, args.jobs):
            return False
        program = os.path.join(out, ('rta_native_' if name == 'run' else 'recomp_test_') + short)
        ok = link(cxx, [j[2] for j in jobs], ['-lpthread'], program) and ok
    flags = ['-std=c++17', '-O2', '-fwrapv', '-w'] + FP + ['-I', RT]
    for arch in ('x86_64', 'arm64'):
        program = os.path.join(out, 'fpcheck_' + ('x64' if arch == 'x86_64' else arch))
        result = subprocess.run(['clang++', '-arch', arch] + flags + [os.path.join(WINSRC, 'fpcheck.cpp'), '-o', program], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[:3000])
            ok = False
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', choices=('clang', 'gcc'))
    parser.add_argument('--opt')
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--original', action='store_true', help='the unpatched game (the shared translation in gen/)')
    parser.add_argument('--no-game', action='store_true', help='do not translate the game again (use what win/gen-app holds)')
    parser.add_argument('--headless', action='store_true', help='only fpcheck.exe and rta_native.exe')
    parser.add_argument('--standin', action='store_true', help='build the macOS x86-64 stand-in instead')
    parser.add_argument('--symbols', action='store_true', help='keep the symbol table in the programs')
    parser.add_argument('--no-translation', action='store_true', help='interpret VU1 even when its main program is translated')
    args = parser.parse_args()
    args.jobs = max(1, min(8, args.jobs))
    if args.standin:
        return 0 if build_standin(args) else 1
    args.gen = os.path.join(WIN, 'gen-orig' if args.original else 'gen-app')
    suffix = '_orig' if args.original else ''
    if not translate(args):
        return 1
    cxx, linker, windres, what = find_toolchain(args.compiler)
    tag = 'clang' if 'clang' in os.path.basename(cxx[0]) else 'gcc'
    print('toolchain: ' + what)
    objdir = os.path.join(WIN, 'obj-%s%s' % (tag, suffix))
    os.makedirs(objdir, exist_ok=True)
    opt = args.opt or '-O2'
    rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + FP + WIN_DEFINES + ['-I', RT, '-I', args.gen]
    render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + FP + WIN_DEFINES + ['-I', RENDER]
    app_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + WIN_DEFINES + ['-I', HERE, '-I', WINSRC, '-I', RENDER, '-I', RT]
    search = [HERE, WINSRC, RENDER, RT, SOUND, args.gen]

    game = game_jobs(args.gen, objdir, rt_flags)
    runtime = source_jobs([(os.path.join(RT, n), rt_flags, 'rt_') for n in RUNTIME + ['host_win32.cpp']], objdir, search)
    # rta_native.exe: rt/main_headless.cpp with native.py's defaults (the executable out of the disc image, a card directory)
    headless = source_jobs([(os.path.join(RT, 'sound_null.cpp'), rt_flags, 'rt_'),
                            (os.path.join(WINSRC, 'headless_main.cpp'), rt_flags + ['-I', HERE], 'h_'),
                            (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'h_')], objdir, search)
    fpcheck = source_jobs([(os.path.join(WINSRC, 'fpcheck.cpp'), rt_flags, 'a_')], objdir, search)
    resource = []
    if windres and os.path.exists(os.path.join(WINSRC, 'rta_app.rc')):
        resource = [(os.path.join(WINSRC, 'rta_app.rc'), [windres, '-I', WINSRC], os.path.join(objdir, 'a_resource.o'),
                     [os.path.join(WINSRC, 'rta_app.manifest')])]
    jobs = game + runtime + headless + fpcheck + resource
    app = []
    if not args.headless:
        translation = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
        vu1 = translation if os.path.exists(translation) and not args.no_translation else os.path.join(RENDER, 'vu1_none.cpp')
        app = source_jobs(
            [(os.path.join(RENDER, n), render_flags, 'r_') for n in RENDER_CORE] + [(vu1, render_flags, 'r_')] +
            # backend_gl.cpp is written against Qt's QOpenGLExtraFunctions; app/win/ has the two headers it
            # includes, over WGL (no Qt on Windows)
            [(os.path.join(RENDER, 'backend_gl.cpp'), render_flags + ['-I', WINSRC], 'r_'),
             (os.path.join(SOUND, 'sound_rta.cpp'), rt_flags + ['-I', SOUND], 'rt_'),
             (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
             (os.path.join(HERE, 'win_main.cpp'), app_flags, 'a_'),
             (os.path.join(HERE, 'pad_win.cpp'), app_flags, 'a_'),
             (os.path.join(WINSRC, 'wgl.cpp'), app_flags, 'a_')], objdir, search)
        jobs += app
    if not compile_all(jobs, cxx, args.jobs):
        return 1
    objs = lambda group: [j[2] for j in group]
    # -static: libstdc++, libgcc and winpthreads inside the program; -s: no symbol table in the
    # program (the map beside the objects has the addresses a crash report names)
    def flags_for(name):
        return ['-static'] + ([] if args.symbols else ['-s']) + ['-Wl,-Map,' + os.path.join(objdir, name + '.map')]
    ok = link(linker + flags_for('fpcheck'), objs(fpcheck) + objs(resource), [], os.path.join(WIN, 'fpcheck.exe'))
    ok = link(linker + flags_for('rta_native'), objs(game) + objs(runtime) + objs(headless) + objs(resource), ['-lwinmm'],
              os.path.join(WIN, 'rta_native%s.exe' % suffix)) and ok
    if app:
        ok = link(linker + flags_for('rta_app'), objs(game) + objs(runtime) + objs(app) + objs(resource), WIN_LIBS,
                  os.path.join(WIN, 'rta_app%s.exe' % suffix)) and ok
    for name in ('play.bat', 'README.txt'):
        if os.path.exists(os.path.join(WINSRC, name)):
            shutil.copyfile(os.path.join(WINSRC, name), os.path.join(WIN, name))
    if ok and app and not args.original:
        # exactly what a tester gets, in one folder
        package = os.path.join(WIN, 'rta-windows')
        os.makedirs(package, exist_ok=True)
        for name in ('rta_app.exe', 'rta_native.exe', 'fpcheck.exe', 'play.bat', 'README.txt'):
            shutil.copyfile(os.path.join(WIN, name), os.path.join(package, name))
        print('the folder to give a tester: ' + os.path.relpath(package, ROOT))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
