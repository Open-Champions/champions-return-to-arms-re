#!/usr/bin/env python3
"""Controls for tools/difftest_player_anim_states.py: change the reference one item at a
time; each change must make the difftest part it belongs to fail.

  python3 tools/mutate_player_anim_states.py /path/to/SLUS_209.73 --seed N

Prints one REJECTED/SURVIVED line per mutation and exits 1 if any survived.  The
reference module is restored before every mutation.  Run it the same way as the
difftest (tools/dis.py shadows the standard library's dis; preload unittest)."""
import argparse
import contextlib
import io
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                   # noqa: E402
import ref_player_anim_states as M                     # noqa: E402
import difftest_player_anim_states as D                # noqa: E402

ORIG = {k: getattr(M, k) for k in dir(M) if not k.startswith('__')}


def rounding_weight(blend, s, knee_bits):
    """run_weight with IEEE double rounding instead of the game's truncation."""
    f = lambda r: struct.unpack('<f', struct.pack('<I', r))[0]          # noqa: E731
    k = struct.unpack('<d', struct.pack('<Q', knee_bits))[0]
    return struct.unpack('<I', struct.pack('<f', (f(blend) * (f(s) - k)) * 3.0))[0]


MUTATIONS = [
    ('L', 'ramp 0.1 + 1 ulp', lambda: setattr(M, 'K_RAMP', 0x3DCCCCCD)),
    ('L', 'run event threshold 0.6 -> 0.5', lambda: setattr(M, 'K_RUN_EVENT', 0x3F000000)),
    ('L', 'IEEE rounding instead of truncation', lambda: setattr(M, 'run_weight', rounding_weight)),
    ('L', 'acceleration 0.05 -> 0.1', lambda: setattr(M, 'K_REST', 0x3DCCCCCC)),
    ('R', 'root y sign', lambda: setattr(M, 'root_to_world',
                                         lambda f, rx, ry: ORIG['root_to_world'](f, rx, ry ^ 0x80000000))),
    ('R', 'slow ignored', lambda: setattr(M, 'anim_step_speed',
                                          lambda sp, sl, d=None: ORIG['anim_step_speed'](sp, 0, d))),
    ('R', 'Drowsy fraction ignored', lambda: setattr(M, 'anim_step_speed',
                                                     lambda sp, sl, d=None: ORIG['anim_step_speed'](sp, sl))),
    ('H', 'suffix boundary', lambda: setattr(M, 'knockdown_name', lambda c, r: ORIG['knockdown_name'](c, r + 1))),
    ('H', 'class 3 prefix', lambda: setattr(M, 'knockdown_name',
                                            lambda c, r: ORIG['knockdown_name'](2 if c == 2 else 0, r))),
    ('H', 'death models', lambda: setattr(M, 'death_offset', lambda m, c: 0x14 if c == 2 else 0x0C)),
    ('H', 'reaction flags', lambda: setattr(M, 'FLAGS_REACTION', 0x80A)),
    ('H', 'fade rate -1/10', lambda: setattr(M, 'FADE_RATE', 0xBDCCCCCD)),
    ('M', 'hit frame 15.0', lambda: setattr(M, 'K_HIT', 0x41700000)),
    ('M', 'combo window -1 frame', lambda: setattr(M, 'K_WINDOW', 0x41A828F5)),
    ('M', 'swing life 1.5 s', lambda: setattr(M, 'K_SWING_LIFE', 0x3FC00000)),
    ('M', 'lunge 0.5 s', lambda: setattr(M, 'K_LUNGE', 0x3F000000)),
    ('M', 'stick end 38', lambda: setattr(M, 'K_STICK_FRAMES', 0x42180000)),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('elf')
    parser.add_argument('--seed', type=int, default=20973)
    args = parser.parse_args()
    C.set_fpu('ps2')
    parts = {'L': D.part_locomotion, 'R': D.part_root, 'M': D.part_melee,
             'H': lambda elf, rng: D.part_hits(elf, rng, args.seed)}
    rejected = 0
    for part, label, apply in MUTATIONS:
        for key, value in ORIG.items():
            setattr(M, key, value)
        apply()
        D.FAILS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            parts[part](args.elf, random.Random(args.seed))
        failed = bool(D.FAILS)
        rejected += failed
        print('%s %s: %s (%d failing checks)' % ('REJECTED' if failed else 'SURVIVED', part, label,
                                                 len(D.FAILS)))
        sys.stdout.flush()
    for key, value in ORIG.items():
        setattr(M, key, value)
    print('seed=%d: %d of %d mutations rejected' % (args.seed, rejected, len(MUTATIONS)))
    return 0 if rejected == len(MUTATIONS) else 1


if __name__ == '__main__':
    raise SystemExit(main())
