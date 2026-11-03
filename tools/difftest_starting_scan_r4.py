#!/usr/bin/env python3
"""Cold starting armor loaded by the original scanner; host-backed private I/O.

No direct cache calls, fixup calls, or original instruction patches. This is a
bounded scanner fixture, not a complete player constructor or level transition.
"""
import hashlib
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest
from difftest_loading import SHA256
from difftest_starting_equipment_r4 import (
    CACHES, RECORD, Media, R, formatter, generic_weapon, initialized,
    load_headers, metadata_model, model_model, require_local, texture_model,
)


def cold_scan(path, folder, tables, body):
    e, equipped, _ = initialized(path, tables, body, 20973)
    media = Media(folder)
    load_headers(e, media)
    generic_weapon(e, media, tables, equipped)
    expected = {}
    for slot, cache in CACHES.items():
        name = formatter(e, body, slot, equipped[slot])
        metadata = metadata_model(e, name, 0)
        assert metadata
        begin = e.mem.u32(metadata + 4)
        split = (e.mem.u32(metadata + 12) - begin) * 0x800
        size = split + e.mem.s16(metadata + 10) * 0x800
        assert 0 < split < size
        base = e.alloc(size + 32)
        e.mem.write(base, bytes(size + 32))
        e.mem.w32(cache, base)
        e.mem.w32(cache + 4, size)
        assert e.mem.u16(cache + 8) == e.mem.u16(cache + 10) == 0
        expected[cache] = (base, size, begin * 0x800, split)
    player = e.alloc(0x600)
    e.mem.w32(player + 0x3C8, 0)
    e.mem.w32(0x4F85B0, 1)
    before_record = e.mem.read(RECORD, 0x4C30)
    submissions, payloads, seen = [], {}, []

    def submit(m):
        cache = m.mem.u32(0x4EF3EC)
        assert cache in expected and cache not in payloads
        base, size, offset, split = expected[cache]
        assert tuple(m.r[4:9]) == (0x535D30, base, 0x4EF3E8, size, offset)
        source = media.file(m, m.r[4])
        assert offset + size <= source.stat().st_size
        with source.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(size)
        assert len(data) == size
        m.mem.write(base, data)
        m.mem.w8(0x4EF3E8, 0)
        transformed = texture_model(data, base)
        transformed[split:] = model_model(transformed[split:], base + split)
        payloads[cache] = (data, bytes(transformed))
        submissions.append(cache)
        return 0

    e.stub(0x1729E8, function=submit)
    e.hook(0x1A2D48, lambda m: seen.append(m.r[5]))
    start = len(e.calls)
    pending = 0
    # One scan requests, later scans submit and publish. Every read is withheld
    # for an extra scan before host completion to check the incomplete control.
    for step in range(24):
        e.mem.w32(0x44FDD0, 100 + step * 4)
        seen.clear()
        ready = e.call(0x1A30B0, player)
        assert seen == list(CACHES.values()), 'scan order mismatch'
        assert e.mem.read(RECORD, 0x4C30) == before_record
        if ready == 0:
            break
        assert ready == 1
        pending += 1
        cache = e.mem.u32(0x4EF3EC)
        if cache in payloads and not e.mem.u8(0x4EF3E8):
            base, size, _offset, _split = expected[cache]
            raw, _transformed = payloads[cache]
            assert e.mem.read(base, size) == raw
            assert e.call(0x1A30B0, player) == 1
            assert e.mem.read(base, size) == raw
            assert e.mem.u16(cache + 10) == 0
            e.mem.w8(0x4EF3E8, 1)
    else:
        raise AssertionError('bounded scanner did not become ready')
    assert submissions == list(CACHES.values()), 'cold submission order mismatch'
    assert e.mem.u32(0x4EF3EC) == 0
    for cache, (base, size, _offset, _split) in expected.items():
        assert e.mem.u16(cache + 10) == 1
        assert e.mem.read(base, size) == payloads[cache][1]
        assert e.mem.read(base + size, 32) == bytes(32)
    calls = e.calls[start:]
    assert {c.target for c in calls if c.stubbed} == {0x1729E8}
    assert [c.target for c in calls if c.target in (0x179E10, 0x179130)] == [0x179E10, 0x179130] * 3
    before = len(e.calls)
    assert e.call(0x1A30B0, player) == 0
    assert not any(c.target in (0x1729E8, 0x179E10, 0x179130) for c in e.calls[before:])
    assert e.mem.read(RECORD, 0x4C30) == before_record
    assert not e.patches and e.follow is None
    return pending, sum(v[1] for v in expected.values())


def main():
    path, folder = sys.argv[1:3]
    require_local(path)
    require_local(folder)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    tables = R.Tables(path)
    pending = compared = 0
    for body in range(12):
        waits, size = cold_scan(path, folder, tables, body)
        pending += waits
        compared += size
        print('PASS cold_scanner body=%d armor_pairs=3 pending_scans=%d' % (body, waits))
    print('PASS cold_scanner bodies=12 armor_pairs=36 incomplete_controls=36 pending_scans=%d bytes_compared=%d' % (pending, compared))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (type(error).__name__, getattr(error, 'addr', 0)))
        sys.exit(1)
