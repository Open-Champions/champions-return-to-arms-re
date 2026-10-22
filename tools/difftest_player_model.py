#!/usr/bin/env python3
"""Compare Player_ctor resource requests to ref_player_model and US v2.00 disc.

Usage: python3 tools/difftest_player_model.py [SLUS_209.73] [disc.iso]
The executable and disc are read only. Tests use authored player records.
"""
import mmap
import json
import hashlib
import os
import sys

from ee_emu import EE
from ps2elf import Elf
from anim_audio_info import iso_files, lmp_entries
import ref_player_model as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELF = os.path.join(ROOT, 'local', 'SLUS_209.73')
DISC = os.path.expanduser('~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')
RECORD = 0x4d8af0
EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def cstr(mem, addr):
    return mem.read(addr, 96).split(b'\0', 1)[0].decode('ascii')


def run_ctor(path, index, appearance, select2, seed, manifest, flag_select2=False):
    emu = EE(path)
    # Run the game's formatter and its library helpers; isolate unrelated world
    # setup. The lookup callback records the name at the moment of the call.
    emu.follow = set(range(0x3a0000, 0x3c3000, 4))
    emu.mem.auto_map = True
    obj, pos = emu.alloc(0x590), emu.alloc(12)
    emu.mem.w32(RECORD + 0x54, index)
    emu.mem.write(RECORD + 0x20, bytes(v & 255 for v in appearance))
    emu.mem.w32(0x4d8ae0, 1 if flag_select2 else (2 if select2 else 1))
    emu.mem.store(0x506040, 1, int(flag_select2))
    emu.mem.w32(0x404464, seed)
    found = []

    def lookup(e):
        lump, name = cstr(e.mem, e.r[4]), cstr(e.mem, e.r[5])
        found.append((lump, name))
        return 0x100000 + len(found) * 0x100 if name in manifest[lump] else 0

    emu.stub(0x17365c, function=lookup)
    emu.call(0x1a1d28, obj, pos, 0, 0, 0, max_steps=1000000)
    ctor = next(c for c in emu.calls if c.site == 0x1a1db4)
    handles = tuple(emu.mem.u32(obj + off) for off in (0x544, 0x548, 0x54c, 0x550, 0x554, 0x558))
    return ctor.args[4], found, handles, emu.mem.u32(0x404464)


def check(path, disc, manifest_out=None):
    with open(path, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable revision'
    elf = Elf(path)
    export = []
    with open(disc, 'rb') as source:
        image = mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ)
        files = iso_files(image)
        manifests = {}
        for name in set(R.ANIM_LUMPS) | {'select.lmp', 'select2.lmp'}:
            key = '/BG/DATA/' + name.upper()
            off, size, _ = files[key]
            manifests[name] = {entry.lower() for entry, _, _ in lmp_entries(image[off:off + size])}

        cases = 0
        for seed in (20973, 7):
            for index in range(12):
                definition = elf.u32(0x4ef330 + index * 4)
                assert elf.cstr(elf.u32(0x4ebbb8 + index * 4)) == R.BODY_CODES[index]
                assert elf.cstr(elf.u32(definition)) == R.ANIM_LUMPS[index]
                clips = [elf.cstr(elf.u32(definition + 8 * slot)) for slot in range(1, 112)]
                assert elf.u32(definition + 112 * 8) == 0
                assert all(name and (name.endswith('.anm') or name == 'silent.vag') for name in clips)
                assert all(name in manifests[R.ANIM_LUMPS[index]] for name in clips if name.endswith('.anm'))
                if seed == 20973:
                    export.append({'model_index': index, 'class_index': R.CLASS_INDEX[index],
                                   'body_code': R.BODY_CODES[index], 'animation_lump': R.ANIM_LUMPS[index],
                                   'animation_table_address': f'0x{definition:08x}',
                                   'clip_slots_1_to_111': clips,
                                   'default_body_model': f'{R.BODY_CODES[index]}_bodyv1.vif'})
                # No part, normal hair, optional beard, alternate texture and
                # SELECT2 selection. Invalid beard entries legitimately return 0.
                for appearance, select2, flag in (((-1, 0, -1, 0), False, False),
                                                  ((0, 0, 0, 0), False, False),
                                                  ((1, 1, -1, 1), True, False),
                                                  ((-1, 0, -1, 0), True, True)):
                    definition_run, got, handles, seed_after = run_ctor(path, index, appearance, select2, seed, manifests, flag)
                    expected = R.requests(index, appearance, select2)
                    assert definition_run == definition, (index, hex(definition_run), hex(definition))
                    assert got == [(lump, name) for lump, name, _ in expected], (index, got, expected)
                    expected_handles = dict.fromkeys((0x544, 0x548, 0x54c, 0x550, 0x554, 0x558), 0)
                    for number, (lump, name, off) in enumerate(expected, 1):
                        if name in manifests[lump]:
                            expected_handles[off] = 0x100000 + number * 0x100
                    assert handles == tuple(expected_handles.values()), (index, handles, expected_handles)
                    assert seed_after == seed
                    cases += 1
        image.close()
    if manifest_out:
        with open(manifest_out, 'w', encoding='utf-8') as out:
            json.dump({'source': 'SLUS-20973 v2.00; generated from local executable',
                       'models': export}, out, indent=2)
            out.write('\n')
    print(f'PASS player model: {cases} constructor cases; 12 animation tables; seeds 20973 and 7')


if __name__ == '__main__':
    if '--manifest' in sys.argv:
        i = sys.argv.index('--manifest')
        manifest_path = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    else:
        manifest_path = None
    check(sys.argv[1] if len(sys.argv) > 1 else ELF,
          sys.argv[2] if len(sys.argv) > 2 else DISC,
          manifest_path)
