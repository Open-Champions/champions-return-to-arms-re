#!/usr/bin/env python3
"""summary.py - a session's comparison, one line per level.

  python3 tools/recomp/proof/summary.py NAME [NAME ...] [--all]

Reads the two tick logs of local/recomp-out/proof/cmp/NAME/ (session.py NAME rig /
native) and compares them as rigcompare.py does: rows matched on level episode and tick.
Per level it prints the ticks compared and, per column that differs, at how many ticks.

Left out unless --all is given, because they are not expected to agree:
  - the displayed-frame counter and the rig's marker (frame timing);
  - the cosmetic seed, the controller checksum and bytes, the sound-slot checksum and the
    equipment-cache checksum: each follows its machine's own sound, controller or disc
    timing (docs/issues/native-proof.md, part 1).
Counted apart: "write rows" - the tick at which a scripted memory write lands, and the one
after it (session.py applies a write in the native run one row after the rig's log first
shows it; a column the write touches differs for that row).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rigcompare                               # noqa: E402

ROOT = rigcompare.ROOT
TIMING = ('draw', 'net', 'cosmetic', 'pads', 'padraw', 'sseq', 'eqcache')


def main():
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    everything = '--all' in sys.argv
    grand = [0, 0, 0]
    for name in names:
        base = os.path.join(ROOT, 'local', 'recomp-out', 'proof', 'cmp', name)
        head, rig = rigcompare.episodes_of(os.path.join(base, 'boot-rig.tsv'))
        head_b, nat = rigcompare.episodes_of(os.path.join(base, 'boot-native.tsv'))
        if head[1:] != head_b[1:]:
            print('%s: the two logs have different columns' % name)
            continue
        writes = {}
        path = os.path.join(base, 'pokes.txt')
        if os.path.exists(path):
            for line in open(path):
                parts = line.split()
                if len(parts) >= 3:
                    writes.setdefault(int(parts[0]), set()).update((int(parts[1]), int(parts[1]) + 1))
        print('%s: %d level episodes on the rig, %d in the native run' % (name, len(rig), len(nat)))
        for number, ((level, rows_a, _), (level_b, rows_b, _)) in enumerate(zip(rig, nat)):
            ticks = [t for t in sorted(rows_a) if t in rows_b and t >= 1]
            if level != level_b or not ticks:
                print('  %-10s NOT COMPARABLE (native: %s; rig ticks to %d, native to %d)' % (
                    level, level_b, max(rows_a), max(rows_b)))
                continue
            marks = writes.get(number, set())
            found, bad_ticks = [], set()
            for column in range(1, len(head)):
                if head[column] in TIMING and not everything:
                    continue
                differ = [t for t in ticks if rows_a[t][1][column] != rows_b[t][1][column]]
                if not differ:
                    continue
                outside = [t for t in differ if t not in marks]
                bad_ticks.update(outside)
                text = head[column] + ' '
                if outside:
                    text += '%d@%d-%d' % (len(outside), outside[0], outside[-1])
                if len(differ) != len(outside):
                    text += '%s(%d write rows)' % (' ' if outside else '', len(differ) - len(outside))
                found.append(text)
            grand[0] += len(ticks)
            grand[1] += len(ticks) - len(bad_ticks)
            grand[2] += max(rows_a) != max(rows_b)
            print('  %-10s %5d ticks (rig to %d, native to %d)  %s' % (level or '(start-up)', len(ticks), max(rows_a), max(rows_b),
                                                              '; '.join(found) if found else 'identical'))
    print('%d ticks compared; at %d of them every column listed above is identical outside write rows' % (grand[0], grand[1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
