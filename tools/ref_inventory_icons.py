"""SLUS-20973 v2.00 picture-cache payload reference; no embedded game data.

Authored from picCache_serviceRequests (0x1003cc), sprite emission (0x17ab50),
and the private disc audit described in docs/formats/inventory-icons.md.
This is a bounded decoder for the observed PICCACHE profile, not all TEX files.
RGBA retains GS alpha (128 = opaque); display conversion is explicit.
"""
from collections import namedtuple
import struct


Picture = namedtuple('Picture', 'width height flags qwc packet_offset rgba')


def packet_span(data):
    """Serialized offset is relative to THIS sector payload (0x1004f0..100500)."""
    if len(data) < 0x40:
        raise ValueError('short picture header')
    qwc = struct.unpack_from('<H', data, 6)[0]
    offset = struct.unpack_from('<I', data, 0x10)[0]
    if not qwc or offset < 0x40 or offset % 16 or offset + qwc * 16 > len(data):
        raise ValueError('invalid upload span')
    return offset, qwc


def dma_chunks(data):
    """Ordered (tag_word, bytes) before runtime addresses are assigned.

    NEXT=2 and RET=6, not END=7. Maximum payload is 79 qwords per 0x500 block.
    Evidence: 0x100504..100510, 0x100624..10064c.
    """
    offset, qwc = packet_span(data)
    result = []
    while qwc:
        count = min(qwc, 79)
        qwc -= count
        result.append(((0x20000000 if qwc else 0x60000000) | count,
                       bytes(data[offset:offset + 16 * count])))
        offset += 16 * count
    return result


def transfers(data):
    """Read the observed packed A+D / IMAGE GIF profile, rejecting other layouts."""
    offset, qwc = packet_span(data)
    end = offset + qwc * 16
    state = {}
    result = []
    buffer = -1
    while offset < end:
        low, regs = struct.unpack_from('<QQ', data, offset)
        offset += 16
        count, mode, nr = low & 0x7fff, (low >> 58) & 3, (low >> 60) & 15 or 16
        if mode == 0:
            if nr != 1 or regs != 14 or offset + count * 16 > end:
                raise ValueError('unsupported/truncated A+D tag')
            for _ in range(count):
                value, reg = struct.unpack_from('<QQ', data, offset)
                offset += 16
                if reg == 0x50:
                    buffer += 1
                    state['dbw'] = (value >> 48) & 63
                    state['psm'] = (value >> 56) & 63
                elif reg == 0x51:
                    state['x'], state['y'] = (value >> 32) & 2047, (value >> 48) & 2047
                elif reg == 0x52:
                    state['w'], state['h'] = value & 4095, (value >> 32) & 4095
                elif reg == 0x53:
                    if value != 0:
                        raise ValueError('not a host-to-local transfer')
                    state['host'] = True
                elif reg != 0x62:
                    raise ValueError('unsupported GS register')
        elif mode == 2:
            if not all(k in state for k in ('dbw', 'psm', 'x', 'y', 'w', 'h', 'host')):
                raise ValueError('incomplete transfer state')
            size = state['w'] * state['h'] * 4
            if (buffer < 0 or state['psm'] != 0 or not size or size != count * 16
                    or offset + size > end):
                raise ValueError('unsupported/truncated image transfer')
            result.append(dict(state, buffer=buffer, data=bytes(data[offset:offset+size])))
            offset += size
        else:
            raise ValueError('unsupported GIF mode')
    return result


_BLOCK = ((0, 1, 4, 5, 16, 17, 20, 21), (2, 3, 6, 7, 18, 19, 22, 23),
          (8, 9, 12, 13, 24, 25, 28, 29), (10, 11, 14, 15, 26, 27, 30, 31))
_WORD = (0, 1, 4, 5, 8, 9, 12, 13)


def gs32_word(x, y, dbw=1):
    """PSMCT32 word address relative to transfer base; 64 x 32 per page."""
    return ((y // 32 * dbw + x // 64) * 2048
            + _BLOCK[(y >> 3) & 3][(x >> 3) & 7] * 64
            + ((y & 7) >> 1) * 16 + (y & 1) * 2 + _WORD[x & 7])


def gs8_byte(x, y, tbw=2):
    """PSMT8 byte address relative to texture base; 128 x 64 per page."""
    yy = y & 15
    xi = (x & 7) ^ (4 if ((yy + 2) >> 2) & 1 else 0)
    word = (yy >> 2) * 16 + (yy & 1) * 2 + _WORD[xi]
    return ((y // 64 * (tbw // 2) + x // 128) * 8192
            + _BLOCK[(y >> 4) & 3][(x >> 4) & 7] * 256
            + word * 4 + ((yy & 3) >> 1) + (((x >> 3) & 1) << 1))


def decode(data):
    """Decode the audited cache profile; woven rows split at logical height/2.

    Extra transfer rows and power-of-two texture padding are not visible pixels.
    Unsupported profiles fail instead of silently returning guessed art.
    """
    offset, qwc = packet_span(data)
    w, h, _, _, flags, marker, tex0 = struct.unpack_from('<6HI', data)
    tbw, psm = tex0 & 63, (tex0 >> 6) & 63
    nw, nh = 1 << ((tex0 >> 12) & 15), 1 << ((tex0 >> 16) & 15)
    if (flags not in (0x44, 0x844, 0x1044, 0x1844) or marker or psm != 19
            or tbw != 2 or not 0 < w <= min(nw, 128) or not 0 < h <= min(nh, 256)
            or h % 2):
        raise ValueError('not the observed inventory-icon profile')
    parts = transfers(data)
    if len(parts) != 2:
        raise ValueError('expected one palette and one image')
    pal, img = parts
    if (pal['buffer'],pal['dbw'],pal['x'],pal['y'],pal['w'],pal['h']) != (0,1,0,0,16,16):
        raise ValueError('unsupported palette')
    if img['buffer'] != 1 or img['dbw'] != 1 or img['x'] or img['y'] or img['w'] > 64 or img['h'] > 128:
        raise ValueError('unsupported image upload')
    memory = bytearray(32768)
    present = bytearray(8192)
    for y in range(img['h']):
        for x in range(img['w']):
            word = gs32_word(x, y)
            source = (y * img['w'] + x) * 4
            memory[word * 4:word * 4 + 4] = img['data'][source:source + 4]
            present[word] = 1
    out = bytearray()
    for y in range(h):
        stored_y = y // 2 + (h // 2 if y & 1 else 0)
        for x in range(w):
            at = gs8_byte(x, stored_y)
            if not present[at // 4]:
                raise ValueError('logical picture reads unsupplied GS memory')
            index = memory[at]
            clut = (index & ~0x18) | ((index & 8) << 1) | ((index & 16) >> 1)
            out.extend(pal['data'][4 * clut:4 * clut + 4])
    return Picture(w, h, flags, qwc, offset, bytes(out))


def display_rgba(rgba):
    """Optional conventional-alpha presentation; RGB and hidden RGB are preserved."""
    if len(rgba) % 4:
        raise ValueError('not RGBA')
    out = bytearray(rgba)
    for i in range(3, len(out), 4):
        out[i] = min(255, out[i] * 2)
    return bytes(out)
