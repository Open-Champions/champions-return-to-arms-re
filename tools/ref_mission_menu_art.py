"""Data-free submission model for the US v2.00 hub mission map.

Coordinates are arguments to the original UI draw API, not screen pixels.
The centred viewports cover all twelve authored rows; icon/layout details
cover the first viewport and its controlled state.
"""

MISSION_PICTURES = (
    ('misswar.tex', 140, 40), ('missinnovation.tex', 70, 240),
    ('misspit.tex', 140, 440), ('misswater.tex', 70, 640),
    ('misstorment.tex', 140, 840), ('missdisease.tex', 70, 1040),
    ('missvalor.tex', 140, 1240), ('missfire.tex', 70, 1440),
    ('missstorms.tex', 140, 1640), ('missfeydark.tex', 70, 1840),
    ('missnightmare.tex', 140, 2040), ('missfear.tex', 70, 2240),
)
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
EVIL_ALTERNATES = {5: (None, 'swamp2', None),
                   9: (None, 'fay1', None),
                   11: ('Plane_of_Tranquil', 'bossevil', 'missairend.tex')}

FRAME_STRIPS = tuple((x, y, 3) for y in range(0, 448, 128) for x in (0, 608))
FIRST_VIEW = (
    ('misswar.tex', 140, 40, 0x7f808080),
    ('missinnovation.tex', 70, 240, 0x7f3c3c3c),
    ('misspit.tex', 140, 440, 0x7f3c3c3c),
)
FIRST_PIPES = (("pipe1.tex", 186, 181, 0x7f3c3c3c),
               ("pipe2.tex", 186, 381, 0x7f3c3c3c),
               ("pipe1.tex", 186, 581, 0x7f3c3c3c))
GLOWS = {0: ('mainglow.tex', 300, 44),
         1: ('amuletglow.tex', 198, 73),
         2: ('bonusglow.tex', 152, 85)}
DETAIL_SUFFIX = {0: '_mis', 1: '_med', 2: '_bon'}
MSEL_SIZES = {
    'frame.tex': (32, 128), 'cosmiclines.tex': (640, 448),
    'starfield.tex': (640, 448), 'starsparkle.tex': (640, 448),
    'misswar.tex': (411, 156), 'missinnovation.tex': (411, 156),
    'misspit.tex': (411, 156), 'pipe1.tex': (249, 74),
    'pipe2.tex': (249, 74), 'shard.tex': (35, 34),
    'amulet1.tex': (53, 52), 'amulet2.tex': (53, 52),
    'amulet3.tex': (53, 52), 'bonus.tex': (33, 34),
    'mainglow.tex': (256, 146),
    'amuletglow.tex': (88, 88), 'bonusglow.tex': (64, 62),
    'missair.tex': (411, 156), 'pipe3.tex': (249, 74),
    'pipe4.tex': (91, 250), 'pipe5.tex': (324, 16),
    'pipe6.tex': (84, 228),
}
MSEL_SIZES.update({name: (411, 156) for name, _, _ in MISSION_PICTURES})
MSEL_SIZES['missairend.tex'] = (411, 156)
FIRST_ICONS = {
    (1, 0): (),
    (1, 1): (('amulet1.tex', 215, 91),),
    (1, 2): (('amulet2.tex', 215, 91),),
    (1, 3): (('amulet3.tex', 215, 91), ('bonus.tex', 167, 99)),
    (3, 0): (('shard.tex', 283, 101), ('amulet2.tex', 215, 91)),
    (3, 3): (('shard.tex', 283, 101), ('amulet3.tex', 215, 91),
             ('amulet2.tex', 215, 91), ('bonus.tex', 167, 99)),
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
