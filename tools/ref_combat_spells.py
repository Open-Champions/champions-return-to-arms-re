#!/usr/bin/env python3
"""ref_combat_spells.py - spells in combat for Champions: Return to Arms (SLUS_209.73, US
v2.00): how a cast becomes an effect and the effect becomes damage on the victims of the
one shared world of tools/ref_combat_runtime.py.  docs/spec/combat-spells.md is the prose.

A research tool, not game code.  Standard library only; no game data is embedded.

What is new here and what is reused
    The skills themselves are modelled and executed already, one function at a time, by
    tools/ref_skills_a.py (ids 1-34), ref_skills_b.py (35-68) and ref_skills_c.py
    (69-101) with their difftests; the player's cast states by tools/ref_player.py; the
    damage function by tools/ref_combat.py; take-damage, pending damage, the burn tick of
    Creature_run and the owner's spell walk (slot 17) by tools/ref_creature.py.  In all
    of those the services a spell uses to FIND its victims were call-outs answered by a
    script.  This module adds them (section 1), executed against the original by
    tools/difftest_combat_spells.py:

        collect_in_arc        world_collectObjectsInArc 0x1614f0
        collect_in_sphere     world_collectInSphere 0x14ab80
        damage_in_radius      world_damageInRadius 0x161270

    and (section 2) composes the reused skill models with ref_combat_runtime.Runtime, so
    that a cast made in one actor's run creates its objects and spells in the shared pool,
    runs them in the shared run lists, finds victims through the shared grid and damages
    them through damage_apply into the victim's slot 2 - the path of round 1.

    and the five destructors of the effects composed here (HolyStrike, Sparks, Projectile,
    LightEffect, SpellWaveOfFlame: QueryModel.DTORS / effect_dtor).

Section 1 is a subclass of ref_combat_runtime.CombatModel (QueryModel); its methods use the
model's call-outs for the box query, the handle-list functions, damage_apply and the
destructor steps, so the difftest can compare every call.

Section 2: SpellRuntime, a subclass of ref_combat_runtime.Runtime.  Composed skills: 16
Holy Strike (ref_skills_a), 57 Shock of Fire (ref_skills_b), 95 Wave of Flame
(ref_skills_c).  AUTHORED: the Skill objects' statistics (give_skill), the cast point
(queue_cast: the end of the caster's run stands in for Player_run state 5), the player's
aim point for its spell walk.  OBSERVED, not executed: the object, spell and Skill table
words, LightEffect_ctor's simulation part and LightEffect_run's end test.  Refused: a
victim carrying a spell damage_apply asks about, a disease entry, a creature destroyed with
attached spells, any virtual slot without a body.  Nothing in ref_combat_runtime.py changes.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

M32 = 0xFFFFFFFF
s16, s32 = RC.s16, RC.s32
ZERO, HALF, ONE = 0, 0x3F000000, 0x3F800000
MINUS_ONE = 0xBF800000
F_100 = 0x42C80000
F_DEG_TO_ANGLE = 0x43360B60     # 182.04443: degrees to 16-bit angle units (0x161618)
F_THIRD = 0x3EAA7EF9            # 0.33299: the octagon distance's weight of the smaller axis

A_COLLECT_IN_ARC = 0x1614F0
A_COLLECT_IN_SPHERE = 0x14AB80
A_DAMAGE_IN_RADIUS = 0x161270


# =======================================================================================
# 1. The victim finders and the radius damage (Executed: tools/difftest_combat_spells.py)
# =======================================================================================

class QueryModel(T.CombatModel):
    """CombatModel plus the three world services spells use to find and hurt victims."""

    INTERNAL = dict(T.CombatModel.INTERNAL)
    INTERNAL.update({'world_collectObjectsInArc': 'collect_in_arc', 'world_collectInSphere': 'collect_in_sphere',
                     'world_damageInRadius': 'damage_in_radius'})
    MODELLED = dict(T.CombatModel.MODELLED)
    MODELLED.update({'world_collectObjectsInArc': A_COLLECT_IN_ARC, 'world_collectInSphere': A_COLLECT_IN_SPHERE,
                     'world_damageInRadius': A_DAMAGE_IN_RADIUS})

    @staticmethod
    def _dot2(origin, v, p):
        """vec2_dotDelta 0x166820 (origin, v, p) = v.x x (p.x - origin.x) + v.y x (p.y - origin.y)."""
        return C.add(C.mul(v[0], C.sub(p[0], origin[0])), C.mul(v[1], C.sub(p[1], origin[1])))

    def _box(self, centre, half, limit):
        low = tuple(C.sub(centre[i], half) for i in range(3))
        high = tuple(C.add(centre[i], half) for i in range(3))
        return self.call('world_collectObjectsInBox', low, high, limit) or ()

    def _list(self, head):
        out, node = [], self.u32(head)
        while node:
            out.append(self.u32(node + 0xC))
            node = self.u32(node)
        return out

    # ---- world_collectObjectsInArc 0x1614f0 ----------------------------------------------
    def collect_in_arc(self, pos, facing, out, filt, radius, arc, width):
        """world_collectObjectsInArc 0x1614f0 (position, facing, out list, filter object;
        radius, arc in degrees, width) -> the out list (also returned as objects in list
        order).

          * ONE box query of position -/+ radius on all three axes, capacity 0x200.  There is
            no distance test besides the box: `radius` is a half-size, the corners reach
            radius x sqrt(2) in the plane.
          * f = (cos16, sin16) of the facing.  With arc != -1.0 the half angle
            n = round-half-away(arc x 0.5 x 182.04443) and two edge normals at facing + n -
            0x4000 and facing - n + 0x4000 (16-bit).  With width != 0 a side normal at facing
            + 0x4000.
          * per object in box order: object flag 0x20 (creature) required, flags 0xd (not
            solid, 4, dead) refused; with a filter object, ITS slot 20 (is enemy) must
            accept; with an arc both edge products >= 0; with a width |side product| <=
            width; the forward product > 0 (strictly), all products 2-D from the position.
          * accepted objects go into the out list through handle_insertNode: behind the
            first node (front to back) whose object is not farther in the plane (<=), or at
            the front when every node is farther.  So the FIRST entry is the nearest (the
            earlier of equals), and every later one is inserted right behind it: the rest of
            the list is in reverse order of acceptance, not sorted.
          * the nodes have no partner (+8 = 0): destroying a listed object does not unlink
            them; callers clear the list (handle_clear) after use."""
        u32 = self.u32
        P = tuple(pos)
        found = self._box(P, radius, 0x200)
        f16 = s16(facing)
        fwd = (C.cos16(f16), C.sin16(f16))
        use_arc = not C.Fpu.compare(arc, MINUS_ONE) == 0
        if use_arc:
            h = C.mul(C.mul(arc, HALF), F_DEG_TO_ANGLE)
            h = C.add(h, HALF) if C.le(ZERO, h) else C.sub(h, HALF)
            n = s32(C.to_int(h))
            a, b = s16(f16 + n - 0x4000), s16(f16 - n + 0x4000)
            n1, n2 = (C.cos16(a), C.sin16(a)), (C.cos16(b), C.sin16(b))
        use_width = not C.Fpu.compare(width, ZERO) == 0
        if use_width:
            side = (C.cos16(f16 + 0x4000), C.sin16(f16 + 0x4000))
        for o in found:
            flags = u32(o + 0xC)
            if not flags & 0x20 or flags & 0xD:
                continue
            if filt and not self.vcall(filt, 20, o):
                continue
            p = self.vec(o + 0x10)
            if use_arc:
                if C.lt(self._dot2(P, n1, p), ZERO) or C.lt(self._dot2(P, n2, p), ZERO):
                    continue
            if use_width and C.lt(width, C.fabs(self._dot2(P, side, p))):
                continue
            if not C.lt(ZERO, self._dot2(P, fwd, p)):
                continue
            dx, dy = C.sub(P[0], p[0]), C.sub(P[1], p[1])
            d2 = C.add(C.mul(dx, dx), C.mul(dy, dy))
            node, after = u32(out), 0
            while node:
                q = u32(node + 0xC)
                qx, qy = C.sub(P[0], u32(q + 0x10)), C.sub(P[1], u32(q + 0x14))
                if C.le(C.add(C.mul(qx, qx), C.mul(qy, qy)), d2):
                    after = node
                    break
                node = u32(node)
            self.call('handle_insertNode', out, after, o)
        return self._list(out)

    # ---- world_collectInSphere 0x14ab80 --------------------------------------------------
    def collect_in_sphere(self, centre, heading, out, radius):
        """world_collectInSphere 0x14ab80 (centre, heading - not read, out list; radius) ->
        the out list.  ONE box query of centre -/+ radius, capacity 0x200; per object in box
        order: flags 0xd refused - NO class test, so projectiles, props and effects are
        listed too; kept when the 3-D distance from the centre (sqrt.s) is below radius +
        the object's radius (strict); handle_addNode links each at the FRONT, so the list is
        in reverse box order.  Nodes without partner, as above."""
        u32 = self.u32
        c = tuple(centre)
        for o in self._box(c, radius, 0x200):
            if u32(o + 0xC) & 0xD:
                continue
            p = self.vec(o + 0x10)
            dx, dy, dz = C.sub(c[0], p[0]), C.sub(c[1], p[1]), C.sub(c[2], p[2])
            d = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
            if C.lt(d, C.add(radius, u32(o + 0x1C))):
                self.call('handle_addNode', out, o)
        return self._list(out)

    # ---- world_damageInRadius 0x161270 ---------------------------------------------------
    def damage_in_radius(self, attacker, centre, most, flags, least, skip, inner, outer):
        """world_damageInRadius 0x161270 (attacker, centre, most, flags, least, skip flags;
        inner, outer).

          * ONE box query of centre -/+ outer on all three axes, capacity 0x80.
          * slope k = most / (outer - inner) when that span exceeds 1.0, else 100.0 (so
            `inner` only shapes the slope; nothing inside it is treated differently).
          * per object in box order: never the attacker itself; for a PLAYER attacker (flag
            0x40) the attacker's slot 20 must accept it - any other attacker, or none,
            damages everything; objects with any of the skip flags are left out (callers
            that pass 0 hit corpses and non-creatures too).
          * distance: an octagon estimate in the plane, (|dx| + |dy|) - min(|dx|, |dy|) x
            0.33299, minus the object's radius; height is not looked at.  Nothing at
            outer or beyond (outer <= d).
          * amount = (outer - d) x k, raised to `least`, capped at `most` (min.s), truncated
            to an integer; damage_apply(object, attacker, 100000, 0, 0, flags, no
            descriptor, 0; amount, amount) - at once, per object, in box order."""
        u32 = self.u32
        c = tuple(centre)
        most_f = C.from_int(s32(most))
        found = self._box(c, outer, 0x80)
        span = C.sub(outer, inner)
        k = C.div(most_f, span) if C.lt(ONE, span) else F_100
        is_player = bool(attacker and u32(attacker + 0xC) & 0x40)
        hit = []
        for o in found:
            if o == attacker:
                continue
            if is_player and not self.vcall(attacker, 20, o):
                continue
            if u32(o + 0xC) & skip:
                continue
            ax = C.fabs(C.sub(u32(o + 0x10), c[0]))
            ay = C.fabs(C.sub(u32(o + 0x14), c[1]))
            d = C.sub(C.sub(C.add(ax, ay), C.mul(C.fmin(ax, ay), F_THIRD)), u32(o + 0x1C))
            if C.le(outer, d):
                continue
            amount = C.mul(C.sub(outer, d), k)
            low = C.from_int(s32(least))
            if C.lt(amount, low):
                amount = low
            amount = C.fmin(amount, most_f)
            dmg = C.from_int(s32(C.to_int(amount)))
            self.call('damage_apply', o, attacker, 100000, 0, 0, flags & M32, 0, 0, dmg, dmg)
            hit.append(o)
        return hit

    # ---- the effect destructors (slot 1) -------------------------------------------------
    # Observed and executed (difftest_combat_spells.py): each stores its own table, clears
    # its own heads, stores the base table, clears the base's heads, then GameObject_dtor
    # (this, 0) - or for a spell nothing more - and pool_free(this) when bit 0 is set (a
    # tail jump).  Rows: function -> (table offset, [own table, steps...], [base table,
    # steps...], GameObject_dtor or not).  A step is a head offset or ('light', offset).
    DTORS = {
        0x3CF534: ('HolyStrike_dtor', 0x48, (0x51A078, 0x58, 0x54), (0x5120B8, 0x4C), True),
        0x3C5B90: ('Sparks_dtor', 0x48, (0x50E998, ('light', 0x64)), (0x5120B8, 0x4C), True),
        0x3C2940: ('Projectile_dtor', 0x48, (0x5120B8, 0x4C), None, True),
        0x3C6888: ('LightEffect_dtor', 0x48, (0x50E198, 0x88, ('light', 0x4C)), None, True),
        0x3D1BD8: ('SpellWaveOfFlame_dtor', 0x14, (0x51C330, 0x18), (0x515BA0, 4), False),
    }

    def effect_dtor(self, fn, this, flags):
        """One of DTORS on `this` with the destructor's argument `flags`."""
        _name, table_off, own, base, gameobject = self.DTORS[fn]
        for part in (own, base):
            if part is None:
                continue
            self.w32(this + table_off, part[0])
            for step in part[1:]:
                if isinstance(step, tuple):
                    self.call('light_dtor', this + step[1], 2)
                else:
                    self.call('handle_clear', this + step)
        if gameobject:
            self.call('GameObject_dtor', this, 0)
        if flags & 1:
            self.call('pool_free', this)

    def dtor_holystrike(self, this, flags):
        return self.effect_dtor(0x3CF534, this, flags)

    def dtor_sparks(self, this, flags):
        return self.effect_dtor(0x3C5B90, this, flags)

    def dtor_projectile(self, this, flags):
        return self.effect_dtor(0x3C2940, this, flags)

    def dtor_lighteffect(self, this, flags):
        return self.effect_dtor(0x3C6888, this, flags)

    def dtor_spell_waveofflame(self, this, flags):
        return self.effect_dtor(0x3D1BD8, this, flags)


# =======================================================================================
# 2. Spells in the shared world: the skill models of ref_skills_a/b/c composed with the
#    round-1 runtime (docs/spec/combat-spells.md sections 3-6)
# =======================================================================================

import ref_combat as RB                         # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import ref_skills_b as SB                       # noqa: E402
import ref_skills_c as SC                       # noqa: E402

G_SKILL_TABLE = SA.G_SKILL_TABLE

# Observed: the function words of the Skill tables of the three skills composed here (slots
# 0-15; `this` adjustments all 0).  Slot 5 (mana cost) is never called by this module.
SKILL_TABLES = {
    16: (0x51A108, (0x3CF4C0, 0x2ED20C, 0x2ECFCC, 0x3C8248, 0x2ED08C, 0x2ED1E4, 0x3C82B8, 0x3CF510,
                    0x3C82E4, 0x2ECF74, 0x3C85FC, 0x3C8690, 0x3C87F0, 0x3C8864, 0x3C88DC, 0x3C88E4)),
    57: (0x51A190, (0x3CF60C, 0x3C8218, 0x2ED4E4, 0x3C8248, 0x2ED6A4, 0x2ED80C, 0x3C82B8, 0x3CF65C,
                    0x3C82E4, 0x2ED3F8, 0x3C85FC, 0x3C8690, 0x3C87F0, 0x3C8864, 0x3C88DC, 0x3C88E4)),
    95: (0x51C2A8, (0x3D1C9C, 0x316B1C, 0x316B24, 0x3C8248, 0x316BDC, 0x316CDC, 0x3C82B8, 0x3D1CEC,
                    0x3C82E4, 0x316A90, 0x3C85FC, 0x3C8690, 0x3C87F0, 0x3C8864, 0x3C88DC, 0x3C88E4)),
}
SKILL_NAMES = {16: 'holystrike', 57: 'shockoffire', 95: 'waveofflame'}

# Observed: the object and spell tables these skills create (slot -> function).
VT_HOLYSTRIKE, VT_SPARKS, VT_LIGHTEFFECT, VT_SPELL_WAVEOFFLAME = 0x51A078, 0x50E998, 0x50E198, 0x51C330
_DEFAULTS = (0x3C7EB0, 0x3C7EB8, 0x3C7EC0, 0x3C7EC8, 0x3C7EF0, 0x3C7EF8, 0x3C7F20, 0x3C7F28)  # slots 7-14
OBJECT_TABLES = {                               # slots 0-16
    VT_HOLYSTRIKE: (0x3CF5BC, 0x3CF534, 0x3C7E88, 0x3C7E90, 0x2EBC50, 0x2ECD90, 0x2ECAE8) + _DEFAULTS
    + (0x11C7F8, 0x3C8120),
    VT_SPARKS: (0x3C5C18, 0x3C5B90, 0x3C7E88, 0x3C7E90, 0x28FA3C, 0x2902E4, 0x2900C8) + _DEFAULTS
    + (0x12C668, 0x3C8120),
    VT_LIGHTEFFECT: (0x3C6908, 0x3C6888, 0x3C7E88, 0x3C7E90, 0x1EE050, 0x3C7EA0, 0x3C7EA8) + _DEFAULTS
    + (0x12E690, 0x3C8120),
}
SPELL_TABLES = {VT_SPELL_WAVEOFFLAME: (0x3D1C4C, 0x3D1BD8, 0x317000, 0x3CB04C, 0x3CB054)}

OBJECT_DTORS = {fn: row for fn, row in QueryModel.DTORS.items() if row[4]}
SPELL_DTORS = {fn: row for fn, row in QueryModel.DTORS.items() if not row[4]}

# Observed: the GameObject defaults these tables keep - bare returns (value 0 where the
# delay slot clears v0), slots 11 and 12 only copy their vector argument to the stack
EMPTY_SLOTS = {0x3C7E88: 2, 0x3C7E90: 3, 0x3C7E98: 4, 0x3C7EA0: 5, 0x3C7EA8: 6, 0x3C7EB0: 7, 0x3C7EB8: 8,
               0x3C7EC0: 9, 0x3C7EC8: 10, 0x3C7EF0: 11, 0x3C7EF8: 12, 0x3C7F20: 13, 0x3C7F28: 14, 0x3C8120: 16}
A_LIGHTEFFECT_RUN = 0x1EE050
# getters of the spell classes damage_apply asks about (difftest_combat.TYPEINFO): a victim
# carrying one is outside this composition
DAMAGE_SPELL_GETTERS = {0x3CB1A0, 0x3D0A00, 0x3D19F0, 0x3D1D70, 0x3CDD40, 0x3CF3AC, 0x3CF3FC, 0x3D18A0,
                        0x3CF000, 0x3CE9BC, 0x3D0DA8}
SPELL_GETTER_NAMES = {0x3D1C4C: 'WaveOfFlame'}
F_60 = 0x42700000
STACK_HEAD = 0x00008000                         # AUTHORED: the word that stands for a caller's stack list


def rb_slots(desc):
    """Any of the descriptor forms the models hand damage_apply -> ref_combat's four effect
    slots (type, v1, v2, v3) as signed 16-bit values, or None for none."""
    if not desc:
        return None
    if not isinstance(desc, tuple):
        raise T.Unsupported('a damage descriptor in memory (an item record)')
    if desc[0] == 'elem':                                             # ref_creature (burn)
        entries = [(0x15, desc[1], desc[2], 0)]
    elif desc[0] != 'desc':
        raise T.Unsupported('descriptor form %r' % (desc[0],))
    elif len(desc) > 1 and isinstance(desc[1], str):                  # ref_skills_c: header first
        entries = [e for e in desc[2:] if len(e) == 4]
    elif len(desc) == 2:                                              # ref_skills_b
        entries = list(desc[1])
    else:                                                             # ref_skills_a
        entries = [e for e in desc[1:] if e is not None]
    slots = [tuple(s16(v) for v in e) for e in entries][:4]
    return slots + [(-1, 0, 0, 0)] * (4 - len(slots))


class SpellBlock:
    """A Spell record (a pool block that is not a GameObject): what its owner's +0x364 list
    and the iterator see.  Its back list +4 is a head of the image."""

    def __init__(self, rt, addr):
        self.addr, self._mem = addr, rt.mem
        self.head4 = rt.mem.head(addr + 4)

    @property
    def flags(self):
        return self._mem.u32(self.addr + 0xC)       # the owner word, tested by an iterator mask


class SpellLiveObj(T.LiveObj):
    """T.LiveObj whose attached spells may be present, as long as none is a class that
    damage_apply looks for."""

    @property
    def spells(self):
        out = []
        for spell in self._rt.attached(self.addr):
            getter = self._mem.u32(self._mem.u32(spell + 0x14) + 4)
            if getter in DAMAGE_SPELL_GETTERS:
                raise T.Unsupported('a victim carrying a spell damage_apply asks about (0x%x)' % getter)
            out.append(RB.Spell(kind=SPELL_GETTER_NAMES.get(getter, 'other')))
        return out

    @spells.setter
    def spells(self, value):
        raise T.Unsupported('damage_apply would attach a spell (disease): outside the domain')


def _composed(module):
    """QueryModel + the skill module's Model on the one image, with the services as callbacks."""
    bodies = set(getattr(module, 'OBJECT_BODIES', {}))

    class Composed(module.Model, QueryModel):
        MODULE = module

        def __init__(self, rt):
            module.Model.__init__(self, rt.mem, rt.services)
            self.vcalls = []
            self.rt = rt
            self.hidden_draws = 0

        def call(self, name, *args):
            if name in T.CombatModel.INTERNAL and name not in self.external:
                return getattr(self, T.CombatModel.INTERNAL[name])(*args)
            return module.Model.call(self, name, *args)         # the victim finders: the runtime's

        def vcall(self, obj, slot, *args):
            fn = self.u32(self.u32(obj + 0x48) + 8 * slot + 4)
            if fn in bodies:
                return module.Model.vcall(self, obj, slot, *args)
            return QueryModel.vcall(self, obj, slot, *args)

        # GameObject_ctor on the shared world (ref_objects, executed) instead of the module's
        # own copy, so that the object is one of the world's
        def gameobject_ctor(self, obj, pos, class_def, props):
            self.rt.construct_object(obj, pos, class_def, props)

        def game_object_ctor(self, obj, pos, class_def, props):
            self.rt.construct_object(obj, self.vec(pos) if isinstance(pos, int) else pos, class_def, props)

        # the handle functions some modules write into node memory themselves: the pool's
        def handle_link(self, head, back, obj):
            return self.rt.svc_handle_link(head, back, obj)

        def handle_clear(self, head):
            return self.rt.svc_handle_clear(head)

        def handle_remove(self, node):
            return self.rt.svc_handle_removeNode(node)

        def handle_removeNode(self, node):
            return self.rt.svc_handle_removeNode(node)

    Composed.__name__ = 'Spells_' + module.__name__.split('_')[-1]
    return Composed


SpellsA, SpellsB, SpellsC = _composed(SA), _composed(SB), _composed(SC)


class SpellServices(T.Services):
    """Virtual call-outs reach the round-1 model, a skill model, an observed destructor or
    an empty body - nothing else."""

    def _virtual(self, slot):
        def fn(this, *args):
            return self.rt.dispatch_virtual(this, slot, *args)
        return fn

    def get(self, name):
        if name.startswith('Spell.v'):
            slot = int(name.split('.v')[1])
            return lambda this, *args: self.rt.spell_virtual(this, slot, *args)
        if name.startswith('Skill.v'):
            slot = int(name.split('.v')[1])
            return lambda this, *args: self.rt.skill_virtual(this, slot, *args)
        return T.Services.get(self, name)


class SpellRuntime(T.Runtime):
    """ref_combat_runtime.Runtime with spells: Skill objects (authored statistics, observed
    tables), the skill models of ref_skills_a/b/c for Holy Strike (16), Shock of Fire (57)
    and Wave of Flame (95), their objects and spells in the shared pool, run lists, grid
    and handle pool, and the victim finders of section 1.  See docs/spec/combat-spells.md.

        rt = SpellRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((120.0, 0.0, 0.0))
        rt.give_skill(95, stats={0: (1, 5, 1.0), 1: (1, 20, 0.0)})
        rt.queue_cast(p, 95, level=3)      # made at the end of p's next run (AUTHORED point)
        rt.tick()
    """

    def __init__(self, terrain=None, anim=None, skill_stat=None, camera_mode=1, lights=True):
        T.Runtime.__init__(self, terrain, anim, skill_stat, camera_mode)
        self.services = SpellServices(self)
        self.model.cb = self.services
        self.qmodel = QueryModel(self.mem, self.services)
        self.models = {SA: SpellsA(self), SB: SpellsB(self), SC: SpellsC(self)}
        self.blocks = {}                        # spell blocks: address -> SpellBlock
        self.iterators = []
        self.lights = lights
        self.queued = {}                        # caster -> [(skill id, level, point, facing)]
        self.mem.register_head(STACK_HEAD, C.Cell(STACK_HEAD))
        for table, words in list(OBJECT_TABLES.items()) + list(SPELL_TABLES.items()):
            for slot, fn in enumerate(words):
                self.mem.poke(table + 8 * slot, 2, 0)
                self.mem.poke(table + 8 * slot + 4, 4, fn)
        self.skill_objects = {}

    # ---- set-up (AUTHORED) -------------------------------------------------------------
    def give_skill(self, skill_id, stats=None, kind=0, recast=0, flags=0):
        """A Skill object for `skill_id` with AUTHORED statistics: stats = {index: (first
        level, base, step)} for tier 1 (tier 2 off: first levels -1).  The table words are
        the executable's (SKILL_TABLES, Observed); no statistic of the game is embedded."""
        table, words = SKILL_TABLES[skill_id]
        for slot, fn in enumerate(words):
            self.mem.poke(table + 8 * slot, 2, 0)
            self.mem.poke(table + 8 * slot + 4, 4, fn)
        skill = self._alloc_fixture(0x68)
        poke = self.mem.poke
        poke(skill + 4, 4, flags)
        poke(skill + 8, 4, kind)
        poke(skill + 0xC, 2, recast)
        for i in range(5):
            first, base, step = (stats or {}).get(i, (1, 1, 0.0))
            poke(skill + 0xE + 2 * i, 2, first & 0xFFFF)
            poke(skill + 0x18 + 2 * i, 2, base & 0xFFFF)
            poke(skill + 0x24 + 4 * i, 4, C.f32(step))
            poke(skill + 0x38 + 2 * i, 2, 0xFFFF)
        poke(skill + 0x60, 4, table)
        poke(skill + 0x64, 4, skill_id)
        poke(G_SKILL_TABLE + 4 * skill_id, 4, skill)
        self.skill_objects[skill_id] = skill
        return skill

    def module_of(self, fn):
        for module in (SA, SB, SC):
            if fn in getattr(module, 'OBJECT_BODIES', {}) or fn in module.SPELL_BODIES or fn in module.SKILL_BODIES:
                return module
        return None

    def model_for(self, fn):
        module = self.module_of(fn)
        return self.models[module] if module is not None else None

    # ---- the cast (AUTHORED driver around executed pieces) -------------------------------
    def queue_cast(self, caster, skill_id, level=1, point=None, facing=None):
        """Make the cast at the end of the caster's next run - where Player_run state 5
        phase 1 calls Player_castSkill (0x1ab4f8; the cast point is cast-track weight 1.0
        offline, docs/spec/player-tick.md state 5).  AUTHORED: the player's state 5 itself
        is not composed here."""
        self.queued.setdefault(caster, []).append((skill_id, level, point, facing))

    def cast(self, caster, skill_id, level=1, point=None, facing=None):
        """The part of Player_castSkill 0x1a42b8 (ref_player.Tick.cast_skill, executed) that
        makes the effect: spell = Skill slot 2 (rank, caster, point, facing); a spell that
        comes back is attached with creature_addSpell (and, for a skill of kind 1, the
        handle +0x588).  AUTHORED around it: no canUse, no aim search, no mana, no recast;
        the point is the caster's position unless given."""
        skill = self.skill_objects[skill_id]
        pos = tuple(point) if point is not None else self.qmodel.vec(caster + 0x10)
        facing = self.qmodel.s16(caster + 0x38) if facing is None else facing
        self.note('cast', caster, skill_id, level)
        spell = self.skill_virtual(skill, 2, level, caster, pos, facing)
        if spell:
            self.svc_creature_addSpell(caster, spell)
            if s32(self.u32(skill + 8)) == 1:
                self.svc_handle_link(caster + 0x588, spell + 4, spell)
        return spell

    def skill_virtual(self, skill, slot, *args):
        fn = self.u32(self.u32(skill + 0x60) + 8 * slot + 4)
        model = self.model_for(fn)
        if model is None:
            raise T.Unsupported('Skill slot %d reaches 0x%x, which has no model' % (slot, fn))
        if model.MODULE is SB and slot == 2:
            pos = model.alloca(0x10)
            for i in range(3):
                self.mem.poke(pos + 4 * i, 4, args[2][i])
            args = args[:2] + (pos,) + args[3:]
        return model.skill_call(skill, slot, *args)

    # ---- spells: blocks, attachment, the owner's walk, destruction ----------------------
    def attached(self, creature):
        cell = self.mem.heads.get(creature + 0x364)
        return [o.addr for o in C.HandlePool.items(cell)] if cell is not None else []

    def spell_block(self, addr):
        block = self.blocks.get(addr)
        if block is None:
            if addr in self.world.objects:
                raise T.CompositionError('0x%x is an object, not a spell' % addr)
            block = self.blocks[addr] = SpellBlock(self, addr)
        return block

    def spell_virtual(self, spell, slot, *args):
        table = self.u32(spell + 0x14)
        fn = self.u32(table + 8 * slot + 4)
        if slot == 1 and fn in SPELL_DTORS:
            return self.spell_dtor(spell, args[0], fn)
        model = self.model_for(fn)
        if model is None:
            raise T.Unsupported('Spell slot %d reaches 0x%x, which has no model' % (slot, fn))
        if model.MODULE is SB:
            if slot == 2:
                pos = model.alloca(0x10)
                for i in range(3):
                    self.mem.poke(pos + 4 * i, 4, args[0][i])
                args = (pos,) + args[1:]
            return model.spell_call(spell, slot, *args)
        return model.table_call('Spell', spell, 0x14, slot, *args)

    def spell_dtor(self, spell, flags, fn):
        """An executed spell destructor (QueryModel.DTORS) on the shared world."""
        self.note('destroy_spell', spell, SPELL_DTORS[fn][0])
        self.qmodel.effect_dtor(fn, spell, flags)

    def svc_creature_addSpell(self, creature, spell):
        """creature_addSpell 0x11a838 (executed in difftest_skills_a): with a spell,
        handle_link(creature + 0x364, spell + 4, spell) - the newest first."""
        if spell:
            self.svc_handle_link(creature + 0x364, spell + 4, spell)

    def svc_creature_findSpellByType(self, c, type_info):
        """creature_findSpellByType 0x11a710 (executed in difftest_skills_a): the spells of
        this composition are never of a class anyone asks for; any other is refused."""
        for spell in self.attached(c):
            getter = self.u32(self.u32(spell + 0x14) + 4)
            if getter not in SPELL_GETTER_NAMES:
                raise T.Unsupported('creature_findSpellByType over an unknown spell class 0x%x' % getter)
        return 0

    def svc_iter_begin(self, head, mask):
        it = C.Iterator(self.mem.head(head), mask)
        self.iterators.append(it)
        return self.mem.node_addr(it.prev) if not it.done else 0

    def svc_iter_next(self):
        it = self.iterators[-1]
        it.advance()
        return self.mem.node_addr(it.prev) if not it.done else 0

    def svc_iter_end(self, flags):
        self.iterators.pop().end()

    # ---- objects --------------------------------------------------------------------------
    def svc_pool_new(self, size):
        addr = self.world.pool.new(size)
        self.note('pool_new', size, addr)
        if addr:
            block = self.world._block_size(addr)
            self.mem.zero(addr, addr + block)
            self.mem.forget_heads(addr, addr + block)
        return addr

    def construct_object(self, addr, pos, class_def, props):
        """GameObject_ctor 0x14cb10 through ref_objects (executed): heads, grid link, ONE
        SHARED DRAW; the bytes ref_objects does not keep are written as the original does."""
        if class_def or props:
            raise T.Unsupported('an effect object with a class definition or properties')
        obj = self.world.construct(addr, [p & M32 for p in pos])
        self.kinds[addr] = 'effect'
        for off, size, value in ((0x24, 4, 0), (0x28, 1, 0x19), (0x29, 1, 0x49), (0x2C, 4, 0), (0x34, 4, 0)):
            self.mem.poke(addr + off, size, value)
        return obj

    def svc_GameObject_ctor(self, obj, pos, class_def, props):
        self.construct_object(obj, pos, class_def, props)

    def svc_LightEffect_ctor(self, block, pos, follow, flag, *floats):
        """LightEffect_ctor 0x201bd8, the parts that are simulation (Observed): GameObject_ctor
        (ONE SHARED DRAW, grid link), table 0x50e198, flags |= 3 (not solid, so the victim
        finders and contact loops skip it), a follow handle +0x88 when `follow` is given,
        end frame +0xb4 = frame + max(trunc(life x 60), 1) with life the fourth stack
        float, the every-frame run list.  Colours, radii and the light record are
        presentation and are not kept."""
        if not self.lights:
            raise T.Unsupported('a LightEffect (lights=False)')
        self.construct_object(block, pos, 0, 0)
        mem = self.mem
        mem.poke(block + 0x48, 4, VT_LIGHTEFFECT)
        mem.poke(block + 0xC, 4, mem.u32(block + 0xC) | 3)
        if follow:
            self.svc_handle_link(block + 0x88, follow, follow)
        life = floats[11] if len(floats) >= 12 else ONE
        frames = s32(C.to_int(C.mul(life, F_60)))
        mem.poke(block + 0xB4, 4, (self.u32(G_SIM_FRAME_ADDR) + (frames if frames > 0 else 1)) & M32)
        self.world.run_every_frame(self.world.obj(block))
        self.note('light', block)

    def light_effect_run(self, obj):
        """LightEffect_run 0x1ee050 (Observed): colour and radius steps (presentation), the
        light follows its handle, and at frame >= +0xb4 its own slot 1 with 3 - destroyed
        at once.  No draw."""
        if not s32(self.u32(G_SIM_FRAME_ADDR)) < s32(self.u32(obj + 0xB4)):
            self.dispatch_virtual(obj, 1, 3)

    def object_dtor(self, obj, flags, fn):
        """An executed object destructor (QueryModel.DTORS) on the shared world."""
        self.note('destroy', obj, OBJECT_DTORS[fn][0])
        self.qmodel.effect_dtor(fn, obj, flags)

    def svc_GameObject_dtor(self, obj, flags):
        """GameObject_dtor 0x14cf90 (ref_objects, executed): +8, +4, +0 cleared."""
        self.world.destroy(self.world.obj(obj), flags)

    def svc_pool_free(self, addr):
        """pool_free 0x150470 of an effect or a spell block: the block goes back to its size
        class (last in, first out) and its handle words are dead memory."""
        block = self.world._block_size(addr)
        obj = self.world.objects.pop(addr, None)
        if obj is not None:
            obj.alive = False
            self.kinds.pop(addr, None)
        self.blocks.pop(addr, None)
        self.world.pool.free(addr)
        self.mem.forget_heads(addr, addr + block)

    def svc_light_dtor(self, light, flags):
        self.note('presentation', 'light_dtor')

    def dispatch_virtual(self, this, slot, *args):
        """A virtual call-out of any model: the round-1 model when it has the body, a skill
        model, an observed destructor, an empty body; otherwise refused."""
        fn = self.u32(self.u32(this + 0x48) + 8 * slot + 4)
        if self.model.knows(fn):
            return self.model.vcall(this, slot, *args)
        if slot == 1 and fn in OBJECT_DTORS:
            return self.object_dtor(this, args[0], fn)
        if fn in EMPTY_SLOTS:
            return 0
        model = self.model_for(fn)
        if model is not None:
            return model.vcall(this, slot, *args)
        raise T.Unsupported('virtual slot %d of 0x%x reaches 0x%x, which has no model' % (slot, this, fn))

    def _slot4(self, obj):
        fn = self._fn(obj.addr, 4)
        if fn == A_LIGHTEFFECT_RUN:
            self.note('run', obj.addr, 'light')
            return self.light_effect_run(obj.addr)
        model = self.model_for(fn)
        if model is not None:
            self.note('run', obj.addr, model.MODULE.__name__)
            return model.vcall(obj.addr, 4)
        T.Runtime._slot4(self, obj)
        for skill_id, level, point, facing in self.queued.pop(obj.addr, ()):
            if obj.addr in self.world.objects:
                self.cast(obj.addr, skill_id, level, point, facing)
        if self.kinds.get(obj.addr) == 'player' and s32(self.u32(obj.addr + 0x58C)) != 4:
            self.player_spell_walk(obj.addr)

    def player_spell_walk(self, P):
        """A player's attached spells run in the TAIL of its own run: Player_updateCast
        0x1a3f70 calls slot 17 (Creature_updateSpells) with the hand midpoint
        (ref_player.Tick.update_cast, executed; Creature_run walks them only for
        non-players, 0x112984).  AUTHORED here: the point is the position raised by 58 (no
        body model), and the rest of Player_updateCast is not composed."""
        x, y, z = self.qmodel.vec(P + 0x10)
        self.note('player_spells', P)
        self.model.vcall(P, 17, (x, y, C.add(z, 0x42680000)))

    def live(self, addr):
        self.world.obj(addr)
        return SpellLiveObj(self, addr, 'Player' if self.kinds.get(addr) == 'player' else 'Creature')

    # ---- handles: spell blocks and the caller's stack list ------------------------------
    def _target(self, obj):
        if obj in self.world.objects:
            return self.world.objects[obj]
        if obj in self.blocks or (obj and self.world.pool.class_of(obj) is not None):
            return self.spell_block(obj)
        raise T.CompositionError('0x%x is not a live object or spell' % obj)

    def _head(self, head):
        return self.mem.head(STACK_HEAD if head == 'stack' or head == 0 else head)

    def svc_handle_link(self, head, back, obj):
        target = self._target(obj)
        back_cell = self.mem.heads.get(back)
        if back_cell is None:
            raise T.CompositionError('handle_link back list 0x%x is not a head' % back)
        node = self.world.handles.link(self._head(head), back_cell, target)
        return self.mem.node_addr(node)

    def svc_handle_clear(self, head):
        self.world.handles.clear(self._head(head))

    def svc_handle_insertNode(self, head, after, obj):
        node = self._node(after) if after else None
        return self.mem.node_addr(self.world.handles.insert(self._head(head), node, self._target(obj)))

    def svc_handle_addNode(self, head, obj):
        return self.mem.node_addr(self.world.handles.add(self._head(head), self._target(obj)))

    def _node(self, addr):
        index, rest = divmod(addr - T.SharedMemory.NODE_BASE, T.SharedMemory.NODE_SIZE)
        if rest or not 0 <= index < len(self.world.handles.nodes):
            raise T.CompositionError('0x%x is not a node' % addr)
        return self.world.handles.nodes[index]

    # ---- the victim finders and the damage function -------------------------------------
    def svc_world_collectObjectsInArc(self, pos, facing, out, filt, radius, arc, width):
        out = STACK_HEAD if out in ('stack', 0) else out
        found = self.qmodel.collect_in_arc(pos, facing, out, filt, radius, arc, width)
        self.note('arc', tuple(found))
        return found

    def svc_world_collectInSphere(self, centre, heading, *rest):
        """Both call forms: (centre, heading, out; radius) and the models' (centre, heading;
        radius) with the caller's stack list."""
        out, radius = (rest[0], rest[1]) if len(rest) == 2 else (STACK_HEAD, rest[0])
        out = STACK_HEAD if out in ('stack', 0) else out
        found = self.qmodel.collect_in_sphere(centre, heading, out, radius)
        self.note('sphere', tuple(found))
        return found

    def svc_world_damageInRadius(self, attacker, centre, most, flags, least, skip, inner, outer):
        return self.qmodel.damage_in_radius(attacker, centre, most, flags, least, skip, inner, outer)

    def svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit, dmin, dmax):
        """damage_apply 0x1e8230 (ref_combat, executed) with the descriptors the skills build."""
        slots = rb_slots(desc)
        self._sync_rb()
        before = len(self.rb.seed.draws)
        self.note('damage_apply', victim, attacker, s32(attack), flags & M32)
        result = RB.damage_apply(self.rb, self.live(victim), self.live(attacker) if attacker else None,
                                 dmin, dmax, attack, flags, slots, no_crit)
        self.note('damage_result', victim, result, tuple(self.rb.seed.draws[before:]))
        return result

    def _rb_pool(self, size):
        raise T.Unsupported('damage_apply asks for a pool block of 0x%x (an effect object)' % size)

    # ---- small services the skill models reach ------------------------------------------
    def svc_terrain_height(self, world, pos, radius):
        return self.terrain.height_below(pos, radius)

    def svc_obj_getPropInt(self, obj, key, default):
        return 0 if obj not in self.kinds or self.kinds[obj] == 'effect' else T.Runtime.svc_obj_getPropInt(
            self, obj, key, default)

    def svc_libc_sprintf(self, fmt, *args):
        return 0

    def svc_trail_create(self, *args):
        self.note('presentation', 'trail_create')
        return 0

    def svc_Creature_v1(self, this, flags):
        return self.dispatch_virtual(this, 1, flags)


G_SIM_FRAME_ADDR = T.G_SIM_FRAME
for _name in ('trail_addPoint', 'light_link', 'light_relink', 'voice_setPosition', 'fx_ringBurst',
              'sound_playAtPos', 'water_disturb'):
    if _name not in T.Services.PRESENTATION:
        T.Services.PRESENTATION = T.Services.PRESENTATION + (_name,)
