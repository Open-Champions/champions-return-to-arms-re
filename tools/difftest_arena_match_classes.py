#!/usr/bin/env python3
"""Compare recipe-0 Goblin/Mummy neutral contracts with original EE execution.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_match_classes.py local/SLUS_209.73 --seed 20973

The base constructor, animation, holder and world services are deterministic
stubs. Class constructors, all requested set-state numbers 0..24, all run
switch arms 0..24, and own GameObject_rand execute in the original. The two
base-class virtual slots for takeDamage and onDeath are asserted. This is not
a live fight or full branch coverage; see the class spec documents.
"""
import argparse
import hashlib

from ee_emu import EE
import ref_arena_match_classes as R

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SEED_SHARED = 0x404464
FRAME = 0x44FDCC
TAKE_DAMAGE = 0x116638
ON_DEATH = 0x10BEB8
HIT_POINTS = 0x42C80000


def fixture(path, kind, seed, state=0):
    spec = R.SPECS[kind]
    emu = EE(path)
    creature = emu.alloc(0x600)
    pos = emu.alloc(16)
    name = emu.mem.u32(0x5037F0 + 4 * spec['index'])
    emu.mem.w32(creature + 0x24, spec['definition'])
    emu.mem.w32(creature + 0x34, name)
    emu.mem.w32(creature + 0x48, spec['table'])
    emu.mem.w32(creature + 0x50, creature + spec['holder'])
    emu.mem.w32(creature + spec['holder'], spec['holder_table'])
    emu.mem.w32(creature + 0x44, seed)
    emu.mem.w32(creature + 0xC, 0x20)
    emu.mem.w16(creature + 0x232, state)
    emu.mem.w32(creature + 0x228, HIT_POINTS)
    emu.mem.w32(creature + 0x22C, HIT_POINTS)
    emu.mem.w32(creature + 0x300, 10)
    emu.mem.w32(FRAME, 100)
    emu.mem.w32(SEED_SHARED, seed)
    emu.follow = {R.RAND}
    emu.stub(0x10C0F0, ret=1)  # active in the run switch
    emu.stub(R.FILTER, ret=0)  # accept the set-state request unchanged
    return emu, creature, pos, name


def targets(emu):
    return tuple(call.target for call in emu.calls)


def draw_state(seed, count):
    for _ in range(count):
        seed, _ = R.next_draw(seed)
    return seed


def check_ctor(path, kind, seed):
    spec = R.SPECS[kind]
    emu, c, pos, name = fixture(path, kind, seed)
    emu.mem.w32(c + 0x44, 0)  # pool_new returns a zero-filled class block

    def base(e):
        # Creature_ctor and its GameObject ctor are independently compared in
        # difftest_creature.py. This fixture supplies their fields, then the
        # class constructor runs from its return point.
        e.mem.w32(c + 0x24, spec['definition'])
        e.mem.w32(c + 0x34, name)
        e.mem.w32(c + 0x48, spec['table'])
        e.mem.w32(c + 0xC, 0x20)
        shared, _ = R.next_draw(e.mem.u32(SEED_SHARED))
        e.mem.w32(SEED_SHARED, shared)
        e.mem.w32(c + 0x44, shared)
        return c

    emu.stub(0x109D68, function=base)
    emu.stub(0x159C20, ret=1)  # plain class name has none of the role prefixes
    args = (c, pos, 0, name, 0) + ((0,) if kind == R.GOBLIN else ())
    emu.call(spec['ctor'], *args)
    want_calls, draws, fields, own_seed, shared_seed = R.constructor(kind, seed)
    assert targets(emu) == want_calls, (kind, seed, 'constructor calls', targets(emu), want_calls)
    assert sum(target == R.RAND for target in targets(emu)) == draws
    assert emu.mem.u32(c + 0x44) == own_seed, (kind, seed, 'own seed')
    assert emu.mem.u32(SEED_SHARED) == shared_seed, (kind, seed, 'shared seed')
    for off, want in fields.items():
        got = emu.mem.u32(c + off)
        assert got == want, (kind, seed, 'constructor field', hex(off), hex(got), hex(want))
    assert emu.mem.u32(c + 0x50) == c + spec['holder']
    flags = 0x200000000 | 0x40000 if kind == R.GOBLIN else 0x400010000
    assert emu.mem.u64(c + 0xA8) == flags, (kind, seed, 'creature flags')
    return 1


def check_set_states(path, kind, seed):
    spec = R.SPECS[kind]
    for state in range(0x19):
        emu, c, _pos, _name = fixture(path, kind, seed)
        emu.call(spec['set_state'], c, state)
        want_calls, draws, want_state, stores = R.set_state(kind, state, seed)
        got_calls = tuple(target for target in targets(emu) if target != R.RAND)
        assert got_calls == want_calls, (kind, seed, 'set calls', state, got_calls, want_calls)
        assert sum(target == R.RAND for target in targets(emu)) == draws, (kind, seed, 'set draws', state)
        assert emu.mem.u32(c + 0x44) == draw_state(seed, draws), (kind, seed, 'set seed', state)
        assert emu.mem.u32(SEED_SHARED) == seed, (kind, seed, 'set shared seed', state)
        assert emu.mem.u16(c + 0x232) == want_state, (kind, seed, 'set state', state)
        for off, want in stores.items():
            actual = emu.mem.u64(c + off) if off == 0xA8 else emu.mem.u32(c + off)
            assert actual == want, (kind, seed, 'set field', state, hex(off), actual, want)
        if state == 0x14:
            assert ON_DEATH in targets(emu), (kind, seed, 'death callback')
            assert (0x10F2C8 in targets(emu)), (kind, seed, 'death loot path')
    return 0x19


def check_runs(path, kind, seed):
    spec = R.SPECS[kind]
    for state in range(0x19):
        emu, c, _pos, _name = fixture(path, kind, seed, state)
        emu.call(spec['run'], c)
        want = R.run(kind, state)
        assert targets(emu) == want, (kind, seed, 'run calls', state, targets(emu), want)
        assert emu.mem.u32(c + 0x44) == seed, (kind, seed, 'run own seed', state)
        assert emu.mem.u32(SEED_SHARED) == seed, (kind, seed, 'run shared seed', state)
    return 0x19


def check_virtuals(emu, kind):
    table = R.SPECS[kind]['table']
    assert emu.mem.u32(table + 8 * 2 + 4) == TAKE_DAMAGE, (kind, 'takeDamage slot')
    assert emu.mem.u32(table + 8 * 28 + 4) == ON_DEATH, (kind, 'onDeath slot')
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable'
    for kind in (R.GOBLIN, R.MUMMY):
        count = check_ctor(args.elf, kind, args.seed)
        count += check_set_states(args.elf, kind, args.seed)
        count += check_runs(args.elf, kind, args.seed)
        emu, _c, _pos, _name = fixture(args.elf, kind, args.seed)
        count += check_virtuals(emu, kind)
        print('%s: %d constructor/state/run/virtual comparisons matched (seed %d)' %
              (kind, count, args.seed))


if __name__ == '__main__':
    main()
