#!/usr/bin/env python3
"""Reference for the arena and PvP-mode rules in Champions: Return to Arms (SLUS_209.73).

A research model, not game code.  Each function follows the instruction sequence named in
its docstring and is compared with that code, run under tools/ee_emu.py, by
tools/difftest_arena_modes.py.  docs/arena-modes.md is the prose.  Floats are the raw
patterns from tools/ref_core.py.  No game data is embedded: recipe bytes and name tables
are arguments, read from the executable by the difftest.

The shared generator used here is the one inlined at the arena sites,
seed = seed * 0x19660d + 0x3c6ef35f, draw = seed >> 16.  It is not Rand.rand.
"""
from ref_core import (HALF, ONE, TWO, ZERO, add, atan2_16, cos16, eq, fmax, from_int, le,
                      lt, mul, neg, s16, s32, sin16, sqrt, sub, to_int)

M32 = 0xFFFFFFFF

# Patterns the arena code loads with lui/ori, not host decimals.
K_180 = 0x43340000
K_36 = 0x42100000
K_240 = 0x43700000
K_259 = 0x43818000
K_290 = 0x43910000
K_M500 = 0xC3FA0000
K_320 = 0x43A00000
K_STEP = 0x3CF5C28F          # 0.03, truncated
K_CLIMB = 0x3C2AF07F         # overlay timer step
K_FADE_STEP = 0x3C61029B       # prompt fade step, lui 0x3c61 / ori 0x29b
K_LEVEL = 0x3F2BC579
K_FIVE = 0x40A00000
K_QUOT = 0x3F814738
K_REM = 0x3F80A393
K_TWO_HALF = 0x40200000
K_1_30 = 0x3D088888          # armour/30, the same pattern damage_apply uses
K_MOVE_NET = 0x3FA00000      # 1.25
K_MOVE_OFF = 0x3FE00000      # 1.75
K_1_5 = 0x3FC00000

SCORE = 0x503898
SCORE_STRIDE = 12
LIVES_START = 2
INTRO_FRAMES = 0xB4          # 180
INTRO_CUE = 0x84             # the frame the counter has just become 132
INTERMISSION_OFFLINE = 0x1E0
INTERMISSION_ONLINE = 0x3C0
DEAD_COUNTDOWN = 0xF0
MODE_A_MAPS = 13
KILL_CHOICES = (5, 10, 25)   # menu index 0, 1, and anything else (0x1e1a64)


def lcg(seed):
    """One step of the inlined generator.  Returns (new seed, draw)."""
    seed = (seed * 0x19660D + 0x3C6EF35F) & M32
    return seed, (seed >> 16) & 0xFFFF


def sdiv(n, d):
    """MIPS div: quotient toward zero, remainder with the dividend's sign.

    A zero divisor is the hardware trap the arena sites do not test for (the ring count,
    the spawn-point count, a recipe's group count)."""
    if s32(d) == 0:
        raise ZeroDivisionError('arena divides by zero')
    n, d = s32(n), s32(d)
    q = abs(n) // abs(d)
    if (n < 0) ^ (d < 0):
        q = -q
    return q, n - q * d


def u16(value):
    return value & 0xFFFF


def _signed_byte(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def high_nibble(byte):
    """sll 24 / sra 28 of an unsigned byte.  0x30 -> 3, 0x42 -> 4."""
    return s32((byte & 0xFF) << 24) >> 28


def low_nibble(byte):
    """The mode-B name-table index in the low nibble (sll 28 / sra 26, then / 4)."""
    return (s32((byte & 0xFF) << 28) >> 26) // 4


class Slot(object):
    """One column of the score block at 0x503898.  Halfwords are stored unsigned."""

    def __init__(self, kills=0, lives=0, snapshot=0, timer=ZERO):
        self.kills = u16(kills)
        self.lives = u16(lives)
        self.snapshot = u16(snapshot)
        self.timer = timer & M32

    def copy(self):
        return Slot(self.kills, self.lives, self.snapshot, self.timer)


def reset_scores(slots, networked):
    """arena_resetScores 0x307c80.  memset of the 0x30-byte block, then per slot."""
    for slot in slots:
        slot.kills = 0
        slot.lives = LIVES_START
        slot.snapshot = 0
        slot.timer = TWO
    return K_MOVE_NET if networked else K_MOVE_OFF


def lose_life(slot, mode_a, prediction=False):
    """arena_loseLife 0x305650.  Prediction copies are ignored.

    Mode A decrements the kill halfword.  Otherwise the life halfword.  The load is
    unsigned, so 0 becomes 65535, which a signed read treats as -1."""
    if prediction:
        return
    if mode_a:
        slot.kills = u16(slot.kills - 1)
    else:
        slot.lives = u16(slot.lives - 1)


def add_kill(slots, killer, amount, mode_a, num_players):
    """arena_addKill 0x3056cc.  The stored credit is +1, never ``amount``.

    In mode A, amount 0 returns without a credit.  ``killer`` is None, or an object with
    .flags, .slot and .owner (the signed byte at creature +0x5a).  A player (flag 0x40)
    is credited on .slot.  A creature is credited on .owner when that byte is >= 0.
    Anything else, including a null killer, credits slot 0 when there is one player and
    does nothing otherwise.
    """
    if mode_a and (amount & M32) == 0:
        return
    if killer is not None and killer.flags & 0x40:
        slots[killer.slot].kills = u16(slots[killer.slot].kills + 1)
        return
    if killer is not None and killer.flags & 0x20 and _signed_byte(killer.owner) >= 0:
        owner = _signed_byte(killer.owner)
        slots[owner].kills = u16(slots[owner].kills + 1)
        return
    if num_players == 1:
        slots[0].kills = u16(slots[0].kills + 1)


def on_killed(slots, slot, killer, mode_a, num_players, prediction=False):
    """arena_onPlayerKilled 0x305580.

    A prediction copy returns.  A killer with flag 0x40 whose slot byte equals the victim
    is a suicide and only loses a life (or, in mode A, a kill).  A null killer, or a killer
    with creature flag 0x20, scores: mode A credits a kill, otherwise the life halfword
    drops by one.  Any other killer only loses the life.
    """
    if prediction:
        return 'ignore'
    if killer is not None and killer.flags & 0x40 and killer.slot == slot:
        lose_life(slots[slot], mode_a)
        return 'suicide'
    if killer is None or killer.flags & 0x20:
        if mode_a:
            add_kill(slots, killer, 1, True, num_players)
            return 'kill'
        lose_life(slots[slot], False)
        return 'life'
    lose_life(slots[slot], mode_a)
    return 'suicide'


def add_life(slot, mode_b, mode_a):
    """arena_addLife 0x3058c0.  Only mode B without mode A, and only +1 life."""
    if mode_b and not mode_a:
        slot.lives = u16(slot.lives + 1)


def grant_life(slot):
    """0x307ee0.  +1 life, overlay timer cleared, HUD word becomes 0x80."""
    slot.lives = u16(slot.lives + 1)
    slot.timer = ZERO
    return 0x80


def respawn_allowed(slot, mode_a, active, intermission):
    """The three gates in arena_respawnPlayer 0x305784, before the spawn call."""
    if not mode_a and s16(slot.lives) < 0:
        return False
    if not active or intermission != 0:
        return False
    return True


def tick_overlay(slots):
    """0x307f68.  A timer sitting on exactly 2.0 stays.  Otherwise it climbs by K_CLIMB,
    and a result above 2.0 is clamped; the clamp also copies lives into the snapshot."""
    for slot in slots:
        if eq(slot.timer, TWO):
            continue
        nxt = add(slot.timer, K_CLIMB)
        slot.timer = nxt
        if lt(TWO, nxt):
            slot.timer = TWO
            slot.snapshot = slot.lives


def overlay_t(timer, step):
    """max(0, timer - step * 0.03), the value drawHud hands to the hermite as f12."""
    return fmax(ZERO, sub(timer, mul(from_int(step), K_STEP)))


def overlay_draws(timer, step):
    """True when that value is <= 1.  drawHud skips the glyph otherwise."""
    return le(overlay_t(timer, step), ONE)


def overlay_anchor_x(screen_x, current):
    """259, negated once a screen x is strictly above 320 while the anchor is still
    positive.  The negated value is kept for later slots in the same call."""
    if lt(K_320, from_int(screen_x)) and lt(ZERO, current):
        return neg(current)
    return current


def hermite(t, p0, p1, m0, m1):
    """vec3_hermite 0x162310.  Component order matches the adds in that function.

    h00 = 2t^3 - 3t^2 + 1, h01 = -2t^3 + 3t^2, h10 = t^3 - 2t^2 + t, h11 = t^3 - t^2.
    """
    t2 = mul(t, t)
    t3 = mul(t2, t)
    three_t2 = mul(t2, 0x40400000)
    two_t2 = add(t2, t2)
    two_t3 = add(t3, t3)
    h00 = add(sub(two_t3, three_t2), ONE)
    h01 = add(mul(t3, 0xC0000000), three_t2)
    h10 = add(sub(t3, two_t2), t)
    h11 = sub(t3, t2)

    def axis(a, b, c, d):
        r = mul(a, h00)
        r = add(r, mul(b, h01))
        r = add(r, mul(c, h10))
        return add(r, mul(d, h11))

    return [axis(p0[i], p1[i], m0[i], m1[i]) for i in range(3)]


def fade_step(value):
    """The first stores of arena_drawPrompt 0x3075dc: add the step, clamp at 1."""
    nxt = add(value, K_FADE_STEP)
    if lt(ONE, nxt):
        return ONE
    return nxt


def ring_delta(slot, count, mode_a):
    """Offset from spawn-table entry 0.  count <= 0 divides by the zero word."""
    quot, _ = sdiv(0xFFFF, count)
    angle = s16(s16(quot) * s32(slot))
    radius = K_180 if mode_a else K_36
    return angle, mul(cos16(angle), radius), mul(sin16(angle), radius)


def _facing_from_entry(pos, entry, mode_a, scramble, slot, points):
    if scramble:
        facing = s16(points[slot][3] - 0x4000)
    else:
        facing = s16(-0x4000 - atan2_16(sub(pos[0], entry[0]), sub(pos[1], entry[1])))
    if not mode_a:
        facing = s16(facing - 0x8000)
    return facing


def pick_spawn(flag, slot, points, seed, mode_a, scramble, network, focus, active,
               search, camera_target):
    """arena_pickSpawnPoint 0x3050a4.

    ``points`` are (x, y, z, angle).  ``search(centre, spread, radius)`` returns
    (pos, ok) the way world_findFreeSpot does.  ``camera_target`` is the vec
    Camera_getTarget writes.  Returns (pos, facing, seed).

    flag != 0 is the wave placement: a ring around entry 0, radius 180 in mode A and 36
    otherwise, then a free-spot search of spread 36 / radius 24, retried at spread 240
    when the ok byte is 0.  Facing uses the scramble word when it is set, otherwise the
    atan2 of the offset from entry 0, and mode B turns that around by half a circle.

    flag == 0 is the respawn.  A net game draws one table index from the shared generator.
    Offline, the points within 240 of the camera focus are the candidates; if there are
    none, the search starts at the camera target with spread 72 / radius 24 and facing 0.
    """
    if flag:
        angle, dx, dy = ring_delta(slot, active, mode_a)
        centre = [add(points[0][0], dx), add(points[0][1], dy), points[0][2]]
        pos, ok = search(centre, 0x24, 0x18)
        if not ok:
            pos, ok = search(centre, 0xF0, 0x18)
        facing = _facing_from_entry(pos, points[0], mode_a, scramble, slot, points)
        return pos, facing, seed
    count = len(points)
    if network:
        seed, index = _mod_index(seed, count)
        chosen = points[index]
        return [chosen[0], chosen[1], chosen[2]], s16(chosen[3] + 0x4000), seed
    near = [i for i, p in enumerate(points) if _near_focus(p, focus)]
    if not near:
        pos, _ok = search(list(camera_target), 0x48, 0x18)
        return pos, 0, seed
    seed, index = _mod_index(seed, len(near))
    chosen = points[near[index]]
    return [chosen[0], chosen[1], chosen[2]], s16(chosen[3] + 0x4000), seed


def _mod_index(seed, count):
    seed, draw = lcg(seed)
    _q, index = sdiv(draw, count)
    return seed, index


def _near_focus(point, focus):
    dx = sub(point[0], focus[0])
    dy = sub(point[1], focus[1])
    return lt(sqrt(add(mul(dx, dx), mul(dy, dy))), K_240)


def monster_level(wave):
    """g_levelMonsterLevel as startWave stores it: float(signed wave) * K_LEVEL + 5."""
    return add(mul(from_int(s16(wave)), K_LEVEL), K_FIVE)


def spawn_budget(wave, active):
    """How many monsters the recipe asks for, before the class split.

    The scaled value is kept when it is below 11 and replaced by 10 when it is not,
    then activeSlots - 1 is added.  Returns (count, wave//3, wave%3)."""
    quot, rem = sdiv(s16(wave), 3)
    acc = add(mul(from_int(quot), K_QUOT), mul(from_int(rem), K_REM))
    if le(ZERO, add(acc, TWO)):
        value = add(acc, K_TWO_HALF)
    else:
        value = sub(add(acc, TWO), HALF)
    count = to_int(value)
    if count >= 11:
        count = 10
    return count + s32(active) - 1, quot, rem


def recipe_groups(record, rem, count):
    """Class indices, one per monster, for one recipe record (6 bytes) and a remainder.

    Remainder 0 repeats the class at byte +1.  Remainder 1 uses high_nibble-1 groups,
    remainder 2 uses the high nibble.  Group 0 receives the division remainder.  Any
    other remainder spawns nothing.  A non-positive group count is the untested div."""
    if rem == 0:
        return [s32((record[1] & 0xFF) << 24) >> 24] * count
    if rem < 0 or rem >= 3:
        return []
    groups = high_nibble(record[0]) - (1 if rem == 1 else 0)
    per, extra = sdiv(count, groups)
    leftover = count - per * groups
    out = []
    for group in range(groups):
        n = per + leftover if group == 0 else per
        cls = s32((record[1 + group] & 0xFF) << 24) >> 24
        out.extend([cls] * n)
    return out


def ring_step(seed, count):
    """0x3065b0.  Returns (seed, angle word, draw halfword)."""
    quot, _ = sdiv(0xFFFF, count)
    seed, draw = lcg(seed)
    return seed, quot & M32, draw & 0xFFFF


def wave_plan(wave, active, record_count, records, seed, saved=0):
    """The monster side of arena_startWave 0x305ed4 once the wave halfword is current.

    ``records`` is the list of 6-byte recipes.  Returns
    (classes, seed, steps) where steps are the (count, angle word, draw) of each
    0x3065b0 call.  saved != 0 skips the recipe; the original then respawns that many
    saved pointers instead, which this function reports as classes None.
    """
    if saved:
        seed, angle, draw = ring_step(seed, saved)
        return None, seed, [(saved, angle, draw)]
    _count, quot, rem = spawn_budget(wave, active)
    record = records[sdiv(quot, record_count)[1]]
    classes = recipe_groups(record, rem, _count)
    steps = []
    if rem == 0:
        seed, angle, draw = ring_step(seed, _count)
        steps.append((_count, angle, draw))
    elif 0 < rem < 3:
        groups = high_nibble(record[0]) - (1 if rem == 1 else 0)
        per, _ = sdiv(_count, groups)
        leftover = _count - per * groups
        for group in range(groups):
            n = per + leftover if group == 0 else per
            seed, angle, draw = ring_step(seed, n)
            steps.append((n, angle, draw))
    return classes, seed, steps


def level_record_index(wave, record_count):
    """Record chosen when mode B changes level: ((signed wave + 1) / 3) % record_count.

    The caller then takes that record's low nibble as the mode-B name index."""
    quot, _rem = sdiv(s16(wave) + 1, 3)
    _q, index = sdiv(quot, record_count)
    return index


def mode_a_next_index(index, scan0):
    """(index + 1) mod 13.  A remainder of 0 is replaced by game_scanCm1Vars(0)."""
    nxt = sdiv(s32(index) + 1, MODE_A_MAPS)[1]
    if nxt == 0:
        return s32(scan0) & 0xFF
    return nxt


def kill_choice(menu_index):
    """The byte stored at 0x4f8408 by the front end (0x1e1a64)."""
    if menu_index == 0:
        return 5
    if menu_index == 1:
        return 10
    return 25


def compare_kills(slot_a, slot_b, kills_a, kills_b):
    """0x307df0.  -1 when A has more kills.  Equal kills return 1 when slot A is the
    higher index and 0 otherwise, so a lower index is not ordered after a higher one."""
    ka, kb = s16(kills_a), s16(kills_b)
    if kb < ka:
        return -1
    if ka < kb:
        return 1
    if slot_b < slot_a:
        return 1
    return 0


def kill_limit_reached(kills, limit):
    """Signed kill halfword >= the signed byte at 0x4f8408."""
    return s16(kills) >= s32(limit << 24) >> 24


def intermission_limit(networked):
    return INTERMISSION_ONLINE if networked else INTERMISSION_OFFLINE


def intermission_done(counter, networked):
    """The compare uses the counter before this frame's increment."""
    return s16(counter) == intermission_limit(networked)


def round_expired(waves_left, mode_a):
    """'level' when the map changes, 'wave' when the same map starts another wave."""
    if s16(waves_left) == 0 or mode_a:
        return 'level'
    return 'wave'


def still_in(active, lives, hp, countdown):
    """Mode B's live-match scan.  An inactive slot is not in.  Lives >= 0, hp > 0, or a
    dead-countdown still running keeps the slot in."""
    if not active:
        return False
    if s16(lives) >= 0 or lt(ZERO, hp):
        return True
    return s16(countdown) > 0


def wipe_during_intermission(active, lives, hp):
    """True when this active slot can still play (hp > 0 or lives >= 0)."""
    if not active:
        return False
    return lt(ZERO, hp) or s16(lives) >= 0


def buy_life(gold, budget):
    """The mode-B tail.  Returns (gold, budget, bought)."""
    if s32(gold) < s32(budget):
        return gold, budget, False
    return s32(gold) - s32(budget), (s32(budget) << 1) & M32, True


def armour_bound(bound, armor):
    """One side of damage_apply's armour cut.  Applied to a player victim, and to every
    victim while mode A is on."""
    cut = mul(from_int(s16(armor)), K_1_30)
    low = sub(bound, cut)
    floor = mul(bound, HALF)
    if lt(low, floor):
        low = floor
    if lt(low, ZERO):
        low = ZERO
    return low


def pvp_half(amount):
    """Mode A, player victim, after the rest of the pipeline: amount * 0.5."""
    return mul(amount, HALF)


def spell_arena_flag(counter):
    """SpellArena_run sets owner flag bit 1 while the intro counter is >= 61.
    Below 61 it clears that bit with a mask of -3 (bit 0 stays).  Particles and the
    tint run only when the counter is >= 30."""
    return s16(counter) >= 0x3D


def spell_arena_tint(counter):
    return s16(counter) >= 0x1E


TINT = (0x56, 0x35, 0x21, 0x3D)
