#!/usr/bin/env python3
"""Check a private Play! Valor trace against bounded campaign contracts.

Usage:
  PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_campaign_combat_live.py \
      work/valor-capture/targeted-breaks.log \
      work/valor-capture/player-entry.log \
      --fight work/valor-capture/fight-breaks.log

The inputs are ignored local logs. This checks identity and call order; a
constructor or hit call alone is not proof of a kill or a normal campaign exit.
"""

import argparse
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

        actors = {field(line, "a0") for line in lines
                  if f"pc={constructor:08x} " in line}
        run60 = {field(line, "a0") for line in lines
                 if "bp=obj_runEvery60 " in line and label in line}
        assert len(actors) == expected, (label, len(actors))
        assert actors <= base_objects and actors == run60, label
        print(f"{label}: {expected} base/derived/run60 identities; "
              f"{len(found)} nonzero {lump} lookups")


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("loader_breaks", type=Path)
    parser.add_argument("loader_run", type=Path)
    parser.add_argument("--fight", type=Path)
    args = parser.parse_args()
    check_loader(args.loader_breaks.read_text().splitlines())
    check_entry(args.loader_run.read_text())
    if args.fight:
        check_melee(args.fight.read_text().splitlines())


if __name__ == "__main__":
    main()
