#!/usr/bin/env python3
"""Missions 9 to 12 and the ending against the original script machine.

The menu confirm that writes storm1, fay2/fay1, nit1 or bossgood/bossevil
stays in difftest_story_beats.py. This file runs the level and hub entries
after that request, the two ending levels, and frontend_start.

Quest and help keys are disc text. They are read from the script images at
the call sites listed in SITES and compared with what execution records, so
no key is written in this file. --keys-out writes the neutral-id map to an
untracked path (keep it under local/).

  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; \
  sys.path.insert(0,"tools"); \
  sys.argv=["difftest_story_mission912.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA"]; \
  runpy.run_path("tools/difftest_story_mission912.py", run_name="__main__")'
"""
import argparse
import hashlib
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE  # noqa: E402
import difftest_natives as N  # noqa: E402
import difftest_story_mission45 as M  # noqa: E402
import ref_story_route as R  # noqa: E402
import scr  # noqa: E402

ELF_SHA256 = M.ELF_SHA256
PLAYERS, MISSION, QUEST, QUEST_COUNT, REC = M.PLAYERS, M.MISSION, M.QUEST, M.QUEST_COUNT, M.REC
SENTINEL, FILL = M.SENTINEL, M.FILL
DECISION = 0x4C1B
FLAGS = 0x4C28                 # player_setFlag 0x1be398 / player_getFlag 0x1bfb80
FLAG_FILL = 0xA5A5A5A5         # bit 0 set, bit 4 clear
G_EXIT = 0x41B508              # g_sessionExitCode
G_COMPLETE = 0x4F85C5          # g_gameCompleteFlag
G_CONFIG = 0x4F8F38            # saved config block, completion bits
G_SAVE_INHIBIT = 0x50605C
G_MENU_OPEN = 0x41B4F8
FRONTEND_START = 0x1E1F34
FRONT_STATE = 0x4F6B78
FRONT_MENU = 0x4F6B7C
FRONT_CREDITS = 0x4F701A
FRONT_SKIP = 0x4F7019
CREDITS_LOAD = 0x223C64
MUSIC_GLOBAL = 0x2110E0
STREAM_CLEAR = 0x216130
TASK_ADD = 0x19E4A0
FRONTEND_RUN = 0x1E08F0
STORY = (8, 9, 10, 11, 12)
SOUND = [
    ('res_find', (b'fx.lmp', b'quest_complete.anm')),
    ('sound_playOnObject', (0, 0, 1065353216)),
    ('sound_setPlaysWhileFrozen', (0,)),
]
LEVELS = (
    'valor', 'storm1', 'storm1a', 'storm1b', 'storm1c', 'storm2', 'storm3', 'storm4',
    'storm5', 'fay1', 'fay2', 'fay3', 'nit1', 'nitdung1', 'nitdung2', 'nitdung4', 'nit2',
    'nitmar1', 'bossgood', 'bossevil', 'endgood', 'endbad', 'hub', 'hub2',
)
# (neutral id, level, script offset of the call, native, argument index).
# The key is whatever string the image holds there.
TEXT_SITES = (
    ('KV1', 'valor', 0x75C, 'removeQuest', 0),
    ('Q9.t', 'storm1', 0x218, 'addQuest', 0),
    ('Q9.b', 'storm1', 0x218, 'addQuest', 1),
    ('H9s.t', 'storm4', 0x470, 'addHelpMessage', 0),
    ('H9s.b', 'storm4', 0x470, 'addHelpMessage', 1),
    ('B9', 'storm2', 0xE64, 'showBust', 1),
    ('H9.t', 'storm2', 0xF10, 'addHelpMessage', 0),
    ('H9.b', 'storm2', 0xF10, 'addHelpMessage', 1),
    ('Q10g.t', 'fay2', 0x5B8, 'addQuest', 0),
    ('Q10g.b', 'fay2', 0x5B8, 'addQuest', 1),
    ('Q10e.t', 'fay1', 0x5E0, 'addQuest', 0),
    ('Q10e.b', 'fay1', 0x5E0, 'addQuest', 1),
    ('H10e.t', 'fay3', 0x12CC, 'addHelpMessage', 0),
    ('H10e.b', 'fay3', 0x12CC, 'addHelpMessage', 1),
    ('H10g.b', 'fay3', 0x13FC, 'addHelpMessage', 1),
    ('Q11.t', 'nit1', 0x190, 'addQuest', 0),
    ('Q11.b', 'nit1', 0x190, 'addQuest', 1),
    ('H11.t', 'nit2', 0x878, 'addHelpMessage', 0),
    ('H11.b', 'nit2', 0x878, 'addHelpMessage', 1),
    ('H11m.t', 'nitmar1', 0x19C, 'addHelpMessage', 0),
    ('H11m.b', 'nitmar1', 0x19C, 'addHelpMessage', 1),
    ('H12.t', 'bossgood', 0xADC, 'addHelpMessage', 0),
    ('H12.b', 'bossgood', 0xADC, 'addHelpMessage', 1),
)
# Non-text call sites: (level, offset, native, leading arguments).
SITES = (
    ('valor', 0x730, 'setMissionAvailable', (9, 1)),
    ('valor', 0x528, 'setMissionAvailable', (8, 1)),
    ('storm1', 0x1D8, 'getMissionComplete', (9,)),
    ('storm1', 0x24C, 'setMissionAvailable', (9, 1)),
    ('storm1', 0x2E0, 'postAction', ('absorb',)),
    ('storm1', 0x35C, 'cutScene', ('storm',)),
    ('storm4', 0x434, 'setPlayerFlag', (None, 4, 1)),
    ('storm2', 0x454, 'getPlayerFlag', (0, 4)),
    ('storm2', 0xF70, 'grantMission', (9,)),
    ('fay2', 0x620, 'setMissionAvailable', (10, 1)),
    ('fay1', 0x648, 'setMissionAvailable', (10, 1)),
    ('fay3', 0xE8C, 'grantMission', (10,)),
    ('nit1', 0xBC, 'setMissionAvailable', (11, 1)),
    ('nit2', 0x8D8, 'grantMission', (11,)),
    ('nitmar1', 0x1C8, 'grantMission', (11,)),
    ('bossgood', 0x9D4, 'newWorld', ('endgood',)),
    ('bossevil', 0x9D4, 'newWorld', ('endbad',)),
    ('endgood', 0x84, 'cutScene', ('endgood',)),
    ('endgood', 0xDC, 'grantMission', (12,)),
    ('endgood', 0x138, 'saveEndConfig', ()),
    ('endgood', 0x1D0, 'saveGame', ()),
    ('endgood', 0x270, 'leaveGame', (1,)),
    ('endbad', 0x84, 'cutScene', ('endbad',)),
    ('endbad', 0xDC, 'grantMission', (12,)),
    ('endbad', 0x270, 'leaveGame', (1,)),
)


class Answers(M.Quiet):
    def __init__(self):
        super().__init__()
        self.card = 0

    def answer(self, name, args):
        if name == 'memcard_getState':
            return self.card
        return super().answer(name, args)


require = M.require
mission = M.mission


def load_levels(data):
    return {name: M.lump_map(os.path.join(data, name.upper() + '.GOB')) for name in LEVELS}


def read_keys(levels):
    keys = {}
    for ident, level, off, native, index in TEXT_SITES:
        _publics, found, _pool = M.calls_in(levels[level]['script.scr'])
        got = [row for row in found if row[0] == off]
        require(len(got) == 1 and got[0][1] == native, (ident, level, hex(off)))
        text = got[0][2][index]
        require(isinstance(text, str) and text, (ident, text))
        keys[ident] = text
    # The bossevil help pair, fay3's other title, and the hub quests are the
    # same strings as the neutral ids above.
    _p, found, _q = M.calls_in(levels['bossevil']['script.scr'])
    require([r[2][:2] for r in found if r[0] == 0xADC] == [(keys['H12.t'], keys['H12.b'])], 'H12 evil')
    _p, found, _q = M.calls_in(levels['fay3']['script.scr'])
    require([r[2][0] for r in found if r[0] == 0x13FC] == [keys['H10e.t']], 'H10 title')
    require([r[2][0] for r in found if r[0] == 0xF28] == [keys['Q10e.t']], 'fay3 evil remove')
    require([r[2][0] for r in found if r[0] == 0xF90] == [keys['Q10g.t']], 'fay3 good remove')
    _p, found, _q = M.calls_in(levels['nit2']['script.scr'])
    require([r[2][0] for r in found if r[0] == 0x938] == [keys['Q11.t']], 'nit2 remove')
    return keys


def check_sites(levels):
    checks = 0
    for level, off, native, args in SITES:
        _publics, found, _pool = M.calls_in(levels[level]['script.scr'])
        got = [row for row in found if row[0] == off]
        require(len(got) == 1 and got[0][1] == native, (level, hex(off), got[:1]))
        for want, have in zip(args, got[0][2]):
            require(want is None or have == want, (level, hex(off), have))
        checks += 1
    return checks


def check_links(levels):
    want = {
        'storm1': {'action=setEntrac6fa', 'action=setEntra6fc5', 'action=newWorld68d7',
                   'action=newWorld92e0', 'action=newWorldebc5'},
        'storm1a': {'action=setEntra52d2'}, 'storm1b': {'action=setEntra31d'},
        'storm1c': {'action=setEntra2ec7', 'action=setEntraf253'},
        'storm2': {'action=newWorld1940', 'action=newWorld43c8', 't=callScri6100'},
        'storm3': {'action=newWorld43c8', 'action=newWorlda363', 't=newWorlda363'},
        'storm4': {'action=newWorld1dd1', 't=newWorld1dd1'},
        'storm5': {'action=newWorld1dd1', 'action=newWorldebc5'},
        'fay1': {'action=newWorldf59a'},
        'fay2': {'action=setEntrad0dc'},
        'fay3': {'action=newWorld5640', 'action=newWorld6f17', 'action=newWorldbff',
                 'action=anchorscript'},
        'nit1': {'action=newWorld3ab3', 'action=newWorld980'},
        'nitdung1': {'action=newWorld9ad', 'action=newWorldb992'},
        'nitdung2': {'action=newWorld22cd', 'action=newWorld3da6'},
        'nitdung4': {'action=newWorldbafc'},
        'nit2': {'action=newWorld6e37'},
        'nitmar1': {'t=callScri7351'},
        'bossgood': {'action=callScri53d3', 'key=returnc798', 't=callScri1ef1'},
        'bossevil': {'action=callScri53d3', 'key=returnc798', 't=callScri1ef1'},
    }
    for level, props in want.items():
        have = M.prop_set(levels[level]['objects.ob'])
        require(props <= have, (level, sorted(props - have)))
    mattmar = M.dbin_rows(levels['valor']['mattmar.dbin'])
    require(mattmar[0] == ('if2a2e', [('', 'setMissi1bb4', 1)]), mattmar[0])
    require(mattmar[2] == ('ifa054', [('', 'setMissie47a', 3)]), mattmar[2])
    nodes = {
        ('hub', 'firiona.dbin'): {24: ('if3a40', ['setMissi22ce', 'setMissi8ea7']),
                                  26: ('if2302', ['setMissi3604']),
                                  29: ('ifb354', ['setMissia052', 'setMissib397'])},
        ('hub', 'firiona_bak.dbin'): {22: ('if3a40', ['setMissi4db8', 'setMissi9964']),
                                      24: ('if2302', ['setMissi6baa', 'setMissi8b33']),
                                      27: ('ifb354', ['setMissia052', 'setMissi350c'])},
        ('hub2', 'natasla.dbin'): {19: ('if3a40', ['setMissiec81']),
                                   21: ('if2302', ['setMissi3604', 'setMissi2732']),
                                   24: ('ifb354', ['setMissia052', 'setMissib397'])},
        ('hub2', 'natasla_bak.dbin'): {20: ('if3a40', ['setMissi4db8', 'setMissi9964']),
                                       22: ('if2302', ['setMissi6baa', 'setMissi8b33']),
                                       25: ('ifb354', ['setMissia052', 'setMissi350c'])},
    }
    for (level, name), rows in nodes.items():
        table = M.dbin_rows(levels[level][name])
        for index, (cond, actions) in rows.items():
            require(table[index][0] == cond, (name, index, table[index][0]))
            require([a for _c, a, _t in table[index][1]] == actions, (name, index, table[index][1]))
    return len(want) + 2 + sum(len(rows) for rows in nodes.values())


def prepare(rig, levels, level, seed, shells=0, evil=0, decision=0, flags=FLAG_FILL):
    mem = M.prepare(rig, levels[level]['script.scr'], seed, shells=shells, evil=evil)
    require(rig.image_pause == (0, 0, 0), rig.image_pause)
    rig.responder.card = 0
    for slot in range(4):
        mem.w8(PLAYERS + slot * REC + DECISION, decision)
        mem.w32(PLAYERS + slot * REC + FLAGS, flags)
    return mem


def bytes_at(mem, index):
    return [mission(mem, slot, index) for slot in range(4)]


def held(mem, skip=()):
    """Every story byte 8..12 on every record, other than those in skip, is the sentinel."""
    return all(mission(mem, slot, index) == SENTINEL
               for slot in range(4) for index in STORY if (slot, index) not in skip
               and index not in skip)


def flag_words(mem):
    return [mem.u32(PLAYERS + slot * REC + FLAGS) for slot in range(4)]


def no_quest(mem):
    return (mem.u32(PLAYERS + QUEST_COUNT) == 0
            and mem.read(PLAYERS + QUEST, 0x40) == bytes([FILL]) * 0x40)


def quest_is(mem, title, body):
    return (mem.u32(PLAYERS + QUEST_COUNT) == 1 and mem.cstr(PLAYERS + QUEST, 32) == title
            and mem.cstr(PLAYERS + QUEST + 0x20, 32) == body)


def removed(mem):
    return mem.u32(PLAYERS + QUEST_COUNT) == 0 and mem.cstr(PLAYERS + QUEST, 32) == 'NoQuests'


def wrote(rig, addr, size, value):
    return any(a == addr and s == size and v == value for _pc, a, s, v in rig.emu.writes)


def pending(mem):
    return mem.cstr(N.N.G_PENDING_LEVEL, 32)


def help_calls(keys, prefix):
    return [('text_lookup', (keys[prefix + '.t'].encode(),)),
            ('text_lookup', (keys[prefix + '.b'].encode(),)),
            ('hud_showHelpMessage', (0xFFFFFFFF, 0, 0))]


def ticks(rig, mem, entry, count, shells=None, paused=0):
    if shells is not None:
        rig.responder.shells = shells
    mem.w32(M.G_PAUSED, paused)
    for _ in range(count):
        M.clear_defer(mem)
        result = M.run_entry(rig, entry)
        require(result == (0, ''), (entry, result))
    # The next prepare checks the image value, so a paused case must not leak.
    mem.w32(M.G_PAUSED, 0)


# ---- mission 9 ------------------------------------------------------------------------

def check_m9_offer(rig, levels, keys, seed):
    checks = 0
    on = R.available_byte(SENTINEL, 1)
    mem = prepare(rig, levels, 'valor', seed)
    M.plant_quest(rig, keys['KV1'], 'plant-body')
    require(M.run_entry(rig, 'setMissie47a') == (0, ''), 'setMissie47a')
    require(bytes_at(mem, 9) == [on, SENTINEL, SENTINEL, SENTINEL], bytes_at(mem, 9))
    require(held(mem, skip=(9,)), 'offer other bytes')
    require(removed(mem), 'offer removes KV1')
    require(rig.calls == [], rig.calls)
    checks += 1
    mem = prepare(rig, levels, 'valor', seed)
    M.plant_quest(rig, 'OTHER-TITLE', 'plant-body')
    M.run_entry(rig, 'setMissie47a')
    require(mem.u32(PLAYERS + QUEST_COUNT) == 1 and mem.cstr(PLAYERS + QUEST, 32) == 'OTHER-TITLE',
            'other quest kept')
    checks += 1
    mem = prepare(rig, levels, 'valor', seed)
    require(M.run_entry(rig, 'setMissi1bb4') == (0, ''), 'setMissi1bb4')
    require(bytes_at(mem, 8) == [on, SENTINEL, SENTINEL, SENTINEL] and held(mem, skip=(8,)), 'm8')
    require(no_quest(mem) and rig.calls == [], 'm8 quest')
    checks += 1
    for entry, index in (('if2a2e', 8), ('ifa054', 9)):
        for byte in (0xA0, 0xA1, 0xA2, 0xA3):
            for other in (0xA0, 0xA3):
                mem = prepare(rig, levels, 'valor', seed)
                mem.w8(PLAYERS + MISSION + index, byte)
                mem.w8(PLAYERS + MISSION + (17 - index), other)
                got = M.run_entry(rig, entry)
                require(got == (0 if byte & 1 else 1, ''), (entry, hex(byte), hex(other), got))
                require(rig.calls == [], rig.calls)
                checks += 1
    return checks


def check_storm1(rig, levels, keys, seed):
    checks = 0
    for start_byte, quest in ((SENTINEL, True), (R.complete_byte(SENTINEL, -1), False)):
        mem = prepare(rig, levels, 'storm1', seed)
        mem.w8(PLAYERS + MISSION + 9, start_byte)
        M.plant_mission_vars(rig, mem, (('startedMission9', 1), ('currentMission', 9)))
        require(M.run_entry(rig, 'start') == (0, ''), 'storm1 start')
        require(bytes_at(mem, 9) == [R.available_byte(start_byte, 1), SENTINEL, SENTINEL, SENTINEL],
                bytes_at(mem, 9))
        require(held(mem, skip=(9,)), 'storm1 other bytes')
        M.require_stored(rig, mem, 'startedmission9', 1)
        M.require_stored(rig, mem, 'currentmission', 9)
        if quest:
            require(quest_is(mem, keys['Q9.t'], keys['Q9.b']), 'Q9')
        else:
            require(no_quest(mem), 'no Q9 when complete')
        require(mem.u32(PLAYERS + REC + QUEST_COUNT) == 0x5A5A5A5A, 'other count')
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb', 'post')
        require(pending(mem) == 'PENDING-SENTINEL' and rig.calls == [], 'storm1 pending')
        require(mem.u32(N.N.G_RAND_SEED) == seed, 'seed')
        checks += 1
    # The cut is gated on sawstorm == 0, so a planted 0x5A also withholds it.
    for planted, cut in ((None, True), (0, True), (0x5A, False), (1, False)):
        mem = prepare(rig, levels, 'storm1', seed)
        if planted is not None:
            M.plant_var(rig, 'sawstorm', planted)
        require(M.run_entry(rig, 'absorb') == (0, ''), 'absorb')
        if cut:
            require(rig.calls == M.cut_calls('storm'), rig.calls)
            M.require_stored(rig, mem, 'sawstorm', 1)
        else:
            require(rig.calls == [], rig.calls)
            require(dict(M.variables(mem))['sawstorm'] == planted, 'sawstorm')
            require(not rig.emu.writes or all(a != M.var_addr(mem, 'sawstorm')
                                              for _p, a, _s, _v in rig.emu.writes), 'no store')
        checks += 1
    return checks


TRAVEL = (
    ('storm1', 'setEntrac6fa', 'storm1c', 'entrance'),
    ('storm1', 'setEntra6fc5', 'storm1c', 'exit'),
    ('storm1', 'newWorld68d7', 'storm1a', None),
    ('storm1', 'newWorld92e0', 'storm1b', None),
    ('storm1', 'newWorldebc5', 'storm2', None),
    ('storm1a', 'setEntra52d2', 'storm1', '1a'),
    ('storm1b', 'setEntra31d', 'storm1', '1b'),
    ('storm1c', 'setEntra2ec7', 'storm1', 'entrance'),
    ('storm1c', 'setEntraf253', 'storm1', 'exit'),
    ('storm2', 'newWorld1940', 'storm1', 'grenidor'),
    ('storm2', 'newWorld43c8', 'storm5', None),
    ('storm5', 'newWorldebc5', 'storm2', None),
    ('storm5', 'newWorld1dd1', 'storm3', None),
    ('storm3', 'newWorld43c8', 'storm5', None),
    ('storm3', 'newWorlda363', 'storm4', None),
    ('storm4', 'newWorld1dd1', 'storm3', None),
    ('fay2', 'setEntrad0dc', 'fay3', 'kelethin'),
    ('fay1', 'newWorldf59a', 'fay3', None),
    ('fay3', 'newWorld5640', 'fay1', None),
    ('fay3', 'newWorldbff', 'fay2', None),
    ('fay3', 'newWorld6f17', 'faybonus', None),
    ('nit1', 'newWorld980', 'nitdung1', None),
    ('nit1', 'newWorld3ab3', 'nitdung4', None),
    ('nitdung1', 'newWorld9ad', 'nit1', 'n1nd1'),
    ('nitdung1', 'newWorldb992', 'nitdung2', 'nd1nd2'),
    ('nitdung2', 'newWorld22cd', 'nitdung1', 'nd1nd2'),
    ('nitdung2', 'newWorld3da6', 'nit2', 'nd2n2'),
    ('nit2', 'newWorld6e37', 'nitdung2', 'nd2n2'),
    ('nitdung4', 'newWorldbafc', 'nit1', 'n1nd4'),
)


def check_travel(rig, levels, seed):
    for level, entry, dest, door in TRAVEL:
        mem = prepare(rig, levels, level, seed)
        require(M.run_entry(rig, entry) == (0, ''), entry)
        require(pending(mem) == dest, (level, entry, pending(mem)))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == (door or 'ENTRANCE-SENTINEL'), (entry, door))
        require(mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, entry)
        require(held(mem) and no_quest(mem), entry)
        require(rig.calls == [('net_closeLocalMenus', (0,))], rig.calls)
        require(mem.u32(N.N.G_RAND_SEED) == seed, entry)
    return len(TRAVEL)


def check_storm4(rig, levels, keys, seed):
    checks = 0
    mem = prepare(rig, levels, 'storm4', seed)
    M.plant_var(rig, 'currentMission', 0x5A)
    require(M.run_entry(rig, 'start') == (0, ''), 'storm4 start')
    M.require_stored(rig, mem, 'currentmission', 9)
    require(rig.calls == [('inventory_countItemByName', (b'shardofstorms', 0))], rig.calls)
    require(M.defer_name(mem) == 'shardCheck', M.defer_name(mem))
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb' and held(mem), 'storm4 post')
    checks += 1
    mem = prepare(rig, levels, 'storm4', seed)
    require(M.run_entry(rig, 'absorb') == (0, ''), 'storm4 absorb')
    require(rig.calls == M.cut_calls('boss'), rig.calls)
    M.require_stored(rig, mem, 'sawboss', 1)
    require(mem.cstr(N.N.G_POST_ACTION, 32) == 'cutsave', 'cutsave post')
    checks += 1
    grant_calls = ([('inventory_countItemByName', (b'shardofstorms', 0))] + help_calls(keys, 'H9s')
                   + [('player_voice', (0, 9))])
    for shells, paused_at, grants in ((1, None, True), (2, None, True), (0, None, False), (1, 24, True)):
        mem = prepare(rig, levels, 'storm4', seed)
        M.run_entry(rig, 'start')
        M.plant_var(rig, 'stm_gotShard', 0x5A)
        ticks(rig, mem, 'shardCheck', 24, shells=0)
        require(flag_words(mem) == [FLAG_FILL] * 4, 'early flag')
        require(M.defer_name(mem) == 'shardCheck' and rig.calls == [], 'early call')
        if paused_at is not None:
            ticks(rig, mem, 'shardCheck', 1, shells=shells, paused=1)
            require(flag_words(mem) == [FLAG_FILL] * 4 and rig.calls == [], 'paused tick')
            require(dict(M.variables(mem))['stm_gotshard'] == 0x5A, 'paused shard')
        ticks(rig, mem, 'shardCheck', 1, shells=shells)
        if grants:
            require(flag_words(mem) == [FLAG_FILL | 0x10] * 4, [hex(w) for w in flag_words(mem)])
            M.require_stored(rig, mem, 'stm_gotshard', 1)
            require(rig.calls == grant_calls, rig.calls)
            require(mem.cstr(N.N.G_POST_ACTION, 32) == 'secondMsgDelay', 'second msg')
            require(M.defer_name(mem) == '', 'queued on grant')
        else:
            require(flag_words(mem) == [FLAG_FILL] * 4, 'no flag')
            require(rig.calls == [('inventory_countItemByName', (b'shardofstorms', 0))], rig.calls)
            require(dict(M.variables(mem))['stm_gotshard'] == 0x5A, 'no shard store')
        require(held(mem), 'storm4 grants nothing')
        checks += 1
    return checks


def check_storm2(rig, levels, keys, seed):
    checks = 0
    for flag, carried in ((FLAG_FILL | 0x10, True), (FLAG_FILL, False)):
        mem = prepare(rig, levels, 'storm2', seed, flags=flag)
        M.plant_var(rig, 'currentMission', 0x5A)
        require(M.run_entry(rig, 'start') == (0, ''), 'storm2 start')
        M.require_stored(rig, mem, 'currentmission', 9)
        require(flag_words(mem) == [FLAG_FILL] * 4, [hex(w) for w in flag_words(mem)])
        M.require_stored(rig, mem, 'stm_gotshard', 1 if carried else 0)
        require(M.defer_name(mem) == ('checkEveryFrame' if carried else ''), M.defer_name(mem))
        require(rig.calls == [('automap_revealAll', ())], rig.calls)
        require(held(mem), 'storm2 start bytes')
        checks += 1
    bust = [('text_lookup', (keys['B9'].encode(),)),
            ('hud_setBust', (b'bust_bubonian.tex', 0, 0, 0xFFFFFFFF))]
    done = R.complete_byte(SENTINEL, -1)
    for shard in (1, 0):
        mem = prepare(rig, levels, 'storm2', seed)
        M.plant_var(rig, 'stm_gotShard', shard)
        ticks(rig, mem, 'checkEveryFrame', 100)
        require(rig.calls == bust and held(mem), ('100th', rig.calls))
        require(dict(M.variables(mem))['storm2cleared'] == 0, 'not cleared yet')
        ticks(rig, mem, 'checkEveryFrame', 1)
        M.require_stored(rig, mem, 'storm2cleared', 1)
        if shard:
            require(rig.calls == bust + help_calls(keys, 'H9') + SOUND, rig.calls)
            require(bytes_at(mem, 9) == [done] * 4 and held(mem, skip=(9,)), bytes_at(mem, 9))
        else:
            require(rig.calls == bust + help_calls(keys, 'H9'), rig.calls)
            require(held(mem), 'no shard, no grant')
        require(M.defer_name(mem) == 'checkEveryFrame', 'requeue')
        ticks(rig, mem, 'checkEveryFrame', 1)
        require(rig.calls == [], ('after clear', rig.calls))
        checks += 1
    mem = prepare(rig, levels, 'storm2', seed)
    M.plant_var(rig, 'stm_gotShard', 1)
    ticks(rig, mem, 'checkEveryFrame', 50)
    ticks(rig, mem, 'checkEveryFrame', 10, paused=1)
    ticks(rig, mem, 'checkEveryFrame', 50)
    require(held(mem) and dict(M.variables(mem))['storm2cleared'] == 0, 'paused ticks count')
    ticks(rig, mem, 'checkEveryFrame', 1)
    require(bytes_at(mem, 9) == [done] * 4, 'grant after unpaused 100')
    checks += 1
    return checks


# ---- mission 10 -----------------------------------------------------------------------

def check_fay(rig, levels, keys, seed):
    checks = 0
    # preStart only decides while both variables are absent or 0.
    for level, undecided in (('fay2', 'good'), ('fay1', 'evil')):
        for decision, evil in ((0, 0), (0, 1), (1, 0), (1, 1)):
            mem = prepare(rig, levels, level, seed, evil=evil, decision=decision)
            require(M.run_entry(rig, 'preStart') == (0, ''), level + ' preStart')
            side = undecided if not decision else ('evil' if evil else 'good')
            M.require_stored(rig, mem, 'playerisevil', 1 if side == 'evil' else 0)
            M.require_stored(rig, mem, 'playerisgood', 1 if side == 'good' else 0)
            require(rig.calls == [('lump_load', (b'bust.lmp',))], rig.calls)
            require(held(mem) and no_quest(mem), level)
            checks += 1
        mem = prepare(rig, levels, level, seed, evil=1, decision=1)
        M.plant_var(rig, 'playerisgood', 1)
        M.run_entry(rig, 'preStart')
        require(dict(M.variables(mem))['playerisgood'] == 1
                and dict(M.variables(mem)).get('playerisevil') == 0, 'kept decision')
        checks += 1
    for level, quest_evil, ident in (('fay2', 0, 'Q10g'), ('fay1', 1, 'Q10e')):
        for evil in (0, 1):
            for start_byte in (SENTINEL, R.complete_byte(SENTINEL, -1)):
                mem = prepare(rig, levels, level, seed, evil=evil)
                mem.w8(PLAYERS + MISSION + 10, start_byte)
                M.plant_mission_vars(rig, mem, (('startedMission10', 1), ('currentMission', 10)))
                require(M.run_entry(rig, 'start') == (0, ''), level + ' start')
                require(bytes_at(mem, 10) == [R.available_byte(start_byte, 1)] + [SENTINEL] * 3,
                        bytes_at(mem, 10))
                require(held(mem, skip=(10,)), level)
                M.require_stored(rig, mem, 'startedmission10', 1)
                M.require_stored(rig, mem, 'currentmission', 10)
                if evil == quest_evil and start_byte == SENTINEL:
                    require(quest_is(mem, keys[ident + '.t'], keys[ident + '.b']), (level, evil))
                else:
                    require(no_quest(mem), (level, evil, 'quest'))
                require(M.defer_name(mem) == 'checkEachFrame' and rig.calls == [], rig.calls)
                # Both side variables are absent, so the box roll (getRand) is not reached.
                require(mem.u32(N.N.G_RAND_SEED) == seed, (level, 'rand box'))
                checks += 1
    done = R.complete_byte(SENTINEL, -1)
    for side, title in (('playerisgood', 'Q10g.t'), ('playerisevil', 'Q10e.t')):
        mem = prepare(rig, levels, 'fay3', seed)
        M.plant_var(rig, side, 1)
        M.plant_quest(rig, keys[title], 'plant-body')
        M.plant_var(rig, 'fay3done', 0x5A)
        for count in range(1, 8):
            require(M.run_entry(rig, 'anchorscript') == (0, ''), 'anchor')
            require(dict(M.variables(mem))['anchcompleted'] == count, count)
            require(held(mem) and mem.u32(PLAYERS + QUEST_COUNT) == 1, ('early', count))
            require(rig.calls == [], rig.calls)
        require(M.run_entry(rig, 'anchorscript') == (0, ''), 'anchor 8')
        require(bytes_at(mem, 10) == [done] * 4 and held(mem, skip=(10,)), bytes_at(mem, 10))
        M.require_stored(rig, mem, 'fay3done', 1)
        require(removed(mem), (side, 'quest'))
        require(rig.calls == [], rig.calls)
        checks += 1
    mem = prepare(rig, levels, 'fay3', seed)
    M.plant_var(rig, 'playerisgood', 1)
    M.plant_quest(rig, keys['Q10e.t'], 'plant-body')
    for _ in range(8):
        M.run_entry(rig, 'anchorscript')
    require(bytes_at(mem, 10) == [done] * 4 and mem.u32(PLAYERS + QUEST_COUNT) == 1,
            'good side keeps evil quest')
    checks += 1
    for side, other, text in (('playerisgood', 'Q10g.t', 'H10g'), ('playerisevil', 'Q10e.t', 'H10e')):
        mem = prepare(rig, levels, 'fay3', seed)
        M.plant_var(rig, side, 1)
        M.plant_quest(rig, keys[other], 'plant-body')
        require(M.run_entry(rig, 'missionDone') == (0, ''), 'missionDone')
        body = keys[text + '.b']
        want = SOUND + [('text_lookup', (keys['H10e.t'].encode(),)), ('text_lookup', (body.encode(),)),
                        ('hud_showHelpMessage', (0xFFFFFFFF, 0, 0))]
        require(rig.calls == want, rig.calls)
        require(removed(mem) and held(mem), side)
        checks += 1
    return checks


# ---- mission 11 -----------------------------------------------------------------------

def check_nit(rig, levels, keys, seed):
    checks = 0
    for start_byte in (SENTINEL, R.complete_byte(SENTINEL, -1)):
        mem = prepare(rig, levels, 'nit1', seed)
        mem.w8(PLAYERS + MISSION + 11, start_byte)
        M.plant_mission_vars(rig, mem, (('startedMission11', 1), ('currentMission', 11)))
        require(M.run_entry(rig, 'start') == (0, ''), 'nit1 start')
        require(bytes_at(mem, 11) == [R.available_byte(start_byte, 1)] + [SENTINEL] * 3, 'nit1 byte')
        require(held(mem, skip=(11,)), 'nit1 others')
        M.require_stored(rig, mem, 'startedmission11', 1)
        M.require_stored(rig, mem, 'currentmission', 11)
        if start_byte == SENTINEL:
            require(quest_is(mem, keys['Q11.t'], keys['Q11.b']), 'Q11')
        else:
            require(no_quest(mem), 'no Q11 when complete')
        words = dict(M.variables(mem))['faywords']
        require(1 <= words <= 4 and mem.u32(N.N.G_RAND_SEED) != seed, ('faywords', words))
        require(rig.calls == [] and pending(mem) == 'PENDING-SENTINEL', rig.calls)
        checks += 1
    done = R.complete_byte(SENTINEL, -1)
    for shells, grants in ((1, True), (0, False)):
        mem = prepare(rig, levels, 'nit2', seed)
        require(M.run_entry(rig, 'start') == (0, ''), 'nit2 start')
        require(rig.calls == [('inventory_countItemByName', (b'shardofnightmare', 0))], rig.calls)
        require(M.defer_name(mem) == 'shardCheck', 'nit2 defer')
        M.plant_quest(rig, keys['Q11.t'], 'plant-body')
        M.plant_var(rig, 'nit_gotShard', 0x5A)
        ticks(rig, mem, 'shardCheck', 24, shells=0)
        require(held(mem) and rig.calls == [], 'nit2 early')
        ticks(rig, mem, 'shardCheck', 1, shells=shells)
        if grants:
            require(bytes_at(mem, 11) == [done] * 4 and held(mem, skip=(11,)), bytes_at(mem, 11))
            M.require_stored(rig, mem, 'nit_gotshard', 1)
            require(removed(mem), 'Q11 removed')
            require(rig.calls == [('inventory_countItemByName', (b'shardofnightmare', 0))]
                    + help_calls(keys, 'H11') + SOUND, rig.calls)
            require(M.defer_name(mem) == '', 'nit2 queued on grant')
        else:
            require(held(mem) and mem.u32(PLAYERS + QUEST_COUNT) == 1, 'nit2 no grant')
            require(dict(M.variables(mem))['nit_gotshard'] == 0x5A, 'nit2 no store')
        checks += 1
    # nit2 shardCheck has no gamePaused test: a paused tick still counts.
    mem = prepare(rig, levels, 'nit2', seed)
    M.run_entry(rig, 'start')
    ticks(rig, mem, 'shardCheck', 24, shells=0, paused=1)
    ticks(rig, mem, 'shardCheck', 1, shells=1, paused=1)
    require(bytes_at(mem, 11) == [done] * 4, 'paused nit2 grant')
    checks += 1
    mem = prepare(rig, levels, 'nitmar1', seed)
    require(M.run_entry(rig, 'start') == (0, ''), 'nitmar1 start')
    require(bytes_at(mem, 11) == [R.available_byte(SENTINEL, 1)] + [SENTINEL] * 3, 'nitmar1 avail')
    require(no_quest(mem) and rig.calls == [], 'nitmar1 quest')
    mem = prepare(rig, levels, 'nitmar1', seed)
    require(M.run_entry(rig, 'callScri7351') == (0, ''), 'nitmar1 trigger')
    require(bytes_at(mem, 11) == [done] * 4 and held(mem, skip=(11,)), 'nitmar1 grant')
    require(rig.calls == help_calls(keys, 'H11m'), rig.calls)
    require(no_quest(mem), 'nitmar1 no quest edit')
    return checks + 2


# ---- mission 12 and the ending --------------------------------------------------------

def check_boss(rig, levels, keys, seed):
    checks = 0
    on = R.available_byte(SENTINEL, 1)
    done = R.complete_byte(SENTINEL, -1)
    for level, item, killed, ending in (('bossgood', b'shardoffear', 'killedthule', 'endgood'),
                                        ('bossevil', b'shardoftranquility', 'killedmar', 'endbad')):
        mem = prepare(rig, levels, level, seed)
        mem.w32(G_SAVE_INHIBIT, 0x5A5A5A5A)
        M.plant_mission_vars(rig, mem, (('startedMission12', 1), ('currentMission', 12)))
        require(M.run_entry(rig, 'start') == (0, ''), level + ' start')
        require(bytes_at(mem, 12) == [on] + [SENTINEL] * 3 and held(mem, skip=(12,)), bytes_at(mem, 12))
        M.require_stored(rig, mem, 'startedmission12', 1)
        M.require_stored(rig, mem, 'currentmission', 12)
        M.require_stored(rig, mem, killed, 0)
        require(mem.u32(G_SAVE_INHIBIT) == 1 and wrote(rig, G_SAVE_INHIBIT, 4, 1), 'save inhibit')
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorb' and M.defer_name(mem) == 'shardCheck', level)
        require(rig.calls == [('inventory_countItemByName', (item, 0))], rig.calls)
        require(no_quest(mem), level)
        checks += 1
        for shells, grants in ((1, True), (0, False)):
            mem = prepare(rig, levels, level, seed)
            M.run_entry(rig, 'start')
            M.plant_var(rig, 'finalShard', 0x5A)
            ticks(rig, mem, 'shardCheck', 24, shells=0)
            require(bytes_at(mem, 12) == [on] + [SENTINEL] * 3 and rig.calls == [], 'boss early')
            ticks(rig, mem, 'shardCheck', 1, shells=shells)
            if grants:
                require(bytes_at(mem, 12) == [R.complete_byte(on, -1)] + [done] * 3, bytes_at(mem, 12))
                M.require_stored(rig, mem, 'finalshard', 1)
                require(rig.calls == [('inventory_countItemByName', (item, 0))] + help_calls(keys, 'H12'),
                        rig.calls)
                require(M.defer_name(mem) == '', 'boss queued on grant')
            else:
                require(bytes_at(mem, 12) == [on] + [SENTINEL] * 3, 'boss no grant')
                require(dict(M.variables(mem))['finalshard'] == 0x5A, 'boss no store')
            require(held(mem, skip=(12,)), level)
            checks += 1
        for shard, key in ((None, 0), (0, 0), (1, 1)):
            mem = prepare(rig, levels, level, seed)
            if shard is not None:
                M.plant_var(rig, 'finalShard', shard)
            require(M.run_entry(rig, 'returnc798') == (key, ''), (level, shard))
            checks += 1
        for shard, fired, stores in ((1, None, True), (1, 1, False), (0, None, False)):
            mem = prepare(rig, levels, level, seed)
            M.plant_var(rig, 'finalShard', shard)
            M.plant_var(rig, 'firedgate', 0x5A if fired is None else fired)
            if fired is None:
                mem.write(M.var_addr(mem, 'firedgate'), b'\0')
            require(M.run_entry(rig, 'gatewaytrigger') == (0, ''), 'gate')
            if stores:
                M.require_stored(rig, mem, 'firedgate', 1)
            else:
                require(not any(a == M.var_addr(mem, 'firedgate') for _p, a, _s, _v in rig.emu.writes),
                        'no gate store')
            # trigger('portal', 0) found no object named portal: no virtual call.
            require(rig.calls == [], rig.calls)
            checks += 1
        mem = prepare(rig, levels, level, seed)
        mem.w32(G_SAVE_INHIBIT, 0x5A5A5A5A)
        require(M.run_entry(rig, 'callScri53d3') == (0, ''), level + ' end')
        require(pending(mem) == ending and mem.u8(N.N.G_PENDING_ORIENT) == 0xFF, pending(mem))
        require(mem.cstr(N.N.G_ENTRANCE_NAME, 32) == 'ENTRANCE-SENTINEL', 'end entrance')
        require(mem.u32(G_SAVE_INHIBIT) == 0 and wrote(rig, G_SAVE_INHIBIT, 4, 0), 'inhibit cleared')
        # setPlayerFlag(-1, 0, 0) with one player clears bit 0 on record 0 only.
        require(flag_words(mem) == [FLAG_FILL & ~1] + [FLAG_FILL] * 3, [hex(w) for w in flag_words(mem)])
        finds = [name for name, _args in rig.calls if name == 'inventory_findItemBySubstring']
        require(len(finds) == 25 and rig.calls[-1] == ('net_closeLocalMenus', (0,))
                and len(rig.calls) == 26, rig.calls[-2:])
        require(all(args[0] == 0 for name, args in rig.calls[:25]), 'player 0 only')
        require(held(mem) and no_quest(mem), 'end bytes')
        checks += 1
        for entry, var in (('absorb', 'saw' + killed[6:]), ('killedboss', killed + ('s' if level == 'bossgood' else ''))):
            mem = prepare(rig, levels, level, seed)
            M.plant_var(rig, var, 0x5A if entry == 'killedboss' else 0)
            require(M.run_entry(rig, entry) == (0, ''), entry)
            M.require_stored(rig, mem, var.lower(), 1)
            if entry == 'absorb':
                require(rig.calls == M.cut_calls('boss'), rig.calls)
                require(mem.cstr(N.N.G_POST_ACTION, 32) == 'cutsave', 'boss cutsave')
            else:
                require(rig.calls == [], rig.calls)
            require(held(mem), entry)
            checks += 1
    return checks


def check_ending(rig, levels, seed):
    checks = 0
    done = R.complete_byte(SENTINEL, -1)
    for level in ('endgood', 'endbad'):
        mem = prepare(rig, levels, level, seed)
        require(M.run_entry(rig, 'start') == (0, ''), level)
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'absorbExtra' and rig.calls == [], 'end post')
        require(held(mem), level)
        mem = prepare(rig, levels, level, seed)
        require(M.run_entry(rig, 'absorbExtra') == (0, ''), level)
        require(rig.calls == M.cut_calls(level), rig.calls)
        require(mem.cstr(N.N.G_POST_ACTION, 32) == 'bailFromGameWin', 'bail post')
        require(bytes_at(mem, 12) == [done] * 4 and held(mem, skip=(12,)), bytes_at(mem, 12))
        require(pending(mem) == 'PENDING-SENTINEL' and no_quest(mem), level)
        checks += 2
        for difficulty, bit in ((1, 0x08), (0, 0)):
            for card, saves in ((-1, True), (0, False)):
                mem = prepare(rig, levels, level, seed)
                mem.w32(N.N.G_DIFFICULTY, difficulty)
                if difficulty:
                    for slot in range(4):
                        base = PLAYERS + slot * REC + MISSION
                        mem.write(base + 13, bytes([SENTINEL]) * 13)
                rig.responder.card = card
                mem.w32(G_EXIT, 0x5A5A5A5A)
                mem.w8(G_COMPLETE, 0x5A)
                mem.w8(G_CONFIG, 0x41)
                mem.w32(G_MENU_OPEN, 0x5A5A5A5A)
                M.clear_defer(mem)
                require(M.run_entry(rig, 'bailFromGameWin') == (0, ''), 'bail 1')
                require(rig.calls == [('game_sendCharacterToLobby', (0xFFFFFFFF,)),
                                      ('memcard_requestConfigSave', ())], rig.calls)
                require(mem.u8(G_COMPLETE) == 1 and wrote(rig, G_COMPLETE, 1, 1), 'complete flag')
                require(mem.u32(M.G_PAUSED) == 1 and mem.u32(G_MENU_OPEN) == 1, 'paused')
                require(mem.u8(G_CONFIG) == 0x41 | bit, hex(mem.u8(G_CONFIG)))
                require(mem.u32(G_EXIT) == 0x5A5A5A5A and M.defer_name(mem) == 'bailFromGameWin', 'bail 1 exit')
                M.clear_defer(mem)
                M.run_entry(rig, 'bailFromGameWin')
                if saves:
                    require(rig.calls == [('memcard_getState', ()), ('net_getLocalPlayerSlot', (0,)),
                                          ('memcard_requestSave', (0,))], rig.calls)
                else:
                    require(rig.calls == [('memcard_getState', ())], rig.calls)
                require(mem.u32(G_EXIT) == 0x5A5A5A5A, 'bail 2 exit')
                M.clear_defer(mem)
                M.run_entry(rig, 'bailFromGameWin')
                require(rig.calls == [('memcard_getState', ())], rig.calls)
                require(mem.u32(G_EXIT) == (0x65 if saves else 0x5A5A5A5A), hex(mem.u32(G_EXIT)))
                if saves:
                    require(wrote(rig, G_EXIT, 4, 0x65), 'exit store')
                require(M.defer_name(mem) == 'bailFromGameWin', 'bail requeue')
                require(held(mem) and no_quest(mem), 'bail bytes')
                require(mem.u32(N.N.G_RAND_SEED) == seed, 'bail seed')
                # saveEndConfig paused the game; undo it so the next prepare sees the image.
                mem.w32(M.G_PAUSED, 0)
                checks += 1
    return checks


def check_frontend(elf, seed):
    """frontend_start 0x1e1f34 with every callee stubbed (returns 0)."""
    emu = EE(elf)
    mem = emu.mem
    results = {}
    for arg in (1, 0, 2):
        emu.follow = set()
        mem.w32(N.N.G_RAND_SEED, seed)
        mem.write(N.N.G_PENDING_LEVEL, b'PENDING-SENTINEL\0')
        mem.w32(FRONT_STATE, 0x5A5A5A5A)
        mem.w32(FRONT_MENU, 0x5A5A5A5A)
        mem.w8(FRONT_CREDITS, 0x5A)
        mem.w8(FRONT_SKIP, 0)
        emu.calls.clear()
        emu.writes.clear()
        emu.call(FRONTEND_START, arg, max_steps=200000)
        targets = [c.target for c in emu.calls]
        results[arg] = targets
        require(mem.cstr(N.N.G_PENDING_LEVEL, 32) == 'intro', 'intro')
        require(mem.u8(FRONT_CREDITS) == (1 if arg == 1 else 0), (arg, mem.u8(FRONT_CREDITS)))
        require(targets[-1] == (CREDITS_LOAD if arg == 1 else TASK_ADD), (arg, hex(targets[-1])))
        task = [c for c in emu.calls if c.target == TASK_ADD]
        require(len(task) == 1 and task[0].args[0] & 0xFFFFFFFF == FRONTEND_RUN
                and task[0].args[1] & 0xFFFFFFFF == 25, 'frontend task')
        if arg == 1:
            tail = emu.calls[-3:]
            require([c.target for c in tail] == [STREAM_CLEAR, MUSIC_GLOBAL, CREDITS_LOAD], 'credits order')
            require(tail[0].args[0] & 0xFFFFFFFF == 2 and tail[2].args[0] & 0xFFFFFFFF == 1, 'credit args')
            require(mem.cstr(tail[1].args[0] & 0xFFFFFFFF, 40) == 'mx_endcredits_ext_l.vag'
                    and tail[1].args[1] & 0xFFFFFFFF == 3, 'credits music')
            require(mem.u32(FRONT_STATE) == 15 and mem.u32(FRONT_MENU) == 0x4F6FB8, 'credits state')
        else:
            require(CREDITS_LOAD not in targets and MUSIC_GLOBAL not in targets, arg)
            require(mem.u32(FRONT_STATE) == 0, (arg, hex(mem.u32(FRONT_STATE))))
        require(mem.u32(N.N.G_RAND_SEED) == seed, 'front seed')
    return 3


def check_hub_offers(rig, levels, keys, seed):
    checks = 0
    for level in ('hub', 'hub2'):
        for entry, index in (('if3a40', 10), ('if2302', 11), ('ifb354', 12)):
            for byte in (0xA0, 0xA1, 0xA2, 0xA3):
                mem = prepare(rig, levels, level, seed)
                mem.w8(PLAYERS + MISSION + index, byte)
                got = M.run_entry(rig, entry)
                require(got == (0 if byte & 1 else 1, '') and rig.calls == [], (level, entry, hex(byte), got))
                checks += 1
    on = R.available_byte(SENTINEL, 1)
    store = ['dialog_isOpen', 'shop_openOrStock']
    actions = {
        'hub': (('setMissi4db8', 10, None, False), ('setMissi9964', 10, None, True),
                ('setMissi22ce', 10, 'Q10g', False), ('setMissi8ea7', 10, 'Q10g', True),
                ('setMissi6baa', 11, None, False), ('setMissi8b33', 11, None, True),
                ('setMissi3604', 11, 'Q11', False), ('setMissia052', 12, None, False),
                ('setMissi350c', 12, None, True), ('setMissib397', 12, None, True)),
        'hub2': (('setMissi4db8', 10, None, False), ('setMissi9964', 10, None, True),
                 ('setMissiec81', 10, 'Q10e', False), ('setMissi6baa', 11, None, False),
                 ('setMissi8b33', 11, None, True), ('setMissi3604', 11, 'Q11', False),
                 ('setMissi2732', 11, 'Q11', True), ('setMissia052', 12, None, False),
                 ('setMissi350c', 12, None, True), ('setMissib397', 12, None, True)),
    }
    for level, rows in actions.items():
        for entry, index, quest, shop in rows:
            mem = prepare(rig, levels, level, seed)
            require(M.run_entry(rig, entry) == (0, ''), (level, entry))
            require(bytes_at(mem, index) == [on] + [SENTINEL] * 3 and held(mem, skip=(index,)),
                    (level, entry, bytes_at(mem, index)))
            if quest:
                require(quest_is(mem, keys[quest + '.t'], keys[quest + '.b']), (level, entry))
            else:
                require(no_quest(mem), (level, entry))
            require(M.stubs(rig) == (store if shop else []), (level, entry, rig.calls))
            if shop:
                require(rig.calls[1] == ('shop_openOrStock', (0, 0, 1)), rig.calls)
            require(pending(mem) == 'PENDING-SENTINEL', entry)
            checks += 1
    return checks


# Every setMissionAvailable / grantMission site for missions 9..12 on the disc,
# by level, native and script offset (the raw immediate, not the census text).
CENSUS = {
    (9, 'setMissionAvailable'): {('valor', 0x730), ('storm1', 0x24C)},
    (9, 'grantMission'): {('storm2', 0xF70)},
    (10, 'setMissionAvailable'): {('fay1', 0x648), ('fay2', 0x620), ('hub', 0x1764), ('hub', 0x17B0),
                                  ('hub', 0x25D8), ('hub', 0x2658), ('hub2', 0x3B20), ('hub2', 0x3B6C),
                                  ('hub2', 0x46E4)},
    (10, 'grantMission'): {('fay3', 0xE8C)},
    (11, 'setMissionAvailable'): {('nit1', 0xBC), ('nitmar1', 0x78), ('hub', 0x19D0), ('hub', 0x1A1C),
                                  ('hub', 0x2730), ('hub2', 0x3D8C), ('hub2', 0x3DD8), ('hub2', 0x4764),
                                  ('hub2', 0x47E4)},
    (11, 'grantMission'): {('nit2', 0x8D8), ('nitmar1', 0x1C8)},
    (12, 'setMissionAvailable'): {('bossgood', 0x34), ('bossevil', 0x34), ('fearboss', 0x78),
                                  ('hub', 0x1C3C), ('hub', 0x1C88), ('hub', 0x27B0), ('hub2', 0x3FF8),
                                  ('hub2', 0x4044), ('hub2', 0x48BC)},
    (12, 'grantMission'): {('bossgood', 0xB3C), ('bossevil', 0xB3C), ('endgood', 0xDC),
                           ('endbad', 0xDC), ('fearboss', 0xF0)},
}


def raw_mission_calls(image):
    """(offset, native, first pushed immediate or None) for the two mission natives."""
    parsed = scr.parse(image)
    natives = [name for _, name in parsed['externals']]
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    found, pending, i = [], [], 0
    while i < len(words):
        op = words[i]
        if op == 0x7D:
            i += 3
            continue
        if op == 0x7B:
            name = natives[words[i + 1]]
            if name in ('setMissionAvailable', 'grantMission'):
                raw = pending[:-1][::-1]
                found.append((i * 4, name, raw[0] if raw else None))
            pending = []
            i += 2
            continue
        if op == 0x27:
            pending.append(words[i + 1])
            i += 2
            continue
        if op in (0x28, 0x24, 0x25):
            pending.append(None)
            i += 1 if op != 0x28 else 2
            continue
        if op == 0x2C:
            pending = []
            i += 2
            continue
        pending = []
        if op in scr.OPS:
            i += 1 + scr.OPS[op][1]
        else:
            i += 1 if op in scr.NO_OPERAND else 2
    return found


def check_census(data):
    got = {key: set() for key in CENSUS}
    files = 0
    for name in sorted(os.listdir(data)):
        if not name.upper().endswith('.GOB'):
            continue
        try:
            image = M.lump_map(os.path.join(data, name))['script.scr']
        except AssertionError:
            continue
        files += 1
        for off, native, first in raw_mission_calls(image):
            require(first is not None, (name, hex(off), native))
            if 9 <= first <= 12:
                got[(first, native)].add((name[:-4].lower(), off))
    require(files > 100, files)
    for key, sites in CENSUS.items():
        require(got[key] == sites, (key, sorted(got[key] ^ sites)))
    return len(CENSUS)


def check_seed(rig, levels, keys, elf, seed):
    checks = check_sites(levels) + check_links(levels)
    checks += check_m9_offer(rig, levels, keys, seed)
    checks += check_storm1(rig, levels, keys, seed)
    checks += check_travel(rig, levels, seed)
    checks += check_storm4(rig, levels, keys, seed)
    checks += check_storm2(rig, levels, keys, seed)
    checks += check_fay(rig, levels, keys, seed)
    checks += check_nit(rig, levels, keys, seed)
    checks += check_boss(rig, levels, keys, seed)
    checks += check_ending(rig, levels, seed)
    checks += check_hub_offers(rig, levels, keys, seed)
    checks += check_frontend(elf, seed)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--seed', type=int, action='append', dest='seeds')
    parser.add_argument('--keys-out', help='write neutral id -> disc key (untracked path only)')
    args = parser.parse_args()
    blob = open(args.elf, 'rb').read()
    if hashlib.sha256(blob).hexdigest() != ELF_SHA256:
        raise SystemExit('unexpected executable')
    levels = load_levels(args.data)
    keys = read_keys(levels)
    if args.keys_out:
        with open(args.keys_out, 'w') as out:
            for ident in sorted(keys):
                out.write('%s\t%s\n' % (ident, keys[ident]))
    for seed in (args.seeds or [20973, 7]):
        rig = N.Rig(args.elf)
        rig.checkpoint()
        rig.responder = Answers()
        count = check_seed(rig, levels, keys, args.elf, seed) + check_census(args.data)
        print('PASS seed %d: %d mission-9..12 and ending checks' % (seed, count))


if __name__ == '__main__':
    main()
