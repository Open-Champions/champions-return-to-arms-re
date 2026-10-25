"""Small, authored options-menu contract for the US v2.00 executable.

Only resource identifiers, addresses and synthetic input/output values appear here.
The option labels are resolved by the game's localized resources at runtime.
"""

# (lookup key, menu-list kind, live value address); 0 has no direct value.
ROWS = (
    ("menu_bright", 4, 0x44FD80),
    ("menu_music", 4, 0x4F8944),
    ("menu_sfx", 4, 0x4F8940),
    ("menu_controls", 0, 0),
    ("menu_combatCam", 3, 0x4F845C),
    ("menu_reverseYaw", 3, 0x4F8460),
    ("menu_vibration", 3, 0x41BFB0),
    ("menu_stereo", 3, 0x4F8948),
    ("menu_blood", 3, 0x44FDC0),
    ("menu_subtitles", 3, 0x44FCF4),
    ("menu_damagedisplay", 3, 0x44FCF8),
    ("menu_chat", 3, 0x50391C),
    ("menu_markers", 3, 0x4F8458),
)

# Golden results of single slider steps from synthetic starting values.
# Values are IEEE-754 words; the PS2 FPU's last bit is captured, not guessed.
SLIDER_STEPS = (
    (0x00000000, 0x2000, 0x3C088888),
    (0x00000000, 0x8000, 0x00000000),
    (0x3F000000, 0x2000, 0x3F022222),
    (0x3F000000, 0x8000, 0x3EFBBBBB),
    (0x3F800000, 0x2000, 0x3F800000),
    (0x3F800000, 0x8000, 0x3F7DDDDD),
)

TOGGLE_STEPS = ((0, 1), (1, 0), (2, 0))

GEOMETRY = {
    0x4F6E88: (
        tuple((297 if row < 3 else 320, 89 + 22 * row) for row in range(13)),
        ((180, 89, 280, 33, 7, 0x300000FF, 0),
         (214, 78, 212, 320, 7, 0x80808080, 2),
         (223, 90, 210, 312, 6, 0x3F000000, 0)),
    ),
    0x44F218: (
        tuple((297 if row < 3 else 320, 80 + 22 * row) for row in range(14)),
        ((180, 80, 280, 32, 7, 0x300000FF, 0),
         (214, 69, 212, 342, 7, 0x80808080, 2),
         (223, 81, 210, 334, 6, 0x3F000000, 0)),
    ),
}
