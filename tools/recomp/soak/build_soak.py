#!/usr/bin/env python3
"""build_soak.py - the native lockstep build for the soak farm (docs/issues/native-soak.md).

  python3 tools/recomp/soak/build_soak.py --name fix26 --sections tools/play-net/sections-suggested.txt
  python3 tools/recomp/soak/build_soak.py --name nofix
  python3 tools/recomp/soak/build_soak.py --name fix26t --sections ... --instrument trace
  options: --section NAME (repeatable), --less NAME (repeatable: a section of --sections left out),
           --instrument count|trace|none, --rt live|frozen, --jobs N

It is tools/recomp/net/build_net.py's program - the translated game, the runtime, the
network shim netshim.cpp - built in directories of its own and with three additions, none
of which touches tools/recomp/net or tools/recomp/rt:

1. soakhooks.cpp is linked in.  netshim.cpp is compiled with the name of the function its
   tick hook calls (orig_003226e4) changed to soak_tasks_run, so the hooks stand between
   the shim and the game's task pass: after each lockstep tick they put checksums of the
   object pool where the tick log's columns can read them.
2. The generated code is compiled against a copy of rt/recomp.h in which the CALL and CALLR
   macros also count the call by target address (--instrument count, the default: the
   coverage figures of a soak), or keep a shadow call stack and compare watched memory at
   every call boundary (--instrument trace: which function writes a word).  The copy is
   written to local/recomp-out/soak/inc-<kind>/ and comes first on the include path; the
   generated files themselves are the translator's, unchanged.
3. Reads and stores where nothing is answer as the Play! emulator answers them
   (build_net.py --wrap-memory; docs/issues/native-net.md finding 1).

Written: local/recomp-out/gen-soak-NAME (translation), local/recomp-out/soak/obj-NAME,
local/recomp-out/soak/objcache, local/recomp-out/soak/bin/rta_soak-NAME, and
local/recomp-out/soak/rt-frozen (the runtime's objects as first built, for --rt frozen on a
day the runtime's sources are between two states).  Everything is derived from the game
and stays under local/.  Only the compiler on the machine is used.
"""
import argparse
import concurrent.futures
import hashlib
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
SOAK = os.path.join(OUT, 'soak')
RT = os.path.join(RECOMP, 'rt')
NET = os.path.join(RECOMP, 'net')
PNACH = os.path.join(ROOT, 'patches', 'SLUS-20973_4028A55F.pnach')
CODEGEN = ['-std=c++17', '-O2', '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off', '-frounding-math']
WRAPPED = ('rt_load', 'rt_store', 'rt_load128', 'rt_store128')

COUNT_CALL = ('#define CALL(fn, target, site) do { g_site = site; g_soak_calls[((target) >> 2) & 0xFFFFFu]++; BUDGET(); fn(c); } while (0)\n'
              '#define CALLR(target, site) do { u32 t_ = (target); g_site = site; g_soak_calls[(t_ >> 2) & 0xFFFFFu]++; BUDGET(); rt_call(c, t_); } while (0)\n')
TRACE_CALL = ('#define CALL(fn, target, site) do { g_site = site; soak_enter(target); BUDGET(); fn(c); soak_leave(); } while (0)\n'
              '#define CALLR(target, site) do { u32 t_ = (target); g_site = site; soak_enter(t_); BUDGET(); rt_call(c, t_); soak_leave(); } while (0)\n')
DECLS = {'count': 'extern u32 g_soak_calls[];\n', 'trace': 'void soak_enter(u32 target);\nvoid soak_leave();\n'}


def instrumented_header(kind):
    """rt/recomp.h with the runtime build's two call macros replaced; None for the plain header."""
    if kind == 'none':
        return None
    text = open(os.path.join(RT, 'recomp.h')).read()
    old_call = '#define CALL(fn, target, site) do { g_site = site; BUDGET(); fn(c); } while (0)\n'
    old_callr = '#define CALLR(target, site) do { g_site = site; BUDGET(); rt_call(c, target); } while (0)\n'
    if old_call not in text or old_callr not in text:
        raise SystemExit('rt/recomp.h: the CALL / CALLR macros are not the ones this script knows; look at it again')
    text = text.replace(old_call + old_callr, DECLS[kind] + (COUNT_CALL if kind == 'count' else TRACE_CALL))
    directory = os.path.join(SOAK, 'inc-' + kind)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, 'recomp.h')
    if not os.path.exists(path) or open(path).read() != text:
        with open(path, 'w') as sink:
            sink.write(text)
    return directory


def sha1_file(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True)
    parser.add_argument('--pnach', default=PNACH)
    parser.add_argument('--sections', help='file of section names, one per line')
    parser.add_argument('--section', action='append', default=[])
    parser.add_argument('--less', action='append', default=[], help='a section of --sections to leave out')
    parser.add_argument('--instrument', choices=('count', 'trace', 'none'), default='count')
    parser.add_argument('--rt', choices=('live', 'frozen'), default='live')
    parser.add_argument('--jobs', type=int, default=5)
    args = parser.parse_args()

    gen = os.path.join(OUT, 'gen-soak-' + args.name)
    objdir = os.path.join(SOAK, 'obj-' + args.name)
    cache = os.path.join(SOAK, 'objcache')
    frozen = os.path.join(SOAK, 'rt-frozen')
    program = os.path.join(SOAK, 'bin', 'rta_soak-' + args.name)
    for path in (gen, objdir, cache, os.path.dirname(program)):
        os.makedirs(path, exist_ok=True)

    # 1. the sections, and the translation (recomp.py patches a copy of the image itself and
    #    writes patches.cpp, from which the runtime writes the words into memory)
    sections = list(args.section)
    if args.sections:
        sections += [line.strip() for line in open(args.sections) if line.strip() and not line.startswith('#')]
    for name in args.less:
        if name not in sections:
            raise SystemExit('--less: not in the set: %s' % name)
        sections.remove(name)
    command = [sys.executable, os.path.join(RECOMP, 'recomp.py'), '--out', gen, '--hle-add', os.path.join(NET, 'hle-net.txt')]
    own_hle = os.path.join(HERE, 'hle-soak.txt')
    if os.path.exists(own_hle):
        command += ['--hle-add', own_hle]
    if sections:
        listing = os.path.join(SOAK, 'sections-%s.txt' % args.name)
        with open(listing, 'w') as sink:
            sink.write('\n'.join(sections) + '\n')
        command += ['--pnach', args.pnach, '--sections', listing]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout[-3000:] + done.stderr[-3000:])
        return 1
    for line in done.stdout.splitlines():
        if line.startswith(('patched', 'warning', 'entangled', 'instructions emitted as rt_unimpl')):
            print('recomp: ' + line)
    if not sections and os.path.exists(os.path.join(gen, 'patches.cpp')):
        os.remove(os.path.join(gen, 'patches.cpp'))

    # 2. compile
    include = instrumented_header(args.instrument)
    includes = (['-I', include] if include else []) + ['-I', RT, '-I', gen]
    digest = hashlib.sha1()
    for path in [os.path.join(include or RT, 'recomp.h'), os.path.join(RT, 'fpu.h'), os.path.join(RT, 'mmi.h')]:
        digest.update(open(path, 'rb').read())
    base_key = ' '.join(CODEGEN) + digest.hexdigest()
    plain = args.instrument == 'none'

    rt_sources = sorted(os.path.join(RT, n) for n in os.listdir(RT) if n.endswith('.cpp') and n != 'test_driver.cpp')
    rt_digest = hashlib.sha1()
    for path in rt_sources + sorted(os.path.join(RT, n) for n in os.listdir(RT) if n.endswith('.h')):
        rt_digest.update(open(path, 'rb').read())
    rt_note = 'runtime: live sources, runtime.cpp sha1 %s, all sources and headers %s' % (
        sha1_file(os.path.join(RT, 'runtime.cpp')), rt_digest.hexdigest())
    if args.rt == 'frozen':
        if not os.path.exists(os.path.join(frozen, 'note.txt')):
            raise SystemExit('no frozen runtime yet: build once with --rt live')
        rt_note = open(os.path.join(frozen, 'note.txt')).read().strip().replace('live sources', 'frozen objects')

    jobs = []           # (source, object, cache key or None, extra flags)
    for entry in sorted(os.listdir(gen)):
        if entry.endswith('.cpp'):
            source = os.path.join(gen, entry)
            key = hashlib.sha1(base_key.encode() + open(source, 'rb').read()).hexdigest()
            jobs.append((source, os.path.join(objdir, entry[:-4] + '.o'), key, []))
    note = ['-DRTA_NET_RT_NOTE="%s"' % rt_note]
    jobs.append((os.path.join(NET, 'netshim.cpp'), os.path.join(objdir, 'netshim.o'), None,
                 note + ['-DRTA_NET_WRAP_MEMORY', '-Dorig_003226e4=soak_tasks_run', '-Dorig_0019b6e4=soak_vblank']))
    jobs.append((os.path.join(HERE, 'soakhooks.cpp'), os.path.join(objdir, 'soakhooks.o'), None,
                 ['-DSOAK_INSTRUMENT_' + args.instrument.upper()]))
    rt_objects = []
    if args.rt == 'frozen':     # the objects as they were first built, whatever the sources are now
        for entry in sorted(os.listdir(frozen)):
            if entry.endswith('.o'):
                shutil.copyfile(os.path.join(frozen, entry), os.path.join(objdir, entry))
                rt_objects.append(os.path.join(objdir, entry))
    else:
        for source in rt_sources:
            target = os.path.join(objdir, 'rt_' + os.path.basename(source)[:-4] + '.o')
            rt_objects.append(target)
            extra = ['-D%s=%s_rt' % (name, name) for name in WRAPPED] if os.path.basename(source) == 'runtime.cpp' else []
            jobs.append((source, target, None, extra))

    def build_one(job):
        source, target, key, extra = job
        cached = os.path.join(cache, key + '.o') if key else None
        if cached and os.path.exists(cached):
            shutil.copyfile(cached, target)
            return source, 0, '', True
        if key and plain:       # the same key formula as build_net.py: its objects serve
            other = os.path.join(OUT, 'net', 'objcache', key + '.o')
            if os.path.exists(other):
                shutil.copyfile(other, target)
                return source, 0, '', True
        # the runtime and the shim always see the runtime's own recomp.h
        inc = includes if key or source.startswith(HERE) else ['-I', RT, '-I', gen]
        result = subprocess.run(['nice', '-n', '10', 'clang++'] + CODEGEN + inc + extra + ['-c', source, '-o', target],
                                capture_output=True, text=True)
        if result.returncode == 0 and cached:
            shutil.copyfile(target, cached + '.tmp')
            os.replace(cached + '.tmp', cached)
        return source, result.returncode, result.stderr, False

    start = time.time()
    failed = hits = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for source, code, err, hit in pool.map(build_one, jobs):
            hits += hit
            if code != 0:
                failed += 1
                print('FAILED %s\n%s' % (source, err[:3000]))
    print('compiled %d files, %d from the cache, in %.1f s (%d failed)' % (len(jobs) - hits, hits, time.time() - start, failed))
    if failed:
        return 1
    if args.rt == 'live' and not os.path.exists(os.path.join(frozen, 'note.txt')):
        os.makedirs(frozen, exist_ok=True)
        for target in rt_objects:
            shutil.copyfile(target, os.path.join(frozen, os.path.basename(target)))
        with open(os.path.join(frozen, 'note.txt'), 'w') as sink:
            sink.write(rt_note + '\n')

    # 3. link (rt_finish and rt_fields are weak in the shim for runtimes that lack them)
    objects = [job[1] for job in jobs] + [o for o in rt_objects if o not in [job[1] for job in jobs]]
    link = subprocess.run(['clang++', '-o', program] + objects + ['-Wl,-U,__Z9rt_finishi', '-Wl,-U,__Z9rt_fieldsv', '-lpthread'],
                          capture_output=True, text=True)
    if link.returncode != 0:
        print('LINK FAILED\n' + link.stderr[:4000])
        return 1
    with open(os.path.join(gen, 'build-info.txt'), 'w') as sink:
        sink.write('%s\nexecutable sha1 %s\ninstrument %s\nsections %d: %s\nflags %s\nnetshim.cpp sha1 %s\nsoakhooks.cpp sha1 %s\n' % (
            rt_note, sha1_file(os.path.join(ROOT, 'SLUS_209.73')), args.instrument, len(sections), '; '.join(sections),
            ' '.join(CODEGEN), sha1_file(os.path.join(NET, 'netshim.cpp')), sha1_file(os.path.join(HERE, 'soakhooks.cpp'))))
    print(rt_note)
    print('linked %s (%d bytes), %d sections, instrument %s' % (program, os.path.getsize(program), len(sections), args.instrument))
    return 0


if __name__ == '__main__':
    sys.exit(main())
