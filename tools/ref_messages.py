#!/usr/bin/env python3
"""ref_messages.py - reference model of the game-message handlers of Champions: Return to
Arms (SLUS_209.73, US v2.00) and of the inventory operations behind them.

A research tool, not game code.  Every method was written from the instruction sequence at
the address given in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_messages.py.  docs/spec/game-messages.md is the prose
version.  Standard library only; no game data is embedded (strings and tables the code
compares with are read through the memory the caller supplies, item definitions through
tools/ref_items.py).

What a game message is
    A menu on one machine never changes the game.  It queues {channel, length, bytes} with
    net_sendGameMsg 0x13db38; the bytes ride in that machine's input packet and every
    machine calls handler[channel](bytes, length) in the same lockstep frame, for each peer
    in slot order after that peer's pad was applied (docs/spec/net-wire.md section 10).
    The handlers below are therefore simulation code.

How the model sees the game
    The handlers follow pointers that arrive in the message (an item address, a stock
    record address, an object address), so the model works on a memory image, like
    tools/ref_player.py:

        mem     an object with load(addr, size) / store(addr, size, value), little endian
                (Memory below is one; the differential test wraps the interpreter's)
        tables  a tools/ref_items.py Tables object (item definitions; needed only by the
                equip test and by item values)

    Machine(mem, tables, callbacks).deliver(channel, payload) runs one handler.  payload is
    a bytes object: what the handler finds at its first argument.  The original copies only
    `length` bytes into a buffer on the net tick's stack, so a handler that reads past the
    length sees what the previous message left there; the caller decides what those bytes
    are by passing a payload longer than the message.

What is outside the model
    Everything a handler calls that another model owns, or that is presentation, is a
    callback named in EXTERNALS: derived statistics (player_recalcStats, player_recalcLoad -
    tools/ref_combat.py), animation, sound, HUD boxes, scripts and quest variables, object
    creation, the world query that places a dropped item, the weapon-swap helper
    (tools/ref_player.py), dialog and level change.  A callback is f(*args) -> result;
    callbacks is an object with get(name) -> function or None, and a missing name returns
    0.  Arguments are canonical: integers as unsigned 32-bit, floats as patterns, a
    position as a tuple of three patterns, a string as its address in mem or - when the
    handler built the text itself - as bytes.  The model records every callback it makes in
    .calls, every store in mem.log.

    No handler draws from the shared seed 0x404464 itself.  The draws of a message are the
    ones its callbacks make (world_findFreeSpot, the object constructors), in call order;
    game_sendCharacterToLobby reads the seed without advancing it.

Modelled here (run for real by the differential test)
    channels      net_registerMsgHandler 0x13da98, net_sendGameMsg 0x13db38
    inventory     invmsg_dispatch 0x1bfdb0, inventory_dropItem 0x1c4310, inventory_equipItem
                  0x1c27c0, inventory_unequipItem 0x1c2f20, inventory_unrefItem 0x1c3350,
                  inventory_removeItem 0x1c1cb0, inventory_giveItem 0x1c1868,
                  inventory_onJoinPanel 0x1c0360, inventory_onStatPoint 0x1c2548,
                  inventory_onSkillPoint 0x1c2648, game_sendCharacterToLobby 0x1eb5c8,
                  player_getSkillRank 0x1bf330, player_setSkillRank 0x1bf3a0,
                  player_getPassiveLevel 0x1bed48, player_raisePassiveLevel 0x1bedd0,
                  player_addSkillAbility 0x1d32e4, player_rebuildAbilities 0x1d34ac,
                  item_sameIdentityFields 0x108924, menu_resetListState 0x1d1380
    game ("HUD")  hud_onMsg 0x1d8ca0, hud_onQuickSlot 0x1de28c, hud_onAssignSpell 0x1de61c,
                  hud_onQuickCastWarn 0x1de340, net_maskLocalButtons 0x13e540,
                  recall_execute 0x18c230, the load-level body 0x18cb80
    shop          shop_onMsg 0x1c5d28, shop_buy 0x1d1240
    through tools/ref_items.py: inventory_checkEquipAllowed 0x1c4948, item_getValue 0x1024a8
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_items as RI                          # noqa: E402

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


def s64(x):
    x &= M64
    return x - (1 << 64) if x >> 63 else x


# ---------------------------------------------------------------------------------------
# Addresses.  (machine) marks what is not lockstep state; docs/spec/game-messages.md
# section 9 says what each one gates.
# ---------------------------------------------------------------------------------------
G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
G_NUM_PLAYERS = 0x4D8AE0
G_NETWORK_MODE = 0x402791               # s8
G_DIFFICULTY = 0x4F719C
G_PVP_MODE_B, G_MEDAL_MISSION = 0x4F7120, 0x4F713C
G_SIM_FRAME, G_RAND_SEED = 0x44FDCC, 0x404464
G_PADS, PAD_SIZE = 0x41BFD8, 0x58
G_SKILL_TABLE = 0x41B170
G_CLASS_SKILLS = 0x4EF538               # per class 0xa88 bytes: 48 entries of 0x38, u64 mask first
G_OLD_ABILITIES = 0x4F5CC8              # rows of 0x68 bytes, the layout of an ability record
G_LOCAL_MENU_OPEN = 0x41B69D            # s8 (machine)
G_ITEM_LIST_CELLS = 0x4EBBB0            # pointer (machine): this machine's item grid copies
G_ITEM_PANELS, PANEL_SIZE = 0x4F4040, 0x74      # (machine) inventory panels
G_PANEL_ROWS = 0x4F4240                 # (machine)
G_PANEL_LEVELUP = 0x4F65C8              # (machine) u8, per panel offline
G_JOIN_FLAG = 0x44FD7C                  # (machine) u8
G_PANEL_ANIM, PANEL_ANIM_SIZE = 0x866850, 0x108
G_MSG_HANDLERS = 0x5D1498               # 16 handler pointers
G_PEERS, PEER_SIZE = 0x5BF838, 0x44E0   # +0xc+0x24a0 message ring (0x2000), +0x44ac write position
G_INPUT_LOCK = 0x5D0BC8                 # per slot {frames, mask, 0}
G_INV_CHANNEL, G_SHOP_CHANNEL = 0x866D18, 0x86A6A0
G_GAME_CHANNEL, G_NULL_CHANNEL = 0x86AC40, 0x86AA60
G_MENU_LOCKOUT, G_PAUSED = 0x41B4FC, 0x41B4F4   # the first is (machine) by its other writers
G_RECALL_COUNTDOWN = 0x41B51D           # s8
G_PENDING_LEVEL, G_LEVEL_NAME = 0x41B6D0, 0x41B721
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_EXIT_COUNTDOWN = 0x4F694A             # s16
G_CHECKSUM_COUNT, G_CHECKSUM_PENDING = 0x86AAA8, 0x4F7138
G_CHECKSUM_RECEIVED, G_CHECKSUM_EXPECTED = 0x86AB58, 0x86AB38
G_CHECKSUM_FAILED, G_MEDAL_ACK = 0x4F7144, 0x4F7140
G_STREAM_FLAG, G_LOAD_FLAG = 0x44FA80, 0x44F208

H_CUTSCENE, H_VOICE, H_DIALOG, H_GAME = 0x198F64, 0x31F354, 0x22EE2C, 0x1D8CA0
H_NULL, H_INVENTORY, H_TEXT, H_SHOP = 0x1E01B0, 0x1BFDB0, 0x31D82C, 0x1C5D28
# start-up order of the registration calls at 0x323e50-0x323e80
REGISTRATION = (('cutscene', H_CUTSCENE, 0x83D1C8), ('voice', H_VOICE, 0x505B14),
                ('dialog', H_DIALOG, 0x8E2E94), ('game', H_GAME, G_GAME_CHANNEL),
                ('null', H_NULL, G_NULL_CHANNEL), ('inventory', H_INVENTORY, G_INV_CHANNEL),
                ('text', H_TEXT, 0x8E8ED8), ('shop', H_SHOP, G_SHOP_CHANNEL))

# record offsets
R_ACK_LEVEL, R_LEVEL, R_BASE_STATS = 0x58, 0x59, 0x78
R_HP, R_HP_MAX, R_MANA, R_MANA_MAX = 0xAC, 0xB0, 0xC0, 0xC4
R_GOLD, R_SKILL_POINTS, R_STAT_POINTS, R_LVLUP_OWNER, R_LVLUP_DONE = 0xE4, 0xE8, 0xEC, 0xED, 0xEE
R_PASSIVES, R_LOAD_LIMIT, R_ABILITY_MASK = 0xEF, 0x124, 0x128
R_BAGS, BAG_SIZE, R_BAG_COUNT, ITEM_SIZE = 0x130, 0x1208, 0x1330, 0x48
R_OBJECT, R_EQUIP, R_SET_WEAPON, R_SECOND_WEAPON = 0x43D8, 0x43F0, 0x4434, 0x443C
R_ABILITIES, ABILITY_SIZE = 0x4440, 0x68
R_ACTIVE_SET, R_QUICK_A, R_QUICK_B, R_WEAPON_CLASS = 0x4A7C, 0x4A84, 0x4A85, 0x4A86
R_SKILL_RANKS, R_MENU_COUNTDOWN, R_FIRST_RECALL, R_SECOND_EARRING = 0x4B08, 0x4BC8, 0x4C25, 0x4C26
GOLD_CAP = 99999999

# string constants (addresses only)
S_FX_LUMP, S_FX_LUMP_HUD, S_FX_LUMP_RECALL = 0x537D08, 0x53C3B8, 0x534368
S_SND_CANTDO, S_SND_STAT, S_SND_LEVELUP = 0x537F38, 0x537F20, 0x537D10
S_SND_ASSIGN, S_SND_RECALL = 0x53C858, 0x534370
S_NOWIELD_TABLE, S_NOWIELD_TITLE = 0x537FF0, 0x538018
S_HOOK_BOW, S_HOOK_WEAPON, S_VAR_BOW = 0x538028, 0x538048, 0x538038
S_STACK_STEM_DROP, S_STACK_STEM_SELL = 0x5385E0, 0x538660
S_RECALL_NAME, S_VAR_FIRST_RECALL, S_HINT_TITLE, S_HINT_BODY = 0x537DB8, 0x537DC8, 0x537DE0, 0x537DF0
S_UNIQUE_A, S_UNIQUE_B = 0x537E08, 0x537E10
S_NEWSTYLE_HUD, S_NEWSTYLE, S_TABLE_END = 0x53C7D0, 0x53B358, 0x53B368
S_TASK_MISSION = 0x53C280
S_LEFT_SPACE, S_LEFT_TEXT, S_QUICKCAST_WARN = 0x53C290, 0x53C298, 0x53C870
S_ERR_RECALL, S_ERR_RECALL_DEAD, S_ERR_RECALL_TARGET, S_ERR_RECALL_CHARGES = 0x534300, 0x534318, 0x534340, 0x534388
S_HUB, S_NONE, S_RECALL_NAME_2 = 0x534330, 0x534338, 0x534358
# equip / drop sounds by material flag: see sound_name()
SND_EQUIP = {'wood_large': 0x538060, 'wood_small': 0x538078, 'wood': 0x538090, 'chain': 0x5380A8,
             'shield': 0x5380C0, 'plate': 0x5380D8, 'metal_large': 0x5380F0, 'metal_small': 0x538108,
             'metal': 0x538120, 'leather': 0x538138, 'cloth': 0x538150, 'potion': 0x538168, 'other': 0x538180}
SND_DROP = {'wood_large': 0x537E18, 'wood_small': 0x537E30, 'wood': 0x537E48, 'chain': 0x538198,
            'shield': 0x5381B0, 'plate': 0x5381C8, 'metal_large': 0x537E78, 'metal_small': 0x537E90,
            'metal': 0x537EA8, 'leather': 0x537EC0, 'cloth': 0x537ED8, 'potion': 0x537EF0, 'other': 0x537F08}

ONE = 0x3F800000


class Ext:
    """One callback: address (0 for a virtual call), argument kinds, number of float
    arguments, result kind.  Kinds: i value, p address, s zero-terminated string, w
    zero-terminated 16-bit string, v pointer to three floats (passed as a tuple), o pointer
    the callee fills with three floats (not passed; the callback returns them), b the
    message buffer of net_sendGameMsg (passed as bytes)."""

    def __init__(self, addr, ints='', floats=0, ret='i', note=''):
        self.addr, self.ints, self.floats, self.ret, self.note = addr, ints, floats, ret, note


EXTERNALS = {
    # --- which machine this is
    'net_isLocalSlot': Ext(0x13E150, 'i', note='(slot) -> this machine owns the slot'),
    'net_getLocalPlayerSlot': Ext(0x13E1F0, 'i', note='(n) -> slot of this machine\'s n-th player'),
    'net_isSlotActive': Ext(0x13DD40, 'i', note='(slot) shared state'),
    'net_allPlayersState2': Ext(0x1EC5D8, '', note='lobby game with lobby-stored characters'),
    'lobby_sendCharacter': Ext(0x3278F0, 'ii', ret='n', note='(slot, isNew) uploads the record'),
    'net_disconnectPlayer': Ext(0x13DE68, 'ii', ret='n', note='(slot, 1)'),
    'net_closeLocalMenus': Ext(0x1EB000, 'i', ret='n'),
    # --- derived state owned by other models
    'player_recalcStats': Ext(0x1B6458, '', ret='n', note='all players (tools/ref_combat.py)'),
    'player_recalcLoad': Ext(0x1BEC10, 'i', ret='n', note='(slot)'),
    'player_countPotions': Ext(0x1BA5F8, 'ii', note='(slot, kind)'),
    'Player_weaponSwapInput': Ext(0x1BB718, 'ppi', note='(player, pad, 1) -> swapped (tools/ref_player.py)'),
    'Player_usePotion': Ext(0x1B9CB8, 'piiii', note='(player, kind, column, row, panel) (tools/ref_player.py)'),
    'Player_processDamage': Ext(0x1B2CC0, 'p', ret='n'),
    'Player_takeDamage_virtual': Ext(0, 'pii', 1, 'n', '(player + offset, 0, 0x20000040; 1000000.0) vtable slot 2'),
    'player_respawn': Ext(0x1BD040, 'iviii', ret='n', note='(slot, position, facing, 2, 8)'),
    'inventory_combineGems': Ext(0x1CEEB8, 'iiii', ret='n', note='(slot, a, b, c) workshop; not modelled'),
    # --- animation, sound, HUD, text
    'player_resetIdleAnim': Ext(0x1B2470, 'i', ret='n'),
    'inventory_selectIdleAnim': Ext(0x1C3F08, 'ipi', ret='n', note='(slot, panel animation state, 0)'),
    'inventory_refreshPanelModel': Ext(0x1C4E88, 'iii', ret='n', note='(slot, panel, 0)'),
    'res_find': Ext(0x17365C, 'ss', note='(lump, entry) -> entry'),
    'sound_playOnObject': Ext(0x214230, 'ip', 1, note='(entry, 0; 1.0)'),
    'text_lookup': Ext(0x173C84, 's', note='(key) -> 16-bit text'),
    'hud_showPlayerNotice': Ext(0x1D9954, 'ippi', ret='n', note='(slot, title, body, panel) owner only'),
    'hud_showHelpMessage': Ext(0x1D9830, 'ipp', ret='n', note='(slot, title, body)'),
    'hud_showMessage': Ext(0x1D92A0, 'wiii', ret='n', note='(text, frames, slot or -1, force)'),
    # --- scripts
    'script_runByName': Ext(0x1ED694, 's', ret='n'),
    'vars_set': Ext(0x1ED854, 'si', ret='n'),
    'vars_get': Ext(0x1ED778, 's'),
    # --- objects and the world
    'world_findFreeSpot': Ext(0x14ACF8, 'oviiii', ret='n', note='(out, centre, 0x30, 0xc, 0, 0): shared-seed draws'),
    'pool_new': Ext(0x14FDB8, 'i', note='(size) -> block or 0'),
    'ItemProp_ctor2': Ext(0x1590EC, 'pvpi', ret='n', note='(block, position, item, 0): one shared-seed draw'),
    'RecallEffect_ctor': Ext(0x1EE248, 'pv', ret='n', note='(block, position)'),
    'Savepoint_startSavedEffect': Ext(0x28CDC4, 'p', ret='n'),
    # --- dialog, menus, level change, audio
    'dialog_isOpen': Ext(0x22FBC0, ''),
    'task_isRunning': Ext(0x19E5E8, 's'),
    'pauseMenu_close': Ext(0x18DF90, '', ret='n'),
    'game_inNoSaveZone': Ext(0x1E7B78, ''),
    'audio_streamStatus': Ext(0x211B20, 'i'),
    'stream_queueStop': Ext(0x211338, 'i', ret='n'),
    'dialog_onMsg': Ext(H_DIALOG, 'pi', ret='n', note='channel 2 handler; not modelled'),
    'cutscene_onMsg': Ext(H_CUTSCENE, 'pi', ret='n', note='channel 0 handler; not modelled'),
    'voice_onMsg': Ext(H_VOICE, 'pi', ret='n', note='channel 1 handler; not modelled'),
    'text_onMsg': Ext(H_TEXT, 'pi', ret='n', note='channel 6 handler; not modelled'),
}


class Memory:
    """Sparse little-endian memory.  Unwritten bytes read from `under` (an object with
    load(addr, size)) or as zero.  Every store is appended to .log."""

    def __init__(self, under=None):
        self.bytes, self.under, self.log = {}, under, []

    def load(self, addr, size):
        get = self.bytes.get
        parts = [get(addr + i) for i in range(size)]
        if parts.count(None) == size:
            return self.under.load(addr, size) if self.under is not None else 0
        value = 0
        for i, b in enumerate(parts):
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


def sound_name(table, flags, slot_byte, subtype, short=False):
    """The material sound of an item, as the equip (0x1c2cf0), drop (0x1c43b0) and unequip
    (0x1c3148) code picks it from the item's flag word, its equipment slot and its weapon
    subtype.  short=True is the unequip variant, which has no size split."""
    if flags & 0x800000:
        if short:
            return table['wood']
        if ((subtype & 0xFF) - 1) & M32 < 4:
            return table['wood_large']
        return table['wood_small'] if flags & 0x20000000 else table['wood']
    if flags & 0x200000:
        return table['chain']
    if slot_byte == 3:
        return table['shield']
    if flags & 0x400000:
        return table['plate']
    if flags & 0x40000:
        if short:
            return table['metal']
        if ((subtype & 0xFF) - 1) & M32 < 3:
            return table['metal_large']
        return table['metal_small'] if flags & 0x20000000 else table['metal']
    if flags & 0x100000:
        return table['leather']
    if flags & 0x80000:
        return table['cloth']
    if flags & 0x1000000:
        return table['potion']
    return table['other']


class Machine:
    """One machine's copy of the game, as far as the message handlers see it."""

    def __init__(self, mem, tables=None, callbacks=None):
        self.mem, self.tables, self.callbacks = mem, tables, callbacks
        self.calls = []
        self.depth = 0

    # ---- memory ---------------------------------------------------------------------------
    def u8(self, a):
        return self.mem.load(a & M32, 1)

    def s8(self, a):
        return s8(self.mem.load(a & M32, 1))

    def u16(self, a):
        return self.mem.load(a & M32, 2)

    def s16(self, a):
        return s16(self.mem.load(a & M32, 2))

    def u32(self, a):
        return self.mem.load(a & M32, 4)

    def s32(self, a):
        return s32(self.mem.load(a & M32, 4))

    def u64(self, a):
        return self.mem.load(a & M32, 8)

    def w8(self, a, v):
        self.mem.store(a & M32, 1, v)

    def w16(self, a, v):
        self.mem.store(a & M32, 2, v)

    def w32(self, a, v):
        self.mem.store(a & M32, 4, v)

    def w64(self, a, v):
        self.mem.store(a & M32, 8, v)

    def copy(self, dst, src, size):
        for i in range(0, size, 8):
            self.w64(dst + i, self.u64(src + i))

    def cstr(self, a, limit=4096):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(a + len(out))
            if b == 0:
                break
            out.append(b)
        return bytes(out)

    def wstr(self, a, limit=4096):
        """A zero-terminated string of 16-bit characters, as bytes."""
        out = bytearray()
        while len(out) < limit:
            c = self.u16(a + len(out))
            if c == 0:
                break
            out += bytes((c & 0xFF, c >> 8))
        return bytes(out)

    def vec(self, a):
        return (self.u32(a), self.u32(a + 4), self.u32(a + 8))

    def rec(self, slot):
        return (G_PLAYERS + s32(slot) * REC_SIZE) & M32

    def call(self, name, *args):
        self.calls.append((name, args))
        f = self.callbacks.get(name) if self.callbacks is not None else None
        return f(*args) if f is not None else 0

    def sound(self, lump, entry):
        """res_find + sound_playOnObject(entry, 0; 1.0), the pair every handler uses."""
        self.call('sound_playOnObject', self.call('res_find', lump, entry), 0, ONE)

    # =======================================================================================
    # Channels
    # =======================================================================================
    def register_handler(self, handler):
        """net_registerMsgHandler 0x13da98: the index of `handler` in the 16-entry table, or
        of the first free entry, which it takes.  With all 16 in use the entry after the
        table is written."""
        for i in range(16):
            if self.u32(G_MSG_HANDLERS + 4 * i) == handler:
                return i
        i = 0
        while i < 16 and self.u32(G_MSG_HANDLERS + 4 * i) != 0:
            i += 1
        self.w32(G_MSG_HANDLERS + 4 * i, handler)
        return i

    def register_all(self):
        """The seven registration calls of start-up, in order; returns {family: id}."""
        ids = {}
        for family, handler, where in REGISTRATION:
            ids[family] = self.register_handler(handler)
            self.w32(where, ids[family])
        return ids

    def send(self, channel, data):
        """net_sendGameMsg 0x13db38.  Offline (g_networkMode 0) the handler runs at once on
        the sender's buffer.  In a net game {channel, length, bytes} goes into the message
        ring of this machine's first local player."""
        channel, n = s32(channel), len(data)
        if self.s8(G_NETWORK_MODE) == 0:
            self.deliver(channel, bytes(data) + bytes(16))
            return
        peer = G_PEERS + s32(self.call('net_getLocalPlayerSlot', 0)) * PEER_SIZE
        ring = peer + 0xC + 0x24A0
        pos = self.u32(peer + 0x44AC)
        self.w8(ring + (pos & 0x1FFF), channel)
        self.w8(ring + ((pos + 1) & 0x1FFF), n)
        for i in range(n):
            self.w8(ring + ((pos + i + 2) & 0x1FFF), data[i])
        self.w32(peer + 0x44AC, (pos + n + 2) & 0x1FFF)

    def deliver(self, channel, payload):
        """handler[channel](payload, n) as the tick calls it (0x13ad24).  The id is not
        range-checked by the original; here an id outside the table is an error."""
        handler = self.u32(G_MSG_HANDLERS + 4 * (channel & M32))
        payload = bytes(payload)
        if handler == H_INVENTORY:
            self.inv_dispatch(payload)
        elif handler == H_GAME:
            self.hud_on_msg(payload)
        elif handler == H_SHOP:
            self.shop_on_msg(payload)
        elif handler == H_NULL:
            pass                                    # 0x1e01b0: an empty function
        elif handler in (H_DIALOG, H_CUTSCENE, H_VOICE, H_TEXT):
            name = {H_DIALOG: 'dialog_onMsg', H_CUTSCENE: 'cutscene_onMsg', H_VOICE: 'voice_onMsg',
                    H_TEXT: 'text_onMsg'}[handler]
            self.call(name, payload, len(payload))
        else:
            raise ValueError('no handler for channel %d' % channel)

    # =======================================================================================
    # Inventory channel
    # =======================================================================================
    def inv_dispatch(self, p):
        """invmsg_dispatch 0x1bfdb0 (jump table 0x537cc0, types 0-10; a type byte of 11 or
        more, or negative, does nothing).  Multi-byte fields are little endian at fixed
        offsets; every one-byte field is sign-extended."""
        p = bytes(p) + bytes(max(0, 16 - len(p)))
        kind = s8(p[0])
        b = lambda i: s8(p[i])
        h = lambda i: s16(p[i] | p[i + 1] << 8)
        w = lambda i: p[i] | p[i + 1] << 8 | p[i + 2] << 16 | p[i + 3] << 24
        if kind == 0:
            self.drop_item(b(1), w(4), b(10), h(2), h(8), b(11), b(12))
            self.send_character_to_lobby(b(1))
        elif kind == 1:
            self.equip_item(h(2), w(4), b(1))
        elif kind == 2:
            self.unequip_item(h(2), w(4))
        elif kind == 4:
            self.on_join_panel(b(1), b(2), b(3))
        elif kind == 5:
            self.w8(self.rec(b(1)) + R_WEAPON_CLASS, p[2])
            self.call('player_resetIdleAnim', b(1) & M32)
        elif kind == 6:
            self.on_stat_point(b(1), h(2))
        elif kind == 7:
            self.on_skill_point(b(1), b(2), w(4))
        elif kind == 8:
            self.call('inventory_combineGems', b(1) & M32, w(4), w(8), w(12))
        elif kind == 9:
            self.w8(self.rec(b(1)) + R_ACK_LEVEL, p[2])
        elif kind == 10:
            player = self.u32(self.rec(b(1)) + R_OBJECT)
            self.call('Player_usePotion', player, h(2) & M32, h(4) & M32, h(6) & M32, h(8) & M32)
        # 3: an empty case

    def send_character_to_lobby(self, slot):
        """game_sendCharacterToLobby 0x1eb5c8, called after every drop message with the
        message's slot byte.  Uploads a character to the lobby from one machine: reads the
        frame counter (or, for slot -1, the shared seed and this machine's slot) to pick
        which machine does it.  Changes no game state."""
        if self.call('net_allPlayersState2') == 0:
            return
        if self.u32(G_PVP_MODE_B) != 0 or self.u32(G_MEDAL_MISSION) != 0:
            return
        active = []
        i = 0
        while i < self.s32(G_NUM_PLAYERS):
            if self.call('net_isSlotActive', i):
                active.append(i)
            i += 1
        if not active:
            return
        if slot == -1:
            local = self.call('net_getLocalPlayerSlot', 0)
            pick = ((self.u32(G_RAND_SEED) + local) & M32) % len(active)        # divu
            self.call('lobby_sendCharacter', active[pick], 0)
            return
        frame = self.s32(G_SIM_FRAME)
        if frame < 0:
            raise ValueError('negative frame counter: the original indexes below its array')
        if s32(active[frame % len(active)]) == s32(self.call('net_getLocalPlayerSlot', 0)):
            self.call('lobby_sendCharacter', slot & M32, 0)

    # ---- item helpers -------------------------------------------------------------------------
    def same_identity(self, a, b):
        """item_sameIdentityFields 0x108924: b has a definition, and the 64-bit flags, the
        definition pointer and the 32-bit word at +0x20 agree."""
        if self.u32(b) == 0:
            return False
        return (self.u64(a + 8) == self.u64(b + 8) and self.u32(a) == self.u32(b)
                and self.u32(a + 0x20) == self.u32(b + 0x20))

    def item_object(self, item):
        data = bytes(self.u8(item + i) for i in range(ITEM_SIZE))
        return RI.Item.unpack(self.tables, data)

    def check_equip_allowed(self, slot, item):
        """inventory_checkEquipAllowed 0x1c4948 through tools/ref_items.py."""
        R = self.rec(slot)
        ranks = {}
        a = R + R_SKILL_RANKS
        while self.s16(a) != -1:
            ranks.setdefault(self.s16(a), self.s16(a + 2))
            a += 4
        player = RI.Player(self.s32(R + 0x50), self.s8(R + R_ACK_LEVEL), self.s32(R + 0x90),
                           self.s32(R + 0x94), self.s32(R + 0x98), self.s32(R + 0x9C), ranks)
        return RI.equip_restriction(self.tables, player, self.item_object(item))

    def item_value(self, item):
        """item_getValue 0x1024a8 through tools/ref_items.py."""
        return RI.item_value(self.tables, self.item_object(item))

    def skill_rank(self, slot, skill_id):
        """player_getSkillRank 0x1bf330: {s16 id, s16 rank} pairs at record +0x4b08, id -1
        ends the list; 0 when the id is not there."""
        a = self.rec(slot) + R_SKILL_RANKS
        while self.s16(a) != -1:
            if self.s16(a) == s16(skill_id):
                return self.s16(a + 2)
            a += 4
        return 0

    def set_skill_rank(self, slot, skill_id, rank):
        """player_setSkillRank 0x1bf3a0: overwrite the rank of the id, or append the pair
        where the -1 was.  It writes no new terminator: the list ends only because the
        record was filled with -1 beforehand."""
        a = self.rec(slot) + R_SKILL_RANKS
        while self.s16(a) != -1:
            if self.s16(a) == s32(skill_id):
                self.w16(a + 2, rank)
                return
            a += 4
        self.w16(a, skill_id)
        self.w16(a + 2, rank)

    def passive_level(self, slot, mask):
        """player_getPassiveLevel 0x1bed48: the level byte (record +0xef + n) of the class
        passive whose 64-bit mask equals `mask`; a negative byte reads as 0; slots above 4
        (unsigned) read as 0."""
        if (slot & M64) > 4:
            return 0
        R = self.rec(slot)
        table = G_CLASS_SKILLS + self.s32(R + 0x50) * 0xA88
        for n in range(0x30):
            if self.u64(table + n * 0x38) == (mask & M64):
                level = self.s8(R + R_PASSIVES + n)
                return 0 if level < 0 else level
        return 0

    def raise_passive_level(self, slot, mask, level):
        """player_raisePassiveLevel 0x1bedd0: store `level` in the passive's byte when it is
        higher than what is there."""
        R = self.rec(slot)
        table = G_CLASS_SKILLS + self.s32(R + 0x50) * 0xA88
        for n in range(0x30):
            if self.u64(table + n * 0x38) == (mask & M64):
                if self.s8(R + R_PASSIVES + n) < s32(level):
                    self.w8(R + R_PASSIVES + n, level)
                return

    def rebuild_abilities(self, mask, slot, index):
        """player_rebuildAbilities 0x1d34ac (mask, slot, ability index or -1).  Looks `mask`
        up in the table of old-style abilities 0x4f5cc8 (rows end at the name "END") and
        copies the row into the ability record; three masks are plain bonuses.  With index
        -1 a record is chosen: nothing when the mask is already in record +0x128, else the
        first of the 15 records whose id is -1."""
        mask &= M64
        R = self.rec(slot)
        index = s32(index)
        if index == -1:
            owned = self.u64(R + R_ABILITY_MASK) & mask
            if not owned and self.s16(R + R_ABILITIES + 0x20) == -1:
                index = 0
            else:
                i = 1
                while i < 15:
                    if not owned and self.s16(R + R_ABILITIES + i * ABILITY_SIZE + 0x20) == -1:
                        index = i
                        break
                    i += 1
        if index == -1:
            return
        rec = R + R_ABILITIES + index * ABILITY_SIZE
        row = G_OLD_ABILITIES
        end = self.cstr(S_TABLE_END)
        while self.cstr(row) != end:
            if mask == self.u64(row + 0x48):
                if self.s16(row + 0x20) != 0x1D:
                    name = self.cstr(row) + b'\0'
                    for i, c in enumerate(name):
                        self.w8(rec + i, c)
                    self.w16(rec + 0x20, self.u16(row + 0x20))
                    self.w16(rec + 0x22, self.u16(row + 0x22))
                    self.w8(rec + 0x24, self.u8(row + 0x24))
                    self.w8(rec + 0x25, self.u8(row + 0x25))
                    self.w16(rec + 0x26, self.u16(row + 0x26))
                    self.w16(rec + 0x28, self.u16(row + 0x28))
                    self.w32(rec + 0x2C, self.u32(row + 0x2C))
                    for k in range(8):
                        self.w16(rec + 0x30 + 2 * k, self.u16(row + 0x30 + 2 * k))
                    self.w32(rec + 0x40, self.u32(row + 0x40))
                    self.w64(rec + 0x48, self.u64(row + 0x48))
                    for k in range(5):
                        self.w32(rec + 0x50 + 4 * k, self.u32(row + 0x50 + 4 * k))
                if mask == 0x40:
                    self.w32(R + R_LOAD_LIMIT, C.add(self.u32(R + R_LOAD_LIMIT), 0x41700000))
                elif mask == 0x80:
                    hp = C.add(self.u32(R + R_HP), 0x40400000)
                    top = C.add(self.u32(R + R_HP_MAX), 0x40400000)
                    self.w32(R + R_HP_MAX, top)
                    self.w32(R + R_HP, hp)
                    if C.lt(top, hp):
                        self.w32(R + R_HP, top)
                elif mask == 0x100:
                    self.w32(R + R_MANA_MAX, C.add(self.u32(R + R_MANA_MAX), 0x40A00000))
                    self.w32(R + R_MANA, C.add(self.u32(R + R_MANA), 0x40A00000))
                    if C.lt(self.u32(R + R_MANA_MAX), self.u32(R + R_MANA)):
                        self.w32(R + R_MANA, self.u32(R + R_MANA_MAX))
                self.w64(R + R_ABILITY_MASK, self.u64(R + R_ABILITY_MASK) | mask)
                return
            row += ABILITY_SIZE

    def add_skill_ability(self, skill_id, slot):
        """player_addSkillAbility 0x1d32e4: give a skill whose kind (skill object +8) is not
        3 an ability record - the first free one of the 15, unless a record already holds
        the id under the marker name - zeroed, named with the marker, level byte 1, kind
        copied; and make the skill's rank at least 1."""
        skill_id = s32(skill_id)
        R = self.rec(slot)
        skill = self.u32(G_SKILL_TABLE + skill_id * 4)
        if self.u32(skill + 8) == 3:
            return
        free = -1
        for i in range(15):
            if self.s16(R + R_ABILITIES + i * ABILITY_SIZE + 0x20) == -1:
                free = i
                break
        marker = self.cstr(S_NEWSTYLE)
        for i in range(15):
            a = R + R_ABILITIES + i * ABILITY_SIZE
            if self.s16(a + 0x20) == skill_id and self.cstr(a) == marker:
                free = -1
        if free == -1:
            return
        rec = R + R_ABILITIES + free * ABILITY_SIZE
        for i in range(ABILITY_SIZE):
            self.w8(rec + i, 0)
        self.w8(rec + 8, self.u8(S_NEWSTYLE + 8))
        self.w64(rec, self.u64(S_NEWSTYLE))
        self.w16(rec + 0x20, skill_id)
        self.w8(rec + 0x24, 1)
        self.w8(rec + 0x25, self.u8(skill + 8))
        rank = self.skill_rank(slot, skill_id)
        self.set_skill_rank(slot, skill_id, rank if rank > 1 else 1)

    # ---- the grid copies of this machine's inventory screen --------------------------------
    def grid(self, panel, bag):
        """Address of one 9 x 75 grid of 0x48-byte item copies (machine): panel * 0x23988 +
        bag * 0xbdd8 from the pointer at 0x4ebbb0; a cell is column * 0x1518 + row * 0x48."""
        return (s32(panel) * 0x23988 + s32(bag) * 0xBDD8 + self.u32(G_ITEM_LIST_CELLS)) & M32

    # ---- inventory operations -----------------------------------------------------------------
    def remove_item(self, slot, index, bag, panel):
        """inventory_removeItem 0x1c1cb0 (slot, index, bag, panel): take one record out of a
        bag.  Clears the equipment pointer that names it, closes the gap, repoints every
        equipment and weapon pointer at a moved record, renumbers the stamps at +0x22, and
        lowers the count.  Nothing is range-checked."""
        R = self.rec(slot)
        index, bag = s32(index), s32(bag)
        base = (R + R_BAGS + bag * BAG_SIZE) & M32
        count_at = (R + R_BAG_COUNT + bag * BAG_SIZE) & M32
        item = (base + index * ITEM_SIZE) & M32
        es = self.s8(self.u32(item) + 0x1C)
        if (es - 5) & M32 < 2:
            if item == self.u32(R + R_EQUIP + 5 * 4):
                self.w32(R + R_EQUIP + 5 * 4, 0)
            elif item == self.u32(R + R_EQUIP + 6 * 4):
                self.w32(R + R_EQUIP + 6 * 4, 0)
        elif (es - 14) & M32 < 2:
            if item == self.u32(R + R_EQUIP + 14 * 4):
                self.w32(R + R_EQUIP + 14 * 4, 0)
            elif item == self.u32(R + R_EQUIP + 15 * 4):
                self.w32(R + R_EQUIP + 15 * 4, 0)
        elif item == self.u32(R + R_EQUIP + es * 4):
            self.w32(R + R_EQUIP + es * 4, 0)
        if self.u32(R + R_SET_WEAPON + 4 * self.s8(R + R_ACTIVE_SET)) == item:
            self.w8(R + R_WEAPON_CLASS, 5)
            self.call('player_resetIdleAnim', slot & M32)
        if self.u32(R + R_SET_WEAPON) == item:
            self.w32(R + R_SET_WEAPON, 0)
        elif self.u32(R + R_SET_WEAPON + 4) == item:
            self.w32(R + R_SET_WEAPON + 4, 0)
        if index < self.s32(count_at) - 1:
            dst, i = item, index
            while True:
                src = dst + ITEM_SIZE
                self.copy(dst, src, ITEM_SIZE)
                for k in range(17):
                    if self.u32(R + R_EQUIP + 4 * k) == src:
                        self.w32(R + R_EQUIP + 4 * k, dst)
                for k in range(2):
                    if self.u32(R + R_SET_WEAPON + 4 * k) == src:
                        self.w32(R + R_SET_WEAPON + 4 * k, dst)
                    if self.u32(R + R_SECOND_WEAPON) == src:
                        self.w32(R + R_SECOND_WEAPON, dst)
                i += 1
                self.w32(src, 0)
                dst = src
                if not i < self.s32(count_at) - 1:
                    break
        # this machine's inventory screen: refresh the bag index stamped in its grid copies
        if self.call('net_isLocalSlot', slot & M32) and self.s8(G_LOCAL_MENU_OPEN) != 0 \
                and self.u32(G_ITEM_LIST_CELLS) != 0:
            grid = self.grid(panel, bag)
            for row in range(75):
                for col in range(9):
                    cell = grid + col * 0x1518 + row * ITEM_SIZE
                    if self.u32(cell) != 0:
                        for k in range(64):
                            if self.same_identity(cell, base + k * ITEM_SIZE):
                                self.w16(cell + 0x22, k)
        count = self.s32(count_at)
        last = count - 1
        if index < last:
            for i in range(index, last):
                a = base + i * ITEM_SIZE + 0x22
                self.w16(a, self.u16(a) - 1)
            index = last
        for i in range(index, 0x40):
            self.w32(base + i * ITEM_SIZE, 0)
        self.w32(count_at, count - 1)
        self.call('player_recalcStats')

    def give_item(self, slot, src, announce):
        """inventory_giveItem 0x1c1868 (slot, item record, flag) -> index in the bag or -1.
        The bag is the definition's category byte.  A stackable item (flag bit 8) is added
        to the first record that agrees in definition, flags, prefix and suffix; otherwise
        the record is copied to position `count`, which must be empty, and stamped with its
        index.  Two named items can be held only once."""
        R = self.rec(slot)
        definition = self.u32(src)
        bag = self.s8(definition + 0x1D)
        base = (R + R_BAGS + bag * BAG_SIZE) & M32
        count_at = (R + R_BAG_COUNT + bag * BAG_SIZE) & M32
        net = self.s8(G_NETWORK_MODE)
        had = False
        if net == 0:
            for i in range(max(0, self.s32(G_NUM_PLAYERS))):
                if self.s8(self.rec(i) + R_FIRST_RECALL) == 1:
                    had = True
        else:
            had = self.s8(R + R_FIRST_RECALL) == 1
        flags = self.u64(src + 8)
        name = self.cstr(self.u32(definition))
        if flags & 0x100:
            for i in range(64):
                it = base + i * ITEM_SIZE
                if self.u32(it) == definition and self.u64(it + 8) == flags \
                        and self.u8(it + 0x20) == self.u8(src + 0x20) and self.u8(it + 0x21) == self.u8(src + 0x21):
                    if self.s32(G_DIFFICULTY) == 1 and not had and s32(announce) != 0 \
                            and name == self.cstr(S_RECALL_NAME) and self.call('vars_get', S_VAR_FIRST_RECALL) == 0 \
                            and net == 0:
                        self.first_recall_hint(slot, R)
                    self.w16(it + 4, self.u16(it + 4) + self.u16(src + 4))
                    self.call('player_recalcLoad', slot & M32)
                    self.call('player_countPotions', slot & M32, 0)
                    self.call('player_countPotions', slot & M32, 1)
                    self.call('player_recalcStats')
                    return i
        if name == self.cstr(S_UNIQUE_A) or name == self.cstr(S_UNIQUE_B):
            i = 0
            while i < self.s32(count_at):
                other = self.u32(base + i * ITEM_SIZE)
                if other != 0 and self.cstr(self.u32(other)) == name:
                    return -1
                i += 1
        count = self.s32(count_at)
        dst = (base + count * ITEM_SIZE) & M32
        if self.u32(dst) != 0:
            return -1
        self.copy(dst, src, ITEM_SIZE)
        if s32(announce) != 0 and name == self.cstr(S_RECALL_NAME) \
                and self.call('vars_get', S_VAR_FIRST_RECALL) == 0 and net == 0 and not had:
            self.first_recall_hint(slot, R)
        self.call('player_countPotions', slot & M32, 0)
        self.call('player_countPotions', slot & M32, 1)
        count = self.s32(count_at)
        self.w16(base + count * ITEM_SIZE + 0x22, count)
        self.call('player_recalcStats')
        count = self.s32(count_at)
        self.w32(count_at, count + 1)
        return count

    def first_recall_hint(self, slot, R):
        self.w8(R + R_FIRST_RECALL, 1)
        self.call('vars_set', S_VAR_FIRST_RECALL, 1)
        title = self.call('text_lookup', S_HINT_TITLE)
        body = self.call('text_lookup', S_HINT_BODY)
        self.call('hud_showHelpMessage', slot & M32, title, body)

    def unref_item(self, slot, item):
        """inventory_unrefItem 0x1c3350 (dual wield).  If `item` is the primary weapon of
        set 0, the second weapon is promoted: this machine SENDS inventory message 1 for it
        from inside the handler.  If it is the second weapon, that pointer and equipment
        slot 1 are cleared and the weapon class becomes 0."""
        R = self.rec(slot)
        if item == self.u32(R + R_SET_WEAPON):
            second = self.u32(R + R_SECOND_WEAPON)
            self.w32(R + R_SET_WEAPON, 0)
            self.w32(R + R_EQUIP, 0)
            msg = bytes((1, 0, slot & 0xFF, (slot >> 8) & 0xFF)) + second.to_bytes(4, 'little')
            self.send(self.u32(G_INV_CHANNEL), msg)
            self.w32(R + R_EQUIP + 4, 0)
            self.w32(R + R_SECOND_WEAPON, 0)
        elif item == self.u32(R + R_SECOND_WEAPON):
            self.w8(R + R_WEAPON_CLASS, 0)
            self.w32(R + R_SECOND_WEAPON, 0)
            self.w32(R + R_EQUIP + 4, 0)
            self.call('player_resetIdleAnim', slot & M32)
            self.call('inventory_selectIdleAnim', slot & M32, (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32, 0)

    def drop_item(self, slot, index, bag, column, row, panel, mode):
        """inventory_dropItem 0x1c4310 (slot, index, bag, column, row, panel, mode): inventory
        message 0 and the tail of shop message 1.  mode 0 drops to the ground, 1 sells (no
        object), 2 or more is silent (potion use).  Takes 1 off the stack - up to 20 for
        ammunition and thrown weapons - and removes the record when nothing is left.  An
        empty cell ends the handler at once; nothing else is checked."""
        R = self.rec(slot)
        item = (R + R_BAGS + s32(index) * ITEM_SIZE + bag * BAG_SIZE) & M32
        if self.u32(item) == 0:
            return
        player = self.u32(R + R_OBJECT)
        self.w8(player + 0x47A, 0)
        definition = self.u32(item)
        if mode < 2:
            entry = sound_name(SND_DROP, self.u64(item + 8), self.s8(definition + 0x1C), self.u8(definition + 0x1E))
            if self.call('net_isLocalSlot', slot & M32):
                self.sound(S_FX_LUMP, entry)
        if self.s8(R + R_WEAPON_CLASS) == 7:
            self.unref_item(slot, item)
        if self.u32(R + R_SET_WEAPON + 4 * self.s8(R + R_ACTIVE_SET)) == item:
            self.w8(R + R_WEAPON_CLASS, 5)
            self.call('player_resetIdleAnim', slot & M32)
        definition = self.u32(item)
        count = self.s16(item + 4)
        if self.s8(definition + 0x1C) == 8 or self.cstr(S_STACK_STEM_DROP) in self.cstr(self.u32(definition)) \
                or self.u64(definition + 0x28) & 0x1C0000000000:
            taken = count if count < 20 else 20
        else:
            taken = 1
        self.w16(item + 4, count - taken)
        # this machine's inventory screen keeps copies of the records: adjust them (machine)
        if self.call('net_isLocalSlot', slot & M32) and self.u32(G_ITEM_LIST_CELLS) != 0:
            grid = self.grid(panel, self.s8(self.u32(item) + 0x1D))
            for r in range(75):
                for c in range(9):
                    cell = grid + c * 0x1518 + r * ITEM_SIZE
                    if self.same_identity(cell, item):
                        self.w16(cell + 4, self.u16(cell + 4) - taken)
        if mode == 0:
            centre = self.vec(player + 0x10)
            spot = self.call('world_findFreeSpot', centre, 0x30, 0xC, 0, 0)
            block = self.call('pool_new', 400)
            if block:
                self.call('ItemProp_ctor2', block, tuple(spot), item, 0)
                self.w16(block + 0x14C, taken)
        if self.s16(item + 4) < 1:
            category = self.s8(self.u32(item) + 0x1D)
            if self.call('net_isLocalSlot', slot & M32) and self.u32(G_ITEM_LIST_CELLS) != 0:
                grid = self.grid(panel, category)
                for r in range(75):
                    for c in range(9):
                        if c == s32(column) and r == s32(row):
                            continue
                        cell = grid + c * 0x1518 + r * ITEM_SIZE
                        if self.same_identity(cell, item):
                            self.w32(cell, 0)
                self.w32(grid + s32(row) * ITEM_SIZE + s32(column) * 0x1518, 0)
            self.remove_item(slot, index, category, panel)
            self.call('inventory_selectIdleAnim', slot & M32, (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32, 0)
        self.call('player_recalcLoad', slot & M32)
        self.call('player_recalcStats')

    def equip_item(self, slot, item, quiet):
        """inventory_equipItem 0x1c27c0 (slot, item address, quiet): inventory message 1.
        The address is not checked against the bags: only a zero definition pointer stops
        the handler.  See docs/spec/game-messages.md section 5.3 for the rules."""
        self.depth += 1
        try:
            self._equip_item(slot, item & M32, quiet)
        finally:
            self.depth -= 1

    def _equip_item(self, slot, item, quiet):
        R = self.rec(slot)
        if self.u32(item) == 0:
            return
        reason = self.check_equip_allowed(slot, item)
        if reason != 0:
            if self.call('net_isLocalSlot', slot & M32):
                self.sound(S_FX_LUMP, S_SND_CANTDO)
            panel = 0
            if self.s32(G_ITEM_PANELS + 0x38) != s32(slot):                 # (machine)
                panel = int(self.s32(G_ITEM_PANELS + PANEL_SIZE + 0x38) == s32(slot))
            title = self.call('text_lookup', S_NOWIELD_TITLE)
            body = self.call('text_lookup', self.u32(S_NOWIELD_TABLE + 4 * reason))
            self.call('hud_showPlayerNotice', slot & M32, title, body, panel)
            return
        definition = self.u32(item)
        es = self.s8(definition + 0x1C)
        if es == 0x10:
            return
        new_set = -1
        if self.s8(definition + 0x1D) == 0 and es != 8:
            if self.s8(definition + 0x1E) in (4, 6):                        # bow or thrown: set 1
                new_set = 1
                self.call('script_runByName', S_HOOK_BOW)
                self.call('vars_set', S_VAR_BOW, 1)
            else:
                new_set = 0
                self.call('script_runByName', S_HOOK_WEAPON)
            es = self.s8(self.u32(item) + 0x1C)
        if es == 3 and self.s8(R + R_ACTIVE_SET) == 1 and self.u32(R + R_SET_WEAPON + 4) != 0 \
                and self.s8(R + R_WEAPON_CLASS) != 6:
            new_set = 0                                                     # a shield puts the bow away
            if self.u32(R + R_SET_WEAPON) != 0:
                self.equip_item(slot, self.u32(R + R_SET_WEAPON), 0)
        second = False
        if new_set != -1:
            self.w8(R + R_ACTIVE_SET, new_set)
            definition = self.u32(item)
            if self.s8(definition + 0x1D) == 0:
                for k in range(2):
                    if self.u32(R + R_SET_WEAPON + 4 * k) == item:
                        self.w32(R + R_SET_WEAPON + 4 * k, 0)
                if self.s8(definition + 0x1C) == 0 and self.passive_level(slot, 0x40000) > 0:
                    first = self.u32(R + R_SET_WEAPON)
                    if first != 0 and self.s8(self.u32(first) + 0x1C) == 0:
                        if self.u32(R + R_EQUIP) != first:
                            self.equip_item(slot, first, 0)
                        self.w32(R + R_SECOND_WEAPON, item)                 # dual wield: the second weapon
                        second = True
                if not second:
                    self.w32(R + R_SET_WEAPON + 4 * new_set, item)
        definition = self.u32(item)
        es = self.s8(definition + 0x1C)
        where = es * 4
        if self.u32(R + R_EQUIP + where) != item:
            category = self.s8(definition + 0x1D)
            if category == 0:
                if es != 8:
                    self.w8(R + R_WEAPON_CLASS, self.u8(definition + 0x1E))
                    definition = self.u32(item)
                kind = self.s8(definition + 0x1C)
                if kind == 2:                                               # two-handed or ranged
                    self.w32(R + R_EQUIP + 8, 0)
                    self.w32(R + R_EQUIP, 0)
                    self.w32(R + R_EQUIP + 4, 0)
                    if self.s8(definition + 0x1E) not in (4, 6):
                        self.w32(R + R_EQUIP + 12, 0)
                        self.w32(R + R_SECOND_WEAPON, 0)
                elif kind == 0:                                             # one-handed
                    two = self.u32(R + R_EQUIP + 8)
                    if two != 0 and self.s8(self.u32(two) + 0x1D) == 0:
                        self.w32(R + R_EQUIP + 8, 0)
                        self.w32(R + R_EQUIP, 0)
                    if self.passive_level(slot, 0x40000) > 0 and self.u32(R + R_EQUIP) != 0:
                        self.w32(R + R_EQUIP + 12, 0)                       # no shield with two weapons
                        self.w8(R + R_WEAPON_CLASS, 7)
                        where = 4
                    definition = self.u32(item)
                if self.s8(self.u32(item) + 0x1C) != 8:
                    self.call('player_resetIdleAnim', slot & M32)
                    self.call('inventory_selectIdleAnim', slot & M32,
                              (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32, 0)
            elif category == 1:
                if es == 3:                                                 # shield
                    two = self.u32(R + R_EQUIP + 8)
                    changed = False
                    if two != 0 and self.s8(self.u32(two) + 0x1D) == 0 and self.s8(R + R_WEAPON_CLASS) != 6:
                        self.w32(R + R_EQUIP + 8, 0)
                        self.w32(R + R_SET_WEAPON + 4 * self.s8(R + R_ACTIVE_SET), 0)
                        self.w8(R + R_WEAPON_CLASS, 5)
                        changed = True
                    elif self.u32(R + R_SECOND_WEAPON) != 0:
                        self.w32(R + R_SECOND_WEAPON, 0)
                        self.w32(R + R_EQUIP + 4, 0)
                        self.w8(R + R_WEAPON_CLASS, 0)
                        changed = True
                    if changed:
                        self.call('player_resetIdleAnim', slot & M32)
                        self.call('inventory_selectIdleAnim', slot & M32,
                                  (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32, 0)
            elif category == 2:
                if es == 5 and self.u32(R + R_EQUIP + 5 * 4) != 0 and self.u32(R + R_EQUIP + 6 * 4) == 0:
                    es = 6
                where = es * 4
                if es == 0xE and self.u8(R + R_SECOND_EARRING) != 0:
                    where = 0x38
                    if self.u32(R + R_EQUIP + 14 * 4) != 0:
                        if self.u32(R + R_EQUIP + 15 * 4) == 0:
                            es = 0xF
                        where = es * 4
            self.w32(R + R_EQUIP + where, item)
        if s32(quiet) == 0:
            definition = self.u32(item)
            entry = sound_name(SND_EQUIP, self.u64(item + 8), self.s8(definition + 0x1C), self.u8(definition + 0x1E))
            if self.call('net_isLocalSlot', slot & M32):
                self.sound(S_FX_LUMP, entry)
        self.call('inventory_selectIdleAnim', slot & M32, (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32, 0)
        self.call('player_recalcStats')

    def unequip_item(self, slot, item):
        """inventory_unequipItem 0x1c2f20 (slot, item address): inventory message 2.  Does
        not test that the item is equipped, or that it has a definition."""
        R = self.rec(slot)
        item &= M32
        definition = self.u32(item)
        category, es = self.s8(definition + 0x1D), self.s8(definition + 0x1C)
        anim = (G_PANEL_ANIM + s32(slot) * PANEL_ANIM_SIZE) & M32
        if category == 0:
            if self.u32(R + R_SECOND_WEAPON) != 0 and es == 0:
                self.unref_item(slot, item)
            else:
                found, swapped = False, 0
                if es == 8:
                    found = True
                elif self.u32(R + R_SET_WEAPON + 4 * self.s8(R + R_ACTIVE_SET)) == item:
                    found = True
                    swapped = self.call('Player_weaponSwapInput', self.u32(R + R_OBJECT),
                                        (G_PADS + s32(slot) * PAD_SIZE) & M32, 1)
                    if swapped == 0:
                        self.w8(R + R_WEAPON_CLASS, 5)
                    self.call('player_resetIdleAnim', slot & M32)
                    self.call('inventory_selectIdleAnim', slot & M32, anim, 0)
                if found and swapped == 0:
                    self.w32(R + R_EQUIP + es * 4, 0)
                for k in range(2):
                    if self.u32(R + R_SET_WEAPON + 4 * k) == item:
                        self.w32(R + R_SET_WEAPON + 4 * k, 0)
        elif category == 1:
            self.w32(R + R_EQUIP + es * 4, 0)
        elif category == 2:
            for k in (6, 5, 14, 15):
                if self.u32(R + R_EQUIP + 4 * k) == item:
                    self.w32(R + R_EQUIP + 4 * k, 0)
                    break
            else:
                if es == 7:
                    self.w32(R + R_EQUIP + 7 * 4, 0)
        entry = sound_name(SND_DROP, self.u64(item + 8), self.s8(self.u32(item) + 0x1C), 0, short=True)
        if self.call('net_isLocalSlot', slot & M32):
            self.sound(S_FX_LUMP, entry)
        self.call('inventory_selectIdleAnim', slot & M32, anim, 0)
        self.call('player_recalcStats')

    def on_join_panel(self, panel, slot, level_up):
        """inventory_onJoinPanel 0x1c0360 (panel, slot, levelUp): inventory message 4.  All of
        it is this machine's menu state except, with levelUp set, the two bookkeeping bytes
        of the record - of the slot stored in the panel, not of the message's slot - and a
        message 9 that every machine sends from inside the handler."""
        P = (G_ITEM_PANELS + s32(panel) * PANEL_SIZE) & M32
        for off in (0x14, 0x24, 0x28, 0x18, 0x1C, 0x3C, 0x40):            # menu_resetListState 0x1d1380
            self.w32(P + off, 0)
        rows = self.u32(P + 0x70)
        self.w32(P + 0x18, rows)
        self.w32(P + 0x4C, 0)
        self.call('inventory_refreshPanelModel', slot & M32, panel & M32, 0)
        self.w32(P + 0x24, (rows * self.u32(G_PANEL_ROWS)) & M32)
        if s32(self.call('net_getLocalPlayerSlot', 0)) == s32(slot):
            self.w8(G_JOIN_FLAG, 0)
        if level_up == 0:
            return
        owner = self.s32(P + 0x34)
        if self.call('net_isLocalSlot', owner & M32):
            self.sound(S_FX_LUMP, S_SND_LEVELUP)
        R = self.rec(owner)
        self.send(self.u32(G_INV_CHANNEL), bytes((9, owner & 0xFF, self.u8(R + R_LEVEL))))
        self.w8(R + R_LVLUP_OWNER, owner)
        self.w32(P + 0x50, 5)
        self.w8(R + R_LVLUP_DONE, 0)
        if self.s8(G_NETWORK_MODE) != 0:
            self.w8(G_PANEL_LEVELUP, 1)
        else:
            self.w8(G_PANEL_LEVELUP + s32(panel) * PANEL_SIZE, 1)

    def on_stat_point(self, slot, stat):
        """inventory_onStatPoint 0x1c2548 (slot, stat): inventory message 6.  stat below 4
        (signed, so also negative) spends a stat point on word +0x78 + 4 * stat; 4-7 raise
        base statistic stat - 4 for nothing; 8 adds a skill point."""
        R = self.rec(slot)
        stat = s32(stat)
        if stat < 4:
            if self.u8(R + R_STAT_POINTS) != 0:
                a = R + R_BASE_STATS + stat * 4
                self.w32(a, self.u32(a) + 1)
                self.w8(R + R_STAT_POINTS, self.u8(R + R_STAT_POINTS) + 0xFF)
            if self.call('net_isLocalSlot', slot & M32):
                self.sound(S_FX_LUMP, S_SND_STAT)
            if self.u8(R + R_STAT_POINTS) == 0:
                self.w8(R + R_STAT_POINTS, 0)
                self.w8(R + R_LVLUP_DONE, 1)
        else:
            if (stat - 4) & M32 < 4:
                a = R + 0x68 + stat * 4
                self.w32(a, self.u32(a) + 1)
            if stat == 8:
                self.w32(R + R_SKILL_POINTS, self.u32(R + R_SKILL_POINTS) + 1)
        self.call('player_recalcStats')

    def on_skill_point(self, slot, is_skill, value):
        """inventory_onSkillPoint 0x1c2648 (slot, kind, value): inventory message 7.  One
        skill point buys one rank, to a limit of 20.  kind 0: value is a passive's mask;
        otherwise a skill id.  The cost, the class and the level are not checked here."""
        R = self.rec(slot)
        if self.s32(R + R_SKILL_POINTS) <= 0:
            return
        if is_skill == 0:
            mask = s32(value) & M64
            if self.passive_level(slot, mask) >= 0x14:
                return
            self.w32(R + R_SKILL_POINTS, self.u32(R + R_SKILL_POINTS) - 1)
            self.rebuild_abilities(mask, slot, -1)
            self.raise_passive_level(slot, mask, self.passive_level(slot, mask) + 1)
            return
        skill_id = s32(value)
        if self.skill_rank(slot, skill_id) >= 0x14:
            return
        self.w32(R + R_SKILL_POINTS, self.u32(R + R_SKILL_POINTS) - 1)
        if self.skill_rank(slot, skill_id) > 0:
            self.set_skill_rank(slot, skill_id, self.skill_rank(slot, skill_id) + 1)
        elif self.u32(self.u32(G_SKILL_TABLE + skill_id * 4) + 8) == 3:
            self.set_skill_rank(slot, skill_id, 1)
        else:
            self.add_skill_ability(skill_id, slot)

    # =======================================================================================
    # Game ("HUD") channel
    # =======================================================================================
    def hud_on_msg(self, p):
        """hud_onMsg 0x1d8ca0 (jump table 0x53c350, types 0-13)."""
        p = bytes(p) + bytes(max(0, 16 - len(p)))
        kind = s8(p[0])
        b = lambda i: s8(p[i])
        w = lambda i: p[i] | p[i + 1] << 8 | p[i + 2] << 16 | p[i + 3] << 24
        if kind == 0:
            self.on_quick_slot(b(1), b(2), b(3))
        elif kind == 1:
            self.on_assign_spell(b(1), b(2), s32(w(4)), w(8) | w(12) << 32)
        elif kind == 2:
            self.on_menu_state(b(1), b(2))
        elif kind == 3:
            if self.call('dialog_isOpen') == 0 and self.call('task_isRunning', S_TASK_MISSION) == 0:
                self.recall(b(1))
                if self.s8(G_RECALL_COUNTDOWN) != 0:
                    self.call('net_closeLocalMenus', 0)
        elif kind == 4:
            self.on_player_left(b(1))
        elif kind == 5:
            self.call('Savepoint_startSavedEffect', w(4))
        elif kind == 6:
            self.on_disconnect_request(b(1))
        elif kind == 7:
            self.set_pending_level(p[1:], False)
        elif kind == 8:
            self.w16(G_EXIT_COUNTDOWN, 0xF0 if self.s8(G_NETWORK_MODE) != 0 else 1)
        elif kind == 9:
            self.w8(G_CHECKSUM_COUNT, 0)
            self.w32(G_CHECKSUM_PENDING, 1)
        elif kind == 10:
            self.on_checksum(b(1), w(4), w(8))
        elif kind == 11:
            self.set_pending_level(p[4:], True)
        elif kind == 12:
            self.w32(G_MEDAL_ACK, 1)
        elif kind == 13:
            self.on_quick_cast(b(1), b(2))

    def on_quick_slot(self, slot, button, index):
        """hud_onQuickSlot 0x1de28c (slot, button, ability index): game message 0.  Binds an
        ability record to button A (button 0) or B; if the other button has it, the two
        bindings are exchanged."""
        R = self.rec(slot)
        if self.call('net_isLocalSlot', slot & M32):
            self.sound(S_FX_LUMP_HUD, S_SND_ASSIGN)
        mine, other = (R_QUICK_A, R_QUICK_B) if button == 0 else (R_QUICK_B, R_QUICK_A)
        if self.s8(R + other) == index:
            self.w8(R + other, self.u8(R + mine))
        self.w8(R + mine, index)

    def on_assign_spell(self, slot, index, kind, value):
        """hud_onAssignSpell 0x1de61c (slot, ability index, kind, 64-bit value): game message
        1.  kind 1: value is a skill id; otherwise it is the 64-bit mask of an old-style
        ability.  If one of the first eight records already holds the value, that record
        takes over what the target record held (a swap)."""
        R = self.rec(slot)
        value &= M64
        rec = (R + R_ABILITIES + s32(index) * ABILITY_SIZE) & M32
        found = -1
        for i in range(8):
            a = R + R_ABILITIES + i * ABILITY_SIZE
            if kind == 1:
                if self.s16(a + 0x20) & M64 == value:
                    found = i
            elif self.u64(a + 0x48) == value:
                found = i
        if found != -1:
            old = R + R_ABILITIES + found * ABILITY_SIZE
            held = self.u16(rec + 0x20)
            self.w64(old + 0x48, M64)
            self.w16(old + 0x20, held)
            if s16(held) != -1:
                if self.cstr(S_NEWSTYLE_HUD) in self.cstr(rec):
                    self.w64(old, self.u64(S_NEWSTYLE_HUD))
                    self.w8(old + 8, self.u8(S_NEWSTYLE_HUD + 8))
                    skill = self.u32(G_SKILL_TABLE + self.s16(rec + 0x20) * 4)
                    self.w8(old + 0x25, self.u8(skill + 8))
                    self.w8(old + 0x24, self.skill_rank(slot, self.s16(rec + 0x20)))
                else:
                    self.rebuild_abilities(0x20000, slot, found)
        if kind == 1:
            self.w8(rec + 8, self.u8(S_NEWSTYLE_HUD + 8))
            self.w64(rec, self.u64(S_NEWSTYLE_HUD))
            for i in range(8):
                a = R + R_ABILITIES + i * ABILITY_SIZE + 0x20
                if self.s16(a) & M64 == value:
                    self.w16(a, 0)
            skill_id = s32(value)
            skill = self.u32(G_SKILL_TABLE + skill_id * 4)
            self.w16(rec + 0x20, value)
            self.w8(rec + 0x25, self.u8(skill + 8))
            self.w8(rec + 0x24, self.skill_rank(slot, skill_id))
        else:
            self.rebuild_abilities(value, slot, index)
        if self.call('net_isLocalSlot', slot & M32):
            self.sound(S_FX_LUMP_HUD, S_SND_ASSIGN)

    def mask_local_buttons(self, slot, frames, mask):
        """net_maskLocalButtons 0x13e540: the input-lock entry of the slot (12 bytes at
        0x5d0bc8): frames = max(old, frames), mask, third word 0."""
        E = (G_INPUT_LOCK + s32(slot) * 12) & M32
        old = self.s32(E)
        self.w32(E + 8, 0)
        self.w32(E, frames if old < frames else old)
        self.w32(E + 4, mask)

    def on_menu_state(self, slot, state):
        """Game message 2, 0x1d8d50 (slot, state): a full-screen menu opened (state 1; 2 or
        more also freezes the character) or closed (0) on the owner's machine.  Ignored
        when the slot has no player object."""
        R = self.rec(slot)
        player = self.u32(R + R_OBJECT)
        if player == 0:
            return
        if state != 0:
            self.w32(player + 0xC, self.u32(player + 0xC) | 0x400000)
            self.w8(R + R_MENU_COUNTDOWN, 0)
            if state >= 2:
                player = self.u32(R + R_OBJECT)
                self.w32(player + 0xC, self.u32(player + 0xC) | 0x800000)
        else:
            self.mask_local_buttons(slot, 0x3C, 0xF0)
            self.w8(R + R_MENU_COUNTDOWN, 10)
            player = self.u32(R + R_OBJECT)
            self.w32(player + 0xC, self.u32(player + 0xC) & 0xFF7FFFFF)

    def recall(self, slot):
        """recall_execute 0x18c230 (slot): game message 3.  Outside the hub it costs one
        recall potion from bag 2; from the hub it needs a stored return level."""
        self.call('pauseMenu_close')
        R = self.rec(slot)
        error = None
        if self.call('game_inNoSaveZone'):
            error = S_ERR_RECALL
        elif C.le(self.u32(R + R_HP), 0):
            error = S_ERR_RECALL_DEAD
        else:
            in_hub = self.cstr(S_HUB) in self.cstr(G_LEVEL_NAME)
            if in_hub and self.cstr(R + 0x24) == self.cstr(S_NONE):
                error = S_ERR_RECALL_TARGET
        if error is not None:
            self.call('hud_showMessage', self.call('text_lookup', error), 0xB4, M32, 0)
            return
        if not in_hub:
            used = False
            if self.u32(R + R_OBJECT) != 0 and C.lt(0, self.u32(R + R_HP)):
                i = 0
                while i < self.s32(R + R_BAG_COUNT + 2 * BAG_SIZE):
                    it = R + R_BAGS + 2 * BAG_SIZE + i * ITEM_SIZE
                    if self.cstr(self.u32(self.u32(it))) == self.cstr(S_RECALL_NAME_2):
                        left = (self.u16(it + 4) - 1) & 0xFFFF
                        used = True
                        self.w16(it + 4, left)
                        if left == 0:
                            self.remove_item(slot, i, 2, 0)
                        break
                    i += 1
            if not used:
                self.call('hud_showMessage', self.call('text_lookup', S_ERR_RECALL_CHARGES), 0xB4, slot & M32, 0)
                return
        self.w8(G_RECALL_COUNTDOWN, 0x3C)
        i = 0
        while i < self.s32(G_ALIVE_COUNT):
            block = self.call('pool_new', 0x60)
            if block:
                player = self.u32(self.rec(self.s32(G_ALIVE_LIST + 4 * i)) + R_OBJECT)
                self.call('RecallEffect_ctor', block, self.vec(player + 0x10))
            i += 1
        self.sound(S_FX_LUMP_RECALL, S_SND_RECALL)
        self.stop_stream()
        self.w32(G_MENU_LOCKOUT, 0x3C)
        self.w32(G_PAUSED, 0)
        self.w8(G_STREAM_FLAG, 0)

    def stop_stream(self):
        if self.call('audio_streamStatus', 2) & 0x40:
            self.call('stream_queueStop', 2)

    def on_player_left(self, slot):
        """Game message 4, 0x1d8e40 (slot): shows "<name> <text>" to everybody and kills the
        slot's character with a damage call of 1,000,000."""
        R = self.rec(slot)
        text = bytearray()
        for c in self.cstr(R) + self.cstr(S_LEFT_SPACE):
            text += bytes((c, 0))
        text += self.wstr(self.call('text_lookup', S_LEFT_TEXT))
        self.call('hud_showMessage', bytes(text), 300, M32, 0)
        player = self.u32(R + R_OBJECT)
        if player == 0:
            return
        entry = self.u32(player + 0x48) + 0x10
        self.w32(player + 0xC, self.u32(player + 0xC) & 0xFFBFFFFF)
        self.call('Player_takeDamage_virtual', (player + self.s16(entry)) & M32, 0, 0x20000040, 0x49742400)
        self.call('Player_processDamage', self.u32(R + R_OBJECT))

    def on_disconnect_request(self, slot):
        """Game message 6, 0x1d8f5c (slot): on the machines that do not own the slot.  If
        the leaver is the only player alive, the first other active slot is respawned at
        the leaver's position; then net_disconnectPlayer(slot, 1)."""
        if self.call('net_isLocalSlot', slot & M32):
            return
        if self.s32(G_ALIVE_COUNT) == 1 and self.s32(G_ALIVE_LIST) == slot:
            i = 0
            while i < self.s32(G_NUM_PLAYERS):
                if self.call('net_isSlotActive', i) and i != slot:
                    player = self.u32(self.rec(slot) + R_OBJECT)
                    self.call('player_respawn', i, self.vec(player + 0x10), self.s16(player + 0x38) & M32, 2, 8)
                    break
                i += 1
        self.call('net_disconnectPlayer', slot & M32, 1)

    def set_pending_level(self, name, clear_load_flag):
        """Game messages 7 (0x1d9004) and 11 (0x18cb80): the level name in the message is
        copied to the pending-level buffer 0x41b6d0 with no length limit."""
        name = bytes(name).split(b'\0')[0] + b'\0'
        for i, c in enumerate(name):
            self.w8(G_PENDING_LEVEL + i, c)
        self.w8(G_PENDING_LEVEL + 0x50, 0xFF)
        self.call('pauseMenu_close')
        self.w32(G_PAUSED, 0)
        self.w32(G_MENU_LOCKOUT, 0x3C)
        self.w8(G_STREAM_FLAG, 0)
        if clear_load_flag:
            self.w8(G_LOAD_FLAG, 0)
        self.stop_stream()

    def on_checksum(self, slot, live, saved):
        """Game message 10, 0x1d90a4 (slot, two checksums).  When as many messages as there
        are players have arrived, each pair is compared with what this machine computed;
        a mismatch sets the failure word and disconnects that slot (not the local one)."""
        E = (G_CHECKSUM_RECEIVED + slot * 8) & M32
        self.w32(E, live)
        count = (self.u8(G_CHECKSUM_COUNT) + 1) & 0xFF
        self.w8(G_CHECKSUM_COUNT, count)
        self.w32(E + 4, saved)
        if s8(count) != self.s32(G_NUM_PLAYERS) or s8(count) <= 0:
            return
        i = 0
        while i < self.s32(G_NUM_PLAYERS):
            for j in range(2):
                at = (i * 2 + j) * 4
                if self.u32(G_CHECKSUM_RECEIVED + at) != self.u32(G_CHECKSUM_EXPECTED + at):
                    self.w32(G_CHECKSUM_FAILED, 1)
                    if i != s32(self.call('net_getLocalPlayerSlot', 0)):
                        self.call('net_disconnectPlayer', i, 1)
            i += 1

    def on_quick_cast(self, slot, index):
        """hud_onQuickCastWarn 0x1de340 (slot, ability index): game message 13.  Despite the
        name this is the quick-cast request: with no cast already queued (player +0x488),
        an ability of kind 1 only shows a warning; any other is queued when the player's
        action state is 2."""
        R = self.rec(slot)
        rec = (R + R_ABILITIES + s32(index) * ABILITY_SIZE) & M32
        if rec == 0:
            return
        player = self.u32(R + R_OBJECT)
        if self.u32(player + 0x488) != 0:
            return
        if self.u8(rec + 0x25) == 1:
            self.call('hud_showMessage', self.call('text_lookup', S_QUICKCAST_WARN), 0x5A, slot & M32, 0)
        elif self.u32(player + 0x58C) == 2:
            self.w32(player + 0x488, rec)

    # =======================================================================================
    # Shop channel
    # =======================================================================================
    def shop_on_msg(self, p):
        """shop_onMsg 0x1c5d28: type 0 buy (slot, address of a stock record), type 1 sell
        (the fields of inventory message 0); any other type does nothing."""
        p = bytes(p) + bytes(max(0, 16 - len(p)))
        kind = s8(p[0])
        b = lambda i: s8(p[i])
        h = lambda i: s16(p[i] | p[i + 1] << 8)
        w = lambda i: p[i] | p[i + 1] << 8 | p[i + 2] << 16 | p[i + 3] << 24
        if kind == 0:
            self.shop_buy(b(1), w(4))
        elif kind == 1:
            self.shop_sell(b(1), w(4), b(10), h(2), h(8), b(11), b(12))

    def shop_buy(self, slot, record):
        """shop_buy 0x1d1240 (slot, stock record): the price is the item's value times 0.6
        (0.45 for category 1, 1.0 for flag bits 40/41 or ammunition), truncated.  With
        enough gold it is paid and inventory_giveItem is called; its result is ignored, so
        a full bag takes the gold and gives nothing."""
        R = self.rec(slot)
        definition = self.u32(record)
        factor = 0x3F199999
        if self.s8(definition + 0x1D) == 1:
            factor = 0x3EE66666
        if self.u64(record + 8) & 0x30000000000 or self.s8(definition + 0x1C) == 8:
            factor = ONE
        price = C.to_int(C.mul(C.from_int(self.item_value(record)), factor))
        gold = self.s32(R + R_GOLD)
        if gold < price:
            return
        self.w32(R + R_GOLD, gold - price)
        self.give_item(slot, record, 1)

    def shop_sell(self, slot, index, bag, column, row, panel, mode):
        """Shop message 1, 0x1c5d70: credit the sale, then inventory_dropItem with the same
        arguments.  The cell is not checked before its value is computed."""
        R = self.rec(slot)
        item = (R + R_BAGS + s32(index) * ITEM_SIZE + bag * BAG_SIZE) & M32
        value = C.from_int(self.item_value(item))
        definition = self.u32(item)
        if self.s8(definition + 0x1C) == 8 or self.cstr(S_STACK_STEM_SELL) in self.cstr(self.u32(definition)) \
                or self.u64(definition + 0x28) & 0x1C0000000000:
            value = C.mul(value, 0x41A00000)
        paid = C.to_int(C.mul(C.div(value, C.from_int(self.s16(item + 4))), 0x3D4CCCCC))
        if paid <= 0:
            paid = 1
        if self.s8(definition + 0x1C) == 8 or self.u64(definition + 0x28) & 0x400000000000:
            paid = 0
        gold = s32(self.s32(R + R_GOLD) + paid)
        self.w32(R + R_GOLD, gold)
        if gold > GOLD_CAP:
            self.w32(R + R_GOLD, GOLD_CAP)
        self.drop_item(slot, index, bag, column, row, panel, mode)


# ---------------------------------------------------------------------------------------
# What the senders put on the wire.  Each function mirrors the sender named in its comment
# (executed by the differential test); the result is (family, bytes).  One-byte fields are
# given as signed or unsigned numbers; nothing is left undefined by any sender.
# ---------------------------------------------------------------------------------------
def _b(*values):
    return bytes(v & 0xFF for v in values)


def _h(v):
    return (v & 0xFFFF).to_bytes(2, 'little')


def _w(v):
    return (v & M32).to_bytes(4, 'little')


def msg_drop(slot, index, bag, column, row, panel, mode):       # invmsg_sendDrop 0x1c59d0, 13 bytes
    return 'inventory', _b(0, slot) + _h(column) + _w(index) + _h(row) + _b(bag, panel, mode)


def msg_equip(slot, item, quiet=0):                             # invmsg_sendEquip 0x1c5800, 8 bytes
    return 'inventory', _b(1, quiet) + _h(slot) + _w(item)


def msg_unequip(slot, item):                                    # invmsg_sendUnequip 0x1c5840, 8 bytes
    return 'inventory', _b(2, 0) + _h(slot) + _w(item)


def msg_join_panel(panel, slot, level_up):                      # invmsg_sendJoinPanel 0x1c5628, 4 bytes
    return 'inventory', _b(4, panel, slot, level_up)


def msg_weapon_class(slot, weapon_class):                       # 0x1c5570 and inventory_close, 3 bytes
    return 'inventory', _b(5, slot, weapon_class)


def msg_stat_point(slot, stat):                                 # invmsg_sendStatPoint 0x1c5780, 4 bytes
    return 'inventory', _b(6, slot) + _h(stat)


def msg_skill_point(slot, is_skill, value):                     # invmsg_sendSkillPoint 0x1c57b8, 8 bytes
    return 'inventory', _b(7, slot, is_skill, 0) + _w(value)


def msg_combine(slot, a, b, c):                                 # invmsg_sendCombine 0x1c5738, 16 bytes
    return 'inventory', _b(8, slot, 0, 0) + _w(a) + _w(b) + _w(c)


def msg_level_ack(slot, level):                                 # 0x1c55a8, menu_openInventory, onJoinPanel; 3 bytes
    return 'inventory', _b(9, slot, level)


def msg_use_potion(slot, kind, column, row, panel):             # 0x1c55e0 (never called), 10 bytes
    return 'inventory', _b(10, slot) + _h(kind) + _h(column) + _h(row) + _h(panel)


def msg_quick_slot(slot, button, index):                        # hudmsg_sendQuickSlot 0x1de06c, 4 bytes
    return 'game', _b(0, slot, button, index)


def msg_assign_spell(slot, index, kind, value):                 # hudmsg_sendAssignSpell 0x1de3ec, 16 bytes
    return 'game', _b(1, slot, index, 0) + _w(kind) + (value & M64).to_bytes(8, 'little')


def msg_menu_state(slot, state, flag=0):                        # hudmsg_sendMenuState 0x1de0dc, 4 bytes, net games only
    return 'game', _b(2, slot, state, flag)


def msg_recall(slot):                                           # hudmsg_sendRecall 0x1de138, 2 bytes
    return 'game', _b(3, slot)


def msg_player_left(slot):                                      # hudmsg_sendPlayerLeft 0x1de16c, 2 bytes
    return 'game', _b(4, slot)


def msg_savepoint(address):                                     # hudmsg_sendSavepoint 0x1de1a0, 8 bytes
    return 'game', _b(5, 5, 5, 5) + _w(address)


def msg_disconnect_request(slot):                               # hudmsg_sendDisconnectRequest 0x1de1e0, 2 bytes
    return 'game', _b(6, slot)


def msg_new_world(name):                                        # hudmsg_sendNewWorld 0x1d9250, strlen + 2 bytes
    return 'game', _b(7) + bytes(name) + b'\0'


def msg_exit_countdown():                                       # hudmsg_sendExitCountdown 0x1de25c
    return 'game', _b(8)


def msg_checksum_start():                                       # hudmsg_sendChecksumStart 0x1de430
    return 'game', _b(9)


def msg_checksum(slot, live, saved):                            # net_sendChecksums 0x1de46c, 12 bytes
    return 'game', _b(10, slot, 0, 0) + _w(live) + _w(saved)


def msg_load_level():                                           # hudmsg_sendLoadLevel 0x1de598: 4 bytes, the
    return 'game', _b(11, 0, 0, 0)                              # name stays behind in the sender's buffer


def msg_medal_ack():                                            # hudmsg_sendMedalAck 0x1de5ec
    return 'game', _b(12)


def msg_quick_cast(slot, index):                                # hudmsg_sendQuickCastWarn 0x1de0a4, 3 bytes
    return 'game', _b(13, slot, index)


def msg_buy(slot, record):                                      # shopmsg_sendBuy 0x1c5f78, 8 bytes
    return 'shop', _b(0, slot, 0, 0) + _w(record)


def msg_sell(slot, index, bag, column, row, panel, mode=1):     # shopmsg_sendSell 0x1d1330 / itemList_input, 13 bytes
    return 'shop', _b(1, slot) + _h(column) + _w(index) + _h(row) + _b(bag, panel, mode)


def msg_shop_closed(slot):                                      # nullmsg_sendShopClosed 0x1e0134, 2 bytes
    return 'null', _b(1, slot)


if __name__ == '__main__':
    print(__doc__)
