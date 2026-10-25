"""What setState does when two field conditions are true together.

Round 3's `select` records one field at a time and raises on any other
condition. These functions do not change that. They cover the combinations
round 3 left open, executed by calling the original setState with both
values stored (difftest_field_precedence.py). Stubbed callees, not a game.

Agony state 0x12 is the case monsters-2 already described: pending-damage
bits 0x380000 against bit 0x40000 on word +0x2dc.
"""

# Any of these bits selects the knockback clip. 0x80000 | 0x100000 | 0x200000.
AGONY_KNOCK_MASK = 0x380000
AGONY_HIT_BIT = 0x40000


def agony_hit_entry(flags):
    """Blend entry for Agony setState 0x234168, request 0x12, word +0x2dc.

    Executed: any bit of 0x380000 → entry 0xd; else bit 0x40000 → entry 9;
    else entry 0xa. Both a knockback bit and 0x40000 follow 0xd. Other bits
    do not change the winner (0x40001 is still 9; 0xffffffff is still 0xd).
    """
    flags &= 0xffffffff
    if flags & AGONY_KNOCK_MASK:
        return 0xd
    if flags & AGONY_HIT_BIT:
        return 9
    return 0xa


def clockwork_idle_entry(form):
    """Clip entry for Clockwork setState state 0, field +0x3c8.

    The field is a form index compared for equality, not a bit mask. The
    bitwise OR of two indices is a third index: 1|2 == 3 plays form 3
    (entry 40); 2|4 == 6 is not a form and the start is given a null clip.
    Executed for
    0..6. Entry 10 * (form + 1) for forms 1..5; form 0 is the default
    entry 10; anything else is None.
    """
    if form == 0:
        return 0xa
    if 1 <= form <= 5:
        return 10 * (form + 1)
    return None


# Both fields set. ops are the animation and holder calls, in order:
# (fn, entry or None, flags or None). stored is the u16 at +0x232.
# The winner is the field whose single-field result this matches.
# setState addresses are the round-3 DISPATCH rows, not repeated here.
COMBINED = (
    # FemaleDarkElf 0x12: +0x2dc bit 0x80000 beats form +0x3c8 = 1.
    dict(cls='FemaleDarkElf', state=0x12,
         fields=((0x2dc, 0x80000), (0x3c8, 1)), winner=0x2dc, stored=0x12,
         ops=(('anim_start', 4, 0x14),
              ('anim_pushChained', 5, 0x24),
              ('anim_pushChained', 26, 0x2))),
    # Horsemen death: form +0x3c8 = 1 stores state 0 and starts nothing,
    # which beats +0x470 = 3 (that alone keeps state 0x14).
    dict(cls='Horsemen', state=0x14,
         fields=((0x3c8, 1), (0x470, 3)), winner=0x3c8, stored=0,
         ops=()),
    # VampireLord: form +0x3c8 = 1 beats +0x3cc = 1.
    dict(cls='VampireLord', state=3,
         fields=((0x3c8, 1), (0x3cc, 1)), winner=0x3c8, stored=3,
         ops=(('anim_start', 16, 0x803), ('anim_syncToSimFrame', None, None))),
    dict(cls='VampireLord', state=5,
         fields=((0x3c8, 1), (0x3cc, 1)), winner=0x3c8, stored=5,
         ops=(('anim_start', 7, 3), ('anim_syncToSimFrame', None, None))),
    dict(cls='VampireLord', state=0x11,
         fields=((0x3c8, 1), (0x3cc, 1)), winner=0x3c8, stored=0x11,
         ops=(('anim_start', 11, 3),)),
    # Clockwork death: form +0x3c8 beats object flag +0xc = 2.
    dict(cls='Clockwork', state=0x14,
         fields=((0xc, 2), (0x3c8, 1)), winner=0x3c8, stored=0x14,
         ops=(('anim_start', 16, 0x806), ('vslot', 28, None))),
    dict(cls='Clockwork', state=0x14,
         fields=((0xc, 2), (0x3c8, 4)), winner=0x3c8, stored=0x14,
         ops=(('anim_start', 46, 0x806), ('vslot', 28, None))),
)


def combined(cls, state, fields):
    """The executed ops when every (offset, value) in `fields` is set."""
    key = (cls, state, tuple(fields))
    for row in COMBINED:
        if (row['cls'], row['state'], row['fields']) == key:
            return row['ops'], row['stored']
    raise KeyError(key)
