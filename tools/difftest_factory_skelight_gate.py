#!/usr/bin/env python3
"""Bounded call-site comparisons on an owner-supplied RTA US v2.00 ELF."""
import sys
from ee_emu import EE


def check_factory(path):
    ee = EE(path)
    ee.stub(0x14fdb8, ret=0x1000000)  # pool_new: a synthetic allocated block
    ee.stub(0x2a8770)                 # inspect the constructor call boundary
    ee.set_reg('s1', 0x1000100)
    ee.set_reg('s2', 0x1000200)
    assert ee.run(0x15b5e4, until=(0x15b610,), max_steps=100) == 'stop'
    calls = [c for c in ee.calls if c.target == 0x2a8770]
    assert len(calls) == 1 and calls[0].site == 0x15b608
    assert calls[0].args[4] == 1, (calls[0].site, calls[0].args[:5])
    print('factory Skelight: 0x15b608 fifth argument = 1 (PASS)')


def check_gate(path):
    # The strcmp runs from the ELF. Only the external lump-residency service
    # is supplied, once with each result. No resource bytes are retained.
    for name, resident, expected in (
        ('intro', 0, 0x1e5730),
        ('INTRO', 0, 0x1e56c4),
        ('hub', 0, 0x1e56c4),
        ('hub', 1, 0x1e5708),
    ):
        ee = EE(path)
        world = ee.alloc(32)
        ee.mem.write(world, name.encode('ascii') + b'\0')
        ee.set_reg('s7', world)
        ee.stub(0x17306c, ret=resident)
        ee.stub(0x1713c0)
        ee.stub(0x108434)
        assert ee.run(0x1e5688, until=(0x1e56c4, 0x1e5708, 0x1e5730),
                      max_steps=3000) == 'stop'
        assert ee.pc == expected, (name, resident, ee.pc)
        calls = {c.site: c for c in ee.calls}
        assert calls[0x1e5690].target == 0x3b8534
        assert calls[0x1e5690].args[1] == 0x53d678
        assert (0x1e56a4 in calls) == (name != 'intro')
        if name != 'intro':
            assert calls[0x1e56a4].target == 0x17306c
            assert calls[0x1e56a4].args[0] == 0x53d680
        assert (0x1e56bc in calls) == (name != 'intro' and not resident)
        if 0x1e56bc in calls:
            assert calls[0x1e56bc].target == 0x108434
        print(f'item gate: {name}, hud resident={resident}, next={expected:#x} (PASS)')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: difftest_factory_skelight_gate.py OWNER_ELF')
    check_factory(sys.argv[1])
    check_gate(sys.argv[1])
