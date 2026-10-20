"""Tests for fx_level_lights.py on synthetic tables and object files (no game file).

Run: python3 -m unittest discover -s tools -p test_fx_level_lights.py
"""
import json
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fx_level_lights as F                     # noqa: E402


def memory_reader(words):
    """words: va -> u32.  Strings are stored as the bytes of a latin1 value."""

    def u32(va):
        return words.get(va, 0)

    def cstr(va):
        raw = words.get(va)
        if isinstance(raw, str):
            return raw
        return None

    return u32, cstr


def put_row(words, table, index, name, flags, name_at):
    va = table + index * F.ROW_BYTES
    words[va] = name_at
    words[va + F.FLAG_OFFSET] = flags
    words[name_at] = name


class Table(unittest.TestCase):
    def test_flags_select_the_base_level(self):
        table = 0x1000
        words = {}
        put_row(words, table, 0, 'alpha', 0x04000000 | 0x20000000, 0x2000)
        put_row(words, table, 1, 'beta', 0x20000000, 0x2010)
        put_row(words, table, 2, '', 0, 0)          # null name pointer ends the table
        words[table + 2 * F.ROW_BYTES] = 0
        words[table + 2 * F.ROW_BYTES + F.FLAG_OFFSET] = 0x04000000
        rows, default = F.read_levels(*memory_reader(words), table=table)
        self.assertEqual([row['name'] for row in rows], ['alpha', 'beta'])
        self.assertEqual([row['base_level'] for row in rows], [0x40, 0x20])
        self.assertEqual(default['index'], 2)
        self.assertEqual(default['base_level'], 0x40)

    def test_lookup_passes(self):
        rows = [
            {'index': 0, 'name': 'alpha', 'flags': 0, 'base_level': 0x80},
            {'index': 1, 'name': 'alpha_extra', 'flags': 1, 'base_level': 0x80},
            {'index': 2, 'name': 'beta', 'flags': 2, 'base_level': 0x80},
        ]
        default = {'index': 3, 'flags': 0, 'base_level': 0x80}
        self.assertEqual(F.lookup_level(rows, default, 'alpha', 'extra')['index'], 1)
        self.assertEqual(F.lookup_level(rows, default, 'alpha')['index'], 0)
        self.assertEqual(F.lookup_level(rows, default, 'zz_beta_zz')['index'], 2)
        self.assertEqual(F.lookup_level(rows, default, 'missing')['index'], 3)


def build_objects(entries):
    """entries: (class name, x, y, z).  Records are 20 bytes and carry no properties."""
    rec = 20
    strings = bytearray()
    offs = []
    for name, _x, _y, _z in entries:
        offs.append(len(strings))
        strings += name.encode('latin1') + b'\0'
    blob = bytearray(struct.pack('<hHi', len(entries), 0, 8 + len(entries) * rec))
    for (_name, x, y, z), off in zip(entries, offs):
        blob += struct.pack('<ihH3f', off, rec, 0, x, y, z)
    blob += strings
    return bytes(blob)


def build_lump(name, payload):
    name_b = name.encode('latin1') + b'\0'
    name_off = 16
    data_off = name_off + len(name_b)
    head = struct.pack('<IIII', 1, name_off, data_off, len(payload))
    return head + name_b + payload


class Markers(unittest.TestCase):
    def test_colours_and_direction(self):
        blob = build_objects([
            ('charAmbient_Light', 100.0, 60.0, 41.0),
            ('charDirectional_Light', 300.0, 200.0, 100.0),
            ('charDirectional_LightD', 0.0, -1.0, 1.0),
            ('Other', 1.0, 2.0, 3.0),
        ])
        got = F.markers_from_objects(blob)
        self.assertEqual(got['ambient'], [50, 30, 20])
        self.assertEqual(got['sun'], [150, 100, 50])
        self.assertEqual(got['direction'], [0.0, -1.0, 1.0])

    def test_lump_and_join(self):
        ob = build_objects([
            ('charAmbient_Light', 10.0, 20.0, 30.0),
            ('charDirectional_LightD', 0.0, -2.0, 2.0),
        ])
        lumps = F.object_blobs('Alpha.lmp', build_lump('objects.ob', ob))
        self.assertEqual(len(lumps), 1)
        files = [dict(F.markers_from_objects(blob), source=source) for source, blob in lumps]
        levels = [
            {'index': 0, 'name': 'other', 'flags': 0, 'base_level': 0x80},
            {'index': 1, 'name': 'alpha', 'flags': 0x20000000, 'base_level': 0x20},
        ]
        F.attach_markers(levels, files)
        self.assertEqual(files[0]['level_index'], 1)
        self.assertEqual(levels[1]['ambient'], [5, 10, 15])
        self.assertEqual(levels[1]['base_level'], 0x20)
        self.assertNotIn('ambient', levels[0])
        json.dumps({'levels': levels, 'files': files, 'defaults': F.DEFAULTS})


if __name__ == '__main__':
    unittest.main()
