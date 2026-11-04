"""Pure quest-list order. The original functions are tools/difftest_quest_log_state.py."""
import unittest

import ref_quest_log as R


def fields(text, tail=b"\xee"):
    raw = text.encode("latin1") + b"\0"
    return raw + tail * (R.FIELD - len(raw))


class QuestListTest(unittest.TestCase):
    def test_add_appends_and_stops(self):
        records = [R.blank_record(), R.blank_record(), R.blank_record()]
        records[0]["titles"][0] = fields("A", b"\x11")
        records[0]["count"] = 1
        R.quest_add(records, 2, "B", "b")
        self.assertEqual([cstr_count(rec) for rec in records], [("A", "B"), ("B",), ()])
        R.quest_add(records, 2, "A", "again")
        self.assertEqual(records[0]["count"], 2)
        self.assertEqual(records[1]["count"], 1)
        records[0]["count"] = 8
        R.quest_add(records, 2, "Late", "no")
        self.assertEqual(records[1]["count"], 1)

    def test_remove_slides_once_from_the_last_match(self):
        rec = R.blank_record()
        rec["count"] = 3
        rec["titles"] = [fields("A"), fields("B"), fields("C")] + [bytes(R.FIELD)] * 5
        rec["bodies"] = [fields("a"), fields("b"), fields("c")] + [bytes(R.FIELD)] * 5
        R.quest_remove([rec], 1, "B")
        self.assertEqual(rec["count"], 2)
        self.assertEqual([R.cstr(rec["titles"][i]) for i in range(2)], ["A", "C"])
        self.assertTrue(rec["titles"][1].startswith(b"C\0"))
        self.assertEqual(rec["titles"][1][2:9], b"Quests\0")

        dup = R.blank_record()
        dup["count"] = 3
        dup["titles"] = [fields("A"), fields("B"), fields("A")] + [bytes(R.FIELD)] * 5
        dup["bodies"] = [fields("a"), fields("b"), fields("a2")] + [bytes(R.FIELD)] * 5
        R.quest_remove([dup], 1, "A")
        self.assertEqual(dup["count"], 2)
        self.assertEqual([R.cstr(dup["titles"][i]) for i in range(2)], ["NoQuests", "B"])
        self.assertTrue(dup["titles"][2].startswith(R.PLACEHOLDER))

    def test_clear_overlays_only_the_active_records(self):
        records = [R.blank_record() for _ in range(3)]
        records[0]["count"] = 1
        records[0]["titles"][0] = fields("A")
        records[1]["count"] = 2
        records[2]["count"] = 3
        R.quest_clear(records, 2)
        self.assertEqual([rec["count"] for rec in records], [0, 0, 3])
        self.assertTrue(records[0]["titles"][0].startswith(R.PLACEHOLDER))
        self.assertEqual(records[2]["titles"][0], bytes(R.FIELD))

    def test_row_positions_add_the_wrap_return(self):
        self.assertEqual(R.row_positions([0, 0], [0, 0]), [(114, 114), (136, 136)])
        self.assertEqual(R.row_positions([1, 3], [0, 2]), [(114, 115), (137, 140)])


def cstr_count(rec):
    return tuple(R.cstr(rec["titles"][i]) for i in range(rec["count"]))


if __name__ == "__main__":
    unittest.main()
