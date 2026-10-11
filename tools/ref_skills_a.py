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

Contents (Model is built up section by section - each section is a `class Model(Model)` -
so that a skill's constants, methods and table rows stay together)
    1. the shared machinery
         Skill slots 1, 2, 5, 8, 9-15 (base bodies 0x3c8218-0x3c88e4), mana cost
         Spell base: constructor part, Spell_rand, creature_addSpell 0x11a838,
                     creature_findSpellByType 0x11a710, the owner's per-tick walk
                     (ref_creature.update_spells 0x11a868)
         GameObject_ctor 0x14cb10 (objects without properties), Projectile_ctor 0x150e48,
         obj_moveAndCollide 0x1509f8, the damage descriptor skills build on their stack
    2. the skills modelled end to end: can-use, cast, constructors, per-tick run, hit
         4 Disease Bolt        7 Fire Storm (both constructors)      9 Riposte (and 82)
         11 Summon Skeleton (imported)       12 / 14 / 26 Lightning, Cold, Poison Weapons
         15 Undead Shield      16 Holy Strike      20 Blinding Light
         21 Repulse Undead (with damage_radial 0x1ead58)      23 Shock Of Frost
         24 Poison Rain        29 Disease Effect   31 / 32 Root (and 52, 85)
         33 Critical Hit (and 53, 81)
       the skills that are only numbers: 2 Dodge (and 83), 3, 19 Regeneration, 25, 27, 28, 30
    3. NOT modelled beyond statistics, mana cost and can-use: 1 Wizard Beam, 5 Disease
       Shield, 6 Disease Trail, 8 Fire Flares, 10 Blessed, 13 Fire Weapons, 17 Hammer Of
       Wrath, 18 Cone Of Fire, 22 Dismiss Undead, 34 Shield Bash (can-use not either).

Presentation is modelled too where a function is: every particle_spawn, light and sound
call-out is made with its arguments, because the own generators that place particles also
roll damage.

Draws.  Model.draws counts the draws from the shared seed 0x404464 made by modelled code.
Constructors that stay callbacks (LightEffect, GlowingShaft, LostSoul, FireStormFlare,
PhProp, the skeleton) make one shared draw each inside GameObject_ctor; the docstrings
say so and Model.hidden_draws counts them, in order of the calls.

Integer division by zero follows what the R5900 is reported to leave (rem / quot below),
as tools/ee_emu.py does with div_zero = 'r5900'; the console's own result is not
established.
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
        if kind in 'ipvelsSOWHDm':
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
            n = 20; 0x2facb0, n = 0);
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
        if (words[3] >> 16 == 0x2406 or words[3] in (0x00003021, 0x00003025, 0x0000302D)) and words[5] >> 16 == 0x2442:
            n = words[3] & 0xFFFF if words[3] >> 16 == 0x2406 else 0        # addiu a2, zero, n / move a2, zero
            slot = (words[5] & 0xFFFF) // 8
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

    # =====================================================================================
    # Skill 4, Disease Bolt: SkillDiseaseBolt (table 0x518468) and the projectile
    # DiseaseBolt (0x7c bytes, table 0x5183d8)
    #
    #   +0x38 s16 heading          +0x4c, +0x54 owner handles     +0x58 homing target handle
    #   +0x5c Skill                +0x60 s16 level                +0x64 velocity (3 floats)
    #   +0x70 expiry frame         +0x74 homing starts after      +0x78 "has hit"
    # =====================================================================================
    DISEASEBOLT_DEFS = (0x8E50A0, 0x8E50F0, 0x8E5140)

    def diseasebolt_can_use(self, skill, caster=0):
        """SkillDiseaseBolt_canUse 0x2cb368 -> 1."""
        return 1

    def diseasebolt_cast(self, skill, level, caster, pos, facing):
        """SkillDiseaseBolt_cast 0x2cb1c0 (skill, level, caster, position, facing) -> 0.

        The caster's second flash quad = (-100, -100, -100, 0) - the caster is NOT tested
        for null - then pool_new(0x7c) and, with a block, DiseaseBolt_ctor."""
        self.flash2(caster, -100, -100, -100, 0)
        obj = self.call('pool_new', 0x7C)
        if obj:
            self.diseasebolt_ctor(obj, facing, level, pos, caster, skill)
        return 0

    def diseasebolt_ctor(self, obj, facing, level, pos, owner, skill):
        """DiseaseBolt_ctor 0x2c9eb0 (object, facing, level, position, owner, skill).

        Projectile_ctor (ONE SHARED DRAW); heading; velocity = (cos, sin, 0) x 350; with an
        owner the second owner handle +0x54; expiry = frame + 300, homing from frame + 10.
        With an owner: world_collectObjectsInArc(position, heading, no filter; 279.99988,
        60 degrees, 0) and the homing target is the first entry the owner's slot 20 calls
        an enemy.  Then the every-frame run list and the cast sound."""
        w32, u32 = self.w32, self.u32
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x54, 0)
        w32(obj + 0x48, 0x5183D8)
        w32(obj + 0x58, 0)
        self.w16(obj + 0x38, facing)
        w32(obj + 0x6C, 0)
        speed = 0x43AF0000
        w32(obj + 0x64, C.mul(C.cos16(s16(facing)), speed))
        w32(obj + 0x68, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        self.w16(obj + 0x60, level)
        if owner:
            self.call('handle_link', obj + 0x54, owner, owner)
        frame = u32(G_SIM_FRAME)
        w32(obj + 0x5C, skill)
        w32(obj + 0x70, frame + 300)
        w32(obj + 0x74, frame + 10)
        w32(obj + 0x78, 0)
        if owner:
            found = self.call('world_collectObjectsInArc', self.vec(obj + 0x10), self.s16(obj + 0x38), 'stack', 0,
                              0x438BFFFC, 0x42700000, ZERO)
            for other in found or ():
                if self.vcall(owner, 20, other):
                    self.call('handle_link', obj + 0x58, other, other)
                    break
            self.call('handle_clear', 'stack')
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', 0x54E988, 0x54E990), obj, ONE)

    def diseasebolt_run(self, obj):
        """DiseaseBolt_run 0x2ca1a8 (object), slot 4, once a frame.

          1. particles, all from the object's own generator: 5, 5 and 6 of the usual kind
             (spread 10 / 15 / 15, speed 16 / 5 / 5).
          2. homing, with a target handle and frame > +0x74: rate = skill slot 13 (1,
             level, the owner handle +0x4c, cap 10) x 182; diff = atan2_16(target - object)
             - heading as plain integers (NOT wrapped to 16 bits); |diff| < rate: heading
             += diff, else -/+ rate (minus when diff <= 0); velocity from the new heading.
             The target node's object is not tested for null.
          3. obj_moveAndCollide with the velocity (the hit handler runs inside).
          4. touched something and "has hit", or went into the ground: expiry = 0.
          5. expiry <= frame: the end sound, fx_spawn(12), 10 x three particles (speed 96 /
             30 / 30), and the object deletes itself."""
        u32, w32 = self.u32, self.w32
        ball = lambda: self.obj_ball(obj)
        defs = self.DISEASEBOLT_DEFS
        for definition, count, spread, speed in ((defs[0], 5, 0x41200000, 0x41800000), (defs[1], 5, 0x41700000, 0x40A00000),
                                                 (defs[2], 6, 0x41700000, 0x40A00000)):
            for _ in range(count):
                self.puff(ball, definition, self.vec(obj + 0x10), spread, speed)
        if u32(obj + 0x58) and self.s32(obj + 0x74) < self.frame():
            skill = u32(obj + 0x5C)
            rate = s32(self.skill_call(skill, 13, 1, self.s16(obj + 0x60), obj + 0x4C, 10)) * 0xB6
            rate = s32(rate)
            target = u32(u32(obj + 0x58) + 0xC)
            diff = C.atan2_16(C.sub(u32(target + 0x14), u32(obj + 0x14)), C.sub(u32(target + 0x10), u32(obj + 0x10))) \
                - self.s16(obj + 0x38)
            heading = self.u16(obj + 0x38)
            if abs(diff) < rate:
                heading += diff
            elif diff <= 0:
                heading -= rate
            else:
                heading += rate
            self.w16(obj + 0x38, heading)
            speed = 0x43AF0000
            w32(obj + 0x64, C.mul(C.cos16(self.s16(obj + 0x38)), speed))
            w32(obj + 0x6C, 0)
            w32(obj + 0x68, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        hit = self.move_and_collide(obj, self.vec(obj + 0x64))
        if hit & 2 and u32(obj + 0x78):
            w32(obj + 0x70, 0)
        if hit & 1:
            w32(obj + 0x70, 0)
        if self.s32(obj + 0x70) <= self.frame():
            self.call('sound_playOnObject', self.call('res_find', 0x54E988, 0x54E9C8), obj, ONE)
            self.call('fx_spawn', 0xC, self.vec(obj + 0x10))
            for _ in range(10):
                self.puff(ball, defs[0], self.vec(obj + 0x10), 0x41200000, 0x42C00000)
                self.puff(ball, defs[1], self.vec(obj + 0x10), 0x41700000, 0x41F00000)
                self.puff(ball, defs[2], self.vec(obj + 0x10), 0x41700000, 0x41F00000)
            self.delete_self(obj)

    def diseasebolt_hit(self, obj, other):
        """DiseaseBolt_onHit 0x2caec8 (object, other), slot 6: called by obj_moveAndCollide
        for every object the bolt overlaps.

        Nothing once "has hit" is set.  Without an owner (handle +0x54 empty) an object
        that is not a creature (flag 0x20) sets "has hit" - and is then damaged all the
        same.  With an owner, only what the owner's slot 20 calls an enemy.  A creature
        that is not a player and has creature flag 0x200 is passed through.  Damage:
        d = skill slot 13 (0, level, the owner handle +0x4c, cap 0); descriptor slot 0 =
        (0x26, d, d, 0); ONE OWN DRAW r; damage_apply(other, owner or 0, 100000, flags 0,
        the descriptor, 0; d, d + d x r/65536 x 0.2); "has hit" = 1."""
        u32 = self.u32
        if u32(obj + 0x78):
            return
        if not u32(obj + 0x54):
            if not u32(other + 0xC) & 0x20:
                self.w32(obj + 0x78, 1)
        else:
            owner = self.handle_obj(obj + 0x54)
            if not self.vcall(owner, 20, other):
                return
        flags = u32(other + 0xC)
        if not flags & 0x40 and flags & 0x20 and self.u64(other + 0xA8) & 0x200:
            return
        dmg = self.skill_call(u32(obj + 0x5C), 13, 0, self.s16(obj + 0x60), obj + 0x4C, 0)
        desc = descriptor((0x26, dmg, dmg, 0))
        amount = C.from_int(s32(dmg))
        high = spread_max(amount, self.obj_rand(obj))
        self.call('damage_apply', other, self.handle_obj(obj + 0x54), 100000, 0, 0, 0, desc, 0, amount, high)
        self.w32(obj + 0x78, 1)


SKILL_BODIES.update({0x2CB368: 'diseasebolt_can_use', 0x2CB1C0: 'diseasebolt_cast'})
OBJECT_BODIES.update({0x2CA1A8: 'diseasebolt_run', 0x2CAEC8: 'diseasebolt_hit'})
MODELLED.update({'SkillDiseaseBolt_canUse': 0x2CB368, 'SkillDiseaseBolt_cast': 0x2CB1C0, 'DiseaseBolt_ctor': 0x2C9EB0,
                 'DiseaseBolt_run': 0x2CA1A8, 'DiseaseBolt_onHit': 0x2CAEC8})


def rem(a, b):
    """The remainder of the machine's signed 32-bit `div`: truncating, and with a zero
    divisor the dividend itself (what the R5900 is reported to leave in HI; tools/ee_emu.py
    follows the same report - the console's own result is not established)."""
    a, b = s32(a), s32(b)
    if b == 0:
        return a
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return a - q * b


def quot(a, b):
    """The quotient of the same instruction; with a zero divisor 1 for a negative dividend,
    else -1 (as reported for the R5900)."""
    a, b = s32(a), s32(b)
    if b == 0:
        return 1 if a < 0 else -1
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def half_toward_zero(value):
    """C's x / 2 on a signed 32-bit value (add the sign bit, shift right)."""
    value = s32(value)
    return (value + (1 if value < 0 else 0)) >> 1


EXTERNALS.update({
    'FireStormFlare_ctor': Ext(0x2D3184, 'pvvi', 1, 'n', '(block, from, velocity, variant; scale): a falling fireball, '
                               'visual; ONE SHARED DRAW inside (GameObject_ctor)'),
    'light_link': Ext(0x148AF8, 'p', 0, 'n', '(light record)'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n', '(light record)'),
    'sound_release': Ext(0x213438, 'i', 0, 'n', '(sound handle): let a looping sound repeat'),
    'sound_stop': Ext(0x213380, 'i', 0, 'n', '(sound handle)'),
})


class Model(Model):                             # noqa: F811 - the class is built up section by section
    # =====================================================================================
    # Skill 7, Fire Storm: SkillFireStorm (table 0x518d28) and the area object FireStorm
    # (0xb4 bytes, table 0x518c98)
    #
    #   +0x4c owner handle        +0x50..+0x88 an embedded light record (presentation)
    #   +0x8c damage per second   +0x90 end frame        +0x94 duration in frames
    #   +0x98 start frame         +0x9c radius (int)     +0xa0 light radius (float)
    #   +0xa4 flare scale         +0xa8 flare period     +0xac sound handle   +0xb0 variant
    # =====================================================================================
    def firestorm_can_use(self, skill, caster):
        """SkillFireStorm_canUse 0x2d532c (skill, caster) -> 1 or 0.  Players only: rank =
        player_getSkillRank(slot, 7); the spot rank-radius x 12 ahead of the player (its own
        facing, z = 0 handed to terrain_height with 12.0); refused when the ground there is
        more than 144 below the player's z."""
        if not self.u32(caster + 0xC) & 0x40:
            return 1
        rank = self.call('player_getSkillRank', self.u32(caster + 0x3C8), 7)
        reach = C.from_int(s32(self.skill_call(skill, 10, 1, rank)))
        facing = self.s16(caster + 0x38)
        x = C.add(C.mul(C.mul(C.cos16(facing), reach), F_12), self.u32(caster + 0x10))
        y = C.add(C.mul(C.mul(C.sin16(facing), reach), F_12), self.u32(caster + 0x14))
        ground = self.call('terrain_height', self.u32(G_WORLD), (x, y, ZERO), F_12)
        return 0 if C.lt(C.sub(ground, self.u32(caster + 0x18)), 0xC3100000) else 1

    def firestorm_cast(self, skill, level, caster, pos, facing):
        """SkillFireStorm_cast 0x2d4f7c (skill, level, caster, position, facing) -> 0.

        r = slot 12 (1, level, caster, cap 10).  Centre = position, moved r x 12 along the
        cast facing for a PLAYER caster only (the caster's flags are read without a null
        test); z = terrain_height(world, (x, y, 0); (float) r) + 6.  pool_new(0xb4) and
        FireStorm_ctor."""
        r = self.skill_call(skill, 12, 1, level, caster, 10)
        reach = C.from_int(s32(r))
        ox = oy = ZERO
        if self.u32(caster + 0xC) & 0x40:
            ox = C.mul(C.mul(C.cos16(s16(facing)), reach), F_12)
            oy = C.mul(C.mul(C.sin16(s16(facing)), reach), F_12)
        x, y = C.add(ox, pos[0]), C.add(oy, pos[1])
        ground = self.call('terrain_height', self.u32(G_WORLD), (x, y, ZERO), reach)
        centre = (x, y, C.add(C.add(ZERO, ground), 0x40C00000))
        obj = self.call('pool_new', 0xB4)
        if obj:
            self.firestorm_ctor(obj, level, caster, centre, skill)
        return 0

    def _firestorm_base(self, obj, pos, owner):
        """What both FireStorm constructors start with: GameObject_ctor (ONE SHARED DRAW),
        the table, the embedded light record at +0x50 and the owner handle."""
        w32, w16 = self.w32, self.w16
        self.gameobject_ctor(obj, pos, 0, 0)
        w32(obj + 0x48, 0x518C98)
        w32(obj + 0x4C, 0)
        self.w8(obj + 0x59, 0)
        self.wvec(obj + 0x80, pos)
        w32(obj + 0x7C, 0x3F004156)
        never = C.div(ONE, C.mul(ZERO, ZERO))                   # 1 / (0 x 0): 0x7fffffff on this FPU, not infinity
        w32(obj + 0x78, never)
        w32(obj + 0x70, never)
        for off, value in ((0x62, 0xFF), (0x64, 0x80), (0x68, 0xFFF0), (0x5A, 0xFF), (0x5C, 0x80), (0x5E, 0),
                           (0x60, 0xFFF0), (0x66, 0)):
            w16(obj + off, value)
        w32(obj + 0x6C, 0)
        w32(obj + 0x74, 0)
        self.w8(obj + 0x58, 0)
        self.call('light_link', obj + 0x50)
        if owner:
            self.call('handle_link', obj + 0x4C, owner, owner)

    def firestorm_ctor(self, obj, level, owner, pos, skill):
        """FireStorm_ctor 0x2d41f8 (object, level, owner, position, skill).

        Damage +0x8c = slot 13 (0, level, owner handle, cap 0); duration +0x94 = slot 13
        (2, ..., cap 20) x 60; radius +0x9c = slot 13 (1, ..., cap 10) x 12; variant 0;
        flare scale +0xa4 = ((float) level x k) x 0.5 + 0.3 with k = 0.05 for a player owner
        and 0.02 for anyone else or nobody; flare period +0xa8 = 15; then the common part."""
        w32 = self.w32
        self._firestorm_base(obj, pos, owner)
        handle = obj + 0x4C
        w32(obj + 0x8C, self.skill_call(skill, 13, 0, level, handle, 0))
        w32(obj + 0x94, s32(self.skill_call(skill, 13, 2, level, handle, 0x14)) * 60)
        r = self.skill_call(skill, 13, 1, level, handle, 10)
        w32(obj + 0xB0, 0)
        w32(obj + 0x9C, s32(r) * 12)
        self.wvec(obj + 0x10, pos)
        k = 0x3D4CCCCC if owner and self.u32(owner + 0xC) & 0x40 else 0x3CA3D70A
        w32(obj + 0xA4, C.add(C.mul(C.mul(C.from_int(s32(level)), k), HALF), 0x3E999999))
        w32(obj + 0xA8, 0xF)
        self.firestorm_init_common(obj, owner)

    def firestorm_ctor2(self, obj, owner, pos, radius, damage, duration, period, scale):
        """FireStorm_ctor2 0x2d4048 (object, owner, position, radius, damage, duration in
        frames, flare period; flare scale): the monster-made variant - the numbers are
        stored as given and the variant word +0xb0 is 1 (flares fall straight, no looping
        sound).  Its one caller is 0x25f988."""
        w32 = self.w32
        self._firestorm_base(obj, pos, owner)
        w32(obj + 0x8C, damage)
        w32(obj + 0xB0, 1)
        w32(obj + 0x94, duration)
        w32(obj + 0x9C, radius)
        w32(obj + 0xA8, period)
        w32(obj + 0xA4, scale)
        self.wvec(obj + 0x10, pos)
        self.firestorm_init_common(obj, owner)

    def firestorm_init_common(self, obj, owner):
        """FireStorm_initCommon 0x2d4480 (object, owner): flags |= 0x421b.  The owner is
        read WITHOUT a null test.  For a creature that is not a player (object flags & 0x60
        == 0x20): start +0x98 = int(frame + 40.499996) and a warning LightEffect (pool_new
        0xbc; ONE SHARED DRAW inside) at the centre + 12 up, its two sizes min(radius, 300)
        and min(2 x radius, 300); end = duration + start.  Otherwise start = 0 and end =
        duration + frame.  Light radius +0xa0 = 0; the every-frame run list; and for
        variant 0 the looping sound, whose handle is kept at +0xac."""
        u32, w32 = self.u32, self.w32
        w32(obj + 0xC, u32(obj + 0xC) | 0x421B)
        if u32(owner + 0xC) & 0x60 == 0x20:
            w32(obj + 0x98, C.to_int(C.add(C.from_int(self.frame()), 0x4221FFFF)))
            radius = self.s32(obj + 0x9C)
            near = C.from_int(300 if 300 < radius else radius)
            far = C.from_int(300 if 300 < s32(radius << 1) else s32(radius << 1))
            pos = (C.add(u32(obj + 0x10), ZERO), u32(obj + 0x14), C.add(u32(obj + 0x18), F_12))
            self.light_effect(0xBC, pos, 0, 1, 0x437F0000, 0x43000000, ZERO, 0x42C80000, 0x437F0000, 0x43000000, ZERO,
                              0x42C80000, near, far, 0x3F266666, 0x40019999)
            start = u32(obj + 0x98)
        else:
            w32(obj + 0x98, 0)
            start = u32(G_SIM_FRAME)
        w32(obj + 0x90, u32(obj + 0x94) + start)
        w32(obj + 0xA0, 0)
        self.call('light_relink', obj + 0x50)
        self.call('obj_runEveryFrame', obj)
        if not u32(obj + 0xB0):
            handle = self.call('sound_playOnObject', self.call('res_find', 0x54F110, 0x54F150), obj, ONE)
            w32(obj + 0xAC, handle)
            self.call('sound_release', handle)

    def firestorm_run(self, obj):
        """FireStorm_run 0x2d470c (object), slot 4, once a frame.

          1. nothing until frame > start.  Then, unless frame < end and the owner handle
             holds something, the object deletes itself.
          2. the light: its radius +0xa0 grows by 1 a frame up to the storm's radius, from
             31 frames after the start; the light record's size is twice that, flickering
             with two sines of the frame, and shrinks over the last 60 frames.
          3. frame % period == 0 (15): a flare.  From = centre + (ball x radius in x and y,
             240.02234 up) - the ball's z is drawn and not used; for variant 0 a second
             ball gives the aim point (centre + ball x radius), for variant 1 the flare
             falls straight; the aim's z = terrain_height(world, aim; 12.0); velocity =
             the unit vector x 15.000689.  pool_new(0x6c) and FireStormFlare_ctor (ONE
             SHARED DRAW inside).  All draws are OWN draws.
          4. frame % 30 == 0: every object of the box centre -/+ radius (capacity 64) the
             owner's slot 20 calls an enemy: half = damage / 2 (toward zero); ONE OWN DRAW
             r; descriptor slot 0 = (0x15, half, half + int((half x r/65536) x 0.2), 0);
             damage_apply(it, owner, 100000, flags 0x40, descriptor; 0, 0).  With any hit
             the hit sound."""
        u32, w32 = self.u32, self.w32
        frame = self.frame()
        if not self.s32(obj + 0x98) < frame:
            return
        end = self.s32(obj + 0x90)
        if not (frame < end and u32(obj + 0x4C)):
            self.delete_self(obj)
            return
        left = end - frame
        radius = C.from_int(self.s32(obj + 0x9C))
        if C.lt(u32(obj + 0xA0), radius) and not s32(frame - s32(end - self.s32(obj + 0x94))) < 0x1F:
            w32(obj + 0xA0, C.add(u32(obj + 0xA0), ONE))
        glow = u32(obj + 0xA0)
        f300 = 0x43960000
        if left < 0x3D:
            size = C.fmin(C.mul(C.add(glow, glow), C.mul(C.from_int(left), DT)), f300)
        else:
            size = C.add(glow, glow)
            flicker = C.add(C.sin16(s16(frame * 3000)), C.sin16(s16(frame * 0x5DC)))
            scale = C.fmin(C.mul(C.div(u32(obj + 0xA0), radius), F_12), f300)
            size = C.add(size, C.from_int(C.to_int(C.mul(flicker, scale))))
        w32(obj + 0x6C, size)
        w32(obj + 0x74, size)
        inverse = C.div(ONE, C.mul(size, size))
        w32(obj + 0x78, inverse)
        w32(obj + 0x70, inverse)
        if rem(frame, u32(obj + 0xA8)) == 0:
            px, py, _pz = self.obj_ball(obj)
            start = (C.add(C.mul(px, radius), u32(obj + 0x10)), C.add(C.mul(py, radius), u32(obj + 0x14)),
                     C.add(u32(obj + 0x18), 0x437005B8))
            if not u32(obj + 0xB0):
                q = self.obj_ball(obj)
                aim = tuple(C.add(C.mul(q[i], radius), u32(obj + 0x10 + 4 * i)) for i in range(3))
            else:
                aim = start
            aim = (aim[0], aim[1], self.call('terrain_height', u32(G_WORLD), aim, F_12))
            d = tuple(C.sub(aim[i], start[i]) for i in range(3))
            inverse = C.rsqrt(ONE, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
            velocity = tuple(C.mul(C.mul(d[i], inverse), 0x417002D2) for i in range(3))
            block = self.call('pool_new', 0x6C)
            if block:
                self.call('FireStormFlare_ctor', block, start, velocity, u32(obj + 0xB0), u32(obj + 0xA4))
                self.hidden_draws += 1
        if rem(self.frame(), 30) == 0:
            found = self.box_around(self.vec(obj + 0x10), radius, 0x40)
            owner = u32(u32(obj + 0x4C) + 0xC)
            any_hit = False
            for other in found:
                if not self.vcall(owner, 20, other):
                    continue
                half = half_toward_zero(u32(obj + 0x8C))
                r = self.obj_rand(obj)
                extra = C.to_int(C.mul(C.mul(C.from_int(half), frac(r)), F_0_2))
                desc = descriptor((0x15, half, half + extra, 0))
                any_hit = True
                self.call('damage_apply', other, owner, 100000, 0, 0, 0x40, desc, 0, ZERO, ZERO)
            if any_hit:
                self.call('sound_playOnObject', self.call('res_find', 0x54F110, 0x54F168), obj, ONE)


SKILL_BODIES.update({0x2D532C: 'firestorm_can_use', 0x2D4F7C: 'firestorm_cast'})
OBJECT_BODIES.update({0x2D470C: 'firestorm_run'})
MODELLED.update({'SkillFireStorm_canUse': 0x2D532C, 'SkillFireStorm_cast': 0x2D4F7C, 'FireStorm_ctor': 0x2D41F8,
                 'FireStorm_ctor2': 0x2D4048, 'FireStorm_initCommon': 0x2D4480, 'FireStorm_run': 0x2D470C})


# math-library functions of tools/ref_core.py that the skills call and the test runs for real
MATH = {'mat34_setPosRotZ': 0x163B30, 'mat34_transformPoint': 0x1660A0, 'math_cos16': 0x166630,
        'math_sin16': 0x1666E0, 'math_atan2_16': 0x166798}

EXTERNALS.update({
    'PhProp_ctor': Ext(0x155A0C, 'pvpppiii', 1, 'n', '(block, position, lump, model, texture, part mask, 0x112, 0; '
                       '1.0): a debris prop; ONE SHARED DRAW inside (GameObject_ctor)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 23, Shock of Frost: SkillShockOfFrost (table 0x51a958), the bolt ShockOfFrost
    # (0xd0 bytes, table 0x51a838) and the shards FrostShard (0x7c bytes, table 0x51a8c8)
    #
    #   bolt:  +0x38 heading   +0x4c, +0x54 owner handles   +0x58..+0x90 light record
    #          +0x94 s16 level   +0x98 spin   +0x9c velocity   +0xa8, +0xb4 ribbon points
    #          +0xc0 expiry   +0xc4 "has hit"   +0xc8 Skill   +0xcc last object hit
    #   shard: +0x38 heading   +0x4c, +0x54 owner handles   +0x58 s16 level   +0x5c spin
    #          +0x60 velocity   +0x6c expiry   +0x70 "has hit"   +0x74 Skill   +0x78 excluded
    # =====================================================================================
    FROST_DEFS = (0x8E6920, 0x8E6970, 0x8E69C0)
    S_FROST_LUMP = 0x550FF8

    def shockoffrost_can_use(self, skill, caster=0):
        """SkillShockOfFrost_canUse 0x2f8b24 -> 1."""
        return 1

    def shockoffrost_cast(self, skill, level, caster, pos, facing):
        """SkillShockOfFrost_cast 0x2f8840 -> 0: pool_new(0xd0) and ShockOfFrost_ctor."""
        obj = self.call('pool_new', 0xD0)
        if obj:
            self.shockoffrost_ctor(obj, pos, facing, level, caster, skill)
        return 0

    def shockoffrost_ctor(self, obj, pos, facing, level, owner, skill):
        """ShockOfFrost_ctor 0x2f7404 (object, position, facing, level, owner, skill):
        Projectile_ctor (ONE SHARED DRAW), the light record at +0x58, the second owner
        handle, velocity (cos, sin, 0) x 350, expiry = frame + 120, the run list, the cast
        sound."""
        w32, w16 = self.w32, self.w16
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x48, 0x51A838)
        w32(obj + 0x54, 0)
        self.w8(obj + 0x61, 0)
        self.wvec(obj + 0x88, pos)
        for off, value in ((0x7C, 0x42D20000), (0x80, 0x38BE37C6), (0x84, 0x3F4D0E45), (0x74, 0x42D20000),
                           (0x78, 0x38BE37C6)):
            w32(obj + off, value)
        for off, value in ((0x6C, 0x80), (0x6E, 0xFF), (0x70, 0x96), (0x62, 0), (0x64, 0x80), (0x66, 0xFF), (0x68, 0x96),
                           (0x6A, 0)):
            w16(obj + off, value)
        self.w8(obj + 0x60, 0)
        self.call('light_link', obj + 0x58)
        if owner:
            self.call('handle_link', obj + 0x54, owner, owner)
        w16(obj + 0x94, level)
        w16(obj + 0x38, facing)
        speed = 0x43AF0000
        w32(obj + 0x9C, C.mul(C.cos16(s16(facing)), speed))
        w32(obj + 0xA0, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        w32(obj + 0xA4, 0)
        w32(obj + 0xC8, skill)
        w32(obj + 0xC4, 0)
        w32(obj + 0xC0, self.u32(G_SIM_FRAME) + 0x78)
        w32(obj + 0xCC, 0)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', self.S_FROST_LUMP, 0x551030), obj, ONE)

    def _frost_debris(self, obj, velocity_at):
        """The ice debris both objects leave: draws from the OWN generator until
        int(r/65536 x 4) is not above the number made so far (so one draw more than
        props); each prop is pool_new(0x248) + PhProp_ctor with model part 1 << i (ONE
        SHARED DRAW inside), then its velocity words +0xfc / +0x100 = old x 0.3 + (the
        projectile's velocity x 0.3) x 1.716, its +0x30 x 0.6, and PhProp_initPhysics."""
        u32, w32 = self.u32, self.w32
        made = 0
        while made < s32(C.to_int(C.mul(frac(self.obj_rand(obj)), 0x40800000))):
            block = self.call('pool_new', 0x248)
            if block:
                self.call('PhProp_ctor', block, self.vec(obj + 0x10), self.S_FROST_LUMP, 0x551000, 0x551010,
                          (1 << (made & 31)) & M32, 0x112, 0, ONE)
                self.hidden_draws += 1
                k, boost = 0x3E999999, 0x3FDBA5E3
                w32(block + 0xFC, C.add(C.mul(u32(block + 0xFC), k), C.mul(C.mul(u32(velocity_at), k), boost)))
                w32(block + 0x30, C.mul(u32(block + 0x30), 0x3F199999))
                w32(block + 0x100, C.add(C.mul(u32(block + 0x100), k), C.mul(C.mul(u32(velocity_at + 4), k), boost)))
                self.call('PhProp_initPhysics', block, 0x112)
            made += 1

    def shockoffrost_run(self, obj):
        """ShockOfFrost_run 0x2f77c0 (object), slot 4, once a frame.

          1. the light follows the bolt; two ribbon points 6 units either side, turning
             with the frame counter (frame x 4000), placed through the bolt's matrix.
          2. particles from the OWN generator: 30 and 20 of the usual kind around the
             point 12 ahead of the bolt (spread 9.04 / 7.0, speed 31.2 / 16.0), and 7
             pairs at the two ribbon points (spread 3.0, speed 5).
          3. spin -= 2000; obj_moveAndCollide with the velocity (the hit handler runs
             inside); touched something and "has hit", or the ground: expiry = 0.
          4. expiry <= frame: the hit sound, fx_spawn(10), the debris, then the shards:
             n = skill slot 13 (1, level, owner handle +0x54, cap 20); for each ONE OWN
             DRAW a gives the first heading (heading + a % 0x7fff - 0x4000), then ten OWN
             DRAWS each give a whole heading c (the draw as s16) that replaces it when
             terrain_raycast(world, position, 24 units toward c, 0; 2.0) is not above 0;
             pool_new(0x7c) and FrostShard_ctor with the owner OBJECT (read through
             +0x54 without a null test) and the last object hit as the one to skip.
             The bolt deletes itself."""
        u32, w32 = self.u32, self.w32
        self.wvec(obj + 0x88, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x58)
        matrix = C.mat34_set_pos_rot_z(self.vec(obj + 0x10), s16(self.u16(obj + 0x38) - 0x7FFF))
        six = 0x40C00000
        turn = s16(self.frame() * 4000)
        w32(obj + 0xA8, 0)
        w32(obj + 0xAC, C.mul(C.cos16(turn), six))
        w32(obj + 0xB0, C.mul(C.sin16(turn), six))
        w32(obj + 0xB4, 0)
        w32(obj + 0xB8, C.mul(C.neg(C.cos16(turn)), six))
        w32(obj + 0xBC, C.mul(C.neg(C.sin16(turn)), six))
        for base in (obj + 0xA8, obj + 0xB4):
            point = C.mat34_transform_point(matrix, self.vec(base))
            for i in range(3):
                w32(base + 4 * i, point[i])
        ball = lambda: self.obj_ball(obj)
        defs = self.FROST_DEFS
        for definition, count, spread, speed in ((defs[0], 30, 0x41109750, 0x41F995ED), (defs[1], 20, 0x40DFFF27, 0x41800003)):
            for _ in range(count):
                b = ball()
                heading = self.s16(obj + 0x38)
                x = C.add(C.add(C.mul(b[0], spread), C.mul(C.cos16(heading), F_12)), u32(obj + 0x10))
                y = C.add(C.add(C.mul(b[1], spread), C.mul(C.sin16(heading), F_12)), u32(obj + 0x14))
                z = C.add(C.mul(b[2], spread), u32(obj + 0x18))
                self.puff(ball, definition, (x, y, z), None, speed)
        for _ in range(7):
            self.puff(ball, defs[2], self.vec(obj + 0xA8), 0x403FFFEF, 0x40A00000)
            self.puff(ball, defs[2], self.vec(obj + 0xB4), 0x403FFFEF, 0x40A00000)
        w32(obj + 0x98, u32(obj + 0x98) - 2000)
        hit = self.move_and_collide(obj, self.vec(obj + 0x9C))
        if hit & 2 and u32(obj + 0xC4):
            w32(obj + 0xC0, 0)
        if hit & 1:
            w32(obj + 0xC0, 0)
        if self.frame() < self.s32(obj + 0xC0):
            return
        self.call('sound_playOnObject', self.call('res_find', self.S_FROST_LUMP, 0x551048), obj, ONE)
        self.call('fx_spawn', 10, self.vec(obj + 0x10))
        self._frost_debris(obj, obj + 0x9C)
        count = s32(self.skill_call(u32(obj + 0xC8), 13, 1, self.s16(obj + 0x94), obj + 0x54, 0x14))
        for _ in range(max(count, 0)):
            heading = s16(self.u16(obj + 0x38) + self.obj_rand(obj) % 0x7FFF - 0x4000)
            for _try in range(10):
                c = s16(self.obj_rand(obj))
                tx = C.add(u32(obj + 0x10), C.mul(C.cos16(c), F_24))
                ty = C.add(u32(obj + 0x14), C.mul(C.sin16(c), F_24))
                tz = u32(obj + 0x18)
                toward = (C.sub(tx, u32(obj + 0x10)), C.sub(ty, u32(obj + 0x14)), C.sub(tz, u32(obj + 0x18)))
                t = self.call('terrain_raycast', u32(G_WORLD), self.vec(obj + 0x10), toward, 0, TWO)
                if not C.lt(ZERO, t):
                    heading = c
            block = self.call('pool_new', 0x7C)
            if block:
                self.frostshard_ctor(block, self.vec(obj + 0x10), heading, self.s16(obj + 0x94),
                                     u32(u32(obj + 0x54) + 0xC), u32(obj + 0xC8), u32(obj + 0xCC))
        self.delete_self(obj)

    def _frost_hit(self, obj, other, stat, level, hit_off):
        """The damage both hit handlers share.  Returns False when the object is let
        through.  A creature is hit only when there is no owner (then with no attacker) or
        the owner's slot 20 calls it an enemy; anything that is not a creature sets "has
        hit" and is "damaged" too, with no attacker.  A creature that is not a player and
        has creature flag 0x200 is passed through.  d = skill slot 13 (stat, level, owner
        handle +0x4c, cap 0); ONE OWN DRAW r; descriptor slot 0 = (0x16, d, d + int((d x
        0.2) x r/65536), 0); damage_apply(other, attacker, 100000, flags 0, descriptor;
        0, 0)."""
        u32 = self.u32
        attacker = 0
        flags = u32(other + 0xC)
        if flags & 0x20:
            if u32(obj + 0x4C):
                attacker = self.handle_obj(obj + 0x4C)
                if not self.vcall(attacker, 20, other):
                    return False
        else:
            self.w32(obj + hit_off, 1)
        if other and not flags & 0x40 and flags & 0x20 and self.u64(other + 0xA8) & 0x200:
            return False
        skill = u32(obj + (0xC8 if hit_off == 0xC4 else 0x74))
        d = self.skill_call(skill, 13, stat, level, obj + 0x4C, 0)
        scaled = C.mul(C.from_int(s32(d)), F_0_2)
        extra = C.to_int(C.mul(scaled, frac(self.obj_rand(obj))))
        self.call('damage_apply', other, attacker, 100000, 0, 0, 0, descriptor((0x16, d, d + extra, 0)), 0, ZERO, ZERO)
        return True

    def shockoffrost_hit(self, obj, other):
        """ShockOfFrost_onHit 0x2f84e4 (object, other), slot 6.  There is no "already hit"
        test: every object overlapped in a frame is handled.  "Last hit" +0xcc is cleared
        first; after the damage (statistic 0) it is the object, and "has hit" is 1."""
        self.w32(obj + 0xCC, 0)
        if self._frost_hit(obj, other, 0, self.s16(obj + 0x94), 0xC4):
            self.w32(obj + 0xCC, other)
            self.w32(obj + 0xC4, 1)

    def frostshard_ctor(self, obj, pos, facing, level, owner, skill, exclude):
        """FrostShard_ctor 0x2f68e0 (object, position, facing, level, owner, skill, excluded
        object): Projectile_ctor (ONE SHARED DRAW), the second owner handle, velocity
        (cos, sin, 0) x 350, expiry = frame + 60, the run list."""
        w32 = self.w32
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x48, 0x51A8C8)
        w32(obj + 0x54, 0)
        if owner:
            self.call('handle_link', obj + 0x54, owner, owner)
        self.w16(obj + 0x58, level)
        self.w16(obj + 0x38, facing)
        speed = 0x43AF0000
        w32(obj + 0x60, C.mul(C.cos16(s16(facing)), speed))
        w32(obj + 0x64, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        w32(obj + 0x68, 0)
        w32(obj + 0x74, skill)
        w32(obj + 0x78, exclude)
        w32(obj + 0x6C, self.u32(G_SIM_FRAME) + 0x3C)
        w32(obj + 0x70, 0)
        self.call('obj_runEveryFrame', obj)

    def frostshard_run(self, obj):
        """FrostShard_run 0x2f6b3c (object), slot 4: 30 + 20 particles around the shard
        (OWN generator), spin -= 2000, obj_moveAndCollide, the two expiry rules; at the
        end ONE OWN DRAW picks the sound (clip number r % 3 + 1), fx_spawn(10), the
        debris, and the shard deletes itself."""
        u32, w32 = self.u32, self.w32
        ball = lambda: self.obj_ball(obj)
        defs = self.FROST_DEFS
        for definition, count, spread, speed in ((defs[0], 30, 0x41109750, 0x41F995ED), (defs[1], 20, 0x40DFFF27, 0x41800003)):
            for _ in range(count):
                self.puff(ball, definition, self.vec(obj + 0x10), spread, speed)
        w32(obj + 0x5C, u32(obj + 0x5C) - 2000)
        hit = self.move_and_collide(obj, self.vec(obj + 0x60))
        if hit & 2 and u32(obj + 0x70):
            w32(obj + 0x6C, 0)
        if hit & 1:
            w32(obj + 0x6C, 0)
        if self.frame() < self.s32(obj + 0x6C):
            return
        text = self.call('libc_sprintf', 0x551020, self.obj_rand(obj) % 3 + 1)
        self.call('sound_playAtPos', self.call('res_find', self.S_FROST_LUMP, text), self.vec(obj + 0x10), ONE)
        self.call('fx_spawn', 10, self.vec(obj + 0x10))
        self._frost_debris(obj, obj + 0x60)
        self.delete_self(obj)

    def frostshard_hit(self, obj, other):
        """FrostShard_onHit 0x2f71ac (object, other), slot 6: nothing once it has hit, and
        nothing for the excluded object (the one the bolt hit last); otherwise the bolt's
        handler with statistic 2."""
        if self.u32(obj + 0x70) or other == self.u32(obj + 0x78):
            return
        if self._frost_hit(obj, other, 2, self.s16(obj + 0x58), 0x70):
            self.w32(obj + 0x70, 1)


SKILL_BODIES.update({0x2F8B24: 'shockoffrost_can_use', 0x2F8840: 'shockoffrost_cast'})
OBJECT_BODIES.update({0x2F77C0: 'shockoffrost_run', 0x2F84E4: 'shockoffrost_hit', 0x2F6B3C: 'frostshard_run',
                      0x2F71AC: 'frostshard_hit'})
MODELLED.update({'SkillShockOfFrost_canUse': 0x2F8B24, 'SkillShockOfFrost_cast': 0x2F8840, 'ShockOfFrost_ctor': 0x2F7404,
                 'ShockOfFrost_run': 0x2F77C0, 'ShockOfFrost_onHit': 0x2F84E4, 'FrostShard_ctor': 0x2F68E0,
                 'FrostShard_run': 0x2F6B3C, 'FrostShard_onHit': 0x2F71AC})


EXTERNALS.update({
    'trail_create': Ext(0x190FF8, 'iiiiiii', 1, 'i', '(seven integers; width) -> trail handle or 0'),
    'trail_addPoint': Ext(0x192550, 'iv', 0, 'n', '(trail handle, position)'),
    'terrain_heightAtPoint': Ext(0x182F28, 'pv', 0, 'f', '(world, position) -> the ground exactly under the point'),
})
EXTERNALS['sound_stop'] = Ext(0x213EA0, 'i', 0, 'n', '(sound handle)')


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 16, Holy Strike: SkillHolyStrike (table 0x51a108) and the projectile HolyStrike
    # (0x80 bytes, table 0x51a078)
    #
    #   +0x38 heading   +0x4c, +0x54 owner handles   +0x58 list of candidate targets
    #   +0x5c s16 level   +0x60 expiry   +0x64 homing starts after   +0x68 Skill
    #   +0x6c velocity   +0x78 "has hit"   +0x7c trail handle
    # =====================================================================================
    HOLYSTRIKE_DEFS = (0x8E61D0, 0x8E6220, 0x8E6270)

    def holystrike_can_use(self, skill, caster=0):
        """SkillHolyStrike_canUse 0x2ed20c -> 1."""
        return 1

    def holystrike_cast(self, skill, level, caster, pos, facing):
        """SkillHolyStrike_cast 0x2ecfcc -> 0: both flash quads of the caster = (0xff, 200,
        0x87, 0x40) (no null test), pool_new(0x80), HolyStrike_ctor."""
        self.flash_both(caster, 0xFF, 200, 0x87, 0x40)
        obj = self.call('pool_new', 0x80)
        if obj:
            self.holystrike_ctor(obj, facing, level, pos, caster, skill)
        return 0

    def holystrike_ctor(self, obj, facing, level, pos, owner, skill):
        """HolyStrike_ctor 0x2eba48 (object, facing, level, position, owner, skill):
        Projectile_ctor (ONE SHARED DRAW); homing from frame + 15, expiry frame + 180;
        velocity (cos, sin, 0) x 450; a trail; then the candidate list +0x58:
        world_collectObjectsInArc(position, heading, the list, filter; 360, 75 degrees,
        0), the filter being the owner when it has object flag 0x20 - so the list holds
        the owner's enemies, nearest first, and it is a list in the object, not a
        handle: it keeps a deleted target's node until the node is reused."""
        w32, u32 = self.w32, self.u32
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x54, 0)
        self.w16(obj + 0x38, facing)
        w32(obj + 0x48, 0x51A078)
        w32(obj + 0x58, 0)
        if owner:
            self.call('handle_link', obj + 0x54, owner, owner)
        self.w16(obj + 0x5C, level)
        frame = u32(G_SIM_FRAME)
        w32(obj + 0x68, skill)
        w32(obj + 0x64, frame + 0xF)
        w32(obj + 0x60, frame + 0xB4)
        speed = 0x43E10000
        w32(obj + 0x6C, C.mul(C.cos16(self.s16(obj + 0x38)), speed))
        w32(obj + 0x74, 0)
        w32(obj + 0x78, 0)
        w32(obj + 0x70, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        trail = self.call('trail_create', 1, 0xFA, 0, 0xFA, 200, 100, 0x80, F_0_2)
        w32(obj + 0x7C, trail)
        self.call('trail_addPoint', trail, self.vec(obj + 0x10))
        who = owner if owner and u32(owner + 0xC) & 0x20 else 0
        self.call('world_collectObjectsInArc', self.vec(obj + 0x10), self.s16(obj + 0x38), obj + 0x58, who,
                  0x43B40000, 0x42960000, ZERO)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', 0x5506C0, 0x5506C8), obj, ONE)

    def holystrike_run(self, obj):
        """HolyStrike_run 0x2ebc50 (object), slot 4, once a frame.

          1. particles (OWN generator): 5, 10 and 9 of the usual kind; a trail point.
          2. homing, with a non-empty list and frame > +0x64: the target is the object of
             the list's FIRST node (not tested for null); rate = skill slot 10 (2, level)
             x 182; the turn is DiseaseBolt's (the difference is not wrapped).
          3. obj_moveAndCollide; the two expiry rules.
          4. expiry <= frame: the sound, a LightEffect (pool_new 0xbc; ONE SHARED DRAW
             inside), 25 x three particles, and the object deletes itself."""
        u32, w32 = self.u32, self.w32
        ball = lambda: self.obj_ball(obj)
        defs = self.HOLYSTRIKE_DEFS
        for definition, count, spread, speed in ((defs[0], 5, 0x40EFFFDC, 0x41800000), (defs[1], 10, 0x411FFF59, 0x4147FF03),
                                                 (defs[2], 9, 0x411FFFCA, 0x419FFFCF)):
            for _ in range(count):
                self.puff(ball, definition, self.vec(obj + 0x10), spread, speed)
        self.call('trail_addPoint', u32(obj + 0x7C), self.vec(obj + 0x10))
        if u32(obj + 0x58) and self.s32(obj + 0x64) < self.frame():
            rate = s32(s32(self.skill_call(u32(obj + 0x68), 10, 2, self.s16(obj + 0x5C))) * 0xB6)
            target = u32(u32(obj + 0x58) + 0xC)
            diff = C.atan2_16(C.sub(u32(target + 0x14), u32(obj + 0x14)), C.sub(u32(target + 0x10), u32(obj + 0x10))) \
                - self.s16(obj + 0x38)
            heading = self.u16(obj + 0x38)
            if abs(diff) < rate:
                heading += diff
            elif diff <= 0:
                heading -= rate
            else:
                heading += rate
            self.w16(obj + 0x38, heading)
            speed = 0x43E10000
            w32(obj + 0x6C, C.mul(C.cos16(self.s16(obj + 0x38)), speed))
            w32(obj + 0x74, 0)
            w32(obj + 0x70, C.mul(C.sin16(self.s16(obj + 0x38)), speed))
        hit = self.move_and_collide(obj, self.vec(obj + 0x6C))
        if hit & 2 and u32(obj + 0x78):
            w32(obj + 0x60, 0)
        if hit & 1:
            w32(obj + 0x60, 0)
        if self.frame() < self.s32(obj + 0x60):
            return
        self.call('sound_playOnObject', self.call('res_find', 0x5506C0, 0x5506E0), obj, ONE)
        self.light_effect(0xBC, self.vec(obj + 0x10), 0, 0, 0x437F0000, 0x43480000, 0x43070000, 0xC2000000, ZERO, ZERO,
                          ZERO, ZERO, 0x43700000, 0x42F00000, HALF, ONE)
        for _ in range(25):
            self.puff(ball, defs[0], self.vec(obj + 0x10), 0x40EFFFDC, 0x42C00000)
            self.puff(ball, defs[1], self.vec(obj + 0x10), 0x411FFF59, 0x4295FF42)
            self.puff(ball, defs[2], self.vec(obj + 0x10), 0x411FFFCA, 0x42EFFFB6)
        self.delete_self(obj)

    def holystrike_hit(self, obj, other):
        """HolyStrike_onHit 0x2ecae8 (object, other), slot 6.

        Nothing once it has hit; with an owner (handle +0x54) only what the owner's slot
        20 calls an enemy; a creature that is not a player and has creature flag 0x200 is
        passed through.  d = skill slot 10 (1 when the byte at other +0xb4 is 0x10
        (undead), else 0; level).  TWO OWN DRAWS: the first only chooses the rounding
        (the sign of d + d x r1/65536 x 0.2 + 0.5), the second gives max = int(d + (d x
        r2/65536) x 0.2 + 1.0) - one more than the usual rounding would give.
        damage_apply(other, owner or 0, 100000, flags 0x80000 - 0 in PvP mode A, an empty
        descriptor, 0; d, max); the target's two flash quads; "has hit" = 1."""
        u32 = self.u32
        if u32(obj + 0x78):
            return
        if u32(obj + 0x54):
            if not self.vcall(self.handle_obj(obj + 0x54), 20, other):
                return
        flags = u32(other + 0xC)
        if not flags & 0x40 and flags & 0x20 and self.u64(other + 0xA8) & 0x200:
            return
        stat = 1 if self.s8(other + 0xB4) == 0x10 else 0
        amount = C.from_int(s32(self.skill_call(u32(obj + 0x68), 10, stat, self.s16(obj + 0x5C))))
        how = 0 if u32(G_PVP_MODE_A) else 0x80000
        probe = C.add(spread_max(amount, self.obj_rand(obj)), HALF)
        rolled = spread_max(amount, self.obj_rand(obj))
        if C.le(ZERO, probe):
            high = C.to_int(C.add(rolled, ONE))
        else:
            high = C.to_int(C.sub(C.add(rolled, HALF), HALF))
        self.call('damage_apply', other, self.handle_obj(obj + 0x54), 100000, 0, 0, how, descriptor(), 0,
                  amount, C.from_int(s32(high)))
        self.w32(obj + 0x78, 1)
        self.flash_both(other, 0xFF, 200, 0x87, 0x40)

    # =====================================================================================
    # Skill 24, Poison Rain: SkillPoisonRain (table 0x51aaf8) and the area object
    # PoisonRain (0x6c bytes, table 0x51aa68).  Tier 1 of the skill is all zero: a monster
    # skill.
    #
    #   +0x4c end frame   +0x50 start frame   +0x54 radius (float)   +0x58 strength
    #   +0x5c level   +0x60 Skill   +0x64 owner handle   +0x68 sound handle or -1
    # =====================================================================================
    def poisonrain_can_use(self, skill, caster=0):
        """SkillPoisonRain_canUse 0x2f9dec -> 1."""
        return 1

    def poisonrain_cast(self, skill, level, caster, pos, facing):
        """SkillPoisonRain_cast 0x2f9a3c -> 0: Fire Storm's placement (r = slot 12 (1,
        level, caster, cap 10); r x 12 ahead for a player caster; z = terrain_height(...;
        (float) r) + 12), pool_new(0x6c), PoisonRain_ctor with no sound."""
        r = self.skill_call(skill, 12, 1, level, caster, 10)
        reach = C.from_int(s32(r))
        ox = oy = ZERO
        if self.u32(caster + 0xC) & 0x40:
            ox = C.mul(C.mul(C.cos16(s16(facing)), reach), F_12)
            oy = C.mul(C.mul(C.sin16(s16(facing)), reach), F_12)
        x, y = C.add(ox, pos[0]), C.add(oy, pos[1])
        ground = self.call('terrain_height', self.u32(G_WORLD), (x, y, ZERO), reach)
        centre = (x, y, C.add(C.add(ZERO, ground), F_12))
        obj = self.call('pool_new', 0x6C)
        if obj:
            self.poisonrain_ctor(obj, level, caster, centre, skill, 0)
        return 0

    def poisonrain_ctor(self, obj, level, owner, pos, skill, sound):
        """PoisonRain_ctor 0x2f8f48 (object, level, owner, position, skill, sound entry or
        0).

        GameObject_ctor (ONE SHARED DRAW); flags |= 0x421b; the owner handle +0x64 is
        linked and the owner's flags read WITHOUT a null test.  Radius +0x54 = (float)
        (slot 13 (1, level, handle, cap 10) x 12).  Start +0x50 = int(frame + 40.499996)
        for a creature that is not a player, else 0; end +0x4c = start + slot 13 (2, ...,
        cap 10) x 60 - so for a player owner the end is an absolute frame number.  A
        LightEffect (pool_new 0xbc; ONE SHARED DRAW inside) whose last number is that
        duration statistic again + 0.675.  Strength +0x58 = slot 13 (0, ..., cap 0);
        sound handle +0x68 = -1, or the given sound started on the object."""
        w32, u32 = self.w32, self.u32
        self.gameobject_ctor(obj, pos, 0, 0)
        w32(obj + 0x48, 0x51AA68)
        w32(obj + 0x5C, level)
        w32(obj + 0xC, u32(obj + 0xC) | 0x421B)
        w32(obj + 0x60, skill)
        w32(obj + 0x64, 0)
        handle = obj + 0x64
        self.call('handle_link', handle, owner, owner)
        skill = u32(obj + 0x60)
        w32(obj + 0x54, C.from_int(s32(s32(self.skill_call(skill, 13, 1, u32(obj + 0x5C), handle, 10)) * 12)))
        if u32(owner + 0xC) & 0x60 == 0x20:
            w32(obj + 0x50, C.to_int(C.add(C.from_int(self.frame()), 0x4221FFFF)))
        else:
            w32(obj + 0x50, 0)
        seconds = self.skill_call(u32(obj + 0x60), 13, 2, u32(obj + 0x5C), handle, 10)
        w32(obj + 0x4C, u32(obj + 0x50) + s32(seconds) * 60)
        block = self.call('pool_new', 0xBC)
        if block:
            radius = u32(obj + 0x54)
            f300 = 0x43960000
            again = self.skill_call(u32(obj + 0x60), 13, 2, u32(obj + 0x5C), handle, 10)
            self.call('LightEffect_ctor', block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_12)), 0, 1,
                      ZERO, 0x437F0000, ZERO, 0x42C80000, ZERO, 0x437F0000, ZERO, 0x42C80000,
                      C.fmin(f300, radius), C.fmin(f300, C.add(radius, radius)), 0x3F266666,
                      C.add(C.from_int(s32(again)), 0x3F2CCCCC))
            self.hidden_draws += 1
        w32(obj + 0x58, self.skill_call(u32(obj + 0x60), 13, 0, u32(obj + 0x5C), handle, 0))
        w32(obj + 0x68, M32)
        if sound:
            w32(obj + 0x68, self.call('sound_playOnObject', sound, obj, ONE))
        self.call('obj_runEveryFrame', obj)

    def poisonrain_run(self, obj):
        """PoisonRain_run 0x2f9254 (object), slot 4, once a frame.

          1. nothing until frame > start.
          2. frame >= end, or the owner handle is empty: sound_stop, a LightEffect
             (pool_new 0xbc; ONE SHARED DRAW inside), and the object deletes itself.
          3. particles from the OWN generator.  Drops: while (float) i < ((R x 0.40243298)
             x (R x 3.1415899)) x 0.006944444 - three draws each (direction, distance,
             height).  Splashes: the same count with 0.40464997 - four draws each
             (direction, distance, two velocity bits), each asking terrain_heightAtPoint.
          4. frame % 30 == 0: every object of the box centre -/+ (float) int(R) (capacity
             64) that the owner's slot 20 calls an enemy: d = slot 13 (0, level, handle,
             cap 0); ONE OWN DRAW r; descriptor slot 0 = (0x17, d, d + int((d x r/65536)
             x 0.2), 0); damage_apply(it, owner, 100000, flags 0x40, descriptor; 0, 0)."""
        u32, w32 = self.u32, self.w32
        frame = self.frame()
        if not self.s32(obj + 0x50) < frame:
            return
        if not (frame < self.s32(obj + 0x4C) and u32(obj + 0x64)):
            self.call('sound_stop', u32(obj + 0x68))
            radius = u32(obj + 0x54)
            pos = (C.add(u32(obj + 0x10), ZERO), u32(obj + 0x14), C.add(u32(obj + 0x18), F_12))
            self.light_effect(0xBC, pos, 0, 1, ZERO, 0x437F0000, ZERO, 0x42C80000, ZERO, 0x437F0000, ZERO, 0x42C80000,
                              C.fmin(0x43960000, C.add(radius, radius)), ZERO, 0x3F266666, HALF)
            self.delete_self(obj)
            return
        base = self.vec(obj + 0x10)

        def count(k):
            radius = u32(obj + 0x54)
            return C.mul(C.mul(C.mul(radius, k), C.mul(radius, 0x40490FCF)), 0x3BE38E38)

        i = 0
        while C.lt(C.from_int(i), count(0x3ECE0BB2)):
            angle = s16(self.obj_rand(obj))
            dist = frac(self.obj_rand(obj))
            i += 1
            px = C.mul(C.cos16(angle), C.mul(dist, u32(obj + 0x54)))
            py = C.mul(C.sin16(angle), C.mul(dist, u32(obj + 0x54)))
            high = self.obj_rand(obj) % 200
            point = (C.add(px, base[0]), C.add(py, base[1]),
                     C.add(C.add(C.add(0x43480000, C.from_int(high)), 0xC2C80000), base[2]))
            self.call('particle_spawn', 0x8E6A10, point, (ZERO, ZERO, 0xC2A00000), ZERO)
        i = 0
        while C.lt(C.from_int(i), count(0x3ECF2E48)):
            angle = s16(self.obj_rand(obj))
            dist = frac(self.obj_rand(obj))
            i += 1
            px = C.mul(C.cos16(angle), C.mul(dist, u32(obj + 0x54)))
            py = C.mul(C.sin16(angle), C.mul(dist, u32(obj + 0x54)))
            vx = C.add(C.from_int(self.obj_rand(obj) & 1), 0xBF800000)
            vy = C.add(C.from_int(self.obj_rand(obj) & 1), 0xBF800000)
            point = (C.add(px, base[0]), C.add(py, base[1]), C.add(ZERO, base[2]))
            ground = self.call('terrain_heightAtPoint', u32(G_WORLD), point)
            point = (point[0], point[1], C.add(ground, 0x40A00000))
            self.call('particle_spawn', 0x8E6A60, point, (vx, vy, ZERO), ZERO)
        if rem(self.frame(), 30) != 0:
            return
        half = C.from_int(s32(C.to_int(u32(obj + 0x54))))
        found = self.box_around(self.vec(obj + 0x10), half, 0x40)
        owner = u32(u32(obj + 0x64) + 0xC)
        for other in found:
            if not self.vcall(owner, 20, other):
                continue
            d = self.skill_call(u32(obj + 0x60), 13, 0, u32(obj + 0x5C), obj + 0x64, 0)
            extra = C.to_int(C.mul(C.mul(C.from_int(s32(d)), frac(self.obj_rand(obj))), F_0_2))
            self.call('damage_apply', other, owner, 100000, 0, 0, 0x40, descriptor((0x17, d, d + extra, 0)), 0, ZERO, ZERO)


SKILL_BODIES.update({0x2ED20C: 'holystrike_can_use', 0x2ECFCC: 'holystrike_cast',
                     0x2F9DEC: 'poisonrain_can_use', 0x2F9A3C: 'poisonrain_cast'})
OBJECT_BODIES.update({0x2EBC50: 'holystrike_run', 0x2ECAE8: 'holystrike_hit', 0x2F9254: 'poisonrain_run'})
MODELLED.update({'SkillHolyStrike_canUse': 0x2ED20C, 'SkillHolyStrike_cast': 0x2ECFCC, 'HolyStrike_ctor': 0x2EBA48,
                 'HolyStrike_run': 0x2EBC50, 'HolyStrike_onHit': 0x2ECAE8,
                 'SkillPoisonRain_canUse': 0x2F9DEC, 'SkillPoisonRain_cast': 0x2F9A3C, 'PoisonRain_ctor': 0x2F8F48,
                 'PoisonRain_run': 0x2F9254})


EXTERNALS.update({
    'LostSoul_ctor': Ext(0x2931BC, 'pvviiii', 0, 'n', '(block, position, velocity, angle, owner, mode, light): a rising '
                         'trail, visual; ONE SHARED DRAW inside (GameObject_ctor)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skills 2 (and 83) Dodge, 19 Regeneration, 3 Resist Poison, 25 Disease Weapons,
    # 27 Hate Beam, 28 Ball Of Hate, 30 Hate Effect: Skill objects that only answer for
    # numbers.  Their cast is the base (or an own function that also returns 0), can-use the
    # base; what is modelled is the helper other code calls.
    # =====================================================================================
    def passive_cast(self, skill, level=0, caster=0, pos=None, facing=0):
        """SkillRiposte_cast 0x2ddb90 and SkillRegeneration_cast 0x2f1440 -> 0 (the same
        body as the base cast: the position is copied to the stack and dropped)."""
        return 0

    def dodge_fraction(self, skill, rank):
        """SkillDodge_getStat0Fraction 0x2e8ac0 (skill, rank) -> float: 0.0 at rank 0, else
        (float) slot 10 (0, slot 14 (rank, 1)) x 0.01 (0x3c23d70a).  MissileWeapon_onTouch
        0x152a18 multiplies it by 100 again and truncates, which under this FPU gives one
        less than the statistic at many ranks (docs/spec/skills-01-34.md, section 2)."""
        if not rank:
            return ZERO
        level = self.skill_call(skill, 14, rank, 1)
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), 0x3C23D70A)

    def regeneration_stat0(self, skill, level):
        """SkillRegeneration_getStat0 0x2f14f0 (skill, rank) -> slot 10 (0, rank): the
        percentage Player_regenMana 0x1b3900 adds."""
        return self.skill_call(skill, 10, 0, level)

    # =====================================================================================
    # Skill 9 (and 82) Riposte: SkillRiposte (table 0x519528).  Passive; damage_apply calls
    # the counter-attack (0x1ea568, 0x1ea5c8).
    # =====================================================================================
    def riposte_counter_attack(self, skill, defender, attacker, level):
        """SkillRiposte_counterAttack 0x2ddccc (skill, defender, attacker, level).

        Nothing at level 0.  dmg = slot 12 (0, level, defender, cap 10), chance = slot 12
        (1, ...).  ONE SHARED DRAW d; when int((d/65536) x 100) < chance: both flash quads
        of the defender = (0x82, 0x82, 0x83, 0x55); then ONLY IF the defender's model
        (slot 16) reports sample points: 200 particles toward the attacker placed with the
        presentation generator (per particle: one draw for the point, a ball; every second
        one a spark as well), ONE SHARED DRAW d2 and damage_apply(attacker, defender,
        100000, flags 0x40, an empty descriptor, no-crit 1; dmg, dmg + (dmg x d2/65536) x
        0.2).  A model without sample points means no counter-hit and no second draw."""
        u32 = self.u32
        if not level:
            return
        dmg = self.skill_call(skill, 12, 0, level, defender, 10)
        chance = self.skill_call(skill, 12, 1, level, defender, 10)
        if not s32(C.to_int(C.mul(frac(self.draw()), 0x42C80000))) < s32(chance):
            return
        self.flash_both(defender, 0x82, 0x82, 0x83, 0x55)
        count = s32(self.call('model_getSamplePointCount', self.vcall(defender, 16)))
        if not count:
            return
        for i in range(200):
            model = self.vcall(defender, 16)
            index = rem(self.cosmetic_draw(), count)
            point = tuple(self.call('model_getSamplePoint', model, defender + 0x114, self.vec(defender + 0x10),
                                    self.s16(defender + 0x38), index, 0, 0, ONE))
            x, y, z = self._cosmetic_ball()
            toward = tuple(C.sub(u32(attacker + 0x10 + 4 * k), u32(defender + 0x10 + 4 * k)) for k in range(3))
            k = 0x424ABC67
            self.call('particle_spawn', 0x8E5AA0, point, toward, ZERO)
            if i & 1:
                self.call('particle_spawn', 0x8E5AF0, point, (C.mul(x, k), C.mul(y, k), C.mul(z, k)), ZERO)
        amount = C.from_int(s32(dmg))
        high = spread_max(amount, self.draw())
        self.call('damage_apply', attacker, defender, 100000, 0, 0, 0x40, descriptor(), 1, amount, high)

    # =====================================================================================
    # Skill 21, Repulse Undead: SkillRepulseUndead (table 0x51a728).  The cast is the whole
    # skill; damage_radial 0x1ead58 has no other caller.
    # =====================================================================================
    def repulse_cast(self, skill, level, caster, pos, facing=0):
        """SkillRepulseUndead_cast 0x2f4d34 (skill, level, caster, position, facing) -> 0.

        For a = 0, step, 2 x step ... while a <= 0xffff, step = 0x10000 / (level + 4): a
        LostSoul (pool_new 0xb0; ONE SHARED DRAW inside) at the position + 36 up with
        velocity (cos a x 450, sin a x 450, 50), mode 1, no owner, no light.  A LightEffect
        (pool_new 0xbc; ONE SHARED DRAW inside).  dmg = slot 10 (0, level), r = slot 10 (1,
        level); damage_radial(caster, position, dmg, flags 0xa100900, minimum 0, skip
        object flag 0x40; inner r x 12, outer r x 24); the sound at the position."""
        speed = 0x43E10000
        up = (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x42100000))
        step = quot(0x10000, s32(level) + 4)
        a = 0
        while True:
            velocity = (C.mul(C.cos16(s16(a)), speed), C.mul(C.sin16(s16(a)), speed), 0x42480000)
            block = self.call('pool_new', 0xB0)
            if block:
                self.call('LostSoul_ctor', block, up, velocity, a, 0, 1, 0)
                self.hidden_draws += 1
            a = s32(a + step)
            if 0xFFFF < a:
                break
        self.light_effect(0xBC, up, 0, 0, 0x42C80000, 0x42C80000, 0x437F0000, 0xC2C00000, ZERO, ZERO, ZERO, ZERO,
                          0x42F00000, 0x43B40000, ZERO, ONE)
        dmg = self.skill_call(skill, 10, 0, level)
        r = s32(self.skill_call(skill, 10, 1, level))
        self.damage_radial(caster, pos, dmg, 0xA100900, 0, 0x40, C.from_int(s32(r * 12)), C.from_int(s32(r * 24)))
        self.call('sound_playAtPos', self.call('res_find', 0x550E50, 0x550E58), tuple(pos), ONE)
        return 0

    def damage_radial(self, attacker, pos, dmg, flags, minimum, skip, inner, outer):
        """damage_radial 0x1ead58 (attacker, position, damage, flags, minimum, skip mask;
        inner, outer).

        Every object of the box position -/+ outer (capacity 128), in the order returned:
          * not a creature (object flag 0x20): skipped when flags has 0x8000000;
          * a creature: with flag 0x8000000 only kind 0x10 (undead, byte +0xb4); and when
            the attacker is a creature only what its slot 20 calls an enemy;
          * never the attacker itself, nor an object with a flag of the skip mask;
          * dist = (|dx| + |dy|) - min(|dx|, |dy|) x 0.333 - the object's radius; inside
            outer: amount = min(max((outer - dist) x scale, minimum), damage) with scale
            = damage / (outer - inner), or 100 when outer - inner is not above 1; the
            object's slot 2 (take damage) is called directly with (attacker, flags;
            (float) int(amount)) - no hit roll, no armour, no draw."""
        u32 = self.u32
        found = self.box_around(pos, outer, 0x80)
        full = C.from_int(s32(dmg))
        scale = 0x42C80000
        if C.lt(ONE, C.sub(outer, inner)):
            scale = C.div(full, C.sub(outer, inner))
        for other in found:
            if u32(other + 0xC) & 0x20:
                if flags & 0x8000000 and self.s8(other + 0xB4) != 0x10:
                    continue
                if attacker and u32(attacker + 0xC) & 0x20 and not self.vcall(attacker, 20, other):
                    continue
            elif flags & 0x8000000:
                continue
            if other == attacker or u32(other + 0xC) & skip:
                continue
            dy = C.fabs(C.sub(u32(other + 0x14), pos[1]))
            dx = C.fabs(C.sub(u32(other + 0x10), pos[0]))
            dist = C.sub(C.sub(C.add(dx, dy), C.mul(C.fmin(dx, dy), 0x3EAA7EF9)), u32(other + 0x1C))
            if C.le(outer, dist):
                continue
            amount = C.mul(C.sub(outer, dist), scale)
            least = C.from_int(s32(minimum))
            if C.lt(amount, least):
                amount = least
            amount = C.fmin(amount, full)
            self.vcall(other, 2, attacker, flags, C.from_int(s32(C.to_int(amount))))


SKILL_BODIES.update({0x2DDB90: 'passive_cast', 0x2F1440: 'passive_cast', 0x2F4D34: 'repulse_cast'})
MODELLED.update({'SkillRiposte_cast': 0x2DDB90, 'SkillRegeneration_cast': 0x2F1440, 'SkillDodge_getStat0Fraction': 0x2E8AC0,
                 'SkillRegeneration_getStat0': 0x2F14F0, 'SkillRiposte_counterAttack': 0x2DDCCC,
                 'SkillRepulseUndead_cast': 0x2F4D34, 'damage_radial': 0x1EAD58})


G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440        # the all-players alive list (slots)

EXTERNALS.update({
    'particleGroup_create': Ext(0x18E880, '', 0, 'i', '() -> group handle or 0'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n', '(group): the particles that follow go into the group'),
    'particleGroup_setMatrix': Ext(0x18E9E8, 'im', 0, 'n', '(group, matrix)'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n', '(group)'),
    'hud_showMessage': Ext(0x1D92A0, 'piii', 0, 'n', '(text, frames, slot, force): local output'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n', '(light record)'),
    'sound_playAtPos': Ext(0x214428, 'pv', 1, 'i', '(entry, position; volume) -> sound handle or -1'),
})


class Model(Model):                             # noqa: F811
    def spell_base(self, spell, level, owner, skill, table):
        """The Spell base, inlined in every spell constructor: level byte +0, back list +4
        = 0, skill +8, owner +0xc, own generator +0x10 = ONE SHARED DRAW, table +0x14."""
        self.w8(spell, level)
        self.w32(spell + 4, 0)
        self.w32(spell + 8, skill)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 0x10, self.draw())
        self.w32(spell + 0x14, table)

    def player_object(self, slot):
        return self.u32((G_PLAYERS + s32(slot) * REC_SIZE + RC.REC_OBJ) & M32)

    # =====================================================================================
    # Skills 31 Cleric Root and 32 Ranger Root (and 52, 85): SkillRoot (table 0x519ba0) and
    # SpellRoot (0x34 bytes, table 0x519b70), which sits on the VICTIM.
    #
    #   +0x18 seconds since the cast (float)   +0x1c phase   +0x20 duration in seconds
    #   +0x24 particle group   +0x28 the victim's position at the cast
    # =====================================================================================
    ROOT_DELAY = 0x3F04DCCA                     # 0.518994 s: the roll comes on the 32nd run

    def root_can_use(self, skill, caster):
        """SkillRoot_canUse 0x2e6534 (skill, caster) -> 1, or 0 for a player caster in PvP
        mode A, who is shown a HUD message for 90 frames (also when the caster is the
        prediction copy: can-use runs before the copy test of Player_castSkill)."""
        if self.u32(G_PVP_MODE_A) and self.u32(caster + 0xC) & 0x40:
            self.call('hud_showMessage', self.call('text_lookup', 0x550178), 0x5A, self.u32(caster + 0x3C8), 0)
            return 0
        return 1

    def root_cast(self, skill, level, caster, pos, facing):
        """SkillRoot_cast 0x2e6598 (skill, level, caster, position, facing) -> 0.

        The level goes through slot 14 (level, 20); the cast sound on the caster; n =
        slot 10 (0, level); world_collectObjectsInArc(position, facing, no filter; 248,
        120 degrees, 0).  The list is walked in order until n spells are made: an entry
        gets one when the caster is null or its slot 20 calls it an enemy, it lacks object
        flag 0x1000000, creature_bossRank is 0 and its root timer +0x314 is below 1:
        pool_new(0x34), SpellRoot_ctor (ONE SHARED DRAW), creature_addSpell - which is
        called, and the count raised, even when the pool gave nothing."""
        level = self.skill_call(skill, 14, level, 0x14)
        self.call('sound_playOnObject', self.call('res_find', 0x550188, 0x550190), caster, ONE)
        limit = s32(self.skill_call(skill, 10, 0, level))
        found = self.call('world_collectObjectsInArc', tuple(pos), s16(facing), 'stack', 0, 0x43780000, 0x42F00000, ZERO)
        made = 0
        for other in found or ():
            if not made < limit:
                break
            if caster and not self.vcall(caster, 20, other):
                continue
            if self.u32(other + 0xC) & 0x1000000 or self.call('creature_bossRank', other):
                continue
            if not self.s16(other + 0x314) < 1:
                continue
            spell = self.call('pool_new', 0x34)
            if spell:
                self.root_spell_ctor(spell, level, other, skill)
            self.add_spell(other, spell)
            made += 1
        self.call('handle_clear', 'stack')
        self.call('handle_clear', 'stack')
        return 0

    def root_spell_ctor(self, spell, level, victim, skill):
        """SpellRoot_ctor 0x2e68c8 (spell, level, victim, skill): the Spell base (ONE SHARED
        DRAW) with the victim as owner; time 0, phase 0; a particle group; the victim's
        position; duration +0x20 = slot 10 (1, level)."""
        self.spell_base(spell, level, victim, skill, 0x519B70)
        self.w32(spell + 0x18, 0)
        self.w32(spell + 0x1C, 0)
        self.w32(spell + 0x24, self.call('particleGroup_create'))
        self.wvec(spell + 0x28, self.vec(victim + 0x10))
        self.w32(spell + 0x20, self.skill_call(self.u32(spell + 8), 10, 1, self.s8(spell)))

    def root_spell_run(self, spell, pos=None, facing=0):
        """SpellRoot_run 0x2e699c (spell, position, facing), once per frame of the victim.

        time += 1/60.
        Phase 0: seven particles inside the group (two OWN draws each).  Once time >
        0.518994: ONE SHARED DRAW d; with slot 10 (2, level) <= d % 100 + 1 the root is
        resisted - 100 particles (a ball each) and the spell deletes itself; otherwise
        both flash quads of the victim = (4, 0x5c, 0, 0x51), a victim that is NOT a
        player gets its root timer +0x314 = duration x 60 (low 16 bits), and phase = 1.
        Phase 1: 22 particles on the victim's model (per particle one OWN draw for the
        sample point, taken modulo the point count, and a ball that is not used); a
        PLAYER victim is pushed back toward where it was caught: knock-back speed +0x2e8
        = distance x 4, angle +0x2e0 = -0x4000 - atan2_16(dx, dy).
        In either phase: duration < time - 0.518994 ends the spell."""
        u32, w32 = self.u32, self.w32
        w32(spell + 0x18, C.add(u32(spell + 0x18), DT))
        phase = self.s32(spell + 0x1C)
        owner = u32(spell + 0xC)
        if phase == 0:
            matrix = C.mat34_set_pos_rot_z(self.vec(owner + 0x10), self.s16(owner + 0x38))
            self.call('particleGroup_begin', u32(spell + 0x24))
            self.call('particleGroup_setMatrix', u32(spell + 0x24), tuple(matrix))
            for _ in range(7):
                owner = u32(spell + 0xC)
                k = 0x3F9FDEBD
                x = C.mul(C.mul(C.add(frac(self.spell_rand(spell)), 0xBF000000), u32(owner + 0x1C)), k)
                y = C.mul(C.mul(C.add(frac(self.spell_rand(spell)), 0xBF000000), u32(u32(spell + 0xC) + 0x1C)), k)
                z = C.add(u32(u32(spell + 0xC) + 0x20), F_12)
                self.call('particle_spawn', 0x8E5F00, (x, y, z), (ZERO, ZERO, 0xC2980000), ZERO)
            self.call('particleGroup_end', u32(spell + 0x24))
            if C.lt(self.ROOT_DELAY, u32(spell + 0x18)):
                roll = self.draw() % 100 + 1
                chance = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))
                owner = u32(spell + 0xC)
                if not roll < chance:
                    base = (u32(owner + 0x10), u32(owner + 0x14), C.add(u32(owner + 0x18), u32(owner + 0x20)))
                    for _ in range(100):
                        b = self.spell_ball(spell)
                        self.call('particle_spawn', 0x8E5F50, base, tuple(C.mul(b[i], 0x41A80000) for i in range(3)), ZERO)
                    self.table_call('Spell', spell, 0x14, 1, 3)
                    return
                self.flash_both(owner, 4, 0x5C, 0, 0x51)
                if not u32(owner + 0xC) & 0x40:
                    self.w16(owner + 0x314, u32(spell + 0x20) * 60)
                w32(spell + 0x1C, u32(spell + 0x1C) + 1)
        elif phase == 1:
            count = self.call('model_getSamplePointCount', self.vcall(owner, 16))
            for _ in range(22):
                owner = u32(spell + 0xC)
                model = self.vcall(owner, 16)
                index = rem(self.spell_rand(spell), count)
                owner = u32(spell + 0xC)
                point, _second = self.call('model_getSamplePoint', model, owner + 0x114, self.vec(owner + 0x10),
                                           self.s16(owner + 0x38), index, 1, 0, ONE)
                self.spell_ball(spell)
                self.call('particle_spawn', 0x8E5EB0, tuple(point), (ZERO, ZERO, ZERO), ZERO)
            owner = u32(spell + 0xC)
            if u32(owner + 0xC) & 0x40:
                dx = C.sub(u32(owner + 0x10), u32(spell + 0x28))
                dy = C.sub(u32(owner + 0x14), u32(spell + 0x2C))
                w32(owner + 0x2E8, C.mul(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), 0x40800000))
                angle = C.atan2_16(C.sub(u32(owner + 0x10), u32(spell + 0x28)), C.sub(u32(owner + 0x14), u32(spell + 0x2C)))
                self.w16(u32(spell + 0xC) + 0x2E0, -0x4000 - angle)
        if C.lt(C.from_int(self.s32(spell + 0x20)), C.sub(u32(spell + 0x18), self.ROOT_DELAY)):
            self.spell_delete(spell)

    # =====================================================================================
    # Skill 33 Ranger Critical Hit (and 53, 81): SkillCriticalHit (table 0x519c58) and
    # SpellCriticalHit (0x5c bytes, table 0x519c28).
    #
    #   +0x18 seconds left (float)   +0x1c..+0x54 a light record   +0x58 particle group
    # =====================================================================================
    CRIT_GETTER = 0x3CF000                      # SpellCriticalHit's type-info getter

    def crit_can_use(self, skill, caster):
        """SkillCriticalHit_canUse 0x2e7224 -> 1 unless the caster carries a
        SpellCriticalHit."""
        return 0 if self.carries(caster, self.CRIT_GETTER) else 1

    def crit_cast(self, skill, level, caster, pos=None, facing=0):
        """SkillCriticalHit_cast 0x2e74b0 -> the spell: pool_new(0x5c) and the constructor."""
        spell = self.call('pool_new', 0x5C)
        if spell:
            self.crit_spell_ctor(spell, level, caster, skill)
        return spell

    def crit_spell_ctor(self, spell, level, owner, skill):
        """SpellCriticalHit_ctor 0x2e7988 (spell, level, owner, skill): the Spell base (ONE
        SHARED DRAW), the light record at +0x1c (linked), seconds +0x18 = (float) slot 10
        (2, level), a particle group."""
        w32, w16 = self.w32, self.w16
        self.spell_base(spell, level, owner, skill, 0x519C28)
        self.w8(spell + 0x25, 0)
        self.wvec(spell + 0x4C, self.vec(owner + 0x10))
        for off, value in ((0x40, 0x42F00000), (0x38, 0x42F00000), (0x44, 0x3891A2B3), (0x3C, 0x3891A2B3), (0x48, 0)):
            w32(spell + off, value)
        for off, value in ((0x32, 0x40), (0x28, 0x40), (0x2A, 0x40), (0x30, 0x40), (0x2E, 0xD7), (0x26, 0xD7), (0x2C, 0),
                           (0x34, 0)):
            w16(spell + off, value)
        self.w8(spell + 0x24, 0)
        self.call('light_link', spell + 0x1C)
        w32(spell + 0x18, C.from_int(s32(self.skill_call(self.u32(spell + 8), 10, 2, self.s8(spell)))))
        w32(spell + 0x58, self.call('particleGroup_create'))

    def crit_set_tint(self, spell, creature):
        """SpellCriticalHit_setTint 0x2e7f58: the creature's first flash quad = (0x44, 0xe,
        0x18, 0xf)."""
        for off, value in ((0x90, 0x44), (0x96, 0xF), (0x92, 0xE), (0x94, 0x18)):
            self.w16(creature + off, value)

    def crit_spell_run(self, spell, pos=None, facing=0):
        """SpellCriticalHit_run 0x2e7acc (spell, position, facing): presentation only.

        seconds -= 1/60; below 0 the spell deletes itself.  Otherwise: the owner's tint;
        the light follows the owner during the last two seconds (and fades in over the
        first of them), else it is unlinked; a ring of level - k + 14 particles (k = 1,
        10, 5 for ids 53, 33, 81) of radius slot 10 (1, level) x 12 around
        net_objOrGhost(owner) - a PER-MACHINE object, used for placement only: one OWN
        draw per particle whatever it returns; and the tint on every other player of the
        all-players alive list inside that radius (same team only in PvP mode A)."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        left = C.sub(u32(spell + 0x18), DT)
        w32(spell + 0x18, left)
        if C.lt(left, ZERO):
            self.spell_delete(spell)
            return
        owner = u32(spell + 0xC)
        self.crit_set_tint(spell, owner)
        elapsed = C.sub(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))), u32(spell + 0x18))
        if C.le(elapsed, TWO):
            owner = u32(spell + 0xC)
            self.wvec(spell + 0x4C, (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42700000)))
            self.call('light_relink', spell + 0x1C)
            if C.lt(ONE, elapsed):
                fade = C.sub(TWO, elapsed)
                a, b = C.to_int(C.mul(fade, 0x42800000)), C.to_int(C.mul(fade, 0x43570000))
                for off, value in ((0x2A, a), (0x26, b), (0x2E, b), (0x30, a), (0x28, a), (0x32, a)):
                    w16(spell + off, value)
        else:
            self.call('light_unlink', spell + 0x1C)
        skill = u32(spell + 8)
        k = {0x35: 1, 0x21: 10, 0x51: 5}.get(u32(skill + 0x64), 1)
        level = self.s8(spell)
        radius = s32(s32(self.skill_call(skill, 10, 1, level)) * 12)
        ghost = self.call('net_objOrGhost', u32(spell + 0xC))
        if radius > 0:
            self.call('particleGroup_begin', u32(spell + 0x58))
            matrix = C.mat34_set_pos_rot_z(self.vec(ghost + 0x10), s16(self.frame() * 118))
            self.call('particleGroup_setMatrix', u32(spell + 0x58), tuple(matrix))
            for _ in range(max(level - k + 0xE, 0)):
                angle = s16(self.spell_rand(spell))
                local = (C.mul(C.cos16(angle), C.from_int(radius)), C.mul(C.sin16(angle), C.from_int(radius)), ZERO)
                world = C.mat34_transform_point(matrix, local)
                height = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(ghost + 0x18))
                if not C.lt(0x42900000, height) and not C.lt(height, 0xC2900000):
                    self.call('particle_spawn', 0x8E5FA0, (local[0], local[1], height), (ZERO, ZERO, ONE), ZERO)
            self.call('particleGroup_end', u32(spell + 0x58))
        reach = C.from_int(s32(radius * radius))
        for i in range(max(self.s32(G_ALIVE_COUNT), 0)):
            other = self.player_object(u32(G_ALIVE_LIST + 4 * i))
            owner = u32(spell + 0xC)
            if other == owner:
                continue
            if u32(G_PVP_MODE_A) and not self.vcall(owner, 22, other):
                continue
            owner = u32(spell + 0xC)
            dy = C.sub(u32(owner + 0x14), u32(other + 0x14))
            dx = C.sub(u32(owner + 0x10), u32(other + 0x10))
            if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), reach):
                self.crit_set_tint(spell, other)

    def crit_bonus_for(self, skill, attacker, rank):
        """SkillCriticalHit_critBonusFor 0x2e76c4 (skill, attacker, rank) -> float: the
        critical-hit chance this table adds (damage_apply takes the largest of ids 33, 53
        and 81; calls at 0x1e8d5c, 0x1e8d7c, 0x1e8da4).

        level = rank when rank != 0 and the attacker carries a SpellCriticalHit.
        Otherwise the all-players alive list (count 0x4f8420, slots 0x4f8440) is walked in
        order, skipping the attacker's own slot: a player within 1000 units (3-D,
        strict), on the same team when PvP mode A is on (ITS slot 22 with the attacker),
        carrying the spell, whose best rank r of ids 53, 81, 33 (asked in that order) is
        not 0 and who is nearer in the plane than THIS table's slot 10 (1, r) x 12, ends
        the walk with level = r.  Then slot 14 (level, 20), and for a level that is not 0
        the result is (float) slot 10 (0, level) x 0.01."""
        u32 = self.u32
        level = 0
        if rank and self.carries(attacker, self.CRIT_GETTER):
            level = rank
        else:
            for i in range(max(self.s32(G_ALIVE_COUNT), 0)):
                slot = u32(G_ALIVE_LIST + 4 * i)
                if slot == u32(attacker + 0x3C8):
                    continue
                other = self.player_object(slot)
                d = [C.sub(u32(other + 0x10 + 4 * k), u32(attacker + 0x10 + 4 * k)) for k in range(3)]
                if not C.lt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])), 0x49742400):
                    continue
                if u32(G_PVP_MODE_A) and not self.vcall(other, 22, attacker):
                    continue
                if not self.carries(self.player_object(slot), self.CRIT_GETTER):
                    continue
                best = s32(self.call('player_getSkillRank', slot, 0x35))
                best = max(best, s32(self.call('player_getSkillRank', slot, 0x51)))
                best = max(best, s32(self.call('player_getSkillRank', slot, 0x21)))
                if not best:
                    continue
                reach = C.from_int(s32(s32(self.skill_call(skill, 10, 1, best)) * 12))
                other = self.player_object(slot)
                dy = C.sub(u32(other + 0x14), u32(attacker + 0x14))
                dx = C.sub(u32(other + 0x10), u32(attacker + 0x10))
                if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(reach, reach)):
                    if best >= 1:
                        level = best
                    break
        level = self.skill_call(skill, 14, level, 0x14)
        if not level:
            return ZERO
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), 0x3C23D70A)


SKILL_BODIES.update({0x2E6534: 'root_can_use', 0x2E6598: 'root_cast', 0x2E7224: 'crit_can_use', 0x2E74B0: 'crit_cast'})
SPELL_BODIES.update({0x2E699C: 'root_spell_run', 0x2E7ACC: 'crit_spell_run'})
MODELLED.update({'SkillRoot_canUse': 0x2E6534, 'SkillRoot_cast': 0x2E6598, 'SpellRoot_ctor': 0x2E68C8,
                 'SpellRoot_run': 0x2E699C, 'SkillCriticalHit_canUse': 0x2E7224, 'SkillCriticalHit_cast': 0x2E74B0,
                 'SpellCriticalHit_ctor': 0x2E7988, 'SpellCriticalHit_run': 0x2E7ACC, 'SpellCriticalHit_setTint': 0x2E7F58,
                 'SkillCriticalHit_critBonusFor': 0x2E76C4})


EXTERNALS.update({
    'Holder.v5': Ext(0, 'pi', 0, 'n', 'poison weapon (on)'),
    'Holder.v8': Ext(0, 'pii', 0, 'n', 'no magic weapon (which, 0)'),
})
REC_WEAPON_SETS, REC_ACTIVE_SET, REC_OFF_HAND = 0x4434, 0x4A7C, 0x443C


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skills 12 Lightning Weapons, 14 Cold Weapons, 26 Poison Weapons (13 Fire Weapons is the
    # same template with its own light and opening effect; it is not modelled here):
    # one Skill class and one Spell class (0x24 bytes) each.
    #
    #   +0x18 end frame   +0x1c aura radius (int; id 26: a frame number that is not read)
    #   +0x20 end of the opening effect (frame; id 26: the aura radius as a float)
    # =====================================================================================
    WEAPON_BUFFS = {
        # id: table, type-info getter, entry type, level cap of the duration, weapon-holder slot (on),
        #     argument of holder slot 8 at the end, eight light numbers, four more, flash quad, lump, sound
        12: dict(table=0x5199D0, getter=0x3CEBA4, kind=0x18, cap=0x14, holder=6, off=0,
                 light=(0x42DE0000, 0x42E00000, 0x431A0000, 0x437F0000, 0x42040000, 0x41F00000, 0x42580000, 0x434D0000),
                 more=(0x42DC0000, 0, 0x3F1999AA, 0x3EFFFFBC), flash=(0x6F, 0x70, 0x9A, 0x1E), sound=(0x54FE88, 0x54FE90)),
        14: dict(table=0x519B40, getter=0x3CED8C, kind=0x16, cap=0, holder=4, off=1,
                 light=(0x42340000, 0x42480000, 0x437F0000, 0x43480000, 0x42D80000, 0x42FA0000, 0x43740000, 0x43480000),
                 more=(0x42C80000, 0, 0x3F1EF9DB, 0x3EFFFF15), flash=(0x2D, 0x32, 0xFF, 0), sound=(0x550060, 0x550068)),
        26: dict(table=0x51C278, getter=0x3D1B14, kind=0x17, cap=10, holder=5, off=0,
                 light=(0x420C0000, 0x43000000, 0x42820000, 0x43000000, 0x420C0000, 0x43000000, 0x42820000, 0x43000000),
                 more=(0x42DC0000, 0, 0x3F199999, HALF), flash=(0x23, 0x80, 0x41, 0x1E), sound=(0x552E78, 0x552E80)),
    }

    def weapons_of(self, player):
        """A player's two weapon items: the active set's (record +0x4434 + 4 x the signed
        byte +0x4a7c) and the off-hand one (+0x443c)."""
        rec = (G_PLAYERS + self.u32(player + 0x3C8) * REC_SIZE) & M32
        return self.u32(rec + REC_WEAPON_SETS + 4 * self.s8(rec + REC_ACTIVE_SET)), self.u32(rec + REC_OFF_HAND)

    def enchant(self, item, kind, value, frames, limit):
        """The inlined "put a timed entry on a weapon" (e.g. 0x2e26b0-0x2e2828): nothing for
        no item or a thrown one (64-bit item flags +8, bit 24).  cur = v1 (the MINIMUM
        DAMAGE, +0x26 of the slot) of the first entry of that type, or 0; only when
        0 <= cur < limit and cur <= value: the first slot that is empty (-1) or already of
        that type becomes (type, value, round(value + value x 0.2), frames).  `limit` is a
        frame count compared with a damage value."""
        if not item or self.u64(item + 8) & 0x1000000:
            return
        cur = 0
        for k in range(4):
            if self.s16(item + 0x24 + 8 * k) == kind:
                cur = self.s16(item + 0x26 + 8 * k)
                break
        if not 0 <= cur < s32(limit) or not cur <= s32(value):
            return
        amount = C.from_int(s32(value))
        high = round_half(C.add(amount, C.mul(amount, F_0_2)))
        for k in range(4):
            if self.s16(item + 0x24 + 8 * k) in (-1, kind):
                self.w16(item + 0x24 + 8 * k, kind)
                self.w16(item + 0x26 + 8 * k, value)
                self.w16(item + 0x28 + 8 * k, high)
                self.w16(item + 0x2A + 8 * k, frames)
                break

    def weaponbuff_can_use(self, sid, caster):
        """SkillLightningWeapons_canUse 0x2e34ac / Cold 0x2e616c / Poison 0x315bb0 -> 1
        unless the caster carries a spell of that class."""
        return 0 if self.carries(caster, self.WEAPON_BUFFS[sid]['getter']) else 1

    def weaponbuff_cast(self, sid, skill, level, caster):
        """The cast (0x2e3184, 0x2e5e44, 0x315be4) -> the spell: pool_new(0x24) and the
        constructor.  Poison Weapons first passes the level through slot 14 (level, 1)."""
        if sid == 26:
            level = self.skill_call(skill, 14, level, 1)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.weaponbuff_ctor(sid, spell, level, caster, skill)
        return spell

    def weaponbuff_ctor(self, sid, spell, level, owner, skill):
        """SpellLightningWeapons_ctor 0x2e24d8 / Cold 0x2e4f94 / Poison 0x315f54 (spell,
        level, owner, skill).

        The Spell base (ONE SHARED DRAW).  end +0x18 = frame + slot 12 (1, level, owner,
        cap) x 60; ids 12, 14: radius +0x1c = slot 12 (2, ..., cap 10) x 12 and +0x20 =
        int(frame + 29.999878 / 22.499683); id 26: +0x1c = frame + 30 and +0x20 = (float)
        slot 10 (2, level) x 12.0.  dmg = slot 12 (0, ..., cap 0), frames = slot 12 (1,
        ..., cap) x 60.  An owner that is not a player: its weapon holder's slot 6 / 4 /
        5 with 1.  A player: both weapons get the entry (type, dmg, round(1.2 dmg),
        frames) by the rule of enchant(), the limit being `frames`.  Then a LightEffect
        at the owner (pool_new 0xbc; ONE SHARED DRAW inside), the owner's second flash
        quad and the sound."""
        p = self.WEAPON_BUFFS[sid]
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, owner, skill, p['table'])
        seconds = self.skill_call(skill, 12, 1, level, owner, p['cap'])
        w32(spell + 0x18, u32(G_SIM_FRAME) + s32(seconds) * 60)
        if sid == 26:
            w32(spell + 0x1C, u32(G_SIM_FRAME) + 0x1E)
            w32(spell + 0x20, C.mul(C.from_int(s32(self.skill_call(skill, 10, 2, self.s8(spell)))), F_12))
        else:
            w32(spell + 0x1C, s32(self.skill_call(skill, 12, 2, self.s8(spell), owner, 10)) * 12)
            w32(spell + 0x20, C.to_int(C.add(C.from_int(self.frame()), 0x41EFFFC0 if sid == 12 else 0x41B3FF5A)))
        dmg = self.skill_call(skill, 12, 0, self.s8(spell), owner, 0)
        frames = s32(self.skill_call(skill, 12, 1, self.s8(spell), owner, p['cap'])) * 60
        owner = u32(spell + 0xC)
        if not u32(owner + 0xC) & 0x40:
            holder = u32(owner + 0x50)
            if holder:
                self.holder_call(holder, p['holder'], 1)
        else:
            for item in self.weapons_of(owner):
                self.enchant(item, p['kind'], dmg, frames, frames)
        self.light_effect(0xBC, self.vec(u32(spell + 0xC) + 0x10), 0, 0, *(p['light'] + p['more']))
        self.flash2(u32(spell + 0xC), *p['flash'])
        self.call('sound_playAtPos', self.call('res_find', *p['sound']), self.vec(u32(spell + 0xC) + 0x10), ONE)

    def weaponbuff_run(self, sid, spell, pos, facing=0):
        """SpellLightningWeapons_run 0x2e2ac4 / Cold 0x2e5578 / Poison 0x3164fc (spell,
        position, facing).

        frame >= end: an owner that is a creature but not a player and has a weapon
        holder gets holder slot 8 (0 / 1 / 0, 0); the spell deletes itself.
        Otherwise the opening effect while frame < +0x20 (id 12: the model shock effect;
        id 14: 6 + 2 particles, five OWN draws each; id 26: none), and - with a radius,
        a PLAYER owner and frame % 30 == 0 - the aura: every other player of the box
        position -/+ radius (capacity 64; same team only in PvP mode A, the owner's slot
        22) gets, on both weapons, the entry (type, a, round(1.2 a), 31) by the rule of
        enchant() with limit 31; a = slot 10 (3, level) for ids 12 and 26, slot 12 (3,
        level, owner, cap 0) for id 14."""
        p = self.WEAPON_BUFFS[sid]
        u32 = self.u32
        frame = self.frame()
        owner = u32(spell + 0xC)
        if not frame < self.s32(spell + 0x18):
            if u32(owner + 0xC) & 0x60 == 0x20 and u32(owner + 0x50):
                self.holder_call(u32(owner + 0x50), 8, p['off'], 0)
            self.spell_delete(spell)
            return
        if sid == 26:
            radius = u32(spell + 0x20)
            if C.eq(radius, ZERO):
                return
        else:
            if frame < self.s32(spell + 0x20):
                if sid == 12:
                    model = self.vcall(owner, 16)
                    owner = u32(spell + 0xC)
                    self.call('fx_shockModel', model, owner + 0x114, self.vec(owner + 0x10), self.s16(owner + 0x38),
                              owner + 0x320, 0x5E808080, 0x409FFF79, u32(owner + 0xDC), u32(owner + 0xE0))
                else:
                    for definition, count in ((0x8E5E10, 6), (0x8E5E60, 2)):
                        for _ in range(count):
                            k = 0x421FFF8B
                            c = C.mul(C.cos16(s16(self.spell_rand(spell))), k)
                            x = C.mul(c, C.sin16(s16((self.spell_rand(spell) >> 1) & 0xFFFF)))
                            s = C.mul(C.sin16(s16(self.spell_rand(spell))), k)
                            y = C.mul(s, C.sin16(s16((self.spell_rand(spell) >> 1) & 0xFFFF)))
                            z = C.mul(C.cos16(s16((self.spell_rand(spell) >> 1) & 0xFFFF)), k)
                            point = (C.add(x, pos[0]), C.add(y, pos[1]), C.add(z, pos[2]))
                            self.call('particle_spawn', definition, point, tuple(C.sub(pos[i], point[i]) for i in range(3)), ZERO)
            if not self.s32(spell + 0x1C):
                return
            radius = C.from_int(self.s32(spell + 0x1C))
        owner = u32(spell + 0xC)
        if not u32(owner + 0xC) & 0x40 or rem(self.frame(), 30) != 0:
            return
        found = self.box_around(pos, radius, 0x40)
        owner = u32(spell + 0xC)
        for other in found:
            if other == owner or not u32(other + 0xC) & 0x40:
                continue
            if u32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, other):
                continue
            first, second = self.weapons_of(other)
            if sid == 14:
                aura = self.skill_call(u32(spell + 8), 12, 3, self.s8(spell), u32(spell + 0xC), 0)
            else:
                aura = self.skill_call(u32(spell + 8), 10, 3, self.s8(spell))
            self.enchant(first, p['kind'], aura, 0x1F, 0x1F)
            self.enchant(second, p['kind'], aura, 0x1F, 0x1F)

    # the per-id entry points
    def lightningweapons_can_use(self, skill, caster):
        return self.weaponbuff_can_use(12, caster)

    def lightningweapons_cast(self, skill, level, caster, pos=None, facing=0):
        return self.weaponbuff_cast(12, skill, level, caster)

    def lightningweapons_run(self, spell, pos, facing=0):
        return self.weaponbuff_run(12, spell, pos, facing)

    def coldweapons_can_use(self, skill, caster):
        return self.weaponbuff_can_use(14, caster)

    def coldweapons_cast(self, skill, level, caster, pos=None, facing=0):
        return self.weaponbuff_cast(14, skill, level, caster)

    def coldweapons_run(self, spell, pos, facing=0):
        return self.weaponbuff_run(14, spell, pos, facing)

    def poisonweapons_can_use(self, skill, caster):
        return self.weaponbuff_can_use(26, caster)

    def poisonweapons_cast(self, skill, level, caster, pos=None, facing=0):
        return self.weaponbuff_cast(26, skill, level, caster)

    def poisonweapons_run(self, spell, pos, facing=0):
        return self.weaponbuff_run(26, spell, pos, facing)


SKILL_BODIES.update({0x2E34AC: 'lightningweapons_can_use', 0x2E3184: 'lightningweapons_cast',
                     0x2E616C: 'coldweapons_can_use', 0x2E5E44: 'coldweapons_cast',
                     0x315BB0: 'poisonweapons_can_use', 0x315BE4: 'poisonweapons_cast'})
SPELL_BODIES.update({0x2E2AC4: 'lightningweapons_run', 0x2E5578: 'coldweapons_run', 0x3164FC: 'poisonweapons_run'})
MODELLED.update({'SkillLightningWeapons_canUse': 0x2E34AC, 'SkillLightningWeapons_cast': 0x2E3184,
                 'SpellLightningWeapons_ctor': 0x2E24D8, 'SpellLightningWeapons_run': 0x2E2AC4,
                 'SkillColdWeapons_canUse': 0x2E616C, 'SkillColdWeapons_cast': 0x2E5E44,
                 'SpellColdWeapons_ctor': 0x2E4F94, 'SpellColdWeapons_run': 0x2E5578,
                 'SkillPoisonWeapons_canUse': 0x315BB0, 'SkillPoisonWeapons_cast': 0x315BE4,
                 'SpellPoisonWeapons_ctor': 0x315F54, 'SpellPoisonWeapons_run': 0x3164FC})


G_GLOW_TEXTURE = 0x4F8498                       # the sprite the swarm glows use (a pointer; presentation)
EXTERNALS.update({
    'glow_add': Ext(0x18FC78, 'viiiiiii', 2, 'n', '(position, 0, 0, 0, alpha, texture, 0, 0; size, range): one glow sprite '
                    'for this frame'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 29, Disease Effect: the Skill object is a statistic table (base cast, can-use
    # and mana cost); the status itself is SpellDiseaseEffect (0x1b0 bytes, table 0x518db0),
    # which sits on the victim.  Created by damage_apply for an entry of type 0x26 (level
    # 0), by its own contagion (level 0) and by Bubo on itself.
    #
    #   +0x08 Skill = 0 (!)   +0x0c, +0x19c victim   +0x18 handle of the source (attacker)
    #   +0x1c, +0xdc 16 swarm points and their velocities   +0x1a0 end frame
    #   +0x1a4 seconds   +0x1a8 level   +0x1ac the Skill
    # =====================================================================================
    DISEASE_GETTER = 0x3CDD40

    def disease_spell_ctor(self, spell, seconds, level, victim, attacker, skill):
        """SpellDiseaseEffect_ctor 0x2d5594 (spell, seconds, level, victim, attacker, skill).

        The Spell base with a NULL skill word (ONE SHARED DRAW); the attacker handle
        +0x18 (empty for no attacker); end = frame + seconds x 60; 16 swarm points from
        the OWN generator - a ball x the victim's radius, and a ball for the velocity."""
        w32, u32 = self.w32, self.u32
        self.spell_base(spell, level, victim, 0, 0x518DB0)
        w32(spell + 0x18, 0)
        if attacker:
            self.call('handle_link', spell + 0x18, attacker, attacker)
        w32(spell + 0x1A4, seconds)
        w32(spell + 0x19C, victim)
        w32(spell + 0x1A0, u32(G_SIM_FRAME) + s32(seconds) * 60)
        for i in range(16):
            b = self.spell_ball(spell)
            radius = u32(u32(spell + 0xC) + 0x1C)
            for k in range(3):
                w32(spell + 0x1C + 12 * i + 4 * k, C.mul(b[k], radius))
            b = self.spell_ball(spell)
            for k in range(3):
                w32(spell + 0xDC + 12 * i + 4 * k, b[k])
        w32(spell + 0x1AC, skill)
        w32(spell + 0x1A8, level)

    def disease_spell_run(self, spell, pos, facing=0):
        """SpellDiseaseEffect_run 0x2d5854 (spell, position, facing), once per frame of the
        victim.

          1. frame >= end: the spell deletes itself.
          2. the swarm: per point one ball from the OWN generator (x 1.5), a pull back
             (-0.02 x the point) once it is outside (2 x radius)^2 x 0.83333, velocity =
             (velocity + that) x 0.8, point += velocity, and a glow at position + point.
          3. the victim's second flash quad = (255, 255, 0, 0).
          4. contagion, when seconds > 1 and frame % 30 == 0: every creature (flag 0x20)
             of the box position -/+ (float) int(2 x the victim's radius) (capacity 64),
             while the source handle holds something, that the source's slot 20 calls an
             enemy (any creature when the source itself is not one) and that carries no
             SpellDiseaseEffect: pool_new(0x1b0), the constructor with seconds =
             int(seconds x 0.5 - its disease resistance (+0x68) x 5), level 0, the same
             source and skill (ONE SHARED DRAW and its swarm), creature_addSpell.
          5. damage, when frame % 30 == 0 and the source handle holds something: d =
             int(skill slot 12 (0, level, source, cap 0) x 0.5), at least 1; ONE OWN DRAW
             r; damage_apply(victim, source, 100000, flags 0xc040, an empty descriptor;
             d, d + (d x r/65536) x 0.2).  With level 0 the statistic is 0 and d is 1."""
        u32, w32 = self.u32, self.w32
        if not self.frame() < self.s32(spell + 0x1A0):
            self.spell_delete(spell)
            return
        for i in range(16):
            point, speed = spell + 0x1C + 12 * i, spell + 0xDC + 12 * i
            push = [C.mul(v, 0x3FC00000) for v in self.spell_ball(spell)]
            p = self.vec(point)
            radius = u32(u32(spell + 0x19C) + 0x1C)
            limit = C.mul(C.mul(C.add(radius, radius), C.add(radius, radius)), 0x3F55551D)
            if C.lt(limit, C.add(C.add(C.mul(p[0], p[0]), C.mul(p[1], p[1])), C.mul(p[2], p[2]))):
                push = [C.add(push[k], C.mul(p[k], 0xBCA3D70A)) for k in range(3)]
            v = [C.mul(C.add(u32(speed + 4 * k), push[k]), 0x3F4CCCCC) for k in range(3)]
            for k in range(3):
                w32(speed + 4 * k, v[k])
            p = [C.add(u32(point + 4 * k), v[k]) for k in range(3)]
            for k in range(3):
                w32(point + 4 * k, p[k])
            self.call('glow_add', tuple(C.add(p[k], pos[k]) for k in range(3)), 0, 0, 0, 200, u32(G_GLOW_TEXTURE), 0, 0,
                      0x41F00000, 0x43C80000)
        victim = u32(spell + 0x19C)
        self.flash2(victim, 0xFF, 0xFF, 0, 0)
        if self.s32(spell + 0x1A4) > 1 and rem(self.frame(), 30) == 0:
            radius = u32(victim + 0x1C)
            for other in self.box_around(pos, C.from_int(s32(C.to_int(C.add(radius, radius)))), 0x40):
                node = u32(spell + 0x18)
                if not node or not u32(other + 0xC) & 0x20:
                    continue
                source = u32(node + 0xC)
                if u32(source + 0xC) & 0x20 and not self.vcall(source, 20, other):
                    continue
                if self.carries(other, self.DISEASE_GETTER):
                    continue
                fresh = self.call('pool_new', 0x1B0)
                if fresh:
                    seconds = C.to_int(C.sub(C.mul(C.from_int(self.s32(spell + 0x1A4)), HALF), C.mul(u32(other + 0x68), 0x40A00000)))
                    self.disease_spell_ctor(fresh, seconds, 0, other, u32(u32(spell + 0x18) + 0xC), u32(spell + 0x1AC))
                self.add_spell(other, fresh)
        if rem(self.frame(), 30) == 0 and u32(spell + 0x18):
            source = u32(u32(spell + 0x18) + 0xC)
            value = self.skill_call(u32(spell + 0x1AC), 12, 0, u32(spell + 0x1A8), source, 0)
            d = s32(C.to_int(C.mul(C.from_int(s32(value)), HALF)))
            amount = C.from_int(d if d >= 1 else 1)
            high = spread_max(amount, self.spell_rand(spell))
            self.call('damage_apply', u32(spell + 0x19C), self.handle_obj(spell + 0x18), 100000, 0, 0, 0xC040, descriptor(), 0,
                      amount, high)


SPELL_BODIES.update({0x2D5854: 'disease_spell_run'})
MODELLED.update({'SpellDiseaseEffect_ctor': 0x2D5594, 'SpellDiseaseEffect_run': 0x2D5854})


EXTERNALS.update({
    'Skelight_ctor': Ext(0x2A8770, 'pvipi', 0, 'n', '(block, position, facing, property list, level): the skeleton, '
                         'modelled by tools/ref_arena_monsters.py (skelight_ctor); a callback here'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 11, Summon Skeleton: imported.  summon_can_use 0x2e2368, summon_cast 0x2e18a4,
    # summon_spell_ctor 0x2e16ec and summon_spell_run 0x2e177c are the methods of
    # tools/ref_arena_monsters.py; the skeleton's own constructor stays a callback here
    # (that module models it, on top of its Creature_ctor).
    # =====================================================================================
    def skelight_ctor(self, c, pos, facing, props, level):
        self.call('Skelight_ctor', c, tuple(pos), facing, props, level)
        self.hidden_draws += 1


MODELLED.update({'SkillSummonSkeleton_canUse': 0x2E2368, 'SkillSummonSkeleton_cast': 0x2E18A4,
                 'SpellSummonSkeleton_ctor': 0x2E16EC, 'SpellSummonSkeleton_run': 0x2E177C})


EXTERNALS.update({
    'gfx_setColorOffset': Ext(0x19B6BC, 'iiii', 0, 'n', '(r, g, b, 0): a whole-screen flash; renderer state, written on '
                              'every machine'),
    'GlowingShaft_ctor': Ext(0x202FF0, 'pviiii', 0, 'n', '(block, position, frames, r, g, b): visual; ONE SHARED DRAW '
                             'inside (GameObject_ctor)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 20, Blinding Light: SkillBlindingLight (table 0x51a670), the one-second effect
    # object BlindingLightEffect (0x54 bytes, table 0x51a5e0) and the status
    # SpellBlindingLight (0x20 bytes, table 0x51a6f8), which sits on each victim.
    #
    #   effect: +0x4c end frame   +0x50 radius (int)
    #   spell:  +0x18 end frame   +0x1c the caster, a RAW POINTER (FINDINGS SA1)
    # =====================================================================================
    def blindinglight_can_use(self, skill, caster=0):
        """SkillBlindingLight_canUse 0x2f4b10 -> 1."""
        return 1

    def blindinglight_cast(self, skill, level, caster, pos, facing):
        """SkillBlindingLight_cast 0x2f47dc (skill, level, caster, position, facing) -> 0.

        Both flash quads of the caster = (0x56, 0x80, 0xfa, 0x6e) (no null test); the
        screen flash gfx_setColorOffset(0x80, 0x80, 0x80, 0);
        world_collectObjectsInArc(position, facing, no filter; 360, 90 degrees, 0); the
        sound.  Only the FIRST entry of the list (the nearest creature in the arc, friend
        or foe) is looked at: when the caster's slot 20 calls it an enemy, pool_new(0x54)
        and BlindingLightEffect_ctor at ITS position."""
        self.flash_both(caster, 0x56, 0x80, 0xFA, 0x6E)
        self.call('gfx_setColorOffset', 0x80, 0x80, 0x80, 0)
        found = self.call('world_collectObjectsInArc', tuple(pos), s16(facing), 'stack', 0, 0x43B40000, 0x42B40000, ZERO)
        self.call('sound_playOnObject', self.call('res_find', 0x550D70, 0x550D78), caster, ONE)
        if found and caster:
            first = found[0]
            if self.vcall(caster, 20, first):
                where = self.vec(first + 0x10)
                obj = self.call('pool_new', 0x54)
                if obj:
                    self.blindinglight_effect_ctor(obj, where, level, caster, skill)
        self.call('handle_clear', 'stack')
        return 0

    def blindinglight_effect_ctor(self, obj, pos, level, caster, skill):
        """BlindingLightEffect_ctor 0x2f3f38 (object, position, level, caster, skill).

        GameObject_ctor (ONE SHARED DRAW); flags |= 0x421b; end = frame + 60; radius =
        slot 10 (3, level) x 12.  Every object of the box position -/+ radius (capacity
        64) the caster's slot 20 calls an enemy: chance = slot 10 (0, level), halved
        (toward zero) plus 1 for anything creature_bossRank does not call 0; ONE OWN DRAW
        r; when (r/65536) x 100 < chance: pool_new(0x20), SpellBlindingLight_ctor (ONE
        SHARED DRAW), creature_addSpell, and the victim's slot 31 (no-target timer) with
        slot 10 (2, level) x 60.  Then a LightEffect (pool_new 0xbc) and a GlowingShaft
        (pool_new 0x5c) - ONE SHARED DRAW inside each - and the every-frame run list."""
        u32, w32 = self.u32, self.w32
        self.gameobject_ctor(obj, pos, 0, 0)
        w32(obj + 0x48, 0x51A5E0)
        w32(obj + 0xC, u32(obj + 0xC) | 0x421B)
        w32(obj + 0x4C, u32(G_SIM_FRAME) + 0x3C)
        radius = s32(s32(self.skill_call(skill, 10, 3, level)) * 12)
        w32(obj + 0x50, radius)
        for other in self.box_around(self.vec(obj + 0x10), C.from_int(radius), 0x40):
            if not self.vcall(caster, 20, other):
                continue
            chance = s32(self.skill_call(skill, 10, 0, level))
            if self.call('creature_bossRank', other):
                chance = half_toward_zero(chance) + 1
            if C.lt(C.mul(frac(self.obj_rand(obj)), 0x42C80000), C.from_int(chance)):
                spell = self.call('pool_new', 0x20)
                if spell:
                    self.blindinglight_spell_ctor(spell, level, caster, other, skill)
                self.add_spell(other, spell)
                self.vcall(other, 31, s32(self.skill_call(skill, 10, 2, level)) * 60)
        radius = self.s32(obj + 0x50)
        self.light_effect(0xBC, self.vec(obj + 0x10), 0, 0, 0x42AC0000, 0x43000000, 0x437A0000, 0xC2000000, ZERO, ZERO, ZERO,
                          ZERO, C.from_int(radius + 0x18), C.from_int(half_toward_zero(radius) + 0x18), 0x3F199999, ONE)
        shaft = self.call('pool_new', 0x5C)
        if shaft:
            self.call('GlowingShaft_ctor', shaft, self.vec(obj + 0x10), 0x3C, 0x56, 0x80, 0xFA)
            self.hidden_draws += 1
        self.call('obj_runEveryFrame', obj)

    def blindinglight_effect_run(self, obj):
        """BlindingLightEffect_run 0x2f42e4 (object), slot 4: while frame < end, twelve
        particles a frame, four OWN draws each (direction, two distances, height);
        afterwards the object deletes itself."""
        u32 = self.u32
        if not self.frame() < self.s32(obj + 0x4C):
            self.delete_self(obj)
            return
        for _ in range(12):
            angle = s16(self.obj_rand(obj))
            x = C.mul(C.cos16(angle), C.mul(frac(self.obj_rand(obj)), C.from_int(self.s32(obj + 0x50))))
            y = C.mul(C.sin16(angle), C.mul(frac(self.obj_rand(obj)), C.from_int(self.s32(obj + 0x50))))
            z = C.mul(frac(self.obj_rand(obj)), 0x413FFF59)
            point = (C.add(x, u32(obj + 0x10)), C.add(y, u32(obj + 0x14)), C.add(z, u32(obj + 0x18)))
            self.call('particle_spawn', 0x8E6590, point, (ZERO, ZERO, 0x42D9BDC5), ZERO)

    def blindinglight_spell_ctor(self, spell, level, caster, victim, skill):
        """SpellBlindingLight_ctor 0x2f4474 (spell, level, caster, victim, skill): the Spell
        base on the victim (ONE SHARED DRAW); end +0x18 = frame + slot 10 (2, level) x 60;
        the caster at +0x1c as a plain pointer."""
        self.spell_base(spell, level, victim, skill, 0x51A6F8)
        seconds = self.skill_call(skill, 10, 2, level)
        self.w32(spell + 0x1C, caster)
        self.w32(spell + 0x18, self.u32(G_SIM_FRAME) + s32(seconds) * 60)

    def blindinglight_spell_run(self, spell, pos=None, facing=0):
        """SpellBlindingLight_run 0x2f4538 (spell, position, facing): at frame >= end the
        spell deletes itself.  While the victim's hit points (+0x228) are above 0, on
        frames divisible by 30: s = slot 10 (1, level); ONE OWN DRAW r; damage_apply(victim,
        the caster POINTER, 100000, flags 0x40, an empty descriptor; (float)(s / 2), (s +
        (s x r/65536) x 0.2) x 0.5)."""
        u32 = self.u32
        if not self.frame() < self.s32(spell + 0x18):
            self.spell_delete(spell)
            return
        if not C.lt(ZERO, u32(u32(spell + 0xC) + 0x228)) or rem(self.frame(), 30) != 0:
            return
        s = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
        full = C.from_int(s)
        high = C.mul(spread_max(full, self.spell_rand(spell)), HALF)
        self.call('damage_apply', u32(spell + 0xC), u32(spell + 0x1C), 100000, 0, 0, 0x40, descriptor(), 0,
                  C.from_int(half_toward_zero(s)), high)


SKILL_BODIES.update({0x2F4B10: 'blindinglight_can_use', 0x2F47DC: 'blindinglight_cast'})
OBJECT_BODIES.update({0x2F42E4: 'blindinglight_effect_run'})
SPELL_BODIES.update({0x2F4538: 'blindinglight_spell_run'})
MODELLED.update({'SkillBlindingLight_canUse': 0x2F4B10, 'SkillBlindingLight_cast': 0x2F47DC,
                 'BlindingLightEffect_ctor': 0x2F3F38, 'BlindingLightEffect_run': 0x2F42E4,
                 'SpellBlindingLight_ctor': 0x2F4474, 'SpellBlindingLight_run': 0x2F4538})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 15, Undead Shield: SkillUndeadShield (table 0x519f90), SpellUndeadShield (0x64
    # bytes, table 0x51a048) on the caster and SpellSecondaryUndeadShield (0x24 bytes,
    # table 0x51a018) on the players it covers.  damage_apply asks the reflection helpers
    # (0x1ea644, 0x1ea668).
    #
    #   shield:    +0x18 end frame   +0x1c aura half-width (85)   +0x20..+0x58 light record
    #              +0x5c particle group   +0x60 sound handle
    #   secondary: +0x00 level 0, +0x08 Skill 0   +0x18 end frame   +0x1c percent
    #              +0x20 particle group
    # =====================================================================================
    SHIELD_GETTER, SECONDARY_GETTER = 0x3CF3AC, 0x3CF3FC

    def undeadshield_can_use(self, skill, caster):
        """SkillUndeadShield_canUse 0x2eb970 -> 1 unless the caster carries a
        SpellUndeadShield."""
        return 0 if self.carries(caster, self.SHIELD_GETTER) else 1

    def undeadshield_cast(self, skill, level, caster, pos=None, facing=0):
        """SkillUndeadShield_cast 0x2eb7cc -> the spell: pool_new(0x64) and the constructor."""
        spell = self.call('pool_new', 0x64)
        if spell:
            self.undeadshield_ctor(spell, level, caster, skill)
        return spell

    def undeadshield_ctor(self, spell, level, owner, skill):
        """SpellUndeadShield_ctor 0x2ea4d8 (spell, level, owner, skill): the Spell base (ONE
        SHARED DRAW), the light record +0x20 (linked), end = frame + slot 10 (1, level) x
        60, aura half-width 85, a particle group and the looping sound."""
        w32, w16 = self.w32, self.w16
        self.spell_base(spell, level, owner, skill, 0x51A048)
        self.w8(spell + 0x29, 0)
        self.wvec(spell + 0x50, self.vec(owner + 0x10))
        never = C.div(ONE, C.mul(ZERO, ZERO))
        for off, value in ((0x48, never), (0x4C, 0x3ECCCCEE), (0x3C, 0), (0x44, 0), (0x40, never)):
            w32(spell + off, value)
        for off, value in ((0x34, 200), (0x36, 100), (0x2C, 200), (0x2E, 100), (0x32, 0xFA), (0x2A, 0xFA), (0x38, 0x96),
                           (0x30, 0x96)):
            w16(spell + off, value)
        self.w8(spell + 0x28, 0)
        self.call('light_link', spell + 0x20)
        seconds = self.skill_call(self.u32(spell + 8), 10, 1, self.s8(spell))
        w32(spell + 0x1C, 0x55)
        w32(spell + 0x18, self.u32(G_SIM_FRAME) + s32(seconds) * 60)
        w32(spell + 0x5C, self.call('particleGroup_create'))
        handle = self.call('sound_playAtPos', self.call('res_find', 0x5505D8, 0x5505E0), self.vec(self.u32(spell + 0xC) + 0x10), ONE)
        w32(spell + 0x60, handle)
        self.call('sound_release', handle)

    def _shield_glow(self, spell, group):
        """What both shield spells do every frame: the owner's first flash quad pulses with
        sin16(frame x 1461), and - when the owner's model has sample points - four
        particles, each one OWN draw for the point and two balls (so at least seven own
        draws each).  A model without sample points makes no draw at all."""
        u32, w16 = self.u32, self.w16
        wave = C.sin16(s16(self.frame() * 0x5B5))
        owner = u32(spell + 0xC)
        five = C.mul(wave, 0x40A00000)
        w16(owner + 0x94, C.to_int(C.add(five, 0x427C0000)))
        w16(owner + 0x96, C.to_int(C.add(C.add(wave, wave), 0x41A00000)))
        w16(owner + 0x90, C.to_int(C.add(five, 0x42C80000)))
        w16(owner + 0x92, C.to_int(C.add(five, 0x429A0000)))
        matrix = C.mat34_set_pos_rot_z(self.vec(owner + 0x10), self.s16(owner + 0x38))
        self.call('particleGroup_setMatrix', u32(spell + group), tuple(matrix))
        self.call('particleGroup_begin', u32(spell + group))
        count = self.call('model_getSamplePointCount', self.vcall(u32(spell + 0xC), 16))
        if count:
            for _ in range(4):
                model = self.vcall(u32(spell + 0xC), 16)
                index = rem(self.spell_rand(spell), count)
                point = tuple(self.call('model_getSamplePoint', model, u32(spell + 0xC) + 0x114, (ZERO, ZERO, ZERO), 0, index,
                                        0, 0, ONE))
                b = self.spell_ball(spell)
                point = tuple(C.add(point[i], b[i]) for i in range(3))
                b = self.spell_ball(spell)
                self.call('particle_spawn', 0x8E6180, point, tuple(C.mul(b[i], 0x41874E39) for i in range(3)), ZERO)
        self.call('particleGroup_end', u32(spell + group))

    def undeadshield_run(self, spell, pos, facing=0):
        """SpellUndeadShield_run 0x2ea74c (spell, position, facing).

        frame >= end: the spell deletes itself.  Otherwise the light (fading in over the
        first second), the glow of _shield_glow, and on frames divisible by 15 the aura:
        every OTHER player of the box position -/+ 85 (capacity 64; same team only in PvP
        mode A, the owner's slot 22) that carries neither kind of shield gets a
        SpellSecondaryUndeadShield for half a second with percent = slot 10 (2, level):
        pool_new(0x24), the constructor (ONE SHARED DRAW), creature_addSpell.  Both
        "carries" questions are asked whatever the first one answers."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        frame = self.frame()
        if not frame < self.s32(spell + 0x18):
            self.spell_delete(spell)
            return
        wave = C.sin16(s16(frame * 0x5B5))
        seconds = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
        age = C.from_int(s32(0x3C - s32(seconds * 60 - s32(self.s32(spell + 0x18) - frame))))
        age = C.mul(C.add(age, age), DT)
        if C.lt(age, ZERO):
            age = ZERO
        if C.lt(ZERO, age):
            self.wvec(spell + 0x50, self.vec(u32(spell + 0xC) + 0x10))
            self.call('light_relink', spell + 0x20)
            size = C.add(C.add(wave, wave), 0x42F0001F)
            w32(spell + 0x3C, size)
            w32(spell + 0x44, size)
            inverse = C.div(ONE, C.mul(size, size))
            w32(spell + 0x48, inverse)
            w32(spell + 0x40, inverse)
            if C.lt(age, ONE):
                shades = [C.to_int(C.mul(age, k)) for k in (0x437A0000, 0x43480000, 0x42C80000, 0x43160000)]
                for i, value in enumerate(shades + shades):
                    w16(spell + 0x2A + 2 * i, value)
        else:
            self.call('light_unlink', spell + 0x20)
        self._shield_glow(spell, 0x5C)
        if not u32(spell + 0x1C) or rem(self.frame(), 15) != 0:
            return
        found = self.box_around(pos, C.from_int(self.s32(spell + 0x1C)), 0x40)
        owner = u32(spell + 0xC)
        for other in found:
            if other == owner or not u32(other + 0xC) & 0x40:
                continue
            if u32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, other):
                continue
            first = self.carries(other, self.SHIELD_GETTER)
            second = self.carries(other, self.SECONDARY_GETTER)
            if first or second:
                continue
            fresh = self.call('pool_new', 0x24)
            if fresh:
                percent = self.skill_call(u32(spell + 8), 10, 2, self.s8(spell))
                self.secondary_shield_ctor(fresh, percent, other, HALF)
            self.add_spell(other, fresh)

    def undeadshield_damage_attacker(self, spell, victim, attacker, incoming):
        """SpellUndeadShield_damageAttacker 0x2eaec0 (spell, victim, attacker, incoming
        damage).  Nothing for a spell of level 0.  Both flash quads of the victim = (100,
        0x4d, 0x3f, 0x14); d = (float) int(incoming x (slot 10 (0, level) x 0.01)); ONE OWN
        DRAW r; damage_apply(attacker, victim, 100000, flags 0x40, an empty descriptor;
        d, d + (d x r/65536) x 0.2)."""
        if not self.s8(spell):
            return
        self.flash_both(victim, 100, 0x4D, 0x3F, 0x14)
        percent = self.skill_call(self.u32(spell + 8), 10, 0, self.s8(spell))
        self._shield_reflect(spell, victim, attacker, incoming, percent)

    def _shield_reflect(self, spell, victim, attacker, incoming, percent):
        share = C.mul(C.from_int(s32(percent)), 0x3C23D70A)
        amount = C.from_int(s32(C.to_int(C.mul(C.from_int(s32(incoming)), share))))
        high = spread_max(amount, self.spell_rand(spell))
        self.call('damage_apply', attacker, victim, 100000, 0, 0, 0x40, descriptor(), 0, amount, high)

    def secondary_shield_ctor(self, spell, percent, victim, seconds):
        """SpellSecondaryUndeadShield_ctor 0x2eb050 (spell, percent, victim; seconds): the
        Spell base with level 0 and no Skill (ONE SHARED DRAW); percent +0x1c; end +0x18 =
        int(frame + seconds x 60.0); a particle group."""
        self.spell_base(spell, 0, victim, 0, 0x51A018)
        self.w32(spell + 0x1C, percent)
        self.w32(spell + 0x18, C.to_int(C.add(C.from_int(self.frame()), C.mul(seconds, 0x42700000))))
        self.w32(spell + 0x20, self.call('particleGroup_create'))

    def secondary_shield_run(self, spell, pos=None, facing=0):
        """SpellSecondaryUndeadShield_run 0x2eb170: the glow while frame < end, then the
        spell deletes itself."""
        if not self.frame() < self.s32(spell + 0x18):
            self.spell_delete(spell)
            return
        self._shield_glow(spell, 0x20)

    def secondary_shield_damage_attacker(self, spell, victim, attacker, incoming):
        """SpellSecondaryUndeadShield_damageAttacker 0x2eb5b4: the same with the percent
        stored at +0x1c and no level test."""
        self.flash_both(victim, 100, 0x4D, 0x3F, 0x14)
        self._shield_reflect(spell, victim, attacker, incoming, self.u32(spell + 0x1C))


SKILL_BODIES.update({0x2EB970: 'undeadshield_can_use', 0x2EB7CC: 'undeadshield_cast'})
SPELL_BODIES.update({0x2EA74C: 'undeadshield_run', 0x2EB170: 'secondary_shield_run'})
MODELLED.update({'SkillUndeadShield_canUse': 0x2EB970, 'SkillUndeadShield_cast': 0x2EB7CC, 'SpellUndeadShield_ctor': 0x2EA4D8,
                 'SpellUndeadShield_run': 0x2EA74C, 'SpellUndeadShield_damageAttacker': 0x2EAEC0,
                 'SpellSecondaryUndeadShield_ctor': 0x2EB050, 'SpellSecondaryUndeadShield_run': 0x2EB170,
                 'SpellSecondaryUndeadShield_damageAttacker': 0x2EB5B4})


def carries_getter(mem_u32, function):
    """The type-info getter a "refused while the caster carries a spell of class X" can-use
    function asks for, read from its instructions (the shape of 0x2ce2b0: `jal getter` as
    the fourth instruction, `jal creature_findSpellByType` as the seventh), or None for
    any other function.  Ids 5, 6, 8, 10, 12-15, 17, 26 and 33 have this shape."""
    first, second = mem_u32(function + 0xC), mem_u32(function + 0x18)
    if first >> 26 == 3 and second == 0x0C000000 | (0x11A710 >> 2):
        return (first & 0x3FFFFFF) << 2
    return None


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Can-use of the skills whose cast and effect are NOT modelled here (ids 5, 6, 8, 10,
    # 13, 17; 18 answers 1; 1 and 22 use the base): the generic "carries" shape.
    # =====================================================================================
    def skill_call(self, skill, slot, *args):
        if slot == 1:
            table = self.u32(skill + 0x60)
            function = self.u32(table + 8 * slot + 4)
            if function not in SKILL_BODIES and ('Skill.v1' not in self.external):
                getter = carries_getter(self.u32, function)
                if getter is not None and getter in self.type_info:
                    return 0 if self.carries(args[0], getter) else 1
                if self.u32(function) == 0x03E00008 and self.u32(function + 4) == 0x24020001:
                    return 1                                    # jr ra; li v0, 1 (e.g. 0x2f123c)
        return super().skill_call(skill, slot, *args)

    def can_use_slot(self, skill, caster):
        """Slot 1 of any skill, through its table."""
        return self.skill_call(skill, 1, caster)


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 13, Fire Weapons: SkillFireWeapons (table 0x519a00) and SpellFireWeapons (0x60
    # bytes, table 0x519a88).  The weapon-buff template of ids 12 / 14 / 26 with entry type
    # 0x15, weapon-holder slot 2, its own light record and no LightEffect.
    #
    #   +0x18 end frame   +0x1c aura radius (int)   +0x20..+0x58 a light record (position
    #   +0x50, range +0x3c / +0x44, 1 / range^2 +0x40 / +0x48)   +0x5c the frame of the cast
    # =====================================================================================
    FIREWEAPONS_GETTER = 0x3CEC68
    FIREWEAPONS_PUFFS = ((0x8E5D20, 4, 0x414A14C9, 0x40EE541D), (0x8E5D70, 5, 0x414A0AC0, 0x40DF7C5E),
                         (0x8E5DC0, 1, 0x418E63DB, 0x40D701A7))

    def fireweapons_can_use(self, skill, caster):
        """SkillFireWeapons_canUse 0x2e4df8 -> 1 unless the caster carries a
        SpellFireWeapons."""
        return 0 if self.carries(caster, self.FIREWEAPONS_GETTER) else 1

    def fireweapons_cast(self, skill, level, caster, pos=None, facing=0):
        """SkillFireWeapons_cast 0x2e4ad0 -> the spell: pool_new(0x60) and the constructor."""
        spell = self.call('pool_new', 0x60)
        if spell:
            self.fireweapons_ctor(spell, level, caster, skill)
        return spell

    def fireweapons_ctor(self, spell, level, owner, skill):
        """SpellFireWeapons_ctor 0x2e34e0 (spell, level, owner, skill).

        The Spell base (ONE SHARED DRAW).  The light record at +0x20: position = the
        owner's, range words 0, the two 1 / range^2 words = 1.0 / 0.0 AS THE MACHINE
        DIVIDES IT (the largest number, not an infinity), colour halfwords (0xff, 0x80, 0,
        0) twice; light_link.  end +0x18 = frame + slot 12 (1, level as passed, owner, cap
        20) x 60; radius +0x1c = slot 12 (2, the stored level byte, owner, cap 10) x 12;
        +0x5c = frame.  dmg = slot 12 (0, ..., cap 0), frames = slot 12 (1, ..., cap 20) x
        60.  An owner that is not a player: its weapon holder's slot 2 with 1.  A player:
        both weapons get (0x15, dmg, round(1.2 dmg), frames) by the rule of enchant() with
        the limit `frames`.  The sound at the owner's position.  No LightEffect, no flash."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.spell_base(spell, level, owner, skill, 0x519A88)
        huge = C.div(ONE, ZERO)
        self.w8(spell + 0x29, 0)
        self.wvec(spell + 0x50, self.vec(owner + 0x10))
        for off, value in ((0x48, huge), (0x4C, 0x3F266655), (0x3C, 0), (0x44, 0), (0x40, huge)):
            w32(spell + off, value)
        for off, value in ((0x32, 0xFF), (0x34, 0x80), (0x2A, 0xFF), (0x2C, 0x80), (0x2E, 0), (0x30, 0), (0x36, 0), (0x38, 0)):
            w16(spell + off, value)
        self.w8(spell + 0x28, 0)
        self.call('light_link', spell + 0x20)
        seconds = self.skill_call(skill, 12, 1, level, owner, 0x14)
        w32(spell + 0x18, u32(G_SIM_FRAME) + s32(seconds) * 60)
        radius = self.skill_call(u32(spell + 8), 12, 2, self.s8(spell), owner, 10)
        w32(spell + 0x5C, u32(G_SIM_FRAME))
        w32(spell + 0x1C, s32(radius) * 12)
        dmg = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), owner, 0)
        frames = s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), owner, 0x14)) * 60
        owner = u32(spell + 0xC)
        if not u32(owner + 0xC) & 0x40:
            holder = u32(owner + 0x50)
            if holder:
                self.holder_call(holder, 2, 1)
        else:
            for item in self.weapons_of(owner):
                self.enchant(item, 0x15, dmg, frames, frames)
        self.call('sound_playAtPos', self.call('res_find', 0x54FF80, 0x54FF88), self.vec(u32(spell + 0xC) + 0x10), ONE)

    def fireweapons_run(self, spell, pos, facing=0):
        """SpellFireWeapons_run 0x2e3b28 (spell, position, facing).

        frame >= end: an owner that is a creature but not a player and has a weapon holder
        gets holder slot 8 (1, 0); the spell deletes itself.
        Otherwise, during the first 30 frames, 4 + 5 + 1 particles: position = an OWN ball
        x spread + the run position, velocity = (cos, sin of the facing) x speed + a second
        OWN ball.  The light: range r = (float)((int)((sin16(frame x 4000) + sin16(frame x
        2000)) x 4) + 110) while more than 30 frames are left (and during the opening),
        min(300, left x (1 / 30) x 110) in the last 30; +0x3c = +0x44 = r, +0x40 = +0x48 =
        1 / r^2; its position = the run position + (cos, sin) x 18; light_relink.
        The aura - a radius, a PLAYER owner and frame % 30 == 0: every other player of the
        box position -/+ radius (capacity 64; same team only in PvP mode A, the owner's
        slot 22) gets, on both weapons, (0x15, a, round(1.2 a), 31) by the rule of enchant()
        with limit 31, a = slot 12 (3, level, owner, cap 10).
        Last: an owner that is a DEAD creature and not a player gets holder slot 8 (1, 0)
        and the spell deletes itself."""
        u32, w32 = self.u32, self.w32
        frame = self.frame()
        facing = s16(facing)
        owner = u32(spell + 0xC)
        if not frame < self.s32(spell + 0x18):
            if u32(owner + 0xC) & 0x60 == 0x20 and u32(owner + 0x50):
                self.holder_call(u32(owner + 0x50), 8, 1, 0)
            self.spell_delete(spell)
            return
        left = s32(self.s32(spell + 0x18) - frame)
        flicker = True
        if s32(frame - self.s32(spell + 0x5C)) < 0x1E:
            for definition, count, spread, speed in self.FIREWEAPONS_PUFFS:
                for _ in range(count):
                    b = self.spell_ball(spell)
                    point = tuple(C.add(C.mul(b[i], spread), pos[i]) for i in range(3))
                    push = (C.mul(C.cos16(facing), speed), C.mul(C.sin16(facing), speed), ZERO)
                    b = self.spell_ball(spell)
                    self.call('particle_spawn', definition, point, tuple(C.add(push[i], b[i]) for i in range(3)), ZERO)
        elif not left > 0x1E:
            flicker = False
        if flicker:
            wave = C.add(C.sin16(s16(frame * 4000)), C.sin16(s16(frame * 2000)))
            reach = C.from_int(s32(C.to_int(C.mul(wave, 0x40800000))) + 0x6E)
        else:
            reach = C.fmin(0x43960000, C.mul(C.mul(C.from_int(left), 0x3D088888), 0x42DC0000))
        w32(spell + 0x3C, reach)
        w32(spell + 0x44, reach)
        inverse = C.div(ONE, C.mul(reach, reach))
        w32(spell + 0x48, inverse)
        w32(spell + 0x40, inverse)
        ahead = (C.mul(C.cos16(facing), 0x41900000), C.mul(C.sin16(facing), 0x41900000), ZERO)
        self.wvec(spell + 0x50, tuple(C.add(ahead[i], pos[i]) for i in range(3)))
        self.call('light_relink', spell + 0x20)
        if self.s32(spell + 0x1C) and u32(u32(spell + 0xC) + 0xC) & 0x40 and rem(self.frame(), 30) == 0:
            found = self.box_around(pos, C.from_int(self.s32(spell + 0x1C)), 0x40)
            owner = u32(spell + 0xC)
            for other in found:
                if other == owner or not u32(other + 0xC) & 0x40:
                    continue
                if u32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, other):
                    continue
                first, second = self.weapons_of(other)
                aura = self.skill_call(u32(spell + 8), 12, 3, self.s8(spell), u32(spell + 0xC), 10)
                self.enchant(first, 0x15, aura, 0x1F, 0x1F)
                self.enchant(second, 0x15, aura, 0x1F, 0x1F)
        owner = u32(spell + 0xC)
        if u32(owner + 0xC) & 0x68 == 0x28:
            if u32(owner + 0x50):
                self.holder_call(u32(owner + 0x50), 8, 1, 0)
            self.spell_delete(spell)


SKILL_BODIES.update({0x2E4DF8: 'fireweapons_can_use', 0x2E4AD0: 'fireweapons_cast'})
SPELL_BODIES.update({0x2E3B28: 'fireweapons_run'})
MODELLED.update({'SkillFireWeapons_canUse': 0x2E4DF8, 'SkillFireWeapons_cast': 0x2E4AD0,
                 'SpellFireWeapons_ctor': 0x2E34E0, 'SpellFireWeapons_run': 0x2E3B28})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 18, Cone of Fire: SkillConeOfFire (table 0x51a3e8, channelled) and
    # SpellConeOfFire (0x58 bytes, table 0x51a470).
    #
    #   +0x18..+0x50 a light record (position +0x48, range +0x34 / +0x3c, 1 / range^2
    #   +0x38 / +0x40)   +0x54 the looping sound
    # =====================================================================================
    CONEOFFIRE_SPRAY = ((0x8E63B0, 20, 0x409FFE80, 0x426FFFD7), (0x8E6400, 5, 0x40A00000, 0x4270000D),
                        (0x8E6450, 3, 0x40A0000E, 0x42200057))

    def coneoffire_can_use(self, skill, caster=0):
        """SkillConeOfFire_canUse 0x2f123c -> 1."""
        return 1

    def coneoffire_cast(self, skill, level, caster, pos=None, facing=0):
        """SkillConeOfFire_cast 0x2f1078 -> the spell: pool_new(0x58) and the constructor."""
        spell = self.call('pool_new', 0x58)
        if spell:
            self.coneoffire_ctor(spell, level, caster, skill)
        return spell

    def coneoffire_ctor(self, spell, level, owner, skill):
        """SpellConeOfFire_ctor 0x2f00ac (spell, level, owner, skill): the Spell base (ONE
        SHARED DRAW); the light record at +0x18 (position = the owner's, range 0, 1 /
        range^2 = 1.0 / 0.0 as the machine divides it), linked; the looping sound at the
        owner's position, kept at +0x54 and released to repeat.  No statistic is read."""
        w32, w16 = self.w32, self.w16
        self.spell_base(spell, level, owner, skill, 0x51A470)
        huge = C.div(ONE, ZERO)
        self.w8(spell + 0x21, 0)
        self.wvec(spell + 0x48, self.vec(owner + 0x10))
        for off, value in ((0x2C, 0x7D), (0x24, 0x7D), (0x2A, 0xFF), (0x22, 0xFF), (0x30, 0x42), (0x28, 0x42), (0x26, 0),
                           (0x2E, 0)):
            w16(spell + off, value)
        for off, value in ((0x40, huge), (0x44, 0x3F19DB22), (0x34, 0), (0x3C, 0), (0x38, huge)):
            w32(spell + off, value)
        self.w8(spell + 0x20, 0)
        self.call('light_link', spell + 0x18)
        sound = self.call('sound_playAtPos', self.call('res_find', 0x550B00, 0x550B08),
                          self.vec(self.u32(spell + 0xC) + 0x10), ONE)
        w32(spell + 0x54, sound)
        self.call('sound_release', sound)

    def coneoffire_run(self, spell, pos, facing=0):
        """SpellConeOfFire_run 0x2f02fc (spell, position, facing), every frame the channel
        is held.

          1. the light's range r = (float)((int)((sin16(frame x 3500) + sin16(frame x
             1750)) x 10) + 80): +0x34 = +0x3c = r, +0x38 = +0x40 = 1 / r^2 (the light is
             not moved and not relinked here).
          2. a = slot 12 (1, level, owner, cap 10), the arc in degrees.  28 particles (20,
             5, 3 of three kinds), each: an OWN ball x spread + the run position; a second
             OWN ball as velocity, to which (cos16(t1), sin16(t2)) x speed is added, t =
             (int)((facing - 91 a) + (d x 2^-16) x (182 a)) with a fresh OWN draw d for
             each of the two - the x and y parts come from DIFFERENT angles.
          3. frame % 15 == 0: world_collectObjectsInArc(position - (cos, sin of the facing)
             x 12, facing, no filter; 96, a + 10 degrees, 0) with a re-read of the arc
             statistic.  For every entry the owner's slot 20 calls an enemy: s0 = slot 12
             (0, level, owner, cap 0); v1 = (int)(s0 x 0.25); ONE OWN DRAW r; v2 =
             (int)(((float)v1 + ((float)v1 x (r x 2^-16)) x 0.2) x 0.25) - THE MAXIMUM IS
             SCALED BY 0.25 A SECOND TIME (0x2f0e5c), so v2 < v1 for every v1 > 0, and
             v2 = v1 - 1 = 0 when v1 is 1; damage_apply(entry, owner, 100000, flags 0x40,
             descriptor slot 0 = (0x15, v1, v2, 0), 0; 0, 0).  When anything was damaged
             the hit sound at the owner's position.  The list is freed."""
        u32, w32 = self.u32, self.w32
        facing = s16(facing)
        frame = self.frame()
        wave = C.add(C.sin16(s16(frame * 0xDAC)), C.sin16(s16(frame * 0x6D6)))
        reach = C.from_int(s32(C.to_int(C.mul(wave, 0x41200000))) + 0x50)
        w32(spell + 0x34, reach)
        w32(spell + 0x3C, reach)
        inverse = C.div(ONE, C.mul(reach, reach))
        w32(spell + 0x40, inverse)
        w32(spell + 0x38, inverse)
        arc = s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), u32(spell + 0xC), 10))
        for definition, count, spread, speed in self.CONEOFFIRE_SPRAY:
            for _ in range(count):
                b = self.spell_ball(spell)
                point = tuple(C.add(C.mul(b[i], spread), pos[i]) for i in range(3))
                v = self.spell_ball(spell)
                base, width = C.from_int(s32(facing - arc * 0x5B)), C.from_int(s32(arc * 0xB6))
                turn = C.to_int(C.add(base, C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), width)))
                vx = C.add(v[0], C.mul(C.cos16(turn), speed))
                turn = C.to_int(C.add(base, C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), width)))
                vy = C.add(v[1], C.mul(C.sin16(turn), speed))
                self.call('particle_spawn', definition, point, (vx, vy, v[2]), ZERO)
        if rem(self.frame(), 15) != 0:
            return
        origin = (C.sub(pos[0], C.mul(C.cos16(facing), F_12)), C.sub(pos[1], C.mul(C.sin16(facing), F_12)), pos[2])
        arc = s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), u32(spell + 0xC), 10))
        found = self.call('world_collectObjectsInArc', origin, facing, 'stack', 0, 0x42C00000, C.from_int(arc + 10), ZERO)
        hit = False
        for other in found or ():
            owner = u32(spell + 0xC)
            if not self.vcall(owner, 20, other):
                continue
            s0 = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), u32(spell + 0xC), 0)
            low = C.to_int(C.mul(C.from_int(s32(s0)), 0x3E800000))
            base = C.from_int(s32(low))
            high = C.to_int(C.mul(spread_max(base, self.spell_rand(spell)), 0x3E800000))
            hit = True
            self.call('damage_apply', other, u32(spell + 0xC), 100000, 0, 0, 0x40, descriptor((0x15, low, high, 0)), 0,
                      ZERO, ZERO)
        if hit:
            self.call('sound_playAtPos', self.call('res_find', 0x550B00, 0x550B38), self.vec(u32(spell + 0xC) + 0x10), ONE)
        self.call('handle_clear', 'stack')


SKILL_BODIES.update({0x2F123C: 'coneoffire_can_use', 0x2F1078: 'coneoffire_cast'})
SPELL_BODIES.update({0x2F02FC: 'coneoffire_run'})
MODELLED.update({'SkillConeOfFire_canUse': 0x2F123C, 'SkillConeOfFire_cast': 0x2F1078,
                 'SpellConeOfFire_ctor': 0x2F00AC, 'SpellConeOfFire_run': 0x2F02FC})


import ref_items as RI                          # noqa: E402

G_ITEM_MODELS = 0x3E9CE0                        # rows of 0x10; +8 the loaded model (a pointer; presentation)
G_HAMMER_COUNT = 0x41B4F0                       # a byte: hammers alive (nothing reads it)
EXTERNALS.update({
    'model_transformSamplePoint': Ext(0x1799E8, 'pmioo', 0, 'n', '(model, matrix, index, point out, size out)'),
})
MATH.update({'mat34_setPosEulerScale': 0x163E48, 'mat34_mul': 0x162808, 'mat34_rotateAxis': 0x163000})


class _ImageExe(RI.Exe):
    """The item tables of tools/ref_items.py read from a memory image instead of a file."""

    def __init__(self, load):                   # noqa: super().__init__ opens a file
        self.load = load

    def read(self, addr, size):
        return bytes(self.load(addr + i, 1) for i in range(size))

    def cstr(self, addr):
        out = bytearray()
        while True:
            byte = self.load(addr + len(out), 1)
            if not byte:
                return bytes(out)
            out.append(byte)


class _SharedDraws:
    """tools/ref_items.py's Rng interface on the model's shared seed."""

    def __init__(self, model):
        self.model = model

    def next(self):
        return self.model.draw()


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 17, Hammer of Wrath: SkillHammerOfWrath (table 0x51a330), the object
    # HammerOfWrath (0xe8 bytes, table 0x51a2a0) and SpellHammerOfWrath (0x1c bytes, table
    # 0x51a3b8), which only holds a handle to the hammer.
    #
    #   +0x38 s16 rest heading     +0x4c owner handle        +0x50 target handle
    #   +0x58 item record (0x48)   +0xa0 counter c           +0xa4 level + 1
    #   +0xa8 frames left          +0xac yaw  +0xb0 pitch  +0xb4 roll and +0xb8, +0xbc,
    #   +0xc0 their velocities (floats, in angle units)      +0xc4 Skill   +0xc8 state
    #   +0xcc velocity per FRAME   +0xd8 goal point
    # =====================================================================================
    HAMMER_GETTER = 0x3CF768
    HAMMER_TEXTS = {0: 0x5508D0, 1: 0x5508F0, 2: 0x550910, 3: 0x550930}        # else 0x550950
    item_tables_cache = None

    def item_tables(self):
        """tools/ref_items.py's tables, read once from the memory image (static data)."""
        if Model.item_tables_cache is None:
            Model.item_tables_cache = RI.Tables(_ImageExe(self.mem.load))
        return Model.item_tables_cache

    def item_parse(self, text, record):
        """item_parseDescriptor 0x1069b8 (text, record, variant -1, presets 0), as
        tools/ref_items.py models it, on the record in memory.

        The definition pointer, the count, the flag word and one slot per modifier are
        stored; the rest of the record is left as the caller prepared it.  The variant -1
        ends in item_randomizeVariant 0x1046e0: ONE SHARED DRAW when the definition has
        model variants (bits 11-15 of its flag word), none otherwise."""
        raw = _ImageExe(self.mem.load).cstr(text)
        item = RI.parse_descriptor(self.item_tables(), raw, -1, False, rng=_SharedDraws(self))
        self.w32(record, item.definition.addr)
        self.w16(record + 4, item.count)
        self.w64(record + 8, item.flags & M64)
        for index, mod in enumerate(item.mods):
            if mod is not None:
                for k in range(4):
                    self.w16(record + 0x24 + 8 * index + 2 * k, mod[k])

    def item_resource_index(self, record):
        """item_getResourceIndex 0x1083f8: definition +0x34 (s16), plus the variant (flag
        bits 11-15) when flag bit 36 is set."""
        row = self.s16(self.u32(record) + 0x34)
        flags = self.u64(record + 8)
        if flags & 0x1000000000:
            row += (flags >> 11) & 0x1F
        return row

    def hammer_can_use(self, skill, caster):
        """SkillHammerOfWrath_canUse 0x2efef8 -> 1 unless the caster carries a
        SpellHammerOfWrath (its hammer exists)."""
        return 0 if self.carries(caster, self.HAMMER_GETTER) else 1

    def hammer_cast(self, skill, level, caster, pos, facing):
        """SkillHammerOfWrath_cast 0x2efb20 (skill, level, caster, position, facing) -> the
        spell or 0.

        Both flash quads of the caster = (-100, -100, -100, 0); a GlowingShaft at the
        position and a LightEffect 36 above it (ONE SHARED DRAW inside each); pool_new
        (0xe8) and HammerOfWrath_ctor 60 above the position; only with a hammer:
        pool_new(0x1c) and SpellHammerOfWrath_ctor.  A hammer whose spell could not be
        allocated stays (and lives its statistic-1 seconds)."""
        self.flash_both(caster, -100, -100, -100, 0)
        shaft = self.call('pool_new', 0x5C)
        if shaft:
            self.call('GlowingShaft_ctor', shaft, tuple(pos), 0x5A, 0x56, 0x7E, 0xFA)
            self.hidden_draws += 1
        self.light_effect(0xBC, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x42100000)), 0, 0,
                          ZERO, 0x431B0000, 0x437F0000, 0xC2C00000, ZERO, ZERO, ZERO, ZERO,
                          0x43340000, 0x43100000, ZERO, ONE)
        hammer = self.call('pool_new', 0xE8)
        if hammer:
            self.hammer_ctor(hammer, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], 0x42700000)), s16(facing), caster, level,
                             skill)
        spell = 0
        if hammer:
            spell = self.call('pool_new', 0x1C)
            if spell:
                self.hammer_spell_ctor(spell, level, caster, skill, hammer)
        return spell

    def hammer_ctor(self, obj, pos, facing, owner, level, skill):
        """HammerOfWrath_ctor 0x2edd78 (object, position, facing, owner, level, skill).

        GameObject_ctor (ONE SHARED DRAW); both handles empty; the item record at +0x58
        made empty (slot types -1, bytes +0x20 / +0x21 = 0xff, the eight halfwords at
        +0x10 = 0); the heading; the owner handle; level +0xa4; item_parseDescriptor on
        the text for the level (0, 1, 2, 3, else one more) with variant -1 - ONE MORE
        SHARED DRAW when the base item has model variants; THEN THE STORED LEVEL IS RAISED
        BY ONE (0x2edefc), and every statistic read of the object uses that; flags |= 1;
        the every-frame run list; the sound; roll +0xb4 = 16384; goal = position; the
        Skill; frames left +0xa8 = slot 10 (1, level + 1) x 60; the byte 0x41b4f0 += 1."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.gameobject_ctor(obj, pos, 0, 0)
        w32(obj + 0x4C, 0)
        w32(obj + 0x48, 0x51A2A0)
        w32(obj + 0x50, 0)
        record = obj + 0x58
        for k in range(4):
            w16(record + 0x24 + 8 * k, 0xFFFF)
        self.w8(record + 0x21, 0xFF)
        self.w8(record + 0x20, 0xFF)
        for k in range(8):
            w16(record + 0x10 + 2 * k, 0)
        w16(obj + 0x38, facing)
        if owner:
            self.call('handle_link', obj + 0x4C, owner, owner)
        w32(obj + 0xA4, level)
        self.item_parse(self.HAMMER_TEXTS.get(s32(level), 0x550950), record)
        w32(obj + 0xA4, u32(obj + 0xA4) + 1)
        w32(obj + 0xC, u32(obj + 0xC) | 1)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', 0x550970, 0x550978), obj, ONE)
        w32(obj + 0xB4, 0x46800000)
        self.wvec(obj + 0xD8, self.vec(obj + 0x10))
        w32(obj + 0xC4, skill)
        w32(obj + 0xA8, s32(self.skill_call(skill, 10, 1, u32(obj + 0xA4))) * 60)
        self.w8(G_HAMMER_COUNT, self.u8(G_HAMMER_COUNT) + 1)

    def hammer_spell_ctor(self, spell, level, owner, skill, hammer):
        """SpellHammerOfWrath_ctor 0x2ef974 (spell, level, owner, skill, hammer): the Spell
        base (ONE SHARED DRAW) and a handle to the hammer at +0x18."""
        self.spell_base(spell, level, owner, skill, 0x51A3B8)
        self.w32(spell + 0x18, 0)
        if hammer:
            self.call('handle_link', spell + 0x18, hammer, hammer)

    def hammer_spell_run(self, spell, pos=None, facing=0):
        """SpellHammerOfWrath_run 0x2efa04: the spell deletes itself once its hammer handle
        is empty."""
        if not self.u32(spell + 0x18):
            self.spell_delete(spell)

    def _hammer_pull(self, obj, anchor, slack):
        """Move the goal +0xd8 toward a point until it is `slack` away: L = |goal -
        anchor|; when slack < L: goal += (anchor - goal) x (1 - slack / L), z first."""
        u32 = self.u32
        goal = self.vec(obj + 0xD8)
        d = [C.sub(goal[i], anchor[i]) for i in range(3)]
        length = C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
        if C.lt(slack, length):
            f = C.sub(ONE, C.div(slack, length))
            for i in (2, 1, 0):
                self.w32(obj + 0xD8 + 4 * i, C.add(goal[i], C.mul(C.sub(anchor[i], goal[i]), f)))

    def _hammer_blow(self, obj, victim, rating):
        """One blow: d = slot 10 (0, level + 1); ONE OWN DRAW r; damage_apply(victim, the
        owner, rating, flags 0x101, the item record at +0x58, 0; d, d + d x r/65536 x
        0.2); the sound."""
        u32 = self.u32
        amount = C.from_int(s32(self.skill_call(u32(obj + 0xC4), 10, 0, u32(obj + 0xA4))))
        high = spread_max(amount, self.obj_rand(obj))
        self.call('damage_apply', victim, u32(u32(obj + 0x4C) + 0xC), rating, 0, 0, 0x101, obj + 0x58, 0, amount, high)
        self.call('sound_playOnObject', self.call('res_find', 0x550970, 0x5509A8), obj, ONE)

    def hammer_run(self, obj):
        """HammerOfWrath_run 0x2ee068 (object), slot 4, once a frame.

        No owner (handle +0x4c empty): the object deletes itself.  anchor = the owner's
        position + (0, 0, 60); farther than 600 from it, during a cutscene, or with a
        player owner whose action state +0x58c is 8 (blocking): state = 0.

        state 0  the goal follows the anchor at 60; world_collectObjectsInBox(anchor -/+
                 (180, 180, 1200), capacity 128) - always; outside cutscenes and blocking:
                 the entry with terrain_raycast(world, position, entry - position, 0; 1.0)
                 <= 0 that the owner's slot 20 calls an enemy and that is nearest to the
                 anchor (3-D, squared, below 32400) becomes the target: handle +0x50, ONE
                 OWN DRAW r, state = 4 when r/65536 x 100 < slot 10 (2, level + 1), else 3
                 (during a cutscene no target is looked for at all); c = 0.
        state 3  no target or a dead one: state 0.  Else the goal follows target + (0, 0,
                 60) at 24; c += 1; at c == 47 the blow (attack rating 300000); at c >= 61
                 c = 0 and, in PvP mode A, state = 0.
        state 4  c += 1; yaw velocity +0xb8 = -3500; at c >= 61 and c % 20 == 0 the blow
                 (rating 3000) on the nearest living non-player CREATURE of the box
                 position -/+ (72, 72, 1200) within 72 (3-D) - no enemy test; without a
                 target the goal circles the owner (radius 36, angle c << 9, 36 up), with a
                 dead one state = 0, else it follows the target as in state 3; (c << 9) >
                 0x10000: state = 0.
        states 1, 2  never stored by anything (not modelled: NotImplementedError).

        Then in every state: the three orientation springs (yaw toward the aim angle with
        the state's stiffness and damping, pitch and roll toward the state's targets at
        0.05 / 0.2, both shaken by sin16(frame << 10) and sin16(frame x 800) x 20), the
        velocity wobble sin16(frame x 403 / 358 / 332) x 0.01, velocity += (goal -
        position) x k, position += velocity, velocity -= velocity x damp, the grid cell;
        the model matrix and 2 or more particles on the hammer's model from the PER-MACHINE
        generator 0x404468 (the count rises over the last 120 frames; 3000 on the last);
        frames left -= 1 and below 1 the object deletes itself."""
        u32, w32 = self.u32, self.w32
        roll, pitch = 0x46800000, 0xC61C4000
        turn_k, turn_damp, pos_k, pos_damp = 0x399D4951, 0x3C23D70A, 0x3B449BA5, 0x3D4CCCCC
        aim = self.s16(obj + 0x38)
        node = u32(obj + 0x4C)
        if not node:
            self.delete_self(obj)
            return
        owner = u32(node + 0xC)
        anchor = (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42700000))
        d = [C.sub(anchor[i], u32(obj + 0x10 + 4 * i)) for i in range(3)]
        if C.lt(0x48AFC800, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2]))):
            w32(obj + 0xC8, 0)
        if self.s8(G_CUTSCENE_ACTIVE):
            w32(obj + 0xC8, 0)
        blocked = False
        if u32(owner + 0xC) & 0x40 and u32(owner + 0x58C) == 8:
            w32(obj + 0xC8, 0)
            blocked = True
        state = u32(obj + 0xC8)
        if state == 0:
            v = self.vec(obj + 0xCC)
            if C.lt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))):
                aim = -C.atan2_16(v[0], v[1])
            anchor = self.vec(obj + 0x10)
            if u32(obj + 0x4C):
                owner = u32(u32(obj + 0x4C) + 0xC)
                anchor = (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42700000))
                self._hammer_pull(obj, anchor, 0x42700000)
            reach = (0x43340000, 0x43340000, 0x44960000)
            found = self.call('world_collectObjectsInBox', tuple(C.sub(anchor[i], reach[i]) for i in range(3)),
                              tuple(C.add(anchor[i], reach[i]) for i in range(3)), 0x80) or ()
            best, best_d = 0, 0x46FD2000
            if not self.s8(G_CUTSCENE_ACTIVE) and not blocked:
                for other in found:
                    way = tuple(C.sub(u32(other + 0x10 + 4 * i), u32(obj + 0x10 + 4 * i)) for i in range(3))
                    t = self.call('terrain_raycast', u32(G_WORLD), self.vec(obj + 0x10), way, 0, ONE)
                    if C.le(t, ZERO) and u32(obj + 0x4C):
                        owner = u32(u32(obj + 0x4C) + 0xC)
                        if self.vcall(owner, 20, other):
                            e = [C.sub(anchor[i], u32(other + 0x10 + 4 * i)) for i in range(3)]
                            dist = C.add(C.add(C.mul(e[0], e[0]), C.mul(e[1], e[1])), C.mul(e[2], e[2]))
                            if C.lt(dist, best_d):
                                best, best_d = other, dist
            if best:
                self.call('handle_link', obj + 0x50, best, best)
                state = 3
                if not self.s8(G_CUTSCENE_ACTIVE):
                    r = self.obj_rand(obj)
                    chance = s32(self.skill_call(u32(obj + 0xC4), 10, 2, u32(obj + 0xA4)))
                    if C.lt(C.mul(C.mul(C.from_int(r), F_2M16), 0x42C80000), C.from_int(chance)):
                        state = 4
                w32(obj + 0xA0, 0)
                w32(obj + 0xC8, state)
        elif state == 3:
            target = self.handle_obj(obj + 0x50)
            if not u32(obj + 0x50) or u32(target + 0xC) & 8:
                w32(obj + 0xC8, 0)
            else:
                turn_k, turn_damp = 0x3DCCCCCC, 0x3F199999
                aim = -C.atan2_16(C.sub(u32(target + 0x10), u32(obj + 0x10)), C.sub(u32(target + 0x14), u32(obj + 0x14)))
                self._hammer_pull(obj, (C.add(u32(target + 0x10), ZERO), u32(target + 0x14),
                                        C.add(u32(target + 0x18), 0x42700000)), 0x41C00000)
                pos_k, pos_damp = 0x3BC49BA5, 0x3E199999
                count = s32(u32(obj + 0xA0) + 1)
                w32(obj + 0xA0, count)
                if count > 0x1E:
                    pitch = 0xC69C4000
                if count > 0x29:
                    pitch = ZERO
                if count == 0x2F:
                    self._hammer_blow(obj, target, 300000)
                if not self.s32(obj + 0xA0) < 0x3D:
                    w32(obj + 0xA0, 0)
                    if u32(G_PVP_MODE_A):
                        w32(obj + 0xC8, 0)
        elif state == 4:
            pitch = ZERO
            count = s32(u32(obj + 0xA0) + 1)
            w32(obj + 0xA0, count)
            w32(obj + 0xB8, 0xC55AC000)
            pos_k, pos_damp, roll = 0x3C23D70A, 0x3E4CCCCC, ZERO
            if not count < 0x3D and rem(count, 0x14) == 0:
                reach = (0x42900000, 0x42900000, 0x44960000)
                here = self.vec(obj + 0x10)
                found = self.call('world_collectObjectsInBox', tuple(C.sub(here[i], reach[i]) for i in range(3)),
                                  tuple(C.add(here[i], reach[i]) for i in range(3)), 0x80) or ()
                victim, best_d = 0, 0x45A20000
                for other in found:
                    flags = u32(other + 0xC)
                    if not flags & 0x20 or flags & 0x48:
                        continue
                    e = [C.sub(u32(obj + 0x10 + 4 * i), u32(other + 0x10 + 4 * i)) for i in range(3)]
                    dist = C.add(C.add(C.mul(e[0], e[0]), C.mul(e[1], e[1])), C.mul(e[2], e[2]))
                    if C.lt(dist, best_d):
                        victim, best_d = other, dist
                if victim:
                    self._hammer_blow(obj, victim, 3000)
            ended = False
            if not u32(obj + 0x50):
                owner = u32(u32(obj + 0x4C) + 0xC)
                base = (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42100000))
                turn = s16(u32(obj + 0xA0) << 9)
                self.wvec(obj + 0xD8, (C.add(base[0], C.mul(C.cos16(turn), 0x42100000)),
                                       C.add(base[1], C.mul(C.sin16(turn), 0x42100000)), base[2]))
            else:
                target = self.handle_obj(obj + 0x50)
                if u32(target + 0xC) & 8:
                    w32(obj + 0xC8, 0)
                    ended = True
                else:
                    turn_k, turn_damp = 0x3DCCCCCC, 0x3F199999
                    aim = -C.atan2_16(C.sub(u32(target + 0x10), u32(obj + 0x10)), C.sub(u32(target + 0x14), u32(obj + 0x14)))
                    self._hammer_pull(obj, (C.add(u32(target + 0x10), ZERO), u32(target + 0x14),
                                            C.add(u32(target + 0x18), 0x42700000)), 0x41C00000)
            if not ended and s32(u32(obj + 0xA0) << 9) > 0x10000:
                w32(obj + 0xC8, 0)
        elif state in (1, 2):
            raise NotImplementedError('HammerOfWrath states 1 and 2: nothing stores them')
        # the springs
        yaw = u32(obj + 0xAC)
        spin = C.add(u32(obj + 0xC0), C.mul(C.sub(roll, u32(obj + 0xB4)), 0x3D4CCCCC))
        tilt = C.add(u32(obj + 0xBC), C.mul(C.sub(pitch, u32(obj + 0xB0)), 0x3D4CCCCC))
        swing = C.add(u32(obj + 0xB8), C.mul(C.from_int(s16(aim - s32(C.to_int(yaw)))), turn_k))
        spin = C.sub(spin, C.mul(spin, F_0_2))
        tilt = C.sub(tilt, C.mul(tilt, F_0_2))
        swing = C.sub(swing, C.mul(swing, turn_damp))
        w32(obj + 0xC0, spin)
        w32(obj + 0xBC, tilt)
        w32(obj + 0xB4, C.add(u32(obj + 0xB4), spin))
        w32(obj + 0xB0, C.add(u32(obj + 0xB0), tilt))
        w32(obj + 0xB8, swing)
        w32(obj + 0xAC, C.add(yaw, swing))
        frame = self.frame()
        w32(obj + 0xBC, C.add(u32(obj + 0xBC), C.mul(C.sin16(s16(frame << 10)), 0x41A00000)))
        w32(obj + 0xC0, C.add(u32(obj + 0xC0), C.mul(C.sin16(s16(frame * 800)), 0x41A00000)))
        for i, factor in enumerate((0x193, 0x166, 0x14C)):
            w32(obj + 0xCC + 4 * i, C.add(u32(obj + 0xCC + 4 * i), C.mul(C.sin16(s16(frame * factor)), 0x3C23D70A)))
        pull = [C.mul(C.sub(u32(obj + 0xD8 + 4 * i), u32(obj + 0x10 + 4 * i)), pos_k) for i in range(3)]
        for i in range(3):
            w32(obj + 0xCC + 4 * i, C.add(u32(obj + 0xCC + 4 * i), pull[i]))
        for i in range(3):
            w32(obj + 0x10 + 4 * i, C.add(u32(obj + 0x10 + 4 * i), u32(obj + 0xCC + 4 * i)))
        for i in range(3):
            v = u32(obj + 0xCC + 4 * i)
            w32(obj + 0xCC + 4 * i, C.sub(v, C.mul(v, pos_damp)))
        self.call('obj_updateGridCell', obj)
        # presentation: the model matrix and the particles (generator 0x404468)
        model = u32((G_ITEM_MODELS + self.item_resource_index(obj + 0x58) * 0x10 + 8) & M32)
        base = [u32(0x5509C0 + 4 * i) for i in range(12)]
        turned = C.mat34_set_pos_euler_scale(ONE, self.vec(obj + 0x10), s16(C.to_int(u32(obj + 0xAC))),
                                             s16(C.to_int(u32(obj + 0xB0))), s16(C.to_int(u32(obj + 0xB4))))
        matrix = C.mat34_mul(base, turned)
        points = self.call('model_getSamplePointCount', model)
        left = C.mul(C.from_int(self.s32(obj + 0xA8)), 0x3C088888)
        if C.lt(ONE, left):
            left = ONE
        count, speed = 2, ZERO
        if C.lt(left, ONE):
            count = s32(C.to_int(C.mul(C.sub(ONE, left), 0x42C80000))) + 2
            speed = C.mul(C.sub(ONE, left), 0x42480000)
            if self.s32(obj + 0xA8) == 1:
                count, speed = 3000, 0x42C80000
        for _ in range(max(count, 0)):
            index = rem(self.seed3_draw(), points)
            point, size = self.call('model_transformSamplePoint', model, tuple(matrix), index)
            scale = C.mul(C.mul(size[0], 0x3727C5AC), 0x420D6666)
            jitter = [C.mul(C.sub(C.mul(C.from_int(self.seed3_draw()), F_2M16), HALF), scale) for _i in range(3)]
            point = tuple(C.add(point[i], jitter[i]) for i in range(3))
            while True:
                b = [unit(self.seed3_draw()) for _i in range(3)]
                if not C.lt(ONE, C.add(C.add(C.mul(b[0], b[0]), C.mul(b[1], b[1])), C.mul(b[2], b[2]))):
                    break
            self.call('particle_spawn', 0x8E62C0, point, tuple(C.mul(b[i], speed) for i in range(3)), ZERO)
        w32(obj + 0xA8, u32(obj + 0xA8) - 1)
        if self.s32(obj + 0xA8) < 1:
            self.delete_self(obj)

    def seed3_draw(self):
        """One draw from the third generator 0x404468 (per machine; presentation)."""
        seed = lcg(self.u32(G_SEED3))
        self.w32(G_SEED3, seed)
        return seed >> 16


SKILL_BODIES.update({0x2EFEF8: 'hammer_can_use', 0x2EFB20: 'hammer_cast'})
SPELL_BODIES.update({0x2EFA04: 'hammer_spell_run'})
OBJECT_BODIES.update({0x2EE068: 'hammer_run'})
MODELLED.update({'SkillHammerOfWrath_canUse': 0x2EFEF8, 'SkillHammerOfWrath_cast': 0x2EFB20,
                 'HammerOfWrath_ctor': 0x2EDD78, 'HammerOfWrath_run': 0x2EE068,
                 'SpellHammerOfWrath_ctor': 0x2EF974, 'SpellHammerOfWrath_run': 0x2EFA04,
                 'item_parseDescriptor': 0x1069B8, 'item_randomizeVariant': 0x1046E0, 'item_getResourceIndex': 0x1083F8})


G_PADS = 0x41BFD8                               # 0x58 bytes per player slot: the frame's agreed input
G_FORCE_GHOST_REBASE = 0x402797                 # s8: rebuild the prediction copy (per machine)
EXTERNALS.update({
    'Player_animStep': Ext(0x1B9520, 'p', 1, 'i', '(player; speed) -> event bits'),
    'Player_move': Ext(0x1B4020, 'pipi', 0, 'i', '(player, mode, pad, external velocity or 0) -> event bits'),
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i', '(slot) -> this machine plays that slot (per machine)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 34, Shield Bash: SkillShieldBash (table 0x51ada0) and SpellShieldBash (0x28
    # bytes, table 0x51ad70).  The code of skill 49, Bash, with other numbers.
    #
    #   +0x18 the blow is done (also what slot 4, 0x2fb67c, returns)   +0x1c the clip's
    #   event was seen   +0x20 0   +0x24 the creature the player is turned toward: a PLAIN
    #   POINTER, read every frame
    # =====================================================================================
    def shieldbash_can_use(self, skill, caster):
        """SkillShieldBash_canUse 0x2faa00 -> 1 for a caster without the player flag; a
        player needs a shield (record +0x43fc not 0) and a weapon class (the signed byte
        +0x4a86) other than 4, else a HUD message for 180 frames and 0."""
        if self.u32(caster + 0xC) & 0x40:
            rec = (G_PLAYERS + self.u32(caster + 0x3C8) * REC_SIZE) & M32
            if not self.u32(rec + 0x43FC) or self.s8(rec + 0x4A86) == 4:
                self.call('hud_showMessage', self.call('text_lookup', 0x551258), 0xB4, self.u32(caster + 0x3C8), 0)
                return 0
        return 1

    def shieldbash_cast(self, skill, level, caster, pos=None, facing=0):
        """SkillShieldBash_cast 0x2faa88 -> the spell: slot 14 (level, 0), pool_new(0x28),
        the constructor."""
        level = self.skill_call(skill, 14, level, 0)
        spell = self.call('pool_new', 0x28)
        if spell:
            self.shieldbash_ctor(spell, level, caster, skill)
        return spell

    def shieldbash_ctor(self, spell, level, owner, skill):
        """SpellShieldBash_ctor 0x2face4 (spell, level, owner, skill).

        The Spell base (ONE SHARED DRAW); the owner's action state +0x58c = 6, whatever the
        owner is; the bash clip of the owner's class lump (res_find(lump, name)) is started
        (anim_startBlendInOut, flags 0x812, 0.1 s in and out) and EVENT SLOT 1 OF THE CLIP
        ITSELF - a header every object of that class shares - is set to mask 2 at 0.594 s
        (stores 0x2fadac, 0x2fadb4).  +0x18, +0x1c, +0x20, +0x24 = 0.
        world_collectObjectsInArc(owner position, facing, no filter; 100, 90 degrees, 0):
        the turn target +0x24 is the HEAD entry when it lacks object flag 0x1000000, and
        also when a later entry lacks it (the loop stores the head's object, not the one
        it found); nothing when every entry has the flag.  The pointer is stored as a
        plain word: no handle is made for it."""
        u32, w32 = self.u32, self.w32
        self.w8(spell, level)
        w32(spell + 8, skill)
        w32(spell + 4, 0)
        w32(spell + 0xC, owner)
        w32(spell + 0x10, self.draw())
        lump = u32(u32(owner + 0x24))
        w32(owner + 0x58C, 6)
        w32(spell + 0x14, 0x51AD70)
        clip = self.call('res_find', lump, 0x551298)
        self.call('anim_startBlendInOut', owner + 0x114, clip, 0x812, F_0_1, F_0_1)
        self.w8(clip + 0x20, 2)
        w32(clip + 0x1C, 0x3F181040)
        for off in (0x20, 0x1C, 0x18, 0x24):
            w32(spell + off, 0)
        found = self.call('world_collectObjectsInArc', self.vec(owner + 0x10), self.s16(owner + 0x38), 'stack', u32(spell + 0x20),
                          0x42C80000, 0x42B40000, ZERO) or ()
        if found and any(not u32(other + 0xC) & 0x1000000 for other in found):
            w32(spell + 0x24, found[0])
        self.call('handle_clear', 'stack')

    def shieldbash_windup_fx(self, spell):
        """SpellShieldBash_windupFx 0x2fb49c (spell): 203 particles on sample points of
        net_objOrGhost(owner) - the owner or, on its own machine, its prediction copy; per
        particle one OWN draw for the point (modulo the point count, which is not tested
        for 0) and an OWN ball x 13 as velocity.  The number of draws is the same on every
        machine; the points are not."""
        u32 = self.u32
        anchor = self.call('net_objOrGhost', u32(spell + 0xC))
        count = self.call('model_getSamplePointCount', u32(anchor + 0x544))
        for _ in range(0xCB):
            index = rem(self.spell_rand(spell), count)
            point, _second = self.call('model_getSamplePoint', u32(anchor + 0x544), anchor + 0x114, self.vec(anchor + 0x10),
                                       self.s16(anchor + 0x38), index, 1, 0, ONE)
            b = self.spell_ball(spell)
            self.call('particle_spawn', 0x8E6AB0, tuple(point), tuple(C.mul(b[i], 0x41500000) for i in range(3)), ZERO)

    def shieldbash_run(self, spell, pos=None, facing=0):
        """SpellShieldBash_run 0x2fae80 (spell, position, facing), once a frame.

          1. Player_animStep(owner; 1.0) -> event bits; Player_move(owner, mode 3, the pad
             record of the owner's slot, 0); with a turn target the owner's slot 26 (0, the
             target's position) - THE TARGET POINTER IS NOT TESTED AND NOT A HANDLE.  Event
             bit 2 sets +0x1c.
          2. Until the blow is done: before the event the wind-up particles.  On it: n =
             slot 10 (3), chance = slot 10 (1), frames = slot 10 (2) x 60; knock-back bit
             0x40000 below level 6, 0x80000 for 6-15, 0x200000 above; the hand (model
             attach point 1); world_collectObjectsInArc(hand, facing, no filter; 41, -1
             (any angle), 0).  In list order, until n are hit: an entry without object flag
             0x1000000 that the owner's slot 20 calls an enemy takes damage_apply(entry,
             owner, 100000, flags bit | 0x40, no descriptor, no-crit 1; low, high of slot
             8 (0, level, no randomising; 0.2)); when it then has no hit points, or ONE
             SHARED DRAW d gives chance < d % 100 + 1, it is tinted, else its slot 30
             (frames, 1) stuns it; the first one hit gets a LightEffect (ONE SHARED DRAW
             inside).  Nobody hit: world_collectInSphere(owner position, facing; 41) ADDS
             to the same list, and its first entry that is neither creature nor player nor
             flagged 0x1000000 is damaged the same way.  The blow is done either way.
          3. The owner's animation status +0x11a without bit 0x10, or owner +0x450 set: the
             owner's action state = 2 and the spell deletes itself.  Otherwise
             net_isLocalSlot(owner's slot) sets the copy-rebuild countdown 0x402797 = 60 -
             a per-machine store."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        owner = u32(spell + 0xC)
        events = self.call('Player_animStep', owner, ONE)
        self.call('Player_move', owner, 3, (G_PADS + self.s32(owner + 0x3C8) * 0x58) & M32, 0)
        target = u32(spell + 0x24)
        if target:
            self.vcall(owner, 26, 0, self.vec(target + 0x10))
        if events & 2:
            w32(spell + 0x1C, 1)
        if not u32(spell + 0x18):
            if not u32(spell + 0x1C):
                self.shieldbash_windup_fx(spell)
            else:
                most = s32(self.skill_call(u32(spell + 8), 10, 3, self.s8(spell)))
                chance = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
                frames = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell))) * 60
                level = self.s8(spell)
                knock = 0x200000 if level > 15 else 0x40000 if level < 6 else 0x80000
                hand = self.call('model_getAttachPoint', u32(owner + 0x544), self.vec(owner + 0x10), self.s16(owner + 0x38),
                                 owner + 0x114, 1, 0, ONE)
                found = list(self.call('world_collectObjectsInArc', tuple(hand), self.s16(owner + 0x38), 'stack', 0,
                                       0x42240000, 0xBF800000, ZERO) or ())
                hits = 0
                if found and most >= 1:
                    for other in found:
                        if not u32(other + 0xC) & 0x1000000 and self.vcall(owner, 20, other):
                            low, high = self.skill_call(u32(spell + 8), 8, 0, self.s8(spell), 0, F_0_2)
                            self.call('damage_apply', other, owner, 100000, 0, 0, knock | 0x40, 0, 1,
                                      C.from_int(s32(low)), C.from_int(s32(high)))
                            if C.lt(ZERO, u32(other + 0x228)) and not chance < self.draw() % 100 + 1:
                                self.vcall(other, 30, frames, 1)
                            else:
                                for off, value in ((0x92, 100), (0x96, 0x40), (0x98, 100), (0x90, 100), (0x9A, 100),
                                                   (0x9C, 0x40), (0x94, 0x40)):
                                    w16(other + off, value)
                            if not u32(spell + 0x18):
                                spot = (C.add(u32(other + 0x10), ZERO), u32(other + 0x14), C.add(u32(other + 0x18), 0x42800000))
                                self.light_effect(0xBC, spot, 0, 0, 0x43210000, 0x430A0000, 0x42800000, ZERO, ZERO, ZERO, ZERO,
                                                  ZERO, 0x43340000, 0x42700000, HALF, 0x3F01479D)
                            hits += 1
                            w32(spell + 0x18, 1)
                        if not hits < most:
                            break
                if not u32(spell + 0x18):
                    more = self.call('world_collectInSphere', self.vec(owner + 0x10), self.s16(owner + 0x38), 'stack',
                                     0x42240000) or ()
                    for other in list(more) + found:
                        if not u32(other + 0xC) & 0x1000060:
                            low, high = self.skill_call(u32(spell + 8), 8, 0, self.s8(spell), 0, F_0_2)
                            self.call('damage_apply', other, owner, 100000, 0, 0, knock | 0x40, 0, 1,
                                      C.from_int(s32(low)), C.from_int(s32(high)))
                            break
                w32(spell + 0x18, 1)
        if not self.u16(owner + 0x11A) & 0x10 or u32(owner + 0x450):
            w32(owner + 0x58C, 2)
            self.spell_delete(spell)
        elif self.call('net_isLocalSlot', u32(owner + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 0x3C)
        self.call('handle_clear', 'stack')

    def shieldbash_done(self, spell):
        """SpellShieldBash slot 4, 0x2fb67c -> +0x18 (Player_run polls it)."""
        return self.u32(spell + 0x18)


SKILL_BODIES.update({0x2FAA00: 'shieldbash_can_use', 0x2FAA88: 'shieldbash_cast'})
SPELL_BODIES.update({0x2FAE80: 'shieldbash_run', 0x2FB67C: 'shieldbash_done'})
MODELLED.update({'SkillShieldBash_canUse': 0x2FAA00, 'SkillShieldBash_cast': 0x2FAA88, 'SpellShieldBash_ctor': 0x2FACE4,
                 'SpellShieldBash_run': 0x2FAE80, 'SpellShieldBash_windupFx': 0x2FB49C, 'SpellShieldBash_isDone': 0x2FB67C})


EXTERNALS.update({
    'voice_setPosition': Ext(0x2168E8, 'iv', 1, 'n', '(voice handle, position; 1.0)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Skill 22, Dismiss Undead: SkillDismissUndead (table 0x51a7b0; can-use is the base) and
    # the projectile HolyBolt (0xc0 bytes, table 0x50e908).
    #
    #   +0x38 s16 heading   +0x4c owner handle   +0x54 expiry frame, 0 once it has hit
    #   +0x58 velocity   +0x64 the homing target: A PLAIN POINTER   +0x68 aim point
    #   +0x74..+0xac a light record (position +0xa4)   +0xb0 voice handle (never stored by
    #   the constructor)   +0xb4 trail   +0xb8 Skill   +0xbc level
    # =====================================================================================
    def dismissundead_cast(self, skill, level, caster, pos, facing):
        """SkillDismissUndead_cast 0x2f645c (skill, level, caster, position, facing) -> 0:
        pool_new(0xc0) and HolyBolt_ctor.  No flash; the caster is not tested for null."""
        obj = self.call('pool_new', 0xC0)
        if obj:
            self.holybolt_ctor(obj, pos, s16(facing), level, caster, skill)
        return 0

    def holybolt_ctor(self, obj, pos, facing, level, owner, skill):
        """HolyBolt_ctor 0x2f5248 (object, position, facing, level, owner, skill).

        Projectile_ctor (ONE SHARED DRAW); the light record at +0x74, linked; heading;
        radius 18; velocity (cos, sin) x 350; Skill, level; flags |= 0x4001; expiry = frame
        + slot 10 (2, level) x 60; the every-frame run list.

        The target, from world_collectObjectsInBox(position -/+ 360 on all axes, capacity
        32), in the order returned.  front = back = none, frontD = backD = 1e7.  An entry
        that is not the bolt, not the owner and is a creature, at 3-D distance d, is LOOKED
        AT when d < frontD OR d < backD; it qualifies when its kind byte +0xb4 is 0x10
        (undead), it is not dead (flag 8) and the owner's slot 20 calls it an enemy; then
        with dot((cos, sin of the OWNER's facing), entry - owner) > 0 it becomes `front`
        with frontD = d, else `back` with backD = d - with no test that it is nearer than
        the one it replaces.  So while one of the two bests is still 1e7 every qualifying
        undead on the other side replaces the previous one: the LAST in box order wins,
        not the nearest.  target +0x64 = front, else back, else 0 - stored as a plain
        pointer, no handle.  Without a target the aim point +0x68 is position + (cos, sin
        of the owner's facing) x 12 x 4000, 36 up; with one the aim is left for the first
        run.  Then the trail, its first point 10 ahead, and the voice (whose handle is not
        kept: +0xb0 stays what the block held)."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.projectile_ctor(obj, pos, owner, 0)
        w32(obj + 0x48, 0x50E908)
        self.w8(obj + 0x7D, 0)
        self.wvec(obj + 0xA4, pos)
        for off, value in ((0x88, 0xFC), (0x8A, 500), (0x80, 0xFC), (0x82, 500), (0x8C, 0xFFE0), (0x84, 0xFFE0),
                           (0x86, 0xAC), (0x7E, 0xAC)):
            w16(obj + off, value)
        for off, value in ((0x98, 0x42F00000), (0x90, 0x42F00000), (0x9C, 0x3891A2B3), (0x94, 0x3891A2B3), (0xA0, 0)):
            w32(obj + off, value)
        self.w8(obj + 0x7C, 0)
        self.call('light_link', obj + 0x74)
        w16(obj + 0x38, facing)
        w32(obj + 0x1C, 0x41900000)
        speed = 0x43AF0000
        self.wvec(obj + 0x58, (C.mul(C.cos16(s16(facing)), speed), C.mul(C.sin16(self.s16(obj + 0x38)), speed), ZERO))
        w32(obj + 0xB8, skill)
        w32(obj + 0xBC, level)
        w32(obj + 0xC, u32(obj + 0xC) | 0x4001)
        w32(obj + 0x54, u32(G_SIM_FRAME) + s32(self.skill_call(skill, 10, 2, level)) * 60)
        self.call('obj_runEveryFrame', obj)
        found = self.box_around(self.vec(obj + 0x10), 0x43B40000, 0x20)
        front = back = None
        front_d = back_d = 0x4B189680
        for index, other in enumerate(found):
            if other == obj or other == owner or not u32(other + 0xC) & 0x20:
                continue
            d = [C.sub(u32(other + 0x10 + 4 * i), u32(obj + 0x10 + 4 * i)) for i in range(3)]
            dist = C.sqrt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
            if C.le(front_d, dist) and C.le(back_d, dist):
                continue
            if self.s8(other + 0xB4) != 0x10 or u32(other + 0xC) & 8 or not self.vcall(owner, 20, other):
                continue
            cos, sin = C.cos16(self.s16(owner + 0x38)), C.sin16(self.s16(owner + 0x38))
            dot = C.add(C.mul(cos, C.sub(u32(other + 0x10), u32(owner + 0x10))),
                        C.mul(sin, C.sub(u32(other + 0x14), u32(owner + 0x14))))
            if C.le(dot, ZERO):
                back, back_d = index, dist
            else:
                front, front_d = index, dist
        chosen = front if front is not None else back
        w32(obj + 0x64, found[chosen] if chosen is not None else 0)
        if not u32(obj + 0x64):
            w32(obj + 0x68, C.add(u32(obj + 0x10), C.mul(C.mul(C.cos16(self.s16(owner + 0x38)), F_12), 0x457A0000)))
            far = C.mul(C.mul(C.sin16(self.s16(owner + 0x38)), F_12), 0x457A0000)
            w32(obj + 0x70, C.add(u32(obj + 0x18), 0x42100000))
            w32(obj + 0x6C, C.add(u32(obj + 0x14), far))
        w32(obj + 0xB4, self.call('trail_create', 4, 0x2EE, 4, 0x6B, 100, 0xEA, 0xAB, 0x3EA4DD2F))
        ahead = (C.mul(C.cos16(self.s16(obj + 0x38)), 0x41200000), C.mul(C.sin16(self.s16(obj + 0x38)), 0x41200000))
        self.call('trail_addPoint', u32(obj + 0xB4), (C.add(u32(obj + 0x10), ahead[0]), C.add(u32(obj + 0x14), ahead[1]),
                                                      u32(obj + 0x18)))
        self.call('sound_playOnObject', self.call('res_find', 0x550EE8, 0x550EF0), obj, ONE)

    def holybolt_run(self, obj):
        """HolyBolt_run 0x2f57b0 (object), slot 4, once a frame.

          1. with a target (THE WORD +0x64, NOT TESTED AS AN OBJECT): aim = its position, 36
             up; diff = (s16)(atan2_16(aim - position) - heading); heading += diff when
             |diff| <= 0x443, else -/+ 0x444 (minus when diff < 1); a target with flag 8
             (dead) is forgotten - the ONLY way the pointer is ever cleared.
          2. velocity = (cos, sin of the heading) x 240; dz = (s16)(int)(aim z - z):
             vertical speed 0 for -9..9, else -50 / +50.
          3. obj_moveAndCollide -> r (the hit handler runs inside).
          4. the trail point: position + a sideways unit vector x cos16(frame x 6880) x
             0.754 + (0, 0, sin16(frame x 6880) x 0.754) + (cos, sin of the heading) x 10.
          5. r == 1 (terrain and nothing else): ONE OWN DRAW a turns the heading by (a %
             0x7fff) - 0x4000; then ten times ONE OWN DRAW for a candidate heading
             (heading + (a % 0x7fff) - 0x4000) that is taken when terrain_raycast(world,
             position, 24 units that way, 0; 2.0) <= 0; a sound; 25 particles (an OWN ball x
             57.6 each).
          6. the voice follows, the light follows, and at frame >= expiry the object
             deletes itself (the hit handler sets the expiry to 0)."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        target = u32(obj + 0x64)
        if target:
            ax, ay = u32(target + 0x10), u32(target + 0x14)
            w32(obj + 0x68, ax)
            w32(obj + 0x6C, ay)
            w32(obj + 0x70, C.add(u32(target + 0x18), 0x42100000))
            heading = self.u16(obj + 0x38)
            diff = s16(C.atan2_16(C.sub(ay, u32(obj + 0x14)), C.sub(ax, u32(obj + 0x10))) - heading)
            if abs(diff) > 0x443:
                heading += -0x444 if diff < 1 else 0x444
            else:
                heading += diff
            w16(obj + 0x38, heading)
            if u32(u32(obj + 0x64) + 0xC) & 8:
                w32(obj + 0x64, 0)
        w32(obj + 0x58, C.mul(C.cos16(self.s16(obj + 0x38)), 0x43700000))
        w32(obj + 0x5C, C.mul(C.sin16(self.s16(obj + 0x38)), 0x43700000))
        dz = s16(C.to_int(C.sub(u32(obj + 0x70), u32(obj + 0x18))))
        w32(obj + 0x60, ZERO if (dz + 9) & 0xFFFF < 0x13 else 0xC2480000 if dz < 1 else 0x42480000)
        result = self.move_and_collide(obj, self.vec(obj + 0x58))
        side = [u32(obj + 0x5C), C.neg(u32(obj + 0x58)), ZERO]
        inverse = C.rsqrt(ONE, C.add(C.add(C.mul(side[0], side[0]), C.mul(side[1], side[1])), C.mul(side[2], side[2])))
        side = [C.mul(v, inverse) for v in side]
        frame = self.frame()
        wave = C.mul(C.cos16(s16(frame * 0x1AE0)), 0x3F410624)
        side = [C.mul(v, wave) for v in side]
        wave = C.mul(C.sin16(s16(frame * 0x1AE0)), 0x3F410624)
        up = [C.mul(ZERO, wave), C.mul(ZERO, wave), C.mul(ONE, wave)]
        point = [C.add(C.add(side[i], up[i]), u32(obj + 0x10 + 4 * i)) for i in range(3)]
        ahead = C.mul(C.cos16(self.s16(obj + 0x38)), 0x41200000)
        point[1] = C.add(point[1], C.mul(C.sin16(self.s16(obj + 0x38)), 0x41200000))
        point[0] = C.add(point[0], ahead)
        self.call('trail_addPoint', u32(obj + 0xB4), tuple(point))
        if s32(result) == 1:
            w16(obj + 0x38, self.u16(obj + 0x38) + rem(self.obj_rand(obj), 0x7FFF) - 0x4000)
            for _ in range(10):
                cand = s16(self.u16(obj + 0x38) + rem(self.obj_rand(obj), 0x7FFF) - 0x4000)
                spot = (C.add(u32(obj + 0x10), C.mul(C.cos16(cand), F_24)), C.add(u32(obj + 0x14), C.mul(C.sin16(cand), F_24)),
                        u32(obj + 0x18))
                way = tuple(C.sub(spot[i], u32(obj + 0x10 + 4 * i)) for i in range(3))
                if C.le(self.call('terrain_raycast', u32(G_WORLD), self.vec(obj + 0x10), way, 0, TWO), ZERO):
                    w16(obj + 0x38, cand)
            self.call('sound_playOnObject', self.call('res_find', 0x550EE8, 0x550F08), obj, ONE)
            for _ in range(0x19):
                b = self.obj_ball(obj)
                self.call('particle_spawn', 0x8E6880, self.vec(obj + 0x10), tuple(C.mul(b[i], 0x42666666) for i in range(3)), ZERO)
        self.call('voice_setPosition', u32(obj + 0xB0), self.vec(obj + 0x10), ONE)
        self.wvec(obj + 0xA4, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x74)
        if self.s32(obj + 0x54) <= self.frame():
            self.delete_self(obj)

    def holybolt_hit(self, obj, other):
        """HolyBolt_onHit 0x2f5fb4 (object, other), slot 6.

        Only a creature; with an owner only what its slot 20 calls an enemy; nothing once
        the expiry is 0.  Then: expiry = 0 (the run that called this deletes the bolt); a
        LightEffect (ONE SHARED DRAW inside); 50 particles (an OWN ball x 57.6 each); the
        sound; d = slot 10 (0 for an undead - kind byte 0x10 - else 1, level); ONE OWN DRAW
        r; damage_apply(other, owner or 0, 10000000, flags 0x200c040, no descriptor, 0; d,
        d + (int)(r/65536 x 0.2 x d)); a victim left without hit points gets a LostSoul
        (pool_new 0xb0; ONE SHARED DRAW inside)."""
        u32 = self.u32
        if not u32(other + 0xC) & 0x20:
            return
        if u32(obj + 0x4C) and not self.vcall(self.handle_obj(obj + 0x4C), 20, other):
            return
        if not u32(obj + 0x54):
            return
        self.w32(obj + 0x54, 0)
        self.light_effect(0xBC, self.vec(obj + 0x10), 0, 0, 0x432C0000, 0x437C0000, 0x43FA0000, 0xC2000000, ZERO, ZERO, ZERO,
                          ZERO, 0x43340000, 0x42F00000, ONE, ONE)
        for _ in range(0x32):
            b = self.obj_ball(obj)
            self.call('particle_spawn', 0x8E68D0, self.vec(obj + 0x10), tuple(C.mul(b[i], 0x42666666) for i in range(3)), ZERO)
        self.call('sound_playOnObject', self.call('res_find', 0x550EE8, 0x550F60), obj, ONE)
        stat = 0 if self.s8(other + 0xB4) == 0x10 else 1
        dmg = s32(self.skill_call(u32(obj + 0xB8), 10, stat, u32(obj + 0xBC)))
        extra = C.to_int(C.mul(C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), F_0_2), C.from_int(dmg)))
        self.call('damage_apply', other, self.handle_obj(obj + 0x4C), 10000000, 0, 0, 0x200C040, 0, 0,
                  C.from_int(dmg), C.from_int(s32(dmg + s32(extra))))
        if C.le(u32(other + 0x228), ZERO):
            soul = self.call('pool_new', 0xB0)
            if soul:
                self.call('LostSoul_ctor', soul, self.vec(obj + 0x10), self.vec(obj + 0x58), self.s16(obj + 0x38), 0, 0, 1)
                self.hidden_draws += 1


SKILL_BODIES.update({0x2F645C: 'dismissundead_cast'})
OBJECT_BODIES.update({0x2F57B0: 'holybolt_run', 0x2F5FB4: 'holybolt_hit'})
MODELLED.update({'SkillDismissUndead_cast': 0x2F645C, 'HolyBolt_ctor': 0x2F5248, 'HolyBolt_run': 0x2F57B0,
                 'HolyBolt_onHit': 0x2F5FB4})
