#!/usr/bin/env python3
"""difftest_loot_and_pickups.py - death drops, ground items and pickup, US v2.00.

Runs original EE code in tools/ee_emu.py. Five sections:

  drop      Creature_dropLoot 0x10f2c8: every branch (dead-loaded flag, noloot,
            eleven exact-class tests, boss rank 2 and 1, tint, the MiniBoss gate)
            with loot_generateDrops 0x100d54 replaced by a recorder.
  scale     level_monsterLevelTimes0_4 0x1ebf20 and ...TimesDifficulty 0x1ebf70,
            and the gold amounts of the real loot_generateDrops, against
            ref_items (unchanged).
  ctor2     the seven ItemProp_ctor2 0x1590ec call sites (static census), the
            overweight givePlayerItem 0x145a88 drop with a real pool block, the
            recorded constructor inputs replayed into the real constructor, and
            the resulting ground item picked up through ItemProp slot 14 0x159b38.
  compare   givePlayerItem against itemprop_tryPickup 0x154dbc on the same bag
            and load states, both through the real inventory_giveItem 0x1c1868.
  autochest AutoChest_dropLoot 0x23ba3c with no placed properties.

Disclosed stubs are listed per section (STUBS, the recorders, the scripted own
generator). Item descriptor text is read from the executable at run time and is
never printed; output is addresses, counts and raw floats only.

  python3 tools/difftest_loot_and_pickups.py local/SLUS_209.73 --seed 20973
  python3 tools/difftest_loot_and_pickups.py local/SLUS_209.73 --seed 7
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, float_to_raw as bits, raw_to_float as number  # noqa: E402
import ref_items as R  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
M32 = 0xFFFFFFFF
SHARED = 0x404464
NUM_PLAYERS, PVP_A, PVP_B = 0x4d8ae0, 0x4f711c, 0x4f7120
LEVEL, DIFFICULTY = 0x4f714c, 0x4f719c
PLAYERS, STRIDE = 0x4d8af0, 0x4c30
P_LOAD, P_LIMIT, P_BAGS, BAG, P_OBJECT = 0x120, 0x124, 0x130, 0x1208, 0x43d8
ALIVE = 0x4f8440

DROP, GENERATE, OWN_RAND = 0x10f2c8, 0x100d54, 0x1509d0
CLASS_TYPES = (0x3c4888, 0x3c3c78, 0x3cc938, 0x3cca98, 0x3c9330, 0x3cc568,
               0x3ca4ac, 0x3cba24, 0x3cc29c, 0x3cb1a0, 0x3ccd64)
NOLOOT_KEY = 0x52ffd8          # key string address; its text is read at run time
RANK2_NAME = 0x52fd48          # first entry of creature_bossRank's name list
COMMON = (36.0, 2.0, 1.6, 0.6, 1.4, 0.25)   # the common death-helper arguments

GIVE, GIVE_END = 0x145a88, 0x145d20
CTOR2, CTOR3, PHPROP_CTOR = 0x1590ec, 0x1592bc, 0x155a0c
POOL_NEW, GIVE_ITEM, TRY_PICKUP, ITEM_INTERACT = 0x14fdb8, 0x1c1868, 0x154dbc, 0x159b38
SCR_GET_ADDR, SCR_GET_STRING = 0x1414a8, 0x141650
NATIVE_TABLE = 0x403370
CTOR2_SITES = (0x145c78, 0x145cd0, 0x145ef0, 0x146130, 0x146234, 0x1c24a4, 0x1c47f4)
# Services that are not the subject: recording stubs returning 0.
STUBS = {
    0x1b6458: 'player_recalcStats', 0x1ba5f8: 'player_countPotions',
    0x1b2470: 'player_resetIdleAnim', 0x1c3f08: 'inventory_selectIdleAnim',
    0x1ed778: 'vars_get', 0x1ed854: 'vars_set', 0x173c84: 'text_lookup',
    0x1d9830: 'hud_showHelpMessage', 0x1d9954: 'hud_showPlayerNotice',
    0x13e150: 'net_isLocalSlot', 0x2134e8: 'sound_playSample',
    0x214230: 'sound_playOnObject', 0x214428: 'sound_playAtPos',
}
TOKEN = 0x7000
LIBC = frozenset(range(0x3a5000, 0x3cc000, 4))
# Real code on the pickup side; every other callee is an auto-recorded stub returning 0
# (sounds, the script hook, HUD notices, recalcStats), listed in the log.
PICKUP_REAL = frozenset({ITEM_INTERACT, TRY_PICKUP, GIVE_ITEM, 0x1bec10, 0x1b6338,
                         0x103e08, 0x108924}) | LIBC
F_BIG = 0x461c3c00             # 9999.0, the original load cap

CHECKS = []


def check(ok, what):
    CHECKS.append((bool(ok), what))
    print('%s  %s' % ('PASS' if ok else 'FAIL', what))


def calls(emu, target):
    return [c for c in emu.calls if c.target == target]


def raw(values):
    return tuple(bits(v) if isinstance(v, float) else v for v in values)


def vector(emu, address, values):
    for i, v in enumerate(values):
        emu.mem.w32(address + 4 * i, bits(v))


def floats(emu, address, count=3):
    return tuple(number(emu.mem.u32(address + 4 * i)) for i in range(count))


def rec(slot):
    return PLAYERS + slot * STRIDE


def cell(slot, bag, index):
    return rec(slot) + P_BAGS + bag * BAG + index * 0x48


def bag_count(emu, slot, bag):
    return emu.mem.s32(rec(slot) + P_BAGS + bag * BAG + 0x1200)


# --------------------------------------------------------------------------------------
# drop: Creature_dropLoot
# --------------------------------------------------------------------------------------
def drop_run(elf, seed, players=1, a8=0, c=0x20, name=0, tint=0, props=(), pvp_b=0,
             getter=None, draws=(), caller=COMMON, extra=None):
    emu = EE(elf)
    emu.mem.w32(SHARED, seed)
    emu.mem.w32(NUM_PLAYERS, players)
    emu.mem.w32(PVP_B, pvp_b)
    obj, vt, pos, type_fn = emu.alloc(0x600), emu.alloc(0x40), emu.alloc(16), emu.alloc(16)
    emu.mem.w32(obj + 0x48, vt)
    emu.mem.w32(vt + 4, type_fn)
    emu.mem.w64(obj + 0xa8, a8)
    emu.mem.w32(obj + 0xc, c)
    emu.mem.w32(obj + 0x34, name)
    emu.mem.w8(obj + 0xa0, tint)
    for offset, value in (extra or {}).items():
        emu.mem.w32(obj + offset, value)
    if props:
        table = emu.alloc(4 * (len(props) + 1))
        for i, text in enumerate(props):
            s = emu.alloc(len(text) + 1)
            emu.mem.write(s, text + b'\0')
            emu.mem.w32(table + 4 * i, s)
        emu.mem.w32(obj + 0x2c, table)
    if getter is None:
        # A type object of no listed class: +0 is its name, compared by 0x3b1250.
        descriptor, label = emu.alloc(16), emu.alloc(16)
        emu.mem.write(label, b'probe-only-type\0')
        emu.mem.w32(descriptor, label)
        type_object = descriptor
    else:
        type_object = emu.call(getter) & M32
    emu.stub(type_fn, ret=type_object, name='slot1_type')
    queue = list(draws)
    used = []

    def own(m):
        assert m.r[4] & M32 == obj
        value = queue.pop(0)
        used.append(value)
        return value

    emu.stub(OWN_RAND, function=own, name='GameObject_rand')
    log = []

    def generate(m):
        log.append((floats(m, m.r[4]), m.r[5] & M32, m.r[6] & M32, m.r[7] & M32,
                    tuple(m.f[12:18])))

    emu.stub(GENERATE, function=generate, name='loot_generateDrops')
    vector(emu, pos, (10.0, 20.0, 30.0))
    filt = emu.alloc(16)
    emu.reset_log()
    emu.call(DROP, obj, pos, 0x1234, filt, fargs=caller)
    return emu, log, used, filt


def ref_drop(players, a8, c, name, tint, noloot, pvp_b, draws, filt, caller=COMMON):
    """Creature_dropLoot as read at 0x10f2c8-0x110718 (non-class creatures)."""
    if a8 & 0x100000000 or (noloot and not pvp_b):
        return []
    rank = 0 if not c & 0x20 else 2 if name else (a8 & 1)
    z, s, gs, gc, q, ic = raw(caller)
    out, it = [], iter(draws)

    def one(args, f=0, force=0):
        out.append((args, f, force))
    if rank == 2:
        one((z, s, gs, gc, q, ic), filt)
        one(raw((caller[0], caller[1], 4.0, 1.0, 6.0, 2.0)))
        one(raw((caller[0], caller[1], 5.0, 1.0, 7.0, 2.0)))
        for _ in range(players):
            one(raw((caller[0], caller[1], 0.0, 0.0, 8.5, 2.0)), 0, int(next(it) < 0x8000))
    elif rank == 1:
        one(raw((caller[0], caller[1], 4.0, 1.0, 3.0, 1.5)))
        one(raw((caller[0], caller[1], 5.0, 1.0, 5.0, 1.5)))
        for _ in range(players):
            one(raw((caller[0], caller[1], 0.0, 0.0, 7.0, 1.5)), 0, int(next(it) < 0x4000))
    if tint:
        gs, q = R.fmul(gs, bits(3.0)), R.fmul(q, bits(4.0))
    if not a8 & 1:
        one((z, s, gs, gc, q, ic), filt)
    return out


def shape(log):
    return [(args, f, force) for _pos, _angle, f, force, args in log]


def drop_cases(elf, seed):
    emu = EE(elf)
    sites = [a for a in range(0x100000, 0x3c0000, 4)
             if emu.mem.u32(a) == (3 << 26) | (DROP >> 2)]
    check(len(sites) == 49, 'Creature_dropLoot has %d jal sites (49 expected)' % len(sites))
    key = emu.mem.cstr(NOLOOT_KEY).encode('latin-1')
    cases = 0
    grid = []
    for players in (1, 2, 4):
        grid += [dict(players=players), dict(players=players, tint=1),
                 dict(players=players, a8=1, c=0),
                 dict(players=players, a8=1, draws=[0x3fff, 0x4000, 0, 0xffff][:players]),
                 dict(players=players, name=RANK2_NAME,
                      draws=[0x7fff, 0x8000, 0, 0xffff][:players]),
                 dict(players=players, name=RANK2_NAME, tint=1, draws=[0x8000] * players),
                 dict(players=players, name=RANK2_NAME, a8=1, draws=[0] * players),
                 dict(players=players, name=RANK2_NAME, c=0)]
    grid += [dict(a8=0x100000000), dict(a8=0x100000000, name=RANK2_NAME),
             dict(props=(key + b'=1',)), dict(props=(key + b'=1',), pvp_b=1),
             dict(props=(key + b'=0',)), dict(props=(key + b'=1',), name=RANK2_NAME)]
    for case in grid:
        rank = case.get('name') or case.get('a8', 0) & 1
        if 'draws' not in case and rank and case.get('c', 0x20) & 0x20 \
                and not case.get('a8', 0) & 0x100000000 and not case.get('props'):
            continue
        noloot = any(p.endswith(b'=1') for p in case.get('props', ()))
        emu, log, used, filt = drop_run(elf, seed, **case)
        want = ref_drop(case.get('players', 1), case.get('a8', 0), case.get('c', 0x20),
                        case.get('name', 0), case.get('tint', 0), noloot,
                        case.get('pvp_b', 0), case.get('draws', ()), filt)
        same_pos = all(p == (10.0, 20.0, 30.0) and angle == 0x1234 for p, angle, *_ in log)
        ok = shape(log) == want and same_pos and used == list(case.get('draws', ()))
        label = ' '.join('%s=%s' % (k, hex(v) if isinstance(v, int) else len(v))
                         for k, v in sorted(case.items()))
        check(ok, 'dropLoot %s -> %d calls, forced %s' % (label, len(log), [x[3] for x in log]))
        cases += 1
    # The eleven exact-class branches: record and lock; none makes the ordinary call
    # and none applies the tint. Class index 0 and 1 are also checked by hand reading.
    # Class 5 is taken only with creature flag +0xa8 bit 0, class 6 only with a nonzero
    # word at +0x3d8 (0x10fb7c, 0x10fcfc); otherwise both fall through to the next tests.
    gates = {5: dict(a8=1), 6: dict(extra={0x3d8: 1})}
    by_class = {}
    for index, getter in enumerate(CLASS_TYPES):
        for gated in ((True, False) if index in gates else (True,)):
            setup = gates.get(index, {}) if gated else {}
            results = []
            for tint in (0, 1):
                for players in (1, 3):
                    draws = [0x7fff, 0x8000, 0x3fff, 0x4000, 0, 0xffff][:players]
                    emu, log, used, filt = drop_run(elf, seed, players=players, tint=tint,
                                                    getter=getter, draws=draws, **setup)
                    results.append((players, tint, shape(log), used, filt))
            if not gated:
                ok = all(r[2] == ref_drop(r[0], 0, 0x20, 0, r[1], False, 0, (), r[4])
                         for r in results)
                check(ok, 'class branch %d without its gate falls through to the generic '
                          'call (tint applied)' % index)
                cases += 1
                continue
            by_class[index] = results
            tint_free = results[0][2] == results[2][2] and results[1][2] == results[3][2]
            ordinary = any(e == (raw(COMMON), results[0][4], 0) for e in results[0][2][1:])
            check(tint_free and not ordinary and len(results[1][2]) == len(results[0][2]) + 2,
                  'class branch %d (type getter 0x%x): %d/%d calls for 1/3 players, tint '
                  'ignored, no trailing ordinary call' % (index, getter, len(results[0][2]),
                                                         len(results[1][2])))
            cases += 1
    c0 = by_class[0][1][2]
    z, s = raw(COMMON[:2])
    check(c0[:3] == [(raw(COMMON), c0[0][1], 0), (raw((36.0, 2.0, 4.0, 1.0, 6.0, 2.0)), 0, 0),
                     (raw((36.0, 2.0, 5.0, 1.0, 7.0, 2.0)), 0, 0)]
          and [e[0] for e in c0[3:]] == [raw((36.0, 2.0, 0.0, 0.0, 8.0, 2.0))] * 3
          and [e[2] for e in c0[3:]] == [1, 0, 1] and by_class[0][1][3] == [0x7fff, 0x8000, 0x3fff],
          'class 0: caller call with filter, (4,1,6,2), (5,1,7,2), per player (0,0,8,2) '
          'forced when own draw < 0x8000')
    c1 = by_class[1][1]
    check([e[2] for e in c1[2][3:]] == [1, 1, 1] and c1[3] == [],
          'class 1: per-player call always forced, no own draw')
    for index, results in by_class.items():
        _p, _t, entries, used, _f = results[1]
        print('LOCK  class %d players 3: %s draws %d' % (index, [
            ('%s' % '/'.join('%g' % number(a) for a in args[2:]), int(bool(f)), force)
            for args, f, force in entries], len(used)))
    return cases


# --------------------------------------------------------------------------------------
# scale: level factors and gold amounts
# --------------------------------------------------------------------------------------
def scale_cases(elf, seed):
    cases = 0
    emu = EE(elf)
    for level in (1.0, 4.0, 4.5, 5.0, 22.0, 60.0):
        for difficulty in range(1, 6):
            for pvp_b in (0, 1):
                emu.mem.w32(LEVEL, bits(level))
                emu.mem.w32(DIFFICULTY, difficulty)
                emu.mem.w32(PVP_B, pvp_b)
                game = R.Game(difficulty=difficulty, pvp_b=pvp_b, level=level)
                emu.call(0x1ebf20)
                a = emu.f[0]
                emu.call(0x1ebf70)
                b = emu.f[0]
                ok = a == game.level_times_0_4() and b == game.level_times_difficulty()
                if not ok:
                    check(False, 'level factor L=%g d=%d pvpB=%d' % (level, difficulty, pvp_b))
                cases += 1
    check(True, 'level factors 0x1ebf20 / 0x1ebf70 equal ref_items on %d states' % cases)
    tables = R.Tables(elf)
    libc = LIBC
    gold_cases = 0
    seen = {}
    for players in (1, 2, 4):
        for level in (1.0, 10.0, 22.0, 40.0):
            for difficulty in (1, 5):
                for pvp_a in (0, 1):
                    for k in range(6):
                        # The start seed depends on everything but the difficulty and the
                        # PvP flag, so those two can be compared on equal seeds.
                        start = (seed * 0x19660d + k * 0x9e3779b1 + players * 7919
                                 + int(level) * 104729) & M32
                        emu = EE(elf)
                        emu.follow = {GENERATE, 0x1ebf20, 0x1ebf70} | libc
                        emu.mem.w32(SHARED, start)
                        emu.mem.w32(NUM_PLAYERS, players)
                        emu.mem.w32(LEVEL, bits(level))
                        emu.mem.w32(DIFFICULTY, difficulty)
                        emu.mem.w32(PVP_A, pvp_a)
                        got = []
                        emu.stub(0x100974, function=lambda m: got.append(m.r[5] & M32 if
                                 m.r[5] & 0x80000000 == 0 else (m.r[5] & M32) - (1 << 32)),
                                 name='loot_spawnGold')
                        pos = emu.alloc(16)
                        emu.call(GENERATE, pos, 0, 0, 0,
                                 fargs=(36.0, 2.0, 1.6, 1.0, 1.4, 0.0))
                        game = R.Game(num_players=players, difficulty=difficulty, pvp_a=pvp_a,
                                      level=level)

                        class World(R.World):
                            def spawn_item(self, kind, item, rng):
                                return False
                        world = World()
                        R.loot_generate_drops(tables, game, R.Rng(start), world, bits(1.6),
                                              bits(1.0), bits(1.4), 0)
                        want = [v for k2, v in world.drops if k2 == 'gold']
                        if got != want:
                            check(False, 'gold P=%d L=%g d=%d pvpA=%d start %08x: %r vs %r'
                                  % (players, level, difficulty, pvp_a, start, got, want))
                        seen.setdefault((players, level, pvp_a, k), []).append(tuple(got))
                        gold_cases += 1
    same = all(len(set(v)) == 1 for v in seen.values())
    check(gold_cases and same, 'gold amounts of 0x100d54 equal ref_items on %d runs; the two '
          'difficulties give identical gold for the same seed' % gold_cases)
    check(all(not v[0] for (p, l, a, k), v in seen.items() if a),
          'PvP mode A: no gold roll reaches loot_spawnGold')
    # Per-roll range as a client table (goldScale 1.6), from the reference.
    for players in (1, 2):
        for level in (1.0, 10.0, 22.0, 40.0):
            gs = bits(1.6)
            if players >= 2:
                gs = R.float_times_double(gs, tables.gold_scale_multiplayer)
            gs = R.fmul(gs, R.Game(level=level).level_times_0_4())
            lo = R.ftrunc(R.fmul(R.fmul(R.fint(40), gs), 0x3d0f5c28))
            hi = R.ftrunc(R.fmul(R.fmul(R.fint(79), gs), 0x3d0f5c28))
            print('TABLE gold per roll, goldScale 1.6, players %d, level %g: %d..%d'
                  % (players, level, lo, hi))
    return cases + gold_cases


# --------------------------------------------------------------------------------------
# ctor2: ItemProp_ctor2 sites, the givePlayerItem drop, replay and pickup
# --------------------------------------------------------------------------------------
def writes_reg(word, reg):
    op = word >> 26
    if op == 0:
        return (word >> 11) & 31 == reg and word & 0x3f not in (0x08, 0x18, 0x19, 0x1a, 0x1b)
    if op == 0x1c:
        return (word >> 11) & 31 == reg
    return op in (8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 32, 33, 35, 36, 37, 39, 55) \
        and (word >> 16) & 31 == reg


def is_zero_move(word, reg):
    return word >> 26 == 0 and (word >> 11) & 31 == reg and (word >> 21) & 31 == 0 \
        and (word >> 16) & 31 == 0 and word & 0x3f in (0x21, 0x25, 0x2d)


def census_cases(elf):
    emu = EE(elf)
    found = tuple(a for a in range(0x100000, 0x3c0000, 4)
                  if emu.mem.u32(a) == (3 << 26) | (CTOR2 >> 2))
    check(found == CTOR2_SITES, 'ItemProp_ctor2 jal sites: %s' % ', '.join(map(hex, found)))
    zero = []
    for site in found:
        writer = None
        for addr in [site + 4] + list(range(site, site - 0x60, -4)):
            if writes_reg(emu.mem.u32(addr), 7):
                writer = emu.mem.u32(addr)
                break
        zero.append(writer is not None and is_zero_move(writer, 7))
    check(all(zero), 'every ctor2 site passes a3 (launch flags) = 0')
    handlers = sorted((emu.mem.u32(NATIVE_TABLE + 8 * i + 4), i) for i in range(160)
                      if 0x100000 < emu.mem.u32(NATIVE_TABLE + 8 * i + 4) < 0x400000)
    owner = {}
    for site in found:
        if site < 0x147000:
            owner[site] = max((h, i) for h, i in handlers if h <= site)[1]
    check([owner.get(s) for s in found[:5]] == [53, 53, 54, 55, 55],
          'script sites belong to natives 53, 53, 54, 55, 55')
    pool = [a for a in range(0x100000, 0x3c0000, 4)
            if emu.mem.u32(a) == (3 << 26) | (POOL_NEW >> 2)]
    sizes = []
    for site in found:
        before = max(a for a in pool if a < site)
        sizes.append(site - before < 0x60)
    check(all(sizes), 'each ctor2 site follows a pool_new within 0x60 bytes')
    return 4


def eligible(d):
    return (not d.preset and d.name and 0 <= d.category <= 2
            and ((d.flags >> 11) & 0x1f) == 0 and d.slot != 8
            and not d.flags & (1 << 42) and not d.flags & 0x20000000000
            and not d.flags & 0x100 and not d.flags & 0x1000000000)


def give_machine(elf, seed, players=1, pool=True):
    emu = EE(elf)
    for addr, name in STUBS.items():
        emu.stub(addr, ret=1 if name == 'vars_get' else 0, name=name)
    strings = {}
    emu.stub(SCR_GET_ADDR, function=lambda e: e.mem.w32(e.r[6] & M32, e.r[5] & M32),
             name='scr_getAddr')

    def get_string(e):
        e.mem.write(e.r[4] & M32, strings[e.r[5] & M32] + b'\0')
    emu.stub(SCR_GET_STRING, function=get_string, name='scr_getString')
    emu.mem.w32(NUM_PLAYERS, players)
    emu.mem.w32(SHARED, seed)
    emu.mem.w32(0x4f713c, 0)
    emu.mem.w32(DIFFICULTY, 2)
    emu.mem.w32(0x86b270, 0)
    objects = []
    for slot in range(4):
        r = rec(slot)
        for bag in range(3):
            emu.mem.write(r + P_BAGS + bag * BAG, bytes(BAG))
        for off in range(17):
            emu.mem.w32(r + 0x43f0 + 4 * off, 0)
        emu.mem.w32(r + P_LOAD, 0)
        emu.mem.w32(r + P_LIMIT, F_BIG)
        emu.mem.w32(r + 0x50, 0)
        emu.mem.w8(r + 0x58, 80)
        obj = emu.alloc(0x800)
        emu.mem.w32(obj + 0x3c8, slot)
        vector(emu, obj + 0x10, (100.0 + slot, 200.0, 300.0))
        emu.mem.w32(r + P_OBJECT, obj)
        emu.mem.w32(ALIVE + 4 * slot, slot)
        objects.append(obj)
    state = {'blocks': [], 'ctor2': []}

    def pool_new(e):
        block = emu.alloc(e.r[4] & M32) if pool else 0
        state['blocks'].append((e.r[4] & M32, block))
        return block

    def ctor2(e):
        state['ctor2'].append((e.r[4] & M32, floats(e, e.r[5]), e.mem.read(e.r[6] & M32, 0x48),
                               e.r[7] & M32, e._fresh_call.site if e._fresh_call else None))
    emu.stub(POOL_NEW, function=pool_new, name='pool_new')
    emu.stub(CTOR2, function=ctor2, name='ItemProp_ctor2')
    return emu, strings, objects, state


def give(emu, strings, text, equip=0):
    strings[TOKEN] = text
    params = emu.alloc(16)
    for i, v in enumerate((12, TOKEN, equip, 0)):
        emu.mem.w32(params + 4 * i, v)
    emu.reset_log()
    return emu.call(GIVE, 0x01100000, params, max_steps=20000000) & M32


def item_weight(emu, slot, item):
    emu.call(0x1b6338, slot, item, max_steps=2000000)
    return emu.f[0]


def replay_ctor2(elf, seed, recorded):
    """The recorded ctor2 inputs, run through the real constructor. Resource lookup
    and model bounds are synthetic (as in difftest_loot_drop.constructor_cases)."""
    _block, pos, record, flags, _site = recorded
    emu = EE(elf)
    emu.follow = {0x14cb10, 0x153e54, 0x153ac0, 0x1541a0, 0x155110, OWN_RAND, 0x3b868c, 0x1083f8}
    emu.mem.w32(SHARED, seed)
    obj, p, item = emu.alloc(0x190), emu.alloc(16), emu.alloc(0x48)
    vector(emu, p, pos)
    emu.mem.write(item, record)
    handles = iter((0x710000, 0x720000))
    emu.stub(0x17365c, function=lambda m: next(handles, 0), name='res_find')

    def bounds(m):
        for pointer, value in zip(m.r[6:12], (-2, -3, -4, 4, 5, 8)):
            m.mem.w32(pointer, value)
    emu.stub(0x179400, function=bounds, name='model_getBounds')
    emu.call(CTOR2, obj, p, item, flags)
    return emu, obj


def ctor2_cases(elf, seed):
    cases = census_cases(elf)
    tables = R.Tables(elf)
    defs = [d for d in tables.defs if eligible(d)]
    heavy = next(d for d in defs if d.weight != 0 and d.count == 1 and d.category == 1)
    hb = heavy.category
    # 1. limit 0: the gift becomes one ctor2 call at the player object's position.
    emu, strings, objects, state = give_machine(elf, seed)
    emu.mem.w32(rec(0) + P_LIMIT, 0)
    v0 = give(emu, strings, heavy.name)
    bag_writes = [w for w in emu.writes if cell(0, hb, 0) <= w[1] < cell(0, hb, 64)]
    c2 = state['ctor2']
    check(v0 == 0 and bag_count(emu, 0, hb) == 0 and not bag_writes
          and state['blocks'] == [(0x190, state['blocks'][0][1])]
          and len(c2) == 1 and c2[0][0] == state['blocks'][0][1]
          and c2[0][1] == (100.0, 200.0, 300.0) and c2[0][3] == 0 and c2[0][4] == 0x145c78
          and struct.unpack_from('<I', c2[0][2])[0] == heavy.addr,
          'givePlayerItem over the limit: pool_new(0x190), ctor2 at 0x145c78 with the player '
          'object position, the parsed record and flags 0; no bag write; v0 0')
    recorded = c2[0]
    # 2. carried + weight == limit is still a drop (strict <).
    emu, strings, objects, state = give_machine(elf, seed)
    probe = emu.alloc(0x48)
    emu.mem.w32(probe, heavy.addr)
    emu.mem.w16(probe + 4, 1)
    w = item_weight(emu, 0, probe)
    emu.mem.w32(rec(0) + P_LIMIT, w)
    give(emu, strings, heavy.name)
    check(len(state['ctor2']) == 1 and bag_count(emu, 0, hb) == 0,
          'givePlayerItem with load + weight == limit drops it (weight %08x)' % w)
    # 3. no player object: the first alive slot's object supplies the position.
    emu, strings, objects, state = give_machine(elf, seed)
    emu.mem.w32(rec(0) + P_LIMIT, 0)
    emu.mem.w32(rec(0) + P_OBJECT, 0)
    emu.mem.w32(ALIVE, 2)
    give(emu, strings, heavy.name)
    c2 = state['ctor2']
    check(len(c2) == 1 and c2[0][1] == (102.0, 200.0, 300.0) and c2[0][4] == 0x145cd0,
          'null player object: ctor2 at 0x145cd0 uses g_alivePlayers[0] (slot 2) object position')
    # 4. two players over the limit: one ground item each, at their own position.
    emu, strings, objects, state = give_machine(elf, seed, players=2)
    emu.mem.w32(rec(0) + P_LIMIT, 0)
    emu.mem.w32(rec(1) + P_LIMIT, 0)
    give(emu, strings, heavy.name)
    check([c[1][0] for c in state['ctor2']] == [100.0, 101.0],
          'two overweight players: two ground items, one at each player')
    # 5. pool refusal: nothing else happens.
    emu, strings, objects, state = give_machine(elf, seed, pool=False)
    emu.mem.w32(rec(0) + P_LIMIT, 0)
    v0 = give(emu, strings, heavy.name)
    check(v0 == 0 and not state['ctor2'] and bag_count(emu, 0, hb) == 0,
          'pool refusal: no ctor2, nothing in the bag, v0 0 (the gift is lost)')
    # 6. replay the recorded inputs into the real constructor.
    emu, obj = replay_ctor2(elf, seed, recorded)
    flags = emu.mem.u32(obj + 0xc)
    check(emu.mem.u32(obj + 0x48) == 0x511c38 and emu.mem.read(obj + 0x148, 0x48) == recorded[2]
          and flags & 0x102000 == 0x102000 and not flags & 0x1800 and flags & 0x100000
          and floats(emu, obj + 0x10) == recorded[1]
          and len(calls(emu, 0x1541a0)) == 1 and not calls(emu, 0x1682f0)
          and emu.mem.u32(obj + 0x4c) == 0x710000 and emu.mem.u32(obj + 0x50) == 0x720000,
          'replayed ctor2: ItemProp vtable 0x511c38, record at +0x148, flags 0x102000 and '
          'interactable 0x100000, 0x1800 clear, Prop_launch once, no rigid body')
    print('INFO  replayed ctor2: flags %08x, radius %08x, height %08x, timer +0x10e %d, '
          'velocity %s' % (flags, emu.mem.u32(obj + 0x1c), emu.mem.u32(obj + 0x20),
                           emu.mem.s16(obj + 0x10e),
                           ['%08x' % emu.mem.u32(obj + o) for o in (0xfc, 0x100, 0x30)]))
    # 7. pick that ground item up with the use path once the player can carry it.
    emu2, strings, objects, state = give_machine(elf, seed)
    prop = emu2.alloc(0x190)
    emu2.mem.write(prop, emu.mem.read(obj, 0x190))
    destroyed = []
    destructor = emu2.mem.u32(0x511c38 + 12)
    emu2.stub(destructor, function=lambda m: destroyed.append(m.r[4] & M32), name='slot1')
    probe = emu2.alloc(0x48)
    emu2.mem.write(probe, recorded[2])
    w = item_weight(emu2, 0, probe)
    for limit, accepted in ((0, False), (w, True)):
        emu2.mem.w32(rec(0) + P_LIMIT, limit)
        emu2.mem.write(rec(0) + P_BAGS, bytes(BAG))
        emu2.mem.w32(rec(0) + P_LOAD, 0)
        destroyed.clear()
        emu2.follow = PICKUP_REAL
        emu2.reset_log()
        emu2.call(ITEM_INTERACT, prop, 0, max_steps=20000000)
        print('INFO  pickup stubs: %s' % sorted({'%x' % c.target for c in emu2.calls
                                                if c.stubbed and c.target not in LIBC}))
        got = bag_count(emu2, 0, hb) == 1 and emu2.mem.u32(cell(0, hb, 0)) == heavy.addr
        check(got == accepted and destroyed == ([prop] if accepted else [])
              and len(calls(emu2, GIVE_ITEM)) == int(accepted),
              'ground item use-pickup at limit %08x: %s' % (limit, 'taken, prop destroyed'
                                                            if accepted else 'refused, stays'))
    return cases + 8


# --------------------------------------------------------------------------------------
# compare: givePlayerItem against itemprop_tryPickup on the same states
# --------------------------------------------------------------------------------------
def compare_cases(elf, seed):
    tables = R.Tables(elf)
    defs = [d for d in tables.defs if eligible(d)]
    heavy = next(d for d in defs if d.weight != 0 and d.count == 1 and d.category == 1)
    hb = heavy.category
    light = next(d for d in tables.defs if not d.preset and d.name and d.weight == 0 and d.count == 1
                 and not (d.flags >> 11) & 0x1f and not d.flags & 0x100 and d.slot != 8)
    rows = []
    for d, label in ((heavy, 'positive weight'), (light, 'zero weight')):
        emu, strings, objects, state = give_machine(elf, seed)
        probe = emu.alloc(0x48)
        emu.mem.w32(probe, d.addr)
        emu.mem.w16(probe + 4, 1)
        w = item_weight(emu, 0, probe)
        one = bits(1.0)
        states = [('room', 0, 0, R.fadd(w, one)), ('exact', 0, 0, w),
                  ('over', 0, one, w), ('count63', 63, 0, F_BIG), ('count64', 64, 0, F_BIG)]
        if d is light:
            states = [('limit0', 0, 0, 0), ('count63', 63, 0, F_BIG)]
        for name, count, load, limit in states:
            results = []
            for path in ('give', 'pickup'):
                emu, strings, objects, state = give_machine(elf, seed)
                emu.mem.w32(rec(0) + P_BAGS + d.category * BAG + 0x1200, count)
                emu.mem.w32(rec(0) + P_LOAD, load)
                emu.mem.w32(rec(0) + P_LIMIT, limit)
                emu.stub(0x1bec10, name='player_recalcLoad')   # keep the set load
                before = bag_count(emu, 0, d.category)
                if path == 'give':
                    give(emu, strings, d.name)
                    ret = None
                else:
                    item = emu.alloc(0x48)
                    emu.mem.w32(item, d.addr)
                    emu.mem.w16(item + 4, 1)
                    emu.follow = PICKUP_REAL - {0x1bec10}
                    emu.reset_log()
                    ret = emu.call(TRY_PICKUP, 0, item, max_steps=20000000) & M32
                after = bag_count(emu, 0, d.category)
                stored = after > before and emu.mem.u32(
                    cell(0, d.category, before)) == d.addr
                outcome = 'bag' if stored else 'ground' if state['ctor2'] else \
                    'lost' if path == 'give' else 'refused'
                results.append((outcome, ret, len(calls(emu, GIVE_ITEM))))
            rows.append((label, name, results))
    want = {
        ('positive weight', 'room'): ('bag', 'bag'),
        ('positive weight', 'exact'): ('ground', 'bag'),
        ('positive weight', 'over'): ('ground', 'refused'),
        ('positive weight', 'count63'): ('bag', 'refused'),
        ('positive weight', 'count64'): ('lost', 'refused'),
        ('zero weight', 'limit0'): ('bag', 'bag'),
        ('zero weight', 'count63'): ('bag', 'refused'),
    }
    for label, name, results in rows:
        got = (results[0][0], results[1][0])
        check(got == want[(label, name)] and results[1][1] == int(got[1] == 'bag'),
              'compare %s / %s: givePlayerItem %s, tryPickup %s (ret %s)'
              % (label, name, got[0], got[1], results[1][1]))
    # count 64: the give still reaches inventory_giveItem, which refuses at index 64.
    lost = [r for label, name, r in rows if name == 'count64'][0]
    check(lost[0][2] == 1, 'count 64: givePlayerItem calls inventory_giveItem once and '
          'makes no ground item')
    return len(rows)


# --------------------------------------------------------------------------------------
# autochest: AutoChest_dropLoot without placed properties
# --------------------------------------------------------------------------------------
def autochest_cases(elf, seed):
    cases = 0
    expected = [raw((36.0, 2.0, 0.0, 0.0, 5.0, 0x3f733333)),
                raw((36.0, 2.0, 0.0, 0.0, 6.0, 0x3ca3d70a)),
                raw((36.0, 2.0, 0.0, 0.0, 9.0, 0x3ba3d70a))]
    for draw, spawned, marker in ((4999, 'parse', 0), (5000, 'consumable', 0),
                                  (14999, 'consumable', 0), (15000, None, 0),
                                  (0, None, 1)):
        emu = EE(elf)
        emu.mem.w32(SHARED, seed)
        obj = emu.alloc(0x200)
        vector(emu, obj + 0x10, (5.0, 6.0, 7.0))
        emu.mem.w16(obj + 0x38, 0x2345)
        emu.mem.w32(obj + 0xec, marker)
        log, used = [], []

        def generate(m):
            log.append((floats(m, m.r[4]), m.r[5] & M32, m.r[6] & M32, m.r[7] & M32,
                        tuple(m.f[12:18])))

        def own(m, value=draw):
            used.append(value)
            return value
        emu.stub(GENERATE, function=generate, name='loot_generateDrops')
        emu.stub(OWN_RAND, function=own, name='GameObject_rand')
        emu.stub(0x1069b8, name='item_parseDescriptor')
        emu.stub(0x108590, ret=1, name='item_generateConsumable')
        emu.stub(POOL_NEW, ret=0, name='pool_new')
        emu.call(0x23ba3c, obj, max_steps=20000000)
        parses, consumables = calls(emu, 0x1069b8), calls(emu, 0x108590)
        if marker:
            ok = not log and not used
        else:
            ok = ([e[4] for e in log] == expected
                  and all(p == (5.0, 6.0, 7.0) and a == 0x2345 and f == 0 and force == 0
                          for p, a, f, force, _ in log)
                  and used == [draw]
                  and len(parses) == int(spawned == 'parse')
                  and (not parses or (parses[0].args[0] & M32, parses[0].args[2] & M32)
                       == (0x542130, M32))
                  and len(consumables) == int(spawned == 'consumable')
                  and len(calls(emu, POOL_NEW)) == int(spawned is not None))
        check(ok, 'AutoChest no properties, +0xec %d, own draw %d: %d generic rolls, extra %s'
              % (marker, draw, len(log), spawned))
        cases += 1
    return cases


SECTIONS = {'drop': drop_cases, 'scale': scale_cases, 'ctor2': ctor2_cases,
            'compare': compare_cases, 'autochest': autochest_cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('elf', nargs='?', default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'local', 'SLUS_209.73'))
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--only', choices=sorted(SECTIONS))
    args = parser.parse_args()
    with open(args.elf, 'rb') as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    if digest != SHA256:
        sys.exit('unexpected executable %s' % digest)
    total = 0
    for name, function in SECTIONS.items():
        if args.only and name != args.only:
            continue
        cases = function(args.elf, args.seed)
        print('SECTION %s: %d cases' % (name, cases))
        total += cases
    failed = [what for ok, what in CHECKS if not ok]
    print('%s loot-and-pickups seed %d: %d checks, %d failed, %d cases'
          % ('PASS' if not failed else 'FAIL', args.seed, len(CHECKS), len(failed), total))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
