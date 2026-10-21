"""ref_fire_touch.py - a LooseFire touching a player or a creature: the fire descriptor
(type 0x15) through the real damage_apply, and the burn it leaves.

Reference contract, executed against the original by tools/difftest_fire_touch.py
(docs/spec/fire-touch.md is the prose).  Evidence words as in CONTRIBUTING.md.

What this module adds is the COMPOSITION, not new bodies:

    LooseFire_onTouch   0x1fcb70   tools/ref_potion_ctors.py (executed with damage_apply a
                                   recording stub)
    damage_apply        0x1e8230   tools/ref_combat.py (executed by tools/difftest_combat.py
                                   with random descriptors)
    the burn tick       0x11332c   tools/ref_creature.py Model._burn_damage (executed by
                                   tools/difftest_creature.py), which calls damage_apply

Here the original LooseFire_onTouch calls the original damage_apply, the descriptor it
builds on its own stack is the one damage_apply reads, and the burn the hit leaves is
the input of the burn tick's own damage_apply.  The model side is
`loosefire_touch` (the onTouch rules on ref_combat records, then ref_combat.damage_apply)
and `burn_tick` (the burn tick's arguments, then ref_combat.damage_apply).

Everything in a docstring is Executed unless it says Inferred.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_combat as R                          # noqa: E402

M32 = 0xFFFFFFFF

# ---------------------------------------------------------------------------------------
# Addresses and constants (Observed at the addresses given)
# ---------------------------------------------------------------------------------------
LOOSEFIRE_ON_TOUCH = 0x1FCB70
DAMAGE_APPLY = 0x1E8230
G_SIM_FRAME = 0x44FDCC                          # its address is formed at 0x1fcb70 and read at 0x1fcb78
G_DIFFICULTY = 0x4F719C                         # address formed at 0x1fcc58, read at 0x1fcc60
G_RAND_SEED = 0x404464                          # the shared seed
G_SKILL_BURN = 0x41B1A4                         # the Skill asked for a burning player's range

TOUCH_PERIOD = 20                               # immediate at 0x1fcb74; signed remainder at 0x1fcb88
OWNER_SLOT = 20                                 # table + 0xa0 at 0x1fcbcc (slot 20, is-enemy)
FIRE_ENTRY = 0x15                               # 0x1fcc6c, 0x1fccd0, 0x1fcd30, 0x1fcd8c, 0x1fce48
PLAYER_VALUE = {2: 2, 3: 3, 4: 4, 5: 5}         # 0x1fcc5c-0x1fcd94: as they are; else 1 (0x1fcde8)
OTHER_PLAYER_VALUE = 1
CREATURE_VALUE = 8                              # 0x1fce4c, 0x1fce50
TOUCH_RATING = 10000000                         # two immediate halves at 0x1fcea4, 0x1fcebc
TOUCH_FLAGS = 0x0100C040                        # two immediate halves at 0x1fcea8, 0x1fcec8

BURN_RATING = 100000                            # the burn tick (ref_creature._burn_damage)
BURN_FLAGS = 0x1180C040
BURN_PERIOD_MASK = 0x1F                         # frame & 0x1f == 0
BURN_MONSTER = 1                                # (0x15, 1, 1)
BURN_SCALE = 0x3E199999                         # 0.15: a player's base from the skill's number
BURN_SPREAD = 0x3E4CCCCC                        # 0.2
DT = 0x3C888888                                 # 1/60, Creature_run's step of the burn seconds

# flag bits of damage_apply that matter here (docs/spec/combat.md, executed in round 1)
F_UNBLOCKABLE = 0x40                            # no block test, no Spirit Shield
F_NO_HIT_SOUND = 0x4000                         # step 26
F_NO_MISS_SOUND = 0x8000                        # step 21
F_NO_NUMBER = 0x1000000                         # step 28: no floating number
F_DOT = 0x800000                                # step 25 (burn tick only)
F_NO_STATUS = 0x10000000                        # 0x15 does not set the burn (burn tick only)

ZERO, ONE, TWO = R.ZERO, R.ONE, R.TWO


def touch_entry(toucher_flags, difficulty):
    """The descriptor LooseFire_onTouch builds for a toucher: [(0x15, v, v, 0)] or None
    for an empty one.  A player (0x40) takes v from g_difficultyIdx (2..5 as they are,
    anything else 1); a creature that is not a player (0x20) takes 8; anything else
    gets an empty descriptor (every type -1)."""
    if toucher_flags & 0x40:
        value = PLAYER_VALUE.get(R.s32(difficulty), OTHER_PLAYER_VALUE)
    elif toucher_flags & 0x20:
        value = CREATURE_VALUE
    else:
        return None
    return [(FIRE_ENTRY, value, value, 0), (-1, 0, 0, 0), (-1, 0, 0, 0), (-1, 0, 0, 0)]


def fire_owner(fire):
    """The object behind the fire's handle +0x4c when its flags have 0x20, else None."""
    if fire.owner_link and fire.owner is not None and fire.owner.flags & 0x20:
        return fire.owner
    return None


def loosefire_touch(w, fire, toucher, owner_says):
    """LooseFire_onTouch 0x1fcb70 with the real damage_apply behind it.

    w           ref_combat.World (w.frame, w.difficulty, the seed)
    fire        the LooseFire as a ref_combat.Obj (its +0x4c handle is owner_link/owner)
    toucher     the ref_combat.Obj touching it
    owner_says  callable(owner, toucher) -> the owner's slot 20 answer

    Returns None when the touch does nothing, else damage_apply's result (which the
    original drops).  Logged: ('enemy20', owner, toucher) for the slot-20 question."""
    if R.c_rem(R.s32(w.frame), TOUCH_PERIOD):
        return None
    owner = fire_owner(fire)
    if owner is not None:
        answer = owner_says(owner, toucher) & M32
        w.log('enemy20', owner.tag, toucher.tag)
        if not answer:
            return None
    desc = touch_entry(toucher.flags, w.difficulty)
    return R.damage_apply(w, toucher, owner if owner is not None else fire, ZERO, ZERO, TOUCH_RATING,
                          TOUCH_FLAGS, desc, 0)


def burn_range(w, skill_number):
    """The burn tick's entry for a PLAYER (ref_creature._burn_damage): base = f32(n) x
    0.15, ONE shared draw d, (int(base), int(base + base x 0.2 x d / 65536))."""
    base = R.fmul(R.itof(R.s32(skill_number)), BURN_SCALE)
    d = w.seed.draw()
    low = R.ftoi(base)
    high = R.ftoi(R.fadd(base, R.fmul(R.fmul(base, BURN_SPREAD), R.fmul(R.itof(d), R.K_1_65536))))
    return low, high


def burn_tick(w, victim, skill_number=0):
    """The burn tick's hit (0x11332c-0x113538) on a burning victim, frame & 0x1f == 0:
    damage_apply(c, c, 100000, 0, 0, 0x1180c040, (0x15, lo, hi, 0), 0; 0, 0).  A monster
    has lo = hi = 1; a player draws its range (burn_range).  The caller decides that the
    victim is burning and the frame is a tick frame (Creature_run, executed)."""
    if victim.flags & 0x40:
        low, high = burn_range(w, skill_number)
    else:
        low = high = BURN_MONSTER
    desc = [(FIRE_ENTRY, low & 0xFFFF, high & 0xFFFF, 0), (-1, 0, 0, 0), (-1, 0, 0, 0), (-1, 0, 0, 0)]
    desc = [tuple(R.s16(v) if i else v for i, v in enumerate(slot)) for slot in desc]
    return R.damage_apply(w, victim, victim, ZERO, ZERO, BURN_RATING, BURN_FLAGS, desc, 0)


# ---------------------------------------------------------------------------------------
# Inferred summaries (from the executed bodies above; checked by the tests)
# ---------------------------------------------------------------------------------------
def burn_after_touch(fire_resistance, before=ZERO):
    """Inferred: the burn seconds +0x340 right after a touch that lands on a creature or
    a player: 2 - 2 x fire resistance (the 0x15 entry, TOUCH_FLAGS lacks 0x10000000).  It
    is a store, not an add: a re-touch resets the burn, it never stacks.  `before` does
    not matter."""
    return R.fsub(TWO, R.fadd(fire_resistance, fire_resistance))


def burn_tick_frames(start_frame, seconds):
    """Inferred: the frames, after the touch frame, on which Creature_run's burn tick hits:
    the burn loses DT per Creature_run (before the tick test) and ticks on frame & 0x1f ==
    0 while it was above 0 when that run began.  Assumes one Creature_run per frame from
    start_frame + 1 and no re-touch."""
    frames = []
    burn = seconds
    frame = start_frame
    while R.flt(ZERO, burn):
        frame += 1
        burn = R.fsub(burn, DT)
        if frame & BURN_PERIOD_MASK == 0:
            frames.append(frame)
    return frames
