"""US v2.00 constructor call contracts for the valor loader probe.

Only executable addresses and call-site structure live here.  Resource results
are deliberately absent: a zero-returning ee_emu stub is not a loaded asset.
"""

CONSTRUCTORS = {
    "WarBoar": (0x2BA03C, 0x3D8, 0x502F80),
    "WarBoarSmall": (0x2BA03C, 0x3D8, 0x502F80),
    "Minotaur": (0x288FDC, 0x470, 0x501200),
}

BOAR_CALLS = (
    (0x2BA0A8, 0x109D68), (0x2BA138, 0x159C20),
    (0x2BA184, 0x179550), (0x2BA19C, 0x1707B0),
    (0x2BA1BC, 0x170838), (0x2BA1CC, 0x14F2B8),
    (0x2BA1F8, 0x118378), (0x2BA224, 0x118378),
    (0x2BA250, 0x118378), (0x2BA27C, 0x118378),
    (0x2BA2B0, 0x118378), (0x2BA2DC, 0x118378),
    (0x2BA308, 0x118378), (0x2BA310, 0x10A230),
)

MINOTAUR_CALLS = (
    (0x289038, 0x109D68), (0x28914C, 0x3B81A0),
    (0x2891D0, 0x11BC18), (0x2891F8, 0x11BC18),
    (0x289200, 0x1509D0), (0x289224, 0x179550),
    (0x28923C, 0x1707B0), (0x289254, 0x28A16C),
    (0x28925C, 0x14F2B8), (0x289288, 0x118378),
    (0x2892B4, 0x118378), (0x2892E8, 0x118378),
    (0x28931C, 0x118378), (0x289348, 0x118378),
    (0x289374, 0x118378), (0x2893A0, 0x118378),
    (0x2893CC, 0x118378), (0x2893D4, 0x10A230),
)

EVENT_ENTRIES = {
    "WarBoar": (4, 5, 6, 7, 10, 11, 12),
    "WarBoarSmall": (4, 5, 6, 7, 10, 11, 12),
    "Minotaur": (5, 6, 7, 8, 9, 13, 3, 4),
}

# (entry index, four integer event masks, four raw f32 event times).
# These are instructions' arguments, independent of any archive bytes.
EVENT_ARGUMENTS = {
    "WarBoar": (
        (4, (1, 2, 0, 0), (0x3E999999, 0x3F333333, 0, 0)),
        (5, (1, 2, 0, 0), (0x3E999999, 0x3F000000, 0, 0)),
        (6, (1, 2, 0, 0), (0x3E999999, 0x3F333333, 0, 0)),
        (7, (1, 2, 0, 0), (0x3E999999, 0x3F000000, 0, 0)),
        (10, (1, 2, 0, 0), (0x3F000000, 0x3F666666, 0, 0)),
        (11, (0x84, 0, 0, 0), (0x3F800000, 0, 0, 0)),
        (12, (0x84, 0, 0, 0), (0x3F800000, 0, 0, 0)),
    ),
    "Minotaur": (
        (5, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
        (6, (1, 1, 0, 0), (0x3E4CCCCC, 0x3F199999, 0, 0)),
        (7, (1, 0, 0, 0), (0x3ECCCCCC, 0, 0, 0)),
        (8, (1, 4, 0, 0), (0x3E4CCCCC, 0x3EB851EB, 0, 0)),
        (9, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
        (13, (1, 0, 0, 0), (0x3E4CCCCC, 0, 0, 0)),
        (3, (1, 0, 0, 0), (0x3F199999, 0, 0, 0)),
        (4, (1, 0, 0, 0), (0x3F199999, 0, 0, 0)),
    ),
}
EVENT_ARGUMENTS["WarBoarSmall"] = EVENT_ARGUMENTS["WarBoar"]

DEFINITION_SLOTS = {"warboar.lmp": 20, "minotaur.lmp": 26}
