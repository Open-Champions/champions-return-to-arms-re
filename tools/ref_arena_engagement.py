"""Small addressed timing model for the recipe-0 arena engagement probe.

These rules are read from arena_runTask 0x306b78, Creature_filterState
0x10a9c0, Creature_pickTarget 0x10ded0, and Player_run state 1
0x1a5030. The class AI and damage arithmetic have separate models.
"""


def intro_step(counter):
    """One 0x306b78 intro visit: next halfword and the three lock words."""
    if counter > 0:
        return counter - 1, (1, 1, 1)
    if counter == 0:
        return 0xFFFF, (0, 0, 0)
    return counter, None


def state_refused(mode_b, mode_a, lock, ended):
    """The PvP-B first gate at 0x10a9c0, before stun/root filtering."""
    return bool(mode_b and not mode_a and lock and not ended)


def first_scan_from(start, serial):
    """First eligible 0x10ded0 target scan at or after an absolute frame."""
    signed = serial if serial < 0x80 else serial - 0x100
    return next(frame for frame in range(start, start + 32)
                if ((frame ^ signed) & 0x1F) == 0)


def unarmed_hit_frame(press_frame):
    """Offline Player_run state-1 hit time with speed 1.0: trunc(16.02)."""
    return press_frame + 16


def health_after_pending(hp, pending):
    """Unblocked plain hit in Player_processDamage 0x1b2cc0."""
    return max(0.0, hp - pending)
