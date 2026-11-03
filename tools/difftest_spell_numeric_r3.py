#!/usr/bin/env python3
"""Original damage, heal, recast and stun results for spell IDs 16, 23, 49 and 55.

Run with unittest already imported and PYTHONDONTWRITEBYTECODE=1. Both seeds
run in this one process. Counts only are written; no instruction text or
executable bytes are emitted.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unittest  # noqa: F401 - preload before tools/ is on the path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import difftest_combat as DC
import difftest_spell_projectiles_r3 as P
import difftest_spell_support_r3 as Support
import ee_emu
import ref_combat as R
import ref_player as RP
import ref_skills_a as SA

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (20973, 7)
MANA = {16: 0x2ED1E4, 23: 0x2F8AF8, 49: 0x2DE60C, 55: 0x2E8E94}
CAST_STUB = 0x00E20000
ATTACH = 0x1754A0
TAKE_DAMAGE = 0x116638
STUN = 0x118A58
BOSS_RANK = 0x10D940
SET_STATE = 0x3C2688
ATAN2 = 0x166798
CAST_HELPER = 0x1A42B8
HEAL_RATE = 0x3C71AA2E
PLAIN = 0x42200000          # 40, an authored equal bound for the floor cases
HALF_PLAIN = 0x41A00000     # 20
COLD = 0x41F00000           # 30
HP_START = 0x42C80000       # 100
ABOVE = 0x447A0000          # 1000, above every tested rank cost
RANK_SET = (1, 2, 5, 20)


class Failure(Exception):
    pass


def previous_pattern(pattern):
    """The next pattern toward zero for a positive finite value."""
    if pattern <= 1:
        raise Failure('pattern')
    return pattern - 1


def desc_slots(canon):
    if canon == 0:
        return None
    if not (isinstance(canon, tuple) and canon and canon[0] == 'desc'):
        raise Failure('descriptor')
    slots = []
    for slot in canon[1:]:
        slots.append((-1, 0, 0, 0) if slot is None else tuple(R.s16(part) for part in slot))
    return slots


class Probe:
    def __init__(self, elf):
        self.elf = str(elf)
        self.counts = Counter()
        self.failures = Counter()
        self.projectiles = P.Checks(elf)
        self.support = Support.Probe(elf)
        DC.REAL.update((TAKE_DAMAGE, STUN, ATAN2, SET_STATE))
        self.combat = DC.Rig(elf)
        self.combat.boss_rank = 0
        self.combat.emu.stub(BOSS_RANK, function=lambda emu: self.combat.boss_rank, name='boss_rank')
        table = self.combat.obj_vtable['Creature']
        self.combat.mem.w16(table + 0xD8, 0)
        self.combat.mem.w32(table + 0xD8 + 4, SET_STATE)
        self._install_cast_stub(self.projectiles.rig)
        self._install_cast_stub(self.support.rig)
        for rig in (self.projectiles.rig, self.support.rig):
            for address in MANA.values():
                rig.real.addresses.add(address)
            rig.real.addresses.add(0x2DE334)
            rig.real.addresses.add(CAST_HELPER)

    def fail(self, label):
        self.counts['assertions'] += 1
        self.failures[label] += 1

    def check(self, label, ok):
        self.counts['assertions'] += 1
        if not ok:
            self.failures[label] += 1
            raise Failure(label)

    def _install_cast_stub(self, rig):
        rig.emu.stub(CAST_STUB, ret=0, name='cast_returns_zero')
        rig.names[CAST_STUB] = 'cast_returns_zero'
        if ATTACH not in rig.names and ATTACH not in rig.real:
            def attach(emu):
                source, dest = emu.r[5] & R.M32, emu.r[9] & R.M32
                if source and dest:
                    emu.mem.write(dest, emu.mem.read(source, 12))
                return dest
            rig.emu.stub(ATTACH, function=attach, name='model_getAttachPoint')
            rig.names[ATTACH] = 'model_getAttachPoint'

    def capture_projectile(self, seed, sid, rank, undead=False, pvp=False):
        checks = self.projectiles
        checks.world.on_world_collectObjectsInArc = lambda args, view, rng: P.D.Res(outs=[list(checks.arc)])
        checks.setup()
        owner = checks.world.player
        obj, _ = checks.cast('capture_setup', sid, rank, owner)
        target = checks.world.mobs[0]
        checks.mem.w32(obj + 0x44, seed & R.M32)
        checks.mem.w8(target + 0xB4, 0x10 if undead else 0)
        checks.mem.w32(SA.G_PVP_MODE_A, 1 if pvp else 0)
        checks.enemy = True
        result = checks.compare('capture', P.HIT[sid], obj, target)
        self.require_compare(result, 'capture_%d' % sid)
        damage = checks.calls(result, 'damage_apply')
        self.check('capture_one', len(damage) == 1)
        return damage[0]

    def capture_child(self, seed):
        checks = self.projectiles
        checks.world.on_world_collectObjectsInArc = lambda args, view, rng: P.D.Res(outs=[list(checks.arc)])
        obj = checks.make_child()
        target = checks.world.mobs[0]
        checks.mem.w32(obj + 0x44, seed & R.M32)
        checks.enemy = True
        result = checks.compare('capture_child', P.ENTRY[0x2F71AC], obj, target)
        self.require_compare(result, 'capture_child')
        damage = checks.calls(result, 'damage_apply')
        self.check('capture_child_one', len(damage) == 1)
        return damage[0]

    def capture_bash(self, rank):
        probe = self.support
        self._restore_support()
        probe.reset()
        obj = probe.cast(49, rank)
        target = probe.world.monsters[0]
        probe.arc, probe.enemies = [target], {target}
        probe.world.forced_events, probe.world.pool_fail = 2, 1.0
        chance = probe.stat(49, 1, rank)
        # The next shared draw is the stun roll. Equality with the chance stuns.
        draw = (chance - 1) & 0xFFFF
        rolled = (((draw << 16) - Support.B.INC) * pow(Support.B.STEP, -1, 1 << 32)) & Support.B.M32
        probe.mem.w32(Support.RC.G_RAND_SEED, rolled)
        out = probe.run(49, obj)
        hits = probe.calls(out, 'damage_apply')
        stun = probe.calls(out, 'Creature.v30')
        if len(hits) != 1 or len(stun) != 1:
            print('bash counts %d %d' % (len(hits), len(stun)))
        self.check('bash_one', len(hits) == 1 and len(stun) == 1)
        return hits[0], stun[0]

    def require_compare(self, result, label):
        bad = [key for key in ('fault', 'calls', 'writes', 'seed', 'result', 'both_fault')
               if result.get(key) is not None]
        self.check(label, not bad and not self.projectiles.rig.unknown)
        self.projectiles.rig.unknown = {}

    def apply_hit(self, seed, dmin, dmax, flags, desc, no_crit, attack, victim_fields,
                  attacker_kind='player'):
        """Run original damage_apply, then original take-damage, against the reference."""
        self.counts['damage_calls'] += 1
        victim = R.Obj(tag='victim', flags=0x20, cls='Creature', hp=HP_START, max_hp=HP_START,
                       armor=0, kind=0, pos=[R.ZERO, R.ZERO, R.ZERO])
        for name, value in victim_fields.items():
            setattr(victim, name, value)
        attacker = None
        if attacker_kind == 'player':
            attacker = R.Obj(tag='caster', flags=0x40, cls='Creature', slot=0,
                             pos=[R.ZERO, R.ZERO, R.ZERO])
        elif attacker_kind == 'creature':
            attacker = R.Obj(tag='caster', flags=0x20, cls='Creature',
                             pos=[R.ZERO, R.ZERO, R.ZERO])
        world = R.World(seed=seed, cosmetic=seed)
        world.frame = 1000
        world.players = [R.PlayerRec() for _ in range(4)]
        if attacker is not None and attacker.flags & 0x40:
            world.players[0].obj = attacker
        rig = self.combat
        objects = [victim] + ([attacker] if attacker is not None else [])
        rig.begin({'world': world, 'pool': lambda size: True, 'local': 0})
        rig.put_objects(objects)
        rig.put_world(world)
        block = rig.put_desc(desc) if desc is not None else 0
        rig.emu.reset_log()
        try:
            returned = rig.call(
                0x1E8230, rig.addr[id(victim)],
                rig.addr[id(attacker)] if attacker is not None else 0,
                attack & R.M32, 0, 0, flags & R.M32, block, no_crit & R.M32,
                fargs=(dmin & R.M32, dmax & R.M32)) & R.M32
            want = R.damage_apply(world, victim, attacker, dmin, dmax, attack, flags, desc, no_crit)
        except (ee_emu.EmuError, DC.Unexpected, ee_emu.StepLimit, RecursionError) as exc:
            if isinstance(exc, DC.Unexpected):
                print('damage target ' + str(exc).split(',')[0])
            raise Failure('damage_apply.' + type(exc).__name__) from None
        got = [event for event in rig.events if event[0] == 'take_damage']
        want_hits = [event for event in world.events if event[0] == 'take_damage']
        self.check('damage_return', returned == want)
        self.check('damage_amount', got == want_hits)
        self.check('damage_status', rig.get_object(victim)['status'] == rig.model_object(victim)['status'])
        self.check('damage_seed', rig.mem.u32(DC.G_SEED) == world.seed.state)
        amount = got[0][2] if got else None
        handed_flags = got[0][4] if got else 0
        self.last_status = rig.get_object(victim)['status']
        self.last_hp = rig.mem.u32(rig.addr[id(victim)] + 0x228)
        # Creature_takeDamage is the base slot. A player-flagged victim uses a different slot.
        if amount is None or victim.flags & 0x40:
            if amount is None:
                self.check('no_hit_hp', self.last_hp == victim_fields.get('hp', HP_START))
            return amount
        before = self.last_hp
        try:
            rig.call(TAKE_DAMAGE, rig.addr[id(victim)],
                     rig.addr[id(attacker)] if attacker is not None else 0,
                     handed_flags, fargs=(amount,))
        except (ee_emu.EmuError, DC.Unexpected, ee_emu.StepLimit) as exc:
            if isinstance(exc, DC.Unexpected):
                print('take-damage target ' + str(exc).split(',')[0])
            raise Failure('take_damage.' + type(exc).__name__) from None
        self.counts['take_damage_calls'] += 1
        after = rig.mem.u32(rig.addr[id(victim)] + 0x228)
        self.check('hp_subtract', after == R.fsub(before, amount))
        self.check('pending', rig.mem.u32(rig.addr[id(victim)] + 0xC8) == amount)
        self.check('pending_flags', rig.mem.u32(rig.addr[id(victim)] + 0x2DC) == handed_flags)
        self.last_hp = rig.mem.u32(rig.addr[id(victim)] + 0x228)
        return amount

    def replay(self, seed, payload, **victim_fields):
        return self.apply_hit(
            seed, payload[-2], payload[-1], payload[5], desc_slots(payload[6]), payload[7],
            payload[2], victim_fields,
            attacker_kind='player' if payload[1] else None)

    def stun(self, frames, flash, boss, corpse):
        self.counts['stun_calls'] += 1
        victim = R.Obj(tag='stunned', flags=0x20, cls='Creature', hp=HP_START, max_hp=HP_START)
        rig = self.combat
        rig.boss_rank = boss
        rig.begin({'world': R.World(seed=1), 'pool': lambda size: True, 'local': 0})
        rig.put_objects([victim])
        rig.put_world(rig.scenario['world'])
        addr = rig.addr[id(victim)]
        if corpse:
            rig.mem.w16(addr + 0x232, 0x14)
        try:
            rig.call(STUN, addr, frames & 0xFFFF, flash)
        except (ee_emu.EmuError, DC.Unexpected, ee_emu.StepLimit) as exc:
            if isinstance(exc, DC.Unexpected):
                print('stun target ' + str(exc).split(',')[0])
            raise Failure('stun.' + type(exc).__name__) from None
        stored = rig.mem.s16(addr + 0x31C)
        state = rig.mem.s16(addr + 0x232)
        if boss or corpse:
            self.check('stun_refused', stored == 0 and state == (0x14 if corpse else 0))
            return
        self.check('stun_timer', stored == R.s16(frames))
        self.check('stun_state', state == 0x13)
        colours = [rig.mem.u16(addr + 0x90 + 2 * index) for index in range(8)]
        if flash:
            self.check('stun_flash', colours == [0x3A, 0x9B, 0x9A, 0x48, 0x3A, 0x9B, 0x9A, 0])
        else:
            self.check('stun_no_flash', colours == [0] * 8)

    def _restore_support(self):
        probe = self.support
        world = probe.world
        world.on_world_collectObjectsInArc = lambda args, view, rng: Support.B.Res(outs=[probe.arc])
        world.on_Creature_v39 = lambda args, view, rng: Support.B.Res(rng.choice((0, 1, 5, 12, 20)))

    def heal_amount(self, seed, rank):
        probe = self.support
        self._restore_support()
        probe.reset()
        probe.mem.w32(DC.G_SEED, seed & R.M32)
        obj = probe.cast(55, rank)
        percent = probe.stat(55, 0, rank) & 0xFFFF
        most = probe.mem.u32(Support.RC.G_PLAYERS + 0xB0)
        share = Support.C.mul(
            Support.C.mul(most, HEAL_RATE),
            Support.C.mul(Support.C.from_int(percent), Support.SB.F_0_01))
        self.check('heal_cached', probe.mem.u32(obj + 0x1C) == share)
        record = Support.RC.G_PLAYERS
        before = probe.mem.u32(record + 0xAC)
        probe.alive([0])
        probe.run(55, obj)
        self.check('heal_added', probe.mem.u32(record + 0xAC) == Support.C.add(before, share))
        self.counts['heal_calls'] += 1

    def _ability(self, rig, sid):
        mem = rig.emu.mem
        text = mem.cstr(RP.S_NEWSTYLE)
        if isinstance(text, str):
            text = text.encode('latin1')
        self.check('ability_name_fits', len(text) < 0x20)
        ability = rig.emu.alloc(0x68)
        mem.write(ability, text + b'\0')
        mem.w16(ability + 0x20, sid)
        return ability

    def _pay_once(self, rig, world, player, sid, rank, mana, recast, copy):
        mem = rig.emu.mem
        world.place(rig.rng, centre=(0, 0, 100))
        world.on_Creature_v39 = lambda args, view, rng, rank=rank: (
            P.D.Res(rank) if rig is self.projectiles.rig else Support.B.Res(rank))
        world.on_world_collectObjectsInArc = lambda args, view, rng: (
            P.D.Res(outs=[[]]) if rig is self.projectiles.rig else Support.B.Res(outs=[[]]))
        mem.w32(player + 0xC, 0x20060 if copy else 0x40)
        mem.w16(player + 0x4AE, recast & 0xFFFF)
        mem.w32(player + 0x544, 1)
        mem.w32(player + 0x3C8, 0)
        record = RP.G_PLAYERS
        mem.w32(record + 0xC0, mana & R.M32)
        if sid == 49:
            mem.w32(record + 0x43FC, getattr(world, 'item', 1) or 1)
            mem.w8(record + 0x4A86, 0)
        skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
        table = mem.u32(skill + 0x60)
        slot = table + 8 * 2 + 4
        previous = mem.u32(slot)
        mem.w32(slot, CAST_STUB)
        ability = self._ability(rig, sid)
        rig.emu.r[29] = rig.emu.stack_hi - 0x400
        rig.emu.reset_log()
        rig.unknown = {}
        try:
            rig.emu.call(CAST_HELPER, player, ability, max_steps=2000000)
        except (ee_emu.EmuError, ee_emu.StepLimit) as exc:
            raise Failure('cast_helper.' + type(exc).__name__) from None
        finally:
            mem.w32(slot, previous)
        unknown = [call.target for call in rig.emu.calls
                   if call.target not in rig.real and call.target not in rig.names]
        self.check('cast_helper_known', not unknown)
        if unknown:
            print('helper targets ' + ' '.join('%x' % target for target in unknown[:8]))
        paid = mem.u32(record + 0xC0)
        stored = mem.s16(player + 0x4AE)
        self.counts['payment_calls'] += 1
        return paid, stored

    def payment(self, seed, rig, world, player, sid):
        mem = rig.emu.mem
        skill = mem.u32(SA.G_SKILL_TABLE + 4 * sid)
        self.check('kind_and_recast', (mem.s32(skill + 8), mem.s16(skill + 0x0C), mem.u32(skill + 4) & 1) == (0, 30, 0))
        for rank in RANK_SET:
            mem.w32(DC.G_SEED, seed & R.M32)
            rig.emu.reset_log()
            rig.emu.call(MANA[sid], skill, rank, max_steps=200000)
            cost = rig.emu.f[0] & R.M32
            self.check('cost_positive', cost != 0)
            for mana, label in ((cost, 'exact'), (previous_pattern(cost), 'below'), (ABOVE, 'above')):
                paid, stored = self._pay_once(rig, world, player, sid, rank, mana, 0, False)
                self.check('debit_' + label, paid == Support.C.sub(mana, cost) and stored == 30)
            paid, stored = self._pay_once(rig, world, player, sid, rank, cost, 1, False)
            self.check('recast_blocks', paid == cost and stored == 1)
            paid, stored = self._pay_once(rig, world, player, sid, rank, cost, 0, True)
            self.check('copy_blocks', paid == cost and stored == 0)

    def boundaries(self, seed, plain_amount):
        amount = self.apply_hit(
            seed, PLAIN, PLAIN, 0x80000, None, 0, 100000, {}, attacker_kind='player')
        self.check('equal_bound', amount == PLAIN)
        flagged = self.apply_hit(
            seed, PLAIN, PLAIN, 0, None, 0, 100000, {}, attacker_kind='player')
        self.check('flag_does_not_change_amount', amount == flagged == plain_amount[0]
                   if plain_amount[0] is not None else amount == flagged)
        if plain_amount[0] is None:
            plain_amount[0] = amount
        else:
            self.check('seed_stable_amount', amount == plain_amount[0])
        armored = self.apply_hit(
            seed, PLAIN, PLAIN, 0, None, 1, 100000,
            {'flags': 0x60, 'armor': 3000, 'slot': 0}, attacker_kind='player')
        cut = R.fmul(R.itof(3000), R.K_1_30)
        self.check('half_floor_condition', R.flt(R.fsub(PLAIN, cut), R.fmul(PLAIN, R.HALF)))
        self.check('half_floor', armored == HALF_PLAIN)
        cold = [(0x16, 30, 30, 0), (-1, 0, 0, 0), (-1, 0, 0, 0), (-1, 0, 0, 0)]
        cold_amount = self.apply_hit(
            seed, R.ZERO, R.ZERO, 0, cold, 0, 100000, {'hp': HP_START, 'max_hp': HP_START},
            attacker_kind='player')
        self.check('cold_amount', cold_amount == COLD)
        expect = R.fdiv(R.fmul(COLD, R.SIXTY), HP_START)
        self.check('cold_timer', self.last_status[1] == expect and R.fle(expect, R.SIXTY))
        self.apply_hit(seed, R.ZERO, R.ZERO, 0, cold, 0, 100000,
                       {'hp': R.ZERO, 'max_hp': HP_START, 'status': [R.ZERO] * 5},
                       attacker_kind='player')
        self.check('cold_timer_at_zero_hp', self.last_status[1] == R.SIXTY)
        resisted = self.apply_hit(
            seed, R.ZERO, R.ZERO, 0, cold, 0, 100000,
            {'res': [R.ZERO, R.ONE, R.ZERO, R.ZERO, R.ZERO]}, attacker_kind='player')
        self.check('cold_resist', resisted == R.ZERO and self.last_status[1] == R.ZERO)
        refused = self.apply_hit(
            seed, PLAIN, PLAIN, 0x40, None, 1, 100000,
            {'cflags': R.CF_INVULNERABLE}, attacker_kind='player')
        self.check('invulnerable', refused is None)
        lethal = self.apply_hit(
            seed, PLAIN, PLAIN, 0, None, 1, 100000, {'hp': PLAIN, 'max_hp': HP_START},
            attacker_kind='player')
        self.check('lethal_hits_zero', lethal == PLAIN and self.last_hp == R.ZERO)

    def run_seed(self, seed, plain_amount):
        payloads = {
            '16': self.capture_projectile(seed, 16, 1),
            '16_undead': self.capture_projectile(seed, 16, 20, undead=True),
            '23': self.capture_projectile(seed, 23, 1),
            '23_child': self.capture_child(seed),
        }
        bash, stun = self.capture_bash(5)
        payloads['49'] = bash
        for name, payload in payloads.items():
            self.replay(seed, payload)
            self.counts['replayed_' + name] += 1
        self.boundaries(seed, plain_amount)
        self.heal_amount(seed, 1)
        self.heal_amount(seed, 20)
        self.stun(stun[1], 1, 0, False)
        self.stun(stun[1], 0, 0, False)
        self.stun(stun[1], 1, 1, False)
        self.stun(stun[1], 1, 0, True)
        self.check('bash_duration', stun[1] == self.support.stat(49, 2, 5) * 60)
        self.payment(seed, self.projectiles.rig, self.projectiles.world,
                     self.projectiles.world.player, 16)
        self.payment(seed, self.projectiles.rig, self.projectiles.world,
                     self.projectiles.world.player, 23)
        self.payment(seed, self.support.rig, self.support.world,
                     self.support.world.players[0], 49)
        self.payment(seed, self.support.rig, self.support.world,
                     self.support.world.players[0], 55)

    def execute(self):
        plain_amount = [None]
        for seed in SEEDS:
            self.run_seed(seed, plain_amount)
        return not self.failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local/spells-r3/numeric-counts.json')
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    allowed = (ROOT / 'local/spells-r3').resolve()
    if not output.resolve().is_relative_to(allowed):
        parser.error('output must remain under local/spells-r3/')
    elf = ROOT / 'local/SLUS_209.73'
    digest = hashlib.sha256(elf.read_bytes()).hexdigest() if elf.is_file() else ''
    if digest != DC.EXPECTED_SHA256:
        print('BLOCKED: private input missing or unexpected; 0 comparisons')
        return 2
    probe = None
    failures = Counter()
    try:
        probe = Probe(elf)
        ok = probe.execute()
    except (Failure, Support.ProbeFailure) as exc:
        failures[str(exc)] += 1
        ok = False
    except Exception as exc:
        failures['aborted.' + type(exc).__name__] += 1
        ok = False
    if probe is not None:
        failures.update(probe.failures)
    report = {
        'status': 'PASS' if ok and not failures else 'FAIL',
        'seeds': list(SEEDS),
        'fpu': 'ps2',
        'counts': dict(sorted(probe.counts.items())) if probe else {},
        'failures': dict(sorted(failures.items())),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('%s  seeds %s  assertions %d  failures %d' % (
        report['status'], ','.join(str(seed) for seed in SEEDS),
        report['counts'].get('assertions', 0), sum(failures.values())))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
