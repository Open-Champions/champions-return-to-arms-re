#!/usr/bin/env python3
"""Wrapper around the rta_rig runner (see README.md in this directory).

It saves typing: it finds the runner and the disc image, loads every symbol file of the
repository (names.tsv, symbols/*.tsv) so that names can be used in watches and break
points, keeps the emulator's data under local/rig-out/, and offers a few presets. Every
other argument is passed to the runner unchanged.

    python3 -I -B tools/rig/rig.py --frames 600 --watch g_randSeed:x32
    python3 -I -B tools/rig/rig.py --screen-text --script my.rig
    python3 -I -B tools/rig/rig.py watches g_randSeed:x32 g_drawFrame:u32
                                       prints name=address:type pairs for the runner

Environment:
    RTA_DISC   path of the disc image (or pass --disc)
    RTA_RIG    path of the rta_rig executable (default local/rig-build/rta_rig)

Standard library only. No game data is read or written by this file.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Text drawing entry points (symbols/engine.tsv). All take the 16-bit string in $a2.
TEXT_HOOKS = ("text_drawWideImpl", "text_drawWrapped", "text_drawWrappedCentered")


def symbol_files():
    files = [os.path.join(ROOT, "names.tsv")]
    files += sorted(glob.glob(os.path.join(ROOT, "symbols", "*.tsv")))
    return [f for f in files if os.path.exists(f)]


def load_symbols():
    table = {}
    for path in symbol_files():
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 2 or line.startswith("#"):
                    continue
                try:
                    address = int(fields[0], 16)
                except ValueError:
                    continue
                table.setdefault(fields[1], address)
    return table


def watch_pairs(specs):
    """'name:type' -> 'name=0xaddress:type' using the repository's symbol files."""
    table = load_symbols()
    pairs = []
    for spec in specs:
        name, _, kind = spec.partition(":")
        if name not in table:
            raise SystemExit("unknown symbol: %s" % name)
        pairs.append("%s=0x%x:%s" % (name, table[name], kind or "x32"))
    return pairs


def main(argv):
    if argv and argv[0] == "watches":
        print(" ".join("--watch " + pair for pair in watch_pairs(argv[1:])))
        return 0

    runner = os.environ.get("RTA_RIG", os.path.join(ROOT, "local", "rig-build", "rta_rig"))
    if not os.path.exists(runner):
        raise SystemExit("runner not built: %s (see tools/rig/README.md)" % runner)

    out_dir = os.path.join(ROOT, "local", "rig-out")
    os.makedirs(out_dir, exist_ok=True)

    command = [runner]
    passed = list(argv)
    if "--disc" not in passed:
        disc = os.environ.get("RTA_DISC")
        if not disc:
            raise SystemExit("set RTA_DISC to the disc image, or pass --disc")
        command += ["--disc", disc]
    if "--data" not in passed:
        command += ["--data", os.path.join(out_dir, "playdata")]
    for path in symbol_files():
        command += ["--sym", path]

    if "--screen-text" in passed:
        passed.remove("--screen-text")
        for name in TEXT_HOOKS:
            command += ["--break", "%s,wstr=a2,collect" % name]

    command += passed
    os.execv(runner, command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
