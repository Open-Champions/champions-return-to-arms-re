#!/usr/bin/env python3
"""er_world_fit.py - the Elden Ring world layer's rebuild (project/er_world.gd): Elden Ring ruin pieces fitted over some of a
level's shapes, and the check that keeps them honest.  Local only: it reads the owner's own converted Elden Ring models and
his own level geometry, and writes into the owner's local er-world folder.  Nothing it reads or writes is tracked.

  python3 er_world_fit.py RECIPE.json [--pictures DIR]

The recipe (a local file; numbers of the level's shapes and names of Elden Ring pieces are data, never tracked):

  {"level": "hub",
   "dump": "<app er world dump of the level: the scene tap's packets, world space>",
   "level_obj": "<optional: world_info.py --obj of the level: every chunk (a dump holds only what one frame drew)>",
   "world": "<the level's .world file: its terrain height field, the game's collision>",
   "models": "<flverdump output folder>", "textures": "<PNG folder>", "out": "<er-world>/rebuild/<level>",
   "tolerance": 12, "reach": <optional, per target: tops higher than this over the ground are not floors (40)>,
   "targets": [{"name": ..., "volume": [cx, cy, cz, hx, hy, hz, yaw, cylinder 0|1, kinds 1 level|2 models] (or "volumes": [...]),
                "object": <optional: only this object's packets>,
                "review": <optional: why the pictures refused it although the check passed (the game's shape stays)>,
                "parts": [{"model": "<flverdump stem>", "fit": "disc" | "box", ...}]}]}

  disc: {"r": radius, "z0": bottom, "z1": top, "cx", "cy" (default: the volume's centre), "turn": degrees}
        the piece's own footprint centre to (cx, cy), its radius to r, its height span to z0..z1
  box:  {"box": [x0, y0, z0, x1, y1, z1] (default: the reference geometry's box), "turn": degrees, "keep_aspect": 0..1}
        the piece's own box (turned) onto that box
  any part: "surfaces": {"<the model's mesh number>" or "*": {"albedo": "<PNG name>", "normal": ..., "metal": "<a metal map>",
        "mask": "<a mask map>", "params": {<er_ruin.gdshader uniform>: value}, "tint": <this surface's own tint 0..1>}}
        a mesh's material made other than the model's own: a carved stone's moulding made gold, a pale stone made marble

What it stands in for is what the game draws inside the target's volume (the drawer leaves exactly that out at run time:
RtaDrawer.set_world_hide - a level draw lying wholly inside, a model's triangles lying wholly inside), taken from the dump.

The check, per target: the piece's surface is sampled every ~3 units; a sample is VISIBLE unless it faces down onto the
ground or onto another part of the target (its normal, 1.5 units out, is under the ground or inside another part's own
shape), or lies inside the rebuilt shape itself (a ray out along its normal meets a back face first: the top of a plinth
under its shaft).  Every visible sample must lie within the tolerance (a hand's width, 12 units) of the surface the game
draws there (the reference: the left-out geometry, point-to-triangle distance); and for a target of the level's own
chunks, every visible sample that faces up and is within reach of the ground (`reach`, 40 units: a floor, a step, not an
arch's crown) within the tolerance of a collision sample next to it (the terrain height field of the .world file: what
the player stands on).  A model's collision is its own circle, so for a model only the surface is checked.  A target with
any sample over the line is REFUSED: nothing of it is written, and the game's own shape stays.

Writes OUT/rebuild.json (pieces, volumes, the check), OUT/<name>.bin (float32: positions, normals, uvs per vertex; int32
indices), OUT/tex/*.png, and with --pictures a top and a side view of each target's samples (green within, red over).
Needs numpy and Pillow.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import world_info  # noqa: E402  (tools/world_info.py: the level file's terrain)


# ---- input ------------------------------------------------------------------------------------------------------------
def load_dump(path):
    """the dump's groups: name -> (triangles (n, 3, 3), kind, object)"""
    verts, groups, cur = [], {}, None
    for line in open(path):
        if line.startswith('v '):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('g '):
            cur = line.split()[1]
            groups.setdefault(cur, [])
        elif line.startswith('f '):
            groups[cur].append([int(x) - 1 for x in line.split()[1:4]])
    v = np.array(verts, float)
    out = {}
    for name, faces in groups.items():
        if not faces:
            continue
        parts = name.split('_')
        kind = int(parts[1][1:])
        obj = int(parts[2][1:])
        out[name] = (v[np.array(faces)], kind, obj)
    return out


def load_model(stem):
    """a flverdump model: per mesh positions, normals, uvs, triangles, material - turned to the game's frame (z up)"""
    j = json.load(open(stem + '.json'))
    b = open(stem + '.bin', 'rb').read()
    meshes = []
    for k, m in enumerate(j['meshes']):
        n, at = m['vertices'], m['at']
        p = np.frombuffer(b, np.float32, n * 3, at).reshape(n, 3).astype(float); at += n * 12
        nm = np.frombuffer(b, np.float32, n * 3, at).reshape(n, 3).astype(float); at += n * 12
        uv = np.frombuffer(b, np.float32, n * 2, at).reshape(n, 2).astype(float); at += n * 8 + n * 32
        idx = np.frombuffer(b, np.int32, m['indices'], at).reshape(-1, 3)
        if not len(idx):
            continue
        # y up -> z up: (x, y, z) -> (x, -z, y), a turn (no mirror)
        p = p[:, [0, 2, 1]] * np.array([1.0, -1.0, 1.0])
        nm = nm[:, [0, 2, 1]] * np.array([1.0, -1.0, 1.0])
        meshes.append({'p': p, 'n': nm, 'uv': uv, 'i': idx.astype(np.int64), 'mat': j['materials'][m['material']], 'k': k})
    return meshes


def inside(points, vol):
    """points (n, 3) inside a volume [cx, cy, cz, hx, hy, hz, yaw, cylinder, kinds] (as RtaDrawer::world_hidden)"""
    d = points - np.array(vol[:3])
    ok = np.abs(d[..., 2]) <= vol[5]
    if vol[7]:
        return ok & (d[..., 0] ** 2 + d[..., 1] ** 2 <= vol[3] ** 2)
    c, s = math.cos(math.radians(vol[6])), math.sin(math.radians(vol[6]))
    lx, ly = d[..., 0] * c + d[..., 1] * s, -d[..., 0] * s + d[..., 1] * c
    return ok & (np.abs(lx) <= vol[3]) & (np.abs(ly) <= vol[4])


def load_level_obj(path):
    """the level's chunks as world_info.py --obj writes them (all of them, not only the ones a frame drew): kind 1"""
    verts, groups, cur = [], {}, None
    for line in open(path):
        if line.startswith('v '):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('g '):
            cur = line.split()[1]
            groups.setdefault(cur, [])
        elif line.startswith('f '):
            groups[cur].append([int(x.split('/')[0]) - 1 for x in line.split()[1:4]])
    v = np.array(verts, float)
    return {'level_' + name: (v[np.array(f)], 1, 0) for name, f in groups.items() if f and '_cell0_' not in name}


def reference(dump, vol, obj=None):
    """what the game draws inside the volume: level draws lying wholly in it, models' triangles lying wholly in it"""
    tris = []
    for name, (t, kind, o) in dump.items():
        if not (vol[8] & kind) or (obj is not None and o != obj):
            continue
        ins = inside(t, vol).all(axis=1)
        if kind == 1:
            if ins.all():
                tris.append(t)
        else:
            tris.append(t[ins])
    tris = [t for t in tris if len(t)]
    return np.concatenate(tris) if tris else np.zeros((0, 3, 3))


# ---- fitting ----------------------------------------------------------------------------------------------------------
def turn(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c, p[:, 2]], 1)


def fit(meshes, part, vol, ref):
    allp = np.concatenate([m['p'][np.unique(m['i'])] for m in meshes])
    deg = part.get('turn', 0.0)
    allp = turn(allp, deg)
    lo, hi = allp.min(0), allp.max(0)
    if part['fit'] == 'disc':
        cx, cy = part.get('cx', vol[0]), part.get('cy', vol[1])
        r_own = max(hi[0] - lo[0], hi[1] - lo[1]) / 2.0
        mid = (lo + hi) / 2.0
        sxy = part['r'] / r_own
        sz = (part['z1'] - part['z0']) / max(hi[2] - lo[2], 1e-6)
        scale = np.array([sxy, sxy, sz])
        offset = np.array([cx, cy, part['z0']]) - np.array([mid[0], mid[1], lo[2]]) * scale
    else:
        box = part.get('box')
        if box is None:
            rp = ref.reshape(-1, 3)
            box = list(rp.min(0)) + list(rp.max(0))
        b0, b1 = np.array(box[:3], float), np.array(box[3:], float)
        scale = (b1 - b0) / np.maximum(hi - lo, 1e-6)
        k = part.get('keep_aspect', 0.0)
        if k:
            sxy = math.sqrt(scale[0] * scale[1])
            scale[0] = scale[0] * (1 - k) + sxy * k
            scale[1] = scale[1] * (1 - k) + sxy * k
        offset = (b0 + b1) / 2.0 - (lo + hi) / 2.0 * scale
        offset[2] = b0[2] - lo[2] * scale[2]
    out = []
    for m in meshes:
        p = turn(m['p'], deg) * scale + offset
        # normals under a scale that differs by axis: by the inverse
        n = turn(m['n'], deg) / scale
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        out.append(dict(m, p=p, n=n))
    return out, {'scale': scale.round(3).tolist(), 'offset': offset.round(2).tolist(), 'turn': deg}


# ---- the check --------------------------------------------------------------------------------------------------------
def samples(meshes, step=3.0):
    """points over every triangle, about `step` apart, with the triangle's own normal"""
    pts, nrm = [], []
    for m in meshes:
        t = m['p'][m['i']]
        e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        cr = np.cross(e1, e2)
        area = np.linalg.norm(cr, axis=1) / 2.0
        n = cr / np.maximum(2 * area[:, None], 1e-9)
        # the vertex normals say which side is out (the triangles' winding is not to be trusted)
        vn = m['n'][m['i']].mean(1)
        n *= np.where((n * vn).sum(1) < 0, -1.0, 1.0)[:, None]
        count = np.maximum(1, np.ceil(area / (step * step * 0.5))).astype(int)
        count = np.minimum(count, 400)
        rng = np.random.default_rng(7)
        for k in np.unique(count):
            sel = np.where(count == k)[0]
            r = rng.random((len(sel), k, 2))
            flip = r.sum(2) > 1
            r[flip] = 1 - r[flip]
            p = t[sel, 0][:, None] + e1[sel][:, None] * r[..., :1] + e2[sel][:, None] * r[..., 1:]
            pts.append(p.reshape(-1, 3))
            nrm.append(np.repeat(n[sel], k, axis=0))
            # the corners too: the edges are where a piece sticks out
            pts.append(t[sel].reshape(-1, 3))
            nrm.append(np.repeat(n[sel], 3, axis=0))
    return np.concatenate(pts), np.concatenate(nrm)


def point_triangle_distance(p, tris, chunk=2048):
    """the distance of each point to the nearest triangle (Ericson's closest point, vectorised)"""
    if not len(tris):
        return np.full(len(p), np.inf)
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    ab, ac = b - a, c - a
    best = np.full(len(p), np.inf)
    for s in range(0, len(p), chunk):
        q = p[s:s + chunk][:, None, :]
        ap = q - a
        d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
        bp = q - b
        d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
        cp = q - c
        d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
        va = d3 * d6 - d5 * d4
        vb = d5 * d2 - d1 * d6
        vc = d1 * d4 - d3 * d2
        den = np.where(np.abs(va + vb + vc) < 1e-12, 1e-12, va + vb + vc)
        v = vb / den
        w = vc / den
        closest = a + ab * v[..., None] + ac * w[..., None]
        # the regions outside the face: vertices and edges
        with np.errstate(divide='ignore', invalid='ignore'):
            reg_a = (d1 <= 0) & (d2 <= 0)
            reg_b = (d3 >= 0) & (d4 <= d3)
            reg_c = (d6 >= 0) & (d5 <= d6)
            reg_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
            t_ab = np.clip(d1 / np.where(d1 - d3 == 0, 1e-12, d1 - d3), 0, 1)
            reg_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
            t_ac = np.clip(d2 / np.where(d2 - d6 == 0, 1e-12, d2 - d6), 0, 1)
            reg_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
            t_bc = np.clip((d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1e-12, (d4 - d3) + (d5 - d6)), 0, 1)
        closest = np.where(reg_bc[..., None], b + (c - b) * t_bc[..., None], closest)
        closest = np.where(reg_ac[..., None], a + ac * t_ac[..., None], closest)
        closest = np.where(reg_ab[..., None], a + ab * t_ab[..., None], closest)
        closest = np.where(reg_c[..., None], c + 0 * q, closest)
        closest = np.where(reg_b[..., None], b + 0 * q, closest)
        closest = np.where(reg_a[..., None], a + 0 * q, closest)
        dist = np.linalg.norm(q - closest, axis=-1)
        best[s:s + chunk] = dist.min(1)
    return best


def first_hit_is_back(origin, direction, tris, normals, chunk=256):
    """per ray: does the nearest triangle it meets face away from it (the ray starts inside a closed shape)?"""
    a = tris[:, 0]
    e1, e2 = tris[:, 1] - a, tris[:, 2] - a
    out = np.zeros(len(origin), bool)
    for s in range(0, len(origin), chunk):
        o, d = origin[s:s + chunk][:, None], direction[s:s + chunk][:, None]
        pv = np.cross(d, e2)
        det = (e1 * pv).sum(-1)
        with np.errstate(divide='ignore', invalid='ignore'):
            inv = 1.0 / det
            tv = o - a
            u = (tv * pv).sum(-1) * inv
            qv = np.cross(tv, e1)
            v = (d * qv).sum(-1) * inv
            t = (e2 * qv).sum(-1) * inv
        hit = (np.abs(det) > 1e-9) & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4)
        t = np.where(hit, t, np.inf)
        k = t.argmin(1)
        has = np.isfinite(t[np.arange(len(k)), k])
        back = (normals[k] * direction[s:s + chunk]).sum(-1) > 0
        out[s:s + chunk] = has & back
    return out


class Ground:
    """the game's collision height (terrain samples, 4 units apart): the highest sample within 3 units"""
    def __init__(self, world_path):
        w = world_info.World(open(world_path, 'rb').read())
        self.x0, self.y0, self.w, self.h, heights, _ = world_info.terrain_raster(w)
        self.z = np.array([np.nan if h is None else h for h in heights], float).reshape(self.h, self.w)

    def nearest(self, x, y, z):
        """the least height difference to a sample within 3 units (nan where there is none)"""
        px = np.rint(x / 4.0).astype(int) - self.x0
        py = np.rint(y / 4.0).astype(int) - self.y0
        best = np.full(len(x), np.nan)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                qx, qy = np.clip(px + dx, 0, self.w - 1), np.clip(py + dy, 0, self.h - 1)
                dz = np.abs(self.z[qy, qx] - z)
                best = np.where(np.isnan(best) | (dz < best), np.where(np.isnan(dz), best, dz), best)
        return best

    def at(self, x, y):
        px = np.rint(x / 4.0).astype(int) - self.x0
        py = np.rint(y / 4.0).astype(int) - self.y0
        best = np.full(len(x), np.nan)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                qx, qy = np.clip(px + dx, 0, self.w - 1), np.clip(py + dy, 0, self.h - 1)
                z = self.z[qy, qx]
                best = np.where(np.isnan(best) | (z > best), np.where(np.isnan(z), best, z), best)
        return best


def part_shape_inside(p, part):
    """inside a part's own fitted shape (its disc, or its box): what a sample facing into it cannot be seen from"""
    if part['fit'] == 'disc':
        r = np.hypot(p[:, 0] - part['_cx'], p[:, 1] - part['_cy'])
        return (r < part['r'] - 0.5) & (p[:, 2] > part['z0'] - 0.5) & (p[:, 2] < part['z1'] - 0.3)
    b = part['_box']
    return np.all((p > np.array(b[:3]) + 0.5) & (p < np.array(b[3:]) - 0.5), axis=1)


def check(target, fitted, ref, ground, tol):
    # a model's collision is its own circle, not the terrain: for it only the surface is checked (the ground still hides)
    collide = target.get('collision', all(v[8] & 1 for v in (target.get('volumes') or [target['volume']])))
    pts, nrm, owner = [], [], []
    for k, meshes in enumerate(fitted):
        p, n = samples(meshes)
        pts.append(p); nrm.append(n); owner.append(np.full(len(p), k))
    p, n, owner = np.concatenate(pts), np.concatenate(nrm), np.concatenate(owner)
    probe = p + n * 1.5
    g = ground.at(probe[:, 0], probe[:, 1]) if ground else np.full(len(p), np.nan)
    hidden = ~np.isnan(g) & (probe[:, 2] < g - 0.5)
    for k, part in enumerate(target['parts']):
        hidden |= (owner != k) & part_shape_inside(probe, part)
    vis = ~hidden
    d_ref = point_triangle_distance(p, ref)
    up = vis & (n[:, 2] > 0.7) & bool(collide)
    if ground is not None:
        # only what one could stand on: a top within reach of the ground under it (an arch's crown is not a floor)
        g_at = ground.at(p[:, 0], p[:, 1])
        up &= ~(p[:, 2] - np.nan_to_num(g_at, nan=-1e9) > float(target.get('reach', 40.0)))
    d_near = ground.nearest(p[:, 0], p[:, 1], p[:, 2]) if ground else np.full(len(p), np.nan)
    d_col = np.where(up & ~np.isnan(d_near), d_near, 0.0)
    over = vis & ((d_ref > tol) | (d_col > tol))
    if over.any():
        # a sample over the line that lies inside the rebuilt shape itself (the top of a plinth under its shaft) is not seen:
        # the first surface a ray out along its normal meets is a back face of the pieces
        tris, tn = [], []
        for meshes in fitted:
            for m in meshes:
                t = m['p'][m['i']]
                nn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                vn = m['n'][m['i']].mean(1)
                nn *= np.where((nn * vn).sum(1) < 0, -1.0, 1.0)[:, None]
                tris.append(t); tn.append(nn)
        inner = first_hit_is_back(p[over] + n[over] * 0.3, n[over], np.concatenate(tris), np.concatenate(tn))
        idx = np.where(over)[0][inner]
        vis[idx] = False
        over[idx] = False
    res = {
        'samples': int(len(p)), 'visible': int(vis.sum()),
        'reference_triangles': int(len(ref)),
        'surface_distance': {'max': round(float(d_ref[vis].max()), 2) if vis.any() else 0.0,
                             'p99': round(float(np.percentile(d_ref[vis], 99)), 2) if vis.any() else 0.0,
                             'mean': round(float(d_ref[vis].mean()), 2) if vis.any() else 0.0},
        'collision_distance_up': {'max': round(float(d_col[up].max()), 2) if up.any() else 0.0, 'samples': int(up.sum())},
        'over': int(over.sum()),
        'passed': bool(not over.any()),
    }
    return res, (p, vis, over)


def picture(path, ref, p, vis, over, title):
    """top and side views: the reference in grey, visible samples green (within) or red (over)"""
    allp = np.concatenate([ref.reshape(-1, 3), p]) if len(ref) else p
    lo, hi = allp.min(0) - 4, allp.max(0) + 4
    size = 480
    im = Image.new('RGB', (size * 2, size + 20), (24, 24, 30))
    d = ImageDraw.Draw(im)
    for view, (ax, ay) in enumerate(((0, 1), (0, 2))):
        span = max(hi[ax] - lo[ax], hi[ay] - lo[ay])
        def to(q):
            return (view * size + (q[..., ax] - lo[ax]) / span * (size - 8) + 4, size + 16 - ((q[..., ay] - lo[ay]) / span * (size - 8) + 4))
        for t in ref:
            x, y = to(t)
            d.polygon(list(zip(x, y)), outline=(90, 90, 100))
        x, y = to(p[vis & ~over])
        for a, b in zip(x[::3], y[::3]):
            d.point((a, b), fill=(60, 200, 90))
        x, y = to(p[over])
        for a, b in zip(x, y):
            d.rectangle((a - 1, b - 1, a + 1, b + 1), fill=(240, 50, 50))
    d.text((4, 2), title, fill=(255, 255, 0))
    im.save(path)


# ---- output -----------------------------------------------------------------------------------------------------------
def texture_pair(mat, texdir):
    """the material's first albedo and normal map, by name, from the PNG folder (an index of material names may give them)"""
    albedo = normal = None
    for t in mat.get('_textures', []):
        base = os.path.splitext(os.path.basename(t.replace('\\', '/')))[0]
        f = os.path.join(texdir, base + '.png')
        if not os.path.exists(f):
            continue
        if base.lower().endswith('_a') and albedo is None:
            albedo = f
        elif base.lower().endswith('_n') and normal is None:
            normal = f
    return albedo, normal


MAX_SIDE = 1024     # the pictures written at most this size (the 2048 maps: four times the loading at the level's start)


def smaller(im):
    if max(im.size) > MAX_SIDE:
        im = im.resize((min(im.width, MAX_SIDE), min(im.height, MAX_SIDE)), Image.LANCZOS)
    return im


def write_picture(src, dst):
    smaller(Image.open(src)).save(dst)


def write_normal(src, dst):
    """an Elden Ring normal map (x, y in red and green) with its z put back, as Godot wants it"""
    im = np.asarray(smaller(Image.open(src).convert('RGBA'))).astype(float) / 255.0
    x, y = im[..., 0] * 2 - 1, im[..., 1] * 2 - 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    out = np.stack([x * 0.5 + 0.5, y * 0.5 + 0.5, z * 0.5 + 0.5], -1)
    Image.fromarray((out * 255).round().astype(np.uint8)).save(dst)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    recipe = json.load(open(sys.argv[1]))
    pics = sys.argv[sys.argv.index('--pictures') + 1] if '--pictures' in sys.argv else None
    tol = float(recipe.get('tolerance', 12.0))
    dump = load_dump(recipe['dump'])
    if recipe.get('level_obj'):
        # the level's chunks from its own file (every one; a dump has only what one frame drew), the models from the dump
        dump = {k: v for k, v in dump.items() if v[1] != 1}
        dump.update(load_level_obj(recipe['level_obj']))
    ground = Ground(recipe['world']) if recipe.get('world') else None
    index = json.load(open(recipe['material_index'])) if recipe.get('material_index') else {}
    out = recipe['out']
    os.makedirs(os.path.join(out, 'tex'), exist_ok=True)
    if pics:
        os.makedirs(pics, exist_ok=True)
    pieces, volumes, report = [], [], []
    for target in recipe['targets']:
        vols = target.get('volumes') or [target['volume']]
        vol = vols[0]
        ref = np.concatenate([reference(dump, v, target.get('object')) for v in vols])
        fitted, fits = [], []
        for part in target['parts']:
            meshes = load_model(os.path.join(recipe['models'], part['model']))
            if part.get('meshes'):
                meshes = [m for k, m in enumerate(meshes) if k in part['meshes']]
            f, info = fit(meshes, part, vol, ref)
            part['_cx'], part['_cy'] = part.get('cx', vol[0]), part.get('cy', vol[1])
            allp = np.concatenate([m['p'] for m in f])
            part['_box'] = list(allp.min(0)) + list(allp.max(0))
            fitted.append(f)
            fits.append(info)
        res, (p, vis, over) = check(target, fitted, ref, ground, tol)
        res['name'] = target['name']
        res['fits'] = fits
        if target.get('review'):
            # refused on sight (the pictures): a fit can pass the check and still look worse than the game's own shape
            # (plainer, less carved, less colour); then the game's shape stays - never a downgrade
            res['review'] = target['review']
            res['passed'] = False
        report.append(res)
        verdict = 'passed' if res['passed'] else ('REFUSED on review (%s)' % res['review'] if res.get('review') else 'REFUSED')
        print('%-12s %s: %d visible samples of %d, surface distance max %.1f (p99 %.1f, mean %.1f), up-facing to collision max %.1f; '
              '%d over %.0f units; %d reference triangles' % (target['name'], verdict, res['visible'], res['samples'], res['surface_distance']['max'],
              res['surface_distance']['p99'], res['surface_distance']['mean'], res['collision_distance_up']['max'], res['over'], tol,
              res['reference_triangles']))
        if pics:
            picture(os.path.join(pics, target['name'] + '.png'), ref, p, vis, over, '%s: %s (max %.1f)' % (target['name'], verdict, res['surface_distance']['max']))
        if not res['passed']:
            continue
        vi = len(volumes)
        volumes.extend(vols)
        for k, (part, f) in enumerate(zip(target['parts'], fitted)):
            name = '%s-%d' % (target['name'], k)
            pos, nrm, uvs, idx, surfaces = [], [], [], [], []
            base = 0
            for m in f:
                mat = dict(m['mat'])
                entry = index.get(mat['name'], {})
                mat['_textures'] = [t['path'] for t in mat.get('textures', []) if t.get('path')] + entry.get('tex', [])
                albedo, normal = texture_pair(mat, recipe['textures'])
                surf = {'first': int(sum(len(x) for x in idx)) * 3, 'count': int(len(m['i'])) * 3}
                # the recipe's own say over this mesh's material (see "surfaces" above): other textures, a metal or mask
                # map, shader values, its own tint
                over = dict(part.get('surfaces', {}).get('*', {}), **part.get('surfaces', {}).get(str(m['k']), {}))
                named = lambda b: os.path.join(recipe['textures'], b + '.png') if b else None
                if over.get('albedo'):
                    albedo = named(over['albedo'])
                if over.get('normal'):
                    normal = named(over['normal'])
                maps = [('albedo', albedo), ('normal', normal)] + [(k, named(over[k])) for k in ('metal', 'mask') if over.get(k)]
                if over.get('params'):
                    surf['params'] = over['params']
                if 'tint' in over:
                    surf['tint'] = over['tint']
                for key, src in maps:
                    if src:
                        dst = os.path.join(out, 'tex', os.path.basename(src))
                        if not os.path.exists(dst):
                            (write_normal if key == 'normal' else write_picture)(src, dst)
                        surf[key] = 'tex/' + os.path.basename(src)
                        if key == 'albedo':
                            surf['albedo_mean'] = [round(float(x), 4) for x in np.asarray(Image.open(src).convert('RGB').resize((32, 32))).reshape(-1, 3).mean(0) / 255.0]
                surfaces.append(surf)
                pos.append(m['p']); nrm.append(m['n']); uvs.append(m['uv']); idx.append(m['i'] + base)
                base += len(m['p'])
            with open(os.path.join(out, name + '.bin'), 'wb') as fh:
                P, N, U, I = np.concatenate(pos), np.concatenate(nrm), np.concatenate(uvs), np.concatenate(idx)
                fh.write(np.array([len(P), len(I) * 3], np.int32).tobytes())
                fh.write(P.astype(np.float32).tobytes()); fh.write(N.astype(np.float32).tobytes()); fh.write(U.astype(np.float32).tobytes())
                fh.write(I.astype(np.int32).tobytes())
            pieces.append({'name': name, 'mesh': name + '.bin', 'volume': vi, 'volumes': list(range(vi, vi + len(vols))), 'surfaces': surfaces,
                           'tint': target.get('tint', 0.6)})
    json.dump({'level': recipe['level'], 'tolerance': tol, 'volumes': volumes, 'pieces': pieces, 'check': report},
              open(os.path.join(out, 'rebuild.json'), 'w'), indent=1)
    print('%d of %d targets passed; %d pieces written to %s' % (sum(r['passed'] for r in report), len(recipe['targets']), len(pieces), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
