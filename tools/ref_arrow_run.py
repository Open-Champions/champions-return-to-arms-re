"""ref_arrow_run.py - the arrows a SkeletonBow (Skeleton kind 4) releases in Skeleton_run
state 8, from construction to destruction: flight, hit, stick (or not), expiry and the
destructor.

Reference contract, executed against the original by tools/difftest_arrow_run.py
(docs/spec/arrow-run.md is the prose).  Everything here is Observed by that difftest unless
a docstring says otherwise.  Standard library only; no game data is embedded.

The four arrows (tools/ref_skeleton_run.py ARROWS, the release 0x2a6ed4-0x2a738c):

    element 0 and others   MissileWeapon (table 0x50e5a0, block 0x1c8)
        MissileWeapon_ctor 0x150ee4      MissileWeapon_run 0x15153c (slot 4)
        MissileWeapon_onTouch 0x152a18 (slot 6)   MissileWeapon_nearestSamplePoint 0x153314 (17)
        MissileWeapon_dtor 0x151454 (slot 1)
    element 1              FireArrowProjectile (table 0x518de0, block 0xb0)
        _ctor 0x2d6238, _run 0x2d66ac (4), _onHit 0x2d685c (6), _end 0x2d6bb8, _dtor 0x3cde04 (1)
    element 2              ColdArrowProjectile (table 0x518ef8, block 0xb0)
        _ctor 0x2d6fb4, _run 0x2d73c8 (4), _onHit 0x2d7aac (6), _end 0x2d7ecc, _dtor 0x3cdf4c (1)
    element 6              ExplodeArrowProjectile (table 0x519240, block 0x74)
        _ctor 0x2daeb4, _run 0x2db17c (4), _onHit 0x2db4f0 (6), _explode 0x2db50c, _dtor 0x3ce30c (1)

and under them, run for real in the same difftest: Projectile_ctor 0x150e48, GameObject_ctor
0x14cb10 (with its ONE SHARED DRAW), obj_moveAndCollide 0x1509f8, GameObject_rand 0x1509d0,
the handle lists (handle_link 0x1a1738, handle_clear 0x1a1698) and the Skill statistics the
element arrows ask (Skill slots 10-14 through the Skill object's table +0x60).

Where the bodies come from
    MissileWeapon_*: written here (own reading of 0x150ee4-0x153514; the earlier contract
        tools/ref_combat_ranged.py was the guide).  The three element-arrow destructors:
        written here (own reading of 0x3cde04-0x3ce378); like MissileWeapon_dtor they end
        with a tail jump to pool_free 0x150470 (a call-out).
    The element arrows' constructors, runs, hit handlers and end functions: the methods of
        tools/ref_skills_b.py (borrowed: executed there by tools/difftest_skills_b.py for
        casts by players and monsters); here they run on the Skeleton's own arguments,
        chained frame after frame on real state.
    GameObject_ctor: tools/ref_skills_a.py's body (borrowed), so that the arrow's own
        generator +0x44 and the shared draw are the original's.

Shared seed 0x404464: ONE draw per arrow (GameObject_ctor).  A MissileWeapon touch adds ONE
draw for every creature or player victim that passed the owner's enemy test (the deflection
roll), plus damage_apply's own (a call-out here).  A player-owned kind-0/3 arrow adds two
(Penetrating Arrows); a monster's never.  The element arrows' damage rolls, flight particles
and explosions use the arrow's OWN generator +0x44 (GameObject_rand), never 0x404464, except
the ExplodeArrow's LightEffect (a GameObject: one shared draw when the pool gives a block).
The cosmetic generator 0x404460 is not touched by any body of this module.
"""
import ref_core as C
import ref_creature as RC
import ref_skills_a as SA
import ref_skills_b as SB
from ref_creature import Ext, M32, s8, s16, s32

# ---- entries (Observed) --------------------------------------------------------------------
GAMEOBJECT_CTOR, PROJECTILE_CTOR, MOVE_AND_COLLIDE = 0x14CB10, 0x150E48, 0x1509F8
MISSILE_CTOR, MISSILE_DTOR, MISSILE_RUN = 0x150EE4, 0x151454, 0x15153C
MISSILE_ON_TOUCH, MISSILE_NEAREST = 0x152A18, 0x153314
FIRE_CTOR, FIRE_RUN, FIRE_ON_HIT, FIRE_END, FIRE_DTOR = 0x2D6238, 0x2D66AC, 0x2D685C, 0x2D6BB8, 0x3CDE04
COLD_CTOR, COLD_RUN, COLD_ON_HIT, COLD_END, COLD_DTOR = 0x2D6FB4, 0x2D73C8, 0x2D7AAC, 0x2D7ECC, 0x3CDF4C
EXPLODE_CTOR, EXPLODE_RUN, EXPLODE_ON_HIT, EXPLODE_EXPLODE, EXPLODE_DTOR = \
    0x2DAEB4, 0x2DB17C, 0x2DB4F0, 0x2DB50C, 0x3CE30C

# function bodies: name -> (start, end); the end is the next function's entry (coverage)
BODIES = {
    'GameObject_ctor': (0x14CB10, 0x14CF84),
    'obj_moveAndCollide': (0x1509F8, 0x150E48),
    'Projectile_ctor': (0x150E48, 0x150EE4),
    'MissileWeapon_ctor': (0x150EE4, 0x151454),
    'MissileWeapon_dtor': (0x151454, 0x15153C),
    'MissileWeapon_run': (0x15153C, 0x15253C),
    'MissileWeapon_onTouch': (0x152A18, 0x153314),
    'MissileWeapon_nearestSamplePoint': (0x153314, 0x153514),
    'FireArrowProjectile_ctor': (0x2D6238, 0x2D6440),
    'FireArrowProjectile_run': (0x2D66AC, 0x2D67E8),
    'FireArrowProjectile_onHit': (0x2D685C, 0x2D6BB8),
    'FireArrowProjectile_end': (0x2D6BB8, 0x2D6C20),
    'FireArrowProjectile_dtor': (0x3CDE04, 0x3CDE88),
    'ColdArrowProjectile_ctor': (0x2D6FB4, 0x2D718C),
    'ColdArrowProjectile_run': (0x2D73C8, 0x2D7980),
    'ColdArrowProjectile_onHit': (0x2D7AAC, 0x2D7ECC),
    'ColdArrowProjectile_end': (0x2D7ECC, 0x2D84CC),
    'ColdArrowProjectile_dtor': (0x3CDF4C, 0x3CDFD0),
    'ExplodeArrowProjectile_ctor': (0x2DAEB4, 0x2DAFE0),
    'ExplodeArrowProjectile_run': (0x2DB17C, 0x2DB430),
    'ExplodeArrowProjectile_onHit': (0x2DB4F0, 0x2DB50C),
    'ExplodeArrowProjectile_explode': (0x2DB50C, 0x2DBA94),
    'ExplodeArrowProjectile_dtor': (0x3CE30C, 0x3CE378),
}

# bodies tools/difftest_arrow_run.py runs REAL and compares (name -> entry)
EXECUTED = {name: start for name, (start, _end) in BODIES.items()}

# the virtual slots of the arrow classes this module runs: function -> (slot, method)
CLASS_BODIES = {
    MISSILE_DTOR: (1, 'missile_dtor'), MISSILE_RUN: (4, 'missile_run'),
    MISSILE_ON_TOUCH: (6, 'missile_on_touch'), MISSILE_NEAREST: (17, 'missile_nearest_sample'),
    FIRE_DTOR: (1, 'firearrow_dtor'), FIRE_RUN: (4, 'firearrow_run'), FIRE_ON_HIT: (6, 'firearrow_on_hit'),
    COLD_DTOR: (1, 'coldarrow_dtor'), COLD_RUN: (4, 'coldarrow_run'), COLD_ON_HIT: (6, 'coldarrow_on_hit'),
    EXPLODE_DTOR: (1, 'explodearrow_dtor'), EXPLODE_RUN: (4, 'explodearrow_run'),
    EXPLODE_ON_HIT: (6, 'explodearrow_on_hit'),
}

# the arrow classes: element -> (class name, table, block size, ctor, run, slot 6, end, dtor)
CLASSES = {
    0: ('MissileWeapon', 0x50E5A0, 0x1C8, MISSILE_CTOR, MISSILE_RUN, MISSILE_ON_TOUCH, None, MISSILE_DTOR),
    1: ('FireArrowProjectile', 0x518DE0, 0xB0, FIRE_CTOR, FIRE_RUN, FIRE_ON_HIT, FIRE_END, FIRE_DTOR),
    2: ('ColdArrowProjectile', 0x518EF8, 0xB0, COLD_CTOR, COLD_RUN, COLD_ON_HIT, COLD_END, COLD_DTOR),
    6: ('ExplodeArrowProjectile', 0x519240, 0x74, EXPLODE_CTOR, EXPLODE_RUN, EXPLODE_ON_HIT, EXPLODE_EXPLODE,
        EXPLODE_DTOR),
}

# ---- addresses and constants (Observed; the address after each is where the code loads it) ----
G_RAND_SEED = RC.G_RAND_SEED                # 0x404464 shared
G_COSMETIC_SEED = SB.G_COSMETIC_SEED        # 0x404460 per machine
G_SIM_FRAME = RC.G_SIM_FRAME                # 0x44fdcc
G_WORLD = RC.G_WORLD                        # 0x44fdc8
G_LEVEL_FLAGS = RC.G_LEVEL_FLAGS            # 0x44fe08: 0x100 cold level, 0x40000 stone level (Inferred)
G_PVP_MODE_A = SB.G_PVP_MODE_A              # 0x4f711c
G_SKILL_TABLE = SB.G_SKILL_TABLE            # 0x41b170
G_MODEL_TABLE = 0x3E9CE0                    # item model rows (16 bytes); +8 / +0xc the Skeleton's two words
G_POOL_CLASSES = 0x403A10                   # pool size classes, 16 bytes each: size, count, base, free head
VT_MISSILE, VT_PROJECTILE = 0x50E5A0, 0x5120B8
VT_FIRE_ARROW, VT_COLD_ARROW, VT_EXPLODE_ARROW = 0x518DE0, 0x518EF8, 0x519240

S_FX_LUMP = 0x532478                        # 'fx.lmp'
S_STONE_HIT = 0x532538                      # the stone-hit sound name (formatted with no conversion, 0x151894)
S_CAST = {1: 0x532498, 2: 0x532480, 5: 0x5324B0, 6: 0x5324C8}       # MissileWeapon_ctor launch sounds
S_IMPACT = {1: 0x5324E0, 2: 0x5324E0, 5: 0x5324F8, 6: 0x532518}     # MissileWeapon_run impact sounds (not kind 0)
S_POTIONS = (0x532570, 0x532580, 0x532590)  # the three item names of the deflection test

ZERO, ONE = RC.ZERO, RC.ONE
F_INV65536 = 0x37800000                     # 2^-16
F_EIGHTEEN = 0x41900000                     # cold-level puff height
F_THREE_QUARTERS = 0x3F400000
F_BIG = 0x4CBEBC20                          # 1e8
F_HUNDRED = 0x42C80000
F_LIGHT_RADIUS = 0x43280000                 # 168.0, MissileWeapon light +0x198 / +0x190
F_LIGHT_FALLOFF = 0x38149B92
F_TRAIL_WIDTH = 0x3E1A9FBE
F_WIDE_RADIUS, F_WIDE_HEIGHT = 0x41C00000, 0x42C80000   # weapon class 6: radius 24, height 100
STUCK_RADIUS = 0x1E0                        # obj_updateActive radius while stuck (480)
LIFE = 300                                  # MissileWeapon expiry, frames
ELEMENT_IDS = (0x18, 0x16, 0x15, 0x17, 0x26)    # the item modifiers that mean "elemental" (no trail)

# Callees that stay recording callbacks (beside ref_skills_b.EXTERNALS)
EXTERNALS = dict(SB.EXTERNALS)
EXTERNALS.update({
    'obj_updateActive': Ext(0x14DB08, 'pii', 0, 'i', '(object, was active, radius) -> active'),
    'light_dtor': Ext(0x14A490, 'pi', 0, 'n', '(light record, 2)'),
    'trail_release': Ext(0x192800, 'i', 0, 'n', '(trail)'),
    'sound_playSample': Ext(0x2134E8, 'iv', 3, 'i', '(sample, position; 1.0, 1.0, 0.0) -> voice'),
    'SkillPenetratingArrows_getStats01Fraction': Ext(0x314C88, 'pwwi', 0, 'n', '(skill, out u, out p, rank)'),
    'SkillDodge_getStat0Fraction': Ext(0x2E8AC0, 'pi', 0, 'f', '(skill, rank) -> fraction'),
    'Player_blockSparks': Ext(0x1B9658, 'pi', 0, 'n', '(player, 0)'),
    'item_parseDescriptor': Ext(0x1069B8, 'S-ii', 0, 'n', '(item name, stack record, -1, 0)'),
    'item_getResourceIndex': Ext(0x1083F8, '-', 0, 'i', '(stack record) -> row of the model table'),
    'PhProp_ctor4': Ext(0x155BDC, 'pvppiii', 1, 'n', '(block, position, model A, model B, 1, 0x2a, 0; 1.0)'),
    'mat3_transpose': Ext(0x166298, '--', 0, 'n', '(stack matrix, same)'),
    'mat3_setIdentity': Ext(0x165650, '-', 0, 'n', '(stack matrix)'),
    'mat3_rotateAxis': Ext(0x162960, '-ii', 0, 'n', '(stack matrix, 2, facing)'),
    'mat3_mul': Ext(0x165710, 'p--', 0, 'n', '(arrow +0x100, two stack matrices)'),
    'AutoContainer_typeinfo': Ext(0x3C9558, '', 0, 'i', '-> descriptor'),
    'Container_typeinfo': Ext(0x3C3308, '', 0, 'i', '-> descriptor'),
    'Skeleton_typeinfo': Ext(0x3CC62C, '', 0, 'i', '-> descriptor'),
    'PushPhysicsProp_typeinfo': Ext(0x3C7BC8, '', 0, 'i', '-> descriptor'),
    'GameObject_dtor': Ext(0x14CF90, 'pi', 0, 'n', '(object, 0)'),
    'pool_free': Ext(0x150470, 'p', 0, 'n', '(block): reached by a tail jump'),
    'model_getSamplePoint': Ext(0x178E18, 'ppviioWQ', 1, 'n', '(model, host +0x114, host position, host facing, '
                                'index, out point, out weight or 0, out 3x3 matrix or 0; host scale)'),
    'Creature.v0': Ext(0, '', 0, 'i', 'type-info getter (no arguments)'),
    'Creature.v2': Ext(0, 'pii', 1, 'n', 'container hit (0, 0; 0.0)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """ref_skills_b.shape_result for this module's rows."""
    saved = SB.EXTERNALS
    SB.EXTERNALS = EXTERNALS
    try:
        return SB.shape_result(name, args, ret, fret, outs)
    finally:
        SB.EXTERNALS = saved


class Model(SB.Model):
    """The four Skeleton arrows on a memory image (ref_skills_b plumbing: memory, call-outs,
    handle lists, the Skill statistics)."""

    def call(self, name, *args):
        if name in SB.INTERNAL_CALLS:
            return getattr(self, name)(*args)
        args = tuple(('stack' if SB.MODEL_STACK <= (a & M32) < SB.MODEL_STACK + SB.MODEL_STACK_SIZE else a & M32)
                     if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        """A virtual call through +0x48: an arrow body of CLASS_BODIES runs here, anything
        else goes to ref_skills_b (its effect objects, or the callback 'Creature.v<slot>')."""
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and body[0] == slot and ('Creature.v%d' % slot) not in self.external:
            return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return SB.Model.vcall(self, obj, slot, *args)

    # ---- the base constructor, real ---------------------------------------------------------
    def game_object_ctor(self, obj, pos, class_def, props):
        """GameObject_ctor 0x14cb10, run for real (tools/ref_skills_a.py's body): ONE SHARED
        DRAW seeds the object's own generator +0x44 (the draw's high half)."""
        SA.Model.gameobject_ctor(self, obj, self.vec(pos), class_def, props)

    # ---- small helpers ------------------------------------------------------------------------
    def type_of(self, obj):
        """Virtual slot 0 (the type-info getter, called with no arguments)."""
        return self.vcall_noargs(obj, 0)

    def vcall_noargs(self, obj, slot):
        return self.call('Creature.v%d' % slot)

    def same_type(self, a, b):
        """rtti_typeInfoEquals 0x3b1250 (C library, real): the same descriptor or equal
        name strings (a descriptor's first word points at its name)."""
        if a == b:
            return True
        return self.cstr(self.u32(a)) == self.cstr(self.u32(b))

    def sample_point(self, model, host, index, weight, matrix, out=None):
        """model_getSamplePoint(host scale +0xdc, model, host +0x114, host position, host
        facing, index, out point, weight or 0, matrix or 0) -> (point, weight, matrix).
        With `out` (the stuck arrow's +0x10) the callee writes the point there."""
        res = self.call('model_getSamplePoint', model, host + 0x114, self.vec(host + 0x10), self.s16(host + 0x38),
                        index, 1 if weight else 0, 1 if matrix else 0, self.u32(host + 0xDC))
        if not (weight or matrix):
            point, rest = (res if isinstance(res, tuple) else (0, 0, 0)), []
        else:
            point, rest = res[0], list(res[1:])
        w = rest.pop(0) if weight and rest else 0
        if out is not None:
            for i in range(3):
                self.mem.poke(out + 4 * i, 4, point[i] & M32)     # written by the callee
        return point, w

    def pool_free_inline(self, block):
        """The pool free the destructors end with: a tail jump (`j`) to pool_free 0x150470
        in each of them (0x151518, 0x3cde6c, 0x3cdfb4, 0x3ce35c); the class walk over the
        bases at 0x403a28 + 16 k and the push on the free head 0x403a1c + 16 k are
        pool_free's own.  A call-out here."""
        self.call('pool_free', block)

    # =====================================================================================
    # MissileWeapon_ctor 0x150ee4 (obj, kind, model A, model B, pos*, vel*, facing, owner;
    #   stack: launch sample, impact sample, dmin, dmax, weapon rating, item flags, attack,
    #   damage flags, item)
    # =====================================================================================
    def missile_ctor(self, obj, kind, model_a, model_b, pos, vel, facing, owner, launch, impact,
                     dmin, dmax, wrating, iflags, attack, dflags, item):
        """Projectile_ctor(obj, copy of pos, owner, 0) (ONE SHARED DRAW); table 0x50e5a0;
        five handle words +0x5c, +0x74, +0x8c, +0xa4, +0xbc = 0; +0x124 = +0x128 = 0 (pierced
        list, stuck host); the light record +0x174 (position +0x1a4 = pos, colour 0xff, 0x9b,
        0, radius 168.0, falloff) linked; +0x28 = 0x48; spin +0xfa, angle +0xfc, +0xfe = 0;
        kind +0xd0 (5, 6: other colours); launch sound for kinds 1, 2, 5, 6; light unlinked
        for kinds 0, 3.  An item (+0 non-null): weapon class 6 -> radius 24, height 100; any
        of the modifiers 0x18, 0x16, 0x15, 0x17, 0x26 non-zero -> +0x170 = 0 (no trail).
        Otherwise kind 0 on a level without flag 0x100: trail_create and its first point.
        Damage words +0xd4..+0xe8, velocity +0x1b0, facing +0x38, models +0x1c0/+0x1c4,
        item +0x12c, flags |= 0x4001, +0xf4 = 0, hit state +0xcc = 0, +0xf8 = 1, expiry +0xec
        = frame + 300, obj_runEveryFrame, active +0xcd = 1, launch voice +0xf0, impact sample
        +0x1bc."""
        u32, w32, w16, w8 = self.u32, self.w32, self.w16, self.w8
        kind = s32(kind)
        start = self.vec(pos)
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x48, VT_MISSILE)
        for k in range(5):
            w32(obj + 0x5C + 0x18 * k, 0)
        light = obj + 0x174
        w32(obj + 0x124, 0)
        w32(obj + 0x128, 0)
        w8(light + 0x9, 0)
        self.wvec(obj + 0x1A4, start)
        w16(light + 0x18, -0x20)
        w16(light + 0x10, -0x20)
        w32(light + 0x24, F_LIGHT_RADIUS)
        w32(light + 0x28, F_LIGHT_FALLOFF)
        w32(light + 0x1C, F_LIGHT_RADIUS)
        w32(light + 0x20, F_LIGHT_FALLOFF)
        w32(light + 0x2C, 0)
        w16(light + 0xA, 0xFF)
        w16(light + 0xC, 0x9B)
        w16(light + 0xE, 0)
        w16(light + 0x12, 0xFF)
        w16(light + 0x14, 0x9B)
        w16(light + 0x16, 0)
        w8(light + 0x8, 0)
        self.call('light_link', light)
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
            entry = self.call('res_find', S_FX_LUMP, S_CAST[kind])
            self.call('sound_playOnObject', entry, obj, ONE)
            kind = s32(u32(obj + 0xD0))
        if kind in (0, 3):
            self.call('light_unlink', light)
        elemental = False
        if item and u32(item):
            if s8(self.u8(u32(item) + 0x1E)) == 6:
                w32(obj + 0x1C, F_WIDE_RADIUS)
                w32(obj + 0x20, F_WIDE_HEIGHT)
            for wanted in ELEMENT_IDS:
                value = 0
                for k in range(4):
                    if self.s16(item + 0x24 + 8 * k) == wanted:
                        value = self.s16(item + 0x26 + 8 * k)
                        break
                if value:
                    w32(obj + 0x170, 0)
                    elemental = True
                    break
        if not elemental and u32(obj + 0xD0) == 0 and not u32(G_LEVEL_FLAGS) & 0x100:
            trail = self.call('trail_create', 1, 0x7A, 0, 0x80, 0x80, 0x80, 0x20, F_TRAIL_WIDTH)
            w32(obj + 0x170, trail)
            self.call('trail_addPoint', trail, self.vec(obj + 0x10))
        w32(obj + 0xD4, dmin)
        w32(obj + 0xD8, dmax)
        w32(obj + 0xDC, wrating)
        w32(obj + 0xE0, iflags)
        w32(obj + 0xE4, attack)
        w32(obj + 0xE8, dflags)
        self.wvec(obj + 0x1B0, self.vec(vel))
        w16(obj + 0x38, facing)
        w32(obj + 0x1C0, model_a)
        w32(obj + 0x1C4, model_b)
        w32(obj + 0x12C, item)
        w32(obj + 0xC, u32(obj + 0xC) | 0x4001)
        w32(obj + 0xF4, 0)
        w8(obj + 0xCC, 0)
        w8(obj + 0xF8, 1)
        w32(obj + 0xEC, u32(G_SIM_FRAME) + LIFE)
        self.call('obj_runEveryFrame', obj)
        w8(obj + 0xCD, 1)
        if launch:
            w32(obj + 0xF0, self.call('sound_playSample', launch, self.vec(obj + 0x10), ONE, ONE, ZERO))
        else:
            w32(obj + 0xF0, 0)
        w32(obj + 0x1BC, impact)

    # =====================================================================================
    # MissileWeapon_run 0x15153c (slot 4)
    # =====================================================================================
    def missile_run(self, this):
        """Stuck (+0x128 set): obj_updateActive(this, +0xcd, 480) -> +0xcd; a host with the
        creature flag 0x20 and creature flag bit 41 -> obj_delete(this), return; the host's
        model (slot 16): the sample point +0xf4 of the host written to +0x10;
        obj_updateGridCell; return (no expiry while stuck).
        Hit state +0xcc set: slot 1 with 3 (destroyed now), return.
        Spin +0xfa added to +0xfc.  r = obj_moveAndCollide(this, velocity +0x1b0) - no
        gravity, the velocity never changes.  res = (r & 1) | (+0xcc ? 2 : 0).
        res: kinds 1, 2, 5, 6 an impact sound (refused here); +0xec = 0; res 2 with +0xcc 2
        a spark (fx 2, 0x11 on a cold level); 3 -> +0xec = frame; 1 -> frame + 1.  res 1:
        the stone-hit name (sprintf without conversion), fx 8 on a stone level (0x40000),
        else fx 0x11 (cold, 0x100) or 2, the sound, the impact sample +0x1bc.
        Kind 0: on a cold level ONE OWN DRAW, and when it is divisible by 3 a second OWN
        DRAW for a puff 0..18 above (fx 0x11) instead of the trail point; otherwise the
        trail point when +0x170.  Kind 3: the trail point when +0x170.
        frame >= +0xec: slot 1 with 3."""
        u32 = self.u32
        if u32(this + 0x128):
            active = self.call('obj_updateActive', this, s8(self.u8(this + 0xCD)), STUCK_RADIUS)
            self.w8(this + 0xCD, active)
            host = self.handle_obj(this + 0x128)
            if u32(host + 0xC) & 0x20 and self.u64(host + 0xA8) & (1 << 41):
                self.call('obj_delete', this)
                return
            model = self.vcall(host, 16)
            if model:
                self.sample_point(model, host, u32(this + 0xF4), False, False, out=this + 0x10)
            self.call('obj_updateGridCell', this)
            return
        if s8(self.u8(this + 0xCC)):
            self.vcall(this, 1, 3)
            return
        kind = s32(u32(this + 0xD0))
        if kind not in (0, 3):
            raise NotImplementedError('MissileWeapon_run of kind %d: impact effects (not a Skeleton arrow)' % kind)
        spin = self.u16(this + 0xFA)
        if s16(spin):
            self.w16(this + 0xFC, self.u16(this + 0xFC) + spin)
        r = self.obj_move_and_collide(this, self.local_vec(self.vec(this + 0x1B0)))
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
                name = self.call('libc_sprintf', S_STONE_HIT, None)
                if u32(G_LEVEL_FLAGS) & 0x40000:
                    self.call('fx_spawn', 8, self.vec(this + 0x10))
                elif u32(G_LEVEL_FLAGS) & 0x100:
                    self.call('fx_spawn', 0x11, self.vec(this + 0x10))
                else:
                    self.call('fx_spawn', 2, self.vec(this + 0x10))
                entry = self.call('res_find', S_FX_LUMP, name)
                self.call('sound_playOnObject', entry, this, ONE)
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
    # MissileWeapon_onTouch 0x152a18 (slot 6) (this, other)
    # =====================================================================================
    def missile_on_touch(self, this, other):
        """1. +0xcc set, or no victim: nothing.  The owner is read from +0x4c first.
        2. A victim without the creature flag 0x20: AutoContainer / Container -> its slot 2
           (0, 0; 0.0); +0xcc = 2 in every case.  No enemy test, no draw.
        3. Owner present with flag 0x20: owner.slot20(victim) must accept, else nothing.
        4. Victim in the pierced list +0x124: nothing.
        5. Owner a PLAYER (flag 0x40) and kind 0 or 3: Penetrating Arrows, TWO SHARED DRAWS.
        6. Victim a creature and owner a PLAYER: PvP and flag 0x1000000 tests, then (no
           pierce, kind 0) the STICK: +0x128 linked to the victim, +0xf4 = slot 17; dropped
           for index 0 or a Skeleton victim; own flag 1.  Kinds 1, 5, 6 override the damage
           flags.  A monster's arrow never comes here: it never sticks.
        7. Deflection chance (player victim: Dodge skills 2 and 0x53; creature: its slot
           36 -> Dodge slot 11), ONE SHARED DRAW; deflected when draw % 100 + 1 < chance:
           block sparks (player), three item_parseDescriptor, maybe a PhProp, obj_delete.
        8. damage_apply(victim, owner or this, +0xe4, +0xdc, +0xe0, +0xe8 | 0x40 if
           unblockable, item +0x12c, 0; float +0xd4, float +0xd8): result 1 -> +0xcc = 3
           (player victim) or 1; otherwise 2.
        9. Pierce and +0xcc set: the victim joins +0x124, +0xcc = 0."""
        u32 = self.u32
        if s8(self.u8(this + 0xCC)):
            return
        owner = self.handle_obj(this + 0x4C)
        if other == 0:
            return
        if not u32(other + 0xC) & 0x20:
            if self.same_type(self.type_of(other), self.call('AutoContainer_typeinfo')):
                self.vcall(other, 2, 0, 0, ZERO)
            elif self.same_type(self.type_of(other), self.call('Container_typeinfo')):
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
        pierce = unblockable = False
        kind = s32(u32(this + 0xD0))
        if owner and u32(owner + 0xC) & 0x40 and kind in (0, 3):
            rank = self.call('player_getSkillRank', u32(owner + 0x3C8), 0x5D)
            u, p = self.call('SkillPenetratingArrows_getStats01Fraction', u32(G_SKILL_TABLE + 4 * 0x5D), rank)
            unblockable = C.le(C.mul(C.from_int(self.draw()), F_INV65536), u)
            if C.le(C.mul(C.from_int(self.draw()), F_INV65536), p):
                pierce = True
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
                elif self.same_type(self.type_of(other), self.call('Skeleton_typeinfo')):
                    self.call('handle_clear', this + 0x128)
                else:
                    model = self.vcall(other, 16)
                    if model:
                        self.sample_point(model, other, u32(this + 0xF4), False, True)
                        self.call('mat3_transpose')
                        self.call('mat3_setIdentity')
                        self.call('mat3_rotateAxis', 2, self.s16(this + 0x38))
                        self.call('mat3_mul', this + 0x100)
                self.w32(this + 0xC, u32(this + 0xC) | 1)
            override = {1: 0x20, 5: 0x400, 6: 0x80}.get(s32(u32(this + 0xD0)))
            if override is not None:
                self.w32(this + 0xE8, override)
                self.w32(this + 0xE4, 10000)
        chance = 0
        player = 0
        oflags = u32(other + 0xC)
        if oflags & 0x40:
            rank = self.call('player_getSkillRank', u32(other + 0x3C8), 2)
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
                self.call('item_parseDescriptor', name, -1 & M32, 0)
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
        elif self.same_type(self.type_of(other), self.call('PushPhysicsProp_typeinfo')):
            self.w8(this + 0xCC, 2)
        if pierce and s8(self.u8(this + 0xCC)):
            self.call('handle_link', this + 0x124, other, other)
            self.w8(this + 0xCC, 0)

    # =====================================================================================
    # MissileWeapon_nearestSamplePoint 0x153314 (slot 17) (this, victim) -> index
    # =====================================================================================
    def missile_nearest_sample(self, this, other):
        """0 without a victim, a model (slot 16) or sample points; else the largest weight
        w, then the point nearest the arrow (3-D) among those with weight >= 0.75 w; ties to
        the first.  Reached only from step 6 of the touch (a player's arrow)."""
        if other == 0:
            return 0
        model = self.vcall(other, 16)
        count = s32(self.call('model_getSamplePointCount', model)) if model else 0
        if count == 0:
            return 0
        best = ZERO
        for k in range(max(count, 0)):
            _p, w = self.sample_point(model, other, k, True, False)
            if C.lt(best, w):
                best = w
        nearest, index = F_BIG, 0
        for k in range(max(count, 0)):
            p, w = self.sample_point(model, other, k, True, False)
            if C.lt(w, C.mul(best, F_THREE_QUARTERS)):
                continue
            d = [C.sub(self.u32(this + 0x10 + 4 * i), p[i]) for i in range(3)]
            dist = C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
            if C.lt(dist, nearest):
                nearest, index = dist, k
        return index

    # =====================================================================================
    # Destructors (slot 1)
    # =====================================================================================
    def missile_dtor(self, this, flags):
        """MissileWeapon_dtor 0x151454: table 0x50e5a0; trail_release when +0x170;
        light_dtor(+0x174, 2); handle_clear of +0x128, +0x124, then +0xbc, +0xa4, +0x8c,
        +0x74, +0x5c; table 0x5120b8 (Projectile); handle_clear(+0x4c); GameObject_dtor(this,
        0); pool_free (a tail jump) when bit 0 of the argument is set."""
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
            self.pool_free_inline(this)

    def _lit_arrow_dtor(self, this, flags, table):
        """FireArrowProjectile_dtor 0x3cde04 / ColdArrowProjectile_dtor 0x3cdf4c (132 bytes
        each, the same code with the class's own table): table; light_dtor(+0x70, 2); table
        0x5120b8 (Projectile); handle_clear(+0x4c) (the owner); GameObject_dtor(this, 0);
        bit 0 of the argument: pool_free (tail jump)."""
        self.w32(this + 0x48, table)
        self.call('light_dtor', this + 0x70, 2)
        self.w32(this + 0x48, VT_PROJECTILE)
        self.call('handle_clear', this + 0x4C)
        self.call('GameObject_dtor', this, 0)
        if flags & 1:
            self.pool_free_inline(this)

    def firearrow_dtor(self, this, flags):
        self._lit_arrow_dtor(this, flags, VT_FIRE_ARROW)

    def coldarrow_dtor(self, this, flags):
        self._lit_arrow_dtor(this, flags, VT_COLD_ARROW)

    def explodearrow_dtor(self, this, flags):
        """ExplodeArrowProjectile_dtor 0x3ce30c (108 bytes): no light (the class has none);
        table 0x5120b8; handle_clear(+0x4c); GameObject_dtor(this, 0); bit 0: pool_free."""
        self.w32(this + 0x48, VT_PROJECTILE)
        self.call('handle_clear', this + 0x4C)
        self.call('GameObject_dtor', this, 0)
        if flags & 1:
            self.pool_free_inline(this)

    # =====================================================================================
    # Entry points by name, for the difftest
    # =====================================================================================
    def skeleton_missile(self, obj, model_a, model_b, pos, vel, facing, owner, dmin, dmax, attack):
        """MissileWeapon_ctor with the Skeleton's arguments (kind 0; stack 0, 0, dmin,
        dmax, 0, 0, attack, 4, 0)."""
        return self.missile_ctor(obj, 0, model_a, model_b, pos, vel, facing, owner, 0, 0, dmin, dmax, 0, 0,
                                 attack, 4, 0)


METHODS = {
    MISSILE_CTOR: 'missile_ctor', MISSILE_RUN: 'missile_run', MISSILE_ON_TOUCH: 'missile_on_touch',
    MISSILE_NEAREST: 'missile_nearest_sample', MISSILE_DTOR: 'missile_dtor',
    FIRE_CTOR: 'firearrow_ctor', FIRE_RUN: 'firearrow_run', FIRE_ON_HIT: 'firearrow_on_hit',
    FIRE_END: 'firearrow_end', FIRE_DTOR: 'firearrow_dtor',
    COLD_CTOR: 'coldarrow_ctor', COLD_RUN: 'coldarrow_run', COLD_ON_HIT: 'coldarrow_on_hit',
    COLD_END: 'coldarrow_end', COLD_DTOR: 'coldarrow_dtor',
    EXPLODE_CTOR: 'explodearrow_ctor', EXPLODE_RUN: 'explodearrow_run', EXPLODE_ON_HIT: 'explodearrow_on_hit',
    EXPLODE_EXPLODE: 'explodearrow_explode', EXPLODE_DTOR: 'explodearrow_dtor',
}

__all__ = ['Model', 'EXECUTED', 'CLASS_BODIES', 'EXTERNALS', 'BODIES', 'CLASSES', 'METHODS', 'shape_result']
