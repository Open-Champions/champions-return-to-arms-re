#!/usr/bin/env python3
"""Execute the shipped mission-2 NPC dialog selector and choice actions.

Run from this worktree with owner inputs under local/:
  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission2_dialog.py \
      local/SLUS_209.73 local --seed 20973

Original functions: dialog message handler 0x22ee2c, node display 0x230c74,
script dispatcher 0x1ed694, VM and native handlers, quest/variable/deferred
queue helpers. The immutable dialog harness supplies presentation, resource,
speaker lookup and audio stubs. Inventory count/find/remove are explicit
controlled services; actual bags, pickup, UI and deferred completion are NOT
proved. No private text or raw script is emitted or written by this tool.
"""
import sys
from pathlib import Path

# The adjacent dis.py is a research tool, not the stdlib module inspect needs.
_TOOLS = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p or '.').resolve()) != _TOOLS]
import unittest  # noqa: E402,F401
sys.path.append(_TOOLS)

import argparse
import hashlib
import itertools
import random
import subprocess
import types

import difftest_natives as N
from gob import gob_entries, lmp_entries
from ref_mission2 import LEVELS
import scr
from difftest_mission2 import ScriptCheck

DIALOG_PIN = '334578d310179760daff20ea6098353a54958df8'
ELF_SHA = '292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675'
PLAYER, STRIDE, MISSION = 0x4D8AF0, 0x4C30, 0x4BBF
RUN_SCRIPT = 0x1ED694


def dependency(name):
    """Read an existing reviewed API from local Git; never copy to a worktree."""
    source = subprocess.check_output(
        ['git', 'show', DIALOG_PIN + ':tools/' + name + '.py'],
        cwd=Path(__file__).resolve().parents[1])
    module = types.ModuleType(name)
    module.__file__ = str(Path(__file__).with_name(name + '.py'))
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


R = dependency('ref_dialog')
D = dependency('difftest_dialog')

# Authored addresses/counts only. A tuple is condition, action, next node.
LAYOUT = (
    ((0x16C, None, -1), (0x1DC, None, 2), (0x1DC, 0x2E0, -1),
     (0x360, 0x418, -1), (0x4F0, None, -1)),
    ((0x5B0, None, -1), (0x810, 0x910, -1),
     (0x990, 0x418, -1), (0xA44, None, -1)),
)
ACTION_TARGETS = {0x2E0, 0x418, 0x910}


def load_inputs(directory):
    """Return (script image, two dialog blobs), all derived from owner GOB."""
    archive = (Path(directory) / (LEVELS[0].upper() + '.GOB')).read_bytes()
    lumps = [archive[o:o+n] for name, o, n in gob_entries(archive)
             if name.lower() == LEVELS[0] + '.lmp']
    assert len(lumps) == 1, 'expected one level lump'
    lump = lumps[0]
    files = {name: lump[o:o+n] for name, o, n in lmp_entries(lump)}
    scripts = [v for k, v in files.items() if k.endswith('.scr')]
    assert len(scripts) == 1, 'expected one script'
    image = scripts[0]
    script = ScriptCheck(image)
    exports = {name: offset for offset, name in scr.parse(image)['internals']}
    dialogs = {}
    for name, blob in files.items():
        if not name.endswith('.dbin'):
            continue
        nodes = R.parse_dbin(blob)
        signature = tuple((exports[node.condition],
                           exports[node.choices[0].action] if node.choices[0].action else None,
                           node.choices[0].next) for node in nodes)
        assert signature in LAYOUT, 'unresearched dialog table'
        index = LAYOUT.index(signature)
        target = script.call_values((0x3c, 0xd0)[index], 'startDialog', 3, (0,))[0]
        assert name == target + '.dbin', 'NPC dialog resource association changed'
        assert index not in dialogs
        assert all(len(n.choices) == 1 and not n.choices[0].condition for n in nodes)
        dialogs[index] = blob
    assert set(dialogs) == {0, 1}
    return image, (dialogs[0], dialogs[1])


class Inventory:
    """Explicit lower-service control, separately instantiated on both sides.

    Counts belong to the input item whose pool address is 0x3c. Search/remove
    model one matching entry per slot; this is not original inventory code.
    """
    def __init__(self, key, counts):
        self.key, self.counts = key, list(counts)
        self.log = []

    def answer(self, name, args):
        self.log.append((name, args))
        if name == 'inventory_countItemByName':
            key, slot = args
            assert key == self.key
            return self.counts[slot]
        if name == 'inventory_findItemBySubstring':
            slot, key = args
            assert key == self.key
            return (0, 0) if self.counts[slot] else (-1, 0)
        if name == 'inventory_removeItem':
            slot, index, bag, count = args
            assert (index, bag, count) == (0, 0, 0)
            assert self.counts[slot] > 0
            self.counts[slot] -= 1
            return 0
        raise AssertionError('unconfigured lower service: ' + name)


class Probe:
    """Reusable dialog+VM composition; never runs the deferred consumer.

    open()/confirm() compare original state with ref_dialog + ref_natives.
    run_entry() is a direct predicate check and is NOT dialog reachability.
    trace contains code-relative entries actually reached by the dispatcher.
    """
    def __init__(self, elf, image, dialog, seed=20973, *, evil=0,
                 item_counts=(0,), finished=0, talked=0, difficulty=0):
        assert 1 <= len(item_counts) <= 4
        assert difficulty in range(5)
        self.seed, self.difficulty = seed, difficulty
        self.image = image
        self.entries = dict(scr.parse(image)['internals'])
        self.reverse = {name: off for off, name in self.entries.items()}
        self.pool = {off: text.encode('latin1')
                     for off, text in scr.strings(image, *scr.parse(image)['strings'])}
        nodes = R.parse_dbin(dialog)
        first = self.reverse[nodes[0].condition]
        assert first in (0x16c, 0x5b0)
        site = 0x3c if first == 0x16c else 0xd0
        self.actor_name, a, b = ScriptCheck(image).call_values(site, 'startDialog', 3, (0,))
        self.open_controls = (a, b)
        rig = self.rig = N.Rig(elf)
        rig.emu.record_calls = True
        rig.checkpoint()
        assert rig.place(image + bytes(256)) == (0, 0)
        scene = self.scene = N.Scene(rig, random.Random(seed),
                                    names=[b'actor'], variables=[], objects=1)
        original_hooks = dict(rig.emu.hooks)
        host = R.Host()
        host.text = lambda _: [65]  # synthetic localization
        old = D.EE
        try:
            D.EE = lambda _: rig.emu
            self.dialog = d = D.Rig(elf, host)
        finally:
            D.EE = old
        rig.emu.follow = N.RealSet(N.REAL_OTHER)
        rig.emu.follow.addresses |= D.LEAF | {
            D.F_ON_MSG, D.F_SHOW, D.F_QUEUE_AUDIO, D.F_IS_OPEN,
            D.F_CLEAR_TEXT, D.F_SET_FOCUS, D.F_MUTEX_RELEASE}
        # The dialog harness normally stubs the VM. Restore the actual VM and
        # its libc functions, preserving original instrumentation hooks.
        for addr in list(rig.emu.hooks):
            if (N.SCRIPT_LO <= addr < N.SCRIPT_HI
                    or N.RUNTIME_LO <= addr < N.RUNTIME_HI):
                rig.emu.unhook(addr)
                if addr in original_hooks:
                    rig.emu.hooks[addr] = original_hooks[addr]
        rig.emu.unhook(RUN_SCRIPT)
        rig.emu.unhook(D.F_IS_OPEN)
        rig.emu.unhook(D.F_MUTEX_RELEASE)
        for addr in D.LEAF:
            rig.emu.unhook(addr)
        m = self.mem = rig.emu.mem
        d.file_ptr = rig.emu.alloc(len(dialog) + 16)
        m.write(d.file_ptr, dialog)
        d.entry = rig.emu.alloc(16)
        m.w32(d.entry + 4, d.file_ptr)
        obj = R.Object(0)
        obj.props['showname'] = 'speaker'
        d.place(obj)
        host.objects = {self.actor_name: [obj]}
        host.player_obj, host.alive = {}, []
        d.plant_world()
        d.plant_state(R.Dialog())
        m.write(0x41b721, LEVELS[0].encode('latin1') + b'\0')
        m.write(PLAYER, bytes(STRIDE * 4))
        m.write(N.N.G_QUEST_VARS, bytes(0x2000))
        m.write(N.N.G_DEFER_NAMES, bytes(2 * 64 * 0x50))
        for addr in (N.N.G_DEFER_COUNT, N.N.G_DEFER_QUEUED,
                     N.N.G_DEFER_FLIP, N.N.G_ACTIVE_PLAYER, N.N.G_MEDAL_MISSION):
            m.w32(addr, 0)
        m.w32(N.N.G_NUM_PLAYERS, len(item_counts))
        m.w32(N.N.G_DIFFICULTY, difficulty)
        m.w32(N.N.G_RAND_SEED, seed)
        m.w8(PLAYER + 0x4C1A, evil << difficulty)
        for slot in range(len(item_counts)):
            m.w8(PLAYER + slot * STRIDE + MISSION + difficulty * 13 + 2, 1)
        for offset, value in ((0x4C, finished), (0x74, talked)):
            rig.call(0x1ED854, scene.cstring(self.pool[offset]), value)
        self.inventory = Inventory(self.pool[0x3C], item_counts)
        rig.responder = self.inventory
        self.model_inventory = Inventory(self.pool[0x3C], item_counts)
        self.game_host = N.TestHost(self.model_inventory, N.O.World())
        self.game = N.N.Game(N.N.Mem(N.Under(m)), host=self.game_host)
        self.game.set_script(N.new_machine(image + bytes(256)))
        self.regions = [(PLAYER, STRIDE * 4), (N.N.G_QUEST_VARS, 0x2000),
                        (N.N.G_DEFER_NAMES, 2 * 64 * 0x50),
                        (N.N.G_DEFER_COUNT, 8), (N.N.G_DEFER_FLIP, 4)]
        for addr, size in self.regions:
            self.game.mem.read(addr, size)  # freeze these pages before original writes
        self.model_host = mh = R.Host()
        mh.text = lambda _: [65]
        mh.objects, mh.player_obj, mh.alive = host.objects, {}, []
        mh.run_script = lambda name: self.game.run_script(name.encode('latin1'))
        self.model = R.Dialog()
        self.nodes = R.parse_dbin(dialog)
        m.w32(D.A['node_index'], 0xFFFFFFFF)
        m.w32(D.A['prompt_node'], 0xFFFFFFFF)
        handlers = {m.cstr(m.u32(N.N.NATIVE_TABLE + i * 8)):
                    m.u32(N.N.NATIVE_TABLE + i * 8 + 4) for i in range(191)}
        self.native_handlers = [handlers[name] for _, name in scr.parse(image)['externals']]
        self.trace, self.native_calls, self.queue_calls = [], [], []
        rig.emu.hook(RUN_SCRIPT, self._trace_script)
        rig.emu.hook(N.SCR_CALL_NATIVE,
                     lambda e: self.native_calls.append(
                         self.native_handlers[e.r[5] & 0xFFFFFFFF]))
        rig.emu.hook(0x1ED52C, self._trace_queue)
        self.actual_targets = set()

    def _trace_script(self, emu):
        name = emu.mem.cstr(emu.r[4] & 0xFFFFFFFF)
        assert name in self.reverse, 'missing entry must not count as true'
        self.trace.append(self.reverse[name])

    def _trace_queue(self, emu):
        name = emu.mem.cstr(emu.r[4] & 0xFFFFFFFF)
        assert name in self.reverse
        self.queue_calls.append(self.reverse[name])

    def compare(self):
        m, d, a = self.mem, self.model, D.A
        unexpected = [c.target for c in self.rig.emu.calls
                      if c.stubbed and c.target not in self.rig.emu.hooks]
        assert not unexpected, tuple(hex(x) for x in unexpected)
        assert not self.dialog.unexpected, self.dialog.unexpected
        assert m.s32(self.rig.base + 0x5C) == 0, 'VM error'
        self.actual_targets.update(c.target for c in self.rig.emu.calls if not c.stubbed)
        assert m.s32(a['node_index']) == d.node_index
        assert bool(m.u32(a['data'])) == (d.node is not None)
        assert m.s32(a['nvis']) == len(d.visible)
        assert [m.s32(a['visible'] + i * 4) for i in range(len(d.visible))] == d.visible
        assert m.s32(a['closing']) == d.closing
        for addr, size in self.regions:
            assert m.read(addr, size) == self.game.mem.read(addr, size), hex(addr)
        assert self.inventory.log == self.model_inventory.log
        assert self.inventory.counts == self.model_inventory.counts
        assert m.u32(N.N.G_RAND_SEED) == self.seed == self.game.seed

    def run_entry(self, offset):
        expected = self.game.run_script(self.entries[offset].encode('latin1'))
        actual = self.rig.call(RUN_SCRIPT, self.dialog.cstr(self.entries[offset])) & 0xFFFFFFFF
        assert actual == expected & 0xFFFFFFFF, hex(offset)
        self.compare()
        return actual

    def open(self, *, recall=0, menu=False):
        self.mem.w8(D.G_RECALL, recall)
        self.dialog.host.recall = self.model_host.recall = recall
        self.dialog.host.mission_menu = self.model_host.mission_menu = menu
        msg = R.start_message(self.actor_name, 0, *self.open_controls, (0, 0, 0), 0, 0)
        self.model.on_open(self.model_host, msg, self.nodes, level=LEVELS[0])
        self.dialog.message(msg)
        requests = [row for row in self.dialog.log if row[0] == 'lump']
        assert requests == ([] if recall or menu else [
            ('lump', LEVELS[0] + '.lmp', self.actor_name + '.dbin')])
        self.compare()
        return self.mem.s32(D.A['node_index'])

    def confirm(self, *, revealing=0, reveal_done=1, at_end=1, blend=0x3F800000):
        """Deliver native confirm on controlled presentation-completion state."""
        for key, value in (('revealing', revealing), ('reveal_done', reveal_done),
                           ('at_end', at_end), ('blend', blend), ('cursor', 0)):
            self.mem.w32(D.A[key], value)
            setattr(self.model, key, value)
        self.model.on_confirm(self.model_host)
        self.dialog.message([R.MSG_CONFIRM])
        self.compare()

    def set_count(self, slot, count):
        """Change a controlled inventory answer on both sides between messages."""
        self.inventory.counts[slot] = self.model_inventory.counts[slot] = count

    def seed_quest(self):
        """Create one real journal entry as a fixture for removal checks."""
        title, body = self.pool[0x5C], self.pool[0x68]
        self.game.quest_add(title, body)
        self.rig.call(0x1D386C, self.scene.cstring(title), self.scene.cstring(body))
        self.compare()
        for slot in range(len(self.inventory.counts)):
            assert self.quest_count(slot) == 1

    def quest_count(self, slot=0):
        return self.mem.u32(PLAYER + slot * STRIDE + 0x43D0)

    def queued(self):
        return self.mem.u32(N.N.G_DEFER_QUEUED)


def expected_node(index, evil, count, finished):
    matches = ((evil, not evil and not count and finished == 0,
                not evil and not count and finished == 0,
                not evil and bool(count), not evil and finished == 1)
               if index == 0 else
               (not evil, evil and not count and finished == 0,
                evil and bool(count), evil and finished == 1))
    return next((i for i, answer in enumerate(matches) if answer), 0), matches


def check_case(elf, image, dialogs, seed, index, evil, count, finished,
               difficulty=0, talked=0, item_counts=None):
    p = Probe(elf, image, dialogs[index], seed, evil=evil,
              item_counts=item_counts or (count,), finished=finished,
              difficulty=difficulty, talked=talked)
    node, answers = expected_node(index, evil, sum(p.inventory.counts), finished)
    if LAYOUT[index][node][1] == 0x418:
        p.seed_quest()
    # Direct predicate checks are separate from the subsequent actual selector.
    for row, answer in zip(LAYOUT[index], answers):
        assert p.run_entry(row[0]) == int(bool(answer)), (index, hex(row[0]))
    p.trace.clear()
    assert p.open() == node, (index, evil, count, finished, node)
    last = next((i for i, value in enumerate(answers) if value), len(answers) - 1)
    assert p.trace == [r[0] for r in LAYOUT[index][:last + 1]]
    assert p.model.visible == [0]
    action = LAYOUT[index][node][1]
    p.native_calls.clear()
    p.confirm()
    if index == 0 and node == 1:
        assert p.model.node_index == 2 and not p.model.closing
        assert not ACTION_TARGETS.intersection(p.trace)
        p.confirm()
        action = 0x2E0
    selected_actions = [off for off in p.trace if off in ACTION_TARGETS]
    assert selected_actions == ([] if action is None else [action])
    assert p.model.closing == 1
    if action == 0x418:
        assert p.native_calls == [0x143540, 0x14598C, 0x143448, 0x144160]
        assert p.queue_calls == [0xC98] and p.queued() == 1
        assert p.quest_count() == 0
        assert p.game.var_get(p.pool[0x4C]) == 1
        assert p.inventory.counts == [max(0, n - 1) for n in (item_counts or (count,))]
        # Queueing is not reward execution or mission completion.
        assert 0xC98 not in p.trace
    elif action in (0x2E0, 0x910):
        assert p.native_calls == [0x1433C8, 0x143540]
        assert p.quest_count() == 1
        assert p.game.var_get(p.pool[0x74]) == 1
        assert not p.queue_calls and p.queued() == 0
    else:
        assert not p.native_calls
        assert p.quest_count() == p.queued() == 0 and not p.queue_calls
    for slot in range(len(p.inventory.counts)):
        assert p.mem.u8(PLAYER + slot * STRIDE + MISSION + difficulty * 13 + 2) == 1
    return p


def run(elf, directory, seed):
    with open(elf, 'rb') as stream:
        assert hashlib.sha256(stream.read()).hexdigest() == ELF_SHA
    image, dialogs = load_inputs(directory)
    cases, predicates, targets = 0, 0, set()
    for index, evil, count, finished, difficulty in itertools.product(
            range(2), range(2), (0, 1, 2), (-1, 0, 1, 2), (0, 4)):
        p = check_case(elf, image, dialogs, seed, index, evil, count, finished,
                       difficulty, talked=cases % 3)
        cases += 1
        predicates += len(LAYOUT[index])
        targets.update(p.actual_targets)
    print('PASS seed=%d selector/action cases=%d direct predicate checks=%d' %
          (seed, cases, predicates))
    # Party possession is summed by the native predicate, not just slot zero.
    for index in range(2):
        p = check_case(elf, image, dialogs, seed, index, index, 1, 0,
                       item_counts=(0, 1, 0, 2))
        assert len([x for x in p.inventory.log if x[0] == 'inventory_removeItem']) == 2
    print('PASS party controls=2; original handler delegates count/find/remove services')
    controls = 0
    for index in range(2):
        for recall, menu in ((1, False), (0, True)):
            p = Probe(elf, image, dialogs[index], seed, evil=index, item_counts=(1,))
            assert p.open(recall=recall, menu=menu) == -1
            assert not p.trace and p.queued() == 0 and p.quest_count() == 0
            p.open()
            p.trace.clear()
            p.confirm()
            assert p.trace == [0x418] and p.queued() == 1
            controls += 1
        for state in ({'revealing': 1, 'reveal_done': 0}, {'at_end': 0},
                      {'blend': 0}):
            p = Probe(elf, image, dialogs[index], seed, evil=index, item_counts=(1,))
            p.open()
            p.trace.clear()
            p.confirm(**state)
            assert not p.trace and p.queued() == 0
            p.confirm()
            assert p.trace == [0x418] and p.queued() == 1
            controls += 1
    print('PASS admission/presentation suppressors=%d with positive follow-ups' % controls)
    # Once the node is selected, confirm does not re-run its admission predicate.
    # This deliberately changes a lower-service answer between native messages.
    for index in range(2):
        p = Probe(elf, image, dialogs[index], seed, evil=index, item_counts=(1,))
        p.seed_quest()
        p.open()
        p.trace.clear()
        p.set_count(0, 0)
        p.confirm()
        assert p.trace == [0x418] and p.queue_calls == [0xC98]
        assert p.queued() == 1 and p.quest_count() == 0
        assert not [x for x in p.inventory.log if x[0] == 'inventory_removeItem']
    print('PASS changed-possession controls=2; selected action has no fresh possession check')
    required = {D.F_SHOW, RUN_SCRIPT, N.SCR_INTERPRET, N.SCR_CALL_NATIVE,
                0x13EAC8, 0x145590, 0x14598C, 0x1ED52C, 0x1ED778,
                0x1ED854, 0x1D386C, 0x1D3968, 0x142044}
    assert required <= targets, tuple(hex(x) for x in required - targets)
    print('PASS executed required native functions=%d; dialog message entry=0x22ee2c' % len(required))
    print('LIMIT inventory/resources/audio/presentation are controlled; deferred consumer, '
          'physical interaction and rendered GUI are not executed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('directory')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.directory, args.seed)


if __name__ == '__main__':
    main()
