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
BaseWorld, BaseRig = D.World, D.Rig

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
    'gameObjectDtor': (0x14CF90, 'ii', 0, 'n', 'gameobject_dtor', (0x14CF90, 0x14D238)),
    'creatureDtor': (0x117128, 'ii', 0, 'n', 'creature_dtor', (0x117128, 0x11722C)),
    'skelightDtor': (0x3CC67C, 'ii', 0, 'n', 'skelight_dtor', (0x3CC67C, 0x3CC6DC)),
    'playerDtor': (0x1A1BB8, 'ii', 0, 'n', 'player_dtor', (0x1A1BB8, 0x1A1D24)),
    'deadUpdate': (0x1108A0, 'iivi', 1, 'n', 'dead_update', (0x1108A0, 0x110B58)),
    'dropLoot': (0x10F2C8, 'ivii', 6, 'n', 'drop_loot', (0x10F2C8, 0x110760)),
    'goblinDeath': (0x26CCFC, 'ii', 0, 'n', 'goblin_set_state', (0x26CCFC, 0x26D690)),
}
# creature-base pieces that run for real inside the entry points (Creature_filterState and
# the three timer tests it calls; executed models in tools/ref_creature.py, ref_arena_monsters.py)
REAL_EXTRA = {0x10A9C0, 0x1195E0, 0x119608, 0x1195F0}

EXTS = {
    'Creature.v12': Ext(0, 'pivi', 1, 'n'),
    'Creature.v27': Ext(0, 'pi', 0, 'n'),
    'Spell.v1': Ext(0, 'pi', 0, 'n'),
    'objNames_remove': Ext(0x14BE58, 'pp', 0, 'n'),
    'pool_free': Ext(0x150470, 'p', 0, 'n'),
    'AnimState_dtor': Ext(0x171098, 'pi', 0, 'n'),
    'light_dtor': Ext(0x14A490, 'pi', 0, 'n'),
    'sub_202500': Ext(0x202500, 'pi', 0, 'n'),
    'loot_generateDrops': Ext(0x100D54, 'viii', 6, 'n'),
    'rtti_typeInfoEquals': Ext(0x3B1250, 'pp', 0, 'i'),
    'Creature.v0': Ext(0, '', 0, 'i'),
    'Creature.v28': Ext(0, 'pi', 0, 'n'),
    'Holder.v11': Ext(0, 'pipii', 0, 'n'),
}
EXTS.update({name: Ext(addr, '', 0, 'i') for name, addr in M.TYPEINFO_GETTERS.items()})
TI_TOKENS = {name: 0x00E00000 + 0x100 * i for i, name in enumerate(sorted(M.TYPEINFO_GETTERS))}

# property strings for GameObject_dtor's 'name=' scan (authored; not game text)
PROP_TEXTS = (b'name=alpha', b'name=beta', b'Name=gamma', b'namex=1', b'nam', b'name', b'name=', b'nameX',
              b'other=2', b'name==', b'')


class World(BaseWorld):
    def __init__(self, emu, rng):
        BaseWorld.__init__(self, emu, rng)
        mem = self.mem
        self.spell_table = emu.alloc(0x40)
        mem.w16(self.spell_table + 8, 0)
        mem.w32(self.spell_table + 0xC, self.stub_for('Spell.v1'))
        self.spells = [emu.alloc(0x40) for _ in range(3)]
        for sp in self.spells:
            mem.w32(sp + 0x14, self.spell_table)
        self.spell_nodes = [emu.alloc(0x20) for _ in range(3)]
        self.texts = []
        for t in PROP_TEXTS:
            a = emu.alloc(0x20)
            mem.write(a, t + b'\0')
            self.texts.append(a)
        self.props = emu.alloc(0x40)
        self.goblin = emu.alloc(0x500)
        self.holder = emu.alloc(0x20)
        self.holder_table = emu.alloc(8 * 32)
        for slot in range(32):
            mem.w32(self.holder_table + 8 * slot + 4, self.stub_for('Holder.v%d' % slot))
        mem.w32(self.holder, self.holder_table)
        self.loot_class = 0

    def on_iter_begin(self, args, view, rng):
        count = rng.choice((0, 0, 1, 2, 3))
        view.iter_nodes = []
        for node, spell in list(zip(self.spell_nodes, self.spells))[:count]:
            view.poke(node + 0xC, 4, rng.choice((spell, spell, 0)))
            view.iter_nodes.append(node)
        return self.on_iter_next(args, view, rng)

    def on_Creature_v0(self, args, view, rng):
        return Res(self.loot_class)

    def on_rtti_typeInfoEquals(self, args, view, rng):
        return Res(1 if args[0] == args[1] else 0)

    def on_obj_getPropInt(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 0, 1)))

    def respond(self, name, args, view, rng):
        if name in TI_TOKENS:
            return Res(TI_TOKENS[name])
        return BaseWorld.respond(self, name, args, view, rng)

    def on_iter_next(self, args, view, rng):
        nodes = getattr(view, 'iter_nodes', [])
        return Res(nodes.pop(0) if nodes else 0)


class Rig(BaseRig):
    def make_stub(self, name, ext):
        inner = BaseRig.make_stub(self, name, ext)
        if name not in ('iter_begin', 'iter_next'):
            return inner

        def stub(emu):
            it = emu.r[4] & D.M32
            ret = inner(emu)
            emu.mem.w32(it + 4, ret & D.M32)
            return ret
        return stub


def _install():
    """Point the round-1 harness at this module's entries and model (module globals)."""
    shim = types.ModuleType('ref_combat_runtime_shim')
    shim.__dict__.update(T.__dict__)
    shim.CombatModel = M.MonsterCombatModel
    D.T = shim
    D.ENTRIES = ENTRIES
    D.EXTS.update(EXTS)
    D.REAL_OTHER = set(D.REAL_OTHER) | REAL_EXTRA

    def on_creature_bossRank(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, 1, 2)))
    BaseWorld.on_creature_bossRank = on_creature_bossRank
    D.World = World
    D.Rig = Rig


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
    if key in ('gameObjectDtor', 'creatureDtor', 'skelightDtor', 'playerDtor'):
        o = rng.choice(w.players) if key == 'playerDtor' else c
        props = 0
        if rng.random() < 0.8:
            props = w.props
            picks = [rng.choice(w.texts) for _ in range(rng.randrange(0, 7))]
            for i, t in enumerate(picks):
                mem.w32(props + 4 * i, t)
            mem.w32(props + 4 * len(picks), 0)
        mem.w32(o + 0x2C, props)
        mem.w8(M.G_IN_GHOST_OP, rng.choice((0, 0, 0, 1)))
        mem.w8(o + 0x462, rng.choice((0, 0, 0, 1)))
        return (o, rng.choice((0, 1, 2, 3)))
    if key == 'deadUpdate':
        mem.w64(c + 0xA8, rng.choice((0, 0x1000000, 0x1000, 0x2000, 0x4000, 0x40000, 0x3000, 0x44000,
                                      0x1001000)))
        mem.w16(c + 0x11A, rng.choice((0, 0x80, 0x88)))
        mem.w8(c + 0x118, rng.choice((1, 2)))
        mem.wf32(c + 0x2F4, rng.choice((0.0, 10.0, 71.9)))
        mem.w32(c + 0xC, rng.choice((0x29, 0x2B, 0x29)))
        off = tuple(f32(rng.choice((0.0, 0.0, 3.5, -12.0))) for _ in range(3))
        return (c, rng.choice((0, 0x80, 1, 0x81)), off, rng.choice((0, 0, 1)),
                f32(rng.choice((20.0, 0.0, 44.0, -1.0))))
    if key == 'dropLoot':
        w.loot_class = rng.choice(list(TI_TOKENS.values()) + [0x00E0F000] * 6)
        mem.w64(c + 0xA8, rng.choice((0, 0, 0, 1, 0x100000000, 0x100000001)))
        mem.w8(c + 0xA0, rng.choice((0, 0, 3, 0xFF)))
        mem.w32(c + 0x3D8, rng.choice((0, 0x1234)))
        mem.w32(T.G_PVP_MODE_B, rng.choice((0, 0, 1)))
        mem.w32(T.G_NUM_PLAYERS, rng.choice((0, 1, 2, 3, 4)))
        p = tuple(mem.u32(c + 0x10 + 4 * i) for i in range(3))
        floats = tuple(f32(v) for v in (36.0, rng.choice((2.0, 3.0)), rng.choice((1.6, 2.8, 0.0)),
                                       rng.choice((0.6, 3.0)), rng.choice((1.4, 3.0, -1.0)), rng.choice((0.25, 1.0))))
        return (c, p, rng.choice((0, 0x1234, 0xFFFF8000)), rng.choice((0, 0, 1, 7))) + floats
    if key == 'goblinDeath':
        g = w.goblin
        for off in range(0, 0x500, 4):
            mem.w32(g + off, mem.u32(c + off) if off < 0x400 else 0)
        mem.w32(g + 0x50, rng.choice((w.holder, w.holder, 0)))
        mem.w8(g + 0x490, rng.choice((0, 1)))
        mem.w32(g + 0x3D4, rng.choice((0, 1, 4, 4, 5)))
        mem.w32(g + 0x2DC, rng.choice((0, 0x40000, 8)))
        mem.w32(g + 0xC, rng.choice((0x29, 0x2B, 0x28, 0x20)))
        mem.w64(g + 0xA8, rng.choice((0, 0x200, 0x100000000, 1, 0x40000)))
        for off in (0x314, 0x318, 0x31A, 0x31C):
            mem.w16(g + off, rng.choice((0, 0, 30)))
        mem.w8(g + 0x231, rng.choice((0, 0, 1)))
        mem.w32(0x503890, rng.choice((0, 0, 1)))
        mem.w32(0x503894, 0)
        mem.w32(T.G_PVP_MODE_B, rng.choice((0, 0, 0, 1)))
        mem.w32(T.G_PVP_MODE_A, 0)
        w.loot_class = rng.choice(list(TI_TOKENS.values()) + [0x00E0F000] * 12)
        return (g, rng.choice((0x14,) * 6 + (0x18, 0x20)))
    raise KeyError(key)


def main(argv):
    _install()
    D.generate = generate
    return D.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
