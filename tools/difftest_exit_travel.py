#!/usr/bin/env python3
"""Counts-only EE comparisons for one level-to-level transition.

python3 -m tools.difftest_exit_travel --seed 20973
Original act lookup, qualified-name, departure directory and load sequencing
run in tools/ee_emu.py. World construction, menus, script bodies and the
loading-screen thread are supplied or not entered.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import random
import sys
import unittest  # Preload before tools/dis.py can shadow the standard library.

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE, float_to_raw
import ref_exit_travel as R

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PENDING, ORIENT, LEVEL, SUB = 0x41B6D0, 0x41B720, 0x41B721, 0x41B771
PREV, SAVED_ORIENT, TEX = 0x41B7C2, 0x41B7C1, 0x44FE18
ACT, CARD, FLAG, FORCED = 0x88D3D4, 0x88D3A0, 0x44FE08, 0x4F85C5
FRONTEND, LATCH, LOADED, RANK = 0x41B510, 0x4F8F28, 0x4F85B0, 0x4F7108
PVP, PLAYERS, SPAWN, RECALL = 0x4F7120, 0x4D8AE0, 0x4F70D0, 0x41B520
RECALL_FLAG, RECALL_LEG = 0x41B51C, 0x41B51E
FACING, RECORD, STRIDE = 0x4F8410, 0x4D8AF0, 0x4C30
HP_OFF, RECALL_OFF = 0xAC, 0x24
MEDAL, MEDAL_SLOT, MEDAL_SAVE = 0x4F713C, 0x4F7148, 0x4F85C0
ACT_MARK, IDLE, VOICE, VOICE_DELAY = 0x4F7118, 0x506054, 0x505B00, 0x506058
QUEST, DIRECTORY, DATA = 0x86DA80, 0x8AB590, 0x8AB698
FIND_ACT, ACT_CHANGED, SET_ACT = 0x217D30, 0x217F70, 0x2180A8
QUALIFIED, STORE, WRITE = 0x1EC0F0, 0x21777C, 0x218600
LOAD = 0x320EDC
ENTRY = 0x18


class Probe:
    def __init__(self, elf):
        self.ee = EE(elf)
        self.mem = self.ee.mem
        self.counts = Counter()
        self.rows, self.row_counts = R.load_acts(elf)
        for addr, size in ((0x41B500, 0x400), (0x44FE00, 0x40), (0x4D8A00, 0x4C30 * 4),
                           (0x4F7000, 0x200), (0x4F8400, 0x200), (0x505000, 0x200),
                           (0x86DA00, 0x100), (0x88D000, 0x800), (0x8AB500, 0x400)):
            self.mem.map(addr, size)

    def equal(self, got, want):
        assert got == want, 'comparison mismatch_count=1'
        self.counts['assertions'] += 1

    def call(self, address, *args):
        self.ee.reset_log()
        result = self.ee.call(address, *args, max_steps=100000)
        self.equal((len(self.ee.patches), self.mem.auto_map,
                    len(self.mem.auto_mapped)), (0, False, 0))
        self.counts['entry_calls'] += 1
        return result

    def put(self, addr, text):
        self.mem.write(addr, text.encode('ascii') + b'\0')

    def targets(self, address):
        return [c for c in self.ee.calls if c.target == address]


def signed(value):
    if value & (1 << 63):
        return value - (1 << 64)
    return value


def acts(elf):
    p = Probe(elf)
    # found, stored act, changed flag. Current act is searched before act 0.
    samples = (
        (-1, 'strife', 0, 0, 1),
        (0, 'strife', 0, 0, 0),
        (6, 'hub', 6, 6, 0),
        (-1, 'hub2', 0, 0, 1),
        (-1, 'storm1a', 8, 8, 1),
        (8, 'storm1a', 8, 8, 0),
        (12, 'strife', 0, 0, 1),
        (5, 'honor', 6, 6, 1),
        (-1, 'SYN_NO_LEVEL', -1, -1, 0),
        (4, 'SYN_NO_LEVEL', -1, 4, 0),
    )
    for current, name, found_want, stored_want, flag_want in samples:
        p.mem.w32(ACT, current & 0xFFFFFFFF)
        addr = p.ee.alloc(len(name) + 1)
        p.put(addr, name)
        found = signed(p.call(FIND_ACT, addr))
        p.equal(found, R.find_act(p.rows, current, name))
        p.equal(found, found_want)
        p.mem.w32(ACT, current & 0xFFFFFFFF)
        changed = p.call(ACT_CHANGED, addr)
        new_act, flag = R.act_change(p.rows, current, name)
        stored = p.mem.s32(ACT)
        p.equal((changed, stored), (flag, new_act))
        p.equal((changed, stored), (flag_want, stored_want))
        p.equal(SET_ACT in [c.target for c in p.ee.calls], bool(flag_want))
        p.counts['act_cases'] += 1
    return p.counts


def names(elf):
    p = Probe(elf)
    buf = p.ee.alloc(64)
    for level, sub in (('', ''), ('SYN_A', ''), ('', 'SYN_B'), ('SYN_A', 'SYN_B')):
        p.mem.write(LEVEL, b'\0' * 0x80)
        p.put(LEVEL, level)
        p.put(SUB, sub)
        p.mem.write(buf, b'\x5a' * 64)
        p.call(QUALIFIED, buf)
        p.equal(p.mem.cstr(buf), R.qualified_name(level, sub))
        p.equal(sum(c.stubbed for c in p.ee.calls), 0)
        p.counts['name_cases'] += 1
    return p.counts


def _clear_dir(mem):
    mem.write(DIRECTORY, b'\0' * (11 * ENTRY))


def _read_dir(mem):
    out = []
    for index in range(11):
        base = DIRECTORY + index * ENTRY
        if mem.u8(base) == 0:
            break
        out.append((mem.cstr(base), mem.u32(base + 0x14)))
    return tuple(out)


def departures(elf):
    p = Probe(elf)
    written = []
    p.ee.stub(WRITE, function=lambda ee: written.append(ee.r[4] & 0xFFFFFFFF) or 0)
    cases = []
    # card 4 and the level flag skip before any directory change.
    cases.append(dict(name='strife', act=0, card=4, flag=0, forced=0,
                       prior=(), size=None))
    cases.append(dict(name='strife', act=0, card=0, flag=0x800, forced=0,
                       prior=(), size=None))
    cases.append(dict(name='hub', act=0, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='hub2', act=5, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='strife', act=0, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='storm1a', act=8, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='strife', act=5, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='SYN_NO_LEVEL', act=0, card=0, flag=0, forced=0, prior=()))
    cases.append(dict(name='strife', act=0, card=0, flag=0, forced=1, prior=()))
    cases.append(dict(name='SYN_NO_LEVEL', act=0, card=0, flag=0, forced=1, prior=()))
    cases.append(dict(name='strife', act=0, card=0, flag=0, forced=0,
                       prior=(('hub', 15000),)))
    cases.append(dict(name='hub', act=0, card=0, flag=0, forced=0,
                       prior=(('hub', 100),)))
    cases.append(dict(name='hub', act=0, card=0, flag=0, forced=0,
                       prior=(('hub', 220000),)))
    cases.append(dict(name='hub', act=0, card=0, flag=0, forced=0,
                       prior=(('hub', 220001),)))
    full = tuple(('SYN_K%d' % i, 1) for i in range(10))
    cases.append(dict(name='strife', act=0, card=0, flag=0, forced=0, prior=full))
    for case in cases:
        _clear_dir(p.mem)
        for index, (key, size) in enumerate(case['prior']):
            p.put(DIRECTORY + index * ENTRY, key)
            p.mem.w32(DIRECTORY + index * ENTRY + 0x14, size)
        p.mem.w32(ACT, case['act'])
        p.mem.w32(CARD, case['card'])
        p.mem.w32(FLAG, case['flag'])
        p.mem.w8(FORCED, case['forced'])
        addr = p.ee.alloc(len(case['name']) + 1)
        p.put(addr, case['name'])
        written.clear()
        p.equal(p.call(STORE, addr), 0)
        size = None if case['card'] == 4 or case['flag'] & 0x800 else R.store_size(
            p.rows, case['act'], case['name'], case['forced'])
        if size is None:
            p.equal(_read_dir(p.mem), case['prior'])
            p.equal(written, [])
        else:
            entries, offset = R.store_directory(case['prior'], case['name'], size)
            p.equal(_read_dir(p.mem), entries)
            p.equal(written, [] if offset is None else [DATA + offset])
        if case['name'] == 'storm1a':
            # First current-act prefix is storm1, not the later storm1a row.
            p.equal(_read_dir(p.mem), (('storm1a', p.rows[8][1][1]),))
            p.equal(p.rows[8][1][0], 'storm1')
        p.equal(sum(c.stubbed for c in p.ee.calls if c.target != WRITE), 0)
        p.counts['store_cases'] += 1
    return p.counts


def _zero_names(mem):
    mem.write(PENDING, b'\0' * 0x120)
    mem.write(TEX, b'\0' * 64)


def _plant_quest(mem, value):
    mem.write(QUEST, b'SYN\0' + bytes([value]) + b'\0')


def transition(elf, rng):
    p = Probe(elf)
    e, m = p.ee, p.mem
    death = {'on': 0}
    store_ret = {'value': 0}
    stored_arg = []
    spots = []
    constructed = []
    sounds = []
    state = {'card': 0}
    e.stub(0x19D9F8, ret=0)
    e.stub(0x19E5E8, function=lambda ee: death['on'])
    e.stub(STORE, function=lambda ee: stored_arg.append(m.cstr(ee.r[4])) or store_ret['value'])
    e.stub(0x1EB6F8, ret=0)
    e.stub(0x21F144, ret=0)
    e.stub(0x27DB00, ret=0)
    e.stub(0x1D3ADC, ret=0)
    e.stub(0x1BE1D8, ret=0)
    e.stub(0x2247EC, ret=0)
    e.stub(0x216588, function=lambda ee: sounds.append(ee.f[12]) or 0)
    e.stub(0x1E55C0, ret=0)
    e.stub(0x355490, ret=0)
    e.stub(0x217550, function=lambda ee: state['card'])
    e.stub(0x13DD40, function=lambda ee: int(ee.r[4] in state['peers']))
    def terrain(ee):
        ee.f[0] = float_to_raw(4.0)
        return 0
    e.stub(0x183820, function=terrain)
    def spot(ee):
        spots.append((ee.r[4], ee.r[5], ee.r[6], ee.r[7]))
        m.wf32(ee.r[4], 9.0)
        m.wf32(ee.r[4] + 4, 8.0)
        m.wf32(ee.r[4] + 8, 7.0)
        return 1
    e.stub(0x14ACF8, function=spot)
    e.stub(0x14FDB8, function=lambda ee: e.alloc(0x590))
    def ctor(ee):
        constructed.append((ee.r[4], m.f32(ee.r[5]), m.f32(ee.r[5] + 4),
                            m.f32(ee.r[5] + 8), ee.r[6] & 0xFFFFFFFF, ee.r[7]))
        return 0
    e.stub(0x1A1D28, function=ctor)
    # Caller branch only: a nonzero store result writes through a null task
    # pointer. Map that page so the original branch can be observed.
    m.map(0, 4)

    orient = rng.randrange(1, 255)
    facing = (rng.randrange(0x10000), rng.randrange(0x10000))
    origin = (float(1 + rng.randrange(5)), float(1 + rng.randrange(5)))

    def prepare(level, sub, pending, act=-1):
        _zero_names(m)
        p.put(LEVEL, level)
        p.put(SUB, sub)
        p.put(PENDING, pending)
        m.w8(ORIENT, orient)
        m.w32(ACT, act & 0xFFFFFFFF)
        m.w32(CARD, 0)
        m.w32(FLAG, 0)
        m.w8(FORCED, 0)
        m.w32(FRONTEND, 0)
        m.w8(LATCH, 0)
        m.w32(LOADED, 0)
        m.w8(RANK, 0)
        m.w32(PVP, 0)
        m.w32(PLAYERS, 0)
        m.w8(RECALL_FLAG, 0)
        m.w8(RECALL_LEG, 0xAB)
        m.w32(MEDAL, 0)
        m.w32(MEDAL_SAVE, 0)
        m.w32(ACT_MARK, 9)
        m.w32(IDLE, 7)
        m.w32(VOICE, 0)
        m.w32(VOICE_DELAY, 3)
        _clear_dir(m)
        _plant_quest(m, 7)
        death['on'] = 0
        store_ret['value'] = 0
        state['card'] = 0
        state['peers'] = set()
        stored_arg.clear()
        spots.clear()
        constructed.clear()
        sounds.clear()
        m.w32(0x4F7134, 0)
        m.w32(0, 0x11111111)

    def run():
        p.call(LOAD)
        p.counts['load_cases'] += 1

    # Empty current level skips the departure save. Pending still splits.
    prepare('', '', 'SYN_A_SUB')
    run()
    base, sub, forced = R.split_request('SYN_A_SUB')
    p.equal(stored_arg, [])
    p.equal((m.cstr(LEVEL), m.cstr(SUB), m.cstr(PENDING), m.cstr(TEX)),
            (base, sub, '', base))
    p.equal((m.u8(ORIENT), m.u8(SAVED_ORIENT), m.cstr(PREV)),
            (forced, orient, ''))
    p.equal([c.target for c in p.targets(0x1E55C0)], [0x1E55C0])
    p.equal(m.cstr(p.ee.calls[[c.target for c in p.ee.calls].index(0x1E55C0)].args[0]), base)

    # Death task skips the save and the act-clear block, not the name split.
    prepare('SYN_OLD', 'PART', 'strife_branch', act=5)
    death['on'] = 1
    run()
    p.equal(stored_arg, [])
    p.equal(m.s32(ACT), 0)
    p.equal(ACT_CHANGED in [c.target for c in p.ee.calls], True)
    p.equal(0x21F144 in [c.target for c in p.ee.calls], False)
    p.equal((m.cstr(LEVEL), m.cstr(SUB), m.cstr(PREV)),
            ('strife', 'branch', 'SYN_OLD_PART'))
    p.equal(m.u32(ACT_MARK), 9)
    p.equal(m.u8(QUEST + 4), 7)

    # Nonzero store result is the caller's early branch. Original store itself
    # is tested separately and returns 0, so this is not a retail failure.
    prepare('SYN_OLD', '', 'strife', act=5)
    store_ret['value'] = 1
    run()
    p.equal(stored_arg, ['SYN_OLD'])
    p.equal(m.u8(PENDING), 0)
    p.equal(m.u32(0), 0)
    p.equal(0x1E55C0 in [c.target for c in p.ee.calls], False)
    p.equal(0x2247EC in [c.target for c in p.ee.calls], False)
    p.equal(m.s32(ACT), 5)

    # Front end does not consult the act table. The request still splits.
    prepare('SYN_OLD', '', 'strife', act=-1)
    m.w32(FRONTEND, 1)
    run()
    p.equal(stored_arg, ['SYN_OLD'])
    p.equal(ACT_CHANGED in [c.target for c in p.ee.calls], False)
    p.equal(m.s32(ACT), -1)
    p.equal(m.cstr(LEVEL), 'strife')

    # Latch and card-state skips leave the cleared-act side effects alone
    # after the act index has already changed.
    prepare('SYN_OLD', '', 'honor', act=0)
    m.w8(LATCH, 1)
    run()
    p.equal(m.s32(ACT), 6)
    p.equal(0x21F144 in [c.target for c in p.ee.calls], False)
    p.equal(m.u32(ACT_MARK), 9)

    # Same-act request does not clear quests. A different act does.
    prepare('SYN_OLD', '', 'strife', act=0)
    run()
    p.equal((m.s32(ACT), m.u32(ACT_MARK), m.u8(QUEST + 4)), (0, 9, 7))
    prepare('SYN_OLD', '', 'strife', act=5)
    m.w32(PLAYERS, 2)
    run()
    p.equal(m.s32(ACT), 0)
    p.equal(m.u32(ACT_MARK), 1)
    p.equal(m.u8(QUEST + 4), 0)
    p.equal(m.cstr(QUEST), 'SYN')
    clears = [c.args[0] for c in p.targets(0x21F144)]
    resets = [c.args[0] for c in p.targets(0x27DB00)]
    removed = [c.args[0] for c in p.targets(0x1BE1D8)]
    p.equal(clears, [0])
    p.equal(resets, [0])
    p.equal(removed, [0, 1])
    p.equal(0x1ED728 in [c.target for c in p.ee.calls], True)

    # Recall copies x/y only. Slot 0 is not scattered. Slot 1 is, then z is
    # the supplied terrain height. Facing grows by 8000 and is sign-extended.
    prepare('SYN_OLD', '', 'SYN_NEXT', act=0)
    m.w32(LOADED, 1)
    m.w32(PLAYERS, 2)
    m.w8(RECALL_FLAG, 1)
    m.w8(RANK, 0)
    state['peers'] = {0, 1}
    for slot in range(2):
        m.wf32(SPAWN + 12 * slot, origin[0] + slot)
        m.wf32(SPAWN + 12 * slot + 4, origin[1])
        m.wf32(SPAWN + 12 * slot + 8, 1.0)
        m.wf32(RECALL + 12 * slot, 3.0 + slot)
        m.wf32(RECALL + 12 * slot + 4, 5.0)
        m.w16(FACING + 2 * slot, facing[slot])
        m.wf32(RECORD + STRIDE * slot + HP_OFF, 1.0)
        m.write(RECORD + STRIDE * slot + RECALL_OFF, b'\xab' * 8)
    run()
    p.equal(m.u8(RECALL_FLAG), 0)
    p.equal(m.u8(RECALL_LEG), 0)
    p.equal((m.f32(SPAWN), m.f32(SPAWN + 4), m.f32(SPAWN + 8)), (3.0, 5.0, 4.0))
    p.equal((m.f32(SPAWN + 12), m.f32(SPAWN + 16), m.f32(SPAWN + 20)), (9.0, 8.0, 4.0))
    p.equal(m.u16(FACING), facing[0])
    p.equal(m.u16(FACING + 2), (facing[1] + 0x1F40) & 0xFFFF)
    p.equal(len(spots), 1)
    p.equal((spots[0][2], spots[0][3]), (0x24, 0xE))
    expect_facing = (facing[1] + 0x1F40) & 0xFFFF
    if expect_facing >= 0x8000:
        expect_facing -= 0x10000
    p.equal([(c[1], c[2], c[3], c[4] if c[4] < 0x80000000 else c[4] - 0x100000000, c[5])
             for c in constructed],
            [(3.0, 5.0, 4.0, facing[0] if facing[0] < 0x8000 else facing[0] - 0x10000, 0),
             (9.0, 8.0, 4.0, expect_facing, 1)])

    # Rank 3, an unloaded level, and the PvP word each skip the free-spot search.
    for rank, loaded, pvp, expect_spots in ((3, 1, 0, 0), (0, 0, 0, 0), (0, 1, 1, 0)):
        prepare('SYN_OLD', '', 'SYN_NEXT', act=0)
        m.w32(LOADED, loaded)
        m.w32(PVP, pvp)
        m.w8(RANK, rank)
        m.w32(PLAYERS, 2)
        state['peers'] = {0, 1}
        for slot in range(2):
            m.wf32(SPAWN + 12 * slot, 2.0)
            m.wf32(SPAWN + 12 * slot + 4, 2.0)
            m.wf32(RECORD + STRIDE * slot + HP_OFF, 1.0)
            m.w16(FACING + 2 * slot, 10)
        run()
        p.equal(len(spots), expect_spots)
        p.equal(len(constructed), 2 if loaded and not pvp else 0)

    # Dead, inactive, and the non-medal slot are not constructed. An act
    # change still writes the recall name for every slot, including the dead one.
    prepare('SYN_OLD', '', 'strife', act=5)
    m.w32(LOADED, 1)
    m.w32(PLAYERS, 2)
    m.w8(RANK, 3)
    m.w32(MEDAL, 1)
    m.w8(MEDAL_SLOT, 0)
    state['peers'] = {0}
    state['card'] = 0
    for slot, hp in ((0, 1.0), (1, 0.0)):
        m.wf32(RECORD + STRIDE * slot + HP_OFF, hp)
        m.write(RECORD + STRIDE * slot + RECALL_OFF, b'\xab' * 8)
        m.wf32(SPAWN + 12 * slot, 2.0)
        m.wf32(SPAWN + 12 * slot + 4, 2.0)
    run()
    p.equal([c[5] for c in constructed], [0])
    p.equal(m.cstr(RECORD + RECALL_OFF), 'None')
    p.equal(m.cstr(RECORD + STRIDE + RECALL_OFF), 'None')

    # Card state 4 and a stored destination suppress the two side effects.
    prepare('SYN_OLD', '', 'strife', act=5)
    m.w32(LOADED, 1)
    m.w32(PLAYERS, 1)
    state['card'] = 4
    state['peers'] = {0}
    m.wf32(RECORD + HP_OFF, 1.0)
    m.write(RECORD + RECALL_OFF, b'\xab' * 8)
    p.put(DIRECTORY, 'strife')
    run()
    p.equal(m.read(RECORD + RECALL_OFF, 4), b'\xab' * 4)
    p.equal(m.u32(IDLE), 7)

    prepare('SYN_OLD', '', 'SYN_FRESH', act=0)
    run()
    p.equal(m.u32(IDLE), 300)
    p.equal(m.u8(RECALL_LEG), 0)
    p.equal(0x2247EC in [c.target for c in p.ee.calls], True)

    # Leading underscore, no underscore, and the voice-option delay.
    prepare('SYN_OLD', '', '_SYN_ONLY', act=0)
    m.w32(VOICE, 1)
    run()
    p.equal((m.cstr(LEVEL), m.cstr(SUB)), ('', 'SYN_ONLY'))
    p.equal((m.u32(VOICE), m.u32(VOICE_DELAY)), (0, 20))
    p.equal(sounds, [0x3D4CCCCC])
    return p.counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seed', type=int, default=20973)
    ap.add_argument('--elf', default='local/SLUS_209.73')
    args = ap.parse_args()
    assert hashlib.sha256(Path(args.elf).read_bytes()).hexdigest() == SHA
    rng = random.Random(args.seed)
    counts = acts(args.elf) + names(args.elf) + departures(args.elf) + transition(args.elf, rng)
    print('PASS exit_travel seed=%d ' % args.seed +
          ' '.join('%s=%d' % item for item in sorted(counts.items())) + ' failures=0')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAIL exit_travel failures=1')
        raise
