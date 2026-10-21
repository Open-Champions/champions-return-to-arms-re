#!/usr/bin/env python3
"""difftest_fire_touch.py - compare tools/ref_fire_touch.py with the game's own code: a
LooseFire touching a player or a creature, the fire descriptor (type 0x15) through the
real damage_apply, and the burn tick that the burn then makes.

Needs your own SLUS_209.73 (US v2.00).  Without it the script says so and exits 0.

  python3 tools/difftest_fire_touch.py [path/to/SLUS_209.73] [--quick] [--seed N] [-v]

What runs for real
    tools/difftest_combat.py's rig and policy (damage_apply and everything round 1 runs
    behind it for real: the critical-hit, stun, thorns, Spirit Shield, Frost Armor,
    BloodLust and Retribution helpers, the status setter 0x118950, the FlyingText and
    LightEffect constructors, GameObject_ctor), plus LooseFire_onTouch 0x1fcb70 itself.
    The victim's take-damage (slot 2), the slot-22 enemy test, sounds, particles, the
    pool, handle bookkeeping and the fire owner's slot 20 are recording stubs; their
    answers come from the case.

What one case is
    The world, the players and the objects of a random round-1 damage case
    (difftest_combat.gen_damage): its victim is the TOUCHER; its attacker, when there is
    one, may own the fire.  A LooseFire object (flags 0x420c as LooseFire_ctor leaves
    them) has a +0x4c handle to that owner, to a non-creature, or none.  Three steps on
    the same memory:
      1. touch: LooseFire_onTouch(fire, toucher) on a frame that is mostly a multiple of
         20 (and of 32), with g_difficultyIdx from -1 to 9 and the owner's slot-20 answer;
      2. burn tick: if the toucher is a creature and burns, the frame is moved to the next
         multiple of 32 and the burn seconds lowered by 1/60 per frame on both sides (the
         driver stands for Creature_run, executed in tools/difftest_creature.py), then
         damage_apply(c, c, 100000, 0, 0, 0x1180c040, (0x15, lo, hi, 0), 0; 0, 0) with
         lo = hi = 1 for a monster or a drawn player range;
      3. re-touch on the next multiple of 20.
    Compared after every step: the stub calls in order with their arguments, the
    shared-seed draws in order, both seeds, every field of every object and player record
    the model accounts for, the music bytes, and that nothing else was stored.
"""
import hashlib
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ee_emu                                   # noqa: E402
from ee_emu import EmuError                     # noqa: E402
import ref_combat as R                          # noqa: E402
import ref_fire_touch as F                      # noqa: E402
import difftest_combat as DT                    # noqa: E402
import difftest_creature as DC                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M32 = 0xFFFFFFFF
OPTIONS = {'quick': False, 'seed': 20973, 'verbose': False}
BODIES = {'LooseFire_onTouch': (0x1FCB70, 0x1FCEF0), 'damage_apply': (0x1E8230, 0x1EACB8)}
VT_SLOT20 = 0xA0                                # table + 8 x 20

DT.REAL.add(F.LOOSEFIRE_ON_TOUCH)
STACK_FAULT = (0x01E00000, ee_emu.EE.STACK_LO)   # a store just below the interpreter's 1 MB stack


class Runaway(Exception):
    """The original ran out of stack in nested damage_apply calls and the model nested at
    least as deep (docs/spec/combat.md 3.5)."""


_MODEL_DAMAGE = R.damage_apply
MODEL_CALLS = [0]


def _counted_damage(*args, **kw):
    MODEL_CALLS[0] += 1
    return _MODEL_DAMAGE(*args, **kw)


R.damage_apply = _counted_damage                # the model's own nested calls go through it too
sys.setrecursionlimit(40000)


class Rig(DT.Rig):
    """difftest_combat's rig with slot 20 in every object table (the fire owner's
    question) and an interpreter trace for coverage."""

    def __init__(self, elf):
        DT.Rig.__init__(self, elf)
        enemy20 = self.stub(self.v_enemy20)
        for table in self.obj_vtable.values():
            self.mem.w16(table + VT_SLOT20, 0)
            self.mem.w32(table + VT_SLOT20 + 4, enemy20)
        self.emu.trace = []
        self.pcs = set()
        self.calls = 0
        self.emu.hook(F.DAMAGE_APPLY, self.count_damage)

    def count_damage(self, emu):
        self.calls += 1

    def v_enemy20(self, emu):
        self.events.append(('enemy20', self.tag(emu.r[4]), self.tag(emu.r[5])))
        return self.scenario['enemy20'] & M32

    def run(self, addr, *args, fargs=()):
        self.calls = 0
        try:
            return self.call(addr, *args, fargs=fargs)
        finally:
            self.pcs.update(self.emu.trace or ())

    def both(self, original, model):
        """Run the original, then the model.  A stack overflow of the original is a
        Runaway when the model, too, nested at least as many damage_apply calls (or hit
        Python's recursion limit); otherwise it is a fault of one side."""
        try:
            original()
        except EmuError as exc:
            text = str(exc)
            if 'unmapped address' not in text or not STACK_FAULT[0] <= int(text.split('address ')[1].split()[0], 16) \
                    < STACK_FAULT[1]:
                raise
            depth = self.calls
            self.emu._pending_call = None
            MODEL_CALLS[0] = 0
            try:
                model()
            except RecursionError:
                raise Runaway(depth)
            if MODEL_CALLS[0] >= depth:
                raise Runaway(depth)
            raise EmuError('original ran out of stack after %d damage_apply calls; the model made %d'
                           % (depth, MODEL_CALLS[0]))
        return model()


def gen_case(rng):
    sc = DT.gen_damage(rng)
    w, victim, attacker = sc['world'], sc['victim'], sc['attacker']
    objects = sc['objects']
    roll = rng.random()
    if victim.flags & 0x20:
        victim.res[0] = rng.choice((R.ZERO, R.ZERO, R.f32(0.25), R.ONE, victim.res[0], R.f32(1.5)))
        if roll < 0.3:
            victim.status[0] = R.ZERO                   # not burning yet
    fire = R.Obj(tag='fire', flags=0x420C | rng.choice((0, 0, 1, 3, 0x10)), cls='Third',
                 pos=[R.f32(R.to_float(victim.pos[i]) + rng.uniform(-10, 10)) for i in range(3)])
    roll = rng.random()
    if attacker is not None and roll < 0.7:
        fire.owner_link, fire.owner = True, attacker
    elif roll < 0.85:
        other = R.Obj(tag='prop', flags=rng.choice((1, 3, 0x80)), cls='Third')
        objects.append(other)
        fire.owner_link, fire.owner = True, other
    objects.append(fire)
    w.difficulty = rng.choice((-1, 0, 1, 2, 3, 4, 5, 6, 9, 2, 3, 4, 5))
    roll = rng.random()
    if roll < 0.75:
        w.frame = rng.randrange(1 << 14) * 20
    elif roll < 0.9:
        w.frame = rng.randrange(1 << 12) * 160            # a multiple of 20 and of 32
    else:
        w.frame = rng.randrange(1 << 20)
    sc.update(fire=fire, enemy20=rng.choice((1, 1, 1, 1, 0, 2, 4, 0xFFFFFFFF)),
              skill_number=rng.choice((0, 1, 7, 40, 133, rng.randrange(0, 2000), -5)))
    return sc


class Case:
    """One case on the rig and on the model, step by step."""

    def __init__(self, rig, sc, tally):
        self.rig, self.sc, self.tally = rig, sc, tally
        self.w = sc['world']
        self.objects = sc['objects']
        self.spells = [spell for obj in self.objects for spell in obj.spells]
        sc['pool'], self.w.pool_fn = DT.pool_plan(sc['plan'])
        rig.begin(sc)
        rig.put_objects(self.objects)
        rig.put_world(self.w)
        self.marks = {}

    def compare(self, step, want):
        rig, w, tally = self.rig, self.w, self.tally
        got_events = [tuple(e) for e in rig.events]
        want_events = [e for e in w.events if e[0] != 'thorns']
        ok = True
        ok &= tally.check(step + ': stub calls, in order', got_events == want_events,
                          lambda: next(((i, a, b) for i, (a, b) in enumerate(zip(got_events + [None] * 99,
                                                                                 want_events + [None] * 99))
                                        if a != b), None))
        ok &= tally.check(step + ': shared-seed draws, in order', rig.seed_draws() == w.seed.draws,
                          lambda: (rig.seed_draws(), w.seed.draws))
        ok &= tally.check(step + ': seeds afterwards', rig.mem.u32(DT.G_SEED) == w.seed.state and
                          rig.mem.u32(DT.G_COSMETIC) == w.cosmetic.state)
        fields = all(rig.get_object(o) == rig.model_object(o) for o in self.objects)
        fields = fields and all(rig.get_spell(s) == (s.f18 & M32, s.f1c, s.f20, s.f2c & M32) for s in self.spells)
        fields = fields and all(rig.get_record(k) == rig.model_record(w.players[k]) for k in range(4))
        fields = fields and rig.mem.read(0x4F7158, 32) == bytes(w.music)
        ok &= tally.check(step + ': fields written', fields, lambda: [
            (o.tag, {k: (v, rig.model_object(o)[k]) for k, v in rig.get_object(o).items()
                     if v != rig.model_object(o)[k]}) for o in self.objects if rig.get_object(o) != rig.model_object(o)])
        stray = rig.stray_writes(self.objects, self.spells, range(4))
        ok &= tally.check(step + ': no other store', not stray, lambda: stray[:4])
        return ok

    def reset_logs(self):
        self.rig.emu.reset_log()
        self.rig.emu.notes = []
        del self.rig.events[:]
        self.w.events = []
        self.w.seed.draws = []
        self.w.cosmetic.draws = []

    def touch(self, step):
        rig, w, sc = self.rig, self.w, self.sc
        fire, victim = sc['fire'], sc['victim']
        self.reset_logs()
        rig.mem.w32(F.G_SIM_FRAME, w.frame)
        before = victim.status[0]
        want = rig.both(lambda: rig.run(F.LOOSEFIRE_ON_TOUCH, rig.addr[id(fire)], rig.addr[id(victim)]),
                        lambda: F.loosefire_touch(w, fire, victim, lambda owner, other: sc['enemy20']))
        self.compare(step, want)
        if want is not None:
            kind = 'player' if victim.flags & 0x40 else 'creature' if victim.flags & 0x20 else 'other'
            self.mark('%s: damage_apply reached, %s toucher' % (step, kind))
            self.mark('%s: damage_apply returned %d' % (step, want))
            if any(e[0] == 'take_damage' and e[1] == victim.tag and e[4] in (0x2000, 0x42000) for e in w.events):
                self.mark('%s: a miss' % step)
            if not want:
                why = ('invulnerable' if victim.cflags & R.CF_INVULNERABLE else
                       'Innoruuk immune' if victim.cls == 'Innoruuk' and victim.innoruuk_immune else
                       'prediction-copy attacker' if F.fire_owner(fire) is not None and fire.owner.flags & 0x20000
                       else 'absolute' if victim.cflags & R.CF_ABSOLUTE else 'other')
                self.mark('%s: returned 0 because %s' % (step, why))
            if victim.flags & 0x60:
                self.mark('%s: entry value %d' % (step, F.touch_entry(victim.flags, w.difficulty)[0][1]))
            if victim.status[0] != before:
                self.mark('%s: burn set' % step)
            if F.fire_owner(fire) is None:
                self.mark('%s: the fire is the attacker' % step)
        elif R.c_rem(R.s32(w.frame), F.TOUCH_PERIOD):
            self.mark('%s: not a touch frame' % step)
        else:
            self.mark('%s: owner says not an enemy' % step)
        return want

    def burn(self, step):
        rig, w, sc, mem = self.rig, self.w, self.sc, self.rig.mem
        victim = sc['victim']
        if not victim.flags & 0x20 or not R.flt(R.ZERO, victim.status[0]):
            return
        a = rig.addr[id(victim)]
        while True:                                     # the driver stands for Creature_run
            w.frame += 1
            victim.status[0] = R.fsub(victim.status[0], F.DT)
            if not w.frame & F.BURN_PERIOD_MASK or not R.flt(R.ZERO, victim.status[0]):
                break
        mem.w32(a + 0x340, victim.status[0])
        mem.w32(F.G_SIM_FRAME, w.frame)
        if w.frame & F.BURN_PERIOD_MASK:
            self.mark('%s: the burn ran out before a tick frame' % step)
            return
        self.reset_logs()
        if victim.flags & 0x40:
            low, high = F.burn_range(R.World(seed=sc['skill_number'] * 7919), sc['skill_number'])
        else:
            low = high = F.BURN_MONSTER
        desc = rig.put_desc([(F.FIRE_ENTRY, low & 0xFFFF, high & 0xFFFF, 0), (-1, 0, 0, 0), (-1, 0, 0, 0),
                             (-1, 0, 0, 0)])
        want = rig.both(lambda: rig.run(F.DAMAGE_APPLY, a, a, F.BURN_RATING, 0, 0, F.BURN_FLAGS, desc, 0,
                                        fargs=(R.ZERO, R.ZERO)),
                        lambda: R.damage_apply(w, victim, victim, R.ZERO, R.ZERO, F.BURN_RATING, F.BURN_FLAGS,
                                               [(F.FIRE_ENTRY, R.s16(low), R.s16(high), 0)] + [(-1, 0, 0, 0)] * 3,
                                               0))
        self.compare(step, want)
        if victim.spell('FrostArmor'):
            self.mark('%s: Frost Armor strikes back at the burning carrier, %d nested hits' % (
                step, min(rig.calls - 1, 3)))
        self.mark('%s: burn tick on a %s, returned %d' % (step, 'player' if victim.flags & 0x40 else 'creature', want))

    def mark(self, key):
        self.marks[key] = self.marks.get(key, 0) + 1


def main(argv):
    args = list(argv)
    elf = None
    while args:
        a = args.pop(0)
        if a == '--quick':
            OPTIONS['quick'] = True
        elif a == '--seed':
            OPTIONS['seed'] = int(args.pop(0), 0)
        elif a == '-v':
            OPTIONS['verbose'] = True
        else:
            elf = a
    if elf is None:
        elf = os.path.join(ROOT, 'SLUS_209.73')
    if not os.path.exists(elf):
        print('difftest_fire_touch: SLUS_209.73 not found - nothing to compare with (this is not a failure)')
        return 0
    digest = hashlib.sha256(open(elf, 'rb').read()).hexdigest()
    if digest != DT.EXPECTED_SHA256:
        print('difftest_fire_touch: %s is not SLUS_209.73 US v2.00 (sha256 %s) - skipped' % (elf, digest[:16]))
        return 0
    DT.OPTIONS['verbose'] = OPTIONS['verbose']
    rng = random.Random(OPTIONS['seed'])
    started = time.time()
    rig = Rig(elf)
    rig.emu.stub(0x10D940, function=lambda e: rig.back[e.r[4] & M32].boss_rank)
    tally = DT.Tally()
    marks, skipped, faults = {}, 0, 0
    count = 300 if OPTIONS['quick'] else 3000
    for _ in range(count):
        sc = gen_case(rng)
        case = Case(rig, sc, tally)
        try:
            case.touch('touch')
            case.burn('burn tick')
            case.w.frame = (case.w.frame // 20 + 1) * 20
            case.touch('re-touch')
        except (ee_emu.StepLimit, RecursionError):
            skipped += 1
            rig.emu._pending_call = None
            continue
        except Runaway as exc:
            key = 'runaway (both sides, stack out after %s nested hits): %s' % (
                'about %d' % (exc.args[0] // 100 * 100), 'Frost Armor self-hit' if any(
                    s.kind == 'FrostArmor' for s in sc['victim'].spells) else 'other')
            marks[key] = marks.get(key, 0) + 1
            for k, v in case.marks.items():
                marks[k] = marks.get(k, 0) + v
            continue
        except (EmuError, DT.Unexpected) as exc:
            faults += 1
            tally.check('ran to completion', False, str(exc))
            rig.emu._pending_call = None
            continue
        tally.check('ran to completion', True)
        for key, value in case.marks.items():
            marks[key] = marks.get(key, 0) + value
    tally.flush({})
    if skipped:
        print('      (%d cases skipped: runaway recursion in both original and model)' % skipped)
    print('paths seen:')
    for key in sorted(marks):
        print('  %-60s %6d' % (key, marks[key]))
    print('coverage of the original as executed here (basic blocks, instructions):')
    for name, (start, end) in BODIES.items():
        leaders, _sites = DC.analyse(rig.mem, start, end)
        inside = {pc for pc in rig.pcs if start <= pc < end}
        print('  %-20s blocks %4d of %4d  instructions %4d of %4d' % (
            name, len(leaders & inside), len(leaders), len(inside), (end - start) // 4))
        if OPTIONS['verbose']:
            print('      never entered: %s' % ' '.join('%06x' % pc for pc in sorted(leaders - inside)))
    print('%d cases (three steps each) in %.0f s' % (count, time.time() - started))
    return 0 if all(ok for _name, ok in DT.RESULTS) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
