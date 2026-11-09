"""Authored pause-menu contract for the US v2.00 executable (SLUS-20973).

Only resource identifiers, addresses and synthetic input/output values appear here.
Rows whose label is a literal (debug) string rather than a ``menu_*`` lookup key are
recorded as ``None``; the test reads them from the executable at run time and checks
only that they are not lookup keys.  See docs/pause-and-options.md.
"""

# ---- tables: (lookup key or None for a literal debug label, kind, live value address)
# kind 0 = action row, 3 = 0/1 toggle, 4 = float slider, 5 = disabled (drawn, not
# selectable), 8 = comm volume row.  Word +0xc bit 0 hides a row.
MAIN = 0x44F3B8
MAIN_ROWS = (
    ("menu_returntogame", 0, 0),
    ("menu_recall", 0, 0),
    ("menu_loadgame", 0, 0),
    ("menu_levelwarp", 0, 0),      # hidden unless g_debugCheats
    (None, 0, 0),                  # literal debug row: mission/flag editor
    ("menu_option", 0, 0),
    ("menu_kickplayers", 0, 0),    # host only, net game, not a medal mission
    ("menu_exitmission", 0, 0),
    ("menu_exitgame", 0, 0),
)

DEBUG = 0x44F458                   # chosen by pauseMenu_open with cheats + held 0x803
DEBUG_ROWS = (
    ("menu_returntogame", 0, 0),
    ("menu_levelwarp", 0, 0),
    ("menu_invulnerability", 3, 0x44F20C),
    (None, 0, 0),                  # literal debug row: object sweep
)

OPTIONS = 0x44F218                 # rows: tools/ref_options_menu.py ROWS + menu_comm
COMM = 0x44F308
COMM_ROWS = (
    ("menu_commenable", 3, 0x505B00),
    ("menu_commecho", 3, 0x505AFC),
    ("menu_commplay", 4, 0x505AF4),
    ("menu_commthresh", 4, 0x505AF0),
    ("menu_commvolume", 8, 0x505AF8),
)
CONTROLS = 0x44F368                # four placeholder rows rewritten with player names
KICK = 0x44F4A8                    # header row (kind 5) then the other active players
KICK_HEADER = ("menu_chooseplayertokick", 5, 0)
LEVELWARP = 0x44F508               # debug list of level names (not reproduced here)

# ---- sub-menu ids in 0x44fa6c and the table each one shows
SUBMENU_TABLE = {0: MAIN, 1: LEVELWARP, 2: OPTIONS, 3: CONTROLS, 4: KICK, 5: COMM}
SUB_LEAVING_OPTIONS = 0x33         # one-frame state: query the config image

# ---- globals
G = {
    "pause_open": 0x44F208,        # g_pauseMenuOpen (byte)
    "editor": 0x44F210,            # debug editor page active (byte)
    "confirm": 0x44FA68,           # exit confirmation: 0 none, 1 exit mission, 2 exit game
    "sub": 0x44FA6C,
    "table": 0x44FA70,
    "warp_row": 0x44FA74,
    "task_live": 0x44FA78,
    "music_idle": 0x44FA7C,        # frames since the last music-volume change
    "paused_here": 0x44FA80,
    "pad_index": 0x7D8A10,
    "kick_slots": 0x7D8A18,        # byte per kick-list row: player slot
    "paused": 0x41B4F4,            # g_paused
    "lockout": 0x41B4FC,           # g_menuInputLockout
    "exit_code": 0x41B508,         # g_sessionExitCode
    "net_exit": 0x4F6948,          # g_netExitCountdown (s16)
}

# ---- functions
F = {
    "task": 0x18CC08, "close": 0x18DF90, "poll": 0x18E00C, "open": 0x18E334,
    "is_open": 0x18CBFC, "levelwarp_build": 0x18E40C, "debug_sweep": 0x18C7BC,
    "list_input": 0x1A01D0, "list_draw": 0x1A07C4, "list_select": 0x1A076C,
    "send_menu_state": 0x1DE0DC, "send_recall": 0x1DE138, "send_exit_countdown": 0x1DE25C,
    "send_new_world": 0x1D9250, "send_load_level": 0x1DE598,
    "card_request_load": 0x2176E0, "card_request_save": 0x2175B4, "card_state": 0x217550,
    "config_backup": 0x1E6428, "config_commit": 0x1E6650,
    "control_config_open": 0x1E2510, "control_config_run": 0x1E259C,
    "debug_editor": 0x1E31C0, "confirm_box": 0x1DADC0, "message_box": 0x1DF248,
    "kick_peer": 0x131CB8, "pulse": 0x320EA4, "task_add": 0x19E4A0,
    "task_remove": 0x19E664, "music_apply": 0x215E78, "send_volumes": 0x2166E0,
    "music_play": 0x2110E0, "stream_status": 0x211B20, "stream_stop": 0x211338,
    "sound": 0x214230, "frozen": 0x1EBDF8, "text_lookup": 0x173C84,
    "inventory_open": 0x1C15C8,
}

# Accept on a main-menu row: expected (calls by name, {global: value}) after one frame.
# "slot" is replaced by the pad index the menu was opened with.
MAIN_ACCEPT = {
    "menu_returntogame": (("close",), {"lockout": 60}),
    "menu_recall": (("send_recall",), {}),
    "menu_loadgame": (("close", "card_request_load"), {"lockout": 60}),
    "menu_levelwarp": (("pulse", "levelwarp_build"), {"sub": 1, "table": LEVELWARP}),
    None: ((), {"editor": 1}),
    "menu_option": (("config_backup",), {"sub": 2, "table": OPTIONS}),
    "menu_kickplayers": (("pulse",), {"sub": 4, "table": KICK}),
    "menu_exitmission": (("pulse",), {"confirm": 1}),
    "menu_exitgame": (("pulse",), {"confirm": 2}),
}

# Exit confirmation prompt keys (addresses of the lookup keys, not their text).
PROMPT_EXIT_TO_MENU = 0x534968
PROMPT_EXIT_MULTIPLAYER = 0x534978
PROMPT_EXIT_MISSION = 0x534990

# Leaving the options list: (query result, pad edge) -> commit args, or None to stay.
LEAVE_OPTIONS = (
    (0, 0x00, (0, 0, 1)),
    (1, 0x40, (0, 0, 0)),
    (1, 0x20, (0, 0, 1)),
    (1, 0x00, None),
)

# The HUD's inventory button (run task hud_run 0x1db870): edge bit in the raw pad's
# pressed word (g_rawPads 0x4028d0 + 0x58 * slot, +0xc), blocked while this bit is down
# in the held word (+0x8).
INVENTORY_EDGE = 0x100
INVENTORY_BLOCK_HELD = 0x80
PAUSE_EDGE = 0x800                 # lockstep pad edge (0x41bfe4 + 0x58 * slot)

# ---- minimap (minimap_draw 0x1e42e0, minimap_applyMode 0x1e3ff0)
MINIMAP_DRAW = 0x1E42E0
MINIMAP_MODE = 0x4F8400            # g_minimapMode, cycled 0 -> 1 -> 2 -> 0 by the map button
MINIMAP_ZOOM = 0x4F71A0            # float, clamped to [0.5, 2.0] while the button is held
MAP_BUTTON_MASKS = 0x41B9E0        # configured map-button mask per local slot
MINIMAP_CURRENT = 0x86AF58         # scale, x, y, half-width, half-height (chased floats)
# Targets by player count (1, or 2 and more) and mode: (scale, x, y, half-width,
# half-height).  Mode 0 is the centred big map; mode 1 the corner map; mode 2 hidden.
MINIMAP_MODES = {
    1: {0: (0.9, 0.0, 0.0, 320.0, 224.0), 1: (0.7, 200.0, -120.0, 120.0, 100.0),
        2: (0.0, 180.0, -120.0, 0.0, 0.0)},
    2: {0: (0.9, 0.0, 0.0, 320.0, 224.0), 1: (0.7, -240.0, 140.0, 120.0, 100.0),
        2: (0.0, -240.0, 140.0, 0.0, 0.0)},
}
