#!/usr/bin/env python3
"""Fresh hub-to-first-mission comparison with original EE functions.

Needs the owner's US v2.00 ELF and locally extracted HUB.GOB/BLOOD1.GOB.
No game data or disassembly is written by this program.
"""
import argparse
import hashlib
import os
import random
import struct

from ee_emu import EE
from gob import gob_entries, lmp_entries
import ref_story_route as R
import scr
import difftest_natives as N

ELF_SHA256 = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYERS = 0x4d8af0
MISSION = 0x4bbf
QUEST = 0x41d0
QUEST_COUNT = 0x43d0
MENU_STATE = 0x8e2efc
MENU_ROW = 0x8e2f0c
MENU_COL = 0x8e2f0d
MENU_COUNTER = 0x8e2f04
MENU_MARK = 0x8e2f08
MENU_C0 = 0x8e2f00
PENDING = 0x41b6d0
ORIENT = 0x41b720
MENU_FOLLOW = {0x231078, 0x2310a8, 0x2310d4, 0x23112c, 0x231180,
               0x2311d4, 0x231228, 0x2312a8, 0x231310, 0x231360,
               0x2313b4, 0x231438, 0x2314bc, 0x2314c8, 0x1bf698,
               0x1bf730, 0x1bf838, 0x1bf8d8, 0x3b868c}


def entry(gob, filename):
    data = open(gob, 'rb').read()
    for lump_name, lo, ls in gob_entries(data):
        if lump_name.lower() != os.path.basename(gob).lower().replace('.gob', '.lmp'):
            continue
        lump = data[lo:lo + ls]
        for name, off, size in lmp_entries(lump):
            if name.lower() == filename.lower():
                return lump[off:off + size]
    raise AssertionError('%s missing %s' % (gob, filename))


def object_records(blob):
    count, _flags, strings = struct.unpack_from('<hHi', blob)
    off = 8
    for _ in range(count):
        class_off, size = struct.unpack_from('<ih', blob, off)
        def text(offset):
            at = strings + offset
            return blob[at:blob.index(b'\0', at)].decode('latin1')
        props = []
        at = off + 20
        while True:
            val, = struct.unpack_from('<i', blob, at)
            at += 4
            if val == 0:
                break
            props.append(text(val))
        yield text(class_off), props
        off += size


def check_disc(hub, blood):
    image = entry(hub, 'script.scr')
    parsed = scr.parse(image)
    imports = {name for _, name in parsed['externals']}
    assert {'startDialog', 'setMissionAvailable', 'addQuest', 'activateMissionMenu',
            'setEntrance'} <= imports
    assert not imports.intersection({'newWorld', 'newWorldPost', 'simpleNewWorld'})
    publics = {name for _, name in parsed['internals']}
    assert {'startDia3314', 'setMissi867e', 'setMissib670', 'warnDetect',
            'gatewaytrigger'} <= publics
    dbin = entry(hub, 'firiona.dbin')
    assert dbin[0] == len(dbin) // 0x448 == 31
    # Node 3 is the first mission's two ending actions. Copy no dialog text.
    row = dbin[3 * 0x448:(3 + 1) * 0x448]
    assert struct.unpack_from('<i', row, 0x54)[0] == 2
    actions = []
    for i in range(2):
        off = 0x58 + i * 0x54
        action = row[off + 0x30:off + 0x50].split(b'\0')[0].decode('ascii')
        nxt, = struct.unpack_from('<i', row, off + 0x50)
        actions.append((action, nxt))
    assert actions == [('setMissi867e', -1), ('setMissib670', -1)]
    hub_objects = list(object_records(entry(hub, 'objects.ob')))
    assert any(cls == 'NPC' and 'dialogscript=startDia3314' in props for cls, props in hub_objects)
    assert any(cls == 'PushTrigger' and 'action=callScri8e04' in props for cls, props in hub_objects)
    assert any(cls == 'Trigger' and 't=callScri1ef1' in props for cls, props in hub_objects)
    blood_objects = list(object_records(entry(blood, 'objects.ob')))
    assert any(cls == 'Player1' and 'default=1' in props for cls, props in blood_objects)
    assert not any(cls == 'Player1' and 'name=goodstart' in props for cls, props in blood_objects)
    hostile = sum(cls in {'Kobold', 'Koboldtough', 'koboldshaman', 'WarWraith'}
                  for cls, _props in blood_objects)
    assert hostile > 0
    return len(hub_objects), len(blood_objects), hostile


def snap(mem):
    return (mem.s8(MENU_STATE), mem.s8(MENU_ROW), mem.s8(MENU_COL),
            mem.s32(MENU_COUNTER), mem.s32(MENU_MARK), mem.s32(0x41b4f4),
            mem.cstr(PENDING, 32), mem.u8(ORIENT), mem.s32(MENU_C0))


def model_snap(state):
    return tuple(state[x] for x in ('phase', 'row', 'col', 'counter', 'mark',
                                    'paused', 'pending', 'orient', 'c0'))


def run_hub_entry(elf, hub_script, seed, name, mission1_available=False):
    """Run a shipped hub entry through scr_load and scr_interpret in ee_emu."""
    rig = N.Rig(elf)
    rig.checkpoint()
    image = hub_script + bytes(256)
    assert rig.place(image) == (0, 0)
    scene = N.Scene(rig, random.Random(seed), names=[b'portal', b'firiona'],
                    variables=[b'firstmissionever'], objects=2)
    machine = N.new_machine(image)
    N.setup_model(scene, seed, machine)
    rig.responder = N.Responder(seed, scene)
    mem = rig.emu.mem
    mem.write(PLAYERS, bytes(N.N.REC_SIZE * 4))
    mem.write(N.N.G_QUEST_VARS, bytes(0x2000))
    mem.w32(0x4d8ae0, 1)
    mem.w32(0x4f719c, 0)
    mem.w32(0x404464, seed)
    mem.w8(PLAYERS + MISSION + 1, int(mission1_available))
    mem.write(0x4f8468, bytes(0x50))
    pointer = scene.cstring(name)
    result = N.s32(rig.call(N.A['script_runByName'], pointer, max_steps=40000000))
    return (result, mem.u8(PLAYERS + MISSION), mem.u8(PLAYERS + MISSION + 1),
            mem.u32(PLAYERS + QUEST_COUNT),
            mem.cstr(PLAYERS + QUEST), mem.cstr(PLAYERS + QUEST + 0x20),
            mem.u32(0x404464), mem.cstr(0x4f8468))


def compare_seed(elf, hub_script, seed):
    start = run_hub_entry(elf, hub_script, seed, b'start')
    assert start[0:4] == (0, 3, 0, 0)
    opening = [run_hub_entry(elf, hub_script, seed, name)[0]
               for name in (b'returnc2f', b'if99a5', b'if441a')]
    assert opening == [0, 1, 0]
    assert R.dialog_start_node(opening) == 1
    portal = run_hub_entry(elf, hub_script, seed, b'warnDetect', mission1_available=True)
    assert portal[0] == 0 and portal[7] == 'goodstart'
    actions = [run_hub_entry(elf, hub_script, seed, name)
               for name in (b'setMissi867e', b'setMissib670')]
    assert actions[0] == actions[1]
    assert actions[0][0] == 0 and actions[0][2:4] == (1, 1) and actions[0][6] == seed
    assert actions[0][4] and actions[0][5]
    emu = EE(elf)
    mem = emu.mem
    mem.w32(0x404464, seed)
    mem.w32(0x4d8ae0, 1)
    mem.w32(0x4f719c, 0)
    mem.w8(PLAYERS + MISSION, 3)
    state = R.fresh_hub_state()
    # The two dialog endings have the same campaign write. Synthetic keys keep
    # game text out of this test while exercising the original state functions.
    title = emu.alloc(32)
    desc = emu.alloc(32)
    mem.write(title, b'route-title\0')
    mem.write(desc, b'route-desc\0')
    assert mem.u8(PLAYERS + MISSION + 1) == 0
    emu.call(0x1bf6d0, 0, 1, 1)
    emu.call(0x1d386c, title, desc)
    R.offer_first_mission(state, 'route-title', 'route-desc')
    assert mem.u8(PLAYERS + MISSION + 1) == state['mission1']
    assert mem.u32(PLAYERS + QUEST_COUNT) == len(state['quests'])
    assert (mem.cstr(PLAYERS + QUEST), mem.cstr(PLAYERS + QUEST + 0x20)) == state['quests'][0]
    assert R.portal_request(state) == 'mission_menu'
    entrance = emu.alloc(32)
    mem.write(entrance, b'goodstart\0')
    # setEntrance's underlying writer is a direct strcpy in the native.
    emu.call(0x3b868c, 0x4f8468, entrance)
    assert mem.cstr(0x4f8468) == state['entrance']
    for name, expected in (('hub', 0), ('blood1', 0), ('valor', 6)):
        ptr = emu.alloc(32)
        mem.write(ptr, name.encode('ascii') + b'\0')
        assert emu.call(0x217d30, ptr) == expected
    R.same_act_on_arrival(state, 0)
    assert state['mission1'] == 1 and len(state['quests']) == 1
    table = 0x4fe540
    story = mem.cstr(mem.u32(table + 8))
    assert story == 'blood1'
    emu.follow = set()
    emu.call(0x231520, 0)
    emu.follow = MENU_FOLLOW
    emu.stub(0x13e150, ret=0, name='isLocal')
    emu.stub(0x13dd40, ret=1, name='slotActive')
    emu.stub(0x18cbfc, ret=0, name='pauseOpen')
    model = R.new_menu()
    assert snap(mem) == model_snap(model)
    checks = 0
    for tick in range(26):
        button = 0x40 if tick == 17 else 0
        fade = 128 if tick >= 22 else 0
        mem.w32(0x41bfe4, button)
        emu.stub(0x1df5ec, ret=fade, name='fade')
        emu.call(0x2316fc, max_steps=400000)
        R.menu_tick(model, button, True, story, fade)
        assert snap(mem) == model_snap(model), (seed, tick, snap(mem), model_snap(model))
        checks += 1
    assert model['pending'] == 'blood1' and model['orient'] == 0xff
    assert mem.u32(0x404464) == seed, 'menu consumed the shared seed'
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', required=True)
    p.add_argument('--hub-gob', required=True)
    p.add_argument('--blood-gob', required=True)
    args = p.parse_args()
    assert hashlib.sha256(open(args.elf, 'rb').read()).hexdigest() == ELF_SHA256
    counts = check_disc(args.hub_gob, args.blood_gob)
    hub_script = entry(args.hub_gob, 'script.scr')
    print('PASS disc route: hub objects %d, blood1 objects %d, selected hostile records %d' % counts)
    for seed in (20973, 7):
        count = compare_seed(args.elf, hub_script, seed)
        print('PASS seed %d: shipped hub start and both dialog actions, mission/quest/act/entrance, '
              '%d menu snapshots -> blood1' % (seed, count))


if __name__ == '__main__':
    main()
