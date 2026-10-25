#!/usr/bin/env python3
"""difftest_lighting.py - compare the round-1 lighting contract (tools/ref_lighting.py)
with the game's own machine code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_lighting.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

Every property prints one line: PASS or FAIL, the name, the number of cases compared and
what was compared.  Exit status 1 when any property fails.

How a property is tested
    The ORIGINAL functions are executed by tools/ee_emu.py on memory this script prepares
    (light nodes it allocates and links with the game's own light_link 0x148af8, the level
    light record at 0x5d3448, the camera matrix 0x44f110, a display-list buffer).  The model
    is given the same inputs.  Integers (colours, radii, chosen nodes, timers, flags) are
    compared exactly; directions, which the model keeps in world space and in Python
    floats, are rotated by the same camera matrix and compared within 1e-4.

Properties
    object light    light_writeVuConstants, light_resetObjectLight, light_addObjectAmbient,
                    light_setObjectAmbient, light_scaleObjectLight in random order: the
                    scaled level colours 0x5d346c-0x5d3473 and the per-object state
                    0x5db370-0x5db393 against LevelLight.scaled / ObjectLight
    collect         light_link + light_collectNear 0x147bf0 on random node sets (layers,
                    the grid edge, the overflow list, more than 31 in reach): the node list
                    in order against collect_near
    model lights    light_emitModelLights 0x149268: the two nodes chosen, their s16 colours,
                    the fill and sun colours, the ambient, and the camera-space directions,
                    against model_lights
    floor tint      light_sampleFloor 0x148ff0: the packed colour against decal_tint
    light chunk     world_runLightChunk 0x18ba18 over runs of frames, modes 0-5, with up to
                    20 chunks competing for the 16 slots: radius, timer, direction bit, slot,
                    node and glow arguments against LightChunk.step / glow_size
    light effect    LightEffect_ctor 0x201bd8 + LightEffect_run 0x1ee050 frame by frame: node
                    colours, radius, falloff, position, deletion frame against LightEffect
    level light     marker constructors 0x158bcc / 0x158c6c / 0x158d0c, the default stores
                    in world_loadRecords 0x14e808, and the load tail 0x1e60e0 against
                    LevelLight.from_markers / base_level
"""
import hashlib
import math
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, M32      # noqa: E402
import ref_lighting as L                  # noqa: E402
import ref_particles as P                 # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
COVER = {}

# ---- addresses in SLUS_209.73 -----------------------------------------------------------
LIGHT_LINK, COLLECT_NEAR, EMIT_MODEL, SAMPLE_FLOOR = 0x148AF8, 0x147BF0, 0x149268, 0x148FF0
WRITE_VU, RESET_OBJ, ADD_AMB, SET_AMB, SCALE_OBJ = 0x148728, 0x148340, 0x148140, 0x14A0C8, 0x148210
RECALC_SUN = 0x148018
RUN_LIGHT_CHUNK, GLOW_ADD, MATH_NOISE = 0x18BA18, 0x18FC78, 0x166B48
LE_CTOR, LE_RUN, GAMEOBJECT_CTOR, RUN_EVERY_FRAME, HANDLE_LINK = (
    0x201BD8, 0x1EE050, 0x14CB10, 0x14F248, 0x1A1738)
SUN_VIS = 0x18B18C
G_GRID, G_OVERFLOW = 0x5D34D8, 0x5DB368
G_SUN_DIR, G_SUN_SCALED, G_AMB_SCALED, G_SUN_SET, G_AMB_SET, G_LEVEL = (
    0x5D3448, 0x5D346C, 0x5D3470, 0x5D3474, 0x5D3478, 0x5D347C)
G_SUN_CAM, G_FILL_CAM = 0x5D34B8, 0x5D34C8
G_OBJ = 0x5DB370                       # ambient, sun, fill (s16 x 4 each), point scale (f32 x 3)
G_PRESELECT, G_PRESEL_A, G_PRESEL_B = 0x4039B0, 0x5DB398, 0x5DB39C
G_LAYER, G_LAYER_ALT, G_SCALE = 0x4039A4, 0x4039A0, 0x4039AC
G_CAMERA, G_WORLD, G_SIM_FRAME, G_DRAW_FRAME, G_SEED = 0x44F110, 0x44FDC8, 0x44FDCC, 0x44FDD0, 0x404460
G_SLOTS, SLOT_SIZE, G_GLOW_TEX = 0x7D3F68, 0x44, 0x7D8A08
VU_PAGE = 0x1100C000


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-14s %7d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:3]:
            print('        ' + line)
    sys.stdout.flush()


def cover(what, count=1):
    if count:
        COVER[what] = COVER.get(what, 0) + count


def scaled(count):
    return max(count // 10, 4) if OPTIONS['quick'] else count


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


class Game:
    def __init__(self, elf):
        e = self.emu = EE(elf)
        e.record_writes = False
        e.record_calls = False
        e.mem.map(VU_PAGE, 0x4000)
        e.mem.map(0x10000000, 0x10000)
        e.stub(SUN_VIS, function=lambda emu: emu.fset(0, 1.0))
        self.glows = []
        e.stub(GLOW_ADD, function=self._glow)
        self.clear_grid()

    def _glow(self, e):
        m = e.mem
        pos = tuple(m.f32(e.r[4] + 4 * i) for i in range(3))
        self.glows.append((e.fget(12), e.fget(13), pos, e.r[5] & 0xFF, e.r[6] & 0xFF,
                           e.r[7] & 0xFF, e.r[8] & 0xFF, e.r[9] & M32, e.r[10] & M32, e.r[11] & M32))

    def clear_grid(self):
        self.emu.mem.write(G_GRID, bytes(90 * 90 * 4))
        self.emu.mem.w32(G_OVERFLOW, 0)

    def call(self, addr, *args, fargs=(), stack=()):
        e = self.emu
        sp = e.r[29] & M32
        for i, v in enumerate(stack):
            e.mem.w32(sp + 8 * i, v & M32)
        return e.call(addr, *args, fargs=fargs)

    def set_level(self, sun_dir, sun_rgba, amb_rgba, level, scale, layer):
        m = self.emu.mem
        for i in range(3):
            m.wf32(G_SUN_DIR + 4 * i, sun_dir[i])
        m.write(G_SUN_SET, bytes(sun_rgba))
        m.write(G_AMB_SET, bytes(amb_rgba))
        m.w32(G_LEVEL, level)
        m.wf32(G_SCALE, scale)
        m.w32(G_LAYER, layer)

    def obj_state(self):
        m = self.emu.mem
        amb = [m.s16(G_OBJ + 2 * i) for i in range(4)]
        sun = [m.s16(G_OBJ + 8 + 2 * i) for i in range(4)]
        fill = [m.s16(G_OBJ + 16 + 2 * i) for i in range(4)]
        ps = [m.f32(G_OBJ + 24 + 4 * i) for i in range(3)]
        return amb, sun, fill, ps

    def new_node(self, n, falloffs, layer, flag9):
        m = self.emu.mem
        a = self.emu.alloc(0x40)
        m.w8(a + 8, layer & 0xFF)
        m.w8(a + 9, flag9)
        for i in range(4):
            m.w16(a + 0xA + 2 * i, (list(n.model_rgb) + [0])[i] & 0xFFFF)
            m.w16(a + 0x12 + 2 * i, (list(n.level_rgb) + [0])[i] & 0xFFFF)
        m.wf32(a + 0x1C, n.model_radius)
        m.wf32(a + 0x20, falloffs[0])
        m.wf32(a + 0x24, n.level_radius)
        m.wf32(a + 0x28, falloffs[1])
        m.wf32(a + 0x2C, n.floor)
        for i in range(3):
            m.wf32(a + 0x30 + 4 * i, n.pos[i])
        self.call(LIGHT_LINK, a)
        return a


def random_level(rng):
    d = [rng.uniform(-1, 1) for _ in range(3)]
    sun = [rng.randint(0, 255) for _ in range(4)]
    amb = [rng.randint(0, 255) for _ in range(4)]
    level = rng.choice([0x80, 0x40, 0x20])
    scale = f32(rng.choice([1.0, rng.uniform(0, 2), 0.5, 1.5]))
    layer = rng.choice([0, 0, 0, 1, 12])
    return d, sun, amb, level, scale, layer


# ---------------------------------------------------------------------------------------

def prop_object_light(elf):
    if not wanted('object light'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 1)
    g = Game(elf)
    m = g.emu.mem
    fails, ex, ops = 0, [], 0
    n = scaled(1500)
    for case in range(n):
        d, sun, amb, level, scale, layer = random_level(rng)
        g.set_level(d, sun, amb, level, scale, layer)
        lv = L.LevelLight(d, sun, amb, level, scale, layer)
        g.call(WRITE_VU)
        obj = lv.object_state()
        model_layer = layer - 10 if layer > 9 else layer
        if model_layer > 9:
            model_layer -= 10
        bad = None
        s_sun, s_amb = lv.scaled()
        got = (tuple(m.read(G_SUN_SCALED, 4)), tuple(m.read(G_AMB_SCALED, 4)))
        if got != (s_sun, s_amb):
            bad = 'scaled %r vs %r' % (got, (s_sun, s_amb))
        for step in range(rng.randint(1, 8)):
            if bad:
                break
            r = rng.random()
            if r < 0.3:
                bias = [rng.randint(-200, 200) for _ in range(4)]
                p = g.emu.alloc(8)
                for i, v in enumerate(bias):
                    m.w16(p + 2 * i, v & 0xFFFF)
                g.call(ADD_AMB, p)
                obj.add_ambient(bias)
            elif r < 0.45:
                rgba = [rng.randint(-50, 300) for _ in range(4)]
                p = g.emu.alloc(8)
                for i, v in enumerate(rgba):
                    m.w16(p + 2 * i, v & 0xFFFF)
                g.call(SET_AMB, p)
                obj.set_ambient(rgba)
            elif r < 0.75:
                k = [f32(rng.choice([1.0, 0.6, rng.uniform(0, 2)])) for _ in range(3)]
                g.call(SCALE_OBJ, fargs=k)
                obj.scale(*k)
            else:
                g.call(RESET_OBJ)
                obj = lv.object_state()
            ops += 1
            amb_o, sun_o, fill_o, ps_o = g.obj_state()
            want = ([int(x) for x in obj.ambient[:4]], [int(x) for x in obj.sun[:3]],
                    [int(x) for x in obj.fill[:3]], [f32(x) for x in obj.point_scale])
            have = (amb_o, sun_o[:3], fill_o[:3], ps_o)
            if have != want:
                bad = 'step %d: original %r model %r' % (step, have, want)
        if bad:
            fails += 1
            ex.append(bad)
    report('object light', fails, n, '%d operations: scaled level colours and the per-object '
           'ambient, sun, fill and point scale, exact' % ops, ex)


def random_nodes(rng, g, count, centre, spread, layers=(0,)):
    nodes, addrs = [], []
    for _ in range(count):
        pos = tuple(f32(c + rng.uniform(-spread, spread)) for c in centre)
        if rng.random() < 0.05:
            pos = (f32(rng.choice([-11600.0, 11530.0, -11520.0, 11519.0])), pos[1], pos[2])
        r = f32(rng.choice([rng.uniform(10, 299), float(rng.randint(1, 299)), rng.uniform(100, 600)]))
        lr = f32(rng.choice([r, rng.uniform(10, 299)]))
        n = L.LightNode(pos, [rng.randint(0, 255) for _ in range(3)], [rng.randint(0, 255) for _ in range(3)],
                        r, lr, f32(rng.choice([0.0, 1.0, rng.uniform(0, 1)])), rng.choice(layers),
                        rng.random() < 0.5)
        fo = (f32(1.0 / (r * r)), f32(1.0 / (lr * lr)))
        n.model_falloff, n.level_falloff = fo
        addrs.append(g.new_node(n, fo, n.layer, 1 if n.tints_decals else 0))
        nodes.append(n)
    return nodes, addrs


def prop_collect(elf):
    if not wanted('collect'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 2)
    g = Game(elf)
    m = g.emu.mem
    fails, ex = 0, []
    n = scaled(800)
    for case in range(n):
        g.clear_grid()
        layer = rng.choice([0, 0, 1])
        m.w32(G_LAYER, layer)
        centre = (rng.uniform(-11000, 11000), rng.uniform(-11000, 11000), rng.uniform(-200, 200))
        nodes, addrs = random_nodes(rng, g, rng.choice([1, 5, 20, 60]), centre,
                                    rng.choice([200, 600, 1200]), layers=(0, 1))
        index = {a: i for i, a in enumerate(addrs)}
        for _ in range(4):
            pos = tuple(f32(c + rng.uniform(-400, 400)) for c in centre)
            p = g.emu.alloc(16)
            out = g.emu.alloc(4 * 33)
            for i in range(3):
                m.wf32(p + 4 * i, pos[i])
            g.call(COLLECT_NEAR, p, out, 32)
            got = []
            for k in range(32):
                a = m.u32(out + 4 * k)
                if not a:
                    break
                got.append(index[a])
            want = [nodes.index(x) for x in L.collect_near(nodes, pos, layer)]
            cover('collect: 31 or more in reach', len(got) >= 31)
            if got != want:
                fails += 1
                ex.append('original %r model %r' % (got, want))
                break
    report('collect', fails, n, 'light_collectNear node list and order (x4 positions per set)', ex)


def rot(mat, v):
    """mat34_rotateVec: v.x row0 + v.y row1 + v.z row2."""
    return tuple(v[0] * mat[0][i] + v[1] * mat[1][i] + v[2] * mat[2][i] for i in range(3))


def random_rotation(rng):
    a, b, c = (rng.uniform(-math.pi, math.pi) for _ in range(3))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    rz = ((ca, sa, 0), (-sa, ca, 0), (0, 0, 1))
    rx = ((1, 0, 0), (0, cb, sb), (0, -sb, cb))
    ry = ((cc, 0, -sc), (0, 1, 0), (sc, 0, cc))

    def mul(p, q):
        return tuple(tuple(sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    return mul(mul(rz, rx), ry)


def prop_model_lights(elf):
    if not wanted('model lights'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 3)
    g = Game(elf)
    m = g.emu.mem
    fails, ex, worst = 0, [], 0.0
    n = scaled(1500)
    for case in range(n):
        g.clear_grid()
        d, sun, amb, level, scale, layer = random_level(rng)
        layer = rng.choice([0, 0, 1])
        g.set_level(d, sun, amb, level, scale, layer)
        cam = random_rotation(rng)
        for r in range(3):
            for c in range(3):
                m.wf32(G_CAMERA + 12 * r + 4 * c, cam[r][c])
        m.w32(G_WORLD, rng.choice([0, 0x700000]))
        m.w32(G_LAYER_ALT, 0)
        lv = L.LevelLight(d, sun, amb, level, scale, layer)
        for i in range(3):                     # stored normalised, as light_setLevelLight does
            m.wf32(G_SUN_DIR + 4 * i, lv.sun_dir[i])
        g.call(WRITE_VU)
        g.call(RECALC_SUN)
        g.call(RESET_OBJ)
        obj = lv.object_state()
        if rng.random() < 0.3:
            k = [f32(rng.uniform(0, 1.5)) for _ in range(3)]
            g.call(SCALE_OBJ, fargs=k)
            obj.scale(*k)
        centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-100, 100))
        nodes, addrs = random_nodes(rng, g, rng.choice([0, 1, 2, 3, 8, 40]), centre, 300, layers=(0, 1))
        pos = tuple(f32(c + rng.uniform(-150, 150)) for c in centre)
        p = g.emu.alloc(16)
        for i in range(3):
            m.wf32(p + 4 * i, pos[i])
        buf = g.emu.alloc(0x100)
        dlp = g.emu.alloc(4)
        m.w32(dlp, buf)
        m.w32(G_PRESELECT, 0)
        g.call(EMIT_MODEL, dlp, p)
        lights, ambient = L.model_lights(pos, nodes, obj, lv)
        # original block: directions qwords 1-3 (x, y, z rows; columns = light0, light1, fill, sun)
        dirs = [tuple(m.f32(buf + 4 + 16 * row + 4 * col) for row in range(3)) for col in range(4)]
        cols = [tuple(m.s16(buf + 0x3C + 8 * k + 2 * i) for i in range(4)) for k in range(5)]
        bad = None
        for k in range(4):
            want_rgb = tuple(lights[k].rgb[:3])
            if cols[k][:3] != want_rgb:
                bad = 'colour %d: %r vs %r' % (k, cols[k], want_rgb)
                break
            if k < 2:
                if lights[k].rgb == (0, 0, 0) and lights[k].direction == (0.0, 0.0, 0.0):
                    wd = (0.0, 0.0, 0.0)
                else:
                    wd = rot(cam, lights[k].direction)
                    wd = (wd[0], wd[1], -wd[2])
                err = max(abs(a - b) for a, b in zip(dirs[k], wd))
                worst = max(worst, err)
                if err > 1e-4:
                    bad = 'direction %d: %r vs %r' % (k, dirs[k], wd)
                    break
        if not bad and cols[4][:4] != tuple(int(x) for x in ambient[:3]) + (cols[4][3],):
            bad = 'ambient %r vs %r' % (cols[4], ambient)
        if not bad:
            fd = rot(cam, lv.fill_dir())
            sd = rot(cam, lv.sun_dir)
            for got, want in ((dirs[2], (fd[0], fd[1], -fd[2])), (dirs[3], (sd[0], sd[1], -sd[2]))):
                err = max(abs(a - b) for a, b in zip(got, want))
                worst = max(worst, err)
                if err > 1e-4:
                    bad = 'fill/sun direction %r vs %r' % (got, want)
        cover('model lights: two point lights', sum(1 for x in lights[:2] if x.rgb != (0, 0, 0)) == 2)
        if bad:
            fails += 1
            ex.append(bad)
    report('model lights', fails, n, 'light_emitModelLights: chosen nodes and s16 colours exact, '
           'ambient exact, camera-space directions within 1e-4 (worst %.2g)' % worst, ex)


def prop_floor_tint(elf):
    if not wanted('floor tint'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 4)
    g = Game(elf)
    m = g.emu.mem
    fails, ex = 0, []
    n = scaled(1500)
    for case in range(n):
        g.clear_grid()
        d, sun, amb, level, scale, layer = random_level(rng)
        layer = rng.choice([0, 0, 1])
        g.set_level(d, sun, amb, level, scale, layer)
        lv = L.LevelLight(d, sun, amb, level, scale, layer)
        # light_setLevelLight normalises the direction; the test writes it as the model holds it
        for i in range(3):
            m.wf32(G_SUN_DIR + 4 * i, lv.sun_dir[i])
        m.w32(G_WORLD, rng.choice([0, 0x700000]))
        centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-100, 100))
        nodes, addrs = random_nodes(rng, g, rng.choice([0, 1, 3, 10]), centre, 250, layers=(0, 1))
        pos = tuple(f32(c + rng.uniform(-150, 150)) for c in centre)
        p = g.emu.alloc(16)
        for i in range(3):
            m.wf32(p + 4 * i, pos[i])
        v = g.call(SAMPLE_FLOOR, p) & M32
        got = (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)
        want = L.decal_tint(pos, nodes, lv)
        if got != tuple(want):
            fails += 1
            ex.append('original %r model %r' % (got, want))
    report('floor tint', fails, n, 'light_sampleFloor packed colour vs decal_tint, exact', ex)


def prop_light_chunk(elf):
    if not wanted('light chunk'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 5)
    fails, ex, calls = 0, [], 0
    n = scaled(150)
    for case in range(n):
        g = Game(elf)
        m = g.emu.mem
        m.w32(G_GLOW_TEX, rng.choice([0, 0x123450]))
        count = rng.choice([1, 4, 16, 20])
        chunks, models, datas = [], [], []
        for k in range(count):
            low, high = rng.randint(0, 400), rng.randint(0, 400)
            mode = rng.choice([0, 1, 2, 3, 4, 5])
            period = rng.choice([0, 1, 5, 30, rng.randint(0, 200)])
            rgba = [rng.randint(0, 0xFFFF) for _ in range(4)]
            data = g.emu.alloc(0x30)
            m.w16(data + 0x10, low)
            m.w16(data + 0x12, high)
            m.w16(data + 0x14, mode)
            m.w16(data + 0x16, period)
            for i in range(4):
                m.w16(data + 0x18 + 2 * i, rgba[i])
            glow = (rng.randint(0, 0xFFFF), rng.randint(0, 6), [rng.randint(0, 255) for _ in range(4)],
                    rng.choice([0, 1]), rng.randint(0, 255))
            m.w16(data + 0x20, glow[0])
            m.w8(data + 0x22, glow[1])
            m.write(data + 0x23, bytes(glow[2]))
            m.w8(data + 0x27, glow[3])
            m.w8(data + 0x28, glow[4])
            ch = g.emu.alloc(0x40)
            m.w32(ch, data)
            pos = [rng.randint(-40000, 40000) for _ in range(3)]     # s32 quarter units
            for i in range(3):
                m.w32(ch + 0x28 + 4 * i, pos[i] & M32)
            chunks.append(ch)
            datas.append(glow)
            lc = L.LightChunk(low, high, mode, period, [x if x < 0x8000 else x - 0x10000 for x in rgba])
            lc.pos = tuple(p * 0.25 for p in pos)
            models.append(lc)
        slots = L.LightSlots()
        frame, draw = rng.randint(0, 1000), rng.randint(1, 1000)
        seed = rng.getrandbits(32)
        m.w32(G_SEED, seed)
        crng = P.CosmeticRng(seed)
        bad = None
        for step in range(rng.choice([30, 120, 400])):
            frame += rng.choice([1, 1, 1, 0, 2])
            draw += 1
            m.w32(G_SIM_FRAME, frame)
            m.w32(G_DRAW_FRAME, draw)
            drawn = [k for k in range(count) if rng.random() < 0.7]
            for k in drawn:
                g.glows.clear()
                g.call(RUN_LIGHT_CHUNK, chunks[k])
                calls += 1
                lc = models[k]
                taken = id(lc) not in slots.slot_of and any(o is not None for o in slots.owner)
                s, node = slots.run(lc, frame, draw, crng.r)
                cover('light chunk: slot taken over', taken and slots.owner.count(None) == 0)
                base = G_SLOTS + SLOT_SIZE * s
                got_r = m.f32(base + 8 + 0x1C)
                want = (lc.timer, lc.down)
                have = (m.s32(chunks[k] + 0x20), bool(m.u32(chunks[k] + 4) & 0x80000000))
                if (m.u32(chunks[k] + 4) & 0x7FFFFFFF) != s + 1:
                    bad = 'slot of chunk %d: %d vs %d' % (k, m.u32(chunks[k] + 4) & 0x7FFFFFFF, s + 1)
                elif have != want:
                    bad = 'timer/direction %r vs %r (mode %d)' % (have, want, lc.mode)
                elif node is not None and got_r != float(lc.radius):
                    bad = 'radius %r vs %r (mode %d)' % (got_r, lc.radius, lc.mode)
                elif node is not None:
                    cm = tuple(m.s16(base + 8 + 0xA + 2 * i) for i in range(4))
                    cl = tuple(m.s16(base + 8 + 0x12 + 2 * i) for i in range(4))
                    if cm != tuple(lc.rgba) or cl != tuple(lc.rgba):
                        bad = 'node colours'
                glow = datas[k]
                expect_glow = glow[3] and m.u32(G_GLOW_TEX)
                if not bad and bool(g.glows) != bool(expect_glow):
                    bad = 'glow drawn %r vs %r' % (bool(g.glows), bool(expect_glow))
                if not bad and g.glows:
                    gb = g.glows[0]
                    noise = None
                    # glow size = base + (trunc(22 noise) << shift): solve for the noise term
                    term = int(gb[1]) - glow[0]
                    shift = glow[1] & 31
                    if term < 0 or term & ((1 << shift) - 1) or (term >> shift) > 21:
                        bad = 'glow size %r for base %d shift %d' % (gb[1], glow[0], shift)
                    elif (gb[0], tuple(gb[3:7]), gb[8:], gb[2]) != (
                            float(glow[4]), tuple(glow[2]), (0, 2), tuple(f32(c) for c in lc.pos)):
                        bad = 'glow arguments %r (bias, rgba, angle/flags, position %r)' % (gb, lc.pos)
                if bad:
                    break
            if bad:
                break
        if not bad and m.u32(G_SEED) != crng.seed:
            bad = 'cosmetic seed'
        if bad:
            fails += 1
            ex.append('case %d: %s' % (case, bad))
    report('light chunk', fails, n, '%d chunk runs (modes 0-5, 16 slots shared by up to 20 chunks): '
           'slot, timer, direction bit, radius, colours, glow arguments and the cosmetic seed, exact'
           % calls, ex)


def prop_light_effect(elf):
    if not wanted('light effect'):
        return
    rng = random.Random(OPTIONS['seed'] * 37 + 6)
    g = Game(elf)
    e, m = g.emu, g.emu.mem
    e.stub(GAMEOBJECT_CTOR, ret=0)
    e.stub(RUN_EVERY_FRAME, ret=0)
    owner_obj = e.alloc(0x40)
    owner_handle = e.alloc(0x20)

    def link(emu):
        emu.mem.w32(emu.r[4] & M32, owner_handle)
    e.stub(HANDLE_LINK, function=link)
    deleted = []
    fake_vt = e.alloc(0x40)
    m.w32(fake_vt + 0xC, 0x00000FF4)
    e.load_words(0xFF0, [0, 0])

    def delete(emu):
        deleted.append(True)
        emu.jump(emu.r[31])
    e.hook(0xFF4, delete)
    fails, ex, frames = 0, [], 0
    n = scaled(600)
    for case in range(n):
        g.clear_grid()
        this = e.alloc(0xC0)
        start = [f32(rng.choice([rng.uniform(-300, 300), float(rng.randint(0, 255))])) for _ in range(4)]
        end = [f32(rng.choice([rng.uniform(-300, 300), float(rng.randint(0, 255)), 0.0])) for _ in range(4)]
        r0 = f32(rng.choice([rng.uniform(1, 400), float(rng.randint(1, 299))]))
        r1 = f32(rng.choice([rng.uniform(1, 400), 0.0, r0]))
        floor = f32(rng.choice([0.0, 1.0, rng.uniform(0, 1)]))
        secs = f32(rng.choice([rng.uniform(0, 2), 0.0, 0.25, 1.0, 0.01]))
        signed = rng.choice([0, 0, 1])
        has_owner = rng.random() < 0.4
        pos = [f32(rng.uniform(-3000, 3000)) for _ in range(3)]
        pp = e.alloc(16)
        for i in range(3):
            m.wf32(pp + 4 * i, pos[i])
        frame = rng.randint(0, 100000)
        m.w32(G_SIM_FRAME, frame)
        m.w32(owner_handle + 0xC, owner_obj if has_owner else 0)
        g.call(LE_CTOR, this, pp, 1 if has_owner else 0, signed,
               fargs=start + end,
               stack=(struct.unpack('<I', struct.pack('<f', r0))[0],
                      struct.unpack('<I', struct.pack('<f', r1))[0],
                      struct.unpack('<I', struct.pack('<f', floor))[0],
                      struct.unpack('<I', struct.pack('<f', secs))[0]))
        m.w32(this + 0x48, fake_vt)
        le = L.LightEffect(start, end, r0, r1, secs, frame, signed=bool(signed), floor=floor, pos=pos)
        bad = None
        for step in range(400):
            frame += 1
            m.w32(G_SIM_FRAME, frame)
            opos = [f32(rng.uniform(-3000, 3000)) for _ in range(3)]
            for i in range(3):
                m.wf32(owner_obj + 0x10 + 4 * i, opos[i])
            deleted.clear()
            g.call(LE_RUN, this)
            frames += 1
            alive, node = le.run(frame, opos if has_owner else None)
            cm = tuple(m.s16(this + 0x56 + 2 * i) for i in range(3))
            rad = m.f32(this + 0x68)
            npos = tuple(m.f32(this + 0x7C + 4 * i) for i in range(3))
            if cm != tuple(node.model_rgb):
                bad = 'step %d colour %r vs %r' % (step, cm, node.model_rgb)
            elif abs(rad - node.model_radius) > 1e-3 * (1 + abs(rad)):
                bad = 'step %d radius %r vs %r' % (step, rad, node.model_radius)
            elif any(abs(a - b) > 1e-3 for a, b in zip(npos, node.pos)):
                bad = 'step %d position %r vs %r' % (step, npos, node.pos)
            elif bool(deleted) == alive:
                bad = 'step %d deleted %r vs alive %r' % (step, bool(deleted), alive)
            if bad or not alive:
                break
        if bad:
            fails += 1
            ex.append('case %d: %s' % (case, bad))
    report('light effect', fails, n, '%d frames: node colours exact, radius and position within '
           '1e-3, deletion frame exact' % frames, ex)


def prop_level_light(elf):
    """The load tail reads the marker block and the flag word.  Colours and the base
    level match from_markers; the stored direction matches within 1e-5."""
    if not wanted('level light'):
        return
    e = EE(elf)
    e.record_writes = False
    e.record_calls = False
    e.stub(RECALC_SUN, ret=0)
    e.stub(RESET_OBJ, ret=0)

    def stub_go(emu):
        obj = emu.r[4] & M32
        src = emu.r[5] & M32
        for i in range(3):
            emu.mem.w32(obj + 0x10 + 4 * i, emu.mem.u32(src + 4 * i))
        return 0

    e.stub(GAMEOBJECT_CTOR, function=stub_go)
    obj = e.alloc(0x80)
    pos = e.alloc(16)
    blob = e.alloc(64)
    e.mem.w16(blob, 0)
    e.mem.w16(blob + 2, 0)
    e.mem.w32(blob + 4, 8)

    def stop(emu):
        emu.jump(emu.RETURN_ADDR)

    e.hook(0x14E8B0, stop)
    e.hook(0x14E9F8, stop)

    def write_defaults():
        e.set_reg('a0', blob)
        e.set_reg('sp', 0x01F02000)
        e.set_reg('ra', e.RETURN_ADDR)
        reason = e.run(0x14E808, max_steps=20000)
        if reason != 'return':
            raise EmuError('default stores stopped: %s at 0x%08x' % (reason, e.pc))

    def apply_markers(ambient, sun, direction):
        write_defaults()
        for ctor, xyz in ((0x158BCC, ambient), (0x158C6C, sun), (0x158D0C, direction)):
            if xyz is None:
                continue
            e.mem.write(pos, struct.pack('<fff', *(f32(c) for c in xyz)))
            e.call(ctor, obj, pos, sp=0x01F02000)

    def run_tail(flags):
        e.mem.w32(0x44FE08, flags & M32)
        e.set_reg('fp', 0x450000)
        e.set_reg('sp', 0x01F01000)
        e.set_reg('ra', e.RETURN_ADDR)
        reason = e.run(0x1E60E0, until=(0x1E615C,), max_steps=8000)
        if reason != 'stop':
            raise EmuError('load tail stopped: %s at 0x%08x' % (reason, e.pc))

    def read_back():
        m = e.mem
        direction = tuple(m.f32(G_SUN_DIR + 4 * i) for i in range(3))
        sun = tuple(m.u8(G_SUN_SET + i) for i in range(4))
        amb = tuple(m.u8(G_AMB_SET + i) for i in range(4))
        return direction, sun, amb, m.u32(G_LEVEL)

    rng = random.Random(OPTIONS['seed'])
    cases = [
        (None, None, None, 0),
        ((20.0, 40.0, 60.0), (80.0, 100.0, 120.0), (0.0, -2.0, 2.0), 0x24000000),
        ((100.0, 60.0, 41.0), (300.0, 200.0, 100.0), (0.0, 0.0, 5.0), 0x20000000),
        ((0.1, 1.0, 41.0), None, None, 0x04000000),
    ]
    for _ in range(scaled(24)):
        def component():
            return f32(rng.uniform(0.0, 400.0))
        direction = tuple(f32(rng.uniform(-2.0, 2.0)) for _ in range(3))
        if direction == (0.0, 0.0, 0.0):
            direction = (0.0, -1.0, 1.0)
        flags = rng.choice([0, 0x04000000, 0x20000000, 0x04000000 | 0x20000000, 0x01000000])
        ambient = tuple(component() for _ in range(3)) if rng.random() < 0.85 else None
        sun = tuple(component() for _ in range(3)) if rng.random() < 0.85 else None
        cases.append((ambient, sun, direction, flags))

    fails, examples = 0, []
    for case, (ambient, sun, direction, flags) in enumerate(cases):
        try:
            apply_markers(ambient, sun, direction)
            m = e.mem
            if ambient is not None:
                got = tuple(m.s32(0x44FDE0 + 4 * i) for i in range(3))
                expect = tuple(L.trunc(c * 0.5) for c in ambient)
                if got != expect:
                    raise EmuError('ambient marker %r vs %r' % (got, expect))
            if direction is not None:
                got = tuple(m.f32(0x44FDE0 + 24 + 4 * i) for i in range(3))
                expect = tuple(f32(c) for c in direction)
                if got != expect:
                    raise EmuError('direction marker %r vs %r' % (got, expect))
            run_tail(flags)
            got_dir, got_sun, got_amb, got_level = read_back()
            model = L.LevelLight.from_markers(ambient, sun, direction, flags)
            bad = None
            if got_level != model.level:
                bad = 'level %r vs %r' % (got_level, model.level)
            elif got_sun != model.sun_set:
                bad = 'sun %r vs %r' % (got_sun, model.sun_set)
            elif got_amb != model.ambient_set:
                bad = 'ambient %r vs %r' % (got_amb, model.ambient_set)
            elif any(abs(a - b) > 1e-5 for a, b in zip(got_dir, model.sun_dir)):
                bad = 'direction %r vs %r' % (got_dir, model.sun_dir)
            if bad:
                fails += 1
                examples.append('case %d: %s' % (case, bad))
        except EmuError as err:
            fails += 1
            examples.append('case %d: %s' % (case, err))
    report('level light', fails, len(cases),
           'constructors, default marker stores and the load tail; colours and base level '
           'exact, direction within 1e-5', examples)


def find_elf(positional):
    for p in positional + [os.path.join(ROOT, 'SLUS_209.73')]:
        if p and os.path.isfile(p):
            return p
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = []
    while argv:
        arg = argv.pop(0)
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg == '--seed':
            OPTIONS['seed'] = int(argv.pop(0), 0)
        elif arg == '-k':
            OPTIONS['filter'] = argv.pop(0)
        else:
            positional.append(arg)
    elf = find_elf(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found (pass its path); nothing was tested')
        return 0
    with open(elf, 'rb') as handle:
        if hashlib.sha256(handle.read()).hexdigest() != EXPECTED_SHA256:
            print('SKIP  %s is not the US v2.00 executable this test was written for' % elf)
            return 0
    started = time.time()
    print('executable %s, seed %d' % (elf, OPTIONS['seed']))
    prop_object_light(elf)
    prop_collect(elf)
    prop_model_lights(elf)
    prop_floor_tint(elf)
    prop_light_chunk(elf)
    prop_light_effect(elf)
    prop_level_light(elf)
    if COVER:
        print('reached: ' + '; '.join('%s %d' % kv for kv in sorted(COVER.items())))
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed, %.0f s' % (len(RESULTS), len(failed), time.time() - started))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
