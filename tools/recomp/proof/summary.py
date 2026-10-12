#!/usr/bin/env python3
"""summary.py - a session's comparison in one line per level.

  python3 tools/recomp/proof/summary.py NAME [NAME ...]

Reads local/recomp-out/proof/cmp/NAME/result.txt (session.py NAME compare) and prints,
per level episode, the ticks compared and the columns that differ with the number of
ticks each differs at.  Columns that are not expected to agree are left out: the displayed
frame counter and the rig's marker (frame timing), and the cosmetic seed, the controller
checksum, the sound-slot checksum and the equipment-cache checksum (each follows its
machine's own sound, controller or disc timing; docs/issues/native-proof.md, part 1).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TIMING = ('draw', 'net', 'cosmetic', 'pads', 'padraw', 'sseq', 'eqcache')


def main():
    total_ticks = clean_ticks = 0
    for name in sys.argv[1:]:
        path = os.path.join(ROOT, 'local', 'recomp-out', 'proof', 'cmp', name, 'result.txt')
        level, ticks, rows = None, 0, []
        out = []

        def flush():
            if level is not None:
                out.append((level, ticks, list(rows)))

        for line in open(path):
            m = re.match(r"episode (\d+), level '([^']*)'", line)
            if m:
                flush()
                level, ticks, rows = m.group(2) or '(start-up)', 0, []
                continue
            m = re.match(r'\s+ticks compared: (\d+)', line)
            if m:
                ticks = int(m.group(1))
            m = re.match(r'\s+(DIFFERENT|different \(timing\)) (\S+)\s+first at tick (\d+).*; (\d+) of (\d+) ticks differ \(last at (\d+)\)', line)
            if m and m.group(2) not in TIMING:
                rows.append('%s %s@%s-%s' % (m.group(2), m.group(4), m.group(3), m.group(6)))
            if 'NOT COMPARABLE' in line:
                rows.append('NOT COMPARABLE')
        flush()
        print('%s:' % name)
        for level, ticks, rows in out:
            total_ticks += ticks
            if not rows:
                clean_ticks += ticks
            print('  %-10s %5d ticks  %s' % (level, ticks, '; '.join(rows) if rows else 'identical'))
    print('%d ticks compared; %d of them in levels where every simulation column is identical at every tick' % (total_ticks, clean_ticks))
    return 0


if __name__ == '__main__':
    sys.exit(main())
