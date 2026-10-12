#!/usr/bin/env python3
"""build.py - compile the generated C++ and link it with one of the programs in rt/.

  python3 tools/recomp/build.py test      # differential-test driver  (-DRECOMP_TEST -DFPU_PS2)
  python3 tools/recomp/build.py run       # headless runtime          (host FPU model)
  options: --opt -O1|-O2|...   --jobs N   --gen DIR   --define NAME (repeatable)
           --name NAME          object directory obj-NAME and program bin/NAME
           --sound FILE.cpp     link this file in place of rt/sound_null.cpp (run only)
           --main FILE.cpp      link this file in place of rt/main_headless.cpp (run only):
                                an application with a window, its own rta::Hooks
           --extra FILE.cpp     one more source file (repeatable), --lib NAME (repeatable)

Objects go to local/recomp-out/obj-<config>/, the program to local/recomp-out/bin/.
Only the compiler already on the machine is used (clang++); nothing is downloaded.
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'local', 'recomp-out')

CONFIGS = {
    'test': {'defines': ['RECOMP_TEST', 'FPU_PS2'], 'opt': '-O1', 'sources': ['test_driver.cpp'],
             'program': 'recomp_test'},
    'run': {'defines': [], 'opt': '-O2', 'program': 'rta_native',
            'sources': ['runtime.cpp', 'iop.cpp', 'script.cpp', 'host_posix.cpp', 'sound_null.cpp', 'main_headless.cpp']},
}


def newer(source, target, extra=()):
    if not os.path.exists(target):
        return True
    stamp = os.path.getmtime(target)
    return any(os.path.getmtime(path) > stamp for path in (source,) + tuple(extra))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', choices=sorted(CONFIGS))
    parser.add_argument('--opt')
    parser.add_argument('--jobs', type=int, default=max(2, (os.cpu_count() or 4) - 4))
    parser.add_argument('--gen', default=os.path.join(OUT, 'gen'))
    parser.add_argument('--define', action='append', default=[])
    parser.add_argument('--name', help='name of the object directory and program (default: the config)')
    parser.add_argument('--sound', help='a source file to link in place of rt/sound_null.cpp')
    parser.add_argument('--main', help='a source file to link in place of rt/main_headless.cpp')
    parser.add_argument('--extra', action='append', default=[], help='one more source file; repeatable')
    parser.add_argument('--lib', action='append', default=[], help='one more library to link; repeatable')
    args = parser.parse_args()
    config = CONFIGS[args.config]
    name = args.name or args.config
    objdir = os.path.join(OUT, 'obj-' + name)
    bindir = os.path.join(OUT, 'bin')
    os.makedirs(objdir, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    rt = os.path.join(HERE, 'rt')
    headers = tuple(os.path.join(rt, n) for n in os.listdir(rt) if n.endswith('.h'))
    # generated code is written against these only; the other headers are the runtime's own
    gen_headers = tuple(os.path.join(rt, n) for n in ('recomp.h', 'fpu.h', 'mmi.h'))
    flags = ['-std=c++17', args.opt or config['opt'], '-fno-strict-aliasing', '-fwrapv', '-w',
             '-ffp-contract=off', '-frounding-math', '-I', rt, '-I', args.gen]
    flags += ['-D' + d for d in config['defines'] + args.define]
    jobs = []
    for entry in sorted(os.listdir(args.gen)):
        if entry.endswith('.cpp'):
            jobs.append((os.path.join(args.gen, entry), os.path.join(objdir, entry[:-4] + '.o'),
                         gen_headers + (os.path.join(args.gen, 'funcs.h'),)))
    sources = [os.path.join(rt, entry) for entry in config['sources']]
    for replaced, by in (('sound_null.cpp', args.sound), ('main_headless.cpp', args.main)):
        if by:
            sources = [os.path.abspath(by) if os.path.basename(s) == replaced else s for s in sources]
    sources += [os.path.abspath(path) for path in args.extra]
    for source in sources:
        jobs.append((source, os.path.join(objdir, 'rt_' + os.path.basename(source)[:-4] + '.o'), headers))
    # objects built with other flags are stale
    stamp = os.path.join(objdir, 'flags.txt')
    previous = open(stamp).read() if os.path.exists(stamp) else None
    if previous != ' '.join(flags):
        for job in jobs:
            if os.path.exists(job[1]):
                os.remove(job[1])
        with open(stamp, 'w') as sink:
            sink.write(' '.join(flags))
    todo = [job for job in jobs if newer(job[0], job[1], job[2])]
    start = time.time()

    def compile_one(job):
        source, target, _ = job
        result = subprocess.run(['nice', '-n', '10', 'clang++'] + flags + ['-c', source, '-o', target],
                                capture_output=True, text=True)
        return source, result.returncode, result.stderr

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for source, code, err in pool.map(compile_one, todo):
            if code != 0:
                failed += 1
                print('FAILED %s\n%s' % (source, err[:3000]))
    print('compiled %d of %d files in %.1f s (%d failed)' % (len(todo), len(jobs), time.time() - start, failed))
    if failed:
        return 1
    program = os.path.join(bindir, config['program'] if name == args.config else name)
    link = subprocess.run(['clang++', '-o', program] + [job[1] for job in jobs] + ['-lpthread'] + ['-l' + lib for lib in args.lib],
                          capture_output=True, text=True)
    if link.returncode != 0:
        print('LINK FAILED\n' + link.stderr[:4000])
        return 1
    print('linked %s (%d bytes)' % (program, os.path.getsize(program)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
