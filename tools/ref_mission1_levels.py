"""Reference model of the mission 1 level scripts (US RTA v2.00).

strife, drundar (story levels after blood1) and drunarm, drunare (their arenas).
Written from the script listings and read independently of the executed run;
tools/difftest_mission1_levels.py compares it with the original script host.

Holds only identifiers (class, entry, variable, monster, level and cutscene
names), counts and code offsets. Text keys are never stored: the model logs
them as "<text>". Positions, raw records and script bytes are not here.
"""
import struct

# ---------------------------------------------------------------- object census
COUNTS = {
    "drunarm": {
        "GladiatorBare": 82, "Crate": 63, "Torch": 46, "Blocker": 32, "PowderKeg": 25,
        "weaprack": 24, "Catapult": 4, "Savepoint": 3, "orkbox": 3, "Trigger": 3,
        "RalosZek": 2, "PushTrigger": 1, "Player1": 1, "Portal": 1, "TestLocation": 1,
        "Ambient_Light": 1, "Directional_Light": 1, "Directional_LightD": 1,
        "charAmbient_Light": 1, "charDirectional_Light": 1, "charDirectional_LightD": 1,
        "Ambient_Light2": 1, "Directional_Light2": 1, "Directional_LightD2": 1,
        "clearColor": 1, "customVars": 1,
    },
    "drunare": {
        "uwflag": 14, "arenadoor": 4, "Trigger": 2, "Player1": 1, "RalosZek": 1,
        "UndeadKnight1": 1, "UndeadKnight2": 1, "UndeadKnight3": 1, "UndeadKnight4": 1,
        "CazicAvatar": 1, "PushTrigger": 1,
        "Ambient_Light": 1, "Directional_Light": 1, "Directional_LightD": 1,
        "charAmbient_Light": 1, "charDirectional_Light": 1, "charDirectional_LightD": 1,
        "Ambient_Light2": 1, "Directional_Light2": 1, "Directional_LightD2": 1,
        "clearColor": 1, "customVars": 1,
    },
}
# Allocation size and last constructor the original factory selects (lower-case key).
# Classes shared with strife/drundar keep their entries in ref_strife_drundar.FACTORY.
FACTORY = {
    "gladiatorbare": (0x480, 0x2bafb4), "raloszek": (0x480, 0x2c1f94),
    "undeadknight1": (0x478, 0x271c70), "undeadknight2": (0x478, 0x271c70),
    "undeadknight3": (0x478, 0x271c70), "undeadknight4": (0x478, 0x271c70),
    "cazicavatar": (0x3e8, 0x24a670), "powderkeg": (0x84, 0x290c24),
    "weaprack": (0x148, 0x23d93c), "arenadoor": (0x198, 0x243594),
    "uwflag": (0x198, 0x23c44c), "orkbox": (0xf8, 0x23ad18),
    "catapult": (0xfc, 0x24d440), "portal": (0x164, 0x27c694),
    "pushtrigger": (0x4c, 0x1ec900), "trigger": (0x70, 0x1ecdf4),
    "savepoint": (0x118, 0x28cb90), "blocker": (0x4c, 0x28f15c),
    "torch": (0x8c, 0x2b1e80), "player1": (0x4c, 0x158928),
    "charambient_light": (0x4c, 0x158bcc), "chardirectional_light": (0x4c, 0x158c6c),
    "chardirectional_lightd": (0x4c, 0x158d0c),
}
# No object (the factory returns 0): property-less Crate, TestLocation, plain lights,
# clearColor, customVars (customVars calls 0x22e714 and still returns 0).
NO_OBJECT = {"crate", "testlocation", "ambient_light", "directional_light",
             "directional_lightd", "ambient_light2", "directional_light2",
             "directional_lightd2", "clearcolor", "customvars"}
ARENA_TOTALS = {"drunarm": (302, 230), "drunare": (39, 31)}   # records, objects made

# ---------------------------------------------------------------- record -> entry links
LINKS = {
    "strife": {
        ("Catapult", "deathscript", "callScri8d4a"): 2,
        ("Catapult", "script", "return523c"): 2,
        ("NPC", "dialogscript", "startDia30cc"): 1,
        ("NPC", "dialogscript", "startDia8851"): 1,
        ("NPC", "dialogscript", "startDiab722"): 1,
        ("NPC", "dialogscript", "startDiad2e3"): 1,
        ("NPC", "exclamation", "return1e8e"): 1,
        ("NPC", "exclamation", "returnadae"): 1,
        ("NPC", "exclamation", "returnc3ef"): 1,
        ("NPC", "exclamation", "returne210"): 1,
        ("Orc2Archer", "deathscript", "callScria77e"): 8,
        ("Orc2Archer", "initscript", "callScri52e"): 8,
        ("Orc2Shaman", "deathscript", "callScri4980"): 2,
        ("Orc2Shaman", "initscript", "callScri9f82"): 2,
        ("Orc2Soldier", "deathscript", "callScria77e"): 5,
        ("Orc2Soldier", "initscript", "callScri52e"): 5,
        ("PushTrigger", "action", "callScri5a82"): 1,
        ("PushTrigger", "action", "newWorld5d32"): 1,
        ("Trigger", "t", "if9d85"): 1,
        ("Trigger", "t", "newWorld5d32"): 1,
        ("kelethinBomb", "script", "return8821"): 15,
    },
    "drundar": {
        ("PushTrigger", "action", "callScri5a82"): 4,
        ("PushTrigger", "action", "newWorld5d32"): 1,
        ("PushTrigger", "key", "return56e0"): 4,
        ("Trigger", "t", "callScri28d3"): 2,
        ("Trigger", "t", "callScri5a82"): 4,
        ("uwswitch", "action1", "switchco1c6a"): 1,
        ("uwswitch", "action1", "switchco45bd"): 1,
        ("uwswitch", "action1", "switchco48ad"): 1,
        ("uwswitch", "action1", "switchco6b46"): 1,
        ("uwswitch", "action1", "switchco8cc5"): 1,
        ("uwswitch", "action1", "switchcoc9e3"): 1,
        ("uwswitch", "action1", "switchcod516"): 1,
        ("uwswitch", "action1", "switchcod546"): 1,
        ("uwswitch", "key", "return6d01"): 1,
        ("uwswitch", "key", "return71ee"): 1,
        ("uwswitch", "key", "return8615"): 1,
        ("uwswitch", "key", "return86a9"): 1,
        ("uwswitch", "key", "returnb94e"): 1,
        ("uwswitch", "key", "returnd0aa"): 1,
        ("uwswitch", "key", "returnd4b"): 1,
        ("uwswitch", "key", "returndf30"): 1,
    },
    "drunarm": {
        ("Catapult", "script", "return25eb"): 4,
        ("Portal", "script", "if6896"): 1,
        ("PushTrigger", "action", "newWorld1c57"): 1,
        ("Trigger", "t", "callScric1d7"): 1,
        ("Trigger", "t", "callScricb6b"): 1,
    },
    "drunare": {
        ("CazicAvatar", "deathscript", "callScria381"): 1,
        ("PushTrigger", "action", "newWorldbcf6"): 1,
        ("PushTrigger", "key", "return9d74"): 1,
        ("Trigger", "t", "callScri8654"): 1,
        ("Trigger", "t", "newWorldbcf6"): 1,
        ("UndeadKnight1", "deathscript", "setv4d6b"): 1,
        ("UndeadKnight2", "deathscript", "setv772a"): 1,
        ("UndeadKnight3", "deathscript", "setv5138"): 1,
        ("UndeadKnight4", "deathscript", "setvcccf"): 1,
    },
}
# Entries reached from neither a record nor script code, and the dialog resource
# (in the same level lump) whose bytes name them.
DIALOG_ENTRIES = {
    "strife": {
        "we_scout.dbin": ("if70a4", "iff29", "setv176d"),
        "we_scout_2.dbin": ("if3e90", "setv23a8"),
        "we_scout_3.dbin": ("if40b3", "setv8921"),
        "we_scout_4.dbin": ("setv70e6",),
    },
}
LOAD_ENTRIES = {"strife": ("preStart", "start"), "drundar": ("preStart", "start"),
                "drunarm": ("prestart", "start"), "drunare": ("start",)}
LOADER_NAMES = ((0x217acc, 0x53f000, "preStart"), (0x217bac, 0x53f020, "start"))

# ---------------------------------------------------------------- cutscenes
# (level, requesting entry, call offset, cutscene, header flags, keys, actors,
#  [(actor class, "create" or bound record name or "" for an unnamed record)],
#  object show keys (key type 8) by actor index)
CUTSCENES = (
    ("strife", "step1scene", 0xffc, "step1com", 0x8, 52, 2,
     (("NPC", "we_scout"), ("NPC", "we_scout_2")), (1,)),
    ("strife", "step2delay", 0x14b0, "step2complete", 0x0, 37, 3,
     (("NPC", "we_scout_2"), ("dbridge", "bridge1"), ("NPC", "we_scout_3")), (2,)),
    ("strife", "step3delay", 0x1900, "step3complete", 0x0, 58, 4,
     (("NPC", "we_scout_3"), ("NPC", "we_scout_4"), ("dbridge", "bridge2"),
      ("dbridge", "bridge3")), (1,)),
    ("drundar", "doors", 0xacc, "doors", 0x8, 27, 5,
     (("arenadoor", "door"), ("arenadoor", "door"), ("arenadoor", "door"),
      ("arenadoor", "door"), ("UWStair", "stairs")), ()),
    ("drunarm", "trippedTrigger", 0x31c, "rallosintro", 0x8, 31, 3,
     (("RalosZek", "rallos"), ("Player", "create"), ("Portal", "")), ()),
    ("drunarm", "playRallosRuns", 0x630, "rallosruns", 0x8, 20, 1,
     (("RalosZek", "rallos2"),), ()),
    ("drunare", "incoming", 0x244, "knights", 0x8, 57, 4,
     (("UndeadKnight4", "knight"), ("UndeadKnight3", "knight"),
      ("UndeadKnight2", "knight"), ("UndeadKnight1", "knight")), (0, 1, 2, 3)),
    ("drunare", "knightDefeated", 0x660, "cazic", 0x8, 43, 3,
     (("arenadoor", "exitdoor"), ("CazicAvatar", "avatar"), ("Player", "create")), (1,)),
    ("drunare", "endmission", 0x9fc, "bossdefeated", 0x8, 64, 2,
     (("arenadoor", ""), ("RalosZek", "rallos")), (1,)),
)
# Cutscene files in the lump that no script requests (besides the ten autosave files).
UNREQUESTED = {"strife": (), "drundar": (), "drunarm": ("rallosrun",), "drunare": ()}
AUTOSAVE = {"strife": 10, "drundar": 10, "drunarm": 10, "drunare": 9}
# Actor classes of the unrequested files.
UNREQUESTED_ACTORS = {"rallosrun": ("UndeadKnight",)}
# Object keys of type 3 / 4 (virtual slot 3 with 1 / 0, cut_execKey 0x196788) per
# cutscene: (actor index, key type) -> count.
SLOT3_KEYS = {
    "step1com": {}, "step2complete": {(1, 3): 1}, "step3complete": {(2, 3): 1},
    "doors": {(0, 3): 1, (1, 3): 1, (2, 3): 1, (3, 3): 1, (4, 3): 1},
    "rallosintro": {}, "rallosruns": {}, "knights": {},
    "cazic": {(0, 3): 1, (0, 4): 1}, "bossdefeated": {(0, 3): 1, (0, 4): 1},
}

# ---------------------------------------------------------------- record properties
# (level, class, record name) -> ((key, value or None for presence only), ...), (absent keys)
RECORD_FACTS = {
    ("drunarm", "RalosZek", "rallos"): ((("dropitem", "shardofwar"),), ("wait", "hide")),
    ("drunarm", "RalosZek", "rallos2"): ((("wait", None),), ("dropitem",)),
    ("drunare", "RalosZek", "rallos"): ((("wait", None),), ("dropitem",)),
    ("drunare", "CazicAvatar", "avatar"): ((("wait", None), ("deathscript", "callScria381")), ("dropitem",)),
    ("drunare", "arenadoor", "exitdoor"): ((("triggerable", None), ("autodoor", None)), ()),
}
# (level, class) -> property key tuple of every record of the class (as a multiset).
CLASS_KEYS = {
    ("drunarm", "GladiatorBare"): ((),) * 82,
    ("drunarm", "Portal"): (("lump", "script"),),
    ("strife", "Portal"): (("lump",),),
    ("drundar", "Portal"): (("lump",),),
    ("drunarm", "Trigger"): (("w", "h", "t"),) * 3,
}
# (level, class, key) -> the values of that key over the class's records (as a multiset).
# "<empty>" is the record's own placeholder value; it names no entry.
CLASS_VALUES = {
    ("drunarm", "Trigger", "t"): ("callScricb6b", "callScric1d7", "<empty>"),
    ("drunarm", "Portal", "script"): ("if6896",),
}
# Every `dropitem` value in each level (as a multiset).
DROPS = {
    "strife": (), "drundar": (), "drunarm": ("shardofwar",),
    "drunare": ("rejuvpotion", "healingpotion", "rejuvpotion", "healingpotion"),
}

# ---------------------------------------------------------------- travel requests
# (level, entry, call offset, destination) for every newWorld site in the four scripts.
NEWWORLD = (
    ("strife", "newWorld5d32", 0x490, "blood1"),
    ("strife", "exitzone", 0x1ae8, "hub"),        # demoRunning branch only
    ("strife", "exitzone", 0x1b94, "drunarm"),
    ("drundar", "exitzone", 0x1a18, "hub"),       # demoRunning branch only
    ("drundar", "exitzone", 0x1ac4, "drunare"),
    ("drundar", "newWorld5d32", 0x1c20, "blood1"),
    ("drunarm", "newWorld1c57", 0xc90, "strife"),
    ("drunare", "levelChange", 0xaf0, "hub2"),
    ("drunare", "newWorldbcf6", 0xd98, "drundar"),
)
GRANTS = (("strife", "exitzone", 0x1abc), ("drundar", "exitzone", 0x19ec),
          ("drunarm", "shardCheckLoop", 0x97c), ("drunare", "levelChange", 0xac4))

# ---------------------------------------------------------------- the script model
_K = struct.unpack("<f", struct.pack("<I", 0x3C888888))[0]


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def scaled_time(n):
    """getScaledTime 0x14412c: int((f32(n) * 60.0) * 0x3c888888)."""
    return int(f32(f32(f32(n) * 60.0) * _K))


TEXT = "<text>"
STUBBED = ("hideMonster", "showMonster", "killMonster", "deleteMonster", "setMonsterVal",
           "autoPropSetState", "setCFlag", "setSaveInhibit", "cutScene", "soundSequence",
           "setInfo", "reapEnemies", "addHelpMessage", "playGotItemSound", "startDialog",
           "showBust", "addParticleOnObject", "getHitPoints", "addQuest", "trigger",
           "preloadResource", "setParticle")


class Model:
    """The four level scripts as Python. One instance per level run."""

    def __init__(self, level):
        self.level = level
        self.vars = {}            # lower-cased name -> signed byte, insertion order
        self.g = {}               # script globals by cell offset
        self.front, self.back = [], []
        self.post = ""
        self.pending = ""
        self.paused = 0
        self.counts = [0, 0, 0, 0]
        self.num_players = 1
        self.hp = {}
        self.demo = 0
        self.mission1 = 1
        self.log, self.scripts = [], []

    # natives -------------------------------------------------------------------
    def n(self, name, *args):
        self.log.append((name,) + args)
        if name == "getv":
            return self.vars.setdefault(args[0].lower(), 0)
        if name == "setv":
            v = args[1] & 0xFF
            self.vars[args[0].lower()] = v - 256 if v > 127 else v
            return 0
        if name == "addDeferedCall":
            self.back.append(args[0])
            return 0
        if name == "postAction":
            self.post = args[0]
            return 0
        if name == "callScript":
            return self.run(args[0])
        if name == "gamePaused":
            return 1 if self.paused else 0
        if name == "getScaledTime":
            return scaled_time(args[0])
        if name == "playerHasItem":
            return self.counts[0]
        if name == "onePlayerHasItem":
            return self.counts[args[0]] if 0 <= args[0] < self.num_players else 0
        if name == "grantMission":
            self.mission1 |= 2
            return 1
        if name == "newWorld":
            self.pending = args[0]
            return 1
        if name == "demoRunning":
            return self.demo
        if name == "getHitPoints":
            return self.hp.get(args[0].lower(), 0)
        return 0

    def run(self, entry):
        self.scripts.append(entry)
        body = getattr(self, "%s_%s" % (self.level, entry), None)
        if body is None:
            return 0xFFFFFFFF
        return body() & 0xFFFFFFFF

    def frame(self):
        todo, self.front = self.front, []
        for name in todo:
            self.run(name)
        self.front, self.back = self.back, []

    def run_post(self):
        if self.post:
            name, self.post = self.post, ""
            self.run(name)

    def queued(self):
        return sorted(self.front + self.back)

    def gv(self, cell):
        return self.g.get(cell, 0)

    # drunarm -------------------------------------------------------------------
    def drunarm_prestart(self):
        for cell in (0x0, 0x4, 0x8, 0x10):
            self.g[cell] = 0
        return 0

    def drunarm_start(self):
        n = self.n
        if not n("getv", "war_triggeredonce"):
            n("hideMonster", "rallos")
        if n("getv", "war_foundShard"):
            n("hideMonster", "rallos")
        n("hideMonster", "rallos2")
        if n("getv", "war_killedRallos"):
            n("addDeferedCall", "removeRallos")
        self.g[0xc] = n("playerHasItem", "shardofwar")
        n("addDeferedCall", "shardCheckLoop")
        return 0

    def drunarm_trippedTrigger(self):
        n = self.n
        if n("getv", "war_triggeredonce"):
            n("callScript", "setFlag")
            return 0
        n("setSaveInhibit", 1)
        n("showMonster", "rallos")
        n("cutScene", "rallosintro")
        n("postAction", "setFlag")
        n("addDeferedCall", "rallosHPcheck")
        n("setv", "war_triggeredonce", 1)
        return 0

    def drunarm_setFlag(self):
        self.n("setCFlag", "rallos", 0, 1)
        return 0

    def drunarm_rallosHPcheck(self):
        n = self.n
        if n("getHitPoints", "rallos") <= 0:
            self.g[0x10] = 0
            n("addDeferedCall", "endDelay")
        else:
            n("addDeferedCall", "rallosHPcheck")
        return 0

    def drunarm_endDelay(self):
        n = self.n
        if not n("gamePaused"):
            self.g[0x10] = self.gv(0x10) + 1
        if n("getScaledTime", self.gv(0x10)) > 275:
            n("callScript", "playRallosRuns")
        else:
            n("addDeferedCall", "endDelay")
        return 0

    def drunarm_playRallosRuns(self):
        n = self.n
        n("showMonster", "rallos2")
        n("cutScene", "rallosruns")
        n("setSaveInhibit", 0)
        n("setv", "war_killedRallos", 1)
        n("postAction", "removeRallos")
        n("removeQuest", TEXT)
        return 0

    def drunarm_removeRallos(self):
        n = self.n
        n("killMonster", "rallos")
        n("hideMonster", "rallos")
        n("deleteMonster", "rallos")
        n("hideMonster", "rallos2")
        n("deleteMonster", "rallos2")
        return 0

    def drunarm_shardCheckLoop(self):
        n = self.n
        if not n("gamePaused"):
            self.g[0x8] = self.gv(0x8) + 1
        if self.gv(0x8) != 25:
            n("addDeferedCall", "shardCheckLoop")
            return 0
        self.g[0x8] = 0
        if not n("playerHasItem", "shardofwar") > self.gv(0xc):
            n("addDeferedCall", "shardCheckLoop")
            return 0
        self.g[0x10] = 0
        n("playGotItemSound")
        n("addHelpMessage", TEXT, TEXT)
        n("setv", "war_foundShard", 1)
        n("grantMission", 1)
        n("setv", "firstmissionever", 1)
        n("postAction", "endmission")
        self.g[0x4] = 0
        while self.gv(0x4) < 4:
            if n("onePlayerHasItem", self.gv(0x4), "shardofwar") > 1:
                n("removePlayerItem", self.gv(0x4), "shardofwar")
            self.g[0x4] += 1
        return 0

    def drunarm_endmission(self):
        self.n("addHelpMessage", TEXT, TEXT)
        self.n("soundSequence", "fx.lmp", "quest_complete.anm")
        return 0

    def _drunarm_gate(self):
        return bool(self.n("getv", "war_triggeredonce")) and not self.n("getv", "war_foundShard")

    def drunarm_portalMessage(self):
        if self._drunarm_gate():
            self.n("setInfo", TEXT)
        return 0

    def drunarm_if6896(self):
        return 0 if self._drunarm_gate() else 1

    def drunarm_newWorld1c57(self):
        self.n("newWorld", "strife")
        return 0

    def drunarm_return25eb(self):
        return 0

    def drunarm_callScricb6b(self):
        self.n("callScript", "portalMessage")
        return 0

    def drunarm_callScric1d7(self):
        self.n("callScript", "trippedTrigger")
        return 0

    # drunare -------------------------------------------------------------------
    def drunare_start(self):
        n = self.n
        n("hideMonster", "Rallos")
        n("hideMonster", "avatar")
        n("hideMonster", "knight")
        n("removeQuest", TEXT)
        n("getv", "killedAv")
        if n("getv", "killedAv"):
            n("autoPropSetState", "safety", 1)
        n("setMonsterVal", "avatar", 4, 2000)
        n("setMonsterVal", "knight", 4, 2000)
        return 0

    def drunare_incoming(self):
        n = self.n
        if not n("getv", "sawknights"):
            n("cutScene", "knights")
            n("postAction", "nosave")
            n("setv", "sawknights", 1)
        else:
            n("callScript", "setFlag")
        return 0

    def drunare_nosave(self):
        self.n("setSaveInhibit", 1)
        self.n("setCFlag", "avatar", 0, 1)
        return 0

    def drunare_setFlag(self):
        self.n("setCFlag", "avatar", 0, 1)
        return 0

    def drunare_knightDefeatedPause(self):
        n = self.n
        for k in ("knight1", "knight2", "knight3", "knight4"):
            if not n("getv", k):
                return 0
        self.g[0x4] = 0
        n("addDeferedCall", "knightDefeatedDelay")
        return 0

    def drunare_knightDefeatedDelay(self):
        n = self.n
        if not n("gamePaused"):
            self.g[0x4] = self.gv(0x4) + 1
        if n("getScaledTime", self.gv(0x4)) > 300:
            n("callScript", "knightDefeated")
        else:
            n("addDeferedCall", "knightDefeatedDelay")
        return 0

    def drunare_knightDefeated(self):
        if not self.n("getv", "sawcaz"):
            self.n("cutScene", "cazic")
            self.n("setv", "sawcaz", 1)
        return 0

    def drunare_bossDefeatedPause(self):
        self.g[0x0] = 0
        self.n("addDeferedCall", "bossDefeatedDelay")
        return 0

    def drunare_bossDefeatedDelay(self):
        n = self.n
        if not n("gamePaused"):
            self.g[0x0] = self.gv(0x0) + 1
        if n("getScaledTime", self.gv(0x0)) > 250 and not n("getv", "endsound"):
            n("setInfo", TEXT)
            n("soundSequence", "fx.lmp", "quest_complete.anm")
            n("setv", "endsound", 1)
            n("setv", "firstmissionever", 1)
            n("addDeferedCall", "bossDefeatedDelay")   # no jump after this block
        if n("getScaledTime", self.gv(0x0)) > 1500:
            n("callScript", "endmission")
        else:
            n("addDeferedCall", "bossDefeatedDelay")
        return 0

    def drunare_endmission(self):
        n = self.n
        if not n("getv", "killedAv"):
            n("postAction", "levelChange")
            n("cutScene", "bossdefeated")
            n("reapEnemies")
            n("removeQuest", TEXT)
            n("setv", "killedAv", 1)
        return 0

    def drunare_levelChange(self):
        self.n("grantMission", 1)
        self.n("newWorld", "hub2")
        return 0

    def _knight(self, var):
        self.n("setv", var, 1)
        self.n("callScript", "knightDefeatedPause")
        return 0

    def drunare_setv4d6b(self):
        return self._knight("knight1")

    def drunare_setv772a(self):
        return self._knight("knight2")

    def drunare_setv5138(self):
        return self._knight("knight3")

    def drunare_setvcccf(self):
        return self._knight("knight4")

    def drunare_callScria381(self):
        self.n("callScript", "bossDefeatedPause")
        return 0

    def drunare_return9d74(self):
        return self.n("getv", "killedAv")

    def drunare_newWorldbcf6(self):
        self.n("newWorld", "drundar")
        return 0

    def drunare_callScri8654(self):
        self.n("callScript", "incoming")
        return 0

    # strife --------------------------------------------------------------------
    SCOUTS = ("we_scout", "we_scout_2", "we_scout_3", "we_scout_4")

    def strife_preStart(self):
        self.n("preloadResource", "bust.lmp")
        self.g[0x144] = 0
        self.g[0x148] = 0
        self.g[0x14c] = self.n("getv", "sfe_step3counter")
        self.g[0x140] = 1
        self.g[0x15c] = 0
        return 0

    def strife_start(self):
        n = self.n
        self.g[0x140] = 0
        for shown, var, test in ((0, "sfe_step1Complete", False), (1, "sfe_step1Complete", True),
                                 (2, "sfe_step2Complete", True), (3, "sfe_step3Complete", True)):
            if bool(n("getv", var)) == test:
                for k, scout in enumerate(self.SCOUTS):
                    n("showMonster" if k == shown else "hideMonster", scout)
        if n("getv", "sfe_begunOrcCounter") and n("getv", "sfe_talkedtofirstscout"):
            n("callScript", "showOrcCounter")
        if n("getv", "sfe_begunShamanCounter") and self.gv(0x144) == 0:
            n("callScript", "showShamanCounter")
        if n("getv", "sfe_begunCatCounter") and self.gv(0x148) == 0:
            n("callScript", "showCatCounter")
        return 0

    def strife_step1InitScript(self):
        if not self.n("getv", "sfe_step1Complete"):
            self.g[0x144] = self.gv(0x144) + 1
        return 0

    def strife_step1DeathScript(self):
        if not self.n("getv", "sfe_step1Complete"):
            self.g[0x144] = self.gv(0x144) - 1
        return 0

    def strife_showOrcCounter(self):
        n = self.n
        if not n("getv", "sfe_begunOrcCounter"):
            n("setv", "sfe_begunOrcCounter", 1)
        if self.gv(0x140) == 0 and self.gv(0x144) == 0:
            n("setv", "sfe_begunOrcCounter", 0)
            n("setv", "sfe_step1Complete", 1)
            self.g[0x150] = 0
            n("addDeferedCall", "step1delay")
            return 0
        n("showBust", "bust_orc.tex", TEXT, self.gv(0x144), -1)
        n("addDeferedCall", "showOrcCounter")
        return 0

    def _delay(self, cell, then, again):
        n = self.n
        if not n("gamePaused"):
            self.g[cell] = self.gv(cell) + 1
        if n("getScaledTime", self.gv(cell)) > 100:
            then()
        else:
            n("addDeferedCall", again)
        return 0

    def strife_step1delay(self):
        return self._delay(0x150, lambda: self.n("callScript", "step1scene"), "step1delay")

    def strife_step1scene(self):
        self.n("setv", "sfe_begunOrcCounter", 0)
        self.n("cutScene", "step1com")
        self.n("postAction", "hideElf1")
        return 0

    def strife_hideElf1(self):
        self.n("showMonster", "we_scout_2")
        self.n("hideMonster", "we_scout")
        return 0

    def strife_step2InitScript(self):
        if not self.n("getv", "sfe_step2Complete"):
            self.g[0x148] = self.gv(0x148) + 1
        return 0

    def strife_step2DeathScript(self):
        if not self.n("getv", "sfe_step2Complete"):
            self.g[0x148] = self.gv(0x148) - 1
        return 0

    def strife_showShamanCounter(self):
        n = self.n
        if not n("getv", "sfe_begunShamanCounter"):
            n("setv", "sfe_begunShamanCounter", 1)
        if self.gv(0x140) == 0 and self.gv(0x148) == 0:
            n("setv", "sfe_begunShamanCounter", 0)
            n("setv", "sfe_step2Complete", 1)
            n("callScript", "step2pause")
            return 0
        n("showBust", "bust_shaman.tex", TEXT, self.gv(0x148), -1)
        n("addDeferedCall", "showShamanCounter")
        return 0

    def strife_step2pause(self):
        self.g[0x154] = 0
        self.n("addDeferedCall", "step2delay")
        return 0

    def _step2done(self):
        self.n("setv", "sfe_begunShamanCounter", 0)
        self.n("cutScene", "step2complete")
        self.n("postAction", "hideElf2")

    def strife_step2delay(self):
        return self._delay(0x154, self._step2done, "step2delay")

    def strife_hideElf2(self):
        self.n("hideMonster", "we_scout_2")
        return 0

    def strife_step3DeathScript(self):
        self.g[0x14c] = self.gv(0x14c) + 1
        self.n("setv", "sfe_step3counter", self.gv(0x14c))
        return 0

    def strife_showCatCounter(self):
        n = self.n
        if not n("getv", "sfe_begunCatCounter"):
            n("setv", "sfe_begunCatCounter", 1)
        if self.gv(0x140) == 0 and self.gv(0x14c) == 2:
            n("setv", "sfe_begunCatCounter", 0)
            n("setv", "sfe_step3Complete", 1)
            n("callScript", "step3pause")
            n("setSaveInhibit", 1)
            return 0
        n("showBust", "bust_catapult.tex", TEXT, 2 - self.gv(0x14c), -1)
        n("addDeferedCall", "showCatCounter")
        return 0

    def strife_step3pause(self):
        self.g[0x158] = 0
        self.n("addDeferedCall", "step3delay")
        return 0

    def _step3done(self):
        self.n("cutScene", "step3complete")
        self.n("postAction", "hide3")

    def strife_step3delay(self):
        return self._delay(0x158, self._step3done, "step3delay")

    def strife_hide3(self):
        self.n("hideMonster", "we_scout_3")
        self.n("setSaveInhibit", 0)
        return 0

    def _exitzone(self, cell, grant_text, arena):
        n = self.n
        if not n("demoRunning"):
            n("newWorld", arena)
            return 0
        if self.gv(cell) == 70:
            n("addHelpMessage", TEXT, TEXT)
        if self.gv(cell) > 150:
            n("grantMission", 1)
            n("newWorld", "hub")
        elif not n("gamePaused"):
            self.g[cell] = self.gv(cell) + 1
        n("addDeferedCall", "exitzone")        # the hub branch jumps here too
        return 0

    def strife_exitzone(self):
        return self._exitzone(0x15c, TEXT, "drunarm")

    def strife_callScri5a82(self):
        self.n("callScript", "exitzone")
        return 0

    def strife_return8821(self):
        return 0 if self.n("getv", "sfe_step3complete") else 1

    def strife_return523c(self):
        return 1

    def strife_callScri52e(self):
        self.n("callScript", "step1InitScript")
        return 0

    def strife_callScria77e(self):
        self.n("callScript", "step1DeathScript")
        return 0

    def strife_callScri8d4a(self):
        self.n("callScript", "step3DeathScript")
        return 0

    def strife_callScri9f82(self):
        self.n("callScript", "step2InitScript")
        return 0

    def strife_callScri4980(self):
        self.n("callScript", "step2DeathScript")
        return 0

    def _scout(self, name):
        self.n("startDialog", name, 0, 0)
        return 0

    def strife_startDia8851(self):
        return self._scout("we_scout")

    def strife_startDia30cc(self):
        return self._scout("we_scout_2")

    def strife_startDiad2e3(self):
        return self._scout("we_scout_3")

    def strife_startDiab722(self):
        return self._scout("we_scout_4")

    def strife_returne210(self):
        return 0 if self.n("getv", "sfe_talkedtofirstscout") else 1

    def strife_return1e8e(self):
        return 0 if self.n("getv", "sfe_talkedToSecondScout") else 1

    def strife_returnadae(self):
        return 0 if self.n("getv", "sfe_talkedToThirdScout") else 1

    def strife_returnc3ef(self):
        return 0 if self.n("getv", "sfe_talkedToFourthScout") else 1

    def strife_if9d85(self):
        if not self.n("getv", "sfe_metscout1"):
            self.n("startDialog", "we_scout", 0, 0)
            self.n("setv", "sfe_metscout1", 1)
        return 0

    def strife_if70a4(self):
        return 0 if self.n("getv", "sfe_talkedtofirstscout") else 1

    def strife_iff29(self):
        return 1 if self.n("getv", "sfe_talkedtofirstscout") else 0

    def strife_if3e90(self):
        return 0 if self.n("getv", "sfe_talkedToSecondScout") else 1

    def strife_if40b3(self):
        return 0 if self.n("getv", "sfe_talkedToThirdScout") else 1

    def strife_newWorld5d32(self):
        self.n("newWorld", "blood1")
        return 0

    def strife_setv176d(self):
        n = self.n
        n("setv", "sfe_talkedtofirstscout", 1)
        if not n("getv", "sfe_begunOrcCounter"):
            n("callScript", "showOrcCounter")
        n("addQuest", TEXT, TEXT)
        return 0

    def strife_setv23a8(self):
        n = self.n
        n("setv", "sfe_talkedToSecondScout", 1)
        n("trigger", "bridge1", 1)
        if not n("getv", "sfe_begunShamanCounter"):
            n("callScript", "showShamanCounter")
        return 0

    def strife_setv8921(self):
        n = self.n
        n("setv", "sfe_talkedToThirdScout", 1)
        n("trigger", "bridge2", 0)
        if not n("getv", "sfe_begunCatCounter"):
            n("callScript", "showCatCounter")
        return 0

    def strife_setv70e6(self):
        self.n("setv", "sfe_talkedToFourthScout", 1)
        self.n("trigger", "bridge3", 0)
        self.n("removeQuest", TEXT)
        return 0

    # drundar -------------------------------------------------------------------
    PILLAR = (("switchcod546", "return6d01", 1), ("switchco48ad", "returnb94e", 2),
              ("switchco1c6a", "returndf30", 3), ("switchco45bd", "return8615", 4),
              ("switchco8cc5", "return86a9", 5), ("switchcod516", "return71ee", 6),
              ("switchco6b46", "returnd0aa", 7), ("switchcoc9e3", "returnd4b", 8))

    def drundar_preStart(self):
        self.g[0x0] = 0
        self.g[0x28] = 0
        for cell in range(0x8, 0x28, 4):
            self.g[cell] = 0
        self.g[0x30] = 0
        return 0

    def drundar_start(self):
        n = self.n
        n("setMonsterVal", "ogreminiboss", 4, 3000)
        n("setMonsterVal", "ogreminiboss", 1, 500)
        n("setMonsterVal", "ogreminiboss", 5, 1000)
        n("setParticle")
        if not n("getv", "drun_intro"):
            n("setv", "drun_intro", 1)
        if n("getv", "drun_sawdoors"):
            n("autoPropSetState", "door", 1)
            n("autoPropSetState", "stairs", 1)
        if not n("getv", "drun_sawdoors") and n("getv", "drun_arenaMess"):
            n("addDeferedCall", "showSwitchCount")
        for k in range(1, 9):
            if n("getv", "pillar%don" % k):
                n("callScript", "switch%deffect" % k)
                self.g[0x0] = self.gv(0x0) + 1
        return 0

    def drundar_showSwitchCount(self):
        n = self.n
        n("showBust", "bust_switch.tex", TEXT, self.gv(0x0), -1)
        if self.gv(0x0) == 8:
            n("setSaveInhibit", 1)
            self.g[0x2c] = 0
            n("addDeferedCall", "doorsdelay")
        else:
            n("addDeferedCall", "showSwitchCount")
        return 0

    def drundar_doorsdelay(self):
        return self._delay(0x2c, lambda: self.n("callScript", "doors"), "doorsdelay")

    def drundar_doors(self):
        if not self.n("getv", "drun_sawdoors"):
            self.n("setSaveInhibit", 0)
            self.n("cutScene", "doors")
            self.n("setv", "drun_sawdoors", 1)
        return 0

    def _effect(self, k):
        n = self.n
        if n("gamePaused"):
            return 0                       # paused: the loop is not requeued
        cell = 0x4 + 4 * k
        self.g[cell] = self.gv(cell) + 1820
        if self.gv(cell) > 65535:
            self.g[cell] -= 65535
        n("sin1000")
        n("cos1000")
        n("addParticleOnObject")
        n("addDeferedCall", "switch%deffect" % k)
        return 0

    def drundar_exitzone(self):
        return self._exitzone(0x30, TEXT, "drunare")

    def drundar_arenaMessage(self):
        n = self.n
        if not n("getv", "drun_arenaMess"):
            n("addHelpMessage", TEXT, TEXT)
            n("setv", "drun_arenaMess", 1)
            n("addDeferedCall", "showSwitchCount")
            n("addQuest", TEXT, TEXT)
        return 0

    def drundar_newWorld5d32(self):
        self.n("newWorld", "blood1")
        return 0

    def drundar_return56e0(self):
        return 1 if self.gv(0x0) == 8 else 0

    def drundar_callScri5a82(self):
        self.n("callScript", "exitzone")
        return 0

    def drundar_callScri28d3(self):
        self.n("callScript", "arenaMessage")
        return 0

    def __getattr__(self, attr):
        # drundar switchNeffect, switch actions and their keys
        if attr.startswith("drundar_switch") and attr.endswith("effect") and attr[14:-6].isdigit():
            k = int(attr[14:-6])
            return lambda: self._effect(k)
        for action, key, k in self.PILLAR:
            if attr == "drundar_" + action:
                def act(k=k):
                    self.g[0x0] = self.gv(0x0) + 1
                    self.n("setv", "pillar%don" % k, 1)
                    self.n("callScript", "switch%deffect" % k)
                    return 0
                return act
            if attr == "drundar_" + key:
                return lambda k=k: 0 if self.n("getv", "pillar%don" % k) else 1
        raise AttributeError(attr)


# ---------------------------------------------------------------- scenario milestones
# Frame (count of script_runDeferred calls) at which each named native first appears,
# from the scenarios in the difftest. Equal on the model and the original.
MILESTONES = {
    "drunarm": {"grant_after_pickup": 16, "outro_after_kill": 303, "outro_after_grant": 277,
                "outro_after_kill_no_shard": 279, "outro_after_queue": 277,
                "outro_after_grant_same_step": 276},
    "drunare": {"cazic_after_fourth_death": 303, "end_after_death": 878},
    "strife": {"step1_after_queue": 102, "step2_after_queue": 102, "step3_after_queue": 102},
    "drundar": {"doors_after_queue": 102},
}

# game_getHubName on (evil, decision, mission 1 complete) of record 0, difficulty 0.
HUB_NAMES = {(0, 1, 1): "hub", (1, 1, 1): "hub2", (0, 1, 0): "hub", (1, 1, 0): "hub"}

# Player1_ctor over a level's markers in record order: (level, previous level) ->
# (final g_playerStartRank, `from` value of the marker that took last, spawn searches).
MARKERS = {
    ("strife", "blood1"): (1, "", 4),
    ("strife", "drunarm"): (2, "drunarm", 8),
    ("drundar", "blood1"): (1, "", 4),
    ("drundar", "drunare"): (1, "", 4),
    ("drunarm", "strife"): (1, "", 4),
    ("drunare", "drundar"): (1, "", 4),
}
# Creature_onDeath(c, 0) on the record's properties: script started (with the
# selected object set to c) and item dropped. With quiet = 1 the drop is skipped.
DEATHS = {
    ("drunarm", "RalosZek"): [("drop", "shardofwar")],
    ("drunare", "RalosZek"): [],
    ("drunare", "CazicAvatar"): [("script", "callScria381", True)],
    ("drunare", "UndeadKnight1"): [("script", "setv4d6b", True), ("drop", "rejuvpotion")],
    ("drunare", "UndeadKnight2"): [("script", "setv772a", True), ("drop", "healingpotion")],
    ("drunare", "UndeadKnight3"): [("script", "setv5138", True), ("drop", "rejuvpotion")],
    ("drunare", "UndeadKnight4"): [("script", "setvcccf", True), ("drop", "healingpotion")],
    ("strife", "Orc2Shaman"): [("script", "callScri4980", True)],
}
# The same, picked by record name (class, `name` property; "" for none). Covers every
# DEATHS row and the records DEATHS left out (rallos2, the second shaman).
DEATHS_BY_NAME = {
    ("drunarm", "RalosZek", "rallos"): [("drop", "shardofwar")],
    ("drunarm", "RalosZek", "rallos2"): [],
    ("drunare", "RalosZek", "rallos"): [],
    ("drunare", "CazicAvatar", "avatar"): [("script", "callScria381", True)],
    ("drunare", "UndeadKnight1", "knight"): [("script", "setv4d6b", True), ("drop", "rejuvpotion")],
    ("drunare", "UndeadKnight2", "knight"): [("script", "setv772a", True), ("drop", "healingpotion")],
    ("drunare", "UndeadKnight3", "knight"): [("script", "setv5138", True), ("drop", "rejuvpotion")],
    ("drunare", "UndeadKnight4", "knight"): [("script", "setvcccf", True), ("drop", "healingpotion")],
    ("strife", "Orc2Shaman", "orcshamanboss1"): [("script", "callScri4980", True)],
    ("strife", "Orc2Shaman", "orcshamanboss2"): [("script", "callScri4980", True)],
}
