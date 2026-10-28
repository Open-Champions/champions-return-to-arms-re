#!/usr/bin/env python3
"""Pinned original-function appearance probes; emits counts, never asset text.

Run with unittest preloaded before inserting tools/ in sys.path. ELF and ISO
must be owner inputs under local/. Resource lookup is a read-only membership
oracle with synthetic handles. No rendering, I/O timing or game boot claimed.
"""
import argparse
import hashlib
import itertools
import mmap
from pathlib import Path
import random

from anim_audio_info import iso_files, lmp_entries
from ee_emu import EE
import ref_char_appearance as ref

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ROWS, MENU, RECORD, STRIDE = 0x4fbbf8, 0x4fdb80, 0x4d8af0, 0x4c30
CHOICES = (0x8e2bc0, 0x8e2bd0, 0x8e2be0, 0x8e2bf0)
COUNT_FORMATS = (0x5406e8, 0x5406f8, 0x540708, 0x540718, 0x540728)
PART_FORMATS = (0x535b78, 0x535b88, 0x535b98, 0x535ba8, 0x535bc0, 0x535bd0)
HANDLES = (0x544, 0x548, 0x54c, 0x550, 0x554, 0x558)
# Count-only expectations for the pinned retail archive survey, in carousel
# rows 1..12. The second archive's row 2 stops at its first mesh gap.
EXPECTED_COUNTS = ((4, 4, 3, 4), (5, 4, 1, 1), (5, 5, 3, 5),
                   (4, 6, 3, 1), (4, 5, 3, 1), (4, 6, 3, 1),
                   (4, 6, 3, 1), (4, 6, 3, 1), (4, 4, 3, 4),
                   (4, 5, 3, 1), (4, 5, 3, 5), (4, 7, 3, 1))


def check(condition, label):
    # Do not leak private names through assert tuple reprs.
    if not condition:
        raise AssertionError(label)


def string(mem, address):
    return mem.cstr(address & 0xffffffff)


def fresh(elf, seed):
    emu = EE(elf)
    # follow=None executes every unstubbed call; unmapped memory is fatal.
    emu.mem.map(0x8e2000, 0x1000)
    emu.r[29] = emu.STACK_HI - 0x2000  # room above SP for bounded caller frames
    emu.mem.w32(0x404464, seed)
    emu.mem.w8(0x8e2c91, -1)
    return emu


def boundary(emu, start, stop):
    check(emu.run(start, until=(stop,), max_steps=500000) == 'stop', 'slice exit')
    check(emu.pc == stop, 'slice stop address')


def archives(elf, iso):
    emu = fresh(elf, 0)
    result = {}
    with open(iso, 'rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as image:
        files = iso_files(image)
        for address in (0x5353e0, 0x535b68):
            wanted = string(emu.mem, address).lower()
            matches = [record for path, record in files.items()
                       if path.rsplit('/', 1)[-1].lower() == wanted]
            check(len(matches) == 1, 'archive identity')
            offset, size = matches[0][:2]
            result[address] = {name.lower() for name, _, _ in
                               lmp_entries(image[offset:offset + size])}
    return result


def lookup_oracle(emu, archive_address, entries, missing=False):
    requests, returned = [], []

    def lookup(machine):
        check(string(machine.mem, machine.r[4]) == string(machine.mem, archive_address),
              'archive selection')
        name = string(machine.mem, machine.r[5])
        requests.append(name)
        handle = 0 if missing or name.lower() not in entries else 0x1000000 + 16 * len(requests)
        returned.append(handle)
        return handle

    emu.stub(0x17365c, function=lookup)
    return requests, returned


def discover(elf, seed, archive_address, entries):
    emu = fresh(elf, seed)
    emu.mem.w32(0x8e2c8c, archive_address)
    formats = tuple(string(emu.mem, a) for a in COUNT_FORMATS)
    requests, returned = lookup_oracle(emu, archive_address, entries)
    rows = {}
    for row in range(1, 13):
        base = ROWS + row * 0x26c
        model = emu.mem.s8(base + 0x10)
        prefix = string(emu.mem, emu.mem.u32(0x4ebbb8 + model * 4))
        optional = emu.mem.s8(base + 0x12)
        expected, expected_requests = ref.scan_variants(
            prefix, formats, entries, optional, emu.mem.s8(base + 0x1a))
        requests.clear()
        returned.clear()
        emu.call(0x22b978, row)
        counts = tuple(emu.mem.s8(base + offset) for offset in (0x18, 0x19, 0x1a, 0x1b))
        check(counts == expected, 'scanner counts')
        retail = ((5, 2, 1, 1) if row == 2 and archive_address == 0x535b68
                  else EXPECTED_COUNTS[row - 1])
        check(counts == retail, 'retail archive count survey')
        check(requests == expected_requests, 'scanner ordered requests')
        rows[row] = (model, optional, counts)
    return rows


def control_cases(elf, seed, rows, archive_address, entries):
    emu = fresh(elf, seed)
    scratch = emu.alloc(0x1600)
    emu.mem.w32(0x4fdb7c, scratch)
    emu.mem.w32(0x8e2c8c, archive_address)
    requests, returned = lookup_oracle(emu, archive_address, entries)
    count = 0
    for row, (model, optional, counts) in rows.items():
        base = ROWS + row * 0x26c
        body, hair, colour, beard = counts
        for i, value in enumerate(counts):
            emu.mem.w8(base + 0x18 + i, value)
        obj = emu.alloc(0x440)
        emu.mem.w32(scratch + 0x1558 + 4 * row, obj)
        prefix = string(emu.mem, emu.mem.u32(0x4ebbb8 + model * 4))
        bounds = ((-int(bool(optional)), hair - 1 - bool(optional), 0, 0x22b720),
                  (0, colour - 1, 0, 0x22b7e8),
                  (-1, beard - 2, -1, 0x22b890), (0, body - 1, 0, 0x22b580))
        for kind, (lower, upper, reset, entry) in enumerate(bounds):
            for current, delta in itertools.product(range(lower - 1, upper + 3), (-2, -1, 0, 1, 2)):
                emu.mem.w8(CHOICES[kind] + row, current)
                requests.clear()
                returned.clear()
                expected, accepted = ref.adjust(current, delta, lower, upper, reset)
                actual = emu.call(entry, row, delta)
                check(actual == accepted and emu.mem.s8(CHOICES[kind] + row) == expected,
                      'control bounds or reset')
                if kind == 3:
                    wanted = [string(emu.mem, 0x5406d8) % prefix,
                              string(emu.mem, 0x5406e8) % (prefix, expected + 1)]
                    check(requests == wanted, 'skin preview ordered requests')
                    check((emu.mem.u32(obj + 0x428), emu.mem.u32(obj + 0x42c)) == tuple(returned),
                          'skin preview handles')
                else:
                    check(not requests, 'non-skin control resource side effect')
                count += 1
        for skin in range(-1, body + 1):
            emu.mem.w8(CHOICES[3] + row, skin)
            emu.mem.w8(CHOICES[0] + row, 77)
            emu.call(0x22e6a4, row)
            check(emu.mem.s8(CHOICES[0] + row) == ref.normalized_hair(skin), 'dependent hair')
            count += 1
    return count


def handoff_cases(elf, seed, rows, archive_address, entries):
    rng = random.Random(seed)
    emu = fresh(elf, seed)
    # Initializer executes fully; only unrelated stat/equipment services are stubbed.
    for address in (0x1bec10, 0x1b6458, 0x1acc78, 0x1bf770, 0x1bf6d0):
        emu.stub(address)
    emu.stub(0x14a4f0)  # Constructor light registration, outside the resource slice.
    requests, returned = lookup_oracle(emu, archive_address, entries)
    formats = tuple(string(emu.mem, address) for address in PART_FORMATS)
    obj = emu.alloc(0x590)
    count = misses = 0
    for row, (model, optional, limits) in rows.items():
        base = ROWS + row * 0x26c
        body, hair, colours, beard = limits
        for i, value in enumerate(limits):
            emu.mem.w8(base + 0x18 + i, value)
        hair_values = range(-int(bool(optional)), max(1, hair - int(bool(optional))))
        beard_values = range(-1, max(0, beard - 1))
        candidates = [(0, 0, -1, 0),
                      (hair_values[-1], max(0, colours - 1), beard_values[-1], body - 1)]
        candidates += [(rng.choice(hair_values), rng.randrange(max(1, colours)),
                        rng.choice(beard_values), rng.randrange(body)) for _ in range(4)]
        if model == 10:
            candidates += [(0, 0, -1, skin) for skin in range(body)]
        for choices in candidates:
            normalized = ((ref.normalized_hair(choices[3]),) + choices[1:]
                          if model == 10 else choices)
            expected = ref.appearance_record(normalized, hair, optional)
            for route in ('pending', 'confirmation'):
                slot = rng.randrange(4) if route == 'pending' else 0
                for index in range(4):
                    emu.mem.write(MENU + index * 0x2c, bytes(0x2c))
                menu = MENU + slot * 0x2c
                emu.mem.write(menu, b'probe\0')
                emu.mem.w8(menu + 0x20, row)
                emu.mem.write(menu + 0x25, bytes((31, 32, 33, 34)))
                for address, value in zip(CHOICES, choices):
                    emu.mem.w8(address + row, value)
                # The real skin-control caller normalizes only carousel row 2.
                emu.r[19], emu.r[22] = row, 4 * row
                boundary(emu, 0x2275dc, 0x2275f4)
                check(tuple(emu.mem.s8(address + row) for address in CHOICES) == normalized,
                      'caller-dependent normalization')
                # Appearance acceptance snapshot, with slot address prepared by
                # the caller. Stop before unrelated starting-stat allocation.
                emu.r[2], emu.r[19], emu.r[22] = slot * 0x2c, row, 0x500000
                boundary(emu, 0x226c68, 0x226cec)
                check(tuple(emu.mem.s8(menu + offset) for offset in (0x21, 0x22, 0x24, 0x23))
                      == normalized, 'selection snapshot')
                emu.reset_log()
                if route == 'pending':
                    emu.mem.w32(0x4fbbd8, 1)
                    emu.mem.w32(0x4d8ae0, slot + 1)
                    emu.call(0x2247ec)
                    check(emu.mem.u32(0x4fbbd8) == 0, 'pending clear')
                else:
                    emu.r[16], emu.r[19] = menu, ROWS
                    boundary(emu, 0x2285bc, 0x228620)
                init_calls = [call for call in emu.calls if call.target == 0x1b1d70]
                check(len(init_calls) == 1, 'single initializer call')
                rec = RECORD + slot * STRIDE
                check(emu.mem.u32(rec + 0x54) == model, 'carousel to model mapping')
                check(tuple(emu.mem.s8(rec + 0x20 + i) for i in range(4)) == expected,
                      'record appearance wiring')
                check(emu.mem.read(rec, 6) == b'probe\0', 'record name source')
                check(((emu.mem.u64(rec + 0x4c18) >> 32) & 31) ==
                      (1 if route == 'pending' else 2), 'record kind')
                # Begin after light setup, stop immediately after all six handles.
                # Registers describe the actual ctor entry state at 0x1a1ea0.
                for players, override in ((1, 0), (2, 0), (1, 1)):
                    selected = 0x535b68 if players >= 2 or override else 0x5353e0
                    if selected != archive_address:
                        continue
                    emu.mem.w32(0x4d8ae0, players)
                    emu.mem.w8(0x506040, override)
                    emu.r[21], emu.r[17], emu.r[23], emu.r[16] = obj, 0, slot, obj + 0x4c8
                    emu.r[4] = 1  # established at 0x1a1e94, consumed by 0x1a1ea4
                    requests.clear()
                    returned.clear()
                    boundary(emu, 0x1a1ea0, 0x1a21f8)
                    check(emu.mem.u8(obj + 0x565) == 1, 'constructor state-byte initialization')
                    prefix = string(emu.mem, emu.mem.u32(0x4ebbb8 + model * 4))
                    wanted = ref.constructor_requests(prefix, formats, expected)
                    check(requests == [name for _, name in wanted], 'constructor ordered requests')
                    handles = dict(zip((offset for offset, _ in wanted), returned))
                    check(all(emu.mem.u32(obj + offset) == handles.get(offset, 0) for offset in HANDLES),
                          'constructor output handles')
                    misses += returned.count(0)
                    count += 1
    return count, misses


def failure_controls(elf, seed, entries):
    """Explicit empty/gapped resource and handoff guards on synthetic state."""
    emu = fresh(elf, seed)
    emu.mem.w32(0x8e2c8c, 0x5353e0)
    formats = tuple(string(emu.mem, address) for address in COUNT_FORMATS)
    row, base = 3, ROWS + 3 * 0x26c
    prefix = string(emu.mem, emu.mem.u32(0x4ebbb8))
    cases = 0
    # A real member removed from the lookup oracle: later styles must not fill
    # the gap. Empty lookup also leaves the pre-existing colour count untouched.
    first_hair = formats[1] % (prefix, 1)
    second_hair = formats[1] % (prefix, 2)
    first_colour = formats[2] % (prefix, 1, 97)
    middle_colour = formats[2] % (prefix, 1, 98)
    last_style_colour = formats[2] % (prefix, 4, 98)
    for available in (set(), entries - {first_hair}, entries - {second_hair},
                      entries - {first_colour}, entries - {middle_colour},
                      entries - {last_style_colour}):
        emu.mem.w8(base + 0x1a, 6)
        expected, wanted = ref.scan_variants(prefix, formats, available, 1, 6)
        requests, _ = lookup_oracle(emu, 0x5353e0, available)
        emu.call(0x22b978, row)
        check(tuple(emu.mem.s8(base + offset) for offset in (0x18, 0x19, 0x1a, 0x1b))
              == expected and requests == wanted, 'scanner missing-resource control')
        cases += 1
    for pending, players in ((0, 4), (1, 0), (1, 4)):
        emu.mem.w32(0x4fbbd8, pending)
        emu.mem.w32(0x4d8ae0, players)
        for slot in range(4):
            # Disabled/zero-player cases keep valid nonempty selections, so
            # skipping for row zero cannot conceal a missing outer guard.
            emu.mem.w8(MENU + slot * 0x2c + 0x20, 0 if pending and players else row)
            emu.mem.write(RECORD + slot * STRIDE, bytes([0xa5]) * STRIDE)
        before = emu.mem.read(RECORD, 4 * STRIDE)
        emu.reset_log()
        emu.call(0x2247ec)
        check(not emu.calls and emu.mem.u32(0x4fbbd8) == 0, 'pending empty/disabled guard')
        check(emu.mem.read(RECORD, 4 * STRIDE) == before, 'guarded record preservation')
        cases += 1
    # Missing constructor entries must overwrite poisoned handles with null.
    obj = emu.alloc(0x590)
    formats = tuple(string(emu.mem, address) for address in PART_FORMATS)
    for choice in ((0, 0, 0, 0), (-1, 0, -1, 0)):
        emu.mem.w32(RECORD + 0x54, 0)
        emu.mem.write(RECORD + 0x20, bytes(x & 255 for x in choice))
        emu.mem.w32(0x4d8ae0, 1)
        emu.mem.w8(0x506040, 0)
        for offset in HANDLES:
            emu.mem.w32(obj + offset, 0x123456)
        requests, _ = lookup_oracle(emu, 0x5353e0, set())
        emu.stub(0x14a4f0)
        emu.r[21], emu.r[17], emu.r[23], emu.r[16] = obj, 0, 0, obj + 0x4c8
        emu.r[4] = 1
        boundary(emu, 0x1a1ea0, 0x1a21f8)
        check(emu.mem.u8(obj + 0x565) == 1, 'null-case constructor state byte')
        check(requests == [name for _, name in ref.constructor_requests(prefix, formats, choice)],
              'null constructor requests')
        check(all(emu.mem.u32(obj + offset) == 0 for offset in HANDLES), 'null handle clearing')
        cases += 1
    # Equality of hair-count and optional flag is the forced-absence predicate.
    for optional, hair_count in ((0, 0), (1, 1), (0, 1), (1, 2)):
        emu.mem.w8(base + 0x12, optional)
        emu.mem.w8(base + 0x19, hair_count)
        emu.mem.write(MENU + 0x20, bytes((row, 5, 2, 3, 1)))
        observed = []
        emu.stub(0x1b1d70, function=lambda m: observed.append(tuple(m.r[4:12])))
        emu.r[16], emu.r[19] = MENU, ROWS
        boundary(emu, 0x2285bc, 0x228620)
        check(len(observed) == 1 and (observed[0][3] & 255) ==
              (255 if hair_count == optional else 5), 'forced absent hair predicate')
        cases += 1
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('iso', type=Path)
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    check(hashlib.sha256(args.elf.read_bytes()).hexdigest() == SHA256, 'unsupported ELF revision')
    sets = archives(args.elf, args.iso)
    counts = {'scanner_rows': 0, 'control_cases': 0, 'handoff_constructor_cases': 0,
              'null_resource_returns': 0}
    for address, entries in sets.items():
        rows = discover(args.elf, args.seed, address, entries)
        counts['scanner_rows'] += len(rows)
        counts['control_cases'] += control_cases(args.elf, args.seed, rows, address, entries)
        cases, misses = handoff_cases(args.elf, args.seed, rows, address, entries)
        counts['handoff_constructor_cases'] += cases
        counts['null_resource_returns'] += misses
    counts['failure_controls'] = failure_controls(args.elf, args.seed, sets[0x5353e0])
    print('PASS seed=%d %s' % (args.seed, ' '.join('%s=%d' % item for item in counts.items())))


if __name__ == '__main__':
    main()
