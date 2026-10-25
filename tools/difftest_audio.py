#!/usr/bin/env python3
"""difftest_audio.py - compare tools/ref_audio_playback.py with the original functions.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.

  python3 tools/difftest_audio.py [path/to/SLUS_209.73] [-k TEXT]

The original functions run in tools/ee_emu.py on streams and directories this script
builds. Disc, IOP and directory-lookup callees are stubbed. Every compared word is a
flag, a counter or a float pattern; no sample bytes are read or written.

Float properties run once under each of the six interpreter rounding setups. Agreement
means the model does the same operations in the same order. It does not mean either
matches a console in the last bit (docs/issues/dynamic-tests.md).
"""
import hashlib
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

from ee_emu import EE, EmuError  # noqa: E402
import ref_audio_playback as P  # noqa: E402

EXPECTED_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
ROOT = os.path.dirname(_HERE)

G_STREAMS = 0x876C10
STRIDE = 0x1C4
G_MUSIC = 0x4F8944
G_DUCK = 0x4F894C
G_DUCK_TARGET = 0x4F8A0C
G_SOUND_FRAME = 0x4F8954
G_DRAW_FRAME = 0x44FDD0
G_LANGUAGE = 0x44FDDC
G_LEVEL_TEX = 0x44FE18
STATUS = 0x8771C0
PENDING = 0x871A00
SERVICE_GATE = 0x4F89FC
MOVIE_SYNC = 0x506034
MOVIE_FRAME = 0x506038
MOVIE_LAST = 0x8EB000
COUNTDOWN = 0x50608C
CUT_GATE = 0x44FD10
GROUP_VOLUME = 0x41BAC8

FPU_CONFIGS = (
    ("ps2", False, False),
    ("ps2g1", False, False),
    ("chop", False, False),
    ("nearest", False, False),
    ("ps2", True, False),
    ("ps2", False, True),
)

FAILS = 0
FILTER = None


def say(kind, name, detail):
    global FAILS
    if FILTER and FILTER not in name:
        return
    if kind == "FAIL":
        FAILS += 1
    print("%s  %s  %s" % (kind, name, detail), flush=True)


def selected(name):
    return not FILTER or FILTER in name


class Harness:
    def __init__(self, elf):
        self.emu = EE(elf)
        self.dir_ptr = 0
        self.rpcs = []
        self.emu.stub(0x3566F0, function=self._rpc, name="rpc")
        self.emu.stub(0x1724FC, function=self._cd, name="cd_findFile")
        self.emu.stub(0x17377C, function=self._dir, name="res_get")
        self.volumes = []
        self.emu.stub(0x216690, function=self._volume, name="setChannelVolume")
        self.sound_image = self.emu.mem.u32(G_SOUND_FRAME)
        self.draw_image = self.emu.mem.u32(G_DRAW_FRAME)
        self.boss = {}
        for label, text in (("reddragon", b"reddragon"), ("snowboss", b"snowboss"), ("goblin", b"goblin")):
            obj = self.emu.alloc(0x40)
            raw = self.emu.alloc(16)
            self.emu.mem.write(raw, text + b"\0")
            self.emu.mem.w32(obj + 0x34, raw)
            found = self.emu.call(0x10DBE0, obj)
            self.boss[label] = (obj, found, self.emu.mem.cstr(found) if found else "")

    def _rpc(self, emu):
        self.rpcs.append(emu.r[5] & 0xFFFFFFFF)
        return 0

    def _cd(self, emu):
        emu.mem.w32(emu.r[5] & 0xFFFFFFFF, 1)
        emu.mem.w32(emu.r[6] & 0xFFFFFFFF, 0x1000)
        return 1

    def _dir(self, _emu):
        return self.dir_ptr

    def _volume(self, emu):
        self.volumes.append((emu.r[4] & 0xFFFFFFFF, emu.f[12] & 0xFFFFFFFF))
        return 0

    def call(self, addr, *args, fargs=()):
        self.emu.r[29] = self.emu.stack_hi - 0x100
        self.emu.reset_log()
        return self.emu.call(addr, *args, fargs=fargs)

    def put_dir(self, rows):
        blob = bytearray()
        for name, offset, rate, stereo, language, restart in rows:
            blob += name.encode("ascii").ljust(0x40, b"\0")
            blob += struct.pack("<IIHhI", offset, rate, stereo, language, restart)
        addr = self.emu.alloc(len(blob) + 16, fill=0)
        self.emu.mem.write(addr, bytes(blob))
        self.dir_ptr = addr

    def wipe(self, index):
        self.emu.mem.write(G_STREAMS + index * STRIDE, bytes(STRIDE))

    def stream(self, index):
        return G_STREAMS + index * STRIDE

    def entry(self, index, slot=0):
        return self.stream(index) + 0x40 + slot * 0x30

    def words(self, addr, offsets):
        return {off: self.emu.mem.u32(addr + off) for off in offsets}

    def queue(self, index, flags, offset, length, rate, stereo, restart, text=b"track.vag"):
        name = self.emu.alloc(32)
        self.emu.mem.write(name, text + b"\0")
        self.call(0x2113C8, index, name, flags, offset, length, rate, stereo, restart)

    def slice(self, start, until, status=0, gate=None):
        calls = []

        def status_fn(emu):
            return status

        def watch(label):
            def inner(emu):
                calls.append((label, emu.r[4] & 0xFFFFFFFF))
                return 0
            return inner

        self.emu.stub(0x211B20, function=status_fn, name="streamStatus")
        self.emu.stub(0x211338, function=watch("queueStop"), name="queueStop")
        self.emu.stub(0x211CE8, function=watch("streamStop"), name="streamStop")
        self.emu.stub(0x216130, function=watch("clearQueue"), name="clearQueue")
        if gate is not None:
            self.emu.mem.w32(CUT_GATE, gate)
        self.emu.r[29] = self.emu.stack_hi - 0x1000
        self.emu.r[6] = self.emu.stack_hi - 0x800
        self.emu.r[31] = EE.RETURN_ADDR
        self.emu.reset_log()
        reason = self.emu.run(start=start, until={until}, max_steps=4000)
        for addr in (0x211B20, 0x211338, 0x211CE8, 0x216130):
            self.emu.unhook(addr)
        return reason, calls

    def fpu(self, model, bias, nearest):
        self.emu.fpu_model = model
        self.emu.fpu_mul_bias = bias
        self.emu.fpu_div_nearest = nearest


def check(name, ok, detail):
    say("PASS" if ok else "FAIL", name, detail)


def test_image(h):
    if not selected("cadence image"):
        return
    check("cadence image",
          (h.sound_image, h.draw_image) == (P.SOUND_FRAME_IMAGE, P.DRAW_FRAME_IMAGE),
          "g_soundFrame %s g_drawFrame %s" % (hex(h.sound_image), hex(h.draw_image)))


def test_gate_and_queue(h):
    if not selected("music queue"):
        return
    name = h.boss["reddragon"][1]
    h.put_dir([
        (h.boss["reddragon"][2], 0x111000, 0x3333, 1, 0, 0x444400),
        ("", 0x333000, 0, 0, 0, 0),
    ])
    cases = 0
    bad = []
    for volume in (P.MUSIC_VOLUME_GATE - 1, P.MUSIC_VOLUME_GATE, P.MUSIC_VOLUME_GATE + 1, 0, 0x3F800000):
        h.wipe(2)
        h.emu.mem.w32(G_MUSIC, volume)
        h.call(0x2110E0, name, 0x103)
        count = h.emu.mem.u32(h.stream(2) + 0x1C0)
        expect = 1 if P.music_gate_open(volume) else 0
        words = h.words(h.entry(2), (0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C))
        model = P.queued_music(0x103, 0x111000, 0x222000, 0x3333, 1, 0x444400)
        ok = count == expect and (expect == 0 or words == model)
        ok = ok and (expect == 0 or h.emu.mem.cstr(h.entry(2)) == P.MOUTH_VAT)
        if not ok:
            bad.append((hex(volume), count, words))
        cases += 1
    # A zero-length row is not queued even when the gate is open.
    h.put_dir([(h.boss["reddragon"][2], 0x1000, 24000, 1, 0, 0x400), ("", 0x1000, 0, 0, 0, 0)])
    h.wipe(2)
    h.emu.mem.w32(G_MUSIC, 0x3F800000)
    h.call(0x2110E0, name, 1)
    cases += 1
    if h.emu.mem.u32(h.stream(2) + 0x1C0) != 0:
        bad.append(("zero-length", h.emu.mem.u32(h.stream(2) + 0x1C0)))
    check("music queue", not bad, "%d volumes and one empty span; mismatches %s" % (cases, bad))


def test_boss(h):
    if not selected("boss override"):
        return
    a_obj, a_name, a_text = h.boss["reddragon"]
    b_obj, b_name, b_text = h.boss["snowboss"]
    g_obj = h.boss["goblin"][0]
    h.put_dir([
        (a_text, 0x111000, 24000, 1, 0, 0x400),
        (b_text, 0x333000, 24000, 1, 0, 0x800),
        ("", 0x555000, 0, 0, 0, 0),
    ])
    h.emu.mem.w32(G_MUSIC, 0x3F800000)
    h.wipe(2)
    h.call(0x1192B0, a_obj)
    first = h.words(h.entry(2), (0x10, 0x28, 0x2C))
    h.call(0x1192B0, b_obj)
    second = h.words(h.entry(2), (0x10, 0x28, 0x2C))
    count = h.emu.mem.u32(h.stream(2) + 0x1C0)
    active = h.emu.mem.cstr(h.stream(2))
    h.call(0x1192B0, g_obj)
    after_goblin = h.words(h.entry(2), (0x10, 0x28, 0x2C))
    h.call(0x1192F8, a_obj)
    stop_count = h.emu.mem.u32(h.stream(2) + 0x1C0)
    stop_flags = h.emu.mem.u32(h.entry(2, 1) + 0x2C)
    stop_name = h.emu.mem.cstr(h.entry(2, 1))
    h.call(0x1192F8, g_obj)
    goblin_stop = h.emu.mem.u32(h.stream(2) + 0x1C0)
    h.emu.mem.w32(G_MUSIC, P.MUSIC_VOLUME_GATE - 1)
    h.call(0x1192B0, b_obj)
    silenced = h.emu.mem.u32(h.stream(2) + 0x1C0) == 0 and h.emu.mem.cstr(h.stream(2)) == ""
    # A known boss whose row is absent still stops, then queues nothing.
    # music_playGlobal will not plant that row, so the occupied queue is built
    # directly and the start is what clears it.
    h.put_dir([("other.vag", 0, 24000, 1, 0, 0), ("", 0x800, 0, 0, 0, 0)])
    h.emu.mem.w32(G_MUSIC, 0x3F800000)
    h.wipe(2)
    h.queue(2, 1, 0x1000, 0x800, 24000, 1, 0)
    planted = h.emu.mem.u32(h.stream(2) + 0x1C0)
    h.call(0x1192B0, a_obj)
    missing = h.emu.mem.u32(h.stream(2) + 0x1C0) == 0 and h.emu.mem.cstr(h.stream(2)) == ""
    model_first = P.queued_music(P.GLOBAL_BOSS_FLAGS, 0x111000, 0x222000, 24000, 1, 0x400)
    model_second = P.queued_music(P.GLOBAL_BOSS_FLAGS, 0x333000, 0x222000, 24000, 1, 0x800)
    ok = (
        planted == 1
        and first == {0x10: model_first[0x10], 0x28: model_first[0x28], 0x2C: 0x123}
        and count == 1 and active == ""
        and second == {0x10: model_second[0x10], 0x28: model_second[0x28], 0x2C: 0x123}
        and after_goblin == second
        and stop_count == 2 and stop_flags == P.FLAG_FADE and stop_name == ""
        and goblin_stop == 2
        and silenced and missing
        and P.boss_action(True, 0x3F800000, 0x222000) == "replace"
        and P.boss_action(False, 0x3F800000, 0x222000) == "noop"
        and P.boss_action(True, P.MUSIC_VOLUME_GATE - 1, 0x222000) == "silence"
    )
    check("boss override", ok,
          "A then B keeps B's span 0x%x; stop appends flag 2; closed gate and a missing row silence"
          % second.get(0x10, 0))


def test_promote(h):
    if not selected("queue promote"):
        return
    bad = []
    cases = (
        (0x40, 0x3FFF, True, (0x50, 0x70)),
        (0x140, 0x3FFF, True, (0x50, 0x70)),
        (0x42, 0x3FFF, False, (0x50, 0x70)),
        (0x142, 1, False, (0x50, 0x70)),
        (0x123, 0, True, (0x50, 0x60, 0x70)),
        (0x123, 0x3FFF, False, (0x50, 0x70)),
        (0x8, 0, False, (0x50,)),
        (0x108, 0, False, (0x50,)),
    )
    for flags, volume, promotes, rpcs in cases:
        for index in range(3):
            h.wipe(index)
        h.emu.mem.write(STATUS, bytes(0x40))
        h.emu.mem.w32(STATUS + 2 * 16 + 8, volume)
        h.queue(2, flags, 0x333000, 0x222000, 24000, 1, 0x800)
        before = h.emu.mem.u32(h.stream(2) + 0x1C0)
        h.rpcs.clear()
        h.call(0x211548)
        after = h.emu.mem.u32(h.stream(2) + 0x1C0)
        got = after == 0
        model = not ((flags & P.FLAG_HOLD) or ((flags & P.FLAG_FADE) and volume))
        if before != 1 or got != promotes or got != model or tuple(h.rpcs) != rpcs:
            bad.append((hex(flags), hex(volume), before, after, [hex(x) for x in h.rpcs]))
        if got:
            head = h.words(h.stream(2), (0x10, 0x14, 0x18, 0x1C, 0x20, 0x3C))
            expect = {0x10: 0x333000, 0x14: 0x222000, 0x18: 0x333000, 0x1C: 0x222000,
                      0x20: flags, 0x3C: 0x800}
            if head != expect or h.emu.mem.cstr(h.stream(2)) != "track.vag":
                bad.append(("head", hex(flags), head))
    check("queue promote", not bad,
          "%d flag/volume pairs; 0x40 and 0x100 do not change it; mismatches %s" % (len(cases), bad))


def test_status(h):
    if not selected("stream status"):
        return
    base = h.stream(2)
    bad = []
    specs = (
        ("playing", 1, 2, 0, 0x140, 0, 0),
        ("remain", 0, 0, 1, 0x40, 0, 0),
        ("queued", 0, 0, 0, 0, 1, 0x100),
        ("held", 0, 0, 0, 0, 1, 0x108),
        ("idle", 0, 0, 0, 0x40, 0, 0),
        ("negative", 0, 0, 0x80000000, 0x40, 1, 0x100),
        ("both", 5, 5, 4, 0x1E0, 0, 0),
    )
    for label, write, read, remain, active, count, first in specs:
        h.wipe(2)
        h.emu.mem.write(STATUS, bytes(0x40))
        h.emu.mem.w32(STATUS + 2 * 16, write)
        h.emu.mem.w32(STATUS + 2 * 16 + 4, read)
        h.emu.mem.w32(base + 0x14, remain)
        h.emu.mem.w32(base + 0x20, active)
        h.emu.mem.w32(base + 0x1C0, count)
        h.emu.mem.w32(base + 0x6C, first)
        got = h.call(0x211B20, 2) & 0xFFFFFFFF
        model = P.stream_status_bits(write, read, remain, active, count, first)
        if got != model:
            bad.append((label, hex(got), hex(model)))
    check("stream status", not bad, "%d arrangements; mismatches %s" % (len(specs), bad))


def test_flag_callers(h):
    if not selected("flag callers"):
        return
    bad = []
    sites = (
        ("recall", 0x18C468, 0x18C488, None),
        ("timer", 0x18D7CC, 0x18D7E8, None),
        ("level", 0x18E2D4, 0x18E2F4, None),
        ("hud", 0x1D9040, 0x1D922C, None),
        ("frontend", 0x1E10F4, 0x1E1114, None),
    )
    for name, start, until, _gate in sites:
        for status in (0x40, 0x41, 0x20, 0x140, 0):
            reason, calls = h.slice(start, until, status=status)
            expect = [("queueStop", 2)] if P.recall_stops_music(status) else []
            if reason != "stop" or calls != expect:
                bad.append((name, hex(status), reason, calls))
    cuts = (
        ("run-off", 0x199E54, 0x199E98, 0, 0x80, []),
        ("run-keep", 0x199E54, 0x199E98, 1, 0x180, []),
        ("run-stop", 0x199E54, 0x199E98, 1, 0x80, [("streamStop", 2)]),
        ("run-quiet", 0x199E54, 0x199E98, 1, 0x20, []),
        ("end-off", 0x19A114, 0x19A168, 0, 0x80, []),
        ("end-keep", 0x19A114, 0x19A168, 1, 0x180, []),
        ("end-hard", 0x19A114, 0x19A168, 1, 0x80, [("streamStop", 2)]),
        ("end-clear", 0x19A114, 0x19A168, 1, 0x20, [("clearQueue", 2)]),
        ("end-idle", 0x19A114, 0x19A168, 1, 0, [("clearQueue", 2)]),
    )
    for name, start, until, gate, status, expect in cuts:
        reason, calls = h.slice(start, until, status=status, gate=gate)
        model = P.cut_run_stream2(gate, status) if name.startswith("run") else P.cut_end_stream2(gate, status)
        mapped = [] if model is None else [("streamStop" if model == "stop" else "clearQueue", 2)]
        if reason != "stop" or calls != expect or mapped != expect:
            bad.append((name, reason, calls, mapped))
    check("flag callers", not bad,
          "%d recall/cut decisions; 0x40 fade-stops, 0x100 keeps stream 2; mismatches %s"
          % (len(sites) * 5 + len(cuts), bad))


def test_loop(h):
    if not selected("loop restart"):
        return
    h.emu.stub(0x172BE8, ret=0, name="cd_isBusy")
    h.emu.stub(0x211548, ret=1, name="startQueued")
    bad = []
    rows = [(restart, 1, 0x111, 0, 0x2000, 0x9000, 0) for restart in
            (0, 1, 0x3FF, 0x400, 0x401, 0x800, 0x123456, 0x7FFFFC00, 0x80000000, 0x40000000)]
    rows += [
        (0x400, 0, 0x111, 0, 0x2000, 0x9000, 0),
        (0x400, 0x40, 0x111, 0, 0x2000, 0x9000, 0),
        (0x400, 0x141, 0x111, 0, 0x2000, 0x9000, 0),
        (0x400, 1, 0x111, 0x20, 0x2000, 0x9000, 0),
        (0x400, 1, 0x111, 0x20, 0x2000, 0x9000, 0x20),
        (0x800, 1, 0, 0x800, 0x1000, 0x5000, 0x800),
    ]
    try:
        for restart, flags, pos, remain, offset, length, nbytes in rows:
            _run_loop(h, "track.vag", flags, pos, remain, offset, length, restart, nbytes, True, True, False, bad)
        _run_loop(h, "", 1, 0x111, 0x10, 0x2000, 0x9000, 0x400, 0x10, True, True, False, bad)
        _run_loop(h, "track.vag", 1, 0x111, 0, 0x2000, 0x9000, 0x400, 0, False, True, False, bad)
        _run_loop(h, "track.vag", 1, 0x55, 0x66, 0x2000, 0x9000, 0x400, 0, True, False, False, bad)
        h.emu.stub(0x172BE8, ret=1, name="cd_isBusy")
        _run_loop(h, "track.vag", 1, 0x55, 0x66, 0x2000, 0x9000, 0x400, 0, True, True, True, bad)
    finally:
        h.emu.unhook(0x172BE8)
        h.emu.unhook(0x211548)
    check("loop restart", not bad, "%d completed reads; mismatches %s" % (len(rows) + 4, bad))


def _run_loop(h, name, flags, pos, remain, offset, length, restart, nbytes, pending, gate, busy, bad):
    base = h.stream(0)
    h.wipe(0)
    if name:
        h.emu.mem.write(base, name.encode("ascii") + b"\0")
    h.emu.mem.w32(base + 0x10, pos)
    h.emu.mem.w32(base + 0x14, remain)
    h.emu.mem.w32(base + 0x18, offset)
    h.emu.mem.w32(base + 0x1C, length)
    h.emu.mem.w32(base + 0x20, flags)
    h.emu.mem.w32(base + 0x3C, restart)
    h.emu.mem.w8(SERVICE_GATE, 1 if gate else 0)
    h.emu.mem.w8(PENDING, 1 if pending else 0)
    h.emu.mem.w32(PENDING + 4, 0)
    h.emu.mem.w32(PENDING + 8, nbytes)
    h.call(0x211DF8)
    got = (h.emu.mem.u32(base + 0x10), h.emu.mem.u32(base + 0x14))
    if busy or not gate or not pending:
        expect = (pos, remain)
    else:
        expect = P.after_completed_read(name, flags, pos, remain, offset, length, restart, nbytes)
    if got != expect:
        bad.append((name, hex(flags), hex(restart), hex(nbytes), pending, gate, busy, got, expect))


def test_duck(h, model="ps2", bias=False, nearest=False, label="duck"):
    if not selected(label):
        return
    h.fpu(model, bias, nearest)
    bad = []
    specs = (
        (0x3F800000, 0, 0x21, 0x21, "", 0),
        (0x3F800000, 0, 0, 0x21, "", 0),
        (0x3F800000, 0, 0x21, 0, "", 0),
        (0x3F800000, 0, 0x21, 0x21, "actintro", 0),
        (0x3F800000, 0, 0x21, 0x21, "actintro", 1),
        (0x3F800000, 0, 0x21, 0x21, "hub", 1),
        (0x3E5DDDE1, 0x3E5DDDE1, 0x21, 0x21, "", 0),
    )
    for current, target, voice, music, text, language in specs:
        h.emu.mem.w32(G_DUCK, current)
        h.emu.mem.w32(G_DUCK_TARGET, target)
        h.emu.mem.w32(G_MUSIC, 0x3F800000)
        h.emu.mem.w8(G_LANGUAGE, language)
        h.emu.mem.write(G_LEVEL_TEX, text.encode("ascii") + b"\0")

        def status(emu, voice=voice, music=music):
            stream = emu.r[4] & 0xFFFFFFFF
            if stream == 1:
                return voice
            if stream == 2:
                return music
            return 0

        h.emu.stub(0x211B20, function=status, name="streamStatus")
        h.volumes.clear()
        h.call(0x212500)
        got = (h.emu.mem.u32(G_DUCK), h.emu.mem.u32(G_DUCK_TARGET))
        model_c, model_t = P.duck_update(current, target, voice, text, language, model, bias)
        send = P.duck_sends_volume(current, model_c, music)
        vol = P.ducked_volume(model_c, 0x3F800000, model, bias) if send else None
        got_vol = h.volumes[-1][1] if h.volumes else None
        if got != (model_c, model_t) or got_vol != vol or (h.volumes and h.volumes[-1][0] != 2):
            bad.append((text, language, hex(voice), got, (hex(model_c), hex(model_t)), got_vol, vol))
    h.emu.unhook(0x211B20)
    bad_set = _set_duck(h, model, bias)
    bad.extend(bad_set)
    suffix = "" if model == "ps2" and not bias and not nearest else " %s%s%s" % (
        model, " bias" if bias else "", " nearest" if nearest else "")
    check(label + suffix, not bad, "%d steps; mismatches %s" % (len(specs) + 3, bad))


def _set_duck(h, model, bias):
    bad = []
    h.emu.stub(0x211B20, function=lambda e: 0, name="streamStatus")
    h.emu.mem.w8(G_LANGUAGE, 0)
    h.emu.mem.write(G_LEVEL_TEX, b"\0")
    for argument in (0, 0x3F800000, 0x3E4CCCCD):
        h.emu.mem.w32(G_DUCK, 0x3F000000)
        h.emu.fset(12, 0)
        h.emu.f[12] = argument
        h.emu.r[29] = h.emu.stack_hi - 0x100
        h.emu.r[31] = EE.RETURN_ADDR
        h.emu.reset_log()
        h.emu.call(0x216570)
        target = h.emu.mem.u32(G_DUCK_TARGET)
        current = h.emu.mem.u32(G_DUCK)
        if target != P.set_duck_target(argument, model) or current != 0x3F000000:
            bad.append(("set", hex(argument), hex(target), hex(current)))
        h.volumes.clear()
        h.call(0x212500)
        got = (h.emu.mem.u32(G_DUCK), h.emu.mem.u32(G_DUCK_TARGET))
        model_c, model_t = P.duck_update(0x3F000000, target, 0, "", 0, model, bias)
        if got != (model_c, model_t):
            bad.append(("step", hex(argument), got, (hex(model_c), hex(model_t))))
    h.emu.unhook(0x211B20)
    return bad


def test_sound_cadence(h):
    if not selected("sound cadence"):
        return
    stubs = (
        (0x212500, "duck"),
        (0x2134E8, "playSample"),
        (0x212340, "pauseVoices"),
        (0x211DF8, "service"),
        (0x2147C0, "seq"),
        (0x2149D0, "ambient"),
        (0x210CD0, "flush"),
        (0x35EE38, "endFlags"),
        (0x2166E0, "sendVolumes"),
    )
    for addr, name in stubs:
        h.emu.stub(addr, ret=0, name=name)
    bad = []
    try:
        for frame in list(range(17)) + [0xF, 0x10, 0x40000]:
            h.emu.mem.w32(G_SOUND_FRAME, frame)
            h.call(0x212670)
            names = [c.name for c in h.emu.calls if c.name]
            model = P.sound_cadence(frame)
            got = {
                "queues": names.count("service") == 1,
                "end_flags": names.count("endFlags") == 2,
                "send_volumes": "sendVolumes" in names,
                "next": h.emu.mem.u32(G_SOUND_FRAME),
            }
            if got["end_flags"] != model["end_flags"]:
                got["end_flags"] = names.count("endFlags") == 2
            if got != model or names.count("endFlags") not in (0, 2):
                bad.append((hex(frame), got, model, names))
    finally:
        for addr, _name in stubs:
            h.emu.unhook(addr)
    check("sound cadence", not bad, "frames 0..16 plus the image phase; mismatches %s" % bad)


def test_draw_cadence(h):
    if not selected("draw cadence"):
        return
    directory = h.emu.alloc(0x100)
    h.emu.mem.write(directory, b"amb_a.vag".ljust(0x50, b"\0") + bytes(0x50))
    other = h.emu.alloc(0x80)
    h.emu.mem.write(other, b"mx_theme.vag".ljust(0x50, b"\0") + bytes(0x50))
    queued = []
    holder = {"dir": directory, "status": 0}

    def grab(emu):
        queued.append((emu.r[4] & 0xFFFFFFFF, emu.r[5] & 0xFFFFFFFF, emu.r[6] & 0xFFFFFFFF))
        return 0

    def level_dir(_emu):
        return holder["dir"]

    def status(_emu):
        return holder["status"]

    h.emu.stub(0x216860, function=level_dir, name="levelDir")
    h.emu.stub(0x211018, function=grab, name="queueIndex")
    h.emu.stub(0x215F48, ret=0, name="playLevel")
    h.emu.stub(0x216310, ret=0, name="queuedFlags")
    h.emu.stub(0x211B20, function=status, name="streamStatus")
    bad = []
    frames = (0x400, 0x401, 0x40F, 0x410, 0, 15, 16, 0x40000, 0x40001)
    try:
        h.emu.mem.w32(COUNTDOWN, 8)
        for frame in frames:
            for status_bits, directory_ptr, expect in (
                (0, directory, P.draw_cadence(frame)),
                (1, directory, False),
                (0x21, directory, False),
                (0, other, False),
                (0, 0, False),
            ):
                queued.clear()
                holder["dir"] = directory_ptr
                holder["status"] = status_bits
                h.emu.mem.w32(G_DRAW_FRAME, frame)
                h.emu.mem.w32(COUNTDOWN, 8)
                h.call(0x322520)
                due = bool(expect and status_bits == 0 and directory_ptr == directory)
                got = queued == [(0, 0, 3)] if due else queued == []
                if not got:
                    bad.append((hex(frame), hex(status_bits), queued))
        for frame in (0x400, 0x401, 0, 1, 16):
            h.emu.mem.w32(G_DRAW_FRAME, frame)
            h.emu.mem.w32(GROUP_VOLUME, 0x11111111)
            h.call(0x170238)
            wrote = h.emu.mem.u32(GROUP_VOLUME) != 0x11111111
            if wrote != P.draw_cadence(frame):
                bad.append(("group", hex(frame), hex(h.emu.mem.u32(GROUP_VOLUME))))
    finally:
        for addr in (0x216860, 0x211018, 0x215F48, 0x216310, 0x211B20):
            h.emu.unhook(addr)
    check("draw cadence", not bad,
          "amb_ poll and group volumes follow g_drawFrame, not g_soundFrame; mismatches %s" % bad)


def test_intro(h):
    if not selected("intro drift"):
        return
    seen = []

    def play(emu):
        seen.append((emu.r[4] & 0xFFFFFFFF, emu.r[6] & 0xFFFFFFFF,
                     h.emu.mem.cstr(emu.r[5] & 0xFFFFFFFF)))
        return 0

    for addr, name in (
        (0x19DD48, "setRate"),
        (0x173558, "load"),
        (0x3202C0, "movieOpen"),
        (0x211A08, "startHeld"),
        (0x320498, "movieFinished"),
    ):
        h.emu.stub(addr, ret=0, name=name)
    h.emu.stub(0x215C20, function=play, name="playGlobalStream")
    bad = []
    try:
        for ready in (0, 1):
            seen.clear()
            h.emu.mem.w32(0x506088, 0)
            h.emu.mem.w8(MOVIE_SYNC, 0)
            h.emu.stub(0x211C18, ret=ready, name="heldReady")
            h.call(0x321788)
            if h.emu.mem.u8(MOVIE_SYNC) != 0 or seen != [(0, 8, "porko_l.vag")]:
                bad.append((ready, h.emu.mem.u8(MOVIE_SYNC), seen))
    finally:
        for addr in (0x19DD48, 0x173558, 0x3202C0, 0x211A08, 0x320498, 0x215C20, 0x211C18):
            h.emu.unhook(addr)
    check("intro drift", not bad,
          "splash holds porko on stream 0 and leaves the sync gate clear")


def test_intro_refs(elf, h):
    if not selected("intro drift"):
        return
    blob = open(elf, "rb").read()
    missing = []
    for addr in (0x3205C8, 0x3205E0):
        jal = struct.pack("<I", (3 << 26) | (addr >> 2))
        ptr = struct.pack("<I", addr)
        if blob.count(jal) or blob.count(ptr):
            missing.append(hex(addr))
    update = struct.pack("<I", (3 << 26) | (0x3205EC >> 2))
    # The splash half of this property already printed if the filter matches.
    # Report the caller scan on its own line so a splash failure stays visible.
    check("intro drift callers", not missing and blob.count(update) >= 1,
          "enable/disable callers %s; movie_update jal count %d" % (missing, blob.count(update)))


def test_movie(h, model="ps2", bias=False, nearest=False, label="movie drift"):
    if not selected(label):
        return
    h.fpu(model, bias, nearest)
    asked = []

    def position(emu, value):
        asked.append(emu.r[4] & 0xFFFFFFFF)
        return value

    h.emu.stub(0x3735E8, ret=0, name="decode")
    bad = []
    samples = (
        (0, 10, 0x400, 0),
        (0, 100, 0x10000, 1),
        (1, 10, 0x800, 0x800),
        (1, 10, 0x400, 0),
        (1, 10, 0x8000, 0),
        (1, 0, 0, 1),
        (1, 100, 0x10000, 0),
        (1, 50, 0x20000, 0),
        (1, 30, 0x10000, 0),
        (1, 1, 0x500, 0),
        (1, 20, 0x4000, 0x100),
    )
    try:
        for enabled, frame, pos, last in samples:
            asked.clear()
            h.emu.mem.w8(MOVIE_SYNC, enabled)
            h.emu.mem.w32(MOVIE_FRAME, frame)
            h.emu.mem.w32(MOVIE_LAST, last)
            h.emu.stub(0x216480, function=lambda e, p=pos: position(e, p), name="streamPos")
            h.emu.r[31] = EE.RETURN_ADDR
            h.emu.r[29] = h.emu.stack_hi - 0x200
            h.emu.reset_log()
            reason = h.emu.run(start=0x3209F8, until={0x320AF0}, max_steps=8000)
            got = (h.emu.mem.u32(MOVIE_FRAME), h.emu.mem.u32(MOVIE_LAST), tuple(asked))
            hold, nxt, stored = P.movie_sync(enabled, frame, pos, last, model, bias)
            expect_asked = () if not enabled else (2,)
            expect = (nxt, stored, expect_asked)
            if reason != "stop" or got != expect:
                bad.append((enabled, frame, hex(pos), got, expect, reason))
            if hold and nxt != frame:
                bad.append(("hold", frame, nxt))
    finally:
        h.emu.unhook(0x3735E8)
        h.emu.unhook(0x216480)
    suffix = "" if model == "ps2" and not bias and not nearest else " %s%s%s" % (
        model, " bias" if bias else "", " nearest" if nearest else "")
    check(label + suffix, not bad, "%d frame/position pairs on stream 2; mismatches %s" % (len(samples), bad))


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith("-")]
    env = os.environ.get("CHAMPIONS_ELF")
    if env:
        candidates.append(env)
    candidates += [os.path.join(ROOT, "SLUS_209.73"), "SLUS_209.73"]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def main(argv=None):
    global FILTER
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    while argv:
        item = argv.pop(0)
        if item == "-k" and argv:
            FILTER = argv.pop(0)
        else:
            args.append(item)
    elf = find_elf(args)
    if elf is None:
        print("SKIP  SLUS_209.73 not found (pass its path); nothing was compared")
        return 0
    digest = hashlib.sha256(open(elf, "rb").read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print("SKIP  %s is not the US v2.00 executable; nothing was compared" % elf)
        return 0
    try:
        harness = Harness(elf)
    except EmuError as exc:
        say("FAIL", "setup", str(exc))
        return 1
    # Remember the path for the caller scan without keeping the bytes on the harness.
    properties = (
        test_image, test_gate_and_queue, test_boss, test_promote, test_status,
        test_flag_callers, test_loop, test_duck, test_sound_cadence, test_draw_cadence,
        test_intro, test_movie,
    )
    for prop in properties:
        try:
            if prop is test_intro:
                prop(harness)
                test_intro_refs(elf, harness)
            else:
                prop(harness)
        except EmuError as exc:
            say("FAIL", prop.__name__, str(exc))
    if selected("duck") or selected("movie drift"):
        for model, bias, nearest in FPU_CONFIGS[1:]:
            try:
                test_duck(harness, model, bias, nearest, "duck")
                test_movie(harness, model, bias, nearest, "movie drift")
            except EmuError as exc:
                say("FAIL", "fpu %s" % model, str(exc))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
