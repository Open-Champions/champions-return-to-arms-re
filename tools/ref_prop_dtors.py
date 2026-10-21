#!/usr/bin/env python3
"""ref_prop_dtors.py - three small bodies the round-4 probe reached once the shattered
skeleton's bones, the gut chunks and the gold pile ran (docs/spec/full-placement.md 7):

    PhProp_dtor            0x3c2fc8   slot 1 of PhProp   (table 0x511ba8)
    GutChunk_dtor          0x3c4d48   slot 1 of GutChunk (table 0x50f3b8)
    Prop_dtor              0x3c2d30   slot 1 of Prop     (table 0x511d58): a resting prop
    ItemProp_dtor          0x3c2ed8   slot 1 of ItemProp (table 0x511c38)
    Gold_dtor              0x3c31d8   slot 1 of Gold     (table 0x511a88)
    anim_advanceUnitSpeed  0x1709d8   Gold_run's clip step

Written from reading the code (pseudo-code in my own words); tools/difftest_prop_dtors.py
executes the original against it.  The base chain is not modelled here: GameObject_dtor
0x14cf90 is tools/ref_combat_monsters.py's (executed by difftest_combat_monsters), and
anim_advance 0x16d748 and AnimState_dtor 0x171098 are tools/ref_anim.py's (executed by
difftest_anim).
"""

M32 = 0xFFFFFFFF

PHPROP_DTOR = 0x3C2FC8
GUTCHUNK_DTOR = 0x3C4D48
PROP_DTOR = 0x3C2D30
ITEMPROP_DTOR = 0x3C2ED8
GOLD_DTOR = 0x3C31D8
ANIM_ADVANCE_UNIT_SPEED = 0x1709D8

GAMEOBJECT_DTOR = 0x14CF90
POOL_FREE = 0x150470
ANIM_ADVANCE = 0x16D748
ANIMSTATE_DTOR = 0x171098

VT_PROP = 0x511D58                              # Prop's table, stored by four of the destructors
VT_GOLD = 0x511A88                              # Gold's own table, stored by Gold_dtor
ONE = 0x3F800000                                # 1.0, built in the body (lui 0x3f80), not loaded

EXECUTED = {'PhProp_dtor': PHPROP_DTOR, 'GutChunk_dtor': GUTCHUNK_DTOR, 'Prop_dtor': PROP_DTOR,
            'ItemProp_dtor': ITEMPROP_DTOR, 'Gold_dtor': GOLD_DTOR,
            'anim_advanceUnitSpeed': ANIM_ADVANCE_UNIT_SPEED}
# slot 1 of the five classes
CLASS_BODIES = {PHPROP_DTOR: (1, 'prop_dtor'), GUTCHUNK_DTOR: (1, 'prop_dtor'), PROP_DTOR: (1, 'prop_dtor'),
                ITEMPROP_DTOR: (1, 'prop_dtor'), GOLD_DTOR: (1, 'gold_dtor')}


class Model:
    """Bodies over a memory with w32 and a call(name, *args, f12=None) callback."""

    def __init__(self, w32, call):
        self.w32, self.call = w32, call

    def prop_dtor(self, obj, flags):
        """PhProp_dtor 0x3c2fc8, GutChunk_dtor 0x3c4d48, Prop_dtor 0x3c2d30 and ItemProp_dtor
        0x3c2ed8, the same 24 instructions and a padding nop each: +0x48 = 0x511d58 (Prop), GameObject_dtor(obj, 0); then, when bit 0 of flags is set,
        pool_free(obj) as a tail jump.  No handle of the class is cleared: the rigid body
        lives inside the block.  Returns nothing (the free's result is passed through)."""
        self.w32(obj + 0x48, VT_PROP)
        self.call('GameObject_dtor', obj, 0)
        if flags & 1:
            return self.call('pool_free', obj)
        return None

    def gold_dtor(self, obj, flags):
        """Gold_dtor 0x3c31d8: +0x48 = 0x511a88 (Gold's own table), AnimState_dtor(obj +
        0x58, 2) (the coin clip's state), GameObject_dtor(obj, 0); then, when bit 0 of flags
        is set, pool_free(obj) as a tail jump."""
        self.w32(obj + 0x48, VT_GOLD)
        self.call('AnimState_dtor', obj + 0x58, 2)
        self.call('GameObject_dtor', obj, 0)
        if flags & 1:
            return self.call('pool_free', obj)
        return None

    def anim_advance_unit_speed(self, state, sound, root, yaw):
        """anim_advanceUnitSpeed 0x1709d8 (a0 state, a1 sound position, a2 root delta out,
        a3 yaw out): f12 = 1.0 and a tail jump to anim_advance with the four arguments
        unchanged; its result is the result."""
        return self.call('anim_advance', state, sound, root, yaw, f12=ONE)
