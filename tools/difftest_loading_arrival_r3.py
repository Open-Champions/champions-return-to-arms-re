#!/usr/bin/env python3
"""Original resource transformations versus authored byte models; counts only."""
import hashlib
import os
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from difftest_loading_readiness import machine
from difftest_loading import SHA256


def word(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def put(data, offset, value):
    struct.pack_into('<I', data, offset, value & 0xffffffff)


def texture_model(data, base):
    """Authored model of 0x179e10; deliberately restricted to bounded valid input."""
    data = bytearray(data)
    if word(data, 0x1c):
        return data
    cursor = word(data, 0x10)
    flags = struct.unpack_from('<H', data, 8)[0]
    struct.pack_into('<H', data, 10, 0xa7fb)
    put(data, 0x1c, -1)
    put(data, 0x10, base + cursor)
    if flags & 1 or not flags & 0x100:
        return data
    put(data, cursor, base + word(data, cursor))
    cursor += 4
    total = 0x48
    while data[cursor] != 255:
        left, top, right, bottom = struct.unpack_from('<bbbb', data, cursor)
        cursor += 4
        area = (bottom - top + 1) * 0x800 * (right - left + 1)
        total += (area // 128 if area >= 0 else -((-area) // 128)) + 6
        for _ in range(max(0, bottom - top + 1) * max(0, right - left + 1)):
            put(data, cursor, base + word(data, cursor))
            cursor += 4
    struct.pack_into('<H', data, 6, total & 0xffff)
    return data


def model_model(data, base):
    """Authored model of 0x179130, including the signed-byte count fallback."""
    data = bytearray(data)
    count = struct.unpack_from('<b', data, 0x26)[0]
    if count <= 0:
        data[0x26] = count = 1
    width = struct.unpack_from('<b', data, 0x12)[0] + 1
    for i in range(max(0, count * width)):
        put(data, 0x28 + 4 * i, base + word(data, 0x28 + 4 * i))
    return data


def compare(e, address, data, reference):
    base = e.alloc(len(data) + 32)
    e.mem.write(base, bytes(data) + bytes(32))
    expected = bytes(reference(data, base))
    before = len(e.calls)
    e.call(address, base)
    assert not e.calls[before:], 'unexpected callee in leaf fixup'
    assert e.mem.read(base, len(data)) == expected
    assert e.mem.read(base + len(data), 32) == bytes(32)
    return base, expected


def transformations(path):
    count = 0
    e = machine(path)
    for flags in (0, 1, 0x100, 0x101):
        for relocated in (0, 1, 0xffffffff):
            for rectangle in ((0, 0, 0, 0), (1, 2, 3, 4)):
                data = bytearray(0x200)
                struct.pack_into('<H', data, 8, flags)
                put(data, 0x10, 0x40)
                put(data, 0x1c, relocated)
                put(data, 0x40, 0x180)
                struct.pack_into('<bbbb', data, 0x44, *rectangle)
                cells = (rectangle[2] - rectangle[0] + 1) * (rectangle[3] - rectangle[1] + 1)
                for i in range(cells):
                    put(data, 0x48 + 4 * i, 0x100 + 4 * i)
                data[0x48 + 4 * cells] = 255
                base, expected = compare(e, 0x179e10, data, texture_model)
                e.call(0x179e10, base)
                assert e.mem.read(base, len(data)) == expected  # guarded second call
                count += 1
    for signed_count in (-128, -1, 0, 1, 2, 7, 127):
        for field12 in (-1, 0, 5):
            data = bytearray(0x1000)
            data[0x12] = field12 & 255
            data[0x26] = signed_count & 255
            for i in range(max(1, signed_count) * max(0, field12 + 1)):
                put(data, 0x28 + 4 * i, 0x220 + i)
            base, expected = compare(e, 0x179130, data, model_model)
            # Unlike the texture transformation this function has no relocation guard.
            e.call(0x179130, base)
            assert e.mem.read(base, len(data)) == bytes(model_model(expected, base))
            count += 1
    return count


def private_resources(path, folder):
    """Read standalone private lumps; do not print identities or retain payloads."""
    from gob import lmp_entries
    e = machine(path)
    e.record_writes = False
    counts = {'.tex': 0, '.vif': 0}
    for lump in sorted(Path(folder).rglob('*')):
        if lump.suffix.lower() != '.lmp':
            continue
        data = lump.read_bytes()
        for name, offset, size in lmp_entries(data):
            kind = Path(name).suffix.lower()
            if kind not in counts:
                continue
            assert 0 <= offset <= offset + size <= len(data)
            e._heap = e.HEAP_LO  # reuse scratch memory, never write the input
            e.calls.clear()
            compare(e, 0x179e10 if kind == '.tex' else 0x179130,
                    data[offset:offset + size], texture_model if kind == '.tex' else model_model)
            counts[kind] += 1
    assert all(counts.values())
    return counts['.tex'], counts['.vif']


def publication(path):
    """Run cache lookup and both real transformations together, without fixup stubs."""
    for flags in (0, 0x100):
        e = machine(path)
        e.follow = {0x179e10, 0x179130, 0x3b8534, 0x3b868c}
        cache, name = e.alloc(0x58), e.alloc(32)
        first, second = e.alloc(4), e.alloc(4)
        data = bytearray(0x400)
        struct.pack_into('<H', data, 8, flags)
        put(data, 0x10, 0x40)
        put(data, 0x40, 0x180)
        put(data, 0x48, 0x100)
        data[0x4c] = 255
        data[0x212], data[0x226] = 1, 2
        for i in range(4):
            put(data, 0x228 + 4 * i, 0x80 + i * 0x10)
        base = e.alloc(len(data))
        e.mem.write(base, data)
        e.mem.write(name, b'authored_resource\0')
        e.mem.write(0x8667a8, b'authored_resource\0')
        e.mem.w32(cache, base)
        e.mem.w32(cache + 0x4c, 0x200)
        e.mem.w16(cache + 8, 1)
        e.mem.w32(0x4ef3ec, cache)
        e.mem.w32(0x4ef3f0, 100)
        e.mem.w32(0x44fdd0, 104)
        e.mem.w8(0x4ef3e8, 1)
        assert e.call(0x1a2d48, name, cache, first, second) == 0
        expected = texture_model(data, base)
        expected[0x200:] = model_model(expected[0x200:], base + 0x200)
        assert e.mem.read(base, len(data)) == bytes(expected)
        assert e.mem.u32(first) == e.mem.u32(second) == 0
        assert e.mem.u16(cache + 10) == 1 and e.mem.u32(0x4ef3ec) == 0
        fixups = [c.target for c in e.calls if c.target in (0x179e10, 0x179130)]
        assert fixups == [0x179e10, 0x179130]
        assert e.call(0x1a2d48, name, cache, first, second) == 1
        assert (e.mem.u32(first), e.mem.u32(second)) == (base + 0x200, base)
        assert e.mem.read(base, len(data)) == bytes(expected)
    return 2


if __name__ == '__main__':
    path = sys.argv[1]
    with open(path, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA256
    print('PASS transformations cases=%d' % transformations(path))
    print('PASS publication cases=%d' % publication(path))
    if len(sys.argv) == 3:
        textures, models = private_resources(path, sys.argv[2])
        print('PASS private resource comparisons textures=%d models=%d' % (textures, models))
