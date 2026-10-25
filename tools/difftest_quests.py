#!/usr/bin/env python3
"""difftest_quests.py - compare tools/ref_quests.py with the original functions.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.

  python3 tools/difftest_quests.py [path/to/SLUS_209.73]

The original functions run in tools/ee_emu.py. Quest-list add/remove, the mission
bits and the script gold/experience wrappers stay in tools/difftest_natives.py
and are not repeated here. Existing reference modules are not modified.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError, MemoryFault, CpuTrap, UnimplementedInstruction  # noqa: E402
import ref_quests as Q  # noqa: E402

ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
HOME_ELF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SLUS_209.73')
ALT_ELF = os.environ.get('CHAMPIONS_ELF', '')

G_PLAYERS = 0x4D8AF0
REC = 0x4C30
NUM_PLAYERS = 0x4D8AE0
DIFFICULTY = 0x4F719C
MISSION = 0x4BBF
MEDAL = 0x4C0D
EVIL = 0x4C1A
DECISION = 0x4C1B
QUEST = 0x41D0
QUEST_COUNT = 0x43D0
LEVEL = 0x59
EXP = 0x5C
SKILL = 0xE8
STAT = 0xEC
HP = 0xAC
MAX_HP = 0xB0
MANA = 0xC0
MAX_MANA = 0xC4
BAGS = 0x130
BAG = 0x1208
BAG_COUNT = 0x1200
ITEM = 0x48

MENU_OPEN = 0x231520
MENU_RUN = 0x2316FC
HELPERS = [0x231078, 0x2310A8, 0x2310D4, 0x23112C, 0x231180, 0x2311D4,
           0x231228, 0x2312A8, 0x231310, 0x231360, 0x2313B4, 0x231438]
MENU_FOLLOW = set(HELPERS) | {0x2314BC, 0x2314C8, 0x1BF698, 0x1BF730, 0x1BF838, 0x1BF8D8, 0x3B868C}
STATE = 0x8E2EFC
ROW_AT = 0x8E2F0C
COL_AT = 0x8E2F0D
COUNTER = 0x8E2F04
MARK = 0x8E2F08
C0 = 0x8E2F00
PAUSED = 0x41B4F4
PENDING = 0x41B6D0
ORIENT = 0x41B720
PAD = 0x41BFE4
RECALC = 0x1B6458
CLEAR = 0x1D3ADC
HUB = 0x1EC300
GIVE = 0x1D3150
FIND = 0x217D30
CHANGED = 0x217F70
ACT_SET = 0x2180A8
ACT_NOW = 0x88D3D4
REMOVE_FLAGS = 0x1BE1D8
REMOVE_ITEM = 0x1C1CB0
MISSION_TABLE = 0x4FE540
MISSION_STRIDE = 0x34
ACT_LISTS = 0x4F8E48
ACT_COUNTS = 0x4F8E10
ACT_COUNT = 0x4F8E7C

RESULTS = []


def report(name, ok, detail):
    RESULTS.append((name, ok))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, detail))


def new_emu(follow):
    emu = EE(new_emu.elf)
    emu.follow = set(follow)
    emu.default_ret = 0
    return emu


def signed(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def load_row(mem, index):
    base = MISSION_TABLE + index * MISSION_STRIDE

    def text(off):
        ptr = mem.u32(base + off)
        return mem.cstr(ptr, 48) if ptr else ''

    return Q.MissionRow(text(8), text(0xC), text(0x10), text(0x14),
                        mem.s32(base + 0x20), mem.s32(base + 0x24), mem.s32(base + 0x28))


def load_acts(mem):
    count = mem.s32(ACT_COUNT)
    acts = []
    for act in range(count):
        ptr = mem.u32(ACT_LISTS + 4 * act)
        names = []
        for k in range(mem.s32(ACT_COUNTS + 4 * act)):
            np = mem.u32(ptr + k * 8)
            names.append(mem.cstr(np, 32) if np else '')
        acts.append(names)
    return acts


def load_xp(mem):
    return [mem.s32(Q.XP_TABLE + 4 * i) for i in range(Q.XP_LEVELS)]


def plant_mission(mem, difficulty, available, complete, medals, evil=0):
    mem.w32(NUM_PLAYERS, 1)
    mem.w32(DIFFICULTY, difficulty)
    for mission in range(13):
        byte = (1 if mission in available else 0) | (2 if mission in complete else 0)
        mem.w8(G_PLAYERS + MISSION + difficulty * 13 + mission, byte)
        mem.w8(G_PLAYERS + MEDAL + mission, medals.get(mission, 0))
    mem.w8(G_PLAYERS + EVIL, evil)


def check_helpers():
    bad = []
    cases = []
    for row in (0, 2, 5, 11):
        for medal in (0, 1, 2, 3):
            for complete in (False, True):
                cases.append((row, medal, complete, None))
    cases.append((0, 3, True, 'flag20'))
    cases.append((0, 3, True, 'flag24'))
    cases.append((0, 3, True, 'flag28'))
    cases.append((0, 3, True, 'flags'))
    cases.append((0, 3, True, 'medal'))
    for row, medal, complete, edit in cases:
        emu = new_emu({0x1BF698, 0x1BF730, 0x1BF838, 0x13E1F0})
        mission = row + 1
        if mission < 13:
            plant_mission(emu.mem, 1, {mission}, {mission} if complete else set(), {mission: medal})
        info = load_row(emu.mem, row)
        if edit == 'flag20':
            emu.mem.w32(MISSION_TABLE + row * MISSION_STRIDE + 0x20, 0)
        elif edit == 'flag24':
            emu.mem.w32(MISSION_TABLE + row * MISSION_STRIDE + 0x24, 0)
        elif edit == 'flag28':
            emu.mem.w32(MISSION_TABLE + row * MISSION_STRIDE + 0x28, 0)
        elif edit == 'flags':
            for off in (0x20, 0x24, 0x28):
                emu.mem.w32(MISSION_TABLE + row * MISSION_STRIDE + off, 0)
        elif edit == 'medal':
            emu.mem.w32(MISSION_TABLE + row * MISSION_STRIDE + 0x10, 0)
        info = load_row(emu.mem, row)
        avail = mission < 13
        for index, addr in enumerate(HELPERS):
            try:
                got = signed(emu.call(addr, row))
            except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
                bad.append((row, edit, index, type(exc).__name__))
                continue
            want = Q.helper_value(index, info, avail, complete and avail, medal)
            if got != want:
                bad.append((row, medal, complete, edit, index, got, want))
    report('menu helpers', not bad, '%d rows%s' % (len(cases), '' if not bad else ' ' + str(bad[:4])))


def snap(mem):
    return (mem.s8(STATE), mem.s8(ROW_AT), mem.s8(COL_AT), mem.s32(COUNTER), mem.s32(MARK),
            mem.s32(PAUSED), mem.cstr(PENDING, 32), mem.u8(ORIENT), mem.s32(C0))


def model_snap(state):
    return (state['state'], state['row'], state['col'], state['counter'], state['mark'],
            state['paused'], state['pending'], state['orient'], state['c0'])


def boot_menu(available, complete=(), medals=None, evil=0, difficulty=1):
    emu = new_emu(set())
    plant_mission(emu.mem, difficulty, available, set(complete), medals or {}, evil)
    emu.mem.write(PENDING, b'\0' * 0x60)
    emu.call(MENU_OPEN, 0)
    emu.follow = set(MENU_FOLLOW)
    emu.stub(0x13E150, ret=0, name='isLocal')
    emu.stub(0x13DD40, ret=1, name='slotActive')
    emu.stub(0x18CBFC, ret=0, name='pauseOpen')
    emu.stub(0x1DF5EC, ret=0, name='fade')
    rows = [load_row(emu.mem, i) for i in range(13)]
    world = Q.CampaignView(rows, available, complete, medals or {}, evil=bool(evil))
    return emu, Q.new_menu(), world


def tick(emu, state, world, button):
    emu.mem.w32(PAD, button)
    emu.stub(0x13E150, ret=1 if world.local else 0, name='isLocal')
    emu.stub(0x13DD40, ret=1 if world.slot_active else 0, name='slotActive')
    emu.stub(0x18CBFC, ret=1 if world.pause else 0, name='pauseOpen')
    emu.stub(0x1DF5EC, ret=world.fade, name='fade')
    emu.call(MENU_RUN, max_steps=400000)
    Q.menu_tick(state, button, world)
    return snap(emu.mem), model_snap(state)


def reach(emu, state, world, n=17):
    last = None
    for _ in range(n):
        last = tick(emu, state, world, 0)
        if last[0] != last[1]:
            return last
    return last


def check_menu():
    bad = []

    def run(label, fn):
        if len(bad) > 8:
            return
        try:
            got = fn()
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((label, type(exc).__name__, hex(getattr(exc, 'pc', 0))))
            return
        if got:
            bad.append((label, got))

    def intro(available, row):
        def body():
            emu, state, world = boot_menu(available)
            opened = snap(emu.mem)
            if opened[0] != 0:
                return ('open', opened)
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            if state['state'] != 2 or state['row'] != row or state['counter'] != 127:
                return (state['state'], state['row'], state['counter'])
            return None
        run('intro %s' % sorted(available), body)

    intro({1, 5}, 4)
    intro({2, 3, 11}, 10)
    intro(set(), 0)
    intro({0}, 0)

    def after(available, complete, medals, evil, setup, button, difficulty=1):
        emu, state, world = boot_menu(available, complete, medals, evil, difficulty)
        mismatch = reach(emu, state, world)
        if mismatch[0] != mismatch[1]:
            return mismatch
        setup(emu, state, world)
        got = tick(emu, state, world, button)
        if got[0] != got[1]:
            return got
        return None

    def force(row, col):
        def apply(emu, state, world):
            emu.mem.w8(ROW_AT, row)
            emu.mem.w8(COL_AT, col)
            state['row'] = row
            state['col'] = col
        return apply

    run('cross opens', lambda: after({1, 2}, set(), {}, 0, force(1, 0), Q.BTN_CROSS))
    run('cross locked', lambda: after({1}, set(), {}, 0, force(3, 0), Q.BTN_CROSS))
    run('circle closes', lambda: after({1, 2}, set(), {}, 0, force(1, 0), Q.BTN_CIRCLE))
    run('select closes', lambda: after({1, 2}, set(), {}, 0, force(1, 0), Q.BTN_SELECT))
    run('triangle stays', lambda: after({1, 2}, set(), {}, 0, force(1, 0), Q.BTN_TRIANGLE))
    run('up ignores the lock', lambda: after({1, 3}, set(), {}, 0, force(2, 0), Q.BTN_UP))
    run('up stays at 0', lambda: after({1}, set(), {}, 0, force(0, 0), Q.BTN_UP))
    run('down locked', lambda: after({1}, set(), {}, 0, force(0, 0), Q.BTN_DOWN))
    run('down moves', lambda: after({1, 2, 3}, set(), {}, 0, force(1, 0), Q.BTN_DOWN))
    run('down stays at 11', lambda: after({12}, set(), {}, 0, force(11, 0), Q.BTN_DOWN))
    run('right to medal', lambda: after({2}, {2}, {2: 0}, 0, force(1, 0), Q.BTN_RIGHT))
    run('left opens an even row', lambda: after({1}, {1}, {1: 0}, 0, force(0, 0), Q.BTN_LEFT))
    run('right stays on an even row', lambda: after({1}, {1}, {1: 3}, 0, force(0, 0), Q.BTN_RIGHT))
    run('right blocked', lambda: after({2}, set(), {2: 3}, 0, force(1, 0), Q.BTN_RIGHT))
    run('right to bonus', lambda: after({2}, {2}, {2: 3}, 0, force(1, 1), Q.BTN_RIGHT))
    run('right no bonus level', lambda: after({3}, {3}, {3: 3}, 0, force(2, 1), Q.BTN_RIGHT))
    run('left from bonus when open', lambda: after({2}, {2}, {2: 3}, 0, force(1, 2), Q.BTN_LEFT))
    run('left skips a locked medal', lambda: after({2}, set(), {2: 3}, 0, force(1, 2), Q.BTN_LEFT))
    run('left from medal', lambda: after({2}, set(), {}, 0, force(1, 1), Q.BTN_LEFT))
    run('confirm medal', lambda: after({2}, {2}, {2: 0}, 0, force(1, 1), Q.BTN_CROSS))
    run('confirm medal locked', lambda: after({2}, set(), {2: 3}, 0, force(1, 1), Q.BTN_CROSS))
    run('confirm bonus', lambda: after({2}, set(), {2: 3}, 0, force(1, 2), Q.BTN_CROSS))
    run('confirm bonus low', lambda: after({2}, set(), {2: 0}, 0, force(1, 2), Q.BTN_CROSS))

    def pause():
        def body():
            return after({1, 2}, set(), {}, 0, _pause, Q.BTN_CROSS)

        def _pause(emu, state, world):
            world.local = True
            world.pause = True
            force(1, 0)(emu, state, world)
        return body()
    run('pause eats the button', pause)

    def inactive():
        def body():
            emu, state, world = boot_menu({1})
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            world.slot_active = False
            got = tick(emu, state, world, 0)
            return None if got[0] == got[1] else got
        return body()
    run('inactive slot closes', inactive)

    def difficulty():
        def body():
            emu, state, world = boot_menu({4}, difficulty=2)
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            if state['row'] != 3:
                return ('row', state['row'])
            return None
        return body()
    run('difficulty 2', difficulty)

    def second_idle():
        def body():
            emu, state, world = boot_menu({1})
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            got = tick(emu, state, world, 0)
            if got[0] != got[1]:
                return got
            got = tick(emu, state, world, 0)
            return None if got[0] == got[1] else got
        return body()
    run('second idle tick', second_idle)

    def chain(evil, col, medals, complete, row):
        def body():
            emu, state, world = boot_menu({row + 1}, complete, medals, 2 if evil else 0)
            world.evil = bool(evil)
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            force(row, col)(emu, state, world)
            got = tick(emu, state, world, Q.BTN_CROSS)
            if got[0] != got[1]:
                return got
            for fade in (0, 0, 0, 128, 128, 128):
                world.fade = fade
                got = tick(emu, state, world, 0)
                if got[0] != got[1]:
                    return got
            return None
        return body

    run('launch story', chain(False, 0, {}, set(), 0))
    run('launch medal', chain(False, 1, {1: 0}, {1}, 0))
    run('launch bonus', chain(False, 2, {1: 3}, set(), 0))
    # Row 5 is the first table row whose evil-level pointer is set. The name
    # itself is read from the table on both sides.
    run('launch evil', chain(True, 0, {}, {6}, 5))
    run('launch evil ignored', chain(True, 0, {}, {2}, 1))

    def closing():
        def body():
            emu, state, world = boot_menu({1})
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            got = tick(emu, state, world, Q.BTN_CIRCLE)
            if got[0] != got[1]:
                return got
            for _ in range(4):
                got = tick(emu, state, world, 0)
                if got[0] != got[1]:
                    return got
            return None
        return body()
    run('close countdown', closing)

    def state3():
        def body():
            emu, state, world = boot_menu({1})
            mismatch = reach(emu, state, world)
            if mismatch[0] != mismatch[1]:
                return mismatch
            emu.mem.w8(STATE, 3)
            state['state'] = 3
            got = tick(emu, state, world, Q.BTN_CROSS)
            return None if got[0] == got[1] else got
        return body()
    run('state 3 returns', state3)

    report('mission menu', not bad, 'paths' if not bad else str(bad[:3]))


def check_clear():
    bad = []
    emu = new_emu(set())
    emu.mem.w32(NUM_PLAYERS, 2)
    blobs = []
    for slot, count, title in ((0, 1, b'ABCDEFGHIJKLMNOPQRSTUV'), (1, 2, b'QuestTwo'), (2, 3, b'Untouched')):
        rec = G_PLAYERS + slot * REC
        emu.mem.w32(rec + QUEST_COUNT, count)
        emu.mem.write(rec + QUEST, title + b'\0' * (32 - len(title)))
        emu.mem.write(rec + QUEST + 0x20, b'body-of-the-quest!!' + b'\0' * 14)
        emu.mem.write(rec + QUEST + 0x40, b'SECOND' + b'\0' * 26)
        blobs.append(emu.mem.read(rec + QUEST, 0x200))
    emu.call(CLEAR)
    for slot, count, _title in ((0, 1, None), (1, 2, None), (2, 3, None)):
        rec = G_PLAYERS + slot * REC
        entries = []
        for i in range(8):
            base = i * 0x40
            entries.append((blobs[slot][base:base + 32], blobs[slot][base + 32:base + 64]))
        if slot < 2:
            expect, n = Q.clear_quest_list(entries, count)
        else:
            expect, n = entries, count
        got_n = emu.mem.s32(rec + QUEST_COUNT)
        if got_n != n:
            bad.append(('count', slot, got_n, n))
        for i, (title, text) in enumerate(expect):
            got_t = emu.mem.read(rec + QUEST + i * 0x40, 32)
            got_x = emu.mem.read(rec + QUEST + i * 0x40 + 32, 32)
            if got_t != title or got_x != text:
                bad.append(('text', slot, i, got_t[:12], title[:12]))
                break
    report('quest clear', not bad, 'two records, the third left%s' % ('' if not bad else ' ' + str(bad[:3])))


def check_hub():
    bad = []
    cases = [(0, 0, 0, 1), (2, 0, 2, 1), (0, 2, 2, 1), (2, 2, 0, 1), (2, 2, 1, 1),
             (2, 2, 2, 1), (2, 2, 3, 1), (1, 1, 2, 1), (4, 4, 2, 2), (1, 1, 2, 0)]
    for evil, decision, mission, difficulty in cases:
        emu = new_emu({0x1BF8D8, 0x1BF960, 0x1BF730})
        emu.mem.w32(DIFFICULTY, difficulty)
        emu.mem.w8(G_PLAYERS + EVIL, evil)
        emu.mem.w8(G_PLAYERS + DECISION, decision)
        emu.mem.w8(G_PLAYERS + MISSION + difficulty * 13 + 1, mission)
        try:
            ptr = emu.call(HUB) & 0xFFFFFFFF
            got = emu.mem.cstr(ptr, 16)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((evil, type(exc).__name__))
            continue
        want = Q.hub_name(evil, decision, mission, difficulty)
        if got != want:
            bad.append((evil, decision, mission, difficulty, got, want))
    report('hub name', not bad, '%d cases%s' % (len(cases), '' if not bad else ' ' + str(bad[:4])))


def check_exp():
    bad = []
    table = load_xp(new_emu(set()).mem)

    def one(slot, level, exp, amount, hp, max_hp, mana, max_mana, stat=0):
        emu = new_emu(set())
        emu.mem.w32(NUM_PLAYERS, 2)
        rec = G_PLAYERS + slot * REC
        other = G_PLAYERS + (1 - slot) * REC
        emu.mem.w8(rec + LEVEL, level)
        emu.mem.w32(rec + EXP, exp & 0xFFFFFFFF)
        emu.mem.w32(rec + SKILL, 0)
        emu.mem.w8(rec + STAT, stat & 0xFF)
        emu.mem.wf32(rec + HP, hp)
        emu.mem.wf32(rec + MAX_HP, max_hp)
        emu.mem.wf32(rec + MANA, mana)
        emu.mem.wf32(rec + MAX_MANA, max_mana)
        emu.mem.w8(other + LEVEL, 3)
        emu.stub(RECALC, ret=0, name='recalc')
        emu.call(GIVE, slot, amount)
        want = Q.give_exp(level, exp, 0, stat & 0xFF, hp, max_hp, mana, max_mana, amount, table)
        got = (emu.mem.s8(rec + LEVEL), emu.mem.s32(rec + EXP), emu.mem.s32(rec + SKILL),
               emu.mem.u8(rec + STAT), emu.mem.f32(rec + HP), emu.mem.f32(rec + MANA),
               len([c for c in emu.calls if c.target == RECALC]))
        if got != want or emu.mem.s8(other + LEVEL) != 3:
            return got, want, emu.mem.s8(other + LEVEL)
        return None

    t1 = table[1]
    cases = [
        one(0, 1, 0, 0, 10.0, 20.0, 3.0, 9.0),
        one(0, 1, 0, 10, 10.0, 20.0, 3.0, 9.0),
        one(0, 1, t1 - 5, 10, 10.0, 20.0, 3.0, 9.0),
        one(0, 1, t1 - 5, 10, 0.0, 20.0, 3.0, 9.0),
        one(0, 5, table[5] - 1, 5, 4.0, 8.0, 1.0, 2.0),
        one(0, 15, table[15] - 1, 1, 4.0, 8.0, 1.0, 2.0),
        one(0, 35, table[35] - 1, 1, 4.0, 8.0, 1.0, 2.0),
        one(0, 36, table[36] - 1, 1, 4.0, 8.0, 1.0, 2.0),
        one(0, 79, table[79], 10 ** 9, 4.0, 8.0, 1.0, 2.0, stat=250),
        one(0, 80, table[80] - 1, 100, 4.0, 8.0, 1.0, 2.0),
        one(0, 5, 100, -5, 4.0, 8.0, 1.0, 2.0),
        one(1, 2, 0, table[2], 4.0, 8.0, 1.0, 2.0),
    ]
    for item in cases:
        if item:
            bad.append(item)
    report('give exp', not bad, '%d cases%s' % (len(cases), '' if not bad else ' ' + str(bad[:2])))


def check_acts():
    bad = []
    acts = load_acts(new_emu(set()).mem)
    if any(not prefix for act in acts for prefix in act):
        bad.append(('empty prefix',))
    libc = {0x3B91D8, 0x3B8DC4, 0x3B8534}

    def find(name, current):
        emu = new_emu(libc)
        emu.mem.w32(ACT_NOW, current & 0xFFFFFFFF)
        buf = emu.alloc(32)
        emu.mem.write(buf, name.encode('ascii') + b'\0')
        return signed(emu.call(FIND, buf))

    for name, current in (('hub', 0), ('hub2', 0), ('hub2', 7), ('blood1', 0), ('blood1_x', 0),
                          ('blood', 0), ('fire', 0), ('fire1', 0), ('fire1', 3), ('fire1', 7),
                          ('fire1', -1), ('endgood', 0), ('HUB', 0), ('nope', 0)):
        try:
            got = find(name, current)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append((name, type(exc).__name__))
            continue
        want = Q.find_act(name, current, acts)
        if got != want:
            bad.append(('find', name, current, got, want))

    def changed(name, current):
        emu = new_emu(libc | {FIND, ACT_SET})
        emu.mem.w32(ACT_NOW, current & 0xFFFFFFFF)
        buf = emu.alloc(32)
        emu.mem.write(buf, name.encode('ascii') + b'\0')
        ret = signed(emu.call(CHANGED, buf))
        return ret, emu.mem.s32(ACT_NOW)

    for name, current in (('fire1', 3), ('fire1', 7), ('fire1', -1), ('nope', 3), ('hub', 7)):
        try:
            got = changed(name, current)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            bad.append(('change', name, type(exc).__name__))
            continue
        want = Q.act_changed(name, current, acts)
        if got != want:
            bad.append(('change', name, current, got, want))
    report('acts', not bad, '%d prefixes%s' % (sum(len(a) for a in acts), '' if not bad else ' ' + str(bad[:4])))


def check_flag39():
    bad = []
    bit = 1 << 39

    def run(items, slot=0, bag=0):
        emu = new_emu({0x3B96A8, 0x3B8534, 0x3B8DC4})
        emu.mem.w32(NUM_PLAYERS, 2)
        rec = G_PLAYERS + slot * REC
        base = rec + BAGS + bag * BAG
        emu.mem.w32(base + BAG_COUNT, len(items))
        for index, (name, flags) in enumerate(items):
            defin = emu.alloc(32)
            text = emu.alloc(48)
            emu.mem.write(text, name.encode('ascii') + b'\0')
            emu.mem.w32(defin, text)
            item = base + index * ITEM
            emu.mem.w32(item, defin)
            emu.mem.w64(item + 8, flags)

        def drop(machine):
            who = machine.r[4] & 0xFFFFFFFF
            index = machine.r[5] & 0xFFFFFFFF
            which = machine.r[6] & 0xFFFFFFFF
            if who > 3 or which > 2 or index > 40:
                drop.args = (who, index, which)
                return 0
            at = G_PLAYERS + who * REC + BAGS + which * BAG
            count = machine.mem.s32(at + BAG_COUNT)
            if index >= count:
                return 0
            for i in range(index, count - 1):
                machine.mem.write(at + i * ITEM, machine.mem.read(at + (i + 1) * ITEM, ITEM))
            machine.mem.w32(at + BAG_COUNT, count - 1)
            return 0
        drop.args = None
        emu.stub(REMOVE_ITEM, function=drop, name='remove')
        try:
            emu.call(REMOVE_FLAGS, slot, max_steps=2000000)
        except (EmuError, MemoryFault, CpuTrap, UnimplementedInstruction) as exc:
            return 'fault %s %08x args %s' % (type(exc).__name__, emu.pc, drop.args)
        count = emu.mem.s32(base + BAG_COUNT)
        left = []
        for index in range(count):
            defin = emu.mem.u32(base + index * ITEM)
            left.append(emu.mem.cstr(emu.mem.u32(defin), 48) if defin else '')
        want = [name for name, _flags in Q.flag39_remaining(items)]
        if left != want:
            return (left, want, drop.args)
        return None

    names = ['zzzz', 'bloodstonefay', 'xxshardofyy', 'spiritrunes', 'emptybag', 'fullbag',
             'pickaxe', 'pickaxe2', 'twistedkey', 'Bloodstone', '']
    for name in names:
        got = run([(name, bit)])
        if got:
            bad.append((name, got))
    got = run([('zzzz', 0)])
    if got:
        bad.append(('plain', got))
    got = run([('zzzz', 1 << 38)])
    if got:
        bad.append(('bit38', got))
    got = run([('pickaxe', bit), ('zzzz', bit)])
    if got:
        bad.append(('keep then drop', got))
    got = run([('zzzz', bit), ('pickaxe', bit)])
    if got:
        bad.append(('drop then keep', got))
    got = run([('zzzz', bit), ('yyyy', bit)])
    if got:
        bad.append(('drop both', got))
    got = run([('zzzz', bit)], bag=1)
    if got:
        bad.append(('bag1', got))
    got = run([('zzzz', bit)], bag=2)
    if got:
        bad.append(('bag2', got))
    got = run([('zzzz', bit)], slot=1)
    if got:
        bad.append(('slot1', got))
    report('flag 39', not bad, '%d bags%s' % (len(names) + 6, '' if not bad else ' ' + str(bad[:3])))


def main(argv):
    elf = argv[1] if len(argv) > 1 else HOME_ELF
    if not os.path.exists(elf):
        elf = ALT_ELF
    if not os.path.exists(elf):
        print('SKIP: SLUS_209.73 not found (the differential test needs your own copy of the executable)')
        return 0
    new_emu.elf = elf
    check_helpers()
    check_menu()
    check_clear()
    check_hub()
    check_exp()
    check_acts()
    check_flag39()
    failed = [name for name, ok in RESULTS if not ok]
    print('%d properties, %d failed' % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
