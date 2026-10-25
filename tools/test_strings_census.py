#!/usr/bin/env python3
"""Synthetic test of tools/strings_census.py: a made-up disc with one string file, one
credits file and one level script.  No game file is used."""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_strings as R        # noqa: E402
import strings_census as C     # noqa: E402


def lmp(entries):
    """u32 count, count x (nameOffset, dataOffset, size), then names and data."""
    head = 4 + 12 * len(entries)
    names = b''.join(name + b'\0' for name, _d in entries)
    out = bytearray(struct.pack('<I', len(entries)))
    name_at, data_at = head, head + len(names)
    blobs = bytearray()
    for name, data in entries:
        out += struct.pack('<III', name_at, data_at + len(blobs), len(data))
        name_at += len(name) + 1
        blobs += data
    return bytes(out + names + blobs)


def gob(lumps):
    """40-byte records name[32], offset, size; an empty name ends the list."""
    table = 40 * (len(lumps) + 1)
    out, data = bytearray(), bytearray()
    for name, blob in lumps:
        out += name.ljust(32, b'\0') + struct.pack('<II', table + len(data), len(blob))
        data += blob
    out += b'\0' * 40
    return bytes(out + data)


def script(calls, imports):
    """A minimal script.scr: header at +0x60, code, packed strings, imports."""
    strings = bytearray()
    offsets = {}
    for _name, args in calls:
        for a in args:
            if isinstance(a, bytes) and a not in offsets:
                offsets[a] = len(strings)
                raw = a + b'\0'
                raw += b'\0' * (-len(raw) % 4)
                for i in range(0, len(raw), 4):
                    strings += raw[i:i + 4][::-1]
    code = []
    for name, args in calls:
        for a in reversed(args):
            code += [0x27, offsets[a] if isinstance(a, bytes) else a & 0xFFFFFFFF]
        code += [0x27, 4 * len(args), 0x7B, imports.index(name)]
    code_b = struct.pack('<%dI' % len(code), *code)
    head = 0x40
    code_off = head
    str_off = code_off + len(code_b)
    ext_off = str_off + len(strings)
    ext = b''.join(struct.pack('<I', 0) + n.encode().ljust(20, b'\0') for n in imports)
    end_off = ext_off + len(ext)
    hdr = bytearray(0x40)
    struct.pack_into('<III', hdr, 0x0C, code_off, str_off, ext_off)
    struct.pack_into('<IIII', hdr, 0x20, 0, 0, len(imports), ext_off)
    return bytes(0x60) + bytes(hdr) + code_b + bytes(strings) + ext + bytes(end_off - end_off)


class Census(unittest.TestCase):
    def test_synthetic_disc(self):
        pairs = [(b'hello', 'Hi'), (b'cnt', 'n=%d'), (b'long', 'y' * 40), (b'hello', 'again'),
                 (b'end', 'v%d')]
        uni = R.build_uni(pairs)
        imports = ['setInfo', 'addHelpMessageF', 'showBust', 'showCompass', 'addHelpMessage']
        calls = [('setInfo', [b'hello']), ('setInfo', [b'nokey']),
                 ('addHelpMessageF', [b'cnt', 5, b'end', 7]),
                 ('showBust', [b'face', b'long', 1, -1]),
                 ('showCompass', [b'obj', b'hello']),
                 ('addHelpMessage', [b'hello', b'cnt'])]
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, 'GTEXT.LMP'), 'wb') as f:
                f.write(lmp([(b'gtext.uni', uni)]))
            with open(os.path.join(root, 'CREDITS.LMP'), 'wb') as f:
                f.write(lmp([(b'credits.txt', b'\xff\xfeA\0')]))
            with open(os.path.join(root, 'LEVEL.GOB'), 'wb') as f:
                f.write(gob([(b'level.lmp', lmp([(b'script.scr', script(calls, imports))]))]))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(C.census(root), 0)
        text = out.getvalue()
        self.assertIn('string files: 2 (.uni 1, .txt 1)', text)
        self.assertRegex(text, r'entries\s+5\n')
        self.assertRegex(text, r'keys repeated \(later copies unreachable\)\s+1\n')
        self.assertRegex(text, r'texts ending in a conversion\s+2\n')
        self.assertIn('level scripts: 1', text)
        setinfo = text.split('  setInfo')[1].split('  addHelpMessage')[0]
        self.assertRegex(setinfo, r'calls\s+2\n')
        self.assertRegex(setinfo, r'key missing from GTEXT \(shows NF:\)\s+1\n')
        f = text.split('  addHelpMessageF')[1].split('  showBust')[0]
        self.assertRegex(f, r'F formatter read past the terminator\s+2\n')
        bust = text.split('  showBust')[1].split('  showCompass')[0]
        self.assertRegex(bust, r'text over its buffer \(31 units\)\s+1\n')
        self.assertRegex(bust, r'bust maximum -1 \(value shown as a number\)\s+1\n')
        # no key, text or name argument is printed
        for secret in ('hello', 'nokey', 'yyyy', 'again', 'face', 'obj', 'n=', 'Hi'):
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()
