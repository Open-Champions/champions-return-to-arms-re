"""ref_weapon_holder.py - the weapon holder a monster carries at a fixed offset of its
object (Skeleton +0x3d8, Gnaw and the Horsemen too): the Weapon1 and WeaponShield
virtual slots 1-17, and the three creature helpers they reach.

Reference contract, executed against the original by tools/difftest_weapon_holder.py
(docs/spec/weapon-holder.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    creature_buildElementDamage   0x1176e0  (x, descriptor, kind): the element setters
    damageDesc_getElement         0x117e88  (x, descriptor) -> 0, 1, 2, 3, 4 or 6
    creature_dropHeldPartAsProp   0x117d30  (x, part, creature, definition, flags)
    Weapon1 slots      (table 0x50cf40)  WeaponShield slots (table 0x50cda0)   see SLOTS

A holder h: word +0 the table; byte +4 the hand bits (bit 0 hand 1 carried, bit 1 hand 2);
byte +8 the hand-1 part; the hand-1 damage descriptor at +0x50 (eight halfwords +0x10,
two bytes +0x20, four effect slots +0x24 of (id, value, value, 0)); WeaponShield only:
byte +0x98 the hand-2 part.  'which' is the hand argument: 1, 2, or 0 for both where a
slot accepts it.  Every hand test is on the full register: the setters' "below 2" is
an unsigned compare, so a negative hand is neither.
"""
import ref_core as C
import ref_creature as RC
from ref_creature import M32, M64, s8, s16, s32

VT_WEAPON1, VT_WEAPONSHIELD, VT_WEAPON2 = 0x50CF40, 0x50CDA0, 0x50CE70
BUILD_ELEMENT, GET_ELEMENT, DROP_PART = 0x1176E0, 0x117E88, 0x117D30

G_SKILL_TABLE = 0x41B170
# creature_buildElementDamage: kind -> (entry id, the Skill whose slot 11 gives the base
# value).  The skill pointers are loaded at 0x117750, 0x117848, 0x117940, 0x117a38,
# 0x117b30, 0x117c28; the ids at 0x117780, 0x117878, 0x117970, 0x117a68, 0x117b60,
# 0x117c58.  Jump table 0x5300d0 (seven words; kind 0 and kind >= 7 store nothing more).
ELEMENTS = {
    1: (0x15, G_SKILL_TABLE + 4 * 13),      # 0x41b1a4
    2: (0x16, G_SKILL_TABLE + 4 * 14),      # 0x41b1a8
    3: (0x17, G_SKILL_TABLE + 4 * 26),      # 0x41b1d8
    4: (0x18, G_SKILL_TABLE + 4 * 12),      # 0x41b1a0
    5: (0x26, G_SKILL_TABLE + 4 * 25),      # 0x41b1d4
    6: (0x1F, G_SKILL_TABLE + 4 * 13),      # 0x41b1a4 again, with another id
}
F_0_2 = 0x3E4CCCCC                          # 0x1177a4/0x1177a8 (and each case's copy)
F_2M16 = RC.F_2M16                          # 0x37800000, 0x1177b4
ONE = RC.ONE
# damageDesc_getElement: id -> element (ids tested at 0x117e90-0x117ea0)
GET_IDS = {0x15: 1, 0x16: 2, 0x17: 3}

DROP_FLAGS = 0x4001                         # 0x117da0, used when the flags argument is 0
DROP_CFLAGS = 0x101000000                   # 0x8080 << 17 (0x117e1c/0x117e20) -> flag 0x100
PROP_SIZE = 0x248                           # 0x117e24

# The bodies: entry -> (class, slot, method).  Weapon1's slot 8 is setElement(hand,
# kind); the WeaponShield slot 8 is its own copy.  Slots 2-7 of both are the six fixed
# element setters (kinds 1, 6, 2, 3, 4, 5).
SLOTS = {
    0x11AFB0: ('Weapon1', 1, 'w1_set_part'),
    0x3C1D08: ('Weapon1', 2, 'set_kind_1'), 0x3C1D38: ('Weapon1', 3, 'set_kind_6'),
    0x3C1D68: ('Weapon1', 4, 'set_kind_2'), 0x3C1D98: ('Weapon1', 5, 'set_kind_3'),
    0x3C1DC8: ('Weapon1', 6, 'set_kind_4'), 0x3C1DF8: ('Weapon1', 7, 'set_kind_5'),
    0x11AFF0: ('Weapon1', 8, 'set_element'),
    0x11B020: ('Weapon1', 9, 'set_colour_a'), 0x11B050: ('Weapon1', 10, 'set_colour_b'),
    0x11B080: ('Weapon1', 11, 'w1_drop'), 0x11B0D0: ('Weapon1', 12, 'w1_show'),
    0x11B0F0: ('Weapon1', 13, 'w1_hide'), 0x11B110: ('Weapon1', 14, 'w1_carried'),
    0x11B130: ('Weapon1', 15, 'w1_part'), 0x11B148: ('Weapon1', 16, 'w1_element'),
    0x11B180: ('Weapon1', 17, 'w1_descriptor'),
    0x11BC18: ('WeaponShield', 1, 'ws_set_part'),
    0x3C23E0: ('WeaponShield', 2, 'set_kind_1'), 0x3C2410: ('WeaponShield', 3, 'set_kind_6'),
    0x3C2440: ('WeaponShield', 4, 'set_kind_2'), 0x3C2470: ('WeaponShield', 5, 'set_kind_3'),
    0x3C24A0: ('WeaponShield', 6, 'set_kind_4'), 0x3C24D0: ('WeaponShield', 7, 'set_kind_5'),
    0x3C2500: ('WeaponShield', 8, 'set_element'),
    0x3C2530: ('WeaponShield', 9, 'set_colour_a'), 0x3C2560: ('WeaponShield', 10, 'set_colour_b'),
    0x11BC90: ('WeaponShield', 11, 'ws_drop'), 0x11BD60: ('WeaponShield', 12, 'ws_show'),
    0x11BDA0: ('WeaponShield', 13, 'ws_hide'), 0x11BDE0: ('WeaponShield', 14, 'ws_carried'),
    0x3C2590: ('WeaponShield', 15, 'ws_part'), 0x3C25C0: ('WeaponShield', 16, 'ws_element'),
    0x11BE20: ('WeaponShield', 17, 'ws_descriptor'),
}
# the end of each body (for coverage): the next function's entry
BODY_END = {
    0x11AFB0: 0x11AFF0, 0x11AFF0: 0x11B020, 0x11B020: 0x11B050, 0x11B050: 0x11B080,
    0x11B080: 0x11B0D0, 0x11B0D0: 0x11B0F0, 0x11B0F0: 0x11B110, 0x11B110: 0x11B130,
    0x11B130: 0x11B148, 0x11B148: 0x11B180, 0x11B180: 0x11B198,
    0x3C1D08: 0x3C1D38, 0x3C1D38: 0x3C1D68, 0x3C1D68: 0x3C1D98, 0x3C1D98: 0x3C1DC8,
    0x3C1DC8: 0x3C1DF8, 0x3C1DF8: 0x3C1E28,
    0x11BC18: 0x11BC90, 0x11BC90: 0x11BD60, 0x11BD60: 0x11BDA0, 0x11BDA0: 0x11BDE0,
    0x11BDE0: 0x11BE20, 0x11BE20: 0x11BE40,
    0x3C23E0: 0x3C2410, 0x3C2410: 0x3C2440, 0x3C2440: 0x3C2470, 0x3C2470: 0x3C24A0,
    0x3C24A0: 0x3C24D0, 0x3C24D0: 0x3C2500, 0x3C2500: 0x3C2530, 0x3C2530: 0x3C2560,
    0x3C2560: 0x3C2590, 0x3C2590: 0x3C25C0, 0x3C25C0: 0x3C2600,
    BUILD_ELEMENT: 0x117D30, DROP_PART: 0x117E88, GET_ELEMENT: 0x117F08,
}

# the bodies with a result (the others leave v0 as their last callee or register had it)
RETURNS = {GET_ELEMENT} | {addr for addr, (_c, slot, _m) in SLOTS.items() if slot >= 14}

EXECUTED = {'creature_buildElementDamage': BUILD_ELEMENT, 'damageDesc_getElement': GET_ELEMENT,
            'creature_dropHeldPartAsProp': DROP_PART}
EXECUTED.update({'%s_slot%d' % (cls, slot): addr for addr, (cls, slot, _m) in SLOTS.items()})


def u_lt2(which):
    """sltiu reg, 2 on the sign-extended register."""
    return 0 <= s32(which) < 2


class Model(RC.Model):
    """The holder bodies on a memory image.  Callbacks: 'Skill.v11' (the skill's
    getStatTier2 through its +0x60 table), 'Creature.v16', 'model_getAttachPoint',
    'pool_new', 'PhProp_ctor'."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        return self.cb.get(name)(*args)

    def entry(self, fn, *args):
        """Run the body at fn (a SLOTS entry or one of the three helpers)."""
        if fn == BUILD_ELEMENT:
            return self.build_element_damage(args[1], args[2])
        if fn == GET_ELEMENT:
            return self.get_element(args[1])
        if fn == DROP_PART:
            return self.drop_held_part(*args)
        return getattr(self, SLOTS[fn][2])(*args)

    # ---- the helpers ----------------------------------------------------------------------
    def build_element_damage(self, desc, kind):
        """creature_buildElementDamage 0x1176e0 (x unused, descriptor, kind & 0xff).

        Frees the four effect slots (id 0xffff at +0x3c, +0x34, +0x2c, +0x24).  Kind 0 or
        7 and above: nothing else.  Otherwise a = slot 11 of the kind's Skill object
        (through its +0x60 table) with (0, trunc(g_levelMonsterLevel), 0); ONE SHARED
        DRAW d; v = trunc(float(a) * 0.2 * (float(d) * 2^-16)).  Slot 0 (always free) gets
        (id, a, a + v, 0) as halfwords."""
        kind &= 0xFF
        for k in (3, 2, 1, 0):
            self.w16(desc + 0x24 + 8 * k, 0xFFFF)
        if kind not in ELEMENTS:
            return
        ident, pointer = ELEMENTS[kind]
        skill = self.u32(pointer)
        level = C.to_int(self.u32(RC.G_LEVEL_MONSTER_LEVEL))
        a = self.table_call('Skill', skill, 0x60, 11, 0, level & M32, 0) & M32
        d = self.draw()
        scaled = C.mul(C.from_int(a), F_0_2)
        v = C.to_int(C.mul(scaled, C.mul(C.from_int(d), F_2M16)))
        self.w16(desc + 0x24, ident)
        self.w16(desc + 0x2A, 0)
        self.w16(desc + 0x26, a)
        self.w16(desc + 0x28, (a + v) & M32)

    def get_element(self, desc):
        """damageDesc_getElement 0x117e88 (x unused, descriptor): over the four effect ids
        (signed halfwords +0x24 + 8k), the last that is 0x15, 0x16, 0x17 gives 1, 2, 3;
        0x1f gives 6 and 0x18 gives 4; anything else keeps the answer; 0 when none."""
        out = 0
        for k in range(4):
            ident = self.s16(desc + 0x24 + 8 * k) & 0xFFFF
            if ident in GET_IDS:
                out = GET_IDS[ident]
            else:
                if ident == 0x1F:
                    out = 6
                if ident == 0x18:
                    out = 4
        return out

    def drop_held_part(self, x, part, c, definition, flags):
        """creature_dropHeldPartAsProp 0x117d30 (x unused, part, creature, definition,
        flags).  Nothing for part 0, creature 0, or creature object flag 2.  The
        definition (the creature's +0x24 when 0) has a record per part: words
        definition + 8 part (name) and + 4 (record, its byte +0x13 the bone, signed).
        Creature slot 16 gives the model; model_getAttachPoint(model, position copy,
        s16(facing - 0x4000), anim +0x114, bone; 1.0) fills the point, which starts as
        the position.  Flags: the argument, or 0x4001 when it is 0, with 0x100 added when
        a creature flag of 0x101000000 is set.  pool_new(0x248); with a block
        PhProp_ctor(block, point, definition word 0, the part's two words +0 and +8, 1,
        flags, 0; scale +0xdc).  No draw here."""
        part &= M32
        if not part or not c or self.u32(c + 0xC) & 2:
            return
        if not definition:
            definition = self.u32(c + 0x24)
        rec = (definition + 8 * part) & M32
        pos = self.vec(c + 0x10)
        out_flags = flags & M32 if flags else DROP_FLAGS
        bone = s8(self.u8(self.u32(rec + 4) + 0x13))
        model = self.call('Creature.v16', (c + self.s16(self.u32(c + 0x48) + 0x80)) & M32)
        facing = s16(self.u16(c + 0x38) - 0x4000)
        point = self.call('model_getAttachPoint', ONE, model, pos, facing, c + 0x114, bone)
        if not isinstance(point, tuple):           # the callee left the point as it was
            point = pos
        if self.u64(c + 0xA8) & DROP_CFLAGS:
            out_flags |= 0x100
        block = self.call('pool_new', PROP_SIZE)
        if block:
            self.call('PhProp_ctor', self.u32(c + 0xDC), block, point, self.u32(definition), self.u32(rec),
                      self.u32(rec + 8), 1, out_flags, 0)

    # ---- slots shared by both classes ----------------------------------------------------
    def _set_kind(self, h, which, kind):
        if u_lt2(which):
            self.build_element_damage(h + 0x50, kind)

    def set_kind_1(self, h, which, *_):
        self._set_kind(h, which, 1)

    def set_kind_6(self, h, which, *_):
        self._set_kind(h, which, 6)

    def set_kind_2(self, h, which, *_):
        self._set_kind(h, which, 2)

    def set_kind_3(self, h, which, *_):
        self._set_kind(h, which, 3)

    def set_kind_4(self, h, which, *_):
        self._set_kind(h, which, 4)

    def set_kind_5(self, h, which, *_):
        self._set_kind(h, which, 5)

    def set_element(self, h, which, kind=0, *_):
        """Slot 8 (hand, kind): kind & 0xff, hand 0 or 1 only."""
        self._set_kind(h, which, kind & 0xFF)

    def _colours(self, h, which, base, a, b, c, d):
        if u_lt2(which):
            self.w16(h + base + 6, d & 0xFF)
            self.w16(h + base, a & 0xFF)
            self.w16(h + base + 2, b & 0xFF)
            self.w16(h + base + 4, c & 0xFF)

    def set_colour_a(self, h, which, a=0, b=0, c=0, d=0, *_):
        """Slot 9 (hand, four bytes): the descriptor's first four halfwords (+0x60...)."""
        self._colours(h, which, 0x60, a, b, c, d)

    def set_colour_b(self, h, which, a=0, b=0, c=0, d=0, *_):
        """Slot 10: the next four (+0x68...)."""
        self._colours(h, which, 0x68, a, b, c, d)

    def _bits(self, h, value):
        self.w8(h + 4, value)

    # ---- Weapon1 ----------------------------------------------------------------------------
    def w1_set_part(self, h, which, part=0, *_):
        """Slot 1 (hand, part): only hand 1: +8 = part & 0xff, bit 0 set when non-zero,
        cleared when zero."""
        part &= 0xFF
        if s32(which) == 1:
            self.w8(h + 8, part)
            self._bits(h, self.u8(h + 4) | 1 if part else self.u8(h + 4) & 0xFE)

    def w1_drop(self, h, which, c=0, definition=0, flags=0, *_):
        """Slot 11 (hand, creature, definition, flags): hand 0 or 1 with bit 0: drop the
        part (the three arguments passed on unchanged) and clear bit 0."""
        if u_lt2(which) and self.u8(h + 4) & 1:
            self.drop_held_part(h + 4, self.u8(h + 8), c, definition, flags)
            self._bits(h, self.u8(h + 4) & 0xFE)

    def w1_show(self, h, which, *_):
        if u_lt2(which):
            self._bits(h, self.u8(h + 4) | 1)

    def w1_hide(self, h, which, *_):
        if u_lt2(which):
            self._bits(h, self.u8(h + 4) & 0xFE)

    def w1_carried(self, h, which, *_):
        return self.u8(h + 4) & 1 if s32(which) == 1 else 0

    def w1_part(self, h, which, *_):
        return self.u8(h + 8) if s32(which) == 1 else 0

    def w1_element(self, h, which, *_):
        """Slot 16: hand 1 tail-jumps to damageDesc_getElement(h + 4, h + 0x50)."""
        return self.get_element(h + 0x50) if s32(which) == 1 else 0

    def w1_descriptor(self, h, which, *_):
        return (h + 0x50) & M32 if s32(which) == 1 else 0

    # ---- WeaponShield -------------------------------------------------------------------------
    def ws_set_part(self, h, which, part=0, *_):
        """Slot 1 (hand, part): hand 2 stores +0x98 and bit 1; hand 1 +8 and bit 0."""
        part &= 0xFF
        if s32(which) == 2:
            self.w8(h + 0x98, part)
            self._bits(h, self.u8(h + 4) | 2 if part else self.u8(h + 4) & 0xFD)
        elif s32(which) == 1:
            self.w8(h + 8, part)
            self._bits(h, self.u8(h + 4) | 1 if part else self.u8(h + 4) & 0xFE)

    def ws_drop(self, h, which, c=0, definition=0, flags=0, *_):
        """Slot 11 (hand, creature, definition, flags): hand 0 or 1 with bit 0: drop the
        hand-1 part, clear bit 0; then hand 0 or 2 with bit 1: drop the +0x98 part, clear
        bit 1.  Skeleton_setState 0x14 calls it with hand 1, then hand 2."""
        if u_lt2(which) and self.u8(h + 4) & 1:
            self.drop_held_part(h + 4, self.u8(h + 8), c, definition, flags)
            self._bits(h, self.u8(h + 4) & 0xFE)
        if s32(which) in (0, 2) and self.u8(h + 4) & 2:
            self.drop_held_part(h + 4, self.u8(h + 0x98), c, definition, flags)
            self._bits(h, self.u8(h + 4) & 0xFD)

    def ws_show(self, h, which, *_):
        if u_lt2(which):
            self._bits(h, self.u8(h + 4) | 1)
        if s32(which) in (0, 2):
            self._bits(h, self.u8(h + 4) | 2)

    def ws_hide(self, h, which, *_):
        """Slot 13: hand 0 or 2 clears bit 1, but hand 0 or 1 SETS bit 0 (an ori where
        Weapon1's slot 13 has an andi)."""
        if u_lt2(which):
            self._bits(h, self.u8(h + 4) | 1)
        if s32(which) in (0, 2):
            self._bits(h, self.u8(h + 4) & 0xFD)

    def ws_carried(self, h, which, *_):
        if s32(which) == 2:
            return (self.u8(h + 4) >> 1) & 1
        return self.u8(h + 4) & 1 if s32(which) == 1 else 0

    def ws_part(self, h, which, *_):
        if s32(which) == 2:
            return self.u8(h + 0x98)
        return self.u8(h + 8) if s32(which) == 1 else 0

    def ws_element(self, h, which, *_):
        """Slot 16: hand 1 calls damageDesc_getElement (a linked call); else 0."""
        return self.get_element(h + 0x50) if s32(which) == 1 else 0

    def ws_descriptor(self, h, which, *_):
        return (h + 0x50) & M32 if s32(which) == 1 else 0


# The element a Skeleton's constructor asks for (ref_combat_ctors.skeleton_ctor) -> the
# holder slot it calls, the kind that slot builds, the descriptor id, and the element
# damageDesc_getElement reports, which picks Skeleton_run state 8's arrow.
SKELETON_ELEMENTS = {1: (4, 2, 0x16, 2), 2: (2, 1, 0x15, 1), 3: (3, 6, 0x1F, 6)}
