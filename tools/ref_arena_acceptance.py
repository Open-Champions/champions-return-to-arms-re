"""Reference model for the arena acceptance boundary (round 12).

Prose: docs/spec/arena-acceptance.md.  Compared against the original functions by
tools/difftest_arena_acceptance.py.  No game strings or table bytes are stored here:
the substrings the front end searches for, menu identifiers, level-name tables and
recipe bytes are read from the private executable at run time and passed in.

Labels follow the repository convention.  Every rule below is the model of an
original body the difftest executes; the addresses are where the rule lives.
"""
import ref_arena_modes as A
from ref_core import from_int, s16

# ---- front end, frontend_run 0x1e08f0 ------------------------------------------------
STATE_DIFFICULTY = 3
STATE_MODE = 4
STATE_KILL_LIMIT = 5
MENU_MODE_SOLO = 0x4F6C68        # two entries: missions, arena
MENU_MODE_MULTI = 0x4F6C28       # three entries: missions, arena co-op, arena versus
MENU_KILL_LIMIT = 0x4F6C98
MENU_DIFFICULTY = 0x4F6E38


def players_choice(index):
    """State 2 (0x1e1888).  Returns (num_players or None, next state or None, menu or None).

    Every visit clears the three mode words (0x1e18d0-0x1e18e4), including an index
    outside 0..3, which changes nothing else."""
    if not 0 <= index < 4:
        return None, None, None
    players = index + 1
    menu = MENU_MODE_SOLO if players < 2 else MENU_MODE_MULTI
    return players, STATE_MODE, menu


def mode_choice(entry_id, needle_a, needle_scramble, needle_b, players):
    """State 4 (0x1e18e8).  entry_id is the chosen menu entry's identifier string.

    Returns a dict of the words the handler leaves: mode A 0x4f711c, scramble 0x4f7124,
    mode B 0x4f7120, g_numPlayers 0x4d8ae0, and what happens next."""
    mode_a = 1 if needle_a in entry_id else 0
    scramble = 1 if needle_scramble in entry_id else 0
    mode_b = 1 if (needle_b in entry_id or scramble) else 0
    if scramble:
        players = 1
    out = {'mode_a': mode_a, 'scramble': scramble, 'mode_b': mode_b, 'players': players,
           'state': None, 'menu': None, 'difficulty': None, 'player_select': 0}
    if mode_a:
        out['state'], out['menu'] = STATE_KILL_LIMIT, MENU_KILL_LIMIT
    elif mode_b:
        out['difficulty'] = 1               # 0x1e19bc-0x1e19c4
        out['player_select'] = 1            # frontend_startPlayerSelect 0x1e3ba0
    else:
        out['state'], out['menu'] = STATE_DIFFICULTY, MENU_DIFFICULTY
    return out


def kill_limit_offline(index):
    """State 5 offline (0x1e1a58): 5, 10, or 25 for any other index."""
    return A.KILL_CHOICES[0] if index == 0 else A.KILL_CHOICES[1] if index == 1 else A.KILL_CHOICES[2]


# ---- net launch, 0x137464-0x137518 ---------------------------------------------------
def net_launch(mode_byte, difficulty_byte, kill_byte, team_arg, scan1):
    """Words written from the launch block 0x402b90 (+0xa0 difficulty, +0xa1 mode,
    +0xa2 kill limit, +0xf4 argument of game_set4f7110 0x1ec830)."""
    m = mode_byte & 0xFF
    mode_b = 1 if 1 <= m <= 3 else 0
    mode_a = 1 if m in (2, 3) else 0
    scramble = 1 if m == 3 else 0
    diff = difficulty_byte - 0x100 if difficulty_byte & 0x80 else difficulty_byte
    w7110 = None
    if mode_a:
        w7110 = scan1 if (team_arg & 0xFFFFFFFF) == 0xFFFFFFFF else team_arg & 0xFFFFFFFF
    return {'mode_a': mode_a, 'mode_b': mode_b, 'scramble': scramble,
            'difficulty': diff & 0xFFFFFFFF, 'limit': kill_byte & 0xFF, 'w7110': w7110}


# ---- team byte at record +0x4c24, character import 0x220644-0x22067c ------------------
def import_team(mode_a, slot):
    return slot & 0xFF if mode_a else 0


# ---- player_removeAllItems 0x1bf600 --------------------------------------------------
def remove_all(bags):
    """The loop at 0x1bf62c-0x1bf678 on lists of cells; returns the removal calls
    as (index, bag) in order.  After any non-empty bag the bag index is reset to 0 by
    the delay slot at 0x1bf66c and then advanced, so the next visit is bag 1."""
    calls = []
    bag = 0
    while bag < 3:
        if bags[bag]:
            calls.append((0, bag))
            bags[bag].pop(0)
            while 1 < len(bags[0]):
                calls.append((1, 0))
                bags[0].pop(1)
            bag = 0
        bag += 1
    return calls


# ---- arena_init 0x304c4c --------------------------------------------------------------
def is_arena_level(name, mode_a, table_a, table_b):
    """0x307d48: strcmp of the previous level name against the mode's table."""
    return 1 if name in (table_a if mode_a else table_b) else 0


def arena_init_fresh(prev_name, mode_a, end_flag, table_a, table_b):
    """False is the continuing branch (0x304c84 beqzl): the previous level was one of
    this mode's arena levels and the end flag is clear."""
    return not (is_arena_level(prev_name, mode_a, table_a, table_b) and end_flag == 0)


def minimap_mode(scramble):
    return 1 if scramble else 2


# ---- arena_drawPrompt 0x3075dc, the result page ---------------------------------------
def result_rows(rank, kills, names, players):
    """ASCII draws per ranked row (x, text): a shadow pass then a front pass
    (0x307960-0x307b70).  The place is 1-based with a trailing full stop (the
    executed output of the format at 0x551f98); kills are signed halfwords printed
    in decimal (format at 0x551fa0)."""
    out = []
    for i in range(players):
        slot = rank[i]
        place = '%d.' % (i + 1)
        k = '%d' % s16(kills[slot])
        n = names[slot]
        out += [(0x7B, place), (0xA0, n), (0x205, k),
                (0x77, place), (0x9C, n), (0x201, k)]
    return out


def result_header(mode_a, end_flag, wave):
    """Which header the page draws: ('winner', None) in mode A, else
    ('defeat' or 'interval', float(signed wave + 1))."""
    if mode_a:
        return 'winner', None
    return ('defeat' if end_flag else 'interval'), from_int(s16(wave) + 1)


# ---- Creature_applyKnockback 0x115eb8, player gate -----------------------------------
def player_push_suppressed(object_flags, network, mode_b):
    """0x115ef0-0x115f24: an object with flag 0x40 (a player) has +0x2e8 zeroed and is
    not moved in a net game or while mode B is set."""
    return bool(object_flags & 0x40) and bool(network or mode_b)


# ---- signed-wave overflow, arena_startWave 0x305ed4 -----------------------------------
def overflow_wave(prev_halfword):
    """The wave halfword after start(1): lhu / addu / sh, so 0x7fff becomes 0x8000."""
    return (prev_halfword + 1) & 0xFFFF


def overflow_plan(wave, active, record_count, byte_at, recipes, seed):
    """Spawn plan for any signed wave, reading recipe bytes through byte_at(addr)
    so a negative record index reads before the table as the original does.

    Returns (class indices, seed, ring steps) or raises ZeroDivisionError."""
    count, quot, rem = A.spawn_budget(wave, active)
    index = A.sdiv(quot, record_count)[1]
    base = recipes + 6 * index
    record = bytes(byte_at(base + i) for i in range(6))
    classes = A.recipe_groups(record, rem, count) if count > 0 else []
    steps = []
    if rem == 0:
        seed, angle, draw = A.ring_step(seed, count)
        steps.append((count, angle, draw))
    elif 0 < rem < 3:
        groups = A.high_nibble(record[0]) - (1 if rem == 1 else 0)
        per, _ = A.sdiv(count, groups)
        leftover = count - per * groups
        for group in range(groups):
            n = per + leftover if group == 0 else per
            seed, angle, draw = A.ring_step(seed, n)
            steps.append((n, angle, draw))
    return classes, seed, steps, index
