"""Creature animation dispatch contract, SLUS-20973 v2.00 (round 3).

See docs/spec/creature-animation-dispatch.md.  Extends ref_creature_animation (round 2)
without changing it.  Round 4 leaves `select` and these rows alone: player states
6, 7, 9 and 0xe are `ref_skill_anim`, and two fields set together are
`ref_field_precedence`.  The per-class numbers live in ref_creature_dispatch_data, which
`tools/scan_anim_dispatch.py --emit` regenerates from the user's own executable; every
row is an Executed single-function result (stubbed callees), not a run of the game.

Vocabulary
----------
op       one call a setState case makes on the creature's animation state (+0x114) or
         its virtual table, in call order:
           ('start', entry, blend, flags)            anim_start 0x16cfe0
           ('blend', entry, blend_in, blend_out, flags)  anim_startBlendInOut 0x16ceb0
           ('push', entry, flags)                    anim_push 0x170838
           ('push_w', entry, flags, (w, dw, l, dl))  anim_pushWithWeights 0x1708c0
           ('push_chained', entry, flags)            anim_pushChained 0x170938
           ('stop', entry, blend)                    anim_stop 0x16d1a0
           ('sync',)  ('jump_end',)  ('snap_end',)  ('randomize',)  ('clear',)  ('drop',)
           ('vslot', n) / ('vslot', 27, state)       virtual call through +0x48
           ('holder', n)                             weapon holder (+0x50) slot n
         `entry` is the class-definition resource index k (pointer at def + 8k + 4); None
         means the case passed a clip that is not a definition entry (for example one
         chosen at run time).  Raw32 patterns, not floats, for every time.
case     DISPATCH[class]['states'][s] (else the class's 'default', see case_for):
         {'ops': [...], 'stored': s, 'rand': (period, [ops per residue]) or None,
          'rand_stored': [stored per residue] when the draw also picks the state,
          'rand_points': [(residue, ops, stored)] when no period up to 12 fits,
          'when': [((field, value) or ('ret', v), ops, stored), ...]}
         `stored` is the u16 written to +0x232 for the request; `rand` gives the clip
         choice as a function of GameObject_rand 0x1509d0 residue (draws in call order:
         only the draw that picks the clip varies the ops); `when` are conditions found by
         setting one read field at a time on a zero creature (offsets from the creature,
         or absolute global addresses) or by letting every stubbed callee return v.
events   {entry: ((seconds raw32, mask), x4)}: creature_setDefEntryParams 0x118378 calls
         of the constructor, i.e. the four mutable event slots of a SHARED clip.
consumers {state: {mask: (function names...)}}: calls of the run function (slot 4)
         and 'store +off:size=value' writes to the creature that appear only when
         Creature_stepAnim 0x1162b0 returns that mask.  Mask 0: the same under every
         mask (any nonzero event word); mask -1: callees handed the event word itself.
"""
import ref_anim as A
import ref_creature_animation as V

# Track flag bits (docs/spec/animation.md 2.1) and the class-marker bits the run
# functions test in the state's flag union (+0x11a): 0x8 "action clip playing",
# 0x10 "hit reaction playing" (Inferred from every test read; see the doc, 2.3).
LOOP, PURGE_BELOW, REPORT_END, ACTION, HIT = 0x1, 0x2, 0x4, 0x8, 0x10
ROOT, YAW = 0x800, 0x4000
STATUS_ENDED = 0x80

# Consumers whose mask no constructor of the class installs (Executed scan, section
# 4.4 of the doc): reachable only if some other writer puts that mask on the clip.
UNINSTALLED_CONSUMERS = {('SpiderQueen', 0x14, 0x8): ('camera_shake',)}


def clip_for(memory, creature, entry):
    """Resolve a definition entry exactly as the setState bodies do: re-read +0x24."""
    return V.class_resource(memory, creature, entry)


def case_for(info, state):
    """The recorded case of a DISPATCH entry, or its switch default (state numbers
    without a case label).  The default's 'stored' is 'same' when the number itself is
    stored, else the stored value; returned with that resolved."""
    case = info['states'].get(state)
    if case is not None:
        return case
    d = info['default']
    return {'ops': d['ops'], 'stored': state if d['stored'] == 'same' else d['stored']}


def select(case, rand=0, field=None, ret=None):
    """Ops for one request.  rand: the residue source of the clip-choosing draw.
    field: (offset-or-global-address, value) set on an otherwise zero creature; ret: the
    value every stubbed callee returns.  Only recorded conditions are known; anything
    else raises (do not invent a rule)."""
    if field is not None or ret is not None:
        key = field if field is not None else ('ret', ret)
        for cond, ops, stored in case.get('when', ()):
            if tuple(cond) == tuple(key):
                return ops, stored
        if field is not None and field[1] == 0:
            return select(case, rand)
        raise KeyError('condition %r was not observed for this case' % (key,))
    if case.get('rand'):
        period, table = case['rand']
        stored = case.get('rand_stored')
        return table[rand % period], stored[rand % period] if stored else case['stored']
    if case.get('rand_points'):
        for r, ops, stored in case['rand_points']:
            if r == rand:
                return ops, stored
        raise KeyError('residue %d was not executed; the choice is not periodic' % rand)
    return case['ops'], case['stored']


def apply_ops(system, state, clips, ops, on_vslot=None):
    """Drive an owned ref_anim.AnimState with the recorded ops (clips: entry -> Clip).
    Virtual-slot ops go to on_vslot(slot, *args); they are never animation calls."""
    for op in ops:
        kind = op[0]
        if kind == 'start':
            A.anim_start(op[2], state, clips[op[1]], op[3])
        elif kind == 'blend':
            A.anim_start_blend_in_out(op[2], op[3], state, clips[op[1]], op[4])
        elif kind == 'push':
            A.anim_push(state, clips[op[1]], op[2])
        elif kind == 'push_w':
            A.anim_push_with_weights(state, clips[op[1]], op[2], *op[3])
        elif kind == 'push_chained':
            A.anim_push_chained(state, clips[op[1]], op[2])
        elif kind == 'stop':
            A.anim_stop(op[2], state, clips[op[1]])
        elif kind == 'sync':
            A.anim_sync_to_sim_frame(system, state)
        elif kind == 'jump_end':
            A.anim_jump_top_to_end(system, state)
        elif kind == 'snap_end':
            A.anim_snap_top_to_end(state)
        elif kind == 'randomize':
            A.anim_randomize_top_time(system, state)
        elif kind == 'clear':
            A.anim_clear(state)
        elif kind == 'drop':
            A.anim_drop_non_persistent(state)
        elif kind in ('vslot', 'holder'):
            if on_vslot is not None:
                on_vslot(*op[1:]) if kind == 'vslot' else on_vslot('holder', *op[1:])
        else:
            raise ValueError('unknown op %r' % (op,))


def install_events(clips, events):
    """The constructor's event writes, as data on shared clips: slot i of entry k gets
    (seconds, mask).  Masks are bytes; anim_advance ORs them sign-extended."""
    for entry, slots in events.items():
        clip = clips.get(entry)
        if clip is None:
            continue
        for i, (seconds, mask) in enumerate(slots):
            clip.events[i] = [seconds, mask & 0xFF]


def event_tick(system, clip, slot, speed=A.ONE, limit=100000):
    """Simulation tick (1-based step count) on which a lone LOOP track of `clip`, started
    at time 0, first reports event slot `slot`; ref_anim.anim_advance is the authority
    (test of the slot time against [time/60, (time+step)/60) before the time moves)."""
    state = A.AnimState()
    A.anim_push(state, clip, LOOP)
    mask = clip.events[slot][1]
    for tick in range(1, limit + 1):
        bits = A.anim_advance(system, speed, state, sound=False)[0]
        if bits & mask:
            return tick
    return None


def signature(states):
    """Dispatch shape of a class: per state, the op kinds with flags but not entries.
    Classes with equal signatures share one dispatch base in the doc's grouping."""
    out = []
    for s in sorted(states):
        case = states[s]
        shape = tuple((op[0],) + tuple(op[-1:] if op[0] in ('start', 'blend', 'push')
                                      else ()) for op in case['ops'])
        out.append((s, shape))
    return tuple(out)


# ---- the common dispatch base ---------------------------------------------------------
# Role of a setState case from what it starts (Inferred from the flags; the doc's
# section 3 gives the evidence per role).  The common base is the role every state
# number plays in most classes; deviations() lists where a class differs.
def role(ops):
    """'idle' | 'locomotion' | 'action' | 'hit' | 'death' | 'oneshot' | 'none'."""
    starts = [op for op in ops if op[0] in ('start', 'blend', 'push', 'push_w')]
    if not starts:
        return 'none'
    flags = starts[-1][-1] if starts[-1][0] != 'push_w' else starts[-1][2]
    if any(op == ('vslot', 28) for op in ops) and flags & REPORT_END:
        return 'death'
    if flags & HIT:
        return 'hit'
    if flags & ACTION:
        return 'action'
    if flags & LOOP:
        return 'locomotion' if flags & ROOT else 'idle'
    return 'oneshot'


BASE_ROLES = {0: 'idle', 1: 'locomotion', 3: 'locomotion', 5: 'idle', 0x10: 'locomotion',
              0x12: 'hit', 0x13: 'idle', 0x14: 'death'}


def deviations(states):
    """{state: (base role, this class's role)} for the base states that differ, plus the
    class's own states (6 and up, other than the base ones) as (None, role)."""
    out = {}
    for st, want in BASE_ROLES.items():
        case = states.get(st)
        got = role(case['ops']) if case else 'none'
        if got != want:
            out[st] = (want, got)
    for st, case in states.items():
        if st not in BASE_ROLES:
            out[st] = (None, role(case['ops']))
    return out


def alternatives(case):
    """Every recorded op list of a case: baseline, random residues, conditions."""
    out = [case['ops']]
    if case.get('rand'):
        out += case['rand'][1]
    out += [ops for _, ops, _ in case.get('rand_points', ())]
    out += [ops for _, ops, _ in case.get('when', ())]
    return out


def state_role(info, state):
    """Role of a state number; a case whose baseline starts nothing takes the role of
    its first alternative that does, marked with a trailing '?' (conditional)."""
    case = case_for(info, state)
    got = role(case['ops'])
    if got == 'none':
        for ops in alternatives(case)[1:]:
            if role(ops) != 'none':
                return role(ops) + '?'
    return got


def group_of(info):
    """Dispatch group of a DISPATCH entry (doc section 5):
    'none'     no setState case starts a clip (base slot 27 or no animation work)
    'root'     common base with root-motion locomotion (state 1 LOOP|ROOT)
    'steered'  common base whose walk/run loops carry no ROOT (moved by steering)
    'special'  a state machine of its own (idle, walk or death outside the base)"""
    cases = list(info['states'].values()) + [info['default']]
    if all(role(ops) == 'none' for c in cases for ops in alternatives(c)):
        return 'none'
    r0, r1, r14 = (state_role(info, s).rstrip('?') for s in (0, 1, 0x14))
    if r0 == 'idle' and r14 == 'death':
        if r1 == 'locomotion':
            return 'root'
        if r1 == 'idle':
            return 'steered'
    return 'special'


def base_deviations(info):
    """{state: role} for the base states whose role differs from BASE_ROLES, after
    the group's own locomotion convention ('steered' walks are 'idle' by flags)."""
    group = group_of(info)
    out = {}
    for st, want in BASE_ROLES.items():
        if group == 'steered' and want == 'locomotion':
            want = 'idle'
        got = state_role(info, st)
        if got.rstrip('?') != want:
            out[st] = got
    return out


def expand(info, ops, depth=0):
    """Inline ('vslot', 27, s): a setState that re-dispatches runs the class's own case
    s (baseline ops) at that point, filter included (not modelled here).  The outer
    case's store of +0x232 still comes last."""
    out = []
    for op in ops:
        if op[0] == 'vslot' and op[1] == 27 and len(op) == 3 and depth < 4:
            out += expand(info, case_for(info, op[2])['ops'], depth + 1)
        else:
            out.append(op)
    return out


# ---- player (docs/spec/player-animation-dispatch.md) ----------------------------------
# anim(k) of the player code is *(def + weaponClass*0x68 + k), def = *(P+0x24), one of
# twelve 111-entry definitions (0x4ef330 by model index).  In this module's entry
# convention (pointer at def + 8e + 4) that is entry (cls*0x68 + k - 4) / 8.
PLAYER_ROW_ROLES = {0x44: 'idle', 0x4c: 'walk', 0x54: 'run layer 1', 0x5c: 'run layer 2',
                    0x64: 'heavy attack', 0x6c: 'cast', 0x74: 'attack 1 / shot',
                    0x7c: 'hit reaction', 0x84: 'block', 0x8c: 'block reaction B',
                    0x94: 'block reaction A', 0x9c: 'block pose', 0xa4: 'block move / evade'}
PLAYER_WEAPON_CLASSES = {0: 'ohw_', 1: 'dhs_', 2: 'dha_', 3: 'l_', 4: 'b_', 5: 'nw_',
                         6: 'ohw_ row with throw', 7: 'dw_'}


def player_entry(weapon_class, k):
    """Definition entry of anim(k) for weapon class 0..7 (k 0x44..0xa4, step 8)."""
    if not 0 <= weapon_class <= 7 or k not in PLAYER_ROW_ROLES:
        raise ValueError('weapon class 0..7 and a row offset 0x44..0xa4 required')
    return (weapon_class * 0x68 + k - 4) // 8


# Rows below: Observed by reading (addresses in 'evidence'), from the player document.
PF01, PF02, PF03, PF05 = 0x3dcccccc, 0x3e4ccccc, 0x3e999999, 0x3f000000
PLAYER_DISPATCH = {
    0: [dict(k=0x74, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x12,
             when='enter state 0 from state 2 (weapon class 4 or 6)', evidence='0x1a7f7c'),
        dict(k=0x44, fn='anim_start', blend_in=PF03, blend_out=None, flags=0x3,
             when='Player slot 27 arg 0 (def+0x24 instead when level flag 0x10000000)', evidence='0x1b5e24')],
    1: [dict(k=0x74, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x802,
             when='first swing from state 2', evidence='0x1a7fb8'),
        dict(k=0x64, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x812,
             when='heavy attack, older id 0x25', evidence='0x1a7308'),
        dict(k='b_attackb.anm', fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x802,
             when='class 4 close target', evidence='0x1a79fc'),
        dict(k='nw_atakseq3.anm', fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x802,
             when='class 6 close target', evidence='0x1a7a48'),
        dict(k='<prefix>_atakseq%d.anm (+0x461)', fn='anim_start', blend_in=PF01, blend_out=None, flags=0x802,
             when='combo step after Player_pickAttackAnim', evidence='0x1aae5c'),
        dict(k='b_attackb / nw_atakseq3', fn='anim_start', blend_in=PF01, blend_out=None, flags=0x802,
             when='combo step, class 4/6, after 39.6 frames with a target', evidence='0x1aaf00'),
        dict(k=0x4c, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x3,
             when='Player slot 27 arg 1, unless already state 1', evidence='0x1b5e78')],
    2: [dict(k=(0x44, 0x4c, 0x54, 0x5c), fn='direct_store', blend_in=None, blend_out=None, flags=0x1205,
             when='player_resetIdleAnim: cells 0..3, weights 1,0,0,0', evidence='0x1b2470'),
        dict(k='<prefix>_idled.anm', fn='anim_start', blend_in=PF05, blend_out=None, flags=0x1,
             when='Player_idleFidget: 4 tracks, shared draw < 0xe2, no fidget', evidence='0x1bc508')],
    3: [dict(k=0x7c, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0xa,
             when='small knock (level<2, or level-1<2 blocking a |rel|>=0x6000 hit)', evidence='0x1b317c'),
        dict(k='knockdown{1,2}_{a,b,c,d}.anm', fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x80a,
             when='large knock not resisted, not already playing', evidence='0x1b30bc'),
        dict(k=0x7c, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0xa,
             when='flinch roll on damage', evidence='0x1b38d0')],
    4: [dict(k='def+0x14', fn='anim_start', blend_in=PF05, blend_out=None, flags=0x206,
             when='death, model not 2/3/6/7 and class 2', evidence='0x1b34c0'),
        dict(k='def+0xc', fn='anim_start', blend_in=PF05, blend_out=None, flags=0x206,
             when='death otherwise', evidence='0x1b34e0')],
    5: [dict(k=0x6c, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x8003,
             when='Skill-object cast phase 0, no 0x8000 track, skill kind != 6', evidence='0x1ab784'),
        dict(k=0x6c, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x8003,
             when='older record kind 1, phase 0', evidence='0x1aba80'),
        dict(k=0x6c, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x8003,
             when='older record kind 2, phase 0', evidence='0x1abca0'),
        dict(k=0x6c, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x8022,
             when='older record kind 0, phase 0', evidence='0x1abf8c')],
    8: [dict(k=0x9c, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x2801,
             when='no blockgo track', evidence='0x1a61b4'),
        dict(k=0x84, fn='anim_start', blend_in=PF01, blend_out=None, flags=0x803,
             when='block held and (+0x47f==0 or neither evade nor block playing)', evidence='0x1a6244'),
        dict(k=0x94, fn='anim_startBlendInOut', blend_in=PF02, blend_out=PF02, flags=0x812,
             when='Player_takeDamage in state 8, shared draw <= 0xafc7', evidence='0x1b5508'),
        dict(k=0x8c, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0x812,
             when='Player_takeDamage in state 8, shared draw > 0xafc7', evidence='0x1b5538')],
    10: [dict(k='dha_quake.anm', fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0xa,
              when='older id 0xc', evidence='0x1a7448'),
         dict(k='dha_quake.anm', fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF01, flags=0xa,
              when='SkillGroundPound_cast, writes the 4 event slots', evidence='0x2c72a8')],
    0xb: [dict(k=0xa4, fn='anim_startBlendInOut', blend_in=PF01, blend_out=PF03, flags=0x808,
               when='Player_tryBlockMove: swap pressed while blocking', evidence='0x1bf218')],
    0xc: [dict(k='<prefix>_warcry.anm (class 4/6: unwritten buffer)', fn='anim_startBlendInOut',
               blend_in=PF01, blend_out=PF01, flags=0x22, when='older id 0xe, P+0x374 == 0', evidence='0x1a71b4')],
    0xd: [dict(k='nw_seated.anm or nw_idlea.anm', fn='anim_start', blend_in=PF01, blend_out=None, flags=0x3,
               when='no nw_seated track, level name != bronzeht', evidence='0x1a5f78')],
}
PLAYER_EVENTS = {
    2: [(0x5, 'Player_footstep (move(0) returns bit 4 when s >= 0.6, bit 1 below)', 'evidence 0x1b48f8')],
    0xb: [(0x5, 'Player_footstep', 'evidence 0x1a6588')],
    'scripted_1': [(0x1, 'Player_footstep, then Creature_moveToDest', 'evidence 0x1a55a4')],
    10: [(0x1, 'player_voice 10 + sound spel_bw_pound.anm; area damage at facing-0x4000 (real only)', 'evidence 0x1a6824'),
         (0x2, 'area damage ahead, 24 units (real only)', 'evidence 0x1a6818'),
         (0x4, 'area damage at facing+0x4000 (real only)', 'evidence 0x1a6818'),
         (0x8, 'GroundPoundEffect, rank of skill 0x26 (real only)', 'evidence 0x1a69bc')],
}
PLAYER_EVENT_SLOTS = {   # written by code; {seconds raw, mask}
    'anim(0x4c), rows 0-5': [(0x3e800000, 1), (0x3f400000, 1)],          # 0x1a2388
    'anim(0x5c), rows 0-5': [(0x3ee66666, 4), (0x3f733333, 4)],          # 0x1a2388
    'anim(0xa4), rows 0-5': [(0x3e800000, 1), (0x3f400000, 1)],          # 0x1a2388
    'dha_quake.anm': [(0x3e800000, 1), (0x3f000000, 2), (0x3f400000, 4), (0x3fbd2e2f, 8)],  # 0x2c723c
}
