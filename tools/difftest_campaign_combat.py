#!/usr/bin/env python3
"""Execute the US v2.00 object factory against the hub reference model.

PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat.py \
    /path/to/SLUS_209.73 /path/to/HUB.GOB --seed 20973

The factory runs in ee_emu. String/property helpers run for real; pool_new and
constructors are recording stubs so this tests classification and constructor
selection, not object initialization or a live campaign fight. No game data is
embedded or written. A second seed changes probe order and checks that it has
no effect on independent factory decisions.
"""
import argparse
import hashlib
import random

from dump_tables import objects_from_file
from ee_emu import EE
from ref_campaign_combat import classify, hub_counts

EXPECTED_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
FACTORY, POOL_NEW, WORLD = 0x159C94, 0x14FDB8, 0x44FDC8


class RealCalls:
    def __contains__(self, addr):
        return addr in (FACTORY, 0x159C20, 0x14F730, 0x14F850) or 0x3A5000 <= addr < 0x3C0000


def put_string(emu, value):
    raw = value.encode("latin1") + b"\0"
    at = emu.alloc(len(raw))
    emu.mem.write(at, raw)
    return at


def original(emu, row):
    name = put_string(emu, row["class"])
    props = [put_string(emu, p) for p in row["properties"].split(";") if p]
    array = emu.alloc(4 * (len(props) + 1))
    for index, ptr in enumerate(props):
        emu.mem.w32(array + 4 * index, ptr)
    position = emu.alloc(12)
    emu.reset_log()
    result = emu.call(FACTORY, name, position, row["angle"], array, max_steps=500000)
    allocs = [call for call in emu.calls if call.target == POOL_NEW]
    named = [call for call in emu.calls if call.target not in
             (POOL_NEW, 0x159C20, 0x14F730, 0x14F850)
             and not 0x3A5000 <= call.target < 0x3C0000]
    if not allocs:
        return (result, None)
    if len(allocs) != 1 or not named:
        raise AssertionError("factory did not make one pool/constructor call")
    return (result, (allocs[0].args[0], named[-1].target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("hub_gob")
    parser.add_argument("--seed", type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, "rb") as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        parser.error("expected SLUS-20973 v2.00 SHA-256")
    with open(args.hub_gob, "rb") as stream:
        rows = objects_from_file(args.hub_gob, stream.read())
    if len(rows) != 24 or hub_counts(rows) != (16, 0):
        raise AssertionError("hub input no longer matches the observed 24/16/0 boundary")
    # Synthetic names reach the hostile factory branches without claiming that
    # these creatures appear in hub.
    probes = rows + [{"index": "synthetic:" + name, "class": name,
                       "angle": 0, "properties": ""}
                     for name in ("Gnaw", "SmallSpider", "Mosquito", "Scorpion", "Badger")]
    random.Random(args.seed).shuffle(probes)
    emu = EE(args.executable)
    emu.follow = RealCalls()
    block = emu.alloc(0x600)
    world = emu.alloc(0x100)
    emu.mem.w32(WORLD, world)  # PushTrigger reads world +0x70 before its ctor.
    emu.stub(POOL_NEW, ret=block, name="pool_new")
    for row in probes:
        expected = classify(row["class"], row["properties"].split(";"))
        returned, actual = original(emu, row)
        want = None if expected is None else expected[:2]
        if actual != want or returned != (block if want else 0):
            raise AssertionError("record %s %s: expected %r, got %r, result %#x" %
                                 (row["index"], row["class"], want, actual, returned))
    print("PASS seed %d: 24 hub records, 16 factory objects, 0 hostile; 5 synthetic creature branches" % args.seed)


if __name__ == "__main__":
    main()
