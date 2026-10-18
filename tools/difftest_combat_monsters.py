#!/usr/bin/env python3
"""difftest_combat_monsters.py - compare the bodies tools/ref_combat_monsters.py adds with the
game's own code (combat research round 2, targets 5 and 6).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_monsters.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                            [--cases N] [-k TEXT] [-v]

Same method and the same harness as tools/difftest_combat_runtime.py (whose World and Rig
are reused): the ORIGINAL function runs in tools/ee_emu.py on records this script builds;
the same inputs go through ref_combat_monsters.MonsterCombatModel on a copy-on-write view
of that memory.  Equal must be: the calls to everything outside the model, in order and
with their arguments; the set of bytes stored outside the stack and their values; the
shared seed and the number of draws; the result.

Real besides the entry points (each entry point is real inside the others):
creature_canSeeObj, the angle functions and the C library (soft doubles).  Everything else
- damage_apply, terrain_raycast, the box query, the handle functions, creature_bossRank,
every virtual slot (20 is enemy, 27 set-state, 12 nearby event) - is a recording stub
answered by a seeded script; the model's call-outs get the same answers.
"""
import math
import os
import random
import struct
import sys
import types

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_combat_runtime as D             # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_monsters as M                 # noqa: E402

f32, Ext, Res = D.f32, D.Ext, D.Res

ENTRIES = {
    'canSeePoint': (0x10C238, 'ivii', 2, 'i', 'can_see_point', (0x10C238, 0x10C40C)),
    'canSeeObjEdge': (0x10C5B8, 'iiiii', 3, 'i', 'can_see_obj_edge', (0x10C5B8, 0x10C80C)),
    'canSeeTargetIn': (0x118D40, 'iiii', 3, 'i', 'can_see_target_in', (0x118D40, 0x118D90)),
    'findPlayerInCone': (0x10CA70, 'iii', 2, 'i', 'find_player_in_cone', (0x10CA70, 0x10CF78)),
    'hitTargetAtReach': (0x1196E8, 'iiiiii', 1, 'i', 'hit_target_at_reach', (0x1196E8, 0x119850)),
    'hitTargetInArcEdge': (0x119850, 'iiiiiiii', 2, 'i', 'hit_target_in_arc_edge', (0x119850, 0x119938)),
    'hitTargetOrPlayerInArc': (0x119A20, 'iiiiiiii', 2, 'i', 'hit_target_or_player_in_arc', (0x119A20, 0x119B54)),
    'knockbackTarget': (0x119D10, 'i', 1, 'n', 'knockback_target', (0x119D10, 0x119D60)),
    'setCooldown': (0x118BF0, 'ii', 0, 'n', 'set_cooldown', (0x118BF0, 0x118C50)),
    'setCooldownOn': (0x118B58, 'iii', 0, 'n', 'set_cooldown_on', (0x118B58, 0x118BF0)),
    'notifyObjectsNear': (0x11A2B8, 'ivi', 1, 'n', 'notify_objects_near', (0x11A2B8, 0x11A3EC)),
}

EXTS = {
    'Creature.v12': Ext(0, 'pivi', 1, 'n'),
    'Creature.v27': Ext(0, 'pi', 0, 'n'),
}


def _install():
    """Point the round-1 harness at this module's entries and model (module globals)."""
    shim = types.ModuleType('ref_combat_runtime_shim')
    shim.__dict__.update(T.__dict__)
    shim.CombatModel = M.MonsterCombatModel
    D.T = shim
    D.ENTRIES = ENTRIES
    D.EXTS.update(EXTS)

    def on_creature_bossRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 1, 2)))
    D.World.on_creature_bossRank = on_creature_bossRank


def generate(rig, key, rng):
    w, mem = rig.world, rig.emu.mem
    c = rng.choice(w.creatures)
    centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50))
    w.scatter(rng, centre)
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20))
    mem.w32(T.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(T.G_NUM_PLAYERS, rng.choice((1, 2, 4, 4, 0)))
    for slot in range(4):
        obj = rng.choice((w.players[slot],) * 6 + (0, w.creatures[slot]))
        mem.w32(T.G_PLAYERS + slot * T.REC_SIZE + T.REC_OBJ, obj)
    mem.w16(c + 0x312, rng.choice((0, 0, 0, 40)))
    mem.w16(c + 0x232, rng.choice((0, 3, 6, 0x14)))
    fa = rng.randrange(0x10000)
    near = rng.choice((0.0, 0.0, 10.0, 40.0))
    far = rng.choice((30.0, 48.0, 100.0, 300.0, 600.0))
    arc = rng.choice((0x1770, 0x2000, 0x4000, 0x7FFF, 0x100, 0x8000))
    target = rng.choice(w.everything)
    mem.w32(c + 0x234, rng.choice((0, w.nodes[target], w.nodes[target], w.nodes[target])))
    lo = rng.choice((1, 4, 18))
    dmg = (lo, lo + rng.choice((0, 4, 18)), rng.choice((100, 504, 100000)), rng.choice((8, 1, 0x40001)),
           rng.choice((0, 0x5000)))
    if key == 'canSeePoint':
        o = rng.choice(w.everything)
        p = tuple(mem.u32(o + 0x10 + 4 * i) for i in range(3))
        return (c, p, fa, arc, f32(near), f32(far))
    if key == 'canSeeObjEdge':
        mem.wf32(w.creatures[1] + 0x308, rng.uniform(-200, 200))
        mem.wf32(w.creatures[1] + 0x30C, rng.uniform(-200, 200))
        return (c, rng.choice(w.everything + [0]), fa, arc, rng.choice((0, 1, 2)), f32(near), f32(far),
                f32(rng.choice((0.0, 0.0, 0.5))))
    if key == 'canSeeTargetIn':
        return (c, fa, arc, rng.choice((0, 1)), f32(near), f32(far), f32(rng.choice((0.0, 0.0, 0.5))))
    if key == 'findPlayerInCone':
        mem.w32(c + 0x2E4, rng.choice((0, w.nodes[rng.choice(w.everything)])))
        return (c, fa, arc, f32(near), f32(far))
    if key == 'hitTargetAtReach':
        reach = rng.choice((0.0, 20.0, 40.0, 72.0))
        if rng.random() < 0.6:                          # put the target near the reach point
            th = mem.s16(c + 0x38) * 2 * math.pi / 65536
            cx, cy, cz = (struct.unpack('<f', struct.pack('<I', mem.u32(c + 0x10 + 4 * i)))[0] for i in range(3))
            mem.wf32(target + 0x10, cx + math.cos(th) * reach + rng.uniform(-70, 70))
            mem.wf32(target + 0x14, cy + math.sin(th) * reach + rng.uniform(-70, 70))
            mem.wf32(target + 0x18, cz + rng.uniform(-30, 30))
        return (c,) + dmg + (f32(reach),)
    if key in ('hitTargetInArcEdge', 'hitTargetOrPlayerInArc'):
        return (c, fa, arc) + dmg + (f32(near), f32(far))
    if key == 'knockbackTarget':
        return (c, f32(rng.choice((0.0, 100.0, 250.0, -5.0))))
    if key == 'setCooldown':
        return (c, rng.choice((0, 30, 90, 0x12345, -1 & 0xFFFFFFFF)))
    if key == 'setCooldownOn':
        return (c, rng.choice((0, 30, 90, 0x12345)), rng.choice(w.everything + [0, 0]))
    if key == 'notifyObjectsNear':
        o = rng.choice(w.everything)
        p = tuple(mem.u32(o + 0x10 + 4 * i) for i in range(3))
        return (rng.getrandbits(32), p, rng.getrandbits(32), f32(rng.choice((0.0, 60.0, 600.0))))
    raise KeyError(key)


def main(argv):
    _install()
    D.generate = generate
    return D.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
