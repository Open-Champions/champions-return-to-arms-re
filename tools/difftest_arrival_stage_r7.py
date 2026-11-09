#!/usr/bin/env python3
"""Arrival round 7. Original functions in tools/ee_emu.py, past the round-6 stops.

Fixtures are disclosed where they are made: the boot stack-guard fill, a 16-byte
map at the timer-0 register, one WakeupThread return, a sealed camera, synthetic
model, clip and property blocks, and a resident lump copied from the private
archive. Deci2 function 0x10 uses the opt-in handler from t3/research-death-reload.
Output is addresses, lengths and counts.
"""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest  # noqa: F401  (preload before tools/dis.py can shadow stdlib dis)
from difftest_arrival_stage_r5 import (
    CAMERA, CD_FIND, LEVEL, LUMP_COUNT, LUMPS, PERMITTED, POST, ROUTE0, ROUTE0_ORDER,
    ROUTE2_ORDER, Boundary, amx_string, capture, data_off, drive, fresh,
    hook_natives, model_for, plant_prop, queues, seal_camera,
)
import difftest_arrival_stage_r5 as R5
from difftest_arrival_stage_r6 import (
    ANIM_PUSH, CUT_RUN, CUT_SETUP, DEFERRED, DTOR, HANDLE_CLEAR, NAME_COUNT,
    NAME_REMOVE, POOL_FREE, PRINTF, SET_FLAG, SLOT19, STR_WALK, ITEM_TEST,
    ROUTE0_FULL, arm_cut, cut_name, init_world, overlaps, plant_actor, preset_flags, stop_at,
)
from difftest_arrival_state_r4 import prepared
from difftest_loading import SHA256
from difftest_loading_arrival_r4 import RECORD, TABLE, private_script, require_local
from ee_emu import EE, CpuTrap, MemoryFault, s64
from gob import gob_entries, lmp_entries

# Producer of the request.
START_SELECT, SELECT_START, ARENA_PICK = 0x1E3BA0, 0x2245B8, 0x304BC8
FINISH, HUB_NAME, FADE_WAIT = 0x22A360, 0x1EC300, 0x322954
DEST, PENDING, ORIENT = 0x4FDC30, 0x41B6D0, 0x41B720
TEX_NAME, LOAD_REQUESTED, LOAD_LEVEL = 0x44FE18, 0x320EDC, 0x1E55C0
TEXT_HUB, TEXT_EMPTY, TEXT_HUB_A, TEXT_HUB_B = 0x53D3E8, 0x53D330, 0x53D6B8, 0x53D6C0
TEXT_BOOT, MISSIONS, MISSION_STRIDE = 0x554898, 0x4FE540, 0x34
MODE_B, SELECT_FLAG, DIFFICULTY = 0x4F7120, 0x4F70A0, 0x4F719C
DECISION, CHOICE, COMPLETE = 0x4C1B, 0x4C1A, 0x4BBF
# Loader after 0x322e58.
WARM_START, WARM, LOOP_HEAD = 0x322E58, 0x506048, 0x322EB0
GUARD, GUARD_SIZE, GUARD_FILL_INSN = 0x1FC0000, 0x1400, 0x19D230
TIMER, WAKE_RA, THREAD_WORD = 0x10000000, 0x17FD20, 0x7CFD04
DECI2, REFER, LS_STOP, LS_THREAD, LS_BYTE = 0x352E10, 0x3528E4, 0x3224D8, 0x506090, 0x5060A0
REBUILD, DRAW, POLL, STREAM, WAKE, IDLE = 0x1E72F8, 0x1EBC18, 0x172CA8, 0x17D830, 0x17FCE0, 0x17FE88
CAM_UPDATE, EQUIP_BUSY, SHOP, LUMP_LOAD = 0x203400, 0x1A30B0, 0x1C7AF8, 0x173558
WARM_PASS = (REBUILD, DRAW, POLL, STREAM, WAKE, IDLE)
TEXT_SHOP_HUB = 0x554678
# Prop and slot 19.
ANIM_EVAL, COLLIDE_A, COLLIDE_B, WORLD_WORD = 0x170BC8, 0x182B00, 0x182C98, 0x44FDC8
# Delete.
STRNCMP, FREE_TABLE = 0x3B91D8, 0x403A1C
FIND_OBJECTS = 0x14BF58
STRCPY, STRCPY_END = 0x3B868C, 0x3B87A0
ANIM_PUSH_END, ANIM_EVAL_END = 0x1708BC, 0x170C80
# Cut.
LUMP_FIXUP, CUT_ADVANCE, CUT_ACTIVE, CUT_SETUP_BYTE = 0x1717D0, 0x199214, 0x44FCD0, 0x44FCD2
CUT_CLOCK, CUT_ACTORS = 0x44FCE0, 0x83D188
KEEP = ('.cut', '.bin', '.dbin')
LOADER_REGS = {16: 0x5541F0, 17: 0x420000, 19: 0x400000, 20: 0x550000,
               21: 0x450000, 22: 0x450000, 23: 0x420000, 30: 0x500000}

UNIFORM = {}


def same(key, value):
    """Record one result per key; every body and seed must agree."""
    if key in UNIFORM:
        assert UNIFORM[key] == value, (key, UNIFORM[key], value)
    else:
        UNIFORM[key] = value
    return value


def calls(e, target):
    return sum(1 for record in e.calls if record.target == target)


def stores_from(writes, address, length, lo, hi):
    touching = overlaps(writes, address, length)
    assert touching, 'no recorded store at 0x%x' % address
    assert all(lo <= pc < hi for pc, _a, _s, _v in touching), touching
    return touching


def last_store(writes, address, length, lo, hi):
    touching = overlaps(writes, address, length)
    assert touching and lo <= touching[-1][0] < hi, touching
    return touching[-1]


def plant_guard(e):
    """The low 0x1400 bytes engine_init fills with 0xa5 (0x19d230/0x19d244)."""
    assert e.mem.s16(GUARD_FILL_INSN) == -0x5B
    e.mem.write(GUARD, b'\xa5' * GUARD_SIZE)


def plant_camera(e):
    camera = e.alloc(0x100)
    e.mem.w32(CAMERA, camera)
    seal_camera(e, camera)
    return camera


def wake_handler(emu):
    """WakeupThread (syscall 51) only from 0x17fce0. That caller overwrites v0 at
    0x17fd24 before reading it. The retail result is unknown; v0 = 0 is a model."""
    if s64(emu.r[3]) == 51 and emu.r[31] & 0xFFFFFFFF == WAKE_RA:
        emu.wakes.append(emu.r[4] & 0xFFFFFFFF)
        emu.r[2] = 0
        return
    EE._dispatch_opt_in_syscall(emu)


# ---- A. the request a new game makes, and the loader split -------------------------
def producer(path, archives, body, seed):
    o = prepared(path, body, seed)
    e = o.emu
    assert e.mem.u32(MODE_B) == 0 and e.mem.u32(SELECT_FLAG) == 0
    # Observed: main copies TEXT_BOOT (0x323edc) and frontend_start copies
    # TEXT_INTRO (0x1e2094) into the request.
    assert e.mem.u16(0x323EDC) == TEXT_BOOT & 0xFFFF and e.mem.s16(0x1E2094) == 0x53D0D0 - 0x540000
    hub, hub_b = e.mem.cstr(TEXT_HUB_A), e.mem.cstr(TEXT_HUB_B)
    assert e.mem.cstr(TEXT_HUB) == hub and e.mem.cstr(TEXT_EMPTY) == ''
    # A1. frontend_startPlayerSelect stores the destination before playerSel_start.
    e.hooks.clear()
    e.record_writes = True
    e.writes.clear()
    e.mem.write(DEST, b'\xa5' * 16)
    e.hook(SELECT_START, stop_at(SELECT_START))
    try:
        o.call(START_SELECT, max_steps=200000)
        raise AssertionError('player select returned')
    except Boundary as hit:
        assert hit.address == SELECT_START
    assert e.mem.cstr(DEST) == hub
    pcs = sorted({pc for pc, _a, _s, _v in stores_from(e.writes, DEST, 4, START_SELECT, SELECT_START)})
    assert pcs == [0x1E3C44, 0x1E3C48], pcs
    assert ARENA_PICK not in {c.target for c in e.calls}
    for flag, value in ((SELECT_FLAG, 1), (MODE_B, 1)):
        c = prepared(path, body, seed)
        c.emu.hooks.clear()
        c.emu.mem.write(DEST, b'\xa5' * 16)
        c.emu.mem.w32(flag, value)
        c.emu.hook(SELECT_START, stop_at(SELECT_START))
        c.emu.hook(ARENA_PICK, stop_at(ARENA_PICK))
        try:
            c.call(START_SELECT, max_steps=200000)
            raise AssertionError('control returned')
        except Boundary as hit:
            if flag == MODE_B:
                assert hit.address == ARENA_PICK
            else:
                assert hit.address == SELECT_START and c.emu.mem.u8(DEST) == 0
                assert c.emu.mem.u8(DEST + 1) == 0xA5
    # A2. game_getHubName: hub_b only with decision, choice and mission 1 complete.
    level = e.mem.u32(DIFFICULTY)
    sites = (RECORD + DECISION, RECORD + CHOICE, RECORD + COMPLETE + 13 * level + 1)
    masks = (1 << level, 1 << level, 2)
    saved = [e.mem.u8(at) for at in sites]
    got = []
    for combo in range(8):
        for bit, (at, mask) in enumerate(zip(sites, masks)):
            value = saved[bit] | mask if combo >> bit & 1 else saved[bit] & ~mask
            e.mem.w8(at, value)
        e.hooks.clear()
        got.append(e.call(HUB_NAME) & 0xFFFFFFFF)
    assert got == [TEXT_HUB_A] * 7 + [TEXT_HUB_B], [hex(v) for v in got]
    for at, value in zip(sites, saved):
        e.mem.w8(at, value)
    # A3. playerSel_finish(0) copies the destination into the request.
    results = []
    for all_set in (False, True):
        f = prepared(path, body, seed)
        fe = f.emu
        plant_guard(fe)
        plant_camera(fe)
        if all_set:
            for at, mask in zip(sites, masks):
                fe.mem.w8(at, fe.mem.u8(at) | mask)
        fe.hooks.clear()
        fe.hook(SELECT_START, stop_at(SELECT_START))
        try:
            f.call(START_SELECT, max_steps=200000)
        except Boundary:
            pass
        fe.hooks.clear()
        fe.calls.clear()
        fe.record_writes = True
        fe.writes.clear()
        fe.mem.write(PENDING, b'\xa5' * 0x51)
        assert f.call(FINISH, 0, max_steps=4000000) is not None
        want = hub_b if all_set else hub
        assert fe.mem.cstr(PENDING) == want and fe.mem.u8(ORIENT) == 0xFF
        stores_from(fe.writes, PENDING, len(want) + 1, STRCPY, STRCPY_END)
        assert any(pc == 0x22A484 and a == ORIENT and v == 0xFF for pc, a, _s, v in fe.writes)
        assert calls(fe, HUB_NAME) == 1 and calls(fe, FADE_WAIT) == 1
        results.append(fe.mem.cstr(PENDING))
        if not all_set:
            finished = f
    # A4. mainloop_loadRequestedWorld splits the request and enters game_loadLevel.
    mission1 = e.mem.cstr(e.mem.u32(MISSIONS + 8))
    boot = e.mem.cstr(TEXT_BOOT)
    split = {}
    for name in (hub, mission1, boot):
        s = finished if name == hub else prepared(path, body, seed)
        se = s.emu
        if name != hub:
            plant_guard(se)
            plant_camera(se)
            se.mem.write(PENDING, name.encode() + b'\0')
        se.mem.write(LEVEL, b'\xa5' * 16)
        se.mem.write(TEX_NAME, b'\xa5' * 16)
        se.hooks.clear()
        se.calls.clear()
        se.record_writes = True
        se.writes.clear()
        se.hook(LOAD_LEVEL, stop_at(LOAD_LEVEL))
        try:
            s.call(LOAD_REQUESTED, max_steps=8000000)
            raise AssertionError('loader returned before game_loadLevel')
        except Boundary as hit:
            assert hit.address == LOAD_LEVEL
        assert se.r[4] & 0xFFFFFFFF == LEVEL
        assert se.mem.cstr(LEVEL) == name and se.mem.cstr(TEX_NAME) == name
        assert se.mem.u8(PENDING) == 0
        pcs = {pc for pc, _a, _s, _v in stores_from(se.writes, LEVEL, len(name) + 1, LOAD_REQUESTED, 0x321524)}
        assert pcs == {0x3210AC, 0x3210D8}, pcs
        stores_from(se.writes, TEX_NAME, len(name) + 1, STRCPY, STRCPY_END)
        split[name] = [i for i, p in enumerate(archives) if Path(p).stem.lower() == name]
    ordinals = (split[hub], split[mission1], split[boot])
    assert ordinals == ([0], [2], [1]), ordinals
    same('producer', (tuple(results), ordinals))
    print('PASS producer body=%d seed=%d dest_stores=0x1e3c44,0x1e3c48 hub_name=%s finish=%s,%s '
          'split=game_loadLevel ordinals=new:%d,mission1:%d,boot:%d' % (
              body, seed, ''.join('1' if v == TEXT_HUB_B else '0' for v in got),
              len(results[0]), len(results[1]), ordinals[0][0], ordinals[1][0], ordinals[2][0]))


# ---- B. the loader from mainloop_startWarmup to loadscreen_stop --------------------
def route0_entry(path, image, body, seed):
    original = R5.Services.call

    def answer(self, name, *args):
        if name == 'inventory_findItemBySubstring':
            return (-1, 0)
        return original(self, name, *args)
    R5.Services.call = answer
    try:
        o = fresh(path, image, body, seed)
        preset_flags(o.emu.mem)
        permit = set(ROUTE0) | {0x14598C, SET_FLAG, ITEM_TEST}
        model, game, expected = model_for(image, o, permit)
        trace, _phases = drive(o, model, game, permit, set(), expected)
    finally:
        R5.Services.call = original
    assert tuple(a for a, _ in trace) == ROUTE0_FULL
    assert queues(o.emu) == (0, 2, 0)
    return o


def loader(path, image, body, seed, shop=None):
    """shop None: fixture level name. 'stop': hub, stop before the disc lookup.
    'miss': hub, let the lookup miss."""
    o = route0_entry(path, image, body, seed)
    e = o.emu
    level = e.mem.cstr(TEXT_SHOP_HUB).encode() if shop else None
    assert all(e.mem.u32(at) >> 26 == 0x0F for at in (WAKE_RA, WAKE_RA + 4)) and e.mem.u32(WAKE_RA + 4) >> 16 & 31 == 2
    e.hooks.clear()
    e.calls.clear()
    e.record_calls = True
    e.install_deci2_kputs()
    e.wakes = []
    e.syscall_handler = wake_handler
    plant_guard(e)
    e.mem.map(TIMER, 0x10)
    e.mem.w32(TIMER, 0x11111111)
    e.mem.w32(LS_BYTE, 0)
    if level is not None:
        e.mem.write(LEVEL, level + b'\0')
        if shop == 'stop':
            e.hook(CD_FIND, stop_at(CD_FIND))
    for reg, value in LOADER_REGS.items():
        e.r[reg] = value
    e.record_writes = True
    e.writes.clear()
    e.r[31] = e.RETURN_ADDR
    e.r[29] = o.SP
    e.jump(WARM_START)
    try:
        e.run(max_steps=40000000)
        raise AssertionError('loader returned')
    except Boundary as hit:
        assert shop == 'stop' and hit.address == CD_FIND
        made = [c.target for c in e.calls if c.target in {SHOP, LUMP_LOAD, CD_FIND, LS_STOP}]
        assert made == [SHOP, LUMP_LOAD, CD_FIND], made
        first = [c for c in e.calls if c.target == SHOP][0]
        assert (first.site, first.args[1] & 0xFF) == (0x3230C4, 1)
        return len(e.wakes)
    except MemoryFault as fault:
        assert shop == 'miss' and (fault.pc, fault.addr) == (0x17363C, 0)
        assert calls(e, CD_FIND) == 1 and calls(e, LS_STOP) == 0
        return len(e.wakes)
    except CpuTrap:
        assert level is None
    assert e.cur == REFER and e.r[31] & 0xFFFFFFFF == 0x322500 and s64(e.r[3]) == 48
    assert e.r[4] & 0xFFFFFFFF == e.mem.u32(LS_THREAD) == 0xFFFFFFFF
    assert e.mem.u8(LS_BYTE) == 1
    assert any(pc == 0x3224EC and a == LS_BYTE and v == 1 for pc, a, _s, v in e.writes)
    assert calls(e, DEFERRED) == 1 and calls(e, ITEM_TEST) == 0 and queues(e) == (2, 0, 1)
    assert calls(e, DECI2) == 4 and calls(e, PRINTF) == 4 and calls(e, 0x13DCD0) == 0
    assert len([c for c in e.calls if c.target == 0x3B8534 and 0x323064 <= c.site < 0x3230F8]) == 4
    order = [c.target for c in e.calls if c.target in set(WARM_PASS)]
    assert order == list(WARM_PASS) * 10, order
    assert e.wakes == [e.mem.u32(THREAD_WORD)] * 10 == [0] * 10
    for absent in (CUT_RUN, CAM_UPDATE, EQUIP_BUSY, SHOP):
        assert calls(e, absent) == 0, hex(absent)
    assert e.mem.u32(WARM) == 0
    warm = [(pc, v) for pc, _a, _s, v in overlaps(e.writes, WARM, 4)]
    assert warm[0][1] == 10 and 0x322934 <= warm[0][0] < 0x322954
    assert [v for _pc, v in warm[1:]] == list(range(9, -1, -1))
    assert all(pc == 0x322F30 for pc, _v in warm[1:])
    timer = overlaps(e.writes, TIMER, 4)
    assert e.mem.u32(TIMER) == 0 and [(pc, v) for pc, _a, _s, v in timer] == [(0x322F04, 0)] * 10
    assert not any(c.stubbed for c in e.calls) and not e.patches
    return same('loader', (len(e.wakes), len(warm), calls(e, DECI2)))


# ---- C. a clip pointer and slot 19's value -----------------------------------------
def prop_case(path, image, off, body, seed, clip, flags, capacity, collide):
    cap = fresh(path, image, body, seed)
    found = capture(cap, off, 0x142320, 0x53F020)
    o = fresh(path, image, body, seed)
    e = o.emu
    obj = plant_prop(o, found['text'], 100)
    block = e.alloc(32)
    e.mem.w64(block + 8, 0x5)
    e.mem.w32(obj + 0x90, block)
    clip_block = 0
    if clip:
        clip_block = e.alloc(16)
        e.mem.w32(clip_block + 4, clip)
        e.mem.w32(obj + 0x128, clip_block)
    e.mem.w32(obj + 0x12C, flags)
    e.mem.w8(obj + 0x9D, capacity)
    e.mem.w32(obj + 0x11C, collide)
    e.mem.w32(obj + 0x17C, 0x22222222)
    e.record_writes = True
    e.writes.clear()
    trace = []
    hook_natives(o, set(ROUTE0), set(), trace)
    try:
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        raise AssertionError('prop entry returned')
    except Boundary as hit:
        stop = ('native', hit.address)
    except MemoryFault as fault:
        stop = ('fault', fault.pc, fault.addr)
    slot = [c for c in e.calls if c.target == SLOT19]
    assert len(slot) == 1 and slot[0].args[0] & 0xFFFFFFFF == obj
    assert slot[0].args[1] & 0xFFFFFFFF == flags & 1
    return o, obj, clip_block, stop, trace


def props(path, image, off, body, seed):
    out = []
    # 1. Clip present, zero capacity byte: no push; +0x17c = clip[4] + 1.
    o, obj, clip, stop, trace = prop_case(path, image, off, body, seed, 5, 0, 0, 0)
    e = o.emu
    assert stop == ('native', 0x14598C) and tuple(a for a, _ in trace) == ROUTE0_ORDER
    push = [c for c in e.calls if c.target == ANIM_PUSH]
    assert [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF) for c in push] == [
        (obj + 0x98, clip, 6)]
    assert calls(e, ANIM_EVAL) == 1 and e.mem.u8(obj + 0x9C) == 0
    assert not overlaps(e.writes, obj + 0xA0, 0x20)
    assert e.mem.u32(obj + 0x17C) == 6
    assert overlaps(e.writes, obj + 0x17C, 4)[-1][:1] == (0x23D764,)
    assert queues(e) == (0, 2, 0)
    out.append('cap0:17c=6')
    # 2-3. Capacity 4: one 32-byte entry. +0x12c bit 0x2 selects mode 3, else 6.
    for flags, mode in ((0, 6), (2, 3)):
        o, obj, clip, stop, trace = prop_case(path, image, off, body, seed, 5, flags, 4, 0)
        e = o.emu
        assert stop == ('native', 0x14598C)
        assert e.mem.u8(obj + 0x9C) == 1 and e.mem.u16(obj + 0x9E) == mode
        entry = obj + 0xA0
        assert e.mem.u32(entry) == clip and e.mem.u16(entry + 0x1C) == mode
        assert [e.mem.u32(entry + k) for k in (8, 0xC, 0x10, 0x14, 0x18)] == [
            0x3F800000, 0, 0x3F800000, 0, 0x40A00000]
        for at, size in ((obj + 0x9C, 1), (obj + 0x9E, 2), (entry, 4), (entry + 0x1C, 2)):
            last_store(e.writes, at, size, ANIM_PUSH, ANIM_PUSH_END)
        last_store(e.writes, entry + 0x18, 4, ANIM_EVAL, ANIM_EVAL_END)
        out.append('cap4:mode=%d' % mode)
    # 4. Value 1, collision bit clear: +0xc bit 0 set, no collision call.
    o, obj, clip, stop, trace = prop_case(path, image, off, body, seed, 0, 1, 0, 0)
    e = o.emu
    assert stop == ('native', 0x14598C) and calls(e, ANIM_PUSH) == 0
    assert e.mem.u32(obj + 0x0C) == 0x10000001 and calls(e, COLLIDE_A) == 0
    assert overlaps(e.writes, obj + 0x0C, 4)[-1][0] == 0x23D878
    out.append('value1:c=0x10000001')
    # 5. Value 1 with +0x11c bit 0: 0x182b00 on the world word 0x44fdc8, which is 0.
    o, obj, clip, stop, trace = prop_case(path, image, off, body, seed, 0, 1, 0, 1)
    e = o.emu
    assert e.mem.u32(WORLD_WORD) == 0
    assert stop == ('fault', 0x182B08, 0x20), stop
    hit = [c for c in e.calls if c.target == COLLIDE_A]
    assert len(hit) == 1 and hit[0].site == 0x23D7E0 and hit[0].args[0] & 0xFFFFFFFF == 0
    assert hit[0].args[2] & 0xFFFFFFFF == 0 and calls(e, COLLIDE_B) == 0
    assert e.mem.u32(obj + 0x0C) == 0x10000000 and queues(e) == (0, 0, 0)
    out.append('collide:fault=0x182b08/0x20')
    return same('props', tuple(out))


# ---- D. delete with and without a property list ------------------------------------
def replacement_name(path, image, off, body, seed, text):
    o = fresh(path, image, body, seed)
    arm_cut(o, image, off, text)
    permit = set(PERMITTED) | {0x143F1C, 0x144B44}
    model, game, expected = model_for(image, o, permit)
    drive(o, model, game, permit, set(), expected)
    seen = []
    hook_natives(o, permit, set(), seen)
    game.run_post_action()
    o.call(0x1EDAC0, max_steps=4000000)
    assert [a for a, _ in seen] == [0x144B44]
    return amx_string(o.emu.mem, o.base, off, seen[0][1][0])


def delete(path, image, off, body, seed, text, name):
    out = []
    for with_props in (False, True):
        o = fresh(path, image, body, seed)
        arm_cut(o, image, off, text)
        init_world(o)
        e = o.emu
        obj = plant_actor(o, name, True)
        entry = 0
        if with_props:
            other = e.alloc(16)
            e.mem.write(other, b'kind=1\0')
            entry = e.alloc(len(name) + 8)
            e.mem.write(entry, b'name=' + name + b'\0')
            plist = e.alloc(16)
            e.mem.w32(plist, other)
            e.mem.w32(plist + 4, entry)
            e.mem.w32(obj + 0x2C, plist)
        assert e.mem.u32(NAME_COUNT) == 1
        e.record_writes = True
        e.writes.clear()
        trace = []
        hook_natives(o, set(PERMITTED) | {0x143F1C, 0x144B44}, set(), trace)
        o.call(0x1ED694, 0x53F000, max_steps=4000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        o.call(0x1EDAC0, max_steps=4000000)
        o.call(0x1EDAC0, max_steps=4000000)
        dtor = [c for c in e.calls if c.target == DTOR]
        assert len(dtor) == 1 and dtor[0].site == 0x144BC4 and dtor[0].args[1] & 0xFFFFFFFF == 3
        assert calls(e, HANDLE_CLEAR) == 3
        freed = [w for w in e.writes if POOL_FREE <= w[0] < 0x1504C8]
        assert len(freed) == 2, freed
        (pc_a, head, size_a, value_a), (pc_b, at_b, size_b, value_b) = freed
        assert (pc_a, size_a, value_a) == (0x1504BC, 4, obj)
        assert FREE_TABLE <= head < FREE_TABLE + 0x100 and (head - FREE_TABLE) % 16 == 0
        assert (pc_b, at_b, size_b) == (0x1504C4, obj, 4)
        assert e.mem.u32(head) == obj and e.mem.u32(obj) == value_b
        removes = [c for c in e.calls if c.target == NAME_REMOVE]
        if with_props:
            assert [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF) for c in removes] == [
                (0x14D19C, entry + 5, obj)]
            assert {c.site for c in e.calls if c.target == STRNCMP} == {0x14D060, 0x14D148}
            assert calls(e, STRNCMP) == 6
            assert e.mem.u32(NAME_COUNT) == 0
            touching = overlaps(e.writes, NAME_COUNT, 4)
            assert [(pc, s, v) for pc, _a, s, v in touching] == [(0x14BE84, 4, 0)], touching
            look = e.alloc(16)
            e.mem.write(look, name + b'\0')
            found = e.alloc(0x40)
            e.mem.write(found, b'\x5a' * 0x40)
            e.calls.clear()
            o.call(FIND_OBJECTS, look, found, 0x10)
            assert e.mem.u32(found) == 0
            out.append('props:remove=1,names=0,free=1')
        else:
            assert not removes and calls(e, STRNCMP) == 0
            assert e.mem.u32(NAME_COUNT) == 1 and not overlaps(e.writes, NAME_COUNT, 4)
            out.append('none:names=1,free=1')
        assert not any(c.stubbed for c in e.calls) and not e.patches
    return same('delete', tuple(out))


# ---- E. cut_setup on a resident copy of the level lump, then cutscene frames --------
def level_lump(archive):
    data = Path(archive).read_bytes()
    for name, start, size in gob_entries(data):
        lump = data[start:start + size]
        entries = lmp_entries(lump)
        if any(Path(n).suffix.lower() == '.scr' for n, _o, _s in entries):
            return name, lump, entries
    raise AssertionError('no level lump')


def resident_lump(e, archive):
    """The lump layout of the archive, restricted to KEEP entries in archive order:
    count, records, packed names, data on 0x80. Bytes stay in emulator memory."""
    name, lump, entries = level_lump(archive)
    kept = [(n, o, s) for n, o, s in entries if n.lower().endswith(KEEP)]
    blob = bytearray(4 + 12 * len(kept))
    struct.pack_into('<I', blob, 0, len(kept))
    names = []
    for n, _o, _s in kept:
        names.append(len(blob))
        blob += n.encode('latin1') + b'\0'
    for index, (n, o, s) in enumerate(kept):
        blob += bytes(-len(blob) % 0x80)
        struct.pack_into('<III', blob, 4 + 12 * index, names[index], len(blob), s)
        blob += lump[o:o + s]
    base = e.alloc(len(blob) + 0x100)
    e.mem.write(base, bytes(blob))
    return name, base, len(blob), len(kept), len(entries)


def cut_refusals(path, image, off, body, seed, text):
    """The round-6 fixture lump, without the 0x14f498 stop: two refusals."""
    out = []
    for tex in (None, True):
        o = fresh(path, image, body, seed)
        arm_cut(o, image, off, text)
        hook_natives(o, set(PERMITTED) | {0x143F1C}, set(), [])
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        o.call(0x1EDAC0, max_steps=4000000)
        e = o.emu
        e.hooks.clear()
        e.calls.clear()
        e.install_deci2_kputs()
        assert e.mem.u8(TEX_NAME) == 0
        if tex:
            e.mem.write(TEX_NAME, e.mem.read(LEVEL, 16))
        try:
            o.call(CUT_RUN, 1, max_steps=6000000)
            raise AssertionError('fixture frame returned')
        except MemoryFault as fault:
            stop = (fault.pc, fault.addr)
        made = [c.target for c in e.calls]
        if tex:
            assert stop == (0x2168A0, 0) and CD_FIND not in made and 0x216860 in made
        else:
            assert stop == (0x17363C, 0) and made.count(CD_FIND) == 1 and 0x1964D4 in made
        out.append('0x%x' % stop[0])
    return same('cut_refusals', tuple(out))


def cut(path, archive, image, off, body, seed, text):
    o = fresh(path, image, body, seed)
    e = o.emu
    lump_name, base, size, kept, total = resident_lump(e, archive)
    e.hooks.clear()
    e.calls.clear()
    o.call(LUMP_FIXUP, base, max_steps=4000000)
    assert not any(c.stubbed for c in e.calls)
    count = e.mem.u16(base)
    stem = Path(lump_name).stem.encode()
    e.mem.write(LEVEL, stem + b'\0')
    e.mem.write(TEX_NAME, stem + b'\0')
    e.mem.write(LUMPS, lump_name.encode() + bytes(16 - len(lump_name)))
    e.mem.w32(LUMPS + 0x10, base)
    e.mem.w32(LUMPS + 0x14, 0)
    e.mem.w32(LUMPS + 0x18, size)
    e.mem.w32(LUMP_COUNT, 1)
    plant_camera(e)
    trace = []
    hook_natives(o, set(PERMITTED) | {0x143F1C}, set(), trace)
    o.call(0x1ED694, 0x53F000, max_steps=2000000)
    o.call(0x1ED694, 0x53F020, max_steps=4000000)
    o.call(0x1EDAC0, max_steps=4000000)
    assert tuple(a for a, _ in trace) == ROUTE2_ORDER
    header = e.mem.u32(0x44FCE4)
    assert base <= header < base + size and e.mem.u8(CUT_ACTIVE) == 1
    assert e.mem.u32(WARM) == 10 and e.mem.u32(CUT_CLOCK) == 1 and e.mem.u8(CUT_SETUP_BYTE) == 0
    assert e.mem.u8(POST) != 0
    every = set()
    for index in range(191):
        if not e.mem.u32(TABLE + 8 * index):
            break
        every.add(e.mem.u32(TABLE + 8 * index + 4))
    natives = []
    hook_natives(o, every, set(), natives)
    e.install_deci2_kputs()
    e.record_writes = True
    e.writes.clear()
    # Warm-up frames: argument 1 while g_warmupFrames is 10.
    for frame in range(3):
        mark = len(e.calls)
        assert o.call(CUT_RUN, 1, max_steps=6000000) == 0
        made = [c.target for c in e.calls[mark:]]
        assert made.count(CUT_SETUP) == (1 if frame == 0 else 0) and CUT_ADVANCE not in made
        assert e.mem.u32(CUT_CLOCK) == 1 and e.mem.u8(CUT_ACTIVE) == 1
    setup = overlaps(e.writes, CUT_SETUP_BYTE, 1)
    assert e.mem.u8(CUT_SETUP_BYTE) == 1 and [(pc, v) for pc, _a, _s, v in setup] == [(0x199BBC, 1)]
    actors = e.mem.u32(CUT_ACTORS)
    # Argument 1 never advances, even at g_warmupFrames 0.
    e.mem.w32(WARM, 0)
    mark = len(e.calls)
    assert o.call(CUT_RUN, 1, max_steps=6000000) == 0
    assert CUT_ADVANCE not in [c.target for c in e.calls[mark:]] and e.mem.u32(CUT_CLOCK) == 1
    # Task frames: argument 0 with g_warmupFrames 0, the value the warm-up loop leaves.
    e.record_writes = False
    advanced = 0
    frames = 0
    last = prev = None
    while e.mem.u8(CUT_ACTIVE) and frames < 4000:
        e.calls.clear()
        clock = e.mem.u32(CUT_CLOCK)
        mark = len(natives)
        assert o.call(CUT_RUN, 0, max_steps=6000000) == 0
        made = [c.target for c in e.calls]
        assert made.count(CUT_ADVANCE) == 1 and CUT_SETUP not in made
        if e.mem.u8(CUT_ACTIVE):
            assert len(natives) == mark and e.mem.u8(POST) != 0
        assert e.mem.u32(CUT_CLOCK) == clock + 1
        assert not any(c.stubbed for c in e.calls)
        prev, last = last, set(made)
        advanced += 1
        frames += 1
    assert e.mem.u8(CUT_ACTIVE) == 0
    assert [a for a, _ in natives] == [0x144B44]
    assert len(amx_string(e.mem, o.base, off, natives[0][1][0])) == 5
    order = [(c.target, c.site) for c in e.calls if c.target in {0x322934, 0x2072E8, 0x1EDAC0}]
    assert order == [(0x322934, 0x199F3C), (0x2072E8, 0x199F5C), (0x1EDAC0, 0x199F6C)], order
    assert e.mem.u8(POST) == 0 and e.mem.u32(WARM) == 10 and queues(e) == (0, 0, 0)
    end_clock = e.mem.u32(CUT_CLOCK)
    ending = sorted(last - prev)
    # One more frame in the state the end left (g_warmupFrames 10): no advance, no native.
    e.calls.clear()
    assert o.call(CUT_RUN, 0, max_steps=6000000) == 0
    assert CUT_ADVANCE not in [c.target for c in e.calls] and e.mem.u32(CUT_CLOCK) == end_clock
    assert [a for a, _ in natives] == [0x144B44] and e.mem.u32(WARM) == 10
    assert not e.patches and e.follow is None
    result = same('cut', (kept, total, count, actors, advanced, end_clock, tuple(ending)))
    print('PASS cut body=%d seed=%d kept=%d/%d fixed=%d actors=%d warm_frames=3 task_frames=%d '
          'clock=1->%d end=0x322934@0x199f3c,0x2072e8@0x199f5c,0x1edac0@0x199f6c native=0x144b44 '
          'post=0 warm=10 new_targets=%d' % (body, seed, kept, total, count, actors, advanced,
                                              end_clock, len(ending)))
    return result


def main():
    path, manifest = sys.argv[1:3]
    require_local(path)
    require_local(manifest)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    archives = json.loads(Path(manifest).read_text())
    for archive in archives:
        require_local(archive)
    images = [private_script(p) for p in archives]
    assert len(images) == 3
    offs = [data_off(image) for image in images]
    bodies = range(12) if len(sys.argv) < 4 else [int(part) for part in sys.argv[3].split(',')]
    for body in bodies:
        for seed in (7, 20973):
            producer(path, archives, body, seed)
            wakes = loader(path, images[0], body, seed)
            shop_wakes = loader(path, images[0], body, seed, shop='stop')
            assert loader(path, images[0], body, seed, shop='miss') == shop_wakes == 10
            print('PASS loader body=%d seed=%d passes=%d wakes=%d deci2=4 queue=2,0,1 '
                  'stop=syscall48@0x3528e4 ra=0x322500 hub_shop=0x1c7af8>0x173558>0x1724fc miss=0x17363c wakes=%d' % (
                      body, seed, wakes[1] - 1, wakes[0], shop_wakes))
            print('PASS props body=%d seed=%d %s' % (body, seed, ' '.join(props(
                path, images[0], offs[0], body, seed))))
            text = cut_name(path, images[2], offs[2], body, seed)
            name = replacement_name(path, images[2], offs[2], body, seed, text)
            print('PASS delete body=%d seed=%d %s' % (body, seed, ' '.join(delete(
                path, images[2], offs[2], body, seed, text, name))))
            print('PASS cut_fixture body=%d seed=%d empty_name=%s fixture_name=%s' % ((body, seed) + cut_refusals(
                path, images[2], offs[2], body, seed, text)))
            cut(path, archives[2], images[2], offs[2], body, seed, text)
    print('PASS arrival_stage_r7 bodies=%d seeds=2 uniform=%d' % (len(list(bodies)), len(UNIFORM)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (
            type(error).__name__, getattr(error, 'address', getattr(error, 'addr', 0)) or 0))
        raise
