#!/usr/bin/env python3
"""Execute original menu + task registry and compare an additive lifetime model.

Private US v2.00 ELF is required. No game bytes/names are emitted or persisted.
Use --iso to also compose the existing original dialog/VM offer probe.
All host substitutions are explicit; implicit fallback calls fail closed.
"""
import sys
from pathlib import Path
_TOOL_DIR = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p or '.').resolve()) != _TOOL_DIR]
import unittest
sys.path.append(_TOOL_DIR)
import argparse
import hashlib
import random

from ee_emu import EE
import difftest_quests as D
import ref_quests as Q
from ref_mission_lifecycle import Menu

ADD, REMOVE, RUNNING, CALL = 0x19e4a0, 0x19e664, 0x19e5e8, 0x19e798
COUNT, CURSOR, TASKS = 0x44fdb8, 0x44fdbc, 0x840100
DRAW, REMOVE_MENU, CHOOSER = 0x232300, 0x2316b8, 0x4fe7ec
RUN_NAME, DRAW_NAME = 0x5410e8, 0x5410f8
BUILD, LOAD, SAVE, SAVE_SIZE = 0x221914, 0x221d60, 0x895580, 0x4bc78
REAL = D.MENU_FOLLOW | {D.MENU_OPEN, D.MENU_RUN, REMOVE_MENU, ADD, REMOVE, RUNNING, CALL, 0x19e760,
                        0x3b8534, 0x3b8dc4, 0x1ec5d0, 0x13e1f0}
CHECKS = 0


def check(condition, label):
    global CHECKS
    CHECKS += 1
    assert condition, label


class Rig:
    def __init__(self, elf, seed=20973, network=0, chooser=0, emu=None):
        self.e = e = emu if emu is not None else EE(elf)
        self.m = e.mem
        self.network = network
        self.model = Menu()
        self.model.fields['orient'] = 0
        self.world = Q.CampaignView([D.load_row(self.m, i) for i in range(13)],
                                   {1}, {1}, {1: 3})
        if emu is None:
            rng = random.Random(seed)
            for reg in range(1, 29):
                e.r[reg] = rng.getrandbits(64)
        # Keep host harness APIs intact when composing with the existing VM rig.
        if isinstance(e.follow, set) or e.follow is None:
            e.follow = set(REAL)
        else:
            e.follow.addresses |= REAL
        for addr in REAL:
            e.unhook(addr)
        self.m.w32(COUNT, 0)
        self.m.w32(CURSOR, 0)
        self.m.w8(0x402791, network)
        self.m.w32(0x41bfb8, Q.BTN_CIRCLE | Q.BTN_SELECT)
        self.m.w32(0x41bfbc, Q.BTN_CROSS)
        D.plant_mission(self.m, 0, {1}, {1}, {1: 3})
        self.m.write(D.PENDING, bytes(0x50))
        self.m.w8(D.ORIENT, 0)
        self.m.w32(D.PAUSED, 0)
        for addr, value in ((0x1eb000, 0), (0x17365c, 0), (0x214230, 0),
                            (0x18ebb8, 0), (0x13e150, 0), (0x13dd40, 1),
                            (0x18cbfc, 0), (0x1df5ec, 0), (0x13e4e8, 0),
                            (0x18df90, 0)):
            e.stub(addr, ret=value, name='explicit menu host')
        self.open(chooser)

    def call(self, addr, *args):
        check(addr not in self.e.hooks, 'original entry unexpectedly stubbed')
        self.e.reset_log()
        result = self.e.call(addr, *args, max_steps=1000000)
        check(not [c.target for c in self.e.calls
                   if c.stubbed and c.target not in self.e.hooks], 'implicit fallback')
        return result

    def compare(self):
        check(D.snap(self.m) == D.model_snap(self.model.fields), 'menu fields differ')
        check(self.m.s8(CHOOSER) == self.model.chooser, 'chooser differs')
        records = [tuple(self.m.u32(TASKS + 16*i + 4*j) for j in range(4))
                   for i in range(self.m.u32(COUNT))]
        expected = [(D.MENU_RUN, 20, RUN_NAME, 0), (DRAW, 20, DRAW_NAME, 1)]
        check(records == (expected if self.model.running else []), 'registry differs')
        for name in (RUN_NAME, DRAW_NAME):
            check(self.call(RUNNING, name) == int(self.model.running), 'task query differs')

    def open(self, chooser=0):
        # Rows are retained by open, even on initial entry; compare after planting.
        if not hasattr(self, 'opened'):
            for address in (D.ROW_AT, D.COL_AT):
                self.m.w8(address, 0)
            self.opened = True
        self.call(D.MENU_OPEN, chooser)
        self.model.open(chooser)
        self.compare()

    def tick(self, button=0, fade=0, active=True):
        self.world.fade, self.world.slot_active = fade, active
        self.m.w32(D.PAD + self.model.chooser * 0x58, button)
        self.e.stub(0x1df5ec, ret=fade, name='controlled fade')
        self.e.stub(0x13dd40, ret=int(active), name='controlled active slot')
        self.call(CALL, 1, -1)  # original run-phase scheduler, not direct calls after death
        calls, writes = list(self.e.calls), list(self.e.writes)
        self.model.tick(button, self.world, bool(self.network))
        self.compare()
        return calls, writes

    def ready(self):
        for _ in range(17):
            self.tick()
        check(self.model.fields['state'] == 2, 'intro did not finish')

    def force(self, **fields):
        addresses = {'state': D.STATE, 'counter': D.COUNTER, 'c0': D.C0,
                     'mark': D.MARK, 'row': D.ROW_AT, 'col': D.COL_AT,
                     'paused': D.PAUSED, 'orient': D.ORIENT}
        for key, value in fields.items():
            addr = addresses[key]
            (self.m.w8 if key in ('state', 'row', 'col', 'orient') else self.m.w32)(addr, value)
        self.model.fields.update(fields)

    def pending(self, value):
        self.m.write(D.PENDING, value.encode() + b'\0')
        self.model.fields['pending'] = value

    def remove(self):
        self.call(REMOVE_MENU)
        self.model.remove()
        self.compare()


def cancellation(elf, seed):
    for network in (0, 1):
        for trigger in ('circle', 'select', 'inactive'):
            r = Rig(elf, seed, network)
            r.ready()
            r.pending('old_request')  # authored sentinel, not a destination from the disc
            button = {'circle': Q.BTN_CIRCLE, 'select': Q.BTN_SELECT, 'inactive': 0}[trigger]
            r.tick(button, active=trigger != 'inactive')
            check(r.model.fields['state'] == 4, 'cancel did not enter closing')
            r.m.w32(0x41b4f8, 1)  # nonzero flag control for the first closing body
            for left in (111, 95, 79, 63, 47, 31, 15, 0):
                calls, writes = r.tick()
                check(r.model.fields['counter'] == left, 'countdown')
                check(r.m.u32(0x41b4f8) == 0 and r.m.u8(0x4f66a8) == 0,
                      'early closing flags')
                check(r.m.u32(0x41b4fc) == int(left != 0), 'input lockout timing')
                removed = [c.args[0] for c in calls if c.target == REMOVE]
                check(removed == ([D.MENU_RUN, DRAW] if left == 0 else []), 'removal timing')
                if left == 0:
                    check([w[3] & 0xffffffff for w in writes if w[1] == D.COUNTER]
                          == [0xffffffff, 0], 'negative then clamp')
                    lock = [c.args[:2] for c in calls if c.target == 0x13e4e8]
                    check(lock == [(0, 5)], 'cancel lock request')
            before = D.snap(r.m)
            calls, _ = r.tick(Q.BTN_CROSS)
            check(not any(c.target == D.MENU_RUN for c in calls), 'terminated menu dispatched')
            check(D.snap(r.m) == before, 'post-termination fields changed')
            r.force(row=7, col=2, mark=55, c0=13)
            r.open()
            check(r.model.fields['pending'] == 'old_request', 'reopen lost pending')
            check((r.m.s8(D.ROW_AT), r.m.s8(D.COL_AT)) == (7, 2), 'open reset selection early')
            r.tick()
            check((r.m.s8(D.ROW_AT), r.m.s8(D.COL_AT)) == (0, 0), 'state zero selection')
    # Exact-zero and conditional close controls are constructed, not claimed reachable.
    for start in (0, 1, 15, 16, 17, 32, 127, 128):
        for c0 in (0, 1, 9):
            r = Rig(elf, seed)
            r.ready()
            r.force(state=4, counter=start, c0=c0)
            steps = start // 16 + 1
            for n in range(steps):
                calls, _ = r.tick()
                check(r.model.running == (n < steps-1 or c0 != 0), 'strict negative boundary')
                check(sum(c.target == 0x18df90 for c in calls) == int(n == steps-1 and c0 != 0),
                      'conditional pause-close request')
            check(r.m.s8(D.STATE) == (5 if c0 else 4), 'conditional closing state')
    print('PASS cancellation: 6 sequences + 24 threshold/branch controls per seed')


def launches(elf, seed):
    for col in (0, 1, 2):
        r = Rig(elf, seed)
        r.ready()
        r.force(col=col)
        r.tick(Q.BTN_CROSS)
        check(r.m.s8(D.STATE) == 5 and r.m.u32(D.C0) == 1, 'accept')
        r.tick()
        for fade in (0, 127, 129, 255):
            r.tick(fade=fade)
            check(r.m.s8(D.STATE) == 6, 'fade must equal 128')
        r.tick(fade=128)
        check(r.m.s8(D.STATE) == 7 and r.model.running, 'fade boundary')
        r.tick()
        check(r.m.s8(D.STATE) == 8 and r.model.running, 'state eight arrival')
        calls, _ = r.tick()
        check(not r.model.running and r.m.s8(D.STATE) == 8, 'state eight body termination')
        check([c.args[0] for c in calls if c.target == REMOVE] == [D.MENU_RUN, DRAW], 'launch remove')
        check(next(i for i,c in enumerate(calls) if c.target == REMOVE)
              < next(i for i,c in enumerate(calls) if c.target == 0x3b868c), 'remove before publish')
        pending = r.m.cstr(D.PENDING)
        r.open()
        check(r.m.cstr(D.PENDING) == pending, 'launch reopen pending')
        r.tick()
        check(r.model.running and r.m.cstr(D.PENDING) == pending, 'running with stale destination')
    for c0 in (0, 1, 9):
        r = Rig(elf, seed)
        r.ready()
        r.force(c0=c0)
        before = D.snap(r.m)
        r.remove()
        check(D.snap(r.m) == before, 'explicit remove mutated fields')
        r.open()
        r.open()  # task_add de-duplicates while open resets the counters
        check(r.m.u32(COUNT) == 2, 'duplicate registrations')
    for chooser in range(4):
        r = Rig(elf, seed)
        r.ready()
        r.force(row=8, col=2, mark=55, c0=9, counter=87, orient=0xfd)
        r.pending('retained')
        r.open(chooser)
        r.ready()
        for _ in range(20):
            r.tick()
        r.tick(Q.BTN_CIRCLE)
        for _ in range(8):
            calls, _ = r.tick()
        check([c.args[:2] for c in calls if c.target == 0x13e4e8] == [(chooser, 5)],
              'reopened chooser not used')
    print('PASS launch/reopen/remove: 3 columns + 3 guards + 4 chooser controls per seed')


def save_hosts(r):
    # Deliberately bounded serializers: no I/O, world serialization or item fixups.
    e, m = r.e, r.m
    for addr, ret in ((0x203918, 0xc4), (0x203a20, 0xc4),
                      (0x27dcf4, 0x1e4), (0x27dd30, 0x1e4),
                      (0x216c80, 0), (0x216ea8, 0), (0x21777c, 0),
                      (0x1ed974, 0), (0x1eda08, 0), (0x1ed728, 0), (0x2180a8, 0),
                      (0x217d30, 0), (0x217edc, 0)):
        e.stub(addr, ret=ret, name='bounded save host')
    e.stub(0x1ec0f0, function=lambda x: x.mem.write(x.r[4], b'checkpoint\0'),
           name='synthetic qualified level')
    m.write(0x41b721, b'checkpoint\0')
    m.w8(0x41b771, 0)
    m.w8(0x4f85c5, 0)
    m.w32(0x4f85b4, 0)
    m.w32(D.G_PLAYERS + 0x43d8, e.alloc(0x100))
    m.write(0x879ec0, bytes(D.REC))
    m.write(SAVE, bytes(SAVE_SIZE))


def save_restore(elf, seed):
    buffers = []
    for phase in ('intro', 'active', 'closing', 'cancelled', 'launched'):
        r = Rig(elf, seed)
        r.tick()
        if phase != 'intro':
            for _ in range(16):
                r.tick()
        if phase in ('closing', 'cancelled'):
            r.tick(Q.BTN_CIRCLE)
            for _ in range(3 if phase == 'closing' else 8):
                r.tick()
        if phase == 'launched':
            r.tick(Q.BTN_CROSS)
            for _ in range(4):
                r.tick(fade=128)
        save_hosts(r)
        before = D.snap(r.m)
        r.e.reads = []
        r.call(BUILD, 0, 0)
        reads = list(r.e.reads)
        r.compare()
        check(D.snap(r.m) == before, 'save_build changed menu')
        # Verify actual main-body read coverage, not absence of a guessed byte pattern.
        check(not any((D.STATE <= a < D.STATE+0x18) or (COUNT <= a < CURSOR+4)
                      or (TASKS <= a < TASKS+32) or (D.PENDING <= a <= D.ORIENT)
                      or a in (D.PAUSED, CHOOSER)
                      for _,a,_,_ in reads), 'build reads menu state')
        blob = r.m.read(SAVE, SAVE_SIZE)
        check(r.m.cstr(SAVE) == 'checkpoint' and r.m.u16(SAVE+0x6a) == 1,
              'build did not execute header/player path')
        buffers.append(blob)
        # Same-process restore preserves *current* lifetime; the buffer has no menu snapshot.
        r.pending('changed_after_save')
        r.force(counter=23, mark=99)
        r.call(LOAD)
        r.model.restore_request('checkpoint')
        r.compare()
        check(r.m.s32(D.COUNTER) == 23 and r.m.s32(D.MARK) == 99, 'load rewound menu')
        r.tick()
        r.open()
        check(r.m.cstr(D.PENDING) == 'checkpoint', 'reopen after load')
        # The identical buffer cannot instantiate a task in another empty task registry.
        fresh = Rig(elf, seed)
        save_hosts(fresh)
        fresh.remove()
        fresh.m.write(SAVE, blob)
        fresh.call(LOAD)
        fresh.model.restore_request('checkpoint')
        fresh.compare()
        check(not fresh.model.running, 'load resurrected menu')
    check(all(b == buffers[0] for b in buffers), 'menu lifecycle leaked into bounded save buffer')
    print('PASS save/restore: 5 phases, same-process + empty-registry restores per seed')


def dialog_controls(elf, iso):
    import difftest_mission_unlocks as U
    image, dialog = U.inputs(elf, iso)
    for phase in ('closing', 'last_positive', 'zero_alive', 'cancelled', 'launch_arrival',
                  'launched', 'reopened', 'restored_active', 'restored_dead', 'removed_active'):
        p = U.Probe(elf, image, dialog, 20973, 3, 0)
        r = Rig(elf, emu=p.rig.emu)
        # Rig mission setup is separate from the authored second-offer input.
        D.plant_mission(r.m, 0, {0, 1}, {0, 1}, {})
        r.ready()
        if phase == 'removed_active':
            r.remove()
        elif phase in ('closing', 'last_positive', 'zero_alive', 'cancelled', 'restored_dead'):
            r.tick(Q.BTN_CIRCLE)
            if phase == 'zero_alive':
                r.force(counter=16)
                r.tick()
            elif phase in ('cancelled', 'restored_dead'):
                for _ in range(8):
                    r.tick()
            elif phase == 'last_positive':
                for _ in range(7):
                    r.tick()
        else:
            r.tick(Q.BTN_CROSS)
            for _ in range(3):
                r.tick(fade=128)
            if phase != 'launch_arrival':
                r.tick()
            if phase in ('reopened', 'restored_active'):
                r.open()
        if phase.startswith('restored'):
            save_hosts(r)
            r.call(BUILD, 0, 0)
            # save_hosts intentionally uses zero synthetic saved players; restore offer bytes.
            r.m.write(SAVE+0x320+14, r.m.read(D.G_PLAYERS, D.REC))
            r.call(LOAD)
            r.model.restore_request('checkpoint')
        # Existing reference host receives model lifetime; original dialog executes real lookup.
        running = r.model.running
        node = p.open(menu=running)
        check(any(c.target == RUNNING and not c.stubbed for c in r.e.calls), 'dialog query stubbed')
        if running:
            check(not p.entered and not p.writes, 'active menu allowed offer')
        else:
            check(node == 7, 'terminated menu did not admit second offer')
            p.confirm()
            check(p.writes == [(0, 2, 1)], 'admitted offer writer')
    print('PASS composed original dialog admission: 10 lifetime controls')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--iso')
    args = parser.parse_args()
    with open(args.elf, 'rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != D.ELF_SHA:
            parser.error('unsupported executable digest')
    for seed in (20973, 7):
        cancellation(args.elf, seed)
        launches(args.elf, seed)
        save_restore(args.elf, seed)
    if args.iso:
        dialog_controls(args.elf, args.iso)
    print('PASS total assertions:', CHECKS)


if __name__ == '__main__':
    main()
