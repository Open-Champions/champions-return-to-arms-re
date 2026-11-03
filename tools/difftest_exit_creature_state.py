#!/usr/bin/env python3
"""Counts-only, no-stub EE comparisons for bounded base Creature save/load.

  PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_creature_state \
      local/SLUS_209.73 --seed 20973

Every load uses independently authored payload/table bytes and a fresh
separately allocated destination. No executable data is printed or exported.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
from pathlib import Path
import random
import struct
import sys
import unittest  # Preload stdlib dis before adding tools to sys.path.

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ee_emu import EE  # noqa: E402
import ref_exit_creature_state as R  # noqa: E402

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SAVE, LOAD = 0x116780, 0x116920
STR_START, STR_END, STR_LOAD = 0x5F86FC, 0x5F8700, 0x5F8704
NAME, MODEL_NAME, OTHER_NAME = b'SYN_BASE_ANIM', b'SYN_BASE_MODEL', b'SYN_OTHER_ANIM'
# Lazy original runtime type-information fields, outside the object oracle.
# Their contents are deliberately neither copied into this source nor asserted.
TYPE_FIELDS = {0x564318, 0x56431C, 0x908138, 0x908130, 0x908134,
               0x9083F8, 0x9083F0, 0x9083F4}


class Checks:
    def __init__(self):
        self.counts = Counter()
        self.calls = 0

    def equal(self, key, got, want):
        if got != want:
            raise AssertionError(f'{key} mismatch_count=1')
        self.counts[key] += 1

    def call(self, ee, addr, *args):
        self.equal('no_hooks_or_patches',
                   (len(ee.hooks), len(ee.patches), ee.follow, ee.mem.auto_map),
                   (0, 0, None, False))
        ee.calls.clear()
        ee.writes.clear()
        result = ee.call(addr, *args, max_steps=100000)
        self.calls += 1
        self.equal('stubbed_calls', sum(c.stubbed for c in ee.calls), 0)
        self.equal('automatic_mappings', len(ee.mem.auto_mapped), 0)
        return result


def put(blob, offset, size, value):
    blob[offset:offset + size] = (value & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')


def guarded(ee, size, rng):
    base = ee.alloc(size + 32)
    guard = bytes(rng.randrange(256) for _ in range(16))
    ee.mem.write(base, guard)
    ee.mem.write(base + 16 + size, guard)
    return base + 16, guard


def check_guard(checks, ee, addr, size, guard):
    checks.equal('guards', (ee.mem.read(addr - 16, 16), ee.mem.read(addr + size, 16)),
                 (guard, guard))


def fixture(ee, rng, source, mode):
    mem = ee.mem
    model, clip, cls = ee.alloc(0x40), ee.alloc(0x70), ee.alloc(0x30)
    length = rng.randrange(1, 257)
    mem.w32(clip + 4, length)
    names = []
    for value in (MODEL_NAME, NAME, OTHER_NAME):
        addr = ee.alloc(len(value) + 1)
        mem.write(addr, value + b'\0')
        names.append(addr)
    mem.w32(cls + 8, names[0])
    mem.w32(cls + 12, model)
    mem.w32(cls + 16, names[1])
    mem.w32(cls + 20, clip)
    src, srcguard = guarded(ee, R.SIZE, rng)
    dst, dstguard = guarded(ee, R.SIZE, rng)
    baseline = bytearray(R.SIZE)
    for off, size, value in ((0x48, 4, R.VTABLE), (0x24, 4, cls), (0x119, 1, 8),
                             (0x22C, 4, R.C.f32(rng.choice((50, 100, 200)))),
                             (0x228, 4, R.C.f32(73)), (0xE8, 4, rng.getrandbits(32)),
                             (0x220, 8, rng.getrandbits(64)), (0x231, 1, 0xA7),
                             (0x232, 2, 7), (0x11A, 2, 0x100),
                             (0xA8, 8, rng.getrandbits(64))):
        put(baseline, off, size, value)
    # Independent fields serve as preservation canaries, never pointer inputs.
    for off in (0x10, 0x14, 0x18, 0x44, 0xD0, 0xD4, 0x300, 0x304):
        put(baseline, off, 4, rng.getrandbits(32))
    mem.write(dst, baseline)
    for off, size, value in ((0x48, 4, R.VTABLE), (0x24, 4, cls),
                             (0x119, 1, 8), (0x118, 1, 1),
                             (0x11C, 4, clip if mode != 'absent' else ee.alloc(0x70)),
                             (0x22C, 4, source.maximum_hp), (0x228, 4, source.hp),
                             (0xE8, 4, source.variant), (0xA8, 8, source.cflags),
                             (0x231, 1, source.inert), (0x312, 2, source.charm)):
        mem.store(src + off, size, value)
    mem.w32(0x4D8AE0, 0)  # No players; not itself the charm gate.
    mem.w32(0x4F7120, 0)  # No external death-event object.
    return (src, dst, bytes(baseline), clip, length, cls, names,
            ((src, R.SIZE, srcguard), (dst, R.SIZE, dstguard)))


def pair(elf, rng, checks, source, mode, table_mode):
    ee = EE(elf)
    mem = ee.mem
    src, dst, baseline, clip, length, cls, names, guards = fixture(ee, rng, source, mode)
    buffer, bufguard = guarded(ee, 64, rng)
    table, tabguard = guarded(ee, 256, rng)
    tail = bytes(rng.randrange(256) for _ in range(64))
    table_tail = bytes(rng.randrange(256) for _ in range(256))
    initial_names = () if table_mode == 0 else ((b'SYN_PREFIX',) if table_mode == 1 else
                                               (b'SYN_PREFIX', NAME))
    initial_table, _ = R.intern_synthetic(initial_names)
    dead = R.C.to_float(source.hp) <= 0
    table_names = initial_names + ((NAME,) if dead and mode != 'absent' else ())
    expected_table, offsets = R.intern_synthetic(table_names)
    animation_offset = offsets[-1] if dead and mode != 'absent' else -1
    expected_payload = R.save_payload(source, animation_offset)
    mem.write(buffer, tail)
    mem.write(table, initial_table + table_tail[len(initial_table):])
    mem.w32(STR_START, table)
    mem.w32(STR_END, table + len(initial_table))
    before_source = mem.read(src, R.SIZE)
    checks.equal('save_size', checks.call(ee, SAVE, src, buffer), len(expected_payload))
    checks.equal('save_payload_and_tail', mem.read(buffer, 64),
                 expected_payload + tail[len(expected_payload):])
    checks.equal('save_string_table_and_tail', mem.read(table, 256),
                 expected_table + table_tail[len(expected_table):])
    checks.equal('save_string_cursor', mem.u32(STR_END), table + len(expected_table))
    expected_word_writes = [(i, 4, int.from_bytes(expected_payload[i:i + 4], 'little'))
                            for i in range(0, len(expected_payload), 4)]
    checks.equal('save_payload_writes', [(a - buffer, s, v) for _, a, s, v in ee.writes
                                        if buffer <= a < buffer + 64], expected_word_writes)
    checks.equal('save_source_preserved', mem.read(src, R.SIZE), before_source)
    checks.equal('save_destination_preserved', mem.read(dst, R.SIZE), baseline)
    checks.equal('save_write_bounds', sum(not (
        buffer <= a and a + s <= buffer + len(expected_payload) or
        table <= a and a + s <= table + len(expected_table) or a == STR_END and s == 4)
        for _, a, s, _ in ee.writes), 0)
    targets = Counter(call.target for call in ee.calls)
    checks.equal('original_string_intern', targets[0x14DE60], int(dead and mode != 'absent'))
    for args in (*guards, (buffer, 64, bufguard), (table, 256, tabguard)):
        check_guard(checks, ee, *args)

    # The load inputs come from the reference, never from bytes read after save.
    mem.write(buffer, expected_payload + tail[len(expected_payload):])
    mem.write(table, expected_table + table_tail[len(expected_table):])
    mem.w32(STR_LOAD, table)
    if mode == 'unmatched':
        mem.w32(cls + 16, names[2])
    expected = R.restore_fresh(baseline, expected_payload, clip=clip, length=length,
                               animation_matches=mode == 'match')
    checks.equal('load_size', checks.call(ee, LOAD, dst, buffer), expected.consumed)
    checks.equal('load_object_image', mem.read(dst, R.SIZE), expected.image)
    checks.equal('load_object_writes', tuple((a - dst, s, v) for _, a, s, v in ee.writes
                                           if dst <= a < dst + R.SIZE), expected.writes)
    checks.equal('load_external_write_bounds', sum(not (
        dst <= a and a + s <= dst + R.SIZE or a in TYPE_FIELDS and s == 4)
        for _, a, s, _ in ee.writes), 0)
    checks.equal('load_source_preserved', mem.read(src, R.SIZE), before_source)
    checks.equal('load_payload_preserved', mem.read(buffer, 64),
                 expected_payload + tail[len(expected_payload):])
    checks.equal('load_string_table_preserved', mem.read(table, 256),
                 expected_table + table_tail[len(expected_table):])
    targets = Counter(call.target for call in ee.calls)
    for addr, count in ((0x11A668, 1), (0x179550, 1), (0x14F290, int(dead)),
                        (0x14F688, int(dead)), (0x1707B0, int(expected.animated)),
                        (0x170838, int(expected.animated)), (0x170BC8, int(expected.animated)),
                        (0x10BEB8, int(expected.animated))):
        checks.equal('original_restore_callees', targets[addr], count)
    checks.equal('fresh_charm_retained_zero', mem.u16(dst + 0x312), 0)
    for args in (*guards, (buffer, 64, bufguard), (table, 256, tabguard)):
        check_guard(checks, ee, *args)
    checks.counts['dead_pairs' if dead else 'live_pairs'] += 1
    checks.counts['animated_pairs'] += int(expected.animated)
    checks.counts['no_animation_pairs'] += int(dead and not expected.animated)
    return baseline, expected_payload, clip, length


def refusals(checks, baseline, payload, clip, length):
    source = R.Source(0, R.C.f32(50), R.C.f32(100))
    calls = [lambda maximum=maximum: R.save_payload(replace(source, maximum_hp=maximum), -1)
             for maximum in (0, R.C.f32(-1), 0x7F800000, 1)]
    calls += [lambda: R.save_payload(replace(source, charm=32768), -1),
              lambda: R.save_payload(replace(source, hp=0x7FC00000), -1),
              lambda: R.save_payload(replace(source, hp=0x00800000,
                                               maximum_hp=0x7F7FFFFF), -1),
              lambda: R.save_payload(replace(source, hp=0x7F7FFFFF,
                                               maximum_hp=0x00800000), -1),
              lambda: R.intern_synthetic((b'X' * 128,))]
    for off, size, value in ((0x48, 4, 0), (0x0C, 4, 0x20), (0x0C, 4, 0x40),
                             (0x312, 2, 0xFFFF), (0x119, 1, 0), (0x114, 4, 1),
                             (0x22C, 4, 0), (0x22C, 4, R.C.f32(-1))):
        altered = bytearray(baseline)
        put(altered, off, size, value)
        calls.append(lambda image=bytes(altered): R.restore_fresh(
            image, payload, clip=clip, length=length, animation_matches=True))
    calls += [lambda: R.restore_fresh(baseline, payload[:-1], clip=clip, length=length,
                                     animation_matches=True),
              lambda: R.restore_fresh(baseline, payload + b'\0' * 4, clip=clip,
                                     length=length, animation_matches=True)]
    unknown_flags = bytearray(payload)
    flag_offset = 12 if R.C.to_float(R.read(payload, 4, 4)) <= 0 else 8
    put(unknown_flags, flag_offset, 4, R.read(payload, flag_offset, 4) | 0x80)
    calls.append(lambda: R.restore_fresh(baseline, bytes(unknown_flags), clip=clip,
                                         length=length, animation_matches=True))
    for call in calls:
        try:
            call()
        except R.Refusal:
            checks.counts['reference_refusals'] += 1
        else:
            raise AssertionError('reference_refusal mismatch_count=1')


def run(elf, seed):
    rng, checks = random.Random(seed), Checks()
    all_flags = sum(R.SAVED_CFLAGS)
    cases = [(hp, charm, all_flags if enabled else 0, enabled, 'match')
             for hp in (50, 0, -1) for charm in (0, 60, -1) for enabled in (0, 1)]
    # One-hot mappings, unrelated bit exclusion, and preexisting destination bits.
    cases += [(hp, 0, mask, 0, 'match') for hp in (50, 0)
              for mask in (*R.SAVED_CFLAGS, 1 << 31)]
    cases += [(hp, 0, 0, 1, 'match') for hp in (50, 0)]
    cases += [(hp, 0, all_flags, 1, mode) for hp in (0, -1)
              for mode in ('absent', 'unmatched')]
    for index, (hp, charm, flags, inert, mode) in enumerate(cases):
        source = R.Source(rng.getrandbits(32), R.C.f32(hp), R.C.f32(100),
                          flags, inert, charm)
        last = pair(elf, rng, checks, source, mode, index % 3)
    refusals(checks, *last)
    groups = {k: v for k, v in checks.counts.items()
              if k.endswith('_pairs') or k == 'reference_refusals'}
    assertions = sum(v for k, v in checks.counts.items() if k not in groups)
    print(f'PASS seed={seed} pairs={len(cases)} entry_calls={checks.calls} assertions={assertions}')
    print(' '.join(f'{key}={value}' for key, value in sorted(groups.items())))
    print('stubbed_calls=0 patches=0 auto_mapped_pages=0 failures=0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default='local/SLUS_209.73')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    if hashlib.sha256(Path(args.elf).read_bytes()).hexdigest() != SHA256:
        print('REFUSE executable_identity_failures=1')
        return 2
    run(args.elf, args.seed)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # Interpreter exceptions can contain original instructions. Fail closed
        # without leaking bytes, strings, payloads, or trace details.
        print('FAIL failures=1')
        raise SystemExit(1)
