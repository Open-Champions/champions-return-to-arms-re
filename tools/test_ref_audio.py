"""Hand-built audio fixtures; no disc files, game bytes or captured sound."""

import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_audio as A  # noqa: E402


def block(filter_index=0, shift=12, flags=0, payload=None):
    return bytes([(filter_index << 4) | shift, flags]) + (payload or bytes(14))


def vat_record(name, offset, rate=24000, stereo=0, language=0, restart=0):
    raw_name = name.encode("ascii")
    return raw_name.ljust(0x40, b"\0") + struct.pack(
        "<IIHhI", offset, rate, stereo, language, restart)


class HeaderAndCodec(unittest.TestCase):
    def test_big_endian_vag_header_without_magic_requirement(self):
        header = bytearray(0x30)
        struct.pack_into(">III", header, 4, 4, 0, 0x20)
        struct.pack_into(">I", header, 0x10, 16000)
        header[0x20:0x24] = b"test"
        parsed = A.parse_vag_header(header)
        self.assertEqual((parsed.magic, parsed.version, parsed.data_size,
                          parsed.rate, parsed.name), (b"\0" * 4, 4, 0x20, 16000, b"test"))
        self.assertEqual(A.base_pitch(parsed.rate), 1365)

    def test_nibble_order_sign_and_end_marker(self):
        # 0x1f means -1 first, +1 second, at shift 12.
        data = block(flags=1, payload=b"\x1f" + bytes(13)) + block(flags=7)
        decoded = A.decode_adpcm(data)
        self.assertEqual(decoded.pcm[:4], (-1, 1, 0, 0))
        self.assertEqual(len(decoded.pcm), 28)
        self.assertIsNone(decoded.loop_start_sample)

    def test_filter_history_crosses_blocks_and_loop_markers(self):
        first = block(0, 12, 6, b"\x01" + bytes(13))
        second = block(1, 12, 3)
        decoded = A.decode_adpcm(first + second)
        self.assertEqual(decoded.pcm[:2], (1, 0))
        self.assertEqual(decoded.pcm[28], 0)
        self.assertEqual((decoded.loop_start_sample, decoded.loop_end_sample), (0, 56))

    def test_invalid_block_and_alignment(self):
        with self.assertRaises(ValueError):
            A.decode_adpcm(b"x")
        with self.assertRaises(ValueError):
            A.decode_adpcm(block(5))


class StreamAndPosition(unittest.TestCase):
    def test_vat_directory_uses_next_offset_and_terminal(self):
        directory = (vat_record("mx_test.vag", 0, stereo=1) +
                     vat_record("line.vag", 0x800, language=3) +
                     vat_record("", 0x1000, rate=0))
        entries = A.parse_vat_directory(directory, 0x1000)
        self.assertEqual([(e.name, e.offset, e.length, e.stereo, e.language)
                          for e in entries],
                         [("mx_test.vag", 0, 0x800, True, 0),
                          ("line.vag", 0x800, 0x800, False, 3)])
        with self.assertRaises(ValueError):
            A.parse_vat_directory(directory, 0x1800)

    def test_stereo_chunk_deinterleave_and_duration(self):
        data = b"L" * 0x400 + b"R" * 0x400 + b"l" * 0x400 + b"r" * 0x400
        self.assertEqual(A.split_stereo_chunks(data),
                         (b"L" * 0x400 + b"l" * 0x400,
                          b"R" * 0x400 + b"r" * 0x400))
        self.assertAlmostEqual(A.stream_duration(0x800, True),
                               64 * 28 / 24000)
        self.assertAlmostEqual(A.stream_duration(0x800, False),
                               128 * 28 / 24000)
        self.assertEqual(A.SPU_RATE * A.STREAM_PITCH / 4096, 23976.5625)

    def test_camera_pan_and_falloff(self):
        c, right = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)
        self.assertEqual(A.pan_atten(c, c, right), (1.0, 1.0))
        left, right_gain = A.pan_atten((600.0, 0.0, 0.0), c, right)
        self.assertAlmostEqual(left, 0.5 * (1 - 600 / 840))
        self.assertAlmostEqual(right_gain, 0.5 * (1 + 600 / 840))
        self.assertEqual(A.pan_atten((840.0, 0.0, 0.0), c, right), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
