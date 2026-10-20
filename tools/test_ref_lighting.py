"""Tests for ref_lighting.py on synthetic values only (no game file).

Run: python3 -m unittest discover -s tools -p test_ref_lighting.py
"""
import math
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_lighting as L                        # noqa: E402


class Level(unittest.TestCase):
    def test_markers_and_defaults(self):
        lv = L.LevelLight.from_markers()
        self.assertEqual(lv.ambient_set[:3], (0x20, 0x20, 0x20))
        self.assertEqual(lv.sun_set[:3], (0x44, 0x44, 0x44))
        self.assertAlmostEqual(lv.sun_dir[1], -math.sqrt(0.5))
        lv = L.LevelLight.from_markers(ambient_pos=(100, 60, 41), sun_pos=(300, 200, 100),
                                       sun_dir_pos=(0, 0, 5))
        self.assertEqual(lv.ambient_set[:3], (50, 30, 20))
        self.assertEqual(lv.sun_dir, (0.0, 0.0, 1.0))

    def test_base_level(self):
        self.assertEqual(L.base_level(0x01000000), 0x80)
        self.assertEqual(L.base_level(0x04000000), 0x40)
        self.assertEqual(L.base_level(0x20000000), 0x20)
        self.assertEqual(L.base_level(0x04000000 | 0x20000000), 0x40)

    def test_scale_and_layer(self):
        lv = L.LevelLight((0, 0, 1), (200, 100, 50, 0), (40, 40, 40, 0), scale=1.5)
        sun, amb = lv.scaled()
        self.assertEqual(sun[:3], (255, 150, 75))
        lv.layer = 1
        self.assertEqual(lv.scaled()[0][:3], (200, 100, 50))

    def test_fill(self):
        lv = L.LevelLight((1, 0, 1), (0, 0, 0, 0), (100, 50, 10, 0))
        fx, fy, fz = lv.fill_dir()
        self.assertAlmostEqual(fx, -1 / math.sqrt(1.25))
        self.assertAlmostEqual(fz, 0.5 / math.sqrt(1.25))
        obj = lv.object_state()
        self.assertEqual(obj.fill[:3], [79, 39, 7])     # trunc(0.79999995 x as-set)

    def test_fill_ignores_scale(self):
        lv = L.LevelLight((0, 0, 1), (100, 100, 100, 0), (100, 100, 100, 0), scale=0.5)
        obj = lv.object_state()
        self.assertEqual((obj.ambient[0], obj.sun[0], obj.fill[0]), (50, 50, 79))

    def test_object_modifiers(self):
        lv = L.LevelLight((0, 0, 1), (100, 100, 100, 0), (30, 30, 30, 0))
        obj = lv.object_state()
        obj.chill(0.5)
        self.assertEqual(obj.ambient, [0, 0, 80, 25])
        obj = lv.object_state()
        obj.poison(2.0)
        self.assertEqual(obj.ambient, [0, 80, 0, 50])
        obj.hit_flash()
        self.assertEqual(obj.ambient, [255, 255, 255, 0])
        obj = lv.object_state()
        obj.scale(0.6, 0.6, 0.6)
        self.assertEqual((obj.ambient[0], obj.sun[0], obj.point_scale[0]), (18, 60, 0.6))


class Nodes(unittest.TestCase):
    def test_grid(self):
        self.assertEqual(L.grid_cell((0, 0, 0)), (45, 45))
        self.assertEqual(L.grid_cell((-11520, 11519, 0)), (0, 89))
        self.assertIsNone(L.grid_cell((11520, 0, 0)))

    def test_collect_cube_and_layer(self):
        a = L.LightNode((0, 0, 0), (255, 0, 0), (0, 0, 0), 100)
        b = L.LightNode((150, 0, 0), (0, 255, 0), (0, 0, 0), 100)
        c = L.LightNode((0, 0, 0), (0, 0, 255), (0, 0, 0), 100, layer=1)
        far = L.LightNode((99, 99, 99), (1, 1, 1), (0, 0, 0), 100)     # corner of the cube
        got = L.collect_near([a, b, c, far], (60, 0, 0))
        self.assertIn(a, got)
        self.assertIn(b, got)
        self.assertIn(far, got)
        self.assertNotIn(c, got)
        self.assertEqual(L.collect_near([a], (101, 0, 0)), [])

    def test_two_best_and_weights(self):
        lv = L.LevelLight((0, 0, 1), (0, 0, 0, 0), (0, 0, 0, 0))
        obj = lv.object_state()
        near = L.LightNode((10, 0, 0), (200, 100, 0), (0, 0, 0), 100)
        mid = L.LightNode((0, 50, 0), (0, 200, 0), (0, 0, 0), 100)
        weak = L.LightNode((0, 0, 90), (0, 0, 200), (0, 0, 0), 100)
        lights, amb = L.model_lights((0, 0, 0), [weak, mid, near], obj)
        self.assertEqual(lights[0].rgb, (198, 99, 0))           # 1 - 100/10000
        self.assertEqual(lights[1].rgb, (0, 150, 0))            # 1 - 2500/10000
        self.assertEqual(lights[0].direction, (1.0, 0.0, 0.0))
        self.assertEqual(len(lights), 4)

    def test_one_light_leaves_slot_empty(self):
        lv = L.LevelLight((0, 0, 1), (0, 0, 0, 0), (10, 10, 10, 0))
        obj = lv.object_state()
        n = L.LightNode((10, 0, 0), (200, 0, 0), (0, 0, 0), 100)
        lights, amb = L.model_lights((0, 0, 0), [n], obj)
        self.assertEqual(lights[1].rgb, (0, 0, 0))
        self.assertEqual(amb, (10, 10, 10))

    def test_shade_model(self):
        lv = L.LevelLight((0, 0, 1), (100, 100, 100, 0), (20, 20, 20, 0))
        obj = lv.object_state()
        rgb = L.shade_model_vertex((0, 0, 1), L.model_lights((0, 0, 0), [], obj))
        self.assertEqual(rgb, (133, 133, 133))           # 20 + 0.99 x 100 (sun) + 0.99 x 15 (fill, straight up)
        rgb = L.shade_model_vertex((0, 0, -1), L.model_lights((0, 0, 0), [], obj))
        self.assertEqual(rgb, (20, 20, 20))

    def test_shade_level_floor_one_is_omni(self):
        torch = L.LightNode.fire((0, 0, 100), 200)
        up = L.shade_level_vertex(0x80, [torch], (0, 0, 0), (0, 0, 1))
        down = L.shade_level_vertex(0x80, [torch], (0, 0, 0), (0, 0, -1))
        self.assertEqual(up, down)
        self.assertEqual(up[0], 0x80 + int(0.75 * 51))

    def test_shade_level_directional(self):
        n = L.LightNode((0, 0, 100), (0, 0, 0), (100, 0, 0), 200)
        up = L.shade_level_vertex(0x80, [n], (0, 0, 0), (0, 0, 1))
        down = L.shade_level_vertex(0x80, [n], (0, 0, 0), (0, 0, -1))
        self.assertEqual(up[0], 0x80 + int(0.75 * 0.99 * 100))
        self.assertEqual(down[0], 0x80)


class Chunks(unittest.TestCase):
    def test_mode0(self):
        ch = L.LightChunk(100, 200, 0, 10, (255, 200, 100, 0))
        self.assertEqual(ch.step(5).model_radius, 100)

    def test_mode1_random_between(self):
        ch = L.LightChunk(100, 200, 1, 10, (255, 200, 100, 0))
        n = ch.step(5, rnd=lambda: 0.5)
        self.assertEqual((n.model_radius, ch.timer), (150, 15))
        n = ch.step(10, rnd=lambda: 0.9)                 # timer not reached: unchanged
        self.assertEqual(n.model_radius, 150)
        self.assertAlmostEqual(n.model_falloff, 1 / 150 ** 2)

    def test_mode2_triangle(self):
        ch = L.LightChunk(100, 200, 2, 10, (1, 1, 1, 0))
        radii = [ch.step(f).model_radius for f in range(1, 23)]
        self.assertEqual(radii[0], 190)                  # jump to high, then one step down
        self.assertEqual(radii[9], 100)
        self.assertEqual(radii[10], 90)                  # period + 1 steps: one below low
        self.assertEqual(radii[11], 110)                 # back to low, one step up
        self.assertEqual(radii[12], 120)

    def test_mode3_toggle_and_mode4_off(self):
        ch = L.LightChunk(100, 200, 3, 4, (1, 1, 1, 0))
        self.assertEqual(ch.step(1).model_radius, 100)
        self.assertEqual(ch.step(3).model_radius, 100)
        self.assertEqual(ch.step(6).model_radius, 200)
        self.assertIsNone(L.LightChunk(100, 200, 4, 4, (1, 1, 1, 0)).step(1))

    def test_clamp(self):
        ch = L.LightChunk(400, 500, 0, 1, (1, 1, 1, 0))
        self.assertEqual(ch.step(1).model_radius, 299)

    def test_glow_size(self):
        self.assertEqual(L.glow_size(100, 2, 0.5), 100 + (11 << 2))


class Fire(unittest.TestCase):
    def test_radii(self):
        self.assertEqual(L.fire_radius('torch', 0.5), 171)
        self.assertEqual(L.fire_radius('lamp', -1.0), 194)
        self.assertEqual(L.candle_radius(3), 48 + 11)
        self.assertEqual(L.candle_radius(10, big=True), 86)
        self.assertEqual(L.lantern_level_radius(170, 'goblinmine2'), 0)
        n = L.LightNode.fire((0, 0, 0), 171)
        self.assertEqual((n.model_rgb, n.level_rgb, n.floor, n.tints_decals),
                         ((200, 150, 50), (51, 39, 18), 1.0, True))

    def test_light_effect(self):
        fx = L.LightEffect((200, 100, 0, 0), (0, 0, 0, 0), 100, 50, 0.5, now=1000)
        self.assertEqual((fx.life, fx.end), (30, 1030))
        alive, node = fx.run(1001)
        self.assertTrue(alive)
        self.assertEqual(node.model_rgb, (193, 96, 0))
        for f in range(1002, 1030):
            alive, node = fx.run(f)
        self.assertTrue(alive)
        alive, node = fx.run(1030)
        self.assertFalse(alive)
        self.assertEqual(node.model_rgb[0], 0)
        self.assertAlmostEqual(node.model_radius, 50.0, places=3)

    def test_light_effect_signed_and_owner(self):
        fx = L.LightEffect((0, 0, 0, 0), (-300, 0, 0, 0), 100, 100, 1 / 60, now=0, signed=True)
        _, node = fx.run(0, owner_pos=(1, 2, 3))
        self.assertEqual(node.model_rgb[0], -255)
        self.assertEqual(node.pos, (1, 2, 39.0))


class Decal(unittest.TestCase):
    def test_only_flagged_lights_above(self):
        lv = L.LevelLight((0, 0, 1), (10, 10, 10, 0), (5, 5, 5, 0))
        above = L.LightNode.fire((0, 0, 50), 100)
        below = L.LightNode.fire((0, 0, -50), 100)
        effect = L.LightNode((0, 0, 50), (255, 255, 255), (0, 0, 0), 100)
        self.assertEqual(L.decal_tint((0, 0, 0), [below, effect], lv), (15, 15, 15))
        r, g, b = L.decal_tint((0, 0, 0), [above], lv)
        self.assertEqual(r, 15 + int(200 * 0.75))



class Round2(unittest.TestCase):
    def test_light_effect_keeps_fractions(self):
        # a rate below one per tick still moves the colour: the accumulator is not truncated
        le = L.LightEffect((0, 0, 0, 0), (10, 0, 0, 0), 50.0, 50.0, 0.5, 0)
        seen = [le.run(f)[1].model_rgb[0] for f in range(1, 31)]
        self.assertEqual(seen[0], 0)
        self.assertGreaterEqual(seen[-1], 9)
        self.assertEqual(sorted(seen), seen)

    def test_slot_takeover_inherits_radius(self):
        slots = L.LightSlots()
        chunks = [L.LightChunk(100 + i, 200, 0, 0, (255, 255, 255, 0)) for i in range(16)]
        for i, c in enumerate(chunks):
            self.assertEqual(slots.run(c, 1, 10 + i)[0], i)
        late = L.LightChunk(5, 9, 3, 100, (1, 2, 3, 0))      # mode 3, timer not expired
        late.timer = 1000
        s, node = slots.run(late, 2, 100)
        self.assertEqual(s, 0)                               # the oldest stamp
        self.assertEqual(node.model_radius, 100.0)           # the previous owner's radius
        self.assertNotIn(id(chunks[0]), slots.slot_of)

if __name__ == '__main__':
    unittest.main()
