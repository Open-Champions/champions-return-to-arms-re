"""Observed frontend list geometry for SLUS-20973 v2.00.

Coordinates are the calls submitted by menuList_draw (0x1a07c4), in the
640 x 448 UI space. Text width and the frame's final width need a loaded font;
the minimum frame below is the result when the width callee returns zero.
"""

TABLES = {
    "main": (0x4F6B88, 4, ()),
    "game_type": (0x4F6BF8, 2, ()),
    "mode_three": (0x4F6C28, 3, ()),
    "mode_two": (0x4F6C68, 2, ()),
    "kill_limit": (0x4F6C98, 3, ()),
    "missions": (0x4F6CD8, 13, ()),
    "net_role": (0x4F6DB8, 2, ()),
    "players": (0x4F6DE8, 4, ()),
    "difficulty": (0x4F6E38, 4, ()),
    "options": (0x4F6E88, 13, (0, 1, 2)),
    "communications": (0x4F6F68, 4, (2, 3)),
    "player_options": (0x4F6FC8, 4, ()),
}


def list_geometry(count, value_rows=(), origin=(320, 309)):
    """Return centred-text anchors and the minimum frame call for one list."""
    x, y = origin
    first = y - (11 * count + 6)
    value_rows = frozenset(value_rows)
    anchors = [(x - (23 if i in value_rows else 0), first + 22 * i)
               for i in range(count)]
    wide = bool(value_rows)
    frame = (x - (105 if wide else 27), first - 7,
             210 if wide else 54, 22 * count + 26, 7, 0x80808080)
    return anchors, frame


def pause_geometry():
    """Normal offline table's five enabled rows at 0x44f3b8."""
    return list_geometry(5, origin=(320, 240))


def publisher_logo_sprites():
    """Two unclipped ui_drawSprite submissions from splash_soeLogo 0x321640."""
    return (("soe_splash_url.tex", 192, 330, 3, 0x80808080),
            ("soe_splash.tex", 64, 50, 3, 0x80808080))


# Resource IDs passed to lump lookup before sound_playOnObject. An attempted
# cancel on the main menu has no transition and makes no sound in this fixture.
MENU_SOUND_IDS = {
    "move": "menu_main_toggle.anm",
    "select": "menu_main_accept.anm",
    "back": "menu_main_back.anm",
    "main_cancel": None,
}


MUSIC_VOLUME_GATE_BITS = 0x3D4CCCCC  # comparison in music_playGlobal 0x2110e0


def first_theme_queues(volume):
    """Whether music_playGlobal enqueues the frontend's initial theme.

    The tested finite nonnegative volumes use the positive IEEE-754 bit order.
    """
    return (volume & 0xFFFFFFFF) >= MUSIC_VOLUME_GATE_BITS
