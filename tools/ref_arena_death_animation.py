"""Bounded death-clip and corpse rule for the recipe-0 Goblin.

The clip header is supplied from the user's disc at run time. The clock and
ended-bit contract comes from anim_advance 0x16d748; the deletion condition
comes from Creature_deadUpdate 0x1108a0. This is not a full AI scheduler.
"""

import ref_anim as A
from ref_core import from_int


def ended_track(clip_data, track_flags):
    """Return the held time and ended-state mask for a REPORT_END track."""
    clip = A.Clip(clip_data)
    if not track_flags & A.REPORT_END:
        raise ValueError('death track must report its end')
    return from_int(clip.length), A.STATUS_ENDED | A.STATUS_TOP_ENDED


def corpse_delete_requested(creature_flags, anim_count, anim_flags, hold):
    """0x1108a0 non-sinking corpse deletion branch."""
    if creature_flags & 0x1000000:
        raise ValueError('sinking-corpse branch is outside this bounded model')
    return bool(hold and anim_count == 1 and anim_flags & 0x80)
