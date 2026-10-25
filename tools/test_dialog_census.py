#!/usr/bin/env python3
"""Synthetic tests of tools/dialog_census.py: the script call graph and objects.ob reader.
No game file is needed."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_census as D  # noqa: E402


def build_script(entries, imports, code_words, strings):
    """A script.scr in the layout of tools/scr.py: header at +0x60, 24-byte records,
    string pool stored as byte-reversed 32-bit words."""
    pool = bytearray()
    offsets = {}
    for s in strings:
        offsets[s] = len(pool)
        pool += s.encode() + b'\0'
    while len(pool) % 4:
        pool += b'\0'
    swapped = b''.join(bytes(pool[i:i + 4])[::-1] for i in range(0, len(pool), 4))
    code = struct.pack('<%dI' % len(code_words), *[w(offsets) if callable(w) else w for w in code_words])
    recs = lambda items: b''.join(struct.pack('<I', v) + n.encode().ljust(20, b'\0') for v, n in items)
    internal = recs(entries)
    external = recs([(0, n) for n in imports])
    body = bytearray()
    code_off = 0x40
    int_off = code_off + len(code)
    ext_off = int_off + len(internal)
    str_off = ext_off + len(external)
    end_off = str_off + len(swapped)
    head = bytearray(0x40)
    struct.pack_into('<III', head, 0x0C, code_off, str_off, end_off)
    struct.pack_into('<IIII', head, 0x20, len(entries), int_off, len(imports), ext_off)
    body = head + code + internal + external + swapped
    return bytes(0x60) + bytes(body)


def push(v):
    return [0x27, v]


def sysreq(n):
    return [0x7B, n]


class ScriptGraph(unittest.TestCase):
    def setUp(self):
        imports = ['startDialog', 'callScript', 'postAction', 'grantMission', 'setv']
        # entry A at 0: startDialog('npc', 1, 0); callScript('B'); return
        # entry B: grantMission(3); call C; return     C (internal): setv; return
        # entry P: postAction('B'); return
        a = [0x2E] + push(lambda o: o['npc']) + push(1) + push(0) + push(12) + sysreq(0) + \
            push(lambda o: o['B']) + push(4) + sysreq(1) + [0x30]
        b_start = len(a) * 4
        c_start = b_start + 4 * 10
        b = [0x2E] + push(3) + push(4) + sysreq(3) + [0x31, c_start] + [0x30]
        c = [0x2E] + push(0) + push(4) + sysreq(4) + [0x30]
        p_start = c_start + 4 * len(c)
        p = [0x2E] + push(lambda o: o['B']) + push(4) + sysreq(2) + [0x30]
        self.assertEqual(len(b), 10)
        data = build_script([(0, 'A'), (b_start, 'B'), (p_start, 'P')], imports, a + b + c + p,
                            ['npc', 'B'])
        self.s = D.Script(data)

    def test_entries_and_calls(self):
        self.assertEqual(sorted(self.s.entries), ['A', 'B', 'P'])
        names = [b for _, b, _ in self.s.calls]
        self.assertEqual(names, ['startDialog', 'callScript', 'grantMission', 'setv', 'postAction'])
        _off, _b, args = self.s.calls[0]
        self.assertEqual(self.s.string(args[0]), 'npc')
        self.assertEqual(args[1:], [1, 0])

    def test_reach_follows_callscript_and_call(self):
        now, later = self.s.reach('A')
        self.assertEqual(now['grantMission'], 1)
        self.assertEqual(now['setv'], 1)
        self.assertEqual(sum(later.values()), 0)

    def test_post_action_counts_later(self):
        now, later = self.s.reach('P')
        self.assertEqual(now['postAction'], 1)
        self.assertEqual(now['grantMission'], 0)
        self.assertEqual(later['grantMission'], 1)

    def test_missing_entry_reaches_nothing(self):
        now, later = self.s.reach('nope')
        self.assertEqual((sum(now.values()), sum(later.values())), (0, 0))


class Objects(unittest.TestCase):
    def test_props(self):
        strings = b'\0NPC\0name=x\0dialogScript=talk\0showName=nm\0'
        table = 8 + 36
        rec = struct.pack('<ihh3f', 1, 36, 0, 0.0, 0.0, 0.0) + struct.pack('<4i', 5, 12, 30, 0)
        blob = struct.pack('<hHi', 1, 0, table) + rec + strings
        got = list(D.object_props(blob))
        self.assertEqual(got, [('NPC', {'name': 'x', 'dialogscript': 'talk', 'showname': 'nm'})])


if __name__ == '__main__':
    unittest.main()
