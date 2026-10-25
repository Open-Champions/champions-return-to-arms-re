#!/usr/bin/env python3
"""ref_items_gaps.py - reference contract for two loose ends of docs/script-items.md
(docs/spec/items-gaps.md sections 1 and 2).

  1. Who sets the host bit (bit 0 of the net settings byte 0x402a30) that guards launch
     record +0xa0..+0xa3 and +0xf4, and how every machine consumes +0xf4:
       lobby_task           0x3276a4-0x327728  own number, player count, host bit, kind bits
       frontend_run         0x1e1b6c-0x1e1b90  menu path: difficulty 1, mode 0, host bit
       frontend_run         0x1e0d2c-0x1e0d5c  kind bits 2 / 4, byte +0x0a = 0xff
       net_launchPrepare    0x1351d8-0x135208  own launch record = 0x402b90 + own * 0x144
                            0x1353f4-0x135430  host only: +0xa0..+0xa3 and +0xf4
       net_launchUpdate     0x137464-0x137518  end of launch: record 0 -> difficulty,
                                               kill limit, mode flags, game_set4f7110
  2. The load-limit bonus word 0x4d8ae8: no writer (the constants below are the evidence
     trail only; the model treats the word as the value the caller supplies).

Every function here works on a memory with load/store (the ref_natives.Mem interface) and
returns the calls it would make.  Nothing from the game is in this file: addresses,
offsets and the order of operations only.
"""
M32 = 0xFFFFFFFF

# ---- the net settings block 0x402a30 (0x14c bytes, docs/ui.md) ----------------------------
SETTINGS = 0x402A30
S_FLAGS = 0x00          # u8: bit 0 host, bit 1 / bit 2 kind of character (2 or 4)
S_DIFFICULTY = 0x02     # u8
S_MODE = 0x03           # u8
S_MISSION = 0x04        # u8
S_KILL_LIMIT = 0x05     # u8
S_COUNT = 0x07          # s8 player count
S_OWN = 0x09            # s8 this machine's player number
S_0A = 0x0A             # u8, set to 0xff with the kind bits (meaning unknown)
FLAG_HOST, FLAG_KIND_A, FLAG_KIND_B = 0x01, 0x02, 0x04

G_LOBBY_CTX = 0x50613C  # word: the lobby context lobby_task reads (own number at +0xc80)
LOBBY_OWN = 0xC80       # s8 own number in the lobby context
LOBBY_ROOM = 0x9C       # room settings at ctx + 0x9c: +0xa2 difficulty, +0xa4 mode,
ROOM_DIFFICULTY, ROOM_MODE, ROOM_KILL_LIMIT, ROOM_MISSION = 0xA2, 0xA4, 0xA6, 0xA8  # +0xa6, +0xa8
G_CHAR_KIND = 0x4FDBA9  # u8: & 3 non-zero -> kind bit 4, else kind bit 2

# ---- launch records ------------------------------------------------------------------------
LAUNCH_RECS, LAUNCH_REC_SIZE = 0x402B90, 0x144   # g_launchRecs, 4 records
R_DIFFICULTY, R_MODE, R_KILL_LIMIT, R_MISSION = 0xA0, 0xA1, 0xA2, 0xA3
R_CM1 = 0xF4

# ---- what the receiver writes ----------------------------------------------------------------
G_DIFFICULTY = 0x4F719C     # g_difficultyIdx (s32)
G_KILL_LIMIT = 0x4F8408     # u8
G_PVP_MODE_A = 0x4F711C     # s32: mode 2 or 3
G_PVP_MODE_B = 0x4F7120     # s32: mode 1, 2 or 3
G_MODE_3 = 0x4F7124         # s32: mode 3 (signed byte compare)

# ---- callees ---------------------------------------------------------------------------------
GAME_SCAN_CM1 = 0x1EB950    # game_scanCm1Vars(recompute)
GAME_SET_CM1 = 0x1EC830     # game_set4f7110(value)

# ---- 0x4d8ae8 (section 2) --------------------------------------------------------------------
G_LOAD_BONUS = 0x4D8AE8
LOAD_BONUS_READER = 0x1B69E0    # the one instruction in any loaded segment that forms it


def s8(v):
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def own_record(own):
    """net_launchPrepare 0x1351d8-0x135208: the record this machine fills (own is s8)."""
    return (LAUNCH_RECS + s8(own) * LAUNCH_REC_SIZE) & M32


def lobby_set_host(mem):
    """lobby_task 0x3276a4-0x327728.  Returns []: no calls."""
    ctx = mem.u32(G_LOBBY_CTX)
    own_byte = mem.u8(ctx + LOBBY_OWN)
    count = s8(mem.u8(SETTINGS + S_COUNT))
    mem.w8(SETTINGS + S_OWN, own_byte)
    if not s8(own_byte) < count:
        mem.w8(SETTINGS + S_COUNT, own_byte + 1)
    mem.w8(SETTINGS + S_FLAGS, 0)                      # always, in the branch's delay slot
    if s8(mem.u8(SETTINGS + S_OWN)) == 0:
        room = ctx + LOBBY_ROOM
        mem.w8(SETTINGS + S_DIFFICULTY, mem.u8(room + ROOM_DIFFICULTY))
        mem.w8(SETTINGS + S_MODE, mem.u8(room + ROOM_MODE))
        mem.w8(SETTINGS + S_KILL_LIMIT, mem.u8(room + ROOM_KILL_LIMIT))
        mem.w8(SETTINGS + S_FLAGS, FLAG_HOST)
        mem.w8(SETTINGS + S_MISSION, mem.u8(room + ROOM_MISSION) + 1)
    flags = mem.u8(SETTINGS + S_FLAGS)
    flags |= FLAG_KIND_B if mem.u8(G_CHAR_KIND) & 3 else FLAG_KIND_A
    mem.w8(SETTINGS + S_FLAGS, flags)
    return []


def frontend_set_host(mem, selection):
    """frontend_run 0x1e1b6c-0x1e1b90: selection is the menu routine's result (0x1a01d0)."""
    mem.w8(SETTINGS + S_DIFFICULTY, 1)
    mem.w8(SETTINGS + S_MODE, 0)
    mem.w8(SETTINGS + S_FLAGS, 0)
    if selection & 0xFFFFFFFFFFFFFFFF:
        mem.w8(SETTINGS + S_FLAGS, FLAG_HOST)
    return []


def frontend_set_kind(mem):
    """frontend_run 0x1e0d2c-0x1e0d5c."""
    flags = mem.u8(SETTINGS + S_FLAGS)
    mem.w8(SETTINGS + S_0A, 0xFF)
    flags |= FLAG_KIND_B if mem.u8(G_CHAR_KIND) & 3 else FLAG_KIND_A
    mem.w8(SETTINGS + S_FLAGS, flags)
    return []


def launch_fill_host_fields(mem, record, scan_result):
    """net_launchPrepare 0x1353f4-0x135430.  scan_result is what game_scanCm1Vars(1)
    returns.  Returns the calls: [(GAME_SCAN_CM1, 1)] for a host, [] otherwise."""
    if not mem.u8(SETTINGS + S_FLAGS) & FLAG_HOST:
        return []
    mem.w8(record + R_DIFFICULTY, mem.u8(SETTINGS + S_DIFFICULTY))
    mem.w8(record + R_MODE, mem.u8(SETTINGS + S_MODE))
    mem.w8(record + R_KILL_LIMIT, mem.u8(SETTINGS + S_KILL_LIMIT))
    mem.w8(record + R_MISSION, mem.u8(SETTINGS + S_MISSION))
    mem.w32(record + R_CM1, scan_result & M32)
    return [(GAME_SCAN_CM1, 1)]


def launch_receive(mem):
    """net_launchUpdate 0x137464-0x137518: every machine, from record 0 (player number 0,
    the host).  Returns the calls: [(GAME_SET_CM1, +0xf4)] in mode 2 or 3, else []."""
    rec = LAUNCH_RECS
    mode = mem.u8(rec + R_MODE)
    mem.w32(G_DIFFICULTY, s8(mem.u8(rec + R_DIFFICULTY)) & M32)
    mem.w8(G_KILL_LIMIT, mem.u8(rec + R_KILL_LIMIT))
    mem.w32(G_PVP_MODE_A, 0)
    mem.w32(G_PVP_MODE_B, 0)
    mem.w32(G_MODE_3, 0)
    if ((mode - 1) & M32) < 3:
        mem.w32(G_PVP_MODE_B, 1)
    if ((mode - 2) & 0xFF) < 2:
        mem.w32(G_PVP_MODE_A, 1)
    if s8(mode) == 3:
        mem.w32(G_MODE_3, 1)
    if mem.u32(G_PVP_MODE_A):
        return [(GAME_SET_CM1, mem.u32(rec + R_CM1))]
    return []


def cm1_word_after_launch(host_scan, own_word, mode):
    """Composition (Inferred from the fragments above, all executed): the 0x4f7110 word
    each machine holds when the level starts.  A host always has bit 0 (lobby_task gives
    it to player number 0, and the host's number is 0), so record 0 +0xf4 is the host's
    scan.  Only modes 2 and 3 copy it; other modes keep this machine's own word."""
    return host_scan if mode in (2, 3) else own_word
