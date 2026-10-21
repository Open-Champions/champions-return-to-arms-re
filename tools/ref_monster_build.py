#!/usr/bin/env python3
"""ref_monster_build.py - reference contract for how a script or the arena builds a
monster (docs/script-items.md section 5).

  arena_spawnMonster     0x3065fc   (className or 0, existing creature or 0)
  ScriptGenerator_spawn  0x265fc4   (generator, typeName)
  generateMonster        0x1473d4   the script handler: name interning, then the spawn
                                    (its wrapper half is in tools/ref_natives.py)

The world is reached through call-outs (Host.call): world_findFreeSpot,
world_createObject, Creature_scaleStats, Creature_clearStatus, pool_new,
creature_addSpell, and the two virtual calls (vtable slot 34 home range, slot 27 AI
state).  The class constructor that world_createObject reaches through the factory is
not part of this contract: it reads the monster level g_levelMonsterLevel 0x4f714c and
its type row (Creature_ctor 0x10a1b0, Creature_setStats 0x10a620, docs/data-tables.md
3.2 and docs/spec/combat.md 4.2).  What this module adds is everything around it:
where, facing, which flags, which scale, which spell, which states, and the seed.

Floats are raw single-precision patterns; each operation is one R5900 operation
(ref_core.add / mul).  Nothing from the game is in this file; the 30 class names the
arena scale table is keyed by are read from the user's executable (0x5037f0) at run time.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C       # noqa: E402

M32 = 0xFFFFFFFF

# ---- arena_spawnMonster -------------------------------------------------------------------
G_WAVE = 0x8E7338               # s16 wave number
G_RECIPE_COUNT = 0x503886       # s16 (5 in the executable image)
G_RING_ANGLE = 0x8E7360         # u16/s16 current angle on the ring
G_RING_STEP = 0x8E7364          # u16 step added after each spawn (arena_setRingStep 0x3065b0)
G_RING_CENTRE = 0x503888        # pointer to the centre vector
G_ARENA_PROPS = 0x8E7230        # property list handed to world_createObject
G_ARENA_CLASSES, ARENA_CLASS_COUNT = 0x5037F0, 30   # class-name pointers keyed to the scale table
G_RAND_SEED = 0x404464
RING_RADIUS = 0x43480000        # 200.0 (0x306768)
SPOT_RANGE, SPOT_RADIUS = 0x60, 0x18
RETRY_STEP = 0xFA0              # 4000: the angle and the try counter both advance
RETRY_LIMIT = 0x10000           # stop when the counter exceeds 65536: at most 17 searches
FACING_FLIP = 0x8000            # the monster faces the centre: angle - 0x8000
OBJ_FLAG_ARENA = 0x2            # object +0x0c |= 2 on a new monster
HOME_RANGE = 5000               # vtable slot 34 argument
VSLOT_HOME_RANGE, VSLOT_AI_STATE = 34, 27
SPELL_SIZE = 0x18
VT_SPELL, VT_SPELL_ARENA = 0x515BA0, 0x51B4F8

# Additive constants of the scale table (0x306670-0x306760): scale[k] = cycle + ADD[k], with
# cycle = float((wave / 3) / recipe count) - the number of full passes through the recipes.
SCALE_ADD = [0x3F800000] * ARENA_CLASS_COUNT
SCALE_ADD[5] = 0x3F0666A9       # 0.525
SCALE_ADD[6] = 0x3F40C4CD       # 0.753
SCALE_ADD[7] = 0x3F12B042       # 0.573
SCALE_ADD[8] = 0x3F66A800       # 0.901
SCALE_ADD[10] = 0x3F3A9FF0      # 0.729
SCALE_ADD[14] = 0x3F410624      # 0.754


class Fault(Exception):
    """The original would use something it does not have (a null object, an unwritten
    stack word)."""


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def tdiv(a, b):
    """MIPS DIV quotient (toward zero).  A zero divisor leaves LO unpredictable."""
    if b == 0:
        raise Fault('division by a recipe count of 0')
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def arena_cycle(wave, recipe_count):
    """(signed wave / 3) / recipe count, both toward zero, as a float pattern."""
    return C.from_int(tdiv(tdiv(s16(wave), 3), s16(recipe_count)))


def arena_scale(cycle, class_index):
    """scale[k] = cycle + ADD[k] for k < 30.  k == 30 (a name not in the table) reads the
    stack word just past the table, which the function never writes: Fault."""
    if not 0 <= class_index < ARENA_CLASS_COUNT:
        raise Fault('class name not in the 30-entry table: the scale is an unwritten stack word')
    return C.add(cycle, SCALE_ADD[class_index])


def ring_point(centre, angle):
    """(cx + cos16(a) * 200, cy + sin16(a) * 200, cz)."""
    cx, cy, cz = centre
    return (C.add(cx, C.mul(C.cos16(s16(angle)), RING_RADIUS)),
            C.add(cy, C.mul(C.sin16(s16(angle)), RING_RADIUS)), cz)


class Host:
    """Call-outs; log is [(name, args)], answers[name](*args) gives a result."""

    def __init__(self, answers=None):
        self.log = []
        self.answers = dict(answers or {})

    def call(self, name, *args):
        self.log.append((name, args))
        f = self.answers.get(name)
        return f(*args) if f is not None else 0


def arena_spawn_monster(mem, host, class_name, creature, class_names):
    """arena_spawnMonster 0x3065fc (className, creature).

    mem         load/store memory with the arena globals
    class_name  bytes or None (a0 == 0: re-place an existing creature)
    creature    address of that creature (a1), used when class_name is None
    class_names the 30 names of 0x5037f0 (bytes), compared with strcmp(table[k], name)

    Ring search: up to 17 times, world_findFreeSpot(out, ring point, 0x60, 0x18, &ok, 0);
    after a miss the stored angle and the counter both gain 4000; the counter passing
    65536 ends the function with no monster.  Returns the object address or None."""
    cycle = arena_cycle(mem.load(G_WAVE, 2), mem.load(G_RECIPE_COUNT, 2))
    centre_at = mem.load(G_RING_CENTRE, 4)
    tries = 0
    while True:
        angle = mem.load(G_RING_ANGLE, 2)
        centre = tuple(mem.load(centre_at + 4 * k, 4) for k in range(3))
        point = ring_point(centre, angle)
        spot, ok = host.call('world_findFreeSpot', point, SPOT_RANGE, SPOT_RADIUS, 0)
        if ok & 0xFF:
            break
        tries += RETRY_STEP
        mem.store(G_RING_ANGLE, 2, (angle + RETRY_STEP) & 0xFFFF)
        if tries > RETRY_LIMIT:
            return None
    facing = s16(angle - FACING_FLIP)
    if class_name is not None:
        obj = host.call('world_createObject', class_name, spot, facing, G_ARENA_PROPS) & M32
        if obj == 0:
            raise Fault('world_createObject returned 0: the original writes flags at address 0xc')
        mem.store(obj + 0x0C, 4, mem.load(obj + 0x0C, 4) | OBJ_FLAG_ARENA)
        index = 0
        while index < ARENA_CLASS_COUNT and class_names[index] != class_name:
            index += 1
        scale = arena_scale(cycle, index)
        host.call('Creature_scaleStats', obj, scale, scale, scale, scale, scale)
    else:
        obj = creature & M32
        for k in range(3):
            mem.store(obj + 0x10 + 4 * k, 4, spot[k])
        mem.store(obj + 0x231, 1, 0)
        mem.store(obj + 0x38, 2, facing & 0xFFFF)
        host.call('Creature_clearStatus', obj)
    spell = host.call('pool_new', SPELL_SIZE) & M32
    if spell != 0:
        seed = (mem.load(G_RAND_SEED, 4) * 0x19660D + 0x3C6EF35F) & M32
        mem.store(G_RAND_SEED, 4, seed)
        mem.store(spell + 0x00, 1, 0)
        mem.store(spell + 0x04, 4, 0)
        mem.store(spell + 0x08, 4, 0)
        mem.store(spell + 0x0C, 4, obj)
        mem.store(spell + 0x10, 4, seed >> 16)
        mem.store(spell + 0x14, 4, VT_SPELL_ARENA)      # Spell's table first, then SpellArena's
    host.call('creature_addSpell', obj, spell)
    host.call('virtual', VSLOT_HOME_RANGE, obj, HOME_RANGE)
    host.call('virtual', VSLOT_AI_STATE, obj, 0)
    mem.store(G_RING_ANGLE, 2, (mem.load(G_RING_ANGLE, 2) + mem.load(G_RING_STEP, 2)) & 0xFFFF)
    return obj


# ---- ScriptGenerator_spawn --------------------------------------------------------------------
GEN_ANGLE_TURN = 0x4000         # the new object faces the generator's angle - a quarter turn
OBJ_FLAG_SCRIPTED = 1 << 24     # creature flag word +0xa8 (u64) |= 0x1000000
SKELETON_RISE_STATE = 0x17
TYPE_SKELETON = b'8Skeleton'


def script_generator_spawn(mem, host, generator, type_name_ptr, type_name, dynamic_type):
    """ScriptGenerator_spawn 0x265fc4 (generator, typeName).

    world_createObject(typeName, position = generator +0x10..+0x18 (copied),
    angle = s16(u16 generator +0x38 - 0x4000), props = word generator +0x2c).  When an
    object comes back: u64 +0xa8 |= 0x1000000, +0x34 = typeName (the same pointer
    world_createObject stored), then its RTTI (vtable entry 0) is compared with Skeleton's
    type_info (0x3cc62c, compared by 0x3b1250): only an object whose dynamic type is exactly
    Skeleton is put into AI state 0x17 (vtable slot 27).  A 0 result does nothing else.

    dynamic_type(obj) -> the RTTI name of the object (the test's stand-in for the vtable)."""
    pos = tuple(mem.load(generator + 0x10 + 4 * k, 4) for k in range(3))
    angle = s16(mem.load(generator + 0x38, 2) - GEN_ANGLE_TURN)
    props = mem.load(generator + 0x2C, 4)
    obj = host.call('world_createObject', type_name, pos, angle, props) & M32
    if obj == 0:
        return 0
    mem.store(obj + 0xA8, 8, mem.load(obj + 0xA8, 8) | OBJ_FLAG_SCRIPTED)
    mem.store(obj + 0x34, 4, type_name_ptr)
    if dynamic_type(obj) == TYPE_SKELETON:
        host.call('virtual', VSLOT_AI_STATE, obj, SKELETON_RISE_STATE)
    return obj


# ---- generateMonster: the name table ----------------------------------------------------------------
G_GEN_NAMES, GEN_NAME_SIZE = 0x5D32C8, 24
G_GEN_COUNT = 0x4F8409          # s8; game_clearLevel 0x1e4f98 sets it to 0


def intern_class_name(mem, name):
    """The interning half of generateMonster 0x1473d4: the first of the s8-count names equal
    to name (strcmp), else name is copied (strcpy, no length limit, so a name of 24 bytes or
    more runs into the next entry) to entry `count` after the count byte is raised.  Returns
    the entry address.  The count is signed: past 127 names the loop sees a negative count,
    finds nothing and writes in front of the table."""
    count = mem.load(G_GEN_COUNT, 1)
    count = count - 0x100 if count & 0x80 else count
    for k in range(max(count, 0)):
        at = G_GEN_NAMES + GEN_NAME_SIZE * k
        if _cstr(mem, at) == name:
            return at
    mem.store(G_GEN_COUNT, 1, (count + 1) & 0xFF)
    at = (G_GEN_NAMES + GEN_NAME_SIZE * count) & M32
    for k, b in enumerate(bytes(name) + b'\0'):
        mem.store(at + k, 1, b)
    return at


def _cstr(mem, addr, limit=4096):
    out = bytearray()
    while len(out) < limit:
        b = mem.load(addr + len(out), 1)
        if b == 0:
            break
        out.append(b)
    return bytes(out)


# ---- the factory rows the arena's 30 class names reach -----------------------------------------
# world_objectFactory 0x159c94 compares case-insensitively (docs/objects.md, "The object
# factory"); each match is pool_new(size) and one constructor call.  These rows are the
# factory tests the 30 names of 0x5037f0 meet first, keyed by the lower-case name:
# (pool size, constructor).  Names are short identifiers the executable exposes.
FACTORY_ARENA = {
    b'scorpion': (0x3D0, 0x2A4D68), b'mummy': (0x480, 0x298418), b'mummyking': (0x4A0, 0x29AFB4),
    b'goblin': (0x498, 0x26A624), b'orc2': (0x488, 0x2A0954), b'warboar': (0x3D8, 0x2BA03C),
    b'kobold': (0x3D0, 0x27F0C0), b'warwraith': (0x468, 0x2C07A8), b'ogre': (0x468, 0x29FAD0),
    b'fgoblin': (0x498, 0x26A624), b'clockworkhammer': (0x500, 0x24E124), b'demon': (0x468, 0x25DC6C),
    b'samurai': (0x480, 0x2BAFB4), b'gladiator': (0x480, 0x2BAFB4), b'tormentor': (0x3D8, 0x287998),
    b'blackwidow': (0x420, 0x2AB958), b'creep': (0x500, 0x253148), b'ghoul': (0x3D8, 0x266088),
    b'cyclopsnew': (0x458, 0x2566D4), b'firebeetle': (0x430, 0x24587C), b'hag': (0x3D8, 0x26F120),
    b'lavamonster': (0x430, 0x28048C), b'mosquito': (0x3C8, 0x297788), b'ant': (0x3E8, 0x235418),
    b'cloudgiant': (0x538, 0x2500B0), b'snobadge': (0x3D0, 0x244018), b'snowbeast': (0x3D8, 0x287998),
    b'demonwater': (0x468, 0x25DC6C), b'watskel': (0x478, 0x2A5AF4), b'seamonster': (0x3D0, 0x2A428C),
}


def factory_row(name):
    """(pool size, constructor) the factory picks for one of the arena names, any case;
    (None, None) for a name outside FACTORY_ARENA."""
    return FACTORY_ARENA.get(bytes(name).lower(), (None, None))


def _selftest():
    assert arena_cycle(0, 5) == 0
    assert arena_cycle(15, 5) == C.from_int(1)
    assert arena_cycle(-4, 5) == 0
    assert arena_scale(0, 0) == 0x3F800000
    try:
        arena_scale(0, 30)
    except Fault:
        pass
    else:
        raise AssertionError('index 30 must fault')
    print('ref_monster_build self-test passed')


if __name__ == '__main__':
    _selftest()
