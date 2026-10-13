#!/usr/bin/env python3
"""pngtest.py - PNG files of every kind, made here, for comparing render/png_read.h with QImage.

  python3 tools/recomp/app/win/pngtest.py OUT_FOLDER       (default local/recomp-out/win/pngtest)
  local/recomp-out/win/standin/pngcheck OUT_FOLDER          (build_win.py --pngcheck)

The art pack holds one kind of file (8-bit RGBA, not interlaced).  The reader reads all of
PNG, so the rest is checked with pictures made here: every colour type and bit depth, with
and without Adam7 interlacing, with a transparent colour (tRNS), palettes of several sizes
(one too short for its pixels), every row filter, and compressed streams of every block
type (stored, fixed codes, dynamic codes, long matches) cut into IDAT chunks in several
ways.  A second set is damaged on purpose (cut short, wrong CRC, wrong filter byte, rows
missing, bytes after the last row, wrong Adler-32): there the two readers must agree on
whether the file is a picture at all.

Nothing here comes from the game; the pixels are a fixed pseudo-random pattern.
"""
import os
import random
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
ADAM7 = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def chunk(kind, body, bad_crc=False):
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    if bad_crc:
        crc ^= 0x5A5A5A5A
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)


def filter_row(kind, row, up, bpp):
    out = bytearray(len(row))
    for k in range(len(row)):
        a = row[k - bpp] if k >= bpp else 0
        b = up[k] if up else 0
        c = up[k - bpp] if (up and k >= bpp) else 0
        pred = (0, a, b, (a + b) >> 1, paeth(a, b, c))[kind]
        out[k] = (row[k] - pred) & 255
    return bytes(out)


def pack_rows(samples, width, height, channels, depth, rng, filters):
    """samples: [y][x][channel] -> the filtered rows of one image or pass."""
    out = bytearray()
    bits = channels * depth
    bpp = max(1, bits // 8)
    up = None
    for y in range(height):
        if depth == 16:
            row = b''.join(struct.pack('>H', v) for x in range(width) for v in samples[y][x])
        elif depth == 8:
            row = bytes(v for x in range(width) for v in samples[y][x])
        else:
            row = bytearray((width * depth + 7) // 8)
            for x in range(width):
                bit = x * depth
                row[bit >> 3] |= samples[y][x][0] << (8 - depth - (bit & 7))
            row = bytes(row)
        kind = filters if isinstance(filters, int) else rng.choice(filters)
        out.append(kind)
        out += filter_row(kind, row, up, bpp)
        up = row
    return bytes(out)


def make(colour, depth, width, height, interlace, rng, *, palette=None, trns=None, filters=(0, 1, 2, 3, 4), level=6, strategy=zlib.Z_DEFAULT_STRATEGY,
         split=None, smooth=False, index_limit=None):
    channels = CHANNELS[colour]
    top = (1 << depth) - 1
    limit = index_limit if index_limit is not None else top
    samples = []
    for y in range(height):
        row = []
        for x in range(width):
            if smooth:      # long runs and far matches for the compressor
                row.append([(((x // 7) * 13 + (y // 5) * 29 + c * 71) * (257 if depth == 16 else 1)) & top if colour != 3 else ((x // 3 + y // 2) % (limit + 1))
                            for c in range(channels)])
            else:
                row.append([rng.randrange(min(limit, top) + 1) if (colour == 3 or channels == 1) else rng.choice((0, top, rng.randrange(top + 1))) for _ in range(channels)])
        samples.append(row)
    if interlace:
        raw = b''
        for x0, y0, dx, dy in ADAM7:
            pw, ph = (width - x0 + dx - 1) // dx if width > x0 else 0, (height - y0 + dy - 1) // dy if height > y0 else 0
            if pw and ph:
                sub = [[samples[y0 + y * dy][x0 + x * dx] for x in range(pw)] for y in range(ph)]
                raw += pack_rows(sub, pw, ph, channels, depth, rng, filters)
    else:
        raw = pack_rows(samples, width, height, channels, depth, rng, filters)
    compressor = zlib.compressobj(level, zlib.DEFLATED, 15, 9, strategy)
    packed = compressor.compress(raw) + compressor.flush()
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, colour, 0, 0, 1 if interlace else 0))
    data += chunk(b'gAMA', struct.pack('>I', 45455))     # a file gamma: neither reader applies it
    if palette is not None:
        data += chunk(b'PLTE', palette)
    if trns is not None:
        data += chunk(b'tRNS', trns)
    pieces = []
    if split == 'bytes':
        pieces = [packed[:1], b'', packed[1:2], packed[2:]]
    elif split:
        pieces = [packed[k:k + split] for k in range(0, len(packed), split)]
    else:
        pieces = [packed]
    for piece in pieces:
        data += chunk(b'IDAT', piece)
    data += chunk(b'tEXt', b'Comment\x00made by pngtest.py') + chunk(b'IEND', b'')
    return data, raw, packed


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'local', 'recomp-out', 'win', 'pngtest')
    good, bad = os.path.join(out, 'good'), os.path.join(out, 'damaged')
    os.makedirs(good, exist_ok=True)
    os.makedirs(bad, exist_ok=True)
    rng = random.Random(20261012)
    count = 0

    def write(folder, name, data):
        nonlocal count
        with open(os.path.join(folder, name + '.png'), 'wb') as sink:
            sink.write(data)
        count += 1

    sizes = [(1, 1), (2, 3), (5, 1), (1, 9), (8, 8), (9, 17), (33, 20), (70, 41)]
    kinds = [(0, d) for d in (1, 2, 4, 8, 16)] + [(2, 8), (2, 16)] + [(3, d) for d in (1, 2, 4, 8)] + [(4, 8), (4, 16), (6, 8), (6, 16)]
    for colour, depth in kinds:
        for interlace in (0, 1):
            for width, height in sizes:
                variants = [dict()]
                top = (1 << depth) - 1
                if colour == 0:
                    variants += [dict(trns=struct.pack('>H', v)) for v in (0, top, top // 2)]
                if colour == 2:
                    variants += [dict(trns=struct.pack('>HHH', 0, 0, 0)), dict(trns=struct.pack('>HHH', top, top, top)), dict(trns=struct.pack('>HHH', top, 0, top))]
                if colour == 3:
                    full = bytes(rng.randrange(256) for _ in range(3 * (top + 1)))
                    variants = [dict(palette=full), dict(palette=full, trns=bytes(rng.randrange(256) for _ in range(top + 1))),
                                dict(palette=full, trns=bytes([0, 128]))]
                    if depth > 1:
                        variants += [dict(palette=full[:3 * (top // 2 + 1)]),                      # shorter than the pixels need
                                     dict(palette=full[:3 * 3], trns=bytes([7]), index_limit=2),    # short, and enough
                                     dict(palette=full[:3 * 2], trns=bytes([77, 200]))]             # too short, its first entry half transparent
                    else:
                        variants += [dict(palette=full[:3])]
                for n, extra in enumerate(variants):
                    data, _, _ = make(colour, depth, width, height, interlace, rng, **extra)
                    write(good, 'c%d-d%02d-i%d-%dx%d-v%d' % (colour, depth, interlace, width, height, n), data)
    # the compressed stream: every block type, long matches, chunk splits, single filters
    for n, (level, strategy, split, smooth, size) in enumerate([
            (0, zlib.Z_DEFAULT_STRATEGY, None, False, (300, 200)),      # stored blocks, several
            (0, zlib.Z_DEFAULT_STRATEGY, 1000, False, (64, 64)),
            (1, zlib.Z_FIXED, None, False, (120, 90)),                   # fixed codes
            (9, zlib.Z_FIXED, 7, True, (200, 150)),
            (9, zlib.Z_DEFAULT_STRATEGY, None, True, (400, 300)),        # dynamic codes, far matches
            (9, zlib.Z_DEFAULT_STRATEGY, 8192, True, (512, 300)),
            (6, zlib.Z_HUFFMAN_ONLY, None, False, (257, 129)),
            (6, zlib.Z_RLE, 'bytes', True, (513, 100)),
            (6, zlib.Z_FILTERED, 3, False, (31, 31)),
            (9, zlib.Z_DEFAULT_STRATEGY, 65536, False, (400, 400)),      # random pixels: long codes
    ]):
        for colour, depth in ((6, 8), (2, 8), (3, 8), (0, 16), (6, 16)):
            extra = dict(palette=bytes(rng.randrange(256) for _ in range(768))) if colour == 3 else {}
            data, _, _ = make(colour, depth, size[0], size[1], n % 2, rng, level=level, strategy=strategy, split=split, smooth=smooth, **extra)
            write(good, 'z%02d-c%d-d%02d' % (n, colour, depth), data)
    for kind in range(5):
        for colour, depth in ((6, 8), (2, 16), (0, 2), (4, 8)):
            data, _, _ = make(colour, depth, 77, 53, 0, rng, filters=kind)
            write(good, 'f%d-c%d-d%02d' % (kind, colour, depth), data)

    # damaged on purpose
    base, raw, packed = make(6, 8, 64, 48, 0, rng)
    head = base[:8 + 25]
    ihdr = struct.pack('>IIBBBBB', 64, 48, 8, 6, 0, 0, 0)

    def rebuild(stream, tail=chunk(b'IEND', b''), **kw):
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', stream, **kw) + tail

    write(bad, 'whole', rebuild(packed))
    write(bad, 'cut-in-idat', base[:len(base) // 2])
    write(bad, 'cut-before-iend', base[:-12])
    write(bad, 'cut-in-iend', base[:-3])
    write(bad, 'no-idat', head + chunk(b'IEND', b''))
    write(bad, 'crc-idat', rebuild(packed, bad_crc=True))
    write(bad, 'crc-iend', rebuild(packed, tail=chunk(b'IEND', b'', bad_crc=True)))
    write(bad, 'crc-ihdr', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr, bad_crc=True) + chunk(b'IDAT', packed) + chunk(b'IEND', b''))
    write(bad, 'crc-text', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'tEXt', b'a\x00b', bad_crc=True) + chunk(b'IDAT', packed) + chunk(b'IEND', b''))
    write(bad, 'adler', rebuild(packed[:-4] + bytes(4)))
    write(bad, 'adler-missing', rebuild(packed[:-4]))
    write(bad, 'adler-half', rebuild(packed[:-2]))
    write(bad, 'iend-without-crc', base[:-4])
    write(bad, 'iend-with-body', rebuild(packed, tail=chunk(b'IEND', b'body')))
    write(bad, 'idat-after-iend', rebuild(packed[:len(packed) // 2]) + chunk(b'IDAT', packed[len(packed) // 2:]))
    write(bad, 'rows-missing', rebuild(zlib.compress(raw[:len(raw) // 2])))
    write(bad, 'rows-extra', rebuild(zlib.compress(raw + bytes(1000))))
    write(bad, 'bytes-after-stream', rebuild(packed + b'more bytes'))
    wrong = bytearray(raw)
    wrong[(64 * 4 + 1) * 10] = 9
    write(bad, 'filter-byte', rebuild(zlib.compress(bytes(wrong))))
    write(bad, 'stream-garbage', rebuild(packed[:40] + bytes(rng.randrange(256) for _ in range(len(packed) - 40))))
    write(bad, 'not-zlib', rebuild(raw[:500]))
    write(bad, 'signature', b'\x89PNG\r\n\x1a\r' + base[8:])
    write(bad, 'empty', b'')
    write(bad, 'zero-width', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 0, 48, 8, 6, 0, 0, 0)) + chunk(b'IDAT', packed) + chunk(b'IEND', b''))
    write(bad, 'depth-3', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 48, 3, 0, 0, 0, 0)) + chunk(b'IDAT', packed) + chunk(b'IEND', b''))
    write(bad, 'palette-missing', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 48, 8, 3, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes(65 * 48))) + chunk(b'IEND', b''))
    write(bad, 'unknown-critical', b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'ABCD', b'x') + chunk(b'IDAT', packed) + chunk(b'IEND', b''))
    print('wrote %d files into %s' % (count, out))


if __name__ == '__main__':
    main()
