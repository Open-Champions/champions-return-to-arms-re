#!/usr/bin/env python3
"""difftest_levels_r3.py - round 3 of tools/ref_levels.py against the original code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.
Synthetic cases build their own worlds.  The disc property runs only when you pass
--disc DIR (the directory of paired level archives) or set RTA_DISC.  It prints
counts only.  --notes PATH writes per-level detail, and only under this repo's local/.

  python3 tools/difftest_levels_r3.py [SLUS_209.73] [--disc DIR] [--notes PATH]
                                      [--quick] [--seed N] [-k TEXT] [-v]

Properties (docs/level-flow.md section 17):

  placement_glue   0x3211c8-0x321238 with terrain_height stubbed: f12 is 12.0, xy stays,
                   z is the returned word
  player_radius    0x1a2220-0x1a2264: object +0x1c becomes 12.0
  player_snap      the same radius through the real terrain_height, on a floor above 12
                   and on a sample radius 4 misses; Player_ctor's snap 0x1a2420-0x1a2460
                   reads +0x1c
  free_spot        world_findFreeSpot 0x14acf8: a floor 6 or more above the centre fails
                   and the centre is kept; a floor under 6 is taken; a miss (the sentinel)
                   passes the height test
  arena_initial    arena_pickSpawnPoint 0x3050a4 with a nonzero first argument: ring
                   around table entry 0, spread 36 then 240, facing
  spawn_real       the geometry-ok levels whose origin fails terrain_heightBelow(radius 4,
                   z = 0): the story slot's terrain_height(radius 12) is a floor, the
                   placement loop keeps xy, and findFreeSpot then that snap stays on a floor
"""
import glob
import hashlib
import json
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE                               # noqa: E402
import ref_core as C                                # noqa: E402
import ref_levels as L                              # noqa: E402
import ref_objects as Obj                           # noqa: E402
import ref_world as W                               # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF

A_FIXUP = 0x181D30
A_HEIGHT = 0x183820
A_HEIGHT_BELOW = 0x1834A8
A_HEIGHT_POINT = 0x182F28
A_FREE = 0x14ACF8
A_COLLECT = 0x14A928
A_PLACE_LO, A_PLACE_HI = 0x3211C8, 0x321238
A_RADIUS_LO, A_RADIUS_HI = 0x1A2220, 0x1A2264
A_SNAP_LO, A_SNAP_HI = 0x1A2420, 0x1A2460
A_RECALC = 0x1B6458
A_ARENA = 0x3050A4
A_NET_COUNT = 0x1EC878
G_WORLD = 0x44FDC8
G_NUM_PLAYERS = 0x4D8AE0
G_SPAWN = 0x4F70D0
G_SEED = 0x404464
G_MODE_A = 0x4F711C
G_FACING_WORD = 0x4F7124
G_TABLE_PTR = 0x503888
WORLD_BASE = 0x03000000
SP = 0x01F80000

OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False,
           'disc': None, 'notes': None}
RESULTS = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def report(name, cases, failures, what):
    ok = not failures
    RESULTS.append(ok)
    print('%s %-16s %6d cases  %s' % ('PASS' if ok else 'FAIL', name, cases, what))
    if failures and OPTIONS['verbose']:
        for f in failures[:8]:
            print('     ', f)


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'] in name


def f32(value):
    return W.f32(value)


class Rig:
    def __init__(self, elf):
        self.emu = EE(elf)
        self.emu.record_calls = False
        self.emu.record_writes = False
        self.emu.fpu_model = 'ps2'
        W.set_fpu('ps2')
        C.set_fpu('ps2')
        self.world_span = 0
        self.base = None

    def hooks_clear(self):
        self.emu.hooks.clear()
        self.emu.stub_names.clear()
        self.emu.follow = None

    def fixup_stubs(self):
        emu = self.emu
        for addr in (0x3B7EF0, 0x14A4F0, 0x195318, 0x18F118, 0x179E10, 0x168894):
            emu.stub(addr, ret=0)
        emu.stub(0x172AD0, function=lambda e: e.mem.write(e.r[5] & M32, bytes(0x40)) or 0)

    def load(self, data):
        """Copy a .world and run world_fixup.  Returns the interpreter address."""
        emu = self.emu
        span = max(len(data) + 0x1000, self.world_span)
        emu.mem.map(WORLD_BASE, span)
        emu.mem.write(WORLD_BASE, bytes(span))
        emu.mem.write(WORLD_BASE, data)
        self.world_span = span
        self.emu._heap = self.emu.HEAP_LO
        self.hooks_clear()
        self.fixup_stubs()
        emu.call(A_FIXUP, WORLD_BASE, max_steps=200000000)
        self.hooks_clear()
        emu.mem.w32(G_WORLD, WORLD_BASE)
        self.base = WORLD_BASE
        return WORLD_BASE

    def call_height(self, addr, radius, pos):
        buf = self.emu.alloc(16)
        for i, word in enumerate(pos):
            self.emu.mem.w32(buf + 4 * i, word)
        self.emu.f[12] = radius & M32
        self.emu.call(addr, self.base, buf, max_steps=20000000)
        return self.emu.f[0]

    def run_to(self, start, stop, max_steps=20000000):
        emu = self.emu
        emu.r[31] = emu.RETURN_ADDR
        emu.r[29] = SP
        reason = emu.run(start, until=(stop,), max_steps=max_steps)
        return reason, emu.pc

    def empty_objects(self):
        def collect(emu):
            emu.mem.w32(emu.r[6] & M32, 0)
            return emu.r[6] & M32
        self.emu.stub(A_COLLECT, ret=None, function=collect)

    def find_free(self, centre, spread, radius, any_height, seed):
        emu = self.emu
        self.empty_objects()
        emu.mem.w32(G_SEED, seed & M32)
        out, cen, okb = emu.alloc(16), emu.alloc(16), emu.alloc(4)
        for i, word in enumerate(centre):
            emu.mem.w32(cen + 4 * i, word)
        emu.mem.w8(okb, 0x5A)
        emu.call(A_FREE, out, cen, spread, radius, okb, 1 if any_height else 0,
                 max_steps=200000000)
        pos = tuple(emu.mem.u32(out + 4 * i) for i in range(3))
        ok = emu.mem.u8(okb)
        self.hooks_clear()
        return pos, ok


def flat_world(x0, y0, w, h, sample_height, element_z=0, element_xy=(0, 0)):
    samples = [sample_height * 16] * (w * h)
    data = W.build_world_file((-2, -2), (8, 8), [(x0, y0, w, h, samples)],
                              [(0, 0, element_xy[0], element_xy[1], element_z, 32767, 0)])
    return data, W.Level(data)


def prop_placement_glue(rig):
    emu = rig.emu
    fails = []
    cases = 0
    for n, words in ((1, (0x3F800000,)), (3, (0x3F800000, 0x40000000, 0x40400000))):
        cases += 1
        rig.hooks_clear()
        seen = []

        def stub(e, words=words, seen=seen):
            seen.append(e.f[12])
            e.f[0] = words[len(seen) - 1]
            return None

        emu.stub(A_HEIGHT, ret=None, function=stub)
        emu.mem.w32(G_NUM_PLAYERS, n)
        xy = []
        for i in range(n):
            x, y = f32(float(i * 3 + 1)), f32(float(i * 3 + 2))
            xy.append((x, y))
            emu.mem.w32(G_SPAWN + i * 12, x)
            emu.mem.w32(G_SPAWN + i * 12 + 4, y)
            emu.mem.w32(G_SPAWN + i * 12 + 8, 0x7FC00000)
        reason, pc = rig.run_to(A_PLACE_LO, A_PLACE_HI, max_steps=20000)
        if reason != 'stop' or seen != [L.PLACEMENT_RADIUS] * n:
            fails.append('n=%d stop %s f12 %s' % (n, reason, seen))
            continue
        for i, (x, y) in enumerate(xy):
            got = (emu.mem.u32(G_SPAWN + i * 12), emu.mem.u32(G_SPAWN + i * 12 + 4),
                   emu.mem.u32(G_SPAWN + i * 12 + 8))
            if got != (x, y, words[i]):
                fails.append('n=%d slot %d' % (n, i))
    rig.hooks_clear()
    report('placement_glue', cases, fails, 'f12 is 12.0, xy stays, z is the height word')


def prop_player_radius(rig):
    emu = rig.emu
    rig.hooks_clear()
    obj = emu.alloc(0x100)
    emu.mem.write(obj, bytes(0x100))
    emu.mem.w32(obj + 0x1C, 0xDEADBEEF)
    emu.set_reg('s5', obj)
    reason, pc = rig.run_to(A_RADIUS_LO, A_RADIUS_HI, max_steps=20000)
    got = emu.mem.u32(obj + 0x1C)
    fails = [] if reason == 'stop' and got == L.PLACEMENT_RADIUS else [
        'stop %s at %08x radius %08x' % (reason, pc, got)]
    report('player_radius', 1, fails, 'object +0x1c becomes 12.0')


def prop_player_snap(rig):
    """Real terrain_height: a floor above 12, and a sample only radius 12 reaches."""
    fails = []
    high_data, high = flat_world(-40, -40, 80, 80, 0, element_z=20)
    far_data, far = flat_world(2, 0, 4, 2, 30)
    origin = (0, 0, 0)
    rig.load(high_data)
    below = rig.call_height(A_HEIGHT_BELOW, f32(4.0), origin)
    at = rig.call_height(A_HEIGHT, f32(4.0), origin)
    top = rig.call_height(A_HEIGHT, L.PLACEMENT_RADIUS, origin)
    if below != W.NO_FLOOR or at != f32(20.0) or top != f32(20.0):
        fails.append('high floor below/r4/r12')
    emu = rig.emu
    emu.mem.w32(G_NUM_PLAYERS, 1)
    emu.mem.w32(G_SPAWN, f32(3.0))
    emu.mem.w32(G_SPAWN + 4, f32(-4.0))
    emu.mem.w32(G_SPAWN + 8, 0)
    reason, _pc = rig.run_to(A_PLACE_LO, A_PLACE_HI)
    placed = (emu.mem.u32(G_SPAWN), emu.mem.u32(G_SPAWN + 4), emu.mem.u32(G_SPAWN + 8))
    want = W.terrain_height(high, L.PLACEMENT_RADIUS, (f32(3.0), f32(-4.0), 0))
    if reason != 'stop' or placed != (f32(3.0), f32(-4.0), want) or want == W.NO_FLOOR:
        fails.append('placement on the high floor')
    obj = emu.alloc(0x80)
    emu.mem.write(obj, bytes(0x80))
    emu.mem.w32(obj + 0x10, placed[0])
    emu.mem.w32(obj + 0x14, placed[1])
    emu.mem.w32(obj + 0x18, 0)
    emu.mem.w32(obj + 0x1C, L.PLACEMENT_RADIUS)
    emu.set_reg('s5', obj)
    emu.stub(A_RECALC, ret=0)
    reason, _pc = rig.run_to(A_SNAP_LO, A_SNAP_HI)
    if reason != 'stop' or emu.mem.u32(obj + 0x18) != want:
        fails.append('Player_ctor snap')
    rig.hooks_clear()

    rig.load(far_data)
    r4 = rig.call_height(A_HEIGHT, f32(4.0), origin)
    r12 = rig.call_height(A_HEIGHT, L.PLACEMENT_RADIUS, origin)
    model4 = W.terrain_height(far, f32(4.0), origin)
    model12 = W.terrain_height(far, L.PLACEMENT_RADIUS, origin)
    if (r4, r12) != (model4, model12) or r4 != W.NO_FLOOR or r12 == W.NO_FLOOR:
        fails.append('sample between radius 4 and 12')
    emu.mem.write(obj, bytes(0x80))
    emu.mem.w32(obj + 0x1C, f32(4.0))
    emu.set_reg('s5', obj)
    emu.stub(A_RECALC, ret=0)
    reason, _pc = rig.run_to(A_SNAP_LO, A_SNAP_HI)
    if reason != 'stop' or emu.mem.u32(obj + 0x18) != W.NO_FLOOR:
        fails.append('snap uses the radius at +0x1c')
    rig.hooks_clear()
    report('player_snap', 4, fails, 'radius 12 keeps a high floor; radius 4 can miss it')


def prop_free_spot(rig):
    fails = []
    cases = []
    # (builder args, seed, expect_ok_zero, expect_sentinel)
    specs = (
        ('high', flat_world(-40, -40, 80, 80, 0, element_z=20), 20973, True, False),
        ('five', flat_world(-40, -40, 80, 80, 0, element_z=5), 20973, False, False),
        ('six', flat_world(-40, -40, 80, 80, 0, element_z=6), 1, True, False),
        ('off', flat_world(200, 200, 4, 4, 0, element_z=0, element_xy=(800, 800)), 0, False, True),
    )
    centre = (0, 0, 0)
    for name, (data, level), seed, expect_fail, expect_sentinel in specs:
        rig.load(data)
        got, ok = rig.find_free(centre, 36, 24, False, seed)
        world = Obj.World()
        world.shared = C.SharedRandom(seed)
        want, want_ok = world.find_free_spot(
            centre, 36, 24, False,
            lambda r, p, level=level: W.terrain_test_flag1(level, r, p),
            lambda r, p, level=level: W.terrain_height(level, r, p))
        want = tuple(want)
        if got != want or ok != want_ok:
            fails.append('%s disagrees with the model' % name)
        if expect_fail and (ok != 0 or got != centre):
            fails.append('%s should keep the centre' % name)
        if expect_sentinel and (ok == 0 or got[2] != W.NO_FLOOR):
            fails.append('%s should accept the sentinel' % name)
        if not expect_fail and not expect_sentinel and got[2] == W.NO_FLOOR:
            fails.append('%s lost the floor' % name)
        cases.append(name)
    report('free_spot', len(cases), fails,
           'six above fails and the centre stays; a miss counts as low enough')


def prop_arena(rig):
    emu = rig.emu
    fails = []
    entry = (f32(10.0), f32(-4.0), f32(2.0))
    table_angle = 0x1234
    plans = (
        dict(slot=0, count=1, mode_a=False, table=False, fail_first=False),
        dict(slot=2, count=4, mode_a=True, table=False, fail_first=False),
        dict(slot=1, count=4, mode_a=False, table=True, fail_first=False),
        dict(slot=1, count=2, mode_a=False, table=False, fail_first=True),
        dict(slot=3, count=3, mode_a=True, table=True, fail_first=True),
    )
    for plan in plans:
        rig.hooks_clear()
        recorded = []

        def stub_spot(e, plan=plan, recorded=recorded):
            centre = tuple(e.mem.u32((e.r[5] & M32) + 4 * i) for i in range(3))
            spread = e.r[6] & M32
            radius = e.r[7] & M32
            any_h = e.r[9] & M32
            recorded.append((centre, spread, radius, any_h))
            out = e.r[4] & M32
            fail = plan['fail_first'] and spread == L.ARENA_FIRST_SPREAD
            z = centre[2] if fail else f32(6.0)
            for i, word in enumerate((centre[0], centre[1], z)):
                e.mem.w32(out + 4 * i, word)
            e.mem.w8(e.r[8] & M32, 0 if fail else 1)
            return 0

        emu.stub(A_FREE, ret=None, function=stub_spot)
        emu.stub(A_NET_COUNT, ret=plan['count'])
        table = emu.alloc(16 * 4)
        emu.mem.write(table, bytes(16 * 4))
        for i, word in enumerate(entry):
            emu.mem.w32(table + 4 * i, word)
        emu.mem.w16(table + 0x0C, table_angle)
        if plan['slot']:
            emu.mem.w16(table + plan['slot'] * 16 + 0x0C, table_angle)
        emu.mem.w32(G_TABLE_PTR, table)
        emu.mem.w32(G_MODE_A, 1 if plan['mode_a'] else 0)
        emu.mem.w32(G_FACING_WORD, 1 if plan['table'] else 0)
        pos_out, face_out = emu.alloc(16), emu.alloc(4)
        emu.call(A_ARENA, 1, plan['slot'], pos_out, face_out, max_steps=200000)
        got = tuple(emu.mem.u32(pos_out + 4 * i) for i in range(3))
        facing = emu.mem.u16(face_out)

        def search(centre, spread, radius, any_height, plan=plan):
            fail = plan['fail_first'] and spread == L.ARENA_FIRST_SPREAD
            z = centre[2] if fail else f32(6.0)
            return (centre[0], centre[1], z), 0 if fail else 1

        want, want_face, _ok = L.arena_initial_place(
            entry, plan['slot'], plan['count'], plan['mode_a'], search,
            table_facing=plan['table'], table_angle=table_angle)
        spreads = [c[1] for c in recorded]
        want_spreads = [36, 240] if plan['fail_first'] else [36]
        centre = L.arena_ring_centre(entry, plan['slot'], plan['count'], plan['mode_a'])
        if (got != tuple(want) or facing != want_face or spreads != want_spreads
                or not recorded or recorded[0][0] != centre
                or any(c[2] != 24 or c[3] != 0 for c in recorded)):
            fails.append('slot %d count %d mode %d table %d retry %d' % (
                plan['slot'], plan['count'], plan['mode_a'], plan['table'], plan['fail_first']))
    rig.hooks_clear()
    report('arena_initial', len(plans), fails, 'ring, spread 36 then 240, facing')


# ---- the disc: counts only -----------------------------------------------------------------


def gob_lumps(data):
    out, pos, i = [], 0x800, 0
    while i + 0x28 <= 0x800:
        name = data[i:i + 32].split(b'\0', 1)[0]
        if not name:
            break
        size = struct.unpack_from('<I', data, i + 0x24)[0]
        out.append((name.decode('latin1'), data[pos:pos + size]))
        pos = (pos + size + 0x7FF) & ~0x7FF
        i += 0x28
    return out


def lmp_entries(blob):
    count = struct.unpack_from('<H', blob, 0)[0]
    out = []
    for i in range(count):
        no, do, ds = struct.unpack_from('<III', blob, 4 + i * 12)
        end = blob.index(b'\0', no)
        out.append((blob[no:end].decode('latin1'), blob[do:do + ds]))
    return out


def first_world(entries):
    picked = L.first_entry_with_extension([n for n, _ in entries], 'world')
    if picked is None:
        return None
    for name, blob in entries:
        if name == picked:
            return blob
    return None


def chunk_census(data):
    n = struct.unpack_from('<I', data, 0)[0]
    off = struct.unpack_from('<I', data, 0x24)[0]
    pieces = struct.unpack_from('<I', data, 0x50)[0]
    water = moved = 0
    for i in range(n):
        flags = struct.unpack_from('<I', data, off + i * 0x3C + 0x24)[0]
        if flags & 0x80:
            water += 1
        if flags & 0x20:
            moved += 1
    return pieces, water, moved


def scenario_positions(records):
    """Cold start, each from, each name, recall, and a gate arrival.  Identity search:
    the slot xy is the marker (or the previous slot, which is 0 here)."""
    p1 = [r for r in records if r.cls.lower() == 'player1']
    froms = {r.prop('from') for r in p1 if r.prop('from') is not None}
    names = {r.prop('name') for r in p1 if r.prop('name') is not None}
    plans = [('', '', False, False)]
    plans += [(src, '', False, False) for src in sorted(froms)]
    plans += [('', nm, False, False) for nm in sorted(names)]
    plans.append(('', '', True, False))
    if any(r.cls.lower() in ('portal', 'portalhurt') for r in records):
        plans.append(('', '', False, True))
    out = []
    for prev, entrance, recall, gate in plans:
        spawn = L.SpawnState()
        L.run_markers(spawn, records, prev, entrance, recall, lambda c, *_a: c, lambda: 0,
                      gate_arrival=gate, num_players=1)
        out.append(tuple(f32(v) for v in spawn.pos[0]))
    return out


def cold_marker(records):
    spawn = L.SpawnState()
    L.run_markers(spawn, records, '', '', False, lambda centre, *_a: centre, lambda: 0)
    p = spawn.pos[0]
    return (f32(p[0]), f32(p[1]), f32(p[2])), spawn.rank, len(
        [r for r in records if r.cls.lower() == 'player1'])


def prop_spawn_real(rig):
    disc = OPTIONS['disc']
    if not disc:
        report('spawn_real', 0, [], 'no disc given')
        return
    gobs = sorted(glob.glob(os.path.join(disc, '*.GOB')))
    tex = {os.path.splitext(os.path.basename(p))[0].upper()
           for p in glob.glob(os.path.join(disc, '*.TEX'))}
    paired = [p for p in gobs if os.path.splitext(os.path.basename(p))[0].upper() in tex]
    refused = []
    for path in paired:
        data = open(path, 'rb').read()
        lumps = gob_lumps(data)
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        lmp = next((blob for name, blob in lumps if name.lower() == stem + '.lmp'), None)
        if lmp is None:
            continue
        entries = lmp_entries(lmp)
        world = first_world(entries)
        objects = next((blob for name, blob in entries if name == 'objects.ob'), None)
        if world is None:
            continue
        pieces, water, moved = chunk_census(world)
        if pieces or water or moved:
            continue
        level = W.Level(world)
        origin = (0, 0, 0)
        if W.terrain_height_below(level, f32(4.0), origin) != W.NO_FLOOR:
            continue
        records = L.parse_objects(objects) if objects else []
        marker, rank, p1 = cold_marker(records)
        starts = [r for r in records if r.cls == 'ArenaPlayerStart']
        refused.append((world, level, marker, rank, p1, starts, scenario_positions(records)))

    fails = []
    if len(paired) != 111:
        fails.append('paired %d' % len(paired))
    if len(refused) != 18:
        fails.append('refused %d' % len(refused))
    seeds = (OPTIONS['seed'],) if OPTIONS['quick'] else (0, OPTIONS['seed'])
    snap_floor = search_floor = search_cases = arena_floor = arena_n = 0
    origin_r12_floor = origin_r4_floor = 0
    scenario_miss = 0
    notes = []
    for index, (world, level, marker, rank, p1, starts, scenarios) in enumerate(refused):
        rig.load(world)
        origin = (0, 0, 0)
        checks = {
            'below4': (A_HEIGHT_BELOW, f32(4.0), origin,
                       W.terrain_height_below(level, f32(4.0), origin)),
            'h4': (A_HEIGHT, f32(4.0), origin, W.terrain_height(level, f32(4.0), origin)),
            'h12': (A_HEIGHT, L.PLACEMENT_RADIUS, origin,
                    W.terrain_height(level, L.PLACEMENT_RADIUS, origin)),
            'marker': (A_HEIGHT, L.PLACEMENT_RADIUS, marker,
                       W.terrain_height(level, L.PLACEMENT_RADIUS, marker)),
            'at': (A_HEIGHT_POINT, None, origin, W.terrain_height_at_point(level, origin)),
        }
        got = {}
        for key, (addr, radius, pos, model) in checks.items():
            if addr == A_HEIGHT_POINT:
                buf = rig.emu.alloc(16)
                for i, word in enumerate(pos):
                    rig.emu.mem.w32(buf + 4 * i, word)
                rig.emu.call(addr, rig.base, buf, max_steps=20000000)
                got[key] = rig.emu.f[0]
            else:
                got[key] = rig.call_height(addr, radius, pos)
            if got[key] != model:
                fails.append('level %d %s' % (index, key))
        if got['below4'] != W.NO_FLOOR:
            fails.append('level %d origin below has a floor' % index)
        if got['marker'] != W.NO_FLOOR:
            snap_floor += 1
        if got['h12'] != W.NO_FLOOR:
            origin_r12_floor += 1
        if got['h4'] != W.NO_FLOOR:
            origin_r4_floor += 1
        emu = rig.emu
        emu.mem.w32(G_NUM_PLAYERS, 1)
        emu.mem.w32(G_SPAWN, marker[0])
        emu.mem.w32(G_SPAWN + 4, marker[1])
        emu.mem.w32(G_SPAWN + 8, 0x7FC00000)
        reason, _pc = rig.run_to(A_PLACE_LO, A_PLACE_HI, max_steps=50000000)
        placed = (emu.mem.u32(G_SPAWN), emu.mem.u32(G_SPAWN + 4), emu.mem.u32(G_SPAWN + 8))
        if reason != 'stop' or placed != (marker[0], marker[1], got['marker']):
            fails.append('level %d placement' % index)
        obj = emu.alloc(0x80)
        emu.mem.write(obj, bytes(0x80))
        emu.mem.w32(obj + 0x10, marker[0])
        emu.mem.w32(obj + 0x14, marker[1])
        emu.mem.w32(obj + 0x18, 0)
        emu.mem.w32(obj + 0x1C, L.PLACEMENT_RADIUS)
        emu.set_reg('s5', obj)
        emu.stub(A_RECALC, ret=0)
        reason, _pc = rig.run_to(A_SNAP_LO, A_SNAP_HI, max_steps=50000000)
        rig.hooks_clear()
        if reason != 'stop' or emu.mem.u32(obj + 0x18) != got['marker']:
            fails.append('level %d ctor snap' % index)

        for seed in seeds:
            search_cases += 1
            got_pos, ok = rig.find_free(marker, 36, 24, False, seed)
            world_o = Obj.World()
            world_o.shared = C.SharedRandom(seed)
            want_pos, want_ok = world_o.find_free_spot(
                marker, 36, 24, False,
                lambda r, p, level=level: W.terrain_test_flag1(level, r, p),
                lambda r, p, level=level: W.terrain_height(level, r, p))
            if got_pos != tuple(want_pos) or ok != want_ok:
                fails.append('level %d seed %d search' % (index, seed))
            snapped = rig.call_height(A_HEIGHT, L.PLACEMENT_RADIUS, got_pos)
            model = W.terrain_height(level, L.PLACEMENT_RADIUS, got_pos)
            if snapped != model:
                fails.append('level %d seed %d snap' % (index, seed))
            if snapped != W.NO_FLOOR:
                search_floor += 1

        if starts:
            arena_n += 1
            entry = (f32(starts[0].x), f32(starts[0].y), f32(starts[0].z))
            table = emu.alloc(16)
            for i, word in enumerate(entry):
                emu.mem.w32(table + 4 * i, word)
            emu.mem.w16(table + 0x0C, starts[0].angle & 0xFFFF)
            emu.mem.w32(G_TABLE_PTR, table)
            emu.mem.w32(G_MODE_A, 0)
            emu.mem.w32(G_FACING_WORD, 0)
            emu.mem.w32(G_SEED, OPTIONS['seed'] & M32)
            rig.empty_objects()
            emu.stub(A_NET_COUNT, ret=1)
            pos_out, face_out = emu.alloc(16), emu.alloc(4)
            emu.call(A_ARENA, 1, 0, pos_out, face_out, max_steps=200000000)
            got_pos = tuple(emu.mem.u32(pos_out + 4 * i) for i in range(3))
            facing = emu.mem.u16(face_out)
            rig.hooks_clear()
            holder = {'world': Obj.World()}
            holder['world'].shared = C.SharedRandom(OPTIONS['seed'])

            def search(centre, spread, radius, any_height, level=level, holder=holder):
                return holder['world'].find_free_spot(
                    centre, spread, radius, any_height,
                    lambda r, p, level=level: W.terrain_test_flag1(level, r, p),
                    lambda r, p, level=level: W.terrain_height(level, r, p))

            want_pos, want_face, _ok = L.arena_initial_place(entry, 0, 1, False, search)
            if got_pos != tuple(want_pos) or facing != want_face:
                fails.append('level %d arena' % index)
            arena_z = rig.call_height(A_HEIGHT, L.PLACEMENT_RADIUS, got_pos)
            if arena_z != W.NO_FLOOR:
                arena_floor += 1
        missed = False
        for pos in scenarios:
            got_h = rig.call_height(A_HEIGHT, L.PLACEMENT_RADIUS, pos)
            model = W.terrain_height(level, L.PLACEMENT_RADIUS, pos)
            if got_h != model:
                fails.append('level %d scenario' % index)
            if got_h == W.NO_FLOOR:
                missed = True
        if missed:
            scenario_miss += 1
        notes.append({'index': index, 'rank': rank, 'p1': p1, 'arena': len(starts),
                      'marker_floor': got['marker'] != W.NO_FLOOR,
                      'origin_r12': got['h12'] != W.NO_FLOOR,
                      'origin_r4': got['h4'] != W.NO_FLOOR,
                      'scenarios': len(scenarios)})
    if scenario_miss:
        fails.append('scenario misses %d' % scenario_miss)
    if search_cases and search_floor != search_cases:
        fails.append('search snap floor %d/%d' % (search_floor, search_cases))
    if snap_floor != len(refused):
        fails.append('marker snap floor %d/%d' % (snap_floor, len(refused)))
    what = ('origin r4 floor %d, origin r12 floor %d, marker r12 floor %d, '
            'search snap %d/%d, arena %d floor %d, scenario misses %d' % (
                origin_r4_floor, origin_r12_floor, snap_floor, search_floor, search_cases,
                arena_n, arena_floor, scenario_miss))
    if OPTIONS['notes']:
        dest = os.path.abspath(OPTIONS['notes'])
        local = os.path.abspath(os.path.join(ROOT, 'local'))
        if dest == local or dest.startswith(local + os.sep):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'w') as f:
                json.dump({'refused': len(refused), 'rows': notes, 'summary': what}, f)
        else:
            fails.append('notes path is not under local/')
    report('spawn_real', len(refused), fails, what)


def main(argv):
    elf = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            i += 1
            OPTIONS['seed'] = int(argv[i])
        elif a == '--disc':
            i += 1
            OPTIONS['disc'] = argv[i]
        elif a == '--notes':
            i += 1
            OPTIONS['notes'] = argv[i]
        elif a == '-k':
            i += 1
            OPTIONS['filter'] = argv[i]
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            elf = a
        i += 1
    if OPTIONS['disc'] is None and os.environ.get('RTA_DISC'):
        OPTIONS['disc'] = os.environ['RTA_DISC']
    if elf is None:
        for cand in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(cand):
                elf = cand
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_levels_r3: no SLUS_209.73 given or found; nothing tested (exit 0)')
        return 0
    digest = sha256(elf)
    if digest != EXPECTED_SHA256:
        print('difftest_levels_r3: %s is not the US v2.00 executable (sha256 %s)' % (elf, digest))
        return 1
    rig = Rig(elf)
    props = (
        ('placement_glue', prop_placement_glue),
        ('player_radius', prop_player_radius),
        ('player_snap', prop_player_snap),
        ('free_spot', prop_free_spot),
        ('arena_initial', prop_arena),
        ('spawn_real', prop_spawn_real),
    )
    for name, fn in props:
        if wanted(name):
            fn(rig)
    print('%d of %d properties pass' % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
