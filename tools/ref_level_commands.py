#!/usr/bin/env python3
"""ref_level_commands.py - reference model of the code five level-script built-ins reach
below their handlers, in Champions: Return to Arms (SLUS_209.73, US v2.00).

A research tool, not game code.  The handlers themselves are ref_natives.Game.n_* (table
0x403370; tools/difftest_natives.py compares them).  This module adds the bodies those
handlers hand work to, which difftest_natives keeps as recording stubs, so that a client
can see every store they make:

    autoPropSetState 0x142320  -> virtual slot 18 of the AutoProp family
                                  AutoProp_setState 0x23d680, AutoProp_setPassable 0x23d7ac
                                  (slot 19), model_buildHideMask 0x179550, anim_push
                                  0x170838, anim_jumpTopToEnd 0x170bc8,
                                  world_setPieceCollision 0x182b00
    killMonster 0x144a84       -> virtual slot 27 of Gnome: Gnome_setState 0x269bb4, the
                                  creature state gate 0x10a9c0 and its three timer tests
                                  0x1195e0 / 0x1195f0 / 0x119608, GameObject_rand 0x1509d0,
                                  anim_start 0x16cfe0, slot 28 Creature_onDeath 0x10beb8,
                                  obj_getPropStr 0x14f4c0 (its in-place key lower-casing),
                                  creature_stopBossMusic 0x1192f8
    soundSequence 0x143684     -> sound_playOnObject 0x214230 (object 0 only), game_isFrozen
                                  0x1ebdf8, sound_setPlaysWhileFrozen 0x216ad0
    preloadResource 0x14222c   -> lump_load 0x173558
    activateStore 0x144010     -> nothing new: its call-outs (dialog_isOpen, shop_openOrStock,
                                  net_isLocalSlot, net_closeLocalMenus) stay call-outs; the
                                  shop itself is docs/spec/vendor-stock.md (t3/research-vendor-
                                  stock 4c73914).

Bodies is used by tools/difftest_level_commands.py as the host side of a ref_natives.Game:
the host routes a call-out or a virtual call to a body here when the original runs that
code for real in the comparison, and records the body's own call-outs (CALLOUTS) exactly as
the original's recording stubs do.  Floats are raw 32-bit patterns through ref_core.

Where the model stops (ref_amx.HostFault, so a comparison counts it as a fault on both
sides or a mismatch): a Gnome state other than 0x14, sound_playOnObject on an object, an
animation track whose flags have 0x800 (animtrack_decode 0x16e468 is not modelled), and
lump_load of a file the disc does not have (the original stores to address 0, 0x17363c).
Standard library only; no game data is embedded.
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

# ---- handlers (table 0x403370) and the bodies below them ------------------------------------
HANDLERS = {'autoPropSetState': 0x142320, 'killMonster': 0x144A84, 'soundSequence': 0x143684,
            'preloadResource': 0x14222C, 'activateStore': 0x144010}
NATIVE_TABLE = 0x403370
VT_AUTOPROP, VT_AUTOPROP_LP, VT_GNOME = 0x5133C0, 0x5130C0, 0x5103A8
AUTOPROP_SET_STATE, AUTOPROP_SET_PASSABLE = 0x23D680, 0x23D7AC
GNOME_SET_STATE, CREATURE_ON_DEATH = 0x269BB4, 0x10BEB8
SLOT_SET_STATE, SLOT_SET_PASSABLE, SLOT_AI_STATE, SLOT_ON_DEATH = 18, 19, 27, 28
REAL_BODIES = {         # run for real in the comparison
    'AutoProp_setState': 0x23D680, 'AutoProp_setPassable': 0x23D7AC, 'model_buildHideMask': 0x179550,
    'anim_push': 0x170838, 'anim_jumpTopToEnd': 0x170BC8, 'anim_start': 0x16CFE0,
    'world_setPieceCollision': 0x182B00, 'Gnome_setState': 0x269BB4, 'creature_stateGate': 0x10A9C0,
    'Creature_isNotRooted': 0x1195E0, 'Creature_isAttackReady': 0x1195F0,
    'Creature_isNotStunned': 0x119608, 'GameObject_rand': 0x1509D0, 'Creature_onDeath': 0x10BEB8,
    'creature_stopBossMusic': 0x1192F8, 'sound_playOnObject': 0x214230,
    'sound_setPlaysWhileFrozen': 0x216AD0, 'game_isFrozen': 0x1EBDF8, 'lump_load': 0x173558,
}
# call-outs of those bodies that stay recording stubs: name -> address
CALLOUTS = {
    'world_movePiece': 0x182C98, 'obj_delete': 0x14F200, 'arena_addKill': 0x3056CC,
    'creature_bossMusicName': 0x10DBE0, 'task_isRunning': 0x19E5E8, 'lump_findLoaded': 0x17306C,
    'cd_findFile': 0x1724FC, 'lump_prepare': 0x1734C4, 'mem_allocTagged': 0x14FF88,
    'cd_readBlocking': 0x172AD0, 'lump_pollAsync': 0x172CA8,
}
# (call-outs that are ref_natives.EXT entries keep their names there: dbg_printf,
# stream_queueStop, loot_spawnNamedItem, dialog_isOpen)

# ---- globals ------------------------------------------------------------------------------------
G_WORLD = 0x44FDC8              # the level's world (pieces at +0x54, chunks at +0x20)
G_SELECTED_OBJ = 0x4039F8
G_ARENA = 0x4F7120              # arena flag tested by the state gate and the death code
G_ARENA_B = 0x4F711C
G_GATE_C, G_GATE_D = 0x503890, 0x503894
G_NETWORK_MODE = 0x402791
G_PAUSED = 0x41B4F4
G_CUTSCENE_ACTIVE = 0x44FCD0
G_FREEZE_B = 0x506048
G_FREEZE_C = 0x4F6708
G_FRAME_COUNT = 0x44FDCC
G_SOUND_SEQS = 0x871A68         # 32 x 0x4c sound-sequence players
SOUND_SEQ_SIZE, SOUND_SEQS = 0x4C, 32
G_SOUND_GROUP_CAP = 0x4F8A28    # s8 per group
G_SOUND_SERIAL = 0x4F8950       # u16, 7 bits used
G_LUMP_TAG_INDEX = 0x41BF7C
G_LUMP_PENDING_DATA, G_LUMP_PENDING_SIZE = 0x41BFA0, 0x41BFA4
G_LUMP_PENDING_FLAG, G_LUMP_PENDING_CLEAR = 0x41BF9D, 0x41BF80
G_LUMP_PENDING_NAME = 0x7C25C8
G_LUMP_TAGS = 0x7B9480          # 40-byte tag records
G_STORE_INDEX, G_STORE_PENDING = 0x4F7150, 0x4FDD30
S_DEATH_SCRIPT, S_DROP_ITEM = 0x52FBF8, 0x52FC08          # 'deathScript', 'dropitem'
S_PLAYER_SELECTION = 0x53DDB8                            # 'playerSelection'
S_LUMP_NOT_FOUND = 0x533F80
F_0, F_1, F_60, F_1_60 = 0x00000000, 0x3F800000, 0x42700000, 0x3C888888
F_0_1 = 0x3DCCCCCC              # Gnome death blend
F_360, F_840 = 0x43B40000, 0x44520000
F_MINUS_256 = 0xC3800000

# ---- object fields --------------------------------------------------------------------------------
O_FLAGS, O_POS, O_PROPS, O_VTABLE = 0x0C, 0x10, 0x2C, 0x48
OF_NOCOLLIDE, OF_DELETE_ON_DEATH, OF_DEAD, OF_CREATURE = 0x1, 0x2, 0x8, 0x20
OF_KILLED, OF_4000, OF_AUTOPROP = 0x2000, 0x4000, 0x10000000
AP_MODEL, AP_ANIM, AP_ANIM_CACHE_CLEAR, AP_MASK = 0x90, 0x98, 0x9C, 0xC8
AP_KIND, AP_STATES, AP_ANIMS, AP_STATE_FLAGS = 0x11C, 0x120, 0x128, 0x12C
AP_STATE, AP_COUNTER, AP_REACHED, AP_PIECE = 0x178, 0x17C, 0x180, 0x18C
AK_DOOR = 0x1                   # AutoDoor in +0x11c
SF_PASSABLE, SF_LOOPING = 0x1, 0x2
C_CLASS, C_RAND, C_FLAGS64, C_ANIM = 0x24, 0x44, 0xA8, 0x114
C_HP, C_HIDDEN, C_AI_STATE, C_TARGET = 0x228, 0x231, 0x232, 0x234
C_OWNER = 0x2E4
C_ROOT, C_ATTACK, C_T31A, C_STUN = 0x314, 0x318, 0x31A, 0x31C
CLASS_DEATH_ANIMS = 0xA4        # 4 x 8-byte entries in the class definition
DEATH_CFLAGS_KEEP = 0xFFFFFFFFF73FFFFF
KILL_FLAGS = OF_KILLED | OF_DEAD | OF_NOCOLLIDE        # 0x2009
STATE_DEAD = 0x14

MUTATION = None                 # set by a mutation control in the difftest; None in normal use


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def sext32(x):
    """A 32-bit result as the 64-bit register holds it."""
    return s32(x) & M64


class Bodies:
    """The bodies above, on a ref_natives.Game's memory.  log(name, *args) records one
    call-out of a body and returns its answer (the difftest's host supplies it)."""

    def __init__(self, game, log):
        self.game = game
        self.mem = game.mem
        self.log = log
        self.virtual_bodies = {AUTOPROP_SET_STATE: self.autoprop_set_state,
                               AUTOPROP_SET_PASSABLE: self.autoprop_set_passable,
                               GNOME_SET_STATE: self.gnome_set_state,
                               CREATURE_ON_DEATH: self.creature_on_death}
        self.ext_bodies = {'anim_push': self.anim_push, 'anim_jumpTopToEnd': self.anim_jump_top_to_end,
                           'anim_start': self.anim_start, 'sound_playOnObject': self.sound_play_on_object,
                           'sound_setPlaysWhileFrozen': self.sound_set_plays_while_frozen,
                           'lump_load': self.lump_load}

    def clip_length(self, clip):
        """The word at clip + 4 (lw): the CPU traps on an unaligned address."""
        if (clip + 4) & 3:
            raise HostFault('unaligned load from 0x%x (clip pointer 0x%x)' % ((clip + 4) & M32, clip))
        return self.mem.u32(clip + 4)

    # ---- virtual calls ------------------------------------------------------------------------
    def slot_target(self, addr, slot):
        """(function, this) of a virtual call: the entry at vtable + 8 slot is a s16 this
        adjustment and the function address at +4 (the handlers' lh / lw pair)."""
        table = self.mem.u32(addr + O_VTABLE)
        return self.mem.u32(table + 8 * slot + 4), (addr + s16(self.mem.u16(table + 8 * slot))) & M32

    def virtual(self, addr, slot, *args):
        function, this = self.slot_target(addr, slot)
        body = self.virtual_bodies.get(function)
        if body is None:
            return self.log('virtual', slot, this, *args)
        return body(this, *args)

    # ---- AutoProp family ----------------------------------------------------------------------
    def autoprop_set_state(self, o, n):
        """AutoProp_setState 0x23d680 (slot 18 of AutoProp 0x5133c0 and AutoPropLP 0x5130c0).
        n < States (+0x120, signed): state +0x178 = n, counter +0x17c = 0, reached bits
        +0x180 = bits 0..n (0 for n = 0), mesh mask +0xc8 = model_buildHideMask(+0x90, low
        word of +0x180), track count +0x9c = 0, then the state's animation (+0x128 + 8n) is
        pushed (mode 3 when the state flags +0x12c + 8n have 2, else 6) and jumped to its
        end and the counter becomes its length + 1; last, slot 19 with state flags & 1.
        n >= States: nothing at all.  No action script, no 'done' bit."""
        mem = self.mem
        n = s32(n)
        if not n < s32(mem.u32(o + AP_STATES)):
            return 0
        mem.w32(o + AP_STATE, n)
        mem.w32(o + AP_COUNTER, 0)
        mem.w64(o + AP_REACHED, 0)
        if n != 0 or MUTATION == 'autoprop_bits_for_zero':
            if s32(n + 1) > 0:
                bits = 0
                for k in range(n + 1):
                    bits |= sext32(1 << (k & 31))
                mem.w64(o + AP_REACHED, bits)
        mask = self.model_build_hide_mask(mem.u32(o + AP_MODEL), sext32(mem.u32(o + AP_REACHED)))
        mem.w8(o + AP_ANIM_CACHE_CLEAR, 0)
        mem.w64(o + AP_MASK, mask)
        state = s32(mem.u32(o + AP_STATE))
        anim = mem.u32(o + AP_ANIMS + 8 * state)
        if anim != 0:
            looping = mem.u32(o + AP_STATE_FLAGS + 8 * state) & SF_LOOPING
            mode = 3 if looping else 6
            if MUTATION == 'autoprop_mode_swapped':
                mode = 6 if looping else 3
            self.anim_push(o + AP_ANIM, anim, mode)
            self.anim_jump_top_to_end(o + AP_ANIM)
            state = s32(mem.u32(o + AP_STATE))
            length = self.clip_length(mem.u32(o + AP_ANIMS + 8 * state))
            mem.w32(o + AP_COUNTER, mem.u32(o + AP_COUNTER) + length + 1)
        state = s32(mem.u32(o + AP_STATE))
        self.virtual(o, SLOT_SET_PASSABLE, mem.u32(o + AP_STATE_FLAGS + 8 * state) & SF_PASSABLE)
        return 0

    def autoprop_set_passable(self, o, on):
        """AutoProp_setPassable 0x23d7ac (slot 19).  on: object flag 0x1 set; off: cleared.
        Only an AutoDoor (+0x11c & 1) also changes its level piece +0x18c in the world
        0x44fdc8: collision off and moved to (0, 0, -256) when on, collision on and moved
        to (0, 0, 0) when off."""
        mem = self.mem
        on = on & M32
        if MUTATION == 'passable_inverted':
            on = 0 if on else 1
        door = mem.u32(o + AP_KIND) & AK_DOOR
        world = mem.u32(G_WORLD)
        if on:
            if door:
                self.world_set_piece_collision(world, mem.u32(o + AP_PIECE), 0)
                self.log('world_movePiece', mem.u32(G_WORLD), mem.u32(o + AP_PIECE), (F_0, F_0, F_MINUS_256), 0)
            mem.w32(o + O_FLAGS, mem.u32(o + O_FLAGS) | OF_NOCOLLIDE)
        else:
            if door:
                self.world_set_piece_collision(world, mem.u32(o + AP_PIECE), 1)
                self.log('world_movePiece', mem.u32(G_WORLD), mem.u32(o + AP_PIECE), (F_0, F_0, F_0), 0)
            mem.w32(o + O_FLAGS, mem.u32(o + O_FLAGS) & ~OF_NOCOLLIDE & M32)
        return 0

    def world_set_piece_collision(self, world, piece, on):
        """0x182b00 (world, piece, on): a negative piece does nothing; else the chunk of
        piece record +0x18 (pieces 28 bytes at world +0x54, chunks 36 bytes at world +0x20)
        gets bit 0x2 of its u16 +0x10 cleared (on) or set (off)."""
        mem = self.mem
        piece = s32(piece)
        if piece < 0:
            return
        record = (mem.u32(world + 0x54) + piece * 28) & M32
        chunk = (mem.u32(world + 0x20) + s16(mem.u16(record + 0x18)) * 36) & M32
        value = mem.u16(chunk + 0x10)
        mem.w16(chunk + 0x10, value & 0xFFFD if on else value | 2)

    def model_build_hide_mask(self, model, bits):
        """model_buildHideMask 0x179550 (model, bits) -> 64-bit mesh mask: ~(model +8);
        when the model's u16 +0x10 has 2 and bits != 0, for each set bit k (low first) the
        k-th 16-byte record from model + 16 * u8(+0x21) ORs in its first word and clears
        its second.  bits is shifted as a 32-bit value (srl)."""
        mem = self.mem
        result = ~mem.u64(model + 8) & M64
        if not mem.u16(model + 0x10) & 2 or bits == 0:
            return result
        record = (model + mem.u8(model + 0x21) * 16) & M32
        while True:
            if bits & 1:
                result = (result | mem.u64(record)) & ~mem.u64(record + 8) & M64
            bits = sext32((bits & M32) >> 1)
            record = (record + 16) & M32
            if bits == 0:
                return result

    # ---- animation state (the bytes of the three functions the bodies call) ---------------------
    def anim_push(self, state, clip, mode):
        """anim_push 0x170838 (state, clip, flags): nothing for a null clip or a full state
        (s8 count +4 >= s8 capacity +5); else the next 32-byte track (state + 8 + 32 count)
        gets the clip, time 0, weight 1.0 / rate 0 / target 1.0 / life 0, flags; the state's
        u16 +6 ORs in the flags; a decoder slot the track still held is released."""
        mem = self.mem
        if clip == 0:
            return 0
        count, capacity = mem.s8(state + 4), mem.s8(state + 5)
        track = (state + count * 32 + 8) & M32
        if not count < capacity:
            return 0
        mem.w8(state + 4, mem.u8(state + 4) + 1)
        flags = (mem.u16(state + 6) | mode) & 0xFFFF
        old = mem.u32(track + 4)
        mem.w32(track, clip)
        mem.w16(state + 6, flags)
        mem.w32(track + 0x18, 0)
        mem.w16(track + 0x1E, 0)
        if old:
            mem.w32(old + 0x14, 0)
            mem.w32(track + 4, 0)
        mem.w16(track + 0x1C, mode)
        mem.w32(track + 0xC, F_0)
        mem.w32(track + 0x8, F_1)
        mem.w32(track + 0x10, F_1)
        mem.w32(track + 0x14, F_0)
        return 0

    def anim_jump_top_to_end(self, state):
        """anim_jumpTopToEnd 0x170bc8 (state): a cache pointer at +0 is dropped (it and
        its +0x610 zeroed); the top track's time +0x18 = float(clip length +4)."""
        mem = self.mem
        cache = mem.u32(state)
        if cache:
            mem.w32(state, 0)
            mem.w32(cache + 0x610, 0)
        count = mem.s8(state + 4)
        if count == 0:
            return 0
        track = (state + (count - 1) * 32 + 8) & M32
        length = C.from_int(s32(self.clip_length(mem.u32(track))))
        flags = mem.u16(track + 0x1C)
        mem.w32(track + 0x18, length)
        if flags & 0x800:
            raise HostFault('anim_jumpTopToEnd on a track with flag 0x800 calls animtrack_decode 0x16e468 '
                            '(not modelled)')
        return 0

    def anim_start(self, state, clip, flags, blend):
        """anim_start 0x16cfe0 (blend seconds; state, clip, flags): pushes a track that
        fades in at rate 1 / (blend x 60) (1.0 when blend < 1/60; the first track has no
        blend); a full state replaces its top track."""
        mem = self.mem
        if clip == 0:
            return 0
        count, capacity = mem.s8(state + 4), mem.s8(state + 5)
        index = count
        if not count < capacity:
            index = count - 1
            link = (state + 0xC + index * 32) & M32
            held = mem.u32(link)
            if held:
                mem.w32(held + 0x14, 0)
                mem.w32(link, 0)
        if index == 0:
            blend = F_0
        track = (state + index * 32 + 8) & M32
        mem.w8(state + 4, index + 1)
        old_flags = mem.u16(state + 6)
        old = mem.u32(track + 4)
        mem.w32(track, clip)
        mem.w16(state + 6, old_flags | flags)
        mem.w32(track + 0x18, 0)
        mem.w16(track + 0x1E, 0)
        if old:
            mem.w32(old + 0x14, 0)
            mem.w32(track + 4, 0)
        mem.w16(track + 0x1C, flags)
        mem.w32(track + 8, 0)
        rate = F_1
        if not C.lt(blend, F_1_60):
            rate = C.div(F_1, C.mul(blend, F_60))
        mem.w32(track + 0xC, rate)
        mem.w32(track + 0x10, F_1)
        mem.w32(track + 0x14, 0)
        return 0

    # ---- Gnome death ----------------------------------------------------------------------------
    def game_object_rand(self, o):
        """GameObject_rand 0x1509d0: the object's own LCG at +0x44 (x 0x19660d +
        0x3c6ef35f), result the high 16 bits.  Not the shared seed."""
        value = (self.mem.u32(o + C_RAND) * 0x19660D + 0x3C6EF35F) & M32
        self.mem.w32(o + C_RAND, value)
        return value >> 16

    def creature_state_gate(self, o, state):
        """0x10a9c0 (creature, &state) -> (refuse, state), for state 0x14 only.  Refuses (1)
        when the arena flag 0x4f7120 is set, 0x4f711c is 0, 0x503890 is set and 0x503894 is
        0; or when the hidden byte +0x231 is set and the state is 1.  State 0x14 zeroes the
        root, attack, +0x31a and stun timers; the three timer tests then pass (the attack
        test stores 0 into +0x318 again when +0x234 is 0) and the gate returns 0."""
        mem = self.mem
        if state != STATE_DEAD:
            raise HostFault('creature state gate for state 0x%x is not modelled' % state)
        if mem.u32(G_ARENA) != 0 and mem.u32(G_ARENA_B) == 0:
            if mem.u32(G_GATE_C) != 0 and mem.u32(G_GATE_D) == 0:
                return 1, state
        for field in (C_STUN, C_ATTACK, C_ROOT, C_T31A):
            mem.w16(o + field, 0)
        # Creature_isNotRooted (lh +0x314 == 0) and Creature_isNotStunned (lh +0x31c == 0) pass
        if mem.u32(o + C_TARGET) == 0:          # Creature_isAttackReady 0x1195f0
            mem.w16(o + C_ATTACK, 0)
        return 0, state

    def gnome_set_state(self, o, state):
        """Gnome_setState 0x269bb4 (slot 27 of Gnome 0x5103a8), state 0x14 (the state
        killMonster asks for): the gate; if it refuses, nothing more.  Else one draw of the
        object's own generator picks death animation (draw & 3) from the class definition
        (+0x24) +0xa4 + 8k, anim_start(0.1 s, +0x114, it, 6), slot 28 (on death, 0), and
        the s16 AI state +0x232 = 0x14."""
        mem = self.mem
        state &= M32
        refuse, state = self.creature_state_gate(o, state)
        if refuse:
            return refuse
        if state != STATE_DEAD:
            raise HostFault('Gnome_setState case 0x%x is not modelled' % state)
        pick = self.game_object_rand(o) & 3
        if MUTATION == 'gnome_anim_first':
            pick = 0
        clip = mem.u32(mem.u32(o + C_CLASS) + CLASS_DEATH_ANIMS + 8 * pick)
        self.anim_start(o + C_ANIM, clip, 6, F_0_1)
        self.virtual(o, SLOT_ON_DEATH, 0)
        mem.w16(o + C_AI_STATE, state)
        return 0

    def prop_str(self, o, key_addr):
        """obj_getPropStr 0x14f4c0 (obj, key, 0): with a property list, the key string is
        lower-cased IN PLACE (every byte stored), then the value of the first 'key=' entry
        or None.  Without a list nothing is stored."""
        mem = self.mem
        obj = self.game.obj_at(o)
        if mem.u32(o + O_PROPS) == 0:
            return None
        key = mem.cstr(key_addr)
        mem.write(key_addr, bytes(c + 0x20 if 65 <= c <= 90 else c for c in key))
        return O.props_find(obj.props, key.lower())

    def creature_on_death(self, o, arg):
        """Creature_onDeath 0x10beb8 (slot 28; Gnome inherits it): clears creature flags
        0x8c00000 (+0xa8 &= 0xfffffffff73fffff); runs the 'deathScript' property through
        script_runByName with g_scriptSelectedObj 0x4039f8 = the creature, then sets
        g_scriptSelectedObj to 0 (not back to what it was); arg 0: a 'dropitem' property
        spawns that item; object flag 0x2: flag 0x4000, animation to its end and
        obj_delete; arena 0x4f7120: arena_addKill; then creature_stopBossMusic."""
        mem, game = self.mem, self.game
        mem.w64(o + C_FLAGS64, mem.u64(o + C_FLAGS64) & DEATH_CFLAGS_KEEP)
        script = self.prop_str(o, S_DEATH_SCRIPT)
        if script is not None and MUTATION != 'kill_no_deathscript':
            mem.w32(G_SELECTED_OBJ, o)
            game.run_script(bytes(script))
            if MUTATION != 'kill_keeps_selected':
                mem.w32(G_SELECTED_OBJ, 0)
        if arg == 0:
            item = self.prop_str(o, S_DROP_ITEM)
            if item is not None:
                self.log('loot_spawnNamedItem', tuple(mem.u32(o + O_POS + 4 * k) for k in range(3)), bytes(item))
        flags = mem.u32(o + O_FLAGS)
        if flags & OF_DELETE_ON_DEATH:
            mem.w32(o + O_FLAGS, flags | OF_4000)
            self.anim_jump_top_to_end(o + C_ANIM)
            self.log('obj_delete', o)
        if mem.u32(G_ARENA) != 0:
            owner = mem.u32(o + C_OWNER)
            self.log('arena_addKill', mem.u32(owner + 0xC) if owner else 0, 0)
        if self.log('creature_bossMusicName', o) != 0:          # creature_stopBossMusic 0x1192f8
            self.log('stream_queueStop', 2)
        return 0

    # ---- sound -----------------------------------------------------------------------------------
    def game_is_frozen(self):
        """game_isFrozen 0x1ebdf8."""
        mem = self.mem
        if mem.s8(G_NETWORK_MODE) != 0:
            return mem.u32(G_PAUSED)
        if mem.s8(G_CUTSCENE_ACTIVE) != 0:
            return mem.u32(G_FREEZE_B)
        if self.log('task_isRunning', mem.cstr(S_PLAYER_SELECTION)) != 0:
            if s32(mem.u32(G_FRAME_COUNT)) < 60:
                return 0
        if mem.u32(G_PAUSED) != 0 or mem.u32(G_FREEZE_B) != 0:
            return 1
        if mem.s8(G_FREEZE_C) == 0:
            return 0
        if self.log('dialog_isOpen') != 0:
            return 0
        if mem.s8(G_CUTSCENE_ACTIVE) != 0:
            return 0
        return 1

    def sound_play_on_object(self, sequence, obj, volume):
        """sound_playOnObject 0x214230 (volume; sequence, object) -> handle or -1, for
        object 0 (the only form soundSequence uses).  A null sequence gives -1.  All 32
        players at 0x871a68 are scanned: the LAST free one (s8 +4 == 0) is taken; every
        busy player of the same group (sequence u8 +0x3c) counts, and for a non-zero group
        reaching the cap s8 0x4f8a28[group] gives -1.  The player: u16 +6 = 0, the sequence
        pushed on its animation state (flags 4), +0x3a = 1 (no object), +0x38 = serial
        0x4f8950 (which becomes (serial + 1) & 0x7f), +0x3b = game_isFrozen(), +0x3c = 0,
        +0x40 volume, +0x44 360.0, +0x48 840.0.  Handle = player | serial << 8 | 0x8000."""
        mem = self.mem
        if sequence == 0:
            return M32
        group = mem.u8(sequence + 0x3C)
        slot, counted = -1, 0
        for index in range(SOUND_SEQS):
            player = G_SOUND_SEQS + SOUND_SEQ_SIZE * index
            if mem.s8(player + 4) == 0:
                slot = index
                if MUTATION == 'sound_first_free':
                    break
                continue
            if mem.u8(mem.u32(player + 8) + 0x3C) != group:
                continue
            counted += 1
            if group != 0 and not counted < mem.s8(G_SOUND_GROUP_CAP + group):
                return M32
        if slot == -1:
            return M32
        if obj != 0:
            raise HostFault('sound_playOnObject on an object (handle link) is not modelled')
        player = G_SOUND_SEQS + SOUND_SEQ_SIZE * slot
        mem.w16(player + 6, 0)
        self.anim_push(player, sequence, 4)
        mem.w8(player + 0x3A, 1)
        frozen = self.game_is_frozen()
        serial = mem.u16(G_SOUND_SERIAL)
        mem.w16(player + 0x38, serial)
        mem.w16(G_SOUND_SERIAL, (serial + 1) & 0x7F)
        mem.w8(player + 0x3B, frozen)
        mem.w8(player + 0x3C, 0)
        mem.w32(player + 0x40, volume)
        mem.w32(player + 0x44, F_360)
        mem.w32(player + 0x48, F_840)
        return (slot | (serial & 0xFFFF) << 8 | 0x8000) & M32

    def sound_set_plays_while_frozen(self, handle):
        """sound_setPlaysWhileFrozen 0x216ad0 (handle): for a handle other than -1 with bit
        0x8000, player (handle & 0xff) byte +0x3b = 1."""
        if handle != M32 and handle & 0x8000:
            self.mem.w8(G_SOUND_SEQS + SOUND_SEQ_SIZE * (handle & 0xFF) + 0x3B, 1)
        return 0

    # ---- resources ---------------------------------------------------------------------------------
    def lump_load(self, name):
        """lump_load 0x173558 (name) -> data.  A loaded lump (lump_findLoaded) is returned
        with nothing stored.  Otherwise cd_findFile; a missing file prints and stores to
        address 0 (0x17363c).  A found file: lump_prepare, a block of (size rounded up to
        2048) + 0x100 bytes tagged 0x7b9480 + 40 x (0x41bf7c), a blocking read, the
        pending data / size / flag at 0x41bfa0 / 0x41bfa4 / 0x41bf9d, the name copied to
        0x7c25c8, lump_pollAsync, 0x41bf80 = 0, and lump_findLoaded again."""
        mem = self.mem
        name = bytes(name)
        found = self.log('lump_findLoaded', name)
        if found != 0 and MUTATION != 'lump_skip_loaded_check':
            return found
        exists, size = self.log('cd_findFile', name)
        if not exists:
            self.log('dbg_printf', S_LUMP_NOT_FOUND)
            raise HostFault('lump_load of a file the disc does not have: the original stores to address 0')
        self.log('lump_prepare', name)
        tag = (G_LUMP_TAGS + s32(mem.u32(G_LUMP_TAG_INDEX)) * 40) & M32
        block = self.log('mem_allocTagged', (((size + 0x7FF) & ~0x7FF) + 0x100) & M32, tag)
        self.log('cd_readBlocking', name, block, 0, 0)
        mem.w32(G_LUMP_PENDING_DATA, block)
        mem.w32(G_LUMP_PENDING_SIZE, size)
        mem.w8(G_LUMP_PENDING_FLAG, 1)
        mem.strcpy(G_LUMP_PENDING_NAME, name)
        self.log('lump_pollAsync')
        mem.w32(G_LUMP_PENDING_CLEAR, 0)
        return self.log('lump_findLoaded', name)


def autoprop_kind(props):
    """The AutoProp fields a constructor derives from the property keys that matter to
    setState, as docs/monsters-2.md 'AutoProp' lists them (ctor 0x23c44c; not executed
    here): (+0x11c mask, States, state flags per state).  Keys are compared lower-case,
    as the shipped objects write them."""
    kv = {}
    for entry in props:
        key, _sep, value = bytes(entry).partition(b'=')
        kv[key.lower()] = value
    mask = 0
    for key, bit in ((b'autodoor', 1), (b'autoswitch', 2), (b'breakable', 4), (b'crumble', 8),
                     (b'pokeable', 0x10), (b'triggerable', 0x40), (b'loopingstate', 0x80),
                     (b'removechunks', 0x100)):
        if O.atoi(kv.get(key, b'0')):
            mask |= bit
    states = O.atoi(kv.get(b'states', b'0'))
    flags = [0] * 10
    for key, bit in ((b'passable', 1), (b'loopinganimation', 2), (b'nomessage', 4), (b'actionatend', 8)):
        text = kv.get(key, b'')
        for index, char in enumerate(text[:10]):
            if char == 0x31:
                flags[index] |= bit
    return mask, states, flags
