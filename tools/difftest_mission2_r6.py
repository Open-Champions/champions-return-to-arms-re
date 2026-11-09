#!/usr/bin/env python3
"""Round 6 for mission 2: the portal menu end to end, and the level loader to arrival.

The original functions run in ee_emu. Every emulator opt-in is named in
OPT_INS, every fixture stub in FIXTURE_STUBS, and every word the fixture
supplies in place of boot or engine_init in SUPPLIED. All of them are
described in docs/mission2-round6.md. Destination names in the menu cases
are synthetic and derived from the seed. The end-to-end chain loads the
disc's hub level by its level name. No disc text key is used, and success
output prints counts and addresses only.
"""
import argparse
import copy
import hashlib
import os
import random
import struct
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE] + [_HERE]

from difftest_mission2 import SHA256  # noqa: E402
import difftest_mission2_r5 as r5  # noqa: E402
from difftest_mission2_r5 import (  # noqa: E402
    CLEAR, DEST_COUNT, DESTS, FONT, FONT_ENTRY, FONT_LUMP, FREE_HEAD, GATE_MENU, HANDLE_INIT,
    HEAP_TOP, INTERACT, LEVEL_NAME, LOAD, LUMP_LOAD, MENU_DRAW, MENU_RUN, POOL_INIT, PORTAL,
    RES_FIND, RUN_SCRIPT, SEED, SENTINEL, SPU_HELPER, SPU_SITES, TEX_NAME, TRAVEL, VU_LIGHTS,
    Disc, cstr, new, player, press, props, vec)
from ee_emu import EE, CpuTrap, EmuError, MemoryFault, UnimplementedInstruction  # noqa: E402

# Startup's constructor list: -1 at 0x3e9980, then entries to a zero word.
# The runner 0x3ad250 counts them (0x3ad280-0x3ad2bc) and calls the last first
# (0x3ad2d0-0x3ad2ec).
CTOR_MARK, CTOR_COUNT = 0x3E9980, 124
SKILL63, SKILL_VTABLE_OFF = 0x6E2E08, 0x60      # g_skillTable[63] = 0x41b26c

# Menu state (jumpgate_menuRun 0x27dd74, jump table 0x547f60).
STATE, CHOOSER, SELECTED, CURRENT, FADE, FIXED = (
    0x8E3A3A, 0x8E3A3B, 0x8E3A38, 0x8E3A40, 0x8E3A3C, 0x8E3C34)
PENDING, ORIENT = 0x41B6D0, 0x41B720
PADS, PRESSED, SECOND = 0x41BFD8, 0x0C, 0x10    # g_pads[0]; stride 0x58
CONFIRM_BIT, CANCEL_BIT, UP_BIT, DOWN_BIT = 0x40, 0x20, 0x1000, 0x4000
PAUSE_WORD, PAUSE_BYTE = 0x41B4F4, 0x44FA80
SAVE_DESTS, LOAD_DESTS, DEST_BLOCK = 0x27DCF4, 0x27DD30, 0x1E4
TASK_REMOVE, LOCK_INPUT, BEGIN_TRAVEL, CLOSE_PAUSE = 0x19E664, 0x13E4E8, 0x27E6A8, 0x18DF90

# Loader, request and arrival.
REQUEST = 0x320EDC                 # mainloop_loadRequestedWorld
STORE_LEVEL = 0x21777C             # save_storeLevelState
LOAD_RECORDS, FACTORY_SITE = 0x14E808, 0x14E9A0
FACTORY_WORD, FACTORY = 0x5F76F4, 0x159C94
PLAYER_CTOR, SPAWN, FACING, RANK = 0x1A1D28, 0x4F70D0, 0x4F8410, 0x4F7108
PREV_LEVEL, SAVED_ORIENT, SUB_NAME = 0x41B7C2, 0x41B7C1, 0x41B771
LARGEST_FREE, DUMP_HEAP = 0x150858, 0x150290
ALLOC, SEGMENT_SITE, SEGMENT_BYTES = 0x14FF88, 0x1825B4, 0x760000   # world_prepare's cache
STRCPY, COPY_SITE, ORIENT_STORE = 0x3B868C, 0x27E1F8, 0x27E210
NEXT_WORLD = (PENDING, 0x41B7E2 - PENDING)       # g_pendingLevel .. end of g_prevLevelName
FIND_FILE = 0x1724FC                              # cd_findFile
ARMOR, SKILL_FRACTION = 0x1B5790, 0x308A7C        # player_recalcArmor, skill 63's getStat0Fraction
CUT_SCENE = 0x143F1C


# Words engine_init and boot would have written. Each entry: label, what is stored.
GIF_CHANNEL = 0x8400D0             # engine_init -> 0x19bd7c, store at 0x19bd94
GFX_SEMA = 0x6E4060                # 0x16c4b8 (engine_init 0x19d700), store at 0x16c69c
VSYNC_SEMAS = (0x8400F0, 0x8400F4)  # engine_init stores at 0x19d2d4, 0x19d348
INTC_ID = 0x44FD4C                 # AddIntcHandler result, store at 0x19d390
TEXCACHE_RING = 0x7CFD40           # texcache_init via texcache_setRange (0x19d6f8)
CAMERA, CAMERA_OBJ = 0x4F8450, 0x86AD68   # game_initCamera 0x1e6b8c, 0x1e6bb0
LIBC_SEMAS = (0x5075D0, 0x5075D4)  # 0x35c050 (startup 0x35c2a8), stores 0x35c098, 0x35c0a4
SUPPLIED = ('constructors', 'g_levelName', 'gif-channel', 'gfx-semaphore', 'texcache',
            'vsync-semaphores', 'intc-handler', 'camera', 'object-factory', 'libc-semaphores')
OPT_INS = ('install_deci2_kputs', 'install_terminate_thread', 'install_modelled_sif_dma',
           'install_modelled_boot', 'install_vu1_data_memory', 'install_ram_mirrors',
           'install_modelled_dma_idle', 'install_modelled_dma_tag_address',
           'install_modelled_vpu_stat', 'install_modelled_intc(while_disabled=True)',
           'install_modelled_gs_privileged', 'install_modelled_timer0_count(0x2626)',
           'install_modelled_end_of_heap', 'install_modelled_main_ram')
FIXTURE_STUBS = r5.FIXTURE_STUBS + ('game_clearLevel', 'mem_largestFree', 'mem_dumpHeap')
TIMER_COUNT = 0x2626               # the divisor at 0x19dccc: one frame's count, chosen
HIGH_HEAP = (0x04000000, 0x08000000)
LEVEL = b'innovat1'

# Values read once from a --discover run, then asserted.
EXPECT = {
    # Return address at each ablation's stop: the call that led to it.
    'ablation-ra': {
        'gif-channel': 0x350640,        # sceDmaSend's call of the DMA wait at 0x350638
        'gfx-semaphore': 0x16C45C,      # SignalSema called at 0x16c454
        'texcache': 0x17FB0C,           # texcache_reset called at 0x17fb04
        'vsync-semaphores': 0x19DB8C,   # PollSema called at 0x19db84
        'camera': 0x19B5B8,             # Camera_setMode called from cut_start at 0x19b5b0
        'g_levelName': 0x17363C,        # the print at 0x173634 before the store to 0
        'object-factory': EE.RETURN_ADDR,
        'libc-semaphores': 0x3B61D0,    # WaitSema called from malloc's lock at 0x3b61c8
    },
    'lmp-ra': 0x173720,                 # lump_load called at 0x173718, inside res_find
    # (pc, address, value) of each store the request makes to the watched bytes:
    # the copy into g_prevLevelName, the subname cleared, 0xfe, the saved 0xff.
    'request-writes': [(0x3B8784, PREV_LEVEL, LEVEL[0]), (0x3210E4, SUB_NAME, 0),
                       (0x32112C, ORIENT, 0xFE), (0x321138, SAVED_ORIENT, 0xFF)],
    # The load clears the rank byte, then the destination gate stores 3.
    'rank-writes': [(0x217AB0, 0), (0x27CA84, 3)],
    # Every cd_findFile call site reached in the round-6 runs.
    'find-sites': [0x1001D4, 0x173584, 0x1A26DC, 0x1A2780, 0x321F28],
}


class Disc6(Disc):
    """Round 5's disc fixture with a chosen synthetic sector numbering.

    Base 0x1000 and step 1 plant exactly round 5's table.  Every call to
    cd_findFile is recorded by its return address in find_sites.
    """

    def __init__(self, root, base=0x1000, step=1):
        Disc.__init__(self, root)
        self.base, self.step = base, step
        self.find_sites = []

    def install(self, emu):
        Disc.install(self, emu)
        sites = self.find_sites
        emu.hook(FIND_FILE, lambda m: sites.append((m.r[31] & 0xFFFFFFFF) - 8))

    def plant(self, emu):
        table = Disc.plant(self, emu)
        for index in range(len(self.directory)):
            emu.mem.w32(table + 32 * index + 0x10, self.base + self.step * index)
        return table


def check(key, value, discover):
    """Assert a value read once from a --discover run, or print it while discovering."""
    if discover or EXPECT[key] is None:
        print('DISCOVER', key, value)
        return
    assert value == EXPECT[key], (key, value)


def run_constructors(emu):
    """Startup's constructor runner, without its frame-info and atexit calls."""
    assert emu.mem.u32(CTOR_MARK) == 0xFFFFFFFF
    entries, addr = [], CTOR_MARK + 4
    while emu.mem.u32(addr):
        entries.append(emu.mem.u32(addr))
        addr += 4
    assert len(entries) == CTOR_COUNT
    for function in reversed(entries):
        emu.call(function, max_steps=5000000)
    return len(entries)


def boot6(elf, disc):
    """Round-5 boot with startup's static constructors run first."""
    emu = EE(elf)
    emu.record_writes = False
    emu.record_calls = False
    disc.install(emu)
    emu.install_deci2_kputs()
    emu.install_terminate_thread()
    emu.install_modelled_sif_dma()
    assert emu.mem.u32(SKILL63 + SKILL_VTABLE_OFF) == 0
    run_constructors(emu)
    assert emu.mem.u32(SKILL63 + SKILL_VTABLE_OFF) != 0
    emu.call(POOL_INIT, max_steps=2000000)
    emu.mem.w32(FREE_HEAD, SENTINEL)
    emu.call(HANDLE_INIT, max_steps=2000000)
    assert emu.mem.u32(FREE_HEAD) == 0x847268
    disc.plant(emu)
    emu.mem.w32(FONT, SENTINEL)
    value = emu.call(RES_FIND, FONT_LUMP, FONT_ENTRY, max_steps=20000000) & 0xFFFFFFFF
    assert value and value != SENTINEL
    emu.mem.w32(FONT, value)
    return emu


def create_sema(emu, max_count):
    param = emu.alloc(0x18)
    emu.mem.w32(param + 4, max_count)
    emu.mem.w32(param + 8, 0)
    sid = emu.call(0x3529E0, param, max_steps=100) & 0xFFFFFFFF
    assert sid
    return sid


def supply_engine_state(emu):
    """The words engine_init and boot store before a load, made by their own calls."""
    emu.install_modelled_boot()
    chan = emu.call(0x3502E8, 2, max_steps=100) & 0xFFFFFFFF     # sceDmaGetChan(2)
    assert chan == 0x1000A000
    emu.mem.w32(GIF_CHANNEL, chan)
    emu.mem.w32(GFX_SEMA, create_sema(emu, 0x186A0))               # 0x16c66c-0x16c684
    # texcache_setRange(*0x83d298, 0x400000 - it); 0x83d298 = 0x359000 (0x19d314-0x19d338).
    emu.call(0x17A3A0, 0x359000, 0x400000 - 0x359000, max_steps=5000000)
    assert emu.mem.u32(TEXCACHE_RING) == 0x7CFE00
    for word in VSYNC_SEMAS:                                         # 0x19d2a4-0x19d2d0
        emu.mem.w32(word, create_sema(emu, 0x7FFFFC17))
    emu.mem.w32(INTC_ID, emu.call(0x3526C0, 2, 0x19B6E4, 0, max_steps=100) & 0xFFFFFFFF)
    assert emu.call(0x353528, 2, max_steps=1000) & 0xFFFFFFFF == 1  # EnableIntc(2)
    emu.call(0x2071A8, CAMERA_OBJ, max_steps=2000000)               # Camera_init
    emu.mem.w32(CAMERA, CAMERA_OBJ)
    emu.call(0x15DA54, max_steps=100)                                # objects_registerFactory
    assert emu.mem.u32(FACTORY_WORD) == FACTORY
    emu.call(0x35C050, max_steps=1000)                               # libc semaphores
    assert all(emu.mem.u32(word) for word in LIBC_SEMAS)


def install_hardware(emu, upto=None):
    """The emulator models in the order the loader needs them."""
    steps = HARDWARE if upto is None else HARDWARE[:upto]
    for _label, apply in steps:
        apply(emu)


def _heap_stubs(emu):
    emu.stub(LARGEST_FREE, ret=0, name='mem_largestFree')
    emu.stub(DUMP_HEAP, ret=0, name='mem_dumpHeap')


def _high_heap(emu):
    emu._heap, emu.HEAP_HI = HIGH_HEAP


def _libc_heap(emu):
    emu.install_modelled_end_of_heap()
    emu.install_modelled_main_ram()


HARDWARE = (
    ('vu1-data', lambda e: e.install_vu1_data_memory()),
    ('ram-mirrors', lambda e: e.install_ram_mirrors()),
    ('dma-idle', lambda e: e.install_modelled_dma_idle()),
    ('dma-tag-address', lambda e: e.install_modelled_dma_tag_address()),
    ('vpu-stat', lambda e: e.install_modelled_vpu_stat()),
    ('intc', lambda e: e.install_modelled_intc(while_disabled=True)),
    ('gs', lambda e: e.install_modelled_gs_privileged()),
    ('timer0', lambda e: e.install_modelled_timer0_count(TIMER_COUNT)),
    ('heap-diagnostics', _heap_stubs),
    ('high-heap', _high_heap),
    ('libc-heap', _libc_heap),
)


def stop_of(emu, steps):
    """Run on from the current pc. Return ('return', v0) or the stop's description."""
    try:
        reason = emu.run(max_steps=steps)
    except MemoryFault as fault:
        return ('fault', fault.pc, fault.addr, fault.size, fault.kind)
    except UnimplementedInstruction as error:
        return ('unimplemented', error.pc)
    except CpuTrap as trap:
        return ('trap', str(trap))
    except EmuError as error:
        return ('error', str(error))
    assert reason == 'return', reason
    return ('return', emu.r[2] & 0xFFFFFFFF)


def loader_snapshot(elf, disc, seed):
    """game_loadLevel(innovat1) under the round-5 loader fixture, to light_writeVuConstants."""
    emu = boot6(elf, disc)
    supply_engine_state(emu)
    emu.HEAP_HI = HEAP_TOP
    emu.stub(CLEAR, ret=0, name='clear')
    emu.mem.w32(SEED, seed)
    emu.mem.write(TEX_NAME, LEVEL + b'\0')
    emu.mem.write(LEVEL_NAME, LEVEL + b'\0')     # the request split in 0x320edc sets this
    text = emu.alloc(16)
    emu.mem.write(text, LEVEL + b'\0')
    disc.reads.clear()
    emu.r[4] = text
    emu.r[31] = EE.RETURN_ADDR
    emu.jump(LOAD)
    assert emu.run(until=(VU_LIGHTS,), max_steps=200000000) == 'stop'
    # Round 5's counts at the same point: the SPU helper only from its two sites.
    assert len(emu.sif_dma) == 653, len(emu.sif_dma)
    assert [row[0] for row in emu.sif_dma] == list(range(1, 654))
    assert emu.sif_dma[0][1] == 0x875C00 and emu.sif_dma[0][3] == 0x10
    assert len(disc.reads) == 23 and all(hits == 1 for *_x, hits in disc.reads)
    assert (emu.r[31] & 0xFFFFFFFF) == 0x19D8DC   # called from gfx_beginFrame at 0x19d8d4
    return emu, list(disc.reads)


# Stops, in order, after each hardware step. Discovered once, then asserted.
HARDWARE_STOPS = (
    ('fault', 0x14877C, 0x1100FFCC, 4, 'write'),     # none: round 5's VU1 store
    ('fault', 0x19C8A4, 0x3083FAD8, 8, 'write'),     # vu1-data: uncached-accelerated store
    ('fault', 0x3501AC, 0x1000A000, 4, 'read'),      # ram-mirrors: GIF channel control word
    ('fault', 0x350644, 0x1000A030, 4, 'read'),      # dma-idle: GIF tag address word
    ('unimplemented', 0x34FF5C),                    # vpu-stat not yet: CFC2 at 0x34ff5c
    ('trap', 'SYSCALL at 0x00352a24 (v1 = 68, a0 = 2); modelled WaitSema count is 0'),
    ('fault', 0x19B6FC, 0x12000000, 8, 'write'),     # intc: the vsync handler's GS store
    ('fault', 0x19DCD0, 0x10000000, 4, 'read'),      # gs: timer 0 count in gfx_endFrame
    ('fault', 0x15086C, 0x00000002, 2, 'read'),      # timer0: mem_largestFree's heap walk
    ('error', 'test heap exhausted'),                # heap-diagnostics: 0x760000 at 0x1825b4
    ('trap', 'SYSCALL at 0x003529c4 (v1 = 62); no kernel is modelled'),   # libc sbrk
    ('return', 0x004F0000),                          # libc-heap: game_loadLevel returns
)
ABLATION_STOPS = {
    'gif-channel': ('fault', 0x3501AC, 0, 4, 'read'),
    'gfx-semaphore': ('trap', 'SYSCALL at 0x00352a04 (v1 = 66, a0 = 0); '
                              'modelled semaphore was not created'),
    'texcache': ('fault', 0x179B30, 0x18, 2, 'write'),
    'vsync-semaphores': ('trap', 'SYSCALL at 0x00352a34 (v1 = 69, a0 = 0); '
                                 'modelled semaphore was not created'),
    'camera': ('fault', 0x207304, 0x34, 4, 'write'),
    'g_levelName': ('fault', 0x17363C, 0, 4, 'write'),
    'object-factory': ('return', 0x004F0000),
    'libc-semaphores': ('trap', 'SYSCALL at 0x00352a24 (v1 = 68, a0 = 0); '
                                'modelled semaphore was not created'),
}


def loader_chain(snapshot, disc, discover=False):
    results = []
    for index in range(len(HARDWARE) + 1):
        emu = copy.deepcopy(snapshot)
        install_hardware(emu, index)
        emu.record_calls = True
        emu.reset_log()
        stop = stop_of(emu, 30000000)
        results.append(stop)
        if discover:
            print('DISCOVER hardware', index, HARDWARE[index - 1][0] if index else 'none', stop)
            continue
        expected = HARDWARE_STOPS[index]
        assert stop == expected, (index, stop)
        assert emu.vu1_reads == [], emu.vu1_reads[:4]   # no load from the VU1 window
        if index == 9:
            # world_prepare's segment cache: the size is the segment count << 17.
            asks = [c for c in emu.calls if c.site == SEGMENT_SITE]
            assert [(c.target, c.args[0] & 0xFFFFFFFF) for c in asks] == [
                (ALLOC, SEGMENT_BYTES)], asks
        if index == 1:
            # Store and readback only: nine stores, all from light_writeVuConstants.
            writes = emu.vu1_writes
            assert len(writes) == 9 and all(0x14877C <= pc <= 0x1487C0 for pc, *_r in writes)
            assert sorted({addr for _pc, addr, _s, _v in writes}) == [0x1100FFAC] + list(
                range(0x1100FFC0, 0x1100FFE0, 4))
            for _pc, addr, size, value in writes:
                assert emu.mem.load(addr, size) == value
    return results


def ablations(full, discover=False):
    """From the full fixture at the snapshot, remove one supplied word at a time."""
    cases = (
        ('gif-channel', ((GIF_CHANNEL, 0),)),
        ('gfx-semaphore', ((GFX_SEMA, 0),)),
        ('texcache', ((TEXCACHE_RING, 0),)),
        ('vsync-semaphores', tuple((word, 0) for word in VSYNC_SEMAS)),
        ('camera', ((CAMERA, 0),)),
        ('g_levelName', ((LEVEL_NAME, 0),)),
        ('object-factory', ((FACTORY_WORD, 0),)),
        ('libc-semaphores', tuple((word, 0) for word in LIBC_SEMAS)),
    )
    out = {}
    lumps = []
    callers = {}
    for label, words in cases:
        emu = copy.deepcopy(full)
        for addr, value in words:
            emu.mem.w32(addr, value)
        emu.record_calls = True
        emu.reset_log()
        if label == 'g_levelName':
            emu.hook(LUMP_LOAD, lambda m: lumps.append(
                (cstr(m.mem, m.r[4]), m.r[31] & 0xFFFFFFFF)))
        stop = stop_of(emu, 40000000)
        out[label] = stop
        assert emu.vu1_reads == [], (label, emu.vu1_reads[:4])
        callers[label] = emu.r[31] & 0xFFFFFFFF   # the stop's return address
        if discover:
            print('DISCOVER ablation', label, stop)
            continue
        assert stop == ABLATION_STOPS[label], (label, stop)
        if label == 'object-factory':
            assert not [c for c in emu.calls if c.site == FACTORY_SITE]
            assert [c.site for c in emu.calls if c.target == LOAD_RECORDS] == [0x217B94]
        if label == 'g_levelName':
            assert lumps[-1][0] == b'.lmp', lumps[-3:]  # cutScene's "%s.lmp" at 0x143f58
            assert CUT_SCENE in {c.target for c in emu.calls}
            check('lmp-ra', lumps[-1][1], discover)
            # cutScene asks res_find for the lump at 0x143f7c.
            assert (RES_FIND, 0x143F7C) in {(c.target, c.site) for c in emu.calls}
    check('ablation-ra', callers, discover)
    return out


def arrival_load(full, seed, discover=False):
    """The innovat1 load to its return, with everything supplied."""
    emu = copy.deepcopy(full)
    emu.record_calls = True
    emu.reset_log()
    scripts = []
    emu.hook(RUN_SCRIPT, lambda m: scripts.append(cstr(m.mem, m.r[4])))
    stop = stop_of(emu, 60000000)
    assert stop[0] == 'return', stop
    calls = emu.calls
    records = [c for c in calls if c.target == LOAD_RECORDS]
    assert [c.site for c in records] == [0x217B94]
    built = [c for c in calls if c.site == FACTORY_SITE]
    assert built and all(c.target == FACTORY for c in built)
    assert PLAYER_CTOR not in {c.target for c in calls}
    assert len(built) == 297, len(built)
    assert emu.vu1_reads == [], emu.vu1_reads[:4]
    # preStart, start, then a third script (the level's post-action script, whose
    # name is level data and is not written here).
    assert scripts[:2] == [b'preStart', b'start'] and len(scripts) == 3, len(scripts)
    assert scripts[2] not in scripts[:2]
    return len(built), scripts


# ---- Track A: the menu ------------------------------------------------------------------

def menu_open(elf, disc, seed):
    """Round 5's portal use, with seeded synthetic prior destinations and the camera."""
    rng = random.Random('dests-%d' % seed)
    prior = ['zm%05x' % rng.randrange(1 << 20) for _ in range(rng.randrange(2, 9))]
    emu, _body, _dmas = r5.portal_ctor(elf, disc, seed)
    owner = player(emu, seed, vec(emu))
    emu.call(0x2071A8, CAMERA_OBJ, max_steps=2000000)
    emu.mem.w32(CAMERA, CAMERA_OBJ)
    emu.mem.write(LEVEL_NAME, LEVEL + b'\0')
    for index, name in enumerate(prior):
        emu.mem.write(DESTS + 0x20 * index, name.encode().ljust(0x20, b'\0'))
    emu.mem.w8(DEST_COUNT, len(prior))
    pad = press(emu)
    emu.mem.w32(TRAVEL, SENTINEL)
    emu.record_calls = True
    emu.reset_log()
    emu.call(INTERACT, owner, pad, 0, max_steps=300000000)
    menus = [c for c in emu.calls if c.target == GATE_MENU]
    assert len(menus) == 1 and [a & 0xFFFFFFFF for a in menus[0].args[:3]] == [0, 0, 0]
    names = [cstr(emu.mem, DESTS + 0x20 * i).decode() for i in range(emu.mem.u8(DEST_COUNT))]
    assert names == prior + [LEVEL.decode()], names
    assert emu.mem.u8(STATE) == 0 and emu.mem.u32(TRAVEL) == 0 and emu.mem.u32(FIXED) == 0
    emu.mem.write(PENDING, b'\0' * 0x20)
    emu.mem.w8(ORIENT, 0x5A)
    return emu, names


def frame(emu, pressed=0, second=0):
    emu.mem.w32(PADS + PRESSED, pressed)
    emu.mem.w32(PADS + SECOND, second)
    emu.reset_log()
    emu.call(MENU_RUN, 0, max_steps=20000000)
    emu.mem.w32(PADS + PRESSED, 0)
    emu.mem.w32(PADS + SECOND, 0)
    return emu.mem.u8(STATE)


def model_select(moves, count):
    selected = 0
    for move in moves:
        if move == 'up' and selected != 0:
            selected -= 1
        elif move == 'down' and selected < count - 1:
            selected += 1
    return selected


def menu_select(opened, seed):
    """Seeded up/down presses, a refused confirm on the current level, then travel."""
    emu = copy.deepcopy(opened[0])
    names = opened[1]
    count, current = len(names), len(names) - 1
    rng = random.Random('moves-%d' % seed)
    moves = [rng.choice(('up', 'down', 'down')) for _ in range(rng.randrange(4, 12))]
    frames = {}
    state = frame(emu)
    assert state == 1 and emu.mem.u8(CURRENT) == current and emu.mem.u8(SELECTED) == 0
    assert emu.mem.u32(PAUSE_WORD) == 1 and emu.mem.u8(PAUSE_BYTE) == 1    # offline pause
    frames[0] = 1
    while state == 1:
        frames[1] = frames.get(1, 0) + 1
        state = frame(emu)
    assert state == 2 and emu.mem.u32(FADE) == 0x7F and frames[1] == 16
    for move in moves:
        assert frame(emu, second=UP_BIT if move == 'up' else DOWN_BIT) == 2
    selected = model_select(moves, count)
    assert emu.mem.u8(SELECTED) == selected, (moves, emu.mem.u8(SELECTED), selected)
    refused = selected == current
    if refused:
        # Confirm on the current level is refused (0x27dfa0).
        assert frame(emu, pressed=CONFIRM_BIT) == 2 and emu.mem.u32(TRAVEL) == 0
        assert frame(emu, second=UP_BIT) == 2
        selected -= 1
        assert emu.mem.u8(SELECTED) == selected
    assert frame(emu, pressed=CONFIRM_BIT) == 3 and emu.mem.u32(TRAVEL) == 1   # 0x27e00c
    fade = 0
    state = 3
    while state == 3:
        fade += 1
        emu.record_calls = True
        state = frame(emu)
    assert state == 4 and fade == 8
    assert CLOSE_PAUSE in [c.target for c in emu.calls]
    assert emu.mem.u32(PAUSE_WORD) == 0 and emu.mem.u8(PAUSE_BYTE) == 0
    assert frame(emu) == 5 and BEGIN_TRAVEL in [c.target for c in emu.calls]
    # Every write to g_pendingLevel .. g_prevLevelName during state 5, with the
    # stretch of each frame's writes made inside the copy called at 0x27e1f8.
    emu.write_watch = (NEXT_WORLD,)
    emu.record_writes = True
    copy_marks = []
    emu.hook(STRCPY, lambda m: copy_marks.append(
        ((m.r[31] & 0xFFFFFFFF) - 8, len(m.writes))))
    emu.hook(COPY_SITE + 8, lambda m: copy_marks.append(('back', len(m.writes))))
    state5 = []
    counted = 0
    while emu.mem.u8(STATE) == 5:
        counted += 1
        copy_marks.clear()
        frame(emu)
        state5.append((list(emu.writes), list(copy_marks)))
    emu.unhook(STRCPY)
    emu.unhook(COPY_SITE + 8)
    emu.record_writes = False
    emu.write_watch = None
    assert counted == 181 and emu.mem.u32(TRAVEL) == 181
    assert all(not w and not marks for w, marks in state5[:-1]), 'state 5 wrote early'
    writes, marks = state5[-1]
    assert [m[0] for m in marks] == [COPY_SITE, 'back'], marks
    start, end = marks[0][1], marks[1][1]
    length = len(names[selected]) + 1
    copied = writes[start:end]
    covered = {a + i for _pc, a, size, _v in copied for i in range(size)}
    assert covered == set(range(PENDING, PENDING + length)), sorted(covered)
    assert all(pc != ORIENT_STORE for pc, *_r in copied)
    assert writes[:start] == [] and writes[end:] == [(ORIENT_STORE, ORIENT, 1, 0xFF)], writes
    assert cstr(emu.mem, PENDING).decode() == names[selected]
    assert emu.mem.u8(ORIENT) == 0xFF and emu.mem.u8(STATE) == 6
    assert frame(emu) == 7 and emu.mem.u32(TRAVEL) == 181
    removed = []
    emu.hook(TASK_REMOVE, lambda m: removed.append((m.r[4] & 0xFFFFFFFF, m.r[31] & 0xFFFFFFFF)))
    frame(emu)
    assert emu.mem.u32(TRAVEL) == 0
    assert removed == [(MENU_RUN, 0x27E2A0), (MENU_DRAW, 0x27E2AC)], removed
    return emu, len(moves), selected, refused


def menu_cancel(opened):
    emu = copy.deepcopy(opened[0])
    pending = b'zcancel'.ljust(0x20, b'\0')
    emu.mem.write(PENDING, pending)                  # nonzero sentinel
    emu.write_watch = (NEXT_WORLD,)
    emu.record_writes = True
    block = []
    while True:
        state = frame(emu)
        block += emu.writes
        if state == 2:
            break
    assert frame(emu, pressed=CANCEL_BIT) == 3 and emu.mem.u32(TRAVEL) == 0
    block += emu.writes
    removed, locks = [], []
    emu.hook(TASK_REMOVE, lambda m: removed.append(m.r[4] & 0xFFFFFFFF))
    emu.hook(LOCK_INPUT, lambda m: locks.append((m.r[4] & 0xFF, m.r[5] & 0xFFFFFFFF)))
    for _ in range(8):
        assert frame(emu) == 3
        block += emu.writes
    assert removed == [MENU_RUN, MENU_DRAW] and locks == [(0, 5)], (removed, locks)
    assert emu.mem.read(PENDING, 0x20) == pending and emu.mem.u8(ORIENT) == 0x5A
    assert block == [], block[:4]                    # nothing written for a next world
    return len(removed)


def destinations_round_trip(emu, names):
    """jumpgate_saveDestinations and jumpgate_loadDestinations on the menu's own list."""
    block = emu.alloc(DEST_BLOCK + 0x20, fill=0xC3)
    before = emu.mem.read(DESTS, 0x1E0)
    assert emu.call(SAVE_DESTS, block, max_steps=100000) & 0xFFFFFFFF == DEST_BLOCK
    assert emu.mem.u32(block) == len(names)
    assert emu.mem.read(block + 4, 0x1E0) == before
    assert emu.mem.read(block + DEST_BLOCK, 4) == b'\xc3' * 4
    emu.mem.write(DESTS, b'\x5a' * 0x1E0)
    emu.mem.w8(DEST_COUNT, 0)
    assert emu.call(LOAD_DESTS, block, max_steps=100000) & 0xFFFFFFFF == DEST_BLOCK
    assert emu.mem.u8(DEST_COUNT) == len(names)
    assert emu.mem.read(DESTS, 0x1E0) == before
    return DEST_BLOCK


# ---- Track A + B: portal to arrival -------------------------------------------------------

def arrival_chain(elf, disc, seed, discover=False):
    emu = boot6(elf, disc)
    supply_engine_state(emu)
    for label, apply in HARDWARE:
        if label != 'high-heap':
            apply(emu)
    emu.mem.w32(SEED, seed)
    body = new(emu, 0x164)
    assert emu.call(PORTAL, body, vec(emu), 0, props(emu, []), max_steps=30000000) == 0
    owner = player(emu, seed, vec(emu))
    emu.mem.write(LEVEL_NAME, LEVEL + b'\0')
    emu.mem.write(TEX_NAME, LEVEL + b'\0')
    emu.mem.write(DESTS, b'hub'.ljust(0x20, b'\0'))
    emu.mem.w8(DEST_COUNT, 1)
    pad = press(emu)
    emu.call(INTERACT, owner, pad, 0, max_steps=300000000)
    assert emu.mem.u8(DEST_COUNT) == 2
    while emu.mem.u8(STATE) != 2:
        frame(emu)
    frame(emu, pressed=CONFIRM_BIT)                  # index 0, the first destination
    while emu.mem.u8(STATE) != 6:
        frame(emu)
    assert cstr(emu.mem, PENDING) == b'hub' and emu.mem.u32(TRAVEL) == 181
    # The main loop takes the request at the top of the next pass, before the
    # tasks run (docs/mainloop.md section 7), so the load sees state 6.
    emu.stub(CLEAR, ret=0, name='clear')
    _high_heap(emu)
    # Sentinels where the request and the gate are asserted to store.  The subname
    # gets none: save_storeLevelState stores the qualified name, which joins it, so
    # a sentinel there would change the stored name.  Its store is in the record.
    emu.mem.w8(SAVED_ORIENT, 0x5A)
    emu.mem.write(PREV_LEVEL, b'zprev\0')
    emu.mem.w8(RANK, 0x5A)
    emu.write_watch = ((SPAWN, 12), (FACING, 2), (TRAVEL, 4), (SAVED_ORIENT, 1),
                       (SUB_NAME, 1), (PREV_LEVEL, 1), (ORIENT, 1), (RANK, 1))
    emu.record_writes = True
    emu.record_calls = True
    emu.reset_log()
    seen = {'store': [], 'load': [], 'gate': [], 'player': []}
    emu.hook(STORE_LEVEL, lambda m: seen['store'].append(cstr(m.mem, m.r[4])))
    emu.hook(LOAD, lambda m: seen['load'].append((cstr(m.mem, m.r[4]), m.r[31] & 0xFFFFFFFF)))
    emu.hook(PORTAL, lambda m: seen['gate'].append(m.mem.u32(TRAVEL)))

    def at_player(m):
        pos = m.r[5] & 0xFFFFFFFF
        seen['player'].append((m.mem.read(pos, 12), m.r[6] & 0xFFFFFFFF, m.r[7] & 0xFFFFFFFF))
    emu.hook(PLAYER_CTOR, at_player)
    disc.reads.clear()
    assert emu.call(REQUEST, max_steps=200000000) & 0xFFFFFFFF == 0
    calls = emu.calls
    assert seen['store'] == [LEVEL] and seen['load'] == [(b'hub', 0x321150)], seen
    assert cstr(emu.mem, LEVEL_NAME) == b'hub' and cstr(emu.mem, SUB_NAME) == b''
    assert cstr(emu.mem, PREV_LEVEL) == LEVEL and cstr(emu.mem, PENDING) == b''
    assert emu.mem.u8(SAVED_ORIENT) == 0xFF and emu.mem.u8(ORIENT) == 0xFE
    built = [c for c in calls if c.site == FACTORY_SITE]
    assert len(built) == 24 and all(c.target == FACTORY for c in built)
    assert seen['gate'] == [181], seen['gate']
    spawn = [w for w in emu.writes if SPAWN <= w[1] < SPAWN + 12]
    assert [w[0] for w in spawn] == [0x27CA44, 0x27CA50, 0x27CA5C, 0x321234], spawn
    facing = [w for w in emu.writes if w[1] == FACING]
    assert [(w[0], w[2]) for w in facing] == [(0x27CA70, 2)], facing   # g_randSeed >> 16
    assert emu.mem.u8(RANK) == 3                     # 0x27ca84: skips the free-spot search
    check('rank-writes', [(w[0], w[3]) for w in emu.writes if w[1] == RANK], discover)
    check('request-writes', [(w[0], w[1], w[3]) for w in emu.writes
                             if w[1] in (SAVED_ORIENT, SUB_NAME, PREV_LEVEL, ORIENT)], discover)
    assert emu.vu1_reads == [], emu.vu1_reads[:4]
    assert len(seen['player']) == 1
    position, heading, slot = seen['player'][0]
    assert position == emu.mem.read(SPAWN, 12) and slot == 0
    assert heading == (emu.mem.load(FACING, 2) | (0xFFFF0000 if emu.mem.load(FACING, 2) & 0x8000 else 0))
    assert emu.mem.u32(TRAVEL) == 181 and emu.mem.u8(STATE) == 6
    assert frame(emu) == 7 and emu.mem.u32(TRAVEL) == 181
    frame(emu)
    assert emu.mem.u32(TRAVEL) == 0
    x, y, z = struct.unpack('<3f', position)
    return {'built': len(built), 'reads': len(disc.reads), 'facing_writes': len(facing),
            'spawn': (x, y, z), 'heading': heading}


def armor_probe(elf, disc, seed):
    """player_recalcArmor on the round-5 player, without and with the constructors."""
    out = []
    for constructors in (False, True):
        emu = boot6(elf, disc) if constructors else r5.boot(elf, disc)
        player(emu, seed, vec(emu))
        emu.record_calls = True
        emu.reset_log()
        emu.r[4] = 0
        emu.r[31] = EE.RETURN_ADDR
        emu.jump(ARMOR)
        stop = stop_of(emu, 20000000)
        fraction = [c for c in emu.calls if c.target == SKILL_FRACTION]
        out.append((stop, [c.args[0] & 0xFFFFFFFF for c in fraction][:1]))
    # Skill 63's vtable word is 0 before the constructors run: its first slot read faults.
    assert out[0] == (('fault', 0x308A98, 0x70, 2, 'read'), [SKILL63]), out[0]
    assert out[1][0][0] == 'return', out[1]
    return out


def results(elf, disc, seed, discover=False):
    """Every asserted round-6 result for one disc numbering, as plain values."""
    opened = menu_open(elf, disc, seed)
    picked, moves, selected, refused = menu_select(opened, seed)
    cancel = menu_cancel(opened)
    block = destinations_round_trip(picked, opened[1])
    snapshot, reads = loader_snapshot(elf, disc, seed)
    out = {'menu': (len(opened[1]), moves, selected, refused, cancel, block),
           'snapshot': (list(snapshot.sif_dma), reads)}
    out['stops'] = loader_chain(snapshot, disc, discover)
    full = copy.deepcopy(snapshot)
    del snapshot
    install_hardware(full)
    out['ablations'] = ablations(full, discover)
    if discover:
        return out
    out['innovat1'] = arrival_load(full, seed, discover)
    del full
    out['arrival'] = arrival_chain(elf, disc, seed, discover)
    out['armor'] = armor_probe(elf, disc, seed)
    return out


# The second numbering: a different base, descending, three sectors apart.
SECTORS = ((0x1000, 1), (0x7F000, -3))


def run(elf, root, seed, discover=False):
    assert hashlib.sha256(Path(elf).read_bytes()).hexdigest() == SHA256
    disc = Disc6(root, *SECTORS[0])
    got = results(elf, disc, seed, discover)
    if discover:
        return
    count, moves, selected, refused, cancel, block = got['menu']
    print('PASS seed=%d menu destinations=%d moves=%d selected=%d refused-current=%d fade-in=16 '
          'fade-out=8 travel-frames=181 orientation=0xff cancel-removed=%d save-block=0x%x' % (
              seed, count, moves, selected, refused, cancel, block))
    print('PASS seed=%d menu state 5 writes only the copy from 0x%x and 0x%x; cancel writes '
          'nothing to 0x%x..0x%x' % (seed, COPY_SITE, ORIENT_STORE, NEXT_WORLD[0],
                                     NEXT_WORLD[0] + NEXT_WORLD[1]))
    print('PASS seed=%d loader stops %s' % (seed, ' '.join(
        '0x%08x' % s[1] if s[0] in ('fault', 'unimplemented') else s[0] for s in got['stops'])))
    print('PASS seed=%d loader ablations %s' % (seed, ' '.join(
        '%s:%s' % (k, '0x%08x' % v[1] if v[0] == 'fault' else v[0])
        for k, v in got['ablations'].items())))
    print('PASS seed=%d no load from VU1 data memory in the chain, ablations and arrivals' % seed)
    built, scripts = got['innovat1']
    print('PASS seed=%d innovat1 load returns, objects=%d scripts=%d' % (seed, built, len(scripts)))
    arrival = got['arrival']
    print('PASS seed=%d portal to hub: objects=%d reads=%d gate spawn=(%.2f, %.2f, %.2f) '
          'heading=0x%08x Player_ctor slot 0' % (
              seed, arrival['built'], arrival['reads'], *arrival['spawn'], arrival['heading']))
    print('PASS seed=%d without constructors player_recalcArmor faults at 0x308a98 (skill 63 '
          'vtable 0); with them it returns' % seed)
    sites = sorted(set(disc.find_sites))
    check('find-sites', sites, discover)
    # The same runs under a second synthetic sector numbering give the same results.
    other = Disc6(root, *SECTORS[1])
    again = results(elf, other, seed)
    assert again == got, [k for k in got if got[k] != again.get(k)]
    assert sorted(set(other.find_sites)) == sites and len(other.find_sites) == len(disc.find_sites)
    print('PASS seed=%d sectors 0x%x+%d*i and 0x%x%d*i give equal results; cd_findFile calls=%d '
          'from %s' % (seed, SECTORS[0][0], SECTORS[0][1], SECTORS[1][0], SECTORS[1][1],
                       len(disc.find_sites), ','.join('0x%x' % x for x in sites)))
    print('SUPPLIED %s' % ','.join(SUPPLIED))
    print('OPT-INS %s' % ','.join(OPT_INS))
    print('STUBS %s' % ','.join(FIXTURE_STUBS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('disc')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--discover', action='store_true')
    args = parser.parse_args()
    run(args.elf, args.disc, args.seed, args.discover)


if __name__ == '__main__':
    main()
