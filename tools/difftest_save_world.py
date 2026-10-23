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
G_SAVE_DIR = 0x8AB590
G_SAVE_DATA = 0x8AB698
G_SCRATCH = 0x88D480
G_AUTO_SIZE = 0x4044D0
G_LOADED = 0x8E1AD6
G_RANK = 0x4F7108
G_SKIP = 0x4F8B58


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


if __name__ == '__main__':
    main()
