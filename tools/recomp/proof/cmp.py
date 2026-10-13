#!/usr/bin/env python3
"""cmp.py - tools/recomp/rigcompare.py in a directory of its own.

rigcompare.py keeps its logs, memory card and replay file in one fixed directory, so two
comparisons cannot run side by side and a second one overwrites the first.  This wrapper
runs the same code with another output directory, another native binary and extra watch
columns:

  python3 tools/recomp/proof/cmp.py NAME [--native BIN] [--watch W]... [--chunks LO:HI:STEP]...
          <rigcompare command> [its options]

  NAME          the run; everything goes to local/recomp-out/proof/cmp/NAME/
  --native BIN  the translated game to run (default: rigcompare's)
  --watch W     one more column on both machines, name=expr:type (repeatable)
  --chunks LO:HI:STEP[:PREFIX]
                checksum columns over LO..HI in pieces of STEP bytes (hex), to find where
                a block differs (repeatable)
  --native-arg A
                one more argument for the translated game (repeatable), for instance
                --native-arg --opt --native-arg proof-hits=FILE

The controller replay file rigcompare.py writes gets one addition here (last_tick_fix:
the bytes of the tick that ended each level).  The workaround of round 1 for the first
tick of a level (removing a level's loading rows from the file) is gone: rt/iop.cpp
hands over the next tick's first row itself while a loading screen is up (since
2026-10-12 23:41; checked on the three sessions that had needed it, s2, s3 and h6).

Nothing here is game data; what the runs write is, and stays under local/.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import rigcompare                               # noqa: E402

ROOT = rigcompare.ROOT
BASE = os.path.join(ROOT, 'local', 'recomp-out', 'proof', 'cmp')


def last_tick_fix(path):
    """Add, to a controller replay file, the bytes of the tick that ended each level.

    The rig's tick log has one row per displayed frame, written at the head of the frame:
    the row of tick T carries the controller bytes the game read while it computed tick T.
    The frame that begins with the row of a level's last tick T computes tick T+1, and when
    that tick asks for a level change (the player uses a door: Player_interact on a button
    edge, script built-in newWorld) the next row belongs to the new level - there is no row
    of tick T+1, so the replay has nothing for the blank before it and the translation
    falls back on its own script's timing, which puts the same press one frame later: it
    then stays one tick longer in the old level (docs/issues/native-proof.md, NP14).  The
    bytes are in the log all the same: nothing reads the controller between that tick and
    the first frame of the load, so the first row of the next episode still shows them."""
    rows = [line.split() for line in open(path)]
    rows = [r for r in rows if len(r) == 4]
    first, last, have = {}, {}, set()
    for r in rows:
        episode, tick, frame = int(r[0]), int(r[1]), int(r[2])
        first.setdefault(episode, r[3])
        last[episode] = max(last.get(episode, 0), tick)
        have.add((episode, tick))
    added = 0
    with open(path, 'a') as sink:
        for episode in sorted(last):
            if episode + 1 in first and (episode, last[episode] + 1) not in have:
                sink.write('%d %d 0 %s\n' % (episode, last[episode] + 1, first[episode + 1]))
                added += 1
    return added


def setup(name, native=None, watches=(), chunks=(), native_args=(), fix_last_tick=True):
    """Point rigcompare at its own directory; returns the directory."""
    out = os.path.join(BASE, name)
    os.makedirs(out, exist_ok=True)
    rigcompare.OUT = out
    if native:
        rigcompare.NATIVE = native
        os.environ['RTA_NATIVE'] = native
    os.environ.setdefault('RTA_NICE', '19')
    extra = list(watches)
    for spec in chunks:
        parts = spec.split(':')
        lo, hi, step = (int(x, 16) for x in parts[:3])
        prefix = parts[3] if len(parts) > 3 else 'c'
        for at in range(lo, hi, step):
            extra.append('%s%06x=0x%x:crc%d' % (prefix, at, at, min(step, hi - at)))
    if native_args or fix_last_tick:
        real_run = subprocess.run

        def run(command, *args, **kwargs):
            if len(command) > 1 and str(command[1]).endswith('native.py'):
                for item in command:
                    if str(item).startswith('pad-replay='):
                        if fix_last_tick:
                            last_tick_fix(str(item)[len('pad-replay='):])
                command = list(command) + list(native_args)
            return real_run(command, *args, **kwargs)
        subprocess.run = run
    original = rigcompare.base_watches
    rigcompare.base_watches = lambda: original() + extra
    return out


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 2
    name, argv = argv[0], argv[1:]
    native, watches, chunks, native_args = None, [], [], []
    while argv and argv[0] in ('--native', '--watch', '--chunks', '--native-arg'):
        if argv[0] == '--native':
            native = os.path.abspath(argv[1])
        elif argv[0] == '--watch':
            watches.append(argv[1])
        elif argv[0] == '--native-arg':
            native_args.append(argv[1])
        else:
            chunks.append(argv[1])
        argv = argv[2:]
    setup(name, native, watches, chunks, native_args)
    sys.argv = [rigcompare.__file__] + argv
    return rigcompare.main()


if __name__ == '__main__':
    sys.exit(main())
