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
