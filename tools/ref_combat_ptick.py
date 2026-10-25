#!/usr/bin/env python3
"""ref_combat_ptick.py - round 2 of the combat contract (docs/combat-runtime.md): the
player's DEFENCE (blocking, Holy Shield, knock-downs, blood, the Resurrect save) and the
REAL player tick as the player's virtual slot 4.  docs/spec/combat-player-defence.md is the
prose; this module adds to tools/ref_combat_runtime.py and changes nothing in it.

A research tool, not game code.  Standard library only; no game data is embedded (the clip
and lump names below are file names the executable exposes, used as identifiers).

What it adds
    DefenceModel (a ref_combat_runtime.CombatModel) - EXECUTED by
    tools/difftest_combat_ptick.py against the original under tools/ee_emu.py:
        player_take_damage_full    Player_takeDamage 0x1b5330 (Player slot 2), with the
                                   block branch (states 8 and 0xb), the in-front block
                                   (sound, Player_blockSparks, the hit halved or zeroed)
                                   and the Holy Shield (mana pays a fraction)
        player_block_sparks        Player_blockSparks 0x1b9658 with silent = 0, the only
                                   argument Player_takeDamage passes (50 sparks, own draws)
        player_process_damage_full Player_processDamage 0x1b2cc0 with the knock-down
                                   (clip by bearing, Player_hasAnim, SkillStrongStance_
                                   trigger when resisted), PvP mode A's halving, blood and
                                   the GutChunk roll, disintegration, the Resurrect save,
                                   the held spell, the arena-lives call-outs (PvP mode B)
    On round 1's domain each _full method makes exactly the calls, stores and draws of
    round 1's method (test_ref_combat_ptick, and the difftest's agreement column).

    TickRuntime (a ref_combat_runtime.Runtime): the player's slot 4 is ref_player.Tick.run
    - the model of all of Player_run 0x1a5030 executed by tools/difftest_player.py - on the
    shared image, instead of round 1's authored driver.  So the per-tick shared-seed draws
    that round 1 omitted are made: the idle voice (0x1a549c) when its counter passes the
    limit +0x4b2, and Player_idleFidget 0x1bc2f8 on every tick with exactly four animation
    tracks (a standing player: player_resetIdleAnim 0x1b2470 leaves four cells).  Every
    call-out of the tick is answered by a model, a labelled fixture or a refusal
    (TickServices); a name can be re-pointed with TickRuntime.plug(name, fn), which is how
    the movement model (tools/ref_combat_move.py) and the melee model
    (tools/ref_combat_melee.py) of the parallel round-2 work are slotted in.

Restricted domain: round 1's (offline, no cutscene, no water, authored floor and
animation), plus what the call-outs refuse; the Runtime keeps refusing every object a
call-out would construct (GutChunk, effects of the Holy Shield, Resurrect and Strong
Stance), the PvP kill credit and Player_interact with something to interact with.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_player as RP                         # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

M32 = T.M32
s8, s16, s32 = T.s8, T.s16, T.s32
ZERO, HALF, ONE = T.ZERO, T.HALF, T.ONE
Unsupported, CompositionError = T.Unsupported, T.CompositionError

F_0_1, F_0_2, F_5, F_10, F_36 = 0x3DCCCCCC, 0x3E4CCCCC, 0x40A00000, 0x41200000, 0x42100000
F_2M16 = 0x37800000                             # 2^-16
F_65536 = 0x47800000
F_0_04 = 0x3D23D70A

S_FX_LUMP = 0x535EF0                            # 'fx.lmp' (address passed to res_find)
NAME_BLOCK_SOUND = 0x5376D0                     # the block sound's name, Player_takeDamage
NAME_SPARK_SOUND = 0x5379C8                     # the block-spark sound's name, Player_blockSparks
KNOCKDOWN_PREFIX = {True: b'knockdown2_', False: b'knockdown1_'}        # 0x537638, 0x537648
G_PROMPT_TIMER, G_PROMPT_OWNER, G_PROMPT_TEXT = 0x4D8AC0, 0x4D8AD0, 0x864F50   # Player_interact
G_SPARK_DEF = 0x8657C0                          # particle definition of the block sparks
G_GUTCHUNK_SIZE = 0x268

G_PVP_MODE_A, G_PVP_MODE_B = T.G_PVP_MODE_A, T.G_PVP_MODE_B
G_SKILL_STRONGSTANCE = T.G_SKILL_STRONGSTANCE
G_NUM_PLAYERS, G_SIM_FRAME = T.G_NUM_PLAYERS, T.G_SIM_FRAME
G_PLAYERS, REC_SIZE, REC_OBJ = T.G_PLAYERS, T.REC_SIZE, T.REC_OBJ


def knockdown_suffix(rel):
    """The bearing letter of a knock-down clip (0x1b2f5c-0x1b2fe8): rel = s16(hit angle
    +0x2e0 - facing +0x38).  'a' for rel < -0x5fff or rel >= 0x6000 (the attacker in
    front, Inferred from the block test), 'c' for -0x5fff..-0x2000, 'b' for -0x1fff..0x2000,
    'd' for 0x2001..0x5fff."""
    if rel < -0x5FFF or rel >= 0x6000:
        return b'a.anm'
    if (rel + 0x6000) & 0xFFFF < 0x4001:
        return b'c.anm'
    if (rel + 0x2000) & 0xFFFF < 0x4001:
        return b'b.anm'
    return b'd.anm'


def knockdown_name(weapon_class, rel):
    """sprintf(prefix) + strcat(suffix) at 0x1b2f0c-0x1b2fe8: 'knockdown2_' for weapon
    animation classes 2 and 3 (record +0x4a86 read unsigned), else 'knockdown1_'."""
    return KNOCKDOWN_PREFIX[((weapon_class & 0xFF) - 2) & M32 < 2] + knockdown_suffix(rel)


class DefenceModel(T.CombatModel):
    """CombatModel with the player's defence bodies.  Player slot 2 (0x1b5330) and the
    direct calls Player_processDamage / Player_blockSparks / Player_hasAnim run the bodies
    below; everything else is round 1's."""

    COMBAT_BODIES = dict(T.CombatModel.COMBAT_BODIES)
    COMBAT_BODIES[0x1B5330] = (2, 'player_take_damage_full')
    INTERNAL = dict(T.CombatModel.INTERNAL)
    INTERNAL.update({'Player_processDamage': 'player_process_damage_full',
                     'Player_takeDamage': 'player_take_damage_full',
                     'Player_blockSparks': 'player_block_sparks', 'Player_interact': 'player_interact'})
    MODELLED = dict(T.CombatModel.MODELLED)
    MODELLED['Player_blockSparks'] = 0x1B9658
    MODELLED['Player_interact'] = 0x1B2640

    # ---- Player_takeDamage 0x1b5330 ------------------------------------------------------
    def player_take_damage_full(self, P, attacker, flags, amount):
        """Player_takeDamage 0x1b5330 (P, attacker, flags; amount), slot 2.

        Round 1's body (docs/combat-runtime.md 6.3) plus, after the hit-immunity test:

        BLOCK - an attacker, action state 8 (block) or 0xb (block move), flags without 0x40:
          state 8 only: ONE SHARED DRAW d (the value s >> 16); the block clip
            anim_startBlendInOut(P+0x114, anim(0x8c), 0x812; 0.1, 0.1) when 0xafc7 < d,
            else anim(0x94) with 0.2, 0.2 (anim(k) = *(P+0x24) + class x 0x68 + k);
          the attacker in front - cos16(facing) x (A.x - P.x) + sin16(facing) x (A.y - P.y)
            > 0, strictly: sound_playAtPos(res_find('fx.lmp', block sound 0x5376d0),
            P.pos; 1.0), Player_blockSparks(P, 0), and the amount becomes amount x 0.5 when
            flags has 0x20000, else 0.  A block from behind changes nothing.
        HOLY SHIELD - the spell looked up on every hit (as round 1); found and record mana
          +0xc0 > 0: frac = SpellHolyShield_absorb(spell) (a call-out; it makes particles and
          maybe a LightEffect); paid = amount x frac; amount -= paid, mana (read again after
          the call) -= paid; each floored at 0.
        Then pending += amount, as round 1."""
        u32 = self.u32
        if self.s8(T.G_RECALL_COUNTDOWN) or self.s16(P + 0x4B4) or u32(P + 0x540):
            return
        if self._cstr(T.G_LEVEL_NAME) == b'actintro':
            return
        if self.call('jumpgate_getTravelState'):
            return
        if u32(T.G_MENU_LOCKOUT) or self.s16(T.G_EXIT_COUNTDOWN):
            return
        slot = self.s32(P + 0x3C8)
        R = (G_PLAYERS + slot * REC_SIZE) & M32
        if self.s8(0x41B69D) and self.call('net_isLocalSlot', slot):
            self.call('gfx_setColorOffset', 0x40, 0, 0, 0)
        slot = self.s32(P + 0x3C8)
        flash = (T.G_HUD_HIT_FLASH + 4 * slot) & M32
        if self.s8(G_PLAYERS + slot * REC_SIZE + 0x4C27) > 0:
            self.w32(flash, u32(flash) | 1)
            return
        state = self.s32(P + 0x58C)
        if attacker and state in (8, 0xB) and not flags & 0x40:
            row = u32(P + 0x24) + 0x68 * self.s8(R + 0x4A86)
            if self.s32(P + 0x58C) != 0xB:
                d = self.draw()
                if 0xAFC7 < d:
                    self.call('anim_startBlendInOut', P + 0x114, u32(row + 0x8C), 0x812, F_0_1, F_0_1)
                else:
                    self.call('anim_startBlendInOut', P + 0x114, u32(row + 0x94), 0x812, F_0_2, F_0_2)
            fx, fy = C.cos16(self.s16(P + 0x38)), C.sin16(self.s16(P + 0x38))
            dx = C.sub(u32(attacker + 0x10), u32(P + 0x10))
            dy = C.sub(u32(attacker + 0x14), u32(P + 0x14))
            if C.lt(ZERO, C.add(C.mul(fx, dx), C.mul(fy, dy))):
                entry = self.call('res_find', S_FX_LUMP, NAME_BLOCK_SOUND)
                self.call('sound_playAtPos', entry, self.vec(P + 0x10), ONE)
                self.call('Player_blockSparks', P, 0)
                amount = C.mul(amount, HALF) if flags & 0x20000 else ZERO
        spell = self.call('creature_findSpellByType', P, self.call('SpellHolyShield_typeinfo'))
        if spell and C.lt(ZERO, u32(R + 0xC0)):
            frac = self.call('SpellHolyShield_absorb', spell)
            paid = C.mul(amount, frac)
            amount = C.sub(amount, paid)
            mana = C.sub(u32(R + 0xC0), paid)
            self.w32(R + 0xC0, mana)
            if C.lt(amount, ZERO):
                amount = ZERO
            if C.lt(mana, ZERO):
                self.w32(R + 0xC0, ZERO)
        self.w32(P + 0xC8, C.add(u32(P + 0xC8), amount))
        df = u32(P + 0x2DC) | flags
        self.w32(P + 0x2DC, df)
        if attacker:
            if not df & 0x800000:
                angle = C.atan2_16(C.sub(u32(P + 0x10), u32(attacker + 0x10)),
                                   C.sub(u32(P + 0x14), u32(attacker + 0x14)))
                self.w16(P + 0x2E0, 0x4000 - angle)
            self.call('handle_clear', P + T.H_LAST_ATTACKER)
            src = attacker
            if u32(attacker + 0xC) & T.F_OWNED:
                node = u32(attacker + T.H_OWNER)
                if node:
                    src = u32(node + 0xC)
            elif flags & 0x10000000:
                node = u32(P + T.H_STATUS_SOURCE)
                if node:
                    src = u32(node + 0xC)
            if src:
                self.call('handle_link', P + T.H_LAST_ATTACKER, src, src)
        if C.lt(ZERO, u32(P + 0xC8)):
            slot = self.s32(P + 0x3C8)
            flash = (T.G_HUD_HIT_FLASH + 4 * slot) & M32
            self.w32(flash, u32(flash) | 1)

    # ---- Player_blockSparks 0x1b9658 -----------------------------------------------------
    def player_block_sparks(self, P, silent):
        """Player_blockSparks 0x1b9658 (P, silent), silent = 0 (the call from
        Player_takeDamage 0x1b5604; the other caller, 0x152fa8, is not in the domain).

          sound_playOnObject(res_find('fx.lmp', spark sound 0x5379c8), the record's
            object R+0x43d8; 1.0) - the real player even when P is the prediction copy;
          the two hand points model_getAttachPoint(P+0x544 model, P.pos, facing, P+0x114,
            index 0 / 1; 1.0) and their midpoint M = (h0 + h1) x 0.5;
          velocity V = (cos16(facing) x 10, sin16(facing) x 10, 10); then 50 times: a point
            of the unit ball from triples of OWN draws (GameObject_rand on P; component =
            2 x (draw x 2^-16) - 1, again while 1 < |v|^2), V += v x 5 - the velocity is
            NOT reset between sparks, it walks - and particle_spawn(0x8657c0, M, V; 0.0).
        So every blocked hit from the front advances P's own seed by at least 150 draws.
        silent != 0 draws the shared seed over model sample points: refused."""
        u32 = self.u32
        if silent:
            raise Unsupported('Player_blockSparks with silent != 0 (shared draws over sample points)')
        R = self._rec(P)
        entry = self.call('res_find', S_FX_LUMP, NAME_SPARK_SOUND)
        self.call('sound_playOnObject', entry, u32(R + REC_OBJ), ONE)
        hands = []
        for index in (0, 1):
            out = self.call('model_getAttachPoint', u32(P + 0x544), self.vec(P + 0x10), self.s16(P + 0x38) & M32,
                            P + 0x114, index, 0, ONE)
            hands.append(out)
        mid = tuple(C.mul(C.add(hands[0][i], hands[1][i]), HALF) for i in range(3))
        vel = [C.mul(C.cos16(self.s16(P + 0x38)), F_10), C.mul(C.sin16(self.s16(P + 0x38)), F_10), F_10]
        for _spark in range(50):
            while True:
                v = []
                for _axis in range(3):
                    u = C.mul(C.from_int(self.obj_rand(P)), F_2M16)
                    v.append(C.sub(C.add(u, u), ONE))
                size = C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))
                if not C.lt(ONE, size):
                    break
            vel = [C.add(vel[i], C.mul(v[i], F_5)) for i in range(3)]
            self.call('particle_spawn', G_SPARK_DEF, mid, tuple(vel), ZERO)

    def player_has_anim(self, P, name):
        """Player_hasAnim 0x1bf230 (ref_player.Tick.has_anim, executed by
        tools/difftest_player.py): res_find in the lump the animation table's first word
        names, then whether one of the +0x118 tracks plays that entry."""
        anm = self.call('res_find', self.u32(self.u32(P + 0x24)), name)
        for i in range(max(self.s8(P + 0x118), 0)):
            if self.u32(P + 0x11C + 0x20 * i) == (anm & M32):
                return 1
        return 0

    # ---- Player_interact 0x1b2640 ---------------------------------------------------------
    def player_interact(self, P, pad, display_only):
        """Player_interact 0x1b2640 (P, pad, displayOnly), restricted to the case of NOTHING
        to interact with and displayOnly 0 - what Player_run (0x1a5c18) passes every tick
        outside menus and dialogs for the real player.

        Nothing in a vehicle (+0x540), with record hp <= 0, or without a record object.
        One box query around the RECORD's object o = R+0x43d8: (o.x - 48, o.y - 48, o.z) to
        (o.x + 48, o.y + 48, o.z + 60), limit 0x100; the candidates are the objects with
        flag 0x100000, nearest in 3-D first (below 1e7 squared) - one found is refused (the
        interaction itself is not modelled).  With none: the slot's prompt timer
        0x4d8ac0[slot] -= 7; at or below 0: 0x4d8ad0[slot] = 0, the timer = 0, and the
        first two halfwords of the slot's prompt text 0x864f50 + slot x 0x200 = 0.
        (These words are written on every tick of a real player; who reads them is not
        established - the HUD prompt, Inferred.)"""
        u32 = self.u32
        if display_only:
            raise Unsupported('Player_interact with displayOnly (the HUD caller)')
        if u32(P + 0x540):
            return
        R = self._rec(P)
        if C.le(u32(R + 0xAC), ZERO):
            return
        o = u32(R + REC_OBJ)
        if not o:
            return
        ox, oy, oz = self.vec(o + 0x10)
        found = self.call('world_collectObjectsInBox', (C.sub(ox, 0x42400000), C.sub(oy, 0x42400000), oz),
                          (C.add(ox, 0x42400000), C.add(oy, 0x42400000), C.add(oz, 0x42700000)), 0x100)
        best, nearest = -1, 0x4B189680
        for i, obj in enumerate(found):
            if not u32(obj + 0xC) & 0x100000:
                continue
            dx, dy, dz = (C.sub(u32(obj + 0x10 + 4 * k), (ox, oy, oz)[k]) for k in range(3))
            d = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
            if C.lt(d, nearest):
                nearest, best = d, i
        if best != -1:
            raise Unsupported('Player_interact with an interactable object (flag 0x100000) in reach')
        slot = self.s32(P + 0x3C8)
        timer = (G_PROMPT_TIMER + 4 * slot) & M32
        t = s32(u32(timer) - 7)
        self.w32(timer, t)
        if t <= 0:
            self.w32(G_PROMPT_OWNER + 4 * slot, 0)
            self.w32(timer, 0)
            text = (G_PROMPT_TEXT + 0x200 * slot) & M32
            self.w16(text, 0)
            self.w16(text + 2, 0)

    # ---- Player_processDamage 0x1b2cc0 ---------------------------------------------------
    def player_process_damage_full(self, P):
        """Player_processDamage 0x1b2cc0 (P).  Round 1's A-E (docs/combat-runtime.md 6.4)
        with the parts round 1 refused:

        B' PvP mode A: no knock-back class -> on to C; else level - 1 and speed +0x2e8 x 0.5
           (before the block test).  Level >= 2 after the block test, the KNOCK-DOWN: the
           name knockdown_name(record +0x4a86, rel) (rel = s16(+0x2e0 - facing));
           resisted: +0x2e8 = 0 after, for the real player, SkillStrongStance_trigger(
           g_skillStrongStance, P, name, trunc(+0x2e8)) (the copy only zeroes the speed);
           not resisted (action state 3 was set first): unless Player_hasAnim(P, name), the
           top-track fix-up and anim_startBlendInOut(P+0x114, res_find(*(*(P+0x24)), name),
           0x80a; 0.1, 0.1).  The flag 0x400000 does not stop a knock-down clip.
        C' with flags & 0xd and (g_decalDetail > 0 or a net game): g_decalDetail > 0:
           fx_spawn(0, (P.x, P.y, P.z + 36)); the real player only: ONE SHARED DRAW, and on
           (draw & 7) == 0 pool_new(0x268) and, when that gave a block, GutChunk_ctor(block,
           point, 2, 1; 1.0).  Flags & 0x10 and record hp <= 0: fx_disintegrateModel(P,
           P+0x544, P+0x114, P.pos, facing, 0; 1.0), and on as before.
        D' the Resurrect save: the spell found and g_numPlayers == 1 exactly: record hp =
           SpellResurrect_onOwnerDeath(spell); still above 0: flags dropped, return (no E).
           A held spell (+0x588 node -> object): its slot 1 (table at +0x14) with 3.  PvP
           mode A: no shout from the other player; the kill credit when the last attacker
           is a player is refused (mana, a skill 0x3b orb: a pool object); PvP mode B:
           arena_onPlayerKilled(slot, last attacker) or arena_loseLife(slot)."""
        u32 = self.u32
        R = self._rec(P)
        if not u32(P + 0x2DC) & 0x20000000 and (self.s8(T.G_CUTSCENE_ACTIVE) or self.call('dialog_isOpen')):
            self.w32(P + 0x2DC, 0)
            self.w32(P + 0xC8, 0)
            return
        df = u32(P + 0x2DC)
        rel = s16(self.u16(P + 0x2E0) - self.u16(P + 0x38))
        level = resist = 0
        state = self.s32(P + 0x58C)
        if df & 0x3C0000 and state not in (6, 10):
            rank = self.vcall(P, 39, 0x3E)
            pct = s32(self.call('SkillStrongStance_getStat0', u32(G_SKILL_STRONGSTANCE), rank))
            df = u32(P + 0x2DC)
            resist = 1 if (self.draw() % 100) < pct else 0
            for bit, speed, lv in ((0x40000, 0x42C80000, 1), (0x80000, 0x43160000, 2),
                                   (0x100000, 0x43480000, 3), (0x200000, 0x437A0000, 3)):
                if df & bit:
                    self.w32(P + 0x2E8, speed)
                    level = lv
                    break
        if u32(G_PVP_MODE_A) and level:
            level -= 1
            self.w32(P + 0x2E8, C.mul(u32(P + 0x2E8), HALF))
        if level > 0:
            if self.s32(P + 0x58C) == 8 and not -0x5FFF <= rel < 0x6000:
                level -= 1
            small = level < 2
            if small or not resist:
                self._set_state3(P)
            if small:
                if not u32(P + 0x2DC) & 0x400000:
                    self._track_fixup(P)
                    self._reaction_clip(P)
            else:
                name = knockdown_name(self.u8(R + 0x4A86), rel)
                if resist:
                    if not u32(P + 0xC) & T.F_PREDICTION_COPY:
                        self.call('SkillStrongStance_trigger', u32(G_SKILL_STRONGSTANCE), P, name,
                                  C.to_int(u32(P + 0x2E8)) & M32)
                    self.w32(P + 0x2E8, 0)
                elif not self.call('Player_hasAnim', P, name):
                    self._track_fixup(P)
                    anm = self.call('res_find', u32(u32(P + 0x24)), name)
                    self.call('anim_startBlendInOut', P + 0x114, anm, 0x80A, F_0_1, F_0_1)
        # C
        if not C.lt(ZERO, u32(P + 0xC8)) or self.s32(P + 0x58C) == 4:
            self.w32(P + 0x2DC, 0)
            return
        if u32(T.G_DEBUG_INVULNERABLE) and not u32(P + 0x2DC) & 0x20000000:
            self.w32(P + 0xC8, ZERO)
        R = self._rec(P)
        self.w32(R + 0xAC, C.sub(u32(R + 0xAC), u32(P + 0xC8)))
        point = (u32(P + 0x10), u32(P + 0x14), C.add(u32(P + 0x18), F_36))
        decal = self.s32(T.G_DECAL_DETAIL)
        if (decal > 0 or self.s8(T.G_NETWORK_MODE)) and u32(P + 0x2DC) & 0xD:
            if decal > 0:
                self.call('fx_spawn', 0, point)
            if not u32(P + 0xC) & T.F_PREDICTION_COPY and not self.draw() & 7:
                block = self.call('pool_new', G_GUTCHUNK_SIZE)
                if block:
                    self.call('GutChunk_ctor', block, point, 2, 1, ONE)
        R = self._rec(P)
        if u32(P + 0x2DC) & 0x10 and C.le(u32(R + 0xAC), ZERO):
            self.call('fx_disintegrateModel', P, u32(P + 0x544), P + 0x114, self.vec(P + 0x10),
                      self.s16(P + 0x38) & M32, 0, ONE)
        self.w32(P + 0xC8, 0)
        self.w32(P + 0xC, u32(P + 0xC) | 0x100)
        R = self._rec(P)
        if C.le(u32(R + 0xAC), ZERO):
            self._death(P)
            return
        self._stagger(P)

    def _death(self, P):
        """0x1b3380-0x1b3714 (D, D')."""
        u32 = self.u32
        spell = self.call('creature_findSpellByType', P, self.call('SpellResurrect_typeinfo'))
        if spell and s32(u32(G_NUM_PLAYERS)) == 1:
            self.w32(self._rec(P) + 0xAC, self.call('SpellResurrect_onOwnerDeath', spell))
        R = self._rec(P)
        if not C.le(u32(R + 0xAC), ZERO):
            self.w32(P + 0x2DC, 0)
            return
        self.w32(R + 0xAC, ZERO)
        self.w32(P + 0xC, u32(P + 0xC) | 8)
        node = u32(P + 0x588)
        if node and u32(node + 0xC):
            self.table_call('Spell', u32(node + 0xC), 0x14, 1, 3)
        R = self._rec(P)
        model = u32(R + 0x54)
        offset = 0x14 if (model in (0, 1, 4, 5, 8, 9, 10, 11) and self.s8(R + 0x4A86) == 2) else 0xC
        self.call('anim_start', P + 0x114, u32(u32(P + 0x24) + offset), 0x206, HALF)
        self.w32(P + 0x58C, 4)
        self.w32(P + 0x448, u32(G_SIM_FRAME))
        self.w32(P + 0xC, u32(P + 0xC) | 1)
        self.call('game_rebuildAlivePlayers')
        if self.call('net_isLocalSlot', u32(P + 0x3C8)):
            self.call('net_closeLocalMenus', 1)
            self.w8(T.G_FORCE_GHOST_REBASE, 1)
        if s32(u32(G_NUM_PLAYERS)) >= 2:
            other = 1 if u32(P + 0x3C8) == 0 else 0
            if C.lt(ZERO, u32(G_PLAYERS + other * REC_SIZE + 0xAC)) and not u32(G_PVP_MODE_A):
                self.call('player_voice', other, 3)
        if u32(G_PVP_MODE_A):
            node = u32(P + T.H_LAST_ATTACKER)
            if node:
                killer = u32(node + 0xC)
                if not killer:
                    raise CompositionError('a last-attacker node without an object')
                if u32(killer + 0xC) & 0x40:
                    raise Unsupported('PvP mode A kill credit (mana, a skill 0x3b orb)')
        if u32(G_PVP_MODE_B):
            node = u32(P + T.H_LAST_ATTACKER)
            if node:
                self.call('arena_onPlayerKilled', u32(P + 0x3C8), u32(node + 0xC))
            else:
                self.call('arena_loseLife', u32(P + 0x3C8))
        self.w32(P + 0x2DC, 0)

    def _stagger(self, P):
        """0x1b3718-0x1b38d8 (E): as round 1."""
        u32 = self.u32
        state = self.s32(P + 0x58C)
        if u32(P + 0x2DC) & 0x400000 or state in (3, 7) or self.s32(P + 0x44C) == 2:
            self.w32(P + 0x2DC, 0)
            return
        R = self._rec(P)
        chance = C.sub(F_0_04, C.mul(u32(R + 0xDC), F_0_04))
        if C.lt(chance, ZERO):
            chance = ZERO
        if C.lt(C.from_int(self.draw()), C.mul(chance, F_65536)) or u32(P + 0x2DC) & 0x4000000:
            if self.s32(P + 0x58C) not in (6, 10):
                self._set_state3(P)
                self._track_fixup(P)
                self._reaction_clip(P)
        self.w32(P + 0x2DC, 0)


# =======================================================================================
# The real player tick as slot 4
# =======================================================================================

def lcg_steps(before, after, limit=100000):
    """How many shared-seed draws (s = s x 0x19660d + 0x3c6ef35f) lead from `before` to
    `after`."""
    s = before
    for n in range(limit + 1):
        if s == after:
            return n
        s = (s * 0x19660D + 0x3C6EF35F) & M32
    raise CompositionError('the shared seed moved by more than %d draws' % limit)


class PlayerAnim(T.AnimTimeline):
    """AUTHORED animation for the tick runtime.  A player's animation state holds the four
    base cells player_resetIdleAnim 0x1b2470 writes (count +0x118 = 4: idle and the three
    locomotion layers; research-anim docs/spec/player-animation-dispatch.md 3.1, Observed
    there), and a clip that is started is pushed as a fifth track until it ends, when the
    count falls back to 4 and the flags +0x11a get 0x80 (ended).  Creatures keep round 1's
    one-track timeline.  Track words +0x11c + 0x20 x i hold the clip token, so
    Player_hasAnim and the fidget see what is playing."""

    def __init__(self, clips=None, default=(20, {}), players=()):
        T.AnimTimeline.__init__(self, clips, default)
        self.players = set(players)

    def is_player(self, anim):
        return anim - 0x114 in self.players

    def reset_player(self, mem, P):
        anim = P + 0x114
        self.players.add(P)
        self.state.pop(anim, None)
        mem.poke(anim + 4, 1, 4)
        mem.poke(anim + 6, 2, 0)
        for i in range(4):
            mem.poke(P + 0x11C + 0x20 * i, 4, 0xA0000000 + 0x44 + 8 * i)

    def start(self, mem, anim, clip, flags=0):
        if not self.is_player(anim):
            return T.AnimTimeline.start(self, mem, anim, clip)
        self.state[anim] = [clip, 0]
        mem.poke(anim + 4, 1, 5)
        mem.poke(anim + 8 + 0x20 * 4, 4, clip & M32)
        mem.poke(anim + 8 + 0x20 * 4 + 0x1C, 2, flags & 0xFFFF)
        mem.poke(anim + 6, 2, 0x8)

    def advance(self, mem, anim):
        if not self.is_player(anim):
            return T.AnimTimeline.advance(self, mem, anim)
        entry = self.state.get(anim)
        if entry is None:
            return 0
        length, events = self.clips.get(entry[0], self.default)
        entry[1] += 1
        bits = events.get(entry[1], 0)
        if entry[1] >= length:
            del self.state[anim]
            mem.poke(anim + 4, 1, 4)
            mem.poke(anim + 8 + 0x20 * 4, 4, 0)
            mem.poke(anim + 8 + 0x20 * 4 + 0x1C, 2, 0)
            mem.poke(anim + 6, 2, (mem.load(anim + 6, 2) & ~0x8 & 0xFFFF) | 0x80)
        return bits


class TickServices(T.Services):
    """Round 1's services, plus the plug-in table (checked first) and the names the real
    tick reaches.  An unknown name is still refused."""

    PRESENTATION = T.Services.PRESENTATION + ('light_relink', 'light_unlink', 'light_link2', 'sound_stop',
                                              'Player_weaponTrails', 'Player_footstep', 'hud_showMessage',
                                              'fx_disintegrateModel')

    def get(self, name):
        fn = self.rt.plugins.get(name)
        if fn is not None:
            return fn
        return T.Services.get(self, name)


class TickRuntime(T.Runtime):
    """Runtime whose player slot 4 is ref_player.Tick.run (Player_run 0x1a5030, executed by
    tools/difftest_player.py) on the shared image, and whose model is DefenceModel.

        rt = TickRuntime()
        rt.plug('Player_move', my_move)          # e.g. ref_combat_move's model method
        rt.plug('Player_pickAttackAnim', my_pick)

    Call-outs and who answers them (TickServices; anything else is refused):
        Creature_run, Creature_applyKnockback   ref_creature / round 1 (executed)
        Player_processDamage                     DefenceModel (executed here)
        Player_move                              round 1's restricted body (still stick,
                                                 modes 0, 3, 4) until plugged
        Player_meleeHit, Player_findTarget       round 1 (executed; unarmed)
        Player_animStep, anim_*                  PlayerAnim (AUTHORED)
        Player_pickAttackAnim                    refused until plugged (one shared draw;
                                                 tools/difftest_player.py 9.10 executed only
                                                 its draw and store)
        Player_interact                          DefenceModel (executed): nothing in
                                                 reach; an interactable object is refused
        light_*, Player_weaponTrails, sounds     presentation (traced, ignored)
    """

    def __init__(self, terrain=None, anim=None, skill_stat=None, camera_mode=1):
        T.Runtime.__init__(self, terrain, anim or PlayerAnim(), skill_stat, camera_mode)
        self.plugins = {}
        self.services = TickServices(self)
        self.model = DefenceModel(self.mem, self.services)
        self.draws_by_player = {}               # P -> [(frame, shared-seed draws of its slot 4)]

    def plug(self, name, fn):
        """Answer the call-out `name` with fn(*args) from now on (a model's method)."""
        self.plugins[name] = fn

    def spawn_player(self, slot, pos, facing=0, hp=100.0, level=1, strength=20, armor=0, team=0,
                     idle_voice_limit=0x7FFF):
        """Round 1's authored player, with the four base animation cells of a constructed
        player (PlayerAnim) and the idle-voice limit +0x4b2 as given (round 1 fixed it at
        0x7fff so the voice never fired; Player_ctor's own value is not read here)."""
        P = T.Runtime.spawn_player(self, slot, pos, facing, hp, level, strength, armor, team)
        if isinstance(self.anim, PlayerAnim):
            self.anim.reset_player(self.mem, P)
        self.mem.poke(P + 0x4B2, 2, idle_voice_limit & 0xFFFF)
        return P

    def player_run(self, P):
        """Slot 4 of a player: Player_run 0x1a5030 as ref_player.Tick.run models it.  The
        shared-seed draws of the whole slot 4 (the tick's own and those of the models it
        calls, Player_processDamage and damage_apply included) are counted from the seed."""
        seed = self.mem.u32(T.G_RAND_SEED)
        tick = RP.Tick(self.mem, P, self.services)
        out = tick.run()
        draws = lcg_steps(seed, self.mem.u32(T.G_RAND_SEED))
        self.note('player_tick', P, out.returned, draws)
        self.draws_by_player.setdefault(P, []).append((self.mem.u32(T.G_SIM_FRAME), draws))
        return out

    # ---- call-outs the real tick reaches -----------------------------------------------
    def svc_anim_start(self, state, clip, flags, blend):
        self.note('anim', 'start', state, clip, flags)
        if isinstance(self.anim, PlayerAnim) and self.anim.is_player(state):
            return self.anim.start(self.mem, state, clip, flags)
        self.anim.start(self.mem, state, clip)

    def svc_anim_startBlendInOut(self, state, clip, flags, blend_in, blend_out):
        self.note('anim', 'blend', state, clip, flags)
        if isinstance(self.anim, PlayerAnim) and self.anim.is_player(state):
            return self.anim.start(self.mem, state, clip, flags)
        self.anim.start(self.mem, state, clip)

    def svc_anim_findTrackByFlag(self, state, mask):
        """anim_findTrackByFlag 0x171178 (ref_anim.anim_find_track_by_flag, executed by
        tools/difftest_anim.py) on the image: the first of the +4 (count) tracks whose u16
        flags at track +0x1c has a bit of mask, else -1000000000."""
        for i in range(max(s8(self.mem.load(state + 4, 1)), 0)):
            if s16(self.mem.load(state + 8 + 0x20 * i + 0x1C, 2)) & mask:
                return i
        return -1000000000 & M32

    def svc_Creature_applyKnockback(self, c, scale):
        return self.model.apply_knockback(c, scale)

    def svc_Player_processDamage(self, P):
        return self.model.player_process_damage_full(P)

    def svc_Player_takeDamage(self, P, attacker, flags, amount):
        return self.model.player_take_damage_full(P, attacker, flags, amount)

    def svc_Player_hasAnim(self, P, name):
        return self.model.player_has_anim(P, name)

    def svc_Player_blockSparks(self, P, silent):
        return self.model.player_block_sparks(P, silent)

    def svc_res_find(self, lump, entry):
        """AUTHORED: a token per entry name (no level data); names given by address are
        read from the image."""
        if isinstance(entry, tuple):                        # ('buf', text) of a libc_sprintf
            entry = entry[1]
        name = entry if isinstance(entry, (bytes, bytearray)) else self.model._cstr(entry, 64)
        return (0xB0000000 | (sum(name) * 131 + len(name)) & 0xFFFFFF) & M32

    def svc_model_getAttachPoint(self, model, pos, facing, anim, index, dir_flag, scale):
        """AUTHORED hand points: the object's position (no skeleton in the contract)."""
        out = tuple(pos)
        return (out, (0, 0, 0)) if dir_flag else out

    def svc_SpellBlessed_typeinfo(self):
        return 0x3CE700

    def svc_SpellBash_typeinfo(self):
        return 0x3CE6B0

    def svc_SpellShieldBash_typeinfo(self):
        return 0x3D0258

    def svc_memcard_isBusy(self):
        return 0

    def svc_pad_buttonValue(self, pad, button):
        return ZERO

    def svc_hud_countActiveNotices(self, slot, index):
        return 0

    def svc_player_getPassiveLevel(self, slot, mask):
        return 0

    def svc_Player_interact(self, P, pad, display_only):
        """DefenceModel.player_interact (executed; nothing to interact with)."""
        return self.model.player_interact(P, pad, display_only)

    def svc_Player_pickAttackAnim(self, P, cls):
        raise Unsupported('Player_pickAttackAnim 0x1bba88 (one shared draw; plug a model)')
