#!/usr/bin/env python3
"""ref_quests.py - campaign steps that are not already in ref_natives.

Quest-list add and remove, the mission bits, medals, the evil and decision
bits, the gold split and the script-facing experience wrapper stay in
tools/ref_natives.py. This module is the rest of one campaign step: the
mission menu, which act a level name belongs to, the hub name, the experience
body, clearing a quest list, and which flag-39 items an act change keeps.

docs/quests.md is the write-up. tools/difftest_quests.py runs the original
functions. tools/test_ref_quests.py checks this file without an executable.

Nothing here is copied from the game. Addresses are the US v2.00 ones.
"""

# player_giveExp 0x1d3150. The 81 thresholds live at 0x41b558 and are read
# from the executable by the differential test; this file does not carry them.
XP_TABLE = 0x41B558
XP_LEVELS = 81

# game_getHubName 0x1ec300. Difficulty bit in the evil byte, the decision byte
# and mission 1's complete bit, all on record 0.
HUB_GOOD = 'hub'
HUB_EVIL = 'hub2'

# quest_clearAll 0x1d3adc writes this into each used entry and then stores 0.
QUEST_PLACEHOLDER = b'NoQuests\0'
QUEST_SLOTS = 8
QUEST_STRIDE = 0x40
QUEST_TEXT = 0x20

# player_removeFlag39Items 0x1be1d8. Compared as C strings, case-sensitive.
QUEST_ITEM_BIT = 39
QUEST_KEEP_CONTAINS = ('bloodstone', 'shardof')
QUEST_KEEP_EXACT = ('spiritrunes', 'emptybag', 'fullbag', 'pickaxe', 'twistedkey')

# missionMenu_run 0x2316fc. One button per tick; a chord is not specified.
BTN_TRIANGLE = 0x10
BTN_CIRCLE = 0x20
BTN_CROSS = 0x40
BTN_SQUARE = 0x80
BTN_SELECT = 0x100
BTN_START = 0x800
BTN_UP = 0x1000
BTN_RIGHT = 0x2000
BTN_DOWN = 0x4000
BTN_LEFT = 0x8000

MENU_ROWS = 12          # cursor rows 0..11, missions 1..12
MENU_LAST_ROW = 11
INTRO_STEP = 8
INTRO_DONE = 127
CLOSE_STEP = 16
FADE_DONE = 128
LAUNCH_ORIENT = 0xFF


class MissionRow(object):
    """One row of g_missionTable. Empty strings stand for null pointers.
    The three flag words are the signed words at +0x20, +0x24 and +0x28."""

    def __init__(self, story, evil, medal, bonus, flag20, flag24, flag28):
        self.story = story or ''
        self.evil = evil or ''
        self.medal = medal or ''
        self.bonus = bonus or ''
        self.flag20 = int(flag20)
        self.flag24 = int(flag24)
        self.flag28 = int(flag28)


class CampaignView(object):
    """The bits the menu reads. `rows` has one MissionRow per table row.
    Mission numbers, not rows, go in the three sets. `evil` is already the
    bit for the current difficulty."""

    def __init__(self, rows, available=(), complete=(), medals=None, evil=False,
                 local=False, pause=False, slot_active=True, fade=0):
        self.rows = list(rows)
        self.available_set = set(available)
        self.complete_set = set(complete)
        self.medals = dict(medals or {})
        self.evil = bool(evil)
        self.local = bool(local)
        self.pause = bool(pause)
        self.slot_active = bool(slot_active)
        self.fade = int(fade)

    def mission_available(self, mission):
        return mission in self.available_set

    def mission_complete(self, mission):
        return mission in self.complete_set

    def mission_medal(self, mission):
        return int(self.medals.get(mission, 0))


def new_menu():
    """The menu after missionMenu_open and before the first run tick."""
    return {
        'state': 0, 'row': 0, 'col': 0, 'counter': 0, 'mark': 0, 'c0': 0,
        'paused': 0, 'pending': '', 'orient': 0,
    }


def initial_row(available):
    """Highest available mission in 1..12, as a row. Mission 0 is not a row."""
    rows = [mission - 1 for mission in available if 1 <= mission <= MENU_ROWS]
    return max(rows) if rows else 0


def helper_value(index, row, available, complete, medal):
    """The twelve predicates at 0x231078, in address order.

    0..2  the mission is available (the flag words are not consulted).
    3..5  medal at least 1, 2 or 3, and the word at +0x24.
    6     complete, the word at +0x24, and a medal-level pointer.
    7     complete and a medal-level pointer. The flag words are not consulted.
    8     complete and the word at +0x20.
    9..11 medal at least 3 and the word at +0x28.
    """
    medal = int(medal)
    if index <= 2:
        return 1 if available else 0
    if index == 3:
        return 1 if medal >= 1 and row.flag24 else 0
    if index == 4:
        return 1 if medal >= 2 and row.flag24 else 0
    if index == 5:
        return 1 if medal >= 3 and row.flag24 else 0
    if index == 6:
        return 1 if complete and row.flag24 and row.medal else 0
    if index == 7:
        return 1 if complete and row.medal else 0
    if index == 8:
        return 1 if complete and row.flag20 else 0
    if 9 <= index <= 11:
        return 1 if medal >= 3 and row.flag28 else 0
    raise IndexError(index)


def _row_mission(row):
    return row + 1


def _toward_side(state, info, avail, done, medal):
    if state['col'] == 0:
        if helper_value(6, info, avail, done, medal):
            state['col'] = 1
        elif helper_value(10, info, avail, done, medal):
            state['col'] = 2
    elif state['col'] == 1 and helper_value(10, info, avail, done, medal):
        state['col'] = 2


def _toward_story(state, info, avail, done, medal):
    if state['col'] == 2:
        state['col'] = 1 if helper_value(6, info, avail, done, medal) else 0
    elif state['col'] == 1:
        state['col'] = 0


def menu_tick(state, button, world):
    """One call of missionMenu_run. Mutates `state`.

    The body that runs is the state at entry. A button stores the next state
    and does not run that new body on the same tick. State 1, state 6 and
    state 8 do their work on the tick that finds them.
    """
    button &= 0xFFFF
    st = state['state']
    if st == 0:
        state['row'] = initial_row(world.available_set)
        state['col'] = 0
        state['paused'] = 1
        state['counter'] = 0
        state['state'] = 1
        return state
    if st == 1:
        state['counter'] += INTRO_STEP
        if state['counter'] >= FADE_DONE:
            state['counter'] = INTRO_DONE
            state['state'] = 2
        return state
    if st == 2:
        state['mark'] += 8
        if world.local and world.pause:
            return state
        if not world.slot_active:
            state['state'] = 4
            return state
        row = state['row']
        info = world.rows[row]
        mission = _row_mission(row)
        avail = world.mission_available(mission)
        done = world.mission_complete(mission)
        medal = world.mission_medal(mission)
        if button & BTN_CROSS:
            accepted = False
            if state['col'] == 0 and helper_value(0, info, avail, done, medal):
                accepted = True
            elif state['col'] == 1 and helper_value(7, info, avail, done, medal):
                accepted = True
            elif state['col'] == 2 and helper_value(11, info, avail, done, medal):
                accepted = True
            if accepted:
                state['state'] = 5
                state['c0'] = 1
            return state
        if button & (BTN_CIRCLE | BTN_SELECT):
            state['state'] = 4
            return state
        if button & BTN_UP:
            if row > 0:
                state['row'] = row - 1
            return state
        if button & BTN_DOWN:
            nxt = row + 1
            if nxt <= MENU_LAST_ROW and world.mission_available(nxt + 1):
                state['row'] = nxt
            return state
        # 0x2314bc returns bit 0 of the row. On an odd row the right button
        # walks toward the medal and bonus columns. On an even row the left
        # button does, and right walks back toward the story column.
        toward_side = BTN_RIGHT if (row & 1) else BTN_LEFT
        toward_story = BTN_LEFT if (row & 1) else BTN_RIGHT
        if button & toward_side:
            _toward_side(state, info, avail, done, medal)
            return state
        if button & toward_story:
            _toward_story(state, info, avail, done, medal)
            return state
        return state
    if st == 3:
        state['state'] = 2
        return state
    if st == 4:
        state['counter'] -= CLOSE_STEP
        return state
    if st == 5:
        state['state'] = 6
        return state
    if st == 6:
        if world.fade >= FADE_DONE:
            state['state'] = 7
        else:
            state['c0'] += 1
        return state
    if st == 7:
        state['state'] = 8
        return state
    if st == 8:
        info = world.rows[state['row']]
        col = state['col']
        if col == 1:
            state['pending'] = info.medal
        elif col == 2:
            state['pending'] = info.bonus
        elif world.evil and info.evil:
            state['pending'] = info.evil
        else:
            state['pending'] = info.story
        state['orient'] = LAUNCH_ORIENT
        state['c0'] = 0
        return state
    return state


def skill_points_for(level):
    """Points added while leaving `level`. The band is the level before it increments."""
    if level < 6:
        return 1
    if level < 16:
        return 2
    if level < 26:
        return 3
    if level < 36:
        return 4
    return 5


def give_exp(level, exp, skill, stat, hp, max_hp, mana, max_mana, amount, table):
    """player_giveExp for one record once the thresholds are known.

    Returns level, exp, skill, stat (low 8 bits), hp, mana, and how many times
    player_recalcStats runs. A record whose hp is not greater than 0 keeps
    both pools. `table` has 81 entries; the cap is the last one minus 1.
    """
    if len(table) != XP_LEVELS:
        raise ValueError('the experience table has 81 entries')
    cap = table[80] - 1
    exp = exp + amount
    if exp > cap:
        exp = cap
    recalcs = 0
    while level < 80 and table[level] <= exp:
        skill += skill_points_for(level)
        stat = (stat + 3) & 0xFF
        level += 1
        recalcs += 1
        if hp > 0:
            hp = max_hp
            mana = max_mana
    return level, exp, skill, stat & 0xFF, hp, mana, recalcs


def hub_name(evil, decision, mission1, difficulty):
    """game_getHubName. `hub2` when this difficulty's bit is set in both
    campaign bytes and mission 1 is complete."""
    bit = 1 << difficulty
    if (evil & bit) and (decision & bit) and (mission1 & 2):
        return HUB_EVIL
    return HUB_GOOD


def find_act(name, current, acts):
    """save_findAct. A row matches when its name is a prefix of `name`.
    The current act is searched first, then acts 0..n-1. current outside
    0..n-1 is skipped. Comparison is case-sensitive."""
    order = []
    if isinstance(current, int) and 0 <= current < len(acts):
        order.append(current)
    order.extend(range(len(acts)))
    for act in order:
        for prefix in acts[act]:
            if prefix and name.startswith(prefix):
                return act
    return -1


def act_changed(name, current, acts):
    """save_actChanged. Returns (1, new act) when a different act matches,
    otherwise (0, current)."""
    found = find_act(name, current, acts)
    if found >= 0 and found != current:
        return 1, found
    return 0, current


def clear_quest_list(entries, count):
    """quest_clearAll for one record.

    `entries` is eight (title, text) pairs of 32-byte fields. The first
    `count` pairs get the placeholder copied over the front of each field;
    bytes after that copy stay. Later pairs stay whole. The count becomes 0.
    """
    out = []
    for index, (title, text) in enumerate(entries):
        if index < count:
            out.append((_overlay(title), _overlay(text)))
        else:
            out.append((_field(title), _field(text)))
    while len(out) < QUEST_SLOTS:
        out.append((b'\0' * 32, b'\0' * 32))
    return out[:QUEST_SLOTS], 0


def _field(data):
    data = bytes(data)
    if len(data) < 32:
        data = data + bytes(32 - len(data))
    return data[:32]


def _overlay(data):
    field = bytearray(_field(data))
    field[:len(QUEST_PLACEHOLDER)] = QUEST_PLACEHOLDER
    return bytes(field)


def quest_item_kept(name):
    """True when an item with flag bit 39 survives player_removeFlag39Items."""
    if any(part in name for part in QUEST_KEEP_CONTAINS):
        return True
    return name in QUEST_KEEP_EXACT


def flag39_remaining(items):
    """`items` is a list of (name, flag int). Items without bit 39 stay.
    Items with the bit stay only when quest_item_kept says so. Order holds."""
    kept = []
    for name, flags in items:
        if ((int(flags) >> QUEST_ITEM_BIT) & 1) and not quest_item_kept(name):
            continue
        kept.append((name, int(flags)))
    return kept
