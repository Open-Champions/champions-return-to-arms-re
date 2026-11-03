#!/usr/bin/env python3
"""Counts-only original-EE character attachment difftests; private ELF required.

Run from repo root with PYTHONDONTWRITEBYTECODE=1. unittest is imported before
adding tools to sys.path (tools/dis.py must not shadow the standard library).
The executable is pinned by SHA256 before any token is read or code executed.

Executed boundaries:
* 0x179550 complete, 0x1a3580 -> 0x1a3604: real body-mask initialization.
* 0x1a3b90 -> 0x1a3cd0/0x1a3df8: real paired-resource/cover gates, real
  substring 0x3b96a8. Entry assumes equipment resource lookup has completed;
  s2=item, s5=record, s6=prior cover, stack+0/+4=mesh/texture.
* 0x1a3e08 -> 0x1a3f34: final hair/beard gates, real 0x1797d8 shell-state
  setter, complete 0x178c28 and 0x175fb8, post-draw body hide-bit updates.
  Entry assumes s3=player, s5=record, s6=cover, fp=draw context.
* Linked slices also execute 0x1a3b90 -> 0x1a3df8 with original item
  effect selection (flags zero), second-slot override/mirror/reset and equipped
  hide-bit update, then resume the final gates. Other iterations are omitted.
* Direct complete 0x178c28: header+0x13, override, parent+0x22 table selection,
  matrix packet copies, mesh-table clamp and 64-bit show-mask range selection.
* Added, same entry rules: definition-slot 3 shield selection 0x1a3cfc–0x1a3d84
  for every body model, the published 12-body starting pointer slots (class
  word unread), shell block 0x1068d8, and the f12 clamp 0x1a4cac–0x1a4d08.
  Shell primitive 0x174e78 is not entered (part flag 0x20 stays clear).

Only 0x16b7f0 (sorted renderer queue submission) is stubbed. It records calls
but never renders. Synthetic relocated models, parent records and packet
buffer are explicitly allocated. Shell passes are disabled (part flag 0x20
clear, global shell count zero), draw flags only 0 or 0x80; flag 0x40 is out
of scope. No auto_map, instruction patches, blanket stubs, or unknown callees.
No constructor, menu, resource-cache, full equipment loop, VU/GS rendering or
live body-mask timing claim. Chosen resources enter as authored object handles.
"""

import os
import sys

# Remove the script directory until the stdlib dependency has loaded.
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or os.curdir) != _TOOL_DIR]
import unittest  # noqa: E402,F401
import argparse
import hashlib
import itertools
import random
import struct

sys.path.insert(0, _TOOL_DIR)
from ee_emu import EE
import ref_char_attachment as ref

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
TOKENS = (0x535d70, 0x535d78, 0x535d80, 0x535d90, 0x535d98, 0x535da8)
RNG = 0x404464
DRAW_PART, SETUP, QUEUE = 0x178c28, 0x175fb8, 0x16b7f0
BUILD_MASK, SET_SHELL, SUBSTRING = 0x179550, 0x1797d8, 0x3b96a8
PACKET_CURSOR, DRAW_FLAGS, SHELL_COUNT = 0x44fe10, 0x41c168, 0x41c164


class BoundedEE(EE):
    """Reject unreviewed callees; execute every approved non-renderer callee."""
    allowed = {DRAW_PART, SETUP, QUEUE, BUILD_MASK, SET_SHELL, SUBSTRING,
               0x1068d8, 0x1046c4, 0x179860, 0x179978}

    def _enter_call(self, target):
        if target not in self.allowed:
            raise AssertionError('unexpected callee at 0x%x' % target)
        return super()._enter_call(target)


class Fixture:
    def __init__(self, elf, seed):
        self.e = e = BoundedEE(elf)
        self.seed = seed
        self.rng = random.Random(seed)
        e.mem.w32(RNG, seed)
        self.packet = e.alloc(0x10000)
        self.obj, self.record = e.alloc(0x590), e.alloc(0x4c30)
        self.item, self.definition = e.alloc(0x50), e.alloc(0x40)
        self.name, self.picture = e.alloc(256), e.alloc(256)
        self.context = e.alloc(0x80)
        self.body = e.alloc(0x800)
        self.parts = (e.alloc(0x800), e.alloc(0x800))
        self.textures = (e.alloc(0x40), e.alloc(0x40))
        self.equipment, self.equipment_texture = e.alloc(0x800), e.alloc(0x40)
        self.payload = e.alloc(0x8000)
        e.mem.w32(self.item, self.definition)
        e.mem.w32(self.definition, self.name)
        e.mem.w32(self.definition + 0x30, self.picture)
        e.mem.w32(self.obj + 0x544, self.body)
        e.mem.w8(self.body + 0x22, 0x40)
        e.mem.w16(self.body + 0x10, 4)
        self.joints, self.matrices = [], []
        for i in range(16):
            at = self.body + 0x400 + 0x34 * i
            joint = (i * 7 + 3) % 64
            values = tuple(float(1 + i * 16 + j) for j in range(12))
            self.joints.append(joint)
            self.matrices.append(values)
            e.mem.w32(at, joint)
            e.mem.write(at + 4, struct.pack('<12f', *values))
        self.tokens = []
        for addr in TOKENS:
            value = bytearray()
            for i in range(96):
                byte = e.mem.u8(addr + i)
                if byte == 0:
                    break
                value.append(byte)
            else:
                raise AssertionError('unterminated pinned token')
            assert value and all(32 <= x < 127 for x in value)
            self.tokens.append(bytes(value))
        self.submitted = []
        e.stub(QUEUE, function=self.submit, name='renderer_queue_boundary')
        for i, part in enumerate(self.parts):
            self.model(part, 2 + i, 4, 2)
        self.reset()

    def submit(self, e):
        self.submitted.append(tuple(e.r[4:9]))
        return 0

    def reset(self, mirrored=False):
        e = self.e
        e.r[29] = e.STACK_HI - 0x1000
        e.mem.w32(PACKET_CURSOR, self.packet)
        e.mem.w32(DRAW_FLAGS, 0x80 if mirrored else 0)
        e.mem.w32(SHELL_COUNT, 0)
        e.mem.w32(0x41c160, 0)
        e.mem.write(self.packet, bytes(0x10000))
        e.reset_log()
        e.reads = []
        self.submitted.clear()

    def check(self):
        e = self.e
        assert e.mem.u32(RNG) == self.seed, 'RNG mutation'
        assert e.follow is None and not e.mem.auto_map and not e.mem.auto_mapped
        assert not e.patches
        assert all(c.target == QUEUE for c in e.calls if c.stubbed)
        assert self.packet <= e.mem.u32(PACKET_CURSOR) < self.packet + 0x10000

    def model(self, at, attach, count, tables, flags=0, lengths=None):
        """Authored relocated mesh tables; all payload addresses are private heap."""
        e = self.e
        e.mem.w16(at + 0x10, flags)
        e.mem.w8(at + 0x12, count)
        e.mem.w8(at + 0x13, attach)
        e.mem.w8(at + 0x26, tables)
        rows = []
        for table in range(tables):
            pos = self.payload + table * 0x1000
            bounds = [pos]
            for i in range(count):
                pos += (lengths[i] if lengths is not None else 1 + (i % 3)) * 16
                bounds.append(pos)
            for i, value in enumerate(bounds):
                e.mem.w32(at + 0x28 + 4 * (table * (count + 1) + i), value)
            rows.append(tuple(bounds))
        return tuple(rows)

    def strings(self, name_id=None, picture_id=None, embedded=False):
        """Runtime token bytes, never copied into tracked source or output."""
        def make(index):
            if index is None:
                return b'!'
            token = self.tokens[index]
            return b'~' + token + b'~' if embedded else token
        name, picture = make(name_id), make(picture_id)
        self.e.mem.write(self.name, name + b'\0')
        self.e.mem.write(self.picture, picture + b'\0')
        return (self.tokens[0] in name, self.tokens[1] in picture,
                self.tokens[2] in picture, self.tokens[3] in name,
                self.tokens[4] in picture)

    def check_attachment(self, header, override, mirrored=False, draws=1):
        e = self.e
        index = ref.attachment_index(header, override)
        reads = [(addr, value) for pc, addr, size, value in e.reads if pc == 0x176134]
        expected = [] if index is None else [
            (self.body + 0x400 + index * 0x34, self.joints[index])] * draws
        assert reads == expected, 'attachment table selection'
        joint_writes = [v for pc, _, _, v in e.writes if pc == 0x17614c]
        assert joint_writes == ([] if index is None else [self.joints[index] * 4] * draws)
        if index is not None:
            lo, hi = ((0x176170, 0x1761d4) if mirrored else (0x1761e4, 0x17623c))
            values = [struct.unpack('<f', struct.pack('<I', v))[0]
                      for pc, _, size, v in e.writes if lo <= pc <= hi and size == 4]
            want = ref.attachment_matrix(self.matrices[index], mirrored)
            assert values == list(want) * draws, 'attachment matrix packet'

    def check_runs(self, boundaries, show):
        refs = [((value >> 32) & 0xffffffff, (value & 0xffff) * 16)
                for pc, _, _, value in self.e.writes if pc == 0x178d58]
        assert tuple(refs) == ref.mesh_runs(boundaries, show), 'masked mesh runs'


def masks(f):
    e, rng = f.e, f.rng
    variants = [(rng.getrandbits(64), rng.getrandbits(64)) for _ in range(32)]
    e.mem.w8(f.body + 0x21, 4)
    for i, (show, hide) in enumerate(variants):
        e.mem.w64(f.body + 0x40 + i * 16, show)
        e.mem.w64(f.body + 0x48 + i * 16, hide)
    count = 0
    selections = (0, 1, 2, 3, 1 << 31, 0x80000001, 0xffffffff)
    for enabled, hidden, selection in itertools.product(
            (False, True), (0, ref.U64, rng.getrandbits(64)), selections):
        f.reset()
        e.mem.w16(f.body + 0x10, 4 | (2 if enabled else 0))
        e.mem.w64(f.body + 8, hidden)
        got = e.call(BUILD_MASK, f.body, selection, max_steps=1000)
        assert got == ref.variant_show_mask(hidden, enabled, selection, variants)
        f.check()
        count += 1
    initial = 0
    for enabled, counter in itertools.product((False, True),
            (0, 0x110, 0x111, 0x112, 0x7fffffff, 0x80000000, 0xffffffff)):
        f.reset()
        hidden = rng.getrandbits(64)
        e.mem.w16(f.body + 0x10, 4 | (2 if enabled else 0))
        e.mem.w64(f.body + 8, hidden)
        e.mem.w32(0x41b514, counter)
        e.r[4] = f.obj
        e.r[5] = f.context
        assert e.run(0x1a3580, until=(0x1a3604,), max_steps=1000) == 'stop'
        assert e.mem.u64(f.obj + 0x220) == ref.initial_body_mask(counter, hidden, enabled, variants)
        expected_calls = int(0x111 <= counter <= 0x7fffffff)
        calls = [c for c in e.calls if c.target == BUILD_MASK]
        assert len(calls) == expected_calls
        assert all(c.args[:2] == (f.body, 1) for c in calls)
        f.check()
        initial += 1
    return count, initial


def direct_parts(f):
    e, rng = f.e, f.rng
    count = 0
    for header, override, mirrored in itertools.product(range(-1, 16), range(-1, 16), (False, True)):
        for requested, mesh_count, table_count, show in (
                (-5, 1, 1, 0), (0, 4, 1, ref.U64), (8, 5, 3, 0b10101),
                (1, 63, 2, rng.getrandbits(64)), (1, 64, 2, rng.getrandbits(64)),
                (0, 64, 1, 1 << 63), (0, 64, 1, 1), (0, 64, 1, ref.U64)):
            f.reset(mirrored)
            rows = f.model(f.parts[0], header, mesh_count, table_count,
                           flags=0x10 if count % 2 else 0,
                           lengths=tuple(rng.randrange(4) for _ in range(mesh_count)))
            e.call(DRAW_PART, f.parts[0], f.textures[0], 1, f.body, f.context,
                   show, override, requested, max_steps=6000)
            f.check_attachment(header, override, mirrored)
            f.check_runs(rows[ref.mesh_table_index(requested, table_count)], show)
            assert len(f.submitted) == 1
            assert f.submitted[0] == (f.packet, 1, f.textures[0], f.context, 0)
            f.check()
            count += 1
    # Null model returns before setup or submission, even with no parent.
    f.reset()
    e.call(DRAW_PART, 0, 0, 1, 0, 0, ref.U64, -1, 0, max_steps=100)
    assert not e.calls and not f.submitted
    f.check()
    # No attachment read occurs for header -1, even with a nonnegative override
    # and a null parent. Parent flag 0x04 is not consulted by this selector.
    for header, override, parent, parent_flags in ((-1, 15, 0, 0), (8, -1, f.body, 0)):
        f.reset()
        f.model(f.parts[0], header, 4, 1)
        e.mem.w16(f.body + 0x10, parent_flags)
        e.call(DRAW_PART, f.parts[0], f.textures[0], 1, parent, f.context,
               ref.U64, override, 0, max_steps=3000)
        f.check_attachment(header, override)
        assert len(f.submitted) == 1
        f.check()
        count += 1
    return count + 1


def cover_cases(f):
    e = f.e
    count = 0
    # Two exact/embedded forms, all three relevant slots and a neutral control.
    for model, prior, slot, name_id, picture_id, embedded in itertools.product(
            range(12), (False, True), (0, 4, 11), (None, 0, 3),
            (None, 1, 2, 4), (False, True)):
        f.reset()
        hits = f.strings(name_id, picture_id, embedded)
        e.mem.w32(f.record + 0x54, model)
        e.mem.w8(f.definition + 0x1c, slot)
        e.mem.w32(e.r[29], f.parts[0])
        e.mem.w32(e.r[29] + 4, f.textures[0])
        e.r[18], e.r[21], e.r[22] = f.item, f.record, int(prior)
        assert e.run(0x1a3b90, until=(0x1a3cd0, 0x1a3df8), max_steps=2500) == 'stop'
        assert e.pc == 0x1a3cd0
        assert bool(e.r[22]) == ref.cover_flag(model, slot, prior, True, hits)
        assert all(c.target == SUBSTRING and not c.stubbed for c in e.calls)
        f.check()
        count += 1
    # Individually missing mesh or texture never enters substring producers.
    for model, prior, mesh, texture in itertools.product(range(12), (False, True), (False, True), (False, True)):
        if mesh and texture:
            continue
        f.reset()
        e.mem.w32(e.r[29], f.parts[0] if mesh else 0)
        e.mem.w32(e.r[29] + 4, f.textures[0] if texture else 0)
        e.r[18], e.r[21], e.r[22] = 0, f.record, int(prior)
        e.mem.w32(f.record + 0x54, model)
        assert e.run(0x1a3b90, until=(0x1a3cd0, 0x1a3df8), max_steps=100) == 'stop'
        assert e.pc == 0x1a3df8 and bool(e.r[22]) == prior and not e.calls
        f.check()
        count += 1
    # Model 9 explicitly guards a null picture pointer before its second test.
    for slot, name_id, prior in itertools.product((0, 4, 11), (None, 0, 3), (False, True)):
        f.reset()
        hits = f.strings(name_id)
        e.mem.w32(f.definition + 0x30, 0)
        e.mem.w32(f.record + 0x54, 9)
        e.mem.w8(f.definition + 0x1c, slot)
        e.mem.w32(e.r[29], f.parts[0])
        e.mem.w32(e.r[29] + 4, f.textures[0])
        e.r[18], e.r[21], e.r[22] = f.item, f.record, int(prior)
        assert e.run(0x1a3b90, until=(0x1a3cd0,), max_steps=2500) == 'stop'
        assert bool(e.r[22]) == ref.cover_flag(9, slot, prior, True, hits)
        f.check()
        count += 1
    e.mem.w32(f.definition + 0x30, f.picture)
    return count


def appearance_cases(f):
    e, rng = f.e, f.rng
    count, draws = 0, 0
    # Independent mesh/texture presence exercises all sixteen handle patterns.
    for model, skin, cover, head_kind, bits in itertools.product(
            range(12), (0, 3, 4, 0xff), (False, True), range(3), range(16)):
        f.reset()
        f.strings(5 if head_kind == 2 else None, embedded=True)
        e.mem.w32(f.record + 0x54, model)
        e.mem.w8(f.record + 0x23, skin)
        e.mem.w32(f.record + 0x441c, f.item if head_kind else 0)
        pairs = ((bool(bits & 1), bool(bits & 2)), (bool(bits & 4), bool(bits & 8)))
        for i, (mesh_off, tex_off) in enumerate(((0x548, 0x558), (0x54c, 0x554))):
            f.model(f.parts[i], i + 2, 4, 1)
            e.mem.w32(f.obj + mesh_off, f.parts[i] if pairs[i][0] else 0)
            e.mem.w32(f.obj + tex_off, f.textures[i] if pairs[i][1] else 0)
        initial = rng.getrandbits(64)
        hides = (rng.getrandbits(64), rng.getrandbits(64))
        e.mem.w64(f.obj + 0x220, initial)
        for part, hide in zip(f.parts, hides):
            e.mem.w64(part, hide)
        e.r[19], e.r[21], e.r[22], e.r[30] = f.obj, f.record, int(cover), f.context
        assert e.run(0x1a3e08, until=(0x1a3f34,), max_steps=5000) == 'stop'
        expected = ref.appearance_draws(model, skin, cover, bool(head_kind), head_kind == 2, pairs)
        calls = [c for c in e.calls if c.target == DRAW_PART]
        assert [c.args for c in calls] == [
            (f.parts[i], f.textures[i], 1, f.body, f.context, ref.U64, ref.U64, 0)
            for i in expected], 'appearance call arguments'
        attachment_reads = [(a, v) for pc, a, _, v in e.reads if pc == 0x176134]
        assert attachment_reads == [(f.body + 0x400 + (i + 2) * 0x34, f.joints[i + 2])
                                    for i in expected]
        assert e.mem.u64(f.obj + 0x220) == ref.clear_drawn_hide_bits(initial, [hides[i] for i in expected])
        hide_writes = [pc for pc, addr, _, _ in e.writes if addr == f.obj + 0x220]
        assert hide_writes == [0x1a3e84 if i == 0 else 0x1a3f30 for i in expected]
        assert len(f.submitted) == len(expected)
        f.check()
        count += 1
        draws += len(expected)
    return count, draws


def linked_cases(f):
    """One equipment iteration then final appearance, not the full 17-slot loop.

    Original 0x1a3580 -> 0x1a3604 initializes the body mask. We then supply
    resolved resource handles and a private record at 0x1a3b90, run through
    0x1a3df8, and resume at 0x1a3e08. Resource lookup and other equipped slots
    are excluded. item+8 flags are zero: original 0x1068d8/0x1046c4 select
    the no-effect path. Original second-slot override and model-2 mirror/reset
    run too; definition slot 3's variant mapping is outside this slice corpus.
    """
    e, rng = f.e, f.rng
    counts, draw_count = 0, 0
    cases = ((0, 0, None, None), (0, 1, None, None), (11, 11, None, None),
             (11, 11, 0, None), (11, 11, None, 1), (11, 11, 5, None),
             (4, 4, None, 2), (4, 4, 3, None), (4, 4, None, 4),
             (4, 4, None, None))
    for model, skin, pair_bits, case in itertools.product(range(12), (0, 4), range(4), cases):
        f.reset()
        slot, loop_index, name_id, picture_id = case
        hits = f.strings(name_id, picture_id, embedded=True)
        e.mem.w32(f.record + 0x54, model)
        e.mem.w8(f.record + 0x23, skin)
        e.mem.w8(f.definition + 0x1c, slot)
        e.mem.w64(f.item + 8, 0)
        head = slot == 11
        e.mem.w32(f.record + 0x441c, f.item if head else 0)
        hidden, add, remove = (rng.getrandbits(64) for _ in range(3))
        e.mem.w16(f.body + 0x10, 6)
        e.mem.w8(f.body + 0x21, 4)
        e.mem.w64(f.body + 8, hidden)
        e.mem.w64(f.body + 0x40, add)
        e.mem.w64(f.body + 0x48, remove)
        counter = 0x110 + (counts % 2)
        e.mem.w32(0x41b514, counter)
        e.r[4], e.r[5] = f.obj, f.context
        assert e.run(0x1a3580, until=(0x1a3604,), max_steps=1000) == 'stop'
        initial = ref.initial_body_mask(counter, hidden, True, [(add, remove)])
        assert e.mem.u64(f.obj + 0x220) == initial
        for i, (mesh_off, texture_off) in enumerate(((0x548, 0x558), (0x54c, 0x554))):
            f.model(f.parts[i], 2 + i, 4, 1)
            e.mem.w32(f.obj + mesh_off, f.parts[i])
            e.mem.w32(f.obj + texture_off, f.textures[i])
        f.model(f.equipment, 8, 4, 1)
        hides = tuple(rng.getrandbits(64) for _ in range(3))
        for part, hide in zip((f.equipment,) + f.parts, hides):
            e.mem.w64(part, hide)
        e.mem.w32(e.r[29], f.equipment if pair_bits & 1 else 0)
        e.mem.w32(e.r[29] + 4, f.equipment_texture if pair_bits & 2 else 0)
        e.r[18], e.r[19], e.r[21] = f.item, f.obj, f.record
        e.r[22], e.r[23], e.r[30] = 0, loop_index, f.context
        assert e.run(0x1a3b90, until=(0x1a3df8,), max_steps=5000) == 'stop'
        paired = pair_bits == 3
        covered = ref.cover_flag(model, slot, False, paired, hits)
        assert bool(e.r[22]) == covered
        assert e.mem.u64(f.obj + 0x220) == ref.clear_drawn_hide_bits(initial, hides[:1] if paired else ())
        assert e.run(0x1a3e08, until=(0x1a3f34,), max_steps=5000) == 'stop'
        parts = ref.appearance_draws(model, skin, covered, head, name_id == 5,
                                    ((True, True), (True, True)))
        expected_models = ([f.equipment] if paired else []) + [f.parts[i] for i in parts]
        draw_calls = [c for c in e.calls if c.target == DRAW_PART]
        assert [c.args[0] for c in draw_calls] == expected_models
        override = 1 if loop_index == 1 else -1
        if paired:
            assert draw_calls[0].args == (f.equipment, f.equipment_texture, 1, f.body,
                                         f.context, ref.U64, override & ref.U64, 0)
        selected = ([ref.attachment_index(8, override)] if paired else []) + [i + 2 for i in parts]
        assert [(a, v) for pc, a, _, v in e.reads if pc == 0x176134] == [
            (f.body + 0x400 + i * 0x34, f.joints[i]) for i in selected]
        visible_hides = ([hides[0]] if paired else []) + [hides[i + 1] for i in parts]
        assert e.mem.u64(f.obj + 0x220) == ref.clear_drawn_hide_bits(initial, visible_hides)
        assert len(f.submitted) == len(expected_models)
        assert e.mem.u32(DRAW_FLAGS) == 0
        f.check()
        counts += 1
        draw_count += len(expected_models)
    return counts, draw_count


def _projection_bits(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def _expect_shell(e, flag33, argument, fill):
    pointer, count, fields = ref.shell_fields(flag33, argument)
    assert e.mem.u32(ref.SHELL_POINTER) == pointer
    assert e.mem.u32(ref.SHELL_COUNT) == count
    blob = bytearray(e.mem.read(ref.SHELL_BLOCK, 16))
    if fields is None:
        assert bytes(blob) == bytes([fill]) * 16
        return
    for offset, value in fields.items():
        if offset in (4, 12):
            assert int.from_bytes(blob[offset:offset + 4], 'little') == value
        else:
            assert blob[offset] == value
    written = set(fields) | {5, 6, 7, 13, 14, 15}
    for offset, byte in enumerate(blob):
        if offset not in written:
            assert byte == fill


def visual_cases(f):
    """Shield bits, published starting slots, and shell words. Not a 17-slot loop."""
    e, rng = f.e, f.rng
    records = tuple((1 << i, 1 << (i + 17)) for i in range(10))
    hidden = 0x1111111111111111
    shield = starting = shell_rows = 0
    for model, enabled, flag33 in itertools.product(
            list(range(12)) + [-1, 12, 15], (False, True), (False, True)):
        f.reset()
        argument = ref.equipped_draw_argument(_projection_bits(200 if flag33 else 0))
        e.f[20] = argument
        e.mem.write(ref.SHELL_BLOCK, bytes([0xa5]) * 16)
        f.strings()
        e.mem.w32(f.record + 0x50, 0x15)
        e.mem.w32(f.record + 0x54, model & 0xffffffff)
        e.mem.w8(f.definition + 0x1c, 3)
        e.mem.w64(f.item + 8, (1 << 33) if flag33 else 0)
        header = (model * 3 + 5) & 15
        f.model(f.equipment, header, 4, 1, flags=2 if enabled else 0)
        e.mem.w8(f.equipment + 0x21, 4)
        e.mem.w64(f.equipment + 8, hidden)
        for index, (show, hide) in enumerate(records):
            e.mem.w64(f.equipment + 0x40 + index * 16, show)
            e.mem.w64(f.equipment + 0x48 + index * 16, hide)
        hide_mask = rng.getrandbits(64)
        e.mem.w64(f.equipment, hide_mask)
        initial = rng.getrandbits(64)
        e.mem.w64(f.obj + 0x220, initial)
        e.mem.w32(e.r[29], f.equipment)
        e.mem.w32(e.r[29] + 4, f.equipment_texture)
        e.r[18], e.r[19], e.r[21] = f.item, f.obj, f.record
        e.r[22], e.r[23], e.r[30] = 0, 3, f.context
        assert e.run(0x1a3b90, until=(0x1a3df8,), max_steps=8000) == 'stop'
        selection = ref.shield_selection(model)
        assert [c.args[:2] for c in e.calls if c.target == BUILD_MASK] == [
            (f.equipment, selection)]
        show = ref.variant_show_mask(hidden, enabled, selection, records)
        draws = [c for c in e.calls if c.target == DRAW_PART]
        assert len(draws) == 1
        assert draws[0].args == (f.equipment, f.equipment_texture, 1, f.body,
                                 f.context, show, ref.U64, 0)
        f.check_attachment(header, -1)
        assert e.mem.u64(f.obj + 0x220) == ref.clear_drawn_hide_bits(initial, [hide_mask])
        assert not [row for row in e.reads if row[1] <= f.record + 0x50 < row[1] + row[2]]
        _expect_shell(e, flag33, argument, 0xa5)
        assert e.mem.u32(DRAW_FLAGS) == 0
        f.check()
        shield += 1
    # Published pointer slots. Class is stored and must not be read. None is slot 1,
    # so the second-weapon override and the model-2 mirror stay off.
    for body in range(12):
        class_index, slots = ref.starting_visual_slots(body)
        for slot in slots:
            f.reset()
            e.f[20] = ref.equipped_draw_argument(_projection_bits(5))
            e.mem.write(ref.SHELL_BLOCK, bytes([0xa5]) * 16)
            f.strings()
            e.mem.w32(f.record + 0x50, class_index ^ 0xff)
            e.mem.w32(f.record + 0x54, body)
            e.mem.w8(f.definition + 0x1c, slot)
            e.mem.w64(f.item + 8, 0)
            header = (body + slot) & 15
            f.model(f.equipment, header, 4, 1)
            hide_mask = rng.getrandbits(64)
            e.mem.w64(f.equipment, hide_mask)
            initial = rng.getrandbits(64)
            e.mem.w64(f.obj + 0x220, initial)
            e.mem.w32(e.r[29], f.equipment)
            e.mem.w32(e.r[29] + 4, f.equipment_texture)
            e.r[18], e.r[19], e.r[21] = f.item, f.obj, f.record
            e.r[22], e.r[23], e.r[30] = 0, slot, f.context
            assert e.run(0x1a3b90, until=(0x1a3df8,), max_steps=8000) == 'stop'
            assert not [c for c in e.calls if c.target == BUILD_MASK]
            draws = [c for c in e.calls if c.target == DRAW_PART]
            assert draws[0].args == (f.equipment, f.equipment_texture, 1, f.body,
                                     f.context, ref.U64, ref.U64, 0)
            f.check_attachment(header, -1)
            assert not [c for c in e.calls if c.target == 0x179860]
            assert e.mem.u64(f.obj + 0x220) == ref.clear_drawn_hide_bits(initial, [hide_mask])
            assert not [row for row in e.reads if row[1] <= f.record + 0x50 < row[1] + row[2]]
            _expect_shell(e, False, e.f[20], 0xa5)
            f.check()
            starting += 1
    # Off-hand pointer composes with the shield bit, and model 2 mirrors then resets.
    for model, slot in ((2, 3), (2, 0), (4, 1)):
        f.reset()
        argument = ref.equipped_draw_argument(_projection_bits(330))
        e.f[20] = argument
        e.mem.write(ref.SHELL_BLOCK, bytes([0xa5]) * 16)
        f.strings()
        e.mem.w32(f.record + 0x54, model)
        e.mem.w8(f.definition + 0x1c, slot)
        e.mem.w64(f.item + 8, 1 << 33)
        header = 4
        f.model(f.equipment, header, 4, 1, flags=2)
        e.mem.w8(f.equipment + 0x21, 4)
        e.mem.w64(f.equipment + 8, hidden)
        for index, (show, hide) in enumerate(records):
            e.mem.w64(f.equipment + 0x40 + index * 16, show)
            e.mem.w64(f.equipment + 0x48 + index * 16, hide)
        e.mem.w64(f.equipment, 0)
        e.mem.w64(f.obj + 0x220, ref.U64)
        e.mem.w32(e.r[29], f.equipment)
        e.mem.w32(e.r[29] + 4, f.equipment_texture)
        e.r[18], e.r[19], e.r[21] = f.item, f.obj, f.record
        e.r[22], e.r[23], e.r[30] = 0, 1, f.context
        assert e.run(0x1a3b90, until=(0x1a3df8,), max_steps=8000) == 'stop'
        override = ref.equipped_override(1)
        mirrored = model == 2
        if slot == 3:
            selection = ref.shield_selection(model)
            show = ref.variant_show_mask(hidden, True, selection, records)
            assert [c.args[:2] for c in e.calls if c.target == BUILD_MASK] == [
                (f.equipment, selection)]
        else:
            show = ref.U64
            assert not [c for c in e.calls if c.target == BUILD_MASK]
        draws = [c for c in e.calls if c.target == DRAW_PART]
        assert draws[0].args[5:8] == (show, override & ref.U64, 0)
        f.check_attachment(header, override, mirrored)
        assert bool([c for c in e.calls if c.target == 0x179860]) == mirrored
        assert e.mem.u32(DRAW_FLAGS) == 0
        # The mirror reset replaces the shell pointer and clears the count.
        assert e.mem.u32(ref.SHELL_POINTER) == 0x41c150
        assert e.mem.u32(ref.SHELL_COUNT) == 0
        f.check()
        shell_rows += 1
    return shield, starting, shell_rows


def shell_cases(f):
    e = f.e
    direct = argument = 0
    values = (0.0, 0.5, 1.0, 1.5, 5.0, -1.0, 100.0, 200.0, 360.0, -1000.0)
    for flag33, value in itertools.product((False, True), values):
        f.reset()
        argument_bits = ref.equipped_draw_argument(_projection_bits(value))
        e.mem.w64(f.item + 8, (1 << 33) if flag33 else 0)
        e.mem.write(ref.SHELL_BLOCK, bytes([0xa5]) * 16)
        e.f[12] = argument_bits
        e.call(0x1068d8, f.item, max_steps=2000)
        _expect_shell(e, flag33, argument_bits, 0xa5)
        f.check()
        direct += 1
    for value in values:
        f.reset()
        raw = _projection_bits(value)
        e.f[0] = raw
        e.f[1] = e.f[2] = e.f[6] = 0
        assert e.run(0x1a4cac, until=(0x1a3580,), max_steps=40) == 'stop'
        assert e.f[12] == ref.equipped_draw_argument(raw)
        f.check()
        argument += 1
    f.reset()
    e.f[12] = 0
    assert e.run(0x1c0c64, until=(0x1a3580,), max_steps=20) == 'stop'
    assert e.f[12] == ref.inventory_draw_argument()
    f.check()
    return direct, argument + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.path.join(_TOOL_DIR, '..', 'local', 'SLUS_209.73'))
    parser.add_argument('--seeds', type=int, nargs='+', default=(20973, 7))
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        assert hashlib.sha256(source.read()).hexdigest() == SHA256, 'wrong executable revision'
    # No ps2elf.analyze(): it could write a cache beside a private input symlink.
    for seed in args.seeds:
        f = Fixture(args.elf, seed)
        mask_count, initial_count = masks(f)
        direct_count = direct_parts(f)
        cover_count = cover_cases(f)
        gate_count, draws = appearance_cases(f)
        linked_count, linked_draws = linked_cases(f)
        shield_count, starting_count, composed_count = visual_cases(f)
        shell_count, argument_count = shell_cases(f)
        print('PASS seed=%d mask=%d initialization=%d direct_part=%d cover=%d appearance=%d draws=%d linked=%d linked_draws=%d shield=%d starting=%d composed=%d shell=%d argument=%d' %
              (seed, mask_count, initial_count, direct_count, cover_count, gate_count, draws,
               linked_count, linked_draws, shield_count, starting_count, composed_count,
               shell_count, argument_count))


if __name__ == '__main__':
    main()
