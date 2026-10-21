#!/usr/bin/env python3
"""ref_level_factory.py - which level records world_objectFactory 0x159c94 turns into objects.

Reference contract for docs/script-session.md section 3 (and docs/objects.md, "The object
factory").  The factory takes a record's class string and property list and either builds
one object (pool_new(size), then one constructor call), calls a function that builds no
object, or returns 0.  This module says which, for any class string and property list.

Nothing from the game is in this file: the test strings and the property keys are named
by their addresses in SLUS_209.73 v2.00 and read from the user's executable at run time
(the `strings` argument of classify: .string(addr) -> bytes, .ctype(signed index) -> the
C library's class byte at 0x5628e1 + index).

Executed in tools/difftest_level_factory.py: the test chain below is the chain the original
walks for a class string no test accepts (206 tests) plus the two tests nested under the
Skeleton prefix; every test string, case variants, prefixes, the property fall-backs and
every record of the disc's level files are run through the original and compared.

What the factory does that classify assumes:
  * pool_new succeeds.  When the pool has no block of the size class, the original
    returns 0 and calls no constructor (docs/spec/object-system.md 2.1); this module does
    not model the pool.
  * Name tests: "eq" is libc_strcasecmp 0x3b81a0 == 0, "prefix" is str_prefixDiffers
    0x159c20 == 0.  Both lower a character by adding 0x20 when bit 0 of its class byte is
    set (the class table is indexed by the signed character), and compare the results as
    signed characters.  strcasecmp also compares the terminators, so it is a full match.
  * Property tests: props_getInt 0x14f730 and props_getStr 0x14f850 lower the KEY (their
    own argument, in place) the same way and compare it case-sensitively with the start
    of each entry, which must then have '='.  getInt is libc atoi of the rest; a test
    passes when it is non-zero.  getStr passes when an entry exists.  A null list fails
    every property test.
"""

M32 = 0xFFFFFFFF
CLEAR_COLOR = 'clear_color'
CLEAR_COLOR_WORD = 0x506044        # g_backgroundColor, written by the clearColor row
CTYPE = 0x5628E1                   # C library class table, indexed by the signed character

# (kind, test string address, pool size or None, the calls the row makes besides pool_new
#  [, CLEAR_COLOR]) in the order the original tests them.  A row with a size builds one
#  object; the last call is its constructor.  A row without one builds nothing.
TESTS = [
    ('eq', 0x5323F0, 0x4C, (0x158BCC,)),
    ('eq', 0x532408, 0x4C, (0x158C6C,)),
    ('eq', 0x532420, 0x4C, (0x158D0C,)),
    ('eq', 0x532438, None, (), CLEAR_COLOR),
    ('eq', 0x5323E0, None, (0x22E714,)),
    ('eq', 0x532870, 0x3E8, (0x2657A0,)),
    ('eq', 0x532880, 0x1A0, (0x24290C,)),
    ('eq', 0x532890, 0x448, (0x2416C4,)),
    ('eq', 0x5328A0, 0x448, (0x2416C4,)),
    ('eq', 0x5328B0, 0x448, (0x2416C4,)),
    ('eq', 0x5328C0, 0x448, (0x2547FC,)),
    ('eq', 0x5328C8, 0x50, (0x294FA4,)),
    ('eq', 0x5328D0, 0x5C, (0x2958A8,)),
    ('eq', 0x5328E0, 0x448, (0x242BD8,)),
    ('eq', 0x5328E8, 0x1A0, (0x243088,)),
    ('eq', 0x5328F8, 0x1A0, (0x24323C,)),
    ('eq', 0x532908, 0x1A0, (0x243398,)),
    ('eq', 0x532918, 0x198, (0x243594,)),
    ('eq', 0x532928, 0x498, (0x24388C,)),
    ('eq', 0x532938, 0x64, (0x295CF4,)),
    ('eq', 0x532948, 0x98, (0x295FF4,)),
    ('eq', 0x532958, 0x98, (0x295FF4,)),
    ('eq', 0x532968, 0x448, (0x243CD0,)),
    ('eq', 0x532978, 0x448, (0x243CD0,)),
    ('eq', 0x532988, 0x198, (0x243E3C,)),
    ('eq', 0x532998, 0x4C, (0x158928,)),
    ('eq', 0x5329A0, None, (0x30503C,)),
    ('eq', 0x5329B8, None, (0x30503C,)),
    ('eq', 0x5329D0, 0x3D0, (0x23396C,)),
    ('eq', 0x5329E0, 0x3E8, (0x236C70,)),
    ('eq', 0x5329F0, 0x3E8, (0x235418,)),
    ('eq', 0x532A00, 0x3E8, (0x235418,)),
    ('prefix', 0x532A10, 0x3E8, (0x235418,)),
    ('eq', 0x532A18, 0x3C8, (0x234584,)),
    ('eq', 0x532A20, 0x3D8, (0x238BB8,)),
    ('eq', 0x532A30, 0x3D0, (0x244018,)),
    ('prefix', 0x532A40, 0x3D0, (0x244018,)),
    ('eq', 0x532A48, 0x3D0, (0x244E4C,)),
    ('prefix', 0x532A58, 0x420, (0x2AB958,)),
    ('prefix', 0x532A68, 0x470, (0x247FB0,)),
    ('eq', 0x532A78, 0x3E8, (0x24A670,)),
    ('eq', 0x532A88, 0x3E8, (0x24A670,)),
    ('eq', 0x5323D0, 0x3D0, (0x28F5DC,)),
    ('prefix', 0x532A98, 0x500, (0x24E124,)),
    ('prefix', 0x532AA8, 0x538, (0x2500B0,)),
    ('eq', 0x532AB8, 0x500, (0x253148,)),
    ('eq', 0x532AC0, 0x458, (0x2566D4,)),
    ('eq', 0x532AD0, 0x458, (0x2566D4,)),
    ('eq', 0x532AE0, 0x458, (0x2566D4,)),
    ('eq', 0x532AE8, 0x468, (0x257DE8,)),
    ('prefix', 0x532AF8, 0x468, (0x25DC6C,)),
    ('eq', 0x532B00, 0x420, (0x2AB958,)),
    ('eq', 0x532B10, 0x3D0, (0x27B840,)),
    ('eq', 0x532B18, 0x430, (0x28048C,)),
    ('prefix', 0x532B28, 0x478, (0x25947C,)),
    ('eq', 0x532B38, 0x430, (0x24587C,)),
    ('eq', 0x532B40, 0x430, (0x24587C,)),
    ('prefix', 0x532B48, 0x430, (0x24587C,)),
    ('eq', 0x532B58, 0x470, (0x24726C,)),
    ('prefix', 0x532B60, 0x468, (0x263E1C,)),
    ('prefix', 0x532B70, 0x3D8, (0x266088,)),
    ('prefix', 0x532B78, 0x3D8, (0x266088,)),
    ('eq', 0x532B88, 0x3C8, (0x26741C,)),
    ('eq', 0x532B90, 0x3E0, (0x267CF4,)),
    ('eq', 0x532BA0, 0x3C8, (0x269EB8,)),
    ('prefix', 0x532BB0, 0x3D8, (0x268FD4,)),
    ('prefix', 0x532BB8, 0x498, (0x26A624,)),
    ('prefix', 0x532BC0, 0x498, (0x26A624,)),
    ('eq', 0x532BC8, 0x460, (0x26E08C,)),
    ('prefix', 0x532BD0, 0x3D8, (0x26F120,)),
    ('eq', 0x532BD8, 0x4D0, (0x2735DC,)),
    ('eq', 0x532BE8, 0x3E8, (0x27A00C,)),
    ('eq', 0x532BF8, 0x430, (0x28048C,)),
    ('prefix', 0x532C08, 0x3D0, (0x27F0C0,)),
    ('eq', 0x532C10, 0x430, (0x28048C,)),
    ('prefix', 0x532C20, 0x4F8, (0x25AFD8,)),
    ('eq', 0x532C30, 0x4A8, (0x2835A0,)),
    ('eq', 0x532C40, 0x3C8, (0x285B30,)),
    ('eq', 0x532C48, 0x3E8, (0x285F10,)),
    ('prefix', 0x532C50, 0x470, (0x288FDC,)),
    ('prefix', 0x532C60, 0x3C8, (0x297788,)),
    ('eq', 0x532C70, 0x4A0, (0x29AFB4,)),
    ('prefix', 0x532C80, 0x480, (0x298418,)),
    ('eq', 0x532C88, 0x3C8, (0x29D70C,)),
    ('eq', 0x532C90, 0x468, (0x29FAD0,)),
    ('eq', 0x532C98, 0x3D8, (0x270968,)),
    ('prefix', 0x532CA8, 0x488, (0x2A0954,)),
    ('prefix', 0x532CB0, 0x488, (0x217EDC, 0x2A0954,)),
    ('eq', 0x532CB8, 0x418, (0x25F470,)),
    ('eq', 0x532CC8, 0x478, (0x271C70,)),
    ('eq', 0x532CD8, 0x478, (0x271C70,)),
    ('eq', 0x532CE8, 0x478, (0x271C70,)),
    ('eq', 0x532CF8, 0x478, (0x271C70,)),
    ('eq', 0x532D08, 0x3D0, (0x29F10C,)),
    ('eq', 0x532D10, 0x3D0, (0x2A4D68,)),
    ('eq', 0x532D20, 0x3D0, (0x2A428C,)),
    ('eq', 0x532D30, 0x478, (0x2A5AF4,)),
    ('prefix', 0x532D38, 0x478, (0x2A5AF4,)),
    ('eq', 0x532D58, 0x468, (0x2A8770,)),
    ('eq', 0x532D68, 0x3D8, (0x287998,)),
    ('eq', 0x532D78, 0x3D8, (0x287998,)),
    ('eq', 0x532D88, 0x3C8, (0x2AB450,)),
    ('eq', 0x532D98, 0x3E0, (0x2A9478,)),
    ('eq', 0x532DA0, 0x430, (0x2AD1C0,)),
    ('prefix', 0x532DB0, 0x3D8, (0x287998,)),
    ('prefix', 0x532DC0, 0x468, (0x2B5538,)),
    ('eq', 0x532DC8, 0x478, (0x271C70,)),
    ('eq', 0x532DD8, 0x478, (0x271C70,)),
    ('eq', 0x532DE8, 0x478, (0x271C70,)),
    ('eq', 0x532DF8, 0x478, (0x271C70,)),
    ('eq', 0x532E08, 0x478, (0x2B3E30,)),
    ('eq', 0x532E18, 0x3C8, (0x2B69D0,)),
    ('eq', 0x532E20, 0x480, (0x2B76E4,)),
    ('eq', 0x532E30, 0x480, (0x2BAFB4,)),
    ('prefix', 0x532E38, 0x480, (0x2BAFB4,)),
    ('prefix', 0x532E48, 0x3D8, (0x2BA03C,)),
    ('prefix', 0x532E50, 0x3E8, (0x2BC820,)),
    ('prefix', 0x532E58, 0x3E8, (0x2BC820,)),
    ('eq', 0x532E68, 0x468, (0x2C07A8,)),
    ('eq', 0x532E78, 0x3D8, (0x2BF2AC,)),
    ('eq', 0x532E80, 0x480, (0x2C1F94,)),
    ('eq', 0x532E90, 0xA0, (0x2B04F8,)),
    ('eq', 0x532370, 0x8C, (0x2B1E80,)),
    ('eq', 0x532390, 0x8C, (0x2B1E80,)),
    ('eq', 0x532E98, 0x8C, (0x2B1E80,)),
    ('eq', 0x532378, 0x8C, (0x2B1E80,)),
    ('eq', 0x532380, 0x8C, (0x2B1E80,)),
    ('eq', 0x532EA8, 0x8C, (0x2B1E80,)),
    ('eq', 0x532EB0, 0x94, (0x2B2C70,)),
    ('eq', 0x532EB8, 0x94, (0x2B2C70,)),
    ('eq', 0x532EC0, 0x50, (0x2B30EC,)),
    ('eq', 0x532368, 0x98, (0x2B33F4,)),
    ('eq', 0x532EC8, 0x5C, (0x201FA8,)),
    ('eq', 0x532ED8, 0x50, (0x202318,)),
    ('eq', 0x532EE8, 0x58, (0x2023F8,)),
    ('eq', 0x532EF8, 0x58, (0x2023F8,)),
    ('eq', 0x532F08, 0x58, (0x2023F8,)),
    ('eq', 0x532F10, 0x170, (0x15711C,)),
    ('eq', 0x532F20, 0x60, (0x158600,)),
    ('prefix', 0x532F70, 0x88, (0x292030,)),
    ('eq', 0x532F78, 0x88, (0x292030,)),
    ('eq', 0x532F80, 0x88, (0x292030,)),
    ('eq', 0x532F88, 0x88, (0x292030,)),
    ('prefix', 0x532F98, 0x84, (0x290C24,)),
    ('eq', 0x532FE8, 0x84, (0x290C24,)),
    ('eq', 0x533058, 0x84, (0x290C24,)),
    ('eq', 0x5330C0, 0x84, (0x290C24,)),
    ('eq', 0x533130, 0x88, (0x292030,)),
    ('eq', 0x533140, 0x84, (0x290C24,)),
    ('eq', 0x5331B0, 0x84, (0x290C24,)),
    ('eq', 0x533220, 0x84, (0x290C24,)),
    ('prefix', 0x533290, 0x84, (0x290C24,)),
    ('eq', 0x533300, 0x84, (0x290C24,)),
    ('eq', 0x533350, 0x84, (0x290C24,)),
    ('eq', 0x533398, 0x84, (0x290C24,)),
    ('eq', 0x5333A0, 0x84, (0x290C24,)),
    ('eq', 0x5333E0, 0x84, (0x290C24,)),
    ('eq', 0x5333E8, 0x84, (0x290C24,)),
    ('eq', 0x533428, 0x84, (0x290C24,)),
    ('eq', 0x533488, 0x84, (0x290C24,)),
    ('eq', 0x5334E8, 0x84, (0x290C24,)),
    ('eq', 0x533558, 0x84, (0x290C24,)),
    ('eq', 0x5335B8, 0x84, (0x290C24,)),
    ('eq', 0x533628, 0x68, (0x2028C8,)),
    ('eq', 0x533690, 0x70, (0x1ECDF4,)),
    ('eq', 0x533698, 0x50, (0x1ECD64,)),
    ('eq', 0x5336A8, 0x4C, (0x1EC900,)),
    ('eq', 0x5336B8, 0x54, (0x1ED288,)),
    ('eq', 0x5336C8, 0x148, (0x1539FC,)),
    ('eq', 0x5336D0, 0x248, (0x155DAC,)),
    ('eq', 0x5336E0, 0x190, (0x159458,)),
    ('eq', 0x5336F0, 0x5C, (0x28A960,)),
    ('eq', 0x533700, 0x5C, (0x28B0A8,)),
    ('eq', 0x533710, 0x5C, (0x28DD94,)),
    ('eq', 0x533720, 0x50, (0x28A850,)),
    ('eq', 0x533728, 0x58, (0x28B4E0,)),
    ('eq', 0x533738, 0x118, (0x28CB90,)),
    ('eq', 0x533748, 0x164, (0x27C694,)),
    ('eq', 0x533758, 0x164, (0x27C694,)),
    ('eq', 0x533760, 0x4C, (0x28E1E4,)),
    ('eq', 0x533770, 0x98, (0x1580E8,)),
    ('eq', 0x5337B8, 0x54, (0x28E394,)),
    ('eq', 0x5337C0, 0x98, (0x28E87C,)),
    ('eq', 0x5337D0, 0x118, (0x15DDDC,)),
    ('eq', 0x533830, 0x118, (0x15DDDC,)),
    ('eq', 0x533880, 0x118, (0x15DD5C,)),
    ('eq', 0x533890, 0x50, (0x28ED14,)),
    ('eq', 0x533898, 0x54, (0x28EC1C,)),
    ('eq', 0x5338A0, 0x8C, (0x2B3718,)),
    ('prefix', 0x5338A8, 0xC0, (0x157754,)),
    ('eq', 0x5338B0, 0x84, (0x2909B0,)),
    ('eq', 0x5338C0, 0x60, (0x15858C,)),
    ('eq', 0x5338D0, 0x98, (0x15806C,)),
    ('eq', 0x5338E8, 0x480, (0x29DF04,)),
    ('eq', 0x5338F0, 0x3C8, (0x28EE80,)),
    ('eq', 0x5323C8, 0x4C, (0x28F15C,)),
    ('eq', 0x5323C0, None, (0x20F844,)),
    ('eq', 0x533908, 0x938, (0x2F9F04,)),
    ('eq', 0x533910, 0x938, (0x2FA3F4,)),
    ('eq', 0x532398, 0x58, (0x261DBC,)),
    ('eq', 0x5323A8, 0x4AC, (0x2C54F8,)),
    ('eq', 0x533920, 0xFC, (0x24D440,)),
    ('eq', 0x533930, 0x2A0, (0x1D7778,)),
    ('eq', 0x533938, 0x4C, (0x265F54,)),
    ('eq', 0x533948, 0x1B8, (0x242E7C,)),
    ('eq', 0x533958, 0x1B8, (0x242C5C,)),
]

# Tested only after the Skeleton prefix (0x532D38) matched: str_prefixDiffers(class string,
# test) again, so neither can match a string that starts with "Skeleton".  The original's
# variants 2 and 3 of Skeleton_ctor (0x15b548, 0x15b594) are unreachable from the factory;
# every Skeleton-prefixed class string takes variant 0 (0x15b5c8).
NESTED = [
    ('prefix', 0x532D48, 0x478, (0x2A5AF4,)),
    ('prefix', 0x532D50, 0x478, (0x2A5AF4,)),
]

LINE = 0x5323C0                    # the Line row: paths_add 0x20f844, no object, unless...
LINE_NAME_KEY = 0x5327B0           # ... props_getStr(props, "name") ...
LINE_WAVE = 0x533900               # ... strcasecmp-equals this string: then
LINE_WAVE_ROW = (0x768, (0x15ECF8,))   # pool_new(0x768) and WaveMaker_ctor 0x15ecf8

# Tried in this order when no name test matched (0x15d684-0x15d998).  (getter, key address,
# outcome); an outcome is (size, constructor) or ('light', with-light row, without-light row)
# chosen by propList_hasAnyLight 0x23a2b4.  'int' is props_getInt != 0, 'str' props_getStr.
FALLBACKS = [
    ('int', 0x533968, (0x3D0, 0x243624)),
    ('int', 0x533980, ('light', (0x150, 0x24259C), (0x148, 0x23D93C))),
    ('int', 0x533990, ('light', (0x100, 0x241468), (0xF8, 0x23AD18))),
    ('int', 0x5339A0, ('light', (0x448, 0x2416C4), (0x198, 0x23C44C))),
    ('int', 0x5339B0, (0x60, 0x240DC8)),
    ('int', 0x5339C0, (0x198, 0x23C44C)),
    ('int', 0x5339D0, (0x198, 0x23C44C)),
    ('int', 0x5339E0, (0x448, 0x2547FC)),
    ('str', 0x5339E8, (0x3E8, 0x2657A0)),
    ('str', 0x5339F8, (0x490, 0x31D180)),
]

# propList_hasAnyLight 0x23a2b4: propList_getInt 0x23a100 (the same rule as props_getInt)
# of three keys, then propList_hasLightIndex 0x23a200 for k = 0..3, which formats three
# keys with libc_sprintf and the number.  True at the first non-zero value.
LIGHT_KEYS = (0x541EC8, 0x541ED8, 0x541EE8)
LIGHT_FORMATS = (0x541E98, 0x541EB0, 0x541EC0)
LIGHT_INDICES = 4


class Outcome:
    def __init__(self, sizes=(), calls=(), creates=False, clear_color=False):
        self.sizes, self.calls, self.creates, self.clear_color = tuple(sizes), tuple(calls), creates, clear_color

    @property
    def constructor(self):
        return self.calls[-1] if self.creates else None

    def __repr__(self):
        return 'Outcome(sizes=%r, calls=%r, creates=%r, clear_color=%r)' % (
            self.sizes, tuple(hex(c) for c in self.calls), self.creates, self.clear_color)


def _signed(c):
    return c - 256 if c >= 128 else c


def _lower(c, strings):
    s = _signed(c)
    return s + 0x20 if strings.ctype(s) & 1 else s


def _lower_bytes(text, strings):
    return bytes((_lower(c, strings)) & 0xFF for c in text)


def str_eq(a, b, strings):
    """libc_strcasecmp(a, b) == 0."""
    a, b = bytes(a) + b'\0', bytes(b) + b'\0'
    for i in range(min(len(a), len(b))):
        if _lower(a[i], strings) != _lower(b[i], strings):
            return False
        if a[i] == 0:
            return True
    return False


def str_prefix(text, prefix, strings):
    """str_prefixDiffers(text, prefix) == 0: text starts with prefix."""
    text = bytes(text) + b'\0'
    for i, p in enumerate(bytes(prefix)):
        have = text[i] if i < len(text) else 0
        if _lower(have, strings) != _lower(p, strings):
            return False
    return True


def prop_find(props, key, strings):
    """The text after 'key=' of the first entry that starts with the lowered key."""
    if props is None:
        return None
    k = _lower_bytes(key, strings)
    for entry in props:
        entry = bytes(entry)
        if entry[:len(k)] == k and entry[len(k):len(k) + 1] == b'=':
            return entry[len(k) + 1:]
    return None


def atoi(text, strings):
    """libc_atoi 0x3b3550: libc_strtol(text, 0, 10) (newlib _strtol_r 0x3ba780), whose long
    is 64 bits, then the low 32 bits.  Leading characters with class bit 0x08 (space) are
    skipped, then one sign, then decimal digits; an overflow clamps to the 64-bit limit."""
    text = bytes(text)
    pos = 0
    while pos < len(text) and strings.ctype(_signed(text[pos])) & 0x08:
        pos += 1
    negative = False
    if pos < len(text) and text[pos] in (0x2B, 0x2D):
        negative, pos = text[pos] == 0x2D, pos + 1
    value = 0
    while pos < len(text) and 48 <= text[pos] <= 57:
        value = value * 10 + text[pos] - 48
        pos += 1
    value = -value if negative else value
    value = max(-(1 << 63), min((1 << 63) - 1, value))
    return value & M32


def prop_int(props, key, strings):
    text = prop_find(props, key, strings)
    return 0 if text is None else atoi(text, strings)


def has_any_light(props, strings):
    for key in LIGHT_KEYS:
        if prop_int(props, strings.string(key), strings):
            return True
    for k in range(LIGHT_INDICES):
        for fmt in LIGHT_FORMATS:
            key = strings.string(fmt).replace(b'%d', b'%d' % k)
            if prop_int(props, key, strings):
                return True
    return False


def classify(name, props, strings):
    """What the factory does with (class string, property list or None)."""
    name = bytes(name)
    for row in TESTS:
        kind, addr, size, calls = row[:4]
        test = strings.string(addr)
        hit = str_eq(name, test, strings) if kind == 'eq' else str_prefix(name, test, strings)
        if not hit:
            continue
        if len(row) > 4 and row[4] == CLEAR_COLOR:
            return Outcome(clear_color=True)
        if addr == LINE:
            value = prop_find(props, strings.string(LINE_NAME_KEY), strings)
            if value is not None and str_eq(value, strings.string(LINE_WAVE), strings):
                wsize, wcalls = LINE_WAVE_ROW
                return Outcome((wsize,), calls + wcalls, True)
            return Outcome((), calls, False)
        if size is None:
            return Outcome((), calls, False)
        return Outcome((size,), calls, True)
    for getter, key, outcome in FALLBACKS:
        text = prop_find(props, strings.string(key), strings)
        passed = (text is not None) if getter == 'str' else (text is not None and atoi(text, strings) != 0)
        if not passed:
            continue
        if outcome[0] == 'light':
            outcome = outcome[1] if has_any_light(props, strings) else outcome[2]
        size, ctor = outcome
        return Outcome((size,), (ctor,), True)
    return Outcome()


def _selftest():
    class S:
        def __init__(self, table):
            self.table = table

        def string(self, addr):
            return self.table.get(addr, b'')

        def ctype(self, index):
            return (1 if 65 <= index <= 90 else 0) | (8 if index in (9, 10, 11, 12, 13, 32) else 0)
    s = S({})
    assert str_eq(b'Gnaw', b'gnaw', s) and not str_eq(b'Gnaw', b'Gnaws', s)
    assert str_prefix(b'Orc2Soldier', b'orc2', s) and not str_prefix(b'Or', b'Orc', s)
    assert prop_find([b'autoprop=1'], b'AutoProp', s) == b'1'
    assert prop_find([b'AutoProp=1'], b'AutoProp', s) is None
    assert atoi(b' -7x', s) == (-7) & M32 and atoi(b'', s) == 0
    assert atoi(b'99999999999999999999', s) == ((1 << 63) - 1) & M32
    print('ref_level_factory self-test passed')


if __name__ == '__main__':
    _selftest()
