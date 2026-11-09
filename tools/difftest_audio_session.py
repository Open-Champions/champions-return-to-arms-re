#!/usr/bin/env python3
"""difftest_audio_session.py - compare tools/ref_audio_session.py with the original functions.

Needs your own SLUS_209.73 (US v2.00). Without it the script says so and exits 0.

  python3 tools/difftest_audio_session.py [path/to/SLUS_209.73] [--seed N] [--cases N] [-k TEXT]

The original functions (or the named address slices of a larger function) run in
tools/ee_emu.py. Every callee that would reach the disc, the IOP or the object system is
stubbed, and each stub is named in the property that uses it. A stub records its
arguments and returns the value the case chose. Compared values are identifiers (entry or
sequence names), call lists, counters, flag words and raw float patterns. No sample byte
is read or written and no directory row comes from the disc: every name given to a
function here is synthetic or is a string the executable itself contains.

Random cases come from Python's random.Random(seed); the default seed is 20973. Run it
with --seed 7 as well.
"""
import hashlib
import os
import random
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ goes to the END of the path: tools/dis.py must not shadow the standard library's dis
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

from ee_emu import EE, EmuError  # noqa: E402
import ref_audio_session as S  # noqa: E402

EXPECTED_SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
ROOT = os.path.dirname(_HERE)

G_COSMETIC_SEED = 0x404460
G_RAND_SEED = 0x404464
RECALL_RETURN = 0x41B51C
RECALL_OUT = 0x41B51E
COUNTDOWN = 0x50608C
PVP_MODE_B = 0x4F7120
G_SFX = 0x4F8940
G_MUSIC = 0x4F8944
G_STEREO = 0x4F8948
G_DUCK = 0x4F894C
G_SOUND_FRAME = 0x4F8954
CHANNELS = 0x4F8A18
G_DRAW_FRAME = 0x44FDD0
PAUSE_TIMER = 0x44FA7C
FRONT_TIMER = 0x4F7030
CUTSCENE_BYTE = 0x44FCD0
NET_BYTE = 0x402791
MENU_BYTE = 0x41B69D
VOICE_NAME = 0x41B721
PLAYERS = 0x4D8AF0
PLAYER_STRIDE = 0x4C30
LEVEL_TABLE = 0x4F7210
RPC_SEND = 0x877200
G_STREAMS = 0x876C10

FAILS = 0
FILTER = None
CASES = 300


def say(kind, name, detail):
    global FAILS
    if FILTER and FILTER not in name:
        return
    if kind == "FAIL":
        FAILS += 1
    print("%s  %s  %s" % (kind, name, detail), flush=True)


def selected(name):
    return not FILTER or FILTER in name


def check(name, ok, detail):
    say("PASS" if ok else "FAIL", name, detail)


class Harness:
    """One EE for every property. Stubs are installed per property and removed after."""

    def __init__(self, elf):
        self.emu = EE(elf)
        self.log = []
        self.pos_bytes = []

    def recorder(self, name, strings=(), floats=0, ret=0):
        def run(emu):
            ints = [emu.r[4 + i] & 0xFFFFFFFF for i in range(4)]
            for i in strings:
                ints[i] = emu.mem.cstr(ints[i], 80) if ints[i] else None
            self.log.append((name, tuple(ints), tuple(emu.f[12 + i] & 0xFFFFFFFF for i in range(floats))))
            return ret(emu) if callable(ret) else ret
        return run

    def stubs(self, table):
        for addr, function in table.items():
            self.emu.stub(addr, function=function)
        return list(table)

    def unstub(self, addrs):
        for addr in addrs:
            self.emu.unhook(addr)

    def fresh(self):
        self.log = []
        self.emu.reset_log()
        self.emu.r[29] = self.emu.stack_hi - 0x200
        self.emu.r[31] = EE.RETURN_ADDR

    def call(self, addr, *args, fargs=()):
        self.fresh()
        return self.emu.call(addr, *args, fargs=fargs)

    def slice(self, start, until, max_steps=200000):
        self.emu.r[31] = EE.RETURN_ADDR
        self.emu.r[29] = self.emu.stack_hi - 0x200
        return self.emu.run(start=start, until=set(until), max_steps=max_steps)


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


# ---- level entry ------------------------------------------------------------------------
SYN_NAMES = ("amb_test_l.vag", "mx_theme_test_l.vag", "a_env_b_l.vag", "x_enttag_l.vag",
             "enttag", "voice001.vag", "y_enttag_z.vag", "q.vag")


def test_level_entry(h, rng):
    """game_loadLevel 0x1e59a4-0x1e5a90, which first copies g_randSeed into g_cosmeticSeed.
    Stubs: level directory getter 0x216860 (returns
    a synthetic 0x50-byte-row directory or 0), music_playLevel 0x215f48, game_set4f83b8
    0x1ec0e0 and stream_queueStop 0x211338 (all recorded). libc strstr runs."""
    e = h.emu
    state = {"dir": 0}
    addrs = h.stubs({
        0x216860: h.recorder("dir", ret=lambda _e: state["dir"]),
        0x215F48: h.recorder("music_playLevel"),
        0x1EC0E0: h.recorder("timer"),
        0x211338: h.recorder("stream_queueStop"),
    })
    bad = []
    block = e.alloc(0x50 * 10)
    try:
        for case in range(CASES):
            r1c = rng.choice((0, 0, 0, 1, 0x80))
            r1e = rng.choice((0, 0, 0, 1, 0xFF))
            if rng.random() < 0.1:
                names = None
            else:
                names = [rng.choice(SYN_NAMES) for _ in range(rng.randrange(0, 8))]
                if rng.random() < 0.3 and names:
                    names.insert(rng.randrange(len(names)), "")
            seed = rng.getrandbits(32)
            rand_seed = rng.getrandbits(32)
            e.mem.write(block, bytes(0x50 * 10))
            if names is not None:
                for i, n in enumerate(names):
                    e.mem.write(block + 0x50 * i, n.encode() + b"\0")
            state["dir"] = 0 if names is None else block
            e.mem.w8(RECALL_RETURN, r1c)
            e.mem.w8(RECALL_OUT, r1e)
            e.mem.w32(G_COSMETIC_SEED, seed)
            e.mem.w32(G_RAND_SEED, rand_seed)
            h.fresh()
            e.r[2] = e.alloc(16)
            e.mem.w32(e.r[2] + 4, 0x1234)
            e.r[17] = e.alloc(16)
            reason = h.slice(0x1E59A4, (0x1E5A8C, 0x1E5A90))
            got = []
            for name, ints, _ in h.log:
                if name == "music_playLevel":
                    got.append((name, (ints[0] - block) // 0x50, ints[1]))
                elif name in ("timer", "stream_queueStop"):
                    got.append((name, ints[0]))
            want, want_seed = S.level_entry(r1c, r1e, names, rand_seed)
            if reason != "stop" or got != want or e.mem.u32(G_COSMETIC_SEED) != want_seed:
                bad.append((r1c, r1e, names, got, want))
    finally:
        h.unstub(addrs)
        e.mem.w8(RECALL_RETURN, 0)
        e.mem.w8(RECALL_OUT, 0)
    check("level entry", not bad, "%d cases (recall bytes, synthetic directories, seed); mismatches %s"
          % (CASES, bad[:3]))


def test_session_countdown(h, rng):
    """mainloop_runSession 0x322d94-0x322db8. No callee runs inside the slice."""
    e = h.emu
    bad = []
    for case in range(CASES):
        r1c = rng.choice((0, 0, 1, 0x80))
        r1e = rng.choice((0, 0, 1, 0xFF))
        old = rng.getrandbits(32)
        e.mem.w8(RECALL_RETURN, r1c)
        e.mem.w8(RECALL_OUT, r1e)
        e.mem.w32(COUNTDOWN, old)
        h.fresh()
        reason = h.slice(0x322D94, (0x322DB8,))
        got = e.mem.u32(COUNTDOWN)
        if reason != "stop" or got != S.session_countdown(r1c, r1e, old) or h.emu.calls:
            bad.append((r1c, r1e, hex(old), hex(got)))
    e.mem.w8(RECALL_RETURN, 0)
    e.mem.w8(RECALL_OUT, 0)
    check("session countdown", not bad, "%d cases; mismatches %s" % (CASES, bad[:3]))


def test_pvp_music(h, rng):
    """game_loadLevel 0x1e5e00-0x1e5e58. Stub: music_playGlobal 0x2110e0 (recorded).
    Register $22 is the caller's 0x4f0000 base."""
    e = h.emu
    addrs = h.stubs({0x2110E0: h.recorder("music_playGlobal", strings=(0,))})
    bad = []
    seen = set()
    try:
        for case in range(CASES):
            mode = rng.choice((0, 1, 2, 0x80000000))
            seed = rng.getrandbits(32)
            e.mem.w32(PVP_MODE_B, mode)
            e.mem.w32(G_COSMETIC_SEED, seed)
            h.fresh()
            e.r[22] = 0x4F0000
            reason = h.slice(0x1E5E00, (0x1E5E58,))
            got = [(n, ints[0], ints[1]) for n, ints, _ in h.log]
            want, want_seed = S.pvp_music(mode, seed)
            seen.update(c[1] for c in got)
            if reason != "stop" or got != want or e.mem.u32(G_COSMETIC_SEED) != want_seed:
                bad.append((mode, hex(seed), got, want))
    finally:
        h.unstub(addrs)
        e.mem.w32(PVP_MODE_B, 0)
    check("pvp music", not bad and len(seen) == len(S.PVP_TRACKS),
          "%d cases, %d distinct tracks; mismatches %s" % (CASES, len(seen), bad[:3]))


# ---- options sliders ----------------------------------------------------------------------
def test_slider_preview(h, rng, screen):
    """Stubs: lump_get 0x17365c, sound_playOnObject 0x214230, audio_streamStatus 0x211b20
    (returns the case's stream-2 status), music_playGlobal 0x2110e0, stream_queueStop
    0x211338, and in the front end music_applyVolume 0x215e78 and audio_sendVolumes
    0x2166e0 (all recorded)."""
    e = h.emu
    state = {"status": 0}
    table = {
        0x17365C: h.recorder("lump_get", ret=0x1234560),
        0x214230: h.recorder("sound_playOnObject", floats=1),
        0x211B20: h.recorder("status", ret=lambda _e: state["status"]),
        0x2110E0: h.recorder("music_playGlobal", strings=(0,)),
        0x211338: h.recorder("stream_queueStop"),
    }
    if screen == "front":
        table[0x215E78] = h.recorder("music_applyVolume")
        table[0x2166E0] = h.recorder("audio_sendVolumes")
    addrs = h.stubs(table)
    timer_addr = PAUSE_TIMER if screen == "pause" else FRONT_TIMER
    values = (0, 0x3F000000, 0x3F800000, 0x3D4CCCCC, 0x3C088888, 0x80000000, 0x3E4CCCCD)
    bad = []
    fades = previews = 0
    try:
        for case in range(CASES):
            entry_old, entry_new = rng.choice(values), rng.choice(values)
            music_old = rng.choice(values)
            music_new = music_old if rng.random() < 0.4 else rng.choice(values)
            status = rng.choice((0, 0x20, 0x40, 0x61, 0x21, 1))
            timer = rng.choice((0, 1, 119, 120, 121, 239, 240, 241, 5000, 0x7FFFFFFF, 0xFFFFFFFF))
            draw = rng.getrandbits(32)
            state["status"] = status
            e.mem.w32(timer_addr, timer)
            e.mem.w32(G_DRAW_FRAME, draw)
            e.mem.w32(G_MUSIC, music_new)
            h.fresh()
            if screen == "pause":
                cell = e.alloc(16)
                e.mem.w32(cell, entry_new)
                e.r[16], e.r[23] = cell, 0x500000
                e.f[20], e.f[21] = entry_old, music_old
                reason = h.slice(0x18D728, (0x18D7E8,))
            else:
                e.mem.w32(G_SFX, entry_new)
                e.r[16], e.r[19], e.r[21], e.r[23] = 0x500000, 0x500000, 0x4F0000, 0x450000
                e.f[20], e.f[21] = entry_old, music_old
                reason = h.slice(0x1E1048, (0x1E1110, 0x1E1114))
            got = []
            for name, ints, fl in h.log:
                if name == "sound_playOnObject":
                    got.append((name, fl[0], ints[1]))
                elif name == "music_playGlobal":
                    got.append((name, ints[0], ints[1]))
                elif name in ("status", "stream_queueStop"):
                    got.append((name, ints[0]))
                else:
                    got.append((name,))
            want, want_timer = S.slider_preview(screen, entry_old, entry_new, music_old, music_new,
                                                status, timer, draw)
            fades += any(c[0] == "stream_queueStop" for c in got)
            previews += any(c[0] == "music_playGlobal" for c in got)
            if reason != "stop" or got != want or e.mem.u32(timer_addr) != want_timer:
                bad.append((hex(entry_old), hex(entry_new), hex(music_old), hex(music_new),
                            hex(status), timer, got, want))
    finally:
        h.unstub(addrs)
    check("%s preview" % screen, not bad,
          "%d cases (%d previews, %d fade-stops); mismatches %s" % (CASES, previews, fades, bad[:2]))


# ---- voices -------------------------------------------------------------------------------
def level_names(e):
    names = []
    for row in range(91):
        ptr = e.mem.u32(LEVEL_TABLE + 0x30 * row)
        if ptr:
            names.append(e.mem.cstr(ptr, 32))
    return names


def test_player_voice(h, rng):
    """player_voice 0x1b7ba8, whole function. Stubs: net_isLocalSlot 0x13e150 (case value),
    stream_activeFlags 0x216388 (case value for stream 1) and
    stream_playGlobalRandom 0x2160c0 (recorded). sprintf and the string compares run.
    Kind 2 is run with every g_levelTable name in the string at 0x41b721."""
    e = h.emu
    state = {"local": 1, "status": 0}
    addrs = h.stubs({
        0x13E150: h.recorder("isLocal", ret=lambda _e: state["local"]),
        0x216388: h.recorder("status", ret=lambda _e: state["status"]),
        0x2160C0: h.recorder("playGlobalRandom", strings=(1,)),
    })
    levels = level_names(e)
    bad = []
    played = set()
    try:
        cases = [(m, k) for m in range(12) for k in range(20)] * 2
        cases += [(rng.randrange(12), rng.randrange(-2, 24)) for _ in range(CASES * 2)]
        for model, kind in cases:
            slot = rng.randrange(4)
            local = rng.choice((1, 1, 1, 0))
            cut = rng.choice((0, 0, 0, 0, 1))
            net = rng.choice((0, 1))
            menu = rng.choice((0, 0, 0, 1))
            status = rng.choice((0, 0, 0, 0x20, 0x21, 1))
            hp = rng.choice((0x3F800000, 0x42C80000, 0, 0x80000000, 0xBF800000, 0x7FC00000,
                             0x3F800000, 0x42C80000))
            seed = rng.getrandbits(32)
            rec = PLAYERS + slot * PLAYER_STRIDE
            e.mem.w32(rec + 0x54, model)
            e.mem.w32(rec + 0xAC, hp)
            e.mem.w8(CUTSCENE_BYTE, cut)
            e.mem.w8(NET_BYTE, net)
            e.mem.w8(MENU_BYTE, menu)
            e.mem.write(VOICE_NAME, rng.choice(levels).encode() + b"\0")
            e.mem.w32(G_COSMETIC_SEED, seed)
            state["local"], state["status"] = local, status
            h.call(0x1B7BA8, slot, kind & 0xFFFFFFFF)
            got = []
            for name, ints, _ in h.log:
                if name == "isLocal":
                    got.append((name,))
                elif name == "status":
                    got.append((name, ints[0]))
                else:
                    got.append((name, ints[0], ints[1], ints[2]))
                    played.add(ints[1])
            want, want_seed = S.player_voice(model, kind, local, cut, net, menu, status, hp, seed)
            if got != want or e.mem.u32(G_COSMETIC_SEED) != want_seed:
                bad.append((model, kind, slot, local, cut, net, menu, hex(status), hex(hp), got, want))
    finally:
        h.unstub(addrs)
        e.mem.w8(NET_BYTE, e.mem.u8(NET_BYTE))
    check("player voice", not bad, "%d calls over models 0-11 and kinds -2..23, %d distinct lines, "
          "%d level names for kind 2; mismatches %s" % (len(cases), len(played), len(levels), bad[:2]))


# ---- foley and hits -----------------------------------------------------------------------
def test_foley(h, rng):
    """sound_playFoley 0x1e7c40, whole function. Stubs: lump_get 0x17365c (records lump and
    sequence names, returns a handle) and sound_playAtPos 0x214428 (recorded)."""
    e = h.emu
    addrs = h.stubs({
        0x17365C: h.recorder("lump_get", strings=(0, 1), ret=0x1234560),
        0x214428: h.recorder("sound_playAtPos", floats=1,
                             ret=lambda emu: h.pos_bytes.append(emu.mem.read(emu.r[5] & 0xFFFFFFFF, 12)) or 0),
    })
    pos = e.alloc(16)
    e.mem.write(pos, struct.pack("<3f", 1.5, -2.25, 40.0))
    bad = []
    names = set()
    bits = (0, 0x80000, 0x100000, 0x200000, 0x400000, 0x800000, 0x40000, 0x1000000)
    try:
        for case in range(CASES * 2):
            water = rng.choice((0, 0, 1))
            flags = 0
            for b in bits:
                if rng.random() < 0.3:
                    flags |= b
            if rng.random() < 0.1:
                flags = rng.getrandbits(32)
            seed = rng.getrandbits(32)
            e.mem.w32(G_COSMETIC_SEED, seed)
            h.call(0x1E7C40, pos, water, 0, flags)
            name, want_seed = S.foley(water, flags, seed)
            want = [] if name is None else [
                ("lump_get", S.FOLEY_LUMP, name),
                ("sound_playAtPos", S.FLOAT_ONE, 0x1234560, e.mem.read(pos, 12))]
            got = []
            for n, ints, fl in h.log:
                if n == "lump_get":
                    got.append((n, ints[0], ints[1]))
                else:
                    got.append((n, fl[0], ints[0], h.pos_bytes.pop(0)))
            names.update(c[2] for c in got if c[0] == "lump_get")
            if got != want or e.mem.u32(G_COSMETIC_SEED) != want_seed:
                bad.append((water, hex(flags), got, want))
    finally:
        h.unstub(addrs)
    check("foley", not bad, "%d cases, %d distinct sequences; mismatches %s" % (CASES * 2, len(names), bad[:2]))


def test_hit(h, rng):
    """sound_playHit 0x1e7e40, whole function. Stubs: lump_get 0x17365c and
    sound_playOnObject 0x214230 (recorded). A player victim's sound follows the
    object word at record +0x43d8. Amount and maximum hit points are chosen so the
    quotient is exact or far from 0.25 and 0x3f199999 in every rounding model."""
    e = h.emu
    addrs = h.stubs({
        0x17365C: h.recorder("lump_get", strings=(0, 1), ret=0x1234560),
        0x214230: h.recorder("sound_playOnObject", floats=1),
    })
    victim = e.alloc(0x400)
    items = [e.alloc(0x20) for _ in range(4)]
    bad = []
    names = set()
    pairs = [(10.0, 100.0), (25.0, 100.0), (30.0, 100.0), (59.0, 100.0), (61.0, 100.0),
             (70.0, 100.0), (1.0, 8.0), (2.0, 8.0), (4.0, 8.0), (5.0, 8.0), (300.0, 100.0),
             (1.0, 1.0), (0.5, 4.0), (3.0, 4.0)]
    try:
        for case in range(CASES * 2):
            is_player = rng.choice((0, 1))
            slot = rng.randrange(4)
            cflags = 0
            for b in range(30, 44):
                if rng.random() < 0.15:
                    cflags |= 1 << b
            armour = None
            rec = PLAYERS + slot * PLAYER_STRIDE
            if rng.random() < 0.15:
                e.mem.w32(rec + 0x4400, 0)
            else:
                armour = 0
                for b in (0x80000, 0x100000, 0x200000, 0x400000, 0x800000, 0x40000):
                    if rng.random() < 0.3:
                        armour |= b
                e.mem.w32(rec + 0x4400, items[slot])
                e.mem.w64(items[slot] + 8, armour)
            dmg = 0
            for b in (1, 2, 4, 8, 0x10, 0x100, 0x4000, 0x8000, 0x10000):
                if rng.random() < (0.12 if b in (0x4000, 0x8000) else 0.3):
                    dmg |= b
            landed = rng.choice((0, 1, 1))
            amount, max_hp = rng.choice(pairs)
            e.mem.w64(victim + 0xA8, cflags)
            e.mem.w32(victim + 0x22C, f32(max_hp))
            e.mem.w32(rec + 0xB0, f32(max_hp))
            obj_word = 0x2000000 + slot
            e.mem.w32(rec + 0x43D8, obj_word)
            h.call(0x1E7E40, is_player, victim, slot, dmg, landed, fargs=(amount,))
            name = S.hit_name(is_player, cflags, armour, dmg, landed, f32(amount), f32(max_hp))
            target = obj_word if is_player else victim
            want = [] if name is None else [
                ("lump_get", S.HIT_LUMP, name), ("sound_playOnObject", S.FLOAT_ONE, 0x1234560, target)]
            got = []
            for n, ints, fl in h.log:
                if n == "lump_get":
                    got.append((n, ints[0], ints[1]))
                else:
                    got.append((n, fl[0], ints[0], ints[1]))
            names.update(c[2] for c in got if c[0] == "lump_get")
            if got != want:
                bad.append((is_player, hex(cflags), armour, hex(dmg), landed, amount, max_hp, got, want))
    finally:
        h.unstub(addrs)
    check("hit name", not bad, "%d cases, %d distinct sequences; mismatches %s" % (CASES * 2, len(names), bad[:2]))


# ---- sound_update order and channel volumes -----------------------------------------------
UPDATE_TARGETS = {
    0x212500: "music_updateDucking", 0x212340: "sound_pauseResumeVoices",
    0x211DF8: "stream_serviceQueues", 0x2147C0: "soundSeq_updateAll",
    0x2149D0: "ambient_update", 0x210CD0: "sound_flushSpuCommands", 0x35EE38: "endFlags",
    0x216690: "audio_setChannelVolume", 0x2166E0: "audio_sendVolumes",
}


def test_update_order(h, rng):
    """sound_update 0x212670 with every callee auto-stubbed (returns 0) and recorded.
    Stream 0's current and queued flags are written into g_streams for the 0x20 test."""
    e = h.emu
    e.follow = {0x212670}
    e.default_ret = 0
    bad = []
    try:
        for case in range(CASES):
            frame = rng.getrandbits(32) if rng.random() < 0.5 else rng.randrange(64)
            active = rng.choice((0, 1))
            cur = rng.choice((0, 3, 8, 0x20, 0x22, 0x80))
            queued = [rng.choice((0, 3, 0x20, 0x122, 8)) for _ in range(rng.randrange(0, 4))]
            e.mem.w32(G_STREAMS + 0x14, active)
            e.mem.w32(G_STREAMS + 0x20, cur)
            e.mem.w32(G_STREAMS + 0x1C0, len(queued))
            for i, f in enumerate(queued):
                e.mem.w32(G_STREAMS + 0x40 + 0x30 * i + 0x2C, f)
            e.mem.w32(G_SOUND_FRAME, frame)
            h.call(0x212670)
            got = [UPDATE_TARGETS.get(c.target, "%x" % c.target) for c in e.calls]
            music0 = bool(((cur if active else 0) | sum_or(queued)) & 0x20)
            want = S.update_order(frame, music0)
            if got != want or e.mem.u32(G_SOUND_FRAME) != (frame + 1) & 0xFFFFFFFF:
                bad.append((hex(frame), active, hex(cur), queued, got, want))
    finally:
        e.follow = None
        e.mem.w32(G_STREAMS + 0x14, 0)
        e.mem.w32(G_STREAMS + 0x20, 0)
        e.mem.w32(G_STREAMS + 0x1C0, 0)
    check("update order", not bad, "%d frames; music_updateDucking is the first callee; mismatches %s"
          % (CASES, bad[:2]))


def sum_or(values):
    out = 0
    for v in values:
        out |= v
    return out


VOLUMES = (0, 0x3F800000, 0x3F000000, 0x3D4CCCCC, 0x3E99999A, 0x3F160000, 0x3F200000,
           0x3F7FFFFF, 0x3FC00000, 0xBF800000, 0x80000000, 0x3C088888)


def test_channel_volumes(h, rng):
    """audio_setChannelVolume 0x216690 and audio_sendVolumes 0x2166e0 run; the RPC call
    0x3566f0 is stubbed and recorded, and the 16 sent bytes are read from 0x877200.
    music_applyVolume 0x215e78 runs with audio_streamStatus 0x211b20 stubbed. The
    sound_update slice 0x2127f0-0x212878 runs with audio_setChannelVolume stubbed."""
    e = h.emu
    state = {"status": 0}
    rpcs = []

    def rpc(emu):
        rpcs.append(tuple(emu.r[4 + i] & 0xFFFFFFFF for i in range(8)))
        return 0
    addrs = h.stubs({0x3566F0: rpc})
    bad = []
    try:
        image = [e.mem.u32(CHANNELS + 4 * i) for i in range(3)]
        for case in range(CASES):
            ch = rng.randrange(3)
            stored = [rng.choice(VOLUMES[:8]) for _ in range(3)]
            value = rng.choice(VOLUMES) if rng.random() < 0.8 else stored[ch]
            stereo = rng.choice((0, 1, 2))
            for i in range(3):
                e.mem.w32(CHANNELS + 4 * i, stored[i])
            e.mem.w32(G_STEREO, stereo)
            rpcs.clear()
            h.call(0x216690, ch, fargs=(struct.unpack("<f", struct.pack("<I", value))[0],))
            # the float argument goes in as a raw pattern
            new, sent = S.set_channel_volume(stored[ch], value)
            got_store = e.mem.u32(CHANNELS + 4 * ch)
            want_store = new
            chans = list(stored)
            chans[ch] = new
            want_payload = S.send_volumes_payload(stereo, chans)
            got_payload = tuple(e.mem.u32(RPC_SEND + 4 * i) for i in range(4))
            got_rpc = [r[1] for r in rpcs]
            ok = got_store == want_store and got_rpc == ([0x80] if sent else [])
            if sent:
                ok = ok and got_payload == want_payload and rpcs[0][3:7] == (RPC_SEND, 0x10, 0x8771C0, 0x40)
            if not ok:
                bad.append((ch, [hex(s) for s in stored], hex(value), hex(got_store), hex(want_store),
                            got_rpc, got_payload, want_payload))
    finally:
        h.unstub(addrs)
    check("channel volumes", not bad, "%d cases; image channels %s; mismatches %s"
          % (CASES, [hex(v) for v in image], bad[:2]))

    addrs = h.stubs({
        0x211B20: h.recorder("status", ret=lambda _e: state["status"]),
        0x216690: h.recorder("setChannel", floats=1),
    })
    bad = []
    try:
        for case in range(CASES):
            duck = rng.choice(VOLUMES[:8])
            music = rng.choice(VOLUMES[:8])
            status = rng.choice((0, 0x20, 0x21, 0x40, 1))
            state["status"] = status
            e.mem.w32(G_DUCK, duck)
            e.mem.w32(G_MUSIC, music)
            h.call(0x215E78)
            got = [(n, ints[0], fl[0]) if n == "setChannel" else (n, ints[0]) for n, ints, fl in h.log]
            want = [("status", 2)]
            if status & 0x20:
                want.append(("setChannel", 2, S.music_channel_volume(duck, music)))
            if got != want:
                bad.append((hex(duck), hex(music), hex(status), got, want))
        for case in range(CASES):
            music = rng.choice(VOLUMES[:9])
            active = rng.choice((0, 1))
            cur = rng.choice((0, 3, 8, 0x20, 0x80))
            queued = [rng.choice((0, 3, 0x20, 8)) for _ in range(rng.randrange(0, 4))]
            e.mem.w32(G_STREAMS + 0x14, active)
            e.mem.w32(G_STREAMS + 0x20, cur)
            e.mem.w32(G_STREAMS + 0x1C0, len(queued))
            for i, f in enumerate(queued):
                e.mem.w32(G_STREAMS + 0x40 + 0x30 * i + 0x2C, f)
            e.mem.w32(G_MUSIC, music)
            h.fresh()
            reason = h.slice(0x2127F0, (0x212878,))
            got = [(ints[0], fl[0]) for n, ints, fl in h.log]
            music0 = ((cur if active else 0) | sum_or(queued)) & 0x20
            want = [] if music0 else [(0, S.channel0_volume(music))]
            if reason != "stop" or got != want:
                bad.append((hex(music), active, hex(cur), queued, got, want))
    finally:
        h.unstub(addrs)
        e.mem.w32(G_STREAMS + 0x14, 0)
        e.mem.w32(G_STREAMS + 0x20, 0)
        e.mem.w32(G_STREAMS + 0x1C0, 0)
    check("music and stream-0 volume", not bad, "%d + %d cases; mismatches %s" % (CASES, CASES, bad[:2]))


def test_option_defaults(h):
    """config_setDefaults(-1) 0x1e6238 with every callee auto-stubbed and recorded."""
    e = h.emu
    e.follow = {0x1E6238}
    e.default_ret = 0
    try:
        before = {k: e.mem.u32(a) for k, a in S.OPTION_IMAGE.items()}
        h.call(0x1E6238, (1 << 64) - 1)
        last = {}
        for pc, addr, size, value in e.writes:
            last[addr] = value
        got = {k: last.get(a) for k, a in S.OPTION_IMAGE.items()}
        saved = {k: last.get(a) for k, a in S.OPTION_SAVED.items()}
        calls = [c.target for c in e.calls]
    finally:
        e.follow = None
        for k, a in S.OPTION_IMAGE.items():
            e.mem.w32(a, before[k])
    ok = got == S.OPTION_DEFAULTS and saved == S.OPTION_DEFAULTS and calls == [0x215E78]
    check("option defaults", ok, "image %s, stored %s, saved copy %s, callees %s"
          % ({k: hex(v) for k, v in before.items()}, {k: hex(v) for k, v in got.items() if v is not None},
             {k: hex(v) for k, v in saved.items() if v is not None}, ["%x" % c for c in calls]))


def test_image(h):
    """Static image words read from the executable: the PvP table, the recall bytes and the
    level-table names used by the voice property. Read only."""
    e = h.emu
    table = tuple(e.mem.cstr(e.mem.u32(0x4F8320 + 4 * i), 40) for i in range(11))
    strings = (e.mem.cstr(0x53DAB0, 16), e.mem.cstr(0x534A60, 32), e.mem.cstr(0x53CE20, 32),
               e.mem.cstr(0x53CFC0, 40))
    ok = (table == S.PVP_TRACKS and e.mem.u32(0x4F8320 + 44) == 0
          and strings == (S.ENTRY_TAG, S.PAUSE_PREVIEW[0], S.FRONT_PREVIEW[0], "mx_endcredits_ext_l.vag")
          and e.mem.u8(RECALL_RETURN) == 0 and e.mem.u8(RECALL_OUT) == 0
          and len(level_names(e)) == 90)
    check("image", ok, "PvP table of %d names, entry tag, preview and credits names, recall bytes 0, "
          "90 level names" % len(table))


def find_elf(argv):
    candidates = [a for a in argv if not a.startswith("-")]
    env = os.environ.get("CHAMPIONS_ELF")
    if env:
        candidates.append(env)
    candidates += [os.path.join(ROOT, "SLUS_209.73"), os.path.join(ROOT, "local", "SLUS_209.73"),
                   "SLUS_209.73"]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def main(argv=None):
    global FILTER, CASES
    argv = list(sys.argv[1:] if argv is None else argv)
    args = []
    seed = 20973
    while argv:
        item = argv.pop(0)
        if item == "-k" and argv:
            FILTER = argv.pop(0)
        elif item == "--seed" and argv:
            seed = int(argv.pop(0), 0)
        elif item == "--cases" and argv:
            CASES = int(argv.pop(0), 0)
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
    print("seed %d, %d cases per property" % (seed, CASES))
    try:
        harness = Harness(elf)
    except EmuError as exc:
        say("FAIL", "setup", str(exc))
        return 1
    rng = random.Random(seed)
    properties = (
        ("image", lambda: test_image(harness)),
        ("option defaults", lambda: test_option_defaults(harness)),
        ("level entry", lambda: test_level_entry(harness, rng)),
        ("session countdown", lambda: test_session_countdown(harness, rng)),
        ("pvp music", lambda: test_pvp_music(harness, rng)),
        ("pause preview", lambda: test_slider_preview(harness, rng, "pause")),
        ("front preview", lambda: test_slider_preview(harness, rng, "front")),
        ("player voice", lambda: test_player_voice(harness, rng)),
        ("foley", lambda: test_foley(harness, rng)),
        ("hit name", lambda: test_hit(harness, rng)),
        ("update order", lambda: test_update_order(harness, rng)),
        ("channel volumes", lambda: test_channel_volumes(harness, rng)),
    )
    for name, prop in properties:
        if FILTER and FILTER not in name and not (name == "channel volumes" and "volume" in FILTER):
            continue
        try:
            prop()
        except EmuError as exc:
            say("FAIL", name, str(exc))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
