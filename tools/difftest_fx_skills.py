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
DS.SK = FS                                      # the rig runs this module's Model
DS.OPTIONS['seed'] = 7337
DS.SCENARIOS[:] = []
DS.GROUPS.pop('stats', None)
DS.GROUPS.pop('shared', None)


class World(DS.World):
    def on_isNearView(self, args, view, rng):
        return Res(1 if rng.random() < 0.8 else 0)


DS.World = World


def entry(key, addr, end, kinds, method, group, ret='n'):
    DS.entry(key, addr, end, kinds, ret, method, group)


def scenario(group, title):
    def register(function):
        DS.SCENARIOS.append((group, title, function))
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


def main(argv):
    if any(a in ('-h', '--help') for a in argv[1:]):
        print(__doc__)
        return 0
    return DS.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
