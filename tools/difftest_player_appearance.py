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
import re
import struct
import sys

from anim_audio_info import iso_files, lmp_entries
from ee_emu import EE
from ps2elf import Elf
import ref_player_appearance as ref

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
RECORD = 0x4d8af0

BODY_TEXTURES = (5, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 4)
HAIR_STYLES = (4, 6, 5, 6, 6, 6, 3, 4, 5, 7, 3, 4)
BEARD_STYLES = (4, 0, 0, 0, 0, 0, 3, 0, 4, 0, 0, 3)


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
    """Read name and texture/model sector pairs from a packed cache header."""
    off, size, _ = files['/BG/DATA/' + name]
    data_size = files['/BG/DATA/' + name.replace('.HDR', '.DAT')][1]
    header = image[off:off + size]
    count, = struct.unpack_from('<I', header)
    groups = []
    for index in range(count):
        variants_at, name_at, length = struct.unpack_from('<III', header, 4 + index * 12)
        assert length % 2 == 0 and variants_at + 8 * length <= size and name_at < size
        end = header.index(b'\0', name_at)
        stem = header[name_at:end].decode('ascii')
        variants = []
        for j in range(0, length, 2):
            texture_id, texture_sectors, texture_at = struct.unpack_from('<hhI', header, variants_at + 8 * j)
            model_id, model_sectors, model_at = struct.unpack_from('<hhI', header, variants_at + 8 * (j + 1))
            assert texture_id == model_id and texture_sectors > 0 and model_sectors > 0
            assert texture_at + texture_sectors == model_at
            assert (model_at + model_sectors) * 2048 <= data_size
            variants.append({'id': texture_id, 'texture_sector': texture_at,
                             'texture_sectors': texture_sectors,
                             'model_sector': model_at, 'model_sectors': model_sectors})
        groups.append({'stem': stem, 'variants': variants})
    return groups


def selection_variants(entries, select2):
    """Assert the complete body/style/letter table in one disc selection lump."""
    checked = 0
    for index, code in enumerate(ref.BODY_CODES):
        body = {int(m[1]) for name in entries
                if (m := re.fullmatch(rf'{code}_bodyv(\d+)\.tex', name))}
        assert body == set(range(1, BODY_TEXTURES[index] + 1)), (code, 'body', body)
        body_meshes = {int(m[1]) for name in entries
                       if (m := re.fullmatch(rf'{code}_bodyv(\d+)\.vif', name))}
        assert body_meshes == body, (code, 'body meshes', body_meshes, body)
        for part, limit in (('hair', HAIR_STYLES[index]), ('beard', BEARD_STYLES[index])):
            meshes = {(int(m[1]), m[2]) for name in entries
                      if (m := re.fullmatch(rf'{code}_{part}(\d+)([a-z])\.vif', name))}
            expected = set(range(1, limit + 1))
            if code == 'vm' and part == 'hair' and select2:
                expected = {1, 3, 4}
            letters = 'a' if code == 'vm' else 'abc'
            assert meshes == {(style, letter) for style in expected for letter in letters}, (
                code, part, meshes, expected)
            textures = {(int(m[1]), m[2]) for name in entries
                        if (m := re.fullmatch(rf'{code}_{part}(\d+)([a-z])\.tex', name))}
            assert textures == {(style, letter) for style in expected for letter in letters}, (
                code, part, textures)
        checked += 1
    return checked


def mask_initialization(elf, seed):
    cases = 0
    for counter in (0, 0x110, 0x111, 0x112):
        ee = EE(elf)
        ee.mem.auto_map = True
        obj = ee.alloc(0x590)
        body = ee.alloc(16)
        ee.mem.w32(obj + 0x544, body)
        ee.mem.w32(0x41b514, counter)
        ee.mem.w32(0x404464, seed)
        ee.stub(0x179550, ret=0x12345678)
        ee.r[4] = obj
        ee.r[5] = 0
        assert ee.run(0x1a3580, until=(0x1a3604,)) == 'stop'
        calls = [call for call in ee.calls if call.target == 0x179550]
        assert len(calls) == int(counter >= 0x111), (counter, calls)
        if calls:
            assert calls[0].args[:2] == (body, 1), (counter, calls[0])
        assert ee.mem.u64(obj + 0x220) == (0x12345678 if calls else 0xffffffffffffffff)
        assert ee.mem.u32(0x404464) == seed
        cases += 1
    return cases


def draw_gates(elf, seed):
    """Run original equipment-state and final hair/beard branches in isolation."""
    cases = 0
    for model in range(12):
        for prior in (False, True):
            for slot, name, resource in ((11, 'circlet', 'cloth1'),
                                     (11, 'other', 'cloth1'),
                                     (11, 'circlet', 'other'),
                                     (4, 'chain', 'chainbody'),
                                     (4, 'other', 'chainbody'),
                                     (4, 'chain', 'other'),
                                     (0, 'other', 'other')):
                ee = EE(elf)
                ee.mem.auto_map = True
                record, item, definition = ee.alloc(0x4c30), ee.alloc(0x50), ee.alloc(0x40)
                name_at, resource_at = ee.alloc(32), ee.alloc(32)
                ee.mem.write(name_at, name.encode() + b'\0')
                ee.mem.write(resource_at, resource.encode() + b'\0')
                ee.mem.w32(definition, name_at)
                ee.mem.w32(definition + 0x30, resource_at)
                ee.mem.w8(definition + 0x1c, slot)
                ee.mem.w32(item, definition)
                ee.mem.w32(record + 0x54, model)
                ee.mem.w32(0x404464, seed)
                ee.r[18], ee.r[21], ee.r[22] = item, record, int(prior)
                assert ee.run(0x1a3ba0, until=(0x1a3cd0,)) == 'stop'
                want = ref.draw_cover_state(model, slot, name, resource, prior)
                assert bool(ee.r[22]) == want, (model, slot, name, resource, prior, ee.r[22], want)
                assert ee.mem.u32(0x404464) == seed
                cases += 1
    for model in range(12):
        for skin, cover, head_name, hair_handles, beard_handles in (
                (0, False, None, True, True),
                (0, True, None, True, True),
                (4, True, None, True, True),
                (3, True, 'leatherhelmet', True, True),
                (0, True, 'other', True, True),
                (0, False, None, False, True),
                (0, False, None, True, False)):
            ee = EE(elf)
            ee.mem.auto_map = True
            obj, record = ee.alloc(0x590), ee.alloc(0x4c30)
            ee.mem.w32(record + 0x54, model)
            ee.mem.w8(record + 0x23, skin)
            ee.mem.w32(0x404464, seed)
            body, hair, beard = ee.alloc(16), ee.alloc(16), ee.alloc(16)
            for off, value in ((0x544, body), (0x548, hair if hair_handles else 0),
                               (0x558, hair if hair_handles else 0),
                               (0x54c, beard if beard_handles else 0),
                               (0x554, beard if beard_handles else 0)):
                ee.mem.w32(obj + off, value)
            if head_name is not None:
                item, definition, name_at = ee.alloc(0x50), ee.alloc(0x40), ee.alloc(32)
                ee.mem.write(name_at, head_name.encode() + b'\0')
                ee.mem.w32(definition, name_at)
                ee.mem.w32(item, definition)
                ee.mem.w32(record + 0x441c, item)
            ee.r[19], ee.r[21], ee.r[22] = obj, record, int(cover)
            ee.stub(0x1797d8)
            ee.stub(0x178c28)
            assert ee.run(0x1a3e08, until=(0x1a3f34,)) == 'stop'
            allowed_hair, allowed_beard = ref.draw_appearance_gates(model, skin, cover, head_name)
            got = [call.args[0] for call in ee.calls if call.target == 0x178c28]
            want = ([hair] if allowed_hair and hair_handles else []) + (
                [beard] if allowed_beard and beard_handles else [])
            assert got == want, (model, skin, cover, head_name, got, want)
            assert ee.mem.u32(0x404464) == seed
            cases += 1
    return cases


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
        variants = sum(selection_variants(entries[lump], lump == 'select2.lmp') for lump in entries)
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
    mask_cases = sum(mask_initialization(elf, seed) for seed in (20973, 7))
    gate_cases = sum(draw_gates(elf, seed) for seed in (20973, 7))
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
          f'{variants} complete variant rows; {mask_cases} mask and {gate_cases} draw-gate cases; '
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
