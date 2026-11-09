#!/usr/bin/env python3
"""Arrival round 9. Checks the round-8 claims that the round-8 audit found unasserted.

Original functions in tools/ee_emu.py. The fixtures are the round-7 and round-8 ones,
reused from tools/difftest_arrival_stage_r8.py and disclosed there. This test adds
planted values that tell the candidate operations apart, setState runs at nonzero
state indexes, and instruction-field checks on named addresses. Output is addresses,
lengths and counts.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest  # noqa: F401  (preload before tools/dis.py can shadow stdlib dis)
import difftest_arrival_stage_r8 as R8
from difftest_arrival_stage_r5 import data_off
from difftest_arrival_stage_r6 import ANIM_PUSH, cut_name, overlaps
from difftest_arrival_stage_r7 import ANIM_EVAL, ANIM_PUSH_END
from difftest_loading import SHA256
from difftest_loading_arrival_r4 import private_script, require_local
from difftest_arrival_state_r4 import prepared
from difftest_arrival_stage_r8 import (
    AFTER_EVAL, FRAME, IDLE_TEST, RES_FIND, RUN_SESSION, RUN_SESSION_END, SET_STATE_ADD,
    SET_STATE_ZERO, WARM_START, dest, fields, no_stub, prop_case, same,
)

SET_STATE = 0x23D680
SPECIAL_OR, SPECIAL_ADDU, SPECIAL_JR = 0x25, 0x21, 0x08


def special(e, at):
    """(op, rs, rt, rd, funct) of an R-type instruction."""
    w = e.mem.u32(at)
    return w >> 26, w >> 21 & 31, w >> 16 & 31, w >> 11 & 31, w & 0x3F


def jal_target(e, at):
    w = e.mem.u32(at)
    assert w >> 26 == 0x03, hex(at)
    return (at + 4) & 0xF0000000 | (w & 0x3FFFFFF) << 2


def branch_target(e, at):
    """Target of a conditional branch at at, or None when at is not one."""
    w = e.mem.u32(at)
    op, rt = w >> 26, w >> 16 & 31
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17) or (
            op == 0x01 and rt in (0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13)):
        return at + 4 + (fields(e, at)[3] << 2)
    return None


# ---- R9-1 static: the +0x9e store in anim_push ----------------------------------------
# 0x17086c loads the halfword at a0 + 6 (obj + 0x9e) into v0, 0x170874 makes v0 | a2
# (the mode), and 0x17087c stores v0 back at a0 + 6. a0 is copied to a3 on entry.
NINE_E_LOAD, NINE_E_OR, NINE_E_STORE = 0x17086C, 0x170874, 0x17087C


def nine_e_static(e):
    assert fields(e, NINE_E_LOAD) == (0x25, 7, 2, 6)  # lhu v0, 6(a3)
    assert special(e, NINE_E_OR) == (0, 2, 6, 2, SPECIAL_OR)  # or v0, v0, a2
    assert fields(e, NINE_E_STORE) == (0x29, 7, 2, 6)  # sh v0, 6(a3)
    # Nothing between the load and the store writes v0 except the or.
    assert [at for at in range(NINE_E_LOAD + 4, NINE_E_STORE, 4)
            if dest(e.mem.u32(at)) == 2] == [NINE_E_OR]
    # a3 holds a0 from the entry to the store: the only writer of a3 before it is a0 + 0.
    writers = [at for at in range(ANIM_PUSH, NINE_E_STORE, 4) if dest(e.mem.u32(at)) == 7]
    assert len(writers) == 1 and special(e, writers[0])[1:4] in ((4, 0, 7), (0, 4, 7)), [
        hex(a) for a in writers]
    # a2, the mode argument, is not written in anim_push before the or.
    assert not [at for at in range(ANIM_PUSH, NINE_E_OR, 4) if dest(e.mem.u32(at)) == 6]
    assert ANIM_PUSH <= NINE_E_STORE < ANIM_PUSH_END
    return 'lhu,or,sh'


# ---- R9-4 static: the four facts the round-8 note gives without an assert --------------
SKIP_BRANCH, SKIP_TARGET, SKIPPED = 0x322DC8, 0x322E08, 0x322E04
SKIPS = (0x322B40, 0x322CDC, 0x322DC8, 0x322DEC)
PROLOGUE_SP, EPILOGUE_JR, EPILOGUE_SP = 0x32299C, 0x3235A0, 0x3235A4
IDLE_CALL, IDLE_FUNC, IDLE_TARGET = 0x322F10, 0x17FE88, 0x322F34
PUSH_CALL, EVAL_CALL = 0x23D734, 0x23D73C


def loader_static(e):
    # 0x322dc8 is bne v0, zero (bnez v0, not the likely form) to 0x322e08, past the second
    # s4 setter 0x322e04. Its delay slot is the first s4 setter 0x322dcc, which therefore
    # runs whether or not the branch is taken.
    op, rs, rt, _imm = fields(e, SKIP_BRANCH)
    assert (op, rs, rt) == (0x05, 2, 0) and branch_target(e, SKIP_BRANCH) == SKIP_TARGET
    assert SKIP_TARGET > SKIPPED and SKIP_BRANCH + 4 == R8.REG_SETTERS[20][0][0]
    targets = {}
    for at in range(RUN_SESSION, RUN_SESSION_END, 4):
        target = branch_target(e, at)
        if target is None and e.mem.u32(at) >> 26 == 0x02:
            target = (at + 4) & 0xF0000000 | (e.mem.u32(at) & 0x3FFFFFF) << 2
        if target is not None:
            targets[at] = target
    # The branches before 0x322e04 that land past it (the round-8 note named one; there are four).
    skips = tuple(at for at, t in targets.items() if at < SKIPPED and t > SKIPPED)
    assert skips == SKIPS, [hex(a) for a in skips]
    # Every branch or j that lands in (0x322dcc, 0x322e58] is itself in [0x322dc8, 0x322e58),
    # and the only register jump is the epilogue's jr ra. So every path that reaches
    # 0x322e58 runs 0x322dcc, and only 0x322e04 writes s4 after it.
    inside = sorted(at for at, t in targets.items() if SKIP_BRANCH + 4 < t <= WARM_START)
    assert inside and all(SKIP_BRANCH <= at < WARM_START for at in inside), [hex(a) for a in inside]
    jumps = [at for at in range(RUN_SESSION, RUN_SESSION_END, 4)
             if special(e, at)[0] == 0 and special(e, at)[4] in (0x08, 0x09)]
    assert [at for at in jumps if special(e, at)[4] == 0x08] == [EPILOGUE_JR], [hex(a) for a in jumps]
    assert [at for at in range(SKIP_BRANCH + 8, WARM_START, 4)
            if dest(e.mem.u32(at)) == 20] == [SKIPPED]
    # The 0x60-byte frame: addiu sp, sp, -0x60 at entry + 4, addiu sp, sp, 0x60 in the
    # delay slot of the final jr ra.
    assert fields(e, PROLOGUE_SP) == (0x09, 29, 29, -FRAME)
    assert special(e, EPILOGUE_JR) == (0, 31, 0, 0, SPECIAL_JR)
    assert fields(e, EPILOGUE_SP) == (0x09, 29, 29, FRAME) and EPILOGUE_SP + 4 == RUN_SESSION_END
    assert [at for at in range(RUN_SESSION, RUN_SESSION_END, 4)
            if dest(e.mem.u32(at)) == 29] == [PROLOGUE_SP, EPILOGUE_SP]
    # 0x322f18 is bne v0, zero to 0x322f34. The call before it is jal 0x17fe88 at
    # 0x322f10, and its delay slot does not write v0, so the branch tests the return value.
    op, rs, rt, _imm = fields(e, IDLE_TEST)
    assert (op, rs, rt) == (0x05, 2, 0) and branch_target(e, IDLE_TEST) == IDLE_TARGET
    assert jal_target(e, IDLE_CALL) == IDLE_FUNC and dest(e.mem.u32(IDLE_CALL + 4)) != 2
    assert IDLE_CALL + 8 == IDLE_TEST
    # setState: jal anim_push at 0x23d734, jal 0x170bc8 at 0x23d73c, so 0x23d744 is the
    # return address of the 0x170bc8 call. The zero store 0x23d6ac comes before the push.
    assert jal_target(e, PUSH_CALL) == ANIM_PUSH and jal_target(e, EVAL_CALL) == ANIM_EVAL
    assert EVAL_CALL + 8 == AFTER_EVAL and SET_STATE_ZERO < PUSH_CALL < AFTER_EVAL < SET_STATE_ADD
    return 'skips=%d inside=%d frame=0x60 idle=v0 after_eval=ra' % (len(skips), len(inside))


# ---- R9-5 static: the +1 and the sum before the store at 0x23d764 ---------------------
# 0x23d744 v0 = obj+0x178 (state); 0x23d748 v1 = obj+0x17c; 0x23d74c v0 <<= 3;
# 0x23d750 v0 += s2 (obj + 8); 0x23d754 v0 = [v0 + 0x120] (clip); 0x23d758 v0 = clip[4];
# 0x23d75c v1 += v0; 0x23d760 v1 += 1; 0x23d764 obj+0x17c = v1.
SUM = ((0x23D744, 'i', (0x23, 17, 2, 0x178)), (0x23D748, 'i', (0x23, 17, 3, 0x17C)),
       (0x23D74C, 'r', (0, 0, 2, 2, 0x00)), (0x23D750, 'r', (0, 2, 18, 2, SPECIAL_ADDU)),
       (0x23D754, 'i', (0x23, 2, 2, 0x120)), (0x23D758, 'i', (0x23, 2, 2, 4)),
       (0x23D75C, 'r', (0, 3, 2, 3, SPECIAL_ADDU)), (0x23D760, 'i', (0x09, 3, 3, 1)),
       (SET_STATE_ADD, 'i', (0x2B, 17, 3, 0x17C)))


def sum_static(e):
    for at, kind, want in SUM:
        got = fields(e, at) if kind == 'i' else special(e, at)
        assert got == want, (hex(at), got)
    assert e.mem.u32(0x23D74C) >> 6 & 31 == 3  # sll v0, v0, 3
    # s2 is obj + 8 (addiu s2, s1, 8 at 0x23d6ec) and s1 is a0 (0x23d688).
    assert fields(e, 0x23D6EC) == (0x09, 17, 18, 8)
    assert special(e, 0x23D688)[1:4] in ((4, 0, 17), (0, 4, 17))
    assert special(e, 0x23D688)[4] in (SPECIAL_ADDU, SPECIAL_OR, 0x2D)
    return 'imm=1'


# ---- R9-1: +0x9e with low bits that overlap the mode -----------------------------------
NINE_E = ((6, 0x105), (6, 0x1FF), (6, 0x106), (6, 0x000), (3, 0x104), (3, 0x103), (3, 0x1FF))


def nine_e(path, image, off, body, seed):
    got = []
    for mode, high in NINE_E:
        flags = 2 if mode == 3 else 0
        e, obj, _c, _l = prop_case(path, image, off, body, seed, 5, flags, 4, 0x22222222,
                                   fill=0x5A, high=high)
        stores = [(pc, v) for pc, _a, _s, v in overlaps(e.writes, obj + 0x9E, 2)]
        assert stores == [(NINE_E_STORE, high | mode)], (mode, hex(high), stores)
        assert e.mem.u16(obj + 0x9E) == high | mode and e.mem.u8(obj + 0x9C) == 1
        assert e.mem.u16(obj + 0xA0 + 0x1C) == mode
        got.append(high | mode)
    # The candidates the round-8 audit named each give another value on some input:
    # add, replace the low byte, replace the low 3 bits. OR gives every stored value.
    pairs = list(zip(NINE_E, got))
    assert all(v == h | m for (m, h), v in pairs)
    for other in (lambda m, h: (h + m) & 0xFFFF, lambda m, h: h & ~0xFF | m,
                  lambda m, h: h & ~7 | m):
        assert any(v != other(m, h) for (m, h), v in pairs)
    return same('nine_e', tuple(got))


# ---- R9-5: setState at nonzero states, called directly on the round-8 prop -------------
def set_state_direct(e, o, obj, state, clip, flags, capacity, plant, late=None):
    # Decoy clips at the other state slots 0-7: a read of the wrong slot changes the sum.
    for other in range(8):
        decoy = e.alloc(16)
        e.mem.w32(decoy + 4, 0x3000 + other)
        e.mem.w32(obj + 0x128 + 8 * other, decoy)
    clip_block = e.alloc(16)
    e.mem.w32(clip_block + 4, clip)
    e.mem.w32(obj + 0x128 + 8 * state, clip_block)
    e.mem.w32(obj + 0x12C + 8 * state, flags)
    e.mem.w8(obj + 0x9D, capacity)
    e.mem.w32(obj + 0x17C, plant)
    e.hooks.clear()
    e.calls.clear()
    e.record_calls = True
    order = []
    e.hook(ANIM_PUSH, lambda m: order.append(('push', len(m.writes))))

    def after(m):
        order.append(('after_eval', len(m.writes)))
        if late is not None:
            m.mem.w32(obj + 0x17C, late)
    e.hook(AFTER_EVAL, after)
    e.record_writes = True
    e.writes.clear()
    o.call(SET_STATE, obj, state, max_steps=2000000)
    index = {pc: i for i, (pc, a, _s, _v) in enumerate(e.writes)
             if a == obj + 0x17C and pc in (SET_STATE_ZERO, SET_STATE_ADD)}
    touching = [(pc, s, v) for pc, _a, s, v in overlaps(e.writes, obj + 0x17C, 4)]
    assert [k for k, _n in order] == ['push', 'after_eval'], order
    # The zero store is before the push call, and the sum's store after 0x170bc8 returns.
    assert index[SET_STATE_ZERO] < order[0][1] <= order[1][1] <= index[SET_STATE_ADD]
    assert e.mem.u32(obj + 0x178) == state
    push = [c for c in e.calls if c.target == ANIM_PUSH]
    mode = 3 if flags & 2 else 6
    assert len(push) == 1 and push[0].site == PUSH_CALL
    assert [x & 0xFFFFFFFF for x in push[0].args[:3]] == [obj + 0x98, clip_block, mode]
    no_stub(e)
    return touching


def states(path, image, off, body, seed):
    e, obj, _c, _l = prop_case(path, image, off, body, seed, 5, 0, 4, 0x22222222, high=0x100)
    o = R8_FRESH[0]
    assert e.mem.u16(obj + 0x9E) == 0x106 and e.mem.u32(obj + 0x17C) == 6
    out = []
    for state in (0, 1, 2, 5):
        for clip in (9, 0x40):
            touching = set_state_direct(e, o, obj, state, clip, 0, 0, 0x13579BDF)
            assert touching == [(SET_STATE_ZERO, 4, 0), (SET_STATE_ADD, 4, clip + 1)], (
                state, touching)
            assert e.mem.u32(obj + 0x17C) == clip + 1
        out.append(state)
    # Control: the late value is the base at a nonzero state too.
    for state, late in ((2, 0x100), (5, 0x7000)):
        set_state_direct(e, o, obj, state, 9, 0, 0, 0x22222222, late=late)
        assert e.mem.u32(obj + 0x17C) == late + 9 + 1
    # A second push: setState zeroes the depth byte +0x9c (0x23d6f8) and pushes at depth 0
    # again. +0x9e keeps the earlier mode bits and gains the new mode.
    before = e.mem.u16(obj + 0x9E)
    set_state_direct(e, o, obj, 1, 5, 2, 4, 0x22222222)
    assert e.mem.u8(obj + 0x9C) == 1 and e.mem.u16(obj + 0x9E) == before | 3 == 0x107
    assert e.mem.u16(obj + 0xA0 + 0x1C) == 3
    assert [(pc, v) for pc, _a, _s, v in overlaps(e.writes, obj + 0x9E, 2)] == [
        (NINE_E_STORE, 0x107)]
    assert fields(e, 0x23D6F8) == (0x28, 17, 0, 0x9C)  # sb zero, 0x9c(s1)
    return same('states', (tuple(out), before, e.mem.u16(obj + 0x9E)))


R8_FRESH = []


def keep_fresh():
    """Record the Original object prop_case builds last, so setState can be called on it."""
    plain = R8.fresh

    def fresh(*args):
        o = plain(*args)
        R8_FRESH[:] = [o]
        return o
    R8.fresh = fresh


# ---- R9-3: res_find's call site on the dialog.bin path ---------------------------------
RES_FIND_CALL, RES_FIND_RETURN = 0x216894, 0x21689C


def dialog_site(e, path, image, off, body, seed, text):
    assert jal_target(e, RES_FIND_CALL) == RES_FIND and RES_FIND_CALL + 8 == RES_FIND_RETURN
    looked, ra = R8.dialog_refusal(path, image, off, body, seed, text)
    assert ra == RES_FIND_RETURN
    return same('dialog_site', (looked, ra - 8, ra))


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
    keep_fresh()
    bodies = range(12) if len(sys.argv) < 4 else [int(part) for part in sys.argv[3].split(',')]
    for body in bodies:
        for seed in (7, 20973):
            e = prepared(path, body, seed).emu
            static = (nine_e_static(e), loader_static(e), sum_static(e))
            same('static', static)
            print('PASS static body=%d seed=%d 9e=%s %s sum=%s' % ((body, seed) + static))
            got = nine_e(path, images[0], offs[0], body, seed)
            print('PASS nine_e body=%d seed=%d %s' % (body, seed, ' '.join(
                'mode%d:0x%x->0x%x' % (m, h, v) for (m, h), v in zip(NINE_E, got))))
            done, before, after = states(path, images[0], offs[0], body, seed)
            print('PASS states body=%d seed=%d states=%s clips=9,0x40 17c=clip4+1 late=2 '
                  'second_push:9e=0x%x->0x%x' % (body, seed, ','.join(map(str, done)), before, after))
            text = cut_name(path, images[2], offs[2], body, seed)
            looked, call, ret = dialog_site(e, path, images[2], offs[2], body, seed, text)
            print('PASS dialog_site body=%d seed=%d res_find_calls=%d call=0x%x return=0x%x' % (
                body, seed, looked, call, ret))
    print('PASS arrival_stage_r9 bodies=%d seeds=2 uniform=%d' % (len(list(bodies)), len(R8.UNIFORM)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (
            type(error).__name__, getattr(error, 'address', getattr(error, 'addr', 0)) or 0))
        raise
