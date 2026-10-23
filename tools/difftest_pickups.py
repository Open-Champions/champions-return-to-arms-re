#!/usr/bin/env python3
"""Compare bounded Chest and ItemProp branches with original US v2.00 code.

Calls outside the named functions are recording stubs. The chest has no placed
properties, so its item/potion/random loops are empty; loot_generateDrops is
recorded, not executed here. See difftest_items.py for the seeded generator.
"""
import argparse
import hashlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, float_to_raw  # noqa: E402
import ref_pickups as model  # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYER_BASE, PLAYER_STRIDE = 0x4d8af0, 0x4c30


def targets(emu, address):
    return [call for call in emu.calls if call.target == address]


def chest_cases(elf, seed):
    cases = 0
    for opened, gold, key in ((0, 0, 'OpenChest'), (0, 9, 'OpenChest'),
                              (1, 9, 'PickUpGold'), (1, 0, None)):
        emu = EE(elf)
        emu.follow = set()
        chest = emu.alloc(0x100)
        emu.mem.w32(chest + 0x84, opened)
        emu.mem.w16(chest + 0x4c, gold)
        assert emu.call(0x29297c, chest, 1) == 1, (opened, gold)
        lookups = targets(emu, 0x173c84)
        assert tuple(emu.mem.cstr(call.args[0]) for call in lookups) == (() if key is None else (key,))
        formats = targets(emu, 0x19ea78)
        assert len(formats) == int(opened and gold > 0), (opened, gold, formats)
        if formats:
            assert formats[0].fargs[0] == float_to_raw(gold), (gold, formats[0].fargs)
        assert len(targets(emu, 0x19e854)) == int(key is not None)
        cases += 1

    for opened, gold in ((0, 0), (0, 9), (1, 9)):
        emu = EE(elf)
        emu.follow = set()
        emu.mem.w32(0x404464, seed)
        emu.mem.w32(0x44fdcc, 100)
        chest = emu.alloc(0x100)
        emu.mem.w32(chest + 0x24, emu.alloc(0x40))
        emu.mem.w32(chest + 0x0c, 0x100000)
        emu.mem.w16(chest + 0x4c, gold)
        emu.mem.w32(chest + 0x84, opened)
        emu.call(0x292a2c, chest, 1)
        expected = model.chest_interact(opened, gold)
        actual = {'opened': emu.mem.u32(chest + 0x84),
                  'gold': emu.mem.u16(chest + 0x4c),
                  'hide': emu.mem.u32(chest + 0x54),
                  'loot_calls': len(targets(emu, 0x100d54)),
                  'floater_calls': len(targets(emu, 0x1dc268)),
                  'interactable': bool(emu.mem.u32(chest + 0x0c) & 0x100000)}
        assert actual == expected, (opened, gold, actual, expected)
        if not opened:
            assert emu.mem.u32(chest + 0x50) == 100
            assert len(targets(emu, 0x170838)) == 1
            assert len(targets(emu, 0x14f248)) == 1
            loot = targets(emu, 0x100d54)
            assert loot[0].site == 0x293120
            assert loot[0].fargs[2:4] == (0, 0), loot[0].fargs
        else:
            assert targets(emu, 0x1dc268)[0].args[0] == 1
        cases += 1

    for done in (False, True):
        emu = EE(elf)
        emu.follow = set()
        chest = emu.alloc(0x100)
        emu.mem.w16(chest + 0x62, 0x80 if done else 0)
        emu.call(0x2923a8, chest)
        actual = (emu.mem.u32(chest + 0x84), len(targets(emu, 0x14dcc8)),
                  len(targets(emu, 0x14f290)))
        assert actual == model.chest_finish(done), (done, actual)
        cases += 1
    return cases


def pickup_cases(elf, seed):
    cases = 0
    for count, load, weight, limit in ((62, 0, 0, 100), (63, 0, 0, 100),
                                       (62, 90, 11, 100), (62, 90, 10, 100)):
        emu = EE(elf)
        emu.follow = set()
        definition, item = emu.alloc(0x40), emu.alloc(0x48)
        emu.mem.w32(item, definition)
        emu.mem.w8(definition + 0x1d, 0)
        emu.mem.w32(PLAYER_BASE + 0x1330, count)
        emu.mem.w32(PLAYER_BASE + 0x120, float_to_raw(load))
        emu.mem.w32(PLAYER_BASE + 0x124, float_to_raw(limit))

        def item_weight(machine):
            machine.f[0] = float_to_raw(weight)

        emu.stub(0x1b6338, function=item_weight)
        actual = emu.call(0x154dbc, 0, item)
        expected = model.can_pickup(count, load, weight, limit)
        assert actual == int(expected), (count, load, weight, limit, actual)
        assert len(targets(emu, 0x1c1868)) == int(expected)
        assert len(targets(emu, 0x1bec10)) == int(expected)
        cases += 1

    for shared, counts, chosen_slot in ((False, (63, 0), 1),
                                        (True, (63, 0), 1),
                                        (False, (0, 0), 1),
                                        (True, (0, 0), 1)):
        emu = EE(elf)
        emu.follow = {0x159b38, 0x154dbc}
        emu.mem.w32(0x404464, seed)
        prop, definition, vtable = emu.alloc(0x190), emu.alloc(0x40), emu.alloc(0x40)
        emu.mem.w32(prop + 0x148, definition)
        emu.mem.w64(prop + 0x150, (1 << 39) if shared else 0)
        emu.mem.w32(prop + 0x48, vtable)
        emu.mem.w32(vtable + 12, 0xf00000)  # recording destructor stub
        emu.mem.w32(0x4d8ae0, 2)
        emu.mem.w8(definition + 0x1d, 0)
        for slot, count in enumerate(counts):
            record = PLAYER_BASE + slot * PLAYER_STRIDE
            emu.mem.w32(record + 0x1330, count)
            emu.mem.w32(record + 0x120, float_to_raw(0))
            emu.mem.w32(record + 0x124, float_to_raw(100))
        emu.call(0x159b38, prop, chosen_slot)
        granted, destroyed = model.item_interact(shared, counts, (0, 0), 0,
                                                  (100, 100), chosen_slot)
        actual_granted = tuple(call.args[0] for call in targets(emu, 0x1c1868))
        assert actual_granted == granted, (shared, counts, actual_granted, granted)
        assert len(targets(emu, 0xf00000)) == int(destroyed), (shared, counts)
        cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error('expected US v2.00 executable SHA-256 %s' % EXPECTED_SHA256)
    chest = chest_cases(args.elf, args.seed)
    print('PASS chest branches: %d cases, seed %d' % (chest, args.seed))
    pickup = pickup_cases(args.elf, args.seed)
    print('PASS pickup branches: %d cases, seed %d' % (pickup, args.seed))
    print('PASS %d bounded original-code cases' % (chest + pickup))


if __name__ == '__main__':
    main()
