#!/usr/bin/env python3
"""The created-character preview over whole frames, its body mask, and the VU1 joint and
attachment matrices. Counts only; nothing read from the disc is printed.

Run from the worktree root with PYTHONDONTWRITEBYTECODE=1. unittest is imported before
tools/ is on sys.path (tools/dis.py shadows the standard library module).

  python3 tools/difftest_char_frame.py local/SLUS_209.73 --data local/char-frame \
      --seeds 20973 7

--data names a private folder with the disc files INTRO.GOB, SELECT.LMP and SELECT2.LMP.
Only the class name and property text of the intro level's NPC records, and the entry
names of the two select archives, are read from them.

Executed (original instructions in tools/ee_emu.py):
* set-up: handle_initPool 0x1a17d0, pool_init 0x14fcd8, anim_init 0x16f9a8 and
  world_init 0x14c370, which registers runObjects and drawObjects.
* NPC_ctor 0x29df04 once per NPC record of the intro level, with the record's property
  text. world_findObjectByName then finds those objects for real.
* playerSel_initCache 0x2243f8 and playerSel_start 0x2245b8 (argument 0).
* frames: the run pass tasks_call(1, -1) and the draw pass tasks_call(0, 1) through
  0x19e798, in the main loop's order. Every call is recorded, linking jumps and jalr
  alike. Arrival hooks sit on the six entry points that write a track time.
* one transition slice 0x226dec-0x226e44 between a draw pass and the next run pass,
  in place of the controller branch that enters it (that branch is not executed).
* NPC_draw 0x29e3ec reached from world_drawObjects 0x14b168, including 0x224d80 (the
  preview body mask) and Creature_draw 0x10b048 up to model_draw.
* the VU1 part: model_emitDrawSetup 0x175670, the pose branch of model_draw
  0x177d4c-0x177da4 (anim_emitPose 0x16f880, MSCAL 0x0c), and model_emitPartSetup
  0x175fb8 build the packet. tools/vu1_emu.py runs the game's own VU1 microcode, loaded
  from the packet at 0x3e5ec0, over that packet.

Disclosed stubs (every call is still recorded):
  lump_load 0x173558 (a zeroed block), cd_readBlocking 0x172ad0 (returns 1),
  dbg_printf 0x355490, the tagged heap 0x14ff88 (test heap; requests above 64 KiB share
  one block, because the stubbed CD reads never fill them), res_find 0x17365c (non-null
  exactly when the entry is in the named select archive; .anm entries get a synthetic
  clip header whose length comes from the seed), model_draw 0x1779b0 and
  model_drawPart 0x178c28 in the frame part (the renderer), anim_buildPose 0x16ed40 in
  the frame part (VU0; executed by tools/difftest_anim.py), and the renderer queue
  0x16b7f0. Planted state is named where it is planted: the carousel row byte, the
  camera position and matrix that make that row visible, the hair, beard and
  preview-item hide qwords, the VU1 part's view-projection at 0x44f1c0, and the
  pose buffer. The selection camera and the camera task do not run, so the camera
  focus stays at the origin and only the previews near it are active.
"""
import os
import sys

_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or os.curdir) != _TOOL_DIR]
import unittest  # noqa: E402,F401
import argparse
import hashlib
import random
import struct

sys.path.insert(0, _TOOL_DIR)
from ee_emu import EE, EmuError
import gob
import ref_char_attachment as ref
import vu1_emu

SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
TASKS_CALL = 0x19e798
NPC_CTOR = 0x29df04
NPC_RUN = 0x29ea40
NPC_DRAW = 0x29e3ec
NPC_VTABLE = 0x50f590
CREATURE_STEP = 0x1162b0
CREATURE_DRAW = 0x10b048
RUN_OBJECTS = 0x14b910
DRAW_OBJECTS = 0x14b168
SEL_TASK = 0x225478
SEL_CACHE = 0x2243f8
SEL_START = 0x2245b8
PREVIEW_MASK = 0x224d80
ANIM_START = 0x16cfe0
ANIM_ADVANCE = 0x16d748
ANIM_BUILD = 0x16ed40
ANIM_EMIT = 0x16f880
RES_FIND = 0x17365c
MODEL_DRAW = 0x1779b0
DRAW_PART = 0x178c28
PART_SETUP = 0x175fb8
DRAW_SETUP = 0x175670
QUEUE = 0x16b7f0
SCRATCH_PTR = 0x4fdb7c
DESCRIPTOR = 0x4fbbf8
STRIDE = 0x26c
VU1_PACKET = 0x3e5ec0
RESTART_LO, RESTART_HI = 0x2254bc, 0x2255b4
TIME_WRITERS = {
    0x16d748: 'anim_advance', 0x1709d8: 'anim_advanceUnitSpeed',
    0x1709f8: 'anim_syncToSimFrame', 0x16d0b8: 'anim_randomizeTopTime',
    0x170bc8: 'anim_jumpTopToEnd', 0x170c80: 'anim_snapTopToEnd',
}
SET_UP = (0x1a17d0, 0x14fcd8, 0x16f9a8, 0x14c370)
ALL_TASKS = 0xFFFFFFFFFFFFFFFF


def check(value, message):
    if not value:
        raise AssertionError(message)


def _ob_records(blob):
    """(class name, [property text], (x, y, height) bits, facing) per objects.ob record."""
    count, _flags, strings = struct.unpack_from('<hHi', blob, 0)
    at, out = 8, []

    def text(offset):
        start = strings + offset
        return blob[start:blob.index(b'\0', start)].decode('latin1')
    for _ in range(count):
        cls, size, angle = struct.unpack_from('<ihh', blob, at)
        place = struct.unpack_from('<3I', blob, at + 8)
        props, cursor = [], at + 20
        while True:
            value, = struct.unpack_from('<i', blob, cursor)
            cursor += 4
            if value == 0:
                break
            props.append(text(value))
        out.append((text(cls), props, place, angle))
        at += size
    return out


def load_private(folder):
    with open(os.path.join(folder, 'INTRO.GOB'), 'rb') as source:
        archive = source.read()
    npcs = []
    for _name, offset, size in gob.gob_entries(archive):
        lump = archive[offset:offset + size]
        for entry, start, length in gob.lmp_entries(lump):
            if entry == 'objects.ob':
                npcs.extend(r for r in _ob_records(lump[start:start + length]) if r[0] == 'NPC')
    members = {}
    for lump, filename in (('select.lmp', 'SELECT.LMP'), ('select2.lmp', 'SELECT2.LMP')):
        with open(os.path.join(folder, filename), 'rb') as source:
            members[lump] = {name.lower() for name, _o, _s in gob.lmp_entries(source.read())}
    return npcs, members


def jalr_site(e, site):
    word = e.mem.u32(site)
    return word >> 26 == 0 and (word & 0x3F) == 9


class Rig:
    """One machine: set-up, thirteen preview NPCs, the selection screen."""

    def __init__(self, elf, seed, npcs, members):
        self.e = e = EE(elf)
        self.rng = random.Random(seed)
        self.clip_length = self.rng.randint(5, 30)
        self.members = members
        self.arrivals = []
        self.pass_name = 'set-up'
        self.big = None
        self.heap_sizes = []
        self.find_names = {}
        e.mem.w32(0x404464, seed)
        e.stub(0x173558, function=lambda emu: emu.alloc(0x100), name='lump_load')
        e.stub(0x172ad0, ret=1, name='cd_readBlocking')
        e.stub(0x355490, ret=0, name='dbg_printf')
        e.stub(0x14ff88, function=self._heap, name='heap')
        e.stub(RES_FIND, function=self._find, name='res_find')
        e.stub(MODEL_DRAW, ret=0, name='model_draw')
        e.stub(DRAW_PART, ret=0, name='model_drawPart')
        e.stub(ANIM_BUILD, ret=0, name='anim_buildPose')
        e.stub(QUEUE, ret=0, name='queue')
        for address, label in TIME_WRITERS.items():
            e.hook(address, self._arrive(address, label))
        for function in SET_UP:
            self.call(function)
        self.objects = []
        self.names = []
        for _cls, props, place, angle in npcs:
            self.objects.append(self.construct(props, place, angle))
        check(len(self.objects) == 13, 'thirteen NPC records')
        self.ctor_writers = sorted({a[1] for a in self.arrivals})
        self.arrivals = []

    # -- stubs -----------------------------------------------------------------
    def _heap(self, e):
        size = e.r[4] & 0xFFFFFFFF
        self.heap_sizes.append(size)
        if size > 0x10000:
            if self.big is None:
                self.big = e.alloc(0x2a0000)
            return self.big
        return e.alloc(size + 16)

    def _find(self, e):
        lump = e.mem.cstr(e.r[4]).lower()
        entry = e.mem.cstr(e.r[5]).lower()
        if e._fresh_call is not None:
            self.find_names[id(e._fresh_call)] = e.mem.cstr(e.r[5])
        if lump in self.members and entry not in self.members[lump]:
            return 0
        block = e.alloc(0x80)
        if entry.endswith('.anm'):
            e.mem.w32(block + 4, self.clip_length)
        return block

    def _arrive(self, address, label):
        def hook(e):
            self.arrivals.append((self.pass_name, label, (e.r[31] - 8) & 0xFFFFFFFF,
                                  e.r[4] & 0xFFFFFFFF))
        return hook

    # -- helpers ---------------------------------------------------------------
    def call(self, function, *args, steps=60000000):
        e = self.e
        e.reset_log()
        e.r[29] = e.STACK_HI - 0x1000
        e.call(function, *args, max_steps=steps)
        return e.calls

    def construct(self, props, place, angle):
        e = self.e
        table = e.alloc(4 * (len(props) + 1))
        for index, text in enumerate(props):
            at = e.alloc(len(text) + 1)
            e.mem.write(at, text.encode('latin1') + b'\0')
            e.mem.w32(table + 4 * index, at)
        position = e.alloc(16)
        for index, bits in enumerate(place):
            e.mem.w32(position + 4 * index, bits)
        obj = e.alloc(0x480)
        self.call(NPC_CTOR, obj, position, angle & 0xFFFF, table, steps=5000000)
        check(e.mem.u32(obj + 0x48) == NPC_VTABLE, 'NPC vtable')
        return obj

    def prop(self, obj, key):
        e = self.e
        table = e.mem.u32(obj + 0x2c)
        index = 0
        while table and e.mem.u32(table + 4 * index):
            text = e.mem.cstr(e.mem.u32(table + 4 * index))
            if text.lower().startswith(key + '='):
                return text[len(key) + 1:]
            index += 1
        return None

    def cells(self, obj):
        e = self.e
        count = e.mem.u8(obj + 0x118)
        return [(e.mem.u32(obj + 0x11c + 0x20 * i), e.mem.u32(obj + 0x134 + 0x20 * i),
                 e.mem.u16(obj + 0x138 + 0x20 * i)) for i in range(count)]

    def run_pass(self):
        self.pass_name = 'run'
        return list(self.call(TASKS_CALL, 1, ALL_TASKS))

    def draw_pass(self):
        self.pass_name = 'draw'
        return list(self.call(TASKS_CALL, 0, 1))


TASK_SITES = (0x19e798, 0x19e858)


def task_segments(e, calls):
    """Split a pass's flat call list at the calls tasks_call makes itself."""
    out, current = [], None
    for call in calls:
        if TASK_SITES[0] <= call.site < TASK_SITES[1]:
            current = (call.target, [])
            out.append(current)
        elif current is not None:
            current[1].append(call)
    return out


def frames(rig):
    """Whole frames: run pass, then draw pass. Returns counters for the log."""
    e = rig.e
    out = {'frames': 0, 'calls': 0, 'jalr': 0, 'targets': set(), 'npc_run': 0,
           'advance': 0, 'task_calls': 0, 'task_jalr': 0, 'task_targets': set(),
           'active': 0}
    by_state = {obj + 0x114: obj for obj in rig.objects}
    out['ctor_writers'] = rig.ctor_writers
    rig.call(SEL_CACHE)
    out['cache_calls'] = len(e.calls)
    check(not rig.arrivals, 'playerSel_initCache writes no track time')
    rig.call(SEL_START, 0)
    check(not rig.arrivals, 'playerSel_start writes no track time')
    active = [o for o in rig.objects if e.mem.u64(o + 0xa8) >> 63]
    watched = None
    times = []
    for _frame in range(rig.rng.randint(3, 5)):
        rig.arrivals = []
        calls = rig.run_pass()
        targets = [c.target for c in calls]
        check(RUN_OBJECTS in targets, 'run pass reaches runObjects')
        npc_runs = [c for c in calls if c.target == NPC_RUN]
        check(npc_runs and all(jalr_site(e, c.site) and 0x14bb44 <= c.site <= 0x14bcc0
                               for c in npc_runs),
              'NPC_run is reached through jalr from the runObjects walk')
        steps = [a for a in rig.arrivals if a[1] == 'anim_advance']
        active = {o + 0x114 for o in rig.objects if e.mem.u64(o + 0xa8) >> 63}
        ran = {c.args[0] + 0x114 for c in npc_runs}
        check(sorted(a[3] for a in steps) == sorted(active & ran), 'active previews advance')
        check(all(a[2] == 0x1163a4 for a in steps), 'advance from Creature_stepAnim')
        check(len(steps) == len(rig.arrivals), 'only anim_advance writes time in the run pass')
        if watched is None:
            watched = by_state[sorted(active & ran)[0]]
            times.append(None)
        times.append(rig.cells(watched)[0][1])
        out['active'] = len(active)
        out['npc_run'] += len(npc_runs)
        out['advance'] += len(steps)
        out['calls'] += len(calls)
        out['jalr'] += sum(jalr_site(e, c.site) for c in calls)
        out['targets'].update(targets)
        rig.arrivals = []
        calls = rig.draw_pass()
        segments = task_segments(e, calls)
        order = [target for target, _calls in segments]
        check(SEL_TASK in order and DRAW_OBJECTS in order, 'draw pass tasks')
        check(order.index(SEL_TASK) < order.index(DRAW_OBJECTS), 'priority 9 before 21')
        check(not rig.arrivals, 'no time writer in the draw pass')
        check(rig.cells(watched)[0][1] == times[-1], 'the draw pass keeps the time')
        for target, inner in segments:
            if target == SEL_TASK:
                out['task_calls'] += len(inner)
                out['task_jalr'] += sum(jalr_site(e, c.site) for c in inner)
                out['task_targets'].update(c.target for c in inner)
        out['calls'] += len(calls)
        out['jalr'] += sum(jalr_site(e, c.site) for c in calls)
        out['targets'].update(c.target for c in calls)
        out['frames'] += 1
    check(not out['task_targets'] & set(TIME_WRITERS), 'playerSel_task reaches no time writer')
    # Each run pass is one unit step of the standing loop (flags 3: no fixed step, speed 1).
    want = times[1]
    for got in times[2:]:
        want, _weight = ref.unit_advance(3, want, 0, 0, ref.BLEND_FORCED, rig.clip_length)
        if ref.f32(want) >= rig.clip_length:
            break
        check(got == want, 'standing loop steps once per run pass')
    out['active_rows'] = [i for i in range(13) if e.mem.u64(
        e.mem.u32(e.mem.u32(SCRATCH_PTR) + 0x1558 + 4 * i) + 0xa8) >> 63]
    return out


def transition(rig, row):
    """The intro4 slice for one row, then frames until playerSel_task restarts the row."""
    e = rig.e
    scratch = e.mem.u32(SCRATCH_PTR)
    obj = e.mem.u32(scratch + 0x1558 + 4 * row)
    check(obj in rig.objects, 'row object is a constructed NPC')
    rig.pass_name = 'slice'
    e.reset_log()
    e.r[29] = e.STACK_HI - 0x2000
    e.r[2] = row * STRIDE
    e.r[17] = row * 4
    e.r[19] = row
    check(e.run(0x226dd8, until=(0x226e44,), max_steps=200000) == 'stop', 'intro4 slice')
    starts = [c for c in e.calls if c.target == ANIM_START]
    check(len(starts) == 1 and starts[0].args[0] == obj + 0x114 and starts[0].args[2] == 6,
          'intro4 starts flags 6 on the row object')
    cells = rig.cells(obj)
    check(cells[-1][1] == 0 and cells[-1][2] == 6, 'intro installed at time 0')
    intro_index = len(cells) - 1
    cell = obj + 0x11c + 0x20 * intro_index
    weight, rate, life = e.mem.u32(cell + 8), e.mem.u32(cell + 0xc), e.mem.u32(cell + 0x10)
    check(weight == 0 and life == ref.BLEND_FORCED, 'intro weight 0, life 1')
    # Unit steps (flags 6: no fixed step, speed 1) until the time reaches the clip length
    # (REPORT_END) and until min(weight, life) reaches 1 (PURGE_BELOW removes the loop).
    time, end_pass, purge_pass, n = 0, None, None, 0
    while end_pass is None or purge_pass is None:
        n += 1
        time, weight = ref.unit_advance(6, time, weight, rate, ref.BLEND_FORCED, rig.clip_length)
        if end_pass is None and ref.f32(time) >= rig.clip_length:
            end_pass = n
            time = ref.f32_bits(float(rig.clip_length))
        if purge_pass is None and min(ref.f32(weight), ref.f32(life)) >= 1.0:
            purge_pass = n
        check(n < 400, 'intro step prediction')
    want_restart = max(end_pass, purge_pass)
    seen_end, restarted, history = None, None, []
    for frame in range(want_restart + 2):
        rig.arrivals = []
        rig.run_pass()
        status = e.mem.u16(obj + 0x11a)
        history.append((rig.cells(obj), status))
        if seen_end is None and status & 0x80:
            seen_end = frame + 1
        rig.arrivals = []
        calls = rig.draw_pass()
        for target, inner in task_segments(e, calls):
            if target != SEL_TASK:
                continue
            got = [c for c in inner if c.target == ANIM_START and RESTART_LO <= c.site < RESTART_HI]
            if got and restarted is None:
                check(all(c.args[0] == obj + 0x114 for c in got), 'restart only on the row')
                restarted = (frame + 1, got[0])
                index = inner.index(got[0])
                finds = [c for c in inner[:index] if c.target == RES_FIND]
                restarted += (rig.find_names.get(id(finds[-1])) if finds else None,)
        if restarted:
            break
    check(seen_end == end_pass, 'intro ends on the predicted run pass')
    check(len(history[want_restart - 1][0]) == 1, 'the purge leaves one track')
    check(restarted and restarted[0] == want_restart, 'restart in the draw pass of that frame')
    after = rig.cells(obj)
    check(after[-1][1] == 0 and after[-1][2] == 3, 'restart installs the standing loop at time 0')
    marked = bool(history[want_restart - 1][1] & 0x08)
    token = e.mem.cstr(e.mem.u32(DESCRIPTOR + row * STRIDE))
    form = e.mem.cstr(ref.INTRO_STANDING_MARKED if marked else ref.INTRO_STANDING)
    want_name = ref.creation_clip_name(token.encode('latin1'), form.encode('latin1'))
    check(restarted[2] == want_name.decode('latin1'), 'restart clip name')
    return {'row': row, 'end': end_pass, 'purge': purge_pass, 'restart': restarted[0],
            'rate': rate, 'status': history[want_restart - 1][1]}


def plant_view(rig, obj):
    """Camera 200 units behind the object on x, looking along +x. Not the selection camera."""
    e = rig.e
    pos = [e.mem.u32(obj + 0x10 + 4 * i) for i in range(3)]
    x = ref.f32(pos[0]) - 200.0
    e.mem.w32(0x44f038, ref.f32_bits(x))
    e.mem.w32(0x44f03c, pos[1])
    e.mem.w32(0x44f040, pos[2])
    matrix = [0.0] * 12
    matrix[2] = 1.0      # forward (column 2): +x
    matrix[3] = 1.0      # side (column 0): +y
    for i, value in enumerate(matrix):
        e.mem.w32(0x44f110 + 4 * i, ref.f32_bits(value))


def draw_mask(rig, row):
    """NPC_draw on the visible row: the preview mask is written, then the body consumes it."""
    e = rig.e
    rng = rig.rng
    scratch = e.mem.u32(SCRATCH_PTR)
    obj = e.mem.u32(scratch + 0x1558 + 4 * row)
    # While the ramp at 0x8e2c44 is strictly between 0 and 1, 0x2248f4 shows only the
    # current carousel row. The row byte is planted here, as the controller code would.
    ramp = ref.f32(e.mem.u32(0x8e2c44))
    slot = e.mem.s8(0x8e2c01)
    e.mem.w8(0x4fdb80 + slot * 0x2c + 0x20, row)
    plant_view(rig, obj)
    # Hair and beard choices and their hide qwords (planted descriptor pointers).
    hair, beard = rng.randrange(4), rng.choice((-1, 0, 1, 2))
    e.mem.w8(0x8e2bc0 + row, hair & 0xff)
    e.mem.w8(0x8e2be0 + row, beard & 0xff)
    hides = {}
    descriptor = DESCRIPTOR + row * STRIDE
    for name, base, index in (('hair', 0x1c, hair), ('beard', 0x3c, beard)):
        for slot in range(8):
            e.mem.w32(descriptor + base + 4 * slot, 0)
        if index >= 0:
            qword = e.alloc(8)
            value = rng.getrandbits(64) & rng.getrandbits(64)
            e.mem.w64(qword, value)
            e.mem.w32(descriptor + base + 4 * index, qword)
            hides[name] = value
    # One equipment-preview group for this row: items with the loaded flag get both handles.
    group = rng.randrange(5)
    for other in range(5):
        if e.mem.s8(scratch + 0xfa0 + 8 * other) == row:
            e.mem.w8(scratch + 0xfa0 + 8 * other, 0xff)
    e.mem.w8(scratch + 0xfa0 + 8 * group, row)
    items = []
    for k in range(8):
        record = scratch + group * 0x320 + k * 0x64
        loaded = rng.random() < 0.6
        e.mem.w32(record + 0x60, int(loaded))
        if loaded:
            qword = e.alloc(8)
            value = rng.getrandbits(64) & rng.getrandbits(64) & rng.getrandbits(64)
            e.mem.w64(qword, value)
            e.mem.w32(record, qword)
            e.mem.w32(record + 4, e.alloc(0x10))
            items.append(value)
        else:
            e.mem.w32(record, 0)
            e.mem.w32(record + 4, 0)
    want = ref.preview_body_mask(hides.get('hair'), hides.get('beard'), items)
    seen = []
    e.stub(MODEL_DRAW, function=lambda emu: seen.append(
        (emu.r[4] & 0xFFFFFFFF, emu.r[5] & 0xFFFFFFFF, emu.r[6] & 0xFFFFFFFF, emu.r[10])) or 0,
        name='model_draw')
    rig.arrivals = []
    rig.draw_pass()
    calls = e.calls
    draws = [i for i, c in enumerate(calls) if c.target == NPC_DRAW and c.args[0] == obj]
    check(len(draws) == 1, 'the row object is drawn once')
    masks = [w for w in e.writes if w[1] == obj + 0x220]
    check(masks and masks[-1][0] == 0x29e800 and masks[-1][3] == want, 'preview mask store')
    bodies = [c for c in calls[draws[0]:] if c.target == CREATURE_DRAW]
    check(bodies and bodies[0].args[:4] == (obj, e.mem.u32(obj + 0x428), e.mem.u32(obj + 0x42c), 0),
          'Creature_draw gets the preview handles')
    check(seen and seen[0][3] == want, 'model_draw receives the same-frame mask')
    order = [w[0] for w in e.writes if w[1] == obj + 0x220]
    others = [c.args[0] for c in calls if c.target == CREATURE_DRAW]
    check(others == [obj] or not 0.0 < ramp < 1.0, 'only the current row is drawn mid-ramp')
    return {'row': row, 'hair': hair, 'beard': beard, 'items': len(items), 'ramp': ramp,
            'stores': ' '.join('%x' % pc for pc in order)}

POSE_POOL = 0x791ec0
VIEW_PROJ = 0x44f1c0
PACKET_CURSOR = 0x44fe10
DRAW_FLAGS = 0x41c168
M32 = 0xFFFFFFFF


def _model(e, at, count, attach_header, payload):
    """A relocated synthetic model: one mesh table of zero qwords (VIF NOPs)."""
    e.mem.w16(at + 0x10, 0)
    e.mem.w8(at + 0x12, count)
    e.mem.w8(at + 0x13, attach_header)
    e.mem.w8(at + 0x26, 1)
    bounds = [payload + 0x10 * i for i in range(count + 1)]
    for i, value in enumerate(bounds):
        e.mem.w32(at + 0x28 + 4 * i, value)
    return bounds


def vu_matrices(elf, seed):
    """The body pose and one attached part through the game's VU1 microcode."""
    rng = random.Random(seed * 31 + 5)
    e = EE(elf)
    e.mem.w32(0x404464, seed)
    queued = []
    e.stub(QUEUE, function=lambda emu: queued.append(emu.r[4] & M32) or 0, name='queue')
    e.stub(ANIM_BUILD, ret=0, name='anim_buildPose')
    for function in (0x16f9a8,):
        e.r[29] = e.STACK_HI - 0x1000
        e.call(function, max_steps=20000000)
    dl = e.alloc(0x40000)
    e.mem.w32(PACKET_CURSOR, dl)
    payload = e.alloc(0x400)
    body = e.alloc(0x800)
    _model(e, body, 2, 0x40, payload)
    e.mem.w8(body + 0x22, 0x40)
    texture = e.alloc(0x40)
    # The attach table at body + 16 * 0x40: joint word, then 12 floats.
    joints = rng.randint(3, 40)
    index = rng.randrange(16)
    joint = rng.randrange(joints)
    values = [ref.f32_bits(rng.uniform(-2.0, 2.0)) for _ in range(12)]
    record = body + 0x400 + 0x34 * index
    e.mem.w32(record, joint)
    for i, bits in enumerate(values):
        e.mem.w32(record + 4 + 4 * i, bits)
    # A pooled pose buffer attached to the state, so anim_emitPose does not build.
    state = e.alloc(0x120)
    buf = POSE_POOL + 0x620 * rng.randrange(100)
    e.mem.w32(state, buf)
    e.mem.w32(buf + 0x610, state)
    e.mem.w32(buf, 0)
    e.mem.w32(buf + 4, (((joints * 3 + 1) << 16) | 0x6D008000) & M32)
    e.mem.w16(buf + 8, joints)
    rows = []
    for j in range(joints):
        joint_rows = []
        for k in range(3):
            row = [rng.randint(-4096, 4096) for _ in range(3)] + [rng.randint(-20000, 20000)]
            for c, value in enumerate(row):
                e.mem.w16(buf + 0x10 + 0x18 * j + 8 * k + 2 * c, value & 0xffff)
            joint_rows.append(row)
        rows.append(joint_rows)
    matrix = e.alloc(0x40)
    for i in range(12):
        e.mem.w32(matrix + 4 * i, ref.f32_bits(rng.uniform(-3.0, 3.0)))
    # Planted view-projection (model_draw reads it at 0x177a14); a fresh machine has zeros.
    for i in range(16):
        e.mem.w32(VIEW_PROJ + 4 * i, ref.f32_bits(rng.uniform(-2.0, 2.0)))
    pos = e.alloc(0x10)
    e.r[29] = e.STACK_HI - 0x1000
    e.reset_log()
    e.call(MODEL_DRAW, body, texture, 1, pos, matrix, state, ref.U64, 0, max_steps=2000000)
    body_calls = [c.target for c in e.calls]
    check(ANIM_EMIT in body_calls, 'model_draw emits the pose')
    check(len(queued) == 1, 'one body packet')
    part = e.alloc(0x800)
    _model(e, part, 1, index, payload)
    mirrored = rng.random() < 0.5
    e.mem.w32(DRAW_FLAGS, 0x80 if mirrored else 0)
    context = e.alloc(0x80)
    e.reset_log()
    e.call(DRAW_PART, part, texture, 1, body, context, ref.U64, -1, 0, max_steps=200000)
    e.mem.w32(DRAW_FLAGS, 0)
    check(len(queued) == 2, 'one part packet')
    vu = vu1_emu.Vu1()
    vif = vu1_emu.Vif1(vu, kick=lambda _vu, _q: None, direct=lambda _w: None)

    def read(address, count):
        return e.mem.read(address, count)
    vif.feed(vu1_emu.dma_chain_words(read, VU1_PACKET))
    vif.feed(vu1_emu.dma_chain_words(read, queued[0]))
    vif.run_waiting()
    transform = [list(vu.vf[r]) for r in (1, 2, 3, 4)]
    words = vu1_emu.dma_chain_words(read, queued[0])
    upload = [i for i, w in enumerate(words) if w == 0x6c04c000]
    check(len(upload) == 1, 'one V4-32 x4 transform upload')
    sent = words[upload[0] + 1:upload[0] + 17]
    check(transform == [sent[4 * r:4 * r + 4] for r in range(4)], 'entry 0x02 loads the upload')
    check(any(x & 0x7fffffff for row in transform for x in row), 'nonzero transform')
    got_joints = [[list(vu.qword(4 * j + r)) for r in range(4)] for j in range(joints)]
    want_joints = [ref.vu_joint(ref.pose_qwords(rows[j]), transform) for j in range(joints)]
    check(got_joints == want_joints, 'joint matrices = pose x transform')
    check(vu.qword(0x3ff)[2] == joints, 'joint count at 0x3ff.z')
    vif.feed(vu1_emu.dma_chain_words(read, queued[1]))
    vif.run_waiting()
    slot = [list(vu.qword(r)) for r in range(4)]
    want_slot = ref.vu_attach(got_joints[joint], ref.attach_qwords(values, mirrored))
    check(slot == want_slot, 'slot 0 = attach x joint')
    check(any(x & 0x7fffffff for row in slot for x in row), 'nonzero slot 0')
    check(any(x & 0x7fffffff for row in got_joints[joint] for x in row), 'nonzero joint')
    return {'joints': joints, 'joint': joint, 'index': index, 'mirrored': int(mirrored),
            'body_calls': len(body_calls)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='?', default=os.path.join(_TOOL_DIR, '..', 'local', 'SLUS_209.73'))
    parser.add_argument('--data', default=os.path.join(_TOOL_DIR, '..', 'local', 'char-frame'))
    parser.add_argument('--seeds', type=int, nargs='+', default=(20973, 7))
    args = parser.parse_args()
    with open(args.elf, 'rb') as source:
        check(hashlib.sha256(source.read()).hexdigest() == SHA256, 'wrong executable revision')
    npcs, members = load_private(args.data)
    for seed in args.seeds:
        rig = Rig(args.elf, seed, npcs, members)
        got = frames(rig)
        print('FRAMES seed=%d frames=%d calls=%d jalr=%d targets=%d npc_run=%d advance=%d '
              'active=%d active_rows=%s ctor_writers=%s cache_calls=%d' % (
                  seed, got['frames'], got['calls'], got['jalr'], len(got['targets']),
                  got['npc_run'], got['advance'], got['active'],
                  ','.join(map(str, got['active_rows'])),
                  ','.join(got['ctor_writers']) or '-', got['cache_calls']), flush=True)
        print('TASK seed=%d calls=%d jalr=%d targets=%d writers=%s' % (
            seed, got['task_calls'], got['task_jalr'], len(got['task_targets']),
            ','.join(sorted(TIME_WRITERS[t] for t in got['task_targets'] & set(TIME_WRITERS)))
            or '-'), flush=True)
        rows = [r for r in got['active_rows'] if r >= 1]
        check(rows, 'an active nonzero row')
        row = rig.rng.choice(rows)
        chain = transition(rig, row)
        print('CHAIN seed=%d row=%d length=%d rate=0x%08x end_pass=%d purge_pass=%d '
              'restart_frame=%d status=0x%x' % (
                  seed, row, rig.clip_length, chain['rate'], chain['end'], chain['purge'],
                  chain['restart'], chain['status']), flush=True)
        drawn = draw_mask(rig, rig.rng.randrange(1, 13))
        print('MASK seed=%d row=%d hair=%d beard=%d items=%d ramp=%s stores=%s' % (
            seed, drawn['row'], drawn['hair'], drawn['beard'], drawn['items'],
            repr(drawn['ramp']), drawn['stores']), flush=True)
        vu = vu_matrices(args.elf, seed)
        print('VU1 seed=%d joints=%d lanes=%d attach_index=%d joint=%d mirrored=%d' % (
            seed, vu['joints'], 16 * vu['joints'] + 16, vu['index'], vu['joint'],
            vu['mirrored']), flush=True)
        print('PASS seed=%d' % seed, flush=True)


if __name__ == '__main__':
    main()
