"""Additive, independently authored exit prompt and request rules.

Evidence: docs/exits-r3-handoff.md. Synthetic inputs only; no loader or VM model.
"""

def first_active(network, count, connected, inactive):
    # 0x13e5a0: only slots within the connected prefix can qualify online.
    return next((i for i in range(count)
                 if not network or (i < connected and not inactive[i])), 0)


def keyed_prompt(network, host_only, slot, host, keys, message, lock, host_lock):
    """Return usable, presentation category, predicate indices evaluated."""
    if network and host_only and slot != host:
        return 0, 'host' if host_lock else None, ()
    visited = []
    for i, value in enumerate(keys):
        visited.append(i)
        if not value:
            return 0, 'lock' if lock else None, tuple(visited)
    return 1, 'message' if message else None, tuple(visited)


def request(network, active, cooldown, alive, post, simple, orientations):
    """Allowed, new cooldown, orientation; rejected requests preserve buffers.

    orientations lists exact lower-case orientation= decimal properties in order.
    Other property spelling is outside this helper's input contract.
    """
    gated = not post and network and active != -1
    if gated and cooldown and alive >= 2:
        return False, cooldown, None
    updated = 600 if gated else cooldown
    orientation = 255 if simple or not orientations else orientations[-1] & 255
    return True, updated, orientation
