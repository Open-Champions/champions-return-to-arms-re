"""Per-class decision models (see ref_creature_ai_m1_3 for the M context).

Each function restates one run function's per-tick decision order for the
synthetic probe: m.target / m.ev / m.anim / m.clock / m.deadline / fields.
"""
X = 0x7FFF


class TickEnd(Exception):
    """A model raises this where the class run returns early."""


def entry(m):
    """processDamage, then Creature_run 0x112948 (a nonzero result ends the
    tick), then Creature_updateActive 0x10c0f0 (a zero result ends it)."""
    m.act("processDamage")
    m.act("baseRun")
    if m.c.get("base", 0):
        raise TickEnd
    m.act("updateActive")
    if not m.c.get("active", 1):
        raise TickEnd


def head(m, knock, holder=False, ally=False, step=1.0):
    entry(m)
    m.act("stepAnim", step)
    m.act("knockback", knock)
    m.act("pickTarget", 0)
    if ally:
        m.act("pickAlly")


# ---------------------------------------------------------------- Kobold
def kobold(m):
    v = m.field(0x3CC)
    head(m, 1.0, ally=True)
    s = m.state
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.q("away") or m.clock > m.deadline:
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(3)
        elif m.clock > m.deadline:
            m.set(0)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif v == 1:
            if m.q("alliesNearTarget", 24.0) > 2:
                m.set(5)
            elif m.q("targetCharging") and m.see(0, 24, 6000):
                m.set(7)
            elif m.see(0, 24, 6000):
                m.set(5)
            elif m.see(0, 24, X):
                m.act("turn")
            else:
                m.act("moveToTarget")
        elif v == 2:
            if m.see(0, 24, 6000) or m.see(0, 164, 5000):
                m.set(5)
            elif m.see(0, 164, X):
                m.act("turn")
            else:
                m.act("moveToTarget")
        else:
            if m.see(0, 24, 6000):
                m.set(5)
            elif m.see(0, 24, X):
                m.act("turn")
            else:
                m.act("angleAllyToTarget")
                if m.q("inGuardSpot"):
                    m.set(5)
                elif m.q("allySeesTarget"):
                    m.act("getGuardPoint")
                    m.act("moveTo")
                else:
                    m.act("moveToTarget")
    elif s == 5:
        if not m.target:
            m.set(0)
            return
        m.act("turn")
        if m.see(0, 24, 6000):
            m.set(6)
        elif v == 1:
            if m.q("notRooted") and not m.q("alliesNearTarget", 24.0) > 2:
                m.set(3)
        elif v == 2:
            if m.q("corpse"):
                m.set(8)
            elif m.q("notRooted") and not m.see(0, 200, 5000):
                m.set(3)
        else:
            if m.q("notRooted"):
                if not m.c["ally"]:
                    m.set(3)
                else:
                    m.act("angleAllyToTarget")
                    if not m.q("inGuardSpot"):
                        m.set(3)
    elif s in (6, 7):
        if m.target and m.ev & 1:
            m.hit(0, 24, 6000, (0x440008 if v == 1 else 8) if s == 6 else 0x80001)
        if s == 7 and m.target and m.ev & 2:
            m.hit(0, 24, 6000, 1)
        if m.target:
            m.act("turn")
        if not m.anim & 8:
            m.set(5)
    elif s == 8:
        if m.ev & 1:
            corpse = m.q("corpse")
            wounded = m.q("wounded")
            if corpse:
                m.act("revive")
            elif wounded:
                # SpellHealing absent (stub 0): cast Healing through the
                # skill at 0x41b24c, table word +0x14, then link it to the ally.
                m.act("findSpellByType")
                m.act("skill+0x14")
                m.act("addSpell")
        if not m.anim & 8:
            m.set(5)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(3)
    elif s == 0x14:
        m.act("deadUpdate", 20.0)
    elif s == 0x17:
        if not m.anim & 0x10:
            m.set(3)
    else:
        m.set(0)


KOBOLD_VARIANTS = ({0x3CC: (8, 0)}, {0x3CC: (8, 1)}, {0x3CC: (8, 2)})
ALL = tuple(s for s in range(0x18) if s != 9)

SPECS = {
    "Kobold": dict(model=kobold, variants=KOBOLD_VARIANTS, states=ALL,
                   evs=(0, 1, 2, 3), allies=(0, 1)),
}


# ---------------------------------------------------------------- WarWraith
def warwraith(m):
    fade = m.field(0x3C8)
    s = m.state
    entry(m)
    m.act("stepAnim", 1.0)
    if s != 0x14:
        m.act("pickTarget", 0)
    m.act("knockback", 0.0)
    if fade >= 99:
        m.act("turn")
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.clock > m.deadline:
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(0)
        else:
            m.act("moveToDest")
    elif s in (3, 5):
        if s == 3 and not m.target:
            m.set(0)
        elif m.see(0, 20, 6000):
            m.set(7 if m.clock > m.field(0x3CC) else 6)
        elif s == 3:
            m.see(0, 20, X)
            m.act("turn")
        elif m.q("notRooted"):
            m.set(3)
    elif s in (6, 7):
        if m.target and m.ev & 1:
            if s == 7:
                m.act("skill+0x5c")
                m.hit_reach(36, 0x404)
            else:
                m.hit_reach(36, 8)
        if m.target:
            m.act("turn")
        if not m.anim & 8:
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x11:
        if m.clock > m.deadline:
            m.set(3)
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(0)
    elif s == 0x14:
        # A tick that starts with fade >= 100 deletes the object (99 does not:
        # executed at 98/99/100), otherwise one particle: an angle draw and a
        # unit-ball rejection point (three draws a try).
        if fade >= 100:
            m.act("objDelete")
        else:
            m.rand()
            m.rng.in_unit_sphere()


# ---------------------------------------------------------------- Orc
def orc(m):
    v = m.field(0x478)
    s = m.state
    melee = v <= 3
    head(m, 0.4)
    if s in (0, 1, 2):
        forced = v == 4 and m.sight(1)
        if forced or m.sight(0):
            # state 2 answers a plain sight with 0, a forced archer sight with 3
            m.set(0 if s == 2 and not forced else 3)
        elif s == 0:
            if m.clock > m.deadline or m.q("away"):
                m.set(1)
        else:
            if not m.q("moveToDest") and s == 2:
                m.set(0)
    elif s == 3:
        if not m.target:
            m.set(0)
        elif melee:
            if m.see(0, 30, 6000):
                m.set(6)
            elif m.see(0, 30, X):
                m.act("turn")
            elif v in (1, 2, 3) and m.q("alliesNearTarget", 30.0) > 0:
                m.set(0x17)
            elif v == 0 and m.q("alliesNearTarget", 30.0) > 1:
                m.set(0x17)
            elif v in (0, 1) and m.rand() % 30 == 0 and m.q("countInBox") < 3:
                m.set(4)
            else:
                m.act("moveToTarget")
        elif v == 4:
            if m.see(0, 80, X):
                m.set(0x10)
            elif m.see(0, 400, 6000, 1):
                m.set(6)
            else:
                m.act("moveToTarget")
        else:
            if m.see(0, 400, 6000, 1):
                m.set(6)
            elif m.see(0, 30, 6000):
                m.set(7)
            elif m.see(0, 6000, X):
                m.act("turn")
            else:
                m.act("moveToTarget")
    elif s == 4:
        if not m.target:
            m.set(0)
            return
        if m.see(0, 30, 6000):
            m.set(6)
        elif m.see(0, 30, X):
            m.act("turn")
        m.rand()
        m.act("moveToTarget")
    elif s == 5:
        if (melee and m.see(0, 30, 6000)) or (not melee and m.see(0, 400, 6000, 1)):
            m.set(6)
        if m.q("notRooted"):
            m.set(3)
    elif s == 6:
        if melee:
            if m.target:
                if m.ev & 3:
                    m.hit_reach(36, 0x40008)
                    if m.ev & 1 and m.rand() % 5 == 0:
                        m.set(3)
                if m.anim & 8:
                    m.act("turn")
        else:
            if m.target:
                m.act("leadTargetPoint")
            if m.target and m.ev & 1 and v == 4:
                m.rng.in_unit_sphere()
                m.rand()
                m.act("poolNew")
            elif m.target and m.ev & 1:
                corpse = wounded = 0
                if not m.see(0, 80, X):
                    corpse = m.q("corpse")
                    wounded = m.q("wounded")
                if corpse:
                        m.act("revive")
                elif wounded:
                    m.act("skill+0x14")
                    m.act("addSpell")
                elif m.rand() % 3 == 0:
                    m.act("poolNew")
                else:
                    m.act("skill+0x14")
        # 0x2a2c78-0x2a2cf0: the stand-after-swing counter +0xf4 counts
        # down only once the clip has ended, but is tested every frame.
        left = m.deadline if m.anim & 8 else m.deadline - 1
        if left <= 0:
            if v == 5:
                m.rand()
                m.set(0x17)
            else:
                m.set(3)
    elif s == 7:
        if m.ev & 1:
            m.hit(0, 30, 6000, 1)
        if not m.anim & 8:
            m.set(0x17)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x11:
        if m.clock > m.deadline:
            m.set(3)
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(0)
    elif s == 0x14:
        m.act("deadUpdate", 30.0)
    elif s == 0x17:
        if not m.target:
            m.set(0)
        elif v == 5:
            if m.clock > m.field(0x47C):
                m.set(3)
            elif m.see(0, 30, 6000):
                m.set(7)
            elif m.see(0, 6000, X):
                # 2026-11-09, executed with +0x47c at the clock: an any-angle
                # sight within 6000 adds a turn before the common one.
                m.act("turn")
        elif v == 4:
            pass
        elif v in (1, 2, 3):
            if m.see(0, 30, X) or m.q("alliesNearTarget", 30.0) == 0:
                m.set(3)
        else:
            if m.see(0, 30, 6000) or m.clock > m.deadline or m.q("alliesNearTarget", 30.0) < 2:
                m.set(3)
        if m.target:
            m.act("turn")


# ---------------------------------------------------------------- Goblin
def goblin(m):
    role = m.field(0x3D4)
    s = m.state
    head(m, 0.5, ally=(role == 5))
    if s in (0, 1, 2):
        archer = role == 4 and m.sight(1)
        if archer:
            m.set(3 if s == 0 else 0)
        elif m.sight(0):
            m.set(3 if s in (0, 1) else 0)
        elif s == 0:
            if m.q("away"):
                m.set(1)
        elif not m.q("moveToDest") and s == 2:
            m.set(0)
    elif s == 3:
        if not m.target:
            m.set(0)
            return
        if role == 4:
            if m.see(0, 80, X):
                m.set(0x10)
            elif m.see(0, 400, 6000, 1):
                m.set(7)
            else:
                m.act("moveToTarget")
        if role == 5:
            if m.see(0, 60, X):
                m.set(0x10)
            elif m.see(0, 400, 6000, 1):
                m.set(8)
            else:
                m.act("moveToTarget")
            return
        if m.see(0, 30, 6000):
            if m.q("hasShield") and m.q("targetAttacking") and m.rand() % 3 == 0:
                m.set(0x11)
            else:
                m.set(6)
        elif m.see(0, 30, X):
            m.act("turn")
        elif role > 0 and m.q("allyInLineOfFire"):
            m.set(0x17)
        elif m.rand() % 30 == 0 and m.q("countInBox") < 3:
            m.set(4)
        else:
            m.act("moveToTarget")
    elif s == 4:
        if not m.target:
            m.set(0)
        elif m.see(0, 30, 6000):
            m.set(6)
        else:
            m.rand()
            m.act("moveToTarget")
    elif s == 5:
        if not m.target:
            m.set(3)
        elif role in (4, 5):
            if m.see(0, 400, 6000, 1):
                m.set(7 if role == 4 else 8)
            elif m.q("notRooted"):
                m.set(3)
        elif m.see(0, 30, 6000):
            m.set(6)
        elif m.q("notRooted"):
            m.set(3)
    elif s == 6:
        if m.target and m.ev & 3:
            m.hit_reach(36, 0x40008)
            if m.ev & 1 and m.rand() % 5 == 0:
                m.set(3)
        if m.anim & 8:
            if m.target:
                m.act("turn")
        else:
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x11:
        if m.clock > m.deadline:
            m.set(3)
    elif s == 0x12:
        if not m.anim & 0x30:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(0)
    elif s == 0x14:
        m.act("deadUpdate", 20.0)
    elif s == 0x17:
        if not m.target:
            m.set(0)
            return
        if role == 5:
            if m.see(0, 60, X):
                m.set(0x10)
            elif m.clock > m.field(0x3D8):
                m.set(3)
        elif m.clock > m.deadline or not m.q("allyInLineOfFire"):
            m.set(3)
        m.act("turn")


# ---------------------------------------------------------------- Ogre
def ogre(m):
    last = m.field(0x460)
    s = m.state
    head(m, 0.1)
    if s == 0:
        if m.sight() or m.q("away"):
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(3)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 60, 2000):
            m.set(5)
        elif last not in (8, 9) and m.see(0, 60, X):
            m.set(9)
        elif not m.q("targetCharging") and m.see(0, 60, X):
            m.act("turn")
        elif m.see(0, 120, 2000) and m.q("alliesNearTarget", 60.0) > 0:
            m.set(5)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.see(0, 60, 2000):
            if last not in (8, 9) and m.rand() % 3 == 0:
                m.set(8)
            elif last != 7 and m.q("blockedByTarget") and m.rand() % 3 == 0:
                m.set(7)
            else:
                m.set(6)
        elif m.q("notRooted"):
            if not m.see(0, 156, 2000) and m.rand() % 60 == 0:
                m.set(3)
            elif m.rand() % 60 == 0 and not m.q("alliesNearTarget", 60.0):
                m.set(3)
    elif s in (6, 7, 8, 9):
        if s == 9:
            m.act("turn")
        if s == 6 and m.ev & 1:
            m.hit_all(0, 60, 6000, 0x40001)
        elif s == 7 and m.ev & 1:
            m.hit_all(0, 60, 6000, 0x100001, dmg=(1, 5, 33))
        elif s == 8:
            if m.ev & 1:
                m.hit_all(0, 60, 6000, 1)
            elif m.ev & 4:
                m.hit_all(0, 60, 6000, 0x80001)
        elif s == 9 and m.ev & 5:
            m.hit_all(0, 60, 6000, 1)
        if not m.anim & 8:
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(3)
    elif s == 0x14:
        m.act("deadUpdate", 30.0)
    else:
        m.set(0)


# ---------------------------------------------------------------- Warrior
def warrior(m):
    s = m.state
    head(m, 0.4)
    count = m.field(0x474)
    if s == 0:
        if m.sight() or m.q("away"):
            m.set(1)
    elif s == 1:
        if not m.sight():
            m.act("moveToDest")
        else:
            m.act("turn")
            if m.see(0, m.field(0x3AE), 8000):
                m.set(3)
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 12, 8000):
            m.set(5)
        elif not m.q("targetCharging") and m.see(0, 36, 8000):
            m.set(5)
        elif not m.q("targetCharging") and m.see(0, 36, X):
            m.act("turn")
        elif m.see(0, 120, 8000) and m.q("alliesNearTarget", 36.0) >= 1:
            m.act("pickTarget", 1)
            m.set(5)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.see(0, 36, 8000):
            if m.q("targetAttacking") and m.rand() % 3 == 0 and m.q("canBlock"):
                m.set(0x17)
            else:
                m.q("blockedByTarget")
                m.set(8 if m.rand() % 2 == 0 else 6)
        elif m.see(0, 36, X):
            m.act("turn")
        elif m.q("notRooted"):
            near = m.see(0, 156, 8000)
            if m.rand() % 60 == 0 and not (near and m.q("alliesNearTarget", 36.0)):
                m.set(3)
        if m.clock > m.deadline:
            m.rand()
    elif s in (6, 7, 8):
        m.act("turn")
        blocking = m.field(0x478)
        if m.ev & 1:
            flags = 8
            if s != 7 and count in (3, 5) and not m.q("alliesNearTarget", 36.0):
                flags = 0x440008 if count == 3 else 0x100008
            m.hit(0, 36, 8000, flags)
        if m.ev & 2:
            if s == 7:
                if m.see(0, 36, 8000):
                    m.set(8 if m.field(0x470) == 6 else 6)
            elif count < 5 and m.see(0, 36, 8000):
                if count == 1:
                    if blocking or (m.rand() & 1) == 0:
                        m.set(7)
                elif count > 1 and blocking:
                    m.set(7)
        if not m.anim & 8:
            m.set(3)
    elif s in (9, 10):
        m.act("turn")
        if s == 9 and m.ev & 1:
            m.hit(0, 36, 8000, 8)
        if not m.anim & 8:
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(3)
    elif s == 0x14:
        m.act("deadUpdate", 20.0)
    elif s == 0x17:
        if m.clock > m.deadline:
            m.set(3)
    else:
        m.set(0)
    del count


# ---------------------------------------------------------------- Clockwork
def clockwork(m):
    sub = m.field(0x3C8)
    s = m.state
    head(m, 0.4)
    if s == 0:
        if m.sight() or m.q("away"):
            m.set(1)
    elif s == 1:
        if not m.sight():
            m.act("moveToDest")
        else:
            m.act("turn")
            if m.see(0, m.field(0x3AE), 8000):
                m.set(3)
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 36, 8000):
            m.set(5)
        elif m.see(0, 280, 16000):
            m.set(9)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.see(0, 36, 8000):
            if m.field(0x3CC) != 6:
                m.set(6)
            else:
                m.set(8 if m.rand() & 3 == 0 else 7)
        elif m.see(0, 36, X):
            m.act("turn")
        elif m.q("notRooted"):
            m.set(3)
    elif s in (6, 7):
        m.act("turn")
        if m.ev & 1:
            if s == 6:
                m.hit(0, 36, 8000, 1 if sub else 0x40008, dmg=(11, 22, 33))
            else:
                m.hit(0, 36, 8000, 0x40001 if sub else 8)
        if not m.anim & 8:
            m.set(5)
    elif s == 8:
        if not m.target:
            m.set(0)
        else:
            m.act("turn")
            if m.ev & 1:
                if sub:
                    m.hit_all(0, 36, X, 1)
                else:
                    m.hit(0, 36, 8000, 8)
            if not m.see(0, 36, 8000):
                m.set(3)
            elif m.clock > m.deadline:
                m.set(5)
    elif s == 9:
        if not m.target:
            m.set(0)
        else:
            m.act("moveToTarget")
            if m.ev & 1:
                m.hit(0, 36, 8000, 1 if sub else 8)
        if not m.q("targetCharging") and m.see(0, 12, 8000):
            m.set(5)
        elif not m.see(0, 280, 16000):
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(3)
    elif s == 0x14:
        if m.ev & 6:
            if m.ev & 4:
                m.act("damageInRadius")
                m.rand()
                m.act("poolNew")
        m.act("deadUpdate", 20.0)
    else:
        m.set(0)
    if sub:
        # 0x24f500-0x24f8e4: two steam puffs, each one own draw & 1 and,
        # while object flag 2 is clear, a rejection-sampled velocity. The
        # dead-state burst above sets object flags 0x4003 first.
        burst = s == 0x14 and m.ev & 6
        for _ in range(2):
            if m.rand() & 1 and not burst:
                m.rng.in_unit_sphere()


# ---------------------------------------------------------------- Droid
def droid(m):
    s = m.state
    head(m, 1.0)
    if m.field(0x3CC) < m.clock and s not in (0x14, 0x17):
        m.set(0x17)
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.q("away"):
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(3)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 24, X):
            m.set(0x17)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.see(0, 24, X):
            m.set(0x17)
        elif m.q("notRooted"):
            m.set(3)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(5)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(5)
    elif s == 0x14:
        if m.ev & 0x40:
            for _ in range(10):
                m.act("poolNew")
            m.act("objDelete")
    elif s == 0x17:
        if m.anim & 0x80:
            m.act("damageInRadius")
            m.rand()
            m.act("poolNew")
            m.act("objDelete")
            for _ in range(10):
                m.act("poolNew")
    else:
        m.set(0)


# ---------------------------------------------------------------- IronGuardian
def ironguardian(m):
    s = m.state
    head(m, 0.0)
    timer = m.field(0x3CC)
    if s == 0:
        if not m.sight():
            if m.q("away"):
                m.set(1)
        elif timer + 1 > 120:
            m.set(3)
    elif s == 1:
        if m.sight():
            m.set(0)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.cone(84, 400, 2000):
            m.set(9)
        elif timer < m.clock and m.cone(240, 400, 10000):
            m.set(10)
        elif m.cone(0, 84, X):
            m.set(5)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.cone(0, 84, 10000):
            m.set(6)
        elif m.cone(0, 84, 0x4000, 0x4000):
            m.set(7)
        elif m.cone(0, 84, 0x4000, -0x4000):
            m.set(8)
        elif m.cone(84, 400, 2000):
            m.set(9)
        elif timer < m.clock and m.cone(240, 400, 10000):
            m.set(10)
        elif m.q("notRooted"):
            m.set(3)
    elif s == 6:
        if m.ev & 1:
            m.hit_all(0, 84, 10000, 8)
        if not m.anim & 8:
            m.set(5)
    elif s in (7, 8):
        if m.c.get("alive", 0) == 1:
            m.act("turn")
        if m.ev & 1:
            m.hit_all(0, 84, 0x4000, 0x80008, facing=0x4000 if s == 7 else -0x4000)
        if not m.anim & 8:
            m.set(5)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(5)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(5)
    elif s == 9:
        m.act("turn")
        if not m.anim & 8:
            m.set(5)
    elif s == 10:
        m.act("turn")
        if m.ev & 1:
            m.rand()
            for _ in range(10):
                m.act("poolNew")
                m.rand()
                m.rng.in_unit_sphere()
        if not m.anim & 8:
            m.set(3)
    elif s == 0x14:
        m.act("deadUpdate", 30.0)
    else:
        m.set(0)


# ---------------------------------------------------------------- Froglock
def froglock(m):
    blowgun = m.c["holder"].get(0x7C) == 0x10   # hand-1 part from holder slot 15
    s = m.state
    head(m, 0.5)
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.q("away") or m.clock > m.deadline:
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(0)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif not blowgun:
            if m.see(0, 40, 6000):
                m.set(6)
            elif not m.see(0, 300, X) and m.see(0, 450, 1000):
                m.set(0x17)
            elif m.see(0, 40, X):
                m.act("turn")
            else:
                m.act("moveToTarget")
        else:
            if m.see(0, 100, X):
                m.set(0x10)
            elif m.see(0, 400, 6000):
                m.set(7)
            elif m.see(0, 400, X):
                m.act("turn")
            else:
                m.act("moveToTarget")
    elif s == 5:
        if (blowgun and m.see(0, 400, 6000)) or (not blowgun and m.see(0, 40, 6000)):
            m.set(7 if blowgun else 6)
        elif m.q("notRooted"):
            m.set(3)
    elif s == 6:
        if m.target and m.ev & 1:
            m.hit_reach(36, 8)
        if not m.anim & 8:
            m.set(5)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(0)
    elif s == 0x14:
        m.act("deadUpdate", 25.0)
    elif s == 0x17:
        if not m.anim & 0x10:
            m.set(3)


# ---------------------------------------------------------------- Amphian
def amphian(m):
    s = m.state
    head(m, 0.5)
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.q("away"):
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(3)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 12, 8000):
            m.set(5)
        elif not m.q("targetCharging") and m.see(0, 36, 8000):
            m.set(5)
        elif not m.q("targetCharging") and m.see(0, 36, X):
            m.act("turn")
        elif m.see(120, 360, 2000):
            m.set(9)
        else:
            m.act("moveToTarget")
    elif s == 5:
        if m.see(0, 36, 8000):
            hp, top = m.hp
            if hp < top * 0.5 and m.rand() & 3 == 0:
                m.set(0x17)
            else:
                m.set(6 + m.rand() % 3)
        elif m.see(0, 36, X):
            m.act("turn")
        elif m.see(120, 360, 2000):
            m.set(9)
        elif m.q("notRooted"):
            m.set(3)
    elif s in (6, 7, 8):
        m.act("turn")
        if m.ev & 1:
            m.hit(0, 36, 8000, 8)
        if m.ev & 2:
            m.hit(0, 36, 8000, 0x40001)
        if not m.anim & 8:
            m.set(5)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(3)
    elif s == 9:
        m.act("turn")
        if m.ev & 1:
            for _ in range(2):
                m.rng.in_unit_sphere()
                m.act("poolNew")
                m.rand()
        if not m.anim & 8:
            m.set(5)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(3)
    elif s == 0x14:
        m.act("deadUpdate", 20.0)
    elif s == 0x17:
        if m.clock > m.deadline:
            m.set(5)
    else:
        m.set(0)


# ---------------------------------------------------------------- SeaMonster
def seamonster(m):
    s = m.state
    head(m, 0.2)
    if s == 0:
        if m.sight():
            m.set(3)
        elif m.q("away"):
            m.set(1)
    elif s == 1:
        if m.sight():
            m.set(3)
        else:
            m.act("moveToDest")
    elif s == 3:
        if not m.target:
            m.set(0)
        elif m.see(0, 36, 5000):
            m.set(5)
        elif m.see(0, 36, X):
            m.act("turn")
        else:
            m.act("moveToTarget")
    elif s == 5:
        if not m.see(0, 36, 5000):
            if m.q("notRooted"):
                m.set(3)
        elif m.rand() & 1 == 0:
            m.set(7)
        else:
            m.set(9 if m.rand() % 3 == 0 else 6)
    elif s in (6, 7, 8):
        if m.target and m.ev & 1:
            m.hit(0, 36, 5000, 8)
        if s in (7, 8) and m.ev & 2 and m.rand() & 1 == 0 and m.see(0, 36, 5000):
            m.set(8 if s == 7 else 7)
        if not m.anim & 8:
            m.set(5)
    elif s == 9:
        if m.target and m.ev & 1:
            m.hit(0, 36, 5000, 0x80008)
        if not m.anim & 8:
            m.set(5)
    elif s == 0x10:
        if m.q("attackReady"):
            m.set(0)
        else:
            m.act("flee")
    elif s == 0x12:
        if not m.anim & 0x10:
            m.set(5)
    elif s == 0x13:
        if m.q("notStunned"):
            m.set(5)
    elif s == 0x14:
        m.act("deadUpdate", 30.0)
    elif s in (0x17, 0x18):
        if not m.anim & 8:
            m.set(3)


def _states(*excluded):
    return tuple(s for s in range(0x19) if s not in excluded)


# Field values at the clock (100) and one either side, so that > / >= and
# < / <= read differently; "states" limits a boundary variant to the states
# that read the field.
EDGE = (99, 100, 101)

SPECS.update({
    "WarWraith": dict(model=warwraith, states=_states(),
                      variants=({0x3C8: (8, 0), 0x3CC: (32, 0)},
                                {0x3C8: (8, 100), 0x3CC: (32, 500)})
                      + tuple({0x3C8: (8, 0), 0x3CC: (32, c), "states": (3, 5)} for c in EDGE)
                      # fade >= 99 turns; fade >= 100 deletes in 0x14
                      + tuple({0x3C8: (8, fade), 0x3CC: (32, 500)} for fade in (98, 99))),
    "Orc": dict(model=orc, states=_states(),
                variants=tuple({0x478: (32, v)} for v in range(6))
                + tuple({0x478: (32, 5), 0x47C: (32, c), "states": (0x17,)} for c in EDGE),
                deadlines=(0, 1, 2, 50, 99, 100, 101, 150)),
    "Goblin": dict(model=goblin, states=_states(7, 8),
                   variants=tuple({0x3D4: (32, v)} for v in range(6))
                   + tuple({0x3D4: (32, 5), 0x3D8: (32, c), "states": (0x17,)} for c in EDGE)),
    "Ogre": dict(model=ogre, states=_states(), evs=(0, 1, 2, 4, 5),
                 variants=tuple({0x460: (32, v)} for v in (0, 7, 8))),
    "Warrior": dict(model=warrior, states=_states(),
                    variants=tuple({0x3C8: (8, 1), 0x3AE: (16, 500), 0x474: (8, n),
                                    0x478: (32, b), 0x470: (32, last)}
                                   for n, b, last in ((0, 0, 0), (1, 0, 6), (1, 1, 8),
                                                      (2, 1, 6), (3, 0, 8), (5, 0, 6)))),
    "Clockwork": dict(model=clockwork, states=_states(), evs=(0, 1, 2, 4),
                      variants=({0x3C8: (8, 0), 0x3AE: (16, 500)},
                                {0x3C8: (8, 1), 0x3AE: (16, 500)},
                                {0x3C8: (8, 1), 0x3CC: (32, 6), 0x3AE: (16, 500)})),
    "Droid": dict(model=droid, states=_states(), evs=(0, 1, 0x40),
                  variants=({0x3CC: (32, 3600)}, {0x3CC: (32, 50)})
                  + tuple({0x3CC: (32, c)} for c in EDGE)),
    "IronGuardian": dict(model=ironguardian, states=_states(),
                         variants=({0x3CC: (32, 0)}, {0x3CC: (32, 120)},
                                   {0x3CC: (32, 700)})
                         + tuple({0x3CC: (32, c), "states": (3, 5)} for c in EDGE)
                         + tuple({0x3CC: (32, c), "states": (0,)} for c in (119, 121))
                         # alive-player count 0x4f8420 = 1: the 7/8 turn
                         + ({0x3CC: (32, 0), "alive": 1, "states": (7, 8)},)),
    "Froglock": dict(model=froglock, states=_states(7, 8),
                     variants=({"holder": {0x7C: 0x12}}, {"holder": {0x7C: 0x10}})),
    # (hit points, maximum): below, at and above half, at two maxima.
    "Amphian": dict(model=amphian, states=_states(),
                    hps=((100.0, 100.0), (10.0, 100.0), (49.0, 100.0), (50.0, 100.0),
                         (51.0, 100.0), (99.0, 200.0), (100.0, 200.0), (101.0, 200.0))),
    "SeaMonster": dict(model=seamonster, states=_states()),
})


# ---------------------------------------------------------------- setState entries
# Authored from docs/monsters-2.md class notes. land: state stored at +0x232
# (default: the request). fields: offset -> exact value, or (base, mod) for
# clock + base + (own draw % mod), or ("abs", base, mod) without the clock.
# calls: names that must be called; absent: names that must not be called;
# unwritten: object offsets that must not be stored.
def _e(land=None, calls=(), absent=(), unwritten=(), **fields):
    return dict(land=land, calls=calls, absent=absent, unwritten=unwritten,
                fields={int(k[1:], 16): v for k, v in fields.items()})


DEATH = ("dropLoot", "onDeath")
SET_ENTRY = {
    "Kobold": {0: _e(xF4=(0, 120)), 1: _e(xF4=(120, 120)), 5: _e(xF4=(60, 120)),
               6: _e(x3C8=6), 7: _e(x3C8=7), 8: _e(x3C8=8), 0x17: _e(x3C8=0x17),
               0x10: _e(x318=60), 4: _e(0), 0xA: _e(0), 0x11: _e(0),
               0x14: _e(calls=DEATH)},
    "WarWraith": {0: _e(xF4=(0, 120)), 7: _e(x3CC=(300, 120)), 0x11: _e(xF4=(120, 60)),
                  0x14: _e(calls=("lootGenerate", "onDeath"))},
    "Orc": {0: _e(xF4=(120, 60)), 4: _e(xF4=(40, 120)), 6: _e(xF4=("abs", 10, 10)),
            0x10: _e(x318=60), 0x11: _e(xF4=(120, 1), xA8=0x200),
            0x17: _e(xF4=(240, 240)), 0x14: _e(calls=DEATH)},
    "Goblin": {0: _e(xF4=(120, 60)), 4: _e(xF4=(40, 120)), 0x10: _e(x318=60),
               0x11: _e(xF4=(120, 1), xA8=0x200), 0x17: _e(xF4=(240, 240)),
               0x14: _e(calls=("dropLoot",))},
    "Ogre": {0: _e(xF4=(0, 120)), 6: _e(x460=6), 7: _e(x460=7), 8: _e(x460=8),
             9: _e(x460=9), 0x10: _e(x318=60), 4: _e(0), 0xA: _e(0), 0x11: _e(0),
             0x17: _e(0), 0x14: _e(calls=DEATH)},
    "Warrior": {0: _e(xF4=(0, 120)), 3: _e(x474=0, x478=0), 5: _e(xF4=(0, 360)),
                6: _e(x470=6, x474=1), 7: _e(x474=1), 8: _e(x470=8, x474=1),
                0x10: _e(x318=60), 0x17: _e(xF4=(60, 120), xA8=0x200),
                4: _e(0), 0x11: _e(0), 0x14: _e(calls=DEATH)},
    "Clockwork": {6: _e(x3CC=6), 7: _e(x3CC=7), 8: _e(x3CC=8, xF4=(120, 1)),
                  9: _e(xF4=(0, 1), x4F8=(0, 1)), 0x10: _e(x318=60),
                  4: _e(0), 0xA: _e(0), 0x11: _e(0), 0x17: _e(0),
                  0x14: _e(calls=DEATH)},
    "Droid": {0x10: _e(x318=60), 4: _e(0), 6: _e(0), 0xA: _e(0), 0x11: _e(0),
              0x14: _e(calls=("onDeath",), absent=("dropLoot", "lootGenerate")),
              0x17: _e(calls=("onDeath",), absent=("dropLoot", "lootGenerate"))},
    "IronGuardian": {9: _e(x3C8=0), 10: _e(x3C8=0), 0x10: _e(x318=60),
                     4: _e(0), 0x11: _e(0), 0x17: _e(0), 0x14: _e(calls=DEATH)},
    "Froglock": {0: _e(xF4=(0, 120)), 7: _e(xF4=("abs", 0, 15)), 8: _e(xF4=("abs", 0, 15)),
                 0x10: _e(x318=60), 0x14: _e(calls=DEATH)},
    "Amphian": {0x10: _e(x318=60), 0x17: _e(xF4=(60, 120), xA8=0x200),
                4: _e(0), 0xA: _e(0), 0x11: _e(0), 0x14: _e(calls=DEATH)},
    "SeaMonster": {0x14: _e(calls=DEATH), 0x10: _e(unwritten=(0x318,))},
}


# Slot 20 (isEnemy), 21 (isAlly), 2 (takeDamage) per class table, as the
# class notes give them: base 0x119328 / 0x119400 / 0x116638 unless named.
SLOTS = {name: (0x119328, 0x119400, 0x116638) for name in SPECS}
SLOTS["Kobold"] = (0x119328, 0x280434, 0x116638)
SLOTS["WarWraith"] = (0x2C1BC0, 0x119400, 0x116638)
SLOTS["Orc"] = (0x119328, 0x119400, 0x2A2EAC)
