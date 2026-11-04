#!/usr/bin/env python3
"""Run startup, then engine_init, then the death/reload sequence in one session.

The round-2, round-3 and round-4 tests do not install this handler.  No service
is stubbed.  Returned syscall values are modelled.
"""
import argparse
import hashlib
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: E402,F401
sys.path.insert(0, HERE)
from difftest_death_reload import SHA
from difftest_death_reload_sequence import prepare
from ee_emu import CpuTrap, EE, MemoryFault

ENTRY = 0x14fa88
ENGINE_INIT = 0x19d19c
MAIN_CALL = 0x14fcb8
WORLD_RECORDS, PLAYER_CTOR = 0x14e808, 0x1a1d28
TEXCACHE_INIT, CREATE_THREAD = 0x17a1d0, 0x3527e0
RING_SLOT, PARTICLE_WORD = 0x7cfd40, 0x82c408
HANDLER_ID = 0x44fd4c
GP = 0x56c170


def run_entry(elf):
    e = EE(elf)
    e.record_calls = False
    e.record_writes = False
    e.install_modelled_boot()
    reached = []
    moved = []
    e.hook(MAIN_CALL, lambda _emu: reached.append(1))
    e.hook(0x14fc4c, lambda emu: moved.append(emu.r[2] & 0xffffffff))
    try:
        e.call(ENTRY, max_steps=4000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x35c108, 0x80000000, 4, 'read'), exc
    else:
        raise AssertionError('entry returned')
    assert not reached
    assert moved == [0x1fffff0]
    assert (e.r[28] & 0xffffffff) == GP
    assert (e.r[4] & 0xffffffff) == 0x80000000
    assert (e.r[5] & 0xffffffff) == 0x80080000
    assert (e.r[6] & 0xffffffff) == 0x35c108
    assert (e.r[3] & 0xffffffff) == 131
    assert (e.r[31] & 0xffffffff) == 0x35c1ec
    assert e.cur == 0x35c108
    assert e.mem.u32(0x5075d0) == 1
    assert e.mem.u32(0x5075d4) == 2
    assert e.mem.u32(RING_SLOT) == 0
    assert e.mem.u32(PARTICLE_WORD) == 0
    return e


def run_engine(elf):
    e = EE(elf)
    e.record_calls = False
    e.record_writes = False
    # The first store in engine_init targets the GS register window.
    e.mem.map(0x12000000, 0x2000)
    e.install_deci2_kputs()
    e.install_modelled_boot()
    e.r[28] = GP
    try:
        e.call(ENGINE_INIT, max_steps=4000000)
    except CpuTrap as exc:
        assert str(exc) == ('SYSCALL at 0x00352a24 (v1 = 68, a0 = 2); '
                            'modelled WaitSema count is 0'), str(exc)
    else:
        raise AssertionError('engine_init returned')
    assert e.cur == 0x352a24
    assert (e.r[31] & 0xffffffff) == 0x19d05c
    assert (e.r[4] & 0xffffffff) == 2
    assert (e.r[28] & 0xffffffff) == GP
    assert e.mem.u32(RING_SLOT) == 0
    assert e.mem.u32(PARTICLE_WORD) == 0
    assert e.mem.u32(HANDLER_ID) == 1
    return e


def reload_after(elf, rng, qualified):
    e = run_engine(elf)
    e.install_terminate_thread()
    e.record_calls = True
    e, info = prepare(elf, rng, found=True, qualified=qualified, ee=e)
    e.call(0x1b2cc0, info['corpse'])
    for _ in range(273):
        e.call(0x3226e4, 1)
    assert e.mem.u8(0x86af50) == 2
    try:
        e.call(0x320edc, max_steps=4000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x18ec10, 4, 4, 'write'), exc
        assert (e.r[31] & 0xffffffff) == 0x1e502c
    else:
        raise AssertionError('loader returned')
    targets = [c.target for c in e.calls]
    assert WORLD_RECORDS not in targets and PLAYER_CTOR not in targets
    assert TEXCACHE_INIT not in targets and CREATE_THREAD not in targets
    assert e.mem.u32(RING_SLOT) == 0
    assert e.mem.u32(PARTICLE_WORD) == 0
    assert e.mem.u8(0x41b720) == 254
    assert not any(c.stubbed for c in e.calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == SHA
    run_entry(args.elf)
    for qualified in (False, True):
        reload_after(args.elf, random.Random(args.seed), qualified)
    print('PASS death-reload boot: 1 entry stop at 0x80000000, '
          '2 engine_init WaitSema stops, 2 particle-reset faults')


if __name__ == '__main__':
    main()
