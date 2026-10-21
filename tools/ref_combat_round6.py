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
from ref_creature import M32, s32               # noqa: E402

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

MODELLED = {
    'poisonGasSpell_run': 0x1FD0F0,
    'DiseaseCorpse_run': 0x2CE4A4,
    'MultiFireProjectile_onHit': 0x2DA610,
    'MultiFireProjectile_end': 0x2DA928,
    'SmokeGen_run': 0x31C898,
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
