#!/usr/bin/env python3
"""Original shipped dialog + VM composition; counts/addresses only output.

Read-only private inputs. Existing dialog harness/model are loaded from a pinned
local Git object, without changing their APIs or writing dependency copies.
"""
import unittest  # preload stdlib dis before importing research tools
import argparse
import hashlib
import mmap
import os
from pathlib import Path
import random
import subprocess
import sys
import types

sys.path.append(str(Path(__file__).resolve().parent))
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
                 evil=0, decision=0, variables=()):
        self.rig = rig = N.Rig(elf)
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
        self.game = N.N.Game(N.N.Mem(N.Under(m)))
        self.game.set_script(N.new_machine(image))
        self.model_host = mh = R.Host()
        mh.text = lambda _: [65]
        mh.objects, mh.player_obj, mh.alive = host.objects, {}, []
        mh.run_script = lambda name: self.game.run_script(name.encode('latin1'))
        self.model = R.Dialog()
        self.nodes = R.parse_dbin(dialog)
        self.seed = seed
        self.difficulty = difficulty

    def compare(self):
        m, model, a = self.mem, self.model, D.A
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elf', required=True)
    parser.add_argument('--iso', required=True)
    args = parser.parse_args()
    image, dialog = inputs(args.elf, args.iso)
    count = 0
    for seed in (20973, 7):
        for first in range(4):
            for second in range(4):
                probe = Probe(args.elf, image, dialog, seed, first, second)
                node = probe.open()
                print('case', seed, first, second, 'node', node)
                if node == 7:
                    probe.confirm()
                    assert probe.mem.u8(PLAYER + MISSION + 2) & 1
                count += 1
    print('PASS composed probes:', count)


if __name__ == '__main__':
    main()
