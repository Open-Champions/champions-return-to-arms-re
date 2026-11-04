#!/usr/bin/env python3
"""Ordered mission-menu beats against original EE functions.

The fresh hub-to-blood1 route stays in difftest_story_route.py. This file
adds the menu row the availability bits select, the story or evil level that
confirmation writes, and the act predicate for that level. It does not replay
the hub-dialog offer matrix or the mission-2 level chain.

Needs the owner's US v2.00 ELF. No game data or disassembly is written.
"""
import argparse
import hashlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, MemoryFault  # noqa: E402
import ref_story_route as R  # noqa: E402

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYERS = 0x4D8AF0
MISSION = 0x4BBF
EVIL = 0x4C1A
DECISION = 0x4C1B
NUM_PLAYERS = 0x4D8AE0
DIFFICULTY = 0x4F719C
SEED = 0x404464
MENU_STATE = 0x8E2EFC
MENU_ROW = 0x8E2F0C
MENU_COL = 0x8E2F0D
MENU_COUNTER = 0x8E2F04
MENU_MARK = 0x8E2F08
MENU_C0 = 0x8E2F00
PENDING = 0x41B6D0
ORIENT = 0x41B720
PAUSED = 0x41B4F4
PAD = 0x41BFE4
TABLE = 0x4FE540
STRIDE = 0x34
ACT_NOW = 0x88D3D4
ACT_LISTS = 0x4F8E48
ACT_COUNTS = 0x4F8E10
ACT_COUNT = 0x4F8E7C
SET_AVAILABLE = 0x1BF6D0
SET_COMPLETE = 0x1BF770
SET_EVIL = 0x1BF8F8
SET_DECISION = 0x1BF980
GET_HUB = 0x1EC300
FIND_ACT = 0x217D30
ACT_CHANGED = 0x217F70
ACT_SET = 0x2180A8
MENU_OPEN = 0x231520
MENU_RUN = 0x2316FC
HELPER = 0x18EBB8
INPUT_READY = 0x8E2F10
READY_ONE = 0x3F800000
# save_findAct from current act -1. Evil is empty when the row pointer is 0.
# The evil name is the same act as the story name.
TABLE_FROM_MINUS_ONE = (
    ('blood1', '', 0),
    ('innovat1', '', 1),
    ('islc1', '', 2),
    ('wat1', '', 3),
    ('tormenta', '', 4),
    ('swamp1', 'swamp2', 5),
    ('valor', '', 6),
    ('fire1', '', 7),
    ('storm1', '', 8),
    ('fay2', 'fay1', 9),
    ('nit1', '', 10),
    ('bossgood', 'bossevil', 11),
)
CURSOR = 0x44FE10
FREE_COUNT = 0x44FDA4
RES_FIND = 0x17365C
PAUSE_OPEN = 0x18CBFC
MENU_FOLLOW = {
    0x231078, 0x2310A8, 0x2310D4, 0x23112C, 0x231180, 0x2311D4, 0x231228,
    0x2312A8, 0x231310, 0x231360, 0x2313B4, 0x231438, 0x2314BC, 0x2314C8,
    0x1BF698, 0x1BF730, 0x1BF838, 0x1BF8D8, 0x3B868C,
}
LIBC = {0x3B91D8, 0x3B8DC4, 0x3B8534}
HUB_FOLLOW = {0x1BF8D8, 0x1BF960, 0x1BF730}


def signed(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def snap(mem):
    return (mem.s8(MENU_STATE), mem.s8(MENU_ROW), mem.s8(MENU_COL),
            mem.s32(MENU_COUNTER), mem.s32(MENU_MARK), mem.s32(PAUSED),
            mem.cstr(PENDING, 32), mem.u8(ORIENT), mem.s32(MENU_C0))


def model_snap(state):
    return tuple(state[key] for key in (
        'phase', 'row', 'col', 'counter', 'mark', 'paused', 'pending', 'orient', 'c0'))


def text_ptr(mem, addr):
    ptr = mem.u32(addr)
    return mem.cstr(ptr, 32) if ptr else ''


def load_rows(mem):
    rows = []
    for index in range(R.MENU_MISSIONS):
        base = TABLE + index * STRIDE
        rows.append((text_ptr(mem, base + 8), text_ptr(mem, base + 0xC)))
    return rows


def load_acts(mem):
    acts = []
    for act in range(mem.s32(ACT_COUNT)):
        ptr = mem.u32(ACT_LISTS + 4 * act)
        names = []
        for index in range(mem.s32(ACT_COUNTS + 4 * act)):
            names.append(text_ptr(mem, ptr + index * 8))
        acts.append(names)
    return acts


def direct(emu, addr, *args):
    saved = emu.follow
    emu.follow = None
    try:
        return emu.call(addr, *args, max_steps=2000000)
    finally:
        emu.follow = saved


def blank(mem, seed, difficulty=0):
    mem.write(PLAYERS, bytes(0x4C30))
    mem.w32(NUM_PLAYERS, 1)
    mem.w32(DIFFICULTY, difficulty)
    mem.w32(SEED, seed)
    mem.write(PENDING, bytes(0x80))
    mem.w8(ORIENT, 0)


def offer(emu, mission, difficulty):
    emu.mem.w32(DIFFICULTY, difficulty)
    direct(emu, SET_AVAILABLE, difficulty, mission, 1)


def complete(emu, mission, difficulty):
    emu.mem.w32(DIFFICULTY, difficulty)
    direct(emu, SET_COMPLETE, difficulty, mission, -1)


def mission_byte(mem, mission, difficulty):
    return mem.u8(PLAYERS + MISSION + difficulty * 13 + mission)


def prepare_menu(emu, local=1):
    emu.follow = set(MENU_FOLLOW)
    emu.record_calls = False
    # A local slot keeps reading the pad on later state-2 ticks. Pause stays
    # closed so that slot is not the pause-menu early return.
    emu.stub(0x13E150, ret=local, name='isLocal')
    emu.stub(0x13DD40, ret=1, name='slotActive')
    emu.stub(PAUSE_OPEN, ret=0, name='pauseOpen')
    emu.stub(0x1DF5EC, ret=0, name='fade')
    emu.stub(HELPER, ret=0, name='menuHelper')
    emu.stub(RES_FIND, ret=0, name='resFind')
    emu.stub(0x214230, ret=0, name='menuHost')


def tick(emu, state, button, available, rows, evil, fade=0):
    emu.mem.w32(PAD, button)
    emu.stub(0x1DF5EC, ret=fade, name='fade')
    emu.call(MENU_RUN, max_steps=400000)
    R.campaign_tick(state, button, available, rows, evil, fade)
    got, want = snap(emu.mem), model_snap(state)
    if got != want:
        raise AssertionError((button, got, want))
    return got


def open_menu(emu, available, rows, evil):
    emu.mem.write(PENDING, bytes(0x80))
    emu.mem.w8(ORIENT, 0)
    for addr in (MENU_STATE, MENU_C0, MENU_COUNTER, MENU_MARK):
        emu.mem.w32(addr, 0)
    emu.mem.w8(MENU_ROW, 0)
    emu.mem.w8(MENU_COL, 0)
    # A cold open. The reopen case below is what checks that open keeps pause.
    emu.mem.w32(PAUSED, 0)
    # Open's own callees stay stubbed, matching the fresh-route menu open.
    saved = emu.follow
    emu.follow = set()
    emu.call(MENU_OPEN, 0)
    emu.follow = saved
    state = R.new_menu()
    opened = snap(emu.mem)
    if opened != model_snap(state):
        raise AssertionError(('open', opened, model_snap(state)))
    for _ in range(17):
        tick(emu, state, 0, available, rows, evil)
    if state['phase'] != 2:
        raise AssertionError(('intro', state['phase'], state['row']))
    return state


def launch(emu, state, available, rows, evil):
    tick(emu, state, R.BTN_CROSS, available, rows, evil)
    tick(emu, state, 0, available, rows, evil)
    tick(emu, state, 0, available, rows, evil, 0)
    tick(emu, state, 0, available, rows, evil, 128)
    tick(emu, state, 0, available, rows, evil, 128)
    tick(emu, state, 0, available, rows, evil, 128)
    return state['pending'], state['orient']


def plant_prefix(emu, seed, last, finish_last, difficulty=0, evil=False):
    blank(emu.mem, seed, difficulty)
    offer(emu, 0, difficulty)
    complete(emu, 0, difficulty)
    for mission in range(1, last):
        offer(emu, mission, difficulty)
        complete(emu, mission, difficulty)
    offer(emu, last, difficulty)
    if finish_last:
        complete(emu, last, difficulty)
    if evil:
        emu.mem.w32(DIFFICULTY, difficulty)
        direct(emu, SET_EVIL, 1)
    available = set(range(1, last + 1))
    return available


def check_hub(emu, seed):
    checks = 0
    cases = (
        (False, False, False, 'hub'),
        (True, False, True, 'hub'),
        (False, True, True, 'hub'),
        (True, True, False, 'hub'),
        (True, True, True, 'hub2'),
    )
    for evil_on, decision_on, done, expect in cases:
        blank(emu.mem, seed, 0)
        if evil_on:
            direct(emu, SET_EVIL, 1)
        if decision_on:
            direct(emu, SET_DECISION, 1)
        offer(emu, 1, 0)
        if done:
            complete(emu, 1, 0)
        emu.follow = set(HUB_FOLLOW)
        ptr = emu.call(GET_HUB) & 0xFFFFFFFF
        got = emu.mem.cstr(ptr, 16)
        want = R.hub_name(emu.mem.u8(PLAYERS + EVIL), emu.mem.u8(PLAYERS + DECISION),
                          mission_byte(emu.mem, 1, 0), 0)
        if got != want or got != expect:
            raise AssertionError((evil_on, decision_on, done, got, want, expect))
        checks += 1
    # Mission 2's completion bit does not replace mission 1's.
    blank(emu.mem, seed, 0)
    direct(emu, SET_EVIL, 1)
    direct(emu, SET_DECISION, 1)
    offer(emu, 2, 0)
    complete(emu, 2, 0)
    emu.follow = set(HUB_FOLLOW)
    ptr = emu.call(GET_HUB) & 0xFFFFFFFF
    if emu.mem.cstr(ptr, 16) != 'hub':
        raise AssertionError('mission 2 completion changed the hub')
    return checks + 1


def check_acts(emu, names, acts):
    checks = 0
    libc = set(LIBC)
    for name in names:
        for current in (-1, 0):
            emu.follow = libc
            emu.mem.w32(ACT_NOW, current & 0xFFFFFFFF)
            buf = emu.alloc(40)
            emu.mem.write(buf, name.encode('latin1') + b'\0')
            got = signed(emu.call(FIND_ACT, buf))
            want = R.find_act(name, current, acts)
            if got != want:
                raise AssertionError(('find', name, current, got, want))
            emu.follow = libc | {FIND_ACT, ACT_SET}
            emu.mem.w32(ACT_NOW, current & 0xFFFFFFFF)
            buf = emu.alloc(40)
            emu.mem.write(buf, name.encode('latin1') + b'\0')
            ret = signed(emu.call(ACT_CHANGED, buf))
            stored = emu.mem.s32(ACT_NOW)
            if (ret, stored) != R.act_changed(name, current, acts):
                raise AssertionError(('change', name, current, ret, stored))
            checks += 2
    return checks


def check_seed(emu, seed, rows, acts, report):
    prepare_menu(emu)
    checks = check_hub(emu, seed)
    names = []
    for story, evil_name in rows:
        if story and story not in names:
            names.append(story)
        if evil_name and evil_name not in names:
            names.append(evil_name)
    for extra in ('hub', 'hub2', 'strife', 'drundar', 'drunarm', 'drunare',
                  'inmine1', 'inmine2', 'innovat2'):
        if extra not in names:
            names.append(extra)
    checks += check_acts(emu, names, acts)
    observed = tuple((story, evil_name, R.find_act(story, -1, acts))
                     for story, evil_name in rows)
    if observed != TABLE_FROM_MINUS_ONE:
        raise AssertionError(observed)
    for story, evil_name, act in TABLE_FROM_MINUS_ONE:
        if evil_name and R.find_act(evil_name, -1, acts) != act:
            raise AssertionError((story, evil_name, act))
    checks += 1
    if report:
        for name in ('hub', 'hub2', 'strife', 'drundar', 'drunarm', 'drunare',
                     'inmine1', 'inmine2', 'innovat2'):
            print('act %s from-1 %d from-0 %d' % (
                name, R.find_act(name, -1, acts), R.find_act(name, 0, acts)))
    prepare_menu(emu)

    def run_prefix(last, evil):
        available = plant_prefix(emu, seed, last, False, 0, evil)
        if mission_byte(emu.mem, 0, 0) != 3 or mission_byte(emu.mem, last, 0) != 1:
            raise AssertionError(('bytes', last, mission_byte(emu.mem, last, 0)))
        before = emu.mem.read(PLAYERS + MISSION, 13)
        state = open_menu(emu, available, rows, evil)
        if emu.mem.u32(INPUT_READY) != READY_ONE:
            raise AssertionError('input word was not 1 at the first choice tick')
        if state['row'] != last - 1:
            raise AssertionError(('row', last, state['row']))
        pending, orient = launch(emu, state, available, rows, evil)
        story, evil_name = rows[last - 1]
        want = R.story_level(story, evil_name, evil)
        if pending != want or orient != 0xFF:
            raise AssertionError((last, evil, pending, want, orient))
        if emu.mem.read(PLAYERS + MISSION, 13) != before:
            raise AssertionError('menu changed mission bytes')
        if emu.mem.u32(SEED) != seed:
            raise AssertionError('menu consumed the seed')
        if report:
            print('mission %d evil %d pending %s act %d' % (
                last, int(evil), pending, R.find_act(pending, -1, acts)))
        return 1

    for mission in range(1, 13):
        checks += run_prefix(mission, False)
        checks += run_prefix(mission, True)

    # One direction tick consumes the 1.0 gate. Cross on the next tick is not
    # read until that word is 1 again. The draw task is not used for this.
    available = plant_prefix(emu, seed, 1, True, 0, False)
    state = open_menu(emu, available, rows, False)
    offer(emu, 2, 0)
    available.add(2)
    prepare_menu(emu)
    tick(emu, state, R.BTN_DOWN, available, rows, False)
    emu.mem.w32(PAD, R.BTN_CROSS)
    emu.call(MENU_RUN, max_steps=400000)
    if emu.mem.s8(MENU_STATE) != 2 or emu.mem.s32(MENU_C0) != 0:
        raise AssertionError('cross was read while the input word was not 1')
    checks += 1

    # Completion leaves the cursor on that mission. The next offer does not
    # move it until down, and down will not cross a mission that is still off.
    for mission in range(1, 12):
        available = plant_prefix(emu, seed, mission, True, 0, False)
        state = open_menu(emu, available, rows, False)
        if state['row'] != mission - 1:
            raise AssertionError(('closed', mission, state['row']))
        tick(emu, state, 0, available, rows, False)
        if state['row'] != mission - 1:
            raise AssertionError('idle moved the row')
        offer(emu, mission + 1, 0)
        available.add(mission + 1)
        prepare_menu(emu)
        tick(emu, state, 0, available, rows, False)
        if state['row'] != mission - 1:
            raise AssertionError('offer moved the open row')
        tick(emu, state, R.BTN_DOWN, available, rows, False)
        if state['row'] != mission:
            raise AssertionError(('down', mission, state['row']))
        if emu.mem.u32(INPUT_READY) == READY_ONE:
            raise AssertionError('a direction tick left the input word at 1')
        # The draw task is not established as the restorer: entered alone it
        # faults. This write is the gate value, not that task's result.
        emu.mem.w32(INPUT_READY, READY_ONE)
        pending, orient = launch(emu, state, available, rows, False)
        if pending != rows[mission][0] or orient != 0xFF:
            raise AssertionError(('next', mission, pending, rows[mission][0]))
        checks += 1

    available = plant_prefix(emu, seed, 1, False, 0, False)
    offer(emu, 3, 0)
    available.add(3)
    state = open_menu(emu, available, rows, False)
    if state['row'] != 2:
        raise AssertionError(('gap-open', state['row']))
    emu.mem.w8(MENU_ROW, 0)
    state['row'] = 0
    tick(emu, state, R.BTN_DOWN, available, rows, False)
    if state['row'] != 0:
        raise AssertionError('down skipped a locked mission')
    emu.mem.w32(INPUT_READY, READY_ONE)
    emu.mem.w8(MENU_ROW, 1)
    state['row'] = 1
    tick(emu, state, R.BTN_DOWN, available, rows, False)
    if state['row'] != 2:
        raise AssertionError(('down-from-locked', state['row']))
    emu.mem.w32(INPUT_READY, READY_ONE)
    emu.mem.w8(MENU_ROW, 2)
    state['row'] = 2
    tick(emu, state, R.BTN_UP, available, rows, False)
    if state['row'] != 1:
        raise AssertionError(('up-onto-locked', state['row']))
    checks += 1

    available = plant_prefix(emu, seed, 1, True, 0, False)
    state = open_menu(emu, available, rows, False)
    pending, _orient = launch(emu, state, available, rows, False)
    if pending != rows[0][0]:
        raise AssertionError(('replay', pending))
    checks += 1

    blank(emu.mem, seed, 0)
    emu.follow = {0x1BF698, 0x1BF730, 0x1BF838}
    if any((emu.call(0x231078, row) & 0xFFFFFFFF) != (1 if row == 0 else 0)
           for row in range(12)):
        raise AssertionError('cleared record did not match the row-0 story gate')
    for mission in range(2, 13):
        blank(emu.mem, seed, 0)
        offer(emu, mission, 0)
        emu.follow = {0x1BF698, 0x1BF730, 0x1BF838}
        if (emu.call(0x231078, mission - 1) & 0xFFFFFFFF) != 1:
            raise AssertionError(('helper', mission))
        if mission < 12 and (emu.call(0x231078, mission) & 0xFFFFFFFF) != 0:
            raise AssertionError(('neighbor', mission))
    checks += 1
    prepare_menu(emu)
    blank(emu.mem, seed, 0)
    state = open_menu(emu, set(), rows, False)
    pending, orient = launch(emu, state, set(), rows, False)
    if pending != rows[0][0] or orient != 0xFF or mission_byte(emu.mem, 1, 0) != 0:
        raise AssertionError(('row0-without-bit', pending, mission_byte(emu.mem, 1, 0)))
    checks += 1

    available = plant_prefix(emu, seed, 1, False, 0, False)
    state = open_menu(emu, available, rows, False)
    emu.mem.w8(MENU_ROW, 4)
    emu.mem.write(PENDING, b'held-request\0')
    emu.mem.w8(ORIENT, 0xFD)
    offer(emu, 3, 0)
    available.add(3)
    prepare_menu(emu)
    emu.follow = set()
    emu.call(MENU_OPEN, 0)
    prepare_menu(emu)
    if (emu.mem.s8(MENU_STATE), emu.mem.s32(MENU_C0), emu.mem.s32(MENU_COUNTER),
            emu.mem.s32(MENU_MARK), emu.mem.s8(MENU_ROW), emu.mem.cstr(PENDING, 32),
            emu.mem.u8(ORIENT), emu.mem.s32(PAUSED)) != (0, 0, 0, 0, 4, 'held-request', 0xFD, 1):
        raise AssertionError('reopen did not keep the row and request')
    state = {
        'phase': 0, 'row': 4, 'col': emu.mem.s8(MENU_COL), 'counter': 0, 'mark': 0,
        'paused': 1, 'pending': 'held-request', 'orient': 0xFD, 'c0': 0,
    }
    tick(emu, state, 0, available, rows, False)
    if state['row'] != 2 or state['pending'] != 'held-request':
        raise AssertionError(('reopen-tick', state['row'], state['pending']))
    checks += 1

    blank(emu.mem, seed, 1)
    offer(emu, 1, 0)
    offer(emu, 4, 1)
    emu.mem.w32(DIFFICULTY, 1)
    state = open_menu(emu, {4}, rows, False)
    if state['row'] != 3:
        raise AssertionError(('difficulty', state['row'], mission_byte(emu.mem, 1, 0)))
    checks += 1

    # Difficulty 1 does not read difficulty 0's evil bit. Use the first row
    # whose evil pointer is set, so the two results can differ.
    evil_row = next(index for index, pair in enumerate(rows) if pair[1])
    evil_mission = evil_row + 1
    blank(emu.mem, seed, 1)
    offer(emu, evil_mission, 1)
    emu.mem.w32(DIFFICULTY, 1)
    emu.mem.w8(PLAYERS + EVIL, 1)
    state = open_menu(emu, {evil_mission}, rows, False)
    pending, _orient = launch(emu, state, {evil_mission}, rows, False)
    if state['row'] != evil_row or pending != rows[evil_row][0]:
        raise AssertionError(('wrong-bit', state['row'], pending))
    emu.mem.w8(PLAYERS + EVIL, 1 << 1)
    state = open_menu(emu, {evil_mission}, rows, True)
    pending, _orient = launch(emu, state, {evil_mission}, rows, True)
    if pending != rows[evil_row][1]:
        raise AssertionError(('right-bit', pending, rows[evil_row][1]))
    checks += 2
    # Draw is not established as the writer that puts 0x8e2f10 back to 1.
    available = plant_prefix(emu, seed, 1, True, 0, False)
    state = open_menu(emu, available, rows, False)
    offer(emu, 2, 0)
    prepare_menu(emu)
    tick(emu, state, R.BTN_DOWN, set(available) | {2}, rows, False)
    # follow None runs every callee that is not already stubbed. The menu
    # stubs stay installed, so res_find, pause open and the helper do not run.
    emu.follow = None
    if any(addr not in emu.hooks for addr in (RES_FIND, PAUSE_OPEN, HELPER)):
        raise AssertionError('menu stubs were not still installed')
    cursor = emu.mem.u32(CURSOR)
    if cursor != 0 or emu.mem.u32(FREE_COUNT) != 0x88B8:
        raise AssertionError((hex(cursor), hex(emu.mem.u32(FREE_COUNT))))
    try:
        emu.call(0x232300, max_steps=200000)
    except MemoryFault as exc:
        # The 8-byte store goes through the display-list cursor plus 0x10.
        if (exc.pc, exc.addr, exc.size, exc.kind) != (0x17B968, cursor + 0x10, 8, 'write'):
            raise AssertionError((hex(exc.pc), hex(exc.addr), exc.size, exc.kind, hex(cursor)))
    else:
        raise AssertionError('menu draw returned')
    checks += 1
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--seed', type=int, action='append', dest='seeds')
    args = parser.parse_args()
    blob = open(args.elf, 'rb').read()
    if hashlib.sha256(blob).hexdigest() != ELF_SHA256:
        raise SystemExit('unexpected executable')
    seeds = args.seeds or [20973, 7]
    probe = EE(args.elf)
    rows = load_rows(probe.mem)
    acts = load_acts(probe.mem)
    if len(rows) != 12 or not rows[0][0] or not acts:
        raise SystemExit('mission table was not readable')
    for index, seed in enumerate(seeds):
        emu = EE(args.elf)
        count = check_seed(emu, seed, rows, acts, report=(index == 0))
        print('PASS seed %d: %d story-beat checks' % (seed, count))


if __name__ == '__main__':
    main()
