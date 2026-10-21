"""Item -> inventory picture association for SLUS-20973 v2.00; see
docs/formats/icon-association.md.

The game never stores a picture id on an item. It builds a file NAME from the
item record, the definition, the prefix table and the viewing player's body
model (item_buildPictureFilename 0x107edc), then looks that name up in
piccache.hdr by stem and trailing decimal number (picCache_findHeaderEntry
0x100000). Keep that two-step contract: (variant, colour) pairs are encoded by
string concatenation and can alias. All tables passed in here are synthetic or
caller-supplied; this module contains no game names or data.
"""
from collections import namedtuple
import re
import struct

# Fields of the 0x40-byte definition row read by 0x107edc (docs/data-tables.md 1.1).
ItemDef = namedtuple('ItemDef', 'name category slot subtype dmg_min dmg_max picture model_row')
# Item record fields read: +0x08 u64 flags (variant in bits 11-15), +0x20 prefix row.
Item = namedtuple('Item', 'definition flags prefix', defaults=(0, 0xff))
# 10-byte piccache.hdr entry (docs/startup.md "Picture cache").
Entry = namedtuple('Entry', 'number sector sectors width height')
Group = namedtuple('Group', 'stem entries')

CLOTH = 1 << 19          # item flags bit tested at 0x108100
ALT_COLOUR = 1 << 23     # 0x107fc0: use the prefix's alternate weapon colour (+8)
PLAIN_WEAPON = 1 << 34   # 0x107f6c: a weapon named like a non-equipment item
NO_PREFIX = 0xff
PLACEHOLDER = ('equipmnt.lmp', 'pic_dagger1.tex')   # item_getPicture 0x10837c..0x108390


def _c_rem(a, b):
    """MIPS div remainder: sign follows the dividend (0x10800c, 0x1082a0..0x1082b4)."""
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def _variant_number(flags):
    """((flags >> 11) + 1) & 31, 0x108070..0x108090: variant 31 prints as 0."""
    return ((flags >> 11) + 1) & 0x1f


def armour_body(body_type, cloth):
    """Body-model substitution of 0x1080c8..0x108160 (non-circlet armour).

    Models 6 and 7 are the only bodies drawn in cloth sheets. Cloth on another
    body uses 7 when that body number is odd and below 10, else 6; non-cloth
    armour on body 6/7 uses 0/1 respectively.
    """
    odd_low = body_type & 1 and body_type < 10
    if cloth:
        return body_type if body_type in (6, 7) else (7 if odd_low else 6)
    if body_type in (6, 7):
        return 1 if odd_low else 0
    return body_type


def _circlet_sheet(name):
    """0x108184..0x108234: circlet<k><n> on body 6/7 becomes cloth<k>helmet6<n>.tex.

    The original reads n with sscanf on the definition name; a name not starting
    with the tested prefix leaves n as uninitialised stack, refused here.
    """
    for k in ('1', '2'):
        if 'circlet' + k in name:
            break
    else:
        k = '3'    # 0x108210: no strstr test before the third form
    head = 'circlet' + k
    number = re.match(r'\s*([-+]?\d+)', name[len(head):])
    if not name.startswith(head) or not number:
        raise ValueError('circlet number unreadable: original uses stack garbage')
    return 'cloth%shelmet6%d.tex' % (k, int(number.group(1)))


def picture_filename(item, body_type, model_textures, prefix_colours, body_codes, value=None):
    """item_buildPictureFilename 0x107edc as used by item_getPicture 0x108358.

    model_textures[row] is the g_itemModels texture name (row +4), used only
    when the definition has no picture name. prefix_colours[row] is the s8
    triple (weapon +6, armour +7, alternate weapon +8). body_codes is the
    12-entry g_bodyTypeCodes table. value is item_getValue(item) (0x1024a8),
    needed only for preset ('+' in the name) armour.
    """
    d, flags, prefix = item.definition, item.flags, item.prefix
    base = d.picture + '.tex' if d.picture else model_textures[d.model_row]
    def splice(text, cut, suffix):
        if len(text) < cut:
            raise ValueError('original writes before the output buffer')
        return text[:len(text) - cut] + suffix
    if d.category == 0 and not flags & PLAIN_WEAPON:
        colour = prefix_colours[prefix][0] if prefix != NO_PREFIX else 1
        if d.subtype == 4:                      # bows, 0x107fac..0x107fb8
            colour = 1
        if prefix != NO_PREFIX and flags & ALT_COLOUR:
            colour = prefix_colours[prefix][2]
        if '+' in d.name:                       # preset row, 0x107fe4..0x108010
            colour = _c_rem(d.dmg_min + d.dmg_max, 18)
        colour = colour or 1                    # 0x108024
        return splice(base, 5, '%d%d.tex' % (_variant_number(flags), colour))
    if d.category == 1:
        if d.slot == 3:                         # 0x1080c4: plain picture name
            return base
        if 'circlet' in d.name:
            body = body_type                    # mapping skipped, 0x1080f4
            if body in (6, 7):
                base = _circlet_sheet(d.name)
        else:
            body = armour_body(body_type, flags & CLOTH)
        name = '%s_%s' % (body_codes[body], base)
        colour = prefix_colours[prefix][1] if prefix != NO_PREFIX else None
        if '+' in d.name:
            if value is None:
                raise ValueError('preset armour colour needs item_getValue')
            colour = _c_rem(value, 4)
        if prefix == NO_PREFIX:                 # 0x1082c8, applied after the preset rule
            colour = 1
        return splice(name, 4, '%d.tex' % colour)
    if '1.tex' in base:                         # 0x1082ec..0x108330
        return splice(base, 5, '%d.tex' % _variant_number(flags))
    return base


def split_picture_name(name):
    """Stem and number as picCache_findHeaderEntry 0x100000 derives them.

    Cut at the LAST '.', then take the maximal run of trailing digits, never
    including the first character; no digits -> number -1. None for an empty stem.
    """
    dot = name.rfind('.')
    if dot >= 0:
        name = name[:dot]
    if not name:
        return None
    start = len(name)
    while start > 1 and name[start - 1].isdigit():
        start -= 1
    digits = name[start:]
    number = int(digits) if digits else -1
    if digits and not -0x80000000 <= number <= 0x7fffffff:
        raise ValueError('atoi overflow is outside the reference domain')
    return name[:start], number


def find_entry(groups, name):
    """First group (in file order) with an equal stem AND an entry whose s16
    number equals the parsed number; a stem match without a number match keeps
    searching later groups. Case-sensitive strcmp. Returns Entry or None."""
    split = split_picture_name(name)
    if split is None:
        return None
    stem, number = split
    for group in groups:
        if group.stem == stem:
            for entry in group.entries:
                if entry.number == number:
                    return entry
    return None


def parse_index(data):
    """Bounded piccache.hdr reader: u32 group count; 12-byte groups of
    (entries offset, stem offset, count); 10-byte entries <hHHhh>.
    Bounds/NUL checks are native-reader policy; the original trusts the file."""
    if len(data) < 4:
        raise ValueError('short index')
    count = struct.unpack_from('<I', data)[0]
    if 4 + 12 * count > len(data):
        raise ValueError('group table out of range')
    groups = []
    for g in range(count):
        entries_at, stem_at, n = struct.unpack_from('<III', data, 4 + 12 * g)
        end = data.find(b'\0', stem_at)
        if stem_at >= len(data) or end < 0 or entries_at + 10 * n > len(data):
            raise ValueError('group %d out of range' % g)
        entries = tuple(Entry(*struct.unpack_from('<hHHhh', data, entries_at + 10 * i))
                        for i in range(n))
        groups.append(Group(data[stem_at:end].decode('latin-1'), entries))
    return tuple(groups)


def picture_or_placeholder(cache_header, name):
    """item_getPicture 0x108358: a loaded cache picture, else the lump placeholder.
    cache_header is what picCache_getOrRequestPicture 0x1008bc returned (or None)."""
    return cache_header if cache_header is not None else PLACEHOLDER


class PictureCache:
    """Streaming states of 0x100000..0x100973 (64 slots, one disc read at a time).

    A model for comparing a native cache with the original's per-machine
    timing, not something a native decoder needs: reading PICCACHE.DAT
    synchronously is equivalent for display except for the placeholder frames.
    Block exhaustion (256 x 0x500 blocks) is not modelled.
    """
    SLOTS, IDLE_FRAMES = 64, 8

    def __init__(self, groups):
        self.groups, self.slots, self.loading = groups, [], None

    def _slot(self, name):
        return next((s for s in self.slots if s['name'] == name), None)

    def request(self, name, frame):
        """0x1008bc: header when loaded (refresh last use), else None; queue on miss."""
        slot = self._slot(name)
        if slot is None:
            self._queue(name, frame)
            return None
        if slot['state'] != 'loaded':
            return None
        slot['last'] = frame
        return slot['entry']

    def _queue(self, name, frame):
        """0x100790: take a free slot, evicting one if all 64 are named; when
        nothing can be evicted the request is dropped (it is retried by the
        next request call)."""
        if len(self.slots) == self.SLOTS and not self._evict(frame):
            return
        self.slots.append(dict(name=name, state='pending', last=frame, entry=None))

    def _evict(self, frame):
        """0x1002d4: oldest last-use strictly below frame-8, not the slot being
        read; first slot wins ties."""
        best, limit = None, frame - self.IDLE_FRAMES
        for s in self.slots:
            if s is not self.loading and s['last'] < limit:
                best, limit = s, s['last']
        if best is None:
            return False
        self.slots.remove(best)
        return True

    def service(self, frame, read_done):
        """0x1003cc once per displayed frame. read_done says the outstanding
        disc read finished. Completes it, then starts at most one new read;
        names missing from the index are marked and never load."""
        if self.loading is not None:
            self.loading['last'] = frame
            if not read_done:
                return
            self.loading['state'] = 'loaded'
            self.loading = None
        for s in self.slots:
            if s['state'] != 'pending':
                continue
            entry = find_entry(self.groups, s['name'])
            if entry is None:
                s['state'] = 'missing'          # block list -2, 0x1006f8
                continue
            s['entry'], s['last'], s['state'] = entry, frame, 'reading'
            self.loading = s
            return
