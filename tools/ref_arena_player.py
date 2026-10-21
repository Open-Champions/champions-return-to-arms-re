"""Bounded Player constructor contract for the offline arena fixture.

All values are independently expressed as field operations.  The constructor's
resource, Creature base, light, model and world services are call boundaries;
the fixture supplies a five-part model definition and zero-return services.
No executable or asset bytes are embedded here.
"""

CTOR = 0x1A1D28
SEED = 0x404464
RECORDS = 0x4D8AF0
RECORD_SIZE = 0x4C30
VTABLE = 0x511308

CALLS = (
    0x109D68, 0x148AF8, 0x14A4F0, 0x3B7EF0, 0x17365C,
    0x3B7EF0, 0x17365C, 0x355490, 0x1707B0, 0x1B2470,
    0x14F248, 0x183820, 0x1B6458, 0x3B60C0, 0x3B60C0, 0x1E72F8,
)


def constructor_fields(player, slot, model_part):
    """Final direct stores for a zeroed, ordinary player with absent appearance parts.

    The base Creature constructor and external services are excluded.  The
    definition fixture points each of its five part cells at ``model_part``.
    Values are (store width, unsigned bit pattern).  Resource-produced handles
    are zero because this fixture gives the resource calls a zero answer.
    """
    p = {}
    def put(width, value, *offsets):
        for offset in offsets:
            p[player + offset] = (width, value)

    put(4, VTABLE, 0x48)
    put(4, 0, *(0x3D8 + 0x18 * i for i in range(5)))
    put(4, 0, 0x4B8, 0x500, 0x588, 0x548, 0x558, 0x54C, 0x554, 0x544, 0x550)
    put(1, 0, 0x4D1, 0x4D0, 0x50D, 0x50C, 0x462, 0x3CC, 0x47B,
        0x47C, 0x47D, 0x47F, 0x481, 0x490, 0x463, 0x47A, 0x480)
    for offset in (0x4F8, 0x4FC):
        put(4, 0, offset)
    put(2, 0xBC, 0x4DE, 0x4D2, 0x4D4, 0x4D6, 0x4DA, 0x4DC)
    put(2, 0xFFC0, 0x4E0, 0x4D8)
    put(4, 0x43960000, 0x4EC, 0x4E4)
    put(4, 0x373A69DB, 0x4F0, 0x4E8)
    put(4, 0, 0x4F4, 0x64, 0x68, 0x6C, 0x60, 0x5C, 0x70, 0x74, 0x78,
        0x7C, 0x80, 0x84, 0x88, 0x8C, 0x45C, 0x458, 0x454, 0x484,
        0x488, 0x450, 0x6C)
    put(4, 0, *(0x36C + 4 * i for i in range(16)))
    put(4, 0xFFFFFFFF, 0x4A8)
    put(1, 0x30, 0x28)  # first byte of the authored model-name buffer
    put(4, 0x4040, 0xC)
    put(4, slot, 0x3C8)
    put(4, 0x3FB33333, 0xB0)
    put(4, 0x41400000, 0x1C)
    put(4, 0x3FCCCCCC, 0x470)
    put(4, 2, 0x58C)
    put(1, 1, 0x461, 0x565)
    put(2, 0xE10, 0x4B2)
    put(2, 0, 0x4AE)
    put(2, 0, 0x4B0)
    put(4, 0x3F400000, 0x18)

    # Five model-part cells receive the same animation setup. The cell's
    # +0x14/+0x1c words and +0x18/+0x20 bytes are the final values.
    part = {model_part + 0x14: (4, 0x3E800000),
            model_part + 0x1C: (4, 0x3F400000),
            model_part + 0x18: (1, 1), model_part + 0x20: (1, 1)}
    return p | {
        RECORDS + slot * RECORD_SIZE + 0x43D8: (4, player),
        RECORDS + slot * RECORD_SIZE + 0x4BC8: (1, 0),
    } | part
