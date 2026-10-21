"""ref_staticfire.py - StaticFire_ctor 0x2c5240 with the two bodies under it that run for real:
StaticFire_initCommon 0x2c5814 and the particle push 0x2c6aa8, as a mixin for ref_arrow_run.Model
(docs/spec/staticfire-ctor.md is the prose).

    StaticFire_ctor         0x2c5240  (fire, position*, life, owner, flag; f12 size, f13 scale)
    StaticFire_initCommon   0x2c5814  (fire)
    StaticFire_pushParticles 0x2c6aa8 (fire, facing)       (my name; unnamed in the symbol table)

The mixin needs the host model's u8/u32/s8/s16, w8/w16/w32/wvec, vec, call, obj_rand,
type_of / same_type and `game_object_ctor_value` (GameObject_ctor: ONE SHARED DRAW).
Pseudo-code in my own words; every constant carries the address of the instruction that loads it.
"""
import ref_core as C
from ref_creature import M32, s16, s32

STATICFIRE_CTOR, STATICFIRE_INIT_COMMON, STATICFIRE_PUSH = 0x2C5240, 0x2C5814, 0x2C6AA8
VT_STATICFIRE = 0x50DA38                    # lui 0x51 at 0x2c52ac, addiu -0x25c8 at 0x2c52c0
S_SMOKEBOMB = 0x54E768                      # the tag string mem_allocTagged is given, 0x2c58ec/0x2c58f4
G_WORLD = 0x44FDC8                          # 0x2c58bc / 0x2c58c0
ZERO, ONE = 0, 0x3F800000
F_36, F_30 = 0x42100000, 0x41F00000         # 0x2c52b8, 0x2c53d0
F_120, F_FALLOFF = 0x42F00000, 0x3891A2B3   # 0x2c52fc; 0x2c5308 / 0x2c530c
F_16, F_25000 = 0x41800000, 0x46C35000      # 0x2c5818; 0x2c5854 / 0x2c5858
F_600, F_480, F_240 = 0x44160000, 0x43F00000, 0x43700000      # 0x2c5910, 0x2c5920, 0x2c5940
F_PUSH_SCALE = 0x406EEEEE                   # 0x2c6af0 / 0x2c6af4 (about 3.7333)
EXECUTED = {'StaticFire_ctor': STATICFIRE_CTOR, 'StaticFire_initCommon': STATICFIRE_INIT_COMMON,
            'StaticFire_pushParticles': STATICFIRE_PUSH}


class FireMixin:
    # =====================================================================================
    def staticfire_ctor(self, fire, pos, life, owner, flag, size, scale):
        """StaticFire_ctor 0x2c5240.  `pos` points at three floats, `life` is the frames the
        fire burns, `owner` the creature (stored as a plain word, no handle), `flag` non-zero
        for a fire that does not own its light, `size` and `scale` the two floats.

        1. GameObject_ctor(fire, copy of pos, 0, 0): ONE SHARED DRAW; table +0x48 = 0x50da38.
        2. The light position +0xb0..+0xbb = (x + 0.0, y, z + 36.0); the light record at +0x80:
           byte +0x89 = 0; radius +0x9c and +0xa4 = 120.0, falloff +0xa0 and +0xa8 =
           0x3891a2b3, +0xac = 1.0; colour (255, 128, 0, 0) as 16-bit values at +0x8a..+0x90 and
           again at +0x92..+0x98; byte +0x88 = 0; light_link(+0x80).
        3. Bytes +0x6f and +0x70 = 0; StaticFire_initCommon(fire).
        4. +0x7c = life; +0x68 = +0x68 x scale (the scale applies to initCommon's 25,000.0);
           +0x50 = size (over initCommon's 480.0); +0x4a8 = owner; byte +0x6e = 1;
           flag non-zero: light_unlink(+0x80).
        5. world_collectObjectsInBox(position -/+ 30, capacity 128): every object but the fire
           itself counts (even a non-fire); without the flag each one that is a StaticFire
           (slot 0's type-info getter against StaticFire_typeinfo, rtti_typeInfoEquals) is
           first light_unlink(object + 0x80)'d.  Four or more objects halve the life +0x7c
           (signed, rounded toward zero)."""
        x, y, z = self.vec(pos)
        self.game_object_ctor_value(fire, (x, y, z))
        w8, w16, w32 = self.w8, self.w16, self.w32
        w32(fire + 0x48, VT_STATICFIRE)
        self.wvec(fire + 0xB0, (C.add(x, ZERO), y, C.add(z, F_36)))
        light = fire + 0x80
        w8(light + 9, 0)
        w32(light + 0x24, F_120)
        w32(light + 0x28, F_FALLOFF)
        w32(light + 0x2C, ONE)
        w16(light + 0x12, 0xFF)
        w16(light + 0x14, 0x80)
        w32(light + 0x1C, F_120)
        w32(light + 0x20, F_FALLOFF)
        w16(light + 0xA, 0xFF)
        w16(light + 0xC, 0x80)
        for k in (0xE, 0x10, 0x16, 0x18):
            w16(light + k, 0)
        w8(light + 8, 0)
        self.call('light_link', light)
        w8(fire + 0x6F, 0)
        w8(fire + 0x70, 0)
        self.staticfire_init_common(fire)
        w32(fire + 0x7C, life)
        w32(fire + 0x68, C.mul(self.u32(fire + 0x68), scale))
        w32(fire + 0x50, size)
        w32(fire + 0x4A8, owner)
        w8(fire + 0x6E, 1)
        if flag & M32:
            self.call('light_unlink', light)
        here = self.vec(fire + 0x10)
        low = tuple(C.sub(v, F_30) for v in here)
        high = tuple(C.add(v, F_30) for v in here)
        found = self.call('world_collectObjectsInBox', low, high, 0x80) or ()
        count = 0
        for other in found:
            if other == fire:
                continue
            if not flag & M32:
                if self.same_type(self.type_of(other), self.call('StaticFire_typeinfo')):
                    self.call('light_unlink', other + 0x80)
            count += 1
        if count >= 4:
            half = s32(self.u32(fire + 0x7C))
            w32(fire + 0x7C, (half + (1 if half < 0 else 0)) >> 1)

    # =====================================================================================
    def staticfire_init_common(self, fire):
        """StaticFire_initCommon 0x2c5814 (fire), shared with StaticFire_ctor2.

        +0x1c = 16.0; s16 +0x38 = 0; byte +0x28 = 60; s16 +0x78 and +0x7a = 0.  ONE OWN DRAW d
        (GameObject_rand); flags +0xc |= 0x40001; +0x68 = 25,000.0; +0x7c = -1; +0x54 and +0x64 =
        1.0; byte +0x6c = 0; +0x4c = float(d mod 300 unsigned).  StaticFire_pushParticles(fire,
        s16 +0x38) (one more own draw, see there).  obj_runEveryFrame; obj_addToAlwaysDraw;
        path_blockNodes(g_world, copy of the position; radius +0x1c).  Byte +0x6f non-zero:
        s16 +0x76 = 250, +0x4a4 = mem_allocTagged(0x9c4, tag, fire + 0xbc), +0x50 = 600.0.
        Otherwise s16 +0x76 = 100, +0x4a4 = fire + 0xbc (the buffer inside the object),
        +0x50 = 480.0, or 240.0 when byte +0x70 is non-zero."""
        w8, w16, w32 = self.w8, self.w16, self.w32
        w32(fire + 0x1C, F_16)
        w16(fire + 0x38, 0)
        w8(fire + 0x28, 0x3C)
        w16(fire + 0x78, 0)
        w16(fire + 0x7A, 0)
        d = self.obj_rand(fire) & M32
        w32(fire + 0x68, F_25000)
        w32(fire + 0xC, self.u32(fire + 0xC) | 0x40001)
        w32(fire + 0x7C, M32)
        w32(fire + 0x54, ONE)
        w32(fire + 0x64, ONE)
        facing = self.s16(fire + 0x38)
        w8(fire + 0x6C, 0)
        w32(fire + 0x4C, C.from_int(d % 300))
        self.staticfire_push(fire, facing)
        self.call('obj_runEveryFrame', fire)
        self.call('obj_addToAlwaysDraw', fire)
        self.call('path_blockNodes', self.u32(G_WORLD), self.vec(fire + 0x10), self.u32(fire + 0x1C))
        if self.s8(fire + 0x6F):
            w16(fire + 0x76, 250)
            w32(fire + 0x4A4, self.call('mem_allocTagged', 0x9C4, S_SMOKEBOMB, fire + 0xBC))
            w32(fire + 0x50, F_600)
        else:
            w32(fire + 0x50, F_480)
            w16(fire + 0x76, 100)
            w32(fire + 0x4A4, (fire + 0xBC) & M32)
            if self.s8(fire + 0x70):
                w32(fire + 0x50, F_240)

    # =====================================================================================
    def staticfire_push(self, fire, facing):
        """0x2c6aa8 (fire, facing).  The unit vector (cos, sin) of the 16-bit facing (renormalised
        by rsqrt.s of cos^2 + sin^2), scaled by 3.7333 and truncated: s16 +0x72 = the cos part,
        +0x74 = the sin part.  ONE OWN DRAW r.  Then, from the particle index +0x7a until it
        meets +0x78 (wrapping to 0 at the ring size +0x76): the particle record at
        (+0x4a4) + 10 x index gets +0x72 added to its u16 at +6 and +0x74 to the u16 at +8 when
        (index & 3) == (r & 3).  The ring stays unchanged otherwise."""
        index = self.s16(fire + 0x7A)
        c, s = C.cos16(facing), C.sin16(facing)
        n = C.add(C.mul(c, c), C.mul(s, s))
        inv = C.rsqrt(ONE, n)
        s2, c2 = C.mul(s, inv), C.mul(c, inv)
        self.w16(fire + 0x74, C.to_int(C.mul(s2, F_PUSH_SCALE)) & 0xFFFF)
        self.w16(fire + 0x72, C.to_int(C.mul(c2, F_PUSH_SCALE)) & 0xFFFF)
        r = self.obj_rand(fire) & 3
        if index == self.s16(fire + 0x78):
            return
        while True:
            entry = (self.u32(fire + 0x4A4) + 10 * index) & M32
            if index & 3 == r:
                self.w16(entry + 6, (self.u16(entry + 6) + self.u16(fire + 0x72)) & 0xFFFF)
                self.w16(entry + 8, (self.u16(entry + 8) + self.u16(fire + 0x74)) & 0xFFFF)
            index += 1
            if index == self.s16(fire + 0x76):
                index = 0
            if index == self.s16(fire + 0x78):
                return
