#!/usr/bin/env python3
"""Execute the save/load screen's confirm, overwrite, and restore handoff.

Usage: python3 tools/difftest_save_screen_flow.py path/to/SLUS_209.73

The original screen and save_load run in tools/ee_emu.py. Card-queue, draw,
and world-writer callees are stubbed and recorded. No card image is written.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from ee_emu import EE, EmuError  # noqa: E402
import ref_save_screen as R  # noqa: E402

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SAVE = 0x218AFC
LOAD = 0x219360
SLOT = 0x21C3A4
SAVE_BUILD = 0x221914
SAVE_LOAD = 0x221D60
SAVE_RELOAD = 0x22266C
STORE_LEVEL = 0x21777C
PACK = 0x2223D4
WORLD_LOAD = 0x14E808
LEVEL_OBJECTS = 0x217978
QUEUE = 0x223470
PUMP = 0x2233E4
MAKE_NAME = 0x21EFFC
REQUEST_SAVE = 0x2175B4
REQUEST_LOAD = 0x2176E0


def s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


class Harness:
    def __init__(self, path, seed):
        self.e = EE(path)
        self.e.mem.auto_map = True
        self.e.record_calls = True
        self.e.mem.w32(0x404460, seed)
        self.ops = []
        self.stored = []
        self.e.stub(QUEUE, function=self._queue, name="mc_queueOp")
        self.e.stub(PUMP, ret=0, name="mc_pump")
        for addr, name in (
            (0x21E650, "memcard_spin"),
            (0x21E65C, "memcard_spin2"),
            (0x21E5C8, "memcard_closeFile"),
            (0x21E8B4, "memcard_popPause"),
            (0x21E850, "memcard_pushPause"),
            (0x21F260, "memcard_backupEntry"),
            (0x21F2F8, "memcard_restoreEntry"),
            (0x1DF248, "hud_drawMessageBox"),
            (0x19EA78, "text_format"),
            (0x22FBC0, "dialog_isOpen"),
            (0x1DE0DC, "hud_message"),
            (0x13E150, "net_menu"),
            (0x203918, "Camera_saveState"),
            (0x27DCF4, "jumpgate_saveDestinations"),
            (0x216C80, "save_snapshotPlayer"),
            (0x1ED974, "vars_walk"),
            (0x203A20, "Camera_loadState"),
            (0x27DD30, "jumpgate_loadDestinations"),
            (0x216EA8, "save_fixupPlayer"),
            (0x1EDA08, "script_clearDeferred"),
            (0x1ED728, "vars_clearAll"),
            (0x1ED854, "vars_set"),
            (0x2180A8, "save_setAct"),
            (0x1C4FA8, "inventory_shareQuestItems"),
            (0x22226C, "memcard_portLabel"),
            (0x351E78, "late_helper"),
            (0x173FD4, "text_finish"),
            (0x17FF48, "heap_release"),
            (0x17FF18, "present_hook"),
            (0x1DF5D0, "fade_clear"),
            (0x1E2168, "frontend_side"),
            (0x322934, "task_note"),
            (0x322954, "task_note2"),
            (0x17E4C8, "heap_alloc"),
        ):
            self.e.stub(addr, ret=0, name=name)
        self.e.stub(0x203918, ret=0xC4, name="Camera_saveState")
        self.e.stub(0x203A20, ret=0xC4, name="Camera_loadState")
        self.e.stub(0x27DCF4, ret=0x1E4, name="jumpgate_saveDestinations")
        self.e.stub(0x27DD30, ret=0x1E4, name="jumpgate_loadDestinations")
        self.e.stub(STORE_LEVEL, function=self._store, name="save_storeLevelState")

    def _queue(self, emu):
        self.ops.append(tuple(emu.r[i] & 0xFFFFFFFF for i in (4, 5, 6, 7)))
        return 0

    def _store(self, emu):
        self.stored.append(emu.mem.cstr(emu.r[4] & 0xFFFFFFFF))
        return 0

    def call(self, entry, *args, steps=2000000):
        self.e.reset_log()
        try:
            return self.e.call(entry, *args, max_steps=steps)
        except EmuError as exc:
            raise AssertionError("0x%08x: %s" % (entry, exc)) from exc

    def targets(self):
        return {c.target for c in self.e.calls}

    def keys(self):
        return tuple(self.e.mem.cstr(c.args[0] & 0xFFFFFFFF)
                     for c in self.e.calls if c.target == 0x173C84)


def prepare_screen(h, *, stage=1, sub=0, mode=3):
    m = h.e.mem
    m.w32(0x88D3E4, 1)          # browser already finished
    m.w32(0x88D3D8, stage)      # 0 asks the slot list, 1 is the screen machine
    m.w32(0x88D3A8, sub)
    m.w32(0x88D3A0, mode)
    m.w32(0x88D3BC, 0)          # no card error
    m.w32(0x8E11F8, 0x40)
    m.w32(0x8E11FC, 0)
    m.w8(0x402791, 0)
    m.w8(0x44FCD0, 0)
    m.w8(0x8E1AD8, 0)
    m.w32(0x4F923C, 0)
    m.w32(0x41BFB8, 0x20)
    m.w32(0x41BFBC, 0x40)
    m.w32(0x4028DC, 0)
    m.w8(0x41B6D0, 0)


def act_row(e, name):
    label = e.alloc(16)
    e.mem.write(label, name + b"\0")
    table = e.alloc(8)
    e.mem.write(table, struct.pack("<IHH", label, 0x2000, 0))
    e.mem.w32(0x88D3D4, 0)
    e.mem.w32(0x4F8E7C, 1)
    e.mem.w32(0x4F8E10, 1)
    e.mem.w32(0x4F8E48, table)


def living(e):
    obj = e.alloc(0x20)
    e.mem.w32(obj + 0xC, 0)
    e.mem.w32(0x4D8AE0, 1)
    e.mem.w32(0x4D8AF0 + 0x43D8, obj)


def slot_image(name, sub, seed):
    buf = bytearray(R.SAVE_IMAGE_BYTES)
    buf[:len(name)] = name
    if sub:
        buf[0x14:0x14 + len(sub)] = sub
    struct.pack_into("<I", buf, 0x31C, 0)
    struct.pack_into("<I", buf, 0x16100, seed)
    return bytes(buf)


def save_filename(h, *, selected, count, fresh):
    m = h.e.mem
    prepare_screen(h, sub=0)
    m.w32(0x88D3B0, selected)
    m.w32(0x4F9238, count)
    m.w8(0x8E1AD8, 1 if fresh else 0)
    if not fresh:
        m.write(0x88D060 + 64 * selected, R.OVERWRITE_SLOT_NAME.encode() + b"\0")
    else:
        m.write(0x88D061, b"BASLUS-20973\0")
    m.write(0x41B721, R.LEVEL_NAME.encode() + b"\0")
    m.w8(0x41B771, 0)
    m.w32(0x4D8AE0, 0)
    act_row(h.e, R.LEVEL_NAME.encode())
    h.call(SAVE)
    return (m.cstr(R.SAVE_NAME), m.u32(0x88D3A8), list(h.ops),
            list(h.stored), MAKE_NAME in h.targets())


def save_build_and_write(h):
    """Continue from sub-state 1 through the queued 0x4bc78 write."""
    m = h.e.mem
    m.w32(0x88D3A8, 1)
    h.ops.clear()
    h.stored.clear()
    h.call(SAVE)
    built = SAVE_BUILD in h.targets()
    packed = PACK in h.targets()
    build_args = next((c.args[0] & 0xFFFFFFFF, c.args[1] & 0xFFFFFFFF)
                      for c in h.e.calls if c.target == SAVE_BUILD)
    name = m.cstr(R.SAVE_BUFFER)
    stored = list(h.stored)
    m.w32(0x88D3A8, 2)
    h.ops.clear()
    h.call(SAVE)
    return built, packed, build_args, name, stored, list(h.ops), m.u32(0x88D3A8)


def advance_saved_box(h, *, selected, count):
    m = h.e.mem
    m.w32(0x88D3B0, selected)
    m.w32(0x4F9238, count)
    m.w8(0x4F8F28, 1)
    m.w32(0x8E11F8, 0)
    m.w32(0x8E11FC, 4)
    m.w32(0x88D3A8, 3)
    h.call(SAVE)
    after_wait = (m.u8(0x4F8F29), s32(m.u32(0x8E11FC)), m.u32(0x88D3A8))
    m.w32(0x8E11F8, 16)
    m.w32(0x8E11FC, 0xFFFFFFF0)
    h.call(SAVE)
    reached = m.u32(0x88D3A8)
    m.w32(0x4028DC, 0x40)
    h.call(SAVE)
    armed = s32(m.u32(0x8E11FC))
    keys = h.keys()
    m.w32(0x4028DC, 0)
    m.w32(0x8E11F8, 16)
    m.w32(0x8E11FC, 0xFFFFFFF0)
    h.call(SAVE)
    return after_wait, reached, armed, keys, m.u8(0x4F8F28), s32(m.u32(0x88D3A0))


def card_error(path, seed, pending):
    h = Harness(path, seed)
    prepare_screen(h, sub=2)
    living(h.e)
    m = h.e.mem
    m.w8(0x4F8F28, 1)
    m.w32(0x88D3BC, 1)
    h.call(SAVE)
    during = (m.u32(0x88D3A8), m.u8(0x4F8F28), 0x21E5C8 in h.targets())
    m.w32(0x88D3BC, 0)
    m.w32(0x4028DC, 0x20)
    m.w32(0x88D3C8, 0)
    if pending:
        m.w8(0x402791, 1)
        m.write(0x41B6D0, b"hub\0")
    h.call(SAVE)
    return during, s32(m.u32(0x88D3A0)), m.u8(0x4F8F28), (
        REQUEST_SAVE in h.targets(), m.u32(0x88D3D8))


def requests(path, seed):
    h = Harness(path, seed)
    m = h.e.mem
    m.w32(0x88D3A0, 7)
    m.w32(0x4D8AE0, 0)
    m.w32(0x88D3C8, 0)
    h.call(REQUEST_SAVE, 0, 0, 0)
    idle = s32(m.u32(0x88D3A0))
    living(h.e)
    m.w32(0x4D8AF0 + 0xAC, 0x3F800000)
    m.w32(0x88D3A0, 0xFFFFFFFF)
    m.w32(0x88D3D8, 0)
    h.call(REQUEST_SAVE, 0, 0, 0)
    opened = (m.u8(0x4F923C), s32(m.u32(0x88D3A0)))
    m.w32(0x88D3A0, 7)
    m.w32(0x88D3C8, 1)
    m.w8(0x41B510, 1)
    h.call(REQUEST_LOAD, 2, 1)
    blocked = s32(m.u32(0x88D3A0))
    m.w32(0x88D3C8, 0)
    h.call(REQUEST_LOAD, 2, 1)
    return idle, opened, blocked, (
        m.u8(0x4F923C), m.u8(0x8E1AB8), m.u8(0x8E1AB9),
        s32(m.u32(0x88D3A0)), m.u8(0x4F8F28),
        m.u32(0x88D3E4), m.u32(0x88D3D8))


def new_row_and_handoff(path, seed):
    """Slot-list states that lead back to the save screen with v0 = 1."""
    e = EE(path)
    e.mem.auto_map = True
    e.record_calls = True
    m = e.mem
    m.w32(0x404460, seed)
    ops = []

    def queue(emu):
        ops.append(tuple(emu.r[i] & 0xFFFFFFFF for i in (4, 5, 6, 7)))
        return 0

    e.stub(QUEUE, function=queue)
    e.stub(PUMP, ret=0)
    e.stub(0x21E8B4, ret=0)
    e.stub(0x21E5C8, ret=0)
    e.stub(0x22226C, ret=0)
    e.stub(0x19EA78, ret=0)
    e.stub(0x17365C, ret=0)
    e.stub(0x214230, ret=0)
    # Diagnostic print. Callers do not read it; death-reload 2c95314.
    e.stub(0x355490, ret=0)
    for addr in (0x1800B8, 0x1802E0, 0x180500, 0x181AA0, 0x181C10,
                 0x181CA0, 0x181530, 0x17BD30, 0x17FBB8, 0x17C118):
        e.stub(addr, ret=0)
    m.w32(0x88D3DC, 4)
    m.w32(0x88D3A0, 3)
    m.w32(0x4F9238, 2)
    m.w32(0x879E24, 2)          # settled cursor, same as the target row
    m.w32(0x879E28, 2)          # the free row, index == count
    m.w32(0x879E2C, 0)
    m.w32(0x879E30, 0)
    m.w32(0x879E34, 0)
    m.w32(0x88D3C4, 10)
    m.w32(0x8E11F8, 0x7F)
    m.w32(0x8E11FC, 8)
    m.w32(0x4028DC, 0x40)
    m.w32(0x4028E0, 0x40)
    m.w32(0x41BFB8, 0x20)
    m.w32(0x41BFBC, 0x40)
    m.w32(0x4F7104, 0xF1F1F1F1)
    m.w32(0x4F9540, 0)
    e.call(SLOT, max_steps=300000)
    armed = (m.u32(0x88D3DC), m.u32(0x4F8EF4), s32(m.u32(0x8E11FC)))
    m.w32(0x8E11F8, 0)
    m.w32(0x8E11FC, 0)
    m.w32(0x4F8EF4, 7)
    m.w32(0x4F9544, 1)
    m.w32(0x4F9548, 2)
    m.w32(0x4028DC, 0)
    ops.clear()
    e.call(SLOT, max_steps=300000)
    after_fade = (m.u32(0x88D3DC), ops[0][0] if ops else None)
    m.w32(0x88D3DC, 7)
    m.w32(0x88D3C4, 0)
    m.w32(0x8E11FC, 8)
    m.w32(0x8E11F8, 0x20)
    m.w32(0x88D3EC, 100)
    m.w32(0x88D3AC, 100)
    e.call(SLOT, max_steps=300000)
    enough = (m.u32(0x88D3DC), s32(m.u32(0x8E11FC)))
    m.w32(0x88D3DC, 7)
    m.w32(0x88D3C4, 0)
    m.w32(0x8E11FC, 8)
    m.w32(0x88D3AC, 99)
    e.reset_log()
    e.call(SLOT, max_steps=300000)
    short = (m.u32(0x88D3DC), R.SPACE_KEY in
             tuple(e.mem.cstr(c.args[0] & 0xFFFFFFFF)
                   for c in e.calls if c.target == 0x173C84))
    m.w32(0x88D3DC, 7)
    m.w32(0x88D3C4, 0)
    m.w32(0x8E11F8, 0)
    m.w32(0x8E11FC, 0)
    e.call(SLOT, max_steps=300000)
    to_commit = m.u32(0x88D3DC)
    m.w32(0x88D3DC, 11)
    ops.clear()
    e.call(SLOT, max_steps=300000)
    listed = (m.u32(0x88D3DC), ops[0][:2] if ops else None,
              e.mem.cstr(ops[0][1]) if ops else "")
    m.w32(0x8E11F8, 0)
    m.w32(0x8E11FC, 0)
    m.w8(0x402791, 0)
    returned = e.call(SLOT, max_steps=300000)
    return armed, after_fade, enough, short, to_commit, listed, (
        returned & 0xFFFFFFFF, m.u32(0x88D3DC))


def load_restore(path, seed, name, sub, live_level, live_sub, flag):
    h = Harness(path, seed)
    image = slot_image(name, sub, seed)
    buf = h.e.alloc(R.SAVE_IMAGE_BYTES)
    h.e.mem.write(buf, image)
    h.e.stub(0x17E4C8, ret=buf, name="heap_alloc")
    m = h.e.mem
    prepare_screen(h, sub=2, mode=4)
    m.write(0x88D2E0, b"BASLUS-20973_slot2\0")
    m.write(0x41B721, b"origin\0")
    m.w8(0x41B771, 0)
    m.w8(0x41B720, 0)
    m.w8(0x8E1AB9, flag)
    h.ops.clear()
    h.call(LOAD)
    queued = list(h.ops)
    m.w32(0x4F8EEC, buf)
    m.w32(0x88D3A8, 4)
    m.w8(0x41B6D0, 0)
    h.call(LOAD)
    pending = m.cstr(0x41B6D0)
    side = m.cstr(0x8E1A98)
    marker = m.u8(0x41B720)
    loaded = m.u8(0x8E1AD6)
    sentinel = m.u32(R.SAVE_BUFFER + 0x16100)
    current = m.cstr(0x41B721)
    called = SAVE_LOAD in h.targets()
    world = bool(h.targets() & {WORLD_LOAD, LEVEL_OBJECTS, SAVE_RELOAD})
    sub_state = m.u32(0x88D3A8)
    latch = m.u8(0x4F8F28)
    closed = s32(m.u32(0x88D3A0))
    if flag and called:
        m.w32(0x88D3A8, 5)
        m.w32(0x88D3A0, 4)
        m.write(0x41B721, live_level)
        m.write(0x41B771, live_sub)
        h.call(LOAD)
        stayed = (m.u32(0x88D3A8), m.u8(0x4F8F28), s32(m.u32(0x88D3A0)))
        m.write(0x41B721, name)
        m.write(0x41B771, sub if sub else b"\0")
        h.call(LOAD)
        matched = (m.u32(0x88D3A8), m.u8(0x4F8F28), s32(m.u32(0x88D3A0)))
    else:
        stayed = matched = None
    return queued, buf, pending, side, marker, loaded, sentinel, current, (
        called, world, sub_state, latch, closed, stayed, matched)


def accept_copies_directory(path, seed):
    h = Harness(path, seed)
    m = h.e.mem
    prepare_screen(h, stage=0, sub=0, mode=4)
    h.e.stub(SLOT, ret=1, name="memcard_slotList")
    h.e.stub(PUMP, ret=1, name="mc_pump")  # busy: accept runs, machine waits
    m.w32(0x88D3B0, 1)
    m.write(0x88D080, b"BASLUS-20973_slot1\0")
    m.w8(0x8E1AB8, 0)
    m.w8(0x8E1AB9, 1)
    m.w8(0x4F8F28, 0)
    h.call(LOAD)
    return (m.cstr(0x88D2C0), m.u32(0x88D3D8), m.u32(0x88D3A8),
            m.u8(0x4F8F28), s32(m.u32(0x8E11FC)))


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    path = argv[1]
    with open(path, "rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == SHA256
    checks = 0
    for seed in R.SEEDS:
        fresh_name, fresh_sub, fresh_ops, _, made = save_filename(
            Harness(path, seed), selected=0, count=0, fresh=True)
        assert made and fresh_name == R.FRESH_SLOT_NAME, (seed, made, fresh_name)
        assert fresh_sub == 1, (seed, fresh_sub)
        assert all(op[0] != R.SAVE_WRITE_OP for op in fresh_ops), (seed, fresh_ops)
        checks += 3
        over_name, over_sub, _, _, made = save_filename(
            Harness(path, seed), selected=1, count=2, fresh=False)
        assert over_name == R.OVERWRITE_SLOT_NAME and over_sub == 1, (seed, over_name, over_sub)
        assert not made, (seed, made)
        checks += 2
        forced_name, _, _, _, made = save_filename(
            Harness(path, seed), selected=1, count=0, fresh=True)
        assert made and forced_name == R.FRESH_SLOT_NAME, (seed, made, forced_name)
        checks += 1

        h = Harness(path, seed)
        save_filename(h, selected=1, count=2, fresh=False)
        built, packed, args, name, stored, ops, sub = save_build_and_write(h)
        assert built and not packed, (seed, built, packed)
        assert args == (0, 0), (seed, args)
        assert name == R.LEVEL_NAME, (seed, name)
        assert stored == [R.LEVEL_NAME], (seed, stored)
        assert [(op[0], op[2], op[1]) for op in ops] == [
            (0, R.SAVE_OPEN_MODE, R.SAVE_NAME),
            (R.SAVE_WRITE_OP, R.SAVE_IMAGE_BYTES, R.SAVE_BUFFER),
            (1, 0, 0),
            (6, 0, R.SAVE_NAME),
        ], (seed, ops)
        assert sub == 3, (seed, sub)
        assert not (h.targets() & {WORLD_LOAD, LEVEL_OBJECTS}), seed
        checks += 7
        waited, reached, armed, keys, latch, state = advance_saved_box(
            h, selected=1, count=2)
        assert waited == (1, -16, 3), (seed, waited)
        assert reached == 4, (seed, reached)
        assert armed == -16, (seed, armed)
        assert keys == R.SAVED_KEYS_OVERWRITE, (seed, keys)
        assert latch == 0 and state == -1, (seed, latch, state)
        checks += 5

        h = Harness(path, seed)
        save_filename(h, selected=0, count=0, fresh=True)
        m = h.e.mem
        m.w32(0x88D3A8, 4)
        m.w32(0x88D3B0, 0)
        m.w32(0x4F9238, 0)
        m.w32(0x8E11F8, 0x40)
        m.w32(0x8E11FC, 8)
        h.call(SAVE)
        assert h.keys() == R.SAVED_KEYS_NEW, (seed, h.keys())
        checks += 1

        net = Harness(path, seed)
        prepare_screen(net, sub=1)
        net.e.mem.w8(0x402791, 1)
        net.e.stub(PACK, ret=0, name="save_packLocalPlayer")
        net.call(SAVE)
        assert PACK in net.targets() and SAVE_BUILD not in net.targets(), seed
        assert net.e.mem.u32(0x88D3A8) == 2, seed
        checks += 2

        during, state, latch, reopen = card_error(path, seed, pending=False)
        assert during == (9, 1, True), (seed, during)
        assert state == -1 and latch == 1 and reopen == (True, 1), (
            seed, state, latch, reopen)
        during, state, latch, reopen = card_error(path, seed, pending=True)
        assert during == (9, 1, True), (seed, during)
        assert state == -1 and latch == 1 and reopen == (False, 1), (
            seed, state, latch, reopen)
        checks += 4

        idle, opened, blocked, loaded = requests(path, seed)
        assert idle == 7, (seed, idle)
        assert opened == (0, 3), (seed, opened)
        assert blocked == 7, (seed, blocked)
        assert loaded == (2, 1, 1, 4, 0, 0, 0), (seed, loaded)
        checks += 4

        armed, faded, enough, short, to_commit, listed, handoff = (
            new_row_and_handoff(path, seed))
        assert armed == (4, 7, -16), (seed, armed)
        assert faded == (7, R.SPACE_OP), (seed, faded)
        assert enough == (7, -16), (seed, enough)
        assert short == (7, True), (seed, short)
        assert to_commit == 12, (seed, to_commit)
        assert listed[0] == 12 and listed[1] == (R.DIRECTORY_OP, 0x53F268), (
            seed, listed)
        assert listed[2] == "/BASLUS-20973", (seed, listed)
        assert handoff == (1, 0), (seed, handoff)
        checks += 7

        copied = accept_copies_directory(path, seed)
        assert copied == ("BASLUS-20973_slot1", 1, 0, 0, 16), (seed, copied)
        checks += 1

        for name, sub, live, live_sub, pending in (
            (b"strife\0", b"", b"origin\0", b"\0", R.LOAD_PLAIN),
            (b"hub\0", b"west\0", b"hub\0", b"\0", R.LOAD_QUALIFIED),
        ):
            (queued, buf, got, side, marker, loaded_flag, sentinel, current,
             rest) = load_restore(path, seed, name, sub, live, live_sub, 1)
            called, world, sub_state, latch, closed, stayed, matched = rest
            assert queued[0][0] == 0 and queued[0][2] == 1, (seed, queued)
            assert queued[0][1] == 0x88D2E0, (seed, queued)
            assert queued[1] == (3, buf, R.SAVE_IMAGE_BYTES, 0), (seed, queued)
            assert queued[2][0] == 1, (seed, queued)
            assert called and not world, (seed, called, world)
            assert got == pending and side == pending, (seed, got, side, pending)
            assert marker == 0xFD and loaded_flag == 1, (seed, marker, loaded_flag)
            assert sentinel == seed, (seed, sentinel)
            assert current == "origin", (seed, current)
            assert sub_state == 5 and latch == 1 and closed == 4, (
                seed, sub_state, latch, closed)
            assert stayed == (5, 1, 4), (seed, stayed)
            assert matched[1] == 0 and matched[2] == -1, (seed, matched)
            checks += 10
        skipped = load_restore(path, seed, b"strife\0", b"", b"origin\0", b"\0", 0)
        assert skipped[8][0] is False and skipped[2] == "", (seed, skipped[2], skipped[8])
        assert skipped[8][2] == 0 and skipped[8][3] == 0 and skipped[8][4] == -1, (
            seed, skipped[8])
        assert skipped[6] == seed, (seed, skipped[6])
        checks += 3
    print("PASS save-screen flow: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main(sys.argv)
