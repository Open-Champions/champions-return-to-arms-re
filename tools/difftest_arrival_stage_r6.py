#!/usr/bin/env python3
"""Arrival round 6. Original functions in tools/ee_emu.py, past the round-5 stops.

Fixtures: an empty or planted name table, a resident lump, a one-entry cut, and a
synthetic model header. No callee is stubbed. Output is addresses, lengths and counts.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest
from difftest_amx import differences
from difftest_arrival_stage_r5 import (
    CAMERA, CD_FIND, HIDE_MASK, LEVEL, LUMPS, ROUTE0, ROUTE0_ORDER, ROUTE1_ORDER,
    ROUTE2_ORDER, amx_string, capture, cut_matches, drive, fresh, hook_natives,
    model_for, plant_lump, plant_prop, queues, regions_match,
)
from difftest_arrival_state_r4 import PERMITTED
from difftest_loading import SHA256
from difftest_loading_arrival_r4 import (
    RECORD, STRIDE, private_script, require_local,
)
from ee_emu import EE, MemoryFault
from ref_amx import Machine

FIND, REMOVE, SET_FLAG = 0x1C5A70, 0x1C1CB0, 0x1416D4
ITEM_TEST, DEFERRED, PRINTF = 0x145690, 0x1EDA24, 0x355490
POOL_INIT, HANDLE_INIT, WORLD_INIT = 0x14FCD8, 0x1A17D0, 0x14C370
POOL_NEW, OBJECT_CTOR = 0x14FDB8, 0x14CB10
OFF_GRID, UPDATE_GRID, IS_OFF = 0x14EF48, 0x14F028, 0x14EFA0
DTOR, STR_WALK, HANDLE_CLEAR, POOL_FREE = 0x14CF90, 0x3B91D8, 0x1A1698, 0x150470
ANIM_PUSH, SLOT19, LIGHT, CUT_SETUP, CUT_HELPER = 0x170838, 0x23D7AC, 0x14A480, 0x19A6CC, 0x14F498
CUT_RUN = 0x199944
BAGS, BAG_SIZE, BAG_COUNT, FLAG_BYTE = 0x130, 0x1208, 0x1200, 0x4C28
MASK64 = 0xFFFFFFFFFFFFFFFF
FLAG_CALLS = ((0, 4, 0), (1, 4, 0), (2, 4, 0), (3, 4, 0))
ROUTE0_FULL = (ROUTE0_ORDER + (0x14598C,) * 16 + (0x143500,) * 3
               + (SET_FLAG,) * 4 + (0x143500,) * 2)


def data_off(image):
    machine = Machine(image)
    assert machine.load() == 0
    return machine.data_offset


def show_mask(hidden, flag, bits, records):
    """model_buildHideMask 0x179550. Flag bit 2 selects the 16-byte records."""
    mask = (~hidden) & MASK64
    if flag & 2:
        for index in range(32):
            if bits & 1 and index < len(records):
                show, hide = records[index]
                mask = (mask | show) & (~hide) & MASK64
            bits >>= 1
    return mask


def bag_counts(mem):
    return tuple(mem.s32(RECORD + BAGS + bag * BAG_SIZE + BAG_COUNT) for bag in range(3))


def preset_flags(mem):
    for slot in range(4):
        at = RECORD + slot * STRIDE + FLAG_BYTE
        mem.w8(at, mem.u8(at) | 0x10)


def flags_clear(mem):
    for slot in range(4):
        assert mem.u8(RECORD + slot * STRIDE + FLAG_BYTE) & 0x10 == 0


def init_world(o):
    e = o.emu
    e.hooks.clear()
    e.call(POOL_INIT, max_steps=3000000)
    e.call(HANDLE_INIT, max_steps=2000000)
    e.call(WORLD_INIT, max_steps=2000000)


def plant_actor(o, name, creature):
    e = o.emu
    pos = e.alloc(12)
    obj = e.call(POOL_NEW, 0x250)
    e.call(OBJECT_CTOR, obj, pos, 0, 0)
    if creature:
        e.mem.w32(obj + 0x0C, e.mem.u32(obj + 0x0C) | 0x20)
    text = e.alloc(len(name) + 1)
    e.mem.write(text, name + b'\0')
    e.call(0x14BCE0, text, obj)
    return obj


def named_calls(o, addresses):
    grabbed = []

    def take(address):
        def run(m, address=address):
            params = m.r[5] & 0xFFFFFFFF
            grabbed.append(amx_string(m.mem, o.base, o.off, m.mem.s32(params + 4)))
        return run

    for address in addresses:
        o.emu.hook(address, take(address))
    return grabbed


def stop_at(address):
    from difftest_arrival_stage_r5 import Boundary

    def run(_m, address=address):
        raise Boundary('callee', address)
    return run


def mask_direct(path, seed):
    e = EE(path)
    e.r[29] = e.stack_hi - 0x4000
    cases = (
        (0, 0, 0, ()),
        (0x5, 0, 1, ()),
        (0x5, 2, 0, ((0x100, 1),)),
        (0x5, 2, 1, ((0x100, 1),)),
        (0x5, 2, 2, ((0x100, 1), (0x8, 4))),
        (0x5, 2, 3, ((0x100, 1), (0x8, 4))),
    )
    for hidden, flag, bits, records in cases:
        block = e.alloc(16 + 32 * 16)
        e.mem.w64(block + 8, hidden)
        e.mem.w16(block + 0x10, flag)
        e.mem.w8(block + 0x21, 1)
        for index, (show, hide) in enumerate(records):
            e.mem.w64(block + 16 + index * 16, show)
            e.mem.w64(block + 16 + index * 16 + 8, hide)
        assert e.call(HIDE_MASK, block, bits) == show_mask(hidden, flag, bits, records)
    try:
        e.call(HIDE_MASK, 0, 0)
        raise AssertionError('null model returned')
    except MemoryFault as error:
        assert error.pc == HIDE_MASK and error.addr == 0x10
    print('PASS mask_direct seed=%d cases=%d null=0x10' % (seed, len(cases)))


def route0(path, image, body, seed):
    from difftest_arrival_stage_r5 import Services
    original = Services.call

    def answer(self, name, *args):
        if name == 'inventory_findItemBySubstring':
            return (-1, 0)
        return original(self, name, *args)

    Services.call = answer
    o = fresh(path, image, body, seed)
    before = bag_counts(o.emu.mem)
    preset_flags(o.emu.mem)
    permit = set(ROUTE0) | {0x14598C, SET_FLAG, ITEM_TEST}
    model, game, expected = model_for(image, o, permit)
    trace, phases = drive(o, model, game, permit, set(), expected)
    got = tuple(addr for addr, _ in trace)
    if got != ROUTE0_FULL:
        print('TRACE %s' % ','.join('%x' % addr for addr in got))
        print('FLAGS %s' % [tuple(args) for addr, args in trace if addr == SET_FLAG])
    assert got == ROUTE0_FULL
    assert [args[0] for addr, args in trace if addr == 0x14598C] == [-1] * 17
    assert [tuple(args[:3]) for addr, args in trace if addr == SET_FLAG] == list(FLAG_CALLS)
    assert phases[-1][1] == 'absent'
    assert queues(o.emu) == (0, 2, 0)
    assert bag_counts(o.emu.mem) == before
    assert calls(o.emu, FIND) == 17 and calls(o.emu, REMOVE) == 0
    flags_clear(o.emu.mem)
    assert not differences(o, model, len(model.image))
    regions_match(o, game.mem)
    # The loader's one call is this queue's promote. The names stay unrun.
    from difftest_arrival_stage_r5 import Boundary
    e = o.emu
    e.hooks.clear()
    e.record_calls = True
    e.calls.clear()
    e.hook(PRINTF, lambda _m: (_ for _ in ()).throw(Boundary('callee', PRINTF)))
    e.r[31] = e.RETURN_ADDR
    e.r[29] = o.SP
    e.jump(0x322E6C)
    try:
        e.run(max_steps=4000000)
        raise AssertionError('loader returned')
    except Boundary as hit:
        assert hit.address == PRINTF
    assert queues(e) == (2, 0, 1)
    assert calls(e, DEFERRED) == 1 and calls(e, ITEM_TEST) == 0
    game.run_deferred()
    assert not differences(o, model, len(model.image))
    regions_match(o, game.mem)
    seen = []
    hook_natives(o, permit, set(), seen)
    mark = len(expected)
    o.call(DEFERRED, max_steps=8000000)
    game.run_deferred()
    assert seen == expected[mark:]
    assert [addr for addr, _ in seen] == [ITEM_TEST] * 48
    assert queues(e) == (0, 0, 2)
    assert not differences(o, model, len(model.image))
    regions_match(o, game.mem)
    print('PASS route0 body=%d seed=%d removes=17 flags=4 loader=promoted second=48' % (body, seed))


def calls(e, target):
    return sum(1 for record in e.calls if record.target == target)


def route0_prop(path, image, off, body, seed):
    cap = fresh(path, image, body, seed)
    found = capture(cap, off, 0x142320, 0x53F020)
    o = fresh(path, image, body, seed)
    obj = plant_prop(o, found['text'], 100)
    permit = set(ROUTE0)
    trace = []
    hook_natives(o, permit, set(), trace)
    try:
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        raise AssertionError('null model returned')
    except MemoryFault as error:
        assert error.pc == HIDE_MASK and error.addr == 0x10
    assert o.emu.mem.u32(obj + 0x90) == 0 and o.emu.mem.u64(obj + 0xC8) == 0
    assert queues(o.emu) == (0, 0, 0)
    o = fresh(path, image, body, seed)
    obj = plant_prop(o, found['text'], 100)
    block = o.emu.alloc(32)
    o.emu.mem.w64(block + 8, 0x5)
    o.emu.mem.w32(obj + 0x90, block)
    trace = []
    hook_natives(o, permit, set(), trace)
    try:
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        raise AssertionError('planted prop passed remove')
    except Exception as error:
        from difftest_arrival_stage_r5 import Boundary
        assert isinstance(error, Boundary) and error.address == 0x14598C
    assert tuple(addr for addr, _ in trace) == ROUTE0_ORDER
    assert o.emu.mem.u64(obj + 0xC8) == show_mask(0x5, 0, 0, ())
    assert calls(o.emu, ANIM_PUSH) == 0 and calls(o.emu, SLOT19) == 1
    assert queues(o.emu) == (0, 2, 0)
    print('PASS route0_prop body=%d seed=%d null=0x10 mask=0xfffffffffffffffa' % (body, seed))


def route1(path, image, off, body, seed):
    cap = fresh(path, image, body, seed)
    found = capture(cap, off, 0x14222C, 0x53F000)
    o = fresh(path, image, body, seed)
    permit = set(PERMITTED) | {0x14222C}
    model, game, expected = model_for(image, o, permit, miss=True)
    trace, _phases = drive(o, model, game, permit, {CD_FIND}, expected)
    assert tuple(addr for addr, _ in trace) == (0x14222C,)
    assert queues(o.emu) == (0, 0, 0)
    o = fresh(path, image, body, seed)
    plant_lump(o.emu, found['text'], b'\0\0\0\0')
    permit = set(PERMITTED) | {0x14222C, 0x144DB8, 0x144C00}
    model, game, expected = model_for(image, o, permit)
    trace, phases = drive(o, model, game, permit, set(), expected)
    assert tuple(addr for addr, _ in trace) == ROUTE1_ORDER
    assert phases[-1] == (None, 'absent', None)
    assert calls(o.emu, UPDATE_GRID) == 0 and calls(o.emu, OFF_GRID) == 0
    # The same names, with an object on the grid for each.
    o = fresh(path, image, body, seed)
    o.off = off
    plant_lump(o.emu, found['text'], b'\0\0\0\0')
    trace = []
    hook_natives(o, permit, set(), trace)
    grabbed = named_calls(o, (0x144DB8, 0x144C00))
    o.call(0x1ED694, 0x53F000, max_steps=4000000)
    o.call(0x1ED694, 0x53F020, max_steps=2000000)
    assert [len(name) for name in grabbed] == [8, 10, 10, 10]
    o = fresh(path, image, body, seed)
    plant_lump(o.emu, found['text'], b'\0\0\0\0')
    init_world(o)
    objs = []
    seen = set()
    for name in grabbed:
        if name in seen:
            continue
        seen.add(name)
        objs.append(plant_actor(o, name, True))
    trace = []
    hook_natives(o, permit, set(), trace)
    o.call(0x1ED694, 0x53F000, max_steps=4000000)
    o.call(0x1ED694, 0x53F020, max_steps=2000000)
    assert tuple(addr for addr, _ in trace) == ROUTE1_ORDER
    assert calls(o.emu, UPDATE_GRID) == 1 and calls(o.emu, OFF_GRID) == 3
    assert [o.call(IS_OFF, obj) for obj in objs] == [0, 1, 1, 1]
    assert [o.emu.mem.u32(obj + 0x0C) & 0x8000 for obj in objs] == [0, 0x8000, 0x8000, 0x8000]
    assert [o.emu.mem.u8(obj + 0x231) & 8 for obj in objs] == [0, 8, 8, 8]
    assert queues(o.emu) == (0, 0, 0)
    print('PASS route1 body=%d seed=%d objects=4 show=1 hide=3' % (body, seed))


def arm_cut(o, image, off, text):
    e = o.emu
    e.mem.write(LEVEL, b'authored\0')
    plant_lump(e, b'authored.lmp', b'\0' * 16)
    label = e.alloc(len(text) + 5)
    e.mem.write(label, text + b'.cut\0')
    e.mem.w32(e.mem.u32(LUMPS + 0x10) + 4, label)
    e.mem.w32(CAMERA, e.alloc(0x100))


def cut_name(path, image, off, body, seed):
    from difftest_arrival_stage_r5 import Boundary
    cap = fresh(path, image, body, seed)
    grabbed = {}

    def take(m, cap=cap, off=off):
        params = m.r[5] & 0xFFFFFFFF
        grabbed['text'] = amx_string(m.mem, cap.base, off, m.mem.s32(params + 4))
        raise Boundary('capture', 0x143F1C)
    hook_natives(cap, set(PERMITTED), set(), [])
    cap.emu.hook(0x143F1C, take)
    try:
        cap.call(0x1ED694, 0x53F000, max_steps=2000000)
        cap.call(0x1ED694, 0x53F020, max_steps=4000000)
        cap.call(0x1EDAC0, max_steps=4000000)
    except Boundary:
        pass
    assert len(grabbed['text']) == 6
    return grabbed['text']


def route2(path, image, off, body, seed, text):
    o = fresh(path, image, body, seed)
    arm_cut(o, image, off, text)
    permit = set(PERMITTED) | {0x143F1C, 0x144B44}
    model, game, expected = model_for(image, o, permit)
    trace, phases = drive(o, model, game, permit, set(), expected)
    assert tuple(addr for addr, _ in trace) == ROUTE2_ORDER
    assert phases[-1][1] == 'return'
    cut_matches(o.emu, game.mem)
    seen = []
    hook_natives(o, permit, set(), seen)
    mark = len(expected)
    game.run_post_action()
    o.call(0x1EDAC0, max_steps=4000000)
    assert [addr for addr, _ in seen] == [0x144B44]
    assert len(amx_string(o.emu.mem, o.base, off, seen[0][1][0])) == 5
    assert calls(o.emu, DTOR) == 0
    # One object of that name. A null property list skips the name walk.
    o = fresh(path, image, body, seed)
    arm_cut(o, image, off, text)
    init_world(o)
    obj = plant_actor(o, amx_string(o.emu.mem, o.base, off, seen[0][1][0]), True)
    before = o.emu.mem.u32(0x5F86F8)
    trace = []
    hook_natives(o, permit, set(), trace)
    o.call(0x1ED694, 0x53F000, max_steps=4000000)
    o.call(0x1ED694, 0x53F020, max_steps=4000000)
    o.call(0x1EDAC0, max_steps=4000000)
    o.call(0x1EDAC0, max_steps=4000000)
    assert calls(o.emu, DTOR) == 1
    assert calls(o.emu, STR_WALK) == 0
    assert calls(o.emu, HANDLE_CLEAR) == 3
    assert calls(o.emu, POOL_FREE) == 0
    assert o.emu.mem.u32(0x5F86F8) == before
    assert o.emu.mem.u32(obj + 0x48) == 0x5122A8
    # First cutscene frame. Each argument starts from a fresh cut_start.
    from difftest_arrival_stage_r5 import Boundary
    for argument in (1, 0):
        o = fresh(path, image, body, seed)
        arm_cut(o, image, off, text)
        hook_natives(o, set(PERMITTED) | {0x143F1C}, set(), [])
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        o.call(0x1EDAC0, max_steps=4000000)
        e = o.emu
        e.hooks.clear()
        e.record_calls = True
        e.calls.clear()
        e.mem.w32(0x4039AC, 0x11111111)
        e.hook(CUT_HELPER, stop_at(CUT_HELPER))
        try:
            o.call(CUT_RUN, argument, max_steps=2000000)
            raise AssertionError('frame returned')
        except Boundary as hit:
            assert hit.address == CUT_HELPER
        assert e.mem.u32(0x4039AC) == 0 and e.mem.u8(0x44FCD2) == 0
        assert [record.target for record in e.calls if record.target in {LIGHT, CUT_SETUP, CUT_HELPER}] == [
            LIGHT, CUT_SETUP, CUT_HELPER]
    print('PASS route2 body=%d seed=%d delete=dtor frame=0x14f498' % (body, seed))


def main():
    path, manifest = sys.argv[1:3]
    require_local(path)
    require_local(manifest)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    images = [private_script(part) for part in json.loads(Path(manifest).read_text())]
    assert len(images) == 3
    offs = [data_off(image) for image in images]
    for seed in (7, 20973):
        mask_direct(path, seed)
    bodies = range(12) if len(sys.argv) < 4 else [int(part) for part in sys.argv[3].split(',')]
    for body in bodies:
        for seed in (7, 20973):
            route0(path, images[0], body, seed)
            route0_prop(path, images[0], offs[0], body, seed)
            route1(path, images[1], offs[1], body, seed)
            text = cut_name(path, images[2], offs[2], body, seed)
            route2(path, images[2], offs[2], body, seed, text)
    print('PASS arrival_stage_r6 bodies=%d seeds=2' % len(list(bodies)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (
            type(error).__name__, getattr(error, 'address', getattr(error, 'addr', 0))))
        raise
