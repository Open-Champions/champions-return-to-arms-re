#!/usr/bin/env python3
"""difftest_combat_walk.py - does a player walk again after an attack, and what does the
search a stuck creature makes beside a walking player return?  Both on the game's own code.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_combat_walk.py [path/to/SLUS_209.73] [--quick] [--seed N] [-k TEXT] [-v]

    --quick   a tenth of the cases
    --seed N  seed of the scenarios (default 20973); a seed repeats exactly
    -k TEXT   only the properties whose name contains TEXT
    -v        print the first mismatches of a failing property

Part 1: walk after attack (Player_run 0x1a5030)
    The ORIGINAL Player_run runs in tools/ee_emu.py on the player tools/difftest_player.py
    builds, through difftest_player's Rig: each tick tools/ref_player.py runs first on a
    copy-on-write view, then the original, and the calls (with arguments), the bytes stored,
    the shared seed and the exit must be equal (difftest_player's comparison, unchanged).
    What is new is the pad script and a calm world (CalmWorld): no damage, no stray events,
    the stick held at full deflection in a seeded direction, the attack button pressed as
    the scenario says.  Then, on what the ORIGINAL did:

      once         one press, stick held: action state 1 (melee) ends - it stores state 2
                   (neutral) - and from the next tick on every tick calls Player_move with
                   mode 0 (walking) and the held stick
      mash.stop    presses every k ticks (k and the count from the seed), then none: state 1
                   ends no later than 40 ticks after the last swing started, then mode 0
      mash.12      a press every 12 ticks for the whole run (the netplay fixture's cadence):
                   state 1 never ends, each press after the swing window chains the next
                   swing (+0x448 restarts on a press: every 24 ticks at speed 1, every 12
                   with enough haste), and Player_move is never called with mode 0
      release      one press, stick released: state 1 ends at +0x470 x 60 ticks instead
    for each melee weapon class difftest_player builds (sword 0, sword2h 1, axe2h 2,
    spear 3, fist 5, dual 7).

Part 2: world_findFreeSpot 0x14acf8 with the creature caller's arguments
    Creature_moveTo's stuck recovery (ref_creature.py) calls world_findFreeSpot(position,
    72, radius, 0).  The ORIGINAL runs on the object world tools/difftest_objects.py builds
    with the original constructors (its Rig and Driver, unchanged); tools/ref_objects.py's
    find_free_spot runs on the same world as Python objects.  Objects stand around the
    centre the way a fight places them (radius 16 for players, 12 for creatures, some
    not solid), the terrain answers are the composed runtime's flat floor (blocked 0.0,
    height = the floor; tools/ref_combat_walk.py), and must be equal: the returned point,
    the ok byte, the terrain calls with their arguments, the shared seed and the whole
    object world afterwards (difftest_objects' full check).

What runs for real and what is a stub: as in tools/difftest_player.py (part 1) and
tools/difftest_objects.py (part 2).
"""
import hashlib
import math
import os
import random
import struct
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
import ref_core as R                            # noqa: E402
import ref_player as RP                         # noqa: E402
import difftest_player as DP                    # noqa: E402
import difftest_objects as DO                   # noqa: E402

EXPECTED_SHA256 = DP.EXPECTED_SHA256
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
OPTIONS = {'quick': False, 'seed': 20973, 'filter': None, 'verbose': False}
RESULTS = []
Res, f32, rd = DP.Res, DP.f32, DP.rd

WEAPONS = ('sword', 'sword2h', 'axe2h', 'spear', 'fist', 'dual')
ATTACK = DP.BTN['attack']
ONE = 0x3F800000


def wanted(name):
    return OPTIONS['filter'] is None or OPTIONS['filter'].lower() in name.lower()


def report(name, failures, count, text, examples=()):
    ok = not failures
    RESULTS.append((name, ok))
    print('%s  %-30s %6d cases  %s%s' % ('PASS' if ok else 'FAIL', name, count, text,
                                         '' if ok else '  [%d mismatches]' % failures))
    if not ok and OPTIONS['verbose']:
        for line in examples[:4]:
            print('        ' + str(line)[:900])
    sys.stdout.flush()


# =======================================================================================
# Part 1: Player_run
# =======================================================================================
class CalmWorld(DP.World):
    """difftest_player.World with the answers that would interrupt a swing held still:
    no damage or death (Player_processDamage), no stray animation events or flag changes
    (Player_animStep), Player_move lands the player and moves nothing (its own body is
    executed by difftest_combat_move), no frozen game, dialog, menu, camera switch or
    spell.  Every other answer is difftest_player's seeded script."""

    def on_net_getCamFlag(self, args, view, rng):
        return Res(0)

    def on_game_isFrozen(self, args, view, rng):
        return Res(0)

    def on_memcard_isBusy(self, args, view, rng):
        return Res(0)

    def on_dialog_isOpen(self, args, view, rng):
        return Res(0)

    def on_task_isRunning(self, args, view, rng):
        return Res(0)

    def on_net_isSlotActive(self, args, view, rng):
        return Res(1)

    def on_Creature_run(self, args, view, rng):
        return Res()

    def on_Player_animStep(self, args, view, rng):
        return Res(0)

    def on_Player_move(self, args, view, rng):
        view.poke(args[0] + 0x482, 1, 15)
        return Res(0)

    def on_Player_processDamage(self, args, view, rng):
        return Res()

    def on_creature_findSpellByType(self, args, view, rng):
        return Res(0)


def make_rig(elf, seed, weapon):
    rig = DP.Rig(elf, seed, 0, 0, 0)
    world = rig.world
    world.__class__ = CalmWorld
    rng = random.Random(seed * 31 + WEAPONS.index(weapon))
    mem = rig.emu.mem
    world.equip(world.slot, weapon, rng)
    P, Rr = world.P, world.R
    mem.wf32(Rr + 0xAC, 200.0)
    mem.wf32(Rr + 0xB0, 200.0)
    mem.w32(P + 0x58C, 2)
    mem.w8(P + 0x2FC, 0)
    mem.w32(P + 0x374, 0)
    mem.w32(P + 0x37C, 0)
    mem.w32(P + 0x488, 0)
    mem.w32(P + 0x450, 0)
    mem.w32(P + 0xC, mem.u32(P + 0xC) & ~0x20000)
    return rig, rng


class Pad:
    def __init__(self, rig, angle):
        self.rig, self.mem = rig, rig.emu.mem
        self.addr = RP.G_PADS + rig.world.slot * RP.PAD_SIZE
        self.lx, self.ly = f32(math.cos(angle)), f32(math.sin(angle))
        self.held = 0

    def set(self, press, stick):
        held = ATTACK if press else 0
        self.mem.w32(self.addr + 8, held)
        self.mem.w32(self.addr + 0xC, held & ~self.held)
        self.held = held
        self.mem.w32(self.addr + 0x14, self.lx if stick else 0)
        self.mem.w32(self.addr + 0x18, self.ly if stick else 0)


class Walk:
    """One scripted run: presses at the given ticks, the stick held from `stick_from` on."""

    def __init__(self, elf, seed, weapon, presses, ticks, stick=True):
        self.rig, rng = make_rig(elf, seed, weapon)
        self.weapon = weapon
        self.pad = Pad(self.rig, rng.uniform(0, 2 * math.pi))
        self.presses, self.ticks, self.stick = set(presses), ticks, stick
        self.states, self.starts, self.moves = [], [], []
        self.bad = []
        self.compared = 0

    def run(self):
        rig, mem = self.rig, self.rig.emu.mem
        P = rig.world.P
        for t in range(self.ticks):
            # the stick: held in walking scenarios; in `release` only before the press
            stick = self.stick if self.stick is not None else t < min(self.presses or {0})
            self.pad.set(t in self.presses, stick)
            before = mem.s32(P + 0x58C)
            result = rig.tick(OPTIONS['seed'] * 1000003 + t)
            if result['fault']:
                self.bad.append('tick %d: fault model %r original %r' % (t, result['model_error'],
                                                                          result['emu_error']))
                return
            self.compared += 1
            for key, text in (('calls_ok', 'calls'), ('set_ok', 'stores'), ('values_ok', 'values'),
                              ('seed_ok', 'seed')):
                if not result[key]:
                    self.bad.append('tick %d state %d: %s differ' % (t, before, text))
            modes = [c[1][1] for c in result['emu_calls'] if c[0] == 'Player_move']
            self.moves.append(modes)
            self.states.append(mem.s32(P + 0x58C))
            self.starts.append(mem.u32(P + 0x448))
            mem.w32(RP.G_SIM_FRAME, (mem.u32(RP.G_SIM_FRAME) + 1) & M32)
        if rig.unknown:
            self.bad.append('calls to addresses neither real nor stubs: %r' % rig.unknown)

    # what the original did, after the run
    def melee_end(self, after):
        """First tick >= after at which the original stored state 2 after being in 1."""
        for t in range(max(after, 1), len(self.states)):
            if self.states[t - 1] == 1 and self.states[t] == 2:
                return t
        return None

    def walking_from(self, t0):
        """Every tick from t0 on is state 2 and calls Player_move with mode 0 only."""
        return all(self.states[t] == 2 and self.moves[t] == [0] for t in range(t0, len(self.states)))


def scenario_walk(elf, rng):
    cases = {'once': [0, []], 'mash.stop': [0, []], 'mash.12': [0, []], 'release': [0, []]}
    figures = {'once': set(), 'mash.stop': set(), 'mash.12': set(), 'release': set()}
    compared = 0
    runs = 1 if OPTIONS['quick'] else 3
    for weapon in WEAPONS:
        for n in range(runs):
            seed = OPTIONS['seed'] * 100 + WEAPONS.index(weapon) * 10 + n
            first = rng.randrange(4, 20)
            # once
            w = Walk(elf, seed, weapon, [first], first + 120)
            w.run()
            compared += w.compared
            cases['once'][0] += 1
            end = w.melee_end(first + 1)
            if w.bad:
                cases['once'][1] += w.bad[:2]
            elif w.states[first] != 1:
                cases['once'][1].append('%s: the press at %d did not start a swing (state %d)'
                                        % (weapon, first, w.states[first]))
            elif end is None or not w.walking_from(end + 1):
                cases['once'][1].append('%s: no return to walking (end %r)' % (weapon, end))
            else:
                figures['once'].add(end - first)
            # mash, then stop
            k, count = rng.randrange(6, 30), rng.randrange(2, 7)
            presses = [first + k * i for i in range(count)]
            w = Walk(elf, seed, weapon, presses, presses[-1] + 140)
            w.run()
            compared += w.compared
            cases['mash.stop'][0] += 1
            last = presses[-1]
            end = w.melee_end(last)
            if w.bad:
                cases['mash.stop'][1] += w.bad[:2]
            elif end is None or not w.walking_from(end + 1):
                cases['mash.stop'][1].append('%s k=%d n=%d: no return to walking (end %r)' % (weapon, k, count, end))
            else:
                # the last swing start the original stored, as a tick of this run
                start_tick = max(t for t in range(1, end) if w.starts[t] != w.starts[t - 1])
                if end - start_tick > 40:
                    cases['mash.stop'][1].append('%s: ended %d ticks after the last swing' % (weapon, end - start_tick))
                figures['mash.stop'].add(end - start_tick)
            # mash every 12 ticks, forever
            presses = list(range(first, first + 240, 12))
            w = Walk(elf, seed, weapon, presses, first + 240)
            w.run()
            compared += w.compared
            cases['mash.12'][0] += 1
            restarts = [t for t in range(first + 1, len(w.starts)) if w.starts[t] != w.starts[t - 1]]
            gaps = {b - a for a, b in zip(restarts, restarts[1:])}
            if w.bad:
                cases['mash.12'][1] += w.bad[:2]
            elif any(s != 1 for s in w.states[first:]):
                cases['mash.12'][1].append('%s: left state 1 at %d' % (weapon, next(
                    t for t in range(first, len(w.states)) if w.states[t] != 1)))
            elif any(0 in m for m in w.moves[first:]):
                cases['mash.12'][1].append('%s: Player_move mode 0 during the combo' % weapon)
            elif not gaps or any(g % 12 for g in gaps):
                cases['mash.12'][1].append('%s: swing restarts %r' % (weapon, sorted(gaps)))
            else:
                figures['mash.12'] |= gaps
            # release the stick after one press
            w = Walk(elf, seed, weapon, [first], first + 160, stick=None)
            w.run()
            compared += w.compared
            cases['release'][0] += 1
            end = w.melee_end(first + 1)
            duration = R.to_float(w.rig.emu.mem.u32(w.rig.world.P + 0x470)) if end else None
            if w.bad:
                cases['release'][1] += w.bad[:2]
            elif end is None:
                cases['release'][1].append('%s: state 1 never ended' % weapon)
            else:
                figures['release'].add(end - first)
    text = {
        'once': 'one press, stick held: state 1 stores 2, then Player_move mode 0 every tick '
                '(ticks from the swing start: %s)' % sorted(figures['once']),
        'mash.stop': 'presses every 6..29 ticks, then none: back to mode 0 within 40 ticks of the last '
                     'swing (%s)' % sorted(figures['mash.stop']),
        'mash.12': 'a press every 12 ticks: state 1 never ends, a press past the swing window chains the '
                   'next swing (restart gaps %s), no mode 0' % sorted(figures['mash.12']),
        'release': 'one press, stick released: state 1 ends (ticks after the press: %s)'
                   % sorted(figures['release']),
    }
    for key, (count, bad) in cases.items():
        name = 'walk.' + key
        if wanted(name):
            report(name, len(bad), count, text[key], bad)
    return compared


# =======================================================================================
# Part 2: world_findFreeSpot with Creature_moveTo's arguments
# =======================================================================================
def scenario_free_spot(rig):
    driver = DO.Driver(rig, cap=120)
    rng = rig.rng
    m = rig.model
    mem = rig.emu.mem
    mem.w32(DO.G_WORLD, 0x00ABC000)
    floor = {'z': 0}

    def terrain_blocked(radius, pos):
        return rig.m_call('blocked', (radius, tuple(pos)), 0)

    def terrain_height(radius, pos):
        return rig.m_call('height', (radius, tuple(pos)), floor['z'])

    def e_blocked(emu):
        emu.f[0] = rig.e_call('blocked', (emu.f[12], struct.unpack('<3I', mem.read(emu.r[5] & M32, 12)))) & M32
        if emu.r[4] & M32 != 0x00ABC000:
            rig.bad('terrain test: world argument')
        return 0

    def e_height(emu):
        emu.f[0] = rig.e_call('height', (emu.f[12], struct.unpack('<3I', mem.read(emu.r[5] & M32, 12)))) & M32
        return 0
    rig.emu.stub(DO.TERRAIN_BLOCKED, function=e_blocked)
    rig.emu.stub(DO.TERRAIN_HEIGHT, function=e_height)
    spots = fails = retried = 0

    def solid(addr_list, centre, half, radii):
        for addr in addr_list:
            obj = m.objects.get(addr)
            if obj is None:
                continue
            pos = (f32(R.to_float(centre[0]) + rng.uniform(-half, half)),
                   f32(R.to_float(centre[1]) + rng.uniform(-half, half)), centre[2])
            driver.top(('move', obj.addr) + pos)
            radius = f32(rng.choice(radii))
            obj.radius = radius
            mem.w32(obj.addr + 0x1C, radius)

    for step in range(DO.scaled(400)):
        if len(m.objects) < 8 or rng.random() < 0.1:
            # a fight: players (radius 16) and creatures (12) around a point, some not solid
            centre = DO.rand_pos(rng)
            made = [driver.top(driver.new_op(None, rng.choice((0x20, 0x20, 0x20, 0x21, 0x0))))
                    for _ in range(rng.randrange(1, 6))]
            solid(made, centre, 80.0, (16.0, 12.0, 12.0, 16.0))
        crowd = rng.random() < 0.15
        floor['z'] = f32(rng.choice((0.0, 0.0, 0.0, -40.0, 200.0)))
        anchor = driver.pick()
        rig.steps += 1
        near = anchor.pos if anchor is not None else (0, 0, floor['z'])
        centre = (f32(R.to_float(near[0]) + rng.uniform(-30, 30)),
                  f32(R.to_float(near[1]) + rng.uniform(-30, 30)), floor['z'])
        if crowd:
            # a crowd around the centre: solid objects the search has to miss; a dense
            # one leaves no spot after 50 tries
            made = [driver.top(driver.new_op(None, 0x20)) for _ in range(rng.choice((6, 12, 30)))]
            solid(made, centre, 72.0, (16.0, 24.0, 40.0))
        radius = rng.choice((12, 12, 12, 16))
        rig.log, rig.pos, rig.diverged = [], 0, False
        want, ok = m.find_free_spot(list(centre), 0x48, radius, 0, terrain_blocked, terrain_height)
        out, flag = rig.scratch + 0x200, rig.scratch + 0x210
        mem.w32(flag, 0x55555555)
        got_ptr = rig.ecall(DO.A['world_findFreeSpot'], out, rig.vec(4, centre), 0x48, radius, flag, 0)
        got = struct.unpack('<3I', mem.read(out, 12))
        if got_ptr != out or got != tuple(w & M32 for w in want) or mem.u32(flag) != (0x55555500 | ok):
            rig.bad('findFreeSpot: %s ok 0x%x, model %s ok %d' % (rig.show(got), mem.u32(flag),
                                                                    rig.show(want), ok))
        if rig.pos != len(rig.log):
            rig.bad('the original made %d of the model\'s %d terrain calls' % (rig.pos, len(rig.log)))
        rig.check(full=(step % 16 == 0))
        spots += 1
        fails += 0 if ok else 1
        retried += 1 if sum(1 for e in rig.log if e[1] == 'blocked') > 1 else 0
        if crowd and len(m.objects) > 90:
            for addr in [o.addr for o in list(m.objects.values())[:40]]:
                if addr in m.objects and addr not in rig.dying:
                    driver.top(('destroy', addr))
        if rng.random() < 0.3:
            driver.top(driver.random_op())
    return ('%d searches (spread 72, radius 12/16, anyHeight 0), %d needed more than one try, %d ended '
            'without a spot' % (spots, retried, fails))


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '-k':
            OPTIONS['filter'] = args.pop(0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_combat_walk: %s not found - nothing to compare with (this is not a failure)' % elf)
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != EXPECTED_SHA256:
        print('difftest_combat_walk: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    started = time.time()
    DP.OPTIONS['seed'] = OPTIONS['seed']
    DO.OPTIONS.update({'seed': OPTIONS['seed'], 'quick': OPTIONS['quick'], 'verbose': OPTIONS['verbose']})
    rng = random.Random(OPTIONS['seed'])
    compared = 0
    if any(wanted('walk.' + k) for k in ('once', 'mash.stop', 'mash.12', 'release')):
        compared = scenario_walk(elf, rng)
        print('        Player_run ticks compared (model = original): %d' % compared)
    if wanted('free_spot'):
        rig = DO.run_scenario('free_spot', 'world_findFreeSpot 0x14acf8 with Creature_moveTo\'s arguments '
                              'on the flat floor', scenario_free_spot, elf, 'walkspot')
        if rig is not None:
            RESULTS.append(('free_spot', rig.failures == 0))
    passed = sum(1 for _n, ok in RESULTS if ok)
    print('%d properties, %d PASS, %d FAIL (seed %d, %.0f s)' % (len(RESULTS), passed, len(RESULTS) - passed,
                                                                 OPTIONS['seed'], time.time() - started))
    return 0 if passed == len(RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
