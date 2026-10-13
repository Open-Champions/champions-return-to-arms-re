#!/usr/bin/env python3
"""imgdiff.py - where two memory images of the same tick differ, in the game's terms.

  python3 tools/recomp/proof/imgdiff.py RIG.bin NATIVE.bin [--range LO:HI]... [--max N]

The images are the 32 MB main memory of the rig and of the native run at the same level
episode and tick (session.py with "dumps" in the session, or rigcompare.py memdiff's
inputs).  Prints every differing 32-bit word of the compared ranges - by default the
object pool and the four player records, the ranges the tick log's `pool` and `record0`
columns cover - with

  - for a pool word: the object it lies in (found through the pool's class table,
    g_poolClasses 0x403a10: {size, count, base, free head} x 3), the object's class (the
    virtual table at +0x48, named from vtables.txt) and the offset inside the object;
  - for a record word: the player slot and the offset inside the record;
  - both values, as hexadecimal and as floats.

Nothing here is game data; the images are, and stay under local/.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
POOL = (0x5F88C0, 0x5F88C0 + 947968)
PLAYERS, RECORD = 0x4D8AF0, 19504
POOL_CLASSES = 0x403A10


def vtables():
    table = {}
    path = os.path.join(ROOT, 'vtables.txt')
    if os.path.exists(path):
        for line in open(path, errors='replace'):
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith('0x'):
                try:
                    table[int(parts[0], 16)] = parts[1]
                except ValueError:
                    pass
    return table


def word(image, at):
    return struct.unpack_from('<I', image, at)[0]


def as_float(value):
    f = struct.unpack('<f', struct.pack('<I', value))[0]
    return '%.6g' % f if 1e-6 < abs(f) < 1e9 or f == 0 else '-'


def pool_classes(image):
    out = []
    for n in range(3):
        size, count, base, _free = struct.unpack_from('<4I', image, POOL_CLASSES + 16 * n)
        if 0 < size < 0x10000 and POOL[0] <= base < POOL[1]:
            out.append((base, size, count))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('rig')
    parser.add_argument('native')
    parser.add_argument('--range', action='append', default=[], help='LO:HI (hex); default: the object pool and the player records')
    parser.add_argument('--max', type=int, default=60)
    args = parser.parse_args()
    a, b = open(args.rig, 'rb').read(), open(args.native, 'rb').read()
    ranges = [tuple(int(x, 16) for x in r.split(':')) for r in args.range] or [POOL, (PLAYERS, PLAYERS + 4 * RECORD)]
    names = vtables()
    classes = pool_classes(a)
    total = 0
    for lo, hi in ranges:
        if a[lo:hi] == b[lo:hi]:
            print('%06x-%06x: identical' % (lo, hi))
            continue
        shown = 0
        count = sum(1 for at in range(lo & ~3, hi, 4) if a[at:at + 4] != b[at:at + 4])
        print('%06x-%06x: %d words differ' % (lo, hi, count))
        total += count
        for at in range(lo & ~3, hi, 4):
            if a[at:at + 4] == b[at:at + 4]:
                continue
            shown += 1
            if shown > args.max:
                continue
            x, y = word(a, at), word(b, at)
            where = ''
            if POOL[0] <= at < POOL[1]:
                for base, size, count in classes:
                    if base <= at < base + size * count:
                        obj = base + (at - base) // size * size
                        table = word(a, obj + 0x48)
                        where = 'object %06x (%s, block of 0x%x) +0x%x' % (obj, names.get(table, 'table %08x' % table), size, at - obj)
            elif PLAYERS <= at < PLAYERS + 4 * RECORD:
                where = 'player %d record +0x%x' % ((at - PLAYERS) // RECORD, (at - PLAYERS) % RECORD)
            print('  %06x  rig %08x (%s)  native %08x (%s)  %s' % (at, x, as_float(x), y, as_float(y), where))
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
