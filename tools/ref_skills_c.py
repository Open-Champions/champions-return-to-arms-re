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
    5  the skills, one mixin class each, in the order they were matched:
         Retribution 69, SpiritShield 94, FrostArmor 96, WaveOfFlame 95, UnspokenWord 70,
         Storms 100 + 80, ConeOfShock 101, Drowsy 88, PoisonBolt 89, Roar 76, BattleCry 77,
         Passives 71 73 74 79 92 93, DiseaseBlade 97, SummonBadger 90, RaiseArmy 91,
         BloodLust 78, SummonItems 72 + 75, ThrownAxes 98 + 99, SharedClasses 82 83 86,
         CriticalHit 81, Root 85
       For each: can-use and cost, the cast (objects created with their fields, every
       shared-seed and own-generator draw in order), the spell's or object's per-tick run
       to its end - particle draws and their rejection loops included, since they share a
       generator with gameplay rolls in 70, 77, 88, 101 and decide the number of shared
       draws in 80 and 100 - and the hit handlers.
Tagar's Insects (87) is modelled and matched in tools/ref_arena_monsters.py; Model below
inherits those methods (tagar_cast, tagar_spell_run, ...) unchanged.  Cyclone (84) is the
one class of the range with no methods here: its code is the class of id 41, which
tools/ref_skills_b.py models; this module has only its statistics (section 3).

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
SPELL_TABLES = set()                            # virtual tables of the spell classes modelled here
OBJECT_TABLES = set()                           # virtual tables of the GameObject classes modelled here
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
    'camera_shake': Ext(0x1EBAE0, 'i', 1, 'n', '(0; strength)'),
    'Player_animStep': Ext(0x1B9520, 'p', 1, 'i', '(player; speed) -> event bits of this step'),
    # --- creature virtual slots
    'Creature.v1': Ext(0, 'pi', 0, 'n', 'destroy (3): slot 1 of any GameObject'),
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
        if kind in 'ipvelsSOWdTI':
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


class Base(AM.Model):
    """The machinery every skill of the range shares, on a memory image."""

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

    def light_effect(self, block, pos, follow, colour, stack, flag=0, colour_2=(0, 0, 0, 0)):
        """LightEffect_ctor 0x201bd8 (block, position, object to follow or 0, flag; four colour
        floats, four more floats; four floats on the stack: radius, a second number, a third
        and the life in seconds).  A GameObject: its constructor makes one shared draw,
        inside the callee."""
        self.call('LightEffect_ctor', block, tuple(pos), follow, flag, *(tuple(colour) + tuple(colour_2) + tuple(stack)))

    def light_record(self, light, colour, radius, falloff, extra, pos):
        """An embedded light record as the constructors of this range fill it: two copies
        of four colour shorts (+0xa, +0x12), radius (+0x1c, +0x24), 1 / radius squared
        (+0x20, +0x28), a float at +0x2c, the position at +0x30, two zero bytes at +8, +9."""
        self.w8(light + 9, 0)
        self.wvec(light + 0x30, pos)
        for k, value in enumerate(colour):
            self.w16(light + 0x12 + 2 * k, value)
            self.w16(light + 0xA + 2 * k, value)
        for off, value in ((0x1C, radius), (0x24, radius), (0x28, falloff), (0x20, falloff), (0x2C, extra)):
            self.w32(light + off, value)
        self.w8(light + 8, 0)

    def model_sample(self, owner, model, at, index):
        """model_getSamplePoint 0x178e18 on the owner's model: (model, animation state
        +0x114, position, facing, index, out, 0, 0; the scale at +0xdc) -> the point."""
        return tuple(self.call('model_getSamplePoint', model, owner + 0x114, tuple(at), self.s16(owner + 0x38),
                               index, 0, 0, self.u32(owner + 0xDC)))

    def callee_store(self, addr, size, value):
        """A store the CALLEE makes through a pointer the model handed it (an output that
        lies in an object, not on the stack): not one of the model's own writes."""
        poke = getattr(self.mem, 'poke', None)
        if poke is not None:
            poke(addr, size, value & ((1 << (8 * size)) - 1))
        else:
            self.mem.store(addr, size, value)

    def attach_point(self, owner, index, model=None):
        """model_getAttachPoint 0x1754a0 on a player's body model (+0x544): (model, position,
        facing, animation state +0x114, index, out, 0; 1.0) -> the point."""
        model = self.u32(owner + 0x544) if model is None else model
        return tuple(self.call('model_getAttachPoint', model, self.vec(owner + 0x10), self.s16(owner + 0x38),
                               owner + 0x114, index, 0, ONE))

    def sound_at(self, lump, name, pos):
        return self.call('sound_playAtPos', self.call('res_find', lump, name), tuple(pos), ONE)

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


# =======================================================================================
# 5. The skills.  Each section is a mixin class with the skill's functions and, below it,
#    the rows that tie the original addresses to the methods.
# =======================================================================================

class Retribution:
    """69 - Retribution (`retribution`, cleric): a timed spell on the caster; while it is
    there damage_apply turns a share of every hit the caster deals into hit points."""
    RET_VT = 0x51BF70
    RET_LUMP, RET_SOUND, RET_PARTICLE = 0x552BB8, 0x552BC0, 0x8E85F8

    def retribution_can_use(self, skill, caster):
        """SkillRetribution_canUse 0x3142bc: 1 unless the caster carries a SpellRetribution."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['Retribution']) else 1

    def retribution_cast(self, skill, level, caster, pos, facing):
        """SkillRetribution_cast 0x3142f0 -> the spell, or 0 without a pool block.  Level
        through slot 14 (level, 0x14); pool_new(0x5c); the constructor."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x5C)
        if spell:
            self.retribution_spell_ctor(spell, level, caster, skill)
        return spell

    def retribution_spell_ctor(self, spell, level, caster, skill):
        """SpellRetribution_ctor 0x314488 (spell, level, caster, skill).  The Spell base (ONE
        SHARED DRAW); an embedded light record at +0x18 placed 20 above the caster and
        linked; a sound at the caster; a particle group handle at +0x54.  The clock at
        +0x58 is not written: it is 0 because the pool zero-fills."""
        w16, w32 = self.w16, self.w32
        self.spell_base(spell, level, caster, skill, self.RET_VT)
        light = spell + 0x18
        place = (C.add(self.u32(caster + 0x10), ZERO), self.u32(caster + 0x14),
                 C.add(self.u32(caster + 0x18), 0x41A00000))
        self.w8(light + 9, 0)
        self.wvec(light + 0x30, place)
        for off, value in ((0x24, F_12), (0x28, 0x3BE38E38), (0x2C, ZERO), (0x1C, F_12), (0x20, 0x3BE38E38)):
            w32(light + off, value)
        for off, value in ((0x12, 0x5F), (0x14, 0x77), (0xA, 0x5F), (0xC, 0x77), (0xE, 0x62), (0x10, 0), (0x16, 0x62),
                           (0x18, 0)):
            w16(light + off, value)
        self.w8(light + 8, 0)
        self.call('light_link', light)
        self.sound_at(self.RET_LUMP, self.RET_SOUND, self.vec(self.u32(spell + 0xC) + 0x10))
        w32(spell + 0x54, self.call('particleGroup_create'))

    def retribution_spell_run(self, spell, pos, facing=0):
        """SpellRetribution_run 0x314618 (spell, position, facing), once per frame of the
        owner: 49 particles from the owner's model vertices (cosmetic generator, inside the
        callee); the light flickers with sin16(frame x 0xb5e) and moves to `pos`; clock
        +0x58 += 1/60; when (float) slot 10 (0, level) < clock the spell destroys itself."""
        u32, w32 = self.u32, self.w32
        light = spell + 0x18
        self.call('particleGroup_begin', u32(spell + 0x54))
        self.call('fx_emitFromModelVerts', u32(spell + 0xC), 0x31, self.RET_PARTICLE, 0, 0, 0x41100000)
        self.call('particleGroup_end', u32(spell + 0x54))
        phase = c_rem(s32(u32(G_SIM_FRAME) * 0xB5E), 0x10000)
        radius = C.add(C.mul(C.sin16(phase), 0x41000000), 0x42960000)
        w32(light + 0x1C, radius)
        w32(light + 0x24, radius)
        falloff = C.div(ONE, C.mul(radius, radius))
        w32(light + 0x28, falloff)
        w32(light + 0x20, falloff)
        self.wvec(light + 0x30, pos)
        self.call('light_relink', light)
        clock = C.add(u32(spell + 0x58), DT)
        w32(spell + 0x58, clock)
        seconds = self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))
        if C.lt(C.from_int(s32(seconds)), clock):
            self.spell_destroy(spell)

    def retribution_heal_owner(self, spell, dmg):
        """SpellRetribution_healOwner 0x314790 (spell; damage dealt) -> the fraction
        statistic 1 / 100, or 0.0 for a player owner without hit points.  The owner flashes
        (+0x98 is left alone); a player owner whose record has hit points above 0 gains
        damage x fraction, up to the record's maximum.  NO draw."""
        u32, w16 = self.u32, self.w16
        owner = u32(spell + 0xC)
        for off, value in ((0x96, 0x3F), (0x90, 0x46), (0x92, 0x80), (0x94, 0x4B), (0x9A, 0x80), (0x9C, 0x4B),
                           (0x9E, 0x3F)):
            w16(owner + off, value)
        fraction = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))), F_0_01)
        owner = u32(spell + 0xC)
        if u32(owner + 0xC) & 0x40:
            rec = self.record(owner)
            hp = u32(rec + 0xAC)
            if not C.lt(ZERO, hp):
                return ZERO
            hp = C.add(hp, C.mul(dmg, fraction))
            self.w32(rec + 0xAC, hp)
            if C.lt(u32(rec + 0xB0), hp):
                self.w32(rec + 0xAC, u32(rec + 0xB0))
        return fraction


SKILL_BODIES.update({0x3142BC: (1, 'retribution_can_use'), 0x3142F0: (2, 'retribution_cast'),
                     0x314454: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x314618: (2, 'retribution_spell_run')})
SPELL_TABLES.add(Retribution.RET_VT)
MODELLED.update({'SkillRetribution_canUse': 0x3142BC, 'SkillRetribution_cast': 0x3142F0,
                 'SkillRetribution_manaCost': 0x314454, 'SpellRetribution_ctor': 0x314488,
                 'SpellRetribution_run': 0x314618, 'SpellRetribution_healOwner': 0x314790})


class SpiritShield:
    """94 - Spirit Shield (`spiritshield`, shaman; FemaleDarkElf and Marr cast it on
    themselves): a timed spell on the caster with a chance to absorb each hit."""
    SS_VT = 0x51C1C0
    SS_LUMP, SS_SOUND, SS_HIT_SOUND, SS_PARTICLE = 0x552D78, 0x552D80, 0x552DA0, 0x8E8648

    def spiritshield_can_use(self, skill, caster):
        """SkillSpiritShield_canUse 0x314e1c: 1 unless the caster carries a SpellSpiritShield."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['SpiritShield']) else 1

    def spiritshield_cast(self, skill, level, caster, pos, facing):
        """SkillSpiritShield_cast 0x314e50: level through slot 14 (level, 2); pool_new(0x24);
        the constructor.  Returns the spell or 0."""
        level = self.skill_call(skill, 14, level, 2)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.spiritshield_spell_ctor(spell, level, caster, skill)
        return spell

    def spiritshield_spell_ctor(self, spell, level, caster, skill):
        """SpellSpiritShield_ctor 0x31500c.  The Spell base (ONE SHARED DRAW); phase +0x18 =
        0, clock +0x1c = 0; a LightEffect (pool_new(0xbc); skipped without a block) 36
        above the caster's visual position, following the caster; a sound at the caster."""
        self.spell_base(spell, level, caster, skill, self.SS_VT)
        self.w32(spell + 0x1C, 0)
        self.w32(spell + 0x18, 0)
        block = self.call('pool_new', 0xBC)
        if block:
            owner = self.u32(spell + 0xC)
            x, y, z = self.visual_pos(owner)
            self.light_effect(block, (C.add(x, ZERO), y, C.add(z, F_36)), self.u32(spell + 0xC),
                              (0x42A20000, 0x424C0000, 0x42B40000, 0x42E40000), (0x42F00000, 0x43340000, ZERO, ONE))
        self.sound_at(self.SS_LUMP, self.SS_SOUND, self.vec(self.u32(spell + 0xC) + 0x10))

    def spiritshield_spell_run(self, spell, pos=None, facing=0):
        """SpellSpiritShield_run 0x3151b4, once per frame of the owner.  Owner flash quad 1
        = (27, 17, 30, 38); clock +0x1c += 1/60; then by phase +0x18:
          0  (float) slot 12 (0, level, owner, cap 10) < clock: the spell destroys itself
          1  dissolve particles with progress 1 - (end - clock) x 5.2083607 (at most 1);
             end +0x20 <= clock: phase 2, end = clock + 0.064
          2  end <= clock: phase 3, end = clock + 0.493
          3  re-form particles with progress 1 - (end - clock) x 2.0284097; end <= clock:
             phase 0.
        Phases 1-3 do not test the duration."""
        u32, w32 = self.u32, self.w32
        owner = u32(spell + 0xC)
        clock = C.add(u32(spell + 0x1C), DT)
        phase = u32(spell + 0x18)
        self.flash(owner, 1, 0x1B, 0x11, 0x1E, 0x26)
        w32(spell + 0x1C, clock)
        if phase == 0:
            seconds = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), owner, 10)
            if C.lt(C.from_int(s32(seconds)), u32(spell + 0x1C)):
                self.spell_destroy(spell)
        elif phase == 1:
            progress = C.sub(ONE, C.mul(C.sub(u32(spell + 0x20), clock), 0x40A6AAE4))
            self._spiritshield_particles(spell, ONE if C.lt(ONE, progress) else progress, True)
            if C.le(u32(spell + 0x20), u32(spell + 0x1C)):
                w32(spell + 0x18, 2)
                w32(spell + 0x20, C.add(u32(spell + 0x1C), 0x3D83126E))
        elif phase == 2:
            if C.le(u32(spell + 0x20), clock):
                w32(spell + 0x18, 3)
                w32(spell + 0x20, C.add(clock, 0x3EFC6A1A))
        elif phase == 3:
            progress = C.sub(ONE, C.mul(C.sub(u32(spell + 0x20), clock), 0x4001D177))
            self._spiritshield_particles(spell, ONE if C.lt(ONE, progress) else progress, False)
            if C.le(u32(spell + 0x20), u32(spell + 0x1C)):
                w32(spell + 0x18, 0)

    def _spiritshield_particles(self, spell, progress, dissolve):
        """SpellSpiritShield_dissolveParticles 0x31539c / _reformParticles 0x315610
        (spell; progress).  Past half way the owner's object flag 2 (not drawn) is set
        (dissolve) or cleared (re-form).  n = trunc(g x 38) or trunc(g x 74) particles with
        g = 2 x progress up to the half and 2 - 2 x progress after it; each takes one OWN
        draw for a model sample point (draw % the model's point count - a division with
        no test for a model without points) and a ball point (three per try)."""
        u32 = self.u32
        owner = u32(spell + 0xC)
        ramp = C.add(progress, progress)
        if C.lt(HALF, progress):
            ramp = C.sub(TWO, ramp)
            flags = u32(owner + 0xC)
            self.w32(owner + 0xC, flags | 2 if dissolve else flags & ~2)
        model = self.vcall(owner, 16)
        points = s32(self.call('model_getSamplePointCount', model))
        at = self.visual_pos(u32(spell + 0xC))
        count = C.to_int(C.mul(ramp, 0x42180000 if dissolve else 0x42940000))
        push, speed = (0x416C4D85, 0x413FF3B5) if dissolve else (0x40CDFBBF, 0x407DE33E)
        for _ in range(max(count, 0)):
            index = c_rem(self.spell_rand(spell), points)
            px, py, pz = self.model_sample(u32(spell + 0xC), model, at, index)
            x, y, z = self.spell_ball(spell)
            point = (C.sub(px, C.mul(x, push)), C.sub(py, C.mul(y, push)), C.sub(pz, C.mul(z, push)))
            self.call('particle_spawn', self.SS_PARTICLE, point, (C.mul(x, speed), C.mul(y, speed), C.mul(z, speed)), ZERO)

    def spiritshield_roll_absorb(self, spell):
        """SpellSpiritShield_rollAbsorb 0x315888 (spell) -> 1 when the hit is absorbed.
        damage_apply calls it for a victim that carries the spell, for hits without flag
        0x40.  With dur = slot 12 (0, level, owner, 10) and chance = slot 12 (1, ...):
        while clock <= dur ONE SHARED DRAW r, and r % 100 < chance absorbs: phase 0 becomes
        phase 1 (end = clock + 0.192) and a sound plays at the owner."""
        u32 = self.u32
        skill, level, owner = u32(spell + 8), self.s8(spell), u32(spell + 0xC)
        seconds = s32(self.skill_call(skill, 12, 0, level, owner, 10))
        chance = s32(self.skill_call(skill, 12, 1, level, u32(spell + 0xC), 10))
        if not C.le(u32(spell + 0x1C), C.from_int(seconds)):
            return 0
        if not self.draw() % 100 < chance:
            return 0
        if u32(spell + 0x18) == 0:
            self.w32(spell + 0x18, 1)
            self.w32(spell + 0x20, C.add(u32(spell + 0x1C), 0x3E449B62))
        self.sound_at(self.SS_LUMP, self.SS_HIT_SOUND, self.vec(u32(spell + 0xC) + 0x10))
        return 1


SKILL_BODIES.update({0x314E1C: (1, 'spiritshield_can_use'), 0x314E50: (2, 'spiritshield_cast'),
                     0x314FD8: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x3151B4: (2, 'spiritshield_spell_run')})
SPELL_TABLES.add(SpiritShield.SS_VT)
MODELLED.update({'SkillSpiritShield_canUse': 0x314E1C, 'SkillSpiritShield_cast': 0x314E50,
                 'SkillSpiritShield_manaCost': 0x314FD8, 'SpellSpiritShield_ctor': 0x31500C,
                 'SpellSpiritShield_run': 0x3151B4, 'SpellSpiritShield_dissolveParticles': 0x31539C,
                 'SpellSpiritShield_reformParticles': 0x315610, 'SpellSpiritShield_rollAbsorb': 0x315888})


class FrostArmor:
    """96 - Frost Armor (`frostarmor`, wizard; Cazic and Kobold cast it on themselves): a
    timed spell on the caster that removes a share of each hit and may strike back."""
    FA_VT = 0x51C3E8
    FA_LUMP, FA_SOUND, FA_HIT_SOUND = 0x553020, 0x553028, 0x553040
    FA_PARTICLES = (0x8E8788, 0x8E87D8)

    def frostarmor_can_use(self, skill, caster):
        """SkillFrostArmor_canUse 0x317afc: 1 unless the caster carries a SpellFrostArmor."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['FrostArmor']) else 1

    def frostarmor_cast(self, skill, level, caster, pos, facing):
        """SkillFrostArmor_cast 0x317b30: level through slot 14 (level, 0xe); pool_new(0x1c);
        the constructor."""
        level = self.skill_call(skill, 14, level, 0xE)
        spell = self.call('pool_new', 0x1C)
        if spell:
            self.frostarmor_spell_ctor(spell, level, caster, skill)
        return spell

    def frostarmor_spell_ctor(self, spell, level, caster, skill):
        """SpellFrostArmor_ctor 0x317d1c: the Spell base (ONE SHARED DRAW); clock +0x18 = 0;
        a LightEffect 36 above the caster's visual position, following the caster; a
        sound at the caster."""
        self.spell_base(spell, level, caster, skill, self.FA_VT)
        self.w32(spell + 0x18, 0)
        block = self.call('pool_new', 0xBC)
        if block:
            x, y, z = self.visual_pos(self.u32(spell + 0xC))
            self.light_effect(block, (C.add(x, ZERO), y, C.add(z, F_36)), self.u32(spell + 0xC),
                              (0x43400000, 0x43000000, 0x43800000, 0x42080000), (0x42F00000, 0x43340000, ZERO, ONE))
        self.sound_at(self.FA_LUMP, self.FA_SOUND, self.vec(self.u32(spell + 0xC) + 0x10))

    def frostarmor_spell_run(self, spell, pos=None, facing=0):
        """SpellFrostArmor_run 0x317ec0, once per frame of the owner: clock +0x18 += 1/60;
        (float) slot 12 (0, level, owner, cap 20) < clock: the spell destroys itself.
        Otherwise both owner flash quads = (0x40, 0x40, 0x80, 0x11) and 11 particles on
        model sample points, each a ball point (three OWN draws per try) and one more own
        draw for the point."""
        u32 = self.u32
        clock = C.add(u32(spell + 0x18), DT)
        self.w32(spell + 0x18, clock)
        seconds = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), u32(spell + 0xC), 0x14)
        if C.lt(C.from_int(s32(seconds)), u32(spell + 0x18)):
            self.spell_destroy(spell)
            return
        owner = u32(spell + 0xC)
        self.flash(owner, 1, 0x40, 0x40, 0x80, 0x11)
        self.flash(owner, 2, 0x40, 0x40, 0x80, 0x11)
        model = self.vcall(owner, 16)
        points = s32(self.call('model_getSamplePointCount', model))
        at = self.visual_pos(u32(spell + 0xC))
        for definition, speed, count in ((self.FA_PARTICLES[0], 0x409A4484, 10), (self.FA_PARTICLES[1], 0x40800000, 1)):
            for _ in range(count):
                x, y, z = self.spell_ball(spell)
                velocity = (C.mul(x, speed), C.mul(y, speed), C.mul(z, speed))
                index = c_rem(self.spell_rand(spell), points)
                point = self.model_sample(u32(spell + 0xC), model, at, index)
                self.call('particle_spawn', definition, point, velocity, ZERO)

    def frostarmor_on_hit(self, spell, attacker, dmg):
        """SpellFrostArmor_onHit 0x318264 (spell, attacker or 0; running damage) -> the
        factor damage_apply multiplies the damage by: 1 - slot 12 (1, level, owner, 0) / 100,
        not below 0.

        With an attacker: ONE SHARED DRAW r, always; r % 100 < slot 12 (2, level, owner, 0)
        strikes back: damage_apply(attacker, owner, 100000, 0, 0, flags 0x540, a descriptor
        whose slot 0 is cold (0x16) with both values (s16) trunc(dmg - factor), 0; 0, 0), a
        sound and fx_spawn(10) at the attacker.  The amount is the incoming damage minus
        the FACTOR (a number from 0 to 1), not the absorbed part."""
        u32 = self.u32
        skill, level = u32(spell + 8), self.s8(spell)
        factor = C.sub(ONE, C.mul(C.from_int(s32(self.skill_call(skill, 12, 1, level, u32(spell + 0xC), 0))), F_0_01))
        if C.lt(factor, ZERO):
            factor = ZERO
        if attacker:
            roll = self.draw()
            chance = s32(self.skill_call(u32(spell + 8), 12, 2, self.s8(spell), u32(spell + 0xC), 0))
            if roll % 100 < chance:
                amount = C.to_int(C.sub(dmg, factor)) & 0xFFFF
                self.call('damage_apply', attacker, u32(spell + 0xC), 100000, 0, 0, 0x540,
                          desc((0x16, amount, amount, 0)), 0, ZERO, ZERO)
                self.sound_at(self.FA_LUMP, self.FA_HIT_SOUND, self.vec(attacker + 0x10))
                self.call('fx_spawn', 10, self.vec(attacker + 0x10))
        return factor


SKILL_BODIES.update({0x317AFC: (1, 'frostarmor_can_use'), 0x317B30: (2, 'frostarmor_cast'),
                     0x317CE8: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x317EC0: (2, 'frostarmor_spell_run')})
SPELL_TABLES.add(FrostArmor.FA_VT)
MODELLED.update({'SkillFrostArmor_canUse': 0x317AFC, 'SkillFrostArmor_cast': 0x317B30,
                 'SkillFrostArmor_manaCost': 0x317CE8, 'SpellFrostArmor_ctor': 0x317D1C,
                 'SpellFrostArmor_run': 0x317EC0, 'SpellFrostArmor_onHit': 0x318264})


class WaveOfFlame:
    """95 - Wave of Flame (`waveofflame`, wizard; Cazic casts it too): a ring that grows
    from the caster and hits, once, everything that stood in its area at the cast."""
    WF_VT = 0x51C330
    WF_LUMP, WF_SOUND, WF_HIT_SOUND = 0x552F40, 0x552F48, 0x552F60
    WF_PARTICLES = (0x8E8698, 0x8E86E8, 0x8E8738)

    def waveofflame_can_use(self, skill, caster=0):
        """SkillWaveOfFlame_canUse 0x316b1c: always 1."""
        return 1

    def waveofflame_cast(self, skill, level, caster, pos, facing):
        """SkillWaveOfFlame_cast 0x316b24: level through slot 14 (level, 0x14);
        pool_new(0x2c); the constructor with a zero offset."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x2C)
        if spell:
            self.waveofflame_spell_ctor(spell, level, caster, (ZERO, ZERO, ZERO), skill)
        return spell

    def waveofflame_spell_ctor(self, spell, level, caster, offset, skill):
        """SpellWaveOfFlame_ctor 0x316d10 (spell, level, caster, offset, skill).

        The Spell base (ONE SHARED DRAW); centre +0x1c = the caster's visual position +
        offset, fixed from then on; clock +0x28 = 0; a sound at the centre; a LightEffect
        36 above the centre following nothing; then the candidate list +0x18:
        world_collectInSphere(centre, caster facing; R) with R = slot 12 (0, level, caster,
        cap 10) x 12 + the same again, and every returned object without object flags 0xd
        linked at the head of the list (so the list is the query's order reversed)."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, self.WF_VT)
        w32(spell + 0x18, 0)
        vx, vy, vz = self.visual_pos(caster)
        w32(spell + 0x1C, C.add(vx, offset[0]))
        w32(spell + 0x20, C.add(vy, offset[1]))
        w32(spell + 0x24, C.add(vz, offset[2]))
        w32(spell + 0x28, 0)
        centre = self.vec(spell + 0x1C)
        self.sound_at(self.WF_LUMP, self.WF_SOUND, centre)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(centre[0], ZERO), centre[1], C.add(centre[2], F_36)), 0,
                              (0x43400000, 0x42900000, 0x42140000, 0x43730000), (0x42F00000, 0x43340000, ZERO, ONE))
        steps = C.from_int(s32(self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), caster, 10)))
        reach = C.add(C.mul(steps, F_12), C.mul(steps, F_12))
        found = self.call('world_collectInSphere', centre, self.s16(u32(spell + 0xC) + 0x38), reach)
        for obj in found or ():
            if obj and not u32(obj + 0xC) & 0xD:
                self.handle_link(spell + 0x18, obj, obj)
        self.handle_clear('stack')

    def waveofflame_spell_run(self, spell, pos=None, facing=0):
        """SpellWaveOfFlame_run 0x317000, once per frame of the owner: clock +0x28 += 1/60;
        r = clock x 6 x 12 + 20.098; when (float) slot 12 (0, level, owner, cap 10) x 12 < r
        the spell destroys itself; else the hit test with r, then three rings of particles
        (trunc(f x 5), trunc(f x 65), trunc(f x 6) with f = min(1, r x 0.028)), each one OWN
        draw for the angle and a ball point for the velocity."""
        u32 = self.u32
        clock = C.add(u32(spell + 0x28), DT)
        self.w32(spell + 0x28, clock)
        ring = C.add(C.mul(C.mul(clock, 0x40C00000), F_12), 0x41A0C8B4)
        steps = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), u32(spell + 0xC), 10)
        if C.lt(C.mul(C.from_int(s32(steps)), F_12), ring):
            self.spell_destroy(spell)
            return
        self.waveofflame_hit_test(spell, ring)
        wobble = C.add(C.mul(C.sin16(u32(G_SIM_FRAME) * 0xD09), 0x40B51EA5), 0x4226189C)
        share = C.mul(ring, 0x3CE56041)
        if not C.le(share, ONE):
            share = ONE
        for definition, scale in zip(self.WF_PARTICLES, (0x40A00000, 0x42820000, 0x40C00000)):
            for _ in range(max(C.to_int(C.mul(share, scale)), 0)):
                angle = self.spell_rand(spell)
                px = C.add(u32(spell + 0x1C), C.mul(C.cos16(angle), ring))
                sine = C.sin16(angle)
                pz = C.add(u32(spell + 0x24), wobble)
                py = C.add(u32(spell + 0x20), C.mul(sine, ring))
                x, y, z = self.spell_ball(spell)
                speed = 0x40CC078F
                self.call('particle_spawn', definition, (px, py, pz),
                          (C.mul(x, speed), C.mul(y, speed), C.mul(z, speed)), ZERO)

    def waveofflame_hit_test(self, spell, ring):
        """SpellWaveOfFlame_hitTest 0x317570 (spell; ring radius): the candidate list in
        order.  An entry whose object is gone is dropped.  One the ring has reached -
        (dx*dx + dy*dy) - radius <= ring*ring in 2-D, the object's radius subtracted
        UNSQUARED - is, if it is a creature with object flags 9 or not an enemy of the owner
        (slot 20), dropped; otherwise hit and dropped: damage_apply(object, owner, 100000,
        0, 0, flags 0x160, descriptor slot 0 = fire (0x15, 10, 10, 0), 0; low, high) with
        the range of statistic_spread(statistic 1), and a sound at the object.  Objects that
        are not creatures are hit without any test."""
        u32 = self.u32
        for node, obj in self.handle_items(spell + 0x18):
            if not obj:
                self.handle_remove(node)
                continue
            dx = C.sub(u32(spell + 0x1C), u32(obj + 0x10))
            dy = C.sub(u32(spell + 0x20), u32(obj + 0x14))
            if not C.le(C.sub(C.add(C.mul(dx, dx), C.mul(dy, dy)), u32(obj + 0x1C)), C.mul(ring, ring)):
                continue
            if u32(obj + 0xC) & 0x20:
                if u32(obj + 0xC) & 9 or not self.vcall(u32(spell + 0xC), 20, obj):
                    self.handle_remove(node)
                    continue
            owner = u32(spell + 0xC)
            low, high = self.statistic_spread(u32(spell + 8), 1, self.s8(spell), owner)
            self.call('damage_apply', obj, u32(spell + 0xC), 100000, 0, 0, 0x160, desc((0x15, 10, 10, 0)), 0,
                      C.from_int(s32(low)), C.from_int(s32(high)))
            self.sound_at(self.WF_LUMP, self.WF_HIT_SOUND, self.vec(obj + 0x10))
            self.handle_remove(node)


SKILL_BODIES.update({0x316B1C: (1, 'waveofflame_can_use'), 0x316B24: (2, 'waveofflame_cast'),
                     0x316CDC: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x317000: (2, 'waveofflame_spell_run')})
SPELL_TABLES.add(WaveOfFlame.WF_VT)
MODELLED.update({'SkillWaveOfFlame_canUse': 0x316B1C, 'SkillWaveOfFlame_cast': 0x316B24,
                 'SkillWaveOfFlame_manaCost': 0x316CDC, 'SpellWaveOfFlame_ctor': 0x316D10,
                 'SpellWaveOfFlame_run': 0x317000, 'SpellWaveOfFlame_hitTest': 0x317570})


class UnspokenWord:
    """70 - Unspoken Word (`unspokenword`, cleric): a ring that grows from the caster for
    30 frames, damages each enemy creature once and may stun it."""
    UW_VT = 0x51AF10
    UW_LUMP, UW_SOUND = 0x5513B0, 0x5513B8
    UW_PARTICLES = (0x8E6C90, 0x8E6CE0)
    UW_WAVE, UW_LIFT = 0x41A2C994, 0x4200654B   # 20.348427, 32.09892

    def unspokenword_cast(self, skill, level, caster, pos, facing):
        """SkillUnspokenWord_cast 0x2fd030: level through slot 14 (level, 0x14); both caster
        flash quads = (0x40, 0x40, 0x80, 0x80); a sound at `pos`; a LightEffect 36 above
        `pos` following the caster; pool_new(0x38); the constructor."""
        level = self.skill_call(skill, 14, level, 0x14)
        self.flash(caster, 1, 0x40, 0x40, 0x80, 0x80)
        self.flash(caster, 2, 0x40, 0x40, 0x80, 0x80)
        self.sound_at(self.UW_LUMP, self.UW_SOUND, pos)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), caster,
                              (0x42C80000, 0x42C80000, 0x437F0000, 0xC2C00000), (0x42F00000, 0x43340000, ZERO, ONE))
        spell = self.call('pool_new', 0x38)
        if spell:
            self.unspokenword_spell_ctor(spell, level, caster, skill)
        return spell

    def unspokenword_spell_ctor(self, spell, level, caster, skill):
        """SpellUnspokenWord_ctor 0x2fd368.  The Spell base (ONE SHARED DRAW); start frame
        +0x2c = the frame counter; two trail handles +0x30, +0x34; caster +0x18 (a plain
        pointer); centre +0x20 = the caster's position; the candidate list +0x1c = every
        creature without object flags 0xd that world_collectInSphere(centre, caster facing;
        slot 10 (1, level) x 12 x 1.5) returns, linked at the head."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, self.UW_VT)
        w32(spell + 0x1C, 0)
        w32(spell + 0x2C, u32(G_SIM_FRAME))
        w32(spell + 0x30, self.call('trail_create', 1, 500, 5, 0x40, 0x40, 0x80, 0x80, TWO))
        handle = self.call('trail_create', 1, 300, 5, 0x40, 0x80, 0x40, 0x80, TWO)
        owner = u32(spell + 0xC)
        w32(spell + 0x34, handle)
        w32(spell + 0x18, owner)
        self.wvec(spell + 0x20, self.vec(owner + 0x10))
        steps = C.from_int(s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell))))
        reach = C.mul(C.mul(steps, F_12), 0x3FC00000)
        found = self.call('world_collectInSphere', self.vec(spell + 0x20), self.s16(u32(spell + 0xC) + 0x38), reach)
        for obj in found or ():
            if obj and u32(obj + 0xC) & 0x20 and not u32(obj + 0xC) & 0xD:
                self.handle_link(spell + 0x1C, obj, obj)
        self.handle_clear('stack')

    def _unspokenword_phase(self, spell, age):
        """The trail angle of this frame: (start frame x 400) % 0x10001 + age x 0x578."""
        return c_rem(s32(self.u32(spell + 0x2C) * 400), 0x10001) + age * 0x578

    def unspokenword_spell_run(self, spell, pos=None, facing=0):
        """SpellUnspokenWord_run 0x2fd5d4, once per frame of the owner.

        age = frame counter - start frame; from age 30 the spell destroys itself.  Else
        r = (age / 30) x (slot 10 (1, level) x 12); two ten-point spiral trails are laid at
        radius r; in the second half (age / 30 > 0.5) the trails shorten and fade and
        particles are spawned - n = statistic 1 x 6 on the first spiral, n / 2 on the
        second, each a ball point from the spell's OWN generator (three draws per try) -
        and then, last, the hit test with r, which takes its stun rolls from the same
        generator."""
        u32 = self.u32
        steps = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
        age = s32(u32(G_SIM_FRAME) - u32(spell + 0x2C))
        share = C.div(C.from_int(age), 0x41F00000)
        fade = ZERO
        if C.lt(HALF, share):
            fade = C.add(C.sub(share, HALF), C.sub(share, HALF))
        if not age < 30:
            self.spell_destroy(spell)
            return
        ring = C.mul(share, C.mul(C.from_int(steps), F_12))
        centre = self.vec(spell + 0x20)
        wave, lift = self.UW_WAVE, self.UW_LIFT

        def first(a, b):
            return (C.mul(ring, C.cos16(a)), C.mul(ring, C.sin16(a)), C.add(C.mul(C.sin16(b << 1), wave), lift))

        def second(a, b, fn):
            return (C.mul(C.neg(ring), C.cos16(b)), C.mul(ring, C.sin16(b)), C.add(C.mul(fn(a << 2), wave), lift))

        def at_centre(p):
            return tuple(C.add(p[i], centre[i]) for i in range(3))

        a = self._unspokenword_phase(spell, age)
        b = a + 0x8000
        trail_1, trail_2 = [], []
        for _ in range(10):
            trail_1.extend(at_centre(first(a, b)))
            trail_2.extend(at_centre(second(a, b, C.cos16)))
            a, b = a + 0x1999, b + 0x1999
        if C.lt(ZERO, fade):
            self.call('trail_setLength', u32(spell + 0x30), C.to_int(C.sub(0x43FA0000, C.mul(fade, 0x43FA0000))))
            self.call('trail_setLength', u32(spell + 0x34), C.to_int(C.sub(0x43960000, C.mul(fade, 0x43960000))))
            alpha = 0x80 - C.to_int(C.mul(fade, 0x43000000))
            self.call('trail_setColor', u32(spell + 0x30), 0x40, 0x40, 0x80, alpha)
            self.call('trail_setColor', u32(spell + 0x34), 0x40, 0x80, 0x40, alpha)
        self.call('trail_setPoints', u32(spell + 0x30), tuple(trail_1), 10, 0x78, ZERO, ONE)
        self.call('trail_setPoints', u32(spell + 0x34), tuple(trail_2), 10, 0x78, ZERO, ONE)
        if C.lt(ZERO, fade):
            steps = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
            count = steps * 6
            a = self._unspokenword_phase(spell, age)
            b = a + 0x8000
            for _ in range(max(count, 0)):
                px, py, pz = first(a, b)
                px, py = C.add(px, centre[0]), C.add(py, centre[1])
                pz = C.add(pz, centre[2])
                x, y, z = self.spell_ball(spell)
                velocity = (C.mul(x, 0x41000000), C.mul(y, 0x41000000), C.mul(z, 0x41000000))
                a, b = a + c_div(0x10000, count), b + c_div(0x10000, count)
                self.call('particle_spawn', self.UW_PARTICLES[0],
                          (C.add(px, velocity[0]), C.add(py, velocity[1]), C.add(pz, velocity[2])), velocity, ZERO)
            half = c_div(count, 2)
            a = self._unspokenword_phase(spell, age)
            b = a + 0x8000
            for _ in range(max(half, 0)):
                px, py, pz = second(a, b, C.sin16)
                px, py = C.add(px, u32(spell + 0x20)), C.add(py, u32(spell + 0x24))
                pz = C.add(pz, u32(spell + 0x28))
                x, y, z = self.spell_ball(spell)
                velocity = (C.mul(x, 0x41000000), C.mul(y, 0x41000000), C.mul(z, 0x41000000))
                a, b = a + c_div(0x10000, half), b + c_div(0x10000, half)
                self.call('particle_spawn', self.UW_PARTICLES[1],
                          (C.add(px, velocity[0]), C.add(py, velocity[1]), C.add(pz, velocity[2])), velocity, ZERO)
        self.unspokenword_hit_ring(spell, ring)

    def unspokenword_hit_ring(self, spell, ring):
        """SpellUnspokenWord_hitRing 0x2fddf0 (spell; radius): the candidate list in order.
        An entry whose object is gone is dropped.  One the ring has reached -
        sqrt(dx*dx + dy*dy) - radius <= ring - is dropped if it is a creature with object
        flags 9 or not an enemy of the caster (+0x18, slot 20); otherwise
        damage_apply(object, caster, 100000, 0, 0, flags, none, 0; low, high) with (low,
        high) = slot 8 (0, level, 0; 0.2) for every caster and flags 0x40940 below level 6,
        0x80940 to 10, 0x2100940 to 15, 0x2200940 from 16.  Then, for a creature whose hit
        points +0x228 are still >= 0, ONE OWN DRAW d: when 100 - slot 10 (2, level) <
        d % 100 + 1 it is stunned (its slot 30) for slot 10 (3, level) x 60 frames with
        the flash.  The entry is dropped either way."""
        u32 = self.u32
        for node, obj in self.handle_items(spell + 0x1C):
            if not obj:
                self.handle_remove(node)
                continue
            dy = C.sub(u32(spell + 0x24), u32(obj + 0x14))
            dx = C.sub(u32(spell + 0x20), u32(obj + 0x10))
            if not C.le(C.sub(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), u32(obj + 0x1C)), ring):
                continue
            if u32(obj + 0xC) & 0x20:
                if u32(obj + 0xC) & 9 or not self.vcall(u32(spell + 0x18), 20, obj):
                    self.handle_remove(node)
                    continue
            skill, level = u32(spell + 8), self.s8(spell)
            low, high = self.skill_call(skill, 8, 0, level, 0, F_0_2)
            flags = 0x2200940 if level >= 16 else 0x2100940 if level >= 11 else 0x80940 if level >= 6 else 0x40940
            self.call('damage_apply', obj, u32(spell + 0x18), 100000, 0, 0, flags, 0, 0,
                      C.from_int(s32(low)), C.from_int(s32(high)))
            if u32(obj + 0xC) & 0x20 and C.le(ZERO, u32(obj + 0x228)):
                roll = self.spell_rand(spell)
                chance = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))
                if 100 - chance < roll % 100 + 1:
                    seconds = s32(self.skill_call(u32(spell + 8), 10, 3, self.s8(spell)))
                    self.vcall(obj, 30, seconds * 60, 1)
            self.handle_remove(node)


EXTERNALS.update({
    'trail_create': Ext(0x190FF8, 'iiiiiii', 1, 'i', '(1, length, 5, four colour bytes; width) -> handle'),
    'trail_setLength': Ext(0x1911A8, 'ii', 0, 'n', '(handle, length)'),
    'trail_setColor': Ext(0x191100, 'iiiii', 0, 'n', '(handle, four colour bytes)'),
    'trail_setPoints': Ext(0x1918A0, 'iTii', 2, 'n', '(handle, ten points, 10, 0x78; 0.0, 1.0)'),
})
SKILL_BODIES.update({0x2FD030: (2, 'unspokenword_cast'), 0x2FD334: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x2FD5D4: (2, 'unspokenword_spell_run')})
SPELL_TABLES.add(UnspokenWord.UW_VT)
MODELLED.update({'SkillUnspokenWord_cast': 0x2FD030, 'SkillUnspokenWord_manaCost': 0x2FD334,
                 'SpellUnspokenWord_ctor': 0x2FD368, 'SpellUnspokenWord_run': 0x2FD5D4,
                 'SpellUnspokenWord_hitRing': 0x2FDDF0})


class Storms:
    """100 - Lightning Strike (`lightningstrike`; no class learns it, the Hag casts it) and
    80 - Pus Storm (`pusstorm`, shaman; FemaleDarkElf): one piece of code compiled twice.
    A drifting storm object that damages every enemy in a box under it each 30 frames and
    scatters decorations, whose count its OWN generator decides."""
    # per skill: table, block size, light record, owner handle, light colours, the float
    # at light +0x2c, sound lump and name, slot-14 constant, damage element, warning light
    STORM_LS = {'vt': 0x51C5E0, 'size': 0xBC, 'light': 0x80, 'handle': 0x7C, 'colour': (0x6F, 0x70, 0x9A, 0xFF),
                'extra': 0x3F199999, 'lump': 0x553330, 'sound': 0x553338, 'adjust': 2, 'element': 0x18,
                'warn': (0x42DE0000, 0x42E00000, 0x431A0000, 0x42FF0000), 'warn_life': 0x3FACCCCC}
    STORM_PS = {'vt': 0x51B830, 'size': 0xC0, 'light': 0x84, 'handle': 0x80, 'colour': (0x4F, 0x84, 0, 0xE7),
                'extra': 0x3F333333, 'lump': 0x552328, 'sound': 0x552330, 'adjust': 0x14, 'element': 0x26,
                'warn': (0x429E0000, 0x43040000, ZERO, 0x42E70000), 'warn_life': 0x3FAC8B32}
    PUSTULE_VT = 0x51B8C0
    PUS_FALL_SQUARED = 0x45160189               # 2400.096: the fall time is its square root, taken at run time

    def lightningstrike_cast(self, skill, level, caster, pos, facing):
        """SkillLightningStrike_cast 0x31a920 -> 0."""
        return self._storm_cast(self.STORM_LS, skill, level, caster, pos, facing)

    def pusstorm_cast(self, skill, level, caster, pos, facing):
        """SkillPusStorm_cast 0x30aaa8 -> 0."""
        return self._storm_cast(self.STORM_PS, skill, level, caster, pos, facing)

    def _storm_cast(self, cfg, skill, level, caster, pos, facing):
        """Both casts.  Level through slot 14.  The damage range: Lightning Strike asks like
        most skills (statistic_spread: slot 8 for a player, truncated tier 2 otherwise);
        PUS STORM ASKS SLOT 8 FOR EVERY CASTER, i.e. the player table.  s0, s2, s3 = slot 12
        (0 / 2 / 3, level, caster, cap 10).  The storm starts at pos + facing x s0 x 12 for a
        player and pos + facing x s0 x -6 for anyone else (the caster's flag word is read
        without a null test), on the ground (terrain_height, radius 24), and drifts along
        the facing at s3 units a second.  The decoration interval is 20 - trunc(level x 0.5).
        Pus Storm plays its sound before pool_new, Lightning Strike after the constructor."""
        level = self.skill_call(skill, 14, level, cfg['adjust'])
        if cfg is self.STORM_PS:
            low, high = self.skill_call(skill, 8, 1, level, 0, F_0_2)
        else:
            low, high = self.statistic_spread(skill, 1, level, caster)
        steps = C.from_int(s32(self.skill_call(skill, 12, 0, level, caster, 10)))
        seconds = s32(self.skill_call(skill, 12, 2, level, caster, 10))
        speed = C.from_int(s32(self.skill_call(skill, 12, 3, level, caster, 10)))
        ahead = 0x41400000 if self.u32(caster + 0xC) & 0x40 else 0xC0C00000
        cx = C.add(C.mul(C.mul(C.cos16(facing), steps), ahead), pos[0])
        cy = C.add(C.mul(C.mul(C.sin16(facing), steps), ahead), pos[1])
        ground = self.call('terrain_height', self.u32(G_WORLD), (cx, cy, C.add(ZERO, pos[2])), 0x41C00000)
        centre = (cx, cy, ground)
        velocity = (C.mul(C.cos16(facing), speed), C.mul(C.sin16(facing), speed), ZERO)
        interval = 0x14 - C.to_int(C.mul(C.from_int(s32(level)), HALF))
        if cfg is self.STORM_PS:
            self.sound_at(cfg['lump'], cfg['sound'], pos)
        block = self.call('pool_new', cfg['size'])
        if block:
            self._storm_ctor(cfg, block, centre, velocity, seconds * 60, interval, low, high, caster, steps)
        if cfg is self.STORM_LS:
            self.sound_at(cfg['lump'], cfg['sound'], pos)
        return 0

    def _storm_ctor(self, cfg, obj, centre, velocity, frames, interval, low, high, caster, steps):
        """LightningStrikeSpell_ctor 0x31ae48 / PusStorm_ctor 0x30af6c (object, centre,
        velocity per second, life in frames, interval, low, high, caster; radius steps).

        GameObject_ctor (its shared draw is inside the callee); object flags |= 0x420f; a
        light record; velocity per frame +0x4c; radius +0x78 = steps x 12; interval +0x68;
        range +0x70, +0x74; next decoration +0x6c = -1.  Start frame +0x58 = frame + 1, but
        frame + 41 with a warning LightEffect when the caster is a creature that is not a
        player.  Lightning Strike: first damage +0x5c = start, spawn end +0x60 = last frame
        +0x64 = start + life.  Pus Storm: fall time +0x7c = sqrt(2400.096) (computed here,
        0x30b14c), +0x60 = start + life, +0x5c = start + trunc(fall), +0x64 = +0x5c + life,
        and its light sits where the storm was `fall` frames ago."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        pus = cfg is self.STORM_PS
        self.call('GameObject_ctor', obj, tuple(centre), 0, 0)
        w32(obj + 0x48, cfg['vt'])
        light = obj + cfg['light']
        glow = C.fmin(0x43960000, C.mul(C.mul(steps, 0x3FE00000), F_12))
        w32(obj + cfg['handle'], 0)
        self.light_record(light, cfg['colour'], glow, C.div(ONE, C.mul(glow, glow)), cfg['extra'], centre)
        self.call('light_link', light)
        w32(obj + 0xC, u32(obj + 0xC) | 0x420F)
        step = tuple(C.mul(v, DT) for v in velocity)
        self.wvec(obj + 0x4C, step)
        w32(obj + 0x78, C.mul(steps, F_12))
        w8(obj + 0x28, 0xFF)
        w32(obj + 0x68, interval)
        w32(obj + 0x70, low)
        w32(obj + 0x74, high)
        if pus:
            w32(obj + 0x7C, C.sqrt(self.PUS_FALL_SQUARED))
        w8(obj + 0x29, 0xFF)
        frame = u32(G_SIM_FRAME)
        w32(obj + 0x58, frame + 1)
        if u32(caster + 0xC) & 0x60 == 0x20:
            w32(obj + 0x58, frame + 0x29)
            block = self.call('pool_new', 0xBC)
            if block:
                radius = u32(obj + 0x78)
                self.light_effect(block, (C.add(centre[0], ZERO), centre[1], C.add(centre[2], F_12)), 0, cfg['warn'],
                                  (C.fmin(0x43960000, C.add(radius, radius)), ZERO, cfg['extra'], cfg['warn_life']),
                                  1, cfg['warn'])
        w32(obj + 0x6C, M32)
        start = u32(obj + 0x58)
        if pus:
            fall = u32(obj + 0x7C)
            w32(obj + 0x60, start + frames)
            w32(obj + 0x5C, start + C.to_int(fall))
            w32(obj + 0x64, start + C.to_int(fall) + frames)
            back = C.neg(fall)
            self.wvec(light + 0x30, tuple(C.add(centre[i], C.mul(step[i], back)) for i in range(3)))
        else:
            w32(obj + 0x5C, start)
            w32(obj + 0x64, start + frames)
            w32(obj + 0x60, start + frames)
            self.wvec(light + 0x30, centre)
        self.call('light_relink', light)
        self.handle_link(obj + cfg['handle'], caster, caster)
        self.call('obj_runEveryFrame', obj)

    def lightningstrike_run(self, obj):
        """LightningStrikeSpell_run 0x31b25c (object), GameObject slot 4."""
        return self._storm_run(self.STORM_LS, obj)

    def pusstorm_run(self, obj):
        """PusStorm_run 0x30b428 (object), GameObject slot 4."""
        return self._storm_run(self.STORM_PS, obj)

    def _storm_run(self, cfg, obj):
        """Both run functions, once per frame.

        Nothing before the start frame +0x58.  Past the last frame +0x64, or with an empty
        owner handle, the object destroys itself (its slot 1 with 3).  Else: the position
        moves by the velocity; the light follows (Pus Storm: `fall` frames behind) and
        flickers; then
          decoration - when next +0x6c (set to this frame if negative) <= frame < spawn end
              +0x60: a ball point from the object's OWN generator (three draws per try)
              times the radius, dropped to the ground (terrain_height, radius 8);
              Lightning Strike: pool_new(0x60), LightningBolt_ctor(point, 17, 0);
              Pus Storm: two more own draws (distance (d / 65536 x 10 + 10) x 12 and angle),
              pool_new(0x160), Pustule_ctor from 240 above;
              then ONE OWN DRAW d: next = frame + interval / 2 + d % interval.  The
              remainder is a `div` with no test for a zero interval (level 40 or 41):
              tools/ee_emu.py then leaves the dividend d, as the R5900 is reported to.
          damage - on frames first damage +0x5c + 30 k: world_collectObjectsInBox(centre -/+
              (r, r, 2r), capacity 64) and, for every object the owner's slot 20 calls an
              enemy, damage_apply(object, owner, 100000, 0, 0, 0x40, descriptor slot 0 =
              (element, low / 2, high / 2, 0), 0; low / 2, high / 2) - integer halves."""
        u32, w32 = self.u32, self.w32
        pus = cfg is self.STORM_PS
        frame = s32(u32(G_SIM_FRAME))
        if not self.s32(obj + 0x58) <= frame:
            return
        if self.s32(obj + 0x64) < frame or u32(obj + cfg['handle']) == 0:
            if obj:
                self.vcall(obj, 1, 3)
            return
        light = obj + cfg['light']
        for k in range(3):
            w32(obj + 0x10 + 4 * k, C.add(u32(obj + 0x10 + 4 * k), u32(obj + 0x4C + 4 * k)))
        self.call('obj_updateGridCell', obj)
        centre = self.vec(obj + 0x10)
        if pus:
            back = C.neg(u32(obj + 0x7C))
            centre = tuple(C.add(u32(obj + 0x10 + 4 * k), C.mul(u32(obj + 0x4C + 4 * k), back)) for k in range(3))
        self.wvec(light + 0x30, centre)
        self.call('light_relink', light)
        glow = C.mul(u32(obj + 0x78), 0x3FE00000)
        glow = C.add(glow, C.mul(C.mul(C.sin16(frame << 10), 0x3D4CCCCC), glow))
        spawn_end = self.s32(obj + 0x60)
        if spawn_end < frame:
            left = C.div(C.from_int(frame - spawn_end), C.from_int(self.s32(obj + 0x64) - spawn_end))
            glow = C.mul(glow, C.sub(ONE, left))
        glow = C.fmin(0x43960000, glow)
        w32(light + 0x1C, glow)
        w32(light + 0x24, glow)
        falloff = C.div(ONE, C.mul(glow, glow))
        w32(light + 0x28, falloff)
        w32(light + 0x20, falloff)
        if self.s32(obj + 0x6C) < 0:
            w32(obj + 0x6C, frame)
        if frame < spawn_end and self.s32(obj + 0x6C) <= frame:
            x, y, z = self.obj_ball(obj)
            radius = u32(obj + 0x78)
            px = C.add(u32(obj + 0x10), C.mul(x, radius))
            py = C.add(u32(obj + 0x14), C.mul(y, radius))
            pz = C.add(u32(obj + 0x18), C.mul(z, radius))
            ground = self.call('terrain_height', u32(G_WORLD), (px, py, pz), 0x41000000)
            if pus:
                reach = C.mul(C.add(C.mul(C.mul(C.from_int(self.obj_rand(obj)), F_2M16), 0x41200000), 0x41200000), F_12)
                angle = self.obj_rand(obj)
                sx = C.add(px, C.mul(reach, C.cos16(angle)))
                sy = C.add(py, C.mul(reach, C.sin16(angle)))
                sz = C.add(ground, 0x43700000)
                inverse = C.div(ONE, u32(obj + 0x7C))
                drift = (C.mul(C.sub(px, sx), inverse), C.mul(C.sub(py, sy), inverse), ZERO)
                block = self.call('pool_new', 0x160)
                if block:
                    self.pustule_ctor(block, (sx, sy, sz), (px, py, ground), drift, angle)
            else:
                block = self.call('pool_new', 0x60)
                if block:
                    self.call('LightningBolt_ctor', block, (px, py, ground), 0x11, 0)
            draw = self.obj_rand(obj)
            interval = self.s32(obj + 0x68)
            rest = draw if interval == 0 else c_rem(draw, interval)
            w32(obj + 0x6C, s32(u32(G_SIM_FRAME)) + ((interval + (1 if interval < 0 else 0)) >> 1) + rest)
        frame = s32(u32(G_SIM_FRAME))
        first = self.s32(obj + 0x5C)
        if first <= frame and c_rem(frame - first, 30) == 0:
            radius = u32(obj + 0x78)
            twice = C.add(radius, radius)
            low_corner = (C.sub(centre[0], radius), C.sub(centre[1], radius), C.sub(centre[2], twice))
            high_corner = (C.add(centre[0], radius), C.add(centre[1], radius), C.add(C.add(centre[2], radius), radius))
            low, high = c_div(self.s32(obj + 0x70), 2), c_div(self.s32(obj + 0x74), 2)
            found = self.call('world_collectObjectsInBox', low_corner, high_corner, 0x40)
            owner = u32(u32(obj + cfg['handle']) + 0xC)
            for other in found or ():
                if self.vcall(owner, 20, other):
                    self.call('damage_apply', other, owner, 100000, 0, 0, 0x40, desc((cfg['element'], low, high, 0)), 0,
                              C.from_int(low), C.from_int(high))

    def pustule_ctor(self, obj, start, ground, drift, angle):
        """Pustule_ctor 0x30bb38 (object, start, ground point, velocity per frame, angle): a
        GameObject (its shared draw is inside the callee) with flags |= 0x420d, the ground
        point at +0x4c, the velocity at +0x58, the angle at +0x68, two zero words (+0x64,
        +0x6c); placed in the grid and run every frame.  It damages nothing."""
        self.call('GameObject_ctor', obj, tuple(start), 0, 0)
        self.w32(obj + 0x48, self.PUSTULE_VT)
        self.wvec(obj + 0x4C, ground)
        self.wvec(obj + 0x58, drift)
        self.w16(obj + 0x68, angle)
        self.w32(obj + 0x64, 0)
        self.w32(obj + 0x6C, 0)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x420D)
        self.call('obj_updateGridCell', obj)
        self.call('obj_runEveryFrame', obj)


EXTERNALS.update({
    'LightningBolt_ctor': Ext(0x295360, 'pvii', 0, 'n', '(block, ground point, life in frames, light flag)'),
})
SKILL_BODIES.update({0x31A920: (2, 'lightningstrike_cast'), 0x31AE14: (5, 'skill_mana_cost'),
                     0x30AAA8: (2, 'pusstorm_cast'), 0x30AF38: (5, 'skill_mana_cost')})
OBJECT_TABLES.update({Storms.STORM_LS['vt'], Storms.STORM_PS['vt'], Storms.PUSTULE_VT})
MODELLED.update({'SkillLightningStrike_cast': 0x31A920, 'SkillLightningStrike_manaCost': 0x31AE14,
                 'LightningStrikeSpell_ctor': 0x31AE48, 'LightningStrikeSpell_run': 0x31B25C,
                 'SkillPusStorm_cast': 0x30AAA8, 'SkillPusStorm_manaCost': 0x30AF38, 'PusStorm_ctor': 0x30AF6C,
                 'PusStorm_run': 0x30B428, 'Pustule_ctor': 0x30BB38})


class ConeOfShock:
    """101 - Cone of Shock (`coneofshock`, kind 1 "channelled"; no class learns it, the Hag
    casts it): a spell on the caster that hits the enemies in a short wedge four times a
    second.  The top of each hit's lightning range comes from the spell's OWN generator,
    which the decoration draw also advances."""
    CS_VT = 0x51C6F8
    CS_LUMP, CS_SOUND, CS_HIT_SOUND = 0x553408, 0x553410, 0x553428

    def coneofshock_cast(self, skill, level, caster, pos, facing):
        """SkillConeOfShock_cast 0x31b8f0: level through slot 14 (level, 1); pool_new(0x58);
        the constructor."""
        level = self.skill_call(skill, 14, level, 1)
        spell = self.call('pool_new', 0x58)
        if spell:
            self.coneofshock_spell_ctor(spell, level, caster, skill)
        return spell

    def coneofshock_spell_ctor(self, spell, level, caster, skill):
        """SpellConeOfShock_ctor 0x31bac8: the Spell base (ONE SHARED DRAW); a light record
        at +0x18 placed 60 above the caster; a looping sound whose handle is kept at +0x54."""
        place = (C.add(self.u32(caster + 0x10), ZERO), self.u32(caster + 0x14), C.add(self.u32(caster + 0x18), F_60))
        self.spell_base(spell, level, caster, skill, self.CS_VT)
        self.light_record(spell + 0x18, (0x6F, 0x70, 0x9A, 0), 0x431C0000, 0x382C598A, ZERO, place)
        self.call('light_link', spell + 0x18)
        self.w32(spell + 0x54, self.sound_at(self.CS_LUMP, self.CS_SOUND, self.vec(self.u32(spell + 0xC) + 0x10)))

    def coneofshock_spell_run(self, spell, pos, facing):
        """SpellConeOfShock_run 0x31bcd0 (spell, position, facing), once per frame of the
        owner, with what Creature slot 17 hands in.

        arc = slot 12 (2, level, owner, cap 10) degrees; reach = slot 12 (1, level, owner,
        cap 25) x 12.
          decoration, on frames with frame % (60 / ((level / 4) x 2 + 2)) == 0: ONE OWN DRAW
              r; a bolt (pool_new(0x60), LightningBolt_ctor2) from 12 to reach + 12 units
              along facing + trunc((s16) trunc(arc x 182.04443) x (r / 65536 - 0.5)).
          damage, on frames with frame % 15 == 0: world_collectObjectsInArc(origin = pos - 12
              x facing, facing, no owner filter; reach, arc + 10, 0) and, for every entry
              the owner's slot 20 calls an enemy, in list order: s0 = slot 12 (0, level,
              owner, 0), ONE OWN DRAW r, q = trunc(s0 x 0.25) and damage_apply(object,
              owner, 100000, 0, 0, 0x40, descriptor slot 0 = lightning (0x18, q, q +
              trunc(q x (r / 65536) x 0.19999999), 0), 0; 0, 0); a sound at the owner if
              anything was hit.
        Then the light radius flickers with sin16(frame x 1000)."""
        u32, w32 = self.u32, self.w32
        facing = s16(facing)
        skill, owner = u32(spell + 8), u32(spell + 0xC)
        arc = C.from_int(s32(self.skill_call(skill, 12, 2, self.s8(spell), owner, 10)))
        arc_angle = s16(C.to_int(C.mul(arc, C.K_DEG_TO_ANGLE)))
        reach = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), u32(spell + 0xC), 0x19))),
                      F_12)
        frame = s32(u32(G_SIM_FRAME))
        period = c_div(0x3C, c_div(self.s8(spell), 4) * 2 + 2)
        if c_rem(frame, period) == 0:
            spread = C.sub(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), HALF)
            angle = s16(facing + C.to_int(C.mul(C.from_int(arc_angle), spread)))
            cosine, sine = C.cos16(angle), C.sin16(angle)
            near = (C.add(pos[0], C.mul(cosine, F_12)), C.add(pos[1], C.mul(sine, F_12)), pos[2])
            length = C.add(reach, F_12)
            far = (C.add(pos[0], C.mul(cosine, length)), C.add(pos[1], C.mul(sine, length)), pos[2])
            block = self.call('pool_new', 0x60)
            if block:
                self.call('LightningBolt_ctor2', block, far, near, 0xB, 0)
        if c_rem(s32(u32(G_SIM_FRAME)), 15) == 0:
            origin = (C.sub(pos[0], C.mul(C.cos16(facing), F_12)), C.sub(pos[1], C.mul(C.sin16(facing), F_12)), pos[2])
            found = self.call('world_collectObjectsInArc', origin, facing, 0, reach, C.add(arc, 0x41200000), ZERO)
            hit = False
            for obj in found or ():
                if not self.vcall(u32(spell + 0xC), 20, obj):
                    continue
                amount = C.from_int(s32(self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), u32(spell + 0xC), 0)))
                quarter = C.to_int(C.mul(amount, 0x3E800000))
                share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
                top = quarter + C.to_int(C.mul(C.mul(C.from_int(quarter), share), F_0_2))
                self.call('damage_apply', obj, u32(spell + 0xC), 100000, 0, 0, 0x40, desc((0x18, quarter, top, 0)), 0,
                          ZERO, ZERO)
                hit = True
            if hit:
                self.sound_at(self.CS_LUMP, self.CS_HIT_SOUND, self.vec(u32(spell + 0xC) + 0x10))
            self.handle_clear('stack')
        glow = C.from_int(C.to_int(C.mul(C.sin16(u32(G_SIM_FRAME) * 1000), 0x40C00000)) + 0x6C)
        w32(spell + 0x34, glow)
        w32(spell + 0x3C, glow)
        falloff = C.div(ONE, C.mul(glow, glow))
        w32(spell + 0x40, falloff)
        w32(spell + 0x38, falloff)
        self.call('light_relink', spell + 0x18)


EXTERNALS.update({
    'LightningBolt_ctor2': Ext(0x295584, 'pvvii', 0, 'n', '(block, far end, near end, life in frames, light flag)'),
    'sound_playAtPos': Ext(0x214428, 'pv', 1, 'i', '(entry, position; volume) -> sound handle'),
})
SKILL_BODIES.update({0x31B8F0: (2, 'coneofshock_cast'), 0x31BA94: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x31BCD0: (2, 'coneofshock_spell_run')})
SPELL_TABLES.add(ConeOfShock.CS_VT)
MODELLED.update({'SkillConeOfShock_cast': 0x31B8F0, 'SkillConeOfShock_manaCost': 0x31BA94,
                 'SpellConeOfShock_ctor': 0x31BAC8, 'SpellConeOfShock_run': 0x31BCD0})


class Drowsy:
    """88 - Drowsy (`drowsy`, shaman): one spell on each victim; after half a second a roll
    from that spell's OWN generator - behind 31 frames of particle draws - decides whether
    the victim is slowed."""
    DR_VT = 0x51BB48
    DR_LUMP, DR_SOUND = 0x552530, 0x552538
    DR_PARTICLES = (0x8E82D8, 0x8E8328)

    def drowsy_cast(self, skill, level, caster, pos, facing):
        """SkillDrowsy_cast 0x30e1f0 -> 0.  Level through slot 14 (level, 10); a sound on
        the caster; both caster flash quads = (0x40, 0x40, 0x80, 0x2e); a LightEffect 36
        above `pos` following the caster; then world_collectObjectsInArc(pos, facing, no
        owner; 240, 120 degrees, 0) and, walking the list until it ends or slot 10 (0,
        level) victims are taken: an entry is taken when the caster's slot 20 calls it an
        enemy (not asked without a caster), it has no object flag 0x1000000,
        creature_bossRank is 0 and its timer +0x31a is below 1.  Each taken entry gets
        pool_new(0x34), a SpellDrowsy (ONE SHARED DRAW) and creature_addSpell - which is
        called with 0, and the entry still counted, when the pool had no block."""
        u32 = self.u32
        facing = s16(facing)
        level = self.skill_call(skill, 14, level, 10)
        self.call('sound_playOnObject', self.call('res_find', self.DR_LUMP, self.DR_SOUND), caster, ONE)
        self.flash(caster, 1, 0x40, 0x40, 0x80, 0x2E)
        self.flash(caster, 2, 0x40, 0x40, 0x80, 0x2E)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), caster,
                              (0x42800000, 0x42800000, 0x43000000, 0x42380000), (0x42F00000, 0x43340000, ZERO, ONE))
        most = s32(self.skill_call(skill, 10, 0, level))
        found = self.call('world_collectObjectsInArc', tuple(pos), facing, 0, 0x43700000, 0x42F00000, ZERO)
        taken = 0
        for obj in found or ():
            if not taken < most:
                break
            if caster and not self.vcall(caster, 20, obj):
                continue
            if u32(obj + 0xC) & 0x1000000 or self.call('creature_bossRank', obj) or not self.s16(obj + 0x31A) < 1:
                continue
            spell = self.call('pool_new', 0x34)
            if spell:
                self.drowsy_spell_ctor(spell, level, obj, skill)
            self.call('creature_addSpell', obj, spell)
            taken += 1
        self.handle_clear('stack')
        return 0

    def drowsy_spell_ctor(self, spell, level, victim, skill):
        """SpellDrowsy_ctor 0x30e620 (spell, level, victim, skill): the Spell base with the
        VICTIM as owner (ONE SHARED DRAW); clock +0x18 = 0, phase start +0x1c = 0, phase
        +0x24 = 0, duration +0x20 = slot 10 (1, level) seconds, three letter heights +0x28
        = 0, -16.96, -33.92."""
        w32 = self.w32
        self.spell_base(spell, level, victim, skill, self.DR_VT)
        w32(spell + 0x18, 0)
        w32(spell + 0x1C, 0)
        w32(spell + 0x24, 0)
        w32(spell + 0x20, self.skill_call(skill, 10, 1, s8(level)))
        w32(spell + 0x28, 0)
        w32(spell + 0x30, 0xC207B1CF)
        w32(spell + 0x2C, 0xC187B1CF)

    def _drowsy_burst(self, spell, definition, speed, flat):
        """15 particles around the victim: per particle two OWN draws (distance and angle)
        and a ball point (three per try)."""
        u32 = self.u32
        owner = u32(spell + 0xC)
        vx, vy, vz = self.visual_pos(owner)
        top = C.add(vz, u32(u32(spell + 0xC) + 0x20))
        radius = u32(u32(spell + 0xC) + 0x1C)
        for _ in range(15):
            share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
            angle = self.spell_rand(spell)
            ox = C.mul(C.mul(C.cos16(angle), share), radius)
            oy = C.mul(C.mul(C.sin16(angle), share), radius)
            x, y, z = self.spell_ball(spell)
            velocity = (C.mul(x, speed), C.mul(y, speed), ZERO if flat else C.mul(z, speed))
            tx, ty = C.add(velocity[0], vx), C.add(velocity[1], vy)
            tz = C.add(top, ZERO) if flat else C.add(velocity[2], top)
            point = (C.add(ox, tx), C.add(oy, ty), C.add(ZERO, tz))
            self.call('particle_spawn', definition, point, velocity, ZERO)

    def drowsy_spell_run(self, spell, pos=None, facing=0):
        """SpellDrowsy_run 0x30e6f0, once per frame of the VICTIM.  clock +0x18 += 1/60; a
        dead victim (object flag 8) destroys the spell.  By phase +0x24:
          0  15 particles; while clock < 0.5 nothing more (30 runs).  Then ONE OWN DRAW r:
             r % 100 < slot 10 (2, level): phase 2, phase start = clock, victim timer
             +0x31a = (s16)(duration x 60); otherwise phase 1, phase start = clock.
          1  15 particles; clock - phase start > 0.178: the spell destroys itself.
          2  clock - phase start > (float) duration: the spell destroys itself; else the
             three letter heights advance by 0.3242 (back to 0 above 51.61), both victim
             flash quads = (0x40, 0x40, 0x80, 0x2e), and in a net game a player victim in
             a local slot sets the force-rebase byte 0x402797 (per machine)."""
        u32, w32 = self.u32, self.w32
        before = u32(spell + 0x18)
        owner = u32(spell + 0xC)
        clock = C.add(before, DT)
        w32(spell + 0x18, clock)
        phase = u32(spell + 0x24)
        expired = True
        if not u32(owner + 0xC) & 8:
            if phase == 0:
                self._drowsy_burst(spell, self.DR_PARTICLES[0], 0x40800000, False)
                if not C.le(HALF, u32(spell + 0x18)):
                    return
                roll = self.spell_rand(spell) % 100
                chance = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))
                if (roll & 0xFFFF) < chance:
                    w32(spell + 0x24, 2)
                    w32(spell + 0x1C, u32(spell + 0x18))
                    self.w16(u32(spell + 0xC) + 0x31A, u32(spell + 0x20) * 0x3C)
                else:
                    w32(spell + 0x1C, u32(spell + 0x18))
                    w32(spell + 0x24, 1)
                return
            if phase == 1:
                self._drowsy_burst(spell, self.DR_PARTICLES[1], F_12, True)
                if C.le(C.sub(u32(spell + 0x18), u32(spell + 0x1C)), 0x3E3645A1):
                    return
            elif phase == 2:
                if C.le(C.sub(clock, u32(spell + 0x1C)), C.from_int(self.s32(spell + 0x20))):
                    for k in range(3):
                        height = C.add(u32(spell + 0x28 + 4 * k), 0x3EA6018C)
                        w32(spell + 0x28 + 4 * k, height)
                        if C.lt(0x424E7203, height):
                            w32(spell + 0x28 + 4 * k, 0)
                    self.flash(owner, 1, 0x40, 0x40, 0x80, 0x2E)
                    self.flash(owner, 2, 0x40, 0x40, 0x80, 0x2E)
                    if self.s8(G_NETWORK_MODE) and u32(owner + 0xC) & 0x40 \
                            and self.call('net_isLocalSlot', u32(owner + 0x3C8)):
                        self.w8(G_FORCE_GHOST_REBASE, 1)
                    return
            else:
                return
        if spell:
            self.spell_destroy(spell)

    def drowsy_fraction(self, spell):
        """SpellDrowsy_getStat3Fraction 0x30ef08 (spell) -> slot 10 (3, level) x 0.01: the
        speed factor nine movement and animation functions apply while the victim's timer
        +0x31a runs and it carries the spell."""
        return C.mul(C.from_int(s32(self.skill_call(self.u32(spell + 8), 10, 3, self.s8(spell)))), F_0_01)


EXTERNALS.update({
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i', '(slot) (machine)'),
})
SKILL_BODIES.update({0x30E1F0: (2, 'drowsy_cast'), 0x30E5EC: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x30E6F0: (2, 'drowsy_spell_run')})
SPELL_TABLES.add(Drowsy.DR_VT)
MODELLED.update({'SkillDrowsy_cast': 0x30E1F0, 'SkillDrowsy_manaCost': 0x30E5EC, 'SpellDrowsy_ctor': 0x30E620,
                 'SpellDrowsy_run': 0x30E6F0, 'SpellDrowsy_getStat3Fraction': 0x30EF08})


class PoisonBolt:
    """89 - Poison Bolt (`poisonbolt`, shaman): a homing projectile that hits the first
    enemy it touches and leaves a gas cloud where it ends."""
    PB_VT = 0x51BB78
    PB_LUMP, PB_LAUNCH, PB_END = 0x5525F8, 0x552600, 0x552640
    PB_PARTICLES = (0x8E8378, 0x8E83C8, 0x8E8418)
    PB_SPEED = 0x43AF0000                       # 350 units a second
    PB_DOUBLES = (0x552658, 0x552660)           # two doubles the burst multiplies by

    def poisonbolt_cast(self, skill, level, caster, pos, facing):
        """SkillPoisonBolt_cast 0x30f168 -> 0.  Level through slot 14 (level, 0x14); both
        caster flash quads = (0, 0x80, 0, 0) (no null test); pool_new(0xb8); the bolt."""
        level = self.skill_call(skill, 14, level, 0x14)
        self.flash(caster, 1, 0, 0x80, 0, 0)
        self.flash(caster, 2, 0, 0x80, 0, 0)
        block = self.call('pool_new', 0xB8)
        if block:
            self.poisonbolt_ctor(block, pos, facing, level, caster, skill)
        return 0

    def poisonbolt_ctor(self, obj, pos, facing, level, caster, skill):
        """PoisonBolt_ctor 0x30f398 (object, position, facing, level, caster, skill).

        Projectile_ctor(object, position, caster, 0) (a GameObject: its shared draw is
        inside the callee); a light record at +0x54; skill +0x98, level +0x9c (s16),
        heading +0x38, velocity +0xa0 = 350 x (cos, sin)(facing), 0; with a caster a handle
        to it at +0x90; "has hit" +0xb4 = 0; expiry +0xac = frame + 113; homing starts
        after +0xb0 = frame + 11.  With a caster: world_collectObjectsInArc(position,
        facing, no filter; 280, 60 degrees, 0) and a handle at +0x94 to the first entry the
        caster's slot 20 calls an enemy.  Then the run list and the launch sound."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.call('Projectile_ctor', obj, tuple(pos), caster, 0)
        w32(obj + 0x48, self.PB_VT)
        self.light_record(obj + 0x54, (0, 0x80, 0, 0), 0x42C20000, 0x38DEE34B, 0x3F4CCCCC, pos)
        self.call('light_link', obj + 0x54)
        w32(obj + 0x90, 0)
        w32(obj + 0x98, skill)
        w16(obj + 0x9C, level)
        w32(obj + 0x94, 0)
        w16(obj + 0x38, facing)
        w32(obj + 0xA8, 0)
        w32(obj + 0xA0, C.mul(C.cos16(facing), self.PB_SPEED))
        w32(obj + 0xA4, C.mul(C.sin16(facing), self.PB_SPEED))
        if caster:
            self.handle_link(obj + 0x90, caster, caster)
        frame = u32(G_SIM_FRAME)
        w32(obj + 0xB4, 0)
        w32(obj + 0xAC, frame + 0x71)
        w32(obj + 0xB0, frame + 0xB)
        if caster:
            found = self.call('world_collectObjectsInArc', tuple(pos), s16(facing), 0, 0x438C0000, F_60, ZERO)
            for other in found or ():
                if self.vcall(caster, 20, other):
                    self.handle_link(obj + 0x94, other, other)
                    break
            self.handle_clear('stack')
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', self.PB_LUMP, self.PB_LAUNCH), obj, ONE)

    def poisonbolt_run(self, obj):
        """PoisonBolt_run 0x30f800 (object), once per frame.

        With a target handle and frame > homing start: d = atan2_16(dy, dx) - heading (not
        wrapped); the heading takes d when |d| < 0x222, else moves 0x222 toward it; the
        velocity follows.  obj_moveAndCollide(object, velocity) -> bit 1 terrain, bit 2
        touched something (its touch handler is poisonbolt_on_hit).  Terrain, or a touch
        with "has hit" set, zeroes the expiry.  While frame < expiry: 36 trail particles
        (each a ball point, one draw and a second ball point from the object's OWN
        generator) and the light follows.  Otherwise the end sound, the burst, and the
        object destroys itself."""
        u32, w32 = self.u32, self.w32
        frame = s32(u32(G_SIM_FRAME))
        if u32(obj + 0x94) and self.s32(obj + 0xB0) < frame:
            target = u32(u32(obj + 0x94) + 0xC)
            turn = C.atan2_16(C.sub(u32(target + 0x14), u32(obj + 0x14)),
                              C.sub(u32(target + 0x10), u32(obj + 0x10))) - self.s16(obj + 0x38)
            heading = self.s16(obj + 0x38)
            if abs(turn) < 0x222:
                heading += turn
            elif turn < 1:
                heading -= 0x222
            else:
                heading += 0x222
            self.w16(obj + 0x38, heading)
            w32(obj + 0xA0, C.mul(C.cos16(self.s16(obj + 0x38)), self.PB_SPEED))
            sine = C.sin16(self.s16(obj + 0x38))
            w32(obj + 0xA8, 0)
            w32(obj + 0xA4, C.mul(sine, self.PB_SPEED))
        old = self.vec(obj + 0x10)
        result = self.call('obj_moveAndCollide', obj, self.vec(obj + 0xA0))
        if result & 2 and u32(obj + 0xB4):
            w32(obj + 0xAC, 0)
        if result & 1:
            w32(obj + 0xAC, 0)
        if s32(u32(G_SIM_FRAME)) < self.s32(obj + 0xAC):
            delta = tuple(C.sub(u32(obj + 0x10 + 4 * k), old[k]) for k in range(3))
            pulse = C.to_int(C.mul(C.mul(C.add(C.sin16(u32(G_SIM_FRAME) << 12), ONE), F_36), HALF))
            for definition, count in ((self.PB_PARTICLES[0], 0x24 - pulse), (self.PB_PARTICLES[1], pulse)):
                for _ in range(max(count, 0)):
                    ball = self.obj_ball(obj)
                    point = tuple(C.add(C.mul(ball[k], 0x40DFC651), old[k]) for k in range(3))
                    share = C.mul(C.from_int(self.obj_rand(obj)), F_2M16)
                    point = tuple(C.add(point[k], C.mul(delta[k], share)) for k in range(3))
                    ball = self.obj_ball(obj)
                    self.call('particle_spawn', definition, point, tuple(C.mul(v, 0x4129CE76) for v in ball), ZERO)
            self.wvec(obj + 0x84, self.vec(obj + 0x10))
            self.call('light_relink', obj + 0x54)
        else:
            self.call('sound_playOnObject', self.call('res_find', self.PB_LUMP, self.PB_END), obj, ONE)
            self.poisonbolt_burst(obj)
            if obj:
                self.vcall(obj, 1, 3)

    def poisonbolt_on_hit(self, obj, other):
        """PoisonBolt_onHit 0x310028 (bolt, other), GameObject slot 6.  Nothing once "has
        hit" +0xb4 is set.  Without an owner: a non-creature sets "has hit", a creature
        does nothing.  With an owner: nothing unless the owner's slot 20 calls `other` an
        enemy, and nothing for a creature with creature flag 0x200; otherwise
        damage_apply(other, owner, 100000, 0, 0, flags, none, 0; slot 8 (0, level, 0; 0.2))
        with flags 0x10040, 0x50040 above level 10, 0x90040 above 15; a creature also gets
        Creature_setEffectTimer(other, 3, owner; slot 10 (3, level) seconds); "has hit" = 1."""
        u32 = self.u32
        if u32(obj + 0xB4):
            return
        if not u32(obj + 0x90):
            if not u32(other + 0xC) & 0x20:
                self.w32(obj + 0xB4, 1)
                return
            return
        owner = u32(u32(obj + 0x90) + 0xC)
        if not self.vcall(owner, 20, other):
            return
        if u32(other + 0xC) & 0x20 and self.u64(other + 0xA8) & 0x200:
            return
        if not u32(obj + 0x90):
            return
        skill, level = u32(obj + 0x98), self.s16(obj + 0x9C)
        low, high = self.skill_call(skill, 8, 0, level, 0, F_0_2)
        flags = 0x90040 if level > 15 else 0x50040 if level > 10 else 0x10040
        self.call('damage_apply', other, u32(u32(obj + 0x90) + 0xC), 100000, 0, 0, flags, 0, 0,
                  C.from_int(s32(low)), C.from_int(s32(high)))
        if u32(other + 0xC) & 0x20:
            seconds = s32(self.skill_call(u32(obj + 0x98), 10, 3, self.s16(obj + 0x9C)))
            self.call('Creature_setEffectTimer', other, 3, u32(u32(obj + 0x90) + 0xC), C.from_int(seconds))
        self.w32(obj + 0xB4, 1)

    def poisonbolt_burst(self, obj):
        """PoisonBolt_burst 0x3101cc (bolt).  With an owner handle and slot 10 (1, level) x
        12 > 0: pool_new(0x70) and poisonGasSpell_ctor(block, position, slot 10 (3) x 60
        frames, slot 10 (1) x 12, 0, the owner behind the handle at +0x4c, slot 10 (2)) - a
        GameObject, one shared draw inside the callee.  Then 321 particles, a ball point
        each from the bolt's OWN generator; the vertical speed is |z| times two double
        constants, in the C library's soft double arithmetic."""
        u32 = self.u32
        if u32(obj + 0x90):
            skill, level = u32(obj + 0x98), self.s16(obj + 0x9C)
            seconds = s32(self.skill_call(skill, 10, 3, level))
            steps = s32(self.skill_call(u32(obj + 0x98), 10, 1, self.s16(obj + 0x9C)))
            value = self.skill_call(u32(obj + 0x98), 10, 2, self.s16(obj + 0x9C))
            if 0 < steps * 12:
                block = self.call('pool_new', 0x70)
                if block:
                    self.call('poisonGasSpell_ctor', block, self.vec(obj + 0x10), seconds * 60, steps * 12, 0,
                              u32(u32(obj + 0x4C) + 0xC), value)
        for _ in range(0x141):
            x, y, z = self.obj_ball(obj)
            up = C.f2d(z)
            if C.dcmp(up, 0) < 0:
                up = C.dsub(0, up)
            up = C.dmul(C.dmul(up, self.u64(self.PB_DOUBLES[0])), self.u64(self.PB_DOUBLES[1]))
            velocity = (C.mul(x, 0x422B2BA5), C.mul(y, 0x422B2BA5), C.d2f(up))
            self.call('particle_spawn', self.PB_PARTICLES[2], self.vec(obj + 0x10), velocity, ZERO)


EXTERNALS.update({
    'Projectile_ctor': Ext(0x150E48, 'pvpi', 0, 'n', '(object, position, owner or 0, 0): a GameObject with an owner '
                           'handle at +0x4c'),
    'obj_moveAndCollide': Ext(0x1509F8, 'pv', 0, 'i', '(object, velocity per second) -> bit 1 terrain, bit 2 touch'),
    'poisonGasSpell_ctor': Ext(0x202DE8, 'pviiipi', 0, 'n', '(block, position, life in frames, radius, 0, owner, '
                               'poison value)'),
    'Creature_setEffectTimer': Ext(0x118950, 'pip', 1, 'n', '(creature, which, source; seconds)'),
})
SKILL_BODIES.update({0x30F168: (2, 'poisonbolt_cast'), 0x30F364: (5, 'skill_mana_cost')})
OBJECT_TABLES.add(PoisonBolt.PB_VT)
MODELLED.update({'SkillPoisonBolt_cast': 0x30F168, 'SkillPoisonBolt_manaCost': 0x30F364, 'PoisonBolt_ctor': 0x30F398,
                 'PoisonBolt_run': 0x30F800, 'PoisonBolt_onHit': 0x310028, 'PoisonBolt_burst': 0x3101CC})


class Roar:
    """76 - Roar (`roar`, berserker): the spell drives the player's shout animation; on its
    first event a wave starts at the mouth and for half a second hits what it reaches."""
    ROAR_VT = 0x51B2D0
    ROAR_NAMES = {0: 0x5517D8, 1: 0x551808, 2: 0x5517F8, 3: 0x551818, 7: 0x551828}
    ROAR_NAME_DEFAULT = 0x5517E8
    ROAR_LUMP, ROAR_SOUND = 0x551838, 0x551840
    ROAR_PARTICLES = {'gust': 0x8E6E20, 'breath': 0x8E6DD0, 'ring': 0x8E6E70, 'dust': 0x8E6EC0}
    STYLE_BYTE = 0x4A86                         # weapon-style byte of the player record
    REC_MANA, REC_MANA_MAX = 0xC0, 0xC4

    def roar_can_use(self, skill, caster):
        """SkillRoar_canUse 0x2fff64: 1 unless the caster carries a SpellRoar."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['Roar']) else 1

    def roar_cast(self, skill, level, caster, pos, facing):
        """SkillRoar_cast 0x2fff98: level through slot 14 (level, 0x14); pool_new(0x50); the
        constructor."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x50)
        if spell:
            self.roar_spell_ctor(spell, level, caster, skill)
        return spell

    def shout_animation(self, owner, names, default, events, flags):
        """What the three shout constructors share: the animation file is named by the
        weapon-style byte of record [owner +0x3c8] (NO is-player test), found in the lump
        the owner's class definition names, its event slots are written INTO THE FILE'S
        HEADER (slot i: seconds at +0x14 + 8i, mask byte at +0x18 + 8i), and it is started
        with a tenth of a second of blend each way."""
        style = self.s8(self.record(owner) + self.STYLE_BYTE)
        text = self.call('libc_sprintf', names.get(style, default), None)
        clip = self.call('res_find', self.u32(self.u32(owner + 0x24)), text)
        for slot, seconds, mask in events:
            self.w8(clip + 0x18 + 8 * slot, mask)
        for slot, seconds, mask in events:
            self.w32(clip + 0x14 + 8 * slot, seconds)
        self.call('anim_startBlendInOut', owner + 0x114, clip, flags, 0x3DCCCCCC, 0x3DCCCCCC)

    def roar_spell_ctor(self, spell, level, owner, skill):
        """SpellRoar_ctor 0x30016c.  The Spell base (ONE SHARED DRAW); owner +0x18; the
        owner's action state +0x58c = 6 (NO is-player test); clock +0x2c = 0, shout time
        +0x30 = -1, end time +0x34 = -1, animating +0x40 = 1; centre +0x20 = the owner's
        position; the shout animation with events 2 at 0.317 s and 4 at 1.236 s; a sound
        whose handle is kept at +0x3c."""
        w32 = self.w32
        self.spell_base(spell, level, owner, skill, self.ROAR_VT)
        w32(spell + 0x3C, M32)
        w32(spell + 0x18, owner)
        w32(spell + 0x34, MINUS_ONE)
        w32(spell + 0x40, 1)
        w32(owner + 0x58C, 6)
        for off in (0x1C, 0x2C, 0x48, 0x44, 0x4C):
            w32(spell + off, 0)
        w32(spell + 0x30, MINUS_ONE)
        self.wvec(spell + 0x20, self.vec(owner + 0x10))
        self.shout_animation(self.u32(spell + 0x18), self.ROAR_NAMES, self.ROAR_NAME_DEFAULT,
                             ((1, 0x3EA24DB1, 2), (2, 0x3F9E3443, 4)), 0x22)
        w32(spell + 0x3C, self.sound_at(self.ROAR_LUMP, self.ROAR_SOUND, self.vec(spell + 0x20)))

    def shout_interrupted(self, spell, owner, sound_at=None):
        """The refund when something else took the player over before the effect started:
        mana += slot 5 (level) x 0.5, up to the maximum, on record [owner +0x3c8]."""
        rec = self.record(owner)
        cost = self.skill_call(self.u32(spell + 8), 5, self.s8(spell))
        mana = C.add(self.u32(rec + self.REC_MANA), C.mul(cost, HALF))
        self.w32(rec + self.REC_MANA, mana)
        if C.lt(self.u32(rec + self.REC_MANA_MAX), mana):
            self.w32(rec + self.REC_MANA, self.u32(rec + self.REC_MANA_MAX))
        if sound_at is not None:
            self.call('sound_stop', self.u32(spell + sound_at))

    def _roar_breath(self, spell, facing, mouth, definition, speed, centred):
        """One mouth particle: ONE OWN DRAW for the angle around the facing."""
        share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
        if centred:
            share = C.sub(C.add(share, share), ONE)
        angle = facing + C.to_int(C.mul(share, 0x45753000))
        cosine, sine = C.cos16(angle), C.sin16(angle)
        point = (C.add(mouth[0], C.mul(cosine, 0x40F891C0)), C.add(mouth[1], C.mul(sine, 0x40F891C0)), mouth[2])
        self.call('particle_spawn', definition, point, (C.mul(cosine, speed), C.mul(sine, speed), ZERO), ZERO)

    def roar_spell_run(self, spell, pos, facing):
        """SpellRoar_run 0x3003d8 (spell, position, facing), once per frame of the owner.

          - net game and net_isLocalSlot(owner slot): the force-rebase byte = 1 (per machine)
          - animating (+0x40) and the owner's action state +0x58c is no longer 6: animating
            = 0 and, if the shout has not happened (shout time < 0): the half refund, the
            sound stops, interrupted +0x44 = 1, end time = clock + 0.5
          - still animating: ev = Player_animStep(owner; 1.0).  Without flag 0x20 in the
            owner's animation flags +0x11a: animating = 0, action state = 2.  Else
              ev == 2: shouting +0x48 = 1, shout time = clock, camera_shake(level x 0.5 +
                  3.5), centre = body-model attach point 7, ground height +0x38 =
                  terrain_height(centre; 6), in water +0x4c = water_test(centre; 8), and the
                  candidate list +0x1c = everything without object flags 0xd that
                  world_collectInSphere(centre; slot 10 (0, level) x 12 x 1.5) returns
              ev == 4: shouting = 0
              shouting: mouth particles - an OWN draw below 0.063 gives one (another own
                  draw), an own draw below 0.171 gives a second (another)
          - not interrupted and shout time >= 0: f = (clock - shout time) x 2; while f <= 1
            the wave: hit ring with r = f x 12 x slot 10 (0, level), 277 (370 from level 10)
            ring particles of one OWN draw each, 9 (12) more with a ball point as well, and
            on the frame of the shout over water, water_disturb; after that end time = clock
          - interrupted: one mouth particle with chance 0.171 (two own draws)
          - not animating: while clock < end time (>= 0) just the clock; else the action
            state goes back from 6 to 2 (unless interrupted) and the spell destroys itself
          - clock +0x2c += 1/60; above 6.0 the spell destroys itself."""
        u32, w32 = self.u32, self.w32
        facing = s16(facing)
        owner = u32(spell + 0x18)
        if self.s8(G_NETWORK_MODE) and self.call('net_isLocalSlot', u32(owner + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 1)
        skip_wave = False
        if u32(spell + 0x40):
            if u32(u32(spell + 0x18) + 0x58C) != 6:
                w32(spell + 0x40, 0)
                if C.lt(u32(spell + 0x30), ZERO):
                    self.shout_interrupted(spell, u32(spell + 0x18), 0x3C)
                    w32(spell + 0x44, 1)
                    w32(spell + 0x34, C.add(u32(spell + 0x2C), HALF))
            if u32(spell + 0x40):
                owner = u32(spell + 0x18)
                event = s32(self.call('Player_animStep', owner, ONE))
                if not self.u16(u32(spell + 0x18) + 0x11A) & 0x20:
                    w32(spell + 0x40, 0)
                    w32(u32(spell + 0x18) + 0x58C, 2)
                else:
                    if event == 2:
                        w32(spell + 0x48, 1)
                        w32(spell + 0x30, u32(spell + 0x2C))
                        self.call('camera_shake', 0, C.add(C.mul(C.from_int(self.s8(spell)), HALF), 0x40600000))
                        owner = u32(spell + 0x18)
                        mouth = self.attach_point(owner, 7)
                        for k in range(3):
                            self.callee_store(spell + 0x20 + 4 * k, 4, mouth[k])
                        centre = self.vec(spell + 0x20)
                        ground = self.call('terrain_height', u32(G_WORLD), centre, 0x40C00000)
                        w32(spell + 0x38, ground)
                        wet = self.call('water_test', u32(G_WORLD), (centre[0], centre[1], ground), 0, 0x41000000)
                        w32(spell + 0x4C, 1 if wet else 0)
                        steps = C.from_int(s32(self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))))
                        found = self.call('world_collectInSphere', self.vec(spell + 0x20),
                                          self.s16(u32(spell + 0x18) + 0x38), C.mul(C.mul(steps, F_12), 0x3FC00000))
                        for obj in found or ():
                            if obj and not u32(obj + 0xC) & 0xD:
                                self.handle_link(spell + 0x1C, obj, obj)
                        self.handle_clear('stack')
                    if event == 4:
                        w32(spell + 0x48, 0)
                    if u32(spell + 0x48):
                        mouth = self.attach_point(u32(spell + 0x18), 7)
                        if C.lt(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0x3D81059E):
                            self._roar_breath(spell, facing, mouth, self.ROAR_PARTICLES['gust'], 0x418FCA03, False)
                        if C.le(0x3E2F1737, C.mul(C.from_int(self.spell_rand(spell)), F_2M16)):
                            skip_wave = False
                        else:
                            self._roar_breath(spell, facing, mouth, self.ROAR_PARTICLES['breath'], 0x4129B986, True)
        if not u32(spell + 0x44):
            if C.le(ZERO, u32(spell + 0x30)):
                grown = C.sub(u32(spell + 0x2C), u32(spell + 0x30))
                grown = C.add(grown, grown)
                if C.le(grown, ONE):
                    level = self.s8(spell)
                    steps = C.from_int(s32(self.skill_call(u32(spell + 8), 10, 0, level)))
                    ring = C.mul(C.mul(grown, F_12), steps)
                    self.roar_hit_ring(spell, ring)
                    height = C.add(u32(spell + 0x28), 0x398F2170)
                    for _ in range(0x172 if self.s8(spell) > 9 else 0x115):
                        angle = self.spell_rand(spell)
                        point = (C.add(u32(spell + 0x20), C.mul(C.cos16(angle), ring)),
                                 C.add(u32(spell + 0x24), C.mul(C.sin16(angle), ring)), height)
                        self.call('particle_spawn', self.ROAR_PARTICLES['ring'], point,
                                  (0x3F57582B, 0x3F57582B, 0x4106971B), ZERO)
                    for _ in range(12 if self.s8(spell) > 9 else 9):
                        angle = self.spell_rand(spell)
                        point = (C.add(u32(spell + 0x20), C.mul(C.cos16(angle), ring)),
                                 C.add(u32(spell + 0x24), C.mul(C.sin16(angle), ring)), height)
                        x, y, z = self.spell_ball(spell)
                        self.call('particle_spawn', self.ROAR_PARTICLES['dust'], point,
                                  (C.mul(x, 0x40800000), C.mul(y, 0x40800000), C.mul(z, 0x40800000)), ZERO)
                    if u32(spell + 0x4C) and C.eq(u32(spell + 0x2C), u32(spell + 0x30)):
                        self.call('water_disturb', u32(G_WORLD), (u32(spell + 0x20), u32(spell + 0x24), u32(spell + 0x38)),
                                  0x455AC000, F_36)
                else:
                    w32(spell + 0x34, u32(spell + 0x2C))
        else:
            mouth = self.attach_point(u32(spell + 0x18), 7)
            if C.lt(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0x3E2F1737):
                self._roar_breath(spell, facing, mouth, self.ROAR_PARTICLES['dust'], 0x4129B986, True)
        if not u32(spell + 0x40):
            if not (C.le(ZERO, u32(spell + 0x34)) and C.lt(u32(spell + 0x2C), u32(spell + 0x34))):
                if not u32(spell + 0x44) and u32(u32(spell + 0x18) + 0x58C) == 6:
                    w32(u32(spell + 0x18) + 0x58C, 2)
                if spell:
                    self.spell_destroy(spell)
                return
        clock = C.add(u32(spell + 0x2C), DT)
        w32(spell + 0x2C, clock)
        if C.lt(0x40C00000, clock) and spell:
            self.spell_destroy(spell)

    def roar_hit_ring(self, spell, ring):
        """SpellRoar_hitRing 0x300f54 (spell; radius): the candidate list in order.  Gone:
        dropped.  Reached (sqrt(dx*dx + dy*dy) - radius <= ring): a creature with object
        flags 9 or not an enemy of the owner (slot 20) is dropped; anything else - objects
        that are not creatures without any test - gets damage_apply(object, owner, 100000,
        0, 0, flags, none, 0; slot 8 (1, level, 0; 0.2)) with flags 0x80940 below level 5,
        0x100940 to 9, 0x200940 from 10, and is dropped."""
        u32 = self.u32
        for node, obj in self.handle_items(spell + 0x1C):
            if not obj:
                self.handle_remove(node)
                continue
            dy = C.sub(u32(spell + 0x24), u32(obj + 0x14))
            dx = C.sub(u32(spell + 0x20), u32(obj + 0x10))
            if not C.le(C.sub(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), u32(obj + 0x1C)), ring):
                continue
            if u32(obj + 0xC) & 0x20:
                if u32(obj + 0xC) & 9 or not self.vcall(u32(spell + 0x18), 20, obj):
                    self.handle_remove(node)
                    continue
            level = self.s8(spell)
            low, high = self.skill_call(u32(spell + 8), 8, 1, level, 0, F_0_2)
            flags = 0x200940 if level >= 10 else 0x100940 if level >= 5 else 0x80940
            self.call('damage_apply', obj, u32(spell + 0x18), 100000, 0, 0, flags, 0, 0,
                      C.from_int(s32(low)), C.from_int(s32(high)))
            self.handle_remove(node)


SKILL_BODIES.update({0x2FFF64: (1, 'roar_can_use'), 0x2FFF98: (2, 'roar_cast'), 0x300138: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x3003D8: (2, 'roar_spell_run')})
SPELL_TABLES.add(Roar.ROAR_VT)
MODELLED.update({'SkillRoar_canUse': 0x2FFF64, 'SkillRoar_cast': 0x2FFF98, 'SkillRoar_manaCost': 0x300138,
                 'SpellRoar_ctor': 0x30016C, 'SpellRoar_run': 0x3003D8, 'SpellRoar_hitRing': 0x300F54})


class BattleCry:
    """77 - Battle Cry (`battlecry`, berserker): a shout that, at its third animation
    event, may stun each enemy around - the roll comes from the spell's OWN generator,
    behind that frame's particle draws - and for its duration speeds up the swings of the
    caster and of allies inside its aura."""
    BC_VT = 0x51B388
    BC_NAMES = {0: 0x551930, 1: 0x551978, 2: 0x551960, 3: 0x551990, 7: 0x5519A0}
    BC_NAME_DEFAULT = 0x551948
    BC_LUMP, BC_SOUND = 0x5519B8, 0x5519C0
    BC_PARTICLES = {'streamer': 0x8E6F60, 'late': 0x8E7000, 'burst': 0x8E7050, 'ring': 0x8E6FB0}
    BC_AURA_MIN = 0x4219B1E4                    # 38.42372

    def battlecry_can_use(self, skill, caster):
        """SkillBattleCry_canUse 0x301464: 1 unless the caster carries a SpellBattleCry."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['BattleCry']) else 1

    def battlecry_cast(self, skill, level, caster, pos, facing):
        """SkillBattleCry_cast 0x301498: level through slot 14 (level, 5); pool_new(0x58);
        the constructor."""
        level = self.skill_call(skill, 14, level, 5)
        spell = self.call('pool_new', 0x58)
        if spell:
            self.battlecry_spell_ctor(spell, level, caster, skill)
        return spell

    def battlecry_spell_ctor(self, spell, level, owner, skill):
        """SpellBattleCry_ctor 0x301714.  The Spell base (ONE SHARED DRAW); cry time +0x24 =
        -1, aura radius +0x28 = -1, clock +0x1c = 0, end time +0x20 = (float) slot 10 (2,
        level), animating +0x30 = 1, streamers +0x34 = 0, interrupted +0x38 = 0, owner
        +0x18; the owner's action state +0x58c = 6 (NO is-player test); the shout animation
        with events 2 at 0.101 s, 4 at 2.351 s and 8 at 1.178 s; a sound (handle +0x2c);
        the two hand points (body-model attach points 0 and 1) at +0x40 and +0x4c."""
        w32 = self.w32
        self.spell_base(spell, level, owner, skill, self.BC_VT)
        w32(spell + 0x28, MINUS_ONE)
        w32(spell + 0x24, MINUS_ONE)
        w32(spell + 0x1C, 0)
        seconds = s32(self.skill_call(skill, 10, 2, s8(level)))
        w32(spell + 0x30, 1)
        w32(owner + 0x58C, 6)
        w32(spell + 0x20, C.from_int(seconds))
        w32(spell + 0x34, 0)
        w32(spell + 0x38, 0)
        w32(spell + 0x18, owner)
        self.shout_animation(self.u32(spell + 0x18), self.BC_NAMES, self.BC_NAME_DEFAULT,
                             ((1, 0x3DCEDA22, 2), (3, 0x3F96C83E, 8), (2, 0x401675EE, 4)), 0x22)
        owner = self.u32(spell + 0x18)
        w32(spell + 0x2C, self.sound_at(self.BC_LUMP, self.BC_SOUND, self.vec(owner + 0x10)))
        for index, at in ((0, 0x40), (1, 0x4C)):
            hand = self.attach_point(self.u32(spell + 0x18), index)
            for k in range(3):
                self.callee_store(spell + at + 4 * k, 4, hand[k])

    def _battlecry_streamers(self, spell, definition):
        """Twenty particles between where the hands were and where they are: per pair two
        ball points and two more OWN draws."""
        u32 = self.u32
        owner = u32(spell + 0x18)
        hand_0 = self.attach_point(owner, 0)
        hand_1 = self.attach_point(u32(spell + 0x18), 1)
        if definition is not None:
            moved_0 = tuple(C.sub(hand_0[k], u32(spell + 0x40 + 4 * k)) for k in range(3))
            moved_1 = tuple(C.sub(hand_1[k], u32(spell + 0x4C + 4 * k)) for k in range(3))
            for _ in range(10):
                first = self.spell_ball(spell)
                second = self.spell_ball(spell)
                first = tuple(C.add(v, v) for v in first)
                second = tuple(C.add(v, v) for v in second)
                share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
                point_0 = tuple(C.add(C.add(hand_0[k], second[k]), C.mul(moved_0[k], share)) for k in range(3))
                share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
                point_1 = tuple(C.add(C.add(hand_1[k], first[k]), C.mul(moved_1[k], share)) for k in range(3))
                self.call('particle_spawn', definition, point_0, first, ZERO)
                self.call('particle_spawn', definition, point_1, second, ZERO)
        self.wvec(spell + 0x40, hand_0)
        self.wvec(spell + 0x4C, hand_1)

    def battlecry_set_tint(self, spell, creature):
        """SpellBattleCry_setTint 0x302bd0: both flash quads = (0x5c, 0x21, 0x0f, 0x23)."""
        self.flash(creature, 1, 0x5C, 0x21, 0xF, 0x23)
        self.flash(creature, 2, 0x5C, 0x21, 0xF, 0x23)

    def battlecry_spell_run(self, spell, pos, facing=0):
        """SpellBattleCry_run 0x301a34 (spell, position), once per frame of the owner.

          - clock +0x1c += 1/60; the per-machine force-rebase byte as in Roar
          - animating and the owner's action state is no longer 6: animating = 0, streamers
            = 0 and, before the cry, the half refund, the sound stops, interrupted +0x38 =
            1, END TIME = clock + 0.5
          - still animating: ev = Player_animStep(owner; 1.0); without animation flag 0x20
            animating = 0 and action state = 2; else ev == 2 streamers on, ev == 4 off,
            ev == 8 cry time +0x24 = clock and a particle group (+0x3c); then the hand
            streamers (when on) and the two hand points are stored
          - end time +0x20 <= clock: the action state goes back from 6 to 2 (unless
            interrupted) and the spell destroys itself
          - otherwise: an interrupted spell lays streamers of a second kind; and from the
            cry on (cry time >= 0): g = min(1, (clock - cry time) x 2.000012); aura radius
            +0x28 = 38.42, or (R - 38.42) x g + 38.42 when R = slot 10 (3, level) x 12
            exceeds 3.2; level + 13 ground particles (four times that while g < 1), ONE OWN
            DRAW each, placed around net_objOrGhost(owner) and dropped unless the ground
            there is within 72 of it; the owner and every other player of the alive list
            within the aura in 3-D (same team only in PvP mode A, slot 22) get the tint
          - on the frame of the cry (cry time == clock): a LightEffect 36 above `pos`
            following the owner; world_collectObjectsInBox(pos -/+ R, capacity 512) and for
            every creature in it that the owner's slot 20 calls an enemy, within R + its
            radius of `pos` in 3-D and with hit points >= 0: ONE OWN DRAW d, and d % 100 <
            slot 10 (0, level) stuns it (slot 30) for trunc(slot 10 (2, level) x 19.979939)
            frames with the flash."""
        u32, w32 = self.u32, self.w32
        clock = C.add(u32(spell + 0x1C), DT)
        w32(spell + 0x1C, clock)
        if self.s8(G_NETWORK_MODE) and self.call('net_isLocalSlot', u32(u32(spell + 0x18) + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 1)
        if u32(spell + 0x30):
            if u32(u32(spell + 0x18) + 0x58C) != 6:
                w32(spell + 0x30, 0)
                w32(spell + 0x34, 0)
                if C.lt(u32(spell + 0x24), ZERO):
                    self.shout_interrupted(spell, u32(spell + 0x18), 0x2C)
                    w32(spell + 0x38, 1)
                    w32(spell + 0x20, C.add(u32(spell + 0x1C), HALF))
            if u32(spell + 0x30):
                event = s32(self.call('Player_animStep', u32(spell + 0x18), ONE))
                if not self.u16(u32(spell + 0x18) + 0x11A) & 0x20:
                    w32(spell + 0x30, 0)
                    w32(u32(spell + 0x18) + 0x58C, 2)
                else:
                    if event == 2:
                        w32(spell + 0x34, 1)
                    if event == 4:
                        w32(spell + 0x34, 0)
                    if event == 8:
                        w32(spell + 0x24, u32(spell + 0x1C))
                        w32(spell + 0x3C, self.call('particleGroup_create'))
                    self._battlecry_streamers(spell, self.BC_PARTICLES['streamer'] if u32(spell + 0x34) else None)
        if C.le(u32(spell + 0x20), u32(spell + 0x1C)):
            if not u32(spell + 0x38) and u32(u32(spell + 0x18) + 0x58C) == 6:
                w32(u32(spell + 0x18) + 0x58C, 2)
            if spell:
                self.spell_destroy(spell)
            return
        if u32(spell + 0x38):
            self._battlecry_streamers(spell, self.BC_PARTICLES['late'])
        if C.le(ZERO, u32(spell + 0x24)):
            grown = C.mul(C.sub(u32(spell + 0x1C), u32(spell + 0x24)), 0x40000032)
            share = grown if C.le(grown, ONE) else ONE
            reach = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 3, self.s8(spell)))), F_12)
            w32(spell + 0x28, self.BC_AURA_MIN)
            if C.lt(0x404CED30, reach):
                w32(spell + 0x28, C.add(C.mul(C.sub(reach, self.BC_AURA_MIN), share), self.BC_AURA_MIN))
            count = self.s8(spell) + 0xD
            lift = C.mul(C.sub(ONE, C.mul(share, share)), 0x428C0000)
            ghost = self.call('net_objOrGhost', u32(spell + 0x18))
            matrix = C.mat34_set_pos_rot_z(self.vec(ghost + 0x10), s16(u32(G_SIM_FRAME) * 61))
            self.call('particleGroup_begin', u32(spell + 0x3C))
            self.call('particleGroup_setMatrix', u32(spell + 0x3C), 'stack')
            if C.lt(share, ONE):
                count *= 4
                definition, velocity = self.BC_PARTICLES['burst'], (ZERO, ZERO, ZERO)
            else:
                definition, velocity = self.BC_PARTICLES['ring'], (ZERO, ZERO, ONE)
            for _ in range(max(count, 0)):
                angle = self.spell_rand(spell)
                local = (C.mul(C.cos16(angle), u32(spell + 0x28)), C.mul(C.sin16(angle), u32(spell + 0x28)), ZERO)
                world = C.mat34_transform_point(matrix, local)
                drop = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(ghost + 0x18))
                if C.le(drop, 0x42900000) and C.le(0xC2900000, drop):
                    self.call('particle_spawn', definition, (local[0], local[1], C.add(drop, lift)), velocity, ZERO)
            self.call('particleGroup_end', u32(spell + 0x3C))
            self.battlecry_set_tint(spell, u32(spell + 0x18))
            radius = u32(spell + 0x28)
            for index in range(max(self.s32(G_ALIVE_COUNT), 0)):
                other = self.player_obj(u32(G_ALIVE_LIST + 4 * index))
                owner = u32(spell + 0x18)
                if not other or other == owner:
                    continue
                if self.s32(G_PVP_MODE_A) and not self.vcall(owner, 22, other):
                    continue
                owner = u32(spell + 0x18)
                gap = [C.sub(u32(owner + 0x10 + 4 * k), u32(other + 0x10 + 4 * k)) for k in range(3)]
                if C.le(C.add(C.add(C.mul(gap[0], gap[0]), C.mul(gap[1], gap[1])), C.mul(gap[2], gap[2])),
                        C.mul(radius, radius)):
                    self.battlecry_set_tint(spell, other)
        if C.eq(u32(spell + 0x24), u32(spell + 0x1C)):
            block = self.call('pool_new', 0xBC)
            if block:
                self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), u32(spell + 0x18),
                                  (0x437F0000, 0x42B80000, 0x42480000, 0xC2C00000), (0x42F00000, 0x43340000, ZERO, TWO))
            reach = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 3, self.s8(spell)))), F_12)
            found = self.call('world_collectObjectsInBox', tuple(C.sub(v, reach) for v in pos),
                              tuple(C.add(v, reach) for v in pos), 0x200)
            for obj in found or ():
                if not u32(obj + 0xC) & 0x20 or not self.vcall(u32(spell + 0x18), 20, obj):
                    continue
                gap = [C.sub(pos[k], u32(obj + 0x10 + 4 * k)) for k in range(3)]
                far = C.sqrt(C.add(C.add(C.mul(gap[0], gap[0]), C.mul(gap[1], gap[1])), C.mul(gap[2], gap[2])))
                if not C.le(far, C.add(reach, u32(obj + 0x1C))) or not C.le(ZERO, u32(obj + 0x228)):
                    continue
                roll = self.spell_rand(spell) % 100
                if (roll & 0xFFFF) < s32(self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))):
                    seconds = C.from_int(s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell))))
                    self.vcall(obj, 30, C.to_int(C.mul(seconds, 0x419FD6EA)), 1)

    def battlecry_affects(self, spell, creature, want_fraction=1):
        """SpellBattleCry_affects 0x302c04 (spell, creature, fraction out) -> (covered,
        fraction).  fraction = slot 10 (1, level) x 0.01, stored when the pointer is given.
        Covered: the owner (+0xc) always; anyone else only when PvP mode A is off or the
        owner's slot 22 accepts it, the cry has happened, and it is within the aura radius
        of the owner (+0x18) in 3-D.  Player_run's swing-speed code asks this."""
        u32 = self.u32
        fraction = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))), F_0_01)
        covered = 0
        if creature:
            owner = u32(spell + 0xC)
            covered = 1
            if creature != owner:
                covered = 0
                if not self.s32(G_PVP_MODE_A) or self.vcall(owner, 22, creature):
                    if C.le(ZERO, u32(spell + 0x24)):
                        owner = u32(spell + 0x18)
                        gap = [C.sub(u32(owner + 0x10 + 4 * k), u32(creature + 0x10 + 4 * k)) for k in range(3)]
                        covered = 1
                        if C.lt(C.mul(u32(spell + 0x28), u32(spell + 0x28)),
                                C.add(C.add(C.mul(gap[0], gap[0]), C.mul(gap[1], gap[1])), C.mul(gap[2], gap[2]))):
                            covered = 0
        return covered, fraction


G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440        # g_alivePlayerCount, g_alivePlayers (slots)
EXTERNALS.update({
    'terrain_heightAtPoint': Ext(0x182F28, 'pv', 0, 'f', '(world, point) -> ground height'),
})
SKILL_BODIES.update({0x301464: (1, 'battlecry_can_use'), 0x301498: (2, 'battlecry_cast'),
                     0x3016E0: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x301A34: (2, 'battlecry_spell_run')})
SPELL_TABLES.add(BattleCry.BC_VT)
MODELLED.update({'SkillBattleCry_canUse': 0x301464, 'SkillBattleCry_cast': 0x301498,
                 'SkillBattleCry_manaCost': 0x3016E0, 'SpellBattleCry_ctor': 0x301714, 'SpellBattleCry_run': 0x301A34,
                 'SpellBattleCry_setTint': 0x302BD0, 'SpellBattleCry_affects': 0x302C04,
                 'mat34_setPosRotZ': 0x163B30, 'mat34_transformPoint': 0x1660A0})


class Passives:
    """The six passives - 71 Berserker Rage, 73 Axe Bandolier, 74 Light Quiver, 79 Throwing,
    92 Battle Mage, 93 Penetrating Arrows: kind 3, never cast (the default can-use, cast
    and mana cost), no spell.  Each is a statistic table and one or two helpers that code
    in the player and object areas calls with the player's rank.  All lookups are slot 10,
    so rank 0 gives 0.  The callers - Player_run's swing speed, Player_recalcDamage (the
    thrown-weapon maximum, the Battle Mage range), player_itemWeight, MissileWeapon_onTouch
    - belong to tools/ref_player.py, tools/ref_combat.py and tools/ref_objects.py."""
    REC_HP, REC_HP_MAX, REC_OBJECT = 0xAC, 0xB0, 0x43D8

    def _rage(self, skill, rank, record, frames, stat, flash):
        level = self.skill_call(skill, 14, rank, 0x14)
        if not C.le(C.div(self.u32(record + self.REC_HP), self.u32(record + self.REC_HP_MAX)), HALF):
            return ONE
        ramp = C.mul(C.from_int(s32(frames)), DT)
        if C.lt(ONE, ramp):
            ramp = ONE
        obj = self.u32(record + self.REC_OBJECT)
        if flash and obj:
            self.w16(obj + 0x9E, 0)
            self.w16(obj + 0x92, 0)
            self.w16(obj + 0x94, 0)
            self.w16(obj + 0x98, C.to_int(C.mul(ramp, 0x42800000)))
            self.w16(obj + 0x9C, C.to_int(C.mul(ramp, 0x41800000)))
            self.w16(obj + 0x90, C.to_int(C.mul(ramp, 0x42C00000)))
            self.w16(obj + 0x96, C.to_int(C.mul(ramp, 0x41700000)))
            self.w16(obj + 0x9A, C.to_int(C.mul(ramp, 0x41800000)))
        value = C.from_int(s32(self.skill_call(skill, 10, stat, level)))
        return C.add(C.mul(C.mul(value, F_0_01), ramp), ONE)

    def berserkerrage_swing_factor(self, skill, rank, record, frames):
        """SkillBerserkerRage_swingFactor 0x2fe324 (skill, rank, player record, frames) ->
        1.0 while record hp / max hp > 0.5; else 1 + slot 10 (0, rank) x 0.01 x t with t =
        min(1, frames x (1/60)), and the record's player object (+0x43d8, if any) gets its
        flash quads from t: +0x90 = t x 96, +0x96 = t x 15, +0x98 = t x 64, +0x9a = +0x9c =
        t x 16 (truncated), +0x92 = +0x94 = +0x9e = 0."""
        return self._rage(skill, rank, record, frames, 0, True)

    def berserkerrage_damage_factor(self, skill, rank, record, frames):
        """SkillBerserkerRage_damageFactor 0x2fe49c: the same with statistic 1, no flash."""
        return self._rage(skill, rank, record, frames, 1, False)

    def passive_complement(self, skill, rank):
        """SkillAxeBandolier_getStat0Complement 0x2ff2e4 and SkillLightQuiver_... 0x2ff4b4
        (skill, rank) -> max(0, 1 - slot 10 (0, rank) x 0.01): the weight factor of thrown
        axes / of ammunition."""
        level = self.skill_call(skill, 14, rank, 2)
        left = C.sub(ONE, C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), F_0_01))
        return ZERO if C.lt(left, ZERO) else left

    def throwing_fraction(self, skill, rank):
        """SkillThrowing_getStat0Fraction 0x304b54 (skill, rank) -> slot 10 (0, rank) x 0.01."""
        level = self.skill_call(skill, 14, rank, 2)
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), F_0_01)

    def battlemage_fraction(self, skill, rank):
        """SkillBattleMage_getStat0Fraction 0x314a78 (skill, rank) -> slot 10 (0, rank) x 0.01;
        0 at rank 0, and Player_recalcDamage REPLACES an eligible weapon's range by that
        share of itself."""
        level = self.skill_call(skill, 14, rank, 1)
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), F_0_01)

    def penetratingarrows_fractions(self, skill, rank):
        """SkillPenetratingArrows_getStats01Fraction 0x314c88 (skill, out 0, out 1, rank) ->
        (slot 10 (0, rank) x 0.01, slot 10 (1, rank) x 0.01): the chances that an arrow
        cannot be blocked and that it flies on."""
        first = C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, rank))), F_0_01)
        second = C.mul(C.from_int(s32(self.skill_call(skill, 10, 1, rank))), F_0_01)
        return first, second


MODELLED.update({'SkillBerserkerRage_swingFactor': 0x2FE324, 'SkillBerserkerRage_damageFactor': 0x2FE49C,
                 'SkillAxeBandolier_getStat0Complement': 0x2FF2E4, 'SkillLightQuiver_getStat0Complement': 0x2FF4B4,
                 'SkillThrowing_getStat0Fraction': 0x304B54, 'SkillBattleMage_getStat0Fraction': 0x314A78,
                 'SkillPenetratingArrows_getStats01Fraction': 0x314C88})


class DiseaseBlade:
    """97 - Disease Blade (`diseaseblade`, shadowknight; Bubo casts it on its allies): a
    timed disease modifier on the caster's weapons, refreshed onto nearby players'
    weapons from rank 5; on a monster a switch of the weapon holder's element."""
    DB_VT = 0x51C4A0
    DB_LUMP, DB_SOUND = 0x553120, 0x553128
    REC_WEAPON_SETS, REC_SECOND_WEAPON, REC_ACTIVE_SET = 0x4434, 0x443C, 0x4A7C

    def diseaseblade_can_use(self, skill, caster):
        """SkillDiseaseBlade_canUse 0x318730: 1 unless the caster carries a SpellDiseaseBlade."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['DiseaseBlade']) else 1

    def diseaseblade_cast(self, skill, level, caster, pos, facing):
        """SkillDiseaseBlade_cast 0x318764: level through slot 14 (level, 1); pool_new(0x24);
        the constructor."""
        level = self.skill_call(skill, 14, level, 1)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.diseaseblade_spell_ctor(spell, level, caster, skill)
        return spell

    def player_weapons(self, player):
        """The two item records a weapon buff writes: the primary weapon of the active set
        (record +0x4434 + 4 x the byte at +0x4a7c) and the second weapon (+0x443c)."""
        rec = self.record(player)
        return (self.u32(rec + self.REC_WEAPON_SETS + 4 * self.s8(rec + self.REC_ACTIVE_SET)),
                self.u32(rec + self.REC_SECOND_WEAPON))

    def write_disease(self, item, value, frames, limit):
        """The block that appears four times in this class (0x318c70, 0x318de8 and twice in
        the run): give an item record a disease modifier (code 0x26) of `value` for
        `frames` frames.  Nothing for a null item or one with item flag bit 24.  With old =
        the first 0x26 slot's FIRST VALUE (0 without one): nothing unless 0 <= old < limit
        - the old VALUE compared with a frame count - and old <= value.  Then the first
        slot that is empty or already 0x26 becomes (0x26, value, round(value + value x
        0.19999999), frames)."""
        value = s32(value)
        if not item or self.u64(item + 8) & 0x1000000:
            return
        old = 0
        for k in range(4):
            if self.s16(item + 0x24 + 8 * k) == 0x26:
                old = self.s16(item + 0x26 + 8 * k)
                break
        if not 0 <= old < limit or not old <= value:
            return
        top = self._round(C.add(C.from_int(value), C.mul(C.from_int(value), F_0_2)))
        for k in range(4):
            if self.s16(item + 0x24 + 8 * k) in (-1, 0x26):
                self.w16(item + 0x24 + 8 * k, 0x26)
                self.w16(item + 0x26 + 8 * k, value)
                self.w16(item + 0x28 + 8 * k, top)
                self.w16(item + 0x2A + 8 * k, frames)
                break

    def diseaseblade_spell_ctor(self, spell, level, caster, skill):
        """SpellDiseaseBlade_ctor 0x318ad4.  The Spell base (ONE SHARED DRAW); expiry frame
        +0x18 = frame + slot 12 (1, level, caster, cap 20) x 60; +0x1c = frame + 30 (never
        read); aura radius +0x20 = slot 10 (2, level) x 12 (tier 1 for every caster).  value
        = slot 12 (0, level, caster, 0), frames = slot 12 (1, ..., 20) x 60.  A caster that
        is not a player: its weapon holder's slot 7 with hand 1, if it has a holder (that
        builds a disease element: one shared draw inside the callee).  A player: both
        weapons get write_disease(value, frames, limit = frames).  Then a LightEffect at
        the caster, flash quad 2 = (0x80, 0x80, 0, 0x1e), a sound."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, self.DB_VT)
        seconds = s32(self.skill_call(skill, 12, 1, s8(level), caster, 0x14))
        frame = u32(G_SIM_FRAME)
        w32(spell + 0x18, frame + seconds * 0x3C)
        w32(spell + 0x1C, frame + 0x1E)
        w32(spell + 0x20, C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))), F_12))
        value = s32(self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), u32(spell + 0xC), 0))
        frames = s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), u32(spell + 0xC), 0x14)) * 0x3C
        owner = u32(spell + 0xC)
        if not u32(owner + 0xC) & 0x40:
            holder = u32(owner + 0x50)
            if holder:
                self.holder_call(holder, 7, 1)
        else:
            for item in self.player_weapons(owner):
                self.write_disease(item, value, frames, frames)
        block = self.call('pool_new', 0xBC)
        if block:
            half = 0x43000000
            self.light_effect(block, self.vec(u32(spell + 0xC) + 0x10), 0, (half, half, ZERO, half),
                              (0x42DC0000, ZERO, 0x3F199999, HALF), 0, (half, 0x42E00000, ZERO, half))
        owner = u32(spell + 0xC)
        self.w16(owner + 0x9E, 0x1E)
        self.w16(owner + 0x9A, 0x80)
        self.w16(owner + 0x98, 0x80)
        self.w16(owner + 0x9C, 0)
        self.sound_at(self.DB_LUMP, self.DB_SOUND, self.vec(u32(spell + 0xC) + 0x10))

    def diseaseblade_spell_run(self, spell, pos, facing=0):
        """SpellDiseaseBlade_run 0x319068 (spell, position), once per frame of the owner.

        Before the expiry frame: with an aura radius that is not 0, a player owner and
        frame % 30 == 0: world_collectObjectsInBox(pos -/+ R on three axes, capacity 64)
        and, for every other player in it (in PvP mode A only one the owner's slot 22
        accepts): v = slot 12 (3, level, owner, 0) and write_disease(v, 31, limit 31) on
        both of its weapons.  From the expiry frame: an owner that is a creature and not a
        player has its weapon holder's slot 8 called with (1, 0), and the spell destroys
        itself.  The caster's own modifier just counts down in the item."""
        u32 = self.u32
        frame = s32(u32(G_SIM_FRAME))
        if frame < self.s32(spell + 0x18):
            reach = u32(spell + 0x20)
            if not C.eq(reach, ZERO) and u32(u32(spell + 0xC) + 0xC) & 0x40 and c_rem(frame, 30) == 0:
                found = self.call('world_collectObjectsInBox', tuple(C.sub(v, reach) for v in pos),
                                  tuple(C.add(v, reach) for v in pos), 0x40)
                owner = u32(spell + 0xC)
                for other in found or ():
                    if owner == other or not u32(other + 0xC) & 0x40:
                        continue
                    if self.s32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, other):
                        continue
                    first, second = self.player_weapons(other)
                    value = self.skill_call(u32(spell + 8), 12, 3, self.s8(spell), u32(spell + 0xC), 0)
                    self.write_disease(first, value, 0x1F, 0x1F)
                    self.write_disease(second, value, 0x1F, 0x1F)
            return
        owner = u32(spell + 0xC)
        if u32(owner + 0xC) & 0x60 == 0x20 and u32(owner + 0x50):
            self.holder_call(u32(owner + 0x50), 8, 1, 0)
        if spell:
            self.spell_destroy(spell)


EXTERNALS.update({
    'Holder.v7': Ext(0, 'pi', 0, 'n', '(hand): the hand\'s element becomes disease (creature_buildElementDamage; '
                     'one shared draw inside)'),
    'Holder.v8': Ext(0, 'pii', 0, 'n', '(hand, 0): the hand\'s element is cleared'),
})
SKILL_BODIES.update({0x318730: (1, 'diseaseblade_can_use'), 0x318764: (2, 'diseaseblade_cast'),
                     0x318AA0: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x319068: (2, 'diseaseblade_spell_run')})
SPELL_TABLES.add(DiseaseBlade.DB_VT)
MODELLED.update({'SkillDiseaseBlade_canUse': 0x318730, 'SkillDiseaseBlade_cast': 0x318764,
                 'SkillDiseaseBlade_manaCost': 0x318AA0, 'SpellDiseaseBlade_ctor': 0x318AD4,
                 'SpellDiseaseBlade_run': 0x319068})


class SummonBadger:
    """90 - Summon Badger (`summonbadger`, shaman): creates a CastBadger creature a little
    ahead of the caster and a two-second spell on the caster that fades it in."""
    SB_VT = 0x51BD18
    SB_TYPE_NAME = 0x5527A8                     # "CastBadger"
    SB_LUMP, SB_SOUND, SB_PARTICLE = 0x5527B8, 0x5527C0, 0x8E8468
    SB_PLAYER_NAMES, SB_MONSTER_NAME = 0x5038F8, 0x503908      # pointers to the object names
    SB_PLAYER_PROPS, SB_MONSTER_PROPS = 0x5038D0, 0x5038F0     # property lists (8 bytes each)

    def summonbadger_can_use(self, skill, caster):
        """SkillSummonBadger_canUse 0x310690: no object in the world may carry this caster's
        badger name - one name per player slot 0-3 (a player in a higher slot is refused),
        one shared by every non-player."""
        name = self.u32(self.SB_MONSTER_NAME)
        if self.u32(caster + 0xC) & 0x40:
            slot = self.u32(caster + 0x3C8)
            if slot > 3:
                return 0
            name = self.u32(self.SB_PLAYER_NAMES + 4 * slot)
        return 0 if self.call('world_findObjectByName', name) else 1

    def summonbadger_cast(self, skill, level, caster, pos, facing):
        """SkillSummonBadger_cast 0x3106f4 -> the spell, or 0.

        The spot is pos + facing x 5.999953 x 12 on the ground (terrain_height, radius 48);
        when it is more than 24 above or below the caster (compared as doubles),
        world_findFreeSpot(caster position, 71, 24, 0) replaces it if it finds one.  The
        badger's level is slot 12 (0, level, caster, cap 10).  pool_new(0x3d0) - nothing
        more without a block - and CastBadger_ctor(type name, spot, facing, property list,
        level); object flags |= 0x4002, type name +0x34, creature flag 0x1000000.  For a
        player caster: followed slot +0x5a, creature flag 0x400000, Creature_setCharm(-1,
        the caster's slot 37), point-blank range +0x3ac = 400, home range (slot 34) 500.
        Then the caster's flash, a LightEffect above the spot following the caster, a sound
        at `pos`, pool_new(0x20) and the spell (level 1)."""
        u32, w32 = self.u32, self.w32
        facing_in = facing
        level = self.skill_call(skill, 14, level, 2)
        sx = C.add(pos[0], C.mul(C.mul(C.cos16(facing), 0x40BFFF9D), F_12))
        sy = C.add(pos[1], C.mul(C.mul(C.sin16(facing), 0x40BFFF9D), F_12))
        sz = self.call('terrain_height', u32(G_WORLD), (sx, sy, pos[2]), 0x42400000)
        spot = (sx, sy, sz)
        if abs(C.to_float(C.sub(sz, u32(caster + 0x18)))) > 24.0:
            out, found = self.call('world_findFreeSpot', self.vec(caster + 0x10), 0x47, 0x18, 0)
            if s8(found):
                spot = tuple(out)
        strength = self.skill_call(skill, 12, 0, level, caster, 10)
        props = 0
        if not u32(caster + 0xC) & 0x40:
            props = self.SB_MONSTER_PROPS
        elif u32(caster + 0x3C8) < 4:
            props = self.SB_PLAYER_PROPS + 8 * u32(caster + 0x3C8)
        badger = self.call('pool_new', 0x3D0)
        if not badger:
            return 0
        self.call('CastBadger_ctor', badger, self.SB_TYPE_NAME, spot, s16(facing_in), props, strength)
        flags = self.u64(badger + 0xA8)
        w32(badger + 0xC, u32(badger + 0xC) | 0x4002)
        w32(badger + 0x34, self.SB_TYPE_NAME)
        self.w64(badger + 0xA8, flags | 0x1000000)
        if u32(caster + 0xC) & 0x40:
            self.w8(badger + 0x5A, self.u8(caster + 0x3C8))
            self.w64(badger + 0xA8, flags | 0x1400000)
            self.call('Creature_setCharm', badger, M32, self.vcall(caster, 37))
            self.w16(badger + 0x3AC, 400)
            self.vcall(badger, 34, 500)
        self.flash(caster, 1, 0x54, 0xC0, 0x33, 0x41)
        self.flash(caster, 2, 0x54, 0xC0, 0x33, 0x41)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(spot[0], ZERO), spot[1], C.add(spot[2], F_36)), caster,
                              (0x42A80000, 0x43400000, 0x424C0000, 0x42820000), (0x42F00000, 0x43340000, ZERO, ONE))
        self.sound_at(self.SB_LUMP, self.SB_SOUND, pos)
        spell = self.call('pool_new', 0x20)
        if spell:
            self.summonbadger_spell_ctor(spell, 1, caster, skill, badger)
        return spell

    def summonbadger_spell_ctor(self, spell, level, caster, skill, badger):
        """SpellSummonBadger_ctor 0x310c3c: the Spell base (ONE SHARED DRAW), clock +0x1c =
        0, a handle to the badger at +0x18."""
        self.spell_base(spell, level, caster, skill, self.SB_VT)
        self.w32(spell + 0x1C, 0)
        self.w32(spell + 0x18, 0)
        if badger:
            self.handle_link(spell + 0x18, badger, badger)

    def summonbadger_spell_run(self, spell, pos=None, facing=0):
        """SpellSummonBadger_run 0x310cd0, once per frame of the caster.  An empty handle
        destroys the spell (a handle whose node carries no object does nothing).  f = clock
        up to 1.0 and 2.0 - clock after it; f < 0 destroys the spell.  clock +0x1c += 1/60;
        nothing more while f <= 0; once the new clock is above 1.0 the badger's object flag
        2 (not drawn) is cleared; then trunc(f x 38) particles on the badger's model sample
        points 0, 8, 16, ... (modulo the point count), each with a ball point from the
        spell's OWN generator."""
        u32 = self.u32
        node = u32(spell + 0x18)
        if node:
            badger = u32(node + 0xC)
            if not badger:
                return
            clock = u32(spell + 0x1C)
            share = clock
            if not C.le(clock, ONE):
                share = C.sub(ONE, C.sub(clock, ONE))
            if C.le(clock, ONE) or C.le(ZERO, share):
                clock = C.add(clock, DT)
                self.w32(spell + 0x1C, clock)
                if C.le(share, ZERO):
                    return
                if C.lt(ONE, clock):
                    self.w32(badger + 0xC, u32(badger + 0xC) & ~2)
                model = self.vcall(badger, 16)
                points = s32(self.call('model_getSamplePointCount', model))
                at = self.visual_pos(badger)
                count = C.to_int(C.mul(share, 0x42180000))
                index = 0
                for _ in range(max(count, 0)):
                    model = self.vcall(badger, 16)
                    px, py, pz = self.model_sample(badger, model, at, index)
                    x, y, z = self.spell_ball(spell)
                    point = (C.sub(px, C.mul(x, 0x423EAF66)), C.sub(py, C.mul(y, 0x423EAF66)),
                             C.sub(pz, C.mul(z, 0x423EAF66)))
                    self.call('particle_spawn', self.SB_PARTICLE, point,
                              (C.mul(x, 0x42092E61), C.mul(y, 0x42092E61), C.mul(z, 0x42092E61)), ZERO)
                    index = c_rem(index + 8, points) if points else index + 8
                return
        if spell:
            self.spell_destroy(spell)


EXTERNALS.update({
    'CastBadger_ctor': Ext(0x244E4C, 'ppvipi', 0, 'n', '(block, type name, position, facing, property list, level)'),
})
SKILL_BODIES.update({0x310690: (1, 'summonbadger_can_use'), 0x3106F4: (2, 'summonbadger_cast'),
                     0x310C08: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x310CD0: (2, 'summonbadger_spell_run')})
SPELL_TABLES.add(SummonBadger.SB_VT)
MODELLED.update({'SkillSummonBadger_canUse': 0x310690, 'SkillSummonBadger_cast': 0x3106F4,
                 'SkillSummonBadger_manaCost': 0x310C08, 'SpellSummonBadger_ctor': 0x310C3C,
                 'SpellSummonBadger_run': 0x310CD0})


class RaiseArmy:
    """91 - Raise Army (`raisearmy`, shadowknight): a wave that travels out from the caster
    and re-creates the corpses it passes as charmed creatures."""
    RA_VT = 0x51BF40
    RA_LUMP, RA_SOUND, RA_RAISE_SOUND, RA_PARTICLE = 0x552A98, 0x552AA0, 0x552AF8, 0x8E85A8
    RA_PREFIXES = (0x552AD8, 0x552AE0, 0x552AF0)       # two wood-elf type names, "ant"

    def raisearmy_can_use(self, skill, caster):
        """SkillRaiseArmy_canUse 0x3134b0: 1 unless the caster carries a SpellRaiseArmy."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['RaiseArmy']) else 1

    def raisearmy_cast(self, skill, level, caster, pos, facing):
        """SkillRaiseArmy_cast 0x3134e4: level through slot 14 (level, 0x14); both caster
        flash quads = (0x80, 0x32, 0, 0x32); a sound at `pos`; a LightEffect 36 above `pos`
        following the caster; pool_new(0x34); the constructor."""
        level = self.skill_call(skill, 14, level, 0x14)
        self.flash(caster, 1, 0x80, 0x32, 0, 0x32)
        self.flash(caster, 2, 0x80, 0x32, 0, 0x32)
        self.sound_at(self.RA_LUMP, self.RA_SOUND, pos)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), caster,
                              (0x43000000, 0x42480000, ZERO, 0x42480000), (0x42F00000, 0x43340000, ZERO, ONE))
        spell = self.call('pool_new', 0x34)
        if spell:
            self.raisearmy_spell_ctor(spell, level, caster, skill)
        return spell

    def raisearmy_is_raisable(self, spell, c):
        """SpellRaiseArmy_isRaisable 0x313b38 (spell, creature) -> 0 or 1: object flag 8
        (dead) set, 0x40 and 2 clear; flag 0x80 in the animation state's flag word +0x11a
        (the death clip has finished); creature flags 0x1, 0x800, 0x1000000, 0x4000000,
        0x100000000 all clear; creature_bossRank 0; object flag 0x1000000 clear."""
        if not c:
            return 0
        if self.u32(c + 0xC) & 0x4A != 0x08 or not self.u16(c + 0x11A) & 0x80:
            return 0
        if self.u64(c + 0xA8) & 0x105000801:
            return 0
        if self.call('creature_bossRank', c):
            return 0
        return 0 if self.u32(c + 0xC) & 0x1000000 else 1

    def raisearmy_spell_ctor(self, spell, level, caster, skill):
        """SpellRaiseArmy_ctor 0x3137d8.  The Spell base (ONE SHARED DRAW); clock +0x28 = 0,
        count +0x30 (s16) = 0; R = slot 10 (0, level) x 12; duration +0x2c = R x 0.005907856
        seconds; centre +0x1c = the caster's position; the candidate list +0x18 = every
        raisable creature of world_collectObjectsInBox(centre -/+ R, capacity 256), linked
        at the head (so the list is the box order reversed)."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, self.RA_VT)
        w32(spell + 0x18, 0)
        w32(spell + 0x28, 0)
        reach = C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, self.s8(spell)))), F_12)
        self.w16(spell + 0x30, 0)
        w32(spell + 0x2C, C.mul(reach, 0x3BC196B0))
        self.wvec(spell + 0x1C, self.vec(u32(spell + 0xC) + 0x10))
        centre = self.vec(spell + 0x1C)
        found = self.call('world_collectObjectsInBox', tuple(C.sub(v, reach) for v in centre),
                          tuple(C.add(v, reach) for v in centre), 0x100)
        for obj in found or ():
            if u32(obj + 0xC) & 0x20 and self.raisearmy_is_raisable(spell, obj):
                self.handle_link(spell + 0x18, obj, obj)

    def raisearmy_spell_run(self, spell, pos=None, facing=0):
        """SpellRaiseArmy_run 0x31399c, once per frame of the caster: f = 1 - (duration -
        clock) / duration; f > 1 destroys the spell; else r = f x 12 x slot 10 (0, level),
        206 ring particles (ONE OWN DRAW each; nothing else reads this generator), the
        raise step with r, and clock +0x28 += 1/60."""
        u32 = self.u32
        share = C.sub(ONE, C.div(C.sub(u32(spell + 0x2C), u32(spell + 0x28)), u32(spell + 0x2C)))
        if C.lt(ONE, share):
            if spell:
                self.spell_destroy(spell)
            return
        steps = C.from_int(s32(self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))))
        height = C.add(u32(spell + 0x24), 0x41C043AE)
        ring = C.mul(C.mul(share, F_12), steps)
        for _ in range(0xCE):
            angle = self.spell_rand(spell)
            point = (C.add(u32(spell + 0x1C), C.mul(C.cos16(angle), ring)),
                     C.add(u32(spell + 0x20), C.mul(C.sin16(angle), ring)), height)
            self.call('particle_spawn', self.RA_PARTICLE, point, (ZERO, ZERO, 0x3B8259E1), ZERO)
        self.raisearmy_raise_in_ring(spell, ring)
        self.w32(spell + 0x28, C.add(u32(spell + 0x28), DT))

    def raisearmy_raise_in_ring(self, spell, ring):
        """SpellRaiseArmy_raiseInRing 0x313bd4 (spell; radius): the candidate list in order.
        Gone: dropped.  Reached (sqrt(dx*dx + dy*dy) - radius <= ring): a creature that is
        no longer raisable is dropped; otherwise, if it has a type name (+0x34),
        world_createObject(type name, its position, its facing, 0), and when that returns
        a creature n:
          - n's hit points +0x228 = slot 10 (2, level) x 0.01 x the corpse's maximum, at
            least 1.0; obj_runEveryFrame(n); creature flags |= 0x8002000101400000;
            followed slot +0x5a = the BYTE at caster +0x3c8 (no is-player test);
            Creature_setCharm(n, 3600, the caster's slot 37)
          - n takes the corpse's pose: its track count +0x118 = 0, flash, then
            anim_pushWithWeights(n's animation state, the clip and the weights of the
            corpse's top track), its field +0x134, and its slot 27 (set state) with 0
          - n's weapon holder (if any) is given, for hand 1 and hand 2, what the corpse's
            holder reports: slot 15 -> slot 1 and slot 16 -> slot 8 (0 without a holder)
          - variant bits +0xe8 = the corpse's unless the type name starts with one of two
            names; the hide mask +0x220 = model_buildHideMask(n's model, variant bits);
            for a type name starting with the third: +0x3e0 copied and the tint preset
            +0xa0 = 2 or 4 for the values 1 and 2
          - the corpse: +0x2f4 = 0, creature flag 0x1000000 (it sinks; never raised again)
        Then, whether or not anything was created: a sound at the corpse, the entry is
        dropped, count +0x30 += 1, and when slot 10 (1, level) <= count the duration
        becomes the clock (the spell ends on its next run) and the walk stops."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        for node, corpse in self.handle_items(spell + 0x18):
            if not corpse:
                self.handle_remove(node)
                continue
            dy = C.sub(u32(spell + 0x20), u32(corpse + 0x14))
            dx = C.sub(u32(spell + 0x1C), u32(corpse + 0x10))
            if not C.le(C.sub(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), u32(corpse + 0x1C)), ring):
                continue
            if u32(corpse + 0xC) & 0x20 and not self.raisearmy_is_raisable(spell, corpse):
                self.handle_remove(node)
                continue
            name = u32(corpse + 0x34)
            if name:
                n = self.call('world_createObject', name, self.vec(corpse + 0x10), self.s16(corpse + 0x38), 0)
                if n and u32(n + 0xC) & 0x20:
                    self._raisearmy_dress(spell, corpse, n)
            self.sound_at(self.RA_LUMP, self.RA_RAISE_SOUND, self.vec(corpse + 0x10))
            self.handle_remove(node)
            count = s16(self.s16(spell + 0x30) + 1)
            w16(spell + 0x30, count)
            if s16(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell))) <= count:
                w32(spell + 0x2C, u32(spell + 0x28))
                return

    def _raisearmy_dress(self, spell, corpse, n):
        u32, w32, w16 = self.u32, self.w32, self.w16
        share = C.mul(C.from_int(s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))), F_0_01)
        hp = C.mul(share, u32(corpse + 0x22C))
        w32(n + 0x228, hp)
        if C.lt(hp, ONE):
            w32(n + 0x228, ONE)
        self.call('obj_runEveryFrame', n)
        self.w64(n + 0xA8, self.u64(n + 0xA8) | 0x8002000101400000)
        self.w8(n + 0x5A, self.u8(u32(spell + 0xC) + 0x3C8))
        self.call('Creature_setCharm', n, 0xE10, self.vcall(u32(spell + 0xC), 37))
        self.w8(n + 0x118, 0)
        self.flash(n, 1, 0x80, 0x32, 0, 0x32)
        self.flash(n, 2, 0x80, 0x32, 0, 0x32)
        top = self.s8(corpse + 0x118) * 0x20
        self.call('anim_pushWithWeights', n + 0x114, u32(corpse + 0xC + top + 0xF0), self.s16(corpse + top + 0x118),
                  u32(corpse + 0x14 + top + 0x100), u32(corpse + 0x14 + top + 0xF0), u32(corpse + top + 0x108),
                  u32(corpse + 0xC + top + 0x100), u32(corpse + 0x10 + top + 0x100))
        w32(n + 0x134, u32(corpse + 0x14 + self.s8(corpse + 0x118) * 0x20 + 0x100))
        self.vcall(n, 27, 0)
        for hand in (1, 2):
            for ask, give in ((15, 1), (16, 8)):
                holder = u32(corpse + 0x50)
                value = self.holder_call(holder, ask, hand) if holder else 0
                holder = u32(n + 0x50)
                if holder:
                    self.holder_call(holder, give, hand, value)
        if self.call('str_prefixDiffers', u32(n + 0x34), self.RA_PREFIXES[0]) \
                and self.call('str_prefixDiffers', u32(n + 0x34), self.RA_PREFIXES[1]):
            w32(n + 0xE8, u32(corpse + 0xE8))
        mask = self.call('model_buildHideMask', self.vcall(n, 16), u32(n + 0xE8))
        self.w64(n + 0x220, mask)
        if not self.call('str_prefixDiffers', u32(n + 0x34), self.RA_PREFIXES[2]):
            kind = u32(corpse + 0x3E0)
            w32(n + 0x3E0, kind)
            if kind in (1, 2):
                self.w8(n + 0xA0, 2 if kind == 1 else 4)
        flags = self.u64(corpse + 0xA8)
        w32(corpse + 0x2F4, 0)
        self.w64(corpse + 0xA8, flags | 0x1000000)


EXTERNALS.update({
    'world_createObject': Ext(0x14F6C8, 'pvii', 0, 'i', '(type name, position, facing, property list) -> object or 0'),
    'anim_pushWithWeights': Ext(0x1708C0, 'ppi', 5, 'n', '(state, clip, flags; five floats of the source track)'),
    'str_prefixDiffers': Ext(0x159C20, 'pp', 0, 'i', '(text, prefix) -> 0 when the text starts with the prefix'),
    'Holder.v16': Ext(0, 'pi', 0, 'i', '(hand) -> the element of the hand'),
    'Holder.v1': Ext(0, 'pii', 0, 'n', '(hand, model entry)'),
    'Holder.v15': Ext(0, 'pi', 0, 'i', '(hand) -> model entry it holds'),
})
SKILL_BODIES.update({0x3134B0: (1, 'raisearmy_can_use'), 0x3134E4: (2, 'raisearmy_cast'),
                     0x3137A4: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x31399C: (2, 'raisearmy_spell_run')})
SPELL_TABLES.add(RaiseArmy.RA_VT)
MODELLED.update({'SkillRaiseArmy_canUse': 0x3134B0, 'SkillRaiseArmy_cast': 0x3134E4,
                 'SkillRaiseArmy_manaCost': 0x3137A4, 'SpellRaiseArmy_ctor': 0x3137D8, 'SpellRaiseArmy_run': 0x31399C,
                 'SpellRaiseArmy_isRaisable': 0x313B38, 'SpellRaiseArmy_raiseInRing': 0x313BD4})


class BloodLust:
    """78 - Blood Lust (`bloodlust`, berserker): a shout; from its animation event the spell
    is "active", which raises the caster's melee damage (Player_recalcDamage asks
    bloodlust_multiplier) and lowers its armour (damage_apply asks bloodlust_complement)
    until the spell ends.  The particle half of the run takes its counts from PER-MACHINE
    inputs - the option g_decalDetail and the hand motion of the prediction copy - so the
    spell's own generator differs between machines; nothing but particles reads it."""
    BL_VT = 0x51B440
    BL_NAMES = {0: 0x551AC8, 1: 0x551B10, 2: 0x551AF8, 3: 0x551B28, 7: 0x551B38}
    BL_NAME_DEFAULT = 0x551AE0
    BL_LUMP, BL_SOUND = 0x551A90, 0x551A98
    BL_PARTICLES = {'trail': 0x8E70A0, 'drip': 0x8E70F0, 'late': 0x8E7140}
    BL_DOUBLES = (0x551B70, 0x551B78)           # two doubles of the flash pulse
    BL_GLOW_TEXTURES = (0x4F8498, 0x4F8490)     # words read for the two glow sprites
    G_DECAL_DETAIL = RC.G_DECAL_DETAIL          # 0x44fdc0 s32, a local option (machine)

    def bloodlust_can_use(self, skill, caster):
        """SkillBloodLust_canUse 0x30300c: 1 unless the caster carries a SpellBloodLust."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['BloodLust']) else 1

    def bloodlust_cast(self, skill, level, caster, pos, facing):
        """SkillBloodLust_cast 0x303040: level through slot 14 (level, 2); a sound at `pos`;
        pool_new(0x4c); the constructor."""
        level = self.skill_call(skill, 14, level, 2)
        self.sound_at(self.BL_LUMP, self.BL_SOUND, pos)
        spell = self.call('pool_new', 0x4C)
        if spell:
            self.bloodlust_spell_ctor(spell, level, caster, skill)
        return spell

    def ghost_hands(self, owner):
        """The two hand points of net_objOrGhost(owner) - the prediction copy on the
        owner's machine (per machine): body-model attach points 0 and 1 at its visual
        position."""
        ghost = self.call('net_objOrGhost', owner)
        at = self.visual_pos(ghost)
        hands = []
        for index in (0, 1):
            hands.append(tuple(self.call('model_getAttachPoint', self.u32(ghost + 0x544), at, self.s16(ghost + 0x38),
                                         ghost + 0x114, index, 0, ONE)))
        return hands

    def bloodlust_spell_ctor(self, spell, level, owner, skill):
        """SpellBloodLust_ctor 0x303254.  The Spell base (ONE SHARED DRAW); clock +0x1c = 0;
        end time +0x24 = (float) slot 10 (0, level); animating +0x28 = 1, active +0x2c = 0,
        interrupted +0x30 = 0, owner +0x18; the owner's action state +0x58c = 6 (NO
        is-player test); the shout animation with event 2 at 0.488 s, started with flags
        0x822; the two hand points of the prediction copy at +0x34 and +0x40."""
        w32 = self.w32
        self.spell_base(spell, level, owner, skill, self.BL_VT)
        w32(spell + 0x1C, 0)
        seconds = s32(self.skill_call(skill, 10, 0, s8(level)))
        w32(spell + 0x28, 1)
        w32(owner + 0x58C, 6)
        w32(spell + 0x24, C.from_int(seconds))
        w32(spell + 0x2C, 0)
        w32(spell + 0x30, 0)
        w32(spell + 0x18, owner)
        self.shout_animation(owner, self.BL_NAMES, self.BL_NAME_DEFAULT, ((1, 0x3EF9DB01, 2),), 0x822)
        hands = self.ghost_hands(self.u32(spell + 0x18))
        for hand, at in zip(hands, (0x34, 0x40)):
            for k in range(3):
                self.callee_store(spell + at + 4 * k, 4, hand[k])

    def hand_streamers(self, spell, definition, hands, last_0, last_1):
        """Ten pairs of particles between where the hands were (two points kept in the
        spell) and where they are: per pair two ball points and two more OWN draws."""
        u32 = self.u32
        hand_0, hand_1 = hands
        moved_0 = tuple(C.sub(hand_0[k], u32(spell + last_0 + 4 * k)) for k in range(3))
        moved_1 = tuple(C.sub(hand_1[k], u32(spell + last_1 + 4 * k)) for k in range(3))
        for _ in range(10):
            first = self.spell_ball(spell)
            second = self.spell_ball(spell)
            first = tuple(C.add(v, v) for v in first)
            second = tuple(C.add(v, v) for v in second)
            share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
            point_0 = tuple(C.add(C.add(hand_0[k], second[k]), C.mul(moved_0[k], share)) for k in range(3))
            share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
            point_1 = tuple(C.add(C.add(hand_1[k], first[k]), C.mul(moved_1[k], share)) for k in range(3))
            self.call('particle_spawn', definition, point_0, first, ZERO)
            self.call('particle_spawn', definition, point_1, second, ZERO)

    def bloodlust_spell_run(self, spell, pos=None, facing=0):
        """SpellBloodLust_run 0x3034dc, once per frame of the owner.

          - clock +0x1c += 1/60; the per-machine force-rebase byte as in Roar
          - animating and the owner's action state is no longer 6: animating = 0 and, if
            not yet active, the half refund, interrupted +0x30 = 1, end time = clock + 0.5
          - still animating: ev = Player_animStep(owner; 1.0); without animation flag 0x20
            animating = 0 and action state = 2; else ev == 2: active +0x2c = 1, start time
            +0x20 = clock
          - end time +0x24 <= clock: the action state goes back from 6 to 2 (unless
            interrupted) and the spell destroys itself
          - otherwise (presentation; the hand points are the prediction copy's):
              interrupted: ten pairs of streamer particles
              active: the owner's flash quad 1 = (12, 5, 2, pulse) and quad 2 = 0 with
                  pulse = trunc(fade x ((sin16(frame << 10) + 1) x 4.4 + 79.2)) in soft
                  double arithmetic, fade ramping over the first and last 0.2 s; four glow
                  sprites on the hands; and, only with g_decalDetail > 0: in action states
                  0 and 1 up to three trail particles per hand by how far it moved (one
                  every fourth frame when nearly still), in the other states blood drops
                  whose number is drawn from the spell's OWN generator
            and the two hand points +0x34, +0x40 are stored."""
        u32, w32 = self.u32, self.w32
        clock = C.add(u32(spell + 0x1C), DT)
        w32(spell + 0x1C, clock)
        if self.s8(G_NETWORK_MODE) and self.call('net_isLocalSlot', u32(u32(spell + 0x18) + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 1)
        if u32(spell + 0x28):
            if u32(u32(spell + 0x18) + 0x58C) != 6:
                w32(spell + 0x28, 0)
                if not u32(spell + 0x2C):
                    self.shout_interrupted(spell, u32(spell + 0x18))
                    w32(spell + 0x30, 1)
                    w32(spell + 0x24, C.add(u32(spell + 0x1C), HALF))
            if u32(spell + 0x28):
                event = s32(self.call('Player_animStep', u32(spell + 0x18), ONE))
                if not self.u16(u32(spell + 0x18) + 0x11A) & 0x20:
                    w32(spell + 0x28, 0)
                    w32(u32(spell + 0x18) + 0x58C, 2)
                elif event == 2:
                    w32(spell + 0x2C, 1)
                    w32(spell + 0x20, u32(spell + 0x1C))
        if C.le(u32(spell + 0x24), u32(spell + 0x1C)):
            if not u32(spell + 0x30) and u32(u32(spell + 0x18) + 0x58C) == 6:
                w32(u32(spell + 0x18) + 0x58C, 2)
            if spell:
                self.spell_destroy(spell)
            return
        hands = self.ghost_hands(u32(spell + 0x18))
        if u32(spell + 0x30):
            self.hand_streamers(spell, self.BL_PARTICLES['late'], hands, 0x34, 0x40)
        elif u32(spell + 0x2C):
            self._bloodlust_glow(spell, hands)
        self.wvec(spell + 0x34, hands[0])
        self.wvec(spell + 0x40, hands[1])

    def _bloodlust_glow(self, spell, hands):
        u32 = self.u32
        frame = u32(G_SIM_FRAME)
        fade = ONE
        since = C.sub(u32(spell + 0x1C), u32(spell + 0x20))
        if C.lt(since, F_0_2):
            fade = C.mul(since, 0x40A00000)
        left = C.sub(u32(spell + 0x24), u32(spell + 0x1C))
        if C.lt(left, F_0_2):
            fade = C.mul(left, 0x40A00000)
        owner = u32(spell + 0x18)
        self.w16(owner + 0x92, 5)
        self.w16(owner + 0x94, 2)
        self.w16(owner + 0x90, 0xC)
        for off in (0x9E, 0x98, 0x9A, 0x9C):
            self.w16(owner + off, 0)
        wave = C.sin16(frame << 10)
        pulse = C.dadd(C.dmul(C.f2d(C.add(wave, ONE)), self.u64(self.BL_DOUBLES[0])), self.u64(self.BL_DOUBLES[1]))
        self.w16(u32(spell + 0x18) + 0x96, C.d2i(C.dmul(C.f2d(fade), pulse)))
        turn = s32(((u32(G_SIM_FRAME) & 0xFFFF) << 22) & M32) >> 16
        for size, base, swing, colour, alpha, texture in (
                (0x3EC18676, 0x45A0D000, 0x44D2C000, (0xFF, 0x21, 0xF), 0x42840000, self.BL_GLOW_TEXTURES[0]),
                (0x4108D0BC, 0x44D60000, 0x4406C000, (0x7B, 0x7C, 0xF), 0x435C0000, self.BL_GLOW_TEXTURES[1])):
            opacity = C.to_int(C.mul(fade, alpha))
            for hand in hands:
                reach = C.add(C.mul(C.sin16(u32(G_SIM_FRAME) << 10), swing), base)
                self.call('glow_add', hand, colour[0], colour[1], colour[2], opacity, u32(texture), turn, 3, size, reach)
        moved = [tuple(C.sub(hand[k], u32(spell + at + 4 * k)) for k in range(3))
                 for hand, at in zip(hands, (0x34, 0x40))]
        if not self.s32(self.G_DECAL_DETAIL) > 0:
            return
        if u32(u32(spell + 0x18) + 0x58C) < 2:
            for delta, at in zip(moved, (0x34, 0x40)):
                far = C.add(C.add(C.mul(delta[0], delta[0]), C.mul(delta[1], delta[1])), C.mul(delta[2], delta[2]))
                count = 3
                if C.le(far, 0x42C80000):
                    count = 2
                    if C.le(far, 0x41C80000):
                        count = 1
                        if C.le(far, 0x40800000):
                            count = 1 if u32(G_SIM_FRAME) & 3 == 0 else 0
                for _ in range(count):
                    share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
                    point = tuple(C.add(u32(spell + at + 4 * k), C.mul(delta[k], share)) for k in range(3))
                    ball = self.spell_ball(spell)
                    point = tuple(C.add(point[k], C.mul(ball[k], 0x40400000)) for k in range(3))
                    self.call('particle_spawn', self.BL_PARTICLES['trail'], point,
                              tuple(C.mul(v, 0x40200000) for v in delta), ZERO)
        else:
            for hand in hands:
                shift = (self.spell_rand(spell) % 0x5DC + 10) & 31
                wave = C.sin16((u32(G_SIM_FRAME) << shift) & M32)
                share = C.mul(C.from_int(self.spell_rand(spell)), F_2M16)
                most = C.from_int(C.to_int(C.sub(C.mul(wave, 0x40C00000), 0x40400000)))
                for _ in range(max(C.to_int(C.mul(share, most)), 0)):
                    ball = self.spell_ball(spell)
                    point = tuple(C.add(hand[k], C.add(ball[k], ball[k])) for k in range(3))
                    self.call('particle_spawn', self.BL_PARTICLES['drip'], point, (ZERO, ZERO, ZERO), ZERO)

    def bloodlust_complement(self, spell):
        """SpellBloodLust_getStat2Complement 0x3047b0 (spell) -> 1.0, or while active 1 -
        slot 10 (2, level) x 0.01: the factor damage_apply puts on the armour of a victim
        that carries the spell."""
        if not self.u32(spell + 0x2C):
            return ONE
        return C.sub(ONE, C.mul(C.from_int(s32(self.skill_call(self.u32(spell + 8), 10, 2, self.s8(spell)))), F_0_01))

    def bloodlust_multiplier(self, spell):
        """SpellBloodLust_getStat1Multiplier 0x30481c (spell) -> 1.0, or while active slot
        10 (1, level) x 0.01 + 1: the melee damage factor Player_recalcDamage takes the
        larger of this and the Berserker Rage factor from."""
        if not self.u32(spell + 0x2C):
            return ONE
        return C.add(C.mul(C.from_int(s32(self.skill_call(self.u32(spell + 8), 10, 1, self.s8(spell)))), F_0_01), ONE)


EXTERNALS.update({
    'glow_add': Ext(0x18FC78, 'viiiiiii', 2, 'n', '(point, three colour bytes, alpha, texture, angle, 3; size, reach)'),
})
SKILL_BODIES.update({0x30300C: (1, 'bloodlust_can_use'), 0x303040: (2, 'bloodlust_cast'),
                     0x303220: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x3034DC: (2, 'bloodlust_spell_run')})
SPELL_TABLES.add(BloodLust.BL_VT)
MODELLED.update({'SkillBloodLust_canUse': 0x30300C, 'SkillBloodLust_cast': 0x303040,
                 'SkillBloodLust_manaCost': 0x303220, 'SpellBloodLust_ctor': 0x303254, 'SpellBloodLust_run': 0x3034DC,
                 'SpellBloodLust_getStat2Complement': 0x3047B0, 'SpellBloodLust_getStat1Multiplier': 0x30481C})


def item_record(definition, quantity, slots=()):
    """The canonical form of an item record built on the stack: definition pointer (+0),
    quantity (a halfword at +4), the all-empty header and the four modifier slots (+0x24).
    The halfword at +6 is not written by the skill code."""
    filled = tuple(tuple(v & 0xFFFF for v in slot) for slot in slots)
    return ('item', definition & M32, quantity & 0xFFFF, DESC_HEADER) + filled + ((0xFFFF,),) * (4 - len(filled))


class SummonItems:
    """72 - Summon Axe (`summonaxe`, berserker) and 75 - Summon Arrows (`summonarrows`,
    ranger): the same code with a different item.  The constructor builds an item record,
    hands it to the inventory if the player can carry it, and equips it; the spell that
    remains is two seconds of particles.  The inventory functions are call-outs
    (tools/ref_items.py and tools/ref_player.py own them)."""
    SI_AXE = {'vt': 0x51B050, 'adjust': 10, 'flash': (0x40, 0x40, 0x80, 0x66), 'lump': 0x5514E8, 'sound': 0x5514F0,
              'light': (0x42800000, 0x42800000, 0x43000000, 0x42CC0000), 'particle': 0x8E6D30, 'count': 0x42480000,
              'out': 0x41807CFC, 'up': 0x41BDE66D, 'speed': 0x413E8AEB}
    SI_ARROWS = {'vt': 0x51B218, 'adjust': 0x14, 'flash': (0x40, 0x80, 0x40, 0x80), 'lump': 0x5516F8,
                 'sound': 0x551700, 'light': (0x42800000, 0x43000000, 0x42800000, 0x43000000), 'particle': 0x8E6D80,
                 'count': 0x41700000, 'out': 0x41851C19, 'up': 0x41B857C1, 'speed': 0x411B8D73}
    SI_AXE_NAMES = ((5, 0x551520), (9, 0x551530), (13, 0x551548), (17, 0x551560), (21, 0x551578))
    SI_ARROWS_NAME = 0x551730
    REC_LOAD, REC_LOAD_LIMIT, REC_BAGS = 0x120, 0x124, 0x130

    def summonarrows_can_use(self, skill, caster=0):
        """SkillSummonArrows_canUse 0x2ff5ec: always 1 (Summon Axe uses the default)."""
        return 1

    def summonaxe_cast(self, skill, level, caster, pos, facing):
        """SkillSummonAxe_cast 0x2fe644."""
        return self._summon_cast(self.SI_AXE, skill, level, caster, pos)

    def summonarrows_cast(self, skill, level, caster, pos, facing):
        """SkillSummonArrows_cast 0x2ff5f4."""
        return self._summon_cast(self.SI_ARROWS, skill, level, caster, pos)

    def _summon_cast(self, cfg, skill, level, caster, pos):
        """Both casts: level through slot 14; the caster's flash; a sound at `pos`; a
        LightEffect 36 above `pos` following the caster; pool_new(0x20); the constructor."""
        level = self.skill_call(skill, 14, level, cfg['adjust'])
        self.flash(caster, 1, *cfg['flash'])
        self.flash(caster, 2, *cfg['flash'])
        self.sound_at(cfg['lump'], cfg['sound'], pos)
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), caster, cfg['light'],
                              (0x42F00000, 0x43340000, ZERO, ONE))
        spell = self.call('pool_new', 0x20)
        if spell:
            self._summon_ctor(cfg, spell, level, caster, skill)
        return spell

    def summonaxe_build_item(self, level, quantity, plain=0):
        """SkillSummonAxe_buildItem 0x2fe96c (skill, level, item record, plain) on a record
        whose four modifier slots are empty: the descriptor is one of five names by level
        (below 5, 9, 13, 17, else), parsed with variant -1 (0 with `plain`, as the menu
        asks), and three modifiers are added, each in the first slot that is empty or
        already holds its code: (0x25, 1), (0x24, 10), (0x0e, required level 5 / 9 / 13 /
        17 / 21).  Returns the record and its definition."""
        level = s8(level)
        for required, name in self.SI_AXE_NAMES:
            if level < required or required == 21:
                break
        definition = self.call('item_parseDescriptor', name, 0 if plain else M32, 0)
        return item_record(definition, quantity, ((0x25, 1, 0, 0), (0x24, 10, 0, 0), (0xE, required, 0, 0))), definition

    def _summon_ctor(self, cfg, spell, level, caster, skill):
        """SpellSummonAxe_ctor 0x2feb88 / SpellSummonArrows_ctor 0x2ff87c.

        The Spell base (ONE SHARED DRAW); start frame +0x18 = the frame counter; a
        particle group handle +0x1c; an item record with quantity slot 10 (0, level) -
        the axe built by summonaxe_build_item, the arrows by parsing their one name with
        variant -1 (the parser may make one shared draw for the variant).  Then, on the
        player record of slot [caster +0x3c8] WITH NO IS-PLAYER TEST: if load +0x120 +
        player_itemWeight(slot, item) <= limit +0x124: inventory_giveItem(slot, item, 1) ->
        index, player_recalcLoad, inventory_equipItem(slot, the record at that index of
        the bag the definition names (+0x1d), 0), player_resetIdleAnim.  Otherwise:
        player_voice(slot, 0), the mana cost is given back (up to the maximum) and the
        start frame becomes -1."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, cfg['vt'])
        w32(spell + 0x18, u32(G_SIM_FRAME))
        w32(spell + 0x1C, self.call('particleGroup_create'))
        quantity = self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))
        if cfg is self.SI_AXE:
            item, definition = self.summonaxe_build_item(self.s8(spell), quantity)
        else:
            definition = self.call('item_parseDescriptor', self.SI_ARROWS_NAME, M32, 0)
            item = item_record(definition, quantity)
        owner = u32(spell + 0xC)
        slot = u32(owner + 0x3C8)
        rec = self.record(owner)
        weight = self.call('player_itemWeight', slot, item)
        if C.le(C.add(u32(rec + self.REC_LOAD), weight), u32(rec + self.REC_LOAD_LIMIT)):
            index = s32(self.call('inventory_giveItem', slot, item, 1))
            self.call('player_recalcLoad', slot)
            bag = self.s8(definition + 0x1D)
            self.call('inventory_equipItem', slot, rec + self.REC_BAGS + bag * 0x1208 + index * 0x48, 0)
            self.call('player_resetIdleAnim', slot)
        else:
            self.call('player_voice', u32(owner + 0x3C8), 0)
            rec = self.record(owner)
            mana = C.add(u32(rec + 0xC0), self.skill_call(u32(spell + 8), 5, self.s8(spell)))
            w32(rec + 0xC0, mana)
            if C.lt(u32(rec + 0xC4), mana):
                w32(rec + 0xC0, u32(rec + 0xC4))
            w32(spell + 0x18, M32)

    def summonaxe_spell_run(self, spell, pos=None, facing=0):
        """SpellSummonAxe_run 0x2feddc."""
        return self._summon_run(self.SI_AXE, spell)

    def summonarrows_spell_run(self, spell, pos=None, facing=0):
        """SpellSummonArrows_run 0x2ffad4."""
        return self._summon_run(self.SI_ARROWS, spell)

    def _summon_run(self, cfg, spell):
        """Both run functions, once per frame of the owner.  Start frame -1: the particle
        group is freed and the spell destroys itself.  Else with age = frame - start:
        trunc(sin16(trunc(age x 0.0333 x 32768)) x 50) particles (x 15 for the arrows; none
        after age 30), each with two OWN draws (a model sample point of the owner and an
        angle), in a group placed at net_objOrGhost(owner)'s visual position; after age
        120 the group is freed and the spell destroys itself."""
        u32 = self.u32
        if self.s32(spell + 0x18) == -1:
            self.call('particleGroup_free', u32(spell + 0x1C))
            if spell:
                self.spell_destroy(spell)
            return
        age = s32(u32(G_SIM_FRAME) - u32(spell + 0x18))
        age_f = C.from_int(age)
        count = C.to_int(C.mul(C.sin16(C.to_int(C.mul(C.mul(age_f, 0x3D088888), 0x47000000))), cfg['count']))
        owner = u32(spell + 0xC)
        points = s32(self.call('model_getSamplePointCount', self.vcall(owner, 16)))
        ghost = self.call('net_objOrGhost', u32(spell + 0xC))
        if C.lt(0x41F00000, age_f):
            count = 0
        self.call('particleGroup_begin', u32(spell + 0x1C))
        self.visual_pos(ghost)
        self.call('particleGroup_setMatrix', u32(spell + 0x1C), 'stack')
        for _ in range(max(count, 0)):
            owner = u32(spell + 0xC)
            model = self.vcall(owner, 16)
            index = c_rem(self.spell_rand(spell), points)
            px, py, pz = self.model_sample(u32(spell + 0xC), model, (ZERO, ZERO, ZERO), index)
            angle = self.spell_rand(spell)
            cosine, sine = C.cos16(angle), C.sin16(angle)
            point = (C.sub(px, C.mul(cosine, cfg['out'])), C.sub(py, C.mul(sine, cfg['out'])),
                     C.add(C.sub(pz, ZERO), cfg['up']))
            self.call('particle_spawn', cfg['particle'], point,
                      (C.mul(cosine, cfg['speed']), C.mul(sine, cfg['speed']), ZERO), ZERO)
        self.call('particleGroup_end', u32(spell + 0x1C))
        if age > 0x78:
            self.call('particleGroup_free', u32(spell + 0x1C))
            if spell:
                self.spell_destroy(spell)


EXTERNALS.update({
    'item_parseDescriptor': Ext(0x1069B8, 'pwii', 0, 'n', '(descriptor text, item record, variant or -1, 0); the '
                                'model is handed the definition pointer the parser stores in the record'),
    'player_itemWeight': Ext(0x1B6338, 'iI', 0, 'f', '(slot, item record) -> weight'),
    'inventory_giveItem': Ext(0x1C1868, 'iIi', 0, 'i', '(slot, item record, 1) -> index in its bag'),
    'player_recalcLoad': Ext(0x1BEC10, 'i', 0, 'n', '(slot)'),
    'inventory_equipItem': Ext(0x1C27C0, 'ipi', 0, 'n', '(slot, item record in the bag, 0)'),
    'player_resetIdleAnim': Ext(0x1B2470, 'i', 0, 'n', '(slot)'),
    'player_voice': Ext(0x1B7BA8, 'ii', 0, 'n', '(slot, line) (local machine only)'),
})
SKILL_BODIES.update({0x2FE644: (2, 'summonaxe_cast'), 0x2FE938: (5, 'skill_mana_cost'),
                     0x2FF5EC: (1, 'summonarrows_can_use'), 0x2FF5F4: (2, 'summonarrows_cast'),
                     0x2FF848: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x2FEDDC: (2, 'summonaxe_spell_run'), 0x2FFAD4: (2, 'summonarrows_spell_run')})
SPELL_TABLES.update({SummonItems.SI_AXE['vt'], SummonItems.SI_ARROWS['vt']})
MODELLED.update({'SkillSummonAxe_cast': 0x2FE644, 'SkillSummonAxe_manaCost': 0x2FE938,
                 'SkillSummonAxe_buildItem': 0x2FE96C, 'SpellSummonAxe_ctor': 0x2FEB88, 'SpellSummonAxe_run': 0x2FEDDC,
                 'SkillSummonArrows_canUse': 0x2FF5EC, 'SkillSummonArrows_cast': 0x2FF5F4,
                 'SkillSummonArrows_manaCost': 0x2FF848, 'SpellSummonArrows_ctor': 0x2FF87C,
                 'SpellSummonArrows_run': 0x2FFAD4, 'mat34_setTranslation': 0x166850})


class ThrownAxes:
    """98 - Fire Axe (`fireaxe`) and 99 - Cold Axe (`coldaxe`), berserker, kind 8: the cast
    throws one axe of the equipped stack as a playerProjectile whose item record - one per
    player slot, INSIDE THE SKILL OBJECT at +0x68 + slot x 0x48 - carries a fire or cold
    modifier.  Everything after the first lines uses caster +0x3c8 with no is-player test.
    The projectile's flight and its hit (MissileWeapon_onTouch) are tools/ref_objects.py's."""
    TA_FIRE = {'adjust': 0x14, 'flash': (0x73, 0x4F, 0x38, 0x23), 'lump': 0x5531E8, 'sound': 0x5531F0,
               'light': (0x42E60000, 0x429E0000, 0x42600000, 0x420C0000), 'element': 0x15, 'warn': 0x5531D8}
    TA_COLD = {'adjust': 2, 'flash': (0x3C, 0x3C, 0x5E, 0x26), 'lump': 0x553298, 'sound': 0x5532A0,
               'light': (0x42700000, 0x42700000, 0x42BC0000, 0x42180000), 'element': 0x16, 'warn': 0x553288}
    REC_SLOT2_ITEM, REC_DAMAGE_MIN, REC_DAMAGE_MAX = 0x43F8, 0xD0, 0xD4
    G_ITEM_MODELS = AM.G_ITEM_MODELS            # 0x3e9ce0, 16-byte rows
    G_HUD_NOTICE_TIMER, G_HUD_NOTICE_SLOT = 0x41B844, 0x41B8C4       # + player slot x 0x20

    def fireaxe_can_use(self, skill, caster):
        """SkillFireAxe_canUse 0x319710."""
        return self._axe_can_use(self.TA_FIRE, caster)

    def coldaxe_can_use(self, skill, caster):
        """SkillColdAxe_canUse 0x31a04c."""
        return self._axe_can_use(self.TA_COLD, caster)

    def _axe_can_use(self, cfg, caster):
        """A non-player is always allowed.  A player needs an item in equipment slot 2
        (record +0x43f8) with item flag bit 42; otherwise a warning text is shown for 180
        frames (hud_showMessage, the owning machine's display) and the cast is refused."""
        if not self.u32(caster + 0xC) & 0x40:
            return 1
        slot = self.u32(caster + 0x3C8)
        item = self.u32(self.record(caster) + self.REC_SLOT2_ITEM)
        if item and self.u64(item + 8) & 0x40000000000:
            return 1
        self.call('hud_showMessage', self.call('text_lookup', cfg['warn']), 0xB4, slot, 0)
        return 0

    def fireaxe_cast(self, skill, level, caster, pos, facing):
        """SkillFireAxe_cast 0x31979c -> 0."""
        return self._axe_cast(self.TA_FIRE, skill, level, caster, pos)

    def coldaxe_cast(self, skill, level, caster, pos, facing):
        """SkillColdAxe_cast 0x31a0d8 -> 0."""
        return self._axe_cast(self.TA_COLD, skill, level, caster, pos)

    def _axe_cast(self, cfg, skill, level, caster, pos):
        """Both casts.  Level through slot 14; the caster's flash; a LightEffect 36 above
        `pos` following the caster; a sound at `pos`; speed = slot 10 (0, level); the hand
        = body-model attach point 0.

        Without a target (+0x234 empty) TWO SHARED DRAWS: heading = facing + r1 % 2600 -
        1300, climb = r2 % 40 + 40.  With one: heading = 0x4000 - atan2_16(target.x -
        hand.x, target.y - hand.y), climb = the 3-D distance hand to target - 120.
        velocity = (cos, sin)(heading) x speed, climb.

        The axe stack is the item of equipment slot 2; its model row comes from
        item_getResourceIndex (asked twice).  Without a primary weapon in the active set
        nothing is thrown.  Otherwise the slot's record in the skill object takes the
        PRIMARY WEAPON's mutable fields (item_copyMutableFields) and, in its first slot
        that is empty or already holds the element, (0x15 fire / 0x16 cold, v, round(v + v
        x 0.19999999), 600) with v = slot 10 (1, level); pool_new(0x1d0) and
        playerProjectile_ctor(model, hand, velocity, heading + 0x4000, caster, 0; on the
        stack 0, the record's damage minimum +0xd0 and maximum +0xd4, 0, 0, attack
        100000, kind 4, the item record).  A stack of 1-20 raises the HUD's low-ammunition
        notice; unless the caster is the prediction copy (object flag 0x20000) the stack
        count +4 goes down by one, and a stack at 0 is removed from bag 0."""
        u32, w32 = self.u32, self.w32
        level = self.skill_call(skill, 14, level, cfg['adjust'])
        self.flash(caster, 1, *cfg['flash'])
        self.flash(caster, 2, *cfg['flash'])
        block = self.call('pool_new', 0xBC)
        if block:
            self.light_effect(block, (C.add(pos[0], ZERO), pos[1], C.add(pos[2], F_36)), caster, cfg['light'],
                              (0x42F00000, 0x43340000, ZERO, HALF))
        self.sound_at(cfg['lump'], cfg['sound'], pos)
        rec = self.record(caster)
        speed = C.from_int(s32(self.skill_call(skill, 10, 0, level)))
        hand, _direction = self.call('model_getAttachPoint', u32(caster + 0x544), self.vec(caster + 0x10),
                                     self.s16(caster + 0x38), caster + 0x114, 0, 1, ONE)
        if not u32(caster + 0x234):
            first = self.draw()
            second = self.draw()
            heading = self.u16(caster + 0x38) + first % 0xA28 - 0x514
            climb = C.add(C.from_int(second % 0x28), 0x42200000)
        else:
            target = self.vec(u32(u32(caster + 0x234) + 0xC) + 0x10)
            away = [C.sub(hand[k], target[k]) for k in range(3)]
            heading = 0x4000 - C.atan2_16(C.sub(target[0], hand[0]), C.sub(target[1], hand[1]))
            climb = C.sub(C.sqrt(C.add(C.add(C.mul(away[0], away[0]), C.mul(away[1], away[1])),
                                       C.mul(away[2], away[2]))), 0x42F00000)
        heading = s16(heading)
        velocity = (C.mul(C.cos16(heading), speed), C.mul(C.sin16(heading), speed), climb)
        stack = u32(rec + self.REC_SLOT2_ITEM)
        model_0 = u32(self.G_ITEM_MODELS + 8 + 16 * s32(self.call('item_getResourceIndex', stack)))
        model_1 = u32(self.G_ITEM_MODELS + 0xC + 16 * s32(self.call('item_getResourceIndex', stack)))
        main = u32(rec + 0x4434 + 4 * self.s8(rec + 0x4A7C))
        if not main:
            return 0
        record = (skill + s32(u32(caster + 0x3C8)) * 0x48 + 0x68) & M32
        self.call('item_copyMutableFields', record, main)
        low, high = self.s32(rec + self.REC_DAMAGE_MIN), self.s32(rec + self.REC_DAMAGE_MAX)
        value = s32(self.skill_call(skill, 10, 1, level))
        top = self._round(C.add(C.from_int(value), C.mul(C.from_int(value), F_0_2)))
        record = (skill + s32(u32(caster + 0x3C8)) * 0x48 + 0x68) & M32
        for k in range(4):
            if self.s16(record + 0x24 + 8 * k) in (-1, cfg['element']):
                self.w16(record + 0x24 + 8 * k, cfg['element'])
                self.w16(record + 0x26 + 8 * k, value)
                self.w16(record + 0x28 + 8 * k, top)
                self.w16(record + 0x2A + 8 * k, 600)
                break
        block = self.call('pool_new', 0x1D0)
        if block:
            item = (skill + s32(u32(caster + 0x3C8)) * 0x48 + 0x68) & M32
            self.call('playerProjectile_ctor', block, model_0, model_1, tuple(hand), velocity, heading + 0x4000, caster,
                      0, 0, low, high, 0, 0, 100000, 4, item)
        if (self.u16(stack + 4) - 1) & M32 < 0x14:
            w32(self.G_HUD_NOTICE_TIMER + u32(caster + 0x3C8) * 0x20, 0xF0)
            shown = self.call('hud_countActiveNotices', u32(caster + 0x3C8), 7)
            w32(self.G_HUD_NOTICE_SLOT + u32(caster + 0x3C8) * 0x20, shown)
        if not u32(caster + 0xC) & 0x20000:
            self.w16(stack + 4, self.u16(stack + 4) - 1)
        if not self.s16(stack + 4) > 0:
            for index in range(0x40):
                if rec + 0x130 + index * 0x48 == u32(rec + self.REC_SLOT2_ITEM):
                    self.call('inventory_removeItem', u32(caster + 0x3C8), index, 0, 0)
        return 0


EXTERNALS.update({
    'text_lookup': Ext(0x173C84, 'p', 0, 'i', '(key) -> text'),
    'hud_showMessage': Ext(0x1D92A0, 'piii', 0, 'n', '(text, frames, slot, 0)'),
    'item_getResourceIndex': Ext(0x1083F8, 'p', 0, 'i', '(item record) -> row of g_itemModels'),
    'item_copyMutableFields': Ext(0x107CA8, 'pp', 0, 'n', '(to, from): count, flags, affixes, the four modifiers'),
    'playerProjectile_ctor': Ext(0x1BEF58, 'piivvipi', 0, 'n', '(block, model, model, position, velocity, heading, '
                                 'owner, 0; on the stack: 0, damage min, damage max, 0, 0, attack, kind, item)'),
    'hud_countActiveNotices': Ext(0x1DACF4, 'ii', 0, 'i', '(slot, 7)'),
    'inventory_removeItem': Ext(0x1C1CB0, 'iiii', 0, 'n', '(slot, index, bag, 0)'),
})
EXTERNALS['playerProjectile_ctor'].stack = 8
SKILL_BODIES.update({0x319710: (1, 'fireaxe_can_use'), 0x31979C: (2, 'fireaxe_cast'), 0x319EA0: (5, 'skill_mana_cost'),
                     0x31A04C: (1, 'coldaxe_can_use'), 0x31A0D8: (2, 'coldaxe_cast'), 0x31A7D4: (5, 'skill_mana_cost')})
MODELLED.update({'SkillFireAxe_canUse': 0x319710, 'SkillFireAxe_cast': 0x31979C, 'SkillFireAxe_manaCost': 0x319EA0,
                 'SkillColdAxe_canUse': 0x31A04C, 'SkillColdAxe_cast': 0x31A0D8, 'SkillColdAxe_manaCost': 0x31A7D4})


class SharedClasses:
    """Ids 81-86 are further static objects of six classes whose first ids lie below 69
    (Critical Hit 33 / 53 / 81, Riposte 9 / 82, Dodge 2 / 83, Cyclone 41 / 84, Root 31 / 32 /
    52 / 85, Healing 55 / 86).  The object's id (+0x64) only selects its name and numbers;
    the statistics getters of all six ids are covered with the rest.  Of the class code,
    this module has what is small: Riposte's counter-attack, Dodge's fraction and Healing.
    Critical Hit, Cyclone and Root are not modelled here: their classes belong to the ranges
    of ids 1-68 (tools/ref_skills_a.py, tools/ref_skills_b.py)."""
    HEAL_VT = 0x519E20
    HEAL_LUMP, HEAL_SOUND, HEAL_PARTICLE = 0x550488, 0x550490, 0x8E6040
    HEAL_SHARE = 0x3C71AA2E                     # 0.014750047: 68 frames of it make 1.003
    RIPOSTE_PARTICLES = (0x8E5AA0, 0x8E5AF0)

    def riposte_cast(self, skill=0, level=0, caster=0, pos=None, facing=0):
        """SkillRiposte_cast 0x2ddb90: returns 0 (kind 3, never cast)."""
        return 0

    def riposte_counter_attack(self, skill, victim, attacker, rank):
        """SkillRiposte_counterAttack 0x2ddccc (skill, victim, attacker, rank); damage_apply
        calls it for a player victim, once for id 9 and once for id 82.  Nothing at rank 0.
        dmg = slot 12 (0, rank, victim, cap 10), chance = slot 12 (1, ...).  ONE SHARED DRAW
        r, always; trunc(r / 65536 x 100) < chance goes on: the victim flashes (both quads
        0x82, 0x82, 0x83, 0x55); if its model has no sample points nothing more; else 200
        particle steps drawn from the COSMETIC generator 0x404460 (one draw and a ball
        point each), a SECOND SHARED DRAW r2 and damage_apply(attacker, victim as the
        attacker, 100000, 0, 0, flags 0x40, an empty descriptor, no-critical 1; dmg, dmg +
        dmg x (r2 / 65536) x 0.19999999)."""
        u32 = self.u32
        if not s32(rank):
            return
        damage = s32(self.skill_call(skill, 12, 0, rank, victim, 10))
        chance = s32(self.skill_call(skill, 12, 1, rank, victim, 10))
        if not C.to_int(C.mul(C.mul(C.from_int(self.draw()), F_2M16), 0x42C80000)) < chance:
            return
        self.flash(victim, 1, 0x82, 0x82, 0x83, 0x55)
        self.flash(victim, 2, 0x82, 0x82, 0x83, 0x55)
        points = s32(self.call('model_getSamplePointCount', self.vcall(victim, 16)))
        if not points:
            return
        for step in range(200):
            model = self.vcall(victim, 16)
            index = c_rem(self.cosmetic_draw(), points)
            point = tuple(self.call('model_getSamplePoint', model, victim + 0x114, self.vec(victim + 0x10),
                                    self.s16(victim + 0x38), index, 0, 0, ONE))
            while True:
                ball = []
                for _ in range(3):
                    share = C.mul(C.from_int(self.cosmetic_draw()), F_2M16)
                    ball.append(C.sub(C.add(share, share), ONE))
                if not C.lt(ONE, C.add(C.add(C.mul(ball[0], ball[0]), C.mul(ball[1], ball[1])), C.mul(ball[2], ball[2]))):
                    break
            toward = tuple(C.sub(u32(attacker + 0x10 + 4 * k), u32(victim + 0x10 + 4 * k)) for k in range(3))
            self.call('particle_spawn', self.RIPOSTE_PARTICLES[0], point, toward, ZERO)
            if step & 1:
                self.call('particle_spawn', self.RIPOSTE_PARTICLES[1], point,
                          tuple(C.mul(v, 0x424ABC67) for v in ball), ZERO)
        low = C.from_int(damage)
        high = C.add(low, C.mul(C.mul(low, C.mul(C.from_int(self.draw()), F_2M16)), F_0_2))
        self.call('damage_apply', attacker, victim, 100000, 0, 0, 0x40, desc(), 1, low, high)

    def dodge_mana_cost(self, skill, level):
        """SkillDodge_manaCost 0x2e8a88: slot 14 (level, 1) is asked, the result is 0.0."""
        self.skill_call(skill, 14, level, 1)
        return ZERO

    def dodge_fraction(self, skill, rank):
        """SkillDodge_getStat0Fraction 0x2e8ac0 (skill, rank) -> 0.0 at rank 0, else slot 10
        (0, rank) x 0.01: MissileWeapon_onTouch's chance that a player dodges a missile
        (the larger of ids 2 and 83)."""
        if not s32(rank):
            return ZERO
        level = self.skill_call(skill, 14, rank, 1)
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), F_0_01)

    def healing_cast(self, skill, level, caster, pos, facing):
        """SkillHealing_cast 0x2e8cf8: level through slot 14 (level, 0xe); pool_new(0x24);
        the constructor."""
        level = self.skill_call(skill, 14, level, 0xE)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.healing_spell_ctor(spell, level, caster, skill)
        return spell

    def healing_spell_ctor(self, spell, level, caster, skill):
        """SpellHealing_ctor 0x2e8ec8.  The Spell base (ONE SHARED DRAW); a sound on the
        caster; a GlowingShaft object at the caster (pool_new(0x5c); a GameObject, its
        shared draw inside the callee); a particle group +0x20; clock +0x18 = 0; the
        owner's amount per frame +0x1c = its maximum hit points x 0.014750047 x slot 12 (0,
        level, owner, cap) x 0.01 - the maximum from the player record (+0xb0) with cap 10
        for a player, from the object (+0x22c) with cap 20 otherwise."""
        u32, w32 = self.u32, self.w32
        self.spell_base(spell, level, caster, skill, self.HEAL_VT)
        self.call('sound_playOnObject', self.call('res_find', self.HEAL_LUMP, self.HEAL_SOUND), u32(spell + 0xC), ONE)
        block = self.call('pool_new', 0x5C)
        if block:
            self.call('GlowingShaft_ctor', block, self.vec(u32(spell + 0xC) + 0x10), 0x5A, 0xFA, 200, 100)
        w32(spell + 0x20, self.call('particleGroup_create'))
        owner = u32(spell + 0xC)
        w32(spell + 0x18, 0)
        if not u32(owner + 0xC) & 0x40:
            percent = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), owner, 0x14)
            most = u32(u32(spell + 0xC) + 0x22C)
        else:
            percent = self.skill_call(u32(spell + 8), 12, 0, self.s8(spell), owner, 10)
            most = u32(self.record(owner) + 0xB0)
        w32(spell + 0x1C, self._healing_amount(most, percent))

    def _healing_amount(self, most, percent):
        """(maximum hit points x 0.014750047) x (percent x 0.01), in that association."""
        return C.mul(C.mul(most, self.HEAL_SHARE), C.mul(C.from_int(s32(percent)), F_0_01))

    def _healing_flash(self, spell, obj):
        if C.lt(self.u32(spell + 0x18), 0x3E050EF8):
            self.flash(obj, 1, 0x35, 0x14, 0xD, 0x32)
            self.flash(obj, 2, 0x35, 0x14, 0xD, 0x32)

    def healing_spell_run(self, spell, pos=None, facing=0):
        """SpellHealing_run 0x2e90b8, once per frame of the owner, for 68 frames.

        R = slot 12 (1, level, owner, cap 20) x 12, an integer.
        Owner not a player, and only while it is a live creature: world_collectObjectsInBox
        (position -/+ R, capacity 128); the owner itself and everything its slot 21 ("is
        ally") accepts, within R in 2-D, gains hit points on the object (+0x228): the
        owner its amount +0x1c, others their own maximum x 0.014750047 x slot 12 (2) x
        0.01.  No "below maximum" test and no clamp.
        Owner a player: every player of the alive list within R in 3-D (in PvP mode A only
        those the owner's slot 22 accepts) whose record has hp + 1 <= max hp gains the
        same way on the record (+0xac), again without a clamp.
        Everyone healed flashes during the first 0.13 s.  With R >= 1: level - (tier-1
        first level of statistic 1) + 5 ground particles, ONE OWN DRAW each, around
        net_objOrGhost(owner).  clock +0x18 += 1/60; above 1.1299399 the spell destroys
        itself."""
        u32, w32 = self.u32, self.w32
        owner = u32(spell + 0xC)
        reach = s32(self.skill_call(u32(spell + 8), 12, 1, self.s8(spell), owner, 0x14)) * 12
        owner = u32(spell + 0xC)
        square = C.from_int(s32(reach * reach))
        if not u32(owner + 0xC) & 0x40:
            if u32(owner + 0xC) & 0x28 == 0x20:
                span = C.from_int(reach)
                at = self.vec(owner + 0x10)
                found = self.call('world_collectObjectsInBox', tuple(C.sub(v, span) for v in at),
                                  tuple(C.add(v, span) for v in at), 0x80)
                for other in found or ():
                    owner = u32(spell + 0xC)
                    if other != owner and not self.vcall(owner, 21, other):
                        continue
                    owner = u32(spell + 0xC)
                    dy = C.sub(u32(owner + 0x14), u32(other + 0x14))
                    dx = C.sub(u32(owner + 0x10), u32(other + 0x10))
                    if not C.le(C.add(C.mul(dx, dx), C.mul(dy, dy)), square):
                        continue
                    if other == owner:
                        amount = u32(spell + 0x1C)
                    else:
                        percent = self.skill_call(u32(spell + 8), 12, 2, self.s8(spell), owner, 0x14)
                        amount = self._healing_amount(u32(other + 0x22C), percent)
                    w32(other + 0x228, C.add(u32(other + 0x228), amount))
                    self._healing_flash(spell, other)
        else:
            near = []
            for index in range(max(self.s32(G_ALIVE_COUNT), 0)):
                slot = u32(G_ALIVE_LIST + 4 * index)
                if self.s32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, self.player_obj(slot)):
                    continue
                owner, other = u32(spell + 0xC), self.player_obj(slot)
                gap = [C.sub(u32(owner + 0x10 + 4 * k), u32(other + 0x10 + 4 * k)) for k in range(3)]
                if C.le(C.add(C.add(C.mul(gap[0], gap[0]), C.mul(gap[1], gap[1])), C.mul(gap[2], gap[2])), square):
                    near.append(slot)
            for slot in near:
                rec = (G_PLAYERS + s32(slot) * REC_SIZE) & M32
                if C.le(C.add(u32(rec + 0xAC), ONE), u32(rec + 0xB0)):
                    if self.player_obj(slot) == u32(spell + 0xC):
                        w32(rec + 0xAC, C.add(u32(rec + 0xAC), u32(spell + 0x1C)))
                    else:
                        percent = self.skill_call(u32(spell + 8), 12, 2, self.s8(spell), u32(spell + 0xC), 0x14)
                        w32(rec + 0xAC, C.add(u32(rec + 0xAC), self._healing_amount(u32(rec + 0xB0), percent)))
                self._healing_flash(spell, self.player_obj(slot))
        if reach >= 1:
            count = self.s8(spell) - self.s16(u32(spell + 8) + 0x10) + 5
            ghost = self.call('net_objOrGhost', u32(spell + 0xC))
            self.call('particleGroup_begin', u32(spell + 0x20))
            matrix = C.mat34_set_pos_rot_z(self.vec(ghost + 0x10), s16(u32(G_SIM_FRAME) * 0x5F))
            self.call('particleGroup_setMatrix', u32(spell + 0x20), 'stack')
            for _ in range(max(count, 0)):
                angle = self.spell_rand(spell)
                local = (C.mul(C.cos16(angle), C.from_int(reach)), C.mul(C.sin16(angle), C.from_int(reach)), ZERO)
                world = C.mat34_transform_point(matrix, local)
                drop = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(ghost + 0x18))
                if C.le(drop, 0x42900000) and C.le(0xC2900000, drop):
                    self.call('particle_spawn', self.HEAL_PARTICLE, (local[0], local[1], drop), (ZERO, ZERO, ONE), ZERO)
            self.call('particleGroup_end', u32(spell + 0x20))
        clock = C.add(u32(spell + 0x18), DT)
        w32(spell + 0x18, clock)
        if C.lt(0x3F90A1DF, clock):
            self.spell_destroy(spell)


EXTERNALS.update({
    'GlowingShaft_ctor': Ext(0x202FF0, 'pviiii', 0, 'n', '(block, position, four integers): a GameObject'),
})
SKILL_BODIES.update({0x2DDB90: (2, 'riposte_cast'), 0x2E8A88: (5, 'dodge_mana_cost'), 0x2E8CF8: (2, 'healing_cast'),
                     0x2E8E94: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x2E90B8: (2, 'healing_spell_run')})
SPELL_TABLES.add(SharedClasses.HEAL_VT)
MODELLED.update({'SkillRiposte_cast': 0x2DDB90, 'SkillRiposte_counterAttack': 0x2DDCCC, 'SkillDodge_manaCost': 0x2E8A88,
                 'SkillDodge_getStat0Fraction': 0x2E8AC0, 'SkillHealing_cast': 0x2E8CF8,
                 'SkillHealing_manaCost': 0x2E8E94, 'SpellHealing_ctor': 0x2E8EC8, 'SpellHealing_run': 0x2E90B8})


class CriticalHit:
    """81 - `berserkercriticalhit`: the berserker's object of the class SkillCriticalHit
    (ids 33, 53, 81).  A timed spell on the caster; while it is there damage_apply adds
    statistic 0 percent to the critical-hit chance of the caster and of players inside its
    aura.  The class is the same code for all three ids; the id (+0x64) is read in one
    place only, the particle count of the run."""
    CH_VT = 0x519C28
    CH_PARTICLE = 0x8E5FA0
    CH_FIRST_LEVEL = {0x35: 1, 0x21: 10, 0x51: 5}       # id -> the level its statistic 1 starts at

    def criticalhit_can_use(self, skill, caster):
        """SkillCriticalHit_canUse 0x2e7224: 1 unless the caster carries a SpellCriticalHit."""
        return 0 if self.find_spell_by_type(caster, TYPEINFO['CriticalHit']) else 1

    def criticalhit_cast(self, skill, level, caster, pos, facing):
        """SkillCriticalHit_cast 0x2e74b0: pool_new(0x5c), the constructor (the level is NOT
        passed through slot 14)."""
        spell = self.call('pool_new', 0x5C)
        if spell:
            self.criticalhit_spell_ctor(spell, level, caster, skill)
        return spell

    def criticalhit_mana_cost(self, skill, level):
        """SkillCriticalHit_manaCost 0x2e7690: slot 15 (level, 0x14)."""
        return self.skill_call(skill, 15, level, 0x14)

    def criticalhit_spell_ctor(self, spell, level, caster, skill):
        """SpellCriticalHit_ctor 0x2e7988: the Spell base (ONE SHARED DRAW); a light record
        at +0x1c at the caster; time left +0x18 = (float) slot 10 (2, level); a particle
        group +0x58."""
        self.spell_base(spell, level, caster, skill, self.CH_VT)
        self.light_record(spell + 0x1C, (0xD7, 0x40, 0x40, 0), 0x42F00000, 0x3891A2B3, ZERO, self.vec(caster + 0x10))
        self.call('light_link', spell + 0x1C)
        seconds = s32(self.skill_call(self.u32(spell + 8), 10, 2, self.s8(spell)))
        self.w32(spell + 0x18, C.from_int(seconds))
        self.w32(spell + 0x58, self.call('particleGroup_create'))

    def criticalhit_set_tint(self, spell, creature):
        """SpellCriticalHit_setTint 0x2e7f58: flash quad 1 = (0x44, 0x0e, 0x18, 0x0f)."""
        self.flash(creature, 1, 0x44, 0xE, 0x18, 0xF)

    def criticalhit_spell_run(self, spell, pos=None, facing=0):
        """SpellCriticalHit_run 0x2e7acc, once per frame of the owner.  time left +0x18 -=
        1/60; below 0 the spell destroys itself.  Otherwise the owner is tinted; the light
        follows the owner for the first two seconds (fading through the second) and is
        unlinked after them; with R = slot 10 (1, level) x 12 > 0: level - first + 14 ground
        particles (ONE OWN DRAW each) around net_objOrGhost(owner), `first` being 1, 10 or
        5 for the ids 53, 33, 81; and every OTHER player of the alive list within R of the
        owner in 2-D (in PvP mode A only one the owner's slot 22 accepts) is tinted."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        left = C.sub(u32(spell + 0x18), DT)
        w32(spell + 0x18, left)
        if C.lt(left, ZERO):
            if spell:
                self.spell_destroy(spell)
            return
        self.criticalhit_set_tint(spell, u32(spell + 0xC))
        seconds = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))
        age = C.sub(C.from_int(seconds), u32(spell + 0x18))
        light = spell + 0x1C
        if C.le(age, TWO):
            owner = u32(spell + 0xC)
            self.wvec(light + 0x30, (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), F_60)))
            self.call('light_relink', light)
            if C.lt(ONE, age):
                dim = C.to_int(C.mul(C.sub(TWO, age), 0x42800000))
                red = C.to_int(C.mul(C.sub(TWO, age), 0x43570000))
                for off, value in ((0x2A, dim), (0x26, red), (0x2E, red), (0x30, dim), (0x28, dim), (0x32, dim)):
                    w16(spell + off, value)
        else:
            self.call('light_unlink', light)
        skill = u32(spell + 8)
        first = self.CH_FIRST_LEVEL.get(self.s32(skill + 0x64), 1)
        level = self.s8(spell)
        reach = s32(self.skill_call(skill, 10, 1, level)) * 12
        ghost = self.call('net_objOrGhost', u32(spell + 0xC))
        if reach > 0:
            self.call('particleGroup_begin', u32(spell + 0x58))
            matrix = C.mat34_set_pos_rot_z(self.vec(ghost + 0x10), s16(u32(G_SIM_FRAME) * 0x76))
            self.call('particleGroup_setMatrix', u32(spell + 0x58), 'stack')
            for _ in range(max(level - first + 0xE, 0)):
                angle = self.spell_rand(spell)
                local = (C.mul(C.cos16(angle), C.from_int(reach)), C.mul(C.sin16(angle), C.from_int(reach)), ZERO)
                world = C.mat34_transform_point(matrix, local)
                drop = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(ghost + 0x18))
                if C.le(drop, 0x42900000) and C.le(0xC2900000, drop):
                    self.call('particle_spawn', self.CH_PARTICLE, (local[0], local[1], drop), (ZERO, ZERO, ONE), ZERO)
            self.call('particleGroup_end', u32(spell + 0x58))
        square = C.from_int(s32(reach * reach))
        for index in range(max(self.s32(G_ALIVE_COUNT), 0)):
            owner = u32(spell + 0xC)
            other = self.player_obj(u32(G_ALIVE_LIST + 4 * index))
            if other == owner:
                continue
            if self.s32(G_PVP_MODE_A) and not self.vcall(owner, 22, other):
                continue
            dy = C.sub(u32(u32(spell + 0xC) + 0x14), u32(other + 0x14))
            dx = C.sub(u32(u32(spell + 0xC) + 0x10), u32(other + 0x10))
            if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), square):
                self.criticalhit_set_tint(spell, other)

    def criticalhit_bonus_for(self, skill, attacker, rank):
        """SkillCriticalHit_critBonusFor 0x2e76c4 (skill, attacker, rank) -> the fraction
        damage_apply adds to a player attacker's critical chance; it asks once for each of
        the ids 33, 53, 81 with that id's object and the attacker's rank in it.

        With a rank and a SpellCriticalHit on the attacker (of whichever id): level = rank.
        Otherwise the first player of the alive list, other than the attacker's slot, that
        is within 1000 units in 3-D (in PvP mode A only one whose slot 22 accepts the
        attacker), carries a SpellCriticalHit, has a best rank r > 0 among ids 53, 81, 33,
        and stands within THIS id's slot 10 (1, r) x 12 in 2-D: level = r.  Else level 0.
        The result is slot 10 (0, level) x 0.01 (the level through slot 14), 0.0 at level 0."""
        u32 = self.u32
        level = 0
        if s32(rank) and self.find_spell_by_type(attacker, TYPEINFO['CriticalHit']):
            level = s32(rank)
        else:
            for index in range(max(self.s32(G_ALIVE_COUNT), 0)):
                slot = u32(G_ALIVE_LIST + 4 * index)
                if slot == u32(attacker + 0x3C8):
                    continue
                other = self.player_obj(slot)
                gap = [C.sub(u32(other + 0x10 + 4 * k), u32(attacker + 0x10 + 4 * k)) for k in range(3)]
                if not C.lt(C.add(C.add(C.mul(gap[0], gap[0]), C.mul(gap[1], gap[1])), C.mul(gap[2], gap[2])),
                            0x49742400):
                    continue
                if self.s32(G_PVP_MODE_A) and not self.vcall(other, 22, attacker):
                    continue
                if not self.find_spell_by_type(self.player_obj(slot), TYPEINFO['CriticalHit']):
                    continue
                best = max(s32(self.call('player_getSkillRank', slot, ident)) for ident in (0x35, 0x51))
                best = max(best, s32(self.call('player_getSkillRank', slot, 0x21)))
                if not best:
                    continue
                reach = C.from_int(s32(self.skill_call(skill, 10, 1, best)) * 12)
                other = self.player_obj(slot)
                dy = C.sub(u32(other + 0x14), u32(attacker + 0x14))
                dx = C.sub(u32(other + 0x10), u32(attacker + 0x10))
                if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(reach, reach)):
                    level = best if best >= 1 else 0
                    break
        level = s32(self.skill_call(skill, 14, level, 0x14))
        if not level:
            return ZERO
        return C.mul(C.from_int(s32(self.skill_call(skill, 10, 0, level))), F_0_01)


TYPEINFO['CriticalHit'] = 0x3CF000
SKILL_BODIES.update({0x2E7224: (1, 'criticalhit_can_use'), 0x2E74B0: (2, 'criticalhit_cast'),
                     0x2E7690: (5, 'criticalhit_mana_cost')})
SPELL_BODIES.update({0x2E7ACC: (2, 'criticalhit_spell_run')})
SPELL_TABLES.add(CriticalHit.CH_VT)
MODELLED.update({'SkillCriticalHit_canUse': 0x2E7224, 'SkillCriticalHit_cast': 0x2E74B0,
                 'SkillCriticalHit_manaCost': 0x2E7690, 'SkillCriticalHit_critBonusFor': 0x2E76C4,
                 'SpellCriticalHit_ctor': 0x2E7988, 'SpellCriticalHit_run': 0x2E7ACC,
                 'SpellCriticalHit_setTint': 0x2E7F58})


class Root:
    """85 - `shamanroot`: the shaman's object of the class SkillRoot (ids 31, 32, 52, 85).
    The cast puts a SpellRoot on up to statistic 0 enemies in a wedge ahead; after half a
    second ONE SHARED DRAW decides, per victim, whether the root takes."""
    ROOT_VT = 0x519B70
    ROOT_LUMP, ROOT_SOUND, ROOT_WARN = 0x550188, 0x550190, 0x550178
    ROOT_PARTICLES = {'pending': 0x8E5F00, 'burst': 0x8E5F50, 'hold': 0x8E5EB0}
    ROOT_DELAY = 0x3F04DCCA                     # 0.518994 s

    def root_can_use(self, skill, caster):
        """SkillRoot_canUse 0x2e6534: a player in PvP mode A is refused, with a warning text
        shown for 90 frames; everyone else is allowed."""
        if not self.s32(G_PVP_MODE_A) or not self.u32(caster + 0xC) & 0x40:
            return 1
        self.call('hud_showMessage', self.call('text_lookup', self.ROOT_WARN), 0x5A, self.u32(caster + 0x3C8), 0)
        return 0

    def root_cast(self, skill, level, caster, pos, facing):
        """SkillRoot_cast 0x2e6598 -> 0.  Level through slot 14 (level, 0x14); a sound on the
        caster; world_collectObjectsInArc(pos, facing, no owner; 248, 120 degrees, 0) and,
        walking the list until it ends or slot 10 (0, level) victims are taken: an entry is
        taken when the caster's slot 20 calls it an enemy (not asked without a caster), it
        has no object flag 0x1000000, creature_bossRank is 0 and its root timer +0x314 is
        below 1.  Each taken entry gets pool_new(0x34), a SpellRoot (ONE SHARED DRAW) and
        creature_addSpell (with 0 when the pool had no block)."""
        u32 = self.u32
        facing = s16(facing)
        level = self.skill_call(skill, 14, level, 0x14)
        self.call('sound_playOnObject', self.call('res_find', self.ROOT_LUMP, self.ROOT_SOUND), caster, ONE)
        most = s32(self.skill_call(skill, 10, 0, level))
        found = self.call('world_collectObjectsInArc', tuple(pos), facing, 0, 0x43780000, 0x42F00000, ZERO)
        taken = 0
        for obj in found or ():
            if not taken < most:
                break
            if caster and not self.vcall(caster, 20, obj):
                continue
            if u32(obj + 0xC) & 0x1000000 or self.call('creature_bossRank', obj) or not self.s16(obj + 0x314) < 1:
                continue
            spell = self.call('pool_new', 0x34)
            if spell:
                self.root_spell_ctor(spell, level, obj, skill)
            self.call('creature_addSpell', obj, spell)
            taken += 1
        self.handle_clear('stack')
        self.handle_clear('stack')
        return 0

    def root_spell_ctor(self, spell, level, victim, skill):
        """SpellRoot_ctor 0x2e68c8 (spell, level, victim, skill): the Spell base with the
        victim as owner (ONE SHARED DRAW); clock +0x18 = 0, phase +0x1c = 0, a particle
        group +0x24, the spot +0x28 = the victim's position, seconds +0x20 = slot 10 (1,
        level)."""
        w32 = self.w32
        self.spell_base(spell, level, victim, skill, self.ROOT_VT)
        w32(spell + 0x18, 0)
        w32(spell + 0x1C, 0)
        w32(spell + 0x24, self.call('particleGroup_create'))
        self.wvec(spell + 0x28, self.vec(victim + 0x10))
        w32(spell + 0x20, self.skill_call(self.u32(spell + 8), 10, 1, self.s8(spell)))

    def root_spell_run(self, spell, pos=None, facing=0):
        """SpellRoot_run 0x2e699c, once per frame of the victim.  clock +0x18 += 1/60.
          phase 0: seven particles (two OWN draws each).  Once clock > 0.518994: ONE SHARED
              DRAW r; slot 10 (2, level) <= r % 100 + 1 fails: a burst of 100 particles (a
              ball point each) and the spell destroys itself.  Otherwise the victim
              flashes, a victim that is NOT a player gets its root timer +0x314 = seconds x
              60, and the phase becomes 1.
          phase 1: 22 particles on model sample points (one OWN draw and a ball point
              each); a PLAYER victim is pulled back: knock-back speed +0x2e8 = 4 x its 2-D
              distance from the spot, knock-back angle +0x2e0 = -0x4000 - atan2_16(dx, dy).
        When (float) seconds < clock - 0.518994 the spell destroys itself."""
        u32, w32 = self.u32, self.w32
        clock = C.add(u32(spell + 0x18), DT)
        w32(spell + 0x18, clock)
        phase = u32(spell + 0x1C)
        if phase == 0:
            victim = u32(spell + 0xC)
            C.mat34_set_pos_rot_z(self.vec(victim + 0x10), self.s16(victim + 0x38))
            self.call('particleGroup_begin', u32(spell + 0x24))
            self.call('particleGroup_setMatrix', u32(spell + 0x24), 'stack')
            for _ in range(7):
                around = []
                for _axis in range(2):
                    share = C.add(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), 0xBF000000)
                    around.append(C.mul(C.mul(share, u32(u32(spell + 0xC) + 0x1C)), 0x3F9FDEBD))
                point = (around[0], around[1], C.add(u32(u32(spell + 0xC) + 0x20), F_12))
                self.call('particle_spawn', self.ROOT_PARTICLES['pending'], point, (ZERO, ZERO, 0xC2980000), ZERO)
            self.call('particleGroup_end', u32(spell + 0x24))
            if C.lt(self.ROOT_DELAY, u32(spell + 0x18)):
                roll = self.draw()
                chance = s32(self.skill_call(u32(spell + 8), 10, 2, self.s8(spell)))
                victim = u32(spell + 0xC)
                if chance <= roll % 100 + 1:
                    point = (u32(victim + 0x10), u32(victim + 0x14), C.add(u32(victim + 0x18), u32(victim + 0x20)))
                    for _ in range(100):
                        ball = self.spell_ball(spell)
                        self.call('particle_spawn', self.ROOT_PARTICLES['burst'], point,
                                  tuple(C.mul(v, 0x41A80000) for v in ball), ZERO)
                    self.spell_destroy(spell)
                    return
                self.flash(victim, 1, 4, 0x5C, 0, 0x51)
                self.flash(victim, 2, 4, 0x5C, 0, 0x51)
                if not u32(victim + 0xC) & 0x40:
                    self.w16(victim + 0x314, u32(spell + 0x20) * 0x3C)
                w32(spell + 0x1C, u32(spell + 0x1C) + 1)
        elif phase == 1:
            victim = u32(spell + 0xC)
            points = s32(self.call('model_getSamplePointCount', self.vcall(victim, 16)))
            for _ in range(22):
                victim = u32(spell + 0xC)
                model = self.vcall(victim, 16)
                index = c_rem(self.spell_rand(spell), points)
                victim = u32(spell + 0xC)
                point, _normal = self.call('model_getSamplePoint', model, victim + 0x114, self.vec(victim + 0x10),
                                           self.s16(victim + 0x38), index, 1, 0, ONE)
                self.spell_ball(spell)
                self.call('particle_spawn', self.ROOT_PARTICLES['hold'], tuple(point), (ZERO, ZERO, ZERO), ZERO)
            victim = u32(spell + 0xC)
            if u32(victim + 0xC) & 0x40:
                dx = C.sub(u32(victim + 0x10), u32(spell + 0x28))
                dy = C.sub(u32(victim + 0x14), u32(spell + 0x2C))
                w32(victim + 0x2E8, C.mul(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), 0x40800000))
                angle = C.atan2_16(C.sub(u32(victim + 0x10), u32(spell + 0x28)),
                                   C.sub(u32(victim + 0x14), u32(spell + 0x2C)))
                self.w16(u32(spell + 0xC) + 0x2E0, -0x4000 - angle)
        if C.lt(C.from_int(self.s32(spell + 0x20)), C.sub(u32(spell + 0x18), self.ROOT_DELAY)) and spell:
            self.spell_destroy(spell)


SKILL_BODIES.update({0x2E6534: (1, 'root_can_use'), 0x2E6598: (2, 'root_cast'), 0x2E6894: (5, 'skill_mana_cost')})
SPELL_BODIES.update({0x2E699C: (2, 'root_spell_run')})
SPELL_TABLES.add(Root.ROOT_VT)
MODELLED.update({'SkillRoot_canUse': 0x2E6534, 'SkillRoot_cast': 0x2E6598, 'SkillRoot_manaCost': 0x2E6894,
                 'SpellRoot_ctor': 0x2E68C8, 'SpellRoot_run': 0x2E699C})


# ---------------------------------------------------------------------------------------
# The model: every section above on the shared machinery
# ---------------------------------------------------------------------------------------
class Model(Root,
            CriticalHit,
            SharedClasses,
            ThrownAxes,
            SummonItems,
            BloodLust,
            RaiseArmy,
            SummonBadger,
            DiseaseBlade,
            Passives,
            BattleCry,
            Roar,
            PoisonBolt,
            Drowsy,
            ConeOfShock,
            Storms,
            UnspokenWord,
            WaveOfFlame,
            FrostArmor,
            SpiritShield,
            Retribution,
            Base):
    """Skills 69-101 on a memory image.  See the module docstring."""
