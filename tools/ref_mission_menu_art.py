"""Data-free submission model for the US v2.00 hub mission map.

Coordinates are arguments to the original UI draw API, not screen pixels.
The centred viewports cover all twelve authored rows; icon/layout details
cover the first viewport and its controlled state.

Textures are named by the address of the name string the code passes to the
resource lookup (0x17365c), never by the name itself: the names are read from
the owner's executable at run time (tools/difftest_mission_menu_art.py).
"""

# name strings of the mission-map lump, by address
S_LUMP = 0x541188                               # the lump itself
S_FRAME = 0x541198
S_SHARD = 0x5411A8
S_AMULET = {1: 0x5411D8, 2: 0x5411C8, 3: 0x5411B8}
S_BONUS = 0x5411E8
S_GLOW = {0: 0x5411F8, 1: 0x541208, 2: 0x541218}
S_PIPE = {1: 0x541228, 2: 0x541238, 3: 0x541248, 4: 0x541258, 5: 0x541268, 6: 0x541278}
S_COSMIC, S_STARS, S_SPARKLE = 0x541300, 0x541310, 0x541320
S_ROW_PICTURE = (0x540DA0, 0x540DF0, 0x540E20, 0x540E68, 0x540EC0, 0x540F18,
                 0x540F58, 0x540FA0, 0x540FE8, 0x541018, 0x541068, 0x5410C8)
S_ROW11_EVIL = 0x5410D8
S_SOUND_ACCEPT, S_SOUND_TOGGLE = 0x541128, 0x541140

MISSION_TABLE, MISSION_ROW = 0x4FE540, 0x34
MISSION_PICTURES = tuple(zip(S_ROW_PICTURE,
                             (140, 70) * 6,
                             range(40, 2241, 200)))
MISSION_ENTRIES = (
    ('Plane_of_War', 'blood1', 'blomedal', 'boar1'),
    ('Plane_of_Innovation', 'innovat1', 'innmedal', 'innpit'),
    ('Norrath_Pit', 'islc1', None, None),
    ('Plane_of_Water', 'wat1', 'watmedal', 'watbonus'),
    ('Plane_of_Torment', 'tormenta', 'tormedal', 'torbonus'),
    ('Plane_of_Disease', 'swamp1', 'dismedal', 'disbonus'),
    ('Plane_of_Valor', 'valor', 'valmedal', 'honor2'),
    ('Plane_of_Fire', 'fire1', 'firmedal', 'firbonus'),
    ('Plane_of_Storms', 'storm1', 'stomedal', 'stobonus'),
    ('Norrath_Faydark', 'fay2', None, None),
    ('Plane_of_Nightmares', 'nit1', 'nitmedal', 'nitbonus'),
    ('Plane_of_Fear', 'bossgood', None, None),
)
# evil alternates: (title, level) as text; the picture by its string address
EVIL_ALTERNATES = {5: (None, 'swamp2', None),
                   9: (None, 'fay1', None),
                   11: ('Plane_of_Tranquil', 'bossevil', S_ROW11_EVIL)}

FRAME_STRIPS = tuple((x, y, 3) for y in range(0, 448, 128) for x in (0, 608))
FIRST_VIEW = tuple((s, x, y, 0x7f808080 if i == 0 else 0x7f3c3c3c)
                   for i, (s, x, y) in enumerate(MISSION_PICTURES[:3]))
FIRST_PIPES = ((S_PIPE[1], 186, 181, 0x7f3c3c3c),
               (S_PIPE[2], 186, 381, 0x7f3c3c3c),
               (S_PIPE[1], 186, 581, 0x7f3c3c3c))
GLOWS = {0: (S_GLOW[0], 300, 44),
         1: (S_GLOW[1], 198, 73),
         2: (S_GLOW[2], 152, 85)}
DETAIL_SUFFIX = {0: '_mis', 1: '_med', 2: '_bon'}
# texture header sizes on the owner's disc, by name-string address (the lump holds 32
# textures; these are the ones the code names)
SIZES = {S_FRAME: (32, 128), S_COSMIC: (640, 448), S_STARS: (640, 448),
         S_SPARKLE: (640, 448), S_SHARD: (35, 34), S_BONUS: (33, 34),
         S_GLOW[0]: (256, 146), S_GLOW[1]: (88, 88), S_GLOW[2]: (64, 62),
         S_PIPE[1]: (249, 74), S_PIPE[2]: (249, 74), S_PIPE[3]: (249, 74),
         S_PIPE[4]: (91, 250), S_PIPE[5]: (324, 16), S_PIPE[6]: (84, 228),
         S_ROW11_EVIL: (411, 156)}
SIZES.update({s: (53, 52) for s in S_AMULET.values()})
SIZES.update({s: (411, 156) for s in S_ROW_PICTURE})
LUMP_TEXTURES = 32
FIRST_ICONS = {
    (1, 0): (),
    (1, 1): ((S_AMULET[1], 215, 91),),
    (1, 2): ((S_AMULET[2], 215, 91),),
    (1, 3): ((S_AMULET[3], 215, 91), (S_BONUS, 167, 99)),
    (3, 0): ((S_SHARD, 283, 101), (S_AMULET[2], 215, 91)),
    (3, 3): ((S_SHARD, 283, 101), (S_AMULET[3], 215, 91),
             (S_AMULET[2], 215, 91), (S_BONUS, 167, 99)),
}


def detail_keys(base, column):
    key = base + DETAIL_SUFFIX[column]
    return key, key + '_title'


def first_view(mission2_available):
    rows = list(FIRST_VIEW)
    pipes = list(FIRST_PIPES)
    if mission2_available:
        name, x, y, _ = rows[1]
        rows[1] = (name, x, y, 0x7f808080)
        name, x, y, _ = pipes[0]
        pipes[0] = (name, x, y, 0x7f808080)
    return tuple(rows), tuple(pipes)


def viewport(selected_row, all_available=False):
    """Centred, noninterpolating draw submissions for authored node rows."""
    return tuple((name, x, y - selected_row * 200, 4,
                  0x7f808080 if i == 0 or all_available else 0x7f3c3c3c)
                 for i, (name, x, y) in enumerate(MISSION_PICTURES)
                 if selected_row <= i < selected_row + 3)
