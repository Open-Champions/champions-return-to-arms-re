#!/usr/bin/env python3
"""Bounded original-code probes for level-up gates.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_levelup.py /path/to/SLUS_209.73

Screens and save helpers run in ee_emu with constructed state and stubbed
draw/audio callees. This verifies calls and record bytes, not pixels or a console.
"""
import hashlib
import os
import struct
import sys

from ee_emu import EE


EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SCREEN = 0x1D1DB8
SENDER = 0x1C5780
RECORD = 0x4D8AF0


def original_sends(elf, seed, *, slot=0, page=2, edge=0x40, cursor=0, panel_state=0,
                   half=0, points=3, elapsed=3000):
    ee = EE(elf)
    ee.mem.auto_map = True
    ee.follow = set()  # run the screen, stub unrelated presentation callees
    ee.default_ret = 0
    ee.mem.w32(0x404464, seed)
    ee.mem.w32(0x44FDA4, elapsed)
    ee.mem.w32(0x4F65EC, slot)    # owner pad index and sender slot
    ee.mem.w32(0x4F65CC, panel_state)
    ee.mem.w32(0x4F65D0, cursor)
    ee.mem.w32(0x41BFE8 + 88 * slot, edge)  # indexed pad edge word
    ee.mem.w8(RECORD + 0x4C30 * slot + 0xEE, half)
    ee.mem.w8(RECORD + 0x4C30 * slot + 0xEC, points)
    ee.call(SCREEN, 0, page, 0, 0x4F4040, max_steps=1_000_000)
    assert ee.mem.u32(0x404464) == seed
    return [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
            for c in ee.calls if c.target == SENDER]


def main(argv):
    elf = argv[1] if len(argv) > 1 else os.path.expanduser('~/champions-re/SLUS_209.73')
    with open(elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable'
    cases = [(dict(cursor=i), [(site, 0, i)]) for i, site in enumerate(
        (0x1D24D4, 0x1D24F4, 0x1D2510, 0x1D252C))]
    cases += [
        (dict(cursor=4), []), (dict(page=0), []), (dict(page=3), []),
        (dict(edge=0), []), (dict(edge=0x10), []),
        (dict(panel_state=1), []), (dict(half=1), []),
        (dict(elapsed=2999), []),
        (dict(elapsed=3000), [(0x1D24D4, 0, 0)]),
        (dict(points=0), [(0x1D24D4, 0, 0)]),
        (dict(slot=1, cursor=2), [(0x1D2510, 1, 2)]),
    ]
    for seed in (20973, 7):
        for options, want in cases:
            got = original_sends(elf, seed, **options)
            assert got == want, (seed, options, got, want)
        print('PASS seed %d: %d stat-point sender gates' % (seed, len(cases)))
    skill_gates(elf)
    progression(elf)
    save_restore(elf)
    return 0


SKILL_SCREEN = 0x1D4660
SKILL_SENDER = 0x1C57B8
GIVE_EXP = 0x1D3150
RECALC = 0x1B6458
RANK = 0x1BF330
PASSIVE = 0x1BED48
STRCMP = 0x3B8534
STRCPY = 0x3B868C
CLASS_SKILLS = 0x1AC7A8
RES_FIND = 0x17365C
VIRT = 0x180000
EXP_TABLE = 0x41B558
TREES = (0x4F4898, 0x4F4E38, 0x4F4B68, 0x4F5108, 0x4F53D8, 0x4F5720, 0x4F5A18)
SKILL_TABLE = 0x41B170
PASSIVE_RUNTIME = 0x4EF510
PASSIVE_MASKS = 0x4EF538
PANEL = 0x4F4040
GATE = 0x4F4878
PAD_BASE = 0x4028D0
SAVED = 0x879EC0
NUM_PLAYERS = 0x4D8AE0
SNAPSHOT = 0x216C80
FIXUP = 0x216EA8
PTR_TO_INDEX = 0x216BF8
INDEX_TO_PTR = 0x216E10
ENCODE = 0x107EA4
DECODE = 0x107EC0
SEED = 0x404464
REC_STRIDE = 0x4C30


def s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def s8(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def boot(elf, seed):
    ee = EE(elf)
    ee.mem.auto_map = True
    ee.record_writes = False
    ee.mem.w32(SEED, seed)
    return ee


def tree_row(ee, cls, index):
    addr = TREES[cls] + index * 0x28
    return {
        'kind': ee.mem.u8(addr),
        'need': ee.mem.s8(addr + 1),
        'ident': ee.mem.u64(addr + 8),
        'pre_kind': ee.mem.s32(addr + 0x10),
        'pre': ee.mem.u64(addr + 0x18),
        'x': ee.mem.s32(addr + 0x20),
        'y': ee.mem.s32(addr + 0x24),
    }


def put_ranks(ee, slot, pairs):
    addr = RECORD + slot * REC_STRIDE + 0x4B08
    for index, (skill_id, rank) in enumerate(pairs):
        ee.mem.w16(addr + index * 4, skill_id)
        ee.mem.w16(addr + index * 4 + 2, rank)
    ee.mem.w16(addr + len(pairs) * 4, 0xFFFF)


def plant_skill(ee, skill_id):
    obj, vt = 0x200000, 0x200100
    ee.mem.w32(obj + 0x60, vt)
    for off in (0x10, 0x18, 0x20, 0x28, 0x30, 0x38):
        ee.mem.w16(vt + off, 0)
        ee.mem.w32(vt + off + 4, VIRT)
    ee.mem.w32(SKILL_TABLE + skill_id * 4, obj)


def skill_sends(elf, seed, *, cls=0, node=0, slot=0, edge=0x40, held=0, points=1,
                ranks=(), ack=20, earned=20, half=0, page=5, gate=0, panel30=0,
                mana=10.0, mana_cost=0.0, resource=True, aim=True, init=True,
                end_table=False, passive_rank=None, passive_masks=()):
    ee = boot(elf, seed)
    ee.follow = {RANK, PASSIVE, STRCMP, STRCPY, CLASS_SKILLS}
    ee.default_ret = 0
    ee.stub(RES_FIND, ret=1 if resource else 0)

    def virt(emu, cost=mana_cost):
        emu.fset(0, cost)
        return 0

    ee.stub(VIRT, function=virt)
    if init:
        ee.call(CLASS_SKILLS, max_steps=2_000_000)
        ee.reset_log()
    if end_table:
        ee.mem.write(PASSIVE_RUNTIME + cls * 0xA88, b'END\x00')
    row = tree_row(ee, cls, node)
    if passive_rank is not None:
        base = PASSIVE_MASKS + cls * 0xA88
        found = None
        for index in range(48):
            if ee.mem.u64(base + index * 0x38) == row['ident']:
                found = index
                break
        assert found is not None, row['ident']
        ee.mem.w8(RECORD + slot * REC_STRIDE + 0xEF + found, passive_rank)
    for mask, level in passive_masks:
        base = PASSIVE_MASKS + cls * 0xA88
        found = None
        for index in range(48):
            if ee.mem.u64(base + index * 0x38) == mask:
                found = index
                break
        assert found is not None, (cls, mask)
        ee.mem.w8(RECORD + slot * REC_STRIDE + 0xEF + found, level)
    rec = RECORD + slot * REC_STRIDE
    ee.mem.w32(rec + 0x50, cls)
    ee.mem.w8(rec + 0x58, ack)
    ee.mem.w8(rec + 0x59, earned)
    ee.mem.w32(rec + 0xE8, points & 0xFFFFFFFF)
    ee.mem.w8(rec + 0xEE, half)
    ee.mem.wf32(rec + 0xC4, mana)
    put_ranks(ee, slot, ranks)
    if row['kind'] != 0:
        plant_skill(ee, row['ident'] & 0xFFFFFFFF)
    pad = PAD_BASE + 88 * slot
    ee.mem.w32(pad + 8, held)
    ee.mem.w32(pad + 0xC, edge)
    ee.mem.w32(0x4F65EC, slot)
    ee.mem.w32(PANEL + 0x30, panel30)
    ee.mem.w32(PANEL + 0x50, page)
    ee.mem.w32(GATE, gate)
    if aim:
        ee.mem.wf32(PANEL + 0x44, row['x'] + 1)
        ee.mem.wf32(PANEL + 0x48, row['y'] + 0x9E + 1)
    else:
        ee.mem.wf32(PANEL + 0x44, -1000.0)
        ee.mem.wf32(PANEL + 0x48, -1000.0)
    ee.call(SKILL_SCREEN, 0, max_steps=5_000_000)
    assert ee.mem.u32(SEED) == seed
    sends = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF,
              c.args[2] & 0xFFFFFFFF) for c in ee.calls if c.target == SKILL_SENDER]
    recalc = [c.site for c in ee.calls if c.target == RECALC]
    return sends, recalc, row


def expect_send(row, slot):
    kind = 0 if row['kind'] == 0 else 1
    site = 0x1D580C if kind == 0 else 0x1D58DC
    return [(site, slot, kind, row['ident'] & 0xFFFFFFFF)]


def skill_gates(elf):
    # (options, 'send' or 'none', whether recalc should run)
    cases = [
        (dict(cls=0, node=0, ack=1), 'send', True),
        (dict(cls=0, node=2, ranks=((60, 1),), ack=3), 'send', True),
        (dict(cls=0, node=0, ack=1, edge=0), 'none', False),
        (dict(cls=0, node=0, ack=1, edge=0x10), 'none', False),
        (dict(cls=0, node=0, ack=1, aim=False), 'none', False),
        (dict(cls=0, node=0, ack=1, points=0), 'none', True),
        (dict(cls=0, node=0, ack=1, points=-1), 'none', True),
        (dict(cls=0, node=0, ack=30, ranks=((60, 20),)), 'none', False),
        (dict(cls=0, node=0, ack=30, ranks=((60, 19),)), 'send', True),
        (dict(cls=0, node=0, ack=0, earned=40), 'none', False),
        (dict(cls=0, node=0, ack=1, earned=1), 'send', True),
        (dict(cls=0, node=0, ack=1, mana=10.0, mana_cost=10.0), 'send', True),
        (dict(cls=0, node=0, ack=1, mana=10.0, mana_cost=11.0), 'none', True),
        (dict(cls=0, node=0, ack=1, half=1), 'send', True),
        (dict(cls=0, node=0, ack=1, page=5, held=2), 'none', False),
        (dict(cls=0, node=0, ack=1, page=0, held=2, gate=0), 'send', True),
        (dict(cls=0, node=0, ack=1, page=0, gate=1), 'none', False),
        (dict(cls=0, node=0, ack=1, page=5, held=2, panel30=1, gate=0), 'send', True),
        (dict(cls=0, node=0, ack=1, resource=False), 'none', False),
        (dict(cls=2, node=6, ranks=((0x3B, 1),), ack=8), 'send', True),
        (dict(cls=2, node=6, ack=8), 'none', False),
        (dict(cls=0, node=3, ranks=((61, 1),), ack=3), 'send', True),
        (dict(cls=0, node=3, ack=3), 'none', False),
        (dict(cls=0, node=0, ack=1, slot=1), 'send', True),
        (dict(cls=0, node=2, ranks=((60, 1),), ack=30, passive_rank=20), 'none', False),
        (dict(cls=0, node=0, ack=1, end_table=True), 'none', False),
        (dict(cls=0, node=3, ranks=((60, 1),), ack=3), 'send', True),
        (dict(cls=3, node=3, ranks=((0x30, 1),), ack=10), 'send', True),
        (dict(cls=3, node=3, ack=10), 'none', False),
        (dict(cls=3, node=14, ranks=((0x2F, 1),), ack=21), 'send', True),
        (dict(cls=3, node=14, ack=21), 'none', False),
        (dict(cls=4, node=10, ranks=((1, 1),), ack=15), 'send', True),
        (dict(cls=4, node=10, ack=15), 'none', False),
        (dict(cls=3, node=5, ranks=((0x3D, 1),), ack=8), 'send', True),
        (dict(cls=3, node=5, ack=8), 'none', False),
        (dict(cls=2, node=14, ranks=((0x28, 1),), ack=22), 'send', True),
        (dict(cls=2, node=14, ack=22), 'none', False),
        (dict(cls=2, node=13, ranks=((0xB, 1),), ack=20), 'send', True),
        (dict(cls=2, node=13, ack=20), 'none', False),
        (dict(cls=1, node=4, passive_masks=((0x40, 1),), ack=8), 'none', False),
    ]
    for seed in (20973, 7):
        for options, mode, want_recalc in cases:
            sends, recalc, row = skill_sends(elf, seed, **options)
            want = expect_send(row, options.get('slot', 0)) if mode == 'send' else []
            assert sends == want, (seed, options, sends, want)
            assert bool(recalc) == want_recalc, (seed, options, recalc)
            if want_recalc:
                assert recalc == [0x1D5950], (seed, options, recalc)
        print('PASS seed %d: %d skill-point sender gates' % (seed, len(cases)))


def table(ee):
    return [ee.mem.s32(EXP_TABLE + 4 * i) for i in range(81)]


def skill_for(old):
    old = s8(old)
    if old < 6:
        return 1
    if old < 16:
        return 2
    if old < 26:
        return 3
    if old < 36:
        return 4
    return 5


def predict(levels, level, exp, amount, skill, stat, alive, max_hp, max_mana, mana):
    added = s32(s32(exp) + amount)
    ceiling = s32(levels[80] - 1)
    if ceiling < added:
        added = ceiling
    while levels[s8(level)] <= added:
        skill = s32(skill + skill_for(level))
        stat = (stat + 3) & 0xFF
        level = s8(s8(level) + 1)
        if alive:
            max_hp = max_hp
            mana = max_mana
    return level, added, skill, stat, mana


def run_give(elf, seed, *, cls=0, level=5, exp=None, amount=0, hp=1.0, max_hp=40.0,
             mana=3.0, max_mana=9.0, stat=0, skill=0, ack=2):
    ee = boot(elf, seed)
    ee.follow = {RECALC}
    ee.default_ret = 0
    ee.mem.w32(NUM_PLAYERS, 1)
    levels = table(ee)
    if exp is None:
        exp = levels[level]
    rec = RECORD
    ee.mem.w32(rec + 0x50, cls)
    ee.mem.w8(rec + 0x58, ack)
    ee.mem.w8(rec + 0x59, level)
    ee.mem.w32(rec + 0x5C, exp & 0xFFFFFFFF)
    ee.mem.w32(rec + 0xE8, skill & 0xFFFFFFFF)
    ee.mem.w8(rec + 0xEC, stat)
    ee.mem.wf32(rec + 0xAC, hp)
    ee.mem.wf32(rec + 0xB0, max_hp)
    ee.mem.wf32(rec + 0xC0, mana)
    ee.mem.wf32(rec + 0xC4, max_mana)
    ee.mem.w32(rec + 0x43D8, 0)
    ee.call(GIVE_EXP, 0, amount & 0xFFFFFFFF, max_steps=2_000_000)
    assert ee.mem.u32(SEED) == seed
    alive = hp > 0.0
    want_level, want_exp, want_skill, want_stat, want_mana = predict(
        levels, level, exp, amount, skill, stat, alive, max_hp, max_mana, mana)
    got = (ee.mem.s8(rec + 0x59), ee.mem.s32(rec + 0x5C), ee.mem.s32(rec + 0xE8),
           ee.mem.u8(rec + 0xEC), ee.mem.u32(rec + 0xC0), ee.mem.s8(rec + 0x58))
    want_mana_bits = struct.unpack('<I', struct.pack('<f', want_mana))[0]
    want = (want_level, want_exp, want_skill, want_stat, want_mana_bits, ack)
    assert got == want, (seed, cls, level, amount, got, want)
    hp_bits = struct.unpack('<I', struct.pack('<f', hp))[0]
    if alive and want_level != s8(level):
        assert ee.mem.u32(rec + 0xAC) == ee.mem.u32(rec + 0xB0)
    else:
        assert ee.mem.u32(rec + 0xAC) == hp_bits
    return got


def progression(elf):
    bands = (1, 5, 6, 15, 16, 25, 26, 35, 36, 79)
    for seed in (20973, 7):
        count = 0
        for level in bands:
            run_give(elf, seed, level=level, amount=0)
            count += 1
            below = run_give(elf, seed, level=level, exp=None, amount=-1)
            # amount -1 from the exact threshold stays below when the step is 1 or more
            count += 1
        # exact threshold grants; one below does not; the band is the old level
        ee = boot(elf, seed)
        levels = table(ee)
        for level, grant in ((5, 1), (6, 2), (15, 2), (16, 3), (25, 3), (26, 4),
                             (35, 4), (36, 5), (79, 5)):
            stayed = run_give(elf, seed, level=level, exp=levels[level] - 1, amount=0)
            assert stayed[0] == level and stayed[2] == 0 and stayed[3] == 0, stayed
            gained = run_give(elf, seed, level=level, exp=levels[level] - 1, amount=1)
            assert gained[0] == s8(level + 1) and gained[2] == grant and gained[3] == 3, (
                level, grant, gained)
            count += 2
        multi = run_give(elf, seed, level=5, exp=levels[7], amount=0, stat=1, skill=4)
        assert multi[0] == 8 and multi[2] == 4 + 1 + 2 + 2 and multi[3] == (1 + 9) & 0xFF, multi
        wrapped = run_give(elf, seed, level=5, exp=levels[5], amount=0, stat=254)
        assert wrapped[3] == 1, wrapped
        dead = run_give(elf, seed, level=5, exp=levels[5], amount=0, hp=0.0, mana=3.0)
        assert dead[4] == struct.unpack('<I', struct.pack('<f', 3.0))[0], dead
        count += 3
        first = None
        for cls in range(7):
            got = run_give(elf, seed, cls=cls, level=16, exp=levels[16] - 1, amount=1)
            if first is None:
                first = got
            assert got == first, (cls, got, first)
            count += 1
        print('PASS seed %d: %d level-grant cases' % (seed, count))


def field_bytes(ee, addr):
    return (ee.mem.u8(addr + 0x58), ee.mem.u8(addr + 0x59), ee.mem.s32(addr + 0x5C),
            ee.mem.s32(addr + 0xE8), ee.mem.u8(addr + 0xEC), ee.mem.u8(addr + 0xED),
            ee.mem.u8(addr + 0xEE), ee.mem.s32(addr + 0x50))


def save_restore(elf):
    pending = (4, 6, 123456, 7, 9, 2, 1, 3)
    for seed in (20973, 7):
        for slot in (0, 1):
            ee = boot(elf, seed)
            ee.follow = {FIXUP, PTR_TO_INDEX, INDEX_TO_PTR, ENCODE, DECODE}
            ee.default_ret = 0
            rec = RECORD + slot * REC_STRIDE
            ee.mem.w8(rec + 0x58, pending[0])
            ee.mem.w8(rec + 0x59, pending[1])
            ee.mem.w32(rec + 0x5C, pending[2])
            ee.mem.w32(rec + 0xE8, pending[3])
            ee.mem.w8(rec + 0xEC, pending[4])
            ee.mem.w8(rec + 0xED, pending[5])
            ee.mem.w8(rec + 0xEE, pending[6])
            ee.mem.w32(rec + 0x50, pending[7])
            ee.mem.w16(rec + 0x4B08, 0xFFFF)
            ee.mem.w32(rec + 0x43D8, 0x11111111)
            ee.call(SNAPSHOT, slot, max_steps=2_000_000)
            saved = SAVED + slot * REC_STRIDE
            assert field_bytes(ee, saved) == pending, (seed, slot, field_bytes(ee, saved))
            assert ee.mem.u32(saved + 0x43D8) == 0x11111111
            assert ee.mem.s32(saved + 0x43F0) == -1
            assert all(c.target != GIVE_EXP for c in ee.calls)
            assert ee.mem.u32(SEED) == seed
        ee = boot(elf, seed)
        ee.follow = {FIXUP, PTR_TO_INDEX, INDEX_TO_PTR, ENCODE, DECODE}
        ee.default_ret = 0
        rec = RECORD
        ee.mem.w8(rec + 0x58, pending[0])
        ee.mem.w8(rec + 0x59, pending[1])
        ee.mem.w32(rec + 0x5C, pending[2])
        ee.mem.w32(rec + 0xE8, pending[3])
        ee.mem.w8(rec + 0xEC, pending[4])
        ee.mem.w8(rec + 0xED, pending[5])
        ee.mem.w8(rec + 0xEE, pending[6])
        ee.mem.w32(rec + 0x50, pending[7])
        ee.mem.w16(rec + 0x4B08, 0xFFFF)
        ee.mem.w32(rec + 0x43D8, 0x11111111)
        ee.call(SNAPSHOT, 0, max_steps=2_000_000)
        image = ee.mem.read(SAVED, REC_STRIDE)
        ee.mem.w8(rec + 0x58, 1)
        ee.mem.w8(rec + 0x59, 1)
        ee.mem.w32(rec + 0x5C, 1)
        ee.mem.w32(rec + 0xE8, 0)
        ee.mem.w8(rec + 0xEC, 0)
        ee.mem.w8(rec + 0xEE, 0)
        ee.mem.w32(rec + 0x43D8, 0)
        buf = 0x1400000
        ee.mem.write(buf, bytes(14) + image)
        ee.mem.w32(NUM_PLAYERS, 1)
        ee.r[16] = buf
        ee.r[17] = 0
        ee.r[18] = 0
        ee.r[19] = 0x4E0000
        ee.r[21] = 0x4E0000
        ee.r[29] = ee.stack_hi - 0x200
        ee.reset_log()
        reason = ee.run(start=0x221EC0, until={0x222050}, max_steps=2_000_000)
        assert reason == 'stop', reason
        assert field_bytes(ee, rec) == pending, field_bytes(ee, rec)
        assert ee.mem.u32(rec + 0x43D8) == 0
        assert ee.mem.u32(rec + 0x43F0) == 0
        assert all(c.target != GIVE_EXP for c in ee.calls)
        assert ee.mem.u32(SEED) == seed
        print('PASS seed %d: pending level-up snapshot and restore' % seed)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
