"""Synthetic checks of ref_hud_dynamic; invented states only, no game data."""
import unittest

import ref_core as F
import ref_hud_dynamic as H


class Pulse(unittest.TestCase):
    def test_range_period_and_sign(self):
        values = [H.pulse(t) for t in range(64)]
        self.assertEqual(max(values), 25)
        self.assertEqual(min(values), -25)
        self.assertEqual(H.pulse(16), 25)       # quarter turn
        self.assertEqual(H.pulse(0), 0)
        self.assertEqual([H.pulse(t + 64) for t in range(64)], values)

    def test_pending_level_colour_truncates_toward_zero(self):
        self.assertEqual(H.pending_level_colour(-3), 0x80313b3b)    # h = -1
        self.assertEqual(H.pending_level_colour(3), 0x80333d3d)

    def test_pulse_grey(self):
        self.assertEqual(H.pulse_grey(-1, 0x40), 0x40666666)


class StatusText(unittest.TestCase):
    def test_colour_precedence_and_blink(self):
        self.assertEqual(H.name_colour(0, 0), H.STATUS_TEXT)
        self.assertEqual(H.name_colour(0, 0, arena_colour=0x80102030), 0x80102030)
        self.assertEqual(H.name_colour(0, 0, arena_colour=0x80102030, player_colour=0x80a0b0c0), 0x80a0b0c0)
        self.assertEqual(H.name_colour(2, 32, player_colour=0x80a0b0c1, blink_mask=4), 0x80505860)
        self.assertEqual(H.name_colour(2, 31, player_colour=0x80a0b0c1, blink_mask=4), 0x80a0b0c1)
        self.assertEqual(H.name_colour(1, 32, player_colour=0x80a0b0c1, blink_mask=4), 0x80a0b0c1)
        self.assertEqual(H.name_colour(2, -1, player_colour=0x80a0b0c1, blink_mask=4), 0x80a0b0c1)

    def test_width_budget(self):
        self.assertEqual(H.name_width_budget(0, 1, 20), 111)
        self.assertEqual(H.name_width_budget(1, 1, 20), 131)
        self.assertEqual(H.name_width_budget(0, 0, 20), 131)

    def test_glow(self):
        self.assertEqual(H.glow_step(124), 128)
        self.assertEqual(H.glow_step(126), 128)
        self.assertEqual(H.glow_sprite(12, 8, 0), H.Sprite('hud_statusbar00glow.tex', 8, 36, 6, 0x08676767))


class Notices(unittest.TestCase):
    def test_fixed_rows_columns_and_decrement(self):
        timers = [5, 0, 1, 0, 100, 0, 0, 0]
        out, t, a, cleared = H.notice_frame(0, timers, [0]*8, [-1, -1, -1, -1, 3, -1, -1, -1], tick=0)
        self.assertEqual(out[0], H.Sprite('nocamera.tex', 37 + 51, 27 + 82, 4, 0x80676767))
        self.assertEqual(out[1], H.Sprite('nomana.tex', 20, 109, 4, 0x80676767))
        self.assertEqual(out[2], H.Text('ascii', 51, 81, 4, 0x044080e4, 'x 3'))
        self.assertEqual(out[3], H.Sprite('counthealth.tex', 20, 82, 4, 0x04676767))
        self.assertEqual(t, [4, 0, 0, 0, 99, 0, 0, 0])
        self.assertEqual(cleared, [2])

    def test_hidden_or_negative_counts_still_fade_and_tick(self):
        out, t, a, _ = H.notice_frame(1, [0]*4 + [30, 0, 0, 90], [0]*4 + [8, 0, 0, 124], [0]*4 + [-1, 0, 0, 2],
                                      tick=0, hide_counts=True)
        self.assertEqual(out, [])
        self.assertEqual(a[4], 4)
        self.assertEqual(a[7], 128)
        self.assertEqual(t[4], 29)

    def test_network_uses_slot0_column(self):
        self.assertEqual(H.notice_base_x(2, network=True), 37)
        self.assertEqual(H.notice_base_x(2), 199)

    def test_alpha_window(self):
        self.assertEqual(H.notice_alpha_step(82, 126), 128)
        self.assertEqual(H.notice_alpha_step(81, 40), 40)
        self.assertEqual(H.notice_alpha_step(37, 2), 0)

    def test_count_active(self):
        self.assertEqual(H.count_active_notices([1, 0, 0, 0, 0, 0, 0, 0], 0), 0)
        self.assertEqual(H.count_active_notices([1, 1, 0, 0, 1, 0, 0, 0], -1), 2)  # 4 hidden by 1
        self.assertEqual(H.count_active_notices([0, 0, 0, 1, 0, 0, 1, 1], 5), 1)
        self.assertEqual(H.count_active_notices([0]*4 + [1]*4, 9), 4)


class MessageAndBoss(unittest.TestCase):
    def test_message_fade_and_frame(self):
        self.assertEqual(H.message_alpha_step(10, 100), 40)
        self.assertEqual(H.message_alpha_step(50, 127), 128)
        out, alpha = H.message_frame(40, 10, False, False, 211)
        self.assertEqual(alpha, 13)
        self.assertEqual(out[1], H.Frame(150, 76, 340, 32, 6, 0x06000000, 0))
        out, _ = H.message_frame(40, 10, True, True, 401)
        self.assertEqual(out[1], H.Frame(100, 76, 441, 32, 7, 0x06000000, 0))
        self.assertEqual(H.message_frame(40, 10, False, True, 1), ([], 10))

    def test_boss_first_frame_and_damage_flash(self):
        out, s = H.boss_meter_frame(H.BossState(50, 0, 0, 0, 0))
        self.assertEqual(out[1], H.Rect(218, 414, 218 + 194, 430, 5, 0x4e181850))
        self.assertEqual(out[2], H.Sprite('bossmeter.tex', 209, 409, 6, 0x80808080))
        self.assertEqual(s, H.BossState(50, 50, 78, 1, 50))
        out, s = H.boss_meter_frame(s._replace(hp=25))
        self.assertEqual(out[1], H.Rect(218, 414, 218 + 97, 430, 5, 0x4e808080))
        out, s = H.boss_meter_frame(s)
        self.assertEqual(out[1].colour, 0x4e181850)

    def test_boss_fade_after_death_and_language_variant(self):
        out, s = H.boss_meter_frame(H.BossState(0, 40, 3, 1, 9), language=3)
        self.assertEqual(out[1], H.Rect(162, 414, 162, 430, 5, 0x00808080))   # 0 < previous: flash
        self.assertEqual(out[2].resource, 'bossmeter_pal.tex')
        out, s = H.boss_meter_frame(s)
        self.assertEqual((out, s.visible), ([], 0))


class Gold(unittest.TestCase):
    def test_floater_moves_with_old_velocity_then_springs(self):
        pos, vel = H.gold_floater_step([F.f32(10.0), F.f32(20.0), F.f32(0.0)],
                                       [F.f32(1.0), F.f32(0.0), F.f32(0.0)], 0)
        self.assertEqual([F.to_float(v) for v in pos], [11.0, 20.0, 0.0])
        self.assertGreater(F.to_float(vel[1]), 1.0)
        self.assertLess(F.to_float(vel[0]), 1.3)

    def test_alpha_and_counter(self):
        self.assertEqual(H.gold_floater_alpha(100, 110), 128)
        self.assertEqual(H.gold_floater_alpha(110, 100), 98)
        self.assertEqual(H.gold_floater_alpha(200, 100), 0)
        self.assertEqual(H.gold_counter_step(60, 124), (59, 128))
        self.assertEqual(H.gold_counter_step(0, 4), (0, 0))
        self.assertEqual(H.gold_counter(3, 8, 30)[0].x, 560)
        self.assertEqual(H.gold_counter(2, 8, 30)[1], H.Sprite('gold03.tex', 16, 240, 6, 0x08808080))
        self.assertEqual(H.gold_counter(0, 0, 30), [])


class Selector(unittest.TestCase):
    def test_centres_and_directions(self):
        self.assertEqual(H.selector_centre(1), (538, 145))
        self.assertEqual(H.selector_centre(3, network=True), (67, 145))
        self.assertEqual(H.selector_centre(2, menu_mode=True), (141, 249))
        self.assertEqual([H.selector_direction(*d) for d in
                          [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, 0)]],
                         [0, 1, 2, 3, 4, 5, 6, 7, -1])

    def test_fade_cycle(self):
        alpha, timer, speed = 0, F.ZERO, -1
        for _ in range(8):
            alpha, timer, speed = H.selector_fade_step(alpha, timer, speed, True)
        self.assertEqual(alpha, 128)
        released = 0
        while alpha == 128:
            alpha, timer, speed = H.selector_fade_step(alpha, timer, speed, False)
            released += 1
        self.assertEqual(released, 30)
        self.assertEqual(alpha, 124)

    def test_ring_open_and_closed(self):
        ring = H.selector_ring(100, 100, 128)
        self.assertEqual(H.selector_radii(128), (60, 32))
        self.assertEqual(ring[0], (0, 100, 40))
        self.assertEqual(ring[2], (2, 160, 100))
        self.assertEqual(ring[4], (4, 100, 160))
        self.assertEqual(ring[6], (6, 40, 100))
        self.assertEqual(ring[1][1:], (142, 58))
        self.assertTrue(all((x, y) == (100, 100) for _, x, y in H.selector_ring(100, 100, 0)))

    def test_highlight(self):
        corona, icon = H.selector_highlight(16, 0x40)
        self.assertEqual(corona, 0x90808080)
        self.assertEqual(icon, 0x40ffffff)


class Bust(unittest.TestCase):
    def test_fade_clamps(self):
        f = F.ZERO
        for _ in range(20):
            f = H.bust_fade_step(f, False)
        self.assertEqual(f, F.ONE)
        self.assertEqual(H.bust_alphas(f), (110, 128))
        self.assertEqual(H.bust_fade_step(F.f32(0.05), True), F.ZERO)

    def test_meter(self):
        self.assertEqual(H.bust_meter(1, 2, 51, 13), ('bar_yellow02.tex', 521 + 26 - 2))


class FlyingText(unittest.TestCase):
    def test_life_and_fade(self):
        self.assertEqual(H.flying_text_life(0), 30)
        self.assertEqual(H.flying_text_life(2), 180)
        life, alpha, delete = 30, 0x80, False
        ticks = 0
        while not delete:
            life, alpha, delete = H.flying_text_step(life, alpha)
            ticks += 1
        self.assertEqual(ticks, 30)
        self.assertEqual(alpha, 0x80 - 30 * 3)
        life, alpha = 180, 0x80
        for _ in range(150):
            life, alpha, delete = H.flying_text_step(life, alpha)
            self.assertFalse(delete)
            self.assertEqual(alpha, 0x80)
        life, alpha, delete = H.flying_text_step(life, alpha)
        self.assertEqual((life, alpha, delete), (29, 0x7d, False))

    def test_style_and_screen(self):
        self.assertEqual(H.flying_text_style(1, 1, 0x40)[0], 0x40602060)
        colour, force, lift = H.flying_text_style(2, 1, 0x20)
        self.assertEqual((colour, force, lift), (0x20008080, False, 0))
        self.assertEqual(H.flying_text_style(2, 0, 0x10)[1:], (True, 0x41400000))
        self.assertEqual(H.flying_text_style(0, 0, 0x10)[0], 0x10323c3c)
        # w = 2, clip x = 128, y = 64 -> x/w = 64, half = 32, y/w = 32
        self.assertEqual(H.flying_text_screen(5, -4, 0x43000000, 0x42800000, 0x40000000),
                         (5 + 32 + 320, (-4 + 32 + 224) & 0xffffffff))


class Minimap(unittest.TestCase):
    def test_mode_tables(self):
        self.assertEqual(H.minimap_params(0, 1),
                         (0x3f666666, 0, 0, 0x43a00000, 0x43600000))
        self.assertEqual(H.minimap_params(0, 4), H.minimap_params(0, 1))
        self.assertEqual(H.minimap_params(1, 1),
                         (0x3f333333, 0x43480000, 0xc2f00000, 0x42f00000, 0x42c80000))
        self.assertEqual(H.minimap_params(1, 4),
                         (0x3f333333, 0xc3700000, 0x430c0000, 0x42f00000, 0x42c80000))
        self.assertEqual(H.minimap_params(2, 1)[1:3], (0x43340000, 0xc2f00000))
        self.assertEqual(H.minimap_extra(0), (0x41800000, 0x40c00000))

    def test_approach_and_blip(self):
        self.assertEqual(H.minimap_approach(0, 0x43480000), 0x42480000)   # 0 -> 50 toward 200
        self.assertEqual(H.minimap_approach(0x3b800000, 0), 0)             # 1/256 < 0.005 snaps
        self.assertEqual(H.minimap_player_blip(1), (0, 0xbf, 0))
        self.assertIsNone(H.minimap_player_blip(4))
        self.assertFalse(H.minimap_player_drawn(0, 0))
        self.assertTrue(H.minimap_player_drawn(0, 0x20))


class CompassAndBoxes(unittest.TestCase):
    def test_identity_anchor_is_the_offset(self):
        ident = [0] * 16
        ident[0] = ident[5] = ident[10] = ident[15] = F.ONE
        self.assertEqual(H.compass_anchor(ident, (0, 0, 0)), H.COMPASS_OFFSET)
        self.assertEqual(H.COMPASS_LABEL, (65, 394, 131, -100, 500, 18))

    def test_help_and_notice(self):
        self.assertEqual(H.help_button_alpha(0), 128)
        self.assertEqual(H.help_button_alpha(13), 0)
        box = H.help_box(42, 20)
        self.assertEqual(box['label'], (324 - 10, 42 + 0x8b))
        self.assertEqual(box['button'][0], box['label'][0] - 0x19)
        self.assertEqual(H.notice_column(1), 320)
        n = H.notice_box(320, 42)
        self.assertEqual(n['title'], (480, 100))
        self.assertEqual(n['rect'][0], 320 + 0x22)

    def test_prompts_and_arena(self):
        self.assertIsNone(H.medal_prompt(True, True, True, False, True))
        medal = H.medal_prompt(False, True, True, True, False)
        self.assertEqual(medal['body_key'], 'MedalRoundPickNet')
        self.assertEqual(medal['box'], (320, 192, 0x208, 6))
        self.assertFalse(H.net_cam_show(False, True, True, False, 0, 2))
        self.assertTrue(H.net_cam_show(True, False, True, False, 0, 2))
        self.assertFalse(H.net_cam_show(True, False, True, True, 5, 2))
        self.assertEqual(H.net_cam_pad(2), 0xb0)
        self.assertTrue(H.arena_player_active(F.ONE))
        self.assertFalse(H.arena_player_active(0x40000000))
        self.assertTrue(H.arena_step_shown(F.ZERO, 0))
        self.assertFalse(H.arena_step_shown(0x40000000, 0))
        self.assertEqual(H.arena_pulse_args(2), (0x80 - 32, 0x7d0 - 0x190))
        self.assertEqual(H.PICTURE_SITES, (0x1cc8ec, 0x1cd4b0))


if __name__ == '__main__':
    unittest.main()
