#!/usr/bin/env python3
"""Run lethal pending damage through frame tasks to the world-loader boundary.

No services are replaced. Constructors, checkpoint creation, resource loading,
collision-produced damage and the top-level frame driver are not covered.
"""
import argparse
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: E402,F401
sys.path.insert(0, HERE)
from difftest_death_reload import SHA, fixture, put, get
from ee_emu import CpuTrap


def prepare(elf, rng, found=True, qualified=False, ee=None):
    e = fixture(elf) if ee is None else ee
    e.record_calls = True
    m = e.mem
    m.w32(0x44fdb8, 0)
    m.w32(0x44fdbc, 0xffffffff)
    m.w8(0x402791, 0)
    m.w8(0x44fcd0, 0)
    m.w32(0x4f85b0, 1)
    m.w32(0x4f7120, 0)
    m.w32(0x4f712c, 0)
    m.w32(0x41b4f4, 0)
    m.w32(0x506048, 0)
    m.w8(0x4f6708, 0)
    m.w32(0x4d8ae0, 1)
    m.w32(0x4f8420, 0)
    m.write(0x44fe18, b'origin\0')
    m.write(0x41b721, b'origin\0')
    m.w8(0x41b771, 0)
    m.w8(0x41b6d0, 0)
    e.call(0x1ec2b8)  # Original countdown reset, supplied initialization boundary.
    assert m.u16(0x4f7194) == 240
    assert get(e, 0x4f84a8, '4H') == (240, 240, 240, 240)
    m.write(0x4d8af0, bytes(0x4c30))
    corpse = e.alloc(0x590)
    m.w32(corpse + 0xc, 0)
    definition, clip = e.alloc(0x100), e.alloc(0x40)
    m.w32(corpse + 0x24, definition)
    m.w32(definition + 0xc, clip)
    m.w8(corpse + 0x119, 4)
    put(e, corpse + 0xc8, 'f', 100.)
    m.w32(0x4d8af0 + 0x43d8, corpse)
    put(e, 0x4d8af0 + 0xac, 'ff', 40., 160.)
    live = m.read(0x4d8af0, 0x4c30)

    # Synthetic act table: both origins match one configured act, or none do.
    table, origin, destination = e.alloc(16), e.alloc(16), e.alloc(16)
    m.write(origin, b'origin\0')
    m.write(destination, b'saved\0')
    put(e, table, 'IHHIHH', origin, 0x2000, 0, destination, 0x2000, 0)
    m.w32(0x88d3d4, 0)
    m.w32(0x4f8e7c, 1)
    m.w32(0x4f8e10, 2 if found else 0)
    m.w32(0x4f8e48, table)

    # Packet emission executes into a supplied RAM pool; no GS submission.
    packets = e.alloc(0x10000)
    m.w32(0x44fe0c, packets)
    m.w32(0x44fe10, packets)
    m.w32(0x44fda4, 0x2000)
    m.w32(0x6f4068, 0)
    m.w32(0x41b4d4, 0)
    m.w32(0x6f4088, e.alloc(16))
    m.write(0x7cbb70, bytes(4 * 24))
    m.write(0x41c140, bytes((0, 1, 2, 3)))
    m.write(0x41bfd8, bytes(4 * 0x58))

    # Actual Camera load/reset reads a constructed camera, 0xc4 saved bytes.
    camera = e.alloc(0x200)
    m.w32(0x4f8450, camera)
    m.write(0x895580, bytes(0x16000))
    m.write(0x895580, b'saved\0')
    if qualified:
        m.write(0x895594, b'part\0')
    m.w16(0x8955ee, 0)
    p = 0x8955f0
    put(e, p, '3f', 1., 2., 3.)
    put(e, p + 76, 'hhIIfff', 123, -456, 0, 0, 1., 2., 170.)
    camera_tail = bytes(rng.getrandbits(8) for _ in range(96))
    m.write(p + 100, camera_tail)
    p += 0xc4
    # Actual destination store load copies a 0x1e0 byte synthetic payload.
    gate_payload = bytes(rng.getrandbits(8) for _ in range(0x1e0))
    m.w32(p, 2)
    m.write(p + 4, gate_payload)
    p += 0x1e4
    put(e, p, 'IIHfff', 7, 1, 1234, 1., -2., 3.)
    p += 22
    saved = bytearray(0x4c30)
    saved[:0x80] = bytes(rng.getrandbits(8) for _ in range(0x80))
    struct.pack_into('<ffI', saved, 0xac, 80., 160., 0)
    for off in range(0x43f0, 0x4440, 4):
        struct.pack_into('<I', saved, off, 0xffffffff)
    struct.pack_into('<I', saved, 0x43d8, 0x12345678)
    m.write(p, saved)
    m.w32(0x86da78, 7)
    m.w32(0x86da7c, 9)
    m.w32(0x4f8690, 11)
    m.write(0x86da80, b'testvar\0\x05\0')
    m.write(0x8ab590, bytes(10 * 0x18))
    m.write(0x8ab590, b'origin\0')
    m.w32(0x8ab5a4, 0x2000)
    world_payload = bytes(rng.getrandbits(8) for _ in range(0x2000))
    m.write(0x8ab698, world_payload)
    # Main-loop stack guard has a required initialized sentinel region.
    m.map(0x1fc0000, 0x1400)
    m.write(0x1fc0000, bytes([0xa5]) * 0x1400)
    return e, dict(live=live, saved=saved, packets=packets, camera=camera,
                   corpse=corpse, clip=clip, world_payload=world_payload,
                   camera_tail=camera_tail, gate_payload=gate_payload,
                   found=found, qualified=qualified)


def sequence(elf, rng, found=True, qualified=False):
    e, f = prepare(elf, rng, found, qualified)
    m = e.mem
    checkpoint = m.read(0x895580, 0x16000)
    directory = m.read(0x8ab590, 10 * 0x18)
    e.call(0x1b2cc0, f['corpse'])
    assert get(e, 0x4d8af0 + 0xac, 'f') == (0.,)
    assert m.u32(f['corpse'] + 0xc) == 0x109
    assert m.u32(f['corpse'] + 0x58c) == 4
    assert m.u32(f['corpse'] + 0x11c) == f['clip']
    assert m.u8(f['corpse'] + 0x118) == 1
    assert m.u16(f['corpse'] + 0x138) == 0x206
    assert m.u32(f['corpse'] + 0xc8) == m.u32(f['corpse'] + 0x2dc) == 0
    f['live'] = m.read(0x4d8af0, 0x4c30)
    for i in range(240):
        e.call(0x3226e4, 1)
        assert m.u16(0x4f7194) == 239 - i
        assert m.u16(0x4f84a8) == 239 - i
        assert m.u32(0x44fdb8) == (1 if i == 239 else 0)
    assert get(e, 0x840100, '4I') == (0x1e75e8, 20, 0x53d438, 0)
    assert m.u32(0x4f66ac) == m.u8(0x86af50) == 0
    for i in range(32):
        e.call(0x3226e4, 1)
        assert m.u32(0x4f66ac) == 4 * (i + 1)
        assert m.u8(0x86af50) == (1 if i == 31 else 0)
        assert m.u32(0x6f4068) == i + 1
    assert m.u32(0x44fe10) > f['packets']
    link = m.u32(m.u32(0x6f4088) + 0xc)
    for i in range(31, -1, -1):
        assert link == 0x6e4068 + i * 16
        link = m.u32(link + 0xc)
    assert link == 0
    e.call(0x3226e4, 1)
    assert m.u8(0x41b720) == 253
    if found:
        assert m.u8(0x86af50) == 2
        assert m.u32(0x44fdb8) == 1
        assert m.cstr(0x41b6d0) == 'saved' + ('_part' if qualified else '')
        assert get(e, 0x4d8af0 + 0xac, 'ff') == (80., 160.)
        assert m.u32(0x4d8af0 + 0x43d8) == 0
        expected = bytearray(f['saved'])
        struct.pack_into('<I', expected, 0x43d8, 0)
        expected[0x43f0:0x4440] = bytes(0x50)
        assert m.read(0x4d8af0, 0x4c30) == expected
        assert get(e, 0x4f70d0, '3f') == (1., -2., 3.)
        assert m.u16(0x4f8410) == 1234
        assert m.read(0x8e3a50, 0x1e0) == f['gate_payload']
        assert m.u8(0x8e3c30) == 2
        assert m.read(f['camera'] + 0x100, 96) == f['camera_tail']
        assert get(e, 0x44f038, '3f') == (1., 2., 3.)
        assert get(e, f['camera'] + 0x68, 'hh') == (123, -456)
        assert [m.u32(p) for p in (0x86da78, 0x86da7c, 0x4f8690)] == [0, 0, 0]
        assert m.read(0x86da80, 10) == b'testvar\0\0\0'
        assert m.u8(0x8e1ad6) == 1
        assert m.u32(0x88d3d4) == 0
        # Unchanged emulated state: attempt the requested world's real loader.
        try:
            e.call(0x320edc, max_steps=1000000)
        except CpuTrap as exc:
            assert str(exc) == ('SYSCALL at 0x00352e14 (v1 = 124); '
                                'no kernel is modelled'), str(exc)
            assert e.pc == 0x352e18 and e.r[3] == 124
        else:
            raise AssertionError('unexpected unbounded loader completion')
        targets = [c.target for c in e.calls]
        assert 0x1e55c0 in targets
        assert 0x1e4e88 in targets and 0x352e10 in targets
        assert 0x21777c not in targets  # Checkpoint store skipped while task lives.
        assert 0x14e808 not in targets  # World reconstruction not reached.
        assert m.read(0x895580, 0x16000) == checkpoint
        assert m.read(0x8ab590, 10 * 0x18) == directory
        assert m.read(0x8ab698, 0x2000) == f['world_payload']
        assert m.u8(0x86af50) == 2 and m.u32(0x44fdb8) == 1
        assert m.u8(0x41b6d0) == 0
        assert m.u8(0x41b720) == 254
        assert m.cstr(0x41b721) == 'saved'
        assert m.cstr(0x41b771) == ('part' if qualified else '')
    else:
        assert m.u32(0x44fdb8) == 0
        expected = bytearray(f['live'])
        struct.pack_into('<f', expected, 0xac, 160.)
        assert m.read(0x4d8af0, 0x4c30) == expected
    assert not e.mem.auto_map and not e.hooks
    assert not any(c.stubbed for c in e.calls)
    return e


def completion_controls(elf):
    # Independent controls only: these do not resume a failed world loader.
    for pending, sub in ((True, ''), (False, ''), (False, 'wrong'), (False, 'part')):
        e = fixture(elf)
        m = e.mem
        m.w32(0x44fdb8, 0)
        m.w32(0x44fdbc, 0xffffffff)
        m.write(0x41b6d0, b'waiting\0' if pending else b'\0')
        m.write(0x41b721, b'saved\0')
        m.write(0x41b771, sub.encode() + b'\0')
        m.write(0x8e1a98, b'saved_part\0')
        m.w8(0x86af50, 2)
        e.call(0x19e4a0, 0x1e75e8, 20, 0x53d438, 0)
        e.call(0x19e798, 1, -1)
        assert m.u32(0x44fdb8) == (0 if not pending and sub == 'part' else 1)


def checkpoint_store_control(elf):
    # With no registered death task, the original prefix reaches the store.
    # Stop before the store: no fabricated writer behavior is substituted.
    e, _ = prepare(elf, random.Random(0))
    e.mem.write(0x41b6d0, b'saved\0')
    e.r[31] = e.RETURN_ADDR
    assert e.run(start=0x320edc, until=(0x21777c,), max_steps=100000) == 'stop'
    assert e.pc == 0x21777c
    assert e.mem.cstr(e.r[4] & 0xffffffff) == 'origin'
    assert not e.hooks and not any(c.stubbed for c in e.calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == SHA
    rng = random.Random(args.seed)
    for found in (False, True):
        for qualified in (False, True):
            sequence(args.elf, rng, found, qualified)
    completion_controls(args.elf)
    checkpoint_store_control(args.elf)
    print('PASS lethal-damage/task/reload sequences: 4 cases, 273 frame calls each')
    print('PASS original-loader fail-closed boundary: 2 cases')
    print('PASS separate task-completion controls: 4 cases')
    print('PASS no-death-task checkpoint-store reachability: 1 control')


if __name__ == '__main__':
    main()
