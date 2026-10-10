#!/usr/bin/env python3
"""ref_player.py - reference model of one tick of the player: Player_run 0x1a5030 of
Champions: Return to Arms (SLUS_209.73, US v2.00) and the small helpers only it uses.

A research tool, not game code.  Every method was written from the instruction sequence at
the address given in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_player.py.  docs/spec/player-tick.md is the prose
version.  Standard library only; no game data is embedded (strings and tables the code
compares with are read through the memory the caller supplies).

How the model sees the game
    Player_run chases pointers all the time (player object -> record -> item -> item
    definition, ability record -> skill object -> virtual table, target handle -> node ->
    creature), so the model works on a memory image rather than on Python records:

        mem     an object with load(addr, size) / store(addr, size, value), little endian
                (Memory below is one; tools/difftest_player.py wraps the interpreter's)
        player  address of the Player object (0x590 bytes)

    The record is found as the original finds it (g_players + slot * 0x4c30), the pad as
    the original chooses it, globals at their own addresses.  Floats are raw 32-bit
    patterns and go through tools/ref_core.py's R5900 arithmetic.

What is outside the model
    Everything the tick calls that is not listed under "modelled helpers" is a callback:
    movement, animation, damage, skill objects, sound, effects, inventory, HUD, lights,
    handle lists, world queries.  EXTERNALS names each one with its address and argument
    list.  A callback is  f(*args) -> result ; callbacks is a dict name -> function, and a
    name that is missing returns zeroes.  Arguments are canonical: integers as unsigned
    32-bit, floats as patterns, a vector as a tuple of three patterns, in the order
    "integer registers, then float registers".  The model records every callback it makes.

    tools/ref_combat.py models Player_recalcDamage and the damage function and
    tools/ref_core.py the math, the generators and the handle lists; this module imports
    ref_core for arithmetic and leaves the combat functions as callbacks so that a caller
    can plug ref_combat in (see combat_callbacks()).

Modelled helpers (run for real by the differential test)
    Player_idleFidget 0x1bc2f8, player_canBlock 0x1bee48, Player_tryBlockMove 0x1bf150,
    Player_hasAnim 0x1bf230, player_getSkillRank 0x1bf330, player_getPassiveLevel 0x1bed48,
    Player_updateCast 0x1a3f70, Player_regenHealth 0x1b3b90, Player_regenMana 0x1b3900,
    Player_tickEnchantTimers 0x1bc560, Player_weaponSwapInput 0x1bb718,
    Player_castSkill 0x1a42b8, GameObject_rand 0x1509d0.
    Any of them can be turned back into a callback by naming it in Tick(..., external=...).

Result
    Tick(mem, player, callbacks).run() returns an Outcome: .writes (every store, in order,
    as (address, size, value)), .calls (every callback, in order, as (name, args)), .seed
    (the shared seed 0x404464 afterwards), .draws (how many shared-seed draws were made).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


# ---------------------------------------------------------------------------------------
# Addresses.  Globals marked (machine) are not lockstep state: see docs/spec/player-tick.md
# section 8 for what each one gates.
# ---------------------------------------------------------------------------------------
G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
G_PADS, PAD_SIZE = 0x41BFD8, 0x58       # lockstep pad per slot: +8 held, +0xc pressed, +0x14/+0x18 stick
G_ZERO_PAD = 0x8667F0
G_SIM_FRAME = 0x44FDCC
G_WORLD = 0x44FDC8
G_LEVEL_FLAGS = 0x44FE08                # level flag word: 0x100 breath effect, 0x10000000 no combat
G_RAND_SEED = 0x404464                  # shared seed (in the sync hash)
G_SEED3 = 0x404468                      # third generator (machine)
G_NETWORK_MODE = 0x402791               # s8
G_CUTSCENE_ACTIVE = 0x44FCD0            # s8
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_LIGHT_SCALE = 0x4F83F4                # float, script decayPlayerLights
G_MEDAL_MISSION, G_MEDAL_DIALOG_TICKS = 0x4F713C, 0x4F7114
G_MENU_LOCKOUT = 0x41B4FC               # (machine) D26
G_PAUSED = 0x41B4F4
G_RECALL_COUNTDOWN = 0x41B51D           # s8
G_ARENA_WORD = 0x503890
G_HUD_BYTE = 0x4F66C8                   # s8, written by hud_addTasks
G_SPELL_SELECTOR = 0x41B818             # int[4] (machine) K1
G_KILL_PLANE = 0x4F7188
G_DEBUG_INVULNERABLE = 0x44F20C
G_POTIONS_ONLY = 0x4F7128               # script explodePotionsOnly
G_PVP_MODE_A = 0x4F711C
G_DEAD_COUNTDOWN = 0x4F84A8             # s16[4]
G_LEVEL_NAME = 0x41B721
G_SKILL_TABLE = 0x41B170
G_BTN_ATTACK, G_BTN_ABILITY_A, G_BTN_ABILITY_B = 0x41B980, 0x41B990, 0x41B9A0
G_BTN_BLOCK, G_BTN_POTION_A, G_BTN_POTION_B, G_BTN_SWAP = 0x41B9D0, 0x41BA10, 0x41BA20, 0x41BA30
G_AURA_LEVEL, G_AURA_COLOR, G_AURA_FADE_RATE = 0x4D8A40, 0x4D8A50, 0x4D8A90
G_AURA_FADE, G_AURA_DIR, G_AURA_LIGHT_COLOR = 0x4D8AA0, 0x4D8AB0, 0x8659A0
G_HUD_NOTICE_TIMER, G_HUD_NOTICE_ROW = 0x41B828, 0x41B8A8       # int[4][8] each
G_CLASS_SKILLS = 0x4EF538               # per class 0xa88 bytes: 48 entries of 0x38, u64 mask first
G_TIMED_MODIFIERS = 0x537C08            # s32 list of modifier ids, -1 ends it
G_PARTICLE_BUILT_A, G_PARTICLE_DEF_A = 0x4EF3F4, 0x864EB0
G_PARTICLE_BUILT_B, G_PARTICLE_DEF_B = 0x4EF3F8, 0x864F00
G_MODEL_TABLE = 0x3E9CE0                # rows of 16 bytes; +8 and +0xc are read here
A_DOUBLE_DEATH_FRAME = 0x5362A0         # a double constant the dead state compares with

# String constants the code passes around.  Only their addresses are named here.
S_NEWSTYLE = 0x535E30                   # marks an ability record implemented by a Skill object
S_JUMPGATE, S_MISSIONMENU = 0x535EB8, 0x535EC8
S_INNPIT = 0x535ED8
S_BURNINGHANDS = 0x536250
S_SOUND_LUMP = 0x535EF0

# Float constants (patterns)
ZERO, HALF, ONE = 0x00000000, 0x3F000000, 0x3F800000
MINUS_ONE = 0xBF800000
F_2M16 = 0x37800000                     # 1 / 65536
F_1_60 = 0x3C888888                     # 1 / 60, truncated
F_60 = 0x42700000
F_0_1 = 0x3DCCCCCC                      # 0.1, truncated


class Ext:
    """One callback: address (0 for a virtual call), integer argument kinds, number of
    float arguments, result kind.  Integer kinds: i value, p address, v pointer to three
    floats (passed as a tuple), s pointer to a C string (passed by address), o pointer the
    callee fills with three floats (not passed; the callback returns them), O the same but
    optional (the model passes 1 or 0), n pointer to an object-pointer array the callee
    fills, h pointer to a handle-list head the callee fills, - not an argument.
    Result kinds: i integer, f float, n nothing."""

    def __init__(self, addr, ints='', floats=0, ret='i', note=''):
        self.addr, self.ints, self.floats, self.ret, self.note = addr, ints, floats, ret, note


EXTERNALS = {
    # --- creature and movement
    'Creature_run': Ext(0x112948, 'pp', 0, 'n', '(player, model +0x544)'),
    'Creature_applyKnockback': Ext(0x115EB8, 'p', 1, 'n', '(player; scale)'),
    'Creature_moveToDest': Ext(0x119F38, 'p', 0, 'n'),
    'Player_move': Ext(0x1B4020, 'pipV', 0, 'i', '(player, mode, pad, ext velocity or 0) -> event bits'),
    'obj_updateGridCell': Ext(0x14F028, 'p', 0, 'n'),
    'Player_findTarget': Ext(0x1BB3C8, 'p', 1, 'n', '(player; range) links the target at +0x234'),
    'Player_interact': Ext(0x1B2640, 'ppi', 0, 'i', '(player, pad, displayOnly)'),
    'Player_processDamage': Ext(0x1B2CC0, 'p', 0, 'n'),
    'Player_usePotion': Ext(0x1B9CB8, 'piiii', 0, 'i', '(player, kind, 0, 0, -1)'),
    # --- animation
    'Player_animStep': Ext(0x1B9520, 'p', 1, 'i', '(player; speed) -> event bits'),
    'anim_start': Ext(0x16CFE0, 'ppi', 1, 'n', '(state, anm, flags; blend in)'),
    'anim_startBlendInOut': Ext(0x16CEB0, 'ppi', 2, 'n', '(state, anm, flags; blend in, blend out)'),
    'anim_findTrackByFlag': Ext(0x171178, 'pi', 0, 'i', '(state, mask) -> track index or negative'),
    'model_getAttachPoint': Ext(0x1754A0, 'pvipioO', 1, 'n', '(model, pos, facing, anim state, index, out, dir out; scale)'),
    'res_find': Ext(0x17365C, 'pp', 0, 'i', '(lump name, entry name) -> entry'),
    'libc_sprintf': Ext(0x3B7EF0, '-pi', 0, 's', '(buffer, format, one integer or none) -> the text'),
    # --- combat
    'Player_meleeHit': Ext(0x1B6A98, 'ppii', 1, 'n', '(player, target, flag, 0; scale 0)'),
    'Player_recalcDamage': Ext(0x1B7158, 'ppi', 0, 'n', '(player, weapon item, 1)'),
    'world_damageInRadius': Ext(0x161270, 'pviiii', 2, 'n'),
    'world_collectObjectsInBox': Ext(0x14A928, 'vvni', 0, 'i', '(min, max, out array, capacity)'),
    'world_collectObjectsInArc': Ext(0x1614F0, 'ivihi', 2, 'n'),
    'item_getModifiedField1a': Ext(0x103F88, 'p', 0, 'i'),
    'item_getDamageRange': Ext(0x104100, 'p--i', 0, 'n'),
    'item_getResourceIndex': Ext(0x1083F8, 'p', 0, 'i'),
    'creature_findSpellByType': Ext(0x11A710, 'pp', 0, 'i', '(creature, type info) -> spell or 0'),
    'creature_addSpell': Ext(0x11A838, 'pp', 0, 'n'),
    'SpellBash_typeinfo': Ext(0x3CE6B0, '', 0, 'i', 'type-info getter'),
    'SpellAncestralCall_typeinfo': Ext(0x3CE9BC, '', 0, 'i', 'type-info getter'),
    'SpellShieldBash_typeinfo': Ext(0x3D0258, '', 0, 'i', 'type-info getter'),
    'SpellBattleCry_typeinfo': Ext(0x3D08DC, '', 0, 'i', 'type-info getter'),
    'SpellBlessed_typeinfo': Ext(0x3CE700, '', 0, 'i', 'type-info getter'),
    'Player_pickAttackAnim': Ext(0x1BBA88, 'pi', 0, 'n', '(player, weapon class): one shared draw'),
    'SpellAncestralCall_queryFor': Ext(0x2E1470, 'ppiq', 0, 'i'),
    'SpellBattleCry_affects': Ext(0x302C04, 'ppq', 0, 'i'),
    'SkillBerserkerRage_swingFactor': Ext(0x2FE324, 'pipi', 0, 'f'),
    'SpellBlessed_getStat0': Ext(0x2DFDB8, 'p', 0, 'i'),
    'SkillRegeneration_getStat0': Ext(0x2F14F0, 'pi', 0, 'i'),
    # --- objects made by the tick
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i', '(size) -> block or 0'),
    'LightEffect_ctor': Ext(0x201BD8, 'pvpi', 8, 'n'),
    'MissileWeapon_ctor': Ext(0x150EE4, 'piiivvip', 0, 'n'),
    'playerProjectile_ctor': Ext(0x1BEF58, 'piivvipi', 0, 'n'),
    'Root_ctor': Ext(0x293704, 'pvipi', 1, 'n'),
    'UnholyAura_ctor': Ext(0x29486C, 'pvpi', 1, 'n'),
    'GroundPoundEffect_ctor': Ext(0x2C74AC, 'pvipip', 0, 'n'),
    'particleDef_ctor': Ext(0x18F3D0, 'ipiiiiii', 2, 'n'),
    'particle_spawn': Ext(0x18F3F8, 'ipvv', 0, 'n'),
    'fx_spawn': Ext(0x1EF270, 'iv', 0, 'n', '(effect id, position)'),
    'decal_add': Ext(0x19F110, 'viii', 1, 'n'),
    'water_disturb': Ext(0x189514, 'pv', 2, 'i'),
    # --- handle lists
    'handle_clear': Ext(0x1A1698, 'p', 0, 'n', '(list head)'),
    'handle_link': Ext(0x1A1738, 'ppp', 0, 'n', '(list head, back list, object)'),
    'handle_removeNode': Ext(0x1A1868, 'p', 0, 'i'),
    'iter_begin': Ext(0x1A1A48, '-pi', 0, 'i', '(iterator, list head, mask) -> first node'),
    'iter_next': Ext(0x1A1B38, '-', 0, 'i', '(iterator) -> next node'),
    'iter_end': Ext(0x1A1AE8, '-i', 0, 'n'),
    # --- lights, sound, HUD, pad
    'light_relink': Ext(0x14A528, 'p', 0, 'n'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n'),
    'light_link2': Ext(0x148BC8, 'p', 0, 'n'),
    'Player_weaponTrails': Ext(0x1BC768, 'p', 0, 'n'),
    'Player_footstep': Ext(0x1BEEC8, 'p', 0, 'n'),
    'player_voice': Ext(0x1B7BA8, 'ii', 0, 'n', '(slot, kind)'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'i'),
    'sound_stop': Ext(0x213EA0, 'i', 0, 'n'),
    'pad_rumble': Ext(0x174088, 'i', 2, 'n'),
    'pad_buttonValue': Ext(0x174D80, 'pi', 0, 'f'),
    'hud_showMessage': Ext(0x1D92A0, 'piii', 0, 'n'),
    'hud_countActiveNotices': Ext(0x1DACF4, 'ii', 0, 'i'),
    'text_lookup': Ext(0x173C84, 'p', 0, 'i'),
    'str_prefixDiffers': Ext(0x159C20, 'pp', 0, 'i'),
    # --- inventory and scripts
    'inventory_removeItem': Ext(0x1C1CB0, 'iiii', 0, 'n'),
    'inventory_equipItem': Ext(0x1C27C0, 'ipi', 0, 'n'),
    'player_recalcLoad': Ext(0x1BEC10, 'i', 0, 'n'),
    'script_runByName': Ext(0x1ED694, 'p', 0, 'n'),
    # --- state of the machine and of the session
    'net_getCamFlag': Ext(0x13E110, 'i', 0, 'i', '(slot): carried in the input record'),
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i', '(slot) (machine)'),
    'net_isSlotActive': Ext(0x13DD40, 'i', 0, 'i'),
    'game_isFrozen': Ext(0x1EBDF8, '', 0, 'i'),
    'memcard_isBusy': Ext(0x217518, '', 0, 'i', '(machine)'),
    'dialog_isOpen': Ext(0x22FBC0, '', 0, 'i'),
    'dialog_22fbd0': Ext(0x22FBD0, 'p', 0, 'i', '(position) -> facing to turn to while a dialog is open'),
    'task_isRunning': Ext(0x19E5E8, 'p', 0, 'i', '(name)'),
    # --- virtual calls: (this, ...)
    'Player.v17': Ext(0, 'pv', 0, 'n', 'set aim point'),
    'Player.v20': Ext(0, 'pp', 0, 'i', 'isEnemy(other)'),
    'Player.v26': Ext(0, 'piv', 0, 'n', 'turn toward a point'),
    'Player.v39': Ext(0, 'pi', 0, 'i', 'skill rank for a skill id'),
    'Creature.v12': Ext(0, 'pivp', 1, 'n', 'being aimed at (kind 2 ranged, 3 melee)'),
    'Vehicle.v17': Ext(0, 'pipp', 0, 'n', 'rider pose'),
    'Skill.v1': Ext(0, 'pp', 0, 'i', 'canUse(player)'),
    'Skill.v2': Ext(0, 'pipvi', 0, 'i', 'cast(rank, player, pos, facing) -> spell or 0'),
    'Skill.v5': Ext(0, 'pi', 0, 'f', 'mana cost for a rank'),
    'Skill.v10': Ext(0, 'pii', 0, 'i', 'getStat(index, rank)'),
    'Spell.v1': Ext(0, 'pi', 0, 'n', 'end(reason)'),
    'Spell.v4': Ext(0, 'p', 0, 'i', 'query used by the leap states'),
}


class Memory:
    """Sparse little-endian memory.  Unwritten bytes read from `under` (an object with
    load(addr, size)) or as zero.  Every store is appended to .log."""

    def __init__(self, under=None):
        self.bytes, self.under, self.log = {}, under, []

    def load(self, addr, size):
        value = 0
        get = self.bytes.get
        for i in range(size):
            b = get(addr + i)
            if b is None:
                b = self.under.load(addr + i, 1) if self.under is not None else 0
            value |= b << (8 * i)
        return value

    def poke(self, addr, size, value):
        """Store without logging (set-up, and what a callback changes)."""
        for i in range(size):
            self.bytes[addr + i] = (value >> (8 * i)) & 0xFF

    def store(self, addr, size, value):
        value &= (1 << (8 * size)) - 1
        self.log.append((addr, size, value))
        self.poke(addr, size, value)

    def write_bytes(self, addr, data):
        for i, b in enumerate(data):
            self.bytes[addr + i] = b


class Outcome:
    def __init__(self, writes, calls, seed, draws, returned):
        self.writes, self.calls, self.seed, self.draws, self.returned = writes, calls, seed, draws, returned

    def written(self):
        """Final value of every byte the tick stored: {address: byte}."""
        out = {}
        for addr, size, value in self.writes:
            for i in range(size):
                out[addr + i] = (value >> (8 * i)) & 0xFF
        return out


class Leave(Exception):
    """The original returns from the middle of the function."""


class Tick:
    """One call of Player_run on `player`.  See the module docstring."""

    HELPERS = ('Player_idleFidget', 'player_canBlock', 'Player_tryBlockMove', 'Player_hasAnim',
               'player_getSkillRank', 'player_getPassiveLevel', 'Player_updateCast',
               'Player_regenHealth', 'Player_regenMana', 'Player_tickEnchantTimers',
               'Player_weaponSwapInput', 'Player_castSkill')

    def __init__(self, mem, player, callbacks=None, external=()):
        self.mem, self.P = mem, player
        self.cb = callbacks if callbacks is not None else {}
        self.external = set(external)
        self.calls, self.writes, self.draws = [], [], 0
        self.pad = 0
        self.instant = 0            # the local at sp+0xe4c: 0, a button mask, or 0xffffffff

    # ---- memory ------------------------------------------------------------------------
    def u8(self, a):
        return self.mem.load(a, 1)

    def s8(self, a):
        return s8(self.mem.load(a, 1))

    def u16(self, a):
        return self.mem.load(a, 2)

    def s16(self, a):
        return s16(self.mem.load(a, 2))

    def u32(self, a):
        return self.mem.load(a, 4)

    def s32(self, a):
        return s32(self.mem.load(a, 4))

    def u64(self, a):
        return self.mem.load(a, 8)

    def _w(self, a, size, v):
        v &= (1 << (8 * size)) - 1
        self.writes.append((a, size, v))
        self.mem.store(a, size, v)

    def w8(self, a, v):
        self._w(a, 1, v)

    def w16(self, a, v):
        self._w(a, 2, v)

    def w32(self, a, v):
        self._w(a, 4, v)

    def vec(self, a):
        return (self.u32(a), self.u32(a + 4), self.u32(a + 8))

    def cstr(self, a, limit=256):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(a + len(out))
            if b == 0:
                break
            out.append(b)
        return bytes(out)

    def strcmp(self, a, b):
        """libc_strcmp 0x3b8534 on two addresses: zero when the strings are equal."""
        return 0 if self.cstr(a) == self.cstr(b) else 1

    def strstr(self, hay, needle):
        """libc_strstr 0x3b96a8: non-zero when needle occurs in hay."""
        return 1 if self.cstr(needle) in self.cstr(hay) else 0

    # ---- callbacks ---------------------------------------------------------------------
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        kind = EXTERNALS[name.split(':')[0]].ret if name.split(':')[0] in EXTERNALS else 'i'
        ints = EXTERNALS[name.split(':')[0]].ints if name.split(':')[0] in EXTERNALS else ''
        zero3 = (0, 0, 0)
        outs = [zero3 for k in ints if k in 'oO'] + [[] for k in ints if k in 'nh'] + [0 for k in ints if k == 'q']
        if outs:
            return outs[0] if len(outs) == 1 and kind == 'n' else tuple(([0] if kind != 'n' else []) + outs)
        return 0

    def vcall(self, cls, obj, table_offset, slot, *args):
        """A virtual call: table pointer at obj + table_offset, eight bytes per slot (a
        16-bit `this` adjustment, then the function at +4)."""
        table = self.u32(obj + table_offset)
        this = (obj + self.s16(table + 8 * slot)) & M32
        return self.call('%s.v%d' % (cls, slot), this, *args)

    def helper(self, name, function, *args):
        if name in self.external:
            return self.call(name, *args)
        return function(*args)

    # ---- generators --------------------------------------------------------------------
    def draw(self):
        """One draw from the shared seed 0x404464 (the three inline instructions)."""
        seed = (self.u32(G_RAND_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_RAND_SEED, seed)
        self.draws += 1
        return seed >> 16

    def draw3(self):
        """One draw from the third generator 0x404468 (not lockstep)."""
        seed = (self.u32(G_SEED3) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_SEED3, seed)
        return seed >> 16

    def obj_rand(self, obj=None):
        """GameObject_rand 0x1509d0: the object's own generator at +0x44."""
        obj = self.P if obj is None else obj
        if 'GameObject_rand' in self.external:
            return self.call('GameObject_rand', obj)
        seed = (self.u32(obj + 0x44) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(obj + 0x44, seed)
        return seed >> 16

    # ---- small accessors ---------------------------------------------------------------
    @property
    def slot(self):
        return self.s32(self.P + 0x3C8)

    @property
    def R(self):
        return (G_PLAYERS + self.slot * REC_SIZE) & M32

    def is_copy(self):
        return bool(self.u32(self.P + 0xC) & 0x20000)

    def anim_name(self, offset):
        """A pointer from the player's animation table (+0x24): 0x68 bytes per weapon
        animation class (record +0x4a86), `offset` inside the row."""
        cls = self.s8(self.R + 0x4A86)
        return self.u32(self.u32(self.P + 0x24) + cls * 0x68 + offset)

    def selected_ability(self):
        """The ability record of the button pressed last (record +0x4a60 picks the index
        byte +0x4a84 or +0x4a85); None when +0x4a60 is neither 0 nor 1."""
        R = self.R
        which = self.s16(R + 0x4A60)
        if which == 0:
            index = self.s8(R + 0x4A84)
        elif which == 1:
            index = self.s8(R + 0x4A85)
        else:
            return None
        return (R + 0x4440 + index * 0x68) & M32

    def skill_of(self, ability):
        return self.u32(G_SKILL_TABLE + 4 * self.s16(ability + 0x20))

    def item_modifier(self, item, wanted, field):
        """The first of an item's four modifiers (item +0x24, 8 bytes each) whose id is
        `wanted`; returns the s16 at +field of it, or 0."""
        for k in range(4):
            if self.s16(item + 0x24 + 8 * k) == wanted:
                return self.s16(item + 0x24 + 8 * k + field)
        return 0

    def hud_notice(self, index, frames):
        """Start HUD notice `index` of this slot: timer, then the row from
        hud_countActiveNotices (0x1a88a0 and four more sites)."""
        self.w32(G_HUD_NOTICE_TIMER + self.slot * 0x20 + index * 4, frames)
        row = self.call('hud_countActiveNotices', self.slot, index)
        self.w32(G_HUD_NOTICE_ROW + self.slot * 0x20 + index * 4, row)

    def sound(self, entry, obj):
        """res_find in the sound lump, then sound_playOnObject at volume 1.0."""
        seq = self.call('res_find', S_SOUND_LUMP, entry)
        self.call('sound_playOnObject', seq, obj, ONE)

    # =====================================================================================
    # Player_run 0x1a5030
    # =====================================================================================
    def run(self):
        returned = 'end'
        try:
            self.top()
            self.switch()
            self.tail()
        except Leave as leave:
            returned = str(leave)
        return Outcome(self.writes, self.calls, self.u32(G_RAND_SEED), self.draws, returned)

    def top(self):
        """0x1a5030-0x1a5e80: everything before the state switch."""
        P = self.P
        u32, s32_, w32 = self.u32, self.s32, self.w32
        # breath puff on levels with flag 0x100 (0x1a5038-0x1a5210): own-generator draws only
        if (u32(G_LEVEL_FLAGS) & 0x100) and not ((u32(G_SIM_FRAME) ^ self.s8(P + 0x230)) & 0xE0) \
                and not (self.obj_rand() & 1):
            while True:
                v = []
                for _ in range(3):
                    u = C.mul(C.from_int(self.obj_rand()), F_2M16)
                    v.append(C.sub(C.add(u, u), ONE))
                if not C.lt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))):
                    break
            d = [C.add(x, x) for x in v]
            x = C.add(u32(P + 0x10), d[0])
            z = C.add(u32(P + 0x18), d[2])
            y = C.add(u32(P + 0x14), d[1])
            r = C.mul(C.mul(C.from_int(self.obj_rand()), F_2M16), 0x41400000)
            z = C.add(z, C.add(u32(P + 0x20), r))
            self.call('fx_spawn', 0x11, (x, y, z))
        self.call('Creature_run', P, u32(P + 0x544))
        self.call('Creature_applyKnockback', P, ONE)
        R = self.R
        w32(P + 0x228, u32(R + 0xAC))
        # the white light at +0x4c8 (0x1a5284-0x1a5328)
        rng = C.mul(u32(G_LIGHT_SCALE), 0x43700000)
        if s32_(G_ALIVE_COUNT) == 2:
            rng = C.mul(rng, 0x3F28F5C2)
        w32(P + 0x4E4, rng)
        w32(P + 0x4EC, rng)
        inv = C.div(ONE, C.mul(rng, rng))
        w32(P + 0x4F0, inv)
        w32(P + 0x4E8, inv)
        self._w(P + 0x4F8, 8, self.u64(P + 0x10))
        w32(P + 0x500, u32(P + 0x18))
        w32(P + 0x500, C.add(u32(P + 0x500), 0x42800000))
        self.call('light_relink', P + 0x4C8)
        self.call('light_unlink', P + 0x504)
        # hit immunity (record +0x4c27), real players only; spawn protection +0x4b4
        if not self.is_copy():
            R = self.R
            self.w8(R + 0x4C27, self.u8(R + 0x4C27) - 1)
            R = self.R
            if self.s8(R + 0x4C27) < 0:
                self.w8(R + 0x4C27, 0)
        if self.s16(P + 0x4B4) != 0:
            v = (self.u16(P + 0x4B4) - 1) & 0xFFFF
            self.w16(P + 0x4B4, v)
            if s16(v) < 0x14:
                w32(P + 0xC, u32(P + 0xC) & ~2)
        # idle voice (0x1a53bc-0x1a54c0): one shared draw when it fires
        R = G_PLAYERS + s32_(P + 0x3C8) * REC_SIZE
        hp_rec = R                                    # $23: fixed for the rest of the tick
        self.R0 = hp_rec
        if C.lt(ZERO, u32(hp_rec + 0xAC)):
            if self.call('net_getCamFlag', self.slot) or self.s8(G_CUTSCENE_ACTIVE) \
                    or self.call('game_isFrozen') or u32(G_PADS + self.slot * PAD_SIZE + 8):
                self.w16(P + 0x4B0, 0)
            else:
                slot = self.slot
                v = (self.u16(P + 0x4B0) + 1) & 0xFFFF
                limit = self.s16(P + 0x4B2)
                self.w16(P + 0x4B0, v)
                if limit < s16(v):
                    self.call('player_voice', slot, 1)
                    self.w16(P + 0x4B0, 0)
                    d = self.draw()
                    self.w16(P + 0x4B2, ((d % 30) + self.slot * 45) * 60 + 0xE10)
        if self.s16(P + 0x4AE) > 0:
            self.w16(P + 0x4AE, self.u16(P + 0x4AE) - 1)
        # low-health rumble (0x1a54d4-0x1a55a0)
        if self.s8(G_NETWORK_MODE) == 0:
            rumble = True
        elif u32(G_MEDAL_MISSION) != 0 and u32(G_MEDAL_DIALOG_TICKS) != 0:
            rumble = False
        else:
            rumble = not self.call('memcard_isBusy')
        if rumble and C.lt(ZERO, u32(hp_rec + 0xAC)) \
                and C.lt(C.div(u32(hp_rec + 0xAC), u32(hp_rec + 0xB0)), 0x3ECCCCCC):
            phase = u32(G_SIM_FRAME) & 0x3F
            if phase == 0:
                self.call('pad_rumble', self.slot, 0x3DF5C28F, ONE)
            if phase == 0x14:
                self.call('pad_rumble', self.slot, 0x3DB851EB, ONE)
        # scripted control (+0x231): only the animation runs (0x1a55a4-0x1a5610)
        if self.s8(P + 0x231) != 0:
            state = s32_(P + 0x58C)
            if state == 0:
                self.call('Player_animStep', P, ONE)
            elif state == 1:
                if self.call('Player_animStep', P, ONE) & 1:
                    self.call('Player_footstep', P)
                self.call('Creature_moveToDest', P)
            w32(P + 0x488, 0)
            raise Leave('scripted')
        w32(P + 0x4C4, ONE)
        if self.s8(P + 0x464) == 0 and not (u32(P + 0xC) & 8):
            self.call('Player_weaponTrails', P)
        self.pad = pad = self.choose_pad()
        self.helper('Player_idleFidget', self.idle_fidget, P, pad)
        if self.call('dialog_isOpen'):
            if C.lt(ZERO, u32(self.R + 0xAC)):
                target = self.call('dialog_22fbd0', P + 0x10)
                self.w16(P + 0x38, C.angle_approach(0x3E000000, MINUS_ONE, MINUS_ONE, self.s16(P + 0x38), target))
        # aura fade and level (0x1a57e4-0x1a58a0); these globals are read only by drawing
        s4 = self.slot * 4
        fade = C.add(u32(G_AURA_FADE + s4), u32(G_AURA_FADE_RATE + s4))
        w32(G_AURA_FADE + s4, fade)
        if C.lt(ONE, fade):
            w32(G_AURA_FADE + s4, ONE)
        if C.lt(u32(G_AURA_FADE + s4), ZERO):
            w32(G_AURA_FADE + s4, ZERO)
        w32(G_AURA_LEVEL + s4, s32_(G_AURA_LEVEL + s4) + s32_(G_AURA_DIR + s4) * 3)
        s4 = self.slot * 4
        if s32_(G_AURA_LEVEL + s4) > 0x50:
            w32(G_AURA_LEVEL + s4, 0x50)
            s4 = self.slot * 4
        if s32_(G_AURA_LEVEL + s4) < 0:
            w32(G_AURA_LEVEL + s4, 0)
        w32(P + 0x4C0, 0)
        w32(P + 0x4BC, 0)
        # minimum time between attacks +0x48c: 0.33 with a bow or nothing, 0.15 otherwise
        weapon = u32(hp_rec + 0x4434 + 4 * self.s8(hp_rec + 0x4A7C))
        self.weapon0 = weapon
        if weapon == 0:
            w32(P + 0x48C, 0x3EA8F5C2)
        else:
            if self.s8(u32(weapon) + 0x1E) == 4:
                w32(P + 0x48C, 0x3EA8F5C2)
            else:
                w32(P + 0x48C, 0x3E199999)
            if self.s8(u32(weapon) + 0x1E) == 4 and C.lt(u32(P + 0x48C), ZERO):
                w32(P + 0x48C, ZERO)
        # potion buttons (0x1a5948-0x1a59f4): pressed bits of the chosen pad
        slot = self.slot
        if C.lt(ZERO, u32(G_PLAYERS + slot * REC_SIZE + 0xAC)):
            pressed = u32(pad + 0xC)
            if pressed & u32(G_BTN_POTION_A + slot * 4):
                self.use_potion(0)
                slot = self.slot
                pressed = u32(pad + 0xC)
            if pressed & u32(G_BTN_POTION_B + slot * 4):
                if not self.strstr(G_LEVEL_NAME, S_INNPIT):
                    self.use_potion(1)
        flags = u32(P + 0xC)
        # which ability button is "the" ability button (record +0x4a80), real players only
        if not (flags & 0x20000):
            cur = u32(hp_rec + 0x4A80)
            if cur != 0:
                s4 = self.slot * 4
                if cur != u32(G_BTN_ABILITY_A + s4) and cur != u32(G_BTN_ABILITY_B + s4):
                    w32(hp_rec + 0x4A80, 0)
            if s32_(P + 0x58C) != 5:
                s4 = self.slot * 4
                pressed = u32(pad + 0xC)
                a = u32(G_BTN_ABILITY_A + s4)
                if pressed & a:
                    w32(hp_rec + 0x4A80, a)
                    self.w16(hp_rec + 0x4A60, 0)
                else:
                    b = u32(G_BTN_ABILITY_B + s4)
                    if pressed & b:
                        w32(hp_rec + 0x4A80, b)
                        self.w16(hp_rec + 0x4A60, 1)
                flags = u32(P + 0xC)
        # class 0 pays mana while status counter 2 (+0x374) runs (0x1a5ab4-0x1a5b0c)
        if s32_(hp_rec + 0x50) == 0 and u32(P + 0x374) != 0 and s32_(P + 0x58C) != 0xC:
            mana = C.sub(u32(hp_rec + 0xC0), C.mul(u32(hp_rec + 0xC4), 0x3ADA740D))
            w32(hp_rec + 0xC0, mana)
            if C.le(mana, ZERO):
                w32(hp_rec + 0xC0, ZERO)
                w32(P + 0x374, 0)
        if not (flags & 8):
            self.helper('Player_regenHealth', self.regen_health, P)
            self.helper('Player_regenMana', self.regen_mana, P)
            self.helper('Player_tickEnchantTimers', self.tick_enchant_timers, P)
            plane = u32(G_KILL_PLANE)
            if C.lt(0xC7AFC800, plane) and C.lt(u32(P + 0x18), plane):
                if u32(G_DEBUG_INVULNERABLE) == 0:
                    w32(P + 0xC, u32(P + 0xC) | 2)
                w32(P + 0x2DC, 0)
                w32(P + 0xC8, 0x49742400)
            self.call('Player_processDamage', P)
            # the gate around weapon swap and interact (K1, D26): 0x1a5b98-0x1a5c20
            if u32(G_PAUSED) == 0 and u32(G_MENU_LOCKOUT) == 0 and not self.call('dialog_isOpen') \
                    and not self.call('net_getCamFlag', self.slot) and not self.is_copy():
                self.helper('Player_weaponSwapInput', self.weapon_swap_input, P, pad, 0)
                if u32(G_SPELL_SELECTOR + self.slot * 4) == 0:
                    self.call('Player_interact', P, pad, 0)
        self.instant_abilities()
        # block request +0x454 (0x1a5e2c-0x1a5e7c)
        slot = self.slot
        w32(P + 0x454, 0)
        if u32(pad + 8) & u32(G_BTN_BLOCK + slot * 4):
            if not (u32(G_LEVEL_FLAGS) & 0x10000000):
                if self.helper('player_canBlock', self.can_block, slot, u32(P + 0x58C)):
                    w32(P + 0x454, 1)

    def choose_pad(self):
        """0x1a5640-0x1a5764: the slot's lockstep pad, or the all-zero pad."""
        P, u32 = self.P, self.u32
        slot = self.slot
        if u32(G_MENU_LOCKOUT) != 0 and self.s8(G_NETWORK_MODE) == 0:
            return G_ZERO_PAD
        if self.call('dialog_isOpen') or self.s16(P + 0x4B4) != 0 or self.s8(G_RECALL_COUNTDOWN) != 0 \
                or u32(G_MEDAL_DIALOG_TICKS) != 0 or self.call('net_getCamFlag', slot) \
                or self.call('task_isRunning', S_JUMPGATE) or self.call('task_isRunning', S_MISSIONMENU) \
                or not self.call('net_isSlotActive', slot) or (u32(P + 0xC) & 0x400000) \
                or u32(G_ARENA_WORD) != 0 or self.s8(G_HUD_BYTE) != 0 \
                or C.le(u32(G_PLAYERS + slot * REC_SIZE + 0xAC), ZERO):
            return G_ZERO_PAD
        return G_PADS + slot * PAD_SIZE

    def instant_abilities(self):
        """0x1a5c24-0x1a5e28: abilities of kind 7 fire without an animation.  Leaves
        self.instant = 0, the mask of the button whose instant ability is ready, or
        0xffffffff when the forced record (+0x488) is one."""
        P, pad, u32 = self.P, self.pad, self.u32
        forced = u32(P + 0x488)
        self.instant = 0
        if forced == 0 and (u32(pad + 8) & 0xF000):
            return
        if self.s16(P + 0x4AE) != 0:
            self.w32(P + 0x488, 0)
            return
        for i in range(2):
            if forced:
                ability = forced
            else:
                slot = self.slot
                mask = u32((G_BTN_ABILITY_A, G_BTN_ABILITY_B)[i] + slot * 4)
                if not (u32(pad + 0xC) & mask):
                    continue
                rec = slot * REC_SIZE
                ability = (rec + self.s8(G_PLAYERS + rec + 0x4A84 + i) * 0x68 + G_PLAYERS + 0x4440) & M32
            if ability == 0 or self.s8(ability + 0x25) != 7:
                if forced:
                    return
                continue
            if self.strcmp(ability, S_NEWSTYLE):
                return
            skill = self.skill_of(ability)
            if not self.vcall('Skill', skill, 0x60, 1, P):
                self.w32(P + 0x488, 0)
                return
            rank = self.vcall('Player', P, 0x48, 39, self.s16(ability + 0x20))
            cost = self.vcall('Skill', skill, 0x60, 5, rank)
            slot = self.slot
            if not C.le(cost, u32(G_PLAYERS + slot * REC_SIZE + 0xC0)):
                self.call('player_voice', slot, 4)
                self.w32(P + 0x488, 0)
                return
            self.instant = M32
            if u32(P + 0x488) != 0:
                return
            self.instant = u32((G_BTN_ABILITY_A, G_BTN_ABILITY_B)[i] + slot * 4)
            return

    def use_potion(self, kind):
        return self.call('Player_usePotion', self.P, kind, 0, 0, M32)

    def tail(self):
        """0x1ac460-0x1ac7a4: aura light, Player_updateCast, record countdowns."""
        P, u32, w32 = self.P, self.u32, self.w32
        slot = self.slot
        if C.lt(ZERO, u32(G_AURA_FADE + slot * 4)):
            light = P + 0x504
            self.call('light_link2', light)
            ability = self.selected_ability()
            if ability is None:
                raise Leave('ability button index')
            if self.strcmp(ability, S_BURNINGHANDS) == 0 and self.s8(G_RECALL_COUNTDOWN) == 0:
                c = C.cos16(self.s16(P + 0x38))
                w32(P + 0x534, C.add(u32(P + 0x10), C.mul(c, 0x42200000)))
                s = C.sin16(self.s16(P + 0x38))
                y = C.add(u32(P + 0x14), C.mul(s, 0x42200000))
            else:
                x = u32(P + 0x10)
                y = u32(P + 0x14)
                w32(P + 0x534, x)
            w32(P + 0x538, y)
            w32(P + 0x53C, C.add(u32(P + 0x18), 0x42100000))
            self.call('light_relink', light)
            wave = C.sin16(s16(u32(G_SIM_FRAME) * 6000))
            radius = C.from_int(C.to_int(C.mul(wave, 0x40800000)) + 0xB4)
            slot = self.slot
            colour = G_AURA_LIGHT_COLOR + slot * 16
            w32(light + 0x1C, radius)
            w32(light + 0x24, radius)
            inv = C.div(ONE, C.mul(radius, radius))
            w32(light + 0x28, inv)
            w32(light + 0x20, inv)
            fade = u32(G_AURA_FADE + slot * 4)
            c = [C.to_int(C.mul(C.from_int(self.s32(colour + 4 * k)), fade)) for k in range(4)]
            self.w16(P + 0x514, c[3])
            self.w16(P + 0x50E, c[0])
            self.w16(P + 0x510, c[1])
            self.w16(P + 0x512, c[2])
            self.w16(P + 0x516, c[0])
            self.w16(P + 0x518, c[1])
            self.w16(P + 0x51A, c[2])
            self.w16(P + 0x51C, c[3])
        slot = self.slot
        if C.lt(ZERO, u32(G_PLAYERS + slot * REC_SIZE + 0xAC)):
            self.helper('Player_updateCast', self.update_cast, P, self.pad)
        if not self.is_copy():
            R = self.R
            if self.u16(R + 0x4BCA) != 0:
                self.w16(R + 0x4BCA, self.u16(R + 0x4BCA) - 1)
            if self.u8(R + 0x4BC8) != 0:
                self.w8(R + 0x4BC8, self.u8(R + 0x4BC8) - 1)
                R = self.R
                if self.u8(R + 0x4BC8) == 0:
                    w32(P + 0xC, u32(P + 0xC) & 0xFFBFFFFF)
            R = self.R
            if self.u8(R + 0x4BC9) != 0:
                self.w8(R + 0x4BC9, self.u8(R + 0x4BC9) - 1)
        if self.s32(P + 0x58C) != 5:
            w32(P + 0x488, 0)

    # =====================================================================================
    # Helpers
    # =====================================================================================
    def idle_fidget(self, P, pad):
        """Player_idleFidget 0x1bc2f8: one shared draw every tick the player has exactly
        four animation tracks and the stick is (nearly) centred or no fidget is running."""
        u32 = self.u32
        ly, lx = u32(pad + 0x18), u32(pad + 0x14)
        length = C.sqrt(C.add(C.mul(lx, lx), C.mul(ly, ly)))
        if C.lt(0x3C23D70A, length) and self.s8(P + 0x463) != 0:
            self.w8(P + 0x463, 0)
            if self.s8(P + 0x118) - 1 < 4:
                return
            i, off = 4, 0x1A0
            while True:
                self.w32(P + 0xC + off, ONE)
                i += 1
                self.w32(P + 0x10 + off, 0xBDAAAAAA)
                off += 0x20
                if self.s8(P + 0x118) - 1 < i:
                    break
            return
        if self.s8(P + 0x118) != 4:
            return
        if self.draw() >= 0xE2:
            return
        if self.s8(P + 0x463) != 0:
            return
        R = G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE
        name = {1: 0x5375D8, 2: 0x5375E8, 3: 0x5375F8, 4: 0x537608, 5: 0x537BF8, 7: 0x537618}.get(
            self.s8(R + 0x4A86), 0x537628)
        obj = u32(R + 0x43D8)
        anm = self.call('res_find', u32(u32(obj + 0x24)), name)
        self.call('anim_start', P + 0x114, anm, 1, HALF)
        self.w8(P + 0x463, 1)

    def can_block(self, slot, state):
        """player_canBlock 0x1bee48: not in state 0xb, not with a bow in the two-hand slot;
        needs a one-hand weapon, a two-hand weapon or a shield."""
        R = G_PLAYERS + s32(slot) * REC_SIZE
        two_hand = self.u32(R + 0x43F8)
        if s32(state) == 0xB:
            return 0
        if two_hand != 0 and self.s8(self.u32(two_hand) + 0x1E) == 4:
            return 0
        if self.u32(R + 0x43F8) == 0 and self.u32(R + 0x43F0) == 0:
            return 1 if self.u32(R + 0x43FC) != 0 else 0
        return 1

    def try_block_move(self, P, pad):
        """Player_tryBlockMove 0x1bf150: swap button pressed while blocking -> state 0xb."""
        if self.u32(G_LEVEL_FLAGS) & 0x10000000:
            return
        if self.u8(P + 0x47F) == 0:
            return
        slot = self.s32(P + 0x3C8)
        if not (self.u32(pad + 0xC) & self.u32(G_BTN_SWAP + slot * 4)):
            return
        if not (self.u32(pad + 8) & self.u32(G_BTN_BLOCK + slot * 4)):
            return
        self.w32(P + 0x58C, 0xB)
        cls = self.s8(G_PLAYERS + slot * REC_SIZE + 0x4A86)
        table = self.u32(P + 0x24)
        self.w8(P + 0x481, 0x2F)
        self.call('anim_startBlendInOut', P + 0x114, self.u32(table + cls * 0x68 + 0xA4), 0x808, F_0_1, 0x3E999999)

    def has_anim(self, P, name):
        """Player_hasAnim 0x1bf230: does one of the tracks play this animation."""
        anm = self.call('res_find', self.u32(self.u32(P + 0x24)), name)
        for i in range(max(self.s8(P + 0x118), 0)):
            if self.u32(P + 0x11C + 0x20 * i) == (anm & M32):
                return 1
        return 0

    def skill_rank(self, slot, skill_id):
        """player_getSkillRank 0x1bf330: (id, rank) pairs at record +0x4b08, id -1 ends."""
        R = G_PLAYERS + s32(slot) * REC_SIZE
        a = R + 0x4B08
        while self.s16(a) != -1:
            if self.s16(a) == s16(skill_id):
                return self.s16(a + 2)
            a += 4
        return 0

    def passive_level(self, slot, mask):
        """player_getPassiveLevel 0x1bed48: level byte (record +0xef + n) of the class
        skill whose 64-bit mask equals `mask`; negative bytes read as 0."""
        if (slot & M32) > 4:
            return 0
        R = G_PLAYERS + slot * REC_SIZE
        table = G_CLASS_SKILLS + self.s32(R + 0x50) * 0xA88
        for n in range(0x30):
            if self.u64(table + n * 0x38) == (mask & M64):
                level = self.s8(R + 0xEF + n)
                return 0 if level < 0 else level
        return 0

    def update_cast(self, P, pad):
        """Player_updateCast 0x1a3f70: aim point from the two hand attach points; ends a
        cast when the ability button is up, the state is not 5, or mana is gone."""
        u32 = self.u32
        pos = self.vec(P + 0x10)
        a = self.call('model_getAttachPoint', u32(P + 0x544), pos, self.s16(P + 0x38), P + 0x114, 0, 0, ONE)
        pos = self.vec(P + 0x10)
        b = self.call('model_getAttachPoint', u32(P + 0x544), pos, self.s16(P + 0x38), P + 0x114, 1, 0, ONE)
        x = C.mul(C.add(a[0], b[0]), HALF)
        y = C.mul(C.add(a[1], b[1]), HALF)
        z = C.mul(C.add(a[2], b[2]), HALF)
        base = u32(P + 0x18)
        # |z - base| > 58.0, compared in software double precision
        diff = C.f2d(C.sub(z, base))
        if C.dcmp(diff, 0) < 0:
            diff = C.dsub(0, diff)
        if C.dcmp(diff, 0x404D000000000000) > 0:
            z = C.add(base, 0x42680000)
        self.vcall('Player', P, 0x48, 17, (x, y, z))
        if u32(P + 0x488) != 0:
            return
        R = G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE
        held = u32(pad + 8) & u32(R + 0x4A80)
        if held and self.s32(P + 0x58C) == 5 and not C.le(u32(R + 0xC0), ZERO):
            return
        track = s32(self.call('anim_findTrackByFlag', P + 0x114, 0x8000))
        if track >= 0 and not C.le(ONE, u32(P + 0x124 + track * 0x20)):
            return
        self.w32(G_AURA_DIR + self.s32(P + 0x3C8) * 4, M32)
        self.w32(G_AURA_FADE_RATE + self.s32(P + 0x3C8) * 4, 0xBD4CCCCC)
        if track >= 0:
            weight = P + 0x12C + track * 0x20
            self.w32(weight, C.fmin(u32(weight), ONE))
            self.w32(P + 0x130 + track * 0x20, 0xBD6EEEEE)
        self.w8(P + 0x47B, 0)
        if self.s32(P + 0x58C) == 5:
            self.w32(P + 0x58C, 2)
        held_spell = u32(P + 0x588)
        if held_spell != 0:
            spell = u32(held_spell + 0xC)
            if spell != 0:
                self.vcall('Spell', spell, 0x14, 1, 3)

    def regen_health(self, P):
        """Player_regenHealth 0x1b3b90 (real players only): natural regeneration, then the
        potion amount still to be delivered (record +0xb4 at +0xb8 per tick)."""
        u32, w32 = self.u32, self.w32
        if self.u32(P + 0xC) & 0x20000:
            return
        slot = self.s32(P + 0x3C8)
        R = G_PLAYERS + slot * REC_SIZE
        hp = u32(R + 0xAC)
        if C.le(hp, ZERO):
            return
        top = u32(R + 0xB0)
        if C.lt(hp, top):
            amount = C.mul(top, 0x38D1B717)
            level = C.from_int(self.helper('player_getPassiveLevel', self.passive_level, slot, 0x10))
            bonus = self.s8(P + 0x477)
            if C.lt(ZERO, level):
                amount = C.mul(amount, C.add(C.mul(level, F_0_1), 0x3F999999))
            amount = C.add(amount, C.mul(C.from_int(bonus), 0x38D1B717))
            for i in range(17):
                item = u32(R + 0x43F0 + 4 * i)
                if item and u32(item):
                    v = self.item_modifier(item, 0xB, 2)
                    amount = C.mul(amount, C.add(C.mul(C.from_int(v), 0x3C23D70A), ONE))
            hp = C.add(u32(R + 0xAC), amount)
            top = u32(R + 0xB0)
            w32(R + 0xAC, hp)
            if C.lt(top, hp):
                w32(R + 0xAC, top)
        pending = u32(R + 0xB4)
        if C.lt(ZERO, pending):
            rate = u32(R + 0xB8)
            hp = C.add(u32(R + 0xAC), rate)
            w32(R + 0xAC, hp)
            if C.lt(top, hp):
                w32(R + 0xAC, top)
                pending = ZERO
                w32(R + 0xB4, ZERO)
            left = C.sub(pending, rate)
            w32(R + 0xB4, left)
            if C.lt(left, ZERO):
                w32(R + 0xB4, ZERO)

    def regen_mana(self, P):
        """Player_regenMana 0x1b3900 (real players only).  Class 0 has no natural gain."""
        u32, w32 = self.u32, self.w32
        if self.u32(P + 0xC) & 0x20000:
            return
        slot = self.s32(P + 0x3C8)
        R = G_PLAYERS + slot * REC_SIZE
        if C.le(u32(R + 0xAC), ZERO):
            return
        mana, top = u32(R + 0xC0), u32(R + 0xC4)
        if C.lt(mana, top):
            amount = C.mul(top, 0x38D1B717)
            level = C.from_int(self.helper('player_getPassiveLevel', self.passive_level, slot, 0x200))
            bonus = self.s8(P + 0x475)
            if C.lt(ZERO, level):
                amount = C.mul(amount, C.add(C.mul(level, 0x3E199999), 0x3F999999))
            amount = C.add(amount, C.mul(C.from_int(bonus), 0x38D1B717))
            if self.s32(R + 0x50) == 0:
                amount = ZERO
            for i in range(17):
                item = u32(R + 0x43F0 + 4 * i)
                if item and u32(item):
                    v = self.item_modifier(item, 0xC, 2)
                    amount = C.mul(amount, C.add(C.mul(C.from_int(v), 0x3C23D70A), ONE))
            spell = self.call('creature_findSpellByType', P, self.call('SpellBlessed_typeinfo'))
            if spell:
                v = s32(self.call('SpellBlessed_getStat0', spell))
                amount = C.add(amount, C.mul(amount, C.mul(C.from_int(v), 0x3C23D70A)))
            rank = self.helper('player_getSkillRank', self.skill_rank, self.s32(P + 0x3C8), 0x13)
            if rank:
                v = s32(self.call('SkillRegeneration_getStat0', u32(G_SKILL_TABLE + 4 * 0x13), rank))
                amount = C.add(amount, C.mul(amount, C.mul(C.from_int(v), 0x3C23D70A)))
            mana = C.add(u32(R + 0xC0), amount)
            top = u32(R + 0xC4)
            w32(R + 0xC0, mana)
            if C.lt(top, mana):
                w32(R + 0xC0, top)
        pending = u32(R + 0xC8)
        if C.lt(ZERO, pending):
            rate = u32(R + 0xBC)
            mana = C.add(u32(R + 0xC0), rate)
            w32(R + 0xC0, mana)
            if C.lt(top, mana):
                w32(R + 0xC0, top)
                pending = ZERO
                w32(R + 0xC8, ZERO)
            left = C.sub(pending, rate)
            w32(R + 0xC8, left)
            if C.lt(left, ZERO):
                w32(R + 0xC8, ZERO)

    def tick_enchant_timers(self, P):
        """Player_tickEnchantTimers 0x1bc560 (real players only): the timed modifiers (ids
        in the list at 0x537c08) of the 17 equipped items lose one frame; at 0 the
        modifier's id becomes -1."""
        if self.u32(P + 0xC) & 0x20000:
            return
        R = G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE
        for i in range(17):
            item = self.u32(R + 0x43F0 + 4 * i)
            if not item or not self.u32(item):
                continue
            entry = G_TIMED_MODIFIERS
            while self.s32(entry) != -1:
                wanted = self.s32(entry)
                entry += 4
                frames = self.item_modifier(item, wanted, 6)
                if frames < 1:
                    continue
                left = frames - 1
                value = self.item_modifier(item, wanted, 2)
                third = self.item_modifier(item, wanted, 4)
                for k in range(4):
                    at = item + 0x24 + 8 * k
                    if self.s16(at) == -1 or self.s16(at) == wanted:
                        self.w16(at, wanted)
                        self.w16(at + 2, value)
                        self.w16(at + 4, third)
                        self.w16(at + 6, left)
                        break
                if left < 1:
                    for k in range(4):
                        at = item + 0x24 + 8 * k
                        if self.s16(at) == wanted:
                            self.w16(at, -1)

    def weapon_swap_input(self, P, pad, force):
        """Player_weaponSwapInput 0x1bb718: the swap button toggles the weapon set (record
        +0x4a7c) in state 2 and equips that set; always ends in Player_recalcDamage."""
        u32 = self.u32
        result = 0
        slot = self.s32(P + 0x3C8)
        R = G_PLAYERS + slot * REC_SIZE
        tries = 0
        if self.s32(P + 0x58C) in (0xB, 8):
            self.w8(R + 0x4A7D, 0)
            slot = self.s32(P + 0x3C8)
        if u32(pad + 8) & u32(G_BTN_BLOCK + slot * 4):
            if self.can_block(slot, self.s32(P + 0x58C)) and force == 0:
                return 0
        if not (u32(G_LEVEL_FLAGS) & 0x10000000):
            if self.s32(P + 0x58C) not in (2, 3):
                if (u32(pad + 0xC) & u32(G_BTN_SWAP + slot * 4)) or force:
                    self.w8(R + 0x4A7D, 1)
            if self.s32(P + 0x58C) == 2:
                if self.s8(R + 0x4A7D) == 0:
                    if (u32(pad + 0xC) & u32(G_BTN_SWAP + self.s32(P + 0x3C8) * 4)) or force:
                        while True:
                            b = (self.u8(R + 0x4A7C) - 1) & 0xFF
                            self.w8(R + 0x4A7C, b)
                            if s8(b) < 0:
                                self.w8(R + 0x4A7C, 1)
                            tries += 1
                            if u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C)) != 0 or tries >= 3:
                                break
                else:
                    self.w8(R + 0x4A7D, 0)
                    while True:
                        b = (self.u8(R + 0x4A7C) + 1) & 0xFF
                        self.w8(R + 0x4A7C, b)
                        if s8(b) > 1:
                            self.w8(R + 0x4A7C, 0)
                        tries += 1
                        if u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C)) != 0 or tries >= 3:
                            break
                which = self.s8(R + 0x4A7C)
                item = u32(R + 0x4434 + 4 * which)
                if item != 0:
                    if u32(R + 0x43F8) != item and u32(R + 0x43F0) != item:
                        result = 1
                        self.call('inventory_equipItem', self.s32(P + 0x3C8), item, 0)
                        if self.s8(R + 0x4A7C) == 1 \
                                and self.s8(u32(u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C))) + 0x1E) == 6:
                            self.hud_notice(7, 0xF0)
                    if which == 0:
                        second = u32(R + 0x443C)
                        if second != 0 and u32(R + 0x43F4) != second:
                            result = 1
                            self.call('inventory_equipItem', self.s32(P + 0x3C8), second, 0)
        self.call('Player_recalcDamage', P, u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C)), 1)
        return result

    def hands_midpoint(self, P, limit_height):
        """The point between attach points 0 and 1 (two model_getAttachPoint calls)."""
        a = self.call('model_getAttachPoint', self.u32(P + 0x544), self.vec(P + 0x10), self.s16(P + 0x38),
                      P + 0x114, 0, 0, ONE)
        b = self.call('model_getAttachPoint', self.u32(P + 0x544), self.vec(P + 0x10), self.s16(P + 0x38),
                      P + 0x114, 1, 0, ONE)
        return a, b

    def cast_skill(self, P, ability):
        """Player_castSkill 0x1a42b8: canUse, aim, cast (Skill slot 2), recast time, mana.
        For the prediction copy only skills with flag bit 0 run, and their spell is ended
        at once."""
        u32 = self.u32
        if self.s16(P + 0x4AE) > 0 or ability == 0:
            return
        if self.strcmp(ability, S_NEWSTYLE):
            return
        skill = self.skill_of(ability)
        copy = bool(u32(P + 0xC) & 0x20000)
        if not (u32(skill + 4) & 1) and copy:
            return
        if not self.vcall('Skill', skill, 0x60, 1, P):
            return
        a, b = self.hands_midpoint(P, True)
        base = u32(P + 0x18)
        z = C.mul(C.add(a[2], b[2]), HALF)
        x = C.mul(C.add(a[0], b[0]), HALF)
        y = C.mul(C.add(a[1], b[1]), HALF)
        diff = C.f2d(C.sub(z, base))
        if C.dcmp(diff, 0) < 0:
            diff = C.dsub(0, diff)
        if C.dcmp(diff, 0x404D000000000000) > 0:
            z = C.add(base, 0x42680000)
        found = self.call('world_collectObjectsInArc', 0, self.vec(P + 0x10), self.s16(P + 0x38), 0,
                          0x43AA0000, 0x41A00000)
        target = 0
        for obj in found:
            if self.vcall('Player', P, 0x48, 20, obj):
                target = obj
                break
        if target == 0:
            facing = self.s16(P + 0x38)
        else:
            angle = C.atan2_16(C.sub(u32(target + 0x10), u32(P + 0x10)), C.sub(u32(target + 0x14), u32(P + 0x14)))
            facing = s16(0x41C2 - angle)
        rank = self.vcall('Player', P, 0x48, 39, self.s16(ability + 0x20))
        spell = self.vcall('Skill', skill, 0x60, 2, rank, P, (x, y, z), facing)
        if spell:
            if u32(P + 0xC) & 0x20000:
                self.vcall('Spell', spell, 0x14, 1, 3)
            else:
                self.call('creature_addSpell', P, spell)
                if self.s32(skill + 8) == 1:
                    self.call('handle_link', P + 0x588, spell + 4, spell)
        self.w16(P + 0x4AE, self.u16(skill + 0xC))
        rank = self.vcall('Player', P, 0x48, 39, self.s16(ability + 0x20))
        cost = self.vcall('Skill', skill, 0x60, 5, rank)
        if self.s32(skill + 8) == 1:
            cost = C.mul(cost, F_1_60)
        R = G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE
        self.w32(R + 0xC0, C.sub(u32(R + 0xC0), cost))
        self.call('handle_clear', 'stack')

    # =====================================================================================
    # The action-state switch 0x1a5e80
    # =====================================================================================
    def switch(self):
        state = self.u32(self.P + 0x58C)
        handler = {0: self.state_ranged, 1: self.state_melee, 2: self.state_neutral, 3: self.state_hit,
                   4: self.state_dead, 5: self.state_cast, 6: self.state_skill, 7: self.state_jump,
                   8: self.state_block, 9: self.state_rush, 10: self.state_pound, 0xB: self.state_block_move,
                   0xC: self.state_warcry, 0xD: self.state_vehicle, 0xE: self.state_skill}.get(state)
        if handler is not None:
            handler()

    def anim_step(self, speed=ONE):
        return self.call('Player_animStep', self.P, speed)

    def move(self, mode, ext=0):
        return self.call('Player_move', self.P, mode, self.pad, ext)

    def frames(self):
        """Frames since the action started: g_simFrame - player +0x448."""
        return s32(self.u32(G_SIM_FRAME) - self.u32(self.P + 0x448))

    def top_track(self, offset):
        """Address of a field relative to the track count: player + count * 0x20 + offset."""
        return self.P + self.s8(self.P + 0x118) * 0x20 + offset

    def stop_loop_sound(self):
        P = self.P
        if self.s32(P + 0x4A8) != -1:
            self.call('sound_stop', self.u32(P + 0x4A8))
            self.w32(P + 0x4A8, M32)

    def clear_extra_tracks(self):
        P = self.P
        i = 1
        if self.s8(P + 0x119) > 1:
            while True:
                self.w32(P + 0x144 + 0x20 * (i - 1), 0)
                self.w32(P + 0x14C + 0x20 * (i - 1), 0)
                i += 1
                if not i < self.s8(P + 0x119):
                    break

    def slow_scale(self, speed):
        """The slow amount (+0x2fc, 1..60) scales a speed by (60 - slow) / 60."""
        slow = self.u8(self.P + 0x2FC)
        if ((slow - 1) & M32) < 0x3C:
            speed = C.mul(speed, C.mul(C.from_int(0x3C - s8(slow)), F_1_60))
        return speed

    def haste_of(self, item):
        """Modifier 0x14 of an item times 0.045 (0x3d3851eb)."""
        return C.mul(C.from_int(self.item_modifier(item, 0x14, 2)), 0x3D3851EB)

    # ---- state 3: staggered / knocked down (0x1ab1f0) ---------------------------------------
    def state_hit(self):
        P = self.P
        if self.s8(P + 0x47B) == 0:
            if self.s8(P + 0x47F) != 0:
                self.w32(self.top_track(0xF0), 0xBD6EEEEE)
                self.w8(P + 0x47F, 0)
        else:
            self.stop_loop_sound()
            self.w32(G_AURA_DIR + self.slot * 4, M32)
            self.w32(G_AURA_FADE_RATE + self.slot * 4, 0xBD4CCCCC)
            self.w32(self.top_track(0xF0), 0xBD6EEEEE)
            self.w8(P + 0x47B, 0)
        self.anim_step()
        if not (self.u16(P + 0x11A) & 8):
            self.w8(P + 0x480, 0)
            self.w32(P + 0x44C, 0)
            self.w32(P + 0x58C, 2)
            self.w32(P + 0x448, self.u32(G_SIM_FRAME))
            self.w8(P + 0x3CC, 0)

    # ---- state 4: dead (0x1ab2f0) ------------------------------------------------------------
    def state_dead(self):
        P = self.P
        self.stop_loop_sound()
        pvp = self.u32(G_PVP_MODE_A)
        self.w32(G_AURA_DIR + self.slot * 4, M32)
        self.w32(G_AURA_FADE_RATE + self.slot * 4, 0xBD4CCCCC)
        if pvp == 0:
            if C.dcmp(C.i2d(self.frames()), self.u64(A_DOUBLE_DEATH_FRAME)) == 0:
                a, b = self.hands_midpoint(P, False)
                z = self.u32(P + 0x18)
                angle = self.draw()
                size = self.draw()
                x = C.mul(C.add(a[0], b[0]), HALF)
                y = C.mul(C.add(a[1], b[1]), HALF)
                self.call('decal_add', (x, y, z), s32(angle), 0, 1, C.from_int(size % 10 + 0x19))
        if self.s16(G_DEAD_COUNTDOWN + self.slot * 2) > 1:
            self.anim_step()

    # ---- state 7: jump (0x1a5f98) ------------------------------------------------------------
    def state_jump(self):
        P = self.P
        go = True
        if C.lt(self.u32(self.top_track(0x114)), 0x4080A3D6):
            go = self.s8(P + 0x47D) != 0
        if go:
            if self.s8(P + 0x47E) == 0:
                if self.u64(P + 0xA8) & 0x2000000000000000:
                    pos = (C.sub(self.u32(P + 0x10), ZERO), self.u32(P + 0x14), C.sub(self.u32(P + 0x18), 0x41400000))
                    self.call('water_disturb', self.u32(G_WORLD), pos, 0x453B8000, 0x41C00000)
                self.call('player_voice', self.slot, 0xD)
                self.w8(P + 0x47E, 1)
                self.w32(P + 0x30, 0x43B40000)
                self.w32(P + 0x18, C.add(self.u32(P + 0x18), 0x3CA3D70A))
            self.w8(P + 0x47D, 1)
        rise = self.u32(P + 0x30)
        if C.lt(ZERO, rise):
            self.w32(P + 0x30, C.sub(rise, 0x4157FFFE))
        self.move(0)

    # ---- state 9: rush (0x1a6bf0) ------------------------------------------------------------
    def state_rush(self):
        P = self.P
        self.w32(P + 0x188, F_0_1)
        self.w32(P + 0x18C, ONE)
        self.w32(P + 0x190, 0)
        self.anim_step(0x40000000)
        self.move(2)

    # ---- state 0xb: block move (0x1a6588) ----------------------------------------------------
    def state_block_move(self):
        P = self.P
        if self.s8(G_RECALL_COUNTDOWN) != 0:
            raise Leave('recall during block move')
        if self.anim_step() & 5:
            self.call('Player_footstep', P)
        if self.u64(P + 0xA8) & 0x2000000000000000:
            pos = (C.sub(self.u32(P + 0x10), ZERO), self.u32(P + 0x14), C.sub(self.u32(P + 0x18), 0x41400000))
            self.call('water_disturb', self.u32(G_WORLD), pos, 0x447A0000, 0x41400000)
        self.w32(P + 0x55C, 0x10)
        if not (self.u16(P + 0x11A) & 8):
            if not (self.u32(self.pad + 8) & self.u32(G_BTN_BLOCK + self.slot * 4)):
                self.w32(P + 0x58C, 2)
                self.w32(self.top_track(0x110), 0xBDAAAAAA)
                self.w32(self.top_track(0xF0), 0xBDAAAAAA)
                self.w8(P + 0x47F, 0)
            else:
                self.w8(P + 0x47F, 1)
                self.w32(P + 0x58C, 8)
        self.move(1)

    # ---- state 0xc: war cry, older ability id 0xe (0x1a66d8) ---------------------------------
    def state_warcry(self):
        P = self.P
        self.anim_step()
        if self.s32(P + 0xF0) == s32(self.u32(G_SIM_FRAME) - 0x1E):
            block = self.call('pool_new', 0xBC)
            if block:
                pos = (C.add(self.u32(P + 0x10), ZERO), self.u32(P + 0x14), C.add(self.u32(P + 0x18), 0x42100000))
                self.call('LightEffect_ctor', block, pos, P, 0,
                          0x437F0000, 0x431B0000, ZERO, 0xC2C00000, ZERO, ZERO, ZERO, ZERO)
        if not (self.u16(P + 0x11A) & 0x20):
            self.w32(P + 0x58C, 2)
            self.w32(self.top_track(0x10C), ONE)
            self.w32(P + 0xF0, self.u32(G_SIM_FRAME))
            self.w32(self.top_track(0x110), 0xBDAAAAAA)

    # ---- state 0xd: riding a vehicle (0x1a5ea8) ----------------------------------------------
    def state_vehicle(self):
        P = self.P
        if self.is_copy() and (self.u32(self.pad + 0xC) & 0x10):
            self.w32(P + 0x58C, 2)
            return
        self.anim_step()
        vehicle = self.u32(P + 0x540)
        self.vcall('Vehicle', vehicle, 0x48, 17, self.slot, P + 0x10, P + 0x38)
        self.call('obj_updateGridCell', P)
        if self.helper('Player_hasAnim', self.has_anim, P, 0x535EE0):
            return
        if self.strcmp(G_LEVEL_NAME, 0x535E40) == 0:
            return
        lump = self.u32(self.u32(P + 0x24))
        name = 0x535EE0 if self.call('res_find', lump, 0x535EE0) else 0x535808
        anm = self.call('res_find', self.u32(self.u32(P + 0x24)), name)
        self.call('anim_start', P + 0x114, anm, 3, F_0_1)

    # ---- state 10: ground pound, older ability id 0xc (0x1a6818) -----------------------------
    def state_pound(self):
        P = self.P
        events = self.anim_step()
        if events & 1:
            self.call('player_voice', self.slot, 10)
            self.sound(0x535EF8, self.u32(self.R + 0x43D8))
        if self.is_copy():
            return
        if events & 7:
            if events & 1:
                turn = -0x4000
            elif events & 2:
                turn = 0
            else:
                turn = (events & 4) << 12
            x = C.add(self.u32(P + 0x10), C.mul(C.cos16(self.s16(P + 0x38) + turn), 0x41C00000))
            y = C.add(self.u32(P + 0x14), C.mul(C.sin16(self.s16(P + 0x38) + turn), 0x41C00000))
            z = C.add(self.u32(P + 0x18), F_60)
            self.call('world_damageInRadius', P, (x, y, z), 1, 0x40000, 1, 0, ZERO, 0x42400000)
        if events & 8:
            block = self.call('pool_new', 0x9C)
            if block:
                rank = self.helper('player_getSkillRank', self.skill_rank, self.slot, 0x26)
                self.call('GroundPoundEffect_ctor', block, self.vec(P + 0x10), self.u16(P + 0x38),
                          self.u32(G_SKILL_TABLE + 4 * 0x26), rank, P)
        if not (self.u16(P + 0x11A) & 8):
            self.w32(P + 0x58C, 2)
            self.w32(self.top_track(0x10C), ONE)
            self.w32(P + 0x448, self.u32(G_SIM_FRAME))
            self.w32(self.top_track(0x110), 0xBDAAAAAA)

    # ---- states 6 and 0xe: under control of a skill (0x1a6a28) -------------------------------
    def state_skill(self):
        P = self.P
        if self.is_copy():
            self.anim_step()
        if self.s32(P + 0x58C) == 0xE:
            return
        self.move(5, (0, 0, 0))
        if self.is_copy():
            return
        R = self.R
        if not (self.u32(self.pad + 0xC) & self.u32(R + 0x4A80)):
            return
        ability = self.selected_ability() or 0
        if self.s16(ability + 0x20) == -1:
            ability = 0
        if ability == 0:
            return
        if self.s16(ability + 0x20) == 0x31:
            spell = self.call('creature_findSpellByType', P, self.call('SpellBash_typeinfo'))
            if spell and self.vcall('Spell', spell, 0x14, 4):
                self.w32(P + 0x450, 1)
        if self.s16(ability + 0x20) == 0x22:
            spell = self.call('creature_findSpellByType', P, self.call('SpellShieldBash_typeinfo'))
            if spell:
                if not self.vcall('Spell', spell, 0x14, 4):
                    return
                self.w32(P + 0x450, 1)

    # ---- state 8: blocking (0x1a60e0) --------------------------------------------------------
    def unit_sphere_shared(self):
        """Three shared draws per try, repeated while the point is outside the unit ball."""
        while True:
            v = []
            for _ in range(3):
                u = C.mul(C.from_int(self.draw()), F_2M16)
                v.append(C.sub(C.add(u, u), ONE))
            if not C.lt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))):
                return v

    def state_block(self):
        P, pad = self.P, self.pad
        R0 = self.R0
        table = self.u32(P + 0x24)
        row = self.s8(self.R + 0x4A86) * 0x68
        restart = False
        if not self.helper('Player_hasAnim', self.has_anim, P, self.u32(self.u32(P + 0x24) + row + 0xA0)):
            restart = not self.helper('Player_hasAnim', self.has_anim, P, self.u32(self.u32(P + 0x24) + row + 0x80))
        self.anim_step()
        if not self.helper('Player_hasAnim', self.has_anim, P, self.u32(self.u32(P + 0x24) + row + 0x98)):
            self.call('anim_start', P + 0x114, self.anim_name(0x9C), 0x2801, F_0_1)
        slot = self.slot
        self.w32(P + 0x55C, 0x10)
        if not (self.u32(pad + 8) & self.u32(G_BTN_BLOCK + slot * 4)):
            if C.le(ONE, self.u32(self.top_track(0x104))) and self.s8(P + 0x118) < 7:
                self.w32(R0 + 0x4A5C, 0)
                self.w8(P + 0x47F, 0)
                self.w32(P + 0x58C, 2)
                self.w32(P + 0x454, 0)
                self.w32(self.top_track(0x110), 0xBDAAAAAA)
                self.w32(self.top_track(0xF0), 0xBDAAAAAA)
        else:
            if self.s8(P + 0x47F) == 0 or restart:
                self.w8(P + 0x47F, 1)
                self.call('anim_start', P + 0x114, self.anim_name(0x84), 0x803, F_0_1)
                self.w32(P + 0x58C, 8)
                slot = self.slot
            self.w32(R0 + 0x4A5C, C.sub(self.u32(R0 + 0x4A5C), F_1_60))
        del table
        if s32(self.helper('player_getSkillRank', self.skill_rank, slot, 0x3B)) > 0:
            a, b = self.hands_midpoint(P, False)
            mid = tuple(C.mul(C.add(a[k], b[k]), HALF) for k in range(3))
            v = self.unit_sphere_shared()
            velocity = tuple(C.mul(x, 0x41200000) for x in v)
            if self.u32(G_PARTICLE_BUILT_A) == 0:
                self.call('particleDef_ctor', 0, G_PARTICLE_DEF_A, 0xF3, 0x11, 0xF0, 0xEA, 0xE5, 0x1B,
                          0x41B5BE76, 0x4119DB22)
                self.w32(G_PARTICLE_BUILT_A, 1)
            self.call('particle_spawn', 0, G_PARTICLE_DEF_A, mid, velocity)
        self.move(1)
        self.helper('Player_tryBlockMove', self.try_block_move, P, pad)

    # ---- state 2: neutral (0x1a6c30) ---------------------------------------------------------
    def old_arrow_notices(self):
        """Low-ammunition notice (20 or fewer left) and, for real players, the "no
        ammunition" voice and notice.  0x1a7d5c-0x1a7e28 and 0x1a7590-0x1a7670."""
        ammo = self.u32(self.R + 0x4410)
        if ammo and ((self.u16(ammo + 4) - 1) & M32) < 0x14:
            self.hud_notice(6, 0xF0)

    def state_neutral(self):
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        R0 = self.R0
        level_flags = G_LEVEL_FLAGS
        w32(P + 0x484, 0)
        if self.s8(P + 0x482) != 0:
            slot = self.slot
            forced = u32(P + 0x488)
            Rs = G_PLAYERS + slot * REC_SIZE
            ability = forced
            if forced == 0:
                ability = self.selected_ability()
                if ability is None:
                    return
            start = False
            if self.s8(ability + 0x25) == 2:
                if (forced != 0 or (u32(pad + 0xC) & u32(Rs + 0x4A80))) and self.s8(P + 0x118) >= 4:
                    if not (u32(level_flags) & 0x10000000):
                        start = self.s16(P + 0x4AE) == 0
                    elif self.s16(P + 0x4AE) == 0:
                        self.call('player_voice', slot, 6)
            elif ((u32(pad + 8) & u32(Rs + 0x4A80)) or u32(P + 0x450) != 0 or forced != 0) \
                    and C.lt(ONE, u32(Rs + 0xC0)):
                if not (u32(level_flags) & 0x10000000):
                    start = self.s16(P + 0x4AE) == 0
                elif self.s16(P + 0x4AE) == 0:
                    self.call('player_voice', slot, 6)
            # offline only: the quick-spell selector vetoes a start (K1's sister test)
            if self.s8(G_NETWORK_MODE) == 0 and u32(G_SPELL_SELECTOR + self.slot * 4) != 0 and u32(P + 0x488) == 0:
                start = False
            if start:
                if self.s16(ability + 0x20) == -1:
                    start = False
                else:
                    Rn = self.R
                    if self.u8(Rn + 0x4BC9) != 0:
                        start = False
                    elif u32(G_POTIONS_ONLY) != 0:
                        start = False
                        text = self.call('text_lookup', 0x535F10)
                        self.call('hud_showMessage', text, 0xB4, M32, 0)
                    elif self.s16(ability + 0x20) == 0x25:
                        if self.s8(Rs + 0x4A86) in (4, 6):
                            start = False
                            text = self.call('text_lookup', 0x535F20)
                            self.call('hud_showMessage', text, 0xB4, self.slot, 0)
                    elif C.eq(u32(ability + 0x2C), 0x4479C000):
                        if C.lt(u32(Rn + 0xC0), u32(Rn + 0xC4)):
                            start = False
            w32(P + 0x450, 0)
            if start and self.s8(ability + 0x24) != 0:
                if self.strcmp(ability, S_NEWSTYLE) == 0:
                    skill = self.skill_of(ability)
                    rank = self.vcall('Player', P, 0x48, 39, self.s16(ability + 0x20))
                    cost = self.vcall('Skill', skill, 0x60, 5, rank)
                    if self.s32(skill + 8) == 1:
                        cost = C.mul(cost, HALF)
                elif self.s16(ability + 0x20) == 0x25:
                    level = s32(self.helper('player_getPassiveLevel', self.passive_level, self.slot, 0x20000))
                    cost = C.add(C.mul(C.from_int(level - 1), 0x407FFFB0), 0x41D00000)
                else:
                    cost = u32(ability + 0x2C)
                if C.le(cost, u32(self.R + 0xC0)) or C.eq(cost, 0x4479C000):
                    if self.neutral_start_ability(ability, cost, Rs):
                        return
                else:
                    self.call('player_voice', self.slot, 4)
        # ---- attack, shot, block (0x1a76c0) ----
        slot = self.slot
        mask = u32(G_BTN_ATTACK + slot * 4)
        if self.u8(P + 0x480) != 0 or u32(P + 0x484) != 0:
            mask = u32(self.R + 0x4A80)
        if not (u32(pad + 8) & u32(self.R + 0x4A80)) and u32(P + 0x488) == 0:
            self.w8(P + 0x480, 0)
        no_combat = bool(u32(level_flags) & 0x10000000)
        if no_combat:
            if (u32(pad + 8) & mask) or (u32(pad + 0xC) & u32(G_BTN_BLOCK + slot * 4)) \
                    or (u32(P + 0x488) != 0 and u32(P + 0x484) != 0):
                self.call('player_voice', slot, 6)
        if not no_combat and self.instant == M32:
            attack = True
        elif u32(P + 0x488) != 0 and u32(P + 0x484) != 0:
            attack = True
        else:
            attack = bool(u32(pad + 8) & (mask | self.instant))
        if attack:
            if self.neutral_attack(mask, slot):
                return
        else:
            wants = u32(P + 0x454) == 1
            if not wants:
                slot = self.slot
                wants = bool(u32(pad + 8) & u32(G_BTN_BLOCK + slot * 4)) and not (u32(level_flags) & 0x10000000)
            else:
                slot = self.slot
            if wants:
                if self.helper('player_canBlock', self.can_block, slot, u32(P + 0x58C)):
                    w32(P + 0x58C, 8)
                else:
                    text = self.call('text_lookup', 0x535FE8)
                    self.call('hud_showMessage', text, 0xB4, self.slot, 0)
        self.helper('Player_tryBlockMove', self.try_block_move, P, pad)
        v = C.add(u32(R0 + 0x4A5C), F_1_60)
        w32(R0 + 0x4A5C, v)
        if C.le(0x3E800000, v):
            w32(R0 + 0x4A5C, HALF)
        events = self.move(0)
        if events & 5:
            self.call('Player_footstep', P)

    def neutral_start_ability(self, ability, cost, Rs):
        """0x1a7020-0x1a76b4: an ability whose mana cost is covered.  Returns True when the
        switch is left at once (states 5, 0xc)."""
        P, u32, w32 = self.P, self.u32, self.w32
        cast = False
        if self.strcmp(ability, S_NEWSTYLE) == 0:
            kind = self.s8(ability + 0x25)
            if kind == 7:
                self.helper('Player_castSkill', self.cast_skill, P, ability)
            elif kind == 8:
                skill = self.skill_of(ability)
                if self.vcall('Skill', skill, 0x60, 1, P):
                    w32(P + 0x484, ability)
                else:
                    w32(P + 0x484, 0)
                    w32(P + 0x488, 0)
            else:
                cast = True
        else:
            sid = self.s16(ability + 0x20)
            if sid == 0xE:                                  # war cry
                cls = self.s8(self.R + 0x4A86)
                fmt = {0: 0x535F30, 5: 0x535F40, 2: 0x535F50, 1: 0x535F60, 3: 0x535F70, 7: 0x535F80}.get(cls)
                name = self.call('libc_sprintf', fmt, None) if fmt else 'stack'
                if u32(P + 0x374) == 0:
                    anm = self.call('res_find', u32(u32(P + 0x24)), name)
                    self.call('anim_startBlendInOut', P + 0x114, anm, 0x22, F_0_1, F_0_1)
                    w32(P + 0x374, 0x30C)
                    w32(P + 0x58C, 0xC)
                    w32(P + 0xF0, u32(G_SIM_FRAME))
                    return True
            elif sid == 0x25:                               # heavy attack
                if u32(P + 0x44C) == 0 and self.s8(P + 0x118) < 6:
                    self.sound(0x535F90, P)
                    w32(P + 0xB0, 0x40333333)
                    w32(P + 0x470, 0x3F5B645A)
                    self.w8(P + 0x460, 0)
                    w32(P + 0x46C, 0)
                    w32(P + 0x448, u32(G_SIM_FRAME))
                    mana = u32(Rs + 0xC0)
                    w32(P + 0x44C, 2)
                    w32(Rs + 0xC0, C.sub(mana, cost))
                    self.clear_extra_tracks()
                    self.call('anim_startBlendInOut', P + 0x114, self.anim_name(0x64), 0x812, F_0_1, F_0_1)
                    if not self.is_copy():
                        block = self.call('pool_new', 0xBC)
                        if block:
                            pos = (C.add(u32(P + 0x10), ZERO), u32(P + 0x14), C.add(u32(P + 0x18), 0x42300000))
                            self.call('LightEffect_ctor', block, pos, 0, 0,
                                      0x437F0000, 0x42CE0000, 0x42E60000, ZERO, ZERO, ZERO, ZERO, ZERO)
                    w32(P + 0x58C, 1)
            elif sid == 0xC:                                # ground pound
                w32(P + 0x58C, 10)
                w32(P + 0x448, u32(G_SIM_FRAME))
                anm = self.call('res_find', u32(u32(P + 0x24)), 0x535FA8)
                self.call('anim_startBlendInOut', P + 0x114, anm, 10, F_0_1, F_0_1)
            elif ((sid - 4) & 0xFFFF) < 3 or sid in (0x13, 0x12):       # the five older arrows
                Rn = self.R
                if self.s8(Rn + 0x4A86) != 4 and u32(Rn + 0x4438) != 0:
                    self.w8(Rn + 0x4A7C, 1)
                Rn = self.R
                if self.s8(Rn + 0x4A86) == 4:
                    if u32(Rn + 0x4410) != 0:
                        w32(P + 0x44C, 1)
                        self.w8(P + 0x480, {4: 1, 5: 2, 6: 3, 0x13: 5, 0x12: 6}[sid])
                    self.old_arrow_notices()
                    if not self.is_copy() and u32(self.R + 0x4410) == 0:
                        self.call('player_voice', self.slot, 5)
                        self.hud_notice(3, 0x78)
                self.w16(P + 0x4AE, self.u16(ability + 0x22))
            else:
                cast = True
        if cast:
            slot = self.slot
            self.w16(P + 0x4AE, self.u16(ability + 0x22))
            self.call('player_voice', slot, 0xB)
            w32(P + 0x58C, 5)
            w32(P + 0x448, u32(G_SIM_FRAME))
            return True
        return False

    def neutral_attack(self, mask, slot):
        """0x1a7804-0x1a7fb8: the attack button (or a ready instant ability) in state 2.
        Returns True when the switch is left at once."""
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        R0 = self.R0
        # a bow or thrown-weapon user of class 0, 2 or 3 may punch instead (own-generator draw)
        if self.s32(R0 + 0x50) in (0, 2, 3) and self.s8(self.R + 0x4A86) in (4, 6):
            ammo = u32(R0 + 0x4410)
            empty = True if ammo == 0 else self.s16(ammo + 4) < 1
            roll = C.mul(C.from_int(self.obj_rand()), F_2M16)
            if C.le(roll, F_0_1) or empty:
                self.call('Player_findTarget', P, 0x42900000)
                node = u32(P + 0x234)
                if node:
                    self.vcall('Player', P, 0x48, 26, 0, self.vec(u32(node + 0xC) + 0x10))
                    aim = self.vec(u32(u32(P + 0x234) + 0xC) + 0x10)
                    if not self.helper('Player_hasAnim', self.has_anim, P, 0x535FB8) \
                            and not self.helper('Player_hasAnim', self.has_anim, P, 0x535FC8):
                        here = self.vec(P + 0x10)
                        w32(P + 0x448, u32(G_SIM_FRAME))
                        d = [C.sub(aim[k], here[k]) for k in range(3)]
                        dist = C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
                        if C.lt(dist, F_60):
                            w32(P + 0x58C, 1)
                            cls = self.s8(R0 + 0x4A86)
                            if cls == 4:
                                anm = self.call('res_find', u32(u32(P + 0x24)), 0x535FB8)
                                self.call('anim_startBlendInOut', P + 0x114, anm, 0x802, F_0_1, F_0_1)
                                w32(P + 0x470, 0x3F666666)
                            elif cls == 6:
                                anm = self.call('res_find', u32(u32(P + 0x24)), 0x535FC8)
                                self.call('anim_startBlendInOut', P + 0x114, anm, 0x802, F_0_1, F_0_1)
                            return True
        go = True
        if u32(G_POTIONS_ONLY) != 0:
            go = False
            if self.s8(self.R + 0x4A86) == 6 and (u32(pad + 8) & mask):
                weapon = u32(R0 + 0x4434 + 4 * self.s8(R0 + 0x4A7C))
                if weapon:
                    go = self.call('str_prefixDiffers', u32(u32(weapon)), 0x535FD8) == 0
            if not go:
                text = self.call('text_lookup', 0x535F10)
                self.call('hud_showMessage', text, 0xB4, M32, 0)
        if go:
            slot = self.slot
            Rs = G_PLAYERS + slot * REC_SIZE
            cls = self.s8(Rs + 0x4A86)
            if cls == 6:                                                    # thrown weapon
                if (u32(pad + 8) & mask) or (u32(P + 0x488) != 0 and u32(P + 0x484) != 0):
                    w32(P + 0x58C, 0)
                    self.w8(P + 0x480, 7)
            elif cls == 4:                                                  # bow
                if u32(P + 0x44C) != 0 or self.instant == M32 or (u32(P + 0x488) != 0 and u32(P + 0x484) != 0) \
                        or (u32(pad + 8) & (mask | self.instant)):
                    w32(P + 0x44C, 0)
                    if u32(Rs + 0x4410) != 0:
                        if u32(P + 0x488) == 0 or u32(P + 0x484) == 0:
                            if C.lt(self.call('pad_buttonValue', pad, u32(G_BTN_ATTACK + self.slot * 4)), 0x3E051EB8) \
                                    and C.lt(self.call('pad_buttonValue', pad, u32(self.R + 0x4A80)), 0x3E051EB8):
                                i = 1
                                if self.s8(P + 0x119) > 1:
                                    while True:
                                        w32(P + 0x150 + 0x20 * (i - 1), 0xBDEEEEEE)
                                        i += 1
                                        if not i < self.s8(P + 0x119):
                                            break
                                self.move(1)
                                self.anim_step()
                                return True
                        slot = self.slot
                        if u32(pad + 8) & u32(G_BTN_ATTACK + slot * 4):
                            self.w8(P + 0x480, 0)
                        w32(P + 0x58C, 0)
                    elif not self.is_copy():
                        for i in range(64):                 # look for ammunition: the last match wins
                            item = Rs + 0x130 + i * 0x48
                            if u32(item) != 0 and self.s8(u32(item) + 0x1C) == 8:
                                w32(Rs + 0x4410, item)
                    if not self.is_copy():
                        self.old_arrow_notices()
                        slot = self.slot
                        if u32(G_PLAYERS + slot * REC_SIZE + 0x4410) == 0:
                            self.call('player_voice', slot, 5)
                            self.hud_notice(3, 0x78)
            else:                                                           # melee
                if C.le(C.mul(u32(P + 0x48C), F_60), C.from_int(self.frames())):
                    if u32(P + 0x44C) != 0 or self.instant == M32 \
                            or (u32(pad + 0xC) & u32(G_BTN_ATTACK + slot * 4)) or self.instant != 0:
                        w32(P + 0x58C, 1)
        state = u32(P + 0x58C)
        if state < 2:
            w32(P + 0x448, u32(G_SIM_FRAME))
            w32(P + 0x470, 0x3FCCCCCC)
            self.w8(P + 0x461, 1)
            w32(P + 0x44C, 0)
            self.w8(P + 0x460, 0)
            w32(P + 0x46C, 0)
            self.clear_extra_tracks()
            self.call('anim_startBlendInOut', P + 0x114, self.anim_name(0x74), 0x12 if state == 0 else 0x802,
                      F_0_1, F_0_1)
            return True
        return False

    # ---- state 1: melee swing and combo (0x1a9678) -------------------------------------------
    COMBO_STEPS = {2: 4, 1: 7, 3: 9, 5: 2, 7: 7}       # by weapon animation class; others 7

    def state_melee(self):
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        frame = u32(G_SIM_FRAME)
        slot = self.slot
        Rm = G_PLAYERS + slot * REC_SIZE
        gap = s32(frame - u32(P + 0x45C))
        w32(P + 0x45C, frame)
        if gap > 0x3C:
            w32(P + 0x458, frame)
        cls = self.s8(Rm + 0x4A86)
        heavy = u32(P + 0x44C) == 2
        if heavy:
            for off, v in ((0x90, 0x8E), (0x92, 0x3A), (0x94, 0x52), (0x9E, 0x40),
                           (0x98, 0x8E), (0x9A, 0x3A), (0x9C, 0x52), (0x96, 0x40)):
                self.w16(P + off, v)
            steps = 1
        else:
            steps = self.COMBO_STEPS.get(cls, 7)
        sweep_frame = 0x7F if (cls == 2 and not heavy) else 0x5E      # entry 4 of the frame table
        weapon = u32(Rm + 0x4434 + 4 * self.s8(Rm + 0x4A7C))
        haste = ZERO
        if weapon:
            other = ZERO
            second = u32(Rm + 0x43F4)
            if second:
                other = self.haste_of(second)
            haste = self.haste_of(weapon)
            if C.lt(haste, other):
                haste = other
            haste = C.add(haste, ZERO)
        if cls == 7:
            haste = C.mul(haste, HALF)
        best = ZERO
        for i in range(self.s32(G_ALIVE_COUNT)):
            obj = u32(G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + 0x43D8)
            spell = self.call('creature_findSpellByType', obj, self.call('SpellAncestralCall_typeinfo'))
            if spell:
                ok, value = self.call('SpellAncestralCall_queryFor', spell, P, 0)
            else:
                obj = u32(G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + 0x43D8)
                spell = self.call('creature_findSpellByType', obj, self.call('SpellBattleCry_typeinfo'))
                if not spell:
                    continue
                ok, value = self.call('SpellBattleCry_affects', spell, P)
            if ok and C.lt(best, value):
                best = value
        speed = ONE
        if not C.eq(best, ZERO):
            speed = C.mul(speed, best)
        if u32(P + 0x374) != 0:
            haste = C.add(haste, 0x3E800000)
        if u32(P + 0x37C) != 0:
            haste = C.add(haste, F_0_1)
        if self.s32(Rm + 0x50) == 5:
            rank = s32(self.helper('player_getSkillRank', self.skill_rank, self.slot, 0x47))
            if rank > 0:
                factor = self.call('SkillBerserkerRage_swingFactor', u32(G_SKILL_TABLE + 4 * 0x47), rank, Rm,
                                   s32(frame - u32(P + 0x458)))
                speed = C.mul(speed, factor)
        speed = C.add(speed, haste)
        self.anim_step(speed)
        speed = self.slow_scale(speed)
        if cls == 2 and not heavy:
            sweep_frame = C.to_int(C.div(C.from_int(sweep_frame), speed))
        # ---- target (0x1aa23c-0x1aa638)
        started = self.s32(P + 0x448)
        turn = False
        if s32(frame - started) == 1 or u32(P + 0x234) == 0:
            reach = 0x42400000
            fx = C.cos16(self.s16(P + 0x38))
            fy = C.sin16(self.s16(P + 0x38))
            if self.s8(Rm + 0x4A86) in (1, 3):
                reach = 0x42680000
            px, py, pz = self.vec(P + 0x10)
            high = (C.add(px, reach), C.add(py, reach), C.add(pz, 0x42900000))
            low = (C.sub(px, reach), C.sub(py, reach), C.sub(pz, 0x42900000))
            objects = self.call('world_collectObjectsInBox', low, high, 0x100)
            nearest = 0x551184E7
            self.call('handle_clear', P + 0x4B8)
            best_obj = None
            for obj in objects:
                if obj == P:
                    continue
                flags = u32(obj + 0xC)
                ok = (flags & 0x49) == 0 \
                    and ((flags & 0x20) == 0
                         or (self.s16(obj + 0x312) == 0 and not (self.u64(obj + 0xA8) & 0x4000000))) \
                    and (flags & 0x1000000) == 0
                if not ok:
                    ok = u32(G_PVP_MODE_A) != 0 and (flags & 0x20) != 0 \
                        and self.vcall('Player', P, 0x48, 20, obj) != 0
                if not ok:
                    continue
                dx = C.sub(u32(obj + 0x10), u32(P + 0x10))
                dy = C.sub(u32(obj + 0x14), u32(P + 0x14))
                dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
                inv = C.div(ONE, dist)
                nx, ny = C.mul(dx, inv), C.mul(dy, inv)
                dot = C.add(C.mul(nx, fx), C.mul(ny, fy))
                if not C.le(ZERO, dot):
                    continue
                if self.s8(Rm + 0x4A86) == 2 and self.s8(P + 0x460) == 3:
                    self.call('handle_link', P + 0x4B8, obj, obj)
                dot = C.add(C.add(C.mul(nx, fx), C.mul(ny, fy)), C.mul(ZERO, ZERO))
                if C.le(HALF, dot):
                    d = C.sub(dist, u32(obj + 0x1C))
                    if C.lt(d, reach):
                        d = C.sub(d, C.mul(dot, 0x42000000))
                        if C.le(d, nearest):
                            best_obj, nearest = obj, d
            self.call('handle_clear', P + 0x234)
            linked = True
            if best_obj is not None:
                self.call('handle_link', P + 0x234, best_obj, best_obj)
                node = u32(P + 0x234)
                if node:
                    target = u32(node + 0xC)
                    if u32(target + 0xC) & 0x20:
                        self.vcall('Creature', target, 0x48, 12, 3, self.vec(P + 0x10), P, ZERO)
                else:
                    linked = False
            if linked and u32(P + 0x234) != 0:
                started = self.s32(P + 0x448)
                turn = True
        else:
            turn = True
        if turn and C.le(C.from_int(s32(frame - started)), 0x41ED1EB7):
            node = u32(P + 0x234)
            self.vcall('Player', P, 0x48, 26, 0, self.vec(u32(node + 0xC) + 0x10))
        started = self.s32(P + 0x448)
        lunge = 0x3F1126E9 if u32(P + 0x44C) == 2 else 0x3EDDB22D
        if C.le(C.from_int(s32(frame - started)), C.mul(lunge, F_60)):
            self.move(4)
        else:
            self.move(3)
        # ---- hit frame, swing sound, voice (0x1aa6b0-0x1aaa88)
        t = s32(u32(G_SIM_FRAME) - u32(P + 0x448))
        hit = swing = shout = False
        hit_flag = 0
        if self.s8(G_NETWORK_MODE) == 0:
            hit = t == C.to_int(C.div(0x418028F5, speed))
            if hit:
                hit_flag = 1
            swing, shout = t == 6, t == 9
        else:
            if t == 1:
                hit = u32(P + 0x55C) == 0
            if not self.call('net_isLocalSlot', self.slot) or self.is_copy():
                swing, shout = t == 6, t == 9
            if self.s32(P + 0x55C) > 0:
                w32(P + 0x55C, self.s32(P + 0x55C) - 1)
        if self.s8(Rm + 0x4A86) == 2 and sweep_frame <= t:
            past = t - sweep_frame
            node = self.call('iter_begin', P + 0x4B8, 0)
            while node:
                target = u32(node + 0xC)
                angle = C.atan2_16(C.sub(u32(target + 0x10), u32(P + 0x10)), C.sub(u32(target + 0x14), u32(P + 0x14)))
                if s16(-self.u16(P + 0x38) - angle + 0x4000) < s16(past * -0x708 + 0x4000):
                    self.call('Player_meleeHit', P, u32(node + 0xC), 0, 0, ZERO)
                    self.call('handle_removeNode', node)
                node = self.call('iter_next')
            self.call('iter_end', 2)
            w32(P + 0x44C, 0)
        elif hit:
            if u32(P + 0x234) != 0:
                self.call('Player_meleeHit', P, u32(u32(P + 0x234) + 0xC), hit_flag, 0, ZERO)
            w32(P + 0x44C, 0)
        if swing:
            if weapon == 0:
                fmt = 0x536120
            elif u32(u32(weapon) + 0x20) & 8:
                fmt = 0x536138 if (self.u64(weapon + 8) & 0x20000000) else 0x536150
            elif self.u64(weapon + 8) & 0x20000000:
                fmt = 0x536168
            else:
                fmt = 0x536180
            name = self.call('libc_sprintf', fmt, (self.draw3() & 3) + 1)
            self.sound(name, P)
        if shout:
            kind = {5: 0x10, 0: 0x12, 2: 0xE, 1: 0xF, 3: 0x11}.get(self.s8(Rm + 0x4A86))
            if kind is not None:
                self.call('player_voice', self.slot, kind)
        # ---- combo window (0x1aaa8c-0x1aaf64)
        cls = self.s8(Rm + 0x4A86)
        trim = C.mul(C.mul(haste, F_60), HALF)
        if C.lt(0x418B3332, trim):
            trim = 0x418B3332
        window = ZERO
        if cls in (2, 1, 3, 5, 0, 4, 6):
            window = C.sub(0x41B028F5, trim)
        elif cls == 7:
            window = C.sub(0x418CED91, trim)
        slot = self.slot
        pressed = u32(pad + 0xC)
        if (pressed & (u32(G_BTN_ATTACK + slot * 4) | self.instant)) == 0 and self.instant != M32:
            started = None
            if u32(P + 0x454) == 1 or ((pressed & u32(G_BTN_BLOCK + slot * 4))
                                       and not (u32(G_LEVEL_FLAGS) & 0x10000000)):
                if self.helper('player_canBlock', self.can_block, slot, u32(P + 0x58C)):
                    w32(P + 0x58C, 8)
                else:
                    text = self.call('text_lookup', 0x535FE8)
                    self.call('hud_showMessage', text, 0xB4, M32, 0)
            started = u32(P + 0x448)
        else:
            if (pressed & self.instant) or self.instant == M32:
                ability = 0
                if self.instant == M32:
                    ability = u32(P + 0x488)
                    w32(P + 0x488, 0)
                else:
                    Rs = G_PLAYERS + slot * REC_SIZE
                    if self.instant & u32(G_BTN_ABILITY_A + slot * 4):
                        ability = Rs + 0x4440 + self.s8(Rs + 0x4A84) * 0x68
                    if self.instant & u32(G_BTN_ABILITY_B + slot * 4):
                        ability = Rs + 0x4440 + self.s8(Rs + 0x4A85) * 0x68
                if self.strcmp(ability, S_NEWSTYLE) == 0:
                    self.helper('Player_castSkill', self.cast_skill, P, ability)
            started = u32(P + 0x448)
            if C.lt(C.div(window, speed), C.from_int(s32(u32(G_SIM_FRAME) - started))):
                started = self.melee_next_swing(Rm, steps, started)
        frame = u32(G_SIM_FRAME)
        if C.le(C.div(window, speed), C.from_int(s32(frame - started))):
            ability = self.selected_ability()
            if ability is not None and self.s16(ability + 0x20) == 0x25 \
                    and (u32(pad + 0xC) & u32(self.R + 0x4A80)):
                w32(P + 0x450, 1)
        lx, ly = u32(pad + 0x14), u32(pad + 0x18)
        stick = C.sqrt(C.add(C.mul(lx, lx), C.mul(ly, ly)))
        elapsed = C.from_int(s32(frame - started))
        if C.le(stick, 0x3F4CCCCC) or C.lt(elapsed, 0x421D3332):
            end = C.le(C.mul(u32(P + 0x470), F_60), elapsed) or u32(P + 0x450) != 0
        else:
            end = True
        if end:
            w32(P + 0x44C, 0)
            w32(P + 0xB0, 0x3FB33333)
            if self.s8(P + 0x118) - 1 > 3:
                i, off = 4, 0x1A0
                while True:
                    w32(P + 0xC + off, ONE)
                    i += 1
                    w32(P + 0x10 + off, 0xBDAAAAAA)
                    off += 0x20
                    if not i <= self.s8(P + 0x118) - 1:
                        break
            w32(P + 0x58C, 2)
            w32(P + 0x448, u32(G_SIM_FRAME))
        self.helper('Player_tryBlockMove', self.try_block_move, P, pad)

    def melee_next_swing(self, Rm, steps, started):
        """0x1aac9c-0x1aafe0: the next swing of the combo.  Returns the action start frame
        the rest of the state uses."""
        P, u32, w32 = self.P, self.u32, self.w32
        step = s8(self.s8(P + 0x460) + 1)
        self.w8(P + 0x460, step)
        if steps - 1 < step:
            self.w8(P + 0x460, steps - 1)
        if u32(P + 0x44C) != 2:
            w32(P + 0x44C, 1)
        w32(P + 0x454, 0)
        self.call('Player_pickAttackAnim', P, self.s8(Rm + 0x4A86))
        cls = self.s8(Rm + 0x4A86)
        fmt = {0: 0x536198, 5: 0x5361B0, 2: 0x5361C8, 1: 0x5361E0, 3: 0x5361F8, 7: 0x536208}.get(cls)
        if fmt is not None:
            name = self.call('libc_sprintf', fmt, self.s8(P + 0x461))
        elif cls == 4:
            name = self.call('libc_sprintf', 0x535FB8, None)
        elif cls == 6:
            name = self.call('libc_sprintf', 0x535FC8, None)
        else:
            name = 'stack'
        cls = self.s8(Rm + 0x4A86)
        if cls in (4, 6):
            started = u32(P + 0x448)
            elapsed = C.from_int(s32(u32(G_SIM_FRAME) - started))
            if C.le(elapsed, 0x421E6665):
                if C.lt(0x4257FFFF, elapsed):
                    w32(P + 0x58C, 2)
                return started
            self.call('Player_findTarget', P, F_60)
            if u32(P + 0x234) == 0:
                return u32(P + 0x448)
            if self.s8(Rm + 0x4A86) == 4:
                w32(P + 0x470, 0x3F666666)
        else:
            w32(P + 0x470, 0x3FCCCCCC)
        anm = self.call('res_find', u32(u32(P + 0x24)), name)
        self.call('anim_start', P + 0x114, anm, 0x802, F_0_1)
        w32(P + 0x448, u32(G_SIM_FRAME))
        return u32(G_SIM_FRAME)

    # ---- state 5: casting (0x1ab4f8) ---------------------------------------------------------
    def end_cast_glow(self, rate=0xBD4CCCCC):
        self.w32(G_AURA_DIR + self.slot * 4, M32)

    def state_cast(self):
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        ability = u32(P + 0x488)
        if ability == 0:
            ability = self.selected_ability() or 0
        if ability != 0 and self.s16(ability + 0x20) == -1:
            ability = 0
        self.anim_step()
        self.move(1 if self.s8(G_NETWORK_MODE) == 0 else 6)
        if ability == 0 or self.strcmp(ability, S_NEWSTYLE) != 0:
            self.cast_old_style(ability)
            return
        skill = self.skill_of(ability)
        phase = self.u8(P + 0x47B)
        if phase == 0:
            if not self.vcall('Skill', skill, 0x60, 1, P):
                w32(P + 0x488, 0)
                w32(P + 0x58C, 2)
                return
            phase = self.u8(P + 0x47B)
        if phase < 2:
            track = s32(self.call('anim_findTrackByFlag', P + 0x114, 0x8000))
            point = ONE if self.s8(G_NETWORK_MODE) == 0 else HALF
            if self.s8(P + 0x47B) == 0 and track < 0:
                if self.s32(skill + 8) != 6:
                    self.call('anim_start', P + 0x114, self.anim_name(0x6C), 0x8003, F_0_1)
                self.w8(P + 0x47B, 1)
            elif self.s8(P + 0x47B) == 1:
                if self.s32(skill + 8) == 6 or C.le(point, u32(P + 0x124 + track * 0x20)):
                    self.w8(P + 0x47B, 2)
                    self.helper('Player_castSkill', self.cast_skill, P, ability)
                    w32(P + 0x488, 0)
                    if self.s32(skill + 8) == 0:
                        weight = P + 0x12C + track * 0x20
                        w32(weight, C.fmin(u32(weight), ONE))
                        w32(P + 0x130 + track * 0x20, 0xBD6EEEEE)
        else:
            if self.s8(ability + 0x25) == 1:
                rank = self.vcall('Player', P, 0x48, 39, self.s16(ability + 0x20))
                cost = self.vcall('Skill', skill, 0x60, 5, rank)
                R = self.R
                w32(R + 0xC0, C.sub(u32(R + 0xC0), C.mul(cost, F_1_60)))
            if not (self.u16(P + 0x11A) & 0x8000):
                self.w8(P + 0x47B, 0)
                w32(P + 0x58C, 2)
                w32(P + 0x488, 0)

    def light_effect(self, height, a2, colours):
        P = self.P
        block = self.call('pool_new', 0xBC)
        if block:
            pos = (C.add(self.u32(P + 0x10), ZERO), self.u32(P + 0x14), C.add(self.u32(P + 0x18), height))
            self.call('LightEffect_ctor', block, pos, a2, 0, *(tuple(colours) + (ZERO,) * (8 - len(colours))))

    def cast_old_style(self, ability):
        """0x1ab638-0x1ac458: abilities that are not Skill objects (kinds 0, 1 and 2).  No
        test for the prediction copy anywhere in here."""
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        a, b = self.hands_midpoint(P, False)
        mid = tuple(C.mul(C.add(a[k], b[k]), HALF) for k in range(3))
        if self.s8(P + 0x47B) == 0:
            w32(G_AURA_DIR + self.slot * 4, 1)
        if ability == 0:
            return
        kind = self.s8(ability + 0x25)
        if kind == 1:                                   # held
            if self.s8(P + 0x47B) == 0:
                if self.s16(ability + 0x20) == 9:
                    for k, v in enumerate((100, 200, 0xFF)):
                        w32(G_AURA_COLOR + self.slot * 16 + 4 * k, v)
                    for k, v in enumerate((0, 0x136, 0x1FE, 0xFFFFFFA0)):
                        w32(G_AURA_LIGHT_COLOR + self.slot * 16 + 4 * k, v)
                slot = self.slot
                w32(G_AURA_FADE_RATE + slot * 4, 0x3D4CCCCC)
                w32(G_AURA_FADE + slot * 4, 0)
                self.call('anim_start', P + 0x114, self.anim_name(0x6C), 0x8003, F_0_1)
            self.w8(P + 0x47B, 1)
            if not (u32(pad + 8) & u32(self.R + 0x4A80)):
                self.stop_loop_sound()
                w32(G_AURA_DIR + self.slot * 4, M32)
                w32(P + 0x58C, 2)
                w32(G_AURA_FADE_RATE + self.slot * 4, 0xBD4CCCCC)
                w32(self.top_track(0x110), 0xBD6EEEEE)
                self.w8(P + 0x47B, 0)
        elif kind == 2:                                 # timed
            if self.s8(P + 0x47B) == 0:
                for k in range(3):
                    w32(G_AURA_COLOR + self.slot * 16 + 4 * k, self.s16(ability + 0x30 + 2 * k))
                for k in range(4):
                    w32(G_AURA_LIGHT_COLOR + self.slot * 16 + 4 * k, self.s16(ability + 0x38 + 2 * k))
                w32(G_AURA_FADE + self.slot * 4, 0)
                w32(G_AURA_FADE_RATE + self.slot * 4, u32(ability + 0x40))
                self.sound(0x536220, u32(self.R + 0x43D8))
                self.call('anim_start', P + 0x114, self.anim_name(0x6C), 0x8003, F_0_1)
                self.w8(P + 0x47B, 1)
            if C.le(0x41200000, u32(self.top_track(0x104))):
                self.call('sound_stop', u32(P + 0x4A8))
                w32(P + 0x4A8, M32)
                w32(G_AURA_DIR + self.slot * 4, M32)
                w32(P + 0x58C, 2)
                w32(P + 0x488, 0)
                w32(G_AURA_FADE_RATE + self.slot * 4, 0xBD4CCCCC)
                w32(self.top_track(0x110), 0xBD6EEEEE)
                self.w8(P + 0x47B, 0)
        elif kind == 0:                                 # one cast
            sid = self.s16(ability + 0x20)
            phase = self.s8(P + 0x47B)
            if phase == 0:
                if sid == 0x1A:
                    w32(P + 0xF0, u32(P + 0x448))
                    w32(u32(self.R + 0x43D8) + 0x398, 0x29)
                elif sid == 0x1B:
                    w32(P + 0xF0, u32(P + 0x448))
                    self.light_effect(0x42100000, 0, (0x437F0000, 0x42C80000, 0x437F0000, 0xC2C00000))
                    w32(u32(self.R + 0x43D8) + 0x3A0, self.s16(ability + 0x22))
                w32(G_AURA_FADE_RATE + self.slot * 4, u32(ability + 0x40))
                for k in range(3):
                    w32(G_AURA_COLOR + self.slot * 16 + 4 * k, self.s16(ability + 0x30 + 2 * k))
                for k in range(4):
                    w32(G_AURA_LIGHT_COLOR + self.slot * 16 + 4 * k, self.s16(ability + 0x38 + 2 * k))
                self.w8(P + 0x47B, 1)
                self.call('anim_startBlendInOut', P + 0x114, self.anim_name(0x6C), 0x8022, F_0_1, F_0_1)
            elif phase != 2 and C.le(ONE, u32(self.top_track(0x104))):
                self.w8(P + 0x47B, 2)
                if sid == 0x19:
                    block = self.call('pool_new', 0xC0)
                    if block:
                        self.call('Root_ctor', block, mid, self.u16(P + 0x38), P, 0, 0x41F00000)
                elif sid == 0x15:
                    self.old_fire_nova(ability)
                elif sid == 0x1A:
                    owner = u32(self.R + 0x43D8)
                    if self.s32(owner + 0x39C) < 1:
                        self.light_effect(0x42100000, 0, (0x437F0000, 0x42C80000, 0x437F0000, 0xC2C00000))
                        block = self.call('pool_new', 0xA0)
                        if block:
                            self.call('UnholyAura_ctor', block, self.vec(P + 0x10), P, 0, 0x424A0000)
                    else:
                        w32(u32(self.R + 0x43D8) + 0x39C, 0)
            if not (self.u16(P + 0x11A) & 0x20):
                self.stop_loop_sound()
                w32(P + 0x488, 0)
                w32(P + 0x58C, 2)
                w32(G_AURA_DIR + self.slot * 4, M32)
                self.w8(P + 0x47B, 0)

    def old_fire_nova(self, ability):
        """Older ability id 0x15 (0x1abf70-0x1ac408): a ring of particles and area damage."""
        P, u32 = self.P, self.u32
        if u32(G_PARTICLE_BUILT_B) == 0:
            self.call('particleDef_ctor', 0, G_PARTICLE_DEF_B, 0x6E, 0x6B, 0x9A, 0x9F, 0x6F, 0x6B,
                      0x4222978D, 0x42A19604)
            self.w32(G_PARTICLE_BUILT_B, 1)
        angle = 0
        while True:
            vx = C.mul(C.cos16(angle), 0x42C80000)
            vy = C.mul(C.sin16(angle), 0x42C80000)
            pos = (C.add(u32(P + 0x10), ZERO), u32(P + 0x14), C.add(u32(P + 0x18), 0x42100000))
            self.call('particle_spawn', 0, G_PARTICLE_DEF_B, pos, (vx, vy, 0))
            angle += 300
            if angle >= 0x10000:
                break
        self.sound(0x536238, u32(self.R + 0x43D8))
        self.light_effect(0x42100000, 0, (ZERO, 0x431B0000, 0x437F0000, 0xC2C00000))
        level = s32(self.helper('player_getPassiveLevel', self.passive_level, self.slot, 0x8000))
        extra = C.to_int(C.powf(C.from_int(level * 5), 0x3F8CCCCC))
        self.call('world_damageInRadius', P, self.vec(P + 0x10), self.s16(ability + 0x28) + extra, 0x100900, 0, 0,
                  F_60, 0x43700000)

    # ---- state 0: ranged attack (0x1a80e0) ---------------------------------------------------
    def aim_at_target(self, speed_divisor, scale=None):
        """Player_findTarget(300), turn toward the target, return its position (or zeros)
        with the lead a level of passive 0x200000 adds."""
        P, u32 = self.P, self.u32
        aim = [ZERO, ZERO, ZERO]
        self.call('Player_findTarget', P, 0x43960000)
        node = u32(P + 0x234)
        if node:
            self.vcall('Player', P, 0x48, 26, 0, self.vec(u32(node + 0xC) + 0x10))
            target = u32(u32(P + 0x234) + 0xC)
            aim = list(self.vec(target + 0x10))
            if self.helper('player_getPassiveLevel', self.passive_level, self.slot, 0x200000):
                target = u32(u32(P + 0x234) + 0xC)
                dy = C.sub(u32(target + 0x14), u32(P + 0x14))
                dx = C.sub(u32(target + 0x10), u32(P + 0x10))
                dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
                if speed_divisor is not None:
                    k = C.div(dist, speed_divisor)
                else:
                    k = C.mul(C.mul(dist, 0x3E800000), 0x42C80000)
                aim[0] = C.add(aim[0], C.mul(u32(target + 0x308), k))
                aim[1] = C.add(aim[1], C.mul(u32(target + 0x30C), k))
        return aim

    def state_ranged(self):
        P, pad, u32, w32 = self.P, self.pad, self.u32, self.w32
        R0 = self.R0
        base = 0xB if self.u8(P + 0x480) == 7 else 0x16
        weapon = u32(R0 + 0x4434 + 4 * self.s8(R0 + 0x4A7C))
        if self.s8(G_NETWORK_MODE) != 0:
            base >>= 1
        speed = ZERO
        if weapon:
            h = self.haste_of(weapon)
            speed = C.add(speed, C.add(h, h))
        speed = C.add(ONE, speed)
        self.anim_step(speed)
        speed = self.slow_scale(speed)
        release = C.to_int(C.div(C.from_int(base), speed))
        if self.u8(P + 0x480) == 7 and weapon:
            self.ranged_throw(weapon, release)
            slot = self.slot
        else:
            slot = self.slot
            if s32(u32(G_SIM_FRAME) - u32(P + 0x448)) == release and u32(G_PLAYERS + slot * REC_SIZE + 0x4410) != 0:
                self.ranged_shoot()
                slot = self.slot
        self.call('player_recalcLoad', slot)
        if (u32(pad + 0xC) & u32(G_BTN_ATTACK + self.slot * 4)) and self.frames() > 0xE:
            w32(P + 0x44C, 1)
        self.move(1 if self.s8(G_NETWORK_MODE) == 0 else 6)
        if not (self.u16(P + 0x11A) & 0x10):
            self.w8(P + 0x3CC, 0)
            if C.le(C.mul(u32(P + 0x48C), F_60), C.from_int(self.frames())):
                w32(P + 0x58C, 2)

    def ranged_throw(self, weapon, release):
        """0x1a8208-0x1a8978: a thrown weapon or potion."""
        P, u32, w32 = self.P, self.u32, self.w32
        velocity = 0x443B8000
        if self.u64(weapon + 8) & 0x1000000:
            velocity = 0x43AF0000
        aim = self.aim_at_target(velocity)
        if s32(u32(G_SIM_FRAME) - u32(P + 0x448)) != release or self.is_copy():
            return
        if u32(P + 0x484) != 0:
            self.helper('Player_castSkill', self.cast_skill, P, u32(P + 0x484))
            self.w16(P + 0x4AE, 0)
            self.w8(P + 0x3CC, 1)
            return
        self.w8(P + 0x3CC, 1)
        hand, _direction = self.call('model_getAttachPoint', u32(P + 0x544), self.vec(P + 0x10), self.s16(P + 0x38),
                                     P + 0x114, 0, 1, ONE)
        angle = self.u16(P + 0x38) + self.draw() % 0xA28 - 0x514
        if u32(P + 0x234) != 0:
            angle = 0x4000 - C.atan2_16(C.sub(aim[0], hand[0]), C.sub(aim[1], hand[1]))
        angle = s16(angle)
        vx = C.mul(C.cos16(angle), velocity)
        vy = C.mul(C.sin16(angle), velocity)
        vz = C.add(C.from_int(self.draw() % 0x28), 0x42200000)
        if u32(P + 0x234) != 0:
            d = [C.sub(u32(P + 0x10 + 4 * k), aim[k]) for k in range(3)]
            vz = C.sub(C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2]))), 0x42F00000)
        item = u32(self.R + 0x43F8)
        model_a = u32(G_MODEL_TABLE + 8 + self.call('item_getResourceIndex', item) * 16)
        model_b = u32(G_MODEL_TABLE + 0xC + self.call('item_getResourceIndex', item) * 16)
        name = self.call('libc_sprintf', 0x535FF8, (self.obj_rand() & 3) + 1)
        self.sound(name, P)
        flags = self.u64(weapon + 8)
        make, turn = True, 0x4000
        if flags & 0x1000000:
            turn = -0x4000
            name_ptr = u32(u32(weapon))
            if not self.strstr(0x536010, name_ptr) and not self.strstr(0x536020, name_ptr):
                make = self.call('str_prefixDiffers', name_ptr, 0x535FD8) == 0
        if make:
            block = self.call('pool_new', 0x1D0)
            if block:
                self.call('playerProjectile_ctor', block, model_a, model_b, hand, (vx, vy, vz), angle + turn, P, 0)
        count = self.u16(item + 4)
        if ((count - 1) & M32) < 0x14:
            self.hud_notice(7, 0xF0)
            count = self.u16(item + 4)
        left = s16(count)
        if not self.is_copy():
            self.w16(item + 4, count - 1)
            left = s16(count - 1)
        if left < 1:
            slot = self.slot
            for i in range(64):
                if G_PLAYERS + slot * REC_SIZE + 0x130 + i * 0x48 == u32(G_PLAYERS + slot * REC_SIZE + 0x43F8):
                    self.call('inventory_removeItem', slot, i, 0, 0)
                    slot = self.slot

    def ranged_shoot(self):
        """0x1a8980-0x1a9574: the bow release.  Shared draws: spread, aim, pitch (twice
        with a target), sound."""
        P, u32, w32 = self.P, self.u32, self.w32
        spawn = self.call('model_getAttachPoint', u32(P + 0x544), self.vec(P + 0x10), self.s16(P + 0x38),
                          P + 0x114, 0, 0, ONE)
        self.aim_at_target(None)
        spread = self.s16(P + 0x38) + self.draw() % 500 - 0xFA
        found = self.call('world_collectObjectsInArc', 0, self.vec(P + 0x10), self.s16(P + 0x38), 0,
                          0x43AA0000, 0x41A00000)
        target = 0
        for obj in found:
            if self.vcall('Player', P, 0x48, 20, obj):
                target = obj
                break
        if target == 0:
            aim = self.u16(P + 0x38) + self.draw() % 500 - 0xFA
        else:
            bearing = C.atan2_16(C.sub(u32(target + 0x10), u32(P + 0x10)), C.sub(u32(target + 0x14), u32(P + 0x14)))
            aim = self.draw() % 500 - bearing + 0x40C8
        aim = s16(aim)
        c, s = C.cos16(aim), C.sin16(aim)
        vel = [C.mul(C.mul(c, 0x41200000), 0x42C80000), C.mul(C.mul(s, 0x41200000), 0x42C80000),
               C.from_int(self.draw() % 0x3C - 0x1E)]
        if target:
            d = [C.sub(u32(target + 0x10), spawn[0]), C.sub(u32(target + 0x14), spawn[1]),
                 C.sub(C.add(u32(target + 0x18), C.mul(u32(target + 0x20), HALF)), spawn[2])]
            inv = C.div(ONE, C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2]))))
            nz = C.mul(d[2], inv)
            c, s = C.cos16(aim), C.sin16(aim)
            vz = C.add(C.mul(nz, 0x447A0000), C.from_int(self.draw() % 0x3C - 0x1E))
            if C.lt(vz, 0xC3960000):
                vz = 0xC3960000
            elif C.lt(0x43960000, vz):
                vz = 0x43960000
            vel = [C.mul(c, 0x447A0000), C.mul(s, 0x447A0000), vz]
        if not self.is_copy() and target and (u32(target + 0xC) & 0x20):
            self.vcall('Creature', target, 0x48, 12, 2, self.vec(P + 0x10), P, ZERO)
        ability = u32(P + 0x488)
        if ability == 0:
            ability = self.selected_ability() or 0
        slot = self.slot
        if ability != 0 and self.s16(ability + 0x20) == -1:
            w32(P + 0x484, 0)
        left = self.s16(u32(G_PLAYERS + slot * REC_SIZE + 0x4410) + 4)
        if u32(P + 0x484) == 0 or self.s16(ability + 0x20) != 0x2E:
            if not self.is_copy():
                left -= 1
        else:
            rank = self.helper('player_getSkillRank', self.skill_rank, slot, 0x2E)
            used = s32(self.vcall('Skill', u32(G_SKILL_TABLE + 4 * 0x2E), 0x60, 10, 2, rank))
            if not self.is_copy():
                left -= used
            slot = self.slot
        if left < 0:
            left = 0
        Rs = G_PLAYERS + slot * REC_SIZE
        bow = u32(Rs + 0x4434 + 4 * self.s8(Rs + 0x4A7C))
        if bow:
            self.call('item_getModifiedField1a', bow)
            self.call('script_runByName', 0x536030)
            name = self.call('libc_sprintf', 0x536048, self.draw() % 5 + 1)
            self.sound(name, P)
            if u32(P + 0x484) == 0:
                kind = self.s8(P + 0x480)
                if kind != 3:
                    if not self.is_copy():
                        self.missile(spawn, vel, spread - 0x4000)
                        kind = self.s8(P + 0x480)
                if kind == 3:
                    self.call('item_getDamageRange', bow, 0)
                    count = self.s16(u32(self.R + 0x4410) + 4)
                    if count >= 1 and not self.is_copy():
                        self.missile(spawn, vel, spread - 0x4000)
                    w32(Rs + 0xC0, C.sub(u32(Rs + 0xC0), u32(ability + 0x2C)))
                elif ((kind - 1) & 0xFF) < 2 or kind in (5, 6):
                    w32(Rs + 0xC0, C.sub(u32(Rs + 0xC0), u32(ability + 0x2C)))
                self.w8(P + 0x480, 0)
            else:
                self.helper('Player_castSkill', self.cast_skill, P, u32(P + 0x484))
                self.w16(P + 0x4AE, 0)
            if not self.is_copy():
                if left == 0:
                    slot = self.slot
                    for i in range(64):
                        if G_PLAYERS + slot * REC_SIZE + 0x130 + i * 0x48 == u32(G_PLAYERS + slot * REC_SIZE + 0x4410):
                            self.call('inventory_removeItem', slot, i, 0, 0)
                            slot = self.slot
                            break
                    w32(G_PLAYERS + slot * REC_SIZE + 0x4410, 0)
                else:
                    self.w16(u32(self.R + 0x4410) + 4, left)
        self.call('handle_clear', 'stack')

    def missile(self, spawn, vel, facing):
        block = self.call('pool_new', 0x1C8)
        if block:
            self.call('MissileWeapon_ctor', block, self.u8(self.P + 0x480), self.u32(G_MODEL_TABLE + 8),
                      self.u32(G_MODEL_TABLE + 0xC), tuple(spawn), tuple(vel), facing, self.P)
