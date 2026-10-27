#!/usr/bin/env python3
"""Original shipped dialog + VM composition; counts/addresses only output.

Read-only private inputs. Existing dialog harness/model are loaded from a pinned
local Git object, without changing their APIs or writing dependency copies.
"""
# Direct execution otherwise resolves inspect's stdlib dependency to tools/dis.py.
import sys
from pathlib import Path
_TOOL_DIR = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p or '.').resolve()) != _TOOL_DIR]
import unittest
sys.path.append(_TOOL_DIR)
import argparse
import hashlib
import mmap
import os
import random
import subprocess
import types

import difftest_natives as N
from ee_emu import EE
from find_hosts import iso_files
from gob import gob_entries, lmp_entries
import scr

DIALOG_PIN = '334578d310179760daff20ea6098353a54958df8'
ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYER, STRIDE, MISSION = 0x4D8AF0, 0x4C30, 0x4BBF


def dependency(name):
    source = subprocess.check_output(['git', 'show', DIALOG_PIN + ':tools/' + name + '.py'],
                                     cwd=Path(__file__).resolve().parents[1])
    module = types.ModuleType(name)
    module.__file__ = str(Path(__file__).with_name(name + '.py'))
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


R = dependency('ref_dialog')
D = dependency('difftest_dialog')


def inputs(elf, iso):
    with open(elf, 'rb') as file:
        assert hashlib.file_digest(file, 'sha256').hexdigest() == ELF_SHA
    e = EE(elf)
    e.mem.write(PLAYER, bytes(STRIDE * 4))
    e.mem.w32(0x4F719C, 0)
    hub = e.mem.cstr(e.call(0x1EC300))
    with open(iso, 'rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as disc:
        _, lba, size = next(x for x in iso_files(disc)
                           if os.path.basename(x[0]).lower() == hub + '.gob')
        archive = disc[lba * 2048:lba * 2048 + size]
    files = {}
    for name, offset, size in gob_entries(archive):
        if name.lower() != hub + '.lmp':
            continue
        lump = archive[offset:offset + size]
        for name, off, length in lmp_entries(lump):
            files[name] = lump[off:off + length]
    image = next(v for k, v in files.items() if k.endswith('.scr'))
    parsed = scr.parse(image)
    action = dict(parsed['internals'])[0x7B0]
    dialog = next(v for k, v in files.items()
                  if k.endswith('.dbin') and action.encode() in v)
    return image, dialog


class Probe:
    def __init__(self, elf, image, dialog, seed, first, second, difficulty=0,
                 evil=0, decision=0, variables=(), mission_bytes=None):
        self.rig = rig = N.Rig(elf)
        rig.emu.record_calls = True
        rig.checkpoint()
        image = image + bytes(256)
        assert rig.place(image) == (0, 0)
        scene = N.Scene(rig, random.Random(seed), names=[b'actor'], variables=[], objects=1)
        N.setup_model(scene, seed, N.new_machine(image))
        rig.responder = N.Responder(seed, scene)
        original_hooks = dict(rig.emu.hooks)
        host = R.Host()
        host.text = lambda _: [65]  # synthetic localization, never copy game prose
        old = D.EE
        try:
            D.EE = lambda _: rig.emu
            self.dialog = d = D.Rig(elf, host)
        finally:
            D.EE = old
        rig.emu.follow = N.RealSet(N.REAL_OTHER)
        rig.emu.follow.addresses |= D.LEAF | {D.F_ON_MSG, D.F_SHOW, D.F_QUEUE_AUDIO,
                                             D.F_IS_OPEN, D.F_CLEAR_TEXT, D.F_SET_FOCUS}
        for address in list(rig.emu.hooks):
            if N.SCRIPT_LO <= address < N.SCRIPT_HI or N.RUNTIME_LO <= address < N.RUNTIME_HI:
                rig.emu.unhook(address)
                if address in original_hooks:
                    rig.emu.hooks[address] = original_hooks[address]
        rig.emu.unhook(0x1ED694)  # execute the real script dispatcher, never a truth stub
        m = self.mem = rig.emu.mem
        d.file_ptr = rig.emu.alloc(len(dialog) + 16)
        m.write(d.file_ptr, dialog)
        d.entry = rig.emu.alloc(16)
        m.w32(d.entry + 4, d.file_ptr)
        obj = R.Object(0)
        d.place(obj)
        host.objects = {'actor': [obj]}
        host.player_obj, host.alive = {}, []
        d.plant_world()
        m.write(PLAYER, bytes(STRIDE * 4))
        m.write(N.N.G_QUEST_VARS, bytes(0x2000))
        m.w32(0x4D8AE0, 1)
        m.w32(0x4F719C, difficulty)
        m.w32(0x4D8AE4, 0)
        m.w32(0x404464, seed)
        m.w8(PLAYER + MISSION + difficulty * 13, 3)
        m.w8(PLAYER + MISSION + difficulty * 13 + 1, first)
        m.w8(PLAYER + MISSION + difficulty * 13 + 2, second)
        m.w8(PLAYER + 0x4C1A, evil << difficulty)
        m.w8(PLAYER + 0x4C1B, decision << difficulty)
        for key, value in variables:
            rig.call(0x1ED854, scene.cstring(key), value)
        if mission_bytes is not None:
            assert len(mission_bytes) == 13
            m.write(PLAYER + MISSION + difficulty * 13, bytes(mission_bytes))
        self.entries = dict(scr.parse(image)['internals'])
        self.entered, self.writes, self.native_calls = [], [], []
        reverse = {name: off for off, name in self.entries.items()}
        rig.emu.hook(0x1ED694, lambda e: self.entered.append(
            reverse.get(e.mem.cstr(e.r[4]), -1)))
        rig.emu.hook(0x1BF6D0, lambda e: self.writes.append(
            tuple(x & 0xFFFFFFFF for x in e.r[4:7])))
        externals = [name for _, name in scr.parse(image)['externals']]
        rig.emu.hook(N.SCR_CALL_NATIVE, lambda e: self.native_calls.append(
            externals[e.r[5] & 0xFFFFFFFF]))
        self.game = N.N.Game(N.N.Mem(N.Under(m)))
        self.game.set_script(N.new_machine(image))
        self.model_host = mh = R.Host()
        mh.text = lambda _: [65]
        mh.objects, mh.player_obj, mh.alive = host.objects, {}, []
        mh.run_script = lambda name: self.game.run_script(name.encode('latin1'))
        # Match the documented closed dialog state before admission controls.
        m.w32(D.A['node_index'], 0xFFFFFFFF)
        m.w32(D.A['prompt_node'], 0xFFFFFFFF)
        self.model = R.Dialog()
        self.nodes = R.parse_dbin(dialog)
        self.seed = seed
        self.difficulty = difficulty

    def run_entry(self, offset):
        name = self.entries[offset]
        expected = self.game.run_script(name.encode('latin1'))
        actual = self.rig.call(0x1ED694, self.dialog.cstr(name)) & 0xFFFFFFFF
        assert actual == expected & 0xFFFFFFFF, (offset, actual, expected)
        assert not [c.target for c in self.rig.emu.calls
                    if c.stubbed and c.target not in self.rig.emu.hooks]
        return actual

    def compare(self):
        m, model, a = self.mem, self.model, D.A
        assert not [c.target for c in self.rig.emu.calls
                    if c.stubbed and c.target not in self.rig.emu.hooks]
        assert m.s32(a['node_index']) == model.node_index
        assert m.s32(a['nvis']) == len(model.visible)
        assert [m.s32(a['visible'] + 4*i) for i in range(len(model.visible))] == model.visible
        for slot in range(4):
            base = PLAYER + slot * STRIDE
            for off, size in ((MISSION, 65), (0x41D0, 0x204), (0x4C1A, 2)):
                assert m.read(base + off, size) == self.game.mem.read(base + off, size)
        assert m.read(N.N.G_QUEST_VARS, 0x2000) == self.game.mem.read(N.N.G_QUEST_VARS, 0x2000)
        assert m.u32(0x404464) == self.seed == self.game.mem.u32(0x404464)

    def open(self, recall=0, menu=False):
        self.mem.w8(0x41B51D, recall)
        self.dialog.host.recall = self.model_host.recall = recall
        self.dialog.host.mission_menu = self.model_host.mission_menu = menu
        msg = R.start_message('actor', 0, 0, 0, (0, 0, 0), 0, 0)
        self.model.on_open(self.model_host, msg, self.nodes)
        self.dialog.message(msg)
        self.compare()
        return self.mem.s32(D.A['node_index'])

    def confirm(self, choice=0):
        # Presentation is complete; controlled state is not a pad/render capture.
        for key, value in (('revealing', 0), ('reveal_done', 1), ('at_end', 1),
                           ('blend', 0x3F800000), ('cursor', choice)):
            self.mem.w32(D.A[key], value)
        self.model.revealing, self.model.reveal_done, self.model.at_end = 0, 1, 1
        self.model.blend, self.model.cursor = 0x3F800000, choice
        self.model.on_confirm(self.model_host)
        self.dialog.message([R.MSG_CONFIRM])
        self.compare()


# Authored address map: (dialog node, public offset, mission, predicate kind).
# This is dialog priority order, not an inferred campaign or travel order.
HUB_CONDITIONS = (
    (0, 0x3F0, 0, 'active'), (1, 0x11C, 1, 'offer'),
    (2, 0x11C, 1, 'offer'), (3, 0x198, 1, 'pending'),
    (4, 0x498, 0, 'demo'), (5, 0x498, 0, 'demo'),
    (6, 0x680, 0, 'demo'), (7, 0x734, 2, 'offer'),
    (8, 0x898, 2, 'pending'), (9, 0x9A0, 3, 'offer'),
    (10, 0x9A0, 3, 'offer'), (11, 0xB04, 3, 'pending'),
    (12, 0xC0C, 4, 'offer'), (13, 0xD70, 4, 'pending'),
    (14, 0xE78, 5, 'offer'), (15, 0xFDC, 5, 'pending'),
    (16, 0x10E4, 6, 'offer'), (17, 0x10E4, 6, 'offer'),
    (18, 0x1248, 6, 'pending'), (19, 0x1350, 7, 'offer'),
    (20, 0x14B4, 7, 'pending'), (21, 0x15BC, 8, 'offer'),
    (22, 0x1638, 9, 'offer'), (23, 0x16B4, 10, 'offer'),
    (24, 0x16B4, 10, 'offer'), (25, 0x1818, 10, 'pending'),
    (26, 0x1920, 11, 'offer'), (27, 0x1A84, 11, 'pending'),
    (28, 0x1B8C, 12, 'offer'), (29, 0x1B8C, 12, 'offer'),
    (30, 0x1CF0, 12, 'pending'),
)
VAR_OFFSETS = (0x6C8, 0x6D8, 0x6E8, 0x6F8, 0x708, 0x718,
               0x728, 0x738, 0x748, 0x758, 0x76C, 0x780)


def expected_conditions(raw, values):
    active = any(raw[i] & 1 and not raw[i] & 2 and values[i-1] != 0
                 for i in range(1, 13))
    out = []
    for node, offset, mission, kind in HUB_CONDITIONS:
        if kind == 'active':
            value = active
        elif kind == 'demo':
            value = False  # original demoRunning native returns zero in this executable
        elif kind == 'offer':
            value = not raw[mission] & 1
        else:
            value = raw[mission] & 1 and not raw[mission] & 2 and values[mission-1] == 0
        out.append((node, offset, int(bool(value))))
    return out


def hub_predicates(elf, image, dialog):
    pool = dict(scr.strings(image, *scr.parse(image)['strings']))
    rng = random.Random(20973)
    states = []
    # Each variable independently: zero, signed negative, and positive controls,
    # crossed with all four availability/completion states of its own mission.
    for mission in range(1, 13):
        for raw_value in range(4):
            for value in (-128, -1, 0, 1, 2, 127):
                raw, values = [3, 3, 0] + [0] * 10, [0] * 12
                raw[mission], values[mission-1] = raw_value, value
                states.append((raw, values))
    for _ in range(64):
        states.append(([3] + [rng.randrange(4) for _ in range(12)],
                       [rng.choice((-128, -1, 0, 1, 127)) for _ in range(12)]))
    for index, (raw, values) in enumerate(states):
        variables = [(pool[offset].encode('latin1'), value)
                     for offset, value in zip(VAR_OFFSETS, values)]
        probe = Probe(elf, image, dialog, 20973, 0, 0, index % 5,
                      index % 2, (index // 2) % 2, variables, raw)
        expected = expected_conditions(raw, values)
        for node, offset, value in expected:
            assert probe.run_entry(offset) == value, (index, node, offset)
        chosen = next((node for node, offset, value in expected if value), 0)
        assert probe.open() == chosen, (index, chosen)
        assert not probe.writes
        assert not probe.rig.unknown
    print('PASS hub predicates and start priority:', len(states),
          'states;', len(states) * len(HUB_CONDITIONS), 'predicate comparisons')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elf', required=True)
    parser.add_argument('--iso', required=True)
    parser.add_argument('--hub-only', action='store_true')
    args = parser.parse_args()
    image, dialog = inputs(args.elf, args.iso)
    if args.hub_only:
        hub_predicates(args.elf, image, dialog)
        return
    count = 0
    expected_nodes = ((1, 1, 1, 1), (3, 3, 3, 3),
                      (1, 1, 1, 1), (7, 8, 7, 9))
    # Every raw low-bit state, five difficulty rows, both alignment/decision bits,
    # both visible choices, and two independently seeded scratch-register states.
    for seed in (20973, 7):
        for difficulty in range(5):
            for evil in range(2):
                for decision in range(2):
                    for first in range(4):
                        for second in range(4):
                            for choice in range(2):
                                probe = Probe(args.elf, image, dialog, seed, first, second,
                                              difficulty, evil, decision)
                                before = probe.mem.read(PLAYER + MISSION, 65)
                                node = probe.open()
                                assert node == expected_nodes[first][second]
                                assert probe.mem.read(PLAYER + MISSION, 65) == before
                                assert not probe.writes
                                if node == 7:
                                    probe.confirm(choice)
                                    assert (0x7B0 if choice == 0 else 0x2064) in probe.entered
                                    assert probe.writes == [(difficulty, 2, 1)]
                                    after = bytearray(before)
                                    after[difficulty * 13 + 2] |= 1
                                    assert probe.mem.read(PLAYER + MISSION, 65) == after
                                elif node == 8:
                                    # Already available but incomplete: decline closes without a write.
                                    probe.confirm(1)
                                    assert not probe.writes
                                assert all(x[0] == 'text_lookup' for x in probe.dialog.unexpected)
                                assert not probe.rig.unknown
                                count += 1
    print('PASS first-to-second dialog matrix:', count)
    blocked = 0
    for recall, menu in ((1, False), (0, True), (1, True)):
        probe = Probe(args.elf, image, dialog, 20973, 3, 0)
        before = probe.mem.read(PLAYER + MISSION, 65)
        probe.open(recall, menu)
        assert not probe.entered and not probe.writes
        assert probe.mem.read(PLAYER + MISSION, 65) == before
        blocked += 1
    print('PASS dialog admission suppressors:', blocked)

    # Direct-entry controls separate the offer predicate from start-node priority.
    # They do not claim these are reachable states of a played campaign.
    direct = 0
    for first in range(4):
        for second in range(4):
            probe = Probe(args.elf, image, dialog, 20973, first, second)
            assert probe.run_entry(0x734) == (1 - (second & 1))
            assert probe.native_calls == ['getMissionAvailable']
            direct += 1
    print('PASS isolated offer predicate:', direct)
    initial = 0
    for difficulty in range(5):
        for first in (0, 2):
            for choice in (0, 1):
                probe = Probe(args.elf, image, dialog, 20973, first, 0, difficulty)
                assert probe.open() == 1
                probe.confirm()
                assert probe.mem.s32(D.A['node_index']) == 2
                probe.confirm()
                assert probe.mem.s32(D.A['node_index']) == 3
                assert not probe.writes
                probe.confirm(choice)
                assert probe.writes == [(difficulty, 1, 1)]
                initial += 1
    print('PASS first-offer choice traversal:', initial)
    hub_predicates(args.elf, image, dialog)


if __name__ == '__main__':
    main()
