#!/usr/bin/env python3
"""In-range use, portal construction from the disc, and the loader past the SIF DMA.

Round 5 for mission 2. The original functions run in ee_emu. Syscalls use
only the opt-in handlers in ee_emu.py: install_deci2_kputs and
install_terminate_thread (taken from t3/research-death-reload) and
install_modelled_sif_dma. Every fixture stub is listed in FIXTURE_STUBS and
in docs/mission2-round5.md. Property values and script names are synthetic
and derived from the seed; no disc text key is used. Private bytes stay
under the disc directory passed on the command line.
"""
import argparse
import hashlib
import os
import random
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

from difftest_mission2 import SHA256  # noqa: E402
from difftest_mission2_r4 import (  # noqa: E402
    ALLOC, BOX, CLEAR, FLUSH, FREE, FREE_HEAD, HANDLE_INIT, INTERACT, LOAD, LUMP_COUNT,
    LUMPS, NPC, OBJECT_CTOR, PLAYER_INIT, PLAYERS, POOL_INIT, POOL_NEW, PORTAL, PROMPT,
    PUSH, READ, REALLOC, SEED, SENTINEL, STACK, TEX_NAME, TRIGGER, USE, USE_MASK, cstr)
from ee_emu import EE, EmuError, MemoryFault  # noqa: E402

# cd_findFile 0x1724fc searches the table whose address is the word at 0x41bf84:
# 32-byte entries (name, then sector at +0x10 and size at +0x14), count at +0x7d00.
FIND_FILE, DIR_POINTER, DIR_COUNT_OFF = 0x1724FC, 0x41BF84, 0x7D00
LUMP_LOAD, RES_FIND = 0x173558, 0x17365C
FONT_LUMP, FONT_ENTRY, FONT = 0x5548C0, 0x5548D0, 0x4F7100   # boot 0x323f6c / 0x323f78
GATE_LOAD = 0x1B281C               # lhu of the prompt text at sp+0x440
ACTIVE_PLAYER = 0x4D8AE4           # g_scriptActivePlayer
RUN_SCRIPT, ACTION_SCRIPTS = 0x1ED694, 0x14DCC8
PUSH_TEXT = 0x173C84               # text_lookup
NPC_PROMPT, NPC_USE = 0x116D50, 0x116BD8
MUTEX_TRY, MUTEX_HELD, MUTEX = 0x22FC04, 0x22FC2C, 0x4FE53C
TRIGGER_RUN, TRIGGER_CONTAINS = 0x1ECF3C, 0x1ED238
GATE_PROMPT, GATE_USE, GATE_MENU, ADD_LEVEL = 0x27D7A0, 0x27D754, 0x27DA24, 0x27DB60
TASK_ADD, MENU_RUN, MENU_DRAW = 0x19E4A0, 0x27DD74, 0x27E2D0
DESTS, DEST_COUNT, LEVEL_NAME, TRAVEL = 0x8E3A50, 0x8E3C30, 0x41B721, 0x500AE8
SPU_HELPER, SPU_SITES = 0x35ED90, frozenset((0x210E28, 0x214120))
VU_LIGHTS, FRAME_SITE = 0x148728, 0x19D8D4
HEAP_TOP = 0x01F00000              # the emulator stack starts here
FIXTURE_STUBS = ('cd_readBlocking', 'mem_allocTagged', 'mem_realloc', 'FlushCache',
                 'dbg_checkStack', 'mem_free')


class Disc:
    """One disc directory: name lookup for cd_readBlocking and a planted cd_findFile table."""

    def __init__(self, root):
        self.files = {}
        for path in Path(root).rglob('*'):
            if path.is_file():
                self.files.setdefault(path.name.lower(), []).append(path)
        level = self.files['innovat1.gob']
        assert len(level) == 1
        self.directory = sorted(p for p in level[0].parent.iterdir() if p.is_file())
        self.reads = []

    def install(self, emu):
        disc = self

        def read(m):
            name = cstr(m.mem, m.r[4]).split(b';', 1)[0].decode('latin1').lower()
            dest, size, offset = (m.r[i] & 0xFFFFFFFF for i in (5, 6, 7))
            hits = disc.files.get(name, [])
            disc.reads.append((name, size, offset, len(hits)))
            if len(hits) != 1:
                return 0
            with hits[0].open('rb') as handle:
                handle.seek(offset)
                # Size 0 is the directory size: cd_readAsync 0x1729e8 replaces a
                # zero size with the cd_findFile size at 0x172a74.
                data = handle.read() if size == 0 else handle.read(size)
            if data:
                m.mem.write(dest, data)
            return len(data)

        def allocate(m):
            size = m.r[4] & 0xFFFFFFFF
            if size == 0 or size > 0x2000000:
                return 0
            return m.alloc(size, align=256)

        emu.stub(READ, function=read, name='cd_readBlocking')
        emu.stub(ALLOC, function=allocate, name='mem_allocTagged')
        emu.stub(REALLOC, function=lambda m: m.r[4] & 0xFFFFFFFF, name='mem_realloc')
        emu.stub(FLUSH, ret=0, name='FlushCache')
        emu.stub(STACK, ret=0, name='dbg_checkStack')
        emu.stub(FREE, ret=0, name='mem_free')

    def plant(self, emu):
        """Fill the cd_findFile table from this directory. Sectors are synthetic."""
        table = emu.mem.u32(DIR_POINTER)
        assert table and emu.mem.u32(table + DIR_COUNT_OFF) == 0
        assert len(self.directory) * 32 <= DIR_COUNT_OFF
        for index, path in enumerate(self.directory):
            name = (path.name.upper() + ';1').encode('latin1')
            assert len(name) < 16
            entry = table + 32 * index
            emu.mem.write(entry, name.ljust(16, b'\0'))
            emu.mem.w32(entry + 0x10, 0x1000 + index)
            emu.mem.w32(entry + 0x14, path.stat().st_size)
        emu.mem.w32(table + DIR_COUNT_OFF, len(self.directory))
        return table


def boot(elf, disc, directory=True, font=True):
    emu = EE(elf)
    emu.record_writes = False
    emu.record_calls = False
    disc.install(emu)
    emu.install_deci2_kputs()
    emu.install_terminate_thread()
    emu.install_modelled_sif_dma()
    emu.call(POOL_INIT, max_steps=2000000)
    emu.mem.w32(FREE_HEAD, SENTINEL)
    emu.call(HANDLE_INIT, max_steps=2000000)
    assert emu.mem.u32(FREE_HEAD) == 0x847268
    if directory:
        disc.plant(emu)
    if font:
        # The boot call at 0x323f6c, then its store at 0x323f78, done by the fixture.
        emu.mem.w32(FONT, SENTINEL)
        value = emu.call(RES_FIND, FONT_LUMP, FONT_ENTRY, max_steps=20000000) & 0xFFFFFFFF
        assert value and value != SENTINEL
        emu.mem.w32(FONT, value)
    return emu


def props(emu, entries):
    array = emu.alloc(4 * (len(entries) + 1))
    for index, entry in enumerate(entries):
        text = emu.alloc(len(entry) + 1)
        emu.mem.write(text, entry + b'\0')
        emu.mem.w32(array + 4 * index, text)
    return array


def new(emu, size):
    block = emu.call(POOL_NEW, size, max_steps=1000000) & 0xFFFFFFFF
    assert block
    return block


def vec(emu, x=0.0, y=0.0, z=0.0):
    out = emu.alloc(16)
    emu.mem.write(out, struct.pack('<3f', x, y, z))
    return out


def player(emu, seed, at):
    """Slot 0 through player_initNewCharacter with a null r11, then its GameObject."""
    emu.mem.w32(SEED, seed)
    name, look = emu.alloc(8), emu.alloc(4)
    emu.mem.write(name, b'A\0')
    assert emu.call(PLAYER_INIT, 0, 0, name, look, 0, 1, 0, 0, max_steps=8000000) == 0
    owner = new(emu, 0x590)
    emu.call(OBJECT_CTOR, owner, at, 0, props(emu, []), max_steps=8000000)
    emu.mem.w32(PLAYERS + 0x43D8, owner)
    return owner


def watch(emu):
    """Record the gate halfword, script names, and the return of selected calls."""
    seen = {'gate': [], 'scripts': [], 'returns': {}}

    def gate(m):
        # 0x1b281c follows the prompt's jalr and delay slot: v0 is the prompt result.
        seen['gate'].append((m.mem.u16((m.r[29] + 0x440) & 0xFFFFFFFF), m.r[2] & 0xFFFFFFFF))

    def script(m):
        seen['scripts'].append(cstr(m.mem, m.r[4]))

    def capture(target):
        def entry(m):
            ra = m.r[31] & 0xFFFFFFFF

            def after(n, ra=ra):
                seen['returns'].setdefault(target, []).append(n.r[2] & 0xFFFFFFFF)
                n.unhook(ra)
            m.hook(ra, after)
        return entry

    emu.hook(GATE_LOAD, gate)
    emu.hook(RUN_SCRIPT, script)
    # The prompts return to GATE_LOAD itself, so their v0 is read by gate().
    for target in (MUTEX_TRY, MUTEX_HELD):
        emu.hook(target, capture(target))
    return seen


def press(emu, mask=0x40, pad_word=0x40):
    pad = emu.alloc(0x80)
    emu.mem.w32(USE_MASK, mask)
    emu.mem.w32(pad + 8, pad_word)
    emu.mem.w32(pad + 0x0C, pad_word)
    return pad


def begin(emu):
    emu.mem.w32(ACTIVE_PLAYER, SENTINEL)
    emu.record_calls = True
    emu.record_writes = True
    emu.reset_log()


def targets(emu):
    return [call.target for call in emu.calls]


def names(seed):
    rng = random.Random(seed)
    return ['zq%06x' % rng.randrange(1 << 24) for _ in range(5)]


def push_use(elf, disc, seed):
    message, action = names(seed)[:2]
    out = {}
    for label, entries, mask, pad_word in (
            ('bare', [], 0x40, 0x40),
            ('message', [b'message=' + message.encode()], 0x40, 0x40),
            ('action', [b'message=' + message.encode(), b'action=' + action.encode()],
             0x40, 0x40),
            ('mask-clear', [b'message=' + message.encode()], 0, 0x40),
            ('pad-clear', [b'message=' + message.encode()], 0x40, 0)):
        emu = boot(elf, disc)
        owner = player(emu, seed, vec(emu))
        body = new(emu, 0x4C)
        emu.call(PUSH, body, vec(emu), 0, props(emu, entries), max_steps=8000000)
        pad = press(emu, mask, pad_word)
        seen = watch(emu)
        begin(emu)
        emu.r[2] = SENTINEL
        value = emu.call(INTERACT, owner, pad, 0, max_steps=30000000) & 0xFFFFFFFF
        called = targets(emu)
        assert called.count(PROMPT) == 1 and called.count(BOX) == 1
        assert len(seen['gate']) == 1 and seen['gate'][0][1] == 1
        uses = [call for call in emu.calls if call.target == USE]
        active = [(pc, v) for pc, a, _s, v in emu.writes if a == ACTIVE_PLAYER]
        if label == 'bare':
            # PushTrigger_prompt 0x1ecc50: no message property, halfword 0, return 1.
            assert seen['gate'][0][0] == 0 and not uses and value == 0x4D8AC0
            assert emu.mem.u32(ACTIVE_PLAYER) == SENTINEL and active == []
        else:
            assert seen['gate'][0][0] == ord('N'), seen['gate']
            assert PUSH_TEXT in called
        if label in ('mask-clear', 'pad-clear'):
            assert not uses and emu.mem.u32(ACTIVE_PLAYER) == SENTINEL and active == []
        if label in ('message', 'action'):
            assert len(uses) == 1 and not uses[0].stubbed
            assert uses[0].args[1] & 0xFFFFFFFF == 0
            assert active == [(0x1B2B70, 0)] and emu.mem.u32(ACTIVE_PLAYER) == 0
        if label == 'message':
            assert ACTION_SCRIPTS not in called and seen['scripts'] == []
        if label == 'action':
            runs = [call for call in emu.calls if call.target == ACTION_SCRIPTS]
            assert len(runs) == 1 and runs[0].args[1] & 0xFFFFFFFF == 1
            assert seen['scripts'] == [action.encode()]
        out[label] = (seen['gate'][0][0], len(uses), value)
    return out


def npc_use(elf, disc, seed):
    shown, dialog = names(seed)[2:4]
    out = {}
    for label, offset in (('front', 10.0), ('same-point', 0.0)):
        emu = boot(elf, disc)
        owner = player(emu, seed, vec(emu, offset, offset))
        body = new(emu, 0x480)
        emu.call(NPC, body, vec(emu), 0,
                 props(emu, [b'showname=' + shown.encode(), b'dialogscript=' + dialog.encode()]),
                 max_steps=8000000)
        assert emu.mem.u32(body + 0x0C) == 0x01100028 and emu.mem.u32(body + 0x368)
        pad = press(emu)
        seen = watch(emu)
        emu.mem.w32(MUTEX, 0)
        begin(emu)
        emu.call(INTERACT, owner, pad, 0, max_steps=30000000)
        called = targets(emu)
        assert called.count(NPC_PROMPT) == 1
        active = [(pc, v) for pc, a, _s, v in emu.writes if a == ACTIVE_PLAYER]
        if label == 'front':
            assert seen['gate'] == [(ord('N'), 1)] and called.count(NPC_USE) == 1
            assert seen['returns'][MUTEX_TRY] == [0] and emu.mem.u32(MUTEX) == 1
            assert seen['scripts'] == [dialog.encode()]
            assert (0x116D28, 0) in active and emu.mem.u32(ACTIVE_PLAYER) == 0
        else:
            # At the NPC's own position the prompt writes no text and returns 0,
            # so Player_interact skips the use at 0x1b2820.
            assert seen['gate'] == [(0, 0)] and NPC_USE not in called
            assert MUTEX_TRY not in called and seen['scripts'] == []
            assert emu.mem.u32(MUTEX) == 0 and emu.mem.u32(ACTIVE_PLAYER) == SENTINEL
        out[label] = (len(seen['scripts']), emu.mem.u32(MUTEX))
    return out


def trigger_use(elf, disc, seed):
    script = names(seed)[4]
    out = {}
    for label, x in (('inside', 0.0), ('outside', 1000.0)):
        emu = boot(elf, disc)
        player(emu, seed, vec(emu, x))
        body = new(emu, 0x70)
        # Trigger_ctor takes the property list in a2 (0x1ecdf8 moves it to a3).
        emu.call(TRIGGER, body, vec(emu),
                 props(emu, [b'w=100', b'h=100', b't=' + script.encode()]), max_steps=8000000)
        assert emu.mem.u32(body + 0x0C) == 3 and cstr(emu.mem, emu.mem.u32(body + 0x5C)) == \
            script.encode()
        seen = watch(emu)
        begin(emu)
        emu.call(TRIGGER_RUN, body, max_steps=30000000)
        called = targets(emu)
        assert called.count(TRIGGER_CONTAINS) == 1
        active = [(pc, v) for pc, a, _s, v in emu.writes if a == ACTIVE_PLAYER]
        if label == 'inside':
            assert seen['scripts'] == [script.encode()]
            assert active == [(0x1ED15C, 0)] and emu.mem.u8(body + 0x60) == 1
        else:
            assert seen['scripts'] == [] and active == []
            assert emu.mem.u32(ACTIVE_PLAYER) == SENTINEL and emu.mem.u8(body + 0x60) == 0
        out[label] = len(seen['scripts'])
    return out


def portal_ctor(elf, disc, seed, directory=True):
    emu = boot(elf, disc, directory=directory, font=directory)
    emu.mem.w32(SEED, seed)
    requested = []
    emu.hook(LUMP_LOAD, lambda m: requested.append(cstr(m.mem, m.r[4])))
    body = new(emu, 0x164)
    emu.mem.w32(body + 0x0C, SENTINEL)
    disc.reads.clear()
    emu.record_calls = True
    emu.reset_log()
    emu.r[2] = SENTINEL
    try:
        value = emu.call(PORTAL, body, vec(emu), 0, props(emu, []), max_steps=30000000)
    except MemoryFault as fault:
        assert not directory
        assert (fault.pc, fault.addr, fault.kind) == (0x17363C, 0, 'write'), fault
        assert requested == [b'mapicons.lmp'] and disc.reads == []
        return None
    assert directory
    assert value & 0xFFFFFFFF == 0
    assert requested == [b'mapicons.lmp', b'jumpgate.lmp'], requested
    assert disc.reads == [('mapicons.lmp', 0, 0, 1), ('jumpgate.lmp', 0, 0, 1)], disc.reads
    lumps = [cstr(emu.mem, LUMPS + i * 0x28) for i in range(emu.mem.u32(LUMP_COUNT))]
    assert lumps[-2:] == [b'mapicons.lmp', b'jumpgate.lmp'], lumps
    assert emu.mem.u32(body + 0x0C) == 0x00100008 and emu.mem.u32(body + 0x48) == 0x50DBE8
    sites = {call.site for call in emu.calls if call.target == SPU_HELPER}
    assert sites == {0x214120}
    assert emu.sif_dma and all(row[2] == 0 and row[4] == 0 for row in emu.sif_dma)
    return emu, body, len(emu.sif_dma)


def portal_use(elf, disc, seed):
    out = {}
    for label in ('locked', 'two-dests'):
        emu, body, _dmas = portal_ctor(elf, disc, seed)
        owner = player(emu, seed, vec(emu))
        emu.mem.write(LEVEL_NAME, b'innovat1\0')
        if label == 'two-dests':
            emu.mem.write(DESTS, b'hub'.ljust(0x20, b'\0'))
            emu.mem.write(DEST_COUNT, b'\x01')
        pad = press(emu)
        emu.mem.w32(TRAVEL, SENTINEL)
        seen = watch(emu)
        begin(emu)
        emu.call(INTERACT, owner, pad, 0, max_steps=300000000)
        called = targets(emu)
        dests = [cstr(emu.mem, DESTS + 0x20 * i) for i in range(emu.mem.u8(DEST_COUNT))]
        assert called.count(GATE_PROMPT) == 1 and called.count(ADD_LEVEL) == 1
        assert seen['gate'][0][0] == ord('N')
        if label == 'locked':
            # One destination: the prompt writes its lock text and returns 0.
            assert dests == [b'innovat1'] and seen['gate'] == [(ord('N'), 0)]
            assert GATE_USE not in called and GATE_MENU not in called
            assert emu.mem.u32(TRAVEL) == SENTINEL
        else:
            assert dests == [b'hub', b'innovat1'] and seen['gate'] == [(ord('N'), 1)]
            assert called.count(GATE_USE) == 1 and seen['returns'][MUTEX_HELD] == [0]
            menus = [call for call in emu.calls if call.target == GATE_MENU]
            assert len(menus) == 1 and [a & 0xFFFFFFFF for a in menus[0].args[:3]] == [0, 0, 0]
            tasks = [call.args[0] & 0xFFFFFFFF for call in emu.calls
                     if call.target == TASK_ADD and call.site in range(GATE_MENU, 0x27DB60)]
            assert tasks == [MENU_RUN, MENU_DRAW], [hex(t) for t in tasks]
            assert emu.mem.u32(TRAVEL) == 0
            assert any(row[0] == 'fx.lmp' for row in disc.reads)
        out[label] = (len(dests), seen['gate'][0][1])
    return out


def loader_sif(elf, disc, seed):
    emu = boot(elf, disc)
    emu.HEAP_HI = HEAP_TOP
    emu.stub(CLEAR, ret=0, name='clear')
    emu.mem.w32(SEED, seed)
    emu.mem.write(TEX_NAME, b'innovat1\0')
    text = emu.alloc(16)
    emu.mem.write(text, b'innovat1\0')
    disc.reads.clear()
    emu.record_calls = True
    emu.reset_log()
    try:
        emu.call(LOAD, text, max_steps=200000000)
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.size, fault.kind) == (
            0x14877C, 0x1100FFCC, 4, 'write'), fault
    else:
        raise AssertionError('loader returned')
    helpers = [call for call in emu.calls if call.target == SPU_HELPER]
    assert helpers and {call.site for call in helpers} == SPU_SITES
    assert all((call.args[3] & 0xFFFFFFFF) == 1 for call in helpers)
    assert len(emu.sif_dma) == len(helpers)
    assert [row[0] for row in emu.sif_dma] == list(range(1, len(helpers) + 1))
    first = emu.sif_dma[0]
    assert (first[1], first[3]) == (0x875C00, 0x10), first
    assert all(row[4] == 0 for row in emu.sif_dma)
    assert all(hits == 1 for _n, _s, _o, hits in disc.reads)
    read_names = [row[0] for row in disc.reads]
    assert read_names[0] == 'equipmnt.lmp' and read_names[-2:] == ['linnovat.lmp', 'loadmisc.lmp']
    lights = [call for call in emu.calls if call.target == VU_LIGHTS]
    assert [call.site for call in lights] == [FRAME_SITE]
    return len(emu.sif_dma), len(disc.reads)


def loader_without_directory(elf, disc, seed):
    """The first DMA passes; the first lump request then misses the empty table."""
    emu = boot(elf, disc, directory=False, font=False)
    emu.stub(CLEAR, ret=0, name='clear')
    emu.mem.w32(SEED, seed)
    emu.mem.write(TEX_NAME, b'innovat1\0')
    text = emu.alloc(16)
    emu.mem.write(text, b'innovat1\0')
    disc.reads.clear()
    try:
        emu.call(LOAD, text, max_steps=200000000)
    except MemoryFault as fault:
        assert (fault.pc, fault.addr, fault.kind) == (0x17363C, 0, 'write'), fault
    else:
        raise AssertionError('loader returned')
    assert len(emu.sif_dma) == 1 and emu.sif_dma[0][1] == 0x875C00
    assert disc.reads == []
    return len(emu.sif_dma)


def run(elf, root, seed):
    assert hashlib.sha256(Path(elf).read_bytes()).hexdigest() == SHA256
    disc = Disc(root)
    push = push_use(elf, disc, seed)
    npc = npc_use(elf, disc, seed)
    trig = trigger_use(elf, disc, seed)
    assert portal_ctor(elf, disc, seed, directory=False) is None
    _emu, _body, ctor_dmas = portal_ctor(elf, disc, seed)
    gate = portal_use(elf, disc, seed)
    bare_dmas = loader_without_directory(elf, disc, seed)
    dmas, reads = loader_sif(elf, disc, seed)
    print('PASS seed=%d push gate bare=%d message=0x%x uses=%d,%d controls=%d,%d' % (
        seed, push['bare'][0], push['message'][0], push['message'][1], push['action'][1],
        push['mask-clear'][1], push['pad-clear'][1]))
    print('PASS seed=%d npc scripts front=%d same-point=%d trigger inside=%d outside=%d' % (
        seed, npc['front'][0], npc['same-point'][0], trig['inside'], trig['outside']))
    print('PASS seed=%d portal ctor dmas=%d, prompt locked=%d two-dests=%d, menu tasks 2' % (
        seed, ctor_dmas, gate['locked'][1], gate['two-dests'][1]))
    print('PASS seed=%d loader no-directory dmas=%d stop=0x0017363c; '
          'directory dmas=%d reads=%d stop=0x0014877c' % (seed, bare_dmas, dmas, reads))
    print('STUBS %s; loader also game_clearLevel' % ','.join(FIXTURE_STUBS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('disc')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    run(args.elf, args.disc, args.seed)


if __name__ == '__main__':
    main()
