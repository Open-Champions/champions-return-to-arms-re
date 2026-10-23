#!/usr/bin/env python3
"""Compare player_resetIdleAnim's base-track stores with a small reference model.

Runs the original function in ee_emu on synthetic resolved pointers, on both
requested seeded case sets. No disc bytes or disassembly are written.
Usage: python3 tools/difftest_player_anim_select.py /path/to/SLUS_209.73 --seed N
"""
import argparse
import hashlib
import random

from ee_emu import EE
import ref_player_anim_select as model

EXPECTED_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
RESET = 0x1B2470
RELEASE = 0x171118


def one(elf, rng, weapon_class, alive, has_object):
    emu = EE(elf)
    mem = emu.mem
    player = emu.alloc(0x600)
    definition = emu.alloc(0x400)
    slot = rng.randrange(4)
    record = model.G_PLAYERS + slot * model.RECORD_SIZE
    mem.w32(record + 0x43D8, player if has_object else 0)
    mem.wf32(record + 0xAC, 10.0 if alive else 0.0)
    mem.w8(record + 0x4A86, weapon_class)
    mem.w32(player + 0x24, definition)
    mem.w8(player + 0x462, 0)
    words = {}
    for k in model.BASE_SLOTS:
        off = model.resource_offset(weapon_class, k)
        words[off] = (rng.getrandbits(28) | 0x20000000) & ~3
        mem.w32(definition + off, words[off])
    before = [mem.read(player + 0x11C + i * 0x20, 0x20) for i in range(4)]
    emu.stub(RELEASE, name='anim_releaseCaches')
    emu.follow = {RESET}
    emu.call(RESET, slot)
    if not alive or not has_object:
        return (all(mem.read(player + 0x11C + i * 0x20, 0x20) == before[i]
                    for i in range(4)) and not emu.calls, 'guard')
    expected = model.base_tracks(weapon_class, words.__getitem__)
    failures = []
    for i, (clip, weight, life, flags) in enumerate(expected):
        p = player + 0x11C + 0x20 * i
        got = (mem.u32(p), mem.u32(p + 8), mem.u32(p + 0x10), mem.u16(p + 0x1C))
        if got != (clip, weight, life, flags):
            failures.append((i, got, (clip, weight, life, flags)))
    if mem.u8(player + 0x118) != 4:
        failures.append(('count', mem.u8(player + 0x118)))
    if [c.target for c in emu.calls] != [RELEASE]:
        failures.append(('calls', [hex(c.target) for c in emu.calls]))
    return not failures, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error('requires SLUS_209.73 US v2.00 (SHA-256 mismatch)')
    rng = random.Random(args.seed)
    cases = failures = 0
    for weapon_class in range(8):
        for alive, has_object in ((True, True), (False, True), (True, False)):
            for _ in range(4):
                ok, detail = one(args.elf, rng, weapon_class, alive, has_object)
                cases += 1
                if not ok:
                    failures += 1
                    if failures <= 4:
                        print('FAIL class=%d alive=%s object=%s: %s' %
                              (weapon_class, alive, has_object, detail))
    print('%s player base selection seed=%d cases=%d mismatches=%d' %
          ('PASS' if failures == 0 else 'FAIL', args.seed, cases, failures))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
