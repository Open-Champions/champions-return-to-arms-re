"""Live producers for the in-game HUD bars, experience line and message.

SLUS-20973 v2.00. Floats are raw patterns through tools/ref_core.py, the same
default FPU as tools/ee_emu.py. No game table is copied into this file: the
experience words are arguments the difftest reads from the loaded executable.
"""
import ref_core as F

PLAYER = 0x4D8AF0
STRIDE = 0x4C30
COPY = 0x20000
ZERO = 0
RATE = 0x38D1B717          # 0.0001, the natural regen step
HEALTH_PASSIVE = 0x3DCCCCCC
MANA_PASSIVE = 0x3E199999
PASSIVE_BIAS = 0x3F999999  # 1.2
HUNDREDTH = 0x3C23D70A
ONE = 0x3F800000
BAR_SPAN = 99
XP_CAP_INDEX = 80


def s32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def s8(value):
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def s16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def _u32(value):
    return value & 0xFFFFFFFF


def fill_right(origin, current, maximum):
    """trunc(float(origin) + (current / maximum) * 99). No clamp.

    Health 0x1d9f24 and mana 0x1da318. current and maximum are record floats.
    """
    return F.to_int(F.add(F.from_int(origin), F.mul(F.div(current, maximum), F.from_int(BAR_SPAN))))


def xp_fill_right(origin, experience, lower, upper):
    """0x1da244. Both differences wrap as signed 32-bit integers, then cvt.s.w."""
    numer = F.from_int(s32(_u32(experience) - _u32(lower)))
    denom = F.from_int(s32(_u32(upper) - _u32(lower)))
    return F.to_int(F.add(F.from_int(origin), F.mul(F.div(numer, denom), F.from_int(BAR_SPAN))))


def promoted_origins(origins, players, local_slots, network):
    """Network rearrangement of the four words at 0x53c408, 0x1d9dec..0x1d9e4c.

    Offline leaves the words alone. Online, every local slot except 0 takes
    slot 0's original word, and the last word displaced by that exchange is
    saved. If slot 0 is not local, it receives that saved word, or 0 when no
    local slot displaced one.
    """
    out = list(origins[:4])
    if not network:
        return out
    first = out[0]
    displaced = 0
    for slot in range(players):
        if slot in local_slots and slot != 0:
            displaced = out[slot]
            out[slot] = first
    if 0 not in local_slots:
        out[0] = displaced
    return out


def bar_edges(origin, health, max_health, mana, max_mana, experience, lower, upper,
              acknowledged, local):
    """Which of the three bars hud_drawPlayerStatus submits, and each clip right.

    origin is the slot word at 0x53c408 before the +15 inset. A remote slot
    submits health only. Experience also needs acknowledged level above 0.
    """
    start = origin + 15
    edges = {'health': fill_right(start, health, max_health)}
    if local and s8(acknowledged) > 0:
        edges['experience'] = xp_fill_right(start, experience, lower, upper)
    if local:
        edges['mana'] = fill_right(start, mana, max_mana)
    return edges


def _modifier(amount, value):
    return F.mul(amount, F.add(F.mul(F.from_int(value), HUNDREDTH), ONE))


def _bonus_add(amount, value):
    return F.add(amount, F.mul(amount, F.mul(F.from_int(value), HUNDREDTH)))


def _natural(current, maximum, amount):
    grown = F.add(current, amount)
    if F.lt(maximum, grown):
        return maximum
    return grown


def _deliver(current, maximum, pending, rate):
    """Pending potion drain. The whole rate is added, then pending loses the rate.

    Hitting the maximum drops whatever pending remains. A rate larger than the
    pending still adds the whole rate when the maximum is not reached; pending
    then floors at 0.
    """
    if not F.lt(ZERO, pending):
        return current, pending
    grown = F.add(current, rate)
    if F.lt(maximum, grown):
        pending = ZERO
        grown = maximum
    left = F.sub(pending, rate)
    if F.lt(left, ZERO):
        left = ZERO
    return grown, left


def regen_health(health, max_health, pending, rate, copy, passive, bonus, modifiers):
    """Player_regenHealth 0x1b3b90. Returns (health, pending).

    passive is the integer 0x1bed48 returns for mask 0x10. modifiers is 17
    signed values, or None where that equipment pointer is empty. bonus is the
    signed byte at object +0x477. The copy flag or health <= 0 leaves both
    words alone, including a positive pending amount.
    """
    if copy or not F.lt(ZERO, health):
        return health, pending
    if F.lt(health, max_health):
        amount = F.mul(max_health, RATE)
        level = F.from_int(passive)
        if F.lt(ZERO, level):
            amount = F.mul(amount, F.add(F.mul(level, HEALTH_PASSIVE), PASSIVE_BIAS))
        amount = F.add(amount, F.mul(F.from_int(bonus), RATE))
        for value in modifiers:
            if value is not None:
                amount = _modifier(amount, value)
        health = _natural(health, max_health, amount)
    return _deliver(health, max_health, pending, rate)


def regen_mana(health, mana, max_mana, pending, rate, copy, class_id, passive, bonus,
               modifiers, blessed, rank, rank_value):
    """Player_regenMana 0x1b3900. Returns (mana, pending).

    The health float gates the whole call. Class word 0 clears the natural
    amount after the object byte and before items, blessed and skill 0x13.
    Those three later terms therefore stay 0 for class 0. Pending still drains.
    """
    if copy or not F.lt(ZERO, health):
        return mana, pending
    if F.lt(mana, max_mana):
        amount = F.mul(max_mana, RATE)
        level = F.from_int(passive)
        if F.lt(ZERO, level):
            amount = F.mul(amount, F.add(F.mul(level, MANA_PASSIVE), PASSIVE_BIAS))
        amount = F.add(amount, F.mul(F.from_int(bonus), RATE))
        if class_id == 0:
            amount = ZERO
        for value in modifiers:
            if value is not None:
                amount = _modifier(amount, value)
        if blessed is not None:
            amount = _bonus_add(amount, blessed)
        if rank:
            amount = _bonus_add(amount, rank_value)
        mana = _natural(mana, max_mana, amount)
    return _deliver(mana, max_mana, pending, rate)


def gain_experience(experience, amount, level, stat_points, skill_points, health, mana,
                    max_health, max_mana, table, local, menu_open):
    """player_giveExp 0x1d3150 plus the message store it asks hud_showMessage for.

    table is the 81 signed words at 0x41b558. The cap is table[80] - 1. Each
    crossed threshold adds stat points from the level being left, adds 3 skill
    points, increments the level byte, and refills health and mana only when
    health is above 0.     Acknowledged level is not written. Every machine calls hud_showMessage
    with 0x168 frames and force 0; only the owning machine stores it, and an
    open menu keeps the previous message. The level-up sound is local only.
    """
    if len(table) != 81:
        raise ValueError('experience table must be the 81 words at 0x41b558')
    cap = _u32(table[XP_CAP_INDEX] - 1)
    total = _u32(experience + amount)
    experience = cap if s32(cap) < s32(total) else total
    steps = 0
    while True:
        index = s8(level)
        if not 0 <= index < 81:
            raise ValueError('level byte outside the executed table')
        if s32(experience) < s32(table[index]):
            break
        band = s8(level)
        if band < 6:
            stat_points = _u32(stat_points + 1)
        elif band < 0x10:
            stat_points = _u32(stat_points + 2)
        elif band < 0x1A:
            stat_points = _u32(stat_points + 3)
        elif band < 0x24:
            stat_points = _u32(stat_points + 4)
        else:
            stat_points = _u32(stat_points + 5)
        skill_points = (skill_points + 3) & 0xFF
        level = (level + 1) & 0xFF
        steps += 1
        if F.lt(ZERO, health):
            health, mana = max_health, max_mana
    # The sound is the only local-only part. The message call is made on every
    # machine; hud_showMessage then keeps it on the owning machine.
    message = show_message(local, menu_open, 0, 0x168, 0) if steps else None
    return {
        'experience': experience, 'level': level, 'stat_points': stat_points,
        'skill_points': skill_points, 'health': health, 'mana': mana,
        'steps': steps, 'sounds': steps if local else 0, 'message': message,
    }


def show_message(local, menu_open, slot, frames, force):
    """hud_showMessage 0x1d92a0. None when the call returns without storing.

    slot -1 skips the local-slot test. Force is the low byte of the fourth
    argument; only a zero byte consults the local-menu byte 0x41b69d. The
    stored timer is the low 16 bits of the frame count.
    """
    if slot != -1 and not local:
        return None
    if (force & 0xFF) == 0 and menu_open:
        return None
    return {'timer': frames & 0xFFFF, 'force': force & 0xFF}


def tick_message(timer, suppressed, warmup, players, network, latch):
    """hud_tickMessage 0x1d934c. Returns (timer, bust latch 0x4f66a9).

    One simulation tick. A suppressed HUD byte or a nonzero warmup word holds
    the timer. A timer whose signed halfword is not positive holds it too.
    Otherwise the unsigned halfword decreases by 1. Four offline players also
    set the bust latch; any other count or a network byte leaves the latch.
    """
    if suppressed or warmup or s16(timer) <= 0:
        return timer & 0xFFFF, latch
    timer = _u32((timer & 0xFFFF) - 1) & 0xFFFF
    if players == 4 and network == 0:
        latch = 1
    return timer, latch


def message_alpha(timer, alpha, suppressed, force):
    """The alpha word 0x4f66ec written by the message half of 0x1d93b0.

    A non-positive timer, or a suppressed HUD with a zero force byte, leaves
    the previous alpha. Below 32 frames alpha becomes 4 * timer. Otherwise it
    rises by 3. A result that is not below 129 becomes 128.
    """
    if s16(timer) <= 0 or (suppressed and (force & 0xFF) == 0):
        return alpha & 0xFFFFFFFF
    if s16(timer) < 0x20:
        alpha = s16(timer) * 4
    else:
        alpha = (alpha + 3) & 0xFFFFFFFF
    if s32(alpha) >= 0x81:
        alpha = 0x80
    return alpha & 0xFFFFFFFF
