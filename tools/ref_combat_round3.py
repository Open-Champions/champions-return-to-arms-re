#!/usr/bin/env python3
"""ref_combat_round3.py - combat bodies round 2 left refused, on the same memory image.

A research tool, not game code.  Each method was written from the instructions at the
address in its docstring.  tools/difftest_combat_round3.py runs the original in
tools/ee_emu.py and compares calls, stored bytes, the shared seed and the result.
docs/spec/combat-round3.md is the prose.

This module subclasses tools/ref_skills_a.py's Model and only ADDS methods.  It does not
change the round-1 or round-2 reference APIs, their pinned vectors, or the bodies those
difftests already compare.

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
import ref_combat_ranged as RR                  # noqa: E402
from ref_creature import M32, s8, s16, s32      # noqa: E402

# DiseaseCloud (table 0x5186f0, 0x64 bytes; symbols/runtime.tsv names that table).
# Cross-checked with research-fx docs/effects.md section 17: the cloud's damage_apply
# has no attacker.
DC_VT = 0x5186F0
DC_PARTICLES = (0x8E5320, 0x8E5370, 0x8E53C0)   # three streams, speeds 6, 6 and 12
DC_SPEEDS = (0x40C00000, 0x40C00000, 0x41400000)
G_SKILL_DISEASE = 0x41B1E4                      # g_skillTable[29], the Disease Effect skill

# GutChunk (table 0x50f3b8).  The name block is Observed at 0x4f86a0.
GUT_BASE = 0x4F86A0
GUT_VT = 0x50F3B8
G_GORE = 0x44FDC0                               # gore option; below 2 forces the blood bit

# StrongStancePhantom (table 0x50f448, clone size 0x3d8).
PHANTOM_VT = 0x50F448
F_1_25 = 0x3FA00000
F_75 = 0x42960000
F_240 = 0x43700000
F_24 = 0x41C00000
F_10 = 0x41200000
F_5 = 0x40A00000

# MissileWeapon impact samples, played before the kind-0 stone visual.  Kinds 0 and 3
# never reach these.  Kind 5's flight then spawns 32 particles from definition 0x6e00c0.
S_KIND12_IMPACT = 0x5324E0
S_KIND5_IMPACT = 0x5324F8
S_KIND6_IMPACT = 0x532518
P_KIND5 = 0x6E00C0
P_KIND1_A = 0x6DFFD0
P_KIND1_B = 0x6E0020
P_KIND6 = 0x6E0070
F_KIND6_SCALE = 0x41ACCCCC
F_KIND6_BIAS = 0x3FD10624
F_INV65536 = 0x37800000
F_KIND1_LEAD = 0x3D75C28F
F_KIND1_SMALL = 0x3C23D70A
F_KIND1_STEP = 0x3DCCCCCC
F_KIND1_DIR = 0x40800000
F_KIND5_DRAG = 0x3DA3D70A
F_KIND5_DIR = 0x41421062
F_RING2 = 0x40000000
F_LIGHT_A = 0x437F0000
F_LIGHT_B = 0x431B0000
F_LIGHT_C = 0xC2000000
F_LIGHT_D = 0x43580000
F_LIGHT_E = 0x42F00000
F_OUTER72 = 0x42900000

MODELLED = {
    'DiseaseCloud_ctor': 0x2CE610, 'DiseaseCloud_run': 0x2CE6E0,
    'GutChunk_ctor': 0x201958,
    'StrongStancePhantom_ctor': 0x1618D4, 'StrongStancePhantom_run': 0x161A54,
}


class Model(SA.Model):
    """Round-3 combat bodies.  Inherited methods (SpellDiseaseEffect, GameObject_ctor,
    the creature base) stay as the modules that already executed them."""

    # =====================================================================================
    # DiseaseCloud
    # =====================================================================================
    def diseasecloud_ctor(self, obj, pos, level, owner):
        """DiseaseCloud_ctor 0x2ce610 (cloud, position, level word, owner or 0).

        GameObject_ctor with no class and no properties (one shared draw inside it).
        Table 0x5186f0.  The owner handle +0x4c is cleared, then linked when an owner
        was passed.  +0x50 = the level word, +0x58 = 48, +0x54 = frame + 240, +0x60 = 20,
        +0x5c = 10.0, object flags |= 3, then obj_runEveryFrame."""
        self.gameobject_ctor(obj, pos, 0, 0)
        self.w32(obj + 0x48, DC_VT)
        self.w32(obj + 0x4C, 0)
        if owner:
            self.call('handle_link', obj + 0x4C, owner, owner)
        self.w32(obj + 0x50, level)
        self.w32(obj + 0x58, 0x30)
        self.w32(obj + 0x54, (self.u32(SA.G_SIM_FRAME) + 0xF0) & M32)
        self.w32(obj + 0x60, 0x14)
        self.w32(obj + 0x5C, F_10)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 3)
        self.call('obj_runEveryFrame', obj)

    def diseasecloud_run(self, obj):
        """DiseaseCloud_run 0x2ce6e0, object slot 4.

        Until frame >= +0x54:
          the radius +0x5c grows by 0.5 while it is strictly below the integer +0x58;
          three streams of (+0x58 / 10) particles, each placed at position + a unit-ball
          point times the radius, velocity a second ball point times 6, 6 and 12
          (definitions 0x8e5320, 0x8e5370, 0x8e53c0; the cloud's own generator +0x44);
          on a frame divisible by 30, every object in the box position +/- trunc(radius)
          except the owner, and except when both the owner and the victim are players
          (flag 0x40), takes damage_apply(victim, attacker 0, 100000, 0, 0, flags
          0x1000040, entry (0x26, +0x60, +0x60, 0), 0; 0, 0).  An empty owner handle
          deals nothing.
        Then slot 1 with 3 destroys the cloud.  Agrees with research-fx effects.md
        section 17: the attacker argument is 0."""
        frame = self.frame()
        if not frame < self.s32(obj + 0x54):
            self.delete_self(obj)
            return
        cap = self.s32(obj + 0x58)
        if C.lt(self.u32(obj + 0x5C), C.from_int(cap)):
            self.w32(obj + 0x5C, C.add(self.u32(obj + 0x5C), C.HALF))
        count = SA.quot(cap, 10)
        for definition, speed in zip(DC_PARTICLES, DC_SPEEDS):
            i = 0
            while i < count:
                ball = self.obj_ball(obj)
                radius = self.u32(obj + 0x5C)
                pos = self.vec(obj + 0x10)
                point = tuple(C.add(C.mul(ball[j], radius), pos[j]) for j in range(3))
                velocity = tuple(C.mul(b, speed) for b in self.obj_ball(obj))
                self.call('particle_spawn', definition, point, velocity, C.ZERO)
                i += 1
        if SA.rem(frame, 30):
            return
        radius = C.from_int(C.to_int(self.u32(obj + 0x5C)))
        pos = self.vec(obj + 0x10)
        low = tuple(C.sub(pos[j], radius) for j in range(3))
        high = tuple(C.add(pos[j], radius) for j in range(3))
        found = self.call('world_collectObjectsInBox', low, high, 0x40) or ()
        for victim in found:
            node = self.u32(obj + 0x4C)
            if not node:
                continue
            owner = self.u32(node + 0xC)
            if owner == victim:
                continue
            if self.u32(owner + 0xC) & 0x40 and self.u32(victim + 0xC) & 0x40:
                continue
            value = self.u32(obj + 0x60) & 0xFFFF
            self.call('damage_apply', victim, 0, 100000, 0, 0, 0x1000040,
                      SA.descriptor((0x26, value, value, 0)), 0, C.ZERO, C.ZERO)

    def disease_attach(self, victim, attacker, skill=None):
        """The disease branch of damage_apply, Observed at 0x1e9e28, composed onto the
        executed SpellDiseaseEffect_ctor 0x2d5594.

        pool_new(0x1b0).  With a block: seconds = trunc(5 - the victim's disease
        resistance at +0x68, times 5), level 0, the victim, the attacker (0 when the
        cloud is the source) and the skill (the word at 0x41b1e4, g_skillTable[29],
        when the caller does not pass one).  creature_addSpell is called even when the
        pool returned nothing.  The sound that precedes the pool and the rest of
        damage_apply are not this function."""
        if skill is None:
            skill = self.u32(G_SKILL_DISEASE)
        block = self.call('pool_new', 0x1B0)
        if block:
            seconds = C.to_int(C.sub(F_5, C.mul(self.u32(victim + 0x68), F_5)))
            self.disease_spell_ctor(block, seconds, 0, victim, attacker, skill)
        self.call('creature_addSpell', victim, block or 0)
        return block or 0

    # =====================================================================================
    # GutChunk
    # =====================================================================================
    def gutchunk_ctor(self, obj, pos, kind, bits):
        """GutChunk_ctor 0x201958 (chunk, position, kind, bits).

        PhProp_ctor 0x155a0c is a callback: (chunk, position, word at 0x4f86a0, word at
        0x4f86f0, word at 0x4f86a0+0x60 when bits bit 1 is set else +0x58, kind, 0xb41, 0;
        1.0).  Then table 0x50f3b8, +0x248 = bits, and when the gore option at 0x44fdc0
        is below 2 that word is stored again with bit 0 set.  Position +0x10 is copied
        to +0x250 (what PhProp left there), +0x25c = 2, byte +0x260 = 0."""
        bits &= M32
        base = GUT_BASE
        name = self.u32(base + (0x60 if bits & 2 else 0x58))
        self.call('PhProp_ctor', obj, tuple(pos), self.u32(base), self.u32(base + 0x50), name,
                  kind & M32, 0xB41, 0, C.ONE)
        self.w32(obj + 0x248, bits)
        self.w32(obj + 0x48, GUT_VT)
        if s32(self.u32(G_GORE)) < 2:
            self.w32(obj + 0x248, bits | 1)
        self.wvec(obj + 0x250, self.vec(obj + 0x10))
        self.w32(obj + 0x25C, 2)
        self.w8(obj + 0x260, 0)

    # =====================================================================================
    # StrongStancePhantom (also the resurrect phantom: same constructor, flag 1)
    # =====================================================================================
    def strongstance_phantom_ctor(self, obj, target, name, speed, flag):
        """StrongStancePhantom_ctor 0x1618d4 (phantom, target, animation name, speed int, flag).

        Creature_ctor is a callback: (phantom, no type name, the target's position, the
        target's facing +0x38, the target's class +0x24, no properties; hit points 0).
        Then +0x3c8 = 0, table 0x50f448, anim_clear of the embedded animation at +0x114,
        res_find of the class's lump and the name, anim_startBlendInOut of that result
        with flags 0x802 and both blends 0.  Creature flags +0xa8 gain bit 63.  Object
        flags |= 0x4005.  +0x2e0 copies the target's +0x2e0.  +0x2e8 = float(speed) x
        1.25.  Radius +0x1c = 24.  +0x3d4 = the flag.  Both timers +0x3cc and +0x3d0 are
        240 when the flag is set and 75 when it is not.  obj_runEveryFrame(phantom), then
        the target is linked at +0x3c8."""
        pos = self.vec(target + 0x10)
        self.call('Creature_ctor', obj, 0, pos, self.s16(target + 0x38) & M32, self.u32(target + 0x24),
                  0, C.ZERO)
        self.w32(obj + 0x3C8, 0)
        self.w32(obj + 0x48, PHANTOM_VT)
        self.call('anim_clear', obj + 0x114)
        lump = self.u32(self.u32(obj + 0x24))
        resource = self.call('res_find', lump, name) or 0
        self.call('anim_startBlendInOut', obj + 0x114, resource, 0x802, C.ZERO, C.ZERO)
        self.w64(obj + 0xA8, self.u64(obj + 0xA8) | (1 << 63))
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4005)
        self.w16(obj + 0x2E0, self.u16(target + 0x2E0))
        self.w32(obj + 0x2E8, C.mul(C.from_int(s32(speed)), F_1_25))
        self.w32(obj + 0x1C, F_24)
        self.w32(obj + 0x3D4, flag & M32)
        timer = F_240 if flag else F_75
        self.w32(obj + 0x3CC, timer)
        self.w32(obj + 0x3D0, timer)
        self.call('obj_runEveryFrame', obj)
        self.call('handle_link', obj + 0x3C8, target, target)

    def strongstance_phantom_run(self, obj):
        """StrongStancePhantom_run 0x161a54, object slot 4.

        Creature_stepAnim with scale 1, Creature_applyKnockback with 0.5,
        Creature_moveBy of a zero velocity.  Timer +0x3cc loses 1.  When the value just
        stored is strictly below 1, obj_delete.  A timer of 240 therefore lasts 239
        steps; a timer of 75 lasts 74."""
        self.call('Creature_stepAnim', obj, C.ONE)
        self.call('Creature_applyKnockback', obj, C.HALF)
        self.call('Creature_moveBy', obj, (C.ZERO, C.ZERO, C.ZERO))
        left = C.sub(self.u32(obj + 0x3CC), C.ONE)
        self.w32(obj + 0x3CC, left)
        if C.lt(left, C.ONE):
            self.call('obj_delete', obj)


class ArrowModel(RR.RangedModel):
    """MissileWeapon_run for kinds 1, 2, 5 and 6.  Kinds 0 and 3 stay on RangedModel.
    obj_moveAndCollide stays a call-out: the ranged difftest runs that body for real."""

    def __init__(self, mem, callbacks=None, external=()):
        if 'obj_moveAndCollide' not in external:
            external = tuple(external) + ('obj_moveAndCollide',)
        RR.RangedModel.__init__(self, mem, callbacks, external)

    def _spread(self, obj):
        """One coordinate of the rejection ball: draw/65536, doubled, then minus 1."""
        unit = C.mul(C.from_int(self.obj_rand(obj)), F_INV65536)
        return C.sub(C.add(unit, unit), C.ONE)

    def _ball(self, obj):
        """Three coordinates whose squared length is not strictly above 1.  The object's
        own generator at +0x44, the same one GameObject_rand advances."""
        while True:
            x, y, z = self._spread(obj), self._spread(obj), self._spread(obj)
            length = C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))
            if not C.lt(C.ONE, length):
                return x, y, z

    def missile_run(self, this):
        """MissileWeapon_run 0x15153c while +0xd0 is 1, 2, 5 or 6.

        A carried arrow and an arrow whose splash byte is already set take the same
        exits as kinds 0 and 3.  A nonzero move result plays the kind's impact sample
        (0x5324e0 for kinds 1 and 2, 0x5324f8 for kind 5, 0x532518 for kind 6) and stores 0
        at +0xec.  A
        result of exactly 1 also plays the sample at +0x1bc, and kind 1 first spawns
        effect 5.  The stone-hit effect is kinds 0 and 3 only.

        Kind 1 then builds (draw & 3) + 3 particle props (pool 0x148, ParticleProp_ctor
        with 8) and the same light as kind 2.  Every frame it emits 24 pairs.  The
        shared position is the arrow plus its velocity times 0x3d75c28f, plus a
        rejection-ball axis times velocity times 0x3c23d70a, plus ((draw % 40) - 20)
        times 0x3dcccccc.  The direction is a second ball times 4.  The first particle
        of the pair is definition 0x6dffd0; the second is 0x6e0020 at that position
        minus velocity times 0x3d75c28f.

        Kind 2 then: fx_ringBurst at scale 2, pool_new(0xbc) and LightEffect_ctor when a
        block comes back, world_damageInRadius of the owner at +0x4c (or 0) for the word
        at +0xd8, inner 24 and outer 72.

        Kind 5 then: fx_spawn 10, the same pool and a LightEffect whose first colour
        word is 0 and whose third is 0x437f0000.  No radius damage.  Every frame, hit or
        miss, kind 5 emits 32 particles from 0x6e00c0.  Each particle's position is the
        arrow position plus its velocity times 0x3da3d70a plus a rejection-ball direction
        times 10; the particle direction is a second ball times 0x41421062; the speed
        argument is 0.

        Kind 6 on a hit emits 100 particles from 0x6e0070 at the arrow position.  The
        direction is a rejection ball times 0x41accccc, with 0x3fd10624 added to z, and
        the speed argument is 0.  Its light matches kind 5.  Every frame, if the owner
        is a player (flag 0x40), it calls player_getPassiveLevel(owner +0x3c8, 0x1000)
        and ignores the result.

        All four then copy the position to +0x1a4 and light_relink +0x174.  No cold
        puff and no trail.  Slot 1 with 3 runs when the frame is no longer strictly
        below +0xec, so a hit destroys the arrow on that same frame."""
        kind = s32(self.u32(this + 0xD0))
        if kind not in (1, 2, 5, 6):
            return RR.RangedModel.missile_run(self, this)
        u32 = self.u32
        if u32(this + 0x128):
            active = self.obj_update_active(this, s8(self.u8(this + 0xCD)), 0x1E0)
            self.w8(this + 0xCD, active)
            host = self.handle_obj(this + 0x128)
            if u32(host + 0xC) & 0x20 and self.u64(host + 0xA8) & (1 << 41):
                self.call('obj_delete', this)
                return
            model = self.model_of(host)
            if model:
                point, _w = self.sample_point(model, host, u32(this + 0xF4), True, False, False)
                for i in range(3):
                    self.mem.poke(this + 0x10 + 4 * i, 4, point[i] & M32)
            self.call('obj_updateGridCell', this)
            return
        if s8(self.u8(this + 0xCC)):
            self.vcall(this, 1, 3)
            return
        spin = self.u16(this + 0xFA)
        if s16(spin):
            self.w16(this + 0xFC, self.u16(this + 0xFC) + spin)
        result = self.call('obj_moveAndCollide', this, self.vec(this + 0x1B0))
        res = result & ~2 & M32
        if s8(self.u8(this + 0xCC)):
            res |= 2
        if res:
            sample = {5: S_KIND5_IMPACT, 6: S_KIND6_IMPACT}.get(kind, S_KIND12_IMPACT)
            hit = self.call('res_find', RR.S_FX_LUMP, sample)
            self.call('sound_playOnObject', hit, this, C.ONE)
            self.w32(this + 0xEC, 0)
            if res == 1 and kind == 1:
                self.call('fx_spawn', 5, self.vec(this + 0x10))
            if res == 1:
                impact = u32(this + 0x1BC)
                if impact:
                    self.call('sound_playSample', impact, self.vec(this + 0x10), C.ONE, C.ONE, C.ZERO)
            pos = self.vec(this + 0x10)
            if kind == 1:
                count = (self.obj_rand(this) & 3) + 3
                for _step in range(count):
                    block = self.call('pool_new', 0x148)
                    if block:
                        self.call('ParticleProp_ctor', block, pos, 8)
                block = self.call('pool_new', 0xBC)
                if block:
                    self.call('LightEffect_ctor', block, pos, 0, 0,
                              F_LIGHT_A, F_LIGHT_B, C.ZERO, F_LIGHT_C, C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                              F_LIGHT_D, F_LIGHT_E, C.ONE, C.ONE)
            elif kind == 2:
                self.call('fx_ringBurst', pos, F_RING2)
                block = self.call('pool_new', 0xBC)
                if block:
                    self.call('LightEffect_ctor', block, pos, 0, 0,
                              F_LIGHT_A, F_LIGHT_B, C.ZERO, F_LIGHT_C, C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                              F_LIGHT_D, F_LIGHT_E, C.ONE, C.ONE)
                node = u32(this + 0x4C)
                attacker = u32(node + 0xC) if node else 0
                self.call('world_damageInRadius', attacker, pos, u32(this + 0xD8), 0, 0, 0, F_24, F_OUTER72)
            elif kind == 5:
                self.call('fx_spawn', 10, pos)
                block = self.call('pool_new', 0xBC)
                if block:
                    self.call('LightEffect_ctor', block, pos, 0, 0,
                              C.ZERO, F_LIGHT_B, F_LIGHT_A, F_LIGHT_C, C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                              F_LIGHT_D, F_LIGHT_E, C.ONE, C.ONE)
            else:
                for _count in range(100):
                    x, y, z = self._ball(this)
                    direction = (C.mul(x, F_KIND6_SCALE), C.mul(y, F_KIND6_SCALE),
                                 C.add(C.mul(z, F_KIND6_SCALE), F_KIND6_BIAS))
                    self.call('particle_spawn', P_KIND6, pos, direction, C.ZERO)
                block = self.call('pool_new', 0xBC)
                if block:
                    self.call('LightEffect_ctor', block, pos, 0, 0,
                              C.ZERO, F_LIGHT_B, F_LIGHT_A, F_LIGHT_C, C.ZERO, C.ZERO, C.ZERO, C.ZERO,
                              F_LIGHT_D, F_LIGHT_E, C.ONE, C.ONE)
        if kind == 1:
            self._kind1_flight(this)
        elif kind == 6:
            node = u32(this + 0x4C)
            owner = u32(node + 0xC) if node else 0
            if owner and u32(owner + 0xC) & 0x40:
                self.call('player_getPassiveLevel', u32(owner + 0x3C8), 0x1000)
        elif kind == 5:
            pos = self.vec(this + 0x10)
            vel = self.vec(this + 0x1B0)
            shifted = tuple(C.add(pos[i], C.mul(vel[i], F_KIND5_DRAG)) for i in range(3))
            for _count in range(32):
                x, y, z = self._ball(this)
                centre = (C.add(shifted[0], C.mul(x, F_10)), C.add(shifted[1], C.mul(y, F_10)),
                          C.add(shifted[2], C.mul(z, F_10)))
                dx, dy, dz = self._ball(this)
                direction = (C.mul(dx, F_KIND5_DIR), C.mul(dy, F_KIND5_DIR), C.mul(dz, F_KIND5_DIR))
                self.call('particle_spawn', P_KIND5, centre, direction, C.ZERO)
        self.wvec(this + 0x1A4, self.vec(this + 0x10))
        self.call('light_relink', this + 0x174)
        if not s32(u32(RC.G_SIM_FRAME)) < s32(u32(this + 0xEC)):
            self.vcall(this, 1, 3)

    def _kind1_flight(self, this):
        """The 24 pairs kind 1 emits on the way to light_relink.  Observed at 0x151df0."""
        pos = self.vec(this + 0x10)
        vel = self.vec(this + 0x1B0)
        base = tuple(C.add(pos[i], C.mul(vel[i], F_KIND1_LEAD)) for i in range(3))
        for _count in range(24):
            ball = self._ball(this)
            place = []
            for i in range(3):
                jitter = C.mul(C.from_int(self.obj_rand(this) % 40 - 20), F_KIND1_STEP)
                drag = C.mul(C.mul(vel[i], F_KIND1_SMALL), ball[i])
                place.append(C.add(C.add(base[i], jitter), drag))
            place = tuple(place)
            dx, dy, dz = self._ball(this)
            direction = (C.mul(dx, F_KIND1_DIR), C.mul(dy, F_KIND1_DIR), C.mul(dz, F_KIND1_DIR))
            self.call('particle_spawn', P_KIND1_A, place, direction, C.ZERO)
            shifted = tuple(C.sub(place[i], C.mul(vel[i], F_KIND1_LEAD)) for i in range(3))
            self.call('particle_spawn', P_KIND1_B, shifted, direction, C.ZERO)
