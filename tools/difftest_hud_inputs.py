#!/usr/bin/env python3
"""Compare automap grid input producers with the original EE instructions.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_hud_inputs.py SLUS_209.73 --seed 20973

Runs automap_loadGrid 0x168894 and the draw-time player reveal 0x16a4b0 via
ee_emu. The reveal property uses exact integer cell centres; this bounds its
claim without guessing the PS2 FPU's behaviour for arbitrary world positions.
No game data or instruction bytes are emitted or stored.
"""
import argparse
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ee_emu import EE  # noqa: E402
import ref_hud_inputs as H  # noqa: E402

GRID = 0x4044F0
WIDTH, HEIGHT = 0x4044DC, 0x4044E0
ORIGIN_X, ORIGIN_Y = 0x4044A8, 0x4044AC
SEEDS = (0x404464, 0x404460, 0x404468)
N = H.GRID_SIDE ** 2


def grid_bytes(cells):
    return struct.pack('<%dH' % N, *cells)


def draws(emu):
    return sum(1 for _pc, address, size, _value in emu.writes
               if address in SEEDS and size == 4)


def load_cases(emu, rng):
    world = emu.alloc(0x100)
    source = emu.alloc(8 + 2 * 32 * 32)
    for case in range(160):
        old = [0] * N
        for _ in range(12):
            old[rng.randrange(N)] = rng.randrange(0x10000)
        emu.mem.write(GRID, grid_bytes(old))
        old_width, old_height = rng.randrange(1, 33), rng.randrange(1, 33)
        emu.mem.w32(WIDTH, old_width)
        emu.mem.w32(HEIGHT, old_height)
        emu.mem.w32(ORIGIN_X, 0x41200000)  # 10.0
        emu.mem.w32(ORIGIN_Y, 0xC1200000)  # -10.0
        width, height = rng.randrange(0, 33), rng.randrange(0, 33)
        x0, y0 = rng.randrange(-200, 201), rng.randrange(-200, 201)
        cells = [rng.randrange(0x10000) for _ in range(width * height)]
        emu.mem.w16(source, x0 & 0xffff)
        emu.mem.w16(source + 2, y0 & 0xffff)
        emu.mem.w16(source + 4, width)
        emu.mem.w16(source + 6, height)
        emu.mem.write(source + 8, struct.pack('<%dH' % len(cells), *cells))
        texture, pointer, keep = rng.randrange(2), rng.randrange(2), rng.randrange(2)
        emu.mem.w32(world + 0x6c, texture)
        emu.mem.w32(world + 0x70, keep)
        emu.mem.w32(world + 0x80, source if pointer else 0)
        want = H.load_grid(texture, pointer, keep, x0, y0, width, height, cells,
                           old_width, old_height, (10.0, -10.0), old)
        emu.writes = []
        emu.call(0x168894, world)
        got = (emu.mem.u32(WIDTH), emu.mem.u32(HEIGHT),
               (emu.mem.u32(ORIGIN_X), emu.mem.u32(ORIGIN_Y)), emu.mem.read(GRID, 2 * N))
        expected = (want[0], want[1],
                    (struct.unpack('<I', struct.pack('<f', want[2][0]))[0],
                     struct.unpack('<I', struct.pack('<f', want[2][1]))[0]), grid_bytes(want[3]))
        if got != expected:
            raise AssertionError('automap_loadGrid case %d: widths %r/%r, origin %r/%r, grid %s' %
                                 (case, got[:2], expected[:2], got[2], expected[2],
                                  'equal' if got[3] == expected[3] else 'differs'))
        if draws(emu):
            raise AssertionError('automap_loadGrid drew a random seed')
    return 160


def reveal_cases(emu, rng):
    position = emu.alloc(16)
    for at in (position, position + 4, position + 8):
        emu.mem.w32(at, 0)  # origin alone chooses the exact cell centre
    for case in range(120):
        cx, cy = rng.randrange(0, H.GRID_SIDE), rng.randrange(0, H.GRID_SIDE)
        old = [rng.randrange(0x10000) for _ in range(N)]
        emu.mem.write(GRID, grid_bytes(old))
        emu.mem.w32(WIDTH, H.GRID_SIDE)
        emu.mem.w32(HEIGHT, H.GRID_SIDE)
        emu.mem.w32(ORIGIN_X, struct.unpack('<I', struct.pack('<f', float(cx)))[0])
        emu.mem.w32(ORIGIN_Y, struct.unpack('<I', struct.pack('<f', float(cy)))[0])
        emu.writes = []
        emu.call(0x16A4B0, position)
        want = grid_bytes(H.reveal_integer_cell(old, H.GRID_SIDE, H.GRID_SIDE, cx, cy))
        if emu.mem.read(GRID, 2 * N) != want:
            raise AssertionError('draw-time reveal case %d at cell (%d, %d)' % (case, cx, cy))
        if draws(emu):
            raise AssertionError('draw-time reveal drew a random seed')
    return 120


def feed_cases(elf, rng):
    """The original minimap_draw, with the projector and world query as observers."""
    emu = EE(elf)
    world, camera = emu.alloc(0x100), emu.alloc(0x100)
    real = [emu.alloc(0x600) for _ in range(4)]
    ghost = [emu.alloc(0x600) for _ in range(4)]
    extra = [emu.alloc(0x600) for _ in range(8)]
    state = {}
    emu.stub(0x1EBDF8, ret=0, name='game_isFrozen')
    emu.stub(0x217550, ret=0, name='memcard_getState')
    emu.stub(0x19E5E8, ret=0, name='task_isRunning')
    emu.stub(0x2074A0, ret=0, name='Camera_getSpectatedSlot')
    emu.stub(0x207450, ret=0, name='Camera_getYaw')
    emu.stub(0x16A838, ret=1, name='projector_gate')

    def reveal(e):
        p = e.r[4] & 0xffffffff
        state['reveal'].append(tuple(e.mem.u32(p + i * 4) for i in range(3)))

    def query(e):
        lo, hi, out, limit = [e.r[i] & 0xffffffff for i in (4, 5, 6, 7)]
        state['query'] = (tuple(e.mem.u32(lo + 4 * i) for i in range(3)),
                          tuple(e.mem.u32(hi + 4 * i) for i in range(3)), limit)
        for i, object_id in enumerate(state['nearby']):
            e.mem.w32(out + 4 * i, object_id)
        e.mem.w32(out + 4 * len(state['nearby']), 0)

    def owner_object(e):
        object_id = e.r[4] & 0xffffffff
        state['owner_calls'].append(object_id)
        return state['ghost_for'][object_id]

    def project(e):
        lst = e.mem.u32(0x4F867C)
        got = []
        for i in range(208):
            object_id = e.mem.u32(lst + 4 * i)
            if not object_id:
                break
            got.append(object_id)
        state['project'] = (e.r[4] & 0xffffffff,
                            tuple(e.mem.u32((e.r[5] & 0xffffffff) + 4 * i)
                                  for i in range(2)), got)

    emu.stub(0x16A4B0, function=reveal, name='automap_revealAtPlayer')
    emu.stub(0x14A928, function=query, name='world_collectObjectsInBox')
    emu.stub(0x13E180, function=owner_object, name='net_objOrGhost')
    emu.stub(0x168CAC, function=project, name='automap_projector')
    emu.mem.w32(0x44FDC8, world)
    emu.mem.w32(world + 0x6c, 0x1234)
    emu.mem.w32(world + 0x80, 0x5678)
    emu.mem.w32(0x4F8450, camera)
    emu.mem.w32(camera + 0x34, 1)
    emu.mem.w32(0x4F841C, 0)
    emu.mem.w8(0x44FCD0, 0)
    emu.mem.w32(0x4F8400, 1)
    emu.mem.w32(0x4F71A0, 0x3F800000)
    emu.mem.w32(0x41B9E0, 0)
    for slot in range(4):
        emu.mem.w32(0x4028D8 + 0x58 * slot, 0)
        emu.mem.w32(0x4028DC + 0x58 * slot, 0)
        emu.mem.w32(0x4F8680 + 4 * slot, 0)
    for case in range(100):
        network = rng.randrange(2)
        nplayers = rng.randrange(1, 5)
        reveal_all = rng.randrange(2)
        emu.mem.w8(0x402791, network)
        emu.mem.w32(0x4D8AE0, nplayers)
        emu.mem.w32(0x6E14D4, reveal_all)
        camera_xy = (rng.randrange(-1000, 1001), rng.randrange(-1000, 1001))
        spectated_z = rng.randrange(-1000, 1001)
        emu.mem.w32(camera + 0x18, fbits(camera_xy[0]))
        emu.mem.w32(camera + 0x1c, fbits(camera_xy[1]))
        nearby = []
        candidates = real[:nplayers] + extra
        for _ in range(rng.randrange(0, 9)):
            object_id = rng.choice(candidates)
            if object_id not in nearby:
                nearby.append(object_id)
        player_rows = []
        expected_reveals = []
        ghost_for = {}
        for slot in range(4):
            record = 0x4D8AF0 + 0x4C30 * slot
            exists = slot < nplayers and (slot == 0 or rng.randrange(2))
            object_id = real[slot] if exists else 0
            emu.mem.w32(record + 0x43d8, object_id)
            emu.mem.w32(record + 0xac, fbits(50.0))
            if exists:
                z = spectated_z if slot == 0 else rng.randrange(-1000, 1001)
                xyz = (rng.randrange(-1000, 1001), rng.randrange(-1000, 1001), z)
                for i, value in enumerate(xyz):
                    emu.mem.w32(object_id + 0x10 + 4 * i, fbits(value))
                expected_reveals.append(tuple(fbits(value) for value in xyz))
                ghost_for[object_id] = ghost[slot]
            player_rows.append((object_id or None, ghost[slot]))
        for object_id in candidates:
            is_player = object_id in real[:nplayers] or rng.randrange(3) == 0
            emu.mem.w32(object_id + 0xc, 0x40 if is_player else 0)
        state.clear()
        state.update(reveal=[], query=None, project=None, owner_calls=[],
                     nearby=nearby, ghost_for=ghost_for)
        emu.writes = []
        emu.call(0x1E42E0)
        if state['reveal'] != expected_reveals:
            raise AssertionError('minimap_draw reveal order case %d' % case)
        expected_box = H.blip_query_box(*camera_xy, spectated_z, reveal_all)
        box_bits = (tuple(fbits(v) for v in expected_box[0]),
                    tuple(fbits(v) for v in expected_box[1]), expected_box[2])
        if state['query'] != box_bits:
            raise AssertionError('minimap_draw query case %d: %r != %r' %
                                 (case, state['query'], box_bits))
        nearby_flags = [(object_id, emu.mem.u32(object_id + 0xc)) for object_id in nearby]
        want = H.blip_sources(nearby_flags, player_rows[:nplayers], network)
        if state['project'] != (world, tuple(fbits(v) for v in camera_xy), want):
            raise AssertionError('minimap_draw projector inputs case %d: got %r expected %r' %
                                 (case, state['project'], want))
        if state['owner_calls'] != ([p for p, _g in player_rows[:nplayers] if p] if network else []):
            raise AssertionError('minimap_draw owner objects case %d' % case)
        if draws(emu):
            raise AssertionError('minimap_draw drew a random seed')
    return 100


def fbits(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def gold_touch_cases(elf, rng):
    emu = EE(elf)
    pile, toucher = emu.alloc(0x100), emu.alloc(0x400)
    effects = []
    emu.stub(0x17365C, ret=0x1234, name='res_find')
    emu.stub(0x214230, function=lambda _e: effects.append(('coin_sound',)),
             name='sound_playOnObject')

    def add_floater(e):
        pos = e.r[5] & 0xffffffff
        effects.append(('add_floater', e.r[4] & 0xffffffff,
                        tuple(e.mem.u32(pos + 4 * i) for i in range(3)),
                        e.r[6] & 0xffffffff))

    emu.stub(0x1DC268, function=add_floater, name='hud_addGoldFloater')
    emu.stub(0x14F200, function=lambda _e: effects.append(('delete',)), name='obj_delete')
    for case in range(180):
        flags = rng.choice((0, 0x40, 0x20000, 0x20040, 0x48))
        countdown = rng.choice((-1, 0, 0, 0, 1, 41))
        amount = rng.choice((0, 1, 25, 999, 0x7fffffff))
        slot = rng.randrange(4)
        position = tuple(fbits(rng.randrange(-1000, 1001)) for _ in range(3))
        emu.mem.w32(toucher + 0xc, flags)
        emu.mem.w32(toucher + 0x3c8, slot)
        emu.mem.w8(pile + 0x4c, countdown & 0xff)
        emu.mem.w32(pile + 0x80, amount)
        for i, value in enumerate(position):
            emu.mem.w32(pile + 0x10 + 4 * i, value)
        effects.clear()
        emu.writes = []
        emu.call(0x157A9C, pile, toucher)
        want_amount, want_effects = H.gold_touch(flags, countdown, amount, slot, position)
        if emu.mem.u32(pile + 0x80) != want_amount or effects != want_effects:
            raise AssertionError('Gold_onTouch case %d: amount %d/%d, effects %r/%r' %
                                 (case, emu.mem.u32(pile + 0x80), want_amount,
                                  effects, want_effects))
        if draws(emu):
            raise AssertionError('Gold_onTouch drew a random seed')
        if want_effects:
            effects.clear()
            emu.call(0x157A9C, pile, toucher)
            if effects:
                raise AssertionError('Gold_onTouch credited a second toucher')
    return 180


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.environ.get('CHAMPIONS_ELF'))
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    if not args.elf or not os.path.isfile(args.elf):
        print('SKIP: SLUS-20973 v2.00 ELF missing')
        return 0
    emu = EE(args.elf)
    a = load_cases(emu, random.Random('%d/load' % args.seed))
    print('PASS automap_loadGrid %d cases; seed draws 0' % a)
    b = reveal_cases(emu, random.Random('%d/reveal' % args.seed))
    print('PASS draw-time reveal %d cases; seed draws 0' % b)
    c = feed_cases(args.elf, random.Random('%d/feed' % args.seed))
    print('PASS minimap_draw feed %d cases; seed draws 0' % c)
    d = gold_touch_cases(args.elf, random.Random('%d/gold-touch' % args.seed))
    print('PASS Gold_onTouch %d cases; seed draws 0' % d)
    print('PASS 4 properties, %d cases, seed %d' % (a + b + c + d, args.seed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
