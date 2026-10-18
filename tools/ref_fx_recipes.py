#!/usr/bin/env python3
"""ref_fx_recipes.py - reference contracts of the one-shot and status effect recipes of
Champions: Return to Arms (SLUS_209.73, US v2.00): fx_spawn, and (below) the model
status, disintegrate, ice-shatter and lose-a-body-part effects.

A research tool, not game code.  Every function was written from the instruction sequence
at the address in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_fx_recipes.py (property names are given in the
docstrings).  docs/effects.md is the prose version.  Standard library only; no game data
is embedded: particle definitions are named by their address (the key the native client
uses to look the values up in the JSON that tools/fx_particle_defs.py reads from the
user's own executable).

Floats are raw 32-bit patterns computed with tools/ref_core.py (the console FPU's rules),
so the positions and velocities handed to particle_spawn match bit for bit.  Use
ref_core.to_float() to read them.

Output.  A recipe returns a list of call records, in the order the original makes them:

    ('ctor', def)                       particleDef_ctor 0x18f3d0 of a definition fx_spawn
                                        makes on its first use
    ('near', pos)                       isNearCameraFocus480 0x1ebd90 (per machine)
    ('spawn', backdate, def, pos, vel)  particle_spawn 0x18f3f8 (pos, vel: 3 patterns)
    ('sound_name', n)                   libc_sprintf of "dism_blood_goosh%d.anm" with n 1-4
    ('res_find', 'fx.lmp')              res_find 0x17365c of that name in fx.lmp
    ('sound', volume, pos)              sound_playAtPos 0x214428 with the found entry
    ('pool_new', size)                  pool_new 0x14fdb8 (the shared object pool)
    ('fire', pos)                       Fire_ctor 0x2020e0 on the new block

and the generators are ref_core.Lcg objects the caller passes and inspects afterwards.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                    # noqa: E402

M32 = 0xFFFFFFFF
ONE = C.ONE
ZERO = C.ZERO

# float constants of fx_spawn, as the compiler stored them (lui/ori pairs)
K_MINUS_HALF = 0xBF000000
K_QUARTER = 0x3E800000
K_0_07 = 0x3D8F5C28             # 0.06999999
K_0_75 = 0x3F400000
K_0_77 = 0x3F451EB8
K_1_28 = 0x3FA3D70A
K_1_633 = 0x3FD10624
K_4 = 0x40800000
K_4_75 = 0x40980000
K_5 = 0x40A00000
K_5_45 = 0x40AE6666
K_6 = 0x40C00000
K_6_05 = 0x40C19999
K_7_86 = 0x40FB851E
K_10_16 = 0x41228F5C
K_10_45 = 0x41273333
K_12 = 0x41400000
K_15 = 0x41700000
K_15_75 = 0x417C0000
K_16 = 0x41800000
K_18 = 0x41900000
K_20 = 0x41A00000
K_21_6 = 0x41ACCCCC
K_24 = 0x41C00000
K_24_72 = 0x41C5C28F
K_34 = 0x42080000
K_36 = 0x42100000
K_40 = 0x42200000
D_HALF = 0x3FE0000000000000

# The 24 definitions fx_spawn makes on first use, in the order of its 24 "made" flags
# (0x4f87bc + 4 * i).  Addresses only; the values come from the user's executable.
FX_SPAWN_DEFS = (0x86FC38, 0x86FC88, 0x86FCD8, 0x86FD28, 0x86FD78, 0x86FDC8, 0x86FE18,
                 0x86FE68, 0x86FEB8, 0x86FF08, 0x86FF58, 0x86FFA8, 0x86FFF8, 0x870048,
                 0x870098, 0x8700E8, 0x870138, 0x870188, 0x8701D8, 0x870228, 0x870278,
                 0x8702C8, 0x870318, 0x870368)
FX_SPAWN_MADE_FLAGS = 0x4F87BC

# Definitions that fx_spawn uses but that are made elsewhere (static initialisers)
DEF_BLOOD_RED = 0x8704A8        # id 0
DEF_BLOOD_RED_90 = 0x8704F8     # id 1
DEF_DUST = 0x4F8710             # id 2

BLOOD_SOUND_FORMAT = 'dism_blood_goosh%d.anm'
BLOOD_SOUND_LUMP = 'fx.lmp'
FX_SPAWN_LAST_ID = 0x16


def v3(x, y, z):
    return [x & M32, y & M32, z & M32]


def scaled(u, k):
    return [C.mul(u[0], k), C.mul(u[1], k), C.mul(u[2], k)]


def _jitter_centre(rng, pos, size, z_size=None, z_base=None, z_lift=None):
    """centre = (pos - size/2) + float(draw % size) per axis, x then y then z; the z axis
    may use another size (z_size) or base (z_base) and a lift added after."""
    half = C.from_int(size // 2)
    cx = C.add(C.sub(pos[0], half), C.from_int(rng.draw() % size))
    cy = C.add(C.sub(pos[1], half), C.from_int(rng.draw() % size))
    zs = size if z_size is None else z_size
    zb = half if z_base is None else z_base
    cz = C.add(C.sub(pos[2], zb), C.from_int(rng.draw() % zs))
    if z_lift is not None:
        cz = C.add(cz, z_lift)
    return [cx, cy, cz]


def _offset(rng, centre, size):
    """p = float(draw % size - size/2) + centre per axis (x, y, z)."""
    return [C.add(C.from_int(rng.draw() % size - size // 2), centre[k]) for k in range(3)]


def _point_within_15(rng, pos):
    """ids 0xd-0x10, 0x12: a random angle (the draw's top half, signed), a random radius
    r * 15 in x y, and (r' - 0.5) * 15 in z."""
    s = rng.draw()
    angle = C.s16(s)
    r = rng.unit()
    x = C.add(pos[0], C.mul(C.mul(C.cos16(angle), r), K_15))
    y = C.add(pos[1], C.mul(C.mul(C.sin16(angle), r), K_15))
    z = C.add(pos[2], C.mul(C.add(rng.unit(), K_MINUS_HALF), K_15))
    return [x, y, z]


def _abs_trunc(a):
    """abs((int)a) back to float: the integer abs() applied to a float (ids 0x15)."""
    return C.from_int(abs(C.s32(C.to_int(a))))


def fx_spawn(fx_id, pos, cosmetic, shared, near=True, gore=2, made=None,
             pool_new=lambda size: 1):
    """fx_spawn 0x1ef270 (id, pos*): one-shot burst at pos (3 float patterns).

    cosmetic, shared: ref_core.Lcg for g_cosmeticSeed 0x404460 and g_randSeed 0x404464
    (only id 5 draws the shared one).  near: what isNearCameraFocus480 answers.  gore:
    g_decalDetail 0x44fdc0.  made: a set of definition addresses already constructed
    (updated in place; None = all made).  pool_new(size) -> 0 for an exhausted pool.
    Returns the call records.  Difftest properties "fx_spawn id N"."""
    calls = []
    pos = v3(*pos)
    if fx_id != 5:
        calls.append(('near', list(pos)))
        if not near:
            return calls
    if made is not None:
        for d in FX_SPAWN_DEFS:
            if d not in made:
                made.add(d)
                calls.append(('ctor', d))
    if not 0 <= fx_id <= FX_SPAWN_LAST_ID:
        return calls

    def spawn(d, p, v):
        calls.append(('spawn', ZERO, d, list(p), list(v)))

    rng = cosmetic
    if fx_id in (0, 1, 9):
        if fx_id in (0, 1) and gore == 0:
            return calls
        centre = _jitter_centre(rng, pos, 12)
        u = rng.in_unit_sphere()
        k = C.rsqrt(ONE, C.add(C.add(C.mul(u[0], u[0]), C.mul(u[1], u[1])), C.mul(u[2], u[2])))
        d = scaled(scaled(u, k), K_34)
        d[2] = C.add(d[2], K_4)
        calls.append(('sound_name', (rng.draw() & 3) + 1))
        calls.append(('res_find', BLOOD_SOUND_LUMP))
        calls.append(('sound', ONE, list(pos)))
        defn = {0: DEF_BLOOD_RED, 1: DEF_BLOOD_RED_90, 9: 0x86FC38}[fx_id]
        for _ in range(300):
            u = rng.in_unit_sphere()
            r = rng.unit()
            t = scaled(d, r)
            vel = [C.add(C.mul(u[k], K_7_86), t[k]) for k in range(3)]
            rng.in_unit_sphere()                # drawn, then not used
            spawn(defn, centre, vel)
    elif fx_id in (2, 8):
        centre = _jitter_centre(rng, pos, 24, z_size=36, z_base=K_18)
        count, defn, half = (150, DEF_DUST, 12) if fx_id == 2 else (300, 0x86FE18, 24)
        for _ in range(count):
            vel = scaled(rng.in_unit_sphere(), K_10_45)
            spawn(defn, _offset(rng, centre, half), vel)
    elif fx_id in (3, 6):
        centre = _jitter_centre(rng, pos, 12, z_lift=K_18)
        k = K_16 if fx_id == 6 else K_10_16
        for _ in range(150):
            spawn(0x86FCD8, centre, scaled(rng.in_unit_sphere(), k))
    elif fx_id == 4:
        centre = _jitter_centre(rng, pos, 12, z_lift=K_18)
        for _ in range(150):
            vel = scaled(rng.in_unit_sphere(), K_16)
            spawn(0x86FD28, _offset(rng, centre, 24), vel)
    elif fx_id == 5:
        n = 3 + (shared.draw() & 1)
        for _ in range(n):
            x = C.add(C.sub(pos[0], K_6), C.from_int(shared.draw() % 12))
            y = C.add(C.sub(pos[1], K_6), C.from_int(shared.draw() % 12))
            z = C.add(pos[2], C.from_int(shared.draw() % 18))
            calls.append(('pool_new', 0x50))
            if pool_new(0x50):
                calls.append(('fire', [x, y, z]))
    elif fx_id in (7, 0x14):
        defn = 0x86FD78 if fx_id == 7 else 0x86FDC8
        for _ in range(3):
            a = rng.in_unit_sphere()
            v = rng.in_unit_sphere()
            vel = [C.mul(v[0], K_4_75), C.mul(v[1], K_4_75),
                   C.add(C.mul(C.mul(v[2], K_4_75), K_0_77), K_6_05)]
            p = [C.add(C.mul(a[0], K_15_75), pos[0]), C.add(C.mul(a[1], K_15_75), pos[1]),
                 C.add(C.add(C.mul(C.mul(a[2], K_15_75), K_0_75), K_0_07), pos[2])]
            spawn(defn, p, vel)
    elif fx_id == 10:
        centre = _jitter_centre(rng, pos, 10)
        for _ in range(25):
            vel = scaled(rng.in_unit_sphere(), K_5_45)
            spawn(0x86FE68, _offset(rng, centre, 24), vel)
        centre = _jitter_centre(rng, pos, 12, z_lift=K_18)
        for _ in range(80):
            vel = scaled(rng.in_unit_sphere(), K_20)
            spawn(0x86FEB8, _offset(rng, centre, 24), vel)
    elif fx_id in (0xB, 0xC):
        centre = _jitter_centre(rng, pos, 10)
        for _ in range(15):
            vel = scaled(rng.in_unit_sphere(), K_5_45)
            spawn(0x86FF08, _offset(rng, centre, 24), vel)
        centre = _jitter_centre(rng, pos, 12, z_lift=K_18)
        for _ in range(20):
            vel = scaled(rng.in_unit_sphere(), K_40)
            spawn(0x86FF58, _offset(rng, centre, 24), vel)
        if fx_id == 0xB:
            for _ in range(5):
                u = rng.in_unit_sphere()
                p = [C.add(C.mul(u[k], K_5), centre[k]) for k in range(3)]
                v = rng.in_unit_sphere()
                vel = [C.mul(v[0], K_21_6), C.mul(v[1], K_21_6),
                       C.add(C.mul(v[2], K_21_6), K_1_633)]
                spawn(0x86FFA8, p, vel)
    elif fx_id in (0xD, 0xE, 0xF, 0x10, 0x12):
        defn = {0xD: 0x86FFF8, 0xE: 0x870048, 0xF: 0x870098, 0x10: 0x8700E8,
                0x12: 0x870138}[fx_id]
        spawn(defn, _point_within_15(rng, pos), [ZERO, ZERO, ZERO])
    elif fx_id == 0x11:
        spawn(0x870188, pos, [ZERO, ZERO, ZERO])
    elif fx_id == 0x13:
        u = rng.in_unit_sphere()
        vel = [C.mul(u[0], K_21_6), C.mul(u[1], K_21_6), C.add(C.mul(u[2], K_21_6), K_1_633)]
        spawn(0x8701D8, pos, vel)
        if rng.draw() % 10 == 0:
            spawn(0x870228, pos, scaled(vel, K_QUARTER))
    elif fx_id == 0x15:
        for _ in range(5):
            u = rng.in_unit_sphere()
            p = [C.add(pos[0], C.mul(u[0], K_36)), C.add(pos[1], C.mul(u[1], K_36)),
                 C.add(pos[2], C.mul(_abs_trunc(u[2]), K_36))]
            v = rng.in_unit_sphere()
            vel = [C.mul(v[0], K_12), C.mul(v[1], K_12), C.mul(_abs_trunc(v[2]), K_12)]
            spawn(0x870278, p, vel)
        for _ in range(5):
            u = rng.in_unit_sphere()
            p = [C.add(pos[0], C.mul(u[0], K_6)), C.add(pos[1], C.mul(u[1], K_6)),
                 C.add(pos[2], C.mul(_abs_trunc(u[2]), K_6))]
            v = rng.in_unit_sphere()
            vz = C.d2f(C.dmul(C.i2d(abs(C.s32(C.to_int(v[2])))), D_HALF))
            vel = [C.mul(v[0], K_24), C.mul(v[1], K_24), C.mul(vz, K_24)]
            spawn(0x8702C8, p, vel)
    elif fx_id == 0x16:
        for defn, k, kz in ((0x870318, K_5, K_5), (0x870368, K_1_28, K_24_72)):
            u = rng.in_unit_sphere()
            uz = C.fabs(u[2]) if C.lt(u[2], ZERO) else u[2]
            spawn(defn, pos, [C.mul(u[0], k), C.mul(u[1], k), C.mul(C.mul(uz, k), kz)])
    return calls


# =======================================================================================
# Deaths: disintegrate, ice shatter
# =======================================================================================
#
# These read the model only through its sample points.  `model` is any object with
#     sample_count()                                   model_getSamplePointCount 0x1799c8
#     sample_point(scale, anim, pos, yaw, index) -> (point, size)
#                                                      model_getSamplePoint 0x178e18: the world
#                                                      position of sample point `index` of the
#                                                      posed model at pos/yaw, and its size value
# (patterns throughout).  The recipe records each query as ('sample', scale, anim, pos, yaw, i).

K_1E_5 = 0x3727C5AC             # 1e-05
K_35_35 = 0x420D6666
K_8_09E10 = 0x5196B020          # 8.09e10: "volume" per particle
K_3_14 = 0x4048F5C2
K_0_4 = 0x3ECCCCCC
DEF_DISINTEGRATE = 0x870638
DEF_DISINTEGRATE_ALT = 0x870688
DISINTEGRATE_SOUND = 'spel_dsrptn_afteraffct.anm'
SHATTER_SOUND_FORMAT = 'expl_ice%d.anm'
ICE_CHUNK_MODEL, ICE_CHUNK_TEXTURE = 'icechunk.vif', 'icechunk.tex'
ICE_CHUNK_LAUNCH_FLAGS = 0x30A
VT_LOOSE_ICE_CHUNK = 0x50F328


def _offset_by_yaw(p, yaw, dist):
    """p + (cos(yaw), sin(yaw), 0) * dist, z gets + 0.0 (so -0 becomes +0)."""
    return [C.add(p[0], C.mul(C.cos16(yaw), dist)), C.add(p[1], C.mul(C.sin16(yaw), dist)),
            C.add(p[2], ZERO)]


def disintegrate_model(model, pos, yaw, scale, offset, alternate, anim, rng):
    """fx_disintegrateModel 0x1f4340 (a0 obj, a1 model, a2 anim, a3 pos*, t0 yaw16, t1 alternate,
    f12 scale, f13 offset): the caller hides the object first (obj +0xc |= 2, done here only
    when there is a model), then the sound spel_dsrptn_afteraffct.anm (fx.lmp) at pos, then for
    every sample point i its size cubed is added to a running total and one particle is made
    per 8.09e10 of it (the remainder carries over to the next point):

        f      = (size * 1e-5) * 35.35
        p      = point + (u - 0.5) * f              per axis (draws x, y, z)
        vel    = (u - 0.5) * 3.14                   per axis (draws x, y, z)
        p     += (cos yaw, sin yaw, 0) * offset     when offset != 0
        spawn(backdate = u * 0.4 seconds, 0x870688 if alternate else 0x870638, p, vel)

    Cosmetic seed only (rng).  Difftest property "disintegrate"."""
    yaw = C.s16(yaw)
    calls = [('hide',), ('res_find', BLOOD_SOUND_LUMP, DISINTEGRATE_SOUND), ('sound', ONE, list(pos))]
    n = model.sample_count()
    calls.append(('sample_count',))
    total = ZERO
    for i in range(n):
        calls.append(('sample', scale, anim, list(pos), yaw, i))
        point, size = model.sample_point(scale, anim, pos, yaw, i)
        total = C.add(total, C.mul(C.mul(size, size), size))
        while C.lt(ZERO, total):
            total = C.sub(total, K_8_09E10)
            f = C.mul(C.mul(size, K_1E_5), K_35_35)
            p = [C.add(C.mul(C.add(rng.unit(), K_MINUS_HALF), f), point[k]) for k in range(3)]
            vel = [C.mul(C.add(rng.unit(), K_MINUS_HALF), K_3_14) for _ in range(3)]
            if not C.eq(offset, ZERO):
                p = _offset_by_yaw(p, yaw, offset)
            back = C.mul(rng.unit(), K_0_4)
            calls.append(('spawn', back, DEF_DISINTEGRATE_ALT if alternate else DEF_DISINTEGRATE,
                          p, vel))
    return calls


def shatter_to_loose_ice(model, pos, yaw, count, scale, offset, anim, shared,
                         pool_new=lambda size: 1):
    """fx_shatterToLooseIce 0x1fb240 (f12 count, f13 scale, f14 offset, a0 model, a1 anim,
    a2 pos*, a3 yaw16): the frozen creature breaks into `count` (truncated) LooseIceChunk
    props.  SHARED seed (g_randSeed 0x404464): one draw for the sound expl_ice<1-3>.anm
    (fx.lmp), then one per chunk for its size.  step = sample_count // count (a count of 0
    divides by zero in the original); with step 0 no chunk.  Chunk k (k = 1..count) sits at
    sample point (k * step) mod n (n queried again each time), moved by (cos, sin) * offset
    when offset != 0, and is PhProp_ctor 0x155a0c(1.0, pos, fx.lmp, icechunk.vif,
    icechunk.tex, part mask 2 / 3 / 4 for draw % 10 = 0 / 1-2 / 3-9, launch flags 0x30a, no
    item) with the LooseIceChunk table 0x50f328 at +0x48.  The chunk's own constructor draws
    more (GameObject_ctor; not part of this recipe).  Difftest property "ice shatter"."""
    yaw = C.s16(yaw)
    count = C.s32(C.to_int(count))
    calls = [('sample_count',)]
    n = model.sample_count()
    step = int(n / count)                         # div: toward zero
    calls.append(('sound_name', shared.draw() % 3 + 1))
    calls.append(('res_find', BLOOD_SOUND_LUMP))
    calls.append(('sound', ONE, list(pos)))
    if step == 0 or count <= 0:
        return calls
    index = 0
    while count > 0:
        calls.append(('sample_count',))
        n = model.sample_count()
        index = (index + step) % n if n > 0 else None
        calls.append(('sample', scale, anim, list(pos), yaw, index))
        point, _size = model.sample_point(scale, anim, pos, yaw, index)
        k = shared.draw() % 10
        mask = 2 if k == 0 else (3 if k < 3 else 4)
        if not C.eq(offset, ZERO):
            point = _offset_by_yaw(point, yaw, offset)
        calls.append(('pool_new', 0x248))
        if pool_new(0x248):
            calls.append(('phprop', ONE, list(point), BLOOD_SOUND_LUMP, ICE_CHUNK_MODEL,
                          ICE_CHUNK_TEXTURE, mask, ICE_CHUNK_LAUNCH_FLAGS, 0))
            calls.append(('vtable', VT_LOOSE_ICE_CHUNK))
        count -= 1
    return calls


# =======================================================================================
# Losing a body part: the eight callers of GutChunk_ctorFromProp 0x201ad0
# =======================================================================================
#
# Common recipe.  A model-variant bit is ORed into the creature's variant word +0xe8 (the bit
# per part is the class's own table), the mesh show mask +0x220 is rebuilt with
# model_buildHideMask 0x179550 (model = class data +0xc), and one GutChunk (pool block 0x268)
# is made from the creature's OWN model, showing only the meshes of the lost part:
#
#   GutChunk_ctorFromProp(scale, block, creature pos (+0x10), yaw (+0x38), class data +0xc
#       (model), creature +0x114 (anim state), class data +0 (lump), +8 (model name), +0x10
#       (texture; Ant: +0x18 when its colour byte +0x3c8 is 1), mask64, launch, bits)
#
# mask64 is either "old show mask AND NOT new show mask" (the meshes that the new variant bit
# just hid) or a constant mesh mask per part; launch is PhProp_ctor2's launch-flag argument;
# bits go to GutChunk +0x248 (2 = yellow blood, 0 = red, docs/effects.md section 9) - with
# gore below 2 GutChunk_ctorFromProp also sets bit 1 (an invisible drop).  Then the chunk's
# vertical speed +0x1c4 gets + 2.0 (not BlackWidow).  GutChunk_ctorFromProp itself: +0x248 =
# bits (| 1 when g_decalDetail < 2), table 0x50f3b8 at +0x48, +0x250 = a copy of its
# position, +0x25c = 2 (splats left), +0x260 = 0.

LOSE_PART_CLASSES = {
    # name: (address, part -> variant bit, part -> constant mesh mask or None (= old & ~new),
    #        launch, blood bits, lift, order) ; order 'mask-first' or 'chunk-first'
    'Ant': (0x236B0C, {n: 2 << n for n in range(8)}, None, 0xE, 2, True, 'mask-first'),
    'AntQueen?': (0x238360, {}, None, 0xE, 0, True, 'mask-first'),
    'FireBeetle': (0x247130, {n: 1 << (n - 1) for n in range(2, 8)},
                   {2: 0x4, 3: 0x6, 4: 0x40, 5: 0xC00, 6: 0x80, 7: 0x300}, 7, 2, True, 'chunk-first'),
    'Ghoul?': (0x2672F4, {0: 2, 1: 4, 2: 8, 3: 0x10, 4: 1},
               {0: 0x8, 1: 0x10, 2: 0x20, 3: 0x40, 4: 0x2}, 7, 0, True, 'chunk-first'),
    'Mosquito': (0x2982CC, {1: 0x10, 2: 0x10, 3: 0x40, 4: 2, 5: 1, 6: 4, 7: 8}, None, 0xE, 2,
                 True, 'mask-first'),
    'Orc': (0x2A3DE0, {1: 0x10000000, 2: 0x8000000, 3: 0x4000000, 4: 0x2000000, 5: 0x1000000},
            {1: 0x20406, 2: 0x800, 3: 0x10, 4: 0x1000, 5: 0x200}, 7, 0, True, 'chunk-first'),
    'Scorpion': (0x2A59F0, None, None, 0xE, 2, True, 'mask-first'),
    'BlackWidow': (0x2ACFD8, {n: 1 << n for n in range(12)}, None, 0xE, 2, False, 'mask-first'),
}
ORC_ATTACH_INDEX = {1: 8, 2: 6, 3: 7, 4: 4, 5: 5}


def orc_head_mask(variant):
    """Orc_severPart part 1 (0x2a3e30-0x2a3f28): the head chunk's mesh mask follows the head
    variants already set in +0xe8 (bits 0-6 and 8-11)."""
    m = 0x60406 if variant & 1 else 0x20406
    if variant & 2:
        m = (m ^ 2) | 0x80000
    for bit, high in ((4, 0x300000), (8, 0xC00000), (0x10, 0x3000000), (0x20, 0xC000000),
                      (0x40, 0x30000000)):
        if variant & bit:
            m = (m ^ 6) | high
    for k in range(4):
        if variant & (0x100 << k):
            m |= 0x80000000 << k
    return m
VT_GUTCHUNK = 0x50F3B8


class Creature:
    """The fields the part functions read (patterns for floats)."""

    def __init__(self, variant=0, cls=(0,) * 8, pos=(0, 0, 0), yaw=0, anim=0,
                 colour=0, scale=ONE, kind=0):
        self.variant, self.cls = variant & M32, list(cls)
        self.pos, self.yaw, self.anim = list(pos), yaw, anim
        self.colour, self.scale, self.kind = colour, scale, kind
        self.show = 0


def lose_body_part(name, c, part, show_mask, pool_new=lambda size: 1):
    """The part function of class `name` (LOSE_PART_CLASSES) on creature c, part number
    `part` (an unsigned 32-bit value).  show_mask(model, variant) -> 64-bit mask
    (model_buildHideMask; model = class data +0xc).  Updates c.variant and c.show; returns
    the call records.  Orc also asks model_getAttachPoint for the part's attach point (index
    ORC_ATTACH_INDEX) at yaw - 0x4001 and does not use it; its parts 6 and 7 (drop a held item
    as a PhProp) are never passed by its only caller and are not modelled.  BlackWidow does
    nothing at all while +0x414 is 1 and makes no chunk for parts 8-11.  'AntQueen?'
    (0x238360, in the AntQueen code) and 'Ghoul?' (0x2672f4, in the Ghoul code) have no caller
    anywhere (no call, jump or stored address).  Difftest properties "lose part <name>"."""
    _addr, bits, consts, launch, blood, lift, order = LOSE_PART_CLASSES[name]
    model = c.cls[3]
    calls = []
    if name == 'BlackWidow' and c.kind == 1:
        return calls
    bit = (1 << (part & 31)) if bits is None else bits.get(part, 0)
    if name == 'Orc':
        chunk = 1 <= part <= 5
    elif name == 'BlackWidow':
        chunk = not 8 <= part <= 11
    else:
        chunk = True
    mask64 = 0
    if order == 'mask-first':
        calls.append(('mask', model, c.variant))
        old = show_mask(model, c.variant)
        c.variant |= bit
        calls.append(('mask', model, c.variant))
        c.show = show_mask(model, c.variant)
        mask64 = old & ~c.show & 0xFFFFFFFFFFFFFFFF
    else:
        if name == 'Orc' and part == 1:
            mask64 = orc_head_mask(c.variant)
        else:
            mask64 = consts.get(part, 0)
        c.variant |= bit
        if name == 'Orc' and part in ORC_ATTACH_INDEX:
            calls.append(('attach', ONE, model, list(c.pos), C.s16(c.yaw - 0x4001), c.anim,
                          ORC_ATTACH_INDEX[part]))
    if chunk:
        calls.append(('pool_new', 0x268))
        if pool_new(0x268):
            tex = c.cls[6] if (name == 'Ant' and c.colour == 1) else c.cls[4]
            scale = c.scale if name == 'BlackWidow' else ONE
            calls.append(('gut', scale, list(c.pos), C.s16(c.yaw), model, c.anim, c.cls[0],
                          c.cls[2], tex, mask64, launch, blood))
            if lift:
                calls.append(('lift',))
    if order == 'chunk-first':
        calls.append(('mask', model, c.variant))
        c.show = show_mask(model, c.variant)
    return calls


# =======================================================================================
# Particles from model sample points, model arcs, model glow
# =======================================================================================

K_9 = 0x41100000
K_10 = 0x41200000
K_0_3 = 0x3E999999               # 0.29999998
K_16_59 = 0x4184BFAB             # 16.593588
K_3_76 = 0x4070B335              # 3.760938
K_1_00597 = 0x3F80C39F           # 1.0059699
K_1E_4 = 0x38D1B717              # 0.0001
K_1_145E8 = 0x4CDA69C5           # 1.145114e8
K_94 = 0x42BC0000
K_250 = 0x437A0000
K_2013 = 0x44FBA000
K_10000 = 0x461C4000
K_60 = 0x42700000
K_GLOW_BIAS = 0xC14DB22D         # -12.856 (glow_add f12)
GLOW_TEXTURE_HALO2 = 0x4F848C    # fx.lmp : halo2.tex (written by main 0x324028)


def emit_from_model_verts(model, pos, yaw, anim, count, defn, direction, offset, speed, rng):
    """fx_emitFromModelVerts 0x1eb1e8 (f12 speed, a0 obj, a1 count, a2 def, a3 dir* or 0,
    t0 offset* or 0): `count` particles of `defn`, each at a random sample point of the
    object's model (obj slot 0x84 / 0x80 gives the model; position obj +0x10, yaw +0x38,
    anim +0x114, scale 1.0) plus offset, moving with dir * speed, or with a random unit-ball
    vector * speed when dir is 0.  Per particle: the unit-ball draws (if any) come first,
    then one draw for the sample index (draw % n; n = 0 divides by zero).  Cosmetic seed.
    Difftest property "emit from model verts"."""
    calls = [('get_model',), ('sample_count',)]
    n = model.sample_count()
    yaw = C.s16(yaw)
    while count > 0:
        u = direction if direction is not None else rng.in_unit_sphere()
        vel = scaled(u, speed)
        index = rng.draw() % n
        calls.append(('sample', ONE, anim, list(pos), yaw, index))
        p, _size = model.sample_point(ONE, anim, pos, yaw, index)
        if offset is not None:
            p = [C.add(p[k], offset[k]) for k in range(3)]
        calls.append(('spawn', ZERO, defn, list(p), vel))
        count -= 1
    return calls


def _round_half_away(a):
    return C.s32(C.to_int(C.add(a, C.HALF) if C.le(ZERO, a) else C.sub(a, C.HALF)))


def model_sparkle(model, pos, yaw, anim, amount, offset, rng, near=True):
    """fx_modelParticlesNearCamera_1f5210 (f13 amount, f14 offset, a0 model, a1 anim, a2 pos*,
    a3 yaw16; f12 unused): two passes over random sample points, camera gated
    (isNearCameraFocus480 of pos; no model or no sample point: nothing).  Pass 0 visits
    round(amount * 16.593588) points with definition 0x870728 and speed 10, pass 1
    round(amount * 3.760938) points with 0x870778 and speed 9 (rounding half away from 0).
    At each point (one draw: the index; scale = amount) p = point + (cos, sin, 0) * offset,
    then while the running value size^2 (minus 1.145114e8 per particle) is above 0:

        p   += (u - 0.5) * ((size * 1.0059699) * 0.0001)    per axis - a random walk: p is
                                                              NOT reset between particles
        vel  = unit-ball * speed
        spawn(backdate = u * 0.3 s, def, p, vel)

    Callers Creature_run, Demon_run, Vampire_run.  Difftest property "model sparkle"."""
    calls = [('near', list(pos))]
    if not near or model is None:
        return calls
    calls.append(('sample_count',))
    n = model.sample_count()
    if n == 0:
        return calls
    yaw = C.s16(yaw)
    for passno, (k_count, defn, speed) in enumerate(((K_16_59, 0x870728, K_10),
                                                      (K_3_76, 0x870778, K_9))):
        count = _round_half_away(C.mul(amount, k_count))
        while count > 0:
            index = rng.draw() % n
            calls.append(('sample', amount, anim, list(pos), yaw, index))
            p, size = model.sample_point(amount, anim, pos, yaw, index)
            ox, oy = C.mul(C.cos16(yaw), offset), C.mul(C.sin16(yaw), offset)
            p = [C.add(p[0], ox), C.add(p[1], oy), C.add(p[2], ZERO)]
            volume = C.mul(size, size)
            while C.lt(ZERO, volume):
                f = C.mul(C.mul(size, K_1_00597), K_1E_4)
                d = [C.mul(C.sub(rng.unit(), C.HALF), f) for _ in range(3)]
                p = [C.add(p[k], d[k]) for k in range(3)]
                vel = scaled(rng.in_unit_sphere(), speed)
                back = C.mul(rng.unit(), K_0_3)
                calls.append(('spawn', back, defn, list(p), vel))
                volume = C.sub(volume, K_1_145E8)
            count -= 1
    return calls


K_7_78 = 0x40F8F5C2
K_4_47 = 0x408F0A3D
DEF_ARC_SPARK = 0x8708B8
DEF_ARC_SPARK_SLOW = 0x870908


class ArcState:
    """The 0x18 bytes at t0 + 8 (three arcs): per arc, sample indices (s16) at +8 / +0xa and
    a beam handle at +0xc, every 8 bytes."""

    def __init__(self, arcs=None):
        self.arcs = [list(a) for a in arcs] if arcs else [[0, 0, 0] for _ in range(3)]


def model_arcs(model, pos, yaw, anim, alpha, scale, offset, state, rgba, rng, near=True,
               beam_create=lambda *a: 0):
    """fx_modelParticlesNearCamera_1f61c0 (f12 alpha, f13 scale, f14 offset, a0 model, a1 anim,
    a2 pos*, a3 yaw16, t0 state, t1 rgba): three lightning arcs between pairs of sample points
    of a model, camera gated like model_sparkle.  alpha is clamped to at most 1.  Per arc:
    with no beam, or when a draw is below 20000 (about 30 % of the time), the arc jumps: two
    new indices (draw % n each), and beam_create(jitter 7.78, scale 4.47, a, b, width 0xcf,
    depth 4, rgba).  Otherwise the indices (reset to 0 when above n) are looked up again,
    beam_update(handle, a, b, alpha 94 * alpha, -1), and each end gets a spark: velocity
    (u.x, u.y, u.z) * 21.6 + (0, 0, 1.633) of 0x8708b8, and on one draw in ten a second one of
    0x870908 at a quarter of that velocity (the fx_spawn id 0x13 recipe).  Ends move by
    (cos, sin, 0) * offset when offset != 0.  Callers Creature_run, Innoruuk_run,
    SpellHateEffect_update, JumpGate_run, jumpgate_travelEffect, SpellAncestralCall,
    SpellLightningWeapons_run.  Difftest property "model arcs"."""
    calls = [('near', list(pos))]
    if not near or model is None:
        return calls
    calls.append(('sample_count',))
    n = model.sample_count()
    if n == 0:
        return calls
    if C.lt(ONE, alpha):
        alpha = ONE
    yaw = C.s16(yaw)

    def ends(ia, ib):
        out = []
        for index in (ia, ib):
            calls.append(('sample', scale, anim, list(pos), yaw, index))
            out.append(model.sample_point(scale, anim, pos, yaw, index)[0])
        if not C.eq(offset, ZERO):
            ox, oy = C.mul(C.cos16(yaw), offset), C.mul(C.sin16(yaw), offset)
            out = [[C.add(p[0], ox), C.add(p[1], oy), C.add(p[2], ZERO)] for p in out]
        return out

    for arc in state.arcs:
        jump = arc[2] == 0 or rng.draw() < 20000
        if jump:
            arc[2] = 0
            arc[0] = C.s16(rng.draw() % n)
            arc[1] = C.s16(rng.draw() % n)
            a, b = ends(arc[0], arc[1])
            calls.append(('beam_create', K_7_78, K_4_47, a, b, 0xCF, 4, rgba))
            arc[2] = beam_create(a, b) & M32
        else:
            if n < arc[0]:
                arc[0] = 0
            if n < arc[1]:
                arc[1] = 0
            a, b = ends(arc[0], arc[1])
            calls.append(('beam_update', arc[2], a, b, C.s32(C.to_int(C.mul(alpha, K_94))), M32))
            for p in (a, b):
                u = rng.in_unit_sphere()
                vel = [C.mul(u[0], K_21_6), C.mul(u[1], K_21_6), C.add(C.mul(u[2], K_21_6), K_1_633)]
                calls.append(('spawn', ZERO, DEF_ARC_SPARK, list(p), vel))
                if rng.draw() % 10 == 0:
                    calls.append(('spawn', ZERO, DEF_ARC_SPARK_SLOW, list(p), scaled(vel, K_QUARTER)))
    return calls


class GlowRamp:
    """Object +0x70 (four floats, ramp A) and +0x80 (four floats, ramp B: the glow colour)."""

    def __init__(self, a=(ZERO,) * 4, b=(ZERO,) * 4):
        self.a, self.b = list(a), list(b)


def model_glow(model, obj_flags, ramp, pos, yaw, anim, scale, offset, fade, target_a, target_b,
               mode, size_add, sim_frame, near=True):
    """fx_drawModelGlowNearCamera 0x1f5890 (a0 obj, a1 model, a2 anim, a3 pos*, t0 yaw16, t2
    target A (4 s16), t3 target B (4 s16), stack +0 mode, stack +8 size add (int); f13 scale,
    f14 offset, f15 fade seconds; t1 and f12 unused), from Creature_draw and FireBeetle_draw:
    per RENDERED frame.
    Camera gated; nothing without the object, its flag 0x20 (+0xc), the model or a sample
    point.  Mode 0 ramps the object's two colours up toward the targets by target / (fade *
    60) per call (clamped at the target), mode 2 down by the same step (clamped at 0), other
    modes hold.  Then one glow per sample point i, at point(pos moved by (cos, sin) * offset in
    x y), bias -12.856, size ((sin16(g_simFrame << 10) * 250 + 10000) - 2013) + size_add,
    colour (int) ramp B, texture *0x4f848c (fx.lmp : halo2.tex), angle (g_simFrame << 6)
    as s16, flags 3 (rotated, additive).  Difftest property "model glow"."""
    calls = [('near', list(pos))]
    if not near or model is None:
        return calls
    calls.append(('sample_count',))
    n = model.sample_count()
    if n == 0:
        return calls
    yaw = C.s16(yaw)
    p = [C.add(pos[0], C.mul(C.cos16(yaw), offset)), C.add(pos[1], C.mul(C.sin16(yaw), offset)),
         pos[2]]
    if obj_flags is None or not obj_flags & 0x20:
        return calls
    fa = [C.from_int(C.s16(v)) for v in target_a]
    fb = [C.from_int(C.s16(v)) for v in target_b]
    if mode == 0:
        for k in range(4):
            step = C.mul(fade, K_60)
            ramp.a[k] = C.add(ramp.a[k], C.div(fa[k], step))
            ramp.b[k] = C.add(ramp.b[k], C.div(fb[k], step))
            if C.lt(fa[k], ramp.a[k]):
                ramp.a[k] = fa[k]
            if C.lt(fb[k], ramp.b[k]):
                ramp.b[k] = fb[k]
    elif mode == 2:
        for k in range(4):
            step = C.mul(fade, K_60)
            ramp.a[k] = C.sub(ramp.a[k], C.div(fa[k], step))
            ramp.b[k] = C.sub(ramp.b[k], C.div(fb[k], step))
            if C.lt(ramp.a[k], ZERO):
                ramp.a[k] = ZERO
            if C.lt(ramp.b[k], ZERO):
                ramp.b[k] = ZERO
    for i in range(n):
        calls.append(('sample', scale, anim, list(p), yaw, i))
        point, _ = model.sample_point(scale, anim, p, yaw, i)
        size = C.add(C.sub(C.add(C.mul(C.sin16((sim_frame << 10) & 0xFFFF), K_250), K_10000),
                           K_2013), C.from_int(size_add))
        rgba = [C.s32(C.to_int(v)) & M32 for v in ramp.b]
        calls.append(('glow', K_GLOW_BIAS, size, list(point), rgba, GLOW_TEXTURE_HALO2,
                      C.s16((sim_frame << 22) >> 16), 3))
    return calls


# =======================================================================================
# Weapon and status visuals: fx_modelStatusEffects 0x1f6ac8
# =======================================================================================

CODE_LIGHTNING, CODE_COLD, CODE_FIRE, CODE_POISON, CODE_DISEASE = 0x18, 0x16, 0x15, 0x17, 0x26
LEVEL_FLAG_NO_STATUS_FX = 0x10000000          # level flag word 0x44fe08: return at once
LEVEL_FLAG_NO_SWING_TRAIL = 0x100             # sparks of fx_spawn 0x11 instead of the trail

K_0_05 = 0x3D4CCCCC
K_0_2 = 0x3E4CCCCC
K_0_68 = 0x3F2E147A
K_0_7 = 0x3F333333
K_0_00191 = 0x3AFA58F5
K_0_00291 = 0x3B3EB5B1
K_1_24TH = 0x3D2AAAAA
K_0_074 = 0x3D978D4F
K_0_156 = 0x3E1FBDAD
K_0_206 = 0x3E52EB5F
K_0_229 = 0x3E6A7EF9
K_0_556 = 0x3F0E55F3
K_0_578 = 0x3F13F7AD
K_0_667 = 0x3F2AC072
K_0_785 = 0x3F48F590
K_0_97 = 0x3F7851EB
K_2_47 = 0x401E147A
K_2_83 = 0x40351EB8
K_3 = 0x40400000
K_3_13 = 0x404851EB
K_3_5 = 0x40600000
K_3_974 = 0x407E5597
K_6_388 = 0x40CC6A46
K_6_589 = 0x40D2D916
K_13_13 = 0x4152147A
K_19_74 = 0x419DEB85
K_30 = 0x41F00000
ARC_RGBA = 0x5E808080
SPARK_DEFS = {1: 0x870BD8, 2: 0x870C28, 3: 0x870C78}


class WeaponFxState:
    """The caller's 0x40-byte state (a2): +0x00 the last matrix (mat34, 12 patterns),
    +0x30 g_simFrame of the last swing, +0x34 lightning beam handle, +0x38 swing trail
    handle, +0x3c swing counter (s8, 0..100), +0x3d spark kind, +0x3e sparks left (s8)."""

    def __init__(self, matrix=None, frame=0, beam=0, trail=0, counter=0, spark_kind=0, sparks=0):
        self.matrix = list(matrix) if matrix else [ZERO] * 12
        self.frame, self.beam, self.trail = frame & M32, beam & M32, trail & M32
        self.counter, self.spark_kind, self.sparks = counter, spark_kind, sparks


class WeaponItem:
    """The fields of the item record (a0) it reads: +0x10 glow colour (4 s16), +0x18 a second
    colour (4 s16) - both fade toward 0 by 2 per call - and the four effect entries at +0x24
    (8 bytes: s16 code, s16 value, ...; docs/gameplay.md 2.2)."""

    def __init__(self, glow=(0, 0, 0, 0), colour2=(0, 0, 0, 0), entries=()):
        self.glow, self.colour2 = [C.s16(v) for v in glow], [C.s16(v) for v in colour2]
        self.entries = [tuple(e) for e in entries] + [(0, 0)] * (4 - len(entries))

    def value(self, code):
        """The value of the first entry with this code (0 when none)."""
        for c, v in self.entries:
            if C.s16(c) == code:
                return C.s16(v)
        return 0


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def _norm_scaled(v, scale):
    k = C.rsqrt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2])))
    return [C.mul(C.mul(v[i], k), scale) for i in range(3)]


def _vsub(a, b):
    return [C.sub(a[i], b[i]) for i in range(3)]


def _vadd(a, b):
    return [C.add(a[i], b[i]) for i in range(3)]


def _length(v):
    return C.sqrt(C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2])))


def model_status_effects(amount, scale, item, model, state, pos, yaw, holder, anim, swinging,
                         joint_add, override, rng, level_flags=0, gore=2, sim_frame=0,
                         dialog_open=False, answers=None):
    """fx_modelStatusEffects 0x1f6ac8 (f12 amount, f13 scale, a0 item, a1 weapon model, a2
    state, a3 pos*, t0 yaw16, t1 holder model, t2 holder anim, t3 swinging, stack +0 joint add,
    stack +8 matrix override* or 0).  Called once per frame for a held weapon (Weapon1/2,
    Player_weaponTrails, projectiles, Cyclops, VampireLord, Innoruuk).  model is the weapon
    model adapter (sample_count, transform_sample_point(matrix, i) -> (point, size),
    effect_segment() -> (a, b) vec3), holder the holder's model (attach_matrix(scale, anim,
    index) -> mat34) or None.  answers: dict with 'trail_create', 'beam_create', 'beam_alive'
    results.  Returns the call records; updates item and state.  Difftest property
    "weapon status".  See docs/effects.md for the prose."""
    answers = answers or {}
    calls = []
    if level_flags & LEVEL_FLAG_NO_STATUS_FX or model is None:
        return calls
    calls.append(('dialog_open',))
    if dialog_open:
        return calls
    if not swinging:
        state.counter = 0
    elif state.counter < 100:
        state.counter += 1
    gated = swinging or any(item.value(c) for c in (CODE_LIGHTNING, CODE_COLD, CODE_FIRE,
                                                     CODE_POISON, CODE_DISEASE)) \
        or any(item.glow)
    if not gated:
        m = C.mat34_set_identity()
    else:
        if holder is not None:
            index = s8(model.attach_base) + joint_add
            calls.append(('attach_matrix', scale, anim, C.s32(index)))
            m = list(holder.attach_matrix(scale, anim, index))
        else:
            m = C.mat34_set_identity()
        m = C.mat34_mul(m, C.mat34_set_pos_rot_z(pos, C.s16(yaw + 0x4000)))
    if override is not None:
        m = list(override)
    s = state.matrix
    if C.eq(s[0], ONE) and C.eq(s[4], ONE) and C.eq(s[8], ONE):
        if C.eq(s[9], s[10]):
            copy = not C.eq(s[11], ONE)
        else:
            copy = not C.eq(s[11], ZERO)
        if copy:
            state.matrix = s = list(m)
    cur_r1, cur_t = m[3:6], m[9:12]
    prev_r1, prev_t = s[3:6], s[9:12]
    if not level_flags & LEVEL_FLAG_NO_SWING_TRAIL:
        if not swinging or override is not None:
            state.trail = 0
            state.spark_kind = state.sparks = 0
        else:
            cd = _norm_scaled(cur_r1, scale)
            pd = _norm_scaled(prev_r1, scale)
            calls.append(('effect_segment',))
            seg_a, seg_b = model.effect_segment()
            base = [C.add(cur_t[i], C.mul(cd[i], seg_a[1])) for i in range(3)]
            tip = [C.add(cur_t[i], C.mul(cd[i], seg_b[1])) for i in range(3)]
            w = C.mul(_length(_vsub(cd, pd)), K_0_68)
            w = C.fmax(w, ZERO)
            w = C.fmin(w, ONE)
            w = C.mul(w, K_0_3)
            w = C.fmin(w, C.mul(C.from_int(s8(state.counter)), K_0_05))
            if state.trail == 0 or state.frame != (sim_frame - 1) & M32:
                calls.append(('trail_create', K_0_2, 3, 1000, 2, 0x80, 0x80, 0x80, 0))
                state.trail = answers.get('trail_create', 0) & M32
            else:
                mt = [C.mul(C.add(cur_t[i], prev_t[i]), C.HALF) for i in range(3)]
                md = [C.mul(C.add(cd[i], pd[i]), C.HALF) for i in range(3)]
                md = _norm_scaled(md, scale)
                mbase = [C.add(mt[i], C.mul(md[i], seg_a[1])) for i in range(3)]
                mtip = [C.add(mt[i], C.mul(md[i], seg_b[1])) for i in range(3)]
                calls.append(('trail_pair', w, state.trail, mtip, mbase))
            calls.append(('trail_pair', w, state.trail, tip, base))
            c = s8(state.sparks)
            if c != 0:
                if gore > 0:
                    d = _vsub(tip, base)
                    k = C.rsqrt(ONE, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
                    dn2 = [C.add(C.mul(d[i], k), C.mul(d[i], k)) for i in range(3)]
                    prev_tip = [C.add(prev_t[i], C.mul(pd[i], seg_b[1])) for i in range(3)]
                    for i in range(max(c, 0)):
                        d = _vsub(tip, base)
                        q = [C.sub(tip[j], C.mul(d[j], K_0_7)) for j in range(3)]
                        f = C.from_int(c - i)
                        start = [C.sub(q[j], C.mul(dn2[j], f)) for j in range(3)]
                        n2 = 2 * i
                        fn = C.from_int(n2)
                        step = [C.div(C.sub(prev_tip[j], tip[j]), fn) for j in range(3)]
                        for jj in range(n2):
                            fj = C.from_int(jj)
                            p = [C.add(start[t], C.mul(step[t], fj)) for t in range(3)]
                            vel = [C.mul(dn2[t], K_9) for t in range(3)]
                            defn = SPARK_DEFS.get(s8(state.spark_kind))
                            if defn:
                                calls.append(('spawn', ZERO, defn, p, vel))
                state.sparks = (c - 1) & 0xFF
            return _finish(calls, amount, item, model, state, m, s, swinging, rng, sim_frame,
                           gore, answers)
    else:
        if not swinging:
            state.trail = 0
            state.spark_kind = state.sparks = 0
        else:
            cd = _norm_scaled(cur_r1, scale)
            pd = _norm_scaled(prev_r1, scale)
            calls.append(('effect_segment',))
            _seg_a, seg_b = model.effect_segment()
            tip = [C.add(cur_t[i], C.mul(cd[i], seg_b[1])) for i in range(3)]
            v = _length(_vsub(cd, pd))
            v = C.add(v, v)
            if C.lt(ONE, v):
                v = ONE
            if C.lt(v, ZERO):
                v = ZERO
            r = rng.draw()
            div = 6 - C.s32(C.to_int(C.mul(v, K_5)))
            if r % div == 0:
                calls.append(('fx_spawn', 0x11, tip))
            return _finish(calls, amount, item, model, state, m, s, swinging, rng, sim_frame,
                           gore, answers)
    return _finish(calls, amount, item, model, state, m, s, swinging, rng, sim_frame, gore,
                   answers)


def _swing_trail(calls, rng, m, s, clamp_e, k_count, defn, k_speed, doubled):
    """The ribbon of particles along the blade between last frame and this one (cold,
    poison and disease while swinging)."""
    t, r = list(m[9:12]), list(m[3:6])
    tp, rp = s[9:12], s[3:6]
    a = [C.add(t[i], C.mul(r[i], K_36)) for i in range(3)]
    b = [C.add(tp[i], C.mul(rp[i], K_36)) for i in range(3)]
    d = _length(_vsub(a, b))
    if C.lt(K_30, d):
        d = K_30
    whole = C.s32(C.to_int(C.mul(d, k_count)))
    n = whole * 2 if doubled else whole
    e = C.mul(d, clamp_e)
    k = C.div(ONE, C.from_int(whole))
    st = [C.mul(C.sub(tp[i], t[i]), k) for i in range(3)]
    sr = [C.mul(C.sub(rp[i], r[i]), k) for i in range(3)]
    for _ in range(n):
        rr = C.add(C.mul(C.mul(C.from_int(rng.draw()), C.TWO_M16), K_30), K_6)
        f = C.mul(C.mul(e, C.from_int(rng.draw())), C.TWO_M16)
        p = [C.add(t[i], C.mul(r[i], rr)) for i in range(3)]
        u = rng.in_unit_sphere()
        vel = [C.add(C.mul(r[i], f), C.mul(u[i], k_speed)) for i in range(3)]
        calls.append(('spawn', ZERO, defn, p, vel))
        t = _vadd(t, st)
        r = _vadd(r, sr)


def _walk(calls, rng, model, mi, step, index_count, back, back_step, emit):
    """Particles at random sample points of the weapon, the matrix walking from last frame's
    toward this frame's by `step` per particle; emit(p) adds the particle calls."""
    for _ in range(index_count):
        index = rng.draw() % model.n_samples
        calls.append(('transform_sample', list(mi), index))
        p, size = model.transform_sample_point(mi, index)
        f = C.mul(C.mul(size, K_1E_5), K_35_35)
        p = [C.add(p[i], C.mul(C.sub(rng.unit(), C.HALF), f)) for i in range(3)]
        emit(p, back)
        mi = [C.add(mi[i], step[i]) for i in range(12)]
        back = C.add(back, back_step)
    return mi, back


def _motion(calls, m, s, clamp):
    a = C.mat34_transform_point(m, [ZERO, ZERO, K_36])
    b = C.mat34_transform_point(s, [ZERO, ZERO, K_36])
    d = _length(_vsub(a, b))
    if C.lt(clamp, d):
        d = clamp
    return d


def _finish(calls, amount, item, model, state, m, s, swinging, rng, sim_frame, gore, answers):
    if any(item.glow):
        calls.append(('sample_count',))
        n = model.sample_count()
        for i in range(n):
            calls.append(('transform_sample', list(m), i))
            p, _ = model.transform_sample_point(m, i)
            size = C.sub(C.add(C.mul(C.sin16((sim_frame << 10) & 0xFFFF), K_250), K_10000), K_2013)
            calls.append(('glow', K_GLOW_BIAS, size, list(p), [v & M32 for v in item.glow],
                          GLOW_TEXTURE_HALO2, C.s16((sim_frame << 22) >> 16), 3))
    for arr in (item.colour2, item.glow):
        for i, v in enumerate(arr):
            arr[i] = max(v - 2, 0) if v > 0 else (min(v + 2, 0) if v < 0 else 0)
    # lightning
    if item.value(CODE_LIGHTNING) == 0 or C.le(amount, ZERO):
        state.beam = 0
    else:
        d = _motion(calls, m, s, K_15)
        back = C.mul(d, K_0_00291)
        count = C.s32(C.to_int(C.mul(C.from_int(C.s32(C.to_int(C.mul(d, K_13_13))) + 1), amount)))
        if count < 1:
            count = 1
        k = C.div(ONE, C.from_int(count))
        step = [C.mul(C.sub(m[i], s[i]), k) for i in range(12)]
        calls.append(('sample_count',))
        model.n_samples = model.sample_count()
        loops = max(int(count / 4), 8)
        back_step = C.mul(k, K_1_24TH)

        def emit(p, bk):
            u = rng.in_unit_sphere()
            vel = [C.add(ZERO, C.mul(u[0], K_3)), C.add(ZERO, C.mul(u[1], K_3)),
                   C.add(K_19_74, C.mul(u[2], K_3))]
            calls.append(('spawn', bk, 0x870958, p, vel))
        _walk(calls, rng, model, list(s), step, loops, back, back_step, emit)
        ends = []
        for _ in range(2):
            index = rng.draw() % model.n_samples
            calls.append(('transform_sample', list(m), index))
            ends.append(model.transform_sample_point(m, index)[0])
        alive = False
        if state.beam != 0:
            calls.append(('beam_alive', state.beam))
            alive = answers.get('beam_alive', 0)
        if state.beam == 0 or not alive:
            calls.append(('beam_create', K_7_78, K_2_47, ends[0], ends[1], 0x6B, 4, ARC_RGBA))
            state.beam = answers.get('beam_create', 0) & M32
        else:
            calls.append(('beam_update', state.beam, ends[0], ends[1],
                          C.s32(C.to_int(C.mul(amount, K_94))), M32))
    # cold
    if item.value(CODE_COLD) != 0:
        d = _motion(calls, m, s, K_20)
        back = C.mul(d, K_0_00191)
        count = C.s32(C.to_int(C.mul(C.from_int(C.s32(C.to_int(C.mul(d, K_3_13))) + 0x1A), amount)))
        k = C.div(ONE, C.from_int(count))
        step = [C.mul(C.sub(m[i], s[i]), k) for i in range(12)]
        calls.append(('sample_count',))
        model.n_samples = model.sample_count()
        _walk(calls, rng, model, list(s), step, count, back, C.mul(k, K_1_24TH),
              lambda p, bk: calls.append(('spawn', bk, 0x870AE8, p, [ZERO, ZERO, ZERO])))
        if swinging:
            _swing_trail(calls, rng, m, s, K_0_97, K_0_229, 0x870B38, K_2_83, True)
            _swing_trail(calls, rng, m, s, K_0_97, K_0_229, 0x870B88, K_2_83, False)
    # fire
    if item.value(CODE_FIRE) != 0:
        d = _motion(calls, m, s, K_20)
        back = C.mul(d, K_0_00191)
        count = C.s32(C.to_int(C.mul(C.from_int(C.s32(C.to_int(C.mul(d, K_3_13))) + 0x10), amount)))
        k = C.div(ONE, C.from_int(count))
        step = [C.mul(C.sub(m[i], s[i]), k) for i in range(12)]
        calls.append(('sample_count',))
        model.n_samples = model.sample_count()
        counter = [0]

        def emit_fire(p, bk):
            u = rng.in_unit_sphere()
            vel = [C.add(C.mul(u[0], K_6_589), ZERO), C.add(C.mul(u[1], K_6_589), ZERO),
                   C.add(C.mul(u[2], K_6_589), K_19_74)]
            calls.append(('spawn', bk, 0x870A48, list(p), vel))
            if counter[0] & 0xF == 0:
                calls.append(('spawn', bk, 0x8709F8, list(p), vel))
                p2 = [p[0], p[1], C.add(p[2], K_6)]
                w = rng.in_unit_sphere()
                vel2 = [C.add(vel[i], C.mul(w[i], K_3_5)) for i in range(3)]
                calls.append(('spawn', bk, 0x870A98, p2, vel2))
            counter[0] += 1
        _walk(calls, rng, model, list(s), step, count, back, C.mul(k, K_1_24TH), emit_fire)
    # poison: the motion term compares this frame's matrix with itself (0)
    if item.value(CODE_POISON) != 0:
        d = _motion(calls, m, m, K_30)
        back = C.mul(d, K_0_00291)
        count = C.s32(C.to_int(C.mul(C.mul(C.from_int(C.s32(C.to_int(C.mul(d, K_13_13))) + 0x1A),
                                           amount), K_0_156)))
        k = C.div(ONE, C.from_int(count))
        step = [C.mul(C.sub(m[i], s[i]), k) for i in range(12)]
        calls.append(('sample_count',))
        model.n_samples = model.sample_count()
        _walk(calls, rng, model, list(s), step, count, back, C.mul(k, K_1_24TH),
              lambda p, bk: calls.append(('spawn', bk, 0x870CC8, p, [ZERO, ZERO, ZERO])))
        if swinging:
            _swing_trail(calls, rng, m, s, K_0_667, K_0_206, 0x870D18, K_6_388, True)
    # disease
    if item.value(CODE_DISEASE) != 0:
        d = _motion(calls, m, m, K_30)
        back0 = C.mul(d, K_0_00291)
        count = C.s32(C.to_int(C.mul(C.mul(C.from_int(C.s32(C.to_int(C.mul(d, K_13_13))) + 0x1A),
                                           amount), K_0_578)))
        fcount = C.from_int(count)
        k = C.div(ONE, fcount)
        step = [C.mul(C.sub(m[i], s[i]), k) for i in range(12)]
        calls.append(('sample_count',))
        model.n_samples = model.sample_count()
        back_step = C.mul(k, K_1_24TH)
        mi, _ = _walk(calls, rng, model, list(s), step, count, back0, back_step,
                      lambda p, bk: calls.append(('spawn', bk, 0x870D68, p, [ZERO, ZERO, ZERO])))

        def emit_big(p, bk):
            u = rng.in_unit_sphere()
            calls.append(('spawn', bk, 0x870E08, p, scaled(u, K_3_974)))
        _walk(calls, rng, model, mi, step, C.s32(C.to_int(C.mul(fcount, K_0_074))), back0,
              back_step, emit_big)
        if not swinging:
            state.matrix = list(m)
            return calls
        _swing_trail(calls, rng, m, s, K_0_556, K_0_785, 0x870DB8, K_3_974, True)
    if swinging:
        state.frame = sim_frame & M32
    state.matrix = list(m)
    return calls
