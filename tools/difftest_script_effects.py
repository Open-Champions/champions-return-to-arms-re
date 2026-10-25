#!/usr/bin/env python3
"""difftest_script_effects.py - script callees against tools/ref_script_effects.py.

Needs your own SLUS_209.73 (US v2.00). Without it nothing is run and the exit
status is 0.

  python3 tools/difftest_script_effects.py [SLUS_209.73] [--cases N] [--no-handlers]

The original functions run in tools/ee_emu.py. For each case the result, the
calls and the bytes stored must match the reference, and neither seed
(0x404464 shared, 0x404460 cosmetic) may move. --cases is how many random
handler states tools/difftest_natives.py re-runs for these commands (default 4).
"""
import hashlib
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ee_emu                                # noqa: E402
import ref_natives as N                      # noqa: E402
import ref_script_effects as E               # noqa: E402
import difftest_natives as D                 # noqa: E402

M32 = 0xFFFFFFFF
SEED, COSMETIC = 0x12345678, 0x11111111
PRIVATE = os.environ.get('CHAMPIONS_ELF', '')


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def low(value):
    return value & M32


class Case:
    """One original call and the reference that should agree with it."""

    def __init__(self, elf):
        self.ee = ee_emu.EE(elf)
        self.ee.follow = set()
        self.ee.mem.w32(0x404464, SEED)
        self.ee.mem.w32(0x404460, COSMETIC)
        self.mem = N.Mem(under=self.ee.mem)
        self.trace = E.Trace()
        self.errors = []

    def poke(self, addr, size, value):
        self.ee.mem.store(addr, size, value)

    def stub(self, addr, name, ret=0):
        def run(emu, fn=ret):
            if callable(fn):
                value = fn(emu.r[4] & M32, emu.r[5] & M32, emu.r[6] & M32, emu.r[7] & M32)
            else:
                value = fn
            return value
        self.ee.stub(addr, function=run, name=name)
        self.trace.returns[name] = (ret if not callable(ret) else (lambda *args: ret(args[0], *args[1:])))

    def ret(self, name, value):
        """A constant return for a stub installed with stub()."""
        self.trace.returns[name] = value

    def follow(self, addr, name):
        self.ee.follow.add(addr)
        self.ee.stub_names[addr] = name

    def run(self, addr, args, fargs=(), expect=None, ignore=()):
        model_bytes = {}
        for at, size in self.mem.writes:
            data = self.mem.read(at, size)
            for index, byte in enumerate(data):
                model_bytes[(at + index) & M32] = byte
        model_calls = list(self.trace.calls)
        self.ee.r[2] = 0xABCDE
        self.ee.reset_log()
        got = self.ee.call(addr, *args, fargs=fargs)
        if self.ee.mem.u32(0x404464) != SEED or self.ee.mem.u32(0x404460) != COSMETIC:
            self.errors.append('seed moved')
        if expect is not None and low(got) != low(expect):
            self.errors.append('v0 0x%x != 0x%x' % (low(got), low(expect)))
        original = {}
        for _pc, at, size, _value in self.ee.writes:
            if 0x01F00000 <= at < 0x02000000:
                continue
            for index in range(size):
                addr = (at + index) & M32
                original[addr] = self.ee.mem.u8(addr)
        for addr in sorted(set(model_bytes) | set(original)):
            if model_bytes.get(addr) != original.get(addr):
                self.errors.append('byte 0x%x model %s original %s' % (
                    addr, model_bytes.get(addr), original.get(addr)))
        got_calls = [rec for rec in self.ee.calls if rec.name and rec.target not in ignore]
        if len(got_calls) != len(model_calls):
            self.errors.append('calls %s != %s' % (
                [(rec.name, [hex(a & M32) for a in rec.args[:4]]) for rec in got_calls],
                [(name, [hex(a) for a in args_]) for name, args_, _f in model_calls]))
        else:
            for (name, args_, fargs_), rec in zip(model_calls, got_calls):
                if rec.name != name:
                    self.errors.append('call %s != %s' % (rec.name, name))
                    break
                for index, arg in enumerate(args_):
                    if arg is None or isinstance(arg, tuple):
                        continue
                    if low(rec.args[index]) != low(arg):
                        self.errors.append('%s arg %d 0x%x != 0x%x' % (
                            name, index, low(rec.args[index]), low(arg)))
                        break
                for index, pat in enumerate(fargs_):
                    if low(rec.fargs[index]) != low(pat):
                        self.errors.append('%s farg %d 0x%x != 0x%x' % (
                            name, index, low(rec.fargs[index]), low(pat)))
                        break
        return got


def _creature(case, flags=0x20):
    creature = case.ee.alloc(0x400)
    case.poke(creature + 0xC, 4, flags)
    return creature


def _open_hud(case):
    camera = case.ee.alloc(0x40)
    case.poke(E.G_CAMERA, 4, camera)
    case.poke(camera + 0x34, 4, 1)
    for addr in (E.G_HUD_SUPPRESSED, E.G_LOCAL_MENU, E.G_LOADSCREEN):
        case.poke(addr, 1, 0)
    case.poke(N.G_MENU_OPEN_FLAG, 4, 0)
    return camera


def test_scale(elf):
    errors = []
    specs = (
        ((100.0, 200.0, 10, 4, 6, 8, 3.5), (0.5, 2.0, 0.25, 1.5, 0.0)),
        ((100.5, 1.0, 1, 1, 3, 1, 2.0), (0.5, 0.1, 0.1, -1.0, 0.25)),
    )
    for (hp, mx, arm, d0, d2, d4, xp), scales in specs:
        case = Case(elf)
        creature = _creature(case)
        case.poke(creature + 0x228, 4, f32(hp))
        case.poke(creature + 0x22C, 4, f32(mx))
        case.poke(creature + 0xE4, 2, arm)
        case.poke(creature + 0xD0, 2, d0)
        case.poke(creature + 0xD2, 2, d2)
        case.poke(creature + 0xD4, 2, d4 & 0xFFFF)
        case.poke(creature + 0xD8, 4, f32(xp))
        result = E.scale_stats(case.mem, creature, tuple(f32(s) for s in scales))
        case.run(0x1185D8, (creature,), fargs=scales, expect=result)
        errors.extend('scale %s: %s' % (scales, item) for item in case.errors)
    return errors


def test_charm(elf):
    errors = []
    # permanent charm refuses
    case = Case(elf)
    creature = _creature(case)
    case.poke(creature + 0x312, 2, 0xFFFF)
    case.poke(creature + 0x310, 1, 9)
    case.stub(0x1A1698, 'handle_clear', 7)
    E.set_charm(case.mem, case.trace, creature, 5, 1)
    case.run(0x1189F0, (creature, 5, 1), expect=0xFFFFFFFF)
    errors.extend('charm permanent: ' + item for item in case.errors)
    # a player
    case = Case(elf)
    creature = _creature(case, 0x60)
    case.poke(creature + 0x312, 2, 3)
    case.stub(0x1A1698, 'handle_clear', 7)
    E.set_charm(case.mem, case.trace, creature, 5, 1)
    case.run(0x1189F0, (creature, 5, 1), expect=0x20)
    errors.extend('charm player: ' + item for item in case.errors)
    # not a creature
    case = Case(elf)
    creature = _creature(case, 0)
    case.poke(creature + 0x312, 2, 3)
    case.stub(0x1A1698, 'handle_clear', 7)
    E.set_charm(case.mem, case.trace, creature, 5, 1)
    case.run(0x1189F0, (creature, 5, 1), expect=0)
    errors.extend('charm plain: ' + item for item in case.errors)
    # a creature accepts -1 frames and team 3
    case = Case(elf)
    creature = _creature(case)
    case.poke(creature + 0x312, 2, 10)
    case.poke(creature + 0x234, 4, 0x44)
    case.stub(0x1A1698, 'handle_clear', 7)
    E.set_charm(case.mem, case.trace, creature, 0xFFFFFFFF, 3)
    case.run(0x1189F0, (creature, 0xFFFFFFFF, 3), expect=7)
    errors.extend('charm ok: ' + item for item in case.errors)
    return errors


def test_slots(elf):
    errors = []
    case = Case(elf)
    creature = _creature(case)
    E.slot34_set_home_range(case.mem, creature, 0x1ABCD)
    case.run(0x3C2708, (creature, 0x1ABCD), expect=0xABCDE)
    errors.extend('slot34: ' + item for item in case.errors)
    case = Case(elf)
    creature = _creature(case)
    E.slot27_set_state(case.mem, creature, 0x12345)
    case.run(0x3C2688, (creature, 0x12345), expect=0xABCDE)
    errors.extend('slot27: ' + item for item in case.errors)
    return errors


def test_message(elf):
    errors = []
    text = None
    # slot -1, menu closed
    case = Case(elf)
    text = case.ee.alloc(16)
    case.poke(E.G_LOCAL_MENU, 1, 0)
    case.stub(0x13E150, 'net_isLocalSlot', 1)
    case.stub(0x19E854, 'wstr_copy', 4)
    E.show_message(case.mem, case.trace, text, 180, -1, 0)
    case.run(0x1D92A0, (text, 180, -1, 0), expect=0x4F0000)
    errors.extend('message: ' + item for item in case.errors)
    # menu open, force 0
    case = Case(elf)
    text = case.ee.alloc(16)
    case.poke(E.G_LOCAL_MENU, 1, 1)
    case.stub(0x13E150, 'net_isLocalSlot', 1)
    case.stub(0x19E854, 'wstr_copy', 4)
    E.show_message(case.mem, case.trace, text, 180, -1, 0)
    case.run(0x1D92A0, (text, 180, -1, 0), expect=1)
    errors.extend('message menu: ' + item for item in case.errors)
    # remote slot
    case = Case(elf)
    text = case.ee.alloc(16)
    case.stub(0x13E150, 'net_isLocalSlot', 0)
    case.stub(0x19E854, 'wstr_copy', 4)
    E.show_message(case.mem, case.trace, text, 90, 2, 1)
    case.run(0x1D92A0, (text, 90, 2, 1), expect=0)
    errors.extend('message remote: ' + item for item in case.errors)
    # forced while the menu is open
    case = Case(elf)
    text = case.ee.alloc(16)
    case.poke(E.G_LOCAL_MENU, 1, 1)
    case.stub(0x13E150, 'net_isLocalSlot', 1)
    case.stub(0x19E854, 'wstr_copy', 4)
    E.show_message(case.mem, case.trace, text, 90, 2, 1)
    case.run(0x1D92A0, (text, 90, 2, 1), expect=0x4F0000)
    errors.extend('message force: ' + item for item in case.errors)
    return errors


def test_help(elf):
    errors = []
    def one(label, slot, network, alive, local_ret, expect):
        case = Case(elf)
        title, body = case.ee.alloc(4), case.ee.alloc(4)
        case.poke(N.G_NETWORK_MODE, 1, network)
        case.poke(N.G_ALIVE_COUNT, 4, len(alive))
        for index, live in enumerate(alive):
            case.poke(N.G_ALIVE_LIST + 4 * index, 4, live)
        case.stub(0x13E150, 'net_isLocalSlot', local_ret)
        case.stub(0x17365C, 'res_find', 0x55)
        case.stub(0x214230, 'sound_playOnObject', 0x8001)
        case.stub(0x216AD0, 'sound_setPlaysWhileFrozen', 0)
        case.stub(0x320EA4, 'ui_startPulse', 0)
        case.stub(0x1DE0DC, 'hudmsg_sendMenuState', 0)
        result = E.show_help(case.mem, case.trace, slot, title, body)
        case.run(0x1D9830, (slot, title, body), expect=result)
        errors.extend(label + ': ' + item for item in case.errors)
    one('help offline', -1, 0, [], lambda slot, *_rest: 1, 90)
    one('help remote slot', 1, 0, [], lambda slot, *_rest: 0, 0)
    one('help net', -1, 1, [1, 0], lambda slot, *_rest: 1 if slot == 0 else 0, 90)
    one('help net none', -1, 1, [1], lambda slot, *_rest: 0, None)
    return errors


def test_fade(elf):
    errors = []
    case = Case(elf)
    E.set_fade(case.mem, 0)
    case.run(0x1DF5D0, (0,), expect=0xABCDE)
    errors.extend('fade off: ' + item for item in case.errors)
    case = Case(elf)
    E.set_fade(case.mem, 1)
    case.run(0x1DF5D0, (1,), expect=128)
    errors.extend('fade on: ' + item for item in case.errors)
    case = Case(elf)
    case.poke(0x4F66AC, 4, 40)
    case.stub(0x17BD30, 'ui_drawRect', 0)
    result = E.step_fade(case.mem, case.trace, 100)
    case.run(0x1DF5EC, (100,), expect=result)
    errors.extend('fade clamp: ' + item for item in case.errors)
    case = Case(elf)
    case.poke(0x4F66AC, 4, 128)
    case.stub(0x17BD30, 'ui_drawRect', 0)
    E.step_fade(case.mem, case.trace, -16)
    case.run(0x1DF5EC, (-16,), expect=112)
    errors.extend('fade step: ' + item for item in case.errors)
    case = Case(elf)
    case.poke(0x4F66AC, 4, 5)
    case.stub(0x17BD30, 'ui_drawRect', 0)
    E.step_fade(case.mem, case.trace, -10)
    case.run(0x1DF5EC, (-10,), expect=0)
    errors.extend('fade zero: ' + item for item in case.errors)
    return errors


def test_compass_bust(elf):
    errors = []
    case = Case(elf)
    _open_hud(case)
    case.poke(E.G_HUD_SUPPRESSED, 1, 1)
    pos = case.ee.alloc(16)
    text = case.ee.alloc(8)
    case.stub(0x19E854, 'wstr_copy', 0)
    case.stub(0x3B868C, 'strcpy', 0)
    E.set_bust(case.mem, case.trace, text, text, 3, 4)
    case.run(0x1DFAA0, (text, text, 3, 4), expect=1)
    errors.extend('bust gate: ' + item for item in case.errors)

    case = Case(elf)
    camera = _open_hud(case)
    case.poke(camera + 0x34, 4, 0)
    text = case.ee.alloc(8)
    pos = case.ee.alloc(16)
    for index, word in enumerate((f32(9.0), f32(8.0), f32(7.0), 0x99)):
        case.poke(pos + 4 * index, 4, word)
    case.stub(0x19E854, 'wstr_copy', 0)
    E.set_compass(case.mem, case.trace, (f32(9.0), f32(8.0), f32(7.0), 0x99), text)
    case.run(0x1DF668, (pos, text), expect=1)
    errors.extend('compass mode: ' + item for item in case.errors)

    case = Case(elf)
    _open_hud(case)
    case.poke(E.G_LOADSCREEN, 1, 1)
    text = case.ee.alloc(8)
    case.stub(0x19E854, 'wstr_copy', 0)
    case.stub(0x3B868C, 'strcpy', 0)
    E.set_bust(case.mem, case.trace, text, text, 3, 4)
    case.run(0x1DFAA0, (text, text, 3, 4), expect=1)
    errors.extend('bust load: ' + item for item in case.errors)

    case = Case(elf)
    _open_hud(case)
    case.poke(N.G_MENU_OPEN_FLAG, 4, 5)
    text = case.ee.alloc(8)
    case.stub(0x19E854, 'wstr_copy', 0)
    E.set_compass(case.mem, case.trace, (0, 0, 0, 0), text)
    pos = case.ee.alloc(16)
    case.run(0x1DF668, (pos, text), expect=5)
    errors.extend('compass menu flag: ' + item for item in case.errors)

    case = Case(elf)
    _open_hud(case)
    text = case.ee.alloc(8)
    pos = case.ee.alloc(16)
    words = (f32(9.0), f32(8.0), f32(7.0), 0x99)
    for index, word in enumerate(words):
        case.poke(pos + 4 * index, 4, word)
    case.stub(0x19E854, 'wstr_copy', 0)
    E.set_compass(case.mem, case.trace, words, text)
    case.run(0x1DF668, (pos, text), expect=0x870000)
    errors.extend('compass: ' + item for item in case.errors)

    case = Case(elf)
    _open_hud(case)
    text = case.ee.alloc(8)
    texture = case.ee.alloc(8)
    case.stub(0x19E854, 'wstr_copy', 0)
    case.stub(0x3B868C, 'strcpy', 0)
    E.set_bust(case.mem, case.trace, texture, text, 3, 4)
    case.run(0x1DFAA0, (texture, text, 3, 4), expect=0x870000)
    errors.extend('bust: ' + item for item in case.errors)
    return errors


def test_frozen_and_queue(elf):
    errors = []
    for handle in (0x8003, -1, 3):
        case = Case(elf)
        result = E.set_plays_while_frozen(case.mem, handle)
        case.run(0x216AD0, (handle,), expect=result)
        errors.extend('frozen 0x%x: %s' % (handle, item) for item in case.errors)
    case = Case(elf)
    count_at, _stride = E.stream_count_addr(2)
    case.poke(count_at, 4, 0)
    E.queue_stop(case.mem, 2)
    case.run(0x211338, (2,), expect=1)
    errors.extend('queue 0: ' + item for item in case.errors)
    case = Case(elf)
    count_at, _stride = E.stream_count_addr(2)
    case.poke(count_at, 4, 1)
    E.queue_stop(case.mem, 2)
    case.run(0x211338, (2,), expect=2)
    errors.extend('queue 1: ' + item for item in case.errors)
    case = Case(elf)
    case.poke(count_at, 4, 8)
    result = E.queue_stop(case.mem, 2)
    case.run(0x211338, (2,), expect=result)
    errors.extend('queue full: ' + item for item in case.errors)
    return errors


def test_music(elf):
    errors = []
    name = None
    for volume, scalar, flags, expect_open in (
            (0, 1.0, 3, False),
            (E.MUSIC_GATE, 1.0, 3, True),
            (f32(1.0), 0.5, 3, True)):
        case = Case(elf)
        if name is None:
            name = case.ee.alloc(8)
        else:
            name = case.ee.alloc(8)
        case.poke(E.G_MUSIC_VOLUME, 4, volume if volume != 0 else 0)
        case.poke(E.G_MUSIC_SCALAR, 4, f32(scalar))
        case.stub(0x216690, 'audio_setChannelVolume', 0)
        case.stub(0x215FC8, 'stream_playLevel', 0)
        E.music_play_level(case.mem, case.trace, name, flags)
        case.run(0x215F48, (name, flags), expect=0 if expect_open else 0x500000)
        errors.extend('music %s: %s' % (hex(volume), item) for item in case.errors)
    return errors


def test_boss(elf):
    errors = []
    case = Case(elf)
    case.follow(0x3B81A0, '')
    # an unnamed follow still shows up if stub_names is empty string, which is falsy.
    # Don't name strcasecmp; the matcher skips unnamed calls.
    case.ee.stub_names.pop(0x3B81A0, None)
    creature = _creature(case)
    case.poke(creature + 0x34, 4, 0)
    E.boss_music_name(case.mem, case.trace, creature)
    case.run(0x10DBE0, (creature,), expect=0)
    errors.extend('boss null: ' + item for item in case.errors)

    for type_addr, prop_addr, track in E.BOSS_ROWS:
        case = Case(elf)
        case.follow(0x3B81A0, 'strcasecmp')
        case.ee.stub_names.pop(0x3B81A0, None)
        creature = _creature(case)
        case.poke(creature + 0x34, 4, type_addr)
        if prop_addr:
            case.stub(0x14F4C0, 'obj_getPropStr', prop_addr)
        else:
            case.stub(0x14F4C0, 'obj_getPropStr', 0)
        got = E.boss_music_name(case.mem, case.trace, creature)
        if got != track:
            errors.append('boss model 0x%x -> 0x%x not 0x%x' % (type_addr, got, track))
        case.run(0x10DBE0, (creature,), expect=track, ignore=(0x3B81A0,))
        errors.extend('boss 0x%x: %s' % (type_addr, item) for item in case.errors)

    case = Case(elf)
    case.follow(0x3B81A0, 'strcasecmp')
    case.ee.stub_names.pop(0x3B81A0, None)
    creature = _creature(case)
    miss = case.ee.alloc(4)
    case.ee.mem.write(miss, b'zz\x00')
    case.poke(creature + 0x34, 4, miss)
    case.stub(0x14F4C0, 'obj_getPropStr', 0)
    E.boss_music_name(case.mem, case.trace, creature)
    case.run(0x10DBE0, (creature,), expect=0, ignore=(0x3B81A0,))
    errors.extend('boss miss: ' + item for item in case.errors)

    case = Case(elf)
    creature = case.ee.alloc(0x40)
    case.stub(0x10DBE0, 'creature_bossMusicName', 0)
    case.stub(0x211CE8, 'audio_streamStop', 0)
    case.stub(0x2110E0, 'music_playGlobal', 5)
    E.start_boss_music(case.trace, creature)
    case.run(0x1192B0, (creature,), expect=0)
    errors.extend('boss start none: ' + item for item in case.errors)

    case = Case(elf)
    creature = case.ee.alloc(0x40)
    name = case.ee.alloc(4)
    case.stub(0x10DBE0, 'creature_bossMusicName', name)
    case.stub(0x211CE8, 'audio_streamStop', 0)
    case.stub(0x2110E0, 'music_playGlobal', 5)
    E.start_boss_music(case.trace, creature)
    case.run(0x1192B0, (creature,), expect=5)
    errors.extend('boss start: ' + item for item in case.errors)
    return errors


def test_spawn(elf):
    errors = []
    case = Case(elf)
    gen = case.ee.alloc(0x80)
    name = case.ee.alloc(8)
    case.poke(gen + 0x10, 4, f32(1.25))
    case.poke(gen + 0x14, 4, f32(2.5))
    case.poke(gen + 0x18, 4, f32(3.75))
    case.poke(gen + 0x1C, 4, 0x99)
    case.poke(gen + 0x38, 2, 0x100)
    case.poke(gen + 0x2C, 4, 0x11)
    captured = {}

    def create(emu):
        pointer = emu.r[5] & M32
        captured['pos'] = tuple(emu.mem.u32(pointer + 4 * i) for i in range(4))
        captured['angle'] = emu.r[6] & M32
        captured['props'] = emu.r[7] & M32
        return 0
    case.ee.stub(0x14F6C8, function=create, name='world_createObject')
    case.trace.returns['world_createObject'] = 0
    E.generator_spawn(case.mem, case.trace, gen, name)
    case.run(0x265FC4, (gen, name), expect=0x01000000)
    if captured.get('pos') != (f32(1.25), f32(2.5), f32(3.75), 0):
        errors.append('spawn pos %s' % (captured.get('pos'),))
    if captured.get('angle') != 0xFFFFC100 or captured.get('props') != 0x11:
        errors.append('spawn angle/props %s' % (captured,))
    errors.extend('spawn none: ' + item for item in case.errors)
    return errors


def test_spawn_real(elf):
    """Separated so a broken placeholder cannot hide the real calls."""
    errors = []

    def make(rtti_ret):
        case = Case(elf)
        gen = case.ee.alloc(0x80)
        name = case.ee.alloc(8)
        obj = case.ee.alloc(0x400)
        table = case.ee.alloc(0x100)
        case.poke(gen + 0x38, 2, 0x4000)
        case.poke(obj + 0x48, 4, table)
        case.poke(obj + 0xA8, 8, 5)
        case.poke(table + 4, 4, 0x111000)
        case.poke(table + 220, 4, 0x3C2688)
        case.ee.stub(0x14F6C8, ret=obj, name='world_createObject')
        case.ee.stub(0x111000, ret=9, name='vtable_slot0')
        case.ee.stub(E.SKELETON_TYPEINFO, ret=9, name='Skeleton_typeinfo')
        case.ee.stub(0x3B1250, ret=rtti_ret, name='rtti_typeInfoEquals')
        case.trace.returns.update(world_createObject=obj, vtable_slot0=9,
                                   Skeleton_typeinfo=9, rtti_typeInfoEquals=rtti_ret)
        case.follow(0x3C2688, 'slot27')
        E.generator_spawn(case.mem, case.trace, gen, name)
        expect = 0x3C2688 if rtti_ret else 0
        case.run(0x265FC4, (gen, name), expect=expect)
        return case

    case = make(0)
    errors.extend('spawn other: ' + item for item in case.errors)
    case = make(1)
    errors.extend('spawn skeleton: ' + item for item in case.errors)
    return errors


def test_weapon(elf):
    errors = []
    for which, kind, body in ((0, 0x105, E.weapon2_set_element), (1, 2, E.weapon2_set_element),
                              (2, 2, E.weapon2_set_element), (0, 4, E.weapon_shield_slot8)):
        case = Case(elf)
        holder = case.ee.alloc(16)
        inner = case.ee.alloc(0x120)
        case.poke(holder + 4, 4, inner)
        case.stub(0x1176E0, 'creature_buildElementDamage', 0)
        addr = 0x3C2238 if body is E.weapon2_set_element else 0x3C2500
        case.follow(addr, 'inner_slot8')
        E.weapon_object_slot8(case.mem, case.trace, holder, which, kind)
        body(case.trace, inner, which, kind)
        # The original enters at the weapon-object forwarder only when we call it.
        # Call the body directly so the element arguments are the ones compared.
        case.trace.calls = [item for item in case.trace.calls if item[0] != 'inner_slot8']
        # which 1 does not finish on the element call; v0 stays 2, the compare immediate.
        expect = 2 if body is E.weapon2_set_element and which == 1 else 0
        case.run(addr, (inner, which, kind & 0xFF), expect=expect)
        errors.extend('weapon %s %d: %s' % (body.__name__, which, item) for item in case.errors)
    # The forwarder itself, which 0, type masked.
    case = Case(elf)
    holder = case.ee.alloc(16)
    inner = case.ee.alloc(0x120)
    table = case.ee.alloc(0x80)
    case.poke(holder + 4, 4, inner)
    case.poke(inner, 4, table)
    case.poke(table + 68, 4, 0x3C2238)
    case.stub(0x1176E0, 'creature_buildElementDamage', 0)
    case.follow(0x3C2238, 'inner_slot8')
    E.weapon_object_slot8(case.mem, case.trace, holder, 0, 0x105)
    E.weapon2_set_element(case.trace, inner, 0, 0x105)
    case.run(0x3C17E8, (holder, 0, 0x105), expect=0)
    errors.extend('weapon forward: ' + item for item in case.errors)
    return errors


def test_dtor(elf):
    errors = []
    for flags, freed in ((0, False), (1, True), (3, True)):
        case = Case(elf)
        creature = case.ee.alloc(0x400)
        case.follow(0x1A1A48, 'iter_begin')
        case.follow(0x1A1AE8, 'iter_end')
        case.follow(0x1A1698, 'handle_clear')
        case.follow(0x202500, 'fn_202500')
        case.stub(0x171098, 'AnimState_dtor', 0)
        case.stub(0x14CF90, 'GameObject_dtor', 0)
        case.stub(0x150470, 'pool_free', 0)
        E.creature_dtor(case.mem, case.trace, creature, flags)
        # iter_begin's first argument is the stack pointer. Compare the list pointer.
        begin = case.trace.calls[0]
        case.trace.calls[0] = ('iter_begin', (None, begin[1][0]), ())
        end = case.trace.calls[1]
        case.trace.calls[1] = ('iter_end', (None, end[1][0]), ())
        case.run(0x117128, (creature, flags), expect=0)
        errors.extend('dtor %d: %s' % (flags, item) for item in case.errors)
        if freed and not any(rec.name == 'pool_free' for rec in case.ee.calls):
            errors.append('dtor %d did not free' % flags)
    return errors


def test_handlers(elf, cases):
    D.OPTIONS['cases'] = cases
    D.OPTIONS['seed'] = 20973
    D.OPTIONS['verbose'] = False
    rig = D.Rig(elf)
    rig.checkpoint()
    coverage = D.Coverage(rig)
    stats = {'cases': 0, 'faults': 0, 'executed': set()}
    before = len(D.RESULTS)
    names = tuple(row[0] for row in E.COMMANDS) + ('runMedalSuccess', 'runMedalFail')
    done = set()
    for name in names:
        if name in done:
            continue
        D.OPTIONS['filter'] = name
        D.group_builtins(rig, coverage, stats)
        done.add(name)
    failed = [(label, ok) for label, ok in D.RESULTS[before:] if not ok]
    return failed, stats['cases']


def find_elf(argv):
    for arg in argv:
        if arg and not arg.startswith('-') and os.path.isfile(arg):
            return arg
    for candidate in (os.environ.get('CHAMPIONS_ELF'), PRIVATE,
                      os.path.join(D.ROOT, 'SLUS_209.73')):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    cases, handlers = 4, True
    positional = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == '--no-handlers':
            handlers = False
        elif arg == '--cases' and index + 1 < len(argv):
            index += 1
            cases = int(argv[index])
        elif not arg.startswith('-'):
            positional.append(arg)
        index += 1
    elf = find_elf(positional)
    if elf is None:
        print('SKIP  no SLUS_209.73 found; nothing was run')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != D.EXPECTED_SHA256:
        print('SKIP  %s is not the US v2.00 executable' % elf)
        return 0
    print('executable: %s  (SHA-256 matches US v2.00)' % elf)
    suites = (
        ('scale', test_scale), ('charm', test_charm), ('slots', test_slots),
        ('message', test_message), ('help', test_help), ('fade', test_fade),
        ('compass', test_compass_bust), ('audio', test_frozen_and_queue),
        ('music', test_music), ('boss', test_boss), ('spawn', test_spawn),
        ('spawn class', test_spawn_real),
        ('weapon', test_weapon), ('dtor', test_dtor),
    )
    failed = 0
    for name, fn in suites:
        errors = fn(elf)
        if errors:
            failed += 1
            print('FAIL  %s' % name)
            for item in errors[:8]:
                print('      %s' % item)
        else:
            print('PASS  %s' % name)
    if handlers:
        try:
            bad, count = test_handlers(elf, cases)
        except Exception as exc:
            print('FAIL  handlers %s' % exc)
            return 1
        if bad:
            failed += 1
            print('FAIL  handlers %d' % len(bad))
            for label, _ok in bad[:8]:
                print('      %s' % label)
        else:
            print('PASS  handlers %d cases' % count)
    print('%d suites, %d failed' % (len(suites) + (1 if handlers else 0), failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
