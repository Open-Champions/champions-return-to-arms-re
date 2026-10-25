#!/usr/bin/env python3
"""Probe original mode-B recipe-0 wave builders with one offline player.

The wave plan, ring placement, arena_spawnMonster, world_createObject, class
factory, and stat scaling execute in ee_emu. The class constructors are
authored fixtures because their full object/resource fixture is separate.
The fighting variant executes class attacks and Player damage processing on
authored positions and fixed service answers. With --real-player the old player's
destructor, pool reuse, the whole Player constructor chain, original placement and
Player_run run for real (docs/spec/arena-player.md). This is not a live match; no
game bytes are saved.
"""
import argparse
from collections import Counter

import gob
import difftest_arena_creature_chain as DCH
import difftest_arena_modes as D
import difftest_player as DP
import ref_arena_creature_chain as CH
import ref_arena_match_core as MC
import ref_arena_player as RA
import ref_monster_build as B
import ref_player as RP
import ref_world as RW
from ref_core import ZERO
from recomp import disc as Disc


ARENA = 'pvparena'                          # the first mode-B map's level name
WORLD_CREATE = 0x14F6C8
OBJECT_FACTORY = 0x159C94
FACTORY_POINTER = 0x5F76F4
POOL_NEW = 0x14FDB8
SCALE = 0x1185D8
ADD_SPELL = 0x11A838
VTABLES = {0: 0x50FE88, 1: 0x516E48, 3: 0x510260,
           4: 0x50FFD0, 25: 0x510F30}
CONSTRUCTORS = {0: 0x2A4D68, 1: 0x298418, 3: 0x26A624,
                4: 0x2A0954, 25: 0x244018}
SIZES = {0: 0x3D0, 1: 0x480, 3: 0x498, 4: 0x488, 25: 0x3D0}
DEFINITIONS = {0: 0x502238, 1: 0x501838, 3: 0x500298}
HOLDERS = {1: (0x3D0, 0x50CF40), 3: (0x3E8, 0x50CDA0)}
SET_STATES = {0: 0x2A55EC, 1: 0x29A6F4, 3: 0x26CCFC}
RUN_STATES = {0: 0x2A5068, 1: 0x298D18, 3: 0x26B27C}
PICK_TARGET = 0x10DED0
TAKE_DAMAGE = 0x116638
PROCESS_DAMAGE = 0x110D30
PLAYER_TAKE_DAMAGE = 0x1B5330
PLAYER_PROCESS_DAMAGE = 0x1B2CC0
PLAYER_RUN = 0x1A5030
LIB = CH.LIBRARY            # C library and software float (through libc_mbtowc_r)
HANDLE_INIT_POOL, HANDLE_LINK, HANDLE_CLEAR, HANDLE_REMOVE = 0x1A17D0, 0x1A1738, 0x1A1698, 0x1A1868
HOME_RANGE_SLOT = 0x3C2708  # vtable slot 34 of these classes (arena-monsters.md 2.3)


class Follow(set):
    """A follow set that also runs the C library and software float range, as
    difftest_player does; arena_pickSpawnPoint needs it (arena-player.md section 3)."""

    def __contains__(self, target):
        return set.__contains__(self, target) or LIB[0] <= target < LIB[1]


def install_real_player(emu):
    """Run the slot loop's replacement for real: the old player's slot-1 destructor,
    pool_free / pool_new reuse of the same block, Player_ctor -> Creature_ctor ->
    GameObject_ctor, game_resetTimers4f84a8 and arena_pickSpawnPoint. Resource lookups
    answer with one authored part; the destructor's and constructor's other callees are
    recording stubs. Each replacement appends (block, seed before the constructor) to
    emu.replacements."""
    emu.follow = Follow(emu.follow)
    emu.follow.update({RA.PICK_SPAWN, RA.PLAYER_DTOR, RA.CTOR, RA.CREATURE_CTOR,
                       RA.GAMEOBJECT_CTOR, RA.RESET_TIMERS, 0x166798})
    part = emu.alloc(0x200)
    emu.player_part = part
    emu.stub(RA.RES_FIND, ret=part)
    emu.mem.write(D.PLAYERS + 0x20, b'\xff' * 4)
    emu.freed = []

    def pool_free(e):
        e.freed.append(e.r[4] & 0xFFFFFFFF)

    emu.stub(RA.POOL_FREE, function=pool_free)
    for slot in range(4):
        emu.mem.w32(RP.G_BTN_ATTACK + 4 * slot, DP.BTN['attack'])   # authored pad binding


def lcg_steps(before, after, limit=64):
    """How many documented shared draws turn ``before`` into ``after``."""
    for steps in range(limit + 1):
        if before == after:
            return steps
        before = RA.lcg(before)[0]
    raise AssertionError('seed moved by more than %d draws' % limit)


PICK_ATTACK_ANIM = 0x1BBA88


def install_player_tick(emu):
    """Player_run, the helpers its executed model covers, and Player_pickAttackAnim (one
    shared draw per combo swing, player-tick.md 9.10 and 10) run for real. Player_move
    stays a recording stub: its only shared draw is on entering water
    (combat-movement.md 3), which this dry fixture never answers."""
    emu.follow.update(set(DP.REAL_HELPERS.values()) | DP.REAL_OTHER | {PLAYER_RUN, PICK_ATTACK_ANIM})


def seed_ledger(emu, start):
    """Every store to the shared seed since ``start``, in order, as (function entry, pc,
    draws): the function holding the storing pc (ghidra_funcs.tsv) and the number of
    documented generator steps the store advanced the seed by."""
    import bisect
    import probe_full_placement as PF
    starts = getattr(seed_ledger, 'starts', None) or PF.function_starts()
    seed_ledger.starts = starts
    out, before = [], start
    for pc, address, _size, value in emu.writes:
        if address != B.G_RAND_SEED:
            continue
        entry = starts[bisect.bisect_right(starts, pc) - 1]
        out.append((entry, pc, lcg_steps(before, value, limit=4000)))
        before = value
    return out


class ConstructorBoundary(Exception):
    def __init__(self, index):
        super().__init__('class-table index %s at world_createObject' % index)
        self.index = index


def disc_file(iso, name):
    entry = iso.find(name)
    if entry is None:
        raise ValueError('%s absent from disc' % name)
    iso.f.seek(entry['lba'] * Disc.SECTOR)
    return iso.f.read(entry['size'])


def recipe0_world_from_disc(path):
    """Read the first mode-B map's .world at run time; keep no extracted game bytes."""
    iso = Disc.Iso(path)
    try:
        archive = disc_file(iso, 'BG/DATA/' + ARENA.upper() + '.GOB')
        lump = next((archive[off:off + size] for name, off, size in gob.gob_entries(archive)
                     if name.lower() == ARENA + '.lmp'), None)
        if lump is None:
            raise ValueError('the arena lump is absent from its archive')
        world = next((lump[off:off + size] for name, off, size in gob.lmp_entries(lump)
                      if name.lower() == ARENA + '.world'), None)
        if world is None:
            raise ValueError('the arena .world is absent from its lump')
        return world
    finally:
        iso.f.close()


def recipe0_clips_from_disc(path):
    """Read all recipe-0 actor clips at run time, without writing them to the tree."""
    iso = Disc.Iso(path)
    clips = {}
    try:
        for actor in ('RAGNAR2', 'GOBLIN', 'GOBLIN_Z', 'MUMMY', 'SCORPION'):
            lump = disc_file(iso, 'BG/DATA/%s.LMP' % actor)
            for name, off, size in gob.lmp_entries(lump):
                if name.lower().endswith('.anm'):
                    clips[(actor.lower() + '.lmp', name.lower())] = lump[off:off + size]
    finally:
        iso.f.close()
    return clips


def recipe0_models_from_disc(path):
    """Read recipe-0 model entries from the owner's disc, without extracting files."""
    iso = Disc.Iso(path)
    models = {}
    try:
        for actor in ('GOBLIN', 'GOBLIN_Z', 'MUMMY', 'SCORPION', 'EQUIPMNT', 'FX',
                      'SELECT', 'SELECT2'):
            lump = disc_file(iso, 'BG/DATA/%s.LMP' % actor)
            for name, off, size in gob.lmp_entries(lump):
                if name.lower().endswith('.vif'):
                    models[(actor.lower() + '.lmp', name.lower())] = lump[off:off + size]
    finally:
        iso.f.close()
    return models


def install_disc_animation(emu, clips):
    """Original animation pool and clip relocation; clips exist only in probe memory."""
    import probe_full_placement as PF
    emu.call(0x16F9A8, max_steps=200_000_000)
    addresses = {}
    for key, blob in clips.items():
        pointer = emu.alloc(len(blob) + 0x40, align=0x40)
        emu.mem.write(pointer, blob)
        emu.call(0x1707B8, pointer, max_steps=1_000_000)
        addresses[key] = pointer
    emu.clip_addresses = addresses


def follow_disc_animation(emu):
    import probe_full_placement as PF
    names = PF.symbol_names()
    emu.follow.update({address for address, name in names.items()
                       if name.startswith('anim_') or name.startswith('anm_')})
    emu.follow.add(0x1162B0)  # Creature_stepAnim


def install_disc_terrain(emu, data):
    """Run world_fixup on the disc's pvparena.world and retain its independent model."""
    # world_fixup's presentation/I/O edges are the same bounded stubs as difftest_world.Rig.
    for address in (0x3B7EF0, 0x14A4F0, 0x195318, 0x18F118, 0x179E10, 0x168894):
        emu.stub(address, ret=0)
    emu.stub(0x172AD0, function=lambda e: e.mem.write(e.r[5] & 0xFFFFFFFF, bytes(0x40)) or 0)
    base = emu.alloc(len(data) + 0x40, align=0x40)
    emu.mem.write(base, data)
    emu.call(0x181D30, base, max_steps=200_000_000)
    emu.mem.w32(0x44FDC8, base)
    emu.world_model = RW.Level(data)


def setup(path, wave, seed, real_creatures=False, world_data=None, clips=None):
    emu = D.boot(path)
    emu.elf_path = path
    if real_creatures:
        # boot-time state the real constructors read: the 101 Skill objects (built first,
        # they move the seed), the handle node pool, and arena_init's property list
        DCH.build_skills(emu)
        emu.call(HANDLE_INIT_POOL)
        DCH.arena_props(emu)
        emu.record_calls = True
    D.modes(emu, mode_a=0, mode_b=1, network=0, seed=seed, players=1)
    player = emu.alloc(0x590)
    emu.mem.w32(player + 0xC, 0x40)
    emu.mem.w32(player + 0x3C8, 0)
    emu.mem.w32(player + 0x58C, 2)
    emu.mem.w32(player + 0x48, 0x511308)  # Player's already documented vtable
    D.bind_player(emu, 0, player)
    emu.arena_player = player
    D.put_slot(emu, 0, 0, 2, 2, 0x40000000)
    emu.mem.w32(D.PLAYERS + 0xAC, 0x41A00000)
    D.put_points(emu, [(ZERO, ZERO, ZERO, 0)])
    emu.mem.w16(D.WAVE, (wave - 1) & 0xFFFF)
    emu.mem.w16(D.LEFT, 3)
    emu.mem.w16(D.SAVED, 0)
    emu.default_ret = 0
    emu.stub(D.NET_COUNT, ret=1)
    emu.stub(D.ACTIVE, ret=1)
    if world_data is not None:
        install_disc_terrain(emu, world_data)
    if clips is not None:
        install_disc_animation(emu, clips)
    return emu


def class_index(mem, pointer):
    for index in range(30):
        if mem.u32(D.CLASSES + 4 * index) == pointer:
            return index
    raise ValueError('spawned class pointer was not in the 30-entry table')


def dry_wave(path, wave, seed):
    emu = setup(path, wave, seed)
    emu.follow = {D.STEP}
    emu.stub(D.SPAWN, ret=0)
    emu.call(D.START, 1)
    indices = [class_index(emu.mem, call.args[0] & 0xFFFFFFFF)
               for call in D.calls(emu, D.SPAWN)]
    assert emu.mem.u16(D.WAVE) == wave
    return indices


def first_constructor_boundary(path, seed):
    emu = setup(path, 0, seed)
    emu.follow = {D.STEP, D.SPAWN, 0x166630, 0x1666E0, 0x3B75D0}

    def find_spot(e):
        out, point, _range, _radius, ok = [e.r[k] & 0xFFFFFFFF for k in range(4, 9)]
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def create(e):
        raise ConstructorBoundary(class_index(e.mem, e.r[4] & 0xFFFFFFFF))

    emu.stub(0x14ACF8, function=find_spot)
    emu.stub(WORLD_CREATE, function=create)
    try:
        emu.call(D.START, 1)
    except ConstructorBoundary as boundary:
        return boundary.index, len(D.calls(emu, D.SPAWN))
    raise AssertionError('first spawn did not reach world_createObject')


def install_factory_fixture(emu, real=False, disc_models=None):
    """Follow original world_createObject/factory with constructor fixtures.

    The constructor fixture retains the original class vtable and gives scaling
    authored HP, damage, armour and experience values. Slot 34 and slot 27, which
    need class resources, are recording stubs. The factory row is also compared
    independently by difftest_monster_build.py for all 30 arena names.
    """
    created = []
    spells = []
    pending = {'index': None, 'block': None}
    emu.creature_part = emu.alloc(0x400)

    def find_spot(e):
        out, point, _range, _radius, ok = [e.r[k] & 0xFFFFFFFF for k in range(4, 9)]
        for j in range(3):
            e.mem.w32(out + 4 * j, e.mem.u32(point + 4 * j))
        e.mem.w8(ok, 1)
        return 0

    def entering_world_create(e):
        pending['index'] = class_index(e.mem, e.r[4] & 0xFFFFFFFF)

    def pool_new(e):
        size = e.r[4] & 0xFFFFFFFF
        if size == 0x590 and e._fresh_call.site == 0x306030:
            if not getattr(e, 'freed', None):
                return 0  # without --real-player the replacement stays outside the fixture
            block = e.freed.pop()
            e.mem.write(block, bytes(0x590))       # pool_new zero-fills (object-system.md 2.1)
            e.arena_player = block
            e.replacements.append([block, e.mem.u32(RA.SEED)])
            return block
        if size == B.SPELL_SIZE and pending['index'] is None:
            if getattr(e, 'spell_block_check', None):
                e.spell_block_check(e)
            block = e.alloc(size)
            spells.append((block, e.mem.u32(B.G_RAND_SEED)))
            return block
        if real and size == GUT_CHUNK_SIZE and (PROCESS_DAMAGE <= e._fresh_call.site < PROCESS_DAMAGE_END or
                                                0x2A59F0 <= e._fresh_call.site < SEVER_PART_END):
            block = e.alloc(size)       # a gib chunk (creature-tick.md 3.4; gut-chunk.md)
            e.chunks.append(block)
            return block
        if real and size in LOOT_POOL and any(lo <= e._fresh_call.site < hi for lo, hi in LOOT_SPANS):
            block = e.alloc(size)       # loot_spawnGold / loot_generateDrops objects
            e.loot.append((size, block))
            return block
        if real and size == CH.ONIBALL_SIZE and e._fresh_call.site == CH.ONIBALL_SITE:
            block = e.alloc(size)       # the Life Tap orb of a kill (creature-tick.md 4 step 9)
            e.orbs.append(block)
            return block
        if real and pending['index'] is None and (e._fresh_call.site, size) in OTHER_POOL:
            block = e.alloc(size)       # traced dropped part prop, still not ticked
            e.other_blocks.append((e._fresh_call.site, size, block))
            return block
        if pending['index'] is None:
            raise ValueError('unexpected pool_new size 0x%x at 0x%x outside factory' %
                             (size, e._fresh_call.site))
        assert size == SIZES[pending['index']], (pending['index'], size)
        pending['block'] = e.alloc(size)
        if real:
            # the original constructor builds the object in this zero-filled block
            assert 0x159C94 <= e._fresh_call.site < 0x15D9C8, hex(e._fresh_call.site)   # the factory body
            created.append((pending['index'], pending['block']))
            pending['index'] = None
        return pending['block']

    def construct(e):
        index = pending['index']
        if index not in VTABLES:
            raise ValueError('no fixture for class-table index %d' % index)
        assert e._fresh_call.target == CONSTRUCTORS[index], index
        obj = e.r[4] & 0xFFFFFFFF
        assert obj == pending['block']
        e.mem.w32(obj + 0x48, VTABLES[index])
        if index in DEFINITIONS:
            e.mem.w32(obj + 0x24, DEFINITIONS[index])
        if index in HOLDERS:
            offset, table = HOLDERS[index]
            e.mem.w32(obj + 0x50, obj + offset)
            e.mem.w32(obj + offset, table)
        e.mem.w32(obj + 0xC, 0x20)
        e.mem.w16(obj + 0x312, 0)
        for field, value in ((0x228, 0x42C80000), (0x22C, 0x42C80000),
                             (0xD8, 0x41200000)):
            e.mem.w32(obj + field, value)
        for field, value in ((0xD0, 10), (0xD2, 20), (0xD4, 30), (0xE4, 40)):
            e.mem.w16(obj + field, value)
        for j in range(3):
            e.mem.w32(obj + 0x10 + 4 * j, e.mem.u32((e.r[5] & 0xFFFFFFFF) + 4 * j))
        e.mem.w16(obj + 0x38, e.r[6] & 0xFFFF)
        created.append((index, obj))
        pending['index'] = None
        pending['block'] = None
        return obj

    emu.mem.w32(FACTORY_POINTER, OBJECT_FACTORY)
    emu.follow.update({WORLD_CREATE, OBJECT_FACTORY, 0x159C20, 0x3B81A0})
    emu.stub(0x14ACF8, function=find_spot)
    emu.hook(WORLD_CREATE, entering_world_create)
    emu.stub(POOL_NEW, function=pool_new)
    if real:
        return install_real_creatures(emu, created, spells, disc_models)
    for constructor in CONSTRUCTORS.values():
        emu.stub(constructor, function=construct)
    def add_spell(e):
        creature, spell = (e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)
        assert spells and spell == spells[-1][0], (creature, spell, spells)
        block, old_seed = spells[-1]
        new_seed = (old_seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        assert e.mem.u32(B.G_RAND_SEED) == new_seed
        assert all(e.mem.u32(block + offset) == 0 for offset in (0, 4, 8))
        assert e.mem.u32(block + 0xC) == creature
        assert e.mem.u32(block + 0x10) == new_seed >> 16
        assert e.mem.u32(block + 0x14) == B.VT_SPELL_ARENA
        return 0

    emu.stub(ADD_SPELL, function=add_spell)
    for table in VTABLES.values():
        for slot in (27, 34):
            emu.stub(emu.mem.u32(table + 8 * slot + 4), ret=0)
    return created


MODEL_BOUNDS_Z = (0, 100)    # authored answer of the model_getBounds service (Creature_init)


def check_spell_record(e, spells, creature, spell):
    """The SpellArena record arena_spawnMonster built (docs/script-items.md 5.2 step 5)."""
    assert spells and spell == spells[-1][0], (creature, spell, spells)
    block, old_seed = spells[-1]
    new_seed = (old_seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    assert e.mem.u32(B.G_RAND_SEED) == new_seed
    assert all(e.mem.u32(block + offset) == 0 for offset in (0, 4, 8))
    assert e.mem.u32(block + 0xC) == creature
    assert e.mem.u32(block + 0x10) == new_seed >> 16
    assert e.mem.u32(block + 0x14) == B.VT_SPELL_ARENA


FREE_SPOT, TERRAIN_BLOCKED, TERRAIN_HEIGHT, BOX_QUERY = 0x14ACF8, 0x183B48, 0x183820, 0x14A928
PROCESS_DAMAGE_END = 0x1124DC          # Creature_processDamage's body ends (ghidra_funcs.tsv)
GUT_CHUNK_SIZE = 0x268
SEVER_PART_END = 0x2A5AF4   # Scorpion_severPart body end (ghidra_funcs.tsv)
# GutChunk_ctor, PhProp_ctor, Prop_ctorNamedLaunch, Prop_launch, PhProp_initPhysics: executed
# with tools/ref_phprop.py (docs/spec/gut-chunk.md), one shared draw per chunk
GUT_CHUNK_CHAIN = {0x201958, 0x155A0C, 0x153E54, 0x1541A0, 0x155110}


def install_real_free_spot(emu):
    """world_findFreeSpot 0x14acf8 runs for real (docs/spec/arena-creature-chain.md): its
    unit-ball sampling makes three shared draws per sample. With disc terrain,
    original terrain_testFlag1 and terrain_height execute; otherwise they answer
    authored flat ground. The box query runs over the real object grid."""
    emu.unhook(FREE_SPOT)
    emu.follow.update({FREE_SPOT, BOX_QUERY})
    emu.free_spot_calls = []

    def flat(e):
        e.f[0] = 0
        return 0
    if hasattr(emu, 'world_model'):
        # terrain_collectElements is a callee of both original terrain queries.
        emu.follow.update({TERRAIN_BLOCKED, TERRAIN_HEIGHT, 0x183248})
    else:
        emu.stub(TERRAIN_BLOCKED, function=flat)
        emu.stub(TERRAIN_HEIGHT, function=flat)

    def entering(e):
        center = tuple(e.mem.u32((e.r[5] & 0xFFFFFFFF) + 4 * k) for k in range(3))
        e.free_spot_calls.append(dict(seed=e.mem.u32(B.G_RAND_SEED), center=center,
                                      range=e.r[6] & 0xFFFFFFFF, radius=e.r[7] & 0xFFFFFFFF,
                                      ok_ptr=e.r[8] & 0xFFFFFFFF, any=e.r[9] & 0xFFFFFFFF, boxes=[]))

    def box_answer(e):              # 0x14b038: the box query has filled the list at sp + 0x80
        out, listed = e.r[29] + 0x80, []
        while e.mem.u32(out + 4 * len(listed)):
            obj = e.mem.u32(out + 4 * len(listed))
            listed.append((e.mem.u32(obj + 0x10), e.mem.u32(obj + 0x14), e.mem.u32(obj + 0x1C),
                           e.mem.u32(obj + 0xC)))
        e.free_spot_calls[-1]['boxes'].append(listed)

    def leaving(e):                 # 0x14b100: ok stored, the spot still at sp + 0x10
        call = e.free_spot_calls[-1]
        answers = iter(call['boxes'])
        if hasattr(e, 'world_model'):
            radius = RW.i2f(RW.s32(call['radius']))
            blocked = lambda point: RW.terrain_test_flag1(e.world_model, radius, point)
            height = lambda point: RW.terrain_height(e.world_model, radius, point)
        else:
            blocked = height = lambda point: 0
        want = CH.free_spot(call['seed'], call['center'], call['range'], call['radius'], call['any'],
                            blocked, height, lambda lo, hi: next(answers))
        got_spot = tuple(e.mem.u32(e.r[29] + 0x10 + 4 * k) for k in range(3))
        assert e.mem.u32(B.G_RAND_SEED) == want[0], ('free spot seed', call)
        assert got_spot == want[1], ('free spot', got_spot, want[1])
        assert not call['ok_ptr'] or e.mem.u8(call['ok_ptr']) == want[2]
        call.update(draws=want[4], tries=want[3], ok=want[2])
    emu.hook(FREE_SPOT, entering)
    emu.hook(0x14B038, box_answer)
    emu.hook(0x14B100, leaving)


# Decision-making callees on the fighting path that have executed contracts (each named
# in symbols/ with its spec): every type-info getter (rtti answers inside damage_apply and
# the spell searches), player_getSkillRank and the Life Tap fraction (the orb roll of a
# kill), Creature_onDeath (slot 28) with obj_delete, arena_addKill and the boss music stop.
DEATH_PATH = {0x1BF330, 0x2F8E78, 0x10BEB8, 0x14F200, 0x3056CC, 0x1192F8,
              CH.GOBLIN_ON_NEARBY, CH.GOBLIN_HAS_SHIELD}   # Goblin slot 12 on a kill (new, round 6)
# The loot chain (docs/issues/kill-loot-xp.md; loot_generateDrops executed in
# tools/difftest_items.py, Creature_dropLoot in tools/difftest_combat_monsters.py,
# loot_spawnGold and Gold_ctor2 in tools/difftest_phprop.py).
LOOT_PATH = {0x10F2C8, 0x100D54, 0x100974, 0x157668,
             0x3C85FC, 0x3C88DC,             # Skill_default_slot10 / slot14 (ref_skills_a)
             0x1EBF20, 0x1EBF70,             # the monster-level factors the generators read
             0x104CA4, 0x10DBE0,             # item_generateWithAffixes, creature_bossMusicName
             0x104C04, 0x104C48, 0x1083F8, 0x108590,   # item_classifyCategory0/1, item_getResourceIndex,
                                                       # item_generateConsumable (ref_items)
             0x2A59F0}                       # Scorpion_severPart (ref_monsters_1): a gib chunk
LOOT_POOL = {0xC0: 'gold pile', 0x248: 'item prop'}
LOOT_SPANS = ((0x100974, 0x100BA0), (0x100D54, 0x101998))   # loot_spawnGold, loot_generateDrops (ghidra_funcs.tsv)
# Creature_dropHeldPartAsProp 0x117d30 allocates a 0x248-byte PhProp at 0x117e30
# (docs/spec/weapon-holder.md 3.3; observed six times in each round-6 fighting run).
OTHER_POOL = {(0x117E30, 0x248): 'dropped held-part prop'}


# Services kept as boundaries even though some difftest executed them: animation, sound and
# presentation, the terrain and ray queries (the world is AUTHORED flat open ground), and
# the camera/net/dialog checks.  Everything else that some difftest of this tree executed
# (probe_full_placement.executed_bodies(): 853 bodies) runs for real in --real-creatures.
KEPT_SERVICES = {
    'anim_clear', 'anim_push', 'anim_pushChained', 'anim_start', 'anim_startBlendInOut',
    'anim_pushWithWeights', 'anim_advance', 'anim_releaseCaches', 'anim_snapTopToEnd',
    'anim_jumpTopToEnd', 'anim_syncToSimFrame', 'anim_setTrackWeightRate', 'anim_findTrack',
    'anim_findTrackByFlag', 'anim_randomizeTopTime', 'Creature_stepAnim', 'Player_animStep',
    'res_find', 'model_buildHideMask', 'model_getBounds', 'model_getAttachPoint',
    'model_getSamplePointCount', 'model_getSamplePoint',
    'terrain_heightBelow', 'terrain_height', 'terrain_raycast', 'world_raycast', 'terrain_testFlag1',
    'world_slideMove', 'water_test', 'water_disturb', 'fx_spawn', 'particle_spawn',
    'sound_playOnObject', 'sound_playAtPos', 'sound_playHit', 'decal_add', 'fx_burnModel',
    'fx_shockModel', 'player_voice', 'glow_add', 'light_link', 'light_unlink', 'light_relink',
    'light_dtor', 'Player_weaponTrails', 'Camera_reset', 'dialog_isOpen', 'net_getCamFlag',
    'task_isRunning', 'game_isFrozen', 'dbg_printf', 'obj_updateActive', 'Creature_updateActive',
    'rigidbody_init', 'quat_fromMat3', 'quat_normalize', 'rigidbody_updateDerived',
    'mainloop_startFadeWait', 'arena_openEndPrompt', 'decal_reset', 'libc_sprintf'}


def executed_follow():
    import probe_full_placement as PF
    names = PF.symbol_names()
    # the player keeps round 5's configuration (install_player_tick): its own bodies are not
    # switched on by this rule
    return {a for a in PF.executed_bodies() if names.get(a) not in KEPT_SERVICES and
            not (names.get(a) or '').lower().startswith('player_')}


def typeinfo_getters():
    import probe_full_placement as PF
    return {a for a, n in PF.symbol_names().items() if n.endswith('_typeinfo')}


def install_chain_check(emu, created):
    """Each construction against ref_arena_creature_chain.chain, evaluated on the memory
    at world_createObject's entry and compared when arena_spawnMonster asks for the
    SpellArena block (nothing between them draws; the wave 0-2 scale is 1.0)."""
    import ref_combat as RC
    tables = RC.Tables.load(emu.elf_path)
    emu.chain_checks = []

    def entering(e):
        index = class_index(e.mem, e.r[4] & 0xFFFFFFFF)
        if index in CH.CONSTRUCTOR:
            seed = e.mem.u32(B.G_RAND_SEED)
            e.chain_pending = (seed, CH.chain(index, seed, e.mem.u32, e.mem.u8, tables, MODEL_BOUNDS_Z))
    emu.hook(WORLD_CREATE + 4, entering)    # after entering_world_create's hook at the entry

    def spell_block(e):
        if getattr(e, 'chain_pending', None) is None:
            return
        seed, want = e.chain_pending
        index, obj = created[-1]
        assert e.mem.u32(B.G_RAND_SEED) == want['shared'], ('chain shared seed', index)
        # arena_spawnMonster then scaled the stats (ref_monster_build.arena_scale,
        # ref_arena_match_core.scale_stats: truncations even at a scale of 1.0)
        scale = B.arena_scale(B.arena_cycle(e.mem.u16(B.G_WAVE), e.mem.u16(B.G_RECIPE_COUNT)), index)
        fields = dict(want['fields'])
        stats = {off: fields[off][1] for off in (0xE4, 0x228, 0x22C, 0xD0, 0xD2, 0xD4, 0xD8)}
        for off, value in MC.scale_stats(stats, (scale,) * 5).items():
            fields[off] = (fields[off][0], value)
        for off, (width, value) in fields.items():
            got = e.mem.load(obj + off, width)
            assert got == value, ('chain field', index, hex(off), hex(got), hex(value))
        e.chain_checks.append((index, len(want['fields']) + 1, want['shared'] != CH.lcg(seed)[0]))
        e.chain_pending = None
    emu.spell_block_check = spell_block


def install_real_creatures(emu, created, spells, disc_models=None):
    """--real-creatures: the class constructors and their whole chain run for real
    (ref_arena_creature_chain.REAL; docs/spec/arena-creature-chain.md), and so do
    creature_addSpell with handle_link (SpellArena is linked into +0x364), slot 34
    (home range) and slot 27 (the class set-state with state 0).  Services: res_find
    answers one authored part for creature entries, model_getBounds authored z bounds,
    the model and animation calls stay recording stubs."""
    emu.orbs, emu.chunks, emu.loot, emu.other_blocks = [], [], [], []
    emu.follow.update(DEATH_PATH | LOOT_PATH | typeinfo_getters() | executed_follow())
    emu.follow.update({CH.ONIBALL_CTOR, CH.PROJECTILE_CTOR, CH.OBJ_RUN_EVERY_FRAME} | GUT_CHUNK_CHAIN)
    emu.follow.update(set(CH.REAL) | set(CONSTRUCTORS.values()) | set(SET_STATES.values()) |
                      {ADD_SPELL, HANDLE_LINK, HANDLE_CLEAR, HANDLE_REMOVE, HOME_RANGE_SLOT,
                       0x10A9C0, 0x1195E0, 0x1195F0, 0x119608, 0x11A6D0, 0x11A710,
                       emu.mem.u32(B.VT_SPELL_ARENA + 4)})   # SpellArena's type-info getter (slot 0)
    player_part = getattr(emu, 'player_part', emu.creature_part)
    model_addresses = {}

    def disc_model(lump_name, entry_name):
        key = (lump_name, entry_name)
        if key not in disc_models:
            raise ValueError('model %s::%s absent from disc' % key)
        if key not in model_addresses:
            blob = disc_models[key]
            pointer = emu.alloc(len(blob) + 0x10, align=0x10)
            emu.mem.write(pointer, blob)
            model_addresses[key] = pointer
        return model_addresses[key]

    def res_find(e):
        site = e._fresh_call.site if e._fresh_call is not None else 0
        if hasattr(e, 'clip_addresses'):
            lump = CH.cstr(e.mem.u8, e.r[4] & 0xFFFFFFFF).decode('latin1').lower()
            name = CH.cstr(e.mem.u8, e.r[5] & 0xFFFFFFFF).decode('latin1').lower()
            clip = e.clip_addresses.get((lump, name))
            if clip is not None:
                e.clip_resolutions += 1
                return clip
        if disc_models is not None:
            lump = CH.cstr(e.mem.u8, e.r[4] & 0xFFFFFFFF).decode('latin1').lower()
            name = CH.cstr(e.mem.u8, e.r[5] & 0xFFFFFFFF).decode('latin1').lower()
            if name.endswith('.vif'):
                return disc_model(lump, name)
        return player_part if RA.CTOR <= site < 0x1A24B8 else e.creature_part
    emu.stub(RA.RES_FIND, function=res_find)
    emu.clip_resolutions = 0
    emu.model_addresses = model_addresses

    def bounds(e):
        outs = [e.r[k] & 0xFFFFFFFF for k in range(6, 12)]
        for out, value in zip(outs, (0, 0, MODEL_BOUNDS_Z[0], 10, 10, MODEL_BOUNDS_Z[1])):
            e.mem.w32(out, value & 0xFFFFFFFF)
        return 0
    emu.stub(CH.MODEL_BOUNDS, function=bounds)

    def entering_add_spell(e):
        check_spell_record(e, spells, e.r[4] & 0xFFFFFFFF, e.r[5] & 0xFFFFFFFF)
    emu.hook(ADD_SPELL, entering_add_spell)
    install_real_free_spot(emu)
    install_chain_check(emu, created)
    for index, table in VTABLES.items():
        if index in SET_STATES:
            assert emu.mem.u32(table + 8 * 27 + 4) == SET_STATES[index]
            assert emu.mem.u32(table + 8 * 34 + 4) == HOME_RANGE_SLOT
    return created


def build_wave(path, wave, seed, real_player=False, real_creatures=False, world_data=None, clips=None):
    """Run the original wave builder through every spawn, with factory fixtures
    (or, with real_creatures, the original constructors)."""
    real_player = real_player or real_creatures
    emu = setup(path, wave, seed, real_creatures, world_data, clips)
    emu.follow = {D.STEP, D.SPAWN, 0x166630, 0x1666E0, 0x3B75D0, SCALE}
    if clips is not None:
        follow_disc_animation(emu)
    emu.replacements = []
    if real_player:
        install_real_player(emu)
    created = install_factory_fixture(emu, real_creatures)
    emu.call(D.START, 1)
    indices = [i for i, _obj in created]
    assert indices == dry_wave(path, wave, seed), (wave, indices)
    assert len(D.calls(emu, SCALE)) == len(created), (wave, len(created))
    assert len(D.calls(emu, WORLD_CREATE)) == len(created)
    assert len(D.calls(emu, OBJECT_FACTORY)) == len(created)
    return emu, created


def disc_animation_report(path, seed, iso_path):
    """Bounded original clip advance for every recipe-0 actor class, not a match tick."""
    world_data = recipe0_world_from_disc(iso_path)
    clips = recipe0_clips_from_disc(iso_path)
    for wave in range(3):
        emu, created = build_wave(path, wave, seed, real_creatures=True,
                                  world_data=world_data, clips=clips)
        assert emu.clip_resolutions, ('no disc clips resolved', wave)
        start_seed = emu.mem.u32(B.G_RAND_SEED)
        results = []
        for index, obj in created:
            # The surrounding object scheduler is still authored. Activate this
            # isolated actor so Creature_stepAnim accepts a one-frame tick.
            emu.mem.w64(obj + 0xA8, emu.mem.u64(obj + 0xA8) | (1 << 63))
            tracks = emu.mem.u8(obj + 0x118)
            before = tuple(emu.mem.u32(obj + 0x114 + 8 + 0x20 * slot + 0x18)
                           for slot in range(tracks))
            emu.call(0x1162B0, obj, fargs=(1.0,), max_steps=10_000_000)
            after = tuple(emu.mem.u32(obj + 0x114 + 8 + 0x20 * slot + 0x18)
                          for slot in range(tracks))
            assert tracks and before != after, ('clip did not advance', wave, index)
            results.append((index, tracks, before, after))
        print('wave %d: %d original clips resolved, %d actors advanced, seed %#x -> %#x; tracks %s'
              % (wave, emu.clip_resolutions, len(results), start_seed,
                 emu.mem.u32(B.G_RAND_SEED), [(index, count) for index, count, _, _ in results]))
    return 0


def run_match(path, seed, attacked, max_frames=2400, fighting=False,
              real_player=False, real_creatures=False, world_data=None, disc_models=None):
    """Run original arena_runTask and nextWave on an authored object fixture.

    The driver injects a lethal player hit after each intro. Original base
    damage processing and the class death set-state execute on the fixture.
    The fighting variant first executes two class AI ticks per creature, with
    a close player at each creature's authored position, then ticks Player
    damage processing. It does not model input or world collision.
    The world walk is an authored service over those fixture objects. This
    establishes the arena flow's next boundary, not combat or a live match.
    """
    assert not fighting or attacked
    real_player = real_player or real_creatures
    emu = setup(path, 0, seed, real_creatures, world_data)
    emu.follow = {D.TICK, D.NEXT, D.START, D.STEP, D.SPAWN, 0x3063FC,
                  0x166630, 0x1666E0, 0x3B75D0, SCALE}
    emu.replacements = []
    if real_player:
        install_real_player(emu)
        install_player_tick(emu)
    created = install_factory_fixture(emu, real_creatures, disc_models)
    emu.player_ticks = emu.player_draws = 0
    emu.player_states = Counter()
    emu.mem.w32(D.PLAYERS + 0xAC, 0x41A00000)
    if fighting:
        emu.mem.w32(D.PLAYERS + 0xAC, 0x461C4000)  # 10,000 HP for three authored waves
        emu.mem.write(0x41B721, b'arena\0')
        emu.stub(0x10C0F0, ret=1)  # active creature
        emu.stub(0x1162B0, ret=1)  # melee animation event
        emu.stub(0x118D40, ret=1)  # close, visible player
        emu.follow.update(set(RUN_STATES.values()) | ({PICK_TARGET} if real_creatures else set()) |
                          {0x1196E8, 0x1E8230, PLAYER_TAKE_DAMAGE,
                           PLAYER_PROCESS_DAMAGE, 0x3B8534})
    emu.mem.w32(D.ENDF, 0)
    emu.mem.w32(D.BUDGET, 100)
    emu.mem.w16(D.INTER, 0)
    emu.stub(D.END, ret=0)

    def walk(e):
        callback = e.r[4] & 0xFFFFFFFF
        if callback in (0x3069E8, 0x306A28):
            alive = sum((e.mem.u32(obj + 0xC) & 0x68) == 0x20 and
                        e.mem.s16(obj + 0x312) >= 0 for _index, obj in created)
            e.mem.w16(0x8E733E, alive)
        return 0

    emu.stub(D.WALK, function=walk)
    if attacked:
        for set_state in SET_STATES.values():
            emu.unhook(set_state)
        emu.follow.update(set(SET_STATES.values()) |
                          {TAKE_DAMAGE, PROCESS_DAMAGE, 0x10A9C0,
                           0x1195E0, 0x1195F0, 0x119608})
        emu.mem.w32(D.WORD890, 0)
    steps = 400_000_000 if real_creatures else 5_000_000
    emu.call(D.START, 1, max_steps=steps)
    waves = [(0, len(created))]
    killed_waves = set()
    combat_frames = {}
    hit_indices = []
    last_wave = 0
    for frame in range(max_frames):
        emu.mem.w32(D.FRAME, frame)
        wave = emu.mem.u16(D.WAVE)
        if fighting and wave not in killed_waves and emu.mem.u16(D.INTRO) == 0xFFFF:
            phase = combat_frames.get(wave, 0)
            if phase < 2:
                player = emu.arena_player
                D.bind_player(emu, 0, player)  # stand-in for the refused Player replacement
                for index, obj in created:
                    if (emu.mem.u32(obj + 0xC) & 0x68) != 0x20:
                        continue
                    if phase == 0:
                        if real_creatures:
                            # Driver requests a scan once; the original chooses through
                            # the real grid and links the target handle.
                            emu.call(PICK_TARGET, obj, 1, max_steps=steps)
                            node = emu.mem.u32(obj + 0x234)
                            assert node and emu.mem.u32(node + 0xC) == player, (index, obj, node)
                        else:
                            node = emu.alloc(0x20)
                            emu.mem.w32(node + 0xC, player)
                            emu.mem.w32(obj + 0x234, node)
                        emu.call(SET_STATES[index], obj, 3)
                    for axis in range(3):
                        emu.mem.w32(player + 0x10 + 4 * axis,
                                    emu.mem.u32(obj + 0x10 + 4 * axis))
                    emu.call(RUN_STATES[index], obj, max_steps=steps)
                if phase == 1:
                    emu.call(PLAYER_PROCESS_DAMAGE, player, max_steps=steps)
                combat_frames[wave] = phase + 1
        if attacked and wave not in killed_waves and emu.mem.u16(D.INTRO) == 0xFFFF and \
                (not fighting or combat_frames.get(wave, 0) >= 2):
            player = emu.arena_player
            D.bind_player(emu, 0, player)
            for index, obj in created:
                if (emu.mem.u32(obj + 0xC) & 0x68) == 0x20:
                    emu.call(TAKE_DAMAGE, obj, player, 1, fargs=(1000.0,), max_steps=steps)
                    emu.call(PROCESS_DAMAGE, obj, 0, max_steps=steps)   # a kill runs the loot chain
                    assert emu.mem.u16(obj + 0x232) == 0x14
                    hit_indices.append(index)
            killed_waves.add(wave)
        if real_player:
            pad = RP.G_PADS
            press = DP.BTN['attack'] if fighting and frame % 30 == 0 else 0
            emu.mem.w32(pad + 8, press)
            emu.mem.w32(pad + 0xC, press)
            player = emu.mem.u32(D.PLAYERS + 0x43D8)
            assert player == emu.arena_player
            emu.player_states[emu.mem.u32(player + 0x58C)] += 1
            before = emu.mem.u32(RA.SEED)
            emu.call(PLAYER_RUN, player, max_steps=steps)
            emu.player_draws += lcg_steps(before, emu.mem.u32(RA.SEED))
            emu.player_ticks += 1
        emu.call(D.RUN, max_steps=steps)
        wave = emu.mem.u16(D.WAVE)
        if wave != last_wave:
            waves.append((wave, len(created)))
            last_wave = wave
            if wave == 2 and not attacked:
                break
        if wave == 2 and attacked and wave in killed_waves:
            break
    expected = [2, 3, 4]
    previous = 0
    for wave, cumulative in waves:
        if wave <= 2:
            made = cumulative - previous
            assert made == expected[wave], (wave, made, waves)
            previous = cumulative
    if attacked:
        assert [wave for wave, _ in waves][:3] == [0, 1, 2], waves
        assert Counter(hit_indices) == {0: 1, 1: 2, 3: 6}, hit_indices
        if fighting:
            emu.fighting_player_hits = len(D.calls(emu, PLAYER_TAKE_DAMAGE))
            hp = emu.mem.f32(D.PLAYERS + 0xAC)
            if real_creatures:
                # real stats and more real AI: the number of accepted hits is a result; each
                # loss is at most the largest damage high of the constructed creatures
                high = max(emu.mem.s16(obj + 0xD2) for _index, obj in created)
                assert 1 <= emu.fighting_player_hits <= 9, emu.fighting_player_hits
                assert 10000.0 - high * emu.fighting_player_hits <= hp < 10000.0, (hp, high)
            else:
                assert emu.fighting_player_hits == 9, emu.fighting_player_hits
                # docs/gameplay.md §2.5 steps 9–10: each of nine zero-armour hits
                # rolls within the authored 10..20 range. Exact HP is seed-specific.
                assert 10000.0 - 20.0 * 9 <= hp <= 10000.0 - 10.0 * 9, hp
    else:
        assert waves == [(0, 2)], waves
    return emu, waves, frame + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    parser.add_argument('--real-player', action='store_true',
                        help='real destructor, pool reuse, Player constructor chain, placement and Player_run')
    parser.add_argument('--real-creatures', action='store_true',
                        help='also the real creature constructor chain, SpellArena attachment, free-spot '
                             'search and every executed body on the path (implies --real-player)')
    parser.add_argument('--disc-terrain', metavar='ISO',
                        help='with --real-creatures, read pvparena.world from this disc at run time '
                             'and execute its original terrain queries')
    parser.add_argument('--disc-animation', metavar='ISO',
                        help='with --real-creatures, load recipe-0 .anm clips from this disc at run '
                             'time and execute one original animation tick per constructed actor')
    args = parser.parse_args()
    if (args.disc_terrain or args.disc_animation) and not args.real_creatures:
        parser.error('--disc-terrain and --disc-animation require --real-creatures')
    if args.disc_animation:
        if args.disc_terrain and args.disc_terrain != args.disc_animation:
            parser.error('both disc options must name the same ISO')
        return disc_animation_report(args.elf, args.seed, args.disc_animation)
    if args.real_creatures:
        world_data = recipe0_world_from_disc(args.disc_terrain) if args.disc_terrain else None
        return real_creatures_report(args.elf, args.seed, world_data)
    if args.real_player:
        return real_player_report(args.elf, args.seed)
    for wave in range(3):
        indices = dry_wave(args.elf, wave, args.seed)
        counts = Counter(indices)
        print('wave %d: %d spawn calls, indices %s' %
              (wave, len(indices), ', '.join('%d:%d' % pair for pair in sorted(counts.items()))))
    index, spawn_number = first_constructor_boundary(args.elf, args.seed)
    print('followed builder: wave 0 spawn %d reaches class-table index %d at world_createObject' %
          (spawn_number, index))
    for wave in range(3):
        emu, created = build_wave(args.elf, wave, args.seed)
        print('constructor fixtures: wave %d created %d objects; original factory/spawn/scale calls %d/%d/%d' %
              (wave, len(created), len(D.calls(emu, OBJECT_FACTORY)),
               len(D.calls(emu, D.SPAWN)), len(D.calls(emu, SCALE))))
    for attacked in (False, True):
        emu, waves, frames = run_match(args.elf, args.seed, attacked)
        print('%s: %d run-task frames; wave/cumulative factory count %s; final wave %d, '
              'intro %d, intermission %d' %
              ('attacked fixture' if attacked else 'idle fixture', frames, waves,
               emu.mem.u16(D.WAVE), emu.mem.u16(D.INTRO), emu.mem.u16(D.INTER)))
    emu, waves, frames = run_match(args.elf, args.seed, True, fighting=True)
    print('fighting fixture: %d frames; waves %s; Player_takeDamage calls %d; final player HP %.1f' %
          (frames, waves, emu.fighting_player_hits,
           emu.mem.f32(D.PLAYERS + 0xAC)))


def real_player_report(path, seed):
    """Recipe 0 (the first record), waves 0-2, idle and fighting, real Player."""
    for wave in range(3):
        emu, created = build_wave(path, wave, seed, real_player=True)
        (block, before), = emu.replacements
        print('wave %d builder: %d objects; player block %#x reused; ctor seed %#x -> spawn %s facing %#x'
              % (wave, len(created), block, before,
                 tuple('%#x' % emu.mem.u32(block + 0x3B4 + 4 * k) for k in range(3)),
                 emu.mem.u16(block + 0x38)))
    for label, attacked, fighting in (('idle', False, False), ('fighting', True, True)):
        emu, waves, frames = run_match(path, seed, attacked, fighting=fighting, real_player=True)
        print('%s: %d frames; waves %s; %d Player constructions, %d Player_run ticks (%d shared draws); '
              'states %s; final seed %#x; record HP %.1f'
              % (label, frames, waves, len(emu.replacements), emu.player_ticks, emu.player_draws,
                 dict(sorted(emu.player_states.items())), emu.mem.u32(RA.SEED),
                 emu.mem.f32(D.PLAYERS + 0xAC)))
        if fighting:
            print('    Player_takeDamage calls %d' % emu.fighting_player_hits)
    return 0



TRIPLE_DRAW_SITES = {FREE_SPOT, 0x100974}   # three draws per sample: world_findFreeSpot, loot_spawnGold


def check_ledger(emu, start):
    """Every value stored to the shared seed lies on the documented generator's orbit
    (lcg_steps raises otherwise) and advances it by at least one draw; the two unit-ball /
    scatter samplers advance it by a multiple of three.  Some bodies draw more than once
    before one store (loot_generateDrops' equipment budget: two).  Returns
    ({function entry: draws}, number of stores of more than one draw)."""
    out, multi = Counter(), 0
    for entry, pc, n in seed_ledger(emu, start):
        assert n >= 1, (hex(pc), n)
        if entry in TRIPLE_DRAW_SITES:
            assert n % 3 == 0, (hex(pc), n)
        elif n > 1:
            multi += 1
        out[entry] += n
    return out, multi


def census(emu):
    """Stubbed callees that are neither kept services nor the authored arena hooks."""
    import probe_full_placement as PF
    names = PF.symbol_names()
    st = Counter(names.get(c.target, hex(c.target)) for c in emu.calls if c.stubbed)
    return {k: v for k, v in st.items() if k not in KEPT_SERVICES}


def real_creatures_report(path, seed, world_data=None):
    """Recipe 0 (the first record), waves 0-2, with the real creature chain."""
    import probe_full_placement as PF
    names = PF.symbol_names()
    for wave in range(3):
        emu, created = build_wave(path, wave, seed, real_creatures=True, world_data=world_data)
        assert not emu.other_blocks, ('unexpected builder part props', wave, emu.other_blocks)
        spots = emu.free_spot_calls
        print('wave %d builder: %d objects %s; chain model matched for %d (%d comparisons, %d with two '
              'shared draws); %d free-spot calls matched the model (%d draws, %d tries)'
              % (wave, len(created), [i for i, _o in created], len(emu.chain_checks),
                 sum(n for _i, n, _t in emu.chain_checks), sum(1 for c in emu.chain_checks if c[2]),
                 len(spots), sum(c['draws'] for c in spots), sum(c['tries'] for c in spots)))
    for label, attacked, fighting, frames in (('idle', False, False, 3700), ('fighting', True, True, 2400)):
        emu, waves, ran = run_match(path, seed, attacked, max_frames=frames, fighting=fighting,
                                    real_creatures=True, world_data=world_data)
        assert Counter((site, size) for site, size, _block in emu.other_blocks) == \
            ({(0x117E30, 0x248): 6} if fighting else {}), (label, emu.other_blocks)
        ledger, multi = check_ledger(emu, seed)
        print('%s: %d frames; waves %s; %d Player constructions, %d Player_run ticks (%d shared draws); '
              'states %s; final seed %#x; %d creature constructions matched the chain model'
              % (label, ran, waves, len(emu.replacements), emu.player_ticks, emu.player_draws,
                 dict(sorted(emu.player_states.items())), emu.mem.u32(RA.SEED), len(emu.chain_checks)))
        print('    shared draws by function (every store checked; %d stores of several draws): %s; total %d'
              % (multi, ', '.join('%s %d' % (names.get(k, hex(k)), v) for k, v in
                                  sorted(ledger.items(), key=lambda kv: -kv[1])), sum(ledger.values())))
        print('    free-spot calls %d matched the model; orbs %d, gib chunks %d, loot blocks %d, other blocks %d'
              % (len(emu.free_spot_calls), len(emu.orbs), len(emu.chunks), len(emu.loot), len(emu.other_blocks)))
        if fighting:
            print('    Player_takeDamage calls %d; record HP %.1f' % (emu.fighting_player_hits,
                                                                     emu.mem.f32(D.PLAYERS + 0xAC)))
        print('    stubs that are not kept services: %s' % dict(sorted(census(emu).items())))
    return 0


if __name__ == '__main__':
    main()
