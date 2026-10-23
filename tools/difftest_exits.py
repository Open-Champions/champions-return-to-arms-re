#!/usr/bin/env python3
"""Compare bounded exit reference rules with original SLUS-20973 v2.00 code.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_exits.py /path/to/SLUS_209.73 --seed 20973
No game bytes or disassembly are written.  The executable is read only.
"""
import argparse
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE, float_to_raw  # noqa: E402
import ref_exits as R  # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def cstr(mem, address):
    return bytes(mem.u8(address + i) for i in range(80)).split(b'\0', 1)[0].decode('ascii')


def run(seed, elf):
    rng = random.Random(seed)
    ee = EE(elf)
    trigger = ee.alloc(0x80)
    params_obj = ee.alloc(0x50)
    table = ee.alloc(0x100)
    script_name = ee.alloc(16)
    ee.mem.write(script_name, b'exit\0')
    ee.mem.w32(trigger + 0x48, table)
    ee.mem.w16(table + 0x88, 0)
    ee.mem.w32(table + 0x8c, 0x1ed238)  # virtual slot 17
    ee.mem.w32(trigger + 0x5c, script_name)
    players = [ee.alloc(0x40) for _ in range(3)]
    for i, obj in enumerate(players):
        ee.mem.w32(0x4dcec8 + i * 0x4c30, obj)
    ee.mem.w32(0x4d8ae0, len(players))
    ee.mem.w8(trigger + 0x61, 1)  # link search already completed
    events = []
    settings = {}
    queried = []
    ee.stub(0x14c880, function=lambda e: queried.append(cstr(e.mem, e.r[5])) or settings.get(queried[-1], 0))
    ee.stub(0x14dcc8, function=lambda e: events.append(('action', e.r[5])) or 0)
    ee.stub(0x1ed694, function=lambda e: events.append(
        ('script', cstr(e.mem, e.r[4]), ee.mem.s32(0x4d8ae4)
         if cstr(e.mem, e.r[4]) == 'exit' else None)) or settings['script_result'])
    checked = 0
    # Include edges, negative disabled delays, and random occupancy/parameter states.
    cases = [((0, 0), None, 0, 0, 0, 1), ((10, 10), None, 0, 0, 0, 1)]
    for _ in range(240):
        cases.append(((rng.choice([-1, 0, 5, 10, 11]), rng.choice([-1, 0, 5, 10, 11])),
                      rng.choice([None, 0, 1, 2]), rng.choice([-2, -1, 0, 1, 3]),
                      rng.randrange(2), rng.randrange(2), rng.randrange(2)))
    for first, chosen_slot, delay, inside, countdown, script_result in cases:
        rect = (0.0, 0.0, 10.0, 10.0)
        for off, val in zip((0x4c, 0x50, 0x54, 0x58), rect):
            ee.mem.w32(trigger + off, float_to_raw(val))
        points = [None] * len(players)
        if chosen_slot is not None:
            points[chosen_slot] = first
        else:
            points[0] = first
        for i, point in enumerate(points):
            ee.mem.w32(0x4dcec8 + i * 0x4c30, players[i] if point is not None else 0)
            if point is not None:
                ee.mem.w32(players[i] + 0x10, float_to_raw(point[0]))
                ee.mem.w32(players[i] + 0x14, float_to_raw(point[1]))
        ee.mem.w32(trigger + 0x64, delay)
        ee.mem.w8(trigger + 0x60, inside)
        ee.mem.w32(trigger + 0x68, 99)
        ee.mem.w8(0x41b51d, countdown)
        ee.mem.w32(0x4d8ae4, -1)
        params = None if rng.randrange(2) else {
            'onOnly': rng.randrange(2), 'offOnly': rng.randrange(2),
            'timeout': rng.choice([0, 0, 1, 2]), 'needScriptHit': rng.randrange(2)}
        ee.mem.w32(trigger + 0x6c, params_obj if params is not None else 0)
        settings.clear()
        settings.update(params or {})
        settings['script_result'] = script_result
        expected, actions = R.trigger_tick(
            {'delay': delay, 'inside': inside, 'slot': 99}, rect, points,
            countdown, params, script_result)
        events.clear()
        queried.clear()
        ee.call(0x1ecf3c, trigger)
        got = {'delay': ee.mem.s32(trigger + 0x64), 'inside': ee.mem.u8(trigger + 0x60),
               'slot': ee.mem.s32(trigger + 0x68)}
        if got != expected or events != actions:
            raise AssertionError(f'trigger case {checked}: {got=} {expected=} {events=} {actions=} {params=} {queried=}')
        checked += 1
    # Two occupants in the same rectangle: lower player slot must win.
    for i in range(2):
        ee.mem.w32(0x4dcec8 + i * 0x4c30, players[i])
        ee.mem.w32(players[i] + 0x10, float_to_raw(5))
        ee.mem.w32(players[i] + 0x14, float_to_raw(5))
    ee.mem.w32(0x4dcec8 + 2 * 0x4c30, 0)
    ee.mem.w32(trigger + 0x6c, 0)
    ee.mem.w32(trigger + 0x64, 0)
    ee.mem.w8(trigger + 0x60, 0)
    ee.mem.w8(0x41b51d, 0)
    ee.mem.w32(0x4d8ae4, -1)
    settings['script_result'] = 1
    events.clear()
    ee.call(0x1ecf3c, trigger)
    if ee.mem.s32(trigger + 0x68) != 0 or events != [('script', 'exit', 0)]:
        raise AssertionError(f'first occupant priority: {events=}')
    checked += 1
    # Exhaustive boundary comparisons against the actual virtual shape predicate.
    for x in (-1, 0, 5, 10, 11):
        for y in (-1, 0, 5, 10, 11):
            ee.mem.w32(players[0] + 0x10, float_to_raw(x))
            ee.mem.w32(players[0] + 0x14, float_to_raw(y))
            got = ee.call(0x1ed238, trigger, players[0])
            if bool(got) != R.contains((0, 0, 10, 10), (x, y)):
                raise AssertionError(f'contains({x}, {y}) = {got}')
            checked += 1
    print(f'PASS exits trigger/rectangle seed={seed} comparisons={checked}')

    gate = ee.alloc(0x170)
    output = ee.alloc(0x100)
    predicate_name = ee.alloc(16)
    ee.mem.write(predicate_name, b'canUse\0')
    gate_settings = {}
    messages = []
    ee.stub(0x19e5e8, function=lambda e: int(gate_settings['menu_open']))
    ee.stub(0x14f4c0, function=lambda e: predicate_name if gate_settings['has_script'] else 0)
    ee.stub(0x1ed694, function=lambda e: int(gate_settings['predicate']))
    ee.stub(0x27db60, function=lambda e: ee.mem.w8(
        0x8e3c30, ee.mem.u8(0x8e3c30) + 1) or 0)
    ee.stub(0x173c84, function=lambda e: e.r[4])
    ee.stub(0x1d92a0)
    ee.stub(0x19e854, function=lambda e: messages.append(cstr(e.mem, e.r[5])) or 0)
    gate_checked = 0
    for found in (0, 1):
        for count in (1, 2):
            for menu_open in (False, True):
                for predicate in (False, True):
                    for near in (False, True):
                        for hurt in (False, True):
                            gate_settings.update(menu_open=menu_open, predicate=predicate,
                                                 has_script=True)
                            ee.mem.w8(gate + 0x4d, found)
                            ee.mem.w8(gate + 0x4f, int(hurt))
                            ee.mem.w8(0x8e3c30, count)
                            ee.mem.w32(0x4f8420, 2)
                            ee.mem.w32(0x4f8440, 0)
                            ee.mem.w32(0x4f8444, 1)
                            ee.mem.w32(0x4dcec8, players[0])
                            ee.mem.w32(0x4dcec8 + 0x4c30, players[1])
                            for off in (0x10, 0x14, 0x18):
                                ee.mem.w32(gate + off, float_to_raw(0))
                            ee.mem.w32(players[1] + 0x10, float_to_raw(95 if near else 97))
                            ee.mem.w32(players[1] + 0x14, float_to_raw(0))
                            ee.mem.w32(players[1] + 0x18, float_to_raw(0))
                            messages.clear()
                            expected_found, expected_message, usable = R.gate_prompt(
                                found, count + (0 if found or menu_open or not predicate or hurt else 1),
                                menu_open, predicate, near, hurt)
                            # The first discovery appends the current level before the
                            # one-destination check.  Model the actual resulting count.
                            result = ee.call(0x27d7a0, gate, output, 0)
                            got_message = messages[-1] if messages else None
                            if ((ee.mem.u8(gate + 0x4d), got_message, bool(result)) !=
                                    (expected_found, expected_message, usable)):
                                raise AssertionError(
                                    f'gate case {gate_checked}: '
                                    f'{(ee.mem.u8(gate + 0x4d), got_message, bool(result))=} '
                                    f'{(expected_found, expected_message, usable)=}')
                            gate_checked += 1
    print(f'PASS exits gate prompt seed={seed} comparisons={gate_checked}')

    push = ee.alloc(0x50)
    key_a = ee.alloc(16)
    key_b = ee.alloc(16)
    success = ee.alloc(16)
    denied = ee.alloc(16)
    for addr, name in ((key_a, b'keyA\0'), (key_b, b'keyB\0'),
                       (success, b'message\0'), (denied, b'locked\0')):
        ee.mem.write(addr, name)
    props = {}
    values = {}
    def push_prop(e):
        name = cstr(e.mem, e.r[5])
        if name == 'key':
            keys = props.get('key', ())
            return keys[e.r[6]] if e.r[6] < len(keys) else 0
        return props.get(name, 0)
    ee.stub(0x14f4c0, function=push_prop)
    ee.stub(0x1ed694, function=lambda e: values.get(cstr(e.mem, e.r[4]), 0))
    ee.mem.w8(0x402791, 0)  # offline; host-only prompt branch is documented, not compared
    push_checked = 0
    for count in (0, 1, 2):
        for key_a_ok in (False, True):
            for key_b_ok in (False, True):
                for have_message in (False, True):
                    for have_lock in (False, True):
                        keys = ('keyA', 'keyB')[:count]
                        props.clear()
                        props.update(key=(key_a, key_b)[:count],
                                     message=success if have_message else 0,
                                     lockMessage=denied if have_lock else 0)
                        values.clear()
                        values.update(keyA=int(key_a_ok), keyB=int(key_b_ok))
                        messages.clear()
                        expected_message, usable = R.push_prompt(
                            keys, values, 'message' if have_message else None,
                            'locked' if have_lock else None)
                        result = ee.call(0x1eca94, push, output, 0)
                        got_message = messages[-1] if messages else None
                        if (got_message, bool(result)) != (expected_message, usable):
                            raise AssertionError(f'push case {push_checked}: '
                                                 f'{(got_message, bool(result))=} '
                                                 f'{(expected_message, usable)=}')
                        push_checked += 1
    print(f'PASS exits push prompt seed={seed} comparisons={push_checked}')

    arrival_gate = ee.alloc(0x170)
    source_pos = ee.alloc(12)
    source_xyz = (10.0, 20.0, 30.0)
    for i, value in enumerate(source_xyz):
        ee.mem.w32(source_pos + 4 * i, float_to_raw(value))
    ee.stub(0x14cb10, function=lambda e: e.mem.write(
        e.r[4] + 0x10, e.mem.read(e.r[5], 12)) or 0)
    for address in (0x148af8, 0x1689a4, 0x14a4f0,
                    0x14f248, 0x17365c, 0x148bc8):
        ee.stub(address)
    ee.stub(0x14c880, ret=0)
    ee.stub(0x14f4c0, ret=0)
    searches = []
    def free_spot(e):
        searches.append((e.r[6], e.r[7], e.r[8], e.r[9]))
        e.mem.write(e.r[4], e.mem.read(e.r[5], 12))
        return 0
    ee.stub(0x14acf8, function=free_spot)
    arrival_checked = 0
    for travel in (0, 1):
        for fixed in (0, 1):
            for count in range(5):
                initial_seed = seed + count
                ee.mem.w32(0x4d8ae0, count)
                ee.mem.w32(0x500ae8, travel)
                ee.mem.w32(0x8e3c34, fixed)
                ee.mem.w32(0x404464, initial_seed)
                ee.mem.w8(0x4f7108, 1)
                for i in range(4):
                    for axis in range(3):
                        ee.mem.w32(0x4f70d0 + i * 12 + axis * 4, float_to_raw(-9))
                    ee.mem.w16(0x4f8410 + i * 2, 0xbeef)
                searches.clear()
                rank, positions, facings, end_seed, search_count = R.gate_arrival(
                    travel, fixed, count, source_xyz, initial_seed, 1,
                    lambda pos, spread, radius, any_height: pos)
                ee.call(0x27c694, arrival_gate, source_pos, 0)
                if (ee.mem.u8(0x4f7108), ee.mem.u32(0x404464), len(searches)) != (
                        rank, end_seed, search_count):
                    raise AssertionError(f'arrival state {travel=} {fixed=} {count=}')
                for i in range(4):
                    expected_pos = positions[i] if i < len(positions) else (-9, -9, -9)
                    expected_facing = facings[i] if i < len(facings) else 0xbeef
                    got_pos = tuple(ee.mem.f32(0x4f70d0 + i * 12 + axis * 4)
                                    for axis in range(3))
                    got_facing = ee.mem.u16(0x4f8410 + i * 2)
                    if (got_pos, got_facing) != (expected_pos, expected_facing):
                        raise AssertionError(f'arrival slot {i}: {got_pos=} {got_facing=} '
                                             f'{expected_pos=} {expected_facing=}')
                if any(args != (36, 24, 0, 1) for args in searches):
                    raise AssertionError(f'arrival search arguments: {searches}')
                arrival_checked += 1
    print(f'PASS exits gate arrival seed={seed} comparisons={arrival_checked}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', nargs='?', default=os.path.expanduser('~/champions-re/SLUS_209.73'))
    p.add_argument('--seed', type=int, default=20973)
    a = p.parse_args()
    if not os.path.isfile(a.elf):
        p.error('SLUS_209.73 not found')
    with open(a.elf, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != EXPECTED_SHA256:
        p.error(f'wrong executable SHA-256: {digest}')
    run(a.seed, a.elf)


if __name__ == '__main__':
    main()
