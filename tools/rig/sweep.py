#!/usr/bin/env python3
"""One pair per skill: both players the same class, the skill at rank 10 on the first
ability button, seeded random movement, attacks and ability presses under a bus delay.

    sweep.py --trees FILE.json --states-prefix local/rig-out/run6- --out DIR [--jobs 5]
             [--frames 3500] [--only CLASS]

FILE.json maps class number to {"active": [skill ids], "passive": [...]} (read from the
executable's skill-tree tables); the states for class c are <prefix><model>/a.zip, b.zip,
booted with both lobby models set to that class's model (see docs/issues/live-rig.md,
section 11). All fix sections (fuzz.FIXES) are applied on both machines. A pair that
differs is run again, and once more with the prediction copy switched off. Writes
OUT/sweep.tsv and prints the pairs that differ. Standard library only.
"""
import concurrent.futures
import json
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import fuzz  # noqa: E402

MODEL = {0: 0, 1: 4, 2: 8, 3: 2, 4: 6, 5: 10, 6: 11}
NO_COPY = "Arena diagnostic: no prediction copy"


def build(skill):
    """Script lines: both records get level 25, statistics, and the one skill (None: passives)."""
    lines = []
    for n in (0, 1):
        rec = lambda off: "g_players+%d+0x%x" % (n * 0x4C30, off)
        put = lambda off, kind, value: lines.append("ontick 680 poke %s:%s %s" % (rec(off), kind, value))
        for off in (0x58, 0x59):
            put(off, "s8", 25)
        for off, value in ((0x78, 200), (0x7C, 300), (0x80, 150), (0x84, 250), (0x90, 200), (0x94, 300), (0x98, 150), (0x9C, 250)):
            put(off, "s32", value)
        for off in (0xB0, 0xAC, 0xC4, 0xC0):
            put(off, "f32", 900)
        if skill is None:
            put(0xEF, "hex48", "05" * 48)      # every class passive at level 5
        else:
            ranks = ([(60, 1)] if skill != 60 else []) + [(skill, 10)]
            blob = b"".join(struct.pack("<hh", i, r) for i, r in ranks) + struct.pack("<hh", -1, -1)
            put(0x4B08, "hex%d" % len(blob), blob.hex())
            put(0x4440, "str16", "newstyle")
            put(0x4460, "hex6", struct.pack("<hhBB", skill, 0, 1, 0).hex())
            put(0x4A84, "hex2", "0001")
        for tick in range(800, 5000, 150):
            lines.append("ontick %d poke %s:f32 900" % (tick, rec(0xC0)))
    return lines


def casts(directory, letter):
    try:
        text = open(os.path.join(directory, letter + ".out"), errors="replace").read()
        found = re.search(r"Player_castSkill @\w+ hits=(\d+)", text)
        return int(found.group(1)) if found else 0
    except OSError:
        return -1


def one(args):
    config, cls, skill, index = args
    job = {"seed": 700 + index, "level": "strife", "groups": "move,cast,fight",
           "bus": "delay=8" if index % 2 == 0 else "delay=12,jitter=4"}
    local = dict(config, states=config["prefix"] + str(MODEL[cls]), prelude=build(skill), keep=True,
                 out=os.path.join(config["out"], "c%d-%s" % (cls, "passives" if skill is None else skill)))
    result = fuzz.run_pair(local, job, fuzz.FIXES, "")
    row = {"class": cls, "skill": "passives" if skill is None else skill, "ticks": result["ticks"],
           "castsA": casts(result["dir"], "a"), "castsB": casts(result["dir"], "b"), "first": result["first"],
           "what": fuzz.class_of(result) if result["first"] is not None else "", "repeats": "", "nocopy": "",
           "columns": " ".join("%s:%d" % item for item in sorted(result.get("first_by_column", {}).items(), key=lambda i: i[1])[:8])}
    if result["first"] is not None:
        again = fuzz.run_pair(local, job, fuzz.FIXES, "-again")
        row["repeats"] = again.get("first") == result["first"]
        nocopy = fuzz.run_pair(local, job, fuzz.FIXES + [NO_COPY], "-nocopy")
        row["nocopy"] = "in sync" if nocopy.get("first") is None else "differs at %s" % nocopy.get("first")
    shutil.rmtree(local["out"], ignore_errors=True)
    return row


def main(argv):
    opt = lambda name, default=None: argv[argv.index(name) + 1] if name in argv else default
    trees = json.load(open(opt("--trees")))
    config = {"prefix": os.path.abspath(opt("--states-prefix")), "out": os.path.abspath(opt("--out")),
              "frames": int(opt("--frames", "3500")), "start_level": "strife", "warp_tick": 700,
              "cards": os.path.join(ROOT, "local", "rig-out", "pair-"),
              "extra": ["--break", "Player_castSkill,quiet"]}
    only = opt("--only")
    work = []
    for cls in sorted(trees, key=int):
        if only is not None and str(cls) != only:
            continue
        for skill in trees[cls]["active"] + [None]:
            work.append((config, int(cls), skill, len(work)))
    os.makedirs(config["out"], exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(int(opt("--jobs", "5"))) as pool:
        rows = list(pool.map(one, work))
    keys = ["class", "skill", "ticks", "castsA", "castsB", "first", "what", "repeats", "nocopy", "columns"]
    with open(os.path.join(config["out"], "sweep.tsv"), "w") as handle:
        handle.write("\t".join(keys) + "\n")
        for row in rows:
            handle.write("\t".join("" if row[k] is None else str(row[k]) for k in keys) + "\n")
    differ = [r for r in rows if r["first"] is not None]
    print("pairs %d, ticks %d, with casts on both machines %d, differ %d" % (
        len(rows), sum(r["ticks"] for r in rows), sum(1 for r in rows if r["castsA"] > 0 and r["castsB"] > 0), len(differ)))
    for r in differ:
        print("class %s skill %s casts %s/%s first tick %s [%s] repeats=%s without the copy: %s | %s" % (
            r["class"], r["skill"], r["castsA"], r["castsB"], r["first"], r["what"][:40], r["repeats"], r["nocopy"], r["columns"][:90]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
