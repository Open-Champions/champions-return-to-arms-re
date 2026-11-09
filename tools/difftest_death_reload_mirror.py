#!/usr/bin/env python3
"""Run startup, then engine_init past the uncached store, then the death sequence.

Opt-ins on top of the round-6 machine: main-RAM mirrors, main RAM above the
second PT_LOAD, the two DMA channel words the GIF kick and sceGsSyncPath use,
CFC2 of VPU_STAT, FlushCache at two callers that do not read v0, and
EndOfHeap at one caller.  Every returned syscall value, the cleared DMA start
bit and the VPU_STAT 0 are modelled.  No service is stubbed.  The test heap is
moved above 32 MB so the fixture does not overlap the game heap.
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
TEX_RELOCATE, MEM_INIT_HEAP, LATER_WAIT = 0x179e10, 0x150598, 0x19d828
SIF_OUTER, SIF_INNER = 0x355d68, 0x355608
RING_SLOT, PARTICLE_WORD = 0x7cfd40, 0x82c408
WATCH = ((RING_SLOT, 4), (PARTICLE_WORD, 4))
BSS_CLEAR = [(0x14fbe0, RING_SLOT, 16, 0), (0x14fbe0, PARTICLE_WORD & ~0xf, 16, 0)]
HEAP_BLOCK, HEAP_SIZE = 0x90a600, 0x16a57cc
GP = 0x56c170
OUTSIDE_RAM = 0x04000000


def run_boot(elf):
    e = EE(elf)
    e.record_calls = False
    # The first store in engine_init targets the GS register window.
    e.mem.map(0x12000000, 0x2000)
    e.install_deci2_kputs()
    e.install_modelled_boot()
    e.install_modelled_intc()
    e.install_ram_mirrors()
    e.install_modelled_main_ram()
    e.install_modelled_dma_idle()
    e.install_modelled_vpu_stat()
    e.install_modelled_flush_cache()
    e.install_modelled_end_of_heap()
    e.writes.clear()
    e.record_writes = True
    e.write_watch = WATCH
    try:
        e.call(e.entry, max_steps=4000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x35c108, 0x80000000, 4, 'read'), exc
    else:
        raise AssertionError('entry returned')
    assert e.mem.u32(0x5075d0) == 1 and e.mem.u32(0x5075d4) == 2
    assert e.writes == BSS_CLEAR, e.writes
    e.writes.clear()

    # engine_init's allocator waits on the semaphore at 0x5075d0 (0x3b61c8),
    # so it runs on the machine startup left.  sp is reset; gp is startup's.
    assert (e.r[28] & 0xffffffff) == GP
    e.r[29] = e.stack_hi - 0x100
    hits = []
    for addr in (TEX_RELOCATE, MEM_INIT_HEAP, SIF_OUTER, SIF_INNER, TEXCACHE_INIT,
                 PARTICLE_INIT, WORLD_RECORDS, PLAYER_CTOR, LATER_WAIT):
        e.hook(addr, lambda emu, addr=addr: hits.append((addr, emu.r[31] & 0xffffffff)))
    stored = []
    # The instruction after each uncached halfword store: read the cached copy.
    for after, reg in ((0x19d4b8, 6), (0x19d524, 20)):
        e.hook(after, lambda emu, reg=reg: stored.append(
            (emu.r[reg] & 0xffffffff, emu.mem.u16((emu.r[reg] & 0x0fffffff) + 0x14))))
    try:
        e.call(ENGINE_INIT, max_steps=200000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x35574c, 0x1000e010, 4, 'read'), exc
    else:
        raise AssertionError('engine_init returned')
    assert (e.r[31] & 0xffffffff) == 0x355744
    assert hits == [(TEX_RELOCATE, 0x19d498), (TEX_RELOCATE, 0x19d4f0),
                    (MEM_INIT_HEAP, 0x19d610), (SIF_OUTER, 0x19bab0),
                    (SIF_INNER, 0x355db8)], hits
    # The uncached stores at 0x19d4b4 and 0x19d520 landed in the cached bytes.
    assert stored == [(0x21800080, 0x2300), (0x2188c180, 0x2bc0)], stored
    # Both blocks are in the PT_LOAD at 0x1800000, inside the heap block, and
    # mem_initHeap's fill later overwrites them.
    assert e.mem.u16(0x1800094) == 0xa5a5 and e.mem.u16(0x188c194) == 0xa5a5
    assert e.mem.u32(0x8400f0) == 3 and e.mem.u32(0x8400f4) == 4
    assert e.mem.u32(0x8400e8) == HEAP_BLOCK and e.mem.u32(0x8400ec) == HEAP_SIZE
    assert e.mem.u8(HEAP_BLOCK + HEAP_SIZE - 1) == 0xa5
    assert e._hw_words == {0x1000a000: 0x101, 0x1000a010: 0x188c180, 0x1000a020: 0x8c08}
    assert e.intc_deliveries == [(2, HANDLER, 4)] * 5, e.intc_deliveries
    assert e.mem.u32(RING_SLOT) == 0 and e.mem.u32(PARTICLE_WORD) == 0
    assert e.writes == [], e.writes
    assert not any(c.stubbed for c in e.calls)
    return e


def reload_after(elf, rng, qualified):
    e = run_boot(elf)
    e.install_terminate_thread()
    e._heap, e.HEAP_HI = OUTSIDE_RAM, OUTSIDE_RAM + 0x700000
    e.r[29] = e.stack_hi - 0x100
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
    assert e.mem.u32(RING_SLOT) == 0 and e.mem.u32(PARTICLE_WORD) == 0
    assert e.writes == [], e.writes
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
    print('PASS death-reload mirror: 2 engine_init SIF D_STAT stops, '
          '2 particle-reset faults')


if __name__ == '__main__':
    main()
