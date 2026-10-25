"""Small contracts for the bounded valor resource, grant and gold probes.

These are identifiers and rules, not level data or a saved player state. The
terrain and loot reference implementations live in ref_world and ref_items.
"""

# Class-only probe with model index left at zero and debug switches
# zero-initialized. These tuples are not portable starting-equipment data.
START_WEAPONS = {
    0: ("axe",), 1: ("mace",), 2: ("shortsword",),
    3: ("shortsword", "shortbow"), 4: ("quarterstaff",),
    5: ("throwingaxe", "axe"), 6: ("club",),
}
START_CALL_COUNTS = {
    0: (7, 10, 4), 1: (7, 10, 4), 2: (7, 10, 4),
    3: (10, 13, 5), 4: (7, 10, 4), 5: (8, 11, 5),
    6: (7, 10, 4),
}


def gold_credit(frame, start, floater, pending, credited):
    """hud_tickGold's one-slot ledger after hud_addGoldFloater at start."""
    if floater and (frame - start) * 3 > 127:
        pending += floater
        floater = 0
    if pending:
        payment = (pending + 7) // 8
        pending -= payment
        credited += payment
    return floater, pending, credited
