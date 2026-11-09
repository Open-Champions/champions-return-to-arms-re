#!/usr/bin/env python3
"""Original hub list, same-session offer, and hub-return stop for mission 2.

The destination list comes from jumpgate_resetDestinations and
jumpgate_addCurrentLevel. The offer dialog, trigger, and mission menu share
one emulator. Run with unittest preloaded. Private inputs stay under local/.
"""
import argparse
import hashlib
import itertools
import mmap
import os
from pathlib import Path

import ref_mission2 as M
import ref_mission2_compose as C
import ref_mission2_travel as R
import difftest_mission2_offer as O
import difftest_mission2_travel as T
from difftest_mission2 import SHA256, ScriptCheck, props_for, put
from dump_tables import objects_from_file
from ee_emu import MemoryFault
from find_hosts import iso_files
from gob import gob_entries, lmp_entries
import scr

LATCH = 0x4F8F28
RESET, ADD, RESOLVE = 0x27DB00, 0x27DB60, 0x1EC300
READERS = {0x1BF730, 0x1BF8D8, 0x1BF960}
FOUND = 0x8E3A40


class ComposeFollow:
    def __contains__(self, address):
        return address in T.Follow() or address in READERS


def text(rig, address, value):
    rig.text(address, value)


def plant(rig, difficulty, evil, decision, first, second, seed):
    mem = rig.m
    mem.write(T.PLAYERS, bytes(4 * 0x4C30))
    mem.w32(0x4F719C, difficulty)
    mem.w32(0x4D8AE0, 1)
    mem.w32(0x404464, seed)
    mem.w8(T.PLAYERS + 0x4C1A, (evil & 1) << difficulty)
    mem.w8(T.PLAYERS + 0x4C1B, (decision & 1) << difficulty)
    base = T.PLAYERS + 0x4BBF + difficulty * 13
    mem.w8(base + 1, first & 0xFF)
    mem.w8(base + 2, second & 0xFF)
    text(rig, T.SUB, '')


def listed(rig):
    return rig.destinations()


def saw(rig, address):
    return any(call.target == address and not call.stubbed for call in rig.e.calls)


def fresh(executable, image=None):
    rig = T.Rig(executable, image)
    rig.e.follow = ComposeFollow()
    return rig


def check_reset_and_insert(executable, seed):
    cases = 0
    for difficulty, evil, decision, complete1, complete2, latch in itertools.product(
            (0, 4), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)):
        rig = fresh(executable)
        first = 1 | (complete1 << 1)
        second = 1 | (complete2 << 1)
        plant(rig, difficulty, evil, decision, first, second, seed)
        before = rig.m.read(T.PLAYERS, 4 * 0x4C30)
        hub = C.resolver_hub(evil, decision, complete1)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        previous = ['keep', 'also']
        rig.m.w8(LATCH, latch)
        rig.set_destinations(previous)
        rig.e.reset_log()
        rig.call(RESET)
        assert listed(rig) == C.reset_destinations(latch, previous, hub)
        assert saw(rig, RESOLVE) == (not latch)
        assert rig.m.read(T.PLAYERS, len(before)) == before
        assert rig.m.u32(0x404464) == seed
        cases += 1
    # Completion is bit 1, including a row that is not also marked available.
    for first in (0, 1, 2, 3):
        rig = fresh(executable)
        plant(rig, 0, 1, 1, first, 0, seed)
        hub = C.resolver_hub(1, 1, (first & 2) != 0)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        rig.m.w8(LATCH, 0)
        rig.call(RESET)
        assert listed(rig) == [hub]
        cases += 1
    samples = (
        ('hub', [], 'hub2'),
        ('hub', [], 'innovat1'),
        ('hub', ['keep'], 'innovat1'),
        ('hub', ['hub', 'hub2'], 'innovat1'),
        ('hub', ['hub2', 'hub'], 'inmine1'),
        ('hub', ['innovat1', 'hub2', 'hub'], 'innovat2'),
        ('hub', ['hub2'], 'hub'),
        ('hub', ['hub2'], 'hub2'),
        ('hub', ['hub2', 'innovat1'], 'innovat1'),
        ('hub2', [], 'hub'),
        ('hub2', ['hub', 'hub2'], 'innovat1'),
        ('hub2', ['hub2', 'hub'], 'inmine1'),
        ('hub2', ['innovat2', 'hub'], 'hub2'),
        ('hub2', ['innovat1', 'hub2', 'hub'], 'innovat2'),
    )
    for hub, start, current in samples:
        evil = decision = complete1 = int(hub == 'hub2')
        rig = fresh(executable)
        plant(rig, 0, evil, decision, 1 | (complete1 << 1), 1, seed)
        assert rig.m.cstr(rig.call(RESOLVE)) == hub
        rig.set_destinations(start)
        text(rig, T.CURRENT, current)
        text(rig, T.SUB, '')
        rig.e.reset_log()
        rig.call(ADD)
        got = listed(rig)
        assert got == C.add_current(start, current, hub), (hub, start, current, got)
        # The resolver runs only when a new name is being considered and some
        # name involved is exactly one of the two hub names. A repeated current
        # level returns before that call.
        involved = current not in start and any(
            name in C.HUBS for name in (current, *start))
        called = sorted({hex(c.target) for c in rig.e.calls if not c.stubbed})
        assert saw(rig, RESOLVE) == involved, (hub, start, current, called)
        assert saw(rig, 0x1EC0F0)
        cases += 1
    for hub in C.HUBS:
        rig = fresh(executable)
        evil = decision = complete1 = int(hub == 'hub2')
        plant(rig, 0, evil, decision, 1 | (complete1 << 1), 1, seed)
        rig.m.w8(LATCH, 0)
        text(rig, T.CURRENT, hub)
        rig.call(RESET)
        for level in M.LEVELS:
            text(rig, T.CURRENT, level)
            rig.call(ADD)
        assert listed(rig) == C.route_list(hub, M.LEVELS)
        text(rig, T.CURRENT, M.LEVELS[-1])
        cases += 1
    return cases


def portal_return(executable, fixture, seed):
    image, check, rows = fixture
    row = rows[57]
    assert isinstance(check, ScriptCheck)
    assert M.FACTORY[row['class'].lower()][1] == 0x27C694
    gate_key = check.call_values(0x13C, 'getv', 1, (0,))[0]
    cases = snapshots = 0
    # Difficulty 0 covers both hubs; difficulty 4 covers the evil row only.
    plans = ((0, 0, 0, 1), (0, 1, 1, 1), (4, 1, 1, 1))
    for difficulty, evil, decision, complete1 in plans:
        for gate in (0, 1):
            rig = fresh(executable, image)
            for addr in (0x173C84, 0x1D92A0, 0x19E854, 0x1EB000, 0x17365C,
                         0x214230, 0x13E4E8, 0x13E150, 0x18CBFC):
                rig.stub(addr)
            plant(rig, difficulty, evil, decision, 1 | (complete1 << 1), 1, seed)
            hub = C.resolver_hub(evil, decision, complete1)
            rig.m.w8(LATCH, 0)
            text(rig, T.CURRENT, hub)
            rig.call(RESET)
            for level in M.LEVELS:
                text(rig, T.CURRENT, level)
                rig.call(ADD)
            built = listed(rig)
            assert built == C.route_list(hub, M.LEVELS)
            before = rig.m.read(T.PLAYERS, 4 * 0x4C30)
            text(rig, T.PENDING, '')
            rig.m.w32(0x4F8450, rig.e.alloc(0x80))
            rig.m.w32(T.ALIVE, 1)
            rig.m.w32(0x4F8440, 0)
            rig.m.w8(T.NETWORK, 0)
            rig.m.w32(0x4FE53C, 0)
            rig.m.w32(0x41BFB8, 1)
            rig.m.w32(0x41BFBC, 2)
            obj = rig.e.alloc(0x180)
            rig.m.w32(obj + 0x2C, props_for(rig.e, row))
            rig.call(0x1ED854, put(rig.e, gate_key), gate)
            ready = rig.call(0x27D7A0, obj, rig.e.alloc(0x200), 0)
            assert listed(rig) == built
            assert (ready, rig.m.u8(obj + 0x4D)) == (gate, gate)
            if not ready:
                assert rig.m.cstr(T.PENDING) == '' and rig.m.u32(T.TASK_COUNT) == 0
                cases += 1
                continue
            rig.call(0x27D754, obj, 0)
            rig.call(0x27DD74)
            for _ in range(16):
                rig.call(0x27DD74)
            assert rig.m.u8(T.STATE) == 2
            assert rig.m.u32(FOUND) == built.index(M.LEVELS[-1])
            # Explicit row selection, not a claim about pad navigation.
            rig.m.w8(T.CHOICE, 0)
            rig.m.w32(0x41BFE4, 2)
            rig.call(0x27DD74)
            assert (rig.m.u8(T.STATE), rig.m.u32(T.COUNTER)) == R.menu_choice(0, 1, False)
            rig.m.w32(0x41BFE4, 0)
            for _ in range(8):
                rig.call(0x27DD74)
            assert rig.m.u8(T.STATE) == 4
            rig.call(0x27DD74)
            for _ in range(181):
                expected = R.travel_counter(
                    rig.m.u32(T.COUNTER), rig.m.cstr(T.PENDING), hub, rig.m.u8(T.ORIENT))
                rig.call(0x27DD74)
                assert (rig.m.u8(T.STATE), rig.m.u32(T.COUNTER),
                        rig.m.cstr(T.PENDING), rig.m.u8(T.ORIENT)) == expected
                snapshots += 1
            assert rig.m.cstr(T.PENDING) == hub and rig.m.u8(T.ORIENT) == 255
            assert listed(rig) == built
            assert rig.m.read(T.PLAYERS, len(before)) == before
            assert rig.m.u32(0x404464) == seed
            boundary(rig, hub, M.LEVELS[-1])
            cases += 1
    return cases, snapshots


def boundary(rig, pending, current):
    """Same pre-load stop as the retained travel test. Act-change stays stubbed off."""
    for address in (0x19D9F8, 0x21777C, 0x217F70, 0x2247EC, 0x216588):
        rig.stub(address)

    def stop(emu):
        assert emu.mem.cstr(emu.r[4] & 0xFFFFFFFF) == pending
        raise T.Boundary()

    rig.e.hook(0x1E55C0, stop)
    try:
        rig.call(0x320EDC)
        raise AssertionError('load boundary was not reached')
    except T.Boundary:
        pass
    assert (rig.m.cstr(T.PENDING), rig.m.cstr(T.CURRENT), rig.m.cstr(T.SUB),
            rig.m.cstr(T.PREVIOUS), rig.m.u8(T.ORIENT), rig.m.u8(0x41B7C1)) == R.request_names(
                pending, current, '', 255)
    assert rig.e.pc == 0x1E55C0
    rig.e.unhook(0x1E55C0)


MENU_REAL = {
    0x14DCC8, 0x231520, 0x2316FC, 0x19E4A0, 0x19E5E8, 0x19E664, 0x19E760,
    0x19E798, 0x1EC5D0, 0x320EDC, 0x1E55C0, 0x22FBC0,
}
QUESTS = 0x86DA80
RUN_NAME, DIALOG_NAME = 0x5410E8, 0x540C70


def prepare_menu(probe):
    probe.rig.emu.follow.addresses |= set(O.S.MENU_FOLLOW) | MENU_REAL
    for address in (0x17365C, 0x214230, 0x1EB000, 0x13E150, 0x18CBFC, 0x18EBB8):
        probe.rig.emu.stub(address, ret=0, name='explicit menu host')
    probe.rig.emu.stub(0x13DD40, ret=1, name='active slot')
    probe.rig.emu.stub(0x1DF5EC, ret=0, name='fade')
    for address in MENU_REAL:
        probe.rig.emu.unhook(address)


def close_dialog(probe):
    assert probe.mem.u8(O.H.D.A['anm_ready']) == 1
    probe.model.on_end(probe.model_host)
    probe.dialog.message([O.H.R.MSG_END])
    probe.compare()
    probe.rig.emu.unhook(0x22FBC0)
    assert probe.rig.call(0x22FBC0) == 0
    assert probe.mem.u32(T.TASK_COUNT) == 0


def changed_prefix(before, after):
    assert len(before) == len(after)
    diffs = [i for i in range(len(before)) if before[i] != after[i]]
    assert diffs == list(range(15))


def reopen(probe, hub, actor, controls, admitted):
    probe.entered, probe.writes = [], []
    probe.dialog.host.mission_menu = probe.model_host.mission_menu = int(not admitted)
    probe.mem.write(0x41B721, hub.encode('latin1') + b'\0')
    msg = O.H.R.start_message(actor, 0, *controls, (0, 0, 0), 0, 0)
    probe.model.on_open(probe.model_host, msg, probe.nodes, level=hub)
    probe.dialog.message(msg)
    probe.compare()
    queries = [c for c in probe.rig.emu.calls if c.target == 0x19E5E8 and not c.stubbed]
    assert queries and queries[0].args[0] == DIALOG_NAME
    assert probe.mem.cstr(DIALOG_NAME) == probe.mem.cstr(RUN_NAME)
    return probe.mem.s32(O.H.D.A['node_index'])


def offer_session(executable, iso, seed):
    image, dialog, hub, actor, controls, row, key = O.inputs(executable, iso)
    probe = O.H.Probe(executable, image, dialog, seed, 3, 0, 0)
    before = probe.mem.read(O.H.PLAYER, O.H.STRIDE * 4)
    assert O.open_bound(probe, hub, actor, controls) == O.R.node(3, 0)
    assert not probe.writes
    probe.confirm(0)
    assert probe.writes == [(0, 2, 1)]
    close_dialog(probe)
    granted = bytearray(before)
    granted[O.H.MISSION + 2] |= 1
    assert probe.mem.read(O.H.PLAYER, len(granted)) == bytes(granted)
    prepare_menu(probe)
    assert probe.run_entry(key) == 1
    quests = probe.mem.read(QUESTS, 0x2000)
    obj = probe.rig.emu.alloc(0x80)
    probe.mem.w32(obj + 0x2C, props_for(probe.rig.emu, row))
    probe.rig.call(0x14DCC8, obj, 1)
    changed_prefix(quests, probe.mem.read(QUESTS, 0x2000))
    probe.game.mem.write(QUESTS, probe.mem.read(QUESTS, 0x2000))
    assert probe.mem.u32(T.TASK_COUNT) == 2
    assert probe.mem.u32(T.TASKS) == 0x2316FC and probe.mem.u32(T.TASKS + 8) == RUN_NAME
    check = ScriptCheck(image)
    entrance = check.call_values(0x4A44, 'setEntrance', 1, (0,))[0]
    assert probe.mem.cstr(0x4F8468) == entrance
    model = O.SREF.new_menu()
    model['orient'] = probe.mem.u8(O.S.ORIENT)
    carried = probe.mem.read(O.H.PLAYER, O.H.STRIDE * 4)
    carried_quests = probe.mem.read(QUESTS, 0x2000)
    destination = probe.mem.cstr(probe.mem.u32(0x4FE540 + 0x34 + 8))
    assert destination == 'innovat1'
    for tick in range(26):
        button = 0x40 if tick == 17 else 0
        fade = 128 if tick >= 22 else 0
        probe.mem.w32(0x41BFE4, button)
        probe.rig.emu.stub(0x1DF5EC, ret=fade, name='fade')
        probe.rig.call(0x2316FC)
        O.R.menu_tick(model, button, True, destination, fade)
        assert O.S.snap(probe.mem) == O.S.model_snap(model)
        assert probe.mem.read(O.H.PLAYER, len(carried)) == carried
    assert probe.mem.cstr(O.S.PENDING) == destination and probe.mem.u8(O.S.ORIENT) == 255
    assert probe.mem.read(QUESTS, 0x2000) == carried_quests
    for address in (0x19D9F8, 0x21777C, 0x217F70, 0x2247EC, 0x216588):
        probe.rig.emu.stub(address, ret=0, name='boundary host')

    def stop(emu):
        assert emu.mem.cstr(emu.r[4] & 0xFFFFFFFF) == destination
        raise T.Boundary()

    probe.rig.emu.hook(0x1E55C0, stop)
    try:
        probe.rig.call(0x320EDC)
        raise AssertionError('offer load boundary was not reached')
    except T.Boundary:
        pass
    assert (probe.mem.cstr(T.PENDING), probe.mem.cstr(T.CURRENT), probe.mem.cstr(T.SUB),
            probe.mem.cstr(T.PREVIOUS), probe.mem.u8(T.ORIENT), probe.mem.u8(0x41B7C1)) == R.request_names(
                destination, hub, '', 255)
    assert probe.mem.read(O.H.PLAYER, len(carried)) == carried
    assert probe.mem.read(QUESTS, 0x2000) == carried_quests
    assert probe.rig.emu.pc == 0x1E55C0
    return carried_quests


def admit_session(executable, iso, seed):
    """16 is the constructed start that lands on a still-registered 0.

    15 is the last positive countdown value from e5c6176. This does not
    remeasure that countdown.
    """
    image, dialog, hub, actor, controls, row, key = O.inputs(executable, iso)
    probe = O.H.Probe(executable, image, dialog, seed, 3, 0, 0)
    assert O.open_bound(probe, hub, actor, controls) == 7
    probe.confirm(0)
    close_dialog(probe)
    prepare_menu(probe)
    assert probe.run_entry(key) == 1
    obj = probe.rig.emu.alloc(0x80)
    probe.mem.w32(obj + 0x2C, props_for(probe.rig.emu, row))
    probe.rig.call(0x14DCC8, obj, 1)
    probe.game.mem.write(QUESTS, probe.mem.read(QUESTS, 0x2000))
    name = probe.mem.u32(T.TASKS + 8)
    probe.mem.w8(0x8E2EFC, 4)
    probe.mem.w32(0x8E2F04, 16)
    probe.mem.w32(0x8E2F00, 0)
    probe.mem.w32(0x41BFE4, 0)
    probe.rig.call(0x2316FC)
    assert probe.mem.s32(0x8E2F04) == 0 and probe.mem.u32(T.TASK_COUNT) == 2
    assert probe.rig.call(0x19E5E8, name) == 1
    assert not C.scripts_admitted(True)
    node = reopen(probe, hub, actor, controls, admitted=False)
    assert node == 7 and not probe.entered and not probe.writes
    probe.rig.call(0x2316FC)
    assert probe.mem.s32(0x8E2F04) == 0 and probe.mem.u8(0x8E2EFC) == 4
    assert probe.mem.u32(T.TASK_COUNT) == 0
    assert probe.rig.call(0x19E5E8, name) == 0
    assert C.scripts_admitted(False)
    assert reopen(probe, hub, actor, controls, admitted=True) == O.R.node(3, 1)
    probe.confirm(1)
    assert not probe.writes


def lump_files(blob, level):
    for name, off, size in gob_entries(blob):
        if name.lower() == level + '.lmp':
            lump = blob[off:off + size]
            return {entry: lump[at:at + n] for entry, at, n in lmp_entries(lump)}
    raise AssertionError('level lump missing')


def archive(iso, level):
    with open(iso, 'rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        matches = [item for item in iso_files(disc)
                   if os.path.basename(item[0]).lower() == level + '.gob']
        assert len(matches) == 1
        _path, lba, size = matches[0]
        return disc[lba * 2048:lba * 2048 + size]


def hub2_boundary(iso):
    hub_image = next(value for name, value in lump_files(archive(iso, 'hub'), 'hub').items()
                     if name.lower().endswith('.scr'))
    blob = archive(iso, 'hub2')
    files = lump_files(blob, 'hub2')
    image = next(value for name, value in files.items() if name.lower().endswith('.scr'))
    check = ScriptCheck(image)
    rows = objects_from_file('hub2.gob', blob)
    assert image != hub_image
    assert 0x7B0 not in set(check.entries.values())
    assert 0x734 not in set(check.entries.values())
    npc = [row for row in rows if row['class'] == 'NPC']
    trigger = [row for row in rows if row['class'] == 'PushTrigger']
    assert len(npc) == len(trigger) == 1
    assert any(item.startswith('dialogscript=') for item in npc[0]['properties'].split(';'))
    entries = {name: off for off, name in scr.parse(image)['internals']}
    props = trigger[0]['properties'].split(';')
    action = entries[next(item[7:] for item in props if item.startswith('action='))]
    key = entries[next(item[4:] for item in props if item.startswith('key='))]
    assert (action, key) == (0x54, 0x98)
    assert len(rows) == 21
    return len(rows)


HELPER, HELPER_CALL = 0x18EBB8, 0x2319A4


def observe_helper_fault(executable, iso, seed):
    """Enter the menu helper from its jal once. Other effects stay unknown."""
    image, dialog, hub, actor, controls, row, key = O.inputs(executable, iso)
    probe = O.H.Probe(executable, image, dialog, seed, 3, 0, 0)
    assert O.open_bound(probe, hub, actor, controls) == O.R.node(3, 0)
    probe.confirm(0)
    close_dialog(probe)
    prepare_menu(probe)
    assert probe.run_entry(key) == 1
    obj = probe.rig.emu.alloc(0x80)
    probe.mem.w32(obj + 0x2C, props_for(probe.rig.emu, row))
    probe.rig.call(0x14DCC8, obj, 1)
    emu = probe.rig.emu
    emu.unhook(HELPER)
    emu.follow.addresses.add(HELPER)
    try:
        probe.rig.call(0x2316FC)
    except MemoryFault as fault:
        entered = [call for call in emu.calls if call.target == HELPER and not call.stubbed]
        assert len(entered) == 1 and entered[0].site == HELPER_CALL, (fault, entered)
        assert (fault.pc, fault.addr, fault.size, fault.kind) == (
            0x18EC10, 0x4, 4, 'write'), fault
        line = ('Observed: helper 0x18ebb8 from 0x2319a4 on the menu image faults on a %s '
                'of %d byte(s) at 0x%08x (pc 0x%08x)'
                % (fault.kind, fault.size, fault.addr, fault.pc))
        print(line)
        Path('local/mission2-compose-helper-%d.log' % seed).write_text(line + '\n')
        return fault
    raise AssertionError('unstubbed helper 0x18ebb8 returned')


QUEST_VARS = 0x86DA80
POOL_INIT, POOL_NEW, OBJECT_CTOR = 0x14FCD8, 0x14FDB8, 0x14CB10
STATIC_INIT, PARTICLE_INIT, SET_DEFAULTS, CLAIM = 0x195D30, 0x18E648, 0x18F360, 0x195BB0
SLOT_USED, TYPE_PTR = 0x82C408, 0x82C4E8
GROUP_HANDLE, TRAIL_HANDLE = 0x7E1D50 + 0x130, 0x82CD00 + 0x400
GROUP_GEN, TRAIL_GEN, TRAIL_GATE = 0x44FC9C, 0x44FCA4, 0x44FC98
EMPTY_FN, TRAIL_RESET, GROUP_RESET = 0x18EBB0, 0x1929C8, 0x18E840


def boot_particles(executable):
    from ee_emu import EE
    emu = EE(executable)
    emu.record_writes = False
    emu.stub(0x19E4A0, ret=0, name='task')
    emu.stub(0x173768, ret=0, name='resource')
    emu.call(STATIC_INIT, 1, 0xFFFF)
    emu.call(PARTICLE_INIT)
    return emu


def helper_effects(executable):
    """particle_resetAll after the original pool init. The menu image is separate."""
    from ee_emu import EE
    for gate in (0, 1):
        emu = boot_particles(executable)
        mem = emu.mem
        mem.w32(TRAIL_GATE, gate)
        mem.w32(GROUP_HANDLE, 9)
        mem.w32(TRAIL_HANDLE, 6)
        mem.w32(GROUP_GEN, 4)
        mem.w32(TRAIL_GEN, 4)
        emu.reset_log()
        assert emu.call(HELPER) & 0xFFFFFFFF == 1
        slots = [mem.s32(SLOT_USED + 4 * i) for i in range(32)]
        assert slots[0] == 1 and slots[1:] == [-1] * 31
        assert mem.u32(GROUP_HANDLE) == 0 and mem.u32(TRAIL_HANDLE) == 0
        assert mem.u32(GROUP_GEN) == 1 and mem.u32(TRAIL_GEN) == 1
        targets = [call.target for call in emu.calls]
        assert targets == ([EMPTY_FN] if gate else []) + [TRAIL_RESET, GROUP_RESET]
    emu = EE(executable)
    emu.record_writes = False
    defn = emu.alloc(0x80)
    emu.call(SET_DEFAULTS, defn)
    assert emu.mem.u32(defn + 0x28) == defn
    boot = boot_particles(executable)
    # setDefaults result is an address in another image. Repeat it there.
    held = boot.alloc(0x80)
    boot.call(SET_DEFAULTS, held)
    assert boot.mem.u32(held + 0x28) == held
    assert boot.call(CLAIM, held) & 0xFFFFFFFF == 1
    slot = boot.mem.s32(held + 4)
    assert slot == 1
    assert boot.mem.u32(TYPE_PTR) == held
    boot.reset_log()
    assert boot.call(HELPER) & 0xFFFFFFFF == 1
    assert boot.mem.s32(held + 4) == -1 and boot.mem.s32(held + 8) == 0
    assert boot.mem.s32(SLOT_USED + 4) == -1
    assert [call.target for call in boot.calls] == [TRAIL_RESET, GROUP_RESET]


class LoaderFollow:
    def __contains__(self, address):
        return address == 0x1E55C0 or 0x3B0000 <= address < 0x3C0000


def loader_prefix(executable, seed):
    """Enter game_loadLevel. Disc, audio and graphics stay stubbed."""
    from ee_emu import EE, MemoryFault
    emu = EE(executable)
    emu.record_writes = False
    emu.follow = LoaderFollow()
    emu.stub(0x19D9F8, ret=0, name='stack')
    emu.mem.w32(0x404464, seed)
    name = emu.alloc(16)
    emu.mem.write(name, b'innovat1\0')
    try:
        emu.call(0x1E55C0, name, max_steps=400000)
        raise AssertionError('loader returned without the archive fault')
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.size, fault.kind) == (
            0x1E59AC, 0x4, 4, 'read'), fault
    sites = [call.site for call in emu.calls]
    assert 0x1E5738 not in sites
    assert any(call.site == 0x1E57EC and not call.stubbed for call in emu.calls)
    assert emu.mem.u32(0x4F7198) == 1
    assert emu.mem.u32(0x404460) == 0 and emu.mem.u32(0x404464) == seed
    lump = [call for call in emu.calls if call.target == 0x173558]
    found = [call for call in emu.calls if call.target == 0x171FD8]
    assert lump and all(call.stubbed and call.ret == 0 for call in lump)
    assert any(call.site == 0x1E5988 for call in lump)
    assert len(found) == 1 and found[0].stubbed and found[0].ret == 0
    assert found[0].site == 0x1E599C
    assert 0x173558 not in LoaderFollow() and 0x171FD8 not in LoaderFollow()
    assert len(sites) == 163
    return len(sites)


RECORD, STRIDE = 0x4D8AF0, 0x4C30
SLOT_WORD, MARK_WORD = 0x3C8, 0x540
FREE_HEAD = 0x864EA8


def interact_without_player(executable):
    """A zero hit-point float returns the record address. The box query is not called."""
    from ee_emu import EE
    emu = EE(executable)
    emu.record_writes = False
    emu.record_calls = True
    pad = emu.alloc(32)
    player = emu.alloc(0x580)
    emu.mem.w32(player + MARK_WORD, 0)
    emu.mem.w32(player + SLOT_WORD, 0)
    emu.r[2] = 0xA5A5A5A5
    ret = emu.call(0x1B2640, player, pad, 0, max_steps=100000) & 0xFFFFFFFF
    assert emu.calls == []
    assert ret == RECORD
    emu.reset_log()
    emu.mem.w32(player + SLOT_WORD, 1)
    emu.r[2] = 0xA5A5A5A5
    ret = emu.call(0x1B2640, player, pad, 0, max_steps=100000) & 0xFFFFFFFF
    assert emu.calls == []
    assert ret == RECORD + STRIDE


def ctor_null_head(executable):
    """The constructor store at 0x1a1780 uses a null free-list head."""
    from ee_emu import EE, MemoryFault
    emu = EE(executable)
    emu.record_writes = False
    assert emu.mem.u32(FREE_HEAD) == 0
    emu.call(POOL_INIT)
    assert emu.mem.u32(FREE_HEAD) == 0
    block = emu.call(POOL_NEW, 0x80) & 0xFFFFFFFF
    assert block
    try:
        emu.call(OBJECT_CTOR, block, emu.alloc(16), 0, 0)
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.size, fault.kind) == (
            0x1A1780, 0, 4, 'write'), fault
        return
    raise AssertionError('object ctor returned without the null link-head store')


def zero_quests(probe):
    blank = bytes(0x2000)
    probe.mem.write(QUEST_VARS, blank)
    probe.game.mem.write(QUEST_VARS, blank)


def hub2_inputs(iso):
    blob = archive(iso, 'hub2')
    files = lump_files(blob, 'hub2')
    image = next(value for name, value in files.items() if name.lower().endswith('.scr'))
    check = ScriptCheck(image)
    parsed = scr.parse(image)
    native = check.natives.index('startDialog')
    code_lo, code_hi = parsed['code']
    actor = controls = None
    for off in range(0, code_hi - code_lo, 4):
        if check.word(off) == 0x7B and check.word(off + 4) == native:
            vals = check.call_values(off, 'startDialog', 3, (0,))
            if vals[0] + '.dbin' in files:
                actor, controls = vals[0], (vals[1], vals[2])
    assert actor and controls == (1, 0)
    assert len(actor) == 7
    rows = objects_from_file('hub2.gob', blob)
    npc = next(row for row in rows if row['class'] == 'NPC')
    entries = {name: off for off, name in parsed['internals']}
    dialog_name = next(item[13:] for item in npc['properties'].split(';')
                       if item.startswith('dialogscript='))
    assert entries[dialog_name] == 0
    return image, files[actor + '.dbin'], actor, controls, check


def bind_hub2(probe, actor):
    obj = probe.dialog.host.objects.pop('actor')
    probe.dialog.host.objects[actor] = obj


def plant_row(probe, row):
    raw = bytes(row)
    assert len(raw) == 13
    for mem in (probe.mem, probe.game.mem):
        mem.write(O.H.PLAYER + O.H.MISSION, raw)


def open_hub2(probe, actor, controls, row):
    zero_quests(probe)
    plant_row(probe, row)
    probe.entered, probe.writes, probe.native_calls = [], [], []
    probe.mem.write(0x41B721, b'hub2\0')
    msg = O.H.R.start_message(actor, 0, *controls, (0, 0, 0), 0, 0)
    probe.model.on_open(probe.model_host, msg, probe.nodes, level='hub2')
    probe.dialog.message(msg)
    probe.compare()
    return probe.mem.s32(O.H.D.A['node_index']), len(probe.model.visible)


def hub2_play(executable, iso, seed):
    image, dialog, actor, controls, check = hub2_inputs(iso)
    probe = O.H.Probe(executable, image, dialog, seed, 0, 0, 0)
    bind_hub2(probe, actor)
    # choice 0, and choice 1 when the cold node shows two. Last entered offset,
    # landing node, mission-byte indexes that change, availability writes.
    expected = {
        (0, 0, 0): (0x29BC, 2, (), ()),
        (0, 2, 0): (0x29BC, 2, (), ()),
        (3, 0, 0): (0x29BC, 3, (), ()),
        (3, 2, 0): (0x29BC, 3, (), ()),
        (0, 1, 0): (0x41B4, 4, (), ()),
        (3, 1, 0): (0x41B4, 4, (), ()),
        (0, 1, 1): (0x2C54, 4, (), ()),
        (3, 1, 1): (0x2C54, 4, (), ()),
        (0, 3, 0): (0x2DD8, 5, (3,), ((0, 3, 1),)),
        (3, 3, 0): (0x2DD8, 5, (3,), ((0, 3, 1),)),
        (0, 3, 1): (0x42C8, 5, (3,), ((0, 3, 1),)),
        (3, 3, 1): (0x42C8, 5, (3,), ((0, 3, 1),)),
    }
    for first in (0, 3):
        for second in (0, 1, 2, 3):
            row = [3, first, second] + [0] * 10
            node, visible = open_hub2(probe, actor, controls, row)
            assert (node, visible) == C.hub2_cold_dialog(second), (first, second, node, visible)
            for choice in range(visible):
                open_hub2(probe, actor, controls, row)
                before = probe.mem.read(O.H.PLAYER + O.H.MISSION, 13)
                probe.confirm(choice)
                after = probe.mem.read(O.H.PLAYER + O.H.MISSION, 13)
                changed = tuple(i for i, (a, b) in enumerate(zip(before, after)) if a != b)
                entered = [x for x in probe.entered if isinstance(x, int)]
                got = (entered[-1], probe.mem.s32(O.H.D.A['node_index']),
                       changed, tuple(probe.writes))
                assert got == expected[(first, second, choice)], (first, second, choice, got)
    # Trigger key and action on a probe that has not opened the dialog.
    bare = O.H.Probe(executable, image, dialog, seed, 0, 0, 0)
    cases = 0
    samples = []
    base = [3] + [0] * 12
    samples.append(base)
    for index, value in ((1, 1), (1, 3), (2, 1), (2, 2), (2, 3), (11, 1), (11, 3),
                         (12, 1), (12, 2), (12, 3)):
        row = base[:]
        row[index] = value
        samples.append(row)
    samples.append([3] * 13)
    for row in samples:
        plant_row(bare, row)
        bare.entered, bare.native_calls = [], []
        got = bare.run_entry(0x98) & 0xFFFFFFFF
        assert got == C.hub2_trigger_key(row), (row, got)
        cases += 1
    planted = [3, 0, 1] + [0] * 10
    gate = O.H.Probe(executable, image, dialog, seed, 0, 0, 0, mission_bytes=bytes(planted))
    assert gate.run_entry(0x1A84) & 0xFFFFFFFF == C.hub2_action_gate(planted, [0] * 12)
    action = O.H.Probe(executable, image, dialog, seed, 0, 0, 0)
    plant_row(action, planted)
    action.native_calls = []
    action.entered = []
    action.rig.emu.reset_log()
    assert action.run_entry(0x54) & 0xFFFFFFFF == 0
    assert 'setEntrance' in action.native_calls and 'activateMissionMenu' in action.native_calls
    opened_dialog = [call for call in action.rig.emu.calls if call.target == 0x22FBC0]
    menu = [call for call in action.rig.emu.calls if call.target == 0x231520]
    assert len(opened_dialog) == 1 and opened_dialog[0].stubbed
    assert opened_dialog[0].site == 0x143FB0
    # dialog_isOpen is the seeded responder, not the original function.
    if opened_dialog[0].ret == 0:
        assert len(menu) == 1 and menu[0].stubbed and menu[0].ret == 0 and menu[0].site == 0x143FF8
    else:
        assert menu == []
    assert (seed, opened_dialog[0].ret) in ((20973, 0), (7, 1)), (seed, opened_dialog[0].ret)
    entrance = action.mem.cstr(0x4F8468)
    assert entrance == 'evilstart', entrance
    variable = check.call_values(0x1B9C, 'getv', 1, (0,))[0].encode('latin1')
    assert len(variable) == 15
    opened = [0] * 12
    opened[1] = 1
    true_row = O.H.Probe(executable, image, dialog, seed, 0, 0, 0,
                         variables=((variable, 1),), mission_bytes=bytes(planted))
    assert true_row.run_entry(0x1A84) & 0xFFFFFFFF == C.hub2_action_gate(planted, opened)
    true_row.native_calls = []
    true_row.entered = []
    true_row.rig.emu.reset_log()
    assert true_row.run_entry(0x54) & 0xFFFFFFFF == 0
    assert 'setEntrance' not in true_row.native_calls
    assert 'activateMissionMenu' not in true_row.native_calls
    assert 0x22D0 in true_row.entered
    assert 'addHelpMessage' in true_row.native_calls and 'addDeferedCall' in true_row.native_calls
    complete = planted[:]
    complete[2] = 3
    closed = O.H.Probe(executable, image, dialog, seed, 0, 0, 0,
                       variables=((variable, 1),), mission_bytes=bytes(complete))
    assert closed.run_entry(0x1A84) & 0xFFFFFFFF == 0
    closed.native_calls = []
    closed.rig.emu.reset_log()
    assert closed.run_entry(0x54) & 0xFFFFFFFF == 0
    assert 'setEntrance' in closed.native_calls and 'activateMissionMenu' in closed.native_calls
    # After the mission-1-complete choice, the stored variable selects node 3.
    for choice, entry in ((0, 0x2B6C), (1, 0x4224)):
        follow = O.H.Probe(executable, image, dialog, seed, 0, 0, 0)
        bind_hub2(follow, actor)
        row = [3, 3, 0] + [0] * 10
        open_hub2(follow, actor, controls, row)
        follow.confirm(0)
        follow.entered, follow.writes = [], []
        msg = O.H.R.start_message(actor, 0, *controls, (0, 0, 0), 0, 0)
        follow.model.on_open(follow.model_host, msg, follow.nodes, level='hub2')
        follow.dialog.message(msg)
        follow.compare()
        assert follow.mem.s32(O.H.D.A['node_index']) == 3
        assert len(follow.model.visible) == 2
        follow.confirm(choice)
        entered = [x for x in follow.entered if isinstance(x, int)]
        assert follow.writes == [(0, 2, 1)], follow.writes
        assert follow.mem.u8(O.H.PLAYER + O.H.MISSION + 2) == 1
        assert entered[-1] == entry, (choice, [hex(x) for x in entered])
    return cases, entrance


def free_head_untouched(executable):
    """Neither pool_init nor pool_new stores the free-list head 0x864ea8."""
    from ee_emu import EE
    planted = EE(executable)
    planted.record_writes = False
    planted.mem.w32(FREE_HEAD, 0xA5A5A5A5)
    planted.call(POOL_INIT)
    assert planted.mem.u32(FREE_HEAD) == 0xA5A5A5A5
    planted.mem.w32(FREE_HEAD, 0x5A5A5A5A)
    assert planted.call(POOL_NEW, 0x80) & 0xFFFFFFFF
    assert planted.mem.u32(FREE_HEAD) == 0x5A5A5A5A
    emu = EE(executable)
    emu.record_writes = True
    emu.write_watch = ((FREE_HEAD, 4),)
    emu.reset_log()
    assert emu.mem.u32(FREE_HEAD) == 0
    emu.call(POOL_INIT)
    assert emu.writes == [] and emu.mem.u32(FREE_HEAD) == 0
    assert emu.call(POOL_NEW, 0x80) & 0xFFFFFFFF
    assert emu.writes == [] and emu.mem.u32(FREE_HEAD) == 0
    return True


def run(executable, source, iso, seed):
    assert hashlib.sha256(Path(executable).read_bytes()).hexdigest() == SHA256
    fixtures = T.inputs(Path(source))
    listed_cases = check_reset_and_insert(executable, seed)
    portal_cases, snapshots = portal_return(executable, fixtures[3], seed)
    offer_session(executable, iso, seed)
    admit_session(executable, iso, seed)
    observe_helper_fault(executable, iso, seed)
    helper_effects(executable)
    sites = loader_prefix(executable, seed)
    interact_without_player(executable)
    ctor_null_head(executable)
    free_head_untouched(executable)
    key_cases, entrance = hub2_play(executable, iso, seed)
    hub_records = hub2_boundary(iso) if seed == 20973 else 0
    print('PASS seed=%d route-list cases=%d portal returns=%d counter comparisons=%d' % (
        seed, listed_cases, portal_cases, snapshots))
    print('PASS seed=%d same-session offer, menu request, load stop, and counter-0 admission' % seed)
    print('PASS seed=%d helper reset, loader sites=%d, hub2 key cases=%d' % (
        seed, sites, key_cases))
    print('PASS seed=%d free-list head 0x864ea8: no store from pool_init or pool_new, '
          'planted sentinels kept' % seed)
    if hub_records:
        print('PASS hub2 records=%d; ordinary-hub offer entries are absent' % hub_records)
    print('LIMIT in-range physical use, the loader body after the stubbed archive lookup, '
          'arrival, and destination-list save/load remain open')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('source')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.source, args.iso, args.seed)


if __name__ == '__main__':
    main()
