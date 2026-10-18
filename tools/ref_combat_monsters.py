#!/usr/bin/env python3
"""ref_combat_monsters.py - combat research round 2, targets 5 and 6: the creature hit and
cooldown helpers round 1 left Observed, creature_findPlayerInCone, the destructor chain,
and death and loot (Creature_dropLoot, the blood-decal path of Creature_deadUpdate) of
Champions: Return to Arms (SLUS_209.73, US v2.00).

A research tool, not game code.  Standard library only; no game data is embedded.
docs/spec/combat-monster-death.md is the prose version.  It ADDS to
tools/ref_combat_runtime.py (round 1) and changes none of its APIs: MonsterCombatModel is
a subclass of ref_combat_runtime.CombatModel; every round-1 method keeps its behaviour.

Executed - tools/difftest_combat_monsters.py runs the original under tools/ee_emu.py and
compares calls, stored bytes, the shared seed and the result (see the doc for figures):

    can_see_point                 creature_canSeePoint 0x10c238
    can_see_obj_edge              creature_canSeeObjEdge 0x10c5b8
    find_player_in_cone           creature_findPlayerInCone 0x10ca70
    hit_target_at_reach           Creature_hitTargetAtReach 0x1196e8
    hit_target_in_arc_edge        Creature_hitTargetInArcEdge 0x119850
    hit_target_or_player_in_arc   Creature_hitTargetOrPlayerInArc 0x119a20
    knockback_target              Creature_knockbackTarget 0x119d10
    set_cooldown                  Creature_setAttackCooldown 0x118bf0 (name proposed)
    set_cooldown_on               Creature_setAttackCooldownOn 0x118b58 (name proposed)
    notify_objects_near           world_notifyObjectsNear 0x11a2b8
    (can_see_target_in            Creature_canSeeTargetIn 0x118d40, ref_arena_monsters)

The calling convention of every method: integer arguments first in register order, then
the float arguments in f12, f13, f14 order, as round 1's methods do.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat as RB                         # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
from ref_combat_runtime import Unsupported, CompositionError    # noqa: E402,F401

M32 = T.M32
s8, s16, s32 = T.s8, T.s16, T.s32
ZERO, HALF, ONE = T.ZERO, T.HALF, T.ONE
F_60 = 0x42700000
F_RAY = 0x3F8CCCCC                              # the length factor of every sight ray (1.0999999)
G_WORLD = T.G_WORLD
G_NUM_PLAYERS, G_PLAYERS, REC_SIZE, REC_OBJ = T.G_NUM_PLAYERS, T.G_PLAYERS, T.REC_SIZE, T.REC_OBJ
H_TARGET, H_LAST_ATTACKER = T.H_TARGET, T.H_LAST_ATTACKER
ST_DEAD = T.ST_DEAD
D_1_4 = RB.Fraction(1.4)                        # the doubles at 0x52fc78 and 0x52fc80 (both 1.4 exactly as stored)


class MonsterCombatModel(T.CombatModel):
    """ref_combat_runtime.CombatModel plus the round-2 bodies of this module."""

    INTERNAL = dict(T.CombatModel.INTERNAL)
    INTERNAL.update({
        'creature_canSeePoint': 'can_see_point', 'creature_canSeeObjEdge': 'can_see_obj_edge',
        'creature_findPlayerInCone': 'find_player_in_cone',
        'Creature_hitTargetAtReach': 'hit_target_at_reach', 'Creature_hitTargetInArcEdge': 'hit_target_in_arc_edge',
        'Creature_hitTargetOrPlayerInArc': 'hit_target_or_player_in_arc',
        'Creature_knockbackTarget': 'knockback_target', 'Creature_setAttackCooldown': 'set_cooldown',
        'Creature_setAttackCooldownOn': 'set_cooldown_on', 'world_notifyObjectsNear': 'notify_objects_near',
    })
    MODELLED = dict(T.CombatModel.MODELLED)
    MODELLED.update({
        'creature_canSeePoint': 0x10C238, 'creature_canSeeObjEdge': 0x10C5B8, 'creature_findPlayerInCone': 0x10CA70,
        'Creature_hitTargetAtReach': 0x1196E8, 'Creature_hitTargetInArcEdge': 0x119850,
        'Creature_hitTargetOrPlayerInArc': 0x119A20, 'Creature_knockbackTarget': 0x119D10,
        'Creature_setAttackCooldown': 0x118BF0, 'Creature_setAttackCooldownOn': 0x118B58,
        'world_notifyObjectsNear': 0x11A2B8,
    })

    # ---- sight -------------------------------------------------------------------------
    def _seen(self, t):
        """The verdict every sight helper draws from a terrain ray: clear unless 0 <= t <= 1."""
        return 1 if C.lt(t, ZERO) or C.lt(ONE, t) else 0

    def can_see_point(self, c, pos, facing, arc, near, far):
        """creature_canSeePoint 0x10c238 (c, &pos, facing, arc; near, far) -> 0 or 1.

        v = pos - c.pos (3-D).  Arc: |s16(s16(0x4000 - atan2_16(v.x, v.y)) - facing)| < arc
        (strict).  Range: d = 2-D distance of the centres, near <= d < far - NO radius.
        Line of sight: one terrain ray from c.pos raised by the creature's FULL height
        (+0x20) along v, mask 3 always, factor 1.0999999; seen when t < 0 or 1 < t."""
        u32 = self.u32
        facing, arc = s16(facing), s16(arc)
        cx, cy, cz = self.vec(c + 0x10)
        v = (C.sub(pos[0], cx), C.sub(pos[1], cy), C.sub(pos[2], cz))
        delta = s16(s16(0x4000 - C.atan2_16(v[0], v[1])) - facing)
        if not abs(delta) < arc:
            return 0
        ex, ey = C.sub(cx, pos[0]), C.sub(cy, pos[1])
        d = C.sqrt(C.add(C.mul(ex, ex), C.mul(ey, ey)))
        if not C.lt(d, far) or not C.le(near, d):
            return 0
        origin = (cx, cy, C.add(cz, u32(c + 0x20)))
        return self._seen(self.call('terrain_raycast', u32(G_WORLD), origin, v, 3, F_RAY))

    def can_see_obj_edge(self, c, obj, facing, arc, ray_mode, near, far, lead):
        """creature_canSeeObjEdge 0x10c5b8 (c, obj, facing, arc, rayMode; near, far, lead).

        As creature_canSeeObj (round 1) - the same lead, arc, ray origin (half height), ray
        mode and verdict - except the range: d < far + obj.r and near - obj.r <= d; the
        creature's own radius is not used."""
        u32 = self.u32
        if not obj:
            return 0
        facing, arc = s16(facing), s16(arc)
        p = list(self.vec(obj + 0x10))
        if not C.eq(lead, ZERO) and u32(obj + 0xC) & 0x20:
            p[0] = C.add(p[0], C.mul(u32(obj + 0x308), lead))
            p[1] = C.add(p[1], C.mul(u32(obj + 0x30C), lead))
        cx, cy, cz = self.vec(c + 0x10)
        v = (C.sub(p[0], cx), C.sub(p[1], cy), C.sub(p[2], cz))
        if not abs(s16(C.atan2_16(v[1], v[0]) - facing)) < arc:
            return 0
        ex, ey = C.sub(cx, p[0]), C.sub(cy, p[1])
        d = C.sqrt(C.add(C.mul(ex, ex), C.mul(ey, ey)))
        orad = u32(obj + 0x1C)
        if not C.lt(d, C.add(far, orad)) or not C.le(C.sub(near, orad), d):
            return 0
        origin = (cx, cy, C.add(cz, C.mul(u32(c + 0x20), HALF)))
        t = self.call('terrain_raycast', u32(G_WORLD), origin, v, 0 if ray_mode else 3, F_RAY)
        return self._seen(t)

    def find_player_in_cone(self, c, facing, arc, near, far):
        """creature_findPlayerInCone 0x10ca70 (c, facing, arc; near, far) -> object or 0.

        A CHARMED creature (s16 +0x312 != 0) runs an inline copy of creature_findEnemyInCone
        (round 1, executed) - the same box (+-single(double(far) x 1.4), the double at
        0x52fc78), slot 20 score, inclusive arc, ray and scoring.
        Otherwise: best = far (a distance, not squared); for slot i in 0..g_numPlayers-1
        the record's object (+0x43d8): skip none and flag 8 (dead); v aimed at half heights;
        |s16(s16(0x4000 - atan2_16(v.x, v.y)) - facing)| < arc (STRICT here); 2-D centre
        distance d < best, d < far + o.r (never decisive: best <= far), near - o.r <= d; a
        terrain ray from the creature's full height along v (mask 3) that must give t < 0
        or 1 < t; then best = d.  The nearest in slot order, ties to the earlier slot.  No
        enemy, team, charm or player-flag test: any object the record names."""
        if self.s16(c + 0x312):
            return self.find_enemy_in_cone(c, facing, arc, near, far)
        u32 = self.u32
        facing, arc = s16(facing), s16(arc)
        best, found = far, 0
        for i in range(max(self.s32(G_NUM_PLAYERS), 0)):
            o = u32((G_PLAYERS + i * REC_SIZE + REC_OBJ) & M32)
            if not o or u32(o + 0xC) & 8:
                continue
            cx, cy, cz = self.vec(c + 0x10)
            ox, oy, oz = self.vec(o + 0x10)
            ctop = C.add(cz, C.mul(u32(c + 0x20), HALF))
            v = (C.sub(ox, cx), C.sub(oy, cy), C.sub(C.add(oz, C.mul(u32(o + 0x20), HALF)), ctop))
            delta = s16(s16(0x4000 - C.atan2_16(v[0], v[1])) - facing)
            if not abs(delta) < arc:
                continue
            ex, ey = C.sub(cx, ox), C.sub(cy, oy)
            d = C.sqrt(C.add(C.mul(ex, ex), C.mul(ey, ey)))
            if not C.lt(d, best):
                continue
            orad = u32(o + 0x1C)
            if not C.lt(d, C.add(far, orad)) or not C.le(C.sub(near, orad), d):
                continue
            origin = (cx, cy, C.add(cz, u32(c + 0x20)))
            if self._seen(self.call('terrain_raycast', u32(G_WORLD), origin, v, 3, F_RAY)):
                found, best = o, d
        return found

    # ---- hit helpers ---------------------------------------------------------------------
    def _damage(self, victim, c, lo, hi, attack, flags, desc):
        return self.call('damage_apply', victim, c, attack, 0, 0, flags, desc, 0,
                         C.from_int(s32(lo)), C.from_int(s32(hi)))

    def hit_target_at_reach(self, c, lo, hi, attack, flags, desc, reach):
        """Creature_hitTargetAtReach 0x1196e8 (c, min, max, attack, flags, desc; reach).

        No target: 0.  Point = (c.x + cos16(facing) x reach, c.y + sin16(facing) x reach,
        c.z).  The target must be within 60.0 of the point in 3-D (strict) and not flag 8
        (dead); no arc, sight ray or enemy test.  Then damage_apply(f32(min), f32(max);
        target, c, attack, 0, 0, flags, desc, 0) and its result."""
        u32 = self.u32
        node = u32(c + H_TARGET)
        if not node:
            return 0
        victim = u32(node + 0xC)
        facing = self.s16(c + 0x38)
        px = C.add(u32(c + 0x10), C.mul(C.cos16(facing), reach))
        py = C.add(u32(c + 0x14), C.mul(C.sin16(facing), reach))
        pz = u32(c + 0x18)
        t = u32(u32(c + H_TARGET) + 0xC)
        dx, dy, dz = C.sub(u32(t + 0x10), px), C.sub(u32(t + 0x14), py), C.sub(u32(t + 0x18), pz)
        d = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
        if not C.lt(d, F_60) or u32(t + 0xC) & 8:
            return 0
        return self._damage(victim, c, lo, hi, attack, flags, desc)

    def hit_target_in_arc_edge(self, c, facing, arc, lo, hi, attack, flags, desc, near, far):
        """Creature_hitTargetInArcEdge 0x119850 - Creature_hitTargetInArc (round 1) with
        creature_canSeeObjEdge (ray mode 0, lead 0) as the test."""
        node = self.u32(c + H_TARGET)
        if not node:
            return 0
        if not self.call('creature_canSeeObjEdge', c, self.u32(node + 0xC), s16(facing), s16(arc), 0,
                         near, far, ZERO):
            return 0
        return self._damage(self.u32(self.u32(c + H_TARGET) + 0xC), c, lo, hi, attack, flags, desc)

    def hit_target_or_player_in_arc(self, c, facing, arc, lo, hi, attack, flags, desc, near, far):
        """Creature_hitTargetOrPlayerInArc 0x119a20 (same arguments).  The target, when it
        has one and creature_canSeePoint(target position, facing, arc; near, far) passes;
        otherwise whatever creature_findPlayerInCone(facing, arc; near, far) returns; 0 when
        neither, else damage_apply as above.  Neither branch tests flag 8 or the enemy slot
        (the cone search itself skips dead players)."""
        u32 = self.u32
        facing, arc = s16(facing), s16(arc)
        victim = 0
        node = u32(c + H_TARGET)
        if node and self.call('creature_canSeePoint', c, self.vec(u32(node + 0xC) + 0x10), facing, arc, near, far):
            victim = u32(u32(c + H_TARGET) + 0xC)
        else:
            victim = self.call('creature_findPlayerInCone', c, facing, arc, near, far)
        if not victim:
            return 0
        return self._damage(victim, c, lo, hi, attack, flags, desc)

    def knockback_target(self, c, speed):
        """Creature_knockbackTarget 0x119d10 (c; speed): with a target, target +0x2e8 =
        speed and +0x2e0 = atan2_16(t.y - c.y, t.x - c.x) (the bearing from the creature).
        No other test; the victim reacts in its own Creature_applyKnockback."""
        node = self.u32(c + H_TARGET)
        if not node:
            return
        t = self.u32(node + 0xC)
        self.w32(t + 0x2E8, speed)
        a = C.atan2_16(C.sub(self.u32(t + 0x14), self.u32(c + 0x14)), C.sub(self.u32(t + 0x10), self.u32(c + 0x10)))
        self.w16(t + 0x2E0, a & 0xFFFF)

    # ---- cooldowns -----------------------------------------------------------------------
    def set_cooldown(self, c, frames):
        """0x118bf0 (c, frames): nothing without a target; unless the AI state is 0x14
        (dead) slot 27 with 0x10; then the cooldown +0x318 (16 bits) = frames."""
        if not self.u32(c + H_TARGET):
            return
        if self.s16(c + 0x232) != ST_DEAD:
            self.vcall(c, 27, 0x10)
        self.w16(c + 0x318, frames & 0xFFFF)

    def set_cooldown_on(self, c, frames, obj):
        """0x118b58 (c, frames, obj): nothing for a boss (creature_bossRank != 0) or a null
        obj; else the target handle is cleared and linked to obj, and then as 0x118bf0
        (slot 27 with 0x10 unless dead, +0x318 = frames)."""
        if self.call('creature_bossRank', c):
            return
        if not obj:
            return
        self.call('handle_clear', c + H_TARGET)
        self.call('handle_link', c + H_TARGET, obj, obj)
        if self.s16(c + 0x232) != ST_DEAD:
            self.vcall(c, 27, 0x10)
        self.w16(c + 0x318, frames & 0xFFFF)

    # ---- notification --------------------------------------------------------------------
    def notify_objects_near(self, a, pos, b, radius):
        """world_notifyObjectsNear 0x11a2b8 (a, &pos, b; R): one box query of pos +- R on all
        three axes, limit 0x80, and slot 12 (a, &copy of pos, b; R) of every object in list
        order - no flag, class or distance test."""
        low = tuple(C.sub(pos[i], radius) for i in range(3))
        high = tuple(C.add(pos[i], radius) for i in range(3))
        for o in self.call('world_collectObjectsInBox', low, high, 0x80):
            self.vcall(o, 12, a, tuple(pos), b, radius)
