#!/usr/bin/env python3
"""ref_horsemen_mount.py - reference model of the mounted Horsemen of Champions: Return to
Arms (SLUS_209.73, US v2.00): the Nightmare mount class and the pieces that join it to its
rider.

A research tool, not game code.  It sits on top of tools/ref_arena_monsters.py (which
already models the rider side: Horsemen_ctor with the mounted flag, Horsemen_run with the
mounted head, Horsemen_setState with the mounted early return and states 0x19-0x23) and
adds, as methods of Model:

    Nightmare (factory type `Nightmare`, and the mount Horsemen_ctor builds)
        nightmare_ctor           0x270968   (block, type name, position, facing, property list)
        nightmare_run            0x270bbc   slot 4
        nightmare_draw           0x270b4c   slot 5 (presentation)
        nightmare_on_hit_terrain 0x27142c   slot 10
        nightmare_on_touch_list  0x271484   slot 11
        nightmare_set_state      0x27155c   slot 27
        nightmare_seat_transform 0x2719d4   (mount, matrix out): attach point 10 of the mount
        nightmare_pick_charge_target 0x271a6c
    the rider's draw
        horsemen_draw            0x2721f8   slot 5 (presentation)
    one creature helper no model had
        angle_to_target          0x118840   Creature_angleToTarget

Every method was written from the instructions at the address in its docstring and is
compared with that code, executed under tools/ee_emu.py, by tools/difftest_horsemen_mount.py.
docs/spec/horsemen-mount.md is the prose version.  Standard library only; no game data is
embedded: strings, tables and class definitions are named by address and read through the
memory the caller supplies.

Shared-seed draws made by this code itself: none.  Every random choice of the mount is its
own generator (+0x44, GameObject_rand): set-state 0 and 1 (one draw each, the idle and
wander timers) and set-state 8 with a rider (one draw: which of the rider's three mounted
swings).  The constructor's Creature_ctor -> GameObject_ctor call-out is where a mount
draws from the shared seed, as for every creature (tools/ref_core.py owns that).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
from ref_creature import Ext, M32, s16, s32    # noqa: E402

# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
VT_NIGHTMARE = 0x5155E8                         # virtual table (39 entries)
DEF_NIGHTMARE = 0x500680                        # class definition
# The mount's property lists Horsemen_ctor hands over: 12 bytes per variant at
# 0x500848 + 12 v: decoded contents and constructor effects are in ref_horsemen_props.py.
MOUNT_PROPS = AM.NIGHTMARE_DATA
G_SIM_FRAME, G_WORLD = RC.G_SIM_FRAME, RC.G_WORLD
G_PLAYERS, REC_SIZE, REC_OBJ, G_NUM_PLAYERS = RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ, RC.G_NUM_PLAYERS

# float patterns (as loaded by lui/ori in the functions named)
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_0_1, F_0_2, F_0_3 = AM.F_0_1, AM.F_0_2, AM.F_0_3
F_0_6, F_0_8, F_0_9, F_1_2, F_1_5 = 0x3F199999, 0x3F4CCCCC, 0x3F666666, 0x3F999999, 0x3FC00000
F_10, F_24, F_30, F_36, F_42 = 0x41200000, 0x41C00000, 0x41F00000, 0x42100000, 0x42280000
F_120, F_240, F_360, F_480, F_2400 = 0x42F00000, 0x43700000, 0x43B40000, 0x43F00000, 0x45160000
F_MINUS_20 = 0xC1A00000
F_GALLOP = 0x413AAAA9                           # 11.666666 units per tick, the dead mount's run-off

MODELLED = {
    'Nightmare_ctor': 0x270968, 'Nightmare_run': 0x270BBC, 'Nightmare_draw': 0x270B4C,
    'Nightmare_onHitTerrain': 0x27142C, 'Nightmare_onTouchList': 0x271484,
    'Nightmare_setState': 0x27155C, 'Horsemen_mountSeatTransform': 0x2719D4,
    'Nightmare_pickChargeTarget': 0x271A6C, 'Horsemen_draw': 0x2721F8,
    'Creature_angleToTarget': 0x118840,
}
NIGHTMARE_BODIES = {
    0x270BBC: (4, 'nightmare_run'), 0x270B4C: (5, 'nightmare_draw'),
    0x27142C: (10, 'nightmare_on_hit_terrain'), 0x271484: (11, 'nightmare_on_touch_list'),
    0x27155C: (27, 'nightmare_set_state'), 0x2721F8: (5, 'horsemen_draw'),
}

EXTERNALS = dict(AM.EXTERNALS)
EXTERNALS.update({
    'creature_inKnockdownAnim': Ext(0x10D390, 'p', 0, 'i', '(creature) -> playing a knock-down clip'),
    'anim_pushChained': Ext(0x170938, 'ppi', 0, 'n', '(state, clip, flags)'),
    'Creature_draw': Ext(0x10B048, 'ppii', 0, 'i', '(creature, model, texture, 0) -> draw handle'),
    'model_setFade': Ext(0x1797B8, 'i', 0, 'n', '(fade 0..100, signed byte)'),
    'model_resetDrawState': Ext(0x179978, '', 0, 'n'),
    'model_getAttachWorldMatrix': Ext(0x175330, 'pvipip', 1, 'n',
                                      '(model, position, facing, anim state, attach point, matrix out; scale)'),
    'model_getAttachMatrix': Ext(0x1795F8, 'ppip', 1, 'n', '(model, anim state, attach point, matrix out; 1.0)'),
    'mat34_invert': Ext(0x164288, 'pp', 0, 'n', '(out, in)'),
    'mat34_mul': Ext(0x162808, 'ppp', 0, 'n', '(a, b, out)'),
    'model_drawShadow': Ext(0x1762E8, 'pipii', 0, 'i', '(model, 1, matrix, anim state, 0)'),
    'model_draw': Ext(0x1779B0, 'pipvppQi', 0, 'i',
                      '(model, texture, 1, centre, matrix, anim state, 64-bit show mask, shadow; 0 on the stack)'),
    'Holder.v18': Ext(0, 'pppi', 0, 'n', '(class definition, model, draw handle): draw the held parts'),
})
EXTERNALS['model_draw'].stack = 1
# argument positions passed as whole 64-bit registers (integer kind 'Q')
WIDE = {name: {i for i, k in enumerate(ext.ints) if k == 'Q'} for name, ext in EXTERNALS.items() if 'Q' in ext.ints}


class Model(AM.Model):
    """The mount and the rider's draw on a memory image; everything of
    tools/ref_arena_monsters.py besides."""

    # ---- plumbing ----------------------------------------------------------------------
    def call(self, name, *args):
        """As the arena model's, except that a constructor or helper this module has runs
        here instead of being a callback (so Horsemen_ctor builds a real mount)."""
        if name in MODELLED and name not in self.external:
            method = {'Nightmare_ctor': 'nightmare_ctor', 'Creature_angleToTarget': 'angle_to_target',
                      'Nightmare_pickChargeTarget': 'nightmare_pick_charge_target',
                      'Horsemen_mountSeatTransform': 'nightmare_seat_transform',
                      'Nightmare_setState': 'nightmare_set_state'}.get(name)
            if method is not None:
                return getattr(self, method)(*args)
        wide = WIDE.get(name, ())
        args = tuple((a & (RC.M64 if i in wide else M32)) if isinstance(a, int) else a for i, a in enumerate(args))
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        function = self.u32(table + 8 * slot + 4)
        body = NIGHTMARE_BODIES.get(function)
        if body is not None and body[0] == slot and ('Creature.v%d' % slot) not in self.external:
            this = (obj + self.s16(table + 8 * slot)) & M32
            return getattr(self, body[1])(this, *args)
        return AM.Model.vcall(self, obj, slot, *args)

    def rider(self, c):
        """The object behind the mount's rider handle +0x3c8, or 0."""
        node = self.u32(c + 0x3C8)
        return self.u32(node + 0xC) if node else 0

    # =====================================================================================
    # Creature_angleToTarget
    # =====================================================================================
    def angle_to_target(self, c):
        """Creature_angleToTarget 0x118840 -> 0 without a target, else the bearing to the
        target minus the facing, wrapped to signed 16 bits."""
        node = self.u32(c + 0x234)
        if not node:
            return 0
        t = self.u32(node + 0xC)
        dx = C.sub(self.u32(t + 0x10), self.u32(c + 0x10))
        dy = C.sub(self.u32(t + 0x14), self.u32(c + 0x14))
        return s16(C.atan2_16(dy, dx) - self.u16(c + 0x38)) & M32

    # =====================================================================================
    # Nightmare
    # =====================================================================================
    def nightmare_ctor(self, c, type_name, pos, facing, props):
        """Nightmare_ctor 0x270968 (block, type name, position, facing, property list).

        Creature_ctor with class definition 0x500680, the property list as given (for the
        mount of a rider: the list at 0x500848 + 12 v) and placeholder hit points 10.0.
        Then: table 0x5155e8, turn rate 0.6, radius 30, +0x28 = 50, rider handle +0x3c8 = 0,
        move speed 0, state 0, kind 10, +0xec = clock, HomeRange 2400, fire resistance
        1.0, +0xe0 = -20 (seat offset along the facing), visualrange 2400, creature flags
        |= 0x20200040000, scale 1.2, timer +0xf4 = 0, fade +0x3cc = 0.  anim_clear, push
        clip entry 3, Nightmare_setState(0) by a DIRECT call, event times of entries 4 and
        8 (0.5 -> 1, 0.8 -> 2, 1.2 -> 2, 1.5 -> 4), obj_runEvery60, Creature_init."""
        w32, w16, w8 = self.w32, self.w16, self.w8
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_NIGHTMARE, props, F_10)
        w32(c + 0x48, VT_NIGHTMARE)
        w32(c + 0xB0, F_0_6)
        w32(c + 0x1C, F_30)
        w8(c + 0x28, 0x32)
        w32(c + 0x3C8, 0)
        w32(c + 0xB8, 0)
        w16(c + 0x232, 0)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        w32(c + 0x3C0, C.from_int(2400))
        w32(c + 0x5C, ONE)
        w32(c + 0xE0, F_MINUS_20)
        w8(c + 0xB4, 10)
        w16(c + 0x3AE, 2400)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x20200040000)
        w32(c + 0xDC, F_1_2)
        w32(c + 0xF4, 0)
        w16(c + 0x3CC, 0)
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x1C), 1)
        self.nightmare_set_state(c, 0)
        for entry in (4, 8):
            self.set_def_entry_params(c, entry, (1, 2, 2, 4), (HALF, F_0_8, F_1_2, F_1_5))
        self.call('obj_runEvery60', c)
        self.call('Creature_init', c)

    def nightmare_draw(self, c):
        """Nightmare_draw 0x270b4c (slot 5): with a fade +0x3cc set, model_setFade(fade as a
        signed byte); below 98 the model is drawn (Creature_draw); with a fade the draw
        state is reset.  Nothing is stored into the object."""
        if self.s16(c + 0x3CC):
            self.call('model_setFade', self.s8(c + 0x3CC))
        if self.s16(c + 0x3CC) < 0x62:
            d = self.u32(c + 0x24)
            self.call('Creature_draw', c, self.u32(d + 0xC), self.u32(d + 0x14), 0)
        if self.s16(c + 0x3CC):
            self.call('model_resetDrawState')

    def nightmare_on_hit_terrain(self, c, _vec=None):
        """Slot 10, 0x27142c (mount, contact point): in the charge (state 7) set-state 3."""
        if self.s16(c + 0x232) == 7:
            self.set_state(c, 3)

    def nightmare_on_touch_list(self, c, touched):
        """Slot 11, 0x271484 (mount, zero-terminated list of touched objects): only in the
        charge (state 7).  Every touched object with object flag 0x40 (a player) that is
        not in a knock-down clip is hit through damage_apply (2 x +0xd0 .. 2 x +0xd2 as
        floats, attack rating 100000, flags 0x100041, no elements); after each such hit the
        mount turns non-solid (object flag 1) until clock + 120 (+0x3d0)."""
        if self.s16(c + 0x232) != 7:
            return
        for obj in touched:
            if not self.u32(obj + 0xC) & 0x40:
                continue
            if self.call('creature_inKnockdownAnim', obj):
                continue
            lo = C.from_int(s32(2 * self.s16(c + 0xD0)))
            hi = C.from_int(s32(2 * self.s16(c + 0xD2)))
            self.call('damage_apply', obj, c, 100000, 0, 0, 0x100041, 0, 0, lo, hi)
            self.w32(c + 0xC, self.u32(c + 0xC) | 1)
            self.w32(c + 0x3D0, self.u32(c + 0x300) + 120)

    def nightmare_pick_charge_target(self, c):
        """Nightmare_pickChargeTarget 0x271a6c (mount) -> 1 when it picked a target.

        For each player slot below the player count (re-read every step), a live player
        object (object flag 8 clear) is probed with up to eight terrain rays of length
        factor 480 from its position + (0, 0, 24) along (cos a, sin a, 0) x 360, a = 0,
        0x2000, .. ; a result strictly between 0 and 1 is a hit and ends that player's
        probes.  The first player with no hit becomes the mount's target (+0x234 cleared,
        then linked) and 1 is returned; otherwise 0."""
        u32 = self.u32
        slot = 0
        while slot < self.s32(G_NUM_PLAYERS):
            p = self.player_obj(slot)
            if p and not u32(p + 0xC) & 8:
                angle, hit, k = 0, False, 0
                while True:
                    p = self.player_obj(slot)
                    pos = self.vec(p + 0x10)
                    start = (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_24))
                    cos, sin = C.cos16(angle), C.sin16(angle)
                    direction = (C.mul(cos, F_360), C.mul(sin, F_360), ZERO)
                    t = self.call('terrain_raycast', u32(G_WORLD), start, direction, 0, F_480)
                    angle = s16(angle + 0x2000)
                    if C.lt(ZERO, t) and C.lt(t, ONE):
                        hit = True
                    k += 1
                    if k >= 8 or hit:
                        break
                if not hit:
                    self.call('handle_clear', c + 0x234)
                    p = self.player_obj(slot)
                    self.call('handle_link', c + 0x234, p, p)
                    return 1
            slot += 1
        return 0

    def nightmare_seat_transform(self, c, out):
        """Horsemen_mountSeatTransform 0x2719d4 (mount, matrix out): the world matrix of
        attach point 10 of the mount's model, placed at position + (cos f, sin f, 0) x
        +0xe0 (the seat offset, -20 from the constructor) with the mount's facing f,
        animation state and scale +0xdc.  Called by Horsemen_draw only."""
        f = self.s16(c + 0x38)
        x = C.add(self.u32(c + 0x10), C.mul(self.u32(c + 0xE0), C.cos16(f)))
        y = C.add(self.u32(c + 0x14), C.mul(self.u32(c + 0xE0), C.sin16(self.s16(c + 0x38))))
        self.call('model_getAttachWorldMatrix', self.class_model(c), (x, y, self.u32(c + 0x18)),
                  self.s16(c + 0x38), c + 0x114, 10, out, self.u32(c + 0xDC))

    def horsemen_draw(self, c):
        """Horsemen_draw 0x2721f8 (slot 5).  Mounted (+0x3c8 set): the mount's seat matrix
        (attach point 10) times the inverse of the rider's own attach point 9, a shadow,
        and model_draw with that matrix, centre (x, y, z + height / 2) and the show mask
        +0x220.  On foot: Creature_draw.  Then the held parts (holder slot 18).  Nothing is
        stored into either object."""
        u32 = self.u32
        anim = c + 0x114
        d = u32(c + 0x24)
        if u32(c + 0x3C8):
            self.nightmare_seat_transform(u32(u32(c + 0x3C8) + 0xC), 'stack')
            self.call('model_getAttachMatrix', u32(d + 0xC), anim, 9, 'stack', ONE)
            self.call('mat34_invert', 'stack', 'stack')
            self.call('mat34_mul', 'stack', 'stack', 'stack')
            centre = (u32(c + 0x10), u32(c + 0x14), C.add(u32(c + 0x18), C.mul(u32(c + 0x20), HALF)))
            d = u32(c + 0x24)
            shadow = self.call('model_drawShadow', u32(d + 0xC), 1, 'stack', anim, 0)
            d = u32(c + 0x24)
            handle = self.call('model_draw', u32(d + 0xC), u32(d + 0x14), 1, centre, 'stack', anim,
                               self.u64(c + 0x220), shadow & M32, 0)
        else:
            handle = self.call('Creature_draw', c, u32(d + 0xC), u32(d + 0x14), 0)
        d = u32(c + 0x24)
        model = self.vcall(c, 16)
        holder = u32(c + 0x50)
        if holder:
            self.holder_call(holder, 18, d, model, handle & M32)

    def nightmare_run(self, c):
        """Nightmare_run 0x270bbc (mount): one tick.

        Head: Creature_processDamage, Creature_run (non-zero ends the tick),
        Creature_updateActive (result unused), Creature_stepAnim at 0.9 in the charge
        while animation flag 0x20 is up (else 1.0), Creature_applyKnockback(0.2), slot 23
        (pick target).  Outside death the mount turns solid again (object flag 1 cleared)
        once +0x3d0 < clock.  Then the switch on the state; see docs/spec/horsemen-mount.md
        section 4 for every row."""
        u32, st = self.u32, self.set_state
        model = self.class_model(c)
        self.process_damage(c, model)
        if self.run(c, self.class_model(c)):
            return
        self.update_active(c)
        speed = F_0_9 if self.s16(c + 0x232) == 7 and self.u16(c + 0x11A) & 0x20 else ONE
        ev = self.step_anim(c, speed)
        self.call('Creature_applyKnockback', c, F_0_2)
        self.vcall(c, 23, 0)
        state = self.s16(c + 0x232)
        if state != 0x14 and self.s32(c + 0x3D0) < self.s32(c + 0x300):
            self.w32(c + 0xC, u32(c + 0xC) & 0xFFFFFFFE)
        state = self.s16(c + 0x232)
        facing = lambda: self.s16(c + 0x38)                      # noqa: E731
        see = lambda f, arc, far: self.can_see_target_in(c, f, arc, 0, ZERO, far, ZERO)   # noqa: E731
        if not 0 <= state < 0x1B:
            return
        if state == 0:                                           # 0x270d08 idle
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
            return
        if state == 1:                                           # 0x270d44 wander
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.s32(c + 0xF4) < self.s32(c + 0x300):
                return st(c, 0)
            self.move_to_dest(c)
            return
        if state == 3:                                           # 0x270d94 chase
            if not u32(c + 0x234):
                return st(c, 0)
            if self.call('creature_findEnemyInCone', c, facing(), 4000, ZERO, F_36):
                return st(c, 5)
            if see(facing(), 0x7FFF, F_36):
                return st(c, 5)
            if self.nightmare_pick_charge_target(c):
                if self.call('creature_findEnemyInCone', c, facing(), 2000, ZERO, F_240):
                    return st(c, 7)
            if see(facing(), 0x7FFF, F_120) and not see(facing(), 6000, F_120):
                return st(c, 0x17)
            self.move_to_target(c)
            return
        if state == 5:                                           # 0x270eb4 close in
            if not u32(c + 0x234):
                return st(c, 0)
            if self.call('creature_findEnemyInCone', c, facing(), 4000, ZERO, F_36):
                return st(c, 6)
            if see(0, 0x7FFF, F_36):
                if abs(s32(self.angle_to_target(c))) < 4000:
                    return st(c, 6)
                if abs(s32(self.angle_to_target(c)) + 0x4000) < 6000:
                    return st(c, 8)
                if abs(s32(self.angle_to_target(c)) + 20000) < 6000:
                    return st(c, 0x18)
                return st(c, 0x17)
            if see(facing(), 0x7FFF, F_120) and not see(facing(), 6000, F_120):
                return st(c, 0x17)
            if self.is_not_rooted(c):
                return st(c, 3)
            return
        if state in (6, 0x17, 0x18):                             # 0x271018 the kick
            self.settle(c)
            if ev & 3:
                self.call('Creature_hitAllEnemiesInArc', c, facing(), 0x1194, s32(2 * self.s16(c + 0xD0)),
                          s32(2 * self.s16(c + 0xD2)), self.s16(c + 0xD4), 1, 0, ZERO, F_42)
            if ev & 4:
                self.call('Creature_hitAllEnemiesInArc', c, facing(), 0x1194, s32(2 * self.s16(c + 0xD0)),
                          s32(2 * self.s16(c + 0xD2)), self.s16(c + 0xD4), 0x100041, 0, ZERO, F_42)
            if ev & 1:
                self.w32(c + 0x3D4, 1)
            if ev & 4:
                self.w32(c + 0x3D4, 0)
            if u32(c + 0x3D4):
                self.turn_to_target(c)
            if self.u16(c + 0x11A) & 8:
                return
            return st(c, 3)
        if state == 7:                                           # 0x2710e8 the charge
            if self.u16(c + 0x11A) & 0x20:
                self.turn_to_target(c)
            elif see(facing(), 6000, F_2400):
                self.turn_to_target(c)
            self.move_by(c, (ZERO, ZERO, ZERO))
            if self.u64(c + 0x118) & 0x180000 == 0x80000:        # animation flag 8 up, 0x10 down
                pos = self.vec(c + 0x10)
                start = (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_24))
                cos = C.cos16(self.s16(c + 0x38))
                sin = C.sin16(self.s16(c + 0x38))
                direction = (C.mul(cos, F_360), C.mul(sin, F_360), ZERO)
                t = self.call('terrain_raycast', u32(G_WORLD), start, direction, 0, F_480)
                if C.lt(ZERO, t) and C.lt(t, ONE):
                    self.call('anim_start', c + 0x114, self.clip(c, 0x3C), 0x803, F_0_1)
                    self.call('anim_syncToSimFrame', c + 0x114)
                    self.call('anim_startBlendInOut', c + 0x114, self.clip(c, 0x34), 0x810, F_0_1, F_0_1)
            if self.u16(c + 0x11A) & 0x18:
                return
            return st(c, 3)
        if state == 8:                                           # 0x2712a4 the rider swings
            if not u32(c + 0x3C8):
                return st(c, 0)
            if self.u16(self.rider(c) + 0x11A) & 8:
                return
            return st(c, 5)
        if state == 0x10:                                        # 0x2712f0 back off
            if self.is_attack_ready(c):
                return st(c, 3)
            self.flee_from_target(c, 0)
            return
        if state == 0x13:                                        # 0x2712d8 stunned
            if self.is_not_stunned(c):
                return st(c, 0)
            return
        if state == 0x14:                                        # 0x271334 dead: gallop off and fade
            f = self.s16(c + 0x38)
            cos = C.cos16(f)
            sin = C.sin16(self.s16(c + 0x38))
            dy = C.mul(sin, F_GALLOP)
            dx = C.mul(cos, F_GALLOP)
            self.w32(c + 0x14, C.add(self.u32(c + 0x14), dy))
            self.w32(c + 0x10, C.add(self.u32(c + 0x10), dx))
            self.call('obj_updateGridCell', c)
            self.w16(c + 0x3CC, self.u16(c + 0x3CC) + 1)
            self.call('Creature_deadUpdate', c, ev, (ZERO, ZERO, ZERO), 1, F_30)
            if self.s16(c + 0x3CC) >= 100:
                self.w32(c + 0xC, u32(c + 0xC) | 0x4002)
                self.call('obj_delete', c)
            return
        if state == 0x1A:                                        # 0x270ce4 reappear
            if self.s16(c + 0x3CC) > 0:
                self.w16(c + 0x3CC, self.u16(c + 0x3CC) - 1)
                return
            return st(c, 0)
        return                                                   # 2, 4, 9-0xf, 0x11, 0x12, 0x15, 0x16, 0x19

    def nightmare_set_state(self, c, state):
        """Nightmare_setState 0x27155c (mount, state): slot 27.

        Creature_filterState first (a refusal returns without storing).  Every accepted
        state is stored at +0x232 at the end; 0x12 stores the CURRENT state instead.  With
        a rider linked (+0x3c8) most cases also set a state on the rider through the
        rider's slot 27 - the only way a mounted Horsemen reaches 0x19 and up:
            0, 5, 0x12, 0x13 -> 0x1b     1, 3 -> 0x1c     7, 0x10 -> 0x1d
            6, 0x17 -> 0x1e              0x18 -> 0x1f     8 -> 0x20 + own draw % 3
            0x19 -> 0x19                 0x1a -> 0x1a     0x14 -> 0x23, then the handle dropped
        Own work per case (clip offsets of the class definition):
            0     +0xf4 = clock + own draw % 120; clip +0x1c (3, 0.3)
            1     path cleared, wander destination, +0xf4 = clock + own draw % 120 + 300;
                  clip +0x3c (0x803, 0.3), synced to the frame
            3     clip +0x3c (0x803, 0.1), synced          5  clip +0x1c (6, 0.3)
            6, 0x17, 0x18  clip +0x44 blended (8, 0.1, 0.1); latch +0x3d4 = 0
            7     clip +0x44 blended (0x24, 0.1, 0.0), clip +0x2c chained (0x80b)
            8     nothing of its own (no rider: only the store)
            0x10  attack cooldown +0x318 = 60, path cleared, clip +0x3c (0x803, 0.1), synced
            0x13  clip +0x1c (3, 0.1)
            0x14  object flag 0x4000, slot 28 (on death, 0), clip +0x2c (0x806, 0.3) - no
                  loot call
            0x19  object flags |= 0xb, +0xf4 = clock + 300
            0x1a  object flags &= ~0xb, fade +0x3cc = 120, clip +0x1c (3, 0.1)
            2, 4, 9-0xf, 0x11, 0x15, 0x16, 27 and up: only the store."""
        u32, w32 = self.u32, self.w32
        refused, state = self.filter_state(c, state)
        if refused:
            return
        anim = c + 0x114
        start = lambda off, flags, blend: self.call('anim_start', anim, self.clip(c, off), flags, blend)  # noqa: E731

        def ride(rstate):
            if u32(c + 0x3C8):
                self.vcall(self.rider(c), 27, rstate)

        s = state & M32
        if s == 0x19:
            w32(c + 0xC, u32(c + 0xC) | 0xB)
            w32(c + 0xF4, u32(c + 0x300) + 300)
            ride(0x19)
        elif s == 0x1A:
            w32(c + 0xC, u32(c + 0xC) & 0xFFFFFFF4)
            self.w16(c + 0x3CC, 120)
            start(0x1C, 3, F_0_1)
            ride(0x1A)
        elif s == 0:
            d = self.obj_rand(c)
            w32(c + 0xF4, u32(c + 0x300) + d % 120)
            start(0x1C, 3, F_0_3)
            ride(0x1B)
        elif s == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            d = self.obj_rand(c)
            w32(c + 0xF4, u32(c + 0x300) + d % 120 + 300)
            start(0x3C, 0x803, F_0_3)
            self.call('anim_syncToSimFrame', anim)
            ride(0x1C)
        elif s == 3:
            start(0x3C, 0x803, F_0_1)
            self.call('anim_syncToSimFrame', anim)
            ride(0x1C)
        elif s == 5:
            start(0x1C, 6, F_0_3)
            ride(0x1B)
        elif s in (6, 0x17, 0x18):
            self.call('anim_startBlendInOut', anim, self.clip(c, 0x44), 8, F_0_1, F_0_1)
            ride(0x1F if s == 0x18 else 0x1E)
            w32(c + 0x3D4, 0)
        elif s == 7:
            self.call('anim_startBlendInOut', anim, self.clip(c, 0x44), 0x24, F_0_1, ZERO)
            self.call('anim_pushChained', anim, self.clip(c, 0x2C), 0x80B)
            ride(0x1D)
        elif s == 8:
            if u32(c + 0x3C8):
                d = self.obj_rand(c)
                self.vcall(self.rider(c), 27, d % 3 + 0x20)
        elif s == 0x12:
            state = self.s16(c + 0x232)
            ride(0x1B)
        elif s == 0x13:
            start(0x1C, 3, F_0_1)
            ride(0x1B)
        elif s == 0x10:
            self.w16(c + 0x318, 60)
            self.clear_path(c)
            start(0x3C, 0x803, F_0_1)
            self.call('anim_syncToSimFrame', anim)
            ride(0x1D)
        elif s == 0x14:
            w32(c + 0xC, u32(c + 0xC) | 0x4000)
            self.vcall(c, 28, 0)
            start(0x2C, 0x806, F_0_3)
            if u32(c + 0x3C8):
                self.vcall(self.rider(c), 27, 0x23)
                self.call('handle_clear', c + 0x3C8)
                w32(c + 0x3C8, 0)
        self.w16(c + 0x232, state)


def shape_result(name, args, ret=0, fret=0, outs=None):
    """ref_arena_monsters.shape_result over this module's EXTERNALS."""
    saved = AM.EXTERNALS
    AM.EXTERNALS = EXTERNALS
    try:
        return AM.shape_result(name, args, ret, fret, outs)
    finally:
        AM.EXTERNALS = saved
