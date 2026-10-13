#!/usr/bin/env python3
"""speedbench.py - builds and runs decode_bench (tools/recomp/web/decode_bench.cpp: the
renderer's processor side alone on a recorded stream) in the variants the speed work
compares (docs/issues/native-render-speed.md).

  speedbench.py build NAME [--vu fast|old|none] [--prof] [--flag F ...] [--wasm] [--simd none]
  speedbench.py run NAME STREAM [bench arguments ...]
  speedbench.py count NAME STREAM [--loops A,B] [bench arguments ...]
                                                    # instructions and cycles per picture of the whole process,
                                                    # from the difference of two runs of A and B passes (start-up,
                                                    # the first pass and - for node - compiling cancel); macOS
  speedbench.py translate STREAM [STREAM ...]       # vu1_translate.py into local/recomp-out/gen-vu/vu1_fast.cpp

  --vu fast    the ahead-of-time translation local/recomp-out/gen-vu/vu1_fast.cpp (default when it exists)
  --vu old     only the older translation of the main program, gen-vu/vu1_translated.cpp
  --vu none    neither: everything interpreted
  --prof       with the instruction counters of render/prof.h
  --wasm       with em++ for node (the Emscripten on the machine; nothing is downloaded)

Objects and programs go to local/recomp-out/speed/NAME/ (derived from the game).  Compiles
at nice 10, one file at a time unless --jobs says otherwise.
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'local', 'recomp-out')
CORE = ['vu1.cpp', 'vif1.cpp', 'gs.cpp', 'renderer.cpp']


def build(args):
    out = os.path.join(OUT, 'speed', args.name)
    os.makedirs(out, exist_ok=True)
    fast = os.path.join(OUT, 'gen-vu', 'vu1_fast.cpp')
    old = os.path.join(OUT, 'gen-vu', 'vu1_translated.cpp')
    vu = args.vu or ('fast' if os.path.exists(fast) else 'old' if os.path.exists(old) else 'none')
    sources = [os.path.join(HERE, n) for n in CORE] + [os.path.join(os.path.dirname(HERE), 'web', 'decode_bench.cpp')]
    sources.append(fast if vu == 'fast' else os.path.join(HERE, 'vu1_fast_none.cpp'))
    sources.append(old if vu in ('fast', 'old') and os.path.exists(old) and not args.no_old else os.path.join(HERE, 'vu1_none.cpp'))
    flags = ['-std=c++17', args.opt, '-fno-strict-aliasing', '-ffp-contract=off', '-I', HERE, '-I', os.path.join(os.path.dirname(HERE), 'web')]
    if args.prof:
        flags.append('-DRTA_PROF')
    if args.simd == 'none':
        flags.append('-DVU1_SIMD_NONE')
    flags += args.flag
    if args.wasm:
        compiler, program = 'em++', os.path.join(out, 'decode_bench.js')
        link = ['-sNODERAWFS=1', '-sINITIAL_MEMORY=1024MB', '-sSTACK_SIZE=8MB'] + args.link_flag
    else:
        compiler, program = 'clang++', os.path.join(out, 'decode_bench')
        flags.append('-frounding-math')
        link = []
    stamp_text = ' '.join([compiler] + flags)
    objects, todo = [], []
    for source in sources:
        target = os.path.join(out, os.path.basename(source)[:-4] + '.o')
        objects.append(target)
        stamp = target + '.flags'
        newest = max([os.path.getmtime(source)] + [os.path.getmtime(os.path.join(d, n)) for d in (HERE, os.path.join(os.path.dirname(HERE), 'web'))
                                                    for n in os.listdir(d) if n.endswith('.h')])
        if not os.path.exists(target) or os.path.getmtime(target) < newest or not os.path.exists(stamp) or open(stamp).read() != stamp_text:
            todo.append((source, target, stamp))

    def compile_one(job):
        source, target, stamp = job
        result = subprocess.run(['nice', '-n', '10', compiler] + flags + ['-c', source, '-o', target], capture_output=True, text=True)
        if result.returncode == 0:
            open(stamp, 'w').write(stamp_text)
        return source, result.returncode, result.stderr

    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for source, code, err in pool.map(compile_one, todo):
            if code != 0:
                failed = True
                print('FAILED %s\n%s' % (source, err[:8000]))
            elif err.strip():
                print(err[:3000])
    if failed:
        return 1
    result = subprocess.run(['nice', '-n', '10', compiler, args.opt] + (['-msimd128'] if '-msimd128' in args.flag else []) + objects + link + ['-o', program],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print('LINK FAILED\n' + result.stderr[:6000])
        return 1
    print('compiled %d of %d files (VU1: %s); linked %s' % (len(todo), len(sources), vu, program))
    return 0


def run(args, rest):
    out = os.path.join(OUT, 'speed', args.name)
    if os.path.exists(os.path.join(out, 'decode_bench')):
        command = [os.path.join(out, 'decode_bench')]
    else:
        command = ['node', '--stack-size=3000', os.path.join(out, 'decode_bench.js')]
    return subprocess.run(['nice', '-n', '10'] + command + [args.stream] + rest).returncode


class RusageInfo(__import__('ctypes').Structure):      # rusage_info_v4 of <sys/resource.h>
    _fields_ = [('uuid', __import__('ctypes').c_uint8 * 16)] + [(n, __import__('ctypes').c_uint64) for n in (
        'user_time', 'system_time', 'pkg_idle_wkups', 'interrupt_wkups', 'pageins', 'wired_size', 'resident_size', 'phys_footprint',
        'proc_start_abstime', 'proc_exit_abstime', 'child_user_time', 'child_system_time', 'child_pkg_idle_wkups', 'child_interrupt_wkups',
        'child_pageins', 'child_elapsed_abstime', 'diskio_bytesread', 'diskio_byteswritten', 'cpu_time_qos_default', 'cpu_time_qos_maintenance',
        'cpu_time_qos_background', 'cpu_time_qos_utility', 'cpu_time_qos_legacy', 'cpu_time_qos_user_initiated', 'cpu_time_qos_user_interactive',
        'billed_system_time', 'serviced_system_time', 'logical_writes', 'lifetime_max_phys_footprint', 'instructions', 'cycles', 'billed_energy',
        'serviced_energy', 'interval_max_phys_footprint', 'runnable_time')]


def counted(command):
    """Runs a command; (instructions, cycles) of its process when it has ended, and its output."""
    import ctypes
    libproc = ctypes.CDLL('/usr/lib/libproc.dylib')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout.read().decode('utf-8', 'replace')
    # wait until it has ended without reaping it: its figures are still there then
    # (waitid(P_PID, pid, &info, WEXITED | WNOWAIT) of macOS's C library; Python's os has none there)
    libc = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    siginfo = ctypes.create_string_buffer(256)
    libc.waitid(1, process.pid, siginfo, 0x4 | 0x20)
    info = RusageInfo()
    ok = libproc.proc_pid_rusage(process.pid, 4, ctypes.byref(info)) == 0
    process.wait()
    return (info.instructions, info.cycles) if ok else (0, 0), output


def count(args, rest):
    import re
    out = os.path.join(OUT, 'speed', args.name)
    if os.path.exists(os.path.join(out, 'decode_bench')):
        command = [os.path.join(out, 'decode_bench')]
    else:
        command = ['node', '--stack-size=3000', os.path.join(out, 'decode_bench.js')]
    a, b = (int(x) for x in args.loops.split(','))
    figures = []
    for loops in (a, b):
        (instructions, cycles), output = counted(['nice', '-n', '10'] + command + [args.stream, '--loops', str(loops)] + rest)
        blanks = re.search(r'first pass: (\d+) blanks', output)
        if not blanks or not instructions:
            print(output[-2000:])
            return 1
        figures.append((instructions, cycles, int(blanks.group(1)) * loops, output))
    pictures = figures[1][2] - figures[0][2]
    sums = re.search(r'list checksum (\w+)', figures[1][3]).group(1)
    commands = re.search(r'draw commands of the first pass: checksum (\w+)', figures[1][3])
    print('%s %s%s: %.2f million instructions, %.2f million cycles per picture (runs of %d and %d passes); lists %s%s; load average %.0f' % (
        args.name, os.path.basename(args.stream), ' ' + ' '.join(rest) if rest else '', (figures[1][0] - figures[0][0]) / pictures / 1e6,
        (figures[1][1] - figures[0][1]) / pictures / 1e6, a, b, sums, ' commands ' + commands.group(1) if commands else '', os.getloadavg()[0]))
    return 0


def translate(args):
    command = [sys.executable, os.path.join(HERE, 'vu1_translate.py'), '--out', os.path.join(OUT, 'gen-vu', 'vu1_fast.cpp'), '--report']
    for stream in args.streams:
        command += ['--stream', stream]
    return subprocess.run(command).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='what', required=True)
    b = sub.add_parser('build')
    b.add_argument('name')
    b.add_argument('--vu', choices=['fast', 'old', 'none'])
    b.add_argument('--no-old', action='store_true', help='with --vu fast: do not link the older translation behind it')
    b.add_argument('--prof', action='store_true')
    b.add_argument('--wasm', action='store_true')
    b.add_argument('--simd', choices=['none'])
    b.add_argument('--opt', default='-O2')
    b.add_argument('--flag', action='append', default=[])
    b.add_argument('--link-flag', action='append', default=[])
    b.add_argument('--jobs', type=int, default=4)
    r = sub.add_parser('run')
    r.add_argument('name')
    r.add_argument('stream')
    c = sub.add_parser('count')
    c.add_argument('name')
    c.add_argument('stream')
    c.add_argument('--loops', default='3,9')
    t = sub.add_parser('translate')
    t.add_argument('streams', nargs='+')
    args, rest = parser.parse_known_args()
    if args.what == 'build':
        return build(args)
    if args.what == 'run':
        return run(args, rest)
    if args.what == 'count':
        return count(args, rest)
    return translate(args)


if __name__ == '__main__':
    sys.exit(main())
