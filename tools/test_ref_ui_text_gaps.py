#!/usr/bin/env python3
"""Synthetic tests for tools/ref_ui_text_gaps.py (no game file needed).

The original functions are compared with these models by tools/difftest_ui_text_gaps.py;
these tests pin the documented behaviour of docs/ui-text-gaps.md on hand-made inputs.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_anim as A                    # noqa: E402
import ref_core as F                    # noqa: E402
import ref_strings as RS                # noqa: E402
import ref_ui_text_gaps as R            # noqa: E402

M32 = 0xFFFFFFFF


def help_state(**kw):
    st = {'delay': 0, 'open': 1, 'net': 0, 'paused': 0, 'pause_byte': 0, 'local_menu': 0,
          'lockout': 0, 'dl_free': 5000, 'pulse': F.ONE, 'title': 0x1000, 'body': 0x2000,
          'font_med': 0xAAAA, 'glyph_word': 0x7E, 'num_players': 1, 'pads': [0, 0, 0, 0],
          'confirm_mask': 0x40, 'alive': [0], 'local': {0}, 'wrap_height': 42, 'label_width': 60}
    st.update(kw)
    return st


class Ramps(unittest.TestCase):
    def test_fade_reaches_one_on_the_ninth_frame(self):
        ramp = R.fade_ramp()
        self.assertEqual(len(ramp), 9)
        self.assertEqual(ramp[0], R.FADE_STEP)
        self.assertEqual(ramp[-1], F.ONE)
        self.assertTrue(all(F.lt(a, b) for a, b in zip(ramp, ramp[1:])))
        self.assertTrue(F.lt(ramp[-2], F.ONE))

    def test_values_at_or_above_one_are_left_alone(self):
        pulse, fade = R.ui_ramps_step([F.ONE] * 4, [F.ONE, F.TWO, F.ONE, 0x3F800001])
        self.assertEqual(pulse, [F.ONE] * 4)
        self.assertEqual(fade, [F.ONE, F.TWO, F.ONE, 0x3F800001])

    def test_pulse_decays_by_four_fifths_of_the_excess(self):
        ramp = R.pulse_ramp(F.TWO, 40)
        self.assertEqual(ramp[0], F.add(F.mul(F.ONE, R.PULSE_DECAY), F.ONE))
        self.assertTrue(all(not F.lt(p, F.ONE) for p in ramp))
        self.assertTrue(F.lt(ramp[-1], ramp[0]))

    def test_slots_are_independent(self):
        _p, fade = R.ui_ramps_step([F.ONE] * 4, [F.ZERO, F.ONE, F.ZERO, F.ONE])
        self.assertEqual(fade, [R.FADE_STEP, F.ONE, R.FADE_STEP, F.ONE])


class Layout(unittest.TestCase):
    def test_glyph_words(self):
        self.assertEqual(R.button_layout(1)[R.G_GLYPH_CONFIRM], 0x7E)
        self.assertEqual(R.button_layout(0)[R.G_GLYPH_CONFIRM], 0x7B)
        self.assertEqual(R.button_layout(2), {})
        self.assertEqual(R.button_layout(0xFF), {})

    def test_confirm_mask_glyph_is_the_drawn_glyph(self):
        for words in R.LAYOUTS.values():
            self.assertEqual(R.pad_mask_to_glyph(words[R.G_CONFIRM_MASK]), words[R.G_GLYPH_CONFIRM])
        self.assertEqual(R.pad_mask_to_glyph(0x60), M32)

    def test_percent_c_takes_the_low_byte(self):
        self.assertEqual(R.glyph_text(0x7E), b'~')
        self.assertEqual(R.glyph_text(0x17B), b'{')
        self.assertEqual(R.glyph_text(0), b'')


class HelpBox(unittest.TestCase):
    def test_closed_box_only_counts_down(self):
        calls, st = R.help_task(help_state(open=0, delay=5))
        self.assertEqual(calls, [])
        self.assertEqual(st['delay'], 4)

    def test_offline_pause_and_frames(self):
        calls, st = R.help_task(help_state(delay=3))
        self.assertEqual((st['paused'], st['pause_byte']), (1, 1))
        frames = [c for c in calls if c[0] == 'ui_drawFrameImpl']
        self.assertEqual(frames[0][1:4], (0x73, 0x5A, 0x1A2))
        self.assertEqual(frames[0][4], 42 + 0x4C + 8)
        self.assertEqual(frames[0][7], 2)                         # tile, via the wrapper
        self.assertEqual(frames[1][1:5], (0x7C, 0x68, 0x1A0, 42 + 0x4C))
        self.assertEqual(frames[1][6:], (R.HELP_INNER_TINT, 0, 0, 0))   # ctile, no flags
        glyph = [c for c in calls if c[0] == 'text_drawAscii'][0]
        self.assertEqual(glyph[1:4], (0x144 - 30 - 0x19, 42 + 0x8B, b'~'))

    def test_inner_frame_pieces_are_ctile(self):
        pieces = R.help_inner_frame(42)
        self.assertTrue(pieces and all(p.resource.startswith('ctile') for p in pieces))

    def test_display_list_gate_skips_the_draw_only(self):
        calls, st = R.help_task(help_state(dl_free=2999, pads=[0x40, 0, 0, 0]))
        self.assertNotIn('text_begin', [c[0] for c in calls])
        self.assertEqual(st['open'], 0)

    def test_two_pads_close_twice(self):
        calls, st = R.help_task(help_state(num_players=2, pads=[0x40, 0x40, 0, 0]))
        self.assertEqual([c[0] for c in calls].count('script_runPostAction'), 2)
        self.assertEqual((st['open'], st['delay'], st['lockout'], st['paused']), (0, 60, 60, 0))

    def test_no_confirm_while_the_delay_runs(self):
        _calls, st = R.help_task(help_state(delay=2, pads=[0x40, 0, 0, 0]))
        self.assertEqual((st['open'], st['delay']), (1, 1))

    def test_net_game_sends_but_runs_no_post_action(self):
        calls, st = R.help_task(help_state(net=1, pads=[0x40, 0, 0, 0], alive=[0, 1], local={1}))
        names = [c[0] for c in calls]
        self.assertNotIn('script_runPostAction', names)
        self.assertIn(('hudmsg_sendMenuState', 1, 0, 0), calls)
        self.assertEqual(st['paused'], 0)


class Bust(unittest.TestCase):
    def state(self, **kw):
        st = {'shown': 5, 'latch': 0, 'fade': F.ONE, 'value': 30, 'maximum': 60,
              'sim_frame': 6, 'font_small': 0x5555,
              'tex': {b'frame.tex': (40, 50), b'<portrait>': (33, 44), b'fieldmeter.tex': (10, 10),
                      b'fieldnumber.tex': (10, 10), b'bar_yellow03.tex': (64, 8)}}
        st.update(kw)
        return st

    def test_not_shown_draws_nothing_and_keeps_the_fade(self):
        calls, st = R.hud_draw_bust(self.state(shown=0, fade=F.ZERO))
        self.assertEqual((calls, st['fade']), ([], F.ZERO))

    def test_meter_branch(self):
        calls, _st = R.hud_draw_bust(self.state())
        self.assertEqual(calls[0], ('text_begin', 0x5555, 6, (110 << 24) | R.BUST_TEXT_RGB, M32))
        wraps = [c for c in calls if c[0] == 'text_drawWrapped']
        self.assertEqual(len(wraps), 1)
        self.assertEqual(wraps[0][1:3], (0x20F, 0x185))
        clip = [c for c in calls if c[0] == 'sprite_clipped'][0]
        self.assertEqual(clip[1], b'bar_yellow03.tex')
        self.assertEqual(clip[8], 0x209 + 32 - 2)               # half of 64, minus 2
        sprites = [c for c in calls if c[0] == 'sprite']
        self.assertTrue(all(c[5] & 0xFFFFFF == R.BUST_SPRITE_RGB for c in sprites))
        portrait = [c for c in sprites if c[1] == b'<portrait>'][0]
        self.assertEqual(portrait[2:4], (0x1F3 - 16, 50 - 44 + 0x16E))

    def test_number_branch(self):
        calls, _st = R.hud_draw_bust(self.state(maximum=-1, value=-7))
        self.assertIn(('text_drawAsciiCentered', 0x21E, 0x173, b'0', 0x2710), calls)
        colour = [c for c in calls if c[0] == 'text_setColor'][0][1]
        self.assertEqual(colour >> 24, 128)                       # the number: fade x 128

    def test_fade_clamps_and_latch_clears(self):
        _c, st = R.hud_draw_bust(self.state(latch=1, fade=F.ZERO))
        self.assertEqual((st['fade'], st['latch']), (F.ZERO, 0))
        _c, st = R.hud_draw_bust(self.state(fade=F.f32(0.95)))
        self.assertEqual(st['fade'], F.ONE)


class SpriteFields(unittest.TestCase):
    def test_field_mode_even_top(self):
        q1 = R.sprite_quad(0, 1, 32, 20, 10, 100, 0, 0, 32, 20, fields=(1, 0))
        q0 = R.sprite_quad(0, 1, 32, 20, 10, 100, 0, 0, 32, 20, fields=(0, 0))
        self.assertEqual(q1[0][0] >> 16, 4)                       # top half, quarter-texel bias
        self.assertEqual(q0[0][0] >> 16, 10 * 16)                 # bottom half
        self.assertEqual(R.field_calls(0, 1, 100), 1)

    def test_field_mode_odd_top_moves_one_line(self):
        y = 101
        Y = y * 16 + 0x7200
        up = R.sprite_quad(0, 1, 32, 20, 10, y, 0, 0, 32, 20, fields=(0, 0))
        down = R.sprite_quad(0, 1, 32, 20, 10, y, 0, 0, 32, 20, fields=(1, 1))
        self.assertEqual((up[1][0] >> 16) & 0xFFFF, Y - 16)
        self.assertEqual((down[1][0] >> 16) & 0xFFFF, Y + 16)
        self.assertEqual(R.field_calls(0, 1, y), 2)

    def test_frame_mode_masks_alternate_lines(self):
        even = R.sprite_quad(1, 1, 32, 20, 10, 100, 0, 0, 32, 20)
        odd = R.sprite_quad(1, 1, 32, 20, 10, 101, 0, 0, 32, 20)
        self.assertEqual([even[0][0], even[5][0], even[10][0]], [3, 2, 0])
        self.assertEqual([odd[0][0], odd[5][0], odd[10][0]], [2, 3, 0])

    def test_progressive_mode_reads_the_whole_texture(self):
        q = R.sprite_quad(0, 0, 32, 20, 10, 100, 0, 0, 32, 20)
        self.assertEqual(q[2][0] >> 16, 20 * 16 + 8)

    def test_woven_line(self):
        self.assertEqual(R.woven_line(100, 100, 20), (0, 0))
        self.assertEqual(R.woven_line(101, 100, 20), (10, 1))
        self.assertEqual(R.woven_line(102, 101, 20), (10, 1))
        self.assertIsNone(R.woven_line(99, 100, 20))


class Compass(unittest.TestCase):
    def state(self, **kw):
        view = [F.ONE, 0, 0, 0, 0, F.ONE, 0, 0, 0, 0, F.ONE, 0, 0, 0, 0, F.ONE]
        st = {'gate': 1, 'player': 0, 'object': 0x100, 'dialog_open': 0, 'shown': 5,
              'view': view, 'camera': [F.ZERO] * 3, 'player_xy': [F.ZERO, F.ZERO],
              'target_xy': [F.ONE, F.ZERO], 'flags': 0, 'light_flag': 0, 'light_depth': 3,
              'font_small': 0x77}
        st.update(kw)
        return st

    def test_gates(self):
        self.assertEqual(R.hud_draw_compass(self.state(gate=0))[0], [])
        self.assertEqual(R.hud_draw_compass(self.state(player=-1))[0], [])
        self.assertEqual(R.hud_draw_compass(self.state(dialog_open=1))[0], [('dialog_isOpen',)])

    def test_two_passes(self):
        calls, st = R.hud_draw_compass(self.state())
        draws = [c for c in calls if c[0] == 'model_draw']
        self.assertEqual(len(draws), 2)
        self.assertEqual((draws[0][8], draws[1][8]), (0x20, 0))
        self.assertEqual((draws[0][10], draws[1][10]), (3, 13))
        self.assertEqual(draws[0][3], draws[1][3])
        self.assertEqual(list(draws[0][3][9:]), R.compass_world(self.state()['view'], [F.ZERO] * 3,
                                                          [F.ZERO] * 2, [F.ONE, F.ZERO])[0][9:])
        self.assertEqual(calls[-2][0], 'text_drawWrappedCentered')


class ChimeSlot(unittest.TestCase):
    def test_frees_after_the_last_event(self):
        self.assertEqual(R.chime_frames([0, 10, 20], 30), 22)

    def test_frees_after_the_end_when_events_lie_beyond(self):
        self.assertEqual(R.chime_frames([0, 40], 30), 32)

    def test_without_events_frees_at_once(self):
        self.assertEqual(R.chime_frames([], 30), 1)

    def make(self, events, length, flags=A.REPORT_END):
        clip = A.Clip(A.encode_clip([((0, 0, 0), (4096, 0, 0, 0))], length, sound_times=events), 'c')
        slot = R.Slot()
        A.anim_push(slot.state, clip, flags)
        return slot, clip

    def test_stops_only_looping_voices_of_this_slot(self):
        slot, _clip = self.make([], 10)
        slot.serial = 5
        voices = [[0x14, 0, 5], [0x04, 0, 5], [0x14, 1, 5], [0x14, 0, 6], [0x10, 0, 5]]
        system = A.AnimSystem(group_limits=[127] * 256)
        ev = R.sound_seq_update_all(system, [slot], voices, False, (0, 0, 0))
        self.assertEqual(ev, [('stop', 0)])
        self.assertEqual(slot.state.count, 0)

    def test_frozen_slot_waits_unless_it_plays_while_frozen(self):
        slot, _clip = self.make([5], 10)
        system = A.AnimSystem(group_limits=[127] * 256)
        self.assertEqual(R.sound_seq_update_all(system, [slot], [], True, (0, 0, 0)), [])
        slot.while_frozen = 1
        self.assertEqual(R.sound_seq_update_all(system, [slot], [], True, (0, 0, 0))[0][0], 'advance')

    def test_released_restart_and_position_rule(self):
        slot, clip = self.make([5], 10, A.LOOP)
        slot.released = 1
        slot.duration[id(clip)] = 3
        slot.state.tracks[0].time = F.f32(4.0)
        slot.handle, slot.handle_obj, slot.no_pos = 1, (F.ONE,) * 3, 1
        system = A.AnimSystem(group_limits=[127] * 256)
        R.sound_seq_update_all(system, [slot], [], False, (F.TWO,) * 3)
        self.assertEqual(slot.pos, (F.TWO,) * 3)                 # no_pos wins over the object
        self.assertTrue(F.lt(slot.state.tracks[0].time, F.TWO))  # restarted from 0, then stepped


class ShowName(unittest.TestCase):
    def table(self):
        t = RS.TextTable()
        t.register(RS.build_uni([(b'Merchant', 'Bob')]), 0x100000)
        return t

    def test_quoted_present_key_is_found(self):
        units, length, hit = R.show_name(self.table(), b'"Merchant"')
        self.assertEqual((units, length, hit), ([ord(c) for c in 'Bob'], 3, True))

    def test_quoted_missing_key_shows_nf_and_sixteen_stripped_bytes(self):
        key = b'"AVeryLongMissingNameKey"'
        units, length, hit = R.show_name(self.table(), key)
        self.assertFalse(hit)
        self.assertEqual(bytes(units), b'NF:' + b'AVeryLongMissingNameKey'[:16])
        self.assertEqual(length, 19)

    def test_all_quotes_key(self):
        units, _length, hit = R.show_name(self.table(), b'""')
        self.assertEqual((bytes(units), hit), (b'NF:', False))


if __name__ == '__main__':
    unittest.main()
