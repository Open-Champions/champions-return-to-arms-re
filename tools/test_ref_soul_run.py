#!/usr/bin/env python3
"""test_ref_soul_run.py - unit tests of tools/ref_soul_run.py that need no game files.

Made-up memory only, with the prologue and the base-class bodies replaced by recorders so
each test sees the switch alone: the range test and the empty states, the demon nibble,
the wander and return timers, the dissolve's three random-index particles, its +0x231
test and its end (delete or stop running), the thrown soul's velocity with and without
a target, its four sub-steps and player contact, the owned burst's matrices, and
Creature_setCharm's three refusals.  Whether the model matches the game is
tools/difftest_soul_run.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_soul_run as SR                       # noqa: E402

f32 = C.f32
CRE, NODE, TARGET, OWNER_NODE, OWNER = 0x100000, 0x120000, 0x130000, 0x140000, 0x150000
CLASS_BLOCK, PLAYER = 0x160000, 0x170000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF


class Recorder(SR.Model):
    """The switch alone: the prologue's pieces and the base bodies only record."""

    def setup(self, ev=0, demon=0, away=0, arrived=0, rooted=0):
        self.log, self.ev, self.demon, self.away, self.arrived, self.rooted = [], ev, demon, away, arrived, rooted

    def process_damage(self, c, model):
        pass

    def run(self, c, model):
        return 0

    def update_active(self, c):
        return 1

    def step_anim(self, c, speed):
        return self.ev

    def move_by(self, c, vel):
        self.log.append(('moveBy',))

    def vcall(self, obj, slot, *args):
        if slot == 16:
            return 0xC00080
        if slot == 27:
            self.log.append(('state', args[0]))
            self.w16(obj + 0x232, args[0])
            return None
        self.log.append(('slot%d' % slot,) + args)
        return 0

    def soul_is_demon_near(self, c):
        self.log.append(('demon',))
        return self.demon

    def is_away_from_home(self, c):
        self.log.append(('away',))
        return self.away

    def move_to(self, c, dest):
        self.log.append(('moveTo', dest))
        return self.arrived

    def is_not_rooted(self, c):
        return self.rooted


class Fixture(unittest.TestCase):
    answers = {}

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = Recorder(self.mem, self)
        self.model.setup()
        self.answers = dict(self.answers)
        self.mem.poke(NODE + 0xC, 4, TARGET)
        self.mem.poke(OWNER_NODE + 0xC, 4, OWNER)
        self.mem.poke(CRE + 0x24, 4, CLASS_BLOCK)
        self.mem.poke(CLASS_BLOCK + 0x1C, 4, 0xC00090)
        self.mem.poke(CRE + 0x300, 4, 1000)                  # the creature clock
        self.mem.poke(CRE + 0xF4, 4, 5000)
        self.mem.poke(CRE + 0xDC, 4, RC.ONE)
        self.mem.poke(CRE + 0x230, 1, 3)                     # the serial byte
        self.mem.poke(RC.G_SIM_FRAME, 4, 0x10)               # (0x10 ^ 3) & 0xf != 0: not due
        self.mem.poke(RC.G_NUM_PLAYERS, 4, 0)

    def get(self, name):
        if name in self.answers:
            value = self.answers[name]
            return value if callable(value) else (lambda *args: value)
        return None

    def state(self, n, **kw):
        self.mem.poke(CRE + 0x232, 2, n)
        self.model.setup(**kw)
        self.model.calls = []
        self.model.soul_run(CRE)
        return self.model.log

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]


class Switch(Fixture):
    def test_out_of_range_and_empty_states(self):
        for n in (0x23, 0x40, 0x7FFF, 0xFFFF, 2, 4, 6, 0x10, 0x11, 0x13, 0x1A, 0x1C, 0x1E, 0x21):
            self.assertEqual(self.state(n), [('slot23', 0), ('moveBy',)], hex(n))

    def test_no_zero_move_when_owned_or_thrown(self):
        self.mem.poke(CRE + 0x3C8, 4, OWNER_NODE)
        self.assertEqual(self.state(2), [('slot23', 0)])
        self.mem.poke(CRE + 0x3C8, 4, 0)
        self.answers['model_getSamplePointCount'] = 0
        self.answers['terrain_height'] = f32(-100.0)
        self.assertNotIn(('moveBy',), self.state(0x1B))

    def test_demon_check_only_on_the_nibble(self):
        self.assertNotIn(('demon',), self.state(0))
        self.mem.poke(RC.G_SIM_FRAME, 4, 0x13)               # (0x13 ^ 3) & 0xf == 0
        log = self.state(0, demon=1)
        self.assertEqual(log[-2:], [('demon',), ('state', 0x18)])
        self.mem.poke(CRE + 0x230, 1, 0xF3)                  # the byte is read signed; its nibble counts
        self.assertIn(('demon',), self.state(1, demon=0))

    def test_state0_wander(self):
        self.assertEqual(self.state(0)[-1], ('away',))
        self.assertEqual(self.state(0, away=1)[-1], ('state', 1))
        self.mem.poke(CRE + 0xF4, 4, 999)
        log = self.state(0)
        self.assertEqual(log[-1], ('state', 1))
        self.assertNotIn(('away',), log)

    def test_state1_returns_on_arrival_or_timer(self):
        self.assertEqual(self.state(1)[-1][0], 'moveTo')
        self.assertEqual(self.state(1, arrived=1)[-1], ('state', 0))
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.assertEqual(self.state(1)[-1], ('state', 0))

    def test_small_states(self):
        self.assertEqual(self.state(3)[-1], ('state', 0))
        self.mem.poke(CRE + 0x234, 4, NODE)
        self.assertEqual(self.state(3)[-1], ('moveBy',))
        self.assertEqual(self.state(5, rooted=1)[-1], ('state', 0))
        self.mem.poke(CRE + 0x11A, 2, 0x10)
        self.assertEqual(self.state(0x12)[-1], ('moveBy',))
        self.mem.poke(CRE + 0x11A, 2, 0)
        self.assertEqual(self.state(0x19)[-1], ('state', 0x18))
        self.assertEqual(self.state(0x17)[-1], ('moveBy',))
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.assertEqual(self.state(0x17)[-1], ('state', 1))
        self.assertEqual(self.state(0x18)[-1], ('moveBy',))  # not due
        self.mem.poke(RC.G_SIM_FRAME, 4, 0x13)
        self.assertEqual(self.state(0x18, demon=0)[-1], ('state', 0))


class Dissolve(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.answers['model_getSamplePointCount'] = 0xFFFFFFFE      # -2: a signed remainder
        self.answers['model_getSamplePoint'] = ((1, 2, 3), (0, 0, 0))

    def test_three_random_indices_then_wait(self):
        self.mem.poke(CRE + 0x44, 4, 0)
        self.state(0x14)
        indices = [args[4] for args in self.named('model_getSamplePoint')]
        self.assertEqual(len(indices), 3)
        d = lcg(0) >> 16
        self.assertEqual(indices[0], (d % 2) & 0xFFFFFFFF)
        self.assertEqual(len(self.named('particle_spawn')), 3)
        self.assertEqual(self.named('obj_delete'), [])

    def test_inert_byte_skips_spawn_not_draws(self):
        self.mem.poke(CRE + 0x231, 1, 1)
        self.mem.poke(CRE + 0x44, 4, 0)
        self.state(0x22)
        self.assertEqual(self.named('particle_spawn'), [])
        self.assertNotEqual(self.mem.load(CRE + 0x44, 4), 0)

    def test_end_delete_or_stop(self):
        self.answers['model_getSamplePointCount'] = 2
        self.mem.poke(CRE + 0x11A, 2, 0x80)
        self.mem.poke(CRE + 0xC, 4, 0x20)
        self.state(0x14)
        self.assertEqual(len(self.named('particle_spawn')), 3 + 2 * 2)
        self.assertEqual(self.named('obj_delete'), [(CRE,)])
        self.assertEqual(self.mem.load(CRE + 0xC, 4), 0x22)
        self.mem.poke(CRE + 0xC, 4, 0x20)
        self.state(0x22)
        self.assertEqual(self.named('obj_stopRunning'), [(CRE,)])
        self.assertEqual(self.mem.load(CRE + 0xC, 4), 0x2B)

    def test_hidden_does_nothing(self):
        self.mem.poke(CRE + 0xC, 4, 2)
        self.state(0x14)
        self.assertEqual(self.model.calls, [('Creature_applyKnockback', (CRE, 0))])


class Thrown(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.answers['model_getSamplePointCount'] = 0
        self.answers['terrain_height'] = f32(-100.0)
        for k, v in enumerate((100.0, 200.0, 50.0)):
            self.mem.poke(CRE + 0x10 + 4 * k, 4, f32(v))

    def test_no_target_flies_down_at_80(self):
        self.mem.poke(CRE + 0x38, 2, 0)
        self.state(0x1B)
        # four sub-steps of (400, 0, -80) / 240
        x = C.to_float(self.mem.load(CRE + 0x10, 4))
        z = C.to_float(self.mem.load(CRE + 0x18, 4))
        self.assertAlmostEqual(x, 100.0 + 4 * 400.0 / 240, places=3)
        self.assertAlmostEqual(z, 50.0 - 4 * 80.0 / 240, places=3)
        self.assertEqual(self.named('obj_delete'), [])       # above the ground, timer running

    def test_deleted_when_timer_runs_out(self):
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.state(0x1B)
        self.assertEqual(self.named('terrain_height'), [])
        self.assertEqual(self.named('obj_delete'), [(CRE,)])

    def test_target_turns_and_clamps_vertical_speed(self):
        self.mem.poke(CRE + 0x3CC, 4, NODE)
        for k, v in enumerate((100.0, 300.0, 400.0)):           # above the soul: z clamped to -60
            self.mem.poke(TARGET + 0x10 + 4 * k, 4, f32(v))
        log = self.state(0x1B)
        turn = [e for e in log if e[0] == 'slot26']
        self.assertEqual(len(turn), 1)
        self.assertEqual(self.mem.load(CRE + 0xB0, 4), SR.F_0_4)
        z = C.to_float(self.mem.load(CRE + 0x18, 4))
        self.assertAlmostEqual(z, 50.0 - 4 * 60.0 / 240, places=3)

    def test_player_contact_hits_once_per_step(self):
        self.mem.poke(CRE + 0x38, 2, 0)
        self.mem.poke(CRE + 0x1C, 4, f32(15.0))
        self.mem.poke(RC.G_NUM_PLAYERS, 4, 1)
        self.mem.poke(RC.G_PLAYERS + RC.REC_OBJ, 4, PLAYER)
        for k, v in enumerate((140.0, 200.0, 50.0)):
            self.mem.poke(PLAYER + 0x10 + 4 * k, 4, f32(v))
        self.mem.poke(PLAYER + 0x1C, 4, f32(12.0))
        self.state(0x1B)
        hits = self.named('damage_apply')
        self.assertEqual(len(hits), 4)
        self.assertEqual(hits[0][:6], (PLAYER, CRE, 100000, 0, 0, SR.DAMAGE_FLAGS))
        self.assertEqual(hits[0][-2:], (SR.F_10, SR.F_50))
        self.assertEqual(self.named('obj_delete'), [(CRE,)])  # a hit deletes without the ground test
        self.assertEqual(self.named('terrain_height'), [])


class Burst(Fixture):
    def test_needs_event_bit0(self):
        self.answers['model_getSamplePointCount'] = 1
        self.state(0x1D, ev=2)
        self.assertEqual(self.named('obj_delete'), [])

    def test_owned_burst_uses_the_matrices(self):
        self.answers['model_getSamplePointCount'] = 2
        self.answers['model_getSamplePoint'] = ((f32(1.0), 0, 0), (0, 0, 0))
        identity = [RC.ONE, 0, 0, 0, RC.ONE, 0, 0, 0, RC.ONE, 0, 0, 0]
        moved = identity[:9] + [f32(10.0), 0, 0]
        self.answers['creature_getAttachMatrix0'] = tuple(moved)
        self.answers['model_getAttachMatrix'] = tuple(identity)
        self.mem.poke(CRE + 0x3C8, 4, OWNER_NODE)
        self.state(0x1D, ev=1)
        self.assertEqual(self.named('creature_getAttachMatrix0'), [(OWNER,), (OWNER,)])
        self.assertEqual(self.named('model_getAttachMatrix'), [(0xC00090, CRE + 0x114, 0, RC.ONE)] * 2)
        spawns = self.named('particle_spawn')
        self.assertEqual(len(spawns), 4)
        self.assertEqual(spawns[0][1], (f32(11.0), 0, 0))
        self.assertEqual(self.mem.load(CRE + 0xC, 4) & 2, 2)
        self.assertEqual(self.named('obj_delete'), [(CRE,)])


class Charm(Fixture):
    def charm(self, flags, timer, frames=0xFFFFFFFF, team=0x1FE):
        self.mem.poke(CRE + 0xC, 4, flags)
        self.mem.poke(CRE + 0x312, 2, timer)
        self.mem.poke(CRE + 0x234, 4, NODE)
        self.mem.poke(CRE + 0x310, 1, 7)
        self.model.calls = []
        self.model.creature_set_charm(CRE, frames, team)

    def test_monster_charmed(self):
        self.charm(0x20, 0, frames=0x12345)
        self.assertEqual(self.mem.load(CRE + 0x310, 1), 0xFE)
        self.assertEqual(self.mem.load(CRE + 0x312, 2), 0x2345)
        self.assertEqual(self.mem.load(CRE + 0x234, 4), 0)
        self.assertEqual(self.model.calls, [('handle_clear', (CRE + 0x234,))])

    def test_refusals(self):
        for flags, timer in ((0x20, 0xFFFF), (0, 0), (0x60, 0), (0x40, 0)):
            self.charm(flags, timer)
            self.assertEqual(self.model.calls, [], (flags, timer))
            self.assertEqual(self.mem.load(CRE + 0x310, 1), 7)
            self.assertEqual(self.mem.load(CRE + 0x234, 4), NODE)

    def test_soul_ctor_reaches_the_body(self):
        self.mem.poke(CRE + 0xC, 4, 0x20)
        self.model.calls = []
        self.model.call('Creature_setCharm', CRE, 0xFFFFFFFF, 0)
        self.assertEqual(self.mem.load(CRE + 0x312, 2), 0xFFFF)
        self.assertEqual(self.model.calls, [('handle_clear', (CRE + 0x234,))])


if __name__ == '__main__':
    unittest.main()
