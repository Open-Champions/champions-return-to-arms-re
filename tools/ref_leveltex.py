#!/usr/bin/env python3
"""ref_leveltex.py - reference contract for the level texture file <LEVEL>.TEX of
Champions: Return to Arms (SLUS_209.73): the cell directory, the 0x40-byte cell headers,
the block-table ("streamed") texture form that every level texture on the disc uses, its
per-block entropy coding, the block permutation and the GS placement, written from the
instruction sequences named in each docstring.  docs/formats/level-texture.md is the prose
version with the evidence; this module is its executable form.

A research tool, not game code.  Standard library only; no game data is embedded.  The
functions work on bytes and file offsets, never on the game's addresses: where the game
turns an offset into a pointer (tex_relocateInCell 0x179f28) this module keeps the offset
and offers relocate_offset() to show the arithmetic.

Use
    d = open('LEVEL.TEX', 'rb').read()
    for cell_id, off, size in parse_directory(d):
        cell = d[off:off + size]
        for t in parse_cell(cell):                 # CellTexture per 0x40-byte header
            img = decode_texture(cell, t)          # Image: width, height, indices, palette
    build_cell(...) in the tests makes synthetic cells; nothing here needs a disc.

Status words (CONTRIBUTING.md): O = observed in the code at the address given; D = holds
in every file on the US v2.00 disc (111 level files, 4,808 cells, 157,820 textures);
I = inferred.  Each docstring says which.
"""
import struct
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
from model_info import gs_addr32, gs_addr8, clut_order   # noqa: E402  (same formulas as the lump decoder)


class FormatError(Exception):
    """Raised when the bytes do not follow the contract.  Nothing is guessed."""


def need(cond, msg):
    if not cond:
        raise FormatError(msg)


# ---------------------------------------------------------------- constants (O unless marked)

DIRECTORY_READ_BYTES = 0x5000       # world_fixup reads exactly this much of "<name>.tex" (0x181f24)
DIRECTORY_RECORD = '<iII'           # {s32 cell id, u32 file offset, u32 size} (0x181f98-0x181fd0)
DIRECTORY_END_IDS = (-1, -2)        # (id + 2) <u 2 ends the list (0x181f88-0x181f90)
CELL_ID_ROW = 100                   # id = row * 100 + column (0x17d948-0x17d960)
CELL_ID_BIAS = 50                   # column = floor(x / cellSize) + 50, row likewise (0x17d91c, 0x17d930)
DEFAULT_CELL_SIZE = 960.0           # header +0x68 == 0 -> 960 (0x182264); 720 in every file (D)
STREAM_BLOCK = 0x20000              # the segment cache is 128 KB blocks (0x179f44, 0x17df30)
STREAM_SLOTS = 9                    # streamed cell slots 0-8 (0x17da74); always-loaded slots 9+ (0x17d740)
BLOCK_MAP_ENTRIES = 0x80            # one byte per 128 KB block of a cell, 0xff = unused (0x17dfbc)
HEADER_SIZE = 0x40                  # cell texture header; headers start at 0x40 (0x17e018)
HEADER_FORMAT = '<HHHHHHIIIhhI'     # +0 w, +2 h, +4 blocks, +6 qwords, +8 flags, +0xa, +0xc tex0, +0x10 off, +0x14, +0x18, +0x1a, +0x1c
MAX_CELL_TEXTURES = 16000           # a count above 0x3e80 is reported as an error (0x17e000)

FLAG_INDIRECT = 0x0001              # payload word is itself an offset; never on the disc (D: 0 of 157,820)
FLAG_8BIT = 0x0004                  # 256-colour image (as in lumps)
FLAG_BLOCK_TABLE = 0x0100           # block-table form (tex_relocate 0x179e44, tex_relocateInCell 0x179fa8)
FLAG_UNKNOWN_8 = 0x0008             # set with the two above in every cell texture; no reader found
CELL_FLAGS = FLAG_BLOCK_TABLE | FLAG_UNKNOWN_8 | FLAG_8BIT     # 0x10c in all 157,820 (D)

PSMT8 = 0x13
RELOC_MARKER = 0xa7fb               # stored at +0xa by both relocators (0x179e1c, 0x179f34)
QWORDS_BASE = 0x48                  # relocated qword count starts at 72 (0x179e4c, 0x179fb0)
QWORDS_PER_RECT = 6                 # + 6 per rectangle record (0x179ec8, 0x17a040)
QWORDS_PER_BLOCK = 16               # + 16 per 256-byte block (0x179e98-0x179ebc: blocks * 2048 >> 7)
PALETTE_GS_BLOCKS = 4               # the palette takes blocks tex+0x18 .. +3, the image starts at +4 (0x16c028)

# The shared palette structure that the first payload word points at (worker 0x17ca58).
PALETTE_BYTES = 0x400               # 256 x RGBA, copied as a 16 x 16 PSMCT32 rectangle (0x17ce34-0x17ce88)
SUCCESSOR_OFF = 0x400               # 256 rows of 8 bytes: predicted successors of a colour (0x17cf6c, 0x17d388-0x17d39c)
SUCCESSOR_ROW = 8
HUFFMAN_COUNT_OFF = 0xc00           # u32 n, then u16 symbol[n] (0x17cefc-0x17cf00)
S_WORDS = 18                        # s32 S[18] after the symbols (0x17cf70: T = S + 0x48)
T_WORDS = 17                        # s32 T[17]; T[k] for k in 1..16 is read (0x17cf94, 0x17d338)
MAX_CODE_LENGTH = 16
FAST_BITS = 8                       # 256-entry table for code lengths 1..8 (0x17cf84-0x17d03c)

SYMBOL_LITERALS = 256
SYMBOL_BACKREF_FIRST = 0x100
BACKREF_DELTAS = (-1, -16, -17, -15, -2)      # 5 signed bytes at 0x41c1a0 (O: 0x17d3a0-0x17d3ac)
SYMBOL_SUCCESSOR_FIRST = 0x105
SYMBOL_COUNT = 0x105 + SUCCESSOR_ROW          # 269 symbols: 0..255 literal, 0x100..0x104, 0x105..0x10c

BLOCK_TEXELS = 256                  # one GS block: 16 x 16 8-bit texels = 8 x 8 32-bit pixels
BLOCK_SIDE = 16
PIXEL_SIDE = 8


# ---------------------------------------------------------------- small readers

def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def s8(d, o): return struct.unpack_from('<b', d, o)[0]


# ---------------------------------------------------------------- directory and cells

def parse_directory(d):
    """Records of the directory at the start of the file: list of (cell_id, offset, size).

    O 0x181ec4-0x181fe8 (world_fixup): the game reads the first 0x5000 bytes, skips the
    first u32 (never read; 0 in every file, D), and stops at the first record whose id is
    -1 or -2.  If the first record's id is 0 there is no directory at all (0x181f30).  Ids
    are not range-checked by the game; the caller places each record in the world's cell
    table at index id - lowest (world header +0x58), see cell_table()."""
    need(len(d) >= 4, 'file shorter than the directory word')
    out, o = [], 4
    while True:
        need(o + 12 <= min(len(d), DIRECTORY_READ_BYTES), 'directory not ended within 0x5000 bytes')
        cid, off, size = struct.unpack_from(DIRECTORY_RECORD, d, o)
        if cid in DIRECTORY_END_IDS:
            return out
        if o == 4 and cid == 0:
            return out                                  # "no directory" (0x181f30-0x181f34)
        need(off + size <= len(d), 'cell %d lies past the end of the file' % cid)
        out.append((cid, off, size))
        o += 12


def cell_table(records, lowest, highest):
    """The world's cell table as world_fixup fills it: (highest - lowest + 1) entries of
    {offset, size}, {0, 0x40} where the directory has no record.  O 0x181f3c-0x181fe8."""
    need(highest >= lowest, 'empty id range')
    table = [(0, 0x40)] * (highest - lowest + 1)
    for cid, off, size in records:
        need(lowest <= cid <= highest, 'cell id %d outside the world range %d..%d' % (cid, lowest, highest))
        table[cid - lowest] = (off, size)
    return table


def cell_id_of(x, y, cell_size=720.0):
    """Texture cell holding world position (x, y).  O 0x17d8e0-0x17d930:
    column = floor(x / size) + 50, row = floor(y / size) + 50, id = row * 100 + column."""
    import math
    col = int(math.floor(x / cell_size)) + CELL_ID_BIAS
    row = int(math.floor(y / cell_size)) + CELL_ID_BIAS
    return row * CELL_ID_ROW + col


def cells_around(cell_id):
    """The nine cells worldtex_stream keeps loaded around the focus cell, in the order it
    lists them.  O 0x17d934-0x17d9a4: rows focus-1 .. focus+1, and within a row the
    columns focus+1, focus, focus-1."""
    row, col = divmod(cell_id, CELL_ID_ROW)
    out = []
    for dr in (-1, 0, 1):
        for dc in (1, 0, -1):
            out.append((row + dr) * CELL_ID_ROW + col + dc)
    return out


def relocate_offset(off, block_map, base=0):
    """What tex_relocateInCell (0x179f44-0x179f70) makes of a cell-relative offset: the
    cell was read in 128 KB pieces into arbitrary blocks of the segment cache, block_map[k]
    being the cache block that holds piece k.  Result = base + map[off >> 17] << 17 +
    (off & 0x1ffff).  The always-loaded path passes the identity map (0x17d780-0x17d7a8)."""
    k = off >> 17
    need(0 <= k < len(block_map) and block_map[k] != 0xff, 'offset 0x%x beyond the mapped blocks' % off)
    return base + (block_map[k] << 17) + (off & (STREAM_BLOCK - 1))


class CellTexture(object):
    """One 0x40-byte header of a cell.  Offsets in the header are relative to the cell."""
    __slots__ = ('index', 'width', 'height', 'blocks', 'qwords', 'flags', 'tex0', 'payload_off',
                 'palette_off', 'rects', 'record_end')

    def __init__(self, index, fields):
        (self.width, self.height, self.blocks, self.qwords, self.flags, marker, self.tex0,
         self.payload_off, run14, run18, run1a, run1c) = fields
        self.index = index
        need(marker == 0 and run14 == 0 and run18 == 0 and run1a == 0 and run1c == 0,
             'texture %d: run-time fields are not zero in the file' % index)
        self.palette_off = None
        self.rects = []
        self.record_end = None

    @property
    def dbw(self):
        """Buffer width of the 32-bit upload, in 64-pixel units: (width + 127) >> 7.
        O 0x17cee4-0x17cf08 (worker: BITBLTBUF.DBW of the image rectangles)."""
        return (self.width + 127) >> 7

    def tex0_fields(self):
        return tex0_fields(self.tex0)


def tex0_fields(frag):
    """The TEX0 fragment at header +0xc, bits 14-45 of the register (docs/formats/model-texture.md)."""
    return {'tbw': frag & 0x3f, 'psm': (frag >> 6) & 0x3f, 'tw': (frag >> 12) & 0xf,
            'th': (frag >> 16) & 0xf, 'tcc': (frag >> 20) & 1, 'tfx': (frag >> 21) & 3,
            'rest': frag >> 23}


def parse_cell(cell):
    """Headers and record lists of one cell.  O 0x17dffc-0x17e05c (worldtex_stream after the
    last 128 KB piece arrived): u32 count at 0, headers of 0x40 bytes from 0x40; each is
    handed to tex_relocateInCell, which follows +0x10 to the payload (first word = offset
    of the palette structure, then the rectangle records, read_records()).

    Checks beyond the game's own: flags must be exactly 0x10c, the TEX0 fragment must say
    PSMT8 with TBW = 2 * DBW, every offset must lie inside the cell (the game reads them
    unchecked; D for all 157,820)."""
    need(len(cell) >= HEADER_SIZE, 'cell shorter than its header')
    count = u32(cell, 0)
    need(count <= MAX_CELL_TEXTURES, 'texture count %d above the game limit' % count)
    need(HEADER_SIZE * (count + 1) <= len(cell), 'headers run past the cell')
    out = []
    for i in range(count):
        o = HEADER_SIZE * (i + 1)
        t = CellTexture(i, struct.unpack_from(HEADER_FORMAT, cell, o))
        need(t.flags == CELL_FLAGS, 'texture %d: flags 0x%x, only the block-table form 0x10c is documented' % (i, t.flags))
        f = t.tex0_fields()
        need(f['psm'] == PSMT8, 'texture %d: pixel format 0x%x is not PSMT8' % (i, f['psm']))
        need(f['rest'] == 0, 'texture %d: TEX0 fragment has bits above TFX' % i)
        need(t.width > 0 and t.height > 0, 'texture %d: empty size' % i)
        need(f['tbw'] == 2 * t.dbw, 'texture %d: TBW %d is not twice the upload width %d' % (i, f['tbw'], t.dbw))
        need(t.payload_off + 4 <= len(cell) and t.payload_off % 4 == 0, 'texture %d: payload offset out of the cell' % i)
        t.palette_off = u32(cell, t.payload_off)
        need(t.palette_off + HUFFMAN_COUNT_OFF + 4 <= len(cell), 'texture %d: palette structure out of the cell' % i)
        t.rects, t.record_end = read_records(cell, t.payload_off + 4, t)
        out.append(t)
    return out


def read_records(cell, o, t=None):
    """Rectangle records after the palette word.  O 0x179fe0-0x17a0ac (tex_relocateInCell)
    and 0x17d068-0x17d0e4 (worker): four signed bytes x0, y0, x1, y1 in units of one GS
    block (8 x 8 32-bit pixels = 16 x 16 texels), ended by x0 == -1; then
    (x1 - x0 + 1) * (y1 - y0 + 1) u32 offsets of the blocks, rows y0..y1 outer, columns
    x0..x1 inner.  Returns ([(x0, y0, x1, y1, [offsets])], offset after the terminator).
    Checks beyond the game: x0,y0 >= 0, x1 >= x0, y1 >= y0, the block offsets inside the cell
    and even (the bit reader fetches 16-bit words), and - when the header is given - the
    rectangle inside the upload buffer and the texture's own block grid (D)."""
    rects = []
    while True:
        need(o + 4 <= len(cell), 'record list runs past the cell')
        x0, y0, x1, y1 = struct.unpack_from('<bbbb', cell, o)
        o += 4
        if x0 == -1:
            return rects, o
        need(x0 >= 0 and y0 >= 0 and x1 >= x0 and y1 >= y0, 'bad rectangle %d,%d-%d,%d' % (x0, y0, x1, y1))
        if t is not None:
            need((x1 + 1) * PIXEL_SIDE <= t.dbw * 64, 'rectangle wider than the upload buffer')
            need((x1 + 1) * BLOCK_SIDE <= ((t.width + 15) & ~15), 'rectangle beyond the texture width')
            need((y1 + 1) * BLOCK_SIDE <= ((t.height + 15) & ~15), 'rectangle beyond the texture height')
        n = (x1 - x0 + 1) * (y1 - y0 + 1)
        need(o + 4 * n <= len(cell), 'block offsets run past the cell')
        offs = list(struct.unpack_from('<%dI' % n, cell, o))
        for p in offs:
            need(p + 2 <= len(cell) and p % 2 == 0, 'block offset 0x%x out of the cell or odd' % p)
        o += 4 * n
        rects.append((x0, y0, x1, y1, offs))


def relocated_qwords(rects):
    """The value both relocators store at header +6 (O 0x179f18, 0x17a0b0): 0x48, plus 6 per
    rectangle and 16 per block.  (It is the length of the upload chain the worker builds:
    one 8-bit palette packet of 71 qwords and a DMA tag, then per rectangle the GIF tag,
    BITBLTBUF, TRXPOS, TRXREG, TRXDIR, IMAGE tag and 16 qwords per block.)"""
    n = QWORDS_BASE
    for x0, y0, x1, y1, offs in rects:
        n += QWORDS_PER_RECT + QWORDS_PER_BLOCK * (x1 - x0 + 1) * (y1 - y0 + 1)
    return n & 0xffff


def gs_block_index(bx, by, dbw):
    """GS block number (256 bytes) of 32-bit block (bx, by) in a buffer dbw pages wide:
    page * 32 + the 8 x 4 block table.  Same arithmetic as gs_addr32 / 256."""
    return gs_addr32(bx * PIXEL_SIDE, by * PIXEL_SIDE, dbw) >> 8


def allocation_blocks(t):
    """Header +4, the GS blocks texcache_alloc reserves (O 0x179bb0 reads it; the handler
    puts the palette at the first block and the image at +4, O 0x16c008-0x16c030).  D for
    all 157,820: 4 + (highest block number any rectangle writes) + 1."""
    top = -1
    for x0, y0, x1, y1, offs in t.rects:
        for by in range(y0, y1 + 1):
            for bx in range(x0, x1 + 1):
                top = max(top, gs_block_index(bx, by, t.dbw))
    return PALETTE_GS_BLOCKS + top + 1


# ---------------------------------------------------------------- the palette structure

class Tables(object):
    """The structure the first payload word points at; shared by textures of one cell."""
    __slots__ = ('palette', 'successor', 'symbols', 'S', 'T', 'fast')

    def __init__(self, palette, successor, symbols, S, T):
        self.palette, self.successor, self.symbols, self.S, self.T = palette, successor, symbols, S, T
        self.fast = build_fast_table(symbols, S, T)


def read_tables(cell, q):
    """O 0x17cdec-0x17cf7c: palette = 1,024 bytes at q (256 RGBA in GS CLUT order, uploaded as a
    16 x 16 32-bit rectangle, so clut_order() applies as for lump textures); successor
    table = 2,048 bytes at q + 0x400 (row = previous texel value, 8 bytes); at q + 0xc00
    u32 n, u16 symbol[n], s32 S[18], s32 T[17].

    Checks beyond the game: every symbol below 269, every T[k] with a code below 2**k and
    not decreasing, every T[k] + S[k] a valid symbol index (D)."""
    need(q + HUFFMAN_COUNT_OFF + 4 <= len(cell), 'palette structure out of the cell')
    n = u32(cell, q + HUFFMAN_COUNT_OFF)
    o = q + HUFFMAN_COUNT_OFF + 4
    need(o + 2 * n + 4 * (S_WORDS + T_WORDS) <= len(cell), 'code tables out of the cell')
    symbols = struct.unpack_from('<%dH' % n, cell, o)
    S = struct.unpack_from('<%di' % S_WORDS, cell, o + 2 * n)
    T = struct.unpack_from('<%di' % T_WORDS, cell, o + 2 * n + 4 * S_WORDS)
    need(all(s < SYMBOL_COUNT for s in symbols), 'symbol above 268')
    last = -1
    for k in range(1, MAX_CODE_LENGTH + 1):
        if T[k] >= 0:
            need(T[k] < (1 << k) and T[k] >= last, 'code table: T[%d] = %d is not canonical' % (k, T[k]))
            need(0 <= T[k] + S[k] < n, 'code table: length %d points outside the symbol list' % k)
            last = T[k]
    return Tables(cell[q:q + PALETTE_BYTES], cell[q + SUCCESSOR_OFF:q + HUFFMAN_COUNT_OFF], symbols, S, T)


def build_fast_table(symbols, S, T):
    """The 256-entry table the worker builds in scratchpad (O 0x17cf84-0x17d03c): for every
    8-bit prefix i, the shortest length k in 1..8 with T[k] >= i >> (8 - k) gives
    (symbol[(i >> (8 - k)) + S[k]], k); no such k gives (0, 0), meaning "longer code"."""
    out = []
    for i in range(1 << FAST_BITS):
        entry = (0, 0)
        for k in range(1, FAST_BITS + 1):
            top = i >> (FAST_BITS - k)
            if T[k] >= top:
                entry = (symbols[top + S[k]], k)
                break
        out.append(entry)
    return out


def canonical_tables(lengths):
    """Build (symbols, S, T) from a code length per symbol (0 = no code), the way the game's
    tables are laid out: symbols grouped by length, canonical codes, S[k] = first index of
    length k minus its first code, T[k] = its last code (-1 when none).  S[0], S[17], T[0]
    are never read by the game (0, 0, -1 in every file, D) and are set so here.  Used by the
    tests' encoder; the game only reads these tables."""
    need(len(lengths) <= SYMBOL_COUNT, 'too many symbols')
    by_len = {}
    for sym, L in enumerate(lengths):
        if L:
            need(1 <= L <= MAX_CODE_LENGTH, 'code length out of range')
            by_len.setdefault(L, []).append(sym)
    symbols, S, T = [], [0] * S_WORDS, [-1] * T_WORDS
    code = 0
    for k in range(1, MAX_CODE_LENGTH + 1):
        group = by_len.get(k, [])
        if group:
            need(code + len(group) <= (1 << k), 'code lengths over-subscribe the code space')
            S[k] = len(symbols) - code
            T[k] = code + len(group) - 1
            symbols.extend(group)
        code = (code + len(group)) << 1
    return symbols, S, T


def code_of(symbol, lengths):
    """(code, length) of a symbol under canonical_tables(lengths); for the tests' encoder."""
    symbols, S, T = canonical_tables(lengths)
    L = lengths[symbol]
    need(L, 'symbol has no code')
    return symbols.index(symbol) - S[L], L


# ---------------------------------------------------------------- one block

class BitReader(object):
    """The worker's bit fetch (O 0x17d2a0-0x17d2c4): the stream is little-endian 16-bit
    words consumed from the most significant bit of each word; a 32-bit window is formed
    from words [pos >> 4] and [pos >> 4] + 1 and shifted left by pos & 15."""
    __slots__ = ('d', 'base', 'pos')

    def __init__(self, d, base):
        self.d, self.base, self.pos = d, base, 0

    def peek16(self):
        o = self.base + (self.pos >> 4) * 2
        need(o + 4 <= len(self.d), 'bit stream runs past the cell')
        w0, w1 = struct.unpack_from('<HH', self.d, o)
        return ((((w0 << 16) | w1) << (self.pos & 15)) & 0xffffffff) >> 16


def decode_symbol(r, tables):
    """One canonical Huffman symbol (O 0x17d2a0-0x17d36c): the top 8 bits try the fast table;
    otherwise the top 9 bits are compared with T[9] and the length grows while
    T[k] < top k bits; the symbol is symbol[top_k + S[k]].  Lengths run 1..16."""
    top16 = r.peek16()
    sym, k = tables.fast[top16 >> 8]
    if k == 0:
        k = FAST_BITS + 1
        while k <= MAX_CODE_LENGTH and tables.T[k] < (top16 >> (16 - k)):
            k += 1
        need(k <= MAX_CODE_LENGTH, 'no code matches at bit %d' % r.pos)
        sym = tables.symbols[(top16 >> (16 - k)) + tables.S[k]]
    r.pos += k
    return sym


def decode_block(cell, off, tables):
    """The 256 texels of one block, index i = x + 16 * y of the 16 x 16 texel block (see
    block_permutation()).  O 0x17d288-0x17d3cc: for i in 0..255 a symbol is decoded;
    < 0x100 is the texel value; 0x100..0x104 copies texel i + BACKREF_DELTAS[s - 0x100];
    0x105..0x10c takes successor[previous value][s - 0x105].  Returns (bytes, bits used).
    A back-reference before the block start is refused (the game would read the stack)."""
    out = bytearray(BLOCK_TEXELS)
    r = BitReader(cell, off)
    prev = 0
    for i in range(BLOCK_TEXELS):
        s = decode_symbol(r, tables)
        if s < SYMBOL_BACKREF_FIRST:
            v = s
        elif s < SYMBOL_SUCCESSOR_FIRST:
            j = i + BACKREF_DELTAS[s - SYMBOL_BACKREF_FIRST]
            need(j >= 0, 'back-reference before the block start at texel %d' % i)
            v = out[j]
        else:
            v = tables.successor[prev * SUCCESSOR_ROW + (s - SYMBOL_SUCCESSOR_FIRST)]
        out[i] = v
        prev = v
    return bytes(out), r.pos


def block_permutation():
    """perm[k] for k = r * 32 + c * 4 + j: which decoded texel (x + 16 y) is byte j of 32-bit
    pixel (c, r) of the 8 x 8 block the worker uploads.  O 0x17a0c0-0x17a1c8 (called once
    by texcache_init), transcribed operation for operation.  It is the GS swizzle of 8-bit
    texels inside a 32-bit block; test_ref_leveltex checks it against gs_addr32/gs_addr8."""
    out = []
    for r in range(8):
        for c in range(8):
            base = ((r >> 1) & 3) * 64 + ((c >> 1) & 3) * 16 + (r & 1) * 8 + (c & 1) * 4
            for j in range(4):
                p = base + j
                p2 = p >> 2
                e8 = ((p2 & 2) >> 1) | ((p & 1) << 1)
                x = ((p2 & 1) | ((p2 & 0xc) >> 1) | ((p & 2) << 2)) ^ ((((p >> 6) & 1) ^ (e8 >> 1)) << 2)
                y = (((p >> 6) & 3) << 2) | e8
                out.append(x + 16 * y)
    return out


PERMUTATION = block_permutation()


def block_pixels(texels):
    """The 256 bytes of the 8 x 8 32-bit pixel block as uploaded, raster order, from the 256
    decoded texels.  O 0x17d3d0-0x17d478 (byte k of the raster = texels[perm[k]])."""
    return bytes(texels[PERMUTATION[k]] for k in range(BLOCK_TEXELS))


# ---------------------------------------------------------------- whole texture

class Image(object):
    __slots__ = ('width', 'height', 'indices', 'palette', 'covered', 'tables')

    def __init__(self, w, h, indices, palette, covered, tables):
        self.width, self.height, self.indices, self.palette = w, h, indices, palette
        self.covered, self.tables = covered, tables

    def rgba(self, x, y):
        return self.palette[self.indices[y * self.width + x]]


def palette_entries(palette_bytes):
    """256 (r, g, b, a) in index order from the 1,024 stored bytes (GS CLUT order, bits 3
    and 4 exchanged, as for lump 8-bit textures).  I: the upload is the same 16 x 16 32-bit
    rectangle (O 0x17cdc0-0x17cde8), so the same order applies; the decoded textures look
    right with it, nothing else was checked."""
    return [tuple(palette_bytes[clut_order(i) * 4:clut_order(i) * 4 + 4]) for i in range(256)]


def upload_transfers(cell, t, tables=None):
    """What the worker sends for the texture, as (dest_x, dest_y, width, height, bytes)
    32-bit rectangles into a buffer t.dbw pages wide, in record order (O 0x17d0e8-0x17d200
    for the registers: TRXPOS = (x0 * 8, y0 * 8), TRXREG = ((x1 - x0 + 1) * 8, (y1 - y0 + 1) * 8),
    TRXDIR 0, IMAGE of 16 qwords per block; blocks are decoded row by row, the raster of a
    block row being (x1 - x0 + 1) * 8 pixels wide).  The palette goes first as a 16 x 16
    rectangle at (0, 0) of its own buffer (DBW 1), not returned here."""
    tables = tables or read_tables(cell, t.palette_off)
    out = []
    for x0, y0, x1, y1, offs in t.rects:
        w, h = (x1 - x0 + 1) * PIXEL_SIDE, (y1 - y0 + 1) * PIXEL_SIDE
        buf = bytearray(w * h * 4)
        k = 0
        for by in range(y0, y1 + 1):
            for bx in range(x0, x1 + 1):
                px = block_pixels(decode_block(cell, offs[k], tables)[0])
                k += 1
                for r in range(PIXEL_SIDE):
                    row = ((by - y0) * PIXEL_SIDE + r) * w * 4 + (bx - x0) * PIXEL_SIDE * 4
                    buf[row:row + PIXEL_SIDE * 4] = px[r * 32:r * 32 + 32]
        out.append((x0 * PIXEL_SIDE, y0 * PIXEL_SIDE, w, h, bytes(buf)))
    return out


def decode_texture_via_gs(cell, t, tables=None):
    """Replay of the GS: upload_transfers() placed with gs_addr32 (buffer t.dbw pages), then
    texel (x, y) read with gs_addr8 (buffer TBW / 2 = t.dbw pages).  Slow; the reference
    the shortcut of decode_texture() is tested against."""
    tables = tables or read_tables(cell, t.palette_off)
    mem = {}
    for dx, dy, w, h, buf in upload_transfers(cell, t, tables):
        for y in range(h):
            for x in range(w):
                a = gs_addr32(dx + x, dy + y, t.dbw)
                o = (y * w + x) * 4
                for j in range(4):
                    mem[a + j] = buf[o + j]
    idx = [mem.get(gs_addr8(x, y, t.dbw), 0) for y in range(t.height) for x in range(t.width)]
    cov = [gs_addr8(x, y, t.dbw) in mem for y in range(t.height) for x in range(t.width)]
    return Image(t.width, t.height, idx, palette_entries(tables.palette), cov, tables)


def decode_texture(cell, t, tables=None):
    """Indices of texel (x, y) for the whole width x height: the texel is byte
    (y & 15) * 16 + (x & 15) of the decoded block (x >> 4, y >> 4) when a rectangle covers
    that block, else 0 (and covered[] says so).  Equivalent to decode_texture_via_gs() -
    test_ref_leveltex proves it for every position - because the 32-bit and 8-bit block
    tables of the GS coincide when TBW = 2 * DBW and the permutation is the in-block swizzle.
    Later rectangles overwrite earlier ones, as later uploads do."""
    tables = tables or read_tables(cell, t.palette_off)
    blocks = {}
    for x0, y0, x1, y1, offs in t.rects:
        k = 0
        for by in range(y0, y1 + 1):
            for bx in range(x0, x1 + 1):
                blocks[(bx, by)] = decode_block(cell, offs[k], tables)[0]
                k += 1
    idx, cov = [], []
    for y in range(t.height):
        for x in range(t.width):
            b = blocks.get((x >> 4, y >> 4))
            idx.append(b[(y & 15) * BLOCK_SIDE + (x & 15)] if b is not None else 0)
            cov.append(b is not None)
    return Image(t.width, t.height, idx, palette_entries(tables.palette), cov, tables)


# ---------------------------------------------------------------- synthetic encoder (tests)

def encode_block(texels, lengths, choose=None):
    """Bit stream for 256 texels under code lengths per symbol (canonical_tables).  Each
    texel is coded as the literal symbol unless `choose(i, texels, prev)` returns another
    symbol (a back-reference or successor symbol that reproduces the texel).  Returns bytes
    of 16-bit little-endian words, MSB first, zero padded.  Not game code: the game only
    decodes; this exists so the tests have independently built inputs."""
    need(len(texels) == BLOCK_TEXELS, 'a block has 256 texels')
    bits = []
    prev = 0
    for i, v in enumerate(texels):
        s = choose(i, texels, prev) if choose else None
        if s is None:
            s = v
        code, L = code_of(s, lengths)
        bits.extend(((code >> (L - 1 - b)) & 1) for b in range(L))
        prev = v
    while len(bits) % 16:
        bits.append(0)
    out = bytearray()
    for w in range(0, len(bits), 16):
        word = 0
        for b in bits[w:w + 16]:
            word = (word << 1) | b
        out += struct.pack('<H', word)
    return bytes(out)


def build_cell(textures, lengths, palette=None, successor=None):
    """A synthetic cell: textures = [(width, height, [(x0, y0, x1, y1, [block texel lists])])].
    Lays out count, zero padding, headers, the palette structure, the block streams and the
    record lists, with header fields as the game's files have them (flags 0x10c, PSMT8,
    TW = TH = 10, TCC 1, TFX 0, TBW = 2 * DBW, +4 = allocation_blocks, +6 = 0).  Blocks with
    identical texels share one stream, as on the disc.  Returns bytes."""
    palette = palette or bytes(range(256)) * 4
    successor = successor or bytes(SUCCESSOR_ROW * 256)
    need(len(palette) == PALETTE_BYTES and len(successor) == 0x800, 'palette structure sizes')
    symbols, S, T = canonical_tables(lengths)
    count = len(textures)
    body = bytearray(HEADER_SIZE * (count + 1))
    struct.pack_into('<I', body, 0, count)
    q = len(body)
    body += palette + successor + struct.pack('<I', len(symbols)) + struct.pack('<%dH' % len(symbols), *symbols)
    body += struct.pack('<%di' % S_WORDS, *S) + struct.pack('<%di' % T_WORDS, *T)
    streams = {}
    records = []
    for w, h, rects in textures:
        recs = bytearray()
        for x0, y0, x1, y1, blocks in rects:
            need(len(blocks) == (x1 - x0 + 1) * (y1 - y0 + 1), 'block count of the rectangle')
            recs += struct.pack('<bbbb', x0, y0, x1, y1)
            for tx in blocks:
                key = bytes(tx)
                if key not in streams:
                    streams[key] = len(body)
                    body += encode_block(tx, lengths)
                    if len(body) % 2:
                        body += b'\0'
                recs += struct.pack('<I', streams[key])
        recs += struct.pack('<bbbb', -1, 0, 0, 0)
        records.append(recs)
    offs = []
    for recs in records:
        while len(body) % 4:
            body += b'\0'
        offs.append(len(body))
        body += struct.pack('<I', q) + recs
    for i, (w, h, rects) in enumerate(textures):
        dbw = (w + 127) >> 7
        top = -1
        for x0, y0, x1, y1, blocks in rects:
            for by in range(y0, y1 + 1):
                for bx in range(x0, x1 + 1):
                    top = max(top, gs_block_index(bx, by, dbw))
        tex0 = (2 * dbw) | (PSMT8 << 6) | (10 << 12) | (10 << 16) | (1 << 20)
        struct.pack_into(HEADER_FORMAT, body, HEADER_SIZE * (i + 1), w, h, PALETTE_GS_BLOCKS + top + 1, 0,
                         CELL_FLAGS, 0, tex0, offs[i], 0, 0, 0, 0)
    return bytes(body)


def build_directory(cells, first_word=0):
    """A synthetic <LEVEL>.TEX: cells = [(cell_id, bytes)] placed at 2 KB boundaries after a
    directory of the game's shape (u32, records, -2 terminator)."""
    recs = bytearray(struct.pack('<I', first_word))
    o = 2048
    placed = []
    for cid, c in cells:
        recs += struct.pack(DIRECTORY_RECORD, cid, o, len(c))
        placed.append((o, c))
        o += (len(c) + 2047) & ~2047
    recs += struct.pack(DIRECTORY_RECORD, -2, 0, 0)
    out = bytearray(o)
    out[:len(recs)] = recs
    for o, c in placed:
        out[o:o + len(c)] = c
    return bytes(out)


# ---------------------------------------------------------------- command line

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Describe or export a level texture file (private input; keep exports out of the repository).')
    ap.add_argument('file')
    ap.add_argument('--cell', type=int, help='cell id')
    ap.add_argument('--index', type=int, help='texture index within the cell')
    ap.add_argument('--ppm', help='write the texture (RGB) to this file')
    a = ap.parse_args(argv)
    d = open(a.file, 'rb').read()
    recs = parse_directory(d)
    if a.cell is None:
        print('%d cells' % len(recs))
        for cid, off, size in recs:
            print('cell %5d  offset 0x%08x  size 0x%06x  textures %d' % (cid, off, size, u32(d, off)))
        return 0
    off, size = dict((c, (o, s)) for c, o, s in recs)[a.cell]
    cell = d[off:off + size]
    texs = parse_cell(cell)
    if a.index is None:
        for t in texs:
            print('%3d  %4d x %-4d blocks %3d rects %d' % (t.index, t.width, t.height, t.blocks, len(t.rects)))
        return 0
    img = decode_texture(cell, texs[a.index])
    if a.ppm:
        with open(a.ppm, 'wb') as f:
            f.write(b'P6 %d %d 255\n' % (img.width, img.height))
            f.write(bytes(b for y in range(img.height) for x in range(img.width) for b in img.rgba(x, y)[:3]))
    print('%d x %d, %d of %d texels covered' % (img.width, img.height, sum(img.covered), len(img.covered)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
