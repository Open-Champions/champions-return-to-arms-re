#!/usr/bin/env python3
"""doctor_home.py - is this checkout able to build and test?  Run it before a build.

  python3 tools/doctor_home.py                # every area
  python3 tools/doctor_home.py native godot   # only these (--list names them)
  python3 tools/doctor_home.py --all          # also look at every file of the checkout (about a minute)

Why it exists (docs/issues/workspace-move.md): on 2026-10-13 the checkout lay in a folder
that iCloud Drive synchronises, the disk filled, and macOS EVICTED tens of thousands of
files: such a file is still listed with its size, but a read of it blocks, possibly for
ever.  The checkout was moved; what was evicted is missing in the new place until it has
been fetched or made again.

For the directories a build or a test of each area reads, this script reports
  - evicted files and directories (the "dataless" flag): a build that reads one can HANG;
  - key files that are not there: the build or test would FAIL;
  - things that are not there but only make a build weaker (WARN).
It asks for names, sizes and flags only (lstat / stat): it never opens a file, so it can
not hang itself, wherever it is run.  Exit code 0: nothing would hang or fail; 1: something
would.  It holds no game data and prints none.
"""
import os
import shutil
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.realpath(ROOT)
HOME = os.path.expanduser('~')
SF_DATALESS = 0x40000000
ELF_BYTES = 5777312             # SLUS_209.73 of the US v2.00 disc
MIN_FREE_GB = 6
DISC = os.environ.get('RTA_DISC') or os.path.join(HOME, 'Library', 'Application Support', 'Play-RTA', 'Champions - Return to Arms (v2.00).iso')
QT = os.environ.get('RTA_QT_PREFIX') or '/opt/homebrew/opt/qtbase'
OUT = 'local/recomp-out'
S12 = OUT + '/app-test/s12'
SPIKE = 'local/godot-spike'
KIT = os.environ.get('SOAK_KIT') or OUT + '/soak/farm3.nosync/kit'
SIGNIN = 'SLUS-20973_4028A55F_signin.pnach'

lines, counts = [], {'FAIL': 0, 'WARN': 0, 'ok': 0}


def say(level, area, text):
    counts[level] += 1
    lines.append('[%-4s] %-8s %s' % (level, area, text))


def full(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def state(path):
    """'absent', 'evicted', 'dangling' (a link to nothing) or 'there' - by lstat/stat only."""
    try:
        st = os.lstat(full(path))
    except OSError:
        return 'absent'
    if getattr(st, 'st_flags', 0) & SF_DATALESS:
        return 'evicted'
    if stat.S_ISLNK(st.st_mode):
        try:
            st = os.stat(full(path))
        except OSError:
            return 'dangling'
        if getattr(st, 'st_flags', 0) & SF_DATALESS:
            return 'evicted'
    return 'there'


def need(area, paths, level='FAIL', why=''):
    """Each path must be there.  Returns True when all are."""
    bad = [(p, state(p)) for p in paths if state(p) != 'there']
    for p, s in bad:
        say('FAIL' if s == 'evicted' else level, area, '%s: %s%s' % (p, s, (' - ' + why) if why else ''))
    return not bad


def scan(area, paths):
    """Evicted files below these directories (never descending into an evicted directory)."""
    found, seen = [], 0
    stack = [full(p) for p in paths if state(p) == 'there']
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                st = os.lstat(e.path)
            except OSError:
                continue
            seen += 1
            if getattr(st, 'st_flags', 0) & SF_DATALESS:
                found.append(e.path)
            elif stat.S_ISDIR(st.st_mode):
                stack.append(e.path)
    if found:
        say('FAIL', area, '%d evicted files or directories in what it reads (a read can hang), e.g. %s' % (
            len(found), ', '.join(os.path.relpath(p, ROOT) for p in sorted(found)[:5])))
    else:
        say('ok', area, 'no evicted file among %d entries looked at' % seen)


def tools(area, names):
    for name in names:
        if not shutil.which(name):
            say('FAIL', area, 'the program `%s` is not on the PATH' % name)


def whole(tree, keys):
    return all(state(os.path.join(tree, k)) == 'there' for k in keys)


def general():
    if 'icloud-old' in REAL:
        say('FAIL', 'home', 'this is the old, evicted folder (%s): never build or read here; the home is ~/champions-re' % REAL)
    synced = [d for d in ('Desktop', 'Documents', os.path.join('Library', 'Mobile Documents')) if REAL.startswith(os.path.join(HOME, d) + os.sep)]
    if synced:
        say('WARN', 'home', 'the checkout lies under ~/%s, which iCloud may synchronise and evict: %s' % (synced[0], REAL))
    else:
        say('ok', 'home', REAL)
    link = os.path.join(HOME, 'Desktop', 'champions-re')
    if os.path.realpath(link) != REAL:
        say('WARN', 'home', '~/Desktop/champions-re does not lead here: scripts and notes with the old path will not find this checkout')
    free = shutil.disk_usage(REAL).free / 1e9
    say('FAIL' if free < MIN_FREE_GB else 'ok', 'disk', '%.1f GB free%s' % (free, ' - below %d GB: do not build' % MIN_FREE_GB if free < MIN_FREE_GB else ''))
    s = state(DISC)
    if s != 'there':
        say('FAIL', 'disc', 'the disc image is %s: %s (set RTA_DISC)' % (s, DISC))
    need('home', ['ghidra_funcs.tsv', 'names.tsv', 'patches/SLUS-20973_4028A55F.pnach', 'tools/play-net/sections-suggested.txt'])


def native():
    a = 'native'
    tools(a, ['clang++'])
    if need(a, ['SLUS_209.73'], why='copy it out of your disc image: python3 tools/recomp/disc.py extract SLUS_209.73 --out .'):
        if os.stat(full('SLUS_209.73')).st_size != ELF_BYTES:
            say('FAIL', a, 'SLUS_209.73 is not %d bytes: not the executable of the US v2.00 disc' % ELF_BYTES)
    need(a, ['tools/recomp/recomp.py', 'tools/recomp/build.py', 'tools/recomp/app/build.py', 'tools/recomp/rt/runtime.cpp', 'tools/play-net/src/RtaOnline.cpp'])
    need(a, [os.path.join(QT, 'lib', 'QtCore.framework'), os.path.join(QT, 'lib', 'QtGui.framework')], why='Qt 6 (brew install qtbase)')
    need(a, [OUT + '/gen-vu/vu1_fast.cpp', OUT + '/gen-vu/vu1_translated.cpp'], 'WARN',
         'the build works without it, the vertex programs are then interpreted (slower); docs/issues/native-render-speed.md')
    if state('local/' + SIGNIN) != 'there' and not os.environ.get('RTA_SIGNIN_PATCH'):
        others = [p for p in ('local/dist-web/play/' + SIGNIN, 'local/rel.nosync/site-pages/' + SIGNIN) if state(p) == 'there']
        say('WARN', a, 'local/%s is not there: app/build.py and play.sh then leave the sign-in skip out (two words fewer, no Internet Game). '
            'A file of that name is at %s: export RTA_SIGNIN_PATCH=<its path>' % (SIGNIN, ' and '.join(others) or 'no other place'))
    need(a, [OUT + '/bin/rta_app'], 'WARN', 'not built: python3 tools/recomp/app/build.py')
    scan(a, ['tools/recomp', 'tools/play-net', 'patches', 'symbols'] + [OUT + '/' + d for d in ('gen', 'gen-app', 'gen-vu', 'obj-run', 'obj-rta_native_fix', 'obj-app', 'obj-app_orig', 'bin')])


def checks():
    a = 'checks'    # the standing checks of docs/issues/native-app.md section 12 (s12/verify.sh)
    need(a, [S12 + '/' + n for n in ('verify.sh', 'det.sh', 'tour.sh', 'rig.sh', 'mkdet.py', 'detcmp.py', 'mktour.py')] +
         ['local/recomp-speed/out/det-fast.rig', S12 + '/det/prev-fast/sums.txt', S12 + '/det/prev-plain-fast/sums.txt', S12 + '/tour/prev-fast/sums.txt',
          OUT + '/app-test/rigsnd/boot-rig.tsv', OUT + '/app-test/rigsnd/boot-rig-breaks.log', OUT + '/app-test/rigsnd/rc.py',
          OUT + '/fight3.rig', OUT + '/app-test/merge/rig-final-compare.txt', OUT + '/bin/rta_app_orig'])
    if state('local/play-out/tourplan.py') != 'there':
        alt = whole('', ['local/rehome/tour-from-route.sh', S12 + '/tour/f3-fast/route.rig'])
        say('WARN' if alt else 'FAIL', a, 'local/play-out/tourplan.py is not there: s12/tour.sh (mktour.py) fails' +
            ('; run the tour from the last verified route: local/rehome/tour-from-route.sh NAME PROGRAM' if alt else ''))
    scan(a, [S12, OUT + '/app-test/rigsnd', OUT + '/app-test/merge', 'local/recomp-speed/out'])


def emulator():
    a = 'emulator'
    tools(a, ['git', 'cmake', 'ninja'])
    need(a, ['tools/play-net/build.sh', 'tools/play-net/play.sh', 'tools/play-net/play-net.patch', 'tools/play-net/src'])
    need(a, [os.path.join(QT, 'lib', 'cmake', 'Qt6')], why='Qt 6 (brew install qtbase)')
    keys = ['.git/HEAD', '.git/index', 'CMakeLists.txt', 'Source/ui_qt/CMakeLists.txt', 'Source/PS2VM.cpp', 'deps/CodeGen/CMakeLists.txt', 'deps/Framework/build_cmake']
    src = os.environ.get('RTA_PLAY_SOURCE') or 'local/play-playable'
    build = os.environ.get('RTA_PLAY_BUILD') or 'local/play-playable-build'
    if state(src) == 'absent':
        say('ok', a, '%s is not there: tools/play-net/build.sh clones Play! into it (network)' % src)
    elif whole(src, keys):
        say('ok', a, 'the source tree %s has its key files' % src)
        scan(a, [src, build])
    else:
        gone = [k for k in keys if state(os.path.join(src, k)) != 'there']
        fresh = 'local/play-playable-rehome'
        hint = ('; a whole tree is at %s: export RTA_PLAY_SOURCE=%s RTA_PLAY_BUILD=%s-build' % (fresh, full(fresh), full(fresh))) if whole(fresh, keys) else \
            '; clone anew into an empty directory: RTA_PLAY_SOURCE=DIR RTA_PLAY_BUILD=DIR-build tools/play-net/build.sh'
        say('FAIL', a, 'the source tree %s is incomplete (%s ...): tools/play-net/build.sh fails there%s' % (src, ', '.join(gone[:3]), hint))
    app = os.environ.get('RTA_PLAY_APP') or os.path.join(build, 'Source/ui_qt/Play.app/Contents/MacOS/Play')
    if not os.environ.get('RTA_PLAY_APP') and state(app) != 'there' and state('local/play-playable-build/Source/ui_qt/Play.app/Contents/MacOS/Play') == 'there':
        app = 'local/play-playable-build/Source/ui_qt/Play.app/Contents/MacOS/Play'
    need(a, [app], 'WARN', 'the application is not built: tools/play-net/build.sh')


def lobby():
    a = 'lobby'
    keys = ['build.sh', 'run.sh', 'Source/main.cpp', 'Dependency/sqlite/sqlite3.c', 'Include/Network', 'Source/Network']
    places = [p for p in ('server/upstream', 'server/upstream-fresh') if state(p) == 'there']
    good = [p for p in places if whole(p, keys)]
    for p in places:
        if p not in good:
            say('WARN', a, '%s is incomplete (%s ...): sh build.sh fails there' % (p, ', '.join(k for k in keys if state(os.path.join(p, k)) != 'there')[:60]))
    if not good:
        say('FAIL', a, 'no whole checkout of the lobby server: clone TrustlessMike/Champions-Reborn-Server (branch macos-port) to server/upstream-fresh')
        return
    say('ok', a, 'whole checkout: %s' % good[-1])
    need(a, [good[-1] + '/bin/config.ini'], why='the server reads it')
    need(a, [good[-1] + '/bin/champions-server'], 'WARN', 'not built: sh build.sh')
    need(a, [good[-1] + '/bin/database/game.db'], 'WARN', 'no database: the server starts with an empty one')
    scan(a, good)


def godot():
    a = 'godot'
    tools(a, ['clang++', 'cmake', 'ninja', 'patch'])
    need(a, ['tools/godot/build.py', 'tools/godot/recomp.patch', 'tools/godot/extension/CMakeLists.txt', 'tools/godot/lib/host_main.cpp', 'tools/recomp/net2/session.cpp',
             SPIKE + '/deps/godot-cpp/src/CMakeLists.txt', SPIKE + '/deps/godot-editor/Godot.app/Contents/MacOS/Godot'])
    if state(SPIKE + '/src/recomp') != 'there':     # `snapshot` then needs the compiled game
        need(a, [OUT + '/obj-rta_native_fix/table.o', OUT + '/obj-run/table.o', OUT + '/gen-app/funcs.h', OUT + '/gen/funcs.h'],
             why='no snapshot and no compiled game to take one from: python3 tools/recomp/app/build.py (and --original)')
    else:
        need(a, [SPIKE + '/src/game-fix/table.o', SPIKE + '/src/game-orig/table.o', SPIKE + '/src/game-fix/funcs.h'], why='the snapshot has no compiled game: build.py snapshot --refresh')
    need(a, [SPIKE + '/lib/librta_game.dylib', SPIKE + '/bin/rtag_host', SPIKE + '/project/bin/rta_godot.macos.template_debug.dylib', SPIKE + '/project/project.godot'],
         'WARN', 'not built or staged: python3 tools/godot/build.py all')
    scan(a, ['tools/godot', 'tools/recomp/net2'] + [SPIKE + '/' + d for d in ('src', 'deps', 'lib', 'bin', 'project', 'build')])


def soak():
    a = 'soak'
    need(a, ['tools/recomp/soak/farm.py', 'tools/recomp/soak/build_soak.py'])
    need(a, [KIT + '/' + n for n in ('SLUS_209.73', 'symbols.tsv', 'poolmask.txt', 'trees.json', 'farm.py', 'pair-a/vfs', 'pair-b/vfs', 'bin')], why='the farm\'s kit (SOAK_KIT)')
    need(a, [OUT + '/soak/rt-frozen/rt_runtime.o'], 'WARN', 'the frozen runtime objects are not there: build_soak.py --rt frozen cannot link (--rt live builds with the runtime as it is now)')
    scan(a, [KIT, 'tools/recomp/soak'])


def proof():
    a = 'proof'
    need(a, ['tools/recomp/proof/build_proof.py', 'tools/recomp/proof/proof_driver.cpp'])
    need(a, [OUT + '/proof/build/bin/' + n for n in ('rta_proof', 'proof_driver')], 'WARN', 'not built: tools/recomp/proof/build_proof.py')
    need(a, [OUT + '/proof/snap/TAKEN', OUT + '/proof/snap/recomp/recomp.py', OUT + '/proof/snap/recomp/rt/iop.cpp'], 'WARN',
         'the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)')
    need(a, ['local/rig-build/rta_rig'], 'WARN', 'the emulator rig is not built (tools/rig/README.md)')
    scan(a, ['tools/recomp/proof', OUT + '/proof/build', OUT + '/proof/snap'])


def analysis():
    a = 'analysis'
    need(a, ['SLUS_209.73'], why='the Python tools read the executable')
    need(a, ['disasm/text.asm'], 'WARN', 'python3 tools/gen_disasm.py SLUS_209.73')
    if need(a, ['decomp/all/index.tsv'], 'WARN', 'no decompiler output: README.md, "Getting started" step 3 (Ghidra)'):
        have = sum(1 for e in os.scandir(full('decomp/all')) if e.name.endswith('.c'))
        if have < 7000:         # one file per function, about 7,700
            say('WARN', a, 'decomp/all holds %d of about 7,700 decompiled functions: make it again (README.md, "Getting started" step 3) before relying on it' % have)
    scan(a, ['tools', 'symbols', 'patches', 'docs', 'disasm', 'decomp'])


AREAS = {'native': native, 'checks': checks, 'emulator': emulator, 'lobby': lobby, 'godot': godot, 'soak': soak, 'proof': proof, 'analysis': analysis}


def main():
    args = sys.argv[1:]
    if '--list' in args or '-h' in args or '--help' in args:
        print(__doc__ + '\nareas: ' + ' '.join(AREAS))
        return 0
    everything = '--all' in args
    wanted = [a for a in args if not a.startswith('--')] or list(AREAS)
    unknown = [a for a in wanted if a not in AREAS]
    if unknown:
        print('unknown area: %s (areas: %s)' % (' '.join(unknown), ' '.join(AREAS)))
        return 2
    general()
    for name in wanted:
        AREAS[name]()
    if everything:
        scan('all', [''])
    print('\n'.join(lines))
    print('doctor_home: %d would hang or fail, %d warnings, %d fine  -> %s' % (
        counts['FAIL'], counts['WARN'], counts['ok'], 'DO NOT BUILD the failing areas' if counts['FAIL'] else 'able to build and test'))
    return 1 if counts['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
