#!/usr/bin/env python3
"""Original loading barrier slices; synthetic state, no private payload output."""
import hashlib
import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE
from difftest_loading import SHA256


def machine(path):
    e = EE(path)
    e.follow = set()
    e.mem.map(0x10000000, 4096)  # scratchpad/hardware write in warm-up slice
    return e


def deferred(path):
    cases = 0
    for parity in (0, 1, 7):
        for front, back in ((0, 0), (0, 2), (2, 0), (2, 3)):
            e = machine(path)
            e.follow = {0x1ED5A0}
            e.mem.w32(0x4F8690, parity)
            e.mem.w32(0x86DA78, front)
            e.mem.w32(0x86DA7C, back)
            calls = []
            e.stub(0x1ED694, function=lambda m: calls.append(m.r[4]) or 0)
            e.call(0x1EDA24)
            assert calls == [0x86B278 + (parity & 1) * 0x1400 + i * 0x50
                             for i in range(front)]
            assert e.mem.u32(0x86DA78) == back
            assert e.mem.u32(0x86DA7C) == 0
            assert e.mem.u32(0x4F8690) == parity + 1
            cases += 1
    # A callback queuing another callback is promoted, not drained recursively.
    e = machine(path)
    e.mem.w32(0x86DA78, 1)
    e.stub(0x1ED694, function=lambda m: m.mem.w32(0x86DA7C, 1) or 0)
    e.call(0x1ED5A0)
    assert e.mem.u32(0x86DA78) == 1 and e.mem.u32(0x86DA7C) == 0
    return cases + 1


def equipment(path):
    cases = 0
    # Actual scanner: generic item path reads model pair, no model builder stub.
    for pair in ((0, 0), (1, 0), (0, 1), (1, 1)):
        e = machine(path)
        player = e.alloc(0x400)
        item = e.alloc(0x48)
        definition = e.alloc(0x40)
        e.mem.w32(player + 0x3C8, 0)
        e.mem.w32(0x4D8AF0 + 0x43F0, item)
        e.mem.w32(item, definition)
        e.mem.w8(definition + 0x1C, 1)
        e.mem.w32(0x3E9CE0 + 8, pair[0])
        e.mem.w32(0x3E9CE0 + 12, pair[1])
        e.stub(0x1083F8, ret=0)
        assert e.call(0x1A30B0, player) == int(not all(pair)), pair
        cases += 1
    # Original warm-up body, including counter update and signed frame escape.
    for count, terrain, pending, elapsed in ((1, 0, 0, 0), (1, 0, 1, 0),
            (7, 0, 1, 0), (1, 1, 0, 0), (1, 1, 1, 1500),
            (1, 1, 1, 1501)):
        e = machine(path)
        e.mem.w32(0x506048, count)
        e.mem.w32(0x506080, 100)
        e.mem.w32(0x44FDD0, 100 + elapsed)
        e.mem.w32(0x4D8AE0, 1)
        e.mem.w32(0x4DCEC8, e.alloc(0x400))
        e.stub(0x17FE88, ret=terrain)
        e.stub(0x1A30B0, ret=pending)
        assert e.run(0x322EB0, until=(0x322FC8,), max_steps=10000) == 'stop'
        want = 10 if terrain else count - 1
        if pending:
            want = max(want, 3)
        if elapsed >= 1501:
            want = 0
        assert e.mem.u32(0x506048) == want
        cases += 1
    # Original async-cache lookup: a valid matching entry publishes both outputs;
    # an outstanding read younger than four frames leaves both outputs zero.
    for cached in (False, True):
        e = machine(path)
        e.follow = {0x3B8534}
        cache = e.alloc(0x58)
        name = e.alloc(32)
        out_a, out_b = e.alloc(4), e.alloc(4)
        e.mem.write(name, b'synthetic_model\0')
        e.mem.write(cache + 12, b'synthetic_model\0')
        e.mem.w16(cache + 10, int(cached))
        e.mem.w32(cache, 0x123400)
        e.mem.w32(cache + 0x4C, 0x80)
        e.mem.w32(0x4EF3EC, cache)
        e.mem.w32(0x4EF3F0, 100)
        e.mem.w32(0x44FDD0, 103)
        e.call(0x1A2D48, name, cache, out_a, out_b)
        assert e.mem.u32(out_a) == (0x123480 if cached else 0)
        assert e.mem.u32(out_b) == (0x123400 if cached else 0)
        cases += 1
    return cases


def peers(path):
    cases = 0
    for n, heard, flags in ((0, 0, (0, 0, 0)), (1, 0, (0, 0, 0)),
            (1, 1, (0, 0, 0)), (1, 0, (1, 0, 0)),
            (1, 0, (0, 1, 0)), (1, 0, (0, 0, 1)),
            (2, 1, (0, 0, 0))):
        e = machine(path)
        e.mem.w32(0x4027C4, n)
        for i in range(n):
            base = 0x5BF838 + i * 0x44E0
            e.mem.w32(base + 0x44D0, heard if i == 0 else 0)
            for j, flag in enumerate(flags):
                e.mem.w8(base + 0x44D4 + j, flag)
        expected = n == 0 or bool(any(flags)) or (n == 1 and bool(heard))
        assert bool(e.call(0x13E008)) == expected
        e.call(0x13DFC0)
        assert all(e.mem.u32(0x5BF838 + i * 0x44E0 + 0x44D0) == 0 for i in range(n))
        cases += 1
    for online, ready, stall in ((0, 0, 0), (1, 1, 0), (1, 0, 601)):
        e = machine(path)
        e.r[19] = 0x400000
        e.mem.w8(0x402791, online)
        e.mem.w32(0x40279C, stall)
        e.stub(0x13E008, ret=ready)
        assert e.run(0x323004, until=(0x323064,), max_steps=1000) == 'stop'
        targets = [c.target for c in e.calls]
        assert (0x13DFC0 in targets) == bool(online)
        assert (0x13E008 in targets) == bool(online)
        cases += 1
    return cases


def stores_save(path):
    cases = 0
    for address, mode in ((0x554678, 1), (0x554680, 1), (0x554688, 2),
                          (0x554698, 3), (None, None)):
        e = machine(path)
        e.follow = {0x3B8534}
        name = e.mem.cstr(address) if address else 'synthetic_nonstore'
        e.mem.write(0x41B721, name.encode() + b'\0')
        assert e.run(0x323064, until=(0x323104,), max_steps=10000) == 'stop'
        stock = [c for c in e.calls if c.target == 0x1C7AF8]
        assert len(stock) == int(mode is not None)
        if stock:
            assert stock[0].args[:3] == (0, mode, 1)
        cases += 1
    for busy in (0, 1, 255):
        e = machine(path)
        e.mem.w8(0x4F8F2C, busy)
        assert e.call(0x32393C) == int(busy == 0)
        assert [c.target for c in e.calls] == [0x222E10, 0x2189E0]
        cases += 1
    for online in (0, 1):
        for busy in (0, 1):
            e = machine(path)
            e.mem.w8(0x402791, online)
            e.mem.w8(0x4F8F2C, busy)
            e.r[19] = 0x400000
            assert e.run(0x322CE4, until=(0x322D20, 0x322D24), max_steps=1000) == 'stop'
            assert any(c.target == 0x3237F8 for c in e.calls) == bool(online and busy)
            cases += 1
    return cases


def main(path):
    with open(path, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == SHA256
    for check in (deferred, equipment, peers, stores_save):
        print('PASS %s cases=%d' % (check.__name__, check(path)))


if __name__ == '__main__':
    main(sys.argv[1])
