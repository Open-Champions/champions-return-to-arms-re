"""ref_skeleton_run.py - the whole of Skeleton_run (every state of its switch, the bow
release included), creature_allyInLineOfFire, Creature_leadTargetPoint, Skeleton_onNearbyEvent
(slot 12) and Skeleton_hasShield.

Reference contract, executed against the original by tools/difftest_skeleton_run.py
(docs/spec/skeleton-run.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    Skeleton_run                0x2a6864 (slot 4; switch table 0x54bf00, 24 entries)
    creature_allyInLineOfFire   0x10d5e8 (creature, target, previous; range, distance)
    Creature_leadTargetPoint    0x11aaf8 (creature, out point or 0; projectile speed)
    Skeleton_onNearbyEvent      0x2a7688 (slot 12: creature, event code, position, other)
    Skeleton_hasShield          0x2a7da0 (creature)

The prologue (damage, Creature_run, an inactive skeleton returns, the holder's slot 21,
stepAnim(1.0) whose event bits states 6, 8 and 0x14 read, applyKnockback(0.7), slot 23)
is tools/ref_combat_ctors.py's; Skeleton_setState (slot 27) and Skeleton_isEnemy (slot 20,
inside slot 23's target scan) are tools/ref_combat_ctors.py's and tools/ref_combat_ctors2.py's.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_ctors as CT
import ref_combat_ctors2 as CT2
from ref_arena_monsters import half_toward_zero
from ref_creature import Ext, M32, M64, s16, s32

SKELETON_RUN, ALLY_IN_LINE, LEAD_TARGET = 0x2A6864, 0x10D5E8, 0x11AAF8
ON_NEARBY_EVENT, HAS_SHIELD = 0x2A7688, 0x2A7DA0
RUN_SWITCH = 0x54BF00                           # 24 words; 2, 4, 7, 9-0xf, 0x15, 0x16 go to the exit
STATE_COUNT = 0x18                              # unsigned compare at 0x2a6954

G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_LEVEL_MONSTER_LEVEL = RC.G_LEVEL_MONSTER_LEVEL    # 0x4f714c, truncated by cvt.w.s
G_SKILL_TABLE = 0x41B170
S_SWISH_FORMAT = 0x54BED8                       # the bow's whoosh clip name, one %d (0x2a71b0 / 0x2a71b8)
S_FX_LUMP = 0x54BEF0                            # the effects lump name (0x2a71c4 / 0x2a71c8)
MISSILE_WORDS = 0x3E9CE0                        # +8 and +0xc: MissileWeapon_ctor's third and fourth arguments

ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16                              # 0x37800000 at 0x2a7090
F_0_7 = CT.F_0_7                                # applyKnockback, 0x2a6920
F_1_75 = 0x3FE00000                             # allyInLineOfFire box half size factor, 0x10d648
F_3 = 0x40400000                                # radius factor of the line-of-fire sweep, 0x2a6b94 / 0x2a6d08
F_13 = 0x41500000                               # sweep origin height, 0x10d6fc
F_18 = 0x41900000                               # arrow origin above mid-height, 0x2a6f1c
F_20 = 0x41A00000                               # 0x2a6c08 / 0x2a6ca8 sight range, 0x2a74a0 deadUpdate size
F_24 = 0x41C00000                               # state 3 melee sight range, 0x2a6b58
F_36 = 0x42100000                               # state 6 reach, 0x2a6d90
F_48 = 0x42400000                               # arrow scatter, 0x2a7128
F_300 = 0x43960000                              # line-of-fire range 0x2a6ba8 / 0x2a6d18; aim distance 0x2a6e50
F_400 = 0x43C80000                              # bow sight range 0x2a6af8 / 0x2a6c68; arrow speed 0x2a6e78

# projectile per element (holder slot 16, hand 1): constructor, pool size, skill word
ARROWS = {
    2: ('ColdArrowProjectile_ctor', 0xB0, G_SKILL_TABLE + 4 * 44),      # 0x41b220
    1: ('FireArrowProjectile_ctor', 0xB0, G_SKILL_TABLE + 4 * 43),      # 0x41b21c
    6: ('ExplodeArrowProjectile_ctor', 0x74, G_SKILL_TABLE + 4 * 47),   # 0x41b22c
}
MISSILE_SIZE = 0x1C8

# bodies executed by tools/difftest_skeleton_run.py (name -> entry)
EXECUTED = {'Skeleton_run': SKELETON_RUN, 'creature_allyInLineOfFire': ALLY_IN_LINE,
            'Creature_leadTargetPoint': LEAD_TARGET, 'Skeleton_onNearbyEvent': ON_NEARBY_EVENT,
            'Skeleton_hasShield': HAS_SHIELD}

# virtual bodies: function -> (slot, method)
CLASS_BODIES = dict(CT2.CLASS_BODIES)
CLASS_BODIES.update({SKELETON_RUN: (4, 'skeleton_run'), ON_NEARBY_EVENT: (12, 'skeleton_on_nearby_event')})

INTERNAL = dict(CT2.INTERNAL)
INTERNAL.update({'creature_allyInLineOfFire': 'ally_in_line_of_fire'})

EXTERNALS = dict(CT2.EXTERNALS)
EXTERNALS.update({
    'world_countLivingNonplayerCreaturesInBox': Ext(0x108970, 'v', 1, 'i', '(centre; half size) -> count'),
    'creature_objInArcRange': Ext(0x10C410, 'ppi', 1, 'i', '(creature, object, arc; range) -> 0 or 1'),
    'ColdArrowProjectile_ctor': Ext(0x2D6FB4, 'pviipp', 0, 'n', '(block, origin, angle, owner, level, skill)'),
    'FireArrowProjectile_ctor': Ext(0x2D6238, 'pviipp', 0, 'n', '(block, origin, angle, owner, level, skill)'),
    'ExplodeArrowProjectile_ctor': Ext(0x2DAEB4, 'pviipp', 0, 'n', '(block, origin, angle, owner, level, skill)'),
    'MissileWeapon_ctor': Ext(0x150EE4, 'piiivvip', 0, 'n', '(block, 0, two words of 0x3e9ce0, origin, velocity, '
                              'angle - 0x4000, owner; nine words on the stack)'),
    'Holder.v16': Ext(0, 'pi', 0, 'i', '(hand) -> element of the hand'),
})
EXTERNALS['MissileWeapon_ctor'].stack = 9


def shape_result(name, args, ret=0, fret=0, outs=None):
    """CT.shape_result for this module's rows."""
    saved = CT.M1.EXTERNALS
    CT.M1.EXTERNALS = EXTERNALS
    try:
        return CT.M1.shape_result(name, args, ret, fret, outs)
    finally:
        CT.M1.EXTERNALS = saved


class Model(CT2.Model):
    """Skeleton_run in full on a memory image, with the line-of-fire sweep, the lead
    point and the shield reaction."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        method = INTERNAL.get(name)
        if method is not None:
            return getattr(self, method)(*args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and body[0] == slot:
            return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return CT2.Model.vcall(self, obj, slot, *args)

    # ---- helpers --------------------------------------------------------------------------
    def expired(self, c, offset):
        """The signed word at offset strictly below the creature clock +0x300."""
        return self.s32(c + offset) < self.s32(c + 0x300)

    def target_obj(self, c):
        return self.u32(self.u32(c + 0x234) + 0xC)

    def descriptor_arg(self, v):
        """A descriptor pointer as the difftests compare it (difftest_monsters_1's kind 'E'):
        0, or what the block holds - eight zero halfwords at +0x10, two 0xff bytes at +0x20
        and four effect slots from +0x24 - or its raw bytes when it does not hold that."""
        if v == 0:
            return 0
        ok = all(self.u16(v + 0x10 + 2 * k) == 0 for k in range(8)) and self.u8(v + 0x20) == 0xFF \
            and self.u8(v + 0x21) == 0xFF
        if not ok:
            return ('desc?', bytes(self.u8(v + 0x10 + k) for k in range(0x34)).hex())
        slots = []
        for k in range(4):
            ident = self.u16(v + 0x24 + 8 * k)
            slots.append(None if ident == 0xFFFF else
                         (ident, self.u16(v + 0x26 + 8 * k), self.u16(v + 0x28 + 8 * k), self.u16(v + 0x2A + 8 * k)))
        return ('desc', tuple(slots))

    def holder(self, c):
        return self.u32(c + 0x50)

    def ahead(self, c, distance):
        """The point `distance` ahead of the facing: (x + cos f * d, y + sin f * d, z)."""
        u32 = self.u32
        cos_f = C.cos16(self.s16(c + 0x38))
        sin_f = C.sin16(self.s16(c + 0x38))
        return (C.add(u32(c + 0x10), C.mul(cos_f, distance)), C.add(u32(c + 0x14), C.mul(sin_f, distance)),
                u32(c + 0x18))

    # ---- the base-class helpers this run reaches --------------------------------------------
    def ally_in_line_of_fire(self, c, target, previous, reach, distance):
        """creature_allyInLineOfFire 0x10d5e8 (creature, target, previous; range, distance)
        -> 0 or 1.

        No target, or a frame where (g_simFrame XOR s8 +0x230) & 7 is not 0: `previous`
        unchanged.  Otherwise n = world_countLivingNonplayerCreaturesInBox(target position;
        target radius x 1.75); creature_objInArcRange(creature, target, 0x4000; range) 0
        -> 0.  Then a = s16(0x4000 - atan2_16(target.x - x, target.y - y)) (x first: the
        bearing from the y axis turned into a heading), a ray from the creature 13 above
        its feet along (cos a, sin a, 0) x distance: world_raycast(g_world, origin,
        direction, creature, hit out, 3, 0; 1.0) -> t.  The answer is 1 when n >= 4
        (previous 0) or n >= 3 (previous non-zero), 0 < t < 1 (strict) and the object hit
        is not the target; else 0.  No draws."""
        u32 = self.u32
        if not target:
            return previous
        if (u32(G_SIM_FRAME) ^ self.s8(c + 0x230)) & 7:
            return previous
        count = s32(self.call('world_countLivingNonplayerCreaturesInBox', self.vec(target + 0x10),
                              C.mul(u32(target + 0x1C), F_1_75)))
        if not self.call('creature_objInArcRange', c, target, 0x4000, reach):
            return 0
        bearing = C.atan2_16(C.sub(u32(target + 0x10), u32(c + 0x10)), C.sub(u32(target + 0x14), u32(c + 0x14)))
        heading = s16(0x4000 - bearing)
        direction = (C.mul(C.cos16(heading), distance), C.mul(C.sin16(heading), distance), ZERO)
        origin = (u32(c + 0x10), u32(c + 0x14), C.add(u32(c + 0x18), F_13))
        t, hit = self.call('world_raycast', u32(G_WORLD), origin, direction, c, 1, 3, 0, ONE)
        if count < (3 if previous else 4):
            return 0
        if not (C.lt(ZERO, t) and C.lt(t, ONE)):
            return 0
        return 0 if hit == target else 1

    def lead_target_point(self, c, point, speed):
        """Creature_leadTargetPoint 0x11aaf8 (creature, out point; projectile speed) ->
        (1, the point) with a target object, else (0, the point unchanged).  k = the 2-D
        distance to the target / speed; the point is (target.x + vx k, target.y + vy k,
        target.z + height x 0.5), v the target's last move +0x308, +0x30c."""
        u32 = self.u32
        node = u32(c + 0x234)
        if not node or not u32(node + 0xC):
            return 0, point
        t = u32(node + 0xC)
        tx, ty, tz = self.vec(t + 0x10)
        dx, dy = C.sub(tx, u32(c + 0x10)), C.sub(ty, u32(c + 0x14))
        k = C.div(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), speed)
        return 1, (C.add(tx, C.mul(u32(t + 0x308), k)), C.add(ty, C.mul(u32(t + 0x30C), k)),
                   C.add(tz, C.mul(u32(t + 0x20), HALF)))

    def lead_target_point_entry(self, c, out, speed):
        """As an entry point: the result, and the point written to out (when out is not 0)
        kept in self.dest (None when nothing is written)."""
        ok, point = self.lead_target_point(c, None, speed)
        self.dest = point if ok and out else None
        return ok

    # ---- slot 12 -------------------------------------------------------------------------
    def skeleton_has_shield(self, c):
        """Skeleton_hasShield 0x2a7da0 -> 1 when the holder's slot 15 for hand 2 answers
        0x60 or 0x62 (the two shield parts the constructor gives a sword-and-board
        skeleton), else 0; 0 without a holder."""
        holder = self.holder(c)
        part = self.holder_call(holder, 15, 2) if holder else 0
        return 1 if part & M32 in (0x60, 0x62) else 0

    def skeleton_on_nearby_event(self, c, code, pos, other):
        """Skeleton_onNearbyEvent 0x2a7688, slot 12 (skeleton, event code, position, other).

        The position's three words are copied to the stack and never used (the pointer
        must be readable).  Only code 2: with a shield (Skeleton_hasShield), in state 3 or
        5, and an `other`, when the bearing to `other` less the facing, + 9999, is below
        19999 unsigned (that is, within -9999..+9999 of the facing): slot 27 with 0x11
        (block).  No draws, nothing else stored."""
        if s32(code) != 2:
            return
        if not self.skeleton_has_shield(c):
            return
        if self.s16(c + 0x232) not in (3, 5):
            return
        if not other:
            return
        u32 = self.u32
        bearing = C.atan2_16(C.sub(u32(other + 0x14), u32(c + 0x14)), C.sub(u32(other + 0x10), u32(c + 0x10)))
        if (bearing - self.s16(c + 0x38) + 9999) & M32 < 19999:
            self.set_state(c, 0x11)

    # ---- the run --------------------------------------------------------------------------
    def skeleton_run(self, c):
        """Skeleton_run 0x2a6864 (creature): one tick.

        Prologue (ref_combat_ctors.skeleton_run_prologue), keeping stepAnim's event bits
        ev.  The state, the s16 at +0x232, is compared unsigned with 0x18.  st = slot 27;
        see(arc, ray, far) = canSeeTargetIn(own facing, arc, ray; near 0, far, lead 0);
        bow = the weapon kind +0x3d0 is 4; T = the target handle +0x234; f4 = +0xf4:

          0, 1  slot 25 (0) -> 3; bow: slot 25 (1) -> 3; f4 < clock -> 1 from 0, 0 from 1;
                else 0: Creature_isAwayFromHome -> 1; 1: Creature_moveToDest
          3     no T -> 0.  bow: see(2000, 1, 400) -> 8; see(0x7fff, 1, 400) -> turn,
                else chase.  melee: see(6000, 0, 24) -> 6; allyInLineOfFire(T, 0; 300,
                radius x 3) -> ONE OWN DRAW, f4 = clock + 240 + d % 240, 5; see(0x7fff,
                0, 20) -> turn, else chase
          5     bow: see(2000, 0, 400) -> 8; melee (the kind re-read): see(6000, 0, 20) ->
                6; rooted -> stay; f4 < clock -> 3; no T -> stay; allyInLineOfFire(T, 1;
                300, radius x 3) -> stay; else 3
          6     with T: on ev bit 0 hitTargetAtReach(+0xd0, +0xd2, +0xd4, 8, holder slot
                17 (1) or 0; 36); clip flag 8 -> turn, else creature flag 0x200.  Clip
                flag 8 clear (re-read) -> f4 - 1; f4 <= 0 -> 3
          8     no T -> 0 (and on to the count-down).  With T: the lead point (a point 300
                ahead, then Creature_leadTargetPoint at speed 400); on ev bit 0 the release
                (skeleton_release); on ev bit 1 holder slot 1 (2, 0x56); clip flag 8 ->
                slot 26 (0, the lead point).  Clip flag 8 clear (re-read) -> f4 - 1;
                f4 <= 0 -> 3
          0x10  Creature_isAttackReady -> 0, else Creature_fleeFromTarget(0)
          0x11  f4 < clock -> 3
          0x12  clip flag 0x10 clear -> 3
          0x13  Creature_isNotStunned -> 0
          0x14  Creature_deadUpdate(ev, (0, 0, 0), 1; 20)
          0x17  fx_spawn(7, position); clip flag 0x10 clear -> 0
          2, 4, 7, 9-0xf, 0x15, 0x16: nothing."""
        st = self.set_state
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        if self.holder(c):
            self.holder_call(self.holder(c), 21, CT.SKEL_COMMON, c, HALF)
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, F_0_7)
        self.vcall(c, 23, 0)
        state = self.s16(c + 0x232)
        if not 0 <= state < STATE_COUNT:
            return
        bow = lambda: self.s32(c + 0x3D0) == 4      # noqa: E731
        see = lambda arc, ray, far: self.can_see_target_in(c, self.s16(c + 0x38), arc, ray, ZERO, far, ZERO)  # noqa
        if state in (0, 1):
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if bow() and self.vcall(c, 25, 1):
                return st(c, 3)
            if self.expired(c, 0xF4):
                return st(c, 1 if state == 0 else 0)
            if state == 0:
                if self.is_away_from_home(c):
                    st(c, 1)
            else:
                self.move_to_dest(c)
        elif state == 3:
            if not self.u32(c + 0x234):
                return st(c, 0)
            if bow():
                if see(2000, 1, F_400):
                    return st(c, 8)
                return self._turn_or_chase(c, see(0x7FFF, 1, F_400))
            if see(6000, 0, F_24):
                return st(c, 6)
            reach = C.mul(self.u32(c + 0x1C), F_3)
            if self.ally_in_line_of_fire(c, self.target_obj(c), 0, F_300, reach):
                d = self.obj_rand(c)
                self.w32(c + 0xF4, self.u32(c + 0x300) + d % 240 + 240)
                return st(c, 5)
            return self._turn_or_chase(c, see(0x7FFF, 0, F_20))
        elif state == 5:
            melee = True
            if bow():
                if see(2000, 0, F_400):
                    return st(c, 8)
                melee = not bow()
            if melee and see(6000, 0, F_20):
                return st(c, 6)
            if not self.is_not_rooted(c):
                return
            if self.expired(c, 0xF4):
                return st(c, 3)
            if not self.u32(c + 0x234):
                return
            reach = C.mul(self.u32(c + 0x1C), F_3)
            if self.ally_in_line_of_fire(c, self.target_obj(c), 1, F_300, reach):
                return
            return st(c, 3)
        elif state == 6:
            if self.u32(c + 0x234):
                if ev & 1:
                    holder = self.holder(c)
                    desc = self.holder_call(holder, 17, 1) if holder else 0
                    self.call('Creature_hitTargetAtReach', c, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 8, self.descriptor_arg(desc & M32), F_36)
                if self.anim_flags(c, 8):
                    self.turn_to_target(c)
                else:
                    self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200)
            return self._count_down(c)
        elif state == 8:
            if not self.u32(c + 0x234):
                st(c, 0)
                return self._count_down(c)
            _found, lead = self.lead_target_point(c, self.ahead(c, F_300), F_400)
            if ev & 1:
                lead = self.skeleton_release(c, lead)
            if ev & 2:
                holder = self.holder(c)
                if holder:
                    self.holder_call(holder, 1, 2, 0x56)
            if self.anim_flags(c, 8):
                self.vcall(c, 26, 0, lead)
            return self._count_down(c)
        elif state == 0x10:
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
        elif state == 0x11:
            if self.expired(c, 0xF4):
                return st(c, 3)
        elif state == 0x12:
            if not self.anim_flags(c, 0x10):
                return st(c, 3)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 0)
        elif state == 0x14:
            self.call('Creature_deadUpdate', c, ev, (ZERO, ZERO, ZERO), 1, F_20)
        elif state == 0x17:
            self.call('fx_spawn', 7, self.vec(c + 0x10))
            if not self.anim_flags(c, 0x10):
                return st(c, 0)

    def _turn_or_chase(self, c, seen):
        if seen:
            self.turn_to_target(c)
        else:
            self.move_to_target(c)

    def _count_down(self, c):
        """States 6 and 8: clip flag 8 clear -> +0xf4 - 1; then +0xf4 <= 0 -> state 3."""
        if not self.anim_flags(c, 8):
            self.w32(c + 0xF4, self.u32(c + 0xF4) - 1)
        if self.s32(c + 0xF4) > 0:
            return
        self.set_state(c, 3)

    def skeleton_release(self, c, lead):
        """State 8 on event bit 0: the arrow (0x2a6ed4-0x2a738c).  Returns the lead point,
        which the far-off-facing case replaces.

          holder slot 1 (2, 0): the hand-2 part off.
          origin o = (x, y, (z + height x 0.5) + 18); delta = lead - o; a = atan2_16(dy, dx).
          |a - facing| > 1000: the lead point becomes the point 300 ahead of the facing, and
              a is computed AGAIN from the SAME delta (so it does not change).
          delta x rsqrt(|delta|^2) x 400 (rsqrt.s 1.0 / sqrt), plus a unit-ball vector by
              OWN DRAW rejection (three draws a try, 2 d 2^-16 - 1 each, again while the
              squared length > 1) x 48: the velocity.
          ONE OWN DRAW d: libc_sprintf("swsh_arrow%d.anm", (d & 3) + 1), res_find("fx.lmp",
              that), sound_playOnObject(entry, creature; 1.0).
          e = holder slot 16 (1), 0 without a holder: 2 cold, 1 fire, 6 exploding arrow
              (pool_new 0xb0, 0xb0, 0x74; ctor(block, origin, a, creature,
              trunc(g_levelMonsterLevel), g_skillTable[44 / 43 / 47])); anything else
              pool_new(0x1c8) and MissileWeapon_ctor(block, 0, words 0x3e9ce8 and 0x3e9cec,
              origin, velocity, a - 0x4000, creature; stack 0, 0, s16 +0xd0, s16 +0xd2 / 2
              toward zero, 0, 0, s16 +0xd4, 4, 0).  A refused block: no constructor."""
        u32 = self.u32
        holder = self.holder(c)
        if holder:
            self.holder_call(holder, 1, 2, 0)
        x, y = u32(c + 0x10), u32(c + 0x14)
        z = C.add(C.add(u32(c + 0x18), C.mul(u32(c + 0x20), HALF)), F_18)
        origin = (x, y, z)
        dx, dy, dz = C.sub(lead[0], x), C.sub(lead[1], y), C.sub(lead[2], z)
        angle = C.atan2_16(dy, dx)
        if abs(angle - self.s16(c + 0x38)) > 1000:
            lead = self.ahead(c, F_300)
            angle = C.atan2_16(dy, dx)
        size = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
        inv = C.rsqrt(ONE, size)
        dx, dy, dz = C.mul(dx, inv), C.mul(dy, inv), C.mul(dz, inv)
        dx, dy, dz = C.mul(dx, F_400), C.mul(dy, F_400), C.mul(dz, F_400)
        while True:
            v = [C.sub(C.add(f, f), ONE) for f in
                 (C.mul(C.from_int(self.obj_rand(c)), F_2M16) for _k in range(3))]
            if not C.lt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))):
                break
        velocity = (C.add(dx, C.mul(v[0], F_48)), C.add(dy, C.mul(v[1], F_48)), C.add(dz, C.mul(v[2], F_48)))
        d = self.obj_rand(c)
        text = self.call('libc_sprintf', S_SWISH_FORMAT, (d & 3) + 1)
        entry = self.call('res_find', S_FX_LUMP, text)
        self.call('sound_playOnObject', entry, c, ONE)
        holder = self.holder(c)
        element = s32(self.holder_call(holder, 16, 1)) if holder else 0
        arrow = ARROWS.get(element)
        if arrow is not None:
            ctor, size, skill = arrow
            block = self.call('pool_new', size)
            if block:
                self.call(ctor, block, origin, angle, c, C.to_int(u32(G_LEVEL_MONSTER_LEVEL)), u32(skill))
        else:
            block = self.call('pool_new', MISSILE_SIZE)
            if block:
                self.call('MissileWeapon_ctor', block, 0, u32(MISSILE_WORDS + 8), u32(MISSILE_WORDS + 0xC), origin,
                          velocity, angle - 0x4000, c, 0, 0, self.s16(c + 0xD0), half_toward_zero(self.s16(c + 0xD2)),
                          0, 0, self.s16(c + 0xD4), 4, 0)
        return lead


__all__ = ['Model', 'EXECUTED', 'EXTERNALS', 'CLASS_BODIES', 'shape_result', 'M64']
