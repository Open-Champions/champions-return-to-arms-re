#!/usr/bin/env python3
"""ref_wading.py - how a wading player disturbs the water (Champions: Return to Arms,
SLUS_209.73, US v2.00).  docs/spec/player-wading.md is the prose version.

A research tool, not game code.  Standard library only; no game data is embedded (the
two format strings and the lump name are read from the caller's memory at run time).

What it adds (Executed: tools/difftest_wading.py runs the original under tools/ee_emu.py
and compares calls with arguments, every byte stored outside the stack, the shared and
cosmetic seeds and the result)

    WadeModel(ref_combat_move.MoveModel)
        player_move      Player_move 0x1b4020 with water_test 0x189438, water_disturb
                         0x189514 and their chunk query 0x189240 running inside the model
                         (ref_water_services) instead of being call-outs: the water test,
                         the in-water bit, the entry splash and the wading ripple all write
                         the real ripple grid
        player_footstep  Player_footstep 0x1beec8 (boot-item flags, the in-water bit)
        sound_play_foley sound_playFoley 0x1e7c40 (the in-water footstep variant, drawn
                         from the cosmetic seed 0x404460, never from the shared seed)

    Band helpers (pure functions of the executed bodies, for a native port)
        entry_box(pos)          the box water_test queries from Player_move (radius 12)
        wade_box(pos)           the box the wading water_disturb queries (z - 12, radius 12)
        player_wade_constants   every constant of the player's water code with its address

Domain: as ref_combat_move.MoveModel and ref_water_services.Model.  The services refuse
what they refuse (malformed trees, a non-positive rounded chunk width).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_move as MV                    # noqa: E402
import ref_water_services as W                  # noqa: E402

M32 = T.M32
ONE = T.ONE
WATER_BIT = MV.WATER_BIT                        # +0xa8 bit 61: standing in water
G_RAND_SEED = RC.G_RAND_SEED                    # 0x404464, the shared (lockstep) seed
G_COSMETIC_SEED = 0x404460                      # the cosmetic seed sound_playFoley draws
G_PLAYERS = T.G_PLAYERS                         # 0x4d8af0 player records
REC_SIZE = T.REC_SIZE                           # 0x4c30
REC_BOOTS_A = 0x4400                            # record item pointer read first (0x1beef0)
REC_BOOTS_B = 0x4418                            # record item pointer read second (0x1beefc)
FOLEY_DEFAULT = 0x80000                         # flags when neither pointer is set (0x1beef8)
S_FOLEY_LUMP = 0x53D688                         # lump name for res_find (0x1e7cb0, 0x1e7e0c)
S_FOLEY_WATER = 0x53DDD8                        # in-water format, n = 1..2 (0x1e7c80)
S_FOLEY_BY_FLAG = (                             # (flag, format, variants), tested in this order
    (0x400000, 0x53DDE8, 5),                    # 0x1e7cf0 / 0x1e7d14
    (0x200000, 0x53DE00, 5),                    # 0x1e7d28 / 0x1e7d4c
    (0x100000, 0x53DE18, 5),                    # 0x1e7d60 / 0x1e7d88
)
S_FOLEY_PLAIN = 0x53DE30                        # 0x80000 (or any of 0x780000 left), n = 1..4
FOLEY_ANY = 0x780000                            # 0x1e7ce0: none of these bits -> no sound
FOLEY_SILENT = 0x400000                         # result register then: the delay slot 0x1e7cec

FOLEY_EXTERNALS = {
    'res_find': RC.Ext(0x17365C, 'ps', 0, 'i', '(lump name, entry name) -> entry'),
    'sound_playAtPos': RC.Ext(0x214428, 'iv', 1, 'i', '(entry, position copy; volume)'),
}


# Every constant of the player's water code.  (value or None for a call site, address of
# the instruction that loads or tests it, meaning).  Floats are raw32 patterns.  Observed at
# the addresses; the values are Executed through the call arguments (difftest_wading.py,
# difftest_combat_move.py playerMove, difftest_player.py for the two Player_run states).
player_wade_constants = (
    (0x3,        0x1b45c0, 'water_test only on frames with g_simFrame & 3 == 0 (out of water)'),
    (0x41400000, 0x1b45d4, 'water_test radius 12.0; also the disturb point z offset (z - 12.0)'),
    (None,       0x1b4600, 'water_test call (world, copy of position, &height; 12.0)'),
    (None,       0x1b461c, 'one shared-seed draw on entry (0x1b461c-0x1b4654); only the seed'
                           ' word changes'),
    (0x3F800000, 0x1b4668, 'entry splash volume 1.0 when airborne (+0x47c != 0, test 0x1b465c)'),
    (0x453B8000, 0x1b46a8, 'entry ripple strength 3000.0 when airborne'),
    (0x41C00000, 0x1b46cc, 'entry ripple radius 24.0 when airborne (call 0x1b46dc)'),
    (None,       0x1b4704, 'airborne entry: splash burst at (x, y, water height); 1.0'),
    (0x3ECCCCCC, 0x1b4728, 'entry splash volume 0.4 on foot'),
    (0x447A0000, 0x1b475c, 'entry ripple strength 1000.0 on foot'),
    (0x41C00000, 0x1b477c, 'entry ripple radius 24.0 on foot (call 0x1b478c)'),
    (0x1000,     0x1b4440, 'level flag word 0x44fe08 bit 0x1000: water hurts'),
    (0xF,        0x1b4454, 'hurting water: damage_apply on itself (0x1b4490) when frame & 0xf == 0'),
    (0x3C23D70A, 0x1b4498, 'wading: ripple every frame while s >= 0.01'),
    (0xF,        0x1b44b8, 'wading: below s 0.01, ripple only when frame & 0xf == 0'),
    (0x43960000, 0x1b4500, 'wading ripple strength 300.0 (call 0x1b4518; second site 0x1b4564/0x1b457c)'),
    (0x41400000, 0x1b44c4, 'wading ripple radius 12.0 and z offset 12.0 (second site 0x1b4528)'),
    (None,       0x1b45ac, 'no chunk touched by the wading ripple: clear bit 61'),
    (0x41400000, 0x1a5ff4, 'Player_run state 7 (take-off while in water, test 0x1a5fe4): z - 12.0'),
    (0x453B8000, 0x1a6034, 'Player_run state 7 ripple strength 3000.0 (call 0x1a6050)'),
    (0x41C00000, 0x1a6040, 'Player_run state 7 ripple radius 24.0'),
    (0x41400000, 0x1a65dc, 'Player_run state 0xb (block-walk in water, test 0x1a65c8): z - 12.0, r 12.0'),
    (0x447A0000, 0x1a6608, 'Player_run state 0xb ripple strength 1000.0 (call 0x1a662c)'),
)


def entry_box(pos, radius=0x41400000):
    """The box Player_move's water_test queries (water_test 0x18948c-0x1894e0):
    ((x - r) - 1, (y - r) - 1, z - 1) .. ((x + r) + 1, (y + r) + 1, z + 60).  A water
    chunk whose bounding box touches it (inclusive) puts the player in water."""
    x, y, z = pos
    lo = (C.sub(C.sub(x, radius), ONE), C.sub(C.sub(y, radius), ONE), C.sub(z, ONE))
    hi = (C.add(C.add(x, radius), ONE), C.add(C.add(y, radius), ONE), C.add(z, W.F60))
    return lo, hi


def wade_box(pos, radius=0x41400000):
    """The box the wading water_disturb queries: the point is (x - 0.0, y, z - 12.0) and
    water_disturb 0x18953c-0x1895d4 uses (x - r, y - r, z' - 1) .. (x + r, y + r, z' + 60)
    with no one-unit XY padding.  No chunk in it clears the in-water bit."""
    x, y, z = pos
    px, pz = C.sub(x, T.ZERO), C.sub(z, 0x41400000)
    lo = (C.sub(px, radius), C.sub(y, radius), C.sub(pz, ONE))
    hi = (C.add(px, radius), C.add(y, radius), C.add(pz, W.F60))
    return lo, hi


class WadeModel(MV.MoveModel):
    """MoveModel whose water_test / water_disturb run the executed service bodies on the
    same memory (so their grid writes are the model's writes) instead of being call-outs."""

    INTERNAL = dict(MV.MoveModel.INTERNAL)
    INTERNAL.update({'water_test': 'wade_water_test', 'water_disturb': 'wade_water_disturb'})
    node_budget = W.Model.node_budget

    def __init__(self, mem, callbacks=None, external=(), inline_grid=True):
        MV.MoveModel.__init__(self, mem, callbacks, external, inline_grid)
        self.cosmetic_draws = 0

    # ---- the services, composed ------------------------------------------------------
    def query(self, world, lo, hi, capacity, out=None):
        return W.Model.query(self, world, lo, hi, capacity, out)

    def wade_water_test(self, world, pos, height_out, radius):
        """Call shape of MV: (world, position copy, height pointer flag; radius) ->
        (hit, height).  The height slot is the caller's stack local, so the chunk's
        minimum z is returned rather than stored; a miss leaves it unread."""
        lo, hi = entry_box(pos, radius)
        chunks = self.query(world, lo, hi, 2)
        if not chunks:
            return (0, 0) if height_out else 0
        height = self.u32(chunks[0] + 0x10)
        return (1, height) if height_out else 1

    def wade_water_disturb(self, world, pos, strength, radius):
        return W.Model.water_disturb(self, strength, radius, world, pos)

    # ---- the footstep -------------------------------------------------------------------
    def player_footstep(self, P):
        """Player_footstep 0x1beec8: flags = low word of (item + 8) for the first non-null
        of record +0x4400, record +0x4418, else 0x80000; then sound_playFoley(copy of the
        position, bit 61 of +0xa8, 0, flags).  Nothing else; no store, no draw."""
        rec = (G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE) & M32
        item = self.u32(rec + REC_BOOTS_A) or self.u32(rec + REC_BOOTS_B)
        flags = self.u32(item + 8) if item else FOLEY_DEFAULT
        wet = 1 if self.u64(P + 0xA8) & WATER_BIT else 0
        return self.sound_play_foley(self.vec(P + 0x10), wet, 0, flags)

    def _cosmetic_draw(self):
        seed = (self.u32(G_COSMETIC_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_COSMETIC_SEED, seed)
        self.cosmetic_draws += 1
        return seed >> 16

    def sound_play_foley(self, pos, wet, _unused, flags):
        """sound_playFoley 0x1e7c40.  In water: one cosmetic draw, n = (d & 1) + 1, the
        in-water format.  Else no sound unless flags & 0x780000 (and the result register is
        0x400000, left by the branch's delay slot); 0x400000, 0x200000,
        0x100000 (first set wins) take n = d % 5 + 1; otherwise n = (d & 3) + 1.  Then
        res_find(lump, name) and sound_playAtPos(entry, position copy; 1.0)."""
        flags &= M32
        if wet:
            fmt, n = S_FOLEY_WATER, (self._cosmetic_draw() & 1) + 1
        elif not flags & FOLEY_ANY:
            return FOLEY_SILENT
        else:
            for bit, f, variants in S_FOLEY_BY_FLAG:
                if flags & bit:
                    fmt, n = f, self._cosmetic_draw() % variants + 1
                    break
            else:
                fmt, n = S_FOLEY_PLAIN, (self._cosmetic_draw() & 3) + 1
        name = self.cstr_bytes(fmt).replace(b'%d', b'%d' % n, 1)
        entry = self.call('res_find', S_FOLEY_LUMP, name)
        return self.call('sound_playAtPos', entry, tuple(pos), ONE)
