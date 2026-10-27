#!/usr/bin/env python3
"""Round-two original arrival probes. Synthetic fixtures; output is counts only."""
import hashlib
import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from difftest_loading_readiness import machine
from difftest_loading import SHA256
from difftest_amx import Original
from ref_amx import Machine, assemble, build_image
from ee_emu import EmuError


def deferred_errors(path):
    cases = 0
    for first in (b'absent', b'failure', b'bounded', b'division', b'good'):
        for error in (0, 4, 27, -1):
            code, labels = assemble([
                ('PROC',), ('CONST.pri', 9), ('HALT', error),
                'good:', ('PROC',), ('CONST.pri', 73), ('STOR.pri', 0), ('HALT', 0),
                'bounded:', ('PROC',), ('CONST.pri', 9), ('BOUNDS', 0), ('HALT', 0),
                'division:', ('PROC',), ('CONST.pri', 9), ('ZERO.alt',), ('SDIV',), ('HALT', 0)])
            image = build_image(code, [0] * 16,
                                [('failure', 0), ('good', labels['good']),
                                 ('bounded', labels['bounded']), ('division', labels['division'])], (), 256)
            original = Original(path)
            original.place(image)
            assert original.load() == 0
            model = Machine(image)
            model.load()
            e = original.emu
            e.record_calls = True
            e.mem.write(0x86B278, first + b'\0')
            e.mem.write(0x86B2C8, b'good\0')
            e.mem.w32(0x86DA78, 2)
            e.mem.w32(0x86DA7C, 1)
            model.call(first)
            model.call(b'good')
            original.call(0x1EDA24)
            assert e.mem.u32(original.base + 0x60 + model.dat) == model.cell(0) == 73
            assert e.mem.u32(0x86DA78) == 1
            assert e.mem.u32(0x86DA7C) == 0
            assert e.mem.u32(0x4F8690) == 1
            assert sum(c.target == 0x1ED694 for c in e.calls) == 2
            cases += 1
    return cases


def io_completion(path):
    cases = 0
    for streaming, busy, error in ((0, 1, 0), (0, 0, 1), (0, 0, 0), (1, 0, 0)):
        e = machine(path)
        done = e.alloc(4)
        e.mem.w32(0x7C25C0, done)
        e.mem.w8(0x41BF90, 1)
        e.mem.w8(0x41BF91, streaming)
        e.mem.w32(0x41BF98, 0x1000)
        e.mem.w32(0x41BF94, e.alloc(0x2000))
        e.stub(0x3618B0, ret=busy)
        e.stub(0x362938, ret=error)
        e.stub(0x362E28, ret=2)
        e.call(0x172CA8)
        completed = bool(streaming or (not busy and not error))
        assert e.mem.u8(done) == int(completed)
        assert e.mem.u8(0x41BF90) == int(not completed)
        assert any(c.target == 0x172098 for c in e.calls) == bool(not streaming and not busy and error)
        cases += 1
    # Original submission stores destination, sector range, completion pointer and clears flag.
    e = machine(path)
    name, buffer, done = e.alloc(16), e.alloc(0x4000), e.alloc(4)
    e.mem.write(name, b'synthetic\0')
    e.mem.w8(done, 1)
    def lookup(m):
        m.mem.w32(m.r[5], 100)
        m.mem.w32(m.r[6], 0x1800)
        return 1
    e.stub(0x1724FC, function=lookup)
    e.call(0x1729E8, name, buffer, done, 0x801, 0x1000)
    assert e.mem.u32(0x7C25C0) == done and e.mem.u8(done) == 0
    assert [e.mem.u32(0x7C25B0 + i * 4) for i in range(4)] == [1, 102, 2, buffer]
    assert e.mem.u8(0x41BF90) == 1
    return cases + 1


def cache_publication(path):
    cases = 0
    for done in (0, 1):
        e = machine(path)
        e.follow = {0x3B8534, 0x3B868C}
        cache, name = e.alloc(0x58), e.alloc(32)
        out_a, out_b = e.alloc(4), e.alloc(4)
        base = e.alloc(0x100)
        e.mem.write(name, b'synthetic_model\0')
        e.mem.write(0x8667A8, b'synthetic_model\0')
        e.mem.w32(cache, base)
        e.mem.w32(cache + 0x4C, 0x80)
        e.mem.w16(cache + 8, 1)
        e.mem.w32(0x4EF3EC, cache)
        e.mem.w32(0x44FDD0, 4)
        e.mem.w8(0x4EF3E8, done)
        assert e.call(0x1A2D48, name, cache, out_a, out_b) == 0
        assert e.mem.u32(out_a) == e.mem.u32(out_b) == 0
        assert e.mem.u16(cache + 10) == done
        assert e.mem.u32(0x4EF3EC) == (0 if done else cache)
        fixups = [c for c in e.calls if c.target in (0x179E10, 0x179130)]
        assert [c.args[0] for c in fixups] == ([base, base + 0x80] if done else [])
        if done:
            assert e.call(0x1A2D48, name, cache, out_a, out_b) == 1
            assert (e.mem.u32(out_a), e.mem.u32(out_b)) == (base + 0x80, base)
        cases += 1
    return cases


def specialized_slots(path):
    cases = 0
    slots = {3: 0x866648, 4: 0x8659E8, 9: 0x865CA8, 10: 0x865B48,
             11: 0x865E08, 12: 0x865F68, 13: 0x8660C8}
    for index in (0, 1):
        for slot, address in slots.items():
            for ready in (False, True):
                e = machine(path)
                e.follow = {0x1A2D48, 0x3B8534, 0x3B8DC4}
                player, item, definition = e.alloc(0x400), e.alloc(0x48), e.alloc(0x40)
                record = 0x4D8AF0 + index * 0x4C30
                cache = address + index * 0x58
                e.mem.w32(player + 0x3C8, index)
                e.mem.w32(record + 0x43F0 + slot * 4, item)
                e.mem.w32(item, definition)
                e.mem.w8(definition + 0x1C, 1)
                e.mem.w32(definition + 0x30, 1)
                e.mem.w32(0x4F85B0, 1)
                e.mem.write(cache + 12, b'synthetic_model\0')
                e.mem.w16(cache + 10, int(ready))
                e.mem.w32(cache, 0x123400)
                e.mem.w32(cache + 0x4C, 0x80)
                e.mem.w32(0x4EF3EC, cache)
                e.mem.w32(0x44FDD0, 3)
                def filename(m):
                    m.mem.write(m.r[4], b'synthetic_model.ext\0')
                    return 0
                e.stub(0x107EDC, function=filename)
                assert e.call(0x1A30B0, player) == int(not ready)
                calls = [c for c in e.calls if c.target == 0x1A2D48]
                assert len(calls) == 1 and calls[0].args[1] == cache
                cases += 1
    return cases


def specialized_submission(path):
    cases = 0
    for flag54, flag56, identifier in ((1, 0, 0x535D10), (0, 1, 0x535D20), (0, 0, 0x535D30)):
        e = machine(path)
        cache, name, metadata = e.alloc(0x58), e.alloc(32), e.alloc(0x20)
        out_a, out_b = e.alloc(4), e.alloc(4)
        e.mem.write(name, b'synthetic_model\0')
        e.mem.w32(cache, e.alloc(0x4000))
        e.mem.w8(cache + 0x54, flag54)
        e.mem.w8(cache + 0x56, flag56)
        e.mem.w32(metadata + 4, 2)
        e.mem.w16(metadata + 10, 3)
        e.mem.w32(metadata + 12, 4)
        e.mem.w32(0x4EF3EC, cache)
        e.mem.w32(0x44FDD0, 4)
        e.stub(0x1A24E8, ret=metadata)
        e.call(0x1A2D48, name, cache, out_a, out_b)
        calls = [c for c in e.calls if c.target == 0x1729E8]
        assert len(calls) == 1
        assert calls[0].args[:5] == (identifier, e.mem.u32(cache), 0x4EF3E8, 0x2800, 0x1000)
        assert e.mem.u16(cache + 8) == 1 and e.mem.u16(cache + 10) == 0
        assert e.mem.u32(cache + 0x4C) == 0x1000
        cases += 1
    return cases


def slot_publication(path):
    cases = 0
    for index in (0, 1):
        for slot in (4, 9, 10, 11, 12, 13, 16):
            e = machine(path)
            item = e.alloc(0x48)
            record = 0x4D8AF0 + index * 0x4C30
            e.r[16], e.r[18], e.r[20], e.r[21] = record, item, slot * 4, 1
            assert e.run(0x1C2CE0, until=(0x1C2ED8,), max_steps=20) == 'stop'
            assert e.mem.u32(record + 0x43F0 + slot * 4) == item
            cases += 1
    return cases


def player_publication(path):
    cases = 0
    for index in (0, 1):
        for display_only in (0, 1):
            e = machine(path)
            player = e.alloc(0x600)
            e.mem.w8(player + 0x462, display_only)
            e.r[21], e.r[23], e.r[22], e.r[30] = player, index, 0x4D8AF0, 0x4C30
            assert e.run(0x1A21E8, until=(0x1A2220,), max_steps=100) == 'stop'
            assert e.mem.u32(player + 0x3C8) == index
            assert e.mem.u32(0x4DCEC8 + index * 0x4C30) == (0 if display_only else player)
            cases += 1
    return cases


def unbound_native(path):
    code, labels = assemble([('PROC',), ('PUSH.C', 0), ('SYSREQ.C', 0), ('HALT', 0),
                             'good:', ('PROC',), ('CONST.pri', 73), ('STOR.pri', 0), ('HALT', 0)])
    image = build_image(code, [0] * 16, [('failure', 0), ('good', labels['good'])], (b'unbound',), 256)
    original = Original(path)
    original.place(image)
    assert original.load() == 0
    e = original.emu
    e.mem.write(0x86B278, b'failure\0')
    e.mem.write(0x86B2C8, b'good\0')
    e.mem.w32(0x86DA78, 2)
    e.mem.w32(0x86DA7C, 1)
    try:
        original.call(0x1EDA24, max_steps=10000)
    except EmuError:
        assert e.pc == 0
    else:
        raise AssertionError('unbound handler unexpectedly returned')
    assert e.mem.u32(0x86DA78) == 2 and e.mem.u32(0x86DA7C) == 1
    assert e.mem.u32(0x4F8690) == 0
    return 1


def header_selection(path):
    cases = 0
    for players, override, identifier in ((1, 0, 0x535C08), (1, 1, 0x535BF8),
                                           (2, 0, 0x535BF8), (2, 1, 0x535BF8)):
        e = machine(path)
        e.mem.w32(0x4D8AE0, players)
        e.mem.w8(0x506040, override)
        assert e.run(0x1A2680, until=(0x1A26D0,), max_steps=100) == 'stop'
        assert e.r[17] == identifier
        cases += 1
    return cases


if __name__ == '__main__':
    path = sys.argv[1]
    with open(path, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA256
    for check in (deferred_errors, io_completion, cache_publication, specialized_slots, specialized_submission, slot_publication, player_publication, unbound_native, header_selection):
        print('PASS %s cases=%d' % (check.__name__, check(path)))
