#!/usr/bin/env python3
"""ref_skills_b.py - reference model of the skills with ids 35-68 of Champions: Return to
Arms (SLUS_209.73, US v2.00): the shared Skill / Spell / projectile machinery first, then
the skills of the range one by one.

A research tool, not game code.  Every method was written from the instructions at the
address in its docstring and is compared with that code, executed under tools/ee_emu.py,
by tools/difftest_skills_b.py.  docs/spec/skills-35-68.md is the prose specification this
follows; docs/spec/skills-35-68-executed.md says what the comparison covers and where the
specification turned out wrong.  Standard library only.  No game data is embedded: the
statistic tables are read from the Skill objects in the memory image (which the test fills
by running the executable's own static initialiser), and strings, particle definitions and
class tables are named by address only.

How it sees the game: as tools/ref_creature.py and tools/ref_arena_monsters.py do - a
memory image (load/store), callbacks for everything outside the model (EXTERNALS extends
their lists), canonical arguments (integers as unsigned 32-bit, floats as 32-bit patterns,
a vector as a tuple of three patterns).  Unlike those two, positions are passed to the
methods here the way the original passes them: as the ADDRESS of three floats.

What is inside the model
    Skill base     slots 1, 2, 5, 8, 10-15 of the base class (statistics by tier and level)
    Spell base     the inlined base constructor (one shared draw), Spell_rand, attaching
                   (creature_addSpell), the per-tick walk of an owner's spells
                   (Creature_updateSpells, slot 17), a spell ending itself (its slot 1)
    handle lists   handle_link, handle_clear, handle_removeNode, list_push and the list
                   iterator, at memory level (the node pool's free list is at 0x864ea8)
    projectiles    Projectile_ctor and obj_moveAndCollide
    the skills     see SKILLS at the end of the file: one entry per id with the functions
                   modelled for it

Virtual calls
    Skill (table at +0x60), Spell (table at +0x14) and effect objects (table at +0x48)
    are resolved through the table in memory: a function this module has runs as a method,
    anything else is the callback 'Skill.v<n>', 'Spell.v<n>' or 'Creature.v<n>' (every
    virtual call on a creature or another world object is a callback here).

Shared-seed draws (0x404464) are counted in Model.draws.  Constructing a GameObject is a
callback ('GameObject_ctor', tools/ref_objects.py owns it) that draws the shared seed
once; game_object_ctor() counts that draw.
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
G_COSMETIC_SEED = 0x404460                      # presentation generator (per machine)
G_SEED3 = RC.G_SEED3                            # 0x404468 third generator (per machine)
G_SIM_FRAME = RC.G_SIM_FRAME
G_WORLD = RC.G_WORLD
G_LEVEL_FLAGS = RC.G_LEVEL_FLAGS
G_NETWORK_MODE = RC.G_NETWORK_MODE
G_NUM_PLAYERS = RC.G_NUM_PLAYERS
G_PLAYERS, REC_SIZE, REC_OBJ = RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ
G_SKILL_TABLE = 0x41B170                        # g_skillTable[id], ids 1-101
G_HANDLE_FREE = 0x864EA8                        # head of the free list of handle nodes
G_FORCE_GHOST_REBASE = 0x402797                 # s8: rebuild the prediction copy (per machine)
G_PADS = 0x41BFB8                               # 0x58 bytes per player slot
G_PVP_MODE_A, G_PVP_MODE_B = 0x4F711C, AM.G_PVP_MODE_B
G_ALIVE_COUNT, G_ALIVE_LIST = RC.G_LOCAL_ALIVE_COUNT, RC.G_LOCAL_ALIVE_LIST

VT_SKILL, VT_SPELL, VT_GAMEOBJECT, VT_PROJECTILE = 0x512670, 0x515BA0, 0x5122A8, 0x5120B8

# The model's own scratch for what the original keeps in its stack frames (list heads,
# iterators).  A caller that runs the model beside the original must map this range; an
# address in it is reported to callbacks as 'stack'.
MODEL_STACK, MODEL_STACK_SIZE = 0x01E00000, 0x10000

# float patterns
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16
DT = RC.DT                                      # 0x3c888888, 1/60 truncated
F_0_01 = 0x3C23D70A
F_0_1 = 0x3DCCCCCC
F_2 = 0x40000000
F_12, F_24, F_72 = 0x41400000, 0x41C00000, 0x42900000

SKILL_IDS = tuple(range(35, 69))

# The original functions of the shared machinery (name -> address).  SKILLS at the end of
# the file adds the per-skill ones; tools/difftest_skills_b.py runs exactly MODELLED for
# real.
MODELLED = {
    'Skill_canUse_base': 0x3C8218, 'Skill_cast_base': 0x3C8220, 'Skill_manaCost_base': 0x3C82A8,
    'Skill_getStatRange': 0x3C82E4, 'Skill_getStat': 0x3C85FC, 'Skill_getStatTier2': 0x3C8690,
    'Skill_getStatFor': 0x3C87F0, 'Skill_getStatForHandle': 0x3C8864, 'Skill_adjustLevel': 0x3C88DC,
    'Skill_manaFromStat4': 0x3C88E4,
    'Spell_rand': 0x16A964, 'GameObject_rand': 0x1509D0,
    'handle_link': 0x1A1738, 'handle_clear': 0x1A1698, 'handle_removeNode': 0x1A1868, 'list_push': 0x1A1980,
    'iter_begin': 0x1A1A48, 'iter_next': 0x1A1B38, 'iter_end': 0x1A1AE8,
    'creature_addSpell': 0x11A838, 'Creature_updateSpells': 0x11A868,
    'Projectile_ctor': 0x150E48, 'obj_moveAndCollide': 0x1509F8,
}

# virtual bodies: function address -> method name
SKILL_BODIES = {
    0x3C8218: 'skill_can_use_base', 0x3C8220: 'skill_cast_base', 0x3C82A8: 'skill_mana_cost_base',
    0x3C82E4: 'skill_stat_range', 0x3C85FC: 'skill_get_stat', 0x3C8690: 'skill_get_stat_tier2',
    0x3C87F0: 'skill_get_stat_for', 0x3C8864: 'skill_get_stat_for_handle', 0x3C88DC: 'skill_adjust_level',
    0x3C88E4: 'skill_mana_from_stat4',
}
SPELL_BODIES = {}
OBJECT_BODIES = {}

EXTERNALS = dict(AM.EXTERNALS)
EXTERNALS.update({
    # --- text, HUD, sound, player
    'text_lookup': Ext(0x173C84, 'p', 0, 'i', '(key) -> wide text'),
    'hud_showMessage': Ext(0x1D92A0, 'piii', 0, 'n', '(text, frames, player slot, 0)'),
    'wstr_format': Ext(0x19EA78, 'iiiiipp', 8, 'n', '(five integers, buffer, format; eight floats)'),
    'wstr_copy': Ext(0x19E854, 'pp', 0, 'n', '(buffer, text)'),
    'player_voice': Ext(0x1B7BA8, 'ii', 0, 'n', '(slot, kind)'),
    'player_getSkillRank': Ext(0x1BF330, 'ii', 0, 'i', '(slot, skill id)'),
    'net_getCamYaw': Ext(0x13E0C8, 'i', 0, 'i', '(slot) -> the camera yaw carried in the input record'),
    'net_isLocalSlot': Ext(0x13E150, 'i', 0, 'i', '(slot) -> this machine plays that slot (per machine)'),
    # --- player mechanics
    'Player_animStep': Ext(0x1B9520, 'p', 1, 'i', '(player; speed) -> event bits'),
    'Player_move': Ext(0x1B4020, 'pipv', 0, 'i', '(player, mode, pad, external velocity) -> event bits'),
    'Player_meleeHit': Ext(0x1B6A98, 'ppii', 1, 'n', '(player, target, flag, flags; damage scale)'),
    # --- lights
    'light_link': Ext(0x148AF8, 'p', 0, 'n', '(light record)'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n', '(light record)'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n', '(light record)'),
    # --- world
    'world_collectInSphere': Ext(0x14AB80, 'viL', 1, 'n', '(centre, heading, list out; radius) -> objects'),
    'world_collectObjectsInArc': Ext(0x1614F0, 'viLp', 3, 'n', '(centre, heading, list out, filter; radius, '
                                     'arc in degrees, half width) -> objects, nearest first'),
    'vec3_hermite': Ext(0x162310, 'ovvvv', 1, 'n', '(out, p0, p1, m0, m1; t)'),
    # --- virtual calls on creatures and other world objects: (this, ...)
    'Creature.v1': Ext(0, 'pi', 0, 'n', 'destroy (3)'),
    'Creature.v6': Ext(0, 'pp', 0, 'n', 'touched by (other)'),
    'Creature.v12': Ext(0, 'piVp', 1, 'n', '(kind, position, source; amount): being aimed at / alerted'),
    'Creature.v39': Ext(0, 'pi', 0, 'i', 'Player: rank in a skill (id)'),
    'Spell.v4': Ext(0, 'p', 0, 'i', 'the value at spell +0x18'),
})
EXTERNALS['wstr_format'].stack = 2

# names the model answers itself, at memory level, wherever a tools/ref_creature.py method
# would have made them a callback
INTERNAL_CALLS = ('handle_link', 'handle_clear', 'handle_removeNode')


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row (the rule of
    ref_arena_monsters.shape_result, for the rows of this module): the integer or float
    result followed by every output the callee fills.  A list output (kind 'L') comes back
    as a Python list of objects; the model links them into its own list head with
    list_fill, exactly as the stub of the test does on the interpreter's side."""
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
        if kind in 'ipvelsSOWVD':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def list_fill(load, poke, head, objects):
    """Link `objects` into the handle list at `head` so that a walk from the head meets
    them in the given order: one node each, taken from the free list 0x864ea8 and pushed
    at the head (the store sequence of list_push 0x1a1980), last object first.  The stubs
    of world queries that hand back a list use this on both sides of the comparison."""
    for obj in reversed(list(objects)):
        node = load(G_HANDLE_FREE, 4)
        poke(G_HANDLE_FREE, 4, load(node, 4))
        poke(node + 0x10, 2, 0)
        first = load(head, 4)
        poke(node, 4, first)
        if first:
            poke(first + 4, 4, node)
        poke(node + 4, 4, head)
        poke(head, 4, node)
        poke(node + 0xC, 4, obj)
        poke(node + 8, 4, 0)


class Model(RC.Model):
    """Skills 35-68 on a memory image.  See the module docstring."""

    def __init__(self, mem, callbacks=None, external=()):
        RC.Model.__init__(self, mem, callbacks, external)
        self.sp = MODEL_STACK + MODEL_STACK_SIZE

    # =====================================================================================
    # Plumbing
    # =====================================================================================
    def call(self, name, *args):
        if name in INTERNAL_CALLS:
            return getattr(self, name)(*args)
        args = tuple(('stack' if MODEL_STACK <= (a & M32) < MODEL_STACK + MODEL_STACK_SIZE else a & M32)
                     if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def alloca(self, size):
        """Scratch for something the original keeps in its stack frame."""
        self.sp -= (size + 15) & ~15
        return self.sp

    def f32(self, a):
        return self.u32(a)

    def cstr(self, addr, limit=64):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(addr + len(out))
            if not b:
                break
            out.append(b)
        return bytes(out)

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48.  A body of OBJECT_BODIES (the effect
        objects of this module) runs here; anything else is the callback
        'Creature.v<slot>' - creatures, players and props alike."""
        table = self.u32(obj + 0x48)
        this = (obj + self.s16(table + 8 * slot)) & M32
        body = OBJECT_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Creature.v%d' % slot) not in self.external:
            return getattr(self, body)(this, *args)
        return self.call('Creature.v%d' % slot, this, *args)

    def skill_call(self, skill, slot, *args):
        """A virtual call on a Skill (table pointer at +0x60)."""
        table = self.u32(skill + 0x60)
        this = (skill + self.s16(table + 8 * slot)) & M32
        body = SKILL_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Skill.v%d' % slot) not in self.external:
            return getattr(self, body)(this, *args)
        return self.call('Skill.v%d' % slot, this, *args)

    def spell_call(self, spell, slot, *args):
        """A virtual call on a Spell (table pointer at +0x14)."""
        table = self.u32(spell + 0x14)
        this = (spell + self.s16(table + 8 * slot)) & M32
        body = SPELL_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Spell.v%d' % slot) not in self.external:
            return getattr(self, body)(this, *args)
        return self.call('Spell.v%d' % slot, this, *args)

    def table_call(self, cls, obj, table_offset, slot, *args):
        if cls == 'Spell':
            return self.spell_call(obj, slot, *args)
        if cls == 'Skill':
            return self.skill_call(obj, slot, *args)
        return RC.Model.table_call(self, cls, obj, table_offset, slot, *args)

    def is_player(self, obj):
        return bool(self.u32(obj + 0xC) & 0x40)

    def record(self, player):
        """The player record of a player object: g_players + slot (+0x3c8) x 0x4c30.  The
        slot is used as it is - the original has no range test at most sites."""
        return (G_PLAYERS + self.s32(player + 0x3C8) * REC_SIZE) & M32

    # =====================================================================================
    # Generators (docs/spec/skills-35-68.md 1.1)
    # =====================================================================================
    def spell_rand(self, spell):
        """Spell_rand 0x16a964: the spell's own generator at +0x10."""
        seed = (self.u32(spell + 0x10) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(spell + 0x10, seed)
        return seed >> 16

    def cosmetic_draw(self):
        """One draw from the presentation generator 0x404460 (per machine)."""
        seed = (self.u32(G_COSMETIC_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_COSMETIC_SEED, seed)
        return seed >> 16

    def seed3_draw(self):
        """One draw from the third generator 0x404468 (per machine)."""
        seed = (self.u32(G_SEED3) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_SEED3, seed)
        return seed >> 16

    @staticmethod
    def unit(draw):
        """draw / 65536 as a float in [0, 1)."""
        return C.mul(C.from_int(draw), F_2M16)

    @staticmethod
    def signed_unit(draw):
        """2 x draw / 65536 - 1: the coordinate of a unit-ball sample."""
        return C.sub(C.mul(C.mul(C.from_int(draw), F_2M16), F_2), ONE)

    def ball(self, draw):
        """A point of the unit ball by rejection: three draws per try (x, y, z in that
        order) from `draw`, retried while x^2 + y^2 + z^2 > 1."""
        while True:
            x = self.signed_unit(draw())
            y = self.signed_unit(draw())
            z = self.signed_unit(draw())
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    # =====================================================================================
    # Handle lists (0x1a1698-0x1a1bb0).  A node is 0x14 bytes: +0 next, +4 the address of
    # the word that points at it (the previous node's +0, or the list head), +8 its partner
    # node in the object's back list, +0xc the object, +0x10 a 16-bit word cleared when
    # the node is taken.  New nodes go to the FRONT of a list.
    # =====================================================================================
    def _node_take(self):
        node = self.u32(G_HANDLE_FREE)
        if node:
            self.w32(G_HANDLE_FREE, self.u32(node))
            self.w16(node + 0x10, 0)
        return node

    def _node_push(self, head, node):
        first = self.u32(head)
        self.w32(node, first)
        if first:
            self.w32(first + 4, node)
        self.w32(node + 4, head)
        self.w32(head, node)

    def _node_unlink(self, node):
        prev, nxt = self.u32(node + 4), self.u32(node)
        if prev:
            self.w32(prev, nxt)
            nxt = self.u32(node)
        if nxt:
            self.w32(nxt + 4, self.u32(node + 4))

    def _node_free(self, node):
        self.w32(node, self.u32(G_HANDLE_FREE))
        self.w32(G_HANDLE_FREE, node)

    def handle_link(self, head, back, obj):
        """handle_link 0x1a1738 (list head, the object's back list, object) -> node.  Two
        nodes: one at the front of the list, its partner at the front of the back list;
        clearing either list frees both."""
        node = self._node_take()
        partner = self._node_take()
        self._node_push(head, node)
        self._node_push(back, partner)
        self.w32(node + 0xC, obj)
        self.w32(node + 8, partner)
        self.w32(partner + 0xC, 0)
        self.w32(partner + 8, node)
        return node

    def list_push(self, head, obj):
        """list_push 0x1a1980 (list head, object) -> node: one node without a partner."""
        node = self._node_take()
        self._node_push(head, node)
        self.w32(node + 0xC, obj)
        self.w32(node + 8, 0)
        return node

    def handle_removeNode(self, node):
        """handle_removeNode 0x1a1868 (node) -> its object: unlinks and frees the node and
        its partner."""
        obj = self.u32(node + 0xC)
        self._node_unlink(node)
        partner = self.u32(node + 8)
        if partner:
            self._partner_drop(partner)
        self._node_free(node)
        return obj

    def _partner_drop(self, partner):
        prev = self.u32(partner + 4)
        if prev:
            self.w32(prev, self.u32(partner))
        nxt = self.u32(partner)
        if nxt:
            self.w32(nxt + 4, self.u32(partner + 4))
        self._node_free(partner)

    def handle_clear(self, head):
        """handle_clear 0x1a1698 (list head): every node of the list is unlinked and
        freed, each with its partner."""
        if head == 'stack':
            return
        node = self.u32(head)
        while node:
            nxt = self.u32(node)
            self._node_unlink(node)
            partner = self.u32(node + 8)
            if partner:
                self._partner_drop(partner)
            self._node_free(node)
            node = nxt

    def handle_obj(self, head):
        node = self.u32(head)
        return self.u32(node + 0xC) if node else 0

    def list_objects(self, head):
        """The objects of a list, head first (empty handles included as 0)."""
        out, node = [], self.u32(head)
        while node:
            out.append(self.u32(node + 0xC))
            node = self.u32(node)
        return out

    def query_list(self, name, *args):
        """A world query that fills a list: the callback returns the objects, and they are
        linked into a list head in the model's frame (list_fill) as the callee would.
        Returns the head; the caller clears it."""
        head = self.alloca(4)
        self.mem.poke(head, 4, 0)
        found = self.call(name, *args)
        list_fill(self.mem.load, self.mem.poke, head, found or ())
        return head

    # ---- the list iterator --------------------------------------------------------------
    def _iter_skip(self, node, mask):
        while node:
            obj = self.u32(node + 0xC)
            if obj and not self.u32(obj + 0xC) & mask:
                break
            node = self.u32(node)
        return node

    def _iter_park(self, it, node):
        nxt = self.u32(node)
        self.w32(it + 4, node)
        self.w32(it, nxt)
        if nxt:
            self.w32(nxt + 4, it)
        self.w32(self.u32(it + 4), it)

    def iter_begin(self, it, head, mask):
        """iter_begin 0x1a1a48 (iterator, list head, exclude mask): the iterator links
        itself into the list BEHIND the first node whose object exists and has none of
        the mask's flag bits; +4 is that node (0 = end)."""
        self.w32(it + 0x14, mask)
        node = self._iter_skip(self.u32(head), mask)
        if node:
            self._iter_park(it, node)
        else:
            self.w32(it, 0)
            self.w32(it + 4, 0)
        self.w32(it + 0xC, 0)

    def iter_next(self, it):
        """iter_next 0x1a1b38: leaves the list, then parks behind the next eligible node.
        A node linked at the head during the walk is behind the iterator and not met."""
        first = self.u32(it)
        node = self._iter_skip(first, self.u32(it + 0x14))
        prev, value = self.u32(it + 4), 0
        if first:
            self.w32(first + 4, prev)
            value, prev = self.u32(it), self.u32(it + 4)
        self.w32(prev, value)
        if node:
            self._iter_park(it, node)
        else:
            self.w32(it + 4, 0)
            self.w32(it, 0)

    def iter_end(self, it, flags):
        """iter_end 0x1a1ae8 (iterator, 2): leaves the list."""
        if self.u32(it):
            self.w32(self.u32(it) + 4, self.u32(it + 4))
        if self.u32(it + 4):
            self.w32(self.u32(it + 4), self.u32(it))

    # =====================================================================================
    # Skill base (docs/spec/skills-35-68.md 1.2; layout in docs/skills.md)
    # =====================================================================================
    def skill_can_use_base(self, skill, caster=0):
        """Skill slot 1, base 0x3c8218: 1."""
        return 1

    def skill_cast_base(self, skill, level=0, caster=0, pos=0, facing=0):
        """Skill slot 2, base 0x3c8220: copies the position into its frame, returns 0."""
        return 0

    def skill_mana_cost_base(self, skill, level=0):
        """Skill slot 5, base 0x3c82a8: 1.0."""
        return ONE

    def _stat(self, skill, first_off, base_off, step_off, stat, level):
        first = self.s16(skill + first_off + 2 * stat)
        if first > level:
            return 0
        value = C.add(C.from_int(self.s16(skill + base_off + 2 * stat)),
                      C.mul(self.u32(skill + step_off + 4 * stat), C.from_int(level - first)))
        return C.to_int(C.sub(value, HALF) if C.lt(value, ZERO) else C.add(value, HALF))

    def skill_get_stat(self, skill, stat, level):
        """Skill slot 10, 0x3c85fc (skill, statistic, level) -> int: tier 1.

        0 for level 0 or a level below the statistic's first level, else
        base + step x (level - first) in single precision, half added (subtracted when
        negative) and truncated."""
        stat, level = s32(stat), s32(level)
        if level == 0:
            return 0
        return self._stat(skill, 0x0E, 0x18, 0x24, stat, level)

    def skill_get_stat_tier2(self, skill, stat, level, cap):
        """Skill slot 11, 0x3c8690 (skill, statistic, level, cap) -> int.

        Level 0 gives 0.  A positive cap limits the level.  A statistic whose tier-2 first
        level is negative has no tier 2 and uses the tier-1 tables."""
        stat, level, cap = s32(stat), s32(level), s32(cap)
        if level == 0:
            return 0
        if cap > 0:
            level = min(level, cap)
        if self.s16(skill + 0x38 + 2 * stat) < 0:
            return self._stat(skill, 0x0E, 0x18, 0x24, stat, level)
        return self._stat(skill, 0x38, 0x42, 0x4C, stat, level)

    def skill_get_stat_for(self, skill, stat, level, caster, cap):
        """Skill slot 12, 0x3c87f0 (skill, statistic, level, caster, cap): slot 10 for a
        caster with the player flag, else slot 11 with the cap."""
        if caster and self.u32(caster + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_get_stat_for_handle(self, skill, stat, level, handle, cap):
        """Skill slot 13, 0x3c8864: slot 12 with the caster given as the address of a
        handle word."""
        node = self.u32(handle)
        if node and self.u32(self.u32(node + 0xC) + 0xC) & 0x40:
            return self.skill_call(skill, 10, stat, level)
        return self.skill_call(skill, 11, stat, level, cap)

    def skill_adjust_level(self, skill, level, n=0):
        """Skill slot 14, 0x3c88dc: the level, unchanged."""
        return level

    def skill_mana_from_stat4(self, skill, level, n=0):
        """Skill slot 15, 0x3c88e4 (skill, level, n) -> float: slot 10 (4, slot 14 (level,
        n))."""
        return C.from_int(s32(self.skill_call(skill, 10, 4, self.skill_call(skill, 14, level, n))))

    def skill_stat_range(self, skill, stat, level, randomise, lo_out, hi_out, spread):
        """Skill slot 8, 0x3c82e4 (skill, statistic, level, randomise, low out, high out;
        spread).  v = slot 10.  Without randomise the bounds are v -/+ v x spread; with
        it each bound makes TWO SHARED DRAWS: the first only chooses the rounding
        direction, the second scales the spread.  Both are rounded half away from zero
        and raised to at least 1."""
        value = C.from_int(s32(self.skill_call(skill, 10, stat, level)))
        for out, op in ((lo_out, C.sub), (hi_out, C.add)):
            if s32(randomise) == 0:
                bound = op(value, C.mul(value, spread))
                negative = C.lt(bound, ZERO)
            else:
                probe = op(value, C.mul(C.mul(value, self.unit(self.draw())), spread))
                negative = C.lt(probe, ZERO)
                bound = op(value, C.mul(C.mul(value, self.unit(self.draw())), spread))
            number = C.to_int(C.sub(bound, HALF) if negative else C.add(bound, HALF))
            self.w32(out, number)
            if s32(number) < 1:
                self.w32(out, 1)

    # ---- helpers for the skills ---------------------------------------------------------
    def stat(self, skill, stat, level):
        return s32(self.skill_call(skill, 10, stat, level))

    def stat_for(self, skill, stat, level, caster, cap):
        return s32(self.skill_call(skill, 12, stat, level, caster, cap))

    def stat_range(self, skill, stat, level, randomise, spread):
        """Slot 8 with its two outputs in the frame -> (low, high)."""
        out = self.alloca(8)
        self.skill_call(skill, 8, stat, level, randomise, out, out + 4, spread)
        return self.s32(out), self.s32(out + 4)

    # =====================================================================================
    # Spell base (docs/skills.md "Spell"; docs/spec/skills-35-68.md 1.1, 1.3, 1.4)
    # =====================================================================================
    def spell_base_ctor(self, spell, level, owner, skill, table):
        """The Spell base, inlined in every spell constructor: level byte +0, back list
        +4 = 0, skill +8, owner +0xc, the spell's own generator +0x10 = ONE SHARED DRAW,
        table +0x14."""
        self.w8(spell, level)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 8, skill)
        self.w32(spell + 4, 0)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 0x10, self.draw())
        self.w32(spell + 0x14, table)

    def creature_add_spell(self, creature, spell):
        """creature_addSpell 0x11a838 (creature, spell or 0): the spell joins the FRONT of
        the list at creature +0x364 (back list: spell +4), so the newest spell runs
        first."""
        if spell:
            self.handle_link(creature + 0x364, spell + 4, spell)

    def creature_update_spells(self, creature, pos):
        """Creature_updateSpells 0x11a868, Creature slot 17 (creature, position): slot 2
        (run) of every attached spell with (a copy of the position, the creature's
        facing), walked with the list iterator from the head.  A spell that ends itself
        in its run, or one attached during the walk, does not disturb it."""
        frame = self.alloca(0x30)
        copy, it = frame, frame + 0x10
        self.mem.poke(copy, 4, self.u32(pos))
        self.mem.poke(copy + 4, 4, self.u32(pos + 4))
        self.mem.poke(copy + 8, 4, self.u32(pos + 8))
        self.iter_begin(it, creature + 0x364, 0)
        while self.u32(it + 4):
            spell = self.u32(self.u32(it + 4) + 0xC)
            self.spell_call(spell, 2, copy, self.u16(creature + 0x38))
            self.iter_next(it)
        self.iter_end(it, 2)

    def spell_end(self, spell):
        """A spell ending itself: its slot 1 with 3 (destroy and free)."""
        if spell:
            self.spell_call(spell, 1, 3)

    # =====================================================================================
    # Projectile base (docs/spec/skills-35-68.md Part 2)
    # =====================================================================================
    def game_object_ctor(self, obj, pos, class_def, props):
        """GameObject_ctor 0x14cb10 (object, position, class definition, properties): a
        callback (tools/ref_objects.py owns it) - and ONE SHARED DRAW, the seed of the
        object's own generator at +0x44."""
        self.draws += 1
        self.call('GameObject_ctor', obj, self.vec(pos), class_def, props)

    def projectile_ctor(self, obj, pos, owner, class_def):
        """Projectile_ctor 0x150e48 (object, position, owner, class definition).

        GameObject_ctor (one shared draw), owner handle +0x4c = empty, splash byte +0x50
        = 0, radius +0x1c = 12.0, table = Projectile, flags |= 0x4081 (not solid, has an
        owner handle, transient), then the owner is linked when there is one."""
        self.game_object_ctor(obj, pos, class_def, 0)
        self.w32(obj + 0x4C, 0)
        self.w32(obj + 0x48, VT_PROJECTILE)
        self.w32(obj + 0x1C, F_12)
        self.w8(obj + 0x50, 0)
        self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4081)
        if owner:
            self.handle_link(obj + 0x4C, owner, owner)
        return obj

    def obj_move_and_collide(self, obj, vel):
        """obj_moveAndCollide 0x1509f8 (object, velocity in units per second) -> bits:
        1 went under the terrain, 2 overlapped at least one object.

        pos += velocity x (1/60); grid cell; under the terrain (strictly): back off
        along the step by 0.1, 0.2, ... of it until terrain_height is not above the
        point (the last point tried is kept, found or not), and once per object a splash
        (ONE OWN DRAW, unused) when the point is in water.  Then every object of the box
        query round the new position that is solid, is not the projectile or its owner
        and overlaps in height and in the plane gets its slot 6 called with the
        projectile, and the projectile's own slot 6 is called with it - for every such
        object, in query order, whatever the handlers do."""
        u32, w32 = self.u32, self.w32
        step = tuple(C.mul(u32(vel + 4 * i), DT) for i in range(3))
        w32(obj + 0x10, C.add(u32(obj + 0x10), step[0]))
        w32(obj + 0x14, C.add(u32(obj + 0x14), step[1]))
        w32(obj + 0x18, C.add(u32(obj + 0x18), step[2]))
        self.call('obj_updateGridCell', obj)
        result = 0
        ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), u32(obj + 0x1C))
        if C.lt(u32(obj + 0x18), ground):
            result = 1
            k = F_0_1
            while True:
                cand = tuple(C.sub(u32(obj + 0x10 + 4 * i), C.mul(step[i], k)) for i in range(3))
                if C.le(self.call('terrain_height', u32(G_WORLD), cand, u32(obj + 0x1C)), cand[2]):
                    break
                k = C.add(k, F_0_1)
                if not C.lt(k, F_2):
                    break
            self.wvec(obj + 0x10, cand)
            if self.s8(obj + 0x50) == 0 and self.call('water_test', u32(G_WORLD), self.vec(obj + 0x10), 0, F_12):
                self.w8(obj + 0x50, 1)
                self.obj_rand(obj)
                name = self.call('libc_sprintf', 0x532458, 1)
                self.call('sound_playOnObject', self.call('res_find', 0x532478, name), obj, 0x3E4CCCCC)
                self.call('water_disturb', u32(G_WORLD), self.vec(obj + 0x10), 0x442F0000, F_24)
        radius, height = u32(obj + 0x1C), u32(obj + 0x20)
        x, y, z = self.vec(obj + 0x10)
        low = (C.sub(x, radius), C.sub(y, radius), C.sub(z, height))
        high = (C.add(x, radius), C.add(y, radius), C.add(z, height))
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
            if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(reach, reach)):
                result |= 2
                self.vcall(other, 6, obj)
                self.vcall(obj, 6, other)
        return result

    # =====================================================================================
    # Damage descriptors (docs/gameplay.md 2.2).  The original builds a 0x44-byte record
    # in its frame; callbacks get it as ('desc', ((type, value, value2), ...)) with only
    # the entries that are in use.
    # =====================================================================================
    @staticmethod
    def descriptor(*entries):
        return ('desc', tuple(tuple(e) for e in entries))
