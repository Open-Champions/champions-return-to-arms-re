#!/usr/bin/env python3
"""Compare synthetic level-save framing and reload order with SLUS-20973 v2.00.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world.py
       /path/to/SLUS_209.73 --seed 20973
No game bytes are stored. Only selected functions run in tools/ee_emu.py;
file I/O, scripts and object factories are replaced by recording callbacks.
"""

import argparse
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: E402,F401 -- tools/dis.py shadows stdlib dis
sys.path.insert(0, HERE)

from ee_emu import EE  # noqa: E402
import ref_save_world as R  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SAVE_WRITE = 0x218600
LEVEL_LOAD = 0x217978
SAVE_STORE = 0x21777C
SAVE_STORED = 0x2182D4
G_SAVE_DIR = 0x8AB590
G_SAVE_DATA = 0x8AB698
G_SCRATCH = 0x88D480
G_AUTO_SIZE = 0x4044D0
G_LOADED = 0x8E1AD6
G_RANK = 0x4F7108
G_SKIP = 0x4F8B58
G_ACT = 0x88D3D4
G_ACT_TABLE = 0x4F8E48
G_LEVEL_NAME = 0x41B721


def cstr(emu, ptr):
    return emu.mem.read(ptr & 0xFFFFFFFF, 64).split(b'\0', 1)[0]


def fixture(elf):
    ee = EE(elf)
    ee.record_calls = False
    ee.record_writes = False
    return ee


def check_write(elf, rng):
    checked = 0
    for _ in range(16):
        ee = fixture(elf)
        ee.mem.w32(G_AUTO_SIZE, R.AUTOMAP_SIZE)
        world = bytes(rng.getrandbits(8) for _ in range(rng.randrange(8, 57, 8)))
        decals = bytes(rng.getrandbits(8) for _ in range(rng.randrange(8, 33, 8)))
        explored = bytes(rng.getrandbits(8) for _ in range(R.AUTOMAP_SIZE))
        size = 0x2000
        dest = ee.alloc(size)
        initial = bytes(rng.getrandbits(8) for _ in range(size))
        ee.mem.write(dest, initial)
        calls = []

        ee.stub(0x1EC0F0)  # qualified name has no byte effect on this function

        def world_fn(e):
            calls.append(('world', e.r[4], e.r[5]))
            e.mem.write(e.r[4], world)
            return len(world)

        def decal_fn(e):
            calls.append(('decal', e.r[4], e.r[5]))
            e.mem.write(e.r[4], decals)
            return len(decals)

        def map_fn(e):
            calls.append(('map', e.r[4]))
            e.mem.write(e.r[4], explored)
            return 0

        ee.stub(0x14E5C8, function=world_fn)
        ee.stub(0x19EE10, function=decal_fn)
        ee.stub(0x16865C, function=map_fn)
        ee.call(SAVE_WRITE, dest, size)
        got = ee.mem.read(dest, size)
        want = R.pack_level_body(world, decals, explored, size, initial)
        expected_calls = [('world', dest + 8, size - R.AUTOMAP_SIZE - 0x18),
                          ('decal', dest + len(world) + 16,
                           size - R.AUTOMAP_SIZE - 0x18 - len(world) + 8),
                          ('map', dest + len(world) + len(decals) + 16)]
        assert got == want, 'save_writeLevelState bytes differ'
        assert calls == expected_calls, (calls, expected_calls)
        assert R.unpack_level_body(got) == (world, decals, explored)
        checked += 1
    print('PASS write_level_body %d cases' % checked)


def check_reload(elf, rng):
    checked = 0
    for saved in (False, True):
        for skip_scripts in (False, True):
            for _ in range(8):
                ee = fixture(elf)
                ee.mem.write(G_SAVE_DIR, bytes(10 * 0x18))
                ee.mem.w8(G_LOADED, 1)
                ee.mem.w8(G_RANK, 0xA5)
                ee.mem.w8(G_SKIP, int(skip_scripts))
                name = ee.alloc(16)
                ee.mem.write(name, b'hub\0')
                base = ee.alloc(16)
                ee.mem.write(base, b'hub\0')
                lump = ee.alloc(16)
                entry = ee.alloc(16)
                ob = ee.alloc(16)
                ee.mem.w32(entry + 4, ob)
                events = []
                rank_checks = []

                def observe_rank(e, event):
                    rank_checks.append((event, e.mem.u8(G_RANK), e.mem.u8(G_LOADED)))
                    assert rank_checks[-1][1:] == (3, 0), rank_checks[-1]
                    events.append(event)
                    return 0

                def script_fn(e):
                    event = cstr(e, e.r[4]).decode()
                    if event == 'preStart':
                        return observe_rank(e, event)
                    events.append(event)
                    return 0

                def objects_fn(e):
                    event = ('saved_objects' if (e.r[4] & 0xFFFFFFFF) == G_SCRATCH else
                             ('level_objects_filtered' if e.r[5] else 'level_objects_all'))
                    if skip_scripts and not rank_checks:
                        observe_rank(e, event)
                    else:
                        events.append(event)
                    return 8

                def automap_fn(e):
                    if skip_scripts and not rank_checks:
                        return observe_rank(e, 'automap_unpack')
                    events.append('automap_unpack')
                    return 0

                ee.stub(0x173558, ret=lump)
                ee.stub(0x171DE4, function=lambda e: entry if cstr(e, e.r[5]) == b'objects.ob' else 0)
                ee.stub(0x1ED650, function=lambda e: events.append('script_set_current') or 0)
                ee.stub(0x1ED694, function=script_fn)
                ee.stub(0x14E808, function=objects_fn)
                ee.stub(0x1A00B0, function=lambda e: events.append('decal_load') or 0)
                ee.stub(0x1686C4, function=automap_fn)
                if saved:
                    world = bytes(rng.getrandbits(8) for _ in range(8))
                    decals = bytes(rng.getrandbits(8) for _ in range(8))
                    body = R.pack_level_body(world, decals, bytes(R.AUTOMAP_SIZE), 0x2000)
                    ee.mem.write(G_SAVE_DIR, b'hub\0')
                    ee.mem.w32(G_SAVE_DIR + 0x14, len(body))
                    ee.mem.write(G_SAVE_DATA, body)
                ee.call(LEVEL_LOAD, base, name)
                want = R.reload_events(saved, skip_scripts=skip_scripts)
                assert events == want, (events, want)
                assert len(rank_checks) == 1, rank_checks
                assert rank_checks[0][0] == ('preStart' if not skip_scripts else
                                               ('automap_unpack' if saved else 'level_objects_all'))
                assert ee.mem.u8(G_RANK) == 3 and ee.mem.u8(G_LOADED) == 0
                if saved:
                    assert ee.mem.read(G_SCRATCH, 8) == world
                    assert ee.mem.read(G_SCRATCH + 8, 8) == decals
                checked += 1
    print('PASS reload_order %d cases' % checked)


def check_class_states(elf, rng):
    checked = 0
    for _ in range(16):
        ee = fixture(elf)
        obj, out = ee.alloc(0x200), ee.alloc(0x100)
        fields = dict(hide_mask=rng.getrandbits(32), gold=rng.randrange(0x8000),
                      bomb=rng.randrange(256), variant=rng.randrange(256),
                      opened=rng.randrange(2))
        ee.mem.w32(obj + 0x54, fields['hide_mask'])
        ee.mem.w16(obj + 0x4c, fields['gold'])
        ee.mem.w8(obj + 0x58, fields['bomb'])
        ee.mem.w8(obj + 0x59, fields['variant'])
        ee.mem.w32(obj + 0x84, fields['opened'])
        assert ee.call(0x292284, obj, out) == 12
        assert ee.mem.read(out, 12) == R.chest_state(fields)
        restored = ee.alloc(0x200)
        model = ee.alloc(0x30)
        ee.mem.w32(restored + 0x24, model)
        effects = []
        for addr in (0x170838, 0x170BC8, 0x14F5F0):
            ee.stub(addr, function=lambda e, a=addr: effects.append(a) or 0)
        assert ee.call(0x2922CC, restored, out) == 12
        for off, width in ((0x54, 4), (0x4c, 2), (0x58, 1), (0x59, 1), (0x84, 4)):
            assert ee.mem.read(obj + off, width) == ee.mem.read(restored + off, width)
        assert effects == ([0x170838, 0x170BC8] if fields['opened'] else []) + [0x14F5F0]
        checked += 1
    print('PASS chest_state %d save/load cases' % checked)

    checked = 0
    for _ in range(16):
        ee = fixture(elf)
        obj, out = ee.alloc(0x200), ee.alloc(0x100)
        item = bytearray(rng.getrandbits(8) for _ in range(0x48))
        index = rng.randrange(0x400)
        struct.pack_into('<I', item, 0, 0x3F7650 + index * 0x40)
        ee.mem.write(obj + 0x148, item)
        suffix = b'PROP!'
        saves = []
        def prop_save(e):
            saves.append((e.r[4], e.r[5]))
            e.mem.write(e.r[5], suffix)
            return len(suffix)
        ee.stub(0x158D8C, function=prop_save)
        assert ee.call(0x1596A4, obj, out) == 0x48 + len(suffix)
        assert ee.mem.read(out, 0x48 + len(suffix)) == R.itemprop_item(item) + suffix
        assert ee.mem.read(obj + 0x148, 0x48) == item
        assert saves == [(obj, out + 0x48)]
        restored = ee.alloc(0x200)
        loads = []
        ee.stub(0x158F04, function=lambda e: loads.append((e.r[4], e.r[5])) or len(suffix))
        ee.stub(0x163B30, function=lambda e: loads.append(('transform', e.r[4])) or 0)
        assert ee.call(0x159758, restored, out) == 0x48 + len(suffix)
        assert ee.mem.read(restored + 0x148, 0x48) == item
        assert loads == [(restored, out + 0x48), ('transform', restored + 0x110)]
        assert ee.mem.u32(restored + 0xc) & 0x100000
        checked += 1
    print('PASS itemprop_state %d save/load cases' % checked)

    # Direct slot-9 writers with no external calls.  These are fields within
    # synthetic objects, not records lifted from a game save.
    writers = (
        (0x1ECF18, {0x64: ('I', 0x12345678), 0x60: ('B', 0xA5)}, '<IB', (0x12345678, 0xA5)),
        (0x28AE3C, {0x50: ('H', 0x1234), 0x58: ('B', 0xFE), 0x54: ('f', 1.25)},
         '<Hhf', (0x1234, -2, 1.25)),
        (0x28B1A0, {0x58: ('B', 1)}, '<B', (1,)),
        (0x28DEE8, {0x5a: ('h', 1), 0x4c: ('h', 7), 0x50: ('f', 2.5), 0x54: ('I', 99)},
         '<iifi', (1, 7, 2.5, 99)),
        (0x27D974, {0x4d: ('B', 2), 0x4e: ('B', 1)}, '<BB', (2, 1)),
        (0x23B06C, {0xc8: ('I', 0xAABBCCDD), 0xdc: ('H', 300),
                     0xe4: ('B', 3), 0xe5: ('B', 4), 0xd8: ('I', 1)},
         '<IHBBI', (0xAABBCCDD, 300, 3, 4, 1)),
    )
    for addr, values, fmt, expected in writers:
        ee = fixture(elf)
        obj, out = ee.alloc(0x200), ee.alloc(0x80)
        for off, (kind, value) in values.items():
            ee.mem.write(obj + off, struct.pack('<' + kind, value))
        want = struct.pack(fmt, *expected)
        assert ee.call(addr, obj, out) == len(want), hex(addr)
        assert ee.mem.read(out, len(want)) == want, hex(addr)
    print('PASS trigger, door, gate, AutoChest writers %d cases' % len(writers))

    # Prop is the variable suffix of ItemProp: three interned strings, a
    # compressed u64 mask, quaternion and three integer coordinates.
    for mask in (8, 10):
        ee = fixture(elf)
        obj, out = ee.alloc(0x200), ee.alloc(0x80)
        ee.mem.write(obj + 0x54, b'asset\0')
        ee.mem.write(obj + 0x64, b'model\0')
        ee.mem.write(obj + 0xa4, b'texture\0')
        ee.mem.write(obj + 0xe8, struct.pack('<Q', mask))
        for off, value in ((0x134, 1.0), (0x138, -2.0), (0x13c, 3.0)):
            ee.mem.write(obj + off, struct.pack('<f', value))
        handles = iter((11, 22, 33))
        ee.stub(0x14DE60, function=lambda e: next(handles))
        ee.stub(0x164330, function=lambda e: e.mem.write(e.r[4], struct.pack('<4f', 0, 0, 0, 1)) or 0)
        ee.stub(0x166550)
        got_size = ee.call(0x158D8C, obj, out)
        expected = R.prop_suffix((11, 22, 33), mask, (0, 0, 0, 10000), (1, -2, 3))
        assert got_size == len(expected), (mask, got_size, len(expected))
        assert ee.mem.read(out, got_size) == expected, mask
    print('PASS Prop suffix 2 mask encodings')

    for hp in (50.0, -25.0):
        ee = fixture(elf)
        obj, out, clips = ee.alloc(0x400), ee.alloc(0x40), ee.alloc(0x20)
        ee.mem.w32(obj + 0xe8, 7)
        ee.mem.write(obj + 0x228, struct.pack('<ff', hp, 100.0))
        ee.mem.w32(obj + 0x24, clips)
        for flags in (0, 0x1000000, 0x100000000, 0x400000,
                      0x800000, 0x2000000000000):
            for half in (0, 5):
                ee.mem.write(obj + 0xa8, struct.pack('<Q', flags))
                ee.mem.w16(obj + 0x312, half)
                ee.mem.w8(obj + 0x231, 1)
                want = R.creature_state(7, hp / 100.0, flags, 1, half)
                assert ee.call(0x116780, obj, out) == len(want)
                assert ee.mem.read(out, len(want)) == want, (hp, flags, half)
    print('PASS Creature alive/dead writer 24 cases')


def check_directory(elf):
    ee = fixture(elf)
    ee.mem.auto_map = True
    ee.mem.write(G_SAVE_DIR, bytes(11 * 0x18))
    ee.mem.w32(G_ACT, 0)
    table = ee.alloc(16)
    row_name = ee.alloc(16)
    ee.mem.write(row_name, b'hub\0')
    ee.mem.w32(G_ACT_TABLE, table)
    ee.mem.w32(table, row_name)
    ee.mem.w16(table + 4, 0x2000)
    writes = []
    ee.stub(SAVE_WRITE, function=lambda e: writes.append((e.r[4], e.r[5])) or 0)
    names = [''] * 11
    for index in range(11):
        name = 'hub%02d' % index
        ptr = ee.alloc(16)
        ee.mem.write(ptr, name.encode() + b'\0')
        slot = R.directory_slot(names, name)
        assert slot == index
        ee.call(SAVE_STORE, ptr)
        names[index] = name
        entry = G_SAVE_DIR + index * 0x18
        assert cstr(ee, entry) == name.encode()
        assert ee.mem.u32(entry + 0x14) == 0x2000
        assert writes[-1] == (G_SAVE_DATA + index * 0x2000, 0x2000)
    assert R.directory_lookup(names, 'hub10') is None
    ee.mem.write(G_LEVEL_NAME, b'hub10\0')
    assert ee.call(SAVE_STORED) == 0
    ee.mem.write(G_LEVEL_NAME, b'hub09\0')
    assert ee.call(SAVE_STORED) == 1
    ptr = ee.alloc(16)
    ee.mem.write(ptr, b'hub11\0')
    assert R.directory_slot(names, 'hub11') == 10
    ee.call(SAVE_STORE, ptr)
    assert len(writes) == 12 and cstr(ee, G_SAVE_DIR + 10 * 0x18) == b'hub10'
    assert writes[-1] == (G_SAVE_DATA + 10 * 0x2000, 0x2000)
    old_size = ee.mem.u32(G_SAVE_DIR + 4 * 0x18 + 0x14)
    ee.mem.w16(table + 4, 0x3000)
    duplicate = ee.alloc(16)
    ee.mem.write(duplicate, b'hub04\0')
    ee.call(SAVE_STORE, duplicate)
    assert ee.mem.u32(G_SAVE_DIR + 4 * 0x18 + 0x14) == old_size
    assert writes[-1] == (G_SAVE_DATA + 4 * 0x2000, old_size)
    print('PASS directory 11 insertions, read limit, overflow alias, duplicate size')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == SHA256, 'wrong executable revision'
    rng = random.Random(args.seed)
    check_write(args.elf, rng)
    check_reload(args.elf, rng)
    check_class_states(args.elf, rng)
    check_directory(args.elf)


if __name__ == '__main__':
    main()
