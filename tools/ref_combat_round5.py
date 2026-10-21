#!/usr/bin/env python3
"""ref_combat_round5.py - the combat bodies round 4 left open, on the same memory image.

A research tool, not game code.  Each method was written from the instructions at the
address in its docstring.  tools/difftest_combat_round5.py runs the original in
tools/ee_emu.py and compares it.  docs/spec/combat-round5.md is the prose.

This module only ADDS.  It does not change the round 1-4 APIs, their pinned vectors,
or the bodies their difftests compare.  New behaviour is a new function or a method
on a subclass.

Evidence, as in docs/combat-runtime.md: Executed means the original was run one function
at a time in the interpreter and agreed.  Observed means read at the address.  Nothing
here was run on a console, in PCSX2 or on the live rig.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_anim as A                            # noqa: E402
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_round4 as R4                  # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
from ref_creature import M32, s8, s16, s32      # noqa: E402

# Creature_processDamage 0x110d30.  The four pairs are the jal sites of math_cos16 /
# math_sin16.  The register value is what the jal receives, after its delay slot.
HIT_BIAS = 0x7FFF
GIB_SPAN_A, GIB_BIAS_A = 16000, 0xE0C0          # two chunks, 0x111b44 / 0x111b64
GIB_SPAN_B, GIB_BIAS_B = 40000, 0xB1E0          # four chunks, 0x111ce4 / 0x111d04
METAL_SCALE = 0x41200000                        # 10, the metal-spark and block-spark scale

# AntQueen_updateBank 0x238448 and AntQueen_fadeBankTracks 0x2385dc.
BANK_RATE = 0x3B000000                          # halfword +0x110, as a float, times this
BANK_LIMIT = 0x3F800000                         # clamp to ±1
BANK_SPRING = 0x3DB851EB
BANK_DAMP = 0x3F75C28F
BANK_ANGLE = 0x45081000
FADE_RATE = 0xBD088888                          # −1/30, stored into the track rate
BANK_CLIPS = (0xB4, 0x44, 0xBC, 0x4C)           # class-def words, tested in this order

# Soul_isDemonNear 0x2ab2b4.
DEMON_REACH = 0x43960000                        # 300
DEMON_LIMIT = 128
DEMON_FLAG = 8                                  # object flag: dead, skipped
DEMON_TYPEINFO = 0x3CA81C
RTTI_EQUALS = 0x3B1250
BOX_QUERY = 0x14A928

# MultiFireProjectile_run 0x2da2bc.  The particle is the definition the spawn is given.
P_VOLLEY = 0x8E5910
F_INV65536 = 0x37800000
F_EIGHT = 0x41000000
VOLLEY_LIFE = 0x259                             # age 601 ends the bolt
VOLLEY_PARTICLES = 10

# Slot 25 is vtable byte 200.  These are the return addresses of its jalr sites, so a
# recording stub can tell them from the other virtual calls in the same run.
SIGHT_RA = {
    'antqueen0': (0x23704C, 0x237088),
    'antqueen1': (0x2370E4,),
    'skeleton0': (0x2A69D8, 0x2A6A0C),
    'skeleton1': (0x2A6A64, 0x2A6A98),
}
FADE_SITE, BANK_SITE = 0x237028, 0x2370C0
DEMON_SITES = (0x2A99DC, 0x2A9A38)              # state 0, state 24
UPDATE_ACTIVE = 0x10C0F0                        # must return nonzero or the run returns


def hit_effect_angle(hit):
    """The angle at 0x110e60 / 0x110e80.

    lh of the hit halfword +0x2e0, then addiu 0x7fff in the cosine's delay slot.  The
    sine repeats that add before its own jal.  The sum is the register math_cos16 and
    math_sin16 receive.  Low 16 bits are the angle they consume."""
    return (s16(hit) + HIT_BIAS) & M32


def facing_angle(facing):
    """The angle at the metal sparks (0x11110c / 0x11111c) and at Player_blockSparks
    (0x1b97dc / 0x1b9800).

    lh of facing +0x38.  Nothing between that load and the jal writes a0, and the delay
    slot does not either.  The sine loads the halfword again.  The register is the
    sign-extended halfword."""
    return s16(facing) & M32


def gib_heading(hit, draw, span, bias):
    """One gib angle.  `draw` is the high 16 bits of one own-generator step.

    rem = draw mod span (unsigned).  The sum bias + rem is sign-extended from 16 bits
    (sll 16, sra 16) and added to the sign-extended hit halfword +0x2e0.  Two chunks use
    span 16000 and bias 0xe0c0.  Four use span 40000 and bias 0xb1e0.  The push uses an
    earlier draw from the same generator; this draw is only the angle."""
    return (s16(hit) + s16(bias + (draw % span))) & M32


def gib_angles(seed, hit):
    """The twelve register values, cosine then sine for each of the six chunks.

    Each chunk draws three times: the chunk variant, the push, then this angle.  The
    sine reuses the angle.  Returns (angles, seed after those draws)."""
    angles = []
    for count, span, bias in ((2, GIB_SPAN_A, GIB_BIAS_A), (4, GIB_SPAN_B, GIB_BIAS_B)):
        for _chunk in range(count):
            for _draw in range(2):
                seed = (seed * 0x19660D + 0x3C6EF35F) & M32
            seed = (seed * 0x19660D + 0x3C6EF35F) & M32
            heading = gib_heading(hit, seed >> 16, span, bias)
            angles.append(heading)
            angles.append(heading)
    return angles, seed


def skeleton_sight_forces(kind, first_hit):
    """Slot 25's a1 in Skeleton_run state 0 and state 1.

    The first call passes 0.  When that call returns 0 and the kind word +0x3d0 is 4,
    a second call passes 1.  Melee (any other kind) never makes the second call.
    `first_hit` means the first call returned nonzero."""
    if first_hit:
        return (0,)
    if kind == 4:
        return (0, 1)
    return (0,)


def soul_demon_due(frame, serial):
    """Whether Soul_run calls Soul_isDemonNear.

    (g_simFrame XOR the byte at +0x230) has its low nibble clear.  The load is a
    sign-extending byte load; the low nibble is the byte's own.  State 0 and state
    24 both use it.  The word at +0x44 is the object's own generator, not this byte."""
    return ((frame ^ (serial & 0xFF)) & 0xF) == 0


def antqueen_sight_forces(state, first_hit, tracks):
    """Slot 25's a1 in AntQueen_run state 0 and state 1.  Both passes are 0.

    State 0 calls twice, unless the first returned nonzero and the track count +0x118
    is strictly below 4: then it asks for state 3 instead of the second sight.  State 1
    calls once."""
    if state == 1:
        return (0,)
    if first_hit and s8(tracks) < 4:
        return (0,)
    return (0, 0)


class _Pose:
    def __init__(self, mats, count):
        self.mats = mats
        self.joint_count = count


class _AnimState:
    def __init__(self, pose):
        self.pose = pose


class QueenModel(RC.Model):
    """AntQueen_fadeBankTracks and AntQueen_updateBank.  Neither calls anything."""

    def _clips(self, creature):
        defin = self.u32(creature + 0x24)
        return [self.u32(defin + off) for off in BANK_CLIPS]

    def fade_bank_tracks(self, creature):
        """AntQueen_fadeBankTracks 0x2385dc (creature).

        The track count is the signed byte at +0x118.  At most that many tracks.  A
        track whose clip equals any of the four class-def words (+0xb4, +0x44, +0xbc,
        +0x4c) gets the rate 0xbd088888.  The weight is not written.  A count at or
        below 0 writes nothing."""
        count = self.s8(creature + 0x118)
        if count <= 0:
            return
        clips = self._clips(creature)
        for index in range(count):
            base = creature + 32 * index
            if self.u32(base + 0x11C) in clips:
                self.w32(base + 0x128, FADE_RATE)

    def update_bank(self, creature):
        """AntQueen_updateBank 0x238448 (creature).

        w = clamp(float(s16 at +0x110) * 0x3b000000, -1, 1).  With vel at +0x3e0 and
        pos at +0x3dc:

            delta = (w - vel) * 0x3db851eb
            pos = pos + delta
            vel = vel + pos
            pos = pos - pos * 0x3f75c28f
            halfword +0x3e4 = int(2*vel * 0x45081000)     toward zero

        The track count is the signed byte at +0x118, read after that store.  A count
        at or below 0 leaves the tracks alone.  Otherwise each track is the 32 bytes at
        +0x110, its clip at +12 and its weight at +20.  While 2*vel is strictly above
        +0, clips equal to class-def +0xb4 or +0x44 get 2*vel and clips equal to +0xbc
        or +0x4c get integer 0.  Otherwise the first pair gets integer 0 and the second
        gets neg.s of 2*vel (so +0 becomes -0).  The four words are tested in that
        order; the first match wins."""
        rate = C.mul(C.from_int(self.s16(creature + 0x110)), BANK_RATE)
        if C.lt(BANK_LIMIT, rate):
            rate = BANK_LIMIT
        if C.lt(rate, C.MINUS_ONE):
            rate = C.MINUS_ONE
        vel = self.u32(creature + 0x3E0)
        pos = self.u32(creature + 0x3DC)
        delta = C.mul(C.sub(rate, vel), BANK_SPRING)
        pos = C.add(pos, delta)
        vel = C.add(vel, pos)
        scaled = C.mul(pos, BANK_DAMP)
        twice = C.add(vel, vel)
        self.w32(creature + 0x3E0, vel)
        pos = C.sub(pos, scaled)
        angle = C.mul(twice, BANK_ANGLE)
        self.w32(creature + 0x3DC, pos)
        self.w16(creature + 0x3E4, C.to_int(angle))
        count = self.s8(creature + 0x118)
        if count <= 0:
            return
        clips = self._clips(creature)
        positive = C.lt(C.ZERO, twice)
        for index in range(count):
            base = creature + 0x110 + 32 * index
            clip = self.u32(base + 12)
            if clip == clips[0] or clip == clips[1]:
                self.w32(base + 20, twice if positive else 0)
            elif clip == clips[2] or clip == clips[3]:
                self.w32(base + 20, 0 if positive else C.neg(twice))


class SoulModel(RC.Model):
    """Soul_isDemonNear.  The box query, the typeinfo getter and the type test are
    call-outs.  The getter is not passed the object.  On the first list entry a0 is
    still the box minimum; after that it still holds the previous entry's type word.
    The object under test is the list entry."""

    def is_demon_near(self, creature, objects):
        """Soul_isDemonNear 0x2ab2b4 (creature) -> 0 or 1.

        The box is the creature's position ± 300 on every axis, capacity 128.  An empty
        list returns 0.  Each entry's vtable slot 0 is called, then Demon_typeinfo, then
        rtti_typeInfoEquals.  The first entry that compares equal and whose object flag
        8 is clear returns 1.  Flag 8 and a failed compare both move on.  `objects` is
        the list the box query wrote, already terminated; this method does not invent
        which objects the box holds."""
        x, y, z = self.vec(creature + 0x10)
        low = (C.sub(x, DEMON_REACH), C.sub(y, DEMON_REACH), C.sub(z, DEMON_REACH))
        high = (C.add(x, DEMON_REACH), C.add(y, DEMON_REACH), C.add(z, DEMON_REACH))
        self.call('world_collectObjectsInBox', low, high, DEMON_LIMIT)
        for obj in objects:
            info = self.call('Creature.v0', obj)
            demon = self.call('Demon_typeinfo')
            if self.call('rtti_typeInfoEquals', info, demon) and not self.u32(obj + 0xC) & DEMON_FLAG:
                return 1
        return 0


class ShieldPoints(R4.ShieldModel):
    """SpellHolyShield_absorb with the sample point executed instead of stubbed.

    holy_shield_absorb is unchanged and still stubs model_getSamplePoint.  This method
    is the same absorb with the point taken from the model's sample block and the pose
    the caster's animation state already holds."""

    def _sample_record(self, model, index):
        block = (model + 16 * self.u8(model + 0x24)) & M32
        count = s32(self.u32(block + 4))
        if index < 0 or index >= count:
            return None
        addr = (block + 0x20 + 8 * index + 16 * (index // 45)) & M32
        return tuple(self.s16(addr + 2 * col) for col in range(4))

    def _joint_state(self, state):
        pose = self.u32(state)
        if not pose:
            raise T.Unsupported('Holy Shield sample point with no pose on the caster')
        count = self.s16(pose + 8)
        if count <= 0:
            raise T.Unsupported('Holy Shield sample point pose has no joints')
        mats = []
        for joint in range(count):
            rows = []
            for row in range(3):
                base = pose + 0x10 + joint * 24 + row * 8
                rows.append([self.s16(base + 2 * col) for col in range(4)])
            mats.append(rows)
        return _AnimState(_Pose(mats, count))

    def holy_shield_sample(self, spell):
        """SpellHolyShield_absorb 0x2e8534, the sample point followed.

        Same as holy_shield_absorb, except model_getSamplePointCount and
        model_getSamplePoint run: scale 1, the caster's position and facing, the
        caster's animation state at +0x114, and the point index Spell_rand mod the
        count.  The pose pointer at that state must already be set; a zero pose would
        build one, and that build is not this method.  A count of 0 is still refused."""
        caster = self.u32(spell + 0xC)
        counted = self.vcall(caster, 16)
        block = (counted + 16 * self.u8(counted + 0x24)) & M32
        count = s32(self.u32(block + 4))
        if count == 0:
            raise T.Unsupported('SpellHolyShield_absorb divides by a sample count of 0')
        model = self.vcall(caster, 16)
        group = self.u32(spell + 0x24)
        self.call('particleGroup_begin', group)
        facing = self.s16(caster + 0x38) & M32
        pos = self.vec(caster + 0x10)
        state = self._joint_state((caster + 0x114) & M32)
        for _particle in range(0xF1):
            index = (self.spell_rand(spell) % count) & M32
            point = self._sample_record(model, index)
            position, _radius, _matrix = A.model_get_sample_point(
                None, C.ONE, pos, facing, state, point, False)
            ball = self._ball(spell)
            direction = tuple(C.mul(axis, R4.F_THIRTY_SEVEN) for axis in ball)
            self.call('particle_spawn', R4.P_HOLY, tuple(position), direction, C.ZERO)
        self.call('particleGroup_end', group)
        if C.le(self.u32(spell + 0x1C), C.ZERO):
            block = self.call('pool_new', 0xBC)
            if block:
                spot = list(pos)
                spot[2] = C.add(spot[2], R4.F_SIXTY)
                self.call('LightEffect_ctor', block, tuple(spot), 0, 0,
                          R4.F_SIXTY_FOUR, R4.F_SIXTY_FOUR, R4.F_ONE_TWENTY_FIVE, C.ZERO,
                          C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                          R4.F_ONE_TWENTY, R4.F_SIXTY, C.HALF, R4.F_COOLDOWN)
            self.w32(spell + 0x1C, R4.F_COOLDOWN)
        skill = self.u32(spell + 0x8)
        table = self.u32(skill + 0x60)
        this = (skill + self.s16(table + 8 * 10)) & M32
        stat = self.call('Skill.v10', this, 0, s8(self.u8(spell)) & M32)
        return C.mul(C.from_int(s32(stat)), R4.F_HUNDREDTH)


class VolleyModel(RC.Model):
    """MultiFireProjectile_run.  The trail, the move, the particle and the end are
    call-outs.  The own generator is the object's, at +0x44."""

    def _unit(self, obj):
        draw = C.mul(C.from_int(self.obj_rand(obj)), F_INV65536)
        return C.sub(C.add(draw, draw), C.ONE)

    def _ball(self, obj):
        while True:
            ball = [self._unit(obj) for _axis in range(3)]
            size = C.add(C.add(C.mul(ball[0], ball[0]), C.mul(ball[1], ball[1])),
                         C.mul(ball[2], ball[2]))
            if not C.lt(C.ONE, size):
                return ball

    def multifire_run(self, obj):
        """MultiFireProjectile_run 0x2da2bc (object).

        Nothing once +0x60 is set.  Otherwise, in order: one trail point at the
        position, age +0x6c increases by 1, obj_moveAndCollide with the velocity at
        +0x54.  Bit 0 of that result ends the bolt with reason 1.  An age of 601 or
        more ends it with reason 0.  Otherwise ten particles of definition 0x8e5910.
        Each one draws a unit ball from the object's own generator (three draws a try,
        again while the squared length is strictly above 1) and one further draw F.
        The velocity is the ball times 8.  The position is the object's position plus
        that velocity times F.  The speed argument is 0."""
        if self.u32(obj + 0x60):
            return
        self.call('trail_addPoint', self.u32(obj + 0x74), self.vec(obj + 0x10))
        age = (self.u32(obj + 0x6C) + 1) & M32
        self.w32(obj + 0x6C, age)
        result = self.call('obj_moveAndCollide', obj, self.vec(obj + 0x54)) & M32
        if result & 1:
            self.call('MultiFireProjectile_end', obj, result & 1)
            return
        if not s32(age) < VOLLEY_LIFE:
            self.call('MultiFireProjectile_end', obj, 0)
            return
        pos = self.vec(obj + 0x10)
        for _particle in range(VOLLEY_PARTICLES):
            ball = self._ball(obj)
            velocity = tuple(C.mul(axis, F_EIGHT) for axis in ball)
            fraction = C.mul(C.from_int(self.obj_rand(obj)), F_INV65536)
            spot = tuple(C.add(pos[i], C.mul(velocity[i], fraction)) for i in range(3))
            self.call('particle_spawn', P_VOLLEY, spot, velocity, C.ZERO)


MODELLED = {
    'AntQueen_fadeBankTracks': 0x2385DC,
    'AntQueen_updateBank': 0x238448,
    'Soul_isDemonNear': 0x2AB2B4,
    'SpellHolyShield_absorb_sample': 0x2E8534,
    'MultiFireProjectile_run': 0x2DA2BC,
}
