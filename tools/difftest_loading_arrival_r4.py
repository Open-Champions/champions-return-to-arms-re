#!/usr/bin/env python3
"""Original queue composition and private arrival prefixes on explicit state controls.

Usage: python3 tools/difftest_loading_arrival_r4.py local/SLUS_209.73 [local/route.json]
The optional JSON is an ordered list of three local archive paths. Private names,
script bytes and arguments are read only into memory; output is counts only.
These are bounded fixtures, never a normal-route arrival or deferred census.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from difftest_amx import Original, differences
from difftest_loading import SHA256
from ee_emu import EE, CpuTrap
from gob import gob_entries, lmp_entries
from ref_amx import Machine, assemble, build_image

QUEUE, FRONT, BACK, PARITY = 0x86B278, 0x86DA78, 0x86DA7C, 0x4F8690
RECORD, STRIDE, RECORDS = 0x4D8AF0, 0x4C30, 4
SAVE, PLAYERS, DIFFICULTY = 0x50605C, 0x4D8AE0, 0x4F719C
TABLE = 0x403370
# Only these native effects are established in this probe. Others stop BEFORE execution.
ALLOWED = {0x1473B4, 0x1420D0, 0x1420A4, 0x142084, 0x142044}


class Boundary(Exception):
    """Intentional unresolved-native boundary, not an original machine fault."""


def require_local(path):
    # Existing read-only input symlinks remain valid; do not follow them for this check.
    root = Path(__file__).absolute().parent.parent / 'local'
    assert Path(os.path.abspath(path)).is_relative_to(root), 'input must be under local/'


def original(path, image):
    o = Original(path)
    o.emu.hooks.clear()  # remove Original's synthetic/nested-call conveniences
    o.place(image)
    assert o.load() == 0
    o.emu.record_calls = True
    assert o.emu.follow is None and not o.emu.patches
    return o


def reset_controls(path):
    """Full original reset clears script queues, but does not create route state."""
    cases = 0
    for players in (1, 2):
        for difficulty in (1, 4):
            e = EE(path)
            e.record_writes = False
            e.mem.w32(PLAYERS, players)
            e.mem.w32(DIFFICULTY, difficulty)
            for address, value in ((FRONT, 9), (BACK, 8), (PARITY, 7), (SAVE, 123)):
                e.mem.w32(address, value)
            e.mem.write(0x86FA80, b'authored_pending\0')
            expected = []
            for slot in range(RECORDS):
                where = RECORD + STRIDE * slot + 0x4BCC  # difficulty rows 1..5
                data = bytes((0x80 + slot + i) & 0xFF for i in range(65))
                e.mem.write(where, data)
                expected.append((where, data))
            e.call(0x1E6F58)
            assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY, SAVE)) == (0, 0, 0, 0)
            assert e.mem.u8(0x86FA80) == 0
            assert e.mem.u32(PLAYERS) == players and e.mem.u32(DIFFICULTY) == difficulty
            assert all(e.mem.read(where, len(data)) == data for where, data in expected)
            assert e.follow is None and not e.hooks and not e.patches
            assert not any(c.stubbed for c in e.calls)
            cases += 1
    return cases


def queue_composition(path):
    """Clear -> real enqueue -> three real passes, including a native re-enqueue."""
    program = []
    for label, value in (('alpha', 11), ('beta', 22), ('gamma', 33)):
        program += [label + ':', ('PROC',), ('PUSH.C', value), ('PUSH.C', 4),
                    ('SYSREQ.C', 0), ('STACK', 8)]
        if label == 'alpha':
            program += [('PUSH.C', 0), ('PUSH.C', 4), ('SYSREQ.C', 1), ('STACK', 8)]
        program += [('CONST.pri', 0), ('HALT', 0)]
    code, labels = assemble(program)
    image = build_image(code, list(b'gamma\0'), list(labels.items()),
                        ('mark', 'enqueue'), 256)
    cases = 0
    for initial_parity in (0, 1, 7):
        o = original(path, image)
        e = o.emu
        assert o.register([(b'mark', 0x1473B4), (b'enqueue', 0x144160)]) == 0
        e.mem.w32(PARITY, initial_parity)
        e.mem.w32(FRONT, 9)
        e.mem.w32(BACK, 8)
        o.call(0x1EDA08)
        assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY)) == (0, 0, 0)
        trace, dispatched = [], []
        e.hook(0x1473B4, lambda m: trace.append((0x1473B4, m.mem.s32(m.r[5] + 4))))
        e.hook(0x144160, lambda m: trace.append((0x144160, None)))
        e.hook(0x1ED694, lambda m: dispatched.append(m.mem.cstr(m.r[4])))
        name = e.alloc(32)
        for text in (b'alpha', b'beta'):
            e.mem.write(name, text + b'\0')
            o.call(0x1ED52C, name)
        assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY)) == (0, 2, 0)
        assert [e.mem.cstr(QUEUE + 0x1400 + 0x50 * i) for i in range(2)] == ['alpha', 'beta']
        o.call(0x1EDA24)
        assert not trace and not dispatched
        assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY)) == (2, 0, 1)
        o.call(0x1EDA24)
        assert dispatched == ['alpha', 'beta']
        assert trace == [(0x1473B4, 11), (0x144160, None), (0x1473B4, 22)]
        assert e.mem.u32(SAVE) == 22
        assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY)) == (1, 0, 2)
        assert e.mem.cstr(QUEUE) == 'gamma'
        o.call(0x1EDA24)
        assert dispatched == ['alpha', 'beta', 'gamma']
        assert trace[-1] == (0x1473B4, 33) and e.mem.u32(SAVE) == 33
        assert tuple(e.mem.u32(a) for a in (FRONT, BACK, PARITY)) == (0, 0, 3)
        assert not any(c.stubbed for c in e.calls)
        cases += 1
    return cases


def capacity(path):
    """The 65th enqueue must not change count, retained entries or adjacent bytes."""
    code, _labels = assemble([('PROC',), ('HALT', 0)])
    image = build_image(code)
    cases = 0
    for parity in (0, 1, 7):
        o = original(path, image)
        e = o.emu
        e.mem.w32(PARITY, parity)
        e.mem.write(QUEUE, bytes([0xA5]) * 0x2800)
        name = e.alloc(32)
        for ordinal in range(64):
            text = ('entry_%02d' % ordinal).encode()
            e.mem.write(name, text + b'\0')
            o.call(0x1ED52C, name)
        before = e.mem.read(QUEUE, 0x2800)
        e.mem.write(name, b'overflow\0')
        o.call(0x1ED52C, name)
        assert e.mem.u32(BACK) == 64 and e.mem.u32(FRONT) == 0
        assert e.mem.read(QUEUE, 0x2800) == before
        back_base = QUEUE + ((parity & 1) ^ 1) * 0x1400
        assert [e.mem.cstr(back_base + i * 0x50) for i in range(64)] == [
            'entry_%02d' % i for i in range(64)]
        other = QUEUE + (parity & 1) * 0x1400
        assert e.mem.read(other, 0x1400) == bytes([0xA5]) * 0x1400
        assert not any(c.stubbed for c in e.calls)
        cases += 1
    return cases


def private_script(archive):
    require_local(archive)
    data = Path(archive).read_bytes()
    scripts = []
    for _name, start, size in gob_entries(data):
        assert 0 <= start <= start + size <= len(data)
        lump = data[start:start + size]
        for name, offset, length in lmp_entries(lump):
            assert 0 <= offset <= offset + length <= len(lump)
            if Path(name).suffix.lower() == '.scr':
                scripts.append(lump[offset:offset + length])
    assert len(scripts) == 1, 'expected exactly one private script'
    return scripts[0]


def prefix(path, image, players, difficulty, bits, choice):
    """Compare actual VM/native execution with an independent VM and state model."""
    o = original(path, image)
    e = o.emu
    assert o.call(0x141310, o.base, TABLE, 0xFFFFFFFF) == 0
    model = Machine(image)
    assert model.load() == 0
    # These are deliberate controls, not player/save state inferred from the route.
    records = bytearray([0xA4]) * (STRIDE * RECORDS)
    for slot in range(RECORDS):
        for row in range(5):
            begin = STRIDE * slot + 0x4BBF + 13 * row
            records[begin:begin + 13] = bytes([0xA4 | bits]) * 13
        records[STRIDE * slot + 0x4C1A] = (1 << difficulty) if choice else 0
    e.mem.write(RECORD, records)
    e.mem.w32(PLAYERS, players)
    e.mem.w32(DIFFICULTY, difficulty)
    e.mem.w32(SAVE, 0x12345678)
    state = {'save': 0x12345678}
    expected_trace, actual_trace = [], []

    def model_native(address):
        def run(_vm, args):
            expected_trace.append((address, tuple(args)))
            if address not in ALLOWED:
                raise Boundary()
            if address == 0x1473B4:
                state['save'] = args[0] & 0xFFFFFFFF
                return 0
            if address == 0x142044:
                return records[0x4C1A] & (1 << difficulty)
            mission = args[0]
            if mission >= 13:
                return 0
            assert 0 <= mission < 13, 'control excludes negative mission indices'
            offset = 0x4BBF + 13 * difficulty + mission
            if address == 0x142084:
                return (records[offset] >> 1) & 1
            if address == 0x1420D0:
                for slot in range(players):
                    pos = STRIDE * slot + offset
                    records[pos] = (records[pos] & 0xFE) | (args[1] & 1)
            elif address == 0x1420A4:
                for slot in range(RECORDS):
                    records[STRIDE * slot + offset] |= 2
            return 0
        return run

    def observe(address):
        def run(m):
            params = m.r[5] & 0xFFFFFFFF
            count = m.mem.s32(params)
            assert 0 <= count <= 64 and count % 4 == 0
            args = tuple(m.mem.s32(params + 4 + i) for i in range(0, count, 4))
            actual_trace.append((address, args))
            if address not in ALLOWED:
                raise Boundary()
            # Return naturally: the original handler and all its callees execute.
        return run

    bindings = {}
    for index in range(191):
        name_ptr, address = e.mem.u32(TABLE + 8 * index), e.mem.u32(TABLE + 8 * index + 4)
        if not name_ptr:
            break
        bindings[e.mem.cstr(name_ptr).encode('latin1')] = model_native(address)
        e.hook(address, observe(address))
    assert model.register(bindings) == 0
    for entry in (0x53F000, 0x53F020):
        name = e.mem.cstr(entry).encode('latin1')
        stopped = [False, False]
        result = [None, None]
        try:
            result[0] = model.call(name)
        except Boundary:
            stopped[0] = True
        try:
            result[1] = o.call(0x1ED694, entry)
        except Boundary:
            stopped[1] = True
        assert stopped[0] == stopped[1] and result[0] == result[1]
        assert actual_trace == expected_trace, 'native address/argument order mismatch'
        assert not differences(o, model, len(image)), 'script state mismatch at boundary'
        assert e.mem.read(RECORD, len(records)) == records, 'player-record effects mismatch'
        assert e.mem.u32(SAVE) == state['save']
        assert e.mem.u32(FRONT) == e.mem.u32(BACK) == 0
        assert not any(c.stubbed for c in e.calls)
        if stopped[0]:
            # The final trace event is an unreached native body, not an executed native.
            return tuple(address for address, _args in actual_trace)
    raise AssertionError('expected an unresolved native boundary')


def private_prefixes(path, manifest):
    require_local(manifest)
    paths = json.loads(Path(manifest).read_text())
    assert isinstance(paths, list) and len(paths) == 3
    cases = 0
    executed = 0
    boundaries = set()
    for archive in paths:
        image = private_script(archive)
        for players in (1, 2, 4):
            for difficulty in (0, 1, 4):
                for bits in (0, 1, 2, 3):
                    for choice in (0, 1):
                        order = prefix(path, image, players, difficulty, bits, choice)
                        boundaries.add(order[-1])
                        executed += len(order) - 1
                        cases += 1
    return cases, executed, len(boundaries)


def bootstrap_boundaries(path, manifest):
    """Diagnostic only: a fresh ELF is not an established normal-arrival state."""
    require_local(manifest)
    paths = json.loads(Path(manifest).read_text())
    assert isinstance(paths, list) and len(paths) == 3
    for archive in paths:
        require_local(archive)
        e = EE(path)
        e.record_writes = False
        name = Path(archive).stem.lower().encode('latin1')
        pointer = e.alloc(len(name) + 1)
        e.mem.write(pointer, name + b'\0')
        try:
            e.call(0x1E55C0, pointer, 0, max_steps=200000)
        except CpuTrap:
            assert e.cur == 0x352E14 and e.r[3] == 124
        else:
            raise AssertionError('expected unsupported syscall boundary')
        assert e.follow is None and not e.hooks and not e.patches
        assert not any(c.stubbed for c in e.calls)
        assert not any(c.target in (0x217978, 0x1ED694, 0x1EDA24) for c in e.calls)
    return len(paths)


def main():
    path = sys.argv[1]
    require_local(path)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256
    print('PASS original_reset cases=%d' % reset_controls(path))
    print('PASS queue_composition cases=%d' % queue_composition(path))
    print('PASS queue_capacity cases=%d' % capacity(path))
    if len(sys.argv) > 2:
        cases, executed, boundaries = private_prefixes(path, sys.argv[2])
        print('PASS private_initial_prefixes cases=%d executed_natives=%d unresolved_native_boundaries=%d'
              % (cases, executed, boundaries))
        print('PASS fresh_ELF_boundary_controls cases=%d' % bootstrap_boundaries(path, sys.argv[2]))
        print('UNKNOWN normal_arrival deferred_census')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # VM/loader exception text can contain private names or instruction words.
        print('FAIL type=%s address=0x%x' % (type(error).__name__, getattr(error, 'addr', 0)))
        sys.exit(1)
