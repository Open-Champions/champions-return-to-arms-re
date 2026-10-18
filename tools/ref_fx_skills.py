#!/usr/bin/env python3
"""ref_fx_skills.py - the visual recipes of the skill and effect classes of Champions:
Return to Arms (SLUS_209.73, US v2.00): which effect primitives each class calls, in which
phase, from which generator, and with which arguments (docs/effects.md section 11).

A research tool, not game code.  Standard library only; no game data is embedded.

Three parts.

1. CALLOUTS - how the call-outs of the skill models become effect primitives.
   tools/ref_skills_a.py, _b.py and _c.py (and tools/ref_arena_monsters.py) already model
   140 of the 161 skill-file functions that call an effect primitive, and their
   differential tests run them against the original, call for call: every particle_spawn,
   LightEffect_ctor, glow_add, trail_create ... is made there with its exact arguments
   (canonical form: integers as unsigned 32-bit, floats as 32-bit patterns, a vector as a
   tuple of three patterns).  CALLOUTS names each such call-out, the primitive address and
   the meaning of each canonical argument, and to_primitive() turns one recorded call into
   a FxCall record a renderer can execute (tools/ref_particles.py, tools/ref_lighting.py,
   tools/ref_fx_render.py are the primitives' own contracts).

2. RECIPES - per effect class: phase (cast / run / draw / event), the original function,
   where its executed model lives (module.method), the primitives it calls and the
   generator its random placement draws from.  recipe(name) and classes() read it.

3. Models of the 21 functions the skill models did not have (the draw slots that queue
   glow sprites, and the run functions of StaticFire, DiseaseCloud, FireStormFlare,
   MultiFireProjectile, SpellPlanarSteelEffect, SpellHornOmenEffect, SpellArena and
   Pustule).  Model below is ref_skills_c.Model with these methods added; it sees the game
   exactly as that module does (a memory image, callbacks for everything outside, R5900
   float arithmetic from tools/ref_core.py).  tools/difftest_fx_skills.py runs each of them
   against the original under tools/ee_emu.py.

Constants.  Counts, timings, angle rates, offsets and glow colours are code constants and
are written here as the instructions hold them (round 1 did the same for fx_spawn and
Fire).  Particle definitions and LightEffect colours / radii are named by address or read
from the caller's memory; tools/fx_skill_recipes.py prints them from your own executable.
"""
import os
import sys
from collections import namedtuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_c as SC                       # noqa: E402
from ref_skills_c import *                      # noqa: E402,F401,F403 - the difftest rig reads these names
from ref_creature import Ext, M32, s16, s32     # noqa: E402

G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_NUM_PLAYERS = 0x4D8AE0                        # s32 number of players in the session
ZERO, ONE = C.ZERO, C.ONE
F_2M16 = RC.F_2M16                              # 1 / 65536

# glow textures (resource words; docs/effects.md section 6 and round-2 item 7)
G_GLOW_TEX_A = 0x4F848C                         # light-chunk / summon glow
G_GLOW_TEX_B = 0x4F8494                         # fire-arrow glow
G_GLOW_TEX_C = 0x4F8498                         # shock / holy-strike glow
G_GLOW_TEX_RES = 0x44FE04                       # the resurrect ring
G_GLOW_TEX_FIRE = 0x4F84A0                      # StaticFire flames
G_GLOW_TEX_FIRE_DIM = 0x4F84A4                  # StaticFire flames below the fade height

# ---------------------------------------------------------------------------------------
# 1. Call-outs -> primitives
# ---------------------------------------------------------------------------------------
Callout = namedtuple('Callout', 'addr primitive fields note')
FxCall = namedtuple('FxCall', 'primitive fields')

CALLOUTS = {
    'particle_spawn': Callout(0x18F3F8, 'particle', ('definition', 'pos', 'vel', 'backdate'),
                              'ref_particles.ParticleSystem.spawn(def, pos, vel, backdate); definition by address'),
    'glow_add': Callout(0x18FC78, 'glow', ('pos', 'r', 'g', 'b', 'a', 'texture', 'angle', 'flags', 'bias', 'size'),
                        'docs/effects.md 6; texture is the resource word the code loaded'),
    'LightEffect_ctor': Callout(0x201BD8, 'light_effect',
                                ('block', 'pos', 'follow', 'flag', 'c0', 'c1', 'c2', 'c3', 'd0', 'd1', 'd2', 'd3',
                                 'radius', 'radius_end', 'floor', 'seconds'),
                                'ref_lighting.LightEffect; a GameObject: ONE SHARED DRAW in its constructor'),
    'trail_create': Callout(0x190FF8, 'trail', ('row', 'width', 'flags', 'r', 'g', 'b', 'a', 'lifetime'),
                            'docs/effects.md 7: (lifetime s; row, width, flags, rgba) -> handle'),
    'trail_addPoint': Callout(0x192550, 'trail_point', ('handle', 'pos'), 'stamp = trail clock + 1'),
    'trail_release': Callout(0x192800, 'trail_release', ('handle',), ''),
    'beam_create': Callout(0x193088, 'beam', ('from', 'to', 'width', 'depth', 'rgba', 'jitter', 'scale'), ''),
    'beam_update': Callout(0x1933C8, 'beam_update', ('handle', 'from', 'to', 'alpha', 'width'), ''),
    'decal_add': Callout(0x19F110, 'decal', ('pos', 'angle', 'type', 'grow', 'size'), 'docs/effects.md 8'),
    'fx_spawn': Callout(0x1EF270, 'fx_spawn', ('id', 'pos'), 'docs/effects.md 10, tools/ref_fx_recipes.py'),
    'fx_ringBurst': Callout(0x1F3D00, 'ring_burst', None, 'arguments as the model records them'),
    'fx_impactPuffNearCamera': Callout(0x1FC150, 'puff', ('pos', 'step', 'mode', 'radius', 'size'), ''),
    'fx_emitFromModelVerts': Callout(0x1EB1E8, 'model_verts', ('object', 'count', 'definition', 'a', 'b', 'speed'), ''),
    'fx_modelParticlesNearCamera_1f61c0': Callout(0x1F61C0, 'model_particles_light', None, ''),
    'fx_modelParticlesNearCamera_1f5210': Callout(0x1F5210, 'model_particles', None, ''),
    'particleGroup_create': Callout(0x18E880, 'group_create', (), '-> handle'),
    'particleGroup_begin': Callout(0x18E958, 'group_begin', ('handle',), ''),
    'particleGroup_end': Callout(0x18E9A0, 'group_end', ('handle',), ''),
    'particleGroup_setMatrix': Callout(0x18E9E8, 'group_matrix', ('handle', 'matrix'), ''),
    'particleGroup_free': Callout(0x18EA90, 'group_free', ('handle',), ''),
    'light_link': Callout(0x148AF8, 'light_link', ('light',), 'the class\'s own light node (ref_lighting.LightNode)'),
    'light_relink': Callout(0x14A528, 'light_relink', ('light',), 'the light follows its new position'),
    'light_unlink': Callout(0x14A4F0, 'light_unlink', ('light',), ''),
}


def _float(raw):
    return C.to_float(raw & M32)


def to_primitive(name, args):
    """One recorded call-out (name, canonical args) -> FxCall, or None when the name is
    not an effect primitive.  Float patterns become Python floats, vectors tuples of
    floats; integers stay as they are.  The argument order of the canonical form is the
    integer registers a0.., then f12.., then stack words (ref_creature.Ext)."""
    out = CALLOUTS.get(name)
    if out is None:
        return None
    if out.fields is None:
        return FxCall(out.primitive, {'args': tuple(args)})
    a = list(args)
    if name == 'particle_spawn':
        values = (a[0], tuple(_float(v) for v in a[1]), tuple(_float(v) for v in a[2]), _float(a[3]))
    elif name == 'glow_add':
        values = (tuple(_float(v) for v in a[0]),) + tuple(a[1:8]) + (_float(a[8]), _float(a[9]))
    elif name == 'LightEffect_ctor':
        values = (a[0], tuple(_float(v) for v in a[1]), a[2], a[3]) + tuple(_float(v) for v in a[4:16])
    elif name == 'trail_create':
        values = tuple(a[0:7]) + (_float(a[7]),)
    elif name == 'trail_addPoint':
        values = (a[0], tuple(_float(v) for v in a[1]) if isinstance(a[1], tuple) else a[1])
    elif name == 'decal_add':
        values = (tuple(_float(v) for v in a[0]), a[1], a[2], a[3], _float(a[4]))
    elif name == 'fx_spawn':
        values = (a[0], tuple(_float(v) for v in a[1]))
    else:
        values = tuple(tuple(_float(x) for x in v) if isinstance(v, tuple) else v for v in a)
    return FxCall(out.primitive, dict(zip(out.fields, values)))


def effects_of(calls):
    """The effect primitives of a recorded call stream, in order."""
    return [fx for fx in (to_primitive(name, args) for name, args in calls) if fx is not None]


# ---------------------------------------------------------------------------------------
# 2. Recipes per class (filled in below the models)
# ---------------------------------------------------------------------------------------
Phase = namedtuple('Phase', 'phase function addr model primitives rng note')
RECIPES = {}


def add_recipe(cls, phase, function, addr, model, primitives, rng='', note=''):
    RECIPES.setdefault(cls, []).append(Phase(phase, function, addr, model, tuple(primitives.split()), rng, note))


def recipe(cls):
    return list(RECIPES.get(cls, ()))


def classes():
    return sorted(RECIPES)


# ---------------------------------------------------------------------------------------
# 3. Models of the functions the skill models did not have
# ---------------------------------------------------------------------------------------
EXTERNALS = dict(SC.EXTERNALS)
EXTERNALS.update({
    'isNearView': Ext(0x1E77C0, 'v', 1, 'i', '(position; radius) -> 1 when the camera focus is near (per machine)'),
    'trail_addPoint': Ext(0x192550, 'iv', 0, 'n', '(handle, point)'),
    'trail_release': Ext(0x192800, 'i', 0, 'n', '(handle)'),
})
MODELLED = dict(SC.MODELLED)
DRAW_MODELLED = {}                              # name -> address, the functions of part 3


def shape_result(name, args, ret=0, fret=0, outs=None):
    """ref_skills_c.shape_result over this module's EXTERNALS."""
    saved = SC.EXTERNALS
    SC.EXTERNALS = EXTERNALS
    try:
        return SC.shape_result(name, args, ret, fret, outs)
    finally:
        SC.EXTERNALS = saved


def _register(name, addr):
    MODELLED[name] = addr
    DRAW_MODELLED[name] = addr


def _from_uint(v):
    """cvt.s.w of an unsigned value, the compiler's way: halve (keeping the low bit) and
    double when bit 31 is set."""
    v &= M32
    if v < 0x80000000:
        return C.from_int(v)
    half = C.from_int((v >> 1) | (v & 1))
    return C.add(half, half)


def _angle_shift(word, left):
    """(u16 word << left) >> 16, arithmetic: an angle built from the frame counter."""
    return s32(((word & 0xFFFF) << left) & M32) >> 16


class Calls:
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)


class Draws:
    """The draw slots that queue glow sprites (GameObject slot 5, Spell slot 3).  They run
    once per rendered frame; nothing here changes game state."""

    def shock_draw(self, obj):
        """ShockProjectile_draw 0x2c4e64.  t = min(1, (expiry +0x58 - frame + 300) / 30)
        (no lower bound); one glow at the position: grey 0x80, alpha int(128 t), size
        int(15152 t + sin16(frame mod 0x8000 x 0x1dd7) x int(15152 t x 0.195006)),
        bias 0, texture *0x4f8498, angle (frame << 26) >> 16, flags 1 (turned quad)."""
        u32 = self.u32
        frame = s32(u32(G_SIM_FRAME))
        t = C.mul(C.from_int(s32(u32(obj + 0x58)) - frame + 300), 0x3D088888)
        if C.lt(ONE, t):
            t = ONE
        rem = frame - int(frame / 0x8000) * 0x8000
        s = C.sin16((rem * 0x1DD7) & M32)
        big = C.mul(t, 0x466CC000)
        alpha = C.to_int(C.mul(t, 0x43000000))
        k = C.from_int(C.to_int(C.mul(big, 0x3E47AFA7)))
        size = C.from_int(C.to_int(C.add(big, C.mul(s, k))))
        angle = _angle_shift(u32(G_SIM_FRAME), 26)
        self.call('glow_add', self.vec(obj + 0x10), 0x80, 0x80, 0x80, alpha, u32(G_GLOW_TEX_C), angle, 1, ZERO, size)

    def firearrow_draw(self, obj):
        """FireArrowProjectile_draw 0x2d67e8: one glow at the arrow, size radius +0x1c x
        1408, bias 10, colour (0x93, 0x62, 0x49), alpha 0x49, texture *0x4f8494, angle 0,
        flags 6 (additive, second pass)."""
        size = C.mul(self.u32(obj + 0x1C), 0x44B00000)
        self.call('glow_add', self.vec(obj + 0x10), 0x93, 0x62, 0x49, 0x49, self.u32(G_GLOW_TEX_B), 0, 6,
                  0x41200000, size)

    def holystrike_draw(self, obj):
        """HolyStrike_draw 0x2ecd90: one glow one unit off the object sideways (the unit
        vector (dir.y, -dir.x, 0) of the direction +0x6c, +0x70) and one unit up; size
        5000 + 250 sin16(frame << 10), bias 5, colour (250, 200, 100), alpha 0x80, texture
        *0x4f8498, angle (frame << 25) >> 16, flags 3."""
        u32 = self.u32
        d0, d1, d2 = u32(obj + 0x70), C.neg(u32(obj + 0x6C)), ZERO
        length2 = C.add(C.add(C.mul(d0, d0), C.mul(d1, d1)), C.mul(d2, d2))
        r = C.rsqrt(ONE, length2)
        n = (C.mul(d0, r), C.mul(d1, r), C.mul(d2, r))
        p = self.vec(obj + 0x10)
        point = (C.add(C.add(n[0], ZERO), p[0]), C.add(C.add(n[1], ZERO), p[1]), C.add(C.add(n[2], ONE), p[2]))
        s = C.sin16((u32(G_SIM_FRAME) << 10) & M32)
        size = C.add(C.mul(s, 0x437A0000), 0x459C4000)
        angle = _angle_shift(u32(G_SIM_FRAME), 25)
        self.call('glow_add', point, 0xFA, 0xC8, 0x64, 0x80, u32(G_GLOW_TEX_C), angle, 3, 0x40A00000, size)

    def badger_draw(self, spell):
        """SpellSummonBadger_draw 0x311034, Spell slot 3.  Needs the badger (handle +0x18).
        f = +0x1c, folded above 1 to 1 - (f - 1) and clamped at 0; nothing when f <= 0.
        One glow at every sample point of the badger's model (slot 16 gives the model):
        size = the second output's x + 250 sin16(frame << 10), bias 12, colour (0x54, 0xc0,
        0x33), alpha int(65 f), texture *0x4f848c, angle (frame << 22) >> 16, flags 7."""
        u32 = self.u32
        node = u32(spell + 0x18)
        if not node:
            return
        badger = u32(node + 0xC)
        if not badger:
            return
        f = u32(spell + 0x1C)
        if C.lt(ONE, f):
            f = C.sub(ONE, C.sub(f, ONE))
            if C.lt(f, ZERO):
                f = ZERO
        if C.le(f, ZERO):
            return
        count = s32(self.call('model_getSamplePointCount', self.vcall(badger, 16)))
        at = self.visual_pos(badger)
        index = 0
        while index < count:
            model = self.vcall(badger, 16)
            point, extra = self.call('model_getSamplePoint', model, badger + 0x114, tuple(at), self.s16(badger + 0x38),
                                     index, 1, 0, u32(badger + 0xDC))
            index += 1
            s = C.sin16((u32(G_SIM_FRAME) << 10) & M32)
            size = C.add(extra[0], C.mul(s, 0x437A0000))
            alpha = C.to_int(C.mul(f, 0x42820000))
            angle = _angle_shift(u32(G_SIM_FRAME), 22)
            self.call('glow_add', point, 0x54, 0xC0, 0x33, alpha, u32(G_GLOW_TEX_A), angle, 7, 0x41400000, size)

    def resurrect_draw(self, spell):
        """SpellResurrect_draw 0x312f48, Spell slot 3.  Only with one player in the session
        (*0x4d8ae0 == 1).  f = 0 while +0x20 is 0, else min(1, (frame - +0x6c, unsigned)
        / 60).  Thirteen glows on a ring of radius int(100 f) + 15 around the owner (+0x18),
        116 above its position; angles start at frame x 0x75 and step 0x13b1 (16 bits),
        (x, y) = owner + (sin16, cos16) x radius; size 5000, bias 10, colour (0x6f, 0x38,
        0x28), alpha int((1 - f) x 128), texture *0x44fe04, angle 0, flags 2."""
        u32 = self.u32
        if s32(u32(G_NUM_PLAYERS)) != 1:
            return
        frame = u32(G_SIM_FRAME)
        angle = (frame * 0x75) & 0xFFFF
        if not u32(spell + 0x20):
            f = ZERO
        else:
            f = C.fmin(C.mul(_from_uint(frame - u32(spell + 0x6C)), 0x3C888888), ONE)
        radius_i = C.to_int(C.mul(f, 0x42C80000))
        alpha = C.to_int(C.mul(C.sub(ONE, f), 0x43000000))
        for _ in range(13):
            s = C.sin16(angle)
            radius = C.from_int(radius_i + 15)
            owner = u32(spell + 0x18)
            x = C.add(u32(owner + 0x10), C.mul(s, radius))
            c = C.cos16(angle)
            y = C.add(u32(owner + 0x14), C.mul(c, radius))
            z = C.add(u32(owner + 0x18), 0x42E80000)
            self.call('glow_add', (x, y, z), 0x6F, 0x38, 0x28, alpha, u32(G_GLOW_TEX_RES), 0, 2, 0x41200000, 0x459C4000)
            angle = (angle + 0x13B1) & 0xFFFF

    def smokegen_draw(self, obj):
        """SmokeGen_draw 0x31cbf8: when isNearView(position; 1000), one glow per live puff
        of the ring at +0x50 (100 records of five s16: x, y, z-and-age, two more; first
        +0x438, end +0x43a).  t = age / (lifetime +0x464 x 60 x speed +0x474); point =
        position + (x, y) / 32, z = position.z + age / 32 + rise +0x47c; size, colour and
        alpha run linearly from +0x45c / +0x43c..+0x448 to +0x460 / +0x44c..+0x458; bias 5,
        texture +0x4c, angle s16(+0x488 x +0x472), negated on odd records, flags 5."""
        u32, s16_ = self.u32, self.s16
        if not self.call('isNearView', self.vec(obj + 0x10), 0x447A0000):
            return
        span = C.mul(C.from_int(s32(u32(obj + 0x464)) * 60), u32(obj + 0x474))
        i = s16_(obj + 0x438)
        end = s16_(obj + 0x43A)
        while i != end:
            rec = obj + 0x50 + i * 10
            age = C.from_int(s16_(rec + 4))
            t = C.div(age, span)
            z = C.add(C.add(u32(obj + 0x18), C.mul(age, 0x3D000000)), u32(obj + 0x47C))
            x = C.add(u32(obj + 0x10), C.mul(C.from_int(s16_(rec)), 0x3D000000))
            y = C.add(u32(obj + 0x14), C.mul(C.from_int(s16_(rec + 2)), 0x3D000000))

            def lerp(a_off, b_off):
                a = s32(u32(obj + a_off))
                return C.add(C.from_int(a), C.mul(C.from_int(s32(u32(obj + b_off)) - a), t))
            colour = [C.to_int(lerp(0x43C + 4 * k, 0x44C + 4 * k)) for k in range(4)]
            size = lerp(0x45C, 0x460)
            angle = s16((s32(u32(obj + 0x488)) * s16_(obj + 0x472)) & 0xFFFF)
            if i & 1:
                angle = s16((-angle) & 0xFFFF)
            self.call('glow_add', (x, y, z), colour[0], colour[1], colour[2], colour[3], u32(obj + 0x4C), angle, 5,
                      0x40A00000, size)
            i += 1
            if i == 100:
                i = 0


_register('ShockProjectile_draw', 0x2C4E64)
_register('FireArrowProjectile_draw', 0x2D67E8)
_register('HolyStrike_draw', 0x2ECD90)
_register('SpellSummonBadger_draw', 0x311034)
_register('SpellResurrect_draw', 0x312F48)
_register('SmokeGen_draw', 0x31CBF8)


class MultiFire:
    """MultiFireProjectile (the arrows of Multi Fire): a projectile with a grey trail and
    a stream of particles, all placed with the arrow's OWN generator (+0x44)."""
    MF_VT = 0x519128
    MF_PARTICLE = 0x8E5910
    MF_LUMP, MF_SOUND_FIRE, MF_SOUND_DUST = 0x54F560, 0x54F598, 0x54F5B0
    LEVEL_FLAGS = 0x44FE08                      # level flag word; 0x40000 selects the fire burst

    def multifire_ctor(self, obj, pos, angle, owner, level, skill):
        """MultiFireProjectile_ctor 0x2da164 (object, position, angle, owner, level, skill).
        Projectile_ctor(object, position, owner, 0) (one shared draw inside); angle s16
        +0x64, table, radius +0x1c = 8, skill +0x70, level +0x68; speed = skill slot 13 (1,
        level, owner handle +0x4c, 10); velocity +0x54 = speed x (cos16, sin16)(angle), 0;
        age +0x6c and ended +0x60 = 0; trail_create(row 1, width 0x7a, flags 0, grey 0x80,
        alpha 0x20; 0.15 s) -> +0x74, its first point at the position; the run list."""
        u32, w32 = self.u32, self.w32
        angle = s16(angle)
        self.call('Projectile_ctor', obj, tuple(pos), owner, 0)
        self.w16(obj + 0x64, angle)
        w32(obj + 0x48, self.MF_VT)
        w32(obj + 0x1C, 0x41000000)
        w32(obj + 0x70, skill)
        w32(obj + 0x68, level)
        speed = C.from_int(s32(self.skill_call(skill, 13, 1, level, obj + 0x4C, 10)))
        w32(obj + 0x54, C.mul(C.cos16(self.s16(obj + 0x64)), speed))
        sine = C.sin16(self.s16(obj + 0x64))
        w32(obj + 0x5C, 0)
        w32(obj + 0x6C, 0)
        w32(obj + 0x60, 0)
        w32(obj + 0x58, C.mul(sine, speed))
        handle = self.call('trail_create', 1, 0x7A, 0, 0x80, 0x80, 0x80, 0x20, 0x3E199999)
        w32(obj + 0x74, handle)
        self.call('trail_addPoint', handle, self.vec(obj + 0x10))
        self.call('obj_runEveryFrame', obj)

    def multifire_run(self, obj):
        """MultiFireProjectile_run 0x2da2bc, GameObject slot 4.  Nothing once ended.  A trail
        point at the position, age + 1, obj_moveAndCollide with the velocity; terrain (bit
        1): end(1); age 601 or more: end(0); else ten particles 0x8e5910: v = 8 x a unit-ball
        point, position + v x r (r = one more draw / 65536), velocity v."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        self.call('trail_addPoint', u32(obj + 0x74), self.vec(obj + 0x10))
        self.w32(obj + 0x6C, u32(obj + 0x6C) + 1)
        result = self.call('obj_moveAndCollide', obj, self.vec(obj + 0x54))
        if result & 1:
            return self.multifire_end(obj, 1)
        if not self.s32(obj + 0x6C) < 0x259:
            return self.multifire_end(obj, 0)
        for _ in range(10):
            ball = self.obj_ball(obj)
            v = tuple(C.mul(b, 0x41000000) for b in ball)
            share = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
            step = tuple(C.mul(v[k], share) for k in range(3))
            p = self.vec(obj + 0x10)
            self.call('particle_spawn', self.MF_PARTICLE, tuple(C.add(p[k], step[k]) for k in range(3)), v, ZERO)

    def multifire_end(self, obj, reason):
        """MultiFireProjectile_end 0x2da928 (object, reason), once (ended +0x60).  The trail
        is released; with a reason, one own draw picks one of four impact sounds and
        fx_spawn(8) at the position when level flag 0x40000 is set, else fx_spawn(2) (dust),
        then the sound on the object; obj_delete; ended = 1."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        self.call('trail_release', u32(obj + 0x74))
        if reason:
            fire = u32(self.LEVEL_FLAGS) & 0x40000
            draw = self.obj_rand(obj)
            text = self.call('libc_sprintf', self.MF_SOUND_FIRE if fire else self.MF_SOUND_DUST, (draw & 3) + 1)
            self.call('fx_spawn', 8 if fire else 2, self.vec(obj + 0x10))
            self.call('sound_playOnObject', self.call('res_find', self.MF_LUMP, text), obj, ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)


_register('MultiFireProjectile_ctor', 0x2DA164)
_register('MultiFireProjectile_run', 0x2DA2BC)
_register('MultiFireProjectile_end', 0x2DA928)


class FireStormFlare:
    """FireStormFlare: the falling fire balls of Fire Storm (skill 7).  Every particle is
    placed with the flare's OWN generator (+0x44); nothing here draws the shared seed."""
    FSF_PARTICLES = (0x8E5640, 0x8E5690, 0x8E56E0)
    FSF_LUMP, FSF_SOUND = 0x54F110, 0x54F138

    def _fsf_trail(self, obj, nv, per_scale, definition, speed=None, z_extra=None):
        """One of the three trail streams of a falling flare: while i < scale x per_scale,
        p = unit-ball x (scale x 8.7999935) + position, moved back along the velocity by r
        (one draw / 65536); velocity = a second ball point, scaled by `speed` (z once more
        by z_extra), or the raw point."""
        u32 = self.u32
        i = 0
        while C.lt(C.from_int(i), C.mul(u32(obj + 0x4C), per_scale)):
            ball = self.obj_ball(obj)
            k = C.mul(u32(obj + 0x4C), 0x410CCCC6)
            pos = self.vec(obj + 0x10)
            p = [C.add(C.mul(ball[j], k), pos[j]) for j in range(3)]
            share = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
            p = tuple(C.add(p[j], C.mul(nv[j], share)) for j in range(3))
            v = self.obj_ball(obj)
            if speed is not None:
                v = (C.mul(v[0], speed), C.mul(v[1], speed), C.mul(C.mul(v[2], speed), z_extra))
            self.call('particle_spawn', definition, p, tuple(v), ZERO)
            i += 1

    def firestormflare_run(self, obj):
        """FireStormFlare_run 0x2d33c0, GameObject slot 4.

        Falling (landed +0x50 = 0 and frame < expiry +0x68): vz += -0.39999998, position +=
        velocity +0x5c..+0x64; three particle streams with the reversed velocity (scale
        +0x4c): x30 of 0x8e5640 (speed 10.419806, z x 10.261909), x18 of 0x8e5690 (5.0619698,
        z x 7.171931), x4 of 0x8e56e0 (raw ball); then terrain_height(world, position;
        radius +0x1c): less than 16 above the ground lands it (+0x50 = 1) with a sound.
        Landed, while the ring +0x58 (s16) is below radius x 3 x scale: ring += 7 and 85
        pairs of particles (0x8e5640 and 0x8e5690, the same point and velocity) at angle =
        one draw, ring x (cos16, sin16) + 6.76 x a ball point + position, velocity a second
        ball point.  Then: one draw % 100 < 33 lowers z by 6 and lays a scorch decal (type 9,
        no growth, size = scale, angle = s16 of one more draw); slot 1 (3) destroys it."""
        u32, w32 = self.u32, self.w32
        if not u32(obj + 0x50) and s32(u32(G_SIM_FRAME)) < self.s32(obj + 0x68):
            w32(obj + 0x64, C.add(u32(obj + 0x64), 0xBECCCCCC))
            for j in range(3):
                w32(obj + 0x10 + 4 * j, C.add(u32(obj + 0x10 + 4 * j), u32(obj + 0x5C + 4 * j)))
            nv = tuple(C.neg(u32(obj + 0x5C + 4 * j)) for j in range(3))
            self._fsf_trail(obj, nv, 0x41F00000, self.FSF_PARTICLES[0], 0x4126B786, 0x412430C7)
            self._fsf_trail(obj, nv, 0x41900000, self.FSF_PARTICLES[1], 0x40A1FBA8, 0x40E58075)
            self._fsf_trail(obj, nv, 0x40800000, self.FSF_PARTICLES[2])
            ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
            if C.lt(C.sub(u32(obj + 0x18), ground), 0x41800000):
                w32(obj + 0x50, 1)
                self.call('sound_playOnObject', self.call('res_find', self.FSF_LUMP, self.FSF_SOUND), obj, ONE)
            return
        if C.lt(C.from_int(self.s16(obj + 0x58)), C.mul(C.mul(u32(obj + 0x1C), 0x40400000), u32(obj + 0x4C))):
            self.w16(obj + 0x58, self.u16(obj + 0x58) + 7)
            for _ in range(0x55):
                draw = self.obj_rand(obj)
                cx = C.mul(C.cos16(draw), C.from_int(self.s16(obj + 0x58)))
                sy = C.mul(C.sin16(draw), C.from_int(self.s16(obj + 0x58)))
                ring = (cx, sy, ZERO)
                ball = self.obj_ball(obj)
                pos = self.vec(obj + 0x10)
                p = tuple(C.add(C.add(ring[j], C.mul(ball[j], 0x40D851EB)), pos[j]) for j in range(3))
                v = self.obj_ball(obj)
                self.call('particle_spawn', self.FSF_PARTICLES[0], p, v, ZERO)
                self.call('particle_spawn', self.FSF_PARTICLES[1], p, v, ZERO)
            return
        if self.obj_rand(obj) % 100 < 0x21:
            w32(obj + 0x18, C.sub(u32(obj + 0x18), 0x40C00000))
            draw = self.obj_rand(obj)
            self.call('decal_add', self.vec(obj + 0x10), s16(draw), 9, 0, u32(obj + 0x4C))
        if obj:
            self.vcall(obj, 1, 3)


_register('FireStormFlare_run', 0x2D33C0)


class Model(Calls, Draws, MultiFire, FireStormFlare, SC.Model):
    """ref_skills_c.Model with the methods of part 3."""
