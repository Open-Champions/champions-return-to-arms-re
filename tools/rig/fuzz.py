#!/usr/bin/env python3
"""Unattended two-machine fuzzing (see README.md, "Fuzzing two machines").

    fuzz.py --states DIR --out DIR [--seeds 100:24] [--frames 6000] [--jobs 4]
            [--levels strife,drunare,hub] [--groups "move,fight;move,fight,dpad,select"]
            [--bus "none;delay=3,jitter=3,loss=50"] [--patches "K1;K2" | --patches none]
            [--try-patches] [--prelude FILE] [--extra "runner options"]

Runs one joined pair (rig.py pair) per seed from the two states DIR/a.zip and DIR/b.zip.
Seed number i takes level i mod L, input mix i mod M and bus setting i mod B from the
lists. A pair whose level is not the states' own is sent there first by writing the
pending level in one lockstep tick on both machines. Each pair plays seeded random input
on both controllers for --frames frames; the two tick logs are compared; a pair that
differs is run once more to see that it repeats, and (with --try-patches) once per
"Net test" section of the patch file to see which section removes the difference.

Divergences are grouped into classes by the shared columns that differ at the first
differing tick (player numbers folded together), so repeats of one cause are counted
once. Only a summary is printed; OUT/summary.tsv has one line per pair, and the logs of
every divergent pair are kept under OUT/<pair>/. Every pair gets fresh copies of the two
memory-card directories. Standard library only.
"""
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import compare  # noqa: E402

PNACH = os.path.join(ROOT, "patches", "SLUS-20973_4028A55F.pnach")
KNOWN = {"K1": "Net test: use button works with the spell selector open",
         "K2": "Net test: potions always leave the bag directly"}
# --patches FIXES: every fix section confirmed or proposed so far (the lag ones other than
# LAG-1 and the sections for menus the developer start cannot reach are left out)
FIXES = ["Net test: " + name for name in (
    "use button works with the spell selector open", "potions always leave the bag directly",
    "stats page does not rewrite stored weapon damage", "menu lockout never drops player damage",
    "menu lockout never blocks weapon swap and use", "closing a notice box does not run the pending script",
    "equalise at once (LAG-1)", "predicted spin cast leaves the shared animation alone",
    "creatures ignore being touched by the prediction copy", "script return keeps the saved stack pointer")]


def option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def patch_sections():
    with open(PNACH, errors="replace") as handle:
        return [line.strip()[1:-1] for line in handle if line.startswith("[")]


def run_pair(config, job, patches, tag, frames=None):
    """One pair. Returns compare.tick_differences() plus 'ok' and 'dir'."""
    name = "%s-s%d%s" % (job["level"], job["seed"], tag)
    out = os.path.join(config["out"], name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for letter in "ab":   # fresh memory cards
        source = config["cards"] + letter
        if os.path.isdir(os.path.join(source, "vfs")):
            shutil.copytree(os.path.join(source, "vfs"), os.path.join(out, "data-" + letter, "vfs"))
    lines = ['pnach %s "%s"' % (PNACH, section) for section in patches]
    if job["level"] != config["start_level"]:
        lines += ["ontick %d poke g_pendingLevel:str16 %s" % (config["warp_tick"], job["level"]),
                  "wait 60",
                  "until g_levelName:str16 == %s timeout 5000" % job["level"],
                  "until g_players+0x43d8:u32 != 0 timeout 5000",
                  "wait 120"]
    lines += config["prelude"]
    lines += ["wait 30", "fuzz %d %d %s" % (job["seed"], config["frames"], job["groups"]), "wait 120"]
    script = os.path.join(out, "script.rig")
    with open(script, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    command = [sys.executable, "-I", "-B", os.path.join(HERE, "rig.py"), "pair", out,
               "--a-load", os.path.join(config["states"], "a.zip"),
               "--b-load", os.path.join(config["states"], "b.zip"), "--script", script]
    bus = job["bus"]
    if bus and bus != "none":
        command += ["--bus", bus + ",seed=%d" % job["seed"]]
    if frames:
        command += ["--frames", str(frames)]
    command += config["extra"]
    env = dict(os.environ, RTA_PAIR_DATA=os.path.join(out, "data-"), RTA_PAIR_TAIL="0")
    with open(os.path.join(out, "pair.txt"), "w") as handle:
        subprocess.call(command, stdout=handle, stderr=subprocess.STDOUT, env=env)
    result = {"ok": False, "dir": out, "ticks": 0, "first": None, "columns_at_first": [], "levels": []}
    try:
        result.update(compare.tick_differences(os.path.join(out, "a.tick.tsv"), os.path.join(out, "b.tick.tsv")))
        result["ok"] = True
    except Exception as error:  # a runner that did not start, a missing log
        result["error"] = str(error)
    for letter in "ab":
        shutil.rmtree(os.path.join(out, "data-" + letter), ignore_errors=True)
    if result["ok"] and result["first"] is None and not config["keep"]:
        shutil.rmtree(out, ignore_errors=True)
    return result


def class_of(result):
    """Columns that differ at the first tick, player numbers folded: the class of a divergence."""
    if result.get("peer_dropped"):
        return "a peer was dropped at that tick (kick or leave): not a desync"
    return "+".join(sorted(set(re.sub(r"^p[0-3]", "pN", c) for c in result["columns_at_first"])))


def main(argv):
    if "--states" not in argv or "--out" not in argv:
        print(__doc__)
        return 2
    start, count = (option(argv, "--seeds", "100:8").split(":") + ["8"])[:2]
    patches = option(argv, "--patches", "K1;K2")
    prelude = option(argv, "--prelude")
    config = {
        "states": os.path.abspath(option(argv, "--states")),
        "out": os.path.abspath(option(argv, "--out")),
        "frames": int(option(argv, "--frames", "6000")),
        "start_level": option(argv, "--start-level", "strife"),
        "warp_tick": int(option(argv, "--warp-tick", "700")),
        "cards": option(argv, "--cards", os.path.join(ROOT, "local", "rig-out", "pair-")),
        "extra": option(argv, "--extra", "").split(),
        "prelude": open(prelude).read().splitlines() if prelude else [],
        "keep": "--keep" in argv,
    }
    base = [] if patches == "none" else list(FIXES) if patches == "FIXES" else [KNOWN.get(p, p) for p in patches.split(";")]
    levels = option(argv, "--levels", "strife").split(",")
    mixes = option(argv, "--groups", "move,rstick,fight,potion,use,dpad,select,start,l3r3").split(";")
    buses = option(argv, "--bus", "none").split(";")
    jobs = [{"seed": int(start) + i, "level": levels[i % len(levels)], "groups": mixes[i % len(mixes)],
             "bus": buses[i % len(buses)]} for i in range(int(count))]
    os.makedirs(config["out"], exist_ok=True)
    workers = int(option(argv, "--jobs", "3"))

    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda job: run_pair(config, job, base, ""), jobs))

    # confirm each divergence by running the pair again (--no-rerun: do not, for runs that
    # write audit or trace files, which a second run would only write again)
    divergent = [(job, result) for job, result in zip(jobs, results) if result["ok"] and result["first"] is not None]
    if "--no-rerun" in argv:
        divergent = []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        again = list(pool.map(lambda item: run_pair(config, item[0], base, "-again"), divergent))
    for (job, result), second in zip(divergent, again):
        result["repeats"] = (second.get("first") == result["first"] and
                             second.get("columns_at_first") == result["columns_at_first"])

    classes = {}
    for job, result in divergent:
        classes.setdefault(class_of(result), []).append((job, result))

    # which patch section removes each class (tried on the class's first pair)
    removed = {}
    if "--try-patches" in argv:
        # The lag sections change when input is sampled, so they can make a timing
        # coincidence go away without touching its cause; they are not tried.
        candidates = [s for s in patch_sections() if s.startswith("Net test") and "LAG" not in s and s not in base]
        for name, members in classes.items():
            job, result = members[0]
            if result.get("peer_dropped"):
                continue
            limit = result["frame_a"] + 400   # frames of this run: past the divergence, no further
            with concurrent.futures.ThreadPoolExecutor(workers) as pool:
                trials = list(pool.map(
                    lambda item: run_pair(config, job, base + [item[1]], "-p%d" % item[0], limit),
                    list(enumerate(candidates))))
            removed[name] = [section for section, trial in zip(candidates, trials)
                             if trial["ok"] and trial["first"] is None and trial["ticks"] > 0]

    with open(os.path.join(config["out"], "summary.tsv"), "w") as handle:
        handle.write("seed\tlevel\tgroups\tbus\tticks\tfirst_tick\tcolumns\tclass\trepeats\tlevels_seen\tfirst_tick_of_each_column\n")
        for job, result in zip(jobs, results):
            handle.write("\t".join(str(v) for v in (
                job["seed"], job["level"], job["groups"], job["bus"], result["ticks"],
                result["first"] if result["first"] is not None else "", ",".join(result["columns_at_first"]),
                class_of(result) if result["first"] is not None else "", result.get("repeats", ""),
                ",".join(result["levels"]),
                " ".join("%s:%d" % item for item in sorted(result.get("first_by_column", {}).items(), key=lambda i: i[1])))) + "\n")

    total = sum(r["ticks"] for r in results)
    failed = [job for job, r in zip(jobs, results) if not r["ok"] or r["ticks"] == 0]
    by_level = {}
    for job, result in zip(jobs, results):
        entry = by_level.setdefault(job["level"], [0, 0, 0])
        entry[0] += 1
        entry[1] += result["ticks"]
        entry[2] += result["first"] is not None
    print("pairs %d, ticks compared %d, divergent %d (%d of them a kick or leave), without a usable log %d; patches on both: %s" % (
        len(jobs), total, len(divergent), sum(1 for _, r in divergent if r.get("peer_dropped")), len(failed),
        "; ".join(base) or "none"))
    print("per level: " + ", ".join("%s %d pairs / %d ticks / %d divergent" % (level, n, t, d)
                                    for level, (n, t, d) in sorted(by_level.items())))
    if failed:
        print("no usable log: " + ", ".join("%s-s%d" % (j["level"], j["seed"]) for j in failed))
    for name, members in sorted(classes.items(), key=lambda item: -len(item[1])):
        print("class [%s]: %d pairs, %d repeated exactly" % (name, len(members), sum(1 for _, r in members if r.get("repeats"))))
        for job, result in members[:4]:
            print("    %s-s%d groups=%s bus=%s first tick %d (frame %d on A)" % (
                job["level"], job["seed"], job["groups"], job["bus"], result["first"], result["frame_a"]))
        if name in removed:
            print("    removed by: " + ("; ".join(removed[name]) or "no single Net test section"))
    return 1 if divergent else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
