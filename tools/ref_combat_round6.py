#!/usr/bin/env python3
"""ref_combat_round6.py - the skill and spell combat handlers the earlier rounds left unrun.

A research tool, not game code.  Each method was written from the instructions at the
address in its docstring.  tools/difftest_combat_round6.py runs the original in
tools/ee_emu.py and compares calls, stored bytes, the shared seed and the result.
docs/spec/combat-round6.md is the prose.

This module subclasses tools/ref_skills_a.py's Model and only ADDS methods.  It does not
change the round-1 through round-5 reference APIs, their pinned vectors, or the bodies
those difftests already compare.

Evidence, as in docs/combat-runtime.md: Executed means the original was run one function
at a time in the interpreter and agreed with the method.  Observed means read at the
address.  Nothing here was run on a console, in PCSX2 or on the live rig.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
from ref_creature import M32, s16, s32          # noqa: E402

# poisonGasSpell_run 0x1fd0f0.  The particle definition is the immediate at 0x1fd328.
GAS_PARTICLE = 0x871088
GAS_SPEED = 0x40A00000                          # 5, the velocity scale at 0x1fd19c
GAS_FLAGS = 0x01000040                          # lui 0x100 / ori 0x40 at 0x1fd508

# MultiFireProjectile_onHit 0x2da610.  The scale is the constant at 0x2da6b0.
F_SCALE = 0x3C23D70A
F_SPREAD = 0x3E4CCCCC                           # the 0.2 at 0x2da820
HIT_FLAGS = 0x40000                             # lui at 0x2da8ec
PLAYER_SKIP = 0x01000040                        # lui 0x100 / ori 0x40 at 0x2da64c
CREATURE_SKIP = 0x04000000                      # lui 0x400 at 0x2da66c, tested against +0xa8

# MultiFireProjectile_end 0x2da928.  Formats and the lump are immediates; the text
# they point at is not copied here.
FMT_ICE = 0x54F598
FMT_STONE = 0x54F5B0
FX_LUMP = 0x54F560
LEVEL_ICE = 0x40000                             # the bit of g_levelFlags at 0x44fe08

# SmokeGen_run 0x31c898.
F_1000 = 0x447A0000
F_3 = 0x40400000
SMOKE_FLAGS = 0x0100C040                        # lui 0x100 / ori 0xc040 at 0x31ca6c

# Pustule_run 0x30bde0.  Definitions and the two sound words are immediates.
PUS_FALL, PUS_DROP = 0x8E7548, 0x8E74F8
PUS_LUMP, PUS_SOUND = 0x552328, 0x552388
PUS_GRAVITY = 0xBE4CCAB3
PUS_DROP_GRAVITY = 0xBEE1C9F7
PUS_AGE = 0x420ECCFB                            # burst dies once the timer float exceeds this
PUS_LIFE = 0x12D                                # 301: the launch timer destroys the blob

# SpellArena_run 0x305bbc.  The counter is the signed halfword at 0x5038c8.
G_ARENA_COUNTER = 0x5038C8
ARENA_PARTICLES = (0x8E71E0, 0x8E7190)
ARENA_TINT = (0x56, 0x35, 0x21, 0x3D)

# SpellHornOmenEffect_run 0x2fc684 and SpellPlanarSteelEffect_run 0x2fb9b4.
HO_PARTICLE = 0x8E6C40
VT_SPELL, HO_VT, PS_VT = 0x515BA0, 0x51AE58, 0x51AE28
PS_BURST, PS_SPARK, PS_SPARK2, PS_FALL = 0x8E6BA0, 0x8E6B00, 0x8E6B50, 0x8E6BF0
PS_LUMP, PS_SOUND_START, PS_SOUND_BURST = 0x551320, 0x551328, 0x551340
G_GLOW_TEX_C = 0x4F8498

MODELLED = {
    'poisonGasSpell_run': 0x1FD0F0,
    'DiseaseCorpse_run': 0x2CE4A4,
    'MultiFireProjectile_onHit': 0x2DA610,
    'MultiFireProjectile_end': 0x2DA928,
    'SmokeGen_run': 0x31C898,
    'Pustule_run': 0x30BDE0,
    'SpellArena_run': 0x305BBC,
    'SpellHornOmenEffect_ctor': 0x2FC574,
    'SpellHornOmenEffect_run': 0x2FC684,
    'SpellPlanarSteelEffect_ctor': 0x2FB728,
    'SpellPlanarSteelEffect_run': 0x2FB9B4,
}


class Model(SA.Model):
    """The round-6 handlers on a memory image.  See the module docstring."""

    def _collect(self, pos, radius):
        low = tuple(C.sub(pos[j], radius) for j in range(3))
        high = tuple(C.add(pos[j], radius) for j in range(3))
        return self.call('world_collectObjectsInBox', low, high, 0x40) or ()

    def _apply(self, victim, attacker, flags, desc, low, high):
        self.call('damage_apply', victim, attacker, 100000, 0, 0, flags, desc, 0, low, high)

    def poison_gas_run(self, obj):
        """poisonGasSpell_run 0x1fd0f0 (cloud).

        While g_simFrame is strictly below the signed end at +0x5c: if the float radius
        +0x64 is strictly below the integer target +0x60, the radius grows by 0.5.
        (target / 10) particles, toward zero, are spawned while that count is positive
        (definition 0x871088; position is a unit-ball point times the radius; velocity
        is a second point times 5; backdate 0).  On a frame divisible by 30, and only
        when the owner handle +0x4c is set, every object in the box position +/-
        trunc(radius) whose owner slot 20 returns nonzero takes damage_apply(victim,
        owner, 100000, 0, 0, flags 0x01000040, entry (0x17, +0x6c, +0x6c, 0), 0; 0, 0).
        The low 16 bits of +0x6c are what the entry stores.  At the end frame, slot 1
        with 3 destroys the cloud.  A frame that is not the end does not.
        """
        if not self.frame() < self.s32(obj + 0x5C):
            self.delete_self(obj)
            return
        target = self.s32(obj + 0x60)
        if C.lt(self.u32(obj + 0x64), C.from_int(target)):
            self.w32(obj + 0x64, C.add(self.u32(obj + 0x64), C.HALF))
        count = SA.quot(target, 10)
        made = 0
        while made < count:
            ball = self.obj_ball(obj)
            radius = self.u32(obj + 0x64)
            pos = self.vec(obj + 0x10)
            point = tuple(C.add(C.mul(ball[j], radius), pos[j]) for j in range(3))
            velocity = tuple(C.mul(part, GAS_SPEED) for part in self.obj_ball(obj))
            self.call('particle_spawn', GAS_PARTICLE, point, velocity, C.ZERO)
            made += 1
        if SA.rem(self.frame(), 30):
            return
        if not self.u32(obj + 0x4C):
            return
        radius = C.from_int(C.to_int(self.u32(obj + 0x64)))
        for victim in self._collect(self.vec(obj + 0x10), radius):
            node = self.u32(obj + 0x4C)
            if not node:
                continue
            owner = self.u32(node + 0xC)
            if not self.vcall(owner, 20, victim):
                continue
            value = self.u32(obj + 0x6C) & 0xFFFF
            self._apply(victim, owner, GAS_FLAGS, SA.descriptor((0x17, value, value, 0)),
                        C.ZERO, C.ZERO)

    def disease_corpse_run(self, obj):
        """DiseaseCorpse_run 0x2ce4a4 (corpse).

        One box, position +/- the integer at +0x54 converted to float, capacity 0x40.
        An empty box destroys the corpse (slot 1 with 3) without reading +0x50.  Otherwise
        half = (+0x50) / 2 toward zero.  half <= 0 destroys it the same way.  Each object
        is a candidate when (flags & 0x28) == 0x28 and the corpse's owner handle is set.
        A candidate consumes one of the half spawns even when pool_new(0x64) returns 0.
        A block is DiseaseCloud_ctor(block, the victim's position, the word +0x50, the
        owner object, which may be 0).  The walk stops at the end of the list or once
        the spawn count reaches half.  The corpse then destroys itself.  DiseaseCloud_ctor
        is the round-3 body; this run only calls it.
        """
        radius = C.from_int(self.s32(obj + 0x54))
        found = self._collect(self.vec(obj + 0x10), radius)
        if found:
            half = SA.half_toward_zero(self.s32(obj + 0x50))
            if half > 0:
                spawned = 0
                index = 0
                while index < len(found):
                    victim = found[index]
                    if (self.u32(victim + 0xC) & 0x28) == 0x28:
                        node = self.u32(obj + 0x4C)
                        if node:
                            spawned += 1
                            block = self.call('pool_new', 0x64) or 0
                            if block:
                                self.call('DiseaseCloud_ctor', block, self.vec(victim + 0x10),
                                          self.u32(obj + 0x50) & M32, self.u32(node + 0xC))
                    index += 1
                    if index >= len(found):
                        break
                    if not spawned < SA.half_toward_zero(self.s32(obj + 0x50)):
                        break
        self.delete_self(obj)

    def _player_bounds(self, obj, owner):
        """min and max for a player-owned bolt: slot 13 (stat 0, level, the handle
        address, cap 10) times 0x3c23d70a, divided by slot 10 (stat 2, level).  Each of
        the owner record's weapon words +0xd0 and +0xd4, as integers, is multiplied by
        that and rounded half away from zero.  The record is g_players + slot*0x4c30,
        and the slot is the word at the owner object +0x3c8."""
        skill = self.u32(obj + 0x70)
        level = self.u32(obj + 0x68)
        stat0 = self.skill_call(skill, 13, 0, level, (obj + 0x4C) & M32, 10)
        stat2 = self.skill_call(skill, 10, 2, level)
        scale = C.div(C.mul(C.from_int(s32(stat0)), F_SCALE), C.from_int(s32(stat2)))
        rec = (RC.G_PLAYERS + self.s32(owner + 0x3C8) * RC.REC_SIZE) & M32
        low = C.from_int(C.round_half_away(C.mul(C.from_int(self.s32(rec + 0xD0)), scale)))
        high = C.from_int(C.round_half_away(C.mul(C.from_int(self.s32(rec + 0xD4)), scale)))
        return low, high

    def _monster_bounds(self, obj):
        """min is slot 13 (stat 0, level, the handle address, cap 10).  Two draws of the
        bolt's own generator follow.  The first only chooses the sign of the 0.2 spread;
        the second is the magnitude.  Both draws are fractions in [0, 1), so a positive
        stat always takes the +0.5 side.  max is min plus that rounded spread."""
        skill = self.u32(obj + 0x70)
        level = self.u32(obj + 0x68)
        base = self.skill_call(skill, 13, 0, level, (obj + 0x4C) & M32, 10)
        amount = C.from_int(s32(base))
        spread = C.mul(amount, F_SPREAD)
        sign = C.mul(spread, SA.frac(self.obj_rand(obj)))
        magnitude = C.mul(spread, SA.frac(self.obj_rand(obj)))
        extra = C.to_int(C.add(magnitude, C.HALF) if C.le(C.ZERO, sign) else C.sub(magnitude, C.HALF))
        high = (s32(base) + extra) & M32
        return amount, C.from_int(s32(high))

    def multifire_on_hit(self, obj, other):
        """MultiFireProjectile_onHit 0x2da610 (bolt, other).

        An empty owner handle returns.  A player owner (object flag 0x40) returns when
        other's flags meet 0x01000040, and when other has flag 0x20 and the word at
        +0xa8 has bit 0x04000000.  Otherwise the player bounds above.  Any other owner
        returns when its slot 20 on other is 0; otherwise the monster bounds above.
        Either way that reaches the damage: damage_apply(other, owner, 100000, 0, 0,
        flags 0x40000, no descriptor, 0; min, max), then MultiFireProjectile_end(bolt, 2).
        There is no already-ended test here.  A stat-2 result of 0 is not exercised.
        """
        node = self.u32(obj + 0x4C)
        if not node:
            return
        owner = self.u32(node + 0xC)
        if self.u32(owner + 0xC) & 0x40:
            flags = self.u32(other + 0xC)
            if flags & PLAYER_SKIP:
                return
            if flags & 0x20 and self.u32(other + 0xA8) & CREATURE_SKIP:
                return
            low, high = self._player_bounds(obj, owner)
        else:
            if not self.vcall(owner, 20, other):
                return
            low, high = self._monster_bounds(obj)
        self._apply(other, owner, HIT_FLAGS, 0, low, high)
        self.multifire_end(obj, 2)

    def multifire_end(self, obj, reason):
        """MultiFireProjectile_end 0x2da928 (bolt, reason).

        A nonzero word at +0x60 returns immediately.  Otherwise trail_release of the
        pointer at +0x74.  Reason 0 then obj_delete and stores 1 at +0x60.  Any other
        reason draws the bolt's own generator once: the level flag 0x40000 selects
        format 0x54f598 and fx_spawn 8, and its absence selects format 0x54f5b0 and
        fx_spawn 2.  The integer printed is (draw & 3) + 1.  res_find(0x54f560, that
        text), sound_playOnObject at volume 1, then the same delete and store.
        """
        if self.u32(obj + 0x60):
            return
        self.call('trail_release', self.u32(obj + 0x74))
        if reason:
            ice = self.u32(RC.G_LEVEL_FLAGS) & LEVEL_ICE
            number = (self.obj_rand(obj) & 3) + 1
            text = self.call('libc_sprintf', FMT_ICE if ice else FMT_STONE, number)
            self.call('fx_spawn', 8 if ice else 2, self.vec(obj + 0x10))
            entry = self.call('res_find', FX_LUMP, text)
            self.call('sound_playOnObject', entry, obj, C.ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)

    def smoke_gen_run(self, obj):
        """SmokeGen_run 0x31c898 (generator).

        isNearView(position, 1000) returning 0 does nothing else.  Otherwise
        SmokeGen_stepParticles runs.  A signed word at +0x48c that is <= 0, or a
        g_simFrame whose low 3 bits are not all clear, stops there.  Otherwise the box
        is position +/- (the float at +0x478 times 3), capacity 0x40.  Every object
        except the generator itself, except one whose flag bit 0 is set, and except one
        without flag 0x20, takes damage_apply(victim, the generator, 100000, 0, 0,
        flags 0x0100c040, entry (0x26, 1, 1, 0), 0; the integer +0x48c as both amounts).
        """
        if not self.call('isNearView', (obj + 0x10) & M32, F_1000):
            return
        self.call('SmokeGen_stepParticles', obj)
        amount = self.s32(obj + 0x48C)
        if amount <= 0 or self.u32(SA.G_SIM_FRAME) & 7:
            return
        reach = C.mul(self.u32(obj + 0x478), F_3)
        desc = SA.descriptor((0x26, 1, 1, 0))
        damage = C.from_int(amount)
        for victim in self._collect(self.vec(obj + 0x10), reach):
            if victim == obj:
                continue
            flags = self.u32(victim + 0xC)
            if flags & 1 or not (flags & 0x20):
                continue
            self._apply(victim, obj, SMOKE_FLAGS, desc, damage, damage)

    def pustule_run(self, obj):
        """Pustule_run 0x30bde0 (blob).

        A burst whose timer float is above 0x420eccfb, or any timer of 301 or more,
        destroys the blob (slot 1 with 3).  Until the burst flag +0x6c is set the blob
        falls: +0x60 gains 0xbe4ccab3, the position gains the velocity at +0x58, and
        three particles (0x8e7548) are laid back along that step.  Reaching the floor
        float +0x54 starts the burst: the timer is cleared, a sound is played at the
        position, and ten drops are stored at +0x70 and +0xe8.  From then on, including
        the burst tick, each drop moves by its velocity, its z velocity gains
        0xbee1c9f7, and one particle (0x8e74f8) is spawned.  The timer then advances.
        The blob's own generator is the only one drawn.
        """
        timer = s32(self.u32(obj + 0x64))
        if self.u32(obj + 0x6C) and C.lt(PUS_AGE, C.from_int(timer)):
            self.delete_self(obj)
            return
        if not timer < PUS_LIFE:
            self.delete_self(obj)
            return
        if not self.u32(obj + 0x6C):
            old = self.vec(obj + 0x10)
            self.w32(obj + 0x60, C.add(self.u32(obj + 0x60), PUS_GRAVITY))
            step = []
            for j in range(3):
                now = C.add(self.u32(obj + 0x10 + 4 * j), self.u32(obj + 0x58 + 4 * j))
                self.w32(obj + 0x10 + 4 * j, now)
                step.append(C.sub(old[j], now))
            for _ in range(3):
                share = C.mul(C.from_int(self.obj_rand(obj)), RC.F_2M16)
                pos = self.vec(obj + 0x10)
                point = tuple(C.add(pos[j], C.mul(step[j], share)) for j in range(3))
                self.call('particle_spawn', PUS_FALL, point, (C.ZERO, C.ZERO, C.ZERO), C.ZERO)
            if C.le(self.u32(obj + 0x18), self.u32(obj + 0x54)):
                self.w32(obj + 0x64, 0)
                self.w32(obj + 0x6C, 1)
                entry = self.call('res_find', PUS_LUMP, PUS_SOUND)
                self.call('sound_playAtPos', entry, self.vec(obj + 0x10), C.ONE)
                base = self.vec(obj + 0x10)
                ground = self.call('terrain_height', self.u32(RC.G_WORLD), self.vec(obj + 0x10), 0x41000000)
                base = (base[0], base[1], C.add(ground, 0x41400000))
                for i in range(10):
                    radius = C.mul(C.from_int(self.obj_rand(obj)), RC.F_2M16)
                    angle = self.obj_rand(obj)
                    x = C.add(base[0], C.mul(C.mul(radius, C.cos16(angle)), 0x40C3693C))
                    y = C.add(base[1], C.mul(C.mul(radius, C.sin16(angle)), 0x40C3693C))
                    angle2 = self.obj_rand(obj)
                    spin = C.mul(C.mul(C.from_int(self.obj_rand(obj)), RC.F_2M16), 0x3F49FB1E)
                    vx = C.mul(C.mul(C.cos16(angle2), spin), 0x408DAF39)
                    vy = C.mul(C.mul(C.sin16(angle2), spin), 0x408DAF39)
                    self.wvec(obj + 0x70 + 12 * i, (x, y, base[2]))
                    self.wvec(obj + 0xE8 + 12 * i, (vx, vy, C.mul(C.ONE, 0x408DAF39)))
            if not self.u32(obj + 0x6C):
                self.w32(obj + 0x64, (self.u32(obj + 0x64) + 1) & M32)
                return
        for i in range(10):
            place, velocity = obj + 0x70 + 12 * i, obj + 0xE8 + 12 * i
            for j in range(3):
                self.w32(place + 4 * j, C.add(self.u32(place + 4 * j), self.u32(velocity + 4 * j)))
            self.w32(velocity + 8, C.add(self.u32(velocity + 8), PUS_DROP_GRAVITY))
            scale = C.mul(C.mul(C.from_int(self.obj_rand(obj)), RC.F_2M16), 0x40A729F7)
            speed = tuple(C.mul(self.u32(velocity + 4 * j), scale) for j in range(3))
            ball = self.obj_ball(obj)
            point = tuple(C.add(C.mul(ball[j], 0x403FEE34), self.u32(place + 4 * j)) for j in range(3))
            self.call('particle_spawn', PUS_DROP, point, speed, C.ZERO)
        self.w32(obj + 0x64, (self.u32(obj + 0x64) + 1) & M32)

    def arena_run(self, spell, pos):
        """SpellArena_run 0x305bbc (spell, position).

        The signed arena counter at 0x5038c8 clears object flag 2 on the creature
        when it is below 61 and sets it otherwise.  Below 30 that is the whole
        call.  From 30 on, f = 1 - (counter - 30) x 0x3bda740d and int(23 f)
        particles are laid, every fourth from 0x8e71e0 and the rest from 0x8e7190.
        Each is a sample of the creature's model (index = the spell draw modulo the
        sample count) moved back along (cos, sin, 0) of a second draw times (1 - f)
        times 10.  Both tint words, +0x90 and +0x98, become (0x56, 0x35, 0x21, 0x3d).
        The position argument is copied and not read again.
        """
        counter = self.s16(G_ARENA_COUNTER)
        creature = self.u32(spell + 0xC)
        flags = self.u32(creature + 0xC)
        self.w32(creature + 0xC, (flags & ~2) if counter < 0x3D else (flags | 2))
        if counter < 0x1E:
            return
        fade = C.sub(C.ONE, C.mul(C.sub(C.from_int(counter), 0x41F00000), 0x3BDA740D))
        count = s32(self.call('model_getSamplePointCount', self.vcall(creature, 16)))
        limit = C.to_int(C.mul(fade, 0x41B80000))
        index = 0
        while index < limit:
            model = self.vcall(self.u32(spell + 0xC), 16)
            draw = self.spell_rand(spell)
            creature = self.u32(spell + 0xC)
            sample = s32(draw) % count
            point, _extra = self.call('model_getSamplePoint', model, (creature + 0x114) & M32,
                                       self.vec(creature + 0x10), self.s16(creature + 0x38),
                                       sample, 1, 0, C.ONE)
            speed = C.mul(C.sub(C.ONE, fade), 0x41200000)
            angle = self.spell_rand(spell)
            velocity = (C.mul(C.cos16(angle), speed), C.mul(C.sin16(angle), speed),
                        C.mul(C.ZERO, speed))
            place = tuple(C.sub(point[j], C.mul(velocity[j], 0x40F25FDC)) for j in range(3))
            definition = ARENA_PARTICLES[0 if index & 3 == 0 else 1]
            self.call('particle_spawn', definition, place, velocity, C.ZERO)
            index += 1
        creature = self.u32(spell + 0xC)
        for slot, value in enumerate(ARENA_TINT + ARENA_TINT):
            self.w16(creature + 0x90 + 2 * slot, value)

    def hornomen_ctor(self, spell, kind, owner, extra):
        """SpellHornOmenEffect_ctor 0x2fc574 (spell, kind, creature, word).

        The shared draw is inlined and seeds +0x10.  The vtable lands on 0x51ae58,
        the group handle is particleGroup_create, and the end frame is the simulation
        frame plus 600.
        """
        self.w8(spell, kind)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 8, extra)
        self.w32(spell + 4, 0)
        self.w32(spell + 0x14, HO_VT)
        self.w32(spell + 0x10, self.draw())
        self.w8(spell, kind)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 8, extra)
        self.w32(spell + 0x1C, self.call('particleGroup_create'))
        self.w32(spell + 0x18, (self.u32(SA.G_SIM_FRAME) + 600) & M32)

    def hornomen_run(self, spell, pos):
        """SpellHornOmenEffect_run 0x2fc684 (spell, position).

        At the end frame +0x18, slot 1 with 3 destroys the spell.  Until then a is
        the ticks since the start, frame - end + 600.  Below 140 the creature tint
        is int(t x (225, 20, 0, 100)) with t = a x 0x3bea0ea0, and the particle
        count is int(150 t).  From 140 the tint is (225, 20, 0, 100) and the count
        is 150.  The group matrix is the one mat34_setPosRotZ left on the stack.
        Each particle is a sample of the creature's model, taken at the origin with
        facing 0, plus 3.0007868 times a ball point; the velocity is 30.000292 times
        a second ball point.  A sample count of 0 lays none.
        """
        frame = self.frame()
        if not frame < self.s32(spell + 0x18):
            self.table_call('Spell', spell, 0x14, 1, 3)
            return
        age = C.from_int(frame - self.s32(spell + 0x18) + 600)
        creature = self.u32(spell + 0xC)
        early = C.lt(age, 0x430C0000)
        if early:
            scale = C.mul(age, 0x3BEA0EA0)
            red, green, blue = (C.to_int(C.mul(scale, channel))
                                for channel in (0x43610000, 0x41A00000, 0x42C80000))
        else:
            red, green, blue = 0xE1, 0x14, 100
        for base in (0x90, 0x98):
            self.w16(creature + base, red)
            self.w16(creature + base + 2, green)
            self.w16(creature + base + 4, 0)
            self.w16(creature + base + 6, blue)
        self.call('particleGroup_setMatrix', self.u32(spell + 0x1C), 'stack')
        self.call('particleGroup_begin', self.u32(spell + 0x1C))
        count = s32(self.call('model_getSamplePointCount', self.vcall(creature, 16)))
        if count:
            made = 0
            while True:
                if early:
                    if not C.lt(C.from_int(made), C.mul(C.mul(age, 0x3BEA0EA0), 0x43160000)):
                        break
                elif made > 0x95:
                    break
                model = self.vcall(self.u32(spell + 0xC), 16)
                sample = self.spell_rand(spell) % count
                point = self.call('model_getSamplePoint', model, (self.u32(spell + 0xC) + 0x114) & M32,
                                  (C.ZERO, C.ZERO, C.ZERO), 0, sample, 0, 0, C.ONE)
                ball = self.spell_ball(spell)
                place = tuple(C.add(point[j], C.mul(ball[j], 0x40400CE4)) for j in range(3))
                velocity = tuple(C.mul(part, 0x41F00099) for part in self.spell_ball(spell))
                self.call('particle_spawn', HO_PARTICLE, place, velocity, C.ZERO)
                made += 1
        self.call('particleGroup_end', self.u32(spell + 0x1C))

    def planarsteel_ctor(self, spell, kind, owner, extra):
        """SpellPlanarSteelEffect_ctor 0x2fb728 (spell, kind, creature, word).

        The shared draw is inlined.  The light at +0x30 copies the creature's position,
        stores the colour twice, and divides 1 by a zero radius.  The end frame is the
        simulation frame plus 240, the countdown is int(the float at creature +0x20
        times 3), and the two orbit angles start at 0 and 0x7fff.  A sound plays.
        """
        self.w8(spell, kind)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 4, 0)
        seed = self.draw()
        self.w32(spell + 0xC, owner)
        self.w32(spell + 8, extra)
        self.w32(spell + 0x10, seed)
        self.w32(spell + 0x14, PS_VT)
        light = (spell + 0x30) & M32
        inverse = C.div(C.ONE, C.ZERO)
        self.w8(light + 9, 0)
        self.wvec(spell + 0x60, self.vec(owner + 0x10))
        self.w32(light + 0x28, inverse)
        self.w32(light + 0x2C, 0x3F266666)
        for off, value in ((0xA, 0x4B), (0xC, 0x4B), (0xE, 200), (0x10, 0xFF),
                           (0x12, 0x4B), (0x14, 0x4B), (0x16, 200), (0x18, 0xFF)):
            self.w16(light + off, value)
        self.w32(light + 0x20, inverse)
        self.w32(light + 0x1C, C.ZERO)
        self.w32(light + 0x24, C.ZERO)
        self.w8(light + 8, 0)
        self.call('light_link', light)
        self.w8(spell, kind)
        self.w32(spell + 8, extra)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 0x20, 0)
        self.w32(spell + 0x24, (self.u32(SA.G_SIM_FRAME) + 0xF0) & M32)
        self.w16(spell + 0x1C, C.to_int(C.mul(self.u32(owner + 0x20), 0x40400000)))
        self.w16(spell + 0x18, 0)
        self.w16(spell + 0x1A, 0x7FFF)
        entry = self.call('res_find', PS_LUMP, PS_SOUND_START)
        self.call('sound_playAtPos', entry, self.vec(owner + 0x10), C.ONE)

    def planarsteel_run(self, spell, pos):
        """SpellPlanarSteelEffect_run 0x2fb9b4 (spell, position).

        At the end frame +0x24, slot 1 with 3 destroys the spell.  Until then, with
        s = sin16(frame x 1000): the light follows the creature and its radius is
        (the kind byte + 0x42) + 10 s; the tint is the four rounded channels at
        +0x90 and again at +0x98.  The countdown +0x1c loses one.  The first time
        that halfword is negative, 60 particles of 0x8e6ba0 spawn 18 above the
        creature and a sound plays.  Two orbit points 40 out, at the countdown
        height, each get a glow and ten sparks.  Ten more sparks fall within 40 of
        the position, and ten sit 5 above the ground under it.
        """
        frame = self.frame()
        if not frame < self.s32(spell + 0x24):
            self.table_call('Spell', spell, 0x14, 1, 3)
            return
        sway = C.sin16((frame * 1000) & M32)
        creature = self.u32(spell + 0xC)
        self.wvec(spell + 0x60, self.vec(creature + 0x10))
        self.call('light_relink', (spell + 0x30) & M32)
        radius = C.add(C.from_int(self.s8(spell) + 0x42), C.mul(sway, 0x41200000))
        share = C.mul(sway, 0x42440000)
        high = C.to_int(C.add(share, 0x43480000))
        low = C.to_int(C.add(C.mul(sway, 0x40A00000), 0x41700000))
        mid = C.to_int(C.add(share, 0x42960000))
        self.w32(spell + 0x4C, radius)
        self.w32(spell + 0x54, radius)
        inverse = C.div(C.ONE, C.mul(radius, radius))
        creature = self.u32(spell + 0xC)
        for base in (0x90, 0x98):
            self.w16(creature + base, mid)
            self.w16(creature + base + 2, mid)
            self.w16(creature + base + 4, high)
            self.w16(creature + base + 6, low)
        self.w32(spell + 0x58, inverse)
        self.w32(spell + 0x50, inverse)
        count = (self.u16(spell + 0x1C) - 1) & 0xFFFF
        self.w16(spell + 0x1C, count)
        if count & 0x8000 and not self.u32(spell + 0x20):
            self.w32(spell + 0x20, 1)
            angle = 0
            for _ in range(60):
                vx = C.mul(C.cos16(angle), 0x42C80000)
                vy = C.mul(C.sin16(angle), 0x42C80000)
                vz = C.mul(C.mul(C.from_int(self.spell_rand(spell)), RC.F_2M16), 0x41A00000)
                creature = self.u32(spell + 0xC)
                place = (C.add(self.u32(creature + 0x10), C.ZERO), self.u32(creature + 0x14),
                         C.add(self.u32(creature + 0x18), 0x41900000))
                self.call('particle_spawn', PS_BURST, place, (vx, vy, vz), C.ZERO)
                angle = s16(angle + 0x444)
            entry = self.call('res_find', PS_LUMP, PS_SOUND_BURST)
            self.call('sound_playAtPos', entry, self.vec(self.u32(spell + 0xC) + 0x10), C.ONE)
        for slot in range(2):
            angle = (self.u16(spell + 0x18 + 2 * slot) - 0x5DC) & 0xFFFF
            self.w16(spell + 0x18 + 2 * slot, angle)
            x = C.mul(C.cos16(s16(angle)), 0x42200000)
            y = C.mul(C.sin16(self.s16(spell + 0x18 + 2 * slot)), 0x42200000)
            lifted = C.mul(sway, 0x42200000)
            creature = self.u32(spell + 0xC)
            height = C.from_int(self.s16(spell + 0x1C))
            colour = C.to_int(C.add(lifted, 0x42480000))
            blue = C.to_int(C.add(lifted, 0x42C80000))
            point = (C.add(x, self.u32(creature + 0x10)), C.add(y, self.u32(creature + 0x14)),
                     C.add(height, self.u32(creature + 0x18)))
            self.call('glow_add', point, colour, colour, blue, colour, self.u32(G_GLOW_TEX_C),
                      0, 2, C.ZERO, 0x457A0000)
            for definition, copies, speed in ((PS_SPARK, 6, 0x3ECCCCCC), (PS_SPARK2, 4, 0x40C00000)):
                for _ in range(copies):
                    velocity = tuple(C.mul(part, speed) for part in self.spell_ball(spell))
                    ball = self.spell_ball(spell)
                    place = tuple(C.add(C.add(ball[j], ball[j]), point[j]) for j in range(3))
                    self.call('particle_spawn', definition, place, velocity, C.ZERO)
        for _ in range(10):
            angle = s16(self.spell_rand(spell))
            radius = C.mul(C.mul(C.from_int(self.spell_rand(spell)), RC.F_2M16), 0x42200000)
            x = C.mul(C.cos16(angle), radius)
            y = C.mul(C.sin16(angle), radius)
            z = C.add(C.add(0x43480000, C.from_int(self.spell_rand(spell) % 200)), 0xC2C80000)
            place = (C.add(x, pos[0]), C.add(y, pos[1]), C.add(z, pos[2]))
            self.call('particle_spawn', PS_FALL, place, (C.ZERO, C.ZERO, 0xC2A00000), C.ZERO)
        for _ in range(10):
            angle = s16(self.spell_rand(spell))
            radius = C.mul(C.mul(C.from_int(self.spell_rand(spell)), RC.F_2M16), 0x42200000)
            x = C.mul(C.cos16(angle), radius)
            y = C.mul(C.sin16(angle), radius)
            vx = C.add(C.from_int(self.spell_rand(spell) & 1), C.MINUS_ONE)
            vy = C.add(C.from_int(self.spell_rand(spell) & 1), C.MINUS_ONE)
            place = (C.add(x, pos[0]), C.add(y, pos[1]), C.add(C.ZERO, pos[2]))
            ground = self.call('terrain_heightAtPoint', self.u32(RC.G_WORLD), place)
            place = (place[0], place[1], C.add(ground, 0x40A00000))
            self.call('particle_spawn', PS_SPARK, place, (vx, vy, C.ZERO), C.ZERO)
