#!/usr/bin/env python3
"""difftest_fx_skills.py - compare tools/ref_fx_skills.py with the game's own code: the
effect functions of the skill files that the skill models did not have (draw slots that
queue glows, and the run functions of a few effect objects), and the call-out table that
turns every recorded effect call into a primitive.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_fx_skills.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT]
                                      [-v] [--fpu MODEL] [--trace-first]

    --quick       a fifth of the cases
    --seed N      seed of the random cases (default 7337); a seed repeats exactly
    -k TEXT       only the groups whose name contains TEXT (draws, multifire, ...)
    -v            the first mismatches of a failing property, and blocks never entered
    --table FILE  write, per entry point, the least / most / total number of each effect
                  primitive one call of the ORIGINAL made (keep FILE local)
    --decode MODULE [options]
                  run another skill difftest (difftest_skills_a, _b, _c,
                  difftest_arena_monsters) unchanged and decode the call-outs of its
                  original runs as primitives (with --table, before --decode)
    --fpu MODEL   ps2 (default), ps2g1, chop or nearest: the adder model of both sides
    --trace-first stop at the first mismatching call and print both sides

How a property is tested
    This is tools/difftest_skills_c.py's rig with ref_fx_skills as the model: the ORIGINAL
    function is executed by tools/ee_emu.py (an instruction interpreter, not a console) on
    an object this script builds in the interpreter's memory; the model runs first on a
    copy-on-write view of the same memory.  Equal must be: the sequence of calls to
    everything outside (glow_add, particle_spawn, trail_addPoint ... with every argument,
    floats as 32-bit patterns), the bytes stored outside the stack, the shared seed, and
    the result.  Everything the function calls is a recording stub answered by a seeded
    script (isNearView, the model sample points, terrain ...) except the angle functions,
    the C library and the functions ref_skills_c / ref_fx_skills model, which run for real.
    Each case draws a fresh frame counter (negative ones included), positions, timers and
    the object's own fields.
"""
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import difftest_skills_c as DS                  # noqa: E402
import difftest_creature as DC                  # noqa: E402
import ref_fx_skills as FS                      # noqa: E402
import ref_creature as RC                       # noqa: E402
from difftest_creature import Res, f32, fl      # noqa: E402

M32 = 0xFFFFFFFF
ENTRY_ROWS, BODY_ROWS, SCENARIO_ROWS = [], [], []


class World(DS.World):
    def on_isNearView(self, args, view, rng):
        return Res(1 if rng.random() < 0.8 else 0)

    def on_Creature_v0(self, args, view, rng):
        return Res(rng.choice((FS.StaticFire.SF_TYPEINFO, 0x3D07B8)))

    def on_rtti_typeInfoEquals(self, args, view, rng):
        return Res(1 if args[0] == args[1] else 0)

    def on_mem_allocTagged(self, args, view, rng):
        if not hasattr(self, 'flame_block'):
            self.flame_block = self.emu.alloc(0xA00)
        return Res(self.flame_block)

    def on_obj_getPropStr(self, args, view, rng):
        return Res(0x00D40000 if rng.random() < 0.5 else 0)

    def on_obj_getPropInt(self, args, view, rng):
        return Res(rng.choice((0, 1, 1, 2, 8, 30)))


def install():
    """Turn tools/difftest_skills_c.py's rig into this test's: ref_fx_skills as the model,
    this world, these entry points and scenarios, and the call-out decoding."""
    DS.SK = FS
    DS.OPTIONS['seed'] = 7337
    DS.SCENARIOS[:] = SCENARIO_ROWS
    DS.GROUPS.pop('stats', None)
    DS.GROUPS.pop('shared', None)
    DS.LIB_STUBBED.add(0x3B1250)                # rtti_typeInfoEquals: a call-out (the tokens are getter addresses)
    DS.World = World
    for row in ENTRY_ROWS:
        DS.entry(*row)
    for row in BODY_ROWS:
        DS.body(*row)
    decode_callouts(DS)


def entry(key, addr, end, kinds, method, group, ret='n'):
    ENTRY_ROWS.append((key, addr, end, kinds, ret, method, group))


def body(key, addr, end, group):
    BODY_ROWS.append((key, addr, end, group))


def scenario(group, title):
    def register(function):
        SCENARIO_ROWS.append((group, title, function))
        return function
    return register


def reps(t, count):
    return max(2, count // 5) if DS.OPTIONS['quick'] else count


GLOW_TEXTURES = (FS.G_GLOW_TEX_A, FS.G_GLOW_TEX_B, FS.G_GLOW_TEX_C, FS.G_GLOW_TEX_RES, FS.G_GLOW_TEX_FIRE,
                 FS.G_GLOW_TEX_FIRE_DIM)


def set_frame(t):
    rng = t.rng
    for k, word in enumerate(GLOW_TEXTURES):         # resource words, distinct so a wrong one shows
        t.mem.w32(word, 0x00D30000 + 0x100 * k + rng.randrange(16))
    frame = rng.choice((rng.randrange(0, 4000), rng.randrange(0, 1 << 20), rng.randrange(1 << 31),
                        -rng.randrange(1, 1 << 20)))
    t.mem.w32(RC.G_SIM_FRAME, frame & M32)
    return frame


def put_vec(mem, addr, values):
    for i, v in enumerate(values):
        mem.wf32(addr + 4 * i, v)


def rand_pos(rng):
    return (rng.uniform(-4000, 4000), rng.uniform(-4000, 4000), rng.uniform(-200, 400))


def fresh(t, size):
    block = t.rig.emu.alloc(size)
    for off in range(0, size, 4):
        t.mem.w32(block + off, t.rng.getrandbits(32) if t.rng.random() < 0.0 else 0)
    return block


# ---------------------------------------------------------------------------------------
# the draw slots
# ---------------------------------------------------------------------------------------
entry('ShockProjectile_draw', 0x2C4E64, 0x2C4FA8, 'i', 'shock_draw', 'draws')
entry('FireArrowProjectile_draw', 0x2D67E8, 0x2D685C, 'i', 'firearrow_draw', 'draws')
entry('HolyStrike_draw', 0x2ECD90, 0x2ECF08, 'i', 'holystrike_draw', 'draws')
entry('SpellSummonBadger_draw', 0x311034, 0x3111D4, 'i', 'badger_draw', 'draws')
entry('SpellResurrect_draw', 0x312F48, 0x3130F4, 'i', 'resurrect_draw', 'draws')
entry('SmokeGen_draw', 0x31CBF8, 0x31CE2C, 'i', 'smokegen_draw', 'draws')


@scenario('draws', 'glow-queuing draw slots')
def scenario_draws(t):
    mem, rng = t.mem, t.rng
    obj = fresh(t, 0x500)
    for _ in range(reps(t, 400)):
        frame = set_frame(t)
        put_vec(mem, obj + 0x10, rand_pos(rng))
        # ShockProjectile: expiry around now
        mem.w32(obj + 0x58, (frame + rng.randrange(-400, 400)) & M32)
        t.do('ShockProjectile_draw', obj)
        # FireArrowProjectile: the radius
        mem.wf32(obj + 0x1C, rng.choice((0.0, 1.0, 3.5, 8.0, 16.0, rng.uniform(0, 40))))
        t.do('FireArrowProjectile_draw', obj)
        # HolyStrike: a direction, sometimes zero length
        d = rng.choice(((0.0, 0.0), (1.0, 0.0), (rng.uniform(-50, 50), rng.uniform(-50, 50))))
        mem.wf32(obj + 0x6C, d[0])
        mem.wf32(obj + 0x70, d[1])
        t.do('HolyStrike_draw', obj)


@scenario('draws', 'summon and resurrect glows')
def scenario_spell_draws(t):
    mem, rng, world = t.mem, t.rng, t.world
    spell = fresh(t, 0x80)
    node = fresh(t, 0x20)
    for _ in range(reps(t, 300)):
        frame = set_frame(t)
        world.reset_objects(rng)
        badger = rng.choice(world.monsters)
        mem.w32(spell + 0x18, node if rng.random() < 0.9 else 0)
        mem.w32(node + 0xC, badger if rng.random() < 0.9 else 0)
        mem.wf32(spell + 0x1C, rng.choice((0.0, 0.5, 1.0, 1.5, 2.0, 2.5, rng.uniform(-1, 3))))
        mem.wf32(badger + 0xDC, rng.choice((1.0, 0.5, 2.0)))
        t.do('SpellSummonBadger_draw', spell)
        mem.w32(FS.G_NUM_PLAYERS, rng.choice((1, 1, 1, 2, 4)))
        mem.w32(spell + 0x20, rng.choice((0, 1)))
        mem.w32(spell + 0x6C, (frame - rng.choice((0, 1, 30, 59, 60, 61, 500, -5))) & M32)
        t.do('SpellResurrect_draw', spell)


@scenario('draws', 'smoke generator puffs')
def scenario_smoke(t):
    mem, rng = t.mem, t.rng
    obj = fresh(t, 0x500)
    for _ in range(reps(t, 300)):
        set_frame(t)
        put_vec(mem, obj + 0x10, rand_pos(rng))
        for i in range(100):
            for k in range(5):
                mem.w16(obj + 0x50 + 10 * i + 2 * k, rng.randrange(-3000, 3000) & 0xFFFF)
        first = rng.randrange(100)
        mem.w16(obj + 0x438, first)
        mem.w16(obj + 0x43A, rng.choice((first, (first + rng.randrange(1, 100)) % 100)))
        for off in range(0x43C, 0x464, 4):
            mem.w32(obj + off, rng.randrange(0, 256) & M32)
        mem.w32(obj + 0x45C, rng.randrange(1000, 20000))
        mem.w32(obj + 0x460, rng.randrange(1000, 20000))
        mem.w32(obj + 0x464, rng.choice((1, 2, 3, 5)))
        mem.wf32(obj + 0x474, rng.choice((1.0, 0.5, 2.0)))
        mem.wf32(obj + 0x47C, rng.uniform(0, 50))
        mem.w32(obj + 0x488, rng.randrange(0, 4000))
        mem.w16(obj + 0x472, rng.randrange(-200, 200) & 0xFFFF)
        mem.w32(obj + 0x4C, 0x00D20000 + rng.randrange(16))
        t.do('SmokeGen_draw', obj)


# ---------------------------------------------------------------------------------------
# MultiFireProjectile
# ---------------------------------------------------------------------------------------
entry('MultiFireProjectile_ctor', 0x2DA164, 0x2DA2BC, 'iviiii', 'multifire_ctor', 'multifire')
entry('MultiFireProjectile_run', 0x2DA2BC, 0x2DA550, 'i', 'multifire_run', 'multifire')
entry('MultiFireProjectile_end', 0x2DA928, 0x2DAA4C, 'ii', 'multifire_end', 'multifire')


def to_vec(values):
    return tuple(f32(v) for v in values)


@scenario('multifire', 'arrows of Multi Fire from launch to end')
def scenario_multifire(t):
    mem, rng, world = t.mem, t.rng, t.world
    skills = sorted(t.skills.values())
    for _ in range(reps(t, 40)):
        set_frame(t)
        world.reset_objects(rng)
        obj = fresh(t, 0x80)
        owner = rng.choice(world.objects + [0])
        mem.w32(FS.MultiFire.LEVEL_FLAGS, rng.choice((0, 0x40000, 0x10040000)))
        t.do('MultiFireProjectile_ctor', obj, to_vec(rand_pos(rng)), rng.randrange(0x10000),
             owner, rng.randrange(0, 41), rng.choice(skills))
        if rng.random() < 0.4:
            mem.w32(obj + 0x6C, rng.choice((590, 598, 599, 600)))
        for _tick in range(rng.choice((3, 10, 30, 700))):
            if mem.u32(obj + 0x60):
                break
            t.tick()
            t.do('MultiFireProjectile_run', obj)
        mem.w32(obj + 0x60, 0)
        t.do('MultiFireProjectile_end', obj, rng.choice((0, 1, 2)))


# ---------------------------------------------------------------------------------------
# FireStormFlare
# ---------------------------------------------------------------------------------------
entry('FireStormFlare_run', 0x2D33C0, 0x2D4048, 'i', 'firestormflare_run', 'firestorm')


@scenario('firestorm', 'Fire Storm flares from the sky to the scorch mark')
def scenario_flare(t):
    mem, rng, world = t.mem, t.rng, t.world
    for _ in range(reps(t, 30)):
        frame = set_frame(t)
        obj = fresh(t, 0x80)
        mem.w32(obj + 0x48, world.vt_creature)
        put_vec(mem, obj + 0x10, rand_pos(rng))
        put_vec(mem, obj + 0x5C, (rng.uniform(-6, 6), rng.uniform(-6, 6), rng.uniform(-12, 2)))
        mem.w32(obj + 0x44, rng.getrandbits(32))
        mem.wf32(obj + 0x4C, rng.choice((0.25, 0.5, 1.0, 1.3, 2.0, 0.0)))
        mem.wf32(obj + 0x1C, rng.choice((8.0, 12.0, 20.0)))
        mem.w32(obj + 0x68, (frame + rng.choice((0, 5, 40, 200))) & M32)
        mem.w32(obj + 0x50, rng.choice((0, 0, 0, 1)))
        mem.w16(obj + 0x58, rng.choice((0, 0, 30, 200)))
        for _tick in range(rng.choice((2, 10, 60))):
            t.tick()
            t.do('FireStormFlare_run', obj)


# ---------------------------------------------------------------------------------------
# Pustule
# ---------------------------------------------------------------------------------------
entry('Pustule_run', 0x30BDE0, 0x30C4AC, 'i', 'pustule_run', 'pusstorm')


@scenario('pusstorm', 'Pus Storm blobs: fall, burst, drops, end')
def scenario_pustule(t):
    mem, rng, world = t.mem, t.rng, t.world
    for _ in range(reps(t, 30)):
        set_frame(t)
        obj = fresh(t, 0x180)
        mem.w32(obj + 0x48, world.vt_creature)
        pos = rand_pos(rng)
        put_vec(mem, obj + 0x10, pos)
        put_vec(mem, obj + 0x58, (rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-8, 1)))
        mem.wf32(obj + 0x54, pos[2] - rng.choice((0.0, 5.0, 30.0, 120.0)))
        mem.w32(obj + 0x44, rng.getrandbits(32))
        mem.w32(obj + 0x64, rng.choice((0, 0, 10, 299, 300)))
        mem.w32(obj + 0x6C, rng.choice((0, 0, 0, 1)))
        for _tick in range(rng.choice((2, 20, 80))):
            t.tick()
            t.do('Pustule_run', obj)


# ---------------------------------------------------------------------------------------
# DiseaseCloud
# ---------------------------------------------------------------------------------------
entry('DiseaseCloud_run', 0x2CE6E0, 0x2CEF7C, 'i', 'diseasecloud_run', 'diseasecloud')


@scenario('diseasecloud', 'disease clouds growing, hurting, ending')
def scenario_cloud(t):
    mem, rng, world = t.mem, t.rng, t.world
    node = fresh(t, 0x20)
    for _ in range(reps(t, 30)):
        frame = set_frame(t)
        world.reset_objects(rng)
        obj = fresh(t, 0x80)
        mem.w32(obj + 0x48, world.vt_creature)
        put_vec(mem, obj + 0x10, (2000.0 + rng.uniform(-50, 50), 3000.0 + rng.uniform(-50, 50), 10.0))
        mem.w32(obj + 0x44, rng.getrandbits(32))
        mem.w32(obj + 0x54, (frame + rng.choice((0, 3, 40, 100))) & M32)
        mem.w32(obj + 0x58, rng.choice((0, 9, 10, 25, 60, 120)))
        mem.wf32(obj + 0x5C, rng.choice((0.0, 10.0, 59.5, 200.0)))
        mem.w32(obj + 0x60, rng.randrange(0, 70000))
        owner = rng.choice(world.objects)
        mem.w32(node + 0xC, owner)
        mem.w32(obj + 0x4C, node if rng.random() < 0.85 else 0)
        for _tick in range(rng.choice((2, 31, 61))):
            t.tick()
            t.do('DiseaseCloud_run', obj)


# ---------------------------------------------------------------------------------------
# SpellArena
# ---------------------------------------------------------------------------------------
entry('SpellArena_run', 0x305BBC, 0x305E9C, 'iv', 'arena_run', 'arena')


@scenario('arena', 'the arena spell over its counter')
def scenario_arena(t):
    mem, rng, world = t.mem, t.rng, t.world
    spell = fresh(t, 0x40)
    for _ in range(reps(t, 300)):
        set_frame(t)
        world.reset_objects(rng)
        c = rng.choice(world.objects)
        mem.w32(spell + 0xC, c)
        mem.w32(spell + 0x10, rng.getrandbits(32))
        mem.w16(FS.Arena.G_ARENA_COUNTER, rng.choice((0, 29, 30, 31, 60, 61, 100, 180, 200, 400,
                                                     rng.randrange(-100, 400))) & 0xFFFF)
        t.do('SpellArena_run', spell, to_vec(rand_pos(rng)))


# ---------------------------------------------------------------------------------------
# SpellHornOmenEffect
# ---------------------------------------------------------------------------------------
entry('SpellHornOmenEffect_ctor', 0x2FC574, 0x2FC610, 'iiii', 'hornomen_ctor', 'hornomen')
entry('SpellHornOmenEffect_run', 0x2FC684, 0x2FCE8C, 'iv', 'hornomen_run', 'hornomen')


@scenario('hornomen', 'horn omen glow from start to end')
def scenario_hornomen(t):
    mem, rng, world = t.mem, t.rng, t.world
    for _ in range(reps(t, 25)):
        set_frame(t)
        world.reset_objects(rng)
        c = rng.choice(world.objects)
        spell = fresh(t, 0x40)
        t.do('SpellHornOmenEffect_ctor', spell, rng.randrange(256), c, rng.getrandbits(32))
        if rng.random() < 0.5:
            mem.w32(spell + 0x18, (mem.u32(spell + 0x18) - rng.choice((100, 135, 139, 140, 141, 300, 598))) & M32)
        for _tick in range(rng.choice((1, 4, 12))):
            t.tick(rng.choice((1, 1, 7, 30)))
            t.do('SpellHornOmenEffect_run', spell, to_vec(rand_pos(rng)))


# ---------------------------------------------------------------------------------------
# SpellPlanarSteelEffect
# ---------------------------------------------------------------------------------------
entry('SpellPlanarSteelEffect_ctor', 0x2FB728, 0x2FB924, 'iiii', 'planarsteel_ctor', 'planarsteel')
entry('SpellPlanarSteelEffect_run', 0x2FB9B4, 0x2FC3AC, 'iv', 'planarsteel_run', 'planarsteel')


@scenario('planarsteel', 'planar steel from start to end')
def scenario_planarsteel(t):
    mem, rng, world = t.mem, t.rng, t.world
    for _ in range(reps(t, 25)):
        set_frame(t)
        world.reset_objects(rng)
        c = rng.choice(world.objects)
        spell = fresh(t, 0x80)
        t.do('SpellPlanarSteelEffect_ctor', spell, rng.randrange(256), c, rng.getrandbits(32))
        if rng.random() < 0.3:
            mem.w16(spell + 0x1C, rng.choice((0, 1, 2)))
        if rng.random() < 0.25:
            mem.w32(spell + 0x24, (mem.u32(RC.G_SIM_FRAME) + rng.choice((0, 1, 2, 3))) & M32)
        for _tick in range(rng.choice((1, 4, 12))):
            t.tick(rng.choice((1, 1, 7, 30)))
            t.do('SpellPlanarSteelEffect_run', spell, to_vec(rand_pos(rng)))


# ---------------------------------------------------------------------------------------
# StaticFire
# ---------------------------------------------------------------------------------------
entry('StaticFire_ctor', 0x2C5240, 0x2C54F8, 'iviiiff', 'staticfire_ctor', 'staticfire')
entry('StaticFire_ctor2', 0x2C54F8, 0x2C5770, 'ivii', 'staticfire_ctor2', 'staticfire')
body('StaticFire_initCommon', 0x2C5814, 0x2C595C, 'staticfire')
body('StaticFire_wind', 0x2C6AA8, 0x2C6BC0, 'staticfire')
body('StaticFire_addFlame', 0x2C6BC0, 0x2C6DF0, 'staticfire')
body('StaticFire_moveFlames', 0x2C6DF0, 0x2C6EA0, 'staticfire')
entry('StaticFire_run', 0x2C595C, 0x2C65E8, 'i', 'staticfire_run', 'staticfire')
entry('StaticFire_draw', 0x2C65E8, 0x2C6AA8, 'i', 'staticfire_draw', 'staticfire')


def level_name(t):
    mem, rng = t.mem, t.rng
    cut = bytes(mem.read(FS.StaticFire.SF_LEVEL_CUTSCENE, 32)).split(b'\0')[0]
    dark = bytes(mem.read(FS.StaticFire.SF_LEVEL_DARK, 32)).split(b'\0')[0]
    name = rng.choice((cut, b'X' + dark + b'2', dark, b'town', b''))
    mem.write(FS.StaticFire.LEVEL_NAME, name + b'\0')


@scenario('staticfire', 'fires on the ground: made, burning, dying, drawn')
def scenario_staticfire(t):
    mem, rng, world = t.mem, t.rng, t.world
    skills = sorted(t.skills.values())
    for _ in range(reps(t, 60)):
        set_frame(t)
        world.reset_objects(rng, spread=40)
        level_name(t)
        mem.w32(FS.StaticFire.SF_SKILL, rng.choice(skills))
        mem.wf32(RC.G_LEVEL_MONSTER_LEVEL, rng.choice((1.0, 7.0, 25.0)))
        mem.w8(RC.G_CUTSCENE_ACTIVE, rng.choice((0, 0, 1)))
        obj = fresh(t, 0x4B0)
        world.query = None
        pos = (2000.0 + rng.uniform(-20, 20), 3000.0 + rng.uniform(-20, 20), rng.choice((10.0, -300.0, -470.0, 300.0)))
        if rng.random() < 0.6:
            t.do('StaticFire_ctor', obj, to_vec(pos), rng.choice((-1, 0, 1, 60, 121, 400)),
                 rng.choice(world.objects + [0]), rng.choice((0, 0, 1)),
                 f32(rng.choice((240.0, 480.0, 60.0))), f32(rng.choice((1.0, 0.5, 2.0))))
        else:
            t.do('StaticFire_ctor2', obj, to_vec(pos), 0, rng.getrandbits(32))
            mem.w32(obj + 0x7C, rng.choice((-1, -1, 0, 5, 200)) & M32)
        if rng.random() < 0.5:
            mem.w32(obj + 0x4A8, rng.choice(world.objects + [0]))
        if rng.random() < 0.3:
            mem.wf32(obj + 0x60, rng.choice((80.0, 108.0, 95.0)))
        if rng.random() < 0.3:
            mem.wf32(obj + 0x64, rng.choice((0.004, 0.5, 0.995, 1.0)))
        if rng.random() < 0.3:                      # the ring's head and tail near its end: the wrap
            end = mem.u16(obj + 0x76)
            mem.w16(obj + 0x78, end - 1)
            mem.w16(obj + 0x7A, end - 1)
        for _tick in range(rng.choice((5, 40, 150, 300))):
            t.tick()
            t.do('StaticFire_run', obj)
            if rng.random() < 0.3:
                t.do('StaticFire_draw', obj)


DECODED = {'calls': 0, 'effects': 0, 'bad': 0, 'examples': [], 'kinds': {}, 'per': {}}
TABLE = {'path': None}


def decode_callouts(module):
    """Wrap module.Rig.compare: after the rig's comparison every call-out the ORIGINAL
    made is turned into an effect primitive with ref_fx_skills.to_primitive; a call-out
    the table names must decode, field for field, from the arguments the original passed."""
    original = module.Rig.compare

    def compare_and_decode(self, *args, **kw):
        out = original(self, *args, **kw)
        if isinstance(out, dict):
            effects = decode(out.get('emu_calls') or ())
            tally(str(args[0]) if args else '?', effects)
        return out
    module.Rig.compare = compare_and_decode


def tally(key, effects):
    """Per entry point: how many calls, and per primitive the least, most and total
    number made in one call (the executed counts of the recipe table)."""
    per = DECODED['per'].setdefault(key, {'calls': 0, 'prims': {}})
    per['calls'] += 1
    counts = {}
    for fx in effects:
        counts[fx.primitive] = counts.get(fx.primitive, 0) + 1
    for prim in set(counts) | set(per['prims']):
        n = counts.get(prim, 0)
        row = per['prims'].setdefault(prim, [0 if per['calls'] > 1 else n, n, 0])
        row[0], row[1], row[2] = min(row[0], n), max(row[1], n), row[2] + n


def write_table(path):
    with open(path, 'w') as f:
        f.write('# entry point\tcalls\tprimitive\tleast\tmost\ttotal (executed under tools/ee_emu.py)\n')
        for key in sorted(DECODED['per']):
            per = DECODED['per'][key]
            for prim, (least, most, total) in sorted(per['prims'].items()):
                f.write('%s\t%d\t%s\t%d\t%d\t%d\n' % (key, per['calls'], prim, least, most, total))


def decode(calls):
    effects = []
    for name, cargs in calls:
        DECODED['calls'] += 1
        if name not in FS.CALLOUTS:
            continue
        try:
            fx = FS.to_primitive(name, cargs)
            fields = FS.CALLOUTS[name].fields
            if fields is not None and len(fx.fields) != len(fields):
                raise ValueError('%d fields' % len(fx.fields))
            DECODED['effects'] += 1
            DECODED['kinds'][fx.primitive] = DECODED['kinds'].get(fx.primitive, 0) + 1
            effects.append(fx)
        except Exception as exc:                # noqa: BLE001 - a decode failure is a result
            DECODED['bad'] += 1
            if len(DECODED['examples']) < 6:
                DECODED['examples'].append('%s%r: %r' % (name, cargs, exc))
    return effects


def main(argv):
    argv = list(argv)
    if '--table' in argv:
        i = argv.index('--table')
        TABLE['path'] = argv[i + 1]
        del argv[i:i + 2]
    if any(a in ('-h', '--help') for a in argv[1:]):
        print(__doc__)
        return 0
    if len(argv) > 2 and argv[1] == '--decode':
        # run another skill difftest unchanged, decoding the call-outs of its original runs
        import importlib
        module = importlib.import_module(argv[2])
        decode_callouts(module)
        # tools/difftest_skills_c.py takes the whole argument vector, the others argv[1:]
        status = module.main([argv[2]] + argv[3:] if module is DS else argv[3:])
        report_decoded(module.report if hasattr(module, 'report') else DS.report)
        return status or (1 if DECODED['bad'] else 0)
    install()
    status = DS.main(argv)
    report_decoded(DS.report)
    return status or (1 if DECODED['bad'] else 0)


def report_decoded(report):
    if TABLE['path']:
        write_table(TABLE['path'])
    if DECODED['calls']:
        report('call-outs decoded as primitives', DECODED['bad'], DECODED['effects'],
               ' '.join('%s:%d' % kv for kv in sorted(DECODED['kinds'].items())), DECODED['examples'])


if __name__ == '__main__':
    sys.exit(main(sys.argv))
