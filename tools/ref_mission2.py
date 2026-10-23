"""Data-free authored-record and constructor contracts for mission 2.

US SLUS-20973 v2.00. Only class frequencies, identifiers and addresses are
stored here; the owner-supplied archives are read by difftest_mission2.py.
"""

LEVELS = ("innovat1", "inmine1", "inmine2", "innovat2")

COUNTS = {
    "innovat1": {
        "Ambient_Light": 1, "Ambient_Light2": 1, "Blocker": 19,
        "Directional_Light": 1, "Directional_Light2": 1,
        "Directional_LightD": 1, "Directional_LightD2": 1,
        "NPC": 2, "Player1": 2, "Portal": 1, "PushTrigger": 1,
        "Rat": 36, "Savepoint": 2, "Seagull": 30, "TestLocation": 5,
        "charAmbient_Light": 1, "charDirectional_Light": 1,
        "charDirectional_LightD": 1, "clearColor": 1,
        "clockworkcutter": 23, "clockworkhammer": 29, "customVars": 1,
        "gearbox": 6, "lavakeg": 113, "smokeBomb": 17,
    },
    "inmine1": {
        "Ambient_Light": 1, "Ambient_Light2": 1, "Blocker": 4,
        "Directional_Light": 1, "Directional_Light2": 1,
        "Directional_LightD": 1, "Directional_LightD2": 1,
        "Droid": 30, "Player1": 2, "PowderKeg": 33,
        "PushTrigger": 2, "Savepoint": 2, "Weather": 1,
        "charAmbient_Light": 1, "charDirectional_Light": 1,
        "charDirectional_LightD": 1, "clearColor": 1,
        "clockworkcutter": 23, "clockworkhammer": 23,
        "customVars": 1, "gbarrel": 77, "gearbox": 5,
    },
    "inmine2": {
        "Ambient_Light": 1, "Ambient_Light2": 1,
        "Directional_Light": 1, "Directional_Light2": 1,
        "Directional_LightD": 1, "Directional_LightD2": 1,
        "Player1": 2, "PowderKeg": 11, "PushTrigger": 2,
        "Savepoint": 2, "TestLocation": 2,
        "charAmbient_Light": 1, "charDirectional_Light": 1,
        "charDirectional_LightD": 1, "clearColor": 1,
        "clockworkcutter": 20, "clockworkhammer": 14,
        "customVars": 1, "gbarrel": 51, "gearbox": 3,
    },
    "innovat2": {
        "Ambient_Light": 1, "Ambient_Light2": 1, "Blocker": 30,
        "Directional_Light": 1, "Directional_Light2": 1,
        "Directional_LightD": 1, "Directional_LightD2": 1,
        "IronGuardian": 1, "Player1": 1, "Portal": 1,
        "PushTrigger": 1, "Rat": 8, "Seagull": 12,
        "Trigger": 2, "charAmbient_Light": 1,
        "charDirectional_Light": 1, "charDirectional_LightD": 1,
        "clearColor": 1, "customVars": 1, "smokeBomb": 4,
    },
}

# Original factory allocation size and called constructor, for every selected
# class string in these four objects.ob files. Metadata/light/test records
# listed in NO_OBJECT do not allocate a GameObject here.
FACTORY = {
    "blocker": (0x4c, 0x28f15c),
    "droid": (0x3d0, 0x27b840),
    "ironguardian": (0x3e8, 0x27a00c),
    "npc": (0x480, 0x29df04),
    "player1": (0x4c, 0x158928),
    "portal": (0x164, 0x27c694),
    "powderkeg": (0x84, 0x290c24),
    "pushtrigger": (0x4c, 0x1ec900),
    "rat": (0x448, 0x2547fc),
    "savepoint": (0x118, 0x28cb90),
    "seagull": (0x448, 0x2547fc),
    "trigger": (0x70, 0x1ecdf4),
    "weather": (0x2a0, 0x1d7778),
    "charambient_light": (0x4c, 0x158bcc),
    "chardirectional_light": (0x4c, 0x158c6c),
    "chardirectional_lightd": (0x4c, 0x158d0c),
    "clockworkcutter": (0x500, 0x24e124),
    "clockworkhammer": (0x500, 0x24e124),
    "gbarrel": (0x148, 0x23d93c),
    "gearbox": (0xf8, 0x23ad18),
    "lavakeg": (0x148, 0x23d93c),
    "smokebomb": (0x4ac, 0x2c54f8),
}
NO_OBJECT = {
    "ambient_light", "ambient_light2", "directional_light",
    "directional_light2", "directional_lightd", "directional_lightd2",
    "testlocation", "clearcolor", "customvars",
}

# GameObject_ctor class-definition requests, in exact order. These three
# definitions are reached by the new mission-2 hostile constructors.
RESOURCE_DEFS = {
    0x4ff260: ("clokwork.lmp", (
        "clockwork.vif", "clockwork.tex",
        *(f"cutter_attack{i}.anm" for i in range(1, 4)),
        *(f"cutter_death{i}.anm" for i in range(1, 4)),
        "cutter_hit.anm", "cutter_idle1.anm", "cutter_walk.anm",
        "cutter_walkattack.anm",
        *(f"hammer_attack{i}.anm" for i in range(1, 4)),
        *(f"hammer_death{i}.anm" for i in range(1, 4)),
        "hammer_hit.anm", "hammer_idle1.anm", "hammer_walk.anm",
        "hammer_walkattack.anm", "l_swoosh.vif", "l_swoosh.tex",
        "r_swoosh.vif", "r_swoosh.tex")),
    0x500a88: ("droid.lmp", (
        "droid.vif", "droid.tex", "explode.anm", "hit_reaction.anm",
        "idle_aggressive.anm", "idle_passive.anm", "run.anm",
        "walk.anm", "death_01.anm", "death_02.anm")),
    0x500960: ("iron.lmp", (
        "i_guard.vif", "i_guard.tex",
        *(f"attack_0{i}.anm" for i in range(1, 5)),
        "catapault.anm", "death.anm", "hit_reaction_01.anm",
        "hit_reaction_02.anm", "idle_01.anm", "idle_02.anm",
        "shoot.anm", "walk.anm",
        *(entry for i in range(1, 11)
          for entry in (f"junk_{i:02}.vif", f"junk_{i:02}.tex")))),
}

HOSTILES = {"clockworkcutter", "clockworkhammer", "Droid", "IronGuardian"}

# Only requests made directly by these derived constructors with lower
# services stubbed. An empty tuple says nothing about later effects.
DIRECT_REQUESTS = {
    "PowderKeg": (("powderk.lmp", "powderkeg.vif"),
                  ("powderk.lmp", "powderkeg.tex")),
    "Blocker": (),
    "PushTrigger": (),
    "Trigger": (),
    "Weather": (),
    "smokeBomb": (),
}

# Minimum observed entry sets for dynamically formatted request families.
# Archive presence is not an exact ordered res_find contract.
ARCHIVE_PRESENCE = {
    "rat.lmp": ("rat.vif", "rat.tex", "rat_idle.anm", "rat_move.anm"),
    "seagull.lmp": ("seagull.vif", "seagull.tex", "seagull_move.anm",
                    "stretch.anm", "preen.anm"),
    "gbarrel.lmp": ("gbarrel.vif", "gbarrel.tex", "gbarrel_explode.vif",
                    "gbarrel_explode.tex"),
    "lavakeg.lmp": ("lavakeg.vif", "lavakeg.tex", "lavakeg_explode.vif",
                    "lavakeg_explode.tex"),
    "gearbox.lmp": ("gearbox.vif", "gearbox.tex", "gearbox.anm"),
}
