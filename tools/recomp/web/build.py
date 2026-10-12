#!/usr/bin/env python3
"""build.py - the native build (tools/recomp) compiled to WebAssembly with Emscripten.

  python3 tools/recomp/web/build.py node     # translated game + runtime, headless, for node
  python3 tools/recomp/web/build.py page     # + renderer on WebGL 2, sound, the page: a site to serve
  python3 tools/recomp/web/build.py mac      # the headless program with the Mac's own compiler: the
                                             # reference a node run is compared with tick for tick

  --src DIR      the tree with rt/, render/, sound/, app/ (default: tools/recomp; it needs
                 shared-sources.patch applied, see docs/issues/native-web.md)
  --gen DIR      the translated game (default: local/recomp-web/gen; made by
                 recomp.py --out local/recomp-web/gen)
  --out DIR      objects, programs, the site (default: local/recomp-web/build)
  --name NAME    the result goes to <out>/NAME/ (default: the target and the arithmetic)
  --arith nearest|zero
                 nearest: single-precision results are rounded as WebAssembly rounds them,
                 to nearest - what the emulator's page computes ("browser arithmetic");
                 zero: toward zero, as the console and the Mac builds do, in software
                 (-DRTA_SOFT_RZ, soft_rz.h).  For `mac`: nearest is the plain build (the
                 processor's own rounding: toward zero, or to nearest with `--opt
                 arith=nearest` when it is run), zero the software one, to check soft_rz.h.
  --opt=-O2      optimisation of the translated code and everything else
  --link-opt=-O2 what em++ is given when it links (-O2 and up run Binaryen's optimiser; =-O1 links in a third of the time)
  --jobs N       compilers at once (each at nice 10)
  --define NAME  (repeatable)
  --flag=FLAG    one more compiler flag for everything but the translated game (repeatable),
                 e.g. --flag=-msimd128
  --vu FILE      page: the VU1 main program translated to C++ (rta_replay --translate-vu
                 writes it); without it VU1 is interpreted
  --vu-arith nearest|zero
                 page: the arithmetic of the vertex programs (VU1), which is the picture's and
                 has nothing to do with the game's.  The unit rounds toward zero.  nearest
                 (default): WebAssembly's own rounding - the vertices come out within a fifth
                 of a pixel of the Mac application's; zero: toward zero in software
                 (-DRTA_SOFT_RZ_VU1), the same vertices bit for bit, at 40 % more decoder time
  --no-sound     page: rt/sound_null.cpp instead of the sound library
  --profiling    keep function names in the WebAssembly (for profiles)

The translated game's objects are shared by `node` and `page` (<out>/obj-gen-<host>-<arith>).
Nothing is downloaded: the Emscripten on the machine is used (em++).  Everything that comes
out is derived from the game and stays under local/.
"""
import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

RT = ['runtime.cpp', 'iop.cpp', 'script.cpp']
RENDER = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']
SOUND = ['sound_rta.cpp']       # it includes the rest of the sound library (spu2, drivers, audio_out)
PAGE_FILES = ['index.html', 'rta-native.js', 'rta-sound-worklet.js']
EXPORTS = ['_main', '_malloc', '_free', '_rta_web_shared', '_rta_web_info', '_rta_web_peek', '_rta_web_sound_ring']
RUNTIME_METHODS = ['FS', 'IDBFS', 'HEAPU8', 'HEAP32', 'HEAPU32', 'wasmMemory', 'UTF8ToString', 'callMain']


def newer(source, target, extra=()):
    if not os.path.exists(target):
        return True
    stamp = os.path.getmtime(target)
    return any(os.path.getmtime(path) > stamp for path in (source,) + tuple(extra) if os.path.exists(path))


def headers_of(*dirs):
    found = []
    for d in dirs:
        if os.path.isdir(d):
            found += [os.path.join(d, n) for n in os.listdir(d) if n.endswith('.h')]
    return tuple(found)


def stale_by_flags(objdir, flags, jobs):
    """objects built with other flags are stale"""
    os.makedirs(objdir, exist_ok=True)
    stamp = os.path.join(objdir, 'flags.txt')
    previous = open(stamp).read() if os.path.exists(stamp) else None
    if previous != ' '.join(flags):
        for job in jobs:
            if os.path.exists(job[1]):
                os.remove(job[1])
        with open(stamp, 'w') as sink:
            sink.write(' '.join(flags))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('target', choices=['node', 'page', 'mac'])
    parser.add_argument('--src', default=os.path.join(ROOT, 'tools', 'recomp'))
    parser.add_argument('--gen', default=os.path.join(ROOT, 'local', 'recomp-web', 'gen'))
    parser.add_argument('--out', default=os.path.join(ROOT, 'local', 'recomp-web', 'build'))
    parser.add_argument('--name')
    parser.add_argument('--arith', choices=['nearest', 'zero'], default='nearest')
    parser.add_argument('--opt', default='-O2')
    parser.add_argument('--link-opt', default='-O2')
    parser.add_argument('--jobs', type=int, default=max(2, (os.cpu_count() or 4) - 6))
    parser.add_argument('--define', action='append', default=[])
    parser.add_argument('--flag', action='append', default=[], help='one more compiler flag for everything but the translated game, as --flag=-msimd128; repeatable')
    parser.add_argument('--vu')
    parser.add_argument('--vu-arith', choices=['nearest', 'zero'], default='nearest')
    parser.add_argument('--no-sound', action='store_true')
    parser.add_argument('--profiling', action='store_true')
    args = parser.parse_args()

    src = os.path.abspath(args.src)
    rt, render, sound, app = (os.path.join(src, d) for d in ('rt', 'render', 'sound', 'app'))
    mac = args.target == 'mac'
    name = args.name or '%s-%s' % (args.target, args.arith)
    outdir = os.path.join(args.out, name)
    os.makedirs(outdir, exist_ok=True)
    compiler = 'clang++' if mac else 'em++'

    base = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-fwrapv', '-w', '-ffp-contract=off']
    base += ['-frounding-math'] if mac else ['-pthread', '-fwasm-exceptions']
    base += ['-I', rt, '-I', args.gen, '-I', HERE]
    base += ['-D' + d for d in args.define + (['RTA_SOFT_RZ'] if args.arith == 'zero' else [])]

    # the translated game
    gen_dir = os.path.join(args.out, 'obj-gen-%s-%s' % ('mac' if mac else 'wasm', args.arith))
    gen_headers = tuple(os.path.join(rt, n) for n in ('recomp.h', 'fpu.h', 'mmi.h')) + (os.path.join(args.gen, 'funcs.h'), os.path.join(HERE, 'soft_rz.h'))
    gen_jobs = [(os.path.join(args.gen, entry), os.path.join(gen_dir, entry[:-4] + '.o'), gen_headers, base)
                for entry in sorted(os.listdir(args.gen)) if entry.endswith('.cpp')]
    stale_by_flags(gen_dir, base, gen_jobs)

    # the runtime and whatever the target adds
    own_dir = os.path.join(args.out, 'obj-' + name)
    flags = list(base) + args.flag
    sources = [os.path.join(rt, n) for n in RT] + [os.path.join(rt, 'host_posix.cpp') if mac else os.path.join(HERE, 'host_web.cpp')]
    headers = headers_of(rt, HERE)
    if args.target == 'page':
        flags += ['-DRTA_WEB_PAGE', '-I', render, '-I', sound, '-I', app]
        if args.vu_arith == 'zero':
            flags.append('-DRTA_SOFT_RZ_VU1')
        headers += headers_of(render, sound, app)
        sources += [os.path.join(render, n) for n in RENDER]
        sources.append(os.path.abspath(args.vu) if args.vu else os.path.join(render, 'vu1_none.cpp'))
        sources += [os.path.join(app, 'app_rt.cpp'), os.path.join(HERE, 'backend_webgl.cpp'), os.path.join(HERE, 'web_main.cpp')]
        if args.no_sound:
            sources += [os.path.join(rt, 'sound_null.cpp'), os.path.join(HERE, 'sound_none_web.cpp')]
        else:
            sources += [os.path.join(sound, n) for n in SOUND]
    else:
        sources += [os.path.join(rt, 'sound_null.cpp'), os.path.join(rt, 'main_headless.cpp')]
    own_jobs = [(source, os.path.join(own_dir, 'rt_' + os.path.basename(source)[:-4] + '.o'), headers, flags) for source in sources]
    stale_by_flags(own_dir, flags, own_jobs)

    jobs = gen_jobs + own_jobs
    todo = [job for job in jobs if newer(job[0], job[1], job[2])]
    start = time.time()

    def compile_one(job):
        source, target, _, job_flags = job
        began = time.time()
        result = subprocess.run(['nice', '-n', '10', compiler] + job_flags + ['-c', source, '-o', target], capture_output=True, text=True)
        return source, result.returncode, result.stderr, time.time() - began

    failed, summed = 0, 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for source, code, err, took in pool.map(compile_one, todo):
            summed += took
            if code != 0:
                failed += 1
                print('FAILED %s\n%s' % (source, err[:3000]))
    print('compiled %d of %d files in %.1f s of wall time, %.0f s summed over the compilers (%d failed)'
          % (len(todo), len(jobs), time.time() - start, summed, failed))
    if failed:
        return 1
    objects = [job[1] for job in jobs]
    print('objects: %.1f MB' % (sum(os.path.getsize(o) for o in objects) / 1e6))

    if mac:
        program = os.path.join(outdir, 'rta_native')
        done = subprocess.run(['clang++', '-o', program] + objects + ['-lpthread'], capture_output=True, text=True)
        if done.returncode != 0:
            print('LINK FAILED\n' + done.stderr[:2500])
            return 1
        print('linked %s (%.2f MB)' % (os.path.relpath(program, ROOT), os.path.getsize(program) / 1e6))
        return 0

    link = ['nice', '-n', '10', 'em++', args.link_opt, '-pthread', '-fwasm-exceptions',
            '-sINITIAL_MEMORY=%d' % (512 << 20), '-sSTACK_SIZE=%d' % (4 << 20), '-sDEFAULT_PTHREAD_STACK_SIZE=%d' % (2 << 20),
            '-sPROXY_TO_PTHREAD=1', '-sEXIT_RUNTIME=1']
    if args.profiling:
        link.append('--profiling-funcs')
    if args.target == 'node':
        program = os.path.join(outdir, 'rta_native.js')
        link += ['-sENVIRONMENT=node,worker', '-sNODERAWFS=1', '-sPTHREAD_POOL_SIZE=12']
    else:
        program = os.path.join(outdir, 'rta.js')
        link += ['-sENVIRONMENT=web,worker', '-sPTHREAD_POOL_SIZE=14', '-sMODULARIZE=1', '-sEXPORT_NAME=RtaNative',
                 '-sMIN_WEBGL_VERSION=2', '-sMAX_WEBGL_VERSION=2', '-sOFFSCREENCANVAS_SUPPORT=1',
                 '-sOFFSCREENCANVASES_TO_PTHREAD=#canvas', '-lidbfs.js', '-sFORCE_FILESYSTEM=1', '-sINVOKE_RUN=0',
                 '-sEXPORTED_RUNTIME_METHODS=' + ','.join(RUNTIME_METHODS), '-sEXPORTED_FUNCTIONS=' + ','.join(EXPORTS)]
    link += ['-o', program] + objects
    start = time.time()
    done = subprocess.run(link, capture_output=True, text=True)
    if done.returncode != 0:
        print('LINK FAILED\n' + done.stderr[:2500])
        return 1
    wasm = program[:-3] + '.wasm'
    print('linked %s in %.1f s: %.2f MB of WebAssembly, %.0f KB of JavaScript'
          % (os.path.relpath(program, ROOT), time.time() - start, os.path.getsize(wasm) / 1e6, os.path.getsize(program) / 1e3))
    if args.target == 'page':
        for entry in PAGE_FILES:
            shutil.copy(os.path.join(HERE, entry), os.path.join(outdir, entry))
        print('site: %s (python3 tools/recomp/web/serve.py --site %s)' % (os.path.relpath(outdir, ROOT), os.path.relpath(outdir, ROOT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
