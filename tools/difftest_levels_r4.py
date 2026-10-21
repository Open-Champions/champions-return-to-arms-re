#!/usr/bin/env python3
"""difftest_levels_r4.py - round 4 of tools/ref_levels.py against the original code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.
The disc property runs only when you pass --disc DIR (the directory of paired level
archives) or set RTA_DISC.  It prints counts only.  --notes PATH writes per-level
detail, and only under this repo's local/.

  python3 tools/difftest_levels_r4.py [SLUS_209.73] [--disc DIR] [--notes PATH]
                                      [--quick] [--seed N] [-k TEXT] [-v]

Properties (docs/level-flow.md section 18):

  seed_matters   world_findFreeSpot 0x14acf8 on two synthetic worlds.  A disc that is a
                 floor at radius 11.25 out to 37 keeps a radius-12 snap for seeds 0 and
                 20973.  A one-sample pad keeps it for one seed and loses it for another.
  cold_three     the paired archives whose cold radius-12 query is the sentinel.  The
                 mode-A wave start (arena_pickSpawnPoint 0x3050a4, a0 = 1, slot 0, count 1)
                 is run on each, and the radius-12 snap of that point is a floor.  The
                 integer lattice out to 37 around each measured ring centre has a floor
                 at radius 11.25, so a point the search can return has one at radius 12.
"""
import glob
import hashlib
import json
import os
import re
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
from dump_tables import Elf                         # noqa: E402

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROOT = os.path.dirname(_HERE)
M32 = 0xFFFFFFFF

A_FIXUP = 0x181D30
A_HEIGHT = 0x183820
A_FREE = 0x14ACF8
A_COLLECT = 0x14A928
A_SNAP_LO, A_SNAP_HI = 0x1A2420, 0x1A2460
A_RECALC = 0x1B6458
A_ARENA = 0x3050A4
A_NET_COUNT = 0x1EC878
G_WORLD = 0x44FDC8
G_SEED = 0x404464
G_MODE_A = 0x4F711C
G_FACING_WORD = 0x4F7124
G_TABLE_PTR = 0x503888
WORLD_BASE = 0x03000000
SP = 0x01F80000

A_TABLE = 0x5037B8
B_TABLE = 0x503798
RECORDS = 0x503868
RECORD_COUNT = 0x503886
ACT_COUNTS = 0x4F8E10
ACT_TABLES = 0x4F8E48
MISSIONS = 0x4FE540

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
        for item in failures[:12]:
            print('     ', item)


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

    def call_height(self, radius, pos):
        buf = self.emu.alloc(16)
        for i, word in enumerate(pos):
            self.emu.mem.w32(buf + 4 * i, word)
        self.emu.f[12] = radius & M32
        self.emu.call(A_HEIGHT, self.base, buf, max_steps=20000000)
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

    def find_free(self, centre, spread, radius, seed):
        emu = self.emu
        self.empty_objects()
        emu.mem.w32(G_SEED, seed & M32)
        out, cen, okb = emu.alloc(16), emu.alloc(16), emu.alloc(4)
        for i, word in enumerate(centre):
            emu.mem.w32(cen + 4 * i, word)
        emu.mem.w8(okb, 0x5A)
        emu.call(A_FREE, out, cen, spread, radius, okb, 0, max_steps=200000000)
        pos = tuple(emu.mem.u32(out + 4 * i) for i in range(3))
        ok = emu.mem.u8(okb)
        self.hooks_clear()
        return pos, ok


def flat_world(x0, y0, w, h):
    samples = [0] * (w * h)
    data = W.build_world_file((-2, -2), (8, 8), [(x0, y0, w, h, samples)],
                              [(0, 0, x0, y0, 0, 32767, 0)])
    return data, W.Level(data)


def ref_search(level, centre, seed):
    world = Obj.World()
    world.shared = C.SharedRandom(seed)
    return world.find_free_spot(
        centre, L.ARENA_FIRST_SPREAD, L.ARENA_SEARCH_RADIUS, False,
        lambda r, p: W.terrain_test_flag1(level, r, p),
        lambda r, p: W.terrain_height(level, r, p))


def prop_seed_matters(rig):
    """The original search, on a solid disc and on a one-sample pad."""
    fails = []
    centre = (f32(0.0), f32(0.0), f32(0.0))
    wide_data, wide = flat_world(-40, -40, 80, 80)
    hole_data, hole = flat_world(0, 0, 1, 1)
    keep = lose = None
    for seed in range(32):
        pos, ok = ref_search(hole, centre, seed)
        snap = W.terrain_height(hole, L.PLACEMENT_RADIUS, tuple(pos))
        if snap == W.NO_FLOOR and lose is None:
            lose = seed
        elif snap != W.NO_FLOOR and keep is None:
            keep = seed
    if keep is None or lose is None:
        fails.append('synthetic pad did not produce both results')
    else:
        rig.load(hole_data)
        for seed, want_floor in ((keep, True), (lose, False)):
            got, ok = rig.find_free(centre, 36, 24, seed)
            want, want_ok = ref_search(hole, centre, seed)
            snap = rig.call_height(L.PLACEMENT_RADIUS, got)
            model = W.terrain_height(hole, L.PLACEMENT_RADIUS, got)
            if got != tuple(want) or ok != want_ok or snap != model:
                fails.append('pad seed %d' % seed)
            if want_floor and snap == W.NO_FLOOR:
                fails.append('pad seed %d lost the floor' % seed)
            if not want_floor and snap != W.NO_FLOOR:
                fails.append('pad seed %d kept the floor' % seed)
    rig.load(wide_data)
    cases = 0
    for seed in (0, OPTIONS['seed']):
        cases += 1
        got, ok = rig.find_free(centre, 36, 24, seed)
        want, want_ok = ref_search(wide, centre, seed)
        snap = rig.call_height(L.PLACEMENT_RADIUS, got)
        model = W.terrain_height(wide, L.PLACEMENT_RADIUS, got)
        if got != tuple(want) or ok != want_ok or snap != model or snap == W.NO_FLOOR:
            fails.append('solid seed %d' % seed)
    report('seed_matters', cases + 2, fails,
           'a solid disc stays on a floor; a one-sample pad loses it for one seed')


def gob_lumps(data):
    out, pos, i = [], 0x800, 0
    while i + 0x28 <= 0x800 and i + 32 <= len(data):
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


def cold_marker(records):
    spawn = L.SpawnState()
    L.run_markers(spawn, records, '', '', False, lambda centre, *_a: centre, lambda: 0)
    p = spawn.pos[0]
    return (f32(p[0]), f32(p[1]), f32(p[2])), spawn.rank


def lattice_misses(level, centre, query):
    cx, cy, cz = centre
    fx, fy = W.to_float(cx), W.to_float(cy)
    misses = tested = 0
    for ix in range(-37, 38):
        for iy in range(-37, 38):
            if ix * ix + iy * iy > 37 * 37:
                continue
            tested += 1
            pos = (f32(fx + ix), f32(fy + iy), cz)
            if W.terrain_height(level, query, pos) == W.NO_FLOOR:
                misses += 1
    return misses, tested


def table_names(elf, base, count):
    out = []
    for i in range(count):
        out.append(elf.cstr(elf.u32(base + 4 * i)))
    return out


def name_hits(elf, stems):
    """Act rows, mission level names, and bounded archive-name bytes."""
    act = mission = 0
    cold = {s.lower() for s in stems}
    for i in range(13):
        count = elf.u32(ACT_COUNTS + 4 * i)
        table = elf.u32(ACT_TABLES + 4 * i)
        for row in range(count):
            name = elf.cstr(elf.u32(table + 8 * row))
            if name and name.lower() in cold:
                act += 1
    for i in range(13):
        base = MISSIONS + i * 0x34
        for off in (0x08, 0x0C, 0x10, 0x14):
            name = elf.cstr(elf.u32(base + off))
            if name and name.lower() in cold:
                mission += 1
    return act, mission


def bounded_gob_hits(disc, stems, paths):
    """Files whose bytes contain the name as its own token. Own file, then every other."""
    own = []
    other = 0
    for stem in stems:
        pat = re.compile(rb'(?<![A-Za-z0-9_])' + re.escape(stem.encode('ascii'))
                         + rb'(?![A-Za-z0-9_])', re.I)
        mine = 0
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0].lower()
            blob = open(path, 'rb').read()
            n = len(pat.findall(blob))
            if not n:
                continue
            if name == stem:
                mine += n
            else:
                other += n
        own.append(mine)
    return own, other


def prop_cold_three(rig, elf_path):
    disc = OPTIONS['disc']
    if not disc:
        report('cold_three', 0, [], 'no disc given')
        return
    fails = []
    gobs = sorted(glob.glob(os.path.join(disc, '*.GOB')))
    tex = {os.path.splitext(os.path.basename(p))[0].upper()
           for p in glob.glob(os.path.join(disc, '*.TEX'))}
    paired = [p for p in gobs if os.path.splitext(os.path.basename(p))[0].upper() in tex]
    rows = []
    floors = 0
    for path in paired:
        data = open(path, 'rb').read()
        lumps = gob_lumps(data)
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        lmp = next((blob for name, blob in lumps if name.lower() == stem + '.lmp'), None)
        if lmp is None:
            continue
        entries = lmp_entries(lmp)
        picked = L.first_entry_with_extension([n for n, _ in entries], 'world')
        world = next((blob for name, blob in entries if name == picked), None)
        objects = next((blob for name, blob in entries if name == 'objects.ob'), None)
        if world is None:
            continue
        records = L.parse_objects(objects) if objects else []
        marker, rank = cold_marker(records)
        level = W.Level(world)
        if W.terrain_height(level, L.PLACEMENT_RADIUS, marker) != W.NO_FLOOR:
            floors += 1
            continue
        pieces, water, moved = chunk_census(world)
        starts = [r for r in records if r.cls == 'ArenaPlayerStart']
        alts = [r for r in records if r.cls == 'ArenaPlayerAlternate']
        portals = [r for r in records if r.cls.lower() in ('portal', 'portalhurt')]
        players = [r for r in records if r.cls.lower() == 'player1']
        rows.append({
            'stem': stem, 'world': world, 'level': level, 'records': records,
            'marker': marker, 'rank': rank, 'pieces': pieces, 'water': water,
            'moved': moved, 'starts': starts, 'alts': len(alts),
            'portals': len(portals), 'players': len(players),
            'records_n': len(records),
        })
    if len(paired) != 111:
        fails.append('paired %d' % len(paired))
    if len(rows) != 3 or floors != 108:
        fails.append('cold %d floor %d' % (len(rows), floors))
    elf = Elf(open(elf_path, 'rb').read())
    stems = [row['stem'] for row in rows]
    cold = {s.lower() for s in stems}
    a_names = table_names(elf, A_TABLE, L.ARENA_MODE_A_COUNT)
    b_names = table_names(elf, B_TABLE, L.ARENA_MODE_B_COUNT)
    a_idx = {i for i, name in enumerate(a_names) if name and name.lower() in cold}
    b_idx = {i for i, name in enumerate(b_names) if name and name.lower() in cold}
    if a_idx != {8, 10, 12}:
        fails.append('mode A indices %s' % sorted(a_idx))
    if b_idx != {1, 3}:
        fails.append('mode B indices %s' % sorted(b_idx))
    if elf.u16(RECORD_COUNT) != 5:
        fails.append('record count %d' % elf.u16(RECORD_COUNT))
    rec_index = []
    for i in range(5):
        off = L.arena_record_table_offset(elf.u8(RECORDS + i * L.ARENA_RECORD_BYTES))
        rec_index.append(off // 4)
    if rec_index[0] != 0 or (b_names[0] or '').lower() in cold:
        fails.append('record 0 selects one of the three')
    act_hits, mission_hits = name_hits(elf, stems)
    if act_hits or mission_hits:
        fails.append('act %d mission %d' % (act_hits, mission_hits))
    own, other = bounded_gob_hits(disc, stems, gobs)
    if other or own != [2, 2, 2]:
        fails.append('name bytes own %s other %d' % (own, other))

    seeds = (OPTIONS['seed'],) if OPTIONS['quick'] else (0, OPTIONS['seed'])
    ring_floor = search_floor = search_n = snap_floor = stand_floor = stand_n = 0
    lattice = 0
    origin_floor = start_floor = 0
    centres = ((1, 0), (2, 1), (4, 1), (4, 2), (4, 3))
    query = f32(11.25)
    notes = []
    for index, row in enumerate(rows):
        if row['players'] or row['portals'] or len(row['starts']) != 1 or row['rank'] != 0:
            fails.append('level %d markers' % index)
            continue
        if row['pieces'] or row['moved'] or not row['water']:
            fails.append('level %d geometry' % index)
        starts = row['starts'][0]
        entry = (f32(starts.x), f32(starts.y), f32(starts.z))
        level = row['level']
        rig.load(row['world'])
        origin = rig.call_height(L.PLACEMENT_RADIUS, row['marker'])
        start_h = rig.call_height(L.PLACEMENT_RADIUS, entry)
        if origin != W.terrain_height(level, L.PLACEMENT_RADIUS, row['marker']):
            fails.append('level %d origin' % index)
        if start_h != W.terrain_height(level, L.PLACEMENT_RADIUS, entry):
            fails.append('level %d start' % index)
        if origin != W.NO_FLOOR:
            origin_floor += 1
        if start_h != W.NO_FLOOR:
            start_floor += 1
        centre = L.arena_ring_centre(entry, 0, 1, True)
        centre_h = rig.call_height(L.PLACEMENT_RADIUS, centre)
        if centre_h != W.terrain_height(level, L.PLACEMENT_RADIUS, centre):
            fails.append('level %d centre' % index)
        if centre_h != W.NO_FLOOR:
            ring_floor += 1
        for count, slot in centres:
            misses, tested = lattice_misses(
                level, L.arena_ring_centre(entry, slot, count, True), query)
            lattice += misses
            if misses or tested != 4293:
                fails.append('level %d lattice %d/%d' % (index, misses, tested))
        emu = rig.emu
        for seed in seeds:
            search_n += 1
            rig.hooks_clear()
            rig.empty_objects()
            emu.stub(A_NET_COUNT, ret=1)
            table = emu.alloc(16)
            for i, word in enumerate(entry):
                emu.mem.w32(table + 4 * i, word)
            emu.mem.w16(table + 0x0C, starts.angle & 0xFFFF)
            emu.mem.w32(G_TABLE_PTR, table)
            emu.mem.w32(G_MODE_A, 1)
            emu.mem.w32(G_FACING_WORD, 0)
            emu.mem.w32(G_SEED, seed & M32)
            pos_out, face_out = emu.alloc(16), emu.alloc(4)
            emu.call(A_ARENA, 1, 0, pos_out, face_out, max_steps=200000000)
            got = tuple(emu.mem.u32(pos_out + 4 * i) for i in range(3))
            facing = emu.mem.u16(face_out)
            rig.hooks_clear()
            holder = {'world': Obj.World()}
            holder['world'].shared = C.SharedRandom(seed)

            def search(c, spread, radius, any_height, level=level, holder=holder):
                return holder['world'].find_free_spot(
                    c, spread, radius, any_height,
                    lambda r, p, level=level: W.terrain_test_flag1(level, r, p),
                    lambda r, p, level=level: W.terrain_height(level, r, p))

            want, want_face, _ok = L.arena_initial_place(entry, 0, 1, True, search)
            if got != tuple(want) or facing != want_face:
                fails.append('level %d seed %d place' % (index, seed))
            snap = rig.call_height(L.PLACEMENT_RADIUS, got)
            model = W.terrain_height(level, L.PLACEMENT_RADIUS, got)
            if snap != model:
                fails.append('level %d seed %d height' % (index, seed))
            obj = emu.alloc(0x80)
            emu.mem.write(obj, bytes(0x80))
            emu.mem.w32(obj + 0x10, got[0])
            emu.mem.w32(obj + 0x14, got[1])
            emu.mem.w32(obj + 0x18, 0)
            emu.mem.w32(obj + 0x1C, L.PLACEMENT_RADIUS)
            emu.set_reg('s5', obj)
            emu.stub(A_RECALC, ret=0)
            reason, _pc = rig.run_to(A_SNAP_LO, A_SNAP_HI, max_steps=50000000)
            rig.hooks_clear()
            if reason != 'stop' or emu.mem.u32(obj + 0x18) != snap:
                fails.append('level %d seed %d snap' % (index, seed))
            if snap != W.NO_FLOOR:
                search_floor += 1
                snap_floor += 1
        for seed in seeds:
            stand_n += 1
            world_o = Obj.World()
            world_o.shared = C.SharedRandom(seed)
            for n, rec in enumerate(row['records']):
                world_o.construct(0x20000000 + n * 0x80,
                                  (f32(rec.x), f32(rec.y), f32(rec.z)))
            pos, _ok = world_o.find_free_spot(
                centre, L.ARENA_FIRST_SPREAD, L.ARENA_SEARCH_RADIUS, False,
                lambda r, p, level=level: W.terrain_test_flag1(level, r, p),
                lambda r, p, level=level: W.terrain_height(level, r, p))
            if W.terrain_height(level, L.PLACEMENT_RADIUS, tuple(pos)) != W.NO_FLOOR:
                stand_floor += 1
        notes.append({
            'stem': row['stem'], 'water': row['water'], 'alts': row['alts'],
            'records': row['records_n'], 'pieces': row['pieces'],
        })
    if rows and (origin_floor or start_floor != len(rows) or ring_floor != len(rows)):
        fails.append('origin floor %d start floor %d ring floor %d' % (
            origin_floor, start_floor, ring_floor))
    if search_n and search_floor != search_n:
        fails.append('search floor %d/%d' % (search_floor, search_n))
    if stand_n and stand_floor != stand_n:
        fails.append('stand-in floor %d/%d' % (stand_floor, stand_n))
    if lattice:
        fails.append('lattice misses %d' % lattice)
    waters = sorted(row['water'] for row in rows)
    alts = sorted(row['alts'] for row in rows)
    what = ('cold %d, origin floor %d, start floor %d, ring floor %d, '
            'search snap %d/%d, stand-in %d/%d, lattice misses %d, '
            'water %s, alternates %s, act %d, mission %d, other names %d' % (
                len(rows), origin_floor, start_floor, ring_floor,
                search_floor, search_n, stand_floor, stand_n, lattice,
                waters, alts, act_hits if rows else 0, mission_hits if rows else 0,
                other if rows else 0))
    if OPTIONS['notes']:
        dest = os.path.abspath(OPTIONS['notes'])
        local = os.path.abspath(os.path.join(ROOT, 'local'))
        if dest == local or dest.startswith(local + os.sep):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'w') as f:
                json.dump({'rows': notes, 'summary': what,
                           'mode_a': sorted(a_idx), 'mode_b': sorted(b_idx)}, f)
        else:
            fails.append('notes path is not under local/')
    report('cold_three', len(rows), fails, what)


def main(argv):
    elf = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--quick':
            OPTIONS['quick'] = True
        elif arg == '--seed':
            i += 1
            OPTIONS['seed'] = int(argv[i])
        elif arg == '--disc':
            i += 1
            OPTIONS['disc'] = argv[i]
        elif arg == '--notes':
            i += 1
            OPTIONS['notes'] = argv[i]
        elif arg == '-k':
            i += 1
            OPTIONS['filter'] = argv[i]
        elif arg == '-v':
            OPTIONS['verbose'] = True
        elif arg in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            elf = arg
        i += 1
    if OPTIONS['disc'] is None and os.environ.get('RTA_DISC'):
        OPTIONS['disc'] = os.environ['RTA_DISC']
    if elf is None:
        for cand in (os.path.join(ROOT, 'SLUS_209.73'),
                     os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(cand):
                elf = cand
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_levels_r4: no SLUS_209.73 given or found; nothing tested (exit 0)')
        return 0
    digest = sha256(elf)
    if digest != EXPECTED_SHA256:
        print('difftest_levels_r4: %s is not the US v2.00 executable (sha256 %s)' % (elf, digest))
        return 1
    rig = Rig(elf)
    props = (
        ('seed_matters', lambda: prop_seed_matters(rig)),
        ('cold_three', lambda: prop_cold_three(rig, elf)),
    )
    for name, fn in props:
        if wanted(name):
            fn()
    print('%d of %d properties pass' % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
