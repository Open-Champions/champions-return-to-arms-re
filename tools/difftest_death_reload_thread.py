#!/usr/bin/env python3
"""Continue the death/reload loader after the observed TerminateThread contract.

The round-2 sequence test still requires the unhandled syscall-124 trap, and
the round-3 test still requires the unhandled syscall-37 trap.  This file only
adds the second opt-in.  No service is stubbed.  particle_init is a harness
call, not a call the loader makes.
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

PARTICLE_INIT = 0x18e648
PARTICLE_INIT_SITE = 0x19d818
ENGINE_INIT, MAIN = 0x19d19c, 0x323dcc
SENTINEL_LO, SENTINEL_HI = 0x82c40c, 0x82c484
LOAD_LEVEL, TEARDOWN, TEARDOWN_RETURN = 0x1e55c0, 0x1e4e88, 0x1e513c
WORLD_RECORDS, PLAYER_CTOR = 0x14e808, 0x1a1d28
DECI2_STUB, DECI2_RETURN = 0x352e10, 0x352e18
PRINTF, PARTICLE_RESET = 0x355490, 0x18ebb8
TEXCACHE_SHUTDOWN, TERMINATE = 0x17e2c8, 0x352830
TEXCACHE_RESET, TEXCACHE_INIT = 0x179b08, 0x17a1d0
START_WRAPPER, REFER_STATUS, CREATE_THREAD = 0x353b20, 0x3528e0, 0x3527e0
START_SYSCALL, DELETE_THREAD = 0x352800, 0x3527f0
# Index word and first ring slot read by texcache_reset before the halfword store.
RING_INDEX, RING_SLOT = 0x7cfe44, 0x7cfd40
THREAD_ID = 0x7cfd04
CREATE_PARAM = 0x425e58


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
    e.install_terminate_thread()
    returned = []
    term_v0 = []
    reset_v0 = []
    e.hook(DECI2_RETURN, lambda emu: returned.append(1))
    e.hook(0x17e480, lambda emu: term_v0.append(emu.r[2] & 0xffffffff))
    e.hook(TEXCACHE_RESET, lambda emu: reset_v0.append(emu.r[2] & 0xffffffff))
    if particles:
        assert e.call(PARTICLE_INIT) == 3
        for addr in range(SENTINEL_LO, SENTINEL_HI + 4, 4):
            assert e.mem.u32(addr) == 0xffffffff
        assert e.mem.u32(0x82c400) == 0x82c300
        assert e.mem.u32(0x82c408) == 1
        assert e.mem.u32(0x44fdb8) == 3
    try:
        e.call(0x320edc, max_steps=4000000)
    except MemoryFault as exc:
        if particles:
            assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x179b30, 0x18, 2, 'write')
            assert (e.r[31] & 0xffffffff) == 0x17e498
            assert e.mem.u32(RING_INDEX) == 0
            assert e.mem.u32(RING_SLOT) == 0
            assert e.mem.u32(THREAD_ID) == 0
            assert e.cop0[12] == 0
            assert term_v0 == [0]
            assert reset_v0 == [0xffffffff]
            kind = 'texcache-reset'
        else:
            assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x18ec10, 4, 4, 'write')
            assert (e.r[31] & 0xffffffff) == 0x1e502c
            assert e.mem.u32(SENTINEL_LO) == 0
            assert e.mem.u32(0x82c4e8) == 0
            assert term_v0 == []
            assert reset_v0 == []
            kind = 'particle-reset'
    else:
        raise AssertionError('loader returned')
    targets = [c.target for c in e.calls]
    sites = [c.site for c in e.calls]
    assert targets.count(DECI2_STUB) == 1
    assert returned == [1]
    assert PRINTF in targets and PARTICLE_RESET in targets
    assert LOAD_LEVEL in targets and TEARDOWN in targets
    assert TEARDOWN_RETURN not in targets
    assert 0x21777c not in targets
    assert WORLD_RECORDS not in targets and PLAYER_CTOR not in targets
    assert PARTICLE_INIT not in targets and PARTICLE_INIT_SITE not in sites
    assert ENGINE_INIT not in targets and MAIN not in targets
    assert CREATE_THREAD not in targets and REFER_STATUS not in targets
    assert START_SYSCALL not in targets and DELETE_THREAD not in targets
    if particles:
        assert TEXCACHE_SHUTDOWN in targets and TERMINATE in targets
        assert START_WRAPPER in targets and TEXCACHE_RESET in targets
        assert TEXCACHE_INIT not in targets
        assert e.mem.u32(0x44fdb8) == 3
    else:
        assert TEXCACHE_SHUTDOWN not in targets and TERMINATE not in targets
        assert START_WRAPPER not in targets and TEXCACHE_RESET not in targets
        assert e.mem.u32(0x44fdb8) == 1
    assert snap(e) == before
    assert e.mem.u8(0x86af50) == 2
    assert e.mem.u8(0x41b720) == 254
    assert not any(c.stubbed for c in e.calls)
    return kind


def texcache_init_stops_at_create(elf):
    """Original texcache_init from the loaded image, with no handler installed."""
    e = EE(elf)
    try:
        e.call(TEXCACHE_INIT, max_steps=2000000)
    except CpuTrap as exc:
        assert str(exc) == ('SYSCALL at 0x003527e4 (v1 = 32); '
                            'no kernel is modelled')
    else:
        raise AssertionError('texcache_init returned')
    assert e.pc == 0x3527e8 and e.cur == 0x3527e4
    assert (e.r[31] & 0xffffffff) == 0x17a37c
    assert (e.r[4] & 0xffffffff) == CREATE_PARAM
    assert (e.r[28] & 0xffffffff) == 0
    words = [e.mem.u32(CREATE_PARAM + offset) for offset in range(0, 0x18, 4)]
    assert words == [0, 0x17ca58, 0x7cbd00, 0x4000, 0, 6]
    assert e.mem.u32(RING_SLOT) == 0x7cfe00
    assert e.mem.u32(THREAD_ID) == 0
    assert [c.target for c in e.calls].count(CREATE_THREAD) == 1
    assert START_WRAPPER not in [c.target for c in e.calls]
    assert not any(c.stubbed for c in e.calls)


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
    assert kinds == ['particle-reset', 'texcache-reset',
                     'particle-reset', 'texcache-reset']
    texcache_init_stops_at_create(args.elf)
    print('PASS death-reload thread continuation: 4 cases '
          '(2 exact particle-reset faults, 2 exact texcache-reset faults) '
          'and 1 exact CreateThread stop')


if __name__ == '__main__':
    main()
