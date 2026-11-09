#!/usr/bin/env python3
"""Mutation controls for tools/difftest_combat_r6.py.

Each control swaps one probe-side oracle (a constant or a method of the probe, never the
guest) and runs the section that uses it on seed 20973. Every control must make that
section fail. The first lines name the probe file by its sha256, so a log ties to one
probe. Run with unittest imported first and PYTHONDONTWRITEBYTECODE=1:

    python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); \
sys.argv=["tools/mutate_combat_r6.py"]; runpy.run_path(sys.argv[0], run_name="__main__")'

Exit 0 when every control was rejected, 1 otherwise, 2 when the private input is missing.
"""
import datetime
import hashlib
from pathlib import Path
import sys
import unittest  # noqa: F401 - preload before tools/ is on the path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import difftest_combat as DC
import difftest_combat_r6 as T

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / 'local/SLUS_209.73'
SEED = 20973
VICTIM = (10.0, 20.0)


def attr(owner, name, value):
    old = getattr(owner, name)
    setattr(owner, name, value)
    return lambda: setattr(owner, name, old)


def run(label, section, patch):
    undo = patch()
    probe = T.Probe(ELF)
    try:
        section(probe)
    except Exception as exc:  # a crash also rejects the mutation; it is counted
        probe.failures['raised.' + type(exc).__name__] += 1
    finally:
        undo()
    bad = sum(probe.failures.values())
    print('%-30s %s  failures %d' % (label, 'REJECTED' if bad else 'NOT REJECTED', bad))
    return bool(bad)


def controls():
    direction = T.Probe.direction
    threshold = T.Probe.stagger_threshold
    award = T.Probe.award_oracle
    added = T.block_added
    return [
        ('direction+1', lambda p: p.hit_direction(SEED),
         lambda: attr(T.Probe, 'direction', lambda self, v, a: (direction(self, v, a) + 1) & 0xFFFF)),
        ('stagger_limit-1', lambda p: p.stagger(SEED),
         lambda: attr(T.Probe, 'stagger_threshold',
                      lambda self, r: ((threshold(self, r)[0] or 1) - 1, threshold(self, r)[1]))),
        ('stagger_constant', lambda p: p.stagger(SEED), lambda: attr(T, 'K_STAGGER', 0x3D4CCCCD)),
        ('award_killer_swapped', lambda p: p.kill_credit(SEED),
         lambda: attr(T.Probe, 'award_oracle',
                      lambda self, e, l, a, k: award(self, e, l, a, (1 - k) if k >= 0 else k))),
        ('award_no_dead_half', lambda p: p.kill_credit(SEED),
         lambda: attr(T.Probe, 'award_oracle',
                      lambda self, e, l, a, k: award(self, e, l, [True] * len(a), k))),
        ('sink_step', lambda p: p.despawn(SEED), lambda: attr(T, 'K_SINK', 0x3EB33334)),
        ('knock_speed', lambda p: p.hit_direction(SEED), lambda: attr(T, 'SENTINEL', 0x3F800001)),
        ('aim_offset', lambda p: p.cast_bodies(SEED), lambda: attr(T, 'K_AIM', 0x41C3)),
        # Added in the fix round: the skill 0x3e roll, the block rules, the death path.
        ('knock_chance_4_per_rank', lambda p: p.knock_down(SEED), lambda: attr(T, 'KNOCK_PER_RANK', 4)),
        ('knock_roll_mod_101', lambda p: p.knock_down(SEED), lambda: attr(T, 'KNOCK_MOD', 101)),
        ('reaction_one_draw', lambda p: p.knock_down(SEED), lambda: attr(T, 'REACTION_DRAWS', 1)),
        ('block_lowers_at_0x6001', lambda p: p.knock_down(SEED), lambda: attr(T, 'BLOCK_REL', 0x6001)),
        ('block_front_adds_all', lambda p: p.player_block(SEED, VICTIM),
         lambda: attr(T, 'block_added', lambda state, behind, flags, amount=T.PLAIN:
                      amount if not flags & 0x20000 else added(state, behind, flags, amount))),
        ('block_state_b_half_ignored', lambda p: p.player_block(SEED, VICTIM),
         lambda: attr(T, 'block_added', lambda state, behind, flags, amount=T.PLAIN:
                      0 if state == 0xB and not behind else added(state, behind, flags, amount))),
        ('death_flag_before_state', lambda p: p.death_path(SEED),
         lambda: attr(T, 'DEATH_ORDER', ('loot', 'slot28', 'flag', 'state', 'award'))),
        ('death_slot28_before_loot', lambda p: p.death_path(SEED),
         lambda: attr(T, 'DEATH_ORDER', ('slot28', 'loot', 'state', 'flag', 'award'))),
        ('death_award_before_loot', lambda p: p.death_path(SEED),
         lambda: attr(T, 'DEATH_ORDER', ('award', 'loot', 'slot28', 'state', 'flag'))),
        ('death_state_before_loot', lambda p: p.death_path(SEED),
         lambda: attr(T, 'DEATH_ORDER', ('state', 'flag', 'loot', 'slot28', 'award'))),
        ('dead_flag_pc_0x111e08', lambda p: p.death_path(SEED), lambda: attr(T, 'DEAD_FLAG_PC', 0x111E08)),
        ('award_sites_swapped', lambda p: p.kill_credit(SEED),
         lambda: attr(T, 'AWARD_SITES', {1: 0x1120E4, 2: 0x1121E8})),
    ]


def main():
    digest = hashlib.sha256(ELF.read_bytes()).hexdigest() if ELF.is_file() else ''
    if digest != DC.EXPECTED_SHA256:
        print('BLOCKED: private input missing or unexpected; 0 controls')
        return 2
    probe_file = Path(T.__file__).resolve()
    print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    print('probe tools/%s sha256 %s' % (probe_file.name, hashlib.sha256(probe_file.read_bytes()).hexdigest()))
    print('controls tools/%s sha256 %s' % (Path(__file__).name,
                                           hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    missed = [label for label, section, patch in controls() if not run(label, section, patch)]
    print('controls %d, not rejected: %d %s' % (len(controls()), len(missed), ' '.join(missed)))
    return 1 if missed else 0


if __name__ == '__main__':
    sys.exit(main())
