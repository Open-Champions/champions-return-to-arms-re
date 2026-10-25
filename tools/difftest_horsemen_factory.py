#!/usr/bin/env python3
"""Execute the eight Horsemen factory rows through their constructor call.

Only the allocator and constructor are stubbed. The executable performs each
name comparison and sets the constructor arguments, including delay slots.
Supply an owner-owned RTA US v2.00 executable as the sole argument.
"""
import hashlib
import sys

from ee_emu import EE


EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROWS = (
    # class-string address, comparison entry, constructor call, variant, mounted
    (0x532cc8, 0x15b2d8, 0x15b3d4, 0, 1),
    (0x532cd8, 0x15b318, 0x15b3d4, 1, 1),
    (0x532ce8, 0x15b358, 0x15b3d4, 2, 1),
    (0x532cf8, 0x15b398, 0x15b3d4, 3, 1),
    (0x532dc8, 0x15b804, 0x15b900, 0, 0),
    (0x532dd8, 0x15b844, 0x15b900, 1, 0),
    (0x532de8, 0x15b884, 0x15b900, 2, 0),
    (0x532df8, 0x15b8c4, 0x15b900, 3, 0),
)


def check(path):
    with open(path, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable revision'
    for string_at, entry, site, variant, mounted in ROWS:
        ee = EE(path)
        # Copy a short identifier from the image into an authored input buffer.
        # No executable bytes or decoded class strings are written to this repo.
        name = ee.mem.cstr(string_at)
        name_at = ee.alloc(32)
        ee.mem.write(name_at, name.encode('ascii') + b'\0')
        object_at = ee.alloc(0x478)
        position_at = ee.alloc(16)
        props_at = ee.alloc(16)
        ee.stub(0x14fdb8, ret=object_at)
        ee.stub(0x271c70)
        ee.set_reg('s0', name_at)
        ee.set_reg('s2', 0x1234)
        ee.set_reg('s3', props_at)
        ee.set_reg('s4', position_at)
        ee.set_reg('a1', 0x530000)  # upper half loaded by the preceding row
        assert ee.run(entry, until=(site + 8,), max_steps=3000) == 'stop'
        calls = [call for call in ee.calls if call.target == 0x271c70]
        assert len(calls) == 1 and calls[0].site == site
        assert calls[0].args[:7] == (object_at, name_at, position_at,
                                    0x1234, props_at, variant, mounted), (hex(entry), calls[0].args[:7])
        print('PASS Horsemen factory row %d, mounted=%d, call=%#x' % (variant, mounted, site))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: difftest_horsemen_factory.py OWNER_ELF')
    check(sys.argv[1])
