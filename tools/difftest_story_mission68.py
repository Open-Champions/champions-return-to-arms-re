#!/usr/bin/env python3
"""Mission 6, 7 and 8 story beats against the original script machine.

The menu requests that write swamp1, swamp2, valor and fire1 stay in
difftest_story_beats.py. The hub entries that make mission 6 available stay in
difftest_story_mission45.py. This file runs the swamp, dis2, valor, valor2,
honor, fire and obsfor1 entries, and the hub entries that make mission 7
available.

Disc text keys (quest titles and bodies, help and info ids) are not written
here. Each is read from its script call site and pinned by the first ten hex
digits of its SHA-256 (TEXT below). The keys themselves stay in ignored local/.

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; \
  sys.path.insert(0,"tools"); \
  sys.argv=["difftest_story_mission68.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA"]; \
  runpy.run_path("tools/difftest_story_mission68.py", run_name="__main__")'
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_natives as N  # noqa: E402
import difftest_story_mission45 as M  # noqa: E402
import ref_story_route as R  # noqa: E402
import scr  # noqa: E402

ELF_SHA256 = M.ELF_SHA256
PLAYERS, MISSION, QUEST, QUEST_COUNT, REC = M.PLAYERS, M.MISSION, M.QUEST, M.QUEST_COUNT, M.REC
SENTINEL, FILL = M.SENTINEL, M.FILL
G_PAUSED = M.G_PAUSED
G_POST_LEVEL = 0x4FDCF0          # newWorldPost copies its name here (script-builtins.md line 499)
POST_SENTINEL = 'POSTLEVEL-SENTINEL'
WATCHED = (5, 6, 7, 8, 9)
AVAIL = R.available_byte(SENTINEL, 1)
DONE = R.complete_byte(SENTINEL, -1)
BOTH = R.complete_byte(AVAIL, -1)
LEVELS = (
    'swamp1', 'swamp2', 'dis2', 'valor', 'valor2', 'honor', 'fire1', 'fire2', 'fire3',
    'fire4', 'fire5', 'obsfor1', 'hub', 'hub2', 'storm1',
)

# (level, script call site, argument index) -> sha256(key)[:10]
TEXT = {
    ('swamp1', 0x0E0, 0): 'd19c4065ff',
    ('swamp1', 0x0E0, 1): 'ad638205f7',
    ('swamp2', 0x0E0, 0): 'd19c4065ff',
    ('swamp2', 0x0E0, 1): 'ad638205f7',
    ('swamp1', 0x1F4, 0): '0125fd7019',
    ('swamp1', 0x1F4, 1): 'afcd253e53',
    ('dis2', 0x18C, 0): 'd0882500e8',
    ('dis2', 0x18C, 1): '8e248adef8',
    ('dis2', 0xE54, 0): 'd19c4065ff',
    ('dis2', 0xF58, 0): 'a0df82f764',
    ('dis2', 0xF58, 1): '0efe320d7b',
    ('dis2', 0x1004, 0): 'd0882500e8',
    ('dis2', 0x1144, 0): '65a1721c33',
    ('dis2', 0x1144, 1): 'de988ded64',
    ('dis2', 0x1280, 0): 'a0df82f764',
    ('dis2', 0x1280, 1): '5d38865288',
    ('dis2', 0xC90, 1): '9f656ce178',
    ('valor', 0xE7C, 0): 'b2b7b8b5f1',
    ('valor', 0xE7C, 1): 'a09d8f2789',
    ('valor', 0xF3C, 0): 'd124df7d2f',
    ('valor', 0xF3C, 1): '4167398c60',
    ('valor', 0x668, 0): 'b2b7b8b5f1',
    ('valor', 0x668, 1): '1f0eb138af',
    ('valor', 0x75C, 0): 'b2b7b8b5f1',
    ('valor', 0x89C, 0): 'd124df7d2f',
    ('valor', 0x89C, 1): 'd34aa9dad6',
    ('valor', 0xBDC, 0): 'd124df7d2f',
    ('valor', 0xC10, 0): '4ff8a3b5ae',
    ('valor', 0xC10, 1): '1030edc5cb',
    ('valor', 0xD78, 0): 'd124df7d2f',
    ('valor', 0xDAC, 0): '4ff8a3b5ae',
    ('valor', 0xDAC, 1): '537f710378',
    ('valor', 0x1880, 0): '0125fd7019',
    ('valor', 0x1880, 1): 'afcd253e53',
    ('honor', 0x1200, 0): '0d52ad7552',
    ('honor', 0x1200, 1): '4169aeb71b',
    ('honor', 0x1258, 0): '4ff8a3b5ae',
    ('fire1', 0x0B0, 0): 'b2b7b8b5f1',
    ('fire1', 0x0B0, 1): 'a09d8f2789',
    ('fire3', 0x08C, 0): 'e997dd831a',
    ('fire3', 0x130, 0): 'e997dd831a',
    ('fire5', 0x52C, 0): '6d5f292589',
    ('fire5', 0x52C, 1): 'ec992006f4',
    ('fire5', 0x76C, 0): 'b60324e54d',
    ('obsfor1', 0x158, 0): '0125fd7019',
    ('obsfor1', 0x158, 1): 'f401646fec',
}


def nid(text):
    return hashlib.sha256(text.encode('latin1')).hexdigest()[:10]


def require(cond, detail):
    if not cond:
        raise AssertionError(detail)


# ---- static script and archive reads ---------------------------------------------------

def site_rows(image):
    """(offset, native, args) per call. An immediate is (raw, pool string or None)."""
    parsed = scr.parse(image)
    pool = dict(scr.strings(image, *parsed['strings']))
    natives = [name for _, name in parsed['externals']]
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    rows, pending, i = [], [], 0
    while i < len(words):
        op = words[i]
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            raw = pending[:-1][::-1] if pending else []
            args = tuple((value, pool.get(value)) if kind == 'imm' else None for kind, value in raw)
            rows.append((i * 4, natives[words[i + 1]], args))
            pending = []
            i += 2
            continue
        if op == 0x27:
            pending.append(('imm', words[i + 1]))
            i += 2
            continue
        if op == 0x28:
            pending.append(('var', words[i + 1]))
            i += 2
            continue
        if op in (0x24, 0x25):
            pending.append(('reg', 0))
            i += 1
            continue
        if op == 0x2C:
            pending = []
            i += 2
            continue
        if pending:
            pending = []
        if op in scr.OPS:
            i += 1 + scr.OPS[op][1]
        else:
            i += 1 if op in scr.NO_OPERAND else 2
    return rows


class Disc:
    def __init__(self, data):
        self.levels = {name: M.lump_map(os.path.join(data, name.upper() + '.GOB')) for name in LEVELS}
        self.rows = {name: site_rows(parts['script.scr']) for name, parts in self.levels.items()}

    def image(self, level):
        return self.levels[level]['script.scr']

    def call(self, level, site):
        got = [row for row in self.rows[level] if row[0] == site]
        require(len(got) == 1, (level, hex(site)))
        return got[0]

    def text(self, level, site, index):
        args = self.call(level, site)[2]
        require(args[index] is not None and args[index][1] is not None, (level, hex(site), index))
        value = args[index][1]
        want = TEXT[(level, site, index)]
        require(nid(value) == want, (level, hex(site), index, nid(value)))
        return value

    def pool0(self, level):
        image = self.image(level)
        parsed = scr.parse(image)
        return dict(scr.strings(image, *parsed['strings'])).get(0)


# Script call sites. An int is the raw immediate; a str is the pool string at that
# immediate; '#' is a text key pinned in TEXT.
SITES = (
    ('swamp1', 0x070, 'getMissionComplete', (6,)),
    ('swamp1', 0x0E0, 'addQuest', ('#', '#')),
    ('swamp1', 0x114, 'setMissionAvailable', (6, 1)),
    ('swamp1', 0x148, 'setv', ('startedMission6', 1)),
    ('swamp1', 0x17C, 'setv', ('currentMission', 6)),
    ('swamp1', 0x1C0, 'grantMission', (6,)),
    ('swamp1', 0x1F4, 'addHelpMessage', ('#', '#')),
    ('swamp2', 0x0E0, 'addQuest', ('#', '#')),
    ('swamp2', 0x114, 'setMissionAvailable', (6, 1)),
    ('dis2', 0x18C, 'addQuest', ('#', '#')),
    ('dis2', 0x960, 'cutScene', ('dis',)),
    ('dis2', 0xDFC, 'givePlayerItem', ('shardofdisease', 0, 0)),
    ('dis2', 0xE28, 'grantMission', (6,)),
    ('dis2', 0xE54, 'removeQuest', ('#',)),
    ('dis2', 0xF58, 'addHelpMessage', ('#', '#')),
    ('dis2', 0xFAC, 'givePlayerItem', ('shardofdisease', 0, 0)),
    ('dis2', 0xFD8, 'grantMission', (6,)),
    ('dis2', 0x1004, 'removeQuest', ('#',)),
    ('dis2', 0x1144, 'addHelpMessage', ('#', '#')),
    ('dis2', 0x1280, 'addHelpMessage', ('#', '#')),
    ('dis2', 0x1B3C, 'startDialog', ('bertoxx', 1, 0)),
    ('dis2', 0x21B4, 'startDialog', ('bertoxx', 1, 0)),
    ('hub', 0x1400, 'setMissionAvailable', (7, 1)),
    ('hub', 0x144C, 'setMissionAvailable', (7, 1)),
    ('hub', 0x2534, 'setMissionAvailable', (7, 1)),
    ('hub2', 0x37BC, 'setMissionAvailable', (7, 1)),
    ('hub2', 0x3808, 'setMissionAvailable', (7, 1)),
    ('hub2', 0x4640, 'setMissionAvailable', (7, 1)),
    ('valor', 0x0E7C, 'addQuest', ('#', '#')),
    ('valor', 0x0F3C, 'addQuest', ('#', '#')),
    ('valor', 0x0F70, 'setMissionAvailable', (7, 1)),
    ('valor', 0x17D4, 'cutScene', ('valor',)),
    ('valor', 0x184C, 'grantMission', (7,)),
    ('valor', 0x1880, 'addHelpMessage', ('#', '#')),
    ('valor', 0x0528, 'setMissionAvailable', (8, 1)),
    ('valor', 0x0668, 'addQuest', ('#', '#')),
    ('valor', 0x0730, 'setMissionAvailable', (9, 1)),
    ('valor', 0x075C, 'removeQuest', ('#',)),
    ('valor', 0x089C, 'addQuest', ('#', '#')),
    ('valor', 0x0BB0, 'newWorldPost', ('valor2',)),
    ('valor', 0x0BDC, 'removeQuest', ('#',)),
    ('valor', 0x0C10, 'addQuest', ('#', '#')),
    ('valor', 0x0D4C, 'newWorldPost', ('valor2',)),
    ('valor', 0x0D78, 'removeQuest', ('#',)),
    ('valor', 0x0DAC, 'addQuest', ('#', '#')),
    ('valor', 0x025C, 'startDialog', ('mattmar', 1, 0)),
    ('valor', 0x21AC, 'trigger', ('portal', 0)),
    ('valor', 0x22A4, 'newWorld', ('fire1',)),
    ('valor', 0x2304, 'newWorld', ('storm1',)),
    ('honor', 0x1184, 'playerHasItem', ('shardofvalor',)),
    ('honor', 0x1200, 'addHelpMessage', ('#', '#')),
    ('honor', 0x122C, 'grantMission', (7,)),
    ('honor', 0x1258, 'removeQuest', ('#',)),
    ('fire1', 0x070, 'getMissionComplete', (8,)),
    ('fire1', 0x0B0, 'addQuest', ('#', '#')),
    ('fire1', 0x0E4, 'setMissionAvailable', (8, 1)),
    ('fire1', 0x118, 'setv', ('startedMission8', 1)),
    ('fire1', 0x14C, 'setv', ('currentMission', 8)),
    ('fire3', 0x08C, 'setInfo', ('#',)),
    ('fire3', 0x130, 'setInfo', ('#',)),
    ('fire5', 0x110, 'playerHasItem', ('shardoffire',)),
    ('fire5', 0x250, 'cutScene', ('dragon',)),
    ('fire5', 0x4E4, 'playerHasItem', ('shardoffire',)),
    ('fire5', 0x52C, 'addHelpMessage', ('#', '#')),
    ('fire5', 0x560, 'setv', ('fire_gotShard', 1)),
    ('fire5', 0x58C, 'grantMission', (8,)),
    ('fire5', 0x76C, 'setInfo', ('#',)),
    ('obsfor1', 0x078, 'setMissionAvailable', (8, 1)),
    ('obsfor1', 0x124, 'grantMission', (8,)),
    ('obsfor1', 0x158, 'addHelpMessage', ('#', '#')),
    ('storm1', 0x24C, 'setMissionAvailable', (9, 1)),
)


def check_sites(disc):
    checks = 0
    for level, site, native, want in SITES:
        _off, got_native, args = disc.call(level, site)
        require(got_native == native, (level, hex(site), got_native))
        require(len(args) >= len(want), (level, hex(site), args))
        for index, expect in enumerate(want):
            arg = args[index]
            require(arg is not None, (level, hex(site), index))
            if expect == '#':
                disc.text(level, site, index)
            elif isinstance(expect, int):
                require(arg[0] == expect, (level, hex(site), index, arg[0]))
            else:
                require(arg[1] == expect, (level, hex(site), index, arg[1]))
        checks += 1
    # Shared keys: the same title is written at one site and removed at another.
    same = (
        (('swamp1', 0x0E0, 0), ('swamp2', 0x0E0, 0), ('dis2', 0xE54, 0)),
        (('swamp1', 0x0E0, 1), ('swamp2', 0x0E0, 1)),
        (('dis2', 0x18C, 0), ('dis2', 0x1004, 0)),
        (('valor', 0xE7C, 0), ('valor', 0x668, 0), ('valor', 0x75C, 0), ('fire1', 0x0B0, 0)),
        (('valor', 0xE7C, 1), ('fire1', 0x0B0, 1)),
        (('valor', 0xF3C, 0), ('valor', 0x89C, 0), ('valor', 0xBDC, 0), ('valor', 0xD78, 0)),
        (('valor', 0xC10, 0), ('valor', 0xDAC, 0), ('honor', 0x1258, 0)),
        (('swamp1', 0x1F4, 0), ('valor', 0x1880, 0), ('obsfor1', 0x158, 0)),
        (('swamp1', 0x1F4, 1), ('valor', 0x1880, 1)),
        (('dis2', 0xF58, 0), ('dis2', 0x1280, 0)),
        (('fire3', 0x08C, 0), ('fire3', 0x130, 0)),
    )
    for group in same:
        values = {disc.text(*key) for key in group}
        require(len(values) == 1, group)
        checks += 1
    differ = (
        (('valor', 0x668, 1), ('valor', 0xE7C, 1)),
        (('valor', 0x89C, 1), ('valor', 0xF3C, 1)),
        (('valor', 0xC10, 1), ('valor', 0xDAC, 1)),
        (('obsfor1', 0x158, 1), ('swamp1', 0x1F4, 1)),
    )
    for first, second in differ:
        require(disc.text(*first) != disc.text(*second), (first, second))
        checks += 1
    for level, name in (('swamp1', 'dis2'), ('swamp2', 'dis2'), ('valor2', 'honor'),
                        ('honor', 'valor2'), ('fire1', 'fire2'), ('fire2', 'fire3'),
                        ('fire4', 'southladder'), ('obsfor1', 'steppedOnTrigger'),
                        ('fire5', 'deadDragon'), ('valor', 'swordKeyCheck')):
        require(disc.pool0(level) == name, (level, disc.pool0(level)))
        checks += 1
    return checks


def objects(blob):
    count, _, strtab = struct.unpack_from('<hHi', blob, 0)

    def text(off):
        o = strtab + off
        return blob[o:blob.index(b'\0', o)].decode('latin1')

    rows, p = [], 8
    for _ in range(count):
        cls, size, _pad = struct.unpack_from('<ihH', blob, p)
        props, q = [], p + 20
        while q < p + size:
            po, = struct.unpack_from('<i', blob, q)
            if po == 0:
                break
            props.append(text(po))
            q += 4
        rows.append((text(cls), props))
        p += size
    return rows


def linked_values(rows):
    found = set()
    for _cls, props in rows:
        for prop in props:
            if '=' in prop:
                found.add(prop.split('=', 1)[1])
    return found


def check_links(disc):
    lv = disc.levels
    checks = 0
    for level in ('swamp1', 'swamp2'):
        rows = objects(lv[level]['objects.ob'])
        pushes = [props for cls, props in rows if cls == 'PushTrigger' and 'action=newWorldda5d' in props]
        triggers = [props for cls, props in rows if cls == 'Trigger' and 't=newWorldda5d' in props]
        require(len(pushes) == 5 and len(triggers) == 1, (level, len(pushes), len(triggers)))
        values = linked_values(rows)
        require('steppedOnTrigger' not in values, level)
        checks += 1
    publics = {name for _off, name in scr.parse(disc.image('swamp2'))['internals']}
    require('steppedOnTrigger' not in publics, 'swamp2 trigger entry')
    rows = objects(lv['dis2']['objects.ob'])
    bert = [props for cls, props in rows if cls == 'NPC' and 'name=bertoxx' in props]
    require(len(bert) == 1 and 'dialogscript=startDiaae3c' in bert[0]
            and 'exclamation=returnaf44' in bert[0], bert)
    good = [props for cls, props in rows if cls == 'disportGOOD']
    evil = [props for cls, props in rows if cls == 'disportEVIL']
    require(len(good) == 8 and all('action1=callScrief4c' in props for props in good), len(good))
    evil_init = sorted(prop.split('=', 1)[1] for props in evil for prop in props
                       if prop.startswith('action1='))
    require(evil_init == sorted(DIS_EVIL_INIT), evil_init)
    require(len(evil) == 8, len(evil))
    exits = {}
    for cls, props in rows:
        if cls != 'PushTrigger':
            continue
        action = [p.split('=', 1)[1] for p in props if p.startswith('action=')]
        name = [p.split('=', 1)[1] for p in props if p.startswith('name=')]
        exits.setdefault(action[0], set()).update(name)
    require(exits == {'setEntra9e0f': set(), 'setEntrae2b1': set(), 'newWorld3914': {'goodexit'},
                      'newWorld5a4f': {'evilexit'}}, exits)
    trig = sorted(p for cls, props in rows if cls == 'Trigger' for p in props if p.startswith('t='))
    require(trig == ['t=if18fc', 't=if69ee'], trig)
    checks += 3
    bertoxx = M.dbin_rows(lv['dis2']['bertoxx.dbin'])
    require(bertoxx == [
        ('ifd05', [('', '', 1)]),
        ('ifd05', [('', '', 2)]),
        ('ifcb59', [('', 'setv7c05', -1)]),
        ('if2de9', [('', 'setv7df7', -1)]),
        ('if41a3', [('', '', -1)]),
    ], bertoxx)
    checks += 1
    rows = objects(lv['valor']['objects.ob'])
    marr = [props for cls, props in rows if cls == 'MattMarr']
    require(len(marr) == 1 and 'dialogscript=startDiaff8' in marr[0] and 'name=mattmar' in marr[0], marr)
    doors = sorted((sorted(p for p in props if p.startswith(('key=', 'action=', 'name=t'))))
                   for cls, props in rows if cls == 'PushTrigger')
    require(doors == [
        ['action=callScrib1e7', 'key=return4520', 'name=tofire'],
        ['action=callScrib1e7', 'key=return4520', 'name=tostorm'],
        ['key=return25eb', 'name=tovalor'],
    ], doors)
    require('steppedOnTrigger' not in linked_values(rows), 'valor trigger link')
    require(any(cls == 'Trigger' and 't=callScri1ef1' in props for cls, props in rows), 'gate trigger')
    checks += 3
    mattmar = M.dbin_rows(lv['valor']['mattmar.dbin'])
    require(mattmar == [
        ('if2a2e', [('', 'setMissi1bb4', 1)]),
        ('if84f0', [('', 'setv6151', -1)]),
        ('ifa054', [('', 'setMissie47a', 3)]),
        ('if7275', [('', 'setv3d8c', -1)]),
        ('ife995', [('', 'setv7ac2', 5)]),
        ('if4ffe', [('', 'newWorldf844', -1), ('', '', -1)]),
        ('if550a', [('', 'newWorld511b', -1)]),
    ], mattmar)
    checks += 1
    rows = objects(lv['valor2']['objects.ob'])
    require([p for cls, props in rows if cls == 'PushTrigger' for p in props if p.startswith('action=')]
            == ['action=newWorld6440'], 'valor2 door')
    rows = objects(lv['honor']['objects.ob'])
    require(sum(1 for cls, props in rows if cls == 'PushTrigger' and 'action=newWorlda6a0' in props) == 1,
            'honor door')
    rows = objects(lv['fire5']['objects.ob'])
    dragon = [props for cls, props in rows if cls == 'reddragon']
    require(len(dragon) == 1 and 'dropitem=shardoffire' in dragon[0]
            and 'deathscript=callScri3971' in dragon[0], dragon)
    portal = [props for cls, props in rows if cls == 'Portal']
    require(portal == [['lump=jumpgate', 'script=return2c8d']], portal)
    rows = objects(lv['obsfor1']['objects.ob'])
    require([p for cls, props in rows for p in props if p.startswith('t=')] == ['t=callScri7351'], 'obsfor1')
    rows = objects(lv['fire3']['objects.ob'])
    keyed = [props for cls, props in rows if cls == 'PushTrigger' and 'key=return7da1' in props]
    require(len(keyed) == 1 and 'action=setEntrabca8' in keyed[0], keyed)
    valves = sorted(p for cls, props in rows if cls == 'pipevalveswitch' for p in props if p.startswith('action1='))
    require(valves == ['action1=hideMons7bb4', 'action1=hideMonsc5f1'], valves)
    checks += 6
    firiona = M.dbin_rows(lv['hub']['firiona.dbin'])
    bak = M.dbin_rows(lv['hub']['firiona_bak.dbin'])
    natasla = M.dbin_rows(lv['hub2']['natasla.dbin'])
    natasla_bak = M.dbin_rows(lv['hub2']['natasla_bak.dbin'])
    require(firiona[19] == ('ifcceb', [('', 'setMissi26bc', -1), ('', 'setMissib9fb', -1)]), firiona[19])
    require(bak[18] == ('ifcceb', [('', 'setMissi26bc', -1), ('', 'setMissi167', -1)]), bak[18])
    require(natasla[14] == ('ifcceb', [('', 'setMissi26bc', -1), ('', 'setMissib9fb', -1)]), natasla[14])
    require(natasla_bak[15] == ('ifcceb', [('', 'setMissi26bc', -1), ('', 'setMissi167', -1)]),
            natasla_bak[15])
    checks += 4
    return checks


DIS_EVIL_INIT = ('callScri7956', 'callScri5b57', 'callScria6fd', 'callScri3067',
                 'callScri1fe8', 'callScri92ad', 'callScri8b5b', 'callScri489d')


# ---- running entries -------------------------------------------------------------------

class Run:
    """One prepared image. Records the natives the interpreter called, in order."""

    def __init__(self, rig, disc, seed):
        self.rig, self.disc, self.seed = rig, disc, seed
        mem = rig.emu.mem
        self.handlers = {}
        for index in range(191):
            pointer = mem.u32(N.N.NATIVE_TABLE + 8 * index)
            if pointer == 0:
                break
            self.handlers.setdefault(mem.u32(N.N.NATIVE_TABLE + 8 * index + 4), mem.cstr(pointer, 40))
        require(len(self.handlers) > 150, len(self.handlers))

    def prepare(self, level, evil=0, shells=0, bytes0=None):
        mem = M.prepare(self.rig, self.disc.image(level), self.seed, shells=shells, evil=evil)
        mem.write(G_POST_LEVEL, POST_SENTINEL.encode('ascii') + b'\0')
        for index, value in (bytes0 or {}).items():
            mem.w8(PLAYERS + MISSION + index, value)
        self.mem = mem
        self.level = level
        return mem

    def entry(self, name):
        ret, err = M.run_entry(self.rig, name)
        require(err == '', (self.level, name, err))
        return ret

    def post(self):
        rig = self.rig
        rig.calls = []
        rig.emu.calls.clear()
        rig.emu.writes.clear()
        return N.s32(rig.call(N.A['script_runPostAction'], max_steps=4000000))

    def natives(self):
        return [self.handlers[rec.target] for rec in self.rig.emu.calls if rec.target in self.handlers]

    def stubs(self):
        return list(self.rig.calls)

    def var(self, name, value):
        M.plant_var(self.rig, name, value)

    def quest(self, title, body='plant-body'):
        M.plant_quest(self.rig, title, body)

    def stored(self, name, value):
        M.require_stored(self.rig, self.mem, name.lower(), value)

    def vars(self):
        return dict(M.variables(self.mem))

    # state
    def missions(self, index):
        return tuple(M.mission(self.mem, slot, index) for slot in range(4))

    def held(self, changed=None):
        """Watched mission bytes are the sentinel except the named ones."""
        changed = changed or {}
        for index in WATCHED:
            want = changed.get(index, (SENTINEL,) * 4)
            require(self.missions(index) == tuple(want), (self.level, index, [hex(v) for v in self.missions(index)]))

    def quests(self):
        mem = self.mem
        count = mem.u32(PLAYERS + QUEST_COUNT)
        return count, [(mem.cstr(PLAYERS + QUEST + 0x40 * i, 32), mem.cstr(PLAYERS + QUEST + 0x40 * i + 0x20, 32))
                       for i in range(min(count, 8))]

    def no_quest_edit(self):
        mem = self.mem
        require(mem.u32(PLAYERS + QUEST_COUNT) == 0, (self.level, 'count'))
        require(mem.read(PLAYERS + QUEST, 8 * 0x40) == bytes([FILL]) * (8 * 0x40), (self.level, 'slots'))
        require(mem.u32(PLAYERS + REC + QUEST_COUNT) == 0x5A5A5A5A, (self.level, 'other count'))

    def requests(self, level='PENDING-SENTINEL', entrance='ENTRANCE-SENTINEL', orient=0x5A,
                 post_level=POST_SENTINEL):
        mem = self.mem
        got = (mem.cstr(N.N.G_PENDING_LEVEL, 32), mem.cstr(N.N.G_ENTRANCE_NAME, 32),
               mem.u8(N.N.G_PENDING_ORIENT), mem.cstr(G_POST_LEVEL, 32))
        require(got == (level, entrance, orient, post_level), (self.level, got))

    def posted(self):
        return self.mem.cstr(N.N.G_POST_ACTION, 32)

    def deferred(self):
        return M.defer_name(self.mem)

    def seed_kept(self):
        require(self.mem.u32(N.N.G_RAND_SEED) == self.seed, (self.level, 'seed'))


def help_calls(first, second):
    return [
        ('text_lookup', (first.encode('latin1'),)),
        ('text_lookup', (second.encode('latin1'),)),
        ('hud_showHelpMessage', (0xFFFFFFFF, 0, 0)),
    ]


def info_calls(key):
    # text_lookup returns 0, so the message callee receives text 0.
    return [('text_lookup', (key.encode('latin1'),)), ('hud_showMessage', (0, 180, 0xFFFFFFFF, 0))]


SOUND_CALLS = [
    ('res_find', (b'fx.lmp', b'quest_complete.anm')),
    ('sound_playOnObject', (0, 0, 1065353216)),
    ('sound_setPlaysWhileFrozen', (0,)),
]
ONE_PLAYER_LOOP = ['onePlayerHasItem'] * 4
CLOSE_MENUS = [('net_closeLocalMenus', (0,))]


def give_calls(item):
    descriptor = (b'\0' * 16 + b'\xff\xff', 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)
    return [
        ('item_parseDescriptor', (item.encode('ascii'), descriptor, 0xFFFFFFFF, 0)),
        ('player_itemWeight', (0,)),
        ('inventory_giveItem', (0, 1)),
        ('player_recalcLoad', (0,)),
    ]


def travel(run, level, entry, dest, entrance='ENTRANCE-SENTINEL', natives=('newWorld',)):
    run.prepare(level)
    run.held()
    require(run.entry(entry) == 0, (level, entry))
    run.requests(level=dest, entrance=entrance, orient=0xFF)
    require(run.natives() == list(natives), (level, entry, run.natives()))
    # The stub returns 0 for every newWorld in the entry, so no menu is closed.
    require(run.stubs() == CLOSE_MENUS * list(natives).count('newWorld'), (level, entry, run.stubs()))
    run.held()
    run.no_quest_edit()
    run.seed_kept()


# ---- mission 6 -------------------------------------------------------------------------

def check_swamp(run):
    disc = run.disc
    checks = 0
    for level in ('swamp1', 'swamp2'):
        title, body = disc.text(level, 0x0E0, 0), disc.text(level, 0x0E0, 1)
        for evil in (0, 1):
            for before in (SENTINEL, DONE):
                run.prepare(level, evil=evil, bytes0={6: before})
                run.var('startedMission6', 0x5A)
                run.var('currentMission', 0x5A)
                require(run.entry('start') == 0, (level, 'start'))
                adds = before == SENTINEL and not evil
                want = ['getMissionComplete']
                if before == SENTINEL:
                    want.append('getEvil')
                if adds:
                    want.append('addQuest')
                want += ['setMissionAvailable', 'setv', 'setv']
                require(run.natives() == want, (level, evil, hex(before), run.natives()))
                require(run.stubs() == [], run.stubs())
                run.held({6: (R.available_byte(before, 1), SENTINEL, SENTINEL, SENTINEL)})
                run.stored('startedMission6', 1)
                run.stored('currentMission', 6)
                if adds:
                    require(run.quests() == (1, [(title, body)]), (level, run.quests()))
                else:
                    run.no_quest_edit()
                run.requests()
                require(run.posted() == '' and run.deferred() == '', (level, 'post'))
                run.seed_kept()
                checks += 1
        travel(run, level, 'newWorldda5d', 'dis2')
        checks += 1
    first, second = disc.text('swamp1', 0x1F4, 0), disc.text('swamp1', 0x1F4, 1)
    for before, after0 in ((SENTINEL, DONE), (AVAIL, BOTH)):
        run.prepare('swamp1', bytes0={6: before})
        require(run.entry('steppedOnTrigger') == 0, 'swamp1 trigger')
        require(run.natives() == ['grantMission', 'addHelpMessage'], run.natives())
        # text_lookup returns 0, so the help callee receives empty text ids.
        require(run.stubs() == help_calls(first, second), run.stubs())
        run.held({6: (after0, DONE, DONE, DONE)})
        run.no_quest_edit()
        run.requests()
        run.seed_kept()
        checks += 1
    return checks


DIS_START_GOOD_FRESH = (['getv', 'getEvil', 'getv', 'postAction', 'getv', 'getEvil'] + ['hideMonster'] * 9
                        + ['getv', 'getEvil', 'getv'])


def check_dis_start(run):
    checks = 0
    run.prepare('dis2')
    require(run.mem.cstr(N.N.G_LEVEL_NAME, 16) == '', 'level name')
    require(run.entry('start') == 0, 'dis2 start')
    require(run.natives() == DIS_START_GOOD_FRESH, run.natives())
    require(run.stubs() == [], run.stubs())
    require(run.posted() == 'absorb' and run.deferred() == '', (run.posted(), run.deferred()))
    for name in ('dis_portalCount', 'dis_sawScene', 'dis_activatedAllPortals'):
        run.stored(name, 0)
    run.held()
    run.no_quest_edit()
    run.requests()
    require(run.post() == 0, 'absorb')
    require(run.natives() == ['cutScene', 'postAction'], run.natives())
    require(run.stubs() == M.cut_calls('dis'), run.stubs())
    require(run.posted() == 'initLevel', run.posted())
    require(run.post() == 0, 'initLevel')
    require(run.natives() == ['hideMonster', 'hideMonster', 'setv', 'addDeferedCall'], run.natives())
    require(run.stubs() == [], run.stubs())
    run.stored('dis_sawScene', 1)
    require(run.deferred() == 'everyFrame', run.deferred())
    require(run.posted() == '', run.posted())
    run.held()
    run.seed_kept()
    checks += 1
    # evil, sawScene, talked -> posted absorb, deferred everyFrame
    cases = (
        (1, None, None, '', ''),
        (0, 1, None, '', 'everyFrame'),
        (1, 1, None, '', ''),
        (1, 1, 1, '', 'everyFrame'),
    )
    for evil, saw, talked, post, defer in cases:
        run.prepare('dis2', evil=evil)
        if saw is not None:
            run.var('dis_sawScene', saw)
        if talked is not None:
            run.var('dis_talkedToBertoxx', talked)
        require(run.entry('start') == 0, 'dis2 start')
        natives = run.natives()
        require(('postAction' in natives) == bool(post), (evil, saw, talked, natives))
        require(('addDeferedCall' in natives) == bool(defer), (evil, saw, talked, natives))
        require(run.posted() == post and run.deferred() == defer, (evil, saw, talked, run.posted(), run.deferred()))
        require(run.stubs() == [], run.stubs())
        run.held()
        run.no_quest_edit()
        run.requests()
        checks += 1
    run.prepare('dis2')
    run.var('dis_portalCount', 5)
    require(run.entry('prestart') == 0, 'prestart')
    require(run.natives() == ['preloadResource', 'getv'], run.natives())
    require(run.stubs() == [('lump_load', (b'bust.lmp',))], run.stubs())
    run.held()
    checks += 1
    return checks


def portal_hits(run, evil, count):
    entries = ['callScrief4c'] * count if not evil else list(DIS_EVIL_INIT[:count])
    for name in entries:
        require(run.entry(name) == 0, name)
        if evil:
            require(run.natives() == ['callScript', 'autoPropSetState', 'callScript'], (name, run.natives()))
        else:
            require(run.natives() == ['callScript'], (name, run.natives()))
        require(run.stubs() == [], run.stubs())


def check_dis_portals(run):
    disc = run.disc
    checks = 0
    swamp_title, swamp_body = disc.text('swamp1', 0x0E0, 0), disc.text('swamp1', 0x0E0, 1)
    bert_title = disc.text('dis2', 0x18C, 0)
    bust = disc.text('dis2', 0xC90, 1)
    for evil in (0, 1):
        for count in (7, 8):
            run.prepare('dis2', evil=evil)
            run.var('dis_sawScene', 1)
            if evil:
                run.var('dis_talkedToBertoxx', 1)
                run.quest(bert_title)
            else:
                run.quest(swamp_title, swamp_body)
            require(run.entry('prestart') == 0, 'prestart')
            run.stored('dis_portalCount', 0)
            portal_hits(run, evil, count)
            M.clear_defer(run.mem)
            require(run.entry('everyFrame') == 0, 'everyFrame')
            run.stored('dis_portalCount', count)
            natives = run.natives()
            if count == 7:
                require(natives == ['getv', 'setv', 'addDeferedCall', 'getv', 'getEvil', 'getv', 'showBust'],
                        (evil, natives))
                # The bust's count argument is 8 minus the hits. text_lookup returns 0.
                require(run.stubs() == [('text_lookup', (bust.encode('latin1'),)),
                                        ('hud_setBust', (b'bust_portal.tex', 0, 1, 0xFFFFFFFF))], run.stubs())
                require(run.deferred() == 'everyFrame', run.deferred())
                require(run.vars()['dis_activatedallportals'] == 0, run.vars())
                run.held()
                require(run.quests()[0] == 1, run.quests())
            elif not evil:
                require(natives == ['getv', 'setv', 'setv', 'callScript', 'getEvil', 'addDeferedCall',
                                    'givePlayerItem', 'grantMission', 'removeQuest'] + ONE_PLAYER_LOOP
                        + ['getv'], natives)
                # givePlayerItem reaches the stubbed item parser and give; no item is
                # shown in a bag. No player object, so onePlayerHasItem finds none.
                require(run.stubs() == give_calls('shardofdisease'), run.stubs())
                run.stored('dis_activatedAllPortals', 1)
                run.held({6: (DONE,) * 4})
                require(run.quests() == (0, []), run.quests())
                require(run.mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', 'placeholder')
                require(run.deferred() == 'pause', run.deferred())
            else:
                require(natives == ['getv', 'setv', 'setv', 'callScript', 'getEvil', 'addHelpMessage', 'getv'],
                        natives)
                require(run.stubs() == help_calls(disc.text('dis2', 0xF58, 0), disc.text('dis2', 0xF58, 1)),
                        run.stubs())
                run.stored('dis_activatedAllPortals', 1)
                run.held()
                require(run.quests() == (1, [(bert_title, 'plant-body')]), run.quests())
                require(run.deferred() == '', run.deferred())
            run.requests()
            run.seed_kept()
            checks += 1
    return checks


def check_dis_pause(run):
    disc = run.disc
    # After prestart clears the requeue local, a paused first call does not
    # queue pause again.
    run.prepare('dis2')
    require(run.entry('prestart') == 0, 'prestart')
    run.mem.w32(G_PAUSED, 1)
    M.clear_defer(run.mem)
    require(run.entry('pause') == 0, 'paused first')
    require(run.natives() == ['gamePaused'] and run.stubs() == [] and run.deferred() == '', run.natives())
    run.prepare('dis2')
    require(run.entry('prestart') == 0, 'prestart')
    seen = []
    unpaused = 0
    for call in range(1, 98):
        paused = 1 if call in (11, 12, 13) else 0
        run.mem.w32(G_PAUSED, paused)
        M.clear_defer(run.mem)
        require(run.entry('pause') == 0, call)
        if paused:
            # A paused call after an unpaused one queues pause again and counts nothing.
            require(run.natives() == ['gamePaused', 'addDeferedCall'] and run.stubs() == []
                    and run.deferred() == 'pause', (call, run.natives()))
            continue
        unpaused += 1
        if run.stubs():
            seen.append((unpaused, run.natives(), run.stubs(), run.deferred()))
        elif unpaused < 92:
            require(run.natives() == ['gamePaused', 'addDeferedCall'] and run.deferred() == 'pause',
                    (call, run.natives()))
    first = help_calls(disc.text('dis2', 0x1280, 0), disc.text('dis2', 0x1280, 1))
    shard = help_calls(disc.text('dis2', 0x1144, 0), disc.text('dis2', 0x1144, 1)) + SOUND_CALLS
    require(seen[0] == (61, ['gamePaused', 'addHelpMessage', 'addDeferedCall'], first, 'pause'), seen[0])
    require(seen[1] == (92, ['gamePaused', 'callScript', 'addHelpMessage', 'soundSequence'], shard, ''),
            seen[1])
    run.held()
    run.no_quest_edit()
    return 1


def check_dis_bert(run):
    disc = run.disc
    checks = 0
    conditions = (
        ('ifd05', (), 1), ('ifd05', (('dis_talkedToBertoxx', 1),), 0),
        ('ifd05', (('dis_talkedToBertoxx', 0x5A),), 0),
        ('ifcb59', (), 1), ('ifcb59', (('dis_activatedAllPortals', 1),), 0),
        ('if2de9', (('dis_talkedToBertoxx', 1), ('dis_activatedAllPortals', 1)), 1),
        ('if2de9', (('dis_talkedToBertoxx', 1), ('dis_activatedAllPortals', 1), ('dis_finishedQuest', 1)), 0),
        ('if2de9', (('dis_activatedAllPortals', 1),), 0),
        ('if2de9', (('dis_talkedToBertoxx', 1),), 0),
        ('if41a3', (), 0), ('if41a3', (('dis_finishedQuest', 1),), 1),
        ('returnaf44', (), 1), ('returnaf44', (('dis_talkedToBertoxx', 1),), 0),
    )
    for entry, plants, expect in conditions:
        run.prepare('dis2')
        for name, value in plants:
            run.var(name, value)
        require(run.entry(entry) == expect, (entry, plants))
        require(run.stubs() == [], run.stubs())
        run.held()
        checks += 1
    dialog_stubs = [('lump_load', (b'.lmp',)), ('Camera_update', (0,)), ('net_isLocalSlot', (0,))]
    for evil, talked, natives, stubs in (
            (0, None, ['getEvil'], []),
            (1, None, ['getEvil', 'getv', 'startDialog'], dialog_stubs),
            (1, 1, ['getEvil', 'getv'], [])):
        run.prepare('dis2', evil=evil)
        if talked is not None:
            run.var('dis_talkedToBertoxx', talked)
        require(run.entry('if18fc') == 0, 'if18fc')
        require(run.natives() == natives, (evil, talked, run.natives()))
        # lump_load returns 0, so no dialog file is loaded by this harness.
        require(run.stubs() == stubs, run.stubs())
        run.held()
        checks += 1
    title, body = disc.text('dis2', 0x18C, 0), disc.text('dis2', 0x18C, 1)
    run.prepare('dis2', evil=1)
    run.var('dis_talkedToBertoxx', 0x5A)
    require(run.entry('setv7c05') == 0, 'setv7c05')
    require(run.natives() == ['setv', 'addDeferedCall', 'addQuest'], run.natives())
    require(run.stubs() == [], run.stubs())
    run.stored('dis_talkedToBertoxx', 1)
    require(run.deferred() == 'everyFrame', run.deferred())
    require(run.quests() == (1, [(title, body)]), run.quests())
    run.held()
    checks += 1
    for before, after0 in ((SENTINEL, DONE), (AVAIL, BOTH)):
        run.prepare('dis2', evil=1, bytes0={6: before})
        run.quest(title)
        run.var('dis_finishedQuest', 0x5A)
        require(run.entry('setv7df7') == 0, 'setv7df7')
        require(run.natives() == ['setv', 'callScript', 'givePlayerItem', 'grantMission', 'removeQuest']
                + ONE_PLAYER_LOOP + ['callScript', 'addHelpMessage', 'soundSequence'], run.natives())
        require(run.stubs() == give_calls('shardofdisease')
                + help_calls(disc.text('dis2', 0x1144, 0), disc.text('dis2', 0x1144, 1)) + SOUND_CALLS,
                run.stubs())
        run.stored('dis_finishedQuest', 1)
        run.held({6: (after0, DONE, DONE, DONE)})
        require(run.quests() == (0, []) and run.mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', run.quests())
        run.requests()
        run.seed_kept()
        checks += 1
    return checks


def check_dis_travel(run):
    routes = (
        ('setEntra9e0f', 'arachna1', 'left', ('setEntrance', 'newWorld'), 0),
        ('setEntrae2b1', 'arachna1', 'right', ('setEntrance', 'newWorld'), 0),
        ('newWorld3914', 'swamp1', 'ENTRANCE-SENTINEL', ('newWorld',), 0),
        ('newWorld5a4f', 'swamp2', 'ENTRANCE-SENTINEL', ('newWorld',), 0),
    )
    for entry, dest, door, natives, _evil in routes:
        travel(run, 'dis2', entry, dest, door, natives)
    for evil, dest in ((0, 'swamp1'), (1, 'swamp2')):
        run.prepare('dis2', evil=evil)
        require(run.entry('if69ee') == 0, 'if69ee')
        run.requests(level=dest, orient=0xFF)
        require(run.natives() == ['getEvil', 'newWorld'], run.natives())
        require(run.stubs() == CLOSE_MENUS, run.stubs())
        run.held()
    return len(routes) + 2


# ---- mission 7 -------------------------------------------------------------------------

def check_mission7_offer(run):
    checks = 0
    for level in ('hub', 'hub2'):
        for before, expect in ((SENTINEL, 1), (AVAIL, 0)):
            run.prepare(level, bytes0={7: before})
            require(run.entry('ifcceb') == expect, (level, hex(before)))
            require(run.natives() == ['getMissionAvailable'] and run.stubs() == [], run.natives())
            checks += 1
        for entry, natives, stubs in (
                ('setMissi26bc', ['setMissionAvailable'], []),
                ('setMissi167', ['setMissionAvailable', 'changeSwoop', 'activateStore'],
                 ['dialog_isOpen', 'shop_openOrStock']),
                ('setMissib9fb', ['setMissionAvailable', 'changeSwoop', 'activateStore'],
                 ['dialog_isOpen', 'shop_openOrStock'])):
            run.prepare(level)
            require(run.entry(entry) == 0, (level, entry))
            require(run.natives() == natives, (level, entry, run.natives()))
            # dialog_isOpen and shop_openOrStock return 0, so no shop is opened.
            require([name for name, _args in run.stubs()] == stubs, (level, entry, run.stubs()))
            run.held({7: (AVAIL, SENTINEL, SENTINEL, SENTINEL)})
            run.no_quest_edit()
            run.requests()
            checks += 1
    return checks


VALOR_START_FRESH = [
    'getMissionAvailable', 'getMissionAvailable', 'setMissionAvailable', 'setv', 'setv', 'getv', 'setv',
    'getv', 'setv', 'setv', 'hideMonster', 'addDeferedCall', 'getv', 'postAction', 'getMissionComplete',
    'showMonster', 'hideMonster', 'hideMonster', 'hideMonster', 'hideMonster', 'getMissionComplete',
    'getMissionComplete', 'getv', 'autoPropSetState',
]


def check_valor_start(run):
    disc = run.disc
    fire = (disc.text('valor', 0xE7C, 0), disc.text('valor', 0xE7C, 1))
    storm = (disc.text('valor', 0xF3C, 0), disc.text('valor', 0xF3C, 1))
    checks = 0
    run.prepare('valor')
    for name in ('startedMission7', 'currentMission', 'skelPopulation'):
        run.var(name, 0x5A)
    require(run.entry('start') == 0, 'valor start')
    require(run.natives() == VALOR_START_FRESH, run.natives())
    require(run.stubs() == [], run.stubs())
    run.held({7: (AVAIL, SENTINEL, SENTINEL, SENTINEL)})
    run.stored('startedMission7', 1)
    run.stored('currentMission', 7)
    run.stored('numberOfWaves', 1)
    run.stored('skelPopulation', 0)
    run.stored('sawValor', 0)
    run.no_quest_edit()
    require(run.posted() == 'absorb' and run.deferred() == 'checkperiodicSpawn', (run.posted(), run.deferred()))
    run.requests()
    run.seed_kept()
    checks += 1
    # mission 8 byte, mission 9 byte -> quest added by start
    cases = (
        (AVAIL, SENTINEL, fire),
        (BOTH, AVAIL, storm),
        (BOTH, BOTH, None),
        (DONE, SENTINEL, None),
    )
    for m8, m9, quest in cases:
        run.prepare('valor', bytes0={8: m8, 9: m9})
        require(run.entry('start') == 0, 'valor start')
        require(run.natives().count('addQuest') == (1 if quest else 0), run.natives())
        if quest:
            require(run.quests() == (1, [quest]), run.quests())
        else:
            run.no_quest_edit()
        run.held({7: (AVAIL, SENTINEL, SENTINEL, SENTINEL), 8: (m8, SENTINEL, SENTINEL, SENTINEL),
                  9: (m9, SENTINEL, SENTINEL, SENTINEL)})
        checks += 1
    run.prepare('valor')
    run.var('sawValor', 1)
    require(run.entry('start') == 0, 'return visit')
    require(run.posted() == '' and 'postAction' not in run.natives(), run.natives())
    checks += 1
    run.prepare('valor')
    run.entry('start')
    require(run.post() == 0, 'absorb')
    require(run.natives() == ['callScript', 'getMissionComplete', 'cutScene', 'setv'], run.natives())
    require(run.stubs() == M.cut_calls('valor'), run.stubs())
    run.stored('sawValor', 1)
    checks += 1
    run.prepare('valor', bytes0={8: BOTH})
    run.var('sawValor', 0x5A)
    require(run.entry('absorb') == 0, 'absorb after mission 8')
    require(run.natives() == ['callScript', 'getMissionComplete'] and run.stubs() == [], run.natives())
    require(run.vars()['sawvalor'] == 0x5A, run.vars())
    checks += 1
    first, second = disc.text('valor', 0x1880, 0), disc.text('valor', 0x1880, 1)
    run.prepare('valor')
    require(run.entry('steppedOnTrigger') == 0, 'valor trigger')
    require(run.natives() == ['grantMission', 'addHelpMessage'], run.natives())
    require(run.stubs() == help_calls(first, second), run.stubs())
    run.held({7: (DONE,) * 4})
    run.no_quest_edit()
    checks += 1
    return checks


MARR_CONDITIONS = ('if2a2e', 'if84f0', 'ifa054', 'if7275', 'ife995', 'if4ffe', 'if550a')


def check_marr(run):
    disc = run.disc
    checks = 0
    # (mission 8 byte, mission 9 byte, MarrDone, evil) -> the seven node conditions
    states = (
        (SENTINEL, SENTINEL, None, 0, (1, 0, 1, 0, 0, 0, 0)),
        (AVAIL, SENTINEL, None, 0, (0, 1, 1, 0, 0, 0, 0)),
        (BOTH, SENTINEL, None, 0, (0, 0, 1, 0, 0, 0, 0)),
        (BOTH, AVAIL, None, 0, (0, 0, 0, 1, 0, 0, 0)),
        (BOTH, BOTH, None, 0, (0, 0, 0, 0, 1, 0, 0)),
        (BOTH, BOTH, 1, 0, (0, 0, 0, 0, 0, 1, 0)),
        (BOTH, BOTH, None, 1, (0, 0, 0, 0, 0, 0, 1)),
        (BOTH, BOTH, 1, 1, (0, 0, 0, 0, 0, 0, 1)),
    )
    for m8, m9, done, evil, want in states:
        got = []
        for entry in MARR_CONDITIONS:
            run.prepare('valor', evil=evil, bytes0={8: m8, 9: m9})
            if done is not None:
                run.var('MarrDone', done)
            got.append(run.entry(entry))
            require(run.stubs() == [], run.stubs())
        require(tuple(got) == want, (hex(m8), hex(m9), done, evil, got))
        checks += 1
    fire_title, fire_body = disc.text('valor', 0x668, 0), disc.text('valor', 0x668, 1)
    storm_title, storm_body = disc.text('valor', 0x89C, 0), disc.text('valor', 0x89C, 1)
    run.prepare('valor')
    require(run.entry('setMissi1bb4') == 0 and run.natives() == ['setMissionAvailable'], run.natives())
    run.held({8: (AVAIL, SENTINEL, SENTINEL, SENTINEL)})
    run.no_quest_edit()
    checks += 1
    run.prepare('valor')
    run.var('mar_fire', 0x5A)
    require(run.entry('setv6151') == 0 and run.natives() == ['setv', 'addQuest'], run.natives())
    run.stored('mar_fire', 1)
    require(run.quests() == (1, [(fire_title, fire_body)]), run.quests())
    run.held()
    checks += 1
    # A title already in the log is not added again and keeps its body.
    run.prepare('valor')
    run.quest(fire_title)
    require(run.entry('setv6151') == 0, 'repeat title')
    require(run.quests() == (1, [(fire_title, 'plant-body')]), run.quests())
    checks += 1
    run.prepare('valor')
    run.quest(fire_title)
    require(run.entry('setMissie47a') == 0 and run.natives() == ['setMissionAvailable', 'removeQuest'],
            run.natives())
    run.held({9: (AVAIL, SENTINEL, SENTINEL, SENTINEL)})
    require(run.quests() == (0, []) and run.mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', run.quests())
    checks += 1
    run.prepare('valor')
    run.var('mar_storm', 0x5A)
    require(run.entry('setv3d8c') == 0 and run.natives() == ['setv', 'addQuest'], run.natives())
    run.stored('mar_storm', 1)
    require(run.quests() == (1, [(storm_title, storm_body)]), run.quests())
    checks += 1
    run.prepare('valor')
    run.var('MarrDone', 0x5A)
    require(run.entry('setv7ac2') == 0 and run.natives() == ['setv'], run.natives())
    run.stored('MarrDone', 1)
    run.held()
    checks += 1
    for entry, site in (('newWorldf844', 0xC10), ('newWorld511b', 0xDAC)):
        run.prepare('valor')
        run.quest(storm_title)
        require(run.entry(entry) == 0, entry)
        require(run.natives() == ['newWorldPost', 'removeQuest', 'addQuest'], run.natives())
        require(run.stubs() == [], run.stubs())
        run.requests(post_level='valor2')
        require(run.quests() == (1, [(disc.text('valor', site, 0), disc.text('valor', site, 1))]), run.quests())
        run.held()
        checks += 1
    run.prepare('valor')
    require(run.entry('startDiaff8') == 0 and run.natives() == ['startDialog'], run.natives())
    require(run.stubs() == [('lump_load', (b'.lmp',)), ('Camera_update', (0,)), ('net_isLocalSlot', (0,))],
            run.stubs())
    checks += 1
    return checks


def check_valor_doors(run):
    checks = 0
    for fire, storm, key, dest in ((None, None, 0, None), (1, None, 1, 'fire1'),
                                   (None, 1, 1, 'storm1'), (1, 1, 1, 'storm1')):
        run.prepare('valor')
        if fire:
            run.var('mar_fire', fire)
        if storm:
            run.var('mar_storm', storm)
        require(run.entry('return4520') == key, (fire, storm))
        run.requests()
        require(run.entry('callScrib1e7') == 0, 'marrPortal')
        wanted = ['callScript', 'getv'] + (['newWorld'] if fire else []) + ['getv'] + (['newWorld'] if storm else [])
        require(run.natives() == wanted, (fire, storm, run.natives()))
        require(run.stubs() == CLOSE_MENUS * ((1 if fire else 0) + (1 if storm else 0)), run.stubs())
        if dest:
            run.requests(level=dest, orient=0xFF)
        else:
            run.requests()
        run.held()
        checks += 1
    run.prepare('valor')
    require(run.entry('return25eb') == 0 and run.natives() == [], run.natives())
    checks += 1
    for fire, gate, natives in ((None, None, ['getv', 'getv']),
                                (1, None, ['getv', 'getv', 'trigger', 'setv']),
                                (1, 1, ['getv', 'getv'])):
        run.prepare('valor')
        if fire:
            run.var('mar_fire', fire)
        if gate:
            run.var('gateon', gate)
        require(run.entry('callScri1ef1') == 0, 'gate')
        require(run.natives() == ['callScript'] + natives, (fire, gate, run.natives()))
        # No object named portal is planted, so trigger makes no virtual call.
        require(run.stubs() == [], run.stubs())
        if fire and not gate:
            run.stored('gateon', 1)
        run.held()
        checks += 1
    return checks


def check_honor(run):
    disc = run.disc
    checks = 0
    travel(run, 'valor2', 'newWorld6440', 'honor')
    travel(run, 'honor', 'newWorlda6a0', 'valor2')
    checks += 2
    title = disc.text('honor', 0x1258, 0)
    grant_natives = (['playerHasItem', 'playerHasItem', 'addHelpMessage', 'grantMission', 'removeQuest',
                      'soundSequence'] + ONE_PLAYER_LOOP + ['gamePaused'])
    grant_stubs = ([('inventory_countItemByName', (b'shardofvalor', 0))] * 2
                   + help_calls(disc.text('honor', 0x1200, 0), disc.text('honor', 0x1200, 1)) + SOUND_CALLS)

    def ticks(count, shells, paused=0):
        run.rig.responder.shells = shells
        run.mem.w32(G_PAUSED, paused)
        for _ in range(count):
            require(run.entry('shardCheck') == 0, 'shardCheck')

    for before, after0 in ((SENTINEL, DONE), (AVAIL, BOTH)):
        run.prepare('honor', shells=0, bytes0={7: before})
        run.quest(title)
        require(run.entry('start') == 0, 'honor start')
        require(run.natives() == ['setParticle', 'addDeferedCall', 'getv', 'playerHasItem'], run.natives())
        # particle_define is a stub that returns 0; its first argument is a pointer.
        require([name for name, _args in run.stubs()] == ['particle_define', 'inventory_countItemByName']
                and run.stubs()[1] == ('inventory_countItemByName', (b'shardofvalor', 0)), run.stubs())
        ticks(25, 0)
        require(run.natives() == ['gamePaused'] and run.stubs() == [], run.natives())
        run.held({7: (before, SENTINEL, SENTINEL, SENTINEL)})
        ticks(1, 1)
        require(run.natives() == grant_natives, run.natives())
        require(run.stubs() == grant_stubs, run.stubs())
        run.held({7: (after0, DONE, DONE, DONE)})
        require(run.quests() == (0, []) and run.mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests', run.quests())
        run.seed_kept()
        checks += 1
    # The count read at start must grow: equal counts do not grant.
    run.prepare('honor', shells=1)
    run.quest(title)
    run.entry('start')
    ticks(26, 1)
    require(run.natives() == ['playerHasItem', 'gamePaused'], run.natives())
    run.held()
    require(run.quests()[0] == 1, run.quests())
    checks += 1
    # A paused call does not advance the counter: the check moves one call later.
    run.prepare('honor', shells=0)
    run.entry('start')
    ticks(4, 0)
    ticks(1, 0, paused=1)
    ticks(21, 1)
    run.held()
    ticks(1, 1)
    run.held({7: (DONE,) * 4})
    checks += 1
    return checks


# ---- mission 8 -------------------------------------------------------------------------

def check_fire1(run):
    disc = run.disc
    title, body = disc.text('fire1', 0x0B0, 0), disc.text('fire1', 0x0B0, 1)
    checks = 0
    for before in (SENTINEL, AVAIL, BOTH):
        run.prepare('fire1', bytes0={8: before})
        run.var('startedMission8', 0x5A)
        run.var('currentMission', 0x5A)
        require(run.entry('start') == 0, 'fire1 start')
        adds = not (before & 2)
        require(run.natives() == ['getMissionComplete'] + (['addQuest'] if adds else [])
                + ['setMissionAvailable', 'setv', 'setv'], run.natives())
        require(run.stubs() == [], run.stubs())
        run.held({8: (R.available_byte(before, 1), SENTINEL, SENTINEL, SENTINEL)})
        run.stored('startedMission8', 1)
        run.stored('currentMission', 8)
        if adds:
            require(run.quests() == (1, [(title, body)]), run.quests())
        else:
            run.no_quest_edit()
        run.requests()
        checks += 1
    # Matt Marr's quest has the same title and another body. fire1 keeps it.
    run.prepare('fire1')
    run.quest(title, disc.text('valor', 0x668, 1))
    run.entry('start')
    require(run.quests() == (1, [(title, disc.text('valor', 0x668, 1))]), run.quests())
    checks += 1
    return checks


def check_fire_travel(run):
    routes = (
        ('fire1', 'newWorlda6b0', 'fire2', 'ENTRANCE-SENTINEL'),
        ('fire2', 'newWorld5cd', 'fire3', 'ENTRANCE-SENTINEL'),
        ('fire2', 'newWorldaaf1', 'fire1', 'ENTRANCE-SENTINEL'),
        ('fire3', 'setEntrabca8', 'fire4', 'centerladder'),
        ('fire3', 'setEntra5ac0', 'fire4', 'eastladder'),
        ('fire3', 'setEntra1124', 'fire4', 'westladder'),
        ('fire3', 'setEntraf090', 'fire4', 'southladder'),
        ('fire3', 'newWorlda6b0', 'fire2', 'ENTRANCE-SENTINEL'),
        ('fire4', 'setEntraf725', 'fire3', 'southladder'),
        ('fire4', 'setEntraf555', 'fire3', 'westladder'),
        ('fire4', 'setEntra3624', 'fire3', 'eastladder'),
        ('fire4', 'setEntraa02b', 'fire3', 'centerladder'),
        ('fire4', 'newWorld9251', 'fire5', 'ENTRANCE-SENTINEL'),
    )
    for level, entry, dest, door in routes:
        natives = ('newWorld',) if door == 'ENTRANCE-SENTINEL' else ('setEntrance', 'newWorld')
        travel(run, level, entry, dest, door, natives)
    checks = len(routes)
    for one, two, expect in ((None, None, 0), (1, None, 0), (None, 1, 0), (1, 1, 1)):
        run.prepare('fire3')
        if one:
            run.var('switch1done', one)
        if two:
            run.var('switch2done', two)
        require(run.entry('return7da1') == expect, (one, two))
        run.requests()
        checks += 1
    for entry, name, site in (('hideMonsc5f1', 'switch2done', 0x08C), ('hideMons7bb4', 'switch1done', 0x130)):
        info = run.disc.text('fire3', site, 0)
        run.prepare('fire3')
        run.var(name, 0x5A)
        require(run.entry(entry) == 0, entry)
        require(run.natives() == ['hideMonster', 'setv', 'setInfo'], run.natives())
        require(run.stubs() == info_calls(info), (entry, run.stubs()))
        run.stored(name, 1)
        run.held()
        checks += 1
    return checks


def check_fire5(run):
    disc = run.disc
    checks = 0
    fire_title = disc.text('fire1', 0x0B0, 0)
    count_call = [('inventory_countItemByName', (b'shardoffire', 0))]
    for killed, natives in ((None, ['playerHasItem', 'addDeferedCall', 'getv', 'setSaveInhibit', 'postAction']),
                            (1, ['playerHasItem', 'addDeferedCall', 'getv', 'postAction'])):
        run.prepare('fire5')
        if killed:
            run.var('killedDragon', killed)
        require(run.entry('start') == 0, 'fire5 start')
        require(run.natives() == natives, (killed, run.natives()))
        require(run.stubs() == count_call, run.stubs())
        require(run.deferred() == 'shardCheck' and run.posted() == 'absorb', (run.deferred(), run.posted()))
        if killed is None:
            run.stored('killedDragon', 0)
        run.held()
        run.no_quest_edit()
        checks += 1
    run.prepare('fire5')
    run.var('fire_sawDragon', 0)
    require(run.entry('absorb') == 0, 'absorb')
    require(run.natives() == ['getv', 'cutScene', 'setv', 'postAction'], run.natives())
    require(run.stubs() == M.cut_calls('dragon'), run.stubs())
    run.stored('fire_sawDragon', 1)
    require(run.posted() == 'firsaved', run.posted())
    require(run.post() == 0, 'firsaved')
    miniboss = ['setCFlag', 'setMonsterVal', 'setMonsterVal', 'setMonsterVal']
    require(run.natives() == ['saveCheckPoint', 'callScript'] + miniboss, run.natives())
    firsaved_stubs = run.stubs()
    require([name for name, _args in firsaved_stubs] == FIRSAVED_STUBS, firsaved_stubs)
    require(firsaved_stubs[1] == ('save_game', (0, 0, 1)), firsaved_stubs)
    run.held()
    checks += 1
    run.prepare('fire5')
    run.var('fire_sawDragon', 1)
    require(run.entry('absorb') == 0, 'second absorb')
    require(run.natives() == ['getv', 'callScript'] + miniboss and run.posted() == '', run.natives())
    checks += 1

    grant_natives = ['playerHasItem', 'addHelpMessage', 'setv', 'grantMission', 'soundSequence'] + ONE_PLAYER_LOOP
    grant_stubs = (count_call + help_calls(disc.text('fire5', 0x52C, 0), disc.text('fire5', 0x52C, 1))
                   + SOUND_CALLS)

    def ticks(count, shells, paused=0):
        run.rig.responder.shells = shells
        run.mem.w32(G_PAUSED, paused)
        for _ in range(count):
            M.clear_defer(run.mem)
            require(run.entry('shardCheck') == 0, 'shardCheck')

    for before, after0, paused in ((SENTINEL, DONE, 0), (AVAIL, BOTH, 0), (SENTINEL, DONE, 1)):
        run.prepare('fire5', shells=0, bytes0={8: before})
        run.quest(fire_title)
        run.var('fire_gotShard', 0x5A)
        run.entry('start')
        ticks(24, 1, paused)
        require(run.natives() == ['addDeferedCall'] and run.stubs() == [], run.natives())
        require(run.deferred() == 'shardCheck', run.deferred())
        run.held({8: (before, SENTINEL, SENTINEL, SENTINEL)})
        require(run.vars()['fire_gotshard'] == 0x5A, run.vars())
        ticks(1, 1, paused)
        # No gamePaused test in this entry: a paused call still counts.
        require(run.natives() == grant_natives, run.natives())
        require(run.stubs() == grant_stubs, run.stubs())
        run.stored('fire_gotShard', 1)
        run.held({8: (after0, DONE, DONE, DONE)})
        require(run.deferred() == '', run.deferred())
        # The grant does not remove the fire quest.
        require(run.quests() == (1, [(fire_title, 'plant-body')]), run.quests())
        run.seed_kept()
        checks += 1
    run.prepare('fire5', shells=1)
    run.entry('start')
    ticks(25, 1)
    require(run.natives() == ['playerHasItem', 'addDeferedCall'] and run.stubs() == count_call, run.natives())
    require(run.deferred() == 'shardCheck', run.deferred())
    run.held()
    checks += 1
    run.prepare('fire5')
    run.var('killedDragon', 0x5A)
    require(run.entry('callScri3971') == 0, 'death')
    require(run.natives() == ['callScript', 'setv', 'setSaveInhibit'] and run.stubs() == [], run.natives())
    run.stored('killedDragon', 1)
    run.held()
    checks += 1
    for planted, expect in ((None, 0), (1, 1), (0x5A, 0)):
        run.prepare('fire5')
        if planted is not None:
            run.var('fire_gotShard', planted)
        require(run.entry('return2c8d') == expect, planted)
        checks += 1
    info = disc.text('fire5', 0x76C, 0)
    for planted, stubs in ((None, info_calls(info)), (1, [])):
        run.prepare('fire5')
        if planted:
            run.var('fire_gotShard', planted)
        require(run.entry('callScricb6b') == 0, 'portal message')
        require(run.stubs() == stubs, run.stubs())
        checks += 1
    return checks


# saveCheckPoint reaches these two stubs; save_game returns 0, so nothing is saved.
FIRSAVED_STUBS = ['dbg_printf', 'save_game']


def check_obsfor1(run):
    disc = run.disc
    run.prepare('obsfor1')
    run.var('startedMission8', 0x5A)
    run.var('currentMission', 0x5A)
    require(run.entry('start') == 0, 'obsfor1 start')
    require(run.natives() == ['setMissionAvailable', 'setv', 'setv'] and run.stubs() == [], run.natives())
    run.held({8: (AVAIL, SENTINEL, SENTINEL, SENTINEL)})
    run.stored('startedMission8', 1)
    run.stored('currentMission', 8)
    run.no_quest_edit()
    run.prepare('obsfor1')
    require(run.entry('callScri7351') == 0, 'obsfor1 trigger')
    require(run.natives() == ['callScript', 'grantMission', 'addHelpMessage'], run.natives())
    require(run.stubs() == help_calls(disc.text('obsfor1', 0x158, 0), disc.text('obsfor1', 0x158, 1)),
            run.stubs())
    run.held({8: (DONE,) * 4})
    run.no_quest_edit()
    return 2


def check_seed(rig, disc, seed):
    run = Run(rig, disc, seed)
    checks = check_sites(disc)
    checks += check_links(disc)
    checks += check_swamp(run)
    checks += check_dis_start(run)
    checks += check_dis_portals(run)
    checks += check_dis_pause(run)
    checks += check_dis_bert(run)
    checks += check_dis_travel(run)
    checks += check_mission7_offer(run)
    checks += check_valor_start(run)
    checks += check_marr(run)
    checks += check_valor_doors(run)
    checks += check_honor(run)
    checks += check_fire1(run)
    checks += check_fire_travel(run)
    checks += check_fire5(run)
    checks += check_obsfor1(run)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--seed', type=int, action='append', dest='seeds')
    args = parser.parse_args()
    blob = open(args.elf, 'rb').read()
    if hashlib.sha256(blob).hexdigest() != ELF_SHA256:
        raise SystemExit('unexpected executable')
    disc = Disc(args.data)
    for seed in (args.seeds or [20973, 7]):
        rig = N.Rig(args.elf)
        rig.checkpoint()
        rig.responder = M.Quiet()
        count = check_seed(rig, disc, seed)
        print('PASS seed %d: %d mission-6/7/8 checks' % (seed, count))


if __name__ == '__main__':
    main()
