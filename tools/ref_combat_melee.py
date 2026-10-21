#!/usr/bin/env python3
"""ref_combat_melee.py - player offence for the combat contract (round 2): the attack-
animation choice, the combo timing of Player_run state 1, and the ARMED melee hit, on the
one shared memory of tools/ref_combat_runtime.py.  docs/spec/combat-player-melee.md is the
prose and says, statement by statement, what is Executed, Observed, Inferred or Unknown.

A research tool, not game code.  Standard library only; no game data is embedded.

What the module adds (MeleeModel, a subclass of ref_combat_runtime.CombatModel)
    Executed - tools/difftest_combat_melee.py runs the original under tools/ee_emu.py and
    compares calls, stored bytes, the shared seed and the result:
        pick_attack_anim       Player_pickAttackAnim 0x1bba88 (one shared draw, unused)
        player_melee_hit_full  Player_meleeHit 0x1b6a98: unarmed and armed, dual wield,
                               bow / thrown recompute, heavy attack, scale, SpellHarmTouch,
                               the AutoProp line-of-sight exception
        player_hit_sparks      Player_hitSparks 0x1bcc20 (200 shared draws)
        skill_rank_scale       skill_rankScale 0x1bf438
        passive_level          player_getPassiveLevel 0x1bed48 as inlined in meleeHit
        creature_get_model, player_get_model   Creature / Player slot 16 (0x3c2738, 0x3c3b38)
    Pure (no memory): combo_timeline() - the frame numbers of state 1 as the executed
    model ref_player.Tick.state_melee computes them (tools/difftest_player.py executed it).

API stability
    Round 1's CombatModel.player_melee_hit (unarmed, scale 0) is untouched.  MeleeModel
    routes the call-out 'Player_meleeHit' to player_melee_hit_full, which equals round 1 on
    round 1's domain (tools/difftest_combat_melee.py checks both on the same cases), and
    'Player_pickAttackAnim' / 'Player_hitSparks' to their models.  MeleeRuntime is
    ref_combat_runtime.Runtime with this model installed.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

M32, M64 = T.M32, T.M64
s8, s16, s32 = T.s8, T.s16, T.s32
ZERO, HALF, ONE = T.ZERO, T.HALF, T.ONE
Unsupported, CompositionError = T.Unsupported, T.CompositionError

G_PLAYERS, REC_SIZE = T.G_PLAYERS, T.REC_SIZE
G_RAND_SEED, G_SIM_FRAME, G_WORLD = T.G_RAND_SEED, T.G_SIM_FRAME, T.G_WORLD
G_CLASS_SKILLS = 0x4EF538           # per record class 0xa88 bytes: 48 entries of 0x38, u64 mask first
F_PREDICTION_COPY = T.F_PREDICTION_COPY

PASSIVE_DUAL_WIELD = 0x40000        # passive mask tested for the second hand (0x1b6c4c)
PASSIVE_HEAVY = 0x20000             # passive mask scaling the heavy attack (0x1b6e24)
HIT_SPARK_DEF = 0x865950            # particle definition of Player_hitSparks (an address only)
HIT_SPARK_PAIRS = 100               # loop count 0x63 .. 0 (0x1bcc44, 0x1bce44)
F_30, F_36, F_60 = 0x41F00000, 0x42100000, 0x42700000
AUTOPROP_DESC = 0x9089F0            # the descriptor AutoProp_typeinfo 0x3c9508 returns

# Player_pickAttackAnim's thresholds are compared with h, the low 16 bits of
# g_simFrame x 0x19660d + 0x3c6ef35f (0x1bbaa8-0x1bbaf4); `T` below is the table form.


def frame_hash(frame):
    """h of Player_pickAttackAnim: the generator step applied to g_simFrame, low 16 bits
    (0x1bbab8-0x1bbaf4).  Not the shared seed: the seed is advanced and its value unused."""
    return ((frame * 0x19660D + 0x3C6EF35F) & M32) & 0xFFFF


def _pick(h, cuts):
    """cuts = (v0, (x1, v1), (x2, v2), ...): v0 below x1, v1 from x1, ... (thresholds as
    the code compares them: `h < x` keeps the earlier value)."""
    value = cuts[0]
    for x, v in cuts[1:]:
        if h >= x:
            value = v
    return value


def pick_attack_variant(model_index, cls, old, h):
    """The decision of Player_pickAttackAnim 0x1bba88 as a pure function: the stores it
    makes to P+0x461, in order (an empty list when nothing is stored).  Read at
    0x1bbaf8-0x1bbfe0 and executed (tools/difftest_combat_melee.py, 'pickAttackAnim').
    Two stores happen on one path (model 9, class 0, old 5: 4 first)."""
    out = []
    mi = s32(model_index)
    # phase A: model 9 (0x1bbaf8-0x1bbc3c)
    if mi == 9:
        if cls == 5:
            v = {1: 2, 2: 3, 3: 1}.get(old)
            if v is not None:
                out.append(v)
        elif cls == 0:
            if old == 1:
                out.append(_pick(h, (2, (0x5555, 3), (0xAAAA, 5))))
            elif old == 2:
                out.append(_pick(h, (1, (0x7FFF, 3))))
            elif old == 3:
                out.append(4)
            elif old == 4:
                out.append(_pick(h, (2, (0x7FFF, 5))))
            elif old == 5:
                out.append(4)                                       # delay-slot store 0x1bbbd4
                if h >= 0x5555:
                    out.append(_pick(h, (3, (0xAAAA, 1))))
        elif cls == 1:
            v = {1: 2, 3: 2}.get(old)
            if old == 2:
                v = _pick(h, (1, (0x7FFF, 3)))
            if v is not None:
                out.append(v)
        if cls in (0, 1, 5):
            return out
    # phase B (0x1bbc40-0x1bbfe0)
    if cls == 0:
        if mi == 11:
            table = {1: (2, (0x7000, 4), (0xE000, 5)), 2: (3, (0x6AA8, 1), (0xD334, 5)),
                     3: (4, (0x7000, 2), (0xE000, 5)), 4: (5, (0x53ED, 1), (0xAAAA, 3))}
            out.append(_pick(h, table.get(old, (1, (0x7FFF, 3)))))
        else:
            table = {1: (2, (0x7FFF, 4)), 2: (1, (0x5555, 3), (0xAAAA, 5)), 3: (2, (0x7FFF, 4)),
                     4: (1, (0x5555, 3), (0xAAAA, 5))}
            out.append(_pick(h, table.get(old, (2, (0xBB80, 4)))))
    elif cls in (2, 3):
        if old == 1:
            out.append(_pick(h, (2, (0x7FFF, 4))))
        elif old == 2:
            out.append(_pick(h, (1, (0x7FFF, 3))))
        elif old == 3:
            if mi == 11 and cls == 2:
                out.append(_pick(h, (2, (0xBB80, 4))))
            else:
                out.append(_pick(h, (2, (0x7FFF, 4))))
        elif old == 4:
            out.append(_pick(h, (1, (0x7FFF, 3))))
    elif cls in (1, 5):
        if cls == 5 and mi == 11:
            table = {2: (1, (0x6D60, 3), (0xDAC0, 4)), 3: (2, (0xBB80, 4)), 4: (2, (0x7FFF, 3))}
            out.append(_pick(h, table.get(old, (2, (0x7FFF, 4)))))
        else:
            if old in (1, 3):
                out.append(2)
            elif old == 2:
                out.append(_pick(h, (1, (0x7FFF, 3))))
    elif cls == 7:
        out.append(2 if old == 1 else 1)
    return out


# ---------------------------------------------------------------------------------------
# combo timing (pure): ref_player.Tick.state_melee, executed by tools/difftest_player.py
# ---------------------------------------------------------------------------------------

COMBO_STEPS = {2: 4, 1: 7, 3: 9, 5: 2, 7: 7}         # others 7; a heavy attack 1 (0x1a9678 on)


def combo_timeline(cls, speed=ONE, haste=ZERO, heavy=False, net=False):
    """Frame numbers (counted from the swing's start frame P+0x448) of one swing of
    Player_run state 1, as the executed model computes them.  `speed` is the final swing
    speed after haste, Berserker Rage and the slow factor (single-precision bits);
    `haste` the haste term alone (it trims the combo window).  Returns a dict:

      hit          the frame of the one target hit (offline trunc(16.02 / speed); net 1,
                   and then only when P+0x55c is 0), or None at speed 0
      sweep_from   class 2 (not heavy): first frame of the sweep, trunc(127 / speed);
                   heavy with a class-2 weapon: 94 (not divided); else None
      next_after   the next swing starts on the first tick with the attack button in
                   pad.pressed and `since` > window / speed (strict); this is window /
                   speed as a float's bits
      ends_at      the frame from which the swing ends by itself, P+0x470 x 60 <= since:
                   1.6 s x 60 = 96 for a swing started from state 2 or by the combo
                   (0.9 x 60 = 54 for the bow melee, 0.857 x 60 for a heavy attack);
                   NOT divided by the speed
      move4_until  the lunge, move mode 4 while since <= 0.433 x 60 (0.567 x 60 heavy)
      steps        the combo length (P+0x460 saturates at steps - 1)
      sounds       frames 6 and 9 (swing sound, shout)
    """
    out = {'steps': 1 if heavy else COMBO_STEPS.get(cls, 7), 'sounds': (6, 9)}
    if C.eq(speed, ZERO):
        out['hit'] = None
    else:
        out['hit'] = 1 if net else C.to_int(C.div(0x418028F5, speed))
    out['sweep_from'] = None
    if cls == 2:
        out['sweep_from'] = 0x5E if heavy else C.to_int(C.div(C.from_int(0x7F), speed))
    trim = C.mul(C.mul(haste, F_60), HALF)
    if C.lt(0x418B3332, trim):
        trim = 0x418B3332
    window = C.sub(0x418CED91 if cls == 7 else 0x41B028F5, trim)
    out['next_after'] = C.div(window, speed)
    lasts = 0x3F5B645A if heavy else (0x3F666666 if cls == 4 else 0x3FCCCCCC)
    out['ends_at'] = C.mul(lasts, F_60)
    out['move4_until'] = C.mul(0x3F1126E9 if heavy else 0x3EDDB22D, F_60)
    return out


# ---------------------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------------------

class MeleeModel(T.CombatModel):
    """CombatModel plus the player-offence bodies of this module."""

    COMBAT_BODIES = dict(T.CombatModel.COMBAT_BODIES)
    COMBAT_BODIES.update({0x3C2738: (16, 'creature_get_model'), 0x3C3B38: (16, 'player_get_model')})
    INTERNAL = dict(T.CombatModel.INTERNAL)
    INTERNAL.update({'Player_meleeHit': 'player_melee_hit_full', 'Player_pickAttackAnim': 'pick_attack_anim',
                     'Player_hitSparks': 'player_hit_sparks'})
    MODELLED = dict(T.CombatModel.MODELLED)
    MODELLED.update({'Player_pickAttackAnim': 0x1BBA88, 'Player_hitSparks': 0x1BCC20, 'skill_rankScale': 0x1BF438,
                     'Creature_slot16': 0x3C2738, 'Player_slot16': 0x3C3B38})

    # ---- slot 16 -----------------------------------------------------------------------
    def creature_get_model(self, c):
        """Creature slot 16 0x3c2738: the model of the class definition, *(c+0x24) + 0xc."""
        return self.u32(self.u32(c + 0x24) + 0xC)

    def player_get_model(self, P):
        """Player slot 16 0x3c3b38: the model at P+0x544."""
        return self.u32(P + 0x544)

    # ---- small helpers ------------------------------------------------------------------
    @staticmethod
    def skill_rank_scale(rank):
        """skill_rankScale 0x1bf438: ((rank - 1) x 9.99999 + 99.99999) x 0.01 in single
        precision (0x411fff98, 0x42c7ffc3, 0x3c23d70a); 0.9 for rank 0."""
        x = C.from_int(s32(rank - 1))
        return C.mul(C.add(C.mul(x, 0x411FFF98), 0x42C7FFC3), 0x3C23D70A)

    def passive_level(self, slot, mask):
        """player_getPassiveLevel as inlined at 0x1b6c2c and 0x1b6e04: 0 for slot >= 5;
        else the level byte R+0xef+n of the first of the 48 class entries whose 64-bit
        mask equals `mask` (negative reads 0), 0 when none matches."""
        if (slot & M32) >= 5:
            return 0
        R = G_PLAYERS + s32(slot) * REC_SIZE
        table = (G_CLASS_SKILLS + s32(self.u32(R + 0x50)) * 0xA88) & M32
        for n in range(0x30):
            if self.u64(table + n * 0x38) == mask:
                level = self.s8(R + 0xEF + n)
                return 0 if level < 0 else level
        return 0

    @staticmethod
    def _round(x):
        """The rounding of 0x1b6ea0-0x1b6ecc: trunc(x + 0.5) when 0 <= x, else trunc(x - 0.5)."""
        return C.to_int(C.add(x, HALF) if C.le(ZERO, x) else C.sub(x, HALF))

    def _cstr(self, addr, limit=64):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(addr + len(out))
            if not b:
                break
            out.append(b)
        return bytes(out)

    def _typeinfo_equal(self, a, b):
        """rtti_typeInfoEquals 0x3b1250: the same descriptor, or equal name strings (word 0
        of each descriptor) - a C-library function, run inline."""
        if a == b:
            return True
        return self._cstr(self.u32(a)) == self._cstr(self.u32(b))

    # ---- Player_pickAttackAnim 0x1bba88 ---------------------------------------------------
    def pick_attack_anim(self, P, cls):
        """Player_pickAttackAnim 0x1bba88 (P, weapon class): one shared draw whose value is
        not used (0x1bbab0-0x1bbafc), the variant byte P+0x461 by pick_attack_variant from
        the record's model index R+0x54, the class, the old variant and frame_hash(
        g_simFrame); then net_isLocalSlot(slot), its result discarded (0x1bbfe4)."""
        slot = self.u32(P + 0x3C8)
        R = (G_PLAYERS + s32(slot) * REC_SIZE) & M32
        self.draw()
        h = frame_hash(self.u32(G_SIM_FRAME))
        for v in pick_attack_variant(self.s32(R + 0x54), s32(cls), self.s8(P + 0x461), h):
            self.w8(P + 0x461, v)
        self.call('net_isLocalSlot', slot)

    # ---- Player_hitSparks 0x1bcc20 -----------------------------------------------------------
    def player_hit_sparks(self, P, target):
        """Player_hitSparks 0x1bcc20 (P, target).  nA = sample points of P's model (P+0x544);
        nB = those of the target's model (slot 16).  100 times: one shared draw picks a
        point of P (draw % nA), slot 16 of the target again, one shared draw picks a
        point of the target (draw % nB); the velocity is the normalised difference (B - A)
        x 30 (rsqrt.s); particle_spawn(0x865950, B, velocity; 0.0).  200 shared draws.
        A model without sample points divides by zero: refused."""
        u32 = self.u32
        n_a = s32(self.call('model_getSamplePointCount', u32(P + 0x544)))
        n_b = s32(self.call('model_getSamplePointCount', self.vcall(target, 16)))
        for _ in range(HIT_SPARK_PAIRS):
            if n_a == 0:
                raise Unsupported('Player_hitSparks: a model without sample points (division by zero)')
            i_a = T._c_rem(self.draw(), n_a)
            a, _x = self.call('model_getSamplePoint', u32(P + 0x544), P + 0x114, self.vec(P + 0x10),
                              self.s16(P + 0x38), i_a, 1, 0, ONE)
            model_b = self.vcall(target, 16)
            if n_b == 0:
                raise Unsupported('Player_hitSparks: a target model without sample points (division by zero)')
            i_b = T._c_rem(self.draw(), n_b)
            b, _x = self.call('model_getSamplePoint', model_b, target + 0x114, self.vec(target + 0x10),
                              self.s16(target + 0x38), i_b, 1, 0, ONE)
            dx, dy, dz = C.sub(b[0], a[0]), C.sub(b[1], a[1]), C.sub(b[2], a[2])
            inv = C.rsqrt(ONE, C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
            v = (C.mul(C.mul(dx, inv), F_30), C.mul(C.mul(dy, inv), F_30), C.mul(C.mul(dz, inv), F_30))
            self.call('particle_spawn', HIT_SPARK_DEF, tuple(b), v, ZERO)

    # ---- Player_meleeHit 0x1b6a98, all branches ------------------------------------------------
    def player_melee_hit_full(self, P, target, a2, extra, scale):
        """Player_meleeHit 0x1b6a98 (scale; P, target, unused, extra flags).  Read at
        0x1b6a98-0x1b7150 and executed (tools/difftest_combat_melee.py, 'meleeHitFull').

          1. nothing for the prediction copy (0x1b6b00);
          2. scale 0 only: terrain_raycast(world, P + (0, 0, 36) - x by `+ 0.0` -, the 3-D
             difference, mask 0; 1.0); a hit (0 <= t) ends the call unless
             typeid(*target) == typeid(AutoProp) (slot 0 of the target, AutoProp_typeinfo,
             rtti_typeInfoEquals);
          3. hand: both hands occupied (R+0x43f0 and R+0x43f4) and the passive 0x40000 above
             0 and the combo step P+0x460 odd -> the second weapon R+0x443c, hand 1; else
             the primary of the set R+0x4434 + 4 x R+0x4a7c, hand 0;
          4. Player_recalcDamage(P, weapon, 0); with a weapon: flags = definition +0x20,
             a3 = item_getModifiedField1a(weapon), a4 = low word of weapon +8; else flags 1;
          5. 0x1000 for class 1 after 60 frames; knock-back class 0x80000 with a scale or
             (class 3 after 60 frames), else 0x40000;
          6. with a weapon and (class 4 or definition +0x1e == 6): Player_recalcDamage(P, 0,
             0) and 0x200000 (a bow or thrown weapon hits as a fist);
          7. heavy (P+0x44c == 2): 0x200000; s = skill_rankScale(passive 0x20000); R+0xd0 +=
             round(R+0xd0 x s), then R+0xd4 likewise (stored in place); a creature target
             (flag 0x20) gets Player_hitSparks;
          8. a scale: R+0xd0 = round(R+0xd0 x scale), R+0xd4 likewise (in place);
          9. min, max = R+0xd0, R+0xd4; a SpellHarmTouch on P: SpellHarmTouch_applyToHit(
             spell, target, &min, &max) and 0x200000;
         10. damage_apply(f32(min), f32(max); target, P, R+0xcc, a3, a4, flags | extra,
             weapon, 0); a landed hit on a creature: material R+0x4ac5 + hand x 0x40 (3 for
             cflag 0x2000, 2 for 0x1000, 1 for 0x40000, else 0) and R+0x4ac6 + hand x 0x40 = 5.
        """
        u32 = self.u32
        if u32(P + 0xC) & F_PREDICTION_COPY:
            return
        slot = u32(P + 0x3C8)
        R = (G_PLAYERS + s32(slot) * REC_SIZE) & M32
        if C.eq(scale, ZERO):
            px, py, pz = self.vec(P + 0x10)
            tx, ty, tz = self.vec(target + 0x10)
            t = self.call('terrain_raycast', u32(G_WORLD), (C.add(px, ZERO), py, C.add(pz, F_36)),
                          (C.sub(tx, px), C.sub(ty, py), C.sub(tz, pz)), 0, ONE)
            if C.le(ZERO, t):
                if not target:
                    raise Unsupported('typeid of a null target (cxx_throwBadTypeid)')
                # slot 0 of the target's table is a static type-info getter; the call
                # leaves a0 as the ray call left it (0x1b6bc0-0x1b6bc8), so it is recorded
                # without arguments.  The target is noted for a service that needs it.
                self.typeid_target = target
                mine = self.call('Creature.v0')
                prop = self.call('AutoProp_typeinfo')
                if not self._typeinfo_equal(mine, prop):
                    return
        a3 = a4 = 0
        flags = 1
        hand = 0
        weapon = None
        if u32(R + 0x43F0) and u32(R + 0x43F4):
            if self.passive_level(slot, PASSIVE_DUAL_WIELD) > 0 and self.u8(P + 0x460) & 1:
                weapon, hand = u32(R + 0x443C), 1
        if weapon is None:
            weapon = u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C))
        self.call('Player_recalcDamage', P, weapon, 0)
        if weapon:
            flags = u32(u32(weapon) + 0x20)
            a3 = self.call('item_getModifiedField1a', weapon)
            a4 = u32(weapon + 8)
        cls = self.s8(R + 0x4A86)
        since = C.from_int(s32(u32(G_SIM_FRAME) - u32(P + 0x448)))
        if cls == 1 and C.le(F_60, since):
            flags |= 0x1000
        if not C.eq(scale, ZERO):
            knock = 0x80000
        else:
            knock = 0x80000 if cls == 3 and C.le(F_60, since) else 0x40000
        flags |= knock
        if weapon and (cls == 4 or self.s8(u32(weapon) + 0x1E) == 6):
            self.call('Player_recalcDamage', P, 0, 0)
            flags |= 0x200000
        if u32(P + 0x44C) == 2:
            flags |= 0x200000
            s = self.skill_rank_scale(self.passive_level(slot, PASSIVE_HEAVY))
            lo = self.s32(R + 0xD0)
            self.w32(R + 0xD0, lo + self._round(C.mul(C.from_int(lo), s)))
            hi = self.s32(R + 0xD4)
            self.w32(R + 0xD4, hi + self._round(C.mul(C.from_int(hi), s)))
            if u32(target + 0xC) & 0x20:
                self.call('Player_hitSparks', P, target)
        if not C.eq(scale, ZERO):
            self.w32(R + 0xD0, self._round(C.mul(C.from_int(self.s32(R + 0xD0)), scale)))
            self.w32(R + 0xD4, self._round(C.mul(C.from_int(self.s32(R + 0xD4)), scale)))
        dmin, dmax = self.s32(R + 0xD0), self.s32(R + 0xD4)
        spell = self.call('creature_findSpellByType', P, self.call('SpellHarmTouch_typeinfo'))
        if spell:
            # (spell, target, &min, &max): the two words are outputs here; the callee
            # receives the range in them and its answer is what it leaves there
            self.harm_touch_range = (dmin, dmax)
            dmin, dmax = self.call('SpellHarmTouch_applyToHit', spell, target)
            dmin, dmax = s32(dmin), s32(dmax)
            flags |= 0x200000
        result = self.call('damage_apply', target, P, u32(R + 0xCC), a3, a4, (flags | extra) & M32, weapon, 0,
                           C.from_int(dmin), C.from_int(dmax))
        if result and u32(target + 0xC) & 0x20:
            cf = self.u64(target + 0xA8)
            m = 3 if cf & 0x2000 else 2 if cf & 0x1000 else 1 if cf & 0x40000 else 0
            self.w8(R + 0x4AC5 + hand * 0x40, m)
            self.w8(R + 0x4AC6 + hand * 0x40, 5)


TYPEINFO = {0x3C2608: 0x908130, 0x3C3AB8: 0x9083D0, 0x3CC6DC: 0x908E10, 0x3C9508: AUTOPROP_DESC}
TYPE_NAMES = {0x908130: b'Creature', 0x9083D0: b'Player', 0x908E10: b'Skelight', AUTOPROP_DESC: b'AutoProp'}


class LiveItemDef:
    """An item definition (0x40 bytes) as ref_combat.ItemDef, read from the image: name +0,
    damage range +0xe/+0x10, armour +0x18, attack rating +0x1a (s16), category +0x1d,
    subtype +0x1e, damage-type bits +0x20, flags +0x28 (the layout tools/difftest_combat.py
    executes ref_combat with)."""

    def __init__(self, mem, addr):
        self._mem, self.addr = mem, addr

    def _s16(self, off):
        return s16(self._mem.load(self.addr + off, 2))

    name = property(lambda self: '')
    dmg_min = property(lambda self: self._s16(0xE))
    dmg_max = property(lambda self: self._s16(0x10))
    armor = property(lambda self: self._s16(0x18))
    attack = property(lambda self: self._s16(0x1A))
    category = property(lambda self: self._mem.load(self.addr + 0x1D, 1))
    subtype = property(lambda self: self._mem.load(self.addr + 0x1E, 1))
    dmg_type = property(lambda self: self._mem.load(self.addr + 0x20, 4))
    flags = property(lambda self: self._mem.load(self.addr + 0x28, 8))


class LiveItem:
    """An item record (0x48 bytes) as ref_combat.Item, read from the image: definition +0,
    count +4, flags +8 (u64), four modifier slots of four s16 at +0x24."""

    def __init__(self, mem, addr):
        self._mem, self.addr = mem, addr

    @property
    def defn(self):
        return LiveItemDef(self._mem, self._mem.load(self.addr, 4))

    count = property(lambda self: s16(self._mem.load(self.addr + 4, 2)))
    flags = property(lambda self: self._mem.load(self.addr + 8, 8))

    @property
    def mods(self):
        return [tuple(s16(self._mem.load(self.addr + 0x24 + 8 * i + 2 * j, 2)) for j in range(4))
                for i in range(4)]

    def mod(self, code, field=1):
        return T.RB.desc_get(self.mods, code, field)


class MeleeRuntime(T.Runtime):
    """ref_combat_runtime.Runtime with MeleeModel installed: the player's swing reaches
    player_melee_hit_full, the combo's next swing pick_attack_anim (its shared draw), and
    a weapon item is served by ref_combat's executed record rules on live views
    (Player_recalcDamage, item_getModifiedField1a, damage_apply's weapon descriptor).
    Refused still: bows, thrown weapons and the record-class-4 rule (they read skill
    statistics), a second weapon (the dual-wield factor reads the class-skill table), a
    heavy attack on a creature (Player_hitSparks needs sample points of real models)."""

    def __init__(self, *args, **kwargs):
        T.Runtime.__init__(self, *args, **kwargs)
        self.model = MeleeModel(self.mem, self.services)
        self.services.table['Creature.v0'] = self.svc_Creature_v0      # before the virtual dispatcher
        self._type_names = False

    # ---- authored set-up -------------------------------------------------------------------
    def give_weapon(self, slot, dmg=(5, 9), attack=10, subtype=0, dmg_type=1, cls=0, mods=()):
        """AUTHORED: an item definition and an item placed in fixture memory and made the
        primary of weapon set 0 (R+0x4434, equipment slot 0 R+0x43f0), weapon class `cls`
        (R+0x4a86) - what inventory_equipItem leaves for a one-hand weapon (0x1c2ad4,
        docs/spec/player-animation-dispatch.md 1.3); its idle-animation reset is not
        modelled."""
        poke = self.mem.poke
        d = self._alloc_fixture(0x40)
        poke(d + 0xE, 2, dmg[0] & 0xFFFF)
        poke(d + 0x10, 2, dmg[1] & 0xFFFF)
        poke(d + 0x1A, 2, attack & 0xFFFF)
        poke(d + 0x1E, 1, subtype & 0xFF)
        poke(d + 0x20, 4, dmg_type)
        item = self._alloc_fixture(0x48)
        poke(item, 4, d)
        poke(item + 4, 2, 1)
        slots = list(mods) + [(-1, 0, 0, 0)] * (4 - len(mods))
        for i, slot_ in enumerate(slots):
            for j in range(4):
                poke(item + 0x24 + 8 * i + 2 * j, 2, slot_[j] & 0xFFFF)
        R = G_PLAYERS + slot * REC_SIZE
        poke(R + 0x4434, 4, item)
        poke(R + 0x43F0, 4, item)
        poke(R + 0x4A86, 1, cls & 0xFF)
        return item

    # ---- services ----------------------------------------------------------------------------
    def svc_Creature_v0(self):
        """Slot 0 (the type-info getter) of the target Player_meleeHit tests.  The
        descriptors' name words are an AUTHORED fixture, written on first use, so that
        rtti_typeInfoEquals compares names as in the game."""
        if not self._type_names:
            for desc, name in TYPE_NAMES.items():
                text = self._alloc_fixture(16)
                for i, b in enumerate(name + b'\0'):
                    self.mem.poke(text + i, 1, b)
                self.mem.poke(desc, 4, text)
            self._type_names = True
        target = self.model.typeid_target
        fn = self.u32(self.u32(target + 0x48) + 4)
        if fn not in TYPEINFO:
            raise Unsupported('the type-info getter 0x%x of 0x%x' % (fn, target))
        return TYPEINFO[fn]

    def svc_AutoProp_typeinfo(self):
        return AUTOPROP_DESC

    def svc_Player_meleeHit(self, P, target, a2, extra, scale):
        return self.model.player_melee_hit_full(P, target, a2, extra, scale)

    def svc_Player_pickAttackAnim(self, P, cls):
        return self.model.pick_attack_anim(P, cls)

    def svc_Player_hitSparks(self, P, target):
        return self.model.player_hit_sparks(P, target)

    def svc_item_getModifiedField1a(self, item):
        """item_getModifiedField1a 0x103f88: ref_combat.item_attack_rating (executed)."""
        return T.RB.item_attack_rating(LiveItem(self.mem, item)) & M32

    def svc_Player_recalcDamage(self, P, weapon, flag):
        """Player_recalcDamage 0x1b7158: ref_combat.recalc_damage (executed) on live views,
        with a weapon item too (the subset that reads no skill statistics)."""
        if not weapon:
            return T.Runtime.svc_Player_recalcDamage(self, P, weapon, flag)
        item = LiveItem(self.mem, weapon)
        if s8(item.defn.subtype) in (4, 6):
            raise Unsupported('a bow or thrown weapon (skill 0x30 / 0x4f statistics)')
        slot = s32(self.u32(P + 0x3C8))
        if s32(self.u32(G_PLAYERS + slot * REC_SIZE + 0x50)) == 4:
            raise Unsupported('record class 4 (skill 0x5c statistics)')
        self._sync_rb()
        rec = T._LivePlayerRec(self, slot)
        self.rb.players[rec.slot] = rec
        T.RB.recalc_damage(None, self.rb, self.live(P), item, flag)

    def svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit, dmin, dmax):
        """damage_apply with a weapon item as the descriptor: its four modifier slots
        (+0x24) are the descriptor (ref_combat.Item); everything else as round 1."""
        if not desc or isinstance(desc, tuple):
            return T.Runtime.svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit,
                                              dmin, dmax)
        slots = LiveItem(self.mem, desc).mods
        self._sync_rb()
        before = len(self.rb.seed.draws)
        self.note('damage_apply', victim, attacker, s32(attack), flags & M32)
        result = T.RB.damage_apply(self.rb, self.live(victim), self.live(attacker) if attacker else None,
                                   dmin, dmax, attack, flags, slots, no_crit)
        self.note('damage_result', victim, result, tuple(self.rb.seed.draws[before:]))
        return result
