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
    'libc_sprintf': Ext(0x3B7EF0, 'ppi', 0, 'n', '(buffer, format, one integer)'),
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
    'typeinfo': Ext(0, '', 0, 'i', 'a type-info getter; the name says which'),
    'SpellAncestralCall_queryFor': Ext(0x2E1470, 'ppiq', 0, 'i'),
    'SpellBattleCry_affects': Ext(0x302C04, 'ppq', 0, 'i'),
    'SkillBerserkerRage_swingFactor': Ext(0x2FE324, 'pipi', 0, 'f'),
    'SpellBlessed_getStat0': Ext(0x2DFDB8, 'p', 0, 'i'),
    'SkillRegeneration_getStat0': Ext(0x2F14F0, 'p', 0, 'i'),
    # --- objects made by the tick
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i', '(size) -> block or 0'),
    'LightEffect_ctor': Ext(0x201BD8, 'pvpi', 8, 'n'),
    'MissileWeapon_ctor': Ext(0x150EE4, 'piiivvip', 0, 'n'),
    'playerProjectile_ctor': Ext(0x1BEF58, 'piivvipi', 0, 'n'),
    'Root_ctor': Ext(0x293704, 'pvipi', 1, 'n'),
    'UnholyAura_ctor': Ext(0x29486C, 'pvpi', 1, 'n'),
    'GroundPoundEffect_ctor': Ext(0x2C74AC, 'pvipip', 0, 'n'),
    'particleDef_ctor': Ext(0x18F3D0, 'ipiiiiiii', 2, 'n'),
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
