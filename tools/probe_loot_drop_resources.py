#!/usr/bin/env python3
"""Run a disc-placed Chest's original constructor and opening animation in EE.

Assets and decoded mappings stay in memory, or in an explicitly ignored local
report. Renderer, sound, final loot generation and the rest of the level are
outside this probe. This is interpreter execution, not a PCSX2 capture.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE))
import difftest_items as items  # noqa: E402
from ee_emu import float_to_raw  # noqa: E402
import gob  # noqa: E402

spec = importlib.util.spec_from_file_location('loot_disc', HERE / 'recomp' / 'disc.py')
disc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disc)


def read_at(iso, entry, offset=0, size=None):
    iso.f.seek(entry['lba'] * disc.SECTOR + offset)
    return iso.f.read(entry['size'] - offset if size is None else size)


def text(data, offset):
    return data[offset:data.index(b'\0', offset)].decode('latin1')


def records(data):
    count, flags, strings = struct.unpack_from('<hHi', data)
    if count < 0 or flags & 3 or not 8 <= strings <= len(data):
        raise ValueError('unsupported placement header')
    at = 8
    for index in range(count):
        name, size, angle, x, y, z = struct.unpack_from('<ihh3f', data, at)
        if size < 24 or at + size > strings:
            raise ValueError('invalid placement record')
        properties = []
        for offset in range(at + 20, at + size, 4):
            pointer = struct.unpack_from('<i', data, offset)[0]
            if not pointer:
                break
            properties.append(text(data, strings + pointer))
        yield {'index': index, 'offset': at, 'class': None if name < 0 else text(data, strings + name),
               'angle': angle, 'position': (x, y, z), 'properties': properties}
        at += size


def sample(iso, index, prefix, placement_member):
    for path, archive in sorted(index.items()):
        if not path.endswith('.gob'):
            continue
        directory = gob.gob_entries(read_at(iso, archive, size=0x800))
        level = Path(path).stem + '.lmp'
        placed = next((entry for entry in directory if entry[0].lower() == level), None)
        if placed is None:
            continue
        lump = read_at(iso, archive, placed[1], placed[2])
        ob = next((entry for entry in gob.lmp_entries(lump)
                   if entry[0].lower() == placement_member.lower()), None)
        if ob is None:
            continue
        data = lump[ob[1]:ob[1] + ob[2]]
        for record in records(data):
            if record['class'] is not None and record['class'].lower().startswith(prefix.lower()):
                return path, archive, directory, record
    raise ValueError('no placed record matches the addressed factory prefix')


def run(elf, iso_path, seed):
    original = items.Original(elf, fast=True)
    emu = original.emu
    emu.record_calls = True
    iso = disc.Iso(iso_path)
    private = {}
    try:
        directory_index = {name.lower(): entry for name, entry in iso.walk()}
        placement_member = emu.mem.cstr(0x53f010)
        path, archive, directory, placed = sample(
            iso, directory_index, emu.mem.cstr(0x532f70), placement_member)
        resource_directory = Path(path).parent
        private.update(archive=path, record=placed)
        cache, blobs, sizes = {}, {}, {}

        def resource(lump_name, entry_name):
            key = (lump_name.lower(), entry_name.lower())
            if key in cache:
                return cache[key]
            lump = blobs.get(key[0])
            if lump is None:
                local_entry = next((entry for entry in directory if entry[0].lower() == key[0]), None)
                if local_entry:
                    lump = read_at(iso, archive, local_entry[1], local_entry[2])
                else:
                    standalone = directory_index.get((resource_directory / key[0]).as_posix())
                    if standalone is None:
                        raise ValueError('addressed resource lump is absent in the selected level and disc directory')
                    lump = read_at(iso, standalone)
                blobs[key[0]] = lump
            entry = next((entry for entry in gob.lmp_entries(lump) if entry[0].lower() == key[1]), None)
            if entry is None:
                raise ValueError('addressed resource entry is absent')
            data = lump[entry[1]:entry[1] + entry[2]]
            address = emu.alloc(len(data) + 16)
            emu.mem.write(address, data)
            if key[1].endswith('.anm'):
                # Original relocation; do not inline or publish the clip bytes.
                saved_follow = emu.follow
                emu.follow = set()
                emu.call(0x1707b8, address)
                emu.follow = saved_follow
            cache[key] = address
            sizes[key] = len(data)
            return address

        # Preload all descriptor resources outside the call hooks: EE.call is
        # intentionally not nested inside a running EE.call.
        descriptor = emu.mem.u32(0x501698)
        lump_name = emu.mem.cstr(emu.mem.u32(descriptor))
        bound = []
        for offset in (8, 16, 24):
            entry_name = emu.mem.cstr(emu.mem.u32(descriptor + offset))
            bound.append(resource(lump_name, entry_name))
        emu.mem.w32(descriptor + 4, emu.mem.u32(0x41bf78))
        for offset, address in zip((12, 20, 28), bound):
            emu.mem.w32(descriptor + offset, address)

        # Original string/property logic, base object, handles, run-list changes,
        # model mask and animation core execute. Rendering/loot/audio are calls.
        for address in (0x214230, 0x100d54, 0x1779b0, 0x1762e8,
                        0x14dcc8, 0x14bce0):
            emu.stub(address)
        emu.stub(0x17365c, ret=0)  # only audio; Chest's descriptor is already resolved
        emu.call(0x1a17d0)
        obj, pos = emu.alloc(0x88), emu.alloc(12)
        for component, value in enumerate(placed['position']):
            emu.mem.w32(pos + 4 * component, float_to_raw(value))
        class_name = emu.alloc(len(placed['class']) + 1)
        emu.mem.write(class_name, placed['class'].encode('latin1') + b'\0')
        props = emu.alloc(4 * (len(placed['properties']) + 1))
        for index, value in enumerate(placed['properties']):
            address = emu.alloc(len(value) + 1)
            emu.mem.write(address, value.encode('latin1') + b'\0')
            emu.mem.w32(props + 4 * index, address)
        emu.mem.w32(items.G_SEED, seed)
        emu.mem.w32(items.G_LEVEL, float_to_raw(22))  # synthetic roll context; placement is real
        emu.mem.w32(items.G_NUM_PLAYERS, 1)
        emu.mem.write(0x41b721, Path(path).stem.encode('latin1') + b'\0')
        emu.stub(0x14fdb8, function=lambda m: obj if m.r[4] == 0x88 else 0)
        emu.call(0x159c94, class_name, pos, placed['angle'], props)
        assert emu.mem.u32(obj + 0x24) == descriptor
        assert emu.mem.u32(obj + 0x48) == 0x5118d8
        assert emu.mem.u8(obj + 0x59) == 0
        trap = emu.mem.u8(obj + 0x58)
        emu.call(0x292a2c, obj, 0)
        assert emu.mem.u32(obj + 0x64) == bound[2]  # first animation track's clip pointer
        assert emu.mem.u32(obj + 0x84) == 1
        if trap:
            raise ValueError('selected seeded Chest is trapped; explosion is outside this probe')
        length = emu.mem.s32(bound[2] + 4)
        frames = 0
        while emu.mem.u32(obj + 0x84) != 2 and frames < length + 2:
            emu.mem.w32(0x44fdcc, frames)
            emu.call(0x2923a8, obj)
            frames += 1
        assert emu.mem.u32(obj + 0x84) == 2
        emu.call(0x29288c, obj)
        drawn = [call for call in emu.calls if call.target == 0x1779b0][-1]
        assert drawn.args[:2] == tuple(bound[:2])
        for address in (0x159c94, 0x292030, 0x14cb10, 0x170838, 0x1709d8):
            if address == 0x159c94:  # direct entry is not a child CallRecord
                continue
            assert any(call.target == address and not call.stubbed for call in emu.calls), hex(address)
        private.update(seed=seed, synthetic_level=22, descriptor=descriptor,
                       animation_length=length, run_calls=frames, opened=2,
                       rendered=False)

        # A real parsed starting descriptor supplies an equipment resource row.
        # Both full constructors and their original model/rigid-body functions
        # execute, with archive lookup provided by the owner disc at run time.
        item = emu.alloc(0x48)
        emu.call(0x1069b8, 0x537430, item, 0, 0)
        row = emu.call(0x1083f8, item)
        table = 0x3e9ce0 + 16 * row
        lump_name = emu.mem.cstr(0x520030)
        names = [emu.mem.u32(table + offset) for offset in (0, 4)]
        handles = [resource(lump_name, emu.mem.cstr(name)) for name in names]

        def find_loaded(m):
            key = (m.mem.cstr(m.r[4]).lower(), m.mem.cstr(m.r[5]).lower())
            return cache.get(key, 0)  # absent sound entries stay outside the probe

        emu.stub(0x17365c, function=find_loaded)
        for entry, size in ((0x155a0c, 0x248), (0x1590ec, 0x190)):
            prop = emu.alloc(size)
            before = emu.mem.u32(items.G_SEED)
            if entry == 0x155a0c:
                emu.call(entry, prop, pos, 0x520030, *names, 1, 0x441, item, fargs=(1,))
                assert emu.mem.u8(prop + 0x238) == 1
                assert emu.mem.u32(prop + 0x190) == float_to_raw(1)
            else:
                emu.call(entry, prop, pos, item, 0)  # original inventory-drop call's flags
            assert [emu.mem.u32(prop + offset) for offset in (0x4c, 0x50)] == handles
            assert emu.mem.read(prop + 0x148, 0x48) == emu.mem.read(item, 0x48)
            assert emu.mem.u32(items.G_SEED) == (before * 0x19660d + 0x3c6ef35f) & 0xffffffff
        assert any(call.target == 0x179400 and not call.stubbed for call in emu.calls)
        assert any(call.target == 0x1682f0 and not call.stubbed for call in emu.calls)
        private['equipment_resource_row'] = row
        private['resources'] = [{'lump': key[0], 'entry': key[1], 'address': value,
                                 'size': sizes[key]} for key, value in cache.items()]
        return private
    finally:
        iso.f.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--iso', required=True)
    parser.add_argument('--seed', type=int, choices=(20973, 7), required=True)
    parser.add_argument('--private-report', required=True)
    args = parser.parse_args()
    destination = Path(args.private_report).resolve()
    local = HERE.parent / 'local'
    if not destination.is_relative_to(local):
        parser.error('decoded reports must be inside this worktree local directory')
    with open(args.elf, 'rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != items.EXPECTED_SHA256:
            parser.error('expected pinned US v2.00 executable')
    result = run(args.elf, args.iso, args.seed)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS disc-placed Chest: original factory, constructor, resource bindings and opening; '
          '%d run calls; seed %d; descriptor %#x' % (result['run_calls'], args.seed, result['descriptor']))
    print('PASS disc-backed PhProp/ItemProp construction, original bounds and rigid-body initialization; '
          'equipment resource row %d' % result['equipment_resource_row'])


if __name__ == '__main__':
    main()
