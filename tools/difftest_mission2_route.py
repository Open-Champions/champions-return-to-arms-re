#!/usr/bin/env python3
"""Execute mission-2 script branches and native deferred/post machinery.

Original images are read at runtime; new private identifiers are never stored
here. The existing AMX/native models are unchanged. Inventory and presentation
are controlled external services, not loaded game objects or an actual journey.
Run from the repository with unittest preloaded (tools/dis.py shadows stdlib).
"""
import argparse
import hashlib
import itertools
from pathlib import Path
import random
import struct

import difftest_natives as D
from difftest_mission2 import SHA256, ScriptCheck, lump
from dump_tables import objects_from_file
import ref_natives as N
import ref_objects as O
import ref_mission2_route as R


class Scene(D.Scene):
    """Four synthetic living players and one named creature, without a level."""

    def build(self, object_count):
        rig = self.rig
        self.num_players = 4
        for slot in range(4):
            obj = self.add_object('player')
            self.w(obj['addr'] + N.O_FLAGS, 4, N.OF_PLAYER | N.OF_CREATURE)
            rec = N.G_PLAYERS + slot * N.REC_SIZE
            rig.poke(rec, bytes(N.REC_SIZE))
            self.w(rec + N.P_OBJECT, 4, obj['addr'])
            self.w(rec + N.P_HP, 4, N.F_1)
            self.w(rec + N.P_CAPACITY, 4, D.f32(100))
            self.w(rec + N.P_STATUS, 4, 1)
        boss = self.add_object('creature')
        self.w(boss['addr'] + N.O_FLAGS, 4, N.OF_CREATURE)
        self.w(boss['addr'] + N.C_FLAGS, 8, 0)
        self.boss = boss['addr']
        for name in self.names:
            self.table.add(name, boss)
        rig.poke(O.G_NAME_KEYS, b''.join(struct.pack('<I', 0 if name is None else self.cstring(name))
                                       for name in self.table.keys))
        rig.poke(O.G_NAME_OBJS, b''.join(struct.pack('<I', 0 if obj is None else obj['addr'])
                                       for obj in self.table.objs))
        for addr in (N.G_QUEST_VARS, N.G_PROFILE_VARS):
            rig.poke(addr, bytes(0x2000))
        rig.poke(N.G_DEFER_NAMES, bytes(0x2800))
        rig.poke(N.G_POST_ACTION, bytes(0x50))
        rig.poke(N.G_PENDING_LEVEL, bytes(0x50))
        for addr in (N.G_NETWORK_MODE, N.G_ACTIVE_PLAYER, N.G_SELECTED_OBJ,
                     N.G_DIFFICULTY, N.G_PAUSED, N.G_CUTSCENE_ACTIVE,
                     N.G_JUMPGATE_TRAVEL, N.G_IN_POST_ACTION, N.G_DEFER_COUNT,
                     N.G_DEFER_QUEUED, N.G_DEFER_FLIP, N.G_DIALOG_DATA,
                     N.G_MEDAL_MISSION, N.G_SAVE_INHIBIT, N.G_LEVEL_LOADING):
            self.w(addr, 4, 0)
        self.w(N.G_NUM_PLAYERS, 4, 4)
        self.w(N.G_ALIVE_COUNT, 4, 4)
        for slot in range(4):
            self.w(N.G_ALIVE_LIST + 4 * slot, 4, slot)
        self.w(N.G_RAND_SEED, 4, self.rng.getrandbits(32))
        self.w(N.G_LOCAL_CAMERA, 4, rig.scratch)
        for i in range(3):
            self.w(rig.item_defs + 0x40 * i + 0x1d, 1, i)


class Services(D.Responder):
    """Independent identical controls on each side, with no inventory claim."""

    def __init__(self, seed, scene, items=0):
        super().__init__(seed, scene)
        self.items = items

    def answer(self, name, args):
        if name in ('dialog_isOpen', 'memcard_isBusy', 'playerSel_isRunning'):
            return 0
        if name == 'net_isLocalSlot':
            return 1
        if name == 'inventory_countItemByName':
            return self.items if args[1] == 0 else 0
        if name == 'inventory_findItemBySubstring':
            return (0, 0) if self.items and args[0] == 0 else (-1, 0)
        if name == 'inventory_giveItem':
            return 0
        if name == 'item_parseDescriptor':
            return self.scene.item_defs
        if name == 'player_itemWeight':
            return 0
        return super().answer(name, args)


class Probe:
    def __init__(self, executable, source_dir, seed):
        self.rig = D.Rig(str(executable))
        self.rig.checkpoint()
        self.seed = seed
        self.source_dir = Path(source_dir)
        self.images = {level: lump((Path(source_dir) / (level.upper() + '.GOB')).read_bytes(),
                                   'script.scr')
                       for level in ('innovat1', 'innovat2')}
        self.scripts = {level: ScriptCheck(image) for level, image in self.images.items()}
        self.cases = 0
        self.steps = 0

    def key(self, level, site, native, count=1, arg=0):
        return self.scripts[level].call_values(site, native, count, (arg,))[arg].encode('latin1')

    def setup(self, level, *, evil=0, items=0, values=(), difficulty=0):
        rig = self.rig
        image = self.images[level] + bytes(256)
        assert rig.place(image) == (0, 0)
        self.level = level
        self.machine = D.new_machine(image)
        names = [self.key('innovat2', 0x3d8, 'setCFlag', 3)]
        scene = self.scene = Scene(rig, random.Random(self.seed), names=names,
                                  variables=[], entries=[b''], objects=0)
        scene.w(N.G_DIFFICULTY, 4, difficulty)
        for slot in range(4):
            scene.w(N.G_PLAYERS + slot * N.REC_SIZE + N.P_EVIL, 1,
                    (1 << difficulty) if evil else 0)
        blob = b''.join(key.lower() + b'\0' + bytes((value & 255,)) for key, value in values)
        rig.poke(N.G_QUEST_VARS, blob + b'\0')
        self.game, self.host = scene.model(Services(self.seed, scene, items))
        self.game.machine = self.machine
        self.machine._bound = None
        self.machine.register(self.game.natives())
        rig.responder = Services(self.seed, scene, items)
        self.cases += 1

    def run(self, entry=None, task=None):
        self.game.mem.writes.clear()
        self.host.log.clear()
        self.game.draws = 0
        if task is None:
            name = self.scripts[self.level].entry_at(entry).encode('latin1')
            pointer = self.scene.cstring(name)
            model = lambda: self.game.run_script(name)
            original = lambda: N.s32(self.rig.call(D.A['script_runByName'], pointer,
                                                  max_steps=4000000))
        else:
            model = {'post': self.game.run_post_action,
                     'deferred': self.game.run_deferred}[task]
            addr = D.A['script_runPostAction' if task == 'post' else 'script_runDeferred']
            # These native void task functions leave a scratch return register.
            def original():
                self.rig.call(addr, max_steps=4000000)
                return None
        result = []
        def capture():
            value = model()
            result.append(value)
            return value
        outcome = D.compare(self.rig, self.machine, self.game, self.host, capture, original)
        assert outcome.fault is None, ('unexpected fault', outcome.fault)
        assert not outcome.problems, outcome.problems
        assert not self.rig.unknown, tuple(self.rig.unknown)
        self.steps += 1
        return result[0]

    def quest_value(self, key):
        # Read without vars_get's append-on-miss side effect.
        mem, addr = self.rig.emu.mem, N.G_QUEST_VARS
        while mem.u8(addr):
            name = mem.cstr(addr).encode('latin1')
            addr += len(name) + 1
            value = N.s8(mem.u8(addr))
            if name == key.lower():
                return value
            addr += 1
        return 0

    def entry_buffer(self, addr, expected):
        assert self.rig.emu.mem.cstr(addr) == self.scripts[self.level].entry_at(expected)

    def complete(self):
        m = self.rig.emu.mem
        difficulty = m.u32(N.G_DIFFICULTY)
        return tuple((m.u8(N.G_PLAYERS + slot * N.REC_SIZE + N.P_MISSIONS +
                          difficulty * 13 + 2) >> 1) & 1 for slot in range(4))


def predicates(p):
    done = p.key('innovat1', 0x274, 'getv')
    offered = p.key('innovat1', 0x348, 'setv', 2)
    assert done != offered
    for site in (0x540, 0x8a4, 0xa90, 0xeb4, 0x1014):
        assert p.key('innovat1', site, 'getv') == done
    for site in (0xf50, 0x10b0):
        assert p.key('innovat1', site, 'getv') == offered
    for entry, evil, count, offer, complete in itertools.product(
            R.PREDICATES, (0, 1), (0, 1, 2), (-1, 0, 1), (-1, 0, 1)):
        p.setup('innovat1', evil=evil, items=count, difficulty=p.cases % 3,
                values=((done, complete), (offered, offer)))
        assert p.run(entry) == R.predicate(entry, evil, count, offer, complete), hex(entry)


def objectives(p):
    first = p.scripts['innovat1']
    done = p.key('innovat1', 0x44c, 'setv', 2)
    offered = p.key('innovat1', 0x348, 'setv', 2)
    intro = p.key('innovat1', 0xc14, 'getv', 2)
    for entry, site in ((0, 0x3c), (0x94, 0xd0)):
        for already_open in (0, 1):
            p.setup('innovat1')
            p.rig.w32(N.G_DIALOG_DATA, already_open)
            p.run(entry)
            messages = [args[1] for name, args in p.rig.calls if name == 'net_sendGameMsg']
            assert len(messages) == (not already_open)
            if messages:
                target = p.key('innovat1', site, 'startDialog', 3)
                assert messages[0][2:2 + messages[0][1]] == target
    for entry, predicate, evil in ((0x54, 0xe48, 0), (0xe8, 0xfa4, 1)):
        for count in (0, 1):
            p.setup('innovat1', evil=evil, items=count, values=((offered, 1),))
            assert p.run(entry) == R.predicate(predicate, evil, count, 1, 0)
    # These two auxiliary exchange actions have only two authored arguments to
    # a three-argument native. Execute that packet unchanged; do not repair it.
    # Standalone execution supplies the third value from the saved AMX frame.
    for entry in (0x790, 0x1278):
        p.setup('innovat1', items=1)
        p.run(entry)
        parsed = [args for name, args in p.rig.calls if name == 'item_parseDescriptor']
        assert len(parsed) == 4 and all(args[3] == 0 for args in parsed)
        assert sum(name == 'inventory_removeItem' for name, _ in p.rig.calls) == 1
        assert p.complete() == (0, 0, 0, 0)
    for count in (0, 1, 2):
        p.setup('innovat1', items=count)
        p.run(0xc98)
        assert p.complete() == (1, 1, 1, 1)
        assert sum(name == 'inventory_giveItem' for name, _ in p.rig.calls) == 4
        assert sum(name == 'inventory_removeItem' for name, _ in p.rig.calls) == (count > 1)
    for prior in (0, 1):
        p.setup('innovat1', values=((intro, prior),))
        p.run(0xb00)
        p.entry_buffer(N.G_POST_ACTION, 0xbe0)
        assert p.complete() == (0, 0, 0, 0)
        for site, value in ((0xb68, 1), (0xb9c, 2)):
            assert p.quest_value(p.key('innovat1', site, 'setv', 2)) == value
        p.run(task='post')
        assert p.quest_value(intro) == 1
        calls = [name for name, _args in p.rig.calls]
        assert calls.count('cut_start') == (not prior)
        assert p.rig.emu.mem.u8(N.G_POST_ACTION) == 0
        assert p.rig.emu.mem.u8(N.G_IN_POST_ACTION) == 0
    for evil, action in ((0, 0x2e0), (1, 0x910)):
        p.setup('innovat1', evil=evil, items=1)
        p.run(action)
        assert p.quest_value(offered) == 1 and p.quest_value(done) == 0
        title, body = first.call_values(0x314 if not evil else 0x944, 'addQuest', 2, (0, 1))
        for slot in range(4):
            rec = N.G_PLAYERS + slot * N.REC_SIZE
            assert p.rig.emu.mem.u32(rec + N.P_QUEST_COUNT) == 1
            assert p.rig.emu.mem.cstr(rec + N.P_QUESTS) == title
            assert p.rig.emu.mem.cstr(rec + N.P_QUESTS + 0x20) == body
        p.run(0x418)
        assert p.quest_value(done) == 1
        assert p.complete() == (0, 0, 0, 0)
        assert p.rig.emu.mem.u32(N.G_DEFER_QUEUED) == 1
        assert sum(name == 'inventory_removeItem' for name, _ in p.rig.calls) == 1
        for slot in range(4):
            assert p.rig.emu.mem.u32(N.G_PLAYERS + slot * N.REC_SIZE + N.P_QUEST_COUNT) == 0
        p.run(task='deferred')
        assert p.complete() == (0, 0, 0, 0)
        assert p.rig.emu.mem.u32(N.G_DEFER_COUNT) == 1
        p.run(task='deferred')
        assert p.complete() == (1, 1, 1, 1)
        assert sum(name == 'inventory_giveItem' for name, _ in p.rig.calls) == 4
        assert p.rig.emu.mem.u32(N.G_DEFER_COUNT) == 0
        p.run(task='deferred')
        assert not p.rig.calls


def boss(p):
    gate = p.key('innovat2', 0x13c, 'getv')
    seen = p.key('innovat2', 0x248, 'getv')
    assert gate != seen
    for prior in (0, 1):
        p.setup('innovat2', values=((seen, prior), (gate, 0)))
        assert p.run(0x110) == 0
        p.run(0x150)
        assert p.quest_value(seen) == 1
        if not prior:
            p.entry_buffer(N.G_POST_ACTION, 0x32c)
            assert p.rig.emu.mem.u32(N.G_SAVE_INHIBIT) == 0
            p.run(task='post')
        assert p.rig.emu.mem.u32(N.G_SAVE_INHIBIT) == (not prior)
        assert p.rig.emu.mem.u64(p.scene.boss + N.C_FLAGS) & 1
        p.run(0x0)
        assert p.quest_value(gate) == 1
        assert p.rig.emu.mem.u32(N.G_SAVE_INHIBIT) == 0
        assert p.run(0x110) == 1
    for value in (-1, 0, 1):
        p.setup('innovat2', values=((gate, value),))
        assert p.run(0x110) == value
        p.run(0x194)
        # The wrapper emits its info call only while the gate is zero.
        assert sum(name == 'hud_showMessage' for name, _ in p.rig.calls) == (value == 0)
    left = p.key('innovat2', 0xb4, 'getv')
    right = p.key('innovat2', 0xdc, 'getv')
    assert left != right
    for a, b in itertools.product((-1, 0, 1), repeat=2):
        p.setup('innovat2', values=((left, a), (right, b)))
        assert p.run(0x88) == int(bool(a) or not b)
    for item_count in (0, 1, 2):
        p.setup('innovat2', items=item_count)
        p.run(0x1d8)
        assert p.rig.emu.mem.u32(N.G_DEFER_QUEUED) == 1
        p.run(task='deferred')
        assert not p.rig.calls  # queue promotion does not execute the entry
        for tick in range(1, 63):
            p.run(task='deferred')
            queries = [args for name, args in p.rig.calls if name == 'inventory_countItemByName']
            removals = [args for name, args in p.rig.calls if name == 'inventory_removeItem']
            assert len(queries) == (4 if tick == 61 else 0)
            assert len(removals) == int(tick == 61 and item_count > 1)
            assert p.rig.emu.mem.u32(N.G_DEFER_COUNT) == 1
            assert p.rig.emu.mem.u32(N.G_DEFER_QUEUED) == 0


def death(p):
    path = p.source_dir / 'INNOVAT2.GOB'
    rows = [row for row in objects_from_file(str(path), path.read_bytes())
            if row['class'] == 'IronGuardian']
    assert len(rows) == 1
    authored = [part.encode('latin1') for part in rows[0]['properties'].split(';') if part]
    def value(key):
        found = [part[len(key) + 1:] for part in authored if part.startswith(key + b'=')]
        assert len(found) == 1
        return found[0]
    script, descriptor = value(b'deathscript'), value(b'dropitem')
    assert script.decode('latin1') == p.scripts['innovat2'].entry_at(0)
    assert descriptor == p.key('innovat1', 0x480, 'removePlayerItem', 2, 1)
    gate = p.key('innovat2', 0x13c, 'getv')
    for quiet, has_script, has_drop in itertools.product((0, 1), repeat=3):
        p.setup('innovat2', values=((gate, 0),))
        rig, obj = p.rig, p.game.world.objects[p.scene.boss]
        props = [part for part in authored
                 if (has_script or not part.startswith(b'deathscript='))
                 and (has_drop or not part.startswith(b'dropitem='))]
        obj.props = props
        ptr = p.scene.tables_at
        rig.poke(ptr, b''.join(struct.pack('<I', p.scene.cstring(part)) for part in props) + bytes(4))
        rig.w32(obj.addr + N.O_PROPS, ptr)
        rig.poke(obj.addr + N.C_FLAGS, struct.pack('<Q', 0x12345678ffffffff))
        rig.w32(N.G_SAVE_INHIBIT, 1)
        rig.w32(0x4f7120, 0)  # no PvP scoring
        rig.real.addresses.add(0x10beb8)
        rig.emu.stub(0x1192f8, ret=0)  # music-stop helper, not part of the gate
        rig.stub_addrs.add(0x1192f8)
        original_drop = rig.emu.hooks[0x100ba0]
        # Observe that the gate has already changed when the drop call is made.
        order = []
        def observe_drop(e):
            order.append(p.quest_value(gate))
            return original_drop(e)
        rig.emu.hook(0x100ba0, observe_drop)
        def original():
            rig.call(0x10beb8, obj.addr, quiet, max_steps=4000000)
        outcome = D.compare(rig, p.machine, p.game, p.host,
                            lambda: R.death(p.game, obj, quiet,
                                            script if has_script else None,
                                            descriptor if has_drop else None), original)
        rig.emu.hooks[0x100ba0] = original_drop
        assert outcome.fault is None and not outcome.problems, outcome.problems
        assert not rig.unknown, tuple(rig.unknown)
        p.steps += 1
        assert p.quest_value(gate) == has_script
        assert rig.emu.mem.u32(N.G_SAVE_INHIBIT) == (not has_script)
        assert rig.emu.mem.u32(N.G_SELECTED_OBJ) == 0
        assert order == ([int(has_script)] if not quiet and has_drop else [])
        assert sum(name == 'loot_spawnNamedItem' for name, _ in rig.calls) == (not quiet and has_drop)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--group', choices=('predicates', 'objectives', 'boss', 'death', 'all'), default='all')
    args = parser.parse_args()
    assert hashlib.sha256(args.executable.read_bytes()).hexdigest() == SHA256
    p = Probe(args.executable, args.source_dir, args.seed)
    for name, function in (('predicates', predicates), ('objectives', objectives), ('boss', boss),
                           ('death', death)):
        if args.group in (name, 'all'):
            function(p)
    print(f'PASS seed {args.seed}: {p.cases} controlled states, {p.steps} original VM/task comparisons; '
          'inventory/presentation services stubbed, no actual scene travel')


if __name__ == '__main__':
    main()
