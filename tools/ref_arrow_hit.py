"""ref_arrow_hit.py - the two bodies a cold arrow's hit and an exploding arrow's explosion reach
that no earlier round executed: Creature_setEffectTimer 0x118950 and LightEffect_ctor 0x201bd8,
as a mixin for ref_arrow_run.Model (docs/spec/arrow-hit.md is the prose).

    Creature_setEffectTimer  0x118950  (creature, which, source; f12 seconds)       12 callers
    LightEffect_ctor         0x201bd8  (block, position*, follow, tag; f12..f19, 4 stack floats)
                                                                                     65 callers

The mixin needs the host model's u32 / w32 / w8 / w16 / wvec, `call` (for the call-outs and
the handle lists), `game_object_ctor` through ref_skills_a (ONE SHARED DRAW) and `s16`.
Pseudo-code in my own words; every constant carries the address of the instruction that loads it.
"""
import ref_core as C
from ref_creature import M32

CREATURE_SET_EFFECT_TIMER, LIGHT_EFFECT_CTOR = 0x118950, 0x201BD8
VT_LIGHTEFFECT = 0x50E198              # lui 0x51 / addiu -0x1e68 at 0x201cc0 / 0x201cd0
F_SIXTY = 0x42700000                   # lui 0x4270 at 0x201d80
ZERO, ONE = 0, 0x3F800000              # 0x201c4c, 0x118 9ac (mtc1 $zero)
EXECUTED = {'Creature_setEffectTimer': CREATURE_SET_EFFECT_TIMER, 'LightEffect_ctor': LIGHT_EFFECT_CTOR}
HIT_CALLS = ('Creature_setEffectTimer', 'LightEffect_ctor')


class HitMixin:
    def Creature_setEffectTimer(self, creature, which, source, seconds):
        """0x118950.  `which` below 5 (unsigned test at 0x118954) stores the seconds in the
        creature's timer `+0x340 + 4 which` (jump table 0x530180: 0..4 map in order to
        +0x340, +0x344, +0x348, +0x34c, +0x350).  Then, when 0.0 < seconds (`c.olt.s` at
        0x1189b0), the attacker list `+0x360` is cleared (handle_clear) and, when `source` is
        not null, linked to the source (handle_link(+0x360, source, source)).  Returns
        nothing; no seed."""
        if (which & M32) < 5:
            self.w32(creature + 0x340 + 4 * (which & M32), seconds)
        if C.lt(ZERO, seconds):
            self.call('handle_clear', creature + 0x360)
            if source:
                self.call('handle_link', creature + 0x360, source, source)

    def LightEffect_ctor(self, block, pos, follow, tag, *fl):
        """0x201bd8 (block, position, follow, tag; f12 f13 f14 f15 = the start colour (r g b a),
        f16 f17 f18 f19 = the end colour, stack: radius, end radius, a third value, life in
        seconds).  The light effect is a GameObject: ONE SHARED DRAW in GameObject_ctor.

        GameObject_ctor(block, pos, 0, 0); table +0x48 = 0x50e198; the light record at +0x4c:
        bytes +0x54 and +0x55 = 0; start colour as signed 16-bit truncations at +0x56..+0x5c and
        again at +0x5e..+0x64; radius +0x68 and +0x70, and 1 / radius^2 at +0x6c and +0x74;
        the third stack value at +0x78; the position at +0x7c..+0x87; light_link(+0x4c).
        +0x88 = 0, flags +0xc |= 3 (not solid: the victim finders skip it); a `follow` object
        is linked to +0x88.  Frames n = trunc(life x 60), 1 when not above 0; end frame +0xb4 =
        g_simFrame + n.  The start colour as floats at +0x8c..+0x98, the radius at +0xac;
        per-frame steps (end - start) / n: colour +0x9c..+0xa8, radius +0xb0.
        obj_runEveryFrame(block); +0xb8 = tag.  The run slot is LightEffect_run 0x1ee050."""
        f = list(fl)
        colour, end_colour, (radius, end_radius, third, life) = f[0:4], f[4:8], f[8:12]
        mul, sub, div = C.mul, C.sub, C.div
        SA_ctor = self.game_object_ctor_value
        SA_ctor(block, tuple(pos))
        w32, w16 = self.w32, self.w16
        light = block + 0x4C
        w32(block + 0x48, VT_LIGHTEFFECT)
        self.w8(light + 9, 0)
        self.wvec(block + 0x7C, tuple(pos))
        inverse_square = div(ONE, mul(radius, radius))
        w32(light + 0x28, inverse_square)
        w32(light + 0x2C, third)
        ints = [C.to_int(c) & 0xFFFF for c in colour]
        for base in (0xA, 0x12):
            for k in range(4):
                w16(light + base + 2 * k, ints[k])
        w32(light + 0x20, inverse_square)
        w32(light + 0x1C, radius)
        w32(light + 0x24, radius)
        self.w8(light + 8, 0)
        self.call('light_link', light)
        w32(block + 0x88, 0)
        w32(block + 0xC, self.u32(block + 0xC) | 3)
        if follow:
            self.call('handle_link', block + 0x88, follow, follow)
        n = C.to_int(mul(life, F_SIXTY))
        n = n if n > 0 else 1
        w32(block + 0x8C, colour[0])
        w32(block + 0x90, colour[1])
        w32(block + 0x94, colour[2])
        w32(block + 0x98, colour[3])
        w32(block + 0xAC, radius)
        w32(block + 0xB4, (self.u32(0x44FDCC) + n) & M32)
        inverse = div(ONE, C.from_int(n))
        w32(block + 0xB0, mul(sub(end_radius, radius), inverse))
        for k, off in enumerate((0x9C, 0xA0, 0xA4, 0xA8)):
            w32(block + off, mul(sub(end_colour[k], colour[k]), inverse))
        self.call('obj_runEveryFrame', block)
        w32(block + 0xB8, tag)

    def LightEffect_ctor_entry(self, block, pos, follow, tag, _a4, _a5, _a6, _a7, s0, s1, s2, s3, *f8):
        """The same body as the original is entered: `pos` is a pointer (read here), the four
        stack floats come before the eight register floats in the argument order of the
        difftest's one-call comparison (registers a4..a7 are unused)."""
        self.LightEffect_ctor(block, self.vec(pos), follow, tag, *(tuple(f8) + (s0, s1, s2, s3)))
