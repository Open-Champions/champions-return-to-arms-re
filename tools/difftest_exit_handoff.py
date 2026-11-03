#!/usr/bin/env python3
"""Counts-only EE comparisons for host/key prompts and level request handoff.

python3 -m tools.difftest_exit_handoff --seed 20973
No original instructions are patched. Script decoding/presentation are supplied;
actual handlers, host selector, properties and request/gate bodies run originally.
"""
import argparse
from collections import Counter
import hashlib
from itertools import product
from pathlib import Path
import random
import sys
import unittest  # Preload before adding tools (dis.py shadows stdlib).

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE
import ref_exit_handoff as R

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ACTIVE, SELECTED, PENDING, ORIENT = 0x4D8AE4, 0x4039F8, 0x41B6D0, 0x41B720
ENTRANCE, POST_NAME, POST_MODE = 0x4F8468, 0x86FA80, 0x4F8698
NETWORK, PLAYERS, CONNECTED, INACTIVE = 0x402791, 0x4D8AE0, 0x4027C4, 0x5C3D0D


class Probe:
    def __init__(self, elf):
        self.ee = EE(elf)
        self.mem = self.ee.mem
        self.counts = Counter()

    def string(self, value):
        addr = self.ee.alloc(len(value) + 1)
        self.mem.write(addr, value + b'\0')
        return addr

    def props(self, obj, values):
        at = self.ee.alloc(4 * (len(values) + 1))
        for i, value in enumerate(values):
            self.mem.w32(at + 4*i, self.string(value))
        self.mem.w32(obj + 0x2C, at)

    def equal(self, got, want):
        assert got == want, 'comparison mismatch_count=1'
        self.counts['assertions'] += 1

    def call(self, address, *args):
        self.ee.reset_log()
        result = self.ee.call(address, *args, max_steps=100000)
        self.equal((len(self.ee.patches), self.mem.auto_map,
                    len(self.mem.auto_mapped)), (0, False, 0))
        self.counts['entry_calls'] += 1
        return result


def host_and_prompt(elf, rng):
    p = Probe(elf)
    e, m = p.ee, p.mem
    # Real first-active-slot selector, including zero-player/all-inactive fallback.
    for network, count, connected, mask in product((0, 1), range(5), range(5), range(16)):
        inactive = [(mask >> i) & 1 for i in range(4)]
        m.w8(NETWORK, network)
        m.w32(PLAYERS, count)
        m.w32(CONNECTED, connected)
        for i, flag in enumerate(inactive):
            m.w8(INACTIVE + i*0x44E0, flag)
        p.equal(p.call(0x13E5A0), R.first_active(network, count, connected, inactive))
        p.counts['host_cases'] += 1
    obj, out = e.alloc(0x50), e.alloc(256)
    events, predicates = [], []
    values = ()
    def script(ee):
        name = m.cstr(ee.r[4])
        index = (b'SYN_KEY_A', b'SYN_KEY_B').index(name.encode('ascii'))
        predicates.append(index)
        return values[index]
    e.stub(0x1ED694, function=script)
    e.stub(0x173C84, function=lambda ee: ee.r[4])  # localization identity
    def copy_text(ee):
        name = m.cstr(ee.r[5])
        events.append(('text', name))
        m.w16(ee.r[4], 65)
        m.w16(ee.r[4] + 2, 0)
        return 0
    e.stub(0x19E854, function=copy_text)
    e.stub(0x1BDF60, function=lambda ee: events.append(('name', tuple(ee.r[4:8]))) or 0)
    def format_host(ee):
        events.append(('host', ee.r[4], ee.r[5]))
        m.w16(ee.r[4], 72)
        m.w16(ee.r[4] + 2, 0)
        return 0
    e.stub(0x19EA78, function=format_host)
    key_vectors = ((), (0,), (1,), (0, 1), (1, 0), (1, 1))
    for network, host_only, slot, host, text in product((0, 1), (0, 1), range(4), range(4), (0, 1)):
        m.w8(NETWORK, network)
        m.w32(PLAYERS, 4)
        m.w32(CONNECTED, 4)
        for i in range(4):
            m.w8(INACTIVE + i*0x44E0, int(i < host))
        for values in key_vectors:
            properties = [b'nethostonly=%d' % host_only]
            properties += [b'key=' + k for k in (b'SYN_KEY_A', b'SYN_KEY_B')[:len(values)]]
            if text:
                properties += [b'message=SYN_OK', b'lockmessage=SYN_LOCK',
                               b'nethostlockmessage=SYN_HOST_PROPERTY']
            p.props(obj, properties)
            active = rng.randrange(4)
            m.w32(ACTIVE, active)
            m.w32(SELECTED, 0x123456)
            m.write(out, bytes([0xAC]) * 256)
            events.clear()
            predicates.clear()
            usable, category, visited = R.keyed_prompt(
                network, host_only, slot, host, values, text, text, text)
            p.equal(p.call(0x1ECA94, obj, out, slot), usable)
            p.equal(tuple(predicates), visited)
            p.equal((m.u32(ACTIVE), m.u32(SELECTED)), (active, 0x123456))
            if category == 'host':
                # Property is only an enable switch: fixed localization key is used.
                p.equal(events, [('name', (0, host, 0x4D8AF0 + host*0x4C30, 8)),
                                 ('host', out, 0x53E2E0)])
            else:
                p.equal(events, [] if category is None else
                        [('text', 'SYN_OK' if category == 'message' else 'SYN_LOCK')])
            p.equal(m.u16(out), 72 if category == 'host' else 65 if category else 0)
            p.equal(m.read(out + 4, 252), bytes([0xAC]) * 252)
            p.counts['prompt_cases'] += 1
    return p.counts


def requests(elf, rng):
    p = Probe(elf)
    e, m = p.ee, p.mem
    obj, node = e.alloc(0x50), e.alloc(16)
    argument = b'SYN_DEST_BRANCH'
    argument_ptr = p.string(argument)
    def decode(ee):
        m.w32(ee.r[6], argument_ptr)
        return 0
    def convert(ee):
        p.equal(ee.r[5], argument_ptr)
        m.write(ee.r[4], argument + b'\0')
        return 0
    e.stub(0x1414A8, function=decode)
    e.stub(0x141650, function=convert)
    closed, notices = [], []
    e.stub(0x1EB000, function=lambda ee: closed.append(ee.r[4]) or 0)
    local = 0
    e.stub(0x13E150, function=lambda ee: local)
    e.stub(0x173C84, function=lambda ee: ee.r[4])
    e.stub(0x13E1F0, ret=3)
    e.stub(0x1D92A0, function=lambda ee: notices.append(tuple(ee.r[4:8])) or 0)
    # Exact lower-case prefix, final matching property wins, byte truncation.
    properties = ((), (b'orientation=7',), (b'orientation=-1',),
                  (b'orientation=260',), (b'orientation=5', b'orientation=9'),
                  (b'Orientation=17',), (b'unrelated=4',))
    orientation_values = ((), (7,), (-1,), (260,), (5, 9), (), ())
    for simple, network, active, cooldown, alive, post in product(
            (0, 1), (0, 1), (-1, 0, 3), (0, 1, 600), (1, 2), (0, 1)):
        index = rng.randrange(len(properties))
        p.props(obj, properties[index])
        has_selected = bool(rng.randrange(2))
        m.w32(SELECTED, obj if has_selected else 0)
        m.w32(ACTIVE, active)
        m.w8(NETWORK, network)
        m.w32(0x4F8420, alive)
        m.w8(POST_MODE, post)
        record = 0x4D8AF0 + max(active, 0)*0x4C30 + 0x4BCA
        m.w16(record, cooldown)
        before = bytes(rng.randrange(1, 256) for _ in range(0x51))
        m.write(PENDING, before)
        m.write(ENTRANCE, b'SYN_ENTRANCE\0')
        m.write(POST_NAME, b'SYN_POST\0')
        local = rng.randrange(2)
        closed.clear()
        notices.clear()
        allowed, timer, orient = R.request(network, active, cooldown, alive, post,
                                            simple, orientation_values[index] if has_selected else ())
        p.equal(p.call(0x143E70 if simple else 0x143DD0, 0, node), 0)
        expected = bytearray(before)
        if allowed:
            expected[:len(argument) + 1] = argument + b'\0'
            expected[0x50] = orient
        p.equal(m.read(PENDING, 0x51), bytes(expected))
        p.equal(m.u16(record), timer)
        p.equal(closed, [0] if allowed else [])
        p.equal(notices, [(0x531280, 180, 3, 0)] if not allowed and local else [])
        p.equal((m.cstr(ENTRANCE), m.cstr(POST_NAME)), ('SYN_ENTRANCE', 'SYN_POST'))
        p.equal((m.s32(ACTIVE), m.u32(SELECTED)), (active, obj if has_selected else 0))
        called = [c.target for c in e.calls if not c.stubbed]
        p.equal(0x143D04 in called, not post)
        p.equal(0x1472C4 in called, allowed and not simple)
        p.counts['request_cases'] += 1
    # Direct helper matrix ensures every property spelling/order/truncation case
    # is checked deterministically, without handler-decoder stubs.
    for props, values in zip(properties, orientation_values):
        p.props(obj, props)
        m.w32(SELECTED, obj)
        p.call(0x1472C4, argument_ptr)
        p.equal(m.u8(ORIENT), values[-1] & 255 if values else 255)
        p.equal(sum(c.stubbed for c in e.calls), 0)
        p.counts['orientation_cases'] += 1
    # Entrance and post action are separate named handoff buffers. Exercise the
    # original commands with independent decoded strings; preserve other buffers.
    for address, target in ((0x142A94, ENTRANCE), (0x143EE4, POST_NAME)):
        for argument in (b'SYN_SIDE_LONG_NAME', b'S', b''):
            argument_ptr = p.string(argument)
            before = {a: bytes(rng.randrange(1, 256) for _ in range(64))
                      for a in (ENTRANCE, POST_NAME, PENDING)}
            for a, data in before.items():
                m.write(a, data)
            p.equal(p.call(address, 0, node), 0)
            for a, data in before.items():
                expected = argument + b'\0' + data[len(argument) + 1:] if a == target else data
                p.equal(m.read(a, 64), expected)
            p.counts['side_buffer_cases'] += 1
    return p.counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seed', type=int, default=20973)
    ap.add_argument('--elf', default='local/SLUS_209.73')
    args = ap.parse_args()
    assert hashlib.sha256(Path(args.elf).read_bytes()).hexdigest() == SHA
    rng = random.Random(args.seed)
    counts = host_and_prompt(args.elf, rng) + requests(args.elf, rng)
    print('PASS exit_handoff seed=%d ' % args.seed +
          ' '.join('%s=%d' % x for x in sorted(counts.items())) + ' failures=0')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('FAIL exit_handoff failures=1')
        raise SystemExit(1)
