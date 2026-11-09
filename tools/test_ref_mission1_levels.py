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
        # The difftest runs the same sequence on the original (outro_after_grant_same_step).
        self.assertEqual(R.MILESTONES["drunarm"]["outro_after_grant_same_step"], outro)
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

    def test_slot3_order_matches_counts(self):
        for cut, actors in R.SLOT3_ORDER.items():
            for actor, keys in actors.items():
                got = {(actor, kind): n for (a, kind), n in R.SLOT3_KEYS[cut].items() if a == actor}
                want = {}
                for kind, _t in keys:
                    want[(actor, kind)] = want.get((actor, kind), 0) + 1
                self.assertEqual(got, want, cut)

    def test_type_names_identifiers(self):
        self.assertEqual(len(R.TYPE_NAMES), 26)
        self.assertEqual(R.TYPE_NAMES[0x29DF04], "NPC")
        self.assertTrue(all(n.replace("_", "").isalnum() for n in R.TYPE_NAMES.values()))

    def test_text_arguments_are_placeholders(self):
        """Every model native call against the difftest's argument kinds (SIG), which the
        host also uses to decode the original's calls: a text-key argument is only ever
        the placeholder, an identifier argument never is."""
        import difftest_mission1_levels as D
        seen = 0
        for level in ("strife", "drundar", "drunarm", "drunare"):
            names = [a[len(level) + 1:] for a in dir(R.Model) if a.startswith(level + "_")]
            names += [k for k, _key, _n in R.Model.PILLAR] + [key for _a, key, _n in R.Model.PILLAR] \
                if level == "drundar" else []
            names += ["switch%deffect" % k for k in range(1, 9)] if level == "drundar" else []
            for entry in names:
                m = R.Model(level)
                m.run(entry)
                for native, *args in m.log:
                    kinds = D.SIG.get(native)
                    if kinds is None:
                        continue
                    for kind, arg in zip(kinds, args):
                        if kind == "t":
                            self.assertEqual(arg, R.TEXT, (level, entry, native))
                        else:
                            self.assertNotEqual(arg, R.TEXT, (level, entry, native))
                        seen += 1
        self.assertGreater(seen, 200)

    def test_no_text_in_tables_or_code(self):
        """No string in any module table or model function constant carries text: only
        identifiers, resource names and the placeholder (no spaces)."""
        import types

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for k, v in value.items():
                    yield from strings(k)
                    yield from strings(v)
            elif isinstance(value, (tuple, list, set, frozenset)):
                for v in value:
                    yield from strings(v)

        found = []
        for name, value in vars(R).items():
            if not name.startswith("_") and not isinstance(value, (types.ModuleType, types.FunctionType, type)):
                found.extend(strings(value))
        codes = [f.__code__ for f in vars(R.Model).values() if isinstance(f, types.FunctionType)]
        while codes:
            code = codes.pop()
            consts = list(code.co_consts)
            if consts and isinstance(consts[0], str) and code.co_name != "<lambda>":
                consts = consts[1:]                      # docstring
            for c in consts:
                if isinstance(c, types.CodeType):
                    codes.append(c)
                elif isinstance(c, str):
                    found.append(c)
        self.assertGreater(len(found), 300)
        for text in found:
            self.assertNotIn(" ", text)
            self.assertTrue(text == R.TEXT or "<" not in text or text == "<empty>", text)


if __name__ == "__main__":
    unittest.main()
