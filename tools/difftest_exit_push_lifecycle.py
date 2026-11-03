#!/usr/bin/env python3
"""Counts-only original-function PushTrigger lifecycle differential test.

Run with unittest preloaded to avoid tools/dis.py shadowing stdlib dis:
  PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy; runpy.run_path(
      "tools/difftest_exit_push_lifecycle.py", run_name="__main__")' --seed 20973

Only the private ELF local/SLUS_209.73 is read. All records/scripts are synthetic.
"""
import argparse
import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ref_exit_push_lifecycle as L
import ref_objects as O
from difftest_objects import Rig, A, POOL_NEW, EXPECTED_SHA256, SET_FILTER, SET_FACTORY
from ee_emu import float_to_raw


PUSH_CTOR, PUSH_USE, PUSH_DTOR = 0x1EC900, 0x1ECC70, 0x3C3A00
SCRIPT, SELECTED, PLAYER = 0x1ED694, 0x4039F8, 0x4D8AE4
SAVE, FILTER, LOAD = 0x14E5C8, 0x15D9C8, 0x14E808
ORIGINALS = (PUSH_CTOR, PUSH_USE, PUSH_DTOR, 0x14DCC8, 0x14CF90,
             0x14F200, 0x14F3A8, SAVE, 0x14E140, 0x14DF50,
             FILTER, LOAD, 0x159C94, 0x3C7EB8, 0x3C7EC0,
             0x14C460, 0x14A610)


class LifecycleRig(Rig):
    def __init__(self, elf, seed):
        super().__init__(elf, seed)
        self.m_events, self.e_events = [], []
        self.context = {'selected': 0, 'player': 0}
        self.m_effect = 0
        self.effect = self.emu.alloc(4)
        self.members_checked = 0
        self.script_checks = 0
        self.save_checks = 0
        self.load_checks = 0
        self.filter_classes = (b'Line',)
        self.executed = dict.fromkeys(ORIGINALS, 0)
        for address in ORIGINALS:
            self.emu.hook(address, lambda e, address=address: self.observe(address, e))
        self.save_buffer = self.emu.alloc(0x10000, align=16)
        self.ecall(SET_FILTER, FILTER)
        self.ecall(SET_FACTORY, 0x159C94)
        self.emu.mem.w32(0x44FDC8, self.emu.alloc(0x100))
        self.emu.mem.w8(O.G_NETWORK_MODE, 0)
        self.emu.stub(SCRIPT, function=self.script_stub)
        self.model.on_destroy = self.destroy_model

    def observe(self, address, emu):
        self.executed[address] += 1
        if address == PUSH_DTOR:
            self.e_events.append(('destroy', emu.r[4] & 0xFFFFFFFF, emu.r[5] & 0xFFFFFFFF))

    def destroy_model(self, obj, flags):
        if obj.vtable == L.VT_PUSH:
            self.m_events.append(('destroy', obj.addr, flags))
            self.model.destroy(obj, flags)
        else:
            super().m_dtor(obj, flags)

    def m_push(self, pos, angle, pkey):
        addr = self.model.pool.new(0x4C)
        obj = L.construct(self.model, addr, pos, angle, self.props[pkey][1])
        obj.tag = {'props': self.props[pkey][0], 'active': 0,
                   'cname': self.cstring(b'PushTrigger')}
        return addr

    def e_push(self, pos, angle, pkey):
        addr = self.ecall(POOL_NEW, 0x4C)
        self.ecall(PUSH_CTOR, addr, self.vec(0, pos), angle, self.props[pkey][0])
        self.emu.mem.w32(addr + 0x34, self.cstring(b'PushTrigger'))
        return addr

    @staticmethod
    def script_code(name):
        # Authored callbacks have different, order-sensitive observable effects.
        return {b'probe_alpha': 3, b'probe_beta': 11,
                b'notprobe_alpha': 19, b'notprobe_beta': 29}[name]

    def script_model(self, name, context):
        self.m_events.append(('script', name, context['selected'], context['player']))
        self.m_effect = (self.m_effect * 37 + self.script_code(name)
                         + 101 * context['player']) & 0xFFFFFFFF

    def script_stub(self, emu):
        mem = emu.mem
        name = self.read_cstr(emu.r[4] & 0xFFFFFFFF)
        selected, player = mem.u32(SELECTED), mem.u32(PLAYER)
        self.e_events.append(('script', name, selected, player))
        mem.w32(self.effect, (mem.u32(self.effect) * 37 + self.script_code(name)
                             + 101 * player) & 0xFFFFFFFF)
        return 0

    def m_use(self, addr, slot):
        L.interact(self.model, self.obj(addr), self.context, self.script_model,
                   lambda obj, flags: self.m_events.append(('destroy', obj.addr, flags)))
        return 0

    def e_use(self, addr, slot):
        self.ecall(PUSH_USE, addr, slot)
        return 0

    def use(self, addr, slot, active):
        self.m_events.clear()
        self.e_events.clear()
        self.context = {'selected': 0x123456, 'player': active}
        self.emu.mem.w32(SELECTED, self.context['selected'])
        self.emu.mem.w32(PLAYER, active)
        self.do('use', addr, slot)
        assert self.m_events == self.e_events, 'action/destructor order or context'
        assert self.m_effect == self.emu.mem.u32(self.effect), 'script effects'
        assert self.context['selected'] == self.emu.mem.u32(SELECTED), 'selected cleanup'
        assert self.context['player'] == self.emu.mem.u32(PLAYER), 'player context'
        self.script_checks += 1

    def membership(self):
        expected = L.members(self.model)
        actual = []
        self.emu.stub(self.STUB_WALK, function=lambda e: actual.append(e.r[4] & 0xFFFFFFFF) or 0)
        self.ecall(A['world_forEachGridObject'], self.STUB_WALK)
        assert actual == expected, 'grid walker membership/order'
        self.check(full=True)
        assert not self.failures, 'object/grid/allocator differential'
        self.members_checked += 1
        return actual

    def parse_records(self, base, size):
        """Decode only our synthetic record output; retain no game-derived bytes."""
        mem = self.emu.mem
        count, flags = mem.s16(base), mem.u16(base + 2)
        strings = base + mem.s32(base + 4)
        assert count >= 0 and flags in (0, 1), 'unrelocated record header'
        assert base + 8 <= strings <= base + size, 'record section bound'
        result, locations, at = [], [], base + 8
        for _ in range(count):
            length = mem.s16(at + 4)
            assert length >= 24 and at + length <= strings, 'record bound'
            name = self.read_cstr(strings + mem.s32(at))
            angle = mem.s16(at + 6)
            pos = tuple(mem.u32(at + 8 + 4 * i) for i in range(3))
            props, ptr = [], at + 20
            while mem.s32(ptr):
                assert ptr + 4 <= at + length, 'property bound'
                props.append(self.read_cstr(strings + mem.s32(ptr)))
                ptr += 4
            if flags & 1 and name == b'PushTrigger':
                assert at + length == (ptr + 4 + 7) & ~7, 'unexpected PushTrigger state extent'
            result.append((name, angle, pos, tuple(props)))
            locations.append((at + 20, strings + mem.s32(at)))
            at += length
        assert at == strings, 'record boundary'
        return result, locations, flags

    def save(self):
        want = L.records(self.model, self.filter_classes)
        size = self.ecall(SAVE, self.save_buffer, 0x10000)
        assert 8 <= size <= 0x10000, 'bounded save size'
        got, locations, flags = self.parse_records(self.save_buffer, size)
        assert flags == 1 and got == want, 'saved record identity/order/content'
        self.save_checks += 1
        return size, want, locations

    def load(self, base, records, locations, filter_only):
        for record, (props_pointer, class_pointer) in zip(records, locations):
            name, angle, position, properties = record
            if filter_only and name not in self.filter_classes:
                continue
            addr = self.model.pool.new(0x4C)
            obj = L.construct(self.model, addr, position, 0, list(properties))
            obj.class_name = name
            obj.tag = {'props': props_pointer, 'active': 0, 'cname': class_pointer}
        self.ecall(LOAD, base, int(filter_only))
        self.check(full=True)
        assert not self.failures, 'loaded object/grid/allocator differential'
        self.load_checks += 1


def save_reentry(rig, rng):
    cases = 0
    for round_no in range(4):
        initial = []
        configs = ((b'used', 1, 2), (b'repeat', 0, 2), (b'unused', 1, 1),
                   (b'empty', 1, 0), (b'deferred', 0, 1),
                   (b'transient', 0, 0))
        for index, (key, once, actions) in enumerate(configs):
            pos = tuple(float_to_raw(rng.choice((-16000, -512, 0, 1, 513, 16000)))
                        for _ in range(3))
            if key == b'used':
                pos = (float_to_raw(16000 if round_no == 2 else rng.choice((-300, 0, 513))),
                       float_to_raw(rng.choice((-512, 0, 256))), pos[2])
            elif key == b'repeat' and round_no == 3:
                pos = initial[0][2]  # surviving neighbour in the same cell
            angle = rng.randrange(65536)
            scripts = [b'action=probe_alpha', b'action=probe_beta'][:actions]
            if rng.randrange(2):
                scripts.reverse()
            props = [b'name=life_' + key, b'once=%d' % once,
                     b'offonly=%d' % rng.randrange(2)] + scripts
            name = b'PushTrigger'
            initial.append((name, O.s16(angle), pos, tuple(props)))
        initial_blob = O.RecordBlob([O.Record(*r) for r in initial]).build()
        base = rig.emu.alloc(len(initial_blob), align=8)
        rig.emu.mem.write(base, initial_blob)
        parsed_initial, initial_locations, _ = rig.parse_records(base, len(initial_blob))
        assert parsed_initial == initial
        rig.load(base, initial, initial_locations, False)
        objects = {O.props_find(obj.props, b'name')[5:]: obj.addr
                   for obj in rig.model.objects.values()}
        for index, (key, _, _) in enumerate(configs):
            addr = objects[key]
            pos = tuple(rig.obj(addr).pos)
            if index % 2 or (key == b'used' and round_no in (1, 3)):
                rig.do('flags', addr, rig.obj(addr).flags | 0x800)
                rig.do('move', addr, *pos)
            rig.do('frame', addr)
            rig.do('adraw', addr)
        transient = objects[b'transient']
        rig.do('flags', transient, rig.obj(transient).flags | 0x4000)
        assert len(rig.membership()) == 6
        assert len(rig.save()[1]) == 5
        # Query exclusion does not exclude the same object from saved records.
        rig.do('set', 'mask', 0x8)
        assert len(rig.save()[1]) == 5
        rig.do('set', 'mask', 0)
        rig.use(objects[b'used'], rng.randrange(4), rng.randrange(4))
        rig.use(objects[b'repeat'], rng.randrange(4), rng.randrange(4))
        rig.use(objects[b'empty'], rng.randrange(4), rng.randrange(4))
        assert objects[b'used'] not in rig.membership()
        assert len(rig.save()[1]) == 4
        rig.do('delete', objects[b'deferred'])
        assert objects[b'deferred'] in rig.membership()
        assert len(rig.save()[1]) == 4
        rig.do('flush')
        assert objects[b'deferred'] not in rig.membership()
        size, saved, locations = rig.save()
        assert len(saved) == 3
        # Keep the saved blob private in emulated memory while unloading the world.
        rig.do('deleteall')
        assert rig.membership() == []
        rig.load(rig.save_buffer, saved, locations, False)
        rig.load(base, initial, initial_locations, True)
        got = L.records(rig.model)
        # Saved records are created in writer order, but grids link at the front.
        # Compare complete logical identities rather than assume new grid order.
        assert sorted(got) == sorted(L.reentry_records(saved, initial, rig.filter_classes))
        assert len(rig.membership()) == 3
        names = {O.props_find(obj.props, b'name'): obj.addr for obj in rig.model.objects.values()}
        assert b'life_used' not in names and b'life_deferred' not in names
        assert b'life_unused' in names and b'life_empty' in names
        rig.use(names[b'life_repeat'], rng.randrange(4), rng.randrange(4))
        rig.use(names[b'life_unused'], rng.randrange(4), rng.randrange(4))
        rig.membership()
        rig.do('deleteall')
        assert rig.membership() == []
        cases += 1
    return cases


def run(elf, seed):
    rng = random.Random(seed)
    rig = LifecycleRig(elf, seed)
    assert rig.ecall(FILTER, rig.cstring(b'PushTrigger')) == 0
    assert rig.ecall(FILTER, rig.cstring(b'Line')) == 1
    # Reject an authored record with an extra class-state payload; properties and
    # logical identities alone would otherwise conceal a nonempty save-state slot.
    extra_state = O.RecordBlob([O.Record(b'PushTrigger', 0, (0, 0, 0), [], bytes(8))], True).build()
    malformed = rig.emu.alloc(len(extra_state), align=8)
    rig.emu.mem.write(malformed, extra_state)
    try:
        rig.parse_records(malformed, len(extra_state))
    except AssertionError as exc:
        assert str(exc) == 'unexpected PushTrigger state extent'
    else:
        raise AssertionError('nonempty PushTrigger state accepted')
    count = 0
    for off_only in (0, 1):
        for once in (0, 1):
            for actions in (0, 1, 2):
                props = [b'name=probe_%d' % count, b'once=%d' % once,
                         b'offonly=%d' % off_only]
                props += [b'action=probe_alpha', b'action=probe_beta'][:actions]
                pos = tuple(float_to_raw(rng.choice((-16000, -300, 0, 256, 16000)))
                            for _ in range(3))
                obj = rig.do('push', pos, rng.randrange(65536), rig.add_props(props))
                assert obj in rig.membership()
                rig.do('frame', obj)
                rig.do('adraw', obj)
                rig.use(obj, rng.randrange(4), rng.randrange(4))
                assert (obj in rig.membership()) == (not (once and actions))
                rig.do('flush')
                rig.membership()
                if obj in rig.model.objects:
                    rig.use(obj, rng.randrange(4), rng.randrange(4))
                    rig.do('delete', obj)
                    assert obj in rig.membership(), 'deferred delete stays in grid'
                    rig.do('flush')
                    assert obj not in rig.membership(), 'flush removes deferred object'
                count += 1
    reentries = save_reentry(rig, rng)
    assert all(rig.executed.values()), 'required original body not entered'
    return {'cases': count, 'operations': rig.steps, 'reentry_cases': reentries,
            'membership_checks': rig.members_checked, 'action_checks': rig.script_checks,
            'save_checks': rig.save_checks, 'load_checks': rig.load_checks,
            'original_functions': len(rig.executed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    elf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'local', 'SLUS_209.73')
    with open(elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == EXPECTED_SHA256, 'ELF identity'
    try:
        counts = run(elf, args.seed)
    except Exception as exc:
        print('FAIL push_lifecycle failures=1 error_type=' + type(exc).__name__)
        return 1
    print('PASS push_lifecycle seed=%d ' % args.seed +
          ' '.join('%s=%d' % item for item in counts.items()) + ' failures=0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
