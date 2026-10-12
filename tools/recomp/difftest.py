#!/usr/bin/env python3
"""difftest.py - is the translated code the same program as the original?

Runs functions of the executable twice on identical inputs - in tools/ee_emu.py (the
project's instruction interpreter) and in the compiled translation (local/recomp-out/bin/
recomp_test, built by `build.py test`) - and compares everything observable: all general
registers (128 bits each), HI/LO and the second pair, the shift-amount register, the FPU
registers, accumulator and compare bit, every call made (site, target, eight integer and
eight float argument registers) and every byte of memory that changed, stack included.

  python3 tools/recomp/difftest.py sweep  [--mode stub|follow] [--only HEX,...] [--limit N]
                                          [--jobs N] [--steps N] [--report FILE]
  python3 tools/recomp/difftest.py replay <tools/difftest_*.py> [script args]

sweep   drives every function of the function table automatically, on six kinds of input
        (see RECIPES).  --mode stub (default) replaces every call the function makes by
        "return 0", as the interpreter's stub-all mode does, so one function's own
        translation is what is compared, including the calls it makes and their arguments;
        --mode follow lets callees run, so whole call trees are compared.
replay  runs one of the project's reference-model tests and, for every call it makes into
        the game's code through the interpreter, replays the same register and memory
        state through the translation: the functions and inputs the reference models are
        checked on.

A case is *comparable* when the interpreter runs it to the function's return without
touching memory outside the 32 MB of main memory.  A function PASSES when it has at least
one comparable case and every comparable case is identical; it FAILS when any comparable
case differs.  Cases the interpreter stops on (step limit, trap, an instruction it does
not implement, a wild pointer) are counted but prove nothing about the function.
"""
import argparse
import os
import random
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError, M64            # noqa: E402

ELF = os.path.join(ROOT, 'SLUS_209.73')
OUT = os.path.join(ROOT, 'local', 'recomp-out')
DRIVER = os.path.join(OUT, 'bin', 'recomp_test')
RAM = 0x02000000
RETURN_ADDR = EE.RETURN_ADDR
ARENA = 0x01000000
ARENA_SIZE = 0x4000
SP = EE.STACK_HI - 0x100
ZERO_PAGE = bytes(4096)

RECIPES = ('zero', 'ints', 'pointers', 'floats', 'mixed', 'random')
NATIVE_STATUS = ('return', 'fault', 'budget', 'trap', 'signal', 'badcall')


class Case:
    """Everything that defines one run: function, registers, memory patches, stubs."""
    __slots__ = ('func', 'stub_all', 'budget', 'r', 'rh', 'hi', 'lo', 'hi1', 'lo1', 'sa', 'fcr31',
                 'f', 'acc', 'cop0', 'stubs', 'patches', 'tag')

    def __init__(self, func):
        self.func = func
        self.stub_all = False
        self.budget = 100000
        self.r = [0] * 32
        self.rh = [0] * 32
        self.hi = self.lo = self.hi1 = self.lo1 = 0
        self.sa = 0
        self.fcr31 = 0x01000001
        self.f = [0] * 32
        self.acc = 0
        self.cop0 = [0] * 32
        self.stubs = []         # (address, value or None)
        self.patches = []       # (address, bytes)
        self.tag = ''

    def pack(self):
        out = [struct.pack('<IIq', self.func, 1 if self.stub_all else 0, self.budget),
               struct.pack('<32Q', *self.r), struct.pack('<32Q', *self.rh),
               struct.pack('<4Q', self.hi, self.lo, self.hi1, self.lo1),
               struct.pack('<II', self.sa, self.fcr31), struct.pack('<32I', *self.f),
               struct.pack('<I', self.acc), struct.pack('<32I', *self.cop0),
               struct.pack('<I', len(self.stubs))]
        for addr, value in self.stubs:
            out.append(struct.pack('<IIQ', addr, 0 if value is None else 1, (value or 0) & M64))
        out.append(struct.pack('<I', len(self.patches)))
        for addr, blob in self.patches:
            out.append(struct.pack('<II', addr, len(blob)))
            out.append(blob)
            out.append(b'\0' * (-len(blob) & 3))
        return b''.join(out)


class Outcome:
    __slots__ = ('status', 'info', 'r', 'rh', 'hi', 'lo', 'hi1', 'lo1', 'sa', 'fcr31', 'f', 'acc',
                 'call_total', 'calls', 'pages')


def write_cases(path, cases):
    with open(path, 'wb') as sink:
        sink.write(struct.pack('<II', 0x31544352, len(cases)))
        for case in cases:
            sink.write(case.pack())


def pre_pages(case, pristine):
    """Memory pages a case's patches touch, as they are when the run starts."""
    pages = {}
    for addr, blob in case.patches:
        pos = 0
        while pos < len(blob):
            index, off = (addr + pos) >> 12, (addr + pos) & 0xFFF
            take = min(len(blob) - pos, 4096 - off)
            page = pages.get(index)
            if page is None:
                page = pages[index] = bytearray(pristine.get(index, ZERO_PAGE))
            page[off:off + take] = blob[pos:pos + take]
            pos += take
    return pages


def read_results(path, cases, pristine):
    with open(path, 'rb') as source:
        data = source.read()
    magic, count = struct.unpack_from('<II', data, 0)
    if magic != 0x31525352:
        raise ValueError('bad result file')
    pos = 8
    outcomes = []
    for index in range(count):
        o = Outcome()
        o.status, o.info = struct.unpack_from('<II', data, pos)
        pos += 8
        o.r = list(struct.unpack_from('<32Q', data, pos)); pos += 256
        o.rh = list(struct.unpack_from('<32Q', data, pos)); pos += 256
        o.hi, o.lo, o.hi1, o.lo1 = struct.unpack_from('<4Q', data, pos); pos += 32
        o.sa, o.fcr31 = struct.unpack_from('<II', data, pos); pos += 8
        o.f = list(struct.unpack_from('<32I', data, pos)); pos += 128
        o.acc, o.call_total, ncalls = struct.unpack_from('<III', data, pos); pos += 12
        o.calls = []
        for _ in range(ncalls):
            site, target, stubbed, _pad = struct.unpack_from('<4I', data, pos)
            args = struct.unpack_from('<8Q', data, pos + 16)
            fargs = struct.unpack_from('<8I', data, pos + 80)
            o.calls.append((site, target, args, fargs))
            pos += 112
        runs, = struct.unpack_from('<I', data, pos); pos += 4
        pre = pre_pages(cases[index], pristine) if runs else {}
        pages = {}
        for _ in range(runs):
            addr, length = struct.unpack_from('<II', data, pos); pos += 8
            page = pages.get(addr >> 12)
            if page is None:
                base = pre.get(addr >> 12)
                if base is None:
                    base = pristine.get(addr >> 12, ZERO_PAGE)
                page = pages[addr >> 12] = bytearray(base)
            page[addr & 0xFFF:(addr & 0xFFF) + length] = data[pos:pos + length]
            pos += (length + 3) & ~3
        o.pages = {k: bytes(v) for k, v in pages.items()}
        outcomes.append(o)
    return outcomes


class Reference:
    """The interpreter, reset between cases."""

    def __init__(self, elf=ELF, fpu_model='ps2'):
        emu = self.emu = EE(elf, fpu_model=fpu_model)
        emu.mem.auto_map = True
        emu.div_zero = 'r5900'
        emu.stack_lo = emu.stack_hi = 0          # record stack writes too
        self.pristine = {index: bytes(page) for index, page in emu.mem.pages.items()}
        self.touched = set()

    def reset(self):
        emu = self.emu
        pages = emu.mem.pages
        for index in self.touched:
            base = self.pristine.get(index)
            if base is None:
                pages.pop(index, None)
            else:
                pages[index][:] = base
        for addr in emu.mem.auto_mapped:
            if (addr >> 12) not in self.pristine:
                pages.pop(addr >> 12, None)
        emu.mem.auto_mapped = []
        self.touched = set()
        emu.hooks.clear()
        emu.stub_names.clear()
        emu.breakpoints.clear()

    def run(self, case):
        """(status, Outcome).  status: return, fault, trap, unimpl, steps, error."""
        emu = self.emu
        self.reset()
        emu.r[:] = case.r
        emu.rh[:] = case.rh
        emu.hi, emu.lo, emu.hi1, emu.lo1 = case.hi, case.lo, case.hi1, case.lo1
        emu.sa, emu.fcr31, emu.acc = case.sa, case.fcr31, case.acc
        emu.f[:] = case.f
        emu.cop0[:] = case.cop0
        emu.calls, emu.writes, emu.notes, emu.steps = [], [], [], 0
        emu._pending_call = emu._fresh_call = None
        pre = pre_pages(case, self.pristine)
        for index, page in pre.items():
            emu.mem.pages[index] = bytearray(page)
            self.touched.add(index)
        emu.follow = set() if case.stub_all else None
        emu.default_ret = 0
        for addr, value in case.stubs:
            emu.stub(addr, ret=value)
        # a jump to address 0 would slide down a page of zeroes (no-ops) into the
        # interpreter's return address and look like a return
        for addr in range(0, RETURN_ADDR, 4):
            emu.hooks[addr] = _null_jump
        emu.r[31] = RETURN_ADDR
        emu.jump(case.func)
        emu.syscall_handler = _syscall_stub
        self.message = ''
        try:
            reason = emu.run(max_steps=case.budget)
            status = 'return' if reason == 'return' else 'error'
        except ee_emu.StepLimit:
            status = 'steps'
        except ee_emu.UnimplementedInstruction as exc:
            status, self.message = 'unimpl', str(exc)
        except ee_emu.CpuTrap as exc:
            status = 'unaligned' if str(exc).startswith('unaligned') else 'trap'
            self.message = str(exc)
        except ee_emu.MemoryFault as exc:
            status, self.message = 'fault', str(exc)
        except EmuError as exc:
            status, self.message = 'error', str(exc)
        written = set()
        for _pc, addr, size, _value in emu.writes:
            written.add(addr >> 12)
            written.add((addr + size - 1) >> 12)
        self.touched |= written
        if status == 'return' and any(addr >= RAM for addr in emu.mem.auto_mapped):
            status = 'fault'
        if status == 'return' and any(index >= (RAM >> 12) for index in written):
            status = 'fault'
        o = Outcome()
        o.status, o.info = status, (emu.cur if status in ('trap', 'unimpl') else emu.pc)
        o.r, o.rh = list(emu.r), list(emu.rh)
        o.hi, o.lo, o.hi1, o.lo1 = emu.hi, emu.lo, emu.hi1, emu.lo1
        o.sa, o.fcr31, o.f, o.acc = emu.sa, emu.fcr31, list(emu.f), emu.acc
        o.call_total = len(emu.calls)
        o.calls = [(rec.site, rec.target, tuple(a & M64 for a in rec.args), tuple(rec.fargs))
                   for rec in emu.calls[:512]]
        pages = {}
        wild = any(addr >= RAM for addr in emu.mem.auto_mapped) or any(index >= (RAM >> 12) for index in written)
        if status == 'return' or (status in ('trap', 'unimpl') and not wild):
            for index in written:
                final = bytes(emu.mem.pages[index])
                before = pre.get(index)
                if before is None:
                    before = self.pristine.get(index, ZERO_PAGE)
                if final != before:
                    pages[index] = final
        o.pages = pages
        return status, o


def _syscall_stub(emu):
    # no kernel on either side: a system call returns 0 (the test driver does the same)
    emu.r[2] = 0


def _null_jump(emu):
    rec = emu._fresh_call
    if rec is not None and emu.follow is not None:
        # a call through a null pointer with every call stubbed: stub it like the rest
        emu.r[2] = 0
        rec.stubbed, rec.ret = True, 0
        emu.jump(emu.r[31] & 0xFFFFFFFF)
        return
    raise EmuError('jump to address 0')


def compare(ref, nat, expect='return'):
    """List of differences between the interpreter's outcome and the translation's."""
    diffs = []
    if NATIVE_STATUS[nat.status] != expect:
        return ['translation stopped: %s (0x%x)' % (NATIVE_STATUS[nat.status], nat.info)]
    for n in range(1, 32):
        if ref.r[n] != nat.r[n]:
            diffs.append('%s = %016x, translation %016x' % (ee_emu.REG_NAMES[n], ref.r[n], nat.r[n]))
        if ref.rh[n] != nat.rh[n]:
            diffs.append('%s high half = %016x, translation %016x' % (ee_emu.REG_NAMES[n], ref.rh[n], nat.rh[n]))
    for name in ('hi', 'lo', 'hi1', 'lo1', 'sa', 'acc'):
        if getattr(ref, name) != getattr(nat, name):
            diffs.append('%s = %x, translation %x' % (name, getattr(ref, name), getattr(nat, name)))
    if (ref.fcr31 ^ nat.fcr31) & 0x00800000:
        diffs.append('FPU compare bit differs')
    for n in range(32):
        if ref.f[n] != nat.f[n]:
            diffs.append('f%d = %08x, translation %08x' % (n, ref.f[n], nat.f[n]))
    if ref.call_total != nat.call_total:
        diffs.append('%d calls, translation %d' % (ref.call_total, nat.call_total))
    for index, (a, b) in enumerate(zip(ref.calls, nat.calls)):
        if a != b:
            diffs.append('call %d: site %x target %x, translation site %x target %x%s' % (
                index, a[0], a[1], b[0], b[1], '' if a[:2] != b[:2] else ' (arguments differ)'))
            break
    if ref.pages != nat.pages:
        for index in sorted(set(ref.pages) | set(nat.pages)):
            a, b = ref.pages.get(index), nat.pages.get(index)
            if a == b:
                continue
            if a is None or b is None:
                diffs.append('page %05x000 changed only in the %s' % (index, 'translation' if a is None else 'interpreter'))
            else:
                off = next(i for i in range(4096) if a[i] != b[i])
                diffs.append('memory %08x = %02x, translation %02x' % ((index << 12) + off, a[off], b[off]))
            if len(diffs) > 8:
                break
    return diffs


def run_native(cases, pristine, workdir, tag):
    case_path = os.path.join(workdir, 'cases-%s.bin' % tag)
    result_path = os.path.join(workdir, 'results-%s.bin' % tag)
    write_cases(case_path, cases)
    done = subprocess.run(['nice', '-n', '19', DRIVER, ELF, case_path, result_path],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError('driver failed (%d): %s' % (done.returncode, done.stderr[:500]))
    outcomes = read_results(result_path, cases, pristine)
    os.remove(case_path)
    os.remove(result_path)
    return outcomes


# ---------------------------------------------------------------------------------------
# Automatic inputs
# ---------------------------------------------------------------------------------------

def game_float(rng):
    kind = rng.random()
    if kind < 0.1:
        return 0.0
    if kind < 0.5:
        return rng.uniform(-1.0, 1.0)
    if kind < 0.9:
        return rng.uniform(-4096.0, 4096.0)
    return rng.uniform(-1e6, 1e6)


def raw(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def sx(value):
    value &= 0xFFFFFFFF
    return value | 0xFFFFFFFF00000000 if value & 0x80000000 else value


def make_case(func, recipe, seed, budget, stub_all):
    rng = random.Random('%x/%s/%d' % (func, recipe, seed))
    case = Case(func)
    case.tag = recipe
    case.budget = budget
    case.stub_all = stub_all
    words = ARENA_SIZE // 4

    def pointer():
        return ARENA + (rng.randrange(words - 64) & ~3) * 4

    if recipe == 'zero':
        # arguments point at four separate areas of zeroes; nothing is patched
        for n in range(4):
            case.r[4 + n] = 0x01100000 + n * 0x10000
        for n in range(4):
            case.r[8 + n] = n
    elif recipe == 'ints':
        for n in range(8):
            case.r[4 + n] = sx(rng.choice((0, 1, 2, 3, 5, 7, 16, 100, 255, 1000, 65535, -1, -2, -100,
                                           rng.randrange(-70000, 70000))))
        for n in range(32):
            case.f[n] = raw(game_float(rng))
    else:
        if recipe == 'pointers':
            blob = struct.pack('<%dI' % words, *[pointer() for _ in range(words)])
        elif recipe == 'floats':
            blob = struct.pack('<%df' % words, *[game_float(rng) for _ in range(words)])
        elif recipe == 'mixed':
            values = []
            for _ in range(words):
                kind = rng.random()
                if kind < 0.4:
                    values.append(pointer())
                elif kind < 0.7:
                    values.append(rng.choice((0, 1, 2, 3, 4, 8, 10, 100, 0xFFFFFFFF, rng.randrange(1 << 16))))
                else:
                    values.append(raw(game_float(rng)))
            blob = struct.pack('<%dI' % words, *values)
        else:
            blob = rng.randbytes(ARENA_SIZE)
        case.patches.append((ARENA, blob))
        for n in range(4):
            case.r[4 + n] = pointer()
        for n in range(4):
            case.r[8 + n] = pointer() if rng.random() < 0.5 else sx(rng.randrange(-8, 64))
        for n in range(32):
            case.f[n] = raw(game_float(rng)) if recipe != 'random' else rng.getrandbits(32)
        if recipe == 'random':
            for n in (2, 3, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 30):
                case.r[n] = rng.getrandbits(64)
                case.rh[n] = rng.getrandbits(64)
            case.hi, case.lo = sx(rng.getrandbits(32)), sx(rng.getrandbits(32))
            case.hi1, case.lo1 = sx(rng.getrandbits(32)), sx(rng.getrandbits(32))
            case.acc = rng.getrandbits(32)
            case.sa = rng.randrange(16)
    if recipe != 'random':
        # callee-saved registers hold recognisable values so that a lost save shows
        for n in range(16, 24):
            case.r[n] = sx(0x5A000000 + n * 0x1111)
        case.r[30] = sx(0x5E000000)
    case.r[29] = SP
    case.r[31] = RETURN_ADDR
    return case


def table_functions():
    funcs = []
    with open(os.path.join(ROOT, 'ghidra_funcs.tsv')) as source:
        for line in source:
            if line.strip() and not line.startswith('#'):
                funcs.append(int(line.split('\t')[0], 16))
    return funcs


def sweep_worker(job):
    funcs, mode, steps, seeds, index = job
    ref = Reference()
    cases = []
    for func in funcs:
        for recipe in RECIPES:
            for seed in range(seeds):
                cases.append(make_case(func, recipe, seed, steps, mode == 'stub'))
    workdir = os.path.join(OUT, 'difftest')
    os.makedirs(workdir, exist_ok=True)
    natives = run_native(cases, ref.pristine, workdir, 'w%d-%d' % (os.getpid(), index))
    rows = []
    for case, nat in zip(cases, natives):
        status, out = ref.run(case)
        if status == 'return':
            diffs = compare(out, nat)
            rows.append((case.func, case.tag, 'pass' if not diffs else 'fail', diffs[:6], ref.emu.steps))
        elif (status in ('trap', 'unimpl') and NATIVE_STATUS[nat.status] == 'trap' and out.info == nat.info
              and (out.pages or not any(a >= RAM for a in ref.emu.mem.auto_mapped))):
            # both stop at the same instruction: the state there can be compared
            diffs = compare(out, nat, 'trap')
            rows.append((case.func, case.tag, 'pass@stop' if not diffs else 'fail', diffs[:6], ref.emu.steps))
        else:
            native = NATIVE_STATUS[nat.status]
            agree = {'fault': 'fault', 'trap': 'trap', 'unimpl': 'trap', 'steps': 'budget'}.get(status)
            if status == 'unaligned':
                agree = native      # the interpreter refuses unaligned accesses; nothing to compare
            rows.append((case.func, case.tag, 'stop:%s/%s' % (status, native),
                         [] if agree == native or status in ('steps', 'error') else ['interpreter %s (%s), translation %s (0x%x)' % (status, ref.message, native, nat.info)],
                         ref.emu.steps))
    return rows


def sweep(args):
    import multiprocessing
    funcs = table_functions()
    if args.only:
        wanted = {int(x, 16) for x in args.only.split(',')}
        funcs = [f for f in funcs if f in wanted]
    if args.limit:
        funcs = funcs[:args.limit]
    batch = 40
    jobs = [(funcs[i:i + batch], args.mode, args.steps, args.seeds, i // batch) for i in range(0, len(funcs), batch)]
    start = time.time()
    rows = []
    with multiprocessing.Pool(args.jobs) as pool:
        for done, part in enumerate(pool.imap_unordered(sweep_worker, jobs)):
            rows.extend(part)
            if (done + 1) % 20 == 0:
                print('  %d/%d batches, %.0f s' % (done + 1, len(jobs), time.time() - start), flush=True)
    per = {}
    for func, tag, verdict, diffs, steps in rows:
        per.setdefault(func, []).append((tag, verdict, diffs, steps))
    passed = failed = none = 0
    case_pass = case_fail = case_stop = case_stop_same = 0
    partial = 0
    stops = {}
    failures = []
    steps_total = 0
    for func in funcs:
        results = per.get(func, [])
        verdicts = [r[1] for r in results]
        case_pass += verdicts.count('pass')
        case_stop_same += verdicts.count('pass@stop')
        case_fail += verdicts.count('fail')
        for tag, verdict, diffs, steps in results:
            steps_total += steps
            if verdict.startswith('stop'):
                case_stop += 1
                stops[verdict] = stops.get(verdict, 0) + 1
        if 'fail' in verdicts:
            failed += 1
            failures.append((func, [(t, d) for t, v, d, s in results if v == 'fail']))
        elif 'pass' in verdicts:
            passed += 1
        elif 'pass@stop' in verdicts:
            partial += 1
        else:
            none += 1
    lines = ['mode %s, %d functions, %d cases, %d interpreter steps, %.0f s' % (
        args.mode, len(funcs), len(rows), steps_total, time.time() - start),
        'functions: %d pass, %d identical only up to an instruction both sides stop at, %d FAIL, '
        '%d without a comparable case' % (passed, partial, failed, none),
        'cases: %d identical to the return, %d identical up to a common stop, %d DIFFERENT, '
        '%d stopped in the interpreter and not comparable' % (case_pass, case_stop_same, case_fail, case_stop),
        'stopped cases by (interpreter/translation): ' + ', '.join(
            '%s %d' % (k[5:], v) for k, v in sorted(stops.items(), key=lambda kv: -kv[1]))]
    odd = [(func, tag, verdict, diffs) for func, tag, verdict, diffs, steps in rows
           if verdict.startswith('stop') and diffs and verdict.split(':')[1] in (
               'trap/return', 'trap/fault', 'trap/badcall', 'unimpl/fault', 'unimpl/badcall', 'fault/badcall', 'trap/budget')]
    for func, tag, verdict, diffs in odd[:args.odd]:
        lines.append('odd %08x [%s] %s' % (func, tag, diffs[0][:230]))
    for func, items in failures[:60]:
        lines.append('FAIL %08x' % func)
        for tag, diffs in items[:2]:
            lines.append('    [%s] %s' % (tag, '; '.join(diffs[:4])))
    text = '\n'.join(lines)
    print(text)
    if args.report:
        with open(args.report, 'w') as sink:
            sink.write(text + '\n')
            sink.write('# function\tverdict per recipe\n')
            for func in funcs:
                sink.write('%08x\t%s\n' % (func, ' '.join('%s=%s' % (t, v) for t, v, d, s in per.get(func, []))))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('sweep')
    p.add_argument('--mode', choices=('stub', 'follow'), default='stub')
    p.add_argument('--only')
    p.add_argument('--limit', type=int)
    p.add_argument('--jobs', type=int, default=max(2, (os.cpu_count() or 4) - 4))
    p.add_argument('--steps', type=int, default=100000)
    p.add_argument('--seeds', type=int, default=1)
    p.add_argument('--report')
    p.add_argument('--odd', type=int, default=0, help='print this many stopped cases whose two sides stopped differently')
    p = sub.add_parser('replay')
    p.add_argument('script')
    p.add_argument('rest', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not os.path.isfile(ELF):
        print('no executable at %s (bring your own SLUS_209.73)' % ELF)
        return 0
    if not os.path.isfile(DRIVER):
        print('no test driver at %s: run recomp.py, then build.py test' % DRIVER)
        return 2
    if args.command == 'sweep':
        return sweep(args)
    import replay
    return replay.run(args.script, args.rest)


if __name__ == '__main__':
    sys.exit(main())
