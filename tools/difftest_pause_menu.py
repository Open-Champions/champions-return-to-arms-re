#!/usr/bin/env python3
"""Execute the original pause menu in ee_emu (SLUS-20973 v2.00); no game bytes are written.

Runs pauseMenu_open 0x18e334, pauseMenu_close 0x18df90, the start-button poll (run
task `warpMenu`) 0x18e00c and one frame of pauseMenu_task 0x18cc08 on authored state,
with the menu-list handler 0x1a01d0, menuList_setSelection 0x1a076c, strcmp and strstr
followed and every other callee replaced by a recorded stub (disclosed in STUBS below
and in docs/pause-and-options.md).  The executable is pinned by SHA-256.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402
import ref_pause_menu as R  # noqa: E402
from ref_options_menu import ROWS as OPTION_ROWS  # noqa: E402

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SEEDS = (20973, 7)
F, G = R.F, R.G
M32 = 0xFFFFFFFF

RAW_PADS, PAD_STRIDE = 0x4028D0, 0x58      # g_rawPads: what the pause task reads
SIM_PADS = 0x41BFD8                         # lockstep pads: what the start poll reads
RECORDS, RECORD_STRIDE = 0x4D8AF0, 0x4C30   # g_players
NUM_PLAYERS = 0x4D8AE0
NET_MODE, DEBUG_CHEATS = 0x402791, 0x4F8EE0
LEVEL_NAME = 0x44FE18
LOCAL_CAMERA = 0x4F8450
PVP_B, MEDAL = 0x4F7120, 0x4F713C
CUTSCENE = 0x44FCD0
SEED_WORDS = (0x404460, 0x404464)
HUB_NEEDLE = 0x534330      # the substring the task looks for in the level name
TASK_NAME = 0x534AF8

FOLLOW = {F["task"], 0x3B8534, 0x3B96A8, F["list_select"], F["list_input"]}
# Recorded stubs with non-default results (all other callees return 0):
# net_isSlotActive 0x13dd40 returns slot < players (a function stub).
STUBS = {
    F["card_state"]: -1,           # memcard_getState: no card screen
    0x13D668: 1,                   # net_localIsFirstActive
    0x13E5A0: 0,                   # net_firstActiveSlot
    0x13E150: 1,                   # net_isLocalSlot
}


def name_of(address):
    for key, value in F.items():
        if value == address:
            return key
    return hex(address)


class Fixture:
    def __init__(self, path, seed, net=0, debug=0, pad=1, players=1, level=b"lvl1",
                 stubs=None):
        ee = self.ee = EE(path)
        ee.mem.auto_map = True
        ee.follow = set(FOLLOW)
        self.seed = seed
        for word in SEED_WORDS:
            ee.mem.w32(word, seed)
        ee.mem.w8(NET_MODE, net)
        ee.mem.w8(DEBUG_CHEATS, debug)
        ee.mem.w32(0x41BFBC, 0x40)   # confirm mask (cross set; game_initCamera byte 1)
        ee.mem.w32(0x41BFB8, 0x20)   # cancel mask
        merged = dict(STUBS)
        merged[0x13E1F0] = pad       # net_getLocalPlayerSlot
        merged.update(stubs or {})
        for address, ret in merged.items():
            ee.stub(address, ret=ret)
        if 0x13DD40 not in merged:   # net_isSlotActive: slot < player count
            ee.stub(0x13DD40, function=lambda e: int((e.r[4] & M32) < players))
        ee.mem.w32(G["table"], R.MAIN)
        ee.mem.w32(G["sub"], 0)
        ee.mem.w8(G["confirm"], 0)
        ee.mem.w32(G["pad_index"], pad)
        ee.mem.w32(NUM_PLAYERS, players)
        for slot in range(4):
            ee.mem.w32(RECORDS + slot * RECORD_STRIDE + 0xAC, 0x3F800000)  # 1.0 hp
        camera = ee.alloc(0x100)
        ee.mem.w32(LOCAL_CAMERA, camera)
        ee.mem.w32(camera + 0x34, 1)                                       # follow mode
        self.camera = camera
        self.set_level(level)
        self.pad = pad

    def set_level(self, name):
        for index, byte in enumerate(name + b"\0"):
            self.ee.mem.w8(LEVEL_NAME + index, byte)

    def select(self, table, rows, row):
        self.ee.mem.w32(table + 16 * rows + 4, row)

    def raw(self, offset, mask):
        self.ee.mem.w32(RAW_PADS + PAD_STRIDE * self.pad + offset, mask)

    def frame(self):
        ee = self.ee
        ee.reset_log()
        ee.call(F["task"], max_steps=600000)
        for word in SEED_WORDS:
            assert ee.mem.u32(word) == self.seed, "pause task wrote the shared seed"
        return ee.calls

    def actions(self, low=0x18D8C8, high=0x18DE50):
        names = {F[k] for k in ("close", "send_recall", "card_request_load",
                                "card_request_save", "pulse", "levelwarp_build",
                                "config_backup", "kick_peer", "send_new_world",
                                "send_load_level", "control_config_open", "debug_sweep")}
        names.add(0x1C7AF8)  # shop_openOrStock (literal debug row only)
        return [c for c in self.ee.calls if low <= c.site < high and c.target in names]


def rows_state(ee, table, count):
    return [(ee.mem.u32(table + 16 * i + 4), ee.mem.u32(table + 16 * i + 12) & 1)
            for i in range(count)]


def check_tables(path, seed):
    ee = Fixture(path, seed).ee
    count = 0
    for table, rows in ((R.MAIN, R.MAIN_ROWS), (R.DEBUG, R.DEBUG_ROWS),
                        (R.COMM, R.COMM_ROWS)):
        for index, (key, kind, value) in enumerate(rows):
            record = table + 16 * index
            text = ee.mem.cstr(ee.mem.u32(record))
            if key is None:
                assert not text.startswith("menu_"), hex(record)
            else:
                assert text == key, (hex(record), key)
            assert ee.mem.u32(record + 4) == kind and ee.mem.u32(record + 8) == value
            count += 1
        assert ee.mem.u32(table + 16 * len(rows)) == 0  # terminator
        count += 1
    for index, (key, kind, address) in enumerate(OPTION_ROWS):
        assert ee.mem.cstr(ee.mem.u32(R.OPTIONS + 16 * index)) == key
    assert ee.mem.cstr(ee.mem.u32(R.OPTIONS + 16 * 13)) == "menu_comm"
    key, kind, value = R.KICK_HEADER
    assert ee.mem.cstr(ee.mem.u32(R.KICK)) == key and ee.mem.u32(R.KICK + 4) == kind
    for index in range(4):   # four placeholder controller rows, then a terminator
        assert ee.mem.u32(R.CONTROLS + 16 * index) != 0
        assert ee.mem.u32(R.CONTROLS + 16 * index + 4) == 0
    assert ee.mem.u32(R.CONTROLS + 64) == 0
    # The main menu's string compare against menu_savegame: no main or debug row has it.
    keys = {ee.mem.cstr(ee.mem.u32(R.MAIN + 16 * i)) for i in range(len(R.MAIN_ROWS))}
    assert "menu_savegame" not in keys
    return count + 4


def check_open_close(path, seed):
    count = 0
    for net, debug, held, table in ((0, 0, 0, R.MAIN), (1, 0, 0, R.MAIN),
                                    (0, 1, 0x803, R.DEBUG), (0, 1, 0x800, R.MAIN),
                                    (0, 0, 0x803, R.MAIN)):
        fx = Fixture(path, seed, net=net, debug=debug)
        ee = fx.ee
        ee.mem.w32(SIM_PADS + 8, held)
        ee.mem.w32(G["sub"], 7)
        ee.reset_log()
        ee.call(F["open"], 1, max_steps=100000)
        m = ee.mem
        assert m.u32(G["pad_index"]) == 1 and m.u32(G["table"]) == table
        assert m.u32(G["sub"]) == 0 and m.u8(G["pause_open"]) == 1
        assert m.u8(G["task_live"]) == 1
        assert m.u32(G["paused"]) == (0 if net else 1)
        assert m.u8(G["paused_here"]) == (0 if net else 1)
        calls = [(c.target, tuple(a & M32 for a in c.args[:4])) for c in ee.calls]
        assert calls[0] == (F["send_menu_state"], (1, 1, 0, calls[0][1][3]))
        assert (F["list_select"], (table, 0)) in [(t, a[:2]) for t, a in calls]
        assert (F["pulse"], 0) in [(t, a[0]) for t, a in calls]
        assert (F["task_add"], (F["task"], 0x34, TASK_NAME, 1)) in calls
        assert [t for t, _ in calls] == [F["send_menu_state"], F["list_select"],
                                         F["pulse"], F["task_add"]]   # nothing else
        count += 10

        # Close: offline it clears the pause flag; online it leaves it alone.
        ee.mem.w32(G["paused"], 1)
        ee.mem.w8(G["confirm"], 2)
        ee.reset_log()
        ee.call(F["close"], max_steps=100000)
        assert m.u8(G["pause_open"]) == 0 and m.u8(G["confirm"]) == 0
        assert m.u8(G["task_live"]) == 0
        assert m.u32(G["paused"]) == (1 if net else 0)
        targets = [(c.target, tuple(a & M32 for a in c.args[:3])) for c in ee.calls]
        assert targets == [(0x13E1F0, targets[0][1]),
                           (F["send_menu_state"], (1, 0, 0)),
                           (F["task_remove"], (F["task"], targets[2][1][1],
                                               targets[2][1][2]))], targets
        count += 4
        # A second close is a no-op.
        ee.reset_log()
        ee.call(F["close"], max_steps=100000)
        assert ee.calls == [] and m.u32(G["paused"]) == (1 if net else 0)
        count += 1
    return count


def visibility(path, seed, **kw):
    stubs = kw.pop("stubs", {})
    alive = kw.pop("alive", True)
    camera_mode = kw.pop("camera_mode", 1)
    pvp = kw.pop("pvp", 0)
    hub = kw.pop("hub", False)
    fx = Fixture(path, seed, stubs=stubs, **kw)
    ee = fx.ee
    if hub:
        fx.set_level(ee.mem.cstr(HUB_NEEDLE).encode() + b"_x")
    if not alive:
        for slot in range(4):
            ee.mem.w32(RECORDS + slot * RECORD_STRIDE + 0xAC, 0)
    ee.mem.w32(fx.camera + 0x34, camera_mode)
    ee.mem.w32(PVP_B, pvp)
    fx.frame()
    return rows_state(ee, R.MAIN, len(R.MAIN_ROWS))


# Each case: fixture options -> {row: (kind, hidden)} for the rows that differ from
# "kind 0, shown".  Rows: 0 return, 1 recall, 2 load, 3 warp, 4 editor, 5 options,
# 6 kick, 7 exit mission, 8 exit game.
VISIBILITY = (
    ({}, {3: (0, 1), 4: (0, 1), 6: (0, 1)}),
    ({"debug": 1}, {6: (0, 1)}),
    ({"hub": True}, {3: (0, 1), 4: (0, 1), 6: (0, 1), 7: (0, 1)}),
    ({"net": 1, "players": 2}, {2: (5, 0), 3: (0, 1), 4: (0, 1)}),
    ({"net": 1, "players": 1}, {2: (5, 0), 3: (0, 1), 4: (0, 1), 6: (0, 1)}),
    ({"net": 1, "players": 2, "stubs": {0x13D668: 0}},
     {2: (5, 0), 3: (0, 1), 4: (0, 1), 6: (0, 1), 7: (0, 1)}),
    ({"stubs": {0x22FBC0: 1}}, {1: (5, 0), 3: (0, 1), 4: (0, 1), 6: (0, 1), 7: (5, 0)}),
    ({"camera_mode": 2}, {1: (5, 0), 3: (0, 1), 4: (0, 1), 6: (0, 1)}),
    ({"alive": False}, {3: (0, 1), 4: (0, 1), 6: (0, 1), 7: (0, 1)}),
    ({"net": 1, "players": 2, "alive": False},
     {1: (5, 0), 2: (5, 0), 3: (0, 1), 4: (0, 1), 7: (0, 1)}),
    ({"pvp": 1}, {1: (0, 1), 2: (5, 0), 3: (0, 1), 4: (0, 1), 6: (0, 1), 7: (0, 1)}),
    ({"stubs": {0x19E5E8: 1}}, {1: (5, 1), 3: (0, 1), 4: (0, 1), 6: (0, 1)}),
)


def check_visibility(path, seed):
    count = 0
    for options, differ in VISIBILITY:
        state = visibility(path, seed, **dict(options))
        expected = [differ.get(i, (0, 0)) for i in range(len(R.MAIN_ROWS))]
        assert state == expected, (options, state)
        count += 1
    return count


def accept_row(path, seed, row, **kw):
    fx = Fixture(path, seed, **kw)
    fx.select(R.MAIN, len(R.MAIN_ROWS), row)
    fx.raw(0xC, 0x40)
    fx.frame()
    return fx


def check_main_accept(path, seed):
    count = 0
    for row, (key, _, _) in enumerate(R.MAIN_ROWS):
        kw = {}
        if row in (3, 4):
            kw = {"debug": 1}
        if key == "menu_kickplayers":
            kw = {"net": 1, "players": 2}
        fx = accept_row(path, seed, row, **kw)
        ee = fx.ee
        calls, values = R.MAIN_ACCEPT[key]
        acts = fx.actions()
        assert tuple(name_of(c.target) for c in acts) == calls, (key, acts)
        for name, value in values.items():
            got = ee.mem.u8(G[name]) if name in ("confirm", "editor") else ee.mem.u32(G[name])
            assert got == value, (key, name, got)
        if key == "menu_recall":
            assert acts[0].args[0] & 0xFF == fx.pad
        if key == "menu_loadgame":
            assert tuple(a & M32 for a in acts[1].args[:2]) == (fx.pad, 1)
        if key == "menu_option":
            assert ee.mem.u32(G["lockout"]) == 0
        if key == "menu_kickplayers":
            # Kick list: header, then every other active slot, cursor on row 1.
            assert ee.mem.u32(R.KICK + 16) == RECORDS + RECORD_STRIDE
            assert ee.mem.u8(G["kick_slots"] + 1) == 1 and ee.mem.u32(R.KICK + 32) == 0
            assert ee.mem.u32(R.KICK + 32 + 4) == 0x101  # (row | row << 8)
        count += 2
    # A cursor left on a hidden (kick, offline) or disabled (recall, camera not in
    # follow mode) row is moved by the list handler before the accept is dispatched.
    for row, kw in ((6, {}), (1, {"camera_mode": 2})):
        camera_mode = kw.pop("camera_mode", 1)
        fx = Fixture(path, seed, **kw)
        fx.ee.mem.w32(fx.camera + 0x34, camera_mode)
        fx.select(R.MAIN, len(R.MAIN_ROWS), row)
        fx.raw(0xC, 0x40)
        fx.frame()
        assert [name_of(c.target) for c in fx.actions()] == ["close"], row
        assert fx.ee.mem.u32(R.MAIN + 16 * len(R.MAIN_ROWS) + 4) & 0xFF == 0
        count += 1
    # Debug table, literal sweep row and invulnerability toggle.
    fx = Fixture(path, seed, debug=1)
    ee = fx.ee
    ee.mem.w32(G["table"], R.DEBUG)
    fx.select(R.DEBUG, len(R.DEBUG_ROWS), 3)
    fx.raw(0xC, 0x40)
    fx.frame()
    assert [name_of(c.target) for c in fx.actions()] == ["debug_sweep"]
    fx = Fixture(path, seed, debug=1)
    ee = fx.ee
    ee.mem.w32(G["table"], R.DEBUG)
    ee.mem.w32(0x44F20C, 0)
    fx.select(R.DEBUG, len(R.DEBUG_ROWS), 2)
    fx.raw(0x10, 0x40)
    fx.frame()
    assert ee.mem.u32(0x44F20C) == 1
    # Editor page: while its flag is set the task only runs the editor; the flag
    # becomes the editor's return value inverted.
    for ret, flag in ((0, 1), (1, 0)):
        fx = Fixture(path, seed, debug=1, stubs={F["debug_editor"]: ret})
        fx.ee.mem.w8(G["editor"], 1)
        calls = fx.frame()
        assert [c.target for c in calls if c.target == F["debug_editor"]] == [F["debug_editor"]]
        assert not any(c.target == F["list_draw"] for c in calls)
        assert fx.ee.mem.u8(G["editor"]) == flag
    return count + 4


CONFIRMS = (
    # (confirm, options, box result, prompt key, expected)
    (2, {}, 2, R.PROMPT_EXIT_TO_MENU, {"exit_code": 1, "close": 1}),
    (2, {"net": 1}, 2, R.PROMPT_EXIT_TO_MENU, {"net_exit": 30, "close": 1}),
    (1, {"pad": 0}, 2, R.PROMPT_EXIT_MISSION, {"countdown": 1, "close": 1}),
    (1, {"pad": 0, "hub": True}, 2, R.PROMPT_EXIT_TO_MENU, {"exit_code": 1, "close": 1}),
    (1, {"pad": 1}, 2, R.PROMPT_EXIT_TO_MENU, {"exit_code": 1, "close": 1}),
    (1, {"pad": 1, "net": 1}, 2, R.PROMPT_EXIT_MULTIPLAYER, {"net_exit": 30, "close": 1}),
    (2, {}, 1, R.PROMPT_EXIT_TO_MENU, {"confirm": 0}),
    (1, {"pad": 0}, 0, R.PROMPT_EXIT_MISSION, {"confirm": 1}),
)


def check_confirm(path, seed):
    count = 0
    for confirm, options, result, prompt, expected in CONFIRMS:
        options = dict(options)
        hub = options.pop("hub", False)
        fx = Fixture(path, seed, stubs={F["confirm_box"]: result}, **options)
        ee = fx.ee
        if hub:
            fx.set_level(ee.mem.cstr(HUB_NEEDLE).encode())
        ee.mem.w8(G["confirm"], confirm)
        ee.mem.w8(G["task_live"], 1)
        calls = fx.frame()
        lookups = [c.args[0] & M32 for c in calls if c.target == F["text_lookup"]]
        assert lookups[0] == prompt, (confirm, options, hex(lookups[0]))
        boxes = [c for c in calls if c.target == F["confirm_box"]]
        assert len(boxes) == 1
        closes = sum(c.target == F["close"] for c in calls)
        assert closes == expected.get("close", 0)
        assert sum(c.target == F["send_exit_countdown"] for c in calls) == \
            expected.get("countdown", 0)
        assert ee.mem.u32(G["exit_code"]) == expected.get("exit_code", 0)
        assert ee.mem.u16(G["net_exit"]) == expected.get("net_exit", 0)
        if "confirm" in expected:
            assert ee.mem.u8(G["confirm"]) == expected["confirm"]
        assert not any(c.target == F["list_draw"] for c in calls)
        count += 1
    return count


def sub_frame(path, seed, sub, table, row=None, rows=None, edge=0, **kw):
    fx = Fixture(path, seed, **kw)
    ee = fx.ee
    ee.mem.w32(G["sub"], sub)
    ee.mem.w32(G["table"], table)
    if row is not None:
        fx.select(table, rows, row)
    if edge:
        fx.raw(0xC, edge)
    fx.frame()
    return fx


def check_submenus(path, seed):
    count = 0
    m = None
    # Options: the two action rows open their own lists.
    for row, sub, table in ((3, 3, R.CONTROLS), (13, 5, R.COMM)):
        fx = sub_frame(path, seed, 2, R.OPTIONS, row, 14, 0x40)
        m = fx.ee.mem
        assert (m.u32(G["sub"]), m.u32(G["table"])) == (sub, table)
        count += 1
    # The controller list is rebuilt every frame with one row per player.
    fx = sub_frame(path, seed, 3, R.CONTROLS, 1, 2, 0x40, players=2)
    m = fx.ee.mem
    fits = [c for c in fx.ee.calls if c.target == 0x1BDF60]
    assert [c.args[1] & M32 for c in fits] == [0, 1]
    assert m.u32(R.CONTROLS) == 0x4F3EC8 and m.u32(R.CONTROLS + 16) == 0x4F3EE8
    assert m.u32(R.CONTROLS + 32) == 0
    opens = [c.args[0] & M32 for c in fx.ee.calls if c.target == F["control_config_open"]]
    assert opens == [1]
    count += 3
    # Cancel from every sub-menu.
    for sub, table, rows, after in ((3, R.CONTROLS, 4, (2, R.OPTIONS)),
                                    (5, R.COMM, 5, (2, R.OPTIONS)),
                                    (2, R.OPTIONS, 14, (R.SUB_LEAVING_OPTIONS, R.OPTIONS)),
                                    (4, R.KICK, 1, (0, R.MAIN)),
                                    (1, R.LEVELWARP, 1, (0, R.MAIN))):
        fx = sub_frame(path, seed, sub, table, 0, rows, 0x20, players=4)
        m = fx.ee.mem
        assert (m.u32(G["sub"]), m.u32(G["table"])) == after, (sub, hex(m.u32(G["table"])))
        assert not any(c.target == F["close"] for c in fx.ee.calls)
        count += 1
    fx = sub_frame(path, seed, 0, R.MAIN, 0, 9, 0x20)
    assert sum(c.target == F["close"] for c in fx.ee.calls) == 1
    assert fx.ee.mem.u32(G["lockout"]) == 60
    count += 1
    # Leaving options: query, then commit with or without the card save.
    for queried, edge, commit in R.LEAVE_OPTIONS:
        fx = Fixture(path, seed, stubs={F["config_commit"]: queried})
        ee = fx.ee
        ee.mem.w32(G["sub"], R.SUB_LEAVING_OPTIONS)
        ee.mem.w32(G["table"], R.OPTIONS)
        fx.raw(0xC, edge)
        calls = fx.frame()
        commits = [tuple(a & M32 for a in c.args[:3]) for c in calls
                   if c.target == F["config_commit"]]
        boxes = sum(c.target == F["message_box"] for c in calls)
        if commit is None:
            assert commits == [(0, 1, 0)] and boxes == 1
            assert ee.mem.u32(G["sub"]) == R.SUB_LEAVING_OPTIONS
        else:
            assert commits == [(0, 1, 0), commit], commits
            assert boxes == queried
            assert (ee.mem.u32(G["sub"]), ee.mem.u32(G["table"])) == (0, R.MAIN)
        count += 1
    # Kick list: accept kicks the slot recorded for that row and closes the menu.
    fx = Fixture(path, seed, net=1, players=3)
    ee = fx.ee
    ee.mem.w32(G["sub"], 4)
    ee.mem.w32(G["table"], R.KICK)
    ee.mem.w32(R.KICK + 16, RECORDS + RECORD_STRIDE)
    ee.mem.w32(R.KICK + 32, RECORDS + 2 * RECORD_STRIDE)
    ee.mem.w32(R.KICK + 48, 0)
    ee.mem.w8(G["kick_slots"] + 1, 1)
    ee.mem.w8(G["kick_slots"] + 2, 2)
    fx.select(R.KICK, 3, 2)
    fx.raw(0xC, 0x40)
    fx.frame()
    acts = fx.actions(0x18DE00, 0x18DE20)
    assert [name_of(c.target) for c in acts] == ["kick_peer", "close"]
    assert acts[0].args[0] & 0xFF == 2       # the slot byte recorded for row 2
    count += 1
    # Level warp (debug): offline sends message 11, online message 7; row remembered.
    for net, sender in ((0, "send_load_level"), (1, "send_new_world")):
        fx = Fixture(path, seed, net=net, debug=1)
        ee = fx.ee
        ee.mem.w32(G["sub"], 1)
        ee.mem.w32(G["table"], R.LEVELWARP)
        fx.select(R.LEVELWARP, 3, 2)
        ee.mem.w32(R.LEVELWARP + 48, 0)
        fx.raw(0xC, 0x40)
        fx.frame()
        acts = fx.actions(0x18DCE0, 0x18DD80)
        assert [(name_of(c.target), c.args[0] & M32) for c in acts] == \
            [(sender, ee.mem.u32(R.LEVELWARP + 32))]
        assert ee.mem.u32(G["warp_row"]) == 2
        count += 1
    # ... but not during a cutscene.
    fx = Fixture(path, seed, debug=1)
    ee = fx.ee
    ee.mem.w32(G["sub"], 1)
    ee.mem.w32(G["table"], R.LEVELWARP)
    fx.select(R.LEVELWARP, 3, 0)
    ee.mem.w32(R.LEVELWARP + 48, 0)
    ee.mem.w8(CUTSCENE, 1)
    fx.raw(0xC, 0x40)
    fx.frame()
    assert fx.actions(0x18DCE0, 0x18DD80) == []
    return count + 1


def check_audio_preview(path, seed):
    count = 0
    # Every frame of the open menu pushes the live volumes to the IOP.
    fx = Fixture(path, seed)
    calls = fx.frame()
    order = [c.target for c in calls if c.target in (F["music_apply"], F["send_volumes"])]
    assert order == [F["music_apply"], F["send_volumes"]]
    count += 1
    # Music slider: preview music starts when stream 2 is idle; idle counter reset.
    for status, plays in ((0, 1), (0x20, 0)):
        fx = Fixture(path, seed, stubs={F["stream_status"]: status})
        ee = fx.ee
        ee.mem.w32(G["table"], R.OPTIONS)
        ee.mem.w32(G["sub"], 2)
        ee.mem.w32(G["music_idle"], 100)
        ee.mem.w32(0x4F8944, 0x3F000000)
        fx.select(R.OPTIONS, 14, 1)
        fx.raw(8, 0x2000)
        calls = fx.frame()
        music = [(c.args[0] & M32, c.args[1] & M32) for c in calls
                 if c.target == F["music_play"]]
        assert music == [(0x534A60, 0x41)] * plays, music
        assert ee.mem.u32(G["music_idle"]) == 1
        count += 1
    # After 240 idle frames the preview stream is stopped if it is still playing.
    for status, stops in ((0x40, 1), (0, 0)):
        fx = Fixture(path, seed, stubs={F["stream_status"]: status})
        ee = fx.ee
        ee.mem.w32(G["music_idle"], 240)
        calls = fx.frame()
        assert ee.mem.u32(G["music_idle"]) == 241
        assert sum(c.target == F["stream_stop"] for c in calls) == stops
        count += 1
    # Effects slider: a sample plays on frames where frame & 7 == 0.
    for frame, plays in ((8, 1), (9, 0)):
        fx = Fixture(path, seed)
        ee = fx.ee
        ee.mem.w32(G["table"], R.OPTIONS)
        ee.mem.w32(G["sub"], 2)
        ee.mem.w32(0x4F8940, 0x3F000000)
        ee.mem.w32(0x44FDD0, frame)
        fx.select(R.OPTIONS, 14, 2)
        fx.raw(8, 0x2000)
        calls = fx.frame()
        sounds = [c for c in calls if c.target == F["sound"] and 0x18D700 < c.site < 0x18D780]
        assert len(sounds) == plays and ee.mem.u32(0x4F8940) != 0x3F000000
        count += 1
    # Triangle in the options list calls 0x222b10.
    for table, calls_it in ((R.OPTIONS, 1), (R.MAIN, 0)):
        fx = Fixture(path, seed)
        fx.ee.mem.w32(G["table"], table)
        fx.ee.mem.w32(G["sub"], 2 if table == R.OPTIONS else 0)
        fx.raw(0xC, 0x10)
        calls = fx.frame()
        assert sum(c.target == 0x222B10 for c in calls) == calls_it
        count += 1
    return count


def poll(path, seed, start=True, open_=False, table=R.MAIN, stubs=None, alive=True,
         net=0):
    fx = Fixture(path, seed, pad=0, net=net, stubs=stubs)
    ee = fx.ee
    ee.follow = {F["poll"]}
    ee.mem.w32(0x44FDA4, 100000)       # display-list head room above the 3000 gate
    ee.mem.w8(G["pause_open"], 1 if open_ else 0)
    ee.mem.w32(G["table"], table)
    if not alive:
        ee.mem.w32(RECORDS + 0xAC, 0)
    ee.mem.w32(SIM_PADS + 0xC, R.PAUSE_EDGE if start else 0)
    ee.reset_log()
    ee.call(F["poll"], max_steps=200000)
    calls = [(name_of(c.target), tuple(a & M32 for a in c.args[:3])) for c in ee.calls
             if c.target in (F["open"], F["close"], F["config_commit"])]
    return ee.mem.u8(G["pause_open"]), calls


def check_poll(path, seed):
    cases = (
        ({}, (1, [("open", (0,))])),
        ({"net": 1}, (1, [("open", (0,))])),
        ({"open_": True}, (0, [("close", ()), ("config_commit", (0, 0, 0))])),
        ({"open_": True, "table": R.OPTIONS}, (1, [])),
        ({"start": False}, (0, [])),
        ({"stubs": {F["frozen"]: 1}}, (0, [])),
        ({"stubs": {F["frozen"]: 1}, "open_": True},
         (0, [("close", ()), ("config_commit", (0, 0, 0))])),
        ({"alive": False}, (0, [])),
        ({"alive": False, "net": 1}, (1, [("open", (0,))])),
        ({"stubs": {0x217518: 1}}, (0, [])),
        ({"stubs": {0x13E150: 0}}, (0, [])),
        ({"stubs": {0x22FBC0: 1}}, (0, [])),
    )
    count = 0
    for options, (state, calls) in cases:
        got_state, got = poll(path, seed, **dict(options))
        got = [(n, a[:1] if n == "open" else (a if n == "config_commit" else ()))
               for n, a in got]
        assert (got_state, got) == (state, calls), (options, got_state, got)
        count += 1
    return count


def check_frozen(path, seed):
    """game_isFrozen 0x1ebdf8: the gate runObjects and the poll consult."""
    count = 0
    for net in (0, 1):
        for paused in (0, 1):
            fx = Fixture(path, seed, net=net)
            ee = fx.ee
            ee.follow = {F["frozen"]}
            ee.mem.w32(G["paused"], paused)
            ee.reads = []
            assert ee.call(F["frozen"], max_steps=10000) & 1 == paused
            count += 1
    return count


def hud_inventory(path, seed, edge=R.INVENTORY_EDGE, held=0, levels=(1, 1), stubs=None):
    fx = Fixture(path, seed, pad=0, stubs=stubs)
    ee = fx.ee
    ee.follow = {0x1DB870}                       # hud_run, the HUD run task
    ee.mem.w32(RAW_PADS + 0xC, edge)
    ee.mem.w32(RAW_PADS + 8, held)
    ee.mem.w8(RECORDS + 0x58, levels[0])         # acknowledged level
    ee.mem.w8(RECORDS + 0x59, levels[1])         # earned level
    ee.mem.w32(RECORDS + 0x43D8, ee.alloc(0x600))  # player object, flags clear
    ee.reset_log()
    ee.call(0x1DB870, max_steps=400000)
    return [tuple(a & M32 for a in c.args[:2]) for c in ee.calls
            if c.target == F["inventory_open"]]


def check_inventory(path, seed):
    count = 0
    cases = (
        ({}, [(0, 0)]),
        ({"levels": (1, 2)}, [(0, 1)]),          # level-up pending: open on that page
        ({"held": R.INVENTORY_BLOCK_HELD}, []),
        ({"edge": 0}, []),
        ({"stubs": {F["is_open"]: 1}}, []),      # pause menu open
        ({"stubs": {F["frozen"]: 1}}, []),       # game frozen (offline pause)
    )
    for options, expected in cases:
        assert hud_inventory(path, seed, **dict(options)) == expected, options
        count += 1
    # menu_openInventory: local menu flag, pause flag offline only, two tasks.
    for net in (0, 1):
        for mode in (0, 1):
            fx = Fixture(path, seed, pad=0, net=net)
            ee = fx.ee
            ee.follow = {F["inventory_open"]}
            ee.mem.w32(G["paused"], 0)
            ee.mem.w8(RECORDS + 0xED, 0x77)
            ee.reset_log()
            ee.call(F["inventory_open"], 0, mode, max_steps=200000)
            assert ee.mem.u8(0x41B69D) == 1                   # g_localMenuOpen
            assert ee.mem.u32(G["paused"]) == (0 if net else 1)
            assert ee.mem.u32(RECORDS + 0x4A58) == 0
            assert ee.mem.u8(RECORDS + 0xED) == (0 if mode else 0x77)
            calls = [(c.target, tuple(a & M32 for a in c.args[:4])) for c in ee.calls]
            assert (F["send_menu_state"], 0, 1, 0) in [(t,) + a[:3] for t, a in calls]
            tasks = [a for t, a in calls if t == F["task_add"]]
            assert [(a[0], a[1], a[3]) for a in tasks] == [(0x1C56A8, 0x32, 1),
                                                           (0x1C1108, 0x32, 1)]
            sends = [t for t, a in calls if t == 0x13DB38]   # net_sendGameMsg
            assert len(sends) == mode
            count += 1
    # inventory_close 0x1c52dc (symbol name from docs/issues/draw-sim-leaks.md): clears
    # g_paused with no network test (docs/ui.md P3).
    for net in (0, 1):
        fx = Fixture(path, seed, pad=0, net=net)
        ee = fx.ee
        ee.follow = {0x1C52DC}
        ee.mem.w32(G["paused"], 1)
        ee.reset_log()
        ee.call(0x1C52DC, max_steps=200000)
        assert ee.mem.u32(G["paused"]) == 0
        assert [pc for pc, a, _, _ in ee.writes if a == G["paused"]] == [0x1C530C]
        count += 1
    return count


def check_card_options(path, seed):
    """Triangle in the options list: 0x222b10 hands over to card state 10."""
    fx = Fixture(path, seed, pad=0)
    ee = fx.ee
    ee.follow = {0x222B10}
    ee.mem.w32(0x88D3E4, 5)
    ee.reset_log()
    ee.call(0x222B10, max_steps=10000)
    calls = [(c.target, c.args[0] & M32) for c in ee.calls]
    assert calls == [(0x21E614, calls[0][1]), (0x21F238, 10)], calls
    assert ee.mem.u32(0x88D3E4) == 0
    # The card dispatcher 0x2189e0 sends state 10 to memcard_optionsScreen 0x222b40.
    assert ee.mem.u32(0x53F090 + 4 * 10) == 0x218AC8
    return 3


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: difftest_pause_menu.py path/to/SLUS_209.73")
    path = sys.argv[1]
    with open(path, "rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == SHA256
    for seed in SEEDS:
        total = 0
        for check in (check_tables, check_open_close, check_visibility,
                      check_main_accept, check_confirm, check_submenus,
                      check_audio_preview, check_poll, check_frozen,
                      check_inventory, check_card_options):
            n = check(path, seed)
            print("seed %d: %-20s %3d checks passed" % (seed, check.__name__, n))
            total += n
        print("seed %d: %d pause-menu checks passed" % (seed, total))


if __name__ == "__main__":
    main()
