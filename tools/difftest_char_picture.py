#!/usr/bin/env python3
"""Pose, body-mask consumption, and the shell primitive. Counts only.

Run from the worktree root with PYTHONDONTWRITEBYTECODE=1. unittest is imported
before tools/ is on sys.path. The executable is pinned before any code runs.

Executed:
* creation restart 0x2254bc–0x2255b4, plus the intro4 and intro2 call setups.
  Time and weight are planted nonzero and must be stored as 0. Flags 3 are
  read back. Race bytes -1..11 (slots 0..12) each run the import-literal row.
* inventory_selectIdleAnim 0x1c3f08 and the inventory draw's unit advance.
  A fresh cell's time and weight are planted nonzero. The step must store
  time 0x3f7fffff and weight 1.
* player_resetIdleAnim 0x1b2470, including the unread time word
* Creature_draw's load at 0x10ba84 and inventory's load at 0x1c0a28,
  then the show-mask walk 0x177df4–0x177eb0
* model_emitShellPasses 0x174e78, and the flag/count gates in model_draw
  and model_drawPart

Observed, not a run of playerSel_task: every direct jal/j target, every
linking branch (REGIMM rt 16-19), every jalr and every jr through a register
other than $ra from 0x225478 through 0x22e700. Across the executable: every
jal, j and linking branch that names anim_advance, every lui-pair site under
two register rules (the Elf.analyze reset at heuristic function starts, and no
reset at all), and every aligned word in every allocated section that has file
data. Then the direct-call closure of the span over the exact bodies in
ghidra_funcs.tsv: jal, linking branches, and j that leaves its body. Indirect
calls inside that closure are counted, not followed; tools/difftest_char_frame.py
records them at run time.

Renderer submission stays stubbed. No archive bytes are printed.
"""
import os
import sys

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or os.curdir) != _TOOL_DIR]
import unittest  # noqa: E402,F401
import argparse
import hashlib
import struct

sys.path.insert(0, _TOOL_DIR)
from ee_emu import EE
import ps2elf
import ref_char_attachment as ref

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
SCRATCH_PTR = 0x4fdb7c
DESCRIPTOR = 0x4fbbf8
STRIDE = 0x26c
RACE_OUT = 0x8e2c98
RACE_INDEX = 0x8e2c91
ARCHIVE = 0x8e2c8c
SHELL_LIST = 0x41c160
SHELL_COUNT = 0x41c164
RES_FIND = 0x17365c
ANIM_START = 0x16cfe0
ANIM_ADVANCE = 0x16d748
RELEASE = 0x171118
MODEL_DRAW = 0x1779b0
SHELL = 0x174e78
DRAW_PART = 0x178c28
SEL_LO = 0x225478
SEL_HI = 0x22e700
FLAGS_AT = 0x225580
# Direct targets the selection span must not name. The last five are the
# other entry points that write a track time.
ADVANCE_DIRECT = (
    ANIM_ADVANCE, 0x1709d8, 0x1709f8, 0x16d0b8, 0x170bc8, 0x170c80,
)
SENTINEL_TIME = 0x55555555
SENTINEL_WEIGHT = 0x66666666
_LOAD_OPS = (0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x28, 0x29, 0x2B,
             0x31, 0x39, 0x37, 0x3F, 0x1E, 0x1F)


def _text_words(elf):
    base, offset, size = elf.text
    count = size // 4
    return base, struct.unpack_from('<%dI' % count, elf.d, offset)


def _function_starts(elf, words, base):
    starts = set()
    for index, word in enumerate(words):
        if word >> 26 != 3:
            continue
        pc = base + index * 4
        target = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if elf.in_text(target):
            starts.add(target)
    for name in ('.data', '.rodata', '.ctors', '.dtors', '.sdata'):
        section = elf.sections.get(name)
        if section is None:
            continue
        _addr, offset, size = section
        for pos in range(0, size - 3, 4):
            value, = struct.unpack_from('<I', elf.d, offset + pos)
            if elf.in_text(value) and value % 4 == 0:
                starts.add(value)
    for index in range(len(words) - 2):
        if words[index] != 0x03E00008:
            continue
        cursor = index + 2
        while cursor < len(words) and words[cursor] == 0:
            cursor += 1
        if cursor < len(words) and (words[cursor] & 0xFFFF8000) == 0x27BD8000:
            starts.add(base + cursor * 4)
    return starts


def _composed_sites(words, base, starts, target):
    """lui/addiu/ori/load sites, with the same register reset Elf.analyze uses."""
    sites = []
    hi = {}
    for index, word in enumerate(words):
        pc = base + index * 4
        if pc in starts:
            hi = {}
        op = word >> 26
        rs, rt, imm = (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0x0F:
            hi[rt] = imm << 16
        elif op in (0x09, 0x19) and rs in hi:
            value = (hi[rs] + simm) & 0xFFFFFFFF
            if value == target:
                sites.append(pc)
            if rt == rs:
                hi.pop(rs, None)
                hi['v%d' % rt] = value
        elif op == 0x0D and rs in hi and (hi[rs] | imm) == target:
            sites.append(pc)
        elif op in _LOAD_OPS and rs in hi and ((hi[rs] + simm) & 0xFFFFFFFF) == target:
            sites.append(pc)
    return sites


LINK_RT = (16, 17, 18, 19)   # bltzal, bgezal, bltzall, bgezall
HOLDERS = (0x1162b0, 0x189870, 0x1b9520, 0x1709d8)   # functions holding the four sites


def _direct_in_span(words, base, jrs=None):
    jals, jumps, links, jalrs = [], [], [], []
    for index, word in enumerate(words):
        pc = base + index * 4
        if pc < SEL_LO or pc > SEL_HI:
            continue
        op = word >> 26
        if op in (2, 3):
            target = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            (jals if op == 3 else jumps).append((pc, target))
        elif op == 1 and ((word >> 16) & 31) in LINK_RT:
            imm = word & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            links.append((pc, (pc + 4 + (simm << 2)) & 0xFFFFFFFF))
        elif op == 0 and (word & 0x3F) == 9:
            jalrs.append(pc)
        elif op == 0 and (word & 0x3F) == 8 and ((word >> 21) & 31) != 31 and jrs is not None:
            jrs.append((pc, (word >> 21) & 31))
    return jals, jumps, links, jalrs


def _data_words(elf, target):
    """Aligned words equal to target in every allocated section with file data."""
    hits, scanned = [], []
    for name, (addr, offset, size) in elf.sections.items():
        if not addr or name in ('.text', '.bss', '.sbss', '.vubss') or offset + size > len(elf.d):
            continue
        scanned.append(name)
        start = (4 - addr % 4) % 4
        for pos in range(start, size - 3, 4):
            if struct.unpack_from('<I', elf.d, offset + pos)[0] == target:
                hits.append(addr + pos)
    return hits, scanned


def _composed_noreset(words, base, target):
    """lui-pair sites with no reset at function starts (the wider rule)."""
    return _composed_sites(words, base, set(), target)


def _bodies(path):
    """Exact function bodies from ghidra_funcs.tsv: entry -> [(lo, hi_inclusive)]."""
    bodies = {}
    with open(path) as source:
        for line in source:
            if not line.strip() or line.startswith('#'):
                continue
            entry, _name, body = line.rstrip('\n').split('\t')
            ranges = []
            for part in body.split(','):
                if part:
                    lo, hi = (int(x, 16) for x in part.split('-'))
                    ranges.append((lo, hi))
            bodies[int(entry, 16)] = ranges
    return bodies


def closure(elf, words, base, roots, bodies):
    """Direct-call closure. Returns (reached entries, parent map, indirect sites)."""
    owner = []
    for entry, ranges in bodies.items():
        for lo, hi in ranges:
            owner.append((lo, hi, entry))
    owner.sort()
    import bisect
    starts = [lo for lo, _hi, _e in owner]

    def entry_of(address):
        i = bisect.bisect_right(starts, address) - 1
        if i >= 0 and owner[i][0] <= address <= owner[i][1]:
            return owner[i][2]
        return None
    parent, queue, indirect = {}, [], []
    for root in roots:
        entry = entry_of(root)
        if entry is not None and entry not in parent:
            parent[entry] = None
            queue.append(entry)
    while queue:
        entry = queue.pop(0)
        for lo, hi in bodies[entry]:
            for pc in range(lo, hi + 1, 4):
                if not elf.in_text(pc):
                    continue
                word = words[(pc - base) // 4]
                op = word >> 26
                target = None
                if op in (2, 3):
                    target = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
                    if op == 2 and entry_of(target) == entry:
                        target = None
                elif op == 1 and ((word >> 16) & 31) in LINK_RT:
                    imm = word & 0xFFFF
                    simm = imm - 0x10000 if imm & 0x8000 else imm
                    target = (pc + 4 + (simm << 2)) & 0xFFFFFFFF
                elif op == 0 and (word & 0x3F) == 9:
                    indirect.append(pc)
                elif op == 0 and (word & 0x3F) == 8 and ((word >> 21) & 31) != 31:
                    indirect.append(pc)
                if target is None:
                    continue
                callee = entry_of(target)
                if callee is not None and callee not in parent:
                    parent[callee] = (entry, pc)
                    queue.append(callee)
    return parent, indirect


def selection_census(path):
    """Direct-call census of playerSel_task through 0x22e700. Not a task run."""
    elf = ps2elf.Elf(path)
    base, words = _text_words(elf)
    jrs = []
    jals, jumps, links, jalrs = _direct_in_span(words, base, jrs)
    family = set(ADVANCE_DIRECT)
    named = sorted({target for _pc, target in jals + jumps + links if target in family})
    check(not named and not jalrs, 'selection span names an advance entry or uses jalr')
    unique = sorted({target for _pc, target in jals})
    check(unique, 'selection span has no direct calls')
    holders = sorted(set(unique) & set(HOLDERS))
    check(not holders, 'a direct target holds an anim_advance site')
    advance_jals, advance_jumps, advance_links = [], [], []
    for index, word in enumerate(words):
        pc = base + index * 4
        op = word >> 26
        if op in (2, 3):
            target = (pc & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        elif op == 1 and ((word >> 16) & 31) in LINK_RT:
            imm = word & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            target = (pc + 4 + (simm << 2)) & 0xFFFFFFFF
        else:
            continue
        if target != ANIM_ADVANCE:
            continue
        if op == 3:
            advance_jals.append(pc)
        elif op == 2:
            advance_jumps.append(pc)
        else:
            advance_links.append(pc)
    starts = _function_starts(elf, words, base)
    advance_refs = _composed_sites(words, base, starts, ANIM_ADVANCE)
    wide_refs = _composed_noreset(words, base, ANIM_ADVANCE)
    advance_ptrs = elf.ptrs_to(ANIM_ADVANCE)
    data_ptrs, scanned = _data_words(elf, ANIM_ADVANCE)
    check(set(advance_ptrs) <= set(data_ptrs), 'the wider data scan covers ptrs_to')
    inside = [site for site in advance_jals + advance_jumps + advance_links + advance_refs
              + wide_refs + data_ptrs if SEL_LO <= site <= SEL_HI]
    check(not inside, 'anim_advance is named inside the selection span')
    bodies = _bodies(os.path.join(_TOOL_DIR, '..', 'ghidra_funcs.tsv'))
    roots = [pc for pc in range(SEL_LO, SEL_HI + 1, 4)]
    parent, indirect = closure(elf, words, base, roots, bodies)
    reached_family = sorted(set(parent) & (family | set(HOLDERS)))
    print('CENSUS range=0x%x-0x%x inclusive jal=%d j=%d bal=%d jalr=%d jr_other=%d unique=%d '
          'advance_direct=%s holders=%s'
          % (SEL_LO, SEL_HI, len(jals), len(jumps), len(links), len(jalrs), len(jrs),
             len(unique), ' '.join('%x' % t for t in named) or '-',
             ' '.join('%x' % t for t in holders) or '-'), flush=True)
    print('CENSUS jr_other %s' % (' '.join('%x:r%d' % site for site in jrs) or '-'), flush=True)
    print('CENSUS targets %s' % ' '.join('%x' % target for target in unique), flush=True)
    print('CENSUS anim_advance jal=%s j=%s bal=%s refs=%s refs_noreset=%s ptrs=%s in_range=%d' % (
        ' '.join('%x' % site for site in advance_jals) or '-',
        ' '.join('%x' % site for site in advance_jumps) or '-',
        ' '.join('%x' % site for site in advance_links) or '-',
        ' '.join('%x' % site for site in advance_refs) or '-',
        ' '.join('%x' % site for site in wide_refs) or '-',
        ' '.join('%x' % site for site in data_ptrs) or '-', len(inside)), flush=True)
    print('CENSUS data_sections %s' % ' '.join(sorted(scanned)), flush=True)
    paths = []
    for entry in reached_family:
        chain, at = [], entry
        while parent[at] is not None:
            chain.append('%x@%x' % (at, parent[at][1]))
            at = parent[at][0]
        chain.append('%x' % at)
        paths.append('<'.join(chain))
    print('CENSUS closure functions=%d indirect_sites=%d reached_writers=%s' % (
        len(parent), len(indirect), ' '.join(paths) or '-'), flush=True)
    return unique, reached_family


class Bounded(EE):
    allowed = {
        ANIM_START, 0x170d88, 0x1709d8, ANIM_ADVANCE, 0x22d2b4, 0x3b8534,
        0x3b868c, 0x3b7ef0, RES_FIND, RELEASE, MODEL_DRAW, SHELL, DRAW_PART,
        0x175fb8, 0x16b7f0, 0x166798, 0x16d558, 0x16e388, 0x16e468,
    }

    def _enter_call(self, target):
        if target not in self.allowed:
            raise AssertionError('unexpected callee 0x%x' % target)
        return super()._enter_call(target)


def check(value, message):
    if not value:
        raise AssertionError(message)


class Picture:
    def __init__(self, elf, seed):
        self.e = e = Bounded(elf)
        self.seed = seed
        e.mem.w32(0x404464, seed)
        e.mem.map(RACE_OUT, 0x100)
        self.scratch = e.alloc(0x1600 + 13 * 4)
        e.mem.w32(SCRATCH_PTR, self.scratch)
        e.mem.w32(ARCHIVE, 0x5353e0)
        self.objects = []
        for index in range(13):
            obj = e.alloc(0x600)
            e.mem.w32(self.scratch + 0x1558 + 4 * index, obj)
            e.mem.w8(obj + 0x119, 8)
            self.objects.append(obj)
        self.names = []
        self.clips = []
        self.clip_of = {}
        self.slice_targets = set()
        e.stub(RES_FIND, function=self._found, name='res_find')
        e.stub(0x3b7ef0, function=self._format, name='sprintf')
        e.stub(RELEASE, ret=0, name='anim_releaseCaches')

    def _found(self, e):
        pair = (e.mem.cstr(e.r[4]), e.mem.cstr(e.r[5]))
        self.names.append(pair)
        if pair not in self.clip_of:
            self.clip_of[pair] = 0x600000 + len(self.clip_of) * 0x40
        clip = self.clip_of[pair]
        self.clips.append(clip)
        return clip

    def _format(self, e):
        # The game selects the format pointer. Only the four `%s` suffixes occur here.
        text = e.mem.cstr(e.r[6]) + e.mem.cstr(e.r[5])[2:]
        e.mem.write(e.r[4], text.encode('latin1') + b'\0')
        return len(text)

    def sp(self):
        self.e.r[29] = self.e.STACK_HI - 0x1000

    def prime(self, index, flags, count):
        obj = self.objects[index]
        self.e.mem.w8(obj + 0x118, count)
        self.e.mem.w16(obj + 0x11a, flags)
        return obj

    def cell(self, obj):
        e = self.e
        return {
            'clip': e.mem.u32(obj + 0x11c),
            'weight': e.mem.u32(obj + 0x124),
            'rate': e.mem.u32(obj + 0x128),
            'life': e.mem.u32(obj + 0x12c),
            'time': e.mem.u32(obj + 0x134),
            'flags': e.mem.u16(obj + 0x138),
            'count': e.mem.u8(obj + 0x118),
        }


def expected_name(e, row, marked):
    literal = e.mem.cstr(ref.IMPORT_LITERAL)
    source = e.mem.u32(DESCRIPTOR + row * STRIDE)
    token = e.mem.cstr(source)
    if token == literal:
        address = ref.race_literal(e.mem.s8(RACE_INDEX))
        check(address is not None, 'race index outside the copied range')
        token = e.mem.cstr(address)
    form = e.mem.cstr(ref.INTRO_STANDING_MARKED if marked else ref.INTRO_STANDING)
    return ref.creation_clip_name(token.encode('latin1'), form.encode('latin1')).decode('latin1')


def plant_track(e, track):
    """Nonzero time and weight. A later 0 is a store, not a leftover fill."""
    e.mem.w32(track + 0x18, SENTINEL_TIME)
    e.mem.w32(track + 8, SENTINEL_WEIGHT)


def literal_rows(e):
    """Rows whose descriptor pointer is 0x53fd38, and rows that only copy its text."""
    literal = e.mem.cstr(ref.IMPORT_LITERAL)
    pointers, copies = [], []
    for row in range(13):
        source = e.mem.u32(DESCRIPTOR + row * STRIDE)
        if source == ref.IMPORT_LITERAL:
            pointers.append(row)
        elif literal is not None and e.mem.cstr(source) == literal:
            copies.append(row)
    return pointers, copies


def restart(pic, marked, flags, track_count, expect, race_byte):
    e = pic.e
    for obj in pic.objects:
        e.mem.write(obj + 0x114, bytes(0x80))
        e.mem.w8(obj + 0x119, 8)
    e.mem.w8(RACE_INDEX, race_byte)
    for index in range(13):
        obj = pic.prime(index, flags, track_count)
        if expect:
            plant_track(e, obj + 0x11c + 0x20 * track_count)
    pic.names.clear()
    pic.clips.clear()
    pic.sp()
    e.reset_log()
    check(e.run(0x2254bc, until=(0x2255b4,), max_steps=200000) == 'stop', 'restart slice')
    pic.slice_targets.update(call.target for call in e.calls)
    if not expect:
        check(not any(call.target == ANIM_START for call in e.calls), 'restart guard')
        return
    check(sum(call.target == 0x22d2b4 for call in e.calls) == 13, 'race selector')
    check(len(pic.names) == 13, 'one creation name per carousel row')
    for row, obj in enumerate(pic.objects):
        base = obj + 0x11c + 0x20 * track_count
        check(pic.names[row][1] == expected_name(e, row, marked), 'creation clip name')
        check(e.mem.u32(base) == pic.clips[row], 'creation clip pointer')
        check(e.mem.u32(base + 0x18) == 0, 'creation time store')
        check(e.mem.u32(base + 8) == 0, 'creation weight store')
        rate = ref.BLEND_FORCED if track_count == 0 else 0x3daaaaab
        check(e.mem.u32(base + 0xc) == rate, 'creation blend')
        check(e.mem.u32(base + 0x10) == ref.BLEND_FORCED, 'creation life')
        check(e.mem.u8(obj + 0x118) == track_count + 1, 'creation count')
        check(e.mem.u16(base + 0x1c) == 3, 'creation flags')


def creation(pic):
    e = pic.e
    word = e.mem.u32(FLAGS_AT)
    check((word >> 26) == 0x09 and (word & 0xFFFF) == 3, 'flags immediate')
    pointers, copies = literal_rows(e)
    check(pointers == [0] and not copies, 'import literal row')
    pic.literal = (pointers, copies)
    count = 0
    for marked, flags, track_count, expect in (
            (False, 0x80, 0, True), (True, 0x88, 1, True),
            (False, 0, 0, False), (False, 0x80, 2, False)):
        restart(pic, marked, flags, track_count, expect, 3)
        count += 1
    # Slots 0..12. Byte 3 is slot 4 and is also the gate row above.
    race = 0
    for race_byte in range(-1, 12):
        restart(pic, False, 0x80, 0, True, race_byte)
        race += 1
    # intro4 twice, intro2 once: the caller's flags and format, same time-zero cell.
    cases = (
        (0x226dec, 0x226e44, 6, ref.INTRO_ONCE, 'intro4'),
        (0x228508, 0x22855c, 0x16, ref.INTRO_ONCE, 'intro4-marked'),
        (0x228a88, 0x228ad8, 0xe, ref.INTRO_OTHER, 'intro2'),
    )
    name = e.alloc(8)
    e.mem.write(name, b'bm\0')
    for start, stop, flags, form, _label in cases:
        obj = pic.objects[0]
        e.mem.write(obj + 0x114, bytes(0x80))
        e.mem.w8(obj + 0x119, 8)
        plant_track(e, obj + 0x11c)
        pic.names.clear()
        pic.clips.clear()
        pic.sp()
        e.r[2] = name
        e.r[5] = 0x540000
        e.r[16] = 0
        e.r[17] = 0
        e.r[20] = e.r[29] + 0x290
        e.r[21] = 0x8e0000
        e.mem.write(e.r[29] + 0x290, bytes(32))
        e.reset_log()
        check(e.run(start, until=(stop,), max_steps=50000) == 'stop', 'transition slice')
        pic.slice_targets.update(call.target for call in e.calls)
        suffix = e.mem.cstr(form)
        want = ref.creation_clip_name(b'bm', suffix.encode('latin1')).decode('latin1')
        got_names = [got for _archive, got in pic.names]
        check(got_names == [want], 'transition name')
        got = pic.cell(obj)
        check(got['flags'] == flags, 'transition flags')
        check(got['time'] == 0, 'transition time store')
        check(got['weight'] == 0, 'transition weight store')
        check(got['rate'] == ref.BLEND_FORCED, 'transition blend forced on an empty state')
        count += 1
    advance = set(ADVANCE_DIRECT)
    check(not pic.slice_targets & advance, 'executed creation slice calls an advance entry')
    return count, race


def inventory_and_play(pic):
    e = pic.e
    count = 0
    record = 0x4d8af0
    state = e.alloc(0x120)
    for model in range(12):
        for weapon in range(8):
            for fast in (0, 1):
                e.mem.write(state, bytes(0x120))
                e.mem.w8(state + 5, 8)
                plant_track(e, state + 8)
                e.mem.w32(record + 0x43d8, pic.objects[0])
                e.mem.w32(record + 0x54, model)
                e.mem.w8(record + 0x4a86, weapon)
                pic.names.clear()
                pic.clips.clear()
                e.reset_log()
                e.call(0x1c3f08, 0, state, fast, max_steps=20000)
                lump = e.mem.cstr(ref.INVENTORY_LUMP[model])
                idle = e.mem.cstr(ref.inventory_idle_address(weapon))
                check([name for _archive, name in pic.names] == [idle, idle], 'inventory idle name')
                find = [c for c in e.calls if c.target == RES_FIND]
                check(len(find) == 2, 'lookup then start')
                check(e.mem.cstr(find[0].args[0]) == lump, 'inventory lump')
                check(e.mem.u32(state + 8) == pic.clips[-1], 'inventory clip')
                check(e.mem.u32(state + 0x20) == 0, 'inventory time store')
                check(e.mem.u32(state + 0x10) == 0, 'inventory weight store')
                check(e.mem.u16(state + 0x24) == 0x43, 'inventory flags')
                # An empty state forces the blend to zero, so 0.1 and 0 store the same rate.
                check(e.mem.u32(state + 0x14) == ref.BLEND_FORCED, 'inventory blend forced')
                e.mem.w32(state + 0x20, 0x11111111)
                pic.names.clear()
                e.reset_log()
                e.call(0x1c3f08, 0, state, fast, max_steps=20000)
                check(e.mem.u32(state + 0x20) == 0x11111111, 'same clip keeps its frame')
                check(not any(c.target == ANIM_START for c in e.calls), 'no second start')
                count += 1
    # The inventory draw asks for one unit step before the body draw.
    e.r[4] = state
    e.r[21] = state
    e.stub(ANIM_ADVANCE, ret=0, name='anim_advance')
    e.reset_log()
    check(e.run(0x1c0a10, until=(0x1c0a18,), max_steps=40) == 'stop', 'advance call')
    stepped = [c for c in e.calls if c.target == ANIM_ADVANCE]
    check(len(stepped) == 1 and stepped[0].args[0] == state, 'advance state')
    check(stepped[0].fargs[0] == ref.BLEND_FORCED, 'advance speed 1')
    e.unhook(ANIM_ADVANCE)
    # One real step from the installed cell. Length stays above the step.
    clip = e.alloc(0x60)
    e.mem.write(clip, bytes(0x60))
    e.mem.w32(clip + 4, 30)
    for slot in range(4):
        e.mem.w32(clip + 0x14 + slot * 8, 0x447a0000)
    e.mem.write(state, bytes(0x120))
    e.mem.w8(state + 5, 8)
    plant_track(e, state + 8)
    e.call(ANIM_START, state, clip, 0x43, fargs=(0.0,), max_steps=5000)
    before = (e.mem.u32(state + 0x20), e.mem.u32(state + 0x10))
    check(before == (0, 0), 'fresh inventory cell before the step')
    e.call(0x1709d8, state, 0, 0, 0, max_steps=20000)
    after_time, after_weight = e.mem.u32(state + 0x20), e.mem.u32(state + 0x10)
    check(after_time == ref.K_STEP and after_weight == ref.BLEND_FORCED,
          'inventory step stores time 0x3f7fffff and weight 1')
    want_time, want_weight = ref.unit_advance(0x43, before[0], before[1], ref.BLEND_FORCED,
                                               ref.BLEND_FORCED, 30)
    check((after_time, after_weight) == (want_time, want_weight), 'first inventory frame')
    count += 1
    # In play. Time and rate are prefilled and must survive the reset.
    player = pic.objects[0]
    definition = e.alloc(0x68 * 8)
    for word in range(0x68 * 8 // 4):
        e.mem.w32(definition + word * 4, 0x710000 + word)
    e.mem.w32(player + 0x24, definition)
    for weapon in range(8):
        for display in (0, 1):
            e.mem.write(player + 0x114, bytes(0x120))
            e.mem.w32(player + 0x134, 0x22222222)
            e.mem.w32(player + 0x128, 0x33333333)
            e.mem.w8(player + 0x462, display)
            e.mem.w32(record + 0x43d8, player)
            e.mem.wf32(record + 0xac, 1.0)
            e.mem.w8(record + 0x4a86, weapon)
            pic.names.clear()
            pic.clips.clear()
            e.reset_log()
            e.call(0x1b2470, 0, max_steps=20000)
            offsets = ref.play_idle_offsets(weapon)
            if display:
                check([name for _archive, name in pic.names] == [e.mem.cstr(ref.display_idle_address(weapon))],
                      'display idle')
                check(e.mem.u32(player + 0x11c) == pic.clips[0], 'display clip')
            else:
                check(not pic.names, 'table idle does not look up a name')
                check(e.mem.u32(player + 0x11c) == e.mem.u32(definition + offsets[0]), 'play idle')
            for cell, offset in enumerate(offsets[1:], start=1):
                check(e.mem.u32(player + 0x11c + 0x20 * cell) == e.mem.u32(definition + offset),
                      'play upper cell')
            check(e.mem.u8(player + 0x118) == 4, 'four base tracks')
            check(e.mem.u32(player + 0x124) == ref.BLEND_FORCED, 'play weight')
            check(e.mem.u32(player + 0x134) == 0x22222222, 'play time not rewritten')
            check(e.mem.u32(player + 0x128) == 0x33333333, 'play rate not rewritten')
            check(e.mem.u16(player + 0x138) == 0x1205, 'play flags')
            count += 1
    e.mem.w32(player + 0x11c, 0x44444444)
    e.mem.w32(record + 0x43d8, 0)
    e.reset_log()
    e.call(0x1b2470, 0, max_steps=2000)
    check(e.mem.u32(player + 0x11c) == 0x44444444, 'missing player')
    e.mem.w32(record + 0x43d8, player)
    e.mem.wf32(record + 0xac, 0.0)
    e.reset_log()
    e.call(0x1b2470, 0, max_steps=2000)
    check(e.mem.u32(player + 0x11c) == 0x44444444, 'no hit points')
    return count + 2


def mask_and_shell(pic):
    e = pic.e
    count = 0
    obj = pic.objects[0]
    sentinel = 0x0123456789abcdef
    e.mem.w64(obj + 0x220, sentinel)
    e.r[18] = obj
    frame = e.alloc(0x200)
    e.r[29] = frame + 0x180
    e.r[30] = frame
    e.mem.w32(frame + 0x124, 0xabc0)
    e.stub(MODEL_DRAW, ret=0, name='model_draw')
    e.reset_log()
    e.reads = []
    check(e.run(0x10ba84, until=(0x10bab0,), max_steps=40) == 'stop', 'creature load')
    drawn = [c for c in e.calls if c.target == MODEL_DRAW]
    check(len(drawn) == 1 and drawn[0].args[6] == sentinel, 'creature passes the mask')
    check(any(addr == obj + 0x220 for _pc, addr, _size, _value in e.reads), 'mask read')
    count += 1
    # Inventory load, then the call that passes r10 onward.
    e.unhook(MODEL_DRAW)
    local = e.alloc(0x20)
    e.mem.w32(local + 8, obj)
    e.r[16] = local
    e.r[19] = 0
    e.reset_log()
    e.reads = []
    check(e.run(0x1c0a18, until=(0x1c0a4c,), max_steps=20) == 'stop', 'inventory load')
    check(e.r[19] == sentinel, 'inventory holds the mask')
    e.r[19] = sentinel
    e.r[21] = 0x10
    e.r[23] = 0x20
    e.r[5] = 0
    e.r[16] = 0
    e.r[20] = 0
    e.r[30] = 0x4e0000
    e.r[29] = e.STACK_HI - 0x200
    e.mem.w32(0x4d8af0 + 0x43d8, obj)
    e.mem.w32(obj + 0x544, 0x111)
    e.mem.w32(obj + 0x550, 0x222)
    e.stub(MODEL_DRAW, ret=7, name='model_draw')
    e.reset_log()
    check(e.run(0x1c0c20, until=(0x1c0c60,), max_steps=40) == 'stop', 'inventory pass')
    passed = [c for c in e.calls if c.target == MODEL_DRAW][0]
    check(passed.args[6] == sentinel, 'inventory passes the mask')
    check(passed.args[0] == 0x111 and passed.args[1] == 0x222 and passed.args[2] == 6,
          'inventory body arguments')
    count += 1
    e.unhook(MODEL_DRAW)
    # The walk itself. Table 0, several masks, one empty mesh.
    cursor = e.alloc(0x10)
    packet = e.alloc(0x400)
    model = e.alloc(0x80)
    for meshes, mask in ((1, 1), (3, 0b101), (4, ref.U64), (4, 0), (3, 0b010)):
        e.mem.write(model, bytes(0x80))
        e.mem.w8(model + 0x12, meshes)
        e.mem.w8(model + 0x26, 1)
        bounds = []
        at = packet
        for i in range(meshes + 2):
            bounds.append(at)
            e.mem.w32(model + 0x28 + 4 * i, at)
            at += 0 if i == 1 and meshes > 1 else 0x20
        e.mem.w32(cursor, packet)
        e.mem.write(packet, bytes([0xa5]) * 0x200)
        e.r[17] = cursor
        e.r[18] = model
        e.r[21] = mask
        e.r[23] = 0
        e.r[16] = 0x420000
        e.reset_log()
        check(e.run(0x177df4, until=(0x177eb0,), max_steps=5000) == 'stop', 'mask walk')
        got = []
        for pc, addr, size, value in e.writes:
            if pc == 0x177e90 and size == 8:
                got.append(((value >> 32) & 0xffffffff, (value & 0xffff) * 16))
        want = list(ref.mesh_runs(tuple(bounds[:meshes + 1]), mask))
        check(got == want, 'body mesh refs')
        count += 1
    # Shell primitive. Flag clear leaves the prefilled image alone.
    image = e.alloc(0x2000)
    block = e.alloc(0x40)
    cursor = e.alloc(0x10)
    alpha = 0x1122334455667788
    e.mem.w64(model + 0x18, alpha)
    e.mem.w16(model + 0x10, 0)
    e.mem.w32(cursor, image)
    e.mem.write(image, bytes([0xa5]) * 0x400)
    e.call(SHELL, cursor, model, 1, block, 2, max_steps=2000)
    check(e.mem.read(image, 0x40) == bytes([0xa5]) * 0x40, 'flag clear writes nothing')
    count += 1
    records = ((0x04032201, 0x3f466665), (0xff00a5c3, 0x42200000))
    for mode, meshes in ((1, 1), (1, 3), (0, 2), (1, 4)):
        e.mem.write(model, bytes(0x80))
        e.mem.w16(model + 0x10, 0x20)
        e.mem.w8(model + 0x12, meshes)
        e.mem.w8(model + 0x26, 1)
        e.mem.w64(model + 0x18, alpha)
        bounds = []
        at = e.alloc(0x20 * (meshes + 1))
        for i in range(meshes + 1):
            bounds.append(at + i * 0x20)
            e.mem.w32(ref.shell_directory(model) + 4 * i, bounds[-1])
        for i, (rgba, bits) in enumerate(records):
            e.mem.w32(block + i * 8, rgba)
            e.mem.w32(block + i * 8 + 4, bits)
        e.mem.write(image, bytes([0xa5]) * 0x2000)
        e.mem.w32(cursor, image)
        e.mem.w32(cursor + 4, 0xbbbbbbbb)
        e.reset_log()
        e.reads = []
        e.call(SHELL, cursor, model, mode, block, len(records), max_steps=20000)
        final, want = ref.shell_packet(image, model, mode, records, bounds, alpha)
        check(e.mem.u32(cursor) == final, 'shell cursor')
        got = e.mem.read(image, len(want))
        if got != want:
            mismatch = next(i for i, (a, b) in enumerate(zip(got, want)) if a != b)
            lo = max(0, mismatch - 8)
            raise AssertionError('shell +%d got %s want %s' % (
                mismatch, got[lo:lo + 24].hex(), want[lo:lo + 24].hex()))
        check(any(addr == ref.shell_directory(model) for _pc, addr, _s, _v in e.reads),
              'shell reads table 0')
        count += 1
    # Gates: positive count and flag 0x20 enter; either condition misses.
    e.mem.w16(model + 0x10, 0x20)
    e.mem.w32(SHELL_COUNT, 2)
    e.mem.w32(SHELL_LIST, block)
    e.r[17] = cursor
    e.r[18] = model
    e.stub(SHELL, ret=0, name='shell')
    e.reset_log()
    check(e.run(0x177da4, until=(0x177dd8,), max_steps=40) == 'stop', 'model_draw gate')
    check([c.args[:5] for c in e.calls if c.target == SHELL] == [(cursor, model, 1, block, 2)],
          'model_draw shell arguments')
    e.mem.w32(SHELL_COUNT, 0)
    e.reset_log()
    check(e.run(0x177da4, until=(0x177de0,), max_steps=40) == 'stop', 'model_draw count gate')
    check(not any(c.target == SHELL for c in e.calls), 'count 0 skips')
    e.mem.w16(model + 0x10, 0)
    e.mem.w32(SHELL_COUNT, 2)
    e.reset_log()
    check(e.run(0x177da4, until=(0x177de0,), max_steps=20) == 'stop', 'model_draw flag gate')
    check(not any(c.target == SHELL for c in e.calls), 'flag clear skips')
    e.r[16] = model
    e.mem.w16(model + 0x10, 0x20)
    e.mem.w32(SHELL_COUNT, 2)
    e.reset_log()
    check(e.run(0x178c88, until=(0x178cbc,), max_steps=40) == 'stop', 'drawPart gate')
    check(any(c.target == SHELL and c.args[2] == 1 and c.args[3] == block and c.args[4] == 2
              for c in e.calls), 'drawPart shell arguments')
    return count + 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.path.join(_TOOL_DIR, '..', 'local', 'SLUS_209.73'))
    parser.add_argument('--seeds', type=int, nargs='+', default=(20973, 7))
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        check(hashlib.sha256(source.read()).hexdigest() == SHA256, 'wrong executable revision')
    selection_census(args.elf)
    for seed in args.seeds:
        pic = Picture(args.elf, seed)
        created, race = creation(pic)
        posed = inventory_and_play(pic)
        drawn = mask_and_shell(pic)
        print('SLICE creation targets %s' % ' '.join(
            '%x' % target for target in sorted(pic.slice_targets)), flush=True)
        print('PASS seed=%d creation=%d pose=%d draw=%d race=%d literal_pointer_rows=%s '
              'literal_copy_rows=%s' % (
                  seed, created, posed, drawn, race,
                  ','.join(map(str, pic.literal[0])) or '-',
                  ','.join(map(str, pic.literal[1])) or '-'), flush=True)


if __name__ == '__main__':
    main()
