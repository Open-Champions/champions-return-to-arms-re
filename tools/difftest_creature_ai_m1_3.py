#!/usr/bin/env python3
"""Mission 1-3 creature AI decision difftests, SLUS_209.73 US v2.00.

    PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_creature_ai_m1_3.py \\
        local/SLUS_209.73 --seed 20973 [--levels local/levels] [-k Kobold]

Executed: each class run function (and GameObject_rand 0x1509d0) runs in
ee_emu on a synthetic object. Every other callee is a recording stub; the
queries listed in creature_ai_rig.QUERY_DOMAIN are answered from an answer
list, and the probe walks every answer path depth-first. The emitted events
(query arguments, slot-27 requests, hit-helper arguments, movement calls)
and the final own-generator state are compared with ref_creature_ai_m1_3.
The hit helpers 0x119938 / 0x1196e8 / 0x119b58 are then executed with sight
and damage_apply stubbed to record what reaches damage_apply 0x1e8230.
With --levels, object records are counted and the original factory 0x159c94
selects each creature constructor (allocation and constructors stubbed).
Nothing here loads a level, runs an animation or moves a live actor.
"""
import sys
from pathlib import Path

# tools/dis.py shadows the standard dis module; load what argparse needs
# from the standard library before the tools directory is searched.
_SAVED = sys.path[:]
sys.path[:] = [p for p in _SAVED if not Path(p or ".", "ee_emu.py").exists()]
import argparse  # noqa: E402
import inspect  # noqa: E402,F401
try:
    import _colorize  # noqa: E402,F401
except ImportError:
    pass
sys.path[:] = _SAVED
import hashlib
import os
import random
from collections import Counter

from creature_ai_rig import NAMES, QUERY_DOMAIN, Rig, f
from ee_emu import EE, float_to_raw
import ref_creature_ai_m1_3 as R
import models_creature_ai_m1_3 as MODELS

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
HEAD = ("processDamage", "baseRun", "updateActive")
KEEP = set(QUERY_DOMAIN) | {
    "set", "turn", "moveToTarget", "moveToDest", "flee", "deadUpdate", "moveTo",
    "objDelete", "poolNew", "pickTarget", "pickAlly", "dropLoot", "lootGenerate",
    "damageInRadius", "hitInArc", "hitAll", "hitAtReach", "stepAnim", "knockback",
    "getGuardPoint", "angleAllyToTarget", "revive", "leadTargetPoint",
    "processDamage", "baseRun", "updateActive", "fleeFrom", "pickWanderDest",
    "clearPath", "aimAngleAt", "addSpell", "findSpellByType"}
NAMES.setdefault(0x10BFC8, "revive")
NAMES.setdefault(0x11A710, "findSpellByType")


def s16(value):
    return ((value & 0xFFFF) ^ 0x8000) - 0x8000


def key(rig, call):
    n = rig.name(call)
    a = [x & 0xFFFFFFFF for x in call.args]
    fa = call.fargs
    if n == "set":
        return ("set", a[1] & 0xFFFF)
    if n == "see":
        return ("see", f(fa[0]), f(fa[1]), s16(a[1]), a[2] & 0xFFFF, a[3])
    if n == "cone":
        return ("cone", f(fa[0]), f(fa[1]), s16(a[1]), a[2] & 0xFFFF)
    if n in ("sight", "pickTarget"):
        return (n, a[1])
    if n in ("hitInArc", "hitAll"):
        return (n, f(fa[0]), f(fa[1]), s16(a[1]), a[2] & 0xFFFF,
                s16(a[3]), s16(a[4]), s16(a[5]), a[6])
    if n == "hitAtReach":
        return (n, f(fa[0]), s16(a[1]), s16(a[2]), s16(a[3]), a[4])
    if n in ("deadUpdate", "stepAnim", "knockback", "alliesNearTarget"):
        return (n, f(fa[0]))
    return (n,)


def kept(name):
    return name in KEEP or name.startswith("skill+")


def events(rig, calls):
    return [key(rig, c) for c in calls if kept(rig.name(c))]


def domain(name):
    values = QUERY_DOMAIN[name]
    return (0, 1) if values == "ptr" else values


def walk(executable, name, ctx, model, limit=4000):
    """Every answer path of one synthetic tick; returns the path count."""
    cls = R.CLASSES[name]
    stack, paths = [()], 0
    while stack:
        prefix = stack.pop()
        rig = Rig(executable, cls, ctx["state"], ctx["seed"], target=ctx["target"],
                  ev=ctx["ev"], anim=ctx["anim"], clock=ctx["clock"],
                  deadline=ctx["deadline"], ally=ctx["ally"],
                  fields=ctx["raw_fields"], answers=prefix)
        for offset, value in ctx["holder"].items():
            rig.entry_returns("holder", offset, value)
        for offset, value in zip((0xD0, 0xD2, 0xD4), R.DMG):
            rig.emu.mem.w16(rig.obj + offset, value)
        if ctx.get("hp") is not None:
            rig.emu.mem.wf32(rig.obj + 0x228, ctx["hp"])
        calls = rig.run()
        used = [prefix[i] if i < len(prefix) else 0 for i in range(len(rig.asked))]
        got = events(rig, calls)
        m = R.M(ctx, used)
        model(m)
        want = m.events
        seed = rig.emu.mem.u32(rig.obj + 0x44)
        if got != want or seed != m.rng.state:
            same = 0
            while same < min(len(got), len(want)) and got[same] == want[same]:
                same += 1
            if not os.environ.get("AI_FULL"):
                got, want = got[same:], want[same:]
            raise AssertionError("%s %s answers=%s\n emu  =%s\n model=%s\n seed emu %08x model %08x"
                                 % (name, {k: v for k, v in ctx.items() if k not in ("raw_fields", "fields")}
                       | {"fields": {hex(k): v for k, v in ctx["fields"].items()}},
                                    used, got, want, seed, m.rng.state))
        paths += 1
        assert paths <= limit, (name, ctx)
        for j in range(len(prefix), len(used)):
            for alt in domain(rig.asked[j]):
                if alt != 0:
                    stack.append(tuple(used[:j]) + (alt,))
    return paths


def contexts(name, spec, seed):
    rng = random.Random("%s:%d" % (name, seed))
    for variant in spec.get("variants", ({},)):
        for state in spec["states"]:
            grid = [(t, ev, anim, dl, al)
                    for t in (1, 0) for ev in spec.get("evs", (0, 1, 2))
                    for anim in spec.get("anims", (0, 8, 0x10, 0x80))
                    for dl in spec.get("deadlines", (50, 150))
                    for al in spec.get("allies", (0,))]
            picks = [grid[0]] + rng.sample(grid[1:], min(spec.get("sample", 10), len(grid) - 1))
            for t, ev, anim, dl, al in picks:
                fields = {k: v for k, v in variant.items() if k != "holder"}
                raw = tuple((size, off, val) for off, (size, val) in fields.items())
                yield dict(state=state, target=t, ev=ev, anim=anim, clock=100,
                           deadline=dl, ally=al, seed=rng.getrandbits(32),
                           fields={off: val for off, (size, val) in fields.items()},
                           raw_fields=raw, hp=spec.get("hp"),
                           holder=variant.get("holder", {}))


def check_class(executable, name, seed, keep_going=False):
    spec = MODELS.SPECS[name]
    count = paths = 0
    failed = set()
    for ctx in contexts(name, spec, seed):
        tag = (tuple(sorted(ctx["fields"].items())), tuple(sorted(ctx["holder"].items())),
               ctx["state"])
        if tag in failed:
            continue
        try:
            paths += walk(executable, name, ctx, spec["model"])
        except AssertionError as exc:
            if not keep_going:
                raise
            failed.add(tag)
            if len(failed) <= 4:
                print("FAIL", exc)
        count += 1
    assert not failed, "%d failing variant/state pairs" % len(failed)
    return count, paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("--seed", type=int, default=20973)
    parser.add_argument("--levels")
    parser.add_argument("-k", action="append")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    data = Path(args.executable).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256, "unexpected executable"
    total = 0
    bad = []
    for name in MODELS.SPECS:
        if args.k and name not in args.k:
            continue
        try:
            cases, paths = check_class(args.executable, name, args.seed, args.keep_going)
        except AssertionError as exc:
            if not args.keep_going:
                raise
            print("FAIL %s: %s" % (name, str(exc).splitlines()[0]))
            bad.append(name)
            continue
        print("PASS %-12s %4d contexts %6d answer paths" % (name, cases, paths))
        total += paths
    assert not bad, "failing classes: %s" % bad
    print("PASS all classes, %d answer paths, seed %d" % (total, args.seed))


if __name__ == "__main__":
    sys.exit(main())
