#!/usr/bin/env python3
"""Run the arena's real creature construction chain and compare it with
tools/ref_arena_creature_chain.py.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_creature_chain.py local/SLUS_209.73 --seed 20973 \
      [--disc DIR]

world_createObject -> world_objectFactory -> the class constructor -> Creature_ctor ->
GameObject_ctor, creature_bossRank, balance_lookup, Creature_setStats, the class code,
Mummy_setState, obj_runEvery60 and Creature_init all execute in tools/ee_emu.py
(ref_arena_creature_chain.REAL).  Only the SERVICES are call boundaries: pool_new (a
zero-filled block), res_find (one authored part for every entry), handle_link /
handle_clear, the model and animation calls, and model_getBounds (authored bounds).

Three classes (arena indices 3, 1, 0: the first recipe's waves 0-2), each built twice in
one state (the second construction finds its class definition already resolved), at
the monster levels arena_startWave stores for waves 0, 1 and 2.  The balance table is
empty unless --disc names the folder holding the user's balance.lmp: its monsters.bal
entry is then copied into the emulator at run time, as balance_load would place it, and
the model reads the same memory.  Nothing from the disc is printed or saved.

Also: balance_lookup on authored record tables, and Creature_init on authored property
lists, holders, flags and bounds (every branch of its body).
"""
import argparse
import hashlib
import os
import random

from ee_emu import EE
import anim_audio_info as AI
import ref_arena_creature_chain as R
import ref_combat as RC
import ref_core as C

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
FACTORY_POINTER, OBJECT_FACTORY, WORLD_CREATE = 0x5F76F4, 0x159C94, 0x14F6C8
ARENA_PROPS, ARENA_PROP_TEXT, ARENA_PROP_SOURCE = 0x8E7230, 0x8E7238, 0x551E80
RAND = 0x1509D0
INDICES = (R.GOBLIN, R.MUMMY, R.SCORPION, R.ORC2, R.SNOBADGE)
LEVEL_STEP, LEVEL_BASE = 0x3F2BC579, 0x40A00000     # docs/arena-modes.md 3.1: wave x step + 5


class Follow(set):
    def __contains__(self, target):
        return set.__contains__(self, target) or R.LIBRARY[0] <= target < R.LIBRARY[1]


def arena_level(wave):
    return C.add(C.mul(C.from_int(wave), LEVEL_STEP), LEVEL_BASE)


def balance_entry(disc):
    """The monsters.bal entry of the user's balance.lmp, read at run time."""
    hits = [f for f in os.listdir(disc) if f.lower() == 'balance.lmp']
    if not hits:
        raise FileNotFoundError('balance.lmp not in %s' % disc)
    with open(os.path.join(disc, hits[0]), 'rb') as f:
        data = f.read()
    for name, off, size in AI.lmp_entries(data):
        if name.lower() == 'monsters.bal':
            return data[off:off + size]
    raise FileNotFoundError('monsters.bal not in balance.lmp')


def place_balance(emu, entry):
    """As balance_load 0x223998 leaves it: records = data + 2, count = s16 data[0]."""
    addr = emu.alloc(len(entry) + 16)
    emu.mem.write(addr, bytes(entry))
    emu.mem.w32(R.BALANCE_RECORDS, addr + 2)
    emu.mem.w32(R.BALANCE_COUNT, C.s16(entry[0] | entry[1] << 8) & 0xFFFFFFFF)


def arena_props(emu):
    """arena_init 0x304c4c's list (0x304e58-0x304e84, Observed): 0x8e7230 = {0x8e7238, 0},
    the string's first byte copied from 0x551e80."""
    emu.mem.w32(ARENA_PROPS, ARENA_PROP_TEXT)
    emu.mem.w32(ARENA_PROPS + 4, 0)
    emu.mem.w8(ARENA_PROP_TEXT, emu.mem.u8(ARENA_PROP_SOURCE))


SKILL_STATIC_INIT, SKILL_INIT_STATS_ALL = 0x16AC74, 0x1EBCA0   # tools/difftest_skills_a.py


def build_skills(e):
    """The game's start-up initialiser builds the 101 Skill objects and their statistics
    (as tools/difftest_skills_a.py and probe_full_placement --skills do).  It moves the
    shared seed, so callers set the seed afterwards."""
    follow, record = e.follow, e.record_calls
    e.follow, e.record_calls = None, False
    e.r[29] = e.stack_hi - 0x100
    e.call(SKILL_STATIC_INIT, 1, 0xFFFF, max_steps=20000000)
    e.r[29] = e.stack_hi - 0x100
    e.call(SKILL_INIT_STATS_ALL, max_steps=20000000)
    e.follow, e.record_calls = follow, record
    e.reset_log()


def new_world(path, seed, level, entry):
    e = EE(path)
    build_skills(e)
    e.mem.w32(R.SEED, seed)
    e.mem.w32(FACTORY_POINTER, OBJECT_FACTORY)
    e.mem.w32(0x4F714C, level)
    arena_props(e)
    if entry is not None:
        place_balance(e, entry)
    part = e.alloc(0x400)
    e.stub(R.RES_FIND, ret=part)
    e.blocks = []

    def pool_new(x):
        block = x.alloc(x.r[4] & 0xFFFFFFFF)
        x.blocks.append(block)
        return block
    e.stub(R.POOL_NEW, function=pool_new)
    e.bounds = (0, 100)

    def bounds(x):
        outs = [x.r[k] & 0xFFFFFFFF for k in range(6, 12)]
        values = (0, 0, x.bounds[0], 10, 10, x.bounds[1])
        for out, value in zip(outs, values):
            x.mem.w32(out, value & 0xFFFFFFFF)
        return 0
    e.stub(R.MODEL_BOUNDS, function=bounds)
    for service in R.SERVICES - {R.RES_FIND, R.POOL_NEW, R.MODEL_BOUNDS}:
        e.stub(service, ret=0)
    return e


def construct(e, index, seed_rng, tables):
    """One world_createObject call, compared field by field with the model."""
    e.reset_log()
    pos = e.alloc(16)
    point = tuple(C.f32(seed_rng.uniform(-300, 300)) for _ in range(2)) + (0,)
    for k in range(3):
        e.mem.w32(pos + 4 * k, point[k])
    facing = seed_rng.getrandbits(16)
    e.bounds = seed_rng.choice(((0, 100), (10, 50), (-20, 200), (5, 89)))
    e.follow = Follow(set(R.REAL) | {R.CONSTRUCTOR[index]})
    seed = e.mem.u32(R.SEED)
    want = R.chain(index, seed, e.mem.u32, e.mem.u8, tables, e.bounds)
    name = e.mem.u32(R.CLASSES + 4 * index)
    obj = e.call(WORLD_CREATE, name, pos, facing, ARENA_PROPS) & 0xFFFFFFFF
    tag = (index, hex(seed))
    assert obj == e.blocks[-1], tag
    services = [c.target for c in e.calls if c.stubbed]
    assert all(t in R.SERVICES for t in services), (tag, 'unexpected boundary', [hex(t) for t in services])
    assert services == want['services'], (tag, [hex(t) for t in services], [hex(t) for t in want['services']])
    pool = [c for c in e.calls if c.target == R.POOL_NEW]
    assert len(pool) == 1 and pool[0].args[0] & 0xFFFFFFFF == R.SIZE[index], tag
    assert e.mem.u32(R.SEED) == want['shared'], (tag, 'shared seed')
    draws = sum(1 for c in e.calls if c.target == RAND)
    assert draws == want['own_draws'], (tag, 'own draws', draws, want['own_draws'])
    n = 0
    for off, (width, value) in sorted(want['fields'].items()):
        got = e.mem.load(obj + off, width)
        assert got == value, (tag, 'field', hex(off), hex(got), hex(value))
        n += 1
    for k in range(3):
        assert e.mem.u32(obj + 0x10 + 4 * k) == point[k], (tag, 'position')
        assert e.mem.u32(obj + 0x3B4 + 4 * k) == point[k], (tag, 'home')
    assert e.mem.u16(obj + 0x38) == facing, (tag, 'facing')
    two = want['shared'] != R.lcg(seed)[0]
    if two:
        assert want['shared'] == R.lcg(R.lcg(seed)[0])[0], tag
    return n + 8 + len(services), (want['found'], two)


def chain_cases(path, seed, entry, tables):
    rng = random.Random(seed)
    count, found, two = 0, 0, 0
    for wave in range(3):
        for index in INDICES:
            e = new_world(path, seed + 1000 * wave + index, arena_level(wave), entry)
            for _repeat in range(2):
                n, (hit, double) = construct(e, index, rng, tables)
                count += n
                found += hit
                two += double
    return count, found, two


# ---- balance_lookup on authored tables ------------------------------------------------
def balance_cases(path, seed):
    rng = random.Random(seed ^ 0xBA1A)
    e = EE(path)
    e.follow = Follow({0x223A4C, 0x223914})
    count = 0
    for case in range(60):
        names = [bytes(rng.choice(b'abcdefgXYZ_019') for _ in range(rng.randint(1, 12))) for _ in range(6)]
        records = []
        for nm in names[:rng.randint(0, 6)]:
            h = R.balance_hash(nm) if rng.random() < 0.8 else rng.getrandbits(16)
            records.append((h,) + tuple(rng.choice((0, 50, 100, 150, 0x7FFF, 0x8000, 0xFFFF, rng.getrandbits(16)))
                                        for _ in range(5)))
        rng.shuffle(records)
        table = e.alloc(12 * len(records) + 16)
        for k, rec in enumerate(records):
            for j, v in enumerate(rec):
                e.mem.w16(table + 12 * k + 2 * j, v)
        e.mem.w32(R.BALANCE_RECORDS, table)
        e.mem.w32(R.BALANCE_COUNT, len(records) if case % 7 else (0xFFFFFFFF if case % 2 else 0))
        query = rng.choice(names + [None])
        name_ptr = 0
        if query is not None:
            name_ptr = e.alloc(len(query) + 8)
            e.mem.write(name_ptr, query + b'\0')
        outs = e.alloc(32)
        for k in range(5):
            e.mem.w32(outs + 4 * k, 0xDEADBEEF)
        e.reset_log()
        got = e.call(0x223A4C, name_ptr, *(outs + 4 * k for k in range(5))) & 0xFFFFFFFF
        found, factors = R.balance_lookup(e.mem.u32, query)
        assert got == found, (seed, case, got, found)
        assert tuple(e.mem.u32(outs + 4 * k) for k in range(5)) == factors, (seed, case)
        if query is not None:
            hashes = [c.ret for c in e.calls if c.target == 0x223914]
            assert hashes == [] or (e.r[2] is not None)
        count += 6
    return count


# ---- Creature_init on authored objects ------------------------------------------------
def init_cases(path, seed):
    rng = random.Random(seed ^ 0x1417)
    count = 0
    for case in range(80):
        e = EE(path)
        e.follow = Follow({0x10A230, 0x14C880, 0x14F4C0, 0x3C2738})
        table = 0x510260                     # Goblin's table; slots 16, 18, 27 read from it
        slot = {k: e.mem.u32(table + 8 * k + 4) for k in (16, 18, 27)}
        assert slot[16] == 0x3C2738
        c = e.alloc(0x600)
        definition = e.alloc(0x40)
        model = rng.choice((0, 0x00C00040))
        e.mem.w32(definition + 0xC, model)
        e.mem.w32(c + 0x24, definition)
        e.mem.w32(c + 0x48, table)
        cflags = rng.getrandbits(64) & ~R.DEAD_FLAG if rng.random() < 0.3 else rng.choice((0, 1))
        e.mem.w64(c + 0xA8, cflags)
        holder = 0
        holder_calls = []
        if rng.random() < 0.7:
            holder = e.alloc(0x40)
            htable = e.alloc(0x50)
            e.mem.w32(holder, htable)
            for k in range(2, 9):
                target = e.alloc(8)
                e.mem.w32(htable + 8 * k + 4, target)
                e.stub(target, function=lambda x, k=k: holder_calls.append(k) or 0)
        e.mem.w32(c + 0x50, holder)
        props = {}
        keys = [b'dead', b'initscript'] + list(R.WEAPON_PROPS) + [b'change%d' % k for k in range(32)] + [b'other']
        for key in rng.sample(keys, rng.randint(0, 6)):
            props[key] = rng.choice((b'1', b'2', b'0', b'abc')) if key in R.WEAPON_PROPS else rng.choice((b'x1', b''))
        if case == 0:
            props = {b'dead': b'', b'change0': b'', b'initscript': b''}
        strings = []
        for key, value in props.items():
            s = e.alloc(64)
            e.mem.write(s, key + b'=' + value + b'\0')
            strings.append(s)
        plist = e.alloc(4 * len(strings) + 8)
        for k, s in enumerate(strings):
            e.mem.w32(plist + 4 * k, s)
        e.mem.w32(c + 0x2C, plist)
        cutscene = 0 if case == 0 else rng.choice((0, 0, 1))
        e.mem.w8(R.CUTSCENE, cutscene)
        bounds = rng.choice(((0, 100), (10, 50), (-20, 200), (5, 89), (0, 84), (0, 83)))
        hide = rng.getrandbits(64)
        log = []

        def svc(name):
            def answer(x):
                if name == 'bounds':
                    outs = [x.r[k] & 0xFFFFFFFF for k in range(6, 12)]
                    for out, value in zip(outs, (0, 0, bounds[0], 9, 9, bounds[1])):
                        x.mem.w32(out, value & 0xFFFFFFFF)
                    log.append((R.MODEL_BOUNDS, x.r[4] & 0xFFFFFFFF))
                    assert x.r[5] & 0xFFFFFFFF == 0xFFFFFFFF
                    return 0
                if name == 'hide':
                    log.append((R.HIDE_MASK, x.r[4] & 0xFFFFFFFF, x.r[5] & 0xFFFFFFFF))
                    return hide
                if name == 'snap':
                    assert x.r[4] & 0xFFFFFFFF == c + 0x114
                    log.append((R.ANIM_SNAP_END,))
                    return 0
                if name == 'script':
                    assert x.mem.u32(R.SELECTED_OBJECT) == c
                    log.append((R.SCRIPT_RUN,))
                    return 0
                if name == 18:
                    log.append(('slot', 18))
                    return 0
                if name == 27:
                    assert x.r[5] & 0xFFFFFFFF == 0x14
                    log.append(('slot', 27, 0x14))
                    return 0
            return answer
        e.stub(R.MODEL_BOUNDS, function=svc('bounds'))
        e.stub(R.HIDE_MASK, function=svc('hide'))
        e.stub(R.ANIM_SNAP_END, function=svc('snap'))
        e.stub(R.SCRIPT_RUN, function=svc('script'))
        e.stub(slot[18], function=svc(18))
        e.stub(slot[27], function=svc(27))
        e.reset_log()
        e.call(0x10A230, c)
        log += [('holder', k) for k in holder_calls]
        want_calls, fields = R.creature_init(cflags, model, props, bool(holder), cutscene, bounds, hide)
        order = lambda calls: ([x for x in calls if x[0] != 'holder'], [x for x in calls if x[0] == 'holder'])
        assert order(log) == order(want_calls), (seed, case, log, want_calls)
        for off, (width, value) in fields.items():
            got = e.mem.load(c + off, width)
            assert got == value, (seed, case, hex(off), hex(got), hex(value))
        assert e.mem.u32(R.SELECTED_OBJECT) == 0
        assert not any(c2.target == RAND for c2 in e.calls), 'Creature_init drew'
        count += 2 + len(fields)
    return count


# ---- world_findFreeSpot on authored terrain and box answers ----------------------------
def free_spot_cases(path, seed):
    rng = random.Random(seed ^ 0xF5)
    count = 0
    for case in range(120):
        e = EE(path)
        e.follow = Follow({R.FREE_SPOT})
        start = rng.getrandbits(32)
        e.mem.w32(R.SEED, start)
        center = (C.f32(rng.uniform(-500, 500)), C.f32(rng.uniform(-500, 500)), C.f32(rng.choice((0, 0, 12.5, -3))))
        cptr = e.alloc(16)
        for k in range(3):
            e.mem.w32(cptr + 4 * k, center[k])
        rng_range, radius = rng.choice((36, 96, 72, 48, 0, 5)), rng.choice((24, 12, 0, 30))
        any_height = rng.choice((0, 0, 1))
        ok_ptr = e.alloc(8)
        e.mem.w8(ok_ptr, 0xEE)
        out = e.alloc(16)
        cut = C.f32(rng.uniform(-400, 400))
        mode = rng.choice(('open', 'open', 'wall', 'steps', 'crowd', 'full'))
        objects = []
        if mode in ('crowd', 'full'):
            for _ in range(rng.randint(1, 6) if mode == 'crowd' else 1):
                ox = C.add(center[0], C.f32(rng.uniform(-60, 60)))
                oy = C.add(center[1], C.f32(rng.uniform(-60, 60)))
                orad = C.f32(rng.choice((0, 12, 18, 30, 400 if mode == 'full' else 20)))
                objects.append((ox, oy, orad, rng.choice((0x20, 0x20, 0x21))))
            if mode == 'full':
                objects[0] = (center[0], center[1], C.f32(10000.0), 0x20)

        def blocked(point):
            return C.ONE if mode == 'wall' and C.lt(point[0], cut) else 0

        def height(point):
            if mode == 'steps':
                return C.f32(7.0) if C.lt(cut, point[1]) else C.f32(3.0)
            return center[2]
        blocks = []
        for ox, oy, orad, oflags in objects:
            b = e.alloc(0x40)
            e.mem.w32(b + 0xC, oflags)
            e.mem.w32(b + 0x10, ox)
            e.mem.w32(b + 0x14, oy)
            e.mem.w32(b + 0x1C, orad)
            blocks.append(b)
        asked = []

        def svc_blocked(x):
            pt = tuple(x.mem.u32((x.r[5] & 0xFFFFFFFF) + 4 * k) for k in range(3))
            x.f[0] = blocked(pt)
            return 0

        def svc_height(x):
            pt = tuple(x.mem.u32((x.r[5] & 0xFFFFFFFF) + 4 * k) for k in range(3))
            x.f[0] = height(pt)
            return 0

        def svc_box(x):
            lo = tuple(x.mem.u32((x.r[4] & 0xFFFFFFFF) + 4 * k) for k in range(3))
            hi = tuple(x.mem.u32((x.r[5] & 0xFFFFFFFF) + 4 * k) for k in range(3))
            asked.append((lo, hi))
            dst = x.r[6] & 0xFFFFFFFF
            assert x.r[7] & 0xFFFFFFFF == 0x80
            for k, b in enumerate(blocks):
                x.mem.w32(dst + 4 * k, b)
            x.mem.w32(dst + 4 * len(blocks), 0)
            return len(blocks)
        e.stub(0x183B48, function=svc_blocked)
        e.stub(0x183820, function=svc_height)
        e.stub(0x14A928, function=svc_box)
        e.call(R.FREE_SPOT, out, cptr, rng_range, radius, ok_ptr, any_height)
        want = R.free_spot(start, center, rng_range, radius, any_height, blocked, height,
                           lambda lo, hi: objects)
        new_seed, spot, ok, tries, draws, boxes = want
        tag = (seed, case, mode)
        assert e.mem.u32(R.SEED) == new_seed, (tag, 'seed')
        assert tuple(e.mem.u32(out + 4 * k) for k in range(3)) == spot, (tag, 'spot')
        assert e.mem.u8(ok_ptr) == ok, (tag, 'ok')
        assert asked == boxes, (tag, 'boxes')
        assert e.mem.u32(R.SEED) == R.lcg_n(start, draws), tag
        count += 4
    return count


# ---- OniBall_ctor on authored creatures ----------------------------------------------
def oniball_cases(path, seed):
    rng = random.Random(seed ^ 0x0B)
    count = 0
    for case in range(40):
        e = EE(path)
        build_skills(e)
        e.follow = Follow({R.ONIBALL_CTOR, R.PROJECTILE_CTOR, 0x14CB10, RAND, 0x14C880})
        start = rng.getrandbits(32)
        e.mem.w32(R.SEED, start)
        frame = rng.getrandbits(20)
        e.mem.w32(R.G_SIM_FRAME, frame)
        c = e.alloc(0x600)
        max_hp = C.f32(rng.uniform(1, 5000))
        e.mem.w32(c + 0x22C, max_hp)
        pos = tuple(C.f32(rng.uniform(-400, 400)) for _ in range(3))
        p = e.alloc(16)
        for k in range(3):
            e.mem.w32(p + 4 * k, pos[k])
        block = e.alloc(R.ONIBALL_SIZE)
        e.call(R.ONIBALL_CTOR, block, p, rng.getrandbits(16), c, 0)
        shared, own, fields, creature = R.oniball_ctor(start, pos, frame, max_hp)
        assert e.mem.u32(R.SEED) == shared, (seed, case)
        for off, (width, value) in fields.items():
            assert e.mem.load(block + off, width) == value, (seed, case, hex(off), hex(e.mem.load(block + off, width)), hex(value))
        for off, (width, value) in creature.items():
            assert e.mem.load(c + off, width) == value, (seed, case, 'creature', hex(off))
        services = [t.target for t in e.calls if t.stubbed]
        assert services == [R.HANDLE_LINK, R.OBJ_RUN_EVERY_FRAME], [hex(t) for t in services]
        count += 1 + len(fields) + len(creature)
    return count


# ---- Goblin_onNearbyEvent on authored Goblins and sources ----------------------------
def nearby_cases(path, seed):
    nearby_cases.hits = {}
    rng = random.Random(seed ^ 0x12)
    count = 0
    tables = {'goblin': 0x510260, 'mummy': 0x516E48, 'player': 0x511308}
    for case in range(120):
        e = EE(path)
        e.follow = Follow({R.GOBLIN_ON_NEARBY, R.GOBLIN_HAS_SHIELD, 0x166798, 0x3B1250} |
                          {e.mem.u32(t + 4) for t in tables.values()})
        g = e.alloc(0x500)
        e.mem.w32(g + 0x48, tables['goblin'])
        state = rng.choice((0, 1, 2, 3, 5, 0x10, 0xFFFF))
        e.mem.w16(g + 0x232, state)
        facing = rng.getrandbits(16)
        e.mem.w16(g + 0x38, facing)
        gxy = (C.f32(rng.uniform(-300, 300)), C.f32(rng.uniform(-300, 300)))
        e.mem.w32(g + 0x10, gxy[0])
        e.mem.w32(g + 0x14, gxy[1])
        answers = {15: rng.choice((7, 7, 3, 0)), 14: rng.choice((0, 1, 2))}
        holder = 0
        if rng.random() < 0.8:
            holder = e.alloc(0x40)
            htable = e.alloc(0x90)
            e.mem.w32(holder, htable)
            for k in (14, 15):
                target = e.alloc(8)
                e.mem.w32(htable + 8 * k + 4, target)

                def answer(x, k=k):
                    assert x.r[5] & 0xFFFFFFFF == 2
                    return answers[k]
                e.stub(target, function=answer)
        e.mem.w32(g + 0x50, holder)
        requests = []
        e.stub(e.mem.u32(tables['goblin'] + 8 * 27 + 4), function=lambda x: requests.append(x.r[5] & 0xFFFFFFFF) or 0)
        kind = 'goblin' if case % 4 == 0 else rng.choice(('goblin', 'goblin', 'mummy', 'player', None))
        source = 0
        sxy = (0, 0)
        if kind:
            source = e.alloc(0x600)
            e.mem.w32(source + 0x48, tables[kind])
            sxy = (C.add(gxy[0], C.f32(rng.uniform(-200, 200))), C.add(gxy[1], C.f32(rng.uniform(-200, 200))))
            e.mem.w32(source + 0x10, sxy[0])
            e.mem.w32(source + 0x14, sxy[1])
        if kind and case % 2:            # aim at the shield branch: facing near the source's bearing
            bearing = C.atan2_16(C.sub(sxy[1], gxy[1]), C.sub(sxy[0], gxy[0]))
            facing = (bearing + rng.randint(-12000, 12000)) & 0xFFFF
            e.mem.w16(g + 0x38, facing)
            answers.update({15: 7, 14: 1})
        pos = e.alloc(16)
        point = tuple(C.f32(rng.uniform(-500, 500)) for _ in range(3))
        for k in range(3):
            e.mem.w32(pos + 4 * k, point[k])
        event = 2 if kind and case % 2 and rng.random() < 0.7 else rng.choice((0, 0, 2, 2, 1, 3))
        if case % 4 == 0:
            event, state = 0, rng.choice((0, 1, 1, 2))
            e.mem.w16(g + 0x232, state)
        if event == 2 and case % 2:
            state = rng.choice((3, 5, 3, 0))
            e.mem.w16(g + 0x232, state)
        e.call(R.GOBLIN_ON_NEARBY, g, event, pos, source)
        shield = R.goblin_has_shield_up(answers[15], answers[14]) if holder else 0
        want, store = R.goblin_on_nearby_event(state, event, source, kind == 'goblin', shield, gxy, facing, sxy)
        tag = (seed, case, kind, event, state)
        assert requests == ([want] if want is not None else []), (tag, requests, want)
        nearby_cases.hits[want] = nearby_cases.hits.get(want, 0) + 1
        stored = tuple(e.mem.u32(g + 0x104 + 4 * k) for k in range(3))
        assert stored == (point if store else (0, 0, 0)), (tag, 'position')
        assert e.mem.u32(R.SEED) == 0 and not any(c.target == RAND for c in e.calls), tag
        count += 3
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--disc', help='folder with the user\'s balance.lmp (read at run time only)')
    args = parser.parse_args()
    with open(args.elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable'
    tables = RC.Tables.load(args.elf)
    print('balance_lookup, authored tables: %d comparisons matched (seed %d)' % (balance_cases(args.elf, args.seed), args.seed))
    print('Creature_init, authored objects: %d comparisons matched (seed %d)' % (init_cases(args.elf, args.seed), args.seed))
    print('world_findFreeSpot, authored terrain and boxes: %d comparisons matched (seed %d)'
          % (free_spot_cases(args.elf, args.seed), args.seed))
    print('OniBall_ctor, authored creatures: %d comparisons matched (seed %d)' % (oniball_cases(args.elf, args.seed), args.seed))
    count = nearby_cases(args.elf, args.seed)
    print('Goblin_onNearbyEvent, authored Goblins: %d comparisons matched; requests %s (seed %d)'
          % (count, dict(sorted(nearby_cases.hits.items(), key=str)), args.seed))
    count, _found, two = chain_cases(args.elf, args.seed, None, tables)
    print('creature chain, empty balance table: %d comparisons matched over %d constructions, '
          '%d with two shared draws (seed %d)' % (count, 6 * len(INDICES), two, args.seed))
    if args.disc:
        count, found, two = chain_cases(args.elf, args.seed, balance_entry(args.disc), tables)
        print('creature chain, the disc\'s balance table: %d comparisons matched over %d constructions, '
              '%d with two shared draws; the type name was found in %d of %d (seed %d)'
              % (count, 6 * len(INDICES), two, found, 6 * len(INDICES), args.seed))


if __name__ == '__main__':
    main()
