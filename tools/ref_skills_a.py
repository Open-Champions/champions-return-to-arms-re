#!/usr/bin/env python3
"""ref_skills_a.py - reference model of the skills with ids 1-34 of Champions: Return to
Arms (SLUS_209.73, US v2.00): the Skill objects, the Spell base, the projectile pattern,
and each skill's can-use, cast, per-tick run and hit handling.

A research tool, not game code.  Every method was written from the instructions at the
address in its docstring and is compared with that code, executed under tools/ee_emu.py,
by tools/difftest_skills_a.py.  docs/spec/skills-01-34.md is the prose (written from
reading); docs/spec/skills-01-34-executed.md says what execution confirmed and corrected.
Standard library only.  No game data is embedded: the statistic tables and the mana-cost
constants are read from the Skill objects and functions in the memory the caller supplies
(tools/dump_tables.py reads the same tables from an executable); strings, particle
definitions and class tables are named by address only.

How it sees the game: exactly as tools/ref_creature.py and tools/ref_arena_monsters.py do -
a memory image (load / store), callbacks for everything outside the model (EXTERNALS),
canonical arguments (integers as unsigned 32-bit, floats as 32-bit patterns, a vector as a
tuple of three patterns, a pointer into the caller's stack as the text 'stack').  Model is
a subclass of ref_arena_monsters.Model, so the creature base class (ref_creature) and
skill 11, Summon Skeleton (ref_arena_monsters), are imported, not modelled again.

Virtual calls are resolved through the table the object carries:
    Skill   table at +0x60   SKILL_BODIES    else the callback 'Skill.v<slot>'
    Spell   table at +0x14   SPELL_BODIES    else 'Spell.v<slot>'
    object  table at +0x48   OBJECT_BODIES, then the creature bodies of the two imported
                             models, else 'Creature.v<slot>'

Contents
    1. the shared machinery
         Skill slots 1, 2, 5, 8, 9-15 (base bodies 0x3c8218-0x3c88e4), mana cost
         Spell base: constructor part, Spell_rand, creature_addSpell 0x11a838,
                     creature_findSpellByType 0x11a710, the owner's per-tick walk
                     (ref_creature.update_spells 0x11a868)
         GameObject_ctor 0x14cb10 (objects without properties), Projectile_ctor 0x150e48,
         obj_moveAndCollide 0x1509f8, the damage descriptor skills build on their stack
    2. the skills, in id order (see the section comments)

Draws.  Model.draws counts the draws from the shared seed 0x404464 made by modelled code.
Constructors that stay callbacks (LightEffect, GlowingShaft, LostSoul, FireStormFlare,
PhProp, the skeleton) make one shared draw each inside GameObject_ctor; the docstrings
say so and Model.hidden_draws counts them, in order of the calls.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
from ref_creature import Ext, M32, M64, s8, s16, s32      # noqa: E402,F401

# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
G_RAND_SEED = RC.G_RAND_SEED                    # 0x404464 shared seed
G_COSMETIC_SEED = AM.G_COSMETIC_SEED            # 0x404460 presentation generator (per machine)
G_SEED3 = RC.G_SEED3                            # 0x404468 third generator (per machine)
G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_LEVEL_MONSTER_LEVEL = RC.G_LEVEL_MONSTER_LEVEL
G_SKILL_TABLE = 0x41B170                        # pointers to the Skill objects, by id
G_LUMP_GENERATION = 0x41BF78                    # compared with class definition +4
G_GRID_A, G_OFF_GRID = 0x5DB4F0, 0x5F76F0       # grid cell heads (120 x 120) and the off-grid list
G_PVP_MODE_A = 0x4F711C
G_PLAYERS, REC_SIZE = RC.G_PLAYERS, RC.REC_SIZE
G_CUTSCENE_ACTIVE = RC.G_CUTSCENE_ACTIVE

VT_GAMEOBJECT, VT_PROJECTILE, VT_SPELL = 0x5122A8, 0x5120B8, AM.VT_SPELL
S_HIDE = 0x5321A8                               # 'hide'
S_SPLASH_FMT, S_FX_LUMP = 0x532458, 0x532478

# float patterns
ZERO, HALF, ONE, TWO = 0x00000000, 0x3F000000, 0x3F800000, 0x40000000
F_2M16 = RC.F_2M16                              # 1 / 65536
DT = RC.DT                                      # 0x3c888888, 1 / 60 truncated
F_0_1, F_0_2 = 0x3DCCCCCC, 0x3E4CCCCC
F_12, F_24, F_72 = 0x41400000, 0x41C00000, 0x42900000

# Skill base bodies (never overridden: slots 8 and 10-15)
SKILL_BASE = {
    0x3C8218: 'skill_can_use_base', 0x3C8220: 'skill_cast_base', 0x3C82A8: 'skill_mana_base',
    0x3C82E4: 'skill_stat_range', 0x3C85B0: 'skill_init_stats_base', 0x3C85FC: 'skill_stat',
    0x3C8690: 'skill_stat_tier2', 0x3C87F0: 'skill_stat_for', 0x3C8864: 'skill_stat_for_handle',
    0x3C88DC: 'skill_adjust_level', 0x3C88E4: 'skill_mana_from_stat4',
}
SKILL_BODIES = dict(SKILL_BASE)                 # function -> method; the skill sections add to it
SKILL_BODIES.update({0x2E2368: 'summon_can_use', 0x2E18A4: 'summon_cast'})      # skill 11, imported
SPELL_BODIES = {0x2E177C: 'summon_spell_run'}   # spell slot 2 bodies (and slot 4 where a class has one)
OBJECT_BODIES = {}                              # GameObject slot bodies: run (4) and touched (6)

# The original functions this module implements (name -> address); the differential test
# runs exactly these, the imported models' functions, the C library and the type-info
# getters for real.
MODELLED = {
    'Skill_canUse_base': 0x3C8218, 'Skill_cast_base': 0x3C8220, 'Skill_manaCost_base': 0x3C82A8,
    'Skill_getStatRange': 0x3C82E4, 'Skill_initStats_base': 0x3C85B0, 'Skill_getStat': 0x3C85FC,
    'Skill_getStatTier2': 0x3C8690, 'Skill_getStatFor': 0x3C87F0, 'Skill_getStatForHandle': 0x3C8864,
    'Skill_adjustLevel': 0x3C88DC, 'Skill_manaFromStat4': 0x3C88E4,
    'Spell_rand': 0x16A964, 'GameObject_rand': 0x1509D0,
    'creature_addSpell': 0x11A838, 'creature_findSpellByType': 0x11A710,
    'GameObject_ctor': 0x14CB10, 'Projectile_ctor': 0x150E48, 'obj_moveAndCollide': 0x1509F8,
}

EXTERNALS = dict(AM.EXTERNALS)
for _name in ('creature_addSpell', 'GameObject_ctor'):
    del EXTERNALS[_name]                        # modelled here
EXTERNALS.update({
    'damage_apply': Ext(0x1E8230, 'ppiiiiDi', 2, 'i', '(victim, attacker, attack rating, 0, 0, flags, descriptor, '
                        'no-crit; min, max)'),
    'world_collectObjectsInArc': Ext(0x1614F0, 'viHp', 3, 'n', '(centre, heading, list head, filter; radius, arc in '
                                     'degrees, half width) -> objects, nearest first'),
    'world_collectInSphere': Ext(0x14AB80, 'viH', 1, 'n', '(centre, heading, list head; radius) -> objects'),
    'Creature.v1': Ext(0, 'pi', 0, 'n', 'destroy (3): how an object deletes itself'),
    'Creature.v22': Ext(0, 'pp', 0, 'i', 'same team (other)'),
    'Skill.v4': Ext(0, 'ppi', 0, 'n', 'describe rank (buffer, level)'),
    'Spell.v0': Ext(0, '', 0, 'i', 'type-info getter'),
    'text_lookup': Ext(0x173C84, 'p', 0, 'i', '(key) -> wide text'),
    'wstr_format': Ext(0x19EA78, 'pp', 8, 'n', '(out, wide format; eight numbers)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row (ref_creature.shape_result
    with this module's rows; 'H' is a list head the callee fills - the objects come back
    as a list; 'D' is a damage descriptor)."""
    ext = EXTERNALS[name]
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwWbnLH':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oO' else ([] if kind in 'nLH' else 0)
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvelsSOWHD':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def descriptor(*entries):
    """The damage descriptor a skill builds on its stack, as damage_apply is handed it:
    an item record whose eight halfwords at +0x10 are 0, whose bytes +0x20 and +0x21 are
    0xff and whose four effect slots at +0x24 (type, v1, v2, v3 - signed 16-bit each) are
    empty (type -1) except the ones given.  Canonical form: ('desc', slot0, slot1, slot2,
    slot3) with None for an empty slot.  (The fill is the inlined "first slot that is
    empty or already of this type", which on a fresh record is slot 0, then 1, ...)"""
    slots = [None] * 4
    for index, entry in enumerate(entries):
        slots[index] = tuple(v & 0xFFFF for v in entry)
    return ('desc',) + tuple(slots)


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & M32


def unit(draw):
    """A 16-bit draw as a coordinate in [-1, 1): (d x 2^-16) doubled, minus 1."""
    m = C.mul(C.from_int(draw), F_2M16)
    return C.sub(C.add(m, m), ONE)


def frac(draw):
    """A 16-bit draw as a fraction in [0, 1): d x 2^-16."""
    return C.mul(C.from_int(draw), F_2M16)


def round_half(value):
    """The inline rounding: + 0.5 when 0 <= value, - 0.5 otherwise, then truncation."""
    return C.to_int(C.add(value, HALF) if C.le(ZERO, value) else C.sub(value, HALF))


def spread_max(base, draw, factor=F_0_2):
    """base + ((base x (draw x 2^-16)) x 0.2), the upper damage bound of nearly every skill
    (base is a float pattern)."""
    return C.add(base, C.mul(C.mul(base, frac(draw)), factor))


class Model(AM.Model):
    """Skills 1-34 on a memory image.  See the module docstring."""

    def __init__(self, mem, callbacks=None, external=()):
        AM.Model.__init__(self, mem, callbacks, external)
        self.hidden_draws = 0           # shared draws inside constructors that stay callbacks

    # ---- plumbing ----------------------------------------------------------------------
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        body = OBJECT_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None:
            return getattr(self, body)((obj + self.s16(table + 8 * slot)) & M32, *args)
        return AM.Model.vcall(self, obj, slot, *args)

    def skill_call(self, skill, slot, *args):
        """A virtual call on a Skill (table pointer at +0x60)."""
        table = self.u32(skill + 0x60)
        this = (skill + self.s16(table + 8 * slot)) & M32
        function = self.u32(table + 8 * slot + 4)
        body = SKILL_BODIES.get(function)
        if body is not None and ('Skill.v%d' % slot) not in self.external:
            return getattr(self, body)(this, *args)
        if slot == 5:
            return self.mana_cost_at(function, this, *args)
        return self.call('Skill.v%d' % slot, this, *args)

    def table_call(self, cls, obj, table_offset, slot, *args):
        if cls == 'Spell':
            table = self.u32(obj + table_offset)
            body = SPELL_BODIES.get(self.u32(table + 8 * slot + 4))
            if body is not None and ('Spell.v%d' % slot) not in self.external:
                return getattr(self, body)((obj + self.s16(table + 8 * slot)) & M32, *args)
        return RC.Model.table_call(self, cls, obj, table_offset, slot, *args)

    def frame(self):
        return self.s32(G_SIM_FRAME)

    def is_player(self, obj):
        return bool(obj and self.u32(obj + 0xC) & 0x40)

    def delete_self(self, obj):
        """An object ending itself: its own slot 1 with 3 (destroy and free)."""
        if obj:
            self.vcall(obj, 1, 3)

    def spell_delete(self, spell):
        """A spell ending itself: its own slot 1 with 3."""
        if spell:
            self.table_call('Spell', spell, 0x14, 1, 3)

    def obj_ball(self, obj):
        """A point of the unit ball from the object's own generator (+0x44): three draws
        per try (x, y, z), retried while (x*x + y*y) + z*z > 1."""
        while True:
            x, y, z = unit(self.obj_rand(obj)), unit(self.obj_rand(obj)), unit(self.obj_rand(obj))
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def spell_ball(self, spell):
        """The same from a spell's own generator (+0x10)."""
        while True:
            x, y, z = unit(self.spell_rand(spell)), unit(self.spell_rand(spell)), unit(self.spell_rand(spell))
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def puff(self, ball, definition, centre, spread, speed):
        """The usual particle: position = ball point x spread + centre, velocity = a second
        ball point x speed (spread None: the centre itself, one ball only)."""
        if spread is None:
            point = tuple(centre)
        else:
            b = ball()
            point = tuple(C.add(C.mul(b[i], spread), centre[i]) for i in range(3))
        b = ball()
        self.call('particle_spawn', definition, point, tuple(C.mul(b[i], speed) for i in range(3)), ZERO)

    def light_effect(self, block_size, pos, *numbers):
        """pool_new + LightEffect_ctor 0x201bd8: a purely visual GameObject (ONE SHARED DRAW
        inside its GameObject_ctor, not made here)."""
        block = self.call('pool_new', block_size)
        if block:
            self.call('LightEffect_ctor', block, tuple(pos), *numbers)
            self.hidden_draws += 1
        return block

    # =====================================================================================
    # 1. Shared machinery: the Skill object
    #
    # Layout (0x68 bytes): +0 name, +4 flags (bit 0: the prediction copy may cast), +8 kind
    # (0 active, 1 channelled, 3 passive), +0xc s16 recast frames, tier 1 = first level
    # +0xe s16[5], base +0x18 s16[5], step +0x24 float[5]; tier 2 = +0x38, +0x42, +0x4c;
    # +0x60 virtual table; +0x64 id in the classes that serve several ids.
    # =====================================================================================
    def skill_by_id(self, skill_id):
        return self.u32(G_SKILL_TABLE + 4 * skill_id)

    def skill_can_use_base(self, skill, caster=0):
        """Slot 1 base, 0x3c8218 -> 1."""
        return 1

    def skill_cast_base(self, skill, level=0, caster=0, pos=None, facing=0):
        """Slot 2 base, 0x3c8220 -> 0 (copies the position to its stack and returns)."""
        return 0

    def skill_mana_base(self, skill, level=0):
        """Slot 5 base, 0x3c82a8 -> 1.0."""
        return ONE

    def skill_init_stats_base(self, skill):
        """Slot 9 base, 0x3c85b0: tier 1 of all five statistics = first level 0, base 1,
        step 2.0.  Tier 2 is not touched."""
        for i in range(5):
            self.w16(skill + 0xE + 2 * i, 0)
            self.w32(skill + 0x24 + 4 * i, TWO)
            self.w16(skill + 0x18 + 2 * i, 1)

    def skill_stat(self, skill, stat, level, _unused=0):
        """Slot 10, 0x3c85fc (skill, statistic, level) -> int, tier 1.

        0 at level 0 and below the statistic's first level; otherwise
        round(base + step x (level - first)) in console single precision."""
        stat, level = s32(stat), s32(level)
        if level == 0:
            return 0
        first = self.s16(skill + 0xE + 2 * stat)
        if level < first:
            return 0
        value = C.add(C.from_int(self.s16(skill + 0x18 + 2 * stat)),
                      C.mul(self.u32(skill + 0x24 + 4 * stat), C.from_int(level - first)))
        return round_half(value)

    def skill_stat_tier2(self, skill, stat, level, cap):
        """Slot 11, 0x3c8690 (skill, statistic, level, cap) -> int.

        0 at level 0.  With cap > 0 the level is min(level, cap) (a level 0 test comes
        first, so a cap never revives level 0).  Tier 2 when its first level is not
        NEGATIVE (the code tests the sign, 0x3c86d8; constructors store -1), else tier 1."""
        stat, level, cap = s32(stat), s32(level), s32(cap)
        if level == 0:
            return 0
        if cap > 0 and cap < level:
            level = cap
        first = self.s16(skill + 0x38 + 2 * stat)
        if first < 0:
            first = self.s16(skill + 0xE + 2 * stat)
            if level < first:
                return 0
            value = C.add(C.from_int(self.s16(skill + 0x18 + 2 * stat)),
                          C.mul(self.u32(skill + 0x24 + 4 * stat), C.from_int(level - first)))
            return round_half(value)
        if level < first:
            return 0
        value = C.add(C.from_int(self.s16(skill + 0x42 + 2 * stat)),
                      C.mul(self.u32(skill + 0x4C + 4 * stat), C.from_int(level - first)))
        return round_half(value)

    def skill_stat_for(self, skill, stat, level, caster, cap):
        """Slot 12, 0x3c87f0 (skill, statistic, level, caster, cap): slot 10 for a caster
        with object flag 0x40 (the cap is ignored), slot 11 otherwise and for no caster."""
        if caster and self.u32(caster + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level, cap)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_stat_for_handle(self, skill, stat, level, handle, cap):
        """Slot 13, 0x3c8864: slot 12 with the caster read through a handle word (its node's
        object at +0xc, not tested for null); an empty handle is "not a player"."""
        node = self.u32(handle)
        if node and self.u32(self.u32(node + 0xC) + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level, cap)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_adjust_level(self, skill, level, n=0):
        """Slot 14, 0x3c88dc -> the level unchanged."""
        return level

    def skill_mana_from_stat4(self, skill, level, n):
        """Slot 15, 0x3c88e4 -> (float) slot 10 (4, slot 14 (level, n))."""
        level = self.skill_call(skill, 14, level, n)
        return C.from_int(s32(self.skill_call(skill, 10, 4, level)))

    def skill_stat_range(self, skill, stat, level, randomise, spread):
        """Slot 8, 0x3c82e4 (skill, statistic, level, randomise, low out, high out; spread)
        -> (low, high), each at least 1.

        v = slot 10.  Plain: round(v - v x spread), round(v + v x spread).  With randomise
        each bound makes TWO SHARED DRAWS: the first only decides which way the 0.5 goes
        (from the sign of v -/+ (v x (d x 2^-16)) x spread), the second gives the value."""
        value = C.from_int(s32(self.skill_call(skill, 10, stat, level)))
        out = []
        for combine in (C.sub, C.add):
            if s32(randomise):
                probe = combine(value, C.mul(C.mul(value, frac(self.draw())), spread))
                bound = combine(value, C.mul(C.mul(value, frac(self.draw())), spread))
            else:
                probe = bound = combine(value, C.mul(value, spread))
            bound = C.to_int(C.add(bound, HALF) if C.le(ZERO, probe) else C.sub(bound, HALF))
            out.append(bound if s32(bound) > 0 else 1)
        return tuple(out)

    def mana_cost(self, skill, level):
        """Slot 5 of the skill -> float pattern."""
        return self.skill_call(skill, 5, level)

    def mana_cost_at(self, function, skill, level):
        """A skill's own slot-5 body, recognised by shape so that no number is embedded:

          * `level - 1` first: (float)(level - 1) x step + base, the two constants being
            the float immediates the function loads (e.g. 0x2cb33c);
          * a call of slot 15 with (level, n): its result (e.g. 0x2e0040, n = 1; 0x2e6894,
            n = 20);
          * a call of slot 14 with (level, n) and then 0.0 (Dodge, 0x2e8a88)."""
        words = [self.u32(function + 4 * i) for i in range(14)]
        if words[0] == 0x24A5FFFF:                              # addiu a1, a1, -1
            consts, value = {}, 0
            for word in words[1:]:
                if word >> 16 == 0x3C01:                        # lui at
                    value = (word & 0xFFFF) << 16
                elif word >> 16 == 0x3421:                      # ori at, at
                    value |= word & 0xFFFF
                elif word & 0xFFFF07FF == 0x44810000:           # mtc1 at, f<n>
                    consts[(word >> 11) & 31] = value
            return C.add(C.mul(C.from_int(s32(level) - 1), consts[2]), consts[1])
        if words[3] >> 16 == 0x2406 and words[5] >> 16 == 0x2442:
            n, slot = words[3] & 0xFFFF, (words[5] & 0xFFFF) // 8
            if slot == 15:
                return self.skill_call(skill, 15, level, n)
            if slot == 14:
                self.skill_call(skill, 14, level, n)
                return ZERO
        raise NotImplementedError('mana-cost function at 0x%x' % function)

    # =====================================================================================
    # 1. Shared machinery: the Spell base
    #
    # Layout: +0 level (u8), +4 back list (what the owner's handle hooks into), +8 Skill,
    # +0xc owner, +0x10 own generator (ONE SHARED DRAW in every constructor), +0x14 table.
    # Slots: 0 type-info getter, 1 destroy, 2 run (position, facing), 3 draw, 4 a field.
    # =====================================================================================
    def add_spell(self, creature, spell):
        """creature_addSpell 0x11a838 (creature, spell): with a spell,
        handle_link(creature + 0x364, spell + 4, spell) - the newest spell is first."""
        if spell:
            self.call('handle_link', creature + 0x364, spell + 4, spell)

    def find_spell_by_type(self, creature, type_info):
        """creature_findSpellByType 0x11a710 (creature, type info) -> the first attached
        spell whose class is exactly that one, or 0.

        The list at +0x364 is walked front to back; a node without an object is skipped;
        each spell's slot 0 (its type-info getter) is compared by rtti_typeInfoEquals
        0x3b1250.  `type_info` here is what the class's getter returned: the model
        identifies a class by its getter's result, as the original does."""
        node = self.u32(creature + 0x364)
        while node:
            spell = self.u32(node + 0xC)
            if spell and self.spell_type(spell) == type_info:
                return spell
            node = self.u32(node)
        return 0

    def spell_type(self, spell):
        """What the spell's slot 0 returns.  The getters are run for real by the test;
        the model takes the class's type-info object from the table of known getters
        (TYPE_INFO, filled by whoever sets the memory up) or asks the callback."""
        table = self.u32(spell + 0x14)
        getter = self.u32(table + 4)
        if getter in self.type_info:
            return self.type_info[getter]
        return self.call('Spell.v0', spell)

    type_info = {}                      # type-info getter -> type-info object (see spell_type)

    def carries(self, creature, getter):
        """"The creature carries a spell of this class": the getter is called (the test
        runs it for real), then creature_findSpellByType."""
        return self.find_spell_by_type(creature, self.type_info[getter])

    # =====================================================================================
    # 1. Shared machinery: objects and the projectile pattern
    # =====================================================================================
    def gameobject_ctor(self, obj, pos, class_def, props):
        """GameObject_ctor 0x14cb10 (object, position, class definition, property list) for
        an object WITHOUT properties (every object of this module).

        Heads +0, +4, +8 = 0, table 0x5122a8, radius +0x1c = 24, height +0x20 = 72, flags
        +0xc = 0, bytes +0x28 = 0x19, +0x29 = 0x49, position +0x10, +0x34 = 0, +0x24 = the
        definition.  A definition whose generation word +4 is not the current one
        (0x41bf78) has each of its names looked up (res_find(lump, name) for the entries
        from +8, eight bytes each, until a null name) and takes the generation.  The grid
        link: handle_link(cell, object + 8, object) with the cell from the truncated
        position ((int)x + 0x3c00) >> 8, row major, or the off-grid list outside 0..119.
        'hide' is asked of the still empty object (obj_getPropInt), +0x2c = the list, and
        ONE SHARED DRAW seeds the object's own generator +0x44 (the 16-bit draw)."""
        w32, u32 = self.w32, self.u32
        for off in (0, 4, 8, 0xC, 0x34):
            w32(obj + off, 0)
        w32(obj + 0x48, VT_GAMEOBJECT)
        w32(obj + 0x1C, F_24)
        w32(obj + 0x20, F_72)
        self.w8(obj + 0x28, 0x19)
        self.w8(obj + 0x29, 0x49)
        self.wvec(obj + 0x10, pos)
        w32(obj + 0x24, class_def)
        if class_def and u32(class_def + 4) != u32(G_LUMP_GENERATION):
            k = 8
            while u32(class_def + k):
                w32(class_def + k + 4, self.call('res_find', u32(class_def), u32(class_def + k)))
                k += 8
            w32(class_def + 4, u32(G_LUMP_GENERATION))
        col = (s32(C.to_int(u32(obj + 0x10))) + 0x3C00) >> 8
        row = (s32(C.to_int(u32(obj + 0x14))) + 0x3C00) >> 8
        if 0 <= col < 0x78 and 0 <= row < 0x78:
            cell = G_GRID_A + 4 * (row * 0x78 + col)
        else:
            cell = G_OFF_GRID
        self.call('handle_link', cell, obj + 8, obj)
        if self.call('obj_getPropInt', obj, S_HIDE, 0):
            raise NotImplementedError('a hidden object: the grid node is moved by hand (0x14cc90)')
        w32(obj + 0x2C, props)
        w32(obj + 0x44, self.draw())
        if props:
            raise NotImplementedError('an object with properties (the name table)')

    def projectile_ctor(self, obj, pos, owner, class_def=0):
        """Projectile_ctor 0x150e48 (object, position, owner, class definition):
        GameObject_ctor without properties (ONE SHARED DRAW), then owner handle +0x4c = 0,
        radius 12, table 0x5120b8, flags |= 0x4081, "has splashed" byte +0x50 = 0, and with
        an owner handle_link(object + 0x4c, owner, owner)."""
        self.gameobject_ctor(obj, pos, class_def, 0)
        self.w32(obj + 0x4C, 0)
        self.w32(obj + 0x1C, F_12)
        self.w32(obj + 0x48, VT_PROJECTILE)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4081)
        self.w8(obj + 0x50, 0)
        if owner:
            self.call('handle_link', obj + 0x4C, owner, owner)

    def move_and_collide(self, obj, velocity):
        """obj_moveAndCollide 0x1509f8 (object, velocity in units per second) -> bit 0:
        went into the ground, bit 1: touched something.

          1. step = velocity x (1/60) per component; position += step; obj_updateGridCell.
          2. terrain_height(world, position; radius) above z: bit 0, and the position is
             moved back by k x step for k = 0.1, 0.2, ... (the 0.1 is added up in single
             precision) until the ground there is not above it or k reaches 2.0; the LAST
             point tried is kept.  Then, once per object (byte +0x50): water_test(world,
             position, 0; 12.0) - with water the byte is set, ONE OWN DRAW is made and
             thrown away (the splash clip is always number 1), the sound plays at 0.2 and
             the water is disturbed (700, 24).
          3. every object of world_collectObjectsInBox(position -/+ (radius, radius,
             height), capacity 256), in the order returned, that has none of the object
             flags 0x201 and 0x20000000, is not the object itself and not the owner (handle
             +0x4c), overlaps in height (z - height <= its z + its height and its z <=
             z + height, both objects' own heights) and is nearer in the plane than the two
             radii together (strict): bit 1; ITS slot 6 with the object, then the object's
             slot 6 with it.  Everything is read again for each one, so a handler that
             moves or resizes the object changes the tests that follow."""
        u32, w32 = self.u32, self.w32
        step = tuple(C.mul(velocity[i], DT) for i in range(3))
        for i in range(3):
            w32(obj + 0x10 + 4 * i, C.add(u32(obj + 0x10 + 4 * i), step[i]))
        self.call('obj_updateGridCell', obj)
        result = 0
        ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
        if C.lt(u32(obj + 0x18), ground):
            result = 1
            k = F_0_1
            while True:
                back = tuple(C.mul(step[i], k) for i in range(3))
                attempt = tuple(C.sub(u32(obj + 0x10 + 4 * i), back[i]) for i in range(3))
                ground = self.call('terrain_height', u32(G_WORLD), attempt, u32(obj + 0x1C))
                if C.le(ground, attempt[2]):
                    break
                k = C.add(k, F_0_1)
                if not C.lt(k, TWO):
                    break
            self.wvec(obj + 0x10, attempt)
            if self.s8(obj + 0x50) == 0:
                if self.call('water_test', u32(G_WORLD), self.vec(obj + 0x10), 0, F_12):
                    self.w8(obj + 0x50, 1)
                    self.obj_rand(obj)
                    text = self.call('libc_sprintf', S_SPLASH_FMT, 1)
                    self.call('sound_playOnObject', self.call('res_find', S_FX_LUMP, text), obj, F_0_2)
                    self.call('water_disturb', u32(G_WORLD), self.vec(obj + 0x10), 0x442F0000, F_24)
        radius, height = u32(obj + 0x1C), u32(obj + 0x20)
        low = (C.sub(u32(obj + 0x10), radius), C.sub(u32(obj + 0x14), radius), C.sub(u32(obj + 0x18), height))
        high = (C.add(u32(obj + 0x10), radius), C.add(u32(obj + 0x14), radius), C.add(u32(obj + 0x18), height))
        owner = self.handle_obj(obj + 0x4C)
        for other in self.call('world_collectObjectsInBox', low, high, 0x100) or ():
            flags = u32(other + 0xC)
            if flags & 0x201 or flags & 0x20000000 or other == obj or other == owner:
                continue
            if C.lt(C.add(u32(other + 0x18), u32(other + 0x20)), C.sub(u32(obj + 0x18), u32(obj + 0x20))):
                continue
            if C.lt(C.add(u32(obj + 0x18), u32(obj + 0x20)), u32(other + 0x18)):
                continue
            dx = C.sub(u32(obj + 0x10), u32(other + 0x10))
            dy = C.sub(u32(obj + 0x14), u32(other + 0x14))
            reach = C.add(u32(obj + 0x1C), u32(other + 0x1C))
            if not C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(reach, reach)):
                continue
            result |= 2
            self.vcall(other, 6, obj)
            self.vcall(obj, 6, other)
        return result

    def box_around(self, centre, half, capacity):
        """world_collectObjectsInBox with a cube: centre -/+ half on all three axes."""
        low = tuple(C.sub(centre[i], half) for i in range(3))
        high = tuple(C.add(centre[i], half) for i in range(3))
        return self.call('world_collectObjectsInBox', low, high, capacity) or ()

    def flash2(self, creature, a, b, c, d):
        """The second flash colour quad of a creature, +0x98..+0x9e (four s16)."""
        for off, value in ((0x98, a), (0x9A, b), (0x9C, c), (0x9E, d)):
            self.w16(creature + off, value)

    def flash_both(self, creature, a, b, c, d):
        """Both flash quads: +0x90..+0x96 and +0x98..+0x9e."""
        for base in (0x90, 0x98):
            for i, value in enumerate((a, b, c, d)):
                self.w16(creature + base + 2 * i, value)
