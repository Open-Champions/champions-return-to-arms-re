"""Control model for the ordinary mission-1 completion entries.

The scaled-time test is the caller's oracle (the original `getScaledTime`).
This module does not load the executable or the disc.
"""


def delay_copy(counter, noticed, scaled):
    """One unpaused `bossDefeatedDelay` copy.

    Returns (counter, noticed, requeue, ended). `ended` is the call to
    `endmission`. A copy that ends does not add the trailing requeue; the
    notice requeue, if this copy just passed 250, still happens.
    """
    counter += 1
    requeue = 0
    if scaled(counter) > 250 and not noticed:
        noticed = True
        requeue += 1
    ended = scaled(counter) > 1500
    if not ended:
        requeue += 1
    return counter, noticed, requeue, ended


def evil_end_frame(scaled, limit=4000):
    """Deferred-call index of the run that first reaches `endmission`.

    Index 0 is the first `script_runDeferred` after the death entry. That
    call only promotes the queued name; the delay body starts on the next
    call. The counter starts at 0, which is what `bossDefeatedPause` stores.
    """
    counter = 0
    noticed = False
    queued = 1
    notice_frame = None
    for frame in range(limit):
        # Call 0 only promotes the name the death entry queued.
        if frame == 0:
            continue
        running, queued = queued, 0
        ended = False
        for _ in range(running):
            counter, noticed, more, this_end = delay_copy(counter, noticed, scaled)
            queued += more
            if noticed and notice_frame is None:
                notice_frame = frame
            if this_end:
                ended = True
        if ended:
            return {"frame": frame, "counter": counter, "notice_frame": notice_frame,
                    "queued_after": queued}
    raise RuntimeError("delay did not reach endmission")


def _shard_passes(paused_prefix=0, limit=200):
    """Deferred-call indexes on which the 25-count check runs.

    `start` queues the loop into the back half, so call 0 only promotes it.
    Later calls run one copy. The copy increments unless this call index is
    below `paused_prefix`.
    """
    counter = 0
    hits = []
    for frame in range(limit):
        if frame == 0:
            continue
        if frame >= paused_prefix:
            counter += 1
        if counter == 25:
            counter = 0
            hits.append(frame)
    return hits


def shard_check_frame(which=1, paused_prefix=0):
    """`which` is 1-based."""
    return _shard_passes(paused_prefix)[which - 1]


def shard_grant_frame(live_after, snapshot=0, paused_prefix=0, limit=200):
    """Deferred-call index of the check that sees the item count rise."""
    for frame in _shard_passes(paused_prefix, limit):
        if live_after(frame) > snapshot:
            return frame
    return None
