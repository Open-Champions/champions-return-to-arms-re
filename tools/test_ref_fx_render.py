#!/usr/bin/env python3
"""Synthetic tests of tools/ref_fx_render.py (made-up values only; the comparison with the
game's code is tools/difftest_fx_render.py).
python3 -m unittest discover -s tools -p 'test_*.py'"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                         # noqa: E402
import ref_fx_render as R                                    # noqa: E402

F = C.f32
IDENT_VIEW = [F(1.0), 0, 0, 0, F(1.0), 0, 0, 0, F(1.0), 0, 0, 0]


def typerec(u0=0x610, v0=0x210, g=0.0, rate=0.0, u1=0x7F0, v1=0x3F0, size0=100.0,
            c0=(128, 64, 32, 128), crate=(0, 0, 0, 0)):
    return ([u0, v0, F(g), F(rate), u1, v1, 0, F(size0)] +
            [F(c + 8388608.0) for c in c0] + [F(r) for r in crate])


def cell(pos, birth, vel=(0, 0, 0), slot=1):
    return struct.pack('<8h', *pos, birth, *vel, slot * 4)


class VuArithmetic(unittest.TestCase):
    def test_cut_and_largest(self):
        vu = R.Vu()
        self.assertEqual(vu.add(F(1.0), F(2.0 ** -24 * 3)), F(1.0) + 1)
        self.assertEqual(vu.vin(0x7F800000), 0x7F7FFFFF)
        self.assertEqual(vu.vin(0x00000001), 0)
        self.assertEqual(vu.div(F(1.0), 0), 0x7F7FFFFF)
        self.assertEqual(vu.div(F(-1.0), 0), 0xFF7FFFFF)

    def test_clamp_is_by_pattern(self):
        vu = R.Vu()
        self.assertEqual(vu.vmax(F(-5.0), R.TWO23), R.TWO23)
        self.assertEqual(vu.vmin(F(9e6), R.TWO23_255), R.TWO23_255)


class Particles(unittest.TestCase):
    def setUp(self):
        self.hdr = R.particle_header(IDENT_VIEW, F(477.5), 10)

    def test_projection_and_header(self):
        m = R.particle_projection(F(477.5))
        self.assertEqual(m[11], R.ONE)
        self.assertEqual(self.hdr['vf5'][3], F(10.0))
        self.assertEqual(self.hdr['vf6'][:2], (F(800.0), F(400.0)))

    def test_sprite_is_centred_and_2_to_1(self):
        v1, v2 = R.sprite_vertices(cell((0, 0, 200), 10), typerec(), self.hdr)
        cx, cy = (v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2
        self.assertAlmostEqual(cx, 0x8000, delta=1)          # straight ahead: screen centre
        self.assertAlmostEqual(cy, 0x8000, delta=1)
        self.assertAlmostEqual(v2[0] - v1[0], 2 * (v2[1] - v1[1]), delta=2)
        self.assertEqual(v2[4], 0)                           # not culled
        self.assertEqual(v1[5], (128, 64, 32, 128))
        self.assertEqual((v1[6], v2[6]), ((0x610, 0x210), (0x7F0, 0x3F0)))

    def test_colour_runs_and_clamps(self):
        rec = typerec(c0=(10, 250, 0, 255), crate=(-1.0, 1.0, 0.5, -0.25))
        # age 20: 10-20 -> 0, 250+20 -> 255, 0+10 = 10, 255-5 = 250
        self.assertEqual(R.colour_bytes(rec, F(20.0)), (0, 255, 10, 250))

    def test_behind_the_camera_is_culled(self):
        v1, v2 = R.sprite_vertices(cell((0, 0, -200), 10), typerec(), self.hdr)
        self.assertEqual(v2[4], 1)

    def test_line_tail_has_alpha_zero(self):
        rec = typerec(c0=(200, 100, 50, 90))
        rec[0] = 0                                          # line gravity +0x10
        rec[3] = F(3.0)                                     # lag +0x1c
        head, tail = R.line_vertices(cell((0, 0, 200), 0, vel=(0, 4096, 0)), rec, self.hdr)
        self.assertEqual(head[5], (200, 100, 50, 90))
        self.assertEqual(tail[5], (200, 100, 50, 0))
        self.assertLess(tail[1], head[1])                  # moving +y in view = down the screen

    def test_list_blocks(self):
        # one page, live cells 5..36: blocks 0 and 1 sent; 1..4 retired (sent as they are),
        # 37..62 zero-filled
        blocks = R.list_blocks([7], 5, 37)
        self.assertEqual([(p, b) for p, b, _ in blocks], [(7, 0), (7, 1)])
        self.assertEqual(blocks[0][2][0], 1)
        self.assertEqual(blocks[1][2][:5], [33, 34, 35, 36, None])
        self.assertEqual(R.list_blocks([3, 4], 0x80, 0x101)[-1][1], 7)    # full last page


def trail(points, oldest=0, flags=0, clock=10, lifetime=60, row=3, width4=250):
    t = R.Trail()
    t.points = points + [(0, 0, 0, 0)] * (128 - len(points))
    t.handle, t.clock, t.oldest, t.newest = 0x101, clock, oldest, len(points) & 0x7F
    t.row, t.flags, t.lifetime, t.rgba, t.width4 = row, flags, lifetime, (1, 2, 3, 4), width4
    return t


class Trails(unittest.TestCase):
    def test_header(self):
        h = R.trail_header(trail([(0, 0, 0, 1)] * 4, flags=4))
        self.assertEqual(h[3][0], 0x48)
        self.assertEqual(C.to_float(h[1][3]), 31.0)          # rows 96..128
        self.assertEqual(C.to_float(h[4][1]), 524288.0 + 96.5)
        self.assertEqual(C.to_float(h[4][3]), 10000.0)
        self.assertEqual(R.trail_header(trail([], flags=8))[3][0], 0x09)

    def test_chunks(self):
        t = trail([(0, 0, 0, 1)] * 100)
        self.assertEqual(R.trail_chunks(t), [(0, 32), (32, 32), (64, 32), (96, 4)])
        t.oldest, t.newest = 3, 10
        self.assertEqual(R.trail_chunks(t), [(2, 8)])        # oldest rounded down to even
        t.oldest, t.newest = 120, 6
        self.assertEqual(R.trail_chunks(t), [(120, 8), (0, 6)])

    def test_strip_and_width(self):
        pts = [(0, 0, 400, 1), (100, 0, 400, 2), (200, 0, 400, 3)]
        hdr = R.particle_header(IDENT_VIEW, F(477.5), 0)
        vs = R.trail_vertices(trail(pts), hdr['m'], hdr['vf6'], hdr['vf7'])
        self.assertEqual(len(vs), 6)
        self.assertEqual((vs[0][4], vs[1][4], vs[2][4]), (1, 1, 0))    # the first point starts the strip
        self.assertEqual(vs[2][0], vs[3][0])                          # a horizontal trail: offset in y only
        self.assertGreater(abs(vs[2][1] - vs[3][1]), 0)
        narrow = R.trail_vertices(trail(pts, width4=1), hdr['m'], hdr['vf6'], hdr['vf7'])
        self.assertLess(abs(narrow[2][1] - narrow[3][1]), abs(vs[2][1] - vs[3][1]))
        lost = R.trail_vertices(trail(pts, width4=1), hdr['m'], hdr['vf6'], hdr['vf7'], waitq_first=False)
        same = R.trail_vertices(trail(pts), hdr['m'], hdr['vf6'], hdr['vf7'], waitq_first=False)
        self.assertEqual(lost[2][:2], same[2][:2])                    # width ignored in vu1.cpp's model

    def test_pairs_carry_alpha(self):
        pts = [(0, 0, 400, 1), (0, 20, 400, 255), (50, 0, 400, 2), (50, 20, 400, 128)]
        hdr = R.particle_header(IDENT_VIEW, F(477.5), 0)
        vs = R.trail_vertices(trail(pts, flags=2), hdr['m'], hdr['vf6'], hdr['vf7'])
        self.assertEqual([v[5][3] for v in vs], [255, 255, 128, 128])


class Beams(unittest.TestCase):
    def test_tree_and_draws(self):
        cos, libc = C.Lcg(1234), C.LibcRand(1)
        nodes = R.beam_build_nodes(F(10.0), 3, cos, libc)
        self.assertEqual(len(nodes), 15)
        check = C.Lcg(1234)
        for _ in range(15 * 6):
            check.draw()
        self.assertEqual(cos.state, check.state)
        self.assertTrue(all(0 <= n.count < 8 for n in nodes))
        n = nodes[0]
        # drift.z subtracts offset.y: recompute from the same draws
        c = C.Lcg(1234)
        s = [c.signed_unit() for _ in range(6)]
        self.assertEqual(n.drift[2], C.mul(C.sub(C.mul(s[5], F(10.0)), n.off[1]), R.K_DRIFT))

    def test_points_lie_between_the_ends_without_jitter(self):
        nodes = R.beam_build_nodes(0, 2, C.Lcg(5), C.LibcRand(1))
        pts = R.beam_points(nodes, [0, 0, 0], [F(70.0), 0, 0], 2, 0, C.Lcg(9))
        self.assertEqual([C.to_float(p[0]) for p in pts], [8.75 * k for k in range(1, 8)])   # no ends

    def test_drift_retarget(self):
        nodes = [R.BeamNode([0, 0, 0], [F(1.0), 0, 0], 0)]
        cos = C.Lcg(77)
        R.beam_drift_nodes(nodes, F(4.0), 0, cos)
        self.assertEqual(nodes[0].off[0], F(1.0))
        self.assertEqual(nodes[0].count, (cos.state >> 21) & 7)

    def test_frame_seed(self):
        self.assertEqual(R.beam_frame_seed(100, 2), 100 * 0x229 + 2 * 0x3F3)
        self.assertEqual(R.beam_trail_points([[F(1.5), F(-2.0), 0]])[0], [(3, -4, 0, 1)])


class Glows(unittest.TestCase):
    def setUp(self):
        proj = C.mat4_set_projection(0x3F7FFFFF, 0x3EEEEEEE, F(477.5), R.ONE, 0x457FFF00,
                                     0x41900000, 0x44E10000)
        self.vp = C.mat4_mul_mat34(IDENT_VIEW, proj)

    def glow(self, z, flags=0, tex=0x100, bias=0.0, size=8000.0):
        return R.Glow([0, 0, F(z)], F(size), F(bias), (255, 150, 0, 60), tex, 0, flags)

    def test_centre_and_cull(self):
        X, Y, Z, H = R.glow_project(self.glow(400.0), IDENT_VIEW, self.vp)
        self.assertEqual((X, Y), (0x8000, 0x8000))
        self.assertIn(H, (319, 320))                      # 8000 * 16 / 400, cut
        self.assertIsNone(R.glow_project(self.glow(10.0), IDENT_VIEW, self.vp))     # depth < 20

    def test_bias_moves_toward_the_camera(self):
        a = R.glow_project(self.glow(400.0), IDENT_VIEW, self.vp)
        b = R.glow_project(self.glow(400.0, bias=100.0), IDENT_VIEW, self.vp)
        self.assertEqual(a[3], b[3])                       # same size: depth = w + bias
        self.assertGreater(b[2], a[2])                     # larger Z: nearer (TEST depth greater)

    def test_packets_group_and_pass(self):
        q = [self.glow(400.0, 0, 0x100), self.glow(400.0, 2, 0x100), self.glow(400.0, 0, 0x200),
             self.glow(400.0, 0, 0x100), self.glow(400.0, 4, 0x100)]
        p1 = R.glow_packets(q, 1, IDENT_VIEW, self.vp, {0x100: (32, 32), 0x200: (32, 32)})
        self.assertEqual([(k, t) for k, t, _, _ in p1], [(4, 0x100)])
        p0 = R.glow_packets(q, 0, IDENT_VIEW, self.vp, {0x100: (32, 32), 0x200: (32, 32)})
        self.assertEqual([(k, t) for k, t, _, _ in p0], [(3, 0x100), (3, 0x100), (3, 0x200)])
        self.assertEqual(sum(1 for r, _ in p0[0][3] if r == 0x05), 4)   # two sprites
        self.assertIn((0x42, 0x48), p0[1][3])                           # flags 2: additive

    def test_negative_x_spills(self):
        g = self.glow(400.0)
        ev = R.glow_vertices(g, 10, 0x8000, 5, 100, 32, 32)
        xyz = ev[2][1]
        self.assertEqual(xyz >> 48, 0xFFFF)                # the sign of 10 - 200 fills Y and Z


class Builders(unittest.TestCase):
    def test_spline_hits_its_points(self):
        pts = [[F(0.0), 0, 0], [F(10.0), F(5.0), 0], [F(20.0), 0, 0], [F(30.0), 0, 0]]
        pos, _ = R.spline_eval(0, pts, 4)
        self.assertEqual(pos, pts[0])
        pos, _ = R.spline_eval(F(1.0 / 3.0), pts, 4)
        self.assertAlmostEqual(C.to_float(pos[0]), 10.0, places=4)
        pos, _ = R.spline_eval(F(-1.0), pts, 4)
        self.assertEqual(pos, pts[0])                     # clamped to 0

    def test_spline_trail_counts(self):
        pts = [[F(0.0), 0, 0], [F(10.0), 0, 0], [F(20.0), 0, 0]]
        out, life = R.trail_set_spline(0, F(1.0), pts, 3, 20)
        self.assertEqual((len(out), life), (20, 20))

    def test_circle(self):
        out = R.trail_set_circle(F(10.0), [0, 0, 0], [0, 0, R.ONE], 4)
        self.assertEqual(len(out), 4)
        for p in out:
            self.assertAlmostEqual(sum(C.to_float(x) ** 2 for x in p), 100.0, places=2)
            self.assertEqual(p[2] & 0x7FFFFFFF, 0)

    def test_sweep_and_pair(self):
        pairs, life = R.trail_sweep_pairs([0, 0, 0], [0, 0, R.ONE], [F(10.0), 0, 0], [F(20.0), 0, 0], 100)
        self.assertEqual((len(pairs), life), (60, 60))
        self.assertEqual(R.trail_pair(F(0.5), [0, 0, 0], [F(1.0), 0, 0], 7)[1][3], 127)


if __name__ == '__main__':
    unittest.main()
