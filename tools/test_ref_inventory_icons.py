"""Synthetic GIF uploads only: no executable, extracted pixels or disc needed."""
import struct
import unittest

import ref_inventory_icons as R


def upload(width, height, pixels):
    registers = ((1 << 48, 0x50), (0, 0x51),
                 (width | height << 32, 0x52), (0, 0x53))
    return (struct.pack('<QQ', 4 | 1 << 60, 14)
            + b''.join(struct.pack('<QQ', *r) for r in registers)
            + struct.pack('<QQ', len(pixels) // 16 | 2 << 58, 0) + pixels)


def fixture(flags=0x44):
    palette = b''.join(bytes((i, i ^ 0x55, 19, i % 129)) for i in range(256))
    pixels = bytearray(8192)
    # Independently selected PSMCT32 source bytes -> GS byte addresses 0,2,33,41.
    pixels[0], pixels[2], pixels[17], pixels[273] = 8, 17, 16, 24
    packet = upload(16, 16, palette) + upload(64, 32, pixels)
    header = bytearray(128)
    struct.pack_into('<6HII', header, 0, 9, 6, 0, len(packet)//16,
                     flags, 0, 2 | 19 << 6 | 7 << 12 | 6 << 16, 128)
    return header + packet


class InventoryIcons(unittest.TestCase):
    def test_logical_crop_field_weave_and_clut(self):
        picture = R.decode(fixture())
        self.assertEqual((picture.width, picture.height, len(picture.rgba)), (9, 6, 216))
        # Output rows read stored rows 0,3,1,4,2,5. Index bits 3/4 swap for CLUT.
        self.assertEqual([picture.rgba[y*9*4] for y in range(6)], [16, 24, 0, 0, 8, 0])
        self.assertEqual(picture.rgba[8*4:9*4], bytes((9, 9 ^ 0x55, 19, 9)))

    def test_flag_variants_do_not_change_pixels(self):
        expected = R.decode(fixture()).rgba
        for flags in (0x844, 0x1044, 0x1844):
            self.assertEqual(R.decode(fixture(flags)).rgba, expected)

    def test_pages_are_bijections_and_have_fixed_landmarks(self):
        self.assertEqual({R.gs32_word(x,y) for y in range(32) for x in range(64)}, set(range(2048)))
        self.assertEqual({R.gs8_byte(x,y) for y in range(64) for x in range(128)}, set(range(8192)))
        self.assertEqual([R.gs8_byte(0,y) for y in range(6)], [0,8,33,41,96,104])
        self.assertEqual(R.gs32_word(0,32), 2048)
        self.assertEqual(R.gs8_byte(0,64), 8192)

    def test_dma_chunks_preserve_bytes_and_end_in_ret(self):
        data = fixture()
        chunks = R.dma_chunks(data)
        offset,qwc = R.packet_span(data)
        self.assertEqual(b''.join(p for _,p in chunks), data[offset:offset+qwc*16])
        self.assertEqual(chunks[0][0], 0x2000004f)
        self.assertEqual(chunks[-1][0] >> 28, 6)
        for tag,payload in chunks:
            self.assertEqual((tag & 0xffff)*16, len(payload))
            self.assertLessEqual(len(payload), 1264)

    def test_alpha_is_explicit_and_keeps_hidden_rgb(self):
        data = bytes((10,20,30,0, 1,2,3,64, 4,5,6,128, 7,8,9,255))
        self.assertEqual(R.display_rgba(data), bytes((10,20,30,0,1,2,3,128,4,5,6,255,7,8,9,255)))
        with self.assertRaises(ValueError): R.display_rgba(b'abc')

    def test_rejects_bad_header_and_upload(self):
        original = fixture()
        variants = [original[:30], original[:-1]]
        for offset,fmt,value in [(0,'H',0),(2,'H',5),(8,'H',1),(10,'H',0xa7fb),
                                 (16,'I',129),(16,'I',0xfffffff0)]:
            data = bytearray(original); struct.pack_into('<'+fmt,data,offset,value); variants.append(data)
        # Replace first transfer's BITBLTBUF with an unsupported PSM.
        data=bytearray(original); struct.pack_into('<Q',data,144,1<<48 | 19<<56); variants.append(data)
        for data in variants:
            with self.subTest(size=len(data)), self.assertRaises(ValueError): R.decode(data)

    def test_rejects_unsupplied_logical_pixels(self):
        data=fixture(); struct.pack_into('<H',data,2,128)
        struct.pack_into('<I',data,12,2 | 19<<6 | 7<<12 | 7<<16)
        with self.assertRaisesRegex(ValueError,'unsupplied'): R.decode(data)


class BottomPad(unittest.TestCase):
    def test_only_0x0800_moves_the_picture_down(self):
        self.assertEqual(R.bottom_anchor_y(100, 30, 0x44), 70)
        self.assertEqual(R.bottom_anchor_y(100, 30, 0x844), 71)
        self.assertEqual(R.bottom_anchor_y(100, 30, 0x1044), 70)

if __name__ == '__main__': unittest.main()
