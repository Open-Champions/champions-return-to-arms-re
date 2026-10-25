#!/usr/bin/env python3
"""ref_fx_props.py - reference contract of the fire props of Champions: Return to Arms
(SLUS_209.73, US v2.00): what Torch_run 0x2b2088, Candle_run 0x2b2dc4, Candle2_run
0x2b3164 (factory name Candle3), Lantern_run 0x2b3554 and Lamp_run 0x2b3858 do each tick -
the particles they spawn (definition, back-date, position, velocity), their light node
(radius, falloff, position) and the "not drawn lately" counter that takes them off the
run list.

A research tool, not game code.  Round 2 (2026-10-18): compared with the original,
executed in tools/ee_emu.py, by tools/difftest_fx_props.py, bit for bit (floats are raw
32-bit patterns through tools/ref_core.py).  docs/lighting.md section 3.2 and
docs/effects.md are the prose versions.  Standard library only; no game data.  The
particle definitions are named by address only; their values come from the user's
executable (tools/fx_particle_defs.py).

Randomness: every draw comes from the object's own generator (GameObject_rand 0x1509d0,
state at object +0x44, ref_core.Lcg).  The light flicker uses math_noise over
g_noiseTable, which is built per machine at boot (cosmetic): pass the table.

    import ref_fx_props as F, ref_core as C
    t = F.FireProp(F.TORCH, addr=0x01234560, pos=(100.0, 50.0, 0.0), seed=0x1234, kind=2)
    out = F.torch_run(t, sim_frame=96, table=[0] * 256)
    for s in out.spawns: print(hex(s.definition), s.position, s.velocity)
"""
import os
import sys
from collections import namedtuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                       # noqa: E402

TORCH, CANDLE, CANDLE3, LANTERN, LAMP = 'torch', 'candle', 'candle3', 'lantern', 'lamp'

# particle definitions (addresses; values are read from the executable at run time)
DEF_TORCH_FLAME, DEF_TORCH_SMOKE, DEF_TORCH_SPARK = 0x8E4740, 0x8E47E0, 0x8E4830
DEF_CANDLE, DEF_CANDLE3, DEF_LAMP = 0x8E4880, 0x8E48D0, 0x8E4920

# the single-precision constants of the code, as bit patterns
K_INV65536 = 0x37800000          # 1.5258789e-05
K_FLAME_LIFT = 0x40999999        # 4.7999997 (velocity z of a flame)
K_SMOKE = 0x41A00000             # 20.0
K_SPARK = 0x41F2E147             # 30.359999
K_SPARK_LIFT = 0x414A6666        # 12.65
K_LAMP = 0x403624DD              # 2.846
K_CANDLE_RISE = 0x3E999999       # 0.29999998
K_CANDLE_LIFT = 0x40600000       # 3.5
NOISE_A = 0x19660D
NOISE_B = 0x7EFE41
NOISE_Z = 0x32CC1A
STOP_AFTER = 31                  # run calls without a draw before obj_stopRunning

Spawn = namedtuple('Spawn', 'backdate definition position velocity')
Tick = namedtuple('Tick', 'spawns stopped')

_TORCH_COUNT = {2: 3, 4: 4, 5: 3}
_TORCH_SPREAD = {2: (10.0, 5.0, None), 3: (5.0, 10.0, None), 4: (15.0, 10.0, None),
                 5: (10.0, 5.0, None), 1: (10.0, None, None)}


def _k(x):
    return C.f32(x)


class FireProp:
    """The fields the run functions read and write.  Positions and radii are float
    patterns; `addr` is the object's address (it feeds the noise index); `seed` the state
    of the object's generator (+0x44)."""

    def __init__(self, cls, addr, pos, seed, kind=0, big=False, level_name=''):
        self.cls, self.addr = cls, addr & 0xFFFFFFFF
        self.pos = [p if isinstance(p, int) else C.f32(p) for p in pos]
        self.rng = C.Lcg(seed)
        self.kind = kind & 0xFF                # Torch +0x8a: 0-5 (Torch, Fire, Campfire, ...)
        self.big = big                         # Candle +0x90 == 1
        self.level_name = level_name           # Lantern: g_levelName 0x41b721
        self.model_radius = self.level_radius = C.f32(240.0)
        self.model_falloff = self.level_falloff = 0x3791A2B3     # 1 / 240^2 as the ctors store it
        self.light_pos = list(self.pos)
        self.counter = 0                       # candle: ticks since the last radius change
        self.undrawn = 0                       # +0x89 (+0x8d candle, +0x95 lantern, +0x4d candle3)
        self.running = True


def _signed_unit(rng):
    return rng.signed_unit()


def _sphere(rng):
    return rng.in_unit_sphere()


def _undrawn_s8(p):
    """The s8 counter: obj_stopRunning when it is 31 or more (as signed), then +1."""
    v = p.undrawn - 0x100 if p.undrawn & 0x80 else p.undrawn
    stopped = v >= STOP_AFTER
    if stopped:
        p.running = False
    p.undrawn = (p.undrawn + 1) & 0xFF
    return stopped


def _set_radius(p, value_pattern, level_too=True):
    p.model_radius = value_pattern
    p.level_radius = value_pattern
    inv = C.div(C.ONE, C.mul(value_pattern, value_pattern))
    p.model_falloff = p.level_falloff = inv


def _flicker_radius(p, sim_frame, table, base):
    n = C.noise(table, C.s32(p.addr * NOISE_A + sim_frame * 16 + NOISE_B))
    return C.from_int(C.to_int(C.mul(n, _k(22.0))) + base)


def torch_run(p, sim_frame, table):
    """Torch_run 0x2b2088 (Torch, Fire, Campfire, Firepot, Firepot2, OilLamp = kind 0-5)."""
    rng, spawns = p.rng, []
    kind = p.kind
    count = _TORCH_COUNT.get(kind, 1)
    for _ in range(count):
        v = _sphere(rng)
        vel = [C.add(v[0], v[0]), C.add(v[1], v[1]), C.add(C.add(v[2], v[2]), K_FLAME_LIFT)]
        u = _sphere(rng)
        x, y, z = u
        if kind in (2, 5):
            x, y, z = C.mul(x, _k(10.0)), C.mul(y, _k(10.0)), C.add(z, _k(5.0))
        elif kind == 3:
            x, y, z = C.mul(x, _k(5.0)), C.mul(y, _k(5.0)), C.add(z, _k(10.0))
        elif kind == 4:
            x, y, z = C.mul(x, _k(15.0)), C.mul(y, _k(15.0)), C.add(z, _k(10.0))
        elif kind == 1:
            x, y = C.mul(x, _k(10.0)), C.mul(y, _k(10.0))
        else:
            x, y, z = C.mul(x, _k(4.0)), C.mul(y, _k(4.0)), C.mul(z, _k(4.0))
        z = C.fabs(z) if C.lt(z, 0) else z
        pos = [C.add(x, p.pos[0]), C.add(y, p.pos[1]), C.sub(C.add(z, p.pos[2]), _k(12.0))]
        back = _k(0.25) if kind == 3 else 0
        spawns.append(Spawn(back, DEF_TORCH_FLAME, pos, list(vel)))
        if sim_frame & 7 == 0 and ((kind - 4) & 0xFFFFFFFF) > 1:
            r = rng.draw()
            vel[2] = C.add(vel[2], C.mul(C.mul(C.from_int(r), K_INV65536), K_SMOKE))
            w = _sphere(rng)
            sx, sy, sz = (C.mul(c, _k(10.0)) for c in w)
            sz = C.fabs(sz) if C.lt(sz, 0) else sz
            spawns.append(Spawn(0, DEF_TORCH_SMOKE, [C.add(sx, p.pos[0]), C.add(sy, p.pos[1]),
                                                     C.add(sz, p.pos[2])], list(vel)))
    base = C.s32(p.addr * NOISE_A)
    _set_radius(p, _flicker_radius(p, sim_frame, table, 160))
    eight = _k(8.0)
    p.light_pos = [
        C.add(p.pos[0], C.mul(C.noise(table, C.s32(sim_frame * 2 + base)), eight)),
        C.add(p.pos[1], C.mul(C.noise(table, C.s32(base + sim_frame * 2 + NOISE_A)), eight)),
        C.add(p.pos[2], C.mul(C.noise(table, C.s32(NOISE_Z + base + sim_frame * 2)), eight))]
    if kind != 0 and kind != 4:
        if rng.draw() <= 0x319:
            w = _sphere(rng)
            vel = [C.mul(w[0], K_SPARK), C.mul(w[1], K_SPARK), C.add(C.mul(w[2], K_SPARK), K_SPARK_LIFT)]
            spawns.append(Spawn(0, DEF_TORCH_SPARK, list(p.pos), vel))
    return Tick(spawns, _undrawn_s8(p))


def _candle_particle(rng):
    v = _sphere(rng)
    vel = [0, 0, C.add(C.mul(v[2], K_CANDLE_RISE), K_CANDLE_LIFT)]
    u = _sphere(rng)
    return vel, u


def candle_run(p, sim_frame=0, table=None):
    """Candle_run 0x2b2dc4 (factory names Candle, Candle2; big = constructor argument 1)."""
    rng = p.rng
    vel, u = _candle_particle(rng)
    z = C.fabs(u[2]) if C.lt(u[2], 0) else u[2]
    if p.big:
        z = C.add(C.add(z, p.pos[2]), _k(8.0))
    else:
        z = C.sub(C.add(z, p.pos[2]), _k(4.0))
    spawns = [Spawn(0, DEF_CANDLE, [p.pos[0], p.pos[1], z], vel)]
    p.counter += 1
    if p.counter == 5:
        p.counter = 0
        r = rng.draw()
        _set_radius(p, C.from_int(((r - 8) & 0xF) + (0x54 if p.big else 0x30)))
    return Tick(spawns, _undrawn_s8(p))


def candle3_run(p, sim_frame=0, table=None):
    """Candle2_run 0x2b3164 (factory name Candle3): no light, one particle a tick."""
    rng = p.rng
    vel, u = _candle_particle(rng)
    z = C.add(u[2], u[2])
    z = C.fabs(z) if C.lt(z, 0) else z
    z = C.add(C.add(z, p.pos[2]), _k(5.0))
    return Tick([Spawn(0, DEF_CANDLE3, [p.pos[0], p.pos[1], z], vel)], _undrawn_s8(p))


def lantern_run(p, sim_frame, table):
    """Lantern_run 0x2b3554: flicker radius 160 + trunc(22 noise); the level radius is 0
    when the level name contains 'mine'.  No particles."""
    _set_radius(p, _flicker_radius(p, sim_frame, table, 160))
    if 'mine' in p.level_name:
        p.level_radius = 0
    return Tick([], _undrawn_s8(p))


def lamp_run(p, sim_frame, table):
    """Lamp_run 0x2b3858: radius 216 + trunc(22 noise); two particles a tick at the object,
    speed 2.846 in a direction from the unit ball."""
    _set_radius(p, _flicker_radius(p, sim_frame, table, 216))
    spawns = []
    for _ in range(2):
        w = _sphere(p.rng)
        inv = C.div(C.ONE, C.sqrt(C.add(C.add(C.mul(w[0], w[0]), C.mul(w[1], w[1])), C.mul(w[2], w[2]))))
        spawns.append(Spawn(0, DEF_LAMP, list(p.pos), [C.mul(C.mul(c, inv), K_LAMP) for c in w]))
    return Tick(spawns, _undrawn_s8(p))


RUN = {TORCH: torch_run, CANDLE: candle_run, CANDLE3: candle3_run, LANTERN: lantern_run, LAMP: lamp_run}
