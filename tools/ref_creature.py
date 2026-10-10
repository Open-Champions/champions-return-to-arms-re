#!/usr/bin/env python3
"""ref_creature.py - reference model of the creature base class of Champions: Return to Arms
(SLUS_209.73, US v2.00): the per-tick logic every monster shares.

A research tool, not game code.  Every method was written from the instruction sequence at
the address given in its docstring and is compared with that code, executed under
tools/ee_emu.py, by tools/difftest_creature.py.  docs/spec/creature-tick.md is the prose
version.  Standard library only; no game data is embedded (strings and tables the code
uses are named by address and read through the memory the caller supplies).

How the model sees the game
    The base class chases pointers all the time (creature -> target handle -> node ->
    object, player record -> player object, virtual tables), so the model works on a memory
    image, like tools/ref_player.py:

        mem        an object with load(addr, size) / store(addr, size, value), little endian
                   (Memory below is one; tools/difftest_creature.py wraps the interpreter's)
        creature   address of a Creature object (0x3c8 bytes, docs/creatures.md)

    Globals are read at their own addresses.  Floats are raw 32-bit patterns and go through
    tools/ref_core.py's R5900 arithmetic.

There is no single "creature tick" function
    Creature_run 0x112948 is one of several base-class functions a monster class's own run
    (virtual slot 4) calls; docs/monsters.md section 1.3 gives the usual order.  Each of
    those functions is one method of Model:

        process_damage   Creature_processDamage 0x110d30     hit reaction, death, kill call-outs
        run              Creature_run 0x112948               followers, timers, counters, boss meter
        update_active    Creature_updateActive 0x10c0f0      near an activity centre (or the camera)?
        pick_target      Creature_pickTarget 0x10ded0        virtual slot 23
        step_anim        Creature_stepAnim 0x1162b0          animation step and root motion
        turn_toward      Creature_turnToward 0x10bb08        virtual slot 26
        move_by          Creature_moveBy 0x113c48            the collision step
        move_to          Creature_moveTo 0x114510            path following, stuck recovery
        move_to_target   Creature_moveToTarget 0x1143e8
        move_to_dest     Creature_moveToDest 0x119f38
        settle           Creature_settle 0x119e38
        take_damage      Creature_takeDamage 0x116638        virtual slot 2
        is_enemy         Creature_isEnemy 0x119328           virtual slot 20
        and the small ones listed in MODELLED.

Virtual calls
    A virtual call reads the table pointer at object +0x48 (16-bit `this` adjustment at
    +8*slot, function at +8*slot+4).  When the function found there is the base class's own
    body and the model has it (BASE_BODIES), the model runs its method; any other function
    is a subclass hook and becomes the callback 'Creature.v<slot>'.  So the same model
    serves a class that overrides set-state and one that does not.

What is outside the model
    Everything not listed in MODELLED is a callback: animation (tools/ref_anim.py owns
    anim_advance), damage numbers (tools/ref_combat.py owns damage_apply and
    Creature_setStats), world queries (tools/ref_world.py: terrain rays, the box query,
    the slide, the height query, paths), effects, sound, object construction, handle
    lists, scripts.  EXTERNALS names each one with its address and argument list.  A
    callback is  f(*args) -> result ; callbacks is a dict name -> function (or any object
    with .get), and a name that is missing answers zeroes.  Arguments are canonical:
    integers as unsigned 32-bit, floats as patterns, a vector as a tuple of three patterns,
    in the order "integer registers, then float registers".  Outputs the callee fills come
    back after the result: (result, out1, out2, ...).  A callback that changes the object
    (anim_advance writes the root motion, a set-state hook writes the state, handle_link
    writes the handle word) does so through the same memory.

Result
    Every method returns what the original returns.  Model.calls is every callback in
    order as (name, args), Model.writes every store as (address, size, value), Model.draws
    the number of shared-seed draws (0x404464) made so far.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF


def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def s64(x):
    x &= M64
    return x - (1 << 64) if x >> 63 else x


# ---------------------------------------------------------------------------------------
# Addresses.  (machine) marks what is not lockstep state: docs/spec/creature-tick.md
# section 12 says what each one gates.
# ---------------------------------------------------------------------------------------
G_PLAYERS, REC_SIZE, REC_OBJ = 0x4D8AF0, 0x4C30, 0x43D8
G_NUM_PLAYERS = 0x4D8AE0
G_SIM_FRAME = 0x44FDCC
G_WORLD = 0x44FDC8
G_LEVEL_FLAGS = 0x44FE08                # bit 0x100: the cold level (breath, forced slow amount)
G_RAND_SEED = 0x404464                  # shared seed (in the sync hash)
G_SEED3 = 0x404468                      # third generator (machine)
G_NETWORK_MODE = 0x402791               # s8
G_CUTSCENE_ACTIVE = 0x44FCD0            # s8
G_DECAL_DETAIL = 0x44FDC0               # s32 local option (machine)
G_CULL_BY_CAMERA = 0x4039C1             # s8 (machine while a cutscene runs: D6)
G_CAMERA_FOCUS = 0x44F048               # Vec3 (machine)
G_ACTIVITY_CENTERS, G_ACTIVITY_COUNT = 0x4039C8, 0x403A08
G_RUN_LIST_ACTIVE, G_RUN_LISTS_60, G_RUN_LIST_60_CURSOR = 0x5DB3A8, 0x5DB3F0, 0x4039FC
G_LOCAL_ALIVE_COUNT, G_LOCAL_ALIVE_LIST = 0x4F8424, 0x4F8430      # (machine) E11
G_BOSS_METER_HP, G_BOSS_METER_MAX, G_BOSS_METER_AUX = 0x41B6A0, 0x41B6A4, 0x41B6A8
G_BOSS_METER_NAME = 0x41BA40
G_FOLLOW_TELEPORT_DIST = 0x40278C       # float
G_SCAVENGER_KIND = 0x402768             # s32: 1 raven, 2 rat
G_SCAVENGER_DATA = (0x402770, 0x402780)
G_LEVEL_MONSTER_LEVEL = 0x4F714C        # float
G_EXCLUDE_MASK = 0x4039B8
G_EXP_TABLE = 0x41B558                  # s32[81]
G_SKILL_BURN = 0x41B1A4                 # pointer to the Skill object asked for a burning player's damage
G_SKILL_ONKILL = 0x41B25C               # pointer to the Skill object behind skill 0x3b's fraction
G_PARTICLE_METAL = 0x5BF608             # particle definition of the metal hit sparks

# strings the code passes around (addresses only)
S_PATHNAME, S_FOLLOW_LOST, S_FOLLOW_FOUND = 0x530048, 0x52FC48, 0x52FC60
S_DEAD, S_FX_LUMP, S_HIT_METAL, S_SPLASH = 0x52FA10, 0x52FC18, 0x52FFE0, 0x530058
S_RAVEN, S_RAT = 0x530020, 0x530040

# float constants (patterns)
ZERO, HALF, ONE = 0x00000000, 0x3F000000, 0x3F800000
MINUS_ONE = 0xBF800000
F_2M16 = 0x37800000                     # 1 / 65536
DT = 0x3C888888                         # 1 / 60, truncated
F_60 = 0x42700000
F_0_1 = 0x3DCCCCCC                      # 0.1, truncated
F_0_3 = 0x3E999999

# Creature virtual slots whose base-class body the model has: slot -> (address, method)
BASE_BODIES = {
    2: (0x116638, 'take_damage'),
    6: (0x11A418, 'slot6_touched'),
    7: (0x11A260, 'slot7_path_done'),
    10: (0x11A3F0, 'slot_empty'),
    11: (0x11A448, 'slot_empty'),
    17: (0x11A868, 'update_spells'),
    20: (0x119328, 'is_enemy'),
    23: (0x10DED0, 'pick_target'),
    26: (0x10BB08, 'turn_toward'),
    27: (0x3C2688, 'slot27_set_state'),
    30: (0x118A58, 'slot30_stun'),
    31: (0x118AF8, 'slot31_no_target'),
    35: (0x118C50, 'slot35'),
    36: (0x118C78, 'slot36'),
    37: (0x3C2730, 'slot37_team'),
}

# The original functions the model implements (name -> address); tools/difftest_creature.py
# runs exactly these for real.
MODELLED = {
    'Creature_run': 0x112948, 'Creature_updateActive': 0x10C0F0, 'obj_updateActive': 0x14DB08,
    'isNearView': 0x1E77C0, 'Creature_processDamage': 0x110D30, 'Creature_takeDamage': 0x116638,
    'Creature_pickTarget': 0x10DED0, 'Creature_isEnemy': 0x119328, 'Creature_turnToward': 0x10BB08,
    'Creature_stepAnim': 0x1162B0, 'Creature_moveBy': 0x113C48, 'Creature_moveTo': 0x114510,
    'Creature_moveToTarget': 0x1143E8, 'Creature_moveToDest': 0x119F38, 'Creature_settle': 0x119E38,
    'Creature_isAwayFromHome': 0x10EED8, 'Creature_getWaypoint': 0x11A020,
    'Creature_getNextWaypoint': 0x11A090, 'Creature_advanceWaypoint': 0x11A108,
    'Creature_clearPath': 0x11A1E0, 'Creature_requestPath': 0x1164C0, 'Creature_slot7': 0x11A260,
    'Creature_updateSpells': 0x11A868, 'Creature_spawnScavenger': 0x1125E0,
    'players_findNearestOnTeam': 0x1124E0, 'Creature_pickWanderDest': 0x119618,
    'Creature_randomPointNearHome': 0x110B58, 'creature_findClearHeading': 0x10EAA8,
    'Creature_slot6': 0x11A418, 'Creature_slot10': 0x11A3F0, 'Creature_slot11': 0x11A448,
    'Creature_default_slot27': 0x3C2688, 'Creature_stun': 0x118A58, 'Creature_slot31': 0x118AF8,
    'Creature_slot35': 0x118C50, 'Creature_slot36': 0x118C78, 'Creature_slot37': 0x3C2730,
    'GameObject_rand': 0x1509D0,
}


class Ext:
    """One callback: address (0 for a virtual call), integer argument kinds, number of
    float arguments, result kind.

    Integer kinds, one per integer register from a0:
        i value          p address          v pointer to three floats (passed as a tuple)
        e pointer to a burn element record, or 0 (passed as ('elem', min, max) or 0)
        l pointer to a zero-terminated list of object pointers (passed as a tuple)
        s pointer to the text a libc_sprintf call produced (passed as ('buf', text))
        o pointer the callee fills with three floats      O the same, may be null (1 or 0 is passed)
        w pointer the callee fills with one 32-bit word   b pointer the callee fills with one byte
        n pointer to an object-pointer array the callee fills, zero terminated
        - not an argument of the model (scratch on the stack)
    Result kinds: i integer, f float, n nothing, s the text of libc_sprintf."""

    def __init__(self, addr, ints='', floats=0, ret='i', note=''):
        self.addr, self.ints, self.floats, self.ret, self.note = addr, ints, floats, ret, note


EXTERNALS = {
    # --- objects, properties, scripts
    'obj_getPropStr': Ext(0x14F4C0, 'ppi', 0, 'i', '(object, property name, 0) -> text or 0'),
    'obj_getPropInt': Ext(0x14C880, 'ppi', 0, 'i', '(object, property name, default)'),
    'obj_updateGridCell': Ext(0x14F028, 'p', 0, 'n'),
    'obj_runEveryFrame': Ext(0x14F248, 'p', 0, 'n'),
    'obj_delete': Ext(0x14F200, 'p', 0, 'n'),
    'script_runByName': Ext(0x1ED694, 'p', 0, 'n'),
    'world_notifyObjectsNear': Ext(0x11A2B8, 'ivp', 1, 'n', '(0, position, creature; 600.0)'),
    'pool_new': Ext(0x14FDB8, 'i', 0, 'i', '(size) -> block or 0'),
    # --- the level path a PathName creature follows
    'pathFollower_init': Ext(0x20FFDC, '-pv', 0, 'n', '(follower, path name, position)'),
    'paths_findByName': Ext(0x20F9E4, 'p', 0, 'i', '(path name) -> point list'),
    'pointList_snapToNearest': Ext(0x210034, '-', 0, 'i', '(follower) -> index (stored in the follower)'),
    'pointList_getPoint': Ext(0x21039C, 'pi', 0, 'i', '(point list, index) -> point record or 0'),
    # --- players
    'players_anyWithinRadius': Ext(0x13E428, 'v', 1, 'i', '(position; radius)'),
    'net_objOrGhost': Ext(0x13E180, 'p', 0, 'i', '(object) -> the object, or the prediction copy of a local player'),
    'player_speedScale': Ext(0x1BEA10, 'i', 0, 'f', '(-1) -> the scale chasing monsters animate at'),
    'player_getSkillRank': Ext(0x1BF330, 'ii', 0, 'i', '(slot, skill id)'),
    'player_giveExp': Ext(0x1D3150, 'ii', 0, 'n', '(slot, amount)'),
    'SkillLifeTap_getStat0Fraction': Ext(0x2F8E78, 'pi', 0, 'f', '(skill object, rank)'),
    # --- animation, model
    'anim_advance': Ext(0x16D748, 'pppp', 1, 'i', '(state, sound position or 0, root out, yaw out; speed) -> event bits'),
    'anim_releaseCaches': Ext(0x171118, 'p', 0, 'n'),
    'anim_snapTopToEnd': Ext(0x170C80, 'p', 0, 'n'),
    'model_getBounds': Ext(0x179400, 'piwwwwww', 0, 'n', '(model, -1) -> six integers'),
    'model_getAttachPoint': Ext(0x1754A0, 'pvipioO', 1, 'n', '(model, pos, facing, anim state, index, out, dir out; scale)'),
    'SpellDrowsy_typeinfo': Ext(0x3D1234, '', 0, 'i', 'type-info getter'),
    'creature_findSpellByType': Ext(0x11A710, 'pp', 0, 'i', '(creature, type info) -> spell or 0'),
    'SpellDrowsy_getStat3Fraction': Ext(0x30EF08, 'p', 0, 'f'),
    'creature_bossRank': Ext(0x10D940, 'p', 0, 'i', '(creature) -> 0, 1 MiniBoss, 2 a boss by name'),
    # --- damage and effects
    'damage_apply': Ext(0x1E8230, 'ppiiiiei', 2, 'i', '(target, attacker, 100000, 0, 0, flags, elements, 0; min, max)'),
    'fx_spawn': Ext(0x1EF270, 'iv', 0, 'n', '(effect id, position)'),
    'fx_burnModel': Ext(0x1F5210, 'ppvip', 4, 'n', '(model, anim state, pos, facing, attach state; seconds, scale, offset, lod)'),
    'fx_shockModel': Ext(0x1F61C0, 'ppvipi', 3, 'n', '(model, anim state, pos, facing, attach state, colour; seconds, scale, offset)'),
    'fx_disintegrateModel': Ext(0x1F4340, 'pppvii', 2, 'n', '(creature, model, anim state, pos, facing, kind; scale, offset)'),
    'fx_shatterToLooseIce': Ext(0x1FB240, 'ppvip', 3, 'n', '(model, anim state, pos, facing, attach state; radius, scale, offset)'),
    'particle_spawn': Ext(0x18F3F8, 'pvv', 1, 'n', '(definition, position, velocity; 0.0)'),
    'decal_add': Ext(0x19F110, 'viii', 1, 'n', '(position, angle, kind, 0; size)'),
    'GutChunk_ctor': Ext(0x201958, 'pvii', 1, 'n', '(block, position, variant, kind; 1.0)'),
    'PhProp_initPhysics': Ext(0x155110, 'pi', 0, 'n', '(block, 0x12)'),
    'OniBall_ctor': Ext(0x294014, 'pvipi', 0, 'n', '(block, position, facing, creature, 0)'),
    'Critter_ctor': Ext(0x2547FC, 'ppvip', 0, 'n', '(block, name, position, facing, data)'),
    'libc_sprintf': Ext(0x3B7EF0, '-pi', 0, 's', '(buffer, format, one integer or none) -> the text'),
    'res_find': Ext(0x17365C, 'ps', 0, 'i', '(lump name, entry name) -> entry'),
    'sound_playOnObject': Ext(0x214230, 'pp', 1, 'i', '(entry, object; volume)'),
    # --- world queries (tools/ref_world.py)
    'terrain_raycast': Ext(0x18A5C0, 'pvvi', 1, 'f', '(world, origin, direction, mask; length factor) -> t, negative = no hit'),
    'world_raycast': Ext(0x18AD94, 'pvvpiii', 1, 'f', '(world, origin, direction, ignore, 0, mask, 0; length) -> t'),
    'terrain_heightBelow': Ext(0x1834A8, 'pv', 1, 'f', '(world, position; radius) -> ground height'),
    'world_collectObjectsInBox': Ext(0x14A928, 'vvni', 0, 'n', '(min, max, out array, capacity) -> objects'),
    'world_slideMove': Ext(0x14D238, 'pviO', 1, 'i', '(position in place, delta, mask, normal out; radius) -> hit'),
    'world_findFreeSpot': Ext(0x14ACF8, 'oviibi', 0, 'n', '(out, position, 72, radius, found out, 0)'),
    'water_test': Ext(0x189438, 'pvi', 1, 'i', '(world, position, 0; 12.0)'),
    'water_disturb': Ext(0x189514, 'pv', 2, 'i', '(world, position; a, b)'),
    'path_requestToPoint': Ext(0x184E38, 'pvvppi', 1, 'n', '(world, from, to, creature, waypoints, 16; radius)'),
    'path_requestType1': Ext(0x184FC8, 'pvvppi', 1, 'n', '(world, from, to, creature, waypoints, 16; distance)'),
    'path_requestType2': Ext(0x185148, 'pvvppi', 1, 'n'),
    'path_requestType3': Ext(0x1852C8, 'pvvppi', 1, 'n'),
    'Creature_probeThreeMovementRays': Ext(0x108FD8, 'pvi', 0, 'f', '(creature, direction, 0) -> clear fraction'),
    'Creature_computeAvoidanceTarget': Ext(0x109280, 'opv', 0, 'n', '(out, creature, destination)'),
    # --- handle lists
    'handle_clear': Ext(0x1A1698, 'p', 0, 'n', '(list head)'),
    'handle_link': Ext(0x1A1738, 'ppp', 0, 'n', '(list head, back list, object)'),
    'handle_removeNode': Ext(0x1A1868, 'p', 0, 'i'),
    'iter_begin': Ext(0x1A1A48, '-pi', 0, 'i', '(iterator, list head, mask); the model gets the first node'),
    'iter_next': Ext(0x1A1B38, '-', 0, 'i', '(iterator); the model gets the next node'),
    'iter_end': Ext(0x1A1AE8, '-i', 0, 'n'),
    # --- virtual calls: (this, ...)
    'Creature.v2': Ext(0, 'ppi', 1, 'n', 'take damage (attacker, flags; amount)'),
    'Creature.v6': Ext(0, 'pp', 0, 'n', 'touched by (other)'),
    'Creature.v7': Ext(0, 'pi', 0, 'n', 'path search finished (found)'),
    'Creature.v10': Ext(0, 'pv', 0, 'n', 'moved into terrain (normal)'),
    'Creature.v11': Ext(0, 'pl', 0, 'n', 'touched objects (list)'),
    'Creature.v17': Ext(0, 'pv', 0, 'n', 'spells follow (position)'),
    'Creature.v19': Ext(0, 'pp', 0, 'n', 'get display name (buffer)'),
    'Creature.v20': Ext(0, 'pp', 0, 'i', 'is enemy (other) -> 0, 1, 4'),
    'Creature.v23': Ext(0, 'pi', 0, 'n', 'pick target (force)'),
    'Creature.v26': Ext(0, 'piv', 0, 'i', 'turn toward (mode, point) -> angle before the turn'),
    'Creature.v27': Ext(0, 'pi', 0, 'n', 'set AI state'),
    'Creature.v30': Ext(0, 'pii', 0, 'n', 'stun (frames, flash)'),
    'Creature.v31': Ext(0, 'pi', 0, 'n', 'no-target timer (frames)'),
    'Creature.v35': Ext(0, 'p', 0, 'i', ''),
    'Creature.v36': Ext(0, 'p', 0, 'i', ''),
    'Creature.v37': Ext(0, 'p', 0, 'i', 'team byte'),
    'Skill.v11': Ext(0, 'piii', 0, 'i', '(0, level, 0) -> the number a burning player\'s damage is made from'),
    'Spell.v2': Ext(0, 'pvi', 0, 'n', 'follow (position, facing)'),
}


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row: the integer or float
    result, with every output the callee fills appended.  With outs=None everything is
    zero - the answer of a callback nobody supplied."""
    ext = EXTERNALS[name]
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwbn':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oO' else ([] if kind == 'n' else 0)
            if kind != 'O' or args[position]:
                values.append(value)
        if kind in 'ipvelsO':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


class Memory:
    """Sparse little-endian memory.  Unwritten bytes read from `under` (an object with
    load(addr, size)) or as zero.  Every store is appended to .log."""

    def __init__(self, under=None):
        self.bytes, self.under, self.log = {}, under, []

    def load(self, addr, size):
        get = self.bytes.get
        parts = [get(addr + i) for i in range(size)]
        if parts.count(None) == size:
            return self.under.load(addr, size) if self.under is not None else 0
        value = 0
        for i, b in enumerate(parts):
            if b is None:
                b = self.under.load(addr + i, 1) if self.under is not None else 0
            value |= b << (8 * i)
        return value

    def poke(self, addr, size, value):
        """Store without logging (set-up, and what a callback changes)."""
        for i in range(size):
            self.bytes[addr + i] = (value >> (8 * i)) & 0xFF

    def store(self, addr, size, value):
        value &= (1 << (8 * size)) - 1
        self.log.append((addr, size, value))
        self.poke(addr, size, value)


class Model:
    """The creature base class on a memory image.  See the module docstring."""

    def __init__(self, mem, callbacks=None, external=()):
        self.mem = mem
        self.cb = callbacks if callbacks is not None else {}
        self.external = set(external)       # names of MODELLED functions to treat as callbacks
        self.calls, self.writes, self.draws = [], [], 0

    # ---- memory ------------------------------------------------------------------------
    def u8(self, a):
        return self.mem.load(a, 1)

    def s8(self, a):
        return s8(self.mem.load(a, 1))

    def u16(self, a):
        return self.mem.load(a, 2)

    def s16(self, a):
        return s16(self.mem.load(a, 2))

    def u32(self, a):
        return self.mem.load(a, 4)

    def s32(self, a):
        return s32(self.mem.load(a, 4))

    def u64(self, a):
        return self.mem.load(a, 8)

    def _w(self, a, size, v):
        v &= (1 << (8 * size)) - 1
        self.writes.append((a, size, v))
        self.mem.store(a, size, v)

    def w8(self, a, v):
        self._w(a, 1, v)

    def w16(self, a, v):
        self._w(a, 2, v)

    def w32(self, a, v):
        self._w(a, 4, v)

    def w64(self, a, v):
        self._w(a, 8, v)

    def vec(self, a):
        return (self.u32(a), self.u32(a + 4), self.u32(a + 8))

    def wvec(self, a, v):
        """The twelve-byte copy the compiler emits for a vector assignment."""
        self._w(a, 8, (v[0] & M32) | ((v[1] & M32) << 32))
        self._w(a + 8, 4, v[2])

    # ---- callbacks ---------------------------------------------------------------------
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def table_call(self, cls, obj, table_offset, slot, *args):
        """A virtual call on something that is not a creature: always a callback."""
        table = self.u32(obj + table_offset)
        this = (obj + self.s16(table + 8 * slot)) & M32
        return self.call('%s.v%d' % (cls, slot), this, *args)

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48.  The base class's own body runs in the
        model; anything else is the callback 'Creature.v<slot>'."""
        table = self.u32(obj + 0x48)
        this = (obj + self.s16(table + 8 * slot)) & M32
        function = self.u32(table + 8 * slot + 4)
        base = BASE_BODIES.get(slot)
        if base is not None and function == base[0] and ('Creature.v%d' % slot) not in self.external:
            return getattr(self, base[1])(this, *args)
        return self.call('Creature.v%d' % slot, this, *args)

    # ---- generators --------------------------------------------------------------------
    def draw(self):
        """One draw from the shared seed 0x404464."""
        seed = (self.u32(G_RAND_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_RAND_SEED, seed)
        self.draws += 1
        return seed >> 16

    def obj_rand(self, obj):
        """GameObject_rand 0x1509d0: the object's own generator at +0x44."""
        seed = (self.u32(obj + 0x44) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(obj + 0x44, seed)
        return seed >> 16

    # ---- small accessors ---------------------------------------------------------------
    def player_obj(self, slot):
        return self.u32((G_PLAYERS + s32(slot) * REC_SIZE + REC_OBJ) & M32)

    def handle_obj(self, head):
        """The object behind a handle word, or 0."""
        node = self.u32(head)
        return self.u32(node + 0xC) if node else 0

    def slow_factor(self, c):
        """(60 - slow) / 60 as the code forms it, or None when the slow amount is outside
        1..60 (the unsigned test `slow - 1 < 60` at five sites)."""
        if not 1 <= self.u8(c + 0x2FC) <= 60:
            return None
        return C.mul(C.from_int(60 - self.s8(c + 0x2FC)), DT)

    # =====================================================================================
    # Creature_updateActive 0x10c0f0, obj_updateActive 0x14db08, isNearView 0x1e77c0
    # =====================================================================================
    def is_near_view(self, pos_addr, radius):
        """isNearView 0x1e77c0 (position; radius) -> 0 or 1.

        A square test in x and y.  With g_cullByCamera set the centre is the camera focus
        (per machine while a cutscene runs: FINDINGS D6); otherwise each player object of
        slots 0..g_numPlayers-1 in turn."""
        u32 = self.u32
        px, py = u32(pos_addr), u32(pos_addr + 4)

        def inside(cx, cy):
            return C.le(px, C.add(cx, radius)) and C.le(C.sub(cx, radius), px) and \
                C.le(py, C.add(cy, radius)) and C.le(C.sub(cy, radius), py)

        if self.s8(G_CULL_BY_CAMERA):
            return 1 if inside(u32(G_CAMERA_FOCUS), u32(G_CAMERA_FOCUS + 4)) else 0
        count = self.s32(G_NUM_PLAYERS)
        slot = 0
        while slot < count:
            obj = self.player_obj(slot)
            if obj and inside(u32(obj + 0x10), u32(obj + 0x14)):
                break
            slot += 1
        return 1 if slot != self.s32(G_NUM_PLAYERS) else 0

    def obj_update_active(self, obj, was, radius):
        """obj_updateActive 0x14db08 (object, was active, radius) -> 0 or 1.

        Active = within `radius` (44000 for an object with flag 0x80000) of the camera
        focus when g_cullByCamera is set, else of any activity centre; 3-D, strict.  On a
        change the object moves between the every-frame run list and one of the sixty
        slow lists (round robin)."""
        u32 = self.u32
        r = 0xABE0 if u32(obj + 0xC) & 0x80000 else radius & M32
        r2 = C.from_int(s32(r * r))
        px, py, pz = self.vec(obj + 0x10)

        def near(base):
            dx = C.sub(px, u32(base))
            dy = C.sub(py, u32(base + 4))
            dz = C.sub(pz, u32(base + 8))
            return C.lt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)), r2)

        now = 0
        if self.s8(G_CULL_BY_CAMERA):
            now = 1 if near(G_CAMERA_FOCUS) else 0
        else:
            for i in range(max(self.s8(G_ACTIVITY_COUNT), 0)):
                if near(G_ACTIVITY_CENTERS + 12 * i):
                    now = 1
                    break
        if now == was:
            return now
        node = u32(obj + 4)
        if node:
            self.call('handle_removeNode', node)
        if now:
            self.call('handle_link', G_RUN_LIST_ACTIVE, obj + 4, obj)
        else:
            cursor = self.s32(G_RUN_LIST_60_CURSOR) + 1
            self.w32(G_RUN_LIST_60_CURSOR, cursor)
            if cursor >= 60:
                self.w32(G_RUN_LIST_60_CURSOR, 0)
            self.call('handle_link', G_RUN_LISTS_60 + 4 * self.s32(G_RUN_LIST_60_CURSOR), obj + 4, obj)
        return now

    def update_active(self, c):
        """Creature_updateActive 0x10c0f0 (creature) -> 1 active, 0 not.

        Copies creature flag bit 63 (active) into bit 62 (was active), asks
        obj_updateActive with the largest of the activity radius +0x3c4, pointblankrange
        +0x3ac and visualrange +0x3ae, stores the answer in bit 63, and releases the
        animation caches of a creature that is not active.  The follow scripts are run on
        a change only when OBJECT flag bits 0xc00000 are set (docs/creatures.md C12)."""
        cf = self.u64(c + 0xA8)
        was = cf >> 63
        cf = cf | 0x4000000000000000 if was else cf & 0xBFFFFFFFFFFFFFFF
        self.w64(c + 0xA8, cf)
        radius = max(self.u16(c + 0x3C4), self.u16(c + 0x3AC), self.u16(c + 0x3AE))
        now = 1 if self.obj_update_active(c, was, radius) else 0
        if self.u32(c + 0xC) & 0xC00000 and was != now:
            script = self.call('obj_getPropStr', c, S_FOLLOW_FOUND if now else S_FOLLOW_LOST, 0)
            if script:
                self.call('script_runByName', script)
        if now:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000000000000000)
        else:
            self.call('anim_releaseCaches', c + 0x114)
            self.w64(c + 0xA8, self.u64(c + 0xA8) & 0x7FFFFFFFFFFFFFFF)
        return now

    # =====================================================================================
    # Creature_run 0x112948
    # =====================================================================================
    def run(self, c, model):
        """Creature_run 0x112948 (creature, model) -> 0, always.

        In order: spells follow (non-players), flash colours decay, PathName follower,
        the five frame timers, the charm timer with the followPlayer logic, the creature
        clock, the cold-level slow amount, glow, burn, shock, chill, status counter 7,
        the two damage-over-time timers, the boss meter, the corpse scavenger, the draw
        height spring, the touched-by-a-player reaction, deletion of a sunk corpse."""
        u32, w32 = self.u32, self.w32
        if not u32(c + 0xC) & 0x40:                              # 0x112984: not a player
            z = C.add(u32(c + 0x18), C.mul(u32(c + 0x20), HALF))
            self.vcall(c, 17, (C.add(u32(c + 0x10), ZERO), u32(c + 0x14), z))
        for quad in (c + 0x98, c + 0x90):                        # 0x112a00: flash colours toward 0 by 2
            for a in range(quad, quad + 8, 2):
                v = self.s16(a)
                if v > 0:
                    self.w16(a, v - 2)
                    if v - 2 < 0:
                        self.w16(a, 0)
                elif v < 0:
                    self.w16(a, v + 2)
                    if v + 2 > 0:
                        self.w16(a, 0)
        if self.u64(c + 0xA8) & 0x8000000:                       # 0x112a80: following a level path
            name = self.call('obj_getPropStr', c, S_PATHNAME, 0)
            if name:
                self._follow_path(c, name)
        frame = u32(G_SIM_FRAME)
        if self.s16(c + 0x316):                                  # no-target timer
            self.w16(c + 0x316, self.u16(c + 0x316) - 1)
            if not frame & 3:
                self.call('fx_spawn', 0x12, (u32(c + 0x10), u32(c + 0x14), C.add(u32(c + 0x18), u32(c + 0x20))))
        t = self.u16(c + 0x314)                                  # root timer: 0 and -1 stay
        if ((t + 1) & 0xFFFF) >= 2:
            self.w16(c + 0x314, t - 1)
        if self.s16(c + 0x318):                                  # attack cooldown
            self.w16(c + 0x318, self.u16(c + 0x318) - 1)
        if self.s16(c + 0x31A):                                  # spell-speed timer
            self.w16(c + 0x31A, self.u16(c + 0x31A) - 1)
        if self.s16(c + 0x31C):                                  # stun timer
            self.w16(c + 0x31C, self.u16(c + 0x31C) - 1)
            if not frame & 3:
                self.call('fx_spawn', 0x10, (u32(c + 0x10), u32(c + 0x14), C.add(u32(c + 0x18), u32(c + 0x20))))
        charm = self.s16(c + 0x312)
        if charm == 0:                                           # 0x113138
            if self.u64(c + 0xA8) & 0x2000000000000 and self.s16(c + 0x232) != 0x14:
                self.vcall(c, 27, 0x14)                          # dies when its charm has ended
        else:
            if charm != -1:
                charm -= 1
                self.w16(c + 0x312, charm)
            if charm == 0:                                       # the charm ends now
                self.w8(c + 0x310, 0xFF)
                self.w64(c + 0xA8, self.u64(c + 0xA8) & 0xFFFFFFFFFF3FFFFF)
            if self.u64(c + 0xA8) & 0xC00000:
                self._follow_player(c)
        if self.s8(c + 0x2FC) != 60:                             # 0x113178: the creature clock
            w32(c + 0x300, u32(c + 0x300) + 1)                   # (two remainders are computed and dropped)
        if u32(G_LEVEL_FLAGS) & 0x100:                           # 0x1131e8: cold level
            self.w8(c + 0x2FC, 10 if u32(c + 0xC) & 0x40 else 15)
        glow = u32(c + 0x354)
        if C.lt(ZERO, glow):                                     # 0x113218
            level = C.to_int(C.mul(C.fmin(ONE, glow), 0x43000000))
            self.w16(c + 0x96, 0x20)
            w32(c + 0x354, C.sub(glow, DT))
            for off in (0x90, 0x9C, 0x98, 0x94):
                self.w16(c + off, level)
        if C.lt(ZERO, u32(c + 0x340)):                           # 0x113278: burning
            flags = u32(c + 0xC)
            if self.call('net_objOrGhost', c) == c and not flags & 0x4000000:
                self.call('fx_burnModel', model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38), c + 0x320,
                          u32(c + 0x340), u32(c + 0xDC), u32(c + 0xE0), C.from_int(self.u8(c + 0x28)))
                flags = u32(c + 0xC)
            w32(c + 0x340, C.sub(u32(c + 0x340), DT))
            if not flags & 0x20000 and not u32(G_SIM_FRAME) & 0x1F:
                self._burn_damage(c, flags)
        if C.lt(ZERO, u32(c + 0x348)):                           # 0x113540: shock
            if self.call('net_objOrGhost', c) == c and not u32(c + 0xC) & 0x4000000:
                self.call('fx_shockModel', model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38), c + 0x320,
                          0x5E808080, u32(c + 0x348), u32(c + 0xDC), u32(c + 0xE0))
            left = C.sub(u32(c + 0x348), DT)
            w32(c + 0x348, left)
            if C.le(left, ZERO):
                for off in (0x33C, 0x334, 0x32C):
                    w32(c + off, 0)
        if C.lt(ZERO, u32(c + 0x344)):                           # 0x113608: chill
            self._chill(c)
        count = self.s32(c + 0x388)
        if count != 0:                                           # 0x113738: status counter 7
            if count <= 0 or u32(c + 0xC) & 8:
                w32(c + 0x388, 0)
                self.w8(c + 0x2FC, 0)
            else:
                elapsed = s32(u32(G_SIM_FRAME) - u32(c + 0xF0))
                if elapsed < 31:
                    self.w8(c + 0x2FC, elapsed << 1)
                    if s8(elapsed << 1) >= 61:
                        self.w8(c + 0x2FC, 60)
                else:
                    self.w8(c + 0x2FC, self.u8(c + 0x388) if count < 31 else 60)
            limit = C.sub(F_60, C.mul(u32(c + 0x6C), F_60))      # lightning resistance caps it
            if C.lt(limit, C.from_int(self.s8(c + 0x2FC))):
                self.w8(c + 0x2FC, C.to_int(limit))
        for timer, low, high in ((0x34C, 0x358, 0x35A), (0x350, 0x35C, 0x35E)):
            left = u32(c + timer)                                # 0x113818, 0x1138c0: damage over time
            if C.lt(ZERO, left):
                w32(c + timer, C.sub(left, DT))
                if not u32(c + 0xC) & 0x20000 and not u32(G_SIM_FRAME) & 0x1F:
                    self.call('damage_apply', c, c, 100000, 0, 0, 0x1080C040, 0, 0,
                              C.mul(C.from_int(self.s16(c + low)), F_0_1),
                              C.mul(C.from_int(self.s16(c + high)), F_0_1))
        cf = self.u64(c + 0xA8)
        if cf & 1 and self.s8(c + 0x231) == 0:                   # 0x113960: MiniBoss, not inert
            self._boss_meter(c, cf)
        self.spawn_scavenger(c)                                  # 0x113ae4
        z0 = u32(c + 0x3C)                                       # 0x113aec: drawn height follows z on a spring
        v = C.add(u32(c + 0x40), C.mul(C.sub(u32(c + 0x18), z0), 0x40400000))
        v = C.sub(v, C.mul(C.sqrt(0x3DB851EB), v))
        w32(c + 0x40, v)
        w32(c + 0x3C, C.add(z0, C.mul(v, DT)))
        state = self.s16(c + 0x232)
        if state in (0, 5) and self.s16(c + 0x312) != 0:         # 0x113b48: idle or held, charmed
            cf = self.u64(c + 0xA8)
            if cf & 0x800000000000000:                           # a player touched it
                self.vcall(c, 27, 1)
                cf = self.u64(c + 0xA8)
            self.w64(c + 0xA8, cf & 0xF7FFFFFFFFFFFFFF)
        if self.u64(c + 0xA8) & 0x8000000001000000 == 0x1000000 and self.s16(c + 0x232) == 0x14:
            w32(c + 0xC, u32(c + 0xC) | 0x4002)                  # 0x113bf8: an inactive corpse with the bit
            self.call('obj_delete', c)
        return 0

    def _follow_path(self, c, name):
        """0x112aac-0x112c68: a creature with creature flag 0x8000000 walks the points of
        the level path its PathName property names."""
        u32, w32 = self.u32, self.w32
        self.call('pathFollower_init', name, self.vec(c + 0x10))
        points = self.call('paths_findByName', name)
        index = self.s16(c + 0x58)
        if index == -1:
            index = s32(self.call('pointList_snapToNearest'))
        point = self.call('pointList_getPoint', points, index)
        if not point:
            return
        dx = C.sub(u32(c + 0x10), u32(point))
        dy = C.sub(u32(c + 0x14), u32(point + 4))
        if C.lt(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), 0x42400000):       # within 48: on to the next
            nxt = self.call('pointList_getPoint', points, index + 1)         # not tested for null
            self.wvec(c + 0x104, self.vec(nxt))
            self.wvec(c + 0x3B4, self.vec(c + 0x104))
            w32(c + 0x54, u32(c + 0x300) + 600)
            self.w16(c + 0x58, self.u16(nxt + 0x3C))
            return
        self.wvec(c + 0x104, self.vec(point))
        self.wvec(c + 0x3B4, self.vec(c + 0x104))
        mine, number = self.s16(c + 0x58), self.u8(point + 0x3C)
        if mine != number:
            w32(c + 0x54, u32(c + 0x300) + 600)
            self.w16(c + 0x58, self.u16(point + 0x3C))
            mine = self.s16(c + 0x58)
        if number == mine and self.s32(c + 0x54) < self.s32(c + 0x300):
            if not self.is_near_view(c + 0x10, 0x447A0000):      # 600 clock ticks late, nobody near: C4
                self.wvec(c + 0x10, self.vec(c + 0x3B4))
                self.call('obj_updateGridCell', c)

    def _follow_player(self, c):
        """0x112db8-0x113130: creature flags 0x400000 / 0x800000 (script followPlayer),
        reached only while the charm timer +0x312 is non-zero."""
        u32 = self.u32
        slot = self.s8(c + 0x5A)
        leader = 0
        if 0 <= slot < self.s32(G_NUM_PLAYERS):
            leader = self.player_obj(slot)
        if not leader or u32(leader + 0xC) & 8:                  # none, or dead: choose again
            self.w8(c + 0x5A, self.find_nearest_on_team(self.vec(c + 0x10), self.s8(c + 0x310), 0x43FA0000))
        else:
            self.wvec(c + 0x3B4, self.vec(leader + 0x10))        # home = 30 units ahead of / behind the leader
            leader = self.player_obj(self.s8(c + 0x5A))
            ox = C.mul(C.cos16(self.s16(leader + 0x38)), 0x41F00000)
            leader = self.player_obj(self.s8(c + 0x5A))
            oy = C.mul(C.sin16(self.s16(leader + 0x38)), 0x41F00000)
            if self.u64(c + 0xA8) & 0x400000:
                hx, hy = C.add(u32(c + 0x3B4), ox), C.add(u32(c + 0x3B8), oy)
            else:
                hx, hy = C.sub(u32(c + 0x3B4), ox), C.sub(u32(c + 0x3B8), oy)
            self.w32(c + 0x3B4, hx)
            self.w32(c + 0x3B8, hy)
            if self.is_away_from_home(c):
                self.wvec(c + 0x104, self.vec(c + 0x3B4))
        if s64(self.u64(c + 0xA8)) < 0:                          # active: nothing more
            return
        # 0x112f88: not active - try to appear near the leader, out of every player's sight
        home = self.vec(c + 0x3B4)
        origin = (home[0], home[1], C.add(home[2], 0x41300000))
        bearing = C.atan2_16(C.sub(u32(c + 0x14), home[1]), C.sub(u32(c + 0x10), home[0]))
        for i in range(32):
            offset = s16((i >> 1) << 11)
            if i & 1:
                offset = s16(-offset)
            angle = s16(bearing + offset)
            cs, sn = C.cos16(angle), C.sin16(angle)
            length = u32(G_FOLLOW_TELEPORT_DIST)
            direction = (C.mul(cs, length), C.mul(sn, length), C.mul(ZERO, length))
            t = self.call('terrain_raycast', u32(G_WORLD), origin, direction, 3, 0x3F8CCCCC)
            if C.lt(t, ZERO):
                t = ONE
            if not C.le(ONE, t):
                continue
            step = (C.mul(direction[0], t), C.mul(direction[1], t), C.mul(direction[2], t))
            spot = (C.add(u32(c + 0x3B4), step[0]), C.add(u32(c + 0x3B8), step[1]), C.add(u32(c + 0x3BC), step[2]))
            if self.call('players_anyWithinRadius', spot, 0x43E10000):
                continue
            self.wvec(c + 0x10, spot)
            self.call('obj_updateGridCell', c)
            self.call('obj_runEveryFrame', c)
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000000000000000)
            self.wvec(c + 0x104, self.vec(c + 0x3B4))
            self.clear_path(c)
            return

    def _burn_damage(self, c, flags):
        """0x11332c-0x113538: every 32nd frame a burning creature damages itself with one
        element record of id 0x15.  A monster gets 1..1; a player gets a level-scaled
        range and that costs ONE SHARED DRAW."""
        if flags & 0x40:
            skill = self.u32(G_SKILL_BURN)
            number = self.table_call('Skill', skill, 0x60, 11, 0, C.to_int(self.u32(G_LEVEL_MONSTER_LEVEL)), 0)
            base = C.mul(C.from_int(s32(number)), 0x3E199999)
            roll = self.draw()
            low = C.to_int(base)
            high = C.to_int(C.add(base, C.mul(C.mul(base, 0x3E4CCCCC), C.mul(C.from_int(roll), F_2M16))))
        else:
            low = high = 1
        self.call('damage_apply', c, c, 100000, 0, 0, 0x1180C040, ('elem', low & 0xFFFF, high & 0xFFFF), 0, ZERO, ZERO)

    def _chill(self, c):
        """0x113618-0x113734: the chill seconds +0x344 become the slow amount."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        left = C.sub(u32(c + 0x344), 0x3D888888)                 # 1/15 a tick
        w32(c + 0x344, left)
        if C.le(left, ZERO):
            w32(c + 0x344, ZERO)
            w8(c + 0x2FC, 0)
        flags = u32(c + 0xC)
        if flags & 8:
            w8(c + 0x2FC, 0)
        else:
            left = u32(c + 0x344)
            w8(c + 0x2FC, C.to_int(left) if C.le(left, F_60) else 0x3B)
        limit = C.sub(F_60, C.mul(u32(c + 0x60), F_60))          # cold resistance caps it
        if C.lt(limit, C.from_int(self.s8(c + 0x2FC))):
            w8(c + 0x2FC, C.to_int(limit))
        if flags & 0x40:                                         # a player: at most 30, and thaws faster
            if self.s8(c + 0x2FC) >= 0x1F:
                w8(c + 0x2FC, 0x1E)
            w32(c + 0x344, C.sub(u32(c + 0x344), 0x3D088888))
        elif self.call('creature_bossRank', c) and self.s8(c + 0x2FC) >= 0x10:
            w8(c + 0x2FC, 0xF)                                   # a boss or MiniBoss: at most 15
        elif self.s8(c + 0x2FC) >= 0x1F:
            w8(c + 0x2FC, 0x1E)                                  # everyone else: at most 30

    def _boss_meter(self, c, cf):
        """0x113980-0x113ae0: creature flag bit 31 and the three boss-meter globals, from
        the list of alive players LOCAL to this machine (FINDINGS E11)."""
        u32, w32 = self.u32, self.w32
        shown = False
        if s64(cf) < 0 and not u32(c + 0xC) & 8 and self.s32(G_LOCAL_ALIVE_COUNT) > 0:
            cx, cy, cz = self.vec(c + 0x10)
            i = 0
            while True:
                player = self.player_obj(self.s32(G_LOCAL_ALIVE_LIST + 4 * i))
                if player:
                    dx = C.sub(u32(player + 0x10), cx)
                    dy = C.sub(u32(player + 0x14), cy)
                    dz = C.sub(u32(player + 0x18), cz)
                    reach = C.mul(u32(c + 0x3C0), u32(c + 0x3C0))
                    if C.lt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)), reach):
                        shown = True
                        if not cf & 0x80000000:
                            self.w64(c + 0xA8, cf | 0x80000000)
                            w32(G_BOSS_METER_AUX, 0)
                            w32(G_BOSS_METER_MAX, 0)
                            w32(G_BOSS_METER_HP, 0)
                        else:
                            self.vcall(c, 19, G_BOSS_METER_NAME)
                            w32(G_BOSS_METER_MAX, C.to_int(u32(c + 0x22C)))
                            w32(G_BOSS_METER_HP, C.to_int(u32(c + 0x228)))
                        break
                i += 1
                if i >= self.s32(G_LOCAL_ALIVE_COUNT):
                    break
        if not shown:
            cf = self.u64(c + 0xA8)
            if cf & 0x80000000:
                w32(G_BOSS_METER_HP, 0)
                w32(G_BOSS_METER_MAX, 0)
                self.w64(c + 0xA8, cf & 0xFFFFFFFF7FFFFFFF)

    def update_spells(self, c, pos):
        """Creature_updateSpells 0x11a868, virtual slot 17 (creature, position): every
        attached spell's slot 2 with the position and the creature's facing."""
        node = self.call('iter_begin', c + 0x364, 0)
        while node:
            self.table_call('Spell', self.u32(node + 0xC), 0x14, 2, pos, self.s16(c + 0x38))
            node = self.call('iter_next')
        self.call('iter_end', 2)

    def find_nearest_on_team(self, pos, team, reach):
        """players_findNearestOnTeam 0x1124e0 (position, team; reach) -> slot or -1 (s8).
        Live player objects in slot order; a team of -1 accepts every player, otherwise
        the record's team byte +0x4c24 must match.  A later player at exactly the same
        distance replaces an earlier one (the test is `reach < distance` to reject)."""
        u32 = self.u32
        best = -1
        for slot in range(max(self.s32(G_NUM_PLAYERS), 0)):
            obj = self.player_obj(slot)
            if not obj or u32(obj + 0xC) & 8:
                continue
            dx = C.sub(pos[0], u32(obj + 0x10))
            dy = C.sub(pos[1], u32(obj + 0x14))
            dz = C.sub(pos[2], u32(obj + 0x18))
            dist = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
            if C.lt(reach, dist):
                continue
            if team != -1 and self.s8(G_PLAYERS + slot * REC_SIZE + 0x4C24) != team:
                continue
            reach, best = dist, slot
        return s8(best)

    def spawn_scavenger(self, c):
        """Creature_spawnScavenger 0x1125e0 (creature).

        For a corpse (state 0x14) whose top clip has finished (animation flag 0x80), on
        the tick its active bit is set and its was-active bit is clear, unless its ally
        handle +0x238 already holds something with creature flag 0x40000000000 or the
        object has flag 2: ONE SHARED DRAW for a bearing, then (when
        g_corpseScavengerKind is 1 or 2) a Critter is built 30 units away, turned to the
        heading with the longest clear ray, and linked at +0x238."""
        u32 = self.u32
        if self.s16(c + 0x232) != 0x14 or not self.u16(c + 0x11A) & 0x80:
            return
        if self.u64(c + 0xA8) & 0xC000000000000000 != 0x8000000000000000:
            return
        ally = self.handle_obj(c + 0x238)
        if ally and self.u64(ally + 0xA8) & 0x40000000000:
            return
        if u32(c + 0xC) & 2:
            return
        seed = (u32(G_RAND_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_RAND_SEED, seed)
        self.draws += 1
        turn = s32(seed) >> 16                                   # arithmetic shift: a signed 16-bit turn
        angle = self.s16(c + 0x38) + turn
        x = C.add(u32(c + 0x10), C.mul(C.cos16(angle), 0x41F00000))
        y = C.add(u32(c + 0x14), C.mul(C.sin16(angle), 0x41F00000))
        spot = (x, y, u32(c + 0x18))
        facing = C.atan2_16(C.sub(u32(c + 0x14), y), C.sub(u32(c + 0x10), x))
        kind = self.s32(G_SCAVENGER_KIND)
        critter = 0
        if kind in (1, 2):
            critter = self.call('pool_new', 0x448)
            if critter:
                self.call('Critter_ctor', critter, S_RAVEN if kind == 1 else S_RAT, spot, facing,
                          G_SCAVENGER_DATA[kind - 1])
        if not critter:
            return
        angle = self.s16(critter + 0x38)
        best, best_t = 0, ZERO
        for _ in range(32):
            direction = (C.mul(C.cos16(angle), 0x43700000), C.mul(C.sin16(angle), 0x43700000),
                         C.mul(0x3E4CCCCC, 0x43700000))
            origin = self.vec(critter + 0x10)
            origin = (origin[0], origin[1], C.add(origin[2], 0x41C00000))
            t = self.call('terrain_raycast', u32(G_WORLD), origin, direction, 0, ONE)
            if C.lt(t, ZERO) or C.lt(ONE, t):
                t = ONE
            if C.lt(best_t, t):
                best_t, best = t, angle
            if C.eq(best_t, ONE):
                break
            angle = s16(angle + 0x800)
        self.w16(critter + 0x38, best)
        self.call('handle_clear', c + 0x238)
        self.w32(c + 0x238, 0)
        self.call('handle_link', c + 0x238, critter, critter)

    # =====================================================================================
    # Creature_takeDamage 0x116638 (virtual slot 2) and Creature_processDamage 0x110d30
    # =====================================================================================
    def take_damage(self, c, attacker, flags, amount):
        """Creature_takeDamage 0x116638, virtual slot 2 (creature, attacker, flags; amount).

        Nothing for an inert creature (+0x231).  Otherwise the visual arc +0x3b0 becomes
        0x7fff - also for an IgnoreDamage creature (creature flag 0x1000000000000), which
        then only has its five second-timers zeroed.  Else: flags ORed into +0x2dc, the
        frame stamped at +0x304; with an attacker and hit points still above zero the hit
        angle +0x2e0 and the last-attacker handle +0x2e4 are rewritten; then hit points
        -= amount and pending +0xc8 += amount.

        The handle is linked to whatever pointer it is given (FINDINGS ST3): the attacker,
        or - for an attacker with object flag 0x80 - the object behind the attacker's
        handle at +0x4c, or - for flag 0x10000000 - the object behind the creature's own
        effect-source handle +0x360.  Nothing tests that the pointer is still an object."""
        u32, w32 = self.u32, self.w32
        if self.s8(c + 0x231):
            return
        self.w16(c + 0x3B0, 0x7FFF)
        if self.u64(c + 0xA8) & 0x1000000000000:
            for off in (0x348, 0x344, 0x340, 0x350, 0x34C):
                w32(c + off, 0)
            return
        w32(c + 0x304, u32(G_SIM_FRAME))
        w32(c + 0x2DC, u32(c + 0x2DC) | flags)
        if attacker and C.lt(ZERO, u32(c + 0x228)):
            angle = C.atan2_16(C.sub(u32(c + 0x10), u32(attacker + 0x10)), C.sub(u32(c + 0x14), u32(attacker + 0x14)))
            self.w16(c + 0x2E0, 0x4000 - angle)
            self.call('handle_clear', c + 0x2E4)
            who = attacker
            if u32(attacker + 0xC) & 0x80:
                node = u32(attacker + 0x4C)
                if node:
                    who = u32(node + 0xC)
            elif flags & 0x10000000:
                node = u32(c + 0x360)
                if node:
                    who = u32(node + 0xC)
            if who:
                self.call('handle_link', c + 0x2E4, who, who)
        w32(c + 0x228, C.sub(u32(c + 0x228), amount))
        w32(c + 0xC8, C.add(u32(c + 0xC8), amount))

    def process_damage(self, c, model):
        """Creature_processDamage 0x110d30 (creature, model).

        Consumes pending damage +0xc8 and the pending flags +0x2dc.  With pending damage:
        the hit effect, then - at hit points <= 0 - death; otherwise the knock-back speed
        and perhaps the hit reaction (state 0x12).  Without: the knock-back speed, and a
        hit reaction only when the flags are exactly 0x2000."""
        u32, w32 = self.u32, self.w32
        if not C.lt(ZERO, u32(c + 0xC8)):                        # 0x112320: no pending damage
            if self.s16(c + 0x232) != 0x14:
                flags = u32(c + 0x2DC)
                self._knockback_speed(c, flags, (0x42480000, 0x42960000, 0x42C80000, 0x431C4000))
                if flags == 0x2000 and self.s16(c + 0x232) != 0x12:
                    self._hit_reaction(c)
            w32(c + 0x2DC, 0)
            return
        if self.s32(G_NUM_PLAYERS) == 1:
            self.call('world_notifyObjectsNear', 0, self.vec(c + 0x10), c, 0x44160000)
        w32(c + 0xC8, 0)
        if self.s16(c + 0x232) == 0x14:                          # a corpse: the flags are NOT cleared
            return
        w32(c + 0xC, u32(c + 0xC) | 0x100)
        if u32(c + 0x2DC) & 0xD:
            self._hit_effect(c, model)
        if not C.le(u32(c + 0x228), ZERO):                       # 0x112250: survived
            if self.s16(c + 0x232) != 0x14:
                flags = u32(c + 0x2DC)
                self._knockback_speed(c, flags, (0x42C80000, 0x43160000, 0x43610000, 0x43BB8000))
                if not flags & 0x400000 and self.s16(c + 0x232) != 0x12:
                    self._hit_reaction(c)
            w32(c + 0x2DC, 0)
            return
        self._die(c, model)
        w32(c + 0x2DC, 0)

    def _knockback_speed(self, c, flags, speeds):
        """Knock-back speed +0x2e8 from the first set bit of 0x40000, 0x80000, 0x100000,
        0x200000; left alone when none is set."""
        for bit, speed in zip((0x40000, 0x80000, 0x100000, 0x200000), speeds):
            if flags & bit:
                self.w32(c + 0x2E8, speed)
                return

    def _hit_reaction(self, c):
        """0x112300 / 0x1123d4 - 0x11248c: whether the hit sends the creature to state 0x12.
        Own-generator draws only.  A MiniBoss reacts only with one player in the game and
        on an odd draw.  Pending flag bits 0x4380000 force the reaction; otherwise one
        draw in three does (a creature with creature flag 0x400 first gets a two-in-three
        chance on a draw of its own)."""
        if not (self.u32(c + 0xA8) ^ 1) & 1:                     # MiniBoss
            if self.s32(G_NUM_PLAYERS) >= 2:
                return
            if not self.obj_rand(c) & 1:
                return
        if not self.u32(c + 0x2DC) & 0x4380000:                  # read as the high half of a 64-bit load at +0x2d8
            if not (self.u64(c + 0xA8) & 0x400 and self.obj_rand(c) % 3 != 0):
                if self.obj_rand(c) % 3 != 0:
                    return
        self.vcall(c, 27, 0x12)

    def _gib(self, c, pos, variant, kind):
        """pool_new(0x268) and, when it gave a block, GutChunk_ctor.  `variant` None means
        one own-generator draw modulo 3, made only when there is a block."""
        chunk = self.call('pool_new', 0x268)
        if chunk:
            if variant is None:
                variant = self.obj_rand(c) % 3
            self.call('GutChunk_ctor', chunk, pos, variant, kind, ONE)
        return chunk

    def _hit_effect(self, c, model):
        """0x110df8-0x111470: the effect of a hit whose flags have any of 0xd, chosen by
        the chill timer and the body-material creature flags.  Own-generator draws only;
        the gib objects come from the pool."""
        u32 = self.u32
        bounds = (0, 0, 0, 0, 0, 0)
        if model:
            bounds = self.call('model_getBounds', model, M32)
        z0 = u32(c + 0x18)
        if C.le(0x41C80000, u32(c + 0x1C)):                      # radius >= 25: on the side the hit came from
            angle = self.s16(c + 0x2E0) + 0x7FFF
            x = C.add(u32(c + 0x10), C.mul(C.cos16(angle), C.mul(u32(c + 0x1C), 0x3F400000)))
            y = C.add(u32(c + 0x14), C.mul(C.sin16(angle), C.mul(u32(c + 0x1C), 0x3F400000)))
        else:
            x, y = u32(c + 0x10), u32(c + 0x14)
        z = C.add(z0, 0x42100000)
        top, bottom = s32(bounds[5]), s32(bounds[2])
        if top < 0x24 and s32(top - bottom) > 0:                 # a low model: half its height + 12
            z = C.add(C.add(z0, C.from_int(s32(top - bottom) >> 1)), 0x41400000)
        pos = (x, y, z)
        cf = self.u64(c + 0xA8)
        if C.lt(ZERO, u32(c + 0x344)) or cf & 0x4000:
            self.call('fx_spawn', 10, pos)
        elif cf & 0x8000:
            self.call('fx_spawn', 0xB, pos)
        elif cf & 0x10000:
            self.call('fx_spawn', 2, pos)
        elif cf & 0x20000:                                       # metal: a sound and fifty sparks
            text = self.call('libc_sprintf', S_HIT_METAL, None)
            entry = self.call('res_find', S_FX_LUMP, text)
            self.call('sound_playOnObject', entry, c, ONE)
            a = self.call('model_getAttachPoint', model, self.vec(c + 0x10), self.s16(c + 0x38), c + 0x114, 0, 0, ONE)
            b = self.call('model_getAttachPoint', model, self.vec(c + 0x10), self.s16(c + 0x38), c + 0x114, 1, 0, ONE)
            mid = tuple(C.mul(C.add(a[k], b[k]), HALF) for k in range(3))
            vel = [C.mul(C.cos16(self.s16(c + 0x38)), 0x41200000), C.mul(C.sin16(self.s16(c + 0x38)), 0x41200000),
                   0x41200000]
            for _ in range(50):
                while True:
                    r = []
                    for _k in range(3):
                        u = C.mul(C.from_int(self.obj_rand(c)), F_2M16)
                        r.append(C.sub(C.add(u, u), ONE))
                    if not C.lt(ONE, C.add(C.add(C.mul(r[0], r[0]), C.mul(r[1], r[1])), C.mul(r[2], r[2]))):
                        break
                for k in range(3):                               # the velocity accumulates over the fifty
                    vel[k] = C.add(vel[k], C.mul(r[k], 0x40A00000))
                self.call('particle_spawn', G_PARTICLE_METAL, mid, tuple(vel), ZERO)
        elif cf & 0x3000:
            kind = 5 if cf & 0x2000 else 3
            self.call('fx_spawn', 3 if cf & 0x2000 else 9, pos)
            self._gib(c, pos, 2, kind)
            if self.obj_rand(c) % 3 == 0:
                self._gib(c, pos, 2, kind)
            if C.le(u32(c + 0x228), ZERO) and self.obj_rand(c) % 3 == 0:
                self._gib(c, pos, 2, kind)
        elif (self.s32(G_DECAL_DETAIL) > 0 or self.s8(G_NETWORK_MODE)) and cf & 0x40000:
            self.call('fx_spawn', 0, pos)                        # blood: the option OR a net game (C6)
            if self.obj_rand(c) % 3 == 0:
                self._gib(c, pos, 2, 1)

    def _die(self, c, model):
        """0x111488-0x11224c: hit points are at or below zero."""
        u32, w32 = self.u32, self.w32
        w32(c + 0xC, u32(c + 0xC) | 9)
        for off in (0x340, 0x344, 0x348, 0x34C, 0x350):          # second-timers down to one second
            if C.lt(ONE, u32(c + off)):
                w32(c + off, ONE)
        flags = u32(c + 0x2DC)
        if flags & 0x20 or C.lt(ONE, u32(c + 0x340)):            # (the burn test cannot hold after the clamp)
            w32(c + 0xC, u32(c + 0xC) | 0x2000000)
        elif flags & 0x10 and model:
            self.call('fx_disintegrateModel', c, model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38), 0,
                      u32(c + 0xDC), u32(c + 0xE0))
            flags = u32(c + 0x2DC)
        elif flags & 0x2000000 and model:
            self.call('fx_disintegrateModel', c, model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38), 1,
                      u32(c + 0xDC), u32(c + 0xE0))
            flags = u32(c + 0x2DC)
        else:
            flags = self._shatter_or_gib(c, model, flags)
        self._knockback_speed(c, flags, (0x42C80000, 0x43160000, 0x43480000, 0x439C4000))
        self.vcall(c, 27, 0x14)                                  # 0x111de8: the class's set-state
        w32(c + 0xC, u32(c + 0xC) | 0x2000)
        if self.call('obj_getPropInt', c, S_DEAD, 0):
            self.call('anim_snapTopToEnd', c + 0x114)
            return
        if self.u64(c + 0xA8) & 0x100000000:                     # revived or loaded dead: nothing is awarded
            return
        self._award_kill(c)

    def _shatter_or_gib(self, c, model, flags):
        """0x1115d0-0x111d54: ice shatter or gibs.  Returns the pending flags as the code
        holds them afterwards.  Own-generator draws, pool blocks, and - for decals and
        the three effect positions only - the third generator 0x404468."""
        u32 = self.u32
        if (u32(c + 0xA8) ^ 1) & 1:                              # not a MiniBoss
            cf = self.u64(c + 0xA8)
            if not cf & 0x20000000 and C.lt(ZERO, u32(c + 0x344)) and model:
                if not self.obj_rand(c) & 7:                     # frozen: one death in eight shatters
                    self.call('fx_shatterToLooseIce', model, c + 0x114, self.vec(c + 0x10), self.s16(c + 0x38),
                              c + 0x320, u32(c + 0x1C), u32(c + 0xDC), u32(c + 0xE0))
                    return self._remove_body(c)
                flags = u32(c + 0x2DC)
        cf = self.u64(c + 0xA8)
        if cf & 0x20000001 or not flags & 0x800 or not flags & 0x3C0000:
            return flags
        if not cf & 0x3000:
            if not cf & 0x40000 or self.s32(G_DECAL_DETAIL) <= 0 or self.s8(G_NETWORK_MODE):
                return flags                                     # blood gibs: the option, and offline only (C6)
        pos = self.vec(c + 0x10)
        if self.s32(G_DECAL_DETAIL) > 0:                         # decals and effects: the third generator
            seed = (u32(G_SEED3) * 0x19660D + 0x3C6EF35F) & M32
            angle = s32(seed) >> 16
            seed = (seed * 0x19660D + 0x3C6EF35F) & M32
            self.w32(G_SEED3, seed)
            kind = ((seed >> 16) & 1) + (4 if cf & 0x2000 else 7 if cf & 0x1000 else 1)
            self.call('decal_add', pos, angle, kind, 0, 0x42300000)
            for _ in range(3):
                seed = u32(G_SEED3)
                while True:
                    r = []
                    for _k in range(3):
                        seed = (seed * 0x19660D + 0x3C6EF35F) & M32
                        u = C.mul(C.from_int(seed >> 16), F_2M16)
                        r.append(C.sub(C.add(u, u), ONE))
                    if not C.lt(ONE, C.add(C.add(C.mul(r[0], r[0]), C.mul(r[1], r[1])), C.mul(r[2], r[2]))):
                        break
                cf = self.u64(c + 0xA8)
                self.w32(G_SEED3, seed)
                base = (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x42100000))
                spot = tuple(C.add(C.mul(r[k], 0x41200000), base[k]) for k in range(3))
                self.call('fx_spawn', 9 if cf & 0x1000 else 3 if cf & 0x2000 else 1, spot)
        for count, first_kind, speed, lift, spread, turn in ((2, 0, 0x42A00000, 0x41A00000, 16000, 0xE0C0),
                                                             (4, 1, 0x42480000, 0x41200000, 40000, 0xB1E0)):
            for _ in range(count):
                cf = self.u64(c + 0xA8)
                chunk = self._gib(c, pos, None, 2 if cf & 0x1000 else 5 if cf & 0x2000 else first_kind)
                if not chunk:
                    continue
                push = C.add(C.mul(C.mul(C.from_int(self.obj_rand(c)), F_2M16), speed), lift)
                angle = s16(turn + self.obj_rand(c) % spread)
                heading = self.s16(c + 0x2E0) + angle
                self.w32(chunk + 0xFC, C.add(C.mul(u32(chunk + 0xFC), F_0_3), C.mul(C.cos16(heading), push)))
                heading = self.s16(c + 0x2E0) + angle
                self.w32(chunk + 0x100, C.add(C.mul(u32(chunk + 0x100), F_0_3), C.mul(C.sin16(heading), push)))
                self.call('PhProp_initPhysics', chunk, 0x12)
        return self._remove_body(c)

    def _remove_body(self, c):
        """0x111d38: the body is gone - object flags 0x4002, creature flag 0x20000000000."""
        cf = self.u64(c + 0xA8)
        flags = self.u32(c + 0x2DC)
        self.w32(c + 0xC, self.u32(c + 0xC) | 0x4002)
        self.w64(c + 0xA8, cf | 0x20000000000)
        return flags

    def _award_kill(self, c):
        """0x111e3c-0x11224c: the kill call-outs, in order: the skill-0x3b object for the
        killer (one OWN-generator draw), then experience for every player."""
        u32, w32 = self.u32, self.w32
        players = self.s32(G_NUM_PLAYERS)
        levels = 0
        for slot in range(max(players, 0)):
            levels += self.s8(G_PLAYERS + slot * REC_SIZE + 0x59)
        value = C.powf(C.div(u32(c + 0xD8), C.from_int(levels)), 0x3FB33333)
        exp = C.to_int(value)
        killer = -1
        node = u32(c + 0x2E4)
        if node:
            who = u32(node + 0xC)
            if self.player_obj(0) == who:
                killer = 0
            else:
                for slot in range(1, self.s32(G_NUM_PLAYERS)):
                    if self.player_obj(slot) == who:
                        killer = slot                            # the last matching slot wins
        if killer != -1:
            rank = self.call('player_getSkillRank', killer, 0x3B)
            chance = C.mul(self.call('SkillLifeTap_getStat0Fraction', u32(G_SKILL_ONKILL), rank), 0x47800000)
            if C.lt(C.from_int(self.obj_rand(c)), chance):
                ball = self.call('pool_new', 0xB8)
                if ball:
                    self.call('OniBall_ctor', ball, self.vec(c + 0x10), self.s16(c + 0x38), c, 0)
        exp = C.to_int(C.mul(C.from_int(exp), 0x3F400000))

        def cap(record):
            level = self.s8(record + 0x59)
            if level < 0x50:
                return self.s32(G_EXP_TABLE + 4 * level + 4) - self.s32(G_EXP_TABLE + 4 * level)
            return self.s32(G_EXP_TABLE + 4 * level)

        def class0_mana(record):
            mana = C.add(u32(record + 0xC0), C.mul(u32(c + 0x22C), 0x3D088888))
            w32(record + 0xC0, mana)
            if C.lt(u32(record + 0xC4), mana):
                w32(record + 0xC0, u32(record + 0xC4))

        if self.s32(G_NUM_PLAYERS) < 2:                          # 0x112160: one player
            slot = 0
            while slot < self.s32(G_NUM_PLAYERS):
                record = G_PLAYERS + slot * REC_SIZE
                if C.lt(ZERO, u32(record + 0xAC)):
                    exp = min(exp, cap(record))
                    self.call('player_giveExp', slot, exp)
                    if u32(record + 0x50) == 0:                  # class 0 gains mana whoever made the kill
                        class0_mana(record)
                slot += 1
            return
        share_base = C.from_int(exp)                             # 0x112004: several
        slot = 0
        while slot < self.s32(G_NUM_PLAYERS):
            record = G_PLAYERS + slot * REC_SIZE
            share = HALF if killer == -1 else 0x3F199999 if killer == slot else 0x3ECCCCCC
            amount = C.to_int(C.mul(share_base, share))
            if C.le(u32(record + 0xAC), ZERO):                   # a dead player gets half
                amount = C.to_int(C.mul(C.from_int(amount), HALF))
            self.call('player_giveExp', slot, min(amount, cap(record)))
            if u32(record + 0x50) == 0 and killer == slot:
                class0_mana(record)
            slot += 1

    # =====================================================================================
    # Creature_pickTarget 0x10ded0 (virtual slot 23), Creature_isEnemy 0x119328 (slot 20)
    # =====================================================================================
    def is_enemy(self, c, other):
        """Creature_isEnemy 0x119328, virtual slot 20 (creature, other) -> 0, 1 or 4.

        0 for nothing, itself, an object that is neither a monster nor a player (object
        flags 0x60), a dead one or a prediction copy (0x20008), a friendly one (creature
        flag 0x4000000) and one with creature flag 0x800.  Otherwise the two team values
        (virtual slot 37 of each) are compared: equal -> 0; different -> 4 when the other
        has the priority flag 0x100000000000, else 1.  The creature's OWN flags are not
        looked at."""
        if not other or other == c:
            return 0
        flags = self.u32(other + 0xC)
        if not flags & 0x60 or flags & 0x20008:
            return 0
        if self.u64(other + 0xA8) & 0x4000800:
            return 0
        if s32(self.vcall(c, 37)) == s32(self.vcall(other, 37)):
            return 0
        return 4 if self.u64(other + 0xA8) & 0x100000000000 else 1

    def pick_target(self, c, force):
        """Creature_pickTarget 0x10ded0, virtual slot 23 (creature, force).  No draws.

        Inert: nothing.  No-target timer running or friendly: the target handle is
        cleared.  A dead target (object flag 8) while the creature is not in state 0x14:
        set-state 0 and nothing else.  Otherwise the current target is kept while slot 20
        still calls it an enemy - except on a scan: every 32nd frame, staggered by the
        serial byte, or whenever `force` is non-zero.

        The scan starts from nothing: a box of +-HomeRange around the creature (all three
        axes) is queried with g_excludeMask forced to 8 for that one call, and the best
        candidate of that list is the result.  A current target that the list does not
        return is dropped.  Score = slot 20 (+1 last attacker, +1 current target); the
        higher score wins, then the smaller 2-D distance (which starts at HomeRange
        squared, so with equal scores a candidate at or beyond HomeRange never wins).
        With `force` and a current target, every OTHER candidate is taken whatever its
        score and the current target is not taken once anything has been: a forced scan
        ends on the last other enemy in list order.  A taken candidate must still pass
        the leash test."""
        u32 = self.u32
        if self.s8(c + 0x231):
            return
        if self.s16(c + 0x316) or self.u64(c + 0xA8) & 0x4000000:
            self.call('handle_clear', c + 0x234)
            self.w32(c + 0x234, 0)
            return
        node = u32(c + 0x234)
        if self.s16(c + 0x232) != 0x14 and node and u32(u32(node + 0xC) + 0xC) & 8:
            self.vcall(c, 27, 0)
            return
        best = 0
        if node and self.vcall(c, 20, u32(node + 0xC)):
            best = u32(u32(c + 0x234) + 0xC)
        if not (u32(G_SIM_FRAME) ^ self.s8(c + 0x230)) & 0x1F or force:
            reach = u32(c + 0x3C0)
            x, y, z = self.vec(c + 0x10)
            low = (C.sub(x, reach), C.sub(y, reach), C.sub(z, reach))
            high = (C.add(x, reach), C.add(y, reach), C.add(z, reach))
            saved = u32(G_EXCLUDE_MASK)
            self.w32(G_EXCLUDE_MASK, 8)
            found = self.call('world_collectObjectsInBox', low, high, 0xC0)
            self.w32(G_EXCLUDE_MASK, saved)
            best, best_score = 0, 0
            best_d2 = C.mul(u32(c + 0x3C0), u32(c + 0x3C0))
            for other in found:
                score = s32(self.vcall(c, 20, other))
                if not score:
                    continue
                dy = C.sub(u32(c + 0x14), u32(other + 0x14))
                dx = C.sub(u32(c + 0x10), u32(other + 0x10))
                d2 = C.add(C.mul(dx, dx), C.mul(dy, dy))
                if self.handle_obj(c + 0x2E4) == other and u32(c + 0x2E4):
                    score += 1
                node = u32(c + 0x234)
                current = u32(node + 0xC) if node else 0
                if node and current == other:
                    score += 1
                if best_score < score or (score == best_score and C.lt(d2, best_d2)):
                    take = True
                else:
                    take = bool(force and node and current != other)
                if best and force and node and current == other:
                    take = False
                if not take:
                    continue
                hx, hy = u32(c + 0x3B4), u32(c + 0x3B8)          # the leash
                oy = C.sub(hy, u32(other + 0x14))
                ox = C.sub(hx, u32(other + 0x10))
                from_home = C.add(C.mul(ox, ox), C.mul(oy, oy))
                if not s32(u32(G_SIM_FRAME) - 480) < self.s32(c + 0x304):       # not hit in the last 480 frames
                    if C.lt(C.mul(u32(c + 0x3C0), u32(c + 0x3C0)), from_home):  # candidate outside HomeRange of home
                        my = C.sub(u32(c + 0x14), hy)
                        mx = C.sub(u32(c + 0x10), hx)
                        if C.lt(C.add(C.mul(mx, mx), C.mul(my, my)), from_home):    # and farther out than I am
                            near = C.add(C.add(u32(other + 0x1C), u32(c + 0x1C)), F_60)
                            if C.lt(C.mul(near, near), d2):      # and not within 60 + both radii
                                continue
                best, best_d2, best_score = other, d2, score
        node = u32(c + 0x234)
        if not best or (node and u32(node + 0xC) != best):
            self.call('handle_clear', c + 0x234)
            self.w32(c + 0x234, 0)
        if best and not u32(c + 0x234):
            self.call('handle_link', c + 0x234, best, best)

    # =====================================================================================
    # Turning, the animation step, the collision step
    # =====================================================================================
    def turn_toward(self, c, mode, point):
        """Creature_turnToward 0x10bb08, virtual slot 26 (creature, mode, point) -> the
        signed 16-bit angle from the facing to the point BEFORE the turn (mode 1: to the
        opposite direction).  A damped spring on the angular velocity +0x110, limited to
        turn rate x 65536/60 per tick; the slow amount scales the step, not the spring."""
        u32 = self.u32
        limit = C.to_int(C.mul(u32(c + 0xB0), 0x44888888))
        target = C.atan2_16(C.sub(point[1], u32(c + 0x14)), C.sub(point[0], u32(c + 0x10)))
        if s32(mode) == 1:
            target += 0x8000
        facing = self.u16(c + 0x38)
        d = s16(target - facing)
        av = self.u16(c + 0x110) + C.to_int(C.mul(C.from_int(d), 0x3D4CCCCC))
        av -= C.to_int(C.mul(C.sqrt(0x3E4CCCCC), C.from_int(s16(av))))
        self.w16(c + 0x110, av)
        if limit < s16(av):
            self.w16(c + 0x110, limit)
        elif s16(av) < s32(-limit):
            self.w16(c + 0x110, -limit)
        k = self.slow_factor(c)
        if k is not None:
            facing += C.to_int(C.mul(C.from_int(self.s16(c + 0x110)), k))
        else:
            facing += self.u16(c + 0x110)
        self.w16(c + 0x38, facing)
        return d

    def _drowsy(self, c, value):
        """value x the SpellDrowsy fraction while the spell-speed timer +0x31a runs and
        such a spell is attached (0x1162ec, 0x114acc)."""
        if self.s16(c + 0x31A) > 0:
            spell = self.call('creature_findSpellByType', c, self.call('SpellDrowsy_typeinfo'))
            if spell:
                value = C.mul(value, self.call('SpellDrowsy_getStat3Fraction', spell))
        return value

    def step_anim(self, c, speed):
        """Creature_stepAnim 0x1162b0 (creature; speed) -> the event bits of anim_advance,
        0 for a creature that is not active (creature flag bit 63).

        The speed is scaled in state 3 (the chase) by player_speedScale(-1), by a Drowsy
        spell, and by the slow amount.  The root motion anim_advance leaves at +0xbc,
        +0xc0 (model space) is scaled by +0xdc, turned into world space with the facing,
        and scaled by the slow amount a second time; the root yaw +0xc4 is multiplied by
        the INTEGER part of (60 - slow)/60, which is 0 for any slow amount (AN1).  A
        creature that is not active keeps and re-rotates whatever root motion is there."""
        u32, w32 = self.u32, self.w32
        events = 0
        if self.s16(c + 0x232) == 3:
            speed = C.mul(speed, self.call('player_speedScale', M32))
        speed = self._drowsy(c, speed)
        cf = self.u64(c + 0xA8)
        if s64(cf) < 0:
            sound = 0 if cf & 0x2000000 else c + 0x10            # the bit mutes the clip's sound cues
            if 1 <= self.u8(c + 0x2FC) <= 60:
                speed = C.mul(C.mul(speed, C.from_int(60 - self.s8(c + 0x2FC))), DT)
            events = self.call('anim_advance', c + 0x114, sound, c + 0xBC, c + 0xC4, speed)
        scale = u32(c + 0xDC)
        rx, ry = C.mul(u32(c + 0xBC), scale), C.mul(u32(c + 0xC0), scale)
        w32(c + 0xBC, rx)
        w32(c + 0xC0, ry)
        cs = C.cos16(self.s16(c + 0x38) - 0x4000)
        sn = C.sin16(self.s16(c + 0x38) - 0x4000)
        rx, ry = C.neg(u32(c + 0xBC)), u32(c + 0xC0)
        w32(c + 0xBC, C.add(C.mul(rx, cs), C.mul(ry, sn)))
        w32(c + 0xC0, C.sub(C.mul(rx, sn), C.mul(ry, cs)))
        k = self.slow_factor(c)
        if k is not None:
            yaw = self.s16(c + 0xC4)
            w32(c + 0xC0, C.mul(u32(c + 0xC0), k))
            w32(c + 0xBC, C.mul(u32(c + 0xBC), k))
            self.w16(c + 0xC4, yaw * C.to_int(C.mul(C.from_int(60 - self.s8(c + 0x2FC)), DT)))
        return events

    def move_by(self, c, vel):
        """Creature_moveBy 0x113c48 (creature, velocity) -> bits: 1 slid along terrain,
        2 touched an object, 4 landed.  0 at once for a hidden creature (inert bit 8).

        velocity + root motion x 60, facing += root yaw, all zeroed by the root timer;
        water bookkeeping; the terrain slide; push-out from up to 15 objects; gravity
        and ground.  One own-generator draw (its value unused) on entering water."""
        u32, w32 = self.u32, self.w32
        if self.u8(c + 0x231) & 8:
            return 0
        old = self.vec(c + 0x10)
        vx = C.add(vel[0], C.mul(u32(c + 0xBC), F_60))
        vy = C.add(vel[1], C.mul(u32(c + 0xC0), F_60))
        vz = vel[2]
        self.w16(c + 0x38, self.u16(c + 0x38) + self.u16(c + 0xC4))
        if self.s16(c + 0x314):
            vx = vy = vz = ZERO
        w32(c + 0x308, vx)
        w32(c + 0x30C, vy)
        self._w(c + 0xBC, 8, 0)
        self.w16(c + 0xC4, 0)
        self._water(c)
        dt = (C.mul(vx, DT), C.mul(vy, DT), C.mul(vz, DT))       # 0x113f84
        bits = 0
        normal = (0, 0, 0)
        if C.lt(0x3A83126E, C.add(C.mul(dt[0], dt[0]), C.mul(dt[1], dt[1]))):
            hit, normal = self.call('world_slideMove', c + 0x10, dt, 3, 1, u32(c + 0x1C))
            self.call('obj_updateGridCell', c)
            bits = 1 if hit else 0
        r = u32(c + 0x1C)
        x, y, z = self.vec(c + 0x10)
        low = (C.sub(x, r), C.sub(y, r), C.sub(z, 0x447A0000))
        high = (C.add(x, r), C.add(y, r), C.add(z, 0x447A0000))
        found = self.call('world_collectObjectsInBox', low, high, 0x10)
        top = C.add(u32(c + 0x18), u32(c + 0x20))
        stand = 0xC7C35000                                       # the highest thing stood on, from -100000
        touched = []
        radius = u32(c + 0x1C)
        for other in found:
            oflags = u32(other + 0xC)
            if oflags & 1 or other == c:
                continue
            dx = C.sub(u32(c + 0x10), u32(other + 0x10))
            dy = C.sub(u32(c + 0x14), u32(other + 0x14))
            oradius = u32(other + 0x1C)
            dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
            if not C.lt(C.add(dist, 0x3A83126E), C.add(radius, oradius)):
                continue
            cflags = u32(c + 0xC)
            push = True
            if (oflags | cflags) & 0x10:                         # one of the two can be stood on
                oz = u32(other + 0x18)
                if C.lt(top, C.add(oz, 0x40400000)):
                    continue                                     # it is above my head
                otop = C.add(oz, u32(other + 0x20))
                if C.lt(otop, u32(c + 0x18)):
                    continue                                     # it is below my feet
                if C.lt(C.sub(otop, u32(c + 0x18)), 0x40A00000):     # a step of less than 5: stand on it
                    if oflags & 0x200:
                        push = False
                    elif not cflags & 0x400:
                        if C.lt(stand, otop):
                            stand = otop
                        continue
            if push and not oflags & 0x200 and not cflags & 0x401 and C.lt(0x3A83126E, C.fabs(dist)):
                k = C.div(C.sub(C.add(radius, oradius), dist), dist)
                self.call('world_slideMove', c + 0x10, (C.mul(dx, k), C.mul(dy, k), 0), 3, 0, radius)
                self.call('obj_updateGridCell', c)
            bits |= 2
            self.vcall(other, 6, c)
            touched.append(other)
            if u32(c + 0xC) & 0x8000000 and u32(c + 0x234) and self.handle_obj(c + 0x234) == other:
                radius = u32(c + 0x1C)
                break                                            # settling: stop at the target
            radius = u32(c + 0x1C)
        ground = self.call('terrain_heightBelow', u32(G_WORLD), self.vec(c + 0x10), radius)
        if C.lt(ground, stand):
            ground = stand
        fall = C.sub(u32(c + 0x30), 0x410FFFFF)
        w32(c + 0x30, fall)
        z = C.add(u32(c + 0x18), C.mul(fall, DT))
        w32(c + 0x18, z)
        if C.le(C.sub(z, 0x3C23D70A), ground):
            w32(c + 0x18, ground)                                # snapped to the ground even while rising
            if C.lt(fall, ZERO):
                w32(c + 0x30, ZERO)
                bits |= 4
        if bits & 1:
            self.vcall(c, 10, normal)
        if bits & 2:
            if u32(c + 0xC) & 0x8000000:
                self.wvec(c + 0x10, old)
                self.call('obj_updateGridCell', c)
            self.vcall(c, 11, tuple(touched))
        return bits

    def _water(self, c):
        """0x113d78-0x113f80: creature flag bit 61 (standing in water) and the splashes."""
        u32 = self.u32
        cf = self.u64(c + 0xA8)
        if cf & 0x100000:                                        # no water or dust effects for this one
            self.w64(c + 0xA8, cf & 0xDFFFFFFFFFFFFFFF)
            return
        if cf & 0x2000000000000000:
            wet = 1
            if not C.lt(u32(c + 0xB8), 0x3C23D70A) or not u32(G_SIM_FRAME) & 0xF:
                wet = self.call('water_disturb', u32(G_WORLD), self.vec(c + 0x10), 0x43960000, 0x41400000)
            if not wet:
                self.w64(c + 0xA8, self.u64(c + 0xA8) & 0xDFFFFFFFFFFFFFFF)
            return
        if (u32(G_SIM_FRAME) ^ self.s8(c + 0x230)) & 7:
            return
        if not self.call('water_test', u32(G_WORLD), self.vec(c + 0x10), 0, 0x41400000):
            return
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x2000000000000000)
        self.obj_rand(c)                                         # drawn, not used: the splash is always number 1
        text = self.call('libc_sprintf', S_SPLASH, 1)
        entry = self.call('res_find', S_FX_LUMP, text)
        self.call('sound_playOnObject', entry, c, 0x3F199999)
        self.call('water_disturb', u32(G_WORLD), self.vec(c + 0x10), 0x44BB8000, 0x41C00000)

    def settle(self, c):
        """Creature_settle 0x119e38 (creature): Creature_moveBy with no velocity under
        object flag 0x8000000 - gravity, push-out and touches, but the old x, y, z are
        restored when anything was touched.  Returns nothing meaningful."""
        self.w32(c + 0xC, self.u32(c + 0xC) | 0x8000000)
        self.move_by(c, (ZERO, ZERO, ZERO))
        self.w32(c + 0xC, self.u32(c + 0xC) & 0xF7FFFFFF)

    # =====================================================================================
    # Waypoints and Creature_moveTo 0x114510
    # =====================================================================================
    def get_waypoint(self, c, ahead=0):
        """Creature_getWaypoint 0x11a020 / Creature_getNextWaypoint 0x11a090 -> a vector:
        waypoint index +0x2bc (+1 for the next) as floats with z = -1.0, or all -1.0 when
        the index is 16 or more.  The stored end marker (-1, -1) therefore reads as
        x = -1.0 too."""
        index = self.s32(c + 0x2BC) + ahead
        if index < 16:
            return (C.from_int(self.s32(c + 0x23C + 8 * index)), C.from_int(self.s32(c + 0x240 + 8 * index)), MINUS_ONE)
        return (MINUS_ONE, MINUS_ONE, MINUS_ONE)

    def request_path(self, c, dest, kind, radius, distance):
        """Creature_requestPath 0x1164c0 (creature, destination, kind; radius, distance):
        one of four path requests into the waypoint buffer +0x23c (16 points); the index
        becomes 16 = search pending."""
        args = (self.u32(G_WORLD), self.vec(c + 0x10), dest, c, c + 0x23C, 0x10)
        if s32(kind) == 1:
            self.call('path_requestType2', *args, distance)
        elif s32(kind) == 2:
            self.call('path_requestType3', *args, distance)
        elif not C.eq(distance, ZERO):
            self.call('path_requestType1', *args, distance)
        else:
            self.call('path_requestToPoint', *args, radius)
        self.w32(c + 0x2BC, 16)

    def advance_waypoint(self, c, waypoint, dest, kind, radius, distance):
        """Creature_advanceWaypoint 0x11a108 (creature, waypoint in/out, destination, kind;
        radius, distance) -> (1, the next waypoint) or (0, x = y = -1.0) after asking for
        a new path (when the list has run out, or there was no current waypoint)."""
        index = self.s32(c + 0x2BC)
        waypoint = (MINUS_ONE, MINUS_ONE, waypoint[2])
        if index >= 16:
            return 0, waypoint
        if self.s32(c + 0x23C + 8 * index) != -1:
            self.w32(c + 0x2BC, index + 1)
            if index + 1 != 16:
                x = self.s32(c + 0x23C + 8 * (index + 1))
                if x != -1:
                    return 1, (C.from_int(x), C.from_int(self.s32(c + 0x240 + 8 * (index + 1))), waypoint[2])
        self.request_path(c, dest, kind, radius, distance)
        return 0, waypoint

    def clear_path(self, c):
        """Creature_clearPath 0x11a1e0: no waypoints, no flee point, no failures, the
        progress record at the current position and clock, no steering point."""
        w32 = self.w32
        w32(c + 0x244, M32)
        w32(c + 0xF8, MINUS_ONE)
        w32(c + 0xFC, MINUS_ONE)
        w32(c + 0x240, M32)
        w32(c + 0x23C, M32)
        w32(c + 0x248, M32)
        w32(c + 0x2BC, 0)
        w32(c + 0x2C4, 0)
        self.wvec(c + 0x2C8, self.vec(c + 0x10))
        w32(c + 0x2D4, self.u32(c + 0x300))
        self.wvec(c + 0x2EC, (0, 0, 0))

    def slot7_path_done(self, c, found):
        """Virtual slot 7, 0x11a260 (creature, found): the path search has answered."""
        self.w32(c + 0x2BC, 0)
        if found:
            self.w32(c + 0x2C4, 0)
        else:
            failures = self.u32(c + 0x2C4)
            self.w32(c + 0x240, M32)
            self.w32(c + 0x23C, M32)
            self.w32(c + 0x2C4, failures + 1)

    def is_away_from_home(self, c):
        """Creature_isAwayFromHome 0x10eed8 -> 0 or 1.  A path follower: more than 48
        units (2-D) from home.  A player follower: more than 120 (3-D).  Anyone else: more
        than HomeRange x 0.666 (3-D)."""
        u32 = self.u32
        cf = self.u64(c + 0xA8)
        dx = C.sub(u32(c + 0x10), u32(c + 0x3B4))
        dy = C.sub(u32(c + 0x14), u32(c + 0x3B8))
        if cf & 0x8000000:
            return 1 if C.lt(0x45100000, C.add(C.mul(dx, dx), C.mul(dy, dy))) else 0
        dz = C.sub(u32(c + 0x18), u32(c + 0x3BC))
        d2 = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
        if cf & 0xC00000:
            return 1 if C.lt(0x46610000, d2) else 0
        limit = C.mul(u32(c + 0x3C0), 0x3F2A7EF9)
        return 1 if C.lt(C.mul(limit, limit), d2) else 0

    def move_to(self, c, dest):
        """Creature_moveTo 0x114510 (creature, destination) -> 1 on arrival, else 0.

        Arrival, then the aim point (side-step / no waypoint / waypoints), the common
        ending (turn through slot 26, speed, Creature_moveBy along the FACING), then the
        stuck recovery.  One own-generator draw when a side-step starts; the last-resort
        teleport goes through world_findFreeSpot (a callback, which draws the shared
        seed)."""
        u32, w32 = self.u32, self.w32
        if C.eq(u32(c + 0x2EC), ZERO) and C.eq(u32(c + 0x2F0), ZERO):
            self.wvec(c + 0x2EC, dest)                           # no steering point yet
        dx = C.sub(dest[0], u32(c + 0x10))
        dy = C.sub(dest[1], u32(c + 0x14))
        dz = C.sub(dest[2], u32(c + 0x18))
        r2 = C.mul(u32(c + 0x1C), u32(c + 0x1C))
        d2 = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
        if C.lt(d2, r2):
            return 1
        frame, serial = u32(G_SIM_FRAME), self.s8(c + 0x230)
        if not (frame ^ serial) & 7 and C.lt(d2, C.add(r2, r2)):
            off = C.atan2_16(dy, dx) - self.s16(c + 0x38)        # not wrapped to 16 bits
            if abs(off) >= 0x4001:
                return 1                                         # close, and behind me
        aim = dest
        if self.s32(c + 0x300) < self.s32(c + 0x2D8):            # side-stepping
            aim = self.vec(c + 0x2EC)
        else:
            waypoint = self.get_waypoint(c)
            if C.eq(waypoint[0], MINUS_ONE):
                aim = self._steer_without_path(c, dest, waypoint)
            else:
                aim = self._steer_along_path(c, dest, waypoint)
        off = s16(self.vcall(c, 26, 0, aim))                     # 0x114aa8: the common ending
        speed = self._drowsy(c, u32(c + 0xB8))
        if abs(off) >= 0x3E81:                                   # turning through more than 16000: half speed
            w32(c + 0xBC, C.mul(u32(c + 0xBC), HALF))
            w32(c + 0xC0, C.mul(u32(c + 0xC0), HALF))
            speed = C.mul(u32(c + 0xB8), HALF)                   # (the Drowsy factor is lost here)
        k = self.slow_factor(c)
        if k is not None:
            speed = C.mul(speed, k)
        facing = self.s16(c + 0x38)
        vx = C.mul(C.cos16(facing), speed)
        self.move_by(c, (vx, C.mul(C.sin16(self.s16(c + 0x38)), speed), 0))
        # 0x114bb8: stuck recovery
        px = C.sub(u32(c + 0x10), u32(c + 0x2C8))
        py = C.sub(u32(c + 0x14), u32(c + 0x2CC))
        if self.s8(G_CUTSCENE_ACTIVE) or C.lt(0x41800000, C.add(C.mul(px, px), C.mul(py, py))):
            self.wvec(c + 0x2C8, self.vec(c + 0x10))             # progress (more than 4 units), or a cutscene
            w32(c + 0x2D4, u32(c + 0x300))
            return 0
        until, clock = self.s32(c + 0x2D8), self.s32(c + 0x300)
        if until < clock and C.lt(C.from_int(u32(c + 0x2D4)), C.sub(C.from_int(clock), 0x41F00000)):
            w32(c + 0x2D8, clock + 30)                           # 30 ticks without progress: side-step
            angle = s16(self.u16(c + 0x38) - 0x8000)
            angle = s16(angle + 0x2000) if self.obj_rand(c) & 1 else s16(angle - 0x2000)
            w32(c + 0x2EC, C.add(u32(c + 0x10), C.mul(C.cos16(angle), 0x44960000)))
            w32(c + 0x2F0, C.add(u32(c + 0x14), C.mul(C.sin16(angle), 0x44960000)))
            return 0
        if until == clock and self.s32(c + 0x2D4) < until - 300:     # a side-step ends, 300 ticks stuck
            spot, found = self.call('world_findFreeSpot', self.vec(c + 0x10), 0x48, C.to_int(u32(c + 0x1C)), 0)
            if s8(found):
                self.wvec(c + 0x10, spot)
                self.call('obj_updateGridCell', c)
        return 0

    def _steer_without_path(self, c, dest, waypoint):
        """0x1146c0-0x11488c: no current waypoint; returns the aim point."""
        u32 = self.u32
        frame, serial = u32(G_SIM_FRAME), self.s8(c + 0x230)
        if not (frame ^ serial) & 0x3F:                          # every 64th frame: is the straight line open?
            ray = (C.sub(dest[0], u32(c + 0x10)), C.sub(dest[1], u32(c + 0x14)), C.sub(dest[2], u32(c + 0x18)))
            if C.lt(self.call('Creature_probeThreeMovementRays', c, ray, 0), ONE):
                self.advance_waypoint(c, waypoint, dest, 0, u32(c + 0x1C), ZERO)
        off = C.atan2_16(C.sub(u32(c + 0x2F0), u32(c + 0x14)), C.sub(u32(c + 0x2EC), u32(c + 0x10))) \
            - self.s16(c + 0x38)
        if abs(off) < 1000:                                      # facing the steering point
            if not (u32(G_SIM_FRAME) ^ self.s8(c + 0x230)) & 7:
                self.wvec(c + 0x2EC, self.call('Creature_computeAvoidanceTarget', c, dest))
            else:
                self.wvec(c + 0x2EC, dest)
        else:
            sx = C.sub(u32(c + 0x10), u32(c + 0x2EC))
            sy = C.sub(u32(c + 0x14), u32(c + 0x2F0))
            ex = C.sub(u32(c + 0x10), dest[0])
            ey = C.sub(u32(c + 0x14), dest[1])
            if C.lt(C.add(C.mul(sx, sx), C.mul(sy, sy)), C.add(C.mul(ex, ex), C.mul(ey, ey))):
                self.wvec(c + 0x2EC, dest)                       # the destination is the farther of the two
        return self.vec(c + 0x2EC)

    def _steer_along_path(self, c, dest, waypoint):
        """0x114890-0x114aa4: a current waypoint exists; returns the aim point."""
        u32 = self.u32
        ray = (C.sub(dest[0], u32(c + 0x10)), C.sub(dest[1], u32(c + 0x14)), C.sub(dest[2], u32(c + 0x18)))
        if C.le(ONE, self.call('Creature_probeThreeMovementRays', c, ray, 0)):
            self.clear_path(c)                                   # the straight line is open: drop the path
            self.wvec(c + 0x2EC, dest)
            return self.vec(c + 0x2EC)
        for _ in range(16):
            nxt = self.get_waypoint(c, 1)
            to_next = (C.sub(nxt[0], waypoint[0]), C.sub(nxt[1], waypoint[1]))
            to_me = (C.sub(u32(c + 0x10), waypoint[0]), C.sub(u32(c + 0x14), waypoint[1]))
            if not C.eq(waypoint[0], MINUS_ONE):
                wx = C.sub(waypoint[0], u32(c + 0x10))
                wy = C.sub(waypoint[1], u32(c + 0x14))
                if not C.lt(C.add(C.mul(wx, wx), C.mul(wy, wy)), 0x44100000) \
                        and not self.s32(c + 0x2C0) < s32(u32(G_SIM_FRAME)):
                    if C.eq(nxt[0], MINUS_ONE):                  # farther than 24, not timed out, nothing after it
                        break
                    if not C.lt(ZERO, C.add(C.mul(to_next[0], to_me[0]), C.mul(to_next[1], to_me[1]))):
                        break                                    # and not passed yet
            self.w32(c + 0x2C0, u32(G_SIM_FRAME) + 30)
            _ok, waypoint = self.advance_waypoint(c, waypoint, dest, 0, u32(c + 0x1C), ZERO)
            if C.eq(waypoint[0], MINUS_ONE):
                break
        if C.eq(waypoint[0], MINUS_ONE):
            return dest
        return waypoint

    def move_to_target(self, c):
        """Creature_moveToTarget 0x1143e8 -> Creature_moveTo's result; with no target,
        set-state 0 and 0.  The destination is the point on the target's rim that faces
        the creature: target + (cos, sin)(bearing target -> creature) x (radius + 5)."""
        u32 = self.u32
        node = u32(c + 0x234)
        if not node:
            self.vcall(c, 27, 0)
            return 0
        tx, ty, tz = self.vec(u32(node + 0xC) + 0x10)
        bearing = C.atan2_16(C.sub(u32(c + 0x14), ty), C.sub(u32(c + 0x10), tx))
        ox = C.mul(C.cos16(bearing), C.add(u32(self.handle_obj(c + 0x234) + 0x1C), 0x40A00000))
        oy = C.mul(C.sin16(bearing), C.add(u32(self.handle_obj(c + 0x234) + 0x1C), 0x40A00000))
        return self.move_to(c, (C.add(tx, ox), C.add(ty, oy), tz))

    def move_to_dest(self, c):
        """Creature_moveToDest 0x119f38 -> 1, or 0 on the tick a new random destination was
        chosen.  Creature_moveTo to +0x104; on arrival set-state 0; after four failed path
        searches (and not a path follower) the path is cleared and the destination becomes
        Creature_randomPointNearHome(300)."""
        if self.move_to(c, self.vec(c + 0x104)):
            self.vcall(c, 27, 0)
        if self.u64(c + 0xA8) & 0x8000000 or self.s32(c + 0x2C4) < 4:
            return 1
        self.clear_path(c)
        self.wvec(c + 0x104, self.random_point_near_home(c, 300))
        return 0

    # =====================================================================================
    # Wander helpers
    # =====================================================================================
    def random_point_near_home(self, c, reach):
        """Creature_randomPointNearHome 0x110b58 (out, creature, reach) -> a point.

        reach is first lowered to int(HomeRange).  Home itself is returned when the
        creature is reach or more from home (3-D), or follows a player with creature flag
        0x400000 and is more than 120 away.  Otherwise up to ten tries, each two
        own-generator draws: home + ((draw & 2*reach) - reach) on x and on y - a bitwise
        AND, not a remainder - accepted when the ground there is within 12 units of the
        creature's z.  After ten failures the tenth point is returned anyway."""
        u32 = self.u32
        reach = s32(reach)
        if C.lt(u32(c + 0x3C0), C.from_int(reach)):
            reach = C.to_int(u32(c + 0x3C0))
        home = self.vec(c + 0x3B4)
        dx = C.sub(u32(c + 0x10), home[0])
        dy = C.sub(u32(c + 0x14), home[1])
        dz = C.sub(u32(c + 0x18), home[2])
        d2 = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
        if C.le(C.from_int(s32(reach * reach)), d2):
            return home
        if self.u64(c + 0xA8) & 0x400000 and C.lt(0x46610000, d2):
            return home
        point = home
        for _ in range(10):
            x = C.add(u32(c + 0x3B4), C.from_int(s32((self.obj_rand(c) & (reach << 1)) - reach)))
            y = C.add(u32(c + 0x3B8), C.from_int(s32((self.obj_rand(c) & (reach << 1)) - reach)))
            point = (x, y, u32(c + 0x3BC))
            ground = self.call('terrain_heightBelow', u32(G_WORLD), point, u32(c + 0x1C))
            z = u32(c + 0x18)
            if C.lt(C.sub(z, 0x41400000), ground) and C.lt(ground, C.add(z, 0x41400000)):
                break
        return point

    def pick_wander_dest(self, c):
        """Creature_pickWanderDest 0x119618 (creature): a new destination +0x104.  Nothing
        for a path follower, nor for a player follower that is away from its (moving)
        home; a player follower close to home wanders within 120, anyone else within
        300."""
        cf = self.u64(c + 0xA8)
        if cf & 0x8000000:
            return
        if cf & 0xC00000:
            if self.is_away_from_home(c):
                return
            point = self.random_point_near_home(c, 0x78)
        else:
            point = self.random_point_near_home(c, 0x12C)
        self.wvec(c + 0x104, point)

    def find_clear_heading(self, c, pos, angle, clockwise, factor):
        """creature_findClearHeading 0x10eaa8 (creature, position, angle, direction;
        length factor) -> a 16-bit angle.

        Up to 32 headings from `angle`, stepping +0x800 (direction non-zero) or -0x800.
        For each, three world rays of length factor x radius, 13 units up: from the
        position, and from one radius to each side of it.  A heading's score is the
        smallest of the three clear fractions (a miss, or anything above 1, counts as 1);
        the first heading that beats the best so far replaces it, and a score of exactly
        1.0 ends the search.  A side ray is not cast once the heading cannot win."""
        u32 = self.u32
        step = 0x800 if clockwise & 0xFF else -0x800
        angle = s16(angle)
        best, best_t = angle, ZERO
        world = u32(G_WORLD)

        def ray(origin):
            length = C.mul(factor, u32(c + 0x1C))
            direction = (C.mul(C.cos16(angle), length), C.mul(C.sin16(angle), length), ZERO)
            start = (origin[0], origin[1], C.add(origin[2], 0x41500000))
            t = self.call('world_raycast', world, start, direction, c, 0, 3, 0, length)
            if C.lt(t, ZERO) or C.lt(ONE, t):
                return ONE
            return t

        for _ in range(32):
            left = (C.add(pos[0], C.mul(C.cos16(angle - 0x4000), u32(c + 0x1C))),
                    C.add(pos[1], C.mul(C.sin16(angle - 0x4000), u32(c + 0x1C))), pos[2])
            right = (C.add(pos[0], C.mul(C.cos16(angle + 0x4000), u32(c + 0x1C))),
                     C.add(pos[1], C.mul(C.sin16(angle + 0x4000), u32(c + 0x1C))), pos[2])
            score = ray(pos)
            if C.lt(best_t, score):
                t = ray(left)
                if C.lt(t, score):
                    score = t
                if C.lt(best_t, score):
                    t = ray(right)
                    if C.lt(t, score):
                        score = t
                    if C.lt(best_t, score):
                        best_t, best = score, angle
            if C.eq(best_t, ONE):
                break
            angle = s16(angle + step)
        return best

    # =====================================================================================
    # Default bodies of virtual slots a subclass normally leaves alone
    # =====================================================================================
    def slot_empty(self, c, *args):
        """Slots 10 (moved into terrain) and 11 (touched objects): the base does nothing."""

    def slot6_touched(self, c, other):
        """Slot 6, 0x11a418 (creature, toucher): a player's touch sets creature flag bit 59."""
        if self.u32(other + 0xC) & 0x40:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x800000000000000)

    def slot27_set_state(self, c, state):
        """Slot 27, 0x3c2688 (creature, state): stores the AI state +0x232 and nothing
        else.  No filter, no timers, no handle: those are in Creature_filterState, which
        only the derived set-states call."""
        self.w16(c + 0x232, state)

    def slot30_stun(self, c, frames, flash):
        """Slot 30, Creature_stun 0x118a58 (creature, frames, flash): nothing for a boss or
        MiniBoss or a corpse; else the stun timer, set-state 0x13 and, with `flash`, the
        two flash colour quads."""
        if self.call('creature_bossRank', c) or self.s16(c + 0x232) == 0x14:
            return
        self.w16(c + 0x31C, frames)
        self.vcall(c, 27, 0x13)
        if flash:
            for off, value in ((0x90, 0x3A), (0x96, 0x48), (0x92, 0x9B), (0x94, 0x9A), (0x98, 0x3A), (0x9A, 0x9B),
                               (0x9C, 0x9A)):
                self.w16(c + off, value)

    def slot31_no_target(self, c, frames):
        """Slot 31, 0x118af8 (creature, frames): nothing in PvP mode A or for a boss or
        MiniBoss; else the no-target timer +0x316 and the target handle is cleared."""
        if self.u32(0x4F711C) or self.call('creature_bossRank', c):
            return
        self.w16(c + 0x316, frames)
        self.call('handle_clear', c + 0x234)
        self.w32(c + 0x234, 0)

    def slot35(self, c):
        """Slot 35, 0x118c50 -> int(g_levelMonsterLevel x 0.3)."""
        return C.to_int(C.mul(self.u32(G_LEVEL_MONSTER_LEVEL), F_0_3))

    def slot36(self, c):
        """Slot 36, 0x118c78 -> 4 for boss rank 1, 10 for rank 2, else 0."""
        rank = s32(self.call('creature_bossRank', c))
        return 4 if rank == 1 else 10 if rank == 2 else 0

    def slot37_team(self, c):
        """Slot 37, 0x3c2730 -> the team byte +0x310, signed."""
        return self.s8(c + 0x310)
