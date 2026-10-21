#!/usr/bin/env python3
"""Synthetic tests of tools/ref_dialog.py (the contract in docs/dialog.md).

No game file is needed.  The same behaviour is compared with the original functions by
tools/difftest_dialog.py.  Run:  python3 -m unittest tools/test_ref_dialog.py
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C  # noqa: E402
import ref_dialog as R  # noqa: E402

C.set_fpu('ps2')


def host_with(nodes_text, scripts=None, network=False):
    h = R.Host()
    h.network = network
    for k, v in nodes_text.items():
        h.texts[k] = v
    h.texts.setdefault('nm', [0x4E, 0x50, 0x43])
    h.scripts = dict(scripts or {})
    return h


def speaker(h, name='npc', npc=True, flags=0x20):
    o = R.Object(0x1000, x=10.0, flags=flags, npc=npc, word24=77, props={'showname': 'nm'})
    h.objects[name] = [o]
    h.role_anims[(o.addr, 'idle')] = 5
    return o


def open_dialog(nodes, h, a=1, b=0):
    d = R.Dialog()
    msg = R.start_message('npc', 0, a, b, (0, 0, 0), 0, 0)
    assert d.on_open(h, msg, nodes)
    return d


def run_to_end(d, h, io_kw=None, limit=400):
    """Tick until the text is fully scrolled (at_end) with the reveal finished."""
    for _ in range(limit):
        d.tick(h, R.TickIO(**(io_kw or {})))
        if d.at_end and d.reveal_done:
            return
        if d.more:
            d.on_confirm(h)
    raise AssertionError('never reached the end of the text')


class Files(unittest.TestCase):
    def test_round_trip(self):
        nodes = [R.Node('c0', 'k0', 'v0', 'who', [R.Choice('a', '', 'act', 1), R.Choice('b', 'cc', '', -1)]),
                 R.Node('', 'k1', 'v1', '', [])]
        data = R.build_dbin(nodes)
        self.assertEqual(len(data), 2 * 0x448)
        self.assertEqual(data[0], 2)
        self.assertEqual(data[0x448], 0)
        back = R.parse_dbin(data)
        self.assertEqual([(n.condition, n.text, n.voice, n.speaker) for n in back],
                         [('c0', 'k0', 'v0', 'who'), ('', 'k1', 'v1', '')])
        self.assertEqual([(c.text, c.condition, c.action, c.next) for c in back[0].choices],
                         [('a', '', 'act', 1), ('b', 'cc', '', -1)])

    def test_field_offsets(self):
        data = bytearray(R.build_dbin([R.Node('C', 'T', 'V', 'S', [R.Choice('X', 'Y', 'Z', -1)])]))
        self.assertEqual(data[0x01:0x02], b'C')
        self.assertEqual(data[0x21:0x22], b'T')
        self.assertEqual(data[0x31:0x32], b'V')
        self.assertEqual(data[0x41:0x42], b'S')
        self.assertEqual(struct.unpack_from('<i', data, 0x54)[0], 1)
        self.assertEqual(data[0x58:0x59], b'X')
        self.assertEqual(data[0x68:0x69], b'Y')
        self.assertEqual(data[0x88:0x89], b'Z')
        self.assertEqual(struct.unpack_from('<i', data, 0xA8)[0], -1)

    def test_refusals(self):
        good = R.build_dbin([R.Node('', 't', 'v', '', [])])
        with self.assertRaises(ValueError):
            R.parse_dbin(good[:-1])
        bad = bytearray(good)
        bad[0] = 2
        with self.assertRaises(ValueError):
            R.parse_dbin(bytes(bad))
        bad = bytearray(good)
        struct.pack_into('<i', bad, 0x54, 13)
        with self.assertRaises(ValueError):
            R.parse_dbin(bytes(bad))
        jump = R.build_dbin([R.Node('', 't', 'v', '', [R.Choice('a', '', '', 3)])])
        with self.assertRaises(ValueError):
            R.parse_dbin(jump)

    def test_reach(self):
        nodes = [R.Node('', 't', 'v', '', [R.Choice('a', '', '', 2)]), R.Node('', 't', 'v', '', []),
                 R.Node('', 't', 'v', '', []), R.Node('c', 't', 'v', '', [R.Choice('a', '', '', 1)])]
        self.assertEqual(R.reachable_nodes(nodes), {0, 1, 2, 3})
        nodes[3].condition = ''
        self.assertEqual(R.reachable_nodes(nodes), {0, 2})


class Start(unittest.TestCase):
    def test_pick_first_accepting_condition(self):
        nodes = [R.Node('', 't'), R.Node('no', 't'), R.Node('yes', 't'), R.Node('yes2', 't')]
        ran = []

        def run(name):
            ran.append(name)
            return {'no': 0, 'yes': 4, 'yes2': 1}[name]
        self.assertEqual(R.pick_start(nodes, run), 2)
        self.assertEqual(ran, ['no', 'yes'])

    def test_missing_condition_entry_is_true(self):
        h = R.Host()
        nodes = [R.Node('', 't'), R.Node('absent', 't')]
        self.assertEqual(R.pick_start(nodes, h.run_script), 1)

    def test_node_zero_condition_also_runs(self):
        h = R.Host()
        h.scripts = {'c0': 0, 'c1': 0}
        self.assertEqual(R.pick_start([R.Node('c0', 't'), R.Node('c1', 't')], h.run_script), 0)
        self.assertEqual(h.ran, ['c0', 'c1'])

    def test_message_layout(self):
        for n in range(0, 9):
            msg = R.start_message('x' * n, 1, 2, 3, (0x11, 0x22, 0x33), -2, 5)
            name_end = 2 + n
            pad = (-name_end) % 4
            self.assertEqual(len(msg), name_end + pad + 0x14)
            self.assertTrue(all(b == 0xFF for b in msg[name_end:name_end + pad]))
            p = name_end + pad
            self.assertEqual(msg[p:p + 4], bytes([1, 2, 3, 0]))
            m = R.parse_start_message(msg)
            self.assertEqual((m['name'], m['player'], m['a'], m['b'], m['cam'], m['yaw'], m['pitch']),
                             ('x' * n, 1, 2, 3, (0x11, 0x22, 0x33), -2, 5))
        with self.assertRaises(ValueError):
            R.start_message('a\0b', 0, 0, 0, (0, 0, 0), 0, 0)
        with self.assertRaises(ValueError):
            R.start_message('a' * 128, 0, 0, 0, (0, 0, 0), 0, 0)

    def test_only_the_owner_sends(self):
        h = R.Host()
        h.local = {1}
        d = R.Dialog()
        self.assertIsNone(d.start(h, 'npc', 1, 0, (0, 0, 0), 0, 0))
        h.local = {0}
        self.assertIsNotNone(d.start(h, 'npc', 1, 0, (0, 0, 0), 0, 0))
        d.node = 0
        self.assertIsNone(d.start(h, 'npc', 1, 0, (0, 0, 0), 0, 0))

    def test_refused_while_menu_or_recall(self):
        h = host_with({'t': [0x41]})
        speaker(h)
        for recall, menu in ((3, False), (0, True)):
            h.recall, h.mission_menu = recall, menu
            d = R.Dialog()
            d.mutex = 1
            self.assertFalse(d.on_open(h, R.start_message('npc', 0, 1, 0, (0, 0, 0), 0, 0),
                                       [R.Node('', 't', 'v')]))
            self.assertEqual((d.mutex, d.node), (0, None))

    def test_open_state(self):
        h = host_with({'t': [0x41, R.CARET, 0x42]})
        o = speaker(h)
        h.layout_height = 57
        d = open_dialog([R.Node('', 't', 'v', '', [R.Choice('a'), R.Choice('b', 'gate'), R.Choice('c')])], h,
                        a=1, b=2)
        self.assertEqual(d.text, [R.SPACE, R.SPACE, 0x41, R.WIDE_NEWLINE, 0x42])
        self.assertEqual(d.visible, [0, 1, 2])          # 'gate' is missing: -1 is true
        self.assertEqual(d.choice_y[:3], [417 - 57, 417 - 38, 417 - 19])
        self.assertEqual(d.total, max(57 + 3 * 19 - 95, 0))
        self.assertEqual((d.swoop, d.side, d.cam_move, d.hud_suppressed, d.revealing), (1, 2, 1, 1, 1))
        self.assertIs(d.focus, o)
        self.assertEqual(d.focus_word, o.addr + 0x3C8)
        self.assertEqual(d.idle_anim, 5)
        self.assertEqual(d.name, [0x4E, 0x50, 0x43])
        self.assertIn(('dialog_view', 2), d.log)
        self.assertIn(('freeze_all',), d.log)

    def test_focus_needs_flag_20_and_non_npc_word(self):
        h = host_with({'t': [0x41]})
        speaker(h, flags=0)
        d = open_dialog([R.Node('', 't', 'v')], h)
        self.assertIsNone(d.focus)
        h2 = host_with({'t': [0x41]})
        o = speaker(h2, npc=False)
        d2 = open_dialog([R.Node('', 't', 'v')], h2)
        self.assertEqual(d2.focus_word, o.word24)

    def test_nearest_speaker(self):
        h = host_with({'t': [0x41]})
        far = R.Object(0x2000, x=500.0, flags=0x20)
        near = R.Object(0x3000, x=20.0, flags=0x20)
        h.objects['npc'] = [far, near]
        h.player_obj = {0: R.Object(0x4000, x=0.0)}
        d = open_dialog([R.Node('', 't', 'v')], h)
        self.assertIs(d.focus, near)
        h.player_obj = {0: None}                     # no player object: the first registered
        d = open_dialog([R.Node('', 't', 'v')], h)
        self.assertIs(d.focus, far)

    def test_too_many_visible_choices(self):
        h = host_with({'t': [0x41], 'c': [0x42]})
        speaker(h)
        with self.assertRaises(ValueError):
            open_dialog([R.Node('', 't', 'v', '', [R.Choice('c')] * 11)], h)


class Progress(unittest.TestCase):
    def setUp(self):
        self.h = host_with({'t0': [0x41] * 10, 't1': [0x42] * 10, 'a': [0x61], 'b': [0x62]},
                           scripts={'act_b': 0})
        speaker(self.h)
        self.h.player_obj = {0: R.Object(0x500)}
        self.nodes = [R.Node('', 't0', 'v', '', [R.Choice('a', '', '', -1), R.Choice('b', '', 'act_b', 1)]),
                      R.Node('', 't1', 'v', '', [])]

    def test_first_confirm_skips_the_typewriter(self):
        d = open_dialog(self.nodes, self.h, a=0)
        d.on_confirm(self.h)
        self.assertEqual((d.revealing, d.reveal_done), (0, 1))

    def test_reveal_counts_until_past_shown(self):
        d = open_dialog(self.nodes, self.h, a=0)
        for i in range(4):
            d.tick(self.h, R.TickIO(shown=2))
        self.assertEqual((d.reveal, d.reveal_done), (3, 1))

    def test_move_offline_blends(self):
        d = open_dialog(self.nodes, self.h, a=0)
        run_to_end(d, self.h, dict(shown=0))
        d.on_move(self.h, 1)
        self.assertEqual((d.cursor, d.cursor_target, d.blend), (0, 1, C.ZERO))
        ticks = 0
        while d.cursor != 1:
            d.tick(self.h, R.TickIO())
            ticks += 1
        self.assertEqual(ticks, 9)                   # 0.12 per tick passes 1.0 on the ninth
        d.on_move(self.h, 5)                         # out of range: ignored
        self.assertEqual(d.cursor_target, 1)

    def test_move_net_is_immediate(self):
        self.h.network = True
        d = open_dialog(self.nodes, self.h, a=0)
        run_to_end(d, self.h, dict(shown=0))
        d.on_move(self.h, 1)
        self.assertEqual((d.cursor, d.blend), (1, C.ONE))

    def test_choice_runs_action_then_jumps(self):
        d = open_dialog(self.nodes, self.h, a=0)
        run_to_end(d, self.h, dict(shown=0))
        d.on_move(self.h, 1)
        for _ in range(9):
            d.tick(self.h, R.TickIO())
        self.h.ran = []
        d.on_confirm(self.h)
        self.assertEqual(self.h.ran, ['act_b'])
        self.assertEqual(d.node, 1)
        self.assertEqual(d.text[:3], [R.SPACE, R.SPACE, 0x42])

    def test_no_choices_closes_and_sends_end(self):
        d = open_dialog(self.nodes, self.h, a=0)
        d.on_confirm(self.h)                         # skip typewriter
        d.node = 1
        d.visible = []
        d.at_end, d.blend = 1, C.ONE
        d.on_confirm(self.h)
        self.assertEqual(d.closing, 1)
        self.assertIn(('fade_restart', 0), d.log)
        sent = d.tick(self.h, R.TickIO(fade=C.ZERO))
        self.assertEqual(sent, [])
        sent = d.tick(self.h, R.TickIO(fade=C.ONE))
        self.assertEqual(sent, [bytes([R.MSG_END])])
        self.assertEqual(d.tick(self.h, R.TickIO(fade=C.ONE)), [])     # once

    def test_swoop_closes_through_leave(self):
        d = open_dialog(self.nodes, self.h, a=1)
        d.cam_move = 0
        d.closing = 1
        self.assertEqual(d.tick(self.h, R.TickIO(fade=C.ONE)), [bytes([R.MSG_LEAVE])])
        d.on_leave(self.h)
        self.assertEqual(d.tick(self.h, R.TickIO(camera=(0,))), [])
        self.assertEqual(d.tick(self.h, R.TickIO(camera=(1,))), [bytes([R.MSG_END])])
        self.assertEqual(d.cam_move, 0)

    def test_closing_camera_waits_for_shop(self):
        d = open_dialog(self.nodes, self.h, a=1)
        d.cam_move = -1
        self.h.shop_open = 1
        io = R.TickIO(camera=(1,))
        self.assertEqual(d.tick(self.h, io), [])
        self.assertEqual(io.asked, [])

    def test_input_gated_by_voice_without_text_option(self):
        d = open_dialog(self.nodes, self.h, a=0)
        self.h.raw_pad = {0: self.h.confirm_mask}
        self.assertEqual(d.tick(self.h, R.TickIO(text_option=0, stream_status=(1,))), [])
        d.hold = 0
        self.assertEqual(d.tick(self.h, R.TickIO(text_option=0, stream_status=(0,))),
                         [bytes([R.MSG_CONFIRM])])
        self.assertEqual(d.tick(self.h, R.TickIO(text_option=1, stream_status=(1,))),
                         [bytes([R.MSG_CONFIRM])])
        self.h.pause_menu = True
        self.assertEqual(d.tick(self.h, R.TickIO(text_option=1)), [])

    def test_active_player_flips_without_object(self):
        d = open_dialog(self.nodes, self.h, a=0)
        self.h.player_obj = {0: None}
        d.tick(self.h, R.TickIO())
        self.assertEqual(d.active_player, 1)
        self.h.player_obj = {0: R.Object(0x500), 1: R.Object(0x600, flags=8)}
        d.tick(self.h, R.TickIO())
        self.assertEqual(d.active_player, 0)

    def test_scroll_auto_without_text_option_and_paged_with_it(self):
        self.h.layout_height = 400
        d = open_dialog([R.Node('', 't0', 'v')], self.h, a=0)
        self.assertEqual(d.total, 400 - 95)
        d.tick(self.h, R.TickIO(text_option=0))
        self.assertEqual((d.scroll_target, d.more), (76, 0))
        d2 = open_dialog([R.Node('', 't0', 'v')], self.h, a=0)
        d2.tick(self.h, R.TickIO(text_option=1))
        self.assertEqual((d2.scroll_target, d2.more), (0, 1))
        d2.on_confirm(self.h)                        # typewriter skip first
        d2.on_confirm(self.h)
        self.assertEqual((d2.scroll_target, d2.more), (76, 0))
        for _ in range(16):
            d2.tick(self.h, R.TickIO(text_option=1))
        self.assertEqual(d2.scroll, 76)

    def test_end_effects(self):
        d = open_dialog(self.nodes, self.h, a=0)
        d.next_world = 'nextlevel'
        d.store_pending = 1
        d.active_player = 0
        d.on_end(self.h)
        self.assertEqual((d.node, d.mutex, d.hud_suppressed, d.pending_world, d.orient),
                         (None, 0, 0, 'nextlevel', 0xFF))
        names = [t[0] for t in d.log]
        self.assertLess(names.index('post_action'), names.index('shop'))
        self.assertIn(('shop', 0, 0, 1), d.log)
        self.assertIn(('far_clip', R.CLIP_FAR_CLOSE), d.log)

    def test_end_shop_in_net_game(self):
        self.h.network = True
        self.h.num_players = 3
        self.h.local = {2}
        d = open_dialog(self.nodes, self.h, a=0)
        d.store_pending = 1
        d.log = []
        d.on_end(self.h)
        self.assertIn(('close_local_menus', 0), d.log)
        self.assertIn(('shop', 2, 0, 1), d.log)
        self.assertIn(('fade_wait', 20), d.log)       # the active player 0 is not local

    def test_free(self):
        d = open_dialog(self.nodes, self.h, a=1)
        d.active_player = 1
        d.free()
        self.assertEqual((d.node, d.mutex, d.active_player, d.cam_move, d.swoop, d.node_index),
                         (None, 0, 0, 0, 0, -1))


class Draw(unittest.TestCase):
    def setUp(self):
        self.h = host_with({'t': [0x41] * 5, 'a': [0x61], 'b': [0x62]})
        speaker(self.h)
        self.d = open_dialog([R.Node('', 't', 'v', '', [R.Choice('a'), R.Choice('b')])], self.h, a=0)
        self.d.on_confirm(self.h)
        self.d.at_end = 1

    def ops(self, fade=C.ONE, opt=1):
        return self.d.draw(self.h, fade, opt, 0x2A, lambda: 0)

    def test_alpha_and_box(self):
        ops = self.ops(fade=C.f32(0.5))
        self.assertEqual(ops[0], ('fade_restart', 0))
        self.assertIn(('sprite', R.BOX_X, R.BOX_Y, 5, (64 << 24) | R.COLOUR_BOX), ops)
        self.assertIn(('text_begin', 6, (64 << 24) | R.COLOUR_BODY), ops)
        self.assertNotIn(('fade_restart', 0), self.ops())

    def test_choices_and_cursor(self):
        ops = self.ops()
        a = 0x80 << 24
        self.assertIn(('wrapped', R.CHOICE_X, 417 - 38, 'a', R.BODY_W, -100, 580, 19), ops)
        self.assertIn(('wrapped', R.CHOICE_X, 417 - 19, 'b', R.BODY_W, -100, 580, 19), ops)
        i = ops.index(('wrapped', R.CHOICE_X, 417 - 38, 'a', R.BODY_W, -100, 580, 19))
        self.assertEqual(ops[i - 1], ('colour', a | R.COLOUR_PICK))
        self.assertIn(('ascii', R.BODY_X, 417 - 38, 0x2A, 100000), ops)
        self.assertEqual(self.d.prompt_shown, 1)

    def test_affirmation_without_choices(self):
        self.d.visible = []
        self.d.nodes[0].raw_choices = 0
        ops = self.ops()
        self.assertIn(('wide', R.CHOICE_X, 409, 'Affirmation', R.FORCED_BUDGET), ops)
        self.assertIn(('ascii', R.BODY_X, R.MORE_Y, 0x2A, 100000), ops)

    def test_text_option_off_hides_body_and_name(self):
        ops = self.ops(opt=0)
        self.assertIn(('wrapped', R.BODY_X, 314, 'body', R.BODY_W, 295, 295, 19), ops)
        self.assertFalse([o for o in ops if o[0] == 'wide_centered'])

    def test_name_shrinks_while_closing(self):
        self.d.closing = 1
        lengths = []
        for _ in range(4):
            self.ops(fade=C.ZERO)
            lengths.append(self.d.name_len)
        self.assertEqual(lengths, [2, 1, 0, 0])

    def test_remote_player_name(self):
        self.h.local = {1}
        ops = self.ops()
        self.assertIn(('fit', 0, R.PLAYER_FIT), ops)
        self.assertIn(('ascii_centered', R.PLAYER_X, R.PLAYER_Y, 0, R.PLAYER_BUDGET), ops)

    def test_nothing_during_camera_move(self):
        self.d.cam_move = 1
        self.assertEqual(self.ops(), [])


class Interact(unittest.TestCase):
    def setUp(self):
        self.h = R.Host()
        self.h.scripts = {'talk': 0}
        self.npc = R.Object(0x10, x=0.0, y=0.0, facing=0, props={'dialogscript': 'talk'})
        self.h.player_obj = {0: R.Object(0x20, x=30.0, y=0.0)}

    def test_in_front_runs_script(self):
        d = R.Dialog()
        d.active_player = 3
        self.assertEqual(d.interact(self.h, self.npc, 0), 'script')
        self.assertEqual((d.active_player, d.mutex, self.h.ran), (0, 1, ['talk']))
        self.assertEqual(d.interact(self.h, self.npc, 0), 'busy')

    def test_behind(self):
        self.h.player_obj[0].pos[0] = C.f32(-30.0)
        self.assertEqual(R.Dialog().interact(self.h, self.npc, 0), 'behind')

    def test_missing_script_keeps_mutex(self):
        del self.npc.props['dialogscript']
        d = R.Dialog()
        self.assertEqual(d.interact(self.h, self.npc, 0), 'no script')
        self.assertEqual(d.mutex, 1)

    def test_shop(self):
        self.npc.props['shop'] = '1'
        d = R.Dialog()
        self.assertEqual(d.interact(self.h, self.npc, 0, flag800000=True), 'shop')
        self.assertEqual(d.interact(self.h, self.npc, 0, flag800000=False), 'script')

    def test_trigger_keeps_active_player(self):
        d = R.Dialog()
        d.active_player = 2
        self.assertEqual(d.trigger(self.h, self.npc), 'script')
        self.assertEqual(d.active_player, 2)


class Builtins(unittest.TestCase):
    def test_store_and_menu_inside_dialog(self):
        h = R.Host()
        d = R.Dialog()
        d.node = 0
        d.activate_store(h, 3)
        self.assertEqual((d.store_pending, d.store_index), (1, 3))
        d.activate_mission_menu(h)
        self.assertEqual(d.log, [])
        d.node = None
        d.activate_store(h, 99)
        self.assertEqual(d.store_index, 3)
        self.assertEqual(d.log, [('shop', 0, 0, 1)])
        d.activate_mission_menu(h)
        self.assertEqual(d.log[-1], ('mission_menu', 0))

    def test_swoop_and_next_world(self):
        d = R.Dialog()
        d.change_swoop(0)
        d.start_with_swoop_done()
        d.new_world_post('lvl')
        self.assertEqual((d.swoop, d.swoop_done, d.next_world), (0, 1, 'lvl'))


class Mouth(unittest.TestCase):
    def test_generic_talk_sets_idle_time(self):
        h = R.Host()
        d = R.Dialog()
        f = R.Object(0x40, anim_count=2)
        h.role_anims[(f.addr, 'talk')] = 11
        d.focus, d.idle_anim = f, 9
        d.buffers[0]['vag'] = 24000 * 16 // 28              # one second of ADPCM
        off, value = d.talk_anim(h)
        self.assertEqual(off, 0x114 + 2 * 0x20)
        self.assertAlmostEqual(C.to_float(value), -60.0, places=2)

    def test_sync_nudges_toward_audio(self):
        d = R.Dialog()
        f = R.Object(0x40, anim_count=2)
        f.flag20_track = 0
        f.tracks[0] = C.f32(0.0)
        d.focus = f
        d.sync_mouth(R.Host(), lambda: 0x400 + 24000 * 16 // 28)
        self.assertEqual(d.nudge, R.NUDGE)
        self.assertAlmostEqual(C.to_float(f.tracks[1]), 0.1, places=5)


if __name__ == '__main__':
    unittest.main()
