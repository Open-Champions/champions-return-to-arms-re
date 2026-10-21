#!/usr/bin/env python3
"""Execute the original request-name split and the two downstream name tests.

The bounded mainloop stretch begins with the request already copied into
g_levelName and s3 holding the underscore index, as established by the
preceding mainloop code. Only synthetic short names are written into memory.
"""
import hashlib
import sys

from ee_emu import EE


EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def check(path):
    with open(path, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256, 'wrong executable revision'
    for request, base, scale in (
        ('stomedal_sub', 'stomedal', 0x3f800000),
        ('innpit_sub', 'innpit', 0x40000000),
        ('blomedal_sub', 'blomedal', 0x40a00000),
    ):
        ee = EE(path)
        ee.mem.write(0x41b6d0, request.encode('ascii') + b'\0')
        ee.mem.write(0x41b721, request.encode('ascii') + b'\0')
        ee.set_reg('s3', request.index('_'))
        assert ee.run(0x3210c0, until=(0x321118,), max_steps=1000) == 'stop'
        assert ee.mem.cstr(0x41b721) == base
        assert ee.mem.cstr(0x44fe18) == base

        # game_loadLevel's level-scale stretch uses the split g_levelName.
        ee.mem.w32(0x4f719c, 1)
        ee.mem.w32(0x4f7120, 0)
        ee.r[4] = 5  # an authored table byte that would ordinarily give level 5
        ee.r[22] = ee.r[16] = ee.r[7] = 0x4f0000
        ee.r[23] = 0x41b721
        ee.r[3] = ee.r[5] = 0
        assert ee.run(0x1e5b88, until=(0x1e5c98, 0x1e5c9c), max_steps=3000) == 'stop'
        assert ee.mem.u32(0x4f714c) == scale

        # Skelight compares g_levelTexName, rather than the unsplit request.
        ee.set_reg('s0', 0x4f0000)
        assert ee.run(0x2a88e0, until=(0x2a8900,), max_steps=3000) == 'stop'
        assert (ee.reg('v0') == 0) == (base == 'blomedal')
        print('PASS request %s: stored base %s, level=%#x, Skelight match=%s' % (
            request, base, scale, base == 'blomedal'))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: difftest_level_name_split.py OWNER_ELF')
    check(sys.argv[1])
