"""Bounded idle target-scan clock for recipe-0 arena creatures.

Creature_pickTarget 0x10ded0 scans when (g_simFrame 0x44fdcc XOR the
creature's signed serial byte +0x230) has low five bits zero. In the
single-player in-range fixture, the first scan links that player. This
models only the idle target clock, not class combat decisions.
"""


def first_scan(serial, frames):
    """First 0x10ded0 scan frame, or None if outside the bounded run."""
    serial = serial & 0xFF
    if serial & 0x80:
        serial -= 0x100
    return next((frame for frame in range(frames)
                 if ((frame ^ serial) & 0x1F) == 0), None)


def target_present(frame, serial, frames):
    """One eligible player stays linked from the first scan onward."""
    scan = first_scan(serial, frames)
    return scan is not None and frame >= scan


def target_link_frames(serial, frames):
    """In a stationary one-player idle fixture, the first scan creates one link."""
    scan = first_scan(serial, frames)
    return [] if scan is None else [scan]
