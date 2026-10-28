#!/usr/bin/env python3
"""Compare numeric projectile cleanup contracts with the owner's executable.

Real execution includes both destructors, the object base destructor, the pool,
handle lists, name removal, deferred deletion and the skill-4 run at its end.
The run uses scripted movement results and silent presentation callbacks; it
does not establish terrain, physical contact, rendering or victim HP parity.
No names, extracted tables or original instructions are emitted or embedded.
"""

import argparse
import hashlib
import json

import difftest_creature as DC
import difftest_objects as DO
import ref_core as C
import ref_skills_a as SA


VT04, VT_PROJECTILE = 0x5183D8, 0x5120B8
DTOR04, DTOR_PROJECTILE = 0x3CCFD4, 0x3C2940
RUN04, CLEAR, FREE = 0x2CA1A8, 0x1A1698, 0x150470
BASE_DTOR = 0x14CF90


class Flight04(SA.Model):
    """Reuse the independently authored flight reference, stopping at cleanup."""

    def __init__(self, mem, collision):
        super().__init__(mem)
        self.collision = collision
        self.ended = False

    def move_and_collide(self, obj, velocity):
        return self.collision

    def delete_self(self, obj):
        self.ended = True


class CleanupRig(DO.Rig):
    def __init__(self, executable, seed):
        super().__init__(executable, seed)
        self.extra = {}
        self.cleanup_trace = []
        self.expected_trace = []
        self.collision = 0
        self.flight_words = {}
        self.at_cleanup_words = None
        for addr in (DTOR04, DTOR_PROJECTILE, BASE_DTOR):
            self.emu.hook(addr, lambda e, addr=addr: self.observe_entry(e, addr))
        self.emu.hook(CLEAR, lambda e: self.cleanup_trace.append(('clear', e.r[4] & DO.M32)))
        self.emu.hook(FREE, lambda e: self.cleanup_trace.append(('free', e.r[4] & DO.M32)))
        for name in ('particle_spawn', 'sound_playOnObject', 'fx_spawn'):
            self.emu.stub(SA.EXTERNALS[name].addr)
        self.emu.stub(0x1509F8, function=lambda e: self.collision)
        for table, body in ((VT04, DTOR04), (VT_PROJECTILE, DTOR_PROJECTILE)):
            if self.emu.mem.u32(table + 12) != body or self.emu.mem.s16(table + 8):
                raise AssertionError('unexpected original slot-1 pointer')

    def observe_entry(self, emu, addr):
        obj, flags = emu.r[4] & DO.M32, emu.r[5] & DO.M32
        self.cleanup_trace.append(('entry', addr, obj, flags))
        if addr == DTOR04:
            self.at_cleanup_words = {off: emu.mem.u32(obj + off) for off in (0x44, 0x70)}

    def head(self, addr):
        return self.extra.setdefault(addr, C.Cell(addr))

    def link(self, addr, target):
        self.model.handles.link(self.head(addr), target.heads[0], target)
        self.ecall(0x1A1738, addr, target.addr, target.addr)

    def m_dtor(self, obj, flags):
        table = obj.vtable
        if table not in (VT04, VT_PROJECTILE):
            if table == DO.O.VT_GAMEOBJECT:
                self.expected_trace.append(('entry', BASE_DTOR, obj.addr, flags & DO.M32))
                self.expected_trace.extend(('clear', obj.addr + off) for off in (8, 4, 0))
                if flags & 1:
                    self.expected_trace.append(('free', obj.addr))
            return super().m_dtor(obj, flags)
        body = DTOR04 if table == VT04 else DTOR_PROJECTILE
        self.expected_trace.append(('entry', body, obj.addr, flags & DO.M32))
        offsets = (0x58, 0x54, 0x4C) if table == VT04 else (0x4C,)
        for off in offsets:
            self.expected_trace.append(('clear', obj.addr + off))
            self.model.handles.clear(self.head(obj.addr + off))
        self.expected_trace.append(('entry', BASE_DTOR, obj.addr, 0))
        self.expected_trace.extend(('clear', obj.addr + off) for off in (8, 4, 0))
        # Both original derived destructors enter the object base with flags 0;
        # only the outermost frame performs the one optional pool release.
        self.model.destroy(obj, flags=0)
        if flags & 1:
            self.expected_trace.append(('free', obj.addr))
            self.model.pool.free(obj.addr)
            obj.alive = False
            self.model.objects.pop(obj.addr)

    def m_cleanup(self, addr, flags):
        self.expected_trace = []
        self.m_dtor(self.obj(addr), flags)
        return 0

    def e_cleanup(self, addr, flags):
        self.cleanup_trace = []
        table = self.emu.mem.u32(addr + 0x48)
        self.ecall(self.emu.mem.u32(table + 12), addr, flags)
        if self.cleanup_trace != self.expected_trace:
            self.bad('cleanup call order differs: %r != %r' %
                     (self.cleanup_trace, self.expected_trace))
        return 0

    def m_flight(self, addr, collision):
        self.expected_trace = []
        view = DC.ModelView(self.emu.mem)
        model = Flight04(view, collision)
        getattr(model, SA.OBJECT_BODIES[RUN04])(addr)
        self.obj(addr).seed = view.load(addr + 0x44, 4)
        self.flight_words = {off: view.load(addr + off, 4) for off in (0x44, 0x70)}
        if model.ended:
            self.m_dtor(self.obj(addr), 3)
        return int(model.ended)

    def e_flight(self, addr, collision):
        self.collision = collision
        self.cleanup_trace = []
        self.at_cleanup_words = None
        self.ecall(RUN04, addr)
        if self.cleanup_trace != self.expected_trace:
            self.bad('run-to-cleanup call order differs')
        got = self.at_cleanup_words if self.expected_trace else {
            off: self.emu.mem.u32(addr + off) for off in self.flight_words}
        if got != self.flight_words:
            self.bad('flight seed or deadline differs before cleanup')
        return int(bool(self.cleanup_trace))

    def m_flush(self):
        self.expected_trace = []
        return super().m_flush()

    def e_flush(self):
        self.cleanup_trace = []
        result = super().e_flush()
        if self.cleanup_trace != self.expected_trace:
            self.bad('deferred cleanup call order differs')
        return result

    def m_destroy(self, addr):
        self.expected_trace = []
        return super().m_destroy(addr)

    def e_destroy(self, addr):
        self.cleanup_trace = []
        result = super().e_destroy(addr)
        if self.cleanup_trace != self.expected_trace:
            self.bad('direct destruction call order differs')
        return result

    def check(self, full=False):
        super().check(full)
        for head in getattr(self, 'extra', {}).values():
            self.check_chain(head)
        if full:
            for node in self.model.handles.nodes:
                addr = DO.NODE_BASE + DO.NODE_SIZE * node.index
                if self.emu.mem.u16(addr + 0x10) != node.tag:
                    self.bad('defined handle metadata differs')
                    break

    def projectile(self, table, linked=True, then='frame', pkey=0):
        addr = self.do('new', 0x7C, (0, 0, 0), pkey, 0, then, 0, 0)
        obj = self.obj(addr)
        obj.vtable = table
        self.emu.mem.w32(addr + 0x48, table)
        for off in ((0x4C, 0x54, 0x58) if table == VT04 else (0x4C,)):
            self.head(addr + off)
            self.emu.mem.w32(addr + off, 0)
        if linked:
            for off in ((0x4C, 0x54, 0x58) if table == VT04 else (0x4C,)):
                self.link(addr + off, self.owner)
        for _ in range(self.rng.randrange(1, 5)):
            self.link(self.emu.alloc(4), obj)
        return addr


def run(executable, seed):
    rig = CleanupRig(executable, seed)
    rig.owner = rig.obj(rig.do('new', 0x4C, (0, 0, 0), 0, 0, 'none', 0, 0))
    cases = 0
    for table in (VT_PROJECTILE, VT04):
        for flags in (0, 1, 2, 3, 0x80000000, 0x80000001, 0xFFFFFFFF):
            for linked in (False, True):
                addr = rig.projectile(table, linked)
                rig.do('cleanup', addr, flags)
                if not flags & 1:
                    rig.do('destroy', addr)
                cases += 1
    # A real deferred queue and flush use the object's original slot 1 too.
    for table in (VT_PROJECTILE, VT04):
        addr = rig.projectile(table)
        rig.do('delete', addr)
        rig.do('flush')
        if addr in rig.model.objects:
            rig.bad('deferred cleanup did not free its object')
        cases += 1
    # The same queue can contain base objects and both derived tables.
    for reverse in (False, True):
        base = rig.do('new', 0x4C, (0, 0, 0), 0, 0, 'frame', 0, 0)
        queued = [base, rig.projectile(VT04), rig.projectile(VT_PROJECTILE)]
        for addr in reversed(queued) if reverse else queued:
            rig.do('delete', addr)
        rig.do('flush')
        if any(addr in rig.model.objects for addr in queued):
            rig.bad('mixed queue retained an object')
        cases += 1
    for table in (VT_PROJECTILE, VT04):
        addr = rig.projectile(table)
        rig.do('destroy', addr)
        cases += 1
    # Synthetic properties are reused from the unchanged object-system corpus.
    # The two populated name entries, schedules, grids and draw lists are real.
    pkey = rig.add_props(DO.PROP_LISTS[3])
    for table in (VT_PROJECTILE, VT04):
        for then in ('none', 'frame', 'r15', 'r60'):
            for offgrid in (False, True):
                for draw in (False, True):
                    addr = rig.projectile(table, then=then, pkey=pkey)
                    if not rig.model.names.count:
                        raise AssertionError('name fixture is empty')
                    if offgrid:
                        rig.do('offgrid', addr)
                    if draw:
                        rig.do('adraw', addr)
                    rig.do('cleanup', addr, 3)
                    if rig.model.names.count:
                        rig.bad('synthetic names remain after cleanup')
                    cases += 1
    # A filtered queue retains its object until a later unfiltered flush.
    for table in (VT_PROJECTILE, VT04):
        addr = rig.projectile(table)
        rig.do('flags', addr, rig.obj(addr).flags | 0x10000000)
        rig.do('delete', addr)
        rig.do('set', 'mask', 0x10000000)
        rig.do('flush')
        if addr not in rig.model.objects:
            rig.bad('excluded queued object was freed')
        rig.do('set', 'mask', 0)
        rig.do('flush')
        if addr in rig.model.objects:
            rig.bad('unfiltered queued object was retained')
        cases += 1
    # Different live targets exercise clearing each independent handle chain.
    addr = rig.projectile(VT04, linked=False)
    target = rig.obj(rig.do('new', 0x4C, (0, 0, 0), 0, 0, 'none', 0, 0))
    for off, obj in ((0x4C, rig.owner), (0x54, rig.owner), (0x58, target)):
        rig.link(addr + off, obj)
    rig.do('cleanup', addr, 3)
    rig.do('destroy', target.addr)
    cases += 1
    # Terminal conditions from the run at 0x2ca1a8: inclusive deadline,
    # ground bit, contact bit with and without the separate hit latch.
    for delta, collision, latch, expected in (
            (-1, 0, 0, False), (0, 0, 0, True), (1, 0, 0, True),
            (-1, 1, 0, True), (-1, 2, 0, False), (-1, 2, 1, True),
            (-1, 3, 0, True), (-1, 3, 1, True)):
        addr = rig.projectile(VT04)
        frame = 2000
        rig.model.frame = frame
        rig.emu.mem.w32(SA.G_SIM_FRAME, frame)
        rig.emu.mem.w32(addr + 0x70, frame - delta)
        rig.emu.mem.w32(addr + 0x74, frame + 1)  # fixture: no homing this tick
        rig.emu.mem.w32(addr + 0x78, latch)
        ended = rig.do('flight', addr, collision)
        if bool(ended) != expected:
            rig.bad('terminal-condition control differs')
        if not ended:
            rig.do('cleanup', addr, 3)
        cases += 1
    # Owner destruction clears both aliases and the target before cleanup.
    addr = rig.projectile(VT04)
    rig.do('destroy', rig.owner.addr)
    rig.do('cleanup', addr, 3)
    cases += 1
    rig.check(full=True)
    row = dict(seed=seed, cases=cases, operations=rig.steps,
               mismatches=rig.failures)
    print(json.dumps(row, sort_keys=True))
    return not rig.failures


def mutation_controls(executable, seed):
    """Reject wrong reference contracts without modifying original code."""
    rejected = 0
    mutations = ('skip_handle', 'wrong_flag', 'wrong_order', 'destroy_order', 'metadata')
    for mutation in mutations:
        class Mutant(CleanupRig):
            def m_dtor(self, obj, flags):
                if obj.vtable == VT04 and mutation == 'skip_handle':
                    obj.vtable = VT_PROJECTILE
                if mutation == 'wrong_flag':
                    flags ^= 1
                super().m_dtor(obj, flags)
                if mutation in ('wrong_order', 'destroy_order'):
                    self.expected_trace[1:3] = reversed(self.expected_trace[1:3])

        rig = Mutant(executable, seed)
        rig.owner = rig.obj(rig.do('new', 0x4C, (0, 0, 0), 0, 0, 'none', 0, 0))
        addr = rig.projectile(VT04)
        try:
            if mutation == 'metadata':
                rig.head(addr + 0x58).next.tag ^= 1
                rig.check(full=True)
            elif mutation == 'destroy_order':
                rig.do('destroy', addr)
            else:
                rig.do('cleanup', addr, 3)
        except DO.Diverged:
            pass
        rejected += bool(rig.failures)
    print(json.dumps(dict(mutation_controls=len(mutations), rejected=rejected), sort_keys=True))
    return rejected == len(mutations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    with open(args.executable, 'rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != DO.EXPECTED_SHA256:
            parser.error('unsupported executable digest')
    matched = run(args.executable, args.seed)
    controlled = mutation_controls(args.executable, args.seed)
    return 0 if matched and controlled else 1


if __name__ == '__main__':
    raise SystemExit(main())
