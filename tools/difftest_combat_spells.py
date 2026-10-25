#!/usr/bin/env python3
"""difftest_combat_spells.py - compare the victim finders and the radius damage of
tools/ref_combat_spells.py with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_spells.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                          [--cases N] [-k TEXT] [-v]

The harness is tools/difftest_combat_runtime.py's (World, Rig, compare): for each entry
point the ORIGINAL function runs in tools/ee_emu.py (an instruction interpreter, not a
console) on objects this script scatters; the same inputs go through
ref_combat_spells.QueryModel on a copy-on-write view.  Equal must be: the calls to
everything outside the model in order with their arguments, the bytes stored outside the
stack, the shared seed, the result.

Real: the entry point, math_cos16 / math_sin16, vec2_dotDelta 0x166820 and the C library.
Stubs answered by a seeded script (the same script answers the model): the box query (a
random subset of the scattered objects in random order), slot 20 of the filter or
attacker, damage_apply, and the two handle-list functions handle_insertNode 0x1a19d0 and
handle_addNode 0x1a1980 - the script links its nodes in memory exactly as those functions
do (tools/ref_core.py HandlePool, executed by tools/difftest_core.py), so the original's
own walk of the out list reads what it would read in the game.
"""
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_combat_runtime as DT           # noqa: E402
import ref_combat_spells as S                   # noqa: E402

f32 = DT.f32
Ext = DT.Ext

ENTRIES = {
    'collectInArc': (0x1614F0, 'viii', 3, 'n', 'collect_in_arc', (0x1614F0, 0x1618D4)),
    'collectInSphere': (0x14AB80, 'vii', 1, 'n', 'collect_in_sphere', (0x14AB80, 0x14ACF8)),
    'damageInRadius': (0x161270, 'iviiii', 2, 'n', 'damage_in_radius', (0x161270, 0x1614F0)),
    'dtorHolyStrike': (0x3CF534, 'ii', 0, 'n', 'dtor_holystrike', (0x3CF534, 0x3CF5BC)),
    'dtorSparks': (0x3C5B90, 'ii', 0, 'n', 'dtor_sparks', (0x3C5B90, 0x3C5C14)),
    'dtorProjectile': (0x3C2940, 'ii', 0, 'n', 'dtor_projectile', (0x3C2940, 0x3C29AC)),
    'dtorLightEffect': (0x3C6888, 'ii', 0, 'n', 'dtor_lighteffect', (0x3C6888, 0x3C6904)),
    'dtorSpellWaveOfFlame': (0x3D1BD8, 'ii', 0, 'n', 'dtor_spell_waveofflame', (0x3D1BD8, 0x3D1C4C)),
}
EXTS = {
    'handle_insertNode': Ext(0x1A19D0, 'ppp', 0, 'i'),
    'handle_addNode': Ext(0x1A1980, 'pp', 0, 'i'),
    'GameObject_dtor': Ext(0x14CF90, 'pi', 0, 'n'),
    'light_dtor': Ext(0x14A490, 'pi', 0, 'n'),
    'pool_free': Ext(0x150470, 'p', 0, 'n'),
}
NODE_AREA = 0x400


_BaseWorld = DT.World


class World(_BaseWorld):
    def __init__(self, emu, rng):
        _BaseWorld.__init__(self, emu, rng)
        self.node_area = emu.alloc(0x20 * NODE_AREA)
        self.out = emu.alloc(0x10)
        self.cursor = {}

    def _node(self, view):
        n = self.cursor.get(id(view), 0)
        self.cursor[id(view)] = n + 1
        return self.node_area + 0x20 * (64 + n)

    def on_handle_insertNode(self, args, view, rng):
        """handle_insertNode 0x1a19d0 (head, after, obj), as tools/ref_core.py has it."""
        head, after, obj = args
        node = self._node(view)
        view.poke(node + 0xC, 4, obj)
        view.poke(node + 8, 4, 0)
        if after:
            view.poke(node + 4, 4, after)
            nxt = view.load(after, 4)
            view.poke(node, 4, nxt)
            if nxt:
                view.poke(nxt + 4, 4, node)
            view.poke(after, 4, node)
        else:
            first = view.load(head, 4)
            view.poke(node, 4, first)
            if first:
                view.poke(first + 4, 4, node)
            view.poke(node + 4, 4, head)
            view.poke(head, 4, node)
        return DT.Res(node)

    def on_handle_addNode(self, args, view, rng):
        """handle_addNode 0x1a1980 (head, obj): at the front."""
        head, obj = args
        node = self._node(view)
        first = view.load(head, 4)
        view.poke(node, 4, first)
        if first:
            view.poke(first + 4, 4, node)
        view.poke(node + 4, 4, head)
        view.poke(head, 4, node)
        view.poke(node + 0xC, 4, obj)
        view.poke(node + 8, 4, 0)
        return DT.Res(node)

    def on_world_collectObjectsInBox(self, args, view, rng):
        limit = args[2]
        pool = list(self.everything)
        rng.shuffle(pool)
        found = pool[:rng.randrange(0, min(len(pool), max(limit - 1, 0)) + 1)]
        if found and rng.random() < 0.2:                # duplicates and exact ties
            found.insert(rng.randrange(len(found) + 1), rng.choice(found))
        return DT.Res(0, 0, [found])


def install():
    """Point the round-1 harness at this file's entry points and stubs."""
    DT.ENTRIES = ENTRIES
    DT.EXTS.update(EXTS)
    DT.REAL_OTHER = set(DT.REAL_OTHER) | {0x166820}
    DT.World = World
    DT.T.CombatModel = S.QueryModel             # compare() builds T.CombatModel


def generate(rig, key, rng):
    w, mem = rig.world, rig.emu.mem
    w.cursor = {}
    centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50))
    w.scatter(rng, centre)
    if rng.random() < 0.3:                          # objects exactly on a line / at the centre
        for obj in rng.sample(w.everything, 3):
            mem.wf32(obj + 0x10, centre[0] + rng.choice((0.0, 10.0, -10.0)))
            mem.wf32(obj + 0x14, centre[1] + rng.choice((0.0, 10.0)))
    for obj in w.everything:
        mem.w32(obj + 0xC, mem.u32(obj + 0xC) | rng.choice((0, 0, 0, 0x4, 0x1, 0x200, 0x40)))
    mem.w32(DT.T.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(w.out, 0)
    if rng.random() < 0.3:                          # an out list that already holds nodes
        prev = w.out
        for i in range(rng.randrange(1, 4)):
            node = w.node_area + 0x20 * i
            mem.w32(prev if prev == w.out else prev, node)
            mem.w32(node + 4, prev)
            mem.w32(node + 0xC, rng.choice(w.everything))
            mem.w32(node + 8, 0)
            mem.w32(node, 0)
            prev = node
    pos = (f32(centre[0] + rng.uniform(-30, 30)), f32(centre[1] + rng.uniform(-30, 30)), f32(centre[2]))
    if key == 'collectInArc':
        filt = rng.choice([0, 0] + w.everything)
        arc = f32(rng.choice((-1.0, -1.0, 20.0, 60.0, 90.0, 179.0, 180.0, 270.0, 360.0, 0.0, 33.3, -30.0, -1.5)))
        width = f32(rng.choice((0.0, 0.0, 0.0, 10.0, 40.0, -0.0)))
        radius = f32(rng.choice((40.0, 120.0, 279.99988, 340.0, 600.0)))
        return (pos, rng.randrange(0x10000), w.out, filt, radius, arc, width)
    if key == 'collectInSphere':
        return (pos, rng.randrange(0x10000), w.out, f32(rng.choice((30.0, 120.0, 300.0, 0.0))))
    if key == 'damageInRadius':
        attacker = rng.choice([0] + w.everything)
        outer = rng.choice((48.0, 100.0, 160.0, 300.0))
        inner = rng.choice((0.0, 24.0, outer - 0.5, outer, outer + 20.0))
        most = rng.choice((1, 10, 50, 120, 1000))
        least = rng.choice((0, 0, 1, 5, most, most + 3))
        return (attacker, pos, most, rng.choice((0x40000, 0x100900, 0x40860, 0)), least,
                rng.choice((0, 0, 8, 0x49, 1)), f32(inner), f32(outer))
    if key.startswith('dtor'):
        return (rng.choice(w.everything), rng.choice((0, 1, 2, 3)))
    raise KeyError(key)


def main(argv):
    install()
    opts = DT.OPTIONS
    opts['cases'] = 4000
    args, elf = list(argv), None
    while args:
        a = args.pop(0)
        if a == '--quick':
            opts['quick'] = True
        elif a == '--seed':
            opts['seed'] = int(args.pop(0), 0)
        elif a == '--cases':
            opts['cases'] = int(args.pop(0), 0)
        elif a == '-k':
            opts['filter'] = args.pop(0)
        elif a == '-v':
            opts['verbose'] = True
        else:
            elf = a
    if elf is None:
        for cand in (os.path.join(DT.ROOT, 'SLUS_209.73'), os.path.join(DT.ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(cand):
                elf = cand
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_combat_spells: no SLUS_209.73 - nothing to compare with (this is not a failure)')
        return 0
    import hashlib
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DT.EXPECTED_SHA256:
        print('difftest_combat_spells: %s is not SLUS_209.73 US v2.00 - skipped' % elf)
        return 0
    cases = max(opts['cases'] // 10, 1) if opts['quick'] else opts['cases']
    started, ok_all = time.time(), True
    print('%-18s %8s %8s %8s  coverage' % ('entry point', 'compared', 'failed', 'refused'))
    for index, key in enumerate(ENTRIES):
        if opts['filter'] and opts['filter'].lower() not in key.lower():
            continue
        rig = DT.Rig(elf, opts['seed'] + index)
        rng = random.Random(opts['seed'] * 37 + index)
        compared = failed = refused = 0
        shown = []
        for n in range(cases):
            args_ = generate(rig, key, rng)
            out = rig.compare(key, args_, rng.getrandbits(32))
            if out == 'refused':
                refused += 1
                continue
            compared += 1
            if out:
                failed += 1
                if len(shown) < (5 if opts['verbose'] else 1):
                    shown.append((n, out))
        start, end = ENTRIES[key][5]
        hit = len([pc for pc in rig.trace if start <= pc < end])
        print('%-18s %8d %8d %8d  %d of %d instructions' % (key, compared, failed, refused, hit, (end - start) // 4))
        for n, out in shown:
            print('    case %d: %s' % (n, out))
        if rig.unknown:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
            ok_all = False
        ok_all = ok_all and not failed
    print('%.0f s' % (time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
