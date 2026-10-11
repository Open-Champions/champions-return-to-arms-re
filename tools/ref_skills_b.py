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
                   modelled for it.  The first pass modelled ids 41-50, 53-55, 59-64 and
                   68; the second pass (from "The second pass" on, where Model is built
                   up section by section) added 35 Charge, 36 Darkness, 37 Shock, 38
                   Ground Pound, 39 / 40 Convert Enemy / Undead, 51 AncestralCall, 67
                   ShadowStep and the can-use of 65.  Not modelled beyond statistics, mana
                   cost and can-use: 56, 57, 58, 66 and the cast of 65.  Id 52 (Root) is
                   the class of ids 31 / 32, modelled in tools/ref_skills_a.py.

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
G_PADS = 0x41BFD8                               # 0x58 bytes per player slot
G_PVP_MODE_A, G_PVP_MODE_B = 0x4F711C, AM.G_PVP_MODE_B
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440    # g_alivePlayerCount, g_alivePlayers (slots; FINDINGS G19)

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

# The original functions the model implements: name -> (start, end).  The per-skill
# sections below add theirs; tools/difftest_skills_b.py runs exactly these for real.
FUNCTIONS = {
    'Skill_canUse_base': (0x3C8218, 0x3C8220), 'Skill_cast_base': (0x3C8220, 0x3C8248),
    'Skill_manaCost_base': (0x3C82A8, 0x3C82B8), 'Skill_getStatRange': (0x3C82E4, 0x3C85B0),
    'Skill_getStat': (0x3C85FC, 0x3C8690), 'Skill_getStatTier2': (0x3C8690, 0x3C87F0),
    'Skill_getStatFor': (0x3C87F0, 0x3C8864), 'Skill_getStatForHandle': (0x3C8864, 0x3C88DC),
    'Skill_adjustLevel': (0x3C88DC, 0x3C88E4), 'Skill_manaFromStat4': (0x3C88E4, 0x3C8944),
    'Spell_rand': (0x16A964, 0x16A98C), 'GameObject_rand': (0x1509D0, 0x1509F8),
    'handle_clear': (0x1A1698, 0x1A1734), 'handle_link': (0x1A1738, 0x1A17CC),
    'handle_removeNode': (0x1A1868, 0x1A18F0), 'list_push': (0x1A1980, 0x1A19D0),
    'iter_begin': (0x1A1A48, 0x1A1AE8), 'iter_end': (0x1A1AE8, 0x1A1B34), 'iter_next': (0x1A1B38, 0x1A1BB0),
    'creature_addSpell': (0x11A838, 0x11A868), 'Creature_updateSpells': (0x11A868, 0x11A91C),
    'Projectile_ctor': (0x150E48, 0x150EE4), 'obj_moveAndCollide': (0x1509F8, 0x150E48),
}

# class tables whose slots the test must resolve: (table, 'Spell' or 'Creature', slots that
# code of this module calls).  A slot whose function is not in FUNCTIONS is a call-out.
CLASS_TABLES = [(VT_SPELL, 'Spell', (1,)), (VT_PROJECTILE, 'Creature', (1, 6)), (VT_GAMEOBJECT, 'Creature', (1, 6))]

# per skill id: name, status and the names of its functions in FUNCTIONS (filled below)
SKILLS = {}

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
    'Player_move': Ext(0x1B4020, 'pipV', 0, 'i', '(player, mode, pad, external velocity or 0) -> event bits'),
    'Player_meleeHit': Ext(0x1B6A98, 'ppii', 1, 'n', '(player, target, flag, flags; damage scale)'),
    # --- lights
    'light_link': Ext(0x148AF8, 'p', 0, 'n', '(light record)'),
    'light_relink': Ext(0x14A528, 'p', 0, 'n', '(light record)'),
    'light_unlink': Ext(0x14A4F0, 'p', 0, 'n', '(light record)'),
    # --- damage, effects
    'damage_apply': Ext(0x1E8230, 'ppiiiiDi', 2, 'i', '(victim, attacker, attack rating, -, -, flags, descriptor or 0, '
                        'no-crit; min, max) -> 1 when the hit landed'),
    'Creature_setEffectTimer': Ext(0x118950, 'pip', 1, 'n', '(creature, which, source; seconds)'),
    'fx_impactPuffNearCamera': Ext(0x1FC150, 'vvi', 2, 'n', '(position, step, kind; radius, size): camera-gated puff'),
    'camera_shake': Ext(0x1EBAE0, 'i', 1, 'n', '(0; strength)'),
    'MissileWeapon_ctor': Ext(0x150EE4, 'piiivvip', 0, 'n', '(block, kind, model A, model B, position, velocity, facing, '
                              'owner; on the stack: launch sample, impact sample, damage min, damage max, weapon '
                              'rating, item flags, attack rating, damage flags, item)'),
    'item_getModifiedField1a': Ext(0x103F88, 'p', 0, 'i', '(item) -> its attack rating with modifiers'),
    'StrongStancePhantom_ctor': Ext(0x1618D4, 'ppiii', 0, 'n', '(block, player, the trigger\'s two arguments, 0)'),
    'Creature.v30': Ext(0, 'pii', 0, 'n', 'stun (frames, flash)'),
    'particleGroup_create': Ext(0x18E880, '', 0, 'i', '-> handle or 0'),
    'particleGroup_begin': Ext(0x18E958, 'i', 0, 'n', '(handle): the particles spawned next join the group'),
    'particleGroup_end': Ext(0x18E9A0, 'i', 0, 'n', '(handle)'),
    'particleGroup_setMatrix': Ext(0x18E9E8, 'iM', 0, 'n', '(handle, 3x4 matrix)'),
    'terrain_heightAtPoint': Ext(0x182F28, 'pv', 0, 'f', '(world, position) -> height'),
    'Creature.v21': Ext(0, 'pp', 0, 'i', 'is ally (other)'),
    'Creature.v22': Ext(0, 'pp', 0, 'i', 'is on my side (other player)'),
    'SpellResurrect_typeinfo': Ext(0x3D162C, '', 0, 'i', 'type-info getter'),
    'SpellCriticalHit_typeinfo': Ext(0x3CF000, '', 0, 'i', 'type-info getter'),
    'player_respawn': Ext(0x1BD040, 'iviii', 0, 'n', '(slot, position, facing, -1, -1): a new Player object for the slot'),
    'player_resetIdleAnim': Ext(0x1B2470, 'i', 0, 'n', '(slot)'),
    'arena_addLife': Ext(0x3058C0, 'i', 0, 'n', '(slot)'),
    'fx_emitFromModelVerts': Ext(0x1EB1E8, 'piivV', 1, 'n', '(object, count, particle definition, direction, offset or 0; '
                                 'speed): presentation generator only'),
    'GlowingShaft_ctor': Ext(0x202FF0, 'pviiii', 0, 'n', '(block, position, four integers): a rising shaft of light'),
    'poisonGasSpell_ctor': Ext(0x202DE8, 'pviiipi', 0, 'n', '(block, position, life in frames, radius, 0, owner, damage)'),
    # --- world
    'world_collectInSphere': Ext(0x14AB80, 'viL', 1, 'n', '(centre, heading, list out; radius) -> objects'),
    'world_collectObjectsInArc': Ext(0x1614F0, 'viLp', 3, 'n', '(centre, heading, list out, filter; radius, '
                                     'arc in degrees, half width) -> objects, nearest first'),
    # --- virtual calls on creatures and other world objects: (this, ...)
    'Creature.v1': Ext(0, 'pi', 0, 'n', 'destroy (3)'),
    'Creature.v6': Ext(0, 'pp', 0, 'n', 'touched by (other)'),
    'Creature.v12': Ext(0, 'piVp', 1, 'n', '(kind, position, source; amount): being aimed at / alerted'),
    'Creature.v39': Ext(0, 'pi', 0, 'i', 'Player: rank in a skill (id)'),
    'Spell.v4': Ext(0, 'p', 0, 'i', 'the value at spell +0x18'),
})
EXTERNALS['wstr_format'].stack = 2
EXTERNALS['MissileWeapon_ctor'].stack = 9
# callbacks that construct a GameObject: the real ones make ONE SHARED DRAW each (the seed of
# the object's own generator); the model counts it where it makes the call
OBJECT_CTORS = ('GameObject_ctor', 'LightEffect_ctor', 'poisonGasSpell_ctor', 'MissileWeapon_ctor',
                'StrongStancePhantom_ctor', 'GlowingShaft_ctor')

# functions other reference models own that the test runs for real beside this module's
# (the model calls the other module's function): name -> address
REAL_LIBRARY = {'vec3_hermite': 0x162310, 'mat34_setPosRotZ': 0x163B30, 'mat34_transformPoint': 0x1660A0,
                'vec3_dotDelta': 0x1667D8}     # all of tools/ref_core.py

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
        if kind in 'ipvelsSOWVDM':
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
        self.addr_names = {}            # function address -> callback name, for class tables whose
                                        # slot functions a caller has named itself

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

    def _virtual(self, cls, bodies, obj, table, slot, args):
        this = (obj + self.s16(table + 8 * slot)) & M32
        function = self.u32(table + 8 * slot + 4)
        name = '%s.v%d' % (cls, slot)
        body = bodies.get(function)
        if body is not None and name not in self.external:
            return getattr(self, body)(this, *args)
        if (cls, slot) in (('Spell', 2), ('Skill', 2)):     # a position goes to a callback by value
            args = tuple(self.vec(a) if i == (0 if cls == 'Spell' else 2) else a for i, a in enumerate(args))
        return self.call(self.addr_names.get(function) or name, this, *args)

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48.  A body of OBJECT_BODIES (the effect
        objects of this module) runs here; anything else is the callback
        'Creature.v<slot>' - creatures, players and props alike."""
        return self._virtual('Creature', OBJECT_BODIES, obj, self.u32(obj + 0x48), slot, args)

    def skill_call(self, skill, slot, *args):
        """A virtual call on a Skill (table pointer at +0x60)."""
        return self._virtual('Skill', SKILL_BODIES, skill, self.u32(skill + 0x60), slot, args)

    def spell_call(self, spell, slot, *args):
        """A virtual call on a Spell (table pointer at +0x14)."""
        return self._virtual('Spell', SPELL_BODIES, spell, self.u32(spell + 0x14), slot, args)

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

    def query_into(self, head, name, *args):
        """A world query that adds to a list the caller already has."""
        found = self.call(name, *args)
        list_fill(self.mem.load, self.mem.poke, head, found or ())

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
            self.spell_call(spell, 2, copy, self.s16(creature + 0x38))
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
        """('desc', ((type, a, b, c), ...)): the four 16-bit fields of each entry in use."""
        return ('desc', tuple(tuple(v & 0xFFFF for v in e) for e in entries))


    # =====================================================================================
    # 41 cyclone (and 84 berserkercyclone): docs/spec/skills-35-68.md section 41
    # =====================================================================================
    VT_SPELL_CYCLONE = 0x518A98
    S_CYCLONE_WARN, S_CYCLONE_CLIP1, S_CYCLONE_CLIP2 = 0x54EF60, 0x54EF88, 0x54EFB8
    S_CYCLONE_LUMP, S_CYCLONE_SOUND = 0x54EF98, 0x54EFA0
    PDEF_CYCLONE_HELIX, PDEF_CYCLONE_SPARK = 0x8E5500, 0x8E5550

    def cyclone_can_use(self, skill, caster):
        """SkillCyclone_canUse 0x2d1484 (skill, caster) -> 1 or 0.  A caster without the
        player flag: 1.  A player whose weapon class (record +0x4a86) is 4 (bow) or 6:
        the warning text for 180 frames on that player's slot, and 0."""
        if not self.u32(caster + 0xC) & 0x40:
            return 1
        if self.s8(self.record(caster) + 0x4A86) not in (4, 6):
            return 1
        self.call('hud_showMessage', self.call('text_lookup', self.S_CYCLONE_WARN), 0xB4, self.u32(caster + 0x3C8), 0)
        return 0

    def cyclone_cast(self, skill, level, caster, pos, facing=0):
        """SkillCyclone_cast 0x2d161c (skill, level, caster, position, facing) -> the
        SpellCyclone or 0: pool_new(0x7c) and the constructor.  Position and facing are
        not used."""
        spell = self.call('pool_new', 0x7C)
        if spell:
            self.cyclone_spell_ctor(spell, level, caster, skill)
        return spell

    def cyclone_spell_ctor(self, spell, level, owner, skill):
        """SpellCyclone_ctor 0x2d17c8 (spell, level, owner, skill).

        Spell base (ONE SHARED DRAW); the light record at +0x1c (radius 36) is linked; the
        owner's action state +0x58c = 6 WHATEVER the owner is; the first spin clip is
        looked up in the owner's class lump and kept at +0x78; spin time +0x68 = clip
        length x (1/60) x statistic 1; then - STILL BEFORE THE PREDICTION-COPY TEST -
        event slot 0 of that clip (a header every object playing the clip shares) is set to
        mask 1 at 0.05 s (stores 0x2d1978, 0x2d197c) and the clip is pushed on the owner's
        animation state with flags 0x23.  Two own draws seed the helix angles.  Only when
        the owner is not the prediction copy (flag 0x20000): the voice line, the sound,
        and every object within 480 of the owner (world_collectInSphere) is linked into
        the candidate list +0x18, in the order of the query's list."""
        u32, w32, w16, w8 = self.u32, self.w32, self.w16, self.w8
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_CYCLONE)
        w32(spell + 0x18, 0)
        self.wvec(spell + 0x4C, self.vec(owner + 0x10))
        w8(spell + 0x25, 0)
        w16(spell + 0x2E, 0x9E)
        w16(spell + 0x26, 0x9E)
        w32(spell + 0x40, 0x42100000)
        w32(spell + 0x44, 0x3A4A4587)
        w32(spell + 0x38, 0x42100000)
        w32(spell + 0x3C, 0x3A4A4587)
        w16(spell + 0x30, 0x6F)
        w16(spell + 0x28, 0x6F)
        w16(spell + 0x32, 0x43)
        w16(spell + 0x2A, 0x43)
        w32(spell + 0x48, 0)
        w16(spell + 0x2C, 0)
        w16(spell + 0x34, 0)
        w8(spell + 0x24, 0)
        self.call('light_link', spell + 0x1C)
        w32(owner + 0x58C, 6)
        w32(spell + 0x58, u32(G_SIM_FRAME))
        clip = self.call('res_find', u32(u32(owner + 0x24)), self.S_CYCLONE_CLIP1)
        w32(spell + 0x78, clip)
        turns = self.stat(u32(spell + 8), 1, self.s8(spell))
        clip = u32(spell + 0x78)
        w32(spell + 0x68, C.mul(C.mul(C.from_int(self.s32(clip + 4)), DT), C.from_int(turns)))
        w8(clip + 0x18, 1)                              # 0x2d1978: the shared clip header
        w32(clip + 0x14, 0x3D4CCCCC)                    # 0x2d197c
        self.call('anim_push', owner + 0x114, u32(spell + 0x78), 0x23)
        w32(spell + 0x5C, 0)
        w32(spell + 0x60, 0)
        w16(spell + 0x64, self.spell_rand(spell))
        w16(spell + 0x66, self.spell_rand(spell))
        self.wvec(spell + 0x6C, self.vec(owner + 0x10))
        if u32(u32(spell + 0xC) + 0xC) & 0x20000:       # 0x2d19c4: the prediction copy stops here
            return
        self.call('player_voice', u32(owner + 0x3C8), 10)
        self.call('sound_playOnObject', self.call('res_find', self.S_CYCLONE_LUMP, self.S_CYCLONE_SOUND), owner, ONE)
        head = self.query_list('world_collectInSphere', self.vec(owner + 0x10), self.s16(owner + 0x38), 0x43F00000)
        for obj in self.list_objects(head):
            self.handle_link(spell + 0x18, obj, obj)
        self.handle_clear(head)

    def cyclone_run(self, spell, pos, facing):
        """SpellCyclone_run 0x2d1a94 (spell, position, facing): slot 2, once per tick of
        the owner.

          1. In a net game the "object or prediction copy" of the owner is fetched.
          2. Player_animStep(owner; 1.0).  Event bit 1 (the clip's slot 0): spin time
             +0x68 -= 0.05, and the slot's time IN THE SHARED CLIP HEADER += 0.05,
             wrapped by the clip's length.  Event bit 4: +0x60 = 1 (the stop clip hit its
             mark: no more hits).
          3. hit tick = frame % 4 == 0 (% 5 on a level with flag 0x100).
          4. Animation status bits 0x30 both clear: owner state = 2 and the spell ends.
             Owner state not 6: the spell ends.
          5. Spinning (+0x5c == 0): when the spin time is <= 0.072 the top track gets
             life 1.0 and life rate -0.833, the stop clip is looked up, ITS event slot 2
             is set to mask 4 at 0.167 s (shared header again), and it is started on the
             owner - and once more on the "object or copy" when there is one - then +0x5c
             = 1.  Then the move: speed = statistic 2 x 143.12 x 0.01 along the pad's two
             stick values in the camera's frame, Player_move mode 5; the fx anchor +0x6c
             follows 0.963 of the owner's displacement.
             Stopping (+0x5c != 0): the light's radius shrinks by 0.916 a tick.
          6. Unless stopping and past the mark: the fx (cyclone_update_fx), the weapon
             tip = position + 28.58 along the horizontal direction to attach point 0, and
             on a hit tick Player_meleeHit(owner, target, 0, 0x40000000; statistic 0 x
             0.01) for every candidate of +0x18 the owner's slot 20 accepts whose centre
             is within its radius + 23 of the tip, in list order.
          7. net_isLocalSlot(owner's slot): the copy-rebuild countdown 0x402797 = 120."""
        u32, w32 = self.u32, self.w32
        facing = s16(facing)
        here = self.vec(pos)
        owner = u32(spell + 0xC)
        ghost = self.call('net_objOrGhost', owner) if self.s8(G_NETWORK_MODE) else 0
        events = self.call('Player_animStep', owner, ONE)
        if events & 1:
            clip = u32(spell + 0x78)
            w32(spell + 0x68, C.sub(u32(spell + 0x68), 0x3D4CCCCC))
            length = C.mul(C.from_int(self.s32(clip + 4)), DT)
            when = C.add(u32(clip + 0x14), 0x3D4CCCCC)
            w32(clip + 0x14, when)
            if C.lt(length, when):
                w32(clip + 0x14, C.sub(when, length))
        if events & 4:
            w32(spell + 0x60, 1)
        period = C.to_int(0x40ABDE74 if u32(G_LEVEL_FLAGS) & 0x100 else 0x408F3962)
        frame = self.s32(G_SIM_FRAME)
        hit_tick = (abs(frame) % period) == 0
        if not self.u16(owner + 0x11A) & 0x30:
            w32(owner + 0x58C, 2)
            return self.spell_end(spell)
        if u32(owner + 0x58C) != 6:
            return self.spell_end(spell)
        if u32(spell + 0x5C):
            radius = C.mul(u32(spell + 0x38), 0x3F6A7EF9)
            w32(spell + 0x38, radius)
            w32(spell + 0x40, radius)
            inverse = C.div(ONE, C.mul(radius, radius))
            w32(spell + 0x44, inverse)
            w32(spell + 0x3C, inverse)
        else:
            if C.le(u32(spell + 0x68), 0x3D93708A):
                w32(owner + self.s8(owner + 0x118) * 0x20 + 0x10C, ONE)
                lump = u32(u32(owner + 0x24))
                w32(owner + self.s8(owner + 0x118) * 0x20 + 0x110, 0xBF555554)
                clip = self.call('res_find', lump, self.S_CYCLONE_CLIP2)
                w32(spell + 0x78, clip)
                self.w8(clip + 0x28, 4)
                w32(clip + 0x24, 0x3E2B00BC)
                self.call('anim_startBlendInOut', owner + 0x114, u32(spell + 0x78), 0x32, ZERO, 0x3E676C48)
                if ghost:
                    self.call('anim_startBlendInOut', ghost + 0x114, u32(spell + 0x78), 0x32, ZERO, 0x3E676C48)
                w32(spell + 0x5C, 1)
            speed = C.mul(C.mul(C.from_int(self.stat(u32(spell + 8), 2, self.s8(spell))), 0x430F1F71), F_0_01)
            yaw = -s32(self.call('net_getCamYaw', u32(owner + 0x3C8)))
            side = (C.neg(C.cos16(yaw - 0x4000)), C.neg(C.sin16(yaw - 0x4000)), ZERO)
            ahead = (C.neg(C.cos16(yaw - 0x8000)), C.neg(C.sin16(yaw - 0x8000)), ZERO)
            pad = (G_PADS + self.s32(owner + 0x3C8) * 0x58) & M32
            along = C.mul(C.neg(speed), u32(pad + 0x18))
            across = C.mul(speed, u32(pad + 0x14))
            push = tuple(C.add(C.mul(side[i], along), C.mul(ahead[i], across)) for i in range(3))
            before = self.vec(owner + 0x10)
            self.call('Player_move', owner, 5, pad, push)
            for i in range(3):
                moved = C.mul(C.sub(u32(owner + 0x10 + 4 * i), before[i]), 0x3F7686D7)
                w32(spell + 0x6C + 4 * i, C.add(u32(spell + 0x6C + 4 * i), moved))
        if not u32(spell + 0x5C) or not u32(spell + 0x60):
            self.cyclone_update_fx(spell, here)
            hand = self.call('model_getAttachPoint', u32(owner + 0x544), here, facing, owner + 0x114, 0, 0, ONE)
            dx, dy = C.sub(hand[0], here[0]), C.sub(hand[1], here[1])
            inverse = C.rsqrt(ONE, C.add(C.mul(dx, dx), C.mul(dy, dy)))
            reach = 0x41E4ACFD
            tip = (C.add(here[0], C.mul(C.mul(dx, inverse), reach)), C.add(here[1], C.mul(C.mul(dy, inverse), reach)),
                   C.add(here[2], C.mul(C.mul(ZERO, inverse), reach)))
            if hit_tick:
                scale = C.mul(C.from_int(self.stat(u32(spell + 8), 0, self.s8(spell))), F_0_01)
                node = u32(spell + 0x18)
                while node:
                    obj = u32(node + 0xC)
                    if obj and self.vcall(owner, 20, obj):
                        ox, oy = C.sub(u32(obj + 0x10), tip[0]), C.sub(u32(obj + 0x14), tip[1])
                        if C.lt(C.sqrt(C.add(C.mul(ox, ox), C.mul(oy, oy))), C.add(u32(obj + 0x1C), 0x41B80000)):
                            self.call('Player_meleeHit', owner, obj, 0, 0x40000000, scale)
                    node = u32(node)
        if self.call('net_isLocalSlot', u32(owner + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 0x78)

    def cyclone_update_fx(self, spell, here):
        """SpellCyclone_updateFx 0x2d21e0 (spell, position): presentation, but with OWN
        draws.  The light follows the position (17 up) and pulses with the frame counter;
        the two helix angles +0x64 / +0x66 advance by 0x6f5 / 0x2e7; 72 particles along a
        Hermite curve from the anchor +0x6c to 90 above it; at level 9 and above, on
        frames divisible by 3, one spark with THREE OWN DRAWS."""
        u32, w32 = self.u32, self.w32
        if not isinstance(here, tuple):
            here = self.vec(here)
        self.wvec(spell + 0x4C, here)
        w32(spell + 0x54, C.add(u32(spell + 0x54), 0x41880000))
        self.call('light_relink', spell + 0x1C)
        frame = self.s32(G_SIM_FRAME)
        low = frame - (((frame + 0xFFFF) if frame < 0 else frame) >> 16 << 16)
        pulse = C.mul(C.cos16(low), 0x42B40000)
        self.w16(spell + 0x64, self.u16(spell + 0x64) + 0x6F5)
        radius = C.add(pulse, 0x42100000)
        w32(spell + 0x38, radius)
        w32(spell + 0x40, radius)
        inverse = C.div(ONE, C.mul(radius, radius))
        w32(spell + 0x44, inverse)
        w32(spell + 0x3C, inverse)
        c1, s1 = C.cos16(self.s16(spell + 0x64)), C.sin16(self.s16(spell + 0x64))
        anchor = self.vec(spell + 0x6C)
        three, far, tangent = 0x40400000, 0x41F80000, 0x43280000
        p0 = (C.add(C.mul(c1, three), anchor[0]), C.add(C.mul(s1, three), anchor[1]), C.add(ZERO, anchor[2]))
        self.w16(spell + 0x66, self.u16(spell + 0x66) + 0x2E7)
        c2, s2 = C.cos16(self.s16(spell + 0x66)), C.sin16(self.s16(spell + 0x66))
        p1 = (C.add(C.mul(c2, far), anchor[0]), C.add(C.mul(s2, far), anchor[1]), C.add(0x42B40000, anchor[2]))
        m0 = (C.mul(ZERO, tangent), C.mul(ZERO, tangent), C.mul(ONE, tangent))
        m1 = (C.mul(c2, tangent), C.mul(s2, tangent), C.mul(ZERO, tangent))
        previous = p0
        t = ZERO
        while True:
            swirl = C.mul(C.mul(t, 0x46686400), 0x447A0000)
            width = C.add(C.mul(t, 0x41E00000), three)
            turn = s16(C.to_int(C.add(swirl, HALF) if C.le(ZERO, swirl) else C.sub(swirl, HALF)))
            angle = self.s16(spell + 0x64) + turn
            ox = C.mul(C.cos16(angle), width)
            oy = C.mul(C.sin16(angle), width)
            point = C.vec3_hermite(t, p0, p1, m0, m1)
            point = (C.add(point[0], ox), C.add(point[1], oy), C.add(point[2], ZERO))
            k = 0xBF065E67
            velocity = tuple(C.mul(C.sub(previous[i], point[i]), k) for i in range(3))
            self.call('particle_spawn', self.PDEF_CYCLONE_HELIX, point, velocity, ZERO)
            t = C.add(t, 0x3C656041)
            previous = point
            if not C.le(t, ONE):
                break
        if self.s8(spell) >= 9 and abs(frame) % 3 == 0:
            point = (u32(spell + 0x6C), u32(spell + 0x70), C.add(u32(spell + 0x74), 0x42840000))
            vx = C.mul(C.sub(self.unit(self.spell_rand(spell)), HALF), 0x41F00000)
            vy = C.mul(C.sub(self.unit(self.spell_rand(spell)), HALF), 0x41F00000)
            vz = C.mul(self.unit(self.spell_rand(spell)), 0x421C0000)
            self.call('particle_spawn', self.PDEF_CYCLONE_SPARK, point, (vx, vy, vz), ZERO)


    # =====================================================================================
    # Bow skills 43-47: what the skill arrows share (docs/spec/skills-35-68.md Part 2,
    # "Bow skills: shared path", S.1 and S.9)
    # =====================================================================================
    def bow_can_use(self, caster, text_key):
        """Slot 1 of the five bow skills (0x2d5fc4, 0x2d6d40, 0x2d877c, 0x2d9a18,
        0x2dac30): 1 for a caster without the player flag and for a player whose weapon
        class (record +0x4a86) is 4, a bow; otherwise the warning text for 180 frames on
        that player's slot, and 0."""
        if not self.u32(caster + 0xC) & 0x40 or self.s8(self.record(caster) + 0x4A86) == 4:
            return 1
        self.call('hud_showMessage', self.call('text_lookup', text_key), 0xB4, self.u32(caster + 0x3C8), 0)
        return 0

    def local_vec(self, values):
        """A vector the original keeps in its frame, for a callee that takes its address."""
        addr = self.alloca(12)
        for i in range(3):
            self.mem.poke(addr + 4 * i, 4, values[i] & M32)
        return addr

    def _arrow_light(self, obj, pos, radius, falloff, colour):
        """The light record every skill arrow carries at +0x70 (position +0xa0)."""
        w32, w16 = self.w32, self.w16
        self.w8(obj + 0x79, 0)
        self.wvec(obj + 0xA0, pos)
        w32(obj + 0x94, radius)
        w32(obj + 0x8C, radius)
        w32(obj + 0x98, falloff)
        w32(obj + 0x90, falloff)
        for off in (0x7A, 0x82):
            w16(obj + off, colour[0])
            w16(obj + off + 2, colour[1])
            w16(obj + off + 4, colour[2])
        w32(obj + 0x9C, 0)
        w16(obj + 0x80, 0)
        w16(obj + 0x88, 0)
        self.w8(obj + 0x78, 0)
        self.call('light_link', obj + 0x70)

    def _arrow_velocity_facing(self, obj, speed):
        """Level flight along the facing at +0x64: velocity +0x54 = (cos, sin, 0) x speed."""
        speed = C.from_int(s32(speed))
        self.w32(obj + 0x54, C.mul(C.cos16(self.s16(obj + 0x64)), speed))
        self.w32(obj + 0x58, C.mul(C.sin16(self.s16(obj + 0x64)), speed))
        self.w32(obj + 0x5C, 0)

    def _arrow_velocity_dir(self, obj, direction, speed):
        """The second constructors: velocity +0x54 = the direction, normalised with a
        reciprocal square root, times the speed (the vertical part is kept)."""
        speed = C.from_int(s32(speed))
        self.wvec(obj + 0x54, direction)
        x, y, z = self.vec(obj + 0x54)
        inverse = C.rsqrt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z)))
        self.w32(obj + 0x5C, C.mul(C.mul(z, inverse), speed))
        self.w32(obj + 0x54, C.mul(C.mul(x, inverse), speed))
        self.w32(obj + 0x58, C.mul(C.mul(y, inverse), speed))

    def _arrow_blocked_for_player(self, other):
        """What a player's skill arrow passes through: objects with flag 0x1000000, and
        creatures with creature flag 0x4000000."""
        flags = self.u32(other + 0xC)
        return bool(flags & 0x1000000 or (flags & 0x20 and self.u64(other + 0xA8) & 0x4000000))

    # =====================================================================================
    # 43 firearrow: docs/spec/skills-35-68.md section 43
    # =====================================================================================
    VT_FIRE_ARROW = 0x518DE0
    S_FIREARROW_WARN, S_FIREARROW_LUMP, S_FIREARROW_SOUND, S_FIREARROW_HIT = 0x54F278, 0x54F2A0, 0x54F2A8, 0x54F2C0

    def firearrow_can_use(self, skill, caster):
        """SkillFireArrow_canUse 0x2d5fc4."""
        return self.bow_can_use(caster, self.S_FIREARROW_WARN)

    def firearrow_cast(self, skill, level, caster, pos, facing):
        """SkillFireArrow_cast 0x2d603c (skill, level, caster, position, facing) -> 0.
        pool_new(0xb0); with a block the level goes through slot 14 (level, 20) and the
        arrow is built 12 below the cast position, flying along `facing`."""
        start = (self.u32(pos), self.u32(pos + 4), C.sub(self.u32(pos + 8), F_12))
        obj = self.call('pool_new', 0xB0)
        if obj:
            level = self.skill_call(skill, 14, level, 0x14)
            self.firearrow_ctor(obj, self.local_vec(start), facing, caster, level, skill)
        return 0

    def _firearrow_common(self, obj, pos, owner, level, skill):
        pos = self.vec(pos)
        self.projectile_ctor(obj, self.local_vec(pos), owner, 0)
        self.w32(obj + 0x48, self.VT_FIRE_ARROW)
        self._arrow_light(obj, pos, 0x42C00000, 0x38E38E38, (0x6D, 100, 0x4C))
        self.w32(obj + 0xAC, skill)

    def _firearrow_stats(self, obj, owner):
        """Radius +0x1c = statistic 2, and the speed = statistic 1, both through slot 12
        with cap 10 (a monster's arrow: level limited to 10, tier 2 where there is one)."""
        skill = self.u32(obj + 0xAC)
        self.w32(obj + 0x1C, C.from_int(self.stat_for(skill, 2, self.u32(obj + 0x6C), owner, 10)))
        return self.stat_for(self.u32(obj + 0xAC), 1, self.u32(obj + 0x6C), owner, 10)

    def firearrow_ctor(self, obj, pos, facing, owner, level, skill):
        """FireArrowProjectile_ctor 0x2d6238 (object, position, facing, owner, level,
        skill).  Projectile base (ONE SHARED DRAW), light, skill +0xac, facing +0x64,
        level +0x6c, radius and speed from the statistics, age +0x68 = 0, ended +0x60 =
        0, on the every-frame run list, launch sound."""
        self._firearrow_common(obj, pos, owner, level, skill)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x6C, level)
        speed = self._firearrow_stats(obj, owner)
        self._arrow_velocity_facing(obj, speed)
        self.w32(obj + 0x68, 0)
        self.w32(obj + 0x60, 0)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', self.S_FIREARROW_LUMP, self.S_FIREARROW_SOUND), obj, ONE)

    def firearrow_ctor2(self, obj, pos, direction, owner, level, skill):
        """FireArrowProjectile_ctor2 0x2d6440 (object, position, direction, owner, level,
        skill): the monsters' constructor.  As the first, but the facing is
        atan2_16(direction.y, direction.x) and the velocity is the normalised direction
        times the speed."""
        direction = self.vec(direction)
        self._firearrow_common(obj, pos, owner, level, skill)
        facing = C.atan2_16(direction[1], direction[0])
        self.w32(obj + 0x6C, level)
        self.w16(obj + 0x64, facing)
        speed = self._firearrow_stats(obj, owner)
        self._arrow_velocity_dir(obj, direction, speed)
        self.w32(obj + 0x68, 0)
        self.w32(obj + 0x60, 0)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', self.S_FIREARROW_LUMP, self.S_FIREARROW_SOUND), obj, ONE)

    def firearrow_run(self, obj):
        """FireArrowProjectile_run 0x2d66ac, slot 4.  Nothing once ended.  Age +0x68 += 1;
        obj_moveAndCollide with the velocity (the hit handler runs inside it); terrain:
        end(1); age 601 or more: end(0); else a camera-gated puff and the light follows."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        self.w32(obj + 0x68, u32(obj + 0x68) + 1)
        result = self.obj_move_and_collide(obj, self.local_vec(self.vec(obj + 0x54)))
        if result & 1:
            return self.firearrow_end(obj, result & 1)
        if not self.s32(obj + 0x68) < 0x259:
            return self.firearrow_end(obj, 0)
        radius = u32(obj + 0x1C)
        size = C.add(C.mul(C.mul(radius, radius), 0x3CB42246), 0x3E88B439)
        step = tuple(C.mul(u32(obj + 0x54 + 4 * i), DT) for i in range(3))
        self.call('fx_impactPuffNearCamera', self.vec(obj + 0x10), step, 1, radius, size)
        self.wvec(obj + 0xA0, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x70)

    def firearrow_on_hit(self, obj, other):
        """FireArrowProjectile_onHit 0x2d685c, slot 6 (arrow, object touched).

        Nothing without an owner (the handle +0x4c is empty once the owner is destroyed).
        s = statistic 0 through slot 13 (level, owner handle, cap 0); ONE OWN DRAW r.
        Monster owner: its slot 20 must accept the object; damage_apply(s .. s + int(s x
        0.2 x r/65536), attack 100000, flags 0x60, descriptor entry (0x15, s, s, 0)).
        Player owner: not through objects with flag 0x1000000 or creatures with creature
        flag 0x4000000; slot 20; damage = the owner record's weapon minimum and maximum
        (+0xd0, +0xd4) READ NOW, flags 0x60 with the knock bits by level (6-10: 0x40000,
        11-15: 0x80000, 16+: 0x200000), descriptor entry (0x1f, 100, s, s).
        Then end(2).  There is no "already hit" test: every object overlapped in the same
        frame is damaged."""
        u32 = self.u32
        if not u32(obj + 0x4C):
            return
        skill = u32(obj + 0xAC)
        amount = s32(self.skill_call(skill, 13, 0, u32(obj + 0x6C), obj + 0x4C, 0))
        draw = self.obj_rand(obj)
        base = C.from_int(amount)
        extra = C.to_int(C.mul(C.mul(base, 0x3E4CCCCC), self.unit(draw)))
        owner = self.handle_obj(obj + 0x4C)
        if not u32(owner + 0xC) & 0x40:
            if not self.vcall(owner, 20, other):
                return
            desc = self.descriptor((0x15, amount & 0xFFFF, amount & 0xFFFF, 0))
            self.call('damage_apply', other, self.handle_obj(obj + 0x4C), 100000, 0, 0, 0x60, desc, 0,
                      base, C.from_int(amount + s32(extra)))
        else:
            if self._arrow_blocked_for_player(other) or not self.vcall(owner, 20, other):
                return
            level = self.s32(obj + 0x6C)
            flags = 0x200060 if level >= 16 else 0x80060 if level > 10 else 0x40060 if level > 5 else 0x60
            desc = self.descriptor((0x1F, 100, amount & 0xFFFF, amount & 0xFFFF))
            owner = self.handle_obj(obj + 0x4C)
            rec = self.record(owner)
            self.call('damage_apply', other, owner, 100000, 0, 0, flags, desc, 0,
                      C.from_int(self.s32(rec + 0xD0)), C.from_int(self.s32(rec + 0xD4)))
        self.firearrow_end(obj, 2)

    def firearrow_end(self, obj, reason):
        """FireArrowProjectile_end 0x2d6bb8 (arrow, reason), once per arrow (guard +0x60):
        the impact sound unless the reason is 0 (expiry), obj_delete, ended = 1."""
        if self.u32(obj + 0x60):
            return
        if reason:
            self.call('sound_playOnObject', self.call('res_find', self.S_FIREARROW_LUMP, self.S_FIREARROW_HIT), obj, ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)


    def obj_ball(self, obj):
        """A unit-ball sample from an object's own generator (three draws per try)."""
        return self.ball(lambda: self.obj_rand(obj))

    def spell_ball(self, spell):
        """A unit-ball sample from a spell's own generator (three draws per try)."""
        return self.ball(lambda: self.spell_rand(spell))

    def _monster_spread(self, amount, draw):
        """(low, high) of a monster-owned effect: amount .. amount + int(amount x 0.2 x
        draw / 65536), as floats."""
        base = C.from_int(amount)
        extra = C.to_int(C.mul(C.mul(base, 0x3E4CCCCC), self.unit(draw)))
        return base, C.from_int(amount + s32(extra))

    def _arrow_flight(self, obj, end, particles, end_reason_terrain=1):
        """The run every skill arrow but the fire one shares: nothing once ended (+0x60);
        age +0x6c += 1; obj_moveAndCollide (the hit handler runs inside); terrain: end;
        age 601 or more: end(0); else the flight particles."""
        if self.u32(obj + 0x60):
            return
        self.w32(obj + 0x6C, self.u32(obj + 0x6C) + 1)
        result = self.obj_move_and_collide(obj, self.local_vec(self.vec(obj + 0x54)))
        if result & 1:
            return end(obj, end_reason_terrain)
        if not self.s32(obj + 0x6C) < 0x259:
            return end(obj, 0)
        particles(obj)

    # =====================================================================================
    # 44 coldarrow: docs/spec/skills-35-68.md section 44
    # =====================================================================================
    VT_COLD_ARROW = 0x518EF8
    S_COLDARROW_WARN, S_COLDARROW_LUMP, S_COLDARROW_SOUND, S_COLDARROW_HIT = 0x54F360, 0x54F388, 0x54F390, 0x54F3A8
    PDEF_COLD_A, PDEF_COLD_B, PDEF_COLD_GROUND = 0x8E5730, 0x8E5780, 0x8E57D0

    def coldarrow_can_use(self, skill, caster):
        """SkillColdArrow_canUse 0x2d6d40."""
        return self.bow_can_use(caster, self.S_COLDARROW_WARN)

    def coldarrow_cast(self, skill, level, caster, pos, facing):
        """SkillColdArrow_cast 0x2d6db8 -> 0: as FireArrow's (block 0xb0, 12 below, slot
        14 (level, 20))."""
        start = (self.u32(pos), self.u32(pos + 4), C.sub(self.u32(pos + 8), F_12))
        obj = self.call('pool_new', 0xB0)
        if obj:
            level = self.skill_call(skill, 14, level, 0x14)
            self.coldarrow_ctor(obj, self.local_vec(start), facing, caster, level, skill)
        return 0

    def _coldarrow_common(self, obj, pos, owner, skill):
        pos = self.vec(pos)
        self.projectile_ctor(obj, self.local_vec(pos), owner, 0)
        self.w32(obj + 0x48, self.VT_COLD_ARROW)
        self._arrow_light(obj, pos, 0x431C0000, 0x382C598A, (0x59, 0x59, 0x82))
        self.w32(obj + 0xAC, skill)

    def _arrow_finish(self, obj, lump, sound):
        self.w32(obj + 0x6C, 0)
        self.w32(obj + 0x60, 0)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', lump, sound), obj, ONE)

    def coldarrow_ctor(self, obj, pos, facing, owner, level, skill):
        """ColdArrowProjectile_ctor 0x2d6fb4 (object, position, facing, owner, level,
        skill).  Projectile base (ONE SHARED DRAW), light, radius +0x1c = 7.0, level
        +0x68, speed = statistic 1 through slot 12 (cap 10), age +0x6c = 0."""
        self._coldarrow_common(obj, pos, owner, skill)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x1C, 0x40E00000)
        self.w32(obj + 0x68, level)
        self._arrow_velocity_facing(obj, self.stat_for(skill, 1, level, owner, 10))
        self._arrow_finish(obj, self.S_COLDARROW_LUMP, self.S_COLDARROW_SOUND)

    def coldarrow_ctor2(self, obj, pos, direction, owner, level, skill):
        """ColdArrowProjectile_ctor2 0x2d718c: the monsters' constructor (direction
        instead of facing)."""
        direction = self.vec(direction)
        self._coldarrow_common(obj, pos, owner, skill)
        facing = C.atan2_16(direction[1], direction[0])
        self.w32(obj + 0x68, level)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x1C, 0x40E00000)
        speed = self.stat_for(self.u32(obj + 0xAC), 1, level, owner, 10)
        self._arrow_velocity_dir(obj, direction, speed)
        self._arrow_finish(obj, self.S_COLDARROW_LUMP, self.S_COLDARROW_SOUND)

    def _flight_particle(self, obj, definition, speed, reach):
        """One flight particle: velocity = a ball sample x speed, position = the arrow
        + a second ball sample x radius x reach.  Six OWN draws or more."""
        v = self.obj_ball(obj)
        velocity = tuple(C.mul(c, speed) for c in v)
        w = self.obj_ball(obj)
        radius = self.u32(obj + 0x1C)
        point = tuple(C.add(self.u32(obj + 0x10 + 4 * i), C.mul(C.mul(w[i], radius), reach)) for i in range(3))
        self.call('particle_spawn', definition, point, velocity, ZERO)

    def _coldarrow_particles(self, obj):
        self.wvec(obj + 0xA0, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x70)
        for _ in range(7):
            self._flight_particle(obj, self.PDEF_COLD_A, 0x41700000, 0x3E800000)
        self._flight_particle(obj, self.PDEF_COLD_B, 0x41600000, 0x3E800000)

    def coldarrow_run(self, obj):
        """ColdArrowProjectile_run 0x2d73c8, slot 4: the shared flight; each flying frame
        the light follows and 8 particles are made (7 + 1, two ball samples of OWN draws
        each)."""
        self._arrow_flight(obj, self.coldarrow_end, self._coldarrow_particles)

    def coldarrow_on_hit(self, obj, other):
        """ColdArrowProjectile_onHit 0x2d7aac, slot 6.

        Nothing without an owner.  Player owner: not through flag 0x1000000 / creature
        flag 0x4000000 objects; slot 20; effect 10; damage = the owner record's weapon
        minimum and maximum read now, flags 0x40 (11-15: | 0x40000, 16+: | 0x80000),
        descriptor entry (0x20, 100, statistic 2, statistic 2) through slot 13 (cap 0).
        Monster owner: slot 20; effect 10; s = statistic 0 (slot 13, cap 0); ONE OWN DRAW;
        damage s .. s + int(s x 0.2 x r/65536), flags 0x40, no descriptor.
        A creature (flag 0x20) then gets its chill timer +0x344 raised by half of
        statistic 3 (slot 13, cap 10; C division) through Creature_setEffectTimer(1).
        Then end(2)."""
        u32 = self.u32
        if not u32(obj + 0x4C):
            return
        owner = self.handle_obj(obj + 0x4C)
        skill = u32(obj + 0xAC)
        if u32(owner + 0xC) & 0x40:
            if self._arrow_blocked_for_player(other) or not self.vcall(owner, 20, other):
                return
            self.call('fx_spawn', 10, self.vec(obj + 0x10))
            level = self.s32(obj + 0x68)
            flags = 0x80040 if level >= 16 else 0x40040 if level > 10 else 0x40
            a = self.skill_call(skill, 13, 2, level, obj + 0x4C, 0)
            b = self.skill_call(u32(obj + 0xAC), 13, 2, u32(obj + 0x68), obj + 0x4C, 0)
            owner = self.handle_obj(obj + 0x4C)
            rec = self.record(owner)
            self.call('damage_apply', other, owner, 100000, 0, 0, flags, self.descriptor((0x20, 100, a, b)), 0,
                      C.from_int(self.s32(rec + 0xD0)), C.from_int(self.s32(rec + 0xD4)))
        else:
            if not self.vcall(owner, 20, other):
                return
            self.call('fx_spawn', 10, self.vec(obj + 0x10))
            amount = s32(self.skill_call(skill, 13, 0, u32(obj + 0x68), obj + 0x4C, 0))
            low, high = self._monster_spread(amount, self.obj_rand(obj))
            self.call('damage_apply', other, self.handle_obj(obj + 0x4C), 100000, 0, 0, 0x40, 0, 0, low, high)
        if u32(other + 0xC) & 0x20:
            seconds = s32(self.skill_call(u32(obj + 0xAC), 13, 3, u32(obj + 0x68), obj + 0x4C, 10))
            half = (seconds + (1 if seconds < 0 else 0)) >> 1
            self.call('Creature_setEffectTimer', other, 1, self.handle_obj(obj + 0x4C),
                      C.add(u32(other + 0x344), C.from_int(half)))
        self.coldarrow_end(obj, 2)

    def coldarrow_end(self, obj, reason):
        """ColdArrowProjectile_end 0x2d7ecc (arrow, reason), once per arrow.

        Reason 0 (expiry): only obj_delete.  Reason 1 (terrain) first makes a ground
        burst of level x 10 + 27 particles round the point one radius ahead (each a ball
        sample of OWN draws, mirrored in the plane when it points along the velocity).
        Then, for any reason but 0, level x 10 burst pairs: two ball samples each (the
        second is drawn and not used), a second, slower particle on every fourth; and the
        impact sound."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        if reason:
            if s32(reason) == 1:
                radius = u32(obj + 0x1C)
                bx = C.add(u32(obj + 0x10), C.mul(C.cos16(self.s16(obj + 0x64)), radius))
                by = C.add(u32(obj + 0x14), C.mul(C.sin16(self.s16(obj + 0x64)), u32(obj + 0x1C)))
                bz = u32(obj + 0x18)
                count = 0
                while count < self.s32(obj + 0x68) * 10 + 0x1B:
                    v = self.obj_ball(obj)
                    along = C.add(C.mul(v[0], u32(obj + 0x54)), C.mul(v[1], u32(obj + 0x58)))
                    x, y = (C.neg(v[0]), C.neg(v[1])) if C.lt(0x3F34FDF3, along) else (v[0], v[1])
                    level = self.s32(obj + 0x68)
                    k = C.from_int(int(level / 3) + 2)
                    point = (C.add(bx, C.mul(x, k)), C.add(by, C.mul(y, k)), C.add(bz, C.mul(v[2], k)))
                    count += 1
                    self.call('particle_spawn', self.PDEF_COLD_GROUND, point, (0, 0, 0), ZERO)
            index = 0
            while C.lt(C.from_int(index), C.mul(C.from_int(self.s32(obj + 0x68) * 0x14), HALF)):
                v = self.obj_ball(obj)
                velocity = [C.mul(c, 0x41F80000) for c in v]
                if C.lt(0x3F34FDF3, C.add(C.mul(velocity[0], u32(obj + 0x54)), C.mul(velocity[1], u32(obj + 0x58)))):
                    velocity[0], velocity[1] = C.neg(velocity[0]), C.neg(velocity[1])
                self.obj_ball(obj)                      # a position is computed from it and never used
                self.call('particle_spawn', self.PDEF_COLD_B, self.vec(obj + 0x10), tuple(velocity), ZERO)
                if index & 3 == 0:
                    velocity = [C.mul(c, 0x3F400000) for c in velocity]
                    self.call('particle_spawn', self.PDEF_COLD_A, self.vec(obj + 0x10), tuple(velocity), ZERO)
                index += 1
            self.call('sound_playOnObject', self.call('res_find', self.S_COLDARROW_LUMP, self.S_COLDARROW_HIT), obj, ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)

    # =====================================================================================
    # 45 poisonarrow: docs/spec/skills-35-68.md section 45
    # =====================================================================================
    VT_POISON_ARROW = 0x519010
    S_POISONARROW_WARN, S_POISONARROW_LUMP, S_POISONARROW_SOUND, S_POISONARROW_HIT = 0x54F448, 0x54F488, 0x54F490, 0x54F4A8
    PDEF_POISON_A, PDEF_POISON_B, PDEF_POISON_RING = 0x8E5820, 0x8E5870, 0x8E58C0

    def poisonarrow_can_use(self, skill, caster):
        """SkillPoisonArrow_canUse 0x2d877c."""
        return self.bow_can_use(caster, self.S_POISONARROW_WARN)

    def poisonarrow_cast(self, skill, level, caster, pos, facing):
        """SkillPoisonArrow_cast 0x2d87f4 -> 0 (block 0xb0, 12 below, slot 14 (level, 1))."""
        start = (self.u32(pos), self.u32(pos + 4), C.sub(self.u32(pos + 8), F_12))
        obj = self.call('pool_new', 0xB0)
        if obj:
            level = self.skill_call(skill, 14, level, 1)
            self.poisonarrow_ctor(obj, self.local_vec(start), facing, caster, level, skill)
        return 0

    def _poisonarrow_common(self, obj, pos, owner, skill):
        pos = self.vec(pos)
        self.projectile_ctor(obj, self.local_vec(pos), owner, 0)
        self.w32(obj + 0x48, self.VT_POISON_ARROW)
        self._arrow_light(obj, pos, 0x42F00000, 0x3891A2B3, (0x3C, 0x84, 0x44))
        self.w32(obj + 0xAC, skill)

    def poisonarrow_ctor(self, obj, pos, facing, owner, level, skill):
        """PoisonArrowProjectile_ctor 0x2d8a64: as ColdArrow's with radius 5.0."""
        self._poisonarrow_common(obj, pos, owner, skill)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x1C, 0x40A00000)
        self.w32(obj + 0x68, level)
        self._arrow_velocity_facing(obj, self.stat_for(skill, 1, level, owner, 10))
        self._arrow_finish(obj, self.S_POISONARROW_LUMP, self.S_POISONARROW_SOUND)

    def poisonarrow_ctor2(self, obj, pos, direction, owner, level, skill):
        """PoisonArrowProjectile_ctor2 0x2d8c40: the monsters' constructor."""
        direction = self.vec(direction)
        self._poisonarrow_common(obj, pos, owner, skill)
        facing = C.atan2_16(direction[1], direction[0])
        self.w32(obj + 0x68, level)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x1C, 0x40A00000)
        speed = self.stat_for(self.u32(obj + 0xAC), 1, level, owner, 10)
        self._arrow_velocity_dir(obj, direction, speed)
        self._arrow_finish(obj, self.S_POISONARROW_LUMP, self.S_POISONARROW_SOUND)

    def _poisonarrow_particles(self, obj):
        self.wvec(obj + 0xA0, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x70)
        for index in range(0x2E):
            self._flight_particle(obj, self.PDEF_POISON_A if index & 1 else self.PDEF_POISON_B, 0x41F00000, 0x3F020BF5)

    def poisonarrow_run(self, obj):
        """PoisonArrowProjectile_run 0x2d8e80, slot 4: the shared flight; 46 particles a
        flying frame (two ball samples of OWN draws each)."""
        self._arrow_flight(obj, self.poisonarrow_end, self._poisonarrow_particles)

    def poisonarrow_on_hit(self, obj, other):
        """PoisonArrowProjectile_onHit 0x2d932c, slot 6.

        Nothing without an owner.  s = statistic 0 (slot 13, cap 0); ONE OWN DRAW (made
        for either kind of owner).  Monster owner: slot 20; damage s .. s + int(s x 0.2 x
        r/65536), flags 0x10040.  Player owner: the usual pass-through tests and slot 20;
        damage = the record's weapon minimum + s .. maximum + s, flags 0x10040 (11-15: |
        0x40000, 16+: | 0x80000).  No descriptor either way.  A creature then gets its
        poison timer set to statistic 3 seconds (slot 12 with the owner, cap 10) through
        Creature_setEffectTimer(3).  Then end(2)."""
        u32 = self.u32
        if not u32(obj + 0x4C):
            return
        skill = u32(obj + 0xAC)
        amount = s32(self.skill_call(skill, 13, 0, u32(obj + 0x68), obj + 0x4C, 0))
        draw = self.obj_rand(obj)
        owner = self.handle_obj(obj + 0x4C)
        if not u32(owner + 0xC) & 0x40:
            if not self.vcall(owner, 20, other):
                return
            low, high = self._monster_spread(amount, draw)
            self.call('damage_apply', other, self.handle_obj(obj + 0x4C), 100000, 0, 0, 0x10040, 0, 0, low, high)
        else:
            if self._arrow_blocked_for_player(other) or not self.vcall(owner, 20, other):
                return
            owner = self.handle_obj(obj + 0x4C)
            level = self.s32(obj + 0x68)
            flags = 0x90040 if level > 15 else 0x50040 if level > 10 else 0x10040
            rec = self.record(owner)
            self.call('damage_apply', other, owner, 100000, 0, 0, flags, 0, 0,
                      C.from_int(self.s32(rec + 0xD0) + amount), C.from_int(self.s32(rec + 0xD4) + amount))
        if u32(other + 0xC) & 0x20:
            seconds = self.stat_for(u32(obj + 0xAC), 3, u32(obj + 0x68), self.handle_obj(obj + 0x4C), 10)
            self.call('Creature_setEffectTimer', other, 3, self.handle_obj(obj + 0x4C), C.from_int(seconds))
        self.poisonarrow_end(obj, 2)

    def poisonarrow_end(self, obj, reason=0):
        """PoisonArrowProjectile_end 0x2d95c8 (arrow), once per arrow; the reason is not
        looked at, so an expired arrow leaves its cloud too.

        A ring of 213 particles (every 0x135 angle units, speed 9).  With an owner:
        pool_new(0x70) and a poisonGasSpell at the arrow (life = statistic 3 x 60 frames,
        radius = statistic 2 x 12, both tier 1 through slot 10, damage 5) - a GameObject,
        so ONE SHARED DRAW unless the pool had no block.  Sound, obj_delete."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        angle = 0
        while angle < 0x10000:
            velocity = (C.mul(C.cos16(angle), 0x41100000), C.mul(C.sin16(angle), 0x41100000), 0)
            self.call('particle_spawn', self.PDEF_POISON_RING, self.vec(obj + 0x10), velocity, ZERO)
            angle += 0x135
        if u32(obj + 0x4C):
            cloud = self.call('pool_new', 0x70)
            if cloud:
                radius = self.stat(u32(obj + 0xAC), 2, u32(obj + 0x68))
                life = self.stat(u32(obj + 0xAC), 3, u32(obj + 0x68))
                self.draws += 1
                self.call('poisonGasSpell_ctor', cloud, self.vec(obj + 0x10), life * 0x3C, radius * 0xC, 0,
                          self.handle_obj(obj + 0x4C), 5)
        self.call('sound_playOnObject', self.call('res_find', self.S_POISONARROW_LUMP, self.S_POISONARROW_HIT), obj, ONE)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)

    # =====================================================================================
    # 47 explodearrow: docs/spec/skills-35-68.md section 47
    # =====================================================================================
    VT_EXPLODE_ARROW = 0x519240
    S_EXPLODEARROW_WARN, S_EXPLODEARROW_LUMP, S_EXPLODEARROW_SOUND = 0x54F648, 0x54F670, 0x54F678
    S_EXPLODE_ICE, S_EXPLODE_STONE, S_EXPLODE_HIT = 0x54F690, 0x54F6A8, 0x54F6C0
    PDEF_EXPLODE = 0x8E5960

    def explodearrow_can_use(self, skill, caster):
        """SkillExplodeArrow_canUse 0x2dac30."""
        return self.bow_can_use(caster, self.S_EXPLODEARROW_WARN)

    def explodearrow_cast(self, skill, level, caster, pos, facing):
        """SkillExplodeArrow_cast 0x2daca8 -> 0: slot 14 (level, 9) first, then
        pool_new(0x74) and the arrow 12 below the cast position."""
        level = self.skill_call(skill, 14, level, 9)
        start = (self.u32(pos), self.u32(pos + 4), C.sub(self.u32(pos + 8), F_12))
        obj = self.call('pool_new', 0x74)
        if obj:
            self.explodearrow_ctor(obj, self.local_vec(start), facing, caster, level, skill)
        return 0

    def explodearrow_ctor(self, obj, pos, facing, owner, level, skill):
        """ExplodeArrowProjectile_ctor 0x2daeb4 (object, position, facing, owner, level,
        skill).  Projectile base (ONE SHARED DRAW); no light; radius 8.0; skill +0x70,
        level +0x68; speed = statistic 1 through slot 12 with the owner READ BACK THROUGH
        THE HANDLE +0x4c (no null test: an arrow built without an owner faults), cap 10."""
        self.projectile_ctor(obj, self.local_vec(self.vec(pos)), owner, 0)
        self.w16(obj + 0x64, facing)
        self.w32(obj + 0x48, self.VT_EXPLODE_ARROW)
        owner = self.u32(self.u32(obj + 0x4C) + 0xC)
        self.w32(obj + 0x1C, 0x41000000)
        self.w32(obj + 0x70, skill)
        self.w32(obj + 0x68, level)
        self._arrow_velocity_facing(obj, self.stat_for(skill, 1, level, owner, 10))
        self._arrow_finish(obj, self.S_EXPLODEARROW_LUMP, self.S_EXPLODEARROW_SOUND)

    def explodearrow_ctor2(self, obj, pos, direction, owner, level, skill):
        """ExplodeArrowProjectile_ctor2 0x2dafe0: the monsters' constructor."""
        direction = self.vec(direction)
        self.projectile_ctor(obj, self.local_vec(self.vec(pos)), owner, 0)
        self.w32(obj + 0x48, self.VT_EXPLODE_ARROW)
        self.w32(obj + 0x70, skill)
        facing = C.atan2_16(direction[1], direction[0])
        self.w32(obj + 0x68, level)
        self.w16(obj + 0x64, facing)
        owner = self.u32(self.u32(obj + 0x4C) + 0xC)
        self.w32(obj + 0x1C, 0x41000000)
        speed = self.stat_for(self.u32(obj + 0x70), 1, level, owner, 10)
        self._arrow_velocity_dir(obj, direction, speed)
        self._arrow_finish(obj, self.S_EXPLODEARROW_LUMP, self.S_EXPLODEARROW_SOUND)

    def _explodearrow_particles(self, obj):
        u32 = self.u32
        for _ in range(6):
            v = self.obj_ball(obj)
            velocity = tuple(C.mul(c, 0x40400000) for c in v)
            step = tuple(C.mul(u32(obj + 0x54 + 4 * i), DT) for i in range(3))
            along = self.unit(self.obj_rand(obj))
            point = tuple(C.add(u32(obj + 0x10 + 4 * i), C.mul(step[i], along)) for i in range(3))
            self.call('particle_spawn', self.PDEF_EXPLODE, point, velocity, ZERO)

    def explodearrow_run(self, obj):
        """ExplodeArrowProjectile_run 0x2db17c, slot 4: the shared flight; 6 particles a
        flying frame (a ball sample and one more OWN draw each)."""
        self._arrow_flight(obj, self.explodearrow_explode, self._explodearrow_particles)

    def explodearrow_on_hit(self, obj, other=0):
        """ExplodeArrowProjectile_onHit 0x2db4f0, slot 6: explode(2), whatever was
        touched - there is no test of the object at all."""
        self.explodearrow_explode(obj, 2)

    def explodearrow_explode(self, obj, reason):
        """ExplodeArrowProjectile_explode 0x2db50c (arrow, reason), once per arrow.

        Reason 0 (expiry): only obj_delete.  Otherwise: ONE OWN DRAW picks one of four
        impact sounds (ice on a level with flag 0x40000, else stone), an effect, the two
        sounds, a ring burst of size max(1, level x 0.1), a LightEffect (a GameObject:
        ONE SHARED DRAW unless the pool has no block), a camera shake of level / 2.
        With an owner: half edge = statistic 2 and damage = statistic 0, both through
        slot 12 with the owner (caps 10 and 0); the knock flag is 0 below level 6,
        0x40000 for 6-11, 0x80000 from 12 - except that a monster's arrow of level 12 or
        more makes ONE OWN DRAW and uses 0x40000 when it is odd.  Every object of the box
        query (cube of that half edge, at most 127) in query order: the owner itself is
        knocked (a zero-damage call with the arrow as attacker) when within half the
        edge; a creature the owner's slot 20 rejects is skipped; every other object -
        creature or not - costs ONE OWN DRAW and gets the zero-damage knock call and then
        damage s .. s + int(s x 0.2 x r/65536) from the owner with flags 0x840."""
        u32 = self.u32
        if u32(obj + 0x60):
            return
        if reason:
            here = self.vec(obj + 0x10)
            pick = (self.obj_rand(obj) & 3) + 1
            if u32(G_LEVEL_FLAGS) & 0x40000:
                name = self.call('libc_sprintf', self.S_EXPLODE_ICE, pick)
                self.call('fx_spawn', 8, here)
            else:
                name = self.call('libc_sprintf', self.S_EXPLODE_STONE, pick)
                self.call('fx_spawn', 2, here)
            self.call('sound_playOnObject', self.call('res_find', self.S_EXPLODEARROW_LUMP, name), obj, ONE)
            self.call('sound_playOnObject', self.call('res_find', self.S_EXPLODEARROW_LUMP, self.S_EXPLODE_HIT), obj, ONE)
            self.call('fx_ringBurst', here, C.fmax(ONE, C.mul(C.from_int(self.s32(obj + 0x68)), F_0_1)))
            light = self.call('pool_new', 0xBC)
            if light:
                self.light_effect(light, here, 0x437F0000, 0x41200000, 0x41200000, 0x42F00000, 0x42700000, HALF, 0x3E800000)
            level = self.s32(obj + 0x68)
            self.call('camera_shake', 0, C.from_int((level + (1 if level < 0 else 0)) >> 1))
            if u32(obj + 0x4C):
                skill = u32(obj + 0x70)
                edge = C.from_int(self.stat_for(skill, 2, u32(obj + 0x68), self.handle_obj(obj + 0x4C), 10))
                level = self.s32(obj + 0x68)
                knock = 0
                if level >= 6:
                    knock = 0x40000 if level < 12 else 0x80000
                    if not u32(self.handle_obj(obj + 0x4C) + 0xC) & 0x40:
                        if level >= 12 and self.obj_rand(obj) & 1:
                            knock = 0x40000
                        elif level < 12:
                            knock = 0x40000
                amount = self.stat_for(u32(obj + 0x70), 0, u32(obj + 0x68), self.handle_obj(obj + 0x4C), 0)
                x, y, z = self.vec(obj + 0x10)
                low = (C.sub(x, edge), C.sub(y, edge), C.sub(z, edge))
                high = (C.add(x, edge), C.add(y, edge), C.add(z, edge))
                for other in self.call('world_collectObjectsInBox', low, high, 0x80) or ():
                    owner = self.handle_obj(obj + 0x4C)
                    if other != owner:
                        if u32(other + 0xC) & 0x20 and not self.vcall(owner, 20, other):
                            continue
                        low_f, high_f = self._monster_spread(amount, self.obj_rand(obj))
                        self.call('damage_apply', other, obj, 100000, 0, 0, knock, 0, 0, ZERO, ZERO)
                        self.call('damage_apply', other, self.handle_obj(obj + 0x4C), 100000, 0, 0, 0x840, 0, 0, low_f, high_f)
                        continue
                    dx = C.sub(u32(other + 0x10), u32(obj + 0x10))
                    dy = C.sub(u32(other + 0x14), u32(obj + 0x14))
                    dz = C.sub(u32(other + 0x18), u32(obj + 0x18))
                    distance = C.sqrt(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
                    if C.lt(distance, C.mul(edge, HALF)):
                        self.call('damage_apply', other, obj, 100000, 0, 0, knock, 0, 0, ZERO, ZERO)
        self.call('obj_delete', obj)
        self.w32(obj + 0x60, 1)

    def light_effect(self, block, pos, f12, f13, f14, s0, s1, s2, s3, a2=0, a3=0, rest=(0, 0, 0, 0, 0)):
        """LightEffect_ctor 0x201bd8 as every site of this range calls it: (block,
        position, a2, a3; eight floats in registers, four more on the stack).  The light
        is a GameObject: ONE SHARED DRAW."""
        self.draws += 1
        self.call('LightEffect_ctor', block, pos, a2, a3, f12, f13, f14, *(tuple(rest) + (s0, s1, s2, s3)))


    # =====================================================================================
    # 46 multifire: docs/spec/skills-35-68.md section 46.  The arrows are plain
    # MissileWeapon objects (docs/spec/skills-35-68.md S.8), which this module does not
    # model: their constructor is a callback with all seventeen arguments.
    # =====================================================================================
    S_MULTIFIRE_WARN, S_MULTIFIRE_LUMP, S_MULTIFIRE_SOUND = 0x54F550, 0x54F560, 0x54F568
    G_ITEM_MODELS = AM.G_ITEM_MODELS

    def multifire_can_use(self, skill, caster):
        """SkillMultiFire_canUse 0x2d9a18."""
        return self.bow_can_use(caster, self.S_MULTIFIRE_WARN)

    def multifire_cast(self, skill, level, caster, pos, facing):
        """SkillMultiFire_cast 0x2d9a90 (skill, level, caster, position, facing) -> 0.

          1. lv = slot 14 (level, 20).  pool_new(0xbc): a LightEffect 20 above the cast
             position (a GameObject: ONE SHARED DRAW unless the pool has no block).
          2. count = statistic 2, speed = statistic 1 (slot 12 with lv, cap 10).  The fan
             starts at facing - int(count x 0.5 x 534.5) angle units.
          3. Damage of each arrow.  Player: f = statistic 0 (slot 12 with the level as
             given, cap 10) x 0.01 / count; min and max = the owner record's weapon
             minimum and maximum (+0xd0, +0xd4) x f, each rounded half away from zero;
             damage flags 0x40000; weapon rating and item flags from the bow of the active
             set (record +0x4434 + 4 x set byte +0x4a7c; no null test).  Anyone else: min
             = statistic 0; max = min + round(min x 0.2 x r/65536) with TWO DRAWS OF THE
             PRESENTATION GENERATOR 0x404460 (the first only picks the rounding
             direction) - FINDINGS SB7; flags 0, no weapon rating.
          4. Per arrow: velocity = (cos, sin, 0) x speed at the fan angle; ONE SHARED
             DRAW d; start height = cast height - d/65536 x 6 - 6; pool_new(0x1c8); with
             a block MissileWeapon_ctor (kind 0, the two arrow models, start, velocity,
             fan angle - 0x4000, owner; no samples, min, max, weapon rating, item flags,
             attack rating 10000, damage flags, no item) - a GameObject: ONE MORE SHARED
             DRAW; the fan angle advances by 0x42d.
          5. The launch sound on the caster."""
        u32 = self.u32
        facing = s16(facing)
        here = self.vec(pos)
        lv = self.skill_call(skill, 14, level, 0x14)
        light = self.call('pool_new', 0xBC)
        if light:
            spot = (C.add(here[0], ZERO), here[1], C.add(here[2], 0x41A00000))
            self.light_effect(light, spot, 0x42F80000, 0x42E60000, 0x434C0000, 0x43021771, 0x42700000, HALF, ONE)
        count = self.stat_for(skill, 2, lv, caster, 10)
        fcount = C.from_int(count)
        angle = s16(facing - s32(C.to_int(C.mul(C.mul(fcount, HALF), 0x4405A000))))
        speed = C.from_int(self.stat_for(skill, 1, lv, caster, 10))
        rating = flags = item_flags = 0
        if u32(caster + 0xC) & 0x40:
            rec = self.record(caster)
            bow = u32(rec + 0x4434 + 4 * self.s8(rec + 0x4A7C))
            share = C.div(C.mul(C.from_int(self.stat_for(skill, 0, level, caster, 10)), F_0_01), fcount)
            rec = self.record(caster)
            low = C.round_half_away(C.mul(C.from_int(self.s32(rec + 0xD0)), share))
            high = C.round_half_away(C.mul(C.from_int(self.s32(rec + 0xD4)), share))
            flags = 0x40000
            rating = self.call('item_getModifiedField1a', bow)
            item_flags = u32(bow + 8)
        else:
            low = self.stat_for(skill, 0, level, caster, 10)
            spread = C.mul(C.from_int(low), 0x3E4CCCCC)
            probe = C.mul(spread, self.unit(self.cosmetic_draw()))
            extra = C.mul(spread, self.unit(self.cosmetic_draw()))
            high = low + s32(C.to_int(C.add(extra, HALF) if C.le(ZERO, probe) else C.sub(extra, HALF)))
        for _ in range(max(count, 0)):
            velocity = (C.mul(C.cos16(angle), speed), C.mul(C.sin16(angle), speed), 0)
            dip = C.mul(self.unit(self.draw()), 0x40C00000)
            start = (here[0], here[1], C.add(C.sub(here[2], dip), 0xC0C00000))
            arrow = self.call('pool_new', 0x1C8)
            if arrow:
                self.draws += 1
                self.call('MissileWeapon_ctor', arrow, 0, u32(self.G_ITEM_MODELS + 8), u32(self.G_ITEM_MODELS + 0xC), start,
                          velocity, angle - 0x4000, caster, 0, 0, low, high, rating, item_flags, 10000, flags, 0)
            angle = s16(angle + 0x42D)
        self.call('sound_playOnObject', self.call('res_find', self.S_MULTIFIRE_LUMP, self.S_MULTIFIRE_SOUND), caster, ONE)
        return 0


    # =====================================================================================
    # The passives: 48 archery, 59 lifetap, 60 Blunt, 61 Slashing, 62 strongstance,
    # 63 naturalresistance, 64 stunningstrike.  None has a spell; each is a statistic
    # read by other code through a small helper, and two have an effect function.
    # Blunt and Slashing have no function of their own at all: every slot is the base's.
    # =====================================================================================
    def _stat_via_slot14(self, skill, stat, level, n):
        return self.stat(skill, stat, self.skill_call(skill, 14, level, n))

    def archery_fraction(self, skill, level):
        """SkillArchery_getStat0Fraction 0x2dbcac (skill, level) -> float: statistic 0
        (slot 14 (level, 20), slot 10) x 0.01 - the share Player_recalcDamage adds to a
        bow's damage."""
        return C.mul(C.from_int(self._stat_via_slot14(skill, 0, level, 0x14)), F_0_01)

    def lifetap_fraction(self, skill, level):
        """SkillLifeTap_getStat0Fraction 0x2f8e78 (skill, level) -> float: statistic 0 x
        0.01 (slot 14 (level, 1))."""
        return C.mul(C.from_int(self._stat_via_slot14(skill, 0, level, 1)), F_0_01)

    def lifetap_stat1(self, skill, level):
        """SkillLifeTap_getStat1 0x2f8eec (skill, level) -> statistic 1."""
        return self._stat_via_slot14(skill, 1, level, 1)

    def strongstance_stat0(self, skill, level):
        """SkillStrongStance_getStat0 0x30851c (skill, level) -> statistic 0."""
        return self._stat_via_slot14(skill, 0, level, 0x14)

    def naturalresistance_fraction(self, skill, level):
        """SkillNaturalResistance_getStat0Fraction 0x308a7c (skill, level) -> float:
        statistic 0 x 0.01."""
        return C.mul(C.from_int(self._stat_via_slot14(skill, 0, level, 1)), F_0_01)

    PDEF_STRONGSTANCE = 0x8E7368

    def strongstance_trigger(self, skill, player, a2, a3):
        """SkillStrongStance_trigger 0x308578 (skill, player, two values handed on).

        A LightEffect 36 above the player (a GameObject: ONE SHARED DRAW unless the pool
        has no block); 25 particles, each at a sample point of the player's model chosen
        with ONE DRAW OF THE THIRD GENERATOR 0x404468 (% the sample-point count - a
        division by zero for a model without sample points) and thrown along a
        unit-ball sample from the PRESENTATION GENERATOR 0x404460, normalised, at speed
        10; then pool_new(0x3d8) and the StrongStancePhantom (a creature: one more
        shared draw inside its constructor, not executed here)."""
        u32 = self.u32
        count = s32(self.call('model_getSamplePointCount', u32(player + 0x544)))
        light = self.call('pool_new', 0xBC)
        if light:
            spot = (C.add(u32(player + 0x10), ZERO), u32(player + 0x14), C.add(u32(player + 0x18), 0x42100000))
            self.light_effect(light, spot, 0x43000000, 0x42C80000, 0x42C80000, 0x42F00000, 0x42100000, HALF, HALF)
        for _ in range(0x19):
            draw = self.seed3_draw()
            index = draw - int(draw / count) * count
            point, _second = self.call('model_getSamplePoint', u32(player + 0x544), player + 0x114,
                                       self.vec(player + 0x10), self.s16(player + 0x38), index, 1, 0, ONE)
            x, y, z = self.ball(self.cosmetic_draw)
            inverse = C.rsqrt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z)))
            velocity = tuple(C.mul(C.mul(c, inverse), 0x41200000) for c in (x, y, z))
            self.call('particle_spawn', self.PDEF_STRONGSTANCE, tuple(point), velocity, ZERO)
        phantom = self.call('pool_new', 0x3D8)
        if phantom:
            self.draws += 1
            self.call('StrongStancePhantom_ctor', phantom, player, a2, a3, 0)

    S_STUN_LUMP, S_STUN_SOUND = 0x5520F0, 0x5520F8

    def stunningstrike_stat0_for(self, skill, target, level):
        """SkillStunningStrike_getStat0ForTarget 0x308c10 (skill, target, level) -> the
        stun chance in percent: 0 without a target, for a non-creature and in PvP mode A;
        else statistic 0 (tier 1), but 0 against a boss by name (creature_bossRank 2 or
        more) and at most 5 against a mini-boss (rank 1)."""
        if not target or not self.u32(target + 0xC) & 0x20 or self.u32(G_PVP_MODE_A):
            return 0
        chance = self.stat(skill, 0, level)
        rank = s32(self.call('creature_bossRank', target))
        if rank >= 2:
            return 0
        if rank <= 0:
            return chance
        return 5 if chance >= 6 else chance

    def stunningstrike_effect(self, skill, target):
        """SkillStunningStrike_spawnEffect 0x308cb4 (skill, target): for a creature, the
        sound at its position, a LightEffect 64 above it (ONE SHARED DRAW unless the
        pool has no block), then ONE SHARED DRAW d and the target's slot 30 (stun) with
        int((d/65536 + 1.5) x 60) frames - 90 to 149 - and flash 1."""
        u32 = self.u32
        if not target or not u32(target + 0xC) & 0x20:
            return
        self.call('sound_playAtPos', self.call('res_find', self.S_STUN_LUMP, self.S_STUN_SOUND), self.vec(target + 0x10), ONE)
        light = self.call('pool_new', 0xBC)
        if light:
            spot = (C.add(u32(target + 0x10), ZERO), u32(target + 0x14), C.add(u32(target + 0x18), 0x42800000))
            self.light_effect(light, spot, 0x43210000, 0x430A0000, 0x42800000, 0x43340000, 0x42700000, HALF, HALF)
        frames = C.to_int(C.mul(C.add(self.unit(self.draw()), 0x3FC00000), 0x42700000))
        self.vcall(target, 30, frames, 1)


    def object_ctor(self, name, *args):
        """A callback that constructs a GameObject: ONE SHARED DRAW inside it."""
        self.draws += 1
        return self.call(name, *args)

    @staticmethod
    def half_toward_zero(value):
        value = s32(value)
        return (value + (1 if value < 0 else 0)) >> 1

    # =====================================================================================
    # 42 harmtouch: docs/spec/skills-35-68.md section 42
    # =====================================================================================
    VT_SPELL_HARMTOUCH = 0x518B50
    S_HARMTOUCH_WARN, S_HARMTOUCH_LUMP, S_HARMTOUCH_SOUND = 0x54F048, 0x54F070, 0x54F078
    PDEF_HARMTOUCH_A, PDEF_HARMTOUCH_B = 0x8E55A0, 0x8E55F0

    def harmtouch_can_use(self, skill, caster):
        """SkillHarmTouch_canUse 0x2d2984: as Cyclone's - 0 with a warning for a player
        whose weapon class is 4 or 6, else 1."""
        if not self.u32(caster + 0xC) & 0x40 or self.s8(self.record(caster) + 0x4A86) not in (4, 6):
            return 1
        self.call('hud_showMessage', self.call('text_lookup', self.S_HARMTOUCH_WARN), 0xB4, self.u32(caster + 0x3C8), 0)
        return 0

    def harmtouch_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillHarmTouch_cast 0x2d2a04 -> the SpellHarmTouch or 0 (pool_new(0x1c))."""
        spell = self.call('pool_new', 0x1C)
        if spell:
            self.harmtouch_spell_ctor(spell, level, caster, skill)
        return spell

    def harmtouch_spell_ctor(self, spell, level, owner, skill):
        """SpellHarmTouch_ctor 0x2d2b5c: Spell base (ONE SHARED DRAW), time left +0x18 =
        0.661 s (0x3f29372a), the sound on the owner."""
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_HARMTOUCH)
        self.w32(spell + 0x18, 0x3F29372A)
        self.call('sound_playOnObject', self.call('res_find', self.S_HARMTOUCH_LUMP, self.S_HARMTOUCH_SOUND), owner, ONE)

    def _harmtouch_tint(self, spell, left):
        owner = self.u32(spell + 0xC)
        self.w16(owner + 0x96, 0x71)
        shade = C.to_int(C.mul(C.fmin(left, ONE), 0x43000000))
        self.w16(owner + 0x92, shade)
        self.w16(owner + 0x9A, shade)

    def harmtouch_run(self, spell, pos=0, facing=0):
        """SpellHarmTouch_run 0x2d2c0c, slot 2: time left -= 1/60; below zero the spell
        ends itself, else the owner's tint follows the time left."""
        left = C.sub(self.u32(spell + 0x18), DT)
        self.w32(spell + 0x18, left)
        if C.lt(left, ZERO):
            return self.spell_end(spell)
        self._harmtouch_tint(spell, left)

    def harmtouch_apply_to_hit(self, spell, target, low_out, high_out):
        """SpellHarmTouch_applyToHit 0x2d2cbc (spell, target, int *min, int *max), called
        by Player_meleeHit for a swing that lands while the spell is on the player.

        The tint as in run.  Only for a creature (flag 0x20): 102 particle pairs on
        sample points of the target's model - TWO OWN (spell) DRAWS per pair, 204 in all,
        the first picks the sample point (% the point count: a division by zero for a
        model without points), the second is not used; a LightEffect 73 above the target
        (ONE SHARED DRAW unless the pool has no block); *min = statistic 0 through slot
        12 (owner, cap 10); ONE MORE OWN DRAW r; *max = *min + int(min x 0.2 x r/65536);
        the spell ends itself.  For any other target the range is left alone and the
        spell stays."""
        u32 = self.u32
        self._harmtouch_tint(spell, u32(spell + 0x18))
        if not u32(target + 0xC) & 0x20:
            return
        for _ in range(0x66):
            draw = self.spell_rand(spell)
            count = s32(self.call('model_getSamplePointCount', self.vcall(target, 16)))
            index = draw - int(draw / count) * count
            point, _second = self.call('model_getSamplePoint', self.vcall(target, 16), target + 0x114,
                                       self.vec(target + 0x10), self.s16(target + 0x38), index, 1, 0, ONE)
            owner = u32(spell + 0xC)
            dx, dy = C.sub(point[0], u32(owner + 0x10)), C.sub(point[1], u32(owner + 0x14))
            inverse = C.rsqrt(ONE, C.add(C.mul(dx, dx), C.mul(dy, dy)))
            velocity = (C.mul(C.mul(dx, inverse), 0x4255BD8F), C.mul(C.mul(dy, inverse), 0x4255BD8F), ZERO)
            self.spell_rand(spell)
            self.call('particle_spawn', self.PDEF_HARMTOUCH_A, tuple(point), velocity, ZERO)
            velocity = tuple(C.mul(c, 0x3E0C49BA) for c in velocity)
            self.call('particle_spawn', self.PDEF_HARMTOUCH_B, tuple(point), velocity, ZERO)
        light = self.call('pool_new', 0xBC)
        if light:
            spot = (C.add(u32(target + 0x10), ZERO), u32(target + 0x14), C.add(u32(target + 0x18), 0x42920000))
            self.light_effect(light, spot, 0x42A60000, 0x435A0000, 0x42920000, 0x43580000, 0x42700000, HALF, 0x3EBB63B2)
        amount = self.stat_for(u32(spell + 8), 0, self.s8(spell), u32(spell + 0xC), 10)
        self.w32(low_out, amount)
        extra = C.to_int(C.mul(C.mul(C.from_int(amount), 0x3E4CCCCC), self.unit(self.spell_rand(spell))))
        self.w32(high_out, self.s32(low_out) + s32(extra))
        self.spell_call(spell, 1, 3)

    # =====================================================================================
    # 50 minorhealing: docs/spec/skills-35-68.md section 50
    # =====================================================================================
    VT_SPELL_MINORHEALING = 0x519720
    S_MINORHEALING_LUMP, S_MINORHEALING_SOUND = 0x54FB00, 0x54FB08

    def minorhealing_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillMinorHealing_cast 0x2e022c -> the SpellMinorHealing or 0: slot 14 (level,
        20), pool_new(0x24), the constructor."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.minorhealing_spell_ctor(spell, level, caster, skill)
        return spell

    def minorhealing_spell_ctor(self, spell, level, owner, skill):
        """SpellMinorHealing_ctor 0x2e0388: Spell base (ONE SHARED DRAW); the sound on the
        owner; the target +0x18 = the owner; pool_new(0x5c) and a GlowingShaft at the
        owner (a GameObject: ONE SHARED DRAW unless the pool has no block); clock +0x1c =
        0; healing per tick +0x20 = the maximum hit points of the record the owner's slot
        (+0x3c8, NO player test) names x statistic 0 x 0.01 x (1/90)."""
        u32 = self.u32
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_MINORHEALING)
        self.call('sound_playOnObject', self.call('res_find', self.S_MINORHEALING_LUMP, self.S_MINORHEALING_SOUND),
                  u32(spell + 0xC), ONE)
        self.w32(spell + 0x18, owner)
        shaft = self.call('pool_new', 0x5C)
        if shaft:
            self.object_ctor('GlowingShaft_ctor', shaft, self.vec(u32(spell + 0xC) + 0x10), 0x5A, 0xFA, 200, 100)
        self.w32(spell + 0x1C, 0)
        percent = C.from_int(self.stat(u32(spell + 8), 0, self.s8(spell)))
        rec = self.record(u32(spell + 0x18))
        self.w32(spell + 0x20, C.mul(C.mul(C.mul(u32(rec + 0xB0), percent), F_0_01), 0x3C360B81))

    def minorhealing_run(self, spell, pos=0, facing=0):
        """SpellMinorHealing_run 0x2e04f8, slot 2: clock += 1/60; while hit points + 1 <=
        maximum the record's hit points rise by the per-tick amount (no clamp at the
        maximum); the target is tinted for the first half second; the spell ends itself
        once the clock is above 1.499996."""
        u32 = self.u32
        target = u32(spell + 0x18)
        rec = self.record(target)
        clock = C.add(u32(spell + 0x1C), DT)
        self.w32(spell + 0x1C, clock)
        if C.le(C.add(u32(rec + 0xAC), ONE), u32(rec + 0xB0)):
            self.w32(rec + 0xAC, C.add(u32(rec + 0xAC), u32(spell + 0x20)))
        clock = u32(spell + 0x1C)
        if C.lt(clock, 0x3EFFFF78):
            for off, value in ((0x96, 0x3F), (0x90, 0x68), (0x92, 0x6B), (0x94, 0x40), (0x98, 0x68), (0x9A, 0x6B), (0x9C, 0x40)):
                self.w16(target + off, value)
        if C.lt(0x3FBFFFDE, clock):
            self.spell_end(spell)


    def _sample_point(self, creature, model, draw, count):
        """A sample point of a creature's model picked by a draw: index = draw % count
        (C remainder; the original divides by zero for a model without sample points)."""
        index = draw - int(draw / count) * count
        point, _second = self.call('model_getSamplePoint', model, creature + 0x114, self.vec(creature + 0x10),
                                   self.s16(creature + 0x38), index, 1, 0, ONE)
        return tuple(point)

    # =====================================================================================
    # 54 holyshield: docs/spec/skills-35-68.md section 54
    # =====================================================================================
    VT_SPELL_HOLYSHIELD = 0x519CE0
    S_HOLYSHIELD_LUMP, S_HOLYSHIELD_SOUND = 0x550350, 0x550358
    PDEF_HOLYSHIELD = 0x8E5FF0

    def holyshield_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillHolyShield_cast 0x2e80fc -> the SpellHolyShield or 0 (slot 14 (level, 20),
        pool_new(0x28))."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x28)
        if spell:
            self.holyshield_spell_ctor(spell, level, caster, skill)
        return spell

    def holyshield_spell_ctor(self, spell, level, owner, skill):
        """SpellHolyShield_ctor 0x2e82fc: Spell base (ONE SHARED DRAW); the sound; a
        GlowingShaft at the owner (ONE SHARED DRAW unless the pool has no block); clock
        +0x18 = 0, flash timer +0x1c = 0; duration +0x20 = (float) statistic 1 in seconds,
        through slot 10 (tier 1 for any caster); a particle group at +0x24."""
        u32 = self.u32
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_HOLYSHIELD)
        self.call('sound_playOnObject', self.call('res_find', self.S_HOLYSHIELD_LUMP, self.S_HOLYSHIELD_SOUND),
                  u32(spell + 0xC), ONE)
        shaft = self.call('pool_new', 0x5C)
        if shaft:
            self.object_ctor('GlowingShaft_ctor', shaft, self.vec(u32(spell + 0xC) + 0x10), 0x5A, 0x56, 0x7E, 0xFA)
        self.w32(spell + 0x1C, 0)
        self.w32(spell + 0x18, 0)
        self.w32(spell + 0x20, C.from_int(self.stat(u32(spell + 8), 1, self.s8(spell))))
        self.w32(spell + 0x24, self.call('particleGroup_create'))

    def holyshield_run(self, spell, pos=0, facing=0):
        """SpellHolyShield_run 0x2e8428, slot 2: clock += 1/60, flash timer -= 1/60; once
        the clock is above the duration the spell ends itself; else the particle group
        follows the owner and the owner is tinted."""
        u32 = self.u32
        clock = C.add(u32(spell + 0x18), DT)
        self.w32(spell + 0x18, clock)
        self.w32(spell + 0x1C, C.sub(u32(spell + 0x1C), DT))
        if C.lt(u32(spell + 0x20), clock):
            return self.spell_end(spell)
        owner = u32(spell + 0xC)
        matrix = C.mat34_set_pos_rot_z(list(self.vec(owner + 0x10)), self.s16(owner + 0x38))
        self.call('particleGroup_setMatrix', u32(spell + 0x24), tuple(matrix))
        owner = u32(spell + 0xC)
        for off, value in ((0x9E, 0x37), (0x90, 0x15), (0x92, 0x1C), (0x94, 0x73), (0x98, 0x15), (0x9A, 0x1C), (0x9C, 0x73),
                           (0x96, 0x37)):
            self.w16(owner + off, value)

    def holyshield_absorb(self, spell):
        """SpellHolyShield_absorb 0x2e8534 (spell) -> float, called by Player_takeDamage
        for every hit taken while the shield is up and the player has mana.

        241 particles on sample points of the owner's model: FOUR OR MORE OWN (spell)
        DRAWS each (one for the point, a unit-ball sample for the velocity).  When the
        flash timer +0x1c is not positive: a LightEffect 60 above the owner (ONE SHARED
        DRAW unless the pool has no block) and the timer = 0.263 s - so at most one light
        per 16 frames, and a shared draw inside the damage chain.  Returns statistic 0 x
        0.01 (slot 10): the share of the hit paid from mana."""
        u32 = self.u32
        owner = u32(spell + 0xC)
        count = s32(self.call('model_getSamplePointCount', self.vcall(owner, 16)))
        model = self.vcall(u32(spell + 0xC), 16)
        self.call('particleGroup_begin', u32(spell + 0x24))
        for _ in range(0xF1):
            draw = self.spell_rand(spell)
            point = self._sample_point(u32(spell + 0xC), model, draw, count)
            velocity = tuple(C.mul(c, 0x42140000) for c in self.spell_ball(spell))
            self.call('particle_spawn', self.PDEF_HOLYSHIELD, point, velocity, ZERO)
        self.call('particleGroup_end', u32(spell + 0x24))
        if C.le(u32(spell + 0x1C), ZERO):
            light = self.call('pool_new', 0xBC)
            if light:
                owner = u32(spell + 0xC)
                spot = (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42700000))
                self.light_effect(light, spot, 0x42800000, 0x42800000, 0x42FA0000, 0x42F00000, 0x42700000, HALF, 0x3E86A832)
            self.w32(spell + 0x1C, 0x3E86A832)
        return C.mul(C.from_int(self.stat(u32(spell + 8), 0, self.s8(spell))), F_0_01)

    # =====================================================================================
    # 55 healing (and 86): docs/spec/skills-35-68.md section 55
    # =====================================================================================
    VT_SPELL_HEALING = 0x519E20
    S_HEALING_LUMP, S_HEALING_SOUND = 0x550488, 0x550490
    PDEF_HEALING_RING = 0x8E6040
    F_HEAL_RATE = 0x3C71AA2E                    # 0.01475: a share of maximum hit points per tick
    HEAL_TINT = ((0x9E, 0x32), (0x90, 0x35), (0x92, 0x14), (0x94, 0x0D), (0x98, 0x35), (0x9A, 0x14), (0x9C, 0x0D), (0x96, 0x32))

    def healing_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillHealing_cast 0x2e8cf8 -> the SpellHealing or 0 (slot 14 (level, 14),
        pool_new(0x24)).  `caster` becomes the spell's owner: a monster that heals an
        ally passes the ally."""
        level = self.skill_call(skill, 14, level, 0xE)
        spell = self.call('pool_new', 0x24)
        if spell:
            self.healing_spell_ctor(spell, level, caster, skill)
        return spell

    def healing_spell_ctor(self, spell, level, owner, skill):
        """SpellHealing_ctor 0x2e8ec8: Spell base (ONE SHARED DRAW); sound; a GlowingShaft
        (ONE SHARED DRAW unless the pool has no block); a particle group +0x20; clock
        +0x18 = 0; the owner's own healing per tick +0x1c = maximum hit points x 0.01475 x
        (statistic 0 x 0.01): a player's maximum from its record with slot 12 cap 10,
        anyone else's from +0x22c with cap 20."""
        u32 = self.u32
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_HEALING)
        self.call('sound_playOnObject', self.call('res_find', self.S_HEALING_LUMP, self.S_HEALING_SOUND), u32(spell + 0xC), ONE)
        shaft = self.call('pool_new', 0x5C)
        if shaft:
            self.object_ctor('GlowingShaft_ctor', shaft, self.vec(u32(spell + 0xC) + 0x10), 0x5A, 0xFA, 200, 100)
        self.w32(spell + 0x20, self.call('particleGroup_create'))
        owner = u32(spell + 0xC)
        self.w32(spell + 0x18, 0)
        if u32(owner + 0xC) & 0x40:
            percent = self.stat_for(u32(spell + 8), 0, self.s8(spell), owner, 10)
            most = u32(self.record(owner) + 0xB0)
        else:
            percent = self.stat_for(u32(spell + 8), 0, self.s8(spell), owner, 0x14)
            most = u32(u32(spell + 0xC) + 0x22C)
        self.w32(spell + 0x1C, C.mul(C.mul(most, self.F_HEAL_RATE), C.mul(C.from_int(percent), F_0_01)))

    def _heal_share(self, spell, most):
        """What a recipient other than the owner gets per tick: its own maximum x 0.01475
        x (statistic 2 x 0.01), statistic 2 through slot 12 with the owner and cap 20."""
        percent = self.stat_for(self.u32(spell + 8), 2, self.s8(spell), self.u32(spell + 0xC), 0x14)
        return C.mul(C.mul(most, self.F_HEAL_RATE), C.mul(C.from_int(percent), F_0_01))

    def healing_run(self, spell, pos=0, facing=0):
        """SpellHealing_run 0x2e90b8, slot 2.

        reach = statistic 1 x 12 (slot 12 with the owner, cap 20), an integer.
        Owner without the player flag, a living creature (flags & 0x28 == 0x20): every
        object of the box query round the owner (cube of the reach) that is the owner or
        that the owner's slot 21 accepts, within the reach in the plane, has its hit
        points +0x228 raised - the owner by +0x1c, others by their share - with no upper
        limit, and is tinted during the first 0.13 s.
        Player owner: the slots of g_alivePlayers (the per-machine list, FINDINGS G19), in
        list order, whose object is within the reach in 3-D (in PvP mode A only those the
        owner's slot 22 accepts): hit points rise in the RECORD, only while hit points + 1
        <= maximum; tint as above.
        Then, reach >= 1: level - (first level of statistic 1) + 5 ring particles, each
        with ONE OWN DRAW for its angle, placed round the "object or prediction copy" of
        the owner and kept only where the terrain is within 72 of that object's height.
        Clock += 1/60; above 1.1299 the spell ends itself (no null test)."""
        u32, w32 = self.u32, self.w32
        skill = u32(spell + 8)
        reach = self.stat_for(skill, 1, self.s8(spell), u32(spell + 0xC), 0x14) * 0xC
        reach2 = C.from_int(s32(reach * reach))
        owner = u32(spell + 0xC)
        early = lambda: C.lt(u32(spell + 0x18), 0x3E050EF8)

        def tint(obj):
            for off, value in self.HEAL_TINT:
                self.w16(obj + off, value)
        if not u32(owner + 0xC) & 0x40:
            if u32(owner + 0xC) & 0x28 == 0x20:
                edge = C.from_int(reach)
                x, y, z = self.vec(owner + 0x10)
                low = (C.sub(x, edge), C.sub(y, edge), C.sub(z, edge))
                high = (C.add(x, edge), C.add(y, edge), C.add(z, edge))
                for other in self.call('world_collectObjectsInBox', low, high, 0x80) or ():
                    owner = u32(spell + 0xC)
                    if other != owner and not self.vcall(owner, 21, other):
                        continue
                    owner = u32(spell + 0xC)
                    dy = C.sub(u32(owner + 0x14), u32(other + 0x14))
                    dx = C.sub(u32(owner + 0x10), u32(other + 0x10))
                    if not C.le(C.add(C.mul(dx, dx), C.mul(dy, dy)), reach2):
                        continue
                    add = u32(spell + 0x1C) if other == owner else self._heal_share(spell, u32(other + 0x22C))
                    w32(other + 0x228, C.add(u32(other + 0x228), add))
                    if early():
                        tint(other)
        else:
            chosen = []
            for i in range(max(self.s32(G_ALIVE_COUNT), 0)):
                slot = self.s32(G_ALIVE_LIST + 4 * i)
                obj = u32((G_PLAYERS + slot * REC_SIZE + REC_OBJ) & M32)
                if u32(G_PVP_MODE_A) and not self.vcall(u32(spell + 0xC), 22, obj):
                    continue
                owner = u32(spell + 0xC)
                obj = u32((G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + REC_OBJ) & M32)
                dx = C.sub(u32(owner + 0x10), u32(obj + 0x10))
                dy = C.sub(u32(owner + 0x14), u32(obj + 0x14))
                dz = C.sub(u32(owner + 0x18), u32(obj + 0x18))
                if C.le(C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)), reach2):
                    chosen.append(self.s32(G_ALIVE_LIST + 4 * i))
            for slot in chosen:
                rec = (G_PLAYERS + slot * REC_SIZE) & M32
                if C.le(C.add(u32(rec + 0xAC), ONE), u32(rec + 0xB0)):
                    if u32(rec + REC_OBJ) == u32(spell + 0xC):
                        w32(rec + 0xAC, C.add(u32(rec + 0xAC), u32(spell + 0x1C)))
                    else:
                        w32(rec + 0xAC, C.add(u32(rec + 0xAC), self._heal_share(spell, u32(rec + 0xB0))))
                if early():
                    tint(u32(rec + REC_OBJ))
        if reach >= 1:
            level, first = self.s8(spell), self.s16(u32(spell + 8) + 0x10)
            anchor = self.call('net_objOrGhost', u32(spell + 0xC))
            self.call('particleGroup_begin', u32(spell + 0x20))
            matrix = C.mat34_set_pos_rot_z(list(self.vec(anchor + 0x10)), s16(self.s32(G_SIM_FRAME) * 0x5F))
            self.call('particleGroup_setMatrix', u32(spell + 0x20), tuple(matrix))
            for _ in range(max(level - first + 5, 0)):
                angle = s16(self.spell_rand(spell))
                ring = [C.mul(C.cos16(angle), C.from_int(reach)), C.mul(C.sin16(angle), C.from_int(reach)), ZERO]
                world = C.mat34_transform_point(matrix, ring)
                height = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(anchor + 0x18))
                if C.lt(0x42900000, height) or C.lt(height, 0xC2900000):
                    continue
                self.call('particle_spawn', self.PDEF_HEALING_RING, (ring[0], ring[1], height), (0, 0, ONE), ZERO)
            self.call('particleGroup_end', u32(spell + 0x20))
        clock = C.add(u32(spell + 0x18), DT)
        w32(spell + 0x18, clock)
        if C.lt(0x3F90A1DF, clock):
            self.spell_call(spell, 1, 3)


    # =====================================================================================
    # 68 resurrect: docs/spec/skills-35-68.md section 68
    # =====================================================================================
    VT_SPELL_RESURRECT = 0x51BE00
    G_DEAD_COUNTDOWN = 0x4F84A8                 # s16 per player slot: 240 at a death, counted down while dead
    S_RESURRECT_PVP, S_RESURRECT_NOBODY = 0x552978, 0x552988
    S_RESURRECT_LUMP, S_RESURRECT_SOUND = 0x5529E8, 0x5529F0
    PDEF_RESURRECT_CASTER, PDEF_RESURRECT_TARGET = 0x8E8508, 0x8E8558
    D_RESURRECT_RATE = 0x3FC645BAE0000000       # the double at 0x552a08: animation seconds per revive

    def resurrect_can_use(self, skill, caster):
        """SkillResurrect_canUse 0x312168 (skill, caster) -> 1 or 0.  A player in PvP mode
        A: a 90-frame message, 0.  With two or more players a target must exist
        (findTarget), else a player gets a 180-frame message and anyone gets 0.  Then 1
        exactly when the caster carries no SpellResurrect already."""
        u32 = self.u32
        if u32(G_PVP_MODE_A) and u32(caster + 0xC) & 0x40:
            self.call('hud_showMessage', self.call('text_lookup', self.S_RESURRECT_PVP), 0x5A, u32(caster + 0x3C8), 0)
            return 0
        if self.s32(G_NUM_PLAYERS) >= 2 and s32(self.resurrect_find_target(skill, caster)) == -1:
            if u32(caster + 0xC) & 0x40:
                self.call('hud_showMessage', self.call('text_lookup', self.S_RESURRECT_NOBODY), 0xB4, u32(caster + 0x3C8), 0)
            return 0
        return 0 if self.call('creature_findSpellByType', caster, self.call('SpellResurrect_typeinfo')) else 1

    def resurrect_find_target(self, skill, caster):
        """SkillResurrect_findTarget 0x312240 (skill, caster) -> player slot or -1.

        Of the slots below g_numPlayers whose dead countdown is below 61 (dead for 180
        counted frames or more) and that have an object: forward distance along the
        caster's facing strictly between -12 and 136, sideways offset (to one side:
        facing + 0x4000) below 56, not already being raised; the smallest forward distance
        wins (strict, so the lower slot on a tie)."""
        u32 = self.u32
        facing = self.s16(caster + 0x38)
        ahead = (C.cos16(facing), C.sin16(facing), ZERO)
        side = (C.cos16(facing + 0x4000), C.sin16(facing + 0x4000), ZERO)
        best, best_d = -1, 0x4B18967F
        slot = 0
        while slot < self.s32(G_NUM_PLAYERS):
            if self.s16(self.G_DEAD_COUNTDOWN + 2 * slot) < 0x3D:
                obj = u32(G_PLAYERS + slot * REC_SIZE + REC_OBJ)
                if obj:
                    d = C.vec3_dot_delta(self.vec(caster + 0x10), ahead, self.vec(obj + 0x10))
                    if C.lt(0xC1400000, d) and C.lt(d, 0x43080000):
                        obj = u32(G_PLAYERS + slot * REC_SIZE + REC_OBJ)
                        across = C.vec3_dot_delta(self.vec(caster + 0x10), side, self.vec(obj + 0x10))
                        if C.lt(across, 0x42600000) and C.lt(d, best_d) and not self.resurrect_is_being_raised(skill, slot):
                            best, best_d = slot, d
            slot += 1
        return best

    def resurrect_is_being_raised(self, skill, slot):
        """SkillResurrect_isSlotBeingRaised 0x31270c (skill, slot) -> 1 when a player of
        g_alivePlayers carries a SpellResurrect whose target (+0x18, a plain pointer) has
        that slot at +0x3c8."""
        i = 0
        while i < self.s32(G_ALIVE_COUNT):
            info = self.call('SpellResurrect_typeinfo')
            obj = self.u32((G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + REC_OBJ) & M32)
            i += 1
            spell = self.call('creature_findSpellByType', obj, info)
            if spell and self.s32(self.u32(spell + 0x18) + 0x3C8) == s32(slot):
                return 1
        return 0

    def resurrect_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillResurrect_cast 0x3123e4 -> the SpellResurrect or 0.  One player in the
        game: the spell goes on the caster (a self-revive in waiting).  More: the target
        of findTarget, or nothing without one.  The level goes through slot 14 (level,
        1); pool_new(0x70)."""
        level = self.skill_call(skill, 14, level, 1)
        if self.s32(G_NUM_PLAYERS) < 2:
            target = caster
            spell = self.call('pool_new', 0x70)
            if not spell:
                return 0
        else:
            slot = s32(self.resurrect_find_target(skill, caster))
            if slot == -1:
                return 0
            spell = self.call('pool_new', 0x70)
            if not spell:
                return 0
            target = self.u32((G_PLAYERS + slot * REC_SIZE + REC_OBJ) & M32)
        self.resurrect_spell_ctor(spell, level, target, skill, caster)
        return spell

    def resurrect_spell_ctor(self, spell, level, target, skill, caster):
        """SpellResurrect_ctor 0x3127b4 (spell, level, target, skill, caster).

        Spell base with the TARGET as owner (ONE SHARED DRAW); the light +0x24 one unit
        above the target, linked; target pointer +0x18 (plain); time left +0x60 =
        (float) statistic 2 in a one-player game, statistic 0 otherwise (slot 10: tier 1);
        caster +0x68; revived flag +0x1c = 0; the target's animation speed +0x64 =
        (float)((1.0 / time) x 0.1740...), computed in double precision; +0x20 = +0x6c =
        0; the sound at the target.  With more than one player: a player caster's record
        +0x4c20 (movement speed factor) = 0.5, and the revive animation (class definition
        +0x44) is started on the target, flags 3, blend 0.1."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.w8(spell, level)
        x, y, z = self.vec(target + 0x10)
        w32(spell + 0x14, VT_SPELL)
        w32(spell + 8, skill)
        w32(spell + 0xC, target)
        w32(spell + 4, 0)
        w32(spell + 0x10, self.draw())
        w32(spell + 0x14, self.VT_SPELL_RESURRECT)
        self.w8(spell + 0x2D, 0)
        self.wvec(spell + 0x54, (C.add(x, ZERO), y, C.add(z, ONE)))
        for off in (0x48, 0x40):
            w32(spell + off, F_12)
            w32(spell + off + 4, 0x3BE38E38)
        w32(spell + 0x50, 0)
        for off in (0x36, 0x2E):
            w16(spell + off, 0x73)
            w16(spell + off + 2, 0x56)
        w16(spell + 0x32, 0x77)
        w16(spell + 0x34, 0)
        w16(spell + 0x3A, 0x77)
        w16(spell + 0x3C, 0)
        self.w8(spell + 0x2C, 0)
        self.call('light_link', spell + 0x24)
        w32(spell + 0x18, u32(spell + 0xC))
        seconds = self.stat(u32(spell + 8), 2 if self.s32(G_NUM_PLAYERS) == 1 else 0, level)
        w32(spell + 0x60, C.from_int(seconds))
        w32(spell + 0x68, caster)
        w32(spell + 0x1C, 0)
        rate = C.dmul(C.ddiv(0x3FF0000000000000, C.f2d(u32(spell + 0x60))), self.D_RESURRECT_RATE)
        w32(spell + 0x20, 0)
        w32(spell + 0x64, C.d2f(rate))
        w32(spell + 0x6C, 0)
        self.call('sound_playAtPos', self.call('res_find', self.S_RESURRECT_LUMP, self.S_RESURRECT_SOUND),
                  self.vec(u32(spell + 0xC) + 0x10), ONE)
        if self.s32(G_NUM_PLAYERS) != 1:
            caster = u32(spell + 0x68)
            if u32(caster + 0xC) & 0x40:
                w32(self.record(caster) + 0x4C20, HALF)
            target = u32(spell + 0x18)
            self.call('anim_start', target + 0x114, u32(u32(target + 0x24) + 0x44), 3, F_0_1)

    RESURRECT_TINT = ((0x90, 0x62), (0x9A, 0x4B), (0x92, 0x4B), (0x9C, 0x2E), (0x94, 0x2E), (0x9E, 0x2E), (0x96, 0x2E))

    def resurrect_run(self, spell, pos=0, facing=0):
        """SpellResurrect_run 0x312b30, slot 2 - run by the creature the spell is attached
        to, which is the CASTER (Player_castSkill attaches what cast returns to the
        caster) while the spell's owner field is the target.

        The light pulses with the frame counter; in a one-player game it follows the
        owner.  The target is tinted.  With two or more players (g_numPlayers is read
        again here): the caster is tinted; two particle streams (presentation generator);
        once the time left is below 0.25 s, once: player_respawn(target's slot, its
        position and facing, -1, -1), the idle animation, the arena life counter, target
        = the slot's NEW object, and the slot's hit points = maximum x statistic 1 x
        0.01; then every tick Player_animStep(target; the speed +0x64) and the
        copy-rebuild byte 0x402797 = 1 ON EVERY MACHINE.
        Time left -= 1/60; below zero the spell ends itself."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        frame = s32(self.s32(G_SIM_FRAME) * 0xF3C)
        low = frame - (((frame + 0xFFFF) if frame < 0 else frame) >> 16 << 16)
        radius = C.add(C.mul(C.sin16(low), 0x40E00000), 0x42C20000)
        w32(spell + 0x40, radius)
        w32(spell + 0x48, radius)
        inverse = C.div(ONE, C.mul(radius, radius))
        w32(spell + 0x4C, inverse)
        w32(spell + 0x44, inverse)
        if self.s32(G_NUM_PLAYERS) == 1:
            owner = u32(spell + 0xC)
            x, y, z = self.vec(owner + 0x10)
            self.wvec(spell + 0x54, (C.add(x, ZERO), y, C.add(z, 0x42400000)))
            self.call('light_relink', spell + 0x24)
        target = u32(spell + 0x18)
        several = self.s32(G_NUM_PLAYERS) >= 2
        for off, value in self.RESURRECT_TINT:
            w16(target + off, value)
        if several:
            caster = u32(spell + 0x68)
            for off, value in self.RESURRECT_TINT:
                w16(caster + off, value)
            d = [C.sub(u32(target + 0x10 + 4 * i), u32(caster + 0x10 + 4 * i)) for i in range(3)]
            inverse = C.rsqrt(ONE, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])))
            d = tuple(C.mul(c, inverse) for c in d)
            self.call('fx_emitFromModelVerts', caster, 0x12, self.PDEF_RESURRECT_CASTER, d, 0, 0x42240000)
            back = tuple(C.mul(c, 0xC2280000) for c in d)
            self.call('fx_emitFromModelVerts', u32(spell + 0x18), 0x26, self.PDEF_RESURRECT_TARGET, d, back, 0x421C0000)
            if C.lt(u32(spell + 0x60), 0x3E800000) and not u32(spell + 0x1C):
                target = u32(spell + 0x18)
                slot = self.s32(target + 0x3C8)
                self.call('player_respawn', slot, self.vec(target + 0x10), self.s16(target + 0x38), M32, M32)
                self.call('player_resetIdleAnim', slot)
                self.call('arena_addLife', slot)
                w32(spell + 0x18, u32((G_PLAYERS + slot * REC_SIZE + REC_OBJ) & M32))
                percent = C.from_int(self.stat(u32(spell + 8), 1, self.s8(spell)))
                rec = self.record(u32(spell + 0x18))
                w32(spell + 0x1C, 1)
                w32(rec + 0xAC, C.mul(C.mul(u32(rec + 0xB0), percent), F_0_01))
            self.call('Player_animStep', u32(spell + 0x18), u32(spell + 0x64))
            self.w8(G_FORCE_GHOST_REBASE, 1)
        left = C.sub(u32(spell + 0x60), DT)
        w32(spell + 0x60, left)
        if C.lt(left, ZERO):
            self.spell_end(spell)

    def resurrect_on_owner_death(self, spell):
        """SpellResurrect_onOwnerDeath 0x3130f4 (spell) -> float hit points, called by
        Player_processDamage in a one-player game when the player carrying the spell
        dies.  ONE SHARED DRAW d; statistic 3 (slot 10) is the chance in percent.
        d % 100 < chance: a StrongStancePhantom (pool_new(0x3d8); a creature: one more
        shared draw inside its constructor) and a LightEffect 36 above the CASTER (ONE
        SHARED DRAW unless the pool has no block); returns half of the target's maximum
        hit points.  Otherwise failed flag +0x20 = 1, +0x6c = the frame, the light is
        unlinked; returns 0.0."""
        u32 = self.u32
        draw = self.draw()
        chance = self.stat(u32(spell + 8), 3, self.s8(spell))
        if draw % 100 < chance:
            phantom = self.call('pool_new', 0x3D8)
            if phantom:
                target = u32(spell + 0x18)
                self.object_ctor('StrongStancePhantom_ctor', phantom, target, u32(u32(target + 0x24) + 8), 0, 1)
            light = self.call('pool_new', 0xBC)
            if light:
                caster = u32(spell + 0x68)
                spot = (C.add(u32(caster + 0x10), ZERO), u32(caster + 0x14), C.add(u32(caster + 0x18), 0x42100000))
                self.light_effect(light, spot, 0x43090000, 0x42CC0000, 0x42B80000, 0x42F00000, 0x43340000, ZERO, 0x40800000,
                                  rest=(0xC2C00000, 0, 0, 0, 0))
            return C.mul(u32(self.record(u32(spell + 0x18)) + 0xB0), HALF)
        self.w32(spell + 0x20, 1)
        self.w32(spell + 0x6C, u32(G_SIM_FRAME))
        self.call('light_unlink', spell + 0x24)
        return ZERO


    # =====================================================================================
    # 49 bash: docs/spec/skills-35-68.md section 49
    # =====================================================================================
    VT_SPELL_BASH = 0x5195B0
    S_BASH_WARN, S_BASH_LUMP, S_BASH_SOUND, S_BASH_CLIP = 0x54F988, 0x54F998, 0x54F9A0, 0x54F9D8
    PDEF_BASH_WINDUP = 0x8E5B40

    def bash_can_use(self, skill, caster):
        """SkillBash_canUse 0x2de334: 1 for a caster without the player flag; a player
        needs record +0x43fc non-zero and a weapon class (+0x4a86) other than 4, else the
        warning for 180 frames and 0."""
        if not self.u32(caster + 0xC) & 0x40:
            return 1
        rec = self.record(caster)
        if self.u32(rec + 0x43FC) and self.s8(rec + 0x4A86) != 4:
            return 1
        self.call('hud_showMessage', self.call('text_lookup', self.S_BASH_WARN), 0xB4, self.u32(caster + 0x3C8), 0)
        return 0

    def bash_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillBash_cast 0x2de3bc -> the SpellBash or 0: slot 14 (level, 19), the sound
        on the caster (also when the pool then has no block), pool_new(0x28)."""
        level = self.skill_call(skill, 14, level, 0x13)
        self.call('sound_playOnObject', self.call('res_find', self.S_BASH_LUMP, self.S_BASH_SOUND), caster, ONE)
        spell = self.call('pool_new', 0x28)
        if spell:
            self.bash_spell_ctor(spell, level, caster, skill)
        return spell

    def bash_spell_ctor(self, spell, level, owner, skill):
        """SpellBash_ctor 0x2de640 (spell, level, owner, skill).

        Spell base (ONE SHARED DRAW); the owner's action state +0x58c = 6 WHATEVER the
        owner is; the bash clip of the owner's class lump is started (flags 0x812, blend
        0.1 in and out) and event slot 1 of that clip - a header shared by every object
        of the class - is set to mask 2 at 0.592 s; hit-done +0x18, struck +0x1c, +0x20
        = 0.  Target +0x24 (a PLAIN pointer): from world_collectObjectsInArc(owner
        position, facing; 100, 90 degrees, 0) - the head when it lacks object flag
        0x1000000; otherwise, when any later entry lacks it, STILL THE HEAD (the loop
        stores the head's object, not the entry it found)."""
        u32, w32 = self.u32, self.w32
        self.w8(spell, level)
        w32(spell + 8, skill)
        w32(spell + 0x14, VT_SPELL)
        w32(spell + 4, 0)
        w32(spell + 0xC, owner)
        w32(spell + 0x10, self.draw())
        lump = u32(u32(owner + 0x24))
        w32(owner + 0x58C, 6)
        w32(spell + 0x14, self.VT_SPELL_BASH)
        clip = self.call('res_find', lump, self.S_BASH_CLIP)
        self.call('anim_startBlendInOut', owner + 0x114, clip, 0x812, F_0_1, F_0_1)
        self.w8(clip + 0x20, 2)
        w32(clip + 0x1C, 0x3F178D60)
        w32(spell + 0x20, 0)
        w32(spell + 0x1C, 0)
        w32(spell + 0x18, 0)
        w32(spell + 0x24, 0)
        head = self.query_list('world_collectObjectsInArc', self.vec(owner + 0x10), self.s16(owner + 0x38), 0,
                               0x42C80000, 0x42B40000, u32(spell + 0x20))
        node = u32(head)
        if node:
            first = u32(node + 0xC)
            if not u32(first + 0xC) & 0x1000000:
                w32(spell + 0x24, first)
            else:
                node = u32(node)
                while node:
                    if not u32(u32(node + 0xC) + 0xC) & 0x1000000:
                        w32(spell + 0x24, first)
                        break
                    node = u32(node)
        self.handle_clear(head)

    def bash_windup_fx(self, spell, unused=3):
        """SpellBash_windupFx 0x2dedec (spell): 203 particles on sample points of the
        "object or prediction copy" of the owner; FOUR OR MORE OWN (spell) DRAWS each.
        Which object's points are used is per machine; the number of draws is not."""
        anchor = self.call('net_objOrGhost', self.u32(spell + 0xC))
        count = s32(self.call('model_getSamplePointCount', self.u32(anchor + 0x544)))
        for _ in range(0xCB):
            draw = self.spell_rand(spell)
            point = self._sample_point(anchor, self.u32(anchor + 0x544), draw, count)
            velocity = tuple(C.mul(c, 0x41500000) for c in self.spell_ball(spell))
            self.call('particle_spawn', self.PDEF_BASH_WINDUP, point, velocity, ZERO)

    def _bash_range(self, spell):
        low, high = self.stat_range(self.u32(spell + 8), 0, self.s8(spell), 0, 0x3E4CCCCC)
        return C.from_int(low), C.from_int(high)

    def bash_run(self, spell, pos=0, facing=0):
        """SpellBash_run 0x2de7dc, slot 2.

          1. Player_animStep(owner; 1.0); Player_move(owner, mode 3, the slot's pad, no
             external velocity); with a target the owner's slot 26 turns it toward the
             target's position (mode 0).  Event bit 2 sets struck +0x1c.
          2. Until the hit is done (+0x18): before the strike the wind-up particles;
             on the strike: up to statistic 3 enemies of world_collectObjectsInArc(attach
             point 1, facing; radius 41, any angle) in list order - not flag 0x1000000,
             accepted by the owner's slot 20 - each take damage_apply(statistic 0 -/+ 20
             % from slot 8 without randomising, attack 100000, flags 0x40 with the knock
             bit by level: below 6 0x40000, 6-15 0x80000, 16 and above 0x200000, no
             descriptor, no-crit 1); then, if it still has hit points, ONE SHARED DRAW d:
             stunned for statistic 2 x 60 frames (slot 30, flash 1) unless statistic 1 <
             d % 100 + 1; a dead or unstunned victim is tinted instead; the first victim
             gets a LightEffect (ONE SHARED DRAW unless the pool has no block).  When
             nobody was hit: the first object of world_collectInSphere(owner, 41) -
             added to the SAME list - that has none of the flags 0x1000060 (not a
             creature, not a player) is damaged the same way with no-crit 0.
          3. Animation status bit 0x10 clear, or owner +0x450 set: owner state = 2 and
             the spell ends itself.  Else net_isLocalSlot(owner's slot): the copy-rebuild
             countdown 0x402797 = 60."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        owner = u32(spell + 0xC)
        head = self.alloca(4)
        self.mem.poke(head, 4, 0)
        events = self.call('Player_animStep', owner, ONE)
        self.call('Player_move', owner, 3, (G_PADS + self.s32(owner + 0x3C8) * 0x58) & M32, 0)
        target = u32(spell + 0x24)
        if target:
            self.vcall(owner, 26, 0, self.vec(target + 0x10))
        if events & 2:
            w32(spell + 0x1C, 1)
        if not u32(spell + 0x18):
            if not u32(spell + 0x1C):
                self.bash_windup_fx(spell, 3)
            else:
                skill, level = u32(spell + 8), self.s8(spell)
                most = self.stat(skill, 3, level)
                chance = self.stat(u32(spell + 8), 1, level)
                frames = self.stat(u32(spell + 8), 2, level) * 0x3C
                flags = 0x200000 if level > 15 else 0x40000 if level < 6 else 0x80000
                hand = self.call('model_getAttachPoint', u32(owner + 0x544), self.vec(owner + 0x10), self.s16(owner + 0x38),
                                 owner + 0x114, 1, 0, ONE)
                self.query_into(head, 'world_collectObjectsInArc', tuple(hand), self.s16(owner + 0x38), 0,
                                0x42240000, 0xBF800000, ZERO)
                hits = 0
                node = u32(head)
                if node and most >= 1:
                    while True:
                        other = u32(node + 0xC)
                        if not u32(other + 0xC) & 0x1000000 and self.vcall(owner, 20, other):
                            low, high = self._bash_range(spell)
                            self.call('damage_apply', other, owner, 100000, 0, 0, flags | 0x40, 0, 1, low, high)
                            if C.lt(ZERO, u32(other + 0x228)) and not chance < self.draw() % 100 + 1:
                                self.vcall(other, 30, frames, 1)
                            else:
                                for off, value in ((0x92, 100), (0x96, 0x40), (0x98, 100), (0x90, 100), (0x9A, 100), (0x9C, 0x40),
                                                   (0x94, 0x40)):
                                    w16(other + off, value)
                            if not u32(spell + 0x18):
                                light = self.call('pool_new', 0xBC)
                                if light:
                                    spot = (C.add(u32(other + 0x10), ZERO), u32(other + 0x14), C.add(u32(other + 0x18), 0x42800000))
                                    self.light_effect(light, spot, 0x43210000, 0x430A0000, 0x42800000, 0x43340000, 0x42700000,
                                                      HALF, HALF)
                            hits += 1
                            w32(spell + 0x18, 1)
                        node = u32(node)
                        if not node or most <= hits:
                            break
                if not u32(spell + 0x18):
                    self.query_into(head, 'world_collectInSphere', self.vec(owner + 0x10), self.s16(owner + 0x38), 0x42240000)
                    node = u32(head)
                    while node and u32(u32(node + 0xC) + 0xC) & 0x1000060:
                        node = u32(node)
                    if node:
                        low, high = self._bash_range(spell)
                        self.call('damage_apply', u32(node + 0xC), owner, 100000, 0, 0, flags | 0x40, 0, 0, low, high)
                        w32(spell + 0x18, 1)
                self._bash_done(spell, head)
        if not self.u16(owner + 0x11A) & 0x10 or u32(owner + 0x450):
            w32(owner + 0x58C, 2)
            self.spell_end(spell)
        elif self.call('net_isLocalSlot', u32(owner + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 0x3C)
        self.handle_clear(head)

    def _bash_done(self, spell, head):
        """0x2ded38: the hit is done whether or not anything was struck - except on the
        path where the sphere query found objects but none eligible, which jumps past the
        store in the original only to land on the same store."""
        self.w32(spell + 0x18, 1)


    # =====================================================================================
    # 53 criticalhit (and 33, 81): docs/spec/skills-35-68.md section 53
    # =====================================================================================
    VT_SPELL_CRITICALHIT = 0x519C28
    PDEF_CRIT_RING = 0x8E5FA0

    def criticalhit_can_use(self, skill, caster):
        """SkillCriticalHit_canUse 0x2e7224: 1 exactly when the caster carries no
        SpellCriticalHit."""
        return 0 if self.call('creature_findSpellByType', caster, self.call('SpellCriticalHit_typeinfo')) else 1

    def criticalhit_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillCriticalHit_cast 0x2e74b0 -> the SpellCriticalHit or 0 (pool_new(0x5c))."""
        spell = self.call('pool_new', 0x5C)
        if spell:
            self.criticalhit_spell_ctor(spell, level, caster, skill)
        return spell

    def criticalhit_spell_ctor(self, spell, level, owner, skill):
        """SpellCriticalHit_ctor 0x2e7988: Spell base (ONE SHARED DRAW); a light at the
        owner (+0x1c, radius 120), linked; time left +0x18 = (float) statistic 2 seconds
        (slot 10); a particle group at +0x58."""
        w32, w16 = self.w32, self.w16
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_CRITICALHIT)
        self.w8(spell + 0x25, 0)
        self.wvec(spell + 0x4C, self.vec(owner + 0x10))
        for off in (0x40, 0x38):
            w32(spell + off, 0x42F00000)
            w32(spell + off + 4, 0x3891A2B3)
        for off in (0x32, 0x28, 0x2A, 0x30):
            w16(spell + off, 0x40)
        w16(spell + 0x2E, 0xD7)
        w16(spell + 0x26, 0xD7)
        w32(spell + 0x48, 0)
        w16(spell + 0x2C, 0)
        w16(spell + 0x34, 0)
        self.w8(spell + 0x24, 0)
        self.call('light_link', spell + 0x1C)
        w32(spell + 0x18, C.from_int(self.stat(self.u32(spell + 8), 2, self.s8(spell))))
        w32(spell + 0x58, self.call('particleGroup_create'))

    def criticalhit_set_tint(self, spell, creature):
        """SpellCriticalHit_setTint 0x2e7f58 (spell, creature)."""
        for off, value in ((0x90, 0x44), (0x96, 0x0F), (0x92, 0x0E), (0x94, 0x18)):
            self.w16(creature + off, value)

    def criticalhit_run(self, spell, pos=0, facing=0):
        """SpellCriticalHit_run 0x2e7acc, slot 2.

        Time left -= 1/60; below zero the spell ends itself.  Else the owner is tinted;
        during the first two seconds the light follows the owner (fading in the second
        one), after that it is unlinked - every tick; reach = statistic 1 x 12; when
        positive, level - b + 14 ring particles (b = 1 for id 53, 10 for id 33, 5 for id
        81), ONE OWN DRAW each, round the "object or prediction copy" of the owner; then
        every other player of g_alivePlayers within the reach in the plane (in PvP mode A
        only those the owner's slot 22 accepts) is tinted.  The aura itself is not applied
        here: the damage function asks critBonusFor."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        left = C.sub(u32(spell + 0x18), DT)
        w32(spell + 0x18, left)
        if C.lt(left, ZERO):
            return self.spell_end(spell)
        self.criticalhit_set_tint(spell, u32(spell + 0xC))
        skill = u32(spell + 8)
        age = C.sub(C.from_int(self.stat(skill, 2, self.s8(spell))), u32(spell + 0x18))
        if C.le(age, F_2):
            owner = u32(spell + 0xC)
            x, y, z = self.vec(owner + 0x10)
            self.wvec(spell + 0x4C, (C.add(x, ZERO), y, C.add(z, 0x42700000)))
            self.call('light_relink', spell + 0x1C)
            if C.lt(ONE, age):
                dim = C.to_int(C.mul(C.sub(F_2, age), 0x42800000))
                bright = C.to_int(C.mul(C.sub(F_2, age), 0x43570000))
                w16(spell + 0x2A, dim)
                w16(spell + 0x26, bright)
                w16(spell + 0x2E, bright)
                for off in (0x30, 0x28, 0x32):
                    w16(spell + off, dim)
        else:
            self.call('light_unlink', spell + 0x1C)
        skill = u32(spell + 8)
        base = {0x35: 1, 0x21: 10, 0x51: 5}.get(self.s32(skill + 0x64), 1)
        level = self.s8(spell)
        reach = self.stat(skill, 1, level) * 0xC
        anchor = self.call('net_objOrGhost', u32(spell + 0xC))
        if reach > 0:
            self.call('particleGroup_begin', u32(spell + 0x58))
            matrix = C.mat34_set_pos_rot_z(list(self.vec(anchor + 0x10)), s16(self.s32(G_SIM_FRAME) * 0x76))
            self.call('particleGroup_setMatrix', u32(spell + 0x58), tuple(matrix))
            for _ in range(max(level - base + 0xE, 0)):
                angle = s16(self.spell_rand(spell))
                ring = [C.mul(C.cos16(angle), C.from_int(reach)), C.mul(C.sin16(angle), C.from_int(reach)), ZERO]
                world = C.mat34_transform_point(matrix, ring)
                height = C.sub(self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world)), u32(anchor + 0x18))
                if C.lt(0x42900000, height) or C.lt(height, 0xC2900000):
                    continue
                self.call('particle_spawn', self.PDEF_CRIT_RING, (ring[0], ring[1], height), (0, 0, ONE), ZERO)
            self.call('particleGroup_end', u32(spell + 0x58))
        i = 0
        while i < self.s32(G_ALIVE_COUNT):
            owner = u32(spell + 0xC)
            obj = u32((G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + REC_OBJ) & M32)
            i += 1
            if obj == owner:
                continue
            if u32(G_PVP_MODE_A) and not self.vcall(owner, 22, obj):
                continue
            owner = u32(spell + 0xC)
            dy = C.sub(u32(owner + 0x14), u32(obj + 0x14))
            dx = C.sub(u32(owner + 0x10), u32(obj + 0x10))
            if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.from_int(s32(reach * reach))):
                self.criticalhit_set_tint(spell, obj)

    def criticalhit_bonus_for(self, skill, attacker, own_rank):
        """SkillCriticalHit_critBonusFor 0x2e76c4 (skill, attacker, own rank) -> float:
        what damage_apply adds to an attacking player's critical-hit chance.

        With a rank of its own and a SpellCriticalHit on the attacker: that rank.
        Otherwise the slots of g_alivePlayers (FINDINGS G19), in list order, other than
        the attacker's: within 1000 of the attacker in 3-D, in PvP mode A accepted by
        THAT player's slot 22, carrying a SpellCriticalHit, with r = the largest of its
        ranks in skills 53, 81 and 33 non-zero, and within statistic 1 (r) x 12 of the
        attacker in the plane - the first such player decides: rank = r.  None: rank 0.
        Result: 0.0 for rank 0 (after slot 14), else statistic 0 (rank) x 0.01."""
        u32 = self.u32
        rank = s32(own_rank)
        found = bool(rank) and bool(self.call('creature_findSpellByType', attacker, self.call('SpellCriticalHit_typeinfo')))
        if not found:
            rank = 0
            i = 0
            while i < self.s32(G_ALIVE_COUNT):
                cell = G_ALIVE_LIST + 4 * i
                i += 1
                if self.s32(cell) == self.s32(attacker + 0x3C8):
                    continue
                obj = u32((G_PLAYERS + self.s32(cell) * REC_SIZE + REC_OBJ) & M32)
                d = [C.sub(u32(obj + 0x10 + 4 * k), u32(attacker + 0x10 + 4 * k)) for k in range(3)]
                if not C.lt(C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2])), 0x49742400):
                    continue
                if u32(G_PVP_MODE_A) and not self.vcall(obj, 22, attacker):
                    continue
                info = self.call('SpellCriticalHit_typeinfo')
                if not self.call('creature_findSpellByType', u32((G_PLAYERS + self.s32(cell) * REC_SIZE + REC_OBJ) & M32), info):
                    continue
                best = s32(self.call('player_getSkillRank', self.s32(cell), 0x35))
                best = max(best, s32(self.call('player_getSkillRank', self.s32(cell), 0x51)))
                best = max(best, s32(self.call('player_getSkillRank', self.s32(cell), 0x21)))
                if not best:
                    continue
                reach = C.from_int(s32(self.stat(skill, 1, best) * 0xC))
                obj = u32((G_PLAYERS + self.s32(cell) * REC_SIZE + REC_OBJ) & M32)
                dy = C.sub(u32(obj + 0x14), u32(attacker + 0x14))
                dx = C.sub(u32(obj + 0x10), u32(attacker + 0x10))
                if not C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(reach, reach)):
                    continue
                if best > 0:
                    rank = best
                break
        level = s32(self.skill_call(skill, 14, rank, 0x14))
        if not level:
            return ZERO
        return C.mul(C.from_int(self.stat(skill, 0, level)), F_0_01)


# =========================================================================================
# Registration helpers
# =========================================================================================
def _register(sid, name, functions, tables=()):
    """Add a skill's functions: {name: (start, end, kind, method)} with kind 'skill',
    'spell', 'object' (virtual bodies, resolved through the class tables) or '' (a plain
    function)."""
    row = SKILLS.setdefault(sid, {'name': name, 'functions': []})
    for fname, (start, end, kind, method) in functions.items():
        FUNCTIONS[fname] = (start, end)
        row['functions'].append(fname)
        if kind == 'skill':
            SKILL_BODIES[start] = method
        elif kind == 'spell':
            SPELL_BODIES[start] = method
        elif kind == 'object':
            OBJECT_BODIES[start] = method
    CLASS_TABLES.extend(tables)


# Skill slot 5 (mana cost) of every id of the range that overrides it:
# id -> (function, end, slot it forwards to, second argument).  Slot 15 gives
# (float) statistic 4 at the level; the two that forward to slot 14 return 0.0 (LifeTap and
# StrongStance cost nothing).  Slot 14 ignores its second argument, so the numbers below
# have no effect in this build.  Ids 60, 61, 63, 64 keep the base slot (1.0).
MANA_COST = {
    35: (0x2C8C80, 0x2C8CB4, 15, 0x14), 36: (0x2CF42C, 0x2CF460, 15, 1), 37: (0x2C3F28, 0x2C3F5C, 15, 10),
    38: (0x2C7478, 0x2C74AC, 15, 4), 39: (0x2D0120, 0x2D0154, 15, 4), 40: (0x2D0C8C, 0x2D0CC0, 15, 10),
    41: (0x2D1794, 0x2D17C8, 15, 0x14), 42: (0x2D2950, 0x2D2984, 15, 0x12), 43: (0x2D6204, 0x2D6238, 15, 0x14),
    44: (0x2D6F80, 0x2D6FB4, 15, 0x14), 45: (0x2D8A30, 0x2D8A64, 15, 1), 46: (0x2DA130, 0x2DA164, 15, 0x14),
    47: (0x2DAE80, 0x2DAEB4, 15, 9), 48: (0x2DBC78, 0x2DBCAC, 15, 0x14), 49: (0x2DE60C, 0x2DE640, 15, 0x13),
    50: (0x2E0354, 0x2E0388, 15, 0x14), 51: (0x2E0980, 0x2E09B4, 15, 10), 52: (0x2E6894, 0x2E68C8, 15, 0x14),
    53: (0x2E7690, 0x2E76C4, 15, 0x14), 54: (0x2E82C8, 0x2E82FC, 15, 0x14), 55: (0x2E8E94, 0x2E8EC8, 15, 0xE),
    56: (0x2E9AD4, 0x2E9B08, 15, 1), 57: (0x2ED80C, 0x2ED840, 15, 0x14), 58: (0x2EDD44, 0x2EDD78, 15, 0x14),
    59: (0x2F8E40, 0x2F8E78, 14, 1), 62: (0x3084E4, 0x30851C, 14, 0x14), 65: (0x30909C, 0x3090D0, 15, 10),
    66: (0x309CD8, 0x309D0C, 15, 0x14), 67: (0x311604, 0x311638, 15, 0x14), 68: (0x3126D8, 0x31270C, 15, 1),
}
SKILL_NAMES = {35: 'charge', 36: 'darkness', 37: 'shock', 38: 'groundpound', 39: 'convertenemy', 40: 'convertundead',
               41: 'cyclone', 42: 'harmtouch', 43: 'firearrow', 44: 'coldarrow', 45: 'poisonarrow', 46: 'multifire',
               47: 'explodearrow', 48: 'archery', 49: 'bash', 50: 'minorhealing', 51: 'ancestralcall', 52: 'root',
               53: 'criticalhit', 54: 'holyshield', 55: 'healing', 56: 'coneoffrost', 57: 'shockoffire',
               58: 'froststorm', 59: 'lifetap', 60: 'blunt', 61: 'slashing', 62: 'strongstance',
               63: 'naturalresistance', 64: 'stunningstrike', 65: 'giantgrowth', 66: 'planarwind', 67: 'shadowstep',
               68: 'resurrect'}


def _mana_cost_method(slot, n):
    def mana_cost(self, skill, level):
        if slot == 15:
            return self.skill_call(skill, 15, level, n)
        self.skill_call(skill, 14, level, n)
        return ZERO
    mana_cost.__doc__ = 'Skill slot 5: forwards (level, %d) to slot %d%s.' % (n, slot, '' if slot == 15 else '; returns 0.0')
    return mana_cost


for _sid in SKILL_IDS:
    SKILLS[_sid] = {'name': SKILL_NAMES[_sid], 'functions': []}
for _sid, (_start, _end, _slot, _n) in MANA_COST.items():
    setattr(Model, 'mana_cost_%d' % _sid, _mana_cost_method(_slot, _n))
    _register(_sid, SKILL_NAMES[_sid], {'Skill%d_manaCost' % _sid: (_start, _end, 'skill', 'mana_cost_%d' % _sid)})

_register(41, 'cyclone', {
    'SkillCyclone_canUse': (0x2D1484, 0x2D1510, 'skill', 'cyclone_can_use'),
    'SkillCyclone_cast': (0x2D161C, 0x2D16A0, 'skill', 'cyclone_cast'),
    'SpellCyclone_ctor': (0x2D17C8, 0x2D1A94, '', 'cyclone_spell_ctor'),
    'SpellCyclone_run': (0x2D1A94, 0x2D21E0, 'spell', 'cyclone_run'),
    'SpellCyclone_updateFx': (0x2D21E0, 0x2D272C, '', 'cyclone_update_fx'),
}, [(Model.VT_SPELL_CYCLONE, 'Spell', (1,))])

_register(43, 'firearrow', {
    'SkillFireArrow_canUse': (0x2D5FC4, 0x2D603C, 'skill', 'firearrow_can_use'),
    'SkillFireArrow_cast': (0x2D603C, 0x2D6108, 'skill', 'firearrow_cast'),
    'FireArrowProjectile_ctor': (0x2D6238, 0x2D6440, '', 'firearrow_ctor'),
    'FireArrowProjectile_ctor2': (0x2D6440, 0x2D66AC, '', 'firearrow_ctor2'),
    'FireArrowProjectile_run': (0x2D66AC, 0x2D67E8, 'object', 'firearrow_run'),
    'FireArrowProjectile_onHit': (0x2D685C, 0x2D6BB8, 'object', 'firearrow_on_hit'),
    'FireArrowProjectile_end': (0x2D6BB8, 0x2D6C20, '', 'firearrow_end'),
})

_register(44, 'coldarrow', {
    'SkillColdArrow_canUse': (0x2D6D40, 0x2D6DB8, 'skill', 'coldarrow_can_use'),
    'SkillColdArrow_cast': (0x2D6DB8, 0x2D6E84, 'skill', 'coldarrow_cast'),
    'ColdArrowProjectile_ctor': (0x2D6FB4, 0x2D718C, '', 'coldarrow_ctor'),
    'ColdArrowProjectile_ctor2': (0x2D718C, 0x2D73C8, '', 'coldarrow_ctor2'),
    'ColdArrowProjectile_run': (0x2D73C8, 0x2D7980, 'object', 'coldarrow_run'),
    'ColdArrowProjectile_onHit': (0x2D7AAC, 0x2D7ECC, 'object', 'coldarrow_on_hit'),
    'ColdArrowProjectile_end': (0x2D7ECC, 0x2D84CC, '', 'coldarrow_end'),
})
_register(45, 'poisonarrow', {
    'SkillPoisonArrow_canUse': (0x2D877C, 0x2D87F4, 'skill', 'poisonarrow_can_use'),
    'SkillPoisonArrow_cast': (0x2D87F4, 0x2D88C0, 'skill', 'poisonarrow_cast'),
    'PoisonArrowProjectile_ctor': (0x2D8A64, 0x2D8C40, '', 'poisonarrow_ctor'),
    'PoisonArrowProjectile_ctor2': (0x2D8C40, 0x2D8E80, '', 'poisonarrow_ctor2'),
    'PoisonArrowProjectile_run': (0x2D8E80, 0x2D91F8, 'object', 'poisonarrow_run'),
    'PoisonArrowProjectile_onHit': (0x2D932C, 0x2D95C8, 'object', 'poisonarrow_on_hit'),
    'PoisonArrowProjectile_end': (0x2D95C8, 0x2D9764, '', 'poisonarrow_end'),
})
_register(47, 'explodearrow', {
    'SkillExplodeArrow_canUse': (0x2DAC30, 0x2DACA8, 'skill', 'explodearrow_can_use'),
    'SkillExplodeArrow_cast': (0x2DACA8, 0x2DAD68, 'skill', 'explodearrow_cast'),
    'ExplodeArrowProjectile_ctor': (0x2DAEB4, 0x2DAFE0, '', 'explodearrow_ctor'),
    'ExplodeArrowProjectile_ctor2': (0x2DAFE0, 0x2DB17C, '', 'explodearrow_ctor2'),
    'ExplodeArrowProjectile_run': (0x2DB17C, 0x2DB430, 'object', 'explodearrow_run'),
    'ExplodeArrowProjectile_onHit': (0x2DB4F0, 0x2DB50C, 'object', 'explodearrow_on_hit'),
    'ExplodeArrowProjectile_explode': (0x2DB50C, 0x2DBA94, '', 'explodearrow_explode'),
})

_register(46, 'multifire', {
    'SkillMultiFire_canUse': (0x2D9A18, 0x2D9A90, 'skill', 'multifire_can_use'),
    'SkillMultiFire_cast': (0x2D9A90, 0x2DA048, 'skill', 'multifire_cast'),
})

_register(48, 'archery', {'SkillArchery_getStat0Fraction': (0x2DBCAC, 0x2DBD20, '', 'archery_fraction')})
_register(59, 'lifetap', {
    'SkillLifeTap_cast': (0x2F8D54, 0x2F8D7C, 'skill', 'skill_cast_base'),
    'SkillLifeTap_getStat0Fraction': (0x2F8E78, 0x2F8EEC, '', 'lifetap_fraction'),
    'SkillLifeTap_getStat1': (0x2F8EEC, 0x2F8F48, '', 'lifetap_stat1'),
})
_register(62, 'strongstance', {
    'SkillStrongStance_cast': (0x308434, 0x30845C, 'skill', 'skill_cast_base'),
    'SkillStrongStance_getStat0': (0x30851C, 0x308578, '', 'strongstance_stat0'),
    'SkillStrongStance_trigger': (0x308578, 0x3088B8, '', 'strongstance_trigger'),
})
_register(63, 'naturalresistance', {
    'SkillNaturalResistance_getStat0Fraction': (0x308A7C, 0x308AF0, '', 'naturalresistance_fraction'),
})
_register(64, 'stunningstrike', {
    'SkillStunningStrike_getStat0ForTarget': (0x308C10, 0x308CB4, '', 'stunningstrike_stat0_for'),
    'SkillStunningStrike_spawnEffect': (0x308CB4, 0x308E64, '', 'stunningstrike_effect'),
})

_register(42, 'harmtouch', {
    'SkillHarmTouch_canUse': (0x2D2984, 0x2D2A04, 'skill', 'harmtouch_can_use'),
    'SkillHarmTouch_cast': (0x2D2A04, 0x2D2A88, 'skill', 'harmtouch_cast'),
    'SpellHarmTouch_ctor': (0x2D2B5C, 0x2D2C0C, '', 'harmtouch_spell_ctor'),
    'SpellHarmTouch_run': (0x2D2C0C, 0x2D2CBC, 'spell', 'harmtouch_run'),
    'SpellHarmTouch_applyToHit': (0x2D2CBC, 0x2D3060, '', 'harmtouch_apply_to_hit'),
}, [(Model.VT_SPELL_HARMTOUCH, 'Spell', (1,))])
_register(50, 'minorhealing', {
    'SkillMinorHealing_cast': (0x2E022C, 0x2E02CC, 'skill', 'minorhealing_cast'),
    'SpellMinorHealing_ctor': (0x2E0388, 0x2E04F8, '', 'minorhealing_spell_ctor'),
    'SpellMinorHealing_run': (0x2E04F8, 0x2E060C, 'spell', 'minorhealing_run'),
}, [(Model.VT_SPELL_MINORHEALING, 'Spell', (1,))])

_register(54, 'holyshield', {
    'SkillHolyShield_cast': (0x2E80FC, 0x2E819C, 'skill', 'holyshield_cast'),
    'SpellHolyShield_ctor': (0x2E82FC, 0x2E8428, '', 'holyshield_spell_ctor'),
    'SpellHolyShield_run': (0x2E8428, 0x2E8534, 'spell', 'holyshield_run'),
    'SpellHolyShield_absorb': (0x2E8534, 0x2E886C, '', 'holyshield_absorb'),
}, [(Model.VT_SPELL_HOLYSHIELD, 'Spell', (1,))])
_register(55, 'healing', {
    'SkillHealing_cast': (0x2E8CF8, 0x2E8D98, 'skill', 'healing_cast'),
    'SpellHealing_ctor': (0x2E8EC8, 0x2E90B8, '', 'healing_spell_ctor'),
    'SpellHealing_run': (0x2E90B8, 0x2E979C, 'spell', 'healing_run'),
}, [(Model.VT_SPELL_HEALING, 'Spell', (1,))])

_register(68, 'resurrect', {
    'SkillResurrect_canUse': (0x312168, 0x312240, 'skill', 'resurrect_can_use'),
    'SkillResurrect_findTarget': (0x312240, 0x3123E4, '', 'resurrect_find_target'),
    'SkillResurrect_cast': (0x3123E4, 0x312500, 'skill', 'resurrect_cast'),
    'SkillResurrect_isSlotBeingRaised': (0x31270C, 0x3127B4, '', 'resurrect_is_being_raised'),
    'SpellResurrect_ctor': (0x3127B4, 0x312A70, '', 'resurrect_spell_ctor'),
    'SpellResurrect_run': (0x312B30, 0x312F48, 'spell', 'resurrect_run'),
    'SpellResurrect_onOwnerDeath': (0x3130F4, 0x3132C4, '', 'resurrect_on_owner_death'),
}, [(Model.VT_SPELL_RESURRECT, 'Spell', (1,))])

_register(49, 'bash', {
    'SkillBash_canUse': (0x2DE334, 0x2DE3BC, 'skill', 'bash_can_use'),
    'SkillBash_cast': (0x2DE3BC, 0x2DE484, 'skill', 'bash_cast'),
    'SpellBash_ctor': (0x2DE640, 0x2DE7DC, '', 'bash_spell_ctor'),
    'SpellBash_run': (0x2DE7DC, 0x2DEDEC, 'spell', 'bash_run'),
    'SpellBash_windupFx': (0x2DEDEC, 0x2DEFCC, '', 'bash_windup_fx'),
}, [(Model.VT_SPELL_BASH, 'Spell', (1,))])

_register(53, 'criticalhit', {
    'SkillCriticalHit_canUse': (0x2E7224, 0x2E7258, 'skill', 'criticalhit_can_use'),
    'SkillCriticalHit_cast': (0x2E74B0, 0x2E7534, 'skill', 'criticalhit_cast'),
    'SkillCriticalHit_critBonusFor': (0x2E76C4, 0x2E7988, '', 'criticalhit_bonus_for'),
    'SpellCriticalHit_ctor': (0x2E7988, 0x2E7ACC, '', 'criticalhit_spell_ctor'),
    'SpellCriticalHit_run': (0x2E7ACC, 0x2E7F58, 'spell', 'criticalhit_run'),
    'SpellCriticalHit_setTint': (0x2E7F58, 0x2E7F7C, '', 'criticalhit_set_tint'),
}, [(Model.VT_SPELL_CRITICALHIT, 'Spell', (1,))])


# =========================================================================================
# The second pass: the casts and effects of ids 35-40, 51, 52, 56-58 and 65-67
# =========================================================================================
EXTERNALS.update({
    'trail_create': Ext(0x190FF8, 'iiiiiii', 1, 'i', '(seven integers; width) -> trail handle or 0'),
    'trail_addPoint': Ext(0x192550, 'iv', 0, 'n', '(trail handle, position)'),
})


def from_uint(value):
    """The compiler's unsigned -> float idiom (e.g. 0x2c8f90): a plain cvt.s.w below 2^31,
    otherwise ((value >> 1) | (value & 1)) converted and doubled."""
    value &= M32
    if value < 0x80000000:
        return C.from_int(value)
    half = C.from_int((value >> 1) | (value & 1))
    return C.add(half, half)


def c_rem(a, b):
    """The remainder of the machine's signed divide (truncating); with a zero divisor the
    dividend, as the R5900 is reported to leave it."""
    a, b = s32(a), s32(b)
    if b == 0:
        return a
    q = abs(a) // abs(b)
    return a - (-q if (a < 0) != (b < 0) else q) * b


class Model(Model):                             # noqa: F811 - built up section by section from here on
    # =====================================================================================
    # 35 charge: docs/spec/skills-35-68.md section 35.  SkillCharge (table 0x518320; can-use
    # is the base) and SpellCharge (0x88 bytes, table 0x5183a8).
    #
    #   +0x1c ten trail handles   +0x44 the frame of the cast   +0x48 contact made
    #   +0x4c..+0x84 a light record (position +0x7c)
    # =====================================================================================
    VT_SPELL_CHARGE = 0x5183A8
    PDEF_CHARGE_A, PDEF_CHARGE_B, PDEF_CHARGE_RING = 0x8E4FB0, 0x8E5000, 0x8E5050

    def charge_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillCharge_cast 0x2c8864 -> the SpellCharge or 0: pool_new(0x88), the
        constructor; then a caster with the player flag gets action state +0x58c = 9, and
        so does net_objOrGhost(caster) when that is not null (on the owner's machine the
        prediction copy - a per-machine store)."""
        spell = self.call('pool_new', 0x88)
        if spell:
            self.charge_spell_ctor(spell, level, caster, skill)
            if self.u32(caster + 0xC) & 0x40:
                self.w32(caster + 0x58C, 9)
                ghost = self.call('net_objOrGhost', caster)
                if ghost:
                    self.w32(ghost + 0x58C, 9)
        return spell

    def _charge_trail_point(self, owner, ahead, index):
        rise = C.add(C.mul(C.from_int(index), 0x40BFFFFF), F_12)
        return (C.add(self.u32(owner + 0x10), ahead[0]), C.add(self.u32(owner + 0x14), ahead[1]),
                C.add(self.u32(owner + 0x18), rise))

    def charge_spell_ctor(self, spell, level, owner, skill):
        """SpellCharge_ctor 0x2c8cb4: Spell base (ONE SHARED DRAW); the light record at
        +0x4c (position = the owner's), linked; the sound on the owner; start frame +0x44,
        contact +0x48 = 0; ten trails (+0x1c..), each with a first point 10 ahead of the
        owner and 12 + 6 i up.  No own draw."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_CHARGE)
        self.w8(spell + 0x55, 0)
        self.wvec(spell + 0x7C, self.vec(owner + 0x10))
        for off, value in ((0x70, 0x42CE0000), (0x68, 0x42CE0000), (0x74, 0x38C5AD3B), (0x6C, 0x38C5AD3B), (0x78, 0)):
            w32(spell + off, value)
        for off, value in ((0x5E, 0x6C), (0x60, 0x66), (0x56, 0x6C), (0x58, 0x66), (0x62, 0xD0), (0x5A, 0xD0), (0x5C, 0),
                           (0x64, 0)):
            w16(spell + off, value)
        self.w8(spell + 0x54, 0)
        self.call('light_link', spell + 0x4C)
        self.call('sound_playOnObject', self.call('res_find', 0x54E8E8, 0x54E8F0), u32(spell + 0xC), ONE)
        w32(spell + 0x44, u32(G_SIM_FRAME))
        facing = self.s16(u32(spell + 0xC) + 0x38)
        w32(spell + 0x48, 0)
        ahead = (C.mul(C.cos16(facing), 0x41200000), C.mul(C.sin16(self.s16(u32(spell + 0xC) + 0x38)), 0x41200000))
        for i in range(10):
            trail = self.call('trail_create', 1, 800, 4, 0x40, 0x40, 0x80, 0x20, 0x3F4CCCCC)
            w32(spell + 0x1C + 4 * i, trail)
            self.call('trail_addPoint', trail, self._charge_trail_point(u32(spell + 0xC), ahead, i))

    def charge_run(self, spell, pos=0, facing=0):
        """SpellCharge_run 0x2c8f2c, slot 2.

        Contact made, or more than 45 frames since the cast (the difference taken as
        UNSIGNED): for an owner with the player flag, net_objOrGhost(owner) and - without
        contact - state 2 on both; with contact state 3 on both, the owner's track-3 life
        rate +0x190 = -0.058333, voice line 12, the stagger clip of the owner's weapon
        class (class definition + class x 0x68 + 0x7c; anim_startBlendInOut, flags 10, 0.1
        in and out) and damage_apply(owner, owner, 100000, flags 0x4000c040, no
        descriptor, 0; 10, 10).  Then the copy-rebuild byte 0x402797 = 1 and the spell
        ends itself.
        Otherwise: the ten trails get a point each (as in the constructor); 4 + 11
        particles on sample points of the owner's model - per particle ONE OWN DRAW for the
        point (modulo the point count, not tested for 0) and an OWN ball x 13 / x 10; the
        light follows the owner 60 up; 0x402797 = 1."""
        u32, w32 = self.u32, self.w32
        owner = u32(spell + 0xC)
        if u32(spell + 0x48) or C.lt(0x42340000, from_uint(u32(G_SIM_FRAME) - u32(spell + 0x44))):
            if u32(owner + 0xC) & 0x40:
                ghost = self.call('net_objOrGhost', owner)
                if not u32(spell + 0x48):
                    w32(ghost + 0x58C, 2)
                    w32(owner + 0x58C, 2)
                else:
                    w32(ghost + 0x58C, 3)
                    w32(owner + 0x58C, 3)
                    w32(owner + 0x190, 0xBD6EEEEE)
                    self.call('player_voice', u32(owner + 0x3C8), 0xC)
                    weapon_class = self.s8(self.record(owner) + 0x4A86)
                    clip = u32((u32(owner + 0x24) + weapon_class * 0x68 + 0x7C) & M32)
                    self.call('anim_startBlendInOut', owner + 0x114, clip, 10, F_0_1, F_0_1)
                    self.call('damage_apply', owner, owner, 100000, 0, 0, 0x4000C040, 0, 0, 0x41200000, 0x41200000)
            self.w8(G_FORCE_GHOST_REBASE, 1)
            self.spell_end(spell)
            return
        ahead = (C.mul(C.cos16(self.s16(owner + 0x38)), 0x41200000),
                 C.mul(C.sin16(self.s16(u32(spell + 0xC) + 0x38)), 0x41200000))
        for i in range(10):
            self.call('trail_addPoint', u32(spell + 0x1C + 4 * i), self._charge_trail_point(u32(spell + 0xC), ahead, i))
        owner = u32(spell + 0xC)
        model = self.vcall(owner, 16)
        count = s32(self.call('model_getSamplePointCount', model))
        for definition, number, speed in ((self.PDEF_CHARGE_B, 4, 0x41500000), (self.PDEF_CHARGE_A, 11, 0x41200000)):
            for _ in range(number):
                point = self._sample_point(u32(spell + 0xC), model, self.spell_rand(spell), count)
                velocity = tuple(C.mul(c, speed) for c in self.spell_ball(spell))
                self.call('particle_spawn', definition, point, velocity, ZERO)
        owner = u32(spell + 0xC)
        self.wvec(spell + 0x7C, (C.add(u32(owner + 0x10), ZERO), u32(owner + 0x14), C.add(u32(owner + 0x18), 0x42700000)))
        self.call('light_relink', spell + 0x4C)
        self.w8(G_FORCE_GHOST_REBASE, 1)

    def charge_stat3_scaled(self, spell):
        """SpellCharge_getStat3Scaled 0x2c95a4 -> (float) slot 10 (3, level) x 0.016: the
        fraction of the remaining angle Player_move turns per frame of the rush."""
        return C.mul(C.from_int(self.stat(self.u32(spell + 8), 3, self.s8(spell))), 0x3C83126E)

    def charge_on_contact(self, spell, target):
        """SpellCharge_onContact 0x2c95f4 (spell, target or 0), called by Player_onTouch and
        Player_move for a player in state 9.

        Nothing once contact is made (+0x48), or for a target with flag 8 (dead).  Else:
        the sound on the owner, camera_shake(10).
        No target (a wall): eight fx_spawn(2) puffs, THREE OWN DRAWS each (x - 6 + d % 12,
        y - 6 + d % 12, z + d % 72).
        A target: d0 = slot 10 (0, level); unless it is a creature the owner's slot 20
        rejects: ONE OWN DRAW r and damage_apply(target, owner, 100000, flags 0x8c040, no
        descriptor, 0; d0, d0 + d0 x r/65536 x 0.2).
        Then R = slot 10 (2, level) x 12; with R != 0: world_collectObjectsInBox(owner -/+
        R on all axes, capacity 128), d1 = slot 10 (1, level), and every entry that is not
        the owner, not the target, not dead and not a creature the owner's slot 20 rejects
        costs ONE OWN DRAW and is damaged the same way with d1; then a ring of 132 particle
        pairs (an OWN ball and ONE OWN DRAW per pair).  Contact +0x48 = 1."""
        u32 = self.u32
        if u32(spell + 0x48) or (target and u32(target + 0xC) & 8):
            return
        level = self.s8(spell)
        self.call('sound_playOnObject', self.call('res_find', 0x54E8E8, 0x54E908), u32(spell + 0xC), ONE)
        self.call('camera_shake', 0, 0x41200000)
        if not target:
            for _ in range(8):
                x = C.add(C.sub(u32(u32(spell + 0xC) + 0x10), 0x40C00000), C.from_int(self.spell_rand(spell) % 12))
                y = C.add(C.sub(u32(u32(spell + 0xC) + 0x14), 0x40C00000), C.from_int(self.spell_rand(spell) % 12))
                z = C.add(C.sub(C.add(u32(u32(spell + 0xC) + 0x18), 0x42100000), 0x42100000),
                          C.from_int(self.spell_rand(spell) % 0x48))
                self.call('fx_spawn', 2, (x, y, z))
        else:
            amount = C.from_int(self.stat(u32(spell + 8), 0, level))
            if not u32(target + 0xC) & 0x20 or self.vcall(u32(spell + 0xC), 20, target):
                high = C.add(amount, C.mul(C.mul(amount, self.unit(self.spell_rand(spell))), 0x3E4CCCCC))
                self.call('damage_apply', target, u32(spell + 0xC), 100000, 0, 0, 0x8C040, 0, 0, amount, high)
        reach = s32(self.stat(u32(spell + 8), 2, level) * 12)
        if reach:
            owner = u32(spell + 0xC)
            half = C.from_int(reach)
            found = self.call('world_collectObjectsInBox', tuple(C.sub(u32(owner + 0x10 + 4 * i), half) for i in range(3)),
                              tuple(C.add(u32(owner + 0x10 + 4 * i), half) for i in range(3)), 0x80) or ()
            amount = C.from_int(self.stat(u32(spell + 8), 1, level))
            for other in found:
                owner = u32(spell + 0xC)
                if other == owner or other == target or u32(other + 0xC) & 8:
                    continue
                if u32(other + 0xC) & 0x20 and not self.vcall(owner, 20, other):
                    continue
                high = C.add(amount, C.mul(C.mul(amount, self.unit(self.spell_rand(spell))), 0x3E4CCCCC))
                self.call('damage_apply', other, u32(spell + 0xC), 100000, 0, 0, 0x8C040, 0, 0, amount, high)
            for angle in range(0, 0x10000, 500):
                owner = u32(spell + 0xC)
                out = (C.mul(C.cos16(s16(angle)), half), C.mul(C.sin16(s16(angle)), half))
                point = (C.add(u32(owner + 0x10), out[0]), C.add(u32(owner + 0x14), out[1]), C.add(u32(owner + 0x18), 0x40A00000))
                b = self.spell_ball(spell)
                rise = C.add(C.mul(self.unit(self.spell_rand(spell)), 0x40A00000), 0x41200000)
                velocity = (C.mul(b[0], 0x41200000), C.mul(b[1], 0x41200000), rise)
                self.call('particle_spawn', self.PDEF_CHARGE_RING, point, velocity, ZERO)
                point = (C.add(u32(owner + 0x10), C.mul(out[0], HALF)), C.add(u32(owner + 0x14), C.mul(out[1], HALF)), point[2])
                self.call('particle_spawn', self.PDEF_CHARGE_RING, point, velocity, ZERO)
        self.w32(spell + 0x48, 1)


_register(35, 'charge', {
    'SkillCharge_cast': (0x2C8864, 0x2C8914, 'skill', 'charge_cast'),
    'SpellCharge_ctor': (0x2C8CB4, 0x2C8F2C, '', 'charge_spell_ctor'),
    'SpellCharge_run': (0x2C8F2C, 0x2C95A4, 'spell', 'charge_run'),
    'SpellCharge_getStat3Scaled': (0x2C95A4, 0x2C95F4, '', 'charge_stat3_scaled'),
    'SpellCharge_onContact': (0x2C95F4, 0x2C9C54, '', 'charge_on_contact'),
}, [(Model.VT_SPELL_CHARGE, 'Spell', (1,))])



class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 36 darkness: docs/spec/skills-35-68.md section 36.  SkillDarkness (table 0x5188a0;
    # can-use is the base) and the object DarknessProjectile (0xb0 bytes, table 0x518810,
    # a GameObject, not a Projectile).
    #
    #   +0x4c step per frame   +0x58..+0x90 a light record (position +0x88)   +0x94 life
    #   +0x98 level   +0x9c still moving   +0xa0 attached (byte)   +0xa8 caster handle
    #   +0xac Skill
    # =====================================================================================
    VT_DARKNESS = 0x518810
    PDEF_DARKNESS = 0x8E5410
    G_AMBIENT_BYTES = 0x5D3478                  # four bytes the light's colour is taken from (presentation)

    def darkness_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillDarkness_cast 0x2cf1e0 -> 0: velocity = (cos, sin of the facing, 0) x 373;
        pool_new(0xb0) and the constructor at the caster's position, 36 up (the position
        argument is not used; the caster is not tested for null)."""
        facing = s16(facing)
        velocity = (C.mul(C.cos16(facing), 0x43BA8000), C.mul(C.sin16(facing), 0x43BA8000), C.mul(ZERO, 0x43BA8000))
        obj = self.call('pool_new', 0xB0)
        if obj:
            start = (C.add(self.u32(caster + 0x10), ZERO), self.u32(caster + 0x14), C.add(self.u32(caster + 0x18), 0x42100000))
            self.darkness_ctor(obj, self.local_vec(start), self.local_vec(velocity), skill, level, caster)
        return 0

    def ambient_bytes(self):
        """0x14a028: the four bytes at 0x5d3478 as four halfwords in the caller's frame."""
        return [self.u8(self.G_AMBIENT_BYTES + i) for i in range(4)]

    def darkness_ctor(self, obj, pos, velocity, skill, level, caster):
        """DarknessProjectile_ctor 0x2cf460 (object, position, velocity, skill, level,
        caster): GameObject_ctor (ONE SHARED DRAW); the light record at +0x58, linked;
        flags |= 0x4001; step +0x4c = velocity x (1/60); life +0x94 = 108; Skill, level;
        not attached, moving; the sound on the caster; the caster handle +0xa8 (with a
        caster); the light's colour = 1 - three of the bytes at 0x5d3478; the every-frame
        run list."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        start, velocity = self.vec(pos), self.vec(velocity)
        self.game_object_ctor(obj, pos, 0, 0)
        w32(obj + 0x48, self.VT_DARKNESS)
        self.w8(obj + 0x61, 0)
        self.wvec(obj + 0x88, start)
        for off, value in ((0x7C, 0x43280000), (0x80, 0x38149B92), (0x74, 0x43280000), (0x78, 0x38149B92), (0x84, 0)):
            w32(obj + off, value)
        for off in (0x6E, 0x62, 0x64, 0x66, 0x6A, 0x6C):
            w16(obj + off, 0xFF82)
        w16(obj + 0x68, 0)
        w16(obj + 0x70, 0)
        self.w8(obj + 0x60, 0)
        self.call('light_link', obj + 0x58)
        w32(obj + 0xA4, 0)
        w32(obj + 0xA8, 0)
        w32(obj + 0xC, u32(obj + 0xC) | 0x4001)
        self.wvec(obj + 0x4C, tuple(C.mul(v, DT) for v in velocity))
        w32(obj + 0x94, 0x6C)
        w32(obj + 0xAC, skill)
        w32(obj + 0x98, level)
        self.w8(obj + 0xA0, 0)
        w32(obj + 0x9C, 1)
        self.call('sound_playOnObject', self.call('res_find', 0x54ECD0, 0x54ECD8), caster, ONE)
        if caster:
            self.handle_link(obj + 0xA8, caster, caster)
        colour = self.ambient_bytes()
        for i in range(3):
            w16(obj + 0x62 + 2 * i, 1 - colour[i])
        self.call('obj_runEveryFrame', obj)

    def _darkness_box(self, obj):
        here = self.vec(obj + 0x10)
        return self.call('world_collectObjectsInBox', tuple(C.sub(v, F_24) for v in here), tuple(C.add(v, F_24) for v in here),
                         0x80) or ()

    def darkness_run(self, obj):
        """DarknessProjectile_run 0x2cf690, slot 4, once a frame.

        Attached (+0xa0 == 1): on frames divisible by 30, with a caster: every entry of
        world_collectObjectsInBox(position -/+ 24, capacity 128) the caster's slot 20
        accepts, that has hit points above 0 and no-target timer +0x316 == 0: T = slot 10
        (0, level); ONE OWN DRAW r; with r % 100 + 1 < T its slot 31 gets slot 10 (3,
        level) x 60 frames - (frames >> 1) + 1 for a creature of non-zero boss rank.
        Not attached: while moving, position += step and terrain_height(world, position;
        24) above z stops it; with a caster the box, and every entry the caster's slot 20
        accepts: the FIRST one attaches the cloud (life = slot 10 (2, level) x 60, position
        = the entry's, 36 up), and each is asked a second time and then takes damage_apply
        (entry, caster, 100000, flags 0x40, no descriptor, 0; low, high of slot 8 (1,
        level, no randomising; 0.2)).
        Then: the light follows; 8 particles (an OWN ball each); life -= 1 and at -1
        obj_delete and the light is unlinked."""
        u32, w32 = self.u32, self.w32
        level = u32(obj + 0x98)
        if self.s8(obj + 0xA0) == 1:
            if c_rem(self.s32(G_SIM_FRAME), 30) == 0:
                if u32(obj + 0xA8):
                    for other in self._darkness_box(obj):
                        owner = u32(u32(obj + 0xA8) + 0xC)
                        if not self.vcall(owner, 20, other):
                            continue
                        if not C.lt(ZERO, u32(other + 0x228)) or self.s16(other + 0x316):
                            continue
                        chance = self.stat(u32(obj + 0xAC), 0, level)
                        if self.obj_rand(obj) % 100 + 1 < chance:
                            frames = s32(self.stat(u32(obj + 0xAC), 3, level) * 60)
                            if self.call('creature_bossRank', other):
                                frames = (frames >> 1) + 1
                            self.vcall(other, 31, frames)
        else:
            if u32(obj + 0x9C):
                for i in range(3):
                    w32(obj + 0x10 + 4 * i, C.add(u32(obj + 0x10 + 4 * i), u32(obj + 0x4C + 4 * i)))
                ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), F_24)
                if C.lt(u32(obj + 0x18), ground):
                    w32(obj + 0x9C, 0)
            if u32(obj + 0xA8):
                for other in self._darkness_box(obj):
                    if not self.vcall(u32(u32(obj + 0xA8) + 0xC), 20, other):
                        continue
                    if self.s8(obj + 0xA0) == 0:
                        life = self.stat(u32(obj + 0xAC), 2, level)
                        self.w8(obj + 0xA0, 1)
                        w32(obj + 0x94, s32(life * 60))
                        self.wvec(obj + 0x10, (C.add(u32(other + 0x10), ZERO), u32(other + 0x14),
                                               C.add(u32(other + 0x18), 0x42100000)))
                    if self.vcall(u32(u32(obj + 0xA8) + 0xC), 20, other):
                        low, high = self.stat_range(u32(obj + 0xAC), 1, level, 0, 0x3E4CCCCC)
                        self.call('damage_apply', other, u32(u32(obj + 0xA8) + 0xC), 100000, 0, 0, 0x40, 0, 0,
                                  C.from_int(low), C.from_int(high))
        self.wvec(obj + 0x88, self.vec(obj + 0x10))
        self.call('light_relink', obj + 0x58)
        for _ in range(8):
            b = self.obj_ball(obj)
            velocity = tuple(C.add(u32(obj + 0x4C + 4 * i), C.mul(b[i], 0xBEA22221)) for i in range(3))
            point = tuple(C.add(C.mul(C.add(b[i], b[i]), F_12), u32(obj + 0x10 + 4 * i)) for i in range(3))
            self.call('particle_spawn', self.PDEF_DARKNESS, point, velocity, ZERO)
        w32(obj + 0x94, u32(obj + 0x94) - 1)
        if self.s32(obj + 0x94) == -1:
            self.call('obj_delete', obj)
            self.call('light_unlink', obj + 0x58)


_register(36, 'darkness', {
    'SkillDarkness_cast': (0x2CF1E0, 0x2CF320, 'skill', 'darkness_cast'),
    'DarknessProjectile_ctor': (0x2CF460, 0x2CF690, '', 'darkness_ctor'),
    'DarknessProjectile_run': (0x2CF690, 0x2CFD8C, 'object', 'darkness_run'),
    'ambientBytes_14a028': (0x14A028, 0x14A054, '', 'ambient_bytes'),
}, [(Model.VT_DARKNESS, 'Creature', (1,))])



EXTERNALS.update({
    'sound_setVolume': Ext(0x214650, 'i', 1, 'n', '(sound handle; volume)'),
    'beam_create': Ext(0x193088, 'vviii', 2, 'i', '(from, to, 0x104, 4, colour; two widths) -> beam handle or 0'),
    'beam_update': Ext(0x1933C8, 'ivvii', 0, 'n', '(beam handle, from, to, alpha, -1)'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 37 shock: docs/spec/skills-35-68.md section 37.  SkillShock (table 0x518210; can-use
    # is the base) and the object ShockProjectile (0x198 bytes, table 0x50e228, a
    # GameObject).
    #
    #   +0x38 s16 facing   +0x4c Skill   +0x50 candidates (list)   +0x54 chained victims
    #   (list, newest first)   +0x58 birth frame   +0x120 step per frame   +0x12c eight beam
    #   handles   +0x14c..+0x184 a light record (position +0x17c)   +0x188 level   +0x189
    #   state (0 flying, 1 struck, 2 stopped)   +0x18a most victims   +0x18b victims
    #   +0x18c chain range squared   +0x190 speed   +0x194 caster handle
    # =====================================================================================
    VT_SHOCK = 0x50E228
    PDEF_SHOCK_A, PDEF_SHOCK_B = 0x8E4BF0, 0x8E4C40

    def shock_cast(self, skill, level, caster, pos, facing):
        """SkillShock_cast 0x2c3d68 -> 0: pool_new(0x198) and the constructor at the cast
        position."""
        obj = self.call('pool_new', 0x198)
        if obj:
            self.shock_ctor(obj, self.local_vec(self.vec(pos)), s16(facing), caster, skill, level)
        return 0

    def shock_ctor(self, obj, pos, facing, caster, skill, level):
        """ShockProjectile_ctor 0x2c3fe4 (object, position, facing, caster, skill, level).

        GameObject_ctor (ONE SHARED DRAW); both lists empty; the light record at +0x14c,
        linked; a sound on the caster; facing; flags |= 1; Skill; birth = frame; level
        byte; radius 12; the caster handle +0x194 (with a caster); state 0; speed 341;
        step = (cos, sin of the facing) x (1 / sqrt(cos^2 + sin^2)) x (341 x (1/60)), z 0;
        most victims +0x18a = slot 13 (1, level, the caster handle, cap 10) + 1 (a byte);
        the every-frame run list; the same sound on the object."""
        u32, w32, w16, w8 = self.u32, self.w32, self.w16, self.w8
        start = self.vec(pos)
        self.game_object_ctor(obj, pos, 0, 0)
        w32(obj + 0x50, 0)
        w32(obj + 0x54, 0)
        w32(obj + 0x48, self.VT_SHOCK)
        w8(obj + 0x155, 0)
        self.wvec(obj + 0x17C, start)
        for off, value in ((0x174, 0x382C598A), (0x16C, 0x382C598A), (0x170, 0x431C0000), (0x168, 0x431C0000), (0x178, 0)):
            w32(obj + off, value)
        for off, value in ((0x160, 0xE1), (0x164, 0xFFE0), (0x158, 0xE1), (0x15C, 0xFFE0), (0x162, 0x140), (0x15A, 0x140),
                           (0x156, 0), (0x15E, 0)):
            w16(obj + off, value)
        w8(obj + 0x154, 0)
        self.call('light_link', obj + 0x14C)
        w32(obj + 0x194, 0)
        self.call('sound_playOnObject', self.call('res_find', 0x54E6A0, 0x54E6A8), caster, ONE)
        w16(obj + 0x38, facing)
        w32(obj + 0xC, u32(obj + 0xC) | 1)
        w32(obj + 0x4C, skill)
        w32(obj + 0x58, u32(G_SIM_FRAME))
        w8(obj + 0x188, level)
        w32(obj + 0x1C, F_12)
        if caster:
            self.handle_link(obj + 0x194, caster, caster)
        w8(obj + 0x189, 0)
        w32(obj + 0x190, 0x43AA8000)
        cos, sin = C.cos16(self.s16(obj + 0x38)), C.sin16(self.s16(obj + 0x38))
        w32(obj + 0x128, 0)
        inverse = C.rsqrt(ONE, C.add(C.mul(cos, cos), C.mul(sin, sin)))
        w32(obj + 0x124, C.mul(sin, inverse))
        w32(obj + 0x120, C.mul(C.mul(cos, inverse), C.mul(u32(obj + 0x190), DT)))
        w32(obj + 0x124, C.mul(u32(obj + 0x124), C.mul(u32(obj + 0x190), DT)))
        most = self.skill_call(u32(obj + 0x4C), 13, 1, self.s8(obj + 0x188), obj + 0x194, 10)
        w8(obj + 0x18A, most + 1)
        self.call('obj_runEveryFrame', obj)
        self.call('sound_playOnObject', self.call('res_find', 0x54E6A0, 0x54E6A8), obj, ONE)

    def shock_in_chain(self, obj, other):
        """ShockProjectile_inChain 0x2c50e4 -> 1 when `other` is in the victims list."""
        return 1 if other in self.list_objects(obj + 0x54) else 0

    def shock_build_chain(self, obj, origin):
        """ShockProjectile_buildChain 0x2c4fa8 (object, address of a point), recursive.

        Nothing once victims == most.  The candidate (list +0x50, from the head) that is
        there, not dead (flag 8), nearer in the plane than the range (+0x18c, squared) and
        than every earlier one (strict, so the first of equals wins), and not in the chain
        yet, is linked at the HEAD of the victims list +0x54; then, when most != 0, the
        count rises and the chain goes on from the new victim's position, and after that
        again from the same point."""
        u32 = self.u32
        if self.s8(obj + 0x18B) == self.s8(obj + 0x18A):
            return
        best, best_d = 0, 0x4CBEB25C
        for other in self.list_objects(obj + 0x50):
            if not other or u32(other + 0xC) & 8:
                continue
            dy = C.sub(u32(other + 0x14), u32(origin + 4))
            dx = C.sub(u32(other + 0x10), u32(origin))
            dist = C.add(C.mul(dx, dx), C.mul(dy, dy))
            if C.lt(dist, u32(obj + 0x18C)) and C.lt(dist, best_d) and not self.shock_in_chain(obj, other):
                best, best_d = other, dist
        if best:
            self.handle_link(obj + 0x54, best, best)
            if self.s8(obj + 0x18A):
                self.w8(obj + 0x18B, self.u8(obj + 0x18B) + 1)
                self.shock_build_chain(obj, best + 0x10)
                self.shock_build_chain(obj, origin)

    def _shock_wants(self, obj, other, target=0):
        """The filter of both box walks: with a caster its slot 20; without one a creature
        (flag 0x20) with none of the flags 0xd that is not the bolt (nor the target)."""
        node = self.u32(obj + 0x194)
        if node:
            return bool(self.vcall(self.u32(node + 0xC), 20, other))
        flags = self.u32(other + 0xC)
        return bool(flags & 0x20) and not flags & 0xD and other != obj and (not target or other != target)

    def shock_run(self, obj):
        """ShockProjectile_run 0x2c42e4, slot 4, once a frame.

        remaining = birth + 300 - frame (taken first).  sound_setVolume(+0x5c; 1.0);
        x, y += step; the grid cell.
        Flying (state 0): with a speed, terrain_height(world, position; 6) above z stops
        the bolt (state 2, speed and step 0, birth = frame - 270, a sound).  Otherwise, on
        frames with (frame & 7) == 0, the hit test: the first entry of
        world_collectObjectsInBox(position -/+ 18, capacity 512) that passes the filter
        and is nearer in the plane than its radius + 18 is the target T.  With a target:
        every entry of the box T -/+ 1200 that passes the filter is linked into the
        candidates +0x50, then T itself; victims = 0, range^2 = 44521; the chain is built
        from T; D = slot 13 (0, level, the caster handle, cap 10); ONE SHARED DRAW r;
        descriptor slot 0 = (0x18, D, D + (int)(D x 0.2 x r/65536), 0); every chained
        victim, newest first, takes damage_apply(victim, the caster or - without one - the
        bolt, 100000, flags 0x40, the descriptor, 0; 0, 0); speed and step 0, state 1,
        birth = frame - 270, the beam handles of the victims = -1.
        In state 0 the light then follows and pulses (dimming over the last 30 frames).
        Struck (state 1): a beam between each chained victim and the next (created once,
        then refreshed).
        Always: 42 particle groups from the OWN generator (a ball for the offset, a ball
        for the velocity, ONE DRAW for a second particle 1 time in 32); at remaining < 1
        the object deletes itself."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        remaining = s32(u32(obj + 0x58) - u32(G_SIM_FRAME) + 300)
        self.call('sound_setVolume', u32(obj + 0x5C), ONE)
        w32(obj + 0x10, C.add(u32(obj + 0x10), u32(obj + 0x120)))
        w32(obj + 0x14, C.add(u32(obj + 0x14), u32(obj + 0x124)))
        self.call('obj_updateGridCell', obj)
        if self.s8(obj + 0x189) == 0:
            stopped = False
            if not C.eq(u32(obj + 0x190), ZERO):
                ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), 0x40C00000)
                if not C.le(ground, u32(obj + 0x18)):
                    stopped = True
                    w32(obj + 0x124, 0)
                    w8(obj + 0x189, 2)
                    w32(obj + 0x190, 0)
                    w32(obj + 0x120, 0)
                    w32(obj + 0x58, u32(G_SIM_FRAME) - 0x10E)
                    self.call('sound_playOnObject', self.call('res_find', 0x54E6A0, 0x54E6C0), obj, ONE)
            if not stopped and u32(G_SIM_FRAME) & 7 == 0:
                here = self.vec(obj + 0x10)
                found = self.call('world_collectObjectsInBox', tuple(C.sub(v, 0x41900000) for v in here),
                                  tuple(C.add(v, 0x41900000) for v in here), 0x200) or ()
                target = 0
                for other in found:
                    if self._shock_wants(obj, other):
                        dy = C.sub(u32(obj + 0x14), u32(other + 0x14))
                        dx = C.sub(u32(obj + 0x10), u32(other + 0x10))
                        if C.lt(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), C.add(u32(other + 0x1C), 0x41900000)):
                            target = other
                            break
                if target:
                    spot = self.vec(target + 0x10)
                    found = self.call('world_collectObjectsInBox', tuple(C.sub(v, 0x44960000) for v in spot),
                                      tuple(C.add(v, 0x44960000) for v in spot), 0x200) or ()
                    for other in found:
                        if self._shock_wants(obj, other, target):
                            self.handle_link(obj + 0x50, other, other)
                    self.handle_link(obj + 0x50, target, target)
                    w8(obj + 0x18B, 0)
                    w32(obj + 0x18C, 0x472DE900)
                    self.shock_build_chain(obj, target + 0x10)
                    amount = s32(self.skill_call(u32(obj + 0x4C), 13, 0, self.s8(obj + 0x188), obj + 0x194, 10))
                    extra = C.to_int(C.mul(C.mul(C.from_int(amount), 0x3E4CCCCC), self.unit(self.draw())))
                    desc = self.descriptor((0x18, amount, amount + s32(extra), 0))
                    for victim in self.list_objects(obj + 0x54):
                        if victim:
                            attacker = u32(u32(obj + 0x194) + 0xC) if u32(obj + 0x194) else obj
                            self.call('damage_apply', victim, attacker, 100000, 0, 0, 0x40, desc, 0, ZERO, ZERO)
                    w32(obj + 0x190, 0)
                    w8(obj + 0x189, 1)
                    w32(obj + 0x120, 0)
                    w32(obj + 0x124, 0)
                    w32(obj + 0x58, u32(G_SIM_FRAME) - 0x10E)
                    for k in range(max(self.s8(obj + 0x18B), 0)):
                        w32(obj + 0x12C + 4 * k, M32)
            fade = 0
            if C.le(C.from_int(remaining), 0x41F00000):
                fade = s32(0xB4 - remaining * 6)
            self.wvec(obj + 0x17C, self.vec(obj + 0x10))
            reach = C.from_int(s32(s32(C.to_int(C.mul(C.sin16(s16(u32(G_SIM_FRAME) * 6000)), 0x41200000))) - fade + 0x60))
            w32(obj + 0x168, reach)
            w32(obj + 0x170, reach)
            inverse = C.div(ONE, C.mul(reach, reach))
            w32(obj + 0x174, inverse)
            w32(obj + 0x16C, inverse)
            self.call('light_relink', obj + 0x14C)
        if self.s8(obj + 0x189) == 1:
            node, k = u32(obj + 0x54), 0
            while node and u32(node):
                victim, after = u32(node + 0xC), u32(u32(node) + 0xC)
                if victim and after:
                    slot = obj + 0x12C + 4 * k
                    a = (C.add(u32(victim + 0x10), ZERO), u32(victim + 0x14), C.add(u32(victim + 0x18), 0x42100000))
                    b = (C.add(u32(after + 0x10), ZERO), u32(after + 0x14), C.add(u32(after + 0x18), 0x42100000))
                    if u32(slot) == M32:
                        w32(slot, self.call('beam_create', a, b, 0x104, 4, 0x5E808080, 0x41800000, 0x41080000))
                    else:
                        self.call('beam_update', u32(slot), a, b, 0x80, M32)
                node = u32(node)
                k += 1
        for _ in range(0x2A):
            b = self.obj_ball(obj)
            inverse = C.rsqrt(ONE, C.add(C.add(C.mul(b[0], b[0]), C.mul(b[1], b[1])), C.mul(b[2], b[2])))
            offset = tuple(C.mul(C.mul(c, inverse), 0x41880000) for c in b)
            point = tuple(C.add(u32(obj + 0x10 + 4 * i), offset[i]) for i in range(3))
            velocity = self.obj_ball(obj)
            self.call('particle_spawn', self.PDEF_SHOCK_A, point, tuple(velocity), ZERO)
            if self.obj_rand(obj) & 0x1F == 0:
                self.call('particle_spawn', self.PDEF_SHOCK_B, point, tuple(velocity), ZERO)
        if remaining < 1:
            self.vcall(obj, 1, 3)


_register(37, 'shock', {
    'SkillShock_cast': (0x2C3D68, 0x2C3DF8, 'skill', 'shock_cast'),
    'ShockProjectile_ctor': (0x2C3FE4, 0x2C42E4, '', 'shock_ctor'),
    'ShockProjectile_run': (0x2C42E4, 0x2C4E64, 'object', 'shock_run'),
    'ShockProjectile_buildChain': (0x2C4FA8, 0x2C50E4, '', 'shock_build_chain'),
    'ShockProjectile_inChain': (0x2C50E4, 0x2C5124, '', 'shock_in_chain'),
}, [(Model.VT_SHOCK, 'Creature', (1,))])



EXTERNALS.update({
    'StaticFire_ctor': Ext(0x2C5240, 'pvipi', 2, 'n', '(block, position, life in frames, owner, secondary; radius, scale): a '
                           'fire that burns what its owner calls an enemy; keeps the owner as a PLAIN POINTER at +0x4a8'),
    'Player_clampToScreen': Ext(0x1B3D90, 'po-', 0, 'n', '(player, velocity in place, mask out): offline only; the callback '
                                'hands back the corrected velocity'),
    'obj_moveWithCollision': Ext(0x14D4B8, 'pvii', 0, 'i', '(object, velocity per second, ignored object, ignore creatures) '
                                 '-> bits'),
    'isNearView': Ext(0x1E77C0, 'v', 1, 'i', '(position; radius) -> near a player (net game) or the camera focus'),
})
OBJECT_CTORS = OBJECT_CTORS + ('StaticFire_ctor',)


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 67 shadowstep: docs/spec/skills-35-68.md section 67.  SkillShadowStep (table
    # 0x51bd78; can-use is the base) and SpellShadowStep (0x34 bytes, table 0x51bd48).
    #
    #   +0x18 progress t   +0x1c speed 370   +0x20 velocity   +0x2c the creature moved
    #   +0x30 s16 the facing set in the second half
    # =====================================================================================
    VT_SPELL_SHADOWSTEP = 0x51BD48
    PDEF_SHADOWSTEP = 0x8E84B8

    def shadowstep_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillShadowStep_cast 0x311340 -> the SpellShadowStep or 0: slot 14 (level, 20),
        pool_new(0x34), the constructor.  Position and facing are not used."""
        level = self.skill_call(skill, 14, level, 0x14)
        spell = self.call('pool_new', 0x34)
        if spell:
            self.shadowstep_spell_ctor(spell, level, caster, skill)
        return spell

    def shadowstep_spell_ctor(self, spell, level, owner, skill):
        """SpellShadowStep_ctor 0x311638 (spell, level, owner, skill).

        Spell base (ONE SHARED DRAW); speed 370, t = 0; the owner's action state +0x58c =
        0xe and object flags |= 5, WHATEVER the owner is; the end facing = facing - 0x8000;
        velocity = (cos, sin of the facing, 0) normalised x 370; the sound.
        s0 = slot 10 (0, level), s1 = slot 10 (1, level).  With s1 != 0: pool_new(0x4ac)
        and a StaticFire at the owner (360 frames; ONE SHARED DRAW inside), and for n = s1
        - 1 further ones on a ring of radius 75 starting at the facing, 0xffff / n apart
        (each: terrain_heightAtPoint, kept when within 72 of the owner's z; 240 frames,
        secondary).  Every fire is handed the owner as a plain pointer.
        Every entry of world_collectObjectsInBox(owner -/+ (97, 97, 1000), capacity 64)
        that is a creature, that the owner's slot 20 accepts and whose target handle +0x234
        holds the owner: its slot 31 (s0), and with n != 0 a knock-back of 151 at angle
        atan2_16(entry - owner) - 0x8000.
        86 particles on the owner's model (an OWN ball and ONE OWN DRAW each).  With n == 0
        a LightEffect 36 above the owner (ONE SHARED DRAW)."""
        u32, w32 = self.u32, self.w32
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_SHADOWSTEP)
        w32(spell + 0x1C, 0x43B90000)
        w32(spell + 0x18, 0)
        w32(spell + 0x20, C.cos16(self.s16(owner + 0x38)))
        w32(spell + 0x24, C.sin16(self.s16(u32(spell + 0xC) + 0x38)))
        w32(spell + 0x28, 0)
        v = self.vec(spell + 0x20)
        facing = self.s16(u32(spell + 0xC) + 0x38)
        flags = u32(owner + 0xC)
        w32(owner + 0x58C, 0xE)
        self.w16(spell + 0x30, facing - 0x8000)
        w32(owner + 0xC, flags | 5)
        w32(spell + 0x2C, owner)
        inverse = C.rsqrt(ONE, C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2])))
        self.wvec(spell + 0x20, tuple(C.mul(C.mul(c, inverse), u32(spell + 0x1C)) for c in v))
        self.call('sound_playAtPos', self.call('res_find', 0x5528C8, 0x5528D0), self.vec(u32(spell + 0xC) + 0x10), ONE)
        mover = u32(spell + 0x2C)
        reach = (0x42C20000, 0x42C20000, 0x447A0000)
        low = tuple(C.sub(u32(mover + 0x10 + 4 * i), reach[i]) for i in range(3))
        high = tuple(C.add(u32(mover + 0x10 + 4 * i), reach[i]) for i in range(3))
        calm = self.skill_call(u32(spell + 8), 10, 0, self.s8(spell))
        fires = s32(self.skill_call(u32(spell + 8), 10, 1, self.s8(spell)))
        ring = 0
        if fires:
            block = self.call('pool_new', 0x4AC)
            if block:
                mover = u32(spell + 0x2C)
                self.object_ctor('StaticFire_ctor', block, self.vec(mover + 0x10), 0x168, mover, 0, 0x42F00000, ONE)
            ring = fires - 1
            if ring:
                angle = self.s16(u32(spell + 0x2C) + 0x38)
                step = 0xFFFF // ring if ring > 0 else 0
                height = ZERO
                for _ in range(max(ring, 0)):
                    x = C.add(u32(u32(spell + 0x2C) + 0x10), C.mul(C.sin16(s16(angle)), 0x42960000))
                    y = C.add(u32(u32(spell + 0x2C) + 0x14), C.mul(C.cos16(s16(angle)), 0x42960000))
                    height = self.call('terrain_heightAtPoint', u32(G_WORLD), (x, y, height))
                    if not C.lt(0x42900000, C.fabs(C.sub(u32(u32(spell + 0xC) + 0x18), height))):
                        block = self.call('pool_new', 0x4AC)
                        if block:
                            self.object_ctor('StaticFire_ctor', block, (x, y, height), 0xF0, u32(spell + 0x2C), 1,
                                             0x42F00000, ONE)
                    angle = s32(angle + step)
        for other in self.call('world_collectObjectsInBox', low, high, 0x40) or ():
            if not u32(other + 0xC) & 0x20 or not self.vcall(u32(spell + 0x2C), 20, other):
                continue
            if not u32(other + 0x234) or u32(u32(other + 0x234) + 0xC) != u32(spell + 0x2C):
                continue
            self.vcall(other, 31, calm)
            if ring:
                w32(other + 0x2E8, 0x43170000)
                mover = u32(spell + 0x2C)
                self.w16(other + 0x2E0, C.atan2_16(C.sub(u32(other + 0x14), u32(mover + 0x14)),
                                                   C.sub(u32(other + 0x10), u32(mover + 0x10))) - 0x8000)
        mover = u32(spell + 0x2C)
        model = self.vcall(mover, 16)
        count = s32(self.call('model_getSamplePointCount', model))
        for _ in range(0x56):
            velocity = tuple(C.mul(c, 0x40400000) for c in self.spell_ball(spell))
            point = self._sample_point(u32(spell + 0x2C), model, self.spell_rand(spell), count)
            self.call('particle_spawn', self.PDEF_SHADOWSTEP, point, velocity, ZERO)
        if not ring:
            light = self.call('pool_new', 0xBC)
            if light:
                mover = u32(spell + 0x2C)
                spot = (C.add(u32(mover + 0x10), ZERO), u32(mover + 0x14), C.add(u32(mover + 0x18), 0x42100000))
                self.light_effect(light, spot, 0x43000000, 0x429E0000, 0x42540000, 0x42F00000, 0x43340000, ZERO, ONE,
                                  rest=(0xC2C00000, 0, 0, 0, 0))

    def shadowstep_run(self, spell, pos=0, facing=0):
        """SpellShadowStep_run 0x311e3c, slot 2.

        s = 2 (t - 0.5); v = the velocity; offline (g_networkMode == 0) Player_clampToScreen
        corrects it; v x 0.5; the mover's scale +0xdc = s^3; obj_moveWithCollision(mover,
        v, 0, ignore creatures 1) TWICE; the copy-rebuild byte 0x402797 = 1; with the scale
        below 0.5 creature flag 0x200000 (not drawn); t += 0.04088309; t > 0.5: the
        OWNER's facing = the end facing; t > 1: the spell ends itself (the 25th call)."""
        u32, w32 = self.u32, self.w32
        half = C.sub(u32(spell + 0x18), HALF)
        half = C.add(half, half)
        velocity = self.vec(spell + 0x20)
        if not self.u8(G_NETWORK_MODE):
            velocity = self.call('Player_clampToScreen', u32(spell + 0x2C))
        mover = u32(spell + 0x2C)
        velocity = tuple(C.mul(c, HALF) for c in velocity)
        w32(mover + 0xDC, C.mul(C.mul(half, half), half))
        self.call('obj_moveWithCollision', mover, velocity, 0, 1)
        self.call('obj_moveWithCollision', u32(spell + 0x2C), velocity, 0, 1)
        self.w8(G_FORCE_GHOST_REBASE, 1)
        mover = u32(spell + 0x2C)
        if C.lt(u32(mover + 0xDC), HALF):
            self.w64(mover + 0xA8, self.u64(mover + 0xA8) | 0x200000)
        w32(spell + 0x18, C.add(u32(spell + 0x18), 0x3D277507))
        if C.lt(HALF, u32(spell + 0x18)):
            self.w16(u32(spell + 0xC) + 0x38, self.u16(spell + 0x30))
        if C.lt(ONE, u32(spell + 0x18)):
            self.spell_end(spell)


_register(67, 'shadowstep', {
    'SkillShadowStep_cast': (0x311340, 0x3113E0, 'skill', 'shadowstep_cast'),
    'SpellShadowStep_ctor': (0x311638, 0x311DA0, '', 'shadowstep_spell_ctor'),
    'SpellShadowStep_run': (0x311E3C, 0x311FC8, 'spell', 'shadowstep_run'),
}, [(Model.VT_SPELL_SHADOWSTEP, 'Spell', (1,))])



EXTERNALS.update({
    'SpellAncestralCall_typeinfo': Ext(0x3CE9BC, '', 0, 'i', 'type-info getter'),
    'sound_stop': Ext(0x213EA0, 'i', 0, 'n', '(sound handle)'),
    'sound_release': Ext(0x213438, 'i', 0, 'n', '(sound handle): let a looping sound repeat'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 51 ancestralcall: docs/spec/skills-35-68.md section 51.  SkillAncestralCall (table
    # 0x519808; flag bit 0 set: THE PREDICTION COPY MAY CAST IT) and SpellAncestralCall
    # (0x84 bytes, table 0x5197d8).
    #
    #   +0x18 the caster again   +0x1c seconds elapsed   +0x20 duration   +0x24 radius
    #   +0x28 frame of the cast   +0x2c three beam handles   +0x7c cast animation over
    #   +0x80 particle group
    # =====================================================================================
    VT_SPELL_ANCESTRALCALL = 0x5197D8
    PDEF_ANCESTRAL_RING = 0x8E5C30
    ANCESTRAL_CLIPS = {0: 0x54FC00, 5: 0x54FC10, 2: 0x54FC20, 1: 0x54FC30, 3: 0x54FC40, 7: 0x54FC50}    # else 0x54fc10
    ANCESTRAL_BEAM_FRAMES = 0x54FC60            # three frame offsets (data)

    def ancestralcall_can_use(self, skill, caster):
        """SkillAncestralCall_canUse 0x2e060c -> 1 unless the caster carries a
        SpellAncestralCall."""
        return 0 if self.call('creature_findSpellByType', caster, self.call('SpellAncestralCall_typeinfo')) else 1

    def ancestralcall_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillAncestralCall_cast 0x2e0750 -> the spell or 0: slot 14 (level, 10),
        pool_new(0x84), the constructor."""
        level = self.skill_call(skill, 14, level, 10)
        spell = self.call('pool_new', 0x84)
        if spell:
            self.ancestralcall_spell_ctor(spell, level, caster, skill)
        return spell

    def ancestralcall_spell_ctor(self, spell, level, owner, skill):
        """SpellAncestralCall_ctor 0x2e09b4 (spell, level, owner, skill).

        For EVERY caster, the prediction copy included: Spell base (ONE SHARED DRAW);
        +0x18 = owner, clock +0x1c = 0; a sound on the owner; the cast clip of the owner's
        weapon class (record byte +0x4a86 picks the name; res_find in the class lump) is
        started on the OWNER'S OWN animation state (anim_startBlendInOut, flags 0x22, 0.1 s
        in and out) - no store into the clip.
        Then the copy test (owner flag 0x20000, 0x2e0b80).  Only for a real caster: a
        LightEffect 36 above the owner (ONE SHARED DRAW); the owner's action state +0x58c
        = 6; +0x7c = 0; +0x28 = frame; the three beam handles = 0; duration +0x20 = slot
        10 (2, level), radius +0x24 = slot 10 (3, level) x 12 (floats); a particle group."""
        u32, w32 = self.u32, self.w32
        self.spell_base_ctor(spell, level, owner, skill, self.VT_SPELL_ANCESTRALCALL)
        w32(spell + 0x18, owner)
        w32(spell + 0x1C, 0)
        self.call('sound_playOnObject', self.call('res_find', 0x54FBE0, 0x54FBE8), owner, ONE)
        weapon_class = self.s8(self.record(u32(spell + 0x18)) + 0x4A86)
        name = self.call('libc_sprintf', self.ANCESTRAL_CLIPS.get(weapon_class, 0x54FC10), None)
        player = u32(spell + 0x18)
        clip = self.call('res_find', u32(u32(player + 0x24)), name)
        self.call('anim_startBlendInOut', u32(spell + 0x18) + 0x114, clip, 0x22, F_0_1, F_0_1)
        if u32(u32(spell + 0xC) + 0xC) & 0x20000:
            return
        light = self.call('pool_new', 0xBC)
        if light:
            player = u32(spell + 0x18)
            spot = (C.add(u32(player + 0x10), ZERO), u32(player + 0x14), C.add(u32(player + 0x18), 0x42100000))
            self.light_effect(light, spot, ZERO, 0x431B0000, 0x437F0000, 0x43340000, 0x43100000, ZERO, 0x40A00000,
                              a2=player, rest=(0xC2C00000, 0, 0, 0, 0))
        w32(u32(spell + 0x18) + 0x58C, 6)
        w32(spell + 0x7C, 0)
        w32(spell + 0x28, u32(G_SIM_FRAME))
        for k in range(3):
            w32(spell + 0x2C + 4 * k, 0)
        w32(spell + 0x20, C.from_int(self.stat(u32(spell + 8), 2, self.s8(spell))))
        w32(spell + 0x24, C.from_int(s32(self.stat(u32(spell + 8), 3, self.s8(spell)) * 12)))
        w32(spell + 0x80, self.call('particleGroup_create'))

    def ancestralcall_tint_and_glow(self, spell, obj):
        """SpellAncestralCall_tintAndGlow 0x2e15a0 (spell, object): both flash quads =
        (0x2c, 0x30, 0xbe, 0x29) and the model shock effect."""
        for off, value in ((0x92, 0x30), (0x94, 0xBE), (0x9A, 0x30), (0x9C, 0xBE), (0x90, 0x2C), (0x9E, 0x29), (0x98, 0x2C),
                           (0x96, 0x29)):
            self.w16(obj + off, value)
        self.call('fx_shockModel', self.u32(obj + 0x544), obj + 0x114, self.vec(obj + 0x10), self.s16(obj + 0x38),
                  obj + 0x320, 0x5E808080, ONE, ONE, ZERO)

    def ancestralcall_run(self, spell, pos, facing=0):
        """SpellAncestralCall_run 0x2e0d10 (spell, position, facing), slot 2.

          1. clock += 1/60.
          2. While the cast animation plays (+0x7c == 0): Player_animStep(caster; 1.0).
             Animation status +0x11a without bit 0x20: the beam handles = 0, the looping
             sound at caster +0x4a8 stopped and that word = -1, the caster's action state
             = 2, +0x7c = 1.  Otherwise the three beams (from 360 above the run position
             to the run position and the two hands), each created when frame - cast frame
             equals its entry of the table at 0x54fc60 and refreshed while it exists, with
             the sounds of the first two.
          3. The caster is tinted; a ring of level + 14 particles (ONE OWN DRAW each) of
             radius slot 10 (3, level) x 12 round net_objOrGhost(owner) - asked again for
             every particle; every other player of the alive list inside the radius in
             the plane (same team only in PvP mode A, the caster's slot 22) is tinted.
          4. duration < clock: the spell ends itself."""
        u32, w32 = self.u32, self.w32
        here = self.vec(pos)
        w32(spell + 0x1C, C.add(u32(spell + 0x1C), DT))
        if not u32(spell + 0x7C):
            self.call('Player_animStep', u32(spell + 0x18), ONE)
            player = u32(spell + 0x18)
            if not self.u16(player + 0x11A) & 0x20:
                for k in range(3):
                    w32(spell + 0x2C + 4 * k, 0)
                if u32(player + 0x4A8) != M32:
                    self.call('sound_stop', u32(player + 0x4A8))
                    w32(u32(spell + 0x18) + 0x4A8, M32)
                w32(u32(spell + 0x18) + 0x58C, 2)
                w32(spell + 0x7C, 1)
            else:
                first = self.call('model_getAttachPoint', u32(player + 0x544), self.vec(player + 0x10),
                                  self.s16(player + 0x38), player + 0x114, 0, 0, ONE)
                player = u32(spell + 0x18)
                second = self.call('model_getAttachPoint', u32(player + 0x544), self.vec(player + 0x10),
                                   self.s16(player + 0x38), player + 0x114, 1, 0, ONE)
                ends = ((C.add(here[0], ZERO), here[1], here[2]), tuple(first), tuple(second))
                top = (C.add(here[0], ZERO), here[1], C.add(here[2], 0x43B40000))
                for k in range(3):
                    slot = spell + 0x2C + 4 * k
                    if s32(u32(G_SIM_FRAME) - u32(spell + 0x28)) == self.s32(self.ANCESTRAL_BEAM_FRAMES + 4 * k):
                        player = u32(spell + 0x18)
                        if u32(player + 0x4A8) == M32 and k == 0:
                            self.call('sound_playOnObject', self.call('res_find', 0x54FBE0, 0x54FC70), u32(spell + 0x18), ONE)
                            handle = self.call('sound_playOnObject', self.call('res_find', 0x54FBE0, 0x54FC88),
                                               u32(spell + 0x18), ONE)
                            w32(u32(spell + 0x18) + 0x4A8, handle)
                            self.call('sound_release', handle)
                        if k == 1:
                            self.call('sound_playOnObject', self.call('res_find', 0x54FBE0, 0x54FC70), u32(spell + 0x18), ONE)
                        if not u32(slot):
                            w32(slot, self.call('beam_create', top, ends[k], 0x168, 5, 0x5E808080, 0x417E6666, 0x41080000))
                            if not u32(slot):
                                continue
                        self.call('beam_update', u32(slot), top, ends[k], 0x80, 0x168)
                    elif u32(slot):
                        self.call('beam_update', u32(slot), top, ends[k], 0x80, 0x168)
        self.ancestralcall_tint_and_glow(spell, u32(spell + 0x18))
        level = self.s8(spell)
        reach = s32(self.stat(u32(spell + 8), 3, level) * 12)
        self.call('particleGroup_begin', u32(spell + 0x80))
        anchor = self.call('net_objOrGhost', u32(spell + 0xC))
        matrix = C.mat34_set_pos_rot_z(list(self.vec(anchor + 0x10)), s16(u32(G_SIM_FRAME) * 0x43))
        self.call('particleGroup_setMatrix', u32(spell + 0x80), tuple(matrix))
        for _ in range(max(level + 0xE, 0)):
            angle = s16(self.spell_rand(spell))
            ring = [C.mul(C.cos16(angle), C.from_int(reach)), C.mul(C.sin16(angle), C.from_int(reach)), ZERO]
            world = C.mat34_transform_point(matrix, ring)
            ground = self.call('terrain_heightAtPoint', u32(G_WORLD), tuple(world))
            anchor = self.call('net_objOrGhost', u32(spell + 0xC))
            height = C.sub(ground, u32(anchor + 0x18))
            if C.le(height, 0x42900000) and C.le(0xC2900000, height):
                self.call('particle_spawn', self.PDEF_ANCESTRAL_RING, (ring[0], ring[1], height), (0, 0, 0), ZERO)
        self.call('particleGroup_end', u32(spell + 0x80))
        i = 0
        while i < self.s32(G_ALIVE_COUNT):
            obj = u32((G_PLAYERS + self.s32(G_ALIVE_LIST + 4 * i) * REC_SIZE + REC_OBJ) & M32)
            i += 1
            caster = u32(spell + 0x18)
            if not obj or obj == caster:
                continue
            if u32(G_PVP_MODE_A) and not self.vcall(caster, 22, obj):
                continue
            caster = u32(spell + 0x18)
            dy = C.sub(u32(caster + 0x14), u32(obj + 0x14))
            dx = C.sub(u32(caster + 0x10), u32(obj + 0x10))
            if C.lt(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.from_int(s32(reach * reach))):
                self.ancestralcall_tint_and_glow(spell, obj)
        if C.lt(u32(spell + 0x20), u32(spell + 0x1C)):
            self.spell_end(spell)

    def ancestralcall_stat0_fraction(self, spell):
        """0x2e13d0 -> (float) slot 10 (0, level) x 0.01: the damage and attack factor."""
        return C.mul(C.from_int(self.stat(self.u32(spell + 8), 0, self.s8(spell))), F_0_01)

    def ancestralcall_stat1_fraction(self, spell):
        """0x2e1420 -> (float) slot 10 (1, level) x 0.01: the swing-speed factor."""
        return C.mul(C.from_int(self.stat(self.u32(spell + 8), 1, self.s8(spell))), F_0_01)

    def ancestralcall_query_for(self, spell, creature, out0, out1):
        """SpellAncestralCall_queryFor 0x2e1470 (spell, creature, float *damage factor or
        0, float *speed factor or 0) -> 1 when the creature is under this aura: the owner
        itself, or - on the same team in PvP mode A (the OWNER's slot 22) - within slot 10
        (3, level) x 12 of the owner in the plane (inclusive).  0 for no creature.  The
        two outputs are written first, whatever the answer."""
        u32 = self.u32
        reach = self.stat(u32(spell + 8), 3, self.s8(spell))
        if out0:
            self.w32(out0, self.ancestralcall_stat0_fraction(spell))
        if out1:
            self.w32(out1, self.ancestralcall_stat1_fraction(spell))
        if not creature:
            return 0
        owner = u32(spell + 0xC)
        if creature == owner:
            return 1
        if u32(G_PVP_MODE_A):
            if not self.vcall(owner, 22, creature):
                return 0
            owner = u32(spell + 0xC)
        dx = C.sub(u32(creature + 0x10), u32(owner + 0x10))
        dy = C.sub(u32(creature + 0x14), u32(owner + 0x14))
        limit = C.from_int(s32(reach * 12 * reach * 12))
        return 0 if C.lt(limit, C.add(C.mul(dx, dx), C.mul(dy, dy))) else 1


_register(51, 'ancestralcall', {
    'SkillAncestralCall_canUse': (0x2E060C, 0x2E0640, 'skill', 'ancestralcall_can_use'),
    'SkillAncestralCall_cast': (0x2E0750, 0x2E07F0, 'skill', 'ancestralcall_cast'),
    'SpellAncestralCall_ctor': (0x2E09B4, 0x2E0D10, '', 'ancestralcall_spell_ctor'),
    'SpellAncestralCall_run': (0x2E0D10, 0x2E13D0, 'spell', 'ancestralcall_run'),
    'SpellAncestralCall_getStat0Fraction': (0x2E13D0, 0x2E1420, '', 'ancestralcall_stat0_fraction'),
    'SpellAncestralCall_getStat1Fraction': (0x2E1420, 0x2E1470, '', 'ancestralcall_stat1_fraction'),
    'SpellAncestralCall_queryFor': (0x2E1470, 0x2E15A0, '', 'ancestralcall_query_for'),
    'SpellAncestralCall_tintAndGlow': (0x2E15A0, 0x2E1634, '', 'ancestralcall_tint_and_glow'),
}, [(Model.VT_SPELL_ANCESTRALCALL, 'Spell', (1,))])



EXTERNALS.update({
    'SpellGiantGrowth_typeinfo': Ext(0x3D0DA8, '', 0, 'i', 'type-info getter'),
})


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # Can-use (slot 1) of ids 38, 39, 40 and 65 - the four ids of the range whose casts
    # are not modelled here but which have a can-use of their own.  Each is run for the
    # prediction copy too (the cast-start code of Player_run asks before Player_castSkill
    # turns the copy away): none of them stores anything; three can raise a HUD message.
    # =====================================================================================
    def groundpound_can_use(self, skill, caster):
        """SkillGroundPound_canUse 0x2c7140 -> 1 for a caster without the player flag; a
        player needs weapon class 2 (record byte +0x4a86) and, when the active weapon set
        holds an item, one whose definition word +0x20 is 1; else a HUD message for 180
        frames and 0."""
        if not self.u32(caster + 0xC) & 0x40:
            return 1
        rec = self.record(caster)
        allowed = self.s8(rec + 0x4A86) == 2
        item = self.u32((rec + 0x4434 + 4 * self.s8(rec + 0x4A7C)) & M32)
        if item and self.u32(self.u32(item) + 0x20) != 1:
            allowed = False
        if not allowed:
            self.call('hud_showMessage', self.call('text_lookup', 0x54E7A0), 0xB4, self.u32(caster + 0x3C8), 0)
        return 1 if allowed else 0

    def convertenemy_can_use(self, skill, caster):
        """SkillConvertEnemy_canUse 0x2cffb8 -> 1, or 0 with a HUD message (90 frames) for a
        player in PvP mode A."""
        if self.u32(G_PVP_MODE_A) and self.u32(caster + 0xC) & 0x40:
            self.call('hud_showMessage', self.call('text_lookup', 0x54ED70), 0x5A, self.u32(caster + 0x3C8), 0)
            return 0
        return 1

    def convertundead_can_use(self, skill, caster):
        """SkillConvertUndead_canUse 0x2d0a58 -> 0 with a HUD message (90 frames) for a
        player in PvP mode A; otherwise 1 as soon as an entry of world_collectObjectsInBox
        (caster -/+ 329 on all axes, capacity 512) is something the caster's slot 20
        accepts with kind byte +0xb4 == 0x10 (undead); none: a HUD message (180 frames)
        and 0 - the slot word +0x3c8 is read whatever the caster is."""
        u32 = self.u32
        if u32(G_PVP_MODE_A) and u32(caster + 0xC) & 0x40:
            self.call('hud_showMessage', self.call('text_lookup', 0x54EE58), 0x5A, u32(caster + 0x3C8), 0)
            return 0
        here = self.vec(caster + 0x10)
        found = self.call('world_collectObjectsInBox', tuple(C.sub(v, 0x43A48000) for v in here),
                          tuple(C.add(v, 0x43A48000) for v in here), 0x200) or ()
        for other in found:
            if self.vcall(caster, 20, other) and self.s8(other + 0xB4) == 0x10:
                return 1
        self.call('hud_showMessage', self.call('text_lookup', 0x54EE68), 0xB4, u32(caster + 0x3C8), 0)
        return 0

    def giantgrowth_can_use(self, skill, caster):
        """SkillGiantGrowth_canUse 0x308f2c -> 1 unless the caster carries a
        SpellGiantGrowth."""
        return 0 if self.call('creature_findSpellByType', caster, self.call('SpellGiantGrowth_typeinfo')) else 1


_register(38, 'groundpound', {'SkillGroundPound_canUse': (0x2C7140, 0x2C71EC, 'skill', 'groundpound_can_use')})
_register(39, 'convertenemy', {'SkillConvertEnemy_canUse': (0x2CFFB8, 0x2D001C, 'skill', 'convertenemy_can_use')})
_register(40, 'convertundead', {'SkillConvertUndead_canUse': (0x2D0A58, 0x2D0B88, 'skill', 'convertundead_can_use')})
_register(65, 'giantgrowth', {'SkillGiantGrowth_canUse': (0x308F2C, 0x308F60, 'skill', 'giantgrowth_can_use')})



EXTERNALS.update({
    'FlyingText_ctor': Ext(0x202158, 'pviiiiip', 0, 'n', '(block, position, 0, 0, 0, 0, 0, wide text): a floating word; a '
                           'GameObject (ONE SHARED DRAW inside)'),
})
OBJECT_CTORS = OBJECT_CTORS + ('FlyingText_ctor',)


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 39 convertenemy and 40 convertundead: docs/spec/skills-35-68.md sections 39, 40.  Two
    # classes from one template: Skill (tables 0x518928 / 0x5189e0) and Spell (0x78 bytes,
    # tables 0x5189b0 / 0x518a68), which sits on the CASTER and holds its targets in a list.
    #
    #   +0x18 targets (handle list, last found first)   +0x70 u16 spiral angle   +0x74
    #   clock (float; the roll comes when it passes 4.0)   particle groups, one per target:
    #   +0x20.. (id 39) / +0x1c.. (id 40)   the frame of the cast: +0x1c (39) / +0x6c (40)
    # =====================================================================================
    CONVERT = {
        39: dict(table=0x5189B0, frame=0x1C, groups=0x20, sound=(0x54ED98, 0x54EDA0), radius=0x43A68000, arc=0x430B0000,
                 turn=0x172D, tick=0x3DF9A5CA, speed=0x40DB3332, pdef=0x8E5460, resist=0x54EDC0, immune=0x54EDB8),
        40: dict(table=0x518A68, frame=0x6C, groups=0x1C, sound=(0x54EE98, 0x54EEA0), radius=0x43A48000, arc=0x42F00000,
                 turn=0x10BB, tick=0x3E0519EA, speed=0x419FBBBB, pdef=0x8E54B0, resist=0x54EEB8, immune=None),
    }

    def convert_cast(self, sid, skill, level, caster):
        """SkillConvertEnemy_cast 0x2cff1c / SkillConvertUndead_cast 0x2d09bc -> the spell
        or 0: pool_new(0x78) and the constructor (an empty list head in the frame is
        cleared afterwards)."""
        head = self.alloca(4)
        self.mem.poke(head, 4, 0)
        spell = self.call('pool_new', 0x78)
        if spell:
            self.convert_spell_ctor(sid, spell, level, caster, skill)
        self.handle_clear(head)
        return spell

    def convert_spell_ctor(self, sid, spell, level, owner, skill):
        """SpellConvertEnemy_ctor 0x2d0154 / SpellConvertUndead_ctor 0x2d0cc0 (spell,
        level, owner, skill).

        Spell base (ONE SHARED DRAW); the target list empty; the frame; n = slot 10 (0,
        level); angle and clock 0; the sound on the owner.  world_collectObjectsInArc(owner
        position, facing, no filter; 333 and 139 degrees for id 39, 329 and 120 for id
        40; 0), walked in order until n targets are linked: an entry qualifies without
        object flag 0x1000000, without the player flag, with charm timer +0x312 == 0, boss
        rank 0 and charm seconds +0x354 <= 0 - and for id 40 only with kind byte +0xb4 ==
        0x10 (undead; id 40 asks the boss rank BEFORE the charm timer, id 39 after).
        Each: handle_link(spell + 0x18, target) and a particle group."""
        p = self.CONVERT[sid]
        u32, w32 = self.u32, self.w32
        self.spell_base_ctor(spell, level, owner, skill, p['table'])
        w32(spell + 0x18, 0)
        w32(spell + p['frame'], u32(G_SIM_FRAME))
        most = self.stat(skill, 0, self.s8(spell))
        self.w16(spell + 0x70, 0)
        w32(spell + 0x74, 0)
        self.call('sound_playOnObject', self.call('res_find', *p['sound']), u32(spell + 0xC), ONE)
        caster = u32(spell + 0xC)
        head = self.query_list('world_collectObjectsInArc', self.vec(caster + 0x10), self.s16(caster + 0x38), 0,
                               p['radius'], p['arc'], ZERO)
        linked = 0
        if most > 0:
            for other in self.list_objects(head):
                flags = u32(other + 0xC)
                if not flags & 0x1000000 and not flags & 0x40:
                    if sid == 39:
                        fits = self.s16(other + 0x312) == 0 and not self.call('creature_bossRank', other)
                    else:
                        fits = not self.call('creature_bossRank', other) and self.s16(other + 0x312) == 0 \
                            and self.s8(other + 0xB4) == 0x10
                    if fits and C.le(u32(other + 0x354), ZERO):
                        self.handle_link(spell + 0x18, other, other)
                        w32(spell + p['groups'] + 4 * linked, self.call('particleGroup_create'))
                        linked += 1
                if not linked < most:
                    break
        self.handle_clear(head)

    def convert_run(self, sid, spell):
        """SpellConvertEnemy_run 0x2d0354 / SpellConvertUndead_run 0x2d0edc, slot 2.

        seconds = slot 10 (1, level); the angle +0x70 and the clock +0x74 advance.
        Clock <= 4.0: for every target still there, one spiral particle in its own group
        (the group index counts the targets that are still there).
        Clock > 4.0, once: chance = slot 10 (2, level); for every target still there, in
        list order: (id 39 only) an undead - kind byte 0x10 - gets the immunity notice
        (pool_new 0x98, text_lookup, FlyingText: ONE SHARED DRAW) and no roll.  Otherwise
        a target wider than 20 (radius +0x1c) halves the chance (rounded half away from
        zero); ONE SHARED DRAW d: with d % 100 + 1 < chance the target is converted -
        creature flag 0x400000, charm seconds +0x354 = seconds, Creature_setCharm(target,
        seconds x 60, the caster's team byte (record +0x4c24, signed) or -1 for a caster
        that is not a player); else only a wide target gets the resistance notice.  The spell then
        ends itself."""
        p = self.CONVERT[sid]
        u32, w32 = self.u32, self.w32
        seconds = self.stat(u32(spell + 8), 1, self.s8(spell))
        angle = (self.u16(spell + 0x70) + p['turn']) & 0xFFFF
        self.w16(spell + 0x70, angle)
        w32(spell + 0x74, C.add(u32(spell + 0x74), p['tick']))
        spiral = (C.mul(C.cos16(s16(angle)), HALF), C.mul(C.sin16(self.s16(spell + 0x70)), HALF), ZERO)
        waiting = C.le(u32(spell + 0x74), 0x40800000)
        chance = 0 if waiting else self.stat(u32(spell + 8), 2, self.s8(spell))
        index = 0
        for target in self.list_objects(spell + 0x18):
            if not target:
                continue
            if waiting:
                group = u32(spell + p['groups'] + 4 * index)
                matrix = C.mat34_set_pos_rot_z(list(self.vec(target + 0x10)), self.s16(target + 0x38))
                self.call('particleGroup_setMatrix', group, tuple(matrix))
                reach = u32(target + 0x1C)
                point = (C.mul(spiral[0], reach), C.mul(spiral[1], reach), C.mul(u32(spell + 0x74), u32(target + 0x1C)))
                velocity = tuple(C.mul(c, p['speed']) for c in spiral)
                self.call('particleGroup_begin', group)
                self.call('particle_spawn', p['pdef'], point, velocity, ZERO)
                self.call('particleGroup_end', group)
            elif p['immune'] and self.s8(target + 0xB4) == 0x10:
                self._convert_word(target, p['immune'])
                continue
            else:
                wide = C.lt(0x41A00000, u32(target + 0x1C))
                need = C.round_half_away(C.mul(C.from_int(chance), HALF)) if wide else chance
                if self.draw() % 100 + 1 < s32(need):
                    team = M32
                    caster = u32(spell + 0xC)
                    if u32(caster + 0xC) & 0x40:
                        team = self.s8(self.record(caster) + 0x4C24) & M32
                    self.w64(target + 0xA8, self.u64(target + 0xA8) | 0x400000)
                    frames = C.from_int(s32(seconds * 60))
                    w32(target + 0x354, C.mul(frames, DT))
                    self.call('Creature_setCharm', target, C.to_int(frames), team)
                elif wide:
                    self._convert_word(target, p['resist'])
            index += 1
        if not waiting:
            self.spell_end(spell)

    def _convert_word(self, target, key):
        block = self.call('pool_new', 0x98)
        if block:
            text = self.call('text_lookup', key)
            self.object_ctor('FlyingText_ctor', block, self.vec(target + 0x10), 0, 0, 0, 0, 0, text)

    def convertenemy_cast(self, skill, level, caster, pos=0, facing=0):
        return self.convert_cast(39, skill, level, caster)

    def convertenemy_run(self, spell, pos=0, facing=0):
        return self.convert_run(39, spell)

    def convertundead_cast(self, skill, level, caster, pos=0, facing=0):
        return self.convert_cast(40, skill, level, caster)

    def convertundead_run(self, spell, pos=0, facing=0):
        return self.convert_run(40, spell)

    def convertenemy_spell_ctor(self, spell, level, owner, skill):
        return self.convert_spell_ctor(39, spell, level, owner, skill)

    def convertundead_spell_ctor(self, spell, level, owner, skill):
        return self.convert_spell_ctor(40, spell, level, owner, skill)


_register(39, 'convertenemy', {
    'SkillConvertEnemy_cast': (0x2CFF1C, 0x2CFFB8, 'skill', 'convertenemy_cast'),
    'SpellConvertEnemy_ctor': (0x2D0154, 0x2D0354, '', 'convertenemy_spell_ctor'),
    'SpellConvertEnemy_run': (0x2D0354, 0x2D0820, 'spell', 'convertenemy_run'),
}, [(0x5189B0, 'Spell', (1,))])
_register(40, 'convertundead', {
    'SkillConvertUndead_cast': (0x2D09BC, 0x2D0A58, 'skill', 'convertundead_cast'),
    'SpellConvertUndead_ctor': (0x2D0CC0, 0x2D0EDC, '', 'convertundead_spell_ctor'),
    'SpellConvertUndead_run': (0x2D0EDC, 0x2D133C, 'spell', 'convertundead_run'),
}, [(0x518A68, 'Spell', (1,))])



# the third argument of water_test is a pointer (0, or scratch in the caller's frame)
EXTERNALS['water_test'] = Ext(0x189438, 'pvp', 1, 'i', '(world, position, out or 0; radius)')
del EXTERNALS['GroundPoundEffect_ctor']         # modelled below


class Model(Model):                             # noqa: F811
    # =====================================================================================
    # 38 groundpound: docs/spec/skills-35-68.md section 38.  SkillGroundPound (table
    # 0x518298; can-use above) and the object GroundPoundEffect (0x9c bytes, table
    # 0x512218), which Player_run creates on the clip's fourth event - and which the
    # monsters Cazic and Zek build themselves.
    #
    #   +0x38 s16 facing   +0x4c run counter (byte)   +0x4d level (byte)   +0x4f over water
    #   +0x50 the ground is 144 or more away   +0x54 light radius   +0x58 Skill
    #   +0x5c..+0x94 a light record (position +0x8c)   +0x98 owner handle
    # =====================================================================================
    VT_GROUNDPOUND = 0x512218

    def groundpound_cast(self, skill, level, caster, pos=0, facing=0):
        """SkillGroundPound_cast 0x2c71ec -> 0.  Only for a caster with the player flag:
        action state +0x58c = 10; the pound clip of the caster's class lump gets its FOUR
        EVENT SLOTS WRITTEN INTO THE CLIP ITSELF (times 0.25, 0.5, 0.75, 1.4779719 s; masks
        1, 2, 4, 8) - a header shared by every object of the class; the clip is started
        (flags 10, 0.1 s in and out); a sound.  Nothing is created and the level is not
        kept."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        if u32(caster + 0xC) & 0x40:
            w32(caster + 0x58C, 10)
            clip = self.call('res_find', u32(u32(caster + 0x24)), 0x54E7B8)
            w8(clip + 0x20, 2)
            w32(clip + 0x14, 0x3E800000)
            w8(clip + 0x18, 1)
            w32(clip + 0x1C, 0x3F000000)
            w32(clip + 0x24, 0x3F400000)
            w8(clip + 0x28, 4)
            w32(clip + 0x2C, 0x3FBD2E2F)
            w8(clip + 0x30, 8)
            self.call('anim_startBlendInOut', caster + 0x114, clip, 10, F_0_1, F_0_1)
            self.call('sound_playOnObject', self.call('res_find', 0x54E7C8, 0x54E7D0), caster, ONE)
        return 0

    def groundpound_effect_ctor(self, obj, pos, facing, skill, level, owner):
        """GroundPoundEffect_ctor 0x2c74ac (object, position, facing, skill, level, owner).

        GameObject_ctor (ONE SHARED DRAW); the light record at +0x5c (radius 108), linked;
        radius +0x1c = 0; facing, Skill, level byte; a sound on the owner; the owner handle
        +0x98 (with an owner); light radius +0x54 = 108, counter 0; the every-frame run
        list.  The centre: 30 ahead of the position along the facing, on the ground
        (terrain_height, radius 6); +0x50 = the ground is 144 or more from the given
        height; +0x4f = water_test(8.0) there.  Over water +0x50 is cleared and the light
        unlinked; on dry ground with +0x50 the light is unlinked too.  The light is placed
        36 above the centre."""
        u32, w32, w16, w8 = self.u32, self.w32, self.w16, self.w8
        start = self.vec(pos)
        self.game_object_ctor(obj, pos, 0, 0)
        w32(obj + 0x48, self.VT_GROUNDPOUND)
        w8(obj + 0x65, 0)
        self.wvec(obj + 0x8C, start)
        for off, value in ((0x84, 0x38B3CC07), (0x7C, 0x38B3CC07), (0x78, 0x42D80000), (0x80, 0x42D80000), (0x88, 0)):
            w32(obj + off, value)
        for base in (0x6E, 0x66):
            for i, value in enumerate((0xC1, 0x75, 0x39, 0xFFE0)):
                w16(obj + base + 2 * i, value)
        w8(obj + 0x64, 0)
        self.call('light_link', obj + 0x5C)
        w32(obj + 0x98, 0)
        w32(obj + 0x1C, 0)
        w16(obj + 0x38, facing)
        w32(obj + 0x58, skill)
        w8(obj + 0x4D, level)
        self.call('sound_playOnObject', self.call('res_find', 0x54E7C8, 0x54E818), owner, ONE)
        if owner:
            self.handle_link(obj + 0x98, owner, owner)
        w32(obj + 0x54, 0x42D80000)
        w8(obj + 0x4C, 0)
        self.call('obj_runEveryFrame', obj)
        w32(obj + 0x10, C.add(start[0], C.mul(C.cos16(self.s16(obj + 0x38)), 0x41F00000)))
        w32(obj + 0x14, C.add(start[1], C.mul(C.sin16(self.s16(obj + 0x38)), 0x41F00000)))
        ground = self.call('terrain_height', u32(G_WORLD), self.vec(obj + 0x10), 0x40C00000)
        w8(obj + 0x50, 0 if C.lt(C.fabs(C.sub(ground, u32(obj + 0x18))), 0x43100000) else 1)
        w32(obj + 0x18, ground)
        water = self.call('water_test', u32(G_WORLD), self.vec(obj + 0x10), 'stack', 0x41000000)
        w8(obj + 0x4F, water)
        if self.s8(obj + 0x4F):
            w8(obj + 0x50, 0)
            self.call('light_unlink', obj + 0x5C)
        elif self.s8(obj + 0x50):
            self.call('light_unlink', obj + 0x5C)
        self.wvec(obj + 0x8C, (C.add(u32(obj + 0x10), ZERO), u32(obj + 0x14), C.add(u32(obj + 0x18), 0x42100000)))
        self.call('light_relink', obj + 0x5C)

    def _groundpound_stat(self, obj, stat, cap):
        """Statistics 0 and 1: slot 10 without an owner, slot 12 (owner, cap) with one."""
        skill, level = self.u32(obj + 0x58), self.s8(obj + 0x4D)
        if not self.u32(obj + 0x98):
            return self.stat(skill, stat, level)
        return self.stat_for(skill, stat, level, self.u32(self.u32(obj + 0x98) + 0xC), cap)

    def groundpound_effect_run(self, obj):
        """GroundPoundEffect_run 0x2c7808, slot 4.

        First run (counter 0): R = statistic 1 x 12 (slot 12 with the owner and cap 10; slot
        10 without an owner), or 24 when +0x50 is set.  A dust ring of 164 particles, THREE
        OWN DRAWS each; a LightEffect 24 ahead (ONE SHARED DRAW inside); 60 burst particles
        and, without +0x50, 23 (46 over water) debris particles, a decal or a water
        disturbance and camera_shake(level x 0.715 + 5) - all from the PER-MACHINE generator
        0x404468.  Then the damage: every entry of world_collectObjectsInBox(centre -/+ R,
        capacity 512) - only while the owner handle holds something - that the owner's slot
        20 accepts and that is nearer in the plane than R + its radius: d = statistic 0
        (slot 12, cap 0); damage_apply(entry, owner, 100000, flags 0x80100, no descriptor,
        0; max(1, round(0.8 d)), max(1, round(1.2 d))); a creature left with hit points >=
        0 costs ONE OWN DRAW r and is stunned (slot 30, slot 10 (3) x 60 frames, 1) when
        100 - slot 10 (2) < r % 100 + 1.
        Counter 30: obj_delete.
        Every run: a spark while the counter is below 4 (dry ground, no +0x50) or a ripple
        over water (0x404468 again); the light's radius = +0x54, which loses 3.8957684 a
        run down to 0; counter += 1."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        here = lambda: self.vec(obj + 0x10)
        unit3 = lambda: self.unit(self.seed3_draw())
        counter = self.s8(obj + 0x4C)
        if counter == 0:
            reach = C.from_int(s32(self._groundpound_stat(obj, 1, 10) * 12))
            if self.s8(obj + 0x50):
                reach = F_24
            for angle in range(0, 0x10000, 400):
                x = C.add(u32(obj + 0x10), C.mul(C.cos16(s16(angle)), reach))
                point = (x, C.add(u32(obj + 0x14), C.mul(C.sin16(s16(angle)), reach)), C.add(u32(obj + 0x18), F_12))
                vx = C.mul(C.mul(C.sub(self.unit(self.obj_rand(obj)), HALF), F_12), 0x3E5CF548)
                vy = C.mul(C.mul(C.sub(self.unit(self.obj_rand(obj)), HALF), F_12), 0x3E5CF548)
                vz = C.mul(C.mul(self.unit(self.obj_rand(obj)), F_12), 0x401F9F81)
                self.call('particle_spawn', 0x8E4D80, point, (vx, vy, vz), ZERO)
            front = (C.add(C.mul(C.cos16(self.s16(obj + 0x38)), F_24), u32(obj + 0x10)),
                     C.add(C.mul(C.sin16(self.s16(obj + 0x38)), F_24), u32(obj + 0x14)), C.add(u32(obj + 0x18), ZERO))
            light = self.call('pool_new', 0xBC)
            if light:
                self.light_effect(light, front, 0x43410000, 0x42EA0000, 0x42640000, 0x41100000, ZERO, 0x3F4CCCCC, 0x3E999999,
                                  rest=(0xC2000000, 0x43410000, 0x42EA0000, 0x42640000, 0xC2000000))
            angle = 0
            definition = 0x8E4EC0 if C.lt(reach, 0x43180000) else 0x8E4F10 if C.lt(reach, 0x43680000) else 0x8E4F60
            for _ in range(0x3C):
                velocity = (C.mul(C.cos16(angle), 0x42C80000), C.mul(C.sin16(angle), 0x42C80000), C.mul(unit3(), 0x41A00000))
                self.call('particle_spawn', definition, front, velocity, F_0_1)
                angle = s16(angle + 0x444)
            if not self.s8(obj + 0x50):
                wet = self.s8(obj + 0x4F)
                for _ in range(0x2E if wet else 0x17):
                    vx = C.mul(C.mul(C.sub(unit3(), HALF), F_12), 0x3F9DDDDD)
                    vy = C.mul(C.mul(C.sub(unit3(), HALF), F_12), 0x3F9DDDDD)
                    vz = C.mul(C.mul(unit3(), F_12), 0x40733332)
                    self.call('particle_spawn', 0x8E4E70 if self.s8(obj + 0x4F) else 0x8E4DD0, here(), (vx, vy, vz), ZERO)
            shake = False
            if not self.s8(obj + 0x4F):
                if not self.s8(obj + 0x50):
                    self.seed3_draw()
                    self.call('decal_add', here(), s32(u32(G_SEED3)) >> 16, 9, 0, F_12)
                    shake = not self.s8(obj + 0x50)
            else:
                self.call('water_disturb', u32(G_WORLD), here(), 0x455F5000, 0x42100000)
                shake = not self.s8(obj + 0x50)
            if shake:
                self.call('camera_shake', 0, C.add(C.mul(C.from_int(self.s8(obj + 0x4D)), 0x3F3709C7), 0x40A00000))
            centre = here()
            found = self.call('world_collectObjectsInBox', tuple(C.sub(v, reach) for v in centre),
                              tuple(C.add(v, reach) for v in centre), 0x200) or ()
            for other in found:
                node = u32(obj + 0x98)
                if not node or not self.vcall(u32(node + 0xC), 20, other):
                    continue
                dy = C.sub(u32(obj + 0x14), u32(other + 0x14))
                dx = C.sub(u32(obj + 0x10), u32(other + 0x10))
                if not C.lt(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), C.add(reach, u32(other + 0x1C))):
                    continue
                amount = C.from_int(self._groundpound_stat(obj, 0, 0))
                low = max(s32(C.round_half_away(C.sub(amount, C.mul(amount, 0x3E4CCCCC)))), 1)
                high = max(s32(C.round_half_away(C.add(amount, C.mul(amount, 0x3E4CCCCC)))), 1)
                self.call('damage_apply', other, u32(u32(obj + 0x98) + 0xC), 100000, 0, 0, 0x80100, 0, 0,
                          C.from_int(low), C.from_int(high))
                if u32(other + 0xC) & 0x20 and C.le(ZERO, u32(other + 0x228)):
                    roll = self.obj_rand(obj)
                    chance = self.stat(u32(obj + 0x58), 2, self.s8(obj + 0x4D))
                    if 100 - chance < roll % 100 + 1:
                        frames = self.stat(u32(obj + 0x58), 3, self.s8(obj + 0x4D))
                        self.vcall(other, 30, s32(frames * 60), 1)
        elif counter == 0x1E:
            self.call('obj_delete', obj)
        if not self.s8(obj + 0x4F):
            if not self.s8(obj + 0x50) and self.s8(obj + 0x4C) < 4:
                b = self.ball(self.seed3_draw)
                self.call('particle_spawn', 0x8E4E20, here(), tuple(C.mul(c, 0x40400000) for c in b), ZERO)
        if self.s8(obj + 0x4F):
            x = C.add(u32(obj + 0x10), C.mul(C.sub(unit3(), HALF), 0x42480000))
            y = C.add(u32(obj + 0x14), C.mul(C.sub(unit3(), HALF), 0x42480000))
            self.call('water_disturb', u32(G_WORLD), (x, y, C.sub(u32(obj + 0x18), 0x42100000)), 0x455BC000, 0x40A00000)
        radius = u32(obj + 0x54)
        w32(obj + 0x78, radius)
        w32(obj + 0x80, radius)
        inverse = C.div(ONE, C.mul(radius, radius))
        w32(obj + 0x84, inverse)
        w32(obj + 0x7C, inverse)
        radius = C.sub(u32(obj + 0x54), 0x40795445)
        w32(obj + 0x54, radius)
        if C.lt(radius, ZERO):
            w32(obj + 0x54, 0)
        w8(obj + 0x4C, self.u8(obj + 0x4C) + 1)


_register(38, 'groundpound', {
    'SkillGroundPound_cast': (0x2C71EC, 0x2C72EC, 'skill', 'groundpound_cast'),
    'GroundPoundEffect_ctor': (0x2C74AC, 0x2C7808, '', 'groundpound_effect_ctor'),
    'GroundPoundEffect_run': (0x2C7808, 0x2C843C, 'object', 'groundpound_effect_run'),
}, [(Model.VT_GROUNDPOUND, 'Creature', (1,))])

MODELLED = {name: start for name, (start, _end) in FUNCTIONS.items()}
