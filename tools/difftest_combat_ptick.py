#!/usr/bin/env python3
"""difftest_combat_ptick.py - compare the player-defence bodies of tools/ref_combat_ptick.py
with the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_ptick.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                         [--cases N] [-k TEXT] [-v]

What is compared (as tools/difftest_combat_runtime.py)
    The ORIGINAL function runs in tools/ee_emu.py (an instruction interpreter, not a
    console) on records this script builds; the same inputs go through
    ref_combat_ptick.DefenceModel on a copy-on-write view of that memory.  Equal must be:
    the calls to everything outside the model, in order and with their arguments (a C
    string argument by its text); the set of bytes stored outside the stack and their
    values; the shared seed 0x404464 and the number of draws; the result.

    Round-1 agreement: on every case the round-1 method (ref_combat_runtime.CombatModel.
    player_take_damage / player_process_damage) does not refuse, it is run too and must
    make the same calls, stores and draws as the _full method.

What runs for real and what is a stub
    Real: the entry point, Player_blockSparks 0x1b9658 (inside Player_takeDamage),
    GameObject_rand, Player slot 39 0x3c3b40, the angle functions and the C library
    (sprintf, strcat, strcmp).  Everything else is a recording stub answered by a seeded
    script; the model's call-outs are answered by the same script.
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
import ref_combat_ptick as PT                   # noqa: E402
import difftest_combat_runtime as D             # noqa: E402

M32 = 0xFFFFFFFF
f32, is_stack, Res, View, ModelView = D.f32, D.is_stack, D.Res, D.View, D.ModelView
LIB_LO, LIB_HI = D.LIB_LO, 0x3C01A8            # the C library, libc_mbtowc_r (sprintf's helper) included
LIBC_SCRATCH = (0x50C530, 0x50C800)             # the C library's own state (sprintf's reentrancy block)
REAL_OTHER = {0x166630, 0x1666E0, 0x166798, 0x1509D0, 0x3C3B40, 0x1B9658}
G_PLAYERS, REC_SIZE = T.G_PLAYERS, T.REC_SIZE

Ext = RC.Ext
EXTS = dict(D.EXTS)
EXTS.update({
    'res_find': Ext(0x17365C, 'pS', 0, 'i'),
    'sound_playAtPos': Ext(0x214428, 'pv', 1, 'n'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'i'),
    'model_getAttachPoint': Ext(0x1754A0, 'pvipioO', 1, 'n'),
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n'),
    'SpellHolyShield_absorb': Ext(0x2E8534, 'p', 0, 'f'),
    'SpellResurrect_onOwnerDeath': Ext(0x3130F4, 'p', 0, 'f'),
    'SkillStrongStance_trigger': Ext(0x308578, 'ppSi', 0, 'n'),
    'Player_hasAnim': Ext(0x1BF230, 'pS', 0, 'i'),
    'fx_spawn': Ext(0x1EF270, 'iv', 0, 'n'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i'),
    'GutChunk_ctor': Ext(0x201958, 'pvii', 1, 'n'),
    'fx_disintegrateModel': Ext(0x1F4340, 'pppvii', 1, 'n'),
    'arena_onPlayerKilled': Ext(0x305580, 'ip', 0, 'n'),
    'arena_loseLife': Ext(0x305650, 'i', 0, 'n'),
    'anim_start': Ext(0x16CFE0, 'ppi', 1, 'n'),
    'anim_startBlendInOut': Ext(0x16CEB0, 'ppi', 2, 'n'),
    'Spell.v1': Ext(0, 'pi', 0, 'n'),
})
EXTS.pop('libc_sprintf', None)                  # the C library runs for real (sprintf, strcat)

ENTRIES = {
    'takeDamageFull': (0x1B5330, 'iii', 1, 'n', 'player_take_damage_full', (0x1B5330, 0x1B5790),
                       'player_take_damage'),
    'blockSparks': (0x1B9658, 'ii', 0, 'n', 'player_block_sparks', (0x1B9658, 0x1B9CB8), None),
    'playerInteract': (0x1B2640, 'iii', 0, 'n', 'player_interact', (0x1B2640, 0x1B2CC0), None),
    'processDamageFull': (0x1B2CC0, 'i', 0, 'n', 'player_process_damage_full', (0x1B2CC0, 0x1B3900),
                          'player_process_damage'),
}
OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False}

FRACTIONS = [f32(v) for v in (0.0, 0.25, 0.5, 1.0, 1.5)]


def shape(name, args, res):
    """What a call-out hands the model: AM.shape_result's rules over this script's EXTS
    (a float result is res.f)."""
    ext = EXTS[name]
    values, position, given = [], 0, list(res.outs)
    for kind in ext.ints:
        if kind in 'oOwWbnL':
            value = given.pop(0) if given else ((0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0))
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvelsSOW':
            position += 1
    head = [] if ext.ret == 'n' else [(res.f if ext.ret == 'f' else res.ret) & M32]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def canon_args(args):
    return tuple(('str', bytes(a)) if isinstance(a, (bytes, bytearray)) else a for a in args)


class World(D.World):
    """D.World plus a spell object (table at +0x14) and the answers of the new call-outs."""

    def __init__(self, emu, rng):
        D.World.__init__(self, emu, rng)
        mem = self.mem
        self.spell = emu.alloc(0x40)
        table = emu.alloc(0x40)
        mem.w32(self.spell + 0x14, table)
        mem.w16(table + 8, 0)
        mem.w32(table + 12, self.stub_for('Spell.v1'))
        self.spell_node = emu.alloc(0x20)
        mem.w32(self.spell_node + 0xC, self.spell)
        self.blocks = [emu.alloc(0x280) for _ in range(2)]

    def on_res_find(self, args, view, rng):
        return Res(rng.choice((0, 0xA0001000, 0xA0002000)))

    def on_model_getAttachPoint(self, args, view, rng):
        pos = args[1]
        return Res(0, 0, [tuple(T.C.add(pos[i], f32(rng.uniform(-30, 30))) for i in range(3))])

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(rng.choice((0, 0, self.spell)))

    def on_SpellHolyShield_absorb(self, args, view, rng):
        return Res(0, rng.choice(FRACTIONS))

    def on_SpellResurrect_onOwnerDeath(self, args, view, rng):
        return Res(0, rng.choice((0, 0, f32(50.0), f32(-1.0))))

    def on_Player_hasAnim(self, args, view, rng):
        return Res(rng.choice((0, 0, 1)))

    def on_pool_new(self, args, view, rng):
        return Res(rng.choice((0, self.blocks[0])))

    def on_SkillStrongStance_getStat0(self, args, view, rng):
        return Res(rng.choice((0, 30, 100, 100)))


class Rig(D.Rig):
    """D.Rig with this script's entry points, externals, the 'S' argument kind and
    DefenceModel."""

    def __init__(self, elf, seed):                  # noqa: no D.Rig.__init__ (other entries)
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
        self.agree = [0, 0]
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

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for i, kind in enumerate(ext.ints):
            v = emu.r[4 + i] & M32
            if kind in 'ip':
                canon.append(v)
            elif kind == 'v':
                canon.append(tuple(mem.u32(v + 4 * j) for j in range(3)))
            elif kind == 'S':
                text = mem.cstr(v)
                canon.append(('str', text.encode('latin-1') if isinstance(text, str) else bytes(text)))
            elif kind in 'OW':
                canon.append(1 if v else 0)
                outs.append((kind, v))
            elif kind in 'onwb':
                outs.append((kind, v))
        for j in range(ext.floats):
            canon.append(emu.f[12 + j])
        return canon, outs

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            def answer(*args):
                res = self.rig.world.respond(name, canon_args(args), self.view, self.rng)
                return shape(name, args, res)
            return answer

    def run_model(self, cls, method, args, call_seed):
        mem = self.emu.mem
        mview = ModelView(mem)
        model = cls(mview, Rig.Callbacks(self, View(mview.load, mview.poke), random.Random(call_seed)))
        mret = getattr(model, method)(*args)
        calls = [(n, canon_args(a)) for n, a in model.calls]
        stored = set()
        for a, size, _v in model.writes:
            stored.update(range(a, a + size))
        return model, mview, mret, calls, stored

    def compare(self, key, args, call_seed):
        addr, kinds, nfloat, ret_kind, method, _body, round1 = ENTRIES[key]
        emu, world, mem = self.emu, self.world, self.emu.mem
        seed_before = mem.u32(T.G_RAND_SEED)
        ints, floats = list(args[:len(kinds)]), list(args[len(kinds):])
        try:
            model, mview, mret, mcalls, mstored = self.run_model(PT.DefenceModel, method, ints + floats, call_seed)
        except (T.Unsupported, T.CompositionError):
            return 'refused'
        r1 = None
        if round1:
            try:
                r1 = self.run_model(T.CombatModel, round1, ints + floats, call_seed)
            except (T.Unsupported, T.CompositionError):
                r1 = None
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
            return 'original stopped: %s' % exc
        self.trace.update(emu.trace)
        for c in emu.calls:
            if c.target not in self.real and c.target not in self.names and not LIB_LO <= c.target < LIB_HI:
                self.unknown[c.target] = self.unknown.get(c.target, 0) + 1
        problems = []
        if mcalls != self.calls:
            problems.append('calls: model %s / original %s' % (mcalls[:6], self.calls[:6]))
        stored = {a for a in self.stored_bytes(world.argbuf, world.argbuf + 0x100)
                  if not LIBC_SCRATCH[0] <= a < LIBC_SCRATCH[1]}
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
        if r1 is not None:
            m1, v1, _ret1, calls1, stored1 = r1
            same = calls1 == mcalls and stored1 == mstored and m1.draws == model.draws and \
                all(v1.load(a, 1) == mview.load(a, 1) for a in stored1)
            self.agree[0] += 1
            if not same:
                self.agree[1] += 1
                problems.append('round-1 method disagrees with the _full method')
        for a in mview.bytes:                               # keep both sides in step
            mem.store(a, 1, mview.bytes[a])
        self.draws += model.draws
        return problems


def generate(rig, key, rng):
    """Arguments for one call (and the state they need)."""
    w, mem = rig.world, rig.emu.mem
    P = rng.choice(w.players)
    centre = (rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50))
    w.scatter(rng, centre)
    mem.w32(T.G_SIM_FRAME, rng.randrange(1 << 20))
    mem.w32(T.G_RAND_SEED, rng.getrandbits(32))
    mem.w8(T.G_NETWORK_MODE, rng.choice((0, 0, 0, 1)))
    mem.w8(T.G_CUTSCENE_ACTIVE, 0)
    mem.w32(T.G_PVP_MODE_A, 0)
    mem.w32(T.G_PVP_MODE_B, 0)
    mem.w32(T.G_DECAL_DETAIL, 0)
    mem.w32(T.G_DEBUG_INVULNERABLE, rng.choice((0, 0, 0, 1)))
    mem.w8(T.G_RECALL_COUNTDOWN, 0)
    mem.w32(T.G_MENU_LOCKOUT, 0)
    mem.w16(T.G_EXIT_COUNTDOWN, 0)
    mem.w8(0x41B69D, rng.choice((0, 1)))
    mem.w32(T.G_NUM_PLAYERS, 4)
    mem.write(T.G_LEVEL_NAME, rng.choice((b'town\0', b'town\0', b'actintro\0')))
    R = G_PLAYERS + mem.u32(P + 0x3C8) * REC_SIZE
    mem.w8(R + 0x4A86, rng.randrange(8))
    mem.w32(P + 0x24, w.anim_table)
    mem.w32(P + 0x544, rng.choice((0, 0x00A10000)))
    if key in ('takeDamageFull', 'blockSparks'):
        mem.w32(P + 0x58C, rng.choice((1, 2, 3, 8, 8, 8, 0xB, 0xB)))
        mem.w16(P + 0x4B4, rng.choice((0, 0, 0, 0, 5)))
        mem.w32(P + 0x2DC, rng.choice((0, 0x2000, 0x800000)))
        mem.wf32(P + 0xC8, rng.choice((0.0, 3.0)))
        mem.wf32(R + 0xC0, rng.choice((0.0, 0.0, 10.0, 100.0, 1.0)))
        mem.w8(R + 0x4C27, rng.choice((0, 0, 0, 0, 2)))
        if key == 'blockSparks':
            return (P, 0)
        mem.w8(T.G_RECALL_COUNTDOWN, rng.choice((0,) * 30 + (1,)))
        mem.w32(T.G_MENU_LOCKOUT, rng.choice((0,) * 30 + (1,)))
        mem.w16(T.G_EXIT_COUNTDOWN, rng.choice((0,) * 30 + (2,)))
        mem.w32(P + 0x540, rng.choice((0,) * 30 + (1,)))
        attacker = rng.choice(w.everything + [0])
        if attacker:
            flags = mem.u32(attacker + 0xC) & ~0x80 & M32
            if attacker != P and rng.random() < 0.15:
                flags |= 0x80                               # owned (a projectile's owner at +0x4c)
                mem.w32(attacker + 0x4C, rng.choice((0, w.nodes[rng.choice(w.everything)])))
            mem.w32(attacker + 0xC, flags)
        mem.w32(P + 0x360, rng.choice((0, w.nodes[rng.choice(w.everything)])))
        flags = rng.choice((8, 1, 0x10000008, 0x40, 0x20000, 0x20008, 0x40001))
        return (P, attacker, flags, f32(rng.choice((0.0, 7.0, 150.0, 1.5))))
    if key == 'playerInteract':
        mem.w32(P + 0x540, rng.choice((0,) * 20 + (1,)))
        mem.wf32(R + 0xAC, rng.choice((100.0, 100.0, 100.0, 0.0)))
        mem.w32(R + T.REC_OBJ, rng.choice((P, P, P, P, 0, rng.choice(w.players))))
        slot = mem.u32(P + 0x3C8)
        mem.w32(PT.G_PROMPT_TIMER + 4 * slot, rng.choice((0, 3, 7, 8, 100, -5 & M32)))
        mem.w32(PT.G_PROMPT_OWNER + 4 * slot, rng.getrandbits(32))
        mem.w32(PT.G_PROMPT_TEXT + 0x200 * slot, rng.getrandbits(32))
        for o in w.everything:
            if rng.random() < 0.05:
                mem.w32(o + 0xC, mem.u32(o + 0xC) | 0x100000)
        return (P, 0x00A20000, 0)
    if key == 'processDamageFull':
        mem.w32(T.G_PVP_MODE_A, rng.choice((0, 0, 0, 1)))
        mem.w32(T.G_PVP_MODE_B, rng.choice((0, 0, 0, 1)))
        mem.w32(T.G_DECAL_DETAIL, rng.choice((0, 0, 1, 2)))
        mem.w32(T.G_NUM_PLAYERS, rng.choice((1, 1, 2, 4)))
        mem.w32(P + 0x58C, rng.choice((1, 2, 2, 3, 4, 6, 7, 8, 8)))
        knock = rng.choice((0, 0, 0x40000, 0x80000, 0x100000, 0x200000, 0x280000))
        bits = rng.choice((0, 1, 4, 8, 0x10, 0x11, 0x400000, 0x4000000, 0x20000000, 0x400008))
        mem.w32(P + 0x2DC, knock | bits)
        mem.wf32(P + 0xC8, rng.choice((0.0, 3.0, 50.0, 200.0)))
        mem.wf32(R + 0xAC, rng.choice((100.0, 40.0, 5.0)))
        mem.w16(P + 0x2E0, rng.randrange(0x10000))
        mem.w32(P + 0x44C, rng.choice((0, 0, 1, 2)))
        mem.w8(P + 0x118, rng.choice((1, 4, 5, 6)))
        mem.w8(T.G_CUTSCENE_ACTIVE, rng.choice((0, 0, 0, 0, 1)))
        mem.w32(R + 0x54, rng.randrange(12))
        mem.w32(P + 0x588, rng.choice((0, 0, w.spell_node)))
        killers = [o for o in w.everything if o not in w.players] if mem.u32(T.G_PVP_MODE_A) else w.everything
        mem.w32(P + 0x2E4, rng.choice((0, w.nodes[rng.choice(killers)])))
        mem.w32(P + 0xC, mem.u32(P + 0xC) | rng.choice((0, 0, 0, 0x20000)))
        return (P,)
    raise KeyError(key)


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
        elf = os.path.join(D.ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_combat_ptick: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != D.EXPECTED_SHA256:
        print('difftest_combat_ptick: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    ok_all = True
    print('%-18s %8s %8s %8s %8s %10s  coverage' % ('entry point', 'compared', 'failed', 'refused', 'draws',
                                                    'round-1 eq'))
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
        agree = '%d/%d' % (rig.agree[0] - rig.agree[1], rig.agree[0]) if ENTRIES[key][6] else '-'
        print('%-18s %8d %8d %8d %8d %10s  %d of %d instructions' % (key, compared, failed, refused, rig.draws,
                                                                     agree, hit, (end - start) // 4))
        if OPTIONS['verbose']:
            missing = sorted(pc for pc in range(start, end, 4) if pc not in rig.trace)
            print('    not executed: %s' % ' '.join('%x' % pc for pc in missing[:80]))
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
