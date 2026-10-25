#!/usr/bin/env python3
"""Execute Player_ctor and the arena player replacement on the owner's US v2.00
executable (seeds 20973 and 7).

1. Player_ctor alone, base constructor stubbed (the bounded contract).
2. The whole chain: Player_ctor with the real Creature_ctor and GameObject_ctor, the
   real Player class definition, authored resource answers; every non-stack byte the
   three bodies store, every call in order with its key arguments, the shared seed.
3. The Player destructor (slot 1) with flags 0/1/3, linked and unlinked records.
4. Player_startSpawnProtection over network, recall, resurrection and allocation cases.
5. game_resetTimers4f84a8.
6. arena_startWave's slot loop with every body above real: placement through the
   original arena_pickSpawnPoint, destruction, pool reuse, construction, seed.
"""
import argparse
import os

from ee_emu import EE
import ref_arena_player as R


def flatten(fields):
    return {address + i: (value >> (8 * i)) & 0xFF
            for address, (size, value) in fields.items() for i in range(size)}


def one(path, seed):
    e = EE(path)
    player = e.alloc(0x590)
    pos = e.alloc(16)
    definition = e.alloc(0x400)
    part = e.alloc(0x200)
    for offset in range(0, 0x400, 4):
        e.mem.w32(definition + offset, part)
    e.mem.w32(R.RECORDS + 0x54, 0)
    e.mem.write(R.RECORDS + 0x20, b'\xff' * 4)
    e.mem.w32(R.SEED, seed)
    e.follow = {0x1509D0}

    def base(x):
        x.mem.w32(player + 0x24, definition)
        return player

    e.stub(0x109D68, function=base)
    e.call(R.CTOR, player, pos, 0, 0)
    actual = {}
    for pc, address, size, value in e.writes:
        if R.CTOR <= pc <= 0x1A24B4:
            actual.update(flatten({address: (size, value)}))
    expected = flatten(R.constructor_fields(player, 0, part))
    expected.update(flatten({0x4EBBB4: (4, 0x5353E0)}))
    assert actual == expected, (seed,
        {'missing': sorted(set(expected) - set(actual)),
         'extra': sorted(set(actual) - set(expected)),
         'different': [(hex(a), actual[a], expected[a]) for a in actual.keys() & expected.keys()
                       if actual[a] != expected[a]][:20]})
    calls = tuple(c.target for c in e.calls)
    assert calls == R.CALLS, (seed, calls)
    assert e.mem.u32(R.SEED) == seed, (seed, e.mem.u32(R.SEED))
    assert e.mem.u32(R.RECORDS + 0x43D8) == player
    return len(actual), len(calls)


def stores(e, spans):
    actual = {}
    for pc, address, size, value in e.writes:
        if any(lo <= pc < hi for lo, hi in spans):
            actual.update(flatten({address: (size, value)}))
    return actual


UNALIGNED_PAIR = {0x109E44, 0x109E48}   # Creature_ctor's sdl/sdr copy of the home vector to +0x3b4


def final_stores(e, spans, before=None, expected=()):
    """Bytes stored by code in ``spans`` with their final values read from memory.  The
    interpreter logs an sdl/sdr store as its aligned doubleword; bytes of the
    Creature_ctor pair that end equal to their value before the call (``before``) are
    not counted as stores unless the model names them."""
    actual, loose = {}, {}
    for pc, address, size, value in e.writes:
        if any(lo <= pc < hi for lo, hi in spans):
            for i in range(size):
                (loose if pc in UNALIGNED_PAIR else actual).setdefault(address + i, None)
    for address in set(loose) - set(actual):
        if before is None or address in expected or e.mem.u8(address) != before(address):
            actual[address] = None
    return {address: e.mem.u8(address) for address in actual}


def compare(tag, actual, expected):
    assert actual == expected, (tag,
        {'missing': [hex(a) for a in sorted(set(expected) - set(actual))][:20],
         'extra': [hex(a) for a in sorted(set(actual) - set(expected))][:20],
         'different': [(hex(a), actual[a], expected[a]) for a in sorted(actual.keys() & expected.keys())
                       if actual[a] != expected[a]][:20]})


def call_key(c):
    return (c.target,) + tuple(a & 0xFFFFFFFF for a in c.args)


CHAIN_CASES = (  # position (x, y, z) floats as patterns, facing, slot, serial counter
    ((0x43480000, 0xC3480000, 0), 0x1234, 0, 0),
    ((0, 0, 0x41200000), 0, 1, 7),
    ((0x47000000, 0, 0), 0x8000, 0, 0xFF),     # 32768.0: off the 120 x 120 grid
    ((0xC2C80000, 0x42C80000, 0x3F800000), 0xC000, 3, 0x40),
)


def chain(path, seed, pos, facing, slot, serial):
    e = EE(path)
    player = e.alloc(0x590)
    point = e.alloc(16)
    part = e.alloc(0x200)
    for k in range(3):
        e.mem.w32(point + 4 * k, pos[k])
    record = R.RECORDS + slot * R.RECORD_SIZE
    e.mem.write(record + 0x20, b'\xff' * 4)
    e.mem.w32(R.SEED, seed)
    e.mem.w8(R.AM.G_SERIAL_COUNTER, serial)
    expected_writes, new_seed, base_calls = R.chain_writes(e.mem.u32, player, pos, facing, slot, seed, part, serial)
    e.follow = {R.CREATURE_CTOR, R.GAMEOBJECT_CTOR}
    e.stub(R.RES_FIND, ret=part)
    e.call(R.CTOR, player, point, facing, slot, 0)
    compare(('chain', seed, slot),
            final_stores(e, (R.GAMEOBJECT_SPAN, R.CREATURE_SPAN, R.PLAYER_SPAN),
                         lambda a: 0 if player <= a < player + 0x590 else None,
                         R.final_bytes(expected_writes)),
            R.final_bytes(expected_writes))
    targets = tuple(c.target for c in e.calls)
    assert targets == tuple(c[0] for c in base_calls) + R.CALLS[1:], (seed, [hex(t) for t in targets])
    for c, want in zip(e.calls, base_calls):
        got = call_key(c)
        if want[0] == R.CREATURE_CTOR:
            assert got[1] == player and got[2] == 0 and (got[4] & 0xFFFF) == facing and got[5] == R.PLAYER_DEF \
                and got[6] == 0 and c.fargs[0] == R.CTOR_HP, (seed, got)
            assert tuple(e.mem.u32(got[3] + 4 * k) for k in range(3)) == tuple(pos)
        elif want[0] == R.GAMEOBJECT_CTOR:
            assert got[1] == player and got[3] == R.PLAYER_DEF and got[4] == 0, (seed, got)
        else:
            assert got[:len(want)] == want, (seed, [hex(x) for x in got[:4]], [hex(x) for x in want])
    assert e.mem.u32(R.SEED) == new_seed
    assert e.mem.u32(record + 0x43D8) == player
    draws = sum(1 for pc, address, _s, _v in e.writes if address == R.SEED)
    return len(R.final_bytes(expected_writes)), len(e.calls), draws


def dtor_case(path, seed, slot, linked, flags):
    e = EE(path)
    player = e.alloc(0x590)
    record = R.RECORDS + slot * R.RECORD_SIZE
    e.mem.w32(player + 0x3C8, slot)
    e.mem.w32(player + 0x48, R.VTABLE)
    e.mem.w32(record + 0x43D8, player if linked else 0x01234560)
    for k in range(5):
        e.mem.w32(record + 0x43DC + 4 * k, 0x11111111 * (k + 1))
    e.mem.w32(R.SEED, seed)
    e.follow = set()
    e.stub(R.POOL_FREE)
    e.call(R.PLAYER_DTOR, player, flags)
    writes, calls = R.destructor(player, slot, flags)
    compare(('dtor', slot, linked, flags), stores(e, ((R.PLAYER_DTOR, R.CTOR),)),
            flatten({a: (w, v) for a, w, v in writes}))
    assert [call_key(c)[:2] for c in e.calls] == [c[:2] for c in calls], (slot, flags)
    assert e.mem.u32(R.SEED) == seed
    return len(calls)


def protection_case(path, seed, network, recall, raised, light, guard, samples):
    e = EE(path)
    player = e.alloc(0x590)
    block = e.alloc(0x100) if light else 0
    slot = 1 + network
    model, sound = 0x00C00010 + slot, 0x00C00100 + guard
    e.mem.w32(player + 0x3C8, slot)
    e.mem.w32(player + 0xC, 0x4060)
    e.mem.w32(player + 0x544, model)
    e.mem.w8(R.NETWORK_BYTE, network)
    e.mem.w8(R.RECALL_COUNTDOWN, recall)
    e.mem.w32(R.PARTICLE_GUARD, guard)
    seeds = (seed, seed ^ 0x5A5A, seed + 3)
    for address, value in zip((R.SEED, 0x404460, 0x404468), seeds):
        e.mem.w32(address, value)
    e.follow = set()
    e.stub(R.IS_SLOT_RAISED, ret=raised)
    e.stub(R.POOL_NEW, ret=block)
    e.stub(R.RES_FIND, ret=sound)
    e.stub(R.SAMPLE_COUNT, ret=samples)
    e.call(R.SPAWN_PROTECTION, player)
    writes, calls = R.spawn_protection(player, slot, network, recall, raised, block, guard, sound, model, samples)
    expected = {}
    for a, w, v in writes:
        expected.update(flatten({a: (w, 0x4062 if v is None else v)}))
    compare(('protect', network, recall, raised, light, guard), stores(e, (R.PROTECT_SPAN,)), expected)
    got = [call_key(c) for c in e.calls]
    assert len(got) == len(calls) and [g[:len(c)] for g, c in zip(got, calls)] == calls, \
        ([tuple(hex(x) for x in g[:3]) for g in got], calls)
    sound_call = next(c for c in e.calls if c.target == R.SOUND_PLAY)
    assert sound_call.fargs[0] == 0x3F800000
    assert tuple(e.mem.u32(a) for a in (R.SEED, 0x404460, 0x404468)) == seeds
    return len(got)


def timers(path, seed):
    e = EE(path)
    e.mem.w32(R.SEED, seed)
    e.follow = set()
    e.call(R.RESET_TIMERS)
    compare('timers', stores(e, ((R.RESET_TIMERS, R.RESET_TIMERS + 0x48),)),
            flatten({a: (w, v) for a, w, v in R.reset_timers()}))
    assert not e.calls and e.mem.u32(R.SEED) == seed


class Follow:
    """Named bodies plus the C library / software float range (as difftest_player)."""

    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or 0x3A5000 <= target < 0x3C0000

    def add(self, target):
        self.addresses.add(target)


def start_wave(path, seed):
    """arena_startWave(1) on the offline one-player arena state of the probe."""
    import difftest_arena_modes as D
    import probe_arena_match as P
    import ref_arena_modes as M
    emu = P.setup(path, 0, seed)
    old = emu.arena_player
    entry = (M.K_ZERO if hasattr(M, 'K_ZERO') else 0,) * 3
    part = emu.alloc(0x200)
    emu.follow = Follow({D.START, R.PICK_SPAWN, R.PLAYER_DTOR, R.CTOR, R.CREATURE_CTOR, R.GAMEOBJECT_CTOR,
                         R.RESET_TIMERS, 0x166630, 0x1666E0, 0x166798})   # + angle helpers, C library
    freed = []

    def find_spot(e):
        out, point, ok = e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF, e.r[8] & 0xFFFFFFFF
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def pool_free(e):
        freed.append(e.r[4] & 0xFFFFFFFF)

    def pool_new(e):
        if (e.r[4] & 0xFFFFFFFF) == 0x590 and freed:
            block = freed.pop()
            e.mem.write(block, bytes(0x590))   # pool_new zero-fills (object-system.md 2.1)
            return block
        return 0

    emu.stub(0x14ACF8, function=find_spot)
    emu.stub(R.POOL_FREE, function=pool_free)
    emu.stub(R.POOL_NEW, function=pool_new)
    emu.stub(R.RES_FIND, ret=part)
    emu.stub(D.STEP)
    emu.stub(D.SPAWN)
    before = emu.mem.u32(R.SEED)
    emu.call(D.START, 1)
    tail = [c for c in emu.calls if c.target == R.POOL_FREE]
    assert [c.args[0] & 0xFFFFFFFF for c in tail] == [old], 'destructor frees the old block once'
    replace = [c for c in emu.calls if c.site in R.REPLACE_SITES.values() and c.target != R.POOL_FREE]
    sites = {c.site: c for c in replace}
    assert sorted(sites) == sorted(R.REPLACE_SITES.values()), [hex(s) for s in sites]
    order = [c.site for c in replace]
    assert order == [R.REPLACE_SITES[k] for k in ('pick', 'dtor', 'new', 'ctor', 'timers')], [hex(x) for x in order]
    points = [(0, 0, 0, 0)]
    spawn, facing, seed_after_pick = M.pick_spawn(
        1, 0, points, before, 0, 0, 0, None, 1, lambda centre, spread, radius: (list(centre), 1), None)
    ctor = sites[R.REPLACE_SITES['ctor']]
    a = [x & 0xFFFFFFFF for x in ctor.args]
    assert a[0] == old and a[3] == 0 and a[4] == 0, [hex(x) for x in a[:5]]
    placed = (emu.mem.u32(old + 0x10), emu.mem.u32(old + 0x14), emu.mem.u32(old + 0x3BC))
    home = tuple(emu.mem.u32(old + 0x3B4 + 4 * k) for k in range(3))
    assert home == tuple(spawn) and placed == tuple(spawn), ('placement', [hex(v) for v in home], spawn)
    assert (a[2] & 0xFFFF) == (facing & 0xFFFF) == emu.mem.u16(old + 0x38) == emu.mem.u16(old + 0x2FA), (hex(a[2]), hex(facing & 0xFFFF), hex(emu.mem.u16(old + 0x38)), hex(emu.mem.u16(old + 0x2FA)))
    pick = sites[R.REPLACE_SITES['pick']]
    assert (pick.args[0] & 0xFFFFFFFF, pick.args[1] & 0xFFFFFFFF) == (1, 0)
    assert sites[R.REPLACE_SITES['dtor']].args[1] & 0xFF == 3
    expected_seed, _draw = R.lcg(seed_after_pick)
    assert emu.mem.u32(R.SEED) == expected_seed, (hex(emu.mem.u32(R.SEED)), hex(expected_seed))
    assert emu.mem.u32(R.RECORDS + 0x43D8) == old and emu.mem.u32(old + 0x48) == R.VTABLE
    assert all(emu.mem.u16(R.DEAD_COUNTDOWNS + 2 * k) == 0xF0 for k in range(4))
    return spawn, facing


PLAYER_RESPAWN = 0x1BD040


def respawn(path, seed, placement):
    """player_respawn(0, position, facing, a, b) with the real destructor, pool reuse,
    constructor chain and spawn protection (offline, local slot, mode B, no Resurrect)."""
    e = EE(path)
    old = e.alloc(0x590)
    pos = e.alloc(16)
    part = e.alloc(0x200)
    record = R.RECORDS
    e.mem.w32(old + 0x48, R.VTABLE)
    e.mem.w32(old + 0x3C8, 0)
    e.mem.w32(record + 0x43D8, old)
    e.mem.write(record + 0x20, b'\xff' * 4)
    e.mem.wf32(record + 0xB0, 100.0)
    e.mem.w32(0x4F7120, 1)       # g_pvpModeB
    e.mem.w32(0x4D8AE0, 1)       # g_numPlayers
    e.mem.w32(R.SEED, seed)
    spot = (0x41200000, 0x41A00000, 0)      # 10.0, 20.0, 0.0
    for k in range(3):
        e.mem.w32(pos + 4 * k, spot[k])
    freed = []
    e.follow = Follow({R.PLAYER_DTOR, R.CTOR, R.CREATURE_CTOR, R.GAMEOBJECT_CTOR, R.SPAWN_PROTECTION})
    e.stub(0x13E150, ret=1)                  # net_isLocalSlot
    e.stub(R.POOL_FREE, function=lambda x: freed.append(x.r[4] & 0xFFFFFFFF))

    def pool_new(x):
        if (x.r[4] & 0xFFFFFFFF) == 0x590 and freed:
            block = freed.pop()
            x.mem.write(block, bytes(0x590))
            return block
        return 0

    def find(x):
        for j in range(3):
            x.mem.w32((x.r[4] & 0xFFFFFFFF) + 4 * j, x.mem.u32((x.r[5] & 0xFFFFFFFF) + 4 * j))
        return 1

    e.stub(R.POOL_NEW, function=pool_new)
    e.stub(0x14ACF8, function=find)
    e.stub(R.RES_FIND, ret=part)
    e.call(PLAYER_RESPAWN, 0, pos, 0x2000, *placement)
    assert e.mem.u32(record + 0x43D8) == old, 'pool reuse: the new Player has the old block'
    assert tuple(e.mem.u32(old + 0x3B4 + 4 * k) for k in range(3)) == spot
    assert e.mem.u16(old + 0x38) == 0x2000 and e.mem.u32(old + 0x48) == R.VTABLE
    assert e.mem.u16(old + 0x4B4) == 60 and e.mem.u32(old + 0xC) & 0x4062 == 0x4062
    assert e.mem.u16(R.DEAD_COUNTDOWNS) == 240 and e.mem.f32(record + 0xAC) == 50.0
    expected_seed, _ = R.lcg(seed)
    assert e.mem.u32(R.SEED) == expected_seed, 'exactly one shared draw (GameObject_ctor)'
    return sum(1 for c in e.calls if c.target == R.POOL_FREE)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf')
    args = ap.parse_args()
    if not os.path.isfile(args.elf):
        raise SystemExit('executable missing')
    for seed in (20973, 7):
        writes, calls = one(args.elf, seed)
        print('seed %d: Player_ctor %d direct bytes, %d calls, 0 shared draws matched' %
              (seed, writes, calls))
        for case in CHAIN_CASES:
            n, c, draws = chain(args.elf, seed, *case)
            print('seed %d: chain slot %d facing %#x: %d bytes, %d calls, %d shared draw matched'
                  % (seed, case[2], case[1], n, c, draws))
        cases = [(s, l, f) for s in (0, 2) for l in (0, 1) for f in (0, 1, 3)]
        for case in cases:
            dtor_case(args.elf, seed, *case)
        print('seed %d: destructor %d cases matched' % (seed, len(cases)))
        cases = [(n, r, x, l, g, k) for n in (0, 1) for r in (0, 1) for x in (0, 1) for l in (0, 1)
                 for g, k in ((0, 0), (1, 3))]
        for case in cases:
            protection_case(args.elf, seed, *case)
        print('seed %d: spawn protection %d cases matched' % (seed, len(cases)))
        timers(args.elf, seed)
        spawn, facing = start_wave(args.elf, seed)
        print('seed %d: arena_startWave replacement matched, spawn %s facing %#x'
              % (seed, tuple(hex(v) for v in spawn), facing & 0xFFFF))
        for placement in ((-1, -1), (2, 3)):
            respawn(args.elf, seed, placement)
        print('seed %d: player_respawn composed (exact and free-spot) matched, 1 shared draw' % seed)


if __name__ == '__main__':
    main()
