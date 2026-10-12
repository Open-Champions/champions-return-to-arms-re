#!/usr/bin/env python3
"""Names and writes out the textures of the disc image without playing the game.

    tools/play-net/disctex.py DISC.iso OUT_DIR [--only TEXT] [--kinds model,other] [--list]
                              [--check DUMP_DIR] [--xxhash DIR]

The playable build knows a texture by a figure of the bytes the game sends for it and of
its palette (tools/play-net/README.md, "Texture dump and replacement"). The textures kept
in the disc's lumps (`.tex` and `.etex` entries of the `.LMP` files and of the lumps inside
the `.GOB` files: models, monsters, items, interface art, effects - 3,236 of them) are
stored as the very packets the game sends, so their names can be worked out from the file:
this tool does that and writes each picture to OUT_DIR exactly as `--rta-texture-dump`
would (`<texels>-<palette>-p<format>-<width>x<height>.png`, alpha as on the console), for
`upscale.py` to enlarge.

What it cannot do:

- **Level textures** (one per piece of ground and wall, in `<LEVEL>.TEX`): they are stored
  packed and the game unpacks them before sending. They are not named here; play the
  level with `--rta-texture-dump`.
- **How a picture is drawn** is not in its file. For model textures (header flag 0x0010)
  a `.json` file is written beside the picture that names the model drawer's state, so
  that `upscale.py` takes them for model textures; it is marked `"source": "disc"`, and
  because nobody has seen the picture drawn `upscale.py` treats none of its texels as
  hidden (the application replaces the file by what it sees when the texture is drawn in
  a run). For everything else (interface art may be two fields or not, effects may be
  added or blended) the `.json` file holds no way of drawing, and `upscale.py` leaves
  such pictures alone until a run with `--rta-texture-dump` has seen them.
- The size in the name is that of what was sent (how the game's usual, repeating draws
  know the texture). A texture that is only ever drawn clamped (trails) is known by its
  full size instead and is not found under the name given here.

`--check DUMP_DIR` compares with a dump made by playing: every name computed here that is
also there must hold the same picture, pixel for pixel.

The figure is XXH3 (64 bits). Python has none, so the tool compiles a few lines of C
against the `xxhash.h` of the Play! checkout (`local/play-playable/deps/Dependencies/xxHash`
after `build.sh`; `--xxhash DIR` names another place) into `local/play-tools/`. Needs a C
compiler, Python 3 with numpy and Pillow. What is written is the game's art: keep it out
of any repository.
"""
import argparse
import ctypes
import json
import os
import struct
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

GS_BITBLTBUF, GS_TRXPOS, GS_TRXREG = 0x50, 0x51, 0x52
PSMCT32, PSMT8, PSMT4 = 0x00, 0x13, 0x14
MODEL_STATE = dict(prim=4, abe=1, alpha=1, fix=0, test=0x507F5, wms=0, wmt=0, mag=1, tfx=3, tcc=1, scanmsk=0, context=0)


# ---- XXH3 -------------------------------------------------------------------------------

def load_xxh3(include):
    cache = os.path.join(ROOT, 'local', 'play-tools')
    library = os.path.join(cache, 'rta-xxh3' + ('.dylib' if sys.platform == 'darwin' else '.so'))
    if not os.path.exists(library):
        if not os.path.exists(os.path.join(include, 'xxhash.h')):
            raise SystemExit('disctex.py: no xxhash.h in %s (run tools/play-net/build.sh once, or give --xxhash DIR)' % include)
        os.makedirs(cache, exist_ok=True)
        source = os.path.join(cache, 'rta-xxh3.c')
        with open(source, 'w') as file:
            file.write('#define XXH_INLINE_ALL\n#include "xxhash.h"\n'
                       'unsigned long long rta_xxh3(const void* data, unsigned long long size) { return XXH3_64bits(data, (size_t)size); }\n')
        subprocess.run(['cc', '-O2', '-shared', '-fPIC', '-I', include, '-o', library, source], check=True)
    lib = ctypes.CDLL(library)
    lib.rta_xxh3.restype = ctypes.c_ulonglong
    lib.rta_xxh3.argtypes = [ctypes.c_char_p, ctypes.c_ulonglong]
    return lambda data: lib.rta_xxh3(bytes(data), len(data))


# ---- the disc image and its lumps --------------------------------------------------------

class Iso:
    """Just enough of ISO 9660 to list and read files."""

    def __init__(self, path):
        self.file = open(path, 'rb')
        self.file.seek(16 * 2048)
        volume = self.file.read(2048)
        if volume[1:6] != b'CD001':
            raise SystemExit('disctex.py: %s is not an ISO 9660 image' % path)
        self.root = self._record(volume[156:190])

    @staticmethod
    def _record(d):
        return dict(lba=struct.unpack_from('<I', d, 2)[0], size=struct.unpack_from('<I', d, 10)[0], flags=d[25], name=d[33:33 + d[32]])

    def walk(self, record=None, prefix=''):
        record = record or self.root
        self.file.seek(record['lba'] * 2048)
        data = self.file.read(record['size'])
        o = 0
        while o < len(data):
            n = data[o]
            if n == 0:
                o = (o // 2048 + 1) * 2048
                continue
            entry = self._record(data[o:o + n])
            o += n
            if entry['name'] in (b'\x00', b'\x01'):
                continue
            name = entry['name'].decode('latin1').split(';')[0]
            if entry['flags'] & 2:
                yield from self.walk(entry, prefix + name + '/')
            else:
                yield prefix + name, entry

    def read(self, record):
        self.file.seek(record['lba'] * 2048)
        return self.file.read(record['size'])


def gob_entries(d):
    """.GOB: 40-byte records name[32], offset, size, ended by an empty name."""
    i = 0
    while i + 40 <= len(d) and d[i] != 0:
        name = d[i:i + 32].split(b'\0')[0].decode('latin1')
        offset, size = struct.unpack_from('<II', d, i + 32)
        yield name, d[offset:offset + size]
        i += 40


def lmp_entries(d):
    """.LMP: count, then name offset, data offset, data size for each entry."""
    if len(d) < 4:
        return
    count, = struct.unpack_from('<I', d, 0)
    if count > 100000 or 4 + count * 12 > len(d):
        return
    for i in range(count):
        name_at, data_at, size = struct.unpack_from('<III', d, 4 + i * 12)
        if name_at >= len(d) or data_at + size > len(d):
            return
        yield d[name_at:d.index(b'\0', name_at)].decode('latin1'), d[data_at:data_at + size]


def disc_textures(iso):
    """(where, name, bytes) of every .tex and .etex entry of the disc's lumps."""
    for path, record in iso.walk():
        upper = path.upper()
        if upper.endswith('.GOB'):
            lumps = [(path + ':' + name, blob) for name, blob in gob_entries(iso.read(record))]
        elif upper.endswith('.LMP'):
            lumps = [(path, iso.read(record))]
        else:
            continue
        for where, blob in lumps:
            for name, data in lmp_entries(blob):
                if name.lower().endswith(('.tex', '.etex')):
                    yield where, name, data


# ---- GS memory: where a pixel of each format lies in a page of 8192 bytes ------------------

_BLOCK_8x4 = ((0, 1, 4, 5, 16, 17, 20, 21), (2, 3, 6, 7, 18, 19, 22, 23),
              (8, 9, 12, 13, 24, 25, 28, 29), (10, 11, 14, 15, 26, 27, 30, 31))
_BLOCK_4x8 = ((0, 2, 8, 10), (1, 3, 9, 11), (4, 6, 12, 14), (5, 7, 13, 15),
              (16, 18, 24, 26), (17, 19, 25, 27), (20, 22, 28, 30), (21, 23, 29, 31))
_WORD = (0, 1, 4, 5, 8, 9, 12, 13)


def _column_word(x, yy):
    r = yy & 3
    xi = (x & 7) ^ (4 if ((yy + 2) >> 2) & 1 else 0)
    return (yy >> 2) * 16 + (r & 1) * 2 + _WORD[xi], r >> 1


def _tables():
    t32 = np.zeros((32, 64), dtype=np.int64)        # word in the page
    for y in range(32):
        for x in range(64):
            t32[y, x] = _BLOCK_8x4[(y >> 3) & 3][(x >> 3) & 7] * 64 + ((y & 7) >> 1) * 16 + (y & 1) * 2 + _WORD[x & 7]
    t8 = np.zeros((64, 128), dtype=np.int64)        # byte in the page
    for y in range(64):
        for x in range(128):
            word, odd = _column_word(x, y & 15)
            t8[y, x] = _BLOCK_8x4[(y >> 4) & 3][(x >> 4) & 7] * 256 + word * 4 + odd + (((x >> 3) & 1) << 1)
    t4 = np.zeros((128, 128), dtype=np.int64)       # nibble in the page
    for y in range(128):
        for x in range(128):
            word, odd = _column_word(x, y & 15)
            t4[y, x] = (_BLOCK_4x8[(y >> 4) & 7][(x >> 5) & 3] * 256 + word * 4) * 2 + odd + (((x >> 3) & 3) << 1)
    return t32, t8, t4


T32, T8, T4 = _tables()


def clut_order(i):
    """Place of palette entry i in the 16 x 16 block as stored."""
    return (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)


# ---- one texture -------------------------------------------------------------------------

class Skip(Exception):
    pass


def transfers(d, start, end):
    """The image transfers of an upload packet, in order."""
    state = dict(dbw=0, dpsm=0, x=0, y=0, w=0, h=0)
    buffer, out, o = -1, [], start
    while o + 16 <= end:
        low, = struct.unpack_from('<Q', d, o)
        o += 16
        nloop, flg, nreg = low & 0x7FFF, (low >> 58) & 3, (low >> 60) & 15
        if flg == 0:
            for _ in range(nloop * (nreg or 16)):
                value, register = struct.unpack_from('<QQ', d, o)
                register &= 0xFF
                o += 16
                if register == GS_BITBLTBUF:
                    buffer += 1
                    state['dbw'], state['dpsm'] = (value >> 48) & 0x3F, (value >> 56) & 0x3F
                elif register == GS_TRXPOS:
                    state['x'], state['y'] = (value >> 32) & 0x7FF, (value >> 48) & 0x7FF
                elif register == GS_TRXREG:
                    state['w'], state['h'] = value & 0xFFF, (value >> 32) & 0xFFF
        elif flg == 2:
            bits = {PSMCT32: 32, PSMT4: 4, PSMT8: 8}.get(state['dpsm'])
            if bits is None or buffer < 0:
                raise Skip('sent in format 0x%x' % state['dpsm'])
            size = (state['w'] * state['h'] * bits + 7) // 8
            if size > nloop * 16 or o + size > end:
                raise Skip('image data shorter than its rectangle')
            out.append(dict(state, buffer=buffer, data=d[o:o + size]))
            o += nloop * 16
        else:
            raise Skip('a GIF tag of another kind')
    return out


def decode(data, xxh):
    """name, RGBA picture, size named by TEX0, header flags, whether every texel was sent."""
    if len(data) < 0x90:
        raise Skip('too small')
    width, height, _, qwc, flags = struct.unpack_from('<5H', data, 0)
    tex0, packet = struct.unpack_from('<II', data, 0x0C)
    if packet != 0x80 or 0x80 + qwc * 16 > len(data):
        raise Skip('not a lump texture')
    if width == 0 or height == 0 or flags & 0x0080:
        raise Skip('no picture (a palette alone, or a surface the engine draws into)')
    tbw, psm = tex0 & 0x3F, (tex0 >> 6) & 0x3F
    named = (1 << ((tex0 >> 12) & 15), 1 << ((tex0 >> 16) & 15))
    pieces = transfers(data, 0x80, 0x80 + qwc * 16)
    if not pieces:
        raise Skip('no image data')
    image = [p for p in pieces if p['buffer'] == pieces[-1]['buffer']]
    palette = [p for p in pieces if p['buffer'] != pieces[-1]['buffer']]
    if len(image) > 256:
        raise Skip('more than 256 pieces')

    # the figure of what is sent, as the application chains it (RecordUpload)
    figure = 0
    for p in image:
        figure = xxh(struct.pack('<5Q', figure, (p['y'] << 32) | p['x'], (p['h'] << 32) | p['w'], xxh(p['data']), (p['dbw'] << 32) | p['dpsm']))

    first = image[0]
    plain = len(image) == 1 and first['dpsm'] == psm and first['dbw'] == tbw and first['x'] == 0 and first['y'] == 0
    if plain:
        w, h = min(first['w'], named[0]), min(first['h'], named[1])
        covered = np.ones((h, w), dtype=bool)
        if psm == PSMCT32:
            texels = np.frombuffer(first['data'], dtype='<u4').reshape(first['h'], first['w'])[:h, :w]
        elif psm == PSMT4:
            nibbles = np.frombuffer(first['data'], dtype=np.uint8)
            nibbles = np.stack([nibbles & 15, nibbles >> 4], axis=1).reshape(-1)[:first['w'] * first['h']]
            texels = nibbles.reshape(first['h'], first['w'])[:h, :w]
        else:
            texels = np.frombuffer(first['data'], dtype=np.uint8).reshape(first['h'], first['w'])[:h, :w]
    else:
        if any(p['dpsm'] != PSMCT32 or p['dbw'] != first['dbw'] for p in image) or psm not in (PSMT8, PSMT4) or tbw != 2 * first['dbw']:
            raise Skip('an upload this tool does not follow')
        natural = psm == PSMT8
        if not natural:                             # the same bytes read as another format are another picture
            figure = xxh(struct.pack('<2Q', figure, (tbw << 32) | psm))
        dbw = first['dbw']
        # the pieces written into GS memory as 32-bit pixels ...
        pages = 1
        for p in image:
            if p['x'] + p['w'] > dbw * 64:
                raise Skip('a piece wider than its buffer')
            pages = max(pages, ((p['y'] + p['h'] - 1) >> 5) * dbw + dbw)
        if psm == PSMT8:
            pages = max(pages, ((named[1] - 1) >> 6) * dbw + ((named[0] - 1) >> 7) + 1)
        else:
            pages = max(pages, ((named[1] - 1) >> 7) * dbw + ((named[0] - 1) >> 7) + 1)
        memory = np.zeros(pages * 2048, dtype='<u4')
        written = np.zeros(pages * 2048, dtype=bool)
        for p in image:
            ys, xs = p['y'] + np.arange(p['h']), p['x'] + np.arange(p['w'])
            words = ((ys >> 5) * dbw)[:, None] * 2048 + (xs >> 6)[None, :] * 2048 + T32[(ys & 31)[:, None], (xs & 63)[None, :]]
            memory[words] = np.frombuffer(p['data'], dtype='<u4').reshape(p['h'], p['w'])
            written[words] = True
        memory = memory.view(np.uint8)
        # ... and read back as the texture's own format
        ys, xs = np.arange(named[1]), np.arange(named[0])
        if psm == PSMT8:
            at = ((ys >> 6) * dbw)[:, None] * 8192 + (xs >> 7)[None, :] * 8192 + T8[(ys & 63)[:, None], (xs & 127)[None, :]]
            texels, covered = memory[at], written[at >> 2]
        else:
            at = ((ys >> 7) * dbw)[:, None] * 16384 + (xs >> 7)[None, :] * 16384 + T4[(ys & 127)[:, None], (xs & 127)[None, :]]
            texels, covered = (memory[at >> 1] >> (4 * (at & 1))) & 15, written[at >> 3]
        if not covered.any():
            raise Skip('nothing of it lies inside the texture')
        w = int(np.nonzero(covered.any(axis=0))[0].max()) + 1
        h = int(np.nonzero(covered.any(axis=1))[0].max()) + 1
        texels, covered = texels[:h, :w], covered[:h, :w]

    palette_figure = 0
    if psm == PSMCT32:
        rgba = texels.astype('<u4')
    else:
        entries = 256 if psm == PSMT8 else 16
        if len(palette) != 1 or len(palette[0]['data']) < entries * 4:
            raise Skip('no palette of its own')
        colours = np.frombuffer(palette[0]['data'], dtype='<u4')[:entries]
        if psm == PSMT8:
            colours = colours[[clut_order(i) for i in range(256)]]
        palette_figure = xxh(colours.astype('<u4').tobytes())
        rgba = colours[texels]
    rgba = np.where(covered, rgba, 0).astype('<u4')
    picture = rgba.view(np.uint8).reshape(h, w, 4)
    name = '%016x-%016x-p%u-%ux%u.png' % (figure, palette_figure, psm, w, h)
    return name, picture, named, flags, bool(covered.all())


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('disc')
    parser.add_argument('out', nargs='?')
    parser.add_argument('--only', default='', help='only lumps or textures whose name contains this text (any case)')
    parser.add_argument('--kinds', default='model,other', help='model (header flag 0x0010), other; default both')
    parser.add_argument('--list', action='store_true', help='print the names and write nothing')
    parser.add_argument('--check', metavar='DUMP_DIR', help='compare with pictures dumped by playing')
    parser.add_argument('--xxhash', default=os.path.join(ROOT, 'local', 'play-playable', 'deps', 'Dependencies', 'xxHash'), help='directory of xxhash.h')
    args = parser.parse_args()
    if not args.list and not args.check and not args.out:
        parser.error('give OUT_DIR, --list or --check')
    xxh = load_xxh3(args.xxhash)
    kinds = set(args.kinds.split(','))
    if args.out and not args.list:
        os.makedirs(args.out, exist_ok=True)

    seen, counts, skipped = {}, dict(model=0, other=0), {}
    same = different = written = 0
    for where, entry, data in disc_textures(Iso(args.disc)):
        if args.only and args.only.lower() not in (where + ':' + entry).lower():
            continue
        try:
            name, picture, named, flags, whole = decode(data, xxh)
        except Skip as reason:
            skipped[str(reason)] = skipped.get(str(reason), 0) + 1
            continue
        kind = 'model' if flags & 0x0010 else 'other'
        if kind not in kinds or name in seen:
            continue
        seen[name] = where + ':' + entry
        counts[kind] += 1
        if args.list:
            print('%s %-5s %s:%s' % (name, kind, where, entry))
        if args.check:
            path = os.path.join(args.check, name)
            if os.path.exists(path):
                if np.array_equal(np.asarray(Image.open(path).convert('RGBA')), picture):
                    same += 1
                else:
                    different += 1
                    print('DIFFERENT: %s (%s:%s)' % (name, where, entry))
        if args.out and not args.list:
            path = os.path.join(args.out, name)
            if not os.path.exists(path):
                Image.fromarray(picture, 'RGBA').save(path)
                written += 1
            meta_path = path[:-4] + '.json'
            if not os.path.exists(meta_path):
                meta = dict(picture=name, source='disc', file=where + ':' + entry, flags=flags, format=int(name.split('-p')[1].split('-')[0]),
                            width=picture.shape[1], height=picture.shape[0], named_width=named[0], named_height=named[1], whole=whole,
                            states=[MODEL_STATE] if kind == 'model' else [])
                with open(meta_path, 'w') as file:
                    json.dump(meta, file)
    print('disctex.py: %d different pictures named (%d model textures, %d others)' % (len(seen), counts['model'], counts['other']))
    for reason, count in sorted(skipped.items()):
        print('disctex.py: %d left out: %s' % (count, reason))
    if args.check:
        dumped = [n for n in os.listdir(args.check) if n.endswith('.png')]
        print('disctex.py: of %d dumped pictures %d have a name computed here: %d hold the same picture, %d differ'
              % (len(dumped), same + different, same, different))
    if args.out and not args.list:
        print('disctex.py: %d pictures written to %s' % (written, args.out))
    return 1 if different else 0


if __name__ == '__main__':
    sys.exit(main())
