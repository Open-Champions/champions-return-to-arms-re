#!/usr/bin/env python3
"""test_ref_gold.py - unit tests of tools/ref_gold.py that need no game files.

Made-up memory: a pile's whole life (built, 41 ticks, touched, 43 ticks, paid an eighth at
a time), the four refusals of the touch, the clip-end shortcut, the direct credit with all
floaters busy, the cap, the flush, the item pickup's two refusals and its sound order, the
every-player item, and the prompt.  Whether the model matches the game is
tools/difftest_gold.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_gold as G                            # noqa: E402

f32 = C.f32
GOLD, PLAYER, PROP, ITEM, DEF = 0x100000, 0x110000, 0x120000, 0x130000, 0x140000
M32 = 0xFFFFFFFF


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.answers = {}
        self.model = G.Model(self.mem, self)
        self.poke(RC.G_RAND_SEED, 0x1234)
        self.poke(G.G_COSMETIC_SEED, 0x5678)
        self.poke(G.G_SIM_FRAME, 1000)
        for j, v in enumerate((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 100.0)):
            self.poke(G.G_VIEW_PROJ + 4 * j, f32(v))
        for slot, (y, x) in enumerate(((200, 50), (200, 590), (250, 50), (250, 590))):
            self.poke(G.HUD_GOLD_Y + 4 * slot, y)
            self.poke(G.HUD_GOLD_X + 4 * slot, x)
        for addr, text in ((G.S_JEWELRY, b'equip_sound_jewelry'), (0x5325D0, b'equip_sound_wood'),
                           (0x5325E8, b'equip_sound_chain'), (0x532648, b'equip_sound_potion'),
                           (G.S_TIMES, b' x %d')):
            for j, b in enumerate(text + b'\0'):
                self.mem.poke(addr + j, 1, b)

    def poke(self, addr, value, size=4):
        self.mem.poke(addr, size, value & ((1 << (8 * size)) - 1))

    def load(self, addr, size=4):
        return self.mem.load(addr, size)

    def get(self, name):
        if name in self.answers:
            return self.answers[name]
        if name in ('res_find', 'obj_getPropInt', 'sound_playOnObject', 'resref_get', 'inventory_giveItem',
                    'text_lookup', 'itemName_buildLocalizedName', 'script_runByName'):
            return lambda *args: 0
        return None

    def calls(self, name):
        return [args for n, args in self.model.calls if n == name]

    def gold(self, slot):
        return self.load(G.record(slot) + G.REC_GOLD)

    def frame(self, n):
        self.poke(G.G_SIM_FRAME, n)

    def player(self, slot, flags=0x4060):
        self.poke(PLAYER + 0xC, flags)
        self.poke(PLAYER + 0x3C8, slot)
        return PLAYER


class PileLife(Fixture):
    def test_whole_life(self):
        """Built at frame 1000 with 120 gold: 41 ticks of Gold_run (drop sound at 1018),
        touched by player 2 at 1041, floater credited at 1041 + 43, paid an eighth at a
        time (rounded up), all 120 in player 2's record, nothing to anyone else."""
        self.poke(G.G_NUM_PLAYERS, 4)
        self.model.gold_ctor2(GOLD, (f32(10.0), f32(20.0), f32(0.0)), 120)
        self.assertEqual(self.model.draws, 1)
        self.assertEqual(self.load(GOLD + 0x4C, 1), G.GOLD_COUNTDOWN)
        self.assertEqual(self.load(GOLD + 0x50), 1000)
        for i in range(1, 42):
            self.frame(1000 + i)
            self.model.gold_run(GOLD)
        self.assertEqual(self.load(GOLD + 0x4C, 1), 0)
        drops = [args for name, args in self.model.calls if name == 'res_find' and args[1] == G.S_COIN_DROP]
        self.assertEqual(len(drops), 1)
        self.assertEqual(self.calls('obj_stopRunning'), [])            # only the clip's end stops it
        self.model.gold_on_touch(GOLD, self.player(2))
        self.assertEqual(self.load(GOLD + 0x80), 0)
        self.assertEqual(self.calls('obj_delete'), [(GOLD,)])
        e = G.floater(0)
        self.assertEqual((self.load(e + 0x1C), self.load(e + 0x20, 1), self.load(e + 0x18)), (120, 2, 1041))
        self.assertEqual(self.model.cosmetic, 1)
        paid = []
        for i in range(1, 80):
            self.frame(1041 + i)
            before = self.gold(2)
            self.model.hud_tick_gold()
            paid.append(self.gold(2) - before)
            if i < 43:
                self.assertEqual(self.load(e + 0x1C), 120, i)
        self.assertEqual(paid[:42], [0] * 42)
        self.assertEqual(paid[42:46], [15, 14, 12, 10])                 # (120 + 7) >> 3, (105 + 7) >> 3, ...
        self.assertEqual(sum(paid), 120)
        self.assertEqual([self.gold(s) for s in (0, 1, 3)], [0, 0, 0])
        self.assertEqual(self.model.draws, 1)                          # the constructor's only

    def test_clip_end_opens_early(self):
        self.model.gold_ctor2(GOLD, (0, 0, 0), 5)
        self.poke(GOLD + 0x5E, 0x80, 2)
        self.model.gold_run(GOLD)
        self.assertEqual(self.load(GOLD + 0x4C, 1), 0)
        self.assertEqual(len(self.calls('obj_stopRunning')), 1)
        self.model.gold_run(GOLD)                                      # countdown 0: nothing at all
        self.assertEqual(len(self.calls('anim_advanceUnitSpeed')), 1)


class Touch(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.poke(GOLD + 0x80, 50)
        self.poke(GOLD + 0x4C, 0, 1)

    def assertNothing(self):
        self.assertEqual(self.model.calls, [])
        self.assertEqual(self.model.writes, [])

    def test_prediction_copy(self):
        self.model.gold_on_touch(GOLD, self.player(0, 0x20060))
        self.assertNothing()

    def test_monster(self):
        self.model.gold_on_touch(GOLD, self.player(0, 0x20))
        self.assertNothing()

    def test_countdown(self):
        self.poke(GOLD + 0x4C, 1, 1)
        self.model.gold_on_touch(GOLD, self.player(0))
        self.assertNothing()

    def test_empty(self):
        self.poke(GOLD + 0x80, 0)
        self.model.gold_on_touch(GOLD, self.player(0))
        self.assertNothing()

    def test_all_floaters_busy_credits_at_once(self):
        for k in range(8):
            self.poke(G.floater(k) + 0x1C, 9)
        self.poke(G.record(3) + G.REC_GOLD, G.GOLD_CAP - 10)
        self.model.gold_on_touch(GOLD, self.player(3))
        self.assertEqual(self.gold(3), G.GOLD_CAP)                     # 99,999,989 + 50, capped
        self.assertEqual(self.model.cosmetic, 0)
        self.assertEqual(self.load(G.G_COSMETIC_SEED), 0x5678)

    def test_second_toucher_gets_nothing(self):
        self.model.gold_on_touch(GOLD, self.player(0))
        n = len(self.model.calls)
        self.model.gold_on_touch(GOLD, self.player(1))
        self.assertEqual(len(self.model.calls), n)


class Floater(Fixture):
    def test_off_screen_edges(self):
        """w 100 (the fixture's camera): flag when 70,000 < |x| or 30,000 < |y|; w < 20 always."""
        for x, y, flag in ((70000.0, 0.0, 0), (70016.0, 0.0, 1), (0.0, -30000.0, 0), (0.0, -30008.0, 1)):
            self.poke(G.floater(0) + 0x1C, 0)
            self.model.hud_add_gold_floater(0, (f32(x), f32(y), 0), 1)
            self.assertEqual(self.load(G.floater(0) + 0x21, 1), flag, (x, y))
        self.poke(G.G_VIEW_PROJ + 60, f32(19.5))
        self.poke(G.floater(0) + 0x1C, 0)
        self.model.hud_add_gold_floater(0, (0, 0, 0), 1)
        self.assertEqual(self.load(G.floater(0) + 0x21, 1), 1)

    def test_screen_place(self):
        self.poke(G.G_VIEW_PROJ + 60, f32(128.0))                       # w a power of two: exact
        self.model.hud_add_gold_floater(1, (f32(1000.0), f32(-500.0), f32(7.0)), 3)
        e = G.floater(0)
        self.assertEqual(self.load(e), f32(1000.0 / 128 * 0.5 + 320))
        self.assertEqual(self.load(e + 4), f32(-500.0 / 128 + 240))
        self.assertEqual(self.load(e + 8), 0)
        self.assertEqual(self.load(e + 0x14), 0)


class Tick(Fixture):
    def test_eighths(self):
        self.poke(G.G_GOLD_PENDING + 4, 100)
        steps = []
        while self.load(G.G_GOLD_PENDING + 4):
            before = self.gold(1)
            self.model.hud_tick_gold()
            steps.append(self.gold(1) - before)
        self.assertEqual(steps[:3], [13, 11, 10])
        self.assertEqual(sum(steps), 100)

    def test_edge_43(self):
        e = G.floater(5)
        self.poke(e + 0x1C, 7)
        self.poke(e + 0x18, 1000 - 42)
        self.model.hud_tick_gold()
        self.assertEqual(self.load(e + 0x1C), 7)
        self.poke(e + 0x18, 1000 - 43)
        self.model.hud_tick_gold()
        self.assertEqual(self.load(e + 0x1C), 0)
        self.assertEqual(self.gold(0), 1)                             # (7 + 7) >> 3 on the same tick

    def test_flush(self):
        self.poke(G.floater(2) + 0x1C, 30)
        self.poke(G.floater(2) + 0x20, 3, 1)
        self.poke(G.G_GOLD_PENDING + 12, 12)
        self.poke(G.G_GOLD_PENDING, -4)
        self.poke(0x86ACD8, 77)
        self.model.hud_flush_gold()
        self.assertEqual(self.gold(3), 42)
        self.assertEqual(self.gold(0), 0)                             # a negative pending sum is left
        self.assertEqual(self.load(G.G_GOLD_PENDING) & M32, -4 & M32)
        self.assertEqual(self.load(0x86ACD8), 0)


class Items(Fixture):
    def item(self, at, category=1, flags=0, count=1):
        self.poke(at, DEF)
        self.poke(DEF + 0x1D, category, 1)
        self.mem.poke(at + 8, 8, flags)
        self.poke(at + 4, count, 2)

    def setUp(self):
        Fixture.setUp(self)
        self.weight = f32(5.0)
        self.answers['player_itemWeight'] = lambda *a: self.weight
        for slot in range(4):
            rec = G.record(slot)
            self.poke(rec + G.REC_LOAD, f32(95.0))
            self.poke(rec + G.REC_LIMIT, f32(100.0))
            self.poke(rec + G.REC_OBJ, PLAYER + slot)

    def test_bag_of_63_refuses(self):
        self.item(ITEM, category=2)
        self.poke(G.record(0) + G.REC_BAG_COUNT + 2 * G.BAG_SIZE, 63)
        self.assertEqual(self.model.try_pickup(0, ITEM), 0)
        self.assertEqual(self.calls('res_find'), [(G.S_FX_LUMP, G.S_CANTDO)])
        self.poke(G.record(0) + G.REC_BAG_COUNT + 2 * G.BAG_SIZE, 62)
        self.assertEqual(self.model.try_pickup(0, ITEM), 1)

    def test_load_limit_is_inclusive(self):
        self.item(ITEM)
        self.assertEqual(self.model.try_pickup(1, ITEM), 1)           # 95 + 5 <= 100
        self.weight = f32(5.5)
        self.assertEqual(self.model.try_pickup(1, ITEM), 0)
        self.assertEqual(self.calls('player_voice'), [(1, 0)])

    def test_sound_order(self):
        self.item(ITEM, flags=0x800000 | 0x200000)
        self.model.try_pickup(0, ITEM)
        self.item(ITEM, flags=0x4000000)
        self.model.try_pickup(0, ITEM)
        self.assertEqual(self.calls('libc_sprintf'), [(0x5325D0,), (G.S_JEWELRY,)])
        self.assertEqual(self.calls('sound_playOnObject')[0][1], PLAYER)
        self.assertEqual(self.calls('inventory_giveItem')[0], (0, ITEM, 1))

    def test_every_player_item(self):
        self.poke(PROP + 0x48, G.VT_PHPROP)
        self.poke(G.VT_PHPROP + 8 + 4, G.PHPROP_DTOR)
        self.item(PROP + 0x148, flags=1 << 39)
        self.poke(G.G_NUM_PLAYERS, 3)
        self.poke(G.record(1) + G.REC_LIMIT, f32(10.0))                # slot 1 cannot carry it
        self.model.prop_interact(PROP, 2)
        self.assertEqual([a[0] for a in self.calls('inventory_giveItem')], [0, 2])
        self.assertEqual(self.calls('PhProp_dtor'), [(PROP, 3)])

    def test_one_player_item_refused_stays(self):
        self.poke(PROP + 0x48, G.VT_ITEMPROP)
        self.poke(G.VT_ITEMPROP + 8 + 4, G.ITEMPROP_DTOR)
        self.item(PROP + 0x148)
        self.weight = f32(50.0)
        self.model.prop_interact(PROP, 0)
        self.assertEqual(self.calls('ItemProp_dtor'), [])

    def test_prompt(self):
        self.item(PROP + 0x148, count=1)
        self.assertEqual(self.model.prop_interact_prompt(PROP, 0x150000), 1)
        self.assertEqual(self.load(PROP + 0x104), 1000)
        self.assertEqual(self.calls('libc_sprintf'), [])
        self.item(PROP + 0x148, count=3)
        self.model.prop_interact_prompt(PROP, 0x150000)
        self.assertEqual(self.calls('libc_sprintf'), [(G.S_TIMES, 3)])
        self.assertEqual(self.calls('wstr_catAscii')[-1], (0x150000, ('buf', b' x 3')))


class ItemAtRest(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        for j, b in enumerate(b'equipmnt.lmp\0'):
            self.mem.poke(G.S_ITEMS_LUMP + j, 1, b)
        for row in range(40):
            self.poke(G.ITEM_MODELS + 16 * row, 0x150000)
            self.poke(G.ITEM_MODELS + 16 * row + 4, 0x150100)
        self.poke(DEF + 0x34, 7, 2)

    def test_no_run_and_flags(self):
        """A zero-filled 0x190 block: flags 0x1809 | 0x102000 less 0x1800 = 0x102009, prop
        flags 1, never linked to the every-frame list; one shared draw, no own draw."""
        self.mem.poke(ITEM, 4, DEF)
        self.model.item_prop_ctor3(PROP, (0, 0, 0), ITEM, 0x160000)
        self.assertEqual(self.load(PROP + 0xC), 0x102009)
        self.assertEqual(self.load(PROP + 0x140, 2), 1)
        self.assertEqual(self.load(PROP + 0x48), G.VT_ITEMPROP)
        self.assertEqual(self.calls('obj_runEveryFrame'), [])
        self.assertEqual(self.model.draws, 1)
        self.assertEqual(self.load(PROP + 0xE8, 8), 0xFFFFFFFFFFFFFFFF)

    def test_every_player_item_loses_0x3000(self):
        self.mem.poke(ITEM, 4, DEF)
        self.mem.poke(ITEM + 8, 8, 1 << 39)
        self.model.item_prop_ctor3(PROP, (0, 0, 0), ITEM, 0x160000)
        self.assertEqual(self.load(PROP + 0xC), 0x100009)

    def test_variant_row(self):
        self.mem.poke(ITEM, 4, DEF)
        self.mem.poke(ITEM + 8, 8, (1 << 36) | (5 << 11))
        self.assertEqual(self.model.resource_index(ITEM), 12)
        self.mem.poke(ITEM + 8, 8, 5 << 11)
        self.assertEqual(self.model.resource_index(ITEM), 7)


class DroppedItem(Fixture):
    """Prop_run on an ItemProp_ctor2 item with launch 0 (every call site's)."""

    def setUp(self):
        Fixture.setUp(self)
        self.ground = f32(0.0)
        self.answers['terrain_heightBelow'] = lambda *a: self.ground
        self.answers['terrain_sweepCircle'] = lambda *a: (C.ONE, (0, 0, 0))
        self.poke(G.G_NUM_PLAYERS, 1)
        self.poke(G.G_ALIVE_PLAYERS, 0)
        self.poke(G.record(0) + G.REC_OBJ, PLAYER)
        self.poke(PLAYER + 0x18, f32(0.0))

    def drop(self):
        self.poke(PROP + 0x18, f32(50.0))
        self.poke(PROP + 0x1C, f32(4.0))
        self.poke(PROP + 0x10E, 180, 2)

    def test_falls_lands_and_rests_after_180(self):
        self.drop()
        for tick in range(1, 181):
            self.model.prop_run(PROP)
            if tick < 180:
                self.assertEqual(self.load(PROP + 0x140, 2) & 1, 0, tick)
        self.assertEqual(self.load(PROP + 0x18), f32(0.0))              # on the ground
        self.assertEqual(self.load(PROP + 0x140, 2), 1)
        self.assertEqual(len(self.calls('obj_stopRunning')), 1)
        self.assertEqual(self.calls('obj_delete'), [])
        self.assertEqual(self.model.draws, 0)

    def test_deleted_120_below_the_first_alive_player(self):
        self.drop()
        self.poke(PLAYER + 0x18, f32(171.0))                            # 50 - 0.45 + 120 < 171
        self.model.prop_run(PROP)
        self.assertEqual(self.calls('obj_delete'), [(PROP,)])

    def test_kept_running_prop_sinks_then_goes(self):
        """Prop flag 2 keeps it running: below life -60 it sinks 0.1 a tick, below -300 slot 1."""
        self.poke(PROP + 0x48, G.PP.VT_PROP)
        self.poke(G.PP.VT_PROP + 8 + 4, 0x3C2D30)
        self.poke(PROP + 0x140, 3, 2)
        self.poke(PROP + 0x10E, (-60) & 0xFFFF, 2)
        self.poke(PROP + 0x18, f32(10.0))
        self.poke(PLAYER + 0x18, f32(-1000.0))
        self.model.prop_run(PROP)                                       # life -61: first sink
        self.assertEqual(self.load(PROP + 0x18), C.sub(f32(10.0), G.F_SINK))
        self.poke(PROP + 0x10E, (-300) & 0xFFFF, 2)
        self.model.prop_run(PROP)
        self.assertEqual(self.calls('Prop_dtor'), [(PROP, 3)])


if __name__ == '__main__':
    unittest.main()
