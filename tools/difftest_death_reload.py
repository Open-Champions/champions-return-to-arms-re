#!/usr/bin/env python3
"""Execute synthetic death reload and class restore boundaries; no game data emitted.

Services explicitly stubbed below are not evidence of their resulting effects.
"""
import argparse
import hashlib
import os
import random
import struct
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
import dis  # noqa: F401,E402
sys.path.insert(0, HERE)
from ee_emu import EE

SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'


def fixture(elf):
    e = EE(elf)
    e.record_calls = e.record_writes = False
    return e


def put(e, p, fmt, *v):
    e.mem.write(p, struct.pack('<' + fmt, *v))


def get(e, p, fmt):
    return struct.unpack('<' + fmt, e.mem.read(p, struct.calcsize('<' + fmt)))


def recorder(e, addr, events, name, n=1, ret=0):
    def call(cpu):
        events.append((name, *(cpu.r[4+i] & 0xffffffff for i in range(n))))
        return ret
    e.stub(addr, function=call)


def death_reload(elf, rng):
    for found in (False, True):
        for qualified in (False, True):
            e = fixture(elf)
            m = e.mem
            events = []
            m.w8(0x86af50, 0)
            m.w8(0x86af51, 0)
            m.w32(0x4f712c, 0)
            m.w32(0x4d8ae0, 1)
            m.write(0x44fe18, b'synthetic_current\0')
            live = bytes(rng.getrandbits(8) for _ in range(0x4c30))
            m.write(0x4d8af0, live)
            put(e, 0x4d8af0 + 0xac, 'ff', 0., 160.)
            live = m.read(0x4d8af0, 0x4c30)
            # Synthetic buffer. Section callbacks use zero-length camera/gate stores.
            m.write(0x895580, bytes(0x16000))
            m.write(0x895580, b'synthetic_saved\0')
            if qualified:
                m.write(0x895594, b'part\0')
            put(e, 0x8955e4, 'I', 12345)
            m.w8(0x8955ec, 2)
            m.w16(0x8955ee, 3)
            p = 0x8955f0
            put(e, p, 'II', 7, 1)
            p += 8
            put(e, p, 'Hfff', 1234, 1., -2., 3.)
            saved = bytearray(rng.getrandbits(8) for _ in range(0x4c30))
            struct.pack_into('<ff', saved, 0xac, 80., 160.)
            struct.pack_into('<I', saved, 0x43d8, 0x12345678)
            m.write(p + 14, saved)
            recorder(e, 0x1df5ec, events, 'fade', ret=128)
            recorder(e, 0x217d30, events, 'act_lookup', ret=0 if found else -1)
            recorder(e, 0x19e664, events, 'remove')
            recorder(e, 0x203a20, events, 'camera', n=2)
            recorder(e, 0x27dd30, events, 'destinations')
            recorder(e, 0x216ea8, events, 'player_fixup')
            recorder(e, 0x1eda08, events, 'clear_deferred', n=0)
            recorder(e, 0x1ed728, events, 'clear_vars', n=0)
            recorder(e, 0x1ed854, events, 'set_var', n=2)
            recorder(e, 0x2180a8, events, 'set_act')
            # Final offline countdown tick executes the actual scheduler wrapper.
            m.w32(0x4f85b0, 1)
            m.w32(0x4f8420, 0)
            m.w32(0x4f7120, 0)
            m.w8(0x44fcd0, 0)
            m.w8(0x402791, 0)
            m.w32(0x41b4f4, 0)
            m.w16(0x4f7194, 1)
            m.w16(0x4f84a8, 1)
            recorder(e, 0x1ebdf8, events, 'frozen', n=0)
            recorder(e, 0x1eb000, events, 'close_menus')
            recorder(e, 0x1df5d0, events, 'fade_clear')
            recorder(e, 0x19e4a0, events, 'schedule', n=4)
            e.call(0x1e7438)
            assert m.u16(0x4f7194) == m.u16(0x4f84a8) == 0
            assert m.u32(0x41b4fc) == 60
            assert events == [('frozen',), ('close_menus', 0), ('fade_clear', 0),
                              ('schedule', 0x1e75e8, 20, 0x53d438, 0)]
            assert m.u8(0x86af50) == m.u8(0x86af51) == 0
            events.clear()
            # libc executes, as do deathTask -> save_reload -> save_load.
            e.call(0x1e75e8)
            assert m.u8(0x86af50) == 1
            e.call(0x1e75e8)
            assert m.u8(0x41b720) == 253
            if found:
                assert m.u8(0x86af50) == 2
                assert m.cstr(0x41b6d0) == 'synthetic_saved' + ('_part' if qualified else '')
                expected = bytearray(saved)
                struct.pack_into('<I', expected, 0x43d8, 0)
                assert m.read(0x4d8af0, 0x4c30) == expected
                assert get(e, 0x4f70d0, 'fff') == (1., -2., 3.)
                assert m.u16(0x4f8410) == 1234
                assert m.u8(0x8e1ad6) == 1
                assert m.u32(0x4d8ae0) == 1
                assert [x[0] for x in events] == ['fade', 'act_lookup', 'camera',
                    'destinations', 'player_fixup', 'clear_deferred', 'clear_vars', 'set_act']
                assert events[-1] == ('set_act', 3)
            else:
                want = bytearray(live)
                struct.pack_into('<f', want, 0xac, 160.)
                assert m.read(0x4d8af0, 0x4c30) == want
                assert m.cstr(0x41b6d0) == 'synthetic_current'
                assert events[-1] == ('remove', 0x1e75e8)
    print('PASS deathTask -> save_reload -> save_load / direct restart: 4 cases')


def trigger_chest_gate(elf):
    for flag in (0, 1, 255):
        e = fixture(elf)
        obj, buf = e.alloc(0x400), e.alloc(32)
        put(e, buf, 'IB', 0x12345678, flag)
        assert e.call(0x1ecef4, obj, buf) == 5
        assert e.mem.u32(obj + 0x64) == 0x12345678
        assert e.mem.u8(obj + 0x60) == flag
    for opened in (0, 1):
        for gold in (0, 1, 32767):
            for variant in (0, 1):
                e = fixture(elf)
                obj, buf, defs = e.alloc(0x200), e.alloc(32), e.alloc(64)
                e.mem.w32(obj + 0x24, defs)
                e.mem.w32(defs + 0x1c, 0x1234)
                e.mem.w32(0x501698 + variant*4, 0x5678 + variant)
                e.mem.w32(obj + 0xc, 0x100800)
                put(e, buf, 'IHBBI', 0xaabbccdd, gold, 2, variant, opened)
                events = []
                recorder(e, 0x170838, events, 'clip', n=3)
                recorder(e, 0x170bc8, events, 'end')
                recorder(e, 0x14f5f0, events, 'class', n=2)
                assert e.call(0x2922cc, obj, buf) == 12
                assert e.mem.u32(obj + 0x54) == 0xaabbccdd
                assert e.mem.u16(obj + 0x4c) == gold
                assert e.mem.u8(obj + 0x58) == 2
                assert e.mem.u8(obj + 0x59) == variant
                assert e.mem.u32(obj + 0x84) == opened
                assert e.mem.u32(obj + 0xc) == (0x800 if opened and not gold else 0x100800)
                want = [('clip', obj+0x5c, 0x1234, 0x204), ('end', obj+0x5c)] if opened else []
                assert events == want + [('class', obj, 0x5678 + variant)]
    for active in (0, 1):
        e = fixture(elf)
        obj, buf = e.alloc(0x200), e.alloc(16)
        put(e, buf, 'BB', 2, active)
        events = []
        recorder(e, 0x148bc8, events, 'light')
        recorder(e, 0x17365c, events, 'lookup', n=2, ret=0x3456)
        recorder(e, 0x170838, events, 'clip', n=3)
        recorder(e, 0x14f248, events, 'update')
        assert e.call(0x27d998, obj, buf) == 2
        assert e.mem.read(obj+0x4d, 2) == bytes((2, active))
        want = [('light', obj+0x100), ('lookup', obj+0x90, 0x547ee0),
                ('clip', obj+0xd8, 0x3456, 3)] if active else []
        assert events == want + [('update', obj)]
    print('PASS Trigger 3, Chest 12, JumpGate 2 load boundaries (services recorded)')


def doors(elf):
    # Synthetic relocated world: one piece, one terrain element, one render surface.
    for addr in (0x28ae74, 0x28b1b8, 0x28df24):
        for opened in (0, 1):
            e = fixture(elf)
            world, piece, element, surface = [e.alloc(0x100) for _ in range(4)]
            e.mem.w32(0x44fdc8, world)
            e.mem.w32(world+0x54, piece)
            e.mem.w32(world+0x20, element)
            e.mem.w32(world+0x24, surface)
            put(e, piece, 'Ih', 0, 1)
            put(e, piece+8, 'iii', 0, 0, 16)
            put(e, piece+0x14, 'hhh', 32767, 0, 0)
            e.mem.w16(element+0x10, 0x12)
            e.mem.w32(element+0x1c, 123)
            e.mem.w32(surface+0x24, 0)
            obj, buf = e.alloc(0x100), e.alloc(32)
            e.mem.w32(obj+0xc, 0x100800)
            e.mem.w16(obj+0x4c, 0)
            events = []
            recorder(e, 0x14f248, events, 'update')
            # World collision/height/pose setters and trig/floor execute, unstubbed.
            if addr == 0x28ae74:
                put(e, buf, 'Hhf', opened * 32768, 0, 1.25)
                assert e.call(addr, obj, buf) == 8
                assert get(e, obj+0x54, 'f') == (1.25,)
                assert e.mem.u8(obj+0x58) == 0
                assert e.mem.u16(element+0x10) == 0x12
                assert get(e, surface+0x28, 'iii') == (0, 0, 16)
                assert events == ([('update', obj)] if opened else [])
                assert e.mem.u32(obj+0xc) == (0x801 if opened else 0x100800)
            elif addr == 0x28b1b8:
                put(e, buf, 'B', opened)
                assert e.call(addr, obj, buf) == 1
                assert e.mem.u8(obj+0x58) == opened
                assert e.mem.u16(element+0x10) == 0x12
                assert get(e, surface+0x28, 'iii') == ((0, 0, -1184) if opened else (0, 0, 0))
                assert e.mem.u32(obj+0xc) == (0x800 if opened else 0x100800)
            else:
                put(e, buf, 'iifi', opened, 0, 2.5, 99)
                assert e.call(addr, obj, buf) == 16
                assert get(e, obj+0x4c, 'hhfI') == (0, 123, 2.5, 99)
                assert e.mem.u16(obj+0x5a) == opened
                assert e.mem.u16(element+0x10) == 0x10
                assert events == ([('update', obj)] if opened else [])
    print('PASS doors: 6 loads with original world collision/height/pose services')


def creature(elf):
    masks = (0x1000000, 0x100000000, 0x400000, 0x800000, 0x2000000000000)
    count = 0
    for dead in (False, True):
        for bits in (0, 1, 2, 4, 8, 16, 32, 64, 127):
            for clip_found in (False, True):
                e = fixture(elf)
                obj, buf, vt, clips = e.alloc(0x400), e.alloc(32), e.alloc(0x100), e.alloc(64)
                e.mem.w32(obj+0x48, vt)
                e.mem.w32(obj+0x24, clips)
                put(e, obj+0x22c, 'f', 160.)
                e.mem.w8(obj+0x231, 0xfe)
                e.mem.w32(obj+0xc, 0x20)
                e.mem.w16(obj+0x312, 0)
                events = []
                for off, target, name, n in ((0xe8, 0x100, 'variant', 1), (0xe0, 0x110, 'motion', 2), (0, 0x120, 'type', 0)):
                    e.mem.w16(vt+off, 0)
                    e.mem.w32(vt+off+4, target)
                    recorder(e, target, events, name, n=n)
                # Synthetic string pointers only; do not copy a game animation identifier.
                token = e.alloc(16)
                e.mem.write(token, b'synthetic\0')
                if clip_found:
                    e.mem.w32(clips+8, token)
                    e.mem.w32(clips+12, 0x5678)
                recorder(e, 0x14f688, events, 'resolve', ret=token if clip_found else 0)
                recorder(e, 0x14f290, events, 'stop')
                recorder(e, 0x1707b0, events, 'anim_reset')
                recorder(e, 0x170838, events, 'clip', n=3)
                recorder(e, 0x170bc8, events, 'end')
                recorder(e, 0x3c4658, events, 'type_base', n=0)
                recorder(e, 0x3b1250, events, 'type_check', n=2, ret=0)
                recorder(e, 0x1a1698, events, 'unlink')
                ratio = -0.25 if dead else 0.5
                payload = struct.pack('<If', 7, ratio)
                if dead:
                    payload += struct.pack('<i', 11)
                payload += struct.pack('<I', bits)
                if bits & 64:
                    payload += struct.pack('<i', 5)
                e.mem.write(buf, payload)
                assert e.call(0x116920, obj, buf) == len(payload)
                assert e.mem.u32(obj+0xe8) == 7
                assert get(e, obj+0x228, 'f') == ((-40. if dead else 80.),)
                assert get(e, obj+0xa8, 'Q')[0] == sum(mask for i, mask in enumerate(masks) if bits & (1<<i))
                assert e.mem.u8(obj+0x231) == (0xff if bits & 32 else 0xfe)
                assert e.mem.u16(obj+0x312) == (5 if bits & 64 else 0)
                want = [('variant', obj)]
                if dead:
                    assert e.mem.u16(obj+0x232) == 20
                    assert e.mem.u32(obj+0xc) == 0x2029
                    want += [('stop', obj), ('resolve', 11)]
                    if clip_found:
                        want += [('anim_reset', obj+0x114), ('clip', obj+0x114, 0x5678, 4),
                                 ('end', obj+0x114), ('motion', obj, 1)]
                        assert e.mem.u16(obj+0x11a) & 0x80
                    want += [('type',), ('type_base',), ('type_check', 0, 0)]
                if bits & 64:
                    want += [('unlink', obj+0x234)]
                assert events == want, (dead, bits, clip_found, events, want)
                count += 1
    print('PASS Creature: %d live/dead/flags/animation load boundaries (services recorded)' % count)



def itemprop(elf):
    import ref_save_world as R
    for state_bit in (False, True):
        for mask in (8, 10):
            e = fixture(elf)
            obj, buf = e.alloc(0x200), e.alloc(0x100)
            e.mem.w32(obj+0xc, 0x3800)
            e.mem.w16(obj+0x38, 0xc000)
            put(e, obj+0x10, 'fff', 4., 5., 6.)
            item = bytearray(0x48)
            struct.pack_into('<I', item, 0, 7)
            struct.pack_into('<Q', item, 8, (1 << 39) if state_bit else 0)
            suffix = R.prop_suffix((11, 22, 33), mask, (0, 0, 0, 10000), (1, -2, 3))
            e.mem.write(buf, item + suffix)
            events = []
            strings = {}
            for handle, value in ((11, b'synthetic_asset'), (22, b'synthetic_model'), (33, b'synthetic_texture')):
                token = e.alloc(32)
                e.mem.write(token, value + b'\0')
                strings[handle] = token
            e.stub(0x14f688, function=lambda cpu: strings[cpu.r[4]])
            def lookup(cpu):
                events.append((cpu.mem.cstr(cpu.r[4]), cpu.mem.cstr(cpu.r[5])))
                return 0x1234 if len(events) == 1 else 0x5678
            e.stub(0x17365c, function=lookup)
            prop = e.alloc(0x200)
            assert e.call(0x158f04, prop, buf+0x48) == len(suffix)
            assert get(e, prop+0x134, 'fff') == (1., -2., 3.)
            assert get(e, prop+0xe8, 'Q') == (mask,)
            assert e.mem.u32(prop+0xc) == 0x1000
            events.clear()
            # Prop, index decoding, quaternion matrix and final transform run for real.
            assert e.call(0x159758, obj, buf) == 0x48 + len(suffix)
            want = bytearray(item)
            struct.pack_into('<I', want, 0, 0x3f7650 + 7*0x40)
            assert e.mem.read(obj+0x148, 0x48) == want
            assert get(e, obj+0xe8, 'Q') == (mask,)
            assert get(e, obj+0x134, 'fff') == (4., 5., 6.)
            assert get(e, obj+0x10, 'fff') == (4., 5., 6.)
            assert e.mem.u32(obj+0xc) == (0x100000 if state_bit else 0x103000)
            assert (e.mem.u32(obj+0x4c), e.mem.u32(obj+0x50)) == (0x1234, 0x5678)
            assert events == [('synthetic_asset', 'synthetic_model'), ('synthetic_asset', 'synthetic_texture')]
            matrix = get(e, obj+0x110, '12f')
            # Final item transform uses base object pose, replacing Prop's suffix pose.
            assert matrix[9:] == (4., 5., 6.), matrix
            assert all(abs(matrix[i]-1) < 0.000001 for i in (0, 4, 8))
    print('PASS ItemProp: 4 full Prop/index/matrix load cases (string/asset lookups recorded)')


def chest_animation(elf):
    for auto in (False, True):
        for opened in (0, 1):
            e = fixture(elf)
            obj, buf, defs, clip = [e.alloc(0x400) for _ in range(4)]
            track = obj + (0x98 if auto else 0x5c)
            e.mem.w8(track+5, 1)
            e.mem.w32(clip+4, 73)
            e.mem.w32(obj+0xc, 0x100000)
            e.mem.w32(obj+0x24, defs)
            e.mem.w32(defs+0x1c, clip)
            e.mem.w32(obj+0xf4, clip)
            # Class definition cache is already current; the original setter executes.
            e.mem.w32(0x501698, defs)
            e.mem.w32(0x41bf78, 9)
            e.mem.w32(defs+4, 9)
            put(e, buf, 'IHBBI', 7, 0, 0, 0, opened)
            assert e.call(0x23b0b4 if auto else 0x2922cc, obj, buf) == 12
            assert e.mem.u8(track+4) == opened
            assert e.mem.u32(obj+0xc) == (0 if opened else 0x100000)
            if opened:
                assert e.mem.u32(track+8) == clip
                assert e.mem.u16(track+6) == 0x204
                assert e.mem.u16(track+8+0x1c) == 0x204
                assert get(e, track+8+0x18, 'f') == (73.,)
    print('PASS Chest/AutoChest: 4 loads with original clip start/end and class setter')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf')
    p.add_argument('--seed', type=int, default=20973)
    a = p.parse_args()
    with open(a.elf, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == SHA, 'wrong executable pin'
    death_reload(a.elf, random.Random(a.seed))
    trigger_chest_gate(a.elf)
    doors(a.elf)
    creature(a.elf)
    itemprop(a.elf)
    chest_animation(a.elf)


if __name__ == '__main__':
    main()
