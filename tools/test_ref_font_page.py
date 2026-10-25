"""Synthetic font pages. No original game bytes."""
import struct
import unittest

import model_info as M
import ref_font_page as F


def _tag(nloop, flg):
    lo = (nloop & 0x7fff) | (flg << 58) | (1 << 60)
    return struct.pack('<QQ', lo, 0xe)


def _reg(value, register):
    return struct.pack('<QQ', value, register)


def _bitblt(dbw, dpsm=0):
    return (dbw << 48) | (dpsm << 56)


def build_page(data_off, pixels):
    """PSMT8 page. pixels is {(x, y): index}. Surface 128x4, used 16x4."""
    dbw, tbw = 1, 2
    words = {}
    for (x, y), index in pixels.items():
        addr = M.gs_addr8(x, y, dbw)
        word = bytearray(words.get(addr >> 2, b'\x00\x00\x00\x00'))
        word[addr & 3] = index
        words[addr >> 2] = bytes(word)
    width, height = 64, 32
    image = bytearray(width * height * 4)
    for yy in range(height):
        for xx in range(width):
            addr = M.gs_addr32(xx, yy, dbw)
            image[(yy * width + xx) * 4:(yy * width + xx) * 4 + 4] = words.get(
                addr >> 2, b'\x00\x00\x00\x00')
    palette = bytearray(1024)
    # Stored alpha is the GS 0x80 scale. Slot follows the CSM1 order.
    stored = {0: (0, 0, 0, 0), 1: (1, 2, 3, 0x80), 8: (9, 8, 7, 0x40)}
    for index, colour in stored.items():
        palette[M.clut_order(index) * 4:M.clut_order(index) * 4 + 4] = bytes(colour)
    packet = bytearray()
    packet += _tag(4, 0)
    packet += _reg(_bitblt(1), 0x50)
    packet += _reg(0, 0x51)
    packet += _reg(16 | (16 << 32), 0x52)
    packet += _reg(0, 0x53)
    packet += _tag(64, 2)
    packet += palette
    packet += _tag(5, 0)
    packet += _reg(_bitblt(dbw), 0x50)
    packet += _reg(0, 0x51)
    packet += _reg(width | (height << 32), 0x52)
    packet += _reg(0, 0x62)
    packet += _reg(0, 0x53)
    packet += _tag(len(image) // 16, 2)
    packet += image
    tex0 = tbw | (0x13 << 6) | (7 << 12) | (2 << 16) | (1 << 20)
    page = bytearray(data_off) + packet
    struct.pack_into('<6HII', page, 0, 16, 4, 8, len(packet) // 16, 0x0044, 0, tex0, data_off)
    return bytes(page)


PIXELS = {(0, 0): 1, (3, 1): 8, (8, 2): 1}


class FontPageTests(unittest.TestCase):
    def test_offsets_match_the_lump_decoder(self):
        standard = build_page(0x80, PIXELS)
        parsed = M.parse_texture(standard)
        want = M.decode_texture(parsed)
        for offset in (0x80, 0x44, 0xb4):
            page = build_page(offset, PIXELS)
            self.assertEqual(F.decode_font_page(page), want)
            info = F.parse_font_page(page)
            self.assertEqual(info.data_off, offset)
            self.assertEqual((info.w, info.h, info.tbw), (16, 4, 2))
        # Independent of decode_texture's palette walk: 0x40 scales to 127.
        w, h, px = F.decode_font_page(build_page(0x44, PIXELS))
        self.assertEqual(px[1 * w + 3], (9, 8, 7, 64 * 255 // 128))
        self.assertEqual(px[0], (1, 2, 3, 255))
        self.assertEqual((w, h), (16, 4))

    def test_weave_matches_the_field_interleave(self):
        page = build_page(0x44, PIXELS)
        stored = F.decode_font_page(page)
        woven = F.decode_font_page(page, weave=True)
        self.assertEqual(woven, M.weave_fields(*stored))
        self.assertNotEqual(woven[2], stored[2])

    def test_rejects_relocated_gap_and_short_packets(self):
        good = bytearray(build_page(0xb4, PIXELS))
        moved = bytearray(good)
        moved[0x0a] = 1
        short_off = bytearray(good)
        struct.pack_into('<I', short_off, 0x10, 0x20)
        gap = bytearray(good)
        gap[0x14] = 1
        trailing = good + b'\x00'
        truncated = good[:-16]
        struct.pack_into('<H', truncated, 6, struct.unpack_from('<H', truncated, 6)[0] - 1)
        flags = bytearray(good)
        struct.pack_into('<H', flags, 8, 0x0020)
        bad_reg = bytearray(good)
        bad_reg[0xb4 + 0x478] = 0
        for blob in (moved, short_off, gap, trailing, truncated, flags, bad_reg):
            with self.assertRaises(ValueError):
                F.parse_font_page(blob)

    def test_relocate_prefix_is_idempotent(self):
        raw = build_page(0x44, PIXELS)
        once = F.apply_tex_relocate_prefix(0x1000, raw)
        twice = F.apply_tex_relocate_prefix(0x1000, once)
        self.assertEqual(twice, once)
        self.assertEqual(struct.unpack_from('<H', once, 0x0a)[0], 0xa7fb)
        self.assertEqual(struct.unpack_from('<I', once, 0x1c)[0], 0xffffffff)
        self.assertEqual(struct.unpack_from('<I', once, 0x10)[0], 0x1044)
        self.assertEqual(struct.unpack_from('<H', once, 6)[0], struct.unpack_from('<H', raw, 6)[0])
        with self.assertRaises(ValueError):
            F.apply_tex_relocate_prefix(0x1000, flags_on(raw, 0x0100))

    def test_dma_sites(self):
        self.assertEqual(F.dma_image_dbp(0x0044), 0x474)
        self.assertEqual(F.dma_image_dbp(0x2000), 0xb4)
        self.assertEqual(F.dma_image_dbp(0x2004), 0x474)
        self.assertIsNone(F.dma_image_dbp(0x0020))


def flags_on(blob, flags):
    out = bytearray(blob)
    struct.pack_into('<H', out, 8, flags)
    return bytes(out)


if __name__ == '__main__':
    unittest.main()
