#!/usr/bin/env python3
"""Bounded hub service census and original Savepoint use checks.

Give a local US v2.00 executable and disc. Archive data is read only; output
contains counts and roles, never object names, dialogue, or game bytes.
"""
import argparse
import collections
import hashlib
import mmap
import struct

from dump_tables import gob_entries, iso_files, lmp_entries, objects_from_file
from ee_emu import EE
import ref_hub_npcs as reference
import scr


ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
ARCHIVES = {
    'HUB.GOB': ('1d5f240025afb86800040664a168c27c236a8431fc4c02caf388bdcee37b385f',
                24, {'Portal': 6, 'Savepoint': 8, 'NPC': 10, 'PushTrigger': 11, 'Trigger': 12},
                82, (1, 23, 2, 11, 35, 19), (31, 54)),
    'HUB2.GOB': ('a061b0f35549674050765eb8f3243491f947888c2cdcef85e5110e2388d71dc4',
                 21, {'Portal': 0, 'NPC': 5, 'Savepoint': 6, 'PushTrigger': 7, 'Trigger': 9},
                 73, (1, 19, 2, 5, 30, 19), (26, 48)),
}
# Exact class census for every row outside the five service-route classes.
# The effect rings have authored actions, so their interaction is not ruled out.
REMAINDER = {
    'HUB.GOB': collections.Counter({
        'Ambient_Light': 1, 'Ambient_Light2': 1, 'Directional_Light': 1,
        'Directional_Light2': 1, 'Directional_LightD': 1, 'Directional_LightD2': 1,
        'charAmbient_Light': 1, 'charDirectional_Light': 1,
        'charDirectional_LightD': 1, 'Player1': 2, 'apprings': 1,
        'bflya': 2, 'bflyb': 3, 'clearColor': 1, 'customVars': 1,
    }),
    'HUB2.GOB': collections.Counter({
        'Ambient_Light': 1, 'Ambient_Light2': 1, 'Directional_Light': 1,
        'Directional_Light2': 1, 'Directional_LightD': 1, 'Directional_LightD2': 1,
        'charAmbient_Light': 1, 'charDirectional_Light': 1,
        'charDirectional_LightD': 1, 'Player1': 1, 'Torch': 3,
        'fpprings': 1, 'clearColor': 1, 'customVars': 1,
    }),
}
SERVICE_PROPERTIES = {'shop', 'dialogscript', 'key', 'action', 't',
                      'action1', 'actionatend', 'pokeable', 'triggerable'}
CALLS = ('startDialog', 'activateStore', 'activateMissionMenu', 'addQuest',
         'setMissionAvailable', 'removePlayerItem')
ABSENT = {'healPlayer', 'giveFullHealth', 'givePlayerExp', 'saveGame',
          'saveCheckPoint', 'removeQuest'}


def properties(row):
    return dict(part.split('=', 1) if '=' in part else (part, '')
                for part in row['properties'].split(';') if part)


def script_calls(image):
    parsed = scr.parse(image)
    cs, ce = parsed['code']
    words = struct.unpack_from('<%dI' % ((ce - cs) // 4), image, cs)
    imports = [name for _, name in parsed['externals']]
    counts = collections.Counter()
    dialog_names = []
    pool = dict(scr.strings(image, *parsed['strings']))
    i = 0
    while i < len(words):
        op = words[i]
        if op == 0x7d:  # source marker and two operands
            i += 3
            continue
        if op == 0x7b:  # SYSREQ.C
            builtin = imports[words[i + 1]]
            counts[builtin] += 1
            if builtin == 'startDialog':
                # Shipped hub call: three literal pushes, first is the file stem.
                assert words[i - 8] == 0x27
                dialog_names.append(pool[words[i - 7]])
        i += 1 + (op not in scr.NO_OPERAND)
    return parsed, counts, dialog_names


def census(iso):
    with open(iso, 'rb') as handle:
        disc = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            found = {}
            for path, off, size in iso_files(disc):
                label = path.rsplit('/', 1)[-1].upper()
                if label in ARCHIVES and path.upper().startswith('/BG/DATA/'):
                    assert label not in found
                    found[label] = disc[off:off + size]
        finally:
            disc.close()
    assert set(found) == set(ARCHIVES)
    for label, blob in sorted(found.items()):
        digest, size, expected, entries, counts, dialog_shape = ARCHIVES[label]
        assert hashlib.sha256(blob).hexdigest() == digest
        rows = objects_from_file(label, blob)
        assert len(rows) == size
        assert [row['index'] for row in rows] == list(range(size))
        for kind, index in expected.items():
            assert [row['index'] for row in rows if row['class'] == kind] == [index]
        interactive = {kind: rows[index] for kind, index in expected.items()}
        remainder = [row for row in rows if row['class'] not in expected]
        assert collections.Counter(row['class'] for row in remainder) == REMAINDER[label]
        rings = 'apprings' if label == 'HUB.GOB' else 'fpprings'
        for row in remainder:
            props = properties(row)
            if row['class'] == rings:
                assert {'action1', 'actionatend', 'triggerable'} <= props.keys()
                assert props['action1'] and props['actionatend']
                assert ('pokeable' in props) == (label == 'HUB.GOB')
                assert not {'shop', 'dialogscript', 'key', 'action', 't'} & props.keys()
            else:
                assert not SERVICE_PROPERTIES & props.keys()
        npc = properties(interactive['NPC'])
        assert npc.get('shop') == '1' and npc.get('dialogscript')
        assert 'action' not in properties(interactive['Savepoint'])
        gate = properties(interactive['PushTrigger'])
        assert gate.get('key') and gate.get('action')
        assert 'shop' not in gate and 'dialogscript' not in gate
        assert 'shop' not in properties(interactive['Portal'])
        walk_in = properties(interactive['Trigger'])
        assert walk_in.get('t')
        scripts, dialog_files = [], {}
        for _, lo, length in gob_entries(blob):
            lump = blob[lo:lo + length]
            for name, off, n in lmp_entries(lump):
                if name.lower() == 'script.scr':
                    scripts.append(lump[off:off + n])
                elif name.lower().endswith('.dbin'):
                    dialog_files[name.lower()] = lump[off:off + n]
        assert len(scripts) == 1
        parsed, called, dialog_names = script_calls(scripts[0])
        assert len(parsed['internals']) == entries
        exported = {name for _, name in parsed['internals']}
        assert {npc['dialogscript'], gate['key'], gate['action'], walk_in['t']} <= exported
        assert {'trigger', 'setEntrance'} <= {name for _, name in parsed['externals']}
        assert tuple(called[key] for key in CALLS) == counts
        assert not any(called[key] for key in ABSENT)
        assert len(dialog_names) == 1
        dialog = dialog_files[dialog_names[0].lower() + '.dbin']
        nodes = dialog[0]
        choices = sum(struct.unpack_from('<I', dialog, i * 0x448 + 0x54)[0]
                      for i in range(nodes))
        assert len(dialog) == nodes * 0x448
        assert (nodes, choices) == dialog_shape
        print('%s: %d records, five singly indexed service-route classes; '
              '%d other records including one action-bearing effect ring; %d script entries, '
              '%d dialog nodes, %d choices PASS' %
              (label, size, len(remainder), entries, nodes, choices))


def savepoint_use(elf, seed):
    # Only Savepoint_interact executes. External card/UI/script services are
    # explicit stubs. The constructed player record is a no-fee control.
    for busy, mutex in ((0, 0), (1, 0), (0, 1)):
        emu = EE(elf)
        emu.mem.auto_map = True
        emu.follow = set()
        emu.mem.w32(0x404464, seed)
        obj = emu.alloc(0x118)
        player = emu.alloc(0x4c30)
        emu.mem.w32(player + 0xe4, 1234)
        before = emu.mem.read(player, 0x4c30)
        emu.stub(0x217518, ret=busy)  # memcard_isBusy
        emu.stub(0x22fc2c, ret=mutex)  # menuMutex_isHeld
        emu.call(0x28dc30, obj, player)
        targets = [call.target for call in emu.calls]
        expected = reference.savepoint_use(busy, mutex)
        assert (0x2175b4 in targets) == expected['request_save']
        assert (0x14dcc8 in targets) == expected['dispatch_action']
        assert emu.mem.u32(obj + 0x84) == expected['activated']
        assert emu.mem.u8(obj + 0xc4) == expected['effect_pending']
        assert (emu.mem.read(player, 0x4c30) != before) == expected['player_record_changed']
        assert emu.mem.u32(0x404464) == seed
    print('seed %d: Savepoint use, card-busy and mutex controls; no player-record debit PASS' % seed)


def savepoint_prompt(elf, seed):
    emu = EE(elf)
    emu.mem.auto_map = True
    emu.follow = set()
    emu.mem.w32(0x404464, seed)
    obj = emu.alloc(0x118)
    player = emu.alloc(0x4c30)
    before = emu.mem.read(player, 0x4c30)
    assert emu.call(0x28da58, obj, player) == 1
    calls = {(call.site, call.target) for call in emu.calls}
    assert (0x28dc04, 0x173c84) in calls  # text_lookup
    assert (0x28dc10, 0x19e854) in calls  # prompt submission
    assert emu.mem.read(player, 0x4c30) == before
    assert emu.mem.u32(0x404464) == seed
    print('seed %d: Savepoint prompt text/submission and record control PASS' % seed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True)
    parser.add_argument('--iso', required=True)
    args = parser.parse_args()
    with open(args.elf, 'rb') as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == ELF_SHA256
    census(args.iso)
    for seed in (20973, 7):
        savepoint_prompt(args.elf, seed)
        savepoint_use(args.elf, seed)
    print('PASS: two pinned hub archives and eight bounded EE cases, 0 mismatches')


if __name__ == '__main__':
    main()
