#!/usr/bin/env python3
"""Live HUD producers against the original SLUS-20973 v2.00 functions.

  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_hud_live.py local/SLUS_209.73 --seed 20973

Runs Player_regenHealth, Player_regenMana, the bar slice of hud_drawPlayerStatus,
player_giveExp, hud_showMessage, hud_tickMessage and the message alpha store.
External services are stubbed. No game bytes are printed.
"""
import argparse
import dis  # stdlib; tools/dis.py would shadow it once that directory is on the path
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ee_emu import EE
import ref_core as F
import ref_hud_live as L

PLAYER = L.PLAYER
STRIDE = L.STRIDE
SEEDS = (0x404460, 0x404464, 0x404468)
ORIGIN = 0x53C408
XP_TABLE = 0x41B558
TIMER = 0x4F66E0
FORCE = 0x4F66E2
ALPHA = 0x4F66EC
SUPPRESSED = 0x4F66A8
WARMUP = 0x506048
PLAYERS = 0x4D8AE0
NETWORK = 0x402791
LATCH = 0x4F66A9
MENU = 0x41B69D
TEXT = 0x86AB78


def draws(emu):
    return sum(1 for _pc, address, size, _value in emu.writes
               if address in SEEDS and size == 4)


def plant_floats(mem, record, pairs):
    for offset, value in pairs:
        mem.w32(record + offset, value & 0xFFFFFFFF)


def item(emu, kind, value):
    """One equipment record whose first real modifier is `kind`."""
    obj = emu.alloc(0x40)
    emu.mem.w32(obj, emu.alloc(4))
    emu.mem.w16(obj + 0x24, 1)
    emu.mem.w16(obj + 0x26, 99)
    emu.mem.w16(obj + 0x2C, kind & 0xFFFF)
    emu.mem.w16(obj + 0x2E, value & 0xFFFF)
    return obj


def blank_modifiers():
    return [None] * 17


def regen_cases(elf, rng):
    emu = EE(elf)
    emu.follow = set()
    box = {'passive': 0, 'spell': 0, 'blessed': 0, 'rank': 0, 'rank_value': 0}
    emu.stub(0x1BED48, function=lambda _e: box['passive'], name='player_getPassiveLevel')
    emu.stub(0x3CE700, ret=1, name='SpellBlessed_typeinfo')
    emu.stub(0x11A710, function=lambda _e: box['spell'], name='creature_findSpellByType')
    emu.stub(0x2DFDB8, function=lambda _e: box['blessed'], name='SpellBlessed_getStat0')
    emu.stub(0x1BF330, function=lambda _e: box['rank'], name='player_getSkillRank')
    emu.stub(0x2F14F0, function=lambda _e: box['rank_value'], name='SkillRegeneration_getStat0')
    obj = emu.alloc(0x500)
    record = PLAYER
    emu.mem.w32(obj + 0x3C8, 0)
    checked = 0

    def run_health(spec):
        mods = blank_modifiers()
        for index, value in spec['items']:
            mods[index] = value
        emu.mem.w32(obj + 0xC, 0x20000 if spec['copy'] else 0)
        emu.mem.w8(obj + 0x477, spec['bonus'] & 0xFF)
        plant_floats(emu.mem, record, (
            (0xAC, spec['hp']), (0xB0, spec['max_hp']),
            (0xB4, spec['pending']), (0xB8, spec['rate'])))
        for index in range(17):
            pointer = 0 if mods[index] is None else item(emu, 0xB, mods[index])
            emu.mem.w32(record + 0x43F0 + 4 * index, pointer)
        box['passive'] = spec['passive']
        emu.writes = []
        emu.call(0x1B3B90, obj)
        want_hp, want_pending = L.regen_health(
            spec['hp'], spec['max_hp'], spec['pending'], spec['rate'], spec['copy'],
            spec['passive'], spec['bonus'], mods)
        got = (emu.mem.u32(record + 0xAC), emu.mem.u32(record + 0xB4))
        if got != (want_hp & 0xFFFFFFFF, want_pending & 0xFFFFFFFF) or draws(emu):
            raise AssertionError('regen health case %d' % spec['n'])

    def run_mana(spec):
        mods = blank_modifiers()
        for index, value in spec['items']:
            mods[index] = value
        emu.mem.w32(obj + 0xC, 0x20000 if spec['copy'] else 0)
        emu.mem.w8(obj + 0x475, spec['bonus'] & 0xFF)
        emu.mem.w32(record + 0x50, spec['class_id'] & 0xFFFFFFFF)
        plant_floats(emu.mem, record, (
            (0xAC, spec['hp']), (0xC0, spec['mana']), (0xC4, spec['max_mana']),
            (0xC8, spec['pending']), (0xBC, spec['rate'])))
        for index in range(17):
            pointer = 0 if mods[index] is None else item(emu, 0xC, mods[index])
            emu.mem.w32(record + 0x43F0 + 4 * index, pointer)
        box.update(passive=spec['passive'], spell=0 if spec['blessed'] is None else 1,
                   blessed=0 if spec['blessed'] is None else spec['blessed'],
                   rank=spec['rank'], rank_value=spec['rank_value'])
        emu.writes = []
        emu.call(0x1B3900, obj)
        want_mana, want_pending = L.regen_mana(
            spec['hp'], spec['mana'], spec['max_mana'], spec['pending'], spec['rate'],
            spec['copy'], spec['class_id'], spec['passive'], spec['bonus'], mods,
            spec['blessed'], spec['rank'], spec['rank_value'])
        got = (emu.mem.u32(record + 0xC0), emu.mem.u32(record + 0xC8))
        if got != (want_mana & 0xFFFFFFFF, want_pending & 0xFFFFFFFF) or draws(emu):
            raise AssertionError('regen mana case %d' % spec['n'])

    hundred = F.from_int(100)
    ten = F.from_int(10)
    one = F.from_int(1)
    fixed = [
        dict(hp=hundred, max_hp=hundred, pending=ten, rate=one, copy=False,
             passive=0, bonus=0, items=[], n=0),
        dict(hp=0, max_hp=hundred, pending=ten, rate=one, copy=False,
             passive=2, bonus=4, items=[(0, 3)], n=1),
        dict(hp=F.from_int(40), max_hp=hundred, pending=0, rate=one, copy=True,
             passive=3, bonus=1, items=[(1, 2)], n=2),
        dict(hp=F.from_int(40), max_hp=hundred, pending=F.from_int(5), rate=F.from_int(2),
             copy=False, passive=2, bonus=-2, items=[(0, 4), (3, -1)], n=3),
        dict(hp=F.from_int(90), max_hp=hundred, pending=F.from_int(30), rate=F.from_int(20),
             copy=False, passive=0, bonus=0, items=[], n=4),
        dict(hp=F.from_int(50), max_hp=hundred, pending=F.from_int(3), rate=F.from_int(8),
             copy=False, passive=1, bonus=0, items=[(2, 0)], n=5),
    ]
    for spec in fixed:
        run_health(spec)
        checked += 1
    mana_fixed = [
        dict(hp=hundred, mana=F.from_int(20), max_mana=hundred, pending=0, rate=one,
             copy=False, class_id=1, passive=2, bonus=1, items=[(0, 2)],
             blessed=3, rank=2, rank_value=4, n=0),
        dict(hp=hundred, mana=F.from_int(20), max_mana=hundred, pending=F.from_int(6),
             rate=F.from_int(4), copy=False, class_id=0, passive=4, bonus=5,
             items=[(1, 9)], blessed=8, rank=3, rank_value=7, n=1),
        dict(hp=0, mana=F.from_int(20), max_mana=hundred, pending=ten, rate=one,
             copy=False, class_id=1, passive=1, bonus=0, items=[],
             blessed=None, rank=0, rank_value=0, n=2),
        dict(hp=hundred, mana=hundred, max_mana=hundred, pending=F.from_int(12),
             rate=F.from_int(5), copy=False, class_id=2, passive=0, bonus=0, items=[],
             blessed=None, rank=0, rank_value=0, n=3),
    ]
    for spec in mana_fixed:
        run_mana(spec)
        checked += 1
    for n in range(30):
        spec = dict(
            hp=rng.getrandbits(32), max_hp=rng.choice((hundred, F.from_int(rng.randrange(1, 80)))),
             pending=rng.choice((0, F.from_int(rng.randrange(0, 40)))),
            rate=F.from_int(rng.randrange(0, 15)), copy=rng.randrange(5) == 0,
            passive=rng.choice((0, 0, 1, 2, -1)), bonus=rng.randrange(-4, 5),
            items=[(rng.randrange(17), rng.randrange(-3, 6))] if rng.randrange(2) else [],
            n=100 + n)
        # A zero or unordered maximum is still original behaviour; keep health below a
        # positive maximum often enough that the natural term is not a dead branch.
        if rng.randrange(3):
            spec['hp'] = F.from_int(rng.randrange(0, 40))
            spec['max_hp'] = F.from_int(rng.randrange(40, 90))
        run_health(spec)
        spec.update(mana=F.from_int(rng.randrange(0, 40)), max_mana=F.from_int(rng.randrange(40, 90)),
                    class_id=rng.choice((0, 1, 2)), blessed=None if rng.randrange(2) else rng.randrange(-2, 5),
                    rank=rng.choice((0, 0, 1, 2)), rank_value=rng.randrange(-2, 5), n=200 + n)
        run_mana(spec)
        checked += 2
    return checked


def bar_cases(elf, rng):
    emu = EE(elf)
    emu.follow = set()
    sprites = []
    names = {}

    def tex(name):
        if name not in names:
            address = emu.alloc(16)
            names[name] = address
            names[address] = name
        return names[name]

    def lookup(e):
        name = e.mem.cstr(e.r[5] & 0xFFFFFFFF)
        if isinstance(name, bytes):
            name = name.decode('latin1')
        record = emu.alloc(16)
        emu.mem.w32(record + 4, tex(name))
        names[record] = name
        return record

    def sprite(e):
        sp = e.r[29] & 0xFFFFFFFF
        name = names.get(e.r[4] & 0xFFFFFFFF, '')
        sprites.append((name, L.s32(e.r[5]), L.s32(e.r[11])))

    def sprintf(e):
        fmt = e.mem.cstr(e.r[5] & 0xFFFFFFFF)
        if isinstance(fmt, bytes):
            fmt = fmt.decode('latin1')
        values, reg = [], 6
        index = 0
        while index < len(fmt):
            if fmt[index] == '%':
                end = index + 1
                while end < len(fmt) and fmt[end] in '-0123456789.':
                    end += 1
                if end < len(fmt) and fmt[end] != '%':
                    values.append(L.s32(e.r[reg]))
                    reg += 1
                index = end
            index += 1
        try:
            out = (fmt % tuple(values)).encode('latin1') + b'\0'
        except (TypeError, ValueError) as exc:
            raise AssertionError('sprintf format %r values %r (%s)' % (fmt, values, exc)) from exc
        e.mem.write(e.r[4] & 0xFFFFFFFF, out)
        return len(out) - 1

    emu.stub(0x173558, ret=emu.alloc(16), name='lump_load')
    emu.stub(0x171DE4, function=lookup, name='lump_findEntry')
    emu.stub(0x17365C, function=lookup, name='res_find')
    emu.stub(0x3B7EF0, function=sprintf, name='sprintf')
    emu.stub(0x17FB88, function=sprite, name='ui_drawSpriteClipped')
    emu.stub(0x13DD40, ret=1, name='net_isSlotActive')
    local_slots = {0}
    emu.stub(0x13E150, function=lambda e: int(L.s32(e.r[4]) in local_slots),
             name='net_isLocalSlot')
    emu.stub(0x1DD270, ret=0, name='hud_spellSelect')
    camera = emu.alloc(0x80)
    obj = emu.alloc(0x600)
    display = emu.alloc(0x4000)
    emu.mem.w32(0x4F8450, camera)
    emu.mem.w32(camera + 0x34, 1)
    emu.mem.w32(0x44FE0C, display)
    emu.mem.w32(0x44FE10, display)
    emu.mem.w32(0x44FDA4, 8000)
    emu.mem.w32(0x4D8AE0, 1)
    record = PLAYER
    emu.mem.w32(record + 0x43D8, obj)
    emu.mem.write(record, b'HUD\0')
    table = [L.s32(emu.mem.u32(XP_TABLE + 4 * i)) for i in range(81)]
    origin = L.s32(emu.mem.u32(ORIGIN))
    checked = 0

    def run(spec):
        nonlocal checked
        emu.mem.w32(0x41B4F8, spec.get('menu', 0))
        emu.mem.w8(SUPPRESSED, 0)
        emu.mem.w32(0x41B50C, 0)
        emu.mem.w8(NETWORK, spec.get('network', 0))
        emu.mem.w32(0x4D8AE0, spec.get('players', 1))
        local_slots.clear()
        local_slots.update(spec.get('locals', {0}))
        emu.mem.w32(0x44FDCC, spec.get('tick', 0) & 0xFFFFFFFF)
        plant_floats(emu.mem, record, (
            (0xAC, spec['hp']), (0xB0, spec['max_hp']), (0xB4, 0),
            (0xC0, spec['mana']), (0xC4, spec['max_mana']), (0xC8, 0)))
        emu.mem.w8(record + 0x58, spec['ack'] & 0xFF)
        emu.mem.w32(record + 0x5C, spec['xp'] & 0xFFFFFFFF)
        emu.mem.w32(obj + 0xC, 0)
        emu.mem.w16(obj + 0x4AE, 0)
        emu.mem.w32(obj + 0x540, 0)
        for index in range(8):
            emu.mem.w32(0x41B828 + 4 * index, 0)
        sprites.clear()
        emu.writes = []
        emu.call(0x1D9CD4, 0)
        if draws(emu):
            raise AssertionError('status bar case %d drew a seed' % spec['n'])
        got = {}
        for name, x, right in sprites:
            if name.startswith('bar_red'):
                kind = 'health'
            elif name.startswith('bar_green'):
                kind = 'experience'
            elif name.startswith('bar_blue'):
                kind = 'mana'
            else:
                continue
            got[kind] = (x, right)
        is_local = 0 in local_slots
        used = L.promoted_origins(
            [L.s32(emu.mem.u32(ORIGIN + 4 * i)) for i in range(4)],
            spec.get('players', 1), set(local_slots), spec.get('network', 0))[0]
        want = {} if spec.get('menu') else L.bar_edges(
            used, spec['hp'], spec['max_hp'], spec['mana'], spec['max_mana'],
            spec['xp'], table[spec['ack'] - 1] if spec['ack'] else 0,
            table[spec['ack']] if spec['ack'] else 0, spec['ack'], is_local)
        expect = {kind: (used + 15, right) for kind, right in want.items()}
        if spec.get('zero_max'):
            start = used + 15
            saturated = {'health': (start, 0x7FFFFFFF), 'mana': (start, -0x80000000)}
            if got != saturated or expect != saturated:
                raise AssertionError('zero maximum edges case %d: original %r model %r' %
                                     (spec['n'], got, expect))
        if got != expect:
            raise AssertionError('status bar case %d: %r != %r' % (spec['n'], got, expect))
        checked += 1

    hundred = F.from_int(100)
    base = [
        dict(hp=hundred, max_hp=hundred, mana=F.from_int(25), max_mana=hundred,
             xp=table[1] // 2, ack=1, n=0),
        dict(hp=0, max_hp=hundred, mana=hundred, max_mana=hundred, xp=0, ack=0, n=1),
        dict(hp=F.from_int(150), max_hp=hundred, mana=F.from_int(-5), max_mana=hundred,
             xp=table[2] + 10, ack=2, n=2),
        dict(hp=hundred, max_hp=hundred, mana=hundred, max_mana=hundred,
             xp=0, ack=1, locals=set(), network=1, n=3),
        dict(hp=hundred, max_hp=hundred, mana=hundred, max_mana=hundred,
             xp=0, ack=1, locals={1}, network=1, players=2, n=7),
        dict(hp=hundred, max_hp=hundred, mana=hundred, max_mana=hundred,
             xp=table[1], ack=1, menu=1, n=4),
        dict(hp=F.from_int(1), max_hp=F.from_int(3), mana=F.from_int(2), max_mana=F.from_int(3),
             xp=table[80] - 1, ack=80, n=5),
    ]
    for spec in base:
        run(spec)
    saved = (emu.mem.u32(XP_TABLE + 8), emu.mem.u32(XP_TABLE + 12))
    emu.mem.w32(XP_TABLE + 8, 50)
    emu.mem.w32(XP_TABLE + 12, 50)
    table[2] = table[3] = 50
    run(dict(hp=hundred, max_hp=hundred, mana=hundred, max_mana=hundred,
             xp=50, ack=3, n=6))
    # ack 3 reads lower at 0x41b554+12 = table word 2, upper at 0x41b558+12 = word 3.
    emu.mem.w32(XP_TABLE + 8, saved[0])
    emu.mem.w32(XP_TABLE + 12, saved[1])
    table[2], table[3] = L.s32(saved[0]), L.s32(saved[1])
    # Positive health and negative mana, both over a zero maximum.
    run(dict(hp=F.from_int(40), max_hp=0, mana=F.from_int(-5), max_mana=0,
             xp=0, ack=0, n=8, zero_max=True))
    for n in range(16):
        ack = rng.choice((0, 1, 2, 5, 10))
        run(dict(hp=rng.getrandbits(32) or F.from_int(1),
                 max_hp=rng.getrandbits(32) or F.from_int(1),
                 mana=rng.getrandbits(32) or F.from_int(1),
                 max_mana=rng.getrandbits(32) or F.from_int(1),
                 xp=rng.randrange(0, max(table[ack], 1) + 5) if ack else 0,
                 ack=ack, n=50 + n))
    return checked


def experience_cases(elf, rng):
    emu = EE(elf)
    box = {'local': 1, 'max_hp': F.from_int(33), 'max_mana': F.from_int(16)}
    text = emu.alloc(8)
    emu.mem.w16(text, 0x41)
    emu.mem.w16(text + 2, 0)
    record = PLAYER + STRIDE
    sounds = []
    emu.follow = {0x1D92A0, 0x19E854}
    emu.stub(0x1B6458, function=lambda e: (
        e.mem.w32(record + 0xB0, box['max_hp']),
        e.mem.w32(record + 0xC4, box['max_mana']), 0)[-1], name='player_recalcStats')
    emu.stub(0x13E150, function=lambda _e: box['local'], name='net_isLocalSlot')
    emu.stub(0x17365C, ret=1, name='res_find')
    emu.stub(0x214230, function=lambda _e: sounds.append(1), name='sound_playOnObject')
    emu.stub(0x173C84, ret=text, name='text_lookup')
    table = [L.s32(emu.mem.u32(XP_TABLE + 4 * i)) for i in range(81)]
    checked = 0

    def run(level, xp, amount, health, mana, local, menu, n, skill=0, stat=0):
        nonlocal checked
        box['local'] = int(local)
        emu.mem.w32(record + 0x5C, xp & 0xFFFFFFFF)
        emu.mem.w8(record + 0x59, level & 0xFF)
        emu.mem.w8(record + 0x58, 4)
        emu.mem.w32(record + 0xE8, skill & 0xFFFFFFFF)
        emu.mem.w8(record + 0xEC, stat & 0xFF)
        plant_floats(emu.mem, record, ((0xAC, health), (0xC0, mana), (0xB0, 0), (0xC4, 0)))
        emu.mem.w16(TIMER, 99)
        emu.mem.w8(FORCE, 7)
        emu.mem.w8(MENU, int(menu))
        emu.mem.w16(TEXT, 0)
        sounds.clear()
        emu.calls = []
        emu.writes = []
        emu.call(0x1D3150, 1, amount & 0xFFFFFFFF)
        want = L.gain_experience(xp, amount, level, skill, stat, health, mana,
                                 box['max_hp'], box['max_mana'], table, local, menu)
        got = (emu.mem.u32(record + 0x5C), emu.mem.u8(record + 0x59),
               emu.mem.u32(record + 0xE8), emu.mem.u8(record + 0xEC),
               emu.mem.u32(record + 0xAC), emu.mem.u32(record + 0xC0),
               emu.mem.u8(record + 0x58))
        recalc = sum(1 for call in emu.calls if call.target == 0x1B6458)
        shown = sum(1 for call in emu.calls if call.target == 0x1D92A0)
        if got != (want['experience'], want['level'], want['skill_points'], want['stat_points'],
                   want['health'] & 0xFFFFFFFF, want['mana'] & 0xFFFFFFFF, 4):
            raise AssertionError('experience record case %d' % n)
        if recalc != want['steps'] or shown != want['steps'] or len(sounds) != want['sounds']:
            raise AssertionError('experience calls case %d' % n)
        if want['message'] is None:
            if emu.mem.u16(TIMER) != 99 or emu.mem.u8(FORCE) != 7:
                raise AssertionError('experience message was stored in case %d' % n)
        elif (emu.mem.u16(TIMER) != want['message']['timer'] or emu.mem.u8(FORCE) != 0
              or emu.mem.u16(TEXT) != 0x41):
            raise AssertionError('experience message case %d' % n)
        if draws(emu):
            raise AssertionError('experience case %d drew a seed' % n)
        checked += 1
        return got

    run(1, 0, 10, F.from_int(8), F.from_int(4), True, False, 0)
    run(1, table[1] - 1, 1, F.from_int(8), F.from_int(4), True, False, 1)
    run(1, table[1] - 1, 1, F.from_int(8), F.from_int(4), True, True, 2)
    run(1, table[1] - 1, 1, F.from_int(8), F.from_int(4), False, False, 3)
    run(1, table[1] - 1, 1, 0, F.from_int(4), True, False, 4)
    run(6, table[6] - 1, 1, F.from_int(8), F.from_int(4), True, False, 5)
    run(16, table[16] - 1, 1, F.from_int(8), F.from_int(4), True, False, 6)
    run(26, table[26] - 1, 1, F.from_int(8), F.from_int(4), True, False, 11)
    run(36, table[36] - 1, 1, F.from_int(8), F.from_int(4), True, False, 7)
    run(79, table[79] - 1, 5000000, F.from_int(8), F.from_int(4), True, False, 8)
    run(2, 100, -40, F.from_int(8), F.from_int(4), True, False, 9)
    span = table[3] - (table[1] - 5)
    run(1, table[1] - 5, span, F.from_int(8), F.from_int(4), True, False, 10)
    # Level being left is 5: the skill word gains 1 and the stat byte wraps.
    wrapped = run(5, table[5] - 1, 1, F.from_int(8), F.from_int(4), True, False, 12,
                  0x11111111, 254)
    if wrapped[1] != 6 or wrapped[2] != 0x11111112 or wrapped[3] != 1:
        raise AssertionError('skill word or stat byte case')
    # Destination starts as a sentinel above entry 80 minus 1.
    planted = 0x00A5A5A5
    capped = run(79, planted, 1, F.from_int(8), F.from_int(4), True, False, 13,
                 0x22222222, 254)
    cap = (table[80] - 1) & 0xFFFFFFFF
    if planted == cap or capped[0] != cap or capped[1] != 80:
        raise AssertionError('experience cap store')
    if capped[2] != (0x22222222 + 5) & 0xFFFFFFFF or capped[3] != 1:
        raise AssertionError('skill word or stat byte beside the cap store')
    for n in range(8):
        level = rng.choice((1, 2, 4, 8))
        run(level, rng.randrange(0, table[level]), rng.randrange(0, 4000),
            F.from_int(rng.randrange(1, 20)), F.from_int(rng.randrange(1, 20)),
            True, False, 20 + n)
    return checked


def message_cases(elf, rng):
    emu = EE(elf)
    emu.follow = {0x19E854}
    text = emu.alloc(8)
    emu.mem.w16(text, 0x42)
    emu.mem.w16(text + 2, 0)
    local = {'on': True}
    emu.stub(0x13E150, function=lambda _e: int(local['on']), name='net_isLocalSlot')
    checked = 0

    def show(slot, frames, force, menu, is_local, n):
        nonlocal checked
        local['on'] = is_local
        emu.mem.w8(MENU, int(menu))
        emu.mem.w16(TIMER, 50)
        emu.mem.w8(FORCE, 9)
        emu.mem.w16(TEXT, 0)
        emu.writes = []
        emu.call(0x1D92A0, text, frames & 0xFFFFFFFF, L.s32(slot), L.s32(force))
        want = L.show_message(is_local, menu, L.s32(slot), frames, force)
        if want is None:
            got = (emu.mem.u16(TIMER), emu.mem.u8(FORCE), emu.mem.u16(TEXT))
            if got != (50, 9, 0):
                raise AssertionError('showMessage stored in case %d' % n)
        elif (emu.mem.u16(TIMER) != want['timer'] or emu.mem.u8(FORCE) != want['force']
              or emu.mem.u16(TEXT) != 0x42):
            raise AssertionError('showMessage case %d: timer %04x force %02x text %04x want %r' %
                                 (n, emu.mem.u16(TIMER), emu.mem.u8(FORCE),
                                  emu.mem.u16(TEXT), want))
        if draws(emu):
            raise AssertionError('showMessage case %d drew a seed' % n)
        checked += 1

    show(-1, 180, 0, False, False, 0)
    show(0, 180, 0, False, False, 1)
    show(0, 180, 0, True, True, 2)
    show(0, 180, 1, True, True, 3)
    show(0, 0x10005, 0x100, False, True, 4)
    show(-1, 360, 0, True, True, 5)
    show(1, 90, 0x80, False, True, 6)
    for n in range(10):
        show(rng.choice((-1, 0, 1, 2)), rng.randrange(0, 1000), rng.choice((0, 1, 0x100, 0x80)),
             rng.choice((False, True)), rng.choice((False, True)), 10 + n)

    def tick(timer, suppressed, warmup, players, network, n):
        nonlocal checked
        emu.mem.w16(TIMER, timer & 0xFFFF)
        emu.mem.w8(SUPPRESSED, suppressed)
        emu.mem.w32(WARMUP, warmup)
        emu.mem.w32(PLAYERS, players)
        emu.mem.w8(NETWORK, network)
        emu.mem.w8(LATCH, 0)
        emu.writes = []
        emu.call(0x1D934C)
        want_timer, want_latch = L.tick_message(timer, suppressed, warmup, players, network, 0)
        if emu.mem.u16(TIMER) != want_timer or emu.mem.u8(LATCH) != want_latch or draws(emu):
            raise AssertionError('tickMessage case %d' % n)
        checked += 1

    tick(10, 0, 0, 1, 0, 0)
    tick(10, 1, 0, 1, 0, 1)
    tick(10, 0, 1, 4, 0, 2)
    tick(0, 0, 0, 4, 0, 3)
    tick(0xFFFF, 0, 0, 4, 0, 4)
    tick(4, 0, 0, 4, 0, 5)
    tick(4, 0, 0, 4, 1, 6)
    tick(4, 0, 0, 3, 0, 7)
    for n in range(8):
        tick(rng.randrange(0, 8), rng.choice((0, 1)), rng.choice((0, 0, 2)),
             rng.choice((1, 3, 4)), rng.choice((0, 1)), 10 + n)

    draw = EE(elf)
    draw.follow = set()
    camera = draw.alloc(0x40)
    draw.mem.w32(0x4F8450, camera)
    draw.mem.w32(camera + 0x34, 0)
    draw.mem.w32(0x41B6A0, 0)
    draw.mem.w32(0x41B6A4, 0)
    draw.mem.w32(0x41B6A8, 0)

    def alpha(timer, old, suppressed, force, n):
        nonlocal checked
        draw.mem.w16(TIMER, timer & 0xFFFF)
        draw.mem.w32(ALPHA, old & 0xFFFFFFFF)
        draw.mem.w8(SUPPRESSED, suppressed)
        draw.mem.w8(FORCE, force & 0xFF)
        draw.mem.w8(MENU, 0)
        draw.writes = []
        draw.call(0x1D93B0)
        want = L.message_alpha(timer, old, suppressed, force)
        if draw.mem.u32(ALPHA) != (want & 0xFFFFFFFF) or draws(draw):
            raise AssertionError('message alpha case %d: got %08x want %08x' %
                                 (n, draw.mem.u32(ALPHA), want & 0xFFFFFFFF))
        checked += 1

    alpha(10, 0, 0, 0, 0)
    alpha(31, 7, 0, 0, 1)
    alpha(32, 0, 0, 0, 2)
    alpha(40, 126, 0, 0, 3)
    alpha(0, 15, 0, 0, 4)
    alpha(20, 15, 1, 0, 5)
    alpha(20, 15, 1, 1, 6)
    alpha(0xFFFF, 15, 0, 0, 7)
    for n in range(8):
        alpha(rng.randrange(0, 80), rng.randrange(0, 140), rng.choice((0, 1)),
              rng.choice((0, 1)), 10 + n)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.environ.get('CHAMPIONS_ELF'))
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    if not args.elf or not os.path.isfile(args.elf):
        print('SKIP: SLUS-20973 v2.00 ELF missing')
        return 0
    # Memory.u8/u16 are used above; fail clearly if this interpreter build lacks them.
    regen = regen_cases(args.elf, random.Random('%d/regen' % args.seed))
    print('PASS regen %d cases; seed draws 0' % regen)
    bars = bar_cases(args.elf, random.Random('%d/bars' % args.seed))
    print('PASS status bars %d cases; seed draws 0' % bars)
    gained = experience_cases(args.elf, random.Random('%d/xp' % args.seed))
    print('PASS experience %d cases; seed draws 0' % gained)
    messages = message_cases(args.elf, random.Random('%d/message' % args.seed))
    print('PASS messages %d cases; seed draws 0' % messages)
    print('PASS 4 properties, %d cases, seed %d' % (regen + bars + gained + messages, args.seed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
