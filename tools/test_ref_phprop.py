#!/usr/bin/env python3
"""test_ref_phprop.py - unit tests of tools/ref_phprop.py that need no game files.

Made-up memory: the draw counts of a gut chunk (one shared, seven own), the launch bits'
velocities and overwrite order, the damping option, the item-record branch with its sound,
the bounds centre, the part-mask bit index and sign extension, and the spin factor.  Whether
the model matches the game is tools/difftest_phprop.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_phprop as PP                         # noqa: E402

f32 = C.f32
OBJ, ITEM, POS = 0x100000, 0x110000, 0x120000
M32 = 0xFFFFFFFF


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & M32


class Fixture(unittest.TestCase):
    bounds = (-4, -6, 0, 4, 6, 10)

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = PP.Model(self.mem, self)
        self.mem.poke(RC.G_RAND_SEED, 4, 0x1234)
        for k, text in enumerate((b'fx.lmp', b'gutchunks.vif', b'gutchunks.tex')):
            for j, b in enumerate(text + b'\0'):
                self.mem.poke(0x130000 + 0x100 * k + j, 1, b)
        for j, b in enumerate(b'game_swish_chest%d.anm\0'):
            self.mem.poke(PP.S_SWISH_FORMAT + j, 1, b)

    def get(self, name):
        if name == 'model_getBounds':
            return lambda *args: tuple(v & M32 for v in self.bounds)
        if name in ('res_find', 'obj_getPropInt', 'sound_playOnObject'):
            return lambda *args: 0
        return None

    def names(self):
        return 0x130000, 0x130100, 0x130200

    def calls(self, name):
        return [args for n, args in self.model.calls if n == name]


class Draws(Fixture):
    def test_gut_chunk_one_shared_seven_own(self):
        """GutChunk_ctor's launch 0xb41: GameObject_ctor's shared draw, then facing (1),
        launch bit 1 (2), bit 0x40 (1), spin (3): seven own draws, no sound."""
        self.mem.poke(PP.R3.GUT_BASE, 4, 0x130000)
        self.mem.poke(PP.R3.GUT_BASE + 0x50, 4, 0x130100)
        self.mem.poke(PP.R3.GUT_BASE + 0x58, 4, 0x130200)
        self.model.gutchunk_ctor(OBJ, (f32(1.0), f32(2.0), f32(3.0)), 2, 0)
        self.assertEqual(self.model.draws, 1)
        seed = lcg(0x1234) >> 16                                       # the 16-bit draw seeds +0x44
        for _ in range(7):
            seed = lcg(seed)
        self.assertEqual(self.mem.load(OBJ + 0x44, 4), seed)
        self.assertEqual(self.calls('sound_playOnObject'), [])
        self.assertEqual(self.mem.load(OBJ + 0x23C, 4), PP.F_DAMP_LIGHT)     # 0xb41 has 0x800
        self.assertEqual(self.mem.load(OBJ + 0x140, 2), 6)                   # 0x100 -> 2, 0x200 -> 4

    def test_item_sound_draw(self):
        self.mem.poke(ITEM + 8, 4, 0x20000)
        self.model.phprop_ctor(OBJ, (0, 0, 0), *self.names(), 0, 0x8, ITEM, C.ONE)
        self.assertEqual(self.mem.load(OBJ + 0x238, 1), 1)
        self.assertEqual(self.mem.load(OBJ + 0x34, 4), PP.ITEM_NAME_FIELD)
        texts = self.calls('libc_sprintf')
        self.assertEqual(len(texts), 1)
        self.assertIn(texts[0][1], (1, 2, 3))
        self.assertEqual(self.calls('res_find')[-1][0], PP.S_FX_LUMP)
        self.assertEqual(self.mem.load(OBJ + 0x19C, 4), 0)                   # record bit 0x20000 -> 0x1000
        flags = self.mem.load(OBJ + 0xC, 4)
        self.assertTrue(flags & 0x100000)
        self.assertFalse(flags & 0x4800)

    def test_no_sound_without_bits(self):
        self.model.phprop_ctor(OBJ, (0, 0, 0), *self.names(), 0, 0x2, ITEM, C.ONE)
        self.assertEqual(self.calls('libc_sprintf'), [])


class Launch(Fixture):
    def test_later_bits_overwrite(self):
        self.model.prop_launch(OBJ, 0x1 | 0x8)
        seed = self.mem.load(OBJ + 0x44, 4)
        self.assertNotEqual(seed, 0)
        # four draws; the last two are bit 8's: (f - 0.5) x 224
        s = 0
        draws = []
        for _ in range(4):
            s = lcg(s)
            draws.append(s >> 16)
        want = C.mul(C.sub(C.mul(C.from_int(draws[3]), PP.F_2M16), PP.HALF), PP.F_224)
        self.assertEqual(self.mem.load(OBJ + 0x100, 4), want)

    def test_life_and_stop(self):
        self.model.prop_launch(OBJ, 0x80)
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), 0)
        self.assertEqual(self.calls('obj_stopRunning'), [(OBJ,)])
        self.model.calls.clear()
        self.model.prop_launch(OBJ, 0x80 | 0x100)
        self.assertEqual(self.calls('obj_stopRunning'), [])

    def test_damping_option(self):
        self.mem.poke(PP.G_PROP_OPTIONS, 4, 0x100)
        self.mem.poke(OBJ + 0x30, 4, f32(900.0))
        self.model.prop_launch(OBJ, 0)
        self.assertEqual(self.mem.load(OBJ + 0x30, 4), f32(100.0))
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), 0xB4)


class Shape(Fixture):
    bounds = (-5, -6, -3, 4, 7, 10)

    def test_centre_and_bit_four(self):
        self.model.prop_ctor_named_launch(OBJ, (f32(100.0), f32(0.0), f32(0.0)), *self.names(), 0, 4)
        self.assertEqual(self.mem.load(OBJ + 0xF0, 4), f32(-1.0))           # (-5 + 4) >> 1
        self.assertEqual(self.mem.load(OBJ + 0xF4, 4), f32(0.0))
        self.assertEqual(self.mem.load(OBJ + 0xF8, 4), f32(3.0))
        self.assertEqual(self.mem.load(OBJ + 0x108, 4), f32(6.0))
        self.assertEqual(self.mem.load(OBJ + 0x10, 4), f32(99.0))
        self.assertEqual(self.calls('obj_updateGridCell')[0], (OBJ,))

    def test_mask_sign_extended_and_index(self):
        self.model.prop_ctor_named_launch(OBJ, (0, 0, 0), *self.names(), 0x80000000, 0)
        self.assertEqual(self.mem.load(OBJ + 0xE8, 8), 0xFFFFFFFF80000000)
        self.assertEqual(PP.bit_index(0), -1)
        self.assertEqual(PP.bit_index(1 << 63), 63)
        self.mem.poke(OBJ + 0xE8, 8, 0)
        self.model.phprop_init_physics(OBJ, 0)
        self.assertEqual(self.mem.load(OBJ + 0x22C, 4), M32)

    def test_spin_factor(self):
        for launch, factor in ((0, 2.0), (0x10, 10.0), (0x400, 10.0)):
            self.mem.poke(OBJ + 0x44, 4, 0)
            self.model.phprop_init_physics(OBJ, launch)
            f = C.mul(C.from_int(lcg(0) >> 16), PP.F_2M16)
            self.assertEqual(self.mem.load(OBJ + 0x1C8, 4), C.mul(C.sub(C.add(f, f), C.ONE), f32(factor)))


class Ctor2(Fixture):
    bounds = (0, 0, 0, 0, 0, 0)

    def get(self, name):
        if name == 'anim_getJointMatrix':
            # a turn of a quarter about z and a lift of 10
            return lambda *args: [0, f32(1.0), 0, f32(-1.0), 0, 0, 0, 0, f32(1.0), 0, 0, f32(10.0)]
        if name == 'model_getMeshJoint':
            return lambda *args: 3
        return Fixture.get(self, name)

    def test_joint_and_flags(self):
        pos = (f32(100.0), f32(0.0), f32(0.0))
        self.model.phprop_ctor2(OBJ, pos, 0, 0x140000, 0x150000, *self.names(), 1 << 40, 0x107, 0, C.ONE)
        self.assertEqual(self.mem.load(OBJ + 0x22C, 4), 40)                # the highest part bit
        self.assertEqual(self.calls('model_getMeshJoint')[0], (0x140000, 40))
        flags = self.mem.load(OBJ + 0xC, 4)
        self.assertTrue(flags & 0x2000 and flags & 0x4000)
        # the offset from the given position is 0 (flat bounds): the prop sits at pos + J's lift
        self.assertEqual(self.mem.load(OBJ + 0x18, 4), f32(10.0))
        self.assertEqual(self.mem.load(OBJ + 0x10, 4), f32(100.0))

    def test_launch_four_added_for_the_centre_only(self):
        self.model.phprop_ctor2(OBJ, (0, 0, 0), 0, 0, 0, *self.names(), 0, 0x100, 0, C.ONE)
        self.assertEqual(len(self.calls('obj_updateGridCell')), 2)       # bit 4 (centre) and Prop_launch
        self.assertEqual(self.mem.load(OBJ + 0x23C, 4), PP.F_DAMP_HEAVY)  # no 0x800


class Gold(Fixture):
    def test_gold(self):
        self.mem.poke(RC.G_SIM_FRAME, 4, 1234)
        self.model.gold_ctor2(OBJ, (f32(1.0), f32(2.0), f32(3.0)), 25)
        self.assertEqual(self.model.draws, 1)
        self.assertEqual(self.mem.load(OBJ + 0x48, 4), PP.VT_GOLD)
        self.assertEqual(self.mem.load(OBJ + 0x80, 4), 25)
        self.assertEqual(self.mem.load(OBJ + 0x50, 4), 1234)
        self.assertEqual(self.mem.load(OBJ + 0x4C, 1), 0x29)
        self.assertEqual(self.mem.load(OBJ + 0x5D, 1), 1)
        self.assertEqual(self.mem.load(OBJ + 0xC, 4) & 0x220C, 0x220C)
        self.assertEqual(self.calls('resref_get'), [(PP.R_GOLD_CLIP,)])
        self.assertEqual(self.calls('anim_push')[0][2], 0x204)


if __name__ == '__main__':
    unittest.main()
