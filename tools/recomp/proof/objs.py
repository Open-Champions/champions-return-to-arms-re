#!/usr/bin/env python3
"""objs.py - the objects in the pool of a memory image: class, position, flags.

  python3 tools/recomp/proof/objs.py IMAGE.bin [--near X,Y[,R]] [--class NAME]

A development aid for writing play scripts (play.py): where the things the character can
use are.  An object's class is the virtual table at +0x48 (named from vtables.txt), its
position the three floats at +0x10, its flag word at +0x0c (docs/objects.md; 0x100000 =
can be used, what Player_interact looks for).  Output is game data: keep it under local/.
"""
import argparse
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import imgdiff                                   # noqa: E402

PLAYER_PTR = 0x4D8AF0 + 0x43D8


def objects(image):
    names = imgdiff.vtables()
    out = []
    for base, size, count in imgdiff.pool_classes(image):
        for n in range(count):
            at = base + n * size
            table = imgdiff.word(image, at + 0x48)
            if table not in names:
                continue
            x, y, z = struct.unpack_from('<3f', image, at + 0x10)
            if not all(math.isfinite(v) and abs(v) < 1e6 for v in (x, y, z)):
                continue
            out.append(dict(addr=at, cls=names[table], x=x, y=y, z=z, flags=imgdiff.word(image, at + 0xC), size=size))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('image')
    parser.add_argument('--near')
    parser.add_argument('--class', dest='cls')
    parser.add_argument('--usable', action='store_true')
    args = parser.parse_args()
    image = open(args.image, 'rb').read()
    me = imgdiff.word(image, PLAYER_PTR)
    px, py, pz = struct.unpack_from('<3f', image, me + 0x10) if me else (0, 0, 0)
    cx, cy, radius = px, py, 1e9
    if args.near:
        parts = [float(v) for v in args.near.split(',')]
        cx, cy = parts[0], parts[1]
        radius = parts[2] if len(parts) > 2 else 300
    print('player object %06x at (%.1f, %.1f, %.1f)' % (me, px, py, pz))
    rows = []
    for o in objects(image):
        d = math.hypot(o['x'] - cx, o['y'] - cy)
        if d > radius or (args.cls and args.cls.lower() not in o['cls'].lower()) or (args.usable and not o['flags'] & 0x100000):
            continue
        rows.append((d, o))
    for d, o in sorted(rows, key=lambda r: r[0]):
        print('%06x %-22s (%9.1f %9.1f %8.1f) %7.1f away  flags %08x%s' % (
            o['addr'], o['cls'], o['x'], o['y'], o['z'], d, o['flags'], '  usable' if o['flags'] & 0x100000 else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
