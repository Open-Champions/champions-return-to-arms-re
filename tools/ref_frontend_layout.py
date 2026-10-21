"""Observed frontend list geometry for SLUS-20973 v2.00.

Coordinates are the calls submitted by menuList_draw (0x1a07c4), in the
640 x 448 UI space. Text width and the frame's final width need a loaded font;
the minimum frame below is the result when the width callee returns zero.
"""

# Keys are local geometry aliases. Names for the less-used tables are
# descriptive only; this capture does not establish their menu semantics.
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

FRONTEND_STATES = {
    0: ("main", 309),
    1: ("game_type", 309),
    2: ("players", 309),
    3: ("difficulty", 309),
    4: ("mode_two", 309),
    11: ("options", 238),
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


def list_frame_calls(count, value_rows=(), origin=(320, 309)):
    """Three calls reaching ui_drawFrameImpl for selected row zero.

    Tuples are x, y, width, height, layer, tint, style, no_center. The ninth
    no_border argument is zero in these captures. Source textures follow
    research-ui's menu_frame: style 0 = ctile*, style 2 = tile*.
    """
    anchors, wrapper = list_geometry(count, value_rows, origin)
    x, y, w, h, layer, tint = wrapper
    wide = bool(value_rows)
    selected_y = anchors[0][1]
    if 0 in value_rows:
        cursor_x, cursor_w = origin[0] - 140, 280
    elif wide:
        cursor_x, cursor_w = origin[0] - 21, 42
    else:
        cursor_x, cursor_w = origin[0] - 20, 40
    return [
        (cursor_x, selected_y, cursor_w,
         32 + (selected_y & 1), 7, 0x300000FF, 0),
        (x - 1, y - 4, w + 2, h + 8, layer, tint, 2),
        (x + 8, y + 8, w, h, 6, 0x3F000000, 0),
    ]


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


# Direct call sites observed with a zeroed state and all callees stubbed.
# These establish entry paths only; deeper art, text and sounds need fixtures.
BOOT_CARD_CALLS = ((0x323974, 0x21755C), (0x323988, 0x3236BC))
BOOT_STEP_CALLS = ((0x3238FC, 0x2189E0),)
INTRO_CALLS = ((0x321790, 0x19DD48), (0x3217BC, 0x215C20),
               (0x3217C8, 0x173558), (0x3217D0, 0x211C18),
               (0x32180C, 0x320498))
CARD_DRAW_DISPATCH = {
    -1: (), 0: ((0x218A98, 0x219A88),),
    1: ((0x218AA8, 0x219B14),),
    3: ((0x218A48, 0x218AFC), (0x218A58, 0x13E4E8)),
    4: ((0x218A68, 0x219360),),
    5: ((0x218A78, 0x21F390),),
    6: ((0x218A88, 0x21F6DC),),
    9: ((0x218AB8, 0x21FA2C),),
    10: ((0x218AC8, 0x222B40),),
}


# Main-list accept on row i (state 0, table 0x4f6b88), executed with the original
# string comparison 0x3b8534 and input 0x1a01d0 followed. The selected index lives
# in the word 0x4f6bcc (terminator entry +4). Value: (next state, next table,
# ((call site, target), ...), music resource and flags requested by 0x2110e0).
# Row 1 stays in state 0 and requests a card load; its slot argument is -1 + 1.
MAIN_MENU_ACCEPT = {
    0: (1, 0x4F6BF8, ((0x1E15B8, 0x214230),), None),
    1: (0, 0x4F6B88, ((0x1E15B8, 0x214230), (0x1E166C, 0x2176E0)), None),
    2: (11, 0x4F6E88, ((0x1E15B8, 0x214230), (0x1E16A0, 0x1E6428)), None),
    3: (15, 0x4F6FB8, ((0x1E15B8, 0x214230), (0x1E16E4, 0x216130),
                       (0x1E16F4, 0x2110E0), (0x1E16FC, 0x223C64)),
        ("mx_endcredits_ext_l.vag", 3)),
}


# frontend_run state 15 (credits): each frame it runs credits_run 0x223d3c at
# 0x1e1124. A zero return ends the credits: 0x211338(2) at 0x1e113c, the
# frontend theme requested again with flags 1 at 0x1e114c, then state 0 and the
# main table (the state-10 lobby branch needs a flag at 0x87ad58 and was not
# exercised). A nonzero return leaves state 15 untouched.
CREDITS_EXIT_FINISHED = (0, 0x4F6B88, ((0x1E113C, 0x211338), (0x1E114C, 0x2110E0)),
                         ("mx_maintheme_l.vag", 1))
CREDITS_EXIT_RUNNING = (15, 0x4F6FB8, (), None)


# Which font word each text_begin call reads, found by planting distinct sentinel
# values in the two font pointer words (0x4f7100 medium, 0x4f7104 small; see
# research-ui docs/formats/ui-fonts.md). (site, font, layer, colour) per fixture.
# The list's own text_begin (0x1a09e8) takes its font from the caller: the front
# end passes the medium word; the pause fixture passes a zero word (font Unknown).
FONT_USES = {
    "frontend_list_state0": ((0x1E0DCC, "small", 7, 0x64464646),
                             (0x1A09E8, "medium", 7, 0)),
    "frontend_difficulty_extra": ((0x1E13C8, "small", 6, 0x082D5049),),
    "name_entry": ((0x22C9C0, "medium", 6, 0x585E5D),
                   (0x22D0E4, "small", 6, 0x316864),
                   (0x22D198, "medium", 6, 0x585E5D)),
    "credits": ((0x223E40, "medium", 7, 0x80000000),),
    "pause": ((0x18D5E8, "medium", 7, 0x80464646),),
}


def credits_one_line_geometry(scroll_y):
    """Two centered submissions for one authored wide-string pointer.

    The first is the offset/shadow pass and the second is the main pass.
    This fixture does not establish the real credits resource layout.
    """
    return ((0x22401C, 322, scroll_y + 2),
            (0x224044, 320, scroll_y))


MUSIC_VOLUME_GATE_BITS = 0x3D4CCCCC  # comparison in music_playGlobal 0x2110e0


def first_theme_queues(volume):
    """Whether music_playGlobal enqueues the frontend's initial theme.

    The input is a finite IEEE-754 bit pattern. Negative volumes do not queue.
    Nonfinite values are excluded from this reference model.
    """
    volume &= 0xFFFFFFFF
    if volume & 0x7F800000 == 0x7F800000:
        raise ValueError("finite volume required")
    return not volume & 0x80000000 and volume >= MUSIC_VOLUME_GATE_BITS
