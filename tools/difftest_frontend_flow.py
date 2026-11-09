#!/usr/bin/env python3
"""Execute the original front-end flow from boot to the first level request.

Usage: python3 tools/difftest_frontend_flow.py <SLUS_209.73>

The pinned US v2.00 executable is read only.  Original functions run in
tools/ee_emu.py on authored memory at seeds 20973 and 7.  Callees outside
each case's follow set are auto-stubbed (return 0) and recorded; extra
stubs are named where they are installed.  Watched words are planted with
sentinels so an absent store is visible.  Strings are compared with the
executable's own bytes and are never printed or stored.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ee_emu import EE, EmuError  # noqa: E402
import ref_frontend_flow as R  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SENT32 = 0xA5A5A5A5
SENT8 = 0xA5
STRCMP, STRCPY, STRSTR, MEMSET = 0x3B8534, 0x3B868C, 0x3B96A8, 0x3B60C0
LIST_RUN = 0x1A01D0
MAX_DIFFICULTY_FN = 0x1EC448
TASK_ADD = 0x19E4A0
PAD_WORDS = (0x41BFE0, 0x41BFE4, 0x41BFE8)   # pad 0 held / pressed / repeat
assert PAD_WORDS == tuple(R.PAD_BASE + w for w in (R.PAD_HELD, R.PAD_PRESSED, R.PAD_REPEAT))
SELECT_CLEARS = (0x4F701C, 0x41B4F4)        # words cleared before character selection
# Executable string addresses compared at run time (contents not stored).
STR_INTRO_LEVEL = 0x53D0D0
STR_SELECT_LEVEL = 0x53D3E8
STR_HUB_A, STR_HUB_B = 0x53D6B8, 0x53D6C0
STR_THEME = 0x53CE20
FRONTEND_LUMPS = (0x53CDF8, 0x53CE00, 0x53CE10)
STR_NEED_PLAYERS = 0x5404E0


def emulator(path, seed):
    e = EE(path)
    e.mem.auto_map = True
    e.mem.w32(0x404460, seed)
    e.mem.w32(0x404464, seed)
    return e


def run(e, entry, *args, steps=400000):
    e.reset_log()
    try:
        return e.call(entry, *args, max_steps=steps)
    except EmuError as exc:
        raise AssertionError('0x%08x: %s' % (entry, exc)) from exc


def stores(e, addr):
    return [(pc, value) for pc, a, _, value in e.writes if a == addr]


def calls(e, *targets):
    return [(c.site, c.target, tuple(x & 0xFFFFFFFF for x in c.args[:4]))
            for c in e.calls if c.target in targets]


def same_cstr(e, a, b):
    return e.mem.cstr(a) == e.mem.cstr(b) and e.mem.cstr(a) != ''


# ---- frontend_start and the first frontend_run pass -------------------------------
START_WATCH = (R.FIRST_ENTRY, R.THEME_REQUESTED, R.NUM_PLAYERS)
# (address, store site, value) of frontend_start's own stores, over sentinels.
START_STORES = ((R.NUM_PLAYERS, 0x1E1F78, 1), (R.THEME_REQUESTED, 0x1E1F7C, 0),
                (R.FIRST_ENTRY, 0x1E1F84, 1), (R.PENDING_MARKER, 0x1E20C0, 0xFF))


def frontend_start(path, seed, load_byte, card_done):
    e = emulator(path, seed)
    e.follow = {R.FRONTEND_MAIN_TABLE_FN}
    m = e.mem
    m.w8(R.LOAD_FROM_MENU, load_byte)
    m.w8(0x4F8F29, card_done)
    m.w8(0x4F7019, 0)
    m.w32(R.STATE, SENT32)
    m.w32(R.MENU, SENT32)
    for addr in START_WATCH:        # the executable's own initial values are hidden
        m.w32(addr, SENT32)
    m.w8(R.PENDING_MARKER, SENT8)
    m.w8(R.PENDING_LEVEL, 0)
    run(e, R.FRONTEND_START, 0)
    task = [c for c in calls(e, TASK_ADD)]
    return dict(
        state=m.u32(R.STATE), menu=m.u32(R.MENU), first=m.u32(R.FIRST_ENTRY),
        theme=m.u32(R.THEME_REQUESTED), players=m.u32(R.NUM_PLAYERS),
        load_byte=m.u8(R.LOAD_FROM_MENU),
        load=calls(e, R.LOAD_REQUEST),
        task=[(t[2][0], t[2][1], t[2][3]) for t in task],
        intro=same_cstr(e, R.PENDING_LEVEL, STR_INTRO_LEVEL),
        marker=m.u8(R.PENDING_MARKER),
        stores=[(addr, stores(e, addr)) for addr, _, _ in START_STORES])


def first_pass(path, seed, theme_byte):
    e = emulator(path, seed)
    e.follow = {LIST_RUN, STRCMP, STRSTR, R.FRONTEND_MAIN_TABLE_FN, MAX_DIFFICULTY_FN}
    m = e.mem
    m.w32(R.FIRST_ENTRY, 1)
    m.w32(R.THEME_REQUESTED, 0)
    m.w8(0x4F701A, theme_byte)
    m.w32(R.STATE, 0)
    m.w32(R.MENU, R.T_MAIN)
    e.stub(0x216480, ret=0x77, name='audio_handle')
    run(e, R.FRONTEND_RUN)
    lumps = [c[2][0] for c in calls(e, 0x173558)]
    theme = [(c[2][0], c[2][1]) for c in calls(e, 0x2110E0)]
    order = [c.target for c in e.calls if c.target in (
        0x173558, 0x222A8C, 0x2243F8, 0x1E3D2C, 0x211CE8, 0x2110E0, 0x216480)]
    return dict(lumps=lumps, theme=theme, order=order,
                first_args=[(c[0], c[2][0]) for c in calls(e, 0x211CE8, 0x216480)],
                first=m.u32(R.FIRST_ENTRY), requested=m.u32(R.THEME_REQUESTED),
                handle=m.u32(0x4F7028))


# ---- frontend_run accept / cancel ---------------------------------------------------
def frontend_input(path, seed, state, table, row, mask, players=1, profile=0,
                   difficulty=SENT32, pads=4, net=0, present=None, kinds=None,
                   pad_words=None, accept_mask=None, cancel_mask=None):
    """One frontend_run pass.  mask goes to pad 0's held, pressed and repeat
    words unless pad_words gives per-slot (held, pressed, repeat) tuples.
    present is a 4-bit pad-present mask (default: slots 0..pads-1); kinds
    pre-plants the players table's four kind words."""
    e = emulator(path, seed)
    e.follow = {LIST_RUN, STRCMP, STRSTR, R.FRONTEND_MAIN_TABLE_FN, MAX_DIFFICULTY_FN}
    m = e.mem
    m.w32(R.FIRST_ENTRY, 0)
    m.w32(R.THEME_REQUESTED, 1)
    m.w32(R.STATE, state)
    m.w32(R.MENU, table)
    rows = R.TABLE_ROWS.get(table, 0)
    if rows:
        m.w32(table + rows * 16 + 4, row)
    if pad_words is None:
        pad_words = [(mask, mask, mask)]
    for slot, words in enumerate(pad_words):
        for offset, value in zip((R.PAD_HELD, R.PAD_PRESSED, R.PAD_REPEAT), words):
            m.w32(R.PAD_BASE + slot * R.PAD_STRIDE + offset, value)
    if accept_mask is not None:
        m.w32(R.ACCEPT_MASK_WORD, accept_mask)
    if cancel_mask is not None:
        m.w32(R.CANCEL_MASK_WORD, cancel_mask)
    if present is None:
        present = (1 << pads) - 1
    for slot in range(4):   # per-slot pad-present words read by the players list
        m.w32(R.PAD_PRESENT + slot * R.PAD_STRIDE, present >> slot & 1)
    if kinds is not None:
        for i, kind in enumerate(kinds):
            m.w32(R.T_PLAYERS + i * 16 + 4, kind)
    for addr in SELECT_CLEARS:
        m.w32(addr, SENT32)
    m.w32(R.PROFILE_WORD, profile)
    m.w32(R.NUM_PLAYERS, players)
    m.w32(R.DIFFICULTY, difficulty)
    m.w8(R.KILL_LIMIT, SENT8)
    for addr in (R.MODE_VS, R.MODE_ARENA, R.MODE_SCRAMBLE):
        m.w32(addr, SENT32)
    m.w32(R.NET_CHOSEN, net)     # offline unless a case sets it
    m.w8(R.LOAD_FROM_MENU, 0)
    run(e, R.FRONTEND_RUN)
    return e


def outcome(e):
    m = e.mem
    return dict(
        state=m.u32(R.STATE), menu=m.u32(R.MENU),
        players=m.u32(R.NUM_PLAYERS), difficulty=m.u32(R.DIFFICULTY),
        kill=m.u8(R.KILL_LIMIT), vs=m.u32(R.MODE_VS), arena=m.u32(R.MODE_ARENA),
        scramble=m.u32(R.MODE_SCRAMBLE), net=m.u32(R.NET_CHOSEN),
        load_byte=m.u8(R.LOAD_FROM_MENU),
        select=calls(e, R.FRONTEND_START_PLAYER_SELECT),
        load=calls(e, R.LOAD_REQUEST),
        options=calls(e, 0x1E6428), credits=calls(e, 0x223C64),
        net_start=calls(e, 0x1E21E0), lobby=calls(e, 0x327F80),
        memset=[(c[0], c[2][:3]) for c in calls(e, MEMSET)],
        state_stores=stores(e, R.STATE))


def check_accepts(path, seed):
    n = 0
    # Main menu rows.
    for row, (state, table) in R.MAIN_ACCEPT.items():
        o = outcome(frontend_input(path, seed, R.S_MAIN, R.T_MAIN, row, R.ACCEPT_MASK))
        assert (o['state'], o['menu']) == (state, table), (seed, row, o)
        if row == R.MAIN_LOAD:
            assert o['state_stores'] == [], (seed, o['state_stores'])
            assert [c[2][:2] for c in o['load']] == [R.LOAD_REQUEST_ARGS], o['load']
            assert o['load'][0][0] == 0x1E166C
            assert o['load_byte'] == 1
            assert (o['vs'], o['arena'], o['scramble']) == (0, 0, 0)
        else:
            assert o['load'] == [] and o['load_byte'] == 0, (seed, row, o)
        assert bool(o['options']) == (row == R.MAIN_OPTIONS)
        assert bool(o['credits']) == (row == R.MAIN_CREDITS)
        assert o['select'] == [] and o['difficulty'] == SENT32
        n += 1
    # Game type: offline row then network row.
    o = outcome(frontend_input(path, seed, R.S_GAME_TYPE, R.T_GAME_TYPE, 0, R.ACCEPT_MASK, net=SENT32))
    assert (o['state'], o['menu'], o['net']) == (R.S_PLAYERS, R.T_PLAYERS, 0), (seed, o)
    o = outcome(frontend_input(path, seed, R.S_GAME_TYPE, R.T_GAME_TYPE, 1, R.ACCEPT_MASK, net=SENT32))
    assert (o['state'], o['net']) == (R.S_LOBBY_WAIT, 1), (seed, o)
    assert [c[0] for c in o['lobby']] == [0x1E1854], o['lobby']
    assert o['memset'] == [(0x1E1828, (0x402A30, 0, 0x14C))], o['memset']
    n += 2
    # Players rows 0..3 (a planted row past the table is clamped by the list
    # handler, so it is not a separate input).
    for row in range(4):
        o = outcome(frontend_input(path, seed, R.S_PLAYERS, R.T_PLAYERS, row,
                                   R.ACCEPT_MASK, players=SENT32))
        want = R.players_accept(row)
        if want is None:
            assert (o['state'], o['players']) == (R.S_PLAYERS, SENT32), (seed, row, o)
        else:
            assert (o['players'], o['state'], o['menu']) == want, (seed, row, o)
        assert (o['vs'], o['arena'], o['scramble']) == (0, 0, 0), (seed, row, o)
        n += 1
    # Rows beyond the first absent pad are disabled (kind word 5) before input.
    for pads in (1, 2, 3, 4):
        e = frontend_input(path, seed, R.S_PLAYERS, R.T_PLAYERS, 0, 0, pads=pads)
        kinds = tuple(e.mem.u32(R.T_PLAYERS + i * 16 + 4) for i in range(4))
        assert kinds == R.players_row_kinds(pads), (seed, pads, kinds)
        n += 1
    # Every present pattern, gaps included, with all four kind words planted 5:
    # row r is re-enabled (0, stored at 0x1e0f74) iff slots 1..r are present;
    # slot 0 is not read and row 0 keeps the planted value.
    for present in range(16):
        e = frontend_input(path, seed, R.S_PLAYERS, R.T_PLAYERS, 0, 0, present=present,
                           kinds=(R.ROW_DISABLED,) * 4)
        kinds = tuple(e.mem.u32(R.T_PLAYERS + i * 16 + 4) for i in range(4))
        want = R.players_row_kinds_present(present, row0_kind=R.ROW_DISABLED)
        assert kinds == want, (seed, bin(present), kinds)
        for i in range(1, 4):
            site = R.PLAYERS_ENABLE_SITE if want[i] == R.ROW_ENABLED else R.PLAYERS_DISABLE_SITE
            assert stores(e, R.T_PLAYERS + i * 16 + 4) == [(site, want[i])], (seed, bin(present), i)
        assert stores(e, R.T_PLAYERS + 4) == [], (seed, bin(present))
        n += 1
    e = frontend_input(path, seed, R.S_PLAYERS, R.T_PLAYERS, 3, R.ACCEPT_MASK,
                       players=SENT32, pads=2)
    o = outcome(e)
    # The list handler moved the planted disabled row; it ended on row 0 here.
    assert (o['players'], o['state'], o['menu']) == R.players_accept(0), (seed, o)
    n += 1
    # Mode rows, one-player and multi-player tables.
    for table, flags in R.MODE_FLAGS.items():
        players = 1 if table == R.T_MODE_ONE else 3
        for row, (vs, scramble, arena) in enumerate(flags):
            o = outcome(frontend_input(path, seed, R.S_MODE, table, row,
                                       R.ACCEPT_MASK, players=players))
            assert (o['vs'], o['scramble'], o['arena']) == (vs, scramble, arena), (seed, table, row, o)
            want = R.mode_next(vs, scramble, arena)
            if want[0] == 'select':
                assert o['difficulty'] == want[1] and len(o['select']) == 1, (seed, table, row, o)
                assert o['select'][0][0] == 0x1E19C0
            else:
                assert (o['state'], o['menu']) == want[1:], (seed, table, row, o)
                assert o['select'] == [] and o['difficulty'] == SENT32
            assert o['players'] == players
            n += 1
    # Kill limit (offline): difficulty is not written on this route.
    for row, kill in enumerate(R.KILL_LIMITS):
        o = outcome(frontend_input(path, seed, R.S_KILL_LIMIT, R.T_KILL_LIMIT, row,
                                   R.ACCEPT_MASK, players=2))
        assert o['kill'] == kill and len(o['select']) == 1, (seed, row, o)
        assert o['select'][0][0] == 0x1E1A78 and o['difficulty'] == SENT32
        n += 1
    # Difficulty rows against every profile unlock level.
    for profile in (0, 0x04, 0x08, 0x01, 0x10, 0x20, 0x40, 0x7D):
        for row in range(4):
            e = frontend_input(path, seed, R.S_DIFFICULTY, R.T_DIFFICULTY, row,
                               R.ACCEPT_MASK, players=1, profile=profile)
            o = outcome(e)
            want = R.difficulty_accept(row, profile)
            if want is None:
                assert o['difficulty'] == SENT32 and o['select'] == [], (seed, profile, row, o)
                assert o['state'] == R.S_DIFFICULTY
            else:
                assert o['difficulty'] == want, (seed, profile, row, o)
                assert [c[0] for c in o['select']] == [0x1E1AD0], o['select']
                # Cleared over planted sentinels by frontend_run itself.
                assert [stores(e, a) for a in SELECT_CLEARS] == [[(0x1E1ACC, 0)], [(0x1E1AD4, 0)]]
            if want is None:
                assert [stores(e, a) for a in SELECT_CLEARS] == [[], []]
            n += 1
    return n


def check_input_rule(path, seed):
    """Accept / cancel come from pad slot 0's pressed word masked by the words
    at 0x41bfbc / 0x41bfb8; held, repeat and pad slot 1 do not count."""
    n = 0
    A, C = R.ACCEPT_MASK, R.CANCEL_MASK
    accept_cases = (
        ([(0, A, 0)], None), ([(A, 0, 0)], None), ([(0, 0, A)], None),
        ([(A, 0, A)], None), ([(0, 0, 0), (0, A, 0)], None),
        ([(0, 0, 0), (A, A, A)], None), ([(0, A, 0)], 0x04), ([(0, 0x04, 0)], 0x04),
        ([(0, 0x80, 0)], 0x80))
    for pads, mask in accept_cases:
        e = frontend_input(path, seed, R.S_MAIN, R.T_MAIN, R.MAIN_NEW, 0,
                           pad_words=pads, accept_mask=mask)
        accept, _ = R.menu_input(pads, A if mask is None else mask, C)
        want = (R.S_GAME_TYPE, R.T_GAME_TYPE) if accept else (R.S_MAIN, R.T_MAIN)
        o = outcome(e)
        assert (o['state'], o['menu']) == want, (seed, pads, mask, o)
        assert len(o['state_stores']) == (1 if accept else 0), (seed, pads, o['state_stores'])
        n += 1
    cancel_cases = (
        ([(0, 0x20, 0)], None), ([(0, 0x100, 0)], None), ([(C, 0, 0)], None),
        ([(0, 0, C)], None), ([(0, 0, 0), (0, C, 0)], None),
        ([(0, C, 0)], 0x04), ([(0, 0x04, 0)], 0x04))
    for pads, mask in cancel_cases:
        e = frontend_input(path, seed, R.S_GAME_TYPE, R.T_GAME_TYPE, 0, 0,
                           pad_words=pads, cancel_mask=mask)
        _, cancel = R.menu_input(pads, A, C if mask is None else mask)
        want = (R.S_MAIN, R.T_MAIN) if cancel else (R.S_GAME_TYPE, R.T_GAME_TYPE)
        o = outcome(e)
        assert (o['state'], o['menu']) == want, (seed, pads, mask, o)
        assert len(o['state_stores']) == (1 if cancel else 0), (seed, pads, o['state_stores'])
        n += 1
    return n


def check_max_difficulty(path, seed):
    """0x1ec448 called directly: its return for every single bit and mixes."""
    n = 0
    for word in (0, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x100,
                 0x60, 0x30, 0x0C, 0x7D, 0xFFFFFF80):
        e = emulator(path, seed)
        e.follow = set()
        e.mem.w32(R.PROFILE_WORD, word)
        got = run(e, MAX_DIFFICULTY_FN)
        assert got == R.max_difficulty(word), (seed, hex(word), got)
        n += 1
    return n


def check_cancels(path, seed):
    n = 0
    cases = ((R.S_GAME_TYPE, R.T_GAME_TYPE, 1), (R.S_PLAYERS, R.T_PLAYERS, 1),
             (R.S_DIFFICULTY, R.T_DIFFICULTY, 1), (R.S_DIFFICULTY, R.T_DIFFICULTY, 2),
             (R.S_MODE, R.T_MODE_ONE, 1), (R.S_KILL_LIMIT, R.T_KILL_LIMIT, 2),
             (R.S_OPTIONS, R.T_OPTIONS, 1))
    for state, table, players in cases:
        e = frontend_input(path, seed, state, table, 0, R.CANCEL_MASK, players=players)
        assert stores(e, R.NET_CHOSEN) == []   # offline: cancel never writes it
        want_state, want_table = R.cancel_offline(state, players)
        o = outcome(e)
        assert o['state'] == want_state, (seed, state, players, o)
        assert o['menu'] == (table if want_table is None else want_table), (seed, state, o)
        assert o['select'] == [] and o['difficulty'] == SENT32
        n += 1
    return n


# ---- frontend_startPlayerSelect -> playerSel_start -> playerSel_finish ---------------
def start_select(e, difficulty, players, arena=0, net=0):
    m = e.mem
    m.w32(R.DIFFICULTY, difficulty)
    m.w32(R.NUM_PLAYERS, players)
    m.w32(R.MODE_ARENA, arena)
    m.w32(R.NET_CHOSEN, net)
    m.w8(R.PLAYER_SEL_PLAYERS, SENT8)
    m.w8(R.PLAYER_SEL_OFFLINE, SENT8)
    m.w8(0x4FBBE1, SENT8)
    m.w32(0x4FDCB4, SENT32)
    for addr in SELECT_CLEARS:
        m.w32(addr, SENT32)
    m.write(R.SEL_LEVEL, bytes([SENT8]) * 0x40)
    run(e, R.FRONTEND_START_PLAYER_SELECT)
    return calls(e, R.PLAYER_SEL_START, 0x304BC8)


def check_select_entry(path, seed):
    n = 0
    for difficulty in (1, 2, 3, 4):
        for players in (1, 4):
            e = emulator(path, seed)
            e.follow = {STRCPY}
            got = start_select(e, difficulty, players)
            m = e.mem
            assert [(c[0], c[2][0]) for c in got] == [
                (0x1E3C58, R.import_first(difficulty))], (seed, difficulty, got)
            assert m.u8(R.PLAYER_SEL_PLAYERS) == players
            assert m.u8(R.PLAYER_SEL_OFFLINE) == 1
            assert same_cstr(e, R.SEL_LEVEL, STR_SELECT_LEVEL)
            assert [stores(e, a) for a in SELECT_CLEARS] == [[(0x1E3BEC, 0)], [(0x1E3BF0, 0)]]
            assert m.u8(0x4FBBE1) == 0 and m.u32(0x4FDCB4) == 0
            n += 1
    # Arena route: the level name comes from 0x304BC8 (stubbed to an authored name).
    e = emulator(path, seed)
    e.follow = {STRCPY}
    name = e.alloc(16)
    e.mem.write(name, b'zz\0')
    e.stub(0x304BC8, ret=name, name='arena_levelName')
    got = start_select(e, 1, 1, arena=1)
    assert [c[1] for c in got] == [0x304BC8, R.PLAYER_SEL_START], got
    assert e.mem.cstr(R.SEL_LEVEL) == 'zz'
    n += 1
    return n


def player_sel_start(path, seed, import_arg):
    e = emulator(path, seed)
    e.follow = {MEMSET}
    m = e.mem
    scratch = e.alloc(0x158C)
    m.w32(0x4FDB7C, scratch)
    m.w8(R.PLAYER_SEL_PHASE, SENT8)
    m.w8(0x4FBBE1, 0)
    m.w8(R.PLAYER_SEL_OFFLINE, 1)
    m.w32(R.PLAYER_SEL_PENDING, SENT32)
    m.w32(R.PLAYER_SEL_RUNNING, SENT32)
    m.write(R.SEL_ROWS, bytes([SENT8]) * 0xB0)
    run(e, R.PLAYER_SEL_START, import_arg)
    task = [c[2] for c in calls(e, TASK_ADD)]
    return dict(phase=m.u8(R.PLAYER_SEL_PHASE), slot=m.u8(R.PLAYER_SEL_SLOT),
                pending=m.u32(R.PLAYER_SEL_PENDING), running=m.u32(R.PLAYER_SEL_RUNNING),
                carousel=m.s8(R.SEL_ROWS + 0x20), other=m.u8(R.SEL_ROWS + 0x2C + 0x20),
                committed=m.u8(R.PLAYER_SEL_COMMITTED),
                keyboard=len(calls(e, 0x22BC9C)), task=task,
                scratch_flag=m.u8(scratch + 0x1554))


def check_player_sel_start(path, seed):
    plain = player_sel_start(path, seed, 0)
    assert plain['phase'] == SENT8, plain            # phase not written
    assert plain['carousel'] == 1 and plain['other'] == 0, plain
    assert plain['pending'] == 1 and plain['running'] == 1, plain
    assert plain['committed'] == 0 and plain['keyboard'] == 1 and plain['scratch_flag'] == 0
    assert [(t[0], t[1], t[3]) for t in plain['task']] == [
        (R.PLAYER_SEL_TASK, R.PLAYER_SEL_PRIORITY, 1)], plain['task']
    imp = player_sel_start(path, seed, 1)
    assert imp['phase'] == R.PHASE_IMPORT and imp['carousel'] == 0, imp
    assert imp['scratch_flag'] == 1 and imp['pending'] == 1, imp
    return 2


def finish_chain(path, seed, decision=0, evil=0, complete=0, players=1, difficulty=1):
    """startPlayerSelect (playerSel_start stubbed) then playerSel_finish(0)."""
    e = emulator(path, seed)
    e.follow = {STRCPY, STRCMP, R.HUB_NAME_FN}
    e.stub(R.HUB_DECIDED, ret=decision, name='game_getMadeDecision')
    e.stub(R.HUB_SIDE, ret=evil, name='game_getEvil')
    e.stub(R.HUB_COMPLETE, ret=complete, name='mission_isComplete')
    start_select(e, difficulty, players)
    m = e.mem
    m.w8(0x4FDBA0, 1)
    m.write(R.PENDING_LEVEL, bytes([SENT8]) * 0x50 + b'\0')
    m.w8(R.PENDING_MARKER, 0)
    m.w8(R.PLAYER_SEL_COMMITTED, 0)
    m.w32(R.PLAYER_SEL_RUNNING, SENT32)
    m.w32(R.PLAYER_SEL_PENDING, SENT32)
    run(e, R.PLAYER_SEL_FINISH, 0)
    return e, dict(
        stop=calls(e, R.FRONTEND_STOP), var=calls(e, 0x1ED854),
        note=calls(e, 0x322954), hub=calls(e, R.HUB_COMPLETE),
        predicates=[(c[1], c[0], c[2][:2]) for c in calls(e, R.HUB_DECIDED, R.HUB_SIDE,
                                                           R.HUB_COMPLETE)],
        difficulty=m.u32(R.DIFFICULTY),
        marker=m.u8(R.PENDING_MARKER), committed=m.u8(R.PLAYER_SEL_COMMITTED),
        running=m.u32(R.PLAYER_SEL_RUNNING), pending=m.u32(R.PLAYER_SEL_PENDING),
        hub_a=same_cstr(e, R.PENDING_LEVEL, STR_HUB_A),
        hub_b=same_cstr(e, R.PENDING_LEVEL, STR_HUB_B))


def check_finish(path, seed):
    n = 0
    # Every first-false position of the three-predicate chain, and the third
    # predicate's arguments at three difficulties (first argument is
    # g_difficultyIdx, second the constant 1).
    for decision, evil, complete, difficulty in (
            (0, 0, 0, 1), (0, 1, 1, 1), (0, 1, 1, 3), (1, 0, 1, 1), (1, 0, 1, 3),
            (1, 1, 0, 1), (1, 1, 0, 3), (1, 1, 1, 1), (1, 1, 1, 3), (1, 1, 1, 4)):
        e, o = finish_chain(path, seed, decision, evil, complete, difficulty=difficulty)
        want_b = R.hub_is_second(decision, evil, complete)
        assert [c[0] for c in o['stop']] == [0x22A46C], (seed, o)
        assert [c[2][0] for c in o['stop']] == [0], o['stop']
        assert [(c[2][0], c[2][1]) for c in o['var']] == [(STR_NEED_PLAYERS, 0)], o['var']
        assert [c[2][0] for c in o['note']] == [10], o['note']
        assert o['marker'] == 0xFF and o['committed'] == 1, o
        assert o['running'] == 0 and o['pending'] == SENT32, o
        assert o['difficulty'] == difficulty, o
        assert (o['hub_a'], o['hub_b']) == (not want_b, want_b), (
            seed, decision, evil, complete, difficulty, o)
        want_calls = R.hub_predicate_calls(decision, evil, difficulty)
        got_calls = o['predicates']
        assert [(fn, site) for fn, site, _ in got_calls] == [
            (fn, R.HUB_PREDICATE_SITES[fn]) for fn, _ in want_calls], (seed, got_calls)
        for (fn, args), (_, _, got_args) in zip(want_calls, got_calls):
            if args is not None:
                assert got_args == args, (seed, difficulty, got_args)
        n += 1
    # finish(1): pending cleared, queued level copied from 0x4FDC70.
    e = emulator(path, seed)
    e.follow = {STRCPY, STRCMP}
    m = e.mem
    m.w8(0x4FDBA0, 1)
    m.write(R.SEL_ALT_LEVEL, b'qq\0')
    m.w32(R.PLAYER_SEL_PENDING, SENT32)
    m.w8(R.PENDING_MARKER, 0)
    run(e, R.PLAYER_SEL_FINISH, 1)
    assert m.u32(R.PLAYER_SEL_PENDING) == 0 and m.cstr(R.PENDING_LEVEL) == 'qq'
    assert m.u8(R.PENDING_MARKER) == 0xFF and calls(e, R.FRONTEND_STOP) == []
    n += 1
    # finish(1) with an empty alternate name requests nothing.
    e = emulator(path, seed)
    e.follow = {STRCPY, STRCMP}
    m = e.mem
    m.w8(0x4FDBA0, 1)
    m.w8(R.SEL_ALT_LEVEL, 0)
    m.write(R.PENDING_LEVEL, b'pp\0')
    m.w8(R.PENDING_MARKER, 0)
    run(e, R.PLAYER_SEL_FINISH, 1)
    assert m.cstr(R.PENDING_LEVEL) == 'pp' and m.u8(R.PENDING_MARKER) == 0
    n += 1
    # Call-site arguments in playerSel_task (instruction words read, not run):
    # the delay slot is addiu a0,zero,1 or daddu a0,zero,zero.
    for site, arg in R.FINISH_SITES:
        word = e.mem.u32(site + 4)
        jal = e.mem.u32(site)
        assert jal == 0x0C000000 | (R.PLAYER_SEL_FINISH >> 2), hex(jal)
        assert word == (0x24040000 | arg if arg else 0x0000202D), hex(word)
        n += 1
    return n


# ---- main menu load -> load screen -> front end stopped -----------------------------
LOAD_SCREEN, SLOT_LIST, PUMP, QUEUE = 0x219360, 0x21C3A4, 0x2233E4, 0x223470
CARD_SET_STATE = 0x21F238


def load_request_chain(path, seed):
    """Main-menu load row with memcard_requestLoad followed for real."""
    e = emulator(path, seed)
    e.follow = {LIST_RUN, STRCMP, STRSTR, R.FRONTEND_MAIN_TABLE_FN, MAX_DIFFICULTY_FN,
                R.LOAD_REQUEST, CARD_SET_STATE}
    m = e.mem
    m.w32(R.FIRST_ENTRY, 0)
    m.w32(R.THEME_REQUESTED, 1)
    m.w32(R.STATE, 0)
    m.w32(R.MENU, R.T_MAIN)
    m.w32(R.T_MAIN + 4 * 16 + 4, R.MAIN_LOAD)
    for addr in PAD_WORDS:
        m.w32(addr, R.ACCEPT_MASK)
    m.w8(0x41B510, 1)
    m.w32(0x88D3C8, 0)
    m.w32(0x88D3C0, 0)
    m.w32(0x88D3A0, SENT32)
    m.w8(0x8E1AB8, SENT8)
    m.w8(0x8E1AB9, SENT8)
    m.w8(0x4F923C, SENT8)
    m.w8(0x4F8F29, SENT8)
    run(e, R.FRONTEND_RUN)
    set_state = [(c[0], c[2][:2]) for c in calls(e, CARD_SET_STATE)]
    assert set_state == [(0x217764, (4, 0))], set_state
    assert m.u8(0x4F8F29) == 0          # card-screen-done byte cleared on open
    return (m.u32(0x88D3A0), m.u8(0x8E1AB8), m.u8(0x8E1AB9), m.u8(0x4F923C),
            m.u8(R.LOAD_FROM_MENU), m.u32(R.STATE))


# Callees stubbed in load_accept (return 0).  Names are from names.tsv; the
# five without one are named by address.
LOAD_ACCEPT_STUBS = (
    (0x21E650, 'unnamed_21e650'), (0x21E65C, 'unnamed_21e65c'),
    (0x21E5C8, 'memcard_closeFile'), (0x21E8B4, 'memcard_popPause'),
    (0x21E850, 'memcard_pushPause'), (0x21F260, 'memcard_backupEntry'),
    (0x21F2F8, 'memcard_restoreEntry'), (0x1DF248, 'hud_drawMessageBox'),
    (0x19EA78, 'wstr_format'), (0x173FD4, 'pad_resetSlotMap'),
    (0x1DF5D0, 'hud_setFade'), (R.FRONTEND_STOP, 'frontend_stop'),
    (0x17FF48, 'unnamed_17ff48'), (0x17FF18, 'unnamed_17ff18'),
    (0x17E4C8, 'unnamed_17e4c8'), (0x173C84, 'text_lookup'))
CARD_DIR_RECORD = 0x88D2C0     # 0x40-byte directory record copied on acceptance
CARD_DIR_COPY_SITES = (0x2194C4, 0x2194C8, 0x2194CC, 0x2194D0, 0x2194D4, 0x2194D8,
                       0x2194DC, 0x2194E4)


def load_accept(path, seed, in_frontend, apply_flag):
    """memcard_loadScreen accepting a slot; slot list stubbed to return 1."""
    e = emulator(path, seed)
    e.stub(SLOT_LIST, ret=1, name='memcard_slotList')
    e.stub(PUMP, ret=0, name='mc_isBusy')
    e.stub(QUEUE, ret=0, name='mc_queueOp')
    for addr, name in LOAD_ACCEPT_STUBS:
        e.stub(addr, ret=0, name=name)
    m = e.mem
    m.w32(0x88D3E4, 1)
    m.w32(0x88D3D8, 0)
    m.w32(0x88D3A8, 0)
    m.w32(0x88D3A0, 4)
    m.w32(0x88D3BC, 0)
    m.w32(0x8E11F8, 0x40)
    m.w32(0x8E11FC, 0)
    m.w8(0x402791, 0)
    m.w32(0x41BFB8, R.CANCEL_MASK)
    m.w32(0x41BFBC, R.ACCEPT_MASK)
    m.w32(0x88D3B0, 1)
    m.w8(0x8E1AB8, in_frontend)
    m.w8(0x8E1AB9, apply_flag)
    m.write(CARD_DIR_RECORD, bytes([SENT8]) * 0x40)
    run(e, LOAD_SCREEN, steps=2000000)
    copy = [(pc, a, size) for pc, a, size, _ in e.writes
            if CARD_DIR_RECORD <= a < CARD_DIR_RECORD + 0x40]
    covered = sorted(b for _, a, size in copy for b in range(a, a + size))
    return dict(stop=[(c[0], c[2][0]) for c in calls(e, R.FRONTEND_STOP)],
                accepted=stores(e, 0x88D3D8), step=stores(e, 0x8E11FC),
                copy_sites=[pc for pc, _, _ in copy],
                copy_full=covered == list(range(CARD_DIR_RECORD, CARD_DIR_RECORD + 0x40)))


def check_load(path, seed):
    card, frontend, flag, slot, byte, state = load_request_chain(path, seed)
    assert (card, frontend, flag, slot, byte, state) == (4, 1, 1, 0, 1, 0), (
        seed, card, frontend, flag, slot, byte, state)
    n = 1
    for in_frontend in (0, 1):
        for apply_flag in (0, 1):
            got = load_accept(path, seed, in_frontend, apply_flag)
            want = [(0x21946C, 0)] if in_frontend and apply_flag else []
            assert got['stop'] == want, (seed, in_frontend, apply_flag, got)
            # Slot acceptance was reached in every combination: the accepted
            # word, the step word and the whole 0x40-byte directory record copy.
            assert got['accepted'] == [(0x21944C, 1)], (seed, in_frontend, apply_flag, got)
            assert got['step'] == [(0x219450, 0x10)], (seed, in_frontend, apply_flag, got)
            assert got['copy_sites'] == list(CARD_DIR_COPY_SITES) and got['copy_full'], got
            n += 1
    return n


def check_start(path, seed):
    o = frontend_start(path, seed, 0, 0)
    assert (o['state'], o['menu']) == (R.S_MAIN, R.T_MAIN), o
    # Planted sentinels: each value below was stored by frontend_start itself.
    assert o['first'] == 1 and o['theme'] == 0 and o['players'] == 1, o
    assert o['stores'] == [(addr, [(site, value)]) for addr, site, value in START_STORES], o['stores']
    assert o['task'] == [(R.FRONTEND_RUN, R.TASK_PRIORITY, 0)], o['task']
    assert o['intro'] and o['marker'] == 0xFF and o['load'] == [], o
    reopen = frontend_start(path, seed, 1, 0)
    assert [(c[0], c[2][:2]) for c in reopen['load']] == [(0x1E1FAC, (0, 1))], reopen
    assert reopen['load_byte'] == 0 and reopen['state'] == SENT32, reopen
    done = frontend_start(path, seed, 1, 1)
    assert done['load'] == [] and done['state'] == R.S_MAIN and done['load_byte'] == 1, done
    n = 3
    for theme_byte, flags in ((0, 5), (1, 1)):
        p = first_pass(path, seed, theme_byte)
        assert p['lumps'] == list(FRONTEND_LUMPS), p
        assert p['theme'] == [(STR_THEME, flags)], p
        assert p['order'] == [0x173558, 0x173558, 0x173558, 0x222A8C, 0x2243F8,
                              0x1E3D2C, 0x211CE8, 0x2110E0, 0x216480], p
        assert p['first_args'] == [(0x1E0994, 2), (0x1E09D4, 2)], p['first_args']
        assert p['first'] == 0 and p['requested'] == 1 and p['handle'] == 0x77, p
        n += 1
    return n


def check_tables(path):
    e = EE(path)
    n = 0
    for table, rows in R.TABLE_ROWS.items():
        for i in range(rows):
            assert e.mem.u32(table + i * 16) != 0, (hex(table), i)
        assert e.mem.u32(table + rows * 16) == 0, hex(table)
        n += 1
    assert e.mem.u32(0x41BFBC) == R.ACCEPT_MASK and e.mem.u32(0x41BFB8) == R.CANCEL_MASK
    assert e.mem.u32(R.FIRST_ENTRY) == 1 and e.mem.u32(R.DIFFICULTY) == 1
    assert e.mem.u32(R.PROFILE_WORD) == 0
    return n + 1


# ---- character creation phases: points, stats, name, name result ---------------------
STRLEN = 0x3B8DC4
PLAYER_SEL_SCRATCH = 0x4FDB7C


def s32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def selection(path, seed, phase):
    e = emulator(path, seed)
    e.follow = set()
    m = e.mem
    scratch = e.alloc(0x158C)
    m.w32(PLAYER_SEL_SCRATCH, scratch)
    m.w8(R.PLAYER_SEL_PHASE, phase)
    m.w8(R.NEXT_PHASE, SENT8)
    m.w32(0x8E2C44, 0x3F800000)     # task fade float must be 1.0 to dispatch
    m.w32(0x8E2C18, 0)              # phase transition float idle
    m.w8(R.PLAYER_SEL_SLOT, 0)
    return e, scratch


def stat_frame(path, seed, carousel, stats, points, cursor, pressed=0, repeat=0,
               warn=(0, 0, 0)):
    e, _ = selection(path, seed, R.PHASE_STATS)
    m = e.mem
    m.w8(R.SEL_ROWS + 0x20, carousel)
    for i, value in enumerate(stats):
        m.w8(R.SEL_ROWS + 0x25 + i, value)
    m.w32(R.POINTS, points)
    m.w8(R.STAT_CURSOR, cursor)
    m.w8(R.STAT_WARN, warn[0])
    m.w32(0x8E2BB4, warn[1])
    m.w32(0x8E2BB8, warn[2])
    m.w32(0x41BFE0, pressed | repeat)
    m.w32(0x41BFE4, pressed)
    m.w32(0x41BFE8, repeat)
    run(e, R.PLAYER_SEL_TASK)
    return dict(stats=[m.s8(R.SEL_ROWS + 0x25 + i) for i in range(4)],
                points=m.u32(R.POINTS), cursor=m.u8(R.STAT_CURSOR),
                next=m.u8(R.NEXT_PHASE),
                warn=(m.u8(R.STAT_WARN), s32(m.u32(0x8E2BB4)), s32(m.u32(0x8E2BB8))),
                lower=calls(e, 0x22BDB0))


def check_stats(path, seed):
    n = 0
    for carousel in (1, 2, 3, 12):
        base = list(R.class_base(carousel))
        cases = [
            (base, 20, 0, 0x2000), (base, 20, 3, 0x2000),
            (base, 0, 1, 0x2000),
            ([99] + base[1:], 5, 0, 0x2000), ([100] + base[1:], 5, 0, 0x2000),
            (base, 0, 2, 0x8000),
            ([base[0], base[1] + 1] + base[2:], 0, 1, 0x8000),
            (base, 0, 0, 0x1000), (base, 0, 3, 0x4000), (base, 0, 1, 0x4000),
            (base, 0, 2, 0x10), (base, 0, 2, 0x100000), (base, 0, 1, 0x200000),
            (base, 4, 1, 0x800000), ([base[0] + 2] + base[1:], 0, 0, 0x400000),
        ]
        for stats, points, cursor, repeat in cases:
            got = stat_frame(path, seed, carousel, stats, points, cursor, repeat=repeat)
            want = R.stat_input(stats, points, cursor, carousel, repeat)
            assert (got['stats'], got['points'], got['cursor']) == (want[0], want[1], want[2]), (
                seed, carousel, stats, points, cursor, hex(repeat), got)
            assert got['next'] == SENT8
            n += 1
    base = list(R.class_base(1))
    warn = stat_frame(path, seed, 1, base, 3, 0, pressed=R.ACCEPT_MASK)
    assert R.stat_accept(3) == 'warn' and warn['warn'] == (1, 0, 16) and warn['next'] == SENT8, warn
    go = stat_frame(path, seed, 1, base, 0, 0, pressed=R.ACCEPT_MASK)
    assert go['next'] == R.stat_accept(0) and [c[0] for c in go['lower']] == [0x227E64], go
    back = stat_frame(path, seed, 1, base, 3, 0, pressed=0x20)
    assert back['next'] == R.PHASE_APPEARANCE and back['points'] == 3, back
    dismiss = stat_frame(path, seed, 1, base, 3, 0, pressed=R.ACCEPT_MASK, warn=(1, 120, 16))
    assert dismiss['warn'] == (1, 126, -16), dismiss
    faded = stat_frame(path, seed, 1, base, 3, 0, warn=(1, 10, -16))
    assert faded['warn'] == (0, 0, -16), faded
    # Warning frames: alpha steps and clamps at 126; accept flips the step only
    # when this frame's alpha is 126 (110 + 16 and 122 + 4 do, 109 + 16 and
    # 120 + 4 do not); at or below 0 the warning clears.
    for alpha, step, accept in ((126, 16, 1), (100, 16, 1), (120, 16, 0), (126, 16, 0),
                                (110, 16, 1), (109, 16, 1), (120, 4, 1), (122, 4, 1),
                                (126, 0, 1), (50, 0, 1), (126, -16, 1), (100, -16, 1),
                                (3, -2, 0), (2, -2, 0), (0, 16, 0)):
        got = stat_frame(path, seed, 1, base, 3, 0,
                         pressed=R.ACCEPT_MASK if accept else 0, warn=(1, alpha, step))
        want = R.stat_warning_frame(alpha, step, accept)
        assert got['warn'] == want, (seed, alpha, step, accept, got)
        assert got['next'] == SENT8 and got['points'] == 3, got
        n += 1
    return n + 5


def check_point_pool(path, seed):
    """Appearance-accept slice 0x226C68..0x226D58 for every carousel row, slot 1."""
    n = 0
    for carousel in range(1, 13):
        e = emulator(path, seed)
        e.follow = set()
        m = e.mem
        m.write(R.SEL_ROWS, bytes([SENT8]) * 0xB0)
        m.w32(R.POINTS, SENT32)
        m.w8(R.STAT_CURSOR, SENT8)
        m.w8(R.STAT_WARN, SENT8)
        m.w8(R.PLAYER_SEL_SLOT, 1)
        # Every carousel column of the four appearance arrays holds a decoy;
        # this row's column holds distinct values.
        m.write(R.APPEARANCE_VALUES, bytes([0xEE]) * (4 * R.APPEARANCE_STRIDE))
        values = tuple(carousel + 3 * i + 1 for i in range(4))
        for i, value in enumerate(values):
            m.w8(R.appearance_source(i, carousel), value)
        # Caller state at 0x226C64: v0 = slot * 0x2C, s3 = carousel row,
        # s4 = 0x8E0000, s6 = 0x500000 (register bases the slice uses).
        e.r[2], e.r[19], e.r[20], e.r[22] = 0x2C, carousel, 0x8E0000, 0x500000
        e.reset_log()
        assert e.run(0x226C68, until=(0x226D58,), max_steps=2000) == 'stop'
        row = R.SEL_ROWS + 0x2C
        stats = tuple(m.u8(row + 0x25 + i) for i in range(4))
        assert stats == R.class_base(carousel), (seed, carousel, stats)
        assert (m.u32(R.POINTS), m.u8(R.STAT_CURSOR), m.u8(R.STAT_WARN),
                m.u8(R.NEXT_PHASE)) == (R.STAT_POINTS, 0, 0, R.PHASE_STATS)
        assert m.u8(R.SEL_ROWS + 0x25) == SENT8      # slot 0's row untouched
        copied = tuple(m.u8(row + R.APPEARANCE_ROW_BYTES[i]) for i in range(4))
        assert copied == values, (seed, carousel, copied, values)
        assert m.u8(R.SEL_ROWS + 0x21) == SENT8
        n += 1
    return n


def name_call(path, seed, name, cursor, pressed=0, repeat=0, held=0, key=-1, warn=0):
    e = emulator(path, seed)
    e.follow = {STRLEN}
    m = e.mem
    scratch = e.alloc(0x158C)
    m.w32(PLAYER_SEL_SCRATCH, scratch)
    run(e, 0x22BC9C)                # original keyboard initializer fills the grid
    glyphs = bytes(m.read(scratch + 0x14B4, 64))
    m.w32(0x8E2C3C, 0x3F800000)
    m.w8(R.PLAYER_SEL_SLOT, 0)
    m.w8(R.NAME_WARN, warn)
    m.write(R.SEL_ROWS, name.encode() + b'\0')
    m.w32(R.NAME_LENGTH, len(name))
    m.w32(R.NAME_CURSOR, cursor & 0xFFFFFFFF)
    m.w32(R.NAME_KEY, key & 0xFFFFFFFF)
    m.w32(0x41BFE0, held | pressed | repeat)
    m.w32(0x41BFE4, pressed)
    m.w32(0x41BFE8, repeat)
    result = s32(run(e, 0x22BE68))
    return dict(result=result, name=m.cstr(R.SEL_ROWS), length=m.u32(R.NAME_LENGTH),
                warn=m.u8(R.NAME_WARN), glyphs=glyphs,
                after=bytes(m.read(scratch + 0x14B4, 26)))


def check_name(path, seed):
    n = 0
    lower = ''.join(chr(c) for c in range(97, 123)) + ''.join(chr(c) for c in range(48, 58))
    for name, cursor in (('', 0), ('ab', 5), ('ab', 35), ('ab', R.CURSOR_SPACE),
                         ('x' * 29, 0), ('x' * 30, 0), ('x' * 30, R.CURSOR_SPACE),
                         ('', R.CURSOR_DONE), ('  ', R.CURSOR_DONE),
                         (' a', R.CURSOR_DONE), ('a ', R.CURSOR_DONE)):
        got = name_call(path, seed, name, cursor, pressed=R.ACCEPT_MASK)
        want = R.name_accept(name, cursor, lower)
        assert (got['name'], got['result'], got['warn']) == want, (seed, name, cursor, got)
        assert got['length'] == len(want[0])
        n += 1
    for mask in (0x20, 0x100):          # either cancel bit returns -1, name kept
        got = name_call(path, seed, 'abc', 3, pressed=mask)
        assert (got['result'], got['name'], got['length']) == (-1, 'abc', 3), got
        n += 1
    got = name_call(path, seed, 'abc', 3, repeat=R.NAME_DELETE_REPEAT)
    assert (got['name'], got['length']) == ('ab', 2), got
    got = name_call(path, seed, '', 3, repeat=R.NAME_DELETE_REPEAT)
    assert (got['name'], got['length']) == ('', 0), got
    up = name_call(path, seed, '', 0, pressed=R.ACCEPT_MASK, held=R.NAME_UPPER_HELD)
    assert up['name'] == 'A' and up['after'] == lower[:26].upper().encode(), up
    assert up['glyphs'][:26] == lower[:26].encode()
    for key, want in ((0x78, ('abx', 0)), (8, ('a', 0)), (0xD, ('ab', 1)), (0x11, ('ab', 0)),
                      (0x12, ('ab', 0)), (0x1A, ('ab', 0))):
        got = name_call(path, seed, 'ab', 0, key=key)
        assert (got['name'], got['result']) == want, (seed, hex(key), got)
        n += 1
    clear = name_call(path, seed, '', R.CURSOR_DONE, pressed=R.ACCEPT_MASK, warn=1)
    assert (clear['warn'], clear['result']) == (0, 0), clear
    odd = name_call(path, seed, 'ab', -3, pressed=R.ACCEPT_MASK)
    assert (odd['name'], odd['length']) == ('ab', 3), odd   # see the note on cursor -3
    return n + 5 + check_case_release(path, seed, lower)


def check_case_release(path, seed, lower):
    """Two nameEntry_run frames on one machine: held 0x08 upper-cases the 26
    letters, the next frame without it restores lower case."""
    e = emulator(path, seed)
    e.follow = {STRLEN}
    m = e.mem
    scratch = e.alloc(0x158C)
    m.w32(PLAYER_SEL_SCRATCH, scratch)
    run(e, 0x22BC9C)
    m.w32(0x8E2C3C, 0x3F800000)
    m.w8(R.PLAYER_SEL_SLOT, 0)
    m.w8(R.NAME_WARN, 0)
    m.write(R.SEL_ROWS, b'\0')
    m.w32(R.NAME_LENGTH, 0)
    m.w32(R.NAME_CURSOR, 0)
    m.w32(R.NAME_KEY, 0xFFFFFFFF)
    grid = []
    for held in (R.NAME_UPPER_HELD, 0):
        m.w32(0x41BFE0, held)
        m.w32(0x41BFE4, 0)
        m.w32(0x41BFE8, 0)
        run(e, 0x22BE68)
        grid.append(bytes(m.read(scratch + 0x14B4, 26)))
    assert grid == [lower[:26].upper().encode(), lower[:26].encode()], (seed, grid)
    assert m.cstr(R.SEL_ROWS) == '' and m.u32(R.NAME_LENGTH) == 0
    return 1


FIRST_SLOT = 0x4FBBE1
STEP_WORD = 0x8E2BB8


def name_phase(path, seed, result, players, slot, first=0):
    e, scratch = selection(path, seed, R.PHASE_NAME)
    m = e.mem
    m.w32(scratch + 0x14B0, 0x3F000000)
    e.stub(0x22BE68, ret=result & 0xFFFFFFFFFFFFFFFF, name='nameEntry_run')
    m.w8(R.PLAYER_SEL_SLOT, slot)
    m.w8(FIRST_SLOT, first)
    m.w8(R.PLAYER_SEL_PLAYERS, players)
    m.w32(R.POINTS, 7)
    m.w32(STEP_WORD, SENT32)
    run(e, R.PLAYER_SEL_TASK)
    nxt = m.u8(R.NEXT_PHASE)
    return dict(phase=m.u8(R.PLAYER_SEL_PHASE), next=None if nxt == SENT8 else nxt,
                points=m.u32(R.POINTS), fade=m.u32(scratch + 0x14B0),
                step=stores(e, STEP_WORD),
                ctor=calls(e, 0x1B1D70, 0x3278F0, R.PLAYER_SEL_FINISH))


def check_name_phase(path, seed):
    n = 0
    for result in (0, 1, -1):
        for players, slot in ((1, 0), (2, 0), (2, 1), (4, 2), (4, 3)):
            got = name_phase(path, seed, result, players, slot)
            want = R.name_phase_result(result, slot, players)
            assert (got['phase'], got['next']) == want, (seed, result, players, slot, got)
            assert got['ctor'] == [], got               # no record built offline here
            assert got['points'] == (0 if result == -1 else 7), got
            if want[0] == R.PHASE_FINISH_FADE:
                assert got['fade'] == 0, got
            if want[1] == R.PHASE_NEXT_PLAYER:
                assert got['step'] == [(0x2286A4, R.NEXT_PLAYER_STEP)], got
            n += 1
    # "Last" is measured from the first local slot 0x4fbbe1: slot - first = players - 1.
    for slot, first, players in ((2, 1, 2), (1, 1, 2), (3, 2, 2), (2, 2, 2),
                                 (3, 1, 3), (2, 1, 3), (1, 0, 2)):
        got = name_phase(path, seed, 1, players, slot, first)
        want = R.name_phase_result(1, slot - first, players)
        assert (got['phase'], got['next']) == want, (seed, slot, first, players, got)
        n += 1
    return n


def check_level_entry_site(path):
    """The level-entry call site of playerSel_applyPending (instruction word read)."""
    e = EE(path)
    word = e.mem.u32(R.LEVEL_ENTRY_APPLY_SITE)
    assert word == 0x0C000000 | (R.PLAYER_SEL_APPLY_PENDING >> 2), hex(word)
    return 1


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    with open(argv[1], 'rb') as source:
        if hashlib.sha256(source.read()).hexdigest() != SHA256:
            raise SystemExit('REFUSED frontend flow: executable SHA-256 does not match US v2.00')
    total = check_tables(argv[1]) + check_level_entry_site(argv[1])
    for seed in R.SEEDS:
        per = (check_start(argv[1], seed) + check_accepts(argv[1], seed) +
               check_input_rule(argv[1], seed) + check_max_difficulty(argv[1], seed) +
               check_cancels(argv[1], seed) + check_select_entry(argv[1], seed) +
               check_player_sel_start(argv[1], seed) + check_finish(argv[1], seed) +
               check_load(argv[1], seed) + check_stats(argv[1], seed) +
               check_point_pool(argv[1], seed) + check_name(argv[1], seed) +
               check_name_phase(argv[1], seed))
        print('seed %d: %d checks' % (seed, per))
        total += per
    print('PASS frontend flow: pinned US v2.00; %d checks; seeds 20973 and 7' % total)


if __name__ == '__main__':
    main(sys.argv)
