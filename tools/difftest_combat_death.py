#!/usr/bin/env python3
"""difftest_combat_death.py - compare tools/ref_combat_death.py with the game's own code:
Skeleton_shatter, creature_bossRank, player_getSkillRank and Player slot 39,
player_giveExp, anim_findTrack; and rerun tools/difftest_items.py's loot_generateDrops
comparison with the original's coverage recorded.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_combat_death.py [path/to/SLUS_209.73] [--seed N] [--cases N]
                                            [--loot N] [--quick] [-v] [--trace-first]

    --loot N   loot_generateDrops calls (default 300; 0 skips them): difftest_items.py's
               own 'loot' worker (library string routines replaced, a quarter of the calls
               with seeds searched so the rare rolls succeed), with every executed pc of
               the body recorded

What is compared
    tools/difftest_weapon_holder.py's MiniRig: the six bodies run for real (the C library
    too: libc_strcasecmp is the original's), each called directly on made-up creatures,
    player records (levels 0-80, experience around the thresholds of the game's own
    table, skill lists of every length), animation states and boss names (the game's own
    name strings, their copies in mixed case, and others).  Callbacks (recording stubs
    answered by a scripted world): pool_new, PhProp_ctor2 (its three stack arguments
    read at the call), obj_getPropStr, player_recalcStats, net_isLocalSlot, res_find,
    sound_playOnObject, text_lookup, hud_showMessage.  The model runs first on a
    copy-on-write view; equal must be: the callbacks with their arguments, every byte
    stored outside the stack, the shared seed with its draw count, the result.
"""
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_death as D                    # noqa: E402
import difftest_weapon_holder as DW             # noqa: E402
from difftest_weapon_holder import Answer, MiniRig, Tally, f32, regs, vec_at   # noqa: E402

M32, M64 = RC.M32, RC.M64
OPTIONS = DW.OPTIONS
OPTIONS.update({'cases': 8000, 'loot': 300})


def stack_args(e):
    sp = e.r[29] & M32
    return (('mask', e.mem.u64(sp)), e.mem.u32(sp + 8), e.mem.u32(sp + 0x10))


STUBS = {
    'pool_new': (0x14FDB8, regs(4), None),
    # (scale f12, block, position, facing, model, anim state, lump, two words; stack: part
    # mask (64 bits), 0x107, 0)
    'PhProp_ctor2': (0x1556C0, lambda e: (e.f[12] & M32, e.r[4] & M32, vec_at(e, e.r[5] & M32))
                     + tuple(e.r[i] & M32 for i in range(6, 12)) + stack_args(e), None),
    'obj_getPropStr': (0x14F4C0, regs(4, 5, 6), None),
    'player_recalcStats': (0x1B6458, lambda e: (), None),
    'net_isLocalSlot': (0x13E150, regs(4), None),
    'res_find': (0x17365C, regs(4, 5), None),
    'sound_playOnObject': (0x214230, lambda e: (e.f[12] & M32, e.r[4] & M32, e.r[5] & M32), None),
    'text_lookup': (0x173C84, regs(4), None),
    'hud_showMessage': (0x1D92A0, regs(4, 5, 6, 7), None),
}


class World:
    def __init__(self, emu, rng):
        self.emu, self.mem, self.rng = emu, emu.mem, rng

    def build(self):
        emu, mem, rng = self.emu, self.mem, self.rng
        self.creature = emu.alloc(0x400)
        self.defs = [emu.alloc(0x40) for _ in range(2)]
        for d in self.defs:
            for k in range(0, 0x40, 4):
                mem.w32(d + k, rng.getrandbits(32))
        self.block = emu.alloc(0x248)
        # boss names: the game's strings (read from your executable at run time), copies
        # in other cases, and other names
        game = [a for a in D.BOSS_NAMES + tuple(n for pair in D.BOSS_PAIRS for n in pair) + D.BOSS_LAST]
        self.names = list(game)
        for a in game:
            text = self.raw(a)
            for variant in (text.upper(), text.lower(), bytes(c ^ 0x20 if 0x41 <= (c | 0x20) <= 0x5A and rng.random() < 0.5
                                                                else c for c in text)):
                self.names.append(self.text(variant))
            self.names.append(self.text(text + b'x'))
            self.names.append(self.text(text[:-1]))
        for other in (b'gnoll', b'Skeleton', b'rat', b'', b'AntQueen2'):
            self.names.append(self.text(other))
        self.values = [self.text(self.raw(v)) for _n, v in D.BOSS_PAIRS] + \
            [self.text(self.raw(v).upper()) for _n, v in D.BOSS_PAIRS] + [self.text(b''), self.text(b'nobody')]
        self.state = emu.alloc(0x200)
        self.player = emu.alloc(0x400)

    def raw(self, addr):
        out = bytearray()
        while self.mem.u8(addr + len(out)):
            out.append(self.mem.u8(addr + len(out)))
        return bytes(out)

    def text(self, value):
        a = self.emu.alloc(len(value) + 1)
        self.mem.write(a, value + b'\0')
        return a

    def respond(self, name, args, rng):
        if name == 'pool_new':
            return Answer(self.block if rng.random() < 0.8 else 0)
        if name == 'obj_getPropStr':
            return Answer(rng.choice(self.values))
        if name == 'net_isLocalSlot':
            return Answer(rng.choice((0, 1, 1)))
        if name in ('res_find', 'text_lookup'):
            return Answer(rng.choice((0, 0x00C01000, 0x00C02000)))
        return Answer(0)


SKILL_IDS = (0x3B, 2, 0x53, 0x5D, 1, 0, 0x7FFF, 0x8000, 0xFFFE, 0x40)


def scenario(world, rng, mem, case):
    """One call: (key, entry, args, model runner, result kind)."""
    roll = rng.random()
    c = world.creature
    if roll < 0.2:
        group = rng.choice((1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 0, 9, M32))
        bits = 0
        for m in D.SHATTER_GROUPS.get(8) + D.SHATTER_GROUPS[2] + D.SHATTER_GROUPS[3]:
            if rng.random() < 0.5:
                bits |= m
        mem.w64(c + 0x220, rng.choice((bits, bits, M64, 0, rng.getrandbits(64))))
        mem.w32(c + 0x24, rng.choice(world.defs))
        for k in range(3):
            mem.w32(c + 0x10 + 4 * k, f32(rng.uniform(-3000, 3000)))
        mem.w16(c + 0x38, rng.randrange(0x10000))
        return 'Skeleton_shatter', D.SHATTER, (c, group), lambda m: m.skeleton_shatter(c, group), 'n'
    if roll < 0.45:
        mem.w32(c + 0xC, rng.choice((0x20, 0x20, 0x20, 0x60, 0, 0x1)))
        mem.w32(c + 0x34, rng.choice(world.names) if rng.random() < 0.92 else 0)
        mem.w64(c + 0xA8, rng.getrandbits(8))
        return 'creature_bossRank', D.BOSS_RANK, (c,), lambda m: m.boss_rank(c), 'i'
    if roll < 0.65:
        slot = rng.randrange(4)
        rec = D.record(slot)
        n = rng.choice((0, 1, 2, 5, 10, 30))
        ids = [rng.choice(SKILL_IDS) for _ in range(n)]
        for k, ident in enumerate(ids):
            mem.w16(rec + D.REC_SKILLS + 4 * k, ident)
            mem.w16(rec + D.REC_SKILLS + 4 * k + 2, rng.choice((0, 1, 5, 20, 0xFFFF, 0x8000)))
        mem.w16(rec + D.REC_SKILLS + 4 * n, 0xFFFF)
        skill = rng.choice(SKILL_IDS + (0xFFFFFFFF, 0xFFFF8000, 0x3B))
        if rng.random() < 0.3:
            p = world.player
            mem.w32(p + 0x3C8, slot)
            return 'Player_slot39', D.PLAYER_SLOT39, (p, skill), lambda m: m.player_slot39(p, skill), 'i'
        return 'player_getSkillRank', D.SKILL_RANK, (slot, skill), lambda m: m.get_skill_rank(slot, skill), 'i'
    if roll < 0.85:
        slot = rng.randrange(4)
        rec = D.record(slot)
        level = rng.choice((0, 1, 1, 2, 5, 6, 15, 16, 25, 26, 35, 36, 50, 79, 80, rng.randrange(81)))
        mem.w8(rec + D.REC_LEVEL, level)
        table = [mem.s32(D.G_EXP_TABLE + 4 * k) for k in range(81)]
        here = table[level]
        exp = rng.choice((0, here - 1, here - rng.randrange(1, 3000), max(here - 1, 0) // 2, table[max(level - 1, 0)]))
        mem.w32(rec + D.REC_EXP, exp & M32)
        amount = rng.choice((0, 1, rng.randrange(3000), rng.randrange(60000), table[80], 0x7FFFFFFF,
                             (here - exp) & M32, -5 & M32))
        mem.w32(rec + D.REC_SKILL_POINTS, rng.randrange(200))
        mem.w8(rec + D.REC_STAT_POINTS, rng.randrange(256))
        for off in (D.REC_HP, D.REC_MAX_HP, D.REC_MANA, D.REC_MAX_MANA):
            mem.w32(rec + off, f32(rng.choice((0.0, 50.0, 300.0, -1.0, 0.5))))
        if rng.random() < 0.05:
            mem.w32(rec + D.REC_HP, 0x80000000)          # -0.0
        return 'player_giveExp', D.GIVE_EXP, (slot, amount), lambda m: m.give_exp(slot, amount), 'n'
    state = world.state
    count = rng.choice((0, 1, 2, 4, 6, 8, 0xFF, 0x80))
    mem.w8(state + 4, count)
    clips = [rng.choice((0x00C00100, 0x00C00200, 0x00C00300, 0)) for _ in range(8)]
    for k, clip in enumerate(clips):
        mem.w32(state + 8 + 32 * k, clip)
    st = rng.choice((state, state, 0))
    clip = rng.choice((0x00C00100, 0x00C00200, 0x00C00300, 0x00C00400, 0))
    return 'anim_findTrack', D.FIND_TRACK, (st, clip), lambda m: m.find_track(st, clip), 'i'


def run(elf, seed, cases, tally):
    world = World.__new__(World)
    real = {a for n, a in D.EXECUTED.items() if n not in D.EXECUTED_ELSEWHERE}
    rig = MiniRig(elf, real, STUBS, world)
    World.__init__(world, rig.emu, random.Random(seed))
    world.build()
    mem, rng = rig.emu.mem, world.rng
    for case in range(cases):
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        key, entry, args, runner, kind = scenario(world, rng, mem, case)
        result = rig.compare(entry, args, D.Model, runner, seed * 1000003 + case, ret_kind=kind)
        tally.add(key, result, lambda: '%s%s' % (key, tuple('%x' % (a & M32) for a in args)))
    return rig


def run_loot(elf, seed, count):
    """difftest_items' loot worker with the original's pcs inside loot_generateDrops
    recorded; returns (calls, mismatches, counters, pcs)."""
    import difftest_items as DI
    pcs = set()
    saved = DI.original

    def traced(*a, **k):
        o = saved(*a, **k)
        for pc in range(D.LOOT, D.BODY_END[D.LOOT], 4):
            if pc not in o.emu.hooks:
                o.emu.hooks[pc] = lambda emu, pc=pc: pcs.add(pc)
        return o
    DI.original = traced
    try:
        n, bad, counters = DI.w_loot(elf, seed, count, (0.25, True))
    finally:
        DI.original = saved
    return n, bad, counters, pcs


def main(argv):
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('--seed', '--cases', '--loot'):
            OPTIONS[a[2:]] = int(args[i + 1], 0)
            i += 1
        elif a == '--quick':
            OPTIONS['quick'] = True
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        i += 1
    elf = DW.find_elf(args)
    if not DW.check_elf(elf, 'difftest_combat_death'):
        return 0
    C.set_fpu('ps2')
    started = time.time()
    cases = OPTIONS['cases'] // 10 if OPTIONS['quick'] else OPTIONS['cases']
    loot = OPTIONS['loot'] // 10 if OPTIONS['quick'] else OPTIONS['loot']
    tally = Tally('death')
    trace, rig = set(), None
    for k in range(2):
        rig = run(elf, OPTIONS['seed'] + k, cases // 2, tally)
        trace |= rig.trace
        if rig.unknown:
            print('FAIL  calls to addresses neither real nor stubbed: %s' % {hex(a): n for a, n in rig.unknown.items()})
            tally.bad.setdefault('unknown', []).append(str(rig.unknown))
    ok = tally.report() and 'unknown' not in tally.bad
    names = {v: k for k, v in D.EXECUTED.items()}
    bodies = sorted((a, e) for a, e in D.BODY_END.items() if a != D.LOOT)
    lines = DW.coverage_lines(trace, rig.emu.mem, bodies, names)
    if loot:
        n, bad, counters, pcs = run_loot(elf, OPTIONS['seed'], loot)
        ok = ok and not bad
        print('%s  %-36s %7d calls  %d mismatches  (%s)' % ('PASS' if not bad else 'FAIL', 'loot_generateDrops', n,
                                                           len(bad), ', '.join('%s %d' % kv for kv in counters.items())))
        if bad and OPTIONS['verbose']:
            for line in bad[:3]:
                print('        ' + line[:1000])
        lines += DW.coverage_lines(pcs, rig.emu.mem, [(D.LOOT, D.BODY_END[D.LOOT])], names)
    DW.print_coverage(lines, OPTIONS['verbose'])
    print('%d calls compared (seed %d), %d shared draws, %d stopped on both sides; %.0f s' % (
        sum(tally.counts.values()), OPTIONS['seed'], tally.draws, tally.both, time.time() - started))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
