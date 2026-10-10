#!/usr/bin/env python3
"""Describe a Snowblind `.world` level file (Champions: Return to Arms, PS2).

  python3 world_info.py LEVEL.world                 summary: header, sections, counts, bounds
  python3 world_info.py LEVEL.world --chunks        one line per chunk
  python3 world_info.py LEVEL.world --elements      one line per terrain element
  python3 world_info.py LEVEL.world --refs          files the level refers to (models, texture cells)
  python3 world_info.py LEVEL.world --check         run the consistency checks used to verify the format
  python3 world_info.py LEVEL.world --tex LEVEL.TEX check texture references against the texture file

Files for inspection (all optional, written only where you say):
  --height-pgm OUT.pgm   terrain height raster, one pixel per 4 units (0 = no ground)
  --flags-pgm OUT.pgm    terrain sample flags: 0 none, 80 open, 160 flag 2, 255 flag 1 or no floor
  --path-pgm OUT.pgm     path grid, one pixel per node: 0 = no links, else 31 * number of links
  --obj OUT.obj          render geometry decoded from the VIF packets, in world space

The layout is documented in docs/formats/world.md. Standard library only. The script
stops with "not a world file" / "bad world file" and exit status 2 when a file does not
fit the layout; it never guesses.
"""
import argparse
import collections
import math
import struct
import sys

HEADER_SIZE = 0x84
CHUNK_SIZE = 0x3C
ELEMENT_SIZE = 0x24
PIECE_SIZE = 0x1C
TERRAIN_CELL = 160      # world units per terrain grid cell
PATH_CELL = 24          # world units between path nodes
SAMPLE_STEP = 4         # world units between height samples
AUTOMAP_CELL = 120      # world units per automap cell
NO_GROUND = -2000       # sample height that means "no floor here"

F_AXIS = 0x1            # orientation is a 3-bit code instead of cos/sin
F_ENVMAP = 0x10
F_PIECE = 0x20          # belongs to a moving piece; bounds padded by 48
F_MIRROR = 0x40
F_WATER = 0x80
F_MODEL = 0x800
F_EMITTER = 0x4000
F_LIGHT = 0x8000
F_NOT_MESH = F_WATER | F_MODEL | F_EMITTER | F_LIGHT

# path link bit -> (dx, dy)
PATH_DIRS = ((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))


class FormatError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise FormatError(msg)


def cstr(data, off, maxlen):
    raw = data[off:off + maxlen]
    return raw.split(b"\0")[0].decode("latin1")


Chunk = collections.namedtuple(
    "Chunk", "index data qwc bmin bmax texoff flags tx ty tz cell rot0 rot1 rot2")
Element = collections.namedtuple(
    "Element", "index minx miny maxx maxy hf flags x y z cos sin")
HeightField = collections.namedtuple("HeightField", "offset x0 y0 w h lo hi")
Piece = collections.namedtuple("Piece", "index chunk count flags x y z cos sin element unk1a")
Batch = collections.namedtuple("Batch", "offset verts normals strip uvs nreg prim")


class World:
    def __init__(self, data):
        self.d = data
        d = data
        need(len(d) >= HEADER_SIZE, "not a world file: shorter than the 0x84-byte header")
        h = struct.unpack_from("<2I2i2I4I2i2I1I2i2I1I2I2iiIfI5I", d, 0)
        (self.nchunks, self.tree_off, self.tg_x0, self.tg_y0, self.tg_w, self.tg_h,
         self.tg_off, self.nelements, self.elem_off, self.chunk_off,
         self.pg_x0, self.pg_y0, self.pg_w, self.pg_h, self.pg_off,
         self.bg_x0, self.bg_y0, self.bg_w, self.bg_h, self.bg_off,
         self.npieces, self.piece_off, self.cell_min, self.cell_max, self.w60,
         self.textable_off, self.cell_size, self.maptex_off,
         self.w70, self.w74, self.tail_off, self.w7c, self.automap_off) = h
        n = len(d)

        need(0 < self.nchunks <= 0xFFFF, "not a world file: chunk count %d" % self.nchunks)
        need(HEADER_SIZE <= self.chunk_off and self.chunk_off + self.nchunks * CHUNK_SIZE <= n,
             "not a world file: chunk table 0x%x x %d does not fit in %d bytes"
             % (self.chunk_off, self.nchunks, n))
        need(self.tree_off == 0 or HEADER_SIZE <= self.tree_off < n - 4,
             "not a world file: tree offset 0x%x" % self.tree_off)
        if self.tree_off:
            need(struct.unpack_from("<H", d, self.tree_off)[0] == 0x4567,
                 "not a world file: no 0x4567 marker at the tree offset 0x%x" % self.tree_off)
        need(self.tg_w <= 4096 and self.tg_h <= 4096, "bad world file: terrain grid %dx%d"
             % (self.tg_w, self.tg_h))
        need(self.nelements <= 1000000 and
             (self.nelements == 0 or self.elem_off + self.nelements * ELEMENT_SIZE <= n),
             "bad world file: terrain element table out of range")
        if self.tg_off:
            need(self.tg_off + 4 * self.tg_w * self.tg_h <= n,
                 "bad world file: terrain grid out of range")
            need(HEADER_SIZE <= self.tail_off < n, "bad world file: tail block offset 0x%x"
                 % self.tail_off)
        need(self.pg_w <= 8192 and self.pg_h <= 8192, "bad world file: path grid %dx%d"
             % (self.pg_w, self.pg_h))
        if self.pg_off:
            need(self.pg_off + 4 * self.pg_w * self.pg_h <= n,
                 "bad world file: path grid out of range")
        if self.bg_off:
            need(self.bg_w <= 65536 and self.bg_h <= 65536 and
                 self.bg_off + (self.bg_w * self.bg_h + 7) // 8 <= n,
                 "bad world file: bit grid out of range")
        need(self.npieces <= 10000 and
             (self.npieces == 0 or self.piece_off + self.npieces * PIECE_SIZE <= n),
             "bad world file: moving piece table out of range")
        need(self.cell_min <= self.cell_max and self.cell_max - self.cell_min < 20000,
             "bad world file: texture cell range %d..%d" % (self.cell_min, self.cell_max))
        need(self.textable_off + 8 * (self.cell_max - self.cell_min + 1) <= n,
             "bad world file: texture cell table out of range")
        need(math.isfinite(self.cell_size) and self.cell_size >= 0,
             "bad world file: texture cell size %r" % self.cell_size)
        need(self.maptex_off < n and self.automap_off < n, "bad world file: automap offsets")

        self.chunks = [self._chunk(i) for i in range(self.nchunks)]
        self.elements = [self._element(i) for i in range(self.nelements)]
        self.heightfields = {}
        for e in self.elements:
            if e.hf not in self.heightfields:
                self.heightfields[e.hf] = self._heightfield(e.hf)
        self.pieces = [self._piece(i) for i in range(self.npieces)]
        self._samples = {}
        self._batches = {}

    # ---- records -------------------------------------------------------
    def _chunk(self, i):
        o = self.chunk_off + i * CHUNK_SIZE
        data, qwc = struct.unpack_from("<II", self.d, o)
        b = struct.unpack_from("<6f", self.d, o + 8)
        texoff, flags, tx, ty, tz = struct.unpack_from("<IIiii", self.d, o + 0x20)
        cell, r0, r1, r2 = struct.unpack_from("<4h", self.d, o + 0x34)
        need(data < len(self.d), "bad world file: chunk %d data offset 0x%x" % (i, data))
        need(all(math.isfinite(x) for x in b), "bad world file: chunk %d bounds" % i)
        return Chunk(i, data, qwc, b[:3], b[3:], texoff, flags, tx, ty, tz, cell, r0, r1, r2)

    def _element(self, i):
        o = self.elem_off + i * ELEMENT_SIZE
        x0, y0, x1, y1, _stamp, hf, flags, x, y, z, c, s = struct.unpack_from(
            "<4hIIIiiihh", self.d, o)
        need(HEADER_SIZE <= hf <= len(self.d) - 0x14,
             "bad world file: terrain element %d height field offset 0x%x" % (i, hf))
        return Element(i, x0, y0, x1, y1, hf, flags, x, y, z, c, s)

    def _heightfield(self, off):
        x0, y0, w, h, lo, hi = struct.unpack_from("<iiIIhh", self.d, off)
        need(0 < w <= 4096 and 0 < h <= 4096 and off + 0x14 + 2 * w * h <= len(self.d),
             "bad world file: height field at 0x%x is %dx%d" % (off, w, h))
        return HeightField(off, x0, y0, w, h, lo, hi)

    def _piece(self, i):
        o = self.piece_off + i * PIECE_SIZE
        first, count, flags, x, y, z, c, s, el, unk = struct.unpack_from("<ihHiiihhhh", self.d, o)
        need(0 <= first and first + count <= self.nchunks and 0 <= el < max(1, self.nelements),
             "bad world file: moving piece %d refers outside the tables" % i)
        return Piece(i, first, count, flags, x, y, z, c, s, el, unk)

    def samples(self, hf):
        """Raw s16 samples of a height field (height = v >> 4, flags = v & 15)."""
        s = self._samples.get(hf.offset)
        if s is None:
            s = struct.unpack_from("<%dh" % (hf.w * hf.h), self.d, hf.offset + 0x14)
            self._samples[hf.offset] = s
        return s

    # ---- tables --------------------------------------------------------
    def path_cells(self):
        if not self.pg_off:
            return ()
        return struct.unpack_from("<%dI" % (self.pg_w * self.pg_h), self.d, self.pg_off)

    def terrain_cell_list(self, i, j):
        """Element indices listed for terrain grid cell (i, j)."""
        v, = struct.unpack_from("<I", self.d, self.tg_off + 4 * (j * self.tg_w + i))
        o = self.tail_off + v
        out = []
        while True:
            need(o + 2 <= len(self.d), "bad world file: terrain cell list runs off the file")
            e, = struct.unpack_from("<h", self.d, o)
            if e == -1:
                return out, o + 2
            need(0 <= e < self.nelements, "bad world file: terrain cell list entry %d" % e)
            out.append(e)
            o += 2

    def automap(self):
        if not self.automap_off:
            return None
        x0, y0, w, h = struct.unpack_from("<4h", self.d, self.automap_off)
        need(0 <= w <= 216 and 0 <= h <= 216 and
             self.automap_off + 8 + 2 * w * h <= len(self.d), "bad world file: automap grid")
        return x0, y0, w, h

    def tree_stats(self):
        """Walk the chunk tree. Returns (nodes, leaves, depth, end offset, leaf chunk refs)."""
        if not self.tree_off:
            return 0, 0, 0, 0, collections.Counter()
        d = self.d
        refs = collections.Counter()
        nodes = leaves = depth = 0
        end = self.tree_off + 2
        stack = [(self.tree_off + 2, 1)]
        seen = set()
        while stack:
            o, lvl = stack.pop()
            need(o + 2 <= len(d) and o not in seen, "bad world file: chunk tree is not a tree")
            seen.add(o)
            depth = max(depth, lvl)
            w0, = struct.unpack_from("<H", d, o)
            if w0 & 0x8000:
                nodes += 1
                need((w0 & 0xFFF) < 3 and o + 20 <= len(d),
                     "bad world file: tree node at 0x%x has axis %d" % (o, w0 & 0xFFF))
                skip, = struct.unpack_from("<h", d, o + 18)
                stack.append((o + 20, lvl + 1))
                stack.append((o + 18 + 2 * skip, lvl + 1))
                end = max(end, o + 20)
            else:
                leaves += 1
                need(o + 2 + 2 * w0 <= len(d), "bad world file: tree leaf runs off the file")
                for c in struct.unpack_from("<%dH" % w0, d, o + 2):
                    need(c < self.nchunks, "bad world file: tree leaf names chunk %d" % c)
                    refs[c] += 1
                end = max(end, o + 2 + 2 * w0)
        return nodes, leaves, depth, end, refs

    # ---- transforms ----------------------------------------------------
    def chunk_matrix(self, c):
        """(a, b, c, d) with world.x = a*lx + b*ly, world.y = c*lx + d*ly."""
        if c.flags & F_AXIS:
            code = c.rot0 & 7
            sx = -1.0 if code & 1 else 1.0
            sy = -1.0 if code & 2 else 1.0
            if code & 4:
                return 0.0, sy, sx, 0.0
            return sx, 0.0, 0.0, sy
        co, si = c.rot0 / 32767.0, c.rot1 / 32767.0
        if c.flags & F_MIRROR:
            return co, si, si, -co
        return co, -si, si, co

    def chunk_origin(self, c):
        """World position of the chunk's local origin.

        Mesh chunks add the translation before rotating; for water, models, emitters and
        lights the translation is already in world axes."""
        lx, ly = c.tx * 0.25, c.ty * 0.25
        if c.flags & F_NOT_MESH:
            return lx, ly, c.tz * 0.25
        a, b, cc, dd = self.chunk_matrix(c)
        return a * lx + b * ly, cc * lx + dd * ly, c.tz * 0.25

    def element_to_world(self, e, sx, sy):
        """World x, y of height sample (sx, sy) (sample indices, not array indices)."""
        co, si = e.cos / 32767.0, e.sin / 32767.0
        lx, ly = sx * SAMPLE_STEP, sy * SAMPLE_STEP
        if e.flags & 1:
            return lx * co + ly * si + e.x, lx * si - ly * co + e.y
        return lx * co - ly * si + e.x, lx * si + ly * co + e.y

    # ---- VIF packets ---------------------------------------------------
    def batches(self, c):
        """Decode the VIF packet of a mesh chunk into batches."""
        d = self.d
        key = (c.data, c.qwc)
        if key in self._batches:                  # packets are shared between chunks
            return self._batches[key]
        p, end = c.data, c.data + c.qwc * 16
        need(end <= len(d), "bad world file: chunk %d packet runs off the file" % c.index)
        out = []
        cur = None
        last = None

        def close():
            nonlocal cur, last
            if cur is None:
                return
            need(all(k in cur for k in ("normals", "vlocs", "extra", "tags")),
                 "bad world file: incomplete batch at 0x%x" % cur["off"])
            nloop = cur["tags"][0][0] & 0x7FFF
            hi = cur["tags"][0][1]
            nreg = (hi >> 28) & 0xF
            prim = (hi >> 15) & 0x7FF
            need(nreg in (3, 4), "bad world file: batch at 0x%x has %d registers per vertex"
                 % (cur["off"], nreg))
            vl = cur["vlocs"]
            nv = len(cur["verts"])
            need(len(vl) == nv + 2 and len(cur["normals"]) == nv,
                 "bad world file: batch at 0x%x table sizes disagree" % cur["off"])
            # Replay in stream order: row j first copies src -> dst (using what is in the
            # strip so far), then places vertex j - 2 at a. Extra copies come last.
            slots = [None] * nloop
            ex = cur["extra"]
            need(ex[0][0] == len(ex) - 1, "bad world file: batch at 0x%x extra copy count"
                 % cur["off"])

            def copy(src, dst):
                if src == dst:
                    return
                s, t = (src & 0x7FFF) // nreg, (dst & 0x7FFF) // nreg
                need(s < nloop and t < nloop and slots[s] is not None and slots[t] is None,
                     "bad world file: batch at 0x%x strip copy %d -> %d" % (cur["off"], s, t))
                slots[t] = (slots[s][0], dst >> 15)

            for j in range(2, nv + 2):
                a, src, dst = vl[j]
                copy(src, dst)
                s = (a & 0x7FFF) // nreg
                need(s < nloop and slots[s] is None,
                     "bad world file: batch at 0x%x strip slot %d" % (cur["off"], s))
                slots[s] = (j - 2, a >> 15)
            for row in ex[1:]:
                copy(row[0], row[1])
                copy(row[2], row[3])
            need(all(s is not None for s in slots),
                 "bad world file: batch at 0x%x leaves strip slots empty" % cur["off"])
            last = {"off": cur["off"], "verts": cur["verts"], "normals": cur["normals"],
                    "strip": slots, "uvs": None, "nreg": nreg, "prim": prim}
            out.append(last)
            cur = None

        while p < end:
            w, = struct.unpack_from("<I", d, p)
            cmd, num, imm = (w >> 24) & 0x7F, (w >> 16) & 0xFF, w & 0xFFFF
            here = p
            p += 4
            if cmd in (0x00, 0x01, 0x04, 0x05, 0x11):    # NOP, STCYCL, ITOP, STMOD, FLUSH
                continue
            if cmd == 0x14:                               # MSCAL: batch is complete
                close()
                continue
            if cmd == 0x50:                               # DIRECT: GS state for the chunk
                p += (imm or 65536) * 16
                continue
            need(cmd & 0x60 == 0x60, "bad world file: VIF code 0x%02x at 0x%x in chunk %d"
                 % (cmd, here, c.index))
            vn, vl = (cmd >> 2) & 3, cmd & 3
            n = num or 256
            unsigned = (imm >> 14) & 1
            need(vl < 3, "bad world file: VIF unpack format 0x%02x at 0x%x" % (cmd, here))
            comp = vn + 1
            size = comp * (4, 2, 1)[vl]
            fmt = "<%d%s" % (n * comp, ("iI", "hH", "bB")[vl][unsigned])
            need(p + n * size <= end, "bad world file: VIF unpack at 0x%x runs past the packet"
                 % here)
            vals = struct.unpack_from(fmt, d, p)
            rows = [vals[k:k + comp] for k in range(0, n * comp, comp)]
            p += (n * size + 3) & ~3
            kind = (comp, (32, 16, 8)[vl], unsigned)
            if kind == (3, 16, 0):
                close()
                cur = {"off": here, "verts": rows}
            elif kind == (3, 8, 0):
                need(cur is not None, "bad world file: normals without positions at 0x%x" % here)
                cur["normals"] = rows
            elif kind == (3, 16, 1):
                need(cur is not None, "bad world file: strip table without positions at 0x%x"
                     % here)
                cur["vlocs"] = rows
            elif kind == (4, 16, 1):
                need(cur is not None, "bad world file: stray V4-16 at 0x%x" % here)
                cur["extra"] = rows
            elif kind == (4, 32, 1):
                need(cur is not None, "bad world file: stray GIF tag at 0x%x" % here)
                cur["tags"] = rows
            elif kind == (2, 16, 1):
                need(last is not None and last["uvs"] is None and
                     len(rows) == len(last["strip"]),
                     "bad world file: texture coordinates at 0x%x do not match a batch" % here)
                last["uvs"] = rows
            else:
                raise FormatError("bad world file: unexpected VIF unpack V%d-%d at 0x%x"
                                  % (comp, kind[1], here))
        close()
        result = [Batch(b["off"], b["verts"], b["normals"], b["strip"], b["uvs"], b["nreg"],
                        b["prim"]) for b in out]
        self._batches[key] = result
        return result

    def chunk_world_vertices(self, c, batch):
        a, b, cc, dd = self.chunk_matrix(c)
        out = []
        for vx, vy, vz in batch.verts:
            lx, ly = (vx + c.tx) * 0.25, (vy + c.ty) * 0.25
            out.append((a * lx + b * ly, cc * lx + dd * ly, (vz + c.tz) * 0.25))
        return out

    @staticmethod
    def triangles(batch):
        """Triangles of a batch as triples of vertex indices (strip restarts honoured)."""
        s = batch.strip
        out = []
        for k in range(2, len(s)):
            if s[k][1]:
                continue
            a, b, c = s[k - 2][0], s[k - 1][0], s[k][0]
            if a != b and b != c and a != c:
                out.append((a, b, c))
        return out


def chunk_kind(c):
    if c.flags & F_WATER:
        return "water"
    if c.flags & F_MODEL:
        return "model"
    if c.flags & F_EMITTER:
        return "emitter"
    if c.flags & F_LIGHT:
        return "light"
    return "mesh"


# ---- reports -------------------------------------------------------------
def sections(w):
    """Byte ranges of everything the header reaches, sorted."""
    d = w.d
    out = [(0, HEADER_SIZE, "header")]
    if w.pg_off:
        out.append((w.pg_off, w.pg_off + 4 * w.pg_w * w.pg_h, "path grid"))
    if w.bg_off:
        out.append((w.bg_off, w.bg_off + (w.bg_w * w.bg_h + 7) // 8, "bit grid (no reader found)"))
    if w.maptex_off:
        out.append((w.maptex_off, w.maptex_off + 0x40, "automap texture header"))
    if w.heightfields:
        lo = min(w.heightfields)
        hi = max(h.offset + 0x14 + 2 * h.w * h.h for h in w.heightfields.values())
        out.append((lo, hi, "height fields x%d" % len(w.heightfields)))
    if w.tree_off:
        out.append((w.tree_off, w.tree_stats()[3], "chunk tree"))
    if w.npieces:
        out.append((w.piece_off, w.piece_off + w.npieces * PIECE_SIZE, "moving pieces"))
    datas = {}
    for c in w.chunks:
        kind = chunk_kind(c)
        size = {"mesh": c.qwc * 16, "water": 0x90, "model": 0xB0, "emitter": 0x48,
                "light": 0x30}[kind]
        datas[c.data] = max(datas.get(c.data, 0), size)
    if datas:
        out.append((min(datas), max(k + v for k, v in datas.items()),
                    "chunk data x%d" % len(datas)))
    out.append((w.textable_off, w.textable_off + 8 * (w.cell_max - w.cell_min + 1),
                "texture cell table"))
    am = w.automap()
    if am:
        out.append((w.automap_off, w.automap_off + 8 + 2 * am[2] * am[3], "automap grid"))
    if w.tg_off:
        ends = []
        starts = []
        for j in range(w.tg_h):
            for i in range(w.tg_w):
                v, = struct.unpack_from("<I", d, w.tg_off + 4 * (j * w.tg_w + i))
                starts.append(w.tail_off + v)
                ends.append(w.terrain_cell_list(i, j)[1])
        if starts:
            out.append((min(starts), max(ends), "terrain cell lists"))
        out.append((w.tg_off, w.tg_off + 4 * w.tg_w * w.tg_h, "terrain grid"))
    if w.nelements:
        out.append((w.elem_off, w.elem_off + w.nelements * ELEMENT_SIZE, "terrain elements"))
    out.append((w.chunk_off, w.chunk_off + w.nchunks * CHUNK_SIZE, "chunk table"))
    out.sort()
    return out


def summary(w, name):
    d = w.d
    print("%s: %d bytes" % (name, len(d)))
    print("header")
    print("  chunks             %d at 0x%x" % (w.nchunks, w.chunk_off))
    print("  chunk tree         0x%x" % w.tree_off)
    print("  terrain grid       origin (%d, %d) size %dx%d cells of %d at 0x%x"
          % (w.tg_x0, w.tg_y0, w.tg_w, w.tg_h, TERRAIN_CELL, w.tg_off))
    print("  terrain elements   %d at 0x%x" % (w.nelements, w.elem_off))
    print("  path grid          origin (%d, %d) size %dx%d nodes %d apart at 0x%x"
          % (w.pg_x0, w.pg_y0, w.pg_w, w.pg_h, PATH_CELL, w.pg_off))
    print("  bit grid           origin (%d, %d) size %dx%d at 0x%x"
          % (w.bg_x0, w.bg_y0, w.bg_w, w.bg_h, w.bg_off))
    print("  moving pieces      %d at 0x%x" % (w.npieces, w.piece_off))
    print("  texture cells      ids %d..%d, table at 0x%x, cell size %g"
          % (w.cell_min, w.cell_max, w.textable_off, w.cell_size or 960.0))
    print("  automap            texture 0x%x, grid 0x%x" % (w.maptex_off, w.automap_off))
    print("  tail block         0x%x" % w.tail_off)
    print("  +0x60 %d  +0x70 %d  +0x74 %d  +0x7c %d" % (w.w60, w.w70, w.w74, w.w7c))

    print("sections")
    prev = 0
    last = ""
    for a, b, label in sections(w):
        if a > prev:
            gap = d[prev:a]
            if last == "automap texture header":
                what = "automap texture data, not decoded here"
            else:
                what = "padding" if not any(gap) else "data not described"
            print("  0x%06x-0x%06x  (%d bytes of %s)" % (prev, a, a - prev, what))
        print("  0x%06x-0x%06x  %s" % (a, b, label))
        prev = max(prev, b)
        last = label
    if prev < len(d):
        print("  0x%06x-0x%06x  (%d trailing bytes)" % (prev, len(d), len(d) - prev))

    kinds = collections.Counter(chunk_kind(c) for c in w.chunks)
    flags = collections.Counter(c.flags for c in w.chunks)
    print("chunks by kind: " + ", ".join("%s %d" % kv for kv in sorted(kinds.items())))
    print("chunks by flag word: " + ", ".join("0x%x x%d" % kv for kv in sorted(flags.items())))
    hidden = sum(1 for c in w.chunks if chunk_kind(c) == "mesh" and c.cell == 0)
    print("mesh chunks with texture cell 0 (never drawn): %d" % hidden)
    mn = [min(c.bmin[k] for c in w.chunks) for k in range(3)]
    mx = [max(c.bmax[k] for c in w.chunks) for k in range(3)]
    print("bounding box of all chunks: (%.1f, %.1f, %.1f) to (%.1f, %.1f, %.1f)"
          % (mn[0], mn[1], mn[2], mx[0], mx[1], mx[2]))

    nodes, leaves, depth, _end, refs = w.tree_stats()
    print("chunk tree: %d split nodes, %d leaves, depth %d, %d chunks referenced (%d more than once)"
          % (nodes, leaves, depth, len(refs), sum(1 for v in refs.values() if v > 1)))

    if w.elements:
        lo = hi = None
        nsamp = flagged = holes = 0
        for hf in w.heightfields.values():
            for v in w.samples(hf):
                nsamp += 1
                if v & 15:
                    flagged += 1
                if v >> 4 <= NO_GROUND:
                    holes += 1
        for e in w.elements:
            hf = w.heightfields[e.hf]
            real = [v >> 4 for v in w.samples(hf) if v >> 4 > NO_GROUND]
            if real:
                a, b = min(real) + e.z, max(real) + e.z
                lo = a if lo is None else min(lo, a)
                hi = b if hi is None else max(hi, b)
        ef = collections.Counter(e.flags for e in w.elements)
        print("terrain: %d elements using %d height fields; %d stored samples (%d flagged, %d no-floor)"
              % (len(w.elements), len(w.heightfields), nsamp, flagged, holes))
        print("terrain: element flags " + ", ".join("%d x%d" % kv for kv in sorted(ef.items()))
              + "; ground height %s..%s" % (lo, hi))
        print("terrain: covers x %d..%d, y %d..%d"
              % (min(e.minx for e in w.elements), max(e.maxx for e in w.elements),
                 min(e.miny for e in w.elements), max(e.maxy for e in w.elements)))
    cells = w.path_cells()
    if cells:
        linked = sum(1 for v in cells if v & 0xFF)
        links = sum(bin(v & 0xFF).count("1") for v in cells)
        print("path grid: %d nodes, %d with links, %d links; x %d..%d, y %d..%d"
              % (len(cells), linked, links, w.pg_x0 * PATH_CELL,
                 (w.pg_x0 + w.pg_w - 1) * PATH_CELL, w.pg_y0 * PATH_CELL,
                 (w.pg_y0 + w.pg_h - 1) * PATH_CELL))
    else:
        print("path grid: none")
    am = w.automap()
    if am:
        print("automap: %dx%d cells of %d units, cell = (%d + x/120, %d + y/120)"
              % (am[2], am[3], AUTOMAP_CELL, am[0], am[1]))
    for p in w.pieces:
        print("moving piece %d: chunk %d (+%d), terrain element %d, rest position (%.2f, %.2f, %.2f)"
              % (p.index, p.chunk, p.count, p.element, p.x * 0.25, p.y * 0.25, p.z * 0.25))


def list_chunks(w):
    print("index kind    flags    data     qwc  cell texoff  origin(x,y,z)              bounds")
    for c in w.chunks:
        ox, oy, oz = w.chunk_origin(c)
        print("%5d %-7s 0x%-6x 0x%06x %4d %5d 0x%-5x (%9.2f,%9.2f,%8.2f) "
              "(%.1f,%.1f,%.1f)-(%.1f,%.1f,%.1f)"
              % ((c.index, chunk_kind(c), c.flags, c.data, c.qwc if chunk_kind(c) == "mesh" else 0,
                  c.cell, c.texoff if chunk_kind(c) == "mesh" else 0, ox, oy, oz)
                 + tuple(c.bmin) + tuple(c.bmax)))


def list_elements(w):
    print("index flags  position(x,y,z)      cos    sin   bounds(x0,y0,x1,y1)        field    size   min   max")
    for e in w.elements:
        hf = w.heightfields[e.hf]
        print("%5d %5d (%6d,%6d,%5d) %6.3f %6.3f (%6d,%6d,%6d,%6d) 0x%06x %3dx%-3d %5d %5d"
              % (e.index, e.flags, e.x, e.y, e.z, e.cos / 32767.0, e.sin / 32767.0,
                 e.minx, e.miny, e.maxx, e.maxy, hf.offset, hf.w, hf.h, hf.lo, hf.hi))


def list_refs(w):
    d = w.d
    cells = collections.Counter(c.cell for c in w.chunks if chunk_kind(c) == "mesh" and c.cell)
    print("texture cells used by mesh chunks (id = row*100 + column, cell (50,50) starts at the origin):")
    for cid, n in sorted(cells.items()):
        col, row = cid % 100, cid // 100
        s = w.cell_size or 960.0
        print("  %d  column %d row %d  x %g..%g  y %g..%g  %d chunks"
              % (cid, col, row, (col - 50) * s, (col - 49) * s, (row - 50) * s, (row - 49) * s, n))
    models = collections.Counter()
    for c in w.chunks:
        if chunk_kind(c) == "model":
            models[(cstr(d, c.data, 0x50), cstr(d, c.data + 0x50, 0x50),
                    struct.unpack_from("<I", d, c.data + 0xAC)[0])] += 1
    print("placed models (lump, model, flags):")
    for (lump, model, fl), n in sorted(models.items()):
        print("  %s.lmp  %s  flags 0x%x  x%d" % (lump, model, fl, n))
    emit = collections.Counter(cstr(d, c.data + 0x3D, 11) for c in w.chunks
                               if chunk_kind(c) == "emitter")
    print("particle emitter records: " + (", ".join("%s x%d" % kv for kv in sorted(emit.items()))
                                          or "none"))
    lights = collections.Counter(cstr(d, c.data, 16) for c in w.chunks if chunk_kind(c) == "light")
    print("light records: " + (", ".join("%s x%d" % kv for kv in sorted(lights.items())) or "none"))


def check(w):
    """Consistency checks. Returns the number of failures."""
    d = w.d
    bad = 0

    def report(label, fails, total, note=""):
        nonlocal bad
        print("  %-58s %s (%d of %d)%s" % (label, "ok" if not fails else "FAIL",
                                           total - fails, total, note))
        if fails:
            bad += 1

    # 1. every mesh packet decodes, strip tables fill every slot once, UV count = strip length
    nb = nv = ntri = nostart = 0
    box_fail = box_n = 0
    worst = 0.0
    for c in w.chunks:
        if chunk_kind(c) != "mesh":
            continue
        mn = [1e30] * 3
        mx = [-1e30] * 3
        for b in w.batches(c):
            nb += 1
            nv += len(b.verts)
            ntri += len(w.triangles(b))
            if len(b.strip) < 3 or not (b.strip[0][1] and b.strip[1][1]):
                nostart += 1
            need(b.uvs is not None, "bad world file: batch at 0x%x has no texture coordinates"
                 % b.offset)
            for v in w.chunk_world_vertices(c, b):
                for k in range(3):
                    mn[k] = min(mn[k], v[k])
                    mx[k] = max(mx[k], v[k])
        if mn[0] > mx[0]:
            continue
        pad = 48.0 if c.flags & F_PIECE else 0.0
        err = max(max(abs(mn[k] - pad - c.bmin[k]) for k in range(3)),
                  max(abs(mx[k] + pad - c.bmax[k]) for k in range(3)))
        box_n += 1
        worst = max(worst, err)
        if err > 1.0:
            box_fail += 1
    print("  mesh packets: %d batches, %d vertices, %d triangles decoded" % (nb, nv, ntri))
    report("first two strip positions of a batch carry the restart bit", nostart, nb)
    print("  %-58s %d of %d within 1 unit (worst %.2f)"
          % ("stored chunk bounds = bounds of decoded vertices", box_n - box_fail, box_n, worst))

    # 2. chunk tree reaches every chunk
    _n, _l, _dp, _e, refs = w.tree_stats()
    report("chunk tree references every chunk", w.nchunks - len(refs), w.nchunks)

    # 2b. tree split planes bound the chunks below them; bit 0x4000 marks water subtrees
    if w.tree_off:
        fails = wfails = nnodes = 0
        axes = collections.Counter()

        def walk(o):
            """Returns (min xyz, max xyz, has water) of the chunks under the node at o."""
            nonlocal fails, wfails, nnodes
            w0, = struct.unpack_from("<H", d, o)
            if not w0 & 0x8000:
                mn, mx, water = [1e30] * 3, [-1e30] * 3, False
                for ci in struct.unpack_from("<%dH" % w0, d, o + 2):
                    c = w.chunks[ci]
                    water = water or bool(c.flags & F_WATER)
                    if c.flags & (F_EMITTER | F_LIGHT):
                        continue                 # effect bounds overhang the planes
                    for k in range(3):
                        mn[k] = min(mn[k], c.bmin[k])
                        mx[k] = max(mx[k], c.bmax[k])
                return mn, mx, water
            hi1, lo2, zlo, zhi = struct.unpack_from("<4i", d, o + 2)
            skip, = struct.unpack_from("<h", d, o + 18)
            axis = w0 & 0xFFF
            axes[axis] += 1
            a = walk(o + 20)
            b = walk(o + 18 + 2 * skip)
            nnodes += 1
            mn = [min(a[0][k], b[0][k]) for k in range(3)]
            mx = [max(a[1][k], b[1][k]) for k in range(3)]
            if (a[1][axis] > hi1 * 4 + 4 or b[0][axis] < lo2 * 4 - 4 or
                    mn[2] < zlo * 4 - 4 or mx[2] > zhi * 4 + 4):
                fails += 1
            if bool(w0 & 0x4000) != (a[2] or b[2]):
                wfails += 1
            return mn, mx, a[2] or b[2]

        sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
        walk(w.tree_off + 2)
        report("tree nodes: split values, z range bound non-effect chunks", fails, nnodes,
               "  axes used: " + ", ".join("%d x%d" % kv for kv in sorted(axes.items())))
        report("tree node bit 0x4000 <=> a water chunk below it", wfails, nnodes)

    # 3. moving pieces <-> flag 0x20
    inpiece = set()
    for p in w.pieces:
        inpiece.update(range(p.chunk, p.chunk + p.count))
    fails = sum(1 for c in w.chunks if (c.index in inpiece) != bool(c.flags & F_PIECE))
    report("flag 0x20 exactly on moving-piece chunks", fails, w.nchunks)

    # 4. terrain element flag 4 <=> height field has flagged samples
    fails = 0
    for e in w.elements:
        any_flag = any(v & 15 for v in w.samples(w.heightfields[e.hf]))
        if bool(e.flags & 4) != any_flag:
            fails += 1
    report("element flag 4 <=> its height field has flagged samples", fails, len(w.elements))

    # 5. stored element rectangle contains every sample that has ground
    hull = {}
    for hf in w.heightfields.values():
        sm = w.samples(hf)
        pts = []
        for j in range(hf.h):
            row = [i for i in range(hf.w) if sm[j * hf.w + i] >> 4 > NO_GROUND]
            if row:
                pts.append((hf.x0 + row[0], hf.y0 + j))
                pts.append((hf.x0 + row[-1], hf.y0 + j))
        hull[hf.offset] = pts
    fails = 0
    for e in w.elements:
        pts = [w.element_to_world(e, sx, sy) for sx, sy in hull[e.hf]]
        if pts and (min(p[0] for p in pts) < e.minx or max(p[0] for p in pts) > e.maxx or
                    min(p[1] for p in pts) < e.miny or max(p[1] for p in pts) > e.maxy):
            fails += 1
    report("element rectangle contains its samples that have ground", fails, len(w.elements))

    # 6. terrain grid lists: an element is listed in every cell its rectangle touches
    if w.tg_off:
        listed = collections.defaultdict(set)
        for j in range(w.tg_h):
            for i in range(w.tg_w):
                for e in w.terrain_cell_list(i, j)[0]:
                    listed[e].add((i, j))
        fails = 0
        for e in w.elements:
            i0 = max(0, math.floor(e.minx / TERRAIN_CELL) - w.tg_x0)
            i1 = min(w.tg_w - 1, math.floor(e.maxx / TERRAIN_CELL) - w.tg_x0)
            j0 = max(0, math.floor(e.miny / TERRAIN_CELL) - w.tg_y0)
            j1 = min(w.tg_h - 1, math.floor(e.maxy / TERRAIN_CELL) - w.tg_y0)
            want = {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)}
            if not want <= listed[e.index]:
                fails += 1
        report("terrain grid lists cover each element's rectangle", fails, len(w.elements))

    # 7. path links stay on the grid, upper 24 bits clear
    cells = w.path_cells()
    if cells:
        fails = 0
        for idx, v in enumerate(cells):
            if v >> 8:
                fails += 1
                continue
            i, j = idx % w.pg_w, idx // w.pg_w
            for bit, (dx, dy) in enumerate(PATH_DIRS):
                if v >> bit & 1 and not (0 <= i + dx < w.pg_w and 0 <= j + dy < w.pg_h):
                    fails += 1
                    break
        report("path nodes: only link bits set, links stay on the grid", fails, len(cells))

    # 8. texture cell ids in range
    fails = sum(1 for c in w.chunks if chunk_kind(c) == "mesh" and c.cell and
                not w.cell_min <= c.cell <= w.cell_max)
    report("mesh texture cell ids inside the header range", fails,
           sum(1 for c in w.chunks if chunk_kind(c) == "mesh"))
    return bad


def check_tex(w, path):
    """Check mesh chunk texture references against the level's .TEX file."""
    t = open(path, "rb").read()
    need(len(t) >= 16, "texture file is too short")
    cells = {}
    o = 4
    while True:
        need(o + 4 <= len(t), "texture file directory has no terminator")
        cid, = struct.unpack_from("<i", t, o)
        if cid in (-1, -2):
            break
        off, size = struct.unpack_from("<II", t, o + 4)
        need(off + size <= len(t) + 0x800, "texture file directory entry %d out of range" % cid)
        cells[cid] = (off, size)
        o += 12
    print("texture file: %d bytes, %d cells: %s" % (len(t), len(cells),
                                                    ", ".join(str(k) for k in sorted(cells))))
    nmesh = fails = uvfail = 0
    sizes = collections.Counter()
    for c in w.chunks:
        if chunk_kind(c) != "mesh" or c.cell == 0:
            continue
        nmesh += 1
        if c.cell not in cells:
            fails += 1
            continue
        off, _size = cells[c.cell]
        count, = struct.unpack_from("<I", t, off)
        if c.texoff % 0x40 or not 1 <= c.texoff // 0x40 <= count:
            fails += 1
            continue
        tw, th = struct.unpack_from("<HH", t, off + c.texoff)
        sizes[(tw, th)] += 1
        um = vm = 0
        for b in w.batches(c):
            for u, v in b.uvs or ():
                um, vm = max(um, u), max(vm, v)
        if um / 16.0 > tw + 1 or vm / 16.0 > th + 1:
            uvfail += 1
    print("  chunk (cell, offset) names a texture header in the file:  %d of %d"
          % (nmesh - fails, nmesh))
    print("  largest u/16, v/16 of the chunk fits the texture size:     %d of %d"
          % (nmesh - fails - uvfail, nmesh - fails))
    print("  most common texture sizes: " + ", ".join("%dx%d x%d" % (k[0], k[1], n)
                                                       for k, n in sizes.most_common(6)))
    return fails + uvfail


# ---- exports -------------------------------------------------------------
def write_pgm(path, width, height, pixels, maxval, comment):
    with open(path, "wb") as f:
        f.write(b"P5\n# %s\n%d %d\n%d\n" % (comment.encode("ascii"), width, height, maxval))
        if maxval > 255:
            f.write(struct.pack(">%dH" % len(pixels), *pixels))
        else:
            f.write(bytes(pixels))


def terrain_raster(w):
    """Rasterise all terrain samples at 4 units per pixel.

    Returns (x0, y0, width, height, heights, flags) where heights holds the highest
    ground height per pixel (None = no sample) and flags the OR of the sample flags."""
    need(w.elements, "this world has no terrain elements")
    x0 = min(e.minx for e in w.elements) // SAMPLE_STEP - 1
    y0 = min(e.miny for e in w.elements) // SAMPLE_STEP - 1
    x1 = max(e.maxx for e in w.elements) // SAMPLE_STEP + 2
    y1 = max(e.maxy for e in w.elements) // SAMPLE_STEP + 2
    width, height = x1 - x0, y1 - y0
    need(width * height <= 64000000, "terrain raster would be %dx%d pixels" % (width, height))
    heights = [None] * (width * height)
    flags = [0] * (width * height)
    for e in w.elements:
        hf = w.heightfields[e.hf]
        s = w.samples(hf)
        co, si = e.cos / 32767.0, e.sin / 32767.0
        mirror = e.flags & 1
        k = 0
        for j in range(hf.h):
            ly = (hf.y0 + j) * SAMPLE_STEP
            for i in range(hf.w):
                v = s[k]
                k += 1
                lx = (hf.x0 + i) * SAMPLE_STEP
                if mirror:
                    wx, wy = lx * co + ly * si + e.x, lx * si - ly * co + e.y
                else:
                    wx, wy = lx * co - ly * si + e.x, lx * si + ly * co + e.y
                px = int(round(wx / SAMPLE_STEP)) - x0
                py = int(round(wy / SAMPLE_STEP)) - y0
                if not (0 <= px < width and 0 <= py < height):
                    continue
                idx = py * width + px
                hgt = v >> 4
                flags[idx] |= (v & 15) | (0x10 if hgt <= NO_GROUND else 0x20)
                if hgt > NO_GROUND:
                    hgt += e.z
                    if heights[idx] is None or hgt > heights[idx]:
                        heights[idx] = hgt
    return x0, y0, width, height, heights, flags


def export_height(w, path, bits):
    x0, y0, width, height, heights, _flags = terrain_raster(w)
    real = [h for h in heights if h is not None]
    need(real, "this world has no ground samples")
    lo, hi = min(real), max(real)
    maxval = 65535 if bits == 16 else 255
    span = max(1, hi - lo)
    if bits == 16:
        pix = [0 if h is None else 1 + h - lo for h in heights]
        note = "pixel = 1 + height - %d" % lo
    else:
        pix = [0 if h is None else 1 + (h - lo) * 254 // span for h in heights]
        note = "pixel = 1 + (height - %d) * 254 / %d" % (lo, span)
    write_pgm(path, width, height, pix, maxval,
              "world x = (column + %d) * 4, y = (row + %d) * 4; 0 = no ground; %s"
              % (x0, y0, note))
    print("wrote %s: %dx%d, ground height %d..%d" % (path, width, height, lo, hi))


def export_flags(w, path):
    x0, y0, width, height, _heights, flags = terrain_raster(w)
    pix = []
    for f in flags:
        if f == 0:
            pix.append(0)
        elif f & 1 or not f & 0x20:
            pix.append(255)
        elif f & 2:
            pix.append(160)
        else:
            pix.append(80)
    write_pgm(path, width, height, pix, 255,
              "world x = (column + %d) * 4, y = (row + %d) * 4; 0 no sample, 80 open, "
              "160 flag 2, 255 flag 1 or no floor" % (x0, y0))
    print("wrote %s: %dx%d" % (path, width, height))


def export_path(w, path):
    cells = w.path_cells()
    need(cells, "this world has no path grid")
    pix = [31 * bin(v & 0xFF).count("1") for v in cells]
    write_pgm(path, w.pg_w, w.pg_h, pix, 255,
              "world x = (column + %d) * 24, y = (row + %d) * 24; pixel = 31 * links"
              % (w.pg_x0, w.pg_y0))
    print("wrote %s: %dx%d" % (path, w.pg_w, w.pg_h))


def export_obj(w, path):
    nv = nt = nf = 0
    with open(path, "w") as f:
        f.write("# world geometry decoded by world_info.py; z is up\n")
        f.write("# vt is in texels (u/16, v/16); divide by the texture size from the .TEX file\n")
        for c in w.chunks:
            if chunk_kind(c) != "mesh":
                continue
            a, b, cc, dd = w.chunk_matrix(c)
            f.write("g chunk%d_cell%d_tex%x\n" % (c.index, c.cell, c.texoff))
            for bt in w.batches(c):
                for x, y, z in w.chunk_world_vertices(c, bt):
                    f.write("v %.3f %.3f %.3f\n" % (x, y, z))
                for nx, ny, nz in bt.normals:
                    f.write("vn %.4f %.4f %.4f\n" % ((a * nx + b * ny) / 127.0,
                                                     (cc * nx + dd * ny) / 127.0, nz / 127.0))
                for u, v in bt.uvs or ():        # one vt per strip slot
                    f.write("vt %.4f %.4f\n" % (u / 16.0, v / 16.0))
                s = bt.strip
                for k in range(2, len(s)):
                    if s[k][1]:
                        continue
                    tri = (s[k - 2][0], s[k - 1][0], s[k][0])
                    if len(set(tri)) < 3:
                        continue
                    if bt.uvs:
                        f.write("f " + " ".join(
                            "%d/%d/%d" % (nv + 1 + tri[m], nt + 1 + k - 2 + m, nv + 1 + tri[m])
                            for m in range(3)) + "\n")
                    else:
                        f.write("f " + " ".join("%d//%d" % (nv + 1 + tri[m], nv + 1 + tri[m])
                                                for m in range(3)) + "\n")
                    nf += 1
                nv += len(bt.verts)
                nt += len(bt.uvs or ())
    print("wrote %s: %d vertices, %d triangles" % (path, nv, nf))


# ---- main ----------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Describe a Snowblind .world level file.")
    ap.add_argument("world")
    ap.add_argument("--chunks", action="store_true", help="list every chunk")
    ap.add_argument("--elements", action="store_true", help="list every terrain element")
    ap.add_argument("--refs", action="store_true", help="list texture cells, models, effects")
    ap.add_argument("--check", action="store_true", help="run the consistency checks")
    ap.add_argument("--tex", metavar="LEVEL.TEX", help="check texture references against the texture file")
    ap.add_argument("--height-pgm", metavar="OUT.pgm")
    ap.add_argument("--pgm-bits", type=int, choices=(8, 16), default=8)
    ap.add_argument("--flags-pgm", metavar="OUT.pgm")
    ap.add_argument("--path-pgm", metavar="OUT.pgm")
    ap.add_argument("--obj", metavar="OUT.obj")
    ap.add_argument("--quiet", action="store_true", help="skip the summary")
    args = ap.parse_args(argv)

    try:
        with open(args.world, "rb") as f:
            data = f.read()
    except OSError as e:
        print("world_info: %s" % e, file=sys.stderr)
        return 2
    status = 0
    try:
        w = World(data)
        if not args.quiet:
            summary(w, args.world)
        if args.chunks:
            list_chunks(w)
        if args.elements:
            list_elements(w)
        if args.refs:
            list_refs(w)
        if args.check:
            print("checks")
            if check(w):
                status = 1
        if args.tex:
            if check_tex(w, args.tex):
                status = 1
        if args.height_pgm:
            export_height(w, args.height_pgm, args.pgm_bits)
        if args.flags_pgm:
            export_flags(w, args.flags_pgm)
        if args.path_pgm:
            export_path(w, args.path_pgm)
        if args.obj:
            export_obj(w, args.obj)
    except FormatError as e:
        print("world_info: %s: %s" % (args.world, e), file=sys.stderr)
        return 2
    except struct.error as e:
        print("world_info: %s: bad world file: a table runs off the end of the file (%s)"
              % (args.world, e), file=sys.stderr)
        return 2
    return status


if __name__ == "__main__":
    sys.exit(main())
