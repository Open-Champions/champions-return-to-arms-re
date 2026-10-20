#!/usr/bin/env python3
"""ref_combat_round4.py - combat bodies round 3 left open, on the same memory image.

A research tool, not game code.  Each method was written from the instructions at the
address in its docstring.  tools/difftest_combat_round4.py runs the original in
tools/ee_emu.py and compares calls, stored bytes, the shared seed and the result.
docs/spec/combat-round4.md is the prose.

This module subclasses the round-2 and round-3 models and only ADDS methods.  It does
not change those modules' APIs, pinned vectors, or the bodies their difftests compare.

Evidence, as in docs/combat-runtime.md: Executed means the original was run one function
at a time in the interpreter and agreed with the method.  Observed means read at the
address.  Nothing here was run on a console, in PCSX2 or on the live rig.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ranged as RR                  # noqa: E402
from ref_creature import M32, s8, s16, s32      # noqa: E402

# playerProjectile_run 0x1ba940, the potion tail.  Flight particles are definitions in
# the executable; the sounds are the strings res_find is given.
P_FLAME_A = 0x8658B0
P_FLAME_B = 0x865900
S_FIRE = 0x537B90                               # spel_we_firearrow_hit.anm
S_GAS = 0x537BB0                                # spel_cas_zomgas.anm
S_BLAST = 0x537BC8                              # spel_we_explarrow_hit.anm
G_LEVEL_TEXT = 0x44FE18                         # the level name strcasecmp reads
S_INNPIT = 0x535ED8                             # the name that skips the blast's damage

F_INV65536 = 0x37800000
F_FIVE = 0x40A00000
F_FLAME_B = 0x3FA3D70A
F_FLAME_BZ = 0x41C5C28F
F_TWENTY = 0x41A00000
F_SIX = 0x40C00000
F_THIRTY_SIX = 0x42100000
F_RISE = 0x416B3333                             # 14.699999, the blast ring
F_FORTY = 0x42200000
F_ONE_EIGHTY = 0x43340000
F_FORTY_EIGHT = 0x42400000
F_ONE_HUNDRED = 0x42C80000
F_SEVENTY_EIGHT = 0x429C0000
F_MINUS_THIRTY_TWO = 0xC2000000
F_ONE_SIXTY_EIGHT = 0x43280000
F_SIXTY = 0x42700000
F_ONE_TWENTY_EIGHT = 0x43000000
F_THIRD = 0x3EB33333                            # 0.34999999
D_FOUR = 0x4010000000000000                     # 4.0, the decal's height gate

MODELLED = {
    'playerProjectile_run': 0x1BA940,
}


class PotionModel(RR.RangedModel):
    """playerProjectile_run for kinds 1, 2 and 3.  Kinds 0 and 4 and above stay on
    RangedModel.  obj_moveAndCollide stays a call-out."""

    def __init__(self, mem, callbacks=None, external=()):
        if 'obj_moveAndCollide' not in external:
            external = tuple(external) + ('obj_moveAndCollide',)
        RR.RangedModel.__init__(self, mem, callbacks, external)

    def _shared_ball(self):
        """Three coordinates from the shared seed whose squared length is not strictly
        above 1.  Three draws a try: draw/65536, doubled, then minus 1."""
        while True:
            coords = []
            for _axis in range(3):
                unit = C.mul(C.from_int(self.draw()), F_INV65536)
                coords.append(C.sub(C.add(unit, unit), C.ONE))
            length = C.add(C.add(C.mul(coords[0], coords[0]), C.mul(coords[1], coords[1])),
                           C.mul(coords[2], coords[2]))
            if not C.lt(C.ONE, length):
                return coords

    def _up(self, z):
        """neg.s when the coordinate is strictly below +0.  -0 stays -0."""
        return C.neg(z) if C.lt(z, C.ZERO) else z

    def _flame_flight(self, this):
        """Kind 1, every run, before the spin.  Two particles from 0x8658b0, then one
        from 0x865900.  The vertical coordinate of the ball is forced upwards, then
        scaled.  The speed argument is 0.  The position is the projectile's own."""
        pos = self.vec(this + 0x10)
        for _count in range(2):
            x, y, z = self._shared_ball()
            z = self._up(z)
            direction = (C.mul(x, F_FIVE), C.mul(y, F_FIVE), C.mul(C.mul(z, F_FIVE), F_FIVE))
            self.call('particle_spawn', P_FLAME_A, pos, direction, C.ZERO)
        x, y, z = self._shared_ball()
        z = self._up(z)
        direction = (C.mul(x, F_FLAME_B), C.mul(y, F_FLAME_B),
                     C.mul(C.mul(z, F_FLAME_B), F_FLAME_BZ))
        self.call('particle_spawn', P_FLAME_B, pos, direction, C.ZERO)

    def _stone_sound(self, this):
        name = self._format(RR.S_STONE_HIT_THROWN)
        hit = self.call('res_find', self.text(RR.S_FX_LUMP_THROWN), name)
        self.call('sound_playOnObject', hit, this, RR.ONE)

    def _end_fire(self, this, owner):
        """Kind 1, once the projectile is done.  One sound, then five fires.  Each fire
        is a ball scaled by 20, dropped onto the ground under the projectile (radius 6),
        a LooseFire when the pool has a 0x54-byte block, and a decal one unit higher.
        The decal's angle is one shared draw, read as a signed halfword."""
        lump = self.call('res_find', self.text(RR.S_FX_LUMP_THROWN), self.text(S_FIRE))
        self.call('sound_playOnObject', lump, this, RR.ONE)
        origin = self.vec(this + 0x10)
        for _count in range(5):
            x, y, z = self._shared_ball()
            place = [C.add(origin[i], C.mul((x, y, z)[i], F_TWENTY)) for i in range(3)]
            ground = self.call('terrain_height', self.u32(RR.G_WORLD), origin, F_SIX)
            place[2] = C.add(ground, C.ONE)
            block = self.call('pool_new', 0x54)
            if block:
                self.call('LooseFire_ctor', block, tuple(place), owner)
            place[2] = C.add(place[2], C.ONE)
            self.call('decal_add', tuple(place), s16(self.draw()), 9, 0, F_THIRTY_SIX)

    def _end_gas(self, this, owner):
        """Kind 2.  pool_new(0x70); with a block, poisonGasSpell_ctor for 300 frames at
        radius 20, then the gas sound on the cloud, not on the projectile.  No block:
        no constructor and no sound."""
        block = self.call('pool_new', 0x70)
        if not block:
            return
        self.call('poisonGasSpell_ctor', block, self.vec(this + 0x10), 0x12C, 0x14, 0, owner, 5)
        lump = self.call('res_find', self.text(RR.S_FX_LUMP_THROWN), self.text(S_GAS))
        self.call('sound_playOnObject', lump, block, RR.ONE)

    def _end_blast(self, this, owner):
        """Kind 3.  The ring is 14.699999 above the projectile.  Radius damage is
        skipped when the level name matches 0x535ed8 ('innpit', case ignored).  A floor
        decal is made only when the ground under the projectile is strictly within 4 of
        its z, compared in the soft double arithmetic.  Then a light, when the pool has
        a 0xbc-byte block."""
        raised = list(self.vec(this + 0x10))
        raised[2] = C.add(raised[2], F_RISE)
        lump = self.call('res_find', self.text(RR.S_FX_LUMP_THROWN), self.text(S_BLAST))
        self.call('sound_playOnObject', lump, this, RR.ONE)
        self.call('fx_ringBurst', tuple(raised), RR.F_TWO)
        if self.cstr(G_LEVEL_TEXT).lower() != self.cstr(S_INNPIT).lower():
            self.call('world_damageInRadius', owner, self.vec(this + 0x10), 0x32, 0x40840, 0, 0,
                      F_FORTY, F_ONE_EIGHTY)
        spot = list(self.vec(this + 0x10))
        spot[2] = C.add(spot[2], C.ONE)
        ground = self.call('terrain_height', self.u32(RR.G_WORLD), self.vec(this + 0x10), F_SIX)
        gap = C.f2d(C.sub(ground, self.u32(this + 0x18)))
        if C.dcmp(gap, 0) < 0:
            gap = C.dsub(0, gap)
        if C.dcmp(gap, D_FOUR) < 0:
            self.call('decal_add', tuple(spot), s16(self.draw()), 9, 0, F_FORTY_EIGHT)
        block = self.call('pool_new', 0xBC)
        if block:
            self.call('LightEffect_ctor', block, self.vec(this + 0x10), 0, 0,
                      F_ONE_TWENTY_EIGHT, F_ONE_HUNDRED, F_SEVENTY_EIGHT, F_MINUS_THIRTY_TWO,
                      C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                      F_ONE_SIXTY_EIGHT, F_SIXTY, C.ONE, F_THIRD)

    def thrown_run(self, this):
        """playerProjectile_run 0x1ba940 while the kind byte +0x1ce is 1, 2 or 3.

        Kind 1 draws the shared seed inline (the constant 0x404464) for a flame on the
        way, two particles then one.  Kinds 2 and 3 do not.  The spin, the gravity
        8.999999 and obj_moveAndCollide are the same steps as a thrown weapon, except
        that a potion keeps the mover's result whole: bit 1 is not cleared, and the
        splash byte +0xcc is not folded in.

        A nonzero result stores 0 at +0xec.  A result of exactly 2 with +0xcc clear, or
        a result of exactly 1, plays the stone-hit sample.  Kinds 1, 2 and 3 do not
        spawn the stone effect.  While the frame is strictly below +0xec the run
        returns.  Otherwise the kind's ending runs and slot 1 is called with 3.

        Kind 1's ending is five LooseFire objects and five decals.  Kind 2's is one
        poisonGasSpell (300 frames, radius 20, damage 5) when a block is returned.
        Kind 3's is a ring, radius damage unless the level is innpit, a decal when the
        ground is within 4, and a light."""
        kind = s8(self.u8(this + 0x1CE))
        if kind not in (1, 2, 3):
            return RR.RangedModel.thrown_run(self, this)
        if kind == 1:
            self._flame_flight(this)
        spin = s16(self.u16(this + 0x1CC))
        if not spin < -0x1387:
            self.w16(this + 0x1CC, spin - 0xC8)
        # libc_sprintf builds the stone-hit name here.  It is the C library, so it is not
        # a recorded call; the sample is that text when a result of 1 or 2 plays it.
        self.w32(this + 0x1B8, C.sub(self.u32(this + 0x1B8), RR.F_GRAVITY))
        res = self.call('obj_moveAndCollide', this, self.vec(this + 0x1B0)) & M32
        if res:
            self.w32(this + 0xEC, 0)
            if res == 2:
                if not s8(self.u8(this + 0xCC)):
                    self._stone_sound(this)
            elif res == 1:
                spot = list(self.vec(this + 0x10))
                ground = self.call('terrain_height', self.u32(RR.G_WORLD), self.vec(this + 0x10),
                                   self.u32(this + 0x1C))
                spot[2] = C.add(ground, RR.F_FIVE)
                self._stone_sound(this)
        if s32(self.u32(RC.G_SIM_FRAME)) < s32(self.u32(this + 0xEC)):
            return
        owner = self.handle_obj(this + 0x1C8)
        if kind == 1:
            self._end_fire(this, owner)
        elif kind == 2:
            self._end_gas(this, owner)
        else:
            self._end_blast(this, owner)
        self.vcall(this, 1, 3)
