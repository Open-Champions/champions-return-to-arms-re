#!/usr/bin/env python3
"""Initialized-record arrival prefixes, compared with unchanged VM/native models.

Only counts and addresses leave the process. Fresh characters and explicit state
controls are not a captured normal route. Unsupported native bodies never run.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest  # preload before research modules can shadow stdlib dis
from difftest_amx import Original, differences
from difftest_loading_arrival_r4 import (
    ALLOWED, BACK, Boundary, DIFFICULTY, FRONT, PARITY, PLAYERS, QUEUE,
    RECORD, RECORDS, SAVE, STRIDE, TABLE, private_script, require_local,
)
from difftest_starting_equipment_r4 import CLASSES, WEAPONS
from difftest_loading import SHA256
from ref_amx import Machine
import ref_natives as N

# Add modeled quest effects; never manufacture object/media/native return values.
PERMITTED = ALLOWED | {0x1433C8, 0x143540, 0x143500, 0x143588, 0x143EE4,
                       0x142010, 0x142024, 0x142058, 0x1420FC}
REGIONS = ((RECORD, STRIDE * RECORDS), (N.G_QUEST_VARS, 0x2000),
           (QUEUE, 0x2808), (PARITY, 4), (SAVE, 4), (PLAYERS, 4),
           (DIFFICULTY, 4), (N.G_RAND_SEED, 4),
           (N.G_POST_ACTION, 0x50), (N.G_IN_POST_ACTION, 1))


class NoServices(N.Host):
    def call(self, name, *args):
        raise AssertionError('reference attempted an unestablished external service')


def prepared(path, body, seed):
    o = Original(path)
    e = o.emu
    e.hooks.clear()
    e.record_calls = True
    e.mem.w32(PLAYERS, 1)
    e.mem.w32(N.G_RAND_SEED, seed)
    name = e.alloc(32)
    e.mem.write(name, b'authored\0')
    e.mem.w32(o.SP, -1)
    e.mem.w32(o.SP + 8, 0)
    o.call(0x1B1D70, 0, body, name, -1, -1, -1, -1, 0)
    assert e.mem.u32(RECORD + 0x50) == CLASSES[body]
    assert e.mem.u32(RECORD + 0x54) == body
    slot = 2 if body in (2, 3, 6, 7) else 0
    assert e.mem.u32(e.mem.u32(RECORD + 0x43F0 + slot * 4)) == WEAPONS[body]
    before = e.mem.read(RECORD, STRIDE * RECORDS)
    # Reset on initialized records, not only the older sentinel mission fixtures.
    o.call(0x1E6F58)
    assert e.mem.read(RECORD, len(before)) == before, 'reset altered initialized records'
    assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY, SAVE)) == (0, 0, 0, 0)
    assert not any(c.stubbed for c in e.calls) and not e.patches
    return o


def compare_prefix(path, image, body, seed, control=None):
    o = prepared(path, body, seed)
    e = o.emu
    # The single-player difficulty is an explicit fixture input, not a route claim.
    e.mem.w32(DIFFICULTY, 1)
    if control is not None:
        complete, choice, full = control
        for slot in range(RECORDS):
            at = RECORD + STRIDE * slot
            e.mem.write(at + 0x4BCC, bytes([2 * complete]) * 13)
            e.mem.w8(at + 0x4C1A, choice << 1)
        if full:
            e.mem.w32(RECORD + 0x43D0, 8)
    o.place(image)
    assert o.load() == 0
    assert o.call(0x141310, o.base, TABLE, 0xFFFFFFFF) == 0
    model = Machine(image)
    assert model.load() == 0
    mem = N.Mem()
    for address, size in REGIONS:
        mem.write(address, e.mem.read(address, size))
    game = N.Game(mem, host=NoServices())
    game.machine = model
    natives = game.natives()
    trace, expected, phases = [], [], []

    def model_native(name, address):
        def run(vm, args):
            expected.append((address, tuple(args)))
            if address not in PERMITTED:
                raise Boundary()
            return natives[name](vm, args)
        return run

    def observe(address):
        def run(m):
            params = m.r[5] & 0xFFFFFFFF
            size = m.mem.s32(params)
            assert 0 <= size <= 64 and size % 4 == 0
            args = tuple(m.mem.s32(params + 4 + i) for i in range(0, size, 4))
            trace.append((address, args))
            if address not in PERMITTED:
                raise Boundary()
        return run

    bindings = {}
    for index in range(191):
        name_ptr = e.mem.u32(TABLE + 8 * index)
        address = e.mem.u32(TABLE + 8 * index + 4)
        if not name_ptr:
            break
        name = e.mem.cstr(name_ptr)
        bindings[name.encode('latin1')] = model_native(name, address)
        e.hook(address, observe(address))
    assert model.register(bindings) == 0
    for entry in (0x53F000, 0x53F020, None):
        if entry is None:
            # Explicit orchestration after a returned start; the normal loader's
            # intervening player/world work is not claimed or silently skipped.
            assert e.mem.u8(N.G_POST_ACTION), 'expected an actual published post action'
        else:
            name = e.mem.cstr(entry).encode('latin1')
        first = len(trace)
        stopped, results = [False, False], [None, None]
        try:
            if entry is None:
                game.run_post_action()
            else:
                results[0] = model.call(name)
        except Boundary:
            stopped[0] = True
        try:
            if entry is None:
                o.call(0x1EDAC0)
            else:
                results[1] = o.call(0x1ED694, entry)
        except Boundary:
            stopped[1] = True
        assert stopped[0] == stopped[1] and results[0] == results[1]
        assert trace == expected, 'native order or argument mismatch'
        assert not differences(o, model, len(image)), 'script state mismatch'
        for address, size in REGIONS:
            assert e.mem.read(address, size) == mem.read(address, size), 'state region mismatch at 0x%x' % address
        assert not any(c.stubbed for c in e.calls) and not e.patches
        assert not game.host.log, 'model attempted an unestablished external service'
        phases.append((entry, stopped[0], results[0], tuple(a for a, _ in trace[first:])))
        if stopped[0]:
            assert e.mem.u32(FRONT) == e.mem.u32(BACK) == e.mem.u32(PARITY) == 0
            return tuple(a for a, _ in trace), e.mem.u32(RECORD + 0x43D0), entry is None, tuple(phases)
    raise AssertionError('expected explicit native boundary')


def main():
    path, manifest = sys.argv[1:3]
    require_local(path)
    require_local(manifest)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    paths = json.loads(Path(manifest).read_text())
    assert isinstance(paths, list) and len(paths) == 3
    images = [private_script(p) for p in paths]
    expected_orders = (
        (0x1473B4, 0x1420D0, 0x1420A4, 0x142320),
        (0x14222C,),
        (0x142084, 0x142044, 0x1433C8, 0x1420D0, 0x143540,
         0x143540, 0x143EE4, 0x142010, 0x143500, 0x143F1C),
    )
    count = 0
    for ordinal, image in enumerate(images):
        orders = set()
        for body in range(12):
            for seed in (7, 20973):
                order, quests, post, phases = compare_prefix(path, image, body, seed)
                assert order == expected_orders[ordinal]
                assert post == (ordinal == 2)
                orders.add((order, post, phases))
                count += 1
        assert len(orders) == 1
        order, post, phases = next(iter(orders))
        print('PASS initialized_prefix route=%d cases=24 post_action_boundary=%d order=%s' % (
            ordinal, post, ','.join('0x%x' % a for a in order)))
        print('PASS phase_evidence route=%d phases=%s' % (ordinal, phases))
    for complete in (0, 1):
        for choice in (0, 1):
            for full in (0, 1):
                order, quests, post, phases = compare_prefix(path, images[2], 0, 20973, (complete, choice, full))
                expected_order = tuple(a for a in expected_orders[2] if not complete or a not in (0x142044, 0x1433C8))
                assert order == expected_order and post
                assert quests == (8 if full else int(not complete))
                print('PASS controlled_prefix complete=%d choice=%d full=%d quests=%d post_action_boundary=%d order=%s' % (
                    complete, choice, full, quests, post, ','.join('0x%x' % a for a in order)))
                count += 1
    print('PASS initialized_reset_and_prefix cases=%d; final address in each order is unexecuted boundary' % count)
    print('UNKNOWN normal_route world_state resource_bootstrap deferred_census')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (type(error).__name__, getattr(error, 'addr', 0)))
        sys.exit(1)
