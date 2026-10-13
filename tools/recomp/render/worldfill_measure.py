#!/usr/bin/env python3
"""worldfill_measure.py - what a level's geometry holds for a camera on the ground.

  python3 tools/recomp/render/worldfill_measure.py LEVEL.world [LEVEL.world ...] [--tsv]

The game was drawn from above (camera 340 to 450 units from the character, pitched 55 to 66
degrees down), and its levels were built for that.  This reads a `.world` entry (unpacked
from the level's lump; docs/formats/world.md, tools/world_info.py) and measures what a view
along the ground needs to know (docs/issues/native-first-person-world.md):

  floor       the ground a character walks on: the terrain's height samples at the nodes of the
              level's path grid that have links.  (The terrain's height field is the top
              surface of everything, walls included - a wall is high ground one cannot reach -
              so "over the ground" must be measured from the walked floor near by, not from
              the sample under the triangle.)
  facing      area of the drawn triangles by the way they face: up (floors, tops of walls and
              roofs), side (walls, cliffs), down (ceilings, undersides);
  height      the same area by height over the nearest walked floor: under it, at it, up to a
              character's head (60 units), above it;
  wall tops   the up-facing area more than 30 units over the floor, and how high it lies (the
              quartiles): the tops of the walls, which is where a level ends upward;
  overhead    how much of the walked floor has any geometry more than 70 units over it,
              and how much has a face that looks down: a ceiling;
  open tops   edges that belong to one triangle only, of a wall, along its top: a wall that
              ends in the air with nothing closing it.  "floor rim": such an edge of an
              up-facing triangle - where a floor or a wall top simply stops;
  extent      the box of the geometry and the walked floor.

Edges are matched by position (quarter units, the files' own grid), across chunks.  Where
two chunks meet with different tessellation an edge is counted as open that is closed in
the picture: the open-edge lengths are upper bounds.  Standard library only; prints
figures, writes nothing.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE))))
import world_info  # noqa: E402

HEAD = 60.0         # a character's height (the collision height of a creature, and what fpview.h takes)
OVER = 70.0         # "overhead" starts here
GRID = 8            # units per cell of the overhead raster


def measure(path):
    data = open(path, 'rb').read()
    w = world_info.World(data)
    out = {'name': os.path.basename(path).split('__')[-1].replace('.world', '')}
    kinds = {}
    for c in w.chunks:
        k = world_info.chunk_kind(c)
        kinds[k] = kinds.get(k, 0) + 1
    out['kinds'] = kinds

    # ---- the ground: the terrain's height samples, 4 units apart
    tx0, ty0, tw, th, heights, _flags = world_info.terrain_raster(w)
    step = world_info.SAMPLE_STEP

    def ground(x, y):
        px, py = int(round(x / step)) - tx0, int(round(y / step)) - ty0
        best = None
        for r in (0, 1, 2, 3):
            for j in range(py - r, py + r + 1):
                if not 0 <= j < th:
                    continue
                for i in range(px - r, px + r + 1):
                    if 0 <= i < tw and (abs(i - px) == r or abs(j - py) == r):
                        h = heights[j * tw + i]
                        if h is not None and (best is None or h > best):
                            best = h
            if best is not None:
                return best
        return None

    # ---- the floor: path nodes with links, 24 units apart, at the terrain's height there
    PC = world_info.PATH_CELL
    cells_p = w.path_cells() or []
    node = {}
    for j in range(w.pg_h):
        for i in range(w.pg_w):
            if cells_p[j * w.pg_w + i] & 0xFF:
                h = ground((i + w.pg_x0) * PC, (j + w.pg_y0) * PC)
                if h is not None:
                    node[(i + w.pg_x0, j + w.pg_y0)] = h
    floor_cache = {}

    def floor(x, y, z):
        """Height of the walked floor near (x, y): of the nodes within 4 (96 units), the nearest ring's
        node closest in height to z.  None when nothing walked is that near."""
        ni, nj = int(round(x / PC)), int(round(y / PC))
        ring = floor_cache.get((ni, nj))
        if ring is None:
            ring = []
            for r in range(0, 5):
                for j in range(nj - r, nj + r + 1):
                    for i in range(ni - r, ni + r + 1):
                        if (abs(i - ni) == r or abs(j - nj) == r) and (i, j) in node:
                            ring.append(node[(i, j)])
                if ring:
                    break
            floor_cache[(ni, nj)] = ring
        if not ring:
            return None
        return min(ring, key=lambda h: abs(h - z)) if len(ring) > 1 else ring[0]

    out['ground_area'] = len(node) * PC * PC
    gs = list(node.values())
    out['ground_z'] = (min(gs), max(gs)) if gs else (0, 0)
    tops = []                        # (height over the floor, area) of up-facing triangles more than 30 over it

    FACES = ('up', 'side', 'down')
    BINS = ('below', 'ground', 'to_head', 'to_150', 'above_150', 'no_ground')
    area = {f: {b: 0.0 for b in BINS} for f in FACES}
    edges = {}                       # (key a, key b) -> [count, facing, is_top, length, mid x, y, z]
    over = {}                        # overhead raster cell -> 1 any, 2 down-facing
    box = [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]
    tris = 0

    for c in w.chunks:
        if world_info.chunk_kind(c) != 'mesh' or c.cell == 0:
            continue
        a, b, cc, dd = w.chunk_matrix(c)
        for bt in w.batches(c):
            verts = list(w.chunk_world_vertices(c, bt))
            norms = bt.normals
            s = bt.strip
            for k in range(2, len(s)):
                if s[k][1]:
                    continue
                i0, i1, i2 = s[k - 2][0], s[k - 1][0], s[k][0]
                if i0 == i1 or i1 == i2 or i0 == i2:
                    continue
                p0, p1, p2 = verts[i0], verts[i1], verts[i2]
                ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                ln = math.sqrt(nx * nx + ny * ny + nz * nz)
                if ln < 1e-6:
                    continue
                tris += 1
                ar = 0.5 * ln
                # the stored normals say which side is the front (the winding does not: world.md)
                sx = sy = sz = 0.0
                for i in (i0, i1, i2):
                    n = norms[i]
                    sx += a * n[0] + b * n[1]
                    sy += cc * n[0] + dd * n[1]
                    sz += n[2]
                if nx * sx + ny * sy + nz * sz < 0:
                    nx, ny, nz = -nx, -ny, -nz
                nz /= ln
                face = 'up' if nz >= 0.6 else 'down' if nz <= -0.6 else 'side'
                cx = (p0[0] + p1[0] + p2[0]) / 3.0
                cy = (p0[1] + p1[1] + p2[1]) / 3.0
                cz = (p0[2] + p1[2] + p2[2]) / 3.0
                g = floor(cx, cy, min(p0[2], p1[2], p2[2]))
                if g is None:
                    hb = 'no_ground'
                else:
                    rel = cz - g
                    if face == 'up' and rel > 30:
                        tops.append((rel, ar))
                    hb = 'below' if rel < -8 else 'ground' if rel <= 8 else 'to_head' if rel <= HEAD else 'to_150' if rel <= 150 else 'above_150'
                area[face][hb] += ar
                for p in (p0, p1, p2):
                    for d in range(3):
                        if p[d] < box[d]: box[d] = p[d]
                        if p[d] > box[3 + d]: box[3 + d] = p[d]
                # overhead raster
                if g is not None and cz - g > OVER:
                    x0 = int(math.floor(min(p0[0], p1[0], p2[0]) / GRID)); x1 = int(math.floor(max(p0[0], p1[0], p2[0]) / GRID))
                    y0 = int(math.floor(min(p0[1], p1[1], p2[1]) / GRID)); y1 = int(math.floor(max(p0[1], p1[1], p2[1]) / GRID))
                    den = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
                    if abs(den) > 1e-9 and (x1 - x0) * (y1 - y0) < 4096:
                        mark = 2 if face == 'down' else 1
                        for gy in range(y0, y1 + 1):
                            qy = (gy + 0.5) * GRID
                            for gx in range(x0, x1 + 1):
                                qx = (gx + 0.5) * GRID
                                l0 = ((p1[1] - p2[1]) * (qx - p2[0]) + (p2[0] - p1[0]) * (qy - p2[1])) / den
                                l1 = ((p2[1] - p0[1]) * (qx - p2[0]) + (p0[0] - p2[0]) * (qy - p2[1])) / den
                                if l0 >= -0.02 and l1 >= -0.02 and l0 + l1 <= 1.02:
                                    key = (gx, gy)
                                    if over.get(key, 0) < mark:
                                        over[key] = mark
                # edges
                keys = [(int(round(p[0] * 4)), int(round(p[1] * 4)), int(round(p[2] * 4))) for p in (p0, p1, p2)]
                pts = (p0, p1, p2)
                for e in range(3):
                    ka, kb = keys[e], keys[(e + 1) % 3]
                    if ka == kb:
                        continue
                    key = (ka, kb) if ka < kb else (kb, ka)
                    rec = edges.get(key)
                    if rec is not None:
                        rec[0] += 1
                        continue
                    pa, pb = pts[e], pts[(e + 1) % 3]
                    ex, ey, ez = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
                    el = math.sqrt(ex * ex + ey * ey + ez * ez)
                    mz = (pa[2] + pb[2]) * 0.5
                    top = abs(ez) < 0.35 * el and mz > cz
                    edges[key] = [1, face, top, el, (pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5, mz]

    out['triangles'] = tris
    out['area'] = area
    out['box'] = box
    # ---- overhead: of the cells with ground under them
    cells = set()
    for (i, j) in node:
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                cells.add(((i * PC + dx * GRID) // GRID, (j * PC + dy * GRID) // GRID))
    tops.sort()
    tarea = sum(t[1] for t in tops)
    quart = []
    run = 0.0
    want = [0.25, 0.5, 0.75]
    for rel, ar in tops:
        run += ar
        while want and run >= want[0] * tarea:
            quart.append(rel)
            want.pop(0)
    out['tops_area'] = tarea
    out['tops_quart'] = quart + [0.0] * (3 - len(quart))
    out['walk_cells'] = len(cells)
    out['over_any'] = sum(1 for k in cells if over.get(k, 0) >= 1)
    out['over_down'] = sum(1 for k in cells if over.get(k, 0) == 2)
    # ---- open edges
    open_top = {'to_head': 0.0, 'to_150': 0.0, 'above_150': 0.0, 'other': 0.0}
    rim = 0.0
    other = 0.0
    all_len = 0.0
    for rec in edges.values():
        all_len += rec[3]
        if rec[0] != 1:
            continue
        if rec[1] == 'side' and rec[2]:
            g = floor(rec[4], rec[5], rec[6])
            if g is None:
                open_top['other'] += rec[3]
            else:
                rel = rec[6] - g
                open_top['to_head' if rel <= HEAD else 'to_150' if rel <= 150 else 'above_150'] += rec[3]
        elif rec[1] == 'up':
            rim += rec[3]
        else:
            other += rec[3]
    out['edges_len'] = all_len
    out['open_top'] = open_top
    out['floor_rim'] = rim
    out['open_other'] = other
    return out


def report(m):
    a = m['area']
    total = sum(sum(v.values()) for v in a.values()) or 1.0
    k = m['kinds']
    print('%s: %d triangles in %d geometry chunks; %d water tiles, %d scenery models, %d emitters, %d lights' % (
        m['name'], m['triangles'], k.get('mesh', 0), k.get('water', 0), k.get('model', 0), k.get('emitter', 0), k.get('light', 0)))
    b = m['box']
    print('  geometry box x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f; walked floor (path nodes): %.0f square units, z %d..%d' % (
        b[0], b[3], b[1], b[4], b[2], b[5], m['ground_area'], m['ground_z'][0], m['ground_z'][1]))
    print('  area by facing (%% of %.0f square units):' % total)
    for f in ('up', 'side', 'down'):
        v = a[f]
        print('    %-5s %5.1f %%   under the floor %4.1f | at the floor %4.1f | to head height %4.1f | to 150 %4.1f | above 150 %4.1f | no walked floor within 96 units %4.1f' % (
            f, 100 * sum(v.values()) / total, 100 * v['below'] / total, 100 * v['ground'] / total, 100 * v['to_head'] / total,
            100 * v['to_150'] / total, 100 * v['above_150'] / total, 100 * v['no_ground'] / total))
    q = m['tops_quart']
    print('  wall tops: up-facing area more than 30 over the floor is %.1f %% of all area; a quarter of it lies below %.0f, half below %.0f, three quarters below %.0f units over the floor' % (
        100 * m['tops_area'] / total, q[0], q[1], q[2]))
    wc = m['walk_cells'] or 1
    print('  overhead: %.1f %% of the walked floor has geometry more than %d units over it; %.1f %% has a face looking down there (a ceiling)' % (
        100.0 * m['over_any'] / wc, OVER, 100.0 * m['over_down'] / wc))
    t = m['open_top']
    print('  open wall tops (upper bound): %.0f units of edge up to head height, %.0f up to 150, %.0f above, %.0f away from any floor; rim of up-facing surfaces %.0f; other open edges %.0f (all edges %.0f)' % (
        t['to_head'], t['to_150'], t['above_150'], t['other'], m['floor_rim'], m['open_other'], m['edges_len']))


def tsv(m):
    a = m['area']
    total = sum(sum(v.values()) for v in a.values()) or 1.0
    f = lambda face: 100 * sum(a[face].values()) / total
    above = 100 * sum(a[face][b] for face in a for b in ('to_150', 'above_150')) / total
    q = m['tops_quart']
    t = m['open_top']
    wc = m['walk_cells'] or 1
    b = m['box']
    print('\t'.join(str(x) for x in (
        m['name'], m['triangles'], '%.0f' % f('up'), '%.0f' % f('side'), '%.1f' % f('down'), '%.0f' % above,
        '%.1f' % (100.0 * m['over_any'] / wc), '%.1f' % (100.0 * m['over_down'] / wc),
        '%.0f' % (t['to_head'] + t['to_150'] + t['above_150'] + t['other']), '%.0f' % (t['to_150'] + t['above_150']), '%.0f' % m['floor_rim'],
        '%.0f' % m['tops_quart'][1], '%.0f' % m['tops_quart'][2], '%.0f' % m['ground_area'])))


def main():
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    if '--tsv' in sys.argv:
        print('level\ttriangles\tup%\tside%\tdown%\tarea above head%\twalkable under geometry%\tunder a ceiling%\topen wall tops\tof them above head\trim of up-facing surfaces\twall tops: median height\tthird quartile\twalked floor area')
    for path in args:
        try:
            m = measure(path)
        except world_info.FormatError as error:
            print('%s: %s' % (path, error))
            continue
        tsv(m) if '--tsv' in sys.argv else report(m)
    return 0


if __name__ == '__main__':
    sys.exit(main())
