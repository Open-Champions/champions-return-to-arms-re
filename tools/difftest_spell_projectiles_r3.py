#!/usr/bin/env python3
"""Bounded original/reference checks for numeric IDs 16 and 23.

Run with unittest preloaded and PYTHONDONTWRITEBYTECODE=1; see the companion
specification. Only a counts report is emitted. No private bytes or names are
exported. The existing family Rig and reference APIs are used unchanged.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

import difftest_skills_a as D
import ref_core as C
import ref_creature as RC
import ref_skills_a as S

ROOT = Path(__file__).resolve().parents[1]
ENTRY = {spec[0]: name for name, spec in D.ENTRIES.items()}
CAST = {16: ENTRY[0x2ECFCC], 23: ENTRY[0x2F8840]}
USE = {16: ENTRY[0x2ED20C], 23: ENTRY[0x2F8B24]}
RUN = {16: ENTRY[0x2EBC50], 23: ENTRY[0x2F77C0]}
HIT = {16: ENTRY[0x2ECAE8], 23: ENTRY[0x2F84E4]}


def positive_chop(value):
    """Independent, positive-normal-only binary32 truncation for the cost oracle."""
    if not value:
        return Fraction(0)
    assert value > 0
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    scale = Fraction(2) ** exponent
    if value < scale:
        exponent -= 1
    unit = Fraction(2) ** (exponent - 23)
    return (value // unit) * unit


def cost_oracle(sid, rank):
    # The two numerical expressions are authored contracts, not an exported table.
    step = 3.0 if sid == 16 else struct.unpack('<f', struct.pack('<f', 3.000033))[0]
    product = positive_chop(Fraction(step) * (rank - 1))
    return D.f32(float(positive_chop(product + 7)))


class Checks:
    def __init__(self, elf):
        C.set_fpu('ps2')
        self.rig = D.Rig(str(elf), 1623)
        self.mem, self.world = self.rig.emu.mem, self.rig.world
        self.counts, self.failures = Counter(), Counter()
        self.serial = 0
        self.bolts = {16: self.world.add_pool(0x80, 1, '16')[0],
                      23: self.world.add_pool(0xD0, 1, '23')[0]}
        self.shards = self.world.add_pool(0x7C, 8, '23')
        self.world.add_pool(0x248, 4, '23')
        self.world.add_pool(0xBC, 1, '16')
        self.arc, self.box, self.enemy, self.ground = [], [], True, False
        self.rays, self.fail_sizes, self.prefill_spin = [0], set(), None
        self.world.kill_bias = self.world.fail_alloc = self.world.extra_bias = 0
        self.world.on_world_collectObjectsInArc = lambda a, v, r: D.Res(outs=[list(self.arc)])
        self.world.on_world_collectObjectsInBox = lambda a, v, r: D.Res(outs=[list(self.box)])
        self.world.on_Creature_v20 = lambda a, v, r: D.Res(int(self.enemy))
        self.world.on_damage_apply = lambda a, v, r: D.Res(1)
        self.world.on_terrain_height = lambda a, v, r: D.Res(f=D.f32(D.fl(a[1][2]) + (1 if self.ground else -100)))
        self.world.on_terrain_raycast = self.raycast
        self.world.on_water_test = lambda a, v, r: D.Res(0)
        allocate = self.world.on_pool_new
        def allocation(args, view, rng):
            result = D.Res(0) if args[0] in self.fail_sizes else allocate(args, view, rng)
            if result.ret and args[0] == 0xD0 and self.prefill_spin is not None:
                view.poke(result.ret + 0x98, 4, self.prefill_spin)
            return result
        self.world.on_pool_new = allocation

    def raycast(self, args, view, rng):
        index = view.state.get('r3_ray_index', 0)
        view.state['r3_ray_index'] = index + 1
        return D.Res(f=self.rays[index % len(self.rays)])

    def check(self, group, label, condition):
        self.counts[group + '.assertions'] += 1
        if not condition:
            self.failures[group + '.' + label] += 1

    def compare(self, group, key, *args):
        self.serial += 1
        result = self.rig.compare(key, args, 1623000 + self.serial)
        self.counts[group + '.comparisons'] += 1
        for prop in ('fault', 'calls', 'writes', 'seed', 'result', 'both_fault'):
            self.check(group, prop, result[prop] is None)
        self.check(group, 'unknown_calls', not self.rig.unknown)
        # Deliberately retain only counters in the output, never the diagnostic payload.
        return result

    def calls(self, result, name):
        return [args for key, args in result['emu_calls'] if key == name]

    def deleted(self, result, obj):
        return any(a[:2] == (obj, 3) for a in self.calls(result, 'Creature.v1'))

    def skill(self, sid):
        return self.mem.u32(S.G_SKILL_TABLE + 4 * sid)

    def stat(self, sid, stat, rank, owner=None, cap=0):
        model = S.Model(D.DC.ModelView(self.mem))
        if sid == 16:
            return model.skill_call(self.skill(sid), 10, stat, rank)
        return model.skill_call(self.skill(sid), 12, stat, rank, owner or 0, cap)

    def setup(self):
        self.arc, self.box, self.enemy, self.ground = [], [], True, False
        self.rays, self.fail_sizes, self.prefill_spin = [0], set(), None
        self.world.place(self.rig.rng, centre=(0, 0, 100))
        self.mem.w32(RC.G_SIM_FRAME, 1000)
        self.mem.w32(S.G_PVP_MODE_A, 0)
        for obj in self.world.everything:
            self.world.put(obj, (0, 0, D.f32(100)), dx=1000)
        self.world.enemy(self.world.mobs[0], 0)
        self.world.enemy(self.world.mobs[1], 0)
        self.world.put(self.world.player, (0, 0, D.f32(100)))
        self.rig.eview.state = {}

    def cast(self, group, sid, rank=5, owner=None):
        owner = self.world.player if owner is None else owner
        result = self.compare(group, CAST[sid], self.skill(sid), rank, owner,
                              (0, 0, D.f32(100)), 0)
        obj = self.bolts[sid]
        self.rig.eview.state.setdefault('alive', set()).add(obj)
        return obj, result

    def costs(self):
        for sid, address in ((16, 0x2ED1E4), (23, 0x2F8AF8)):
            skill = self.skill(sid)
            table = self.mem.u32(skill + 0x60)
            self.check('cost', 'address', self.mem.u32(table + 44) == address)
            self.check('cost', 'metadata', (self.mem.u32(skill + 8), self.mem.s16(skill + 12), self.mem.u32(skill + 4)) == (0, 30, 0))
            for rank in range(1, 21):
                model = S.Model(D.DC.ModelView(self.mem))
                expected = model.mana_cost(skill, rank)
                self.rig.emu.reset_log()
                self.rig.emu.call(address, skill, rank)
                got = self.rig.emu.f[0]
                self.counts['cost.comparisons'] += 1
                self.check('cost', 'reference', got == expected)
                self.check('cost', 'oracle', got == cost_oracle(sid, rank))
                self.check('cost', 'stores', not self.rig.emu.writes and not model.writes)
                if sid == 23:
                    self.check('cost', 'integer_step_control', (got != D.f32(7 + 3 * (rank - 1))) == (rank > 1))

    def admission_and_cast(self):
        for sid in (16, 23):
            self.setup()
            for owner in (0, self.world.player, self.world.copy, self.world.monster):
                r = self.compare('admission', USE[sid], self.skill(sid), owner)
                self.check('admission', 'returns_one', r['ret'] == 1)
                self.check('admission', 'no_callbacks', not r['emu_calls'])
            for rank in range(1, 21):
                self.setup()
                obj, r = self.cast('cast', sid, rank)
                self.check('cast', 'returns_zero', r['ret'] == 0)
                end, duration, level, vel = (0x60, 180, 0x5C, 0x6C) if sid == 16 else (0xC0, 120, 0x94, 0x9C)
                self.check('cast', 'fields', self.mem.u32(obj + end) == 1000 + duration and self.mem.s16(obj + level) == rank)
                speed = D.f32(450 if sid == 16 else 350)
                self.check('cast', 'velocity', tuple(self.mem.u32(obj + vel + 4 * i) for i in range(3)) == (C.mul(C.cos16(0), speed), C.mul(C.sin16(0), speed), 0))
                self.check('cast', 'owner_handles', all(self.mem.u32(obj + off) == self.world.nodes[self.world.player] for off in (0x4C, 0x54)))
                if sid == 16:
                    query = self.calls(r, 'world_collectObjectsInArc')
                    self.check('cast', 'arc_contract', len(query) == 1 and query[0][3:] == (self.world.player, D.f32(360), D.f32(75), 0))
                    self.check('cast', 'arm', self.mem.u32(obj + 0x64) == 1015)
                else:
                    self.check('cast', 'no_arc_query', not self.calls(r, 'world_collectObjectsInArc'))
            self.setup()
            self.fail_sizes = {0x80 if sid == 16 else 0xD0}
            self.mem.w32(self.bolts[sid] + 0x48, 0)
            _, r = self.cast('allocation', sid)
            self.check('allocation', 'no_object', self.mem.u32(self.bolts[sid] + 0x48) == 0)
            self.check('allocation', 'no_schedule', not self.calls(r, 'obj_runEveryFrame'))
            self.check('allocation', 'returns_zero', r['ret'] == 0)
        self.setup()
        self.prefill_spin = 12345
        obj, _ = self.cast('allocation', 23)
        self.check('allocation', 'preserves_prefill', self.mem.u32(obj + 0x98) == self.prefill_spin)

    def effects(self):
        for sid in (16, 23):
            for rank in range(1, 21):
                for variant in (0, 1):
                    self.setup()
                    owner = self.world.player if sid == 16 or not variant else self.world.monster
                    obj, _ = self.cast('effect_setup', sid, rank, owner)
                    target = self.world.mobs[0]
                    self.mem.w8(target + 0xB4, 0x10 if sid == 16 and variant else 0)
                    self.mem.w32(S.G_PVP_MODE_A, variant)
                    before = self.mem.u32(obj + 0x44)
                    r = self.compare('effect', HIT[sid], obj, target)
                    damage = self.calls(r, 'damage_apply')
                    self.check('effect', 'one_call', len(damage) == 1)
                    if not damage:
                        continue
                    a = damage[0]
                    self.check('effect', 'recipient', a[:3] == (target, owner, 100000))
                    stat = variant if sid == 16 else 0
                    low = self.stat(sid, stat, rank, owner)
                    if sid == 16:
                        self.check('effect', 'payload', a[5] == (0 if variant else 0x80000) and a[6] == S.descriptor() and a[-2] == D.f32(low))
                        self.check('effect', 'upper_range', low + 1 <= D.fl(a[-1]) <= int(low * 1.2) + 1)
                    else:
                        d = a[6]
                        self.check('effect', 'payload', a[5] == 0 and a[-2:] == (0, 0) and d[0] == 'desc' and d[1][0:2] == (0x16, low) and d[1][3] == 0 and d[2:] == (None, None, None))
                        self.check('effect', 'upper_range', low <= d[1][2] <= int(low * 1.2))
                    expected_seed = before
                    for _ in range(2 if sid == 16 else 1):
                        expected_seed = S.lcg(expected_seed)
                    self.check('effect', 'own_draws', self.mem.u32(obj + 0x44) == expected_seed)

    def hit_gates(self):
        for sid in (16, 23):
            for condition in ('enemy', 'friendly', 'filtered', 'player_bit', 'owner_absent', 'repeat', 'noncreature'):
                self.setup()
                obj, _ = self.cast('gate_setup', sid)
                target = self.world.mobs[0]
                self.enemy = condition != 'friendly'
                if condition in ('filtered', 'player_bit'):
                    self.mem.w64(target + 0xA8, 0x200)
                    if condition == 'player_bit':
                        self.mem.w32(target + 0xC, 0x60)
                if condition == 'owner_absent':
                    self.mem.w32(obj + 0x54, 0)
                    self.mem.w32(obj + 0x4C, 0)
                    self.enemy = False
                if condition == 'noncreature':
                    self.mem.w32(target + 0xC, 0)
                    self.enemy = False
                latch = 0x78 if sid == 16 else 0xC4
                if condition == 'repeat':
                    self.mem.w32(obj + latch, 1)
                before = self.mem.u32(obj + 0x44)
                r = self.compare('gate', HIT[sid], obj, target)
                admitted = condition not in ('friendly', 'filtered') and not (sid == 16 and condition in ('repeat', 'noncreature'))
                damage = self.calls(r, 'damage_apply')
                self.check('gate', condition, len(damage) == int(admitted))
                self.check('gate', 'draw_gate', (self.mem.u32(obj + 0x44) != before) == admitted)
                self.check('gate', 'latch', self.mem.u32(obj + latch) == int(admitted or condition == 'repeat'))
                if sid == 23:
                    self.check('gate', 'last_target', self.mem.u32(obj + 0xCC) == (target if admitted else 0))
                if admitted and condition in ('owner_absent', 'noncreature'):
                    self.check('gate', 'no_attacker', damage[0][1] == 0)
        self.setup()
        obj, _ = self.cast('gate_setup', 23)
        first, second = self.world.mobs[:2]
        for target, accepted in ((first, True), (second, True), (first, False)):
            self.enemy = accepted
            r = self.compare('gate_sequence', HIT[23], obj, target)
            self.check('gate_sequence', 'admission', len(self.calls(r, 'damage_apply')) == int(accepted))
            self.check('gate_sequence', 'last_target', self.mem.u32(obj + 0xCC) == (target if accepted else 0))
            self.check('gate_sequence', 'latch_retained', self.mem.u32(obj + 0xC4) == 1)

    def homing(self):
        for rank in (4, 5):
            for age in (14, 15, 16):
                for present in (False, True):
                    self.setup()
                    target = self.world.mobs[0]
                    self.world.put(target, (D.f32(100), D.f32(100), D.f32(100)))
                    self.arc = [target] if present else []
                    obj, _ = self.cast('homing_setup', 16, rank)
                    self.mem.w32(RC.G_SIM_FRAME, 1000 + age)
                    self.compare('homing', RUN[16], obj)
                    expected = 182 if rank == 5 and age == 16 and present else 0
                    self.check('homing', 'heading', self.mem.s16(obj + 0x38) == expected)
        # The supplied first node wins even if the second would turn the other way.
        self.setup()
        first, second = self.world.mobs[:2]
        self.world.put(first, (D.f32(100), D.f32(100), D.f32(100)))
        self.world.put(second, (D.f32(100), D.f32(-100), D.f32(100)))
        self.arc = [first, second]
        obj, _ = self.cast('homing_setup', 16)
        self.mem.w32(RC.G_SIM_FRAME, 1016)
        self.compare('homing', RUN[16], obj)
        self.check('homing', 'first_node', self.mem.s16(obj + 0x38) == 182)

    def endings(self):
        for sid in (16, 23):
            duration = 180 if sid == 16 else 120
            for age in (duration - 1, duration, duration + 1):
                self.setup()
                obj, _ = self.cast('timing_setup', sid, 4)
                self.mem.w32(RC.G_SIM_FRAME, 1000 + age)
                r = self.compare('timing', RUN[sid], obj)
                self.check('timing', 'expiry', self.deleted(r, obj) == (age >= duration))
            for ground, contact, accepted in ((False, False, False), (True, False, False),
                                               (False, True, False), (False, True, True)):
                self.setup()
                obj, _ = self.cast('collision_setup', sid, 4)
                target = self.world.mobs[0]
                self.world.put(target, (D.f32(6), 0, D.f32(100)))
                self.box = [target] if contact else []
                self.ground, self.enemy = ground, accepted
                r = self.compare('collision', RUN[sid], obj)
                self.check('collision', 'end_gate', self.deleted(r, obj) == (ground or contact and accepted))
                self.check('collision', 'damage_gate', len(self.calls(r, 'damage_apply')) == int(contact and accepted))

    def release(self):
        # Both tiers straddle their onset; extra ranks straddle rounding and cap 20.
        for owner_kind, ranks in ((0, (4, 5, 6, 7, 20, 21, 24)), (1, (9, 10, 14, 15, 20, 21, 24, 26))):
            for rank in ranks:
                self.setup()
                owner = self.world.monster if owner_kind else self.world.player
                obj, _ = self.cast('release_setup', 23, rank, owner)
                self.mem.w32(obj + 0xCC, self.world.mobs[1])
                self.mem.w32(RC.G_SIM_FRAME, 1120)
                expected = self.stat(23, 1, rank, owner, 20)
                r = self.compare('release', RUN[23], obj)
                allocations = [a for a in self.calls(r, 'pool_new') if a == (0x7C,)]
                self.check('release', 'count', len(allocations) == expected)
                if rank == 24:
                    self.check('release', 'cap_control', len(allocations) == (2 if owner_kind else 8))
                if rank == 26:
                    self.check('release', 'nonplayer_cap_control', len(allocations) == 2 and self.stat(23, 1, rank, owner, 0) == 3)
                self.check('release', 'ray_count', len(self.calls(r, 'terrain_raycast')) == expected * 10)
                self.check('release', 'deletion', self.deleted(r, obj))
                for shard in self.shards[:expected]:
                    self.check('release', 'child_fields', self.mem.u32(shard + 0x78) == self.world.mobs[1] and self.mem.u32(shard + 0x6C) == 1180 and self.mem.s16(shard + 0x58) == rank)
        self.setup()
        obj, _ = self.cast('release_setup', 23)
        self.fail_sizes = {0x7C, 0x248}
        self.mem.w32(RC.G_SIM_FRAME, 1120)
        r = self.compare('release', RUN[23], obj)
        self.check('release', 'failed_allocations_continue', len([a for a in self.calls(r, 'pool_new') if a == (0x7C,)]) == 3 and self.deleted(r, obj))
        for answers in ([D.f32(1)] * 10, [0] * 10,
                        [D.f32(-1) if i in (2, 7) else D.f32(1) for i in range(10)]):
            self.setup()
            self.rays = answers
            obj, _ = self.cast('direction_setup', 23)
            self.mem.w32(RC.G_SIM_FRAME, 1120)
            r = self.compare('direction', RUN[23], obj)
            self.check('direction', 'ten_per_child', len(self.calls(r, 'terrain_raycast')) == 30)
            # Reverse only the final 33 documented own-generator transitions: the
            # unrelated particle/debris draw counts are deliberately not assumed.
            state = self.mem.u32(obj + 0x44)
            inverse = pow(1664525, -1, 1 << 32)
            draws = []
            for _ in range(33):
                draws.append(state >> 16)
                state = ((state - 1013904223) * inverse) & 0xFFFFFFFF
            draws.reverse()
            clear = [i for i, value in enumerate(answers) if D.fl(value) <= 0]
            for index, shard in enumerate(self.shards[:3]):
                samples = draws[index * 11:(index + 1) * 11]
                heading = samples[clear[-1] + 1] if clear else samples[0] % 32767 - 16384
                self.check('direction', 'last_clear_or_initial', self.mem.u16(shard + 0x38) == heading & 0xFFFF)

    def make_child(self):
        self.setup()
        obj, _ = self.cast('child_setup', 23, 5)
        self.mem.w32(obj + 0xCC, self.world.mobs[1])
        self.mem.w32(RC.G_SIM_FRAME, 1120)
        self.compare('child_setup', RUN[23], obj)
        return self.shards[0]

    def children(self):
        for condition in ('enemy', 'excluded', 'latched', 'friendly', 'filtered', 'owner_absent'):
            obj = self.make_child()
            target = self.world.mobs[1 if condition == 'excluded' else 0]
            if condition == 'latched':
                self.mem.w32(obj + 0x70, 1)
            if condition == 'filtered':
                self.mem.w64(target + 0xA8, 0x200)
            if condition == 'owner_absent':
                self.mem.w32(obj + 0x4C, 0)
            self.enemy = condition not in ('friendly', 'owner_absent')
            r = self.compare('child_hit', ENTRY[0x2F71AC], obj, target)
            admitted = condition in ('enemy', 'owner_absent')
            damage = self.calls(r, 'damage_apply')
            self.check('child_hit', condition, len(damage) == int(admitted))
            if damage:
                owner = self.world.player if condition == 'enemy' else 0
                self.check('child_hit', 'stat_2', damage[0][6][1][:2] == (0x16, self.stat(23, 2, 5, owner)))
        for age in (59, 60, 61):
            obj = self.make_child()
            self.mem.w32(RC.G_SIM_FRAME, 1120 + age)
            r = self.compare('child_timing', ENTRY[0x2F6B3C], obj)
            self.check('child_timing', 'expiry', self.deleted(r, obj) == (age >= 60))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='local/spells-r3/projectiles-counts.json')
    args = parser.parse_args()
    output = Path(args.output).absolute()
    allowed = (ROOT / 'local/spells-r3').resolve()
    if not output.resolve().is_relative_to(allowed):
        parser.error('output must remain under local/spells-r3/')
    elf = ROOT / 'local/SLUS_209.73'
    if not elf.is_file() or hashlib.sha256(elf.read_bytes()).hexdigest() != D.DC.EXPECTED_SHA256:
        print('BLOCKED: private input missing or unexpected; 0 comparisons')
        return 2
    checks = None
    method = 'initialization'
    failures = Counter()
    try:
        checks = Checks(elf)
        for method in ('costs', 'admission_and_cast', 'effects', 'hit_gates', 'homing', 'endings', 'release', 'children'):
            getattr(checks, method)()
    except Exception as exc:
        # Interpreter diagnostics can contain instruction words; never export
        # them into the count receipt or console log, including during startup.
        failures[method + '.aborted.' + type(exc).__name__] += 1
    if checks is not None:
        failures.update(checks.failures)
    report = {'status': 'FAIL' if failures else 'PASS', 'ids': [16, 23],
              'fpu': 'ps2', 'counts': dict(sorted(checks.counts.items())) if checks else {},
              'failures': dict(sorted(failures.items()))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
