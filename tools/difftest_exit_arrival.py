#!/usr/bin/env python3
"""Counts-only EE comparisons for arriving in a level (round five).

python3 -m tools.difftest_exit_arrival --seed 20973 [--disc local/rta-disc]

The disc argument is a read-only copy of the disc's files (BG/DATA inside).
Original code runs in tools/ee_emu.py: the ISO directory parser, the CD
read layer, gob_loadAll, lump_fixup and world_fixup, Player1_ctor,
world_findFreeSpot with the original terrain and box queries,
save_writeLevelState and its section writers, and
level_loadScriptAndObjects with the original script machine.

Supplied, and listed in every PASS line's stub count: sceCdRead 0x362600
(served from the disc copy at synthetic sector numbers), 0x3618b0 and
0x362938 (return 0: done, no error), gfx_waitVsync 0x19d028, FlushCache
0x352c60, world_loadRecords 0x14e808 (records its arguments), and the level
script's built-in handlers (record their argument cells; return a seeded
sequence). callScript 0x143158 is not supplied. Deci2 function 0x10 uses
EE.install_deci2_kputs from t3/research-death-reload.
"""
import argparse
from collections import Counter
import hashlib
import os
from pathlib import Path
import random
import struct
import sys
import unittest  # Preload before tools/dis.py can shadow the standard library.

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE, M32, float_to_raw
import ref_amx
import ref_exit_arrival as R
import ref_world as W

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
LEVELS = ('strife', 'hub', 'honor', 'storm1a')

TOC, TOC_COUNT = 0x7BA8A0, 0x7BA8A0 + 0x7D00
LOAD_DIR, HEAP_INIT, GOB_LOAD = 0x1721E4, 0x150598, 0x1737D8
FIND_LOADED, FIND_ENTRY, FIND_EXT = 0x17306C, 0x171DE4, 0x171FD8
CD_READ, CD_SYNC, CD_ERROR, VSYNC, FLUSH = 0x362600, 0x3618B0, 0x362938, 0x19D028, 0x352C60
LUMPS, LUMP_COUNT, LUMP_ROW = 0x7B9480, 0x41BF7C, 40
LEVEL, TEXNAME, SUB, PREV = 0x41B721, 0x44FE18, 0x41B771, 0x41B7C2
ENTRANCE, LEG, WORLD, SEED = 0x4F8468, 0x41B51E, 0x44FDC8, 0x404464
RANK, SPAWN, FACING = 0x4F7108, 0x4F70D0, 0x4F8410
GRID_A, GRID_B, OFF_GRID, GRID_BYTES = 0x5DB4F0, 0x5E95F0, 0x5F76F0, 120 * 120 * 4
PLAYER1, GAMEOBJECT, FREE_SPOT = 0x158928, 0x14CB10, 0x14ACF8
WRITE, AUTOMAP, DECALS, SPACE_WORD = 0x218600, 0x4044F0, 0x846458, 0x4044D0
OBJ_SIZE_WORD, STR_START, STR_END = 0x88D3E8, 0x5F86FC, 0x5F8700
ARRIVE, DIRECTORY, DATA, RESTORE = 0x217978, 0x8AB590, 0x8AB698, 0x88D480
SCRIPT_GATE, FROM_SAVE, MACHINE = 0x4F8B58, 0x8E1AD6, 0x86B270
LOAD_RECORDS, DECAL_LOAD, AUTOMAP_UNPACK = 0x14E808, 0x1A00B0, 0x1686C4
SET_SCRIPT, RUN_SCRIPT, CALL_NATIVE, CALL_SCRIPT = 0x1ED650, 0x1ED694, 0x141050, 0x143158
BUILTINS, QUALIFIED = 0x403370, 0x1EC0F0
HEAP, HEAP_SIZE = 0x1A00000, 0x480000
HANDLE_INIT = 0x1A17D0             # engine_init calls it at 0x19d710
FILTER, FILTER_LIST, REGISTER_FACTORY, SAVE_FILTER = 0x403A0C, 0x403A68, 0x15DA54, 0x15D9C8
VTABLES = {'GameObject': 0x5122A8, 'Counter': 0x50D888, 'Lever': 0x50D918,
           'JumpGate': 0x50DBE8, 'Savepoint': 0x50DC78}
SENTINEL = 0xA5                     # destination bytes before the write
STACK_FILL = 0x5A                   # stack bytes before the write
SUPPLIED = (CD_READ, CD_SYNC, CD_ERROR, VSYNC, FLUSH)


def f(value):
    return float_to_raw(value)


class Disc:
    """The disc copy at synthetic sector numbers (ref_exit_arrival.iso_layout)."""

    def __init__(self, root):
        self.data = os.path.join(root, 'BG', 'DATA')
        listing = [(n, os.path.getsize(os.path.join(self.data, n)))
                   for n in os.listdir(self.data)]
        self.sectors, self.files, self.toc = R.iso_layout(listing)
        self.spans = sorted((lsn, size, name) for lsn, size, name in self.files.values())

    def read(self, lsn, count):
        if R.DIR_LSN <= lsn < R.DIR_LSN + len(self.sectors):
            return b''.join(self.sectors[lsn - R.DIR_LSN:lsn - R.DIR_LSN + count])
        for start, size, name in self.spans:
            if start <= lsn < start + (size + R.SECTOR - 1) // R.SECTOR:
                with open(os.path.join(self.data, name), 'rb') as handle:
                    handle.seek((lsn - start) * R.SECTOR)
                    return handle.read(count * R.SECTOR).ljust(count * R.SECTOR, b'\0')
        raise AssertionError('sector outside every file')

    def file(self, name):
        with open(os.path.join(self.data, name), 'rb') as handle:
            return handle.read()

    def lsn(self, name):
        return self.files[name.upper() + ';1'][0]


class Probe:
    def __init__(self, elf, disc):
        self.elf, self.disc = elf, disc
        self.counts = Counter()
        self.stubs = set()

    def equal(self, got, want):
        assert got == want, 'comparison mismatch_count=1'
        self.counts['assertions'] += 1

    def machine(self):
        ee = EE(self.elf)
        ee.install_deci2_kputs()
        self.reads = []

        def cd_read(e):
            lsn, count, buf = e.r[4] & M32, e.r[5] & M32, e.r[6] & M32
            self.reads.append((lsn, count))
            e.mem.write(buf, self.disc.read(lsn, count))
            return 1
        ee.stub(CD_READ, function=cd_read)
        for addr in (CD_SYNC, CD_ERROR, VSYNC, FLUSH):
            ee.stub(addr, ret=0)
        ee.mem.map(HEAP, HEAP_SIZE)
        self.stubs.update(SUPPLIED)
        return ee

    def call(self, ee, address, *args, steps=400000000):
        result = ee.call(address, *args, max_steps=steps)
        self.equal((len(ee.patches), ee.mem.auto_map, len(ee.mem.auto_mapped)), (0, False, 0))
        self.counts['entry_calls'] += 1
        return result

    def text(self, ee, value):
        addr = ee.alloc(len(value) + 1)
        ee.mem.write(addr, value.encode('latin1') + b'\0')
        return addr

    def stubbed_targets(self, ee):
        return {c.target for c in ee.calls if getattr(c, 'stubbed', False)}


# ---------------------------------------------------------------------------
# 1. Disc load
# ---------------------------------------------------------------------------

def load_level(p, level):
    """Fresh machine, original TOC parse, heap, gob_loadAll. Returns (ee, lumps)."""
    ee = p.machine()
    p.call(ee, LOAD_DIR, TOC, R.DIR_LSN, len(p.disc.sectors))
    toc = [(ee.mem.read(TOC + 32 * k, 16).split(b'\0')[0] if k > 1 else
            ee.mem.read(TOC + 32 * k, 1),
            ee.mem.u32(TOC + 32 * k + 0x10), ee.mem.u32(TOC + 32 * k + 0x14))
           for k in range(ee.mem.u32(TOC_COUNT))]
    p.equal(toc, p.disc.toc)
    p.equal(p.reads, [(R.DIR_LSN + k, 1) for k in range(len(p.disc.sectors))])
    p.counts['toc_entries'] += len(toc)
    p.call(ee, HEAP_INIT, HEAP, HEAP_SIZE)
    p.call(ee, HANDLE_INIT)
    for addr in (LEVEL, TEXNAME):          # what 0x320edc leaves for game_loadLevel
        ee.mem.write(addr, level.encode() + b'\0')
    gob_bytes = p.disc.file(level.upper() + '.GOB')
    entries, sequential = R.gob_plan(gob_bytes)
    p.equal(sequential, True)
    p.reads = []
    ee.reset_log()
    p.call(ee, GOB_LOAD, p.text(ee, level + '.gob'))
    lmp_bytes = {name: gob_bytes[off:off + size] for name, off, size in entries}
    world_lump = [i for i, (name, _o, _s) in enumerate(entries)
                  if R.first_by_extension(lmp_bytes[name], 'world')][0]
    p.equal(p.reads, R.gob_reads(entries, p.disc.lsn(level + '.GOB'),
                                 p.disc.lsn(level + '.TEX'), world_lump))
    p.counts['sector_reads'] += len(p.reads)
    vsyncs = [c for c in ee.calls if c.target == VSYNC]
    p.equal(len(vsyncs), len(p.reads))     # one frame wait per blocking read
    p.equal(p.stubbed_targets(ee) <= set(SUPPLIED), True)
    p.equal(ee.mem.u32(LUMP_COUNT), len(entries))
    names = [ee.mem.cstr(LUMPS + LUMP_ROW * k) for k in range(len(entries))]
    p.equal(names, R.lump_names(entries))
    lumps = {}
    for name in names:
        ptr = p.call(ee, FIND_LOADED, p.text(ee, name)) & M32
        p.equal(ptr, ee.mem.u32(LUMPS + LUMP_ROW * names.index(name) + 0x10))
        lumps[name] = ptr
        p.counts['lumps'] += 1
    lmp = lmp_bytes[level + '.lmp']
    ptr = lumps[level + '.lmp']
    for entry in ('script.scr', 'objects.ob'):
        rec = p.call(ee, FIND_ENTRY, ptr, p.text(ee, entry)) & M32
        want = R.lmp_entry(lmp, entry)
        p.equal(ee.mem.u32(rec + 8), len(want))
        p.equal(ee.mem.read(ee.mem.u32(rec + 4), len(want)), want)
        p.counts['entries_compared'] += 1
    rec = p.call(ee, FIND_EXT, ptr, p.text(ee, 'world'), 0) & M32
    p.equal(ee.mem.cstr(ee.mem.u32(rec)), R.first_by_extension(lmp, 'world'))
    ee.mem.w32(WORLD, ee.mem.u32(rec + 4))      # 0x1e59ac / 0x1e59bc
    p.counts['disc_levels'] += 1
    return ee, lmp, lumps


def missing(p, ee):
    """A name with no TOC row: cd_readAsync stores 2 through the null lookup
    result (0x172a5c-0x172a64) and returns before the busy flag is set."""
    m = ee.mem
    m.map(0, 0x10)
    m.w32(0, 0x11111111)
    p.reads = []
    buf = ee.alloc(0x800)
    ee.reset_log()
    p.call(ee, 0x172AD0, p.text(ee, 'SYN_MISSING.BIN'), buf, 0x800, 0)
    p.equal(m.u32(0), 2)
    p.equal(p.reads, [])
    p.equal(m.u8(0x41BF90), 0)
    p.equal([c.target for c in ee.calls if c.target in (0x172098, VSYNC)], [])
    p.counts['missing_cases'] += 1


# ---------------------------------------------------------------------------
# 2. Placement on arrival
# ---------------------------------------------------------------------------

def markers(lmp):
    ob = R.lmp_entry(lmp, 'objects.ob')
    return [(angle, pos, props) for _i, cls, angle, pos, props in R.objects(ob)
            if cls.lower() == 'player1']


def place_case(p, ee, level_ref, marks, rank, prev, entrance, leg, seed, blockers=()):
    m = ee.mem
    m.write(GRID_A, b'\0' * GRID_BYTES)
    m.w32(OFF_GRID, 0)
    m.write(SPAWN, b'\xee' * 48)
    m.write(FACING, b'\xee' * 8)
    m.w8(RANK, rank & 0xFF)
    m.write(PREV, prev.encode() + b'\0')
    m.write(ENTRANCE, entrance.encode() + b'\0')
    m.w8(LEG, leg)
    m.w32(SEED, seed)
    blocks = []
    for bx, by, bz, radius in blockers:
        obj = ee.alloc(0x180)
        pos = ee.alloc(16)
        for k, v in enumerate((bx, by, bz)):
            m.w32(pos + 4 * k, v)
        p.call(ee, GAMEOBJECT, obj, pos, 0, 0)
        seed = R.lcg(seed)                      # GameObject_ctor 0x14cd5c-0x14cd80
        p.equal(m.u32(obj + 0x44), seed >> 16)
        m.w32(obj + 0x1C, radius)
        p.equal(m.u32(obj + 0xC) & 1, 0)
        blocks.append((bx, by, radius))
    want_rank, taken = R.player_start([pr for _a, _p, pr in marks], rank, prev, entrance, leg)
    spawns = [tuple([0xEEEEEEEE] * 3)] * 4
    facings = [0xEEEE] * 4
    founds = []
    ee.reset_log()
    for index, (angle, pos, props) in enumerate(marks):
        obj = ee.alloc(0x180)
        posbuf = ee.alloc(16)
        for k, v in enumerate(pos):
            m.w32(posbuf + 4 * k, v)
        array = ee.alloc(4 * (len(props) + 1))
        for k, item in enumerate(props):
            m.w32(array + 4 * k, p.text(ee, item))
        p.call(ee, PLAYER1, obj, posbuf, angle - 0x10000 if angle & 0x8000 else angle, array)
        seed = R.lcg(seed)
        p.equal(m.u32(obj + 0x44), seed >> 16)
        if index in taken:
            for slot in range(4):
                out, found, seed = R.free_spot(level_ref, seed, pos, 0x24, 0x18, 0, blocks)
                facings[slot], seed = R.spawn_facing(angle, seed)
                spawns[slot] = out
                founds.append(found)
    calls = [c for c in ee.calls if c.target == FREE_SPOT]
    p.equal(len(calls), 4 * len(taken))
    p.equal({(c.args[2] & M32, c.args[3] & M32, c.args[4] & M32, c.args[5] & M32)
             for c in calls} <= {(0x24, 0x18, 0, 0)}, True)
    p.equal(m.s8(RANK), want_rank)
    p.equal([tuple(m.u32(SPAWN + 12 * s + 4 * k) for k in range(3)) for s in range(4)], spawns)
    p.equal([m.u16(FACING + 2 * s) for s in range(4)], facings)
    p.equal(m.u32(SEED), seed)
    p.equal(p.stubbed_targets(ee) <= set(SUPPLIED), True)
    p.counts['placement_cases'] += 1
    p.counts['free_spot_calls'] += len(calls)
    p.counts['free_spot_misses'] += founds.count(0)
    return seed, spawns if taken else None


def loader_scatter(p, ee, level_ref, spawns, seed):
    """0x3212e0: slots 1-3 again, radius 0x24, size 0xe, from the spawn slots."""
    m = ee.mem
    out = ee.alloc(16)
    inp = ee.alloc(16)
    for slot in range(1, 4):
        for k in range(3):
            m.w32(inp + 4 * k, spawns[slot][k])
        ee.reset_log()
        p.call(ee, FREE_SPOT, out, inp, 0x24, 0xE, 0, 0)
        want, _found, seed = R.free_spot(level_ref, seed, spawns[slot], 0x24, 0xE)
        p.equal(tuple(m.u32(out + 4 * k) for k in range(3)), want)
        p.equal(m.u32(SEED), seed)
        p.counts['free_spot_calls'] += 1


def placement(p, ee, lmp, level, rng):
    level_ref = W.Level(R.lmp_entry(lmp, R.first_by_extension(lmp, 'world')))
    W.set_fpu('ps2')
    ee.mem.w32(0x44F08C, 0)                 # g_terrainStamp, the model's start
    marks = markers(lmp)
    p.equal(len(marks) >= 1, True)
    first = marks[0]
    cases = [('fresh', 0, '', '', 0, marks, ())]
    for frm in sorted({R.prop(pr, 'from') for _a, _p, pr in marks} - {None}):
        cases.append(('from', 0, frm, '', 0, marks, ()))
    syn_gate = (0x2000, first[1], ['name=SYN_GATE'])
    cases.append(('entrance', 0, '', 'SYN_GATE', 0, marks + [syn_gate], ()))
    cases.append(('gate', 0, '', '', 1, marks + [(0x6000, first[1], ['from=gate'])], ()))
    cases.append(('saved', 3, '', '', 0, marks, ()))
    cases.append(('blocker', 0, '', '', 0, marks, ((first[1][0], first[1][1], first[1][2],
                                                    0x41C00000),)))
    if level == 'strife':
        cases.append(('wall', 0, '', '', 0, marks, ((first[1][0], first[1][1], first[1][2],
                                                     f(100.0)),)))
    for _label, rank, prev, entrance, leg, marks_, blockers in cases:
        seed = rng.getrandbits(32)
        seed, spawns = place_case(p, ee, level_ref, marks_, rank, prev, entrance, leg, seed,
                                  blockers)
        if spawns is not None and not blockers:
            loader_scatter(p, ee, level_ref, spawns, seed)


# ---------------------------------------------------------------------------
# 3. Level-state record bytes
# ---------------------------------------------------------------------------

TAILS = {
    'GameObject': lambda fld: b'',
    'Counter': lambda fld: struct.pack('<I', fld[0x4C]),
    'Lever': lambda fld: struct.pack('<II', fld[0x4C], fld[0xC]) + bytes([fld[0x50], fld[0x51]]),
    'JumpGate': lambda fld: bytes([fld[0x4D], fld[0x4E]]),
    'Savepoint': lambda fld: struct.pack('<I', fld[0x84] or fld[0x80]) + bytes([fld[0xC5],
                                                                            fld[0xC6]]),
}
WIDTH = {0xC: 4, 0x4C: 4, 0x4D: 1, 0x4E: 1, 0x50: 1, 0x51: 1, 0x80: 4, 0x84: 4, 0xC5: 1,
         0xC6: 1}


def filter_names(ee):
    out, at = [], FILTER_LIST
    while ee.mem.u32(at):
        out.append(ee.mem.cstr(ee.mem.u32(at)))
        at += 4
    return out


def build_world(p, ee, rng, specs, filtered=()):
    """Objects in grid A, grid B and the off-grid list, linked by hand.

    specs: (list name, cell, name text, class, flags, props, angle, pos, fields).
    Returns the records the writer should produce, in walk order."""
    m = ee.mem
    m.write(GRID_A, b'\0' * GRID_BYTES)
    m.write(GRID_B, b'\0' * GRID_BYTES)
    m.w32(OFF_GRID, 0)
    heads = {}
    p.nodes = []
    for where, cell, name, cls, flags, props, angle, pos, fld in specs:
        obj = ee.alloc(0x100)
        m.w32(obj + 0xC, flags)
        for k, v in enumerate(pos):
            m.w32(obj + 0x10 + 4 * k, v)
        m.w16(obj + 0x38, angle)
        m.w32(obj + 0x48, VTABLES[cls])
        m.w32(obj + 0x34, p.text(ee, name))
        if props:
            array = ee.alloc(4 * (len(props) + 1))
            for k, item in enumerate(props):
                m.w32(array + 4 * k, p.text(ee, item))
            m.w32(obj + 0x2C, array)
        for off, value in fld.items():
            if off != 0xC:
                {4: m.w32, 1: m.w8}[WIDTH[off]](obj + off, value)
        head = {'A': GRID_A + 4 * cell, 'B': GRID_B + 4 * cell, 'off': OFF_GRID}[where]
        node = ee.alloc(16)
        p.nodes.append(node)
        m.w32(node + 0xC, obj)
        tail = heads.get(head)
        if tail is None:
            m.w32(head, node)
            m.w32(node + 4, head)
        else:
            m.w32(tail, node)
            m.w32(node + 4, tail)
        heads[head] = node
    order = {'A': 0, 'B': 1, 'off': 2}
    walk = sorted(range(len(specs)), key=lambda i: (order[specs[i][0]], specs[i][1], i))
    records = []
    for i in walk:
        where, cell, name, cls, flags, props, angle, pos, fld = specs[i]
        if flags & 0x4000 or name.lower() in filtered:
            continue
        fld = dict(fld)
        fld[0xC] = flags
        records.append((name.split(';')[0].split(',')[0], props, angle, pos, TAILS[cls](fld)))
    return records


def writer_case(p, ee, rng, specs, decal_blocks=(), filtered=()):
    m = ee.mem
    records = build_world(p, ee, rng, specs, filtered)
    m.write(DECALS, b'\0' * (30 * 30 * 4))
    expect_decals = []
    for k in range(15):
        for row, col, entries in sorted(decal_blocks):
            if k < len(entries):
                expect_decals.append(entries[k])
    for row, col, entries in decal_blocks:
        block = ee.alloc(0x180)
        m.w32(block + 0x178, len(entries))
        for k, (a, b, c, x, y, z) in enumerate(entries):
            base = block + 0x18 * k
            m.w16(base + 8, a)
            m.w16(base + 0xA, b)
            m.w16(base + 0xC, c)
            m.w16(base + 0x10, x & 0xFFFF)
            m.w16(base + 0x12, y & 0xFFFF)
            m.w16(base + 0x14, z & 0xFFFF)
        m.w32(DECALS + 4 * (row * 30 + col), block)
    grid = bytes(rng.getrandbits(8) for _ in range(0x16B00))
    m.write(AUTOMAP, grid)
    space = 35000
    dst = DATA
    m.write(dst, bytes([SENTINEL]) * (space + 0x40))
    sp = ee.r[29] & M32
    m.write(sp - 0x10000, bytes([STACK_FILL]) * (0x10000 - 0x100))
    lists = [(GRID_A, GRID_BYTES), (GRID_B, GRID_BYTES), (OFF_GRID, 4)] + \
        [(node, 16) for node in p.nodes]
    before = [m.read(addr, size) for addr, size in lists]
    ee.reset_log()
    p.call(ee, WRITE, dst, space)
    p.equal([m.read(addr, size) for addr, size in lists], before)   # iterators unlinked
    section, holes, padded = R.objects_section(records)
    got = m.read(dst, space + 0x40)
    p.equal(struct.unpack_from('<I', got, 0)[0], padded)
    p.equal(got[4:8], bytes([SENTINEL]) * 4)
    expect = bytearray(section.ljust(padded, bytes([SENTINEL])))
    for lo, hi in holes:                 # copied from the stack record buffer
        expect[lo:hi] = bytes([STACK_FILL]) * (hi - lo)
        p.counts['hole_bytes'] += hi - lo
    p.equal(got[8:8 + padded], bytes(expect))
    at = 8 + padded
    p.equal(m.u32(OBJ_SIZE_WORD), padded)
    decal_len = struct.unpack_from('<I', got, at)[0]
    p.equal(decal_len, 8 + 12 * len(expect_decals))
    p.equal(got[at + 4:at + 8], bytes([SENTINEL]) * 4)
    p.equal(struct.unpack_from('<I', got, at + 8)[0], len(expect_decals))
    p.equal(got[at + 12:at + 16], bytes([SENTINEL]) * 4)
    for k, (a, b, c, x, y, z) in enumerate(expect_decals):
        e = got[at + 16 + 12 * k:at + 28 + 12 * k]
        dist = W.f2i(W.fadd(W.fsqrt(W.i2f((x * x + y * y) & M32)), 0x3F000000)) & 0xFFFF
        p.equal(struct.unpack_from('<4H', e, 0), (a, b, c, dist))
        p.equal(e[10], ((z - 0x3D3) >> 1) & 0xFF)
        p.counts['decal_entries'] += 1
    automap = at + 8 + decal_len
    p.equal(got[automap:automap + 5832], R.automap_pack(grid))
    p.equal(got[automap + 5832:automap + 5832 + 16], bytes([SENTINEL]) * 16)
    allowed = [(dst, automap + 5832 + dst), (OBJ_SIZE_WORD, OBJ_SIZE_WORD + 4),
               (STR_START, STR_END + 4)] + [(addr, addr + size) for addr, size in lists]
    outside = [w for w in ee.writes if not any(lo <= w[1] < hi for lo, hi in allowed)]
    p.equal(outside, [])
    p.equal(p.stubbed_targets(ee), set())
    p.counts['writer_cases'] += 1
    p.counts['record_bytes'] += len(section)
    p.counts['records'] += len(records)
    return got[:automap + 5832], padded, decal_len, grid


def writer(p, ee, rng):
    m = ee.mem
    p.equal(m.u32(FILTER), 0)                # g_saveFilter in the image, before boot
    for cls, vt in VTABLES.items():
        p.equal(m.s16(vt + 0x48), 0)         # slot-9 this adjustment
    p.equal(writer_case(p, ee, rng, [])[1], 8)

    def pos():
        return tuple(f(rng.uniform(-3000, 3000)) for _ in range(3))

    def fields(cls):
        return {
            'GameObject': {},
            'Counter': {0x4C: rng.getrandbits(32)},
            'Lever': {0x4C: f(rng.uniform(0, 4)), 0x50: rng.getrandbits(8),
                      0x51: rng.getrandbits(8)},
            'JumpGate': {0x4D: rng.getrandbits(8), 0x4E: rng.getrandbits(8)},
            'Savepoint': {0x80: rng.getrandbits(32), 0x84: rng.choice((0, rng.getrandbits(32))),
                          0xC5: rng.getrandbits(8), 0xC6: rng.getrandbits(8)},
        }[cls]
    specs = [
        ('A', 120 * 7 + 9, 'SYN_Prop', 'GameObject', 0, ['SYN_k=1', 'SYN_s=two'],
         rng.getrandbits(16), pos(), fields('GameObject')),
        ('A', 120 * 7 + 9, 'Counter;3', 'Counter', 0x1000, ['SYN_s=two'],
         rng.getrandbits(16), pos(), fields('Counter')),
        ('A', 120 * 2 + 100, 'Lever,b', 'Lever', 0x2000, [], rng.getrandbits(16), pos(),
         fields('Lever')),
        ('A', 120 * 2 + 101, 'SYN_Gone', 'GameObject', 0x4000, ['SYN_k=1'],
         rng.getrandbits(16), pos(), {}),
        ('B', 5, 'JumpGate', 'JumpGate', 0x800, ['SYN_dest=x'], rng.getrandbits(16), pos(),
         fields('JumpGate')),
        ('off', 0, 'Savepoint', 'Savepoint', 2, ['SYN_k=1', 'SYN_a=1', 'SYN_b=2'],
         rng.getrandbits(16), pos(), fields('Savepoint')),
        ('off', 0, 'Savepoint', 'Savepoint', 2, [], rng.getrandbits(16), pos(),
         {**fields('Savepoint'), 0x84: 0}),
    ]
    rng.shuffle(specs)
    decals = [(3, 4, [(rng.getrandbits(16), rng.getrandbits(16), rng.getrandbits(16),
                       rng.randrange(-300, 300), rng.randrange(-300, 300),
                       rng.randrange(0x3D3, 0x5D3)) for _ in range(2)]),
              (0, 0, [(1, 2, 3, 30, -40, 0x3D3 + 21)])]
    writer_case(p, ee, rng, specs, decals)
    # Boot state: main 0x323ecc calls objects_registerFactory, which installs
    # world_saveFilter. It compares the whole +0x34 name, ignoring case.
    p.call(ee, REGISTER_FACTORY)
    p.equal(m.u32(FILTER), SAVE_FILTER)
    names = filter_names(ee)
    p.equal(len(names) >= 1, True)
    pick = names[rng.randrange(len(names))]
    specs = specs + [
        ('A', 120 * 9 + 9, pick, 'GameObject', 0, [], rng.getrandbits(16), pos(), {}),
        ('A', 120 * 9 + 9, pick.upper(), 'GameObject', 0, [], rng.getrandbits(16), pos(), {}),
        ('off', 0, pick + ';1', 'GameObject', 0, ['SYN_k=1'], rng.getrandbits(16), pos(), {}),
    ]
    p.counts['filter_names'] = len(names)
    return writer_case(p, ee, rng, specs, decals, {n.lower() for n in names})


# ---------------------------------------------------------------------------
# 4. Entry scripts and the stored-state reader
# ---------------------------------------------------------------------------

def builtins(ee):
    out, at = [], BUILTINS
    while ee.mem.u32(at):
        out.append((ee.mem.cstr(ee.mem.u32(at)), ee.mem.u32(at + 4)))
        at += 8
    return out


class Script:
    """Original-side native recorders and the model side, same returns."""

    def __init__(self, p, ee, image, seed):
        self.p, self.ee = p, ee
        self.table = builtins(ee)
        self.trace, self.model_trace = [], []
        self.seed = seed
        self.pending = []
        self.names = None

        def at_native(e):
            self.pending.append(e.r[5] & M32)

        def at_call_script(e):
            self.pending.pop()
            params = e.r[5] & M32
            count = e.mem.s32(params) // 4
            self.trace.append((b'callScript', tuple(e.mem.s32(params + 4 + 4 * k)
                                                    for k in range(count))))
        ee.hook(CALL_NATIVE, at_native)
        ee.hook(CALL_SCRIPT, at_call_script)
        for _name, addr in self.table:
            if addr != CALL_SCRIPT:
                ee.stub(addr, function=self._orig)
                p.stubs.add(addr)
        self.model = ref_amx.Machine(image)
        p.equal(self.model.load(), 0)
        self.names = self.model.native_names()
        natives = {name: (self._model_call if name == b'callScript' else self._model(name))
                   for name in self.names}
        p.equal(self.model.register(natives), 0)

    @staticmethod
    def returns(rng):
        roll = rng.random()
        return 0 if roll < 0.5 else 1 if roll < 0.8 else rng.randint(2, 6)

    def begin(self):
        self.orig_rng = random.Random(self.seed)
        self.model_rng = random.Random(self.seed)

    def _orig(self, e):
        index = self.pending.pop()
        params = e.r[5] & M32
        count = e.mem.s32(params) // 4
        args = tuple(e.mem.s32(params + 4 + 4 * k) for k in range(count))
        self.trace.append((self.names[index], args))
        return self.returns(self.orig_rng) & M32

    def _model(self, name):
        def native(machine, args):
            self.model_trace.append((name, tuple(args)))
            return self.returns(self.model_rng)
        return native

    def _model_call(self, machine, args):
        self.model_trace.append((b'callScript', tuple(args)))
        return machine.call(machine.get_string(args[0]))


def arrive(p, ee, lmp, lumps, level, rng, stored=None, gate=0, from_save=0, eleventh=None):
    """level_loadScriptAndObjects(level, qualified) with world_loadRecords recorded."""
    m = ee.mem
    loads = []
    ee.stub(LOAD_RECORDS, function=lambda e: loads.append((e.r[4] & M32, e.r[5] & M32)) or 0)
    p.stubs.add(LOAD_RECORDS)
    image = R.lmp_entry(lmp, 'script.scr')
    script = Script(p, ee, image, rng.getrandbits(32))
    m.write(DIRECTORY, b'\0' * (11 * 0x18))
    if stored is not None:
        blob, padded, decal_len = stored
        m.write(DIRECTORY, level.encode() + b'\0')
        m.w32(DIRECTORY + 0x14, len(blob))
        m.write(DATA, blob)
        prior = 0
    if eleventh is not None:
        blob, padded, decal_len = eleventh
        for k in range(10):
            m.write(DIRECTORY + 0x18 * k, b'SYN_K%d\0' % k)
            m.w32(DIRECTORY + 0x18 * k + 0x14, 1)
        m.write(DIRECTORY + 0x18 * 10, b'SYN_ELEVEN\0')
        m.w32(DIRECTORY + 0x18 * 10 + 0x14, len(blob))
        m.write(DATA + 10, blob)
        stored, prior = eleventh, 10
    m.w8(SCRIPT_GATE, gate)
    m.w8(FROM_SAVE, from_save)
    m.w8(RANK, 0x55)
    m.write(RESTORE, b'\0' * 0x100)
    name_ptr = p.text(ee, level)
    qual = ee.alloc(0x80)
    p.call(ee, QUALIFIED, qual)
    p.equal(m.cstr(qual), level)
    rec = p.call(ee, FIND_ENTRY, lumps[level + '.lmp'], p.text(ee, 'script.scr')) & M32
    script_ptr = m.u32(rec + 4)
    m.write(script_ptr, image)           # a fresh lump load: unrelocated bytes
    rec = p.call(ee, FIND_ENTRY, lumps[level + '.lmp'], p.text(ee, 'objects.ob')) & M32
    objects_ptr = m.u32(rec + 4)
    script.begin()
    ee.reset_log()
    p.call(ee, ARRIVE, name_ptr, qual)
    seq = [c for c in ee.calls if c.target in (SET_SCRIPT, RUN_SCRIPT, LOAD_RECORDS,
                                               AUTOMAP_UNPACK, DECAL_LOAD)]
    top = [(c.target, m.cstr(c.args[0] & M32) if c.target == RUN_SCRIPT else c.args[0] & M32)
           for c in seq if c.target != RUN_SCRIPT or m.cstr(c.args[0] & M32) in
           ('preStart', 'start')]
    want = [(SET_SCRIPT, script_ptr)]
    if not gate:
        want.append((RUN_SCRIPT, 'preStart'))
    if stored is not None:
        blob, padded, decal_len = stored
        base = DATA + prior
        want += [(AUTOMAP_UNPACK, base + 0x10 + padded + decal_len),
                 (LOAD_RECORDS, RESTORE), (DECAL_LOAD, RESTORE + padded)]
    want.append((LOAD_RECORDS, objects_ptr))
    if not gate:
        want.append((RUN_SCRIPT, 'start'))
    p.equal(top, want)
    p.equal(loads, ([(RESTORE, 0)] if stored is not None else []) +
            [(objects_ptr, 1 if stored is not None else 0)])
    p.equal(m.u32(MACHINE), script_ptr)
    p.equal(m.u8(RANK), 3 if from_save else 0)
    p.equal(m.u8(FROM_SAVE), 0)
    if stored is not None:
        blob, padded, decal_len = stored
        p.equal(m.read(RESTORE, padded), blob[8:8 + padded])
        p.equal(m.read(RESTORE + padded, decal_len), blob[0x10 + padded:0x10 + padded + decal_len])
        packed = ee.alloc(5832)
        p.call(ee, 0x16865C, packed)
        start = 0x10 + padded + decal_len
        p.equal(m.read(packed, 5832), blob[start:start + 5832])
    if not gate:
        for entry in (b'preStart', b'start'):
            if script.model.find_public(entry.decode())[0] == 0:
                script.model.call(entry.decode())
        p.equal(script.trace, script.model_trace)
        p.counts['natives'] += len(script.trace)
    stray = p.stubbed_targets(ee) - set(SUPPLIED) - {LOAD_RECORDS} - \
        {a for _n, a in script.table}
    p.equal(stray, set())
    ee.unhook(CALL_NATIVE)
    ee.unhook(CALL_SCRIPT)
    for _name, addr in script.table:
        ee.unhook(addr)
    ee.unhook(LOAD_RECORDS)
    p.counts['arrival_cases'] += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seed', type=int, default=20973)
    ap.add_argument('--elf', default='local/SLUS_209.73')
    ap.add_argument('--disc', default='local/rta-disc')
    ap.add_argument('--levels', default=','.join(LEVELS))
    args = ap.parse_args()
    assert hashlib.sha256(Path(args.elf).read_bytes()).hexdigest() == SHA
    rng = random.Random(args.seed)
    p = Probe(args.elf, Disc(args.disc))
    for level in args.levels.split(','):
        ee, lmp, lumps = load_level(p, level)
        placement(p, ee, lmp, level, rng)
        blob, padded, decal_len, _grid = writer(p, ee, rng)
        arrive(p, ee, lmp, lumps, level, rng)
        arrive(p, ee, lmp, lumps, level, rng, gate=1, from_save=1)
        arrive(p, ee, lmp, lumps, level, rng, stored=(blob, padded, decal_len))
        empty, epad, edecal, _g = writer_case(p, ee, rng, [])
        arrive(p, ee, lmp, lumps, level, rng, eleventh=(empty, epad, edecal))
        missing(p, ee)                  # last: it maps page 0
    p.counts['stubs'] = len(p.stubs)
    print('PASS exit_arrival seed=%d ' % args.seed +
          ' '.join('%s=%d' % item for item in sorted(p.counts.items())) + ' failures=0')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAIL exit_arrival failures=1')
        raise
