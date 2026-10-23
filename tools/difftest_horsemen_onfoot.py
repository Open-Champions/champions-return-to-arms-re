#!/usr/bin/env python3
"""Verify the four on-foot Horsemen placements on an owner's v2.00 disc.

Read-only ISO scan plus original obj_getPropInt/Str in ee_emu.py. No disc data is
written. Run with --seed 20973 and --seed 7; see docs/spec/horsemen-mount.md 9.5.
"""
import argparse
import hashlib
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import difftest_objects as DO  # noqa: E402
import dump_tables as DT  # noqa: E402

KNIGHTS = tuple('UndeadKnight%d' % n for n in range(1, 5))
FIELDS = ('deathscript', 'wait', 'light1', 'light2', 'name', 'dropitem')
OFFSETS = ((0x124, 0x138), (0x154, 0x168), (0x184, 0x198), (0x1B4, 0x1C8))
DROPS = ('rejuvpotion', 'healingpotion', 'rejuvpotion', 'healingpotion')
DISC_GOBS, OBJECT_LUMPS, OBJECT_ROWS = 120, 120, 18675


def records(blob):
    """Yield (record offset, property-array offset, type, property strings)."""
    if len(blob) < 8:
        raise ValueError('short objects.ob')
    count, _flags, strtab = struct.unpack_from('<hHi', blob, 0)
    if count < 0 or not 0 <= strtab <= len(blob) or (count and strtab == len(blob)):
        raise ValueError('invalid objects.ob header')

    def string(offset):
        start = strtab + offset
        if not strtab <= start < len(blob):
            raise ValueError('string offset outside objects.ob')
        end = blob.find(b'\0', start)
        if end < 0:
            raise ValueError('unterminated objects.ob string')
        return blob[start:end].decode('latin1')

    pos = 8
    for _ in range(count):
        if pos + 20 > len(blob):
            raise ValueError('short object record')
        cls, size = struct.unpack_from('<ih', blob, pos)
        if size < 24 or pos + size > len(blob):
            raise ValueError('invalid object record size')
        props = []
        ptr = pos + 20
        while ptr + 4 <= pos + size:
            offset, = struct.unpack_from('<i', blob, ptr)
            if offset == 0:
                break
            props.append(string(offset))
            ptr += 4
        else:
            raise ValueError('unterminated property array')
        yield pos, pos + 20, string(cls), props
        pos += size


def scan(iso):
    matches = {name: [] for name in KNIGHTS}
    gobs = lumps = rows = 0
    for path, start, size in DT.iso_files(iso):
        if not path.upper().endswith('.GOB'):
            continue
        gobs += 1
        gob = iso[start:start + size]
        for lump_name, offset, length in DT.gob_entries(gob):
            if offset + length > len(gob):
                raise ValueError('GOB entry outside %s' % path)
            lump = gob[offset:offset + length]
            entries = DT.lmp_entries(lump)
            if not entries:
                raise ValueError('invalid level lump in %s' % path)
            for name, obj_offset, obj_length in entries:
                if name.lower() != 'objects.ob':
                    continue
                lumps += 1
                for rec_offset, prop_offset, cls, props in records(lump[obj_offset:obj_offset + obj_length]):
                    rows += 1
                    if cls in matches:
                        matches[cls].append((path, lump_name, rec_offset, prop_offset, props))
    if (gobs, lumps, rows) != (DISC_GOBS, OBJECT_LUMPS, OBJECT_ROWS):
        raise ValueError('disc scan coverage changed: %s' % ((gobs, lumps, rows),))
    return matches, (gobs, lumps, rows)


def check(elf, matches, seed):
    rig = DO.Rig(elf, seed)
    mem = rig.emu.mem
    death_scripts, lights = [], []
    for variant, name in enumerate(KNIGHTS):
        placements = matches[name]
        if len(placements) != 1:
            raise ValueError('%s has %d placements, expected one' % (name, len(placements)))
        path, lump, record_offset, prop_offset, props = placements[0]
        if (path.upper(), lump.lower()) != ('/BG/DATA/DRUNARE.GOB', 'drunare.lmp'):
            raise ValueError('%s is outside Drundar' % name)
        if (record_offset, prop_offset) != OFFSETS[variant]:
            raise ValueError('%s offsets changed' % name)
        parts = [prop.split('=', 1) for prop in props]
        if len(parts) != len(FIELDS) or tuple(part[0] for part in parts) != FIELDS:
            raise ValueError('%s ordered fields changed' % name)
        values = {key: value for key, value in parts}
        if values['wait'] != '1' or values['name'] != 'knight' or values['dropitem'] != DROPS[variant]:
            raise ValueError('%s fixed property values changed' % name)
        if not values['deathscript'] or not values['light1'] or not values['light2']:
            raise ValueError('%s empty script or light property' % name)
        death_scripts.append(values['deathscript'])
        lights.append((values['light1'], values['light2']))

        # Execute the original parser on the six strings extracted above. The
        # object and pointer array are scratch memory; no game bytes are stored.
        prop_index = rig.add_props([entry.encode('latin1') for entry in props])
        obj = rig.emu.alloc(0x50)
        mem.w32(obj + 0x2C, rig.props[prop_index][0])
        for key in FIELDS:
            if key == 'wait':
                actual = rig.ecall(DO.A['obj_getPropInt'], obj, rig.cstring(b'wait'), 0)
                if actual != 1:
                    raise ValueError('%s original wait parser returned %d' % (name, actual))
            else:
                ptr = rig.ecall(DO.A['obj_getPropStr'], obj, rig.cstring(key.encode('ascii')), 0)
                if not ptr or mem.cstr(ptr) != values[key]:
                    raise ValueError('%s original %s parser mismatch' % (name, key))
    if len(set(death_scripts)) != 4 or len(set(lights)) != 1:
        raise ValueError('death scripts or light properties changed')
    print('PASS on-foot disc scan: %d GOBs, %d objects.ob, %d records; 4 exact placements; '
          '24 original parser reads; seed %d' % (DISC_GOBS, OBJECT_LUMPS, OBJECT_ROWS, seed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', help='owner SLUS_209.73 executable')
    parser.add_argument('iso', help='owner v2.00 disc image')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        if hashlib.sha256(stream.read()).hexdigest() != DT.KNOWN_SHA256:
            parser.error('executable is not pinned SLUS_209.73 v2.00')
    with open(args.iso, 'rb') as stream:
        iso = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            matches, _coverage = scan(iso)
        finally:
            iso.close()
    check(args.elf, matches, args.seed)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, struct.error, IndexError) as exc:
        sys.exit('FAIL on-foot disc scan: %s' % exc)
