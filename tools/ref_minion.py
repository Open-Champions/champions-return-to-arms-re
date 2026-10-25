"""ref_minion.py - the start of Minion_run 0x2862c0 (slot 4 of the Minion class, table 0x5164a8): the
frame's common calls and, in them, the placement of a held Soul (0x286364-0x2863e0), up to the
state dispatch at 0x2863e4.  docs/spec/minion-place.md is the prose; tools/difftest_minion.py
runs the original against it.

Pseudo-code in my own words; every constant carries the address of the instruction that loads it.
The model works on a memory image with the accessors of ref_creature.Model.
"""
from ref_creature import M32, Model as BaseModel, s16

MINION_RUN = 0x2862C0
OFFSET_HELD, OFFSET_DEF, OFFSET_STATE, OFFSET_ANIM, OFFSET_SCALE = 0x3C8, 0x24, 0x232, 0x114, 0xDC
F_ONE, F_KNOCKBACK = 0x3F800000, 0x3E4CCCCC          # 0x286320 / 0x286334
STATE_LIMIT = 0x18                                   # sltiu at 0x2863e8
VTABLE_SLOT_ADJUST = 0xB8                            # addiu at 0x286350: the slot's (adjust, function) pair


class Model(BaseModel):
    def minion_run_prefix(self, this):
        """Minion_run up to the state dispatch.  `model` is `(this + 0x24) -> +0xc`.

        1. Creature_processDamage(this, model); a = Creature_run(this, model); a non-zero result
           ends the call (the branch to the epilogue 0x287400, *likely*: nothing else runs).
        2. Creature_updateActive(this); Creature_stepAnim(this; 1.0); Creature_applyKnockback(this;
           0.2), its result kept in a callee-saved register for the states.
        3. The virtual call through the table word +0x48 at offset 0xb8: (this + the 16-bit
           adjustment, 0).
        4. Placement.  When the held handle `+0x3c8` is non-null: the held object is the node's
           word +0xc.  p = model_getAttachPoint(scale +0xdc; model, a stack copy of the position
           +0x10..0x18, s16 facing +0x38, anim state this + 0x114, index 0, out p, out d).  The
           held object's position +0x10..0x18 = p; its facing +0x38 = the Minion's, as the low
           16 bits; obj_updateGridCell(held).
        5. State s16 +0x232 at 0x18 or above ends the call; below that the state dispatch
           (not modelled: refused)."""
        d = self.u32(this + OFFSET_DEF)
        mdl = self.u32(d + 0xC)
        self.call('Creature_processDamage', this, mdl)
        if self.call('Creature_run', this, mdl):
            return 'early'
        self.call('Creature_updateActive', this)
        self.call('Creature_stepAnim', this, F_ONE)
        self.call('Creature_applyKnockback', this, F_KNOCKBACK)
        table = self.u32(this + 0x48) + VTABLE_SLOT_ADJUST
        self.call('Minion.slot23', (this + self.s16(table)) & M32, 0)
        node = self.u32(this + OFFSET_HELD)
        if node:
            held = self.u32(node + 0xC)
            point, _dir = self.call('model_getAttachPoint', mdl, self.vec(this + 0x10), self.s16(this + 0x38),
                                    this + OFFSET_ANIM, 0, self.u32(this + OFFSET_SCALE))
            self.wvec(held + 0x10, point)
            self.w16(held + 0x38, self.u16(this + 0x38))
            self.call('obj_updateGridCell', held)
        if 0 <= self.s16(this + OFFSET_STATE) < STATE_LIMIT:          # sltiu on the sign-extended halfword
            raise NotImplementedError('the Minion state dispatch (jump table) is not modelled')
        return 'done'
