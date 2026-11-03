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


def run(executable, source, iso, seed):
    assert hashlib.sha256(Path(executable).read_bytes()).hexdigest() == SHA256
    fixtures = T.inputs(Path(source))
    listed_cases = check_reset_and_insert(executable, seed)
    portal_cases, snapshots = portal_return(executable, fixtures[3], seed)
    offer_session(executable, iso, seed)
    admit_session(executable, iso, seed)
    hub_records = hub2_boundary(iso) if seed == 20973 else 0
    print('PASS seed=%d route-list cases=%d portal returns=%d counter comparisons=%d' % (
        seed, listed_cases, portal_cases, snapshots))
    print('PASS seed=%d same-session offer, menu request, load stop, and counter-0 admission' % seed)
    if hub_records:
        print('PASS hub2 records=%d; ordinary-hub offer entries are absent' % hub_records)
    print('LIMIT physical use, helper 0x18ebb8, hub2 dialog choices, loader body, and arrival remain open')


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
