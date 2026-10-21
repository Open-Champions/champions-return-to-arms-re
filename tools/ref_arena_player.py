"""Bounded Player constructor contract for the offline arena fixture.

All values are independently expressed as field operations.  The constructor's
resource, Creature base, light, model and world services are call boundaries;
the fixture supplies a five-part model definition and zero-return services.
No executable or asset bytes are embedded here.

Section 2 (below ``constructor_fields``) composes the whole constructor chain
``GameObject_ctor`` -> ``Creature_ctor`` -> ``Player_ctor`` from the executed
base contracts it cites, and adds the arena replacement, destructor, spawn
protection and countdown-reset contracts executed by
``tools/difftest_arena_player.py``.
"""
import ref_arena_monsters as AM
import ref_core as C
import ref_skills_a as SA

CTOR = 0x1A1D28
SEED = 0x404464
RECORDS = 0x4D8AF0
RECORD_SIZE = 0x4C30
VTABLE = 0x511308

CALLS = (
    0x109D68, 0x148AF8, 0x14A4F0, 0x3B7EF0, 0x17365C,
    0x3B7EF0, 0x17365C, 0x355490, 0x1707B0, 0x1B2470,
    0x14F248, 0x183820, 0x1B6458, 0x3B60C0, 0x3B60C0, 0x1E72F8,
)


def constructor_fields(player, slot, model_part, pos=(0, 0, 0), res=0, base_flags=0):
    """Final direct stores for a zeroed, ordinary player with absent appearance parts.

    ``pos`` is the spawn position (the light record +0x4f8/+0x4fc/+0x500 copies it,
    0x1a1e48-0x1a1e50), ``res`` the answer of Player_ctor's own two res_find calls
    (stored at +0x544 and +0x550, 0x1a21bc / 0x1a21f4), ``base_flags`` the object flags
    the base constructors left (0x1a21f8 ORs 0x4040 into them).

    The base Creature constructor and external services are excluded.  The
    definition fixture points each of its five part cells at ``model_part``.
    Values are (store width, unsigned bit pattern).  Resource-produced handles
    are zero because this fixture gives the resource calls a zero answer.
    """
    p = {}
    def put(width, value, *offsets):
        for offset in offsets:
            p[player + offset] = (width, value)

    put(4, VTABLE, 0x48)
    put(4, 0, *(0x3D8 + 0x18 * i for i in range(5)))
    put(4, 0, 0x4B8, 0x588, 0x548, 0x558, 0x54C, 0x554)
    put(4, res, 0x544, 0x550)
    put(1, 0, 0x4D1, 0x4D0, 0x50D, 0x50C, 0x462, 0x3CC, 0x47B,
        0x47C, 0x47D, 0x47F, 0x481, 0x490, 0x463, 0x47A, 0x480)
    put(4, pos[0], 0x4F8)
    put(4, pos[1], 0x4FC)
    put(4, pos[2], 0x500)
    put(2, 0xBC, 0x4DE, 0x4D2, 0x4D4, 0x4D6, 0x4DA, 0x4DC)
    put(2, 0xFFC0, 0x4E0, 0x4D8)
    put(4, 0x43960000, 0x4EC, 0x4E4)
    put(4, 0x373A69DB, 0x4F0, 0x4E8)
    put(4, 0, 0x4F4, 0x64, 0x68, 0x6C, 0x60, 0x5C, 0x70, 0x74, 0x78,
        0x7C, 0x80, 0x84, 0x88, 0x8C, 0x45C, 0x458, 0x454, 0x484,
        0x488, 0x450, 0x6C)
    put(4, 0, *(0x36C + 4 * i for i in range(16)))
    put(4, 0xFFFFFFFF, 0x4A8)
    put(1, 0x30, 0x28)  # first byte of the authored model-name buffer
    put(4, base_flags | 0x4040, 0xC)
    put(4, slot, 0x3C8)
    put(4, 0x3FB33333, 0xB0)
    put(4, 0x41400000, 0x1C)
    put(4, 0x3FCCCCCC, 0x470)
    put(4, 2, 0x58C)
    put(1, 1, 0x461, 0x565)
    # idle-voice threshold: Player_run's formula with no draw (player-tick.md 1), 0x1a22ec
    put(2, (3600 + 2700 * slot) & 0xFFFF, 0x4B2)
    put(2, 0, 0x4AE)
    put(2, 0, 0x4B0)
    put(4, 0x3F400000, 0x18)

    # Five model-part cells receive the same animation setup. The cell's
    # +0x14/+0x1c words and +0x18/+0x20 bytes are the final values.
    part = {model_part + 0x14: (4, 0x3E800000),
            model_part + 0x1C: (4, 0x3F400000),
            model_part + 0x18: (1, 1), model_part + 0x20: (1, 1)}
    return p | {
        RECORDS + slot * RECORD_SIZE + 0x43D8: (4, player),
        RECORDS + slot * RECORD_SIZE + 0x4BC8: (1, 0),
    } | part


# ---------------------------------------------------------------------------
# 2. The whole chain and the arena replacement (executed, difftest sections 2-6)
# ---------------------------------------------------------------------------
GAMEOBJECT_CTOR, CREATURE_CTOR = 0x14CB10, 0x109D68
GAMEOBJECT_SPAN, CREATURE_SPAN, PLAYER_SPAN = (0x14CB10, 0x14CF84), (0x109D68, 0x10A230), (CTOR, 0x1A24B8)
PLAYER_DEF = 0x4ECC58          # class definition Player_ctor hands to Creature_ctor (observed argument)
CTOR_HP = 0x41500000           # 13.0, Creature_ctor's placeholder hit points from Player_ctor (observed f12)
MODEL_CELL, MODEL_TABLE = 0x4EBBB4, 0x5353E0
RES_FIND, HANDLE_LINK = 0x17365C, 0x1A1738
PROP_INT, PROP_STR = 0x14C880, 0x14F4C0
CREATURE_PROPS = ((PROP_INT, AM.S_WAIT), (PROP_INT, AM.S_HIDE), (PROP_STR, AM.S_SHOWNAME),
                  (PROP_INT, AM.S_DEAD), (PROP_INT, AM.S_HOMERANGE), (PROP_INT, AM.S_POINTBLANK),
                  (PROP_INT, AM.S_VISUALRANGE), (PROP_INT, AM.S_VISUALARC), (PROP_INT, AM.S_SCALE),
                  (PROP_INT, AM.S_MINIBOSS), (PROP_INT, AM.S_IGNOREDAMAGE), (PROP_STR, AM.S_LIGHT1),
                  (PROP_STR, AM.S_LIGHT2), (PROP_STR, AM.S_AMBIENT))


def lcg(seed):
    """The shared generator as documented (docs/arena-modes.md 3.1): new seed, 16-bit draw."""
    seed = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    return seed, seed >> 16


def grid_cell(x_pattern, y_pattern):
    """GameObject_ctor's grid cell for a position (ref_skills_a.gameobject_ctor)."""
    col = (C.s32(C.to_int(x_pattern)) + 0x3C00) >> 8
    row = (C.s32(C.to_int(y_pattern)) + 0x3C00) >> 8
    if 0 <= col < 0x78 and 0 <= row < 0x78:
        return SA.G_GRID_A + 4 * (row * 0x78 + col)
    return SA.G_OFF_GRID


def chain_writes(u32, player, pos, facing, slot, seed, part, serial):
    """Ordered (address, width, value) stores of the whole constructor chain for an
    ordinary arena player: a zero-filled block, no property list, no type name, the
    real Player class definition, every res_find answered with ``part`` and every
    property query answered 0.  ``u32`` reads the caller's memory before the call
    (the class definition's name list and generation).  Returns (writes, new seed,
    calls).  Composition, in execution order:

    * GameObject_ctor 0x14cb10 (docs/spec/object-system.md 2.2, ref_skills_a): defaults,
      the definition's names resolved when its generation word is stale, grid link,
      ``hide`` query, ONE shared draw into +0x44;
    * Creature_ctor 0x109d68 with type name 0 (ref_arena_monsters.creature_ctor,
      docs/spec/arena-monsters.md 2.1): base fields, serial byte, fourteen property
      queries, no Creature_setStats and therefore no own draw;
    * Player_ctor's own stores (``constructor_fields`` above).
    """
    out, calls = [], [(CREATURE_CTOR, player, 0, facing, PLAYER_DEF, 0), (GAMEOBJECT_CTOR, player, PLAYER_DEF, 0)]
    def w(addr, width, value):
        out.append((addr, width, value & ((1 << (8 * width)) - 1)))
    # GameObject_ctor
    for off in (0, 4, 8, 0xC, 0x34):
        w(player + off, 4, 0)
    w(player + 0x48, 4, SA.VT_GAMEOBJECT)
    w(player + 0x1C, 4, SA.F_24)
    w(player + 0x20, 4, SA.F_72)
    w(player + 0x28, 1, 0x19)
    w(player + 0x29, 1, 0x49)
    for k in range(3):
        w(player + 0x10 + 4 * k, 4, pos[k])
    w(player + 0x24, 4, PLAYER_DEF)
    if u32(PLAYER_DEF + 4) != u32(SA.G_LUMP_GENERATION):
        k = 8
        while u32(PLAYER_DEF + k):
            calls.append((RES_FIND, u32(PLAYER_DEF), u32(PLAYER_DEF + k)))
            w(PLAYER_DEF + k + 4, 4, part)
            k += 8
        w(PLAYER_DEF + 4, 4, u32(SA.G_LUMP_GENERATION))
    calls.append((HANDLE_LINK, grid_cell(pos[0], pos[1]), player + 8, player))
    calls.append((PROP_INT, player, SA.S_HIDE))
    w(player + 0x2C, 4, 0)
    seed, draw = lcg(seed)
    w(SEED, 4, seed)
    w(player + 0x44, 4, draw)
    # Creature_ctor, type name 0, no properties
    w(player + 0x50, 4, 0)
    w(player + 0x48, 4, AM.VT_CREATURE)
    w(player + 0x4C, 4, AM.VT_CREATURE_SUB)
    w(player + 0x119, 1, 8)
    for off in (0x2F4, 0x2EC, 0x2F0, 0x234, 0x238, 0x2E4, 0x360, 0x364):
        w(player + off, 4, 0)
    for k in range(3):
        w(player + 0x3B4 + 4 * k, 4, pos[k])
    w(player + 0x38, 2, facing)
    w(player + 0x22C, 4, CTOR_HP)
    w(player + 0x220, 8, 0xFFFFFFFFFFFFFFFF)
    w(player + 0xC, 4, 0x20)
    w(player + 0xC8, 4, 0)
    w(player + 0x228, 4, CTOR_HP)
    w(player + 0x23C, 4, 0xFFFFFFFF)
    w(player + 0x240, 4, 0xFFFFFFFF)
    for off in (0x2BC, 0x2C0, 0x2DC, 0xF4, 0x2C4, 0x300):
        w(player + off, 4, 0)
    for off in (0x110, 0x31C, 0x312, 0x316):
        w(player + off, 2, 0)
    w(player + 0x231, 1, 0)
    w(player + 0x2FC, 1, 0)
    w(player + 0x310, 1, 0xFF)
    w(player + 0x5A, 1, 0xFF)
    w(player + 0xA0, 1, 0)
    w(player + 0x3C, 4, pos[2])
    w(player + 0xDC, 4, AM.ONE)
    w(player + 0x58, 2, 0xFFFF)
    w(player + 0x3C4, 2, 600)
    for off in (0xB8, 0x304, 0xE0, 0x2D8):
        w(player + off, 4, 0)
    for off in (0x314, 0x31A, 0x318):
        w(player + off, 2, 0)
    w(AM.G_SERIAL_COUNTER, 1, serial + 1)
    w(player + 0x230, 1, serial)
    calls.extend((fn, player, name) for fn, name in CREATURE_PROPS)
    w(player + 0x3C0, 4, 0x447A0000)
    w(player + 0x3AC, 2, 300)
    w(player + 0x3AE, 2, 500)
    w(player + 0x3B0, 2, 0x4000)
    w(player + 0x2FA, 2, facing)
    # Player_ctor's own stores; constructor_fields gives final values, applied last.
    for addr, (width, value) in constructor_fields(player, slot, part, pos, part, 0x20).items():
        w(addr, width, value)
    w(MODEL_CELL, 4, MODEL_TABLE)
    return out, seed, calls


def final_bytes(writes):
    """Apply ordered stores; return {address: byte} of the final values."""
    result = {}
    for addr, width, value in writes:
        for i in range(width):
            result[addr + i] = (value >> (8 * i)) & 0xFF
    return result


# Player destructor, virtual slot 1 (old player at arena_startWave 0x306028 and player_respawn)
PLAYER_DTOR, CREATURE_DTOR, POOL_FREE = 0x1A1BB8, 0x117128, 0x150470
REBUILD_ALIVE = 0x1E72F8
HANDLE_CLEAR, ANIMSTATE_DTOR, LIGHT_DTOR = 0x1A1698, 0x171098, 0x14A490


def destructor(player, slot, flags):
    """Player slot-1 destructor 0x1a1bb8 (this, flags) with its callees as boundaries.

    Stores: vtable +0x48 = 0x511308; record +0x43d8 (object link) and the five words
    +0x43dc..+0x43ec = 0.  Calls, in order: game_rebuildAlivePlayers(g_players);
    handle_clear(+0x588); AnimState_dtor(+0x560, 2); light_dtor(+0x504, 2), (+0x4c8, 2);
    handle_clear(+0x4b8) and the five handle heads +0x438..+0x3d8 (descending);
    the Creature destructor 0x117128 with flags 0; then, only when flags bit 0 is set,
    a tail jump to pool_free(this).  No shared draw."""
    record = RECORDS + slot * RECORD_SIZE
    writes = [(player + 0x48, 4, VTABLE), (record + 0x43D8, 4, 0)]
    writes += [(record + 0x43DC + 4 * k, 4, 0) for k in range(5)]
    calls = [(REBUILD_ALIVE, RECORDS), (HANDLE_CLEAR, player + 0x588), (ANIMSTATE_DTOR, player + 0x560),
             (LIGHT_DTOR, player + 0x504), (LIGHT_DTOR, player + 0x4C8), (HANDLE_CLEAR, player + 0x4B8)]
    calls += [(HANDLE_CLEAR, player + 0x438 - 0x18 * k) for k in range(5)]
    calls.append((CREATURE_DTOR, player))
    if flags & 1:
        calls.append((POOL_FREE, player))
    return writes, calls


# Player_startSpawnProtection 0x1b8f28 (player_respawn calls it; arena_startWave does not)
SPAWN_PROTECTION = 0x1B8F28
NETWORK_BYTE, RECALL_COUNTDOWN = 0x402791, 0x41B51D
RESURRECT_SKILL, IS_SLOT_RAISED = 0x6E3010, 0x31270C
POOL_NEW, LIGHTEFFECT_CTOR, LIGHTEFFECT_SIZE = 0x14FDB8, 0x201BD8, 0xBC


PROTECT_SPAN = (SPAWN_PROTECTION, 0x1B9520)
PARTICLE_GUARD, PARTICLE_DEF, PARTICLE_DEF_CTOR = 0x4EF470, 0x865750, 0x18F3D0
SOUND_LUMP, SOUND_NAME, SOUND_PLAY = 0x535EF0, 0x536220, 0x214230
SAMPLE_COUNT, SAMPLE_POINT = 0x1799C8, 0x178E18


def spawn_protection(player, slot, network, recall, raised, light_block, guard, sound, model, samples):
    """Stores and calls of Player_startSpawnProtection 0x1b8f28 for one case.

    +0x4b4 (s16) = 90 when the network byte 0x402791 is set, else 60; then 1 when the
    recall countdown byte 0x41b51d is non-zero.  SkillResurrect_isSlotBeingRaised(skill
    0x6e3010, slot); object flag 0x2 is ORed into +0xc only when it answers 0.  Then
    pool_new(0xbc) and, only for a block, LightEffect_ctor 0x201bd8 (block first).  Then
    res_find(lump 0x535ef0, name 0x536220) and sound_playOnObject(that answer, 0; 1.0).
    The static particle definition 0x865750 is built once: when the guard word
    0x4ef470 is 0, particleDef_ctor(0x865750, ...) and guard = 1.  Then
    model_getSamplePointCount(model +0x544) and, for each sample point,
    model_getSamplePoint(model, player + 0x114, ...).  None of the three generators
    (0x404464, 0x404460, 0x404468) is drawn by this function's own code with these
    callees as boundaries; LightEffect's constructor is a boundary (a GameObject-derived
    constructor draws once, see ref_skills_a's module docstring)."""
    writes = [(player + 0x4B4, 2, 90 if network else 60)]
    if recall:
        writes.append((player + 0x4B4, 2, 1))
    if not raised:
        writes.append((player + 0xC, 4, None))  # read-modify-write: flags | 2
    calls = [(IS_SLOT_RAISED, RESURRECT_SKILL, slot), (POOL_NEW, LIGHTEFFECT_SIZE)]
    if light_block:
        calls.append((LIGHTEFFECT_CTOR, light_block))
    calls += [(RES_FIND, SOUND_LUMP, SOUND_NAME), (SOUND_PLAY, sound, 0)]
    if guard == 0:
        calls.append((PARTICLE_DEF_CTOR, PARTICLE_DEF))
        writes.append((PARTICLE_GUARD, 4, 1))
    calls.append((SAMPLE_COUNT, model))
    calls += [(SAMPLE_POINT, model, player + 0x114)] * samples
    return writes, calls


# game_resetTimers4f84a8 0x1ec2b8, called after Player_ctor by arena_startWave
RESET_TIMERS = 0x1EC2B8
DEAD_COUNTDOWNS, RESET_WORD = 0x4F84A8, 0x4F7194


def reset_timers():
    """Stores 0xf0 (240) in the halfword 0x4f7194 and in the four dead countdowns
    0x4f84a8 + 2 * slot (written slot 3 down to 0).  No calls, no draw."""
    return [(RESET_WORD, 2, 0xF0)] + [(DEAD_COUNTDOWNS + 2 * k, 2, 0xF0) for k in (3, 2, 1, 0)]


# arena_startWave 0x305ed4, one active slot's player replacement
START_WAVE, PICK_SPAWN = 0x305ED4, 0x3050A4
REPLACE_SITES = {'pick': 0x306000, 'dtor': 0x306028, 'new': 0x306030, 'ctor': 0x30604C, 'timers': 0x306090}


def start_wave_replacement(old, slot, spawn, facing):
    """Call order for one slot: arena_pickSpawnPoint(1, slot, out position, out facing);
    the old object's slot-1 destructor (old, 3); pool_new(0x590), which returns the old
    block again (object-system.md 2.2: the freed block heads its free list);
    Player_ctor(block, position, facing, slot, 0); game_resetTimers4f84a8()."""
    return [(PICK_SPAWN, 1, slot), (PLAYER_DTOR, old, 3), (POOL_NEW, 0x590),
            (CTOR, old, spawn, facing, slot, 0), (RESET_TIMERS,)]
