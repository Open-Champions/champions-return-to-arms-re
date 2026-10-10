#!/usr/bin/env python3
"""Inspect Snowblind .vif models and .tex / .etex textures (Champions: Return to Arms layout).

  python3 model_info.py FILE.vif                      header, tables and per-mesh summary
  python3 model_info.py FILE.vif -v                   also one line per vertex packet
  python3 model_info.py FILE.vif --obj OUT.obj        export the meshes to Wavefront OBJ
        [--tex FILE.tex | --texsize WxH]              texture size used to normalise UVs
        [--meshes all|default|0,3,7]                  which meshes (default: not hidden by +0x08)
  python3 model_info.py FILE.tex                      header and upload packet summary
  python3 model_info.py FILE.tex --ppm OUT.ppm        colour as binary PPM
        [--pgm OUT.pgm]                               alpha as binary PGM
        [--full]                                      whole power-of-two surface, not w x h
        [--weave]                                     interleave the two fields of an interface picture

The file kind comes from the extension; --kind vif|tex overrides it. The script stops with
a message and exit status 2 on anything it does not understand; it never guesses.
Layouts are described in docs/formats/model-texture.md. Standard library only.

Alpha: the PGM holds the stored alpha with 0x80 written as 255. In model textures (flag
0x10) a stored alpha of 0 is opaque. Keep extracted files and exports outside the repository.
"""
import argparse, os, struct, sys


class FormatError(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise FormatError(msg)


def u8(d, o): return d[o]
def s8(d, o): return struct.unpack_from('<b', d, o)[0]
def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def u64(d, o): return struct.unpack_from('<Q', d, o)[0]


# ----------------------------------------------------------------------------------------
# GIF tags (used by both formats)
# ----------------------------------------------------------------------------------------

def giftag(d, o):
    need(o + 16 <= len(d), 'GIF tag at 0x%x runs past the end of the file' % o)
    lo, hi = struct.unpack_from('<QQ', d, o)
    return {
        'nloop': lo & 0x7fff, 'eop': (lo >> 15) & 1, 'pre': (lo >> 46) & 1,
        'prim': (lo >> 47) & 0x7ff, 'flg': (lo >> 58) & 3, 'nreg': (lo >> 60) & 15 or 16,
        'regs': hi,
    }


PRIM_BITS = ((3, 'IIP'), (4, 'TME'), (5, 'FGE'), (6, 'ABE'), (7, 'AA1'), (8, 'FST'), (9, 'CTXT'), (10, 'FIX'))
PRIM_TYPES = ('point', 'line', 'linestrip', 'triangle', 'tristrip', 'trifan', 'sprite', '?')


def prim_text(p):
    return PRIM_TYPES[p & 7] + ''.join('+' + n for b, n in PRIM_BITS if p >> b & 1)


# ----------------------------------------------------------------------------------------
# .vif models
# ----------------------------------------------------------------------------------------

VIF_NOP, VIF_STCYCL, VIF_ITOP, VIF_STMOD, VIF_MSCAL = 0x00, 0x01, 0x04, 0x05, 0x14
MESH_PROGRAMS = {0x42: 'one pass, 3 qwords per strip vertex',
                 0x44: 'two passes, 4 qwords per strip vertex',
                 0x46: 'one pass, no weights, positions unpacked with STMOD 1'}
MODEL_FLAGS = ((0x01, 'bit0'), (0x02, 'variants'), (0x04, 'attach'), (0x08, 'late-layer'),
               (0x10, 'second-pass'), (0x20, 'shell-normals'), (0x40, 'facing-points'))


class Chunk:
    """One vertex packet: the data between an ITOP and its MSCAL, plus the UV list that follows."""
    def __init__(self, off):
        self.off = off
        self.n = None
        self.pos = self.nrm = self.vloc = self.weights = self.extra = self.tags = None
        self.shell = None
        self.uv = None
        self.uv_stride = None
        self.program = None
        self.stmod = 0


def vif_code(d, o):
    w = u32(d, o)
    return w & 0xffff, (w >> 16) & 0xff, (w >> 24) & 0x7f, w >> 31


def unpack_items(d, o, cmd, num, imm):
    """Decode one VIF UNPACK. Returns (items, bytes consumed, address, uses TOPS, unsigned)."""
    vn, vl = (cmd >> 2) & 3, cmd & 3
    need(vl != 3, 'UNPACK V4-5 at 0x%x is not used by this format' % o)
    need(not cmd & 0x10, 'masked UNPACK at 0x%x is not used by this format' % o)
    comps, width = vn + 1, 4 >> vl
    count = num or 256
    size = comps * width * count
    need(o + 4 + size <= len(d), 'UNPACK at 0x%x runs past the end of the file' % o)
    unsigned = bool(imm & 0x4000)
    ch = {4: 'i', 2: 'h', 1: 'b'}[width]
    vals = struct.unpack_from('<%d%s' % (comps * count, ch.upper() if unsigned else ch), d, o + 4)
    items = [vals[i * comps:(i + 1) * comps] for i in range(count)]
    return items, 4 + ((size + 3) & ~3), imm & 0x3ff, bool(imm & 0x8000), unsigned


def parse_mesh_stream(d, start, end):
    """Walk the VIF1 stream of one mesh and return its list of chunks."""
    need(start % 16 == 0 and end % 16 == 0, 'mesh range 0x%x..0x%x is not qword aligned' % (start, end))
    chunks = []
    cur = None          # chunk being filled (after ITOP, before MSCAL)
    last = None         # last finished chunk, waiting for its UV list
    cl = wl = 1
    stmod = 0
    o = start
    while o < end:
        imm, num, cmd, irq = vif_code(d, o)
        need(not irq, 'VIF code with the interrupt bit at 0x%x' % o)
        if cmd == VIF_NOP:
            o += 4
        elif cmd == VIF_STCYCL:
            cl, wl = imm & 0xff, imm >> 8
            need(wl == 1 and cl in (1, 3, 4), 'unexpected STCYCL cl=%d wl=%d at 0x%x' % (cl, wl, o))
            o += 4
        elif cmd == VIF_STMOD:
            stmod = imm & 3
            need(stmod in (0, 1), 'unexpected STMOD %d at 0x%x' % (stmod, o))
            o += 4
        elif cmd == VIF_ITOP:
            need(cur is None, 'ITOP at 0x%x inside an unfinished packet' % o)
            need(0 < imm <= 0x7f, 'vertex count %d at 0x%x is out of range' % (imm, o))
            cur = Chunk(o)
            cur.n = imm
            o += 4
        elif cmd == VIF_MSCAL:
            need(cur is not None, 'MSCAL at 0x%x without a packet' % o)
            need(imm in MESH_PROGRAMS, 'MSCAL 0x%x at 0x%x is not a known mesh program' % (imm, o))
            cur.program = imm
            finish_chunk(cur)
            chunks.append(cur)
            last, cur = cur, None
            o += 4
        elif cmd & 0x60 == 0x60:
            items, used, addr, tops, unsigned = unpack_items(d, o, cmd, num, imm)
            need(tops, 'UNPACK at 0x%x is not relative to TOPS' % o)
            kind = (cmd >> 2 & 3, cmd & 3)        # (vn, vl): (2,1)=V3-16 (2,2)=V3-8 (3,2)=V4-8 ...
            if kind == (1, 1):                    # V2-16: texture coordinates of the previous packet
                need(cur is None and last is not None and last.uv is None,
                     'UV list at 0x%x does not follow a finished packet' % o)
                need(unsigned and addr == 0x81 and cl in (3, 4), 'unexpected UV unpack at 0x%x' % o)
                last.uv, last.uv_stride = items, cl
            else:
                need(cur is not None, 'UNPACK at 0x%x outside a packet' % o)
                need(cl == 1, 'vertex data at 0x%x unpacked with STCYCL cl=%d' % (o, cl))
                place_unpack(cur, kind, items, addr, unsigned, stmod, o)
            o += used
        else:
            raise FormatError('VIF command 0x%02x at 0x%x is not used by this format' % (cmd, o))
    need(o == end, 'mesh stream overruns its range (0x%x, expected 0x%x)' % (o, end))
    need(cur is None, 'mesh stream ends inside a packet')
    for c in chunks:
        need(c.uv is not None, 'packet at 0x%x has no UV list' % c.off)
        need(len(c.uv) == c.tags[0]['nloop'], 'packet at 0x%x: %d UVs for a strip of %d'
             % (c.off, len(c.uv), c.tags[0]['nloop']))
        need(c.uv_stride == c.tags[0]['nreg'], 'packet at 0x%x: UV stride %d, %d registers per vertex'
             % (c.off, c.uv_stride, c.tags[0]['nreg']))
    return chunks


def place_unpack(c, kind, items, addr, unsigned, stmod, o):
    n = c.n
    if kind == (2, 1) and not unsigned and addr == 0:
        need(c.pos is None and len(items) == n, 'bad position block at 0x%x' % o)
        c.pos, c.stmod = items, stmod
    elif kind == (2, 2) and not unsigned and addr == n:
        need(c.nrm is None and len(items) == n, 'bad normal block at 0x%x' % o)
        c.nrm = items
    elif kind == (2, 1) and unsigned and addr == 2 * n:
        need(c.vloc is None and len(items) == n + 2, 'bad strip-slot block at 0x%x' % o)
        c.vloc = items
    elif kind == (3, 2) and unsigned and addr == 3 * n + 2:
        need(c.weights is None, 'second weight block at 0x%x' % o)
        c.weights = items
    elif kind == (3, 1) and unsigned:
        need(c.extra is None and addr == 3 * n + 2 + len(c.weights or ()), 'bad copy block at 0x%x' % o)
        c.extra = items
    elif kind == (3, 0):
        need(c.tags is None and c.extra is not None and len(items) in (1, 2)
             and addr == 3 * n + 2 + len(c.weights or ()) + len(c.extra), 'bad GIF tag block at 0x%x' % o)
        c.tags = [giftag(struct.pack('<4I', *[v & 0xffffffff for v in it]), 0) for it in items]
        c.tag_addr = addr
    elif kind == (2, 2) and not unsigned and c.tags is not None:
        need(c.shell is None and len(items) == n and addr == c.tag_addr + len(c.tags),
             'bad shell-normal block at 0x%x' % o)
        c.shell = items
    else:
        raise FormatError('unexpected UNPACK (vn=%d vl=%d addr=0x%x) at 0x%x' % (kind[0], kind[1], addr, o))


def finish_chunk(c):
    where = 'packet at 0x%x' % c.off
    for name in ('pos', 'nrm', 'vloc', 'extra', 'tags'):
        need(getattr(c, name) is not None, '%s has no %s block' % (where, name))
    if c.program == 0x46:
        need(c.weights is None, '%s: program 0x46 with weights' % where)
    else:
        need(c.weights is not None, '%s has no weight block' % where)
    need(len(c.tags) == (2 if c.program == 0x44 else 1), '%s: %d GIF tags for program 0x%x'
         % (where, len(c.tags), c.program))
    t = c.tags[0]
    need(t['flg'] == 0 and t['pre'] == 1 and t['eop'] == 1 and (t['prim'] & 7) == 4,
         '%s: GIF tag is not a packed triangle strip' % where)
    need((t['nreg'], t['regs'] & 0xffff) in ((3, 0x413), (4, 0x41f3)), '%s: unexpected register list %x' % (where, t['regs']))
    if len(c.tags) == 2:
        need(c.tags[1]['nloop'] == t['nloop'] and c.tags[1]['regs'] & 0xffff == 0x413f,
             '%s: second GIF tag does not match the first' % where)
    need(c.extra[0][0] == len(c.extra) - 1, '%s: copy block count %d, %d entries'
         % (where, c.extra[0][0], len(c.extra) - 1))
    if c.shell is not None:
        need(c.vloc[0][1] == c.tag_addr + len(c.tags), '%s: shell-normal address is not in the first slot entry' % where)
    c.vertex_bones = decode_weights(c, where)
    c.strip = build_strip(c)
    for i, slot in enumerate(c.strip):
        need(slot is not None, '%s: strip position %d is never given a vertex' % (where, i))


def decode_weights(c, where):
    """Per vertex: list of (joint, weight/255). Program 0x46 has none."""
    if c.weights is None:
        return [[] for _ in range(c.n)]
    out, i, w = [], 0, c.weights
    while len(out) < c.n:
        need(i < len(w), '%s: weight list covers %d of %d vertices' % (where, len(out), c.n))
        b1, w1, b2, w2 = w[i]
        i += 1
        need(b1 % 4 == 0, '%s: joint byte %d is not a multiple of 4' % (where, b1))
        if b2 == 0xff:                       # run of w2 vertices rigidly bound to b1
            need(w2 > 0, '%s: empty weight run' % where)
            out.extend([[(b1 // 4, 1.0)]] * min(w2, c.n - len(out)))
            continue
        need(b2 % 4 == 0, '%s: joint byte %d is not a multiple of 4' % (where, b2))
        bones = [(b1 // 4, w1 / 255.0), (b2 // 4, w2 / 255.0)]
        if w1 + w2 != 255:                   # a second entry carries joints 3 and 4
            need(i < len(w), '%s: weight list ends inside a 3/4-joint vertex' % where)
            b3, w3, b4, w4 = w[i]
            i += 1
            need(b3 % 4 == 0, '%s: joint byte %d is not a multiple of 4' % (where, b3))
            bones.append((b3 // 4, w3 / 255.0))
            if b4 != 0xff:
                need(b4 % 4 == 0, '%s: joint byte %d is not a multiple of 4' % (where, b4))
                bones.append((b4 // 4, w4 / 255.0))
        out.append(bones)
    need(len(w) - i <= 1, '%s: %d weight entries left over' % (where, len(w) - i))
    c.weight_entries_used = i
    return out


def build_strip(c):
    """Replay the output-buffer writes of the vertex program, one qword at a time.

    A strip vertex is nreg qwords: [UV][pass-2 UV, 4-register packets only][RGBA][XYZ + no-draw bit].
    The UV qword comes from the VIF stream; the program writes the others at the addresses in the
    slot rows. A cell is (qword kind, vertex index, no-draw flag); kind 2 is the XYZ qword.
    Returns one entry per strip vertex: (vertex index, no-draw flag), or None if its XYZ qword
    never received a vertex.
    """
    nreg, nloop = c.tags[0]['nreg'], c.tags[0]['nloop']
    kinds = (0, 1, 2) if nreg == 4 else (1, 2)       # qwords written, relative to a slot address
    copy_first = (0,) if nreg == 4 else (1, 2)       # qwords where the copy lands before the vertex
    mem = {}

    def retag(cell, k, flag):                        # the no-draw bit comes from the address written to
        return (2, cell[1], flag) if k == 2 and cell is not None and cell[0] == 2 else cell

    for j, (x, y, z) in enumerate(c.vloc):
        xa, ya, za = x & 0x7fff, y & 0x7fff, z & 0x7fff
        xf, zf = bool(x & 0x8000), bool(z & 0x8000)
        src = {k: mem.get(ya + k) for k in kinds}    # the copy source is read before anything is stored
        for k in kinds:
            vert = (k, j - 2, xf) if j >= 2 else None    # rows 0 and 1 store nothing meaningful
            if k in copy_first:
                mem[za + k] = retag(src[k], k, zf)
                mem[xa + k] = vert
            else:
                mem[xa + k] = vert
                mem[za + k] = retag(src[k], k, zf)
    for s1, d1, s2, d2 in c.extra[1:]:
        one = {k: mem.get((s1 & 0x7fff) + k) for k in kinds}
        two = {k: mem.get((s2 & 0x7fff) + k) for k in kinds}
        for k in kinds:
            mem[(d2 & 0x7fff) + k] = retag(two[k], k, bool(d2 & 0x8000))
            mem[(d1 & 0x7fff) + k] = retag(one[k], k, bool(d1 & 0x8000))
    slots = []
    for i in range(nloop):
        cell = mem.get(i * nreg + nreg - 1)
        slots.append((cell[1], cell[2]) if cell is not None and cell[0] == 2 else None)
    return slots


def chunk_triangles(c):
    """Return (triangles, stitches). A triangle is ((vertex, strip position) x 3); the strip position
    indexes the UV list. Stitches are the drawn strip triangles that repeat a vertex; they are dropped.

    The strip order carries no usable winding (see the format document), so each triangle is turned
    to face the way its vertex normals point.
    """
    tris, stitches = [], 0
    s = c.strip
    for i in range(2, len(s)):
        if s[i][1]:
            continue
        a, b, e = (s[i - 2][0], i - 2), (s[i - 1][0], i - 1), (s[i][0], i)
        if len({a[0], b[0], e[0]}) < 3:
            stitches += 1
            continue
        pa, pb, pe = c.pos[a[0]], c.pos[b[0]], c.pos[e[0]]
        u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        v = (pe[0] - pa[0], pe[1] - pa[1], pe[2] - pa[2])
        face = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        na, nb, ne = c.nrm[a[0]], c.nrm[b[0]], c.nrm[e[0]]
        dot = sum(face[k] * (na[k] + nb[k] + ne[k]) for k in range(3))
        tris.append((a, b, e) if dot >= 0 else (b, a, e))
    return tris, stitches


class Model:
    pass


def parse_model(d):
    need(len(d) >= 0x40 and len(d) % 16 == 0, 'file is too small or not a multiple of 16 bytes')
    m = Model()
    m.size = len(d)
    m.part_mask, m.hidden_mask = u64(d, 0), u64(d, 8)
    m.flags = u16(d, 0x10)
    m.mesh_count, m.attach_index = s8(d, 0x12), s8(d, 0x13)
    m.alpha1 = u64(d, 0x18)
    m.fix2 = u8(d, 0x20)
    m.tab = {name: u8(d, o) * 16 for name, o in
             (('variants', 0x21), ('attach', 0x22), ('facing', 0x23), ('samples', 0x24), ('hull', 0x25), ('segment', 0x27))}
    m.lod_count = max(1, s8(d, 0x26))
    need(u32(d, 0x14) == 0, 'header +0x14 is not zero; not a model of this layout')
    need(1 <= m.mesh_count <= 64, 'mesh count %d is out of range' % m.mesh_count)
    need(m.flags & ~0x7f == 0, 'unknown flag bits 0x%x' % m.flags)
    n = m.mesh_count
    tab_end = 0x28 + m.lod_count * (n + 1) * 4
    need(tab_end + n * 10 <= len(d), 'mesh table runs past the end of the file')
    m.offsets = [list(struct.unpack_from('<%dI' % (n + 1), d, 0x28 + l * (n + 1) * 4)) for l in range(m.lod_count)]
    for offs in m.offsets:
        need(all(a <= b for a, b in zip(offs, offs[1:])) and offs[-1] <= len(d) and offs[0] >= tab_end + n * 10,
             'mesh offsets are not ascending inside the file')
        need(all(o % 16 == 0 for o in offs), 'mesh offsets are not qword aligned')
    m.mesh_info = []
    for i in range(n):
        o = tab_end + i * 10
        m.mesh_info.append({'bbox': struct.unpack_from('<6b', d, o), 'joint': u8(d, o + 6),
                            'b7': u8(d, o + 7), 'w8': u16(d, o + 8)})
    first_mesh = min(offs[0] for offs in m.offsets)
    starts = sorted([v for v in m.tab.values() if v] + [first_mesh])
    for name, off in m.tab.items():
        need(off == 0 or tab_end + n * 10 <= off < first_mesh, '%s table offset 0x%x is outside the header area' % (name, off))

    def extent(off):
        return starts[starts.index(off) + 1] - off

    for bit, name in ((0x02, 'variants'), (0x04, 'attach'), (0x40, 'facing')):
        need(bool(m.flags & bit) == bool(m.tab[name]), 'flag 0x%02x and the %s table disagree' % (bit, name))
    m.variants = []
    if m.tab['variants']:
        o = m.tab['variants']
        m.variants = [struct.unpack_from('<QQ', d, o + i * 16) for i in range(min(32, extent(o) // 16))]
    m.attach = []
    if m.tab['attach']:
        o = m.tab['attach']
        for i in range(extent(o) // 0x34):
            m.attach.append((struct.unpack_from('<i', d, o + i * 0x34)[0], struct.unpack_from('<12f', d, o + i * 0x34 + 4)))
    m.hull = []
    if m.tab['hull']:
        o = m.tab['hull']
        need(o + n * 24 <= first_mesh, 'hull table runs into the mesh data')
        m.hull = [[struct.unpack_from('<3b', d, o + i * 24 + k * 3) for k in range(8)] for i in range(n)]
    m.segment = struct.unpack_from('<6f', d, m.tab['segment']) if m.tab['segment'] else None
    m.samples = parse_samples(d, m.tab['samples']) if m.tab['samples'] else []
    m.meshes = [[parse_mesh_stream(d, offs[i], offs[i + 1]) for i in range(n)] for offs in m.offsets]
    return m


def parse_samples(d, o):
    """Sample points: an 0x20-byte header, then 8-byte records with a 16-byte gap after every 45."""
    count = u32(d, o + 4)
    need(count < 0x4000, 'sample point count %d is out of range' % count)
    out = []
    for i in range(count):
        p = o + 0x20 + i * 8 + (i // 45) * 0x10
        need(p + 8 <= len(d), 'sample points run past the end of the file')
        x, y, z, w = struct.unpack_from('<4h', d, p)
        out.append((x / 16.0, y / 16.0, z / 16.0, (w & 0xff) >> 2, w))
    return out


def describe_model(m, verbose, out):
    p = lambda s='': print(s, file=out)
    names = [n for b, n in MODEL_FLAGS if m.flags & b]
    p('model: %d bytes, %d mesh(es), %d mesh table(s)' % (m.size, m.mesh_count, m.lod_count))
    p('  +0x00 mask of parent meshes this part replaces  0x%016x' % m.part_mask)
    p('  +0x08 meshes hidden by default                  0x%016x' % m.hidden_mask)
    p('  +0x10 flags 0x%04x (%s)' % (m.flags, ', '.join(names) or 'none'))
    p('  +0x13 attach slot on the parent                 %d' % m.attach_index)
    p('  +0x18 GS ALPHA_1 value 0x%x   +0x20 pass-2 FIX alpha 0x%02x' % (m.alpha1, m.fix2))
    p('  tables: ' + ', '.join('%s@0x%x' % (k, v) for k, v in m.tab.items() if v))
    if m.variants:
        used = [(i, s, h) for i, (s, h) in enumerate(m.variants) if s or h]
        p('  variants: %d record(s), %d non-empty' % (len(m.variants), len(used)))
        if verbose:
            for i, s, h in used:
                p('    bit %2d  show 0x%016x  hide 0x%016x' % (i, s, h))
    if m.attach:
        p('  attach points: %d record(s)' % len(m.attach))
        if verbose:
            for i, (joint, mat) in enumerate(m.attach):
                p('    %2d joint %3d  origin (%.2f, %.2f, %.2f)' % (i, joint, mat[9], mat[10], mat[11]))
    if m.segment:
        p('  effect segment: (%.2f, %.2f, %.2f) to (%.2f, %.2f, %.2f)' % m.segment)
    if m.samples:
        joints = sorted({s[3] for s in m.samples})
        p('  sample points: %d, joints %d..%d' % (len(m.samples), joints[0], joints[-1]))
    for lod, meshes in enumerate(m.meshes):
        tv = tt = 0
        for i, chunks in enumerate(meshes):
            info = m.mesh_info[i]
            nv = sum(c.n for c in chunks)
            tris = 0
            for c in chunks:
                tris += len(chunk_triangles(c)[0])
            tv += nv
            tt += tris
            joints = sorted({b for c in chunks for vb in c.vertex_bones for b, _ in vb})
            progs = '/'.join('%x' % x for x in sorted({c.program for c in chunks}))
            hidden = 'hidden' if m.hidden_mask >> i & 1 else 'shown'
            p('  mesh %2d [%s] 0x%06x..0x%06x  %3d packet(s) %5d verts %5d tris  prog %s  joints %s  bbox %s  joint %d  header tris %d'
              % (i, hidden, m.offsets[lod][i], m.offsets[lod][i + 1], len(chunks), nv, tris, progs,
                 ('%d..%d' % (joints[0], joints[-1])) if joints else '-', info['bbox'], info['joint'], info['w8']))
            if verbose:
                for c in chunks:
                    t = c.tags[0]
                    p('      0x%06x n=%3d strip=%3d prog=%x %s weights=%d copies=%d%s%s'
                      % (c.off, c.n, t['nloop'], c.program, prim_text(t['prim']), len(c.weights or ()),
                         len(c.extra) - 1, ' shell' if c.shell else '', ' stmod' if c.stmod else ''))
        p('  table %d total: %d vertices, %d triangles' % (lod, tv, tt))


def export_obj(m, path, which, tex_wh, name):
    meshes = m.meshes[0]
    if which == 'all':
        sel = list(range(m.mesh_count))
    elif which == 'default':
        sel = [i for i in range(m.mesh_count) if not m.hidden_mask >> i & 1]
    else:
        need(all(x.isdigit() for x in which.split(',')), '--meshes wants all, default or a list such as 0,3,7')
        sel = [int(x) for x in which.split(',')]
        need(all(i < m.mesh_count for i in sel), 'mesh index out of range')
    tw, th = tex_wh or (256.0, 256.0)
    lines = ['# %s exported by model_info.py; positions are file units / 16; faces turned to match the normals' % name]
    if not tex_wh:
        lines.append('# no texture size given: UVs are texels / 256')
    nv = nt = 1
    for i in sel:
        lines.append('g mesh_%02d' % i)
        for c in meshes[i]:
            tris, _ = chunk_triangles(c)
            if not tris:
                continue
            for (x, y, z), (a, b, e) in zip(c.pos, c.nrm):
                lines.append('v %.4f %.4f %.4f' % (x / 16.0, y / 16.0, z / 16.0))
                lines.append('vn %.4f %.4f %.4f' % (a / 127.0, b / 127.0, e / 127.0))
            for u, v in c.uv:
                lines.append('vt %.5f %.5f' % (u / 16.0 / tw, 1.0 - v / 16.0 / th))
            for tri in tris:
                lines.append('f ' + ' '.join('%d/%d/%d' % (nv + vi, nt + si, nv + vi) for vi, si in tri))
            nv += c.n
            nt += len(c.uv)
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return nv - 1, sel


# ----------------------------------------------------------------------------------------
# .tex / .etex textures
# ----------------------------------------------------------------------------------------

GS_BITBLTBUF, GS_TRXPOS, GS_TRXREG, GS_TRXDIR, GS_LABEL = 0x50, 0x51, 0x52, 0x53, 0x62
PSM_NAMES = {0x00: 'PSMCT32', 0x02: 'PSMCT16', 0x13: 'PSMT8', 0x14: 'PSMT4'}
TEX_FLAGS = ((0x0004, '8-bit'), (0x2000, '4-bit'), (0x0020, '32-bit'), (0x0080, 'no-pixels'))


class Texture:
    pass


def parse_texture(d):
    need(len(d) >= 0x90, 'file is too small for a texture header')
    t = Texture()
    t.size = len(d)
    t.w, t.h, t.pages, t.qwc, t.flags, t.rt_magic = struct.unpack_from('<6H', d, 0)
    t.tex0, t.data_off = struct.unpack_from('<II', d, 0x0c)
    need(t.data_off == 0x80, 'pixel packet offset is 0x%x, expected 0x80 (not a lump texture)' % t.data_off)
    need(not any(d[0x14:0x80]), 'header bytes 0x14..0x7f are not zero (runtime fields); not a lump texture')
    need(t.flags & 0x101 == 0, 'flag bits 0x001/0x100 (streamed world texture) are not handled')
    need(t.w <= 1024 and t.h <= 1024 and bool(t.w) == bool(t.h), 'size %dx%d is out of range' % (t.w, t.h))
    need(0x80 + t.qwc * 16 <= len(d), 'packet of %d qwords does not fit in the file' % t.qwc)
    t.tbw, t.psm = t.tex0 & 0x3f, (t.tex0 >> 6) & 0x3f
    t.tw, t.th = 1 << ((t.tex0 >> 12) & 15), 1 << ((t.tex0 >> 16) & 15)
    t.tcc, t.tfx = (t.tex0 >> 20) & 1, (t.tex0 >> 21) & 3
    need(t.tex0 >> 23 == 0, 'unexpected high bits in the TEX0 fragment 0x%x' % t.tex0)
    need(t.psm in PSM_NAMES, 'pixel format 0x%x is not handled' % t.psm)
    need(t.w <= t.tw and t.h <= t.th, 'size %dx%d exceeds the surface %dx%d' % (t.w, t.h, t.tw, t.th))
    kinds = [n for b, n in TEX_FLAGS if t.flags & b]
    need(len(kinds) == 1, 'flags 0x%04x name %d storage kinds' % (t.flags, len(kinds)))
    t.kind = kinds[0]
    need({'8-bit': 0x13, '4-bit': 0x14, '32-bit': 0x00, 'no-pixels': 0x02}[t.kind] == t.psm,
         'flags 0x%04x do not match pixel format %s' % (t.flags, PSM_NAMES[t.psm]))
    t.transfers = walk_upload(d, 0x80, 0x80 + t.qwc * 16)
    return t


def walk_upload(d, o, end):
    """Return the image transfers of the GS upload packet: dicts with buffer index, format, rectangle, data."""
    out = []
    buf = -1
    st = {'dbw': 0, 'dpsm': 0, 'dsax': 0, 'dsay': 0, 'rrw': 0, 'rrh': 0}
    while o < end:
        tag = giftag(d, o)
        o += 16
        if tag['flg'] == 0:
            need(tag['nreg'] == 1 and tag['regs'] & 0xf == 0xe and not tag['pre'],
                 'GIF tag at 0x%x is not a register list' % (o - 16))
            for _ in range(tag['nloop']):
                need(o + 16 <= end, 'register list runs past the packet')
                val, reg = u64(d, o), u8(d, o + 8)
                if reg == GS_BITBLTBUF:
                    buf += 1
                    st['dbw'], st['dpsm'] = (val >> 48) & 0x3f, (val >> 56) & 0x3f
                    need(val & 0xffffffff == 0 and (val >> 32) & 0x3fff == 0, 'BITBLTBUF at 0x%x has a base pointer' % o)
                elif reg == GS_TRXPOS:
                    st['dsax'], st['dsay'] = (val >> 32) & 0x7ff, (val >> 48) & 0x7ff
                    need(val & 0xffffffff == 0 and val >> 59 == 0, 'TRXPOS at 0x%x has a source or direction' % o)
                elif reg == GS_TRXREG:
                    st['rrw'], st['rrh'] = val & 0xfff, (val >> 32) & 0xfff
                elif reg == GS_TRXDIR:
                    need(val & 3 == 0, 'TRXDIR at 0x%x is not host to local' % o)
                elif reg == GS_LABEL:
                    pass                     # padding
                else:
                    raise FormatError('GS register 0x%02x at 0x%x is not used by this format' % (reg, o))
                o += 16
        elif tag['flg'] == 2:
            n = tag['nloop'] * 16
            need(buf >= 0 and o + n <= end, 'image data at 0x%x has no destination or runs past the packet' % o)
            bpp = {0x00: 32, 0x14: 4}.get(st['dpsm'])
            need(bpp, 'upload format 0x%x at 0x%x is not handled' % (st['dpsm'], o))
            want = (st['rrw'] * st['rrh'] * bpp + 7) // 8
            need(want <= n < want + 16, 'image data at 0x%x: %d bytes for a %dx%d rectangle' % (o, n, st['rrw'], st['rrh']))
            out.append(dict(st, buf=buf, off=o, data=d[o:o + want]))
            o += n
        else:
            raise FormatError('GIF tag at 0x%x uses REGLIST mode' % (o - 16))
    need(o == end, 'upload packet overruns its size')
    return out


def clut_order(i):
    """Position of palette entry i in the 16x16 block as stored (GS CSM1 order)."""
    return (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)


# GS local memory layout. A page is 8192 bytes; it holds 64x32 32-bit pixels, 128x64 8-bit texels or
# 128x128 4-bit texels, cut into 32 blocks of 256 bytes, each block into 4 columns of 64 bytes.
_BLOCK_8x4 = ((0, 1, 4, 5, 16, 17, 20, 21), (2, 3, 6, 7, 18, 19, 22, 23),
              (8, 9, 12, 13, 24, 25, 28, 29), (10, 11, 14, 15, 26, 27, 30, 31))      # 32-bit and 8-bit
_BLOCK_4x8 = ((0, 2, 8, 10), (1, 3, 9, 11), (4, 6, 12, 14), (5, 7, 13, 15),
              (16, 18, 24, 26), (17, 19, 25, 27), (20, 22, 28, 30), (21, 23, 29, 31))  # 4-bit
_WORD = (0, 1, 4, 5, 8, 9, 12, 13)


def gs_addr32(x, y, bw):
    """Byte address of 32-bit pixel (x, y) in a buffer bw pages (64 pixels each) wide."""
    page = (y >> 5) * bw + (x >> 6)
    block = _BLOCK_8x4[(y >> 3) & 3][(x >> 3) & 7]
    word = ((y & 7) >> 1) * 16 + (y & 1) * 2 + _WORD[x & 7]
    return (page * 2048 + block * 64 + word) * 4


def _column_word(x, yy):
    r = yy & 3
    xi = (x & 7) ^ (4 if ((yy + 2) >> 2) & 1 else 0)
    return (yy >> 2) * 16 + (r & 1) * 2 + _WORD[xi], r >> 1


def gs_addr8(x, y, bw):
    """Byte address of 8-bit texel (x, y) in a buffer bw pages (128 texels each) wide."""
    page = (y >> 6) * bw + (x >> 7)
    block = _BLOCK_8x4[(y >> 4) & 3][(x >> 4) & 7]
    word, odd = _column_word(x, y & 15)
    return page * 8192 + block * 256 + word * 4 + odd + (((x >> 3) & 1) << 1)


def gs_addr4(x, y, bw):
    """Nibble address of 4-bit texel (x, y) in a buffer bw pages (128 texels each) wide."""
    page = (y >> 7) * bw + (x >> 7)
    block = _BLOCK_4x8[(y >> 4) & 7][(x >> 5) & 3]
    word, odd = _column_word(x, y & 15)
    return (page * 8192 + block * 256 + word * 4) * 2 + odd + (((x >> 3) & 3) << 1)


def decode_texture(t, full=False):
    """Return (width, height, [(r, g, b, a)] row major). Alpha is scaled so that 0x80 becomes 255."""
    need(t.kind != 'no-pixels', 'this texture has no stored pixels (it names a blank surface)')
    need(t.w and t.h, 'this texture is empty (0x0): it stores a palette and no image')
    w, h = (t.tw, t.th) if full else (t.w, t.h)
    tr = t.transfers

    def rgba(b, o):
        return b[o], b[o + 1], b[o + 2], min(255, b[o + 3] * 255 // 128)

    if t.kind == '32-bit':
        need(tr and all(r['buf'] == 0 and r['dpsm'] == 0 for r in tr), '32-bit texture is not uploaded to one 32-bit buffer')
        px = [(0, 0, 0, 0)] * (w * h)
        for r in tr:
            for yy in range(r['rrh']):
                for xx in range(r['rrw']):
                    X, Y = r['dsax'] + xx, r['dsay'] + yy
                    if X < w and Y < h:
                        px[Y * w + X] = rgba(r['data'], (yy * r['rrw'] + xx) * 4)
        return w, h, px
    pal = [r for r in tr if r['buf'] == 0]
    img = [r for r in tr if r['buf'] == 1]
    need(len(pal) == 1 and img and len(pal) + len(img) == len(tr), 'paletted texture without a palette and an image buffer')
    pd = pal[0]['data']
    if t.kind == '8-bit':
        need((pal[0]['rrw'], pal[0]['rrh'], pal[0]['dpsm']) == (16, 16, 0), 'palette is not 16x16 32-bit')
        colours = [rgba(pd, clut_order(i) * 4) for i in range(256)]
    else:
        need((pal[0]['rrw'], pal[0]['rrh'], pal[0]['dpsm']) == (8, 2, 0), 'palette is not 8x2 32-bit')
        colours = [rgba(pd, i * 4) for i in range(16)]
    if all(r['dpsm'] == 0 for r in img):
        # the image was sent as 32-bit pixels; the GS then reads the same memory as 8-bit or 4-bit texels
        bw = img[0]['dbw']
        need(bw * 2 == t.tbw, 'upload buffer width %d does not match TBW %d' % (bw, t.tbw))
        mem = {}
        for r in img:
            need(r['dsax'] + r['rrw'] <= bw * 64, 'rectangle does not fit the upload buffer')
            data, rw = r['data'], r['rrw']
            for yy in range(r['rrh']):
                for xx in range(rw):
                    mem[gs_addr32(r['dsax'] + xx, r['dsay'] + yy, bw) >> 2] = (yy * rw + xx) * 4, data
        px = []
        if t.kind == '8-bit':
            for y in range(h):
                for x in range(w):
                    a = gs_addr8(x, y, bw)
                    cell = mem.get(a >> 2)
                    px.append(colours[cell[1][cell[0] + (a & 3)]] if cell else colours[0])
        else:
            for y in range(h):
                for x in range(w):
                    a = gs_addr4(x, y, bw)
                    cell = mem.get(a >> 3)
                    px.append(colours[(cell[1][cell[0] + ((a >> 1) & 3)] >> (4 * (a & 1))) & 15] if cell else colours[0])
        return w, h, px
    need(t.kind == '4-bit' and len(img) == 1 and img[0]['dpsm'] == 0x14 and (img[0]['dsax'], img[0]['dsay']) == (0, 0),
         'image upload is neither 32-bit rectangles nor one direct 4-bit rectangle')
    r = img[0]
    px = []
    for y in range(h):
        for x in range(w):
            if x < r['rrw'] and y < r['rrh']:
                i = y * r['rrw'] + x
                px.append(colours[(r['data'][i >> 1] >> (4 * (i & 1))) & 15])
            else:
                px.append(colours[0])
    return w, h, px


def describe_texture(t, verbose, out):
    p = lambda s='': print(s, file=out)
    if not t.w:
        p('texture: %d bytes, empty (0x0): palette only' % t.size)
    else:
        p('texture: %d bytes, %dx%d used of a %dx%d %s surface' % (t.size, t.w, t.h, t.tw, t.th, PSM_NAMES[t.psm]))
    p('  +0x04 GS blocks reserved %d   +0x06 upload packet %d qwords (%d bytes after the 0x80 header)'
      % (t.pages, t.qwc, t.qwc * 16))
    other = t.flags & ~0x20a4
    p('  +0x08 flags 0x%04x (%s%s%s)' % (t.flags, t.kind, '; 0x10 model texture, alpha 0 is opaque' if t.flags & 0x10 else '',
                                      '; other bits 0x%04x' % (other & ~0x10) if other & ~0x10 else ''))
    p('  +0x0c TEX0 fragment 0x%06x: buffer width %d, %s, %dx%d, TCC %d, TFX %d'
      % (t.tex0, t.tbw * 64, PSM_NAMES[t.psm], t.tw, t.th, t.tcc, t.tfx))
    for r in t.transfers:
        p('  transfer at 0x%06x to buffer %d (%s): %3dx%-3d at (%d, %d), buffer width %d, sent as %s, %d bytes'
          % (r['off'], r['buf'], 'palette' if r['buf'] == 0 and t.kind in ('8-bit', '4-bit') else 'image',
             r['rrw'], r['rrh'], r['dsax'], r['dsay'], r['dbw'] * 64, PSM_NAMES.get(r['dpsm'], hex(r['dpsm'])), len(r['data'])))
    if t.size > 0x80 + t.qwc * 16:
        p('  %d bytes of padding after the packet' % (t.size - 0x80 - t.qwc * 16))


def weave_fields(w, h, px):
    """Interface pictures hold two interlaced fields, one above the other: rows [0, h/2) are the
    even scanlines and rows [h/2, 2*(h/2)) the odd ones. Return the picture with the rows interleaved."""
    half = h // 2
    out = []
    for k in range(half):
        out.extend(px[k * w:(k + 1) * w])
        out.extend(px[(half + k) * w:(half + k + 1) * w])
    return w, half * 2, out


def write_ppm(path, w, h, px):
    with open(path, 'wb') as f:
        f.write(b'P6\n%d %d\n255\n' % (w, h))
        f.write(bytes(c for r, g, b, a in px for c in (r, g, b)))


def write_pgm(path, w, h, px):
    with open(path, 'wb') as f:
        f.write(b'P5\n%d %d\n255\n' % (w, h))
        f.write(bytes(a for r, g, b, a in px))


# ----------------------------------------------------------------------------------------

def kind_of(path, forced):
    if forced:
        return forced
    ext = os.path.splitext(path)[1].lower()
    if ext == '.vif':
        return 'vif'
    if ext in ('.tex', '.etex'):
        return 'tex'
    raise FormatError('cannot tell the file kind from the extension %r; use --kind vif|tex' % ext)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Inspect Snowblind .vif models and .tex textures.')
    ap.add_argument('file')
    ap.add_argument('--kind', choices=('vif', 'tex'))
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--obj', metavar='OUT.obj')
    ap.add_argument('--tex', metavar='FILE.tex', help='texture whose size normalises the UVs of --obj')
    ap.add_argument('--texsize', metavar='WxH')
    ap.add_argument('--meshes', default='default', help='all, default, or a comma-separated list')
    ap.add_argument('--ppm', metavar='OUT.ppm')
    ap.add_argument('--pgm', metavar='OUT.pgm')
    ap.add_argument('--full', action='store_true', help='export the whole power-of-two surface')
    ap.add_argument('--weave', action='store_true', help='interleave the two stacked fields of an interface picture')
    a = ap.parse_args(argv)
    try:
        with open(a.file, 'rb') as f:
            d = f.read()
        kind = kind_of(a.file, a.kind)
        if kind == 'vif':
            need(not (a.ppm or a.pgm), '--ppm/--pgm apply to textures')
            m = parse_model(d)
            describe_model(m, a.verbose, sys.stdout)
            if a.obj:
                wh = None
                if a.texsize:
                    parts = a.texsize.lower().split('x')
                    need(len(parts) == 2 and all(x.isdigit() and int(x) > 0 for x in parts), '--texsize wants WxH, for example 256x128')
                    wh = (float(parts[0]), float(parts[1]))
                elif a.tex:
                    with open(a.tex, 'rb') as f:
                        t = parse_texture(f.read())
                    wh = (float(t.w), float(t.h)) if t.w else None
                nv, sel = export_obj(m, a.obj, a.meshes, wh, os.path.basename(a.file))
                print('wrote %s: %d vertices from meshes %s' % (a.obj, nv, ','.join(str(i) for i in sel)))
        else:
            need(not a.obj, '--obj applies to models')
            t = parse_texture(d)
            describe_texture(t, a.verbose, sys.stdout)
            if a.ppm or a.pgm:
                need(not (a.full and a.weave), '--weave applies to the used part, not with --full')
                w, h, px = decode_texture(t, a.full)
                if a.weave:
                    w, h, px = weave_fields(w, h, px)
                if a.ppm:
                    write_ppm(a.ppm, w, h, px)
                    print('wrote %s (%dx%d colour)' % (a.ppm, w, h))
                if a.pgm:
                    write_pgm(a.pgm, w, h, px)
                    print('wrote %s (%dx%d alpha, stored 0x80 written as 255)' % (a.pgm, w, h))
    except FormatError as e:
        print('model_info: %s: %s' % (a.file, e), file=sys.stderr)
        return 2
    except (struct.error, IndexError, KeyError) as e:
        print('model_info: %s: malformed file (%s: %s)' % (a.file, type(e).__name__, e), file=sys.stderr)
        return 2
    except OSError as e:
        print('model_info: %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
