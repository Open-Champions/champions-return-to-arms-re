#!/usr/bin/env python3
"""ref_strings.py - reference model of the string table, the wide-string formatter and
the HUD text script commands of Champions: Return to Arms (SLUS-20973 v2.00).

Written from the instructions at the addresses named below; docs/strings.md says what
each part is and how it was checked.  tools/difftest_strings.py runs the original
functions in tools/ee_emu.py next to this model; tools/test_ref_strings.py checks the
model on its own.  Nothing from the game is in this file.

Parts
  1. text_hash 0x173a74, text_registerTable 0x173bac, text_unregisterTable 0x173ac0,
     text_lookup 0x173c84 (with its 16-entry "NF:" ring), text_find 0x173de0.
  2. wstr_format 0x19ea78 and wstr_formatAscii 0x19e9c4; wstr_copy 0x19e854,
     wstr_len 0x19e994, wstr_fromAscii 0x19e884, wstr_toAscii 0x19e8b4.
  3. The HUD state the five script commands write: setInfo 0x14318c, addHelpMessage
     0x1431d8, addHelpMessageF 0x143270, showBust 0x142864, showCompass 0x1427b4,
     through hud_showMessage 0x1d92a0, hud_showHelpMessage 0x1d9830, hud_setBust
     0x1dfaa0 and hud_setCompassTarget 0x1df668; the run-side timers hud_tickMessage
     0x1d934c and the two countdowns in hud_run 0x1dbbec-0x1dbc24.
  4. sound_playOnObject 0x214230 (slot choice, category cap, handle, slot fields) with
     anim_push 0x170838 for the one track a sequence slot holds.
  5. Creature_setCharm 0x1189f0 on a creature whose target handle (+0x234) is live, on
     top of ref_core.HandlePool (handle_clear 0x1a1698).
"""
import struct

import ref_core as RC

M32 = 0xFFFFFFFF

# ---------------------------------------------------------------------------------------
# 1. String table
# ---------------------------------------------------------------------------------------
G_TEXT_HASH = 0x7C2EA0          # 8,192 pointers to keys
TEXT_SLOTS = 0x2000
G_NF_INDEX = 0x41BFA8           # s8 ring position
G_NF_RING = 0x7CAEA0            # 16 entries x 40 bytes
NF_ENTRIES = 16
NF_UNITS = 20
LOOKUP_KEY_BYTES = 0x200        # text_lookup / text_find copy the key into this stack buffer


class TableError(Exception):
    """The original has no defined result here (an endless probe, a stack overrun)."""


def sx8(b):
    return b - 0x100 if b & 0x80 else b


def s32(x):
    x &= M32
    return x - 0x100000000 if x & 0x80000000 else x


def text_hash(key):
    """text_hash(str, len) 0x173a74 -> 0..0x1fff.  Bytes are read with lb: signed."""
    h = 0
    for b in key:
        h = (h + sx8(b)) & M32
        h = (h + (h << 10)) & M32
        h ^= (s32(h) >> 6) & M32
    h = (h + (h << 3)) & M32
    h ^= (s32(h) >> 11) & M32
    return h & 0x1FFF


def strip_quotes(key):
    """text_lookup / text_find drop every double-quote byte (0x22) from the request."""
    return bytes(b for b in key if b != 0x22)


def uni_entries(data, start=0):
    """Walk a .uni stream the way text_registerTable does.  Yields
    (key_offset, key, text_offset, units, next_offset).  The walk stops when the byte at
    the next key offset is zero (lb, so any non-zero byte continues)."""
    pos = start
    while pos < len(data) and data[pos] != 0:
        end = data.index(b'\0', pos)
        key = bytes(data[pos:end])
        text = (pos + len(key) + 2) & ~1
        units, q = [], text
        while True:
            unit, = struct.unpack_from('<H', data, q)
            if unit == 0:
                break
            units.append(unit)
            q += 2
        nxt = q + 2
        yield pos, key, text, units, nxt
        pos = nxt


def build_uni(pairs, pad=0):
    """A synthetic .uni stream from (key bytes, text str) pairs, ended by a zero byte.
    pad is the byte value used for the alignment hole after an odd-placed key."""
    out = bytearray()
    for key, text in pairs:
        out += key + b'\0'
        if len(out) & 1:
            out.append(pad)
        out += text.encode('utf-16-le') + b'\0\0'
    out += b'\0\0'
    return bytes(out)


class TextTable:
    """g_textHash and the ring of miss texts.  Keys are identified by their address, as
    in the original (the table holds pointers).  `memory` maps a key address to its
    (key, units) so that lookups can return the text."""

    def __init__(self):
        self.slots = [0] * TEXT_SLOTS
        self.keys = {}               # key address -> key bytes
        self.texts = {}              # key address -> (text address, units)
        self.nf_index = 0
        self.nf_ring = [[0] * NF_UNITS for _ in range(NF_ENTRIES)]
        self.probes = 0              # slots inspected by the last call
        self.blobs = []              # (base, data) of every registered stream

    # -- registration
    def register(self, data, base):
        """text_registerTable(base): every entry goes to the first free slot from its
        hash.  Duplicates are not detected, so the earlier entry stays the one found.
        Returns the list of (key address, slot)."""
        placed = []
        self.blobs.append((base, bytes(data)))
        for koff, key, toff, units, _ in uni_entries(data):
            addr = base + koff
            slot = text_hash(key)
            for _ in range(TEXT_SLOTS):
                if self.slots[slot] == 0:
                    break
                slot = (slot + 1) & 0x1FFF
            else:
                raise TableError('table full: text_registerTable would probe forever')
            self.slots[slot] = addr
            self.keys[addr] = key
            self.texts[addr] = (base + toff, units)
            placed.append((addr, slot))
        return placed

    def unregister(self, data, base):
        """text_unregisterTable(base): probe from the hash for the slot holding this very
        key address and zero it.  No tombstone: a later key that had probed past this
        slot becomes unreachable (see docs/strings.md, 1.4)."""
        for koff, key, _toff, _units, _ in uni_entries(data):
            addr = base + koff
            slot = text_hash(key)
            for _ in range(TEXT_SLOTS):
                if self.slots[slot] == addr:
                    break
                slot = (slot + 1) & 0x1FFF
            else:
                raise TableError('key not in the table: text_unregisterTable would probe forever')
            self.slots[slot] = 0

    # -- lookup
    def _probe(self, request):
        key = strip_quotes(request)
        if len(key) + 1 > LOOKUP_KEY_BYTES:
            raise TableError('key of %d bytes overruns the 0x200-byte stack copy' % len(key))
        slot = text_hash(key)
        self.probes = 0
        while True:
            self.probes += 1
            addr = self.slots[slot]
            if addr == 0:
                return key, None
            if self.keys.get(addr) == key:
                return key, addr
            slot = (slot + 1) & 0x1FFF
            if self.probes > TEXT_SLOTS:
                raise TableError('full table without the key: the probe never ends')

    def find(self, request):
        """text_find 0x173de0: the text address, or 0 when the key is missing."""
        _key, addr = self._probe(request)
        return 0 if addr is None else self.texts[addr][0]

    def lookup(self, request, stale=b''):
        """text_lookup 0x173c84 -> (address, units, hit).  A miss advances the ring,
        clears its 40-byte entry and writes 'N', 'F', ':' and then 16 bytes of the
        key's stack copy, each sign-extended to 16 bits.  Bytes after the copy's
        terminator are whatever the stack held (`stale`); the visible text is always
        "NF:" + the first 16 bytes of the stripped key."""
        key, addr = self._probe(request)
        if addr is not None:
            taddr, units = self.texts[addr]
            return taddr, list(units), True
        self.nf_index = (self.nf_index + 1) & 0xF
        entry = [0] * NF_UNITS
        entry[0:3] = [0x4E, 0x46, 0x3A]
        copy = (key + b'\0' + bytes(stale))[:16].ljust(16, b'\0')
        for i, b in enumerate(copy):
            entry[3 + i] = sx8(b) & 0xFFFF
        self.nf_ring[self.nf_index] = entry
        return G_NF_RING + self.nf_index * 40, visible(entry), False


    def unit_at(self, addr):
        """The 16-bit unit at addr in a registered stream or in the miss ring (what the
        formatter reads when it runs past a text's terminator)."""
        for base, data in self.blobs:
            if base <= addr and addr + 2 <= base + len(data):
                return struct.unpack_from('<H', data, addr - base)[0]
        if G_NF_RING <= addr < G_NF_RING + NF_ENTRIES * 40:
            off = (addr - G_NF_RING) // 2
            return self.nf_ring[off // NF_UNITS][off % NF_UNITS]
        raise FormatError('read outside the modelled text memory at 0x%x' % addr)

    def reader(self, addr):
        return lambda k: self.unit_at(addr + 2 * k)


def visible(units):
    out = []
    for u in units:
        if u == 0:
            break
        out.append(u)
    return out


def nf_text(request):
    """What a miss shows: NF: and the first 16 bytes of the stripped key."""
    key = strip_quotes(request)[:16]
    return [0x4E, 0x46, 0x3A] + [sx8(b) & 0xFFFF for b in key]


# ---------------------------------------------------------------------------------------
# 2. Wide strings and the formatter
# ---------------------------------------------------------------------------------------
class FormatError(Exception):
    """No defined result in the original."""


def wstr_copy(src):
    """wstr_copy(dst, src) 0x19e854: units through the terminator, unbounded."""
    return visible(src) + [0]


def wstr_from_ascii(src):
    """wstr_fromAscii 0x19e884: each byte zero-extended (lbu), unbounded."""
    return [b for b in src.split(b'\0')[0]] + [0]


def wstr_to_ascii(units):
    """wstr_toAscii 0x19e8b4: the low byte of every unit."""
    return bytes(u & 0xFF for u in visible(units)) + b'\0'


def cvt_w_s(raw):
    """CVT.W.S on the R5900: truncate toward zero, saturate."""
    return s32(RC.to_int(raw & M32))


def cvt_s_w(value):
    """CVT.S.W (the formatter's callers convert integers with it)."""
    return RC.from_int(value & M32)


def widen(raw):
    """The soft-float widening 0x3aef58 (unpack, then pack as a double) reads the
    pattern the R5900 way (executed): exponent field 0 is a signed zero, so denormal
    patterns become 0.0; exponent field 255 is an ordinary number up to
    (2 - 2**-23) * 2**128, never an infinity or a NaN."""
    raw &= M32
    sign = -1.0 if raw & 0x80000000 else 1.0
    exp = (raw >> 23) & 0xFF
    if exp == 0:
        return sign * 0.0
    return sign * (1.0 + (raw & 0x7FFFFF) / 8388608.0) * 2.0 ** (exp - 127)


def _float_text(raw):
    """sprintf("%.2f", widen(f)): newlib prints the exact binary value rounded to two
    places, as Python does."""
    return ('%.2f' % widen(raw)).encode('ascii')


def wstr_format(fmt, args=(), cstr=None, wstr=None):
    """wstr_format(out, fmt) 0x19ea78 with the eight float arguments f12..f19.

    fmt    the format as 16-bit units AS THEY LIE IN MEMORY, including whatever follows
           the terminator: the loop can read past it (see below).
    args   up to eight raw float patterns; a conversion past the eighth reads the
           function's own scratch buffer and is refused here.
    cstr   cstr(address) -> bytes, for %s (8-bit string at the truncated float).
    wstr   wstr(address) -> units, for %u (16-bit string at the truncated float).

    Returns (written, used): every unit stored, in order, and the number of arguments
    taken.  The visible result is written up to its first 0.

    Loop (Observed): a unit that is not '%' is copied; then if the NEXT unit is 0 a 0 is
    stored and the function returns.  '%' looks at the unit after it only:
      %%  a '%'           %d  sprintf %d of trunc(arg)    %c  the unit trunc(arg)
      %s  8-bit string    %u  16-bit string                %f  sprintf %.2f of arg
    and then skips both units; any other unit after '%' writes nothing and takes no
    argument.  Flags, widths and precisions are not parsed: "%.2f" prints "2f".
    Because the end test only looks after a copied unit, a format that ends with a
    conversion (or with a lone '%') copies its terminator and goes on reading what
    follows it, stopping after the first copied unit that is followed by a 0."""
    out, i, used = [], 0, 0

    def arg():
        nonlocal used
        if used >= 8:
            raise FormatError('a ninth conversion reads the formatter scratch buffer')
        used += 1
        return args[used - 1] if used - 1 < len(args) else 0

    def unit(k):
        if callable(fmt):
            return fmt(k)
        if k >= len(fmt):
            raise FormatError('the formatter read past the supplied memory (index %d)' % k)
        return fmt[k]

    while True:
        c = unit(i)
        if c == 0x25:
            conv = unit(i + 1)
            if conv == 0x25:
                out.append(0x25)
            elif conv == 0x64:                          # d
                out += [sx8(b) & 0xFFFF for b in b'%d' % cvt_w_s(arg())]
            elif conv == 0x63:                          # c
                out.append(cvt_w_s(arg()) & 0xFFFF)
            elif conv == 0x73:                          # s
                ptr = cvt_w_s(arg()) & M32
                out += list(cstr(ptr).split(b'\0')[0])
            elif conv == 0x75:                          # u: a wide string
                ptr = cvt_w_s(arg()) & M32
                out += visible(wstr(ptr))
            elif conv == 0x66:                          # f
                out += [sx8(b) & 0xFFFF for b in _float_text(arg())]
            i += 2
            continue
        out.append(c)
        i += 1
        if unit(i) == 0:
            out.append(0)
            return out, used
        if len(out) > 0x10000:
            raise FormatError('runaway copy')


def wstr_format_ascii(fmt8, args=(), cstr=None, wstr=None, tail=()):
    """wstr_formatAscii(out, fmt) 0x19e9c4: widen the 8-bit format into a 0x200-byte
    stack buffer with wstr_fromAscii, then wstr_format.  `tail` stands for the units
    that follow the widened terminator in that buffer."""
    widened = wstr_from_ascii(fmt8)
    if len(widened) * 2 > 0x200:
        raise FormatError('format of %d bytes overruns the 0x200-byte widening buffer' % len(fmt8))
    return wstr_format(widened + list(tail), args, cstr, wstr)


def format_one_int(fmt, value):
    """What addHelpMessageF does with one looked-up text and its integer: wstr_format
    with f12 = cvt.s.w(value) and f13..f19 = 0.0.  fmt is a unit list (text, its
    terminator and what follows) or a reader k -> unit."""
    args = [cvt_s_w(value)] + [0] * 7
    return wstr_format(fmt, args, cstr=_refuse_pointer, wstr=_refuse_pointer)


def _refuse_pointer(_addr):
    raise FormatError('a %s or %u conversion in a help text would dereference a float argument')


# ---------------------------------------------------------------------------------------
# 3. HUD state written by the five commands
# ---------------------------------------------------------------------------------------
G_HUD_SUPPRESSED = 0x4F66A8     # s8
G_BUST_HIDE_LATCH = 0x4F66A9    # s8
G_HELP_CLOSE_DELAY = 0x4F66CC   # s32
G_BUST_FADE = 0x4F66D0          # float
G_BUST_SHOWN = 0x4F66D4         # s8 countdown
G_COMPASS_SHOWN = 0x4F66D5      # s8 countdown
G_MSG_FRAMES = 0x4F66E0         # s16
G_MSG_FORCE = 0x4F66E2          # s8
G_BUST_TEXTURE = 0x4F6B48       # char[] (strcpy)
G_HELP_OPEN = 0x41B928          # s8
G_LOCAL_MENU = 0x41B69D         # s8
G_MENU_OPEN = 0x41B4F8          # s32
G_LOCAL_CAMERA = 0x4F8450       # ptr, mode word at +0x34
G_LOADSCREEN = 0x506094         # s8
G_WARMUP = 0x506048             # s32
G_NUM_PLAYERS = 0x4D8AE0        # s32
G_NETWORK = 0x402791            # s8
G_ALIVE_COUNT = 0x4F8420        # s32
G_ALIVE_LIST = 0x4F8440         # s32[]
G_HELP_TITLE = 0x86AA64         # ptr
G_HELP_BODY = 0x86AA68          # ptr
G_COMPASS_TARGET = 0x86A8F0     # Vec3 (12 bytes)
HELP_F_TITLE = 0x5D3048         # 32 units, then the body buffer
HELP_F_BODY = 0x5D3088          # 128 units, then 0x5d3188 (another function's data)

# One block of HUD data, in address order.  The four text buffers have no length check.
BUST_TEXT = 0x86AAB0            # 32 units, then the compass label
COMPASS_LABEL = 0x86AAF0        # 32 units, then the bust value
BUST_VALUE = 0x86AB30           # s32
BUST_MAX = 0x86AB34             # s32, -1 = no meter (value shown as a number)
EXPECTED_SUMS = 0x86AB38        # int[4][2] g_expectedChecksums
RECEIVED_SUMS = 0x86AB58        # int[4][2] g_receivedChecksums
MESSAGE_TEXT = 0x86AB78         # 100 units, then g_msgIdGame
MSG_ID_GAME = 0x86AC40          # s32: the HUD game-message channel id
HUD_BLOCK_END = 0x86AC44

LIMITS = {                      # longest text (units, terminator excluded) that stays inside
    'bust text': (COMPASS_LABEL - BUST_TEXT) // 2 - 1,         # 31
    'compass label': (BUST_VALUE - COMPASS_LABEL) // 2 - 1,    # 31
    'message': (MSG_ID_GAME - MESSAGE_TEXT) // 2 - 1,          # 99
    'help F title': (HELP_F_BODY - HELP_F_TITLE) // 2 - 1,     # 31
    'help F body': (0x5D3188 - HELP_F_BODY) // 2 - 1,          # 127
    'help F format output': 0x200 // 2 - 1,                    # 255 (stack buffers)
    'script key': 0xA0 - 1,                                    # 159 bytes (stack copies)
    'bust texture name': 0x4F6B70 - G_BUST_TEXTURE - 1,        # 39 bytes, then frontend words
}

HELP_CHIME = ('fx.lmp', 'butn_message.anm')
MESSAGE_FRAMES = 180            # setInfo's duration (ticks of the run task)
HELP_CLOSE_DELAY_OPEN = 90      # written when a help box opens
SHOWN_TICKS = 5                 # bust / compass stay up for 5 run ticks after a call


class Hud:
    """The words the five commands and the run-side timers read and write.  Text
    buffers are modelled as the block of bytes they share so that an overrun lands
    where it lands in the original."""

    def __init__(self):
        self.block = bytearray(HUD_BLOCK_END - BUST_TEXT)
        self.help_f = bytearray(0x5D3188 - HELP_F_TITLE)
        self.msg_frames = 0
        self.msg_force = 0
        self.help_open = 0
        self.help_title = 0
        self.help_body = 0
        self.help_close_delay = 0
        self.bust_shown = 0
        self.compass_shown = 0
        self.bust_texture = b''
        self.compass_target = (0, 0, 0)      # three raw words
        self.latch = 0
        # inputs
        self.suppressed = 0
        self.local_menu = 0
        self.menu_open = 0
        self.camera_mode = 1                 # None = no camera object (the gate faults)
        self.loadscreen = 0
        self.warmup = 0
        self.num_players = 1
        self.network = 0
        self.alive = []                      # alive slots, list order
        self.local = lambda slot: True       # net_isLocalSlot
        # what was called outward
        self.events = []

    # -- byte block helpers
    def _write_units(self, block, base, addr, units):
        off = addr - base
        need = off + 2 * len(units)
        if need > len(block):
            raise FormatError('text of %d units runs past the modelled block at 0x%x'
                              % (len(units), base + len(block)))
        for i, u in enumerate(units):
            struct.pack_into('<H', block, off + 2 * i, u & 0xFFFF)

    def write_text(self, addr, units):
        """wstr_copy into the HUD block (addresses BUST_TEXT..HUD_BLOCK_END)."""
        self._write_units(self.block, BUST_TEXT, addr, wstr_copy(units))

    def read_units(self, addr, limit=4096):
        if HELP_F_TITLE <= addr < 0x5D3188:
            block, base = self.help_f, HELP_F_TITLE
        else:
            block, base = self.block, BUST_TEXT
        off, out = addr - base, []
        while off + 1 < len(block) and len(out) < limit:
            u, = struct.unpack_from('<H', block, off)
            if u == 0:
                break
            out.append(u)
            off += 2
        return out

    def word(self, addr):
        return struct.unpack_from('<I', self.block, addr - BUST_TEXT)[0]

    def set_word(self, addr, value):
        struct.pack_into('<I', self.block, addr - BUST_TEXT, value & M32)

    # -- the four setters
    def show_message(self, text_units, frames, slot, force):
        """hud_showMessage 0x1d92a0.  Returns True when it stored."""
        force = sx8(force & 0xFF)
        if slot != -1 and not self.local(slot):
            return False
        if force == 0 and self.local_menu:
            return False
        self.write_text(MESSAGE_TEXT, text_units)
        self.msg_frames = frames & 0xFFFF
        self.msg_force = force & 0xFF
        return True

    def show_help(self, slot, title_addr, body_addr):
        """hud_showHelpMessage 0x1d9830.  There is no queue: a second call while a box is
        open replaces the two pointers, plays the chime again and re-arms the delay."""
        if slot != -1 and not self.local(slot):
            return False
        opened = not self.network
        if self.network:
            for alive in self.alive:
                if self.local(alive):
                    self.events.append(('hudmsg_sendMenuState', alive & 0xFF, 1, 0))
                    opened = True
                    break
        if not opened:
            return False
        self.events.append(('res_find',) + HELP_CHIME)
        self.events.append(('sound_playOnObject', 'chime', 0, 1.0))
        self.events.append(('sound_setPlaysWhileFrozen',))
        self.events.append(('ui_startPulse', 0))
        self.help_open = 1
        self.help_title = title_addr
        self.help_body = body_addr
        self.help_close_delay = HELP_CLOSE_DELAY_OPEN
        return True

    def _widget_gate(self):
        """hud_setBust / hud_setCompassTarget share this gate, in this order."""
        if self.suppressed or self.local_menu:
            return False
        if self.camera_mode is None:
            raise FormatError('no local camera: the gate reads +0x34 of a null pointer')
        if self.camera_mode != 1 or self.loadscreen or self.menu_open:
            return False
        return True

    def set_bust(self, texture, text_units, value, maximum):
        """hud_setBust 0x1dfaa0."""
        if not self._widget_gate():
            return False
        self.bust_shown = SHOWN_TICKS
        self.bust_texture = texture
        self.write_text(BUST_TEXT, text_units)
        self.set_word(BUST_VALUE, value)
        self.set_word(BUST_MAX, maximum)
        return True

    def set_compass(self, position_words, text_units):
        """hud_setCompassTarget 0x1df668.  The position is copied only after the label,
        so a label long enough to reach it is overwritten by nothing here; it does run
        into the bust value and maximum."""
        if not self._widget_gate():
            return False
        self.compass_shown = SHOWN_TICKS
        self.write_text(COMPASS_LABEL, text_units)
        self.compass_target = tuple(w & M32 for w in position_words)
        return True

    # -- run-side timers
    def tick_message(self):
        """hud_tickMessage 0x1d934c, called first thing by hud_run each tick."""
        if self.suppressed or self.warmup:
            return
        frames = self.msg_frames - 0x10000 if self.msg_frames & 0x8000 else self.msg_frames
        if frames <= 0:
            return
        self.msg_frames = (self.msg_frames - 1) & 0xFFFF
        if self.num_players == 4 and not self.network:
            self.latch = 1

    def tick_widgets(self):
        """hud_run 0x1dbbec-0x1dbc24: each non-zero countdown loses one, unconditionally."""
        if self.bust_shown:
            self.bust_shown = (self.bust_shown - 1) & 0xFF
        if self.compass_shown:
            self.compass_shown = (self.compass_shown - 1) & 0xFF


class Commands:
    """The five script handlers on top of a TextTable and a Hud.  Keys are the C strings
    the handlers copy out of the script (scr_getString into 0xa0-byte stack buffers)."""

    def __init__(self, table, hud, find_object=None):
        self.table = table
        self.hud = hud
        self.find_object = find_object or (lambda name: None)
        self.last_f = None

    def _key(self, key):
        if len(key) + 1 > 0xA0:
            raise FormatError('script string of %d bytes overruns the 0xa0-byte stack copy' % len(key))
        return key

    def set_info(self, key):
        addr, units, _hit = self.table.lookup(self._key(key))
        self.hud.show_message(units, MESSAGE_FRAMES, -1, 0)
        return 0

    def add_help_message(self, title_key, body_key):
        taddr, _t, _ = self.table.lookup(self._key(title_key))
        baddr, _b, _ = self.table.lookup(self._key(body_key))
        self.hud.show_help(-1, taddr, baddr)
        return 0

    def add_help_message_f(self, key1, v1, key2, v2):
        """Each text is a format with one integer (as a float).  The formatter reads the
        text in place, so what follows its terminator matters (wstr_format)."""
        a1, _u1, _ = self.table.lookup(self._key(key1))
        out1, _ = format_one_int(self.table.reader(a1), v1)
        a2, _u2, _ = self.table.lookup(self._key(key2))
        out2, _ = format_one_int(self.table.reader(a2), v2)
        self.last_f = (out1, out2)
        if len(out1) * 2 > 0x200 or len(out2) * 2 > 0x200:
            raise FormatError('formatted text overruns its 0x200-byte stack buffer')
        title, body = wstr_copy(out1), wstr_copy(out2)
        self.hud._write_units(self.hud.help_f, HELP_F_TITLE, HELP_F_TITLE, title)
        self.hud._write_units(self.hud.help_f, HELP_F_TITLE, HELP_F_BODY, body)
        self.hud.show_help(-1, HELP_F_TITLE, HELP_F_BODY)
        return 0

    def show_bust(self, texture, key, value, maximum):
        _addr, units, _ = self.table.lookup(self._key(key))
        self.hud.set_bust(self._key(texture), units, value, maximum)
        return 0

    def show_compass(self, name, key):
        """No null check: a name that finds nothing makes the handler read +0x10 of
        address 0 (refused here)."""
        position = self.find_object(self._key(name))
        _addr, units, _ = self.table.lookup(self._key(key))
        if position is None:
            raise FormatError('showCompass of a missing object reads through a null pointer')
        self.hud.set_compass(position, units)
        return 0


# ---------------------------------------------------------------------------------------
# 4. sound_playOnObject
# ---------------------------------------------------------------------------------------
G_SOUND_SEQS = 0x871A68
SEQ_SLOTS = 32
SEQ_STRIDE = 0x4C
G_SOUND_GROUP_LIMIT = 0x4F8A28
G_SOUND_SERIAL = 0x4F8950
NEAR, FAR = 0x43B40000, 0x44520000     # 360.0, 840.0


class SeqSlot:
    """The fields of one 0x4c-byte slot that sound_playOnObject and anim_push touch."""
    __slots__ = ('tracks', 'capacity', 'flags', 'seq', 'track_link', 'track_time',
                 'track_flags', 'track_words', 'pos', 'serial', 'no_pos', 'frozen',
                 'released', 'volume', 'near', 'far', 'handle_head')

    def __init__(self):
        self.tracks = 0          # +0x04 s8: tracks in use; non-zero = busy
        self.capacity = 1        # +0x05 s8
        self.flags = 0           # +0x06 u16
        self.seq = 0             # +0x08 track 0: sequence pointer
        self.track_link = 0      # +0x0c
        self.track_time = 0      # +0x20 (track +0x18)
        self.track_flags = 0     # +0x24 s16 (track +0x1c); +0x26 (track +0x1e)
        self.track_words = (0, 0, 0, 0)   # +0x10 .. +0x1c floats (track +8..+0x14)
        self.pos = (0, 0, 0)     # +0x2c
        self.serial = 0          # +0x38 u16
        self.no_pos = 0          # +0x3a
        self.frozen = 0          # +0x3b
        self.released = 0        # +0x3c
        self.volume = 0          # +0x40 raw float
        self.near = 0            # +0x44
        self.far = 0             # +0x48
        self.handle_head = None  # +0x28: a ref_core Cell


def anim_push(slot, seq, flags):
    """anim_push(state, anm, flags) 0x170838 for a sequence slot (one track).  Returns
    True when a track was added.  The old track link (+0x0c) is cut: its +0x14 is
    zeroed (`cut` is reported) and the link itself zeroed."""
    if seq == 0 or not sx8(slot.tracks) < sx8(slot.capacity):
        return False, None
    if slot.tracks != 0:
        raise FormatError('a second track would land in the handle and position fields')
    slot.tracks = (slot.tracks + 1) & 0xFF
    slot.flags = (slot.flags | flags) & 0xFFFF
    slot.seq = seq
    slot.track_time = 0
    cut = slot.track_link or None
    slot.track_link = 0
    slot.track_flags = flags
    slot.track_words = (0x3F800000, 0, 0x3F800000, 0)
    return True, cut


class SoundSeqs:
    """g_soundSeqs as seen by sound_playOnObject."""

    def __init__(self, pool=None):
        self.slots = [SeqSlot() for _ in range(SEQ_SLOTS)]
        for i, slot in enumerate(self.slots):
            slot.handle_head = RC.Cell(G_SOUND_SEQS + i * SEQ_STRIDE + 0x28)
        self.serial = 0
        self.limits = [0] * 256
        self.pool = pool
        self.frozen = 0          # game_isFrozen()
        self.groups = {}         # sequence pointer -> category byte (+0x3c of the .anm)

    def play_on_object(self, seq, obj=None, volume=0x3F800000):
        """sound_playOnObject(seq, obj, f12 volume) -> (handle, slot index or None).

        Busy = slot +4 non-zero.  The scan runs over all 32 slots and keeps the LAST
        free one; while scanning, each busy slot of the same non-zero category counts,
        and the call fails as soon as that count reaches the category's cap."""
        if seq == 0:
            return M32, None
        group = self.groups.get(seq, 0) & 0xFF
        chosen, count = -1, 0
        for i, slot in enumerate(self.slots):
            if slot.tracks == 0:
                chosen = i
                continue
            if (self.groups.get(slot.seq, 0) & 0xFF) != group:
                continue
            count += 1
            if group == 0:
                continue
            if not count < sx8(self.limits[group]):
                return M32, None
        if chosen < 0:
            return M32, None
        slot = self.slots[chosen]
        slot.flags = 0
        anim_push(slot, seq, 4)
        if obj is not None:
            self.pool.clear(slot.handle_head)
            self.pool.link(slot.handle_head, obj.heads[0], obj)
            slot.pos = tuple(obj.position)
            slot.no_pos = 0
        else:
            slot.no_pos = 1
        frozen = self.frozen & 0xFF
        old = self.serial
        slot.serial = old
        self.serial = (old + 1) & 0x7F
        slot.frozen = frozen
        slot.released = 0
        slot.volume = volume & M32
        slot.near, slot.far = NEAR, FAR
        return (chosen | (old << 8) | 0x8000), chosen


# ---------------------------------------------------------------------------------------
# 5. Creature_setCharm with a live target
# ---------------------------------------------------------------------------------------
class Creature:
    """What Creature_setCharm reads and writes, plus the three object heads."""

    def __init__(self, addr, flags):
        self.addr, self.flags = addr, flags
        self.heads = [RC.Cell(addr), RC.Cell(addr + 4), RC.Cell(addr + 8)]
        self.target = RC.Cell(addr + 0x234)
        self.team = 0
        self.charm = 0
        self.position = (0, 0, 0)


def set_charm(pool, creature, frames, team):
    """Creature_setCharm(c, frames, team) 0x1189f0.  Returns True when it stored.
    With a live target the handle_clear of +0x234 removes this creature's node and
    the partner node in the target's back list; the target and its other handles are
    untouched.  The word +0x234 is then stored 0 (already 0 after the clear)."""
    charm = creature.charm - 0x10000 if creature.charm & 0x8000 else creature.charm
    if charm == -1:
        return False
    if not creature.flags & 0x20:
        return False
    if creature.flags & 0x40:
        return False
    creature.team = team & 0xFF
    creature.charm = frames & 0xFFFF
    pool.clear(creature.target)
    creature.target.next = None
    return True
