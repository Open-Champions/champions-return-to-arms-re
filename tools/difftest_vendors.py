#!/usr/bin/env python3
"""Bounded original vendor probes. Run with PYTHONDONTWRITEBYTECODE=1.

The original functions execute in ee_emu; constructed external services and
item values are explicit. No game data, text or disassembly is emitted.
"""
import hashlib
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE
from dump_tables import iso_files, objects_from_file
import ref_vendors as R

ELF = os.path.expanduser('~/champions-re/SLUS_209.73')
SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
DISC = os.path.expanduser('~/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso')
HUB_SHA = '1d5f240025afb86800040664a168c27c236a8431fc4c02caf388bdcee37b385f'
OPEN, TASK, CLOSE = 0x1C7AF8, 0x1C6068, 0x1D0AB8
BUY, MSG = 0x1D1240, 0x1C5D28


def emulator(path, seed):
    e = EE(path)
    e.mem.auto_map = True
    e.follow = set()                   # only the named entry runs; callees are recorded
    e.mem.w32(0x404464, seed)
    e.mem.w32(0x404460, seed)
    return e


def hub_vendor(disc):
    """Check only the relevant record and NPC count in the pinned private archive."""
    with open(disc, 'rb') as handle:
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            entries = [(off, size) for name, off, size in iso_files(mapped)
                       if name.upper() == '/BG/DATA/HUB.GOB']
            assert len(entries) == 1
            off, size = entries[0]
            blob = mapped[off:off + size]
            assert hashlib.sha256(blob).hexdigest() == HUB_SHA
            rows = objects_from_file('HUB.GOB', blob)
        finally:
            mapped.close()
    npcs = [row for row in rows if row['class'] == 'NPC']
    assert len(npcs) == 1 and npcs[0]['index'] == 10
    props = set(npcs[0]['properties'].split(';'))
    assert {'name=firiona', 'dialogscript=startDia3314', 'shop=1'} <= props


def open_close(path, seed):
    e = emulator(path, seed)
    e.stub(0x13E150, ret=1)           # local slot
    e.call(OPEN, 0, 0, 1, max_steps=500_000)
    calls = {(c.site, c.target) for c in e.calls}
    assert e.mem.u32(0x41B50C) == 1 and e.mem.u32(0x41B4F8) == 1
    assert e.mem.u32(0x41B4F4) == 1
    assert (0x1C89B4, 0x19E4A0) in calls  # draw task, priority 50
    audio = {(c.site, c.target, e.mem.cstr(c.args[1] & 0xFFFFFFFF, 80))
             for c in e.calls if c.site in (0x1C883C, 0x1C8854)}
    assert audio == {(0x1C883C, 0x17365C, 'coins.vag'),
                     (0x1C8854, 0x17365C, 'shoptick.vag')}
    e.reset_log()
    e.call(CLOSE)
    calls = {(c.site, c.target) for c in e.calls}
    assert e.mem.u32(0x41B50C) == 0 and e.mem.u32(0x41B4F8) == 0
    assert e.mem.u32(0x41B4F4) == 0 and e.mem.u32(0x41B4FC) == 60
    assert (0x1D0B58, 0x19E664) in calls  # task removal
    assert (0x1D0B4C, 0x1C54D0) in calls  # inventory resource unload


def screen(path, seed):
    e = emulator(path, seed)
    e.follow = {0x1C74C0, 0x1C7218, 0x1C7350, 0x1CB098, 0x1C6BB8}
    e.stub(0x13E150, ret=1)
    e.stub(0x1BFBC8, ret=1)           # inventory resource poll
    tex = e.alloc(0x40)
    e.mem.w16(tex, 32)
    e.mem.w16(tex + 2, 32)
    e.stub(0x17306C, ret=tex)
    names = []

    def resource(emu):
        names.append((emu._call_site, emu.mem.cstr(emu.r[5] & 0xFFFFFFFF, 80)))
        return tex

    e.stub(0x17365C, function=resource)
    e.call(OPEN, 0, 0, 1)
    e.reset_log()
    e.call(TASK)
    assert (0x1C6C4C, 'buttontop.tex') in names
    assert (0x1C6F50, 'buysell.tex') in names
    assert (0x1C6398, 'front.tex') in names
    calls = {(c.site, c.target) for c in e.calls}
    assert (0x1C75AC, 0x1CB098) in calls and (0x1C75B8, 0x1C6BB8) in calls
    assert any(c.site == 0x1C6CE0 and c.target == 0x1800B8 for c in e.calls)
    assert {(c.site, c.target, c.args[0], c.args[1]) for c in e.calls
            if c.site in (0x1C6D20, 0x1C6E8C)} == {
                (0x1C6D20, 0x181CA0, 160, 203),
                (0x1C6E8C, 0x181CA0, 160, 243)}
    placements = {c.site: tuple(c.args[1:4]) for c in e.calls
                  if c.site in (0x1C6C6C, 0x1C6F70, 0x1C63B4)}
    assert placements == {0x1C6C6C: (66, 210, 0),
                          0x1C6F70: (60, 174, 0),
                          0x1C63B4: (320, 0, 1)}


def prices(path, seed):
    checked = 0
    for category, slot, flags, gold, value, give_result in (
        (0, 0, 0, 1000, 100, 0),
        (1, 0, 0, 1000, 100, 0),
        (2, 0, 0, 1000, 100, -1),
        (0, 8, 0, 1000, 100, 0),
        (0, 0, 0x30000000000, 1000, 100, 0),
        (0, 0, 0, 40, 100, 0),
    ):
        e = emulator(path, seed)
        item, definition = e.alloc(0x48), e.alloc(0x40)
        e.mem.w32(item, definition)
        e.mem.w8(definition + 0x1C, slot)
        e.mem.w8(definition + 0x1D, category)
        e.mem.w64(item + 8, flags)
        e.mem.w32(R.PLAYER + 0xE4, gold)
        e.stub(0x1024A8, ret=value)
        e.stub(0x1C1868, ret=give_result)
        e.call(BUY, 0, item)
        price = R.buy_price(value, category, slot, flags)
        gave = [c for c in e.calls if c.target == 0x1C1868]
        assert e.mem.s32(R.PLAYER + 0xE4) == gold - (price if gold >= price else 0)
        assert len(gave) == int(gold >= price)
        checked += 1
    return checked


def sales(path, seed):
    checked = 0
    for slot, flags, gold in ((0, 0, 100), (8, 0, 100),
                              (0, 1 << 46, 100), (0, 0, 99_999_998)):
        e = emulator(path, seed)
        definition = e.alloc(0x40)
        e.mem.w8(definition + 0x1C, slot)
        e.mem.w64(definition + 0x28, flags)
        e.mem.w32(R.PLAYER + 0x130, definition)
        e.mem.w16(R.PLAYER + 0x134, 1)
        e.mem.w32(R.PLAYER + 0xE4, gold)
        e.stub(0x1024A8, ret=100)
        e.stub(0x1C4310, ret=1)
        msg = e.alloc(16)
        e.mem.write(msg, struct.pack('<BbhIhbbb', 1, 0, 0, 0, 0, 0, 0, 1))
        e.call(MSG, msg, 13)
        assert e.mem.s32(R.PLAYER + 0xE4) == R.credited_gold(
            gold, R.sell_credit(100, 1, slot, flags))
        assert sum(c.target == 0x1C4310 for c in e.calls) == 1
        checked += 1
    return checked


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ELF
    disc = sys.argv[2] if len(sys.argv) > 2 else DISC
    assert hashlib.sha256(open(path, 'rb').read()).hexdigest() == SHA
    hub_vendor(disc)
    total = 1
    print('pinned HUB.GOB: object 10 vendor properties and one NPC PASS')
    for seed in (20973, 7):
        open_close(path, seed)
        screen(path, seed)
        total += 2 + prices(path, seed) + sales(path, seed)
        print('seed %d: open/close with audio and unload, screen with text, 6 buys, 4 sells PASS' % seed)
    print('PASS: %d bounded checks, 0 mismatches' % total)


if __name__ == '__main__':
    main()
