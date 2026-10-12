#!/usr/bin/env python3
"""replay.py - run a reference-model test (tools/difftest_*.py) and put every call it makes
into the game's code through the translation as well.

Used through `difftest.py replay <script> [script args]`.  The script runs unchanged; the
interpreter's `call` is wrapped.  For each call the wrapper keeps the state before (all
registers, every memory page that differs from the executable's image, the stubs in force)
and the state after (registers, calls made, pages changed), then the translation is run
from the same "before" and must arrive at the same "after".

What is replayed: calls made under the interpreter's default floating-point model ('ps2',
the model the translation's test build implements), that return normally, whose stubs are
plain "return a constant" stubs.  A call during which a Python-implemented stub or hook
fires is skipped (its effect cannot be given to the translation) and counted.  At most
PER_FUNCTION calls are replayed per function per script.
"""
import os
import runpy
import sys

import difftest
from difftest import Case, Outcome, compare, run_native, ZERO_PAGE, RAM, M64
import ee_emu
from ee_emu import EE

PER_FUNCTION = 150
TEXT_LO, TEXT_HI = 0x100000, 0x3E6000
BATCH = 100


class Recorder:
    def __init__(self):
        self.pristine = None
        self.pending = []           # (case, expected outcome)
        self.count = {}             # function -> calls replayed
        self.stats = {'calls': 0, 'replayed': 0, 'identical': 0, 'different': 0, 'other_fpu': 0,
                      'python_stub': 0, 'over_cap': 0, 'not_returned': 0, 'outside_ram': 0,
                      'code_patched': 0}
        self.failed = {}
        self.passed = set()
        self.batches = 0
        self.workdir = os.path.join(difftest.OUT, 'difftest')
        os.makedirs(self.workdir, exist_ok=True)

    def native_pristine(self):
        if self.pristine is None:
            segments, _entry = ee_emu.load_elf_segments(difftest.ELF)
            pages = {}
            for vaddr, blob, memsz in segments:
                for index in range(vaddr >> 12, ((vaddr + max(len(blob), 1) - 1) >> 12) + 1):
                    pages.setdefault(index, bytearray(4096))
                pos = 0
                while pos < len(blob):
                    index, off = (vaddr + pos) >> 12, (vaddr + pos) & 0xFFF
                    take = min(len(blob) - pos, 4096 - off)
                    pages[index][off:off + take] = blob[pos:pos + take]
                    pos += take
            self.pristine = {k: bytes(v) for k, v in pages.items()}
        return self.pristine

    def flush(self):
        if not self.pending:
            return
        cases = [c for c, _ in self.pending]
        self.batches += 1
        natives = run_native(cases, self.native_pristine(), self.workdir, 'r%d-%d' % (os.getpid(), self.batches))
        for (case, expected), nat in zip(self.pending, natives):
            diffs = compare(expected, nat)
            if diffs:
                self.stats['different'] += 1
                self.failed.setdefault(case.func, []).append(diffs[:4])
            else:
                self.stats['identical'] += 1
                self.passed.add(case.func)
        self.pending = []


REC = Recorder()
_original_call = EE.call
_in_call = [False]


def _classify_hooks(emu):
    """(constant stubs, wrapped hook table or None when nothing needs watching)."""
    stubs, watch = [], {}
    for addr, function in emu.hooks.items():
        cells = {}
        if getattr(function, '__name__', '') == 'run_stub' and function.__closure__:
            cells = dict(zip(function.__code__.co_freevars, [c.cell_contents for c in function.__closure__]))
        if cells and cells.get('function') is None:
            stubs.append((addr, cells.get('ret')))
        else:
            watch[addr] = function
    return stubs, watch


def call(self, addr, *args, fargs=(), max_steps=5000000, sp=None):
    if _in_call[0]:
        return _original_call(self, addr, *args, fargs=fargs, max_steps=max_steps, sp=sp)
    stats = REC.stats
    stats['calls'] += 1
    skip = None
    if self.fpu_model != 'ps2' or self.fpu_mul_bias or self.fpu_div_nearest:
        skip = 'other_fpu'
    elif REC.count.get(addr, 0) >= PER_FUNCTION:
        skip = 'over_cap'
    elif self.breakpoints or self.default_ret not in (0, None):
        skip = 'python_stub'
    if skip:
        stats[skip] += 1
        return _original_call(self, addr, *args, fargs=fargs, max_steps=max_steps, sp=sp)

    # the argument set-up of EE.call, done here so that the state before is complete
    if len(args) > 8:
        raise ValueError('at most 8 register arguments')
    for index, value in enumerate(args):
        self.r[4 + index] = int(value) & M64
    for index, value in enumerate(fargs):
        self.f[12 + index] = ee_emu.float_to_raw(value)
    if sp is not None:
        self.r[29] = sp & M64
    self.r[31] = self.RETURN_ADDR

    case = Case(addr)
    case.budget = min(max_steps, 5000000)
    case.r, case.rh = list(self.r), list(self.rh)
    case.r[0] = case.rh[0] = 0
    case.hi, case.lo, case.hi1, case.lo1 = self.hi, self.lo, self.hi1, self.lo1
    case.sa, case.fcr31, case.acc = self.sa, self.fcr31, self.acc
    case.f = list(self.f)
    case.cop0 = [v & 0xFFFFFFFF for v in self.cop0]
    stubs, watch = _classify_hooks(self)
    case.stubs = stubs
    policy = self.follow
    decisions = {}
    if policy is not None:
        # the script's follow policy may be any object with `in`; what it answers for
        # each call target during this call is what the translation's run is given
        class Recording:
            def __contains__(_self, target):
                answer = target in policy
                decisions.setdefault(target, set()).add(bool(answer))
                return answer
        self.follow = Recording()
        case.stub_all = True
        case.keep_v0 = self.default_ret is None
    before = {index: bytes(page) for index, page in self.mem.pages.items()}
    fired = [False]
    saved_hooks = None
    if watch:
        saved_hooks = dict(self.hooks)
        for target, function in watch.items():
            def spy(emu, function=function):
                fired[0] = True
                return function(emu)
            self.hooks[target] = spy
    calls_before = len(self.calls)
    record = self.record_calls
    self.record_calls = True
    _in_call[0] = True
    try:
        result = _original_call(self, addr, max_steps=max_steps)
    except BaseException:
        stats['not_returned'] += 1
        raise
    finally:
        _in_call[0] = False
        self.follow = policy
        self.record_calls = record
        if saved_hooks is not None:
            self.hooks.clear()
            self.hooks.update(saved_hooks)
    made = self.calls[calls_before:]
    if not record:
        del self.calls[calls_before:]
    if fired[0] or any(len(answers) > 1 for answers in decisions.values()):
        stats['python_stub'] += 1
        return result
    case.follow = sorted(target for target, answers in decisions.items() if True in answers)
    pristine = REC.native_pristine()
    if any(index >= (RAM >> 12) for index in self.mem.pages):
        # memory outside the 32 MB (e.g. a scratchpad the script mapped) - only a problem
        # when it holds something or changed
        for index, page in self.mem.pages.items():
            if index >= (RAM >> 12) and (bytes(page) != ZERO_PAGE or before.get(index, ZERO_PAGE) != ZERO_PAGE):
                stats['outside_ram'] += 1
                return result
    for index, page in before.items():
        if index < (RAM >> 12) and page != pristine.get(index, ZERO_PAGE):
            if TEXT_LO <= (index << 12) < TEXT_HI:
                # the script changed code (a patch under test, or instructions of its own):
                # the translation is of the unmodified executable
                stats['code_patched'] += 1
                return result
            case.patches.append((index << 12, page))
    expected = Outcome()
    expected.status, expected.info = 'return', 0
    expected.r, expected.rh = list(self.r), list(self.rh)
    expected.hi, expected.lo, expected.hi1, expected.lo1 = self.hi, self.lo, self.hi1, self.lo1
    expected.sa, expected.fcr31, expected.f, expected.acc = self.sa, self.fcr31, list(self.f), self.acc
    expected.call_total = len(made)
    expected.calls = [(rec.site, rec.target, tuple(a & M64 for a in rec.args), tuple(rec.fargs)) for rec in made[:512]]
    pages = {}
    for index, page in self.mem.pages.items():
        if index >= (RAM >> 12):
            continue
        final = bytes(page)
        if final != before.get(index, ZERO_PAGE):
            pages[index] = final
    expected.pages = pages
    REC.count[addr] = REC.count.get(addr, 0) + 1
    stats['replayed'] += 1
    REC.pending.append((case, expected))
    if len(REC.pending) >= BATCH:
        REC.flush()
    return result


def run(script, rest):
    EE.call = call
    sys.argv = [script] + list(rest)
    sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
    code = 0
    try:
        runpy.run_path(script, run_name='__main__')
    except SystemExit as exc:
        code = exc.code or 0
    finally:
        EE.call = _original_call
    REC.flush()
    s = REC.stats
    print('---- replay through the translation: %s' % os.path.basename(script))
    print('calls into game code: %d; replayed: %d (identical %d, DIFFERENT %d)' % (
        s['calls'], s['replayed'], s['identical'], s['different']))
    print('not replayed: %d under another FPU model, %d beyond %d per function, %d with a Python stub or '
          'hook firing, %d that did not return, %d touching memory outside the 32 MB, %d on code the script changed' % (
              s['other_fpu'], s['over_cap'], PER_FUNCTION, s['python_stub'], s['not_returned'], s['outside_ram'],
              s['code_patched']))
    print('functions replayed: %d; all identical: %d; with a difference: %d' % (
        len(REC.count), len(REC.passed - set(REC.failed)), len(REC.failed)))
    for func, items in sorted(REC.failed.items())[:20]:
        print('  DIFFERENT %08x: %s' % (func, '; '.join(items[0])))
    print('REPLAY\t%s\t%d\t%d\t%d\t%d\t%d\t%s' % (os.path.basename(script), s['calls'], s['replayed'], s['identical'],
                                              s['different'], len(REC.count),
                                              ','.join('%x' % f for f in sorted(REC.count))))
    return 1 if s['different'] else (code if isinstance(code, int) else 1)
