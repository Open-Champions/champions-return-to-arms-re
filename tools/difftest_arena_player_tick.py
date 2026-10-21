#!/usr/bin/env python3
"""Arena tick of a Player built by the real constructor chain (seeds 20973 and 7).

  python3 tools/difftest_arena_player_tick.py local/SLUS_209.73 [--seed N] [--ticks N] [--cases N]

The player object is not authored here. Section 2 of tools/difftest_arena_player.py
constructs it in place: original Player_ctor, Creature_ctor and GameObject_ctor, the
real Player class definition 0x4ecc58, offline mode B (g_pvpModeB 0x4f7120 = 1). The
comparison then reuses two harnesses whose reference models are already executed:

* Player_run 0x1a5030 against tools/ref_player.py, through difftest_player.Rig
  (docs/spec/player-tick.md). Every tick compares calls, stored bytes and final values,
  and the shared seed. The pad script holds the stick, taps attack for a melee combo,
  or stays idle: neutral state 2, melee state 1 and walking, the states the arena probe
  reaches. A player that the harness's scripted damage kills (state 4) is rebuilt by
  the constructor after 40 dead ticks, as player_respawn replaces it.
* Player_takeDamage 0x1b5330 and Player_processDamage 0x1b2cc0 against
  tools/ref_combat_ptick.py, through difftest_combat_ptick.Rig
  (docs/spec/combat-player-defence.md, t3/research-combat).

The fixture changes after construction are named, not hidden. +0x48 points at the
harness's scripted virtual table, because the virtual slots are the harness's call-outs.
The harness's record supplies equipment, a one-hand weapon. Every res_find during
construction answers with one of the harness's scripted animation handles, whose
page is mapped as zeroed memory so the constructor's event-field stores land there. Faults
count as failures here: the arena player must run without reading unmapped memory.
"""
import argparse
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE                          # noqa: E402
import difftest_player as DP                   # noqa: E402
import difftest_combat_ptick as DT             # noqa: E402
import ref_arena_player as R                   # noqa: E402
import ref_player as RP                        # noqa: E402

PVP_MODE_B = 0x4F7120
LIB = (0x3A5000, 0x3C0000)


class Follow:
    def __init__(self, addresses):
        self.addresses = set(addresses)

    def __contains__(self, target):
        return target in self.addresses or LIB[0] <= target < LIB[1]


def construct(emu, block, slot, pos, facing, answers):
    """Run the original constructor chain on ``block`` (zero-filled first, as pool_new
    does) inside a harness emulator. The harness's own hooks are set aside for the call
    and restored after it. Returns the shared seed before and after."""
    saved_hooks, saved_names, saved_follow = dict(emu.hooks), dict(emu.stub_names), emu.follow
    emu.hooks, emu.stub_names = {}, {}
    emu.mem.write(block, bytes(0x590))
    point = emu.alloc(16)
    for k in range(3):
        emu.mem.w32(point + 4 * k, pos[k])
    turn = iter(range(1 << 30))
    emu.stub(R.RES_FIND, function=lambda e: answers[next(turn) % len(answers)])
    emu.follow = Follow({R.CTOR, R.CREATURE_CTOR, R.GAMEOBJECT_CTOR})
    before = emu.mem.u32(R.SEED)
    emu.r[29] = emu.stack_hi - 0x100
    emu.call(R.CTOR, block, point, facing, slot, 0)
    after = emu.mem.u32(R.SEED)
    emu.hooks, emu.stub_names, emu.follow = saved_hooks, saved_names, saved_follow
    emu.reset_log()
    assert after == R.lcg(before)[0], 'constructor chain draws exactly once'
    assert emu.mem.u32(R.RECORDS + slot * R.RECORD_SIZE + 0x43D8) == block
    assert emu.mem.u32(block + 0x58C) == 2 and emu.mem.u32(block + 0x48) == R.VTABLE
    return before, after


# ---------------------------------------------------------------------------
# Player_run
# ---------------------------------------------------------------------------
def pad_plan(rng):
    kind = rng.random()
    if kind < 0.3:
        return [(0, 0.0, 0.0)] * rng.randrange(5, 40)                       # idle
    if kind < 0.65:
        lx, ly = rng.uniform(-1, 1), rng.uniform(-1, 1)
        return [(0, lx, ly)] * rng.randrange(5, 60)                         # walk
    plan = []
    for _ in range(rng.randrange(1, 5)):                                    # melee combo
        plan += [(DP.BTN['attack'], 0.0, 0.0)] * rng.randrange(1, 3)
        plan += [(0, 0.0, 0.0)] * rng.randrange(1, 25)
    return plan


def run_tick_section(elf, seed, ticks):
    rig = DP.Rig(elf, seed, 0, 0, 0)
    world, mem, rng = rig.world, rig.emu.mem, rig.rng
    slot, P, Rr = world.slot, world.P, world.R
    world.equip(slot, 'sword', rng)
    mem.wf32(Rr + 0xAC, 100.0)
    mem.w32(PVP_MODE_B, 1)
    spawn = (0x42100000, 0x37100000, 0)          # the ring point difftest_arena_player places
    if not mem.is_mapped(world.anims[0], 0x100):
        mem.map(world.anims[0] & ~0xFFF, 0x1000)  # the constructor writes event fields into its parts
    construct(rig.emu, P, slot, spawn, 1, world.anims)
    mem.w32(P + 0x48, world.vt_player)
    pad = RP.G_PADS + slot * RP.PAD_SIZE
    states, bad, plan, held, dead, rebuilt = {}, [], [], 0, 0, 0
    for t in range(ticks):
        dead = dead + 1 if mem.u32(P + 0x58C) == 4 else 0
        if dead > 40:                              # as player_respawn: a new object, same block
            mem.wf32(Rr + 0xAC, 50.0)
            construct(rig.emu, P, slot, spawn, 1, world.anims)
            mem.w32(P + 0x48, world.vt_player)
            dead, rebuilt = 0, rebuilt + 1
        if not plan:
            plan = pad_plan(rng)
        buttons, lx, ly = plan.pop(0)
        mem.w32(pad + 8, buttons)
        mem.w32(pad + 0xC, buttons & ~held)
        held = buttons
        mem.wf32(pad + 0x14, lx)
        mem.wf32(pad + 0x18, ly)
        state = mem.u32(P + 0x58C)
        result = rig.tick(seed * 1000003 + t)
        row = states.setdefault(state, [0, 0])
        row[0] += 1
        ok = not result['fault'] and result['calls_ok'] and result['set_ok'] and result['values_ok'] \
            and result['seed_ok']
        if not ok:
            row[1] += 1
            if len(bad) < 3:
                bad.append((t, state, 'fault %r / %r' % (result.get('model_error'), result.get('emu_error'))
                            if result['fault'] else DP.describe_calls(result['model_calls'], result['emu_calls'])
                            if not result['calls_ok'] else 'writes or seed'))
            if result['fault']:
                break
        mem.w32(RP.G_SIM_FRAME, (mem.u32(RP.G_SIM_FRAME) + 1) & 0xFFFFFFFF)
    if rig.unknown:
        bad.append(('unknown calls', {hex(a): n for a, n in rig.unknown.items()}))
    return states, bad, rebuilt


# ---------------------------------------------------------------------------
# Player_takeDamage / Player_processDamage
# ---------------------------------------------------------------------------
def damage_section(elf, seed, key, cases):
    rig = DT.Rig(elf, seed)
    w, mem = rig.world, rig.emu.mem
    rng = random.Random(seed * 37 + len(key))
    compared = failed = refused = 0
    shown = []
    for n in range(cases):
        args = list(DT.generate(rig, key, rng))
        P = args[0]
        slot = mem.u32(P + 0x3C8)
        keep = {off: mem.u32(P + off) for off in (0x58C, 0x4B4, 0x2DC, 0xC8, 0x540, 0x360, 0x2E4, 0x44C, 0x588)}
        keep8 = mem.u8(P + 0x118)
        construct(rig.emu, P, slot, (mem.u32(P + 0x10), mem.u32(P + 0x14), mem.u32(P + 0x18)),
                  rng.randrange(0x10000), [w.anim_table + 4 * k for k in range(8)])
        mem.w32(P + 0x48, w.table_p)
        for off, value in keep.items():                  # the case's combat state, not construction
            mem.w32(P + off, value)
        mem.w8(P + 0x118, keep8)
        mem.w32(DT.T.G_PVP_MODE_B, 1)
        mem.w32(DT.T.G_PVP_MODE_A, 0)
        out = rig.compare(key, tuple(args), rng.getrandbits(32))
        if out == 'refused':
            refused += 1
            continue
        compared += 1
        if out:
            failed += 1
            if len(shown) < 2:
                shown.append((n, out))
    if rig.unknown:
        shown.append(('unknown calls', {hex(a): v for a, v in rig.unknown.items()}))
        failed += 1
    return compared, failed, refused, rig.draws, shown


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf')
    ap.add_argument('--seed', type=int, action='append')
    ap.add_argument('--ticks', type=int, default=1500)
    ap.add_argument('--cases', type=int, default=400)
    args = ap.parse_args()
    if not os.path.isfile(args.elf):
        raise SystemExit('executable missing')
    ok = True
    for seed in args.seed or (20973, 7):
        states, bad, rebuilt = run_tick_section(args.elf, seed, args.ticks)
        compared = sum(v[0] for v in states.values())
        failed = sum(v[1] for v in states.values())
        print('seed %d: Player_run on the constructed arena player: %d ticks, %d mismatching, %d rebuilds; '
              'states %s' % (seed, compared, failed, rebuilt,
                             ', '.join('%d:%d' % (s, v[0]) for s, v in sorted(states.items()))))
        for item in bad:
            print('    ', item)
        ok = ok and not bad
        for key in ('takeDamageFull', 'processDamageFull'):
            compared, failed, refused, draws, shown = damage_section(args.elf, seed, key, args.cases)
            print('seed %d: %s on the constructed arena player: %d compared, %d failed, %d refused, %d draws'
                  % (seed, key, compared, failed, refused, draws))
            for item in shown:
                print('    ', str(item)[:600])
            ok = ok and not failed
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
