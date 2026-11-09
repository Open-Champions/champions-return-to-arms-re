#!/usr/bin/env python3
"""Arrival round 8. Checks the round-7 claims that the round-7 audit found unasserted.

Original functions in tools/ee_emu.py. The fixtures are the round-7 ones, reused from
tools/difftest_arrival_stage_r7.py and disclosed there. This test adds read recording
on named words, sentinels and planted values, instruction-field checks on named
addresses, and negative controls. Output is addresses, lengths and counts.
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
import difftest_arrival_stage_r7 as R7
from difftest_arrival_stage_r5 import (
    CAMERA, CD_FIND, LEVEL, LUMP_COUNT, LUMPS, NET, PERMITTED, ROUTE0, ROUTE0_ORDER,
    ROUTE2_ORDER, Boundary, capture, data_off, fresh, hook_natives, plant_prop, queues,
)
from difftest_arrival_stage_r6 import (
    ANIM_PUSH, CUT_RUN, DEFERRED, ITEM_TEST, PRINTF, SLOT19, arm_cut, cut_name, overlaps,
    stop_at,
)
from difftest_arrival_stage_r7 import (
    ANIM_EVAL, ANIM_EVAL_END, ANIM_PUSH_END, CHOICE, COMPLETE, CUT_ACTIVE, CUT_CLOCK, DECI2,
    DECISION, DIFFICULTY, GUARD, GUARD_SIZE, HUB_NAME, KEEP, LOADER_REGS, LS_STOP, LS_THREAD,
    LUMP_FIXUP, LUMP_LOAD, MISSIONS, REFER, SHOP, TEX_NAME, TEXT_HUB_A, TEXT_HUB_B,
    TEXT_SHOP_HUB, THREAD_WORD, TIMER, WAKE, WARM, WARM_PASS, WARM_START, calls, level_lump,
    plant_camera, plant_guard, route0_entry, wake_handler,
)
from difftest_arrival_state_r4 import prepared
from difftest_loading import SHA256
from difftest_loading_arrival_r4 import RECORD, private_script, require_local
from ee_emu import EE, CpuTrap, MemoryFault, s64

# Loader: mainloop_runSession 0x322998-0x3235a7 (ghidra_funcs.tsv:4198).
RUN_SESSION, RUN_SESSION_END, FRAME = 0x322998, 0x3235A8, 0x60
# Register -> (setting instruction addresses, kind, immediate). Each value LOADER_REGS
# plants is checked against these fields (Observed, static).
REG_SETTERS = {
    16: ((0x322E0C,), 'addiu', (20, 0x41F0)),
    17: ((0x322CD4,), 'lui', 0x42),
    19: ((0x322CE0,), 'lui', 0x40),
    20: ((0x322DCC, 0x322E04), 'lui', 0x55),
    21: ((0x322E1C,), 'lui', 0x45),
    22: ((0x322D2C,), 'lui', 0x45),
    23: ((0x3229AC,), 'lui', 0x42),
    30: ((0x3229B4,), 'lui', 0x50),
}
S2 = 18
S2_SET = 0x322EC0
S2_USES = (0x322EC0, 0x322F38, 0x322F84, 0x322F90, 0x323354, 0x323388, 0x3233EC, 0x323580)
POISON = 0xA5A5A5A5
FORMATS_SITES = ((0x322E64, 0x554668), (0x322E78, 0x554670), (0x322FFC, 0x554580),
                 (0x3230FC, 0x5546A8))
GUARD_CHECK, GUARD_CHECK_END = 0x19D9F8, 0x19DA78
STACK_CHECKS = ((0x322E84, 0x5541F0, 0x7BA, 0x322E8C), (0x322FF0, 0x5541F0, 0x7F0, 0x322FF8))
NET_READS = (0x322E8C, 0x323004)
CAMERA_READ, CUT_BYTE_READ, PLAYERS_READ, PLAYER_PTR_READ = 0x322EBC, 0x322EDC, 0x322F38, 0x322F58
PLAYERS_WORD, PLAYER_PTR, PLAYER_STRIDE = 0x4D8AE0, 0x4DCEC8, 0x4C30
STRCMP = 0x3B8534
IDLE_TEST = 0x322F18
WAKE_END = 0x17FD44
# Guard check fields (Observed, static).
GUARD_LUI, GUARD_CMP, GUARD_LIMIT, GUARD_FAULT = 0x19D9FC, 0x19DA2C, 0x19DA50, 0x19DA4C
# setState 0x23d680-0x23d7ab (ghidra_funcs.tsv:2371).
SET_STATE_ZERO, SET_STATE_ADD = 0x23D6AC, 0x23D764
AFTER_EVAL = 0x23D744
# Delete / cut.
RES_FIND, DIR_SEARCH = 0x17365C, 0x171DE4

UNIFORM = {}


def same(key, value):
    if key in UNIFORM:
        assert UNIFORM[key] == value, (key, UNIFORM[key], value)
    else:
        UNIFORM[key] = value
    return value


def fields(e, at):
    w = e.mem.u32(at)
    imm = w & 0xFFFF
    return w >> 26, w >> 21 & 31, w >> 16 & 31, imm - 0x10000 if imm & 0x8000 else imm


def dest(w):
    """General register an instruction word writes (0 when none)."""
    op, rs, rt, rd = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31
    if op in (0x00, 0x1C):
        return rd
    if op == 0x03:
        return 31
    if op == 0x01:
        return 31 if rt in (0x10, 0x11, 0x12, 0x13) else 0
    if 0x08 <= op <= 0x0F or op in (0x18, 0x19, 0x1A, 0x1B, 0x1E, 0x37) or 0x20 <= op <= 0x27:
        return rt
    if op in (0x10, 0x11, 0x12) and rs in (0, 1, 2):
        return rt
    return 0


def uses(w, reg):
    """True when an instruction word names general register reg in any field."""
    op, rs, rt, rd = w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31
    if op in (0x02, 0x03):
        return False
    if op in (0x00, 0x1C):
        return reg in (rs, rt, rd)
    if op == 0x11:
        return rs in (0, 2, 4, 6) and rt == reg
    if op in (0x10, 0x12):
        return rs in (0, 1, 2, 4, 5, 6) and rt == reg
    if op in (0x31, 0x35, 0x36, 0x39, 0x3D, 0x3E):
        return rs == reg
    return reg in (rs, rt)


def watch_reads(e, ranges):
    """Record (pc, address, size, value) for guest loads that touch any range."""
    seen = []
    plain = EE._load

    def load(addr, size):
        value = plain(e, addr, size)
        for lo, hi in ranges:
            if addr < hi and lo < addr + size:
                seen.append((e.cur, addr, size, value))
                break
        return value
    e._load = load
    return seen


def marks(e, addresses, log):
    for address in addresses:
        previous = e.hooks.get(address)

        def mark(emu, address=address, previous=previous):
            log.append(address)
            if previous is not None:
                previous(emu)
        e.hook(address, mark)


def no_stub(e):
    assert not any(c.stubbed for c in e.calls) and not e.patches


# ---- R8-5: the registers the loader stage plants, against their instructions -------------
def loader_registers(e):
    for reg, (setters, kind, imm) in REG_SETTERS.items():
        for at in setters:
            op, rs, rt, value = fields(e, at)
            if kind == 'lui':
                assert (op, rt, value & 0xFFFF) == (0x0F, reg, imm), (hex(at), reg)
                assert LOADER_REGS[reg] == imm << 16
            else:
                base, low = imm
                assert (op, rs, rt, value) == (0x09, base, reg, low), (hex(at), reg)
                assert LOADER_REGS[reg] == (REG_SETTERS[base][2] << 16) + low
        writers = [at for at in range(RUN_SESSION, WARM_START, 4) if dest(e.mem.u32(at)) == reg]
        assert writers and writers[-1] == setters[-1], (reg, [hex(a) for a in writers])
    assert sorted(LOADER_REGS) == sorted(REG_SETTERS)
    # s2 is never written before 0x322e58; its first use after is the write at 0x322ec0.
    assert not [at for at in range(RUN_SESSION, WARM_START, 4) if dest(e.mem.u32(at)) == S2]
    named = tuple(at for at in range(WARM_START, RUN_SESSION_END, 4) if uses(e.mem.u32(at), S2))
    assert named == S2_USES, [hex(a) for a in named]
    assert dest(e.mem.u32(S2_SET)) == S2 and fields(e, S2_SET)[0] == 0x0F
    # The only stack-relative accesses after 0x322e58 are the epilogue's restores.
    frame = [at for at in range(WARM_START, RUN_SESSION_END, 4)
             if e.mem.u32(at) >> 26 not in (0x02, 0x03) and e.mem.u32(at) >> 21 & 31 == 29
             and e.mem.u32(at) >> 26 not in (0x00, 0x1C)]
    assert frame and min(frame) >= 0x323578, [hex(a) for a in frame]
    return len(REG_SETTERS), len(S2_USES), len(frame)


# ---- R8-4 / R8-5: the loader from 0x322e58, every claimed detail, all three runs ---------
def loader(path, image, body, seed, shop=None):
    o = route0_entry(path, image, body, seed)
    e = o.emu
    static = loader_registers(e)
    level = e.mem.cstr(TEXT_SHOP_HUB).encode() if shop else None
    e.hooks.clear()
    e.calls.clear()
    e.record_calls = True
    e.install_deci2_kputs()
    e.wakes = []
    e.syscall_handler = wake_handler
    plant_guard(e)
    e.mem.map(TIMER, 0x10)
    e.mem.w32(TIMER, 0x11111111)
    e.mem.w32(R7.LS_BYTE, 0)
    if level is not None:
        e.mem.write(LEVEL, level + b'\0')
        if shop == 'stop':
            e.hook(CD_FIND, stop_at(CD_FIND))
    for reg, value in LOADER_REGS.items():
        e.r[reg] = value
    e.r[S2] = POISON
    sp = o.SP
    reads = watch_reads(e, ((TIMER, TIMER + 0x10), (NET, NET + 1), (CAMERA, CAMERA + 4),
                            (CUT_ACTIVE, CUT_ACTIVE + 1), (PLAYERS_WORD, PLAYERS_WORD + 4),
                            (PLAYER_PTR, PLAYER_PTR + 8 * PLAYER_STRIDE), (sp, sp + FRAME)))
    log = []
    marks(e, S2_USES + tuple(r for _s, _a, _b, r in STACK_CHECKS), log)
    idle = []
    e.hook(IDLE_TEST, lambda m: idle.append(m.r[2] & 0xFFFFFFFF))
    e.record_writes = True
    e.writes.clear()
    e.r[31] = e.RETURN_ADDR
    e.r[29] = sp
    e.jump(WARM_START)
    stop = None
    try:
        e.run(max_steps=40000000)
        raise AssertionError('loader returned')
    except Boundary as hit:
        stop = ('callee', hit.address)
    except MemoryFault as fault:
        stop = ('fault', fault.pc, fault.addr)
    except CpuTrap:
        stop = ('syscall', e.cur, s64(e.r[3]), e.r[31] & 0xFFFFFFFF)
    del e._load
    want = {None: ('syscall', REFER, 48, 0x322500), 'stop': ('callee', CD_FIND),
            'miss': ('fault', 0x17363C, 0)}[shop]
    assert stop == want, stop
    # dbg_printf: the format a0 of each call from this function, in order, and one Deci2
    # call after each one.
    printed = 4 if shop is None else 3
    mine = [c for c in e.calls if c.target == PRINTF and RUN_SESSION <= c.site < RUN_SESSION_END]
    assert [(c.site, c.args[0] & 0xFFFFFFFF) for c in mine] == list(FORMATS_SITES[:printed])
    others = tuple(c.site for c in e.calls if c.target == PRINTF and not RUN_SESSION <= c.site < RUN_SESSION_END)
    assert len(others) == (1 if shop == 'miss' else 0), [hex(a) for a in others]
    pair = [c.target for c in e.calls if c.target in (PRINTF, DECI2)]
    assert pair == [PRINTF, DECI2] * (printed + len(others)), [hex(t) for t in pair]
    # The stack check is called twice, with these arguments, and returns both times.
    checks = [(c.site, c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
              for c in e.calls if c.target == GUARD_CHECK]
    assert checks == [(s, a, b) for s, a, b, _r in STACK_CHECKS], checks
    assert [a for a in log if a in {r for _s, _a, _b, r in STACK_CHECKS}] == [
        r for _s, _a, _b, r in STACK_CHECKS]
    # s2: the poisoned caller value is written at 0x322ec0 before any use.
    s2_log = [a for a in log if a in S2_USES]
    assert s2_log[0] == S2_SET and S2_USES[-1] not in s2_log
    # Precondition words and their reads.
    net = [(pc, v) for pc, a, _s, v in reads if a == NET]
    assert net == [(at, 0) for at in NET_READS], net
    camera = [(pc, v) for pc, a, _s, v in reads if a == CAMERA]
    assert camera == [(CAMERA_READ, 0)] * 10, camera
    cut_byte = [(pc, v) for pc, a, _s, v in reads if a == CUT_ACTIVE]
    assert cut_byte == [(CUT_BYTE_READ, 0)] * 10, cut_byte
    players = [(pc, v) for pc, a, _s, v in reads
               if a == PLAYERS_WORD and RUN_SESSION <= pc < RUN_SESSION_END]
    count = e.mem.u32(PLAYERS_WORD)
    assert count == 1 and [v for _pc, v in players] == [count] * len(players)
    assert [pc for pc, _v in players] == [PLAYERS_READ, 0x322F90] * 10, [hex(pc) for pc, _v in players]
    pointer = [(pc, a, v) for pc, a, _s, v in reads if RUN_SESSION <= pc < RUN_SESSION_END
               and a in {PLAYER_PTR + k * PLAYER_STRIDE for k in range(8)}]
    assert pointer == [(PLAYER_PTR_READ, PLAYER_PTR, 0)] * 10, pointer
    timer = [pc for pc, a, _s, _v in reads if TIMER <= a < TIMER + 0x10]
    assert len(timer) == 20 and all(WAKE <= pc < WAKE_END for pc in timer), [hex(p) for p in timer]
    frame = [r for r in reads if sp <= r[1] < sp + FRAME]
    assert not frame, frame
    # Pass order, counter and timer stores, promote and queue: the same in every run.
    assert calls(e, DEFERRED) == 1 and calls(e, ITEM_TEST) == 0 and queues(e) == (2, 0, 1)
    assert calls(e, 0x13DCD0) == 0
    order = [c.target for c in e.calls if c.target in set(WARM_PASS)]
    assert order == list(WARM_PASS) * 10, order
    assert idle == [0] * 10, idle  # 0x17fe88's v0 at the branch 0x322f18
    assert e.wakes == [e.mem.u32(THREAD_WORD)] * 10 == [0] * 10
    for absent in (CUT_RUN, R7.CAM_UPDATE, R7.EQUIP_BUSY):
        assert calls(e, absent) == 0, hex(absent)
    assert e.mem.u32(WARM) == 0
    warm = [(pc, v) for pc, _a, _s, v in overlaps(e.writes, WARM, 4)]
    assert warm[0][1] == 10 and 0x322934 <= warm[0][0] < 0x322954
    assert warm[1:] == [(0x322F30, v) for v in range(9, -1, -1)], warm
    timer_stores = [(pc, v) for pc, _a, _s, v in overlaps(e.writes, TIMER, 4)]
    assert timer_stores == [(0x322F04, 0)] * 10
    tests = [c.site for c in e.calls if c.target == STRCMP and 0x323064 <= c.site < 0x3230F8]
    if shop is None:
        assert tests == [0x323074, 0x32308C, 0x3230AC, 0x3230D8] and calls(e, SHOP) == 0
        assert e.r[4] & 0xFFFFFFFF == e.mem.u32(LS_THREAD) == 0xFFFFFFFF
    else:
        assert tests == [0x323074]
        shops = [(c.site, c.args[1] & 0xFF) for c in e.calls if c.target == SHOP]
        assert shops == [(0x3230C4, 1)] and calls(e, LS_STOP) == 0
        made = [c.target for c in e.calls if c.target in {SHOP, LUMP_LOAD, CD_FIND}]
        assert made == [SHOP, LUMP_LOAD, CD_FIND], made
    no_stub(e)
    return same('loader:%s' % shop, (static, printed, others, len(timer), len(players), len(log)))


# ---- R8-7: the stack guard's base, compare value, length and fault -------------------------
def guard(path, body, seed):
    o = prepared(path, body, seed)
    e = o.emu
    op, _rs, rt, imm = fields(e, GUARD_LUI)
    assert (op, rt, imm << 16) == (0x0F, 2, GUARD)
    op, rs, rt, imm = fields(e, GUARD_CMP)
    assert (op, rs, rt, imm) == (0x09, 0, 2, 0xA5)
    op, rs, rt, imm = fields(e, GUARD_LIMIT)
    assert (op, rs, rt, imm) == (0x0A, 16, 2, GUARD_SIZE)
    op, rs, rt, imm = fields(e, GUARD_FAULT)
    assert (op, rs, rt, imm) == (0x2B, 0, 0, 0)
    e.install_deci2_kputs()
    out = []
    for offset in (None, 0, GUARD_SIZE - 1, GUARD_SIZE):
        plant_guard(e)
        e.mem.w8(GUARD + GUARD_SIZE, 0xA5)
        if offset is not None:
            e.mem.w8(GUARD + offset, 0x5A)
        e.hooks.clear()
        e.calls.clear()
        try:
            o.call(GUARD_CHECK, 0x5541F0, 0x7BA, max_steps=200000)
            result = 'ret'
        except MemoryFault as fault:
            assert (fault.pc, fault.addr) == (GUARD_FAULT, 0)
            result = 'fault'
        printed = [c.site for c in e.calls if c.target == PRINTF]
        assert printed == ([0x19DA44] if result == 'fault' else [])
        out.append(result)
        no_stub(e)
    assert out == ['ret', 'fault', 'fault', 'ret'], out
    return same('guard', tuple(out))


# ---- R8-8: game_getHubName at every difficulty, and mission row 0 +0x0c -------------------
def hub_name(path, archives, body, seed):
    o = prepared(path, body, seed)
    e = o.emu
    out = []
    for level in range(1, 6):
        e.mem.w32(DIFFICULTY, level)
        sites = (RECORD + DECISION, RECORD + CHOICE, RECORD + COMPLETE + 13 * level + 1)
        masks = (1 << level, 1 << level, 2)
        saved = [e.mem.u8(at) for at in sites]
        got = []
        for combo in range(8):
            for bit, (at, mask) in enumerate(zip(sites, masks)):
                e.mem.w8(at, saved[bit] | mask if combo >> bit & 1 else saved[bit] & ~mask)
            e.hooks.clear()
            got.append(e.call(HUB_NAME) & 0xFFFFFFFF)
        for at, value in zip(sites, saved):
            e.mem.w8(at, value)
        assert got == [TEXT_HUB_A] * 7 + [TEXT_HUB_B], (level, [hex(v) for v in got])
        out.append(level)
    no_stub(e)
    evil = e.mem.u32(MISSIONS + 0x0C)
    if evil:
        stem = e.mem.cstr(evil)
        evil_route = tuple(i for i, p in enumerate(archives) if Path(p).stem.lower() == stem)
    else:
        evil_route = None
    return same('hub_name', (tuple(out), evil != 0, evil_route))


# ---- R8-1 / R8-2: +0x17c and the anim entry, with planted values -----------------------
def prop_case(path, image, off, body, seed, clip, flags, capacity, plant17c, fill=None,
              link=False, late=None, high=0):
    cap = fresh(path, image, body, seed)
    found = capture(cap, off, 0x142320, 0x53F020)
    o = fresh(path, image, body, seed)
    e = o.emu
    obj = plant_prop(o, found['text'], 100)
    block = e.alloc(32)
    e.mem.w64(block + 8, 0x5)
    e.mem.w32(obj + 0x90, block)
    clip_block = e.alloc(16)
    e.mem.w32(clip_block + 4, clip)
    e.mem.w32(obj + 0x128, clip_block)
    e.mem.w32(obj + 0x12C, flags)
    e.mem.w8(obj + 0x9D, capacity)
    e.mem.w16(obj + 0x9E, high)
    e.mem.w32(obj + 0x11C, 0)
    e.mem.w32(obj + 0x17C, plant17c)
    linked = 0
    if fill is not None:
        e.mem.write(obj + 0xA0, bytes([fill]) * 0x20)
        e.mem.w32(obj + 0xA4, 0)
        if link:
            linked = e.alloc(0x20, fill=fill)
            e.mem.w32(obj + 0xA4, linked)
    e.record_writes = True
    e.writes.clear()
    trace = []
    hook_natives(o, set(ROUTE0), set(), trace)
    if late is not None:
        e.hook(AFTER_EVAL, lambda m: m.mem.w32(obj + 0x17C, late))
    try:
        o.call(0x1ED694, 0x53F000, max_steps=2000000)
        o.call(0x1ED694, 0x53F020, max_steps=4000000)
        raise AssertionError('prop entry returned')
    except Boundary as hit:
        stop = ('native', hit.address)
    assert stop == ('native', 0x14598C) and tuple(a for a, _ in trace) == ROUTE0_ORDER
    slot = [c for c in e.calls if c.target == SLOT19]
    assert len(slot) == 1 and slot[0].args[1] & 0xFFFFFFFF == flags & 1
    no_stub(e)
    return e, obj, clip_block, linked


def props(path, image, off, body, seed):
    out = []
    # R8-1: setState zeroes +0x17c at 0x23d6ac, then stores (+0x17c) + clip[4] + 1.
    for clip in (5, 9, 0x40):
        for plant in (0x22222222, 0x13579BDF):
            e, obj, _c, _l = prop_case(path, image, off, body, seed, clip, 0, 0, plant)
            touching = [(pc, s, v) for pc, _a, s, v in overlaps(e.writes, obj + 0x17C, 4)]
            assert touching == [(SET_STATE_ZERO, 4, 0), (SET_STATE_ADD, 4, clip + 1)], touching
            assert e.mem.u32(obj + 0x17C) == clip + 1
    # Control: a value planted after 0x170bc8 returns is the base of the sum.
    for late in (0x100, 0x7000):
        e, obj, _c, _l = prop_case(path, image, off, body, seed, 9, 0, 0, 0x22222222, late=late)
        assert e.mem.u32(obj + 0x17C) == late + 9 + 1
        assert overlaps(e.writes, obj + 0x17C, 4)[-1][0] == SET_STATE_ADD
    out.append('17c=clip4+1 clips=3 plants=2 late=2')
    # R8-2: entry +0x00..+0x1f over a 0x5a sentinel (+4 zero, or a linked block).
    credit = None
    for flags, mode in ((0, 6), (2, 3)):
        for link in (False, True):
            e, obj, clip, linked = prop_case(path, image, off, body, seed, 5, flags, 4, 0x22222222,
                                             fill=0x5A, link=link, high=0x100)
            entry = obj + 0xA0
            assert e.mem.u8(obj + 0x9C) == 1 and e.mem.u16(obj + 0x9E) == 0x100 | mode
            assert [(pc, v) for pc, _a, _s, v in overlaps(e.writes, obj + 0x9E, 2)] == [
                (0x17087C, 0x100 | mode)]
            want = {0: (4, clip), 4: (4, 0), 8: (4, 0x3F800000), 0xC: (4, 0), 0x10: (4, 0x3F800000),
                    0x14: (4, 0), 0x18: (4, 0x40A00000), 0x1C: (2, mode), 0x1E: (2, 0)}
            stores = {}
            for k, (size, value) in want.items():
                assert e.mem.read(entry + k, size) == value.to_bytes(size, 'little'), hex(k)
                stores[k] = tuple(pc for pc, _a, _s, _v in overlaps(e.writes, entry + k, size))
            if link:
                assert stores[4] == (0x170890,)
                assert [(pc, v) for pc, _a, _s, v in overlaps(e.writes, linked + 0x14, 4)] == [
                    (0x17088C, 0)]
            else:
                assert stores[4] == ()
            row = {k: v for k, v in stores.items() if k != 4}
            assert credit is None or row == credit, row
            credit = row
    assert credit == {0: (0x170878,), 8: (0x1708A8,), 0xC: (0x1708A4,), 0x10: (0x1708AC,),
                      0x14: (0x1708B0,), 0x1C: (0x1708A0,), 0x1E: (0x170888,),
                      0x18: credit[0x18]}, credit
    assert credit[0x18][0] == 0x170880 and len(credit[0x18]) == 2
    assert ANIM_EVAL <= credit[0x18][1] < ANIM_EVAL_END
    assert all(ANIM_PUSH <= pc < ANIM_PUSH_END for k, pcs in credit.items() for pc in pcs
               if (k, pc) != (0x18, credit[0x18][1]))
    out.append('entry=9fields push=8 eval=1 link=0x17088c,0x170890 9e|=mode')
    return same('props', tuple(out) + (credit[0x18][1],))


# ---- R8-6: the previous free-list head ----------------------------------------------------
def free_head(path, image, off, body, seed, text, name):
    from difftest_arrival_stage_r6 import init_world, plant_actor
    o = fresh(path, image, body, seed)
    arm_cut(o, image, off, text)
    init_world(o)
    e = o.emu
    obj = plant_actor(o, name, True)
    before = e.mem.read(R7.FREE_TABLE, 0x100)
    e.record_writes = True
    e.writes.clear()
    hook_natives(o, set(PERMITTED) | {0x143F1C, 0x144B44}, set(), [])
    o.call(0x1ED694, 0x53F000, max_steps=4000000)
    o.call(0x1ED694, 0x53F020, max_steps=4000000)
    o.call(0x1EDAC0, max_steps=4000000)
    o.call(0x1EDAC0, max_steps=4000000)
    freed = [w for w in e.writes if R7.POOL_FREE <= w[0] < 0x1504C8]
    (pc_a, head, _sa, value_a), (pc_b, at_b, _sb, value_b) = freed
    assert (pc_a, value_a, pc_b, at_b) == (0x1504BC, obj, 0x1504C4, obj)
    previous = struct.unpack_from('<I', before, head - R7.FREE_TABLE)[0]
    assert value_b == previous and e.mem.u32(obj) == previous and e.mem.u32(head) == obj
    no_stub(e)
    return same('free_head', ((head - R7.FREE_TABLE) // 16, previous == 0))


# ---- R8-3: the resident lump's order and the binary search ---------------------------------
def build_lump(e, archive, order=None):
    """R7.resident_lump with an optional record order. order None is byte-identical."""
    name, lump, entries = level_lump(archive)
    kept = [(n, o, s) for n, o, s in entries if n.lower().endswith(KEEP)]
    if order is not None:
        kept = [kept[i] for i in order(len(kept))]
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


def records(e, base):
    return [tuple(e.mem.u32(base + 4 + 12 * i + k) for k in (0, 4, 8)) for i in range(e.mem.u16(base))]


def inversions(e, pointers):
    return sum(1 for a, b in zip(pointers, pointers[1:]) if s64(e.call(STRCMP, a, b)) >= 0)


def found_by_search(e, base):
    hits = 0
    for index, (pointer, _d, _s) in enumerate(records(e, base)):
        key = e.alloc(64)
        e.mem.write(key, e.mem.cstr(pointer).encode('latin1') + b'\0')
        e.calls.clear()
        if e.call(DIR_SEARCH, base, key) & 0xFFFFFFFF == base + 4 + 12 * index:
            hits += 1
        assert calls(e, STRCMP) >= 1
    return hits


def run_cut_prefix(o, e, lump_name, base, size):
    e.mem.write(LEVEL, Path(lump_name).stem.encode() + b'\0')
    e.mem.write(TEX_NAME, Path(lump_name).stem.encode() + b'\0')
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
    try:
        o.call(0x1EDAC0, max_steps=4000000)
    except MemoryFault as fault:
        return trace, ('fault', 'post', fault.pc, fault.addr)
    except Boundary as hit:
        return trace, ('stop', 'post', hit.address, 0)
    if e.mem.u8(CUT_ACTIVE) != 1:
        return trace, ('inactive', 'post', e.mem.u32(0x44FCE4), 0)
    every = set()
    for index in range(191):
        if not e.mem.u32(R7.TABLE + 8 * index):
            break
        every.add(e.mem.u32(R7.TABLE + 8 * index + 4))
    hook_natives(o, every, set(), [])
    e.install_deci2_kputs()
    try:
        o.call(CUT_RUN, 1, max_steps=6000000)
    except MemoryFault as fault:
        return trace, ('fault', 'frame', fault.pc, fault.addr)
    except Boundary as hit:
        return trace, ('stop', 'frame', hit.address, 0)
    return trace, ('ran', e.mem.u32(R7.CUT_ACTORS))


def lump_order(path, archive, image, off, body, seed, text):
    o = fresh(path, image, body, seed)
    e = o.emu
    lump_name, base, size, kept, total = build_lump(e, archive)
    _n, twin, twin_size, _k, _t = R7.resident_lump(e, archive)
    assert twin_size == size and e.mem.read(twin, size) == e.mem.read(base, size)
    raw = [base + p for p, _d, _s in records(e, base)]
    raw_inversions = inversions(e, raw)
    e.hooks.clear()
    e.calls.clear()
    o.call(LUMP_FIXUP, base, max_steps=4000000)
    no_stub(e)
    after = records(e, base)
    kept_at = {p for p, _d, _s in after}
    removed = tuple(i for i, p in enumerate(raw) if p not in kept_at)
    assert len(after) == kept - len(removed) == 16
    fixed_inversions = inversions(e, [p for p, _d, _s in after])
    hits = found_by_search(e, base)
    assert fixed_inversions == 0 and hits == len(after)
    trace, stop = run_cut_prefix(o, e, lump_name, base, size)
    assert tuple(a for a, _ in trace) == ROUTE2_ORDER and stop == ('ran', 12), stop
    result = [('archive', removed, raw_inversions, fixed_inversions, hits, stop)]
    # Negative controls: the same records reversed, and sorted by the unstripped name.
    _n, _l, entries = level_lump(archive)
    raw_names = [n.lower() for n, _o, _s in entries if n.lower().endswith(KEEP)]
    by_raw = sorted(range(len(raw_names)), key=lambda i: raw_names[i])
    for label, order in (('reversed', lambda n: list(range(n))[::-1]),
                         ('raw_sorted', lambda n: by_raw)):
        c = fresh(path, image, body, seed)
        ce = c.emu
        lump_name, cbase, csize, _k, _t = build_lump(ce, archive, order)
        ce.hooks.clear()
        ce.calls.clear()
        c.call(LUMP_FIXUP, cbase, max_steps=4000000)
        no_stub(ce)
        crecs = records(ce, cbase)
        cinv = inversions(ce, [p for p, _d, _s in crecs])
        chits = found_by_search(ce, cbase)
        _trace, cstop = run_cut_prefix(c, ce, lump_name, cbase, csize)
        # Negative control: the permuted copy is not in search order, some names are not
        # found, and the cut path faults instead of running setup.
        assert len(crecs) == 16 and cinv > 0 and chits < len(crecs), (cinv, chits)
        # reversed: the post action faults in cut_start; raw_sorted: the first cut frame
        # faults where the dialog.bin refusal does.
        assert cstop == {'reversed': ('fault', 'post', 0x19B504, 0),
                         'raw_sorted': ('fault', 'frame', 0x2168A0, 0)}[label], cstop
        result.append((label, int(list(order(len(by_raw))) == list(range(len(by_raw)))),
                       len(crecs), cinv, chits, cstop))
    return same('lump_order', tuple(result))


# ---- R8-12: res_find on the dialog.bin path ------------------------------------------------
def dialog_refusal(path, image, off, body, seed, text):
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
    e.mem.write(TEX_NAME, e.mem.read(LEVEL, 16))
    level = e.mem.cstr(LEVEL)
    looked = []

    def enter(m):
        ra = m.r[31] & 0xFFFFFFFF
        entry = (m.mem.cstr(m.r[4] & 0xFFFFFFFF), m.mem.cstr(m.r[5] & 0xFFFFFFFF), ra)
        previous = m.hooks.get(ra)

        def back(n):
            looked.append(entry + (n.r[2] & 0xFFFFFFFF,))
            if previous is None:
                n.unhook(ra)
            else:
                n.hooks[ra] = previous
        m.hooks[ra] = back
    e.hook(RES_FIND, enter)
    try:
        o.call(CUT_RUN, 1, max_steps=6000000)
        raise AssertionError('fixture frame returned')
    except MemoryFault as fault:
        assert (fault.pc, fault.addr) == (0x2168A0, 0)
    dialog = [x for x in looked if x[1] == 'dialog.bin']
    # a0 is the level lump name "<level>.lmp", a1 the entry; v0 is 0.
    assert len(dialog) == 1 and dialog[0][0] == level + '.lmp' and dialog[0][3] == 0, len(dialog)
    assert looked[-1] == dialog[0]
    no_stub(e)
    return same('dialog', (len(looked), dialog[0][2]))


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
            static, printed, _o, timer, players, marked = loader(path, images[0], body, seed)
            loader(path, images[0], body, seed, shop='stop')
            miss_printf = loader(path, images[0], body, seed, shop='miss')[2][0]
            print('PASS loader body=%d seed=%d regs=%d s2_uses=%d frame_insns=%d printf=4,3,3 '
                  'deci2_pairs=ok stack_checks=2 net_reads=2 camera=10 cut_byte=10 player_ptr=10 '
                  'timer_reads=%d frame_reads=0 shop_runs=same_loop miss_printf=0x%x' % (
                      (body, seed) + static + (timer, miss_printf)))
            print('PASS guard body=%d seed=%d %s' % ((body, seed, ','.join(guard(path, body, seed)))))
            levels, evil, evil_route = hub_name(path, archives, body, seed)
            print('PASS hub_name body=%d seed=%d difficulties=%s evil_alt=%s' % (
                body, seed, ','.join(map(str, levels)),
                'null' if not evil else 'route%s' % ','.join(map(str, evil_route))))
            print('PASS props body=%d seed=%d %s' % ((body, seed, ' '.join(
                str(x) if not isinstance(x, int) else '0x%x' % x for x in props(
                    path, images[0], offs[0], body, seed)))))
            text = cut_name(path, images[2], offs[2], body, seed)
            name = R7.replacement_name(path, images[2], offs[2], body, seed, text)
            bucket, empty = free_head(path, images[2], offs[2], body, seed, text, name)
            print('PASS free_head body=%d seed=%d bucket=%d previous_head=%s' % (
                body, seed, bucket, '0' if empty else 'nonzero'))
            order = lump_order(path, archives[2], images[2], offs[2], body, seed, text)
            (_a, removed, raw_inv, fixed_inv, hits, stop), *controls = order
            print('PASS lump_order body=%d seed=%d archive:removed=%s raw_inversions=%d fixed_inversions=%d '
                  'found=%d/16 cut=setup,actors=%d %s' % (
                      body, seed, ','.join(map(str, removed)), raw_inv, fixed_inv, hits, stop[1],
                      ' '.join('%s:same_as_archive=%d,records=%d,inversions=%d,found=%d/16,stop=%s@0x%x/%d' % (
                          (label, flag, n, inv, found) + tuple(st[1:]))
                          for label, flag, n, inv, found, st in controls)))
            looked, site = dialog_refusal(path, images[2], offs[2], body, seed, text)
            print('PASS dialog body=%d seed=%d res_find_calls=%d site=0x%x v0=0 fault=0x2168a0/0' % (
                body, seed, looked, site))
    print('PASS arrival_stage_r8 bodies=%d seeds=2 uniform=%d' % (len(list(bodies)), len(UNIFORM)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (
            type(error).__name__, getattr(error, 'address', getattr(error, 'addr', 0)) or 0))
        raise
