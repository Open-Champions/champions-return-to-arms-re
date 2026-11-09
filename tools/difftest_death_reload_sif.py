#!/usr/bin/env python3
"""Run startup and engine_init through the EE half of the SIF handshake.

Round 8.  The round-7 machine (difftest_death_reload_mirror.py) stops at the
D_STAT read at 0x35574c in sceSifInitCmd 0x355608.  This test adds one more
opt-in, EE.install_modelled_sif, and nothing else.  Every syscall result, the
two DMA words, the IOP buffer placeholder and the one set-register packet are
modelled; see that method.  No called function is stubbed.  The boot runs
with record_calls False, so that is checked on the machine itself
(assert_unstubbed: no follow set, no stub installed, every hook one of this
test's call recorders), and mutation controls show the check fails when a
stub or a follow set is added (audit R8-8).

This machine is reached only through models (audit R7-1, R7-2): the GS
privileged-register model, and five INTC deliveries taken while COP0 Status
is 0 (install_modelled_intc(while_disabled=True)).  The set-register packet
is also delivered while Status disables interrupts (0x10000: EIE set, IE
clear).  The test asserts each Status.  Nothing past those deliveries is an
executed retail result.

The two software-register reads before any SetReg return a modelled 0 that
selects the branch the run takes (audit R8-5).  D_STAT and D5_CHCR read as a
modelled 0, and a store to either traps (audit R8-4).

The run then stops where the EE waits for an IOP reply that the EE code does
not determine: WaitSema in sceSifBindRpc 0x356510, bound by sceCdInit
0x361bc8 to server 0x80000592.  The death sequence then runs on that machine
and reaches the same particle-reset fault as round 7.
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
from difftest_death_reload import SHA  # noqa: E402
import difftest_death_reload_mirror as R7  # noqa: E402
from ee_emu import EE, CpuTrap, MemoryFault  # noqa: E402

INIT_RPC, INIT_CMD, CD_INIT, BIND_RPC = 0x355d68, 0x355608, 0x361bc8, 0x356510
CALL_RPC, DMAC_HANDLER, SET_SREG, GET_SREG = 0x3566f0, 0x355b70, 0x355590, 0x3555c0
REBOOT_IOP = 0x35bed8
CMD_DATA, SREG0, SUBADDR_WORD, DMAC_ID = 0x8ef118, 0x8ef2c0, 0x8ef120, 0x8ef114
CD_CLIENT, CD_RESULT, CD_MODE = 0x8f8a68, 0x509e40, 0x8f8ac0
CD_SERVER = CD_CLIENT + 0x24
PH = EE.SIF_SUBADDR_PLACEHOLDER
SENTINEL = 0x5a5b5c5d
# (address, size) of every word whose stores are recorded after startup.
WATCH = ((R7.RING_SLOT, 4), (R7.PARTICLE_WORD, 4), (SREG0, 4), (SUBADDR_WORD, 4),
         (DMAC_ID, 4), (CD_SERVER, 4), (CD_RESULT, 0x10), (CD_MODE, 4))
PLANTED = (SREG0, SUBADDR_WORD, DMAC_ID, CD_SERVER, CD_MODE,
           CD_RESULT, CD_RESULT + 4, CD_RESULT + 8, CD_RESULT + 12)
# Every store to a watched word, in order.  The CD words have no store.
EXPECTED_WRITES = [
    (0x3556ac, SUBADDR_WORD, 4, 0),       # sceSifInitCmd clears cmd data +8
    (0x3556f0, SREG0, 4, 0),              # the 32-word sreg clear, last word stored is sregs[0]
    (0x3557a4, DMAC_ID, 4, 2),            # AddDmacHandler id (modelled)
    (0x3557b8, SUBADDR_WORD, 4, 0),       # GetReg(0x80000000) = 0
    (0x35581c, SUBADDR_WORD, 4, PH),      # GetReg(2) placeholder
    (0x3555a8, SREG0, 4, 1),              # the game's set_sreg handler, modelled packet
    (0x356544, CD_SERVER, 4, 0),          # sceSifBindRpc clears client +0x24
]
HOOKED = (INIT_RPC, INIT_CMD, DMAC_HANDLER, SET_SREG, GET_SREG, CD_INIT,
          BIND_RPC, CALL_RPC, REBOOT_IOP, R7.TEXCACHE_INIT, R7.PARTICLE_INIT,
          R7.LATER_WAIT)
# The IOP reset 0x35bd08, read but not reached by the boot: a stub there
# changes nothing the run asserts except the no-stubs check.
UNREACHED_RESET = 0x35bd08


class StubbedBoot(AssertionError):
    """assert_unstubbed found a stub, a follow set or a foreign hook."""


def install_recorders(e, hits):
    """Hook every address in HOOKED with a call recorder.  Returns {address: recorder}."""
    recorders = {}
    for addr in HOOKED:
        def record(emu, addr=addr):
            hits.append((addr, emu.r[31] & 0xffffffff, emu.r[4] & 0xffffffff,
                         emu.r[5] & 0xffffffff))
        e.hook(addr, record)
        recorders[addr] = record
    return recorders


def assert_unstubbed(e, recorders):
    """Fail unless every callee ran: no follow set, no named stub, and the hooks
    are exactly this test's recorders (EE.stub installs its replacement as a hook,
    so any stub, named or not, changes e.hooks)."""
    if e.follow is not None:
        raise StubbedBoot('follow set installed: %r' % (sorted(e.follow),))
    if e.stub_names:
        raise StubbedBoot('named stubs: %r' % (e.stub_names,))
    foreign = sorted(hex(a) for a in e.hooks if e.hooks[a] is not recorders.get(a))
    missing = sorted(hex(a) for a in recorders if a not in e.hooks)
    if foreign or missing:
        raise StubbedBoot('hooks other than the recorders: %r, recorders missing: %r'
                          % (foreign, missing))


def mutation_controls(elf):
    """Each mutant must make assert_unstubbed fail.  Returns the number killed."""
    mutants = (
        lambda e: e.stub(UNREACHED_RESET),               # unnamed stub, not reached
        lambda e: e.stub(INIT_CMD),                      # a stub replacing a recorder
        lambda e: e.stub(UNREACHED_RESET, name='reset'), # named stub
        lambda e: setattr(e, 'follow', set()),           # stub every callee
    )
    base = EE(elf)
    assert_unstubbed(base, install_recorders(base, []))
    killed = 0
    for mutate in mutants:
        e = EE(elf)
        recorders = install_recorders(e, [])
        mutate(e)
        try:
            assert_unstubbed(e, recorders)
        except StubbedBoot:
            killed += 1
        else:
            raise AssertionError('no-stubs check survived a mutant')
    return killed


def boot_sif(elf, mutate=None):
    e = EE(elf)
    e.record_calls = False
    e.install_modelled_gs_privileged()
    e.install_deci2_kputs()
    e.install_modelled_boot()
    e.install_modelled_intc(while_disabled=True)
    e.install_ram_mirrors()
    e.install_modelled_main_ram()
    e.install_modelled_dma_idle()
    e.install_modelled_vpu_stat()
    e.install_modelled_flush_cache()
    e.install_modelled_end_of_heap()
    e.install_modelled_sif(while_disabled=True)
    if mutate is not None:
        mutate(e)
    e.writes.clear()
    e.record_writes = True
    e.write_watch = R7.WATCH
    try:
        e.call(e.entry, max_steps=4000000)
    except MemoryFault as exc:
        assert (exc.pc, exc.addr, exc.size, exc.kind) == (0x35c108, 0x80000000, 4, 'read'), exc
    else:
        raise AssertionError('entry returned')
    assert e.writes == R7.BSS_CLEAR, e.writes
    assert e.sif_transfers == [] and e.sif_reg_writes == [] and e.sif_deliveries == []

    # Plant sentinels after crt0's .bss clear, then record every store to them.
    for addr in PLANTED:
        e.mem.w32(addr, SENTINEL)
    e.writes.clear()
    e.write_watch = WATCH
    assert (e.r[28] & 0xffffffff) == R7.GP
    e.r[29] = e.stack_hi - 0x100
    hits = []
    recorders = install_recorders(e, hits)
    try:
        e.call(R7.ENGINE_INIT, max_steps=200000000)
    except CpuTrap as exc:
        assert 'SYSCALL at 0x00352a24 (v1 = 68, a0 = 5)' in str(exc), exc
        assert 'modelled WaitSema count is 0' in str(exc), exc
    else:
        raise AssertionError('engine_init passed the bind wait')
    assert e.cur == 0x352a24 and (e.r[31] & 0xffffffff) == 0x3565f4

    # Call order.  a1 is shown only where the callee reads it.
    seen = [(addr, ra, a0) for addr, ra, a0, _a1 in hits]
    assert seen == [
        (INIT_RPC, 0x19bab0, 0),
        (INIT_CMD, 0x355db8, 0),
        (DMAC_HANDLER, EE.RETURN_ADDR, 5),
        (SET_SREG, 0x355c90, seen[3][2]),
        (GET_SREG, 0x355ec8, 0),
        (CD_INIT, 0x19bac8, 0),
        (INIT_RPC, 0x361c14, 0),
        (BIND_RPC, 0x361c9c, CD_CLIENT),
    ], [tuple(hex(v) for v in item) for item in seen]
    assert hits[-1][3] == 0x80000592
    assert hits[3][3] == CMD_DATA

    # The three commands handed to SetDma, all at ra 0x355acc, all to the placeholder.
    cmds = [(src, dest, size, attr, struct.unpack_from('<I', data, 8)[0],
             struct.unpack_from('<I', data, 12)[0], data[0])
            for _ra, src, dest, size, attr, data in e.sif_transfers]
    assert [t[0] for t in e.sif_transfers] == [0x355acc] * 3
    assert cmds == [
        (0x8ef100, PH, 0x14, 0x44, 0x80000002, 0, 0x14),
        (0x8ef380, PH, 0x10, 0x44, 0x80000002, 1, 0x10),
        (0x208ef340, PH, 0x40, 0x44, 0x80000009, 0, 0x40),
    ], cmds
    # sceSifInitCmd's packet carries its receive buffer; the bind packet carries
    # the client and the server number.
    first = e.sif_transfers[0][5]
    assert struct.unpack_from('<I', first, 0x10)[0] == 0x8ef040
    bind = e.sif_transfers[2][5]
    assert struct.unpack_from('<II', bind, 0x1c) == (CD_CLIENT, 0x80000592)
    assert e.sif_reg_writes == [(0x35582c, 0x80000000, PH), (0x35583c, 0x80000001, CMD_DATA),
                                (0x19bab0, 0x80000002, 1)], e.sif_reg_writes
    # Delivered with Status 0x10000 (EIE from the EI at 0x35c044, reached from
    # the call at 0x355e7c, the last of three EI/DI pairs; IE clear):
    # a modelled exception the CPU state does not allow.
    assert e.sif_deliveries == [(5, DMAC_HANDLER, 0x80000001, 0, 1, 0x10000)], e.sif_deliveries
    assert e.mem.u32(CMD_DATA) == 0x208ef040
    # The size byte the handler clears at 0x355bb8.
    assert e.mem.u8(0x8ef040) == 0

    # Recorded stores, and the words left planted.
    assert e.writes == EXPECTED_WRITES, [tuple(hex(v) for v in w) for w in e.writes]
    assert e.mem.u32(SREG0) == 1 and e.mem.u32(SUBADDR_WORD) == PH
    assert e.mem.u32(CD_SERVER) == 0
    for addr in (CD_MODE, CD_RESULT, CD_RESULT + 4, CD_RESULT + 8, CD_RESULT + 12):
        assert e.mem.u32(addr) == SENTINEL, hex(addr)
    assert e.mem.u32(R7.RING_SLOT) == 0 and e.mem.u32(R7.PARTICLE_WORD) == 0
    # The D_STAT and D5_CHCR words were read, never written.
    assert 0x1000e010 not in e._hw_words and 0x1000c000 not in e._hw_words
    assert e._semas[5] == {'count': 0, 'max': 1}
    assert e.intc_deliveries == [(2, R7.HANDLER, 4)] * 5, e.intc_deliveries
    assert e.intc_delivery_status == [0] * 5, e.intc_delivery_status
    assert e.gs_reads == [(0x34f780, 0x12001000, 0)] + [(0x19b8d8, 0x12001000, 0)] * 5, e.gs_reads
    # e.calls is empty here (record_calls is False), so this line cannot fail;
    # assert_unstubbed is the check (audit R8-8).
    assert not any(c.stubbed for c in e.calls)
    assert_unstubbed(e, recorders)
    e.write_watch = R7.WATCH
    e.writes.clear()
    return e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--mutate-boot', action='store_true',
                        help='run the boot once with a stub at the unreached IOP reset '
                             '0x35bd08 and require the no-stubs check to fail')
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == SHA
    killed = mutation_controls(args.elf)
    if args.mutate_boot:
        try:
            boot_sif(args.elf, mutate=lambda e: e.stub(UNREACHED_RESET))
        except StubbedBoot as exc:
            print('PASS death-reload sif mutation: a boot with a stub at 0x%x reaches the '
                  'bind wait and fails only the no-stubs check (%s); %d in-process mutants '
                  'killed' % (UNREACHED_RESET, exc, killed))
            return
        raise AssertionError('the mutated boot passed the no-stubs check')
    for qualified in (False, True):
        R7.reload_after(args.elf, random.Random(args.seed), qualified, boot=boot_sif)
    print('PASS death-reload sif: 2 engine_init bind waits on server 0x80000592 '
          '(3 SetDma commands, 1 modelled set-register packet), 2 particle-reset faults; '
          'no-stubs check killed %d of 4 mutants' % killed)


if __name__ == '__main__':
    main()
