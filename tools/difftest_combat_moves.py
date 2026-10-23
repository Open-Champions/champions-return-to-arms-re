#!/usr/bin/env python3
"""Focused original Player_meleeHit probes on constructed state.

Run with PYTHONDONTWRITEBYTECODE=1. The hit resolver and damage calculation are
replaced by recording stubs so this checks the move's handoff, not a real fight.
"""
import argparse
import hashlib

from ee_emu import EE


EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
RECORD = 0x4D8AF0
MELEE = 0x1B6A98
RECALC = 0x1B7158
RANK_SCALE = 0x1BF438
DAMAGE = 0x1E8230
RAY = 0x18A5C0
TAKE_DAMAGE = 0x1B5330
SEED = 0x404464


def probe(executable, seed, weapon_class, step, heavy, scale, copy=False):
    emu = EE(executable)
    mem = emu.mem
    player = emu.alloc(0x600)
    target = emu.alloc(0x600)
    mem.w32(player + 0x3C8, 0)
    mem.w32(player + 0xC, 0x20040 if copy else 0x40)
    mem.w32(target + 0xC, 0x20)
    mem.w8(RECORD + 0x4A86, weapon_class)
    mem.w8(player + 0x460, step)
    mem.w32(player + 0x44C, 2 if heavy else 0)
    mem.w32(player + 0x448, 0)
    mem.w32(0x44FDCC, 100)
    mem.w32(SEED, seed)
    emu.follow = {MELEE, RANK_SCALE}

    def recalc(_emu):
        mem.w32(RECORD + 0xCC, 100)
        mem.w32(RECORD + 0xD0, 10)
        mem.w32(RECORD + 0xD4, 20)

    emu.stub(RECALC, function=recalc)
    emu.stub(DAMAGE, ret=0)
    emu.stub(RAY, function=lambda e: e.f.__setitem__(0, 0xBF800000))
    emu.call(MELEE, player, target, 0, 0, fargs=(scale,), max_steps=200000)
    calls = [c for c in emu.calls if c.target == DAMAGE]
    if copy:
        assert not emu.calls, 'prediction copy reached a callee'
        assert mem.u32(SEED) == seed, 'prediction copy advanced the shared seed'
        return
    assert len(calls) == 1, ('damage call count', len(calls))
    assert sum(c.target == RECALC for c in emu.calls) == 1
    assert sum(c.target == RANK_SCALE for c in emu.calls) == int(heavy)
    # With the rank-scale helper's input zero, its original result is 0.9.
    # The heavy request adds 90 percent of each bound before an optional scale.
    expected = ((10, 20) if not heavy else (19, 38))
    if scale == 0.5:
        expected = ((5, 10) if not heavy else (10, 19))
    actual = (mem.s32(RECORD + 0xD0), mem.s32(RECORD + 0xD4))
    assert actual == expected, (weapon_class, step, heavy, scale, actual, expected)
    assert mem.s32(RECORD + 0xCC) == 100
    flags = 1 | (0x80000 if scale else 0x40000) | (0x1000 if weapon_class == 1 else 0)
    if heavy:
        flags |= 0x200000
    assert calls[0].args[5] == flags, (hex(calls[0].args[5]), hex(flags))
    assert mem.u32(SEED) == seed, 'stubbed hit advanced the shared seed'


def guard_probe(executable, seed, state, flags, front):
    """Run the original player damage slot with real direction helpers."""
    emu = EE(executable)
    mem = emu.mem
    player = emu.alloc(0x600)
    attacker = emu.alloc(0x600)
    animation = emu.alloc(0x100)
    mem.write(0x41B721, b'hub\0')
    mem.w32(player + 0xC, 0x60)
    mem.w32(player + 0x3C8, 0)
    mem.w32(player + 0x58C, state)
    mem.w32(player + 0x24, animation)
    mem.wf32(player + 0x10, 100)
    mem.wf32(player + 0x14, 200)
    mem.wf32(attacker + 0x10, 110 if front else 90)
    mem.wf32(attacker + 0x14, 200)
    mem.w16(player + 0x38, 0)
    mem.wf32(RECORD + 0xAC, 100)
    mem.w32(SEED, seed)
    emu.follow = {0x3B8534, 0x166630, 0x1666E0}  # strcmp, cos16, sin16
    emu.call(TAKE_DAMAGE, player, attacker, flags, fargs=(25.0,), max_steps=100000)
    expected = (0.0 if flags == 0 else 12.5 if flags == 0x20000 else 25.0)
    if state == 2 or not front:
        expected = 25.0
    assert mem.f32(player + 0xC8) == expected, (state, flags, front, mem.f32(player + 0xC8))
    assert mem.u32(player + 0x2DC) == flags
    guard_attempt = state == 8 and flags != 0x40
    expected_seed = ((seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) if guard_attempt else seed
    assert mem.u32(SEED) == expected_seed, (state, flags, front, hex(mem.u32(SEED)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256
    count = 0
    for weapon_class in (0, 1, 5):
        for step in (0, 1, 2, 3):
            for heavy in (False, True):
                for scale in (0.0, 0.5):
                    probe(args.executable, args.seed, weapon_class, step, heavy, scale)
                    count += 1
    probe(args.executable, args.seed, 0, 0, False, 0.0, copy=True)
    guards = 0
    for state in (2, 8, 11):
        for flags in (0, 0x20000, 0x40):
            for front in (True, False):
                guard_probe(args.executable, args.seed, state, flags, front)
                guards += 1
    print('PASS seed %d: %d original melee handoffs, 1 prediction-copy refusal, %d guard hits' %
          (args.seed, count, guards))


if __name__ == '__main__':
    main()
