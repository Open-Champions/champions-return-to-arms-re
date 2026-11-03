"""Additive mission-2 route list. Existing offer and travel models are unchanged.

The list is the one original reset and current-level insertion leave behind.
It is not a successful load, a save image, or a physical walk.
"""

HUBS = ('hub', 'hub2')


def resolver_hub(evil, decision, mission1_complete):
    """game_getHubName 0x1ec300 for one difficulty row. Bits are 0 or 1."""
    if evil and decision and mission1_complete:
        return 'hub2'
    return 'hub'


def reset_destinations(latch, previous, hub):
    """jumpgate_resetDestinations 0x27db00. Latch 1 is g_cardXferLatch 0x4f8f28."""
    if latch:
        return list(previous)
    return [hub]


def add_current(entries, current, hub):
    """jumpgate_addCurrentLevel 0x27db60.

    A current name that is already present returns immediately, and the
    resolver is not consulted. Otherwise the name is appended, then the walk
    removes the first hub or hub2 entry that is not the resolver result and
    returns. A second copy of that other hub name stays. `hub` is the
    resolver result.
    """
    entries = list(entries)
    if current in entries:
        return entries
    entries.append(current)
    for index, name in enumerate(entries):
        if name in HUBS and name != hub:
            del entries[index]
            break
    return entries


def scripts_admitted(task_registered):
    """Dialog script entry follows task_isRunning, including a zero counter.

    The zero-counter registration is the audited mission-unlocks result at
    e5c6176. This does not re-derive the cancellation countdown.
    """
    return not task_registered


def route_list(hub, levels):
    """Reset, then insertion at each named arrival. `levels` are ordinary route names."""
    entries = reset_destinations(0, [], hub)
    for level in levels:
        entries = add_current(entries, level, hub)
    return entries
