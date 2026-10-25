#!/usr/bin/env python3
"""difftest_combat_melee.py - compare the player-offence bodies of tools/ref_combat_melee.py
with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_melee.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                         [--cases N] [-k TEXT] [-v]

What is compared
    As tools/difftest_combat_runtime.py (whose World and Rig this script extends): the
    ORIGINAL function runs in tools/ee_emu.py (an instruction interpreter, not a console)
    on records this script builds; the same inputs go through ref_combat_melee.MeleeModel
    on a copy-on-write view of that memory.  Equal must be: the calls to everything outside
    the model, in order and with their arguments; the set of bytes stored outside the
    stack and their values; the shared seed 0x404464 and the number of draws; the result.

Entry points
    pickAttackAnim     Player_pickAttackAnim 0x1bba88
    meleeHitFull       Player_meleeHit 0x1b6a98, every branch (weapons, two hands, bow and
                       thrown, heavy attack with Player_hitSparks run for real, scale,
                       SpellHarmTouch, the AutoProp exception)
    meleeHitRound1     the same function on round 1's generator (an unarmed player,
                       scale 0) through player_melee_hit_full - the superset method equals
                       the original where round 1's method was compared
    hitSparks          Player_hitSparks 0x1bcc20 on its own

What runs for real and what is a stub
    Real: the entry point, Player_hitSparks, skill_rankScale 0x1bf438, Creature and Player
    slot 16 (0x3c2738, 0x3c3b38), the C library (rtti_typeInfoEquals, strcmp, soft
    doubles) and the round-1 set.  Everything else - Player_recalcDamage, damage_apply,
    terrain_raycast, item_getModifiedField1a, the sample-point functions, particle_spawn,
    SpellHarmTouch_applyToHit, the type-info getters, net_isLocalSlot - is a recording stub
    answered by a seeded script; the model's call-outs get the same answers.
    The class-skill table read by the inlined player_getPassiveLevel is the executable's
    own data at 0x4ef538 (both sides read the same memory); the level bytes are random.
"""
import hashlib
import os
import random
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EE, EmuError                 # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_melee as M                    # noqa: E402
import difftest_combat_runtime as D             # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32 = D.M32
LIB_LO, LIB_HI = D.LIB_LO, D.LIB_HI
G_PLAYERS, REC_SIZE = D.G_PLAYERS, D.REC_SIZE
f32 = D.f32
Res, View, ModelView = D.Res, D.View, D.ModelView

REAL_OTHER = set(D.REAL_OTHER) | {0x1BCC20, 0x1BF438, 0x3C2738, 0x3C3B38}
AUTOPROP_DESC = 0x9089F0                        # the descriptor AutoProp_typeinfo returns (0x3c9514)

Ext = RC.Ext
EXTS = dict(D.EXTS)
EXTS.update({
    'item_getModifiedField1a': Ext(0x103F88, 'p', 0, 'i'),
    'AutoProp_typeinfo': Ext(0x3C9508, '', 0, 'i'),
    'SpellHarmTouch_applyToHit': Ext(0x2D2CBC, 'ppww', 0, 'n'),
    'Creature.v0': Ext(0, '', 0, 'i'),
})

ENTRIES = {
    'pickAttackAnim': (0x1BBA88, 'ii', 0, 'n', 'pick_attack_anim', (0x1BBA88, 0x1BBFF8)),
    'meleeHitFull': (0x1B6A98, 'iiii', 1, 'n', 'player_melee_hit_full', (0x1B6A98, 0x1B7158)),
    'meleeHitRound1': (0x1B6A98, 'iiii', 1, 'n', 'player_melee_hit_full', (0x1B6A98, 0x1B7158)),
    'hitSparks': (0x1BCC20, 'ii', 0, 'n', 'player_hit_sparks', (0x1BCC20, 0x1BCE88)),
}
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False}


class World(D.World):
    """Round 1's fake world plus weapons, type descriptors and the slot-16 bodies."""

    def __init__(self, emu, rng):
        D.World.__init__(self, emu, rng)
        mem = self.mem
        for table, fn in ((self.table_c, 0x3C2738), (self.table_p, 0x3C3B38)):
            mem.w32(table + 8 * 16 + 4, fn)
        name_a, name_c = emu.alloc(16), emu.alloc(16)
        mem.write(name_a, b'AutoProp\0')
        mem.write(name_c, b'Creature\0')
        mem.w32(AUTOPROP_DESC, name_a)
        twin, other = emu.alloc(16), emu.alloc(16)
        mem.w32(twin, name_a)
        mem.w32(other, name_c)
        self.descriptors = (AUTOPROP_DESC, twin, other, other)
        self.defs = [emu.alloc(0x40) for _ in range(6)]
        self.items = [emu.alloc(0x48) for _ in range(8)]
        self.spell = emu.alloc(0x40)
        # the class-skill table the inlined player_getPassiveLevel searches (0x4ef538, 0xa88
        # bytes per record class): overwritten here with masks the test chooses, so that
        # both the dual-wield (0x40000) and the heavy-attack (0x20000) passives are found
        # (record class 5: neither, the not-found path)
        for cls in range(6):
            base = M.G_CLASS_SKILLS + cls * 0xA88
            for n in range(0x30):
                mem.w64(base + n * 0x38, 0 if cls == 5 else rng.choice((0, 0, 0, 0x40000, 0x20000, 0x10, 0x200)))

    def arm(self, rng, P):
        """Weapons, hands, classes and levels for one meleeHit case."""
        mem = self.mem
        R = G_PLAYERS + mem.u32(P + 0x3C8) * REC_SIZE
        for d in self.defs:
            mem.w32(d + 0x20, rng.choice((1, 8, 2, 0x40, 0x101, 4)))
            mem.w8(d + 0x1E, rng.choice((0, 1, 2, 3, 4, 6, 6, 7)))
        for it in self.items:
            mem.w32(it, rng.choice(self.defs))
            mem.w64(it + 8, rng.getrandbits(64))
        pick = lambda p: rng.choice(self.items) if rng.random() < p else 0       # noqa: E731
        mem.w32(R + 0x4434, pick(0.7))
        mem.w32(R + 0x4438, pick(0.5))
        mem.w8(R + 0x4A7C, rng.choice((0, 0, 1)))
        mem.w32(R + 0x43F0, pick(0.6))
        mem.w32(R + 0x43F4, pick(0.6))
        mem.w32(R + 0x443C, pick(0.6))
        mem.w8(R + 0x4A86, rng.randrange(8))
        mem.w32(R + 0x50, rng.randrange(6))
        for n in range(0x30):
            mem.w8(R + 0xEF + n, rng.choice((0, 0, 1, 3, 0xFF)))
        mem.w8(P + 0x460, rng.randrange(9))
        mem.w32(P + 0x44C, rng.choice((0, 1, 2, 2)))
        mem.w32(P + 0x544, rng.choice((0x00A10000, 0x00A20000)))

    def on_Player_recalcDamage(self, args, view, rng):
        res = D.World.on_Player_recalcDamage(self, args, view, rng)
        if rng.random() < 0.2:                         # negative ranges reach the other rounding
            R = G_PLAYERS + view.load(args[0] + 0x3C8, 4) * REC_SIZE
            view.poke(R + 0xD0, 4, -rng.choice((1, 6, 11)) & M32)
            view.poke(R + 0xD4, 4, -rng.choice((0, 3)) & M32)
        return res

    # ---- answers -------------------------------------------------------------------------
    def on_model_getSamplePointCount(self, args, view, rng):
        return Res(rng.choice((1, 3, 17, 40)))

    def on_model_getSamplePoint(self, args, view, rng):
        p = tuple(f32(rng.uniform(-500, 500)) for _ in range(3))
        q = tuple(f32(rng.uniform(-500, 500)) for _ in range(3))
        return Res(0, 0, [p, q])

    def on_item_getModifiedField1a(self, args, view, rng):
        return Res(rng.choice((0, 5, 37, 210)))

    def on_AutoProp_typeinfo(self, args, view, rng):
        return Res(AUTOPROP_DESC)

    def on_Creature_v0(self, args, view, rng):
        return Res(rng.choice(self.descriptors))

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(rng.choice((0, 0, 0, self.spell)))

    def on_SpellHarmTouch_applyToHit(self, args, view, rng):
        lo = rng.choice((3, 40, 250))
        return Res(0, 0, [lo, lo + rng.choice((0, 8))])


class Rig(D.Rig):
    """difftest_combat_runtime.Rig with this script's world, entries and external table."""

    def __init__(self, elf, seed):          # noqa: no D.Rig.__init__: its tables are module-level
        self.rng = random.Random(seed)
        emu = self.emu = EE(elf)
        self.world = World(emu, self.rng)
        real = set(REAL_OTHER) | {e[0] for e in ENTRIES.values()}
        self.real = real
        emu.follow = type('Follow', (), {'__contains__': lambda _s, t: t in real or LIB_LO <= t < LIB_HI})()
        self.names = {}
        for name, ext in EXTS.items():
            addr = self.world.stub_for(name) if ext.addr == 0 else ext.addr
            if addr in real:
                continue
            self.names[addr] = name
            emu.stub(addr, function=self.make_stub(name, ext), name=name)
        for addr, name in self.world.stub_name.items():
            if addr not in self.names:
                self.names[addr] = name
                ext = EXTS.get(name, Ext(0, 'pp', 0, 'n'))
                emu.stub(addr, function=self.make_stub(name, ext), name=name)
        self.calls, self.unknown = [], {}
        self.trace = set()
        self.draws = 0
        self.partial, self.partial_ops = [], {}
        bodies = [e[5] for e in ENTRIES.values()]
        for start, end in bodies:
            for pc in range(start, end, 4):
                w = emu.mem.u32(pc)
                if w >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = w >> 26
                    emu.hook(pc, self.partial_hook(pc, (w >> 21) & 31, ee_emu.sx16(w)))
        self.eview = View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    class Callbacks(D.Rig.Callbacks):
        def get(self, name):
            if name == 'SpellHarmTouch_applyToHit':
                def answer(*args):
                    res = self.rig.world.respond(name, args, self.view, self.rng)
                    return tuple(v & M32 for v in res.outs)
                return answer
            if name.startswith('Creature.v') or name in EXTS and name not in AM.EXTERNALS:
                def answer(*args):
                    res = self.rig.world.respond(name, args, self.view, self.rng)
                    ext = EXTS.get(name)
                    return None if ext is not None and ext.ret == 'n' else res.ret & M32
                return answer
            return D.Rig.Callbacks.get(self, name)

    def compare(self, key, args, call_seed):
        addr, kinds, _nfloat, ret_kind, method, _body = ENTRIES[key]
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        mview = ModelView(mem)
        model = M.MeleeModel(mview, Rig.Callbacks(self, View(mview.load, mview.poke), random.Random(call_seed)))
        ints, floats = list(args[:len(kinds)]), list(args[len(kinds):])
        try:
            mret = getattr(model, method)(*(ints + floats))
        except (T.Unsupported, T.CompositionError):
            return 'refused'
        self.calls, self.touched = [], set()
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        self.partial = []
        emu.trace = []
        emu.r[29] = emu.stack_hi - 0x100
        regs = [a & M32 for a in ints]
        for j, value in enumerate(floats):
            emu.f[12 + j] = value & M32
        try:
            eret = emu.call(addr, *regs, max_steps=4000000)
        except EmuError as exc:
            return ['original stopped: %s' % exc]
        self.trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names and not LIB_LO <= c.target < LIB_HI:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        problems = []
        if model.calls != self.calls:
            first = next((i for i, (a, b) in enumerate(zip(model.calls, self.calls)) if a != b),
                         min(len(model.calls), len(self.calls)))
            problems.append('calls differ at %d: model %s / original %s' % (
                first, model.calls[first:first + 2], self.calls[first:first + 2]))
        stored = self.stored_bytes(0, 0)
        mstored = set()
        for a, size, _v in model.writes:
            mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            problems.append('writes: only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:6], sorted('%x' % a for a in mstored - stored)[:6],
                ['%x' % a for a in diff[:6]]))
        s = seed_before
        for _ in range(model.draws):
            s = (s * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(T.G_RAND_SEED) == mview.load(T.G_RAND_SEED, 4) == s:
            problems.append('seed: model draws %d' % model.draws)
        if ret_kind == 'i' and (eret & M32) != ((mret or 0) & M32):
            problems.append('result: original %08x model %08x' % (eret & M32, (mret or 0) & M32))
        for a in mview.bytes:
            mem.store(a, 1, mview.bytes[a])
        self.draws += model.draws
        return problems


def generate(rig, key, rng):
    w, mem = rig.world, rig.emu.mem
    if key == 'meleeHitRound1':
        return D.generate(rig, 'playerMeleeHit', rng)
    P, target, a2, extra, _scale = D.generate(rig, 'playerMeleeHit', rng)
    if key == 'pickAttackAnim':
        R = G_PLAYERS + mem.u32(P + 0x3C8) * REC_SIZE
        mem.w32(R + 0x54, rng.choice((0, 1, 2, 4, 5, 7, 8, 9, 9, 9, 10, 11, 11, 11)))
        mem.w8(P + 0x461, rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 0xFF)))
        mem.w32(T.G_SIM_FRAME, rng.getrandbits(32))
        return (P, rng.choice((0, 0, 0, 1, 2, 3, 4, 5, 5, 6, 7, 8, 0xFF)))
    w.arm(rng, P)
    mem.w64(target + 0xA8, rng.choice((0, 0x2000, 0x1000, 0x40000, 0x3000, 0x41000, 1 << 63)))
    if key == 'hitSparks':
        return (P, target)
    scale = rng.choice((0.0, 0.0, 0.0, 0.5, 1.5, 2.0, -1.0))
    return (P, target, a2, extra, f32(scale))


# ---------------------------------------------------------------------------------------
# combo sequences: Player_run state 1 with weapon classes 4, 6 and 7 (tools/difftest_player.py)
# ---------------------------------------------------------------------------------------
# The combo steps of state 1 are part of ref_player.Tick, executed by tools/difftest_player.py,
# whose random runs never entered the next swing of the bow / thrown-weapon melee
# (0x1aad90-0x1aaf30) nor the class-7 combo window (0x1aab18).  These runs use that script's
# world and rig unchanged and a driver that, in state 2, equips a bow, a thrown weapon or
# two weapons and enters state 1 by writing the fields the state-2 attack writes for it
# (AUTHORED driver; state 2's own bow/thrown punch path 0x1a79fc writes the same ones), then
# taps attack.

COMBO_BLOCKS = {'class-7 combo window 0x1aab18': (0x1AAB18, 0x1AAB1C),
                'class 4/6 next swing 0x1aae70': (0x1AAE70, 0x1AAE74),
                'Player_findTarget(P, 60) 0x1aaeac': (0x1AAEAC, 0x1AAEB0),
                'class 4/6 swing started 0x1aaf00': (0x1AAF00, 0x1AAF04),
                'state 2 at 0x1aaf30 (unreachable: since <= 39.6 and > 54)': (0x1AAF30, 0x1AAF34)}


def combo_runs(elf, ticks, seed):
    import difftest_player as DP
    RP = DP.RP

    class ComboDriver(DP.Driver):
        def between(self):
            DP.Driver.between(self)
            rng, mem, world = self.rng, self.mem, self.world
            P, R = world.P, world.R
            frame = mem.u32(RP.G_SIM_FRAME)
            if mem.s32(P + 0x58C) == 2 and rng.random() < 0.08:
                key = rng.choice(('bow', 'thrown', 'dual', 'dual', 'bow'))
                world.equip(world.slot, key, rng)
                mem.w32(P + 0x58C, 1)
                mem.w32(P + 0x448, (frame - rng.choice((0, 0, 1, 20, 41))) & M32)
                mem.w32(P + 0x470, 0x3F666666 if key == 'bow' else 0x3FCCCCCC)
                mem.w8(P + 0x461, 1)
                mem.w32(P + 0x44C, 0)
                mem.w8(P + 0x460, 0)
                self.plan = []
                for _ in range(rng.randrange(2, 8)):
                    self.plan += [DP.BTN["attack"]] * rng.randrange(1, 3) + [0] * rng.randrange(15, 60)

    totals = {'ticks': 0, 'state1': {}, 'bad': 0, 'examples': []}
    hits = {k: 0 for k in COMBO_BLOCKS}
    for n, (net, copy, machine) in enumerate(((0, 0, 0), (1, 0, 0), (0, 0, 1), (1, 1, 1))):
        rig = DP.Rig(elf, seed + n, net, copy, machine)
        driver = ComboDriver(rig)
        world, mem = rig.world, rig.emu.mem
        world.place_creatures(rig.rng)
        for t in range(ticks):
            driver.pad()
            state = mem.s32(world.P + 0x58C)
            cls = mem.s8(world.R + 0x4A86)
            result = rig.tick(seed * 1000003 + n * 7919 + t, trace=True)
            if result['fault']:
                if (result['model_error'] is None) != (result['emu_error'] is None):
                    totals['bad'] += 1
                world.init_object(world.P, world.slot, rig.rng)
                world.init_record(world.slot, rig.rng)
                mem.wf32(world.R + 0xAC, 100.0)
                driver.between()
                continue
            totals['ticks'] += 1
            if state == 1:
                totals['state1'][cls] = totals['state1'].get(cls, 0) + 1
            for k, (lo, hi) in COMBO_BLOCKS.items():
                if any(lo <= pc < hi for pc in rig.emu.trace or ()):
                    hits[k] += 1
            if not (result['calls_ok'] and result['set_ok'] and result['values_ok'] and result['seed_ok']):
                totals['bad'] += 1
                if len(totals['examples']) < 3:
                    totals['examples'].append('run %d tick %d state %d class %d: calls %s set %s values %s seed %s'
                                              % (n, t, state, cls, result['calls_ok'], result['set_ok'],
                                                 result['values_ok'], result['seed_ok']))
            driver.between()
        if rig.unknown:
            totals['bad'] += 1
            totals['examples'].append('unknown calls %s' % {hex(a): c for a, c in rig.unknown.items()})
    return totals, hits


def main(argv):
    args, elf = list(argv), None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        for cand in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(cand):
                elf = cand
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_combat_melee: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_melee: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    print('%-22s %8s %8s %8s %8s  coverage' % ('entry point', 'compared', 'failed', 'refused', 'draws'))
    for index, key in enumerate(ENTRIES):
        if OPTIONS['filter'] and OPTIONS['filter'].lower() not in key.lower():
            continue
        rig = Rig(elf, OPTIONS['seed'] + index)
        rng = random.Random(OPTIONS['seed'] * 37 + index)
        compared = failed = refused = 0
        shown = []
        for n in range(cases):
            args = generate(rig, key, rng)
            out = rig.compare(key, args, rng.getrandbits(32))
            if out == 'refused':
                refused += 1
                continue
            compared += 1
            if out:
                failed += 1
                if len(shown) < (5 if OPTIONS['verbose'] else 1):
                    shown.append((n, out))
        start, end = ENTRIES[key][5]
        hit = len([pc for pc in rig.trace if start <= pc < end])
        print('%-22s %8d %8d %8d %8d  %d of %d instructions' % (key, compared, failed, refused, rig.draws, hit,
                                                                 (end - start) // 4))
        for n, out in shown:
            print('    case %d: %s' % (n, out))
        if rig.unknown:
            print('    calls to unknown addresses: %s' % {('%x' % k): v for k, v in rig.unknown.items()})
            ok_all = False
        ok_all = ok_all and not failed
    if not OPTIONS['filter'] or OPTIONS['filter'].lower() in 'combo':
        ticks = max(OPTIONS['cases'] // 10, 30) if OPTIONS['quick'] else OPTIONS['cases']
        totals, hits = combo_runs(elf, ticks, OPTIONS['seed'])
        print('combo runs (Player_run vs ref_player.Tick, 4 x %d ticks): %d compared, %d failed; '
              'state-1 ticks by weapon class %s' % (ticks, totals['ticks'], totals['bad'],
                                                     dict(sorted(totals['state1'].items()))))
        for k, v in hits.items():
            print('    ticks entering %s: %d' % (k, v))
        for e in totals['examples']:
            print('    ' + e)
        ok_all = ok_all and not totals['bad']
    print('%.0f s' % (time.time() - started))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
