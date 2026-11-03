#!/usr/bin/env python3
"""Stage the arrival prefixes past the round-4 native boundaries.

Original handlers run in tools/ee_emu.py. An empty name table, a resident lump
and a one-entry cut are fixtures. Unsupported bodies stop before their first
instruction. Output is addresses, lengths and counts.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
import unittest
from difftest_amx import differences
from difftest_arrival_state_r4 import PERMITTED, REGIONS, prepared
from difftest_loading import SHA256
from difftest_loading_arrival_r4 import (
    FRONT, BACK, PARITY, TABLE, private_script, require_local,
)
from ref_amx import Machine
import ref_natives as N

NAMES, OBJECTS = 0x5F76F8, 0x5F7EF8
LUMPS, LUMP_COUNT = 0x7B9480, 0x41BF7C
LEVEL, CAMERA, NET = 0x41B721, 0x4F8450, 0x402791
VT_AUTOPROP = 0x5133C0
CD_FIND, HIDE_MASK = 0x1724FC, 0x179550
ENQUEUE, POST, IN_POST = 0x1ED52C, 0x86FA80, 0x4F8698
ROUTE0 = PERMITTED | {0x142320, 0x144160, 0x143534}
ROUTE0_ORDER = (0x1473B4, 0x1420D0, 0x1420A4, 0x142320, 0x144160, 0x143534,
                0x144160, 0x143500, 0x143540, 0x14598C)
ROUTE1_ORDER = (0x14222C, 0x143500, 0x143500, 0x144DB8, 0x144C00, 0x144C00,
                0x144C00, 0x143500, 0x143500, 0x143500, 0x143500, 0x143500,
                0x143500)
ROUTE2_ORDER = (0x142084, 0x142044, 0x1433C8, 0x1420D0, 0x143540, 0x143540,
                0x143EE4, 0x142010, 0x143500, 0x143F1C, 0x143540, 0x143EE4)
CUT_CALLS = (0x3B7EF0, 0x3B7EF0, 0x17365C, 0x19B4DC, 0x322934, 0x1EB000,
             0x19A62C, 0x18617C, 0x2072E8, 0x18619C, 0x3A59A8, 0x3A59A8,
             0x3A59A8, 0x19E4A0, 0x19E4A0)
CUT_WORDS = (
    (0x506048, 4, 10), (0x44FD2C, 4, 0), (0x44FD28, 4, 0), (0x44FCD2, 1, 0),
    (0x44FCFC, 4, 0), (0x44FD00, 4, 0), (0x44FCE0, 4, 1), (0x44FCD0, 1, 1),
    (0x44FCD1, 1, 1), (0x44FCEC, 1, 0), (0x44FCE8, 4, 0), (0x7D8A04, 4, 0x44E10000),
    (0x41B4FC, 4, 0x3C), (0x4F66A8, 1, 1), (0x83D198, 4, 0), (0x83D18C, 4, 0),
    (0x44FDB8, 4, 2),
)


class Boundary(Exception):
    def __init__(self, kind, address):
        self.kind, self.address = kind, address


class Services(N.Host):
    """Resident-lump and cutscene answers. Every other service stays refused."""

    def __init__(self, miss=False):
        N.Host.__init__(self)
        self.miss = miss
        self.header = 0x01002000

    def call(self, name, *args):
        if name == 'lump_load':
            if self.miss:
                raise Boundary('disc', CD_FIND)
            return 0
        if name == 'res_find':
            return self.header
        if name == 'cut_start':
            apply_cut(self.game.mem, self.header)
            return 0
        raise AssertionError('unestablished service %s' % name)


def apply_cut(mem, header):
    """Final stores of cut_start 0x19b4dc when header word bit 0x2 is clear."""
    mem.w32(0x44FCE4, header)
    mem.w32(0x506048, 10)
    mem.w32(0x506080, mem.u32(0x44FDD0))
    for address, size, value in CUT_WORDS:
        if size == 1:
            mem.w8(address, value)
        elif address != 0x506048:
            mem.w32(address, value)
    camera = mem.u32(CAMERA)
    if camera:
        mem.w32(camera + 0x34, 0)
    mem.w32(header, 0)


def amx_string(mem, base, data_off, address, limit=64):
    def cell(at):
        return mem.s32(base + data_off + at)

    out = bytearray()
    if cell(address) < 0x100:
        while len(out) < limit:
            value = cell(address)
            if value == 0:
                return bytes(out)
            out.append(value & 0xFF)
            address += 4
        return bytes(out)
    while len(out) < limit:
        value = cell(address) & 0xFFFFFFFF
        address += 4
        for shift in (24, 16, 8, 0):
            char = (value >> shift) & 0xFF
            if char == 0:
                return bytes(out)
            out.append(char)
    return bytes(out)


def data_off(image):
    machine = Machine(image)
    assert machine.load() == 0
    return machine.data_offset


def bind(o, image):
    e = o.emu
    e.mem.w32(0x4F719C, 1)
    e.mem.write(NAMES, bytes(512 * 4))
    e.mem.write(OBJECTS, bytes(512 * 4))
    e.mem.w32(LUMP_COUNT, 0)
    assert e.mem.u8(NET) == 0 and e.mem.u32(0x4DCEC8) == 0
    o.place(image)
    assert o.load() == 0
    assert o.call(0x141310, o.base, TABLE, 0xFFFFFFFF) == 0
    return o


def fresh(path, image, body, seed):
    return bind(prepared(path, body, seed), image)


def plant_lump(e, name, payload):
    assert 0 < len(name) < 16
    data = e.alloc(max(len(payload), 16))
    e.mem.write(data, payload)
    label = e.alloc(len(name) + 1)
    e.mem.write(label, name + b'\0')
    image = e.alloc(16)
    e.mem.w16(image, 1)
    e.mem.w32(image + 4, label)
    e.mem.w32(image + 8, data)
    e.mem.w32(image + 12, len(payload))
    e.mem.write(LUMPS, name + b'\0' + bytes(15 - len(name)))
    e.mem.w32(LUMPS + 0x10, image)
    e.mem.w32(LUMPS + 0x14, 0)
    e.mem.w32(LUMP_COUNT, 1)
    return data


def plant_prop(o, name, states):
    e = o.emu
    text = e.alloc(len(name) + 1)
    e.mem.write(text, name + b'\0')
    obj = e.alloc(0x198)
    e.mem.w32(obj + 0x0C, 0x10000000)
    e.mem.w32(obj + 0x48, VT_AUTOPROP)
    e.mem.w32(obj + 0x120, states)
    o.call(0x14BCE0, text, obj)
    return obj


def capture(o, image_off, address, entry):
    found = {}

    def grab(m):
        params = m.r[5] & 0xFFFFFFFF
        count = m.mem.s32(params)
        args = [m.mem.s32(params + 4 + i) for i in range(0, count, 4)]
        found['args'] = args
        found['text'] = amx_string(m.mem, o.base, image_off, args[0]) if args else b''
        raise Boundary('capture', address)

    o.emu.hooks.clear()
    o.emu.hook(address, grab)
    try:
        if entry is None:
            o.call(0x1EDAC0, max_steps=4000000)
        else:
            o.call(0x1ED694, entry, max_steps=4000000)
    except Boundary:
        return found
    raise AssertionError('capture missed 0x%x' % address)


def hook_natives(o, permit, stops, trace):
    e = o.emu
    e.hooks.clear()
    e.record_calls = True
    e.calls.clear()

    def observe(address):
        def run(m):
            params = m.r[5] & 0xFFFFFFFF
            count = m.mem.s32(params)
            assert 0 <= count <= 64 and count % 4 == 0
            args = tuple(m.mem.s32(params + 4 + i) for i in range(0, count, 4))
            trace.append((address, args))
            if address not in permit:
                raise Boundary('native', address)
        return run

    for index in range(191):
        if not e.mem.u32(TABLE + 8 * index):
            break
        e.hook(e.mem.u32(TABLE + 8 * index + 4), observe(e.mem.u32(TABLE + 8 * index + 4)))
    for address in stops:
        e.hook(address, lambda _m, address=address: (_ for _ in ()).throw(Boundary('callee', address)))


def model_for(image, o, permit, miss=False):
    model = Machine(image)
    assert model.load() == 0
    mem = N.Mem()
    for address, size in REGIONS:
        mem.write(address, o.emu.mem.read(address, size))
    mem.w32(0x44FDD0, o.emu.mem.u32(0x44FDD0))
    mem.w32(CAMERA, o.emu.mem.u32(CAMERA))
    mem.write(LEVEL, o.emu.mem.read(LEVEL, 16))
    host = Services(miss=miss)
    game = N.Game(mem, host=host)
    host.header = 0x01002000
    mem.w32(host.header, 0)
    game.machine = model
    natives = game.natives()
    expected = []

    def model_native(name, address):
        def run(vm, args):
            expected.append((address, tuple(args)))
            if address not in permit:
                raise Boundary('native', address)
            return natives[name](vm, args)
        return run

    bindings = {}
    e = o.emu
    for index in range(191):
        name_ptr = e.mem.u32(TABLE + 8 * index)
        address = e.mem.u32(TABLE + 8 * index + 4)
        if not name_ptr:
            break
        bindings[e.mem.cstr(name_ptr)] = model_native(e.mem.cstr(name_ptr), address)
    assert model.register(bindings) == 0
    return model, game, expected


def regions_match(o, mem):
    for address, size in REGIONS:
        assert o.emu.mem.read(address, size) == mem.read(address, size), 'region 0x%x' % address


def drive(o, model, game, permit, stops, expected):
    e = o.emu
    trace = []
    hook_natives(o, permit, stops, trace)
    phases = []
    for entry in (0x53F000, 0x53F020, None):
        first = len(trace)
        stopped = [False, False]
        results = [None, None]
        try:
            if entry is None:
                if not e.mem.u8(POST):
                    phases.append((entry, 'absent', None))
                    break
                game.run_post_action()
            else:
                results[0] = model.call(e.mem.cstr(entry))
        except Boundary:
            stopped[0] = True
        try:
            if entry is None:
                if phases and phases[-1][1] == 'absent':
                    break
                results[1] = o.call(0x1EDAC0, max_steps=8000000)
            else:
                results[1] = o.call(0x1ED694, entry, max_steps=8000000)
        except Boundary:
            stopped[1] = True
        assert stopped[0] == stopped[1], (entry, stopped, trace[first:], expected[first:])
        if entry is not None and not stopped[0]:
            assert results[0] == results[1], (entry, results[0], results[1])
        assert trace == expected
        assert not differences(o, model, len(model.image))
        regions_match(o, game.mem)
        assert not any(c.stubbed for c in e.calls) and not e.patches
        phases.append((entry, 'stop' if stopped[0] else 'return',
                       None if not trace[first:] else trace[-1][0]))
        if stopped[0]:
            return trace, phases
    return trace, phases


def queues(e):
    return tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY))


def word(mem, address, size):
    return mem.u8(address) if size == 1 else mem.u32(address)


def cut_matches(e, mem):
    assert e.mem.u32(0x506080) == e.mem.u32(0x44FDD0) == 0x400
    assert mem.u32(0x506080) == mem.u32(0x44FDD0) == 0x400
    for address, size, value in CUT_WORDS:
        assert word(e.mem, address, size) == value
        assert word(mem, address, size) == value
    camera = e.mem.u32(CAMERA)
    assert camera and e.mem.u32(camera + 0x34) == mem.u32(mem.u32(CAMERA) + 0x34) == 0
    header = e.mem.u32(0x44FCE4)
    assert header and e.mem.u32(header) == 0 and mem.u32(mem.u32(0x44FCE4)) == 0
    notable = tuple(c.target for c in e.calls if c.target in set(CUT_CALLS))
    assert notable == CUT_CALLS
    assert CD_FIND not in {c.target for c in e.calls}


def main():
    path, manifest = sys.argv[1:3]
    require_local(path)
    require_local(manifest)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    images = [private_script(p) for p in json.loads(Path(manifest).read_text())]
    assert len(images) == 3
    offs = [data_off(image) for image in images]
    cases = 0
    for body in (0, 11):
        for seed in (7, 20973):
            image, off = images[0], offs[0]
            o = fresh(path, image, body, seed)
            permit = set(ROUTE0)
            model, game, expected = model_for(image, o, permit)
            trace, phases = drive(o, model, game, permit, set(), expected)
            assert tuple(a for a, _ in trace) == ROUTE0_ORDER
            assert phases[-1][1] == 'stop' and trace[-1][0] == 0x14598C
            assert queues(o.emu) == (0, 2, 0) and game.defer_count == 0 and game.defer_queued == 2
            assert 0x23D680 not in {c.target for c in o.emu.calls}
            assert 0x14BF58 in {c.target for c in o.emu.calls}
            # The two queued names then run. No player object, so each item test returns 0.
            permit.add(0x145690)
            mark = len(expected)
            seen = []
            hook_natives(o, permit, set(), seen)
            o.call(0x1EDA24, max_steps=2000000)
            game.run_deferred()
            assert not seen and len(expected) == mark
            assert queues(o.emu) == (2, 0, 1)
            regions_match(o, game.mem)
            seen = []
            hook_natives(o, permit, set(), seen)
            o.call(0x1EDA24, max_steps=8000000)
            game.run_deferred()
            assert seen == expected[mark:]
            assert [a for a, _ in seen] == [0x145690] * 48
            assert queues(o.emu) == (0, 0, 2)
            assert not differences(o, model, len(image))
            regions_match(o, game.mem)
            assert not any(c.stubbed for c in o.emu.calls)
            print('PASS route0_empty body=%d seed=%d enqueued=2 item_tests=48 stop=0x14598c' % (body, seed))

            # State 0 is not below States 0, so slot 18 returns before the mask call.
            cap = fresh(path, image, body, seed)
            found = capture(cap, off, 0x142320, 0x53F020)
            assert found['args'][1] == 0 and len(found['text']) == 6
            for states, stop in ((0, None), (100, HIDE_MASK)):
                o = fresh(path, image, body, seed)
                obj = plant_prop(o, found['text'], states)
                permit = set(ROUTE0)
                model, game, expected = model_for(image, o, permit)
                stops = set() if stop is None else {stop}
                if stop is None:
                    trace, _phases = drive(o, model, game, permit, stops, expected)
                    assert tuple(a for a, _ in trace) == ROUTE0_ORDER
                    assert o.emu.mem.u32(obj + 0x178) == 0
                    assert 0x23D680 in {c.target for c in o.emu.calls}
                    assert HIDE_MASK not in {c.target for c in o.emu.calls}
                else:
                    trace = []
                    hook_natives(o, permit, stops, trace)
                    try:
                        o.call(0x1ED694, 0x53F000, max_steps=2000000)
                        o.call(0x1ED694, 0x53F020, max_steps=4000000)
                        raise AssertionError('in-range setState returned')
                    except Boundary as hit:
                        assert hit.kind == 'callee' and hit.address == HIDE_MASK
                    assert tuple(a for a, _ in trace) == ROUTE0_ORDER[:4]
                    assert o.emu.mem.u32(obj + 0x178) == 0
                    assert o.emu.mem.u32(obj + 0x17C) == 0
                    assert o.emu.mem.u64(obj + 0x180) == 0
                    assert 0x23D680 in {c.target for c in o.emu.calls}
                    assert queues(o.emu) == (0, 0, 0)
                    assert not any(c.stubbed for c in o.emu.calls)
                print('PASS route0_prop body=%d seed=%d states=%d stop=%s' % (
                    body, seed, states, '0x14598c' if stop is None else '0x179550'))

            # Route 1: a missing lump stops before the disc lookup. A resident
            # normal lump lets the entry return without a grid call.
            image, off = images[1], offs[1]
            cap = fresh(path, image, body, seed)
            found = capture(cap, off, 0x14222C, 0x53F000)
            assert len(found['text']) == 8
            o = fresh(path, image, body, seed)
            permit = set(PERMITTED) | {0x14222C}
            model, game, expected = model_for(image, o, permit, miss=True)
            trace, _phases = drive(o, model, game, permit, {CD_FIND}, expected)
            assert tuple(a for a, _ in trace) == (0x14222C,)
            assert queues(o.emu) == (0, 0, 0)
            assert {c.target for c in o.emu.calls} >= {0x173558, 0x17306C, CD_FIND}
            print('PASS route1_miss body=%d seed=%d stop=0x1724fc' % (body, seed))
            o = fresh(path, image, body, seed)
            plant_lump(o.emu, found['text'], b'\0\0\0\0')
            permit = set(PERMITTED) | {0x14222C, 0x144DB8, 0x144C00}
            model, game, expected = model_for(image, o, permit)
            trace, phases = drive(o, model, game, permit, set(), expected)
            assert tuple(a for a, _ in trace) == ROUTE1_ORDER
            assert phases[-1] == (None, 'absent', None)
            assert queues(o.emu) == (0, 0, 0)
            assert CD_FIND not in {c.target for c in o.emu.calls}
            assert 0x14F028 not in {c.target for c in o.emu.calls}
            print('PASS route1_resident body=%d seed=%d natives=%d returned=1' % (body, seed, len(trace)))

            # Route 2: fixture level name, resident cut, offline, no player object.
            image, off = images[2], offs[2]
            cap = fresh(path, image, body, seed)
            grabbed = {}

            def grab(m, grabbed=grabbed, cap=cap, off=off):
                params = m.r[5] & 0xFFFFFFFF
                grabbed['text'] = amx_string(m.mem, cap.base, off, m.mem.s32(params + 4))
                raise Boundary('capture', 0x143F1C)
            hook_natives(cap, set(PERMITTED), set(), [])
            cap.emu.hook(0x143F1C, grab)
            try:
                cap.call(0x1ED694, 0x53F000, max_steps=2000000)
                cap.call(0x1ED694, 0x53F020, max_steps=4000000)
                cap.call(0x1EDAC0, max_steps=4000000)
            except Boundary:
                pass
            assert len(grabbed['text']) == 6
            o = fresh(path, image, body, seed)
            e = o.emu
            e.mem.write(LEVEL, b'authored\0')
            payload = plant_lump(e, b'authored.lmp', b'\0' * 16)
            label = e.alloc(len(grabbed['text']) + 5)
            e.mem.write(label, grabbed['text'] + b'.cut\0')
            e.mem.w32(e.mem.u32(LUMPS + 0x10) + 4, label)
            camera = e.alloc(0x100)
            e.mem.w32(CAMERA, camera)
            permit = set(PERMITTED) | {0x143F1C, 0x144B44}
            model, game, expected = model_for(image, o, permit)
            game.mem.w32(game.host.header, 0)
            trace, phases = drive(o, model, game, permit, set(), expected)
            assert tuple(a for a, _ in trace) == ROUTE2_ORDER
            assert phases[-1][1] == 'return'
            assert e.mem.u8(POST) != 0 and e.mem.u8(IN_POST) == 0
            assert e.mem.u32(0x4D8AF0 + 0x43D0) == 1
            assert queues(e) == (0, 0, 0)
            cut_matches(e, game.mem)
            assert e.mem.u32(payload) == 0
            mark = len(expected)
            seen = []
            hook_natives(o, permit, set(), seen)
            game.run_post_action()
            o.call(0x1EDAC0, max_steps=4000000)
            assert seen == expected[mark:]
            assert [a for a, _ in seen] == [0x144B44]
            assert len(amx_string(e.mem, o.base, off, seen[0][1][0])) == 5
            assert e.mem.u8(POST) == 0 and queues(e) == (0, 0, 0)
            assert not differences(o, model, len(model.image))
            regions_match(o, game.mem)
            assert not any(c.stubbed for c in e.calls)
            print('PASS route2_cut body=%d seed=%d tasks=2 replacement_stop=returned' % (body, seed))
            cases += 1
    print('PASS arrival_stage_r5 cases=%d' % cases)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('FAIL type=%s address=0x%x' % (type(error).__name__, getattr(error, 'address', getattr(error, 'addr', 0))))
        raise
