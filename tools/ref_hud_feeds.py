"""Reference models for the HUD feeds closed in round 3 (SLUS-20973 v2.00).

Authored from the instruction behaviour that tools/difftest_hud_feeds.py executes in
tools/ee_emu.py (and tools/vu1_emu.py for the tile program). No game bytes, strings or
table values are stored here; addresses are cited for the reader.

Sections
  1. hud_run 0x1db870 opening the level-up panel, the message-9 send in
     menu_openInventory 0x1c15c8 and the store to acknowledged level +0x58.
  2. Branch conditions of the hud_showMessage 0x1d92a0 callers reachable in missions:
     script_setInfo 0x14318c, DoorSwing_interact 0x28aa7c, Savepoint_interactPrompt
     0x28da58, JumpGate_interactPrompt 0x27d7a0, and itemprop_tryPickup 0x154dbc
     (whose own body never calls it; its accepted-path callees were stubbed).
  3. Ammunition (lines 3 and 6) and thrown (line 7) notice starters.
  4. Map icons: the registrar 0x1689a4, the PushTrigger_ctor property feed and the
     draw-time vars_get / script_runByName gates of 0x168cac.
  5. Automap tile quads: which grid cells one strip packet carries and the (u, v, alpha)
     of each vertex the VU1 program at 0x403e20 emits.
"""

M32 = 0xFFFFFFFF


def s8(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


# ---- 1. acknowledged level -------------------------------------------------------------
# hud_run per-slot gates, in the order the code tests them (0x1db964..0x1dba90).
ACK_GATES = (
    'pressed',        # raw pad 0x4028d0 + 0x58*slot, pressed word +0xc has bit 0x100
    'held_80',        # held word +0x8 must NOT have bit 0x80
    'menu_open',      # g_localMenuOpen 0x41b69d
    'pause_menu',     # pauseMenu_isOpen 0x18cbfc
    'frozen',         # game_isFrozen 0x1ebdf8
    'camera_mode',    # *(0x4f8450) + 0x34 must equal 1
    'cutscene',       # g_cutsceneActive 0x44fcd0
    'input_block',    # byte 0x4f66c8
    'word_503890',    # word 0x503890
    'object_540',     # record +0x43d8 object, +0x540 (only when the object exists)
    'travel',         # jumpgate_getTravelState 0x27dd68
    'task_a',         # task_isRunning(name at 0x53c5b0)
    'task_b',         # task_isRunning(name at 0x53c280)
    'recall',         # g_recallCountdown 0x41b51d
    'no_object',      # record +0x43d8 null
    'flag_400000',    # object +0xc bit 0x400000
)


def hud_run_open(blocked, ack, earned, object_flags, health_positive):
    """What one slot's pass of hud_run does after the pad edge.

    blocked: set of ACK_GATES names that are failing. Returns None (no call),
    or (level_up,) for the menu_openInventory(slot, level_up) call. When level_up is 1
    the glow word 0x86aa50[slot] is also zeroed (0x1dbaec).
    """
    if blocked:
        return None
    if object_flags & 0x8 or not health_positive:
        return None
    return (1,) if s8(ack) < s8(earned) else (0,)


def level_ack_message(slot, earned):
    """Inventory message 9 that menu_openInventory(slot, 1) sends (0x1c17f8..0x1c1818):
    three bytes {9, slot, signed earned level byte +0x59}."""
    return bytes([9, slot & 0xFF, earned & 0xFF])


def apply_level_ack(payload):
    """invmsg_dispatch 0x1bfdb0 case 9: record(payload[1]) + 0x58 = payload[2]."""
    return payload[1], payload[2]


# ---- 2. message callers ----------------------------------------------------------------
SHOW_FRAMES = 0xB4          # 180, every caller in this section


def set_info():
    """script_setInfo: text_lookup(key), then hud_showMessage(text, 180, -1, 0)."""
    return {'frames': SHOW_FRAMES, 'slot': -1, 'force': 0}


def door_interact(slot, lock_script, lock_result, sound_prop, sound_is_plain):
    """DoorSwing_interact(door, slot) up to the locked branch (0x28aa7c..0x28ab90).

    lock_script: the door has the lock-script property (obj_getPropStr, key 0x549070).
    lock_result: what script_runByName returned for it. sound_prop: the door has the
    property at 0x549078; sound_is_plain: strcmp of that value with the string at
    0x549080 is 0. Returns None when the door goes on to open, else the locked effects.
    """
    if slot == -10 or not lock_script or lock_result != 0:
        return None
    if sound_prop and not sound_is_plain:
        sound = None
    elif sound_prop:
        sound = 'named'          # res_find(0x549088, 0x549090)
    else:
        sound = 'default'        # res_find(0x549088, 0x5490a8)
    return {'sound': sound, 'voice': (slot, 7), 'message': (SHOW_FRAMES, -1, 0)}


def savepoint_prompt(busy, all_state2, no_save_zone, flags_540, override, network,
                     frame_word, byte_c7):
    """Savepoint_interactPrompt(savepoint, buffer) (0x28da58..0x28dc2c).

    flags_540: per active slot, whether that player object's +0x540 is nonzero.
    override: the savepoint has the text-key property at 0x549258.
    Returns (result, message key or None, prompt key or None). Keys are the addresses
    of the text-key strings the code passes to text_lookup.
    """
    if busy or all_state2:
        return 0, None, None
    if no_save_zone:
        if not any(flags_540):
            return 0, ('override' if override else 0x549268), None
        return 0, 0x549278, None
    if network:
        if frame_word >= 0x709 and s8(byte_c7) == -1:
            return 1, None, 0x549288
        return 1, None, 0x5492a0
    return 1, None, 0x5492b0


def jumpgate_first_prompt(flag_4f, task_running, gate_script, gate_result, seen):
    """The message half of JumpGate_interactPrompt(gate, buffer, slot) (0x27d7a0..0x27d860).

    Returns 'stop' (returns 0 before any message), 'message' (first prompt: +0x4d set to
    1, 0x27db60 called, hud_showMessage(text, 180, 0x4f8440[slot], 0)), or 'quiet'
    (+0x4d already set) or 'other' (+0x4f set: a different branch, not followed).
    """
    if s8(flag_4f) != 0:
        return 'other'
    if task_running:
        return 'stop'
    if gate_script and gate_result == 0:
        return 'stop'
    return 'quiet' if s8(seen) != 0 else 'message'


def pickup(bag_count_plus_one_below_64, load_fits):
    """itemprop_tryPickup(slot, item): its own body never calls hud_showMessage (its
    callees, the level-script call included, were stubs in the difftest).
    Returns (result, effects)."""
    if not bag_count_plus_one_below_64:
        return 0, ('sound',)
    if not load_fits:
        return 0, ('voice0',)
    return 1, ('sound', 'script', 'giveItem', 'after')


# ---- 3. notices ------------------------------------------------------------------------
NOTICE_TIMER, NOTICE_ROW = 0x41B828, 0x41B8A8      # int[4][8] each


def low_count(count):
    """The starters' test: (u16 count - 1) unsigned < 20, i.e. 1..20."""
    return ((count & 0xFFFF) - 1) & M32 < 0x14


def ammo_neutral(ammo_present, count, copy):
    """Player_run 0x1a758c..0x1a7678 (an arrow ability in the neutral state).
    Line 6 does not test the prediction copy here; line 3 does."""
    out = []
    if ammo_present and low_count(count):
        out.append((6, 0xF0))
    if not copy and not ammo_present:
        out.append(('voice', 5))
        out.append((3, 0x78))
    return out


def ammo_attack(ammo_present, count, copy):
    """Player_run 0x1a7d4c..0x1a7eb4 (after the ammunition search): a copy skips both."""
    if copy:
        return []
    return ammo_neutral(ammo_present, count, False)


def thrown_release(count):
    """Line 7 for 240 frames when the stack being thrown holds 1..20 before the
    decrement (Player_run 0x1a888c, SkillFireAxe_cast 0x319cc4, SkillColdAxe_cast
    0x31a5f8)."""
    return [(7, 0xF0)] if low_count(count) else []


def weapon_swap(set_index, item_class):
    """Player_weaponSwapInput 0x1bb9b0: line 7 when the new set is 1 and its weapon's
    class byte +0x1e is 6, whatever the count."""
    return [(7, 0xF0)] if s8(set_index) == 1 and s8(item_class) == 6 else []


# ---- 4. map icons ----------------------------------------------------------------------
ICONS, ICON_COUNT, ICON_STRIDE = 0x6E0F90, 0x6E14D0, 0x1C
SCALE_SMALL, SCALE_ONE = 0x3F266666, 0x3F800000


def arrow_choice(direction, angle):
    """Which of the four fixed arrow names (0x533ba0, 0x533bb0, 0x533bc0, 0x533bd0 as
    k = 0, 1, 2, 3) the registrar uses for a name that starts with the 4-byte prefix
    0x533b60. direction is 0..3 for a name equal to 0x533b68/70/80/90, else -1."""
    a = angle + 0x3FFF if angle < 0 else angle
    x = direction - (a >> 14) + 4
    k = x - int(x / 4) * 4            # C remainder
    return k


def register_icon(pos, rotate, name, offset, scale_int, var, script, f32_add):
    """0x1689a4: one table entry, or None when name is null. offset is (dx, dy) as f32
    bit patterns (0, 0 when the offset string is null); f32_add adds two patterns."""
    if not name:
        return None
    return {'x': f32_add(pos[0], offset[0]), 'y': f32_add(pos[1], offset[1]),
            'rotate': rotate & M32, 'scale': SCALE_SMALL if scale_int else SCALE_ONE,
            'var': var & M32, 'script': script & M32}


def pushtrigger_rotate(name_is_a, name_is_b):
    """PushTrigger_ctor 0x1ec9c8..0x1ec9e8: rotate unless the icon name equals the
    string at 0x53e260 or the one at 0x53e268."""
    return 0 if (name_is_a or name_is_b) else 1


def icon_gate(var, var_value, var_known, script, machine, find_error, result):
    """Phase B of 0x168cac for one icon (vars_get at 0x1696a4 on +0x14, then
    script_runByName at 0x1696c4 on +0x18). Returns (drawn, appended, interpreted).

    var/script: the entry has the name pointer. var_known: the name is already in
    g_questVars; var_value its signed byte. machine: the word at 0x86b270 is nonzero.
    find_error: what scr_findEntry 0x13eac8 returns (0 = found; it writes the entry
    index through its third argument). result: the word scr_interpret 0x13ecf8 leaves
    in the slot script_runByName seeded with that 0.
    """
    appended = interpreted = False
    if var:
        value = var_value if var_known else 0
        appended = not var_known
        if value == 0:
            return False, appended, False
    if script:
        if not machine or find_error != 0:
            ret = -1
        else:
            interpreted = True
            ret = result
        if ret == 0:
            return False, appended, interpreted
    return True, appended, interpreted


# ---- 5. automap tile quads -------------------------------------------------------------
TILE_UV_STEP, TILE_UV_SPAN = 160, 158
ORIENT = (
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((1, 0), (1, 1), (0, 0), (0, 1)),
    ((0, 1), (0, 0), (1, 1), (1, 0)),
    ((1, 1), (1, 0), (0, 1), (0, 0)),
    ((0, 0), (1, 0), (0, 1), (1, 1)),
    ((0, 1), (1, 1), (0, 0), (1, 0)),
    ((1, 0), (0, 0), (1, 1), (0, 1)),
    ((1, 1), (0, 1), (1, 0), (0, 0)),
)


def strip_columns(c_min, c_end, cols=30, step=29):
    """Column runs of the strip packets: (first column, count)."""
    out = []
    c = c_min
    while c < c_end:
        out.append((c, min(c + cols, c_end) - c))
        c += step
    return out


def tile_quad(c_r, c_r1, c1_r, c1_r1):
    """One quad: corners (c,r), (c,r+1), (c+1,r), (c+1,r+1) in emission order. Tile column
    bits 0-4, orientation 5-7 and atlas row 8-11 come from (c+1, r+1); each vertex's
    alpha is its own corner's high byte. Returns four (u, v, alpha)."""
    src = c1_r1 & 0xFFFF
    col, orient, row = src & 0x1F, (src >> 5) & 7, (src >> 8) & 0xF
    us = (col * TILE_UV_STEP, col * TILE_UV_STEP + TILE_UV_SPAN)
    vs = (row * TILE_UV_STEP, row * TILE_UV_STEP + TILE_UV_SPAN)
    corners = (c_r, c_r1, c1_r, c1_r1)
    return tuple((us[ue], vs[ve], (corners[i] >> 8) & 0xFF)
                 for i, (ue, ve) in enumerate(ORIENT[orient]))


def strip_vertices(grid_cell, rows, first_col, count):
    """Every vertex of one strip packet, in emission order: for each pair of adjacent
    rows, for each pair of adjacent columns, tile_quad. grid_cell(col, row) -> u16."""
    out = []
    for j in range(len(rows) - 1):
        r = rows[j]
        for i in range(count - 1):
            c = first_col + i
            out.extend(tile_quad(grid_cell(c, r), grid_cell(c, r + 1),
                                 grid_cell(c + 1, r), grid_cell(c + 1, r + 1)))
    return out


# Added in the round-3 fix: the GS shape of one strip packet. Each pair of adjacent rows
# is one PRIM write, 0x15c (triangle strip, Gouraud, textured, alpha-blended, UV
# coordinates), followed by four XYZ2 vertices with ADC 0 per quad of that row pair.
TILE_PRIM = 0x15C


def strip_prim_runs(row_count, column_count):
    """Vertices after each PRIM write of one strip packet: one run per row pair."""
    return [4 * (column_count - 1)] * max(row_count - 1, 0)
