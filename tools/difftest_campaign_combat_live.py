#!/usr/bin/env python3
"""Check a private Play! Valor trace against bounded campaign contracts.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_live.py \
      work/valor-capture/targeted-breaks.log \
      work/valor-capture/player-entry.log \
      --fight work/valor-capture/fight-breaks.log \
      --supported work/valor-capture/round8-supported-breaks.log \
      --supported-watch work/valor-capture/round8-supported-watch.tsv \
      --kill work/valor-capture/round8-kill-breaks.log \
      --kill-watch work/valor-capture/round8-kill-watch.tsv \
      --credit work/valor-capture/round8-credit-breaks.log

The inputs are ignored local logs. The optional death/credit check requires
the HP watch and the focused HUD replay; a constructor or hit call alone is
not proof of a kill or a normal campaign exit.
"""

import argparse
import csv
import re
from pathlib import Path

from ref_campaign_combat_r4 import MODEL_CLASS
from ref_campaign_combat_r5 import CONSTRUCTORS, DEFINITION_SLOTS


def field(line, name, base=16):
    match = re.search(r"(?:^| )" + re.escape(name) + r"=([0-9a-f]+)(?: |$)", line)
    if match is None:
        raise AssertionError(f"missing {name}: {line[:160]}")
    return int(match.group(1), base)


def entries(lines, marker):
    return [line for line in lines if marker in line]


def number_field(line, name):
    match = re.search(r"(?:^| )" + re.escape(name)
                      + r"=([-+]?[0-9]+(?:\.[0-9]+)?)(?: |$)", line)
    if match is None:
        raise AssertionError(f"missing numeric {name}: {line[:160]}")
    return float(match.group(1))


def check_loader(lines):
    definitions = {
        0x502F80: ("warboar.lmp", 0x2BA03C, 78, "WarBoar_ctor"),
        0x501200: ("minotaur.lmp", 0x288FDC, 6, "Minotaur_ctor"),
    }
    base_objects = {field(line, "a0") for line in entries(lines, "bp=GameObject_ctor ")}
    for definition, (lump, constructor, expected, label) in definitions.items():
        assert definition in [value[2] for value in CONSTRUCTORS.values()]
        found = []
        for index, line in enumerate(lines[:-1]):
            if ("bp=res_find " in line and "ra=0014cbfc" in line
                    and field(line, "a2") == definition):
                returned = lines[index + 1]
                assert "ret=res_find " in returned
                found.append(field(returned, "v0"))
        assert len(found) == DEFINITION_SLOTS[lump], (lump, len(found))
        assert all(found) and len(set(found)) == len(found), lump

        class_calls = [(index, field(line, "a0"))
                       for index, line in enumerate(lines)
                       if f"pc={constructor:08x} " in line]
        actors = {actor for _, actor in class_calls}
        run60 = {field(line, "a0") for line in lines
                 if "bp=obj_runEvery60 " in line and label in line}
        assert len(actors) == expected, (label, len(actors))
        assert actors <= base_objects and actors == run60, label
        for call_number, (class_at, actor) in enumerate(class_calls):
            end = (class_calls[call_number + 1][0]
                   if call_number + 1 < len(class_calls) else len(lines))
            # Creature_ctor is identified by GameObject_ctor's live return
            # address; this trace did not break at Creature_ctor entry.
            base_at = next(index for index in range(class_at + 1, end)
                           if "bp=GameObject_ctor " in lines[index]
                           and "ra=00109dbc(Creature_ctor+0x54)" in lines[index]
                           and field(lines[index], "a0") == actor)
            base_ret = next(index for index in range(base_at + 1, end)
                            if "ret=GameObject_ctor " in lines[index])
            class_ret = next(index for index in range(base_ret + 1, end)
                             if f"ret={label} " in lines[index])
            assert class_at < base_at < base_ret < class_ret
            if call_number == 0:
                lookups = [index for index in range(base_at + 1, base_ret)
                           if "bp=res_find " in lines[index]
                           and "ra=0014cbfc" in lines[index]
                           and field(lines[index], "a2") == definition]
                assert len(lookups) == DEFINITION_SLOTS[lump], (label, len(lookups))
                assert all("ret=res_find " in lines[index + 1]
                           for index in lookups), label
        print(f"{label}: {expected} base/derived/run60 identities; "
              f"{len(found)} nonzero {lump} lookups; nested entry/return order")


def check_entry(text):
    line = next(line for line in text.splitlines()
                if "g_levelName@" in line and "=valor " in line
                and "g_players+0x50@" in line)
    def value(offset):
        match = re.search(r"g_players\+" + re.escape(offset)
                          + r"@[0-9a-f]+=(\w+)", line)
        assert match, offset
        return match.group(1)
    klass, model = int(value("0x50")), int(value("0x54"))
    assert MODEL_CLASS[model] == klass
    assert int(value("0x4a7c")) in (0, 1)
    assert int(value("0x4434"), 16) != 0
    print(f"Valor entry: class {klass}, model {model}, active set "
          f"{value('0x4a7c')}, weapon pointer nonzero")


def check_melee(lines):
    hits = entries(lines, "bp=Player_meleeHit ")
    assert hits, "no player melee call"
    ordered = 0
    for hit in hits:
        frame = field(hit, "frame", 10)
        target = field(hit, "a1")
        later = lines[lines.index(hit) + 1:]
        damage = next((line for line in later if "bp=damage_apply " in line
                       and "Player_meleeHit" in line
                       and field(line, "frame", 10) == frame), None)
        take = next((line for line in later if "bp=Creature_takeDamage " in line
                     and field(line, "frame", 10) == frame), None)
        if (damage and take and lines.index(damage) < lines.index(take)
                and field(damage, "a0") == target and field(take, "a0") == target):
            ordered += 1
    assert ordered, "no melee -> damage -> takeDamage sequence"
    drops = len(entries(lines, "bp=Creature_dropLoot "))
    print(f"melee: {len(hits)} calls, {ordered} ordered damage paths, "
          f"{drops} loot calls; kill not determined by this checker")


def check_supported(lines, watch_path):
    watch = list(csv.DictReader(watch_path.open(), delimiter="\t"))
    assert watch and "boar_hp" in watch[0]
    hp = [float(row["boar_hp"]) for row in watch]
    positive = [line for line in entries(lines, "bp=Creature_takeDamage ")
                if number_field(line, "f12") > 0]
    assert len(positive) == 2, ("positive hits", len(positive))
    actor = field(positive[0], "a0")
    assert all(field(line, "a0") == actor for line in positive)
    assert all(any("bp=damage_apply " in call and "Player_meleeHit" in call
                   and field(call, "a0") == actor
                   and field(call, "frame", 10) == field(line, "frame", 10)
                   for call in lines) for line in positive)
    assert abs((hp[0] - hp[-1])
               - sum(number_field(line, "f12") for line in positive)) < 0.001
    assert not entries(lines, "bp=Creature_dropLoot ")
    print(f"first live hits: boar HP {hp[0]:.6f} -> {hp[-1]:.6f}; "
          f"{len(positive)} positive takeDamage calls")


def check_kill(lines, watch_path, credit_lines):
    watch = list(csv.DictReader(watch_path.open(), delimiter="\t"))
    assert watch and {"frame", "boar_hp", "gold"} <= watch[0].keys()
    hp = [float(row["boar_hp"]) for row in watch]
    gold = [int(row["gold"]) for row in watch]
    assert hp[0] > 0 and min(hp) <= 0
    assert all(after <= before for before, after in zip(hp, hp[1:])), "boar HP rose"

    drops = [(index, line) for index, line in enumerate(lines)
             if "bp=Creature_dropLoot " in line]
    assert len(drops) == 1, ("loot calls", len(drops))
    drop_at, drop = drops[0]
    actor, drop_frame = field(drop, "a0"), field(drop, "frame", 10)
    assert "WarBoar_setState" in drop
    death_hit = next((line for line in reversed(lines[:drop_at])
                      if "bp=Creature_takeDamage " in line
                      and field(line, "a0") == actor
                      and number_field(line, "f12") > 0), None)
    assert death_hit and field(death_hit, "frame", 10) == drop_frame - 1
    assert any("bp=damage_apply " in line and "Player_meleeHit" in line
               and field(line, "a0") == actor
               and field(line, "frame", 10) == drop_frame - 1
               for line in lines[:drop_at])
    assert any("bp=WarBoar_run " in line
               and "ra=0014bb80(runObjects+0x270)" in line
               and field(line, "a0") == actor for line in lines)
    assert any("bp=runObjects " in line for line in lines)
    first_dead = next(int(row["frame"]) for row in watch
                      if float(row["boar_hp"]) <= 0)
    assert abs(first_dead - drop_frame) <= 1
    generated = [line for line in lines[drop_at:]
                 if "bp=loot_generateDrops " in line
                 and field(line, "frame", 10) == drop_frame]
    assert len(generated) == 1 and "Creature_dropLoot" in generated[0]
    assert not entries(lines, "bp=loot_spawnGold ")

    constructors = entries(lines, "bp=Gold_ctor2 ")
    floaters = entries(lines, "bp=hud_addGoldFloater ")
    assert len(constructors) == len(floaters) == 2
    assert all("AutoContainer_run" in line for line in constructors)
    amounts = [field(line, "a2") for line in floaters]
    assert amounts == [field(line, "a2") for line in constructors]
    for ctor, floater in zip(constructors, floaters):
        ctor_frame, pickup_frame = (field(line, "frame", 10)
                                   for line in (ctor, floater))
        assert ctor_frame < pickup_frame
        assert "Gold_onTouch" in floater
        assert any("bp=Gold_onTouch " in line
                   and field(line, "a0") == field(ctor, "a0")
                   and field(line, "frame", 10) == pickup_frame
                   for line in lines)
    assert gold[-1] - gold[0] == sum(amounts)

    hud = entries(credit_lines, "bp=hud_tickGold ")
    assert hud, "no direct gold tick in credit replay"
    credited = [field(line, "gold", 10) for line in hud]
    assert credited[0] == gold[0] and credited[-1] == gold[-1]
    assert all(after >= before for before, after in zip(credited, credited[1:]))
    print(f"kill: boar HP {hp[0]:.6f} -> {min(hp):.6f}; "
          f"takeDamage frame {drop_frame - 1}, drop/generator frame {drop_frame}")
    print(f"Gold: AutoContainer objects {amounts}, touch/floater -> "
          f"hud_tickGold {gold[0]} -> {gold[-1]}; no boar Gold spawn")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("loader_breaks", type=Path)
    parser.add_argument("loader_run", type=Path)
    parser.add_argument("--fight", type=Path)
    parser.add_argument("--supported", type=Path, help="first positive-hit breakpoint log")
    parser.add_argument("--supported-watch", type=Path, help="first positive-hit HP watch")
    parser.add_argument("--kill", type=Path, help="controlled death/pickup breakpoint log")
    parser.add_argument("--kill-watch", type=Path, help="controlled boar HP/Gold watch")
    parser.add_argument("--credit", type=Path, help="focused hud_tickGold replay log")
    args = parser.parse_args()
    check_loader(args.loader_breaks.read_text().splitlines())
    check_entry(args.loader_run.read_text())
    if args.fight:
        check_melee(args.fight.read_text().splitlines())
    if args.supported or args.supported_watch:
        assert args.supported and args.supported_watch
        check_supported(args.supported.read_text().splitlines(), args.supported_watch)
    if args.kill or args.kill_watch or args.credit:
        assert args.kill and args.kill_watch and args.credit
        check_kill(args.kill.read_text().splitlines(), args.kill_watch,
                   args.credit.read_text().splitlines())


if __name__ == "__main__":
    main()
