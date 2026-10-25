#!/usr/bin/env python3
"""difftest_holder_slots.py - compare tools/ref_holder_slots.py with the game's own code:
slots 18-24 of the weapon holders Weapon1, WeaponShield and Weapon2 (drawing, the
per-frame effect update, save and load), creature_drawHeldPart, and Weapon2's slots 8
and 16 (which Weapon2's save and load reach through the table).

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 -u tools/difftest_holder_slots.py [path/to/SLUS_209.73] [--seed N] [--cases N]
                                            [--quick] [-v] [--trace-first]

What is compared
    Holders of the three classes, with the game's own table at +0, random hand bits,
    parts, descriptors (both of Weapon2's) and effect-block bytes, are handed to each of
    slots 18-24 taken from the table, with the slot's arguments (definitions, parents,
    creatures, buffers, f12) drawn from a scripted world; Weapon2's slots 8 and 16 and
    creature_drawHeldPart are also called directly.  Runs for real: everything in
    ref_holder_slots.EXECUTED and ref_weapon_holder.EXECUTED (the save and load slots
    reach slots 8 and 16 through the table, and so creature_buildElementDamage and
    damageDesc_getElement), and the C library.  Recording stubs answered by the world:
    model_drawPart, model_getAttachPoint, model_getAttachWorldMatrix, model_draw,
    isNearView, fx_modelStatusEffects, the creature's slot 16 and the Skills' slot 11.
    Each call runs through the model first on a copy-on-write view, and these must be
    equal: the callbacks in order with every argument (vectors and matrices read at the
    call, the stack arguments, f12/f13), every byte stored outside the stack, the shared
    seed 0x404464 with its draw count, the result.
"""
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_weapon_holder as WH                  # noqa: E402
import ref_holder_slots as HS                   # noqa: E402
import difftest_weapon_holder as DWH            # noqa: E402

M32, M64 = RC.M32, RC.M64
OPTIONS = DWH.OPTIONS
Answer = DWH.Answer
f32 = DWH.f32


def vec_at(emu, addr, n=3):
    return tuple(emu.mem.u32((addr + 4 * k) & M32) for k in range(n))


def write_words(reg, n):
    def writer(emu, answer):
        if answer.outs is not None:
            for k in range(n):
                emu.mem.w32(((emu.r[reg] & M32) + 4 * k) & M32, answer.outs[k] & M32)
    return writer


def sp_word(emu, off):
    return emu.mem.u32(((emu.r[29] & M32) + off) & M32)


regs = DWH.regs
STUBS = {
    'Skill.v11': (None, regs(4, 5, 6, 7), None),
    'Creature.v16': (None, regs(4), None),
    # (part, tex, layer, parent, chain, showMask, slotOverride, table)
    'model_drawPart': (0x178C28, regs(4, 5, 6, 7, 8, 9, 10, 11), None),
    # (scale f12, model, position copy, facing, anim, bone, second out t2); point out t1
    'model_getAttachPoint': (0x1754A0, lambda e: (e.f[12] & M32, e.r[4] & M32, vec_at(e, e.r[5]), e.r[6] & M32,
                                                   e.r[7] & M32, e.r[8] & M32, e.r[10] & M32), write_words(9, 3)),
    # (scale f12, model, position copy, facing, anim, bone); matrix out t1 (twelve words)
    'model_getAttachWorldMatrix': (0x175330, lambda e: (e.f[12] & M32, e.r[4] & M32, vec_at(e, e.r[5]),
                                                         e.r[6] & M32, e.r[7] & M32, e.r[8] & M32),
                                   write_words(9, 12)),
    # (model, model, 1, point, matrix, anim, 64-bit t2 as (lo, hi), t3, stack word 0)
    'model_draw': (0x1779B0, lambda e: (e.r[4] & M32, e.r[5] & M32, e.r[6] & M32, vec_at(e, e.r[7]),
                                        vec_at(e, e.r[8], 12), e.r[9] & M32, (e.r[10] & M32, (e.r[10] >> 32) & M32),
                                        e.r[11] & M32, sp_word(e, 0)), None),
    # (position pointer, the vector there, radius f12)
    'isNearView': (0x1E77C0, lambda e: (e.r[4] & M32, vec_at(e, e.r[4]), e.f[12] & M32), None),
    # (f12, f13; descriptor, model word, effect block, position copy, facing, model, anim,
    #  attacking; stack words 0 and 8)
    'fx_modelStatusEffects': (0x1F6AC8, lambda e: (e.f[12] & M32, e.f[13] & M32) + tuple(
        e.r[i] & M32 for i in (4, 5, 6)) + (vec_at(e, e.r[7]),) + tuple(e.r[i] & M32 for i in (8, 9, 10, 11))
        + (sp_word(e, 0), sp_word(e, 8)), None),
}

SEEN = {}                                       # callback name -> calls the original made
TABLES = {'Weapon1': HS.VT_WEAPON1, 'WeaponShield': HS.VT_WEAPONSHIELD, 'Weapon2': HS.VT_WEAPON2}
ELEMENT_BYTES = (0, 0, 1, 2, 3, 4, 5, 6, 6, 7, 0x80, 0xFF)
F12S = (0x3F000000, 0x3F000000, 0x3F800000, 0, 0xBF800000, 0x42C80000)
STATES = (0, 3, 5, 6, 6, 7, 8, 10, 15, 16, 0x14, 0xFFFF, 0x8006)


class World(DWH.World):
    def build(self, stub_addr):
        DWH.World.build(self, stub_addr)
        emu, mem = self.emu, self.mem
        self.holders = [emu.alloc(0x140) for _ in range(4)]
        self.buffers = [emu.alloc(0x10) for _ in range(2)]

    def randomise_creature(self, c):
        DWH.World.randomise_creature(self, c)
        mem, rng = self.mem, self.rng
        mem.w8(c + 0x231, rng.choice((0, 0, 0, 8, 0x10, 0xFF, 0xF7)))
        mem.w16(c + 0x232, rng.choice(STATES + (rng.randrange(0x10000),)))
        mem.w64(c + 0x220, rng.getrandbits(64))

    def randomise_holder(self, h, table):
        DWH.World.randomise_holder(self, h, table)
        mem, rng = self.mem, self.rng
        desc = h + HS.DESC2
        for k in range(8):
            mem.w16(desc + 0x10 + 2 * k, rng.choice((0, rng.randrange(0x10000))))
        for k in range(4):
            mem.w16(desc + 0x24 + 8 * k, rng.choice(DWH.IDS))
            for j in (2, 4, 6):
                mem.w16(desc + 0x24 + 8 * k + j, rng.randrange(0x10000))
        for off in range(0xC, 0x4C, 4):                       # the effect blocks: junk
            mem.w32(h + off, rng.getrandbits(32))
            mem.w32(h + HS.FX2 + off - 0xC, rng.getrandbits(32))

    def respond(self, name, args, rng):
        if name in ('Skill.v11', 'Creature.v16'):
            return DWH.World.respond(self, name, args, rng)
        if name == 'model_getAttachPoint':
            return Answer(0, outs=tuple(f32(rng.uniform(-3000, 3000)) for _ in range(3)))
        if name == 'model_getAttachWorldMatrix':
            return Answer(0, outs=tuple(f32(rng.uniform(-2, 2)) for _ in range(12)))
        if name == 'isNearView':
            return Answer(1 if rng.random() < 0.7 else 0)
        return Answer(rng.choice((0, 1, 0x00C00200)))


def make_rig(elf, seed):
    world = World.__new__(World)
    real = set(WH.EXECUTED.values()) | set(HS.EXECUTED.values())
    rig = DWH.MiniRig(elf, real, STUBS, world)
    DWH.World.__init__(world, rig.emu, random.Random(seed))
    world.build(rig.addr_of)
    return rig, world


def slot_args(world, slot, h, c, rng):
    """The slot's arguments after 'this' (and its f12)."""
    d = rng.choice(world.definitions + [0])
    nz = lambda: rng.choice((0x00C00040, 0x00C00080, 0x00C00300, 1, 0x80000000)) if rng.random() < 0.85 else 0
    if slot == 18:
        return (d, nz(), nz()), ()
    if slot == 19:
        return (nz(), nz(), nz(), nz()), ()
    if slot == 20:
        return (rng.choice((c, c, c, 0)),), ()
    if slot == 21:
        return (d, rng.choice((c, c, c, 0))), (rng.choice(F12S),)
    if slot == 22:
        return (nz(), rng.choice((c, c, c, 0))), (rng.choice(F12S),)
    buf = rng.choice(world.buffers)
    mem = world.mem
    for k in range(8):
        mem.w8(buf + k, rng.randrange(0x100))
    if slot == 24:
        mem.w8(buf, rng.choice((0, 1, 2, 3, 0x81, 0xFF)))
        mem.w8(buf + 1, rng.choice((0, 0x52, 0x60, rng.randrange(0x100))))
        mem.w8(buf + 2, rng.choice(ELEMENT_BYTES))
        mem.w8(buf + 3, rng.choice((0, 0x60, 0x62, 0x80)))
        mem.w8(buf + 4, rng.choice(ELEMENT_BYTES))
    return (buf,), ()


def run(elf, seed, cases, tally):
    rig, world = make_rig(elf, seed)
    mem, rng = rig.emu.mem, world.rng
    n = 0
    for case in range(cases):
        mem.w32(RC.G_LEVEL_MONSTER_LEVEL, f32(rng.choice(DWH.LEVELS)))
        mem.w32(RC.G_RAND_SEED, rng.getrandbits(32))
        cls = rng.choice(('Weapon1', 'WeaponShield', 'Weapon2'))
        table = TABLES[cls]
        h = rng.choice(world.holders)
        world.randomise_holder(h, table)
        c = rng.choice(world.creatures)
        world.randomise_creature(c)
        roll = rng.random()
        fargs = ()
        if roll < 0.05:
            fn = HS.DRAW_HELD_PART
            args = (h + 4, rng.choice((0, 1, 0x52, 0x60, 0xFF, 0x100)), rng.choice((c, c, c, 0)))
            key = 'creature_drawHeldPart'
        elif roll < 0.12:
            table = HS.VT_WEAPON2
            mem.w32(h, table)
            slot = rng.choice((8, 16))
            fn = mem.u32(table + 8 * slot + 4)
            hand = rng.choice(DWH.HANDS)
            args = (h, hand) + ((rng.choice((0, 1, 2, 3, 4, 5, 6, 7, 0x102, 0xFF)),) if slot == 8 else ())
            key = 'Weapon2 slot %d' % slot
        else:
            slot = rng.choice(range(18, 25))
            fn = mem.u32(table + 8 * slot + 4)
            this = (h + mem.s16(table + 8 * slot)) & M32
            extra, fargs = slot_args(world, slot, h, c, rng)
            args = (this,) + extra
            key = '%s slot %d (%06x)' % (cls, slot, fn)
        n += 1
        f12 = fargs[0] if fargs else 0
        result = rig.compare(fn, args, HS.Model, lambda m, fn=fn, args=args, f12=f12: m.entry(fn, *args, f12=f12),
                             seed * 1000003 + case, fargs=fargs, ret_kind='i' if fn in HS.RETURNS else 'n')
        tally.add(key, result, lambda: '%s%s f12 %s' % (key, tuple('%x' % (a & M32) for a in args), fargs))
        for name, _args in result['emu_calls']:
            SEEN[name] = SEEN.get(name, 0) + 1
    return rig, n


def main(argv):
    args = list(argv)
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--seed':
            OPTIONS['seed'] = int(args[i + 1], 0)
            i += 1
        elif a == '--cases':
            OPTIONS['cases'] = int(args[i + 1], 0)
            i += 1
        elif a == '--quick':
            OPTIONS['quick'] = True
        elif a == '-v':
            OPTIONS['verbose'] = True
        elif a == '--trace-first':
            OPTIONS['trace_first'] = True
        i += 1
    elf = DWH.find_elf(args)
    if not DWH.check_elf(elf, 'difftest_holder_slots'):
        return 0
    C.set_fpu('ps2')
    started = time.time()
    cases = OPTIONS['cases'] // 10 if OPTIONS['quick'] else OPTIONS['cases']
    tally = DWH.Tally('holder slots')
    total, trace, rig, stubs_seen = 0, set(), None, {}
    for k in range(2):                                          # two worlds per seed
        rig, n = run(elf, OPTIONS['seed'] + k, cases // 2, tally)
        trace |= rig.trace
        total += n
        if rig.unknown:
            print('FAIL  calls to addresses neither real nor stubbed: %s' % {hex(a): n for a, n in rig.unknown.items()})
            tally.bad.setdefault('unknown', []).append(str(rig.unknown))
    ok = tally.report()
    names = {addr: '%s_slot%d' % (cls, slot) for addr, (cls, slot, _m) in HS.SLOTS.items()}
    names[HS.DRAW_HELD_PART] = 'creature_drawHeldPart'
    print_lines = DWH.coverage_lines(trace, rig.emu.mem, sorted(HS.BODY_END.items()), names)
    DWH.print_coverage(print_lines, OPTIONS['verbose'])
    if OPTIONS['verbose']:
        for start, end in sorted(HS.BODY_END.items()):
            missed = [pc for pc in range(start, end, 4) if pc not in trace]
            if missed:
                print('  %-34s instructions not executed: %s' % (names[start], ' '.join('%06x' % pc for pc in missed)))
    print('callbacks the original made: %s' % ', '.join('%s %d' % kv for kv in sorted(SEEN.items())))
    print('%d calls compared (seed %d), %d shared draws, %d stopped on both sides; %.0f s' % (
        total, OPTIONS['seed'], tally.draws, tally.both, time.time() - started))
    return 0 if ok and 'unknown' not in tally.bad else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
