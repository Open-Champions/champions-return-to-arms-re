"""Embedded font-page textures for SLUS-20973 v2.00.

A font page is the TEX suffix of an FNT. Its GIF packet starts at the u32 at
+0x10, which is not 0x80. The pixels are the same PSMT8 upload as a lump
texture. See docs/formats/ui-fonts.md.

parse_texture and parse_font are unchanged. This module only adds a reader
for the non-0x80 page.
"""
import struct
from collections import namedtuple

from model_info import FormatError, Texture, decode_texture, walk_upload, weave_fields


# Packet-relative. gfx_dmaHandler 0x16c048 stores the GS block as the
# BITBLTBUF destination base (DBP, bits 32-47) at the first of these, and
# block+4 at the second when the matching flag is set. The +4 is the
# 1024-byte palette, four blocks of 256.
PALETTE_DBP = 0x14
IMAGE_DBP_8 = 0x474
IMAGE_DBP_4 = 0xb4

FontPage = namedtuple(
    'FontPage', 'w h blocks qwc flags tex0 data_off tbw tw th transfers')


def dma_image_dbp(flags):
    """Second DBP halfword, or None when the handler writes only +0x14.

    Flag 0x0004 is tested first (0x16c058), so an 8-bit page does not also
    take the 4-bit store.
    """
    if flags & 0x0004:
        return IMAGE_DBP_8
    if flags & 0x2000:
        return IMAGE_DBP_4
    return None


def apply_tex_relocate_prefix(base, data):
    """The prefix of tex_relocate 0x179e10 when flags lack 0x0001 and 0x0100.

    Adds base to the packet offset, stores 0xa7fb at +0x0a and -1 at +0x1c,
    and leaves the qword count alone. A later call sees +0x1c and changes
    nothing. The block-table walk is not this function.
    """
    if len(data) < 0x20:
        raise ValueError('short texture header')
    flags = struct.unpack_from('<H', data, 8)[0]
    if flags & 0x0101:
        raise ValueError('flags 0x%04x take the block-table walk' % flags)
    out = bytearray(data)
    if struct.unpack_from('<I', out, 0x1c)[0]:
        return bytes(out)
    offset = struct.unpack_from('<I', out, 0x10)[0]
    struct.pack_into('<H', out, 0x0a, 0xa7fb)
    struct.pack_into('<I', out, 0x1c, 0xffffffff)
    struct.pack_into('<I', out, 0x10, (base + offset) & 0xffffffff)
    return bytes(out)


def _reject(msg):
    raise ValueError(msg)


def parse_font_page(data):
    """Unrelocated embedded font page. Raises ValueError on a lump-shaped
    page whose packet is not the font layout the DMA handler patches."""
    if len(data) < 0x40:
        _reject('short font page')
    w, h, blocks, qwc, flags, magic = struct.unpack_from('<6H', data, 0)
    tex0, data_off = struct.unpack_from('<II', data, 0x0c)
    if magic:
        _reject('font page is already relocated')
    if data_off < 0x40:
        _reject('packet offset 0x%x overlaps the runtime header' % data_off)
    if data_off > len(data) or any(data[0x14:data_off]):
        _reject('gap before the packet is not zero')
    if flags & ~0x0044 or not flags & 0x0004:
        _reject('flags 0x%04x are not an 8-bit font page' % flags)
    if not qwc or data_off + qwc * 16 != len(data):
        _reject('packet does not end at the end of the page')
    if data_off + IMAGE_DBP_8 + 8 > len(data):
        _reject('packet is shorter than the image BITBLTBUF')
    tbw, psm = tex0 & 0x3f, (tex0 >> 6) & 0x3f
    tw, th = 1 << ((tex0 >> 12) & 15), 1 << ((tex0 >> 16) & 15)
    if tex0 >> 23 or psm != 0x13 or not tbw or tbw & 1:
        _reject('TEX0 0x%x is not a PSMT8 page' % tex0)
    if not (0 < w <= tw and 0 < h <= th and tw <= 1024 and th <= 1024):
        _reject('size %dx%d does not fit the surface' % (w, h))
    if (struct.unpack_from('<Q', data, data_off + 0x18)[0] & 0xff) != 0x50:
        _reject('palette BITBLTBUF is not at packet+0x10')
    if (struct.unpack_from('<Q', data, data_off + IMAGE_DBP_8 + 4)[0] & 0xff) != 0x50:
        _reject('image BITBLTBUF is not at packet+0x470')
    try:
        transfers = walk_upload(data, data_off, data_off + qwc * 16)
    except FormatError as exc:
        _reject(str(exc))
    pal = [r for r in transfers if r['buf'] == 0]
    img = [r for r in transfers if r['buf'] == 1]
    if not (len(pal) == 1 and len(img) == 1 and len(transfers) == 2):
        _reject('font page is not one palette and one image')
    if (pal[0]['rrw'], pal[0]['rrh'], pal[0]['dpsm']) != (16, 16, 0):
        _reject('palette is not 16x16 PSMCT32')
    image = img[0]
    if image['dpsm'] != 0 or (image['dsax'], image['dsay']) != (0, 0):
        _reject('image is not one PSMCT32 rectangle at the origin')
    if image['dbw'] * 2 != tbw:
        _reject('upload width does not match TBW')
    return FontPage(w, h, blocks, qwc, flags, tex0, data_off, tbw, tw, th,
                    (pal[0], image))


def decode_font_page(data, weave=False):
    """Return (width, height, rgba). Alpha follows decode_texture (0x80 is 255).

    weave interleaves the two fields. Glyph rectangles in ui-fonts.md are in
    that woven space. The default is stored order.
    """
    page = data if isinstance(data, FontPage) else parse_font_page(data)
    tex = Texture()
    tex.kind = '8-bit'
    tex.w, tex.h, tex.tbw = page.w, page.h, page.tbw
    tex.transfers = page.transfers
    w, h, px = decode_texture(tex)
    if weave:
        return weave_fields(w, h, px)
    return w, h, px
