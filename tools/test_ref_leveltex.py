#!/usr/bin/env python3
"""Unit tests of tools/ref_leveltex.py on synthetic cells.  No game file is read; the
fixtures are built by ref_leveltex.build_cell / build_directory from texels and code
lengths chosen here.  Whether the model matches the disc is recorded in
docs/formats/level-texture.md ("What was checked").

  python3 -m unittest discover -s tools -p 'test_ref_leveltex.py'
"""
import os
import struct
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_leveltex as L                        # noqa: E402
from model_info import gs_addr32, gs_addr8, clut_order   # noqa: E402


def lengths_all_literals():
    """8-bit codes for the 256 literals and nothing else: a complete code."""
    return [8] * 256 + [0] * (L.SYMBOL_COUNT - 256)


def lengths_mixed():
    """Short codes for a few symbols, long ones for the rest, every special symbol coded:
    exercises the fast table (lengths <= 8) and the slow path (lengths 9..16)."""
    ln = [0] * L.SYMBOL_COUNT
    ln[0x100] = 2            # back-reference -1
    ln[0x105] = 2            # successor 0
    ln[7] = 3
    ln[0x101] = 4
    ln[0x102] = 5
    ln[0x103] = 6
    ln[0x104] = 7
    for s in range(0x106, 0x10d):
        ln[s] = 9
    rest = [s for s in range(256) if s != 7]
    for i, s in enumerate(rest):
        ln[s] = 11 if i < 100 else 12
    return ln


def gradient_block(seed):
    return [(x * 3 + y * 5 + seed) & 0xff for y in range(16) for x in range(16)]


def solid_block(v):
    return [v] * 256


class TestTables(unittest.TestCase):
    def test_canonical_tables_are_prefix_free_and_complete_for_literals(self):
        symbols, S, T = L.canonical_tables(lengths_all_literals())
        self.assertEqual(list(symbols), list(range(256)))
        self.assertEqual(T[8], 255)
        self.assertEqual(S[8], 0)
        self.assertTrue(all(T[k] == -1 for k in range(1, 17) if k != 8))
        self.assertEqual((S[0], S[17], T[0]), (0, 0, -1))

    def test_fast_table_matches_slow_decode_for_every_prefix(self):
        ln = lengths_mixed()
        symbols, S, T = L.canonical_tables(ln)
        fast = L.build_fast_table(symbols, S, T)
        for i in range(256):
            sym, k = fast[i]
            found = None
            for kk in range(1, 9):
                if T[kk] >= (i >> (8 - kk)):
                    found = (symbols[(i >> (8 - kk)) + S[kk]], kk)
                    break
            self.assertEqual((sym, k), found or (0, 0), i)
        # every length in use is reachable: short codes through the fast table, long ones not
        self.assertTrue(any(k == 2 for s, k in fast))
        self.assertTrue(any(k == 0 for s, k in fast))

    def test_code_of_roundtrip_through_decode_symbol(self):
        ln = lengths_mixed()
        symbols, S, T = L.canonical_tables(ln)
        tables = L.Tables(bytes(0x400), bytes(0x800), symbols, S, T)
        for sym in range(L.SYMBOL_COUNT):
            if not ln[sym]:
                continue
            code, k = L.code_of(sym, ln)
            bits = [(code >> (k - 1 - b)) & 1 for b in range(k)] + [0] * 32
            word = 0
            for b in bits[:32]:
                word = (word << 1) | b
            stream = struct.pack('<HH', word >> 16, word & 0xffff)
            r = L.BitReader(stream, 0)
            self.assertEqual(L.decode_symbol(r, tables), sym)
            self.assertEqual(r.pos, k)

    def test_read_tables_refuses_bad_canonical_data(self):
        cell = L.build_cell([(16, 16, [(0, 0, 0, 0, [solid_block(1)])])], lengths_all_literals())
        t = L.parse_cell(cell)[0]
        q = t.palette_off + L.HUFFMAN_COUNT_OFF
        n = L.u32(cell, q)
        bad = bytearray(cell)
        # T[8] above 2**8 - 1
        struct.pack_into('<i', bad, q + 4 + 2 * n + 4 * L.S_WORDS + 4 * 8, 256)
        with self.assertRaises(L.FormatError):
            L.read_tables(bytes(bad), t.palette_off)
        bad = bytearray(cell)
        struct.pack_into('<H', bad, q + 4, 269)             # a symbol above 268
        with self.assertRaises(L.FormatError):
            L.read_tables(bytes(bad), t.palette_off)


class TestBitReader(unittest.TestCase):
    def test_words_are_little_endian_and_consumed_msb_first(self):
        # word 0 = 0x8000 -> first bit 1; word 1 = 0x0001 -> bit 31 is 1
        stream = struct.pack('<HH', 0x8000, 0x0001) + b'\0\0'
        r = L.BitReader(stream, 0)
        self.assertEqual(r.peek16() >> 15, 1)
        r.pos = 1
        self.assertEqual(r.peek16(), 0)
        r.pos = 16
        self.assertEqual(r.peek16(), 0x0001)
        r.pos = 31
        self.assertEqual(r.peek16() >> 15, 1)

    def test_running_past_the_cell_is_refused(self):
        r = L.BitReader(b'\0\0', 0)
        with self.assertRaises(L.FormatError):
            r.peek16()


class TestBlock(unittest.TestCase):
    def test_permutation_is_the_gs_swizzle(self):
        """Byte k of the uploaded 32-bit 8x8 block (raster, 4 bytes per pixel) is texel
        (x + 16 y) of the 16x16 8-bit block: check against the GS address formulas used
        for lump textures, for every one of the 256 positions."""
        perm = L.block_permutation()
        self.assertEqual(sorted(perm), list(range(256)))
        for k in range(256):
            r, c, j = k >> 5, (k >> 2) & 7, k & 3
            a32 = gs_addr32(c, r, 1) + j               # where the upload puts this byte
            tx, ty = perm[k] & 15, perm[k] >> 4
            a8 = gs_addr8(tx, ty, 1)                    # where the sampler reads this texel
            self.assertEqual(a32, a8, k)

    def test_decode_block_literals_backrefs_and_successors(self):
        ln = lengths_mixed()
        symbols, S, T = L.canonical_tables(ln)
        succ = bytearray(0x800)
        succ[9 * 8 + 0] = 42                          # after a 9 comes 42 as "successor 0"
        succ[42 * 8 + 1] = 7
        tables = L.Tables(bytes(0x400), bytes(succ), symbols, S, T)
        texels = gradient_block(0)
        texels[1] = texels[0]                         # -1
        texels[16] = texels[0]                        # -16
        texels[17] = texels[0]                        # -17
        texels[31] = texels[16]                       # -15 from 31 is 16
        texels[2] = texels[0]                         # -2
        texels[40] = 9
        texels[41] = 42                               # successor 0 of 9
        texels[42] = 7                                # successor 1 of 42

        def choose(i, tx, prev):
            return {1: 0x100, 16: 0x101, 17: 0x102, 31: 0x103, 2: 0x104, 41: 0x105, 42: 0x106}.get(i)
        stream = L.encode_block(texels, ln, choose)
        out, bits = L.decode_block(stream, 0, tables)
        self.assertEqual(list(out), texels)
        self.assertLessEqual(bits, len(stream) * 8)
        self.assertGreater(len(stream) * 8 - bits, -1)

    def test_backref_before_start_is_refused(self):
        ln = lengths_mixed()
        symbols, S, T = L.canonical_tables(ln)
        tables = L.Tables(bytes(0x400), bytes(0x800), symbols, S, T)
        stream = L.encode_block([0] * 256, ln, lambda i, tx, prev: 0x100 if i == 0 else None)
        with self.assertRaises(L.FormatError):
            L.decode_block(stream, 0, tables)


class TestCell(unittest.TestCase):
    def setUp(self):
        self.ln = lengths_mixed()
        blocks_a = [gradient_block(s) for s in range(4)]
        # texture 0: 40 x 20 texels -> blocks (0..2) x (0..1); an L shape of two rectangles
        self.tex0 = (40, 20, [(0, 0, 1, 1, [blocks_a[0], blocks_a[1], blocks_a[2], blocks_a[3]]),
                              (2, 0, 2, 0, [solid_block(5)])])
        # texture 1: 140 x 18 -> DBW 2, blocks 0..8 x 0..1; only the second block row is sent
        self.tex1 = (140, 18, [(0, 1, 8, 1, [gradient_block(9 + i) for i in range(9)])])
        stored = bytearray(0x400)                       # entry i sits at the CLUT position of i
        for i in range(256):
            stored[clut_order(i) * 4:clut_order(i) * 4 + 4] = bytes((i, 255 - i, i ^ 0x55, 0x80 if i & 1 else 0))
        self.pal = bytes(stored)
        self.cell = L.build_cell([self.tex0, self.tex1], self.ln, palette=self.pal)
        self.texs = L.parse_cell(self.cell)

    def test_header_fields(self):
        t0, t1 = self.texs
        self.assertEqual((t0.width, t0.height, t0.flags), (40, 20, 0x10c))
        self.assertEqual(t0.tex0_fields()['psm'], L.PSMT8)
        self.assertEqual(t0.tex0_fields()['tbw'], 2 * t0.dbw)
        self.assertEqual((t0.dbw, t1.dbw), (1, 2))
        self.assertEqual(t0.blocks, L.allocation_blocks(t0))
        # blocks: highest written block is (2, 0) (block table row 0 col 2 = 4), (2, 1) is never sent -> 4 + 5
        self.assertEqual(t0.blocks, 4 + 4 + 1)
        # texture 1: block (8, 1) is in page 1 -> 32 + table row 1 col 0 = 2 -> 4 + 35
        self.assertEqual(t1.blocks, 4 + 34 + 1)
        self.assertEqual(t0.qwords, 0)                 # 0 in the file, filled by relocation
        self.assertEqual(L.relocated_qwords(t0.rects), 0x48 + (6 + 16 * 4) + (6 + 16 * 1))
        self.assertEqual(L.relocated_qwords(t1.rects), 0x48 + 6 + 16 * 9)

    def test_records_are_read_in_engine_order(self):
        t0 = self.texs[0]
        self.assertEqual([r[:4] for r in t0.rects], [(0, 0, 1, 1), (2, 0, 2, 0)])
        self.assertEqual(len(t0.rects[0][4]), 4)
        self.assertEqual(self.cell[t0.record_end - 4], 0xff)

    def test_decode_texture_matches_the_fixture_and_the_gs_replay(self):
        t0, t1 = self.texs
        img = L.decode_texture(self.cell, t0)
        blocks = {(0, 0): gradient_block(0), (1, 0): gradient_block(1), (0, 1): gradient_block(2),
                  (1, 1): gradient_block(3), (2, 0): solid_block(5)}
        for y in range(20):
            for x in range(40):
                b = blocks.get((x >> 4, y >> 4))         # block (2, 1) is not sent
                want = b[(y & 15) * 16 + (x & 15)] if b else 0
                self.assertEqual(img.indices[y * 40 + x], want, (x, y))
                self.assertEqual(img.covered[y * 40 + x], b is not None, (x, y))
        via = L.decode_texture_via_gs(self.cell, t0)
        self.assertEqual(via.indices, img.indices)
        self.assertEqual(via.covered, img.covered)
        img1 = L.decode_texture(self.cell, t1)
        via1 = L.decode_texture_via_gs(self.cell, t1)
        self.assertEqual(via1.indices, img1.indices)
        # row 0 of blocks was not sent: uncovered, index 0
        self.assertFalse(any(img1.covered[:140 * 16]))
        self.assertTrue(all(img1.covered[140 * 16:]))
        self.assertEqual(img1.indices[17 * 140 + 139], gradient_block(9 + 8)[1 * 16 + 11])

    def test_palette_order_and_rgba(self):
        img = L.decode_texture(self.cell, self.texs[0])
        for i in (0, 7, 8, 16, 24, 31, 200, 255):
            self.assertEqual(img.palette[i], (i, 255 - i, i ^ 0x55, 0x80 if i & 1 else 0))
        self.assertEqual(img.rgba(0, 0), img.palette[gradient_block(0)[0]])

    def test_upload_transfers_have_the_workers_registers(self):
        t0 = self.texs[0]
        tr = L.upload_transfers(self.cell, t0)
        self.assertEqual([(dx, dy, w, h) for dx, dy, w, h, buf in tr], [(0, 0, 16, 16), (16, 0, 8, 8)])
        self.assertEqual(len(tr[0][4]), 16 * 16 * 4)
        # pixel (0, 0) of the first rectangle is bytes perm[0..3] of block (0, 0)
        px = L.block_pixels(bytes(gradient_block(0)))
        self.assertEqual(tr[0][4][:4], px[:4])
        self.assertEqual(tr[0][4][8 * 4:8 * 4 + 4], L.block_pixels(bytes(gradient_block(1)))[:4])

    def test_shared_blocks_and_shared_palette(self):
        t0, t1 = self.texs
        self.assertEqual(t0.palette_off, t1.palette_off)
        cell = L.build_cell([(16, 16, [(0, 0, 0, 0, [solid_block(3)])]),
                             (16, 16, [(0, 0, 0, 0, [solid_block(3)])])], self.ln)
        a, b = L.parse_cell(cell)
        self.assertEqual(a.rects[0][4], b.rects[0][4])

    def test_refusals(self):
        bad = bytearray(self.cell)
        struct.pack_into('<H', bad, 0x40 + 8, 0x104)           # flags without 0x100
        with self.assertRaises(L.FormatError):
            L.parse_cell(bytes(bad))
        bad = bytearray(self.cell)
        struct.pack_into('<I', bad, 0x40 + 0x1c, 1)             # run-time field set
        with self.assertRaises(L.FormatError):
            L.parse_cell(bytes(bad))
        bad = bytearray(self.cell)
        struct.pack_into('<I', bad, 0x40 + 0x10, len(bad))      # payload offset outside
        with self.assertRaises(L.FormatError):
            L.parse_cell(bytes(bad))
        bad = bytearray(self.cell)
        struct.pack_into('<I', bad, 0x40 + 0xc, (1 << 23) | L.u32(bad, 0x40 + 0xc))
        with self.assertRaises(L.FormatError):
            L.parse_cell(bytes(bad))
        t0 = self.texs[0]
        bad = bytearray(self.cell)
        struct.pack_into('<bbbb', bad, t0.payload_off + 4, 0, 0, 3, 1)    # x1 = 3 is beyond 40 texels
        with self.assertRaises(L.FormatError):
            L.parse_cell(bytes(bad))
        with self.assertRaises(L.FormatError):
            L.parse_cell(self.cell[:0x40])

    def test_truncated_prefixes_are_refused_or_identical(self):
        full = L.parse_cell(self.cell)
        for cut in range(0, len(self.cell), 97):
            try:
                texs = L.parse_cell(self.cell[:cut])
                for t in texs:
                    L.decode_texture(self.cell[:cut], t)
            except L.FormatError:
                continue
            self.fail('prefix of %d bytes accepted' % cut)
        self.assertEqual(len(full), 2)


class TestDirectory(unittest.TestCase):
    def test_directory_roundtrip_and_cell_table(self):
        c1 = L.build_cell([(16, 16, [(0, 0, 0, 0, [solid_block(1)])])], lengths_all_literals())
        c2 = L.build_cell([], lengths_all_literals())
        d = L.build_directory([(5049, c1), (5151, c2)])
        recs = L.parse_directory(d)
        self.assertEqual([r[0] for r in recs], [5049, 5151])
        self.assertEqual(recs[0][1] % 2048, 0)
        self.assertEqual(d[recs[0][1]:recs[0][1] + len(c1)], c1)
        table = L.cell_table(recs, 4949, 5151)
        self.assertEqual(len(table), 203)
        self.assertEqual(table[0], (0, 0x40))
        self.assertEqual(table[100], (recs[0][1], len(c1)))
        self.assertEqual(table[202], (recs[1][1], len(c2)))
        with self.assertRaises(L.FormatError):
            L.cell_table(recs, 5100, 5151)

    def test_no_directory_and_bad_directory(self):
        self.assertEqual(L.parse_directory(struct.pack('<Ii', 0, 0) + bytes(16)), [])
        with self.assertRaises(L.FormatError):
            L.parse_directory(struct.pack('<I', 0) + struct.pack('<iII', 7, 0, 0) * 2000)
        with self.assertRaises(L.FormatError):
            L.parse_directory(struct.pack('<I', 0) + struct.pack('<iII', 7, 4096, 4096) + struct.pack('<iII', -1, 0, 0))

    def test_cell_ids_and_neighbours(self):
        self.assertEqual(L.cell_id_of(0.0, 0.0), 5050)
        self.assertEqual(L.cell_id_of(-1.0, 0.0), 5049)
        self.assertEqual(L.cell_id_of(720.0, -720.0), 4951)
        self.assertEqual(L.cells_around(5050), [4951, 4950, 4949, 5051, 5050, 5049, 5151, 5150, 5149])

    def test_relocate_offset(self):
        bmap = [3, 7] + [0xff] * 126
        self.assertEqual(L.relocate_offset(0x10, bmap, 0x1000000), 0x1000000 + (3 << 17) + 0x10)
        self.assertEqual(L.relocate_offset(0x20010, bmap, 0), (7 << 17) + 0x10)
        identity = list(range(256))
        self.assertEqual(L.relocate_offset(0x12345, identity, 0x500), 0x500 + 0x12345)
        with self.assertRaises(L.FormatError):
            L.relocate_offset(0x40000, bmap, 0)


if __name__ == '__main__':
    unittest.main()
