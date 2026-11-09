"""Numeric reference for the original front-end flow, SLUS-20973 US v2.00.

Boot -> main menu -> new game setup -> character selection -> first level
request, and main menu -> load screen.  Every value here is an address, a
state number, a row index or a small integer.  No lookup key, localized
string, level identifier or other game text is stored; tests that need a
string compare it with the pinned executable's own bytes at run time.

`tools/difftest_frontend_flow.py` executes the original functions in
`tools/ee_emu.py` and checks them against the functions below.
"""

SEEDS = (20973, 7)

# Front-end task and its two state words.
FRONTEND_RUN = 0x1E08F0
FRONTEND_START = 0x1E1F34
FRONTEND_STOP = 0x1E2168
FRONTEND_START_PLAYER_SELECT = 0x1E3BA0
FRONTEND_MAIN_TABLE_FN = 0x1E318C
STATE = 0x4F6B78
MENU = 0x4F6B7C
FIRST_ENTRY = 0x4F6B70        # 1 until the first frontend_run pass
THEME_REQUESTED = 0x4F7024
TASK_PRIORITY = 25

# Setup globals written by the accept handlers.
NUM_PLAYERS = 0x4D8AE0
DIFFICULTY = 0x4F719C
KILL_LIMIT = 0x4F8408
NET_CHOSEN = 0x4F70A0
MODE_VS = 0x4F711C
MODE_ARENA = 0x4F7120
MODE_SCRAMBLE = 0x4F7124
LOAD_FROM_MENU = 0x86AD50     # byte: set by the main-menu load row
PROFILE_WORD = 0x4F8F38       # first word of g_savedConfig
PENDING_LEVEL = 0x41B6D0
PENDING_MARKER = 0x41B720

# Menu tables (16-byte records; the terminator's +4 word is the selected row).
T_MAIN = 0x4F6B88
T_GAME_TYPE = 0x4F6BF8
T_PLAYERS = 0x4F6DE8
T_MODE_ONE = 0x4F6C68         # one player: two rows
T_MODE_MULTI = 0x4F6C28       # two to four players: three rows
T_DIFFICULTY = 0x4F6E38
T_KILL_LIMIT = 0x4F6C98
T_NET_ROLE = 0x4F6DB8
T_OPTIONS = 0x4F6E88
T_CREDITS = 0x4F6FB8
TABLE_ROWS = {T_MAIN: 4, T_GAME_TYPE: 2, T_PLAYERS: 4, T_MODE_ONE: 2,
              T_MODE_MULTI: 3, T_DIFFICULTY: 4, T_KILL_LIMIT: 3, T_NET_ROLE: 2}

S_MAIN, S_GAME_TYPE, S_PLAYERS, S_DIFFICULTY, S_MODE, S_KILL_LIMIT = range(6)
S_NET_ROLE, S_LOBBY_WAIT, S_OPTIONS, S_SAVE_CHOICE, S_CREDITS = 6, 10, 11, 14, 15

PAD_PRESENT = 0x41BFDC        # pad slot word read by the players list
PAD_STRIDE = 0x58
ACCEPT_MASK = 0x40            # initial word at 0x41BFBC
CANCEL_MASK = 0x120           # initial word at 0x41BFB8
ACCEPT_MASK_WORD = 0x41BFBC
CANCEL_MASK_WORD = 0x41BFB8
PAD_BASE = 0x41BFD8           # slot s at PAD_BASE + s * PAD_STRIDE
PAD_HELD, PAD_PRESSED, PAD_REPEAT = 0x8, 0xC, 0x10
MENU_PADS_SCANNED = 1         # frontend_run reads pad slot 0 only


def menu_input(pads, accept_mask=ACCEPT_MASK, cancel_mask=CANCEL_MASK):
    """frontend_run accept / cancel flags from per-slot (held, pressed, repeat)
    words: only the pressed word of the scanned slots counts, masked by the
    words at ACCEPT_MASK_WORD and CANCEL_MASK_WORD."""
    scanned = [pad[1] for pad in pads[:MENU_PADS_SCANNED]]
    return (any(word & accept_mask for word in scanned),
            any(word & cancel_mask for word in scanned))

# Main-menu rows, by the order of the retail table at T_MAIN.
MAIN_NEW, MAIN_LOAD, MAIN_OPTIONS, MAIN_CREDITS = range(4)
MAIN_ACCEPT = {
    MAIN_NEW: (S_GAME_TYPE, T_GAME_TYPE),
    MAIN_LOAD: (S_MAIN, T_MAIN),       # state unchanged; load screen requested
    MAIN_OPTIONS: (S_OPTIONS, T_OPTIONS),
    MAIN_CREDITS: (S_CREDITS, T_CREDITS),
}
LOAD_REQUEST = 0x2176E0
LOAD_REQUEST_ARGS = (0, 1)    # (pad index, apply-save flag)

# Mode rows: (vs, scramble, arena) flags derived from each row's key.
MODE_FLAGS = {
    T_MODE_ONE: ((0, 0, 0), (0, 0, 1)),
    T_MODE_MULTI: ((0, 0, 0), (0, 0, 1), (1, 0, 1)),
}
KILL_LIMITS = (5, 10, 25)


def max_difficulty(profile_word):
    """0x1EC448: highest difficulty row + 1 the profile unlocks (1..5)."""
    if profile_word & 0x40:
        return 5
    if profile_word & 0x20:
        return 4
    if profile_word & 0x11:
        return 3
    if profile_word & 0x0C:
        return 2
    return 1


def players_row_kinds(pads_present):
    """Kind words the players list gets each pass for pads_present contiguous
    pad slots 0..n-1 (see players_row_kinds_present)."""
    return players_row_kinds_present((1 << pads_present) - 1)


ROW_ENABLED, ROW_DISABLED = 0, 5
PLAYERS_ENABLE_SITE, PLAYERS_DISABLE_SITE = 0x1E0F74, 0x1E0F88


def players_row_kinds_present(present_mask, row0_kind=0):
    """Kind words after one pass, from a 4-bit pad-present mask (bit s = slot
    s's word at PAD_PRESENT + s * PAD_STRIDE is nonzero).  Row 0 is never
    written (row0_kind is whatever it held).  Row r (1..3) is 0 iff slots
    1..r are all present; slot 0 is not read.  Once a row is disabled every
    later row is too."""
    kinds, latched = [row0_kind], False
    for slot in range(1, 4):
        latched = latched or not present_mask >> slot & 1
        kinds.append(ROW_DISABLED if latched else ROW_ENABLED)
    return tuple(kinds)


def players_accept(row):
    """State 2 accept: (players, next state, next table) or None."""
    if not 0 <= row < 4:
        return None
    players = row + 1
    return players, S_MODE, T_MODE_ONE if players < 2 else T_MODE_MULTI


def mode_next(vs, scramble, arena):
    """State 4 accept, offline: ('kill', state, table) / ('select', difficulty)
    / ('difficulty', state, table).  Scramble also forces one player."""
    if vs:
        return ('kill', S_KILL_LIMIT, T_KILL_LIMIT)
    if arena or scramble:
        return ('select', 1)
    return ('difficulty', S_DIFFICULTY, T_DIFFICULTY)


def difficulty_accept(row, profile_word):
    """State 3 accept, offline: the stored difficulty or None when locked."""
    level = row + 1
    if max_difficulty(profile_word) < level:
        return None
    return level


def cancel_offline(state, players):
    """Cancel from the offline setup states: (state, table)."""
    if state == S_GAME_TYPE:
        return S_MAIN, T_MAIN
    if state == S_PLAYERS:
        return S_GAME_TYPE, T_GAME_TYPE
    if state == S_DIFFICULTY:
        return S_MODE, T_MODE_ONE if players < 2 else T_MODE_MULTI
    if state == S_MODE:
        return S_PLAYERS, T_PLAYERS
    if state == S_KILL_LIMIT:
        return S_MODE, T_MODE_MULTI
    if state == S_OPTIONS:
        return S_SAVE_CHOICE, None
    raise ValueError(state)


# Character selection entry and finish.
PLAYER_SEL_START = 0x2245B8
PLAYER_SEL_FINISH = 0x22A360
PLAYER_SEL_TASK = 0x225478
PLAYER_SEL_PRIORITY = 9
PLAYER_SEL_PHASE = 0x8E2C02
PLAYER_SEL_SLOT = 0x8E2C01
PLAYER_SEL_PENDING = 0x4FBBD8
PLAYER_SEL_RUNNING = 0x4FBBDC
PLAYER_SEL_OFFLINE = 0x4FBBE3
PLAYER_SEL_COMMITTED = 0x4FBBE2
PLAYER_SEL_PLAYERS = 0x4FDCB0
SEL_ROWS = 0x4FDB80
SEL_ROW_STRIDE = 0x2C
SEL_LEVEL = 0x4FDC30          # level the finish phase queues
SEL_ALT_LEVEL = 0x4FDC70      # level used by finish(1)
HUB_NAME_FN = 0x1EC300
PHASE_IMPORT = 1
FINISH_SITES = ((0x225D48, 1), (0x2287E4, 0))   # (call site, argument)
LEVEL_ENTRY_APPLY_SITE = 0x321024
PLAYER_SEL_APPLY_PENDING = 0x2247EC    # the call at LEVEL_ENTRY_APPLY_SITE
HUB_DECIDED, HUB_SIDE, HUB_COMPLETE = 0x1BF960, 0x1BF8D8, 0x1BF730
HUB_PREDICATE_SITES = {HUB_DECIDED: 0x1EC308, HUB_SIDE: 0x1EC318, HUB_COMPLETE: 0x1EC32C}
HUB_MISSION = 1               # second argument of mission_isComplete


def hub_predicate_calls(decided, side, difficulty):
    """game_getHubName's short-circuit chain: [(predicate, args)] in call order
    for the given predicate results (the third result does not change the
    calls)."""
    got = [(HUB_DECIDED, None)]
    if decided:
        got.append((HUB_SIDE, None))
        if side:
            got.append((HUB_COMPLETE, (difficulty, HUB_MISSION)))
    return got


def hub_is_second(decided, side, complete):
    """True when game_getHubName returns the second hub name."""
    return bool(decided and side and complete)


def import_first(difficulty):
    """playerSel_start argument: 1 (import phase first) from difficulty 2."""
    return 1 if difficulty >= 2 else 0


# ---- Character creation: starting stats, ability points, name entry --------------
# Carousel row -> model -> class, and class starting stats, as already pinned
# by tools/difftest_char_create.py (repeated here so this module stands alone).
CAROUSEL_MODEL = (0, 11, 10, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
MODEL_CLASS = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)
CLASS_STATS = (
    (35, 20, 25, 35), (26, 36, 27, 26), (28, 30, 27, 30),
    (28, 25, 35, 27), (23, 39, 25, 28), (32, 22, 31, 30),
    (26, 37, 24, 28),
)
STAT_POINTS = 20              # word 0x8E2BB0 after the appearance accept
# Appearance accept copies byte appearance_source(i, carousel row) into
# selection row byte APPEARANCE_ROW_BYTES[i] (the last two are swapped).
APPEARANCE_VALUES = 0x8E2BC0  # four 16-byte arrays, one byte per carousel row
APPEARANCE_STRIDE = 0x10
APPEARANCE_ROW_BYTES = (0x21, 0x22, 0x24, 0x23)


def appearance_source(index, carousel_row):
    return APPEARANCE_VALUES + index * APPEARANCE_STRIDE + carousel_row
STAT_MAX = 100                # an increment is allowed while the value is < 100
POINTS = 0x8E2BB0
STAT_CURSOR = 0x8E2BBC
STAT_WARN = 0x8E2BBD
NEXT_PHASE = 0x8E2C03
PHASE_APPEARANCE, PHASE_STATS, PHASE_NAME, PHASE_FINISH_FADE, PHASE_NEXT_PLAYER = 2, 3, 4, 5, 6
# Pad word bits per slot (base 0x41BFD8 + slot * 0x58; +0xC pressed, +0x10 repeat).
REPEAT_UP, REPEAT_DOWN = 0x101000, 0x204000
REPEAT_RIGHT, REPEAT_LEFT = 0x802000, 0x408000
NAME_DELETE_REPEAT = 0x80
NAME_UPPER_HELD = 0x08


def class_base(carousel_row):
    return CLASS_STATS[MODEL_CLASS[CAROUSEL_MODEL[carousel_row]]]


def stat_input(stats, points, cursor, carousel_row, repeat):
    """One phase-3 frame with a repeat bit: returns (stats, points, cursor)."""
    stats = list(stats)
    if repeat & REPEAT_UP:
        return stats, points, cursor - 1 if cursor > 0 else cursor
    if repeat & REPEAT_DOWN:
        return stats, points, cursor + 1 if cursor < 3 else cursor
    if repeat & REPEAT_RIGHT and points and stats[cursor] < STAT_MAX:
        stats[cursor] += 1
        return stats, points - 1, cursor
    if repeat & REPEAT_LEFT and stats[cursor] > class_base(carousel_row)[cursor]:
        stats[cursor] -= 1
        return stats, points + 1, cursor
    return stats, points, cursor


def stat_accept(points):
    """Accept in phase 3: unspent points open the warning, else the name phase."""
    return 'warn' if points else PHASE_NAME


WARN_ALPHA_MAX = 126
WARN_STEP_OPEN, WARN_STEP_CLOSE = 16, -16
NEXT_PLAYER_STEP = 16         # 0x8E2BB8 when the next-player box opens


def stat_warning_frame(alpha, step, accept):
    """One phase-3 frame while the unspent-points warning is up:
    (shown, alpha, step).  Alpha 0x8E2BB4 moves by step 0x8E2BB8 and clamps at
    WARN_ALPHA_MAX; at or below 0 the warning clears.  Accept turns the step
    to WARN_STEP_CLOSE only when this frame's alpha is WARN_ALPHA_MAX."""
    alpha = min(alpha + step, WARN_ALPHA_MAX)
    if alpha <= 0:
        return 0, 0, step
    if accept and alpha == WARN_ALPHA_MAX:
        step = WARN_STEP_CLOSE
    return 1, alpha, step


NAME_MAX = 30
NAME_LENGTH = 0x8E2BA4
NAME_CURSOR = 0x8E2BA0
NAME_KEY = 0x8E2C5C           # keyboard character, -1 for none
NAME_WARN = 0x8E2BBF
CURSOR_DONE, CURSOR_SPACE = -1, -2


def name_accept(name, cursor, glyphs):
    """Accept press in nameEntry_run 0x22BE68: (name, return value, warning)."""
    if cursor == CURSOR_DONE:
        return (name, 1, 0) if name.strip(' ') else (name, 0, 1)
    if len(name) >= NAME_MAX:
        return name, 0, 0
    return name + (' ' if cursor == CURSOR_SPACE else glyphs[cursor]), 0, 0


def name_phase_result(result, slot_offset, players):
    """Phase 4 offline after nameEntry_run returns: (phase byte, next phase)."""
    if result == 1:
        if slot_offset == players - 1:
            return PHASE_FINISH_FADE, None          # straight to the finish fade
        return PHASE_NAME, PHASE_NEXT_PLAYER
    if result == -1:
        return PHASE_NAME, PHASE_STATS              # and the point pool becomes 0
    return PHASE_NAME, None
