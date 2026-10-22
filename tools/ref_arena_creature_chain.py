"""Composed reference for the arena's real creature construction chain.

US SLUS_209.73 v2.00.  arena_spawnMonster asks world_createObject(name, spot, facing,
0x8e7230); the factory picks the pool size and the class constructor
(docs/spec/arena-match-probe.md, tools/difftest_monster_build.py).  This module composes
what the whole chain under that call does, from contracts that were each executed
before, plus two that are new in this round (balance_lookup and Creature_init, section
1 and 2 below; docs/spec/arena-creature-chain.md):

  class constructor (ref_arena_match_classes / ref_monsters_1 section 6)
    -> Creature_ctor 0x109d68 (ref_arena_monsters.creature_ctor, arena-monsters.md 2.1)
       -> GameObject_ctor 0x14cb10 (ref_skills_a.gameobject_ctor): ONE shared draw;
          the object's own generator +0x44 = that draw (seed >> 16)
       -> creature_bossRank 0x10d940, balance_lookup 0x223a4c,
          Creature_setStats 0x10a620 (ref_combat.boss_rank / monster_stats): one OWN
          draw for the hit-point roll
    -> the class's own draws, fields and service calls
    -> Creature_init 0x10a230 (section 2)

The result is what the difftest compares: shared seed, own seed and own draw count,
the ordered list of SERVICE calls (the bodies the test does not run), and final
fields.  No game data is stored here: class names, definitions, the balance records and
the executable's rules tables are read from the caller's memory at run time through
``u32`` / ``u8`` readers.  The only literals are Creature_init's property keys, as
docs/creatures.md and docs/script.md already list them, and addressed constants read
from the instructions cited.
"""
import ref_arena_match_classes as AC
import ref_combat as RC
import ref_core as C
import ref_monsters_1 as M1
import ref_skills_a as SA
import ref_weapon_holder as WH

SEED = 0x404464
G_SIM_FRAME = M1.G_SIM_FRAME
CLASSES = 0x5037F0
GOBLIN, MUMMY, SCORPION, ORC2, SNOBADGE = 3, 1, 0, 4, 25
KIND = {GOBLIN: AC.GOBLIN, MUMMY: AC.MUMMY}

# ---- services (bodies the chain difftest keeps as call boundaries) ------------------
POOL_NEW, RES_FIND, HANDLE_LINK, HANDLE_CLEAR = 0x14FDB8, 0x17365C, 0x1A1738, 0x1A1698
HIDE_MASK, ANIM_CLEAR, ANIM_PUSH, ANIM_START = 0x179550, 0x1707B0, 0x170838, 0x16CFE0
MODEL_BOUNDS = 0x179400
SERVICES = {POOL_NEW, RES_FIND, HANDLE_LINK, HANDLE_CLEAR, HIDE_MASK, ANIM_CLEAR,
            ANIM_PUSH, ANIM_START, MODEL_BOUNDS}

# ---- executed bodies (each with an earlier difftest, or new here) -------------------
REAL = {
    0x14F6C8: 'world_createObject', 0x159C94: 'world_objectFactory',
    0x159C20: 'str_prefixDiffers', 0x3B81A0: 'C library strcmp (factory)',
    0x109D68: 'Creature_ctor', 0x14CB10: 'GameObject_ctor', 0x1509D0: 'GameObject_rand',
    0x10D940: 'creature_bossRank', 0x223A4C: 'balance_lookup (new, section 1)',
    0x223914: 'balance_hashName (new, section 1)', 0x10A620: 'Creature_setStats',
    0x10A230: 'Creature_init (new, section 2)', 0x14C880: 'obj_getPropInt',
    0x14F4C0: 'obj_getPropStr', 0x3C2738: 'Creature_default_slot16',
    0x11BC18: 'WeaponShield_slot1', 0x11AFB0: 'Weapon1_slot1',
    0x118378: 'creature_setDefEntryParams', 0x14F2B8: 'obj_runEvery60',
    0x29A6F4: 'Mummy_setState', 0x10A9C0: 'Creature_filterState',
    0x1195E0: 'Creature_isNotRooted', 0x1195F0: 'Creature_isAttackReady',
    0x119608: 'Creature_isNotStunned', 0x3CF87C: 'SpellConeOfFire_typeinfo',
    0x11A6D0: 'creature_removeSpellByType', 0x11A710: 'creature_findSpellByType',
    0x3C2830: 'Spell_typeinfo', 0x2A14F8: 'Orc_pickHandParts', 0x2A169C: 'Orc_applyVariantFlags',
    0x3C1D68: 'Weapon1_slot4', 0x3C1DF8: 'Weapon1_slot7',
    WH.BUILD_ELEMENT: 'creature_buildElementDamage', 0x3C8690: 'Skill_default_slot11 (getStatTier2)',
}
LIBRARY = (0x3A5000, 0x3C0200)   # C library and software float, as the other probes follow

CONSTRUCTOR = {GOBLIN: 0x26A624, MUMMY: 0x298418, SCORPION: 0x2A4D68, ORC2: 0x2A0954, SNOBADGE: 0x244018}
# Orc2: the factory's model-set flag is 1 for names starting Orc2, giving class block
# 0x501df8 and weapon list 0x502090 (docs/monsters-2.md, Orc).  SnoBadge is Badger
# variant 1 (docs/monsters-2.md, Badger): definition 0x4fecf8 + 0xa0.
ORC2_WEAPON_LIST = 0x502090
DEFINITION = {GOBLIN: 0x500298, MUMMY: 0x501838, SCORPION: M1.DEF_SCORPION, ORC2: 0x501DF8,
              SNOBADGE: M1.DEF_BADGER + M1.DEF_BADGER_STEP}
VTABLE = {GOBLIN: 0x510260, MUMMY: 0x516E48, SCORPION: M1.VT_SCORPION, ORC2: 0x50FFD0,
          SNOBADGE: M1.VT_BADGER}
SIZE = {GOBLIN: 0x498, MUMMY: 0x480, SCORPION: 0x3D0, ORC2: 0x488, SNOBADGE: 0x3D0}
G_LUMP_GENERATION = SA.G_LUMP_GENERATION    # docs/spec/object-system.md 2.2

# ---- 1. balance_lookup 0x223a4c ------------------------------------------------------
# Records pointer and count, stored by balance_load 0x223998 (0x223a28 / 0x223a2c,
# Observed): the pointer is the entry's data + 2, the count its first halfword.
BALANCE_RECORDS, BALANCE_COUNT = 0x4FB5C4, 0x4FB5C8
PERCENT = 0x3C23D70A              # 0.01, the multiplier at 0x223b20-0x223b24


def balance_hash(name):
    """balance_hashName 0x223914 as docs/data-tables.md gives it (lower-case first)."""
    h = 0
    for ch in name:
        if 0x41 <= ch <= 0x5A:
            ch += 0x20
        if ch >= 0x80:
            ch -= 0x100          # signed chars
        h = (((h + ch) & 0xFFFF) * 0x401) & 0xFFFF
        h ^= h >> 6
    h = (h * 9) & 0xFFFF
    return (((h >> 11) ^ h) * 0x8001) & 0xFFFF


def balance_lookup(u32, name):
    """(found, (hp, armour, damage, attack, experience)) as float patterns.

    All five outputs are 1.0 first; a null name returns 0.  Otherwise the records at
    BALANCE_RECORDS (12 bytes: u16 hash, then five u16 percentages, loaded with lhu, so
    unsigned) are scanned in order for the first equal hash; each percentage becomes
    float(value) x 0.01.  No draw."""
    ones = (C.ONE,) * 5
    if not name:
        return 0, ones
    records, count = u32(BALANCE_RECORDS), C.s32(u32(BALANCE_COUNT))
    want = balance_hash(name)

    def u16(addr):
        word = u32(addr & ~3)
        return (word >> (8 * (addr & 2))) & 0xFFFF
    for k in range(max(count, 0)):
        rec = records + 12 * k
        if u16(rec) == want:
            return 1, tuple(C.mul(C.from_int(u16(rec + 2 * j)), PERCENT) for j in range(1, 6))
    return 0, ones


# ---- 2. Creature_init 0x10a230 ---------------------------------------------------------
HEIGHT_FLOOR = 0x42A80000         # 84.0, 0x10a2e0
CHANGE_BITS = 32


def creature_init_height(min_z, max_z):
    """+0x20 and byte +0x29 from model_getBounds' z outputs (ints, out[2] and out[5]):
    height = float(maxZ - minZ), at least 84.0; +0x29 = trunc(height) + 1."""
    height = C.from_int(C.s32(max_z - min_z))
    if C.lt(height, HEIGHT_FLOOR):
        height = HEIGHT_FLOOR
    return height, (C.to_int(height) + 1) & 0xFF


def creature_init_services(model):
    """Service calls of Creature_init for a creature that is not a MiniBoss, has an empty
    property list and runs outside a cutscene (byte 0x44fcd0 clear): slot 16 (real) gives
    the model; with one, model_getBounds(model, -1, six outputs).  Then 'dead', the 32
    'change%d' strings, the seven weapon-element properties and 'initScript' are asked
    for (real queries, all absent): no state, no hide mask, no holder slot, no script."""
    return [MODEL_BOUNDS] if model else []


CUTSCENE = 0x44FCD0               # byte; non-zero skips initScript (0x10a5bc)
SELECTED_OBJECT = 0x4039F8        # g_scriptSelectedObj around the script call (docs/script.md)
SCRIPT_RUN = 0x1ED694             # script_runByName
ANIM_SNAP_END = 0x170C80          # anim_snapTopToEnd(c + 0x114)
WEAPON_PROPS = (b'fireweapons', b'fireburstweapons', b'coldweapons', b'poisonweapons',
                b'shockweapons', b'diseaseweapons', b'nomagicweapons')   # holder slots 2..8
DEAD_FLAG = 1 << 32               # creature flag word +0xa8 |= 0x8000 << 17 (0x10a340-0x10a358)


def atoi(text):
    """obj_getPropInt's conversion: libc_atoi 0x3b3550 (strtol base 10): optional
    blanks and sign, then decimal digits; none gives 0."""
    text = text.lstrip(b' \t\n\v\f\r')
    sign = -1 if text[:1] == b'-' else 1
    text = text[1:] if text[:1] in (b'-', b'+') else text
    digits = b''
    for ch in text:
        if not 0x30 <= ch <= 0x39:
            break
        digits += bytes((ch,))
    return sign * int(digits) if digits else 0


def creature_init(cflags, model, props, holder, cutscene, bounds, hide_mask):
    """Creature_init 0x10a230 (creature), read from 0x10a230-0x10a61b.

    cflags     u64 at +0xa8 on entry
    model      what virtual slot 16 returns (the definition's model word)
    props      {lower-case key: value bytes} of the property list (+0x2c)
    holder     whether +0x50 holds a weapon holder
    cutscene   byte 0x44fcd0
    bounds     (minZ, maxZ) answer of model_getBounds
    hide_mask  the 64-bit answer of model_buildHideMask

    Returns (calls, fields).  calls are ('slot', k) for this creature's virtual slots
    that are services here (18, 27), ('holder', k) for holder slots, and service
    addresses with their key arguments.  fields {offset: (width, value)}.

      1. creature flag bit 0 (MiniBoss): virtual slot 18.
      2. model = slot 16; with a model: model_getBounds(model, -1, six int outputs);
         +0x20 = max(float(maxZ - minZ), 84.0); byte +0x29 = trunc(+0x20) + 1.
      3. obj_getPropStr 'dead' present: flags |= bit 32; slot 27 (c, 0x14);
         anim_snapTopToEnd(c + 0x114).
      4. mask = OR of 1 << k for every 'change<k>' present (k 0..31, obj_getPropStr);
         non-zero: +0xe8 = mask; +0x220 = model_buildHideMask(slot 16 model, mask).
      5. each weapon property present (obj_getPropInt non-zero) with a holder: holder
         slot 2..8 (holder, 0); slot 8 has a third argument 0.
      6. cutscene byte clear: obj_getPropStr 'initScript'; present: g_scriptSelectedObj
         = c, script_runByName(value), g_scriptSelectedObj = 0.
    No draw anywhere in the function's own code."""
    calls, fields = [], {}
    if cflags & 1:
        calls.append(('slot', 18))
    if model:
        calls.append((MODEL_BOUNDS, model))
        height, byte = creature_init_height(*bounds)
        fields[0x20] = (4, height)
        fields[0x29] = (1, byte)
    if b'dead' in props:
        cflags |= DEAD_FLAG
        calls += [('slot', 27, 0x14), (ANIM_SNAP_END,)]
    mask = 0
    for k in range(CHANGE_BITS):
        if b'change%d' % k in props:
            mask |= 1 << k
    if mask:
        fields[0xE8] = (4, mask)
        calls.append((HIDE_MASK, model, mask))
        fields[0x220] = (8, hide_mask)
    for k, key in enumerate(WEAPON_PROPS):
        value = props.get(key)
        if value and atoi(value) != 0 and holder:
            calls.append(('holder', 2 + k))
    if not cutscene and b'initscript' in props:
        calls.append((SCRIPT_RUN,))
    fields[0xA8] = (8, cflags)
    return calls, fields


# ---- 2b. the rare Mummy's weapon element (creature_buildElementDamage 0x1176e0) -------
MUMMY_HOLDER = 0x3D0


class _Reader:
    def __init__(self, u32):
        self.u32 = u32

    def s16(self, addr):
        return C.s16(self.u32(addr & ~3) >> (8 * (addr & 2)))


def element_damage(u32, kind, shared):
    """(new shared seed, {descriptor offset: halfword}) of creature_buildElementDamage for
    kinds 1-6, as ref_weapon_holder.build_element_damage: the four effect ids freed,
    a = the kind's Skill slot 11 (stat 0, trunc(monster level), cap 0), ONE SHARED DRAW d,
    v = trunc(float(a) x 0.2 x (float(d) x 2^-16)); slot 0 = (id, a, a + v, 0)."""
    ident, pointer = WH.ELEMENTS[kind]
    level = C.to_int(u32(0x4F714C))
    a = SA.Model.skill_stat_tier2(_Reader(u32), u32(pointer), 0, level, 0) & 0xFFFFFFFF
    shared, d = lcg(shared)
    v = C.to_int(C.mul(C.mul(C.from_int(a), WH.F_0_2), C.mul(C.from_int(d), WH.F_2M16)))
    out = {0x3C: 0xFFFF, 0x34: 0xFFFF, 0x2C: 0xFFFF}
    out.update({0x24: ident, 0x26: a & 0xFFFF, 0x28: (a + v) & 0xFFFF, 0x2A: 0})
    return shared, out


# ---- 3. the chain ----------------------------------------------------------------------
def lcg(state):
    state = (state * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    return state, state >> 16


def cstr(u8, addr):
    out = bytearray()
    while addr and u8(addr + len(out)):
        out.append(u8(addr + len(out)))
    return bytes(out)


class World:
    """The globals Creature_setStats reads (ref_combat.monster_stats), read from memory."""

    def __init__(self, u32, u8):
        self.monster_level = u32(0x4F714C)
        self.num_players = u32(0x4D8AE0)
        self.medal_mission = u32(0x4F713C)
        self.difficulty = u32(0x4F719C)
        self.level_name = cstr(u8, 0x44FE18).decode('latin1')


GOBLIN_FAMILY_BLOCKS = 0x500448


def entry_lookups(u32, block):
    """One res_find per named entry (+8, +0x10, ...) while the block's generation word
    (+4) differs from the lump generation; the block then takes the generation."""
    calls = []
    if u32(block + 4) != u32(G_LUMP_GENERATION):
        k = 8
        while u32(block + k):
            calls.append(RES_FIND)
            k += 8
    return calls


def gameobject_services(u32, definition):
    """GameObject_ctor's service calls: the definition's entry lookups, then
    handle_link (grid)."""
    return entry_lookups(u32, definition) + [HANDLE_LINK]


def chain(index, seed, u32, u8, tables, bounds=(0, 100), model=1):
    """What world_createObject(name of class ``index``, spot, facing, 0x8e7230) does.

    ``bounds`` is the (minZ, maxZ) answer of the model_getBounds service; ``model``
    whether the definition's model word is non-zero after the entries resolve.
    Returns dict(shared, own, own_draws, services, fields{offset: (width, value)}).
    """
    name_ptr = u32(CLASSES + 4 * index)
    name = cstr(u8, name_ptr)
    definition = DEFINITION[index]
    shared, draw = lcg(seed)
    own, own_draws = draw, 0
    services = [POOL_NEW]
    if index in (GOBLIN, ORC2):
        own_draws += 1                     # the pre-base draw on the zeroed block's 0
    services += gameobject_services(u32, definition)
    # Creature_ctor with a type name: setStats rolls hit points with one own draw
    found, pct = balance_lookup(u32, name)
    rank = RC.boss_rank(tables, True, name.decode('latin1'), '', 0)
    own, hp_draw = lcg(own)
    own_draws += 1
    stats = RC.monster_stats(tables, World(u32, u8), pct, rank, name.decode('latin1'), True, own_draw=hp_draw)
    fields = {0x48: (4, VTABLE[index]), 0x34: (4, name_ptr), 0x24: (4, definition),
              0x228: (4, stats['hp']), 0x22C: (4, stats['max_hp']),
              0xE4: (2, stats['armor'] & 0xFFFF), 0xD0: (2, stats['dmg_low'] & 0xFFFF),
              0xD2: (2, stats['dmg_high'] & 0xFFFF), 0xD4: (2, stats['attack'] & 0xFFFF),
              0xD8: (4, stats['exp_value']), 0x2C: (4, 0x8E7230), 0x232: (2, 0)}
    if index in KIND:
        calls, draws, class_fields, own, _ = AC.constructor(KIND[index], seed, own)
        own_draws += draws - (1 if index == GOBLIN else 0)   # the pre-base draw is counted above
        modifier = class_fields.pop(AC.RARE_MODIFIER, 0)
        for off, value in class_fields.items():
            if off in (0x28, 0x48):
                continue
            width = 2 if off == 0x232 else 4
            fields[off] = (width, value & ((1 << (8 * width)) - 1))
        fields[0x28] = (1, class_fields[0x28])
        if index == GOBLIN:
            # the family's own entry block, 0x500448 + 0x80 x family (+0x490, 0 for the plain
            # type), resolved under the same generation test (0x26a774-0x26a840, Observed)
            services += entry_lookups(u32, GOBLIN_FAMILY_BLOCKS) + [HIDE_MASK, ANIM_CLEAR, ANIM_PUSH]
        else:
            # Mummy_setState(c, 0) runs inside the constructor (AC.set_state): the filter
            # accepts 0 and clears the target handle; one own draw sets +0xf4 = clock + d % 120,
            # the clock +0x300 being 0 after Creature_ctor.
            own, first = lcg(own)
            own_draws += 1
            fields[0xF4] = (4, first % 120)
            services += [HIDE_MASK, ANIM_CLEAR, HANDLE_CLEAR, ANIM_START]
            if modifier:
                # after the hide mask: holder (+0x50 = c + 0x3d0) slot 7 (modifier 1, element
                # kind 5) or slot 4 (modifier 2, kind 2), hand 1 (0x298938-0x2989b0, Observed;
                # docs/monsters-2.md Mummy); the slot builds the element (weapon-holder.md 3.1)
                kind = 5 if modifier == 1 else 2
                shared, element = element_damage(u32, kind, shared)
                for off, value in element.items():
                    fields[MUMMY_HOLDER + 0x50 + off] = (2, value)
    elif index == ORC2:
        # Orc_ctor, the plain 'orc2' recruit (variant 0: no prefix matches), read at
        # 0x2a0d50-0x2a0e74, Orc_pickHandParts 0x2a14f8 and 0x2a11cc: own draw r picks one
        # model-variant bit; when r & 0x32 one more draw (even: a shield in hand 2);
        # pickHandParts' one draw; the idle clip's draw (% 3).  Resource lookups of the
        # weapon list block come after the base constructor.
        own, r = lcg(own)
        own_draws += 1
        if r & 1:
            bit = 0x1 if r & 2 else 0x2
        else:
            bit = 0x100 if r & 2 else (0x200 if r & 4 else 0x400)
        if r & 0x32:
            own, _ = lcg(own)
            own_draws += 1
        own, _ = lcg(own)                  # Orc_pickHandParts
        own, _ = lcg(own)                  # the idle clip, % 3
        own_draws += 2
        fields.update({0x28: (1, 0x28), 0xB8: (4, 0x42A00000), 0xB0: (4, M1.F_1_2),
                       0x1C: (4, 0x41900000), 0x47C: (4, 0), 0x478: (4, 0), 0xE8: (4, bit),
                       0x480: (4, ORC2_WEAPON_LIST)})
        services += entry_lookups(u32, ORC2_WEAPON_LIST) + [HIDE_MASK, ANIM_CLEAR, ANIM_PUSH]
    elif index == SNOBADGE:                # ref_monsters_1.Model.badger_ctor, variant 1; no own draw
        fields.update({0x1C: (4, M1.F_25), 0x28: (1, 0x28), 0xB8: (4, 0), 0xB0: (4, C.ONE),
                       0xB4: (1, 3), 0x3CC: (1, 1), 0x60: (4, C.ONE), 0x5C: (4, 0xBE999999),
                       0xDC: (4, M1.F_0_8), 0xE0: (4, 0xC1200000), 0xE8: (4, 0)})
        services += [HIDE_MASK, ANIM_CLEAR, ANIM_PUSH]
    else:                                  # Scorpion, ref_monsters_1.Model.scorpion_ctor
        own, d1 = lcg(own)
        own, d2 = lcg(own)
        own_draws += 2
        step = C.mul(C.from_int(d1 % 6), M1.F_0_05)
        scale = C.d2f(C.dadd(C.f2d(step), M1.D_0_75))
        fields.update({0x1C: (4, C.mul(M1.F_30, scale)), 0xDC: (4, scale), 0x3C8: (1, d2 & 1),
                       0x28: (1, 0x46), 0xB4: (1, 0x12), 0xB0: (4, M1.F_1_2), 0xB8: (4, 0),
                       0x64: (4, M1.F_0_4), 0xE8: (4, 0)})
        services += [HIDE_MASK, ANIM_CLEAR, ANIM_PUSH]
    fields[0xEC] = (4, u32(G_SIM_FRAME))   # every class stores g_simFrame at +0xec
    services.append(HANDLE_LINK)           # obj_runEvery60 links the run node
    services += creature_init_services(model)
    if model:
        height, byte = creature_init_height(*bounds)
        fields[0x20] = (4, height)
        fields[0x29] = (1, byte)
    fields[0x44] = (4, own)
    return dict(shared=shared, own=own, own_draws=own_draws, services=services, fields=fields,
                found=found, factors=pct, stats=stats)


# ---- 4. world_findFreeSpot 0x14acf8 ---------------------------------------------------
FREE_SPOT = 0x14ACF8
FREE_SPOT_TRIES = 50              # 0x14b0e0 slti 0x32
HEIGHT_STEP = 0x40C00000          # 6.0, 0x14af44
BOX_DEPTH = 0x47C35000            # 100000.0, 0x14adbc


def unit_ball_sample(seed):
    """Three shared draws d1..d3 per sample, p_k = (f(d) x 2^-16 + itself) - 1.0; samples
    repeat while 1.0 < (px^2 + py^2) + pz^2 (0x14ade8-0x14ae5c).  Returns (seed, p, draws)."""
    draws = 0
    while True:
        p = []
        for _ in range(3):
            seed, d = lcg(seed)
            draws += 1
            t = C.mul(C.from_int(d), C.TWO_M16)
            p.append(C.sub(C.add(t, t), C.ONE))
        if not C.lt(C.ONE, C.add(C.add(C.mul(p[0], p[0]), C.mul(p[1], p[1])), C.mul(p[2], p[2]))):
            return seed, p, draws


def free_spot(seed, center, rng_range, radius, any_height, blocked, height, box):
    """world_findFreeSpot(out, center, range, radius, ok out, anyHeight), read from
    0x14acf8-0x14b167.  ``blocked(point)`` and ``height(point)`` answer terrain_testFlag1 /
    terrain_height (float patterns, radius = float(radius)); ``box(min, max)`` answers
    world_collectObjectsInBox with [(x, y, object radius, object flags)].

    Per try (at most 50): a unit-ball sample; candidate (cx + px x range, cy + py x range)
    at the centre's z.  Rejected when terrain_testFlag1 is not 0.0, or when
    height - cz >= 6.0 and anyHeight is 0.  Otherwise the spot becomes (x, y, height) and
    the box (x -/+ radius, y -/+ radius, height -/+ 100000) is asked; the try fails when an
    object without object flag 1 has dx^2 + dy^2 <= float(radius^2) + r^2.  The seed is
    stored once per try, after its sample. Returns (seed, spot, ok, attempts, draws,
    boxes); attempts counts samples, while the original's zero-based loop counter is
    attempts - 1 on success and 50 on exhaustion.
    """
    frange, frad = C.from_int(C.s32(rng_range)), C.from_int(C.s32(radius))
    spot = tuple(center)
    tries, draws, boxes = 0, 0, []
    while tries < FREE_SPOT_TRIES:
        seed, p, n = unit_ball_sample(seed)
        draws += n
        x = C.add(C.mul(p[0], frange), center[0])
        y = C.add(C.mul(p[1], frange), center[1])
        point = (x, y, center[2])
        if blocked(point) != 0:
            tries += 1
            continue
        h = height(point)
        if not C.lt(C.sub(h, center[2]), HEIGHT_STEP) and not any_height:
            tries += 1
            continue
        spot = (x, y, h)
        lo = (C.sub(x, frad), C.sub(y, frad), C.sub(h, BOX_DEPTH))
        hi = (C.add(x, frad), C.add(y, frad), C.add(h, BOX_DEPTH))
        boxes.append((lo, hi))
        limit = C.from_int(C.s32(radius * radius))
        hit = False
        for ox, oy, orad, oflags in box(lo, hi):
            if oflags & 1:
                continue
            dx, dy = C.sub(ox, x), C.sub(oy, y)
            if C.le(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.add(limit, C.mul(orad, orad))):
                hit = True
                break
        if not hit:
            return seed, spot, 1, tries + 1, draws, boxes
        tries += 1
    return seed, spot, 0, tries, draws, boxes


def lcg_n(seed, n):
    for _ in range(n):
        seed = lcg(seed)[0]
    return seed


# ---- 5. OniBall_ctor 0x294014 (the Life Tap orb a kill can drop) ---------------------
ONIBALL_CTOR, ONIBALL_SIZE, ONIBALL_SITE = 0x294014, 0xB8, 0x111F94   # creature-tick.md 4 step 9
VT_ONIBALL = 0x50E878             # 0x294068-0x294074
PROJECTILE_CTOR = 0x150E48
OBJ_RUN_EVERY_FRAME = 0x14F248
F_36, F_50, F_0_05 = 0x42100000, 0x42480000, 0x3D4CCCCC   # 0x294114, 0x294120, 0x2940fc


def oniball_ctor(seed, pos, frame, creature_max_hp):
    """OniBall_ctor(block, position, facing (unused), creature, 0), read from
    0x294014-0x2941e3.  Projectile_ctor(block, position copy, 0, 0) (ref_skills_a: ONE
    SHARED DRAW in GameObject_ctor, the object's own seed = that draw); then vtable
    0x50e878, bytes +0x80/+0x81 = 0, radius +0x1c = 0, and five OWN draws:
    facing +0x38 = d1; +0x54 = frame + 600; flags |= 0x4000; d2 % 65536 < 0x7333 gives
    byte +0x74 = 0 and creature +0x38c = 30, else +0x74 = 1 and creature +0x394 = 30;
    +0x58 = trunc(creature max hp x 0.05); creature +0xf0 = frame; obj_runEveryFrame;
    z += 36; +0x68 = (x - 50) + float(d3 % 100); +0x6c = (y - 50) + float(d4 % 100);
    +0x70 = (z + float(d5 % 2000)) + 36 with the raised z.
    Returns (shared seed, own seed, block fields, creature fields)."""
    shared, own = lcg(seed)
    own, d1 = lcg(own)
    own, d2 = lcg(own)
    own, d3 = lcg(own)
    own, d4 = lcg(own)
    own, d5 = lcg(own)
    z = C.add(pos[2], F_36)
    fields = {0x48: (4, VT_ONIBALL), 0x80: (1, 0), 0x81: (1, 0), 0x1C: (4, 0), 0x38: (2, d1),
              0x54: (4, (frame + 600) & 0xFFFFFFFF), 0x74: (1, 0 if (d2 & 0xFFFF) < 0x7333 else 1),
              0x58: (4, C.to_int(C.mul(creature_max_hp, F_0_05)) & 0xFFFFFFFF), 0x18: (4, z),
              0x68: (4, C.add(C.sub(pos[0], F_50), C.from_int(d3 % 100))),
              0x6C: (4, C.add(C.sub(pos[1], F_50), C.from_int(d4 % 100))),
              0x70: (4, C.add(C.add(z, C.from_int(d5 % 2000)), F_36)), 0x44: (4, own)}
    creature = {0xF0: (4, frame), (0x38C if (d2 & 0xFFFF) < 0x7333 else 0x394): (4, 30)}
    return shared, own, fields, creature


# ---- 6. Goblin_onNearbyEvent 0x26c9f4 (Goblin slot 12) ---------------------------------
GOBLIN_ON_NEARBY, GOBLIN_HAS_SHIELD = 0x26C9F4, 0x26D7E4
GOBLIN_TYPEINFO = 0x3C44E8


def goblin_has_shield_up(slot15_hand2, slot14_hand2):
    """Goblin_hasShieldUp 0x26d7e4 (goblin): with a holder (+0x50), holder slot 15 (hand 2)
    must answer part 7 and then holder slot 14 (hand 2) non-zero; else 0."""
    return 1 if slot15_hand2 == 7 and slot14_hand2 != 0 else 0


def goblin_on_nearby_event(state, event, source, source_is_goblin, shield, goblin_xy, facing, source_xy):
    """Goblin_onNearbyEvent(goblin, event, position, source), read from 0x26c9f4-0x26cb43.
    Returns (set-state request or None, store the position at +0x104).

      event 0, a source whose type info equals Goblin's (rtti_typeInfoEquals) and
        u16 state < 2: slot 27 (goblin, 2) and +0x104..+0x10c = the position.
      event 2, Goblin_hasShieldUp and a source, state 3 or 5: b = atan2_16(source.y -
        y, source.x - x); when u32(b - s16 facing + 0x270f) < 0x4e1f: slot 27 (goblin, 0x11).
      Anything else: nothing.  No draw."""
    if event == 0:
        if source and source_is_goblin and (state & 0xFFFF) < 2:
            return 2, True
        return None, False
    if event == 2 and shield and source and C.s16(state) in (3, 5):
        dy = C.sub(source_xy[1], goblin_xy[1])
        dx = C.sub(source_xy[0], goblin_xy[0])
        b = C.atan2_16(dy, dx)
        if ((b - C.s16(facing) + 0x270F) & 0xFFFFFFFF) < 0x4E1F:
            return 0x11, False
    return None, False
