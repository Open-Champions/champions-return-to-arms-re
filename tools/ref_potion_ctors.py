#!/usr/bin/env python3
"""ref_potion_ctors.py - what the endings of the thrown potions of kinds 1 and 2 build:
LooseFire (and the Fire objects its constructor makes through fx_spawn id 5) and
poisonGasSpell, on a memory image.

A research tool, not game code.  Every method was written from the instructions at the
address in its docstring.  tools/difftest_potion_ctors.py runs the original of each in
tools/ee_emu.py and compares the calls (in order, with arguments), the bytes stored
outside the stack, the shared seed 0x404464 with its draw count, and the result.
docs/spec/potion-ctors.md is the prose.  Standard library only; no game data is
embedded (particle definitions, tables and globals are named by address).

Why: playerProjectile_run 0x1ba940 ends a kind-1 potion with five
LooseFire_ctor(pool_new(0x54), point, owner) calls and a kind-2 potion with
poisonGasSpell_ctor(pool_new(0x70), position, 300, 20, 0, owner, 5).  The combat rounds
executed those endings with both constructors as recording stubs, and poisonGasSpell_run
0x1fd0f0 on its own.  The constructors, fx_spawn id 5, Fire_ctor, Fire_run, LooseFire_run
and LooseFire_onTouch were Observed only.  This module adds them.

How it sees the game: as tools/ref_skills_a.py does (it is a subclass of that Model, so
GameObject_ctor 0x14cb10 - executed by tools/difftest_skills_a.py - is reused, not
written again).  Callbacks for everything outside the model (EXTERNALS below), canonical
arguments (integers unsigned 32-bit, floats as 32-bit patterns, a vector as a tuple of
three patterns, a damage descriptor as ref_skills_a.descriptor()).  Model.draws counts
the draws from the shared seed.

Evidence words, as in CONTRIBUTING.md: Executed = the original was run one function at a
time in the interpreter by tools/difftest_potion_ctors.py and agreed with the method.
Observed = read at the address.  Inferred = follows from those.  Nothing here was run on
a console, in PCSX2 or on the live rig.

Contents
    obj_run_every_frame   obj_runEveryFrame 0x14f248        Executed
    fx_spawn (id 5 only)  fx_spawn 0x1ef270, arm 0x1f0ae0   Executed (id 5; other ids refuse)
    fire_ctor             Fire_ctor 0x2020e0                Executed
    fire_run              Fire_run 0x1f34e0                 Executed
    loosefire_ctor        LooseFire_ctor 0x202b70           Executed
    loosefire_run         LooseFire_run 0x202c48            Executed
    loosefire_on_touch    LooseFire_onTouch 0x1fcb70        Executed
    poison_gas_ctor       poisonGasSpell_ctor 0x202de8      Executed
    loosefire_draws       how many shared draws one LooseFire_ctor makes   Inferred
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
from ref_creature import Ext, M32, s16, s32     # noqa: E402

# ---------------------------------------------------------------------------------------
# Addresses and constants (Observed at the addresses given)
# ---------------------------------------------------------------------------------------
G_RAND_SEED = RC.G_RAND_SEED                    # 0x404464 shared seed
G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_DIFFICULTY = 0x4F719C                         # g_difficultyIdx, read by LooseFire_onTouch
G_ACTIVE_LIST = 0x5DB3A8                        # obj_runEveryFrame's list head (0x14f26c)
FX_DEF_FLAGS = 0x4F87BC                         # fx_spawn's 24 "definition made" words
FX_DEF_COUNT = 24
G_GLOW_TEXTURE = 0x4F848C                       # the word Fire_run hands glow_add (0x1f35a0)

VT_LOOSEFIRE = 0x50E2B8                         # slot 1 0x3c6778, 4 0x202c48, 6 0x1fcb70
VT_FIRE = 0x50F208                              # slot 1 0x3c5050, 4 0x1f34e0
VT_POISON_GAS = 0x50D500                        # slot 1 0x3c7878, 4 0x1fd0f0, 5 0x202f00

SIZE_LOOSEFIRE, SIZE_FIRE, SIZE_POISON_GAS = 0x54, 0x50, 0x70

LOOSEFIRE_LIFE = 0x78                           # +0x50 = frame + 120 (0x202bec)
FIRE_LIFE = 0x64                                # +0x4c = 100 (0x202140)
FIRE_PARTICLE = 0x870548                        # Fire_run's particle definition (0x1f3788)
TOUCH_PERIOD = 0x14                             # LooseFire_onTouch acts when frame % 20 == 0
TOUCH_RATING = 0x989680                         # 10,000,000, damage_apply's third argument
TOUCH_FLAGS = 0x100C040
FIRE_ENTRY = 0x15                               # descriptor entry type
CREATURE_STRENGTH = 8                           # the entry's value for a non-player creature
GAS_RADIUS_FLOOR = 10

F_TEN = 0x41200000                              # LooseFire +0x1c, poisonGasSpell +0x64
F_SIX = C.SIX                                   # fx_spawn id 5: x and y start 6 lower
F_FIVE = 0x40A00000                             # glow bias
F_GLOW_SIZE = 0x45FA0000                        # 8000
F_GLOW_SWING = 0x437A0000                       # 250
F_RISE = 0x40999999                             # 4.7999997, Fire_run's upward speed
ZERO, ONE = C.ZERO, C.ONE

# The original functions this module implements (name -> address).
MODELLED = {
    'obj_runEveryFrame': 0x14F248, 'fx_spawn': 0x1EF270, 'Fire_ctor': 0x2020E0,
    'Fire_run': 0x1F34E0, 'LooseFire_ctor': 0x202B70, 'LooseFire_run': 0x202C48,
    'LooseFire_onTouch': 0x1FCB70, 'poisonGasSpell_ctor': 0x202DE8,
}

EXTERNALS = dict(SA.EXTERNALS)
EXTERNALS.update({
    'handle_removeNode': Ext(0x1A1868, 'p', 0, 'i', '(node) -> the object of the node'),
    'glow_add': Ext(0x18FC78, 'viiiiiii', 2, 'n', '(position, r, g, b, alpha, texture, 0, 0; bias, size)'),
    'particleDef_ctor': Ext(0x18F3D0, 'piiiiiii', 3, 'n', 'a particle definition; never reached here'),
    'Creature.v20': Ext(0, 'pp', 0, 'i', 'is enemy (other): nonzero lets the fire burn'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """The zero answer of a callback nobody supplied (ref_creature.shape_result on this
    module's rows)."""
    ext = EXTERNALS[name]
    if ext.ret == 'n':
        return None
    return fret if ext.ret == 'f' else ret


def loosefire_draws(blocks):
    """Inferred from the Executed bodies: the shared draws one LooseFire_ctor makes.

    `blocks` is what pool_new(0x50) answers for each Fire, in order (truthy = a block).
    GameObject_ctor of the LooseFire draws 1; fx_spawn id 5 draws 1 for the count
    (3 + (d & 1)); every Fire then draws 3 for its point and, only when the pool gave a
    block, 1 more inside its own GameObject_ctor.  So 2 + 3n + (blocks given), n = 3 or
    4: between 11 and 18."""
    return 2 + sum(4 if block else 3 for block in blocks)


class Model(SA.Model):
    """LooseFire, Fire and poisonGasSpell on a memory image.  See the module docstring."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    # ---- small shared pieces -----------------------------------------------------------
    def obj_run_every_frame(self, obj):
        """obj_runEveryFrame 0x14f248 (object).  Executed.

        When the run link word +4 is set, handle_removeNode(that word) first.  Then
        handle_link(0x5db3a8, object + 4, object): the object joins the list whose
        members get their slot 4 (run) every frame."""
        node = self.u32(obj + 4)
        if node:
            self.call('handle_removeNode', node)
        self.call('handle_link', G_ACTIVE_LIST, (obj + 4) & M32, obj)

    # ---- Fire (fx_spawn id 5) ------------------------------------------------------------
    def fx_spawn(self, fx_id, pos):
        """fx_spawn 0x1ef270 (id, position) for id 5 only - the arm at 0x1f0ae0.  Executed.

        Id 5 skips the camera test the other ids make (0x1ef2d8) and is the only id that
        draws the shared seed.  Precondition: the 24 particle definitions of fx_spawn are
        already made (words 0x4f87bc + 4i nonzero); a first call that makes them is
        research-fx's (docs/effects.md 14.1) and is refused here.

        Shared draw d: n = 3 + (d & 1) fires.  For each, three shared draws dx, dy, dz:
        the point is ((x - 6) + float(dx % 12), (y - 6) + float(dy % 12), z +
        float(dz % 18)), where d % k is the unsigned remainder of the 16-bit draw.  Then
        pool_new(0x50) and, with a block, Fire_ctor(block, point) - whose GameObject_ctor
        draws the shared seed once more.  A refused block skips only that Fire."""
        if s32(fx_id) != 5:
            raise NotImplementedError('fx_spawn id %d: only id 5 is modelled here' % s32(fx_id))
        for i in range(FX_DEF_COUNT):
            if not self.u32(FX_DEF_FLAGS + 4 * i):
                raise NotImplementedError('fx_spawn definition %d not made yet (first call)' % i)
        pos = tuple(pos)
        count = 3 + (self.draw() & 1)
        for _fire in range(count):
            dx, dy, dz = self.draw(), self.draw(), self.draw()
            point = (C.add(C.sub(pos[0], F_SIX), C.from_int(dx % 12)),
                     C.add(C.sub(pos[1], F_SIX), C.from_int(dy % 12)),
                     C.add(pos[2], C.from_int(dz % 18)))
            block = self.call('pool_new', SIZE_FIRE)
            if block:
                self.fire_ctor(block, point)

    def fire_ctor(self, obj, pos):
        """Fire_ctor 0x2020e0 (block, position).  Executed.

        GameObject_ctor (no class definition, no properties: ONE SHARED DRAW), table
        0x50f208, flags +0xc |= 0x4001, byte +0x28 = 0xf0, obj_runEveryFrame, then the
        life halfword +0x4c = 100."""
        self.gameobject_ctor(obj, tuple(pos), 0, 0)
        self.w32(obj + 0x48, VT_FIRE)
        self.w8(obj + 0x28, 0xF0)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4001)
        self.obj_run_every_frame(obj)
        self.w16(obj + 0x4C, FIRE_LIFE)

    def fire_run(self, obj):
        """Fire_run 0x1f34e0 (fire), slot 4.  Executed.  Cosmetic except its lifetime.

        alpha from the signed life L = +0x4c: L < 20 gives 60 - 3(20 - L), L > 80 gives
        3(100 - L), else 60.  glow_add(position, 255, 150, 0, alpha, the word at
        0x4f848c, 0, 0; bias 5, size sin16(g_simFrame << 10) * 250 + 8000) - math_sin16
        0x1666e0 is real code (ref_core.sin16).  One particle: a unit-ball point u then
        u' from the fire's OWN generator (+0x44), velocity (2u.x, 2u.y, 2u.z + 4.8),
        position (2u'.x, 2u'.y, |2u'.z|) + the fire's position (neg.s only when strictly
        below zero, so -0 stays), particle_spawn(0x870548, position, velocity; 0).  Then
        the life halfword drops by one; at 0 or below (signed) slot 1 with 3 deletes the
        fire.  Nothing here draws the shared seed."""
        life = self.s16(obj + 0x4C)
        if life < 20:
            alpha = 60 - 3 * (20 - life)
        elif life < 0x51:
            alpha = 60
        else:
            alpha = 3 * (100 - life)
        swing = C.sin16((self.u32(G_SIM_FRAME) << 10) & M32)
        size = C.add(C.mul(swing, F_GLOW_SWING), F_GLOW_SIZE)
        self.call('glow_add', self.vec(obj + 0x10), 0xFF, 0x96, 0, alpha, self.u32(G_GLOW_TEXTURE), 0, 0,
                  F_FIVE, size)
        u = self.obj_ball(obj)
        velocity = (C.add(u[0], u[0]), C.add(u[1], u[1]), C.add(C.add(u[2], u[2]), F_RISE))
        w = self.obj_ball(obj)
        up = C.add(w[2], w[2])
        if C.lt(up, ZERO):
            up = C.neg(up)
        pos = self.vec(obj + 0x10)
        point = (C.add(C.add(w[0], w[0]), pos[0]), C.add(C.add(w[1], w[1]), pos[1]), C.add(up, pos[2]))
        self.call('particle_spawn', FIRE_PARTICLE, point, velocity, ZERO)
        left = (self.u16(obj + 0x4C) - 1) & 0xFFFF
        self.w16(obj + 0x4C, left)
        if s16(left) <= 0 and obj:
            self.vcall(obj, 1, 3)

    # ---- LooseFire -------------------------------------------------------------------------
    def loosefire_ctor(self, obj, pos, owner):
        """LooseFire_ctor 0x202b70 (block, position, owner object or 0).  Executed.

        GameObject_ctor (ONE SHARED DRAW), table 0x50e2b8, owner handle +0x4c = 0 and,
        with an owner, handle_link(obj + 0x4c, owner, owner).  End frame +0x50 =
        g_simFrame + 120.  fx_spawn(5, the object's position): 3 or 4 Fire objects and
        their shared draws (see fx_spawn).  obj_runEveryFrame.  Flags +0xc |= 0x420c,
        radius +0x1c = 10.0.  So one LooseFire makes 11 to 18 shared draws
        (loosefire_draws)."""
        self.gameobject_ctor(obj, tuple(pos), 0, 0)
        self.w32(obj + 0x48, VT_LOOSEFIRE)
        self.w32(obj + 0x4C, 0)
        if owner:
            self.call('handle_link', (obj + 0x4C) & M32, owner, owner)
        self.w32(obj + 0x50, self.u32(G_SIM_FRAME) + LOOSEFIRE_LIFE)
        self.fx_spawn(5, self.vec(obj + 0x10))
        self.obj_run_every_frame(obj)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x420C)
        self.w32(obj + 0x1C, F_TEN)

    def loosefire_run(self, obj):
        """LooseFire_run 0x202c48 (fire), slot 4.  Executed.

        Only when the signed end frame +0x50 is strictly below g_simFrame: slot 1 with 3
        (delete).  So a LooseFire lives 121 runs after the frame it was made in, if run
        every frame.  Nothing else: the burning is the touch handler's."""
        if self.s32(obj + 0x50) < self.frame() and obj:
            self.vcall(obj, 1, 3)

    def loosefire_on_touch(self, obj, other):
        """LooseFire_onTouch 0x1fcb70 (fire, toucher), slot 6.  Executed.

        Nothing unless g_simFrame % 20 == 0 (signed div).  The owner is the object behind
        the handle +0x4c when its flags +0xc have 0x20 (a creature), else none; an owner
        asks its slot 20 (owner, toucher) and a zero answer ends the touch.  The fire
        entry (type 0x15, v, v, 0) goes into slot 0 of a fresh descriptor: a toucher with
        flag 0x40 (a player) gets v from g_difficultyIdx 0x4f719c (2, 3, 4, 5 as they
        are, anything else 1); one with 0x20 and not 0x40 gets v = 8; anything else an
        EMPTY descriptor.  Then damage_apply(toucher, owner or the fire itself,
        10000000, 0, 0, 0x100c040, descriptor, 0; 0, 0).  Its result is not used."""
        if SA.rem(self.u32(G_SIM_FRAME), TOUCH_PERIOD):
            return
        owner = 0
        node = self.u32(obj + 0x4C)
        if node:
            candidate = self.u32(node + 0xC)
            if self.u32(candidate + 0xC) & 0x20:
                owner = candidate
        if owner and not (self.vcall(owner, 20, other) or 0) & M32:
            return
        flags = self.u32(other + 0xC)
        if flags & 0x40:
            level = self.s32(G_DIFFICULTY)
            value = level if level in (2, 3, 4, 5) else 1
            desc = SA.descriptor((FIRE_ENTRY, value, value, 0))
        elif flags & 0x20:
            desc = SA.descriptor((FIRE_ENTRY, CREATURE_STRENGTH, CREATURE_STRENGTH, 0))
        else:
            desc = SA.descriptor()
        self.call('damage_apply', other, owner or obj, TOUCH_RATING, 0, 0, TOUCH_FLAGS, desc, 0, ZERO, ZERO)

    # ---- poisonGasSpell ----------------------------------------------------------------------
    def poison_gas_ctor(self, obj, pos, life, radius, word68, owner, damage):
        """poisonGasSpell_ctor 0x202de8 (block, position, life frames, radius, word,
        owner object or 0, damage).  Executed.  A GameObject, not a Spell: there is no
        Spell base and no spell generator.

        GameObject_ctor (ONE SHARED DRAW), owner handle +0x4c = 0, table 0x50d500, a
        second copy of the position at +0x50, end frame +0x5c = g_simFrame + life, target
        radius +0x60 = radius, +0x68 = the fifth argument, damage +0x6c, and with an
        owner handle_link(obj + 0x4c, owner, owner).  A target radius below 10 (signed)
        becomes 10.  Flags +0xc |= 3, current radius +0x64 = 10.0, obj_runEveryFrame.
        The potion's call (300, 20, 0, owner, 5) gives end = frame + 300, target 20,
        damage 5; poisonGasSpell_run (round 6) grows +0x64 by 0.5 a frame toward the
        target and burns every 30th frame."""
        pos = tuple(pos)
        self.gameobject_ctor(obj, pos, 0, 0)
        self.w32(obj + 0x4C, 0)
        self.w32(obj + 0x48, VT_POISON_GAS)
        self.wvec(obj + 0x50, pos)
        self.w32(obj + 0x60, radius)
        self.w32(obj + 0x68, word68)
        self.w32(obj + 0x5C, self.u32(G_SIM_FRAME) + life)
        self.w32(obj + 0x6C, damage)
        if owner:
            self.call('handle_link', (obj + 0x4C) & M32, owner, owner)
        if self.s32(obj + 0x60) < GAS_RADIUS_FLOOR:
            self.w32(obj + 0x60, GAS_RADIUS_FLOOR)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 3)
        self.w32(obj + 0x64, F_TEN)
        self.obj_run_every_frame(obj)
