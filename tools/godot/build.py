#!/usr/bin/env python3
"""build.py - the translated game as a library, and the Godot project around it.

  python3 tools/godot/build.py snapshot        # copy tools/recomp's sources and the compiled game, apply recomp.patch
  python3 tools/godot/build.py lib             # local/godot-spike/lib/librta_game.dylib and bin/rtag_host
  python3 tools/godot/build.py lib --original  # librta_game_orig.dylib: the game as it is on the disc (the one
                                               # that is compared tick for tick with the original in the rig)
  python3 tools/godot/build.py extension       # the GDExtension (cmake + ninja, against the pinned godot-cpp)
  python3 tools/godot/build.py extension --release   # ... for an exported application (template_release)
  python3 tools/godot/build.py project         # stage the Godot project: local/godot-spike/project/
  python3 tools/godot/build.py all             # snapshot (if there is none), lib, extension, project
  python3 tools/godot/build.py export          # a macOS application: local/godot-spike/export/RtaGodot.app (needs
                                               # `extension --release` and the export templates, see below)
  python3 tools/godot/build.py patch           # maintenance: write recomp.patch from the snapshot as it is now
  options: --opt -O1|-O2   --refresh (snapshot: take tools/recomp as it is now, again)   --jobs N (default 8)
           --from ROOT (snapshot: sources and compiled game from another root of the same layout, e.g. a work
           copy in which a patch that changes the translation is applied and built: local/recomp-fp/root)

What goes where.  Nothing derived from the game leaves local/:
  local/godot-spike/src/recomp.orig/   tools/recomp/{rt,render,sound,app} as they were when the snapshot was taken
  local/godot-spike/src/recomp/        the same with tools/godot/recomp.patch applied: what is compiled
  local/godot-spike/src/game-fix/      the compiled translated game with the fix set (objects of
  local/godot-spike/src/game-orig/     local/recomp-out/obj-rta_native_fix, obj-run) and the headers they were made with
  local/godot-spike/src/gen-vu/        the VU1 programs translated ahead of time
  local/godot-spike/obj-*/             objects
  local/godot-spike/lib/               librta_game.dylib, librta_game_orig.dylib
  local/godot-spike/bin/rtag_host      the test host (tools/godot/lib/host_main.cpp)
  local/godot-spike/build/             the extension's cmake directories
  local/godot-spike/project/           the Godot project as it is run: tools/godot/project/ copied, and bin/
                                       with the extension and the game library beside it
  local/godot-spike/export/            the project as it is exported (no test settings, no game library in it),
                                       and RtaGodot.app: Godot's export with the game library put into
                                       Contents/Frameworks afterwards - the application holds the translated
                                       game and stays on this machine
The export needs Godot's export templates for 4.5.2 (deps/godot-templates/Godot_v4.5.2-stable_export_templates.tpz,
from the same release as the editor, checked against its SHA-512); only templates/macos.zip is taken out of it.
Why a snapshot: tools/recomp is another agent's and changes while this is built; the library is
made from one consistent copy, and what it needs changed there is tools/godot/recomp.patch.

The translated game itself is not compiled here: `python3 tools/recomp/app/build.py` (and
`--original`) makes it from your own disc's executable; this script takes its objects.
Uses the compiler, cmake and ninja already on the machine; nothing is downloaded (the two
downloads the Godot side needs - the editor and godot-cpp - are described in
docs/issues/native-godot.md).
"""
import argparse
import concurrent.futures
import filecmp
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RECOMP = os.path.join(ROOT, 'tools', 'recomp')
RECOMP_OUT = os.path.join(ROOT, 'local', 'recomp-out')
# RTA_GODOT_OUT=local/NAME: build into another directory beside the shared one (the owner's local/godot-spike stays as it
# is); the downloads (godot-cpp, the editor, the export templates) are taken from local/godot-spike/deps all the same
OUT = os.path.abspath(os.environ.get('RTA_GODOT_OUT', os.path.join(ROOT, 'local', 'godot-spike')))
DEPS = os.path.join(ROOT, 'local', 'godot-spike', 'deps')
SRC = os.path.join(OUT, 'src')
SNAP = os.path.join(SRC, 'recomp')
SNAP_ORIG = os.path.join(SRC, 'recomp.orig')
LIB = os.path.join(HERE, 'lib')
PATCH = os.path.join(HERE, 'recomp.patch')
PARTS = ('rt', 'render', 'sound', 'app', 'net', 'net2')    # net, net2: the network and a room of our own (fix-set library only)
GAMES = {'fix': ('obj-rta_native_fix', 'gen-app'), 'orig': ('obj-run', 'gen')}
RENDER_CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp', 'worldfill.cpp']
RUNTIME = ['runtime.cpp', 'iop.cpp', 'script.cpp']
NICE = ['nice', '-n', '10']
EXPORTS = ['rtag_api_version', 'rtag_has', 'rtag_start', 'rtag_set_pad', 'rtag_step', 'rtag_poll', 'rtag_run', 'rtag_audio_pull',
           'rtag_memory', 'rtag_fields', 'rtag_info', 'rtag_ended', 'rtag_exit_code', 'rtag_stop', 'rtag_set_option',
           'rtag_controls_hud', 'rtag_mouse', 'rtag_mouse_button', 'rtag_fill_get', 'rtag_texture_names']
# A room of our own (tools/recomp/net2/session.h, game.h): the fix-set library carries the one copy of net2 in the
# process - the session client, the carrier of the game's datagrams and the direct launch - and hands out its plain-C
# functions under their own names, for the portal (docs/issues/native-rendezvous.md 5.1).
NET2_EXPORTS = ['net2_block', 'net2_blocked', 'net2_chat', 'net2_close', 'net2_debug', 'net2_delete_everything', 'net2_error_text',
                'net2_friend_accept', 'net2_friend_add', 'net2_friend_add_id', 'net2_friend_decline', 'net2_friend_remove', 'net2_friends',
                'net2_game_attach', 'net2_game_choose', 'net2_game_launch', 'net2_game_launch_direct', 'net2_game_state', 'net2_game_status',
                'net2_game_stop', 'net2_host', 'net2_invite', 'net2_invite_accept', 'net2_invite_dismiss', 'net2_invites', 'net2_join',
                'net2_join_friend', 'net2_kick', 'net2_leave', 'net2_local_characters', 'net2_me', 'net2_next_event', 'net2_open', 'net2_poll',
                'net2_ready', 'net2_recent', 'net2_requests', 'net2_room', 'net2_session', 'net2_set', 'net2_set_character', 'net2_set_game',
                'net2_set_name', 'net2_set_options', 'net2_start', 'net2_unblock']


def copy_sources(to, recomp):
    """tools/recomp/{rt,render,sound,app,net,net2}: the files of each directory, not what lies below."""
    for part in PARTS:
        if not os.path.isdir(os.path.join(recomp, part)):
            continue
        os.makedirs(os.path.join(to, part), exist_ok=True)
        for name in sorted(os.listdir(os.path.join(recomp, part))):
            path = os.path.join(recomp, part, name)
            if os.path.isfile(path) and re.search(r'\.(cpp|h|mm|inc|txt)$', name) and ' ' not in name:
                shutil.copy2(path, os.path.join(to, part, name))


def snapshot(args):
    if os.path.isdir(SNAP) and not args.refresh:
        print('the snapshot is there (%s); --refresh takes tools/recomp as it is now' % SNAP)
        return 0
    # --from ROOT: another root with the same layout (tools/recomp, local/recomp-out) - a work copy in which a patch
    # that changes the translation (hle.txt) has been applied and built, e.g. the view modes: local/recomp-fp/root
    root = os.path.abspath(args.source) if args.source else ROOT
    recomp, recomp_out = os.path.join(root, 'tools', 'recomp'), os.path.join(root, 'local', 'recomp-out')
    for d in (SNAP, SNAP_ORIG):
        shutil.rmtree(d, ignore_errors=True)
    copy_sources(SNAP_ORIG, recomp)
    copy_sources(SNAP, recomp)
    # the one-step online's file of the emulator application, which net/online.cpp includes as ../../play-net/src/RtaOnline.h
    # (linked as it is, as app/build.py does): beside the snapshot where that path finds it
    playnet = os.path.join(SRC, 'play-net', 'src')
    shutil.rmtree(os.path.join(SRC, 'play-net'), ignore_errors=True)
    os.makedirs(playnet)
    for name in ('RtaOnline.h', 'RtaOnline.cpp', 'RtaNet.h'):
        source = os.path.join(root, 'tools', 'play-net', 'src', name)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(playnet, name))
    for game, (objects, gen) in GAMES.items():
        source, to = os.path.join(recomp_out, objects), os.path.join(SRC, 'game-' + game)
        shutil.rmtree(to, ignore_errors=True)
        if not os.path.isdir(source):
            print('no %s: run tools/recomp/app/build.py%s first; the %s library cannot be built' % (source, ' --original' if game == 'orig' else '', game))
            continue
        os.makedirs(to)
        count = 0
        # the game's objects by their exact names (a file synchroniser leaves copies "c_003 2.o" beside them)
        for name in sorted(os.listdir(source)):
            if re.fullmatch(r'c_\d+\.o', name) or name in ('table.o', 'hle_weak.o', 'patches.o'):
                shutil.copy2(os.path.join(source, name), os.path.join(to, name))
                count += 1
        for name in ('funcs.h',):
            shutil.copy2(os.path.join(recomp_out, gen, name), os.path.join(to, name))
        print('game-%s: %d objects from %s' % (game, count, objects))
    vu = os.path.join(SRC, 'gen-vu')
    shutil.rmtree(vu, ignore_errors=True)
    os.makedirs(vu)
    for name in ('vu1_fast.cpp', 'vu1_translated.cpp'):
        path = os.path.join(recomp_out, 'gen-vu', name)
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(vu, name))
    # (the new files of tools/godot/core are copied in by `lib`).  A patch file that holds notes and no hunk - everything
    # it had is merged into tools/recomp - is not handed to patch(1), which calls such a file garbage and fails.
    if os.path.exists(PATCH) and re.search(r'^(diff -ru |--- )', open(PATCH).read(), re.M):
        result = subprocess.run(['patch', '-p1', '-d', SNAP, '-i', PATCH, '--no-backup-if-mismatch'], capture_output=True, text=True)
        print(result.stdout.strip())
        if result.returncode != 0:
            print('recomp.patch does not apply to tools/recomp as it is now:\n' + result.stderr)
            return 1
    open(os.path.join(SRC, 'SNAPSHOT.txt'), 'w').write('taken %s from %s (objects: %s)\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), recomp, recomp_out))
    print('snapshot taken: ' + SNAP)
    return 0


def make_patch(args):
    result = subprocess.run(['diff', '-ru', 'recomp.orig', 'recomp'], cwd=SRC, capture_output=True, text=True)
    result.stdout = ''.join(line + '\n' for line in result.stdout.splitlines() if not line.startswith('Only in '))    # the new files are in core/
    text = re.sub(r'^(---|\+\+\+) (\S+)\t.*$', r'\1 \2', result.stdout, flags=re.M)    # no time stamps
    notes = ''
    if os.path.exists(PATCH):                           # the notes at its head (what patch(1) skips) stay
        old = open(PATCH).read()
        cut = old.find('diff -ru ')
        notes = old[:cut] if cut > 0 else old if cut < 0 else ''      # no hunk in it: all of it is notes
    open(PATCH, 'w').write(notes + text)
    print('wrote %s (%d lines)' % (PATCH, text.count('\n')))
    return 0


def includes_of(source, dirs, seen=None):
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


def compile_all(jobs, objdir, dirs, workers):
    """jobs: (source, flags, prefix).  Returns the objects, or None when something failed."""
    os.makedirs(objdir, exist_ok=True)
    objects, todo = [], []
    for source, flags, prefix in jobs:
        target = os.path.join(objdir, prefix + os.path.splitext(os.path.basename(source))[0] + '.o')
        objects.append(target)
        stamp = target + '.flags'
        deps = [source] + includes_of(source, dirs)
        if not os.path.exists(target) or any(os.path.getmtime(p) > os.path.getmtime(target) for p in deps) \
                or not os.path.exists(stamp) or open(stamp).read() != ' '.join(flags):
            todo.append((source, flags, target, stamp))

    def compile_one(job):
        source, flags, target, stamp = job
        result = subprocess.run(NICE + ['clang++'] + flags + ['-c', source, '-o', target], capture_output=True, text=True)
        if result.returncode == 0:
            open(stamp, 'w').write(' '.join(flags))
        return source, result.returncode, result.stderr

    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for source, code, err in pool.map(compile_one, todo):
            if code != 0:
                failed = True
                print('FAILED %s\n%s' % (source, err[:6000]))
            elif err.strip():
                print(err[:3000])
    print('compiled %d of %d files' % (len(todo), len(jobs)))
    return None if failed else objects


def build_lib(args):
    if not os.path.isdir(SNAP):
        print('no snapshot: python3 tools/godot/build.py snapshot')
        return 1
    game = 'orig' if args.original else 'fix'
    game_dir = os.path.join(SRC, 'game-' + game)
    if not os.path.isdir(game_dir):
        print('no compiled game in %s (see `snapshot`)' % game_dir)
        return 1
    rt, render, sound, app = (os.path.join(SNAP, p) for p in PARTS[:4])
    # files proposed for tools/recomp (tools/godot/core/<part>/...) go into the snapshot, where they will live.
    # (None now: render/scene_tap.h and .cpp were merged into tools/recomp/render on 2026-10-13 with the hooks of
    # recomp.patch, so `snapshot` brings them; the directory need not exist, and a new proposal can lie there again.)
    core = os.path.join(HERE, 'core')
    for folder, _, files in os.walk(core):
        for name in files:
            a, b = os.path.join(folder, name), os.path.join(SNAP, os.path.relpath(folder, core), name)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                shutil.copy2(a, b)
    standin = os.path.join(LIB, 'gl_standin')
    opt = args.opt
    render_flags = ['-std=c++17', opt, '-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math', '-Wall', '-Wno-unused-function', '-I', render]
    rt_flags = ['-std=c++17', opt, '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math', '-I', rt, '-I', game_dir]
    lib_flags = ['-std=c++17', opt, '-Wall', '-Wno-unused-function', '-fno-strict-aliasing', '-ffp-contract=off', '-frounding-math',
                 '-I', LIB, '-I', app, '-I', render, '-I', rt] + (['-DRTAG_ORIGINAL'] if args.original else [])
    # What the library can do depends on what the snapshot's core has (recomp.patch, or the shared tree once it is merged):
    # the music's own volume (sound/drivers.cpp: rta_sound_set_music_gain) and the second HUD group (render/gs.h:
    # hide_text - and the translation must wrap the two draw functions: funcs.h then declares orig_001d93b0).
    def has(path, word):
        try:
            return word in open(path, errors='replace').read()
        except OSError:
            return False
    if has(os.path.join(sound, 'drivers.cpp'), 'rta_sound_set_music_gain'):
        lib_flags.append('-DRTAG_HAVE_MUSIC_GAIN')
    hud_text = has(os.path.join(render, 'gs.h'), 'hide_text') and has(os.path.join(game_dir, 'funcs.h'), 'orig_001d93b0')
    if hud_text:
        lib_flags.append('-DRTAG_HAVE_HUD_TEXT')
    gfx_flags = rt_flags + ['-I', app] + ([] if hud_text else ['-DRTA_NO_HUD_TEXT_HOOKS'])
    # the world for a camera inside it (app/fpworld.cpp, render/worldfill.cpp): fpworld.cpp supplies three hooks of the
    # translation (frustum_testBox, world_draw, world_drawChunk), so it is linked only when the translation wraps them
    world = has(os.path.join(app, 'fpworld.cpp'), 'install') and has(os.path.join(game_dir, 'funcs.h'), 'orig_001868a4')
    if world:
        lib_flags.append('-DRTAG_HAVE_WORLD')
    core = [n for n in RENDER_CORE if os.path.exists(os.path.join(render, n))]
    jobs = [(os.path.join(render, n), render_flags, 'r_') for n in core + ['scene_tap.cpp']]
    vu = os.path.join(SRC, 'gen-vu')
    translated, fast = os.path.join(vu, 'vu1_translated.cpp'), os.path.join(vu, 'vu1_fast.cpp')
    jobs.append((translated if os.path.exists(translated) else os.path.join(render, 'vu1_none.cpp'), render_flags, 'r_'))
    jobs.append((fast if os.path.exists(fast) else os.path.join(render, 'vu1_fast_none.cpp'), render_flags, 'r_'))
    jobs.append((os.path.join(render, 'backend_gl.cpp'), render_flags + ['-I', standin], 'r_'))
    jobs.append((os.path.join(render, 'texpack.cpp'), render_flags + ['-DRTA_NO_QIMAGE'], 'r_'))
    jobs += [(os.path.join(rt, n), rt_flags, 'rt_') for n in RUNTIME]
    jobs.append((os.path.join(LIB, 'host_godot.cpp'), rt_flags, 'rt_'))
    jobs.append((os.path.join(sound, 'sound_rta.cpp'), rt_flags + ['-I', sound, '-I', LIB, '-DRTA_AUDIO_HOST="audio_host.inc"'], 'rt_'))
    jobs.append((os.path.join(app, 'app_rt.cpp'), rt_flags + ['-I', app], 'a_'))
    jobs.append((os.path.join(app, 'gfx_rt.cpp'), gfx_flags, 'a_'))
    if os.path.exists(os.path.join(app, 'fpview.cpp')):      # the view modes (a snapshot with tools/recomp/app/fpview.patch applied)
        jobs.append((os.path.join(app, 'fpview.cpp'), rt_flags + ['-I', app], 'a_'))
    if world:
        jobs.append((os.path.join(app, 'fpworld.cpp'), rt_flags + ['-I', app, '-I', render], 'a_'))
    # the look controls (fpcontrols.h): nothing of the runtime in them but iface.h; rtag.cpp finds the header by itself
    if os.path.exists(os.path.join(app, 'fpcontrols.cpp')):
        jobs.append((os.path.join(app, 'fpcontrols.cpp'), ['-std=c++17', opt, '-Wall', '-I', app, '-I', rt], 'a_'))
        # the souls-style combat mode (soulscombat.h, docs/issues/native-souls-combat.md): it needs the controls (lock-on)
        if os.path.exists(os.path.join(app, 'soulscombat.cpp')):
            jobs.append((os.path.join(app, 'soulscombat.cpp'), rt_flags + ['-I', app, '-I', render], 'a_'))
            lib_flags.append('-DRTAG_HAVE_SOULS')
    else:
        lib_flags.append('-DRTAG_NO_CONTROLS')
    if not args.original:
        jobs.append((os.path.join(app, 'film.cpp'), rt_flags + ['-I', app], 'a_'))     # the films: only this translation leaves their entries open
    # the network and a room of our own, as rta_app has them (app/build.py): the fix-set translation leaves the network
    # library's entries of net/hle-online.txt to net/netdrv.cpp; net2/launch.cpp starts the game's own lockstep session
    # from a room.  Nothing opens a socket until a host asks for a room (rtag_start "--opt net2=..." or net2_open).
    net, net2 = os.path.join(SNAP, 'net'), os.path.join(SNAP, 'net2')
    has_net2 = not args.original and os.path.exists(os.path.join(net2, 'launch.cpp')) and has(os.path.join(net, 'netdrv.cpp'), 'net2hook') \
        and os.path.exists(os.path.join(SRC, 'play-net', 'src', 'RtaOnline.cpp'))
    if has_net2:
        jobs += [(os.path.join(net, n), rt_flags, 'n_') for n in ('netdrv.cpp', 'online.cpp')]
        jobs.append((os.path.join(SRC, 'play-net', 'src', 'RtaOnline.cpp'), rt_flags, 'n_'))
        plain = ['-std=c++17', opt, '-Wall', '-I', net2]
        # tls.cpp: the link to the service inside TLS (the system's Network and Security frameworks), when the snapshot has it
        jobs += [(os.path.join(net2, n), plain, 'n2_') for n in ('session.cpp', 'session_mock.cpp', 'session_net.cpp', 'carrier.cpp', 'tls.cpp', 'cardchars.cpp',
                                                                    'clicmd.cpp') if n != 'tls.cpp' or os.path.exists(os.path.join(net2, n))]
        jobs.append((os.path.join(net2, 'launch.cpp'), rt_flags + ['-I', net2], 'n2_'))
        lib_flags.append('-DRTAG_HAVE_NET2')
    jobs.append((os.path.join(LIB, 'rtag.cpp'), lib_flags, 'g_'))
    jobs.append((os.path.join(LIB, 'scene_export.cpp'), lib_flags, 'g_'))
    jobs.append((os.path.join(LIB, 'gl_offscreen_mac.cpp'), lib_flags, 'g_'))
    objects = compile_all(jobs, os.path.join(OUT, 'obj-' + game), [LIB, app, render, rt, sound, game_dir, vu, os.path.join(SNAP, 'net'), os.path.join(SNAP, 'net2')], args.jobs)
    if objects is None:
        return 1
    link = [os.path.join(game_dir, n) for n in sorted(os.listdir(game_dir)) if n.endswith('.o')]
    os.makedirs(os.path.join(OUT, 'lib'), exist_ok=True)
    name = 'librta_game.dylib' if game == 'fix' else 'librta_game_orig.dylib'
    final = os.path.join(OUT, 'lib', name)
    out = final + '.link%d' % os.getpid()
    exports = os.path.join(OUT, 'obj-' + game, 'exports.txt')
    open(exports, 'w').write(''.join('_%s\n' % e for e in EXPORTS + (NET2_EXPORTS if has_net2 else [])))
    result = subprocess.run(NICE + ['clang++', '-dynamiclib', '-o', out] + objects + link +
                            ['-framework', 'OpenGL', '-framework', 'Network', '-framework', 'Security', '-framework', 'CoreFoundation', '-lz', '-lpthread',
                             '-Wl,-exported_symbols_list,' + exports, '-Wl,-install_name,@rpath/' + name],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED\n' + result.stderr[:6000])
        if os.path.exists(out):
            os.remove(out)
        return 1
    os.replace(out, final)
    print('linked %s (%d bytes)' % (final, os.path.getsize(final)))
    # the test host
    os.makedirs(os.path.join(OUT, 'bin'), exist_ok=True)
    host = os.path.join(OUT, 'bin', 'rtag_host')
    result = subprocess.run(NICE + ['clang++', '-std=c++17', '-O2', '-Wall', '-I', LIB, os.path.join(LIB, 'host_main.cpp'), '-o', host], capture_output=True, text=True)
    if result.returncode != 0:
        print('rtag_host FAILED\n' + result.stderr[:4000])
        return 1
    return 0


def build_extension(args):
    target = 'template_release' if args.release else 'template_debug'
    cpp = os.path.join(DEPS, 'godot-cpp', 'src')
    if not os.path.exists(os.path.join(cpp, 'CMakeLists.txt')):
        print('no godot-cpp at %s: see docs/issues/native-godot.md, "From nothing"' % cpp)
        return 1
    build = os.path.join(OUT, 'build', 'extension-' + target)
    command = ['cmake', '-S', os.path.join(HERE, 'extension'), '-B', build, '-G', 'Ninja', '-DGODOT_CPP_DIR=' + cpp, '-DCMAKE_BUILD_TYPE=Release',
               '-DGODOTCPP_TARGET=' + target, '-DRTA_GODOT_OUTPUT_DIR=' + os.path.join(OUT, 'project', 'bin')]
    for step in (command, ['cmake', '--build', build, '--parallel', str(args.jobs)]):
        result = subprocess.run(NICE + step, capture_output=True, text=True)
        if result.returncode != 0:
            print((result.stdout[-6000:] + result.stderr[-3000:]))
            return 1
    print('extension built: %s' % os.path.join(OUT, 'project', 'bin', 'rta_godot.macos.%s.dylib' % target))
    return 0


def stage_project(args):
    """The project as Godot runs it: scripts, scenes and shaders from tools/godot/project (copied, so that
    Godot's import cache and its .uid files stay out of the repository), bin/ with the libraries."""
    source, to = os.path.join(HERE, 'project'), os.path.join(OUT, 'project')
    count = 0
    for folder, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in ('.godot', 'bin')]
        rel = os.path.relpath(folder, source)
        os.makedirs(os.path.join(to, rel), exist_ok=True)
        for name in files:
            if name.endswith(('.uid', '.import')) or name in ('.DS_Store', 'export_presets.cfg'):
                continue
            a, b = os.path.join(folder, name), os.path.join(to, rel, name)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                shutil.copy2(a, b)
                count += 1
    os.makedirs(os.path.join(to, 'bin'), exist_ok=True)
    for name in ('librta_game.dylib', 'librta_game_orig.dylib'):
        a, b = os.path.join(OUT, 'lib', name), os.path.join(to, 'bin', name)
        if os.path.exists(a) and (not os.path.exists(b) or os.path.getmtime(a) > os.path.getmtime(b)):
            # a new file put over the name (not written into the old one): a program that has the old one loaded
            # (another agent's test, the portal's) keeps running on it
            shutil.copy2(a, b + '.new%d' % os.getpid())
            os.replace(b + '.new%d' % os.getpid(), b)
            count += 1
    # the per-level look presets made by presets.py from a walk through the levels (game output: OUT/presets, not in
    # the repository) go beside the tracked hand-tuning in presets/
    made = os.path.join(OUT, 'presets', 'levels.cfg')
    if os.path.exists(made):
        os.makedirs(os.path.join(to, 'presets'), exist_ok=True)
        if not os.path.exists(os.path.join(to, 'presets', 'levels.cfg')) or not filecmp.cmp(made, os.path.join(to, 'presets', 'levels.cfg'), shallow=False):
            shutil.copy2(made, os.path.join(to, 'presets', 'levels.cfg'))
            count += 1
    # The staged copy is the one test runs start: its window is small and says what it is from the first
    # moment (the script gives it its final title).  An exported application is made from a copy without this.
    open(os.path.join(to, 'override.cfg'), 'w').write(
        '[application]\n\nconfig/name="AGENT TEST - the translated game in Godot"\n\n[display]\n\nwindow/size/viewport_width=480\n'
        'window/size/viewport_height=360\nwindow/size/no_focus=true\n')
    print('project staged: %s (%d files copied)' % (to, count))
    return 0


def export_app(args):
    godot = os.environ.get('RTA_GODOT', os.path.join(DEPS, 'godot-editor', 'Godot.app', 'Contents', 'MacOS', 'Godot'))
    tpz = os.path.join(DEPS, 'godot-templates', 'Godot_v4.5.2-stable_export_templates.tpz')
    template = os.path.join(DEPS, 'godot-templates', 'templates', 'macos.zip')
    if not os.path.exists(template):
        if not os.path.exists(tpz):
            print('no export templates at %s (docs/issues/native-godot.md, "Export")' % tpz)
            return 1
        subprocess.run(['unzip', '-q', '-o', tpz, 'templates/macos.zip', 'templates/version.txt', '-d', os.path.dirname(tpz)], check=True)
    release = os.path.join(OUT, 'project', 'bin', 'rta_godot.macos.template_release.dylib')
    game = os.path.join(OUT, 'lib', 'librta_game.dylib')
    for needed in (release, game):
        if not os.path.exists(needed):
            print('missing %s (build.py lib, build.py extension --release)' % needed)
            return 1
    export = os.path.join(OUT, 'export')
    project = os.path.join(export, 'project')
    shutil.rmtree(project, ignore_errors=True)
    source = os.path.join(HERE, 'project')
    for folder, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in ('.godot', 'bin')]
        rel = os.path.relpath(folder, source)
        os.makedirs(os.path.join(project, rel), exist_ok=True)
        for name in files:
            if not name.endswith(('.uid', '.import')) and name not in ('.DS_Store', 'override.cfg'):
                shutil.copy2(os.path.join(folder, name), os.path.join(project, rel, name))
    made = os.path.join(OUT, 'presets', 'levels.cfg')     # the look presets of presets.py (game output: this machine's application only)
    if os.path.exists(made):
        os.makedirs(os.path.join(project, 'presets'), exist_ok=True)
        shutil.copy2(made, os.path.join(project, 'presets', 'levels.cfg'))
    os.makedirs(os.path.join(project, 'bin'))
    for name in ('rta_godot.macos.template_release.dylib', 'rta_godot.macos.template_debug.dylib'):
        shutil.copy2(os.path.join(OUT, 'project', 'bin', name), os.path.join(project, 'bin', name))
    presets = os.path.join(project, 'export_presets.cfg')
    text = open(presets).read().replace('custom_template/release=""', 'custom_template/release="%s"' % template)
    open(presets, 'w').write(text)
    env = dict(os.environ)
    for key, name in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
        env[key] = os.path.join(OUT, 'godot-home', name)
        os.makedirs(env[key], exist_ok=True)
    app = os.path.join(export, 'RtaGodot.app')
    shutil.rmtree(app, ignore_errors=True)
    log = os.path.join(export, 'export.log')
    with open(log, 'w') as sink:
        # the bounded editor start fills the import cache (and avoids the first-import shutdown crash), then the export
        subprocess.run(NICE + [godot, '--headless', '--path', project, '--editor', '--quit-after', '120', '--frame-delay', '50'], env=env, stdout=sink, stderr=sink)
        result = subprocess.run(NICE + [godot, '--headless', '--path', project, '--export-release', 'macOS', app], env=env, stdout=sink, stderr=sink)
    if result.returncode != 0 or not os.path.isdir(app):
        print('the export failed (%d): see %s' % (result.returncode, log))
        return 1
    # the game: beside the extension, inside the application - which therefore must not leave this machine
    frameworks = os.path.join(app, 'Contents', 'Frameworks')
    os.makedirs(frameworks, exist_ok=True)
    shutil.copy2(game, os.path.join(frameworks, 'librta_game.dylib'))
    subprocess.run(['xattr', '-cr', app])               # a synchronised folder hangs attributes on files that a signature does not allow
    signed = subprocess.run(['codesign', '--force', '--deep', '-s', '-', app], capture_output=True, text=True)      # ad hoc: this Mac only
    if signed.returncode != 0:
        print('codesign: ' + signed.stderr.strip())
        return 1
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(app) for f in fs)
    print('exported %s (%.1f MB; the translated game is inside: it stays on this machine)' % (app, size / 1048576.0))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('what', choices=['snapshot', 'patch', 'lib', 'extension', 'project', 'all', 'export'])
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--original', action='store_true')
    parser.add_argument('--release', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--from', dest='source', default='', help='snapshot: another root (tools/recomp + local/recomp-out) to take sources and objects from')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    args.jobs = max(1, min(args.jobs, 8))               # never more: other jobs share the machine
    steps = {'snapshot': [snapshot], 'patch': [make_patch], 'lib': [build_lib], 'extension': [build_extension], 'project': [stage_project],
             'all': [snapshot, build_lib, build_extension, stage_project], 'export': [export_app]}[args.what]
    for step in steps:
        code = step(args)
        if code:
            return code
    return 0


if __name__ == '__main__':
    sys.exit(main())
