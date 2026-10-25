"""ref_holder_slots.py - the weapon holder's virtual slots 18-24 (drawing, the per-frame
effect update, save and load) for Weapon1 (table 0x50cf40), WeaponShield (0x50cda0) and
Weapon2 (0x50ce70); creature_drawHeldPart, which slot 20 reaches; and Weapon2's slots 8
and 16, which its slots 23 and 24 reach through the table.

Reference contract, executed against the original by tools/difftest_holder_slots.py
(docs/spec/weapon-holder-slots.md is the prose).  Builds on tools/ref_weapon_holder.py
(slots 1-17 of Weapon1 and WeaponShield, the element helpers), whose Model this one
extends.

The holder h (as in ref_weapon_holder): word +0 the table; byte +4 the hand bits (bit 0
hand 1 carried, bit 1 hand 2); byte +8 the hand-1 part; +0xc the hand-1 effect block
(written only by fx_modelStatusEffects, FINDINGS D37); +0x50 the hand-1 damage
descriptor.  WeaponShield and Weapon2: byte +0x98 the hand-2 part.  Weapon2 only: +0x9c
the hand-2 effect block and +0xe0 the hand-2 damage descriptor.

A part definition d (the skelcom block 0x5023e0 for a Skeleton, or the creature's +0x24)
is read as words: d + 8p + 4 (the part's model, whose byte +0x13 is its bone) and
d + 8p + 0xc (the word model_drawPart takes as its texture).

    slot 18  draw parts on a parent      model_drawPart per carried hand
    slot 19  draw one given part         model_drawPart (hand-1 bit only)
    slot 20  draw parts at their bones   creature_drawHeldPart per carried hand
    slot 21  effect update (definition)  fx_modelStatusEffects behind isNearView(480)
    slot 22  effect update (model)       the same with an explicit model
    slot 23  save                        bits, parts, elements -> 3, 4 or 5 bytes
    slot 24  load                        the inverse; the elements are REBUILT (shared draw)
"""
import ref_core as C
import ref_creature as RC
import ref_weapon_holder as WH
from ref_creature import M32, M64, s8, s16, s32

VT_WEAPON1, VT_WEAPONSHIELD, VT_WEAPON2 = WH.VT_WEAPON1, WH.VT_WEAPONSHIELD, WH.VT_WEAPON2
DRAW_HELD_PART = 0x117F08                   # creature_drawHeldPart (x, part, creature)
W2_SET_ELEMENT, W2_GET_ELEMENT = 0x3C2238, 0x11B8C8     # Weapon2 slots 8 and 16

NEAR_VIEW_RADIUS = 0x43F00000               # 480.0: lui at 0x11b320, 0x11b450, 0x1180d4, 0x1181b4
DESC2, FX2 = 0xE0, 0x9C                     # Weapon2's hand-2 descriptor and effect block

# entry -> (class, slot, method)
SLOTS = {
    0x11B198: ('Weapon1', 18, 'w1_draw_on_parent'),
    0x11B208: ('Weapon1', 19, 'draw_given_part'),         # also WeaponShield 19, Weapon2 19
    0x11B270: ('Weapon1', 20, 'w1_draw_at_bones'),
    0x11B2A8: ('Weapon1', 21, 'w1_effects'),               # also WeaponShield 21
    0x11B3E8: ('Weapon1', 22, 'w1_effects_model'),         # also WeaponShield 22, Weapon2 22
    0x11B510: ('Weapon1', 23, 'w1_save'),
    0x11B580: ('Weapon1', 24, 'w1_load'),
    0x11BE40: ('WeaponShield', 18, 'two_draw_on_parent'),
    0x11BF40: ('WeaponShield', 20, 'two_draw_at_bones'),
    0x11BFB8: ('WeaponShield', 23, 'ws_save'),
    0x11C048: ('WeaponShield', 24, 'ws_load'),
    0x11B948: ('Weapon2', 18, 'two_draw_on_parent'),      # the same code as WeaponShield 18
    0x11BA48: ('Weapon2', 20, 'two_draw_at_bones'),       # the same code as WeaponShield 20
    0x118058: ('Weapon2', 21, 'w2_effects'),
    0x11BAC0: ('Weapon2', 23, 'w2_save'),
    0x11BB70: ('Weapon2', 24, 'w2_load'),
    W2_SET_ELEMENT: ('Weapon2', 8, 'w2_set_element'),
    W2_GET_ELEMENT: ('Weapon2', 16, 'w2_get_element'),
}
# the end of each body (for coverage): the next function's entry
BODY_END = {
    0x11B198: 0x11B208, 0x11B208: 0x11B270, 0x11B270: 0x11B2A8, 0x11B2A8: 0x11B3E8,
    0x11B3E8: 0x11B510, 0x11B510: 0x11B580, 0x11B580: 0x11B5F0,
    0x11BE40: 0x11BF40, 0x11BF40: 0x11BFB8, 0x11BFB8: 0x11C048, 0x11C048: 0x11C0D0,
    0x11B948: 0x11BA48, 0x11BA48: 0x11BAC0, 0x118058: 0x118280, 0x11BAC0: 0x11BB70,
    0x11BB70: 0x11BC18, W2_SET_ELEMENT: 0x3C22B0, W2_GET_ELEMENT: 0x11B920,
    DRAW_HELD_PART: 0x118058,
}
RETURNS = {0x11B510, 0x11B580, 0x11BFB8, 0x11C048, 0x11BAC0, 0x11BB70, W2_GET_ELEMENT}

# Which body each class's table holds in slots 18-24 (Observed in the tables).
TABLE_SLOTS = {
    'Weapon1': {18: 0x11B198, 19: 0x11B208, 20: 0x11B270, 21: 0x11B2A8, 22: 0x11B3E8, 23: 0x11B510, 24: 0x11B580},
    'WeaponShield': {18: 0x11BE40, 19: 0x11B208, 20: 0x11BF40, 21: 0x11B2A8, 22: 0x11B3E8, 23: 0x11BFB8,
                     24: 0x11C048},
    'Weapon2': {18: 0x11B948, 19: 0x11B208, 20: 0x11BA48, 21: 0x118058, 22: 0x11B3E8, 23: 0x11BAC0, 24: 0x11BB70},
}

EXECUTED = {'creature_drawHeldPart': DRAW_HELD_PART}
for _addr, (_cls, _slot, _m) in SLOTS.items():
    EXECUTED.setdefault('%s_slot%d' % (_cls, _slot), _addr)


def u_lt2(which):
    return 0 <= s32(which) < 2


class Model(WH.Model):
    """Slots 18-24 on a memory image.  Callbacks (besides ref_weapon_holder's):
    'model_drawPart', 'Creature.v16', 'model_getAttachPoint' (answers the point),
    'model_getAttachWorldMatrix' (answers twelve words), 'model_draw', 'isNearView',
    'fx_modelStatusEffects'.  A holder slot called through the holder's own table runs
    here when its body is modelled (here or in ref_weapon_holder), else it is the
    callback 'Holder.v<slot>'."""

    def entry(self, fn, *args, f12=0):
        if fn == DRAW_HELD_PART:
            return self.draw_held_part(*args)
        if fn in SLOTS:
            method = getattr(self, SLOTS[fn][2])
            if fn in (0x11B2A8, 0x11B3E8, 0x118058):
                return method(*args, f12=f12)
            return method(*args)
        return WH.Model.entry(self, fn, *args)

    def holder_vcall(self, h, slot, *args):
        """A call through the holder's own table (adjusted 'this')."""
        table = self.u32(h)
        this = (h + self.s16(table + 8 * slot)) & M32
        fn = self.u32(table + 8 * slot + 4)
        if fn in SLOTS or fn in WH.SLOTS:
            return self.entry(fn, this, *args)
        return self.call('Holder.v%d' % slot, this, *args)

    # ---- creature_drawHeldPart 0x117f08 ---------------------------------------------------
    def draw_held_part(self, x, part, c):
        """creature_drawHeldPart 0x117f08 (x unused, part, creature).  Nothing for part 0
        or creature 0 (full registers), nor when the part's bone (signed byte +0x13 of the
        word definition + 8 part + 4, the definition being the creature's +0x24) is
        negative.  Otherwise: model = creature slot 16; model_getAttachPoint(scale +0xdc;
        model, position copy, s16 facing +0x38, anim +0x114, bone, point out, 0); model =
        slot 16 again; model_getAttachWorldMatrix(scale; model, position copy, facing,
        anim, bone, matrix out); model_draw(rec, rec, 1, point, matrix, anim +0x114, the
        64-bit +0x220, 0; stack 0) with rec the part's model word.  No stores, no draws."""
        part &= M32
        if not part or not c:
            return
        rec_word = lambda: self.u32((self.u32(c + 0x24) + 8 * part + 4) & M32)
        bone = s8(self.u8(rec_word() + 0x13))
        if bone < 0:
            return
        scale, pos = self.u32(c + 0xDC), self.vec(c + 0x10)
        facing = self.s16(c + 0x38)
        model = self.call('Creature.v16', (c + self.s16(self.u32(c + 0x48) + 0x80)) & M32)
        point = self.call('model_getAttachPoint', scale, model, pos, facing, c + 0x114, bone, 0)
        model = self.call('Creature.v16', (c + self.s16(self.u32(c + 0x48) + 0x80)) & M32)
        matrix = self.call('model_getAttachWorldMatrix', scale, model, pos, facing, c + 0x114, bone)
        rec = rec_word()
        wide = self.u64(c + 0x220)
        self.call('model_draw', rec, rec, 1, tuple(point), tuple(matrix), c + 0x114,
                  (wide & M32, wide >> 32), 0, 0)

    # ---- slots 18 and 19: model_drawPart ----------------------------------------------------
    def _draw_part(self, definition, part, parent, chain):
        base = (definition + 8 * part) & M32
        self.call('model_drawPart', self.u32(base + 4), self.u32(base + 0xC), 0, parent, chain, -1, -1, 0)

    def _hand_draw(self, h, bit, part_off, definition, parent, chain):
        if not self.u8(h + 4) & bit:
            return
        part = self.u8(h + part_off)
        if part and definition and parent and chain:
            self._draw_part(definition, part, parent, chain)

    def w1_draw_on_parent(self, h, definition=0, parent=0, chain=0, *_):
        """Slot 18 (definition, parent, chain): with bit 0, part +8 non-zero and all three
        arguments non-zero: model_drawPart(word d+8p+4, word d+8p+0xc, 0, parent, chain,
        -1, -1, 0).  Skeleton_draw passes (skelcom, the model from creature slot 16, the
        result of Creature_draw)."""
        self._hand_draw(h, 1, 8, definition, parent, chain)

    def two_draw_on_parent(self, h, definition=0, parent=0, chain=0, *_):
        """Slot 18 of WeaponShield and Weapon2: hand 1 as Weapon1's, then bit 1 with part
        +0x98 the same way."""
        self._hand_draw(h, 1, 8, definition, parent, chain)
        self._hand_draw(h, 2, 0x98, definition, parent, chain)

    def draw_given_part(self, h, part=0, tex=0, parent=0, chain=0, *_):
        """Slot 19 (part, tex, parent, chain), shared by all three: with bit 0 and the four
        arguments non-zero, model_drawPart(part, tex, 0, parent, chain, -1, -1, 0).  The
        holder's own part is not read.  Skelight_draw calls it."""
        if self.u8(h + 4) & 1 and part and tex and parent and chain:
            self.call('model_drawPart', part, tex, 0, parent, chain, -1, -1, 0)

    # ---- slot 20: creature_drawHeldPart ---------------------------------------------------------
    def w1_draw_at_bones(self, h, c=0, *_):
        """Slot 20 (creature): bit 0 -> creature_drawHeldPart(h + 4, part +8, creature)."""
        if self.u8(h + 4) & 1:
            self.draw_held_part(h + 4, self.u8(h + 8), c)

    def two_draw_at_bones(self, h, c=0, *_):
        """Slot 20 of WeaponShield and Weapon2: hand 1 as Weapon1's, then bit 1 -> the same
        with part +0x98."""
        if self.u8(h + 4) & 1:
            self.draw_held_part(h + 4, self.u8(h + 8), c)
        if self.u8(h + 4) & 2:
            self.draw_held_part(h + 4, self.u8(h + 0x98), c)

    # ---- slots 21 and 22: the effect update ------------------------------------------------------
    def _effect(self, h, desc_off, block_off, model_word, c, f12):
        """The common tail: c not hidden (object flag 2 at +0xc), isNearView(c + 0x10;
        480), creature byte +0x231 bit 8 clear; model = creature slot 16;
        fx_modelStatusEffects(f12, scale +0xdc; descriptor, model word, effect block,
        position copy, s16 facing, model, anim +0x114, 6 <= u16 state +0x232 <= 15;
        stack 0, 0)."""
        if self.u32(c + 0xC) & 2:
            return
        if not self.call('isNearView', c + 0x10, self.vec(c + 0x10), NEAR_VIEW_RADIUS):
            return
        if self.u8(c + 0x231) & 8:
            return
        model = self.call('Creature.v16', (c + self.s16(self.u32(c + 0x48) + 0x80)) & M32)
        attacking = 1 if ((self.u16(c + 0x232) - 6) & M64) < 10 else 0
        self.call('fx_modelStatusEffects', f12 & M32, self.u32(c + 0xDC), h + desc_off, model_word, h + block_off,
                  self.vec(c + 0x10), self.s16(c + 0x38), model, c + 0x114, attacking, 0, 0)

    def w1_effects(self, h, definition=0, c=0, *_, f12=0):
        """Slot 21 (definition, creature; f12), Weapon1 and WeaponShield: hand 1 only.  Bit
        0, part +8, definition and creature non-zero -> the tail with descriptor +0x50,
        block +0xc and the model word d + 8p + 4.  Skeleton_run's prologue calls it with
        (skelcom 0x5023e0, c; 0.5) every tick."""
        if not self.u8(h + 4) & 1:
            return
        part = self.u8(h + 8)
        if part and definition and c:
            self._effect(h, 0x50, 0xC, self.u32((definition + 8 * part + 4) & M32), c, f12)

    def w1_effects_model(self, h, model_word=0, c=0, *_, f12=0):
        """Slot 22 (model word, creature; f12), shared by all three: bit 0 and both
        arguments non-zero -> the tail with descriptor +0x50, block +0xc and the given
        word.  The part +8 is not read.  Skelight_run calls it."""
        if self.u8(h + 4) & 1 and model_word and c:
            self._effect(h, 0x50, 0xC, model_word, c, f12)

    def w2_effects(self, h, definition=0, c=0, *_, f12=0):
        """Weapon2 slot 21: hand 1 as w1_effects; then bit 1, part +0x98, definition and
        creature -> the tail with descriptor +0xe0 and block +0x9c (isNearView asked
        again)."""
        if self.u8(h + 4) & 1:
            part = self.u8(h + 8)
            if part and definition and c:
                self._effect(h, 0x50, 0xC, self.u32((definition + 8 * part + 4) & M32), c, f12)
        if self.u8(h + 4) & 2:
            part = self.u8(h + 0x98)
            if part and definition and c:
                self._effect(h, DESC2, FX2, self.u32((definition + 8 * part + 4) & M32), c, f12)

    # ---- slots 23 and 24: save and load ----------------------------------------------------------
    def _element(self, h, hand):
        return self.holder_vcall(h, 16, hand) & 0xFF

    def w1_save(self, h, buf, *_):
        """Slot 23 (buffer) -> 3: [bits +4, part +8, slot 16 (1) & 0xff]."""
        self.w8(buf, self.u8(h + 4))
        self.w8(buf + 1, self.u8(h + 8))
        self.w8(buf + 2, self._element(h, 1))
        return 3

    def ws_save(self, h, buf, *_):
        """WeaponShield slot 23 -> 4: [bits, part +8, element of hand 1, part +0x98]."""
        self.w8(buf, self.u8(h + 4))
        self.w8(buf + 1, self.u8(h + 8))
        self.w8(buf + 2, self._element(h, 1))
        self.w8(buf + 3, self.u8(h + 0x98))
        return 4

    def w2_save(self, h, buf, *_):
        """Weapon2 slot 23 -> 5: [bits, part +8, element of hand 1, part +0x98, element of
        hand 2]."""
        self.w8(buf, self.u8(h + 4))
        self.w8(buf + 1, self.u8(h + 8))
        self.w8(buf + 2, self._element(h, 1))
        self.w8(buf + 3, self.u8(h + 0x98))
        self.w8(buf + 4, self._element(h, 2))
        return 5

    def w1_load(self, h, buf, *_):
        """Slot 24 (buffer) -> 3: bits +4 = buf[0], part +8 = buf[1], then slot 8 (1,
        buf[2]): the element is rebuilt by creature_buildElementDamage (ONE SHARED DRAW for
        kinds 1-6)."""
        self.w8(h + 4, self.u8(buf))
        self.w8(h + 8, self.u8(buf + 1))
        self.holder_vcall(h, 8, 1, self.u8(buf + 2))
        return 3

    def ws_load(self, h, buf, *_):
        """WeaponShield slot 24 -> 4: as Weapon1's, then part +0x98 = buf[3] (after the
        element is rebuilt)."""
        self.w8(h + 4, self.u8(buf))
        self.w8(h + 8, self.u8(buf + 1))
        self.holder_vcall(h, 8, 1, self.u8(buf + 2))
        self.w8(h + 0x98, self.u8(buf + 3))
        return 4

    def w2_load(self, h, buf, *_):
        """Weapon2 slot 24 -> 5: as WeaponShield's, then slot 8 (2, buf[4])."""
        self.w8(h + 4, self.u8(buf))
        self.w8(h + 8, self.u8(buf + 1))
        self.holder_vcall(h, 8, 1, self.u8(buf + 2))
        self.w8(h + 0x98, self.u8(buf + 3))
        self.holder_vcall(h, 8, 2, self.u8(buf + 4))
        return 5

    # ---- Weapon2 slots 8 and 16 ---------------------------------------------------------------
    def w2_set_element(self, h, which, kind=0, *_):
        """Weapon2 slot 8 (hand, kind): kind & 0xff; hand 0 or 1 builds descriptor +0x50,
        then hand 0 or 2 builds +0xe0 (hand 0: both, two shared draws)."""
        kind &= 0xFF
        if u_lt2(which):
            self.build_element_damage(h + 0x50, kind)
        if s32(which) in (0, 2):
            self.build_element_damage(h + DESC2, kind)

    def w2_get_element(self, h, which, *_):
        """Weapon2 slot 16 (hand): hand 2 -> damageDesc_getElement(+0xe0) (a tail jump),
        hand 1 -> the same on +0x50, else 0."""
        if s32(which) == 2:
            return self.get_element(h + DESC2)
        if s32(which) == 1:
            return self.get_element(h + 0x50)
        return 0


# What survives a save and load: the element a save writes (damageDesc_getElement's
# answer) -> the kind slot 8 rebuilds -> the id it puts in slot 0 of the descriptor.
# Element 5 is never written (id 0x26 is not reported), so a kind-5 element is lost.
ROUND_TRIP = {0: (0, None), 1: (1, 0x15), 2: (2, 0x16), 3: (3, 0x17), 4: (4, 0x18), 6: (6, 0x1F)}
