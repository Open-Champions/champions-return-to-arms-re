#!/usr/bin/env python3
"""Synthetic world-present original-function probes; see death-reload-objects.md.

Only the counts are printed on success. Resource/constructor boundaries are
explicit; this is not a whole-game or checkpoint-validity test.
"""
import argparse
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: E402,F401 -- preload stdlib before tools/dis.py can shadow it
sys.path.insert(0, HERE)
from ee_emu import EE, CpuTrap  # noqa: E402

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
GRID_A, GRID_B, ACTIVE = 0x5DB4F0, 0x5E95F0, 0x5DB3A8


def put(e, p, fmt, *values):
    e.mem.write(p, struct.pack('<' + fmt, *values))


def get(e, p, fmt):
    return struct.unpack('<' + fmt, e.mem.read(p, struct.calcsize('<' + fmt)))


def cell(pos, second=False):
    x, y = ((int(v) + 0x3c00) >> 8 for v in pos[:2])
    if not (0 <= x < 120 and 0 <= y < 120):
        return 0x5F76F0
    return (GRID_B if second else GRID_A) + 4 * (120*y + x)


def members(e, head):
    """Independently inspect the paired linked-list representation, including backlinks."""
    m, prev, node, result = e.mem, head, e.mem.u32(head), []
    seen = set()
    while node:
        assert node not in seen, 'list cycle'
        seen.add(node)
        assert m.u32(node+4) == prev, 'list backlink'
        obj, paired = m.u32(node+12), m.u32(node+8)
        assert obj and paired and m.u32(paired+8) == node
        assert m.u32(m.u32(paired+4)) == paired
        result.append(obj)
        prev, node = node, m.u32(node)
    return result


class Scene:
    def __init__(self, elf, seed):
        self.e = e = EE(elf)
        e.record_calls = e.record_writes = False
        # Original allocator initializers. No scheduler/world-init substitution.
        e.call(0x14FCD8)
        e.call(0x1A17D0)
        e.mem.w32(0x404464, seed)
        e.mem.w32(0x4039B8, 0)
        e.mem.w32(0x403A00, 0)
        self.world, self.piece, self.element, self.surface = [e.alloc(0x200) for _ in range(4)]
        e.mem.w32(0x44FDC8, self.world)
        e.mem.w32(self.world+0x54, self.piece)
        e.mem.w32(self.world+0x20, self.element)
        e.mem.w32(self.world+0x24, self.surface)
        put(e, self.piece, 'Ih', 0, 1)
        put(e, self.piece+8, 'iii', 0, 0, 16)
        put(e, self.piece+0x14, 'hhh', 32767, 0, 0)
        e.mem.w16(self.element+0x10, 0x12)
        e.mem.w32(self.element+0x1c, 123)
        # Existing world member makes constructor/list tests nonempty.
        self.anchor = self.base((4., 5., 6.))
        e.call(0x14F248, self.anchor)
        assert members(e, cell((4., 5., 6.))) == [self.anchor]
        assert members(e, ACTIVE) == [self.anchor]

    def base(self, pos, size=0x200):
        e = self.e
        obj, vec = e.alloc(size), e.alloc(12)
        put(e, vec, 'fff', *pos)
        e.call(0x14CB10, obj, vec, 0, 0)
        return obj

    def text(self, value):
        p = self.e.alloc(len(value)+1)
        self.e.mem.write(p, value+b'\0')
        return p

    def archive(self, name, entries):
        """Supply an already relocated synthetic resource directory and cache entry."""
        e = self.e
        index = e.mem.u32(0x41BF7C)
        assert index < 16
        directory = e.alloc(4+12*len(entries))
        e.mem.w16(directory, len(entries))
        for i, (key, pointer) in enumerate(sorted(entries.items())):
            put(e, directory+4+12*i, 'III', self.text(key), pointer, 1)
        entry = 0x7B9480 + 0x28*index
        assert len(name) < 16
        e.mem.write(entry, name+b'\0')
        put(e, entry+0x10, 'II', directory, 0)
        e.mem.w32(0x41BF7C, index+1)
        return directory

    def container_assets(self):
        e = self.e
        model, defs, clip = [e.alloc(0x80) for _ in range(3)]
        # One synthetic model part with integer bounds, not an empty model.
        e.mem.w8(model+0x12, 1)
        put(e, model+0x28, '6b', -6, -8, 0, 6, 8, 20)
        e.mem.w32(0x41BF78, 9)
        e.mem.w32(defs+4, 9)
        e.mem.w32(defs+0xc, model)
        e.mem.w32(defs+0x1c, clip)
        e.mem.w32(clip+4, 73)
        e.mem.w32(0x501698, defs)
        e.mem.w32(0x88D3D4, 2)
        put(e, 0x4F714C, 'f', 1.)
        e.mem.write(0x41B721, b'r2_level\0')
        return model, defs, clip

    def auto_assets(self, model, clip):
        e = self.e
        e.mem.write(0x533990, b'r2a\0')
        for addr, suffix in ((0x541F00, b'_a'), (0x541F08, b'_m'),
                             (0x541F10, b'_t'), (0x542000, b'_c')):
            e.mem.write(addr, suffix+b'\0')
        self.archive(b'r2_auto_a', {b'r2_auto_m': model,
                                   b'r2_auto_t': clip, b'r2_auto_c': clip})


def record_blob(records, saved=True):
    """Independent serialization of synthetic records, including property relocation."""
    strings, offsets = bytearray(b'\0'), {}
    def intern(value):
        if value not in offsets:
            offsets[value] = len(strings)
            strings.extend(value+b'\0')
        return offsets[value]
    rows = bytearray()
    for token, pos, angle, props, state in records:
        row = bytearray(struct.pack('<ihhfff', intern(token), 0, angle, *pos))
        row += struct.pack('<%dI' % (len(props)+1), *[intern(p) for p in props], 0)
        row += bytes((-len(row)) % 8)
        if saved:
            row += state
        row += bytes((-len(row)) % 8)
        struct.pack_into('<h', row, 4, len(row))
        rows.extend(row)
    blob = struct.pack('<hHI', len(records), int(saved), 8+len(rows)) + rows + strings
    return blob + bytes((-len(blob)) % 8)


def assert_track(e, track, opened, clip):
    assert e.mem.u8(track+4) == opened
    if opened:
        assert e.mem.u32(track+8) == clip
        assert e.mem.u16(track+6) == e.mem.u16(track+0x24) == 0x204
        assert get(e, track+0x20, 'f') == (73.,)


def container_records(elf, seed):
    count = 0
    for opened in (0, 1):
        for gold in (0, 1, 32767, 32768, 65535):
            s = Scene(elf, seed)
            e = s.e
            model, defs, clip = s.container_assets()
            s.auto_assets(model, clip)
            e.mem.write(0x533690, b'r2_t\0')
            e.mem.write(0x532F70, b'r2_c\0')
            e.mem.w32(0x5F76F4, 0x159C94)
            state = struct.pack('<IHBBI', 0xA1234567, gold, 2, 0, opened)
            blob = record_blob([
                (b'r2_t', (4., 5., 6.), 0, [], struct.pack('<IB', 19, 255)),
                (b'r2_c', (4., 5., 6.), -16384, [], state),
                (b'r2_auto', (4., 5., 6.), 0, [b'r2a=1'], state),
            ])
            data = e.alloc(len(blob))
            e.mem.write(data, blob)
            # Original records -> factory -> pool -> constructors -> virtual loaders.
            e.call(0x14E808, data, 0)
            auto, chest, trigger, anchor = members(e, cell((4., 5., 6.)))
            assert anchor == s.anchor
            assert [e.mem.u32(o+0x48) for o in (auto, chest, trigger)] == [
                0x513468, 0x5118D8, 0x511600]
            assert e.mem.u16(data+2) == 3
            assert e.mem.cstr(e.mem.u32(auto+0x34)) == 'r2_auto'
            assert e.mem.cstr(e.mem.u32(chest+0x34)) == 'r2_c'
            assert e.mem.cstr(e.mem.u32(trigger+0x34)) == 'r2_t'
            assert e.mem.u32(trigger+0x64) == 19 and e.mem.u8(trigger+0x60) == 255
            assert members(e, 0x5DB3B4) == [trigger]
            assert members(e, ACTIVE) == [anchor]
            assert members(e, GRID_B+4*(120*60+60)) == []
            for obj, mask_off, gold_off, byte_off, open_off, track in (
                (chest, 0x54, 0x4c, 0x58, 0x84, 0x5c),
                (auto, 0xc8, 0xdc, 0xe4, 0xd8, 0x98),
            ):
                assert e.mem.u32(obj+mask_off) == 0xA1234567
                assert e.mem.u16(obj+gold_off) == gold
                assert e.mem.read(obj+byte_off, 2) == b'\x02\x00'
                assert e.mem.u32(obj+open_off) == opened
                depleted = gold == 0 or gold >= 32768
                assert e.mem.u32(obj+0xc) == (0x18 if opened and depleted else 0x100018)
                assert_track(e, obj+track, opened, clip)
            assert e.mem.u64(auto+0xc8) == 0xFFFFFFFFA1234567
            assert e.mem.u32(chest+0x24) == defs
            assert e.mem.u32(auto+0x90) == model and e.mem.u32(auto+0xf4) == clip
            assert e.mem.u32(auto+0xe8) == e.mem.u32(auto+0xec) == 0
            assert get(e, auto+0x1c, 'ff') == (12., 60.)
            assert e.mem.read(auto+0x28, 2) == bytes((12, 12))
            assert not e.hooks and not e.patches
            count += 1
    return count


def trigger_factory(elf, seed):
    scene = Scene(elf, seed)
    e = scene.e
    # Substitute only the factory's compared data token, never an instruction.
    e.mem.write(0x533690, b'r2_t\0')
    token, pos, props = scene.text(b'r2_t'), e.alloc(12), e.alloc(4)
    put(e, pos, 'fff', 4., 5., 6.)
    obj = e.call(0x159C94, token, pos, 0, props)
    assert obj and e.mem.u32(obj+0x48) == 0x511600
    assert members(e, cell((4., 5., 6.))) == [obj, scene.anchor]
    assert members(e, 0x5DB3B0+4) == [obj]
    assert members(e, ACTIVE) == [scene.anchor]
    assert get(e, obj+0x4c, '4f') == (4., 5., 4., 5.)
    assert e.mem.u32(obj+0xc) == 3 and e.mem.u32(obj+0x68) == 0xffffffff
    payload = e.alloc(8)
    put(e, payload, 'IB', 0x12345678, 255)
    assert e.call(0x1ECEF4, obj, payload) == 5
    assert e.mem.u32(obj+0x64) == 0x12345678 and e.mem.u8(obj+0x60) == 255
    assert members(e, 0x5DB3B0+4) == [obj]
    return 1


def item_loads(elf, seed):
    rng, count = random.Random(seed), 0
    for protected in (False, True):
        for mask in (8, 10):
            for away in (False, True):
                s = Scene(elf, seed)
                e = s.e
                model, _, texture = s.container_assets()
                e.mem.write(0x5326B0, b'r2_assets\0')
                e.mem.w32(0x3E9CE0, s.text(b'r2_model'))
                e.mem.w32(0x3E9CE4, s.text(b'r2_texture'))
                s.archive(b'r2_assets', {b'r2_model': model, b'r2_texture': texture})
                # Synthetic definition and unprotected constructor item; descriptor
                # parsing/factory constructor 0x159458 is intentionally not substituted.
                definition = 0x3F7650+7*0x40
                e.mem.write(definition, bytes(0x40))
                item, mat, vec, obj = e.alloc(0x48), e.alloc(48), e.alloc(12), e.alloc(0x190)
                e.mem.w32(item, definition)
                pos = (float(rng.randrange(260, 300) if away else 4), 5., 6.)
                put(e, vec, 'fff', *pos)
                put(e, mat, '12f', 1., 0., 0., 0., 1., 0., 0., 0., 1., *pos)
                # Original alternate ItemProp constructor, including Prop and grid relinks.
                e.call(0x1592BC, obj, vec, item, mat)
                assert e.mem.u32(obj+0xc) == 0x102009
                assert e.mem.u32(obj+0x48) == 0x511C38
                expected_cell = [obj] if away else [obj, s.anchor]
                assert members(e, cell(pos)) == expected_cell
                assert members(e, cell(pos, True)) == []
                # Facing is a supplied input to the loader; this constructor variant
                # takes a matrix, not the level factory's facing argument.
                e.mem.w16(obj+0x38, 0xC000)
                strings = b'r2_assets\0r2_model\0r2_texture\0'
                table = e.alloc(len(strings))
                e.mem.write(table, strings)
                e.mem.w32(0x5F8704, table)
                prefix = bytearray(rng.getrandbits(8) for _ in range(0x48))
                struct.pack_into('<I', prefix, 0, 7)
                struct.pack_into('<Q', prefix, 8, (1 << 39) if protected else 0)
                # Independent authored wire data; no save implementation is an oracle.
                suffix = struct.pack('<III', 0, 10, 19)
                suffix += b'\x03' if mask == 8 else struct.pack('<iQb', -1, 10, 0)
                suffix += struct.pack('<bbbhhhh', 0, 0, 0, 10000, 1, -2, 3)
                state = e.alloc(len(prefix)+len(suffix))
                e.mem.write(state, prefix+suffix)
                assert e.call(0x159758, obj, state) == 0x48+len(suffix)
                expected_item = bytearray(prefix)
                struct.pack_into('<I', expected_item, 0, definition)
                assert e.mem.read(obj+0x148, 0x48) == expected_item
                assert e.mem.u64(obj+0xe8) == mask
                assert e.mem.u32(obj+0xc) == (0x100009 if protected else 0x103009)
                assert e.mem.u32(obj+0x4c) == model and e.mem.u32(obj+0x50) == texture
                matrix = get(e, obj+0x110, '12f')
                expected_matrix = (1., 0., 0., 0., 1., 0., 0., 0., 1., *pos)
                assert all(abs(a-b) < 0.000001 for a, b in zip(matrix, expected_matrix))
                assert members(e, cell(pos)) == expected_cell
                assert members(e, cell(pos, True)) == []
                assert members(e, ACTIVE) == [s.anchor]
                assert not e.hooks and not e.patches
                count += 1
    return count


def door_loads(elf, seed):
    count = 0
    for loader in (0x28AE74, 0x28B1B8, 0x28DF24):
        for opened in (0, 1):
            s = Scene(elf, seed)
            e = s.e
            # Full base constructor, then explicitly supplied derived-constructor state:
            # piece index zero, interactable flags, scheduled (15-frame) membership.
            obj, buf = s.base((4., 5., 6.)), e.alloc(32)
            e.mem.w32(obj+0xc, 0x100000)
            e.mem.w16(obj+0x4c, 0)
            e.call(0x14F330, obj)
            assert members(e, 0x5DB3B4) == [obj]
            before_piece = e.mem.read(s.piece, 0x200)
            if loader == 0x28AE74:
                put(e, buf, 'Hhf', opened*32768, -1, 1.25)
                consumed = 8
                pose = (0, 0, 16)
                terrain = 0x12
                flags = 1 if opened else 0x100000
            elif loader == 0x28B1B8:
                put(e, buf, 'B', opened)
                consumed = 1
                pose = (0, 0, -1184) if opened else (0, 0, 0)
                terrain = 0x12
                flags = 0 if opened else 0x100000
            else:
                put(e, buf, 'iifi', opened, 0, 2.5, 99)
                consumed = 16
                pose = (0, 0, 0)
                terrain = 0x10
                flags = 0 if opened else 0x100000
            for _ in range(2):
                assert e.call(loader, obj, buf) == consumed
                active = bool(opened and loader != 0x28B1B8)
                assert members(e, ACTIVE) == ([obj, s.anchor] if active else [s.anchor])
                assert members(e, 0x5DB3B4) == ([] if active else [obj])
                assert members(e, cell((4., 5., 6.))) == [obj, s.anchor]
                assert e.mem.u32(obj+0xc) == flags
                assert e.mem.u16(s.element+0x10) == terrain
                assert get(e, s.surface+0x28, 'iii') == pose
                assert e.mem.read(s.piece, 0x200) == before_piece
            if loader == 0x28AE74:
                assert e.mem.u16(obj+0x50) == opened*32768
                assert e.mem.u8(obj+0x58) == 255 and get(e, obj+0x54, 'f') == (1.25,)
            elif loader == 0x28DF24:
                assert get(e, obj+0x4c, 'hhfI') == (0, 123, 2.5, 99)
                assert e.mem.u16(obj+0x5a) == opened
            assert not e.hooks and not e.patches
            count += 1
    return count


def level_pipeline(elf, seed):
    """Original 0x217978 with cached resources, no script, saved nonempty objects."""
    s = Scene(elf, seed)
    e = s.e
    model, _, clip = s.container_assets()
    s.auto_assets(model, clip)
    e.mem.write(0x533690, b'r2_t\0')
    e.mem.write(0x532F70, b'r2_c\0')
    e.mem.write(0x53EFE8, b'%s.r2\0')
    e.mem.write(0x53F010, b'r2_ob\0')
    e.mem.w32(0x5F76F4, 0x159C94)
    e.mem.w32(0x403A0C, 0x15D9C8)
    saved = record_blob([
        (b'r2_t', (4., 5., 6.), 0, [], struct.pack('<IB', 23, 1)),
        (b'r2_c', (4., 5., 6.), 0, [], struct.pack('<IHBBI', 7, 0, 2, 0, 1)),
        (b'r2_auto', (4., 5., 6.), 0, [b'r2a=1'], struct.pack('<IHBBI', 9, 1, 0, 0, 1)),
    ])
    # This base-level object must be rejected by the original saved-world filter.
    level = record_blob([(b'r2_t', (4., 5., 6.), 0, [], b'')], saved=False)
    data = e.alloc(len(level))
    e.mem.write(data, level)
    s.archive(b'r2_level.r2', {b'r2_ob': data})
    decals = bytes(8)
    body = struct.pack('<II', len(saved), 0) + saved
    body += struct.pack('<II', len(decals), 0) + decals + bytes(0x16C8)
    e.mem.write(0x8AB590, bytes(0x108))
    e.mem.write(0x8AB590, b'r2_level\0')
    e.mem.w32(0x8AB5A4, len(body))
    e.mem.write(0x8AB698, body)
    e.mem.w8(0x8E1AD6, 1)
    e.mem.w8(0x4F8B58, 1)  # explicitly suppress script entry points
    e.mem.w32(0x86B270, 0x12345678)
    name = s.text(b'r2_level')
    e.call(0x217978, name, name, max_steps=1000000)
    auto, chest, trigger, anchor = members(e, cell((4., 5., 6.)))
    assert anchor == s.anchor
    assert [e.mem.u32(o+0x48) for o in (auto, chest, trigger)] == [
        0x513468, 0x5118D8, 0x511600]
    assert e.mem.u32(trigger+0x64) == 23 and e.mem.u8(trigger+0x60) == 1
    assert e.mem.u32(chest+0xc) == 0x18 and e.mem.u32(auto+0xc) == 0x100018
    assert_track(e, chest+0x5c, 1, clip)
    assert_track(e, auto+0x98, 1, clip)
    assert members(e, ACTIVE) == [anchor] and members(e, 0x5DB3B4) == [trigger]
    assert e.mem.u8(0x4F7108) == 3 and e.mem.u8(0x8E1AD6) == 0
    assert e.mem.u32(0x86B270) == 0
    assert e.mem.u32(0x4D8A00) == 0  # original empty decal reset
    assert e.mem.read(0x8AB698, len(body)) == body  # source snapshot remains pristine
    assert e.mem.u16(0x88D482) == 3 and e.mem.u16(data+2) == 2
    assert not e.hooks and not e.patches
    return 1


def gate_loads(elf, seed):
    """Nonportal gate vtable dispatch, with explicit supplied state/clip/piece bindings."""
    count = 0
    for state in (0, 1, 2):
        for passable in (0, 1):
            for animated in (False, True):
                s = Scene(elf, seed)
                e = s.e
                model, _, clip = s.container_assets()
                obj, payload = s.base((4., 5., 6.)), e.alloc(4)
                # The actual gate's vtable, with its shared load and state services.
                e.mem.w32(obj+0x48, 0x513B68)
                assert e.mem.u32(0x513B68+0x44) == 0x23CEB8
                assert e.mem.u32(0x513B68+0x94) == 0x23D680
                assert e.mem.u32(0x513B68+0x9c) == 0x23D7AC
                e.mem.w32(obj+0x90, model)
                e.mem.w8(obj+0x9d, 1)
                e.mem.w32(obj+0x11c, 1)  # moving-piece participation supplied
                e.mem.w32(obj+0x120, 2)
                e.mem.w32(obj+0x18c, 0)
                for i in range(2):
                    e.mem.w32(obj+0x128+8*i, clip if animated else 0)
                    e.mem.w32(obj+0x12c+8*i, passable | (2 if i else 0))
                e.mem.w32(obj+0x17c, 99)
                e.mem.w64(obj+0x180, 0x55)
                e.mem.w64(obj+0xc8, 0x77)
                e.call(0x14F330, obj)
                e.mem.w32(payload, state)
                assert e.call(0x23CEB8, obj, payload) == 4
                assert e.mem.u32(obj+0x178) == state
                valid = state < 2
                if valid:
                    assert e.mem.u32(obj+0x17c) == (74 if animated else 0)
                    assert e.mem.u64(obj+0x180) == (3 if state else 0)
                    assert e.mem.u64(obj+0xc8) == 0xFFFFFFFFFFFFFFFF
                    assert e.mem.u32(obj+0xc) == passable
                    assert e.mem.u16(s.element+0x10) == (0x12 if passable else 0x10)
                    assert get(e, s.surface+0x28, 'iii') == (0, 0, -1008 if passable else 16)
                    assert e.mem.u8(obj+0x9c) == int(animated)
                    if animated:
                        assert e.mem.u32(obj+0xa0) == clip
                        assert e.mem.u16(obj+0xbc) == (3 if state else 6)
                        assert get(e, obj+0xb8, 'f') == (73.,)
                else:
                    # Loader stores an out-of-range word before setter rejects it.
                    assert e.mem.u32(obj+0x17c) == 99
                    assert e.mem.u64(obj+0x180) == 0x55
                    assert e.mem.u64(obj+0xc8) == 0x77
                    assert e.mem.u32(obj+0xc) == 0
                    assert e.mem.u16(s.element+0x10) == 0x12
                    assert get(e, s.surface+0x28, 'iii') == (0, 0, 0)
                assert members(e, cell((4., 5., 6.))) == [obj, s.anchor]
                assert members(e, ACTIVE) == [s.anchor]
                assert members(e, 0x5DB3B4) == [obj]
                assert not e.hooks and not e.patches
                count += 1
    return count


def unresolved_boundaries(elf, seed):
    """Fail closed on the actual unmodeled kernel path; never turn it into a return."""
    for item_factory in (False, True):
        s = Scene(elf, seed)
        e = s.e
        e.trace = []
        try:
            if item_factory:
                e.mem.write(0x5336E0, b'r2_i\0')
                e.mem.write(0x5326A0, b'r2_void\0')
                pos = e.alloc(12)
                put(e, pos, 'fff', 4., 5., 6.)
                e.call(0x159C94, s.text(b'r2_i'), pos, 0, e.alloc(4), max_steps=200000)
            else:
                e.call(0x17365C, s.text(b'r2_missing'), s.text(b'r2_model'), max_steps=200000)
        except CpuTrap as failure:
            assert str(failure) == 'SYSCALL at 0x00352e14 (v1 = 124); no kernel is modelled'
            assert e.cur == 0x352E14 and e.r[3] == 124
        else:
            raise AssertionError('unresolved resource path unexpectedly returned')
        assert 0x173558 in e.trace and 0x159758 not in e.trace
        assert members(e, ACTIVE) == [s.anchor]
        assert members(e, cell((4., 5., 6.))) == [s.anchor]
        if item_factory:
            assert 0x159458 in e.trace and 0x1069B8 in e.trace
            # This original failure is NOT transactional: the partial constructor
            # has already linked one object to grid B before resources fail.
            partial, = members(e, cell((4., 5., 6.), True))
            assert e.mem.u32(partial+0x48) == 0x511C38
            assert e.mem.u32(partial+0xc) == 0x1809
        else:
            assert members(e, cell((4., 5., 6.), True)) == []
        assert not e.hooks and not e.patches
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA, 'wrong executable pin'
    count = trigger_factory(args.elf, args.seed)
    count += container_records(args.elf, args.seed)
    count += item_loads(args.elf, args.seed)
    count += door_loads(args.elf, args.seed)
    count += level_pipeline(args.elf, args.seed)
    count += gate_loads(args.elf, args.seed)
    boundaries = unresolved_boundaries(args.elf, args.seed)
    print('PASS %d cases; %d expected boundaries' % (count, boundaries))


if __name__ == '__main__':
    main()
