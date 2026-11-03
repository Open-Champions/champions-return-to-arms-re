#!/usr/bin/env python3
"""Continue the death/reload loader after the observed Deci2 kputs contract.

The round-2 sequence test still requires the unhandled syscall trap.  This file
only adds the opt-in continuation.  No service is stubbed.
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
from ee_emu import CpuTrap, MemoryFault

PARTICLE_INIT = 0x18e648
# Id slots scanned by 0x18ec00.  0x82c408 is a different word, rewritten at 0x195c1c.
SENTINEL_LO, SENTINEL_HI = 0x82c40c, 0x82c484
LOAD_LEVEL, TEARDOWN, TEARDOWN_RETURN = 0x1e55c0, 0x1e4e88, 0x1e513c
WORLD_RECORDS, PLAYER_CTOR = 0x14e808, 0x1a1d28
DECI2_STUB, DECI2_RETURN = 0x352e10, 0x352e18
PRINTF, PARTICLE_RESET = 0x355490, 0x18ebb8
TEXCACHE_SHUTDOWN, TERMINATE, TEXCACHE_INIT = 0x17e2c8, 0x352830, 0x17a1d0


def drive(elf, rng, qualified):
    e, info = prepare(elf, rng, found=True, qualified=qualified)
    e.call(0x1b2cc0, info['corpse'])
    for _ in range(273):
        e.call(0x3226e4, 1)
    assert e.mem.u8(0x86af50) == 2
    assert e.mem.u32(0x44fdb8) == 1
    assert e.mem.u8(0x41b720) == 253
    assert not any(c.stubbed for c in e.calls)
    assert not e.hooks
    return e


def snap(e):
    m = e.mem
    return (m.read(0x895580, 0x16000), m.read(0x8ab590, 10 * 0x18),
            m.read(0x8ab698, 0x2000))


def continue_loader(elf, rng, qualified, particles):
    e = drive(elf, rng, qualified)
    before = snap(e)
    e.install_deci2_kputs()
    if particles:
        assert e.call(PARTICLE_INIT) == 3
        for addr in range(SENTINEL_LO, SENTINEL_HI + 4, 4):
            assert e.mem.u32(addr) == 0xffffffff
        # 0x18ee18 links the free list; 0x195c1c stores this separate word.
        assert e.mem.u32(0x82c400) == 0x82c300
        assert e.mem.u32(0x82c408) == 1
        assert e.mem.u32(0x44fdb8) == 3
    returned = []
    e.hook(DECI2_RETURN, lambda _emu: returned.append(1))
    try:
        e.call(0x320edc, max_steps=2000000)
    except MemoryFault as exc:
        assert not particles
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x18ec10, 4, 4, 'write')
        assert (e.r[31] & 0xffffffff) == 0x1e502c
        assert e.mem.u32(SENTINEL_LO) == 0
        assert e.mem.u32(0x82c4e8) == 0
        kind = 'particle-reset'
    except CpuTrap as exc:
        assert particles
        assert str(exc) == ('SYSCALL at 0x00352834 (v1 = 37); '
                            'no kernel is modelled')
        assert e.pc == 0x352838 and e.cur == 0x352834
        assert (e.r[3] & 0xffffffff) == 37
        assert (e.r[4] & 0xffffffff) == 0
        assert (e.r[31] & 0xffffffff) == 0x17e480
        assert e.mem.u32(0x7cfd04) == 0
        kind = 'terminate-thread'
    else:
        raise AssertionError('loader returned')
    targets = [c.target for c in e.calls]
    assert targets.count(DECI2_STUB) == 1
    assert returned == [1]
    assert PRINTF in targets and PARTICLE_RESET in targets
    assert LOAD_LEVEL in targets and TEARDOWN in targets
    assert TEARDOWN_RETURN not in targets
    assert 0x21777c not in targets
    assert WORLD_RECORDS not in targets and PLAYER_CTOR not in targets
    assert TEXCACHE_INIT not in targets
    if particles:
        assert TEXCACHE_SHUTDOWN in targets and TERMINATE in targets
        assert e.mem.u32(0x44fdb8) == 3
    else:
        assert TEXCACHE_SHUTDOWN not in targets and TERMINATE not in targets
        assert e.mem.u32(0x44fdb8) == 1
    assert snap(e) == before
    assert e.mem.u8(0x86af50) == 2
    assert e.mem.u8(0x41b720) == 254
    assert not any(c.stubbed for c in e.calls)
    return kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == SHA
    kinds = []
    for qualified in (False, True):
        for particles in (False, True):
            kinds.append(continue_loader(
                args.elf, random.Random(args.seed), qualified, particles))
    assert kinds == ['particle-reset', 'terminate-thread',
                     'particle-reset', 'terminate-thread']
    print('PASS death-reload kputs continuation: 4 cases '
          '(2 exact particle-reset faults, 2 exact TerminateThread stops)')


if __name__ == '__main__':
    main()
