#!/usr/bin/env python3
"""ref_arena_monsters.py - reference model of the monster classes of the evil-path Drundar
arena (level DRUNARE) of Champions: Return to Arms (SLUS_209.73, US v2.00).

A research tool, not game code.  It sits on top of tools/ref_creature.py (the creature base
class) and adds, as methods of Model:

    Horsemen (the knights UndeadKnight1-4; also the mounted Rider* of another level)
        horsemen_ctor        0x271c70      horsemen_run         0x27236c
        horsemen_set_state   0x272f4c
    Skelight (the skeleton the fourth knight summons)
        skelight_ctor        0x2a8770      skelight_run         0x2a8b84
        skelight_set_state   0x2a91b8      skelight_shatter     0x2a946c
    Zek (RalosZek, the speaker of the last cutscene; a full boss class)
        zek_ctor             0x2c1f94      zek_run              0x2c2440
        zek_take_damage      0x2c34e4      zek_set_state        0x2c382c
        zek_slot35           0x2c3c54
    the pieces of the creature base class these three use and tools/ref_creature.py left out
        creature_ctor        0x109d68      set_def_entry_params 0x118378
        turn_to_target       0x1187e0      can_see_target_in    0x118d40
        is_target_charging   0x118f90      count_allies_near_target 0x119258
        is_blocked_by_target 0x118f08      slot25_can_see_target    0x10e658
        slot28_on_death      0x10beb8      slot16_model         0x3c2738
        slot34_set_home_range 0x3c2708
        is_not_rooted 0x1195e0, is_attack_ready 0x1195f0, is_not_stunned 0x119608
    the two skills whose cast the knights' run function reaches and that touch the shared
    seed in the caster's tick - Summon Skeleton with its spell, and Tagar's Insects with
    its spell's per-tick run (which executes inside the casting knight's Creature_run)
        summon_can_use       0x2e2368      summon_cast          0x2e18a4
        summon_spell_ctor    0x2e16ec      summon_spell_run     0x2e177c
        tagar_cast           0x30c708      tagar_spell_ctor     0x30c95c
        tagar_spell_run      0x30cbc8      tagar_tick_victims   0x30d558
        tagar_pick_target    0x30d998      tagar_is_valid       0x30db9c
        spell_rand           0x16a964

Every method was written from the instructions at the address in its docstring and is
compared with that code, executed under tools/ee_emu.py, by tools/difftest_arena_monsters.py.
docs/spec/arena-monsters.md is the prose version and says what the comparison covers.
Standard library only; no game data is embedded: strings, tables and class definitions are
named by address and read through the memory the caller supplies.  (ArenaScript at the end
is the one exception in kind: a model of the level's script, it carries that script's own
entry and variable names and its three frame counts.)

How it sees the game: exactly as tools/ref_creature.py does - a memory image (load/store),
callbacks for everything outside the model (EXTERNALS below extends that module's list),
canonical arguments (integers as unsigned 32-bit, floats as patterns, a vector as a tuple of
three patterns).  A virtual call is resolved through the table at object +0x48: when the
function found there is one this module or the base model has, its method runs; anything
else is the callback 'Creature.v<slot>'.  The same rule serves the weapon holder (table at
holder +0, callbacks 'Holder.v<slot>'), skills (table at skill +0x60, 'Skill.v<slot>') and
spells (table at spell +0x14, 'Spell.v<slot>').

Call-outs to what other models own: anim_start / anim_startBlendInOut / anim_push /
anim_clear / anim_syncToSimFrame / anim_advance (tools/ref_anim.py), Creature_setStats and
damage_apply behind the hit helpers (tools/ref_combat.py), GameObject_ctor, pool_new, the
name table and the run lists (tools/ref_core.py, tools/ref_objects.py), terrain_height and
world_findFreeSpot (tools/ref_world.py).

Shared-seed draws made by this code itself (Model.draws counts them):
    summon_cast 1 or 2, summon_spell_ctor 1, tagar_spell_ctor 1, tagar_spell_run 1 on
    each arrival.
No function of Horsemen, Skelight or Zek draws from the shared seed itself; they draw from
the object's own generator (+0x44).  The cosmetic generator 0x404460 is drawn by
summon_cast only (particles).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
from ref_creature import Ext, M32, M64, s8, s16, s32, s64      # noqa: E402,F401

# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
G_RAND_SEED = RC.G_RAND_SEED                    # 0x404464 shared seed (in the sync hash)
G_COSMETIC_SEED = 0x404460                      # presentation generator (per machine)
G_SIM_FRAME = RC.G_SIM_FRAME
G_WORLD = RC.G_WORLD
G_LEVEL_MONSTER_LEVEL = RC.G_LEVEL_MONSTER_LEVEL
G_LEVEL_NAME = 0x44FE18                         # current level name (text)
G_SERIAL_COUNTER = 0x4F85C4                     # u8: next creature serial (+0x230)
G_SCRIPT_SELECTED = 0x4039F8                    # object a death script runs for
G_PVP_MODE_B = 0x4F7120
G_ITEM_MODELS = 0x3E9CE0                        # 16-byte rows; +8 the model the holder update is given
G_SKELIGHT_STATIC = 0x8E4560                    # 8 bytes Skelight's set-state 0x14 zeroes
G_ZEK_SPARK_DEF, G_ZEK_SPARK_READY = 0x8E4BA0, 0x503748
G_SUMMON_PARTICLES = (0x8E5C80, 0x8E5CD0)
G_SUMMON_PLAYER_NAMES, G_SUMMON_MONSTER_NAME = 0x503778, 0x503788     # pointers to object names
G_SUMMON_PLAYER_PROPS, G_SUMMON_MONSTER_PROPS = 0x503750, 0x503770    # property lists
# skill objects the run functions cast through (pointers)
G_SKILL_DISEASEBOLT, G_SKILL_FIRESTORM = 0x41B180, 0x41B18C           # skills 4 and 7
G_SKILL_SUMMONSKELETON, G_SKILL_TAGARSINSECTS = 0x41B19C, 0x41B2CC    # skills 11 and 87
G_SKILL_GROUNDPOUND = 0x41B208                                        # skill 38

VT_CREATURE, VT_CREATURE_SUB = 0x50CC58, 0x50D010
VT_HORSEMEN, VT_SKELIGHT, VT_ZEK = 0x515730, 0x5174B0, 0x5180C8
VT_HOLDER_BASE, VT_WEAPON1, VT_WEAPONSHIELD = 0x512148, 0x50CF40, 0x50CDA0
VT_SPELL, VT_SPELL_SUMMON, VT_SPELL_TAGAR, VT_SPELL_MARKER = 0x515BA0, 0x519918, 0x51BA60, 0x51BA90
DEF_HORSEMEN, DEF_SKELIGHT, DEF_ZEK = 0x5006E8, 0x502728, 0x503688    # class definitions
NIGHTMARE_DATA = 0x500848                       # the mount's property list, 12 bytes per variant

# strings (addresses only)
S_WAIT, S_HIDE, S_SHOWNAME, S_DEAD = 0x52F9F0, 0x52F9F8, 0x52FA00, 0x52FA10
S_HOMERANGE, S_POINTBLANK, S_VISUALRANGE, S_VISUALARC = 0x52FA18, 0x52FA28, 0x52FA38, 0x52FA48
S_SCALE, S_MINIBOSS, S_IGNOREDAMAGE = 0x52FA58, 0x52FA60, 0x52FA70
S_LIGHT1, S_LIGHT2, S_AMBIENT = 0x52FA80, 0x52FA88, 0x52FA90
S_DEATHSCRIPT, S_DROPITEM = 0x52FBF8, 0x52FC08
S_SKELE_LUMP, S_NIGHTMARE, S_SKELIGHTM = 0x547310, 0x547380, 0x547420
S_BLOMEDAL, S_ZEK_LEVEL = 0x54C080, 0x54E5F8
S_FX_LUMP_ZEK, S_ZEK_WAVE_SOUND, S_ZEK_CLANG = 0x54E558, 0x54E560, 0x54E5D8
S_FX_LUMP_SUMMON, S_SUMMON_SOUND = 0x54FDD0, 0x54FDD8
S_FX_LUMP_TAGAR, S_TAGAR_SOUND, S_TAGAR_HIT_SOUND = 0x552428, 0x552430, 0x552460

# float patterns
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16
F_0_1, F_0_2, F_0_3 = 0x3DCCCCCC, 0x3E4CCCCC, 0x3E999999
F_36, F_48, F_72, F_84, F_400 = 0x42100000, 0x42400000, 0x42900000, 0x42A80000, 0x43C80000

# The original functions this module implements (name -> address);
# tools/difftest_arena_monsters.py runs exactly these (and ref_creature.MODELLED) for real.
MODELLED = {
    'Horsemen_ctor': 0x271C70, 'Horsemen_run': 0x27236C, 'Horsemen_setState': 0x272F4C,
    'Skelight_ctor': 0x2A8770, 'Skelight_run': 0x2A8B84, 'Skelight_setState': 0x2A91B8,
    'Skelight_shatter': 0x2A946C,
    'Zek_ctor': 0x2C1F94, 'Zek_run': 0x2C2440, 'Zek_takeDamage': 0x2C34E4, 'Zek_setState': 0x2C382C,
    'Zek_slot35': 0x2C3C54,
    'Creature_ctor': 0x109D68, 'creature_setDefEntryParams': 0x118378,
    'Creature_turnToTarget': 0x1187E0, 'Creature_canSeeTargetIn': 0x118D40,
    'Creature_isTargetCharging': 0x118F90, 'Creature_countAlliesNearTarget': 0x119258,
    'Creature_isBlockedByTarget': 0x118F08, 'Creature_canSeeTarget': 0x10E658,
    'Creature_onDeath': 0x10BEB8, 'Creature_default_slot16': 0x3C2738, 'Creature_default_slot34': 0x3C2708,
    'SkillSummonSkeleton_canUse': 0x2E2368, 'SkillSummonSkeleton_cast': 0x2E18A4,
    'SpellSummonSkeleton_ctor': 0x2E16EC, 'SpellSummonSkeleton_run': 0x2E177C,
    'SkillTagarsInsects_cast': 0x30C708, 'SpellTagarsInsects_ctor': 0x30C95C,
    'SpellTagarsInsects_run': 0x30CBC8, 'SpellTagarsInsects_tickVictims': 0x30D558,
    'SpellTagarsInsects_pickTarget': 0x30D998, 'SpellTagarsInsects_isValidTarget': 0x30DB9C,
    'Spell_rand': 0x16A964,
}

# virtual bodies of Creature-derived objects this module has: function -> (slot, method)
CLASS_BODIES = {
    0x27236C: (4, 'horsemen_run'), 0x272F4C: (27, 'horsemen_set_state'),
    0x2A8B84: (4, 'skelight_run'), 0x2A91B8: (27, 'skelight_set_state'),
    0x2C2440: (4, 'zek_run'), 0x2C382C: (27, 'zek_set_state'), 0x2C34E4: (2, 'zek_take_damage'),
    0x2C3C54: (35, 'zek_slot35'),
    0x3C2738: (16, 'slot16_model'), 0x10E658: (25, 'slot25_can_see_target'),
    0x10BEB8: (28, 'slot28_on_death'), 0x3C2708: (34, 'slot34_set_home_range'),
}
# skill bodies (table at skill +0x60) and spell bodies (table at spell +0x14)
SKILL_BODIES = {
    0x2E2368: (1, 'summon_can_use'), 0x2E18A4: (2, 'summon_cast'), 0x30C708: (2, 'tagar_cast'),
}
SPELL_BODIES = {0x2E177C: (2, 'summon_spell_run'), 0x30CBC8: (2, 'tagar_spell_run')}

EXTERNALS = dict(RC.EXTERNALS)
EXTERNALS.update({
    # --- creature base class, not modelled anywhere yet
    'Creature_applyKnockback': Ext(0x115EB8, 'p', 1, 'n', '(creature; scale)'),
    'Creature_deadUpdate': Ext(0x1108A0, 'pivi', 1, 'n', '(creature, event bits, vector, flag; 20.0)'),
    'Creature_dropLoot': Ext(0x10F2C8, 'pvii', 6, 'n', '(creature, position, facing, 0; six floats)'),
    'Creature_hitTargetInArc': Ext(0x119938, 'piiiiiii', 2, 'i',
                                   '(creature, facing, arc, min, max, attack rating, damage flags, weapon '
                                   'descriptor; near, far) -> hit'),
    'Creature_hitAllEnemiesInArc': Ext(0x119B58, 'piiiiiii', 2, 'i', 'same arguments; every enemy in the arc'),
    'creature_canSeeObj': Ext(0x10C810, 'ppiii', 3, 'i', '(creature, object, facing, arc, ray mode; near, far, lead)'),
    'creature_findEnemyInCone': Ext(0x10CF78, 'pii', 2, 'i', '(creature, facing, arc; near, far) -> object or 0'),
    'creature_countAlliesNear': Ext(0x10D800, 'pv', 1, 'i', '(creature, position; radius) -> count'),
    'creature_isBlockedBy': Ext(0x10D2A8, 'pp', 0, 'i', '(creature, other)'),
    'creature_addSpell': Ext(0x11A838, 'pp', 0, 'n', '(creature, spell or 0)'),
    'creature_stopBossMusic': Ext(0x1192F8, 'p', 0, 'n'),
    'Creature_setCharm': Ext(0x1189F0, 'pii', 0, 'n', '(creature, frames or -1, team)'),
    'Creature_setStats': Ext(0x10A620, 'pi', 5, 'n', '(creature, roll hit points; hp, armour, damage, attack, exp)'),
    'Creature_init': Ext(0x10A230, 'p', 0, 'n', 'post-constructor set-up (height, properties, initScript)'),
    'balance_lookup': Ext(0x223A4C, 'pwwwww', 0, 'i', '(type name) -> found, five factors (float patterns)'),
    # --- objects
    'GameObject_ctor': Ext(0x14CB10, 'pvpp', 0, 'n', '(object, position, class definition, property list)'),
    'obj_moveOffGrid': Ext(0x14EF48, 'p', 0, 'n'),
    'obj_runEvery60': Ext(0x14F2B8, 'p', 0, 'n'),
    'world_findObjectByName': Ext(0x14F498, 'p', 0, 'i', '(name) -> object or 0'),
    'loot_spawnNamedItem': Ext(0x100BA0, 'vp', 0, 'n', '(position, item descriptor text)'),
    'arena_addKill': Ext(0x3056CC, 'pi', 0, 'n', '(killer object or 0, 0)'),
    'lump_load': Ext(0x173558, 'p', 0, 'n', '(lump name)'),
    'Nightmare_ctor': Ext(0x270968, 'ppvip', 0, 'n', '(block, type name, position, facing, property list)'),
    'GroundPoundEffect_ctor': Ext(0x2C74AC, 'pvipip', 0, 'n', '(block, position, facing, skill, level, owner)'),
    'LightEffect_ctor': Ext(0x201BD8, 'pvii', 8, 'n', '(block, position, 0, 0; eight floats; four more on the stack)'),
    'particleDef_ctor': Ext(0x18F3D0, 'piiiiiii', 3, 'n', '(definition, seven integers; three floats; five on the stack)'),
    # --- animation (tools/ref_anim.py)
    'anim_start': Ext(0x16CFE0, 'ppi', 1, 'n', '(state, clip, flags; blend seconds)'),
    'anim_startBlendInOut': Ext(0x16CEB0, 'ppi', 2, 'n', '(state, clip, flags; blend in, blend out)'),
    'anim_push': Ext(0x170838, 'ppi', 0, 'n', '(state, clip, flags)'),
    'anim_clear': Ext(0x1707B0, 'p', 0, 'n'),
    'anim_syncToSimFrame': Ext(0x1709F8, 'p', 0, 'n'),
    'anim_jumpTopToEnd': Ext(0x170BC8, 'p', 0, 'n'),
    # --- model
    'model_buildHideMask': Ext(0x179550, 'pi', 0, 'q', '(model, variant bits) -> 64-bit show mask'),
    'model_getSamplePointCount': Ext(0x1799C8, 'p', 0, 'i'),
    'model_getSamplePoint': Ext(0x178E18, 'ppviioOi', 1, 'n', '(model, anim state, position, facing, index, out, '
                                'second out or 0, 0; 1.0)'),
    # --- effects, sound, world
    'fx_ringBurst': Ext(0x1F3D00, 'v', 1, 'n', '(position; 4.0)'),
    'combat_applyAreaDamage': Ext(0x1097F8, 'pviiii', 2, 'n', '(attacker, position, min, max, flags, 0; inner, radius)'),
    'sound_playAtPos': Ext(0x214428, 'pv', 1, 'n', '(entry, position; volume)'),
    'terrain_height': Ext(0x183820, 'pv', 1, 'f', '(world, position; 12.0) -> ground height'),
    'res_find': Ext(0x17365C, 'pS', 0, 'i', '(lump name, entry name) -> entry'),
    # --- virtual calls
    'Creature.v16': Ext(0, 'p', 0, 'i', 'model'),
    'Creature.v25': Ext(0, 'pi', 0, 'i', 'can see target (force)'),
    'Creature.v28': Ext(0, 'pi', 0, 'n', 'on death (0)'),
    'Creature.v34': Ext(0, 'pi', 0, 'n', 'set home range'),
    'Holder.v1': Ext(0, 'pii', 0, 'n', '(hand, model entry): put an item model in a hand'),
    'Holder.v2': Ext(0, 'pi', 0, 'n', 'fire weapon (0)'),
    'Holder.v4': Ext(0, 'pi', 0, 'n', 'cold weapon (0)'),
    'Holder.v6': Ext(0, 'pi', 0, 'n', 'shock weapon (0)'),
    'Holder.v11': Ext(0, 'pipii', 0, 'n', '(hand, creature, 0, 0): drop the held part as a physics prop'),
    'Holder.v15': Ext(0, 'pi', 0, 'i', '(hand) -> model entry it holds'),
    'Holder.v17': Ext(0, 'pi', 0, 'i', '(hand) -> the hand\'s damage descriptor'),
    'Holder.v21': Ext(0, 'ppp', 1, 'n', '(class definition, creature; 0.5): per-frame update'),
    'Holder.v22': Ext(0, 'ppp', 1, 'n', '(item model, creature; 0.5): per-frame update'),
    'Skill.v1': Ext(0, 'pp', 0, 'i', 'can use (caster)'),
    'Skill.v2': Ext(0, 'pipvi', 0, 'i', 'cast (level, caster, position, facing) -> spell or 0'),
    'Skill.v12': Ext(0, 'piipi', 0, 'i', 'statistic (index, level, caster, cap)'),
    'Skill.v14': Ext(0, 'pii', 0, 'i', '(level, 0x14) -> level'),
    'Spell.v1': Ext(0, 'pi', 0, 'n', 'destroy (3)'),
    # --- the insects spell
    'creature_findSpell': Ext(0x11A788, 'pip', 0, 'i', '(creature, skill id, caster) -> the marker spell or 0'),
    'world_collectInSphere': Ext(0x14AB80, 'viL', 1, 'n', '(centre, heading, list out; radius) -> objects'),
    'world_collectObjectsInArc': Ext(0x1614F0, 'viLp', 3, 'n', '(centre, heading, list out, owner; radius, '
                                     'arc in degrees, 0.0) -> objects, nearest first'),
    'Skill.v8': Ext(0, 'piiiww', 1, 'n', '(statistic, level, 0; spread) -> low, high'),
})
EXTERNALS['LightEffect_ctor'].stack = 4
EXTERNALS['particleDef_ctor'].stack = 5


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row (see ref_creature.shape_result;
    this copy knows the rows added here, the kind 'S', the kind 'L' - a list head the callee
    fills with a chain of nodes, handed back as a list of objects - and the 64-bit result
    kind 'q')."""
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
        if kind in 'ipvelsSOW':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


def half_toward_zero(value):
    """C's  x / 2  on a signed 16-bit value (0x2c2a2c: add the sign bit, shift right)."""
    value = s16(value)
    return (value + (1 if value < 0 else 0)) >> 1


def third_toward_zero(value):
    """C's  x / 3  on a signed 16-bit value (0x272938)."""
    value = s16(value)
    return -((-value) // 3) if value < 0 else value // 3


class Model(RC.Model):
    """The arena's monster classes on a memory image.  See the module docstring."""

    # ---- plumbing ----------------------------------------------------------------------
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48: a body of CLASS_BODIES runs here, a base
        body of ref_creature runs there, anything else is the callback 'Creature.v<slot>'."""
        table = self.u32(obj + 0x48)
        function = self.u32(table + 8 * slot + 4)
        body = CLASS_BODIES.get(function)
        if body is not None and ('Creature.v%d' % slot) not in self.external:
            this = (obj + self.s16(table + 8 * slot)) & M32
            return getattr(self, body[1])(this, *args)
        return RC.Model.vcall(self, obj, slot, *args)

    def skill_call(self, skill, slot, *args):
        """A virtual call on a skill object (table pointer at +0x60)."""
        table = self.u32(skill + 0x60)
        this = (skill + self.s16(table + 8 * slot)) & M32
        body = SKILL_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Skill.v%d' % slot) not in self.external:
            return getattr(self, body[1])(this, *args)
        return self.call('Skill.v%d' % slot, this, *args)

    def table_call(self, cls, obj, table_offset, slot, *args):
        """As ref_creature's, except that a spell body of SPELL_BODIES runs here (so a
        spell attached to a creature runs inside that creature's Creature_run)."""
        if cls == 'Spell':
            table = self.u32(obj + table_offset)
            body = SPELL_BODIES.get(self.u32(table + 8 * slot + 4))
            if body is not None and ('Spell.v%d' % slot) not in self.external:
                return getattr(self, body[1])((obj + self.s16(table + 8 * slot)) & M32, *args)
        return RC.Model.table_call(self, cls, obj, table_offset, slot, *args)

    def spell_rand(self, spell):
        """Spell_rand 0x16a964: the spell's own generator at +0x10."""
        seed = (self.u32(spell + 0x10) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(spell + 0x10, seed)
        return seed >> 16

    def holder_call(self, holder, slot, *args):
        """A virtual call on a weapon holder (table pointer at +0): always a callback."""
        return self.table_call('Holder', holder, 0, slot, *args)

    def cosmetic_draw(self):
        """One draw from the presentation generator 0x404460 (per machine)."""
        seed = (self.u32(G_COSMETIC_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_COSMETIC_SEED, seed)
        return seed >> 16

    def cstr(self, addr, limit=64):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(addr + len(out))
            if not b:
                break
            out.append(b)
        return bytes(out)

    def class_model(self, c):
        """The model pointer of the class definition (+0x24 -> +0xc)."""
        return self.u32(self.u32(c + 0x24) + 0xC)

    def clip(self, c, offset):
        """An animation handle of the class definition: the word at definition + offset
        (entry k of the definition keeps its pointer at +8k+4, so offset 0x1c is entry 3)."""
        return self.u32(self.u32(c + 0x24) + offset)

    def set_state(self, c, state):
        return self.vcall(c, 27, state)

    def weapon_descriptor(self, c):
        """The damage descriptor of hand 1 of the weapon holder at +0x50 (holder slot 17),
        or 0 without a holder: the last argument of a full-damage hit."""
        holder = self.u32(c + 0x50)
        return self.holder_call(holder, 17, 1) if holder else 0

    # =====================================================================================
    # Pieces of the creature base class
    # =====================================================================================
    def is_not_rooted(self, c):
        """Creature_isNotRooted 0x1195e0 -> 1 when the root timer +0x314 is 0."""
        return 1 if self.s16(c + 0x314) == 0 else 0

    def is_attack_ready(self, c):
        """Creature_isAttackReady 0x1195f0 -> 1 when the attack cooldown +0x318 is 0.  It
        first ZEROES the cooldown of a creature that has no target."""
        if not self.u32(c + 0x234):
            self.w16(c + 0x318, 0)
        return 1 if self.s16(c + 0x318) == 0 else 0

    def is_not_stunned(self, c):
        """Creature_isNotStunned 0x119608 -> 1 when the stun timer +0x31c is 0."""
        return 1 if self.s16(c + 0x31C) == 0 else 0

    def slot16_model(self, c):
        """Slot 16, 0x3c2738 -> the model of the class definition."""
        return self.class_model(c)

    def slot34_set_home_range(self, c, value):
        """Slot 34, 0x3c2708 (creature, value): HomeRange +0x3c0 = the low 16 bits of the
        value, unsigned, as a float.  What script setMonsterVal(name, 4, value) reaches."""
        self.w32(c + 0x3C0, C.from_int(value & 0xFFFF))

    def turn_to_target(self, c):
        """Creature_turnToTarget 0x1187e0 -> 0.  With a target: slot 26 (creature, 0, the
        target's position)."""
        node = self.u32(c + 0x234)
        if node:
            self.vcall(c, 26, 0, self.vec(self.u32(node + 0xC) + 0x10))
        return 0

    def can_see_target_in(self, c, facing, arc, ray_mode, near, far, lead):
        """Creature_canSeeTargetIn 0x118d40 (creature, facing, arc, ray mode; near, far, lead)
        -> 0 without a target, else whatever creature_canSeeObj answers for the target.
        Facing and arc are narrowed to signed 16 bits on the way."""
        node = self.u32(c + 0x234)
        if not node:
            return 0
        return self.call('creature_canSeeObj', c, self.u32(node + 0xC), s16(facing), s16(arc), ray_mode,
                         near, far, lead)

    def is_target_charging(self, c):
        """Creature_isTargetCharging 0x118f90 -> 1 when the target faces this creature
        (bearing from the creature to the target, minus the target's facing, within
        -0x3fff..+0x3fff - the difference is NOT wrapped to 16 bits) and its last move
        velocity (+0x308, +0x30c, written by Creature_moveBy) is faster than 100."""
        node = self.u32(c + 0x234)
        if not node:
            return 0
        t = self.u32(node + 0xC)
        bearing = C.atan2_16(C.sub(self.u32(t + 0x14), self.u32(c + 0x14)),
                             C.sub(self.u32(t + 0x10), self.u32(c + 0x10)))
        t = self.u32(self.u32(c + 0x234) + 0xC)
        if not ((bearing - self.s16(t + 0x38) + 0x3FFF) & M32) < 0x7FFF:
            return 0
        vy, vx = self.u32(t + 0x30C), self.u32(t + 0x308)
        speed = C.sqrt(C.add(C.mul(vx, vx), C.mul(vy, vy)))
        return 1 if C.lt(0x42C80000, speed) else 0

    def count_allies_near_target(self, c, radius):
        """Creature_countAlliesNearTarget 0x119258 (creature; radius) -> 0 without a target,
        else creature_countAlliesNear(creature, the target's position; radius)."""
        node = self.u32(c + 0x234)
        if not node:
            return 0
        return self.call('creature_countAlliesNear', c, self.vec(self.u32(node + 0xC) + 0x10), radius)

    def is_blocked_by_target(self, c):
        """Creature_isBlockedByTarget 0x118f08 -> 0 without a target, else
        creature_isBlockedBy(creature, target)."""
        node = self.u32(c + 0x234)
        if not node:
            return 0
        return self.call('creature_isBlockedBy', c, self.u32(node + 0xC))

    def slot25_can_see_target(self, c, force):
        """Slot 25, Creature_canSeeTarget 0x10e658 (creature, force) -> 0 or 1.

        Two tests of the target with creature_canSeeObj: any direction within
        pointblankrange +0x3ac, then inside visualarc +0x3b0 around the facing within
        visualrange +0x3ae.  The ray mode handed down is 1 when `force` is non-zero or the
        visual arc is 0x7fff (which is what any damage sets it to), else 0."""
        mode = 1 if force else 0
        if self.u16(c + 0x3B0) == 0x7FFF:
            mode = 1
        near = C.from_int(self.u16(c + 0x3AC))
        node = self.u32(c + 0x234)
        seen = self.call('creature_canSeeObj', c, self.u32(node + 0xC), 0, 0x7FFF, mode, ZERO, near, ZERO) \
            if node else 0
        if seen:
            return 1
        far = C.from_int(self.u16(c + 0x3AE))
        node = self.u32(c + 0x234)
        if not node:
            return 0
        seen = self.call('creature_canSeeObj', c, self.u32(node + 0xC), self.s16(c + 0x38), self.s16(c + 0x3B0),
                         mode, ZERO, far, ZERO)
        return 1 if seen else 0

    def slot28_on_death(self, c, quiet):
        """Slot 28, Creature_onDeath 0x10beb8 (creature, quiet).

        Clears the follower bits 0x8c00000 of the creature flags; runs the `deathScript`
        property as a level script with the creature as the selected object; unless
        `quiet`, spawns the `dropitem` property as a named item at the creature; a hidden
        creature (object flag 2) is finished at once (flag 0x4000, the animation jumps to
        its end, obj_delete); in PvP mode B the kill is credited; the boss music stops."""
        self.w64(c + 0xA8, self.u64(c + 0xA8) & 0xFFFFFFFFF73FFFFF)
        script = self.call('obj_getPropStr', c, S_DEATHSCRIPT, 0)
        if script:
            self.w32(G_SCRIPT_SELECTED, c)
            self.call('script_runByName', script)
            self.w32(G_SCRIPT_SELECTED, 0)
        if not quiet:
            item = self.call('obj_getPropStr', c, S_DROPITEM, 0)
            if item:
                self.call('loot_spawnNamedItem', self.vec(c + 0x10), item)
        flags = self.u32(c + 0xC)
        if flags & 2:
            self.w32(c + 0xC, flags | 0x4000)
            self.call('anim_jumpTopToEnd', c + 0x114)
            self.call('obj_delete', c)
        if self.u32(G_PVP_MODE_B):
            self.call('arena_addKill', self.handle_obj(c + 0x2E4), 0)
        self.call('creature_stopBossMusic', c)

    def set_def_entry_params(self, c, entry, masks, times):
        """creature_setDefEntryParams 0x118378 (creature, entry, four masks; four times):
        writes up to four (time, event mask) pairs into animation entry `entry` of the
        CLASS definition (shared by every object of the class): time k at entry record
        +0x14 + 8k, mask k (one byte) at +0x18 + 8k.  The masks are the event bits
        Creature_stepAnim returns when the clip passes that time."""
        for k in range(4):
            record = self.u32(self.u32(c + 0x24) + 8 * entry + 4)
            self.w8(record + 0x18 + 8 * k, masks[k])
            self.w32(record + 0x14 + 8 * k, times[k])

    def creature_ctor(self, c, type_name, pos, facing, class_def, props, hp):
        """Creature_ctor 0x109d68 (creature, type name or 0, position, facing, class
        definition, property list; placeholder hit points).

        GameObject_ctor (a callback: it draws the object's own seed from the shared seed
        and registers the name), the base tables, zeroed AI fields, home = position, the
        serial byte from a global counter, then the level-record properties, in this
        order: wait (inert bit 1), hide (inert bit 8, off the grid, object flag 0x8000),
        ShowName, Dead (1000 pending damage), HomeRange (default 1000), pointblankrange
        (300), visualrange (500), visualarc (0x4000), Scale (percent), MiniBoss (creature
        flag 1), IgnoreDamage (flag bit 48), light1 / light2 / ambient (flag 0x40000000).
        With a type name: Creature_setStats with the five factors balance_lookup finds for
        it (all 1.0 when it finds none), rolling hit points."""
        w32, w16, w8, prop = self.w32, self.w16, self.w8, self._prop_int
        self.call('GameObject_ctor', c, pos, class_def, props)
        w32(c + 0x50, 0)
        w32(c + 0x48, VT_CREATURE)
        w32(c + 0x4C, VT_CREATURE_SUB)
        w8(c + 0x119, 8)
        for off in (0x2F4, 0x2EC, 0x2F0, 0x234, 0x238, 0x2E4, 0x360, 0x364):
            w32(c + off, 0)
        self.wvec(c + 0x3B4, pos)
        w16(c + 0x38, facing)
        w32(c + 0x22C, hp)
        self.w64(c + 0x220, M64)
        w32(c + 0xC, self.u32(c + 0xC) | 0x20)
        w32(c + 0xC8, 0)
        w32(c + 0x228, hp)
        w32(c + 0x23C, M32)
        w32(c + 0x240, M32)
        for off in (0x2BC, 0x2C0, 0x2DC, 0xF4, 0x2C4, 0x300):
            w32(c + off, 0)
        for off in (0x110, 0x31C, 0x312, 0x316):
            w16(c + off, 0)
        w8(c + 0x231, 0)
        w8(c + 0x2FC, 0)
        w8(c + 0x310, 0xFF)
        w8(c + 0x5A, 0xFF)
        w8(c + 0xA0, 0)
        w32(c + 0x3C, self.u32(c + 0x18))
        w32(c + 0xDC, ONE)
        w16(c + 0x58, 0xFFFF)
        w16(c + 0x3C4, 600)
        for off in (0xB8, 0x304, 0xE0, 0x2D8):
            w32(c + off, 0)
        for off in (0x314, 0x31A, 0x318):
            w16(c + off, 0)
        serial = self.u8(G_SERIAL_COUNTER)
        w8(G_SERIAL_COUNTER, serial + 1)
        w8(c + 0x230, serial)
        if prop(c, S_WAIT):
            w8(c + 0x231, self.u8(c + 0x231) | 1)
        if prop(c, S_HIDE):
            w8(c + 0x231, self.u8(c + 0x231) | 8)
            self.call('obj_moveOffGrid', c)
            w32(c + 0xC, self.u32(c + 0xC) | 0x8000)
        if self.call('obj_getPropStr', c, S_SHOWNAME, 0):
            w32(c + 0x368, self.call('obj_getPropStr', c, S_SHOWNAME, 0))
            w32(c + 0xC, self.u32(c + 0xC) | 0x100000)
        if prop(c, S_DEAD):
            w32(c + 0xC8, 0x447A0000)
        w32(c + 0x3C0, 0x447A0000)
        if prop(c, S_HOMERANGE):
            w32(c + 0x3C0, C.from_int(s32(prop(c, S_HOMERANGE))))
        for off, name, default in ((0x3AC, S_POINTBLANK, 300), (0x3AE, S_VISUALRANGE, 500), (0x3B0, S_VISUALARC, 0x4000)):
            w16(c + off, default)
            if prop(c, name):
                w16(c + off, prop(c, name))
        if prop(c, S_SCALE):
            w32(c + 0xDC, C.mul(C.from_int(s32(prop(c, S_SCALE))), 0x3C23D70A))
        if prop(c, S_MINIBOSS):
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 1)
        if prop(c, S_IGNOREDAMAGE):
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x1000000000000)
        if self.call('obj_getPropStr', c, S_LIGHT1, 0) or self.call('obj_getPropStr', c, S_LIGHT2, 0) \
                or self.call('obj_getPropStr', c, S_AMBIENT, 0):
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x40000000)
        if type_name:
            w32(c + 0x34, type_name)
            found, f_hp, f_armour, f_damage, f_attack, f_exp = self.call('balance_lookup', type_name)
            if found:
                self.call('Creature_setStats', c, 1, f_hp, f_armour, f_damage, f_attack, f_exp)
            else:
                self.call('Creature_setStats', c, 1, ONE, ONE, ONE, ONE, ONE)
        w16(c + 0x2FA, self.u16(c + 0x38))

    def _prop_int(self, c, name):
        return self.call('obj_getPropInt', c, name, 0)

    def _init_holder(self, c, holder, final_table=None):
        """The embedded weapon holder: table, two bytes, and its hand tables cleared
        (0x271d00-0x271d78 for Horsemen; the same code at 0x2a87dc and 0x2c2004).  The
        hand block starts 0x50 bytes into the holder."""
        w16, w8 = self.w16, self.w8
        self.w32(holder, VT_HOLDER_BASE)
        w8(holder + 4, 0)
        self.w32(holder, VT_WEAPON1)
        w8(holder + 8, 0)
        block = holder + 0x50
        for k in range(4):
            w16(block + 0x24 + 8 * k, 0xFFFF)
        w8(block + 0x21, 0xFF)
        w8(block + 0x20, 0xFF)
        for k in range(4):
            w16(block + 0x10 + 2 * k, 0)
            w16(block + 0x18 + 2 * k, 0)
        if final_table is not None:
            w8(holder + 0x98, 0)
            self.w32(holder, final_table)

    # =====================================================================================
    # Horsemen
    # =====================================================================================
    HORSEMEN_EVENTS = (
        (3, (1, 1, 0, 0), (F_0_2, 0x3F199999, 0, 0)),             # clip +0x1c, state 6
        (4, (1, 1, 1, 0), (F_0_2, 0x3F199999, ONE, 0)),           # clip +0x24, state 7
        (5, (2, 0, 0, 0), (F_0_3, 0, 0, 0)),                      # clip +0x2c, state 10: event bit 1 only
        (6, (1, 1, 1, 0), (F_0_3, 0x3F4CCCCC, 0x3FCCCCCC, 0)),    # clip +0x34, state 0xb
        (0xE, (1, 0, 0, 0), (HALF, 0, 0, 0)),                     # clip +0x74, state 8
        (8, (1, 0, 0, 0), (0x40000000, 0, 0, 0)),                 # clip +0x44, state 0x17 (the cast)
        (0x11, (1, 0, 0, 0), (F_0_2, 0, 0, 0)),                   # clips +0x8c, +0x94, +0x9c, +0xc4:
        (0x12, (1, 0, 0, 0), (F_0_2, 0, 0, 0)),                   #   the mounted swings 0x20-0x22, 0x1f
        (0x13, (1, 0, 0, 0), (F_0_2, 0, 0, 0)),
        (0x18, (1, 0, 0, 0), (F_0_2, 0, 0, 0)),
        (0xF, (0x80, 0, 0, 0), (F_0_1, 0, 0, 0)),                 # clip +0x7c, the death clip
    )

    def horsemen_ctor(self, c, type_name, pos, facing, props, variant, mounted):
        """Horsemen_ctor 0x271c70 (object, type name, position, facing, property list,
        variant 0-3, mounted).

        Creature_ctor with class definition 0x5006e8; a WeaponShield holder embedded at
        +0x3d0 with model entries 2v+0x1b in hand 1 and 2v+0x23 in hand 2; radius 20, turn
        rate 1.2, kind 9, scale 1.2, creature flags |= 0x2020020000 (metal body, no gibs,
        bit 37), resistances +0x5c 0.2, +0x64 1.0, +0x68 1.0, +0x6c 0.3.  ONE OWN DRAW sets
        the first cast time +0x474 = clock + 480 + draw % 120.  Variant 3 loads the
        skeleton's lump.  Event times of eleven clips (HORSEMEN_EVENTS).  It joins a
        60-frame run list.  With `mounted`: a Nightmare is built at the same place and
        linked both ways through +0x3c8, and the knight enters state 0x1b."""
        w32, w16, w8 = self.w32, self.w16, self.w8
        variant &= M32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_HORSEMEN, props, 0x41200000)
        holder = c + 0x3D0
        w32(c + 0x48, VT_HORSEMEN)
        w32(c + 0x3C8, 0)
        self._init_holder(c, holder, VT_WEAPONSHIELD)
        w8(c + 0x28, 0x30)
        w32(c + 0x1C, 0x41A00000)
        w32(c + 0xB8, 0)
        w32(c + 0xB0, 0x3F999999)
        w16(c + 0x232, 0)
        w8(c + 0xB4, 9)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        w32(c + 0x50, holder)
        self.holder_call(holder, 1, 1, (2 * variant + 0x1B) & 0xFF)
        holder = self.u32(c + 0x50)
        if holder:
            self.holder_call(holder, 1, 2, (2 * variant + 0x23) & 0xFF)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x2020020000)
        w32(c + 0xDC, 0x3F999999)
        w16(c + 0x472, 0)
        w32(c + 0x5C, F_0_2)
        w32(c + 0x68, ONE)
        w32(c + 0x64, ONE)
        w32(c + 0x6C, F_0_3)
        draw = self.obj_rand(c)
        w8(c + 0x470, variant)
        bits = (1 << (variant & 31)) & M32
        w32(c + 0xE8, bits)
        w32(c + 0x474, self.u32(c + 0x300) + draw % 120 + 480)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), bits))
        if self.s8(c + 0x470) == 3:
            self.call('lump_load', S_SKELE_LUMP)
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x54), 1)
        self.call('obj_runEvery60', c)
        for entry, masks, times in self.HORSEMEN_EVENTS:
            self.set_def_entry_params(c, entry, masks, times)
        if mounted:
            block = self.call('pool_new', 0x3D8)
            if block:
                self.call('Nightmare_ctor', block, S_NIGHTMARE, self.vec(c + 0x10), self.s16(c + 0x38),
                          NIGHTMARE_DATA + 12 * self.s8(c + 0x470))
                self.call('handle_link', c + 0x3C8, block, block)
                self.call('handle_link', block + 0x3C8, c, c)
                self.horsemen_set_state(c, 0x1B)
        self.call('Creature_init', c)

    def horsemen_run(self, c):
        """Horsemen_run 0x27236c (creature): one tick.

        Head: the weapon holder's per-frame update (holder slot 21), then for a knight on
        foot Creature_processDamage, Creature_run, Creature_updateActive, Creature_stepAnim
        (speed 1.0), Creature_applyKnockback (0.5), slot 23 pick target; for a mounted one
        the mount's position and facing are copied first, the knock-back and the target
        pick are left out and the mount's target is taken over.  Then the switch on the AI
        state (see docs/spec/arena-monsters.md section 3); at most one set-state per tick
        from the switch itself.  Every random choice is the knight's own generator."""
        u32, st = self.u32, self.set_state
        holder = u32(c + 0x50)
        if holder:
            self.holder_call(holder, 21, u32(c + 0x24), c, HALF)
        if not u32(c + 0x3C8):
            self.process_damage(c, self.class_model(c))
            if self.run(c, self.class_model(c)):
                return
            self.update_active(c)
            ev = self.step_anim(c, ONE)
            self.call('Creature_applyKnockback', c, HALF)
            self.vcall(c, 23, 0)
        else:
            mount = u32(u32(c + 0x3C8) + 0xC)
            self.wvec(c + 0x10, self.vec(mount + 0x10))
            self.w16(c + 0x38, self.u16(u32(u32(c + 0x3C8) + 0xC) + 0x38))
            self.call('obj_updateGridCell', c)
            self.process_damage(c, self.class_model(c))
            if self.run(c, self.class_model(c)):
                return
            self.update_active(c)
            ev = self.step_anim(c, ONE)
            theirs = u32(u32(u32(c + 0x3C8) + 0xC) + 0x234)
            if theirs:
                mine = u32(c + 0x234)
                if not mine or u32(theirs + 0xC) != u32(mine + 0xC):
                    self.call('handle_clear', c + 0x234)
                    target = u32(u32(u32(u32(c + 0x3C8) + 0xC) + 0x234) + 0xC)
                    self.call('handle_link', c + 0x234, target, target)
        state = self.s16(c + 0x232)
        facing = lambda: self.s16(c + 0x38)                      # noqa: E731  (re-read at every use)
        see = lambda arc, far: self.can_see_target_in(c, facing(), arc, 0, ZERO, far, ZERO)   # noqa: E731
        playing = lambda mask=8: self.u16(c + 0x11A) & mask      # noqa: E731

        if state == 0:                                           # 0x272534 idle
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
            if self.s32(c + 0xF4) < self.s32(c + 0x300):         # idled long enough: wander
                return st(c, 1)
            return
        if state == 1:                                           # 0x272598 walk home / wander
            if self.vcall(c, 25, 0):
                return st(c, 0)                                  # sees its target: back to idle FIRST
            self.move_to_dest(c)
            return
        if state == 3:                                           # 0x2725cc chase
            if not u32(c + 0x234):
                return st(c, 0)
            if see(10000, F_36):
                return st(c, 5)
            if see(6000, F_36) and self.is_target_charging(c):
                return st(c, 8)
            if see(10000, F_400) and s32(self.count_allies_near_target(c, F_36)) > 0:
                return st(c, 5)
            if self.s32(c + 0x474) < self.s32(c + 0x300) and self.u8(c + 0x470) < 3:
                if self.call('creature_findEnemyInCone', c, facing(), 6000, ZERO, F_400):
                    return st(c, 0x17)
            if self.s8(c + 0x470) == 3:                          # the summoner: no timer, only "can use"
                if self.skill_call(u32(G_SKILL_SUMMONSKELETON), 1, c):
                    return st(c, 0x17)
            self.move_to_target(c)
            return
        if state == 5:                                           # 0x27273c between attacks
            if not self.is_not_rooted(c):
                if see(10000, F_36):
                    return st(c, 6)
                return
            if see(10000, F_36):
                if self.obj_rand(c) & 1 and self.is_blocked_by_target(c):
                    return st(c, 10)
                return st(c, 6 if self.obj_rand(c) & 1 else 7)
            if see(3000, F_72):
                return st(c, 0xB)
            if self.obj_rand(c) % 60:
                return
            if s32(self.count_allies_near_target(c, F_36)) > 0:
                return
            return st(c, 3)
        if state in (6, 7, 10, 0xB):                             # 0x272888 swings
            self.move_by(c, (0, 0, 0))
            if u32(c + 0x234):
                if ev & 1:
                    desc = self.weapon_descriptor(c)
                    self.call('Creature_hitTargetInArc', c, facing(), 10000, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 8, desc, ZERO, F_36)
                elif ev & 2:
                    self.call('Creature_hitTargetInArc', c, facing(), 10000, third_toward_zero(self.s16(c + 0xD0)),
                              third_toward_zero(self.s16(c + 0xD2)), self.s16(c + 0xD4), 0x100001, 0, ZERO, F_36)
                self.turn_to_target(c)
            if playing():
                return
            return st(c, 3)
        if state == 8:                                           # 0x272994 the heavy swing
            self.move_by(c, (0, 0, 0))
            if u32(c + 0x234):
                if ev & 1:
                    desc = self.weapon_descriptor(c)
                    self.call('Creature_hitTargetInArc', c, facing(), 10000, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 0x40008, desc, ZERO, F_36)
                self.turn_to_target(c)
            if playing():
                return
            return st(c, 3)
        if state == 0x10:                                        # 0x272d2c cooldown: retreat
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
            return
        if state in (0x11, 0x18):                                # 0x272cc0, 0x272cdc wait for the clip
            if playing():
                return
            return st(c, 3)
        if state == 0x12:                                        # 0x272cf8 hit reaction
            if playing(0x10):
                return
            return st(c, 3)
        if state == 0x13:                                        # 0x272d14 stunned
            if not self.is_not_stunned(c):
                return
            return st(c, 3)
        if state == 0x14:                                        # 0x272d50 dead
            self.call('Creature_deadUpdate', c, ev, (0, 0, 0), 0, 0x41A00000)
            return
        if state == 0x17:                                        # 0x272a50 the cast
            if u32(c + 0x234):
                if ev & 1:
                    self._horsemen_cast(c)
                    self.w32(c + 0x474, u32(c + 0x300) + self.obj_rand(c) % 120 + 480)
                self.turn_to_target(c)
            if playing():
                return
            return st(c, 3)
        if state == 0x19:                                        # 0x272d88
            self.move_by(c, (0, 0, 0))
            return
        if state == 0x1A:                                        # 0x272db0 countdown +0x472
            if self.s16(c + 0x472) > 0:
                self.w16(c + 0x472, self.u16(c + 0x472) - 1)
            return
        if 0x1B <= state <= 0x1E:                                # 0x272f28 riding: nothing
            return
        if 0x1F <= state <= 0x22:                                # 0x272dc8 mounted swings
            if not u32(c + 0x234) or not ev & 1:
                return
            desc = self.weapon_descriptor(c)
            self.call('Creature_hitAllEnemiesInArc', c, s16(self.u16(c + 0x38) - 0x4000), 10000, self.s16(c + 0xD0),
                      self.s16(c + 0xD2), self.s16(c + 0xD4), 8, desc, ZERO, F_36)
            return
        if state == 0x23:                                        # 0x272e50 dismount hand-over
            self.move_by(c, (0, 0, 0))
            flags = self.u16(c + 0x11A)
            if flags & 0x98 == 0x88:                             # ended, still queued, no reaction clip
                self.w8(c + 0x118, 0)
                self.w16(c + 0x11A, flags & 0xFF7F)
                self.call('anim_push', c + 0x114, self.clip(c, 0x84), 0x14)
            elif flags & 0x90 == 0x90:
                self.call('anim_start', c + 0x114, self.clip(c, 0x54), 3, ZERO)
            if playing(0x18):
                return
            return st(c, 0)
        return st(c, 0)                                          # 0x272f0c: 2, 4, 9, 0xc-0xf, 0x15, 0x16, others

    def _horsemen_cast(self, c):
        """The four casts of state 0x17 (0x272a64-0x272c74), by the variant byte +0x470
        (signed): 0 skill 4 from chest height, 1 skill 7 at the target, 2 skill 87 on
        itself (the spell is attached), 3 skill 11 at its own position (the spell is
        dropped).  The level is slot 35.  Any other variant casts nothing."""
        u32 = self.u32
        variant = self.s8(c + 0x470)
        if variant == 0:
            level = self.vcall(c, 35)
            lift = C.mul(u32(c + 0x20), HALF)
            pos = (C.add(u32(c + 0x10), ZERO), u32(c + 0x14), C.add(u32(c + 0x18), lift))
            self.skill_call(u32(G_SKILL_DISEASEBOLT), 2, level, c, pos, self.s16(c + 0x38))
        elif variant == 1:
            level = self.vcall(c, 35)
            target = u32(u32(c + 0x234) + 0xC)
            self.skill_call(u32(G_SKILL_FIRESTORM), 2, level, c, self.vec(target + 0x10), self.s16(c + 0x38))
        elif variant == 2:
            level = self.vcall(c, 35)
            spell = self.skill_call(u32(G_SKILL_TAGARSINSECTS), 2, level, c, self.vec(c + 0x10), self.s16(c + 0x38))
            self.call('creature_addSpell', c, spell)
        elif variant == 3:
            level = self.vcall(c, 35)
            self.skill_call(u32(G_SKILL_SUMMONSKELETON), 2, level, c, self.vec(c + 0x10), self.s16(c + 0x38))

    def horsemen_set_state(self, c, state):
        """Horsemen_setState 0x272f4c (creature, state): slot 27.

        Creature_filterState first (it may refuse or redirect).  Creature flag 0x200 is
        cleared on every accepted call.  A MOUNTED knight ignores every request below
        0x19 after that (so it cannot be put in the death state).  Then per state: the
        clip of the class definition, and

          0     object flags 9 (dead, no-collide) cleared, idle until clock + own draw % 120,
                the mount handle dropped
          1     path cleared, a wander destination picked
          0x11  creature flag 0x200 set
          0x12  ignored (the state stays) while a state-6 swing is still playing, and
                for a mounted knight
          0x14  creature flag bit 41; variant 3 sends the object named `skelightm`, if it
                is a monster, to state 0x14; Creature_dropLoot; both hands dropped (holder
                slot 11); the death clip; slot 28 (on death)
          0x19 / 0x1a / 0x1b  object flags |= 0xb / &= ~2 / |= 9
          0x23  the mount handle dropped and the knight lifted 48 units
          2, 4, 9, 0xc-0xf, 0x15, 0x16 and anything from 0x24 up: a nested set-state 3,
                after which the REQUESTED number is stored as the state all the same."""
        u32, w32 = self.u32, self.w32
        refused, state = self.filter_state(c, state)
        if refused:
            return
        mount = u32(c + 0x3C8)
        self.w64(c + 0xA8, self.u64(c + 0xA8) & 0xFFFFFFFFFFFFFDFF)
        if mount and state < 0x19:
            return
        anim = c + 0x114
        start = lambda off, flags, blend=F_0_1: self.call('anim_start', anim, self.clip(c, off), flags, blend)  # noqa: E731
        swing = lambda off, flags: self.call('anim_startBlendInOut', anim, self.clip(c, off), flags, F_0_1, F_0_1)  # noqa: E731
        swings = {6: (0x1C, 0x808), 7: (0x24, 0x808), 8: (0x74, 0x808), 10: (0x2C, 0x808), 0xB: (0x34, 0x808),
                  0x17: (0x44, 0x808), 0x18: (0x64, 0x808), 0x20: (0x8C, 8), 0x21: (0x94, 8), 0x22: (0x9C, 8)}
        loops = {5: 0x3C, 0x1C: 0xD4, 0x1D: 0xCC, 0x1E: 0xBC, 0x1F: 0xC4}
        if state == 0:
            w32(c + 0xC, u32(c + 0xC) & 0xFFFFFFF6)
            w32(c + 0xF4, u32(c + 0x300) + self.obj_rand(c) % 120)
            start(0x54, 3)
            if u32(c + 0x3C8):
                self.call('handle_clear', c + 0x3C8)
                w32(c + 0x3C8, 0)
        elif state in (1, 3, 0x10):
            self.clear_path(c)
            if state == 1:
                self.pick_wander_dest(c)
            start(0x6C, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state in loops:
            start(loops[state], 3)
        elif state in swings:
            swing(*swings[state])
        elif state == 0x11:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200)
            start(0x3C, 3)
        elif state == 0x12:
            if (self.s16(c + 0x232) == 6 and self.u16(c + 0x11A) & 8) or mount:
                state = self.s16(c + 0x232)
            else:
                swing(0x4C, 0x10)
        elif state == 0x13:
            if mount:
                state = self.s16(c + 0x232)
            else:
                start(0x54, 3, F_0_3)
        elif state == 0x14:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x20000000000)
            if self.s8(c + 0x470) == 3:
                pet = self.call('world_findObjectByName', S_SKELIGHTM)
                if pet and u32(pet + 0xC) & 0x20:
                    self.vcall(pet, 27, 0x14)
            self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), 0,
                      F_36, 0x40000000, 0x3FE66666, 0x3F199999, 0x40000000, 0x3E800000)
            holder = u32(c + 0x50)
            if holder:
                self.holder_call(holder, 11, 1, c, 0, 0)
                holder = u32(c + 0x50)
            if holder:
                self.holder_call(holder, 11, 2, c, 0, 0)
            start(0x7C, 6)
            self.vcall(c, 28, 0)
        elif state == 0x19:
            w32(c + 0xC, u32(c + 0xC) | 0xB)
            start(0xA4, 3)
        elif state == 0x1A:
            w32(c + 0xC, u32(c + 0xC) & 0xFFFFFFFD)
            start(0xA4, 3)
        elif state == 0x1B:
            w32(c + 0xC, u32(c + 0xC) | 9)
            start(0xA4, 3)
        elif state == 0x23:
            start(0xB4, 0x80C)
            if u32(c + 0x3C8):
                self.call('handle_clear', c + 0x3C8)
                w32(c + 0x3C8, 0)
                z = C.add(u32(c + 0x18), F_48)
                w32(c + 0x3C, z)
                w32(c + 0x18, z)
        else:
            self.vcall(c, 27, 3)
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Skelight
    # =====================================================================================
    def skelight_ctor(self, c, pos, facing, props, level):
        """Skelight_ctor 0x2a8770 (object, position, facing, property list, level).

        Creature_ctor with no type name (so no statistics there) and class definition
        0x502728; a Weapon1 holder embedded at +0x3c8 with model entry 4 in hand 1; radius
        12, turn rate 1.5, creature flags |= 0x10000 (bone body), +0x64 = +0x68 = 1.0.  The
        level is stored at +0x460 and written, as a float, over g_levelMonsterLevel for the
        length of ONE call: Creature_setStats(1.33, 1.2, 1.2, 1.0, e) rolling hit points,
        with e = 0.0 when the level name is `blomedal` (compared without case) and 1.0
        everywhere else; then the global is put back.  It enters state 0x17 (rise), joins
        the every-frame run list, sets two clips' event times, runs Creature_init, and
        ends with kind 0x10 and the ACTIVE bit 63 set."""
        w32, w16, w8 = self.w32, self.w16, self.w8
        self.creature_ctor(c, 0, pos, s16(facing), DEF_SKELIGHT, props, 0x41200000)
        holder = c + 0x3C8
        w32(c + 0x48, VT_SKELIGHT)
        self._init_holder(c, holder)
        w8(c + 0x28, 0x14)
        w32(c + 0xB0, 0x3FC00000)
        w32(c + 0x1C, 0x41400000)
        w32(c + 0xB8, 0)
        w16(c + 0x232, 0)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x10000)
        w32(c + 0x68, ONE)
        w32(c + 0x64, ONE)
        w32(c + 0x50, holder)
        self.holder_call(holder, 1, 1, 4)
        w32(c + 0x460, level)
        saved = self.u32(G_LEVEL_MONSTER_LEVEL)
        w32(G_LEVEL_MONSTER_LEVEL, C.from_int(s32(level)))
        in_blomedal = self.cstr(G_LEVEL_NAME).lower() == self.cstr(S_BLOMEDAL).lower()
        self.call('Creature_setStats', c, 1, 0x3FAA3D70, 0x3F999999, 0x3F999999, ONE, ZERO if in_blomedal else ONE)
        w32(G_LEVEL_MONSTER_LEVEL, saved)
        w32(c + 0xE8, 0)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), 0))
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x3C), 0xC)
        self.skelight_set_state(c, 0x17)
        self.call('obj_runEveryFrame', c)
        self.set_def_entry_params(c, 3, (1, 0, 0, 0), (F_0_3, 0, 0, 0))
        self.set_def_entry_params(c, 4, (1, 1, 0, 0), (F_0_3, ONE, 0, 0))
        self.call('Creature_init', c)
        w8(c + 0xB4, 0x10)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000000000000000)

    def skelight_run(self, c):
        """Skelight_run 0x2a8b84 (creature): one tick.

        Creature_processDamage is SKIPPED while the state is 0x17 (rising), so hits taken
        then wait.  Creature_run, Creature_updateActive (result unused), the weapon holder
        (slot 15 with 1 -> row of g_itemModels, then slot 22 with that row's model),
        Creature_stepAnim(1.0), Creature_applyKnockback(0.7), slot 23, then the switch."""
        u32, st = self.u32, self.set_state
        if self.s16(c + 0x232) != 0x17:
            self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        self.update_active(c)
        holder = u32(c + 0x50)
        row = (s32(self.holder_call(holder, 15, 1)) << 4) if holder else 0
        holder = u32(c + 0x50)
        item_model = u32((G_ITEM_MODELS + row + 8) & M32)
        if holder:
            self.holder_call(holder, 22, item_model, c, HALF)
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, 0x3F333333)
        self.vcall(c, 23, 0)
        state = self.s16(c + 0x232)
        if state == 0:                                           # 0x2a8d14
            if self.vcall(c, 25, 1):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
            return
        if state == 1:                                           # 0x2a8d58
            if self.vcall(c, 25, 1):
                return st(c, 3)
            self.move_to_dest(c)
            return
        if state == 3:                                           # 0x2a8d94 chase
            if not u32(c + 0x234):
                return st(c, 0)
            if self.can_see_target_in(c, self.s16(c + 0x38), 6000, 0, ZERO, F_48, ZERO):
                return st(c, 6)
            if self.can_see_target_in(c, 0, 0x7FFF, 0, ZERO, F_36, ZERO):
                self.turn_to_target(c)
            else:
                self.move_to_target(c)
            return
        if state == 5:                                           # 0x2a8e20
            if self.can_see_target_in(c, self.s16(c + 0x38), 6000, 0, ZERO, F_48, ZERO):
                return st(c, 6)
            if self.is_not_rooted(c):
                return st(c, 3)
            return
        if state == 6:                                           # 0x2a8e6c the swing
            count_down = True
            if u32(c + 0x234):
                if ev & 1:
                    desc = self.weapon_descriptor(c)
                    self.call('Creature_hitTargetInArc', c, self.s16(c + 0x38), 6000, self.s16(c + 0xD0),
                              self.s16(c + 0xD2), self.s16(c + 0xD4), 8, desc, ZERO, F_48)
                if self.u16(c + 0x11A) & 8:
                    self.turn_to_target(c)
                    count_down = not self.u16(c + 0x11A) & 8
            else:
                count_down = not self.u16(c + 0x11A) & 8
            if count_down:
                self.w32(c + 0xF4, u32(c + 0xF4) - 1)
            if self.s32(c + 0xF4) > 0:
                return
            return st(c, 3)
        if state == 0x10:                                        # 0x2a8f4c
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
            return
        if state == 0x12:                                        # 0x2a8f28
            return st(c, 3)
        if state == 0x13:                                        # 0x2a8f34
            if not self.is_not_stunned(c):
                return
            return st(c, 0)
        if state == 0x14:                                        # 0x2a8f90
            self.call('Creature_deadUpdate', c, ev, (0, 0, 0), 1, 0x41A00000)
            return
        if state == 0x17:                                        # 0x2a8cb8 rising
            if self.u16(c + 0x11A) & 0x80:
                st(c, 0)
            self.call('fx_spawn', 7, self.vec(c + 0x10))
            return
        return                                                   # every other number: nothing at all

    def skelight_shatter(self, c=0, arg=0):
        """Skelight_shatter 0x2a946c: zeroes the eight bytes at 0x8e4560; the arguments
        (creature, 8) are not used."""
        self.w64(G_SKELIGHT_STATIC, 0)

    def skelight_set_state(self, c, state):
        """Skelight_setState 0x2a91b8 (creature, state): slot 27.

        After Creature_filterState:
          0     idle clip; +0xf4 = clock + 60
          1     path cleared, wander destination, walk clip; +0xf4 = clock + 300
          3, 0x10  walk clip (the path is NOT cleared)
          5, 0x13  idle clip
          6     ONE OWN DRAW picks one of two swing clips; +0xf4 = 1
          0x12  ignored: the state stays what it was (no hit reaction)
          0x14  object flag 2 (hidden), creature flag bit 41, the static at 0x8e4560
                zeroed, effect 2 at every third sample point of the model, obj_delete.
                No loot, no slot 28, no corpse.
          0x17  stored, nothing else
          anything else: state 0 with the idle clip (and +0xf4 untouched)."""
        u32, w32 = self.u32, self.w32
        refused, state = self.filter_state(c, state)
        if refused:
            return
        anim = c + 0x114
        idle = lambda: self.call('anim_start', anim, self.clip(c, 0x34), 3, F_0_1)        # noqa: E731

        def walk():
            self.call('anim_start', anim, self.clip(c, 0x44), 0x803, F_0_1)
            self.call('anim_syncToSimFrame', anim)

        if state == 0:
            idle()
            w32(c + 0xF4, u32(c + 0x300) + 60)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            walk()
            w32(c + 0xF4, u32(c + 0x300) + 300)
        elif state in (3, 0x10):
            walk()
        elif state in (5, 0x13):
            idle()
        elif state == 6:
            pick = self.obj_rand(c) & 1
            self.call('anim_startBlendInOut', anim, self.clip(c, 0x1C + 8 * pick), 0x808, F_0_1, F_0_1)
            w32(c + 0xF4, 1)
        elif state == 0x12:
            state = self.s16(c + 0x232)
        elif state == 0x14:
            w32(c + 0xC, u32(c + 0xC) | 2)
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x20000000000)
            self.skelight_shatter(c, 8)
            count = s32(self.call('model_getSamplePointCount', self.vcall(c, 16)))
            index = 0
            while index < count:
                point, _second = self.call('model_getSamplePoint', self.vcall(c, 16), anim, self.vec(c + 0x10),
                                           self.s16(c + 0x38), index, 1, 0, ONE)
                self.call('fx_spawn', 2, tuple(point))
                index += 3
            self.call('obj_delete', c)
        elif state == 0x17:
            pass
        else:
            state = 0
            idle()
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Zek
    # =====================================================================================
    ZEK_EVENTS = (
        (3, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)), (4, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),     # state 6, two clips
        (5, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                 # +0x2c, state 0xe (the wave)
        (10, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                # +0x54, state 7
        (0x11, (1, 2, 0, 0), (F_0_3, 0x3F333333, 0, 0)),          # +0x8c, state 8: two hits
        (6, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                 # +0x34, state 0xb
        (8, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                 # +0x44, state 0xc
        (7, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                 # +0x3c, state 9
        (9, (1, 0, 0, 0), (0x3F4CCCCC, 0, 0, 0)),                 # +0x4c, state 10
        (0x10, (1, 0, 0, 0), (0x3FE66666, 0, 0, 0)),              # +0x84, state 0xd (the ground pound)
        (0x13, (0x80, 0, 0, 0), (F_0_2, 0, 0, 0)),                # +0x9c, the death clip used in one level
    )

    def zek_ctor(self, c, type_name, pos, facing, props):
        """Zek_ctor 0x2c1f94 (object, type name, position, facing, property list).

        Creature_ctor with class definition 0x503688; a Weapon1 holder embedded at +0x3c8
        with model entry 0x15 in hand 1; radius 30, turn rate 1.2, kind 0xb, +0x28 = 0x32,
        creature flags |= 0x2000040000, the five resistances 0.5, +0xf4 = frame + 300, the
        wave fields and the special timer +0x478 zeroed.  State 0 through its own
        set-state, a 60-frame run list, eleven clips' event times (ZEK_EVENTS),
        Creature_init.  No own draw, no property of its own."""
        w32, w16, w8 = self.w32, self.w16, self.w8
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_ZEK, props, 0x41200000)
        holder = c + 0x3C8
        w32(c + 0x48, VT_ZEK)
        self._init_holder(c, holder)
        frame = self.u32(G_SIM_FRAME)
        w8(c + 0x28, 0x32)
        w8(c + 0xB4, 0xB)
        w32(c + 0xB0, 0x3F999999)
        w32(c + 0x1C, 0x41F00000)
        w32(c + 0xEC, frame)
        w32(c + 0xF4, frame + 300)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x2000040000)
        for off in (0x68, 0x5C, 0x60, 0x6C, 0x64):
            w32(c + off, HALF)
        for off in (0x460, 0xB8, 0x464, 0x478):
            w32(c + off, 0)
        w16(c + 0x232, 0)
        w32(c + 0x50, holder)
        self.holder_call(holder, 1, 1, 0x15)
        self.call('anim_clear', c + 0x114)
        self.zek_set_state(c, 0)
        self.call('obj_runEvery60', c)
        for entry, masks, times in self.ZEK_EVENTS:
            self.set_def_entry_params(c, entry, masks, times)
        self.call('Creature_init', c)

    def zek_slot35(self, c):
        """Zek's slot 35, 0x2c3c54: the base body (monster level x 0.3)."""
        return self.slot35(c)

    def zek_take_damage(self, c, attacker, flags, amount):
        """Zek_takeDamage 0x2c34e4 (creature, attacker, damage flags; amount): slot 2.

        Damage flag 0x2000 from an attacker with object flag 0x20 (a monster) plays the
        clang and throws fifty sparks; the spark directions are OWN draws (three per try,
        retried while outside the unit ball) and the velocity accumulates.  The particle
        definition 0x8e4ba0 is built on first use (word 0x503748).  Then the base body.
        Damage is never refused or changed here."""
        u32 = self.u32
        if flags & 0x2000 and attacker and u32(attacker + 0xC) & 0x20:
            self.call('sound_playOnObject', self.call('res_find', S_FX_LUMP_ZEK, S_ZEK_CLANG), c, ONE)
            if not u32(G_ZEK_SPARK_READY):
                self.call('particleDef_ctor', G_ZEK_SPARK_DEF, 200, 200, 150, 300, 200, 175, 100,
                          0x40000000, 0x40A00000, 0xC1A00000, 0, 1, 2, 2, 0)
                self.w32(G_ZEK_SPARK_READY, 1)
            ten = 0x41200000
            angle = C.atan2_16(C.sub(u32(attacker + 0x14), u32(c + 0x14)), C.sub(u32(attacker + 0x10), u32(c + 0x10)))
            vx = C.mul(C.cos16(angle), ten)
            vy = C.mul(C.sin16(angle), ten)
            vz = ten
            px, py, pz = self.vec(c + 0x10)
            pz = C.add(pz, C.mul(u32(c + 0x20), 0x3E800000))
            ox = C.mul(C.cos16(angle), u32(c + 0x1C))
            oy = C.mul(C.sin16(angle), u32(c + 0x1C))
            px = C.add(px, ox)
            py, pz = C.add(py, oy), C.add(pz, ZERO)
            for _ in range(50):
                while True:
                    bx = self._unit(self.obj_rand(c))
                    by = self._unit(self.obj_rand(c))
                    bz = self._unit(self.obj_rand(c))
                    if not C.lt(ONE, C.add(C.add(C.mul(bx, bx), C.mul(by, by)), C.mul(bz, bz))):
                        break
                five = 0x40A00000
                vx = C.add(vx, C.mul(bx, five))
                vy = C.add(vy, C.mul(by, five))
                vz = C.add(vz, C.mul(bz, five))
                self.call('particle_spawn', G_ZEK_SPARK_DEF, (px, py, pz), (vx, vy, vz), ZERO)
        self.take_damage(c, attacker, flags, amount)

    @staticmethod
    def _unit(draw):
        """A 16-bit draw as a coordinate in [-1, 1): (d x 2^-16) doubled, minus 1."""
        m = C.mul(C.from_int(draw), F_2M16)
        return C.sub(C.add(m, m), ONE)

    def zek_run(self, c):
        """Zek_run 0x2c2440 (creature): one tick.

        Creature_processDamage and Creature_run with the model from slot 16; the function
        RETURNS when Creature_updateActive says "not active" (no animation, no AI, and the
        ground wave does not move).  Then the holder update (slot 21),
        Creature_stepAnim(1.0), Creature_applyKnockback(0.2), slot 23, the switch, and on
        every path out of the switch the ground-wave tail."""
        u32, st = self.u32, self.set_state
        self.process_damage(c, self.vcall(c, 16))
        if self.run(c, self.vcall(c, 16)):
            return
        if not self.update_active(c):
            return
        holder = u32(c + 0x50)
        if holder:
            self.holder_call(holder, 21, u32(c + 0x24), c, HALF)
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, F_0_2)
        self.vcall(c, 23, 0)
        self._zek_switch(c, ev, st)
        self._zek_wave(c)

    def _zek_specials(self, c, st):
        """The two special attacks, tested in states 3 and 5 (0x2c2644, 0x2c2850): the
        wave when the clock is more than 180 past +0x478 and an enemy stands 120-800 away
        within 5000 of the facing; the ground pound when the clock is past +0x478 and an
        enemy is within 260 in any direction.  -> True when a state was entered."""
        clock = self.s32(c + 0x300)
        if self.s32(c + 0x478) < s32(clock - 180):
            if self.call('creature_findEnemyInCone', c, self.s16(c + 0x38), 5000, 0x42F00000, 0x44480000):
                st(c, 0xE)
                return True
        if self.s32(c + 0x478) < self.s32(c + 0x300):
            if self.call('creature_findEnemyInCone', c, self.s16(c + 0x38), 0x7FFF, ZERO, 0x43820000):
                st(c, 0xD)
                return True
        return False

    def _zek_switch(self, c, ev, st):
        u32 = self.u32
        state = self.s16(c + 0x232)
        facing = lambda turn=0: s16(self.u16(c + 0x38) + turn)   # noqa: E731
        see = lambda face, arc: self.can_see_target_in(c, face, arc, 0, ZERO, F_84, ZERO)      # noqa: E731
        playing = lambda mask=8: self.u16(c + 0x11A) & mask      # noqa: E731
        half = half_toward_zero

        def sweep(face, flags, lo, hi, desc):
            self.call('Creature_hitAllEnemiesInArc', c, face, 8000, lo, hi, self.s16(c + 0xD4), flags, desc,
                      ZERO, F_84)

        if state == 0:                                           # 0x2c2568
            if self.vcall(c, 25, 0):
                st(c, 3)
            elif self.is_away_from_home(c):
                st(c, 1)
        elif state == 1:                                         # 0x2c25ac
            if self.vcall(c, 25, 0):
                st(c, 3)
            else:
                self.move_to_dest(c)
        elif state == 3:                                         # 0x2c25e8 chase
            if not u32(c + 0x234):
                st(c, 0)
            elif see(facing(), 32000):
                st(c, 7 if self.is_target_charging(c) else 5)
            elif not self._zek_specials(c, st):
                if see(facing(), 0x7FFF):
                    self.turn_to_target(c)
                else:
                    self.move_to_target(c)
        elif state == 5:                                         # 0x2c2700 between attacks
            if see(facing(), 8000):
                if self.is_target_charging(c):
                    st(c, 7)
                elif self.s32(c + 0x47C) != 8:
                    st(c, self.obj_rand(c) % 3 + 6)
                else:
                    st(c, (self.obj_rand(c) & 1) + 6)
            elif see(facing(16000), 8000):
                st(c, 9)
            elif see(facing(-16000), 8000):
                st(c, 10)
            elif self.call('creature_findEnemyInCone', c, facing(16000), 8000, ZERO, F_84):
                st(c, 0xB)
            elif self.call('creature_findEnemyInCone', c, facing(-16000), 8000, ZERO, F_84):
                st(c, 0xC)
            elif not self._zek_specials(c, st):
                if see(facing(), 0x7FFF):
                    self.turn_to_target(c)
                elif self.is_not_rooted(c):
                    st(c, 3)
        elif state in (6, 7):                                    # 0x2c296c swing at the target
            self.settle(c)
            if ev & 1:
                desc = self.weapon_descriptor(c)
                self.call('Creature_hitTargetInArc', c, facing(), 8000, self.s16(c + 0xD0), self.s16(c + 0xD2),
                          self.s16(c + 0xD4), 0x80008, desc, ZERO, F_84)
            if not playing():
                st(c, 5)
        elif state == 8:                                         # 0x2c2a00 double hit, turning
            self.settle(c)
            self.turn_to_target(c)
            if ev & 1:
                sweep(facing(), 0x440001, half(self.s16(c + 0xD0)), half(self.s16(c + 0xD2)), 0)
            if ev & 2:
                sweep(facing(), 0x80001, half(self.s16(c + 0xD0)), half(self.s16(c + 0xD2)), 0)
            if not playing():
                st(c, 5)
        elif state in (9, 10, 0xB, 0xC):                         # 0x2c2af4 ... sweeps
            self.settle(c)
            if ev & 1:
                desc = self.weapon_descriptor(c)
                turn = {9: 0, 10: -16000, 0xB: 16000, 0xC: -16000}[state]
                sweep(facing(turn), 0x80008, self.s16(c + 0xD0), self.s16(c + 0xD2), desc)
            if not playing():
                st(c, 5)
        elif state == 0xD:                                       # 0x2c2d68 ground pound
            self.settle(c)
            if ev & 1:
                reach = F_84
                dx = C.mul(C.cos16(self.s16(c + 0x38)), reach)
                dy = C.mul(C.sin16(self.s16(c + 0x38)), reach)
                spot = (C.add(u32(c + 0x10), dx), C.add(u32(c + 0x14), dy), u32(c + 0x18))
                block = self.call('pool_new', 0x9C)
                if block:
                    level = self.vcall(c, 35)
                    self.call('GroundPoundEffect_ctor', block, spot, self.s16(c + 0x38), u32(G_SKILL_GROUNDPOUND),
                              level, c)
                self.w32(c + 0x478, u32(c + 0x300) + 600)
            if not playing():
                st(c, 5)
        elif state == 0xE:                                       # 0x2c2e64 launch the ground wave
            self.settle(c)
            if ev & 1:
                reach = 0x42F00000
                enemy = self.call('creature_findEnemyInCone', c, self.s16(c + 0x38), 10000, reach, 0x44480000)
                if enemy:
                    self.call('handle_link', c + 0x460, enemy, enemy)
                self.w32(c + 0x464, 1)
                dx = C.mul(C.cos16(self.s16(c + 0x38)), reach)
                dy = C.mul(C.sin16(self.s16(c + 0x38)), reach)
                self.wvec(c + 0x46C, (C.add(u32(c + 0x10), dx), C.add(u32(c + 0x14), dy), u32(c + 0x18)))
                self.w16(c + 0x468, self.u16(c + 0x38))
                self.w32(c + 0x478, u32(c + 0x300) + 600)
            if not playing():
                st(c, 5)
        elif state == 0x10:                                      # 0x2c2f9c
            if self.is_attack_ready(c):
                st(c, 0)
            else:
                self.flee_from_target(c, 0)
        elif state == 0x12:                                      # 0x2c2f68
            if not playing(0x10):
                st(c, 5)
        elif state == 0x13:                                      # 0x2c2f84
            if self.is_not_stunned(c):
                st(c, 3)
        elif state == 0x14:                                      # 0x2c2fe0 dead
            self.move_by(c, (0, 0, 0))
            self.call('Creature_deadUpdate', c, ev, (0, 0, 0), 0, 0x41A00000)
        else:                                                    # 0x2c3034: 2, 4, 0xf, 0x11, others
            st(c, 0)

    def _zek_wave(self, c):
        """The tail of Zek_run, 0x2c3054-0x2c34b4: the travelling ground wave, while the
        word +0x464 is set (whatever state Zek is in).

        It moves 5 units along its heading +0x468; its height is terrain_height + 1, and a
        step whose height differs by more than 12 from the old one is undone and ends it.
        With an enemy linked at +0x460 the heading is steered and the wave ends within 36
        units of it (2-D); it also ends beyond 800 units from Zek (2-D).  The end: ring
        effect, sound, area damage (inner 40, radius 180, half melee damage, flags
        0x80840), ONE OWN DRAW for the scorch decal's rotation, a light effect, the handle
        dropped.  Effect 7 at the wave every tick, the last one included."""
        u32, w32 = self.u32, self.w32
        if not u32(c + 0x464):
            return
        wave = c + 0x46C
        old = self.vec(wave)
        cs = C.cos16(self.s16(c + 0x468))
        sn = C.sin16(self.s16(c + 0x468))
        five = 0x40A00000
        w32(wave + 4, C.add(u32(wave + 4), C.mul(sn, five)))
        w32(wave, C.add(u32(wave), C.mul(cs, five)))
        z = C.add(self.call('terrain_height', u32(G_WORLD), self.vec(wave), 0x41400000), ONE)
        w32(wave + 8, z)
        over = False
        if abs(C.to_float(C.sub(z, old[2]))) > 12.0:             # compared as doubles (0x2c3130)
            self.wvec(wave, old)
            over = True
        node = u32(c + 0x460)
        if node:
            ex, ey, _ez = self.vec(u32(node + 0xC) + 0x10)
            bearing = C.atan2_16(C.sub(u32(wave + 4), ey), C.sub(u32(wave), ex))     # from the enemy to the wave
            heading = self.u16(c + 0x468)
            off = s16(bearing - heading)
            step = C.to_int(C.mul(C.from_int(off), 0x3BA3D70A))
            damp = C.to_int(C.mul(C.sqrt(0x3CA3D70A), C.from_int(step)))
            self.w16(c + 0x468, heading - (step - damp))
            dx, dy = C.sub(u32(wave), ex), C.sub(u32(wave + 4), ey)
            if C.lt(C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy))), F_36):
                over = True
        dx, dy = C.sub(u32(c + 0x10), u32(wave)), C.sub(u32(c + 0x14), u32(wave + 4))
        if C.lt(0x491C4000, C.add(C.mul(dx, dx), C.mul(dy, dy))):
            over = True
        if over:
            w32(c + 0x464, 0)
            self.call('fx_ringBurst', self.vec(wave), 0x40800000)
            self.call('sound_playOnObject', self.call('res_find', S_FX_LUMP_ZEK, S_ZEK_WAVE_SOUND), c, ONE)
            self.call('combat_applyAreaDamage', c, self.vec(wave), half_toward_zero(self.s16(c + 0xD0)),
                      half_toward_zero(self.s16(c + 0xD2)), 0x80840, 0, 0x42200000, 0x43340000)
            turn = s16(self.obj_rand(c))
            self.call('decal_add', self.vec(wave), turn, 9, 0, F_48)
            block = self.call('pool_new', 0xBC)
            if block:
                self.call('LightEffect_ctor', block, self.vec(wave), 0, 0, 0x43000000, 0x42C80000, 0x429C0000,
                          0xC2000000, 0, 0, 0, 0, 0x43280000, 0x42700000, ONE, 0x3EB33333)
            self.call('handle_clear', c + 0x460)
            w32(c + 0x460, 0)
        self.call('fx_spawn', 7, self.vec(wave))

    def zek_set_state(self, c, state):
        """Zek_setState 0x2c382c (creature, state): slot 27.

        After Creature_filterState:
          0 / 0x13  idle clip (blend 0.1 / 0.3)
          1     path cleared, wander destination, walk clip
          3     path cleared, walk clip
          0x10  attack cooldown +0x318 = 60, path cleared, walk clip
          5     idle clip, synchronised to the frame counter
          6-0xe the state is remembered in +0x47c; 6 picks one of two clips with ONE OWN
                DRAW; 9 and 10 use clip flags 0x4808
          0x12  ONE OWN DRAW picks one of four hit clips
          0x14  creature flag bit 41, Creature_dropLoot, then - unless the level name is
                the text at 0x54e5f8 (exact compare) - the weapon is dropped (holder slot
                11) and the other death clip plays; slot 28 (on death)
          anything else: state 0 is stored and nothing else happens."""
        u32 = self.u32
        refused, state = self.filter_state(c, state)
        if refused:
            return
        anim = c + 0x114
        start = lambda off, flags, blend=F_0_1: self.call('anim_start', anim, self.clip(c, off), flags, blend)  # noqa: E731
        swing = lambda clip, flags: self.call('anim_startBlendInOut', anim, clip, flags, F_0_1, F_0_1)  # noqa: E731
        clips = {7: (0x54, 0x808), 8: (0x8C, 0x808), 9: (0x3C, 0x4808), 10: (0x4C, 0x4808), 0xB: (0x34, 0x808),
                 0xC: (0x44, 0x808), 0xD: (0x84, 0x808), 0xE: (0x2C, 0x808)}
        if state == 0:
            start(0x7C, 3)
        elif state == 0x13:
            start(0x7C, 3, F_0_3)
        elif state in (1, 3, 0x10):
            if state == 0x10:
                self.w16(c + 0x318, 60)
            self.clear_path(c)
            if state == 1:
                self.pick_wander_dest(c)
            start(0x94, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 5:
            start(0x7C, 3)
            self.call('anim_syncToSimFrame', anim)
        elif state == 6:
            self.w32(c + 0x47C, state)
            swing(self.clip(c, 0x1C + 8 * (self.obj_rand(c) & 1)), 0x808)
        elif state in clips:
            self.w32(c + 0x47C, state)
            swing(self.clip(c, clips[state][0]), clips[state][1])
        elif state == 0x12:
            swing(self.clip(c, 0x5C + 8 * (self.obj_rand(c) & 3)), 0x10)
        elif state == 0x14:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x20000000000)
            self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), 0,
                      F_36, 0x40000000, 0x3FCCCCCC, 0x3F199999, 0x3FB33333, 0x3E800000)
            if self.cstr(G_LEVEL_NAME) == self.cstr(S_ZEK_LEVEL):
                start(0x9C, 0x806, F_0_2)
            else:
                holder = u32(c + 0x50)
                if holder:
                    self.holder_call(holder, 11, 1, c, 0, 0)
                start(0xA4, 0x806, F_0_2)
            self.vcall(c, 28, 0)
        else:
            state = 0
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Skill 11, Summon Skeleton
    # =====================================================================================
    def summon_can_use(self, skill, caster):
        """SkillSummonSkeleton_canUse 0x2e2368 (skill, caster) -> 1 or 0.

        The name asked for is the monsters' shared one (pointer at 0x503788) for a caster
        without object flag 0x40, else the per-slot name (table 0x503778, slot at caster
        +0x3c8; slot 4 or more refuses).  1 exactly when world_findObjectByName finds no
        object of that name.  The name table sees hidden, dead and delete-queued objects
        (docs/issues/arena-desync.md F4)."""
        if self.u32(caster + 0xC) & 0x40:
            slot = self.u32(caster + 0x3C8)
            if slot >= 4:
                return 0
            name = self.u32(G_SUMMON_PLAYER_NAMES + 4 * slot)
        else:
            name = self.u32(G_SUMMON_MONSTER_NAME)
        return 0 if self.call('world_findObjectByName', name) else 1

    def _cosmetic_ball(self):
        """A point of the unit ball from the presentation generator: three draws per try
        (x, y, z in that order), retried while the squared length exceeds 1."""
        while True:
            x = self._unit(self.cosmetic_draw())
            y = self._unit(self.cosmetic_draw())
            z = self._unit(self.cosmetic_draw())
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def summon_cast(self, skill, level, caster, pos, facing):
        """SkillSummonSkeleton_cast 0x2e18a4 (skill, level, caster, position, facing)
        -> the SpellSummonSkeleton, or 0.

        In order:
          1. the caster's second flash quad (+0x98 -128, +0x9a -110, +0x9c -128, +0x9e 30);
          2. when the caster's model has sample points: 32 + 200 particles; every number
             comes from the presentation generator 0x404460;
          3. the spot: 72 units along `facing` from `pos`, z = terrain_height; when that
             differs from the CASTER's z by more than 24: world_findFreeSpot around the
             caster (range 72, radius 12) and its answer if it found one;
          4. ONE SHARED DRAW d1 (always);
          5. strength = skill slot 12 (0, level, caster, 10);
          6. pool_new(0x468); with a block: Skelight_ctor at the spot with the property
             list 0x503770 (monster) or 0x503750 + 8 x slot (player) and the strength as
             its level; object flag 0x4000; chance = slot 12 (1, ...); when
             d1 / 65536 < chance x 0.01: ONE SHARED DRAW % 3 chooses holder slot 2, 4 or 6
             (an elemental weapon); for a player caster with level > 0 the charm set-up;
          7. the sound at `pos`;
          8. with a skeleton: pool_new(0x1c) and SpellSummonSkeleton_ctor (one more shared
             draw).  A monster caster drops the result (FINDINGS D22)."""
        u32, w16 = self.u32, self.w16
        facing = s16(facing)
        w16(caster + 0x9A, 0xFF92)
        w16(caster + 0x9C, 0xFF80)
        w16(caster + 0x9E, 0x1E)
        w16(caster + 0x98, 0xFF80)
        count = s32(self.call('model_getSamplePointCount', self.vcall(caster, 16)))
        if count:
            for _ in range(32):
                point = self._summon_sample(caster, count)
                x, y, z = self._cosmetic_ball()
                k = 0x3E72AF9A
                point = (C.add(point[0], C.mul(x, k)), C.add(point[1], C.mul(y, k)), C.add(point[2], C.mul(z, k)))
                x, y, z = self._cosmetic_ball()
                k = 0x3D8B4634
                self.call('particle_spawn', G_SUMMON_PARTICLES[0], point, (C.mul(x, k), C.mul(y, k), C.mul(z, k)), ZERO)
            for _ in range(200):
                point = self._summon_sample(caster, count)
                x, y, z = self._cosmetic_ball()
                k = 0x41C000E5
                self.call('particle_spawn', G_SUMMON_PARTICLES[1], point, (C.mul(x, k), C.mul(y, k), C.mul(z, k)), ZERO)
        reach = F_72
        sx = C.add(pos[0], C.mul(C.cos16(facing), reach))
        sy = C.add(pos[1], C.mul(C.sin16(facing), reach))
        sz = self.call('terrain_height', u32(G_WORLD), (sx, sy, pos[2]), 0x41400000)
        spot = (sx, sy, sz)
        if caster and abs(C.to_float(C.sub(sz, u32(caster + 0x18)))) > 24.0:      # compared as doubles
            out, found = self.call('world_findFreeSpot', self.vec(caster + 0x10), 0x48, 0xC, 0)
            if s8(found):
                spot = tuple(out)
        d1 = C.mul(C.from_int(self.draw()), F_2M16)
        strength = self.skill_call(skill, 12, 0, level, caster, 10)
        if not u32(caster + 0xC) & 0x40:
            props = G_SUMMON_MONSTER_PROPS
        elif u32(caster + 0x3C8) < 4:
            props = G_SUMMON_PLAYER_PROPS + 8 * u32(caster + 0x3C8)
        else:
            props = 0
        skel = self.call('pool_new', 0x468)
        if skel:
            self.skelight_ctor(skel, spot, facing, props, strength)
            self.w32(skel + 0xC, u32(skel + 0xC) | 0x4000)
            chance = self.skill_call(skill, 12, 1, level, caster, 10)
            if C.lt(d1, C.mul(C.from_int(s32(chance)), 0x3C23D70A)):
                pick = self.draw() % 3
                holder = u32(skel + 0x50)
                if holder:
                    self.holder_call(holder, (2, 4, 6)[pick], 0)
            if u32(caster + 0xC) & 0x40 and s32(level) > 0:
                self.w8(skel + 0x5A, self.u8(caster + 0x3C8))
                self.w64(skel + 0xA8, self.u64(skel + 0xA8) | 0x400000)
                self.call('Creature_setCharm', skel, M32, self.vcall(caster, 37))
                w16(skel + 0x3AC, 400)
                self.vcall(skel, 34, 500)
        self.call('sound_playAtPos', self.call('res_find', S_FX_LUMP_SUMMON, S_SUMMON_SOUND), tuple(pos), ONE)
        if not skel:
            return 0
        spell = self.call('pool_new', 0x1C)
        if spell:
            self.summon_spell_ctor(spell, level, caster, skill, skel)
        return spell

    def _summon_sample(self, caster, count):
        """One random sample point of the caster's model (presentation generator)."""
        model = self.vcall(caster, 16)
        index = self.cosmetic_draw() % abs(count)                # a signed remainder of a non-negative draw
        point = self.call('model_getSamplePoint', model, caster + 0x114, self.vec(caster + 0x10),
                          self.s16(caster + 0x38), index, 0, 0, ONE)
        return tuple(point)

    def spell_base_ctor(self, spell, level, owner, skill, table):
        """The Spell base, inlined in every spell constructor: level byte +0, back list
        +4 = 0, skill +8, owner +0xc, the spell's own generator +0x10 = ONE SHARED DRAW,
        table +0x14."""
        self.w8(spell, level)
        self.w32(spell + 0x14, VT_SPELL)
        self.w32(spell + 0xC, owner)
        self.w32(spell + 4, 0)
        self.w32(spell + 8, skill)
        self.w32(spell + 0x10, self.draw())
        self.w32(spell + 0x14, table)

    def summon_spell_ctor(self, spell, level, caster, skill, skel):
        """SpellSummonSkeleton_ctor 0x2e16ec (spell, level, caster, skill, skeleton): the
        Spell base (one shared draw) and a handle to the skeleton at +0x18."""
        self.spell_base_ctor(spell, level, caster, skill, VT_SPELL_SUMMON)
        self.w32(spell + 0x18, 0)
        if skel:
            self.call('handle_link', spell + 0x18, skel, skel)

    def summon_spell_run(self, spell, pos=None, facing=0):
        """SpellSummonSkeleton_run 0x2e177c (spell, position, facing): when the handle at
        +0x18 is empty the spell destroys itself (slot 1 with 3).  Reached only through an
        attached-spell list, which a monster caster's spell never joins."""
        if not self.u32(spell + 0x18) and spell:
            self.table_call('Spell', spell, 0x14, 1, 3)

    # =====================================================================================
    # Skill 87, Tagar's Insects: the cast and the spell's constructor
    # =====================================================================================
    def tagar_cast(self, skill, level, caster, pos, facing):
        """SkillTagarsInsects_cast 0x30c708 (skill, level, caster, position, facing) -> the
        spell, or 0 when the pool has no block.

        The level goes through skill slot 14 (level, 0x14); a sound at `pos`;
        pool_new(0x94); SpellTagarsInsects_ctor.  `pos` and `facing` are otherwise unused:
        the constructor reads the caster."""
        level = self.skill_call(skill, 14, level, 0x14)
        self.call('sound_playAtPos', self.call('res_find', S_FX_LUMP_TAGAR, S_TAGAR_SOUND), tuple(pos), ONE)
        spell = self.call('pool_new', 0x94)
        if spell:
            self.tagar_spell_ctor(spell, level, caster, skill)
        return spell

    def tagar_spell_ctor(self, spell, level, owner, skill):
        """SpellTagarsInsects_ctor 0x30c95c (spell, level, owner, skill).

        The Spell base (ONE SHARED DRAW), eight empty victim handles +0x18, clock +0x78 =
        0, hunt end +0x7c = 0x4000101f (2.0009...), current slot +0x80 = -1, victims +0x82
        = 0, heading +0x84 = the owner's facing, wander +0x86 = 0, swarm position +0x88 =
        the owner's position moved 24 units along its facing and 48 up."""
        w32, w16, u32 = self.w32, self.w16, self.u32
        self.spell_base_ctor(spell, level, owner, skill, VT_SPELL_TAGAR)
        for k in range(8):
            w32(spell + 0x18 + 4 * k, 0)
        w16(spell + 0x80, 0xFFFF)
        w16(spell + 0x82, 0)
        w32(spell + 0x7C, 0x4000101F)
        w32(spell + 0x78, 0)
        owner = u32(spell + 0xC)
        self.wvec(spell + 0x88, self.vec(owner + 0x10))
        w16(spell + 0x86, 0)
        w16(spell + 0x84, self.u16(u32(spell + 0xC) + 0x38))
        reach = 0x41C00000
        w32(spell + 0x88, C.add(u32(spell + 0x88), C.mul(C.cos16(self.s16(spell + 0x84)), reach)))
        y = C.add(u32(spell + 0x8C), C.mul(C.sin16(self.s16(spell + 0x84)), reach))
        w32(spell + 0x90, C.add(u32(spell + 0x90), F_48))
        w32(spell + 0x8C, y)


    # =====================================================================================
    # Skill 87: the spell's per-tick run (slot 2 of the spell, called from Creature_run of
    # the creature it is attached to)
    # =====================================================================================
    TAGAR_SPEED = 0x434B0DA1                    # 203.05 units a second
    TAGAR_TIME_PER_UNIT = 0x3BA1605B            # 1 / 203.05
    TAGAR_CLOUD = (0x8E7598, 0x8E75E8, 0x8E7638, 0x8E7688)     # particle definitions

    def _spell_ball(self, spell):
        """A point of the unit ball from the spell's own generator: three draws per try,
        retried while the squared length exceeds 1."""
        while True:
            x = self._unit(self.spell_rand(spell))
            y = self._unit(self.spell_rand(spell))
            z = self._unit(self.spell_rand(spell))
            if not C.lt(ONE, C.add(C.add(C.mul(x, x), C.mul(y, y)), C.mul(z, z))):
                return x, y, z

    def tagar_is_valid(self, spell, obj, marker_test):
        """SpellTagarsInsects_isValidTarget 0x30db9c (spell, object, marker test) -> 0 or 1:
        the object exists, has neither object flag 1 nor 8, the owner's slot 20 calls it
        an enemy, and - with the marker test - it carries no marker (skill id 0x57) of
        this owner."""
        if not obj or self.u32(obj + 0xC) & 9:
            return 0
        owner = self.u32(spell + 0xC)
        if not self.vcall(owner, 20, obj):
            return 0
        if marker_test and self.call('creature_findSpell', obj, 0x57, self.u32(spell + 0xC)):
            return 0
        return 1

    def tagar_pick_target(self, spell, later):
        """SpellTagarsInsects_pickTarget 0x30d998 (spell, later) -> object or 0.

        The first victim (later = 0): world_collectObjectsInArc(swarm position, heading,
        owner; 120, 90 degrees, 0) and the FIRST entry of its list that is valid and not
        marked.  Later victims: world_collectInSphere(swarm position; 120) and, among the
        valid unmarked entries not already in one of the n victim slots, the one with the
        smallest squared distance to the swarm in 3-D (strict; start value 1,000,000)."""
        u32 = self.u32
        swarm = self.vec(spell + 0x88)
        heading = self.s16(spell + 0x84)
        if later:
            found = self.call('world_collectInSphere', swarm, heading, 0x42F00000)
        else:
            found = self.call('world_collectObjectsInArc', swarm, heading, u32(spell + 0xC),
                              0x42F00000, 0x42B40000, ZERO)
        best, best_d = 0, 0x49742400
        for obj in found or ():
            if not self.tagar_is_valid(spell, obj, 1):
                continue
            count = self.s16(spell + 0x82)
            if any(u32(spell + 0x18 + 4 * k) and u32(u32(spell + 0x18 + 4 * k) + 0xC) == obj for k in range(max(count, 0))):
                continue
            if not later:
                self.call('handle_clear', 'stack')
                return obj
            dx = C.sub(u32(spell + 0x88), u32(obj + 0x10))
            dy = C.sub(u32(spell + 0x8C), u32(obj + 0x14))
            dz = C.sub(u32(spell + 0x90), u32(obj + 0x18))
            d = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
            if C.lt(d, best_d):
                best, best_d = obj, d
        self.call('handle_clear', 'stack')
        return best

    def tagar_tick_victims(self, spell):
        """SpellTagarsInsects_tickVictims 0x30d558 (spell) -> 1 when any victim is still
        infested.  For each of the n victim slots whose handle holds an object and whose
        time +0x38 is not negative:

          time <= clock, or the victim is no longer valid: its marker (if
              creature_findSpell finds one) is destroyed and the time becomes -1.0;
          else: the victim's second flash quad = (100, 0, 0, 4); when the slot's next-tick
              time +0x58 <= clock: damage_apply(victim, owner, 100000, 0, 0, 0x4000000,
              none, 0; low, high) and the next tick is 1.0 later.  low / high: a player
              owner asks skill slot 8 (1, level, 0; 0.2); anyone else takes v = slot 12
              (1, level, owner, 0) and uses int(v - v x 0.2), int(v + v x 0.2).  Then five
              particles on the victim, each with a ball point from the SPELL'S OWN
              generator (three draws per try) - they shift the wander draws of the run."""
        u32, w16 = self.u32, self.w16
        active = 0
        i = 0
        while i < self.s16(spell + 0x82):
            node = u32(spell + 0x18 + 4 * i)
            victim = u32(node + 0xC) if node else 0
            slot = spell + 0x38 + 4 * i
            if not victim or C.lt(u32(slot), ZERO):
                i += 1
                continue
            if C.le(u32(slot), u32(spell + 0x78)) or not self.tagar_is_valid(spell, victim, 0):
                marker = self.call('creature_findSpell', victim, 0x57, u32(spell + 0xC))
                if marker:
                    self.table_call('Spell', marker, 0x14, 1, 3)
                self.w32(slot, 0xBF800000)
                i += 1
                continue
            w16(victim + 0x98, 100)
            w16(victim + 0x9E, 4)
            w16(victim + 0x9A, 0)
            w16(victim + 0x9C, 0)
            active += 1
            tick = spell + 0x58 + 4 * i
            if C.le(u32(tick), u32(spell + 0x78)):
                owner, level, skill = u32(spell + 0xC), self.s8(spell), u32(spell + 8)
                if owner and u32(owner + 0xC) & 0x40:
                    low, high = self.skill_call(skill, 8, 1, level, 0, F_0_2)
                else:
                    value = C.from_int(s32(self.skill_call(skill, 12, 1, level, owner, 0)))
                    spread = C.mul(value, F_0_2)
                    high = C.to_int(C.add(value, spread))
                    low = C.to_int(C.sub(value, spread))
                self.call('damage_apply', victim, u32(spell + 0xC), 100000, 0, 0, 0x4000000, 0, 0,
                          C.from_int(s32(low)), C.from_int(s32(high)))
                self.w32(tick, C.add(u32(tick), ONE))
            for j in range(5):
                frame = u32(G_SIM_FRAME)
                sign = 0xBF800000 if j & 1 else ONE
                ux, uy, uz = self._spell_ball(spell)
                four = 0x40800000
                velocity = (C.mul(ux, four), C.mul(uy, four), C.mul(uz, four))
                swirl = ((frame + j * 0x2AAA) << 9) & M32
                px = C.mul(C.mul(sign, u32(victim + 0x1C)), C.cos16(swirl))
                py = C.mul(C.mul(sign, u32(victim + 0x1C)), C.sin16(swirl))
                bob = C.sin16(((frame - j * 0x2AAA) << 10) & M32)
                pz = C.mul(C.mul(sign, bob), C.mul(u32(victim + 0x20), 0x3E800000))
                px = C.add(px, u32(victim + 0x10))
                py = C.add(py, u32(victim + 0x14))
                pz = C.add(C.add(pz, u32(victim + 0x18)), C.mul(u32(victim + 0x20), HALF))
                self.call('particle_spawn', self.TAGAR_CLOUD[0], (px, py, pz), velocity, ZERO)
            i += 1
        return 1 if active > 0 else 0

    def tagar_spell_run(self, spell, pos=None, facing=0):
        """SpellTagarsInsects_run 0x30cbc8 (spell, position, facing): slot 2 of the spell,
        once per tick of the creature it is attached to.  The two arguments are not used.

          1. tickVictims (with the clock of the previous tick), then clock +0x78 += 1/60.
          2. hunt end +0x7c <= clock: destroy the spell (its slot 1 with 3) when no victim
             is active; return either way.
          3. limit = min(8, skill slot 12 (0, level, owner, 10)); return when n >= limit.
          4. the current slot +0x80: dropped (-1) when its handle is empty or its object
             no longer valid; without one, pickTarget, and a new target takes slot n: its
             handle is linked and its time = clock + distance x (1/203.05).
          5. with a target: steer the heading (a reflection, not a wrap, beyond a quarter
             turn; a fifth of the error per tick), shorten the slot's time to the direct
             flight time, speed = distance / time left (a division by zero on the arrival
             tick, overwritten below - FINDINGS F3), close a share of the height gap,
             and on arrival (time <= clock + 1/30): n += 1, time = seconds statistic +
             1/30, next damage tick = clock, a marker spell on the victim (ONE SHARED
             DRAW for its unused generator; none if the pool has no block), a sound, the
             hunt end + 0.501, current slot = -1.
          6. wander: ONE OWN DRAW; below 0x4906 a second one sets the wander angle; the
             swarm moves along heading + wander at the speed.
          7. the cloud: 50 particles (per particle: a ball point, a second ball point, one
             draw for the offset length, one for the kind - all OWN draws) and one marker
             particle placed with the frame counter."""
        u32, w32, w16 = self.u32, self.w32, self.w16
        active = self.tagar_tick_victims(spell)
        clock = C.add(u32(spell + 0x78), RC.DT)
        w32(spell + 0x78, clock)
        if C.le(u32(spell + 0x7C), clock):
            if not active and spell:
                self.table_call('Spell', spell, 0x14, 1, 3)
            return
        skill = u32(spell + 8)
        limit = min(8, s32(self.skill_call(skill, 12, 0, self.s8(spell), u32(spell + 0xC), 10)))
        if not self.s16(spell + 0x82) < limit:
            return
        target = 0
        current = self.s16(spell + 0x80)
        if current >= 0:
            node = u32(spell + 0x18 + 4 * current)
            if node:
                target = u32(node + 0xC)
            if not node or not self.tagar_is_valid(spell, target, 0):
                w16(spell + 0x80, 0xFFFF)
        if self.s16(spell + 0x80) < 0:
            target = self.tagar_pick_target(spell, 1 if self.s16(spell + 0x82) > 0 else 0)
            if target:
                count = self.u16(spell + 0x82)
                w16(spell + 0x80, count)
                self.call('handle_link', spell + 0x18 + 4 * s16(count), target, target)
                dy = C.sub(u32(target + 0x14), u32(spell + 0x8C))
                dx = C.sub(u32(target + 0x10), u32(spell + 0x88))
                dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
                w32(spell + 0x38 + 4 * self.s16(spell + 0x80),
                    C.add(u32(spell + 0x78), C.mul(dist, self.TAGAR_TIME_PER_UNIT)))
        speed = self.TAGAR_SPEED
        if target:
            dx = C.sub(u32(target + 0x10), u32(spell + 0x88))
            dy = C.sub(u32(target + 0x14), u32(spell + 0x8C))
            if C.lt(ONE, C.add(C.mul(dx, dx), C.mul(dy, dy))):
                error = C.atan2_16(dy, dx) - self.s16(spell + 0x84)
                if error >= 0x4000:
                    error = 0x7FFF - error
                elif error < -0x3FFF:
                    error = -0x8000 - error
                step = -((-error) // 5) if error < 0 else error // 5
                w16(spell + 0x84, self.u16(spell + 0x84) + step)
            dx = C.sub(u32(target + 0x10), u32(spell + 0x88))
            dy = C.sub(u32(target + 0x14), u32(spell + 0x8C))
            slot = spell + 0x38 + 4 * self.s16(spell + 0x80)
            dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
            eta = C.add(u32(spell + 0x78), C.mul(dist, self.TAGAR_TIME_PER_UNIT))
            if C.lt(eta, u32(slot)):
                w32(slot, eta)
            clock = u32(spell + 0x78)
            left = C.sub(u32(slot), clock)
            speed = C.div(dist, left)
            if C.lt(RC.DT, left):
                sz = u32(spell + 0x90)
                gap = C.sub(C.add(u32(target + 0x18), F_48), sz)
                w32(spell + 0x90, C.add(sz, C.div(gap, C.mul(left, 0x42700000))))
            thirtieth = 0x3D088888
            if C.le(u32(slot), C.add(clock, thirtieth)):          # arrival
                w16(spell + 0x82, self.u16(spell + 0x82) + 1)
                seconds = self.skill_call(u32(spell + 8), 12, 2, self.s8(spell), u32(spell + 0xC), 10)
                current = self.s16(spell + 0x80)
                w32(spell + 0x38 + 4 * current, C.add(C.from_int(s32(seconds)), thirtieth))
                w32(spell + 0x58 + 4 * current, u32(spell + 0x78))
                marker = self.call('pool_new', 0x20)
                if marker:
                    owner = u32(spell + 0xC)
                    self.w8(marker, 1)
                    w32(marker + 0x14, VT_SPELL)
                    w32(marker + 4, 0)
                    w32(marker + 0xC, target)
                    w32(marker + 8, 0)
                    w32(marker + 0x10, self.draw())
                    w32(marker + 0x14, VT_SPELL_MARKER)
                    w32(marker + 0x18, owner)
                    w32(marker + 0x1C, 0x57)
                self.call('creature_addSpell', target, marker)
                speed = self.TAGAR_SPEED
                self.call('sound_playAtPos', self.call('res_find', S_FX_LUMP_TAGAR, S_TAGAR_HIT_SOUND),
                          self.vec(target + 0x10), ONE)
                w16(spell + 0x80, 0xFFFF)
                w32(spell + 0x7C, C.add(u32(spell + 0x7C), 0x3F0041AA))
        if self.spell_rand(spell) < 0x4906:                       # 0x30d0ac wander
            turn = C.sub(C.mul(C.from_int(self.spell_rand(spell)), F_2M16), HALF)
            w16(spell + 0x86, C.to_int(C.mul(turn, 0x45F81000)))
        angle = s16(self.u16(spell + 0x84) + self.u16(spell + 0x86))
        w32(spell + 0x88, C.add(u32(spell + 0x88), C.mul(C.mul(C.cos16(angle), speed), RC.DT)))
        sine = C.sin16(angle)
        grow = C.mul(u32(spell + 0x78), 0x40226FA7)
        w32(spell + 0x8C, C.add(u32(spell + 0x8C), C.mul(C.mul(sine, speed), RC.DT)))
        if C.lt(ONE, grow):
            grow = ONE
        for _ in range(50):                                       # 0x30d18c the cloud
            x, y, z = self._spell_ball(spell)
            k = C.mul(C.mul(grow, 0x436D90B9), RC.DT)
            velocity = (C.mul(x, k), C.mul(y, k), C.mul(z, k))
            cx, cy, cz = self._spell_ball(spell)
            inverse = C.rsqrt(ONE, C.add(C.add(C.mul(cx, cx), C.mul(cy, cy)), C.mul(cz, cz)))
            cx, cy, cz = C.mul(cx, inverse), C.mul(cy, inverse), C.mul(cz, inverse)
            reach = C.mul(C.mul(grow, 0x4151D268), C.mul(C.from_int(self.spell_rand(spell)), F_2M16))
            point = (C.add(C.mul(cx, reach), u32(spell + 0x88)), C.add(C.mul(cy, reach), u32(spell + 0x8C)),
                     C.add(C.mul(cz, reach), u32(spell + 0x90)))
            kind = self.spell_rand(spell)
            definition = self.TAGAR_CLOUD[0 if kind >= 0x7D01 else 1 if kind >= 0x3A99 else 2]
            self.call('particle_spawn', definition, point, velocity, ZERO)
        ring, lean = 0x4151D268, 0x3F0F56FB                       # 0x30d444 the marker particle
        side = C.neg(C.sin16(self.s16(spell + 0x84)))
        spin = (u32(G_SIM_FRAME) << 10) & M32
        px = C.mul(C.mul(side, lean), C.mul(C.cos16(spin), ring))
        ahead = C.mul(C.cos16(self.s16(spell + 0x84)), lean)
        py = C.mul(ahead, C.mul(C.cos16((u32(G_SIM_FRAME) << 10) & M32), ring))
        pz = C.mul(C.mul(C.sin16((u32(G_SIM_FRAME) << 10) & M32), ring), lean)
        point = (C.add(px, u32(spell + 0x88)), C.add(py, u32(spell + 0x8C)), C.add(pz, u32(spell + 0x90)))
        self.call('particle_spawn', self.TAGAR_CLOUD[3], point, (0, 0, 0), ZERO)


# ---------------------------------------------------------------------------------------
# The level script's part.  No game data: the entry and variable names are the level's
# own, the three numbers are the script's.  docs/spec/arena-monsters.md section 10 is the
# prose; scripts/DRUNARE.txt (local) is the decompiled script this follows.
# ---------------------------------------------------------------------------------------
def scaled_time(count):
    """Script built-in getScaledTime 0x14412c: int((float(count) x 60.0) x 0x3c888888).
    The second factor is 1/60 truncated, so the result is count - 1 for the counts this
    script reaches: "more than 300" first holds at a count of 302."""
    return C.to_int(C.mul(C.mul(C.from_int(count), 0x42700000), RC.DT))


class ArenaScript:
    """The DRUNARE level script as a small state machine: what the death scripts of the
    four knights and of the avatar do, frame by frame, through the deferred-call queue.

    Deferred calls (docs/script.md 2.4): a name queued during frame N runs in frame N+1,
    once; an entry that wants to keep running queues itself again.  `frame(paused)` is one
    simulated frame's Script task; `paused` is what the built-in gamePaused() would answer
    (the pause flag, a jump-gate journey, or a running cutscene).  Things the script asks
    the game to do are appended to .log as tuples.

    Quest variables (.q) outlive the level; script globals (.g) do not."""

    def __init__(self, quest=None):
        self.q = {'sawknights': 0, 'sawcaz': 0, 'killedAv': 0, 'endsound': 0, 'firstmissionever': 0,
                  'knight1': 0, 'knight2': 0, 'knight3': 0, 'knight4': 0}
        self.q.update(quest or {})
        self.g = {0: 0, 4: 0}
        self.front, self.back, self.log = [], [], []
        self.paused = 0

    def defer(self, name):
        if len(self.back) < 64:                 # a 65th name in one frame is dropped (0x1ed52c)
            self.back.append(name)

    def frame(self, paused=0):
        """One Script task: run the names queued last frame, then promote this frame's."""
        self.paused = 1 if paused else 0
        for name in self.front:
            getattr(self, name)()
        self.front, self.back = self.back, []

    # ---- entries, in file order ---------------------------------------------------------
    def start(self):
        for name in ('Rallos', 'avatar', 'knight'):
            self.log.append(('hideMonster', name))
        self.log.append(('removeQuest',))
        if self.q['killedAv']:
            self.log.append(('autoPropSetState', 'safety', 1))
        self.log.append(('setMonsterVal', 'avatar', 4, 2000))       # slot 34: HomeRange 2000
        self.log.append(('setMonsterVal', 'knight', 4, 2000))

    def incoming(self):                         # the trigger volume
        if not self.q['sawknights']:
            self.log.append(('cutScene', 'knights'))
            self.log.append(('postAction', 'nosave'))
            self.q['sawknights'] = 1
        else:
            self.setFlag()

    def nosave(self):                           # post action of the first cutscene
        self.log.append(('setSaveInhibit', 1))
        self.log.append(('setCFlag', 'avatar', 0, 1))

    def setFlag(self):
        self.log.append(('setCFlag', 'avatar', 0, 1))

    def knight_death(self, index):
        """The deathScript of knight `index` (1-4): runs inside that knight's tick."""
        self.q['knight%d' % index] = 1
        self.knightDefeatedPause()

    def knightDefeatedPause(self):
        if all(self.q['knight%d' % i] for i in (1, 2, 3, 4)):
            self.g[4] = 0
            self.defer('knightDefeatedDelay')

    def knightDefeatedDelay(self):
        if not self.paused:
            self.g[4] += 1
        if scaled_time(self.g[4]) > 300:
            self.knightDefeated()
        else:
            self.defer('knightDefeatedDelay')

    def knightDefeated(self):
        if not self.q['sawcaz']:
            self.log.append(('cutScene', 'cazic'))
            self.q['sawcaz'] = 1

    def avatar_death(self):
        """The avatar's deathScript."""
        self.g[0] = 0
        self.defer('bossDefeatedDelay')

    def bossDefeatedDelay(self):
        if not self.paused:
            self.g[0] += 1
        if scaled_time(self.g[0]) > 250 and not self.q['endsound']:
            self.log.append(('setInfo',))
            self.log.append(('soundSequence',))
            self.q['endsound'] = 1
            self.q['firstmissionever'] = 1
            self.defer('bossDefeatedDelay')     # and no jump: the test below queues it AGAIN
        if scaled_time(self.g[0]) > 1500:
            self.endmission()
        else:
            self.defer('bossDefeatedDelay')

    def endmission(self):
        if not self.q['killedAv']:
            self.log.append(('postAction', 'levelChange'))
            self.log.append(('cutScene', 'bossdefeated'))
            self.log.append(('reapEnemies',))
            self.log.append(('removeQuest',))
            self.q['killedAv'] = 1

    def levelChange(self):                      # post action of the last cutscene
        self.log.append(('grantMission', 1))
        self.log.append(('newWorld', 'hub2'))
