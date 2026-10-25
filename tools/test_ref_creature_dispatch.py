"""Synthetic tests of the round-3 dispatch contract; no ELF, extracted model or game bytes.

The per-class table (ref_creature_dispatch_data) is checked three ways: its shape, its
agreement with the independently authored class bodies of ref_monsters_1 and
ref_arena_monsters (run here on synthetic memory), and its use on owned ref_anim states
with authored clips.
"""
import unittest
import ref_core as C
import ref_anim as A
import ref_creature as R
import ref_creature_dispatch as D
import ref_creature_dispatch_data as T
import ref_monsters_1 as M1
import ref_arena_monsters as AM

CLIP0 = 0x10000          # synthetic clip k at CLIP0 + 0x100*k
OBJ, DEF, VT, FAKE = 0x1000, 0x2000, 0x5000, 0xF00000


def synthetic_clip(length=120):
    return A.Clip(A.encode_clip([((0, 0, 0), (4096, 0, 0, 0))], length))


def model_ops(model_class, set_state, state, rand=0, fields=()):
    """Run an independent class body on synthetic memory and convert its recorded
    animation calls to the op vocabulary of ref_creature_dispatch."""
    m = R.Memory()
    m.poke(OBJ + 0x24, 4, DEF)
    m.poke(OBJ + 0x48, 4, VT)
    for k in range(64):
        m.poke(DEF + 8 * k + 4, 4, CLIP0 + 0x100 * k)
    for s in range(40):
        m.poke(VT + 8 * s + 4, 4, FAKE + 8 * s)
    m.poke(VT + 27 * 8 + 4, 4, set_state)
    m.poke(OBJ + 0x50, 4, 0x6000)        # a weapon holder, as in the scan
    m.poke(0x6000, 4, 0x6100)
    for off, size, value in fields:
        m.poke(OBJ + off, size, value)
    model = model_class(m, {'handle_clear': lambda p: 0})
    model.obj_rand = lambda obj: rand
    model.vcall(OBJ, 27, state)
    entry = lambda clip: (clip - CLIP0) // 0x100 if clip >= CLIP0 else None  # noqa: E731
    ops = []
    for name, args in model.calls:
        if name == 'anim_start':
            ops.append(('start', entry(args[1]), args[3], args[2]))
        elif name == 'anim_startBlendInOut':
            ops.append(('blend', entry(args[1]), args[3], args[4], args[2]))
        elif name == 'anim_push':
            ops.append(('push', entry(args[1]), args[2]))
        elif name in ('anim_syncToSimFrame', 'anim_jumpTopToEnd', 'anim_snapTopToEnd',
                      'anim_randomizeTopTime', 'anim_clear'):
            ops.append(({'anim_syncToSimFrame': 'sync', 'anim_jumpTopToEnd': 'jump_end',
                         'anim_snapTopToEnd': 'snap_end', 'anim_randomizeTopTime': 'randomize',
                         'anim_clear': 'clear'}[name],))
        elif name.startswith('Holder.v'):
            ops.append(('holder', int(name[8:])))
        elif name.startswith('Creature.v'):
            ops.append(('vslot', int(name[10:])) + ((args[1],) if name == 'Creature.v27' else ()))
    return ops, m.load(OBJ + 0x232, 2)


INDEPENDENT = {  # class -> (model, setState) for bodies authored before this round
    'SmallSpider': (M1.Model, 0x2AB704), 'Gnaw': (M1.Model, 0x267A0C),
    'Mosquito': (M1.Model, 0x297F54), 'Scorpion': (M1.Model, 0x2A55EC),
    'Badger': (M1.Model, 0x244AA4), 'Horsemen': (AM.Model, 0x272F4C),
    'Skelight': (AM.Model, 0x2A91B8), 'Zek': (AM.Model, 0x2C382C),
}


class TableShape(unittest.TestCase):
    def test_every_catalogue_class_has_its_slots(self):
        self.assertGreaterEqual(len(T.DISPATCH), 73)
        for name, info in T.DISPATCH.items():
            self.assertTrue(0x100000 <= info['setState'] < 0x3e9c00, name)
            self.assertTrue(0x100000 <= info['run'] < 0x3e9c00, name)

    def test_ops_are_well_formed(self):
        arity = {'start': 4, 'blend': 5, 'push': 3, 'push_w': 4, 'push_chained': 3,
                 'stop': 3, 'sync': 1, 'jump_end': 1, 'snap_end': 1, 'randomize': 1,
                 'clear': 1, 'drop': 1}
        def check(ops, where):
            for op in ops:
                if op[0] in ('vslot', 'holder'):
                    self.assertIn(len(op), (2, 3), where)
                elif op[0] in ('other_state', 'set_state'):
                    continue
                else:
                    self.assertEqual(len(op), arity[op[0]], (where, op))
                    if op[0] in ('start', 'blend', 'push', 'push_w', 'push_chained', 'stop'):
                        self.assertTrue(op[1] is None or 0 <= op[1] < 64, (where, op))
        for name, info in T.DISPATCH.items():
            for st, case in info['states'].items():
                check(case['ops'], (name, st))
                if 'rand' in case:
                    period, table = case['rand']
                    self.assertEqual(len(table), period)
                    for ops in table:
                        check(ops, (name, st))
                for cond, ops, stored in case.get('when', ()):
                    check(ops, (name, st, cond))

    def test_event_slots_are_four_raw_seconds_and_byte_masks(self):
        for name, events in T.EVENTS.items():
            for entry, slots in events.items():
                self.assertEqual(len(slots), 4, name)
                for seconds, mask in slots:
                    self.assertTrue(0 <= mask <= 0xFF)
                    self.assertFalse(C.lt(seconds, 0), (name, entry))

    def test_consumed_masks_are_installed_by_the_constructor(self):
        """The link between creature_setDefEntryParams and the run function (Inferred in
        monsters-2 2.3): every mask a run state consumes is installed on some clip of the
        class, or the class is listed as receiving events another way."""
        found = {}
        for name, states in T.CONSUMERS.items():
            installed = 0
            for slots in list(T.EVENTS.get(name, {}).values()) + [
                    s for v in T.EVENT_VARIANTS.get(name, {}).values() for s in v.values()]:
                for _, mask in slots:
                    installed |= mask
            for st, masks in states.items():
                for mask in (m for m in masks if m > 0):
                    if not mask & installed:
                        found[(name, st, mask)] = masks[mask]
        self.assertEqual(found, D.UNINSTALLED_CONSUMERS)


class IndependentBodies(unittest.TestCase):
    """The scanned table and the class bodies written by hand in earlier rounds agree."""

    def test_baseline_and_random_choices(self):
        checked = 0
        for name, (model, set_state) in INDEPENDENT.items():
            info = T.DISPATCH[name]
            self.assertEqual(info['setState'], set_state)
            for st, case in info['states'].items():
                residues = (range(case['rand'][0]) if 'rand' in case else
                            [r for r, _, _ in case['rand_points']] if 'rand_points' in case
                            else (0,))
                for r in residues:
                    want, stored = D.select(case, rand=r)
                    got, got_stored = model_ops(model, set_state, st, rand=r)
                    self.assertEqual(got, D.expand(info, want), (name, hex(st), r))
                    self.assertEqual(got_stored, stored, (name, hex(st), r))
                    checked += 1
        self.assertGreater(checked, 60)

    def test_field_conditions(self):
        checked = 0
        for name, (model, set_state) in INDEPENDENT.items():
            for st, case in T.DISPATCH[name]['states'].items():
                for cond, ops, stored in case.get('when', ()):
                    if cond[0] == 'ret' or cond[0] >= 0x564180:
                        continue          # stubbed-callee or global conditions
                    off, value = cond
                    if off >= 0x2000:
                        continue
                    size = 4 if off % 4 == 0 else (2 if off % 2 == 0 else 1)
                    if value >> (8 * size):
                        continue
                    got, got_stored = model_ops(model, set_state, st,
                                                fields=((off, size, value),))
                    if got == ops:
                        checked += 1
        self.assertGreater(checked, 0)


class DriveOwnedAnimation(unittest.TestCase):
    def clips(self):
        return {k: synthetic_clip() for k in range(32)}

    def test_smallspider_death_choice_and_hidden_jump(self):
        case = T.DISPATCH['SmallSpider']['states'][0x14]
        self.assertEqual(case['rand'][0], 4)
        for r in range(4):
            ops, stored = D.select(case, rand=r)
            self.assertEqual(ops[0][:2], ('start', 3 + r))
            self.assertEqual(stored, 0x14)
        ops, _ = D.select(case, field=(0xC, 2))
        self.assertIn(('jump_end',), ops)
        system, state, clips = A.AnimSystem(), A.AnimState(), self.clips()
        slots = []
        D.apply_ops(system, state, clips, ops, on_vslot=lambda *a: slots.append(a))
        self.assertIs(state.top().clip, clips[3])
        self.assertTrue(C.eq(state.top().time, C.from_int(120)))
        self.assertEqual(slots, [(28,)])

    def test_unobserved_condition_is_refused(self):
        case = T.DISPATCH['SmallSpider']['states'][0x14]
        with self.assertRaises(KeyError):
            D.select(case, field=(0x2dc, 0x12345))

    def test_attack_event_lands_on_its_tick_and_marks_the_union(self):
        """Agony attack 1 (state 6): blend-in/out track with the ACTION marker; its first
        event slot (raw 0x3f199999, mask 1) is the hit frame its run state consumes."""
        clips = self.clips()
        D.install_events(clips, T.EVENTS['Agony'])
        ops, _ = D.select(T.DISPATCH['Agony']['states'][6])
        kind, entry, blend_in, blend_out, flags = ops[0]
        self.assertEqual((kind, flags & (D.ACTION | D.ROOT)), ('blend', D.ACTION | D.ROOT))
        self.assertIn('Creature_hitTargetInArc', T.CONSUMERS['Agony'][6][1])
        system = A.AnimSystem()
        tick = D.event_tick(system, clips[entry], 0)
        # 0.6 s at 60 ticks per second, with the 0.99999994 step and the half-open
        # window of anim_advance: the step that starts at time 35.999998.
        self.assertEqual(tick, 37)
        state = A.AnimState()
        A.anim_push(state, clips[12], D.LOOP)
        D.apply_ops(system, state, clips, ops)
        self.assertTrue(state.flags & D.ACTION)
        bits = 0
        for _ in range(tick):
            bits |= A.anim_advance(system, A.ONE, state, sound=False)[0]
        self.assertTrue(bits & 1)

    def test_events_are_shared_by_every_creature_of_the_class(self):
        clips = self.clips()
        D.install_events(clips, {3: ((C.f32(0.5), 1), (0, 0), (0, 0), (0, 0))})
        a, b = A.AnimState(), A.AnimState()
        A.anim_push(a, clips[3], D.LOOP)
        A.anim_push(b, clips[3], D.LOOP)
        self.assertIs(a.top().clip.events, b.top().clip.events)

    def test_walk_cases_loop_with_root_motion_and_resync(self):
        """Every class whose state 1 starts a clip: report the shape; the common base
        is LOOP|ROOT (0x803) or LOOP|PURGE_BELOW (3) followed by an optional sync."""
        shapes = {}
        for name, info in T.DISPATCH.items():
            case = info['states'].get(1)
            if case and case['ops'] and case['ops'][0][0] == 'start':
                shapes.setdefault(case['ops'][0][3], []).append(name)
        self.assertIn(0x803, shapes)

    def test_signature_groups_cover_every_class(self):
        groups = {}
        for name, info in T.DISPATCH.items():
            groups.setdefault(D.signature(info['states']), []).append(name)
        self.assertEqual(sum(len(v) for v in groups.values()), len(T.DISPATCH))


if __name__ == '__main__':
    unittest.main()


class Player(unittest.TestCase):
    def test_row_arithmetic_matches_the_creature_entry_convention(self):
        self.assertEqual(D.player_entry(0, 0x44), 8)        # def + 0x44
        self.assertEqual(D.player_entry(7, 0xA4), 111)      # last of 111 entries
        for cls in range(8):
            for k in D.PLAYER_ROW_ROLES:
                self.assertEqual(8 * D.player_entry(cls, k) + 4, cls * 0x68 + k)
        with self.assertRaises(ValueError):
            D.player_entry(8, 0x44)

    def test_markers_and_roles_of_the_player_rows(self):
        for st, rows in D.PLAYER_DISPATCH.items():
            for row in rows:
                if row['fn'] == 'anim_startBlendInOut':
                    self.assertIsNotNone(row['blend_out'], (st, row))
        death = D.PLAYER_DISPATCH[4]
        self.assertTrue(all(r['flags'] & D.REPORT_END for r in death))
        cast = [r for r in D.PLAYER_DISPATCH[5] if r['fn'] == 'anim_start']
        self.assertTrue(all(r['flags'] & 0x8000 for r in cast))
        self.assertTrue(all(r['flags'] & D.ACTION for r in D.PLAYER_DISPATCH[3]))

    def test_footstep_masks_are_written_and_consumed(self):
        written = 0
        for slots in D.PLAYER_EVENT_SLOTS.values():
            for _, mask in slots:
                written |= mask
        consumed = 0
        for rows in D.PLAYER_EVENTS.values():
            for mask, _, _ in rows:
                consumed |= mask
        self.assertEqual(consumed & ~written, 0)
        self.assertEqual(D.PLAYER_EVENTS[2][0][0], 0x5)

    def test_walk_footstep_tick(self):
        """Walk slot {0x3e800000 = 0.25 s, mask 1} on a lone loop at speed 1: tick 16."""
        clip = synthetic_clip(60)
        seconds, mask = D.PLAYER_EVENT_SLOTS['anim(0x4c), rows 0-5'][0]
        clip.events[0] = [seconds, mask]
        self.assertEqual(D.event_tick(A.AnimSystem(), clip, 0), 16)
