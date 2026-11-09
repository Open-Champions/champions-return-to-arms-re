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
from dump_tables import objects_from_file
from ee_emu import EE
import ref_creature_ai_m1_3 as R
import models_creature_ai_m1_3 as MODELS

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
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


COS, SIN = 0x166630, 0x1666E0
FOLLOW_SET = (0x10A9C0, 0x1195E0, 0x1195F0, 0x119608, 0x1509D0)


def set_rig(executable, name, state, seed, clock, target=True, fields=()):
    cls = R.CLASSES[name]
    rig = Rig(executable, cls, state, seed, target=target, clock=clock, fields=fields)
    for address in FOLLOW_SET:
        rig.emu.unhook(address)
    rig.emu.follow = {cls["set"]} | set(FOLLOW_SET)
    rig.emu.reset_log()
    return rig


def written(rig):
    out = {}
    for _pc, address, _size, value in rig.emu.writes:
        out[address - rig.obj] = value
    return out


def check_setstate(executable, seed):
    """Entry timers, last-attack fields, cflag 0x200 and the death calls."""
    rng = random.Random("set:%d" % seed)
    count = 0
    for name, table in MODELS.SET_ENTRY.items():
        cls = R.CLASSES[name]
        for state, entry in table.items():
            for _ in range(3):
                clock = rng.randrange(1000, 5000)
                rig = set_rig(executable, name, 3, rng.getrandbits(32), clock)
                rig.emu.call(cls["set"], rig.obj, state, max_steps=300000)
                land = state if entry["land"] is None else entry["land"]
                got = rig.emu.mem.u16(rig.obj + 0x232)
                assert got == land, (name, state, got, land)
                w = written(rig)
                for offset, want in entry["fields"].items():
                    value = w.get(offset)
                    assert value is not None, (name, state, hex(offset), "not written")
                    if isinstance(want, tuple):
                        if want[0] == "abs":
                            base, mod = want[1], want[2]
                        else:
                            base, mod = clock + want[0], want[1]
                        value = value - (1 << 32) if value & 0x80000000 else value
                        assert base <= value < base + mod, (name, state, hex(offset), value, want)
                    else:
                        assert value == want, (name, state, hex(offset), value, want)
                names = [rig.name(c) for c in rig.emu.calls]
                for wanted in entry["calls"]:
                    assert wanted in names, (name, state, wanted, names)
                count += 1
    return count


def check_filter(executable, seed):
    """Creature_filterState 0x10a9c0 redirects, executed under each class."""
    count = 0
    cases = (  # fields, target, request, landing, field expectations
        (((16, 0x314, 30),), True, 3, 5, {}),
        (((16, 0x314, 30),), False, 3, 0, {}),
        (((16, 0x314, 30),), True, 6, 6, {}),
        (((16, 0x31C, 30),), True, 3, 0x13, {}),
        (((16, 0x318, 30),), True, 3, 0x10, {}),
        (((16, 0x318, 30),), False, 3, 3, {0x318: 0}),
        (((16, 0x318, 30), (16, 0x314, 9), (16, 0x31C, 9)), True, 0x14, 0x14,
         {0x318: 0, 0x314: 0, 0x31C: 0}),
    )
    rng = random.Random("filter:%d" % seed)
    for name, cls in R.CLASSES.items():
        for fields, target, request, land, writes in cases:
            rig = set_rig(executable, name, 1, rng.getrandbits(32), 1000,
                          target=target, fields=fields)
            rig.emu.call(cls["set"], rig.obj, request, max_steps=300000)
            got = rig.emu.mem.u16(rig.obj + 0x232)
            if name == "Droid" and land == 6:
                land = 0        # Droid_setState has no case 6 and stores 0
            assert got == land, (name, fields, target, request, got, land)
            w = written(rig)
            for offset, value in writes.items():
                assert w.get(offset) == value, (name, hex(offset), w.get(offset))
            count += 1
    return count


def check_slots(executable, seed):
    """Which function each run reaches through slots 23/24/25 (vtable words)."""
    count = 0
    for name, cls in R.CLASSES.items():
        table = cls["vtable"]
        rig = Rig(executable, cls, 0, seed)
        mem = rig.emu.mem
        for slot, want in ((20, MODELS.SLOTS[name][0]), (21, MODELS.SLOTS[name][1]),
                           (23, 0x10DED0), (25, 0x10E658), (2, MODELS.SLOTS[name][2])):
            got = mem.u32(table + 8 * slot + 4)
            assert got == want, (name, slot, hex(got), hex(want))
            count += 1
    return count


def check_hits(executable, seed):
    """Hit helpers -> damage_apply 0x1e8230 (sight, isEnemy, grid collect stubbed)."""
    rng = random.Random("hits:%d" % seed)
    cls = R.CLASSES["Kobold"]
    count = 0
    for _ in range(6):
        lo, hi, rating = rng.randrange(1, 200), rng.randrange(200, 900), rng.randrange(1, 999)
        flags = rng.choice((1, 8, 0x40008, 0x80001, 0x100001, 0x440008, 0x404))
        desc = rng.choice((0, 0x1234))
        near, far, arc = 0.0, float(rng.choice((24, 30, 36, 60, 84))), rng.choice((2000, 6000, 8000, 0x7FFF))
        for helper in ("hitInArc", "hitAtReach", "hitAll"):
            for target, seen in ((1, 1), (1, 0), (0, 1)):
                rig = Rig(executable, cls, 6, rng.getrandbits(32), target=target,
                          answers=[seen] * 8)
                emu = rig.emu
                emu.unhook(0x1196E8)
                address = {"hitInArc": 0x119938, "hitAtReach": 0x1196E8, "hitAll": 0x119B58}[helper]
                emu.follow = {address, COS, SIN}
                emu.mem.wf32(rig.target + 0x10, 50.0)
                victims = [rig.target, rig.ally, rig.obj]

                def collect(e):
                    out = e.r[6] & 0xFFFFFFFF
                    for i, o in enumerate(victims):
                        e.mem.w32(out + 4 * i, o)
                    return len(victims)
                emu.stub(0x14A928, function=collect)
                emu.stub(0x119328, function=lambda e: int((e.r[5] & 0xFFFFFFFF) == rig.target))
                emu.reset_log()
                if helper == "hitAtReach":
                    emu.call(address, rig.obj, lo, hi, rating, flags, desc, fargs=(36.0,),
                             max_steps=300000)
                else:
                    emu.call(address, rig.obj, 0, arc, lo, hi, rating, flags, desc,
                             fargs=(near, far), max_steps=300000)
                applied = [c for c in emu.calls if c.target == 0x1E8230]
                if helper == "hitAtReach":
                    expect = 1 if target else 0          # 14 units from the reach point
                elif helper == "hitInArc":
                    expect = 1 if target and seen else 0
                    sight = [c for c in emu.calls if c.target == 0x10C810]
                    if target:
                        assert len(sight) == 1 and sight[0].args[1] & 0xFFFFFFFF == rig.target
                        assert (sight[0].args[3] & 0xFFFF, f(sight[0].fargs[1])) == (arc, far)
                else:
                    expect = 1 if seen else 0           # only the isEnemy candidate
                    grid = [c for c in emu.calls if c.target == 0x14A928][0]
                    assert grid.args[3] == 0x80
                assert len(applied) == expect, (helper, target, seen, len(applied))
                for call in applied:
                    a = [x & 0xFFFFFFFF for x in call.args]
                    assert a[0] == rig.target and a[1] == rig.obj
                    assert (a[2], a[3], a[4], a[5], a[6]) == (rating, 0, 0, flags, desc)
                    assert (f(call.fargs[0]), f(call.fargs[1])) == (float(lo), float(hi))
                count += 1
    # hitAtReach: 3-D distance of the target centre from position + facing x
    # reach, strictly below 60; radii do not enter; object flag 8 refuses.
    for reach, x, z, radius, oflags, expect in (
            (36.0, 95.9, 0.0, 20.0, 0, 1), (36.0, 96.0, 0.0, 20.0, 0, 0),
            (36.0, -23.9, 0.0, 20.0, 0, 1), (36.0, -24.0, 0.0, 20.0, 0, 0),
            (36.0, 36.0, 59.9, 5.0, 0, 1), (36.0, 36.0, 60.0, 40.0, 0, 0),
            (60.0, 119.9, 0.0, 20.0, 0, 1), (60.0, 120.0, 0.0, 20.0, 0, 0),
            (36.0, 36.0, 0.0, 20.0, 8, 0), (36.0, 36.0, 0.0, 20.0, 0x40, 1)):
        rig = Rig(executable, cls, 6, seed)
        emu = rig.emu
        emu.unhook(0x1196E8)
        emu.follow = {0x1196E8, COS, SIN}
        emu.mem.wf32(rig.target + 0x10, x)
        emu.mem.wf32(rig.target + 0x18, z)
        emu.mem.wf32(rig.target + 0x1C, radius)
        emu.mem.w32(rig.target + 0xC, oflags)
        emu.reset_log()
        emu.call(0x1196E8, rig.obj, 11, 22, 33, 8, 0, fargs=(reach,), max_steps=300000)
        got = len([c for c in emu.calls if c.target == 0x1E8230])
        assert got == expect, (reach, x, z, radius, oflags, got)
        count += 1
    return count


FACTORY, FACTORY_ALLOC = 0x159C94, 0x14FDB8
FACTORY_FOLLOW = (FACTORY, 0x159C20, 0x14F730, 0x14F850)


class FactoryFollow:
    def __contains__(self, addr):
        return addr in FACTORY_FOLLOW or 0x3A5000 <= addr < 0x3C0000


def put(emu, value):
    raw = value.encode("latin1") + b"\0"
    ptr = emu.alloc(len(raw))
    emu.mem.write(ptr, raw)
    return ptr


def check_levels(executable, levels, seed):
    """Record counts per level, then the factory's pool size and constructor
    for every creature record (shuffled per seed). Counts only are published."""
    emu = EE(executable)
    emu.follow = FactoryFollow()
    block = emu.alloc(0x1000)
    emu.mem.w32(0x44FDC8, emu.alloc(0x100))
    emu.stub(FACTORY_ALLOC, ret=block)
    selected = 0
    for level in R.LEVELS:
        path = Path(levels, level.upper() + ".GOB")
        rows = objects_from_file(str(path), path.read_bytes())
        assert len(rows) == R.RECORDS[level], (level, len(rows))
        counts = Counter(row["class"] for row in rows)
        for kind, (count, _size, _ctor) in R.CREATURES[level].items():
            assert counts[kind] == count, (level, kind, counts[kind])
        wanted = [row for row in rows if row["class"] in R.CREATURES[level]]
        random.Random("%s:%d" % (level, seed)).shuffle(wanted)
        for row in wanted:
            _count, size, ctor = R.CREATURES[level][row["class"]]
            strings = [put(emu, x) for x in row["properties"].split(";") if x]
            props = emu.alloc((len(strings) + 1) * 4)
            for i, ptr in enumerate(strings):
                emu.mem.w32(props + 4 * i, ptr)
            emu.reset_log()
            result = emu.call(FACTORY, put(emu, row["class"]), emu.alloc(12),
                              row["angle"], props, max_steps=500000)
            alloc = [c for c in emu.calls if c.target == FACTORY_ALLOC]
            ctors = [c.target for c in emu.calls if c.target not in FACTORY_FOLLOW
                     and c.target != FACTORY_ALLOC and not 0x3A5000 <= c.target < 0x3C0000]
            assert len(alloc) == 1 and alloc[0].args[0] == size, (level, row["class"])
            assert ctors and ctors[-1] == ctor and result == block, (level, row["class"])
            selected += 1
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("--seed", type=int, default=20973)
    parser.add_argument("--levels")
    parser.add_argument("-k", action="append")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--skip-walk", action="store_true")
    args = parser.parse_args()
    data = Path(args.executable).read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256, "unexpected executable"
    total = 0
    bad = []
    for name in MODELS.SPECS:
        if (args.k and name not in args.k) or args.skip_walk:
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
    if not args.k or args.skip_walk:
        print("PASS setState entries %d" % check_setstate(args.executable, args.seed))
        print("PASS filterState redirects %d" % check_filter(args.executable, args.seed))
        print("PASS vtable slots %d" % check_slots(args.executable, args.seed))
        print("PASS hit helpers %d" % check_hits(args.executable, args.seed))
    if args.levels:
        print("PASS level census and factory selections %d"
              % check_levels(args.executable, args.levels, args.seed))
    print("PASS all classes, %d answer paths, seed %d" % (total, args.seed))


if __name__ == "__main__":
    sys.exit(main())
