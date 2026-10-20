#!/usr/bin/env python3
"""ref_lighting.py - reference contract of the lighting of Champions: Return to Arms
(SLUS_209.73, US v2.00): the level light, per-object light state, light nodes and their
grid, the two-best-lights choice for models, the four-lights term for level vertices, the
level light chunks' flicker, the fire objects, LightEffect and the floor-decal tint.

A research tool, not game code.  Written from the code at the addresses in the
docstrings; docs/lighting.md is the prose version and docs/spec/render-pipeline.md
sections 4.6 / 4.7 give the vertex programs this feeds.  Not executed against the
original.  Standard library only; no game data.

    import ref_lighting as L
    level = L.LevelLight.from_markers(ambient_pos=(64, 64, 64), sun_pos=(136, 136, 136),
                                      sun_dir_pos=(0, -1, 1))
    obj = level.object_state()
    torch = L.LightNode.fire(pos=(100, 0, 40), radius=170)
    lights = L.model_lights((100, 50, 0), [torch], obj, level)
    rgb = L.shade_model_vertex((0, -1, 0), lights)

Colours are ints 0..255 in r, g, b order (alpha ignored unless stated); directions are
world-space unit vectors pointing from the lit point towards the light.
"""
import math
import os
import sys
from collections import namedtuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ref_particles import f32, rz          # noqa: E402  (console rounding, toward zero)

FILL_FACTOR = f32(0.79999995)  # light_resetObjectLight 0x148340: 0x3f4ccccc, just below 0.8

GRID_ORIGIN = 11520          # light grid: 90 x 90 cells of 256 (light_link 0x148af8)
GRID_CELLS = 90
COLLECT_REACH = 300          # light_collectNear 0x147bf0 walks cells within +-300
COLLECT_MAX = 31             # out[] of 32 with a 0 terminator
RADIUS_CLAMP = 299           # world_runLightChunk 0x18ba18, AddParticle
FIRE_COLOUR_MODEL = (200, 150, 50)
FIRE_COLOUR_LEVEL = (51, 39, 18)


def trunc(x):
    return int(x)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n > 0.0 else (0.0, 0.0, 0.0)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


# --- level light -------------------------------------------------------------------------

class LevelLight:
    """The record at 0x5d3448 (light_setLevelLight 0x14a2d8)."""

    def __init__(self, sun_dir, sun_rgba, ambient_rgba, level=0x80, scale=1.0, layer=0):
        self.sun_dir = norm(sun_dir)
        self.sun_set = tuple(sun_rgba)
        self.ambient_set = tuple(ambient_rgba)
        self.level = level
        self.scale = scale              # g_lightScale 0x4039ac
        self.layer = layer              # render layer 0x4039a4

    BOOT = None                         # light_init 0x1489c0 values, filled below

    @classmethod
    def from_markers(cls, ambient_pos=None, sun_pos=None, sun_dir_pos=None, level_flags=0):
        """game_loadLevel: marker positions x 0.5 are colours (truncated, I), the third
        marker's position is the direction; defaults when a marker is absent."""
        amb = (0x20, 0x20, 0x20) if ambient_pos is None else tuple(trunc(c * 0.5) for c in ambient_pos)
        sun = (0x44, 0x44, 0x44) if sun_pos is None else tuple(trunc(c * 0.5) for c in sun_pos)
        d = (0.0, -1.0, 1.0) if sun_dir_pos is None else sun_dir_pos
        return cls(d, sun + (0,), amb + (0,), base_level(level_flags))

    def scaled(self):
        """light_writeVuConstants 0x148728: clamp(trunc(scale x as-set), 0, 255); the
        scale is 1 while the render layer is not 0.  The base level is not scaled."""
        k = 1.0 if self.layer != 0 else self.scale
        f = lambda c: tuple(clamp(trunc(k * x), 0, 255) for x in c)
        return f(self.sun_set), f(self.ambient_set)

    def fill_dir(self):
        """light_recalcSun 0x148018: normalize(-sun.x, -sun.y, 0.5 sun.z)."""
        x, y, z = self.sun_dir
        return norm((-x, -y, 0.5 * z))

    def object_state(self):
        """light_resetObjectLight 0x148340."""
        sun, amb = self.scaled()
        # trunc(0.79999995 x as-set): a multiple of 5 gives one less than 0.8 would (round 2)
        fill = tuple(trunc(rz(float(c) * FILL_FACTOR)) for c in self.ambient_set[:3]) + (0,)
        return ObjectLight(list(amb), list(sun), list(fill), [1.0, 1.0, 1.0], self)


def base_level(level_flags):
    """g_worldLightLevel: 0x80, 0x40 with flag 0x04000000, 0x20 with 0x20000000
    (render-pipeline 5.1).  Both flags set yields 0x40: the load tail at 0x1e60e0
    applies 0x04000000 after 0x20000000."""
    if level_flags & 0x04000000:
        return 0x40
    if level_flags & 0x20000000:
        return 0x20
    return 0x80


LevelLight.BOOT = LevelLight((-0.57735, -0.57735, 0.57735), (0x40, 0x46, 0x50, 0), (0x20, 0x20, 0x20, 0))


class ObjectLight:
    """Per-object colours 0x5db370 (ambient), 0x5db378 (sun), 0x5db380 (fill) and the
    point-light scale 0x5db388."""

    def __init__(self, ambient, sun, fill, point_scale, level):
        self.ambient, self.sun, self.fill = ambient, sun, fill
        self.point_scale = point_scale
        self.level = level
        self.sun_dir = level.sun_dir
        self.fill_dir = level.fill_dir()

    def add_ambient(self, bias):
        """light_addObjectAmbient 0x148140: as-set ambient + bias, clamped below at 0."""
        self.ambient = [max(a + b, 0) for a, b in zip(self.level.ambient_set, bias)]

    def set_ambient(self, rgba):
        self.ambient = list(rgba)

    def scale(self, r, g, b):
        """light_scaleObjectLight 0x148210 (truncation per channel)."""
        k = (r, g, b)
        for arr in (self.ambient, self.sun, self.fill):
            for i in range(3):
                arr[i] = trunc(arr[i] * k[i])
        self.point_scale = [r, g, b]

    def hit_flash(self):
        """Creature_draw with object flag 0x100: ambient = (255, 255, 255, 0)."""
        self.set_ambient((255, 255, 255, 0))

    def chill(self, f):
        f = min(f, 1.0)
        if f > 0:
            self.add_ambient((-trunc(f * 100), -trunc(f * 100), trunc(f * 100), trunc(f * 100) >> 1))

    def poison(self, f):
        f = min(f, 1.0)
        if f > 0:
            self.add_ambient((-trunc(f * 100), trunc(f * 100) >> 1, -trunc(f * 100), trunc(f * 100) >> 1))


# --- nodes ----------------------------------------------------------------------------------

class LightNode:
    """A 0x3c-byte light node (docs/lighting.md section 2)."""

    __slots__ = ('pos', 'model_rgb', 'level_rgb', 'model_radius', 'model_falloff',
                 'level_radius', 'level_falloff', 'floor', 'layer', 'tints_decals')

    def __init__(self, pos, model_rgb, level_rgb, model_radius, level_radius=None,
                 floor=0.0, layer=0, tints_decals=False):
        self.pos = tuple(pos)
        self.model_rgb, self.level_rgb = tuple(model_rgb), tuple(level_rgb)
        self.model_radius = float(model_radius)
        self.level_radius = float(model_radius if level_radius is None else level_radius)
        self.model_falloff = 1.0 / (self.model_radius ** 2) if self.model_radius else math.inf
        self.level_falloff = 1.0 / (self.level_radius ** 2) if self.level_radius else math.inf
        self.floor, self.layer, self.tints_decals = floor, layer, tints_decals

    @classmethod
    def fire(cls, pos, radius, level_radius=None):
        """Torch / Candle / Lantern / Lamp node: the fixed fire colours, floor 1, decal
        flag set (0x2b1e80 and the other constructors)."""
        return cls(pos, FIRE_COLOUR_MODEL, FIRE_COLOUR_LEVEL, radius,
                   radius if level_radius is None else level_radius, 1.0, 0, True)


def grid_cell(pos):
    """(cx, cy) of the light grid, or None for the overflow list."""
    cx = (trunc(pos[0]) + GRID_ORIGIN) >> 8
    cy = (trunc(pos[1]) + GRID_ORIGIN) >> 8
    if 0 <= cx < GRID_CELLS and 0 <= cy < GRID_CELLS:
        return cx, cy
    return None


def collect_near(nodes, pos, layer=0):
    """light_collectNear 0x147bf0: grid cells within +-300 of pos, nodes of the layer
    whose cube of half-size model radius contains pos; at most 31, in walk order (cells by
    y then x; within a cell the most recently linked first - here: list order)."""
    x0 = max((trunc(pos[1]) + GRID_ORIGIN - COLLECT_REACH) >> 8, 0)
    x1 = min((trunc(pos[1]) + GRID_ORIGIN + COLLECT_REACH) >> 8, GRID_CELLS - 1)
    y0 = max((trunc(pos[0]) + GRID_ORIGIN - COLLECT_REACH) >> 8, 0)
    y1 = min((trunc(pos[0]) + GRID_ORIGIN + COLLECT_REACH) >> 8, GRID_CELLS - 1)
    by_cell = {}
    for n in nodes:
        c = grid_cell(n.pos)
        if c is not None:
            by_cell.setdefault((c[1], c[0]), []).append(n)
    out = []
    for row in range(x0, x1 + 1):              # the outer index is the y cell
        for col in range(y0, y1 + 1):
            for n in reversed(by_cell.get((row, col), [])):
                r = n.model_radius
                inside = all(n.pos[i] - r <= pos[i] <= n.pos[i] + r for i in range(3))
                if inside and n.layer == layer and len(out) < COLLECT_MAX:
                    out.append(n)
    return out


ModelLight = namedtuple('ModelLight', 'direction rgb')


def model_lights(pos, nodes, obj, level=None, preselected=None):
    """light_emitModelLights 0x149268: [point0, point1, fill, sun] plus the ambient.
    Returns (lights, ambient_rgb).  Directions are world space."""
    if preselected is None:
        cand = collect_near(nodes, pos, obj.level.layer)
        best = []
        for i, n in enumerate(cand):
            d2 = sum((pos[k] - n.pos[k]) ** 2 for k in range(3))
            best.append(((trunc(d2 - n.model_radius ** 2) << 7) | i, i, n))
        best.sort(key=lambda t: t[0])
        chosen = [t[2] for t in best[:2]]
    else:
        chosen = list(preselected)[:2]
    lights = []
    for n in chosen:
        d = tuple(n.pos[k] - pos[k] for k in range(3))
        d2 = dot(d, d)
        w = clamp((n.model_radius ** 2 - d2) * n.model_falloff, 0.0, 1.0)
        rgb = tuple(trunc(n.model_rgb[i] * w * obj.point_scale[i]) for i in range(3))
        lights.append(ModelLight(norm(d), rgb))
    while len(lights) < 2:
        lights.append(ModelLight((0.0, 0.0, 0.0), (0, 0, 0)))
    shade = 1.0                                   # 0x18b18c returns 1.0
    lights.append(ModelLight(obj.fill_dir, tuple(obj.fill[:3])))
    lights.append(ModelLight(obj.sun_dir, tuple(trunc(c * shade) for c in obj.sun[:3])))
    return lights, tuple(obj.ambient[:3])


def shade_model_vertex(normal, lights_and_ambient):
    """The model vertex program (render-pipeline 4.7): min(ambient + sum max(n.L, 0) x
    colour, 255) per channel; the 0.99 factor of the original's cosine is kept."""
    lights, ambient = lights_and_ambient
    n = norm(normal)
    out = []
    for ch in range(3):
        v = ambient[ch]
        for lt in lights:
            v += max(dot(n, lt.direction) * 0.99, 0.0) * lt.rgb[ch]
        out.append(min(trunc(v), 255))
    return tuple(out)


def shade_level_vertex(base, nodes, vpos, normal):
    """The level vertex program for up to four nodes (render-pipeline 4.6), world units:
    a = max(1 - D^2/R^2 ... ) written with the node's level radius and falloff; floor >= 1
    = non-directional.  normal is a unit vector.  Returns (r, g, b) before the 255 clamp
    wrap rules (clamped here)."""
    n = norm(normal)
    lit = any(sum((nd.pos[k] - vpos[k]) ** 2 for k in range(3)) < nd.level_radius ** 2 and nd.floor < 1
              for nd in nodes)
    acc = [float(base)] * 3
    for nd in nodes[:4]:
        d = tuple(nd.pos[k] - vpos[k] for k in range(3))
        d2 = dot(d, d)
        a = max((nd.level_radius ** 2 - d2) * nd.level_falloff, 0.0)
        if lit:
            dl = math.sqrt(d2) or 1.0
            a *= clamp(dot(d, n) / dl * 0.99, nd.floor, 1.0)
        a = min(a, 1.0)
        for ch in range(3):
            acc[ch] += a * nd.level_rgb[ch]
    return tuple(min(trunc(c), 255) for c in acc)


# --- level light chunks ------------------------------------------------------------------------

class LightChunk:
    """A 0x30-byte light chunk record and its run-time state (chunk +0x20 timer, +4 bit 31
    direction, the slot's radius)."""

    def __init__(self, low, high, mode, period, rgba, glow=None):
        self.low, self.high, self.mode, self.period = low, high, mode, period
        self.rgba = tuple(rgba)
        self.glow = glow
        self.timer = 0
        self.down = False
        self.radius = 0

    def step(self, sim_frame, rnd=None):
        """world_runLightChunk 0x18ba18, one call (a drawn frame).  rnd() -> [0, 1) is the
        cosmetic draw of mode 1.  Returns the LightNode, or None for mode 4 (off)."""
        r = self.radius
        m = self.mode
        if m == 0:
            r = self.low
        elif m == 1:
            if sim_frame > self.timer:
                self.timer = sim_frame + self.period
                r = self.low + trunc((self.high - self.low) * rnd())
        elif m == 2:
            if sim_frame > self.timer:
                self.timer = sim_frame + self.period
                if self.down:
                    r, self.down = self.low, False
                else:
                    r, self.down = self.high, True
            if self.period:
                step = trunc((self.high - self.low) / self.period)
                r += -step if self.down else step
        elif m == 3:
            if sim_frame > self.timer:
                self.timer = sim_frame + self.period
                r = self.high if r == self.low else self.low
        if m == 4:
            return None
        r = clamp(r, 0, RADIUS_CLAMP)
        self.radius = r
        return LightNode((0, 0, 0), self.rgba[:3], self.rgba[:3], r, r, 0.0, 0, False)


class LightSlots:
    """The 16 light slots of the level light chunks (0x7d3f68, 0x44 bytes each: draw stamp,
    owner chunk, node) and world_claimLightSlot 0x18b93c.  A chunk keeps its slot while it is
    drawn; otherwise it takes the slot with the oldest draw stamp (the first such, scanning
    0..15, among stamps below the current g_drawFrame; slot 0 when none is older) and the
    previous owner loses it.  The radius a mode keeps "unchanged" is the SLOT's, so a chunk
    that takes over a slot starts from the previous owner's radius (round 2: executed)."""

    def __init__(self):
        self.owner = [None] * 16
        self.stamp = [0] * 16
        self.radius = [0] * 16
        self.slot_of = {}

    def claim(self, chunk, draw_frame):
        s = self.slot_of.get(id(chunk))
        if s is None:
            s, oldest = 0, draw_frame
            for i in range(16):
                if self.stamp[i] < oldest:
                    s, oldest = i, self.stamp[i]
            prev = self.owner[s]
            if prev is not None:
                self.slot_of.pop(id(prev), None)
            self.owner[s] = chunk
            self.slot_of[id(chunk)] = s
        self.stamp[s] = draw_frame
        return s

    def run(self, chunk, sim_frame, draw_frame, rnd=None):
        """world_runLightChunk for one drawn chunk: -> (slot, LightNode or None)."""
        s = self.claim(chunk, draw_frame)
        chunk.radius = self.radius[s]
        node = chunk.step(sim_frame, rnd)
        if node is not None:
            self.radius[s] = chunk.radius
        return s, node


def glow_size(base, shift, noise):
    """Light chunk glow size: +0x20 + (trunc(22 x noise) << shift)."""
    return base + (trunc(noise * 22.0) << (shift & 31))


# --- fire objects and LightEffect -----------------------------------------------------------------

FIRE_RADIUS_BASE = {'torch': 160, 'lantern': 160, 'lamp': 216}


def fire_radius(kind, noise):
    """Torch_run 0x2b2088, Lantern_run 0x2b3554, Lamp_run 0x2b3858: base + trunc(22 noise)."""
    return FIRE_RADIUS_BASE[kind] + trunc(noise * 22.0)


def candle_radius(rand16, big=False):
    """Candle_run 0x2b2dc4, every 5 ticks: 48 (or 84) + ((rand - 8) & 15)."""
    return (84 if big else 48) + ((rand16 - 8) & 15)


def lantern_level_radius(radius, level_name):
    """Lantern_run: the level-geometry radius is 0 in levels whose name contains 'mine'."""
    return 0 if 'mine' in level_name else radius


class LightEffect:
    """LightEffect_ctor 0x201bd8 / LightEffect_run 0x1ee050."""

    def __init__(self, start_rgba, end_rgba, radius0, radius1, seconds, now, signed=False,
                 floor=0.0, pos=(0.0, 0.0, 0.0)):
        # single-precision work rounded toward zero, as the console does it (round 2)
        self.life = max(1, trunc(rz(f32(seconds) * 60.0)))
        self.end = now + self.life
        inv = rz(1.0 / self.life)
        self.c = [f32(x) for x in start_rgba]
        self.rate = [rz(rz(f32(e) - f32(s)) * inv) for s, e in zip(start_rgba, end_rgba)]
        self.radius = f32(radius0)
        self.rrate = rz(rz(f32(radius1) - f32(radius0)) * inv)
        self.signed, self.floor, self.pos = signed, floor, tuple(pos)

    def run(self, sim_frame, owner_pos=None):
        """One run call; returns (alive, LightNode)."""
        self.c = [rz(c + r) for c, r in zip(self.c, self.rate)]
        self.radius = rz(self.radius + self.rrate)
        lo = -255.0 if self.signed else 0.0
        # the accumulators are clamped but keep their fractions (round 2: executed)
        self.c[:3] = [clamp(c, lo, 255.0) for c in self.c[:3]]
        if owner_pos is not None:
            self.pos = (f32(owner_pos[0]), f32(owner_pos[1]), rz(f32(owner_pos[2]) + 36.0))
        rgb = tuple(trunc(c) for c in self.c[:3])
        node = LightNode(self.pos, rgb, rgb, self.radius, self.radius, self.floor, 0, False)
        return sim_frame < self.end, node


# --- decal tint ----------------------------------------------------------------------------------

def decal_tint(pos, nodes, level):
    """0x148ff0: the colour a floor decal is given when it is made (r, g, b)."""
    c = [0.0, 0.0, 0.0]
    for n in collect_near(nodes, pos, level.layer):
        if not n.tints_decals:
            continue
        d = tuple(n.pos[k] - pos[k] for k in range(3))
        d2 = dot(d, d)
        if d2 <= 0.0:
            continue
        w = (n.model_radius ** 2 - d2) * n.model_falloff * d[2] / math.sqrt(d2)
        w = clamp(w, 0.0, 1.0)
        for ch in range(3):
            c[ch] += n.model_rgb[ch] * w
    s = max(level.sun_dir[2] * 1.0, 0.0)
    return tuple(clamp(trunc(c[ch] + level.sun_set[ch] * s + level.ambient_set[ch]), 0, 255)
                 for ch in range(3))
