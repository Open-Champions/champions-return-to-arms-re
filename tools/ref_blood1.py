"""Data-free factory and hostile resource contracts for the first story level.

Addresses and short resource identifiers are for SLUS-20973 US v2.00.  No
level records or resource bytes are stored here.
"""

FACTORY = {
    "bffiredoor": (0x198, 0x23C44C),  # AutoProp property fallback
    "bfhappydoor": (0x198, 0x23C44C),
    "barrel": (0x84, 0x290C24),
    "blocker": (0x4C, 0x28F15C),
    "kobold": (0x3D0, 0x27F0C0),
    "koboldtough": (0x3D0, 0x27F0C0),
    "koboldshaman": (0x3D0, 0x27F0C0),
    "npc": (0x480, 0x29DF04),
    "player1": (0x4C, 0x158928),
    "portal": (0x164, 0x27C694),
    "powderkeg": (0x84, 0x290C24),
    "pushtrigger": (0x4C, 0x1EC900),
    "savepoint": (0x118, 0x28CB90),
    "trigger": (0x70, 0x1ECDF4),
    "warwraith": (0x468, 0x2C07A8),
    "charambient_light": (0x4C, 0x158BCC),
    "chardirectional_light": (0x4C, 0x158C6C),
    "chardirectional_lightd": (0x4C, 0x158D0C),
    "orkbox": (0xF8, 0x23AD18),  # AutoChest property fallback
    "smokebomb": (0x4AC, 0x2C54F8),
}

# Authored class-string frequencies in BLOOD1.GOB objects.ob. Counts only;
# no positions, properties or record payloads are retained.
CLASS_COUNTS = {
    "Ambient_Light": 1, "Ambient_Light2": 1, "Barrel": 87,
    "BFfiredoor": 1, "BFhappydoor": 1, "Blocker": 33,
    "charAmbient_Light": 1, "charDirectional_Light": 1,
    "charDirectional_LightD": 1, "clearColor": 1, "customVars": 1,
    "Directional_Light": 1, "Directional_Light2": 1,
    "Directional_LightD": 1, "Directional_LightD2": 1,
    "Kobold": 118, "koboldshaman": 5, "Koboldtough": 8,
    "NPC": 1, "orkbox": 18, "Player1": 3, "Portal": 1,
    "PowderKeg": 13, "PushTrigger": 2, "Savepoint": 3,
    "smokeBomb": 44, "TestLocation": 4, "Trigger": 1,
    "WarWraith": 9,
}

# Six level-light records, four test locations, and the two metadata records
# are consumed without producing an object.  The factory side effects of the
# metadata records are outside this constructor comparison.
NO_OBJECT = {
    "ambient_light", "ambient_light2", "directional_light",
    "directional_light2", "directional_lightd", "directional_lightd2",
    "testlocation", "clearcolor", "customvars",
}

RESOURCE_DEFS = {
    0x500AF0: ("kobold.lmp", (
        "kobold.vif", "kobold.tex", "attack1.anm", "attack2.anm",
        "attack3.anm", "attack4.anm", "attack5.anm", "death1.anm",
        "death2.anm", "death3.anm", "death4.anm", "evade.anm",
        "evade_lft.anm", "evade_ryt.anm", "hitreact.anm",
        "hitreact2.anm", "knockdown.anm", "idle1.anm", "idle2.anm",
        "run.anm", "spell1.anm", "walk.anm")),
    0x5034F0: ("wwraith.lmp", (
        "warwraith.vif", "warwraith.tex", "ataklong.anm",
        "atakswd1.anm", "atakswd2.anm", "death.anm",
        "deathtouch.anm", "fly.anm", "forward.anm",
        "hitreaction.anm", "idle_axcythe.anm", "idleweap.anm",
        "cythe.vif", "cythe.tex", "dhaxe.vif", "dhaxe.tex",
        "dhsword1.vif", "dhsword1.tex")),
}

# Direct requests reached with the derived constructor running and its lower
# object/resource services stubbed. This is not a transitive resource list.
DIRECT_REQUESTS = {
    "Barrel": (("barrel.lmp", "barrel.vif"),
               ("barrel.lmp", "barrel.tex")),
    "PowderKeg": (("powderk.lmp", "powderkeg.vif"),
                  ("powderk.lmp", "powderkeg.tex")),
    "Blocker": (),
    "smokeBomb": (),
}
