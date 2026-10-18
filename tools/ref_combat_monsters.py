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

    # =====================================================================================
    # The destructor chain (virtual slot 1).  Executed: tools/difftest_combat_monsters.py
    # =====================================================================================
    INTERNAL.update({'GameObject_dtor': 'gameobject_dtor', 'Creature_dtor': 'creature_dtor'})
    MODELLED.update({'GameObject_dtor': 0x14CF90, 'Creature_dtor': 0x117128, 'Skelight_dtor': 0x3CC67C,
                     'Player_dtor': 0x1A1BB8})

    def _lower_key(self):
        """GameObject_dtor lower-cases the static key string at 0x5321b0 in place before every
        scan (through the C library's class table at 0x5628e1, bit 0 = upper case): a store of
        each byte up to the terminator, even when nothing changes."""
        a = S_NAME_KEY
        while True:
            ch = self.u8(a)
            if not ch:
                return
            sc = s8(ch)
            if self.u8((G_CTYPE + sc) & M32) & 1:
                sc += 0x20
            self.w8(a, sc & 0xFF)
            a += 1

    def _strneq(self, a, b, n):
        """libc strncmp(a, b, n) == 0 (0x3b91d8)."""
        for i in range(n):
            x, y = self.u8(a + i), self.u8(b + i)
            if x != y:
                return False
            if not x:
                return True
        return True

    def _find_name(self, o, index):
        """The value of the index-th 'name=' entry of the property list +0x2c (entries are
        C strings; strncmp(entry, key, 4) == 0 and entry[4] == '='), or 0.  Keys are compared
        case-sensitively after the key string is lower-cased."""
        self._lower_key()
        props = self.u32(o + 0x2C)
        k = 0
        while True:
            entry = self.u32(props + 4 * k)
            if not entry:
                return 0
            same = self._strneq(entry, S_NAME_KEY, 4)
            if same and s8(self.u8(entry + 4)) == 0x3D:
                index -= 1
                if index == -1:
                    return (entry + 5) & M32
            k += 1

    def gameobject_dtor(self, o, flags):
        """GameObject_dtor 0x14cf90 (o, flags).  +0x48 = the GameObject table 0x5122a8.  For
        n = 0, 1, ...: the n-th 'name=' property is looked up (twice, the same scan), and
        objNames_remove(value, o) is called, until none is left; with no property list
        (+0x2c == 0) no scan at all.  Then handle_clear of +8 (grid), +4 (run list), +0
        (every handle to it) and, when bit 0 of flags is set, pool_free(o)."""
        self.w32(o + 0x48, VT_GAMEOBJECT)
        n = 0
        while self.u32(o + 0x2C):
            if not self._find_name(o, n):
                break
            self.call('objNames_remove', self._find_name(o, n), o)
            n += 1
        for off in (8, 4, 0):
            self.call('handle_clear', o + off)
        if flags & 1:
            self.call('pool_free', o)

    def creature_dtor(self, c, flags):
        """Creature_dtor 0x117128 (c, flags).  +0x48 = the Creature table 0x50cc58 (so a
        class's own slots are no longer reached from here on).  Every attached spell of the
        list +0x364 (iterator, mask 0): spell slot 1 with 3 through the spell's table at +0x14
        (a node whose object word is 0 is passed over); iter_end(2).  Then handle_clear of
        +0x364, +0x360; 0x202500(+0x320, 2) (a destructor that only frees with bit 0: nothing
        here); handle_clear of +0x2e4, +0x238, +0x234; AnimState_dtor(+0x114, 0);
        GameObject_dtor(c, 0); pool_free(c) when bit 0 of flags is set."""
        self.w32(c + 0x48, T.VT_CREATURE)
        node = self.call('iter_begin', c + 0x364, 0)
        while node:
            spell = self.u32(node + 0xC)
            if spell:
                self.table_call('Spell', spell, 0x14, 1, 3)
            node = self.call('iter_next')
        self.call('iter_end', 2)
        self.call('handle_clear', c + 0x364)
        self.call('handle_clear', c + 0x360)
        self.call('sub_202500', c + 0x320, 2)
        for off in (0x2E4, 0x238, 0x234):
            self.call('handle_clear', c + off)
        self.call('AnimState_dtor', c + 0x114, 0)
        self.call('GameObject_dtor', c, 0)
        if flags & 1:
            self.call('pool_free', c)

    def skelight_dtor(self, c, flags):
        """Skelight_dtor 0x3cc67c: +0x48 = 0x5174b0, Creature_dtor(c, 0), pool_free when bit 0."""
        self.w32(c + 0x48, T.VT_SKELIGHT)
        self.call('Creature_dtor', c, 0)
        if flags & 1:
            self.call('pool_free', c)

    def player_dtor(self, P, flags):
        """Player_dtor 0x1a1bb8 (P, flags).  +0x48 = 0x511308.  Unless g_inGhostOp (s8
        0x402795): for an ordinary player (+0x462 == 0) the record's object pointer +0x43d8 is
        zeroed, for a display-only one the byte 0x4ef360 instead; in both cases the five
        record words +0x43dc..+0x43ec.  Then (also during a ghost operation)
        game_rebuildAlivePlayers; handle_clear(+0x588); AnimState_dtor(+0x560, 2);
        light_dtor(+0x504, 2), light_dtor(+0x4c8, 2); handle_clear(+0x4b8); the array of five
        0x18-byte elements at +0x3d0 in reverse - handle_clear of +0x438, +0x420, +0x408,
        +0x3f0, +0x3d8; Creature_dtor(P, 0); pool_free when bit 0."""
        self.w32(P + 0x48, T.VT_PLAYER)
        if not self.s8(G_IN_GHOST_OP):
            R = self._rec(P)
            if not self.s8(P + 0x462):
                self.w32(R + REC_OBJ, 0)
            else:
                self.w8(G_DISPLAY_PLAYER_BYTE, 0)
            for k in range(5):
                self.w32(R + 0x43DC + 4 * k, 0)
        self.call('game_rebuildAlivePlayers')
        self.call('handle_clear', P + 0x588)
        self.call('AnimState_dtor', P + 0x560, 2)
        self.call('light_dtor', P + 0x504, 2)
        self.call('light_dtor', P + 0x4C8, 2)
        self.call('handle_clear', P + 0x4B8)
        for off in (0x438, 0x420, 0x408, 0x3F0, 0x3D8):
            self.call('handle_clear', P + off)
        self.call('Creature_dtor', P, 0)
        if flags & 1:
            self.call('pool_free', P)


    # =====================================================================================
    # Creature_deadUpdate 0x1108a0 with its blood decal (round 1 refused the decal)
    # =====================================================================================
    BLOOD_KINDS = ((0x1000, 6), (0x2000, 3), (0x4000, 0xA), (0x40000, 0))

    def dead_update(self, c, events, offset, hold, size):
        """Creature_deadUpdate 0x1108a0 (size; c, events, &offset, hold), the whole body.

        The sinking corpse (creature flag 0x1000000) and the final delete test are round 1's
        (ref_combat_runtime.CombatModel.dead_update, executed).  The blood decal, new here:
        with events & 0x80, object flag 2 clear, 0 < size and hold 0, the FIRST of the
        creature-flag bits 0x1000, 0x2000, 0x4000, 0x40000 that is set picks decal kind 6, 3,
        0xa or 0; then TWO OWN DRAWS (GameObject_rand on +0x44): angle = s16(first), and
        decal_add(position + offset, angle, kind, 1; size + float(second % 10)) (an unsigned
        remainder).  No bit set: no draw, no decal."""
        u32 = self.u32
        cf = self.u64(c + 0xA8)
        if cf & 0x1000000:
            return T.CombatModel.dead_update(self, c, events, offset, hold, size)
        if events & 0x80 and not u32(c + 0xC) & 2 and C.lt(ZERO, size) and not hold:
            for bit, kind in self.BLOOD_KINDS:
                if cf & bit:
                    x, y, z = self.vec(c + 0x10)
                    pos = (C.add(x, offset[0]), C.add(y, offset[1]), C.add(z, offset[2]))
                    angle = s16(self.obj_rand(c))
                    extra = (self.obj_rand(c) & M32) % 10
                    self.call('decal_add', pos, angle, kind, 1, C.add(size, C.from_int(extra)))
                    break
        if self.u64(c + 0x118) & 0x8000FF == 0x800001 and hold:
            self.call('obj_delete', c)


    # =====================================================================================
    # Creature_dropLoot 0x10f2c8.  Executed: tools/difftest_combat_monsters.py ('dropLoot')
    # =====================================================================================
    INTERNAL.update({'Creature_dropLoot': 'drop_loot'})
    MODELLED.update({'Creature_dropLoot': 0x10F2C8})

    def _gen(self, pos, angle, filt, force, z, throw, gs, gc, q, ic):
        self.call('loot_generateDrops', pos, angle, filt, force, z, throw, gs, gc, q, ic)

    def _is_class(self, c, typeinfo_name):
        """One exact-class test: typeid(*c) (virtual slot 0 - called with whatever the
        previous call left in a0, so its `this` is not meaningful) against the class's
        type-info getter, through rtti_typeInfoEquals 0x3b1250."""
        mine = self.call('Creature.v0')
        theirs = self.call(typeinfo_name)
        return self.call('rtti_typeInfoEquals', mine, theirs)

    def drop_loot(self, c, pos, angle, filt, z, throw, gs, gc, q, ic):
        """Creature_dropLoot 0x10f2c8 (c, &pos, angle, filter; zOffset, throwSpeed,
        goldScale, goldChance, qualityRow, itemChance).  Every drop is a call of
        loot_generateDrops 0x100d54 (&copy of pos, angle, filter or 0, forcePreset; six
        floats) - tools/ref_items.py models that generator.  In order:

          1. nothing for creature flag 0x100000000, or the 'noloot' property (key 0x52ffd8)
             outside PvP mode B (0x4f7120);
          2. eleven exact-class tests in the order of LOOT_CLASSES; the first class that
             matches (SeaMonster only with creature flag bit 0, CloudGiant only with the
             word +0x3d8 non-zero - otherwise the next test runs) makes its fixed calls and
             RETURNS: optionally the ordinary call (the caller's filter and six numbers), two
             or three richer calls, then one call per player slot 0..g_numPlayers-1 that
             forces a preset item either always or when an OWN DRAW (GameObject_rand,
             float(value) x 2^-16) is below 0.5;
          3. otherwise creature_bossRank: rank 2 adds the ordinary call, two richer calls and
             a per-player coin (0.5); else a second creature_bossRank call, and rank 1 adds
             two calls and a per-player coin of 0.25;
          4. then a tint preset (s8 +0xa0 != 0) multiplies goldScale by 3 and qualityRow by
             4, and the ordinary call is made when creature flag bit 0 (MiniBoss) is clear.
        No shared draw; the own draws are one per player slot in a coin loop."""
        u32 = self.u32
        if self.u64(c + 0xA8) & 0x100000000:
            return
        if self.call('obj_getPropInt', c, S_NOLOOT, 0) and not u32(G_PVP_MODE_B):
            return
        ordinary = (filt, 0, z, throw, gs, gc, q, ic)

        def per_player(kind, q_extra, ic_extra):
            for _slot in range(max(self.s32(G_NUM_PLAYERS), 0)):
                force = 1
                if kind != 'always':
                    draw = self.obj_rand(c)
                    force = 1 if C.lt(C.mul(C.from_int(s32(draw)), 0x37800000), kind) else 0
                self._gen(pos, angle, 0, force, z, throw, ZERO, ZERO, q_extra, ic_extra)
            return

        for name, cond, has_ord, extras, loop in LOOT_CLASSES:
            if not self._is_class(c, name):
                continue
            if cond == 'miniboss' and not self.u64(c + 0xA8) & 1:
                continue
            if cond == 'word3d8' and not u32(c + 0x3D8):
                continue
            if has_ord:
                self._gen(pos, angle, *ordinary)
            for e_gs, e_gc, e_q, e_ic in extras:
                self._gen(pos, angle, 0, 0, z, throw, e_gs, e_gc, e_q, e_ic)
            per_player(*loop)
            return
        rank = s32(self.call('creature_bossRank', c))
        if rank == 2:
            self._gen(pos, angle, *ordinary)
            for e_gs, e_gc, e_q, e_ic in ((F4, F1, F6, F2), (F5, F1, F7, F2)):
                self._gen(pos, angle, 0, 0, z, throw, e_gs, e_gc, e_q, e_ic)
            per_player(F_HALF, F8_5, F2)
        elif s32(self.call('creature_bossRank', c)) == 1:
            for e_gs, e_gc, e_q, e_ic in ((F4, F1, F3, F1_5), (F5, F1, F5, F1_5)):
                self._gen(pos, angle, 0, 0, z, throw, e_gs, e_gc, e_q, e_ic)
            per_player(F_QUARTER, F7, F1_5)
        if self.s8(c + 0xA0):
            gs, q = C.mul(gs, F3), C.mul(q, F4)
        if not u32(c + 0xA8) & 1:
            self._gen(pos, angle, filt, 0, z, throw, gs, gc, q, ic)


    # =====================================================================================
    # A corpse-phase class's death: Goblin_setState 0x26ccfc, state 0x14 only
    # =====================================================================================
    MODELLED.update({'Goblin_setState': 0x26CCFC})

    def goblin_set_state(self, c, state):
        """Goblin_setState 0x26ccfc (c, state), slot 27 of Goblin (table 0x510260) -
        DEATH ONLY: any filtered state below 0x18 other than 0x14 is refused.

        Creature_filterState (refused: return, +0x232 untouched); creature flag 0x200
        cleared.  State 0x14:
          1. without the 'dead' property (0x546998): one box query of +-96 around the
             goblin, limit 0x80; when 3 or more of the objects have flags & 0x68 == 0x28
             (creature, dead, not a player) +0x488 = 1 (this corpse will sink and be deleted,
             Goblin_run state 0x14);
          2. unless object flag 2: object flag 1 is CLEARED, and the weapon holder (+0x50)
             drops hand 1 then hand 2 (holder slot 11 with (hand, c, part table 0x500448 +
             family +0x490 x 0x80, 0));
          3. the 'dead' property again: set -> object flag 1;
          4. the death clip (definition +0x44, flags 6, blend 0.3) - the same call whether or
             not the pending flags +0x2dc carry a knock-back class (both branches, 0x26d514);
          5. unless creature flag 0x100000000: Creature_dropLoot(c, position, facing, 0;
             36, 2, 1.8, 0.6, 2, 0.25); then an archer (role +0x3d4 == 4) with an OWN DRAW
             below 6000 (of 65536) and no 'noloot' property drops the named item 'arrows'
             (loot_spawnNamedItem);
          6. slot 28 (on death) with 0;
        then +0x232 = the state."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        self.w64(c + 0xA8, self.u64(c + 0xA8) & ~0x200 & T.M64)
        if state < 0x18 and state != 0x14:
            raise Unsupported('Goblin_setState state 0x%x (only the death branch is in this contract)' % state)
        if state == 0x14:
            u32 = self.u32
            if not self.call('obj_getPropInt', c, S_GOBLIN_DEAD, 0):
                x, y, z = self.vec(c + 0x10)
                found = self.call('world_collectObjectsInBox', (C.sub(x, F_96), C.sub(y, F_96), C.sub(z, F_96)),
                                  (C.add(x, F_96), C.add(y, F_96), C.add(z, F_96)), 0x80)
                if sum(1 for o in found if u32(o + 0xC) & 0x68 == 0x28) >= 3:
                    self.w32(c + 0x488, 1)
            if not u32(c + 0xC) & 2:
                self.w32(c + 0xC, u32(c + 0xC) & ~1 & M32)
                for hand in (1, 2):
                    holder = u32(c + 0x50)
                    if holder:
                        self.holder_call(holder, 11, hand, c, (GOBLIN_PARTS + s8(self.u8(c + 0x490)) * 0x80) & M32, 0)
            if self.call('obj_getPropInt', c, S_GOBLIN_DEAD, 0):
                self.w32(c + 0xC, u32(c + 0xC) | 1)
            self.call('anim_start', c + 0x114, self.clip(c, 0x44), 6, 0x3E999999)
            if not self.u64(c + 0xA8) & 0x100000000:
                self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), 0,
                          0x42100000, F2, 0x3FE66666, 0x3F199999, F2, F_QUARTER)
                if self.s32(c + 0x3D4) == 4 and (self.obj_rand(c) & M32) < 0x1770:
                    if not self.call('obj_getPropInt', c, S_GOBLIN_NOLOOT, 0):
                        self.call('loot_spawnNamedItem', self.vec(c + 0x10), S_GOBLIN_ARROWS)
            self.vcall(c, 28, 0)
        self.w16(c + 0x232, state & 0xFFFF)


VT_GAMEOBJECT = 0x5122A8
S_NAME_KEY = 0x5321B0                           # the key string GameObject_dtor scans for
G_CTYPE = 0x5628E1
G_IN_GHOST_OP = 0x402795
G_DISPLAY_PLAYER_BYTE = 0x4EF360                # cleared by Player_dtor for a display-only player (meaning Unknown)
DTOR_BODIES = {0x14CF90: 'gameobject_dtor', 0x117128: 'creature_dtor', 0x3CC67C: 'skelight_dtor',
               0x1A1BB8: 'player_dtor'}

G_PVP_MODE_B = T.G_PVP_MODE_B
S_NOLOOT = 0x52FFD8                             # the property key string 'noloot'
F_QUARTER, F_HALF, F1, F1_5, F2, F3, F4 = 0x3E800000, 0x3F000000, 0x3F800000, 0x3FC00000, 0x40000000, 0x40400000, 0x40800000
F5, F6, F7, F7_5, F8, F8_5, F15, F20 = 0x40A00000, 0x40C00000, 0x40E00000, 0x40F00000, 0x41000000, 0x41080000, 0x41700000, 0x41A00000
_STD = ((F4, F1, F6, F2), (F5, F1, F7, F2))
# Creature_dropLoot's class tests, in order (Observed, 0x10f384-0x110424):
#   (type-info getter, condition, ordinary call first, richer calls (goldScale, goldChance,
#    qualityRow, itemChance), per-player call (force: 'always' or a coin threshold,
#    qualityRow, itemChance))
LOOT_CLASSES = (
    ('SpiderQueen_typeinfo', None, True, _STD, (F_HALF, F8, F2)),         # 0x10f3b0
    ('AntQueen_typeinfo', None, True, _STD, ('always', F8, F2)),         # 0x10f548
    ('UndeadKnight_typeinfo', None, True, _STD, (F_HALF, F8, F2)),       # 0x10f698
    ('VampireLord_typeinfo', None, True, _STD, (F_HALF, F8, F2)),        # 0x10f830
    ('Arenabeast_typeinfo', None, True, _STD, (F_HALF, F8, F2)),         # 0x10f9c8
    ('SeaMonster_typeinfo', 'miniboss', False, ((F4, F1, F5, F2), (F5, F1, F6, F2)), (F_HALF, F7_5, F2)),  # 0x10fb60
    ('CloudGiant_typeinfo', 'word3d8', True, _STD, ('always', F8, F2)),  # 0x10fce0
    ('Minion_typeinfo', None, True, _STD, ('always', F8, F2)),           # 0x10fe38
    ('MummyKing_typeinfo', None, True, _STD, (F_HALF, F8, F2)),          # 0x10ff88
    ('Innoruuk_typeinfo', None, True, ((F15, F1, F6, F2), (F20, F1, F7, F2)), (F_HALF, F8, F2)),  # 0x110120
    ('Zek_typeinfo', None, False, ((F4, F1, F4, F2), (F4, F1, F5, F2), (F6, F1, F7, F2)), (F_HALF, F8_5, F2)),  # 0x1102b8
)
TYPEINFO_GETTERS = {
    'SpiderQueen_typeinfo': 0x3C4888, 'AntQueen_typeinfo': 0x3C3C78, 'UndeadKnight_typeinfo': 0x3CC938,
    'VampireLord_typeinfo': 0x3CCA98, 'Arenabeast_typeinfo': 0x3C9330, 'SeaMonster_typeinfo': 0x3CC568,
    'CloudGiant_typeinfo': 0x3CA4AC, 'Minion_typeinfo': 0x3CBA24, 'MummyKing_typeinfo': 0x3CC29C,
    'Innoruuk_typeinfo': 0x3CB1A0, 'Zek_typeinfo': 0x3CCD64,
}

F_96 = 0x42C00000
GOBLIN_PARTS = 0x500448                         # weapon-part tables, one of 0x80 bytes per model family
S_GOBLIN_DEAD, S_GOBLIN_NOLOOT, S_GOBLIN_ARROWS = 0x546998, 0x5469A0, 0x5469A8
VT_GOBLIN = 0x510260


class MonsterRuntime(T.Runtime):
    """ref_combat_runtime.Runtime whose model is MonsterCombatModel: the round-2 helpers are
    reachable from the shared world (AUTHORED composition; the bodies are executed).  The
    destructor chain stays round 1's Runtime._slot1, whose order the executed bodies confirm
    (docs/spec/combat-monster-death.md 4); loot generation and type-info tests are call-outs
    the runtime refuses (loot objects are outside the contract's domain)."""

    def __init__(self, *args, **kwargs):
        T.Runtime.__init__(self, *args, **kwargs)
        self.model = MonsterCombatModel(self.mem, self.services)
