"""Reference decision models for mission 1-3 creature run functions (US v2.00).

Each model restates, as code, the per-tick decision order of one class run
function: which query it asks (with near/far/facing/arc), what it requests
through slot 27, which hit helper it calls with which flags, and which own
generator draws it makes. The models were authored from the static class
notes in docs/monsters-2.md; tools/difftest_creature_ai_m1_3.py executes the
original run functions in ee_emu and compares. Corrections found by the
comparison are listed in docs/creature-ai-m1-3.md.

Counts below are object-record counts only (no positions or properties).
"""
from ref_core import Lcg

LEVELS = ("blood1", "strife", "drundar", "drunare", "drunarm", "innovat1",
          "inmine1", "inmine2", "innovat2", "islc1", "islc2")

# Creature records per level: type string -> (count, pool size, constructor).
CREATURES = {
    "blood1": {"Kobold": (118, 0x3D0, 0x27F0C0), "Koboldtough": (8, 0x3D0, 0x27F0C0),
               "koboldshaman": (5, 0x3D0, 0x27F0C0), "WarWraith": (9, 0x468, 0x2C07A8)},
    "strife": {"Orc2Archer": (20, 0x488, 0x2A0954), "Orc2Leader": (2, 0x488, 0x2A0954),
               "Orc2Leader1": (2, 0x488, 0x2A0954), "Orc2Shaman": (2, 0x488, 0x2A0954),
               "Orc2Soldier": (43, 0x488, 0x2A0954), "Catapult": (2, 0xFC, 0x24D440)},
    "drundar": {"GoblinArcher": (23, 0x498, 0x26A624), "GoblinRecruit": (9, 0x498, 0x26A624),
                "GoblinSoldier": (39, 0x498, 0x26A624), "Ogre": (14, 0x468, 0x29FAD0)},
    "drunare": {"UndeadKnight1": (1, 0x478, 0x271C70), "UndeadKnight2": (1, 0x478, 0x271C70),
                "UndeadKnight3": (1, 0x478, 0x271C70), "UndeadKnight4": (1, 0x478, 0x271C70),
                "CazicAvatar": (1, 0x3E8, 0x24A670), "RalosZek": (1, 0x480, 0x2C1F94)},
    "drunarm": {"GladiatorBare": (82, 0x480, 0x2BAFB4), "RalosZek": (2, 0x480, 0x2C1F94),
                "Catapult": (4, 0xFC, 0x24D440)},
    "innovat1": {"clockworkcutter": (23, 0x500, 0x24E124), "clockworkhammer": (29, 0x500, 0x24E124),
                 "Rat": (36, 0x448, 0x2547FC), "Seagull": (30, 0x448, 0x2547FC)},
    "inmine1": {"clockworkcutter": (23, 0x500, 0x24E124), "clockworkhammer": (23, 0x500, 0x24E124),
                "Droid": (30, 0x3D0, 0x27B840)},
    "inmine2": {"clockworkcutter": (20, 0x500, 0x24E124), "clockworkhammer": (14, 0x500, 0x24E124)},
    "innovat2": {"IronGuardian": (1, 0x3E8, 0x27A00C), "Rat": (8, 0x448, 0x2547FC),
                 "Seagull": (12, 0x448, 0x2547FC)},
    "islc1": {"Froglock": (46, 0x468, 0x263E1C), "Crab": (39, 0x448, 0x2547FC)},
    "islc2": {"Amphian": (37, 0x3C8, 0x234584), "Crab": (44, 0x448, 0x2547FC),
              "SeaMonster": (2, 0x3D0, 0x2A428C)},
}
RECORDS = {"blood1": 363, "strife": 283, "drundar": 270, "drunare": 39,
           "drunarm": 302, "innovat1": 297, "inmine1": 213, "inmine2": 118,
           "innovat2": 71, "islc1": 262, "islc2": 255}

# Records of (level, type) whose property keys include every key in `with`
# and none in `without` (key names only; no values are kept).
KEY_COUNTS = (
    ("drundar", "Ogre", ("miniboss",), (), 1),
    ("islc2", "SeaMonster", ("miniboss",), (), 2),
    ("drunarm", "RalosZek", ("visualarc", "dropitem"), ("wait",), 1),
    ("drunarm", "RalosZek", ("wait",), ("visualarc", "dropitem"), 1),
)

# Class run/setState entry points and the synthetic layout the rig needs.
CLASSES = {
    "Kobold": dict(run=0x27F52C, set=0x27FF6C, vtable=0x515EF0, size=0x3D0,
                   skills=(0x41B24C,)),
    "WarWraith": dict(run=0x2C0C2C, set=0x2C1648, vtable=0x517F80, size=0x468, holder=0x3D0),
    "Orc": dict(run=0x2A1848, set=0x2A323C, vtable=0x50FFD0, size=0x488, holder=0x3D8),
    "Goblin": dict(run=0x26B27C, set=0x26CCFC, vtable=0x510260, size=0x498, holder=0x3E8),
    "Ogre": dict(run=0x29FE50, set=0x2A060C, vtable=0x517220, size=0x468, holder=0x3C8),
    "Warrior": dict(run=0x2BB640, set=0x2BC320, vtable=0x517E38, size=0x480, holder=0x3D0),
    "Clockwork": dict(run=0x24E758, set=0x24F90C, vtable=0x514300, size=0x500, holder=0x3D0),
    "Droid": dict(run=0x27BA78, set=0x27C0A0, vtable=0x515DA8, size=0x3D0),
    "IronGuardian": dict(run=0x27A390, set=0x27B550, vtable=0x515C60, size=0x3E8),
    "Froglock": dict(run=0x264314, set=0x265150, vtable=0x510780, size=0x468, holder=0x3C8),
    "Amphian": dict(run=0x23483C, set=0x2350D0, vtable=0x512DA0, size=0x3C8),
    "SeaMonster": dict(run=0x2A44A8, set=0x2A4AA4, vtable=0x517368, size=0x3D0),
}

DMG = (11, 22, 33)          # synthetic +0xd0/+0xd2/+0xd4 in every probe
X7FFF = 0x7FFF


class M:
    """Model context: same answers as the emulator's query stubs."""

    def __init__(self, ctx, answers):
        self.c = ctx
        self.answers = list(answers)
        self.i = 0
        self.events = []
        self.rng = Lcg(ctx["seed"])

    # queries
    def ask(self, *event):
        self.events.append(event)
        value = self.answers[self.i] if self.i < len(self.answers) else 0
        self.i += 1
        return value

    def see(self, near, far, arc, ray=0, facing=0):
        return self.ask("see", float(near), float(far), facing, arc, ray)

    def cone(self, near, far, arc, facing=0):
        return self.ask("cone", float(near), float(far), facing, arc)

    def sight(self, force=0):
        return self.ask("sight", force)

    def q(self, name, *args):
        return self.ask(name, *args)

    # actions
    def act(self, *event):
        self.events.append(event)

    def set(self, state):
        self.events.append(("set", state))

    def hit(self, near, far, arc, flags, dmg=DMG, facing=0, name="hitInArc"):
        self.act(name, float(near), float(far), facing, arc, *dmg, flags)

    def hit_all(self, near, far, arc, flags, dmg=DMG, facing=0):
        self.hit(near, far, arc, flags, dmg, facing, "hitAll")

    def hit_reach(self, reach, flags, dmg=DMG):
        """hitAtReach's result is tested by the wraith, so it is a query."""
        return self.ask("hitAtReach", float(reach), *dmg, flags)

    def rand(self):
        return self.rng.draw()

    # context
    @property
    def state(self):
        return self.c["state"]

    @property
    def target(self):
        return self.c["target"]

    @property
    def ev(self):
        return self.c["ev"]

    @property
    def anim(self):
        return self.c["anim"]

    def field(self, offset):
        return self.c["fields"].get(offset, 0)

    @property
    def clock(self):
        return self.c["clock"]

    @property
    def deadline(self):
        return self.c["deadline"]

    @property
    def hp(self):
        """(hit points +0x228, maximum +0x22c); the rig default is 100/100."""
        return tuple(self.c.get("hp") or (100.0, 100.0))
