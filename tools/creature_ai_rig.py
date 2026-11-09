"""Synthetic ee_emu rig for creature run/setState decision probes, US v2.00.

The class run (and the object generator 0x1509d0) execute in ee_emu. Every
other callee is a recording stub. Selected boolean/count/pointer queries are
answered from an explicit answer list so that a caller can walk the decision
tree. Creature_run 0x112948 and Creature_updateActive 0x10c0f0 answer from the
context (base / active), so both early exits of the class tick can be run.
Nothing here loads a level, an animation or a live actor.
"""
from ee_emu import EE, float_to_raw, raw_to_float

RAND = 0x1509D0
SKILLS = 0x41B170
POOL_NEW = 0x14FDB8
PROCESS, BASE_RUN, ACTIVE = 0x110D30, 0x112948, 0x10C0F0
STEP, KNOCK, PICK = 0x1162B0, 0x115EB8, 0x10DED0

NAMES = {
    0x10C0F0: "updateActive", 0x10D4E0: "getGuardPoint",
    0x10D5E8: "allyInLineOfFire", 0x10D800: "countAlliesNear",
    0x10CF78: "cone", 0x10C810: "canSeeObj", 0x10DED0: "pickTarget",
    0x10E2C0: "pickAlly", 0x10E658: "sight", 0x10EED8: "away",
    0x10F008: "corpse", 0x10F190: "wounded", 0x10F2C8: "dropLoot",
    0x1108A0: "deadUpdate", 0x110D30: "processDamage", 0x112948: "baseRun",
    0x113C48: "moveBy", 0x1143E8: "moveToTarget", 0x114510: "moveTo",
    0x115EB8: "knockback", 0x1162B0: "stepAnim", 0x1175C0: "aimAngleAtTarget",
    0x1187E0: "turn", 0x118840: "angleToTarget", 0x1188A0: "angleAllyToTarget",
    0x118CB0: "inArcRange", 0x118CF0: "seeEdge", 0x118D40: "see",
    0x118E90: "targetAttacking", 0x118F08: "blockedByTarget",
    0x118F90: "targetCharging", 0x119038: "targetRunning",
    0x1190E8: "targetKnockedDown", 0x119258: "alliesNearTarget",
    0x119128: "allySeesTarget", 0x119180: "inGuardSpot",
    0x1195E0: "notRooted", 0x1195F0: "attackReady", 0x119608: "notStunned",
    0x119618: "pickWanderDest", 0x1196E8: "hitAtReach",
    0x119850: "hitInArcEdge", 0x119938: "hitInArc",
    0x119A20: "hitTargetOrPlayer", 0x119B58: "hitAll",
    0x119E38: "settle", 0x119E98: "moveToAlly", 0x119F08: "flee",
    0x119F38: "moveToDest", 0x11A1E0: "clearPath", 0x11A920: "aimAngleAt",
    0x11AAF8: "leadTargetPoint", 0x14F200: "objDelete", 0x14FDB8: "poolNew",
    0x100D54: "lootGenerate", 0x100BA0: "lootNamed", 0x161270: "damageInRadius",
    0x10BB08: "turnToward", 0x118A58: "stun", 0x11A838: "addSpell",
    0x108970: "countInBox", 0x1155E0: "moveToDirect", 0x115910: "fleeFrom",
    0x10A9C0: "filterState", 0x10BEB8: "onDeath",
    0x26D7E4: "hasShield", 0x2BC7C8: "canBlock",
}

# Queries whose result the class tests. Domain: values the walk tries.
BOOL = (0, 1)
QUERY_DOMAIN = {
    "sight": BOOL, "see": BOOL, "cone": BOOL, "away": BOOL,
    "notRooted": BOOL, "attackReady": BOOL, "notStunned": BOOL,
    "targetAttacking": BOOL, "blockedByTarget": BOOL,
    "targetCharging": BOOL, "targetRunning": BOOL, "targetKnockedDown": BOOL,
    "allyInLineOfFire": BOOL, "inGuardSpot": BOOL, "allySeesTarget": BOOL,
    "moveToDest": BOOL, "canSeeObj": BOOL, "seeEdge": BOOL,
    "inArcRange": BOOL, "hitAtReach": BOOL,
    # Counts: every value at and around the thresholds the classes test
    # (> 0, > 1, > 2, == 0, < 2, >= 1 for allies; < 3 for the box count).
    "alliesNearTarget": (0, 1, 2, 3), "countAlliesNear": (0, 1, 2, 3),
    "countInBox": (0, 2, 3, 4), "corpse": "ptr", "wounded": "ptr",
    "hasShield": BOOL, "canBlock": BOOL,
}


def f(raw):
    return round(raw_to_float(raw & 0xFFFFFFFF), 4)


class Rig:
    """One synthetic creature of a class, with one target object."""

    def __init__(self, executable, cls, state, seed, target=True, ev=0,
                 anim=0, clock=100, deadline=0, fields=(), answers=(),
                 queries=None, ally=False, hp=(100.0, 100.0), base=0, active=1):
        self.emu = emu = EE(executable)
        self.cls = cls
        self.obj = emu.alloc(cls["size"] + 0x40)
        self.definition = emu.alloc(0x400)
        self.target = emu.alloc(0x500)
        self.thandle = emu.alloc(0x10)
        self.ally = emu.alloc(0x500)
        self.ahandle = emu.alloc(0x10)
        self.extra = emu.alloc(0x500)       # corpse / wounded-ally answer
        mem = emu.mem
        mem.w32(self.thandle + 0xC, self.target)
        mem.w32(self.ahandle + 0xC, self.ally)
        mem.w32(self.obj + 0x48, cls["vtable"])
        mem.w32(self.obj + 0x24, self.definition)
        mem.w32(self.obj + 0x44, seed)
        mem.w32(self.obj + 0x234, self.thandle if target else 0)
        mem.w32(self.obj + 0x238, self.ahandle if ally else 0)
        mem.w16(self.obj + 0x232, state)
        mem.w16(self.obj + 0x11A, anim)
        mem.w32(self.obj + 0x300, clock)
        mem.w32(self.obj + 0xF4, deadline)
        mem.wf32(self.obj + 0x1C, 20.0)
        mem.wf32(self.obj + 0x20, 72.0)
        mem.wf32(self.target + 0x1C, 20.0)
        mem.wf32(self.target + 0x20, 72.0)
        mem.wf32(self.target + 0x10, 50.0)
        mem.wf32(self.obj + 0x228, float(hp[0]))      # hit points
        mem.wf32(self.obj + 0x22C, float(hp[1]))      # maximum hit points
        mem.w32(self.target + 0x48, cls["vtable"])
        mem.w32(self.ally + 0x48, cls["vtable"])
        mem.w32(self.extra + 0x48, cls["vtable"])
        for offset in range(0, 0x400, 4):
            mem.w32(self.definition + offset, 0x700000 + offset)
        # Fake holder and skill objects with recording tables. A virtual
        # entry at table offset o is (s16 this-adjust, function) at o / o+4;
        # each function is a stub named holder+0xNN / skill+0xNN.
        self.code = {}
        self.holder = self._recording_object("holder", 0)
        if cls.get("holder") is not None:
            mem.w32(self.obj + 0x50, self.holder)
        # The skill pointer table (SKILL[i] at 0x41b170 + 4i) is filled at
        # boot; here every entry points at one recording skill object.
        self.skill = self._recording_object("skill", 0x60)
        for index in range(128):
            mem.w32(SKILLS + 4 * index, self.skill)
        for size, offset, value in fields:
            if size == "f":
                mem.wf32(self.obj + offset, value)
            else:
                getattr(mem, "w%d" % size)(self.obj + offset, value)
        mem.w32(0x404464, 0x12345678)
        self.answers = list(answers)
        self.asked = []
        self.queries = QUERY_DOMAIN if queries is None else queries
        emu.stub(POOL_NEW, function=lambda e: e.alloc(0x600), name="poolNew")
        emu.stub(ACTIVE, ret=active)
        emu.stub(BASE_RUN, ret=base)
        emu.stub(STEP, ret=ev)
        for address, name in NAMES.items():
            if name in self.queries:
                emu.stub(address, function=self._answer(name), name=name)

    def _recording_object(self, label, table_at):
        emu, mem = self.emu, self.emu.mem
        obj = emu.alloc(0x200)
        table = emu.alloc(0x200)
        code = emu.alloc(0x200)
        self.code[label] = code
        mem.w32(obj + table_at, table)
        for offset in range(4, 0x200, 4):
            # The function word of a virtual entry sits at `offset`; the
            # word before it is read as the this-adjust (ignored by stubs).
            # Names use the function-word offset, as the class notes do.
            mem.w32(table + offset, code + offset)
            emu.stub(code + offset, ret=0, name="%s+0x%x" % (label, offset))
        return obj

    def entry_returns(self, label, offset, value):
        """Make the function at table word `offset` return `value`."""
        self.emu.stub(self.code[label] + offset, ret=value,
                      name="%s+0x%x" % (label, offset))

    def _answer(self, name):
        def answer(emu):
            index = len(self.asked)
            value = self.answers[index] if index < len(self.answers) else 0
            if self.queries[name] == "ptr" and value:
                value = self.extra
            self.asked.append(name)
            return value
        return answer

    def run(self, max_steps=200000):
        emu = self.emu
        emu.follow = {self.cls["run"], RAND}
        emu.reset_log()
        emu.call(self.cls["run"], self.obj, max_steps=max_steps)
        return emu.calls

    def name(self, call):
        if call.target == self.cls["set"]:
            return "set"
        if call.name:
            return call.name
        return NAMES.get(call.target, "0x%x" % call.target)
