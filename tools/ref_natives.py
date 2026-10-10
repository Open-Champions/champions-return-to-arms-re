#!/usr/bin/env python3
"""ref_natives.py - reference model of the level-script built-in commands of Champions:
Return to Arms (SLUS_209.73, US v2.00): the 191 native functions of the table at 0x403370
that compiled level scripts call to act on the game, and the host machinery around them
(script_runByName, quest variables, deferred calls, the post action, the newWorld gate).

A research tool, not game code.  Every function was written from the instruction sequence at
the address in its docstring and is compared with that code, executed under tools/ee_emu.py,
by tools/difftest_natives.py.  docs/spec/script-builtins.md is the prose version and says
what the comparison covers.  Standard library only; no game data is embedded.

    import ref_amx, ref_natives
    game = ref_natives.Game()
    machine = ref_amx.Machine(open('script.scr', 'rb').read())
    machine.load()
    game.set_script(machine)                 # script_setCurrent: binds the built-ins
    game.run_script('start')                 # script_runByName
    game.run_deferred()                      # the per-tick Script task (priority 125)

How the model sees the game
    mem      a Mem: sparse little-endian memory holding every scalar the built-ins touch AT
             ITS REAL ADDRESS - globals, the four player records, the quest-variable table,
             the deferred-call buffers, and the fields of objects.  Game has a named
             property for each global (game.active_player, game.num_players ...).  A Mem can
             be laid over another memory (the differential test lays it over the
             interpreter's), which is what makes "every byte written" comparable.
    world    a ref_objects.World: the name table, the grids and the run lists.  Objects are
             Obj (a ref_objects.GameObject whose flags, position and facing live in mem);
             a name is resolved by ref_objects.NameTable exactly as world_findObjectsByName
             does, so "which object does this name mean" is not modelled again here.
    host     call-outs.  Everything a built-in hands to code that belongs to another model
             or to presentation - sound, camera, HUD, cutscene and dialog start, inventory,
             spawning by class, net messages, virtual calls on objects - goes through
             Game.ext(name, *args) and is recorded in host.log.  EXT lists every call-out
             with its address and argument registers.  Host answers 0 unless you give it a
             handler; the object-system call-outs default to the ref_objects operation.
    machine  the level's ref_amx.Machine (g_scriptMachine).

Floats are raw 32-bit patterns and go through tools/ref_core.py's R5900 arithmetic.

Where the model stops: a built-in that would follow a null or uninitialised pointer (most
do not check that a named object exists) raises ref_amx.HostFault instead of guessing.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)          # appended: tools/dis.py must not shadow the standard dis
import ref_core as C                                # noqa: E402
import ref_objects as O                             # noqa: E402
from ref_amx import HostFault                       # noqa: E402

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


def _tdiv(a, b):
    """The CPU's signed divide: quotient toward zero (b != 0)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


# =======================================================================================
# 1. Addresses
# =======================================================================================
NATIVE_TABLE = 0x403370             # 191 x {name pointer, handler}, zero terminated

G_SCRIPT_MACHINE = 0x86B270
G_DEFER_NAMES = 0x86B278            # 2 halves x 64 names x 0x50 bytes
G_DEFER_COUNT = 0x86DA78            # names in the half being run
G_DEFER_QUEUED = 0x86DA7C           # names queued in the other half
G_DEFER_FLIP = 0x4F8690             # parity selects the half being run
G_MISSING_STAMP = 0x4F8694
G_IN_POST_ACTION = 0x4F8698         # s8
G_QUEST_VARS = 0x86DA80             # packed: name, 0, value byte, name, 0, value byte ... 0
G_POST_ACTION = 0x86FA80
G_SELECTED_OBJ = 0x4039F8
G_ACTIVE_PLAYER = 0x4D8AE4
G_NUM_PLAYERS = 0x4D8AE0
G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
G_RAND_SEED = 0x404464
G_NETWORK_MODE = 0x402791           # s8
G_DIFFICULTY = 0x4F719C
G_PAUSED = 0x41B4F4
G_CUTSCENE_ACTIVE = 0x44FCD0        # s8
G_JUMPGATE_TRAVEL = 0x500AE8
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_DRAW_FRAME = 0x44FDD0
G_PENDING_LEVEL = 0x41B6D0          # next world name; +0x50 (0x41b720) entrance orientation
G_PENDING_ORIENT = 0x41B720         # u8
G_LEVEL_NAME = 0x41B721
G_POST_DIALOG_LEVEL = 0x4FDCF0      # newWorldPost
G_ENTRANCE_NAME = 0x4F8468
G_SESSION_EXIT = 0x41B508
G_MENU_LOCKOUT, G_MENU_LOCKOUT_HOLD = 0x41B4FC, 0x41B500
G_SHOP_OPEN = 0x41B50C
G_RECALL_COUNTDOWN = 0x41B51D       # s8
G_HELP_OPEN = 0x41B928              # u8
G_STORE_INDEX = 0x4F7150            # u16
G_STORE_PENDING = 0x4FDD30
G_SWOOP, G_SWOOP_DONE = 0x4FDCE4, 0x4FDCE8
G_SAVE_INHIBIT = 0x50605C
G_ALT_DEATH = 0x4F712C
G_POTIONS_ONLY = 0x4F7128
G_WAVE_DETAIL = 0x4F7130
G_MEDAL_TICKS = 0x4F7114
G_MEDAL_MISSION = 0x4F713C
G_MEDAL_ACK = 0x4F7140
G_MEDAL_PLAYER = 0x4F7148           # u8
G_REWARD_PLAYER = 0x4F7149          # u8
G_RESPAWN_COUNTDOWN = 0x4F7194
G_LEVEL_LOADING = 0x4F7198
G_HIDE_PLAYERS = 0x4F83F8           # u8
G_LIGHT_SCALE = 0x4F83F4            # float
G_DEAD_COUNTDOWN = 0x4F84A8         # s16[4]
G_SOLO_SAVED = 0x4F85C0
G_GAME_COMPLETE = 0x4F85C5          # u8
G_MANA_USED, G_HEALTH_USED = 0x4F85C8, 0x4F85CA     # u16
G_LEVEL_TIMER = 0x4F85CC
G_SAVED_CONFIG = 0x4F8F38
G_PROFILE_VARS = 0x4F9030
G_MENU_OPEN_FLAG = 0x41B4F8
G_BOSS_HP, G_BOSS_MAX_HP = 0x41B6A0, 0x41B6A4
G_NO_MONSTER_FLAG = 0x5D32C4        # u8 scratch of checkMonstersLeft
G_GEN_NAMES, G_GEN_COUNT = 0x5D32C8, 0x4F8409       # 24-byte class names; s8 count
G_HELP_TITLE_BUF, G_HELP_BODY_BUF = 0x5D3048, 0x5D3088
G_MEDAL_PROMPT_BUF = 0x4F6848
G_HUD_FONT = 0x4F7104
G_PADS, PAD_SIZE = 0x41BFD8, 0x58   # +0xc: buttons pressed this tick
G_BTN_CANCEL, G_BTN_CONFIRM = 0x41BFB8, 0x41BFBC
G_BTN_NAME_A, G_BTN_NAME_B = 0x41B978, 0x41B97C
G_CAMERA_POS = 0x44F038             # Vec3, this machine's camera
G_LOCAL_CAMERA = 0x4F8450           # pointer
G_DIALOG_DATA = 0x8E2D60            # non-zero while a dialog is open
G_DIALOG_MSG_ID = 0x8E2E94           # message id dialog_start sends with
G_UNKNOWN_4D8A08, G_UNKNOWN_4039C0 = 0x4D8A08, 0x4039C0       # cleared by saveEndConfig
PARTICLE_DEFS = (0x5D3188, 0x5D31D8, 0x5D3228)      # the three pointers at 0x403360
SKILL_PTR_HORN = 0x41B1E4           # pointer global passed to the two spell-effect constructors

# player record (g_players + slot * 0x4c30)
P_RECALL = 0x24
P_CLASS, P_MODEL = 0x50, 0x54
P_KEEP_78 = 0x78                    # 24 bytes restorePlayer keeps
P_HP, P_MAX_HP = 0xAC, 0xB0         # floats
P_MANA, P_MAX_MANA = 0xC0, 0xC4     # floats
P_GOLD, P_SKILL_POINTS = 0xE4, 0xE8
P_SKILL_RANKS = 0xEF                # 48 bytes
P_WEIGHT, P_CAPACITY = 0x120, 0x124
P_SKILL_MASK = 0x128                # 8 bytes
P_BAGS, BAG_SIZE, BAG_COUNT, ITEM_SIZE = 0x130, 0x1208, 0x1200, 0x48
P_QUESTS, P_QUEST_COUNT, QUEST_SIZE = 0x41D0, 0x43D0, 0x40
P_OBJECT = 0x43D8
P_EQUIPPED = 0x4434                 # 3 pointers
P_ABILITY_SKILL = 0x4460            # +0x68 k: s16 skill id, +4 u8
P_4A80, P_4A84, P_4A85 = 0x4A80, 0x4A84, 0x4A85
P_SKILL_SLOTS = 0x4B08              # 48 x {s16, s16}
P_MISSIONS = 0x4BBF                 # 13 bytes per difficulty: bit 0 available, bit 1 complete
P_NEWWORLD_COOLDOWN = 0x4BCA        # s16
P_MEDALS = 0x4C0D                   # s8 per mission
P_EVIL, P_DECISION = 0x4C1A, 0x4C1B
P_STATUS = 0x4C1C
P_PIERCED = 0x4C26
P_FLAGS = 0x4C28

# object fields
O_FLAGS, O_POS, O_PROPS, O_ANGLE, O_VTABLE = 0x0C, 0x10, 0x2C, 0x38, 0x48
OF_NOCOLLIDE, OF_DEAD, OF_CREATURE, OF_PLAYER = 0x1, 0x8, 0x20, 0x40
OF_2000, OF_4000, OF_NOT_RUN = 0x2000, 0x4000, 0x8000
OF_FRIENDLY, OF_AUTOPROP = 0x1000000, 0x10000000
C_WEAPON_OBJ = 0x50
C_FLAGS = 0xA8                      # u64 creature flag word
C_HP = 0x228                        # float
C_HIDDEN_BYTE = 0x231               # bit 3 while hidden
C_AI_STATE = 0x232                  # s16; 0x14 is the death state
C_ROOT = 0x314                      # s16, -1 while rooted
C_VAL = {1: 0x3AC, 2: 0x3AE, 3: 0x3B0, 5: 0x3C4}
C_ACTIVITY_RADIUS = 0x3C4
C_PATH_HOME = 0x3B4                 # Vec3
CF_BOSS, CF_FOLLOW_PLAYER, CF_FRIENDLY, CF_FOLLOW_PATH = 1 << 0, 1 << 23, 1 << 26, 1 << 27
CF_BOSS_METER, CF_ON_MAP, CF_RANK_UP = 1 << 31, 1 << 43, 1 << 44
PLAYER_PUSH_DIR, PLAYER_PUSH_SPEED = 0x2E0, 0x2E8
PLAYER_VEHICLE = 0x540

# virtual slots (function pointer at vtable + 8 slot + 4, this-delta at vtable + 8 slot)
V_DESTROY, V_DAMAGE, V_TRIGGER, V_INTERACT = 1, 2, 3, 14
V_CONTAINS, V_SET_STATE, V_SEAT, V_AI_STATE, V_HOME_RANGE = 17, 18, 19, 27, 34
V_WEAPON_SET = 8                    # of the object at creature +0x50, whose table is at +0

TYPE_SCRIPT_GENERATOR = b'15ScriptGenerator'
TYPE_MONSTER_TRIGGER = b'14MonsterTrigger'
TYPE_AUTO_CONTAINER = b'13AutoContainer'
TYPE_TRIGGER = b'7Trigger'

# float patterns
F_0, F_1 = 0x00000000, 0x3F800000
F_60, F_1_60 = 0x42700000, 0x3C888888
F_1000, F_128 = 0x447A0000, 0x43000000
F_0_01, F_0_001 = 0x3C23D70A, 0x3A83126E
F_0_3 = 0x3E999999
F_100000 = 0x47C35000
F_BOX = 0x476A6000                  # 60000.0, reapEnemies
F_2, F_0_707 = 0x40000000, 0x3F34FDF3

MAX_GOLD = 99999999
DEFER_MAX, DEFER_NAME = 64, 0x50


# =======================================================================================
# 2. Memory
# =======================================================================================
class Mem:
    """Sparse little-endian memory in 4 KiB pages.  under, when given, is an object with
    read(addr, size) that supplies the first contents of a page (copy on write); without
    it pages start as zeroes.  Every store is appended to writes as (addr, size)."""
    PAGE = 4096

    def __init__(self, under=None):
        self.pages = {}
        self.under = under
        self.writes = []

    def _page(self, index):
        page = self.pages.get(index)
        if page is None:
            page = bytearray(self.PAGE)
            if self.under is not None:
                page[:] = self.under.read(index << 12, self.PAGE)
            self.pages[index] = page
        return page

    def read(self, addr, size):
        out = bytearray()
        addr &= M32
        while size > 0:
            off = addr & 0xFFF
            take = min(size, self.PAGE - off)
            out += self._page(addr >> 12)[off:off + take]
            addr, size = (addr + take) & M32, size - take
        return bytes(out)

    def write(self, addr, data):
        addr &= M32
        if data:
            self.writes.append((addr, len(data)))
        pos = 0
        while pos < len(data):
            off = addr & 0xFFF
            take = min(len(data) - pos, self.PAGE - off)
            self._page(addr >> 12)[off:off + take] = data[pos:pos + take]
            addr, pos = (addr + take) & M32, pos + take

    def load(self, addr, size):
        return int.from_bytes(self.read(addr, size), 'little')

    def store(self, addr, size, value):
        self.write(addr, (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little'))

    def u8(self, a):
        return self.load(a, 1)

    def u16(self, a):
        return self.load(a, 2)

    def u32(self, a):
        return self.load(a, 4)

    def u64(self, a):
        return self.load(a, 8)

    def s8(self, a):
        return s8(self.load(a, 1))

    def s16(self, a):
        return s16(self.load(a, 2))

    def s32(self, a):
        return s32(self.load(a, 4))

    def w8(self, a, v):
        self.store(a, 1, v)

    def w16(self, a, v):
        self.store(a, 2, v)

    def w32(self, a, v):
        self.store(a, 4, v)

    def w64(self, a, v):
        self.store(a, 8, v)

    def cstr(self, addr, limit=0x4000):
        """The bytes of a zero-terminated string."""
        out = bytearray()
        while len(out) < limit:
            byte = self.load(addr + len(out), 1)
            if byte == 0:
                return bytes(out)
            out.append(byte)
        raise HostFault('string at 0x%x has no terminator' % addr)

    def strcpy(self, addr, text):
        """libc_strcpy 0x3b868c: the bytes and the terminator, nothing more."""
        self.write(addr, bytes(text) + b'\0')


class _Global:
    """A named global of Game: kind is u8, s8, u16, s16, u32 or s32."""

    def __init__(self, addr, kind='s32', doc=''):
        self.addr, self.kind, self.size = addr, kind, int(kind[1:]) // 8
        self.__doc__ = doc

    def __get__(self, game, _owner=None):
        if game is None:
            return self
        value = game.mem.load(self.addr, self.size)
        if self.kind[0] == 's':
            sign = 1 << (8 * self.size - 1)
            value = value - (sign << 1) if value & sign else value
        return value

    def __set__(self, game, value):
        game.mem.store(self.addr, self.size, value)


# =======================================================================================
# 3. Objects
# =======================================================================================
class Obj(O.GameObject):
    """A ref_objects.GameObject whose flags (+0xc), position (+0x10) and facing (+0x38) are
    read from and written to the game memory, together with every field of the classes
    built on it (u/w below).  props is the property list (+0x2c) as a Python list of
    'key=value' byte strings, type_name the name in the class's type-info object."""

    def __init__(self, mem, addr, type_name=b'10GameObject'):
        self._mem = None
        O.GameObject.__init__(self, addr)
        self.__dict__.pop('flags', None)
        self.__dict__.pop('pos', None)
        self.__dict__.pop('angle', None)
        self._mem = mem
        self.type_name = type_name

    @property
    def flags(self):
        return self._mem.u32(self.addr + O_FLAGS) if self._mem else 0

    @flags.setter
    def flags(self, value):
        if self._mem:
            self._mem.w32(self.addr + O_FLAGS, value)

    @property
    def pos(self):
        if not self._mem:
            return [0, 0, 0]
        return [self._mem.u32(self.addr + O_POS + 4 * i) for i in range(3)]

    @pos.setter
    def pos(self, value):
        if self._mem:
            for i in range(3):
                self._mem.w32(self.addr + O_POS + 4 * i, value[i])

    @property
    def angle(self):
        return self._mem.u16(self.addr + O_ANGLE) if self._mem else 0

    @angle.setter
    def angle(self, value):
        if self._mem:
            self._mem.w16(self.addr + O_ANGLE, value)

    def u(self, offset, size):
        return self._mem.load(self.addr + offset, size)

    def w(self, offset, size, value):
        self._mem.store(self.addr + offset, size, value)

    def cflags(self):
        return self.u(C_FLAGS, 8)

    def set_cflags(self, value):
        self.w(C_FLAGS, 8, value)

    def __repr__(self):
        return '<Obj 0x%x %s>' % (self.addr, self.type_name.decode('latin-1'))


# =======================================================================================
# 4. Call-outs
# =======================================================================================
class X:
    """One call-out: address (0 for a virtual call), the integer registers a0.. it takes,
    the number of float registers f12.., words passed on the stack, and the result kind.

    Integer kinds: i a value or an address; s a C string, passed by content; v a pointer to
    three floats, passed as a tuple of patterns; p a pointer that may point into the
    handler's stack frame (then passed as the text 'stack'); T the blank item record the
    give-item built-ins prepare (passed as ITEM_BLANK); x a pointer the callee fills, not
    passed.  Result kinds: i integer, f float pattern, n nothing the built-in uses; a
    capital letter means the call-out returns something built from memory the callee
    filled - see the note."""

    def __init__(self, addr, ints='', floats=0, stack=0, ret='n', note=''):
        self.addr, self.ints, self.floats, self.stack, self.ret, self.note = addr, ints, floats, stack, ret, note


# The item record of the give-item built-ins as they blank it before item_parseDescriptor:
# bytes +0x10..+0x21 and the four 16-bit words at +0x24, +0x2c, +0x34, +0x3c.
ITEM_BLANK = (bytes(16) + b'\xff\xff', 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)

EXT = {
    # ---- net and local-slot tests -----------------------------------------------------
    'net_isLocalSlot': X(0x13E150, 'i', ret='i', note='(slot) is this player on this machine'),
    'net_getLocalPlayerSlot': X(0x13E1F0, 'i', ret='i', note='(n) slot of this machine\'s n-th player'),
    'net_firstActiveSlot': X(0x13E5A0, '', ret='i'),
    'net_closeLocalMenus': X(0x1EB000, 'i', note='(isDeath): net games only; with 0 also empties vehicles'),
    'net_dropAllRemotes': X(0x13DEF8),
    'net_sendGameMsg': X(0x13DB38, 'iB', note='(message id, bytes): the dialog request of startDialog'),
    'hudmsg_sendMedalAck': X(0x1DE5EC, note='game message 12'),
    'invmsg_sendStatPoint': X(0x1C5780, 'ii', note='inventory message 6 (slot, stat)'),
    'game_sendCharacterToLobby': X(0x1EB5C8, 'i'),
    # ---- level flow, dialog, cutscene, save ---------------------------------------------
    'dialog_isOpen': X(0x22FBC0, '', ret='i'),
    'Camera_update': X(0x203400, 'i'),
    'Camera_getYaw': X(0x207450, 'i', ret='i'),
    'Camera_getPitch': X(0x207458, 'i', ret='i'),
    'cut_start': X(0x19B4DC, 'is', note='(resource, name)'),
    'lump_load': X(0x173558, 's'),
    'res_find': X(0x17365C, 'ss', ret='i', note='(lump, entry) -> data or 0'),
    'text_lookup': X(0x173C84, 's', ret='i', note='(key) -> wide string'),
    'save_game': X(0x218128, 'iii'),
    'dbg_printf': X(0x355490, 'i'),
    'deathTask_schedule': X(0x1EBD48, 'i'),
    'memcard_requestSave': X(0x2175B4, 'i'),
    'memcard_requestEndGameSave': X(0x217C38, 'ii'),
    'memcard_requestConfigSave': X(0x217BDC),
    'memcard_getState': X(0x217550, '', ret='i'),
    'memcard_isBusy': X(0x217518, '', ret='i'),
    'menuMutex_release': X(0x22FC38),
    'missionMenu_open': X(0x231520, 'i'),
    'game_openMissionMenu': X(0x1EB4F0),
    'shop_openOrStock': X(0x1C7AF8, 'iii'),
    'playerSel_isRunning': X(0x2248E8, '', ret='i'),
    'save_playerCopy': X(0x21837C, 'i', ret='i', note='(slot) -> address of the saved record copy'),
    'game_rebuildAlivePlayers': X(0x1E72F8),
    # ---- HUD ------------------------------------------------------------------------------
    'hud_showMessage': X(0x1D92A0, 'iiii', note='(text, frames, slot or -1, force)'),
    'hud_showHelpMessage': X(0x1D9830, 'iii', note='(slot, title, body)'),
    'hud_setCompassTarget': X(0x1DF668, 'vi'),
    'hud_setBust': X(0x1DFAA0, 'siii'),
    'hud_setFade': X(0x1DF5D0, 'i'),
    'hud_stepFade': X(0x1DF5EC, 'i', ret='i'),
    'hud_drawMessageBox': X(0x1DF248, 'iiiiiiii', stack=2),
    'wstr_format': X(0x19EA78, 'pi', floats=8, note='(out, wide format, eight floats)'),
    'wstr_copy': X(0x19E854, 'ip'),
    'text_begin': X(0x1800B8, 'iiii'),
    'text_end': X(0x180500),
    'text_drawWrappedCentered': X(0x181530, 'iiiiiii', ret='i'),
    'automap_revealAll': X(0x16A760),
    # ---- audio, camera, effects -------------------------------------------------------------
    'sound_playSample': X(0x2134E8, 'iii', floats=2),
    'sound_playOnObject': X(0x214230, 'ii', floats=1, ret='i'),
    'sound_setPlaysWhileFrozen': X(0x216AD0, 'i'),
    'music_playLevel': X(0x215F48, 'si'),
    'stream_playLevel': X(0x215FC8, 'isi'),
    'stream_queueStop': X(0x211338, 'i'),
    'creature_startBossMusic': X(0x1192B0, 'i'),
    'camera_shake': X(0x1EBAE0, 'i', floats=1),
    'camera_setFarClip': X(0x18617C, '', floats=1),
    'particle_define': X(0x18F118, 'iiiiiiii', floats=3, stack=5, note='0x18f118, script setParticle'),
    'particle_spawn': X(0x18F3F8, 'ivv', floats=1),
    'decal_add': X(0x19F110, 'viii', floats=1),
    'player_voice': X(0x1B7BA8, 'ii'),
    'anim_clear': X(0x1707B0, 'i'),
    'anim_push': X(0x170838, 'iii'),
    'anim_jumpTopToEnd': X(0x170BC8, 'i'),
    'anim_releaseCaches': X(0x171118, 'i'),
    'anim_start': X(0x16CFE0, 'iii', floats=1),
    # ---- inventory and items ----------------------------------------------------------------
    'inventory_countItemByName': X(0x1C5880, 'si', ret='i'),
    'inventory_findItemBySubstring': X(0x1C5A70, 'isxx', ret='P', note='-> (index or -1, bag)'),
    'inventory_removeItem': X(0x1C1CB0, 'iiii', note='(slot, index, bag, count)'),
    'inventory_giveItem': X(0x1C1868, 'ixi', ret='i', note='(slot, item, 1) -> index in its bag'),
    'inventory_equipItem': X(0x1C27C0, 'iii', note='(slot, address of the bag entry, 0)'),
    'inventory_onStatPoint': X(0x1C2548, 'ii'),
    'item_parseDescriptor': X(0x1069B8, 'sTii', ret='i',
                              note='(text, item, -1, variant); returns the definition pointer the callee '
                                   'stores at item +0'),
    'player_itemWeight': X(0x1B6338, 'ix', ret='f'),
    'player_recalcLoad': X(0x1BEC10, 'i'),
    'player_resetIdleAnim': X(0x1B2470, 'i'),
    'player_giveExp': X(0x1D3150, 'ii'),
    'loot_spawnNamedItem': X(0x100BA0, 'vs'),
    # ---- object system (modelled by ref_objects) and spawning ---------------------------------
    'obj_moveOffGrid': X(0x14EF48, 'i'),
    'obj_updateGridCell': X(0x14F028, 'i'),
    'obj_runEveryFrame': X(0x14F248, 'i'),
    'world_collectObjectsInBox': X(0x14A928, 'vvxi', ret='L', note='-> objects'),
    'world_forEachGridObject': X(0x14A610, 'i', ret='L', note='-> objects the walk visits'),
    'world_findObjectsByClass': X(0x14C0B8, 'sxi', ret='L', note='-> objects'),
    'pool_new': X(0x14FDB8, 'i', ret='i', note='(size) -> zeroed block or 0'),
    'ItemProp_ctor2': X(0x1590EC, 'ivxi'),
    'LightEffect_ctor': X(0x201BD8, 'ivii', floats=8, stack=4),
    'SpellHornOmenEffect_ctor': X(0x2FC574, 'iiii'),
    'SpellPlanarSteelEffect_ctor': X(0x2FB728, 'iiii'),
    'ParticleMorphEffect_ctor': X(0x160A88, 'iii'),
    'creature_addSpell': X(0x11A838, 'ii'),
    'ScriptGenerator_spawn': X(0x265FC4, 'is', note='(generator, class name)'),
    'MonsterTrigger_count': X(0x1ED4E4, 'i', ret='i'),
    'Creature_setCharm': X(0x1189F0, 'iii', note='(creature, frames, team)'),
    'Creature_scaleStats': X(0x1185D8, 'i', floats=5),
    'Vehicle_attachNpcDriver': X(0x208AF0, 'ii'),
    'Vehicle_setHold': X(0x208B94, 'ii'),
}

# virtual calls: slot -> (integer kinds after this, floats, result kind)
VIRTUAL = {
    V_DESTROY: ('i', 0, 'n'),           # (this, 3): delete now
    V_DAMAGE: ('ii', 1, 'n'),           # (this, 0, 0; f12 amount)
    V_TRIGGER: ('i', 0, 'n'),           # (this, argument)
    V_WEAPON_SET: ('ii', 0, 'n'),       # (weapon object, 0, type byte)
    V_INTERACT: ('i', 0, 'n'),          # (vehicle, player slot)
    V_CONTAINS: ('i', 0, 'i'),          # (trigger, object) -> inside
    V_SET_STATE: ('i', 0, 'n'),         # (auto prop, state)
    V_SEAT: ('vxx', 0, 'P'),            # (vehicle, offset, out position, out facing) -> (position, facing)
    V_AI_STATE: ('i', 0, 'n'),          # (creature, state)
    V_HOME_RANGE: ('i', 0, 'n'),        # (creature, range)
}


class Host:
    """Answers the call-outs.  log is every call-out in order as (name, args); a virtual
    call is ('virtual', (slot, object address, ...)).  handlers[name] = f(*args) overrides
    an answer; the object-system call-outs are otherwise carried out on the model's
    ref_objects.World, and everything else answers 0."""

    def __init__(self, game=None):
        self.game = game
        self.log = []
        self.handlers = {}

    def call(self, name, *args):
        self.log.append((name, args))
        handler = self.handlers.get(name)
        if handler is not None:
            return handler(*args)
        handler = getattr(self, 'do_' + name, None)
        return handler(*args) if handler is not None else self.default(name, args)

    def default(self, name, args):
        kind = VIRTUAL[args[0]][2] if name == 'virtual' else EXT[name].ret
        if kind == 'L':
            return []
        if kind == 'P':
            return (-1, 0) if name == 'inventory_findItemBySubstring' else ((0, 0, 0), 0)
        return 0

    # the object system, through tools/ref_objects.py
    def _obj(self, addr):
        return self.game.world.objects[addr]

    def do_obj_moveOffGrid(self, addr):
        self.game.world.move_off_grid(self._obj(addr))

    def do_obj_updateGridCell(self, addr):
        self.game.world.update_grid_cell(self._obj(addr))

    def do_obj_runEveryFrame(self, addr):
        self.game.world.run_every_frame(self._obj(addr))

    def do_world_collectObjectsInBox(self, lo, hi, limit):
        return self.game.world.collect_in_box(list(lo), list(hi), limit)

    def do_world_forEachGridObject(self, _callback):
        seen = []
        self.game.world.for_each_grid_object(seen.append)
        return seen

    def do_world_findObjectsByClass(self, type_name, limit):
        return self.game.world.find_by_class(type_name, limit)

    def do_virtual(self, slot, addr, *args):
        if slot == V_DESTROY:
            world = self.game.world
            world.on_destroy(self._obj(addr), args[0])
        return self.default('virtual', (slot,))

    def do_game_rebuildAlivePlayers(self):
        self.game.rebuild_alive_players()


# =======================================================================================
# 5. The game state and the host side of the script machine
# =======================================================================================
class Args:
    """The argument cells of the built-in being called.  Handlers do not look at the
    argument count the script pushed: a[k] is the cell at params + 4 + 4 k whatever is
    there (a call that pushed too few reads the caller's stack)."""

    def __init__(self, machine):
        self.m = machine
        self.base = machine.params + 4

    def __getitem__(self, k):
        return self.m.cell(self.base + 4 * k)

    def u(self, k):
        return self[k] & M32

    def f(self, k):
        """cvt.s.w of the cell."""
        return C.from_int(self[k])

    def s(self, k, room=160):
        """scr_getAddr 0x1414a8 then scr_getString 0x141650 into a stack buffer of room
        bytes.  The handlers ignore scr_getAddr's result: a refused address leaves the
        pointer uninitialised.  The copy has no length limit."""
        address = self[k]
        if self.m.get_addr(address) != 0:
            raise HostFault('string argument %d (0x%x) is refused by scr_getAddr: the handler goes on '
                            'with an uninitialised pointer' % (k, address & M32))
        text = self.m.get_string(address)
        if len(text) >= room:
            raise HostFault('string argument %d is %d bytes: it overruns the handler\'s %d-byte stack buffer'
                            % (k, len(text), room))
        return text


class GameState:
    """Game state as the built-ins see it (see the module text): globals, players, objects,
    quest variables, deferred calls and the post action, running scripts, level change, and
    the small state functions of the gameplay area that built-ins wrap.  The built-ins
    themselves are the n_* methods of Game, below."""

    network_mode = _Global(G_NETWORK_MODE, 's8', 'g_networkMode: set in a net game')
    num_players = _Global(G_NUM_PLAYERS, 's32')
    active_player = _Global(G_ACTIVE_PLAYER, 's32', 'g_scriptActivePlayer')
    selected_obj = _Global(G_SELECTED_OBJ, 'u32', 'g_scriptSelectedObj: address or 0')
    seed = _Global(G_RAND_SEED, 'u32', 'g_randSeed, the shared seed')
    difficulty = _Global(G_DIFFICULTY, 's32')
    paused = _Global(G_PAUSED, 's32')
    cutscene_active = _Global(G_CUTSCENE_ACTIVE, 's8')
    jumpgate_travel = _Global(G_JUMPGATE_TRAVEL, 's32')
    alive_count = _Global(G_ALIVE_COUNT, 's32')
    draw_frame = _Global(G_DRAW_FRAME, 's32')
    missing_stamp = _Global(G_MISSING_STAMP, 's32')
    in_post_action = _Global(G_IN_POST_ACTION, 's8')
    defer_count = _Global(G_DEFER_COUNT, 's32')
    defer_queued = _Global(G_DEFER_QUEUED, 's32')
    defer_flip = _Global(G_DEFER_FLIP, 'u32')
    pending_orientation = _Global(G_PENDING_ORIENT, 'u8')
    medal_player = _Global(G_MEDAL_PLAYER, 'u8')
    reward_player = _Global(G_REWARD_PLAYER, 'u8')
    medal_mission = _Global(G_MEDAL_MISSION, 's32')
    medal_ack = _Global(G_MEDAL_ACK, 's32')
    medal_ticks = _Global(G_MEDAL_TICKS, 's32')
    recall_countdown = _Global(G_RECALL_COUNTDOWN, 's8')
    session_exit = _Global(G_SESSION_EXIT, 's32')
    save_inhibit = _Global(G_SAVE_INHIBIT, 's32')
    dialog_data = _Global(G_DIALOG_DATA, 'u32')

    def __init__(self, mem=None, world=None, host=None):
        self.mem = mem if mem is not None else Mem()
        self.world = world if world is not None else O.World()
        self.host = host if host is not None else Host()
        if getattr(self.host, 'game', None) is None:
            self.host.game = self
        self.machine = None
        self.entry_pri = 0              # PRI at the start of a run: uninitialised in the original
        self.draws = 0                  # shared-seed draws made by the built-ins themselves
        self._next_addr = 0x01000000

    # ---- call-outs --------------------------------------------------------------------
    def ext(self, name, *args):
        return self.host.call(name, *args)

    def virtual(self, obj, slot, *args):
        """Virtual call through the table at object +0x48."""
        return self.host.call('virtual', slot, obj.addr, *args)

    def rand(self):
        """One draw from the shared seed (the three instructions inlined at every use)."""
        self.seed = (self.seed * C.Lcg.MULTIPLIER + C.Lcg.INCREMENT) & M32
        self.draws += 1
        return self.seed >> 16

    # ---- players ------------------------------------------------------------------------
    def rec(self, slot):
        """Address of g_players[slot]; slot is used as the handlers use it, unchecked."""
        return (G_PLAYERS + s32(slot) * REC_SIZE) & M32

    def player_obj(self, slot):
        """The Obj a record's +0x43d8 points at, or None."""
        return self.obj_at(self.mem.u32(self.rec(slot) + P_OBJECT))

    def alive(self, index):
        """g_alivePlayers[index]."""
        return self.mem.s32(G_ALIVE_LIST + 4 * index)

    def rebuild_alive_players(self):
        """game_rebuildAlivePlayers 0x1e72f8, the two shared words only (the default
        answer of that call-out): slots whose object exists and is not dead, in order."""
        living = []
        for slot in range(self.num_players):
            obj = self.player_obj(slot)
            if obj is not None and not obj.flags & OF_DEAD:
                living.append(slot)
        for index, slot in enumerate(living):
            self.mem.w32(G_ALIVE_LIST + 4 * index, slot)
        self.alive_count = len(living)

    # ---- objects --------------------------------------------------------------------------
    def obj_at(self, addr):
        """The Obj at an address; None for 0.  An address that is no known object is what
        a stale or uninitialised pointer would be."""
        if addr == 0:
            return None
        obj = self.world.objects.get(addr)
        if obj is None:
            raise HostFault('0x%x is not an object of the model' % addr)
        return obj

    def new_object(self, names=(), flags=0, pos=(0, 0, 0), angle=0, type_name=b'10GameObject',
                   props=None, addr=None, size=0x1000):
        """Put an object into the model's world: an Obj in the registry, linked to the grid
        and entered in the name table under each of names (and under every 'name='
        property).  This is state set-up for users and tests, not GameObject_ctor: it
        draws nothing from the seed."""
        if addr is None:
            addr = self._next_addr
            self._next_addr += (size + 15) & ~15
        obj = Obj(self.mem, addr, type_name)
        obj.flags, obj.pos, obj.angle = flags, [p & M32 for p in pos], angle
        obj.props = list(props) if props is not None else None
        world = self.world
        world.handles.link(world.home_cell(obj, True), obj.heads[2], obj)
        for name in list(names) + [entry[5:] for entry in (obj.props or ()) if entry[:5] == b'name=']:
            world.names.add(name, obj)
        world.objects[addr] = obj
        return obj

    def find(self, name, limit):
        """world_findObjectsByName 0x14bf58 (name, out, limit): at most limit - 1 objects,
        in the name table's probe order - see ref_objects.NameTable.find."""
        return self.world.names.find(name, limit)

    def find_first(self, name):
        """world_findObjectByName 0x14f498: the first of them, or None."""
        return self.world.names.find_first(name)

    def need(self, obj, what):
        if obj is None:
            raise HostFault('%s: no such object, and the handler does not check - it reads and writes '
                            'through address 0' % what)
        return obj

    # ---- quest variables: vars_* 0x1ed728-0x1eda07 -------------------------------------------
    @staticmethod
    def _lower(name):
        """The in-place lower-casing both lookups do with the C library's character table
        (ASCII upper case + 0x20); the table is indexed with a signed char."""
        name = bytes(name)
        if any(c >= 0x80 for c in name):
            raise HostFault('non-ASCII variable name: the original indexes its table with a negative number')
        return name.lower()

    def _var_slot(self, table, name):
        """Walk a packed table: address of the entry whose name equals name (strcmp), or
        of the terminating empty name."""
        where = table
        while self.mem.u8(where) != 0:
            entry = self.mem.cstr(where)
            if entry == name:
                return where, True
            where += len(entry) + 2
        return where, False

    def var_get(self, name):
        """vars_get 0x1ed778: the signed value byte.  A name that is not in the table is
        APPENDED with value 0 (so reading changes the table)."""
        name = self._lower(name)
        where, found = self._var_slot(G_QUEST_VARS, name)
        if not found:
            self.mem.strcpy(where, name)
            self.mem.w8(where + len(name) + 1, 0)
            return 0
        return self.mem.s8(where + len(name) + 1)

    def var_set(self, name, value):
        """vars_set 0x1ed854: value clamped to -128..127; the entry is created if needed."""
        value = max(-128, min(127, s32(value)))
        name = self._lower(name)
        where, found = self._var_slot(G_QUEST_VARS, name)
        if not found:
            self.mem.strcpy(where, name)
        self.mem.w8(where + len(name) + 1, value)

    def vars_clear_all(self):
        """vars_clearAll 0x1ed728: every value becomes 0; the names stay."""
        where = G_QUEST_VARS
        while self.mem.u8(where) != 0:
            length = len(self.mem.cstr(where))
            self.mem.w8(where + length + 1, 0)
            where += length + 2

    def var_by_index(self, index):
        """vars_getByIndex 0x1ed974 (the save builder's reader): (name, value) or None."""
        where = G_QUEST_VARS
        while self.mem.u8(where) != 0:
            name = self.mem.cstr(where)
            if index == 0:
                return name, self.mem.s8(where + len(name) + 1)
            index -= 1
            where += len(name) + 2
        return None

    def quest_vars(self):
        """The whole table in table order, as [(name, value)]."""
        out, index = [], 0
        while True:
            entry = self.var_by_index(index)
            if entry is None:
                return out
            out.append(entry)
            index += 1

    def profile_get(self, name):
        """profile_getVar 0x22289c: the same table format at 0x4f9030 (this machine's
        profile); an unknown name is appended with 0 by 0x222a44."""
        name = self._lower(name)
        where, found = self._var_slot(G_PROFILE_VARS, name)
        if not found:
            self.mem.strcpy(where, name)
            self.mem.w8(where + len(name) + 1, 0)
            return 0
        return self.mem.s8(where + len(name) + 1)

    def profile_set(self, name, value, save):
        """profile_setVar 0x22274c (name, value, save): clamps, stores; when the value
        changed (or the name was new) and save is set, asks for a config save."""
        value = max(-128, min(127, s32(value)))
        name = self._lower(name)
        where, found = self._var_slot(G_PROFILE_VARS, name)
        if found:
            if self.mem.s8(where + len(name) + 1) == value:
                return
            self.mem.w8(where + len(name) + 1, value)
        else:
            self.mem.strcpy(where, name)
            self.mem.w8(where + len(name) + 1, value)
        if save:
            self.ext('memcard_requestConfigSave')

    # ---- deferred calls and the post action ------------------------------------------------
    def queue_deferred(self, name):
        """script_queueDeferred 0x1ed52c: copy the name into the half of the buffer that is
        NOT being run; a 65th name is dropped."""
        queued = self.defer_queued
        if queued < DEFER_MAX:
            self.defer_queued = queued + 1
            half = (self.defer_flip & 1) ^ 1
            self.mem.strcpy(G_DEFER_NAMES + half * DEFER_MAX * DEFER_NAME + queued * DEFER_NAME, name)

    def run_deferred(self):
        """script_runDeferred 0x1ed5a0, the run task "Script" (priority 125): run every
        name of the current half in order - the count is read again after each run - then
        swap the halves."""
        index = 0
        while index < self.defer_count:
            half = self.defer_flip & 1
            name = self.mem.cstr(G_DEFER_NAMES + half * DEFER_MAX * DEFER_NAME + index * DEFER_NAME)
            index += 1
            self.run_script(name)
        self.defer_count = self.defer_queued
        self.defer_queued = 0
        self.defer_flip = self.defer_flip + 1

    def clear_deferred(self):
        """script_clearDeferred 0x1eda08."""
        self.defer_count = 0
        self.defer_queued = 0
        self.defer_flip = 0

    def reset_script_state(self):
        """script_resetState 0x1eda78 (from game_resetState): the queue and the post
        action."""
        self.clear_deferred()
        self.mem.w8(G_POST_ACTION, 0)

    def set_post_action(self, name):
        """script_setPostAction 0x1eda9c: one name; a second call replaces the first."""
        self.mem.strcpy(G_POST_ACTION, name)

    def run_post_action(self):
        """script_runPostAction 0x1edac0: if a name is set, take it, clear the buffer and
        run it with g_scriptInPostAction = 1."""
        if self.mem.u8(G_POST_ACTION) != 0:
            name = self.mem.cstr(G_POST_ACTION)
            self.mem.w8(G_POST_ACTION, 0)
            self.in_post_action = 1
            self.run_script(name)
            self.in_post_action = 0

    # ---- running scripts ----------------------------------------------------------------------
    def set_script(self, machine):
        """script_setCurrent 0x1ed650: the level's machine (None for a level without one);
        scr_load and scr_registerNatives are the caller's business in the model, but the
        built-ins are bound here when the machine has unbound natives."""
        self.machine = machine
        if machine is not None:
            machine.register(self.natives())

    def run_script(self, name):
        """script_runByName 0x1ed694: -1 when there is no machine or no such entry point
        (then also g_scriptMissingStamp = g_drawFrame + 20 if the old stamp has passed);
        otherwise the run's result, or 0 when the run ended with an error."""
        machine = self.machine
        if name is None or machine is None:
            return -1
        error, index = machine.find_public(name)
        if error:
            if self.missing_stamp < self.draw_frame:
                self.missing_stamp = self.draw_frame + 20
            return -1
        error, result = machine.execute(index, pri=self.entry_pri)
        return 0 if result is None else result

    # ---- level change ---------------------------------------------------------------------------
    def net_gate(self):
        """newWorld_netGate 0x143d04 -> 1 to refuse.  Net games only, and only for an
        active player other than -1: while that player's cooldown (record +0x4bca) runs
        and more than one player is alive the change is refused, and the active player's
        own machine shows a HUD line; otherwise the cooldown is set to 600."""
        if self.network_mode != 0 and self.active_player != -1:
            slot = self.active_player
            cooldown = self.rec(slot) + P_NEWWORLD_COOLDOWN
            if self.mem.u16(cooldown) != 0 and not self.alive_count < 2:
                if self.ext('net_isLocalSlot', slot & M32) != 0:
                    text = self.ext('text_lookup', b'noZone3')
                    local = self.ext('net_getLocalPlayerSlot', 0)
                    self.ext('hud_showMessage', text & M32, 180, local & M32, 0)
                return 1
            self.mem.w16(cooldown, 600)
        return 0

    def set_next_world(self, name):
        """script_setNextWorld 0x1472c4: the name goes to g_pendingLevel; the entrance
        orientation byte is atoi of the selected object's 'orientation=' property (every
        such entry is applied, so the last one wins), or 0xff when there is no selected
        object or no such property.  The comparison is a case-sensitive strncmp of 12
        characters."""
        self.mem.strcpy(G_PENDING_LEVEL, name)
        found = False
        selected = self.obj_at(self.selected_obj)
        if selected is not None:
            if selected.props is None:
                raise HostFault('selected object has no property list: the original reads through a null pointer')
            for entry in selected.props:
                if bytes(entry[:12]) == b'orientation=':
                    found = True
                    self.pending_orientation = O.atoi(entry[12:])
        if not found:
            self.pending_orientation = 0xFF

    # ---- state functions of the gameplay area the built-ins wrap ----------------------------------
    def mission_byte(self, slot, difficulty, mission):
        return (self.rec(slot) + P_MISSIONS + s32(difficulty) * 13 + mission) & M32

    def mission_is_available(self, difficulty, mission):
        """mission_isAvailable 0x1bf698: bit 0 of record 0's mission byte; 0 for a mission
        of 13 or more (signed test: a negative number is accepted)."""
        if not mission < 13:
            return 0
        return self.mem.u8(self.mission_byte(0, difficulty, mission)) & 1

    def mission_set_available(self, difficulty, mission, on):
        """mission_setAvailable 0x1bf6d0: bit 0, in the first g_numPlayers records."""
        if mission < 13:
            for slot in range(max(self.num_players, 0)):
                where = self.mission_byte(slot, difficulty, mission)
                self.mem.w8(where, (self.mem.u8(where) & 0xFE) | (on & 1))

    def mission_is_complete(self, difficulty, mission):
        """mission_isComplete 0x1bf730: bit 1 of record 0's byte."""
        if not mission < 13:
            return 0
        return (self.mem.u8(self.mission_byte(0, difficulty, mission)) >> 1) & 1

    def mission_set_complete(self, difficulty, mission, value):
        """mission_setComplete 0x1bf770: bit 1 in ALL FOUR records, whatever the player
        count; value -1 sets it, any other value stores its bit 0."""
        if mission < 13:
            for slot in range(4):
                where = self.mission_byte(slot, difficulty, mission)
                byte = self.mem.u8(where)
                byte = byte | 2 if value == -1 else (byte & 0xFD) | ((value & 1) << 1)
                self.mem.w8(where, byte)

    def mission_grant_medal(self, mission, level):
        """mission_grantMedal 0x1bdb80: for every player whose medal byte is below level:
        that player becomes the reward player (0x4f7149), the entry points firstBronze,
        firstSilver, firstGold are run for each level gained (in that order, each through
        script_runByName), then the byte is stored."""
        if not mission < 13:
            return
        slot = 0
        while slot < self.num_players:
            where = (self.rec(slot) + P_MEDALS + mission) & M32
            have = self.mem.s8(where)
            if have < level:
                self.reward_player = slot
                while True:
                    if have == 0:
                        self.run_script(b'firstBronze')
                        have = 1
                    elif have == 1:
                        self.run_script(b'firstSilver')
                        have = 2
                    else:
                        self.run_script(b'firstGold')
                        have += 1
                    if not have < level:
                        break
                self.mem.w8(where, level)
            slot += 1

    def mission_get_medal(self, mission, level, flag):
        """mission_getMedal 0x1bf838 (mission, level, flag): the medal byte of
        net_getLocalPlayerSlot(0) - of slot 0 instead when flag is set in a net game.
        level -1 returns the byte, otherwise whether it has reached level."""
        slot = 0
        if flag == 0 or self.network_mode == 0:
            slot = s32(self.ext('net_getLocalPlayerSlot', 0))
        if not mission < 13:
            return 0
        medal = self.mem.s8((self.rec(slot) + P_MEDALS + mission) & M32)
        if level == -1:
            return medal
        return 0 if medal < level else 1

    def quest_add(self, title, text):
        """quest_add 0x1d386c.  Players are taken in order and the whole call ENDS at the
        first player whose list is full (8) or already has the title; until then each
        player gets the pair appended."""
        slot = 0
        while slot < self.num_players:
            rec = self.rec(slot)
            count = self.mem.s32(rec + P_QUEST_COUNT)
            if count > 7:
                return
            for index in range(max(count, 0)):
                if self.mem.cstr(rec + P_QUESTS + index * QUEST_SIZE) == title:
                    return
            self.mem.strcpy(rec + P_QUESTS + count * QUEST_SIZE, title)
            self.mem.strcpy(rec + P_QUESTS + count * QUEST_SIZE + 0x20, text)
            self.mem.w32(rec + P_QUEST_COUNT, count + 1)
            slot += 1

    def quest_remove(self, title):
        """quest_remove 0x1d3968: in every player's list each entry with that title has
        both strings overwritten by a nine-byte placeholder; then the entries behind the
        LAST such entry move up by one and the count drops by one (only one, however many
        matched)."""
        placeholder = b'NoQuests\0'
        for slot in range(max(self.num_players, 0)):
            rec = self.rec(slot)
            last = -1
            index = 0
            while index < self.mem.s32(rec + P_QUEST_COUNT):
                entry = rec + P_QUESTS + index * QUEST_SIZE
                if self.mem.cstr(entry) == title:
                    self.mem.write(entry, placeholder)
                    self.mem.write(entry + 0x20, placeholder)
                    last = index
                index += 1
            if last != -1:
                while last < self.mem.s32(rec + P_QUEST_COUNT) - 1:
                    entry = rec + P_QUESTS + last * QUEST_SIZE
                    self.mem.strcpy(entry, self.mem.cstr(entry + QUEST_SIZE))
                    self.mem.strcpy(entry + 0x20, self.mem.cstr(entry + QUEST_SIZE + 0x20))
                    last += 1
                self.mem.w32(rec + P_QUEST_COUNT, self.mem.s32(rec + P_QUEST_COUNT) - 1)

    def player_set_flag(self, slot, bit, on):
        """player_setFlag 0x1be398: bit (number taken mod 32, stored in a byte) of record
        +0x4c28; slot -1 means the first g_numPlayers records."""
        mask = (1 << (bit & 31)) & 0xFF
        slots = range(max(self.num_players, 0)) if slot == -1 else (slot,)
        for each in slots:
            where = self.rec(each) + P_FLAGS
            byte = self.mem.u8(where)
            self.mem.w8(where, byte | mask if on != 0 else byte & ~mask)

    def player_get_flag(self, slot, bit):
        """player_getFlag 0x1bfb80."""
        return self.mem.u8(self.rec(slot) + P_FLAGS) & ((1 << (bit & 31)) & M32)

    def _difficulty_bit(self):
        return (1 << (self.difficulty & 31)) & M32

    def get_evil(self):
        """game_getEvil 0x1bf8d8: record 0 +0x4c1a masked with 1 << difficulty (the masked
        value, not 0 or 1)."""
        return self.mem.u8(self.rec(0) + P_EVIL) & self._difficulty_bit()

    def _set_choice(self, offset, on):
        mask = self._difficulty_bit() & 0xFF
        for slot in range(max(self.num_players, 0)):
            where = self.rec(slot) + offset
            byte = self.mem.u8(where)
            self.mem.w8(where, byte | mask if on != 0 else byte & ~mask)

    def set_evil(self, on):
        """game_setEvil 0x1bf8f8: that bit in the first g_numPlayers records."""
        self._set_choice(P_EVIL, on)

    def get_made_decision(self):
        """game_getMadeDecision 0x1bf960: record 0 +0x4c1b."""
        return self.mem.u8(self.rec(0) + P_DECISION) & self._difficulty_bit()

    def set_made_decision(self, on):
        """game_setMadeDecision 0x1bf980."""
        self._set_choice(P_DECISION, on)

    def count_players_with_hp(self):
        """game_countPlayersWithHp 0x1ebec8."""
        return sum(1 for slot in range(max(self.num_players, 0))
                   if C.lt(F_0, self.mem.u32(self.rec(slot) + P_HP)))

    def save_player_record(self):
        """game_savePlayerRecord 0x1ec720 (script savePlayer): the medal player's whole
        record is copied to save_playerCopy(slot); 0x4f85c0 = 1."""
        slot = self.medal_player
        copy = self.ext('save_playerCopy', slot) & M32
        self.mem.write(copy, self.mem.read(self.rec(slot), REC_SIZE))
        self.mem.w32(G_SOLO_SAVED, 1)

    def restore_player_record(self):
        """game_restorePlayerRecord 0x1eb6f8 (script restorePlayer): the copy comes back,
        except medals (+0x4c0d, 8 bytes), +0x4c15 (4 bytes), +0x4c19, +0x78 (24 bytes) and
        the object pointer, which keep their live values.  Then the respawn countdown
        0x4f7194 = 240, the four per-player death countdowns = 240 (highest slot first),
        the alive list is rebuilt and 0x4f85c0 = 0."""
        slot = self.medal_player
        rec = self.rec(slot)
        kept = [(offset, self.mem.read(rec + offset, size))
                for offset, size in ((P_MEDALS, 8), (0x4C15, 4), (0x4C19, 1), (P_KEEP_78, 24), (P_OBJECT, 4))]
        copy = self.ext('save_playerCopy', slot) & M32
        self.mem.write(rec, self.mem.read(copy, REC_SIZE))
        self.mem.w32(G_RESPAWN_COUNTDOWN, 240)
        for offset, data in kept:
            self.mem.write(rec + offset, data)
        for index in (3, 2, 1, 0):
            self.mem.w16(G_DEAD_COUNTDOWN + 2 * index, 240)
        self.ext('game_rebuildAlivePlayers')
        self.mem.w32(G_SOLO_SAVED, 0)

    def dialog_start(self, name, a, b):
        """dialog_start 0x22fa50 (script startDialog).  Camera_update on this machine's
        camera, 0x4fdce8 = 0; then, only where the active player is local and no dialog is
        open, game message 0 is sent: a zero byte, the name length, the name, 0xff padding
        to a multiple of four, the active player, a, b, a zero byte, this machine's camera
        position (three floats) and its yaw and pitch (16 bits each)."""
        camera = self.mem.u32(G_LOCAL_CAMERA)
        self.ext('Camera_update', camera)
        self.mem.w32(G_SWOOP_DONE, 0)
        if self.ext('net_isLocalSlot', self.active_player & M32) != 0 and self.dialog_data == 0:
            message = bytearray([0, len(name) & 0xFF]) + bytes(name)
            while len(message) & 3:
                message.append(0xFF)
            message += bytes([self.active_player & 0xFF, a & 0xFF, b & 0xFF, 0])
            message += self.mem.read(G_CAMERA_POS, 12)
            message += (self.ext('Camera_getYaw', camera) & 0xFFFF).to_bytes(2, 'little')
            message += (self.ext('Camera_getPitch', camera) & 0xFFFF).to_bytes(2, 'little')
            self.ext('net_sendGameMsg', self.mem.u32(G_DIALOG_MSG_ID), bytes(message))

    # ---- the table ------------------------------------------------------------------------------
    def natives(self):
        """name -> callable(machine, args) for tools/ref_amx.py, for every built-in the
        model has (NOT_MODELLED lists the rest; calling one raises HostFault)."""
        table = {}
        for name in NATIVE_NAMES:
            method = getattr(self, 'n_' + name, None)
            if method is None:
                table[name] = self._missing(name)
            else:
                table[name] = (lambda machine, _args, method=method: method(machine, Args(machine)))
        return table

    @staticmethod
    def _missing(name):
        def native(_machine, _args):
            raise HostFault('built-in %s is not modelled' % name)
        return native


# =======================================================================================
# 6. The built-ins.  Each is  n_<name>(machine, a) -> cell , a being the Args of the call;
#    the address is the handler's.  Order: script control, quest state, level flow, menus
#    and HUD, players, items, creatures, other objects and effects, audio, vehicles.
# =======================================================================================
# Text keys and resource names that built-ins pass to presentation call-outs are read from
# the executable's data through mem (the model embeds none of them).
S_NO_ZONE = 0x531280                # HUD line of the refused level change
S_SAVE_DEBUG = 0x531250             # debug text of saveCheckPoint
S_HEAL_LUMP, S_HEAL_SOUND = 0x531398, 0x5313A0
S_MEDAL_PROMPT, S_MEDAL_WON, S_MEDAL_FAIL = 0x531230, 0x531220, 0x531240
S_PROP_LUMP_KEY = 0x531278          # property key startPropAnim asks for
S_ORC_CAVE = 0x5312A8               # level-name fragment givePlayerRandom looks for
S_ORC_SWORDS = {1: (0x5312B8, 0x12, 0x33), 2: (0x531308, 0x33, 0x34), 3: (0x531358, 0x24, 0x35)}
POINTER_TYPES = (0x3C7D20, 0x3C7D70, 0x3C7DC0)      # type-info getters reapEnemies compares with


class Game(GameState):
    """GameState plus the built-ins."""

    # ---------------------------------------------------------------------------------
    # script control and pure helpers
    # ---------------------------------------------------------------------------------
    def n_callScript(self, m, a):
        """0x143158 (s entry): script_runByName; nested on the same machine."""
        return self.run_script(a.s(0))

    def n_addDeferedCall(self, m, a):
        """0x144160 (s entry)."""
        self.queue_deferred(a.s(0))
        return 0

    def n_postAction(self, m, a):
        """0x143ee4 (s entry)."""
        self.set_post_action(a.s(0))
        return 0

    def n_print(self, m, a):
        """0x143120 (s text): converts the string and drops it."""
        a.s(0)
        return 0

    def n_printVal(self, m, a):
        """0x143150."""
        return 0

    def n_getRand(self, m, a):
        """0x146570: one shared-seed draw, 0..65535."""
        return self.rand()

    def n_getScaledTime(self, m, a):
        """0x14412c (i n): (int)((float)n * 60.0 * (1/60 truncated))."""
        return C.to_int(C.mul(C.mul(a.f(0), F_60), F_1_60))

    def n_sin1000(self, m, a):
        """0x141fb0 (i angle16)."""
        return C.to_int(C.mul(C.sin16(a[0]), F_1000))

    def n_cos1000(self, m, a):
        """0x141fe0 (i angle16)."""
        return C.to_int(C.mul(C.cos16(a[0]), F_1000))

    def n_gamePaused(self, m, a):
        """0x14699c: g_paused, or the jump-gate travel state (0x27dd68), or a cutscene."""
        return 1 if self.paused != 0 or self.jumpgate_travel != 0 or self.cutscene_active != 0 else 0

    def n_demoRunning(self, m, a):
        """0x141764."""
        return 0

    def n_networkMode(self, m, a):
        """0x142214: the flag byte itself."""
        return self.network_mode

    def n_levelLoading(self, m, a):
        """0x146aa4."""
        return self.mem.s32(G_LEVEL_LOADING)

    def n_getLevelTimer(self, m, a):
        """0x1421a8: the frame counter 0x4f85cc as an unsigned number, times 1/60."""
        ticks = self.mem.u32(G_LEVEL_TIMER)
        if ticks & 0x80000000:
            value = C.from_int((ticks >> 1) | (ticks & 1))
            value = C.add(value, value)
        else:
            value = C.from_int(ticks)
        return C.to_int(C.mul(value, F_1_60))

    # ---------------------------------------------------------------------------------
    # quest variables, profile variables, campaign progress
    # ---------------------------------------------------------------------------------
    def n_getv(self, m, a):
        """0x143500 (s name)."""
        return self.var_get(a.s(0))

    def n_setv(self, m, a):
        """0x143540 (s name, i value)."""
        self.var_set(a.s(0), a[1])
        return 0

    def n_addv(self, m, a):
        """0x143588 (s name, i delta): returns the sum before clamping."""
        name = a.s(0)
        total = s32(self.var_get(name) + a[1])
        self.var_set(name, total)
        return total

    def n_getpv(self, m, a):
        """0x143480 (s name)."""
        return self.profile_get(a.s(0))

    def n_setpv(self, m, a):
        """0x1434b4 (s name, i value): profile_setVar with save = 1."""
        self.profile_set(a.s(0), a[1], 1)
        return 0

    def n_getEvil(self, m, a):
        """0x142044."""
        return self.get_evil()

    def n_setEvil(self, m, a):
        """0x142058 (i on): a zero argument does nothing."""
        if a[0] != 0:
            self.set_evil(a[0])
        return 0

    def n_getMadeDecision(self, m, a):
        """0x142010."""
        return self.get_made_decision()

    def n_setMadeDecision(self, m, a):
        """0x142024."""
        self.set_made_decision(1)
        return 0

    def n_grantMission(self, m, a):
        """0x1420a4 (i mission)."""
        self.mission_set_complete(self.difficulty, a[0], -1)
        return 0

    def n_getMissionComplete(self, m, a):
        """0x142084 (i mission)."""
        return self.mission_is_complete(self.difficulty, a[0])

    def n_setMissionAvailable(self, m, a):
        """0x1420d0 (i mission, i on)."""
        self.mission_set_available(self.difficulty, a[0], a[1])
        return 0

    def n_getMissionAvailable(self, m, a):
        """0x1420fc (i mission)."""
        return self.mission_is_available(self.difficulty, a[0])

    def n_grantGold(self, m, a):
        """0x14211c (i mission)."""
        self.mission_grant_medal(a[0], 3)
        return 0

    def n_grantSilver(self, m, a):
        """0x142140 (i mission)."""
        self.mission_grant_medal(a[0], 2)
        return 0

    def n_grantBronze(self, m, a):
        """0x142164 (i mission)."""
        self.mission_grant_medal(a[0], 1)
        return 0

    def n_getMedal(self, m, a):
        """0x142188 (i mission): this machine's first local player's medal."""
        return self.mission_get_medal(a[0], -1, 0)

    def n_addQuest(self, m, a):
        """0x1433c8 (s title, s text)."""
        title = a.s(0)
        self.quest_add(title, a.s(1))
        return 0

    def n_removeQuest(self, m, a):
        """0x143448 (s title)."""
        self.quest_remove(a.s(0))
        return 0

    # ---------------------------------------------------------------------------------
    # level flow, cutscenes, dialog, saving
    # ---------------------------------------------------------------------------------
    def n_newWorld(self, m, a):
        """0x143dd0 (s level); newWorldAlways is the same handler.  Outside a post action
        the net gate decides; then net_closeLocalMenus(0) and script_setNextWorld."""
        name = a.s(0)
        if self.in_post_action != 0 or self.net_gate() == 0:
            self.ext('net_closeLocalMenus', 0)
            if len(name) >= 0x70:
                raise HostFault('level name of %d bytes overruns script_setNextWorld\'s buffer' % len(name))
            self.set_next_world(name)
        return 0

    n_newWorldAlways = n_newWorld

    def n_simpleNewWorld(self, m, a):
        """0x143e70 (s level): the same gate; orientation 0xff without looking at the
        selected object."""
        name = a.s(0)
        if self.in_post_action != 0 or self.net_gate() == 0:
            self.ext('net_closeLocalMenus', 0)
            self.pending_orientation = 0xFF
            self.mem.strcpy(G_PENDING_LEVEL, name)
        return 0

    def n_newWorldPost(self, m, a):
        """0x143cc4 (s level): the dialog-end handler moves it to the next-world buffer."""
        self.mem.strcpy(G_POST_DIALOG_LEVEL, a.s(0))
        return 0

    def n_newWorldParameter(self, m, a):
        """0x1471fc: the selected object's first 'level=' property (strncmp, 6
        characters); no gate, no null check."""
        selected = self.need(self.obj_at(self.selected_obj), 'newWorldParameter without a selected object')
        if selected.props is None:
            raise HostFault('selected object has no property list')
        for entry in selected.props:
            if bytes(entry[:6]) == b'level=':
                self.ext('net_closeLocalMenus', 0)
                self.set_next_world(bytes(entry[6:]))
                break
        return 0

    def n_setEntrance(self, m, a):
        """0x142a94 (s name)."""
        self.mem.strcpy(G_ENTRANCE_NAME, a.s(0))
        return 0

    def n_cutScene(self, m, a):
        """0x143f1c (s name): res_find("<level>.lmp", "<name>.cut"), then cut_start."""
        name = a.s(0)
        lump = self.mem.cstr(G_LEVEL_NAME) + b'.lmp'
        cut = name + b'.cut'
        self.ext('cut_start', self.ext('res_find', lump, cut) & M32, cut)
        return 0

    def n_startDialog(self, m, a):
        """0x143824 (s name, i a, i b): lump_load("<level>.lmp"), then dialog_start."""
        name = a.s(0)
        self.ext('lump_load', self.mem.cstr(G_LEVEL_NAME) + b'.lmp')
        self.dialog_start(name, a[1], a[2])
        return 0

    def n_dialogRunning(self, m, a):
        """0x143cb0."""
        return self.ext('dialog_isOpen')

    def n_forceMutexRelease(self, m, a):
        """0x1471dc."""
        self.ext('menuMutex_release')
        return 0

    def n_changeSwoop(self, m, a):
        """0x1438b0 (i mode)."""
        self.mem.w32(G_SWOOP, a[0])
        return 0

    def n_startWithSwoopDone(self, m, a):
        """0x1438c4."""
        self.mem.w32(G_SWOOP_DONE, 1)
        return 0

    def n_leaveGame(self, m, a):
        """0x146ab0 (i how)."""
        self.session_exit = 1 if a[0] == 0 else 0x65
        return 0

    def n_endGame(self, m, a):
        """0x146ad4."""
        self.ext('memcard_requestEndGameSave', 0, 1)
        return 0

    def n_exitToMainMenu(self, m, a):
        """0x146d80."""
        self.session_exit = 1
        return 0

    def n_saveGame(self, m, a):
        """0x146c04: nothing when any player's status (record +0x4c1c, low five bits) is
        2; otherwise the save flow of this machine's first local player."""
        slot = 0
        while slot < self.num_players:
            if self.mem.u32(self.rec(slot) + P_STATUS) & 0x1F == 2:
                return 0
            slot += 1
        self.ext('memcard_requestSave', self.ext('net_getLocalPlayerSlot', 0) & M32)
        return 0

    def n_saveEndConfig(self, m, a):
        """0x146c78: end of the campaign."""
        self.ext('game_sendCharacterToLobby', M32)
        self.mem.w8(G_UNKNOWN_4D8A08, 0)
        self.mem.w8(G_UNKNOWN_4039C0, 0)
        self.mem.w32(G_MENU_OPEN_FLAG, 1)
        self.mem.w8(G_GAME_COMPLETE, 1)
        self.paused = 1
        if self.network_mode != 0:
            self.ext('net_dropAllRemotes')
        bit = {1: 0x08, 2: 0x10, 3: 0x20, 4: 0x40}.get(self.difficulty)
        if bit is not None:
            self.mem.w32(G_SAVED_CONFIG, self.mem.u32(G_SAVED_CONFIG) | bit)
        self.ext('memcard_requestConfigSave')
        return 0

    def n_saveDone(self, m, a):
        """0x146d5c: this machine's card state is idle (-1)."""
        return 1 if s32(self.ext('memcard_getState')) == -1 else 0

    def n_saveCheckPoint(self, m, a):
        """0x142a40."""
        self.ext('dbg_printf', S_SAVE_DEBUG)
        self.ext('save_game', 0, 0, 1)
        return 0

    def n_loadCheckPoint(self, m, a):
        """0x142a74."""
        self.ext('deathTask_schedule', 0)
        return 0

    def n_setSaveInhibit(self, m, a):
        """0x1473b4 (i on)."""
        self.save_inhibit = a[0]
        return 0

    def n_getSaveInhibit(self, m, a):
        """0x1473c8."""
        return self.save_inhibit

    def n_setAlternateDeath(self, m, a):
        """0x141790."""
        self.mem.w32(G_ALT_DEATH, 1)
        return 0

    def n_preloadResource(self, m, a):
        """0x14222c (s lump)."""
        self.ext('lump_load', a.s(0))
        return 0

    def n_clearRecall(self, m, a):
        """0x146af8: the five bytes "None\\0" over record +0x24 of every player."""
        slot = 0
        while slot < self.num_players:
            self.mem.write(self.rec(slot) + P_RECALL, b'None\0')
            slot += 1
        return 0

    def n_playersLoaded(self, m, a):
        """0x147278."""
        slot = 0
        while slot < self.num_players:
            if self.mem.u32(self.rec(slot) + P_OBJECT) != 0:
                return 1
            slot += 1
        return 0

    def n_pauseGameControl(self, m, a):
        """0x1469f0 (i frames)."""
        self.mem.w32(G_MENU_LOCKOUT, a[0])
        self.mem.w32(G_MENU_LOCKOUT_HOLD, 1)
        return 0

    # ---------------------------------------------------------------------------------
    # menus, HUD, medal results
    # ---------------------------------------------------------------------------------
    def n_activateMissionMenu(self, m, a):
        """0x143fa8: offline the active player's menu, in a net game net_firstActiveSlot's."""
        if self.ext('dialog_isOpen') == 0 and self.recall_countdown == 0:
            if self.network_mode == 0:
                self.ext('missionMenu_open', self.active_player & M32)
            else:
                self.ext('missionMenu_open', self.ext('net_firstActiveSlot') & M32)
        return 0

    def n_activateStore(self, m, a):
        """0x144010 (i store).  With a dialog open only the pending flag is set."""
        if a.u(0) < 0x15:
            self.mem.w16(G_STORE_INDEX, a[0])
        if self.ext('dialog_isOpen') == 0:
            if self.network_mode == 0:
                self.ext('shop_openOrStock', self.active_player & M32, 0, 1)
            else:
                index = 0
                while index < self.alive_count:
                    if self.ext('net_isLocalSlot', self.alive(index) & M32) != 0:
                        self.ext('net_closeLocalMenus', 0)
                        self.ext('shop_openOrStock', self.alive(index) & M32, 0, 1)
                    index += 1
        else:
            self.mem.w8(G_STORE_PENDING, 1)
        return 0

    def n_storeRunning(self, m, a):
        """0x1440f8."""
        return self.mem.s32(G_SHOP_OPEN)

    def n_setInfo(self, m, a):
        """0x14318c (s textKey)."""
        self.ext('hud_showMessage', self.ext('text_lookup', a.s(0)) & M32, 180, M32, 0)
        return 0

    def n_addHelpMessage(self, m, a):
        """0x1431d8 (s titleKey, s bodyKey)."""
        title_key = a.s(0)
        body_key = a.s(1)
        title = self.ext('text_lookup', title_key) & M32
        body = self.ext('text_lookup', body_key) & M32
        self.ext('hud_showHelpMessage', M32, title, body)
        return 0

    def n_addHelpMessageF(self, m, a):
        """0x143270 (s key1, i v1, s key2, i v2): each text formatted with its number (as
        the first of eight float arguments) into a stack buffer, copied to two static
        buffers, shown."""
        key1 = a.s(0)
        key2 = a.s(2)
        self.ext('wstr_format', 'stack', self.ext('text_lookup', key1) & M32, a.f(1), 0, 0, 0, 0, 0, 0, 0)
        self.ext('wstr_format', 'stack', self.ext('text_lookup', key2) & M32, a.f(3), 0, 0, 0, 0, 0, 0, 0)
        self.ext('wstr_copy', G_HELP_TITLE_BUF, 'stack')
        self.ext('wstr_copy', G_HELP_BODY_BUF, 'stack')
        self.ext('hud_showHelpMessage', M32, G_HELP_TITLE_BUF, G_HELP_BODY_BUF)
        return 0

    def n_helpMessageActive(self, m, a):
        """0x1433bc."""
        return self.mem.u8(G_HELP_OPEN)

    def n_showCompass(self, m, a):
        """0x1427b4 (s object, s textKey): no null check on the object."""
        name = a.s(0)
        key = a.s(1)
        obj = self.need(self.find_first(name), 'showCompass')
        text = self.ext('text_lookup', key) & M32
        self.ext('hud_setCompassTarget', tuple(obj.pos), text)
        return 0

    def n_showBust(self, m, a):
        """0x142864 (s texture, s textKey, i a, i b)."""
        texture = a.s(0)
        key = a.s(1)
        self.ext('hud_setBust', texture, self.ext('text_lookup', key) & M32, a.u(2), a.u(3))
        return 0

    def n_hudResetFadeScreen(self, m, a):
        """0x14277c (i on)."""
        self.ext('hud_setFade', a.u(0))
        return 0

    def n_hudFadeScreen(self, m, a):
        """0x14279c (i delta): returns hud_stepFade's result."""
        return self.ext('hud_stepFade', a.u(0))

    def n_revealMap(self, m, a):
        """0x141e78."""
        self.ext('automap_revealAll')
        return 0

    def n_showOnMap(self, m, a):
        """0x141e98 (s name, i on): bit 43 of the creature flag word, up to 99 objects."""
        for obj in self.find(a.s(0), 100):
            if obj.flags & OF_CREATURE:
                if a[1] == 0:
                    obj.set_cflags(obj.cflags() & ~CF_ON_MAP & M64)
                else:
                    obj.set_cflags(obj.cflags() | CF_ON_MAP)
        return 0

    def _medal_gate(self):
        """The head of both medal screens: 0 = return 0 now, 1 = draw and test the pad,
        2 = skip the drawing and test the pad."""
        self.medal_ticks = 2
        if self.network_mode == 0:
            self.paused = 1
            return 0 if self.ext('memcard_isBusy') != 0 else 1
        if self.medal_player == self.ext('net_getLocalPlayerSlot', 0) & M32:
            if self.ext('memcard_isBusy') != 0:
                return 0
            if self.medal_ack == 0:
                self.ext('hudmsg_sendMedalAck')
                return 0
            return 1
        if self.medal_ack == 0:
            return 0
        return 2 if self.ext('memcard_isBusy') != 0 else 1

    def _medal_prompt(self):
        """The button prompt, only where the medal player is local (or offline)."""
        if self.network_mode == 0 or self.ext('net_getLocalPlayerSlot', 0) & M32 == self.medal_player:
            text = self.ext('text_lookup', self.mem.cstr(S_MEDAL_PROMPT)) & M32
            self.ext('wstr_format', G_MEDAL_PROMPT_BUF, text, C.from_int(self.mem.s32(G_BTN_NAME_A)),
                     C.from_int(self.mem.s32(G_BTN_NAME_B)), 0, 0, 0, 0, 0, 0)
            return G_MEDAL_PROMPT_BUF
        return 0

    def _medal_pad(self):
        """The tail of both: the medal player's pressed buttons.  Confirm restarts the
        level (next world = current level, orientation 0xff); cancel opens the mission
        menu; either returns 1."""
        pressed = self.mem.u32(G_PADS + self.medal_player * PAD_SIZE + 0xC)
        if pressed & self.mem.u32(G_BTN_CONFIRM):
            self.mem.strcpy(G_PENDING_LEVEL, self.mem.cstr(G_LEVEL_NAME))
            self.pending_orientation = 0xFF
            return 1
        if pressed & self.mem.u32(G_BTN_CANCEL):
            self.ext('game_openMissionMenu')
            return 1
        return 0

    def n_runMedalSuccess(self, m, a):
        """0x1417a4 (i mission, i oldMedal, s title, s line1, s line2, s line3): the medal
        result screen, called every frame.  Line k (1..3) is drawn when oldMedal < k <=
        the local player's medal for the mission."""
        gate = self._medal_gate()
        if gate == 0:
            return 0
        if gate == 1:
            self.ext('text_begin', self.mem.u32(G_HUD_FONT), 6, 0x80323C3C, M32)
            old = a[1]
            medal = self.mission_get_medal(a[0], -1, 0)
            keys, heights, total = [], [0, 0, 0, 0], 0
            for k in range(4):
                keys.append(a.s(2 + k, 128))
                if k == 0 or (old < medal and old < k and not medal < k):
                    text = self.ext('text_lookup', keys[k]) & M32
                    height = s32(self.ext('text_drawWrappedCentered', 0x140, 0xDC, text, 0x15E, 100, 100, 0x11))
                    heights[k] = s32(height + (0x11 if k else 0x22))
                    total = s32(total + heights[k] + 0x11)
            y = s32(0xD8 - _tdiv(total, 2))
            text = self.ext('text_lookup', keys[0]) & M32
            self.ext('text_drawWrappedCentered', 0x140, y & M32, text, 0x15E, -100 & M32, 0x244, 0x11)
            y = s32(y + heights[0])
            for k in (1, 2, 3):
                if heights[k] != 0:
                    text = self.ext('text_lookup', keys[k]) & M32
                    self.ext('text_drawWrappedCentered', 0x140, y & M32, text, 0x15E, -100 & M32, 0x244, 0x11)
                    y = s32(y + heights[k])
            self.ext('text_end')
            prompt = self._medal_prompt()
            title = self.ext('text_lookup', self.mem.cstr(S_MEDAL_WON)) & M32
            self.ext('hud_drawMessageBox', title, 0, prompt, 0x80, 400, total & M32, 0, M32, 0, 0)
        return self._medal_pad()

    def n_runMedalFail(self, m, a):
        """0x141c00 (s textKey): the same flow with the failure box."""
        gate = self._medal_gate()
        if gate == 0:
            return 0
        if gate == 1:
            key = a.s(0)
            prompt = self._medal_prompt()
            title = self.ext('text_lookup', self.mem.cstr(S_MEDAL_FAIL)) & M32
            body = self.ext('text_lookup', key) & M32
            self.ext('hud_drawMessageBox', title, body, prompt, 0x80, 0, 0, 0, M32, 0, 0)
        return self._medal_pad()

    def n_setupPlayerSel(self, m, a):
        """0x142bb8."""
        return 0

    def n_startPlayerSel(self, m, a):
        """0x142bc0."""
        return 0

    def n_playerSelRunning(self, m, a):
        """0x142bc8."""
        return self.ext('playerSel_isRunning')

    # ---------------------------------------------------------------------------------
    # players
    # ---------------------------------------------------------------------------------
    def n_getNumPlayers(self, m, a):
        """0x143534."""
        return self.num_players

    def n_countPlayersAlive(self, m, a):
        """0x142220."""
        return self.alive_count

    def n_checkPlayerAlive(self, m, a):
        """0x1470ac (i which)."""
        if a[0] != 0:
            return 1 if self.mem.s32(G_RESPAWN_COUNTDOWN) > 0 else 0
        return self.count_players_with_hp()

    def n_setBestActivePlayer(self, m, a):
        """0x1470e0: 0, or 1 when player 0 has no object or is dead and there are exactly
        two players."""
        first = self.player_obj(0)
        if (first is None or first.flags & OF_DEAD) and self.num_players == 2:
            self.active_player = 1
        else:
            self.active_player = 0
        return self.active_player

    def n_activePlayerIsDwarf(self, m, a):
        """0x1465a0: record +0x54 (model index) of the active player is 0."""
        return 1 if self.mem.s32(self.rec(self.active_player) + P_MODEL) == 0 else 0

    def n_activePlayerIsElf(self, m, a):
        """0x1465c4."""
        return 0

    def n_isClericOrWizard(self, m, a):
        """0x1465cc (i player): class 1 or 4; player must be 0..3 and <= g_numPlayers."""
        player = a.u(0)
        if player < 4 and player <= self.num_players:
            return 1 if self.mem.s32(self.rec(player) + P_CLASS) in (1, 4) else 0
        return 0

    def n_getMaxPlayerHP(self, m, a):
        """0x1428fc (i player, counted from 1)."""
        slot = s32(a[0] - 1)
        if slot < 0 or not slot < self.num_players:
            return -1
        return C.to_int(self.mem.u32(self.rec(slot) + P_MAX_HP))

    def _refill(self, only_living):
        slot = 0
        while slot < self.num_players:
            rec = self.rec(slot)
            if not only_living or C.lt(F_0, self.mem.u32(rec + P_HP)):
                self.mem.w32(rec + P_HP, self.mem.u32(rec + P_MAX_HP))
            slot += 1

    def n_healPlayer(self, m, a):
        """0x1468ac: a cast sound on player 0's object, then full hit points for every
        player whose hit points are above 0."""
        sound = self.ext('res_find', self.mem.cstr(S_HEAL_LUMP), self.mem.cstr(S_HEAL_SOUND)) & M32
        self.ext('sound_playOnObject', sound, self.mem.u32(self.rec(0) + P_OBJECT), F_1)
        self._refill(True)
        return 0

    def n_giveFullHealth(self, m, a):
        """0x146950: full hit points for every player, dead or not."""
        self._refill(False)
        return 0

    def n_zeroPlayerMana(self, m, a):
        """0x142450."""
        slot = 0
        while slot < self.num_players:
            self.mem.w32(self.rec(slot) + P_MANA, 0)
            slot += 1
        return 0

    def n_refillPlayerMana(self, m, a):
        """0x142494."""
        slot = 0
        while slot < self.num_players:
            rec = self.rec(slot)
            self.mem.w32(rec + P_MANA, self.mem.u32(rec + P_MAX_MANA))
            slot += 1
        return 0

    def _distance3(self, a, b):
        dx, dy, dz = C.sub(a[0], b[0]), C.sub(a[1], b[1]), C.sub(a[2], b[2])
        return C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))), dx, dy

    def n_hitPlayers(self, m, a):
        """0x1424dc (s object, i radius, i damage, i push): every living player nearer than
        radius takes damage (virtual slot 2, no attacker) and is pushed away.  No null
        check on the object or on a living player's object."""
        centre = self.need(self.find_first(a.s(0)), 'hitPlayers')
        index = 0
        while index < self.alive_count:
            slot = self.alive(index)
            index += 1
            player = self.need(self.player_obj(slot), 'hitPlayers: living player without an object')
            distance, dx, dy = self._distance3(player.pos, centre.pos)
            if C.lt(distance, a.f(1)):
                self.virtual(player, V_DAMAGE, 0, 0, a.f(2))
                again = self.need(self.player_obj(self.alive(index - 1)), 'hitPlayers')
                again.w(PLAYER_PUSH_SPEED, 4, a.f(3))
                angle = C.atan2_16(dy, dx)
                again = self.need(self.player_obj(self.alive(index - 1)), 'hitPlayers')
                again.w(PLAYER_PUSH_DIR, 2, angle)
        return 0

    def n_closestPlayerDist(self, m, a):
        """0x14268c (s object): distance to the nearest living player, 100000 if none."""
        centre = self.find_first(a.s(0))
        best = F_100000
        index = 0
        while index < self.alive_count:
            player = self.player_obj(self.alive(index))
            index += 1
            if player is not None:
                distance = self._distance3(player.pos, self.need(centre, 'closestPlayerDist').pos)[0]
                if C.lt(distance, best):
                    best = distance
        return C.to_int(best)

    def n_givePlayerExp(self, m, a):
        """0x146278 (i amount)."""
        slot = 0
        while slot < self.num_players:
            self.ext('player_giveExp', slot, a.u(0))
            slot += 1
        return 0

    def n_givePlayerGold(self, m, a):
        """0x1462dc (i amount): amount / players (C division) to each, capped."""
        slot = 0
        while slot < self.num_players:
            where = self.rec(slot) + P_GOLD
            gold = s32(self.mem.s32(where) + _tdiv(a[0], self.num_players))
            self.mem.w32(where, gold)
            if gold > MAX_GOLD:
                self.mem.w32(where, MAX_GOLD)
            slot += 1
        return 0

    def n_takePlayerGold(self, m, a):
        """0x1463ec (i amount): not below 0."""
        slot = 0
        while slot < self.num_players:
            where = self.rec(slot) + P_GOLD
            gold = s32(self.mem.s32(where) - _tdiv(a[0], self.num_players))
            self.mem.w32(where, max(gold, 0))
            slot += 1
        return 0

    def n_checkPlayerGold(self, m, a):
        """0x14644c: the sum."""
        total, slot = 0, 0
        while slot < self.num_players:
            total = s32(total + self.mem.s32(self.rec(slot) + P_GOLD))
            slot += 1
        return total

    def n_checkPlayerMinGold(self, m, a):
        """0x146494: the smallest; player 0's when there is one player or none."""
        least, slot = self.mem.s32(self.rec(0) + P_GOLD), 1
        while slot < self.num_players:
            least = min(least, self.mem.s32(self.rec(slot) + P_GOLD))
            slot += 1
        return least

    def n_playerAdjustStat(self, m, a):
        """0x146348 (i player, i stat, i count): stat 4..8.  Player -1 applies the points
        to the reward player directly; any other player SENDS inventory message 6."""
        player, stat, count = a[0], a[1], a[2]
        reward = self.reward_player
        if (stat - 4) & M32 < 5:
            for _ in range(max(count, 0)):
                if player == -1:
                    self.ext('inventory_onStatPoint', reward, stat & M32)
                else:
                    self.ext('invmsg_sendStatPoint', player & M32, stat & M32)
        return 0

    def n_setPlayerFlag(self, m, a):
        """0x1416d4 (i player, i bit, i on)."""
        self.player_set_flag(a[0], a[1], a[2])
        return 0

    def n_getPlayerFlag(self, m, a):
        """0x1416fc (i player, i bit) -> 0 or 1."""
        return 1 if self.player_get_flag(a[0], a[1]) != 0 else 0

    def n_piercePlayerEar(self, m, a):
        """0x145610 (i player): record +0x4c26 = 1 for that player (0..3) or all (-1)."""
        player = a.u(0)
        if player == M32:
            slot = 0
            while slot < self.num_players:
                self.mem.w8(self.rec(slot) + P_PIERCED, 1)
                slot += 1
        elif player < 4:
            self.mem.w8(self.rec(player) + P_PIERCED, 1)
        return 0

    def n_clearAllSkills(self, m, a):
        """0x1458e0: the medal player's skills."""
        rec = self.rec(self.medal_player)
        self.mem.w64(rec + P_SKILL_MASK, 0)
        for k in range(48):
            self.mem.w8(rec + P_SKILL_RANKS + k, 0)
        for k in range(48):
            self.mem.w16(rec + P_SKILL_SLOTS + 4 * k, 0xFFFF)
            self.mem.w16(rec + P_SKILL_SLOTS + 4 * k + 2, 0xFFFF)
        self.mem.w32(rec + P_SKILL_POINTS, 0)
        self.mem.w8(rec + P_4A85, 1)
        self.mem.w32(rec + P_4A80, 0)
        self.mem.w8(rec + P_4A84, 0)
        for k in range(15):
            self.mem.w16(rec + P_ABILITY_SKILL + 0x68 * k, 0xFFFF)
            self.mem.w8(rec + P_ABILITY_SKILL + 0x68 * k + 4, 0)
        return 0

    def n_savePlayer(self, m, a):
        """0x141724."""
        self.save_player_record()
        return 0

    def n_restorePlayer(self, m, a):
        """0x141744."""
        self.restore_player_record()
        return 0

    def n_hidePlayers(self, m, a):
        """0x147098 (i on): the low byte."""
        self.mem.w8(G_HIDE_PLAYERS, a[0])
        return 0

    def n_decayPlayerLights(self, m, a):
        """0x147130 (i target1, i target2, i step): 0x4f83f4 += step / 100, stored; when
        the new value has reached the target in the direction of the step, the target is
        stored and the result is 1.  target2 applies when exactly two players are alive."""
        target = C.mul(a.f(1) if self.alive_count == 2 else a.f(0), F_0_01)
        step = C.mul(a.f(2), F_0_01)
        value = C.add(self.mem.u32(G_LIGHT_SCALE), step)
        self.mem.w32(G_LIGHT_SCALE, value)
        if (C.lt(F_0, step) and C.le(target, value)) or (C.lt(step, F_0) and C.le(value, target)):
            self.mem.w32(G_LIGHT_SCALE, target)
            return 1
        return 0

    def _spell_effect(self, ctor, size, heal):
        slot = 0
        while slot < self.num_players:
            rec = self.rec(slot)
            if heal and C.lt(F_0, self.mem.u32(rec + P_HP)):
                self.mem.w32(rec + P_HP, self.mem.u32(rec + P_MAX_HP))
            target = self.mem.u32(rec + P_OBJECT)
            if target != 0:
                block = self.ext('pool_new', size) & M32
                if block != 0:
                    self.ext(ctor, block, 1, self.mem.u32(rec + P_OBJECT), self.mem.u32(SKILL_PTR_HORN))
                self.ext('creature_addSpell', self.mem.u32(rec + P_OBJECT), block)
            slot += 1
        return 0

    def n_hornOmen(self, m, a):
        """0x146628: a 0x20-byte spell effect on every player object.  creature_addSpell is
        called even when the allocation failed (with 0)."""
        return self._spell_effect('SpellHornOmenEffect_ctor', 0x20, False)

    def n_planarSteel(self, m, a):
        """0x1466d4: full hit points for living players, then a 0x6c-byte spell effect."""
        return self._spell_effect('SpellPlanarSteelEffect_ctor', 0x6C, True)

    def n_getManaUsed(self, m, a):
        """0x1421fc."""
        return self.mem.u16(G_MANA_USED)

    def n_getHealthUsed(self, m, a):
        """0x142208."""
        return self.mem.u16(G_HEALTH_USED)

    def n_playGotItemSound(self, m, a):
        """0x1464e8: the active player is clamped to 0..1 AND STORED; the voice goes to the
        value it had before the clamp, unless there are two or more players and that
        player's hit points are not above 0 - then to 1 if the clamped value is 0, else 0."""
        slot = self.active_player
        if slot < 0:
            self.active_player = 0
        elif not slot < 2:
            self.active_player = 1
        if not self.num_players < 2 and C.le(self.mem.u32(self.rec(slot) + P_HP), F_0):
            slot = 1 if self.active_player != 1 else 0
        self.ext('player_voice', slot & M32, 9)
        return 0

    def n_explodePotionsOnly(self, m, a):
        """0x1433a8."""
        self.mem.w32(G_POTIONS_ONLY, 1)
        return 0

    # ---------------------------------------------------------------------------------
    # items
    # ---------------------------------------------------------------------------------
    def n_playerHasItem(self, m, a):
        """0x145590 (s item): the sum over all players."""
        name = a.s(0)
        total, slot = 0, 0
        while slot < self.num_players:
            total = s32(total + self.ext('inventory_countItemByName', name, slot))
            slot += 1
        return total

    def n_onePlayerHasItem(self, m, a):
        """0x145690 (i player, s item): 0 unless the player has a living object."""
        slot = a[0]
        if slot < self.num_players:
            player = self.player_obj(slot)
            if player is not None and not player.flags & OF_DEAD:
                return self.ext('inventory_countItemByName', a.s(1), slot & M32)
        return 0

    def n_countQuestItems(self, m, a):
        """0x145720 (s item): player 0's bags only."""
        return self.ext('inventory_countItemByName', a.s(0), 0)

    def n_removePlayerItem(self, m, a):
        """0x14598c (i player, s text): the item inventory_findItemBySubstring picks is
        removed; player -1 means every player."""
        text = a.s(1)
        player = a[0]
        if player == -1:
            slot = 0
            while slot < self.num_players:
                index, bag = self.ext('inventory_findItemBySubstring', slot, text)
                if s32(index) != -1:
                    self.ext('inventory_removeItem', slot, index & M32, bag & M32, 0)
                slot += 1
        elif player < self.num_players:
            index, bag = self.ext('inventory_findItemBySubstring', player & M32, text)
            if s32(index) != -1:
                self.ext('inventory_removeItem', player & M32, index & M32, bag & M32, 0)
        return 0

    def _empty_bag(self, slot, bag):
        rec = self.rec(slot)
        for _ in range(max(self.mem.s32(rec + P_BAGS + bag * BAG_SIZE + BAG_COUNT), 0)):
            if self.mem.u32(rec + P_BAGS + bag * BAG_SIZE) != 0:
                self.ext('inventory_removeItem', slot, 0, bag, 0)

    def n_removeAllItems(self, m, a):
        """0x145758: the medal player's three bags: as many removals of entry 0 as the bag
        held items (the count is read once per bag)."""
        slot = self.medal_player
        for bag in range(3):
            self._empty_bag(slot, bag)
        return 0

    def n_removeAllWeapons(self, m, a):
        """0x145828: bag 0 of the medal player, then the three equipped pointers."""
        slot = self.medal_player
        self._empty_bag(slot, 0)
        for k in range(3):
            self.mem.w32(self.rec(slot) + P_EQUIPPED + 4 * k, 0)
        return 0

    def _drop_at(self, pos_of):
        """A ground item (0x190-byte block, ItemProp_ctor2) at a position."""
        block = self.ext('pool_new', 400) & M32
        if block != 0:
            self.ext('ItemProp_ctor2', block, tuple(pos_of().pos), 0)

    def _give(self, slot, text, variant, equip, strict, reset_idle):
        rec = self.rec(slot)
        definition = self.ext('item_parseDescriptor', text, ITEM_BLANK, M32, variant & M32) & M32
        weight = self.ext('player_itemWeight', slot & M32) & M32
        fits = C.lt(C.add(self.mem.u32(rec + P_WEIGHT), weight), self.mem.u32(rec + P_CAPACITY))
        if fits or (not strict and C.eq(weight, F_0)):
            index = s32(self.ext('inventory_giveItem', slot & M32, 1))
            self.ext('player_recalcLoad', slot & M32)
            if equip != 0:
                bag = self.mem.s8(definition + 0x1D)
                entry = (rec + P_BAGS + bag * BAG_SIZE + index * ITEM_SIZE) & M32
                self.ext('inventory_equipItem', slot & M32, entry, 0)
                if reset_idle:
                    self.ext('player_resetIdleAnim', slot & M32)
            return True
        return False

    def n_givePlayerItem(self, m, a):
        """0x145a88 (s descriptor, i equip, i variant): every player, or only the medal
        player while medal mode 0x4f713c is set.  An item that does not fit (and weighs
        something) becomes a ground item at the player, or at the first living player when
        this one has no object."""
        text = a.s(0)
        variant = a[2]
        slot = 0
        while slot < self.num_players:
            if self.medal_mission == 0 or slot == self.medal_player:
                if not self._give(slot, text, variant, a[1], False, True):
                    if self.mem.u32(self.rec(slot) + P_OBJECT) == 0:
                        self._drop_at(lambda: self.need(self.player_obj(self.alive(0)), 'givePlayerItem'))
                    else:
                        self._drop_at(lambda slot=slot: self.player_obj(slot))
            slot += 1
        return 0

    def n_giveOnePlayerItem(self, m, a):
        """0x145d20 (i player, s descriptor, i equip, i variant): one living player; the
        weight test is strict."""
        slot = a[0]
        if slot < self.num_players:
            variant = a[3]
            player = self.player_obj(slot)
            if player is not None and not player.flags & OF_DEAD:
                text = a.s(1)
                if not self._give(slot, text, variant, a[2], True, False):
                    self._drop_at(lambda: self.player_obj(slot))
        return 0

    def n_dropItem(self, m, a):
        """0x1477ac (s object, s descriptor): loot_spawnNamedItem at the object, nothing
        when there is none."""
        obj = self.find_first(a.s(0))
        text = a.s(1)
        if obj is not None:
            self.ext('loot_spawnNamedItem', tuple(obj.pos), text)
        return 0

    def n_selectDropItem(self, m, a):
        """0x147860 (s descriptor): at the selected object."""
        text = a.s(0)
        selected = self.obj_at(self.selected_obj)
        if selected is not None:
            self.ext('loot_spawnNamedItem', tuple(selected.pos), text)
        return 0

    # ---------------------------------------------------------------------------------
    # creatures ("creatures named X": the name's objects that have flag 0x20)
    # ---------------------------------------------------------------------------------
    def _creatures(self, a, limit=0x200):
        return [obj for obj in self.find(a.s(0), limit) if obj.flags & OF_CREATURE]

    def n_increaseEnemyRank(self, m, a):
        """0x144200 (s name): bit 44."""
        for obj in self._creatures(a):
            obj.set_cflags(obj.cflags() | CF_RANK_UP)
        return 0

    def n_charmMonster(self, m, a):
        """0x14429c (s name): Creature_setCharm(creature, -1, 0)."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                self.ext('Creature_setCharm', obj.addr, M32, 0)
        return 0

    def n_rootMonster(self, m, a):
        """0x14433c (s name): unless in the death state."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE and s16(obj.u(C_AI_STATE, 2)) != 0x14:
                obj.w(C_ROOT, 2, 0xFFFF)
                self.virtual(obj, V_AI_STATE, 0)
        return 0

    def n_unRootMonster(self, m, a):
        """0x144408 (s name)."""
        for obj in self._creatures(a):
            obj.w(C_ROOT, 2, 0)
        return 0

    def apply_monster_val(self, obj, which, value):
        """script_applyMonsterVal 0x144494: which 1, 2, 3, 5 store the low 16 bits at
        +0x3ac, +0x3ae, +0x3b0, +0x3c4; 4 calls virtual slot 34 with them."""
        if obj is None:
            return
        if which == 4:
            self.virtual(obj, V_HOME_RANGE, value & 0xFFFF)
        elif which in C_VAL:
            obj.w(C_VAL[which], 2, value)

    def n_selectSetMonsterVal(self, m, a):
        """0x144514 (i which, i value): the selected object; no null check."""
        selected = self.need(self.obj_at(self.selected_obj), 'selectSetMonsterVal without a selected object')
        if selected.flags & OF_CREATURE:
            self.apply_monster_val(selected, a[0], a[1])
        return 0

    def n_setMonsterVal(self, m, a):
        """0x144550 (s name, i which, i value)."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                self.apply_monster_val(obj, a[1], a[2])
        return 0

    def apply_cflag(self, obj, bit, on):
        """script_applyCFlag 0x1445fc: only bits 0 and 26 can be changed.  Bit 0 (boss):
        clearing it while bit 31 is set also clears bit 31 and the boss meter words; set or
        cleared, creature_startBossMusic is called."""
        if obj is None:
            return
        if bit == 0:
            if not on and obj.cflags() & CF_BOSS_METER:
                self.mem.w32(G_BOSS_HP, 0)
                self.mem.w32(G_BOSS_MAX_HP, 0)
                obj.set_cflags(obj.cflags() & ~CF_BOSS_METER & M64)
            self.ext('creature_startBossMusic', obj.addr)
        elif bit != 26:
            return
        if on:
            obj.set_cflags(obj.cflags() | (1 << bit))
        else:
            obj.set_cflags(obj.cflags() & ~(1 << bit) & M64)

    def n_selectSetCFlag(self, m, a):
        """0x1446d0 (i bit, i on)."""
        selected = self.obj_at(self.selected_obj)
        if selected is not None and selected.flags & OF_CREATURE:
            self.apply_cflag(selected, a[0], a[1] != 0)
        return 0

    def n_setCFlag(self, m, a):
        """0x144714 (s name, i bit, i on)."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                self.apply_cflag(obj, a[1], a[2] != 0)
        return 0

    def apply_oflag(self, obj, which, on):
        """script_applyOFlag 0x1447c4: only which == 14: object flag 0x4000."""
        if obj is not None and which == 14:
            obj.flags = obj.flags | OF_4000 if on else obj.flags & ~OF_4000 & M32

    def n_selectSetOFlag(self, m, a):
        """0x1447fc (i which, i on)."""
        selected = self.obj_at(self.selected_obj)
        if selected is not None:
            self.apply_oflag(selected, a[0], a[1] != 0)
        return 0

    def n_setOFlag(self, m, a):
        """0x144834 (s name, i which, i on): any object."""
        for obj in self.find(a.s(0), 0x200):
            self.apply_oflag(obj, a[1], a[2] != 0)
        return 0

    def n_setWeaponType(self, m, a):
        """0x1448e4 (s name, i type): virtual slot 8 of the object at creature +0x50, when
        there is one, with (0, type as a byte)."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                weapon = obj.u(C_WEAPON_OBJ, 4)
                if weapon != 0:
                    self.host.call('virtual', V_WEAPON_SET, weapon, 0, a[1] & 0xFF)
        return 0

    def n_setMonsterRange(self, m, a):
        """0x1449b4 (s name, i range): virtual slot 34 when range > 0."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE and a[1] > 0:
                self.virtual(obj, V_HOME_RANGE, a[1] & 0xFFFF)
        return 0

    def n_killMonster(self, m, a):
        """0x144a84 (s name): creatures not already dead."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & (OF_CREATURE | OF_DEAD) == OF_CREATURE:
                obj.flags = obj.flags | OF_2000 | OF_DEAD | OF_NOCOLLIDE
                obj.w(C_HP, 4, 0)
                self.virtual(obj, V_AI_STATE, 0x14)
        return 0

    def n_deleteMonster(self, m, a):
        """0x144b44 (s name): virtual slot 1 with 3 - destroyed at once."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                self.virtual(obj, V_DESTROY, 3)
        return 0

    def n_hideMonster(self, m, a):
        """0x144c00 (s name): ANY object: off the grid, flag 0x8000; creatures also get
        bit 3 of +0x231."""
        for obj in self.find(a.s(0), 0x200):
            self.ext('obj_moveOffGrid', obj.addr)
            flags = obj.flags
            obj.flags = flags | OF_NOT_RUN
            if flags & OF_CREATURE:
                obj.w(C_HIDDEN_BYTE, 1, obj.u(C_HIDDEN_BYTE, 1) | 8)
        return 0

    def n_showMonster(self, m, a):
        """0x144db8 (s name): the reverse."""
        for obj in self.find(a.s(0), 0x200):
            self.ext('obj_updateGridCell', obj.addr)
            flags = obj.flags
            obj.flags = flags & ~OF_NOT_RUN & M32
            if flags & OF_CREATURE:
                obj.w(C_HIDDEN_BYTE, 1, obj.u(C_HIDDEN_BYTE, 1) & 0xF7)
        return 0

    def n_moveMonster(self, m, a):
        """0x144cb8 (s name, s target): position and facing of the target to every object
        of the name; each is relinked into the grid."""
        objs = self.find(a.s(0), 0x200)
        target = self.find_first(a.s(1))
        if target is not None:
            for obj in objs:
                obj.pos = target.pos
                obj.angle = target.angle
                self.ext('obj_updateGridCell', obj.addr)
        return 0

    def n_followPlayer(self, m, a):
        """0x144e78 (s name): bit 23 and the charm call."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                obj.set_cflags(obj.cflags() | CF_FOLLOW_PLAYER)
                self.ext('Creature_setCharm', obj.addr, M32, 0)
        return 0

    def n_stopFollowingPlayer(self, m, a):
        """0x144f2c (s name)."""
        for obj in self._creatures(a):
            obj.set_cflags(obj.cflags() & ~CF_FOLLOW_PLAYER & M64)
        return 0

    def _follow_path(self, obj):
        if obj.flags & OF_CREATURE and not obj.cflags() & CF_FOLLOW_PATH:
            obj.set_cflags(obj.cflags() | CF_FOLLOW_PATH)
            obj.w(C_ACTIVITY_RADIUS, 2, 44000)
            self.ext('obj_runEveryFrame', obj.addr)

    def _stop_path(self, obj):
        if obj.flags & OF_CREATURE and obj.cflags() & CF_FOLLOW_PATH:
            obj.w(C_ACTIVITY_RADIUS, 2, 0x47E)
            obj.set_cflags(obj.cflags() & ~CF_FOLLOW_PATH & M64)
            pos = obj.pos
            for k in range(3):
                obj.w(C_PATH_HOME + 4 * k, 4, pos[k])
            if s16(obj.u(C_AI_STATE, 2)) != 0x14:
                self.virtual(obj, V_AI_STATE, 0)

    def n_followPath(self, m, a):
        """0x144fc8 (s name): bit 27, activity radius 44000, onto the every-frame list."""
        for obj in self.find(a.s(0), 0x200):
            self._follow_path(obj)
        return 0

    def n_selectFollowPath(self, m, a):
        """0x145090."""
        selected = self.obj_at(self.selected_obj)
        if selected is not None:
            self._follow_path(selected)
        return 0

    def n_stopFollowingPath(self, m, a):
        """0x1450ec (s name): radius 1150, bit 27 cleared, position remembered at +0x3b4,
        AI state 0 unless dead."""
        for obj in self.find(a.s(0), 0x200):
            self._stop_path(obj)
        return 0

    def n_selectStopPath(self, m, a):
        """0x1451f0."""
        selected = self.obj_at(self.selected_obj)
        if selected is not None:
            self._stop_path(selected)
        return 0

    def n_friendly(self, m, a):
        """0x145294 (s name): object flag 0x1000000 and bit 26."""
        for obj in self._creatures(a):
            obj.flags = obj.flags | OF_FRIENDLY
            obj.set_cflags(obj.cflags() | CF_FRIENDLY)
        return 0

    def n_unFriendly(self, m, a):
        """0x145338 (s name)."""
        for obj in self._creatures(a):
            obj.flags = obj.flags & ~OF_FRIENDLY & M32
            obj.set_cflags(obj.cflags() & ~CF_FRIENDLY & M64)
        return 0

    def n_reapEnemies(self, m, a):
        """0x1453e4: every dead creature that is not a player, among up to 511 objects of
        a box of +-60000, is destroyed.  For the others the class is compared with three
        POINTER types, which no object has, so nothing else is ever destroyed."""
        box = (F_BOX | 0x80000000,) * 3
        for obj in self.ext('world_collectObjectsInBox', box, (F_BOX,) * 3, 0x200):
            if obj.flags & (OF_CREATURE | OF_DEAD) == OF_CREATURE | OF_DEAD and not obj.flags & OF_PLAYER:
                self.virtual(obj, V_DESTROY, 3)
        return 0

    def n_checkMonstersLeft(self, m, a):
        """0x1441c0: 1 when the grid walk meets a living creature that is not a player
        (callback 0x144198)."""
        self.mem.w8(G_NO_MONSTER_FLAG, 1)
        for obj in self.ext('world_forEachGridObject', 0x144198):
            flags = obj.flags
            if not flags & OF_PLAYER and flags & (OF_CREATURE | OF_DEAD) == OF_CREATURE:
                self.mem.w8(G_NO_MONSTER_FLAG, 0)
        return 1 if self.mem.u8(G_NO_MONSTER_FLAG) == 0 else 0

    def n_getHitPoints(self, m, a):
        """0x142944 (s name): the first creature of the name, 0 if none."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                return C.to_int(obj.u(C_HP, 4))
        return 0

    def n_setHitPoints(self, m, a):
        """0x1429e0 (s name, i value): the first object if it is a creature; no null check."""
        obj = self.need(self.find_first(a.s(0)), 'setHitPoints')
        if obj.flags & OF_CREATURE:
            obj.w(C_HP, 4, a.f(1))
        return 0

    def n_generateMonster(self, m, a):
        """0x1473d4 (s generator, s className): the class name is interned in a table of
        24-byte names (0x5d32c8, count byte 0x4f8409); then every object of the generator
        name whose class is ScriptGenerator spawns one."""
        generator = a.s(0)
        class_name = a.s(1)
        count = self.mem.s8(G_GEN_COUNT)
        index = -1
        for k in range(max(count, 0)):
            if self.mem.cstr(G_GEN_NAMES + 24 * k) == class_name:
                index = k
                break
        if index == -1:
            index = count
            self.mem.w8(G_GEN_COUNT, count + 1)
            self.mem.strcpy(G_GEN_NAMES + 24 * index, class_name)
        for obj in self.find(generator, 0x200):
            if obj.type_name == TYPE_SCRIPT_GENERATOR:
                self.ext('ScriptGenerator_spawn', obj.addr, self.mem.cstr(G_GEN_NAMES + 24 * index))
        return 0

    def n_monstersInTrigger(self, m, a):
        """0x147570 (s name): the sum of MonsterTrigger_count over MonsterTrigger objects."""
        total = 0
        for obj in self.find(a.s(0), 0x200):
            if obj.type_name == TYPE_MONSTER_TRIGGER:
                total = s32(total + self.ext('MonsterTrigger_count', obj.addr))
        return total

    def _scale(self, obj, a, first):
        self.ext('Creature_scaleStats', obj.addr, *[C.mul(a.f(first + k), F_0_01) for k in range(5)])

    def n_initScriptSetParams(self, m, a):
        """0x147640 (i x5): Creature_scaleStats on the selected creature, each / 100."""
        selected = self.obj_at(self.selected_obj)
        if selected is not None and selected.flags & OF_CREATURE:
            self._scale(selected, a, 0)
        return 0

    def n_setCreatureParams(self, m, a):
        """0x1476c0 (s name, i x5)."""
        for obj in self.find(a.s(0), 0x200):
            if obj.flags & OF_CREATURE:
                self._scale(obj, a, 1)
        return 0

    def _start_anim(self, state, anim, mode):
        if mode == -1:
            self.ext('anim_clear', state)
            self.ext('anim_push', state, anim(), 6)
            self.ext('anim_jumpTopToEnd', state)
            self.ext('anim_releaseCaches', state)
        else:
            self.ext('anim_start', state, anim(), mode & M32, F_0_3)

    def n_startNPCAnim(self, m, a):
        """0x1438d8 (s name, s lump, s anim, i mode): the animation state at +0x114 of
        every creature; mode -1 restarts it at its end, another mode blends over 0.3 s."""
        name = a.s(0)
        lump = a.s(1)
        anim = a.s(2)
        for obj in self.find(name, 0x200):
            if obj.flags & OF_CREATURE:
                self._start_anim(obj.addr + 0x114, lambda: self.ext('res_find', lump, anim) & M32, a[3])
        return 0

    def n_NPCAnimAtEnd(self, m, a):
        """0x143a4c (s name): bit 7 of +0x11a of the first object; no null check."""
        obj = self.need(self.find_first(a.s(0)), 'NPCAnimAtEnd')
        return (obj.u(0x11A, 2) >> 7) & 1

    def n_countLiveObjects(self, m, a):
        """0x146a10 (s name): objects of the name (at most 127) that are not dead creatures."""
        return sum(1 for obj in self.find(a.s(0), 0x80)
                   if obj.flags & (OF_CREATURE | OF_DEAD) != OF_CREATURE | OF_DEAD)

    # ---------------------------------------------------------------------------------
    # other objects, effects, camera
    # ---------------------------------------------------------------------------------
    def n_trigger(self, m, a):
        """0x142264 (s name, i arg): virtual slot 3 on up to 99 objects."""
        for obj in self.find(a.s(0), 100):
            self.virtual(obj, V_TRIGGER, a.u(1))
        return 0

    def n_autoPropSetState(self, m, a):
        """0x142320 (s name, i state): virtual slot 18 on objects with flag 0x10000000."""
        for obj in self.find(a.s(0), 100):
            if obj.flags & OF_AUTOPROP:
                self.virtual(obj, V_SET_STATE, a.u(1))
        return 0

    def n_autoPropGetState(self, m, a):
        """0x1423e0 (s name): +0x178 of the first object if it is an auto prop; no null
        check."""
        found = self.find(a.s(0), 100)
        obj = self.need(found[0] if found else None, 'autoPropGetState')
        return s32(obj.u(0x178, 4)) if obj.flags & OF_AUTOPROP else 0

    def n_startPropAnim(self, m, a):
        """0x143a8c (s name, s anim, i mode): the animation state at +0x54 of the first
        object; the lump name is the object's 'lump' property.  No null check."""
        obj = self.find_first(a.s(0))
        anim = a.s(1)
        obj = self.need(obj, 'startPropAnim')

        def resource():
            lump = O.props_find(obj.props, self.mem.cstr(S_PROP_LUMP_KEY))
            if lump is None:
                raise HostFault('startPropAnim: the object has no lump property; res_find gets a null name')
            return self.ext('res_find', bytes(lump), anim) & M32
        self._start_anim(obj.addr + 0x54, resource, a[2])
        return 0

    def n_stopPropAnim(self, m, a):
        """0x143bb8 (s name): +0x58 = 0; no null check."""
        self.need(self.find_first(a.s(0)), 'stopPropAnim').w(0x58, 1, 0)
        return 0

    def n_propAnimAtEnd(self, m, a):
        """0x143bf4 (s name): bit 7 of +0x5a; no null check."""
        return (self.need(self.find_first(a.s(0)), 'propAnimAtEnd').u(0x5A, 2) >> 7) & 1

    def n_deleteObjects(self, m, a):
        """0x146ff4 (s name): virtual slot 1 with 3 on up to 24 objects."""
        for obj in self.find(a.s(0), 0x19):
            self.virtual(obj, V_DESTROY, 3)
        return 0

    def n_setNoCollide(self, m, a):
        """0x146f58 (s name, i on): object flag bit 0 of the first object; no null check."""
        obj = self.need(self.find_first(a.s(0)), 'setNoCollide')
        obj.flags = obj.flags & ~OF_NOCOLLIDE & M32 if a[1] == 0 else obj.flags | OF_NOCOLLIDE
        return 0

    def n_objInPlayerTrig(self, m, a):
        """0x142ad4 (s name): 1 if the object is inside (virtual slot 17) any Trigger - up
        to 49 found by class - that has a player inside (+0x68 != -1)."""
        obj = self.find_first(a.s(0))
        if obj is not None:
            for trigger in self.ext('world_findObjectsByClass', TYPE_TRIGGER, 0x32):
                if s32(trigger.u(0x68, 4)) != -1 and self.virtual(trigger, V_CONTAINS, obj.addr) != 0:
                    return 1
        return 0

    def n_findDistance(self, m, a):
        """0x1478c8 (s a, s b): horizontal distance, 0 if either is missing."""
        name_a = a.s(0)
        name_b = a.s(1)
        first = self.find_first(name_a)
        second = self.find_first(name_b)
        if first is None or second is None:
            return 0
        dy = C.sub(first.pos[1], second.pos[1])
        dx = C.sub(first.pos[0], second.pos[0])
        return C.to_int(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))))

    def n_setContainerProps(self, m, a):
        """0x14799c (s name, i which, i value): AutoContainer objects, which == 1: bit 3 of
        +0x124 set when value is 0, cleared otherwise."""
        for obj in self.find(a.s(0), 0x200):
            if obj.type_name == TYPE_AUTO_CONTAINER and a[1] == 1:
                bits = obj.u(0x124, 4)
                obj.w(0x124, 4, bits | 8 if a[2] == 0 else bits & ~8 & M32)
        return 0

    def n_lightEffect(self, m, a):
        """0x143720 (ref pos[3], i scale, i x10): a 0xbc-byte LightEffect at the position
        read from three script cells.  Values 2..9 go in the eight float registers; values
        10 and 11, the constant 1.0 and scale / 100 go on the stack."""
        address = a[0]
        if m.get_addr(address) != 0:
            raise HostFault('lightEffect: position address refused by scr_getAddr')
        pos = tuple(C.from_int(m.cell(address + 4 * k)) for k in range(3))
        block = self.ext('pool_new', 0xBC) & M32
        if block != 0:
            self.ext('LightEffect_ctor', block, pos, 0, 0, *[a.f(2 + k) for k in range(8)],
                     a.f(10), a.f(11), F_1, C.mul(a.f(1), F_0_01))
        return 0

    def n_addExpandingPool(self, m, a):
        """0x143c34 (s object, i unused, i size): decal_add(size, position, 0, 10, 2); no
        null check."""
        obj = self.need(self.find_first(a.s(0)), 'addExpandingPool')
        self.ext('decal_add', tuple(obj.pos), 0, 10, 2, a.f(2))
        return 0

    def n_particleMorph(self, m, a):
        """0x1467ac (s from, s to): when the first object of each name is a creature, a
        0x5c-byte ParticleMorphEffect."""
        first = self.find(a.s(0), 0x200)
        second = self.find(a.s(1), 0x200)
        source = first[0] if first and first[0].flags & OF_CREATURE else None
        target = second[0] if second and second[0].flags & OF_CREATURE else None
        if source is not None and target is not None:
            block = self.ext('pool_new', 0x5C) & M32
            if block != 0:
                self.ext('ParticleMorphEffect_ctor', block, source.addr, target.addr)
        return 0

    @staticmethod
    def _particle_def(slot):
        if not 0 <= slot < 3:
            raise HostFault('particle slot %d: the handler reads past its table of three pointers' % slot)
        return PARTICLE_DEFS[slot]

    def n_setParticle(self, m, a):
        """0x146d94 (i slot, i x14): 0x18f118 with the slot's definition.  Values 1..7 in
        integer registers, 9..11 as floats, 8, 12, 13, 14 and a zero on the stack."""
        self.ext('particle_define', self._particle_def(a[0]), *[a.u(k) for k in range(1, 8)],
                 a.f(9), a.f(10), a.f(11), a.u(8), a.u(12), a.u(13), a.u(14), 0)
        return 0

    def n_addParticleOnObject(self, m, a):
        """0x146e20 (i slot, s object, i dx, i dy, i dz, i vx, i vy, i vz): particle_spawn
        at the object plus the offset, velocity = v / 1000; slot -1 means slot 0.  No null
        check."""
        velocity = (C.mul(a.f(5), F_0_001), C.mul(a.f(6), F_0_001), C.mul(a.f(7), F_0_001))
        offset = (a.f(2), a.f(3), a.f(4))
        obj = self.need(self.find_first(a.s(1)), 'addParticleOnObject')
        pos = tuple(C.add(offset[k], obj.pos[k]) for k in range(3))
        self.ext('particle_spawn', self._particle_def(0 if a[0] == -1 else a[0]), pos, velocity, F_0)
        return 0

    def n_shakeCamera(self, m, a):
        """0x146fc0 (i amount): unless the medal screen countdown 0x4f7114 runs."""
        if self.medal_ticks == 0:
            self.ext('camera_shake', 0, a.f(0))
        return 0

    def n_setFarClip(self, m, a):
        """0x144104 (i distance)."""
        self.ext('camera_setFarClip', a.f(0))
        return 0

    def n_setWaveDetail(self, m, a):
        """0x14176c (i on)."""
        self.mem.w32(G_WAVE_DETAIL, 1 if a[0] != 0 else 0)
        return 0

    # ---------------------------------------------------------------------------------
    # audio
    # ---------------------------------------------------------------------------------
    def n_sound(self, m, a):
        """0x1435e0 (s lump, s name): sound_playSample(1.0, 1.0, 0, resource, 0) when the
        resource exists."""
        lump = a.s(0)
        sample = self.ext('res_find', lump, a.s(1)) & M32
        if sample != 0:
            self.ext('sound_playSample', 0, sample, 0, F_1, F_1)
        return 0

    def n_soundSequence(self, m, a):
        """0x143684 (s lump, s name): sound_playOnObject(1.0, resource, 0) - also for a
        missing resource - and sound_setPlaysWhileFrozen on its handle."""
        lump = a.s(0)
        sequence = self.ext('res_find', lump, a.s(1)) & M32
        self.ext('sound_setPlaysWhileFrozen', self.ext('sound_playOnObject', sequence, 0, F_1) & M32)
        return 0

    def n_startMusic(self, m, a):
        """0x146b68 (s name)."""
        self.ext('music_playLevel', a.s(0), 3)
        return 0

    def n_startAudio(self, m, a):
        """0x146ba4 (s name)."""
        self.ext('stream_playLevel', 1, a.s(0), 2)
        return 0

    def n_endMusic(self, m, a):
        """0x146be4."""
        self.ext('stream_queueStop', 2)
        return 0

    # ---------------------------------------------------------------------------------
    # vehicles (no shipped script calls these)
    # ---------------------------------------------------------------------------------
    def n_putNPCInVehicle(self, m, a):
        """0x142bdc (s vehicle, s npc)."""
        vehicle_name = a.s(0)
        npc_name = a.s(1)
        vehicle = self.find_first(vehicle_name)
        if vehicle is not None:
            npc = self.find_first(npc_name)
            self.ext('Vehicle_attachNpcDriver', vehicle.addr, npc.addr if npc is not None else 0)
        return 0

    def n_putPlayersInVehicle(self, m, a):
        """0x142df4 (s vehicle): virtual slot 14 for the active player first (unless -1),
        then for every other player whose object is not dead (no null check)."""
        vehicle = self.find_first(a.s(0))
        if vehicle is not None:
            if self.active_player != -1:
                self.virtual(vehicle, V_INTERACT, self.active_player & M32)
            slot = 0
            while slot < self.num_players:
                if slot != self.active_player:
                    player = self.need(self.player_obj(slot), 'putPlayersInVehicle')
                    if not player.flags & OF_DEAD:
                        self.virtual(vehicle, V_INTERACT, slot)
                slot += 1
        return 0

    def n_entityRideVehicle(self, m, a):
        """0x142c78 (s entity, s vehicle, i x, i y, i z, i angle): the vehicle's virtual
        slot 19 turns the seat offset into a position and a facing; the entity is moved
        there (facing + angle) and relinked.  No null checks."""
        entity_name = a.s(0)
        vehicle = self.need(self.find_first(a.s(1)), 'entityRideVehicle')
        entity = self.need(self.find_first(entity_name), 'entityRideVehicle')
        pos, facing = self.virtual(vehicle, V_SEAT, (a.f(2), a.f(3), a.f(4)))
        entity.pos = list(pos)
        entity.angle = facing + a[5]
        self.ext('obj_updateGridCell', entity.addr)
        return 0

    def n_controlVehicle(self, m, a):
        """0x142d94 (s vehicle, i a, i b)."""
        vehicle = self.find_first(a.s(0))
        if vehicle is not None:
            vehicle.w(0x410, 4, a[1])
            vehicle.w(0x2F0, 4, a.f(2))
        return 0

    def n_holdVehicle(self, m, a):
        """0x142eec (s vehicle, i on)."""
        vehicle = self.find_first(a.s(0))
        if vehicle is not None:
            self.ext('Vehicle_setHold', vehicle.addr, a.u(1))
        return 0

    def _vehicle_of(self, slot):
        player = self.player_obj(slot)
        if player is None or player.flags & OF_DEAD:
            return 0
        return player.u(PLAYER_VEHICLE, 4)

    def n_getPlayerVPosition(self, m, a):
        """0x142f40: over the players in vehicles, keeps vehicle +0x34c whenever vehicle
        +0x90c exceeds the value kept so far; times 128."""
        best = F_0
        slot = 0
        while slot < self.num_players:
            vehicle = self._vehicle_of(slot)
            slot += 1
            if vehicle != 0 and C.lt(best, self.mem.u32(vehicle + 0x90C)):
                best = self.mem.u32(vehicle + 0x34C)
        return C.to_int(C.mul(best, F_128))

    def n_getVPosition(self, m, a):
        """0x1430cc (s vehicle): +0x90c times 128, 0 if not found."""
        vehicle = self.find_first(a.s(0))
        return C.to_int(C.mul(vehicle.u(0x90C, 4), F_128)) if vehicle is not None else 0

    def n_getPlayerVDir(self, m, a):
        """0x142fc8: for the first living player in a vehicle faster than 2.0 (+0x348)
        whose direction dot product decides: 1 when it is above 0, -1 when below 0.707;
        else the next player; 0 at the end."""
        index = 0
        while index < self.alive_count:
            vehicle = self._vehicle_of(self.alive(index))
            index += 1
            if vehicle != 0 and C.lt(F_2, self.mem.u32(vehicle + 0x348)):
                path = self.mem.u32(vehicle + 0x910)
                dot = F_0
                terms = [C.mul(self.mem.u32(vehicle + 0x468 + 4 * k) ^ 0x80000000, self.mem.u32(path + 0xC + 4 * k))
                         for k in range(3)]
                dot = C.add(C.add(terms[0], terms[1]), terms[2])
                if C.lt(F_0, dot):
                    return 1
                if C.lt(dot, F_0_707):
                    return -1
        return 0


NATIVE_NAMES = (
    'callScript', 'print', 'printVal', 'sound', 'soundSequence', 'lightEffect', 'simpleNewWorld', 'newWorld',
    'newWorldAlways', 'newWorldPost', 'activateMissionMenu', 'activateStore', 'storeRunning', 'getScaledTime',
    'setFarClip', 'startDialog', 'changeSwoop', 'startWithSwoopDone', 'dialogRunning', 'increaseEnemyRank',
    'charmMonster', 'rootMonster', 'unRootMonster', 'selectSetMonsterVal', 'setMonsterVal', 'selectSetCFlag',
    'setCFlag', 'selectSetOFlag', 'setOFlag', 'setWeaponType', 'setMonsterRange', 'killMonster', 'deleteMonster',
    'hideMonster', 'showMonster', 'moveMonster', 'followPlayer', 'stopFollowingPlayer', 'followPath',
    'selectFollowPath', 'stopFollowingPath', 'selectStopPath', 'friendly', 'unFriendly', 'startPropAnim',
    'stopPropAnim', 'propAnimAtEnd', 'startNPCAnim', 'NPCAnimAtEnd', 'addExpandingPool', 'playerHasItem',
    'onePlayerHasItem', 'removePlayerItem', 'givePlayerItem', 'giveOnePlayerItem', 'givePlayerRandom',
    'givePlayerExp', 'givePlayerGold', 'takePlayerGold', 'checkPlayerGold', 'checkPlayerMinGold',
    'playGotItemSound', 'setInfo', 'addHelpMessage', 'addQuest', 'removeQuest', 'hornOmen', 'planarSteel',
    'particleMorph', 'healPlayer', 'leaveGame', 'endGame', 'clearRecall', 'startMusic', 'startAudio', 'endMusic',
    'saveGame', 'saveEndConfig', 'saveDone', 'exitToMainMenu', 'reapEnemies', 'getv', 'getNumPlayers', 'setv',
    'addv', 'setpv', 'getpv', 'getRand', 'activePlayerIsDwarf', 'activePlayerIsElf', 'gamePaused',
    'pauseGameControl', 'levelLoading', 'setParticle', 'addParticleOnObject', 'setNoCollide', 'shakeCamera',
    'deleteObjects', 'hidePlayers', 'checkPlayerAlive', 'setBestActivePlayer', 'decayPlayerLights',
    'checkMonstersLeft', 'forceMutexRelease', 'addDeferedCall', 'cutScene', 'postAction', 'newWorldParameter',
    'putNPCInVehicle', 'putPlayersInVehicle', 'entityRideVehicle', 'controlVehicle', 'playersLoaded', 'holdVehicle',
    'getPlayerVPosition', 'getVPosition', 'getPlayerVDir', 'setupPlayerSel', 'startPlayerSel', 'playerSelRunning',
    'objInPlayerTrig', 'setEntrance', 'hudResetFadeScreen', 'hudFadeScreen', 'closestPlayerDist', 'hitPlayers',
    'zeroPlayerMana', 'showCompass', 'showBust', 'getMaxPlayerHP', 'getHitPoints', 'setHitPoints', 'saveCheckPoint',
    'loadCheckPoint', 'trigger', 'autoPropSetState', 'autoPropGetState', 'preloadResource', 'setSaveInhibit',
    'getSaveInhibit', 'countQuestItems', 'countPlayersAlive', 'countLiveObjects', 'networkMode', 'getManaUsed',
    'getHealthUsed', 'getLevelTimer', 'getEvil', 'setEvil', 'getMadeDecision', 'setMadeDecision', 'grantMission',
    'getMissionComplete', 'setMissionAvailable', 'getMissionAvailable', 'grantGold', 'grantSilver', 'grantBronze',
    'getMedal', 'generateMonster', 'monstersInTrigger', 'sin1000', 'cos1000', 'helpMessageActive',
    'addHelpMessageF', 'revealMap', 'showOnMap', 'initScriptSetParams', 'setCreatureParams', 'explodePotionsOnly',
    'runMedalSuccess', 'runMedalFail', 'setAlternateDeath', 'dropItem', 'selectDropItem', 'findDistance',
    'setContainerProps', 'setWaveDetail', 'demoRunning', 'removeAllItems', 'savePlayer', 'restorePlayer',
    'piercePlayerEar', 'playerAdjustStat', 'giveFullHealth', 'setPlayerFlag', 'getPlayerFlag', 'clearAllSkills',
    'isClericOrWizard', 'refillPlayerMana', 'removeAllWeapons',
)                                   # in table order: index k is the entry at 0x403370 + 8 k
NOT_MODELLED = tuple(name for name in NATIVE_NAMES if not hasattr(Game, 'n_' + name))


def _main(argv):
    """python3 tools/ref_natives.py list   - the table, with the handler docstrings."""
    if argv[:1] != ['list']:
        print(__doc__)
        return 2
    for index, name in enumerate(NATIVE_NAMES):
        method = getattr(Game, 'n_' + name, None)
        text = ' '.join((method.__doc__ or '').split()) if method else '(not modelled)'
        print('%3d %-20s %s' % (index, name, text[:110]))
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
