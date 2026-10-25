"""ref_phprop_run.py - the per-frame run of a physics prop (PhProp_run, slot 4 of PhProp and
of the bone props PhProp_ctor2 builds) and of a gut chunk (GutChunk_run, slot 4 of
GutChunk, which calls PhProp_run first), with the rigid-body bodies under them and the
constructors of the resting prop a PhProp turns into.

Reference contract, executed against the original by tools/difftest_phprop_run.py
(docs/spec/phprop-run.md is the prose).  Pseudo-code in my own words.

    GutChunk_run                    0x1edb18  (chunk)
    PhProp_run                      0x155fcc  (prop)
    rigidbody_pointVelocity         0x167008  (body, point, out)
    rigidbody_applyCollisionImpulse 0x167408  (restitution; body, point, normal)
    rigidbody_integrate             0x167730  (dt; body, force, torque)
    rigidbody_addForceAtPoint       0x167c18  (body, point, force, force sum, torque sum)
    model_getHullPoints             0x179320  (model, mesh) -> eight s8 points or 0
    Prop_ctorNamed                  0x153ac0  (obj, pos, lump, model, texture, mask, flags, matrix)
    Prop_ctorRes                    0x153c88  (obj, pos, model entry, texture entry, mask, flags, matrix)
    ItemProp_ctor3                  0x1592bc  (obj, pos, item record, matrix)

The prop's rigid body lives at +0x190 (body offsets in brackets):
    +0x190 [0]     inverse mass            +0x194..+0x19c [4..0xc] inverse inertia (body axes)
    +0x1a0 [0x10]  position                +0x1ac [0x1c]  orientation quaternion (x, y, z, w)
    +0x1bc [0x2c]  linear momentum         +0x1c8 [0x38]  angular momentum
    +0x1d4 [0x44]  rotation matrix         +0x1f8 [0x68]  inverse inertia (world)
    +0x21c [0x8c]  angular velocity
With the mass of 1 PhProp_initPhysics gives, momentum is velocity per frame.

Draws: none of these bodies touches the shared seed 0x404464 except through the
constructors of the resting prop (Prop_ctorNamed / Prop_ctorRes / ItemProp_ctor3 each call
GameObject_ctor: ONE SHARED DRAW).  Every other draw is the prop's own generator +0x44
(GameObject_rand).  fx_impactPuffNearCamera and rigidbody_init (not called here) draw the
cosmetic seed 0x404460; StaticFire_ctor (a stub here) draws the shared seed through its own
GameObject_ctor.
"""
import ref_core as C
import ref_creature as RC
import ref_phprop as PP
from ref_creature import Ext, M32, M64, s16, s32

GUTCHUNK_RUN, PHPROP_RUN = 0x1EDB18, 0x155FCC
RB_POINT_VELOCITY, RB_APPLY_IMPULSE = 0x167008, 0x167408
RB_INTEGRATE, RB_ADD_FORCE = 0x167730, 0x167C18
MODEL_HULL_POINTS = 0x179320
PROP_CTOR_NAMED, PROP_CTOR_RES, ITEMPROP_CTOR3 = 0x153AC0, 0x153C88, 0x1592BC
GUTCHUNK_DTOR, PHPROP_DTOR = 0x3C4D48, 0x3C2FC8          # slot 1 of 0x50f3b8 / 0x511ba8
VT_PROP, VT_ITEMPROP = 0x511D58, 0x511C38
DTORS = {GUTCHUNK_DTOR: 'GutChunk_dtor', PHPROP_DTOR: 'PhProp_dtor'}

# ---- globals -----------------------------------------------------------------------------
G_SIM_FRAME = RC.G_SIM_FRAME            # 0x44fdcc: the water test runs when its low 3 bits are 0
G_WORLD = 0x44FDC8                      # first argument of every terrain and water service
G_DECAL_DETAIL = 0x44FDC0               # local option (also the gore word GutChunk_ctor reads)
G_PROP_OPTIONS = PP.G_PROP_OPTIONS      # 0x44fe08: bit 0x100 lowers the gravity
G_NUM_PLAYERS = RC.G_NUM_PLAYERS        # 0x4d8ae0
G_ALIVE_PLAYERS = 0x4F8440              # g_alivePlayers: its first entry, a player slot
G_PLAYER_OBJ = 0x4DCEC8                 # + 0x4c30 x slot: the player record's object word
REC_SIZE = 0x4C30
ITEM_MODELS = 0x3E9CE0                  # row x 16: model name +0, texture name +4

# ---- texts (addresses of the strings the code passes) ------------------------------------
S_FX_LUMP = 0x532478                    # 'fx.lmp' (PhProp_run)
S_SPLASH_FORMAT = 0x532458              # the small-splash sound name format (one %d)
S_FX_LUMP2, S_GUT_SPLAT = 0x53E3C0, 0x53E4A0      # 'fx.lmp', the water-bounce sound (GutChunk_run)
S_EQUIP_LUMP = 0x5326B0                 # 'equipmnt.lmp' (ItemProp_ctor3)
SND_WOOD, SND_METAL, SND_SHIELD = 0x5326C0, 0x5326D8, 0x5326F0
SND_CHAIN, SND_METAL2, SND_LEATHER = 0x532708, 0x532720, 0x532738
SND_CLOTH, SND_POTION, SND_JEWELRY = 0x532750, 0x532768, 0x532780
PARTICLE_DEFS = (0x870458, 0x870408, 0x8703B8)    # chunk bit 4, bit 2, neither

# ---- float constants (bit patterns as loaded) ----------------------------------------------
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_TWO = 0x40000000
F_M1, F_M2 = 0xBF800000, 0xC0000000
F_M10000 = 0xC61C4000
F_EIGHT, F_TWELVE, F_24, F_120 = 0x41000000, 0x41400000, 0x41C00000, 0x42F00000
F_240, F_700 = 0x43700000, 0x442F0000
F_GRAV, F_GRAV_LOW = 0x3E3851E9, 0x3D5D2F18      # 0.18, or 0.054 with bit 0x100 of 0x44fe08
F_PUSH = 0x3BC49BA5                     # 0.006: ground push per unit of depth
F_SPIN_MAX = 0x3D4CCCCC                 # 0.05: the clamp of angular momentum x inertia
F_DAMP = 0x3F733333                     # 0.95
F_HUNDREDTH, F_MILLI = 0x3C23D70A, 0x3A83126E   # 0.01, 0.001
F_1_5 = 0x3FC00000
F_08, F_02, F_TENTH = 0x3F4CCCCC, 0x3E4CCCCC, 0x3DCCCCCC
F_SPLASH_VOL = 0x3E4CCCCC               # 0.2

EXECUTED = {
    'GutChunk_run': GUTCHUNK_RUN, 'PhProp_run': PHPROP_RUN,
    'rigidbody_pointVelocity': RB_POINT_VELOCITY, 'rigidbody_applyCollisionImpulse': RB_APPLY_IMPULSE,
    'rigidbody_integrate': RB_INTEGRATE, 'rigidbody_addForceAtPoint': RB_ADD_FORCE,
    'model_getHullPoints': MODEL_HULL_POINTS,
    'Prop_ctorNamed': PROP_CTOR_NAMED, 'Prop_ctorRes': PROP_CTOR_RES, 'ItemProp_ctor3': ITEMPROP_CTOR3,
}
# the run slot (vtable +0x24) of each class this module's run bodies serve
CLASS_BODIES = {
    0x50F3B8: ('GutChunk', GUTCHUNK_RUN),
    0x511BA8: ('PhProp', PHPROP_RUN),
}
# bodies executed elsewhere that run for real under these (name -> entry)
BORROWED = {
    'GameObject_ctor': 0x14CB10, 'GameObject_rand': 0x1509D0, 'item_getResourceIndex': 0x1083F8,
    'quat_mul': 0x166480, 'quat_normalize': 0x166550, 'mat3_transpose': 0x166298, 'mat3_mul': 0x165710,
    'mat3_mulVecTransposed': 0x165DA0, 'mat3_scale': 0x165CC0, 'mat34_translateLocal': 0x165B10,
}

# Callees that stay recording stubs.  Kinds as ref_creature.Ext; v: pointer to three floats
# (passed as a tuple); S: a text pointer (a stack buffer is compared by its text); N: a
# pointer the callee fills with two floats; f result: a float.
EXTERNALS = {
    # world services (what a probe must answer)
    'water_test': Ext(0x189438, 'ivi', 1, 'i', '(world, position, height out or 0; radius) -> in water'),
    'terrain_heightBelow': Ext(0x1834A8, 'iv', 1, 'f', '(world, position; radius) -> ground height'),
    'terrain_sweepCircle': Ext(0x185A40, 'ivviN', 1, 'f', '(world, position, delta, flags, normal out; '
                                                          'radius) -> fraction of the move'),
    'terrain_height': Ext(0x183820, 'iv', 1, 'f', '(world, position; radius) -> highest ground'),
    # object services
    'obj_updateGridCell': PP.EXTERNALS['obj_updateGridCell'],
    'obj_runEveryFrame': PP.EXTERNALS['obj_runEveryFrame'],
    'obj_delete': Ext(0x14F200, 'p', 0, 'n', '(object): deferred delete'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i', '(size) -> zero-filled block or 0'),
    'handle_link': PP.EXTERNALS['handle_link'],
    'obj_getPropInt': PP.EXTERNALS['obj_getPropInt'],
    'res_find': PP.EXTERNALS['res_find'],
    'GutChunk_dtor': Ext(GUTCHUNK_DTOR, 'pi', 0, 'n', '(object, 3): slot 1, destroys at once'),
    'PhProp_dtor': Ext(PHPROP_DTOR, 'pi', 0, 'n', '(object, 3): slot 1, destroys at once'),
    'StaticFire_ctor': Ext(0x2C5240, 'pviii', 2, 'n', '(block, position, burn frames, 0, 0; 240, 0.5)'),
    # presentation
    'sound_playOnObject': PP.EXTERNALS['sound_playOnObject'],
    'libc_sprintf': PP.EXTERNALS['libc_sprintf'],
    'water_disturb': Ext(0x189514, 'iv', 2, 'i', '(world, position; strength, radius) -> chunks'),
    'fx_impactPuffNearCamera': Ext(0x1FC150, 'vvi', 2, 'n', '(position, velocity, kind; size, 1.0)'),
    'particle_spawn': Ext(0x18F3F8, 'ivv', 1, 'n', '(definition, position, velocity; 0.0)'),
    'decal_add': Ext(0x19F110, 'viii', 1, 'n', '(position, angle (s16), type, flag; size)'),
}
SERVICES = ('water_test', 'terrain_heightBelow', 'terrain_sweepCircle', 'terrain_height')
PRESENTATION = ('sound_playOnObject', 'libc_sprintf', 'res_find', 'water_disturb', 'fx_impactPuffNearCamera',
                'particle_spawn', 'decal_add')
OWN_EXTERNALS = set(EXTERNALS) - set(PP.EXTERNALS)


def default_result(name):
    ret = EXTERNALS[name].ret
    if name == 'terrain_sweepCircle':
        return (ONE, ZERO, ZERO)
    return None if ret == 'n' else 0


class Model(PP.Model):
    """PhProp_run and GutChunk_run on a memory image (on top of the prop constructors)."""

    def call(self, name, *args):
        if name in OWN_EXTERNALS:
            args = tuple(a & M32 if isinstance(a, int) else a for a in args)
            self.calls.append((name, args))
            function = self.cb.get(name)
            if function is not None:
                return function(*args)
            return default_result(name)
        return PP.Model.call(self, name, *args)

    # ---- small helpers ----------------------------------------------------------------------
    def words(self, a, n):
        return [self.u32(a + 4 * k) for k in range(n)]

    def wwords(self, a, values):
        for k, v in enumerate(values):
            self.w32(a + 4 * k, v)

    def hull_points(self, model, mesh):
        """model_getHullPoints 0x179320: model + header byte +0x25 x 16 + mesh x 24, or 0
        when that byte is 0."""
        k = self.u8(model + 0x25)
        return (model + k * 0x10 + mesh * 0x18) & M32 if k else 0

    # =====================================================================================
    # Rigid body
    # =====================================================================================
    def rb_point_velocity(self, body, point):
        """rigidbody_pointVelocity 0x167008: w x (point - position) + momentum x inverse mass."""
        mul, sub, add = C.mul, C.sub, C.add
        r = [sub(point[i], self.u32(body + 0x10 + 4 * i)) for i in range(3)]
        w = self.words(body + 0x8C, 3)
        out = [sub(mul(w[1], r[2]), mul(w[2], r[1])),
               sub(mul(w[2], r[0]), mul(w[0], r[2])),
               sub(mul(w[0], r[1]), mul(w[1], r[0]))]
        m = self.u32(body)
        return [add(out[i], mul(self.u32(body + 0x2C + 4 * i), m)) for i in range(3)]

    def rb_add_force(self, body, point, force, fsum, tsum):
        """rigidbody_addForceAtPoint 0x167c18: the force sum gains the force, the torque sum
        (point - position) x force."""
        mul, sub, add = C.mul, C.sub, C.add
        for i in range(3):
            fsum[i] = add(fsum[i], force[i])
        r = [sub(point[i], self.u32(body + 0x10 + 4 * i)) for i in range(3)]
        t = [sub(mul(r[1], force[2]), mul(r[2], force[1])),
             sub(mul(r[2], force[0]), mul(r[0], force[2])),
             sub(mul(r[0], force[1]), mul(r[1], force[0]))]
        for i in range(3):
            tsum[i] = add(tsum[i], t[i])

    def rb_apply_impulse(self, e, body, point, normal):
        """rigidbody_applyCollisionImpulse 0x167408 (restitution e; body, point, normal).

        vn = v(point) . n; numerator vn x e - vn; nothing unless it is > 0.  r = point -
        position, u = Iw (r x n) (mat3_mulVecTransposed), denominator = inverse mass + (u x r)
        . n; j = numerator / denominator; momentum += n j; angular momentum += r x (n j);
        angular velocity = Iw L."""
        mul, sub, add = C.mul, C.sub, C.add
        n = normal
        v = self.rb_point_velocity(body, point)
        vn = add(add(mul(v[0], n[0]), mul(v[1], n[1])), mul(v[2], n[2]))
        num = sub(mul(vn, e), vn)
        if C.le(num, ZERO):
            return
        r = [sub(point[i], self.u32(body + 0x10 + 4 * i)) for i in range(3)]
        im = self.u32(body)
        c = [sub(mul(r[1], n[2]), mul(r[2], n[1])),
             sub(mul(r[2], n[0]), mul(r[0], n[2])),
             sub(mul(r[0], n[1]), mul(r[1], n[0]))]
        iw = self.words(body + 0x68, 9)
        u = C.mat3_mul_vec_transposed(iw, c)
        w = [sub(mul(u[1], r[2]), mul(u[2], r[1])),
             sub(mul(u[2], r[0]), mul(u[0], r[2])),
             sub(mul(u[0], r[1]), mul(u[1], r[0]))]
        denom = add(im, add(add(mul(w[0], n[0]), mul(w[1], n[1])), mul(w[2], n[2])))
        j = C.div(num, denom)
        J = [mul(n[0], j), mul(n[1], j), mul(n[2], j)]
        for i in range(3):
            self.w32(body + 0x2C + 4 * i, add(self.u32(body + 0x2C + 4 * i), J[i]))
        t = [sub(mul(r[1], J[2]), mul(r[2], J[1])),
             sub(mul(r[2], J[0]), mul(r[0], J[2])),
             sub(mul(r[0], J[1]), mul(r[1], J[0]))]
        for i in range(3):
            self.w32(body + 0x38 + 4 * i, add(self.u32(body + 0x38 + 4 * i), t[i]))
        self.wwords(body + 0x8C, C.mat3_mul_vec_transposed(iw, self.words(body + 0x38, 3)))

    def rb_integrate(self, dt, body, force, torque):
        """rigidbody_integrate 0x167730 (dt; body, force, torque).

        q += (w, 0) * q x dt/2 (quat_mul), momentum += force x dt, angular momentum +=
        torque x dt, q normalised; R = the transpose of the quaternion's matrix; Iw = (R with
        each column c times inverse inertia c) x R^T; angular velocity = Iw L.  The
        position is not moved (PhProp_run moves it)."""
        mul, add = C.mul, C.add
        q = self.words(body + 0x1C, 4)
        w4 = self.words(body + 0x8C, 3) + [ZERO]
        qd = C.quat_mul(w4, q)
        h = mul(dt, HALF)
        q = [add(q[i], mul(qd[i], h)) for i in range(4)]
        self.wwords(body + 0x1C, q)
        for base, vec in ((0x2C, force), (0x38, torque)):
            for i in range(3):
                self.w32(body + base + 4 * i, add(self.u32(body + base + 4 * i), mul(vec[i], dt)))
        q = C.quat_normalize(q)
        self.wwords(body + 0x1C, q)
        self.derive(body, q)

    def derive(self, body, q):
        """The tail of rigidbody_integrate and rigidbody_updateDerived: rotation, world
        inverse inertia, angular velocity."""
        r = C.mat3_transpose(C.mat3_from_quat(q))
        self.wwords(body + 0x44, r)
        inertia = self.words(body + 4, 3)
        m = [C.mul(r[3 * row + col], inertia[col]) for row in range(3) for col in range(3)]
        iw = C.mat3_mul(m, C.mat3_transpose(r))
        self.wwords(body + 0x68, iw)
        self.wwords(body + 0x8C, C.mat3_mul_vec_transposed(iw, self.words(body + 0x38, 3)))

    # =====================================================================================
    # PhProp_run
    # =====================================================================================
    def landing_sound(self, obj):
        """The sound of a fast landing: by the prop bits +0x140 for a plain prop, by the
        item record's definition (+0x148) bytes +0x1c/+0x1d and flags +0x150 for an item."""
        if not self.s8(obj + 0x238):
            bits = self.u16(obj + 0x140)
            return SND_WOOD if bits & 8 else SND_METAL if bits & 0x10 else None
        definition, flags = self.u32(obj + 0x148), self.u64(obj + 0x150)
        if not self.s8(definition + 0x1D):
            return SND_WOOD if flags & 0x800000 else SND_METAL if flags & 0x40000 else None
        if self.s8(definition + 0x1C) == 3:
            return SND_SHIELD if flags & 0x840000 else None
        for bit, sound in ((0x800000, SND_WOOD), (0x200000, SND_CHAIN), (0x40000, SND_METAL2),
                           (0x100000, SND_LEATHER), (0x80000, SND_CLOTH), (0x1000000, SND_POTION),
                           (0x4000000, SND_JEWELRY), (0x2000000, SND_JEWELRY), (0x10000000, SND_JEWELRY)):
            if flags & bit:
                return sound
        return None

    def phprop_run(self, obj):
        """PhProp_run 0x155fcc (prop).  In this order:

        1. Not yet in water (+0x239 = 0) and g_simFrame & 7 = 0: water_test(world, copy of
           the position, 0; 12).  In water: +0x239 = 1, ONE OWN DRAW (unused), the sound
           the first small-splash sound of fx.lmp at 0.2, water_disturb(world, position; 700, 24).
        2. Gravity: +0x1c4 -= 0.18 (0.054 with 0x44fe08 bit 0x100) / inverse mass.  The
           contact level is last frame's ground +0x228 + 2.  +0x230 = 0.
        3. For each set bit k of the 64-bit part mask +0xe8, the eight hull points of mesh k
           (model_getHullPoints(+0x4c, k)): p = point - centre +0xf0.  Its height (row 2 of R
           . p + body z) under the contact level makes w = R^T p + body position.  Then a
           countdown +0x234 > 0 is decremented instead (per point).  Otherwise, when w is
           under the contact level: contact; the point velocity; under -1 and not in water,
           the landing sound (1.0); under 0, the collision impulse with restitution +0x23c
           and the normal (0, 0, 1), +0x230 = 1; depth = min(level - w.z, 1); force (0, 0,
           depth x 0.006) at the point when > 0.
        4. +0x140 bit 0x20: each angular momentum component is clamped so that it times the
           inverse inertia stays within +-0.05.
        5. rigidbody_integrate(1; body, the force and torque sums).  After a contact the
           horizontal momentum x 0.95; the angular momentum x 0.95 always.
        6. Position = body position; body z += vz x inverse mass; the horizontal move d =
           momentum x inverse mass.  Ground = terrain_heightBelow(world, position; radius
           +0x1c) -> +0x228; the position z snaps to it when z - 0.01 <= ground.
        7. When |d|^2 > 0.001: t = terrain_sweepCircle(world, position, d, 1, normal out;
           radius); the position moves by d x t; relinked; t < 1 with a = 0.001 - n . p > 0
           pushes the momentum by n a 1.5; a burning prop (+0x23a) makes a camera puff.
        8. Body x, y = position x, y; relinked.
        9. +0x23a = 1, within 12 of the ground and all six momenta under 0.8: +0x23a = 2 and
           a StaticFire (pool 0x4ac; ONE OWN DRAW d, burn (d % 40) x 60 + 480).
       10. Life +0x10e under -220, or (decremented) life that was <= 0 with all six momenta
           under 0.2: the resting prop replaces it (phprop_rest).  Otherwise the prop is
           deleted when it is 120 under the first alive player."""
        u32, w32 = self.u32, self.w32
        mul, add, sub, lt = C.mul, C.add, C.sub, C.lt
        if not self.s8(obj + 0x239) and not u32(G_SIM_FRAME) & 7:
            if self.call('water_test', u32(G_WORLD), self.vec(obj + 0x10), 0, F_TWELVE):
                self.w8(obj + 0x239, 1)
                self.obj_rand(obj)
                text = self.call('libc_sprintf', S_SPLASH_FORMAT, 1)
                entry = self.call('res_find', S_FX_LUMP, ('buf', text))
                self.call('sound_playOnObject', entry, obj, F_SPLASH_VOL)
                self.call('water_disturb', u32(G_WORLD), self.vec(obj + 0x10), F_700, F_24)
        mask = self.u64(obj + 0xE8)
        g = F_GRAV_LOW if u32(G_PROP_OPTIONS) & 0x100 else F_GRAV
        w32(obj + 0x1C4, sub(u32(obj + 0x1C4), C.div(g, u32(obj + 0x190))))
        level = add(u32(obj + 0x228), F_TWO)
        w32(obj + 0x230, 0)
        fsum, tsum, contact = [ZERO] * 3, [ZERO] * 3, False
        body = obj + 0x190
        mesh = 0
        while mask:
            if mask & 1:
                pts = self.hull_points(u32(obj + 0x4C), mesh)
                for j in range(8):
                    a = pts + 3 * j
                    p = [sub(C.from_int(self.s8(a + i)), u32(obj + 0xF0 + 4 * i)) for i in range(3)]
                    height = add(add(add(mul(p[0], u32(obj + 0x1EC)), mul(p[1], u32(obj + 0x1F0))),
                                     mul(p[2], u32(obj + 0x1F4))), u32(obj + 0x1A8))
                    if C.le(level, height):
                        continue
                    w = C.mat3_mul_vec_transposed(self.words(obj + 0x1D4, 9), p)
                    point = [add(w[i], u32(obj + 0x1A0 + 4 * i)) for i in range(3)]
                    countdown = u32(obj + 0x234)
                    if countdown:
                        w32(obj + 0x234, countdown - 1)
                        continue
                    if not lt(point[2], level):
                        continue
                    contact = True
                    vz = self.rb_point_velocity(body, point)[2]
                    if lt(vz, F_M1) and not self.s8(obj + 0x239):
                        sound = self.landing_sound(obj)
                        if sound is not None:
                            entry = self.call('res_find', S_FX_LUMP, ('buf', self.cstr(sound)))
                            self.call('sound_playOnObject', entry, obj, ONE)
                    if lt(vz, ZERO):
                        self.rb_apply_impulse(u32(obj + 0x23C), body, point, (ZERO, ZERO, ONE))
                        w32(obj + 0x230, 1)
                    depth = sub(level, point[2])
                    if lt(ONE, depth):
                        depth = ONE
                    push = mul(depth, F_PUSH)
                    if lt(ZERO, push):
                        self.rb_add_force(body, point, (ZERO, ZERO, push), fsum, tsum)
            mask >>= 1
            mesh += 1
        if self.u16(obj + 0x140) & 0x20:
            limit, low = F_SPIN_MAX, C.neg(F_SPIN_MAX)
            for off, inv in ((0x1C8, 0x194), (0x1CC, 0x198), (0x1D0, 0x19C)):
                i = u32(obj + inv)
                if lt(limit, mul(u32(obj + off), i)):
                    w32(obj + off, C.div(limit, i))
                if lt(mul(u32(obj + off), i), low):
                    w32(obj + off, C.div(low, i))
        self.rb_integrate(ONE, body, fsum, tsum)
        if contact:
            w32(obj + 0x1BC, mul(u32(obj + 0x1BC), F_DAMP))
            w32(obj + 0x1C0, mul(u32(obj + 0x1C0), F_DAMP))
        for off in (0x1D0, 0x1C8, 0x1CC):
            w32(obj + off, mul(u32(obj + off), F_DAMP))
        self.wvec(obj + 0x10, self.vec(obj + 0x1A0))
        m = u32(obj + 0x190)
        w32(obj + 0x1A8, add(u32(obj + 0x1A8), mul(u32(obj + 0x1C4), m)))
        d = [mul(u32(obj + 0x1BC), m), mul(u32(obj + 0x1C0), m), ZERO]
        ground = self.call('terrain_heightBelow', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
        w32(obj + 0x228, ground)
        if C.le(sub(u32(obj + 0x18), F_HUNDREDTH), ground):
            w32(obj + 0x18, ground)
        if lt(F_MILLI, add(mul(d[0], d[0]), mul(d[1], d[1]))):
            t, nx, ny = self.call('terrain_sweepCircle', u32(G_WORLD), self.vec(obj + 0x10), tuple(d), 1,
                                  u32(obj + 0x1C))
            d = [mul(v, t) for v in d]
            for i in (1, 2, 0):
                w32(obj + 0x10 + 4 * i, add(u32(obj + 0x10 + 4 * i), d[i]))
            self.call('obj_updateGridCell', obj)
            if lt(t, ONE):
                px, py = u32(obj + 0x1BC), u32(obj + 0x1C0)
                a = sub(F_MILLI, add(mul(nx, px), mul(ny, py)))
                if lt(ZERO, a):
                    w32(obj + 0x1C0, add(py, mul(mul(ny, a), F_1_5)))
                    w32(obj + 0x1BC, add(px, mul(mul(nx, a), F_1_5)))
            if self.s8(obj + 0x23A):
                v = self.rb_point_velocity(body, self.vec(obj + 0x10))
                size = mul(C.from_int(self.u8(obj + 0x28)), F_08)
                self.call('fx_impactPuffNearCamera', self.vec(obj + 0x1A0), tuple(v), 0, size, ONE)
        w32(obj + 0x1A0, u32(obj + 0x10))
        w32(obj + 0x1A4, u32(obj + 0x14))
        self.call('obj_updateGridCell', obj)
        speeds = (0x1C8, 0x1CC, 0x1D0, 0x1BC, 0x1C0, 0x1C4)
        if (self.s8(obj + 0x23A) == 1 and lt(C.fabs(sub(u32(obj + 0x18), ground)), F_TWELVE)
                and all(lt(C.fabs(u32(obj + off)), F_08) for off in speeds)):
            self.w8(obj + 0x23A, 2)
            block = self.call('pool_new', 0x4AC)
            if block:
                draw = self.obj_rand(obj)
                self.call('StaticFire_ctor', block, self.vec(obj + 0x10), (draw % 40) * 60 + 480, 0, 0, F_240, HALF)
        life = self.s16(obj + 0x10E)
        if life < -220:
            rest = True
        else:
            self.w16(obj + 0x10E, life - 1)
            rest = life <= 0 and all(lt(C.fabs(u32(obj + off)), F_02) for off in speeds)
        if rest:
            self.phprop_rest(obj)
            return
        if self.s32(G_NUM_PLAYERS) > 0:
            slot = self.s32(G_ALIVE_PLAYERS)
            if slot >= 0:
                player = u32((G_PLAYER_OBJ + slot * REC_SIZE) & M32)
                if player and lt(add(u32(obj + 0x18), F_120), u32(player + 0x18)):
                    self.call('obj_delete', obj)

    def phprop_rest(self, obj):
        """The resting prop: matrix +0x110 = R^T with the body position as translation,
        scaled by +0x240 (mat3_scale) and moved by minus the centre (mat34_translateLocal).
        An item prop (+0x238) becomes an ItemProp (pool 0x190, ItemProp_ctor3 with the record
        +0x148); a prop with a lump name (+0x54) a Prop_ctorNamed (pool 0x148, the three
        names); any other a Prop_ctorRes (pool 0x148, entries +0x4c/+0x50).  The mask +0xe8
        and the bits +0x140 (signed) go along.  Then obj_delete, block or not."""
        r = self.words(obj + 0x1D4, 9)
        m = C.mat3_transpose(r) + self.words(obj + 0x1A0, 3)
        m = C.mat3_scale(self.u32(obj + 0x240), m)
        m = C.mat34_translate_local(C.neg(self.u32(obj + 0xF0)), C.neg(self.u32(obj + 0xF4)),
                                    C.neg(self.u32(obj + 0xF8)), m)
        self.wwords(obj + 0x110, m)
        pos = self.vec(obj + 0x10)
        if self.s8(obj + 0x238):
            block = self.call('pool_new', 0x190)
            if block:
                self.itemprop_ctor3(block, pos, obj + 0x148, obj + 0x110)
        elif self.s8(obj + 0x54):
            block = self.call('pool_new', 0x148)
            if block:
                self.prop_ctor_named(block, pos, obj + 0x54, obj + 0x64, obj + 0xA4, self.u64(obj + 0xE8),
                                     self.s16(obj + 0x140), obj + 0x110)
        else:
            block = self.call('pool_new', 0x148)
            if block:
                self.prop_ctor_res(block, pos, self.u32(obj + 0x4C), self.u32(obj + 0x50), self.u64(obj + 0xE8),
                                   self.s16(obj + 0x140), obj + 0x110)
        self.call('obj_delete', obj)

    # =====================================================================================
    # The resting prop's constructors
    # =====================================================================================
    def _prop_common(self, obj, pos, flags, bits, matrix):
        self.gameobject_ctor(obj, tuple(pos), 0, 0)
        self.w32(obj + 0x48, VT_PROP)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | flags)
        self.call('obj_updateGridCell', obj)
        self.w16(obj + 0x140, bits | 1)
        self.w32(obj + 0x1C, PP.F_FOUR)
        self.wwords(obj + 0x110, self.words(matrix, 12))

    def _prop_tail(self, obj):
        if self.u16(obj + 0x140) & 2:
            self.call('obj_runEveryFrame', obj)
            self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4000)
        if self.u16(obj + 0x140) & 4:
            self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x1000)

    def prop_ctor_named(self, obj, pos, lump, model, texture, mask, bits, matrix):
        """Prop_ctorNamed 0x153ac0: GameObject_ctor (ONE SHARED DRAW), table 0x511d58,
        flags |= 0x1809, relinked, +0x140 = bits | 1, radius 4, the 3x4 matrix to +0x110,
        the names copied to +0x54/+0x64/+0xa4 and resolved (+0x4c, +0x50), +0xe8 = mask;
        bits 2: runs every frame and flags |= 0x4000; bits 4: flags |= 0x1000."""
        self._prop_common(obj, pos, 0x1809, bits, matrix)
        self.strcpy(obj + 0x54, lump)
        self.strcpy(obj + 0x64, model)
        self.strcpy(obj + 0xA4, texture)
        self.w32(obj + 0x4C, self.call('res_find', obj + 0x54, obj + 0x64))
        self.w32(obj + 0x50, self.call('res_find', obj + 0x54, obj + 0xA4))
        self.w64(obj + 0xE8, mask & M64)
        self._prop_tail(obj)

    def prop_ctor_res(self, obj, pos, model_entry, texture_entry, mask, bits, matrix):
        """Prop_ctorRes 0x153c88: as Prop_ctorNamed with flags |= 0x5809 and the entries
        given (no names, no lookups)."""
        self._prop_common(obj, pos, 0x5809, bits, matrix)
        self.w32(obj + 0x4C, model_entry)
        self.w32(obj + 0x50, texture_entry)
        self.w64(obj + 0xE8, mask & M64)
        self._prop_tail(obj)

    def itemprop_ctor3(self, obj, pos, record, matrix):
        """ItemProp_ctor3 0x1592bc (obj, position, item record, matrix): Prop_ctorNamed with
        'equipmnt.lmp' and the model / texture names of row item_getResourceIndex (asked
        twice) of 0x3e9ce0, mask all ones, bits 0; table 0x511c38; the empty item record
        then the record's 0x48 bytes at +0x148; flags |= 0x102000 and lose 0x1800, and lose
        0x3000 too when the record word +0x150 has bit 39; relinked."""
        a = self.item_resource_index(record)
        b = self.item_resource_index(record)
        model = self.u32((ITEM_MODELS + a * 16) & M32)
        texture = self.u32((ITEM_MODELS + b * 16 + 4) & M32)
        self.prop_ctor_named(obj, pos, S_EQUIP_LUMP, model, texture, M64, 0, matrix)
        self.w32(obj + 0x48, VT_ITEMPROP)
        for k in range(4):
            self.w16(obj + 0x16C + 8 * k, 0xFFFF)
        self.w8(obj + 0x169, 0xFF)
        self.w8(obj + 0x168, 0xFF)
        for k in range(4):
            self.w16(obj + 0x158 + 2 * k, 0)
            self.w16(obj + 0x160 + 2 * k, 0)
        for k in range(0, 0x48, 8):
            self.w64(obj + 0x148 + k, self.u64(record + k))
        flags = (self.u32(obj + 0xC) | 0x102000) & ~0x1800 & M32
        if self.u64(obj + 0x150) & 0x8000000000:
            flags &= ~0x3000
        self.w32(obj + 0xC, flags)
        self.call('obj_updateGridCell', obj)

    # =====================================================================================
    # GutChunk_run
    # =====================================================================================
    def chunk_type(self, bits, values):
        return values[0] if bits & 4 else values[1] if bits & 2 else values[2]

    def gutchunk_run(self, obj):
        """GutChunk_run 0x1edb18 (chunk).  In this order:

        1. PhProp_run.
        2. Rising faster than 1 (+0x1c4 > 1): ONE OWN DRAW d; d % 3 = 0 with the local
           option 0x44fdc0 non-zero spawns a particle (definition by the chunk bits +0x248: 4
           -> 0x870458, 2 -> 0x870408, else 0x8703b8) at the position, velocity 0.
        3. h = terrain_height(world, position; 8).  The spot is (x, y, h).
        4. Bits & 9 = 1 (deletes on its first bounce, and not bit 8), h under the chunk and
           above -10000, and the vertical speed crossed -1 or -2 downward since last frame
           (+0x24c): a falling decal, TWO OWN DRAWS (angle, then type base + (d & 1)).
        5. Last frame falling (+0x24c < 0) and now rising: a hard bounce (last < -1) plays
           the water-bounce sound (0x53e4a0) of fx.lmp at 0.5.  Bit 0: the chunk destroys itself through slot 1
           (argument 3) and returns.  Otherwise the bounce counter +0x25c, while non-zero,
           counts down; without bit 8 and with h under the chunk above -10000 each count
           leaves a decal, TWO OWN DRAWS (the second unused).
        6. Without bit 0, once (+0x260), when both horizontal momenta are under 0.1 (signed):
           +0x260 = 1 and, without bit 8, h <= z and above -10000, a resting decal, ONE OWN
           DRAW (angle), flag 1.
        7. +0x24c = +0x1c4."""
        u32, lt = self.u32, C.lt
        self.phprop_run(obj)
        if lt(ONE, u32(obj + 0x1C4)):
            d = self.obj_rand(obj)
            if d % 3 == 0 and u32(G_DECAL_DETAIL):
                definition = self.chunk_type(u32(obj + 0x248), PARTICLE_DEFS)
                self.call('particle_spawn', definition, self.vec(obj + 0x10), (ZERO, ZERO, ZERO), ZERO)
        pos = self.vec(obj + 0x10)
        h = self.call('terrain_height', u32(G_WORLD), pos, F_EIGHT)
        spot = (pos[0], pos[1], h)
        last = u32(obj + 0x24C)
        if (u32(obj + 0x248) & 9) == 1 and lt(h, u32(obj + 0x18)) and lt(F_M10000, h):
            vz = u32(obj + 0x1C4)
            if (lt(F_M1, last) and lt(vz, F_M1)) or (lt(F_M2, last) and lt(vz, F_M2)):
                base = self.chunk_type(u32(obj + 0x248), (4, 7, 1))
                angle = s16(self.obj_rand(obj))
                kind = (self.obj_rand(obj) & 1) + base
                self.call('decal_add', spot, angle & M32, kind, 0, F_TWELVE)
            last = u32(obj + 0x24C)
        bits = u32(obj + 0x248)
        if lt(last, ZERO) and lt(ZERO, u32(obj + 0x1C4)):
            if lt(last, F_M1):
                entry = self.call('res_find', S_FX_LUMP2, S_GUT_SPLAT)
                self.call('sound_playOnObject', entry, obj, HALF)
            bits = u32(obj + 0x248)
            if bits & 1:
                table = u32(obj + 0x48)
                this = (obj + self.s16(table + 8)) & M32
                target = u32(table + 0xC)
                self.call(DTORS.get(target, 'vcall_%x' % target), this, 3)
                return
            count = u32(obj + 0x25C)
            if count:
                if not bits & 8 and lt(h, u32(obj + 0x18)) and lt(F_M10000, h):
                    base = self.chunk_type(bits, (4, 7, 1))
                    angle = s16(self.obj_rand(obj))
                    self.obj_rand(obj)
                    self.call('decal_add', spot, angle & M32, base, 0, F_TWELVE)
                    bits, count = u32(obj + 0x248), u32(obj + 0x25C)
                self.w32(obj + 0x25C, count - 1)
        if (not bits & 1 and not self.s8(obj + 0x260) and lt(u32(obj + 0x1BC), F_TENTH)
                and lt(u32(obj + 0x1C0), F_TENTH)):
            self.w8(obj + 0x260, 1)
            if not bits & 8 and C.le(h, u32(obj + 0x18)) and lt(F_M10000, h):
                angle = s16(self.obj_rand(obj))
                self.call('decal_add', spot, angle & M32, self.chunk_type(bits, (3, 6, 0)), 1, F_TWELVE)
        self.w32(obj + 0x24C, u32(obj + 0x1C4))
