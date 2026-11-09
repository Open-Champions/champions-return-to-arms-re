"""Unit tests for tools/ref_mission1_levels.py (no private inputs needed)."""
import unittest

import ref_mission1_levels as R


def frames_until(model, native, arg, limit=3000):
    for frame in range(1, limit):
        mark = len(model.log)
        model.frame()
        if any(e[0] == native and e[1:2] == (arg,) for e in model.log[mark:]):
            return frame
    raise AssertionError("never: %s %s" % (native, arg))


class ScaledTime(unittest.TestCase):
    def test_minus_one(self):
        for n in (1, 100, 101, 102, 250, 252, 275, 277, 300, 302, 1500, 1502):
            self.assertEqual(R.scaled_time(n), n - 1)


class Deferred(unittest.TestCase):
    def test_direct_queue_runs_two_frames_later(self):
        m = R.Model("drunarm")
        m.run("start")
        m.frame()
        self.assertNotIn("shardCheckLoop", m.scripts[1:])
        m.frame()
        self.assertEqual(m.scripts[-1], "shardCheckLoop")

    def test_knights_then_cazic(self):
        m = R.Model("drunare")
        for entry in ("setv4d6b", "setv772a", "setv5138"):
            m.run(entry)
        self.assertEqual(m.queued(), [])
        m.run("setvcccf")
        self.assertEqual(frames_until(m, "cutScene", "cazic"), 303)

    def test_avatar_end_doubles(self):
        m = R.Model("drunare")
        m.run("callScria381")
        self.assertEqual(frames_until(m, "cutScene", "bossdefeated"), 878)
        self.assertEqual(m.post, "levelChange")
        m.run_post()
        self.assertEqual((m.pending, m.mission1 & 2), ("hub2", 2))

    def test_shard_grant_restarts_outro(self):
        m = R.Model("drunarm")
        m.run("start")
        m.run("callScric1d7")
        m.run_post()
        m.frame()                      # rallosHPcheck queued directly: first runs frame 2
        m.hp["rallos"] = 0
        m.counts[0] = 1
        grant = frames_until(m, "grantMission", 1)
        outro = frames_until(m, "cutScene", "rallosruns")
        # Counted again from the grant frame. Here shardCheckLoop runs before endDelay
        # in that frame (queue order), so endDelay already counts 1 in it: 276 more.
        self.assertEqual(outro, 276)
        self.assertEqual(m.post, "removeRallos")
        self.assertGreater(grant, 0)

    def test_paused_switch_loop_stops(self):
        m = R.Model("drundar")
        m.run("switchcod546")
        m.frame()
        m.frame()
        self.assertIn("switch1effect", m.queued())
        m.paused = 1
        m.frame()
        m.frame()
        self.assertNotIn("switch1effect", m.queued())


class Tables(unittest.TestCase):
    def test_cutscenes_unique_and_requested_once(self):
        names = [row[3] for row in R.CUTSCENES]
        self.assertEqual(len(names), len(set(names)), names)
        self.assertEqual(len(names), 9)

    def test_travel_matches_model(self):
        for level, entry, _off, dest in R.NEWWORLD:
            if entry == "exitzone":
                continue
            m = R.Model(level)
            m.run(entry)
            self.assertEqual(m.pending, dest, (level, entry))

    def test_no_text_keys(self):
        for row in R.CUTSCENES:
            for value in row:
                self.assertNotIn("<text>", str(value))


if __name__ == "__main__":
    unittest.main()
