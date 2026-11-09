#!/usr/bin/env python3
"""Character-progression probes on the original code (level-up round 3).

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_progression.py /path/to/SLUS_209.73

Every section runs original functions in tools/ee_emu.py on constructed state,
on seeds 20973 and 7, and checks that the shared seed word 0x404464 is left
alone.  Callees that are not listed as followed are recording stubs that return
0; each section names the ones that matter.  This is interpreter evidence: no
console, no pixels, no memory-card hardware.  No table values are embedded; the
expected numbers come from the reference models or from the executable.
"""
import copy
import hashlib
import os
import random
import struct
import sys

from ee_emu import EE
import difftest_levelup as L
import difftest_creature as DC
import difftest_combat as DCB
import ref_combat as R
import ref_skills_a as SA
import ref_skills_b as SB
import ref_skills_c as SC

SEEDS = (20973, 7)
SKILL_STATIC_INIT, SKILL_INIT_STATS = 0x16AC74, 0x1EBCA0
SKILL_BASE = {0x3C82A8, 0x3C82E4, 0x3C85B0, 0x3C85FC, 0x3C8690, 0x3C87F0, 0x3C8864,
              0x3C88DC, 0x3C88E4}
ON_STAT, ON_SKILL = 0x1C2548, 0x1C2648
SET_RANK, ADD_ABILITY, REBUILD, RAISE_PASSIVE = 0x1BF3A0, 0x1D32E4, 0x1D34AC, 0x1BEDD0
NOTICE, TEXT = 0x1D9954, 0x173C84
MEMSET = 0x3B60C0
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
MBTOWC = 0x3C0170
ABILITY = 0x4440                     # 15 records of 0x68; id s16 at +0x20
CURSOR_INPUT, CURSOR_DIR, HERMITE = 0x1C6570, 0x1C6438, 0x1658F0
OPEN_INVENTORY, JOIN_PANEL, DISPATCH = 0x1C15C8, 0x1C0360, 0x1BFDB0
SEND_MSG, IS_LOCAL = 0x13DB38, 0x13E150
SAVE_BUILD, SAVE_LOAD, LOAD_SCREEN = 0x221914, 0x221D60, 0x219360
SAVE_BUFFER, HEADER_COPY, IMAGE_BYTES = 0x895580, 0x879E38, 0x4BC78
QUEST_OFF = 0x13418
CAMERA_PTR = 0x4F8450
VARS_CLEAR, VARS_SET = 0x1ED728, 0x1ED854
SHARE_QUEST, CLEAR_DEFERRED, STORE_LEVEL = 0x1C4FA8, 0x1EDA08, 0x21777C


class Follow:
    """emu.follow: the listed functions and the C library run for real."""

    def __init__(self, *groups):
        self.addresses = set()
        for group in groups:
            self.addresses |= set(group)

    def __contains__(self, target):
        return target in self.addresses or LIB_LO <= target < LIB_HI or target == MBTOWC


def f32(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xFFFFFFFF))[0]


def below(bits):
    """The next float below a non-negative pattern; -FLT_MIN below zero (no denormal)."""
    bits &= 0xFFFFFFFF
    if bits in (0, 0x80000000):
        return 0x80800000
    assert not bits & 0x80000000, hex(bits)
    return bits - 1


# ---------------------------------------------------------------------------
# A snapshot of the interpreter memory after the game's own Skill construction
# ---------------------------------------------------------------------------
class Booted:
    def __init__(self, elf, seed):
        ee = self.ee = L.boot(elf, seed)
        ee.record_calls = False
        ee.call(SKILL_STATIC_INIT, 1, 0xFFFF, max_steps=20_000_000)
        ee.call(SKILL_INIT_STATS, max_steps=20_000_000)
        ee.follow = {L.STRCMP, L.STRCPY}
        ee.default_ret = 0
        ee.call(L.CLASS_SKILLS, max_steps=2_000_000)
        # 0x16ac74 runs every static constructor, and one of them sets the seed
        # word; plant the test seed after it, so the probes below can check it.
        ee.mem.w32(L.SEED, seed)
        ee.record_calls = True
        self.seed = seed
        self.pages = {k: bytes(v) for k, v in ee.mem.pages.items()}

    def fresh(self):
        ee = self.ee
        pages = ee.mem.pages
        pages.clear()
        for key, value in self.pages.items():
            pages[key] = bytearray(value)
        ee.hooks.clear()
        ee.stub_names.clear()
        ee.reset_log()
        ee.record_calls = True
        ee.record_writes = False
        ee.default_ret = 0
        ee.r[29] = ee.stack_hi - 0x100
        return ee


def skill_object(ee, sid):
    skill = ee.mem.u32(L.SKILL_TABLE + 4 * sid)
    table = ee.mem.u32(skill + 0x60)
    return skill, table


def skill_closure(ee, sid):
    skill, table = skill_object(ee, sid)
    return SKILL_BASE | {ee.mem.u32(table + 8 * slot + 4) for slot in range(1, 16)}


def model_for(sid, mem):
    module = SA if sid < 35 else SB if sid < 69 else SC
    return module.Model(DC.ModelView(mem))


def tree_rows(ee, cls, count=2):
    nodes = []
    for index in range(40):
        row = L.tree_row(ee, cls, index)
        if row['x'] == -1:
            break
        nodes.append((index, row))
    ys = sorted({row['y'] for _, row in nodes})[:count]
    return [(index, row, ys.index(row['y']) + 1) for index, row in nodes if row['y'] in ys]


def passive_index(ee, cls, mask):
    base = L.PASSIVE_MASKS + cls * 0xA88
    for index in range(48):
        if ee.mem.u64(base + index * 0x38) == mask:
            return index
    raise AssertionError((cls, mask))


def setup_screen(ee, cls, row, rank, *, slot=0, points=3, mana_bits=0x461C4000,
                 cursor=None, panel_x=0, scroll=0):
    """Record, prerequisite, pad and panel for one skill-screen call on `row`."""
    m = ee.mem
    rec = L.RECORD + slot * L.REC_STRIDE
    level = row['need'] + rank
    m.w32(rec + 0x50, cls)
    m.w8(rec + 0x58, level)
    m.w8(rec + 0x59, level)
    m.w32(rec + 0xE8, points & 0xFFFFFFFF)
    m.w32(rec + 0xC4, mana_bits)
    for index in range(15):
        m.w16(rec + ABILITY + 0x20 + 0x68 * index, 0xFFFF)
    pairs = []
    assert row['pre_kind'] == 1, row
    pre = row['pre']
    if pre != 0xFFFFFFFFFFFFFFFF:
        pairs.append((60 if pre == 0 else pre & 0xFFFF, 1))
    ident = row['ident'] & 0xFFFFFFFF
    if row['kind'] != 0:
        if rank:
            pairs.append((ident, rank))
    else:
        index = passive_index(ee, cls, row['ident'])
        m.w8(rec + 0xEF + index, rank)
        if rank:
            m.w32(rec + 0x128, m.u32(rec + 0x128) | (row['ident'] & 0xFFFFFFFF))
    L.put_ranks(ee, slot, pairs)
    pad = L.PAD_BASE + 88 * slot
    m.w32(pad + 8, 0)
    m.w32(pad + 0xC, 0x40)
    m.w32(0x4F65EC, slot)
    m.w32(L.PANEL + 0x00, panel_x)
    m.w32(L.PANEL + 0x28, scroll & 0xFFFFFFFF)
    m.w32(L.PANEL + 0x30, 0)
    m.w32(L.PANEL + 0x50, 5)
    m.w32(L.GATE, 0)
    if cursor is None:
        cursor = (panel_x + row['x'] + 1, row['y'] + 0x9E + 1 - scroll)
    m.wf32(L.PANEL + 0x44, cursor[0])
    m.wf32(L.PANEL + 0x48, cursor[1])
    return rec


def run_screen(ee, follow):
    ee.stub(L.RES_FIND, ret=1)
    ee.stub(IS_LOCAL, ret=1)     # the owner is local: sounds and the notice box run
    ee.follow = follow
    ee.reset_log()
    ee.call(L.SKILL_SCREEN, 0, max_steps=5_000_000)
    sends = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF)
             for c in ee.calls if c.target == L.SKILL_SENDER]
    return sends


SCREEN_FOLLOW = {L.RANK, L.PASSIVE, L.STRCMP, L.STRCPY, L.CLASS_SKILLS}
HANDLER_FOLLOW = Follow({L.RANK, SET_RANK, ADD_ABILITY, L.PASSIVE, RAISE_PASSIVE, REBUILD})


def apply_handler(ee, slot, kind, value):
    ee.follow = HANDLER_FOLLOW
    ee.stub(IS_LOCAL, ret=0)
    ee.reset_log()
    ee.record_writes = True
    ee.writes = []
    ee.call(ON_SKILL, slot, kind, value, max_steps=2_000_000)
    ee.record_writes = False
    return list(ee.writes), [c.target for c in ee.calls]


def writes_outside(writes, rec, allowed):
    out = []
    for pc, addr, size, value in writes:
        if not any(base <= addr and addr + size <= base + length
                   for base, length in ((rec + off, n) for off, n in allowed)):
            out.append((hex(pc), hex(addr), size))
    return out


# ---------------------------------------------------------------------------
# 1. Rows 1-2 skill nodes: original mana-cost body, the screen's <= compare,
#    and what message 7 then does to the record
# ---------------------------------------------------------------------------
def skill_rows(elf):
    for seed in SEEDS:
        booted = Booted(elf, seed)
        bodies = sends_checked = learned = fractions = 0
        ids = set()
        for cls in range(7):
            for node, row, rowno in tree_rows(booted.ee, cls):
                if row['kind'] == 0:
                    continue
                sid = row['ident'] & 0xFFFFFFFF
                ids.add(sid)
                for rank in (0, 1, 9, 19):
                    ee = booted.fresh()
                    skill, table = skill_object(ee, sid)
                    fn = ee.mem.u32(table + 0x2C)
                    this = (skill + ee.mem.s16(table + 0x28)) & 0xFFFFFFFF
                    closure = skill_closure(ee, sid)
                    ee.follow = closure
                    ee.call(fn, this, rank + 1, max_steps=200_000)
                    cost = ee.f[0] & 0xFFFFFFFF
                    assert not [c for c in ee.calls if c.stubbed], (seed, sid, ee.calls)
                    want = model_for(sid, ee.mem).skill_call(skill, 5, rank + 1) & 0xFFFFFFFF
                    assert cost == want, (seed, sid, rank, hex(cost), hex(want))
                    bodies += 1
                    for mana_bits, sends_ok in ((cost, True), (below(cost), False)):
                        ee = booted.fresh()
                        rec = setup_screen(ee, cls, row, rank, mana_bits=mana_bits)
                        sends = run_screen(ee, SCREEN_FOLLOW | closure)
                        virt = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
                                for c in ee.calls if c.target == fn]
                        assert virt == [(0x1D5884, this, rank + 1)], (seed, sid, rank, virt)
                        recalc = [c.site for c in ee.calls if c.target == L.RECALC]
                        assert recalc == [0x1D5950], (seed, sid, rank, recalc)
                        notice = [c.site for c in ee.calls if c.target == NOTICE]
                        keys = [ee.mem.cstr(c.args[0] & 0xFFFFFFFF) for c in ee.calls
                                if c.target == TEXT]
                        if sends_ok:
                            assert sends == [(0x1D58DC, 0, 1, sid)], (seed, sid, rank, sends)
                            assert notice == [] and 'NotEnoughMana' not in keys
                        else:
                            assert sends == [], (seed, sid, rank, sends)
                            assert notice == [0x1D5948], (seed, sid, rank, notice)
                            assert 'NotEnoughMana' in keys and 'NotEnoughManaDesc' in keys, keys
                        assert ee.mem.u32(L.SEED) == seed
                        sends_checked += 1
                        if not sends_ok:
                            continue
                        kind3 = ee.mem.u32(skill + 8) == 3
                        writes, targets = apply_handler(ee, 0, 1, sid)
                        assert ee.mem.s32(rec + 0xE8) == 2, (seed, sid, rank)
                        ee.follow = HANDLER_FOLLOW
                        got_rank = ee.call(L.RANK, 0, sid) & 0xFFFFFFFF
                        assert got_rank == rank + 1, (seed, sid, rank, got_rank)
                        stray = writes_outside(writes, rec, ((0xE8, 4), (0x4B08, 4 * 20),
                                                             (ABILITY, 15 * 0x68)))
                        assert not stray, (seed, sid, rank, stray)
                        added = [i for i in range(15)
                                 if ee.mem.s16(rec + ABILITY + 0x20 + 0x68 * i) == sid]
                        if rank == 0 and not kind3:
                            # reached by the tail jump at 0x1c2784, so judged by its record
                            assert len(added) == 1, (seed, sid, added)
                            assert ee.mem.cstr(rec + ABILITY + 0x68 * added[0]) == 'newstyle'
                        else:
                            assert not added, (seed, sid, rank, added)
                        assert L.RECALC not in targets
                        learned += 1
                    if sid in (48, 79):
                        ee = booted.fresh()
                        frac_fn = {48: 0x2DBCAC, 79: 0x304B54}[sid]
                        ee.follow = closure
                        ee.call(frac_fn, skill, rank + 1, max_steps=200_000)
                        got = ee.f[0] & 0xFFFFFFFF
                        model = model_for(sid, ee.mem)
                        method = model.archery_fraction if sid == 48 else model.throwing_fraction
                        assert got == method(skill, rank + 1) & 0xFFFFFFFF, (seed, sid, rank)
                        fractions += 1
        print('PASS seed %d: %d slot-5 mana bodies of rows 1-2 (%d skills) equal the models'
              % (seed, bodies, len(ids)))
        print('PASS seed %d: %d skill-screen mana compares at the cost and one float below'
              % (seed, sends_checked))
        print('PASS seed %d: %d sent skill points applied by message 7 (rank + 1, one point)'
              % (seed, learned))
        print('PASS seed %d: %d archery/throwing fractions at the learned rank' % (seed, fractions))


# ---------------------------------------------------------------------------
# 2. Rows 1-2 passive nodes: send, then message 7 kind 0
# ---------------------------------------------------------------------------
def passive_rows(elf):
    for seed in SEEDS:
        booted = Booted(elf, seed)
        count = 0
        for cls in range(7):
            for node, row, rowno in tree_rows(booted.ee, cls):
                if row['kind'] != 0:
                    continue
                mask = row['ident'] & 0xFFFFFFFF
                for rank in (0, 1, 19):
                    ee = booted.fresh()
                    rec = setup_screen(ee, cls, row, rank)
                    m = ee.mem
                    m.wf32(rec + 0x124, 100.0)
                    m.wf32(rec + 0xAC, 10.0)
                    m.wf32(rec + 0xB0, 20.0)
                    m.wf32(rec + 0xC0, 10.0)
                    m.wf32(rec + 0xC4, 20.0)
                    sends = run_screen(ee, SCREEN_FOLLOW)
                    assert sends == [(0x1D580C, 0, 0, mask)], (seed, cls, node, rank, sends)
                    before_128 = m.u64(rec + 0x128)
                    writes, targets = apply_handler(ee, 0, 0, mask)
                    index = passive_index(ee, cls, row['ident'])
                    assert m.s8(rec + 0xEF + index) == rank + 1, (seed, cls, mask, rank)
                    assert m.s32(rec + 0xE8) == 2
                    assert REBUILD in targets and L.RECALC not in targets
                    assert m.u64(rec + 0x128) == before_128 | mask, (seed, mask, rank)   # u64 (sd 0x1d37e8)
                    first = rank == 0
                    load = f32(m.u32(rec + 0x124))
                    if mask == 0x40 and first:
                        assert load == 115.0, (seed, cls, load)
                    else:
                        assert load == 100.0, (seed, cls, mask, rank, load)
                    stray = writes_outside(writes, rec, ((0xE8, 4), (0xEF, 48), (0x124, 12),
                                                         (ABILITY, 15 * 0x68)))
                    assert not stray, (seed, cls, mask, rank, stray)
                    assert m.u32(L.SEED) == seed
                    count += 1
        print('PASS seed %d: %d passive nodes of rows 1-2 sent and applied by message 7'
              % (seed, count))


# ---------------------------------------------------------------------------
# 3. Skill-screen cursor box: inclusive edges, panel origin, scroll, truncation
# ---------------------------------------------------------------------------
def box_edges(elf):
    for seed in SEEDS:
        booted = Booted(elf, seed)
        count = 0
        for cls, node in ((0, 0), (3, 4)):
            row = L.tree_row(booted.ee, cls, node)
            sid = row['ident'] & 0xFFFFFFFF
            closure = skill_closure(booted.ee, sid)
            for panel_x, scroll in ((0, 0), (40, 13), (-24, -13)):
                x_lo = panel_x + row['x']
                x_hi = x_lo + 0x32
                y_lo = row['y'] + 0x9E
                y_hi = row['y'] + 0xD0
                xm, ym = (x_lo + x_hi) // 2, (y_lo + y_hi) // 2
                cases = [((x_lo, ym), 1), ((x_lo - 1, ym), 0), ((x_hi, ym), 1),
                         ((x_hi + 1, ym), 0), ((xm, y_lo), 1), ((xm, y_lo - 1), 0),
                         ((xm, y_hi), 1), ((xm, y_hi + 1), 0), ((x_lo, y_lo), 1),
                         ((x_hi, y_hi), 1), ((x_hi + 0.75, ym), 1), ((x_hi + 1.25, ym), 0),
                         ((xm, y_hi + 0.75), 1), ((xm, y_lo - 0.25), 0 if y_lo - scroll > 0 else 1)]
                for (x, y), hit in cases:
                    ee = booted.fresh()
                    rank = 0
                    setup_screen(ee, cls, row, rank, cursor=(x, y - scroll), panel_x=panel_x,
                                 scroll=scroll)
                    sends = run_screen(ee, SCREEN_FOLLOW | closure)
                    want = [(0x1D58DC, 0, 1, sid)] if hit else []
                    assert sends == want, (seed, cls, node, panel_x, scroll, x, y, sends)
                    assert ee.mem.u32(L.SEED) == seed
                    count += 1
        print('PASS seed %d: %d skill-screen cursor-box edge cases' % (seed, count))


# ---------------------------------------------------------------------------
# 4. Stat screen: the row is menu_cursorInput's list cursor, clamped to 0..3
# ---------------------------------------------------------------------------
def stat_frames(elf, seed, start, held, frames, edge=0, slot=0):
    ee = EE(elf)
    ee.mem.auto_map = True
    ee.follow = {CURSOR_INPUT, CURSOR_DIR, HERMITE}
    ee.default_ret = 0
    m = ee.mem
    m.w32(L.SEED, seed)
    m.w32(0x44FDA4, 3000)
    m.w32(0x4F65EC, slot)
    m.w32(0x4F65CC, 0)
    m.w32(0x4F65D0, start)
    m.w8(L.RECORD + 0x4C30 * slot + 0xEC, 3)
    trail, sends = [], []
    for _ in range(frames):
        m.w32(L.PAD_BASE + 88 * slot + 8, held)
        m.w32(0x41BFE8 + 88 * slot, edge)
        ee.reset_log()
        ee.call(L.SCREEN, 0, 2, 0, 0x4F4040, max_steps=1_000_000)
        trail.append((m.s32(0x4F65D0), m.s32(0x4F65CC)))
        sends += [(c.site, c.args[1] & 0xFFFFFFFF) for c in ee.calls if c.target == L.SENDER]
        cursor = [c.site for c in ee.calls if c.target == CURSOR_INPUT]
        assert cursor == [0x1D2350], cursor
    assert m.u32(L.SEED) == seed
    return trail, sends


def stat_rows(elf):
    down, up = 0x4000, 0x1000
    for seed in SEEDS:
        count = 0
        for held in (down, 0x200000):
            trail, _ = stat_frames(elf, seed, 1, held, 1)
            assert trail[0] == (1, 1), trail          # a move starts: direction word +1
            count += 1
            trail, _ = stat_frames(elf, seed, 3, held, 40)
            assert all(t == (3, 0) for t in trail), trail   # bottom row: no move, no wrap
            count += 1
        for held in (up, 0x100000):
            trail, _ = stat_frames(elf, seed, 2, held, 1)
            assert trail[0] == (2, -1), trail
            count += 1
            trail, _ = stat_frames(elf, seed, 0, held, 40)
            assert all(t == (0, 0) for t in trail), trail   # top row: no move, no wrap
            count += 1
        trail, _ = stat_frames(elf, seed, 0, down, 200)
        rows = [r for r, _ in trail]
        assert rows[-1] == 3 and max(rows) == 3 and rows == sorted(rows), rows
        steps = [b - a for a, b in zip(rows, rows[1:]) if b != a]
        assert steps == [1, 1, 1], steps                     # one row per finished move
        count += 1
        trail, _ = stat_frames(elf, seed, 3, up, 200)
        rows = [r for r, _ in trail]
        assert rows[-1] == 0 and rows == sorted(rows, reverse=True), rows
        count += 1
        # the confirm edge on a frame where the move is running does not send
        trail, sends = stat_frames(elf, seed, 1, down, 1, edge=0x40)
        assert trail[0] == (1, 1) and sends == [], (trail, sends)
        trail, sends = stat_frames(elf, seed, 1, 0, 1, edge=0x40)
        assert trail[0] == (1, 0) and sends == [(0x1D24F4, 1)], (trail, sends)
        count += 2
        print('PASS seed %d: %d stat-screen row cursor edges' % (seed, count))


# ---------------------------------------------------------------------------
# 5. What a spend changes downstream: the combat rig (difftest_combat) runs the
#    original handler and then the original recalc against ref_combat
# ---------------------------------------------------------------------------
def combat_rig(elf, tables, booted):
    DCB.REAL.update({ON_STAT, ON_SKILL, SET_RANK, ADD_ABILITY, REBUILD, RAISE_PASSIVE, MEMSET})
    rig = DCB.Rig(elf)
    rig.emu.stub(IS_LOCAL, ret=0)
    # the rig's stand-in Skill objects get the kind word the game's own init left
    for sid in (0x30, 0x3C, 0x3D, 0x4F):
        real_kind = booted.ee.mem.u32(booted.ee.mem.u32(L.SKILL_TABLE + 4 * sid) + 8)
        rig.mem.w32(rig.mem.u32(DCB.G_SKILL_TABLE + 4 * sid) + 8, real_kind)
    return rig


def spend_downstream(elf):
    tables = R.Tables.load(elf)
    weapon_for = {0x3C: dict(dmg_type=1, subtype=0), 0x3D: dict(dmg_type=8, subtype=0),
                  0x30: dict(subtype=4, dmg_type=0), 0x4F: dict(subtype=6, dmg_type=0)}
    for seed in SEEDS:
        booted = Booted(elf, seed)
        rig = combat_rig(elf, tables, booted)
        rng = random.Random(seed)
        stat_cases = spends = 0
        moved = {}
        for case in range(64):
            w = DCB.make_world(rng)
            objects = []
            DCB.gen_players(rng, tables, w, objects)
            slot = rng.choice([s for s in range(4) if w.players[s].obj is not None])
            rec = w.players[slot]
            w.num_players = max(R.s32(w.num_players), slot + 1)
            rec.stat_points = rng.choice((0, 1, 1, 2, 5, 40))
            rig.begin({'world': w, 'local': 0})
            rig.put_objects(objects)
            rig.put_world(w)
            stat = case % 4
            unspent = copy.deepcopy(w)
            R.recalc_stats(tables, unspent)
            rig.emu.reset_log()
            rig.call(ON_STAT, slot, stat)
            spent = R.s8(rec.stat_points) != 0
            if spent:
                rec.base[stat] = R.s32(rec.base[stat] + 1)
                rec.stat_points = R.s8(rec.stat_points - 1)
            R.recalc_stats(tables, w)
            assert DCB.compare_players(rig, DCB.Tally(), 'stat spend', w, objects), (seed, case)
            addr = L.RECORD + slot * L.REC_STRIDE
            if R.s8(rec.stat_points) == 0:
                assert rig.mem.u8(addr + 0xEE) == 1, (seed, case)
            if spent:
                a, b = DCB.Rig.model_record(unspent.players[slot]), DCB.Rig.model_record(rec)
                for key in ('max_hp', 'max_mana', 'load_limit'):
                    if a[key] != b[key]:
                        moved.setdefault((stat, key), 0)
                        moved[(stat, key)] += 1
                if unspent.players[slot].obj.armor != rec.obj.armor:
                    moved[(stat, 'armor')] = moved.get((stat, 'armor'), 0) + 1
                spends += 1
            assert all(item[1] != addr + 0x58 for item in rig.emu.writes)
            stat_cases += 1
        learn_cases = 0
        for case in range(48):
            sid = (0x3C, 0x3D, 0x30, 0x4F)[case % 4]
            rank = (0, 1, 9, 19)[(case // 4) % 4]
            w = DCB.make_world(rng)
            objects = []
            DCB.gen_players(rng, tables, w, objects)
            slot = rng.choice([s for s in range(4) if w.players[s].obj is not None])
            rec = w.players[slot]
            rec.skills = [(i, r) for i, r in rec.skills if i != sid] + ([(sid, rank)] if rank else [])
            rec.skill_points = rng.randrange(1, 9)
            weapon = DCB.gen_item(rng, tables, None, True)
            for key, value in weapon_for[sid].items():
                setattr(weapon.defn, key, value)
            rec.weapon_sets[0] = weapon
            rec.second_weapon = None
            rec.cls = 0
            rig.begin({'world': w, 'local': 0})
            rig.put_objects(objects)
            rig.put_world(w)
            rig.emu.reset_log()
            rig.call(ON_SKILL, slot, 1, sid)
            if rank:
                rec.skills = [(i, r + 1 if i == sid else r) for i, r in rec.skills]
            else:
                rec.skills = rec.skills + [(sid, 1)]
            rec.skill_points -= 1
            rig.call(0x1B7158, rig.addr[id(rec.obj)], rig.addr[id(weapon)], 0)
            R.recalc_damage(tables, w, rec.obj, weapon, 0)
            assert DCB.compare_players(rig, DCB.Tally(), 'learn', w, objects), (seed, sid, rank)
            learn_cases += 1
        passive_cases = 0
        for case in range(16):
            w = DCB.make_world(rng)
            objects = []
            DCB.gen_players(rng, tables, w, objects)
            slot = rng.choice([s for s in range(4) if w.players[s].obj is not None])
            w.num_players = max(R.s32(w.num_players), slot + 1)
            rec = w.players[slot]
            rec.cls = (1, 3)[case % 2]
            index = [i for i in range(48)
                     if booted.ee.mem.u64(L.PASSIVE_MASKS + rec.cls * 0xA88 + i * 0x38) == 0x40][0]
            rank = (0, 1, 5, 19)[(case // 2) % 4]
            rec.passives = list(rec.passives)
            rec.passives[index] = rank
            rec.skill_points = rng.randrange(1, 9)
            rig.begin({'world': w, 'local': 0})
            rig.put_objects(objects)
            rig.put_world(w)
            rig.emu.reset_log()
            rig.call(ON_SKILL, slot, 0, 0x40)
            rec.passives[index] = rank + 1
            rec.skill_points -= 1
            rig.call(L.RECALC)
            R.recalc_stats(tables, w)
            assert DCB.compare_players(rig, DCB.Tally(), 'passive', w, objects), (seed, rank)
            passive_cases += 1
        print('PASS seed %d: %d stat spends through the original handler and recalc '
              '(%d with a point to spend)' % (seed, stat_cases, spends))
        print('      seed %d: fields a spend moved, by stat index: %s' % (
            seed, ', '.join('%d:%s x%d' % (k[0], k[1], v) for k, v in sorted(moved.items()))))
        names = {0: {'load_limit'}, 1: {'max_mana'}, 2: {'armor'}, 3: {'max_hp'}}
        assert all(key in names[stat] for stat, key in moved), moved
        print('PASS seed %d: %d skill learns of 48/60/61/79 followed by the original '
              'Player_recalcDamage' % (seed, learn_cases))
        print('PASS seed %d: %d passive 0x40 learns followed by the original recalc'
              % (seed, passive_cases))


# ---------------------------------------------------------------------------
# 6. Acknowledged level +0x58: static writers and the message 9 path
# ---------------------------------------------------------------------------
def load_functions(root):
    funcs = []
    with open(os.path.join(root, 'ghidra_funcs.tsv')) as source:
        for line in source:
            if not line.strip() or line.startswith('#'):
                continue
            entry, name, body = line.rstrip('\n').split('\t')
            ranges = [tuple(int(x, 16) for x in part.split('-')) for part in body.split(',') if part]
            funcs.append((int(entry, 16), name, ranges))
    return funcs


def owner_of(funcs, pc):
    for entry, name, ranges in funcs:
        if any(lo <= pc <= hi for lo, hi in ranges):
            return entry
    return None


def addresses_records(ee, funcs, entry):
    for e, name, ranges in funcs:
        if e != entry:
            continue
        for lo, hi in ranges:
            for addr in range(lo, hi, 4):
                word = ee.mem.u32(addr)
                if word >> 26 in (0x09, 0x0D) and word & 0xFFFF in (0x8AF0, 0x4C30):
                    return True
    return False


def ack_writers(elf):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    funcs = load_functions(root)
    ee = EE(elf)
    sb58, absolute = [], []
    for pc in range(0x100000, 0x3C0000, 4):
        word = ee.mem.u32(pc)
        if word >> 26 == 0x28 and word & 0xFFFF == 0x58:
            sb58.append(pc)
        if word >> 26 in (0x28, 0x29, 0x2B, 0x3F) and word & 0xFFFF == 0x8B48:
            absolute.append(pc)
    record_sb = sorted({owner_of(funcs, pc) for pc in sb58
                        if addresses_records(ee, funcs, owner_of(funcs, pc))})
    assert absolute == [0x1BFF6C], [hex(a) for a in absolute]
    assert record_sb == [0x1BD458, 0x28AA7C], [hex(a) for a in record_sb if a is not None]
    # DoorSwing_interact also names g_players, but its two stores use $17, which
    # 0x28aa90 copies from $4 (the door object): the door's own +0x58.
    door = [pc for pc in sb58 if owner_of(funcs, pc) == 0x28AA7C]
    assert door == [0x28ADB8, 0x28AE0C] and all((ee.mem.u32(pc) >> 21) & 31 == 17 for pc in door)
    move = ee.mem.u32(0x28AA90)
    assert (move >> 11) & 31 == 17 and (move >> 21) & 31 == 4 and move & 0x3F in (0x21, 0x25, 0x2D)
    imported = [pc for pc in sb58 if owner_of(funcs, pc) == 0x1BD458]
    assert imported == [0x1BD520, 0x1BD528, 0x1BD57C], [hex(pc) for pc in imported]
    print('PASS static: %d byte stores at offset 0x58 in .text; record writers among them are '
          'player_importCharacter 0x1bd520/0x1bd528/0x1bd57c only (DoorSwing_interact '
          'stores its own field); the one store to 0x4d8b48 is 0x1bff6c in invmsg_dispatch'
          % len(sb58))
    for seed in SEEDS:
        count = 0
        for slot, earned, ack, level_up in ((0, 7, 3, 1), (1, 12, 12, 0), (0, 40, 1, 1)):
            e = EE(elf)
            e.mem.auto_map = True
            e.mem.w32(L.SEED, seed)
            e.follow = {OPEN_INVENTORY}
            e.default_ret = 0
            e.stub(IS_LOCAL, ret=1)
            rec = L.RECORD + slot * L.REC_STRIDE
            e.mem.w8(rec + 0x58, ack)
            e.mem.w8(rec + 0x59, earned)
            e.mem.w8(rec + 0xEE, 1)
            e.record_writes = True
            e.call(OPEN_INVENTORY, slot, level_up, max_steps=1_000_000)
            sent = [c for c in e.calls if c.target == SEND_MSG]
            if level_up:
                assert len(sent) == 1 and sent[0].site == 0x1C1814, sent
                buf, length = sent[0].args[1] & 0xFFFFFFFF, sent[0].args[2] & 0xFFFFFFFF
                body = bytes(e.mem.read(buf, length))
                assert length == 3 and body == bytes((9, slot, earned)), body
                assert e.mem.u8(rec + 0xED) == slot and e.mem.u8(rec + 0xEE) == 0
                assert e.mem.u32(0x4F4090) == 5 and e.mem.u8(0x4F65C8) == 1
            else:
                assert sent == [], sent
            assert all(w[1] != rec + 0x58 for w in e.writes)
            assert e.mem.u8(rec + 0x58) == ack and e.mem.u32(L.SEED) == seed
            count += 1
            # the message itself, through the original dispatcher
            d = EE(elf)
            d.mem.auto_map = True
            d.mem.w32(L.SEED, seed)
            d.follow = {DISPATCH}
            d.default_ret = 0
            d.mem.w8(rec + 0x58, ack)
            d.mem.w8(rec + 0x59, earned)
            msg = 0x1400000
            d.mem.write(msg, bytes((9, slot, earned, 0xA5)))
            d.record_writes = True
            d.call(DISPATCH, msg, max_steps=200_000)
            assert d.writes == [(0x1BFF6C, rec + 0x58, 1, (earned | 0xA500) & 0xFF)], d.writes
            assert d.mem.u8(rec + 0x59) == earned and d.mem.u32(L.SEED) == seed
            count += 1
        # inventory message 4 with levelUp re-sends message 9 for the panel's owner
        for panel_owner in (0, 1):
            e = EE(elf)
            e.mem.auto_map = True
            e.mem.w32(L.SEED, seed)
            e.follow = {JOIN_PANEL}
            e.default_ret = 0
            e.stub(IS_LOCAL, ret=1)
            rec = L.RECORD + panel_owner * L.REC_STRIDE
            other = L.RECORD + (1 - panel_owner) * L.REC_STRIDE
            e.mem.w8(rec + 0x58, 2)
            e.mem.w8(rec + 0x59, 9)
            e.mem.w8(other + 0x58, 3)
            e.mem.w8(other + 0x59, 4)
            e.mem.w32(0x4F4040 + 0x34, panel_owner)
            e.record_writes = True
            # the joining slot argument differs from the panel's owner word
            e.call(JOIN_PANEL, 0, 1 - panel_owner, 1, max_steps=1_000_000)
            sent = [c for c in e.calls if c.target == SEND_MSG]
            assert len(sent) == 1 and sent[0].site == 0x1C0478, sent
            body = bytes(e.mem.read(sent[0].args[1] & 0xFFFFFFFF, sent[0].args[2] & 0xFFFFFFFF))
            assert body == bytes((9, panel_owner, 9)), body
            assert e.mem.u8(rec + 0xED) == panel_owner and e.mem.u8(rec + 0xEE) == 0
            assert all(w[1] not in (rec + 0x58, other + 0x58) for w in e.writes)
            assert e.mem.u32(L.SEED) == seed
            count += 1
        # character creation: the record is cleared, then +0x59 and +0x58 get 1
        # (0x1b216c/0x1b2170, base +0x50 in $6, so the literal scan above misses it)
        e = EE(elf)
        e.mem.auto_map = True
        e.mem.w32(L.SEED, seed)
        e.follow = Follow({0x1B1D70})
        e.default_ret = 0
        e.mem.write(0x1400000, b'Hero\x00')
        e.mem.w8(L.RECORD + 0x58, 0x77)
        e.mem.w8(L.RECORD + 0x59, 0x77)
        e.record_writes = True
        e.call(0x1B1D70, 0, 0, 0x1400000, 0, 0, 0, 0xFFFFFFFF, 0, max_steps=5_000_000)
        byte58 = [(pc, value) for pc, addr, size, value in e.writes
                  if addr == L.RECORD + 0x58 and size == 1]
        assert byte58 == [(0x1B2170, 1)], byte58
        assert e.mem.u8(L.RECORD + 0x59) == 1 and e.mem.u32(L.SEED) == seed
        count += 1
        # import from the larger layout: both level bytes copied, each capped at 50
        for ack, earned in ((60, 45), (7, 51), (50, 50)):
            e = EE(elf)
            e.mem.auto_map = True
            e.mem.w32(L.SEED, seed)
            e.follow = Follow({0x1BD458})
            e.default_ret = 0
            src = 0x1400000
            e.mem.write(src, bytes(0x6000))
            e.mem.w8(src + 0x58, ack)
            e.mem.w8(src + 0x59, earned)
            e.record_writes = True
            e.call(0x1BD458, 1, src, max_steps=5_000_000)
            rec = L.RECORD + L.REC_STRIDE
            assert (e.mem.u8(rec + 0x58), e.mem.u8(rec + 0x59)) == (min(ack, 50), min(earned, 50))
            sites = sorted({pc for pc, addr, size, value in e.writes if addr == rec + 0x58})
            assert set(sites) <= {0x1BD520, 0x1BD528, 0x1BD57C}, [hex(p) for p in sites]
            assert e.mem.u32(L.SEED) == seed
            count += 1
        print('PASS seed %d: %d acknowledged-level writers executed (message 9 sends and '
              'store, creation, import)' % (seed, count))


# ---------------------------------------------------------------------------
# 7. save_load from its entry: header, camera, jump gates, players, quest
#    variables, act, difficulty, time, pending level; and load-screen step 4
# ---------------------------------------------------------------------------
SAVE_FOLLOW = Follow({SAVE_BUILD, SAVE_LOAD, 0x1EC0F0, 0x217D30, 0x217EDC, 0x203918, 0x203A20,
                      0x203210, 0x27DCF4, 0x27DD30, L.SNAPSHOT, L.FIXUP, L.PTR_TO_INDEX,
                      L.INDEX_TO_PTR, L.ENCODE, L.DECODE, 0x1ED974, VARS_CLEAR, VARS_SET,
                      0x2180A8, 0x217518, 0x1BF328})
CAMERA = 0x1500000


def save_world(e, seed, quest, share_flag):
    """State A: names, act table, camera, view words, players, quest variables."""
    m = e.mem
    m.write(0x41B721, b'hub\x00')
    m.write(0x41B771, b'west\x00')
    label, table = 0x1601000, 0x1602000
    m.write(label, b'hub\x00')
    m.write(table, struct.pack('<IHH', label, 0x2000, 0))
    m.w32(0x4F8E7C, 1)
    m.w32(0x4F8E10, 1)
    m.w32(0x4F8E48, table)
    m.w32(0x88D3D4, 0)
    m.w32(CAMERA_PTR, CAMERA)
    for off in range(0, 0x200, 4):
        m.w32(CAMERA + off, 0x3F800000 + off + seed)
    for off in range(0, 0x40, 4):
        m.w32(0x44F110 + off, 0x40000000 + off)
    m.w32(0x8E3A50, 0)
    m.w32(0x4F8400, 2)
    m.w32(0x4D8AE0, 2)
    m.w8(0x4F719C, 3)
    m.w32(0x88D414, 4321 + seed)
    for slot, pending in enumerate(((4, 6, 1234, 7, 9, 2, 1, 3), (1, 1, 0, 0, 3, 0xFF, 0, 5))):
        rec = L.RECORD + slot * L.REC_STRIDE
        for off, size, value in zip((0x58, 0x59, 0x5C, 0xE8, 0xEC, 0xED, 0xEE, 0x50),
                                    (1, 1, 4, 4, 1, 1, 1, 4), pending):
            m.write(rec + off, (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little'))
        m.w16(rec + 0x4B08, 0xFFFF)
        m.w32(rec + 0x43D8, 0)
    e.call(VARS_CLEAR, max_steps=2_000_000)
    for name, value in quest:
        m.write(0x1600000, name + b'\x00')
        e.call(VARS_SET, 0x1600000, value & 0xFFFFFFFF, max_steps=2_000_000)
    m.w32(0x4F85B4, share_flag)


def live_b(e):
    """State B: every restored field changed by direct stores (not handlers)."""
    m = e.mem
    for off in range(0, 0x200, 4):
        m.w32(CAMERA + off, 0x11111111)
    for off in range(0, 0x40, 4):
        m.w32(0x44F110 + off, 0x22222222)
    m.w32(0x4F8400, 9)
    m.w32(0x4D8AE0, 1)
    m.w8(0x4F719C, 0)
    m.w32(0x88D414, 1)
    for slot in range(2):
        rec = L.RECORD + slot * L.REC_STRIDE
        for off in (0x58, 0x59, 0xEC, 0xED, 0xEE):
            m.w8(rec + off, 0x55)
        m.w32(rec + 0x5C, 0)
        m.w32(rec + 0xE8, 0)
    m.w32(0x88D3D4, 1)
    m.w8(0x8E1AD6, 0)
    m.w8(0x41B720, 0)
    m.w32(0x88D40C, 0)
    m.write(0x41B6D0, b'\x00')
    m.write(0x8E1A98, b'\x00')


def restored(e, image, seed, share_flag, quest):
    m = e.mem
    assert bytes(m.read(HEADER_COPY, 0x70)) == image[:0x70]
    assert m.u8(0x8E1AD6) == 1 and m.u8(0x41B720) == 0xFD and m.u32(0x88D40C) == 99
    assert m.cstr(0x41B6D0) == 'hub_west' and m.cstr(0x8E1A98) == 'hub_west'
    assert m.cstr(0x41B721) == 'hub'                 # the live level name is not replaced
    assert m.u8(0x4F719C) == 3 and m.u32(0x88D414) == 4321 + seed
    assert m.u32(0x4F8400) == 2 and m.u32(0x4D8AE0) == 2 and m.u32(0x88D3D4) == 0
    view = [off for off in range(0, 0x40, 4) if m.u32(0x44F110 + off) == 0x40000000 + off]
    assert view == list(range(0, 0x34, 4)), [hex(o) for o in view]   # 13 words come back
    cam = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF) for c in e.calls
           if c.target == 0x203A20]
    assert cam == [(0x221E74, CAMERA, SAVE_BUFFER + 0x70)], cam
    gates = [(c.site, c.args[0] & 0xFFFFFFFF) for c in e.calls if c.target == 0x27DD30]
    assert gates == [(0x221E80, SAVE_BUFFER + 0x70 + 0xC4)], gates
    fixups = [(c.site, c.args[0] & 0xFFFFFFFF) for c in e.calls if c.target == L.FIXUP]
    assert fixups == [(0x22201C, 0), (0x22201C, 1)], fixups
    quest_sets = [c.site for c in e.calls if c.target == VARS_SET]
    assert quest_sets == [0x222098] * len(quest), quest_sets
    rec0 = L.field_bytes(e, L.RECORD)
    rec1 = L.field_bytes(e, L.RECORD + L.REC_STRIDE)
    assert rec0 == (4, 6, 1234, 7, 9, 2, 1, 3), rec0
    assert rec1 == (1, 1, 0, 0, 3, 0xFF, 0, 5), rec1
    shared = [c for c in e.calls if c.target == SHARE_QUEST]
    if share_flag == 1:
        assert [(c.site, c.args[0] & 0xFFFFFFFF) for c in shared] == [(0x2221AC, 0)]
        assert m.u32(0x4F85B4) == 0
    else:
        assert shared == [] and m.u32(0x4F85B4) == share_flag
    assert [c.site for c in e.calls if c.target == CLEAR_DEFERRED] == [0x222074]
    assert m.u32(L.SEED) == seed


def quest_section(image):
    out, off = [], QUEST_OFF
    while image[off]:
        name = image[off:off + 0x20].split(b'\x00')[0]
        out.append((name, struct.unpack('<i', image[off + 0x20:off + 0x24])[0]))
        off += 0x24
    return out


def save_round_trip(elf):
    quest = ((b'r3alpha', 11), (b'r3beta', -5), (b'r3big', 200))
    for seed in SEEDS:
        count = 0
        for share_flag in (0, 1, 2):
            e = EE(elf)
            e.mem.auto_map = True
            e.mem.w32(L.SEED, seed)
            e.follow = SAVE_FOLLOW
            e.default_ret = 0
            save_world(e, seed, quest, share_flag)
            e.reset_log()
            e.call(SAVE_BUILD, 0, 0, max_steps=5_000_000)
            assert [c.site for c in e.calls if c.target == STORE_LEVEL] == [0x221D28]
            image = bytes(e.mem.read(SAVE_BUFFER, IMAGE_BYTES))
            saved_vars = quest_section(image)
            assert saved_vars == [(b'r3alpha', 11), (b'r3beta', -5), (b'r3big', 127)], saved_vars
            live_b(e)
            e.call(VARS_CLEAR, max_steps=2_000_000)
            e.mem.write(0x1600000, b'r3late\x00')
            e.call(VARS_SET, 0x1600000, 99, max_steps=2_000_000)
            e.mem.w32(0x4F85B4, share_flag)
            e.reset_log()
            e.call(SAVE_LOAD, max_steps=5_000_000)
            restored(e, image, seed, share_flag, quest)
            stubbed = sorted({c.target for c in e.calls if c.stubbed})
            assert stubbed == sorted({0x207308, 0x207310, 0x207318, 0x2035C8, CLEAR_DEFERRED}
                                     | ({SHARE_QUEST} if share_flag == 1 else set())), \
                [hex(s) for s in stubbed]
            e.reset_log()
            e.call(SAVE_BUILD, 0, 0, max_steps=5_000_000)
            again = bytes(e.mem.read(SAVE_BUFFER, QUEST_OFF))
            assert again == image[:QUEST_OFF], [hex(i) for i in range(QUEST_OFF)
                                                if again[i] != image[i]][:8]
            # a variable made after the save keeps its name and reads 0 after the load
            assert quest_section(bytes(e.mem.read(SAVE_BUFFER, IMAGE_BYTES))) == \
                saved_vars + [(b'r3late', 0)]
            assert e.mem.u32(L.SEED) == seed
            count += 1
            # the same image through load-screen step 4 (card read already finished)
            s = EE(elf)
            s.mem.auto_map = True
            s.mem.w32(L.SEED, seed)
            s.follow = Follow(SAVE_FOLLOW.addresses, {LOAD_SCREEN})
            s.default_ret = 0
            save_world(s, seed, quest, share_flag)
            live_b(s)
            s.call(VARS_CLEAR, max_steps=2_000_000)
            buf = 0x1700000
            s.mem.write(buf, image)
            m = s.mem
            m.w32(0x88D3E4, 1)
            m.w32(0x88D3D8, 1)
            m.w32(0x88D3A8, 4)
            m.w32(0x88D3A0, 4)
            m.w32(0x88D3BC, 0)
            m.w32(0x4F8EEC, buf)
            m.w8(0x8E1AB9, 1)
            m.w8(0x4F8F28, 0xA5)
            m.w32(0x41BFB8, 0x20)
            m.w32(0x41BFBC, 0x40)
            s.reset_log()
            s.call(LOAD_SCREEN, max_steps=5_000_000)
            assert [c.site for c in s.calls if c.target == SAVE_LOAD] == [0x219830]
            assert bytes(m.read(SAVE_BUFFER, IMAGE_BYTES)) == image
            restored(s, image, seed, share_flag, quest)
            count += 1
        print('PASS seed %d: %d save_load runs from the entry (direct and load-screen step 4)'
              % (seed, count))


def main(argv):
    elf = argv[1] if len(argv) > 1 else 'local/SLUS_209.73'
    with open(elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == L.EXPECTED_SHA256, 'wrong executable'
    skill_rows(elf)
    passive_rows(elf)
    box_edges(elf)
    stat_rows(elf)
    spend_downstream(elf)
    ack_writers(elf)
    save_round_trip(elf)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
