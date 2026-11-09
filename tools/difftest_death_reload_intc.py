#!/usr/bin/env python3
"""Deliver the registered handler when engine_init's WaitSema would block.

The round-5 boot test does not install interrupt delivery.  Returned syscall
values and the one-delivery cadence are modelled.
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
from ee_emu import EE, MemoryFault

ENGINE_INIT = 0x19d19c
HANDLER = 0x19b6e4
WORLD_RECORDS, PLAYER_CTOR = 0x14e808, 0x1a1d28
TEXCACHE_INIT, PARTICLE_INIT = 0x17a1d0, 0x18e648
TEX_RELOCATE, LATER_WAIT = 0x179e10, 0x19d828
RING_SLOT, RING_NEIGHBOR = 0x7cfd40, 0x7cfd44
PARTICLE_WORD, PARTICLE_NEIGHBOR = 0x82c408, 0x82c40c
RING_SENTINEL, PARTICLE_SENTINEL = 0x51525354, 0x61626364
WATCH = ((RING_SLOT, 4), (PARTICLE_WORD, 4))
COUNTER, COUNTER_NEIGHBOR, FIELD_BYTE = 0x44fd98, 0x44fd94, 0x44fd9c
HANDLER_ID = 0x44fd4c
SEMA_A, SEMA_B = 0x8400f0, 0x8400f4
GP = 0x56c170


def run_engine(elf):
    e = EE(elf)
    e.record_calls = False
    # engine_init and the INTC handler use GS privileged registers.  This is
    # the GS register model (EE.install_modelled_gs_privileged), not a GS.
    e.install_modelled_gs_privileged()
    e.install_deci2_kputs()
    e.install_modelled_boot()
    # Status is 0 at every delivery, so each one is a modelled exception the
    # CPU state does not allow (audit R7-2).  It is recorded and asserted.
    e.install_modelled_intc(while_disabled=True)
    e.r[28] = GP
    e.mem.w32(COUNTER_NEIGHBOR, 0x11111111)
    e.mem.w8(FIELD_BYTE, 0xA5)
    e.mem.w32(RING_SLOT, RING_SENTINEL)
    e.mem.w32(RING_NEIGHBOR, 0x22222222)
    e.mem.w32(PARTICLE_WORD, PARTICLE_SENTINEL)
    e.mem.w32(PARTICLE_NEIGHBOR, 0x33333333)
    e.writes.clear()
    e.record_writes = True
    e.write_watch = WATCH
    hits = []
    for addr in (TEX_RELOCATE, TEXCACHE_INIT, PARTICLE_INIT, WORLD_RECORDS,
                 PLAYER_CTOR, LATER_WAIT):
        e.hook(addr, lambda _emu, addr=addr: hits.append(addr))
    try:
        e.call(ENGINE_INIT, max_steps=4000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x19d4b4, 0x21800094, 2, 'write'), exc
    else:
        raise AssertionError('engine_init returned')
    assert e.cur == 0x19d4b4 and e.pc == 0x19d4b8
    assert (e.r[31] & 0xffffffff) == 0x19d498
    assert (e.r[28] & 0xffffffff) == GP
    assert (e.r[2] & 0xffffffff) == 0x2300
    assert (e.r[5] & 0xffffffff) == 0x1800080
    assert (e.r[6] & 0xffffffff) == 0x21800080
    assert (e.r[16] & 0xffffffff) == 0x1800000
    assert (e.r[19] & 0xffffffff) == 0x83d290
    assert (e.r[20] & 0xffffffff) == 0x20000000
    assert (e.r[21] & 0xffffffff) == 0x1000a000
    assert e.mem.u32(0x1800010) == 0x1800080
    assert e.mem.u32(0x83d290) == 0x230000
    assert e.mem.is_mapped(0x1800094, 2)
    assert e.mem.u32(COUNTER) == 5
    assert e.mem.u32(COUNTER_NEIGHBOR) == 0x11111111
    # 0 is the GS model's CSR bit 13, stored by the handler at 0x19b8f8.
    # It checks the model; it is not an executed GS result.
    assert e.mem.u8(FIELD_BYTE) == 0
    assert e.gs_reads == [(0x34f780, 0x12001000, 0)] + [(0x19b8d8, 0x12001000, 0)] * 5, e.gs_reads
    assert e.mem.u32(HANDLER_ID) == 1
    assert e.mem.u32(SEMA_A) == 1 and e.mem.u32(SEMA_B) == 2
    assert e._semas[1]['count'] == 5 and e._semas[2]['count'] == 0
    assert e.intc_deliveries == [(2, HANDLER, 2)] * 5
    assert e.intc_delivery_status == [0] * 5, e.intc_delivery_status
    assert e.mem.u32(RING_SLOT) == RING_SENTINEL and e.mem.u32(RING_NEIGHBOR) == 0x22222222
    assert e.mem.u32(PARTICLE_WORD) == PARTICLE_SENTINEL
    assert e.mem.u32(PARTICLE_NEIGHBOR) == 0x33333333
    assert e.writes == []
    assert hits == [TEX_RELOCATE]
    assert not any(c.stubbed for c in e.calls)
    return e


def reload_after(elf, rng, qualified):
    e = run_engine(elf)
    e.install_terminate_thread()
    e.record_calls = True
    e, _info = prepare(elf, rng, found=True, qualified=qualified, ee=e)
    e.call(0x1b2cc0, _info['corpse'])
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
    assert TEXCACHE_INIT not in targets and PARTICLE_INIT not in targets
    assert e.mem.u32(RING_SLOT) == RING_SENTINEL
    assert e.mem.u32(PARTICLE_WORD) == PARTICLE_SENTINEL
    assert e.writes == []
    assert e.mem.u8(0x41b720) == 254
    assert not any(c.stubbed for c in e.calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == SHA
    for qualified in (False, True):
        reload_after(args.elf, random.Random(args.seed), qualified)
    print('PASS death-reload intc: 2 engine_init uncached-store stops, '
          '2 particle-reset faults')


if __name__ == '__main__':
    main()
