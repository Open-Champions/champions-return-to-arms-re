"""Count-only object and bounded constructor reference for US RTA v2.00."""

COUNTS = {
    "strife": {
        "Ambient_Light": 1, "Ambient_Light2": 1, "Blocker": 6,
        "Catapult": 2, "Directional_Light": 1, "Directional_Light2": 1,
        "Directional_LightD": 1, "Directional_LightD2": 1, "Firepot": 6,
        "NPC": 4, "Orc2Archer": 20, "Orc2Leader": 2,
        "Orc2Leader1": 2, "Orc2Shaman": 2, "Orc2Soldier": 43,
        "Player1": 2, "Portal": 1, "PushTrigger": 2, "Savepoint": 3,
        "TestLocation": 8, "Torch": 64, "Trigger": 2, "Weather": 1,
        "ammocart": 2, "boxafay": 36, "boxbfay": 35,
        "charAmbient_Light": 1, "charDirectional_Light": 1,
        "charDirectional_LightD": 1, "clearColor": 1, "customVars": 1,
        "dbridge": 3, "gobstand": 5, "kelethinBomb": 15,
        "leanto": 6,
    },
    "drundar": {
        "Ambient_Light": 1, "Ambient_Light2": 1, "Barrel": 29,
        "Blocker": 12, "Crate": 71, "Directional_Light": 1,
        "Directional_Light2": 1, "Directional_LightD": 1,
        "Directional_LightD2": 1, "GoblinArcher": 23,
        "GoblinRecruit": 9, "GoblinSoldier": 39, "Ogre": 14,
        "Player1": 1, "Portal": 1, "PushTrigger": 13,
        "Savepoint": 3, "TestLocation": 7, "Trigger": 6,
        "UWStair": 1, "arenadoor": 4,
        "charAmbient_Light": 1, "charDirectional_Light": 1,
        "charDirectional_LightD": 1, "clearColor": 1,
        "customVars": 1, "orkbox": 3, "uwflag": 15,
        "uwswitch": 8,
    },
}

# Allocation size and selected constructor from the original object factory.
FACTORY = {
    "blocker": (0x4c, 0x28f15c), "catapult": (0xfc, 0x24d440),
    "firepot": (0x8c, 0x2b1e80), "npc": (0x480, 0x29df04),
    "crate": (0x148, 0x23d93c),
    "orc2archer": (0x488, 0x2a0954), "orc2leader": (0x488, 0x2a0954),
    "orc2leader1": (0x488, 0x2a0954),
    "orc2shaman": (0x488, 0x2a0954),
    "orc2soldier": (0x488, 0x2a0954),
    "player1": (0x4c, 0x158928), "portal": (0x164, 0x27c694),
    "pushtrigger": (0x4c, 0x1ec900),
    "savepoint": (0x118, 0x28cb90), "torch": (0x8c, 0x2b1e80),
    "trigger": (0x70, 0x1ecdf4), "weather": (0x2a0, 0x1d7778),
    "ammocart": (0x148, 0x23d93c),
    "boxafay": (0x148, 0x23d93c),
    "boxbfay": (0x148, 0x23d93c),
    "charambient_light": (0x4c, 0x158bcc),
    "chardirectional_light": (0x4c, 0x158c6c),
    "chardirectional_lightd": (0x4c, 0x158d0c),
    "dbridge": (0x198, 0x23c44c),
    "gobstand": (0x198, 0x23c44c),
    "kelethinbomb": (0x58, 0x261dbc),
    "leanto": (0xf8, 0x23ad18),
    "barrel": (0x84, 0x290c24),
    "goblinarcher": (0x498, 0x26a624),
    "goblinrecruit": (0x498, 0x26a624),
    "goblinsoldier": (0x498, 0x26a624),
    "ogre": (0x468, 0x29fad0),
    "uwstair": (0x198, 0x23c44c),
    "arenadoor": (0x198, 0x243594),
    "orkbox": (0xf8, 0x23ad18),
    "uwflag": (0x198, 0x23c44c),
    "uwswitch": (0x198, 0x23c44c),
}
NO_OBJECT = {
    "ambient_light", "ambient_light2", "directional_light",
    "directional_light2", "directional_lightd", "directional_lightd2",
    "testlocation", "clearcolor", "customvars",
}

HOSTILES = {
    "strife": {"Orc2Archer", "Orc2Leader", "Orc2Leader1",
               "Orc2Shaman", "Orc2Soldier"},
    "drundar": {"GoblinArcher", "GoblinRecruit", "GoblinSoldier", "Ogre"},
}

# GameObject_ctor definition tables: address, archive, entry count.
DEFINITIONS = {
    0x501df8: ("orc_vari.lmp", 45),
    0x500298: ("goblin.lmp", 25),
    0x501bf8: ("ogre.lmp", 15),
    0x4ff240: ("catapult.lmp", 2),
    0x4ffe08: ("firebomb.lmp", 2),
}
HOSTILE_DEF = {
    "Orc2Archer": 0x501df8, "Orc2Leader": 0x501df8,
    "Orc2Leader1": 0x501df8, "Orc2Shaman": 0x501df8,
    "Orc2Soldier": 0x501df8,
    "GoblinArcher": 0x500298, "GoblinRecruit": 0x500298,
    "GoblinSoldier": 0x500298, "Ogre": 0x501bf8,
}
HOSTILE_REQUESTS = {
    "Orc2Archer": 79, "Orc2Leader": 79, "Orc2Leader1": 79,
    "Orc2Shaman": 79, "Orc2Soldier": 79,
    "GoblinArcher": 39, "GoblinRecruit": 39,
    "GoblinSoldier": 39, "Ogre": 15,
}
ORC_WEAPONS = (
    "oaxe1", "obow1", "ocleever", "ohook", "omace", "oquiver",
    "oscimitar", "oshield1", "oshield2", "oshield3", "oshield4",
    "oshield5", "ospear", "osword1", "osword2", "osword3", "oarrow",
)
GOBLIN_WEAPONS = (
    "g_arrow", "g_staff", "g_bow", "g_shield", "g_axe",
    "g_sword1", "g_sword2",
)
DIRECT_REQUESTS = {
    "Catapult": (("catapult.lmp", "catapult.vif"),
                 ("catapult.lmp", "catapult.tex"),
                 ("catapult.lmp", "catapult.anm")),
    "kelethinBomb": (("firebomb.lmp", "firebomb.vif"),
                     ("firebomb.lmp", "firebomb.tex")),
    "Barrel": (("barrel.lmp", "barrel.vif"),
               ("barrel.lmp", "barrel.tex")),
    "Blocker": (), "PushTrigger": (), "Trigger": (),
    "Weather": (), "Torch": (), "Firepot": (),
}

# Authored property selectors. These identify candidate archives, not proven
# ordered res_find requests through the property-driven constructors.
PROPERTY_LUMPS = {
    "strife": {
        "Portal": "jumpgate", "Catapult": "catapult",
        "NPC": "we_sldr", "ammocart": "ammocart",
        "boxafay": "boxafay", "boxbfay": "boxbfay",
        "dbridge": "dbridge", "gobstand": "gobstand",
        "leanto": "leanto",
    },
    "drundar": {
        "Portal": "jumpgate", "UWStair": "ehubanim",
        "arenadoor": "uwadoor", "orkbox": "orkbox",
        "uwflag": "uwflag", "uwswitch": "uwswitch",
    },
}

# Paired per-record key/action names of the eight authored Drundar switches.
SWITCH_LINKS = (
    ("return6d01", "switchcod546"),
    ("returnb94e", "switchco48ad"),
    ("returnd0aa", "switchco6b46"),
    ("returnd4b", "switchcoc9e3"),
    ("return86a9", "switchco8cc5"),
    ("return71ee", "switchcod516"),
    ("return8615", "switchco45bd"),
    ("returndf30", "switchco1c6a"),
)
