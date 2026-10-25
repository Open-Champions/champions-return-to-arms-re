"""ref_soul_run.py - the whole of Soul_run, every state of its switch, Soul_isDemonNear as
it runs inside it, and Creature_setCharm.

Reference contract, executed against the original by tools/difftest_soul_run.py
(docs/spec/soul-run.md is the prose).  Everything here is Observed by that difftest unless
a docstring says otherwise.

    Soul_run            0x2a9870 (slot 4; switch table 0x54c2c0, 35 entries)
    Soul_isDemonNear    0x2ab2b4 (round 5's body, here with the real type-info getters)
    Creature_setCharm   0x1189f0 (creature, frames, team)

The prologue (damage and Creature_run with the slot-16 model, an inactive soul returns,
stepAnim(1.0) whose event bits state 0x1d reads, applyKnockback(0.0), slot 23, the
zero-vector move unless owned or in 0x1b) is tools/ref_combat_ctors.py's.  The matrix
helpers (mat34_setPosRotZScale, mat34_rotateAxis, mat34_transformPoint, mat34_invert,
mat34_mul) are tools/ref_core.py's bodies, executed by tools/difftest_core.py, and run for
real here too.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_ctors as CT
import ref_combat_ctors2 as CT2
import ref_monsters_1 as M1
from ref_creature import Ext, M32, s16, s32

SOUL_RUN, SOUL_IS_DEMON_NEAR, CREATURE_SET_CHARM = 0x2A9870, 0x2AB2B4, 0x1189F0
RUN_SWITCH = 0x54C2C0                           # 35 words (0x23 at 0x2a997c)
STATE_COUNT = 0x23
P_SOUL = CT.P_SOUL                              # 0x8e4600 (formed at 0x2a9ccc/0x2a9cd4 and the other spawns)
G_WORLD = RC.G_WORLD
G_SIM_FRAME = RC.G_SIM_FRAME
G_NUM_PLAYERS, G_PLAYERS, REC_SIZE, REC_OBJ = RC.G_NUM_PLAYERS, RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ

ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16                              # 0x37800000, the unit-ball draws (0x2a9be4 ...)
F_15 = CT.F_15                                  # 0x41700000, particle speed (0x2a9c7c ...)
F_0_2 = 0x3E4CCCCC                              # thrown: target velocity lead (0x2aa0f8)
F_0_4 = 0x3ECCCCCC                              # thrown: turn rate stored at +0xb0 (0x2aa124)
F_400 = 0x43C80000                              # thrown: speed (0x2aa23c, 0x2aa284)
F_M60 = 0xC2700000                              # thrown at a target: highest vertical speed (0x2aa248)
F_M80 = 0xC2A00000                              # thrown with no target: vertical speed (0x2aa2a8)
F_STEP = 0x3B888888                             # 1/240 per sub-step (0x2aa2cc)
F_36 = 0x42100000                               # thrown: contact point ahead (0x2aa384)
F_6 = 0x40C00000                                # thrown: terrain_height radius (0x2aa4dc)
F_10, F_50 = 0x41200000, 0x42480000             # thrown: damage_apply min / max (0x2aa43c, 0x2aa448)
DAMAGE_FLAGS = 0x4000140                        # 0x2aa450 / 0x2aa464
THROW_ROLL = 0x5F40                             # added to the facing for the throw matrix (0x2a9f14)
THROW_PITCH = 0x4FA0                            # mat34_rotateAxis(m, 0, ...) (0x2a9f54)
SAMPLE_FACING = 0xFFFFC000                      # -0x4000 passed as the facing (0x2a9fb0, 0x2aa554, 0x2aa718)
DEMON_REACH, DEMON_LIMIT = 0x43960000, 0x80     # Soul_isDemonNear: box half-size 300, capacity 128

# bodies executed by tools/difftest_soul_run.py (name -> entry); Soul_isDemonNear was
# executed first by tools/difftest_combat_round5.py and runs for real here too
EXECUTED = {'Soul_run': SOUL_RUN, 'Creature_setCharm': CREATURE_SET_CHARM, 'Soul_isDemonNear': SOUL_IS_DEMON_NEAR}
# what the model runs as bodies: the above plus tools/ref_core.py's matrix helpers, executed
# by tools/difftest_core.py and borrowed here unchanged
MODELLED = dict(EXECUTED)
MODELLED.update({'mat34_setPosRotZScale': 0x163CB8, 'mat34_rotateAxis': 0x163000,
                 'mat34_transformPoint': 0x1660A0, 'mat34_invert': 0x164288, 'mat4_invert': 0x163F98,
                 'mat34_mul': 0x162808})
# Soul_run states whose arms the difftest executed in full (every state: see the doc)
SOUL_RUN_STATES_EXECUTED = set(range(STATE_COUNT))

MATRIX_OUT = {'creature_getAttachMatrix0': 1, 'model_getAttachMatrix': 3}   # name -> register of the out mat34

EXTERNALS = dict(CT2.EXTERNALS)
EXTERNALS.update({
    'obj_stopRunning': Ext(0x14F290, 'p', 0, 'n', '(object): off the run lists'),
    'creature_getAttachMatrix0': Ext(0x287940, 'p-', 0, 'n', '(owner object, out mat34)'),
    'model_getAttachMatrix': Ext(0x1795F8, 'ppi-', 1, 'n', '(model, anim state, attach 0, out mat34; 1.0)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """M1.shape_result for this module's rows; the two matrix call-outs return their
    twelve floats (zeros when nobody supplied them)."""
    if name in MATRIX_OUT:
        return tuple(outs[0]) if outs else (0,) * 12
    saved = M1.EXTERNALS
    M1.EXTERNALS = EXTERNALS
    try:
        return M1.shape_result(name, args, ret, fret, outs)
    finally:
        M1.EXTERNALS = saved


c_rem = CT2.c_rem


class Model(CT2.Model):
    """Soul_run in full on a memory image."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        if name == 'Creature_setCharm':         # executed here: not a callback
            return self.creature_set_charm(*args)
        method = CT2.INTERNAL.get(name)
        if method is not None:
            return getattr(self, method)(*args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    # ---- Creature_setCharm ------------------------------------------------------------------
    def creature_set_charm(self, c, frames, team):
        """Creature_setCharm 0x1189f0 (creature, frames, team).

        Nothing when the charm timer +0x312 (s16) is already -1, when object flag 0x20
        (a monster) is clear, or when object flag 0x40 (a player) is set.  Otherwise: team
        byte +0x310 = the low byte of team, +0x312 = the low halfword of frames,
        handle_clear(+0x234) (the target handle), then +0x234 = 0.  No draw."""
        if self.s16(c + 0x312) == -1:
            return
        flags = self.u32(c + 0xC)
        if not flags & 0x20 or flags & 0x40:
            return
        self.w8(c + 0x310, team & 0xFF)
        self.w16(c + 0x312, frames & 0xFFFF)
        self.call('handle_clear', c + 0x234)
        self.w32(c + 0x234, 0)

    # ---- Soul_isDemonNear (round 5's contract) --------------------------------------------
    def soul_is_demon_near(self, c):
        """Soul_isDemonNear 0x2ab2b4 -> 0 or 1: the box +-300 around the soul, capacity
        128; the first entry whose type is exactly Demon (slot 0 against Demon_typeinfo,
        rtti_typeInfoEquals) and whose object flag 8 is clear."""
        x, y, z = self.vec(c + 0x10)
        low = (C.sub(x, DEMON_REACH), C.sub(y, DEMON_REACH), C.sub(z, DEMON_REACH))
        high = (C.add(x, DEMON_REACH), C.add(y, DEMON_REACH), C.add(z, DEMON_REACH))
        found = self.call('world_collectObjectsInBox', low, high, DEMON_LIMIT)
        for obj in found:
            mine = self.typeid(obj)
            if self.typeinfo_equals(mine, self.typeinfo(CT2.TI_DEMON)) and not self.u32(obj + 0xC) & 8:
                return 1
        return 0

    # ---- helpers --------------------------------------------------------------------------
    def expired(self, c, offset):
        """The signed word at offset strictly below the creature clock +0x300."""
        return self.s32(c + offset) < self.s32(c + 0x300)

    def demon_due(self, c):
        """(g_simFrame XOR the signed byte +0x230) & 0xf == 0."""
        return ((self.u32(G_SIM_FRAME) ^ self.s8(c + 0x230)) & 0xF) == 0

    def unit_ball(self, c):
        """Three OWN DRAWS a try, each 2 d 2^-16 - 1, again while x^2 + y^2 + z^2 > 1."""
        while True:
            v = [C.sub(C.add(f, f), ONE) for f in
                 (C.mul(C.from_int(self.obj_rand(c)), F_2M16) for _k in range(3))]
            size = C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))
            if not C.lt(ONE, size):
                return v

    def flat_velocity(self, v):
        """The copy's z word zeroed, then x, y and that zero times 15."""
        return (C.mul(v[0], F_15), C.mul(v[1], F_15), C.mul(ZERO, F_15))

    def sample_point(self, c, position, facing, index):
        """model_getSamplePoint(slot 16 model, +0x114, position, facing, index, out, second
        out, 0; scale +0xdc) -> the point (slot 16 is called first)."""
        model = self.vcall(c, 16)
        point, _second = self.call('model_getSamplePoint', model, c + 0x114, tuple(position), facing & M32,
                                   index & M32, 1, 0, self.u32(c + 0xDC))
        return tuple(point)

    def spawn(self, point, v):
        self.call('particle_spawn', P_SOUL, tuple(point), self.flat_velocity(v), ZERO)

    # ---- the run --------------------------------------------------------------------------
    def soul_run(self, c):
        """Soul_run 0x2a9870 (creature): one tick.

        Prologue (ref_combat_ctors.soul_run_prologue), keeping stepAnim's event bits ev.
        The state, the s16 at +0x232 (read again after the zero-vector move), is compared
        unsigned with 0x23.  With st = slot 27, due = (g_simFrame ^ s8 +0x230) & 0xf == 0,
        demon = Soul_isDemonNear, expired(o) = s32 o < s32 clock +0x300:

          0     due and demon -> 0x18; expired(+0xf4) -> 1; Creature_isAwayFromHome -> 1
          1     due and demon -> 0x18; Creature_moveTo(copy of +0x104) arrived -> 0;
                expired(+0xf4) -> 0
          3     no target +0x234 -> 0
          5     Creature_isNotRooted -> 0
          0x12, 0x19  clip flag 0x10 clear -> 0x18
          0x14, 0x22  dissolve (soul_dissolve)
          0x17  expired(+0xf4) -> 1
          0x18  due and not demon -> 0
          0x1b  thrown (soul_thrown)
          0x1d  on ev bit 0: burst and delete (soul_burst_owned)
          anything else below 0x23: nothing."""
        self.process_damage(c, self.vcall(c, 16))
        if self.run(c, self.vcall(c, 16)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, ZERO)
        self.vcall(c, 23, 0)
        if not self.u32(c + 0x3C8) and self.s16(c + 0x232) != 0x1B:
            self.move_by(c, (ZERO, ZERO, ZERO))
        state = self.s16(c + 0x232)
        if not 0 <= state < STATE_COUNT:
            return

        def st(n):
            self.vcall(c, 27, n)

        if state == 0:
            if self.demon_due(c) and self.soul_is_demon_near(c):
                return st(0x18)
            if self.expired(c, 0xF4) or self.is_away_from_home(c):
                return st(1)
        elif state == 1:
            if self.demon_due(c) and self.soul_is_demon_near(c):
                return st(0x18)
            if self.move_to(c, self.vec(c + 0x104)) or self.expired(c, 0xF4):
                return st(0)
        elif state == 3:
            if not self.u32(c + 0x234):
                return st(0)
        elif state == 5:
            if self.is_not_rooted(c):
                return st(0)
        elif state in (0x12, 0x19):
            if not self.anim_flags(c, 0x10):
                return st(0x18)
        elif state in (0x14, 0x22):
            self.soul_dissolve(c)
        elif state == 0x17:
            if self.expired(c, 0xF4):
                return st(1)
        elif state == 0x18:
            if self.demon_due(c) and not self.soul_is_demon_near(c):
                return st(0)
        elif state == 0x1B:
            self.soul_thrown(c)
        elif state == 0x1D:
            if ev & 1:
                self.soul_burst_owned(c)

    def soul_dissolve(self, c):
        """States 0x14 and 0x22 (0x2a9b34-0x2a9ed8).

        Object flag 2 set: nothing.  n = s32 model_getSamplePointCount(slot 16).  n != 0:
        THREE particles, each ONE OWN DRAW d for the index d % n (signed), the point at the
        soul's position and s16 facing, a unit-ball velocity (OWN DRAWS) made flat and
        times 15, and particle_spawn only while the byte +0x231 is 0 (the draws are made
        either way).  Then, unless +0xf4 has expired or clip flag 0x80 is set, return.
        Otherwise, for every sample point i < n, TWO particles the same way (index i, no
        index draw).  Object flags |= 2; in 0x14 obj_delete, in 0x22 flags |= 0xb (of the
        word read before the |= 2) and obj_stopRunning."""
        if self.u32(c + 0xC) & 2:
            return
        n = s32(self.call('model_getSamplePointCount', self.vcall(c, 16)))
        if n:
            for _ in range(3):
                d = self.obj_rand(c)
                point = self.sample_point(c, self.vec(c + 0x10), self.s16(c + 0x38), c_rem(d, n))
                v = self.unit_ball(c)
                if not self.s8(c + 0x231):
                    self.spawn(point, v)
        if not self.expired(c, 0xF4) and not self.u16(c + 0x11A) & 0x80:
            return
        for i in range(max(n, 0)):
            point = self.sample_point(c, self.vec(c + 0x10), self.s16(c + 0x38), i)
            for _ in range(2):
                v = self.unit_ball(c)
                if not self.s8(c + 0x231):
                    self.spawn(point, v)
        flags = self.u32(c + 0xC)
        self.w32(c + 0xC, flags | 2)
        if self.s16(c + 0x232) == 0x14:
            self.call('obj_delete', c)
        else:
            self.w32(c + 0xC, flags | 0xB)
            self.call('obj_stopRunning', c)

    def soul_thrown(self, c):
        """State 0x1b, a thrown soul (0x2a9edc-0x2aa6a0).

        n = s32 model_getSamplePointCount(slot 16).  The throw matrix m =
        mat34_setPosRotZScale(scale +0xdc, copy of the position, s16(u16 facing + 0x5f40)),
        then mat34_rotateAxis(m, 0, 0x4fa0).  n != 0: THREE particles: ONE OWN DRAW d, the
        sample point d % n at (0, 0, 0) and facing -0x4000, through m, a unit-ball velocity
        (OWN DRAWS) flat times 15, particle_spawn (no +0x231 test).

        Velocity: with no handle +0x3cc, (cos16 f, sin16 f) x 400 and z = -80 (f the s16
        facing).  With one (its object T): the point T's position + 0.2 x (T+0x308,
        T+0x30c) (z unchanged); +0xb0 = 0.4; slot 26 (Creature_turnToward) (0, that
        point); then the direction to T (T re-read) normalised by rsqrt; velocity (cos16
        f, sin16 f) x 400 with the new facing and z = that direction's z x 400, held at
        most -60.

        Four sub-steps: position += velocity / 240 (y, z, x stored in that order); then
        for each player slot below g_numPlayers (re-read) with an object whose flag 8 is
        clear: the contact point 36 ahead of the soul (cos16/sin16 of the facing) at its
        z, against the player's position with z + height +0x20 x 0.5; when the distance is
        at most the two radii +0x1c added, damage_apply(player, soul, 100000, 0, 0,
        0x4000140, 0, 0; 10, 50), a hit, and no further player in this sub-step.

        After the four: no hit and +0xf4 not expired -> terrain_height(g_world, position;
        6.0); not strictly above the soul's z -> return.  Otherwise obj_delete, then for
        every sample point i < n the point at (0, 0, 0), facing -0x4000, through the OLD m
        (built before the move), and TWO particles each (no +0x231 test).  Own draws only;
        no shared draw of its own."""
        u32 = self.u32
        n = s32(self.call('model_getSamplePointCount', self.vcall(c, 16)))
        m = C.mat34_set_pos_rot_z_scale(u32(c + 0xDC), self.vec(c + 0x10), s16(self.u16(c + 0x38) + THROW_ROLL))
        m = C.mat34_rotate_axis(m, 0, THROW_PITCH)
        if n:
            for _ in range(3):
                d = self.obj_rand(c)
                point = self.sample_point(c, (ZERO, ZERO, ZERO), SAMPLE_FACING, c_rem(d, n))
                point = C.mat34_transform_point(m, point)
                self.spawn(point, self.unit_ball(c))
        handle = u32(c + 0x3CC)
        hit = 0
        if not handle:
            f = self.s16(c + 0x38)
            vel = [C.mul(C.cos16(f), F_400), C.mul(C.sin16(f), F_400), F_M80]
        else:
            t = u32(handle + 0xC)
            p = list(self.vec(t + 0x10))
            p[0] = C.add(p[0], C.mul(u32(t + 0x308), F_0_2))
            p[1] = C.add(p[1], C.mul(u32(t + 0x30C), F_0_2))
            self.w32(c + 0xB0, F_0_4)
            self.vcall(c, 26, 0, tuple(p))
            cx, cy, cz = self.vec(c + 0x10)
            t = u32(u32(c + 0x3CC) + 0xC)
            dx, dy, dz = C.sub(u32(t + 0x10), cx), C.sub(u32(t + 0x14), cy), C.sub(u32(t + 0x18), cz)
            size = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
            nz = C.mul(dz, C.rsqrt(ONE, size))
            f = self.s16(c + 0x38)
            vel = [C.mul(C.cos16(f), F_400), C.mul(C.sin16(f), F_400), C.mul(nz, F_400)]
            if C.lt(F_M60, vel[2]):
                vel[2] = F_M60
        for _step in range(4):
            sx, sy, sz = (C.mul(vel[k], F_STEP) for k in range(3))
            x, y, z = self.vec(c + 0x10)
            self.w32(c + 0x14, C.add(y, sy))
            self.w32(c + 0x18, C.add(z, sz))
            self.w32(c + 0x10, C.add(x, sx))
            j = 0
            while j < s32(u32(G_NUM_PLAYERS)):
                obj = u32((G_PLAYERS + j * REC_SIZE + REC_OBJ) & M32)
                if obj and not u32(obj + 0xC) & 8:
                    px, py, pz = self.vec(obj + 0x10)
                    pz = C.add(pz, C.mul(u32(obj + 0x20), HALF))
                    f = self.s16(c + 0x38)
                    ax = C.add(u32(c + 0x10), C.mul(C.cos16(f), F_36))
                    ay = C.add(u32(c + 0x14), C.mul(C.sin16(f), F_36))
                    az = u32(c + 0x18)
                    ex, ey, ez = C.sub(ax, px), C.sub(ay, py), C.sub(az, pz)
                    dist = C.sqrt(C.add(C.add(C.mul(ex, ex), C.mul(ey, ey)), C.mul(ez, ez)))
                    if C.le(dist, C.add(u32(c + 0x1C), u32(obj + 0x1C))):
                        self.call('damage_apply', obj, c, 100000, 0, 0, DAMAGE_FLAGS, 0, 0, F_10, F_50)
                        hit = 1
                        break
                j += 1
        if not hit and not self.expired(c, 0xF4):
            h = self.call('terrain_height', u32(G_WORLD), self.vec(c + 0x10), F_6)
            if not C.lt(u32(c + 0x18), h):
                return
        self.call('obj_delete', c)
        for i in range(max(n, 0)):
            point = self.sample_point(c, (ZERO, ZERO, ZERO), SAMPLE_FACING, i)
            point = C.mat34_transform_point(m, point)
            for _ in range(2):
                self.spawn(point, self.unit_ball(c))

    def soul_burst_owned(self, c):
        """State 0x1d on event bit 0 (0x2aa6a4-0x2aa8cc).

        n = s32 model_getSamplePointCount(slot 16).  For every sample point i < n: the
        point at (0, 0, 0), facing -0x4000, index i; while owned (+0x3c8) it is moved by
        A' = mul(inverse(B), A), A = creature_getAttachMatrix0(owner object), B =
        model_getAttachMatrix(class block +0x1c model, +0x114, 0; 1.0); then TWO particles
        (OWN DRAWS, no +0x231 test).  Object flags |= 2, obj_delete."""
        n = s32(self.call('model_getSamplePointCount', self.vcall(c, 16)))
        for i in range(max(n, 0)):
            point = self.sample_point(c, (ZERO, ZERO, ZERO), SAMPLE_FACING, i)
            owner = self.u32(c + 0x3C8)
            if owner:
                a = self.call('creature_getAttachMatrix0', self.u32(owner + 0xC))
                b = self.call('model_getAttachMatrix', self.u32(self.u32(c + 0x24) + 0x1C), c + 0x114, 0, ONE)
                b = C.mat34_invert(list(b))
                a = C.mat34_mul(b, list(a))
                point = C.mat34_transform_point(a, point)
            for _ in range(2):
                self.spawn(point, self.unit_ball(c))
        self.w32(c + 0xC, self.u32(c + 0xC) | 2)
        self.call('obj_delete', c)
