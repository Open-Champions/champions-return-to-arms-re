#!/usr/bin/env python3
"""Who writes the three stock lists after boot. Original functions run in tools/ee_emu.py.

Groups (seeds 20973 and 7 where a session runs):
  boot     the stock constructor alone on sentinel lists, checked record by record; the
           .bss clear's byte tail; the static-constructor walker's calls by kind
  census   every address in the lists that code forms from constants: lui followed by
           addiu/daddiu, ori, addu/daddu/or/subu into another register, and memory offsets,
           tracked through each function's branches and jump-table blocks; clear-class
           library calls and indexed stores whose formed base lies below the lists
  join     the panel-1 join's itemGrid_build call (shop rig of difftest_vendor_progress)
  paths    one machine per seed: main's static constructors, a session start with a store
           world (level load with its act change, warm-up, stock generation), a level load
           (mainloop_loadRequestedWorld), a new game (game_resetState,
           player_initNewCharacter), a save build, save load and the saved level's load, the
           session exit and a new session's start; every store into the lists is recorded with its
           phase
Output is counts and addresses only. Pass the private executable.
"""
import argparse
import bisect
import collections
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != HERE] + [HERE]
import unittest  # noqa: E402,F401  tools/dis.py must not shadow stdlib dis.
from ee_emu import EE  # noqa: E402
from ps2elf import Elf  # noqa: E402
from difftest_items import EXPECTED_SHA256  # noqa: E402
import difftest_vendor_residue as V  # noqa: E402
import ref_vendor_stock as S  # noqa: E402

SEEDS = V.SEEDS
LO, HI = V.LISTS
WINDOW = 0x100000                       # how far below the lists a base is followed
FUNCTIONS = {0x1C5F78, 0x1C7AF8, 0x1C8A00, 0x1CBBE8, 0x1CC7E0, 0x1D10B0, 0x1D13C8}
LUI_FUNCTIONS = 235                     # functions holding lui 0x86 or lui 0x87
CLEARS = {0x3B60C0: 'memset', 0x3B5F0C: 'memcpy', 0x3B5FBC: 'memmove', 0x3B36A0: 'bzero',
          0x3B35B0: 'bcopy', 0x3B868C: 'strcpy', 0x3B9390: 'strncpy', 0x3B8278: 'strcat'}
BSS_TAIL = 0x14FC00                     # byte store after the 16-byte loop
SBSS, BSS_END = 0x564300, 0x90A434      # .sbss start and .bss end in the section headers
CTOR_CALL = 0x3AD2E4                    # the walker helper's call of each .ctors entry
JOIN = 0x1C7734
TEMPS = frozenset(list(range(1, 16)) + [24, 25, 31])
CAP = 8

# Session rig. Stubs (each named): the debug stack check (the emulator's stack is not the
# game's thread stack), the GS path sync (a COP2 instruction the emulator lacks) and the
# DMA idle wait, and 0x18b270, which game_loadLevel (0x1e5070) runs on the previous level's
# scenery block (no level file was read, so that block is stale heap), and
# eqcache_loadHeader, which relocates a header file the emulator never read, and the
# resource request 0x173558 (answered 0, as difftest_vendor_residue does); libc strcmp is replaced by the same compare in Python (it reads and never
# stores, so no list store can hide in it). Kernel calls are answered 0, PollSema (0x45) -1
# and ReferThreadStatus (0x30) 0x10, so the loading-screen thread (not run) reads as
# stopped; hardware registers read 0 and drop writes. No file data is delivered.
STUBS = {0x19D9F8: 'dbg_checkStack', 0x34FE78: 'sceGsSyncPath', 0x350190: 'libdma_waitIdle',
         0x18B270: 'level-data scenery reset', 0x1A2680: 'eqcache_loadHeader',
         V.RESOURCE: 'resource request'}
STRCMP = 0x3B8534
SESSION, LOOP_HEAD, FRAME, SEEDED, NEW_LOAD = 0x322998, 0x322B3C, 0x3231D8, 0x322A08, 0x322E30
LOAD_WORLD = 0x320EDC                   # mainloop_loadRequestedWorld
PENDING, EXIT_CODE, NUM_PLAYERS = 0x41B6D0, 0x41B508, 0x4D8AE0
RESET, INIT_CHARACTER, SAVE_BUILD, SAVE_LOAD = 0x1E6F58, 0x1B1D70, 0x221914, 0x221D60
STOCK_FN = V.STOCK_FN
GENERATION = {0x1046E0, 0x104CA4, 0x1069B8, 0x1C7AF8}    # writers inside the stock call
MARKS = {0x321148: 'game_loadLevel', 0x1E56BC: 'item_loadResources', 0x1E59B4: 'cosmetic seed copy',
         0x1E5FEC: 'objects_levelReset', 0x320FCC: 'act change: save_clearBuffer',
         0x32101C: 'act change: vars_clearAll', 0x321024: 'playerSel_applyPending',
         0x322E6C: 'script_runDeferred', 0x322EB0: 'warm-up frame', 0x3234E0: 'session exit'}


def words_of(elf):
    text, off, size = elf.text
    return text, struct.unpack_from('<%dI' % (size // 4), elf.d, off)


# ---- boot -------------------------------------------------------------------------------
def boot_cases(path):
    pattern = V.constructed()
    want = set(range(0x10, 0x22)) | {0x24 + 8 * code + k for code in range(4) for k in range(2)}
    e = EE(path)
    e.mem.auto_map = True
    e.mem.write(LO, b'\xa5' * (HI - LO))
    e.call(V.STOCK_CTOR, max_steps=5000000)
    for category in range(3):
        base = LO + category * S.LIST_STRIDE
        for n in range(64):
            raw = e.mem.read(base + n * S.ITEM_SIZE, S.ITEM_SIZE)
            assert all(raw[k] == pattern[k] for k in want), (category, n)
            assert all(raw[k] == 0xA5 for k in range(S.ITEM_SIZE) if k not in want), (category, n)
        assert e.mem.read(base + 0x1200, 8) == b'\xa5' * 8
    cases = 1
    print('PASS boot stock constructor on sentinel lists: in each of the 192 records the written bytes '
          '(+0x10..+0x21 and the four codes) hold the constructed values (+0x10..+0x1f 0, +0x20/+0x21 0xff, '
          'codes -1) and every other byte keeps the sentinel; counts keep it', flush=True)
    # The entry's clear: 16-byte stores to 0x90a430, then bytes to the .bss end.
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()
    e.syscall_handler = lambda emu: emu.r.__setitem__(2, 0)
    e.hook(V.MAIN, lambda emu: (_ for _ in ()).throw(V.Reached()))
    try:
        e.call(V.ENTRY, max_steps=5000000)
    except V.Reached:
        pass
    wide = sorted(a for pc, a, _s, _v in e.writes if pc == V.BSS_STORE)
    tail = sorted(a for pc, a, s, _v in e.writes if pc == BSS_TAIL and s == 1)
    elf = Elf(path)
    assert elf.sections['.sbss'][0] == SBSS
    bss = elf.sections['.bss']
    assert bss[0] + bss[2] == BSS_END
    assert wide[0] == SBSS and wide[-1] + 16 == V.BSS[1] and tail == list(range(V.BSS[1], BSS_END)), (
        hex(wide[-1]), [hex(a) for a in tail])
    cases += 1
    print('PASS boot .bss clear 0x%x..0x%x: 16-byte stores at 0x%x to 0x%x, then %d byte stores at 0x%x to '
          'the .bss end 0x%x (section headers: .sbss 0x%x, .bss end 0x%x)' % (
              SBSS, BSS_END, V.BSS_STORE, V.BSS[1], len(tail), BSS_TAIL, BSS_END, SBSS, BSS_END), flush=True)
    # The walker: how many .ctors entries it calls, and how many calls there are in all.
    e = EE(path)
    e.mem.auto_map = True
    e.follow = {V.STOCK_CTOR, V.ITEM_ARRAY_CTOR}
    e.mem.write(LO, bytes(HI - LO))
    e.call(V.WALKER, max_steps=20000000)
    entries = [c for c in e.calls if c.site == CTOR_CALL]
    stock = [c for c in entries if c.target == V.STOCK_CTOR]
    nested = [c for c in e.calls if c.target == V.ITEM_ARRAY_CTOR]
    assert len(stock) == 1 and len(nested) == 1 and nested[0].site == 0x1D1994
    assert len({c.target for c in entries}) == len(entries)
    cases += 1
    print('PASS boot walker 0x%x: %d calls in all; %d are .ctors entries called at 0x%x, each once, one of '
          'them the stock constructor 0x%x (counted once); it calls 0x%x at 0x1d1994' % (
              V.WALKER, len(e.calls), len(entries), CTOR_CALL, V.STOCK_CTOR, V.ITEM_ARRAY_CTOR), flush=True)
    return cases


# ---- census ------------------------------------------------------------------------------
def _written(w):
    op, rs, rt, rd, fn = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0x3F
    if op == 0:
        return (() if fn in (0x08, 0x0C, 0x0D, 0x0F, 0x11, 0x13, 0x1A, 0x1B) else (rd,)), False
    if op == 1:
        return ((31,) if rt & 0x10 else ()), False
    if op == 3:
        return (31,), True
    if op in (2, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17):
        return (), False
    if 8 <= op <= 0xF or op in (0x18, 0x19, 0x1A, 0x1B, 0x1E) or 0x20 <= op <= 0x27 or op == 0x37:
        return (rt,), False
    if op == 0x1C:
        return (rd,), False
    if op in (0x10, 0x11, 0x12):
        return ((rt,) if rs in (0, 1, 2) else ()), False
    return (), False


def _branch(w, pc):
    """(targets, ends, likely) for a transfer, else (None, False, False)."""
    op, rs, rt, fn = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0x3F
    simm = (w & 0xFFFF) - 0x10000 if w & 0x8000 else w & 0xFFFF
    rel = (pc + 4 + (simm << 2)) & 0xFFFFFFFF
    if op == 4 and rs == 0 and rt == 0:
        return [rel], True, False
    if op == 1 and rs == 0 and rt in (1, 0x11):
        return [rel], rt == 1, False
    if op in (4, 5, 6, 7):
        return [rel], False, False
    if op in (0x14, 0x15, 0x16, 0x17):
        return [rel], False, True
    if op == 1 and rt in (0, 1, 0x10, 0x11):
        return [rel], False, False
    if op == 1 and rt in (2, 3, 0x12, 0x13):
        return [rel], False, True
    if op == 0x11 and rs == 8:
        return [rel], False, bool(rt & 2)
    if op == 2:
        return [((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)], True, False
    if op == 0 and fn == 0x08:
        return [], True, False
    return None, False, False


def _step(st, w, pc, function, out):
    """Abstract execution of one instruction: register -> {(value, indexed)}."""
    op, rs, rt, rd, funct = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0x3F
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    memory = 0x1A <= op < 0x40 and op not in (0x1C, 0x1D)
    store = op in (0x1F, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x39, 0x3D, 0x3E, 0x3F)
    if rs in st and (op in (0x09, 0x19, 0x0D) or memory):
        kind = 'mem' if memory else ('ori' if op == 0x0D else 'addiu')
        for value, indexed in st[rs]:
            address = (value | imm) if op == 0x0D and not indexed else (value + simm) & 0xFFFFFFFF
            if LO <= address < HI:
                out['hits'].setdefault(pc, set()).add((function, kind, indexed))
            elif LO - WINDOW <= address < LO and indexed and store:
                out['below'].setdefault(function, set()).add(address)
            if LO - 0x2000 <= address < LO and not indexed:
                out['near'].add((address, function))
    if op == 3:
        dest = (pc & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        if dest in CLEARS:
            out['clears'].setdefault(pc, [function, CLEARS[dest], set(), set()])
            out['clears'][pc][2] |= st.get(4, set())
            out['clears'][pc][3] |= st.get(6, set())
    new = None
    if op == 0x0F:
        new = {(imm << 16, False)}
    elif op in (0x09, 0x19) and rs == 0:
        new = {(simm & 0xFFFFFFFF, False)}
    elif op == 0x0D and rs == 0:
        new = {(imm, False)}
    elif op in (0x09, 0x19) and rs in st:
        if out['widen'] and rt == rs:
            new = {(value, True) for value, _i in st[rs]}
        else:
            new = {((value + simm) & 0xFFFFFFFF, indexed) for value, indexed in st[rs]}
    elif op == 0x0D and rs in st:
        new = {((value | imm) if not indexed else value, indexed) for value, indexed in st[rs]}
    elif op == 0 and funct in (0x20, 0x21, 0x2C, 0x2D, 0x25, 0x22, 0x23, 0x2E, 0x2F):
        if rt == 0 and rs in st and funct not in (0x22, 0x2E):
            new = set(st[rs])
        elif rs == 0 and rt in st and funct in (0x20, 0x21, 0x2C, 0x2D, 0x25):
            new = set(st[rt])
        else:
            sources = (rs, rt) if funct not in (0x22, 0x23, 0x2E, 0x2F) else (rs,)
            new = {(value, True) for src in sources if src in st for value, _i in st[src]} or None
    regs, call = _written(w)
    for reg in regs:
        st.pop(reg, None)
    if call:
        for reg in TEMPS:
            st.pop(reg, None)
    if new and regs and regs[0]:
        if len(new) > CAP:
            out['capped'] += 1
            new = {(value, True) for value, _i in sorted(new)[:CAP]}
        st[regs[0]] = new
    return st


def extended_census(elf):
    """Flow-sensitive constant tracking per function (V.function_starts bounds). Blocks
    that no branch reaches (jump-table targets) start with nothing known."""
    text, words = words_of(elf)
    starts = V.function_starts(elf, words)
    bounds = starts + [text + len(words) * 4]
    out = {'hits': {}, 'below': {}, 'near': set(), 'clears': {}, 'capped': 0, 'lui': set(),
           'widen': False, 'seeded': 0}
    for index, begin in enumerate(starts):
        end = bounds[index + 1]
        word = lambda pc: words[(pc - text) // 4]
        leaders = {begin}
        for pc in range(begin, end, 4):
            w = word(pc)
            if w >> 26 == 0x0F and (w & 0xFFFF) in (0x86, 0x87):
                out['lui'].add(begin)
            targets, _ends, _likely = _branch(w, pc)
            if targets is not None:
                leaders.update(t for t in targets if begin <= t < end)
                if pc + 8 < end:
                    leaders.add(pc + 8)
        order = sorted(leaders)
        following = dict(zip(order, order[1:] + [end]))
        state_in, visits, work = {begin: {}}, {}, [begin]
        pending = order[::-1]

        def put(dest, st):
            if not begin <= dest < end:
                return
            current = state_in.get(dest)
            if current is None:
                state_in[dest] = {r: set(v) for r, v in st.items()}
                work.append(dest)
                return
            grew = False
            for reg in set(current) | set(st):
                union = current.get(reg, set()) | st.get(reg, set())
                if union != current.get(reg, set()):
                    current[reg] = union
                    grew = True
            if grew:
                work.append(dest)
        while work or pending:
            if not work:
                block = pending.pop()
                if block in state_in:
                    continue
                state_in[block] = {}
                out['seeded'] += 1
                work.append(block)
            block = work.pop()
            visits[block] = visits.get(block, 0) + 1
            out['widen'] = visits[block] > 4
            st = {r: set(v) for r, v in state_in[block].items()}
            pc = block
            while pc < following[block]:
                w = word(pc)
                targets, ends, likely = _branch(w, pc)
                if targets is not None and pc + 4 < end:
                    before = {r: set(v) for r, v in st.items()}
                    st = _step(st, word(pc + 4), pc + 4, begin, out)
                    for target in targets:
                        put(target, st)
                    if not ends:
                        put(pc + 8, before if likely else st)
                    break
                st = _step(st, w, pc, begin, out)
                pc += 4
            else:
                put(following[block], st)
    return out, starts


def census_cases(path):
    elf = Elf(path)
    out, starts = extended_census(elf)
    functions = {f for s in out['hits'].values() for f, _k, _i in s}
    linear = V.list_census(elf)
    assert set(linear) <= set(out['hits']), sorted(hex(p) for p in set(linear) - set(out['hits']))
    assert set(V.CENSUS) <= set(out['hits'])
    assert functions == FUNCTIONS, sorted(hex(f) for f in functions)
    assert len(out['lui']) == LUI_FUNCTIONS, len(out['lui'])
    assert functions <= out['lui']
    kinds = collections.Counter((k, i) for s in out['hits'].values() for _f, k, i in s)
    cases = 4
    print('PASS census extended: %d functions hold lui 0x86/0x87 (the only lui values whose 16-bit '
          'window reaches the lists) and all were walked block by block (%d blocks reached only by '
          'jump tables walked with nothing known); %d instructions form a list address (direct %d, '
          'through an indexing add %d; ori %d), all in the same seven functions %s; every site of the '
          'linear census is among them' % (
              len(out['lui']), out['seeded'], len(out['hits']),
              sum(v for (k, i), v in kinds.items() if not i), sum(v for (k, i), v in kinds.items() if i),
              sum(v for (k, i), v in kinds.items() if k == 'ori'),
              ','.join('0x%x' % f for f in sorted(functions))), flush=True)
    # Clear-class library calls whose destination is formed from constants near the lists.
    exact, indexed, runtime = [], [], 0
    for pc, (function, name, a0, a2) in sorted(out['clears'].items()):
        if not a0:
            runtime += 1
            continue
        for value, is_indexed in a0:
            if not LO - WINDOW <= value < HI:
                continue
            assert not LO <= value < HI, 'a clear starts inside the lists at 0x%x' % pc
            lengths = {v for v, i in a2 if not i}
            sized = name in ('memset', 'memcpy', 'memmove', 'bzero') and len(lengths) == 1 and len(a2) == 1
            (indexed if is_indexed else exact).append((pc, function, name, value, lengths.pop() if sized else None))
    for pc, function, name, value, length in exact:
        if length is not None:
            assert value + length <= LO, (hex(pc), hex(value), hex(length))
    unsized = sorted({pc for pc, _f, _name, _value, length in exact + indexed if length is None})
    cases += 1
    print('PASS census clear-class calls (%s): %d sites; %d with a destination formed from constants within '
          '0x%x below the lists (%d with a plain base, %d with an array-element base), none starting inside them; every plain one '
          'with a constant length ends below 0x%x; %d have a run-time length or are string copies (%s); %d '
          'take their destination at run time' % (
              ','.join(sorted(set(CLEARS.values()))), len(out['clears']), len({x[0] for x in exact + indexed}),
              WINDOW, len({x[0] for x in exact}), len({x[0] for x in indexed}), LO, len(unsized),
              ','.join('0x%x' % pc for pc in unsized), runtime), flush=True)
    near = sorted(out['near'])
    cases += 1
    print('PASS census below the lists: highest constant-formed address 0x%x (in 0x%x); %d functions store '
          'through an indexed base formed within 0x%x below the lists (bounds not followed); %d constant sets '
          'capped' % (near[-1][0], near[-1][1], len(out['below']), WINDOW, out['capped']), flush=True)
    return cases


# ---- join --------------------------------------------------------------------------------
def join_cases(path):
    import difftest_vendor_progress as P
    cases = 0
    for seed in SEEDS:
        shop = P.Shop(path, seed, players=2)
        calls = shop.tick(press=shop.confirm, slot=1)
        grids = [(c.site, tuple(x & 0xFFFFFFFF for x in c.args[:3])) for c in calls if c.target == P.GRID]
        assert grids == [(JOIN, (1, 1, 1))], [(hex(s), a) for s, a in grids]
        assert shop.panel(1)[0] == S.MENU_CHOICE
        cases += 1
    print('PASS join: the panel-1 join tick calls itemGrid_build 0x%x once, at 0x%x with (1, 1, 1) '
          '(slot 1, panel 1, stock), seeds %s' % (P.GRID, JOIN, ','.join(map(str, SEEDS))), flush=True)
    return cases


# ---- paths -------------------------------------------------------------------------------
class Session:
    def __init__(self, path, seed, starts):
        e = self.e = EE(path)
        e.mem.auto_map = True
        e.record_writes = False
        e.record_calls = True
        self.starts = starts
        self.phase = 'start'
        self.hits = []
        self.kernel = collections.Counter()
        self.marks = collections.Counter()
        self.stubbed = collections.Counter()
        self.seed = seed
        e.mem.write(LO, bytes(HI - LO))         # what the entry's .bss clear leaves
        store, load = e._store, e._load

        def hardware(address):
            return address >= 0x10000000 and 0x10000000 <= (address & 0x1FFFFFFF) < 0x14000000

        def recorded(address, size, value):
            if hardware(address):
                return
            if address < HI and address + size > LO:
                self.hits.append((e.cur, address, size, self.phase))
            store(address, size, value)

        def quiet(address, size):
            return 0 if hardware(address) else load(address, size)
        e._store, e._load = recorded, quiet

        def kernel(emu):
            number = emu.r[3] & 0xFFFFFFFF
            number = abs(number - (1 << 32) if number & 0x80000000 else number)
            self.kernel[number] += 1
            emu.r[2] = ((1 << 64) - 1) if number == 0x45 else (0x10 if number == 0x30 else 0)
        e.syscall_handler = kernel
        for address, name in STUBS.items():
            e.stub(address, name=name, function=(lambda n: lambda emu: self.stubbed.update([n]) and None)(name))
        def strcmp(emu):
            self.stubbed['strcmp'] += 1
            a, b = emu.r[4] & 0xFFFFFFFF, emu.r[5] & 0xFFFFFFFF
            while True:
                x, y = emu.mem.u8(a), emu.mem.u8(b)
                if x != y or not x:
                    return (x - y) & 0xFFFFFFFFFFFFFFFF
                a, b = a + 1, b + 1
        e.stub(STRCMP, function=strcmp, name='strcmp')
        for address, name in MARKS.items():
            e.hook(address, (lambda n: lambda emu: self.marks.update([n]))(name))
        e.hook(SEEDED, self.seeded)
        e.hook(STOCK_FN, self.stock_entry)
        e.hook(0x3230CC, lambda emu: setattr(self, 'phase', 'after the stock call'))
        self.stock_calls = []
        self.name = e.alloc(0x10)
        e.mem.write(self.name, b'test\0')

    def seeded(self, emu):
        """The session start has just loaded both seeds from the cycle counter."""
        emu.mem.w32(S.SHARED, self.seed)
        emu.mem.w32(S.COSMETIC, self.seed)

    def stock_entry(self, emu):
        self.stock_calls.append((emu.r[31] - 8) & 0xFFFFFFFF)
        self.at_stock = emu.mem.read(LO, HI - LO)
        self.phase = 'stock generation'

    def lists(self):
        return self.e.mem.read(LO, HI - LO)

    def function(self, pc):
        return self.starts[bisect.bisect_right(self.starts, pc) - 1]

    def run(self, phase, start, until=(FRAME,), steps=900000000):
        self.phase = phase
        e = self.e
        e.reset_log()
        reason = e.run(start, until=until, max_steps=steps)
        reached = {c.target for c in e.calls}
        e.reset_log()
        return reason, len(reached)

    def call(self, phase, address, *args):
        self.phase = phase
        e = self.e
        e.reset_log()
        e.call(address, *args, max_steps=50000000)
        reached = {c.target for c in e.calls}
        e.reset_log()
        return len(reached)


def paths_cases(path):
    elf = Elf(path)
    _text, words = words_of(elf)
    starts = V.function_starts(elf, words)
    cases = 0
    for seed in SEEDS:
        s = Session(path, seed, starts)
        e, m = s.e, s.e.mem
        reached = collections.OrderedDict()
        # Boot: main's static-constructor walker with every callee live (sets the vtables the
        # later paths use); in the lists only the stock constructor writes.
        reached['boot constructors'] = s.call('boot', V.WALKER)
        assert {s.function(h[0]) for h in s.hits} == {V.ITEM_ARRAY_CTOR}
        booted = s.lists()
        del s.hits[:]
        # Session start with the store world pending (first level, so an act change): level
        # load, warm-up frames, stock generation at 0x3230c4, up to the first frame.
        m.write(PENDING, b'hub\0')
        e.r[31] = EE.RETURN_ADDR
        reason, reached['session start + hub load + stock'] = s.run('session start', SESSION)
        assert reason == 'stop' and s.stock_calls == [0x3230C4], (reason, [hex(x) for x in s.stock_calls])
        assert s.at_stock == booted, 'a list byte changed before the stock call'
        before = [h for h in s.hits if h[3] != 'stock generation']
        assert not before, sorted({hex(h[0]) for h in before})
        writers = {s.function(h[0]) for h in s.hits}
        assert writers == GENERATION, sorted(hex(f) for f in writers)
        for mark in ('game_loadLevel', 'item_loadResources', 'cosmetic seed copy', 'objects_levelReset',
                     'act change: save_clearBuffer', 'act change: vars_clearAll', 'playerSel_applyPending',
                     'script_runDeferred', 'warm-up frame'):
            assert s.marks[mark], mark
        counts = tuple(m.u32(LO + c * S.LIST_STRIDE + 0x1200) for c in range(3))
        assert all(0 < n <= 64 for n in counts), counts
        generated, gen_writes = s.lists(), len(s.hits)
        del s.hits[:]

        def unchanged(what):
            assert s.lists() == generated and not s.hits, '%s wrote the lists: %s' % (
                what, sorted({hex(h[0]) for h in s.hits}))
        # A level load (a level other than the four store worlds), as step E calls it.
        m.write(PENDING, b'blood1\0')
        s.marks.clear()
        reached['level load'] = s.call('level load', LOAD_WORLD)
        assert s.marks['game_loadLevel'] == 1 and len(s.stock_calls) == 1
        unchanged('the level load')
        # New game, as frontend_run does: reset, then a new character for slot 0.
        reached['new game'] = (s.call('new game', RESET)
                               + s.call('new game', INIT_CHARACTER, 0, 0, s.name, 0, 0, 0, 0))
        unchanged('the new game')
        # The new game's first level (game_resetState emptied the level name), with the
        # living character, then a save, its load, and the load of the level it names.
        m.write(PENDING, b'blood1\0')
        s.marks.clear()
        reached['level load with a character'] = s.call('level load with a character', LOAD_WORLD)
        assert s.marks['game_loadLevel'] == 1 and len(s.stock_calls) == 1
        unchanged('the level load with a character')
        reached['save build + save load'] = s.call('save', SAVE_BUILD, 0, 0) + s.call('save load', SAVE_LOAD)
        assert m.cstr(PENDING) == 'blood1' and m.u8(0x41B720) == 0xFD, 'save_load named no level'
        s.marks.clear()
        reached['saved level load'] = s.call('saved level load', LOAD_WORLD)
        assert s.marks['game_loadLevel'] == 1 and len(s.stock_calls) == 1
        unchanged('the save or its load')
        # Leave the session (its loop head, exit code set) and start a new one up to its
        # level-load call. (Its level load is not run: the exit unloaded the resident lumps,
        # and reloading them reads files the emulator does not deliver.)
        m.w32(EXIT_CODE, 1)
        s.marks.clear()
        reason, reached['session exit'] = s.run('session exit', LOOP_HEAD, until=())
        assert reason == 'return' and s.marks['session exit'] == 1
        unchanged('the session exit')
        m.write(PENDING, b'blood1\0')
        e.r[31] = EE.RETURN_ADDR
        s.marks.clear()
        reason, reached['new session start'] = s.run('new session', SESSION, until=(NEW_LOAD,))
        assert reason == 'stop' and len(s.stock_calls) == 1
        unchanged('the new session')
        cases += 1
        print('PASS paths seed=%d: boot constructors (lists written only by 0x%x), session start with hub '
              '(act change, game_loadLevel, warm-up, stock at 0x3230c4: %d list stores, all inside the stock '
              'call, by %s; counts %s), level load, new game, level load with the character, save build + '
              'save load + saved level load, '
              'session exit, new session start: no other list store, list bytes unchanged after the '
              'stock call; functions reached %s; stubs called %s; kernel calls %s' % (
                  seed, V.ITEM_ARRAY_CTOR, gen_writes, ','.join('0x%x' % f for f in sorted(writers)),
                  ','.join(map(str, counts)), ','.join('%s %d' % kv for kv in reached.items()),
                  ','.join('%s %d' % kv for kv in sorted(s.stubbed.items())),
                  ','.join('0x%x' % k for k in sorted(s.kernel))), flush=True)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--only', choices=('boot', 'census', 'join', 'paths'))
    args = parser.parse_args()
    assert V.sha(args.elf) == EXPECTED_SHA256, 'executable digest'
    groups = (('boot', boot_cases), ('census', census_cases), ('join', join_cases), ('paths', paths_cases))
    total = 0
    for name, run in groups:
        if args.only and name != args.only:
            continue
        count = run(args.elf)
        total += count
        print('PASS %s cases=%d' % (name, count), flush=True)
    print('PASS total=%d mismatches=0' % total)


if __name__ == '__main__':
    main()
