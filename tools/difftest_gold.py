#!/usr/bin/env python3
"""difftest_gold.py - compare tools/ref_gold.py with the game's own code: the gold pile's
frame and pickup down to the credit, and the item props' pickup.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_gold.py [path/to/SLUS_209.73] [--quick] [--seed N]
                                    [--cases N] [-k TEXT] [-v] [--trace-first]

What is compared
    Each case is one call or a sequence of calls with the harness's own stores between them
    (the frame counter of a new tick, a second toucher).  These bodies run REAL in
    tools/ee_emu.py: Gold_run 0x157b58, Gold_onTouch 0x157a9c, hud_addGoldFloater 0x1dc268,
    hud_tickGold 0x1dcb80, hud_flushGold 0x1dc5f4, itemprop_tryPickup 0x154dbc,
    PhProp_interact 0x155020, ItemProp_interact 0x159b38, PhProp_interactPrompt 0x154d10,
    ItemProp_interactPrompt 0x159870, and under them mat4_transformPoint 0x165ee0; in the
    'pile' sequence also Gold_ctor2 0x157668 with GameObject_ctor 0x14cb10 and
    GameObject_rand 0x1509d0.  Everything else is a recording stub answered by the same
    seeded script on both sides.  The same steps go through ref_gold.Model on a
    copy-on-write view; equal must be the calls with their arguments (a stack text buffer
    compared by its text), every byte stored outside the stack, the shared seed 0x404464
    with its draw count, the cosmetic seed 0x404460 with its draw count, and every result.

Entries
    goldRun      Gold_run on dirty piles: countdown 0, 1, 0x29, negative; the sound frame;
                 the clip-end bit before and from the anim call
    goldTouch    Gold_onTouch with players, prediction copies, monsters; countdown; amount 0;
                 floaters free or all busy (direct credit); gold near the cap
    floater      hud_addGoldFloater direct: positions on and off screen, odd cameras
    tickGold     hud_tickGold on random floaters (around the 43-frame edge) and pending sums
    flushGold    hud_flushGold on the same
    tryPickup    itemprop_tryPickup: bag counts around 63, load against limit, flag sounds
    phInteract   PhProp_interact (bit 39: every player; or the one slot), real tryPickup
    itemInteract ItemProp_interact the same
    phPrompt     PhProp_interactPrompt, stack counts
    itemPrompt   ItemProp_interactPrompt
    pile         the multi-frame life: Gold_ctor2 at frame F, N ticks of Gold_run, a touch (a
                 player, the copy, a monster, two players in one tick), M ticks of
                 hud_tickGold; the record's gold is compared at the end like every byte
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
import ref_gold as G                            # noqa: E402
import difftest_combat_runtime as D             # noqa: E402
import difftest_creature as DC                  # noqa: E402

EXPECTED_SHA256 = D.EXPECTED_SHA256
ROOT = D.ROOT
M32, M64 = 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF
LIB_LO, LIB_HI = 0x3A5000, 0x3C0000
f32 = D.f32
is_stack = D.is_stack

OPTIONS = {'quick': False, 'seed': 20973, 'cases': 3000, 'filter': None, 'verbose': False, 'trace_first': False}

BODIES = {                                      # ghidra_funcs.tsv bounds
    'Gold_run': (0x157B58, 0x157C04),
    'Gold_onTouch': (0x157A9C, 0x157B58),
    'hud_addGoldFloater': (0x1DC268, 0x1DC5F4),
    'hud_tickGold': (0x1DCB80, 0x1DCC78),
    'hud_flushGold': (0x1DC5F4, 0x1DC708),
    'itemprop_tryPickup': (0x154DBC, 0x155020),
    'PhProp_interact': (0x155020, 0x155108),
    'ItemProp_interact': (0x159B38, 0x159C20),
    'PhProp_interactPrompt': (0x154D10, 0x154DBC),
    'ItemProp_interactPrompt': (0x159870, 0x15991C),
    'Gold_ctor2': (0x157668, 0x157754),
    'ItemProp_ctor3': (0x1592BC, 0x159458),
    'ItemProp_ctor2': (0x1590EC, 0x1592BC),
    'Prop_ctorNamed': (0x153AC0, 0x153C88),
    'item_getResourceIndex': (0x1083F8, 0x108434),
    'Prop_run': (0x154514, 0x1548BC),
}
# executed elsewhere, real here too (only their partial stores are hooked)
OTHER_SPANS = [(0x14CB10, 0x14CF84), (0x165EE0, 0x165FC0), (0x163B30, 0x163CB8),
               (0x153E54, 0x154028), (0x1541A0, 0x154514)]
REAL = set(G.EXECUTED.values()) | {G.MAT4_TRANSFORM_POINT, G.MAT34_SET_POS_ROT_Z, G.ITEM_RESOURCE_INDEX, 0x157668,
                                   0x14CB10, 0x1509D0, 0x153E54, 0x1541A0}
STUBBED = {name: ext for name, ext in G.EXTERNALS.items() if ext.addr not in REAL}

ENTRIES = {
    # key -> (address, argument kinds, result kind, method)
    'goldRun': (G.GOLD_RUN, 'p', 'n', 'gold_run'),
    'goldTouch': (G.GOLD_ON_TOUCH, 'pp', 'n', 'gold_on_touch'),
    'floater': (G.HUD_ADD_GOLD_FLOATER, 'ivi', 'n', 'hud_add_gold_floater'),
    'tickGold': (G.HUD_TICK_GOLD, '', 'n', 'hud_tick_gold'),
    'flushGold': (G.HUD_FLUSH_GOLD, '', 'n', 'hud_flush_gold'),
    'tryPickup': (G.TRY_PICKUP, 'ip', 'i', 'try_pickup'),
    'phInteract': (G.PHPROP_INTERACT, 'pi', 'n', 'prop_interact'),
    'itemInteract': (G.ITEMPROP_INTERACT, 'pi', 'n', 'prop_interact'),
    'phPrompt': (G.PHPROP_PROMPT, 'pp', 'i', 'prop_interact_prompt'),
    'itemPrompt': (G.ITEMPROP_PROMPT, 'pp', 'i', 'prop_interact_prompt'),
    'goldCtor2': (0x157668, 'pvi', 'n', 'gold_ctor2'),
    'itemCtor3': (G.ITEMPROP_CTOR3, 'pvpp', 'n', 'item_prop_ctor3'),
    'itemCtor2': (G.ITEMPROP_CTOR2, 'pvpi', 'n', 'item_prop_ctor2'),
    'propNamed': (G.PROP_CTOR_NAMED, 'pvpppqip', 'n', 'prop_ctor_named'),
    'propRun': (G.PROP_RUN, 'p', 'n', 'prop_run'),
    'dropLife': None,
    'pile': None,
    'itemLife': None,
}
SEQUENCES = ('goldCtor2', 'pile', 'itemLife', 'dropLife')
SINGLE = [k for k in ENTRIES if k not in SEQUENCES] + ['pile', 'itemLife', 'dropLife']


class RealSet:
    def __contains__(self, target):
        return target in REAL or LIB_LO <= target < LIB_HI


class World:
    def __init__(self, emu):
        self.emu, self.mem = emu, emu.mem
        self.argbuf = emu.alloc(0x400)
        self.golds = [emu.alloc(0x100, align=16) for _ in range(3)]
        self.people = [emu.alloc(0x400, align=16) for _ in range(4)]
        self.props = [emu.alloc(0x280, align=16) for _ in range(2)]
        self.defs = [emu.alloc(0x40, align=16) for _ in range(4)]
        self.outbuf = emu.alloc(0x200)
        self.items = [emu.alloc(0x50, align=16) for _ in range(2)]
        self.matrix = emu.alloc(0x40, align=16)
        self.names = []
        for text in (b'fx.lmp', b'equipmnt.lmp', b'model_a', b'a_rather_long_made_up_model_name_for_the_copy', b''):
            at = emu.alloc(0x48)
            self.mem.write(at, text + b'\0')
            self.names.append(at)

    def respond(self, name, args, view, rng):
        handler = getattr(self, 'on_' + name, None)
        return handler(args, view, rng) if handler is not None else D.Res()

    def on_res_find(self, args, view, rng):
        return D.Res(rng.choice((0, 0x00A10000, 0x00A10040)))

    def on_sound_playOnObject(self, args, view, rng):
        return D.Res(rng.choice((0xFFFFFFFF, 3)))

    def on_obj_getPropInt(self, args, view, rng):
        return D.Res(0)

    def on_resref_get(self, args, view, rng):
        return D.Res(rng.choice((0, 0x00A30000)))

    def on_anim_advanceUnitSpeed(self, args, view, rng):
        """The clip ends (anim state +6 gains 0x80) now and then, as anim_advance would."""
        if rng.random() < 0.08:
            at = args[0] + 6
            view.poke(at, 2, view.load(at, 2) | 0x80)
        return D.Res()

    def on_model_getBounds(self, args, view, rng):
        def v():
            return rng.choice((0, 1, -1, 3, -7, 12, -12, 40, rng.randrange(-300, 300)))
        return D.Res(outs=[v() & M32 for _ in range(6)])

    def on_terrain_sweepCircle(self, args, view, rng):
        t = rng.choice((1.0, 1.0, 1.0, 0.0, 0.5, 0.999, 1.25, rng.random()))
        normal = rng.choice(((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.6, 0.8, 0.0), (-0.7071, 0.7071, 0.0),
                             (0.0, 0.0, 1.0), (rng.uniform(-1, 1), rng.uniform(-1, 1), 0.0)))
        return D.Res(f=f32(t), outs=[[f32(v) for v in normal]])

    def on_terrain_heightBelow(self, args, view, rng):
        z = DC.fl(args[1][2])
        return D.Res(f=f32(rng.choice((z - 40.0, z - 3.0, z - 0.4, z, z + 0.2, z + 5.0, -1.0e9, 0.0))))

    def on_player_itemWeight(self, args, view, rng):
        return D.Res(f=rng.choice((0, 0x80000000, f32(1.0), f32(2.5), f32(12.0), f32(400.0),
                                   f32(rng.uniform(0, 60)))))

    def on_inventory_giveItem(self, args, view, rng):
        return D.Res(rng.choice((0, 3, 0xFFFFFFFF)))

    def on_text_lookup(self, args, view, rng):
        return D.Res(0x00A50000)

    def on_itemName_buildLocalizedName(self, args, view, rng):
        return D.Res(0x00564420)


class Rig:
    def __init__(self, elf):
        emu = self.emu = EE(elf, fpu_model='ps2')
        emu.div_zero = 'r5900'
        self.world = World(emu)
        emu.follow = RealSet()
        self.names = {}
        for name, ext in STUBBED.items():
            self.names[ext.addr] = name
            stub = self.sprintf_stub if name == 'libc_sprintf' else self.make_stub(name, ext)
            emu.stub(ext.addr, function=stub, name=name)
        self.calls, self.unknown, self.pcs = [], {}, set()
        self.partial, self.partial_ops = [], {}
        for start, end in list(BODIES.values()) + OTHER_SPANS:
            for pc in range(start, end, 4):
                word = emu.mem.u32(pc)
                if word >> 26 in (0x2A, 0x2C, 0x2D, 0x2E):
                    self.partial_ops[pc] = word >> 26
                    emu.hook(pc, self.partial_hook(pc, (word >> 21) & 31, ee_emu.sx16(word)))
        self.eview = D.View(emu.mem.load, self._epoke)
        self.touched = set()
        self.script_rng = None

    def partial_hook(self, pc, base, offset):
        def note(emu):
            ea = (emu.r[base] + offset) & M32
            if not is_stack(ea):
                self.partial.append((pc, ea))
        return note

    def _epoke(self, addr, size, value):
        self.emu.mem.store(addr, size, value & ((1 << (8 * size)) - 1))
        self.touched.update(range(addr, addr + size))

    def stored_bytes(self, lo, hi):
        out, pending = set(), list(self.partial)
        for pc, addr, size, _value in self.emu.writes:
            op = self.partial_ops.get(pc)
            if op is not None:
                _ppc, ea = pending.pop(0)
                if op == 0x2C:
                    first, last = ea & ~7, ea
                elif op == 0x2D:
                    first, last = ea, ea | 7
                elif op == 0x2A:
                    first, last = ea & ~3, ea
                else:
                    first, last = ea, ea | 3
            else:
                first, last = addr, addr + size - 1
            if not lo <= first < hi and not is_stack(first):
                out.update(range(first, last + 1))
        return out

    def decode(self, ext, emu):
        mem, canon, outs = emu.mem, [], []
        for index, kind in enumerate(ext.ints):
            reg = emu.r[4 + index]
            if kind == 'q':
                canon.append(reg & M64)
            elif kind == 'S':
                ptr = reg & M32
                if is_stack(ptr):
                    text = bytearray()
                    while mem.u8(ptr + len(text)):
                        text.append(mem.u8(ptr + len(text)))
                    canon.append(('buf', bytes(text)))
                else:
                    canon.append(ptr)
            elif kind == 'w':
                outs.append(reg & M32)
            elif kind == 'v':
                canon.append(tuple(mem.u32((reg & M32) + 4 * j) for j in range(3)))
            elif kind == 'N':
                outs.append(('N', reg & M32))
            elif kind == 'M':
                pass
            else:
                canon.append(reg & M32)
        for j in range(ext.floats):
            canon.append(emu.f[12 + j] & M32)
        return tuple(canon), outs

    def make_stub(self, name, ext):
        def stub(emu):
            canon, outs = self.decode(ext, emu)
            self.calls.append((name, canon))
            res = self.world.respond(name, canon, self.eview, self.script_rng)
            given = list(res.outs)
            for ptr in outs:
                if isinstance(ptr, tuple):              # a vector the callee fills
                    words = given.pop(0) if given else (0, 0, 0)
                    for j, word in enumerate(words):
                        emu.mem.w32(ptr[1] + 4 * j, word)
                else:
                    emu.mem.w32(ptr, given.pop(0) if given else 0)
            if ext.ret == 'f':
                emu.f[0] = res.f & M32
            return res.ret
        return stub

    def sprintf_stub(self, emu):
        """libc_sprintf(buffer, format[, value]): recorded as (format, value) when the format
        has a conversion, else (format,); the buffer gets the text the library would write."""
        buf, fmt, value = emu.r[4] & M32, emu.r[5] & M32, emu.r[6] & M32
        text = bytearray()
        while emu.mem.u8(fmt + len(text)):
            text.append(emu.mem.u8(fmt + len(text)))
        if b'%' in text:
            self.calls.append(('libc_sprintf', (fmt, value)))
            out = G.PP.render(bytes(text), value)
        else:
            self.calls.append(('libc_sprintf', (fmt,)))
            out = bytes(text)
        emu.mem.write(buf, out + b'\0')
        return 0

    class Callbacks:
        def __init__(self, rig, view, rng):
            self.rig, self.view, self.rng = rig, view, rng

        def get(self, name):
            ext = STUBBED.get(name)
            if ext is None or name == 'libc_sprintf':
                return None

            def answer(*args):
                res = self.rig.world.respond(name, args, self.view, self.rng)
                if 'N' in ext.ints:
                    return res.f & M32, tuple(res.outs[0]) if res.outs else (0, 0, 0)
                if 'w' in ext.ints:
                    n = ext.ints.count('w')
                    return tuple((list(res.outs) + [0] * n)[:n])
                if ext.ret == 'f':
                    return res.f & M32
                if ext.ret == 'n':
                    return None
                return res.ret & M32
            return answer

    def run_steps(self, steps, call_seed, key=''):
        """steps: ('poke', addr, size, value) or ('call', key, args).  Model first, then the
        original, on the same starting memory."""
        emu, mem = self.emu, self.emu.mem
        gold_before = [mem.u32(G.record(s) + G.REC_GOLD) for s in range(4)]
        seed_before = mem.u32(RC.G_RAND_SEED)
        cosmetic_before = mem.u32(G.G_COSMETIC_SEED)
        mview = D.ModelView(mem)
        model = G.Model(mview, Rig.Callbacks(self, D.View(mview.load, mview.poke), random.Random(call_seed)))
        out = {'fault': None, 'calls': None, 'writes': None, 'seed': None, 'result': None, 'draws': 0,
               'cosmetic': 0, 'model_calls': model.calls, 'emu_calls': None}
        model_error, mrets = None, []
        try:
            for step in steps:
                if step[0] == 'note':
                    continue
                if step[0] == 'poke':
                    mview.poke(step[1], step[2], step[3])
                else:
                    _addr, _kinds, _rk, method = ENTRIES[step[1]]
                    mrets.append(getattr(model, method)(*step[2]))
        except EmuError as exc:
            model_error = exc
        self.calls, self.touched, self.partial = [], set(), []
        out['emu_calls'] = self.calls
        self.script_rng = random.Random(call_seed)
        emu.reset_log()
        emu.trace = []
        emu_error, erets = None, []
        scratch = self.world.argbuf
        try:
            for step in steps:
                if step[0] == 'note':
                    continue
                if step[0] == 'poke':
                    self._epoke(step[1], step[2], step[3])
                    continue
                addr, kinds, _rk, _method = ENTRIES[step[1]]
                emu.r[29] = emu.stack_hi - 0x800
                regs = []
                for value, kind in zip(step[2], kinds):
                    if kind == 'v':
                        for j in range(3):
                            mem.w32(scratch + 4 * j, value[j])
                        regs.append(scratch)
                        scratch += 0x10
                    elif kind == 'q':
                        regs.append(value & M64)
                    else:
                        regs.append(ee_emu.s32(value & M32))
                erets.append(emu.call(addr, *regs, max_steps=4000000))
        except EmuError as exc:
            emu_error = exc
        self.pcs.update(emu.trace)
        for call in emu.calls:
            if call.target not in REAL and call.target not in self.names and not LIB_LO <= call.target < LIB_HI:
                self.unknown[call.target] = self.unknown.get(call.target, 0) + 1
        if model_error or emu_error:
            if (model_error is None) != (emu_error is None):
                out['fault'] = 'model %r / original %r' % (model_error, emu_error)
            return out
        if model.calls != self.calls:
            out['calls'] = DC.describe_calls(model.calls, self.calls)
        lo, hi = self.world.argbuf, self.world.argbuf + 0x400
        stored = self.stored_bytes(lo, hi)
        mstored = set()
        for a, size, _v in model.writes:
            if not is_stack(a):
                mstored.update(range(a, a + size))
        diff = [a for a in sorted(stored | mstored | self.touched | mview.touched)
                if mem.load(a, 1) != mview.load(a, 1)]
        if stored != mstored or diff:
            out['writes'] = 'only original %s; only model %s; values differ at %s' % (
                sorted('%x' % a for a in stored - mstored)[:8],
                sorted('%x' % a for a in mstored - stored)[:8],
                ['%x:%02x/%02x' % (a, mem.load(a, 1), mview.load(a, 1)) for a in diff[:8]])
        problems = []
        expect = seed_before
        for _ in range(model.draws):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(RC.G_RAND_SEED) == mview.load(RC.G_RAND_SEED, 4) == expect:
            problems.append('shared: model draws %d original %08x model %08x' % (
                model.draws, mem.u32(RC.G_RAND_SEED), mview.load(RC.G_RAND_SEED, 4)))
        expect = cosmetic_before
        for _ in range(model.cosmetic):
            expect = (expect * 0x19660D + 0x3C6EF35F) & M32
        if not mem.u32(G.G_COSMETIC_SEED) == mview.load(G.G_COSMETIC_SEED, 4) == expect:
            problems.append('cosmetic: model draws %d original %08x model %08x' % (
                model.cosmetic, mem.u32(G.G_COSMETIC_SEED), mview.load(G.G_COSMETIC_SEED, 4)))
        if problems:
            out['seed'] = '; '.join(problems)
        out['draws'], out['cosmetic'] = model.draws, model.cosmetic
        out['outcomes'] = outcomes(model, key)
        note = steps[0][1] if steps[0][0] == 'note' else None
        if note and note['clean'] and 'taken' in out['outcomes']:
            paid = sum(ee_emu.s32(mview.load(G.record(s) + G.REC_GOLD, 4) - gold_before[s]) for s in range(4))
            if paid == note['value']:
                out['outcomes'].add('clean: paid in full')
            elif 0 < paid < note['value']:
                out['outcomes'].add('clean: paid partly')
            elif paid == 0:
                out['outcomes'].add('clean: nothing paid yet')
            else:
                out['outcomes'].add('clean: other (cap)')
        calls = [st for st in steps if st[0] == 'call']
        for step, eret, mret in zip(calls, erets, mrets):
            if ENTRIES[step[1]][2] == 'i' and (eret & M32) != ((mret or 0) & M32):
                out['result'] = '%s result %08x / %08x' % (step[1], eret & M32, (mret or 0) & M32)
        return out


def outcomes(model, key=''):
    """What a case did, from the model's calls and stores (both sides agreed on them)."""
    names = [name for name, _args in model.calls]
    gold_words = {G.record(s) + G.REC_GOLD for s in range(8)}
    out = set()
    if 'obj_delete' in names:
        out.add('deleted: 120 below the player' if key in ('propRun', 'dropLife') else 'taken')
    if any(a in gold_words for a, _size, _v in model.writes):
        out.add('credited')
    if any(G.FLOATERS + 0x1C <= a < G.FLOATERS + 8 * G.FLOATER_SIZE and (a - G.FLOATERS) % G.FLOATER_SIZE == 0x1C
           and v for a, size, v in model.writes if size == 4):
        out.add('floater filled')
    if model.cosmetic == 0 and 'taken' in out and 'credited' in out:
        out.add('direct credit')
    if any(name == 'res_find' and args[1] == G.S_COIN_DROP for name, args in model.calls):
        out.add('drop sound')
    if 'obj_stopRunning' in names:
        out.add('stopped')
    if 'obj_runEveryFrame' in names:
        out.add('runs every frame')
    if 'player_voice' in names:
        out.add('refused: load')
    if any(name == 'res_find' and args[1] == G.S_CANTDO for name, args in model.calls):
        out.add('refused: bag')
    if 'inventory_giveItem' in names:
        out.add('given x%d' % names.count('inventory_giveItem'))
    if 'PhProp_dtor' in names or 'ItemProp_dtor' in names or 'Prop_dtor' in names:
        out.add('prop deleted')
    if 'terrain_sweepCircle' in names:
        out.add('swept')
    if any(name == 'libc_sprintf' and len(args) == 2 for name, args in model.calls):
        out.add('count text')
    return out


class Coverage(DC.Coverage):
    def __init__(self, mem):
        self.parts = {name: (start, end) + DC.analyse(mem, start, end) for name, (start, end) in BODIES.items()}
        self.pcs = set()


# ---------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------
def _pos(rng):
    return tuple(f32(rng.uniform(-4000, 4000)) for _ in range(3))


def _fill(mem, addr, size, rng, zero):
    for off in range(0, size, 4):
        mem.w32(addr + off, 0 if zero else rng.getrandbits(32))


def _view_proj(mem, rng):
    """g_viewProj: a camera looking at the scene (w = depth around 20..3000), or junk."""
    r = rng.random()
    if r < 0.15:
        m = [rng.uniform(-3, 3) for _ in range(16)]
    elif r < 0.2:
        m = [0.0] * 16
    else:
        s = rng.uniform(0.5, 3)
        m = [s, 0, 0, 0,
             0, s * rng.choice((1, -1)), 0, 0,
             rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), 0.3, 1.0,
             rng.uniform(-3000, 3000), rng.uniform(-3000, 3000), rng.uniform(-50, 50), rng.uniform(-200, 1500)]
    for j, v in enumerate(m):
        mem.w32(G.G_VIEW_PROJ + 4 * j, f32(v))


def _amount(rng):
    return rng.choice((0, 1, 7, 25, 120, 999, 0x7FFFFFFF, 0xFFFFFFFF, rng.randrange(1, 5000)))


def _gold_word(rng):
    return rng.choice((0, 500, 99999990, 99999999, 100000000, 0x7FFFFFF0, 0xFFFFFFFF, rng.randrange(0, 10 ** 6)))


def _floaters(mem, rng, frame, busy=None):
    """The eight floaters: free, busy around the 43-frame edge, or all busy."""
    if busy is None:
        busy = rng.choice((0.0, 0.3, 0.7, 1.0, 1.0))
    for k in range(8):
        e = G.floater(k)
        _fill(mem, e, 0x24, rng, False)
        if rng.random() < busy:
            mem.w32(e + 0x1C, _amount(rng) or 5)
        else:
            mem.w32(e + 0x1C, 0)
        start = (frame - rng.choice((0, 1, 42, 43, 44, 100, -5, rng.randrange(0, 1 << 32)))) & M32
        mem.w32(e + 0x18, start)
        mem.w8(e + 0x20, rng.choice((0, 1, 2, 3, 0, 1, 0xFF)))


def _records(mem, rng):
    for slot in range(4):
        rec = G.record(slot)
        mem.w32(rec + G.REC_GOLD, _gold_word(rng))
        mem.w32(G.G_GOLD_PENDING + 4 * slot, rng.choice((0, 0, 1, 7, 8, 9, 64, 1000, -3 & M32, 0x7FFFFFF9,
                                                          rng.randrange(0, 10 ** 5))))
        for base in G.FLUSH_CLEARED:
            mem.w32(base + 4 * slot, rng.getrandbits(32))


def _frame(mem, rng):
    frame = rng.choice((0, 18, 43, 1000, 0x7FFFFFF0, rng.randrange(0, 1 << 20)))
    mem.w32(G.G_SIM_FRAME, frame)
    return frame


def _player_records(rig, rng):
    w, mem = rig.world, rig.emu.mem
    for slot in range(5):
        rec = G.record(slot)
        for cat in range(-1, 4):
            mem.w32((rec + G.REC_BAG_COUNT + cat * G.BAG_SIZE) & M32,
                    rng.choice((0, 5, 62, 63, 64, 65, 0x7FFFFFFF, rng.randrange(0, 64))))
        load = rng.choice((0.0, 10.0, 99.0, 100.0, 150.0, rng.uniform(0, 300)))
        mem.w32(rec + G.REC_LOAD, f32(load))
        mem.w32(rec + G.REC_LIMIT, f32(rng.choice((100.0, 125.0, 9999.0, load, load + 1.0, load + 2.5,
                                                    rng.uniform(0, 300)))))
        mem.w32(rec + G.REC_OBJ, rng.choice((0, w.people[slot % 4])))


def _item(rig, rng, at):
    """An item record at `at`: a definition with a category byte, a 64-bit flag word."""
    w, mem = rig.world, rig.emu.mem
    _fill(mem, at, 0x48, rng, False)
    d = rng.choice(w.defs)
    mem.w32(at, d)
    mem.w8(d + 0x1D, rng.choice((0, 1, 2, 2, 0xFF, 3)))
    mem.w16(d + 0x34, rng.randrange(0, 80))
    bits = rng.choice((0, 0x800000, 0x200000, 0x40000, 0x100000, 0x80000, 0x1000000, 0x4000000, 0x2000000,
                       0x10000000, 0xA00000, 0x1080000, 1 << 39, 1 << 36 | rng.getrandbits(16) & 0xF800,
                       rng.getrandbits(64) & ~(1 << 36)))
    mem.w64(at + 8, bits)
    mem.w16(at + 4, rng.choice((0, 1, 2, 5, 0xFFFD, 0x7FFF, 0x8000)))


def generate(rig, key, rng):
    """One case: a list of steps."""
    w, mem = rig.world, rig.emu.mem
    mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
    mem.w32(G.G_COSMETIC_SEED, rng.getrandbits(32))
    frame = _frame(mem, rng)
    _view_proj(mem, rng)
    _floaters(mem, rng, frame)
    _records(mem, rng)
    mem.w32(G.G_NUM_PLAYERS, rng.choice((0, 1, 2, 3, 4, 4)))
    if key == 'goldRun':
        gold = rng.choice(w.golds)
        _fill(mem, gold, 0xC0, rng, rng.random() < 0.3)
        mem.w8(gold + 0x4C, rng.choice((0, 1, 2, 0x29, 0x80, 0xFF, rng.randrange(256))))
        mem.w32(gold + 0x50, (frame - G.COIN_SOUND_AT) & M32 if rng.random() < 0.4 else rng.getrandbits(32))
        mem.w16(gold + 0x5E, rng.choice((0, 0x80, 0xFF7F, 0xFFFF, rng.getrandbits(16))))
        return [('call', key, (gold,))]
    if key == 'goldTouch':
        gold, other = rng.choice(w.golds), rng.choice(w.people)
        _fill(mem, gold, 0xC0, rng, False)
        mem.w8(gold + 0x4C, rng.choice((0, 0, 0, 1, 0x29, 0x80)))
        mem.w32(gold + 0x80, _amount(rng))
        _fill(mem, other, 0x400, rng, False)
        mem.w32(other + 0xC, rng.choice((0x40, 0x60, 0x4060, 0x20060, 0x20040, 0x20, 0, 0x40 | rng.getrandbits(17),
                                         rng.getrandbits(32))))
        mem.w32(other + 0x3C8, rng.choice((0, 1, 2, 3, 0, 1, 5)))
        return [('call', key, (gold, other))]
    if key == 'floater':
        slot = rng.choice((0, 1, 2, 3, 3, 6))
        pos = _pos(rng)
        if rng.random() < 0.4:                  # the off-screen edges: w 20, |x| 700 w, |y| 300 w
            wv = rng.choice((19.99, 20.0, 20.01, 30.0, 100.0, 250.0))
            m = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, wv]
            for j, v in enumerate(m):
                mem.w32(G.G_VIEW_PROJ + 4 * j, f32(v))
            kx = rng.choice((0.0, 699.5, 700.0, 700.4, 702.0, 705.0, 710.0))
            ky = rng.choice((0.0, 299.5, 300.0, 300.4, 301.0, 303.0, 310.0))
            pos = (f32(wv * kx * rng.choice((1, -1))), f32(wv * ky * rng.choice((1, -1))), f32(rng.uniform(-50, 50)))
        return [('call', key, (slot, pos, _amount(rng)))]
    if key in ('tickGold', 'flushGold'):
        return [('call', key, ())]
    if key == 'tryPickup':
        _player_records(rig, rng)
        item = rng.choice(w.items)
        _item(rig, rng, item)
        return [('call', key, (rng.choice((0, 1, 2, 3)), item))]
    if key in ('phInteract', 'itemInteract'):
        _player_records(rig, rng)
        prop = rng.choice(w.props)
        _fill(mem, prop, 0x280, rng, False)
        mem.w32(prop + 0x48, G.VT_PHPROP if key == 'phInteract' else G.VT_ITEMPROP)
        _item(rig, rng, prop + 0x148)
        if rng.random() < 0.4:
            mem.w64(prop + 0x150, mem.u64(prop + 0x150) | G.ITEM_ALL_PLAYERS)
        return [('call', key, (prop, rng.choice((0, 1, 2, 3))))]
    if key in ('phPrompt', 'itemPrompt'):
        prop = rng.choice(w.props)
        _fill(mem, prop, 0x280, rng, False)
        mem.w16(prop + 0x14C, rng.choice((0, 1, 2, 3, 99, 0xFFFF, 0x8000, 0x7FFF)))
        return [('call', key, (prop, w.outbuf))]
    if key == 'itemCtor3':
        obj = rng.choice(w.props)
        _fill(mem, obj, 0x280, rng, rng.random() < 0.5)
        item = rng.choice(w.items)
        _item(rig, rng, item)
        _fill(mem, w.matrix, 0x40, rng, False)
        return [('call', key, (obj, _pos(rng), item, w.matrix))]
    if key == 'itemCtor2':
        obj = rng.choice(w.props)
        _fill(mem, obj, 0x280, rng, rng.random() < 0.5)
        item = rng.choice(w.items)
        _item(rig, rng, item)
        mem.w32(G.PP.G_PROP_OPTIONS, rng.choice((0, 0, 0x100, rng.getrandbits(32))))
        launch = rng.choice((0, 0x19, 0x9, 0x11, 0x1, 0x8, 0x80, 0x181, 0x2041, 0x10020, rng.getrandbits(17)))
        return [('call', key, (obj, _pos(rng), item, launch))]
    if key == 'propNamed':
        obj = rng.choice(w.props)
        _fill(mem, obj, 0x280, rng, rng.random() < 0.5)
        _fill(mem, w.matrix, 0x40, rng, False)
        names = [rng.choice(w.names) for _ in range(3)]
        mask = rng.choice((0xFFFFFFFFFFFFFFFF, 0, 1, 1 << 63, rng.getrandbits(64)))
        flags = rng.choice((0, 1, 2, 4, 6, 7, 0xFFFF, rng.getrandbits(16)))
        return [('call', key, (obj, _pos(rng), names[0], names[1], names[2], mask, flags, w.matrix))]
    if key == 'itemLife':
        return item_life(rig, rng, frame)
    if key == 'propRun':
        return [('call', key, (_moving_prop(rig, rng),))]
    if key == 'dropLife':
        return drop_life(rig, rng, frame)
    return pile(rig, rng, frame)


def _alive(rig, rng):
    """g_alivePlayers[0] and the z of that record's object (the 120-below test)."""
    w, mem = rig.world, rig.emu.mem
    alive = rng.choice((0, 1, 2, 3, -1 & M32))
    mem.w32(G.G_ALIVE_PLAYERS, alive)
    for slot in range(4):
        mem.w32(G.record(slot) + G.REC_OBJ, rng.choice((0, w.people[slot])))
        mem.wf32(w.people[slot] + 0x18, rng.choice((0.0, 100.0, -200.0, rng.uniform(-500, 500))))


def _moving_prop(rig, rng):
    """A Prop or ItemProp as a launch leaves it, or one that has run a while."""
    w, mem = rig.world, rig.emu.mem
    _alive(rig, rng)
    prop = rng.choice(w.props)
    _fill(mem, prop, 0x280, rng, False)
    mem.w32(prop + 0x48, rng.choice((G.VT_ITEMPROP, G.PP.VT_PROP)))
    mem.w16(prop + 0x140, rng.choice((0, 0, 1, 2, 3, 4, 0x10, rng.getrandbits(16))))
    mem.w16(prop + 0x10E, rng.choice((180, 2, 1, 0, 0xFFFF, (-60) & 0xFFFF, (-61) & 0xFFFF, (-300) & 0xFFFF,
                                      (-301) & 0xFFFF, 0x7FFF, rng.getrandbits(16))))
    mem.w16(prop + 0x10C, rng.choice((0, 5, 10, 11, 2000, 0x8000, rng.getrandbits(16))))
    for off, choices in ((0xFC, (0.0, 0.01, 0.06, 40.0, -120.0)), (0x100, (0.0, -0.05, 30.0, 200.0)),
                         (0x30, (0.0, 27.0, -0.2, -5.0, 300.0, -400.0)), (0x108, (0.0, 3.0, 12.0)),
                         (0x1C, (4.0, 24.0))):
        mem.wf32(prop + off, rng.choice(choices + (rng.uniform(-300, 300),)))
    for j in range(3):
        mem.wf32(prop + 0x10 + 4 * j, rng.uniform(-500, 500))
    if rng.random() < 0.3:                      # the 120-below edge, on a prop at rest
        mem.w16(prop + 0x140, mem.u16(prop + 0x140) | 1)
        mem.w16(prop + 0x10E, rng.choice((50, 2, 0)))
        mem.w32(G.G_NUM_PLAYERS, rng.choice((1, 2)))
        mem.w32(G.G_ALIVE_PLAYERS, 0)
        mem.w32(G.record(0) + G.REC_OBJ, w.people[0])
        z = DC.fl(mem.u32(prop + 0x18))
        mem.wf32(w.people[0] + 0x18, z + rng.choice((119.9, 120.0, 120.05, 120.5, 121.0, 122.0, 125.0)))
    return prop


def drop_life(rig, rng, frame):
    """An item dropped from the bag or given at full load: ItemProp_ctor2 with launch 0 (every
    call site's), then N ticks of Prop_run (slot 4), then the use button."""
    w, mem = rig.world, rig.emu.mem
    _player_records(rig, rng)
    _alive(rig, rng)
    obj = rng.choice(w.props)
    _fill(mem, obj, 0x280, rng, True)
    item = rng.choice(w.items)
    _item(rig, rng, item)
    mem.w32(G.PP.G_PROP_OPTIONS, rng.choice((0, 0, 0x100)))
    steps = [('call', 'itemCtor2', (obj, _pos(rng), item, rng.choice((0, 0, 0, 0x19, 0x81))))]
    for i in range(1, rng.choice((1, 30, 179, 180, 181, 200, 250, 400)) + 1):
        steps.append(('poke', G.G_SIM_FRAME, 4, (frame + i) & M32))
        steps.append(('call', 'propRun', (obj,)))
    steps.append(('call', 'itemInteract', (obj, rng.choice((0, 1, 2, 3)))))
    return steps


def item_life(rig, rng, frame):
    """An item comes to rest (ItemProp_ctor3 on a zero-filled 0x190 block), is prompted a few
    ticks while a player stands by, then the use button: ItemProp_interact."""
    w, mem = rig.world, rig.emu.mem
    _player_records(rig, rng)
    obj = rng.choice(w.props)
    _fill(mem, obj, 0x280, rng, True)
    item = rng.choice(w.items)
    _item(rig, rng, item)
    _fill(mem, w.matrix, 0x40, rng, False)
    steps = [('call', 'itemCtor3', (obj, _pos(rng), item, w.matrix))]
    for i in range(1, rng.choice((1, 2, 5)) + 1):
        steps.append(('poke', G.G_SIM_FRAME, 4, (frame + i) & M32))
        steps.append(('call', 'itemPrompt', (obj, w.outbuf)))
    steps.append(('call', 'itemInteract', (obj, rng.choice((0, 1, 2, 3)))))
    return steps


def pile(rig, rng, frame):
    """The multi-frame life of one pile: built by the real Gold_ctor2 on a zero-filled 0xc0
    block (pool_new's), N ticks of Gold_run, a touch, M ticks of hud_tickGold."""
    w, mem = rig.world, rig.emu.mem
    gold = rng.choice(w.golds)
    _fill(mem, gold, 0x100, rng, True)
    r = rng.random()
    clean = r < 0.75
    if clean:                                   # a fresh level: nothing pending, floaters free or all busy
        _floaters(mem, rng, frame, busy=1.0 if r < 0.15 else 0.0)
        for k in range(8):                      # busy ones that will not fall due in this case
            mem.w32(G.floater(k) + 0x18, (frame + 100000) & M32)
            mem.w8(G.floater(k) + 0x20, rng.choice((0, 1, 2, 3)))
        for slot in range(4):
            mem.w32(G.G_GOLD_PENDING + 4 * slot, 0)
            mem.w32(G.record(slot) + G.REC_GOLD, rng.choice((0, 500, 99999000, rng.randrange(0, 10 ** 6))))
    value = rng.choice((0, 1, 25, 120, 4000, 99999999, rng.randrange(1, 900)))
    steps = [('note', {'clean': clean, 'value': value})]
    steps.append(('call', 'goldCtor2', (gold, _pos(rng), value)))
    ticks = rng.choice((0, 10, 18, 40, 41, 42, 45, 60, rng.randrange(0, 70)))
    for i in range(1, ticks + 1):
        steps.append(('poke', G.G_SIM_FRAME, 4, (frame + i) & M32))
        steps.append(('call', 'goldRun', (gold,)))
    touchers = []
    for k in range(rng.choice((1, 1, 1, 2))):
        other = w.people[k]
        _fill(mem, other, 0x400, rng, False)
        mem.w32(other + 0xC, rng.choice((0x4060, 0x4060, 0x4060, 0x20060, 0x60, 0x4020)))
        mem.w32(other + 0x3C8, rng.choice((0, 1, 2, 3)))
        touchers.append(other)
    for other in touchers:
        steps.append(('call', 'goldTouch', (gold, other)))
    after = rng.choice((0, 1, 42, 43, 44, 50, 60, 80, 120, 200))
    for i in range(1, after + 1):
        steps.append(('poke', G.G_SIM_FRAME, 4, (frame + ticks + i) & M32))
        steps.append(('call', 'tickGold', ()))
    if rng.random() < 0.15:
        steps.append(('call', 'flushGold', ()))
    return steps


def main(argv):
    args, elf = list(argv), None
    while args:
        item = args.pop(0)
        if item == '--quick':
            OPTIONS['quick'] = True
        elif item == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif item == '--cases':
            OPTIONS['cases'] = int(args.pop(0), 0)
        elif item == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif item == '-v':
            OPTIONS['verbose'] = True
        elif item == '--trace-first':
            OPTIONS['trace_first'] = True
        else:
            elf = item
    if elf is None:
        for candidate in (os.path.join(ROOT, 'SLUS_209.73'), os.path.join(ROOT, 'local', 'SLUS_209.73')):
            if os.path.exists(candidate):
                elf = candidate
                break
    if elf is None or not os.path.exists(elf):
        print('difftest_gold: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_gold: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    RC.C.set_fpu('ps2')
    cases = max(OPTIONS['cases'] // 10, 1) if OPTIONS['quick'] else OPTIONS['cases']
    started = time.time()
    rig = Rig(elf)
    coverage = Coverage(rig.emu.mem)
    rng = random.Random(OPTIONS['seed'])
    counts, total = {}, 0
    for key in SINGLE:
        if OPTIONS['filter'] and OPTIONS['filter'] not in key:
            continue
        bad = {'fault': [], 'calls': [], 'writes': [], 'seed': [], 'result': []}
        draws = cosmetic = 0
        seen = {}
        n_cases = max(cases // 3, 1) if key == 'pile' else cases
        for n in range(n_cases):
            call_seed = OPTIONS['seed'] * 1000003 + total
            steps = generate(rig, key, rng)
            result = rig.run_steps(steps, call_seed, key)
            total += 1
            draws += result['draws']
            cosmetic += result['cosmetic']
            for what in result.get('outcomes', ()):
                seen[what] = seen.get(what, 0) + 1
            failed = False
            for prop in bad:
                if result[prop]:
                    failed = True
                    bad[prop].append('case %d %s: %s' % (n, key, result[prop]))
            if failed and OPTIONS['trace_first']:
                print('first mismatch: %s case %d %s' % (key, n, steps if len(steps) < 12 else steps[:12]))
                for prop in bad:
                    if result[prop]:
                        print('  %s: %s' % (prop, result[prop]))
                print('  model calls:')
                for call in result['model_calls'][:60]:
                    print('    ' + DC.fmt_call(call))
                print('  original calls:')
                for call in (result['emu_calls'] or ())[:60]:
                    print('    ' + DC.fmt_call(call))
                return 1
        counts[key] = (n_cases, sum(len(v) for v in bad.values()), draws, cosmetic, seen)
        for prop, examples in bad.items():
            DC.report('%s %s' % (key, prop), len(examples), n_cases, prop, examples)
    if rig.unknown:
        DC.report('unknown calls', len(rig.unknown), total, 'calls to neither real nor stubbed addresses',
                  ['%x x%d' % kv for kv in sorted(rig.unknown.items())])
    coverage.pcs = rig.pcs
    print()
    print('cases per entry / with any mismatch / shared draws / cosmetic draws')
    for key, (n, bad_n, draws, cosmetic, seen) in counts.items():
        print('  %-14s %6d / %d / %d / %d   %s' % (key, n, bad_n, draws, cosmetic,
                                                ', '.join('%s %d' % kv for kv in sorted(seen.items()))))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for part in BODIES:
        b, bt, i, it = coverage.numbers(part)
        print('  %-24s blocks %4d of %4d  instructions %4d of %4d' % (part, b, bt, i, it))
        if OPTIONS['verbose'] and b != bt:
            print('      never entered: %s' % ' '.join('%06x' % a for a in coverage.missing(part)))
    print('%d cases in %.0f s' % (total, time.time() - started))
    return 0 if all(ok for _name, ok in DC.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
