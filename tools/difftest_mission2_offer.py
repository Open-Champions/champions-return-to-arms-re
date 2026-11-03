#!/usr/bin/env python3
"""Mission-2 offer to story request, original EE versus existing models.

Run with unittest preloaded, private ELF/disc under local/. Dependencies are
immutable local Git objects, never fetched. Boundary: constructed player state,
synthetic speaker/resource return, explicit dialog and menu calls. No game text
is emitted, physical use/load/save/completion of mission 1 is not established.
"""
import argparse
import itertools
import mmap
import os
from pathlib import Path
import subprocess
import sys
import types

import ref_mission2_offer as R
from difftest_mission2 import ScriptCheck, props_for
from difftest_mission2_travel import Rig, Follow
from dump_tables import objects_from_file
from find_hosts import iso_files
from gob import gob_entries, lmp_entries
import scr

UNLOCK_PIN = '950b2538ef8f1cb4f5ad26cf3f88fd502c0184f6'
STORY_PIN = '76d4447c8e372f5e7e662edb267e0dcd51f13279'


def dependency(pin, name):
    source = subprocess.check_output(['git', 'show', pin + ':tools/' + name + '.py'],
                                     cwd=Path(__file__).resolve().parents[1])
    module = types.ModuleType(name)
    module.__file__ = str(Path(__file__).with_name(name + '.py'))
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


H = dependency(UNLOCK_PIN, 'difftest_mission_unlocks')
SREF = dependency(STORY_PIN, 'ref_story_route')
S = dependency(STORY_PIN, 'difftest_story_route')


def inputs(elf, iso):
    image, dialog = H.inputs(elf, iso)  # enforces ELF hash, original hub lookup
    e = H.EE(elf)
    e.mem.write(H.PLAYER, bytes(H.STRIDE * 4))
    e.mem.w32(0x4f719c, 0)
    hub = e.mem.cstr(e.call(0x1ec300))
    with open(iso, 'rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        matches = [x for x in iso_files(disc) if os.path.basename(x[0]).lower() == hub + '.gob']
        assert len(matches) == 1
        path, lba, size = matches[0]
        archive = disc[lba * 2048:lba * 2048 + size]
    rows = objects_from_file(path, archive)
    check = ScriptCheck(image)
    actor, a, b = check.call_values(0x3c, 'startDialog', 3, (0,))
    assert rows[10]['class'] == 'NPC'
    assert rows[10]['properties'].split(';').count('dialogscript=' + check.entry_at(0)) == 1
    blobs = [archive[o:o+n] for name, o, n in gob_entries(archive) if name.lower() == hub + '.lmp']
    assert len(blobs) == 1
    files = {name: blobs[0][o:o+n] for name, o, n in lmp_entries(blobs[0])}
    assert files[actor + '.dbin'] == dialog
    nodes = H.R.parse_dbin(dialog)
    entries = {name: off for off, name in scr.parse(image)['internals']}
    assert entries[nodes[7].condition] == 0x734
    assert [(entries[c.action], c.next, c.condition) for c in nodes[7].choices] == [
        (0x7b0, -1, ''), (0x2064, -1, '')]
    assert rows[11]['class'] == 'PushTrigger'
    props = rows[11]['properties'].split(';')
    actions = [v[7:] for v in props if v.startswith('action=')]
    keys = [v[4:] for v in props if v.startswith('key=')]
    assert len(actions) == len(keys) == 1
    assert (entries[actions[0]], entries[keys[0]]) == (0x54, 0x98)
    return image, dialog, hub, actor, (a, b), rows[11], entries[keys[0]]


def open_bound(p, hub, actor, controls):
    # Bind the controlled resource lookup to the actual NPC's requested identity.
    obj = p.dialog.host.objects.pop('actor')
    p.dialog.host.objects[actor] = obj
    p.mem.write(0x41b721, hub.encode('latin1') + b'\0')
    msg = H.R.start_message(actor, 0, *controls, (0, 0, 0), 0, 0)
    p.model.on_open(p.model_host, msg, p.nodes, level=hub)
    p.dialog.message(msg)
    p.compare()
    assert [x for x in p.dialog.log if x[0] == 'lump'] == [('lump', hub + '.lmp', actor + '.dbin')]
    return p.mem.s32(H.D.A['node_index'])


class MenuFollow:
    def __contains__(self, addr):
        return addr in S.MENU_FOLLOW or addr in (0x1ec5d0, 0x231520) or addr in Follow()


def menu(elf, seed, difficulty, player_bytes, source, *, locked=False, busy=False, recall=0):
    """Explicit player-byte handoff, not a loader or a physical hub interaction."""
    image, row, key = source
    p = Rig(elf, image)
    p.e.follow = MenuFollow()
    m = p.m
    m.write(H.PLAYER, player_bytes)
    m.w32(0x4d8ae0, 1)
    m.w32(0x4f719c, difficulty)
    m.w32(0x404464, seed)
    m.w32(0x4d8ae4, 0)
    m.w8(0x402791, 0)
    p.text(S.PENDING, '')
    m.w8(S.ORIENT, 0)
    # UI, network-local admission, audio/fade are explicit service controls.
    for address in (0x17365c, 0x214230, 0x1eb000, 0x13e150, 0x18cbfc, 0x18ebb8):
        p.stub(address)
    p.stub(0x13dd40, 1)
    p.stub(0x1df5ec)
    p.stub(0x22fbc0, int(busy))  # Dialog-closed boundary is explicit.
    m.w8(0x41b51d, recall)
    check = ScriptCheck(image)
    second = m.u8(H.PLAYER + H.MISSION + difficulty * 13 + 2)
    usable = p.run_entry(check, key)
    assert usable == int(second == 1), (second, usable)
    if not usable and not locked:
        assert m.u32(0x44fdb8) == 0 and m.cstr(S.PENDING) == ''
        return 0
    obj = p.e.alloc(0x80)
    m.w32(obj + 0x2c, props_for(p.e, row))
    if locked:
        p.call(0x231520, 0)  # Independent forced-menu negative control.
    else:
        p.call(0x14dcc8, obj, 1)
    entrance = check.call_values(0x4a44, 'setEntrance', 1, (0,))[0]
    if not locked:
        assert m.cstr(0x4f8468) == entrance
    if busy or recall:
        assert m.u32(0x44fdb8) == 0 and m.cstr(S.PENDING) == ''
        return 0
    assert m.u32(0x44fdb8) == 2
    model = SREF.new_menu()
    assert S.snap(m) == S.model_snap(model)
    destination = m.cstr(m.u32(0x4fe540 + 0x34 + 8))
    assert destination == 'innovat1'
    snapshots = 0
    for tick in range(26):
        if tick == 17 and locked:
            # Negative control forces row 1 with availability absent, not UI navigation.
            m.w8(S.MENU_ROW, 1)
            model['row'] = 1
        button = 0x40 if tick == 17 else 0
        fade = 128 if tick >= 22 else 0
        m.w32(0x41bfe4, button)
        p.stub(0x1df5ec, fade)
        p.call(0x2316fc)
        R.menu_tick(model, button, not locked, destination, fade)
        assert S.snap(m) == S.model_snap(model), (tick, S.snap(m), S.model_snap(model))
        assert m.read(H.PLAYER, len(player_bytes)) == player_bytes
        assert m.u32(0x404464) == seed
        snapshots += 1
    assert m.cstr(S.PENDING) == ('' if locked else destination)
    return snapshots


def run(elf, iso, seed):
    image, dialog, hub, actor, controls, row, key = inputs(elf, iso)
    source = image, row, key
    cases = snapshots = 0
    for difficulty, first, second, choice in itertools.product(range(5), range(4), (0, 2), range(2)):
        p = H.Probe(elf, image, dialog, seed, first, second, difficulty)
        # Freeze all records before original writes, including inactive players.
        p.game.mem.read(H.PLAYER, H.STRIDE * 4)
        before = p.mem.read(H.PLAYER, H.STRIDE * 4)
        assert open_bound(p, hub, actor, controls) == R.node(first, second)
        assert not p.writes
        assert p.mem.read(H.PLAYER, H.STRIDE * 4) == before
        if first == 3:
            p.confirm(choice)
            assert p.writes == [(difficulty, 2, 1)]
            expected = bytearray(before)
            expected[H.MISSION + difficulty * 13 + 2] |= 1
            assert p.mem.read(H.PLAYER, len(expected)) == bytes(expected)
            assert p.mem.read(H.PLAYER, len(expected)) == p.game.mem.read(H.PLAYER, len(expected))
            assert (0x7b0 if choice == 0 else 0x2064) in p.entered
            snapshots += menu(elf, seed, difficulty, bytes(expected), source)
        else:
            assert not p.writes
        assert not p.rig.unknown
        assert all(x[0] == 'text_lookup' for x in p.dialog.unexpected)
        cases += 1
    # Completion alone: still no availability, forced row-1 confirmation refuses.
    for difficulty in range(5):
        p = H.Probe(elf, image, dialog, seed, 3, 0, difficulty)
        snapshots += menu(elf, seed, difficulty, p.mem.read(H.PLAYER, H.STRIDE * 4), source, locked=True)
    for busy, recall in ((True, 0), (False, 1), (True, 1)):
        p = H.Probe(elf, image, dialog, seed, 3, 1)
        menu(elf, seed, 0, p.mem.read(H.PLAYER, H.STRIDE * 4), source, busy=busy, recall=recall)
    print('PASS trigger suppressors=3; action property dispatch and original menu setup executed')
    print('PASS seed=%d bound hub selectors=%d menu snapshots=%d; NPC record 10 and node 7 actions checked' %
          (seed, cases, snapshots))
    print('LIMIT physical use, mission-1 completion, hub2, full loading and rendered UI Unknown')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('iso')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.iso, args.seed)


if __name__ == '__main__':
    main()
