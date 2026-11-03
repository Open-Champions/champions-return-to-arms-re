#!/usr/bin/env python3
"""Bounded original/reference comparisons for IDs 49 and 55.

Run with unittest preloaded and PYTHONDONTWRITEBYTECODE=1; see the companion
document. Private input is read-only. Only counts are emitted. The world, pool,
relationships, damage result, presentation and movement are scripted, not gameplay.
Existing models and vectors are imported without changes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import unittest  # noqa: F401 - preload before adding tools to the search path

sys.path.append(str(Path(__file__).resolve().parent))
import difftest_skills_b as B
import ref_anim as A

SB, RC, C = B.SB, B.RC, B.C
ROOT = Path(__file__).resolve().parents[1]


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class ProbeFailure(Exception):
    pass


def exact_count_discrepancy(model_calls, original_calls, model_bytes,
                            original_bytes, extra_bytes, first_calls):
    """Permit just the second recipient's callback and prescribed writes."""
    return (model_calls[:2] == first_calls
            and original_calls == model_calls[:1] + model_calls[2:]
            and set(model_bytes) - set(original_bytes) == set(extra_bytes)
            and not set(original_bytes) - set(model_bytes)
            and all(model_bytes[a] == value for a, value in original_bytes.items())
            and all(model_bytes.get(a) == value for a, value in extra_bytes.items()))


class Probe:
    def __init__(self, elf):
        B.OPTIONS.update(seed=4955, fpu='ps2', trace_first=False)
        C.set_fpu('ps2')
        self.rig = B.Rig(str(elf), 4955)
        self.mem, self.world = self.rig.emu.mem, self.rig.world
        self.counts = Counter()
        self.functions = Counter()
        self.group = 'setup'
        self.failure = None
        self.discrepancies = Counter()
        w = self.world
        w.on_world_collectObjectsInArc = lambda a, v, r: B.Res(outs=[self.arc])
        w.on_world_collectInSphere = lambda a, v, r: B.Res(outs=[self.sphere])
        w.on_world_collectObjectsInBox = lambda a, v, r: B.Res(outs=[self.box])
        w.on_Creature_v20 = lambda a, v, r: B.Res(int(a[1] in self.enemies))
        w.on_Creature_v21 = lambda a, v, r: B.Res(int(a[1] in self.allies))
        w.on_Creature_v22 = lambda a, v, r: B.Res(int(a[1] in self.team))
        w.on_Player_move = lambda a, v, r: B.Res()
        w.on_model_getAttachPoint = lambda a, v, r: B.Res(outs=[a[1], (0, 0, 0)])
        w.on_terrain_heightAtPoint = lambda a, v, r: B.Res(f=a[1][2])
        w.on_damage_apply = self.damage
        self.reset()

    def reset(self):
        w, m = self.world, self.mem
        w.live.clear()
        w.place(random.Random(4955))
        w.pool_fail, w.sample_counts, w.forced_events = 0.0, (3,), 0
        self.arc, self.sphere, self.box = [], [], []
        self.enemies, self.allies, self.team = set(), set(), set()
        self.post_damage = None
        for obj in w.objects:
            B.put_vec(m, obj + 0x10, (0.0, 0.0, 0.0))
            m.w32(obj + 0xC, 0x40 if obj in w.players else 0x20)
            m.w32(obj + 0x450, 0)
            m.w16(obj + 0x38, 0)
            m.w16(obj + 0x11A, 0x10)
            m.wf32(obj + 0x228, 100.0)
            m.wf32(obj + 0x22C, 120.0)
        for slot in range(4):
            rec = RC.G_PLAYERS + slot * RC.REC_SIZE
            m.wf32(rec + 0xAC, 0.0)
            m.wf32(rec + 0xB0, 120.0)
            m.w32(rec + 0x43FC, w.item)
            m.w8(rec + 0x4A86, 0)
        m.w32(SB.G_ALIVE_COUNT, 0)
        m.w32(SB.G_PVP_MODE_A, 0)

    def damage(self, args, view, rng):
        if self.post_damage is not None:
            view.poke(args[0] + 0x228, 4, self.post_damage)
        return B.Res(1)

    def check(self, ok, label):
        self.counts['assertions'] += 1
        if not ok:
            self.counts['failures'] += 1
            self.failure = self.group + ':' + label
            raise ProbeFailure(self.failure)

    def compare(self, address, method, args, ret='n'):
        out = self.rig.compare(B.FUNCTION_AT[address], method, args, ret=ret)
        self.counts['comparisons'] += 1
        self.counts[self.group + ':comparisons'] += 1
        self.functions['%06x' % address] += 1
        for key in ('fault', 'calls', 'writes', 'seed', 'result', 'both_fault'):
            self.check(out[key] is None, key)
        self.check(not self.rig.unknown, 'unknown_targets')
        return out

    def slot(self, sid, slot, args=(), ret='i'):
        skill = B.skill_obj(self.mem, sid)
        fn = self.mem.u32(self.mem.u32(skill + 0x60) + 8 * slot + 4)
        return self.compare(fn, SB.SKILL_BODIES[fn], (skill,) + tuple(args), ret)

    def cast(self, sid, rank, owner=None):
        owner = self.world.players[0] if owner is None else owner
        out = self.slot(sid, 2, (rank, owner, self.world.scratch, 0))
        obj = out['ret'] & B.M32
        self.check(bool(obj), 'allocation')
        self.world.live.add(obj)
        return obj

    def run(self, sid, obj):
        fn, method = ((0x2DE7DC, 'bash_run') if sid == 49 else
                      (0x2E90B8, 'healing_run'))
        return self.compare(fn, method, (obj, self.world.scratch, 0))

    @staticmethod
    def calls(out, name):
        return [args for called, args in out['emu_calls'] if called == name]

    def stat(self, sid, index, rank):
        return self.slot(sid, 10, (index, rank))['ret'] & B.M32

    def alive(self, slots):
        self.mem.w32(SB.G_ALIVE_COUNT, len(slots))
        for i, slot in enumerate(slots):
            self.mem.w32(SB.G_ALIVE_LIST + 4 * i, slot)

    def costs_and_gates(self):
        self.group = 'costs'
        for sid in (49, 55):
            for rank in range(1, 21):
                out = self.slot(sid, 5, (rank,), ret='f')
                expected = (16 + 3 * (rank - 1) if sid == 49 else
                            55 + 6 * (rank - 1))
                self.check(out['mret'] == self.rig.emu.f[0] == bits(expected),
                           'exact_integer_float')
                self.counts['cost_rank_pairs'] += 1
        self.group = '49_gate'
        m, w = self.mem, self.world
        rec = RC.G_PLAYERS
        for owner, equipped, kind, expect in (
                (w.players[0], False, 0, 0), (w.players[0], False, 4, 0),
                (w.players[0], True, 4, 0), (w.players[0], True, 3, 1),
                (w.players[0], True, 5, 1), (w.players[0], True, 255, 1),
                (w.monsters[0], False, 4, 1)):
            m.w32(rec + 0x43FC, w.item if equipped else 0)
            m.w8(rec + 0x4A86, kind)
            out = self.slot(49, 1, (owner,))
            self.check(out['ret'] == expect, 'equipment_gate')
            self.check(len(self.calls(out, 'hud_showMessage')) == 1 - expect,
                       'notice_gate')
        self.group = '55_gate'
        for owner in (w.players[0], w.monsters[0], 0):
            self.check(self.slot(55, 1, (owner,))['ret'] == 1, 'base_gate')
        for sid in (49, 55):
            self.group = '%d_allocation' % sid
            self.reset()
            w.pool_fail = 1.0
            out = self.slot(sid, 2, (1, w.players[0], w.scratch, 0))
            self.check(out['ret'] == 0, 'allocation_failure')
            self.check(out['draws'] == 0, 'no_constructor_draw')
            self.check(len(self.calls(out, 'sound_playOnObject')) == int(sid == 49),
                       'sound_before_allocation')

    def targeting_49(self):
        self.group = '49_target'
        m, w = self.mem, self.world
        a, b = w.monsters[:2]
        for flags, expect in (((), None), ((0x20,), a),
                              ((0x1000020, 0x1000020), None),
                              ((0x1000020, 0x20), a), ((0x20, 0x1000020), a)):
            self.reset()
            self.arc = [a, b][:len(flags)]
            for obj, value in zip(self.arc, flags):
                m.w32(obj + 0xC, value)
            obj = self.cast(49, 1)
            self.check(m.u32(obj + 0x24) == (expect or 0), 'head_selection')
            self.check(m.u32(w.players[0] + 0x58C) == 6, 'action_state')
            queries = self.calls({'emu_calls': self.rig.calls}, 'world_collectObjectsInArc')
            self.check(len(queries) == 1 and queries[0][-3:] ==
                       (bits(100), bits(90), 0), 'query_arguments')

    def effects_49(self):
        self.group = '49_effect'
        m, w = self.mem, self.world
        for rank in range(1, 21):
            self.reset()
            obj = self.cast(49, rank)
            candidates = [v for v in w.objects if v != w.players[0]]
            m.w32(candidates[0] + 0xC, 0x1000020)
            self.arc, self.enemies = candidates, set(candidates[2:])
            w.forced_events, w.pool_fail = 2, 1.0
            out = self.run(49, obj)
            hits = self.calls(out, 'damage_apply')
            count = 1 + (rank + 1) // 4
            self.check([a[0] for a in hits] == candidates[2:2 + count], 'cap_order_filter')
            centre = 50 + 10 * (rank - 1)
            knock = 0x40000 if rank < 6 else 0x80000 if rank < 16 else 0x200000
            for a in hits:
                self.check(a[2] == 100000 and a[5:8] == (knock | 0x40, 0, 1),
                           'damage_flags')
                self.check(a[-2:] == (bits(centre * 4 // 5), bits(centre * 6 // 5)),
                           'damage_bounds')
            self.check(m.u32(obj + 0x18) == m.u32(obj + 0x1C) == 1, 'strike_latches')
            again = self.run(49, obj)
            self.check(not self.calls(again, 'damage_apply') and again['draws'] == 0,
                       'single_strike')
        self.group = '49_stun'
        for hp, roll_delta, expect in ((bits(1), 0, True), (bits(1), 1, False),
                                       (0, 0, False), (bits(-1), 0, False)):
            self.reset()
            obj = self.cast(49, 5)
            target = w.monsters[0]
            self.arc, self.enemies = [target], {target}
            self.post_damage = hp
            w.forced_events, w.pool_fail = 2, 1.0
            chance = self.stat(49, 1, 5)
            duration = self.stat(49, 2, 5) * 60
            draw = chance - 1 + roll_delta
            seed = (((draw << 16) - B.INC) * pow(B.STEP, -1, 1 << 32)) & B.M32
            m.w32(RC.G_RAND_SEED, seed)
            out = self.run(49, obj)
            self.check(self.calls(out, 'Creature.v30') ==
                       ([(target, duration, 1)] if expect else []), 'stun_threshold')
            self.check(out['draws'] == int(hp == bits(1)), 'positive_hp_draw')
        self.group = '49_fallback'
        for eligible in (False, True):
            self.reset()
            obj = self.cast(49, 1)
            a, b = w.props
            m.w32(a + 0xC, 0 if eligible else 0x1000000)
            m.w32(b + 0xC, 0 if eligible else 0x40)
            self.arc = [w.monsters[0]]
            self.sphere = [w.monsters[1], a, b]
            w.forced_events, w.pool_fail = 2, 1.0
            out = self.run(49, obj)
            hits = self.calls(out, 'damage_apply')
            self.check(len(hits) == int(eligible), 'fallback_filter')
            if eligible:
                self.check(hits[0][0] == a and hits[0][7] == 0, 'fallback_first')
            self.check(m.u32(obj + 0x18) == 1, 'empty_strike_done')
            self.check(not self.calls(self.run(49, obj), 'damage_apply'), 'no_retry')
        self.group = '49_first_light'
        for fail in (False, True):
            self.reset()
            obj = self.cast(49, 3)
            self.arc = w.monsters[:2]
            self.enemies = set(self.arc)
            w.forced_events, w.pool_fail = 2, float(fail)
            out = self.run(49, obj)
            self.check(len(self.calls(out, 'damage_apply')) == 2, 'two_hits')
            self.check(self.calls(out, 'pool_new') == [(0xBC,)], 'first_hit_only')
            self.check(out['draws'] == (2 if fail else 3), 'light_allocation_draw')

    def timing_49(self):
        self.group = '49_timing'
        self.reset()
        m, w = self.mem, self.world
        owner = w.players[0]
        obj = self.cast(49, 1)
        clip = self.calls({'emu_calls': self.rig.calls}, 'anim_startBlendInOut')[0][1]
        # Synthetic long clip and one non-root track isolate the event clock.
        data = A.encode_clip([((0, 0, 0), (4096, 0, 0, 0))], 120)
        model_clip = A.Clip(data)
        event_time, event_mask = m.u32(clip + 0x1C), m.u8(clip + 0x20)
        self.check(event_mask == 2, 'constructor_event_mask')
        model_clip.events[1] = [event_time, event_mask]
        m.w32(clip, 1)
        m.w32(clip + 4, 120)
        for off in (0x14, 0x18, 0x24, 0x28, 0x2C, 0x30, 0x38, 0x48, 0x4C):
            m.w32(clip + off, 0)
        state = owner + 0x114
        for off in range(0, 0x108, 4):
            m.w32(state + off, 0)
        m.w8(state + 4, 1)
        m.w8(state + 5, 8)
        for off, value in ((0, clip), (8, C.ONE), (0x10, C.ONE), (0x1C, 0x10)):
            m.w32(state + 8 + off, value)
        model_state = A.AnimState()
        model_state.count = 1
        track = model_state.tracks[0]
        track.clip, track.weight, track.life, track.flags = model_clip, C.ONE, C.ONE, 0x10
        system = A.AnimSystem(decoder_slots=2, pose_buffers=2)
        observed = []
        self.arc, self.enemies = [w.monsters[0]], {w.monsters[0]}
        for tick in range(1, 38):
            events = B.real_anim_advance(self.rig, state)
            want = A.anim_advance(system, C.ONE, model_state, False, False, False)[0]
            self.counts['animation_comparisons'] += 1
            self.check(events == want, 'animation_events')
            self.check(m.u32(state + 8 + 0x18) == track.time and
                       m.u16(state + 6) == model_state.flags, 'animation_time_status')
            if events & 2:
                observed.append(tick)
            if tick >= 35:
                w.forced_events = events
                out = self.run(49, obj)
                self.check(len(self.calls(out, 'damage_apply')) == int(tick == 36),
                           'event_drives_single_strike')
        self.check(observed == [36], 'event_call_36')
        for status, repeat, ends in ((0x10, 0, False), (0, 0, True), (0x10, 1, True)):
            m.w16(owner + 0x11A, status)
            m.w32(owner + 0x450, repeat)
            m.w32(owner + 0x58C, 6)
            out = self.run(49, obj)
            self.check(B.ended(out, obj) == ends, 'termination_gate')
            self.check(m.u32(owner + 0x58C) == (2 if ends else 6), 'termination_state')

    def range_55(self):
        self.group = '55_range'
        m, w = self.mem, self.world
        recipient = w.players[1]
        rec = RC.G_PLAYERS + RC.REC_SIZE
        for rank in range(1, 21):
            self.reset()
            obj = self.cast(55, rank)
            reach = 12 * self.stat(55, 1, rank)
            self.alive([1])
            for axis in (0, 2):
                for delta in (-1, 0, 1):
                    B.put_vec(m, recipient + 0x10, (0.0, 0.0, 0.0))
                    m.w32(recipient + 0x10 + 4 * axis, bits(reach) + delta)
                    m.wf32(rec + 0xAC, 0.0)
                    self.run(55, obj)
                    self.check((m.u32(rec + 0xAC) != 0) == (delta <= 0),
                               'three_axis_inclusive_radius')
        self.group = '55_team_list'
        for mode, accept, listed, expected in ((0, False, True, True),
                                              (1, False, True, False),
                                              (1, True, True, True),
                                              (0, True, False, False)):
            self.reset()
            obj = self.cast(55, 1)
            self.alive([0, 1] if listed else [])
            self.team = {w.players[0], recipient} if accept else set()
            m.w32(SB.G_PVP_MODE_A, mode)
            out = self.run(55, obj)
            self.check((m.u32(rec + 0xAC) != 0) == expected, 'recipient_gate')
            self.check(len(self.calls(out, 'Creature.v22')) == (2 if mode and listed else 0),
                       'team_call_gate')
            self.check((m.u32(RC.G_PLAYERS + 0xAC) != 0) == expected, 'owner_list_gate')

    def effects_55(self):
        self.group = '55_health'
        m, w = self.mem, self.world
        for hp in (bits(119) - 1, bits(119), bits(119) + 1, bits(120), bits(121)):
            self.reset()
            obj = self.cast(55, 20)
            self.alive([0])
            m.w32(RC.G_PLAYERS + 0xAC, hp)
            expected = C.add(hp, m.u32(obj + 0x1C)) if hp <= bits(119) else hp
            self.run(55, obj)
            self.check(m.u32(RC.G_PLAYERS + 0xAC) == expected, 'guard_without_clamp')
            if hp == bits(119):
                self.check(m.f32(RC.G_PLAYERS + 0xAC) > 120, 'overshoot')
        self.group = '55_cached_amount'
        self.reset()
        obj = self.cast(55, 10)
        cached = m.u32(obj + 0x1C)
        self.alive([0, 1])
        for slot in (0, 1):
            m.wf32(RC.G_PLAYERS + slot * RC.REC_SIZE + 0xB0, 240.0)
        self.run(55, obj)
        self.check(m.u32(RC.G_PLAYERS + 0xAC) == cached == m.u32(obj + 0x1C),
                   'cached_self_amount')
        other = m.u32(RC.G_PLAYERS + RC.REC_SIZE + 0xAC)
        m.wf32(RC.G_PLAYERS + RC.REC_SIZE + 0xAC, 0.0)
        m.wf32(RC.G_PLAYERS + RC.REC_SIZE + 0xB0, 120.0)
        self.run(55, obj)
        self.check(other == C.mul(bits(2), m.u32(RC.G_PLAYERS + RC.REC_SIZE + 0xAC)),
                   'recipient_current_maximum')
        self.group = '55_nonplayer'
        for flags, accept, x, z, expected in ((0x20, True, 60, 60, True),
                                             (0x20, False, 60, 60, False),
                                             (0x28, True, 0, 0, False),
                                             (0x20, True, 61, 0, False)):
            self.reset()
            owner, target = w.monsters[:2]
            obj = self.cast(55, 1, owner)
            m.w32(owner + 0xC, flags)
            self.box, self.allies = [owner, target], {target} if accept else set()
            B.put_vec(m, target + 0x10, (x, 0.0, z))
            m.wf32(target + 0x228, 120.0)
            out = self.run(55, obj)
            self.check((m.f32(target + 0x228) > 120) == expected, 'planar_unclamped')
            self.check((m.f32(owner + 0x228) > 100) == (flags == 0x20), 'self_bypasses_ally')
            self.check(len(self.calls(out, 'world_collectObjectsInBox')) == int(flags == 0x20),
                       'owner_dead_gate')

    def timing_55(self):
        self.group = '55_timing'
        m, w = self.mem, self.world
        for rank in (1, 10, 20):
            self.reset()
            obj = self.cast(55, rank)
            self.alive([0])
            for tick in range(1, 69):
                # Keeping health low isolates the last heal and tint from saturation.
                m.wf32(RC.G_PLAYERS + 0xAC, 0.0)
                m.w16(w.players[0] + 0x9E, 0)
                out = self.run(55, obj)
                self.check(B.ended(out, obj) == (tick == 68), 'expiry_call')
                self.check(m.u32(RC.G_PLAYERS + 0xAC) == m.u32(obj + 0x1C),
                           'heal_including_last_call')
                self.check(bool(m.u16(w.players[0] + 0x9E)) == (tick <= 8), 'tint_first_eight')
            self.counts['55_lifetime_cases'] += 1
        self.group = '55_tint_boundary'
        for clock in (0x3E050EF7, 0x3E050EF8, 0x3E050EF9):
            self.reset()
            obj = self.cast(55, 1)
            self.alive([0])
            m.w32(obj + 0x18, clock)
            m.w16(w.players[0] + 0x9E, 0)
            self.run(55, obj)
            self.check(bool(m.u16(w.players[0] + 0x9E)) == (clock < 0x3E050EF8),
                       'strict_preincrement_tint')
        self.group = '55_expiry_boundary'
        threshold = 0x3F90A1DF
        near = C.sub(threshold, SB.DT)
        for delta in (-1, 0, 1):
            desired = threshold + delta
            candidates = [v for v in range(near - 4, near + 5)
                          if C.add(v, SB.DT) == desired]
            self.check(bool(candidates), 'clock_preimage')
            self.reset()
            obj = self.cast(55, 1)
            self.alive([0])
            m.w32(obj + 0x18, candidates[0])
            out = self.run(55, obj)
            self.check(m.u32(obj + 0x18) == desired, 'postincrement_clock')
            self.check(B.ended(out, obj) == (delta > 0), 'strict_expiry')
            self.check(m.u32(RC.G_PLAYERS + 0xAC) == m.u32(obj + 0x1C),
                       'heal_before_expiry')

    def mutable_count_55(self):
        """Adversarial callback exposes a model difference, not a gameplay claim.

        Original 0x2e9180 rereads the count; the existing reference snapshots it.
        Keep this expected discrepancy separate from the matching comparisons.
        """
        self.group = '55_mutable_count'
        self.reset()
        m, w = self.mem, self.world
        obj = self.cast(55, 1)
        self.alive([0, 1])
        m.w32(SB.G_PVP_MODE_A, 1)
        previous = w.on_Creature_v22
        views = {}
        owner, other = w.players[:2]
        recipient = RC.G_PLAYERS + RC.REC_SIZE
        percent = self.stat(55, 2, 1)
        share = C.mul(C.mul(m.u32(recipient + 0xB0), SB.Model.F_HEAL_RATE),
                      C.mul(C.from_int(percent), SB.F_0_01))
        extra = {}
        for addr, size, value in [(recipient + 0xAC, 4, C.add(m.u32(recipient + 0xAC), share))] + [
                (other + off, 2, value) for off, value in SB.Model.HEAL_TINT]:
            extra.update({addr + i: (value >> (8 * i)) & 255 for i in range(size)})
        before_extra = {addr: m.load(addr, 1) for addr in extra}
        first_health = C.add(m.u32(RC.G_PLAYERS + 0xAC), m.u32(obj + 0x1C))

        def shrink(args, view, rng):
            if isinstance(view, B.ModelView):
                views['model'] = view
            view.poke(SB.G_ALIVE_COUNT, 4, 0)
            return B.Res(1)

        w.on_Creature_v22 = shrink
        try:
            out = self.rig.compare(B.FUNCTION_AT[0x2E90B8], 'healing_run',
                                   (obj, w.scratch, 0))
        finally:
            w.on_Creature_v22 = previous
        self.counts['adversarial_comparisons'] += 1
        for key in ('fault', 'seed', 'result', 'both_fault'):
            self.check(out[key] is None, 'unexpected_' + key)
        for key in ('calls', 'writes'):
            self.check(out[key] is not None, 'expected_' + key)
            self.discrepancies[key] += 1
        self.check(not self.rig.unknown, 'unknown_targets')
        self.check(len(self.calls(out, 'Creature.v22')) == 1, 'original_stops_after_first')
        self.check(sum(name == 'Creature.v22' for name, _ in out['model_calls']) == 2,
                   'model_uses_initial_count')
        self.check(m.u32(RC.G_PLAYERS + 0xAC) != 0 and
                   m.u32(RC.G_PLAYERS + RC.REC_SIZE + 0xAC) == 0, 'original_recipient_set')
        self.check(m.u32(RC.G_PLAYERS + 0xAC) == first_health, 'exact_first_health')
        self.check(all(m.load(a, 1) == value for a, value in before_extra.items()),
                   'second_recipient_unchanged')
        view = views['model']
        keep = lambda addr: not B.is_stack(addr) and not B.is_model_stack(addr)
        model_bytes = {a: view.load(a, 1) for a in view.bytes if keep(a)}
        original_bytes = {a: m.load(a, 1) for a in
                          self.rig.stored_bytes() | self.rig.eview.touched if keep(a)}
        first_calls = [('Creature.v22', (owner, owner)), ('Creature.v22', (owner, other))]
        args = (out['model_calls'], out['emu_calls'], model_bytes,
                original_bytes, extra, first_calls)
        self.check(exact_count_discrepancy(*args), 'only_diagnosed_difference')
        # Negative controls must reject extra faults without changing original code.
        bad_health = dict(original_bytes)
        bad_health[RC.G_PLAYERS + 0xAC] ^= 1
        bad_calls = list(out['emu_calls'])
        name, call_args = bad_calls[-1]
        bad_calls[-1] = (name, (call_args[0] ^ 1,) + call_args[1:])
        bad_store = dict(original_bytes)
        bad_store[obj + 0x1C] = m.load(obj + 0x1C, 1)
        bad_extra = dict(model_bytes)
        bad_extra[recipient + 0xAC] ^= 1
        for altered in (
                (args[0], args[1], model_bytes, bad_health, extra, first_calls),
                (args[0], bad_calls, model_bytes, original_bytes, extra, first_calls),
                (args[0], args[1], model_bytes, bad_store, extra, first_calls),
                (args[0], args[1], bad_extra, original_bytes, extra, first_calls)):
            self.check(not exact_count_discrepancy(*altered), 'reject_extra_discrepancy')
            self.counts['discrepancy_mutations_rejected'] += 1
        self.counts['documented_model_discrepancies'] += 1

    def execute(self):
        for operation in (self.costs_and_gates, self.targeting_49, self.effects_49,
                          self.timing_49, self.range_55, self.effects_55, self.timing_55,
                          self.mutable_count_55):
            operation()

    def report(self):
        status = 'FAIL' if self.failure else ('PASS_WITH_MODEL_DISCREPANCY'
                  if self.discrepancies else 'PASS')
        return {'status': status, 'ids': [49, 55],
                'fpu': 'ps2', 'counts': dict(sorted(self.counts.items())),
                'function_comparisons': dict(sorted(self.functions.items())),
                'documented_discrepancy_properties': dict(self.discrepancies),
                'unexpected_failure_count': self.counts['failures'],
                'unknown_target_count': len(self.rig.unknown),
                'failure_case': self.failure, 'real_gameplay_established': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, default=ROOT / 'local/SLUS_209.73')
    parser.add_argument('--output', type=Path, default=ROOT / 'local/spells-r3/support-counts.json')
    args = parser.parse_args()
    destination = args.output.resolve()
    allowed = (ROOT / 'local/spells-r3').resolve()
    if not destination.is_relative_to(allowed):
        parser.error('output must be under local/spells-r3/')
    if not args.elf.is_file() or hashlib.sha256(args.elf.read_bytes()).hexdigest() != B.DC.EXPECTED_SHA256:
        print(json.dumps({'status': 'BLOCKED', 'input_verified': False}))
        return 2
    probe = Probe(args.elf)
    try:
        probe.execute()
    except ProbeFailure:
        pass
    report = probe.report()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    return int(probe.failure is not None)


if __name__ == '__main__':
    sys.exit(main())
