#!/usr/bin/env python3
"""Compare appearance lookups and item model indices with original US v2.00 code.

Usage: PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_player_appearance.py ELF ISO
Reads private inputs only. The constructor is isolated from world setup; this is
function-level execution, not a live visual or equipment draw test.
"""
import hashlib
import json
import mmap
import os
import struct
import sys

from anim_audio_info import iso_files, lmp_entries
from ee_emu import EE
from ps2elf import Elf
import ref_player_appearance as ref

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
RECORD = 0x4d8af0


def cstr(mem, addr):
    return mem.read(addr, 96).split(b'\0', 1)[0].decode('ascii')


def constructor(elf, index, choices, select2, seed, entries):
    ee = EE(elf)
    ee.follow = set(range(0x3a0000, 0x3c3000, 4))
    ee.mem.auto_map = True
    obj, pos = ee.alloc(0x590), ee.alloc(12)
    ee.mem.w32(RECORD + 0x54, index)
    ee.mem.write(RECORD + 0x20, bytes(x & 255 for x in choices))
    ee.mem.w32(0x4d8ae0, 2 if select2 else 1)
    ee.mem.w32(0x404464, seed)
    found = []

    def lookup(e):
        lump, name = cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5])
        found.append((lump, name))
        return 0x100000 + len(found) * 0x100 if name in entries[lump] else 0

    ee.stub(0x17365c, function=lookup)
    ee.call(0x1a1d28, obj, pos, 0, 0, 0, max_steps=1000000)
    handles = tuple(ee.mem.u32(obj + off) for off in (0x544, 0x548, 0x54c, 0x550, 0x554, 0x558))
    return found, handles, ee.mem.u32(0x404464)


def item_indices(elf):
    ee = EE(elf)
    ee.mem.auto_map = True
    definition, item = ee.alloc(0x40), ee.alloc(0x48)
    ee.mem.w32(item, definition)
    count = 0
    for base in range(134):
        for variant in (0, 1, 7, 31):
            for enabled in (False, True):
                flags = ((variant << 11) | ((1 << 36) if enabled else 0))
                ee.mem.w16(definition + 0x34, base)
                ee.mem.w64(item + 8, flags)
                got = ee.call(0x1083f8, item)
                want = ref.item_model_index(base, flags)
                assert got == want, (base, variant, enabled, got, want)
                count += 1
    return count


def cache_groups(image, files, name):
    """Read only the name/variant directory of a packed equipment cache."""
    off, size, _ = files['/BG/DATA/' + name]
    header = image[off:off + size]
    count, = struct.unpack_from('<I', header)
    groups = []
    for index in range(count):
        variants_at, name_at, length = struct.unpack_from('<III', header, 4 + index * 12)
        assert variants_at + 8 * length <= size and name_at < size
        end = header.index(b'\0', name_at)
        stem = header[name_at:end].decode('ascii')
        variants = [struct.unpack_from('<h', header, variants_at + 8 * j)[0]
                    for j in range(length)]
        groups.append({'stem': stem, 'variants': variants})
    return groups


def main(elf, disc, manifest_path=None):
    with open(elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA256, 'wrong executable revision'
    data = Elf(elf)
    with open(disc, 'rb') as source:
        image = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        files = iso_files(image)
        entries = {}
        for lump in ('select.lmp', 'select2.lmp'):
            off, size, _ = files['/BG/DATA/' + lump.upper()]
            entries[lump] = {name.lower() for name, _, _ in lmp_entries(image[off:off + size])}
        cache_catalog = {name: cache_groups(image, files, name)
                         for name in ('EQCACHE.HDR', 'EQCACHE2.HDR', 'WCACHE.HDR')}
        cases = 0
        for seed in (20973, 7):
            for index, code in enumerate(ref.BODY_CODES):
                assert data.cstr(data.u32(0x4ebbb8 + 4 * index)) == code
                for choices, select2 in (((-1, 0, -1, 0), False),
                                         ((0, 0, 0, 0), False),
                                         ((1, 1, -1, 1), True),
                                         ((2, 2, 1, 2), True)):
                    got, handles, after = constructor(elf, index, choices, select2, seed, entries)
                    expected = ref.part_requests(index, choices, select2)
                    assert got == [(lump, name) for lump, name, _ in expected], (index, got, expected)
                    lookup_handles = {off: 0 for off in (0x544, 0x548, 0x54c, 0x550, 0x554, 0x558)}
                    for number, (lump, name, off) in enumerate(expected, 1):
                        if name in entries[lump]:
                            lookup_handles[off] = 0x100000 + number * 0x100
                    assert handles == tuple(lookup_handles.values()), (index, choices, handles, lookup_handles)
                    assert after == seed
                    cases += 1
        image.close()
    indices = item_indices(elf)
    if manifest_path:
        rows = []
        for index in range(134):
            addr = 0x3e9ce0 + 16 * index
            rows.append({'index': index, 'model': data.cstr(data.u32(addr)),
                         'texture': data.cstr(data.u32(addr + 4))})
        with open(manifest_path, 'w', encoding='utf-8') as out:
            json.dump({'source': 'SLUS-20973 v2.00 g_itemModels 0x3e9ce0 and disc cache headers',
                       'item_models': rows, 'cache_groups': cache_catalog}, out, indent=2)
            out.write('\n')
    counts = ', '.join(f'{name} {len(groups)}' for name, groups in cache_catalog.items())
    print(f'PASS appearance: {cases} constructor cases; {indices} item index cases; '
          f'cache groups {counts}; seeds 20973 and 7')


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_elf = os.path.join(root, 'local', 'SLUS_209.73')
    default_iso = os.path.expanduser('~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')
    args = sys.argv[1:]
    manifest = None
    if '--manifest' in args:
        at = args.index('--manifest')
        manifest = args[at + 1]
        del args[at:at + 2]
    main(args[0] if args else default_elf,
         args[1] if len(args) > 1 else default_iso, manifest)
