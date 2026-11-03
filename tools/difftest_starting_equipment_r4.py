#!/usr/bin/env python3
"""Original starting-item selection and private cache mapping; counts only.

Read inputs through this worktree's local/. Never emit resource identities or
payloads. Device reads and tagged allocation are explicit host adapters; original
selection, parsing, equip, formatting, header search and fixups execute unchanged.
"""
import hashlib
import os
import re
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]
from ee_emu import EE, EmuError, s32
from difftest_loading import SHA256
from difftest_items import _cstr
from difftest_loading_arrival_r3 import texture_model, model_model
from gob import lmp_entries
import ref_items as R


RECORD = 0x4d8af0
CLASSES = (0, 0, 3, 3, 1, 1, 4, 4, 2, 2, 5, 6)
WEAPONS = (0x3f7f50, 0x3f7f50, 0x3f7650, 0x3f7650,
           0x3f8910, 0x3f8910, 0x3f9250, 0x3f9250,
           0x3f7a10, 0x3f7a10, 0x3f7f50, 0x3f87d0)
CACHES = {4: 0x8659e8, 10: 0x865b48, 12: 0x865f68}


def require_local(path):
    # Do not resolve the existing private-input symlinks: access stays via local/.
    root = Path(__file__).absolute().parent.parent / 'local'
    assert Path(os.path.abspath(path)).is_relative_to(root), 'input must be under local/'


def initialized(path, tables, body, seed, kind=-1):
    """Full original initializer and callees, with parser/model comparisons."""
    e = EE(path)
    e.record_writes = False
    e.mem.w32(0x4d8ae0, 1)
    e.mem.w32(0x404464, seed)
    name = e.alloc(32)
    e.mem.write(name, b'authored\0')
    e.mem.w32(e.r[29], kind)
    e.mem.w32(e.r[29] + 8, 0)
    parsed = []

    def parser_entry(m):
        text, out, variant, presets = m.r[4:8]
        rng = R.Rng(m.mem.u32(0x404464))
        expected = R.parse_descriptor(tables, _cstr(m.mem, text), s32(variant), bool(presets), rng)
        return_address = m.r[31] & 0xffffffff

        def parser_return(n):
            actual = n.mem.read(out, 0x48)
            # Defined/modelled fields only, not a whole-record differential:
            # preserved bytes originate in the parser's frame, not this buffer.
            assert expected.pack(stale=actual) == actual, 'parser/model mismatch'
            assert n.mem.u32(0x404464) == rng.seed, 'parser seed mismatch'
            parsed.append((text, expected.definition.addr))
            n.unhook(return_address)

        m.hook(return_address, parser_return)

    e.hook(0x1069b8, parser_entry)
    e.call(0x1b1d70, 0, body, name, -1, -1, -1, -1, 0)
    e.unhook(0x1069b8)
    assert not any(c.stubbed for c in e.calls), 'initialization must execute every callee'
    assert not e.patches
    assert e.mem.u32(RECORD + 0x50) == CLASSES[body]
    assert e.mem.u32(RECORD + 0x54) == body
    assert e.mem.u8(RECORD + 0x58) == e.mem.u8(RECORD + 0x59) == 1
    weapon_slot = 2 if body in (2, 3, 6, 7) else 0
    armor = (0x3fa210, 0x3fa250, 0x3fa310) if body in (6, 7) else (0x3fb110, 0x3fb150, 0x3fb210)
    expected = {weapon_slot: WEAPONS[body], **dict(zip(CACHES, armor))}
    equipped = {slot: e.mem.u32(RECORD + 0x43f0 + slot * 4)
                for slot in range(17) if e.mem.u32(RECORD + 0x43f0 + slot * 4)}
    assert {s: e.mem.u32(p) for s, p in equipped.items()} == expected, 'starting slot mismatch'
    for slot, item in equipped.items():
        assert e.mem.u8(e.mem.u32(item) + 0x1c) == slot
        assert RECORD <= item < RECORD + 0x43d8, 'equipped pointer is not in inventory'
    return e, equipped, len(parsed)


def armor_filename(e, body, item):
    """Independent bounded model for the actual baseline starting armor only."""
    definition = e.mem.u32(item)
    assert e.mem.u8(definition + 0x1c) in CACHES
    assert ((e.mem.u64(item + 8) >> 11) & 31) == 0
    picture = _cstr(e.mem, e.mem.u32(definition + 0x30))
    stem = _cstr(e.mem, 0x52f8f0) % picture
    body_code = _cstr(e.mem, e.mem.u32(0x4026d8 + body * 4))
    composed = _cstr(e.mem, 0x52f9b0) % (body_code, stem)
    prefix = e.mem.u8(item + 0x20)
    assert prefix != 255, 'bounded reference requires the actual starting prefix'
    color = e.mem.u8(0x400e50 + prefix * 0x28 + 7)
    return composed[:-4] + (_cstr(e.mem, 0x52f9b8) % color)


def formatter(e, body, slot, item):
    out = e.alloc(256)
    before = len(e.calls)
    e.call(0x107edc, out, body, item)
    assert not any(c.stubbed for c in e.calls[before:])
    actual = _cstr(e.mem, out)
    if slot in CACHES:
        assert actual == armor_filename(e, body, item), 'armor formatter mismatch'
    assert len(actual) > 4
    e.mem.w8(out + len(actual) - 4, 0)
    return out


class Media:
    """Read-only private-file adapter, deliberately not an emulated disc device."""
    def __init__(self, folder):
        require_local(folder)
        self.files = {}
        for path in Path(folder).rglob('*'):
            if path.is_file():
                self.files.setdefault(path.name.lower(), []).append(path)
        self.reads = []
        self.allocations = []

    def file(self, e, address):
        key = _cstr(e.mem, address).decode('latin1').lower()
        choices = self.files.get(key, [])
        assert len(choices) == 1, 'private role missing or ambiguous'
        return choices[0]

    def install_header(self, e):
        def lookup(m):
            assert m.r[5] == 0, 'unexpected sector-output request'
            m.mem.w32(m.r[6], self.file(m, m.r[4]).stat().st_size)
            return 1

        def allocate(m):
            size = m.r[4]
            address = m.alloc(size)
            m.mem.write(address, bytes(size))
            self.allocations.append((address, size))
            return address

        def read(m):
            role, destination, size, offset = m.r[4:8]
            assert offset == 0
            data = self.file(m, role).read_bytes()
            assert len(data) <= size
            m.mem.write(destination, data)
            self.reads.append((role, destination, data))
            return len(data)

        e.stub(0x1724fc, function=lookup)
        e.stub(0x14ff88, function=allocate)
        e.stub(0x172ad0, function=read)


def load_headers(e, media, players=1, override=0):
    e.mem.w32(0x4d8ae0, players)
    e.mem.w8(0x506040, override)
    media.install_header(e)
    before = len(e.calls)
    e.call(0x1a2680)
    assert {c.target for c in e.calls[before:] if c.stubbed} == {0x1724fc, 0x14ff88, 0x172ad0}
    assert len(media.reads) == 2
    assert media.reads[0][0] == (0x535c08 if players < 2 and not override else 0x535bf8)
    assert media.reads[1][0] == 0x535c28
    for (role, base, data), pointer, count_address in zip(media.reads, (0x8659e0, 0x8659e4), (0x4ef36c, 0x4ef370)):
        count = struct.unpack_from('<I', data)[0]
        assert e.mem.u32(pointer) == base + 4
        assert e.mem.u32(count_address) == count
        expected = bytearray(data)
        for index in range(count):
            for offset in (4 + index * 12, 8 + index * 12):
                value = struct.unpack_from('<I', data, offset)[0]
                assert value < len(data)
                struct.pack_into('<I', expected, offset, base + value)
        assert e.mem.read(base, len(data)) == expected, 'header relocation mismatch'


def metadata_model(e, name, second):
    """Independent search of relocated groups and their eight-byte records."""
    text = _cstr(e.mem, name).split(b'.', 1)[0]
    match = re.search(rb'[0-9]+$', text)
    assert match is not None, 'bounded reference requires a numeric suffix'
    key, number = text[:match.start()], int(match.group())
    table = e.mem.u32(0x8659e4 if second else 0x8659e0)
    count = e.mem.u32(0x4ef370 if second else 0x4ef36c)
    for i in range(count):
        group = table + 12 * i
        if _cstr(e.mem, e.mem.u32(group + 4)) != key:
            continue
        records = e.mem.u32(group)
        for j in range(e.mem.u32(group + 8)):
            record = records + j * 8
            if e.mem.s16(record) == number:
                return record
        return 0
    return 0


def selection(path, tables):
    cases = parsers = formatted = 0
    for body in range(12):
        for seed in (7, 20973):
            for kind in (-1, 1):
                e, equipped, count = initialized(path, tables, body, seed, kind)
                parsers += count
                for slot, item in equipped.items():
                    formatter(e, body, slot, item)
                    formatted += int(slot in CACHES)
                cases += 1
    return cases, parsers, formatted


def header_selection(path, folder):
    for players, override in ((1, 0), (1, 1), (2, 0), (2, 1)):
        e = EE(path)
        load_headers(e, Media(folder), players, override)
    return 4


def cache_pair(e, media, name, cache, metadata):
    """Real cache state machine and fixups; exact private range, host completion."""
    begin = e.mem.u32(metadata + 4)
    split_sector = e.mem.u32(metadata + 12)
    tail = e.mem.s16(metadata + 10)
    split = (split_sector - begin) * 0x800
    size = split + tail * 0x800
    assert 0 < split < size
    base = e.alloc(size + 32)
    e.mem.write(base, bytes(size + 32))
    e.mem.w32(cache, base)
    e.mem.w32(cache + 4, size)
    assert e.mem.u8(cache + 0x54) == e.mem.u8(cache + 0x56) == 0
    first, second = e.alloc(4), e.alloc(4)
    submissions = []

    def submit(m):
        role, destination, completion, length, offset = m.r[4:9]
        assert (role, destination, completion, length, offset) == (
            0x535d30, base, 0x4ef3e8, size, begin * 0x800), 'sector request mismatch'
        source = media.file(m, role)
        assert offset + length <= source.stat().st_size
        with source.open('rb') as stream:
            stream.seek(offset)
            data = stream.read(length)
        assert len(data) == length
        m.mem.w8(completion, 0)
        m.mem.write(destination, data)
        submissions.append(data)
        return 0

    e.stub(0x1729e8, function=submit)
    e.mem.w32(0x44fdd0, 100)
    start = len(e.calls)
    assert e.call(0x1a2d48, name, cache, first, second) == 0
    assert e.mem.u32(0x4ef3ec) == cache
    assert e.mem.u32(0x4ef3f0) == 100
    assert not submissions
    e.mem.w32(0x44fdd0, 103)
    assert e.call(0x1a2d48, name, cache, first, second) == 0
    assert not submissions
    e.mem.w32(0x44fdd0, 104)
    assert e.call(0x1a2d48, name, cache, first, second) == 0
    assert len(submissions) == 1 and e.mem.u32(cache + 0x4c) == split
    data = submissions[0]
    assert e.call(0x1a2d48, name, cache, first, second) == 0
    assert e.mem.u16(cache + 10) == 0
    assert e.mem.read(base, size) == data
    e.mem.w8(0x4ef3e8, 1)  # host reports its completed read; no device claim
    assert e.call(0x1a2d48, name, cache, first, second) == 0
    expected = texture_model(data, base)
    expected[split:] = model_model(expected[split:], base + split)
    assert e.mem.read(base, size) == expected, 'paired resource transformation mismatch'
    assert e.mem.read(base + size, 32) == bytes(32)
    assert e.mem.u16(cache + 10) == 1 and e.mem.u32(0x4ef3ec) == 0
    assert e.mem.u32(first) == e.mem.u32(second) == 0
    assert _cstr(e.mem, cache + 12) == _cstr(e.mem, name)
    assert e.call(0x1a2d48, name, cache, first, second) == 1
    assert (e.mem.u32(first), e.mem.u32(second)) == (base + split, base)
    assert e.mem.read(base, size) == expected
    calls = e.calls[start:]
    assert [c.target for c in calls if c.target in (0x179e10, 0x179130)] == [0x179e10, 0x179130]
    assert {c.target for c in calls if c.stubbed} == {0x1729e8}
    return size


def generic_weapon(e, media, tables, equipped):
    """Register the exact original source lump; run its real lookup/publication."""
    data = media.file(e, 0x520030).read_bytes()
    base = e.alloc(len(data) + 32)
    e.mem.write(base, data + bytes(32))
    before = len(e.calls)
    e.call(0x171700, base, 0x520030)
    rng = R.Rng(e.mem.u32(0x404464))
    R.load_resources(tables, rng)
    e.call(0x108434, max_steps=20000000)
    assert e.mem.u32(0x404464) == rng.seed, 'resource loader seed mismatch'
    assert not any(c.stubbed for c in e.calls[before:])
    assert e.mem.read(base + len(data), 32) == bytes(32)
    entries = lmp_entries(data)
    slot = next(s for s in equipped if s not in CACHES)
    item = equipped[slot]
    definition = e.mem.u32(item)
    row = e.mem.s16(definition + 0x34)
    if e.mem.u64(item + 8) & (1 << 36):
        row += (e.mem.u64(item + 8) >> 11) & 31
    assert e.call(0x1083f8, item) == row
    table_row = 0x3e9ce0 + 16 * row
    for role, reference in ((0, model_model), (1, texture_model)):
        name_pointer = e.mem.u32(table_row + 4 * role)
        wanted = _cstr(e.mem, name_pointer).decode('latin1')
        matches = [(offset, size) for name, offset, size in entries if name == wanted]
        assert len(matches) == 1, 'generic resource is absent or ambiguous in its source lump'
        offset, size = matches[0]
        pointer = base + offset
        record = e.call(0x171de4, base, name_pointer)
        assert record and e.mem.u32(record + 4) == pointer
        assert e.mem.u32(record + 8) == size
        assert e.mem.u32(table_row + 8 + role * 4) == pointer
        assert e.mem.read(pointer, size) == reference(data[offset:offset + size], pointer)
    return table_row


def resource_mapping(path, folder, tables):
    cases = lookups = byte_count = pending = ready = missing = 0
    for body in range(12):
        e, equipped, _ = initialized(path, tables, body, 20973)
        media = Media(folder)
        load_headers(e, media)
        for slot, item in equipped.items():
            name = formatter(e, body, slot, item)
            for second in (0, 1):
                actual = e.call(0x1a24e8, name, second)
                assert actual == metadata_model(e, name, second), 'metadata search mismatch'
                assert bool(actual) == (second == int(slot not in CACHES)), 'unexpected header role'
                lookups += 1
            if slot not in CACHES:
                continue
            metadata = metadata_model(e, name, 0)
            byte_count += cache_pair(e, media, name, CACHES[slot], metadata)
            cases += 1
        # A bounded player fixture supplies only the index consumed by the scan.
        # The original constructor and destination transitions are not executed.
        player = e.alloc(0x600)
        e.mem.w32(player + 0x3c8, 0)
        e.mem.w32(0x4f85b0, 1)
        before_record = e.mem.read(RECORD, 0x4c30)
        seen = []

        def observe_lookup(m):
            cache = m.r[5]
            assert cache in CACHES.values()
            assert _cstr(m.mem, m.r[4]) == _cstr(m.mem, cache + 12)
            seen.append(cache)

        e.hook(0x1a2d48, observe_lookup)
        for _ in range(2):
            seen.clear()
            before = len(e.calls)
            # The actual starting weapon uses the generic table, which this
            # fixture has not loaded. The original must continue to say pending.
            assert e.call(0x1a30b0, player) == 1
            assert seen == list(CACHES.values())
            assert not any(c.stubbed for c in e.calls[before:])
            assert not any(c.target in (0x179e10, 0x179130) for c in e.calls[before:])
            assert e.mem.read(RECORD, 0x4c30) == before_record
            pending += 1
        table_row = generic_weapon(e, media, tables, equipped)
        for _ in range(2):
            seen.clear()
            before = len(e.calls)
            assert e.call(0x1a30b0, player) == 0
            assert seen == list(CACHES.values())
            assert not any(c.stubbed for c in e.calls[before:])
            assert e.mem.read(RECORD, 0x4c30) == before_record
            ready += 1
        if body == 0:
            for offset in (8, 12):
                original = e.mem.u32(table_row + offset)
                e.mem.w32(table_row + offset, 0)
                assert e.call(0x1a30b0, player) == 1
                e.mem.w32(table_row + offset, original)
                missing += 1
    return cases, lookups, byte_count, pending, ready, missing


def main():
    path = sys.argv[1]
    require_local(path)
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SHA256, 'executable digest mismatch'
    tables = R.Tables(path)
    cases, parsers, formatted = selection(path, tables)
    print('PASS starting selection cases=%d parser_comparisons=%d armor_formatters=%d' % (cases, parsers, formatted))
    if len(sys.argv) == 3:
        folder = sys.argv[2]
        print('PASS header selection cases=%d' % header_selection(path, folder))
        cases, lookups, byte_count, pending, ready, missing = resource_mapping(path, folder, tables)
        print('PASS private mapping armor_pairs=%d metadata_comparisons=%d bytes_compared=%d' % (cases, lookups, byte_count))
        print('PASS original scanner pending=%d ready=%d missing_weapon_pointer_controls=%d generic_weapon_pairs=12' % (pending, ready, missing))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Library errors can contain private strings or instruction words.
        print('FAIL type=%s address=0x%x' % (type(error).__name__, getattr(error, 'addr', 0)))
        sys.exit(1)
