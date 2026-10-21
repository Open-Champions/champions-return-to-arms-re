#!/usr/bin/env python3
"""Synthetic tests of the record reader in tools/objects_census.py (no game file needed)."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import objects_census as C              # noqa: E402


def build(records, flags=0):
    """An object list in the docs/objects.md layout: records [(class, angle, x, y, z, [props])]."""
    strings, index = bytearray(b'\0'), {}

    def intern(text):
        if text not in index:
            index[text] = len(strings)
            strings.extend(text + b'\0')
        return index[text]
    body = bytearray()
    for cls, angle, x, y, z, props in records:
        offs = [intern(p) for p in props]
        body += struct.pack('<ihH3f', intern(cls), 20 + 4 * (len(offs) + 1), angle, x, y, z)
        body += struct.pack('<%di' % (len(offs) + 1), *(offs + [0]))
    return struct.pack('<hHi', len(records), flags, 8 + len(body)) + bytes(body) + bytes(strings)


class Records(unittest.TestCase):
    def test_round_trip(self):
        blob = build([(b'Gen', 0x4000, 1.0, 2.0, 3.0, [b'name=g1', b'speed=2']),
                      (b'Box', 0, 0.0, 0.0, 0.0, []),
                      (b'Mon', 7, 5.0, 5.0, 0.0, [b'name="m1"', b'name=m2', b'hide=1'])])
        recs = C.parse_objects(blob)
        self.assertEqual([r[0] for r in recs], [b'Gen', b'Box', b'Mon'])
        self.assertEqual(recs[0][1], [b'name=g1', b'speed=2'])
        self.assertEqual(recs[1][1], [])

    def test_name_props_strip_quotes_and_case_sensitive_key(self):
        self.assertEqual(C.name_props([b'name="m1"', b'name=m2', b'Name=x', b'names=y', b'hide=1']), [b'm1', b'm2'])

    def test_bad_record_size_refused(self):
        blob = bytearray(build([(b'A', 0, 0.0, 0.0, 0.0, [])]))
        struct.pack_into('<h', blob, 12, 0)
        with self.assertRaises(ValueError):
            C.parse_objects(bytes(blob))


if __name__ == '__main__':
    unittest.main()
