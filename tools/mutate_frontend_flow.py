#!/usr/bin/env python3
"""Mutation controls for tools/difftest_frontend_flow.py.

Usage: python3 tools/mutate_frontend_flow.py <SLUS_209.73> [seed]

Each control changes one reference value / rule, or NOPs one store in the
executable image loaded by the emulator, then runs the check that should
catch it.  Every control must fail with an AssertionError; a control that
passes is reported as SURVIVED and the script exits 1.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import difftest_frontend_flow as D  # noqa: E402
import ref_frontend_flow as R      # noqa: E402

if len(sys.argv) not in (2, 3):
    raise SystemExit(__doc__)
PATH = sys.argv[1]
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else R.SEEDS[0]
with open(PATH, 'rb') as source:
    if hashlib.sha256(source.read()).hexdigest() != D.SHA256:
        raise SystemExit('REFUSED mutation controls: executable SHA-256 does not match US v2.00')
NOP = 0


def per_slot(mask, row0_kind=0):
    return (row0_kind,) + tuple(0 if mask >> s & 1 else 5 for s in range(1, 4))


def latch_from_zero(mask, row0_kind=0):
    kinds, latched = [row0_kind], not mask & 1
    for s in range(1, 4):
        latched = latched or not mask >> s & 1
        kinds.append(5 if latched else 0)
    return tuple(kinds)


def held_input(pads, accept_mask=R.ACCEPT_MASK, cancel_mask=R.CANCEL_MASK):
    words = [p[0] | p[1] | p[2] for p in pads[:1]]
    return any(w & accept_mask for w in words), any(w & cancel_mask for w in words)


def warn_any_accept(alpha, step, accept):
    alpha = min(alpha + step, R.WARN_ALPHA_MAX)
    if alpha <= 0:
        return 0, 0, step
    return 1, alpha, R.WARN_STEP_CLOSE if accept else step


def max_diff_swapped(word):
    return 4 if word & 0x40 else ORIG['max_difficulty'](word)


def hub_no_first(decided, side, complete):
    return bool(side and complete)


def hub_const_difficulty(decided, side, difficulty):
    return ORIG['hub_predicate_calls'](decided, side, 1)


def hub_no_short_circuit(decided, side, difficulty):
    return [(R.HUB_DECIDED, None), (R.HUB_SIDE, None), (R.HUB_COMPLETE, (difficulty, 1))]


ORIG = {name: getattr(R, name) for name in dir(R) if not name.startswith('_')}

CHECKS = {
    'start': lambda: D.check_start(PATH, SEED),
    'accepts': lambda: D.check_accepts(PATH, SEED),
    'input': lambda: D.check_input_rule(PATH, SEED),
    'maxdiff': lambda: D.check_max_difficulty(PATH, SEED),
    'select': lambda: D.check_select_entry(PATH, SEED),
    'finish': lambda: D.check_finish(PATH, SEED),
    'load': lambda: D.check_load(PATH, SEED),
    'stats': lambda: D.check_stats(PATH, SEED),
    'pool': lambda: D.check_point_pool(PATH, SEED),
    'name': lambda: D.check_name(PATH, SEED),
    'name_phase': lambda: D.check_name_phase(PATH, SEED),
    'entry_site': lambda: D.check_level_entry_site(PATH),
}

# (label, check, reference overrides, executable store sites to NOP)
CONTROLS = (
    ('stat maximum 99', 'stats', {'STAT_MAX': 99}, ()),
    ('name limit 29', 'name', {'NAME_MAX': 29}, ()),
    ('point pool 19', 'pool', {'STAT_POINTS': 19}, ()),
    ('kill limits (5, 10, 20)', 'accepts', {'KILL_LIMITS': (5, 10, 20)}, ()),
    ('players rule per slot (own controller)', 'accepts', {'players_row_kinds_present': per_slot}, ()),
    ('players latch reads slot 0', 'accepts', {'players_row_kinds_present': latch_from_zero}, ()),
    ('menu input from held|pressed|repeat', 'input', {'menu_input': held_input}, ()),
    ('menu scans pads 0 and 1', 'input', {'MENU_PADS_SCANNED': 2}, ()),
    ('0x1ec448 bit 0x40 -> 4', 'maxdiff', {'max_difficulty': max_diff_swapped}, ()),
    ('hub2 without the decision predicate', 'finish', {'hub_is_second': hub_no_first}, ()),
    ('mission_isComplete with constant difficulty 1', 'finish', {'hub_predicate_calls': hub_const_difficulty}, ()),
    ('hub predicates not short-circuited', 'finish', {'hub_predicate_calls': hub_no_short_circuit}, ()),
    ('appearance bytes in order +0x21..+0x24', 'pool', {'APPEARANCE_ROW_BYTES': (0x21, 0x22, 0x23, 0x24)}, ()),
    ('appearance source not indexed by carousel', 'pool', {'appearance_source': lambda i, c: R.APPEARANCE_VALUES + i * 0x10 + 3}, ()),
    ('warning accept flips at any alpha', 'stats', {'stat_warning_frame': warn_any_accept}, ()),
    ('next-player step 8', 'name_phase', {'NEXT_PLAYER_STEP': 8}, ()),
    ('level-entry callee 0x2247f0', 'entry_site', {'PLAYER_SEL_APPLY_PENDING': 0x2247F0}, ()),
    ('NOP first-entry store 0x1e1f84', 'start', {}, (0x1E1F84,)),
    ('NOP theme-requested store 0x1e1f7c', 'start', {}, (0x1E1F7C,)),
    ('NOP player-count store 0x1e1f78', 'start', {}, (0x1E1F78,)),
    ('NOP players re-enable store 0x1e0f74', 'accepts', {}, (0x1E0F74,)),
    ('NOP difficulty-accept clear 0x1e1acc', 'accepts', {}, (0x1E1ACC,)),
    ('NOP difficulty-accept clear 0x1e1ad4', 'accepts', {}, (0x1E1AD4,)),
    ('NOP select-entry clear 0x1e3bec', 'select', {}, (0x1E3BEC,)),
    ('NOP select-entry clear 0x1e3bf0', 'select', {}, (0x1E3BF0,)),
)

real_emulator = D.emulator
survived = 0
print('mutation controls, seed %d' % SEED)
for label, check, overrides, nops in CONTROLS:
    for name, value in overrides.items():
        setattr(R, name, value)
    if nops:
        def patched(path, seed, _nops=nops):
            e = real_emulator(path, seed)
            for site in _nops:
                e.mem.w32(site, NOP)
            return e
        D.emulator = patched
    try:
        CHECKS[check]()
    except AssertionError as exc:
        where = exc.__traceback__
        while where.tb_next:
            where = where.tb_next
        print('FAILED as expected: %-48s %-10s line %d: %s' % (
            label, check, where.tb_lineno, str(exc)[:110]))
    else:
        survived += 1
        print('SURVIVED: %s (%s)' % (label, check))
    finally:
        for name in overrides:
            setattr(R, name, ORIG[name])
        D.emulator = real_emulator
# unmodified run of the same checks must pass
for check in sorted(set(c for _, c, _, _ in CONTROLS)):
    CHECKS[check]()
print('unmutated checks pass')
print('%d controls, %d survived' % (len(CONTROLS), survived))
sys.exit(1 if survived else 0)
