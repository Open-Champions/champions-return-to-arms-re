#!/usr/bin/env python3
"""build_win.py - build the native game for Windows x86-64 (and the x86-64 stand-in for macOS).

  python3 tools/recomp/app/build_win.py              # everything into local/recomp-out/win/
  python3 tools/recomp/app/build_win.py --headless   # fpcheck.exe and rta_native.exe only
  python3 tools/recomp/app/build_win.py --standin    # the same sources for macOS x86-64 (runs under
                                                     # Rosetta): win/standin/rta_native_x64, recomp_test_x64,
                                                     # fpcheck_x64, and rta_native_arm64, fpcheck_arm64 as
                                                     # the controls from the same sources
  python3 tools/recomp/app/build_win.py --reference  # after --standin, with RTA_DISC: runs the tester's check script
                                                     # (rta-windows/boot-check.rig) in the arm64 Mac build of the
                                                     # same sources and writes rta-windows/boot-check-mac.txt
  python3 tools/recomp/app/build_win.py --mac        # after --standin: the macOS window program (arm64, Qt) from this
                                                     # build's own translation and the sources as they are now, into
                                                     # win/mac/rta_app - app/build.py's program without touching the
                                                     # shared local/recomp-out/bin - and win/mac/rta_app_pngread, the
                                                     # same with the art pack read by render/png_read.h instead of QImage
  python3 tools/recomp/app/build_win.py --pngcheck   # win/standin/pngcheck: png_read.h against QImage (app/win/pngcheck.cpp)
  options: --compiler clang|gcc   (default clang when it can target Windows, see below)
           --original             the unpatched game (gen/) instead of the fix set (gen-app/)
           --no-game              do not translate the game again first (recomp.py, about 2 s)
           --no-net               rta_app.exe without the network (tools/recomp/net) and without the sign-in patch
           --opt -O1|-O2          --jobs N (default 8, never more: other jobs share the machine)
           --symbols              keep the symbol table in the programs (default: stripped; a map
                                  of each program is written beside its objects either way)

What it makes (docs/issues/native-windows.md says what was proven and what was not run):
  rta_app.exe      the game in a window: Win32 window, OpenGL 4.1 core through WGL, XInput
                   and keyboard, WASAPI (app/win_main.cpp, app/pad_win.cpp, app/win/*,
                   sound/audio_out_win.cpp, render/backend_gl.cpp unchanged); the picture
                   options of docs/issues/native-graphics.md (app/gfx_rt.cpp, app/settings.h,
                   render/texpack.cpp with render/png_read.h in place of Qt's QImage); the
                   network (net/netdrv.cpp over net/sock.h's Winsock body, net/online.cpp,
                   tools/play-net/src/RtaOnline.cpp, net/online_win.cpp)
  rta_native.exe   the machine with nothing attached (app/win/headless_main.cpp): boots and runs scripts
  fpcheck.exe      the game's floating-point operations as a table of checksums (app/win/fpcheck.cpp)
  rta-windows/     the folder a tester gets: the three programs, play.bat and README.txt (from
                   app/win/), boot-check.rig (the rig's boot script with addresses for names)

Toolchain.  On macOS: `brew install mingw-w64` (GCC, binutils, the MinGW-w64 headers and
libraries, UCRT).  --compiler clang compiles with the Mac's own clang++ for the target
x86_64-w64-mingw32 against that sysroot and links with the MinGW g++ driver: the same
compiler and the same x86-64 code generator as the stand-in that is run under Rosetta.
--compiler gcc compiles with x86_64-w64-mingw32-g++ and names its programs rta_app_gcc.exe,
rta_native_gcc.exe, fpcheck_gcc.exe (a second build to try if the first does not start).  On Windows itself (MSYS2 UCRT64 or
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
NET = os.path.join(RECOMP, 'net')
ONLINE = os.path.join(ROOT, 'tools', 'play-net', 'src', 'RtaOnline.cpp')      # the one-step online, linked as it is
NET_HLE = os.path.join(NET, 'hle-online.txt')
QT = '/opt/homebrew/opt/qtbase'                         # --mac and --pngcheck only
ON_WINDOWS = os.name == 'nt'
NICE = [] if ON_WINDOWS else ['nice', '-n', '10']

# The flags of tools/recomp/build.py and app/build.py.  -ffp-contract=off: no fused
# multiply-add; -frounding-math: the rounding mode is changed at run time (toward zero).
FP = ['-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math']
WIN_DEFINES = ['-D_WIN32_WINNT=0x0A00', '-DWINVER=0x0A00', '-D_USE_MATH_DEFINES', '-DNOMINMAX', '-DWIN32_LEAN_AND_MEAN']
RENDER_CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']
FILM, FILM_HLE = os.path.join(HERE, 'film.cpp'), os.path.join(HERE, 'hle-app.txt')
RUNTIME = ['runtime.cpp', 'iop.cpp', 'script.cpp']
WIN_LIBS = ['-lopengl32', '-lgdi32', '-luser32', '-lole32', '-lwinmm', '-lavrt', '-lshell32', '-ldwmapi']
NET_LIBS = ['-lws2_32', '-liphlpapi', '-ladvapi32']     # Winsock, the list of this computer's addresses, the saved login's access list


def with_net(args):
    """The network is part of the fix-set program unless it was switched off."""
    return not args.original and not getattr(args, 'no_net', False)


def signin_patch():
    """The local sign-in patch (kept outside the repository; nothing of it is printed), or None."""
    path = os.environ.get('RTA_SIGNIN_PATCH', os.path.join(ROOT, 'local', 'SLUS-20973_4028A55F_signin.pnach'))
    return path if os.path.isfile(path) else None


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
    # clang and GCC pad C++ type information (the _ZTS name strings, the _ZTI objects) differently;
    # ld says so for every one it merges with libstdc++'s copy ("duplicate section ... has
    # different size") and keeps one
    lines = [l for l in result.stderr.splitlines() if l.strip()]
    padding = [l for l in lines if 'duplicate section' in l and '.rdata$_ZT' in l and 'different size' in l]
    other = [l for l in lines if l not in padding]
    print('linked %s (%d bytes)%s%s' % (os.path.relpath(out, ROOT), os.path.getsize(out),
                                        '; %d type-information sections merged with a different padding' % len(padding) if padding else '',
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
        # as app/build.py: the film player's library entries are left to app/film.cpp, the
        # network library's to net/netdrv.cpp, and the local sign-in patch is applied when
        # the file is there (a program that does not link the driver - rta_native.exe - gets
        # the translated originals of those entries and is offline as before)
        if os.path.exists(FILM_HLE) and os.path.exists(FILM):
            command += ['--hle-add', FILM_HLE]
        if with_net(args):
            command += ['--hle-add', NET_HLE]
            if signin_patch():
                command += ['--extra-pnach', signin_patch()]
            else:
                print('no sign-in patch in local/: the program will stop with a network error after "Internet Game"')
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


def write_check_script(target):
    """tools/rig/examples/boot-to-hub.rig with every name replaced by its address.

    The boot route of the rig (memory card, front end, character creation, into the first
    level) is written with the project's names for the game's variables; the runtime reads
    them from names.tsv and symbols/*.tsv.  A tester has neither, so the copy that goes into
    the package names addresses.  Lines of the form `<address>\t<name>...` define a name."""
    names = {}
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(
            os.path.join(ROOT, 'symbols', n) for n in os.listdir(os.path.join(ROOT, 'symbols')) if n.endswith('.tsv')):
        for line in open(path, errors='replace'):
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 2 and re.fullmatch(r'[0-9a-fA-F]{6,8}', parts[0]) and re.fullmatch(r'[A-Za-z_]\w*', parts[1]):
                names.setdefault(parts[1], int(parts[0], 16))
    out, replaced = [], set()
    for line in open(os.path.join(ROOT, 'tools', 'rig', 'examples', 'boot-to-hub.rig')):
        code, hash_, comment = line.partition('#')

        def address(match):
            word = match.group(0)
            if word in names and ('_' in word):
                replaced.add(word)
                return '0x%x' % names[word]
            return word
        out.append(re.sub(r'(?<![\w.])[A-Za-z_]\w*', address, code) + hash_ + comment)
    with open(target, 'w') as sink:
        sink.write('# boot-check.rig - made by build_win.py from tools/rig/examples/boot-to-hub.rig: the same script with\n'
                   '# addresses in place of names (%s).\n' % ', '.join(sorted(replaced)))
        sink.writelines(out)
    return len(replaced)


def build_standin(args):
    """The same sources for macOS x86-64, with the Mac's compiler: what can be run here."""
    if sys.platform != 'darwin':
        sys.exit('--standin is for a Mac (it builds x86-64 programs that run under Rosetta)')
    out = os.path.join(WIN, 'standin')
    os.makedirs(out, exist_ok=True)
    gens = {}
    for kind, original in (('gen-orig', True), ('gen-app', False)):
        args.original, args.gen = original, os.path.join(WIN, kind)
        if not translate(args):
            return False
        gens[kind] = args.gen
    args.original = False
    headless = RUNTIME + ['host_posix.cpp', 'sound_null.cpp', 'main_headless.cpp']
    online = [os.path.join(NET, 'netdrv.cpp'), os.path.join(NET, 'online.cpp'), ONLINE]
    ok = True
    # run: the headless runtime with the unpatched game (the one compared with the rig), for
    #      x86-64 and - from the same sources at the same moment, as the control - for arm64;
    # test: the driver of difftest.py for x86-64;
    # fix: the headless runtime with the game as rta_native.exe has it (the fix set), for arm64:
    #      what its report should read on a PC;
    # the same with the network (net/netdrv.cpp over net/sock.h's BSD body, net/online.cpp,
    #      RtaOnline.cpp: what net/build_online.py builds as bin/rta_native_online), for x86-64
    #      and for arm64: the programs of a lobby game between two copies on this Mac
    for name, arch, kind, defines, opt, sources, extra, program in (
            ('run', 'x86_64', 'gen-orig', [], '-O2', headless, [], 'rta_native_x64'),
            ('run', 'arm64', 'gen-orig', [], '-O2', headless, [], 'rta_native_arm64'),
            ('test', 'x86_64', 'gen-orig', ['-DRECOMP_TEST', '-DFPU_PS2'], '-O1', ['test_driver.cpp'], [], 'recomp_test_x64'),
            ('fix', 'arm64', 'gen-app', [], '-O2', headless, [], 'rta_native_fix_arm64'),
            ('fix', 'arm64', 'gen-app', [], '-O2', headless, online, 'rta_native_online_arm64'),
            ('fix', 'x86_64', 'gen-app', [], '-O2', headless, online, 'rta_native_online_x64')):
        if extra and getattr(args, 'no_net', False):
            continue
        gen = gens[kind]
        short = 'x64' if arch == 'x86_64' else arch
        cxx = ['clang++', '-arch', arch]
        objdir = os.path.join(WIN, 'obj-standin-%s-%s' % (name, short))
        os.makedirs(objdir, exist_ok=True)
        flags = ['-std=c++17', args.opt or opt, '-fwrapv', '-w'] + FP + ['-I', RT, '-I', gen] + defines
        jobs = game_jobs(gen, objdir, flags) + source_jobs([(os.path.join(RT, s), flags, 'rt_') for s in sources] +
                                                           [(path, flags, 'n_') for path in extra], objdir, [RT, gen, NET])
        if not compile_all(jobs, cxx, args.jobs):
            return False
        ok = link(cxx, [j[2] for j in jobs], ['-lpthread'], os.path.join(out, program)) and ok
    flags = ['-std=c++17', '-O2', '-fwrapv', '-w'] + FP + ['-I', RT]
    for arch in ('x86_64', 'arm64'):
        program = os.path.join(out, 'fpcheck_' + ('x64' if arch == 'x86_64' else arch))
        result = subprocess.run(['clang++', '-arch', arch] + flags + [os.path.join(WINSRC, 'fpcheck.cpp'), '-o', program], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[:3000])
            ok = False
    return ok


def write_readme(package):
    """README.txt for the tester, with the figures of this build in it: the two lines the
    check script must end in (from rta-windows/boot-check-mac.txt) and the patch set every
    copy of this build announces (from win/standin/patch-set.txt); both made by --reference."""
    source = os.path.join(WINSRC, 'README.txt')
    if not os.path.exists(source):
        return
    values = {'@FRAMES_LINE@': '(not made yet: build_win.py --reference)', '@VU0_LINE@': '(not made yet: build_win.py --reference)',
              '@PATCH_SET@': '(not made yet: build_win.py --reference)'}
    reference = os.path.join(package, 'boot-check-mac.txt')
    if os.path.exists(reference):
        for line in open(reference, errors='replace'):
            found = re.match(r'(frames=\d+) wall=.*(fields=\d+ units=\d+)', line)
            if found:
                values['@FRAMES_LINE@'] = '%s wall=...: ... %s' % found.groups()
            if line.startswith('VU0:'):
                values['@VU0_LINE@'] = line.strip()
    figure = os.path.join(WIN, 'standin', 'patch-set.txt')
    if os.path.exists(figure):
        values['@PATCH_SET@'] = open(figure).read().strip()
    text = open(source).read()
    for key, value in values.items():
        text = text.replace(key, value)
    open(os.path.join(package, 'README.txt'), 'wb').write(text.replace('\r\n', '\n').replace('\n', '\r\n').encode())


def build_mac(args):
    """The macOS window program from this build's own translation: app/build.py's rta_app, made
    beside the Windows build instead of in the shared bin/ (other work runs tests against that).

    Game and runtime objects are the stand-in's (obj-standin-fix-arm64: the same sources and
    flags); everything else is compiled here.  Two programs: rta_app (the art pack through
    QImage, as app/build.py makes it) and rta_app_pngread (texpack.cpp with RTA_NO_QIMAGE: the
    pack through render/png_read.h, the reader of the Windows program)."""
    if sys.platform != 'darwin':
        sys.exit('--mac is for a Mac')
    shared = os.path.join(WIN, 'obj-standin-fix-arm64')
    gen = os.path.join(WIN, 'gen-app')
    if not os.path.exists(os.path.join(shared, 'rt_runtime.o')):
        sys.exit('--mac needs build_win.py --standin first (its arm64 objects of the game and the runtime)')
    out, objdir = os.path.join(WIN, 'mac'), os.path.join(WIN, 'obj-mac')
    os.makedirs(out, exist_ok=True)
    os.makedirs(objdir, exist_ok=True)
    opt = args.opt or '-O2'
    qtlib = os.path.join(QT, 'lib')
    qt_flags = ['-F', qtlib] + sum((['-I', os.path.join(qtlib, m + '.framework', 'Headers')] for m in ('QtCore', 'QtGui')), [])
    render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + FP + ['-I', RENDER]
    rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + FP + ['-I', RT, '-I', gen]
    app_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function', '-I', HERE, '-I', RENDER, '-I', RT]
    objc = ['-std=c++17', opt, '-Wall', '-fobjc-arc']
    translation = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
    vu1 = translation if os.path.exists(translation) and not args.no_translation else os.path.join(RENDER, 'vu1_none.cpp')
    sources = [(os.path.join(RENDER, n), render_flags, 'r_') for n in RENDER_CORE] + [
        (vu1, render_flags, 'r_'),
        (os.path.join(RENDER, 'backend_gl.cpp'), render_flags + qt_flags, 'r_'),
        (os.path.join(SOUND, 'sound_rta.cpp'), rt_flags + ['-I', SOUND], 'rt_'),
        (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
        (os.path.join(HERE, 'gfx_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
        (FILM, rt_flags + ['-I', HERE], 'a_'),
        (os.path.join(NET, 'netdrv.cpp'), rt_flags, 'n_'),
        (os.path.join(NET, 'online.cpp'), rt_flags, 'n_'),
        (ONLINE, rt_flags, 'n_'),
        (os.path.join(NET, 'online_mac.mm'), objc + ['-I', NET], 'n_'),
        (os.path.join(HERE, 'app_main.cpp'), app_flags + qt_flags, 'a_'),
        (os.path.join(HERE, 'pad_mac.mm'), objc + ['-I', HERE, '-I', RT], 'a_')]
    search = [HERE, RENDER, RT, SOUND, NET, gen]
    common = source_jobs(sources, objdir, search)
    with_qt = source_jobs([(os.path.join(RENDER, 'texpack.cpp'), render_flags + qt_flags, 'r_')], objdir, search)
    own = source_jobs([(os.path.join(RENDER, 'texpack.cpp'), render_flags + ['-DRTA_NO_QIMAGE'], 'rp_')], objdir, search)
    cxx = ['clang++', '-arch', 'arm64']
    if not compile_all(common + with_qt + own, cxx, args.jobs):
        return False
    game = [os.path.join(shared, n) for n in sorted(os.listdir(shared))
            if n.endswith('.o') and (n.startswith('g_') or n in ('rt_runtime.o', 'rt_iop.o', 'rt_script.o', 'rt_host_posix.o'))]
    frameworks = sum((['-framework', f] for f in ('QtCore', 'QtGui', 'GameController', 'AppKit', 'Foundation')), [])
    libs = ['-F', qtlib] + frameworks + ['-Wl,-rpath,' + qtlib, '-lpthread']
    ok = link(cxx, game + [j[2] for j in common + with_qt], libs, os.path.join(out, 'rta_app'))
    return link(cxx, game + [j[2] for j in common + own], libs, os.path.join(out, 'rta_app_pngread')) and ok


def build_pngcheck(args):
    """app/win/pngcheck.cpp: render/png_read.h against QImage over folders of PNG files (macOS, Qt)."""
    out = os.path.join(WIN, 'standin')
    os.makedirs(out, exist_ok=True)
    qtlib = os.path.join(QT, 'lib')
    command = NICE + ['clang++', '-std=c++17', '-O2', '-Wall', '-F', qtlib] + \
        sum((['-I', os.path.join(qtlib, m + '.framework', 'Headers')] for m in ('QtCore', 'QtGui')), []) + \
        ['-I', RENDER, os.path.join(WINSRC, 'pngcheck.cpp'), '-o', os.path.join(out, 'pngcheck'),
         '-framework', 'QtCore', '-framework', 'QtGui', '-Wl,-rpath,' + qtlib, '-lpthread']
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stderr[:3000] if result.returncode else 'built ' + os.path.relpath(os.path.join(out, 'pngcheck'), ROOT))
    return result.returncode == 0


def make_reference(args):
    """What rta_native.exe should print for the check script: the same sources as an arm64 Mac program print it."""
    binary = os.path.join(WIN, 'standin', 'rta_native_fix_arm64')
    package = os.path.join(WIN, 'rta-windows')
    disc = os.environ.get('RTA_DISC')
    if not os.path.exists(binary) or not disc:
        sys.exit('--reference needs build_win.py --standin first, and RTA_DISC set to the disc image')
    os.makedirs(package, exist_ok=True)
    script = os.path.join(package, 'boot-check.rig')
    write_check_script(script)
    card = os.path.join(WIN, 'standin', 'card-reference')
    shutil.rmtree(card, ignore_errors=True)         # the script expects a blank memory card
    done = subprocess.run(NICE + [binary, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--disc', disc, '--card', card, '--script', script],
                          capture_output=True, text=True)
    text = done.stdout + done.stderr
    open(os.path.join(package, 'boot-check-mac.txt'), 'w').write(text)
    for line in text.splitlines():
        if line.startswith(('frames=', 'VU0:')):
            print('reference: ' + line)
    print('wrote %s (%d lines, exit %d)' % (os.path.relpath(os.path.join(package, 'boot-check-mac.txt'), ROOT), len(text.splitlines()), done.returncode))
    # the patch set a copy of this build announces to other players: the network driver says it
    # at start-up (the stand-in with the network, a few frames, nothing sent anywhere)
    online = os.path.join(WIN, 'standin', 'rta_native_online_arm64')
    if os.path.exists(online):
        scratch = os.path.join(WIN, 'standin', 'net-reference')
        shutil.rmtree(scratch, ignore_errors=True)
        os.makedirs(scratch)
        said = subprocess.run(NICE + [online, 'boot', '--elf', os.path.join(ROOT, 'SLUS_209.73'), '--disc', disc, '--card', os.path.join(scratch, 'card'),
                                      '--fields', '120', '--opt', 'net-data=' + scratch, '--opt', 'net-local-only=1', '--opt', 'online-person=0',
                                      '--opt', 'net-pace=0'], capture_output=True, text=True)
        found = re.search(r'patch set ([0-9a-f]{8}) \((\d+) words\)', said.stdout + said.stderr)
        if found:
            open(os.path.join(WIN, 'standin', 'patch-set.txt'), 'w').write('patch set %s (%s words)\n' % found.groups())
            print('reference: patch set %s (%s words)' % found.groups())
        else:
            print('reference: the stand-in with the network did not say its patch set')
        shutil.rmtree(scratch, ignore_errors=True)
    write_readme(package)
    return done.returncode == 0


def main():
    sys.stdout.reconfigure(line_buffering=True)     # progress shows in a log file while it runs
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', choices=('clang', 'gcc'))
    parser.add_argument('--opt')
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--original', action='store_true', help='the unpatched game (the shared translation in gen/)')
    parser.add_argument('--no-game', action='store_true', help='do not translate the game again (use what win/gen-app holds)')
    parser.add_argument('--headless', action='store_true', help='only fpcheck.exe and rta_native.exe')
    parser.add_argument('--standin', action='store_true', help='build the macOS x86-64 stand-in instead')
    parser.add_argument('--reference', action='store_true', help='run the check script in the arm64 Mac build: what rta_native.exe should print')
    parser.add_argument('--symbols', action='store_true', help='keep the symbol table in the programs')
    parser.add_argument('--no-translation', action='store_true', help='interpret VU1 even when its main program is translated')
    parser.add_argument('--no-net', action='store_true', help='without the network and the sign-in patch')
    parser.add_argument('--mac', action='store_true', help='the macOS window program from this build\'s translation, into win/mac/')
    parser.add_argument('--pngcheck', action='store_true', help='build the comparison of png_read.h with QImage')
    args = parser.parse_args()
    args.jobs = max(1, min(8, args.jobs))
    if args.pngcheck:
        return 0 if build_pngcheck(args) else 1
    if args.mac:
        return 0 if build_mac(args) else 1
    if args.standin:
        return 0 if build_standin(args) else 1
    if args.reference:
        return 0 if make_reference(args) else 1
    args.gen = os.path.join(WIN, 'gen-orig' if args.original else 'gen-app')
    if not translate(args):
        return 1
    cxx, linker, windres, what = find_toolchain(args.compiler)
    tag = 'clang' if 'clang' in os.path.basename(cxx[0]) else 'gcc'
    # the programs of the default build have plain names; the others say what they are
    suffix = ('_orig' if args.original else '') + ('_gcc' if tag == 'gcc' and not ON_WINDOWS else '')
    print('toolchain: ' + what)
    objdir = os.path.join(WIN, 'obj-%s%s' % (tag, '_orig' if args.original else ''))
    os.makedirs(objdir, exist_ok=True)
    opt = args.opt or '-O2'
    rt_flags = ['-std=c++17', opt, '-fwrapv', '-w'] + FP + WIN_DEFINES + ['-I', RT, '-I', args.gen]
    render_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + FP + WIN_DEFINES + ['-I', RENDER]
    app_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function'] + WIN_DEFINES + ['-I', HERE, '-I', WINSRC, '-I', RENDER, '-I', RT]
    search = [HERE, WINSRC, RENDER, RT, SOUND, NET, args.gen]
    net = with_net(args)

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
             # the art pack: PNG files through render/png_read.h (no Qt, so no QImage)
             (os.path.join(RENDER, 'texpack.cpp'), render_flags + ['-DRTA_NO_QIMAGE'], 'r_'),
             (os.path.join(SOUND, 'sound_rta.cpp'), rt_flags + ['-I', SOUND], 'rt_'),
             (os.path.join(HERE, 'app_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
             # widescreen and the marks for the 2-D layer: the hooks of the 16 view and draw functions in hle.txt
             (os.path.join(HERE, 'gfx_rt.cpp'), rt_flags + ['-I', HERE], 'a_'),
             (os.path.join(HERE, 'win_main.cpp'), app_flags + (['-DRTA_NET', '-I', NET] if net else []), 'a_'),
             ] + ([
             # the network: the driver on net/sock.h's Winsock body, the one-step online (the
             # emulator build's own file, with three POSIX calls supplied by net/posix_win.h),
             # and its questions on the window
             (os.path.join(NET, 'netdrv.cpp'), rt_flags, 'n_'),
             (os.path.join(NET, 'online.cpp'), rt_flags, 'n_'),
             (ONLINE, rt_flags + ['-include', os.path.join(NET, 'posix_win.h')], 'n_'),
             (os.path.join(NET, 'online_win.cpp'), app_flags + ['-I', NET], 'n_')] if net else []) + ([
             # the films (app/film.cpp, when the application has it); <ctime> is given from here:
             # the file's timing aid finds it by itself only on macOS
             (FILM, rt_flags + ['-I', HERE, '-include', 'ctime'], 'a_')] if os.path.exists(FILM) and os.path.exists(FILM_HLE) and not args.original else []) + [
             (os.path.join(HERE, 'pad_win.cpp'), app_flags, 'a_'),
             (os.path.join(WINSRC, 'wgl.cpp'), app_flags, 'a_')], objdir, search)
        # a file given with -include is a dependency the sources do not name
        app = [(source, flags, target, deps + ([os.path.join(NET, 'posix_win.h')] if source == ONLINE else []))
               for source, flags, target, deps in app]
        jobs += app
    if not compile_all(jobs, cxx, args.jobs):
        return 1
    objs = lambda group: [j[2] for j in group]
    # -static: libstdc++, libgcc and winpthreads inside the program; -s: no symbol table in the
    # program (the map beside the objects has the addresses a crash report names)
    def flags_for(name):
        return ['-static'] + ([] if args.symbols else ['-s']) + ['-Wl,-Map,' + os.path.join(objdir, name + '.map')]
    ok = link(linker + flags_for('fpcheck'), objs(fpcheck) + objs(resource), [], os.path.join(WIN, 'fpcheck%s.exe' % suffix))
    ok = link(linker + flags_for('rta_native'), objs(game) + objs(runtime) + objs(headless) + objs(resource), ['-lwinmm'],
              os.path.join(WIN, 'rta_native%s.exe' % suffix)) and ok
    if app:
        ok = link(linker + flags_for('rta_app'), objs(game) + objs(runtime) + objs(app) + objs(resource), WIN_LIBS + (NET_LIBS if net else []),
                  os.path.join(WIN, 'rta_app%s.exe' % suffix)) and ok
    texts = ('play.bat', 'online.bat', 'README.txt', 'server.txt')
    for name in texts:
        if os.path.exists(os.path.join(WINSRC, name)):
            shutil.copyfile(os.path.join(WINSRC, name), os.path.join(WIN, name))
    if ok and app and not args.original:
        # exactly what a tester gets, in one folder (the GCC build's programs beside the others when they exist)
        package = os.path.join(WIN, 'rta-windows')
        os.makedirs(package, exist_ok=True)
        for name in ('rta_app.exe', 'rta_native.exe', 'fpcheck.exe', 'rta_app_gcc.exe', 'fpcheck_gcc.exe') + texts:
            source, target = os.path.join(WIN, name), os.path.join(package, name)
            if name == 'server.txt' and os.path.exists(target):
                continue                    # the tester's (or the builder's) address stays
            if os.path.exists(source) and name in texts:
                # text for Windows: lines end in CR LF (cmd.exe reads a batch file with bare LF unreliably)
                text = open(source, 'rb').read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                open(target, 'wb').write(text)
            elif os.path.exists(source):
                shutil.copyfile(source, target)
        # a program of the second compiler that is older than this build's is not the same program
        newest = os.path.getmtime(os.path.join(WIN, 'rta_app.exe'))
        for name in ('rta_app_gcc.exe', 'fpcheck_gcc.exe'):
            if tag != 'gcc' and os.path.exists(os.path.join(WIN, name)) and os.path.getmtime(os.path.join(WIN, name)) < newest - 3600:
                if os.path.exists(os.path.join(package, name)):
                    os.remove(os.path.join(package, name))
                print('%s is from an earlier build and was left out of the folder (make it again: --compiler gcc)' % name)
        write_check_script(os.path.join(package, 'boot-check.rig'))
        write_readme(package)
        print('the folder to give a tester: ' + os.path.relpath(package, ROOT))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
