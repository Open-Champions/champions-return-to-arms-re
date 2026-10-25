#!/usr/bin/env python3
"""ref_combat_ranged.py - projectiles and ranged attacks of Champions: Return to Arms
(SLUS_209.73, US v2.00) as a reference contract on top of tools/ref_combat_runtime.py.

docs/spec/combat-projectiles.md is the prose version and labels every statement.  A
research tool, not game code.  Standard library only; no game data is embedded.

What the module adds

    RangedModel (ref_combat_runtime.CombatModel plus the projectile bodies below).
    Executed - tools/difftest_combat_ranged.py runs the original under tools/ee_emu.py and
    compares calls, stored bytes outside the stack, the shared seed and the result:

        move_and_collide        obj_moveAndCollide 0x1509f8 (projectile flight)
        projectile_ctor         Projectile_ctor 0x150e48
        missile_ctor            MissileWeapon_ctor 0x150ee4 (17 arguments)
        missile_run             MissileWeapon_run 0x15153c, kinds 0 and 3
        missile_on_touch        MissileWeapon_onTouch 0x152a18 (slot 6; every kind)
        missile_nearest_sample  MissileWeapon slot 17 0x153314
        missile_dtor            MissileWeapon_dtor 0x151454 (slot 1)
        thrown_ctor             playerProjectile_ctor 0x1bef58
        thrown_run              playerProjectile_run 0x1ba940, kinds 0, 4..
        thrown_dtor             playerProjectile_dtor 0x3c6468 (slot 1)

    RangedRuntime (ref_combat_runtime.Runtime): the same world with projectiles in it -
    a projectile is constructed by the models above in a pool block, runs from the
    every-frame list, touches through obj_moveAndCollide, damages through damage_apply
    and destroys ITSELF (slot 1 with 3, not obj_delete) inside its own run.

Restricted domain (Unsupported otherwise): MissileWeapon kinds 0 (plain arrow) and 3 in
MissileWeapon_run (kinds 1, 2, 5, 6 make effect objects and lights on impact); thrown
kinds other than 1, 2, 3 (fire, gas and exploding potions); in the runtime no deflected
missile (item_parseDescriptor with a random variant, a dropped PhProp), no orphaned
missile as attacker, no water.  The call-outs are named as round 1 names them
('Creature.v<slot>' for every virtual call).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

M32 = 0xFFFFFFFF
s8, s16, s32 = RC.s8, RC.s16, RC.s32
f32 = C.f32
ZERO, ONE = 0, 0x3F800000
Unsupported, CompositionError = T.Unsupported, T.CompositionError

# ---- addresses (Observed) -------------------------------------------------------------
G_WORLD = RC.G_WORLD                    # 0x44fdc8
G_SIM_FRAME = T.G_SIM_FRAME             # 0x44fdcc
G_LEVEL_FLAGS = RC.G_LEVEL_FLAGS        # 0x44fe08: 0x100 cold level, 0x40000 stone level (Inferred)
G_PVP_MODE_A = T.G_PVP_MODE_A           # 0x4f711c
G_SKILL_TABLE = 0x41B170                # g_skillTable[id] = 0x41b170 + 4 id
G_MODEL_TABLE = 0x3E9CE0                # item model rows, 16 bytes; +8 / +0xc the two model words
VT_PROJECTILE, VT_MISSILE, VT_THROWN = 0x5120B8, 0x50E5A0, 0x50E470

# strings the bodies pass (addresses of the executable's own text; not copied here)
S_FX_LUMP = 0x532478                    # lump name used by MissileWeapon (another copy at 0x535ef0)
S_FX_LUMP_THROWN = 0x535EF0
S_SPLASH_FMT = 0x532458                 # obj_moveAndCollide splash sample, '%d' = 1
S_STONE_HIT = 0x532538                  # MissileWeapon_run impact sample name (no conversions)
S_STONE_HIT_THROWN = 0x537B70           # the same text for playerProjectile_run
S_CAST = {1: 0x532498, 2: 0x532480, 5: 0x5324B0, 6: 0x5324C8}       # launch sounds by kind
S_POTIONS = (0x532570, 0x532580, 0x532590)                          # three item names (deflection)

# float constants (bit patterns as the code loads them)
F_DT = 0x3C888888                       # 1/60
F_TENTH = 0x3DCCCCCC
F_TWO = 0x40000000
F_TWELVE = 0x41400000
F_GRAVITY = 0x410FFFFF                  # 8.999999 per frame (thrown weapons only)
F_FIVE = 0x40A00000
F_INV65536 = 0x37800000
F_EIGHTEEN = 0x41900000
F_THREE_QUARTERS = 0x3F400000
F_BIG = 0x4CBEBC20                      # 1e8
F_HUNDRED = 0x42C80000

# virtual tables (Observed: the words of the executable; slot -> function)
MISSILE_SLOTS = {0: 0x3C62C0, 1: 0x151454, 2: 0x3C7E88, 3: 0x3C7E90, 4: 0x15153C, 5: 0x15253C,
                 6: 0x152A18, 7: 0x3C7EB0, 8: 0x3C7EB8, 9: 0x3C7EC0, 10: 0x3C7EC8, 11: 0x3C7EF0,
                 12: 0x3C7EF8, 13: 0x3C7F20, 14: 0x3C7F28, 15: 0x12D498, 16: 0x3C8120, 17: 0x153314}
THROWN_SLOTS = dict(MISSILE_SLOTS)
THROWN_SLOTS.update({0: 0x3C64D8, 1: 0x3C6468, 4: 0x1BA940, 5: 0x1BA730, 15: 0x12D9E0})

# type-info getters and their descriptors (Observed)
TYPEINFO = {
    0x3C2608: (0x908130, b'8Creature'), 0x3C9558: (0x9089E0, b'13AutoContainer'),
    0x3C3308: (0x908140, b'9Container'), 0x3CC62C: (0x908E20, b'8Skeleton'),
    0x3C7BC8: (0x908560, b'15PushPhysicsProp'), 0x3C62C0: (0x908330, b'13MissileWeapon'),
}
TYPEINFO_NAMES = {'AutoContainer_typeinfo': 0x3C9558, 'Container_typeinfo': 0x3C3308,
                  'Skeleton_typeinfo': 0x3CC62C, 'PushPhysicsProp_typeinfo': 0x3C7BC8}

# slot-16 bodies ("the model of this object") met on the projectile path (Observed)
MODEL_GETTERS = {0x3C2738: 'class', 0x3C3B38: 'player', 0x3C8120: 'none'}


class RangedModel(T.CombatModel):
    """CombatModel with the projectile bodies.  Bodies run here when a virtual call or a
    direct call reaches them; naming the call in `external` makes it a call-out."""

    RANGED_BODIES = {
        0x152A18: (6, 'missile_on_touch'), 0x153314: (17, 'missile_nearest_sample'),
        0x15153C: (4, 'missile_run'), 0x1BA940: (4, 'thrown_run'),
    }
    DTORS = (0x151454, 0x3C6468)        # slot 1: through destroy_hook when one is set (the runtime)
    destroy_hook = None
    RANGED_INTERNAL = {
        'obj_moveAndCollide': 'move_and_collide', 'Projectile_ctor': 'projectile_ctor',
        'MissileWeapon_ctor': 'missile_ctor', 'playerProjectile_ctor': 'thrown_ctor',
        'MissileWeapon_dtor': 'missile_dtor',
    }
    RANGED_MODELLED = {
        'obj_moveAndCollide': 0x1509F8, 'Projectile_ctor': 0x150E48, 'MissileWeapon_ctor': 0x150EE4,
        'MissileWeapon_run': 0x15153C, 'MissileWeapon_onTouch': 0x152A18, 'MissileWeapon_slot17': 0x153314,
        'MissileWeapon_dtor': 0x151454, 'playerProjectile_ctor': 0x1BEF58, 'playerProjectile_run': 0x1BA940,
        'playerProjectile_dtor': 0x3C6468,
    }

    def call(self, name, *args):
        method = self.RANGED_INTERNAL.get(name)
        if method is not None and name not in self.external:
            return getattr(self, method)(*args)
        return T.CombatModel.call(self, name, *args)

    def knows(self, fn):
        return fn in self.RANGED_BODIES or fn in MODEL_GETTERS or fn in TYPEINFO or \
            fn in (0x3C7E88,) or T.CombatModel.knows(self, fn)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        fn = self.u32(table + 8 * slot + 4)
        this = (obj + self.s16(table + 8 * slot)) & M32
        name = 'Creature.v%d' % slot
        if name not in self.external:
            if slot == 1 and fn in self.DTORS and self.destroy_hook is not None:
                self.vcalls.append((name, (this,) + tuple(args)))
                return self.destroy_hook(this, *args)
            body = self.RANGED_BODIES.get(fn)
            if body is not None:
                self.vcalls.append((name, (this,) + tuple(args)))
                return getattr(self, body[1])(this, *args)
        return T.CombatModel.vcall(self, obj, slot, *args)

    # ---- small helpers -------------------------------------------------------------------
    def handle_obj(self, head):
        node = self.u32(head)
        return self.u32(node + 0xC) if node else 0

    def cstr(self, addr, limit=64):
        out = bytearray()
        while len(out) < limit:
            b = self.mem.load(addr + len(out), 1)
            if b == 0:
                break
            out.append(b)
        return bytes(out)

    def text(self, addr):
        """A string argument as the call-out sees it (kind 'S')."""
        return ('str', self.cstr(addr))

    def type_of(self, obj):
        """Virtual slot 0 (the type-info getter): a descriptor address."""
        table = self.u32(obj + 0x48)
        fn = self.u32(table + 4)
        if fn in TYPEINFO and 'Creature.v0' not in self.external:
            return TYPEINFO[fn][0]
        return self.call('Creature.v0')

    def static_type(self, name):
        """A direct call of a type-info getter (AutoContainer_typeinfo ...)."""
        return self.call(name)

    def same_type(self, a, b):
        """rtti_typeInfoEquals 0x3b1250: the same descriptor, or equal name strings (the
        name pointer is the descriptor's first word)."""
        if a == b:
            return True
        return self.cstr(self.u32(a)) == self.cstr(self.u32(b))

    def model_of(self, obj):
        """Virtual slot 16 (the drawn model): a body for the getters met here."""
        table = self.u32(obj + 0x48)
        fn = self.u32(table + 8 * 16 + 4)
        kind = MODEL_GETTERS.get(fn)
        if kind is None or 'Creature.v16' in self.external:
            return self.vcall(obj, 16)
        self.vcalls.append(('Creature.v16', (obj,)))
        if kind == 'class':
            return self.u32(self.u32(obj + 0x24) + 0xC)
        if kind == 'player':
            return self.u32(obj + 0x544)
        return 0

    def sample_point(self, model, host, index, out, second, third):
        """model_getSamplePoint(model, host anim, host position, host facing, index, out,
        second out, third out; host scale) - a call-out; returns (point, weight)."""
        res = self.call('model_getSamplePoint', model, host + 0x114, self.vec(host + 0x10), self.s16(host + 0x38),
                        index, 1 if out else 0, 1 if second else 0, 1 if third else 0, self.u32(host + 0xDC))
        if res is None:
            return (0, 0, 0), 0
        if not isinstance(res, tuple) or not res or not isinstance(res[0], tuple):
            res = (res,)
        point = res[0] if out else (0, 0, 0)
        weight = res[1] if second and len(res) > 1 else 0
        return point, weight

    # =====================================================================================
    # obj_moveAndCollide 0x1509f8 (obj, vel) -> bits: 1 below the terrain, 2 an overlap
    # =====================================================================================
    def move_and_collide(self, obj, vel):
        u32 = self.u32
        step = [C.mul(vel[i], F_DT) for i in range(3)]
        pos = [C.add(u32(obj + 0x10 + 4 * i), step[i]) for i in range(3)]
        for i in range(3):
            self.w32(obj + 0x10 + 4 * i, pos[i])
        self.call('obj_updateGridCell', obj)
        result = 0
        h = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
        if C.lt(u32(obj + 0x18), h):
            result = 1
            k = F_TENTH
            while True:
                back = [C.mul(step[i], k) for i in range(3)]
                cand = (C.sub(u32(obj + 0x10), back[0]), C.sub(u32(obj + 0x14), back[1]),
                        C.sub(u32(obj + 0x18), back[2]))
                h2 = self.call('terrain_height', u32(G_WORLD), cand, u32(obj + 0x1C))
                if C.le(h2, cand[2]):
                    break
                k = C.add(k, F_TENTH)
                if not C.lt(k, F_TWO):
                    break
            self.wvec(obj + 0x10, cand)
            if s8(self.u8(obj + 0x50)) == 0:
                if self.call('water_test', u32(G_WORLD), self.vec(obj + 0x10), 0, F_TWELVE):
                    self.w8(obj + 0x50, 1)
                    self.obj_rand(obj)
                    name = self._format(S_SPLASH_FMT, 1)
                    res = self.call('res_find', self.text(S_FX_LUMP), name)
                    self.call('sound_playOnObject', res, obj, 0x3E4CCCCC)
                    self.call('water_disturb', u32(G_WORLD), self.vec(obj + 0x10), 0x442F0000, 0x41C00000)
        r, hgt = u32(obj + 0x1C), u32(obj + 0x20)
        x, y, z = self.vec(obj + 0x10)
        lo = (C.sub(x, r), C.sub(y, r), C.sub(z, hgt))
        hi = (C.add(x, r), C.add(y, r), C.add(z, hgt))
        owner = self.handle_obj(obj + 0x4C)
        found = self.call('world_collectObjectsInBox', lo, hi, 0x100)
        for o in found or ():
            flags = u32(o + 0xC)
            if flags & 0x201 or flags & 0x20000000 or o == obj or o == owner:
                continue
            oz, oh, mz, mh = u32(o + 0x18), u32(o + 0x20), u32(obj + 0x18), u32(obj + 0x20)
            if C.lt(C.add(oz, oh), C.sub(mz, mh)):
                continue
            if C.lt(C.add(mz, mh), oz):
                continue
            dx = C.sub(u32(obj + 0x10), u32(o + 0x10))
            dy = C.sub(u32(obj + 0x14), u32(o + 0x14))
            d2 = C.add(C.mul(dx, dx), C.mul(dy, dy))
            rr = C.add(u32(obj + 0x1C), u32(o + 0x1C))
            if not C.lt(d2, C.mul(rr, rr)):
                continue
            result |= 2
            self.vcall(o, 6, obj)
            self.vcall(obj, 6, o)
        return result

    def _format(self, fmt_addr, *values):
        """The text libc_sprintf makes from a format of the executable (only %d is met)."""
        text = self.cstr(fmt_addr)
        if b'%d' in text:
            text = text.replace(b'%d', str(s32(values[0])).encode(), 1)
        return ('str', text)

    # =====================================================================================
    # Projectile_ctor 0x150e48 (obj, pos*, owner, classDef)
    # =====================================================================================
    def projectile_ctor(self, obj, pos, owner, class_def):
        self.call('GameObject_ctor', obj, tuple(pos), class_def, 0)
        flags = self.u32(obj + 0xC) | 0x4081
        self.w32(obj + 0x4C, 0)
        self.w32(obj + 0x1C, F_TWELVE)
        self.w32(obj + 0x48, VT_PROJECTILE)
        self.w32(obj + 0xC, flags)
        self.w8(obj + 0x50, 0)
        if owner:
            self.call('handle_link', obj + 0x4C, owner, owner)

    # =====================================================================================
    # MissileWeapon_ctor 0x150ee4 (obj, kind, modelA, modelB, pos*, vel*, facing, owner,
    #   launch sample, impact sample, dmin, dmax, weapon rating, item flags, attack,
    #   damage flags, item)
    # =====================================================================================
    def missile_ctor(self, obj, kind, model_a, model_b, pos, vel, facing, owner, launch, impact,
                     dmin, dmax, wrating, iflags, attack, dflags, item):
        u32, w32, w16, w8 = self.u32, self.w32, self.w16, self.w8
        kind = s32(kind)
        pos, vel = tuple(pos), tuple(vel)
        self.call('Projectile_ctor', obj, pos, owner, 0)
        w32(obj + 0x48, VT_MISSILE)
        for k in range(5):
            w32(obj + 0x5C + 0x18 * k, 0)
        L = obj + 0x174
        w32(obj + 0x124, 0)
        w32(obj + 0x128, 0)
        w8(L + 0x9, 0)
        self.wvec(obj + 0x1A4, pos)
        w16(L + 0x18, -0x20)
        w16(L + 0x10, -0x20)
        w32(L + 0x24, 0x43280000)
        w32(L + 0x28, 0x38149B92)
        w32(L + 0x1C, 0x43280000)
        w32(L + 0x20, 0x38149B92)
        w32(L + 0x2C, 0)
        w16(L + 0xA, 0xFF)
        w16(L + 0xC, 0x9B)
        w16(L + 0xE, 0)
        w16(L + 0x12, 0xFF)
        w16(L + 0x14, 0x9B)
        w16(L + 0x16, 0)
        w8(L + 0x8, 0)
        self.call('light_link', L)
        w8(obj + 0x28, 0x48)
        w8(obj + 0xFE, 0)
        w16(obj + 0xFC, 0)
        w16(obj + 0xFA, 0)
        w32(obj + 0xD0, kind)
        if ((kind - 5) & M32) < 2:
            w16(obj + 0x180, 0x9B)
            w16(obj + 0x182, 0xFF)
            w16(obj + 0x186, 0)
            w16(obj + 0x17E, 0)
            w16(obj + 0x188, 0x9B)
            w16(obj + 0x18A, 0xFF)
        kind = s32(u32(obj + 0xD0))
        if kind in S_CAST:
            res = self.call('res_find', self.text(S_FX_LUMP), self.text(S_CAST[kind]))
            self.call('sound_playOnObject', res, obj, ONE)
            kind = s32(u32(obj + 0xD0))
        if kind in (0, 3):
            self.call('light_unlink', L)
        elemental = 0
        if item and u32(item):
            if s8(self.u8(u32(item) + 0x1E)) == 6:
                w32(obj + 0x1C, 0x41C00000)
                w32(obj + 0x20, 0x42C80000)
            for wanted in (0x18, 0x16, 0x15, 0x17, 0x26):
                value = 0
                for k in range(4):
                    if self.s16(item + 0x24 + 8 * k) == wanted:
                        value = self.s16(item + 0x26 + 8 * k)
                        break
                if value:
                    w32(obj + 0x170, 0)
                    elemental = 1
                    break
        if not elemental and u32(obj + 0xD0) == 0 and not u32(G_LEVEL_FLAGS) & 0x100:
            trail = self.call('trail_create', 1, 0x7A, 0, 0x80, 0x80, 0x80, 0x20, 0x3E1A9FBE)
            w32(obj + 0x170, trail)
            self.call('trail_addPoint', trail, self.vec(obj + 0x10))
        w32(obj + 0xD4, dmin)
        w32(obj + 0xD8, dmax)
        w32(obj + 0xDC, wrating)
        w32(obj + 0xE0, iflags)
        w32(obj + 0xE4, attack)
        w32(obj + 0xE8, dflags)
        self.wvec(obj + 0x1B0, vel)
        w16(obj + 0x38, facing)
        flags = u32(obj + 0xC) | 0x4001
        w32(obj + 0x1C0, model_a)
        w32(obj + 0x1C4, model_b)
        w32(obj + 0x12C, item)
        w32(obj + 0xC, flags)
        w32(obj + 0xF4, 0)
        w8(obj + 0xCC, 0)
        w8(obj + 0xF8, 1)
        w32(obj + 0xEC, u32(G_SIM_FRAME) + 0x12C)
        self.call('obj_runEveryFrame', obj)
        w8(obj + 0xCD, 1)
        if launch:
            w32(obj + 0xF0, self.call('sound_playSample', launch, self.vec(obj + 0x10), ONE, ONE, ZERO))
        else:
            w32(obj + 0xF0, 0)
        w32(obj + 0x1BC, impact)

    # =====================================================================================
    # playerProjectile_ctor 0x1bef58 (obj, modelA, modelB, pos*, vel*, facing, owner, launch,
    #   impact, dmin, dmax, weapon rating, item flags, attack, kind, item)
    # =====================================================================================
    def thrown_ctor(self, obj, model_a, model_b, pos, vel, facing, owner, launch, impact, dmin, dmax,
                    wrating, iflags, attack, kind, item):
        kind = s8(kind)
        self.call('MissileWeapon_ctor', obj, 0, model_a, model_b, tuple(pos), tuple(vel), facing, owner, launch,
                  impact, dmin, dmax, wrating, iflags, attack, 4, item)
        self.w32(obj + 0x1C8, 0)
        self.w16(obj + 0x1CC, 0x7D0)
        self.w32(obj + 0x48, VT_THROWN)
        self.w8(obj + 0x1CE, kind)
        if kind == 0:
            self.w16(obj + 0x1CC, -0x7D0)
        if owner:
            self.call('handle_link', obj + 0x1C8, owner, owner)

    # =====================================================================================
    # MissileWeapon_run 0x15153c (slot 4)
    # =====================================================================================
    def missile_run(self, this):
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
                    self.mem.poke(this + 0x10 + 4 * i, 4, point[i] & M32)     # written by the callee
            self.call('obj_updateGridCell', this)
            return
        if s8(self.u8(this + 0xCC)):
            self.vcall(this, 1, 3)
            return
        kind = s32(u32(this + 0xD0))
        if kind not in (0, 3):
            raise Unsupported('MissileWeapon_run of kind %d (impact effects) is not in this contract' % kind)
        spin = self.u16(this + 0xFA)
        if s16(spin):
            self.w16(this + 0xFC, self.u16(this + 0xFC) + spin)
        r = self.call('obj_moveAndCollide', this, self.vec(this + 0x1B0))
        res = r & ~2 & M32
        if s8(self.u8(this + 0xCC)):
            res |= 2
        if res:
            self.w32(this + 0xEC, 0)
            if res == 2:
                cc = s8(self.u8(this + 0xCC))
                if cc == 2:
                    self.call('fx_spawn', 0x11 if u32(G_LEVEL_FLAGS) & 0x100 else 2, self.vec(this + 0x10))
                elif cc == 3:
                    self.w32(this + 0xEC, u32(G_SIM_FRAME))
                else:
                    self.w32(this + 0xEC, u32(G_SIM_FRAME) + 1)
            elif res == 1:
                name = self._format(S_STONE_HIT)
                if u32(G_LEVEL_FLAGS) & 0x40000:
                    self.call('fx_spawn', 8, self.vec(this + 0x10))
                elif u32(G_LEVEL_FLAGS) & 0x100:
                    self.call('fx_spawn', 0x11, self.vec(this + 0x10))
                else:
                    self.call('fx_spawn', 2, self.vec(this + 0x10))
                hit = self.call('res_find', self.text(S_FX_LUMP), name)
                self.call('sound_playOnObject', hit, this, ONE)
                impact = u32(this + 0x1BC)
                if impact:
                    self.call('sound_playSample', impact, self.vec(this + 0x10), ONE, ONE, ZERO)
        kind = s32(u32(this + 0xD0))
        puff = False
        if kind == 0 and u32(G_LEVEL_FLAGS) & 0x100:
            if self.obj_rand(this) % 3 == 0:
                spot = list(self.vec(this + 0x10))
                d = self.obj_rand(this)
                spot[2] = C.add(spot[2], C.mul(C.mul(C.from_int(d), F_INV65536), F_EIGHTEEN))
                self.call('fx_spawn', 0x11, tuple(spot))
                puff = True
        if not puff and u32(this + 0x170):
            self.call('trail_addPoint', u32(this + 0x170), self.vec(this + 0x10))
        if not s32(u32(G_SIM_FRAME)) < s32(u32(this + 0xEC)):
            self.vcall(this, 1, 3)

    # =====================================================================================
    # playerProjectile_run 0x1ba940 (slot 4)
    # =====================================================================================
    def thrown_run(self, this):
        u32 = self.u32
        kind = self.u8(this + 0x1CE)
        if kind in (1, 2, 3):
            raise Unsupported('playerProjectile_run of kind %d (a thrown potion) is not in this contract' % kind)
        spin = self.s16(this + 0x1CC)
        if kind == 0:
            if spin < 0x1388:
                self.w16(this + 0x1CC, spin + 0xC8)
        elif ((kind - 4) & 0xFF) < 3:
            self.w16(this + 0x1CC, spin + 0xBB8)
        elif not spin < -0x1387:
            self.w16(this + 0x1CC, spin - 0xC8)
        name = self._format(S_STONE_HIT_THROWN)
        self.w32(this + 0x1B8, C.sub(u32(this + 0x1B8), F_GRAVITY))
        r = self.call('obj_moveAndCollide', this, self.vec(this + 0x1B0))
        res = r & ~2 & M32
        if s8(self.u8(this + 0xCC)):
            res |= 2
        if res:
            self.w32(this + 0xEC, 0)
            kind = s8(self.u8(this + 0x1CE))
            if res == 2:
                if not s8(self.u8(this + 0xCC)):
                    if kind in (0, 4, 5, 6):
                        self.call('fx_spawn', 2, self.vec(this + 0x10))
                    hit = self.call('res_find', self.text(S_FX_LUMP_THROWN), name)
                    self.call('sound_playOnObject', hit, this, ONE)
            elif res == 1:
                spot = list(self.vec(this + 0x10))
                ground = self.call('terrain_height', u32(G_WORLD), self.vec(this + 0x10), u32(this + 0x1C))
                spot[2] = C.add(ground, F_FIVE)
                if kind in (0, 4, 5, 6):
                    self.call('fx_spawn', 2, tuple(spot))
                hit = self.call('res_find', self.text(S_FX_LUMP_THROWN), name)
                self.call('sound_playOnObject', hit, this, ONE)
        if s32(u32(G_SIM_FRAME)) < s32(u32(this + 0xEC)):
            return
        self.handle_obj(this + 0x1C8)               # the owner, read and not used by these kinds
        self.vcall(this, 1, 3)

    # =====================================================================================
    # MissileWeapon_onTouch 0x152a18 (slot 6) (this, other)
    # =====================================================================================
    def missile_on_touch(self, this, other):
        u32 = self.u32
        if s8(self.u8(this + 0xCC)):
            return
        owner = self.handle_obj(this + 0x4C)
        if other == 0:
            return
        if not u32(other + 0xC) & 0x20:
            if self.same_type(self.type_of(other), self.static_type('AutoContainer_typeinfo')):
                self.vcall(other, 2, 0, 0, ZERO)
            elif self.same_type(self.type_of(other), self.static_type('Container_typeinfo')):
                self.vcall(other, 2, 0, 0, ZERO)
            self.w8(this + 0xCC, 2)
            return
        if owner and u32(owner + 0xC) & 0x20:
            if not self.vcall(owner, 20, other):
                return
        node = u32(this + 0x124)
        while node:
            if u32(node + 0xC) == other:
                return
            node = u32(node)
        pierce = unblockable = 0
        kind = s32(u32(this + 0xD0))
        if owner and u32(owner + 0xC) & 0x40 and kind in (0, 3):
            rank = self.call('player_getSkillRank', u32(owner + 0x3C8), 0x5D)
            u, p = self.call('SkillPenetratingArrows_getStats01Fraction', u32(G_SKILL_TABLE + 4 * 0x5D), rank)
            if C.le(C.mul(C.from_int(self.draw()), F_INV65536), u):
                unblockable = 1
            if C.le(C.mul(C.from_int(self.draw()), F_INV65536), p):
                pierce = 1
            else:
                self.call('handle_clear', this + 0x124)
        oflags = u32(other + 0xC)
        if oflags & 0x20 and owner and u32(owner + 0xC) & 0x40:
            if oflags & 0x40 and u32(G_PVP_MODE_A) == 0:
                return
            if oflags & 0x1000000 and not oflags & 0x40:
                return
            if not pierce and u32(this + 0xD0) == 0:
                self.call('handle_link', this + 0x128, other, other)
                index = self.vcall(this, 17, other)
                self.w32(this + 0xF4, index)
                if index == 0:
                    self.call('handle_clear', this + 0x128)
                elif self.same_type(self.type_of(other), self.static_type('Skeleton_typeinfo')):
                    self.call('handle_clear', this + 0x128)
                else:
                    model = self.model_of(other)
                    if model:
                        self.sample_point(model, other, u32(this + 0xF4), True, False, True)
                        self.call('mat3_transpose')
                        self.call('mat3_setIdentity')
                        self.call('mat3_rotateAxis', 2, self.s16(this + 0x38))
                        self.call('mat3_mul', this + 0x100)
                self.w32(this + 0xC, u32(this + 0xC) | 1)
            kind = s32(u32(this + 0xD0))
            override = {1: 0x20, 5: 0x400, 6: 0x80}.get(kind)
            if override is not None:
                self.w32(this + 0xE8, override)
                self.w32(this + 0xE4, 0x2710)
        chance = 0
        player = 0
        oflags = u32(other + 0xC)
        if oflags & 0x40:
            slot = u32(other + 0x3C8)
            rank = self.call('player_getSkillRank', slot, 2)
            f = self.call('SkillDodge_getStat0Fraction', u32(G_SKILL_TABLE + 8), rank)
            chance = s32(C.to_int(C.mul(f, F_HUNDRED)))
            player = other
            rank = self.call('player_getSkillRank', u32(other + 0x3C8), 0x53)
            f = self.call('SkillDodge_getStat0Fraction', u32(G_SKILL_TABLE + 4 * 0x53), rank)
            second = s32(C.to_int(C.mul(f, F_HUNDRED)))
            if chance < second:
                chance = second
        elif oflags & 0x20:
            if self.vcall(other, 36):
                level = self.vcall(other, 36)
                chance = s32(self.skill_call(u32(G_SKILL_TABLE + 8), 11, 0, level, 0))
        roll = self.draw() % 100 + 1
        oflags = u32(other + 0xC)
        if roll < chance:
            if oflags & 0x40:
                self.call('Player_blockSparks', player, 0)
            for name in S_POTIONS:
                self.call('item_parseDescriptor', self.text(name), -1, 0)
            a, b = u32(this + 0x1C0), u32(this + 0x1C4)
            if a and b:
                drop = True
                for _ in S_POTIONS:
                    index = s32(self.call('item_getResourceIndex'))
                    if u32(G_MODEL_TABLE + 8 + 16 * index) == a:
                        drop = False
                        break
                if drop:
                    block = self.call('pool_new', 0x248)
                    if block:
                        self.call('PhProp_ctor4', block, self.vec(this + 0x10), a, b, 1, 0x2A, 0, ONE)
            self.call('obj_delete', this)
            return
        if oflags & 0x20:
            flags = u32(this + 0xE8) | (0x40 if unblockable else 0)
            attacker = owner if owner else this
            result = self.call('damage_apply', other, attacker, u32(this + 0xE4), u32(this + 0xDC), u32(this + 0xE0),
                               flags & M32, u32(this + 0x12C), 0, C.from_int(s32(u32(this + 0xD4))),
                               C.from_int(s32(u32(this + 0xD8))))
            if result == 1:
                self.w8(this + 0xCC, 3 if u32(other + 0xC) & 0x40 else 1)
            else:
                self.w8(this + 0xCC, 2)
        elif self.same_type(self.type_of(other), self.static_type('PushPhysicsProp_typeinfo')):
            self.w8(this + 0xCC, 2)
        if pierce and s8(self.u8(this + 0xCC)):
            self.call('handle_link', this + 0x124, other, other)
            self.w8(this + 0xCC, 0)

    # =====================================================================================
    # MissileWeapon slot 17 0x153314 (this, other) -> the sample point to stick to
    # =====================================================================================
    def missile_nearest_sample(self, this, other):
        if other == 0:
            return 0
        model = self.model_of(other)
        count = s32(self.call('model_getSamplePointCount', model)) if model else 0
        if count == 0:
            return 0
        best = ZERO
        for k in range(max(count, 0)):
            _p, w = self.sample_point(model, other, k, True, True, False)
            if C.lt(best, w):
                best = w
        nearest, index = F_BIG, 0
        for k in range(max(count, 0)):
            p, w = self.sample_point(model, other, k, True, True, False)
            if C.lt(w, C.mul(best, F_THREE_QUARTERS)):
                continue
            d = [C.sub(self.u32(this + 0x10 + 4 * i), p[i]) for i in range(3)]
            dist = C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
            if C.lt(dist, nearest):
                nearest, index = dist, k
        return index

    # =====================================================================================
    # Destructors: MissileWeapon_dtor 0x151454, playerProjectile_dtor 0x3c6468
    # =====================================================================================
    def missile_dtor(self, this, flags):
        u32 = self.u32
        self.w32(this + 0x48, VT_MISSILE)
        if u32(this + 0x170):
            self.call('trail_release', u32(this + 0x170))
        self.call('light_dtor', this + 0x174, 2)
        self.call('handle_clear', this + 0x128)
        self.call('handle_clear', this + 0x124)
        for off in (0xBC, 0xA4, 0x8C, 0x74, 0x5C):
            self.call('handle_clear', this + off)
        self.w32(this + 0x48, VT_PROJECTILE)
        self.call('handle_clear', this + 0x4C)
        self.call('GameObject_dtor', this, 0)
        if flags & 1:
            self.call('pool_free', this)

    def thrown_dtor(self, this, flags):
        self.w32(this + 0x48, VT_THROWN)
        self.call('handle_clear', this + 0x1C8)
        self.call('MissileWeapon_dtor', this, 0)
        if flags & 1:
            self.call('pool_free', this)


# =======================================================================================
# The runtime with projectiles
# =======================================================================================

PROJECTILE_HEADS = (0x4C, 0x5C, 0x74, 0x8C, 0xA4, 0xBC, 0x124, 0x128)
MISSILE_SIZE, THROWN_SIZE = 0x1C8, 0x1D0


class RangedRuntime(T.Runtime):
    """ref_combat_runtime.Runtime whose world can hold projectiles.  Typical use:

        rt = RangedRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((300.0, 0.0, 0.0))
        a = rt.spawn_missile(p, (0.0, 0.0, 36.0), (1000.0, 0.0, 0.0), dmin=4, dmax=8, attack=100000)
        rt.tick()  ...

    spawn_missile / spawn_thrown stand for the call sites that make projectiles (the bow
    and throw release of Player_run state 0, monster run functions): AUTHORED set-up that
    calls the EXECUTED constructors with the arguments the caller passes.  Everything that
    follows - running, flight, touches, damage, self-destruction - is the models'."""

    RUN_BODIES = dict(T.Runtime.RUN_BODIES)
    RUN_BODIES.update({0x15153C: 'missile', 0x1BA940: 'thrown'})
    DTOR_BODIES = dict(T.Runtime.DTOR_BODIES)
    DTOR_BODIES.update({0x151454: 'missile', 0x3C6468: 'thrown'})
    PRESENTATION = ('light_link', 'light_unlink', 'light_dtor', 'light_relink', 'trail_addPoint',
                    'trail_release', 'mat3_transpose', 'mat3_setIdentity', 'mat3_rotateAxis', 'mat3_mul',
                    'Player_blockSparks', 'water_disturb')

    def __init__(self, *args, **kwargs):
        T.Runtime.__init__(self, *args, **kwargs)
        self.model = RangedModel(self.mem, self.services)
        self.model.destroy_hook = lambda addr, flags: self._slot1(self.world.obj(addr), flags)
        for name in self.PRESENTATION:
            self.services.table[name] = self.services._presentation(name)
        for table, slots in ((VT_MISSILE, MISSILE_SLOTS), (VT_THROWN, THROWN_SLOTS)):
            for slot, fn in slots.items():
                self.mem.poke(table + 8 * slot, 2, 0)
                self.mem.poke(table + 8 * slot + 4, 4, fn)
        names = self._alloc_fixture(0x100)
        at = names
        for fn, (desc, name) in sorted(TYPEINFO.items()):
            for i, b in enumerate(name + b'\0'):
                self.mem.poke(at + i, 1, b)
            self.mem.poke(desc, 4, at)
            at += (len(name) + 0x10) & ~0xF
        self.projectiles = {}                   # address -> 'missile' | 'thrown'
        self._pending = None
        self.dodge = {}                         # (slot, skill) -> fraction (fixture; empty = rank 0)

    # ---- spawning (AUTHORED call sites, EXECUTED constructors) ----------------------------
    def _new_block(self, size):
        addr = self.world.pool.new(size)
        if addr == 0:
            raise Unsupported('the pool refused the block')
        return addr

    def spawn_missile(self, owner, pos, vel, facing=0, dmin=1, dmax=2, attack=100, dflags=4, item=0, kind=0,
                      launch=0, impact=0, wrating=0, iflags=0, models=(0, 0)):
        """pool_new(0x1c8) and MissileWeapon_ctor with the arguments a caller passes: a
        monster passes its own damage range (+0xd0, +0xd2), attack (+0xd4), damage flags 4,
        no item (Orc_run 0x2a2718-0x2a278c); the player's bow passes record +0xd0/+0xd4/
        +0xcc, the bow's rating and flags and the bow item (Player_run 0x1a9188-0x1a9244)."""
        addr = self._new_block(MISSILE_SIZE)
        self.projectiles[addr] = 'missile'
        self.model.missile_ctor(addr, kind, models[0], models[1], [f32(v) for v in pos],
                                [f32(v) for v in vel], facing & 0xFFFF, owner, launch, impact, dmin & M32,
                                dmax & M32, wrating & M32, iflags & M32, attack & M32, dflags & M32, item)
        self.kinds[addr] = 'missile'
        return addr

    def spawn_thrown(self, owner, pos, vel, facing=0, dmin=1, dmax=2, attack=100000, kind=4, item=0, models=(0, 0)):
        """pool_new(0x1d0) and playerProjectile_ctor as a throw passes them."""
        addr = self._new_block(THROWN_SIZE)
        self.projectiles[addr] = 'thrown'
        self.model.thrown_ctor(addr, models[0], models[1], [f32(v) for v in pos], [f32(v) for v in vel],
                               facing & 0xFFFF, owner, 0, 0, dmin & M32, dmax & M32, 0, 0, attack & M32, kind, item)
        self.kinds[addr] = 'missile'
        return addr

    # ---- services the projectile bodies reach -----------------------------------------------
    def svc_GameObject_ctor(self, obj, pos, class_def, props):
        if class_def or props:
            raise Unsupported('a projectile with a class definition')
        self.world.construct(obj, list(pos))
        for off in PROJECTILE_HEADS + ((0x1C8,) if self.projectiles.get(obj) == 'thrown' else ()):
            self.mem.head(obj + off)

    def svc_terrain_height(self, world, pos, radius):
        return self.terrain.height_below(pos, radius)

    def svc_water_test(self, world, pos, flag, radius):
        if self.terrain.water_test(pos, radius):
            raise Unsupported('a projectile entering water')
        return 0

    def svc_res_find(self, lump, entry):
        return 0

    def svc_sound_playSample(self, sample, pos, *rest):
        self.note('presentation', 'sound_playSample')
        return 0

    def svc_trail_create(self, *args):
        self.note('presentation', 'trail_create')
        return 0

    def svc_obj_updateActive(self, obj, was, radius):
        return self.model.obj_update_active(obj, was, radius)

    def svc_AutoContainer_typeinfo(self):
        return TYPEINFO[0x3C9558][0]

    def svc_Container_typeinfo(self):
        return TYPEINFO[0x3C3308][0]

    def svc_Skeleton_typeinfo(self):
        return TYPEINFO[0x3CC62C][0]

    def svc_PushPhysicsProp_typeinfo(self):
        return TYPEINFO[0x3C7BC8][0]

    def svc_SkillPenetratingArrows_getStats01Fraction(self, skill, rank):
        if rank:
            raise Unsupported('Penetrating Arrows at rank %d (statistics not in the contract)' % rank)
        return (ZERO, ZERO)

    def svc_SkillDodge_getStat0Fraction(self, skill, rank):
        if rank:
            raise Unsupported('Dodge at rank %d (statistics not in the contract)' % rank)
        return ZERO

    def svc_item_parseDescriptor(self, *args):
        raise Unsupported('a deflected missile (item_parseDescriptor, a dropped prop)')

    def svc_GameObject_dtor(self, obj, flags):
        self._pending = obj

    def svc_pool_free(self, obj):
        if self._pending != obj:
            raise CompositionError('pool_free of 0x%x without its GameObject_dtor' % obj)

    def svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit, dmin, dmax):
        if attacker in self.projectiles:
            raise Unsupported('a missile whose owner is gone is its own attacker (damage_apply with the missile)')
        if isinstance(desc, int) and desc:
            raise Unsupported('a weapon item as damage descriptor is outside this contract')
        return T.Runtime.svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, 0, no_crit, dmin, dmax)

    # ---- slot 4 and slot 1 of projectiles -------------------------------------------------
    def _slot4(self, obj):
        fn = self._fn(obj.addr, 4)
        kind = self.RUN_BODIES.get(fn)
        if kind == 'missile':
            self.note('run', obj.addr, kind)
            self.model.missile_run(obj.addr)
        elif kind == 'thrown':
            self.note('run', obj.addr, kind)
            self.model.thrown_run(obj.addr)
        else:
            T.Runtime._slot4(self, obj)

    def _slot1(self, obj, flags):
        fn = self._fn(obj.addr, 1)
        kind = self.DTOR_BODIES.get(fn)
        if kind not in ('missile', 'thrown'):
            return T.Runtime._slot1(self, obj, flags)
        addr = obj.addr
        self.note('destroy', addr, kind)
        self._pending = None
        if kind == 'missile':
            self.model.missile_dtor(addr, flags)
        else:
            self.model.thrown_dtor(addr, flags)
        if self._pending != addr:
            raise CompositionError('the projectile destructor did not reach GameObject_dtor')
        block = self.world._block_size(addr)
        self.world.destroy(obj, flags)
        self.mem.forget_heads(addr, addr + block)
        self.kinds.pop(addr, None)
        self.projectiles.pop(addr, None)
