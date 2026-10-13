#!/usr/bin/env python3
"""realproof.py - the functions the automatic sweep could not drive, on inputs taken from
the running game.

tools/recomp/difftest.py compares every function of the executable in the interpreter
(tools/ee_emu.py) and in the translation on synthetic inputs; for 301 functions the
interpreter stops on every one of them (a made-up pointer, an endless wait).  Here the
inputs are real: the instrumented runtime (proof_rt.cpp, --opt proof-capture) records the
registers and all of memory at the moment the game enters a function, and each recorded
state is run to the function's return twice - in the interpreter and in the translation
(proof_driver) - and everything observable is compared, as difftest.py does: all general
registers (128 bits), HI/LO and the second pair, the shift-amount register, the FPU
registers, accumulator and compare bit, every call made (site, target, eight integer and
eight float argument registers) and every byte of main memory, the scratchpad and any
other memory touched.

  python3 tools/recomp/proof/realproof.py want    [--sweep FILE]
  python3 tools/recomp/proof/realproof.py replay  DIR [--jobs N] [--steps N] [--stub-steps N] [--all]
  python3 tools/recomp/proof/realproof.py report  [DIR ...] [--hits FILE ...]
  python3 tools/recomp/proof/realproof.py bounded DIR [--events 16,256,4096] [--only ADDR,...]

want    reads the sweep's report and writes local/recomp-out/proof/want.txt: the functions
        without a comparable case (and those identical only up to a common stop), with the
        reason the interpreter stopped on the synthetic inputs.
replay  runs the states recorded in DIR (pages.bin, captures.bin).  Each state is tried
        with callees running ("follow": the whole call tree is compared); when the
        interpreter does not reach the return within --steps instructions, again with
        every call replaced by "return 0" on both sides ("stub": the function's own
        translation on real arguments and memory).  Writes DIR/results.tsv.
report  the table: of the functions in want.txt, how many now have an identical
        comparable case, how many were never entered in any session, how many differ.

bounded for the functions that never return in isolation (they wait for an interrupt or an
        answer): both sides are stopped after the same number of counted events - the
        translation counts every call and every taken backward branch inside a unit
        (BUDGET), the interpreter is made to count the same (BoundedEE; the branch sites
        come from the snapshot translator, build_proof.py sites) - and the whole state
        is compared there: verdict pass@bound.  Writes DIR/bounded.tsv.

Verdicts: pass (ran to the return, identical), pass@stop (both stopped at the same
instruction - BREAK, a vector-unit instruction - identical up to there), FAIL (a
difference), stop:<why> (the interpreter did not finish; nothing proved).
"""
import argparse
import mmap
import multiprocessing
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RECOMP = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(RECOMP))
sys.path.insert(0, RECOMP)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import difftest                                 # noqa: E402
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
sys.path.insert(0, HERE)
import vu0ref                                   # noqa: E402

OUT = os.path.join(ROOT, 'local', 'recomp-out')
PROOF = os.path.join(OUT, 'proof')
DRIVER = os.environ.get('PROOF_DRIVER') or os.path.join(PROOF, 'build', 'bin', 'proof_driver')      # built from the snapshot (build_proof.py)
SITES = os.path.join(PROOF, 'build', 'budget-sites.txt')
SKEW = int(os.environ.get('PROOF_BOUND_SKEW', '0'))     # a control: the interpreter stops this many events later than the translation
RAM_PAGES = 0x02000000 >> 12
PAGES = RAM_PAGES + 4
SPR_PAGE = 0x70000000 >> 12
MIRRORS = (0x20000000, 0x30000000, 0x80000000, 0xA0000000)
HEAD = struct.Struct('<6I16s')
BODY = struct.Struct('<32Q32Q4Q2I32II')
NATIVE_STATUS = difftest.NATIVE_STATUS


VU_MODEL = os.environ.get('PROOF_VU_MODEL', 'host')      # vu0ref.py: 'host' (rt/vu0.h as it is) or 'console' (as proposed)


class Outcome(difftest.Outcome):
    __slots__ = ('vu',)


class Capture:
    __slots__ = ('index', 'number', 'addr', 'hit', 'episode', 'tick', 'level', 'r', 'rh', 'hi', 'lo', 'hi1', 'lo1',
                 'sa', 'fcr31', 'f', 'acc', 'changed', 'vu')


def load_captures(directory):
    with open(os.path.join(directory, 'captures.bin'), 'rb') as source:
        data = source.read()
    out, pos = [], 0
    while pos + HEAD.size + BODY.size + 4 <= len(data):
        magic, number, addr, hit, episode, tick, level = HEAD.unpack_from(data, pos)
        if magic not in (0x50414350, 0x32414350):
            raise ValueError('bad state record at %d' % pos)
        pos += HEAD.size
        v = BODY.unpack_from(data, pos)
        pos += BODY.size
        cap = Capture()
        cap.index, cap.number, cap.addr, cap.hit, cap.episode, cap.tick = len(out), number, addr, hit, episode, tick
        cap.level = level.split(b'\0')[0].decode('latin1')
        cap.r, cap.rh = list(v[0:32]), list(v[32:64])
        cap.hi, cap.lo, cap.hi1, cap.lo1, cap.sa, cap.fcr31 = v[64:70]
        cap.f, cap.acc = list(v[70:102]), v[102]
        count, = struct.unpack_from('<I', data, pos)
        pos += 4
        if pos + 8 * count > len(data):
            break                               # a run that was cut short
        cap.changed = struct.unpack_from('<%dI' % (2 * count), data, pos)
        pos += 8 * count
        cap.vu = None
        if magic == 0x32414350:                 # with the vector unit's state
            if pos + vu0ref.STATE.size > len(data):
                break
            cap.vu = data[pos:pos + vu0ref.STATE.size]
            pos += vu0ref.STATE.size
        out.append(cap)
    return out


def _syscall_stub(emu):
    emu.r[2] = 0


class BoundReached(EmuError):
    """The interpreter has counted as many events as the translation was given."""


class BoundedEE(EE):
    """The interpreter with the translation's count: the translation decrements its budget
    at every taken branch or jump to a target at or before it inside the same unit and at
    every call, and stops when the budget is gone (rt_budget).  Counting the same events
    here stops both sides at the same point of the same instruction stream, whatever the
    function is waiting for - and there the whole state can be compared.

    An event is counted where the translation counts it: after the delay slot, before the
    first instruction of the target runs.  `events` None: no bound."""

    sites = frozenset()
    events = None
    _arrive = None

    def _note(self, target):
        self._arrive = target
        if target not in self.hooks:
            self.hooks[target] = BoundedEE._arrived

    def _arrived(self):
        pc = self.pc
        if self.hooks.get(pc) is BoundedEE._arrived:
            del self.hooks[pc]
        if self._arrive == pc:
            self._arrive = None
            self._count()

    def _count(self):
        if self.events is not None:
            self.events -= 1
            if self.events < 0:
                raise BoundReached('bound')

    def _branch(self, taken, word, likely=False):
        EE._branch(self, taken, word, likely)
        if taken and self.cur in self.sites:
            self._note(self.npc)

    def _j(self, w):
        EE._j(self, w)
        if self.cur in self.sites:
            self._note(self.npc)

    def _enter_call(self, target):
        self._count()
        return EE._enter_call(self, target)


class VuEE(BoundedEE):
    """The interpreter with vector unit 0 (vu0ref.py): the COP2 forms the game uses, LQC2
    and SQC2, and the unit's microprogram and data memory at 0x11000000 / 0x11004000."""

    def __init__(self, *args, **kwargs):
        BoundedEE.__init__(self, *args, **kwargs)
        self.vu = vu0ref.Vu0(VU_MODEL)
        for op in (0x12, 0x36, 0x3E):
            self._ops[op] = self._vu_op

    def _vu_op(self, w):
        try:
            self.vu.cop2(self, w)
        except vu0ref.Unimplemented as exc:
            self._unimplemented(w, str(exc))

    def _load16(self, addr):
        return self.mem.load(addr, 16)

    def _store16(self, addr, value):
        self.mem.store(addr, 16, value)


def vu_diffs(out, nat):
    """Differences between the two sides' vector unit after a run (Q is not compared: the
    game's program does not use it and rt/vu0.h does not keep it)."""
    if getattr(out, 'vu', None) is None or getattr(nat, 'vu', None) is None:
        return []
    a, b = vu0ref.STATE.unpack(out.vu), vu0ref.STATE.unpack(nat.vu)
    diffs = []
    for n in range(128):
        if a[n] != b[n]:
            diffs.append('vf%d.%s = %08x, translation %08x' % (n // 4, 'xyzw'[n % 4], a[n], b[n]))
    for n in range(16):
        if a[128 + n] != b[128 + n]:
            diffs.append('vi%d = %x, translation %x' % (n, a[128 + n], b[128 + n]))
    for n in range(4):
        if a[144 + n] != b[144 + n]:
            diffs.append('acc.%s = %08x, translation %08x' % ('xyzw'[n], a[144 + n], b[144 + n]))
    if a[149] != b[149]:
        diffs.append('I = %08x, translation %08x' % (a[149], b[149]))
    for n in range(32):
        if a[150 + n] != b[150 + n]:
            diffs.append('control %d = %x, translation %x' % (n, a[150 + n], b[150 + n]))
    for name, x, y in (('microprogram', a[182], b[182]), ('data', a[183], b[183])):
        if x != y:
            off = next(i for i in range(4096) if x[i] != y[i])
            diffs.append('vector unit %s memory +%03x = %02x, translation %02x' % (name, off, x[off], y[off]))
    return diffs


def budget_sites():
    if not os.path.exists(SITES):
        raise SystemExit('no %s: run build_proof.py sites' % SITES)
    return frozenset(int(line, 16) for line in open(SITES) if line.strip() and not line.startswith('#'))


class RealReference:
    """The interpreter on recorded states."""

    def __init__(self, directory, bounded=False):
        emu = self.emu = VuEE(None, fpu_model='ps2')
        if bounded:
            emu.sites = budget_sites()
        emu.mem.auto_map = True
        emu.div_zero = 'r5900'
        emu.stack_lo = emu.stack_hi = 0
        emu.record_writes = False
        self.file = open(os.path.join(directory, 'pages.bin'), 'rb')
        self.store = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.pages = [bytearray(4096) for _ in range(PAGES)]
        self.have = [-1] * PAGES                # number in the store of what a page holds; -1 unknown
        self.want = [0] * PAGES
        self.base = {}
        for page in range(RAM_PAGES):
            self.base[page] = self.pages[page]
            for mirror in MIRRORS:
                self.base[(mirror >> 12) + page] = self.pages[page]
        for k in range(4):
            self.base[SPR_PAGE + k] = self.pages[RAM_PAGES + k]
        self.base[vu0ref.MICRO >> 12] = emu.vu.micro
        self.base[vu0ref.MEM >> 12] = emu.vu.mem
        emu.mem.pages = dict(self.base)
        self.message = ''

    def advance(self, cap):
        """Apply a state's page changes to `want` (states must be visited in file order)."""
        changed = cap.changed
        for i in range(0, len(changed), 2):
            if changed[i] < PAGES:
                self.want[changed[i]] = changed[i + 1]

    def materialise(self):
        store, pages, have, want = self.store, self.pages, self.have, self.want
        for page in range(PAGES):
            ref = want[page]
            if have[page] != ref:
                pages[page][:] = store[ref * 4096:ref * 4096 + 4096]
                have[page] = ref

    def run(self, cap, stub_all, budget, events=None):
        emu = self.emu
        emu.events, emu._arrive = events, None
        fresh = vu0ref.Vu0(VU_MODEL)
        emu.vu.load(cap.vu if cap.vu is not None else fresh.dump())
        self.materialise()
        emu.mem.pages = dict(self.base)
        emu.mem.auto_mapped = []
        emu.hooks.clear()
        emu.stub_names.clear()
        emu.breakpoints.clear()
        emu.r[:] = cap.r
        emu.rh[:] = cap.rh
        emu.r[0] = emu.rh[0] = 0
        emu.hi, emu.lo, emu.hi1, emu.lo1 = cap.hi, cap.lo, cap.hi1, cap.lo1
        emu.sa, emu.acc = cap.sa, cap.acc
        emu.fcr31 = (cap.fcr31 & 0x00800000) | 0x01000001
        emu.f[:] = cap.f
        emu.cop0[:] = [0] * 32
        emu.calls, emu.writes, emu.notes, emu.steps = [], [], [], 0
        emu._pending_call = emu._fresh_call = None
        emu.follow = set() if stub_all else None
        emu.default_ret = 0
        for addr in range(0, EE.RETURN_ADDR, 4):
            emu.hooks[addr] = difftest._null_jump
        emu.r[31] = EE.RETURN_ADDR
        emu.jump(cap.addr)
        emu.syscall_handler = _syscall_stub
        self.message = ''
        try:
            reason = emu.run(max_steps=budget)
            status = 'return' if reason == 'return' else 'error'
        except BoundReached:
            status = 'bound'
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
        o = Outcome()
        o.status, o.info = status, (emu.cur if status in ('trap', 'unimpl') else emu.pc)
        o.r, o.rh = list(emu.r), list(emu.rh)
        o.hi, o.lo, o.hi1, o.lo1 = emu.hi, emu.lo, emu.hi1, emu.lo1
        o.sa, o.fcr31, o.f, o.acc = emu.sa, emu.fcr31, list(emu.f), emu.acc
        o.call_total = len(emu.calls)
        o.calls = [(rec.site, rec.target, tuple(a & ee_emu.M64 for a in rec.args), tuple(rec.fargs)) for rec in emu.calls[:512]]
        # every page that no longer holds what the state had
        store, pages, have, want = self.store, self.pages, self.have, self.want
        changed = {}
        for page in range(PAGES):
            ref = want[page]
            if pages[page] != store[ref * 4096:ref * 4096 + 4096]:
                changed[page if page < RAM_PAGES else SPR_PAGE + page - RAM_PAGES] = bytes(pages[page])
                have[page] = -1
        zero = bytes(4096)
        for addr in emu.mem.auto_mapped:
            index = addr >> 12
            page = emu.mem.pages.get(index)
            if page is not None and index not in self.base and bytes(page) != zero:
                changed[index] = bytes(page)
        o.pages = changed
        o.vu = emu.vu.dump() if cap.vu is not None else None
        return status, o


def read_native(path, count, pre_page):
    """Outcomes of proof_driver; pre_page(job number, page index) gives a page before the run."""
    with open(path, 'rb') as source:
        data = source.read()
    magic, n = struct.unpack_from('<II', data, 0)
    if magic not in (0x31525352, 0x32525352) or n != count:
        raise ValueError('bad result file')
    pos, outcomes = 8, []
    for job in range(n):
        o = Outcome()
        o.status, o.info = struct.unpack_from('<II', data, pos); pos += 8
        o.r = list(struct.unpack_from('<32Q', data, pos)); pos += 256
        o.rh = list(struct.unpack_from('<32Q', data, pos)); pos += 256
        o.hi, o.lo, o.hi1, o.lo1 = struct.unpack_from('<4Q', data, pos); pos += 32
        o.sa, o.fcr31 = struct.unpack_from('<II', data, pos); pos += 8
        o.f = list(struct.unpack_from('<32I', data, pos)); pos += 128
        o.acc, o.call_total, ncalls = struct.unpack_from('<III', data, pos); pos += 12
        o.calls = []
        for _ in range(ncalls):
            site, target, _stubbed, _pad = struct.unpack_from('<4I', data, pos)
            o.calls.append((site, target, struct.unpack_from('<8Q', data, pos + 16), struct.unpack_from('<8I', data, pos + 80)))
            pos += 112
        runs, = struct.unpack_from('<I', data, pos); pos += 4
        raw = []
        for _ in range(runs):
            addr, length = struct.unpack_from('<II', data, pos); pos += 8
            raw.append((addr, data[pos:pos + length]))
            pos += (length + 3) & ~3
        o.pages = raw                           # turned into pages by the caller, which has the state
        o.vu = None
        if magic == 0x32525352:
            o.vu = data[pos:pos + vu0ref.STATE.size]
            pos += vu0ref.STATE.size
        outcomes.append(o)
    return outcomes


def native_pages(runs, ref):
    """{page index: bytes} from the driver's runs of changed bytes."""
    pages = {}
    for addr, blob in runs:
        index = addr >> 12
        page = pages.get(index)
        if page is None:
            if index < RAM_PAGES:
                r = ref.want[index]
                page = bytearray(ref.store[r * 4096:r * 4096 + 4096])
            elif SPR_PAGE <= index < SPR_PAGE + 4:
                r = ref.want[RAM_PAGES + index - SPR_PAGE]
                page = bytearray(ref.store[r * 4096:r * 4096 + 4096])
            else:
                page = bytearray(4096)
            pages[index] = page
        page[addr & 0xFFF:(addr & 0xFFF) + len(blob)] = blob
    return {k: bytes(v) for k, v in pages.items()}


def judge(status, out, nat):
    """(verdict, detail) for one run of one state."""
    native = NATIVE_STATUS[nat.status]
    if status == 'return':
        diffs = difftest.compare(out, nat) + vu_diffs(out, nat)
        return ('pass', '') if not diffs else ('FAIL', '; '.join(diffs[:4]))
    if status in ('trap', 'unimpl') and native == 'trap' and out.info == nat.info:
        diffs = difftest.compare(out, nat, 'trap') + vu_diffs(out, nat)
        return ('pass@stop', '%x' % out.info) if not diffs else ('FAIL', 'at stop %x: %s' % (out.info, '; '.join(diffs[:4])))
    # nothing to compare at an end; the calls made so far still can be
    shared = min(len(out.calls), len(nat.calls))
    agree = all(out.calls[i] == nat.calls[i] for i in range(shared))
    detail = 'translation %s; first %d calls %s' % (native, shared, 'agree' if agree else 'DIFFER')
    return 'stop:%s' % status, detail


def judge_bounded(status, out, nat):
    """As judge(), for a run both sides were to stop after the same count of events."""
    native = NATIVE_STATUS[nat.status]
    if status == 'bound' and native == 'budget':
        diffs = difftest.compare(out, nat, 'budget') + vu_diffs(out, nat)
        return ('pass@bound', '') if not diffs else ('FAIL', 'at the bound: ' + '; '.join(diffs[:4]))
    if status == 'return' and native == 'return':
        diffs = difftest.compare(out, nat)
        return ('pass', '') if not diffs else ('FAIL', '; '.join(diffs[:4]))
    if status in ('trap', 'unimpl') and native == 'trap' and out.info == nat.info:
        diffs = difftest.compare(out, nat, 'trap')
        return ('pass@stop', '%x' % out.info) if not diffs else ('FAIL', 'at stop %x: %s' % (out.info, '; '.join(diffs[:4])))
    if status in ('bound', 'return') or native in ('budget', 'return'):
        # one side reached the bound or the return and the other did not: the two did not
        # count alike, or ran differently
        return 'FAIL', 'interpreter %s at %x, translation %s' % (status, out.info, native)
    return 'stop:%s' % status, 'translation %s' % native


def bounded_worker(job):
    directory, first, last, steps, wanted, bounds, tag = job
    caps = load_captures(directory)
    ref = RealReference(directory, bounded=True)
    chosen = [c for c in caps[first:last] if c.addr in wanted]
    if not chosen:
        return []
    work = os.path.join(directory, 'work')
    os.makedirs(work, exist_ok=True)
    jobs_path = os.path.join(work, 'bjobs-%s.bin' % tag)
    result_path = os.path.join(work, 'bresults-%s.bin' % tag)
    plan = [(cap, stub, bound) for cap in chosen for stub in (0, 1) for bound in bounds]
    with open(jobs_path, 'wb') as sink:
        sink.write(struct.pack('<II', 0x424F4A50, len(plan)))
        for cap, stub, bound in plan:
            sink.write(struct.pack('<IIq', cap.index, stub, bound))
    done = subprocess.run(['nice', '-n', '15', DRIVER, directory, jobs_path, result_path], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError('proof_driver failed (%d): %s' % (done.returncode, done.stderr[:400]))
    natives = read_native(result_path, len(plan), None)
    os.remove(jobs_path)
    os.remove(result_path)
    rows, position = [], 0
    for n, (cap, stub, bound) in enumerate(plan):
        while position <= cap.index:
            ref.advance(caps[position])
            position += 1
        nat = natives[n]
        status, out = ref.run(cap, bool(stub), steps, events=bound + SKEW)
        nat.pages = native_pages(nat.pages, ref)
        verdict, detail = judge_bounded(status, out, nat)
        rows.append((cap.index, cap.addr, cap.hit, cap.episode, cap.tick, cap.level, '%s/%d' % ('stub' if stub else 'follow', bound),
                     verdict, ref.emu.steps, detail or ref.message[:120]))
    return rows


def bounded(args):
    """The functions that wait: both sides stopped after the same number of counted events."""
    caps = load_captures(args.dir)
    if args.only:
        wanted = {int(x, 16) for x in args.only.split(',')}
    else:
        # the functions whose every replayed state ended at the step limit
        wanted, seen = set(), {}
        for line in open(os.path.join(args.dir, 'results.tsv')):
            if not line.startswith('#'):
                p = line.rstrip('\n').split('\t')
                seen.setdefault(int(p[1], 16), set()).add(p[7])
        wanted = {f for f, verdicts in seen.items() if all(v.startswith('stop:') for v in verdicts)}
    bounds = [int(x) for x in args.events.split(',')]
    step = max(1, (len(caps) + args.jobs * 4 - 1) // (args.jobs * 4))
    jobs = [(args.dir, at, min(len(caps), at + step), args.steps, wanted, bounds, '%d-%d' % (os.getpid(), at))
            for at in range(0, len(caps), step)]
    start = time.time()
    rows = []
    with multiprocessing.Pool(args.jobs) as pool:
        for part in pool.imap_unordered(bounded_worker, jobs):
            rows.extend(part)
    rows.sort()
    with open(os.path.join(args.dir, 'bounded.tsv'), 'w') as sink:
        sink.write('# state\tfunction\tcall\tepisode\ttick\tlevel\tmode/events\tverdict\tsteps\tdetail\n')
        for row in rows:
            sink.write('%d\t%08x\t%d\t%d\t%d\t%s\t%s\t%s\t%d\t%s\n' % row)
    counts, per = {}, {}
    for row in rows:
        key = row[7].split(':')[0]
        counts[key] = counts.get(key, 0) + 1
        per.setdefault(row[1], {}).setdefault(key, 0)
        per[row[1]][key] += 1
    print('%d functions, %d runs in %s, %.0f s: %s' % (len(per), len(rows), args.dir, time.time() - start,
                                                      ', '.join('%s %d' % kv for kv in sorted(counts.items()))))
    names = symbols()
    for func in sorted(per):
        print('  %08x %-28s %s' % (func, names.get(func, '')[:28], ', '.join('%s %d' % kv for kv in sorted(per[func].items()))))
    for row in rows:
        if row[7] == 'FAIL':
            print('FAIL %08x state %d (%s tick %d, %s): %s' % (row[1], row[0], row[5], row[4], row[6], row[9][:300]))
    return 1 if counts.get('FAIL') else 0


def replay_worker(job):
    directory, first, last, steps, stub_steps, wanted, tag = job
    caps = load_captures(directory)
    ref = RealReference(directory)
    chosen = [c for c in caps[first:last] if wanted is None or c.addr in wanted]
    if not chosen:
        return []
    work = os.path.join(directory, 'work')
    os.makedirs(work, exist_ok=True)
    jobs_path = os.path.join(work, 'jobs-%s.bin' % tag)
    result_path = os.path.join(work, 'results-%s.bin' % tag)
    with open(jobs_path, 'wb') as sink:
        sink.write(struct.pack('<II', 0x424F4A50, 2 * len(chosen)))
        for cap in chosen:
            sink.write(struct.pack('<IIq', cap.index, 0, 400000000))
            sink.write(struct.pack('<IIq', cap.index, 1, 400000000))
    done = subprocess.run(['nice', '-n', '19', DRIVER, directory, jobs_path, result_path], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError('proof_driver failed (%d): %s' % (done.returncode, done.stderr[:400]))
    natives = read_native(result_path, 2 * len(chosen), None)
    os.remove(jobs_path)
    os.remove(result_path)
    rows = []
    position = 0
    for n, cap in enumerate(chosen):
        while position <= cap.index:
            ref.advance(caps[position])
            position += 1
        results = []
        for mode, stub_all, budget in (('follow', False, steps), ('stub', True, stub_steps)):
            nat = natives[2 * n + (1 if stub_all else 0)]
            status, out = ref.run(cap, stub_all, budget)
            nat_pages = native_pages(nat.pages, ref)
            keep = nat.pages
            nat.pages = nat_pages
            verdict, detail = judge(status, out, nat)
            nat.pages = keep
            results.append((mode, verdict, ref.emu.steps, detail or ref.message[:120]))
            if verdict in ('pass', 'FAIL'):
                break
        for mode, verdict, count, detail in results:
            rows.append((cap.index, cap.addr, cap.hit, cap.episode, cap.tick, cap.level, mode, verdict, count, detail))
    return rows


def replay(args):
    caps = load_captures(args.dir)
    wanted = None
    if not args.all and os.path.exists(os.path.join(PROOF, 'want.txt')):
        wanted = {int(line.split()[0], 16) for line in open(os.path.join(PROOF, 'want.txt')) if line.strip() and not line.startswith('#')}
    if args.only:
        wanted = {int(x, 16) for x in args.only.split(',')}
    step = max(1, (len(caps) + args.jobs * 4 - 1) // (args.jobs * 4))
    jobs = [(args.dir, at, min(len(caps), at + step), args.steps, args.stub_steps, wanted, '%d-%d' % (os.getpid(), at))
            for at in range(0, len(caps), step)]
    start = time.time()
    rows = []
    with multiprocessing.Pool(args.jobs) as pool:
        for part in pool.imap_unordered(replay_worker, jobs):
            rows.extend(part)
    rows.sort()
    with open(os.path.join(args.dir, args.out), 'w') as sink:
        sink.write('# state\tfunction\tcall\tepisode\ttick\tlevel\tmode\tverdict\tsteps\tdetail\n')
        for row in rows:
            sink.write('%d\t%08x\t%d\t%d\t%d\t%s\t%s\t%s\t%d\t%s\n' % row)
    counts = {}
    for row in rows:
        counts[(row[6], row[7].split(':')[0])] = counts.get((row[6], row[7].split(':')[0]), 0) + 1
    print('%d states in %s, %d runs, %.0f s: %s' % (len(caps), args.dir, len(rows), time.time() - start,
                                                   ', '.join('%s %s %d' % (m, v, n) for (m, v), n in sorted(counts.items()))))
    for row in rows:
        if row[7] == 'FAIL':
            print('FAIL %08x state %d (%s tick %d, %s): %s' % (row[1], row[0], row[5], row[4], row[6], row[9][:300]))
    return 1 if any(row[7] == 'FAIL' for row in rows) else 0


# ---- the list of unproven functions ------------------------------------------------------------

def sweep_rows(path):
    rows = {}
    for line in open(path):
        parts = line.rstrip('\n').split('\t')
        if len(parts) == 2 and len(parts[0]) == 8:
            rows[int(parts[0], 16)] = [item.split('=')[1] for item in parts[1].split()]
    return rows


def why(verdicts):
    """The reason a function has no comparable case: what the interpreter stopped on in most
    of its twelve synthetic runs (ties go to the earlier name in the list)."""
    kinds = [v[5:].split('/')[0] for v in verdicts if v.startswith('stop:')]
    names = (('unaligned', 'unaligned access through a made-up pointer'),
             ('fault', 'wild pointer: memory outside the 32 MB'),
             ('steps', 'step limit: a loop that waits for something, or a very long one'),
             ('unimpl', 'an instruction the interpreter does not implement (vector unit, COP0)'),
             ('trap', 'BREAK or a trap'),
             ('error', 'a jump to address 0 or out of the code'))
    best, count = 'other', 0
    for key, text in names:
        if kinds.count(key) > count:
            best, count = text, kinds.count(key)
    return best


def want(args):
    rows = sweep_rows(args.sweep)
    os.makedirs(PROOF, exist_ok=True)
    none, partial, reasons = [], [], {}
    for func in sorted(rows):
        verdicts = rows[func]
        if 'pass' in verdicts:
            continue
        if 'pass@stop' in verdicts:
            partial.append(func)
            continue
        none.append(func)
        reasons.setdefault(why(verdicts), []).append(func)
    with open(os.path.join(PROOF, 'want.txt'), 'w') as sink:
        sink.write('# function\tclass\treason on synthetic inputs\n')
        for reason, funcs in reasons.items():
            for func in funcs:
                sink.write('%08x\tnone\t%s\n' % (func, reason))
        for func in partial:
            sink.write('%08x\tpartial\tidentical only up to an instruction both sides stop at\n' % func)
    print('%d functions without a comparable case, %d identical only up to a common stop' % (len(none), len(partial)))
    for reason, funcs in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
        print('  %4d  %s' % (len(funcs), reason))
    return 0


def read_want():
    out = {}
    for line in open(os.path.join(PROOF, 'want.txt')):
        if line.strip() and not line.startswith('#'):
            parts = line.rstrip('\n').split('\t')
            out[int(parts[0], 16)] = (parts[1], parts[2])
    return out


def symbols():
    import glob
    names = {}
    for path in [os.path.join(ROOT, 'names.tsv')] + sorted(glob.glob(os.path.join(ROOT, 'symbols', '*.tsv'))):
        for line in open(path):
            parts = line.split('\t')
            if len(parts) >= 2 and not line.startswith('#'):
                try:
                    names[int(parts[0], 16)] = parts[1].strip()
                except ValueError:
                    pass
    return names


def references(funcs):
    """{function: (call sites, jump sites, data words holding its address)} read from the
    executable: who could reach a function that no session entered."""
    import recomp
    image = recomp.Image(os.path.join(ROOT, 'SLUS_209.73'))
    wanted = set(funcs)
    out = {f: [0, 0, 0] for f in funcs}
    for index, w in enumerate(image.words):
        op = w >> 26
        if op in (2, 3):
            target = ((image.text_lo + 4 * index) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
            if target in wanted:
                out[target][0 if op == 3 else 1] += 1
    for _addr, value in image.data_words():
        if value in wanted:
            out[value][2] += 1
    return out


def report(args):
    wanted = read_want()
    best = {}                                   # function -> best verdict rank and row
    rank = {'FAIL': 5, 'pass': 4, 'pass@stop': 3}
    runs = 0
    for directory in args.dirs:
        path = os.path.join(directory, 'results.tsv')
        if not os.path.exists(path):
            continue
        for line in open(path):
            if line.startswith('#'):
                continue
            p = line.rstrip('\n').split('\t')
            func, mode, verdict = int(p[1], 16), p[6], p[7]
            runs += 1
            entry = best.setdefault(func, {'FAIL': 0, 'pass': 0, 'pass@stop': 0, 'stop': 0, 'modes': set(), 'why': {}, 'fail': ''})
            key = verdict if verdict in rank else 'stop'
            entry[key] += 1
            if verdict == 'pass':
                entry['modes'].add(mode)
            if key == 'stop':
                entry['why'][verdict] = entry['why'].get(verdict, 0) + 1
            if verdict == 'FAIL' and not entry['fail']:
                entry['fail'] = '%s state %s: %s' % (directory, p[0], p[9])
    hits = {}
    for path in args.hits or []:
        for line in open(path):
            p = line.split()
            if len(p) == 2:
                hits[int(p[0], 16)] = hits.get(int(p[0], 16), 0) + int(p[1])
    names = symbols()
    classes = {'none': {}, 'partial': {}}
    for func, (kind, _reason) in wanted.items():
        entry = best.get(func)
        if entry is None:
            state = 'never entered' if (args.hits and not hits.get(func)) else 'entered, no state replayed' if args.hits else 'no state'
        elif entry['FAIL']:
            state = 'DIFFERENT'
        elif entry['pass']:
            state = 'identical to the return (callees run)' if 'follow' in entry['modes'] else 'identical to the return (calls replaced)'
        elif entry['pass@stop']:
            state = 'identical up to a common stop'
        else:
            state = 'not comparable: ' + max(entry['why'].items(), key=lambda kv: kv[1])[0]
        classes[kind].setdefault(state, []).append(func)
    print('%d runs of recorded states read' % runs)
    for kind, title in (('none', 'functions without a comparable case in the sweep'),
                        ('partial', 'functions identical only up to a common stop in the sweep')):
        total = sum(len(v) for v in classes[kind].values())
        print('%s: %d' % (title, total))
        for state, funcs in sorted(classes[kind].items(), key=lambda kv: -len(kv[1])):
            print('  %4d  %s' % (len(funcs), state))
    if args.list:
        refs = references(list(wanted))
        for kind in ('none', 'partial'):
            for state, funcs in sorted(classes[kind].items()):
                if state.startswith('identical to the return'):
                    continue
                print('%s / %s:' % (kind, state))
                for func in sorted(funcs):
                    extra = ''
                    if func in best and best[func]['fail']:
                        extra = '  ' + best[func]['fail'][:200]
                    calls, jumps, data = refs[func]
                    print('  %08x %-34s calls %d, jumps %d, data words %d%s' % (func, names.get(func, ''), calls, jumps, data, extra))
        unreferenced = [f for f in wanted if not any(refs[f]) and f not in best]
        print('%d of the functions no state exists for are referenced by no call, jump or data word' % len(unreferenced))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('want')
    p.add_argument('--sweep', default=os.path.join(OUT, 'sweep-stub.txt'))
    p = sub.add_parser('replay')
    p.add_argument('dir')
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--steps', type=int, default=1000000)
    p.add_argument('--stub-steps', type=int, default=200000)
    p.add_argument('--all', action='store_true', help='every recorded state, not only the functions in want.txt')
    p.add_argument('--out', default='results.tsv', help='name of the result file inside DIR')
    p.add_argument('--only', help='hex addresses, comma separated')
    p = sub.add_parser('bounded')
    p.add_argument('dir')
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--events', default='16,256,4096', help='stop both sides after each of these counts of events')
    p.add_argument('--steps', type=int, default=3000000, help='the interpreter gives up after this many instructions')
    p.add_argument('--only', help='hex addresses, comma separated (default: the functions whose replayed states all ended at the step limit)')
    p = sub.add_parser('report')
    p.add_argument('dirs', nargs='*')
    p.add_argument('--hits', action='append')
    p.add_argument('--list', action='store_true')
    args = parser.parse_args()
    return {'want': want, 'replay': replay, 'report': report, 'bounded': bounded}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
