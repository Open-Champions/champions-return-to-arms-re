#!/usr/bin/env python3
"""ref_script_items.py - reference contract for the item, gold and skill script commands
and the helpers behind them (docs/script-items.md).

What this module covers, each with the address of the original function:

  inventory_countItemByName      0x1c5880   (name, slot) -> sum of stack counts
  inventory_findItemBySubstring  0x1c5a70   (slot, text, *index, *bag)
  player_getPassiveLevel         0x1bed48   (slot, mask) -> level byte or 0
  player_getSkillRank            0x1bf330   (slot, skill id) -> rank or 0
  player_itemWeight              0x1b6338   (slot, item) -> float
  player_recalcLoad              0x1bec10   (slot): record +0x120
  the load limit part of player_recalcStats 0x1b6458 (0x1b6964-0x1b6a20): record +0x124
  clearAllSkills                 0x1458e0
  game_scanCm1Vars               0x1eb950   (recompute) -> word 0x4f7110 or a scan index
  game_set4f7110                 0x1ec830   (value or -1)
  the script handlers playerHasItem 0x145590, onePlayerHasItem 0x145690,
  countQuestItems 0x145720, removeAllItems 0x145758, removeAllWeapons 0x145828,
  removePlayerItem 0x14598c, givePlayerItem 0x145a88, giveOnePlayerItem 0x145d20,
  givePlayerGold 0x1462dc, takePlayerGold 0x1463ec, checkPlayerGold 0x14644c,
  checkPlayerMinGold 0x146494.

The handlers are written against a Host (call-outs) and a memory with load/store (the
ref_natives.Mem interface).  inventory_giveItem and inventory_removeItem are not
re-modelled: Composer routes them to tools/ref_messages.py (Machine.give_item,
Machine.remove_item), which tools/difftest_messages.py already runs against the original.
item_parseDescriptor is tools/ref_items.parse_descriptor; item_getWeight is
tools/ref_items.item_weight.  Every float is a raw 32-bit pattern and every operation is
one R5900 operation (ref_items.fadd/fmul/flt).

Nothing from the game is in this file: addresses, offsets, constants and the order of
operations only.  The tables the parser needs are read from the user's own executable at
run time (ref_items.Tables).
"""
import os
import struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_items as I       # noqa: E402

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF

# ---- globals ------------------------------------------------------------------------------
G_NUM_PLAYERS = 0x4D8AE0            # s32
G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
G_LOAD_BONUS = 0x4D8AE8             # s32 word read only by player_recalcStats (0x1b69e0)
G_RAND_SEED = 0x404464
G_MEDAL_MISSION = 0x4F713C          # s32: non-zero = medal mode, give only to the medal player
G_MEDAL_PLAYER = 0x4F7148           # u8
G_ALIVE_LIST = 0x4F8440             # s32[]: slots of the living players
G_CM1_WORD = 0x4F7110               # s32, -1 in the executable image
G_CLASS_SKILLS, CLASS_SKILLS_SIZE, CLASS_SKILL_ROW = 0x4EF538, 0xA88, 0x38
G_SKILL_OBJECTS = 0x41B170          # g_skillTable: pointer per skill id
SKILL_AXE_BANDOLIER, SKILL_LIGHT_QUIVER = 0x49, 0x4A
MAX_GOLD = 99999999

# ---- the player record (docs/player.md) ---------------------------------------------------
P_CLASS = 0x50
P_EFF_STRENGTH = 0x90
P_GOLD, P_SKILL_POINTS = 0xE4, 0xE8
P_PASSIVES = 0xEF                   # s8[48]
P_LOAD, P_LOAD_LIMIT = 0x120, 0x124  # floats
P_ABILITY_MASK = 0x128              # u64
P_BAGS, BAG_SIZE, BAG_COUNT, ITEM_SIZE, BAG_SLOTS = 0x130, 0x1208, 0x1200, 0x48, 64
P_OBJECT = 0x43D8
P_SET_WEAPONS = 0x4434              # item*[2], then +0x443c the second weapon
P_ABILITY_SKILL, ABILITY_SIZE, ABILITIES = 0x4460, 0x68, 15
P_PAD_MASK, P_QUICK_A, P_QUICK_B = 0x4A80, 0x4A84, 0x4A85
P_SKILL_PAIRS, SKILL_PAIRS = 0x4B08, 48     # {s16 id, s16 rank}; ends at +0x4bc8
P_MISSIONS = 0x4BBF                 # + difficulty * 13 + mission; difficulty is 1..5
P_MEDALS = 0x4C0D
OBJ_FLAGS, OBJ_DEAD, OBJ_POS = 0x0C, 0x8, 0x10

# ---- constants (raw single-precision patterns) --------------------------------------------
F_ZERO, F_HALF, F_ONE = 0, 0x3F000000, 0x3F800000
F_15 = 0x41700000                   # 0x1b69c8: per level of the load passive
F_5000 = 0x459C4000                 # 0x1b69f4: when G_LOAD_BONUS is non-zero
F_9999 = 0x461C3C00                 # 0x1b6a0c: the cap
LOAD_STRENGTH_BASE = 125            # 0x1b6988: strength + 125
PASSIVE_LOAD = 0x40                 # 0x1b698c: class passive mask that raises the limit
PASSIVE_AMMO = 0x10000              # 0x1b6390: class passive mask that halves ammunition
ITEM_SLOT_AMMO = 8                  # definition +0x1c
ITEM_FLAG_THROWN_AXE = 1 << 42      # 0x1b63f8: 0x8000 << 27

# ---- game_scanCm1Vars ------------------------------------------------------------------------
# The nine profile-variable names at 0x53e170, 0x53e178 .. 0x53e1b0 (8 bytes apart), in the
# order tested.  They are short identifiers the executable exposes (m<N>cm1); there is no
# m10cm1 or m3cm1.  The index returned is the position in this list, 9 when none is set.
CM1_NAMES = (b'm11cm1', b'm9cm1', b'm8cm1', b'm7cm1', b'm6cm1', b'm5cm1', b'm4cm1', b'm2cm1',
             b'm1cm1')
CM1_NAME_ADDRS = tuple(0x53E170 + 8 * k for k in range(9))
CM1_NONE = 9


class Fault(Exception):
    """The original would read through a null pointer here (address 0 + offset)."""


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def rec(slot):
    """g_players + slot * 0x4c30.  The handlers multiply the slot as given, unchecked."""
    return (G_PLAYERS + s32(slot) * REC_SIZE) & M32


def bag_entry(slot, bag, index):
    return (rec(slot) + P_BAGS + s32(bag) * BAG_SIZE + s32(index) * ITEM_SIZE) & M32


def bag_count_at(slot, bag):
    return (rec(slot) + P_BAGS + s32(bag) * BAG_SIZE + BAG_COUNT) & M32


def cstr(mem, addr, limit=0x4000):
    out = bytearray()
    while len(out) < limit:
        b = mem.load((addr + len(out)) & M32, 1)
        if b == 0:
            return bytes(out)
        out.append(b)
    raise ValueError('string at 0x%x has no terminator' % addr)


def strcmp_equal(a, b):
    """libc_strcmp 0x3b8534 == 0 (case matters)."""
    return a == b


def strstr_found(haystack, needle):
    """libc_strstr 0x3b96a8 != NULL.  An empty needle is found in any text."""
    return needle in haystack


# =========================================================================================
# The item helpers
# =========================================================================================
def count_item_by_name(mem, name, slot):
    """inventory_countItemByName 0x1c5880 (name, slot).

    For each of the three bags, for i from 0 while i < the bag's count (re-read after every
    entry): when the definition name of entry i (the string at *(entry +0) +0) equals name
    exactly, add the entry's s16 stack count (+0x04).  Returns the 32-bit sum.  The entry's
    definition pointer is not tested: an entry inside the count with definition 0 reads the
    word at address 0 as the name pointer.  The slot is not range-checked."""
    total = 0
    for bag in range(3):
        i = 0
        while i < mem_s32(mem, bag_count_at(slot, bag)):
            entry = bag_entry(slot, bag, i)
            definition = mem.load(entry, 4)
            if strcmp_equal(cstr(mem, mem.load(definition, 4)), name):
                total = s32(total + s16(mem.load(entry + 4, 2)))
            i += 1
    return total


def find_item_by_substring(mem, slot, text):
    """inventory_findItemBySubstring 0x1c5a70 (slot, text, *index, *bag) -> (index, bag).

    *index is set to -1 first; *bag is written only on a match.  For bag 0, 1, 2 and every
    entry inside the count (re-read each time), an entry whose definition NAME occurs inside
    TEXT (strstr(text, name)) overwrites both outputs.  So the LAST matching entry of the
    LAST bag that has one wins, and an item whose name is empty matches any text.
    Returns (index, bag) with bag None when nothing matched (the caller's word is kept)."""
    index, found_bag = -1, None
    for bag in range(3):
        i = 0
        while i < mem_s32(mem, bag_count_at(slot, bag)):
            entry = bag_entry(slot, bag, i)
            name = cstr(mem, mem.load(mem.load(entry, 4), 4))
            if strstr_found(text, name):
                index, found_bag = i, bag
            i += 1
    return index, found_bag


def passive_level(mem, slot, mask):
    """player_getPassiveLevel 0x1bed48 (slot, mask): slot (unsigned) must be below 5 - so a
    fifth record past the four is accepted.  The 48 class-skill rows of the player's class
    (0x4ef538 + class * 0xa88, rows of 0x38, u64 mask first) are searched for mask (64-bit
    compare); the level is the s8 at record +0xef + row, negative read as 0.  0 when absent."""
    if (slot & M32) >= 5:
        return 0
    r = rec(slot)
    table = (G_CLASS_SKILLS + s32(mem.load(r + P_CLASS, 4)) * CLASS_SKILLS_SIZE) & M32
    for row in range(48):
        if mem.load(table + row * CLASS_SKILL_ROW, 8) == mask & M64:
            level = s8(mem.load(r + P_PASSIVES + row, 1))
            return level if level >= 0 else 0
    return 0


def skill_rank(mem, slot, skill):
    """player_getSkillRank 0x1bf330 (slot, id): the {s16 id, s16 rank} pairs at record
    +0x4b08 up to the first id -1.  There is no count limit: a list with no -1 among its 48
    pairs runs on into +0x4bc8 (the countdown bytes) and beyond."""
    r = rec(slot)
    where = r + P_SKILL_PAIRS
    while True:
        ident = s16(mem.load(where, 2))
        if ident == -1:
            return 0
        if ident == s16(skill):
            return s16(mem.load(where + 2, 2))
        where += 4


def item_get_weight(mem, tables, item_addr):
    """item_getWeight 0x103e08 through ref_items.item_weight (raw float)."""
    data = bytes(mem.load(item_addr + k, 1) for k in range(ITEM_SIZE))
    return I.item_weight(I.Item.unpack(tables, data))


def item_weight(mem, tables, host, slot, item_addr):
    """player_itemWeight 0x1b6338 (slot, item) -> raw float.

    A null item, or an item whose definition pointer is 0, weighs 1.0 (not 0).
    Ammunition (definition +0x1c == 8): f = 0.5 if the class passive 0x10000 has a level,
    then x 0.5 again for the same test (the code asks twice), then x Light Quiver's
    complement (call-out skill_lightQuiverComplement(g_skillTable[0x4a], rank)) when rank 0x4a
    is not 0.  Otherwise an item with flag bit 42: f = Axe Bandolier's complement
    (skill_axeBandolierComplement(g_skillTable[0x49], rank)) when rank 0x49 is not 0.
    Weight = f * item_getWeight(item)."""
    if item_addr == 0 or mem.load(item_addr, 4) == 0:
        return F_ONE
    definition = mem.load(item_addr, 4)
    f = F_ONE
    if s8(mem.load(definition + 0x1C, 1)) == ITEM_SLOT_AMMO:
        if passive_level(mem, slot, PASSIVE_AMMO):
            f = F_HALF
        if passive_level(mem, slot, PASSIVE_AMMO):
            f = I.fmul(f, F_HALF)
        rank = skill_rank(mem, slot, SKILL_LIGHT_QUIVER)
        if rank != 0:
            obj = mem.load(G_SKILL_OBJECTS + 4 * SKILL_LIGHT_QUIVER, 4)
            f = I.fmul(f, host.call('skill_lightQuiverComplement', obj, rank & M32))
    elif mem.load(item_addr + 8, 8) & ITEM_FLAG_THROWN_AXE:
        rank = skill_rank(mem, slot, SKILL_AXE_BANDOLIER)
        if rank != 0:
            obj = mem.load(G_SKILL_OBJECTS + 4 * SKILL_AXE_BANDOLIER, 4)
            f = I.fmul(f, host.call('skill_axeBandolierComplement', obj, rank & M32))
    return I.fmul(f, item_get_weight(mem, tables, item_addr))


def recalc_load(mem, tables, host, slot):
    """player_recalcLoad 0x1bec10 (slot): +0x120 = 0, then for each bag and each entry
    inside the count (re-read), +0x120 = +0x120 + player_itemWeight(slot, entry) - one
    float add per entry, in bag order.  Empty entries inside the count are weighed too
    (1.0 each, see item_weight)."""
    r = rec(slot)
    mem.store(r + P_LOAD, 4, 0)
    for bag in range(3):
        i = 0
        while i < mem_s32(mem, bag_count_at(slot, bag)):
            w = item_weight(mem, tables, host, slot, bag_entry(slot, bag, i))
            mem.store(r + P_LOAD, 4, I.fadd(mem.load(r + P_LOAD, 4), w))
            i += 1


def load_limit(effective_strength, passive_load_level, bonus_word):
    """The load limit (record +0x124) as player_recalcStats 0x1b6458 stores it
    (0x1b6978-0x1b6a20).  recalcStats walks slots 0 .. g_numPlayers - 1 and skips a record
    whose object pointer (+0x43d8) is 0 (0x1b64d8): that record keeps its old limit.
    Otherwise, with strength the effective strength recalcStats has just rebuilt (+0x90)
    and obj_slot the slot word of the player OBJECT (+0x3c8):

        limit = float(strength + 125)
        limit = limit + float(player_getPassiveLevel(obj_slot, 0x40)) * 15.0
        if word 0x4d8ae8 != 0: limit = limit + 5000.0
        if 9999.0 < limit:     limit = 9999.0

    Returns the raw pattern."""
    limit = I.fint(s32(effective_strength + LOAD_STRENGTH_BASE))
    limit = I.fadd(limit, I.fmul(I.fint(passive_load_level), F_15))
    if s32(bonus_word) != 0:
        limit = I.fadd(limit, F_5000)
    if I.flt(F_9999, limit):
        limit = F_9999
    return limit


def fits(mem, slot, weight, strict):
    """The handlers' weight test: load + weight < limit (C.OLT.S), or - givePlayerItem only,
    strict False - a weight that is exactly 0 (C.EQ.S, so -0.0 as well)."""
    r = rec(slot)
    if I.flt(I.fadd(mem.load(r + P_LOAD, 4), weight), mem.load(r + P_LOAD_LIMIT, 4)):
        return True
    return not strict and (weight & 0x7FFFFFFF) == 0


# =========================================================================================
# clearAllSkills, mission bytes
# =========================================================================================
def clear_all_skills(mem):
    """clearAllSkills 0x1458e0, on the record of the medal player (u8 0x4f7148):

        +0x128  u64 = 0                          (0x145900)
        +0xef + k  = 0  for k 0..47              (the 48 class-passive levels)
        +0x4b08 + 4k: s16 -1, s16 -1 for k 0..47 (0x145928-0x145944: bytes +0x4b08..+0x4bc7)
        +0xe8   s32 = 0                          (skill points)
        +0x4a85 u8  = 1   (set, not cleared)
        +0x4a80 s32 = 0
        +0x4a84 u8  = 0
        +0x4460 + 0x68 k: s16 -1, and the byte at +4 = 0, for the 15 ability records
    Returns 0.  The skill-pair stores cover +0x4bbf..+0x4bc7, which is where the mission
    row of difficulty 0 would begin (mission_byte_addr); difficulty is 1..5, so no mission
    flag is touched (docs/script-items.md section 3)."""
    r = rec(mem.load(G_MEDAL_PLAYER, 1))
    mem.store(r + P_ABILITY_MASK, 8, 0)
    for k in range(48):
        mem.store(r + P_PASSIVES + k, 1, 0)
    for k in range(SKILL_PAIRS):
        mem.store(r + P_SKILL_PAIRS + 4 * k, 2, 0xFFFF)
        mem.store(r + P_SKILL_PAIRS + 4 * k + 2, 2, 0xFFFF)
    mem.store(r + P_SKILL_POINTS, 4, 0)
    mem.store(r + P_QUICK_B, 1, 1)
    mem.store(r + P_PAD_MASK, 4, 0)
    mem.store(r + P_QUICK_A, 1, 0)
    for k in range(ABILITIES):
        mem.store(r + P_ABILITY_SKILL + ABILITY_SIZE * k, 2, 0xFFFF)
        mem.store(r + P_ABILITY_SKILL + ABILITY_SIZE * k + 4, 1, 0)
    return 0


def mission_byte_addr(slot, difficulty, mission):
    """Record +0x4bbf + difficulty * 13 + mission (mission_isAvailable 0x1bf698 and the
    other four).  Rows 1..5 are +0x4bcc..+0x4c0c, ending where the medal bytes +0x4c0d
    start; row 0 would be +0x4bbf..+0x4bcb, inside the skill pairs and the countdowns."""
    return (rec(slot) + P_MISSIONS + s32(difficulty) * 13 + s32(mission)) & M32


SKILL_PAIR_SPAN = (P_SKILL_PAIRS, P_SKILL_PAIRS + 4 * SKILL_PAIRS)      # [+0x4b08, +0x4bc8)
MISSION_ROW_SPAN = {d: (P_MISSIONS + 13 * d, P_MISSIONS + 13 * d + 13) for d in range(6)}


def mission_rows_overlapping_skill_pairs():
    """Difficulties whose 13 mission bytes share a byte with the skill pairs."""
    lo, hi = SKILL_PAIR_SPAN
    return [d for d, (a, b) in MISSION_ROW_SPAN.items() if a < hi and lo < b]


# =========================================================================================
# game_scanCm1Vars and its cache
# =========================================================================================
def scan_cm1_vars(recompute, profile_get, word):
    """game_scanCm1Vars 0x1eb950 (recompute).

    recompute == 0: returns the word at 0x4f7110 (passed as `word`) - no profile read.
    Otherwise: profile_getVar 0x22289c on each of CM1_NAMES in order, and the index of the
    first that is non-zero; 9 when none is.  profile_get(name) must behave like
    profile_getVar (it appends an unknown name with 0 - a write to this machine's profile
    table, which the scan therefore makes for each name it reaches)."""
    if recompute == 0:
        return s32(word)
    for index, name in enumerate(CM1_NAMES):
        if profile_get(name) != 0:
            return index
    return CM1_NONE


def set_cm1_word(mem, value, profile_get):
    """game_set4f7110 0x1ec830 (value): 0x4f7110 = value, or game_scanCm1Vars(1) when
    value is -1.  Callers: frontend_start 0x1e204c (-1), the start-up path 0x323e90 (-1),
    and the net launch receiver 0x137504 (the word at launch message +0xf4, which the
    host's launch builder 0x13542c filled with game_scanCm1Vars(1))."""
    if s32(value) == -1:
        value = scan_cm1_vars(1, profile_get, 0)
    mem.store(G_CM1_WORD, 4, value & M32)


# =========================================================================================
# The handlers
# =========================================================================================
def mem_s32(mem, addr):
    return s32(mem.load(addr & M32, 4))


class Host:
    """Call-outs.  log holds (name, args) for every call-out in order; answers[name] is a
    function giving the result (default 0)."""

    def __init__(self, answers=None):
        self.log = []
        self.answers = dict(answers or {})

    def call(self, name, *args):
        self.log.append((name, args))
        f = self.answers.get(name)
        return f(*args) if f is not None else 0


class Composer:
    """The item handlers composed with their callees.

    mem      memory with load(addr, size) / store(addr, size, value) holding the game state
    tables   ref_items.Tables of the user's executable (for the parser and item weights)
    host     Host for the call-outs that are not part of this contract:
             player_recalcStats, player_countPotions, inventory_equipItem,
             player_resetIdleAnim, pool_new, ItemProp_ctor2, vars_get, vars_set,
             text_lookup, hud_showHelpMessage, net_isLocalSlot,
             skill_lightQuiverComplement, skill_axeBandolierComplement
    scratch  an address the composer may use for the handler's stack record

    inventory_giveItem / inventory_removeItem run as tools/ref_messages.py has them, on the
    same memory, with their call-outs sent to host (player_recalcLoad is answered here)."""

    def __init__(self, mem, tables, host, scratch):
        import ref_messages as RM
        self.mem, self.tables, self.host, self.scratch = mem, tables, host, scratch
        callbacks = {name: (lambda *a, _n=name: self.host.call(_n, *a)) for name in (
            'player_recalcStats', 'player_countPotions', 'player_resetIdleAnim', 'vars_get', 'vars_set',
            'text_lookup', 'hud_showHelpMessage', 'net_isLocalSlot', 'inventory_selectIdleAnim')}
        callbacks['player_recalcLoad'] = lambda slot: recalc_load(self.mem, self.tables, self.host, slot)
        self.machine = RM.Machine(mem, tables=None, callbacks=callbacks)

    # ---- memory helpers ---------------------------------------------------------------------
    @property
    def num_players(self):
        return mem_s32(self.mem, G_NUM_PLAYERS)

    @property
    def seed(self):
        return self.mem.load(G_RAND_SEED, 4)

    def _object(self, slot):
        return self.mem.load(rec(slot) + P_OBJECT, 4)

    # ---- counts --------------------------------------------------------------------------------
    def playerHasItem(self, name):
        """0x145590 (s item): the sum of inventory_countItemByName over slots 0 ..
        g_numPlayers - 1 (the count is re-read after every slot)."""
        total, slot = 0, 0
        while slot < self.num_players:
            total = s32(total + count_item_by_name(self.mem, name, slot))
            slot += 1
        return total

    def onePlayerHasItem(self, player, name):
        """0x145690 (i player, s item): 0 unless player < g_numPlayers (SIGNED: a negative
        player passes and reads in front of g_players), the record's object pointer is not
        0 and object flag 8 (dead) is clear.  The string is fetched only after those tests."""
        player = s32(player)
        if not player < self.num_players:
            return 0
        obj = self._object(player)
        if obj == 0 or self.mem.load(obj + OBJ_FLAGS, 4) & OBJ_DEAD:
            return 0
        return count_item_by_name(self.mem, name, player)

    def countQuestItems(self, name):
        """0x145720 (s item): player 0 only, with no player-count, object or death test."""
        return count_item_by_name(self.mem, name, 0)

    # ---- removal -------------------------------------------------------------------------------
    def _remove(self, slot, index, bag):
        self.machine.remove_item(slot, index, bag, 0)

    def removePlayerItem(self, player, text):
        """0x14598c (i player, s text).  player -1: for slot 0 .. g_numPlayers - 1, the
        entry inventory_findItemBySubstring picks is removed with inventory_removeItem(slot,
        index, bag, 0).  Otherwise, when player < g_numPlayers (signed), the same for that
        one slot.  The handler's bag word starts at 0 and is not reset between players;
        it is used only after a match, which writes it."""
        player = s32(player)
        if player == -1:
            slot = 0
            while slot < self.num_players:
                index, bag = find_item_by_substring(self.mem, slot, text)
                if index != -1:
                    self._remove(slot, index, bag)
                slot += 1
        elif player < self.num_players:
            index, bag = find_item_by_substring(self.mem, player, text)
            if index != -1:
                self._remove(player, index, bag)
        return 0

    def _empty_bag(self, slot, bag):
        count = mem_s32(self.mem, bag_count_at(slot, bag))
        while count > 0:
            if self.mem.load(bag_entry(slot, bag, 0), 4) != 0:
                self._remove(slot, 0, bag)
            count -= 1

    def removeAllItems(self):
        """0x145758: medal player (u8 0x4f7148); for bags 0, 1, 2: the count c is read once;
        c times, inventory_removeItem(slot, 0, bag, 0) when entry 0's definition word is not 0.
        A count <= 0 does nothing."""
        slot = self.mem.load(G_MEDAL_PLAYER, 1)
        for bag in range(3):
            self._empty_bag(slot, bag)
        return 0

    def removeAllWeapons(self):
        """0x145828: bag 0 of the medal player by the same loop, then record +0x4434,
        +0x4438 (the two weapon-set pointers) and +0x443c (the second weapon) = 0.  The
        equipment slots +0x43f0.. are cleared only by inventory_removeItem for the entries
        it removes."""
        slot = self.mem.load(G_MEDAL_PLAYER, 1)
        self._empty_bag(slot, 0)
        r = rec(slot)
        for off in (0, 4, 8):
            self.mem.store(r + P_SET_WEAPONS + off, 4, 0)
        return 0

    # ---- giving ----------------------------------------------------------------------------------
    def _parse(self, text, use_presets):
        """item_parseDescriptor(text, record, -1, use_presets): variant -1 (one draw when the
        definition has variants), into the handler's stack record (self.scratch)."""
        rng = I.Rng(self.seed)
        item = I.parse_descriptor(self.tables, text, -1, use_presets, rng)
        if rng.draws:
            self.mem.store(G_RAND_SEED, 4, rng.seed)
        data = item.pack(bytes(self.mem.load(self.scratch + k, 1) for k in range(ITEM_SIZE)))
        for k, b in enumerate(data):
            self.mem.store(self.scratch + k, 1, b)
        return item

    def _give_one(self, slot, text, equip, use_presets, strict, reset_idle):
        """Parse, weigh, then either inventory_giveItem(slot, record, 1) +
        player_recalcLoad(slot) [+ equip] and True, or False (the caller drops it)."""
        self._parse(text, use_presets)
        weight = item_weight(self.mem, self.tables, self.host, slot, self.scratch)
        if not fits(self.mem, slot, weight, strict):
            return False
        index = s32(self.machine.give_item(slot, self.scratch, 1))
        recalc_load(self.mem, self.tables, self.host, slot)
        if equip != 0:
            bag = s8(self.mem.load(self.mem.load(self.scratch, 4) + 0x1D, 1))
            self.host.call('inventory_equipItem', slot & M32, bag_entry(slot, bag, index), 0)
            if reset_idle:
                self.host.call('player_resetIdleAnim', slot & M32)
        return True

    def _drop(self, position_obj):
        """pool_new(0x190); when it is not 0, ItemProp_ctor2(block, &position of the object
        (12 bytes copied from object +0x10), record, 0).  pool_new 0 loses the item."""
        block = self.host.call('pool_new', 0x190) & M32
        if block == 0:
            return
        if position_obj == 0:
            raise Fault('givePlayerItem: neither the player nor g_alivePlayers[0] has an object '
                        '(the original reads the position at address 0x10)')
        pos = tuple(self.mem.load(position_obj + OBJ_POS + 4 * k, 4) for k in range(3))
        self.host.call('ItemProp_ctor2', block, pos, self.scratch, 0)

    def givePlayerItem(self, text, equip, use_presets):
        """0x145a88 (s descriptor, i equip, i usePresets).  The third script argument is
        passed to item_parseDescriptor as its usePresets argument; the variant argument is
        always -1 (random).  For slot 0 .. g_numPlayers - 1 (re-read), skipping every slot
        but the medal player while word 0x4f713c is non-zero: parse, then give if
        load + weight < limit or weight == 0, equip (and player_resetIdleAnim) when equip is
        non-zero; otherwise drop at the player's object, or - when the record has no object -
        at the object of the first living player (g_alivePlayers[0], 0x4f8440), read only
        after pool_new returned a block; when that record has no object either the original
        reads the position at address 0x10 (Fault here)."""
        slot = 0
        while slot < self.num_players:
            if mem_s32(self.mem, G_MEDAL_MISSION) == 0 or slot == self.mem.load(G_MEDAL_PLAYER, 1):
                if not self._give_one(slot, text, equip, use_presets, False, True):
                    obj = self._object(slot)
                    if obj == 0:
                        obj = self._object(mem_s32(self.mem, G_ALIVE_LIST))
                    self._drop(obj)
            slot += 1
        return 0

    def giveOnePlayerItem(self, player, text, equip, use_presets):
        """0x145d20 (i player, s descriptor, i equip, i usePresets): one slot, which must be
        < g_numPlayers (signed) and have an object without flag 8; strict weight test (a
        weight of 0 must also fit); no player_resetIdleAnim after equipping; a drop is at the
        player's own object."""
        player = s32(player)
        if not player < self.num_players:
            return 0
        obj = self._object(player)
        if obj == 0 or self.mem.load(obj + OBJ_FLAGS, 4) & OBJ_DEAD:
            return 0
        if not self._give_one(player, text, equip, use_presets, True, False):
            self._drop(obj)
        return 0

    # ---- gold ------------------------------------------------------------------------------------
    def givePlayerGold(self, amount):
        """0x1462dc (i amount): each slot gains amount / g_numPlayers (C division, toward
        zero), with the 32-bit wrap; a result above 99,999,999 is stored and then replaced
        by 99,999,999.  The count is re-read for each slot; with no players nothing runs."""
        slot = 0
        while slot < self.num_players:
            at = rec(slot) + P_GOLD
            gold = s32(mem_s32(self.mem, at) + _tdiv(amount, self.num_players))
            self.mem.store(at, 4, gold & M32)
            if gold > MAX_GOLD:
                self.mem.store(at, 4, MAX_GOLD)
            slot += 1
        return 0

    def takePlayerGold(self, amount):
        """0x1463ec (i amount): each slot loses amount / g_numPlayers, not below 0."""
        slot = 0
        while slot < self.num_players:
            at = rec(slot) + P_GOLD
            gold = s32(mem_s32(self.mem, at) - _tdiv(amount, self.num_players))
            self.mem.store(at, 4, max(gold, 0) & M32)
            slot += 1
        return 0

    def checkPlayerGold(self):
        """0x14644c: the 32-bit sum of every slot's gold."""
        total, slot = 0, 0
        while slot < self.num_players:
            total = s32(total + mem_s32(self.mem, rec(slot) + P_GOLD))
            slot += 1
        return total

    def checkPlayerMinGold(self):
        """0x146494: the smallest gold; slot 0's when there are fewer than two players."""
        least, slot = mem_s32(self.mem, rec(0) + P_GOLD), 1
        while slot < self.num_players:
            least = min(least, mem_s32(self.mem, rec(slot) + P_GOLD))
            slot += 1
        return least

    def clearAllSkills(self):
        return clear_all_skills(self.mem)


def _tdiv(a, b):
    a, b = s32(a), s32(b)
    if b == 0:
        raise ZeroDivisionError('division by g_numPlayers 0')
    q = abs(a) // abs(b)
    return s32(q if (a < 0) == (b < 0) else -q)


HANDLERS = {
    'playerHasItem': 0x145590, 'onePlayerHasItem': 0x145690, 'countQuestItems': 0x145720,
    'removeAllItems': 0x145758, 'removeAllWeapons': 0x145828, 'clearAllSkills': 0x1458E0,
    'removePlayerItem': 0x14598C, 'givePlayerItem': 0x145A88, 'giveOnePlayerItem': 0x145D20,
    'givePlayerGold': 0x1462DC, 'takePlayerGold': 0x1463EC, 'checkPlayerGold': 0x14644C,
    'checkPlayerMinGold': 0x146494,
}
# argument kinds per handler, in script order: i integer, s string
SIGNATURES = {
    'playerHasItem': 's', 'onePlayerHasItem': 'is', 'countQuestItems': 's', 'removeAllItems': '',
    'removeAllWeapons': '', 'clearAllSkills': '', 'removePlayerItem': 'is', 'givePlayerItem': 'sii',
    'giveOnePlayerItem': 'isii', 'givePlayerGold': 'i', 'takePlayerGold': 'i', 'checkPlayerGold': '',
    'checkPlayerMinGold': '',
}


def _selftest():
    assert load_limit(46, 0, 0) == I.f_bits(171.0)
    assert load_limit(10000, 0, 0) == F_9999
    assert mission_rows_overlapping_skill_pairs() == [0]
    assert scan_cm1_vars(0, None, 0xFFFFFFFF) == -1
    assert scan_cm1_vars(1, lambda n: 0, 0) == 9
    print('ref_script_items self-test passed')


if __name__ == '__main__':
    _selftest()
