#!/usr/bin/env python3
"""ref_skills_c.py - reference model of the player and monster skills with ids 69-101 of
Champions: Return to Arms (SLUS_209.73, US v2.00).

A research tool, not game code.  docs/spec/skills-69-101.md is the written specification
(made from reading only); this module is that specification turned into code, and
tools/difftest_skills_c.py runs every method against the original machine code under
tools/ee_emu.py.  docs/spec/skills-69-101-executed.md says, per skill, what was executed,
how much of the code the test reached and where the specification turned out wrong.
Standard library only.  No game data is embedded: statistic tables, strings, particle
definitions and virtual tables are named by address and read through the memory the
caller supplies (tools/dump_tables.py --table skills prints the statistic tables of your
own executable).

How it sees the game: exactly as tools/ref_creature.py and tools/ref_arena_monsters.py do -
a memory image (load / store), callbacks for everything outside the model (EXTERNALS),
canonical arguments (integers as unsigned 32-bit, floats as raw 32-bit patterns, a vector
as a tuple of three patterns).  Floats go through tools/ref_core.py's R5900 arithmetic.

Contents (the address of the code each part mirrors is in its docstring)
    1  plumbing: virtual calls on skills, spells and creatures
    2  handle lists on the memory image (handle_link, handle_clear, handle_removeNode)
    3  the Skill object: statistics by tier and level (slots 8, 10-15), the default
       can-use / cast / mana-cost, the per-skill mana-cost functions
    4  the Spell base, Spell_rand, the unit-ball rejection loop, Creature_getVisualPos
    5  the skills, one section each
Tagar's Insects (87) is modelled and matched in tools/ref_arena_monsters.py; Model below
inherits those methods (tagar_cast, tagar_spell_run, ...) unchanged.

What other models own (call-outs here): damage_apply and what it does to the victim
(tools/ref_combat.py), the world queries and object construction (tools/ref_world.py,
tools/ref_objects.py), animation (tools/ref_anim.py), the inventory (tools/ref_items.py),
Player_castSkill / Player_updateCast, which reach these functions (tools/ref_player.py).

Draws: Model.draws counts draws from the shared seed 0x404464; a spell's own generator is
the word at spell +0x10, an object's own generator the word at object +0x44.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
from ref_creature import Ext, M32, M64, s8, s16, s32, s64      # noqa: E402,F401

# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
G_RAND_SEED = RC.G_RAND_SEED                    # 0x404464 shared seed (in the sync hash)
G_SIM_FRAME = RC.G_SIM_FRAME                    # 0x44fdcc
G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_PLAYERS, REC_SIZE = RC.G_PLAYERS, RC.REC_SIZE
G_NETWORK_MODE = RC.G_NETWORK_MODE              # s8
G_SKILL_TABLE = 0x41B170                        # Skill* [102], index = skill id
G_HANDLE_FREE = 0x864EA8                        # head of the free list of handle nodes
G_HANDLE_NODES, HANDLE_NODE_SIZE, HANDLE_NODE_COUNT = 0x847268, 20, 6096
G_PVP_MODE_A = 0x4F711C                         # s32 (docs/player.md)
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8424, 0x4F8430
G_FORCE_GHOST_REBASE = 0x402797                 # u8 (machine)

VT_SPELL = AM.VT_SPELL                          # 0x515ba0 the Spell base table
VT_SKILL = 0x512670                             # the Skill base table

SKILL_IDS = tuple(range(69, 102))

# float patterns
ZERO, HALF, ONE, TWO = C.ZERO, C.HALF, C.ONE, C.TWO
MINUS_ONE = C.MINUS_ONE
F_2M16 = RC.F_2M16                              # 1 / 65536
DT = RC.DT                                      # 0x3c888888, 1 / 60 truncated
F_0_01 = 0x3C23D70A                             # 0.01
F_0_2 = 0x3E4CCCCC                              # 0.19999999: the "20 %" spread
F_12, F_36, F_60 = 0x41400000, 0x42100000, 0x42700000

# Skill base bodies (never overridden): slot -> address
SKILL_BASE = {1: 0x3C8218, 2: 0x3C8220, 5: 0x3C82A8, 8: 0x3C82E4, 10: 0x3C85FC, 11: 0x3C8690,
              12: 0x3C87F0, 13: 0x3C8864, 14: 0x3C88DC, 15: 0x3C88E4}

# function -> (slot, method) for the bodies this module has.  The per-skill sections add
# to these three tables and to MODELLED as they define their methods.
SKILL_BODIES = {
    0x3C8218: (1, 'skill_can_use_default'), 0x3C8220: (2, 'skill_cast_default'),
    0x3C82A8: (5, 'skill_mana_default'), 0x3C82E4: (8, 'skill_stat_range'),
    0x3C85FC: (10, 'skill_get_stat'), 0x3C8690: (11, 'skill_get_stat_tier2'),
    0x3C87F0: (12, 'skill_stat_for'), 0x3C8864: (13, 'skill_stat_for_handle'),
    0x3C88DC: (14, 'skill_adjust_level'), 0x3C88E4: (15, 'skill_mana_from_stat4'),
}
SPELL_BODIES = {}
MODELLED = {
    'Skill_canUse_default': 0x3C8218, 'Skill_cast_default': 0x3C8220, 'Skill_manaCost_default': 0x3C82A8,
    'Skill_getStatRange': 0x3C82E4, 'Skill_getStat': 0x3C85FC, 'Skill_getStatTier2': 0x3C8690,
    'Skill_getStatFor': 0x3C87F0, 'Skill_getStatForHandle': 0x3C8864, 'Skill_adjustLevel': 0x3C88DC,
    'Skill_manaFromStat4': 0x3C88E4,
    'Spell_rand': 0x16A964, 'GameObject_rand': 0x1509D0, 'Creature_getVisualPos': 0x118738,
    'handle_link': 0x1A1738, 'handle_clear': 0x1A1698, 'handle_removeNode': 0x1A1868,
}

# type-info getters of the spell classes whose presence a can-use function tests
# (creature_findSpellByType 0x11a710 compares the result with each attached spell's)
TYPEINFO = {'Roar': 0x3D07B8, 'BattleCry': 0x3D08DC, 'BloodLust': 0x3D0A00, 'RaiseArmy': 0x3D16F0,
            'Retribution': 0x3D18A0, 'SpiritShield': 0x3D19F0, 'FrostArmor': 0x3D1D70,
            'DiseaseBlade': 0x3D1E94}

DESC_HEADER = '00' * 16 + 'ffff'                # bytes +0x10..+0x21 of an all-empty item record

EXTERNALS = dict(AM.EXTERNALS)
EXTERNALS.update({
    # --- the damage function: the element record is passed as ('desc', header, slot0..slot3)
    'damage_apply': Ext(0x1E8230, 'ppiiiidi', 2, 'i', '(target, attacker, attack rating, 0, 0, flags, '
                        'descriptor or 0, no-critical; min, max)'),
    # --- spells on creatures
    'typeinfo': Ext(0, 'i', 0, 'i', '(getter address) -> the class token creature_findSpellByType is given'),
    'creature_findSpellByType': Ext(0x11A710, 'pp', 0, 'i', '(creature, class token) -> spell or 0'),
    'Spell.v1': Ext(0, 'pi', 0, 'n', 'destroy (3)'),
    # --- effects that only present
    'light_link': Ext(0x148AF8, 'p', 0, 'n', '(light record)'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n', '(light record)'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n'),
    'light_dtor': Ext(0x14A490, 'pi', 0, 'n'),
    'particleGroup_create': Ext(0x18E880, '', 0, 'i', '() -> handle'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n', '(handle)'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n', '(handle)'),
    'particleGroup_free': Ext(0x18EA90, 'i', 0, 'n', '(handle)'),
    'particleGroup_setMatrix': Ext(0x18E9E8, 'ip', 0, 'n', '(handle, matrix)'),
    'fx_emitFromModelVerts': Ext(0x1EB1E8, 'pipii', 1, 'n', '(object, count, particle definition, 0, 0; speed)'),
    'sound_stop': Ext(0x213EA0, 'i', 0, 'n', '(sound handle)'),
    'camera_shake': Ext(0x1EBAE0, '', 1, 'n', '(; strength)'),
    # --- creature virtual slots
    'Creature.v21': Ext(0, 'pp', 0, 'i', 'is ally (other)'),
    'Creature.v22': Ext(0, 'pp', 0, 'i', 'same team (other)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row: the integer or float
    result, then every output the callee fills.  (ref_arena_monsters.shape_result with the
    kind 'd' - a damage descriptor - counted as an argument.)"""
    ext = EXTERNALS[name]
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwWbnL':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0)
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvelsSOWd':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def c_div(a, b):
    """C's signed integer division (toward zero)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def c_rem(a, b):
    """C's signed remainder (the sign of the dividend)."""
    return a - b * c_div(a, b)


def desc(*slots):
    """The canonical form of a damage descriptor built on the stack: an all-empty item
    record whose effect slots are `slots` (each (type, v1, v2, v3)), the rest empty."""
    filled = tuple(tuple(v & 0xFFFF for v in slot) for slot in slots)
    return ('desc', DESC_HEADER) + filled + ((0xFFFF,),) * (4 - len(filled))


class Model(AM.Model):
    """Skills 69-101 on a memory image.  See the module docstring."""

    # =====================================================================================
    # 1. Plumbing
    # =====================================================================================
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def skill_call(self, skill, slot, *args):
        """A virtual call on a Skill object (table pointer at +0x60; 16-bit `this`
        adjustment at +8*slot, function at +8*slot+4).  A body this module has runs here;
        anything else is the callback 'Skill.v<slot>'."""
        table = self.u32(skill + 0x60)
        this = (skill + self.s16(table + 8 * slot)) & M32
        body = SKILL_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is None:
            body = AM.SKILL_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Skill.v%d' % slot) not in self.external:
            return getattr(self, body[1])(this, *args)
        return self.call('Skill.v%d' % slot, this, *args)

    def table_call(self, cls, obj, table_offset, slot, *args):
        """A virtual call on a spell (table at +0x14) or a weapon holder (table at +0): a
        spell body this module has runs here, anything else is a callback."""
        if cls == 'Spell':
            table = self.u32(obj + table_offset)
            body = SPELL_BODIES.get(self.u32(table + 8 * slot + 4))
            if body is not None and ('Spell.v%d' % slot) not in self.external:
                return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return AM.Model.table_call(self, cls, obj, table_offset, slot, *args)

    def spell_destroy(self, spell):
        """What a spell does to end itself: its own slot 1 with argument 3 (destroy and
        free).  The destructors are outside this model."""
        self.table_call('Spell', spell, 0x14, 1, 3)

    def find_spell_by_type(self, creature, getter):
        """creature_findSpellByType 0x11a710 with the type-info getter the caller names: the
        first spell attached to the creature whose class is exactly that one, or 0."""
        token = self.call('typeinfo', getter)
        return self.call('creature_findSpellByType', creature, token)

    def is_player(self, obj):
        return bool(obj and self.u32(obj + 0xC) & 0x40)

    def record(self, obj):
        """The player record of the slot at object +0x3c8.  The original indexes it with
        whatever that word holds; see each caller for whether it tests the is-player flag."""
        return (G_PLAYERS + s32(self.u32(obj + 0x3C8)) * REC_SIZE) & M32

    def flash(self, obj, quad, a, b, c, d):
        """One colour quad of a creature: quad 1 at +0x90, quad 2 at +0x98."""
        base = obj + (0x90 if quad == 1 else 0x98)
        for k, v in enumerate((a, b, c, d)):
            self.w16(base + 2 * k, v)

    def sound_at(self, lump, name, pos):
        self.call('sound_playAtPos', self.call('res_find', lump, name), tuple(pos), ONE)

    # =====================================================================================
    # 2. Handle lists (docs/objects.md; tools/ref_core.py HandlePool is the same logic on
    #    Python objects).  A node is 20 bytes: +0 next, +4 prev (a node or the list head:
    #    both start with the 'next' pointer), +8 partner, +0xc object, +0x10 a 16-bit tag.
    #    A list head on the caller's stack is passed as 'stack' and stays a callback, since
    #    the model has no stack.
    # =====================================================================================
    def _h_take(self):
        node = self.u32(G_HANDLE_FREE)
        if node:
            self.w32(G_HANDLE_FREE, self.u32(node))
            self.w16(node + 0x10, 0)
        return node

    def handle_link(self, head, back, obj):
        """handle_link 0x1a1738 (head, back, object) -> the node: node A at the front of
        the list `head` carrying the object, node B at the front of `back` (a list of the
        object itself) carrying nothing; each is the other's partner."""
        if head == 'stack':
            return self.call('handle_link', head, back, obj)
        u32, w32 = self.u32, self.w32
        a = self._h_take()
        b = self._h_take()
        w32(a, u32(head))
        if u32(head):
            w32(u32(head) + 4, a)
        w32(a + 4, head)
        w32(head, a)
        w32(b, u32(back))
        if u32(back):
            w32(u32(back) + 4, b)
        w32(b + 4, back)
        w32(back, b)
        w32(a + 0xC, obj)
        w32(a + 8, b)
        w32(b + 0xC, 0)
        w32(b + 8, a)
        return a

    def _h_unlink_free(self, node):
        u32, w32 = self.u32, self.w32
        if u32(node + 4):
            w32(u32(node + 4), u32(node))
        if u32(node):
            w32(u32(node) + 4, u32(node + 4))
        partner = u32(node + 8)
        if partner:
            if u32(partner + 4):
                w32(u32(partner + 4), u32(partner))
            if u32(partner):
                w32(u32(partner) + 4, u32(partner + 4))
            w32(partner, u32(G_HANDLE_FREE))
            w32(G_HANDLE_FREE, partner)
        w32(node, u32(G_HANDLE_FREE))
        w32(G_HANDLE_FREE, node)

    def handle_remove(self, node):
        """handle_removeNode 0x1a1868 (node) -> its object.  The node and its partner leave
        their lists; the partner goes back to the free list first."""
        obj = self.u32(node + 0xC)
        self._h_unlink_free(node)
        return obj

    def handle_clear(self, head):
        """handle_clear 0x1a1698 (head): every node of the list, front to back, with its
        partner."""
        if head == 'stack':
            return self.call('handle_clear', head)
        node = self.u32(head)
        while node:
            following = self.u32(node)
            self._h_unlink_free(node)
            node = following

    def handle_items(self, head):
        """(node, object) of every node of a list, front to back."""
        out, node = [], self.u32(head)
        while node:
            out.append((node, self.u32(node + 0xC)))
            node = self.u32(node)
        return out

    # =====================================================================================
    # 3. The Skill object (0x68 bytes, docs/skills.md).  Tier 1: first level s16[5] +0x0e,
    #    base s16[5] +0x18, step float[5] +0x24.  Tier 2: +0x38, +0x42, +0x4c; a negative
    #    first level means "no tier 2 for this statistic".
    # =====================================================================================
    @staticmethod
    def _round(value):
        """trunc(x + 0.5) for x >= 0, trunc(x - 0.5) below: written out at every site."""
        if C.le(ZERO, value):
            return C.to_int(C.add(value, HALF))
        return C.to_int(C.sub(value, HALF))

    def _tier_value(self, skill, first_at, base_at, step_at, stat, level):
        first = self.s16(skill + first_at + 2 * stat)
        if level < first:
            return 0
        step = C.mul(self.u32(skill + step_at + 4 * stat), C.from_int(level - first))
        return self._round(C.add(C.from_int(self.s16(skill + base_at + 2 * stat)), step)) & M32

    def skill_get_stat(self, skill, stat, level, *_):
        """Skill slot 10, 0x3c85fc (skill, statistic, level) -> integer: tier 1.  0 at level
        0 and below the statistic's first level; else round(base + step x (level - first))
        in single precision."""
        stat, level = s32(stat), s32(level)
        if level == 0:
            return 0
        return self._tier_value(skill, 0x0E, 0x18, 0x24, stat, level)

    def skill_get_stat_tier2(self, skill, stat, level, cap):
        """Skill slot 11, 0x3c8690 (skill, statistic, level, cap) -> integer.  0 at level 0;
        with cap > 0 the level is min(level, cap); tier 2 when the statistic has one (first
        level not negative), else tier 1 - both with the clamped level."""
        stat, level, cap = s32(stat), s32(level), s32(cap)
        if level == 0:
            return 0
        if cap > 0 and cap < level:
            level = cap
        if self.s16(skill + 0x38 + 2 * stat) < 0:
            return self._tier_value(skill, 0x0E, 0x18, 0x24, stat, level)
        return self._tier_value(skill, 0x38, 0x42, 0x4C, stat, level)

    def skill_stat_for(self, skill, stat, level, caster, cap):
        """Skill slot 12, 0x3c87f0 (skill, statistic, level, caster, cap): slot 10 when the
        caster exists and has the is-player flag, else slot 11 (also for a null caster)."""
        if caster and self.u32(caster + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_stat_for_handle(self, skill, stat, level, handle, cap):
        """Skill slot 13, 0x3c8864: slot 12 with the caster given as the address of a handle
        word (an empty handle counts as "not a player")."""
        node = self.u32(handle)
        if node and self.u32(self.u32(node + 0xC) + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_adjust_level(self, skill, level, n=0):
        """Skill slot 14, 0x3c88dc: the level, unchanged (the second argument is dead)."""
        return level & M32

    def skill_mana_from_stat4(self, skill, level, n=0):
        """Skill slot 15, 0x3c88e4 (skill, level, n) -> float: slot 10 (4, slot 14 (level,
        n))."""
        level = self.skill_call(skill, 14, level, n)
        return C.from_int(s32(self.skill_call(skill, 10, 4, level)))

    def skill_stat_range(self, skill, stat, level, randomise, spread):
        """Skill slot 8, 0x3c82e4 (skill, statistic, level, randomise, low out, high out;
        spread) -> (low, high).  v = slot 10 (always tier 1); low = round(v - v x spread),
        high = round(v + v x spread), each at least 1.

        With `randomise` each bound makes TWO SHARED DRAWS: the first decides only which
        way the second is rounded; the bound is v -/+ v x (second draw / 65536) x spread.
        No caller in ids 69-101 sets it."""
        value = C.from_int(s32(self.skill_call(skill, 10, stat, level)))
        out = []
        for combine in (C.sub, C.add):
            if randomise:
                probe = combine(value, C.mul(C.mul(value, C.mul(C.from_int(self.draw()), F_2M16)), spread))
                second = combine(value, C.mul(C.mul(value, C.mul(C.from_int(self.draw()), F_2M16)), spread))
                if C.le(ZERO, probe):
                    bound = C.to_int(C.add(second, HALF))
                else:
                    bound = C.to_int(C.sub(second, HALF))
            else:
                bound = self._round(combine(value, C.mul(value, spread)))
            out.append(bound if bound > 0 else 1)
        return out[0], out[1]

    def skill_can_use_default(self, skill, caster=0):
        """Skill slot 1 default, 0x3c8218: always 1."""
        return 1

    def skill_cast_default(self, skill, level=0, caster=0, pos=None, facing=0):
        """Skill slot 2 default, 0x3c8220: returns 0 (the passives)."""
        return 0

    def skill_mana_default(self, skill, level=0):
        """Skill slot 5 default, 0x3c82a8 -> 1.0 (the passives; nothing asks)."""
        return ONE

    def skill_mana_cost(self, skill, level):
        """The mana-cost function of every castable skill of this range (slot 5; 0x314454
        for Retribution and the same four instructions elsewhere): slot 15 (level, 0x14),
        i.e. (float) statistic 4 of tier 1."""
        return self.skill_call(skill, 15, level, 0x14)

    def statistic_spread(self, skill, stat, level, owner):
        """The damage range most skills of this range ask for (e.g. 0x3176b8): a player
        owner gets slot 8 (rounded, at least 1, tier 1); anyone else, a null owner
        included, gets v = slot 12 (stat, level, owner, cap 0) and the TRUNCATED
        v - v x 0.19999999, v + v x 0.19999999 with no floor."""
        if owner and self.u32(owner + 0xC) & 0x40:
            return self.skill_call(skill, 8, stat, level, 0, F_0_2)
        value = C.from_int(s32(self.skill_call(skill, 12, stat, level, owner, 0)))
        high = C.to_int(C.add(value, C.mul(value, F_0_2)))
        low = C.to_int(C.sub(value, C.mul(value, F_0_2)))
        return low, high

    # =====================================================================================
    # 4. The Spell base (0x18 bytes: +0 level byte, +4 back list, +8 skill, +0xc owner,
    #    +0x10 own generator, +0x14 table), its generator and two small helpers
    # =====================================================================================
    def spell_base(self, spell, level, owner, skill, table):
        """The Spell base constructor, inlined in every spell constructor: ONE SHARED DRAW
        seeds the spell's own generator."""
        self.w8(spell, level)
        self.w32(spell + 8, skill)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 4, 0)
        self.w32(spell + 0x10, self.draw())
        self.w32(spell + 0x14, table)

    def spell_unit(self, spell):
        """(draw / 65536) x 2 - 1 from the spell's own generator."""
        return C.sub(C.mul(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), TWO), ONE)

    def spell_ball(self, spell):
        """A point of the unit ball from the spell's own generator: three draws per try,
        repeated while 1.0 < x*x + y*y + z*z in single precision."""
        while True:
            x = self.spell_unit(spell)
            y = self.spell_unit(spell)
            z = self.spell_unit(spell)
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def obj_unit(self, obj):
        return C.sub(C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), TWO), ONE)

    def obj_ball(self, obj):
        """The same rejection loop on an object's own generator (+0x44)."""
        while True:
            x = self.obj_unit(obj)
            y = self.obj_unit(obj)
            z = self.obj_unit(obj)
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def visual_pos(self, c):
        """Creature_getVisualPos 0x118738 (out, creature) -> (x, y, z): the position moved
        along the facing by the float at +0xe0 when that is not 0, with the height +0x3c."""
        x, y = self.u32(c + 0x10), self.u32(c + 0x14)
        if not C.eq(self.u32(c + 0xE0), ZERO):
            x = C.add(x, C.mul(C.cos16(self.s16(c + 0x38)), self.u32(c + 0xE0)))
            y = C.add(y, C.mul(C.sin16(self.s16(c + 0x38)), self.u32(c + 0xE0)))
        return (x, y, self.u32(c + 0x3C))
