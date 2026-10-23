#!/usr/bin/env python3
"""Compare player_resetIdleAnim's base-track stores with a small reference model.

Runs the original function in ee_emu on synthetic resolved pointers, on both
requested seeded case sets. No disc bytes or disassembly are written.
Usage: python3 tools/difftest_player_anim_select.py /path/to/SLUS_209.73 --seed N
"""
import argparse
import hashlib
import random

from ee_emu import EE
import ref_player_anim_select as model

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
RESET = 0x1B2470
RELEASE = 0x171118
EQUIP = 0x1C27C0
PASSIVE = 0x1BED48
PROCESS_DAMAGE = 0x1B2CC0


def one(elf, rng, weapon_class, alive, has_object):
    emu = EE(elf)
    mem = emu.mem
    player = emu.alloc(0x600)
    definition = emu.alloc(0x400)
    slot = rng.randrange(4)
    record = model.G_PLAYERS + slot * model.RECORD_SIZE
    mem.w32(record + 0x43D8, player if has_object else 0)
    mem.wf32(record + 0xAC, 10.0 if alive else 0.0)
    mem.w8(record + 0x4A86, weapon_class)
    mem.w32(player + 0x24, definition)
    mem.w8(player + 0x462, 0)
    words = {}
    for k in model.BASE_SLOTS:
        off = model.resource_offset(weapon_class, k)
        words[off] = (rng.getrandbits(28) | 0x20000000) & ~3
        mem.w32(definition + off, words[off])
    before = [mem.read(player + 0x11C + i * 0x20, 0x20) for i in range(4)]
    emu.stub(RELEASE, name='anim_releaseCaches')
    emu.follow = {RESET}
    emu.reads = []
    emu.call(RESET, slot)
    if not alive or not has_object:
        return (all(mem.read(player + 0x11C + i * 0x20, 0x20) == before[i]
                    for i in range(4)) and not emu.calls, 'guard')
    expected = model.base_tracks(weapon_class, words.__getitem__)
    failures = []
    for i, (clip, weight, life, flags) in enumerate(expected):
        p = player + 0x11C + 0x20 * i
        got = (mem.u32(p), mem.u32(p + 8), mem.u32(p + 0x10), mem.u16(p + 0x1C))
        if got != (clip, weight, life, flags):
            failures.append((i, got, (clip, weight, life, flags)))
    if mem.u8(player + 0x118) != 4:
        failures.append(('count', mem.u8(player + 0x118)))
    if [c.target for c in emu.calls] != [RELEASE]:
        failures.append(('calls', [hex(c.target) for c in emu.calls]))
    class_reads = [(pc, value) for pc, address, size, value in emu.reads
                   if address == record + 0x4A86 and size == 1]
    if (0x1B24B4, weapon_class) not in class_reads:
        failures.append(('selector class read', class_reads))
    definition_reads = [(pc, value) for pc, address, size, value in emu.reads
                        if address == player + 0x24 and size == 4]
    if not {0x1B25B0, 0x1B25C4}.issubset(
            {pc for pc, value in definition_reads if value == definition}):
        failures.append(('selector definition reads', definition_reads))
    return not failures, failures


def equip_then_select(elf, rng, weapon_class, *, dual=False, ammunition=False):
    """Follow the original equip store into the original base-clip selector.

    The item and resolved clip words are synthetic. Other equip callees are
    recording stubs, so this checks the class handoff, not item eligibility.
    """
    emu = EE(elf)
    mem = emu.mem
    slot = rng.randrange(4)
    record = model.G_PLAYERS + slot * model.RECORD_SIZE
    player = emu.alloc(0x600)
    table = emu.alloc(0x400)
    item = emu.alloc(0x48)
    definition = emu.alloc(0x40)
    equipment_slot = 8 if ammunition else (0 if dual or weapon_class in (0, 5, 7) else 2)
    mem.w32(item, definition)
    mem.w8(definition + 0x1C, equipment_slot)
    mem.w8(definition + 0x1D, 0)
    mem.w8(definition + 0x1E, 0 if dual else weapon_class)
    mem.w8(record + 0x4A86, 5)
    mem.w32(record + 0x43D8, player)
    mem.wf32(record + 0xAC, 10.0)
    mem.w32(player + 0x24, table)
    if dual:
        first = emu.alloc(0x48)
        first_definition = emu.alloc(0x40)
        mem.w32(first, first_definition)
        mem.w8(first_definition + 0x1C, 0)
        mem.w8(first_definition + 0x1D, 0)
        mem.w8(first_definition + 0x1E, 0)
        mem.w32(record + 0x4434, first)
        mem.w32(record + 0x43F0, first)
        emu.stub(PASSIVE, ret=1, name='player_getPassiveLevel')
    emu.follow = {EQUIP}
    emu.call(EQUIP, slot, item, 1)
    expected_class = 5 if ammunition else 7 if dual else weapon_class
    failures = []
    if mem.u8(record + 0x4A86) != expected_class:
        failures.append(('class', mem.u8(record + 0x4A86), expected_class))
    class_stores = [(pc, value) for pc, address, size, value in emu.writes
                    if address == record + 0x4A86 and size == 1]
    expected_stores = ([] if ammunition else
                       [(0x1C2AD4, 0 if dual else weapon_class)] +
                       ([(0x1C2B64, 7)] if dual else []))
    if class_stores != expected_stores:
        failures.append(('class stores', class_stores))
    reset_sites = [c.site for c in emu.calls if c.target == RESET]
    if reset_sites != ([] if ammunition else [0x1C2B80]):
        failures.append(('reset call sites', reset_sites))
    set_stores = [(pc, value) for pc, address, size, value in emu.writes
                  if address == record + 0x4A7C and size == 1]
    expected_set = 1 if weapon_class in (4, 6) and not dual else 0
    if ammunition:
        if set_stores:
            failures.append(('ammunition set stores', set_stores))
    elif set_stores != [(0x1C29E8, expected_set)]:
        failures.append(('set stores', set_stores, expected_set))

    # Use different pointers in every row so selecting the old class is visible.
    for cls in range(8):
        for k in model.BASE_SLOTS:
            mem.w32(table + model.resource_offset(cls, k),
                    0x20000000 + cls * 0x1000 + k)
    emu.reset_log()
    emu.stub(RELEASE, name='anim_releaseCaches')
    emu.follow = {RESET}
    emu.reads = []
    emu.call(RESET, slot)
    class_reads = [(pc, value) for pc, address, size, value in emu.reads
                   if address == record + 0x4A86 and size == 1]
    if (0x1B24B4, expected_class) not in class_reads:
        failures.append(('selector class read', class_reads))
    definition_reads = [(pc, value) for pc, address, size, value in emu.reads
                        if address == player + 0x24 and size == 4]
    if not {0x1B25B0, 0x1B25C4}.issubset(
            {pc for pc, value in definition_reads if value == table}):
        failures.append(('selector definition reads', definition_reads))
    for i, k in enumerate(model.BASE_SLOTS):
        got = mem.u32(player + 0x11C + 0x20 * i)
        want = mem.u32(table + model.resource_offset(expected_class, k))
        if got != want:
            failures.append(('clip', i, got, want))
    return not failures, failures


def death_entry(elf, seed):
    """Execute the original lethal-damage entry to action state 4.

    Callees are stubbed; this verifies the player state store, not the death
    clip or a full damage simulation.
    """
    emu = EE(elf)
    mem = emu.mem
    player = emu.alloc(0x600)
    table = emu.alloc(0x400)
    record = model.G_PLAYERS
    mem.w32(0x404464, seed)
    mem.w32(player + 0xC, 0x60)
    mem.w32(player + 0x3C8, 0)
    mem.w32(player + 0x24, table)
    mem.w32(player + 0x58C, 2)
    mem.wf32(player + 0xC8, 500.0)
    mem.wf32(record + 0xAC, 100.0)
    mem.w32(record + 0x43D8, player)
    emu.follow = set()
    emu.call(PROCESS_DAMAGE, player)
    state_stores = [(pc, value) for pc, address, size, value in emu.writes
                    if address == player + 0x58C and size == 4]
    ok = (state_stores == [(0x1B34FC, 4)] and mem.u32(player + 0x58C) == 4
          and mem.u32(record + 0xAC) == 0)
    return ok, state_stores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error('requires SLUS_209.73 US v2.00 (SHA-256 mismatch)')
    rng = random.Random(args.seed)
    cases = failures = 0
    for weapon_class in range(8):
        for alive, has_object in ((True, True), (False, True), (True, False)):
            for _ in range(4):
                ok, detail = one(args.elf, rng, weapon_class, alive, has_object)
                cases += 1
                if not ok:
                    failures += 1
                    if failures <= 4:
                        print('FAIL class=%d alive=%s object=%s: %s' %
                              (weapon_class, alive, has_object, detail))
    equip_cases = equip_failures = 0
    for weapon_class in range(8):
        ok, detail = equip_then_select(args.elf, rng, weapon_class)
        equip_cases += 1
        if not ok:
            equip_failures += 1
            print('FAIL equip class=%d: %s' % (weapon_class, detail))
    for kind in ('dual', 'ammunition'):
        ok, detail = equip_then_select(args.elf, rng, 0, dual=kind == 'dual',
                                        ammunition=kind == 'ammunition')
        equip_cases += 1
        if not ok:
            equip_failures += 1
            print('FAIL equip %s: %s' % (kind, detail))
    print('%s player base selection seed=%d cases=%d mismatches=%d' %
          ('PASS' if failures == 0 else 'FAIL', args.seed, cases, failures))
    print('%s equip to base selection seed=%d cases=%d mismatches=%d' %
          ('PASS' if equip_failures == 0 else 'FAIL', args.seed, equip_cases,
           equip_failures))
    death_ok, death_detail = death_entry(args.elf, args.seed)
    print('%s lethal damage state entry seed=%d cases=1 %s' %
          ('PASS' if death_ok else 'FAIL', args.seed,
           '' if death_ok else death_detail))
    return 1 if failures or equip_failures or not death_ok else 0


if __name__ == '__main__':
    raise SystemExit(main())
