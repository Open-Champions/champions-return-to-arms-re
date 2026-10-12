#!/usr/bin/env python3
"""poolcmp.py - the object pools of two machines at one tick, object by object.

  python3 tools/recomp/soak/farm.py one --arm fix25 --out DIR --seed S --dump 1041,1227 --tag=-d
  python3 tools/recomp/soak/poolcmp.py DIR/fix25-S-d 1041 1227 [--machines 0,1] [--words] [--all]

Reads the dumps `farm.py one --dump` leaves (m<k>-pool-<tick>.bin: 0xe7700 bytes at
0x5f88c0; m<k>-glob-<tick>.bin: 0x2000 bytes at 0x402000, which holds the pool table at
0x403a10 and the prediction copy's address at 0x4027bc).  For every block that is live on
both machines and is not a prediction copy it lists the word offsets that differ, grouped
by class (the name of the virtual table at +0x48, from vtables.txt); --words prints each
differing word with both values.  The three handle heads (+0, +4, +8) and, in a Player,
the flag bits 0x200100 differ between machines in step and are left out, and a word that
is an address is compared as soakhooks.cpp compares it (a heap address as such, a pool
address as the class it points into), unless --all is given.  --masked: the words of
poolmask.txt are left out too (what "poolraw" sees).  --sum: one table over all the ticks
given; --mask: the same as lines for poolmask.txt.

Standard library only.  The dumps are game data: keep them under local/.
"""
import collections
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE = 0x5F88C0
VT_PLAYER = 0x511308


def vtable_names():
    names = {}
    for line in open(os.path.join(ROOT, 'vtables.txt'), errors='replace'):
        fields = line.split()
        if len(fields) >= 2 and fields[0].startswith('0x'):
            try:
                names[int(fields[0], 16)] = fields[1]
            except ValueError:
                pass
    return names


def load(directory, machine, tick):
    pool = open(os.path.join(directory, 'm%d-pool-%d.bin' % (machine, tick)), 'rb').read()
    glob = open(os.path.join(directory, 'm%d-glob-%d.bin' % (machine, tick)), 'rb').read()
    word = lambda a: struct.unpack_from('<I', glob, a - 0x402000)[0]
    classes, free = [], set()
    for entry in range(0x403A10, 0x403A40, 16):
        size, count, base, head = word(entry), word(entry + 4), word(entry + 8), word(entry + 12)
        classes.append((size, count, base))
        steps = 0
        while base <= head < base + size * count and steps <= count:
            free.add(head)
            head = struct.unpack_from('<I', pool, head - BASE)[0]
            steps += 1
    return pool, classes, free, word(0x4027BC)


def canon(value, pool, classes):
    """soakhooks.cpp's view of a word that is an address: a heap address is "a heap address",
    an address in the pool the class it points into and the offset there."""
    if value < BASE or value >= 0x2000000:
        return value
    if value >= BASE + 0xE7700:
        return 0xA0000002
    for size, count, base in classes:
        if base <= value < base + size * count:
            block = base + (value - base) // size * size
            return 0xB0000000 ^ ((struct.unpack_from('<I', pool, block - BASE + 0x48)[0] * 31) & 0xFFFFFFFF) ^ (value - block)
    return 0xA0000001


def read_mask():
    """poolmask.txt as {virtual table or 0: {offset: bits}}, with what soakhooks.cpp has built in."""
    mask = {0: {0: 0xFFFFFFFF, 4: 0xFFFFFFFF, 8: 0xFFFFFFFF}, VT_PLAYER: {0xC: 0x200100}}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'poolmask.txt')
    if os.path.exists(path):
        for line in open(path):
            fields = line.split('#')[0].split()
            if len(fields) < 2 or fields[1] in ('nohard', 'skip'):
                continue
            vtable = 0 if fields[0] == '*' else int(fields[0], 16)
            entry = mask.setdefault(vtable, {})
            offset = int(fields[1], 16)
            entry[offset] = entry.get(offset, 0) | (int(fields[2], 16) if len(fields) > 2 else 0xFFFFFFFF)
    return mask


def compare(directory, tick, machines=(0, 1), everything=False, masked=False, names=None):
    """(per class: Counter of differing word offsets, lines).  masked: also leave out the
    words of poolmask.txt - what is left is what the "poolraw" checksum sees."""
    names = names or vtable_names()
    mask = read_mask() if masked else {}
    pa, classes, fa, ga = load(directory, machines[0], tick)
    pb, _, fb, gb = load(directory, machines[1], tick)
    offsets = collections.defaultdict(collections.Counter)
    lines = []
    live = [0, 0]
    for size, count, base in classes:
        for i in range(count):
            block = base + i * size
            la, lb = block not in fa, block not in fb
            live[0] += la
            live[1] += lb
            oa, ob = pa[block - BASE:block - BASE + size], pb[block - BASE:block - BASE + size]
            va, vb = struct.unpack_from('<I', oa, 0x48)[0], struct.unpack_from('<I', ob, 0x48)[0]
            if block in (ga, gb):
                continue
            if la != lb:
                lines.append('  block %x (0x%x bytes): %s on machine %d, %s on machine %d' % (
                    block, size, names.get(va, hex(va)) if la else 'free', machines[0],
                    names.get(vb, hex(vb)) if lb else 'free', machines[1]))
                continue
            if not la or oa == ob:
                continue
            if va not in names and not everything:       # not a game object: soakhooks.cpp leaves it out
                continue
            name = names.get(va, hex(va)) + ('' if va == vb else '/' + names.get(vb, hex(vb)))
            for o in range(0, size & ~3, 4):
                wa, wb = struct.unpack_from('<I', oa, o)[0], struct.unpack_from('<I', ob, o)[0]
                if wa == wb:
                    continue
                if not everything:
                    if o != 0xC:
                        wa, wb = canon(wa, pa, classes), canon(wb, pb, classes)
                    if o in (0, 4, 8):
                        continue
                    if va == VT_PLAYER and o == 0xC:
                        wa, wb = wa & ~0x200100, wb & ~0x200100
                    if masked:
                        bits = mask.get(0, {}).get(o, 0) | mask.get(va, {}).get(o, 0)
                        wa, wb = wa & ~bits, wb & ~bits
                if wa != wb:
                    offsets[name][o] += 1
                    lines.append('  %s at %x +0x%x: %08x | %08x' % (name, block, o, wa, wb))
    return offsets, lines, live, (ga, gb)


def main(argv):
    flags = [a for a in argv if a.startswith('--')]
    args = [a for a in argv if not a.startswith('--')]
    machines = (0, 1)
    for flag in flags:
        if flag.startswith('--machines='):
            machines = tuple(int(x) for x in flag.split('=')[1].split(','))
    directory, ticks = args[0], [int(t) for t in args[1:]]
    names = vtable_names()
    total = collections.defaultdict(collections.Counter)
    for tick in ticks:
        offsets, lines, live, ghosts = compare(directory, tick, machines, '--all' in flags, '--masked' in flags, names)
        for name, counter in offsets.items():
            for offset, n in counter.items():
                total[name][offset] += n
        if '--sum' in flags or '--mask' in flags:
            continue
        print('tick %d: live %d and %d (prediction copies at %x and %x)' % (tick, live[0], live[1], ghosts[0], ghosts[1]))
        for name, counter in sorted(offsets.items()):
            print('  %s: differing word offsets (objects): %s' % (name, ' '.join('%x(%d)' % item for item in sorted(counter.items()))))
        if '--words' in flags or not offsets:
            print('\n'.join(l for l in lines if '--words' in flags or l.startswith('  block'))[:20000])
        if not offsets and not lines:
            print('  no difference')
    if '--mask' in flags:       # lines for poolmask.txt
        by_name = {name: address for address, name in names.items()}
        for name, counter in sorted(total.items()):
            for offset in sorted(counter):
                print('%x %x\t# %s' % (by_name.get(name.split('/')[0], 0), offset, name))
        return 0
    if '--sum' in flags:
        print('%d ticks; per class, word offsets that differ (object-ticks):' % len(ticks))
        for name, counter in sorted(total.items()):
            print('  %s: %s' % (name, ' '.join('%x(%d)' % item for item in sorted(counter.items()))))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
