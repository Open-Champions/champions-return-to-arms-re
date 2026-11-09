#!/usr/bin/env python3
"""Round 12: the arena acceptance boundary.  Runs original SLUS_209.73 bodies in
tools/ee_emu.py and compares them with tools/ref_arena_acceptance.py.

    python3 tools/difftest_arena_acceptance.py local/SLUS_209.73 --seed 20973
    python3 tools/difftest_arena_acceptance.py local/SLUS_209.73 --seed 7

Cases (docs/spec/arena-acceptance.md):
  setup     frontend_run 0x1e08f0 entered at its state dispatch 0x1e15c0 for the
            player-count, game-mode and kill-limit states; the net launch block copy
            0x137464-0x137554; the character-import team byte 0x220644-0x220680.
  init      arena_init 0x304c4c whole: fresh and continuing branches, record snapshot,
            gold clear, task registration, and player_removeAllItems 0x1bf600 with the
            real inventory_removeItem 0x1c1cb0 under the scramble word.
  results   arena_drawPrompt 0x3075dc whole: header choice and every ranked row.
  overflow  arena_startWave 0x305ed4 across the signed halfword wrap, and the
            level request of arena_runTask 0x306b78 at those waves.
  knockback Creature_applyKnockback 0x115eb8 player gate.

Stubs are recorded and listed per case; nothing is a default success.  Private
strings and table bytes are read at run time and never printed: the log shows
addresses, counts and hashes only.  A missing executable or a different build
exits 2.
"""
import hashlib
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE]
sys.path.append(_HERE)

from ee_emu import EE, EmuError                        # noqa: E402
import ref_arena_modes as A                            # noqa: E402
import ref_arena_acceptance as R                       # noqa: E402
from ref_core import ONE, TWO, from_int, s16           # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'

# functions
DISPATCH = 0x1E15C0
H_PLAYERS, H_MODE, H_LIMIT = 0x1E1888, 0x1E18E8, 0x1E19D8
FE_STOPS = (0x1E1CAC, 0x1E1CB0)
JUMPS = 0x53D050
STRSTR = 0x3B96A8
PSELECT = 0x1E3BA0
LAUNCH, LAUNCH_STOPS = 0x137464, (0x137518, 0x137554)
SET7110 = 0x1EC830
SCAN = 0x1EB950
TEAM_IN, TEAM_OUT = 0x220644, 0x220680
INIT = 0x304C4C
TASK_ADD = 0x19E4A0
ALLOC = 0x14FF88
LUMP = 0x173558
RES = 0x17365C
REMOVE_ALL = 0x1BF600
REMOVE = 0x1C1CB0
RECALC, IDLE, LOCAL = 0x1B6458, 0x1B2470, 0x13E150
DRAW = 0x3075DC
LOOKUP, WFMT = 0x173C84, 0x19EA78
T_BEGIN, T_END, T_COLOUR = 0x1800B8, 0x180500, 0x1802E0
T_WIDE, T_ASCII = 0x181CA0, 0x181AA0
FIT, SLOTCOL = 0x1BDF60, 0x1BF2A0
START, STEP, SPAWN = 0x305ED4, 0x3065B0, 0x3065FC
NET_COUNT = 0x1EC878
RUN, STRCPY, END, NEXT = 0x306B78, 0x3B868C, 0x307EBC, 0x305E9C
KNOCK, MOVEBY = 0x115EB8, 0x113C48

# data
FSTATE, FMENU = 0x4F6B78, 0x4F6B7C
NEEDLE_A, NEEDLE_S, NEEDLE_B = 0x53D008, 0x53D010, 0x53D020
MODE_A, MODE_B, SCRAMBLE = 0x4F711C, 0x4F7120, 0x4F7124
NUM, PLAYERS, REC = 0x4D8AE0, 0x4D8AF0, 0x4C30
DIFF, LIMIT, NETFLAG = 0x4F719C, 0x4F8408, 0x4F70A0
BLOCK, W7110 = 0x402B90, 0x4F7110
SLOTBYTE = 0x4F923C
SEED, NET = 0x404464, 0x402791
PREV = 0x41B7C2
ENDF, WAVE, LEFT, INTER, INTRO = 0x503894, 0x8E7338, 0x8E733A, 0x8E733C, 0x5038C8
INDEX, SAVED, BUDGET, W7354 = 0x8E7343, 0x8E7340, 0x8E7358, 0x8E7354
SPAWN_P, MONS_P, SPAWN_N = 0x503888, 0x50388C, 0x8E7342
FONT_A, FONT_B = 0x8E734C, 0x8E7350
MINIMAP = 0x4F8400
SAVECOPY = 0x879EC0
SCORE = 0x503898
NAMES_A, NAMES_B, RECIPES, NREC, CLASSES = 0x5037B8, 0x503798, 0x503868, 0x503886, 0x5037F0
RANK_B, FADE_W, FIT_BUF = 0x8E7348, 0x8E735C, 0x4F3EC8
LEVEL, WORD890 = 0x4F714C, 0x503890
PAUSED, FRONT, MENU_OPEN, FRAME = 0x41B4F4, 0x41B510, 0x41B69D, 0x44FDCC
GOLD, EXP = 0xE4, 0x5C
BAGS, BAG, COUNT, ITEM = 0x130, 0x1208, 0x1200, 0x48
SENT = 0x5A5A5A5A

RESULTS = []
PATH = None
SEED_VALUE = 20973


def check(name, got, want):
    ok = got == want
    RESULTS.append((name, ok))
    if not ok:
        print('FAIL  %s\n      got  %r\n      want %r' % (name, got, want))
    return ok


def note(text):
    print('      ' + text)


def boot():
    emu = EE(PATH)
    emu.record_calls = True
    emu.mem.w32(SEED, SEED_VALUE & 0xFFFFFFFF)
    return emu


def cstr(emu, addr):
    return emu.mem.cstr(addr, 64)


def calls(emu, target):
    return [c for c in emu.calls if c.target == target]


def hide(data):
    return hashlib.sha256(data).hexdigest()[:8]


def table(emu, addr, limit=20):
    out = []
    for i in range(limit):
        p = emu.mem.u32(addr + 4 * i)
        if p == 0:
            break
        out.append(p)
    return out


def run_fragment(emu, start, stops, max_steps=2000000):
    emu.r[31] = EE.RETURN_ADDR
    emu.jump(start)
    return emu.run(until=stops, max_steps=max_steps)


# ---------------------------------------------------------------------------- setup ----
def case_setup():
    probe = boot()
    jt = [probe.mem.u32(JUMPS + 4 * i) for i in range(13)]
    check('dispatch: player-count state 2', jt[2], H_PLAYERS)
    check('dispatch: game-mode state 4', jt[4], H_MODE)
    check('dispatch: kill-limit state 5', jt[5], H_LIMIT)
    needles = [probe.mem.read(a, 16).split(b'\0')[0] for a in (NEEDLE_A, NEEDLE_S, NEEDLE_B)]
    note('front-end substrings: %s' % ' '.join(hide(n) for n in needles))

    def frontend(state, menu, index, players, ids=None):
        emu = boot()
        emu.mem.w32(FSTATE, state)
        emu.mem.w32(FMENU, menu)
        emu.mem.w32(NUM, players)
        for word in (MODE_A, MODE_B, SCRAMBLE, DIFF):
            emu.mem.w32(word, SENT)
        emu.mem.w8(LIMIT, 0x77)
        emu.mem.w32(NETFLAG, 0)
        if ids is not None:                       # synthetic menu built from runtime bytes
            text = emu.alloc(64)
            emu.mem.write(text, ids + b'\0')
            menu = emu.alloc(32)
            emu.mem.w32(menu, text)
            emu.mem.w32(FMENU, menu)
        sp = emu.r[29] - 0x400
        emu.r[29] = sp
        emu.mem.w32(sp + 0xC8, 0)
        emu.r[16] = FSTATE
        emu.r[21] = 0x4F0000
        emu.r[20] = index & 0xFFFFFFFFFFFFFFFF
        emu.follow = {STRSTR}
        emu.stub(PSELECT, ret=0, name='frontend_startPlayerSelect')
        seen = []
        for h in (H_PLAYERS, H_MODE, H_LIMIT):
            emu.hook(h, lambda e, h=h: seen.append(h))
        reason = run_fragment(emu, DISPATCH, FE_STOPS)
        return emu, reason, seen

    for index in range(-1, 5):
        emu, reason, seen = frontend(2, 0, index, 3)
        players, state, menu = R.players_choice(index)
        check('players %d: stopped at merge' % index, (reason, seen), ('stop', [H_PLAYERS]))
        check('players %d: words' % index,
              (emu.mem.u32(NUM), emu.mem.u32(FSTATE), emu.mem.u32(FMENU)),
              (players if players else 3, state if state else 2, menu if menu else 0))
        check('players %d: modes cleared' % index,
              (emu.mem.u32(MODE_A), emu.mem.u32(MODE_B), emu.mem.u32(SCRAMBLE)), (0, 0, 0))

    def mode_case(label, menu, index, players, ids=None):
        emu, reason, seen = frontend(4, menu, index, players, ids)
        if ids is None:
            entry = probe.mem.u32(menu + 16 * index)
            ids_used = probe.mem.read(entry, 32).split(b'\0')[0]
        else:
            ids_used = ids
        want = R.mode_choice(ids_used, needles[0], needles[1], needles[2], players)
        check('mode %s: stopped' % label, (reason, seen), ('stop', [H_MODE]))
        got = {'mode_a': emu.mem.u32(MODE_A), 'scramble': emu.mem.u32(SCRAMBLE),
               'mode_b': emu.mem.u32(MODE_B), 'players': emu.mem.u32(NUM),
               'state': emu.mem.u32(FSTATE), 'menu': emu.mem.u32(FMENU),
               'difficulty': emu.mem.u32(DIFF), 'player_select': len(calls(emu, PSELECT))}
        if want['state'] is None:
            want['state'], want['menu'] = 4, emu.mem.u32(FMENU) if ids is not None else menu
        if want['difficulty'] is None:
            want['difficulty'] = SENT
        check('mode %s: words' % label, got, want)
        return got

    rows = []
    rows.append(('solo/0', mode_case('solo/0', R.MENU_MODE_SOLO, 0, 1)))
    rows.append(('solo/1', mode_case('solo/1', R.MENU_MODE_SOLO, 1, 1)))
    for i in range(3):
        rows.append(('multi/%d' % i, mode_case('multi/%d' % i, R.MENU_MODE_MULTI, i, 3)))
    rows.append(('synthetic scramble id', mode_case('synthetic scramble', 0, 0, 3,
                                                    ids=b'x' + needles[1] + b'x')))
    for label, got in rows:
        note('%-22s A=%d B=%d scramble=%d players=%d state=%d select=%d' % (
            label, got['mode_a'], got['mode_b'], got['scramble'], got['players'],
            got['state'], got['player_select']))

    for index in range(4):
        emu, reason, seen = frontend(5, R.MENU_KILL_LIMIT, index, 2)
        check('kill limit %d' % index, (reason, seen, emu.mem.u8(LIMIT), len(calls(emu, PSELECT))),
              ('stop', [H_LIMIT], R.kill_limit_offline(index), 1))

    # net launch
    for mode in range(5):
        for arg in (0xFFFFFFFF, 7):
            emu = boot()
            for word in (MODE_A, MODE_B, SCRAMBLE, DIFF, W7110):
                emu.mem.w32(word, SENT)
            emu.mem.w8(BLOCK + 0xA0, 0xFE)
            emu.mem.w8(BLOCK + 0xA1, mode)
            emu.mem.w8(BLOCK + 0xA2, 25)
            emu.mem.w32(BLOCK + 0xF4, arg)
            emu.follow = {SET7110}
            emu.stub(SCAN, ret=6, name='game_scanCm1Vars')
            reason = run_fragment(emu, LAUNCH, LAUNCH_STOPS)
            want = R.net_launch(mode, 0xFE, 25, arg, 6)
            got = {'mode_a': emu.mem.u32(MODE_A), 'mode_b': emu.mem.u32(MODE_B),
                   'scramble': emu.mem.u32(SCRAMBLE), 'difficulty': emu.mem.u32(DIFF),
                   'limit': emu.mem.u8(LIMIT),
                   'w7110': emu.mem.u32(W7110) if want['w7110'] is not None else None}
            check('net launch mode %d arg %x' % (mode, arg), (reason, got), ('stop', want))
            if want['w7110'] is None:
                check('net launch mode %d leaves 0x4f7110' % mode, emu.mem.u32(W7110), SENT)
            scans = [c.args[0] & 0xFF for c in calls(emu, SCAN)]
            check('net launch mode %d scan calls' % mode, scans,
                  [1] if want['mode_a'] and arg == 0xFFFFFFFF else [])

    # character import team byte
    for mode_a in (0, 1):
        for slot in range(4):
            emu = boot()
            emu.mem.w32(MODE_A, mode_a)
            emu.mem.w8(SLOTBYTE, slot)
            for s in range(4):
                emu.mem.w8(PLAYERS + s * REC + 0x4C24, 0x77)
            emu.r[16], emu.r[17], emu.r[18] = PLAYERS, REC, SLOTBYTE
            emu.follow = set()
            reason = run_fragment(emu, TEAM_IN, (TEAM_OUT,))
            others = [emu.mem.u8(PLAYERS + s * REC + 0x4C24) for s in range(4) if s != slot]
            check('import team A=%d slot %d' % (mode_a, slot),
                  (reason, emu.mem.u8(PLAYERS + slot * REC + 0x4C24), others, emu.calls),
                  ('stop', R.import_team(mode_a, slot), [0x77] * 3, []))


# ----------------------------------------------------------------------------- init ----
class Cell(object):
    def __init__(self, tag):
        self.tag = tag


def plant(emu, slot, bag, index, tag):
    rec = PLAYERS + slot * REC
    base = rec + BAGS + bag * BAG
    text = emu.alloc(16)
    emu.mem.write(text, tag.encode('ascii') + b'\0')
    defin = emu.alloc(64)
    emu.mem.w32(defin, text)
    emu.mem.w8(defin + 0x1C, 0xFF)
    emu.mem.w8(defin + 0x1D, bag)
    addr = base + index * ITEM
    emu.mem.w32(addr, defin)
    emu.mem.w16(addr + 4, 1)
    emu.mem.w32(base + COUNT, index + 1)


def read_bags(emu, slot):
    rec = PLAYERS + slot * REC
    out = []
    for bag in range(3):
        base = rec + BAGS + bag * BAG
        n = emu.mem.s32(base + COUNT)
        cells = []
        for i in range(max(0, n)):
            defin = emu.mem.u32(base + i * ITEM)
            cells.append(cstr(emu, emu.mem.u32(defin)) if defin else '')
        out.append(cells)
    return out


def case_init():
    probe = boot()
    names_a = [cstr(probe, p).encode('latin-1') for p in table(probe, NAMES_A)]
    names_b = [cstr(probe, p).encode('latin-1') for p in table(probe, NAMES_B)]
    check('init: level tables', (len(names_a), len(names_b)), (13, 7))
    byte_e80 = probe.mem.u8(0x551E80)

    fixture = {0: [['a0', 'a1', 'a2'], ['b0', 'b1'], ['c0']],
               1: [['d0'], [], ['e0', 'e1']],
               2: [['f0', 'f1'], ['g0'], []],
               3: [[], [], ['h0']]}

    def run(label, players, mode_a, scramble, prev, end, network=0):
        emu = boot()
        emu.mem.w32(MODE_A, mode_a)
        emu.mem.w32(MODE_B, 1)
        emu.mem.w32(SCRAMBLE, scramble)
        emu.mem.w32(NUM, players)
        emu.mem.w8(NET, network)
        emu.mem.w32(ENDF, end)
        emu.mem.write(PREV, prev + b'\0')
        emu.mem.write(PLAYERS, bytes(4 * REC))
        emu.mem.write(SAVECOPY, b'\xee' * (4 * REC))
        for slot in range(4):
            rec = PLAYERS + slot * REC
            emu.mem.write(rec, ('P%d' % slot).encode('ascii') + b'\0')
            emu.mem.w32(rec + GOLD, 1000 + 7 * slot)
            emu.mem.w32(rec + EXP, 500 + slot)
            emu.mem.write(rec + 0x4000, bytes((slot * 16 + i) & 0xFF for i in range(16)))
            for bag in range(3):
                for i, tag in enumerate(fixture[slot][bag]):
                    plant(emu, slot, bag, i, tag)
        pre = [bytes(emu.mem.read(PLAYERS + s * REC, REC)) for s in range(4)]
        # state a continuing match would carry
        emu.mem.w16(WAVE, 5)
        emu.mem.w8(INDEX, 0x44)
        old_table = emu.alloc(0x320, fill=0x77)
        emu.mem.w32(SPAWN_P, old_table)
        emu.mem.w32(MONS_P, 0x1234)
        emu.mem.w8(SPAWN_N, 9)
        emu.mem.w32(BUDGET, 800)
        emu.mem.w32(MINIMAP, SENT)
        for s in range(4):
            emu.mem.write(SCORE + 12 * s, bytes([3, 0, 1, 0, 1, 0, 0, 0]) + (0).to_bytes(4, 'little'))
        allocs = []

        def alloc(e):
            block = e.alloc(e.r[4] & 0xFFFFFFFF, fill=0x33)
            allocs.append((e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF, block))
            return block

        res_ret = [emu.alloc(16), emu.alloc(16)]
        lump_ret = emu.alloc(16)
        emu.stub(SCAN, ret=3, name='game_scanCm1Vars')
        emu.stub(TASK_ADD, ret=1, name='task_add')
        emu.stub(ALLOC, function=alloc, name='alloc')
        emu.stub(LUMP, ret=lump_ret, name='lump_load')
        emu.stub(RES, function=lambda e: res_ret[len(calls(e, RES)) - 1], name='res_find')
        emu.stub(RECALC, name='recalc')
        emu.stub(IDLE, name='idle')
        emu.stub(LOCAL, ret=0, name='local')
        emu.call(INIT)
        fresh = R.arena_init_fresh(prev, mode_a, end, names_a, names_b)
        got_fresh = len(calls(emu, TASK_ADD)) > 0
        check('%s: branch' % label, got_fresh, fresh)
        live = [bytes(emu.mem.read(PLAYERS + s * REC, REC)) for s in range(4)]
        saved = [bytes(emu.mem.read(SAVECOPY + s * REC, REC)) for s in range(4)]
        if fresh:
            check('%s: snapshot of every active record' % label,
                  [saved[s] == pre[s] for s in range(4)], [s < players for s in range(4)])
            check('%s: untouched save copies stay' % label,
                  [saved[s] == b'\xee' * REC for s in range(players, 4)], [True] * (4 - players))
            check('%s: live gold cleared for active slots' % label,
                  [emu.mem.u32(PLAYERS + s * REC + GOLD) for s in range(4)],
                  [0 if s < players else 1000 + 7 * s for s in range(4)])
            check('%s: experience kept' % label,
                  [emu.mem.u32(PLAYERS + s * REC + EXP) for s in range(4)], [500 + s for s in range(4)])
            check('%s: wave -1, index, end flag' % label,
                  (s16(emu.mem.u16(WAVE)), emu.mem.u8(INDEX), emu.mem.u32(ENDF)), (-1, 3, 0))
            check('%s: scores reset' % label,
                  [(emu.mem.u16(SCORE + 12 * s + 2), emu.mem.u32(SCORE + 12 * s + 8)) for s in range(4)],
                  [(2, TWO) if s < players else (0, 0) for s in range(4)])
            tasks = [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF, c.args[2] & 0xFFFFFFFF,
                      c.args[3] & 0xFFFFFFFF) for c in calls(emu, TASK_ADD)]
            check('%s: tasks' % label, tasks, [(0x306B78, 100, 0x551E48, 0), (0x307284, 100, 0x551E50, 1)])
            check('%s: tables allocated' % label, [(a[0], a[1]) for a in allocs],
                  [(0x320, 0x551E60), (0x4B0, 0x551E70)])
            check('%s: table pointers' % label, (emu.mem.u32(SPAWN_P), emu.mem.u32(MONS_P)),
                  (allocs[0][2], allocs[1][2]))
            check('%s: budget, 0x8e7354, 0x8e7230' % label,
                  (emu.mem.u32(BUDGET), emu.mem.u32(W7354), emu.mem.u8(0x8E7238),
                   emu.mem.u32(0x8E7230), emu.mem.u32(0x8E7234)),
                  (100, 0x80000000, byte_e80, 0x8E7238, 0))
            check('%s: minimap mode' % label, emu.mem.u32(MINIMAP), R.minimap_mode(scramble))
            want_bags = []
            want_calls = []
            for s in range(4):
                bags = [list(b) for b in fixture[s]]
                if scramble and s < players:
                    want_calls += [(s, i, b) for i, b in R.remove_all(bags)]
                want_bags.append(bags)
            got_calls = [(c.args[0] & 0xFF, c.args[1] & 0xFF, c.args[2] & 0xFF)
                         for c in calls(emu, REMOVE)]
            check('%s: removeAllItems slots' % label, [c.args[0] & 0xFF for c in calls(emu, REMOVE_ALL)],
                  list(range(players)) if scramble else [])
            check('%s: inventory_removeItem calls' % label, got_calls, want_calls)
            check('%s: bags after init' % label, [read_bags(emu, s) for s in range(4)], want_bags)
            if scramble:
                check('%s: saved copy keeps the bags' % label,
                      all(saved[s] == pre[s] for s in range(players)), True)
        else:
            check('%s: records untouched' % label, live, pre)
            check('%s: save copies untouched' % label, saved, [b'\xee' * REC] * 4)
            check('%s: match state kept' % label,
                  (s16(emu.mem.u16(WAVE)), emu.mem.u8(INDEX), emu.mem.u32(BUDGET),
                   emu.mem.u32(MINIMAP), emu.mem.u32(MONS_P),
                   [emu.mem.u16(SCORE + 12 * s + 2) for s in range(4)]),
                  (5, 0x44, 800, SENT, 0x1234, [1] * 4))
            check('%s: no tasks, allocations, removals' % label,
                  (calls(emu, TASK_ADD), allocs, calls(emu, REMOVE_ALL)), ([], [], []))
            check('%s: spawn table kept' % label, emu.mem.u32(SPAWN_P), old_table)
        table_p = emu.mem.u32(SPAWN_P)
        check('%s: spawn entry 0 and count' % label,
              ([emu.mem.u32(table_p + 4 * i) for i in range(3)], emu.mem.u16(table_p + 12),
               emu.mem.u8(SPAWN_N)), ([0, 0, 0], 0, 1))
        check('%s: resources' % label,
              ([c.args[0] & 0xFFFFFFFF for c in calls(emu, LUMP)],
               [(c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF) for c in calls(emu, RES)],
               emu.mem.u32(FONT_A), emu.mem.u32(FONT_B)),
              ([0x551E88], [(0x551E98, 0x551EA8), (0x551E98, 0x551EB8)], res_ret[0], res_ret[1]))
        check('%s: shared seed unchanged' % label, emu.mem.u32(SEED), SEED_VALUE & 0xFFFFFFFF)
        note('%-30s fresh=%d removeAll=%d removeItem=%d minimap=%#x' % (
            label, got_fresh, len(calls(emu, REMOVE_ALL)), len(calls(emu, REMOVE)),
            emu.mem.u32(MINIMAP)))

    other = b'zz' + names_b[0][:6]
    for players in (1, 2, 4):
        run('co-op entry, %d players' % players, players, 0, 0, other, 0)
    run('co-op entry, scramble, 4', 4, 0, 1, other, 0)
    run('co-op entry, scramble, 2', 2, 0, 1, other, 0)
    run('scramble entry online', 2, 1, 1, other, 0, network=1)
    for k in (0, 6):
        run('co-op level change B[%d]' % k, 2, 0, 0, names_b[k], 0)
        run('co-op restart B[%d] end=1' % k, 2, 0, 0, names_b[k], 1)
    run('co-op, prev level only in A', 2, 0, 0,
        next(n for n in names_a if n not in names_b), 0)
    run('versus level change A[3]', 3, 1, 0, names_a[3], 0)
    run('versus, scramble, level change', 3, 1, 1, names_a[5], 0)
    only_b = [n for n in names_b if n not in names_a]
    check('init: every table-B name is also in table A', only_b, [])
    run('versus entry from a co-op level', 3, 1, 0, names_b[1], 1)


# -------------------------------------------------------------------------- results ----
def case_results():
    for mode_a, end, players, wave, kills, rank in (
            (0, 1, 1, 0, [3, 0, 0, 0], [0, 1, 2, 3]),
            (0, 1, 2, 4, [7, 12, 0, 0], [1, 0, 2, 3]),
            (0, 0, 2, 2, [5, 1, 0, 0], [0, 1, 2, 3]),
            (0, 1, 4, 0x7FFF, [1, 0xFFFF, 9, 2], [2, 3, 0, 1]),
            (0, 1, 3, 0x8000, [0, 4, 2, 0], [1, 2, 0, 3]),
            (1, 1, 4, 3, [10, 3, 5, 1], [0, 2, 1, 3]),
            (1, 0, 2, 0, [2, 5, 0, 0], [1, 0, 2, 3])):
        emu = boot()
        emu.mem.w32(MODE_A, mode_a)
        emu.mem.w32(MODE_B, 1)
        emu.mem.w32(NUM, players)
        emu.mem.w32(ENDF, end)
        emu.mem.w16(WAVE, wave)
        emu.mem.w32(FADE_W, 0x3F000000)
        for word in (FONT_A, FONT_B, W7354):
            emu.mem.w32(word, emu.alloc(16))
        names = []
        for s in range(4):
            name = 'Q%dz' % s
            names.append(name)
            emu.mem.write(PLAYERS + s * REC, name.encode('ascii') + b'\0')
            emu.mem.w16(SCORE + 12 * s, kills[s])
            emu.mem.w8(RANK_B + s, rank[s])
        keys = []
        wide = {}

        def lookup(e):
            keys.append(e.r[4] & 0xFFFFFFFF)
            block = e.alloc(16)
            wide[block] = e.r[4] & 0xFFFFFFFF
            return block

        def fit(e):
            slot = e.r[5] & 0xFF
            src = cstr(e, e.r[6] & 0xFFFFFFFF)
            e.mem.write(FIT_BUF + 32 * slot, src.encode('ascii')[:31] + b'\0')
            return FIT_BUF + 32 * slot

        ascii_draws = []

        def draw_ascii(e):
            ascii_draws.append((e.r[4] & 0xFFFFFFFF, cstr(e, e.r[6] & 0xFFFFFFFF)))

        emu.stub(LOOKUP, function=lookup, name='text_lookup')
        emu.stub(WFMT, ret=0, name='wstr_format')
        for addr, nm in ((T_BEGIN, 'text_begin'), (T_END, 'text_end'), (T_COLOUR, 'text_colour'),
                         (T_WIDE, 'text_drawWideCentered')):
            emu.stub(addr, ret=0, name=nm)
        emu.stub(T_ASCII, function=draw_ascii, name='text_drawAscii')
        emu.stub(FIT, function=fit, name='ui_fitText')
        emu.stub(SLOTCOL, ret=0x80FFFFFF, name='player_slotColor')
        emu.call(DRAW)
        label = 'results A=%d end=%d n=%d wave=%#x' % (mode_a, end, players, wave)
        check(label + ': rows', ascii_draws, R.result_rows(rank, kills, names, players))
        kind, value = R.result_header(mode_a, end, wave)
        header_key = {'winner': 0x551F60, 'defeat': 0x551F70, 'interval': 0x551F80}[kind]
        fmt = calls(emu, WFMT)
        check(label + ': header key', (keys[0], len(fmt)), (header_key, 1))
        if kind == 'winner':
            value = from_int(FIT_BUF + 32 * rank[0])
            check(label + ': winner fitted first', (calls(emu, FIT)[0].args[1] & 0xFF), rank[0])
        check(label + ': header figure', fmt[0].fargs[0] & 0xFFFFFFFF, value)
        check(label + ': header format is the looked-up key', wide.get(fmt[0].args[1] & 0xFFFFFFFF), header_key)
        check(label + ': column label twice', keys[1:], [0x551F90, 0x551F90])
        check(label + ': slot colours', [c.args[0] & 0xFF for c in calls(emu, SLOTCOL)],
              [rank[i] for i in range(players)] if players >= 2 else [])
        check(label + ': fade step', emu.mem.u32(FADE_W), A.fade_step(0x3F000000))
        writes = sorted(set(a for pc, a, _n, _v in emu.writes if DRAW <= pc < 0x307BBC))
        check(label + ': the page body stores only the fade', writes, [FADE_W])
        note('%-34s keys=%d rows=%d figure=%#010x' % (label, len(keys), len(ascii_draws) // 6,
                                                       fmt[0].fargs[0] & 0xFFFFFFFF))


# ------------------------------------------------------------------------- overflow ----
def case_overflow():
    probe = boot()
    nrec = probe.mem.u16(NREC)
    classes = [probe.mem.u32(CLASSES + 4 * i) for i in range(256)]
    names_b_ptr = NAMES_B

    def byte_at(addr):
        return probe.mem.u8(addr)

    for prev in (0x7FFD, 0x7FFE, 0x7FFF, 0x8000, 0x8001, 0x8002, 0x8003, 0x8004):
        for active in (1, 4):
            emu = boot()
            emu.mem.w32(MODE_A, 0)
            emu.mem.w32(MODE_B, 1)
            emu.mem.w32(NUM, 0)
            emu.mem.w16(WAVE, prev)
            emu.mem.w16(LEFT, 3)
            emu.mem.w16(SAVED, 0)
            emu.mem.w32(0x4F8450, 0)
            emu.follow = {STEP}
            emu.stub(NET_COUNT, ret=active)
            emu.stub(SPAWN, ret=0)
            for addr in (0x203210, 0x1EB000, 0x1EC2B8):
                emu.stub(addr, ret=0)
            wave = R.overflow_wave(prev)
            label = 'overflow %#06x->%#06x active %d' % (prev, wave, active)
            try:
                want_classes, want_seed, steps, index = R.overflow_plan(
                    s16(wave), active, nrec, byte_at, RECIPES, SEED_VALUE & 0xFFFFFFFF)
            except ZeroDivisionError:
                note(label + ': model divides by zero; skipped')
                continue
            emu.call(START, 1)
            got = [c.args[0] & 0xFFFFFFFF for c in calls(emu, SPAWN)]
            check(label + ': wave halfword', emu.mem.u16(WAVE), wave)
            check(label + ': spawns', got, [classes[c & 0xFF] for c in want_classes])
            check(label + ': ring steps', [c.args[0] & 0xFFFFFFFF for c in calls(emu, STEP)],
                  [n & 0xFFFFFFFF for n, _a, _d in steps])
            check(label + ': seed', emu.mem.u32(SEED), want_seed)
            check(label + ': monster level', emu.mem.u32(LEVEL), A.monster_level(wave))
            check(label + ': intro and lock', (emu.mem.u16(INTRO), emu.mem.u32(WORD890)), (A.INTRO_FRAMES, 1))
            note('%-36s record %+d spawns %d steps %d level %#010x' % (
                label, index, len(got), len(steps), emu.mem.u32(LEVEL)))

    # The level request at those waves (waves-left 0, intermission expiring offline).
    for wave in (0x7FFE, 0x7FFF, 0x8000, 0x8001, 0x8002, 0x8003, 0xFFFE, 0xFFFF):
        emu = boot()
        emu.mem.w32(MODE_A, 0)
        emu.mem.w32(MODE_B, 1)
        emu.mem.w8(NET, 0)
        emu.mem.w32(NUM, 1)
        for addr, value in ((PAUSED, 0), (FRONT, 0)):
            emu.mem.w32(addr, value)
        emu.mem.w8(MENU_OPEN, 0)
        emu.mem.w16(INTRO, 0xFFFF)
        emu.mem.w16(INTER, A.INTERMISSION_OFFLINE)
        emu.mem.w32(ENDF, 0)
        emu.mem.w32(FRAME, 1)
        emu.mem.w16(WAVE, wave)
        emu.mem.w16(LEFT, 0)
        emu.mem.w16(SCORE + 2, 2)
        emu.mem.w32(PLAYERS + 0xAC, from_int(10))
        emu.follow = {0x307F68}
        emu.stub(0x13DD40, ret=1)
        for addr in (END, NEXT, SCAN, STRCPY, 0x1EB000, 0x304FB0, 0x13E5A0, 0x17365C,
                     0x2134E8, 0x14A610):
            emu.stub(addr, ret=0)
        emu.call(RUN)
        rec = R.A.level_record_index(wave, nrec)
        nib = A.low_nibble(byte_at(RECIPES + 6 * rec))
        want_ptr = probe.mem.u32(names_b_ptr + 4 * nib)
        got = calls(emu, STRCPY)
        label = 'level request at wave %#06x' % wave
        check(label + ': one copy', len(got), 1)
        if got:
            check(label + ': source pointer', got[0].args[1] & 0xFFFFFFFF, want_ptr)
        check(label + ': mode B kept, no end', (emu.mem.u32(MODE_B), emu.mem.u32(ENDF), len(calls(emu, END))),
              (1, 0, 0))
        inside = want_ptr in table(probe, NAMES_B)
        note('%-30s record %+d name index %+d in table B: %s' % (label, rec, nib, inside))


# ------------------------------------------------------------------------ knockback ----
def case_knockback():
    for flags in (0x40, 0x60, 0x20):
        for network in (0, 1):
            for mode_b in (0, 1):
                for mode_a in (0, 1):
                    emu = boot()
                    emu.mem.w32(MODE_A, mode_a)
                    emu.mem.w32(MODE_B, mode_b)
                    emu.mem.w8(NET, network)
                    obj = emu.alloc(0x400)
                    emu.mem.w32(obj + 0xC, flags)
                    emu.mem.w32(obj + 0x2E8, from_int(150))
                    emu.mem.w16(obj + 0x2E0, 0x2000)
                    moved = []

                    def move(e):
                        moved.append([e.mem.u32((e.r[5] & 0xFFFFFFFF) + 4 * i) for i in range(2)])
                        return 1                    # a nonzero result skips the dust tail

                    emu.follow = {0x166630, 0x1666E0}
                    emu.stub(MOVEBY, function=move, name='Creature_moveBy')
                    emu.default_ret = 0
                    try:
                        emu.call(KNOCK, obj, fargs=(1.0,))
                    except EmuError as exc:
                        check('knockback %#x net=%d B=%d A=%d ran' % (flags, network, mode_b, mode_a),
                              str(exc), 'return')
                        continue
                    sup = R.player_push_suppressed(flags, network, mode_b)
                    label = 'knockback flags %#x net=%d B=%d A=%d' % (flags, network, mode_b, mode_a)
                    check(label + ': moved', len(moved), 0 if sup else 1)
                    if sup:
                        check(label + ': speed zeroed', emu.mem.u32(obj + 0x2E8), 0)
                        check(label + ': no trig', len(calls(emu, 0x166630)) + len(calls(emu, 0x1666E0)), 0)
                    else:
                        check(label + ': push is nonzero', any(v & 0x7FFFFFFF for v in moved[0]), True)
                        check(label + ': speed decays by 2', emu.mem.u32(obj + 0x2E8), from_int(148))


def main(argv):
    global PATH, SEED_VALUE
    args = [a for a in argv[1:]]
    if '--seed' in args:
        i = args.index('--seed')
        SEED_VALUE = int(args[i + 1])
        del args[i:i + 2]
    PATH = args[0] if args else os.path.join('local', 'SLUS_209.73')
    if not os.path.exists(PATH):
        print('SKIP  no executable at %s' % PATH)
        return 2
    if hashlib.sha256(open(PATH, 'rb').read()).hexdigest() != ELF_SHA:
        print('SKIP  unexpected executable')
        return 2
    random.seed(SEED_VALUE)
    only = os.environ.get('ARENA_CASES')
    for name, fn in (('setup', case_setup), ('init', case_init), ('results', case_results),
                     ('overflow', case_overflow), ('knockback', case_knockback)):
        if only and name not in only.split(','):
            continue
        print('== %s (seed %d)' % (name, SEED_VALUE))
        before = len(RESULTS)
        try:
            fn()
        except EmuError as exc:
            check('%s: original body ran' % name, repr(exc), 'no fault')
        part = RESULTS[before:]
        print('   %s: %d checks, %d failed' % (name, len(part), sum(1 for _n, ok in part if not ok)))
    failed = sum(1 for _n, ok in RESULTS if not ok)
    print('%s  %d checks, %d failed, seed %d' % ('PASS' if not failed else 'FAIL', len(RESULTS),
                                                  failed, SEED_VALUE))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
