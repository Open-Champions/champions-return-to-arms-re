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

Section 1 is a subclass of ref_combat_runtime.CombatModel (QueryModel); its methods use the
model's call-outs for the box query, the handle-list insertion and damage_apply, so the
difftest can compare every call.  Nothing in ref_combat_runtime.py changes.
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
