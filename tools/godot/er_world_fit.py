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

  surface: {"fit": "surface", "top": {...}, "side": {"band": [v0, v1], ...}, "plain": {...}, "plain_textures": [...],
        "roles": ["top", "side", "plain"], "offset": units, "smooth": degrees}
        the game's own triangles in the target in an Elden Ring material (what lies flat laid in world space, what stands a
        band of the texture run along it); with "overlay": true on the target and "offset", laid in front of the game's own
        surface, which stays drawn (no volume is left out); an overlay is cut
        by the game packet each triangle lies on, and each part is drawn only on frames the game drew that packet (a watch-only
        volume, kinds 4, naming the packet's figure: the game culls far packets, and an overlay drawn without them floats)
        "inlay": {"bands": [[d0, d1, "<key>"], ...], "offset", "band": {"<key>": [v0, v1]}, "above": z, "radial": bool} on a surface part - a worn inlay
        laid in the tops along their rims, each band d0..d1 units in from the rim in the material the part names by <key>
  loft: {"fit": "loft", "rings": [[z, half], ...], "spans": ["<key>", ...], "cap": "<key>", "turn": degrees, "sides": 4,
        "cx", "cy"} - a turned, tapered base made to a profile (the game's own, read from its triangles), each span in the
        material the part names by <key> (a "band" in it runs a frieze up the span, else "scale" lays it in world units)
  any surface entry or part: "relief": {"mode": "panels", "what": "panels" | "frames" | "figures", "z": [lo, hi], "cavity"}
        (or the smoothed-height measure) - a relief mask per vertex for the shader's gilding; "smooth_normals": degrees;
        "colour": [r, g, b] - the colour of a model the game draws in several passes, its vertex light kept round it
  "borrow": [{"volume": [...], "shift": [dx, dy, dz]}] on a target - its reference completed from a twin shape elsewhere
  "dump" may be a list (merged); "texture_means": `app er world info` reports - every corner of a piece carries the colour
        the game gave the surface nearest it (texture mean x vertex light), which the shader lights as the level's own
  "budget": triangles per surface; the meshes and pictures are baked by er_mesh_bake.gd (Godot, headless; --no-bake: not)

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
indices), OUT/<name>.v2 and .mesh.res (the baked mesh), OUT/tex/*.png and .tex.res, and with --pictures a top and a side view of each target's samples (green within, red over).
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
    """the dump's groups: name -> (triangles (n, 3, 3), kind, object, the game's vertex light per corner (n, 3, 3), 128 = 1,
    the texture's name); several dumps (a list) are merged"""
    if isinstance(path, list):
        out = {}
        for k, one in enumerate(path):
            out.update({'%d:%s' % (k, n): v for n, v in load_dump(one).items()})
        return out
    verts, cols, groups, cur = [], [], {}, None
    for line in open(path):
        if line.startswith('v '):
            a = line.split()
            verts.append([float(x) for x in a[1:4]])
            cols.append([float(x) for x in a[4:7]] if len(a) >= 7 else [128.0, 128.0, 128.0])
        elif line.startswith('g '):
            cur = line.split()[1]
            groups.setdefault(cur, [])
        elif line.startswith('f '):
            groups[cur].append([int(x) - 1 for x in line.split()[1:4]])
    v = np.array(verts, float)
    c = np.array(cols, float)
    out = {}
    for name, faces in groups.items():
        if not faces:
            continue
        parts = name.split('_')
        kind = int(parts[1][1:])
        obj = int(parts[2][1:])
        tex = name.split('_t', 1)[1].rsplit('_z', 1)[0] if '_t' in name else ''
        f = np.array(faces)
        out[name] = (v[f], kind, obj, c[f], tex)
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
    return {'level_' + name: (v[np.array(f)], 1, 0, None, '') for name, f in groups.items() if f and '_cell0_' not in name}


def reference(dump, vol, obj=None, means=None, with_colour=False):
    """what the game draws inside the volume: level draws lying wholly in it, models' triangles lying wholly in it; with
    with_colour also the colour the game gave each corner (its texture's mean times its vertex light, stored values 0..1:
    what the level's own shader multiplies its light by; `means`: texture name -> mean) and each triangle's texture"""
    tris, colours, names = [], [], []
    # a level draw is left out whole or not at all: every packet of it (the dump's groups d<draw>_..._m<packet>) inside
    draw_of = lambda name: name.split('_k', 1)[0]
    whole = {}
    for name, (t, kind, o, c, tex) in dump.items():
        if kind == 1:
            d = draw_of(name)
            whole[d] = whole.get(d, True) and bool(inside(t, vol).all())
    for name, (t, kind, o, c, tex) in dump.items():
        if not (vol[8] & kind) or (obj is not None and o != obj):
            continue
        ins = inside(t, vol).all(axis=1)
        if kind != 1:
            sel = ins
        elif whole.get(draw_of(name), False):
            sel = np.ones(len(t), bool)
        else:
            continue
        if not sel.any():
            continue
        tris.append(t[sel])
        if with_colour:
            m = np.array((means or {}).get(tex, [0.5, 0.5, 0.5]), float)
            vc = c[sel] if c is not None else np.full((int(sel.sum()), 3, 3), 128.0)
            colours.append(np.clip(m * vc / 128.0, 0.0, 1.0))
            names += [tex] * int(sel.sum())
    if not tris:
        z = np.zeros((0, 3, 3))
        return (z, z, []) if with_colour else z
    if with_colour:
        return np.concatenate(tris), np.concatenate(colours), names
    return np.concatenate(tris)


def watch_figures(dump, vols):
    """the level packets the game draws inside the volumes (draws lying wholly in one, as `reference`): figure (the dump's
    m<hex>) -> the middles of its triangles"""
    draw_of = lambda name: name.split('_k', 1)[0]
    out = {}
    for v in vols:
        whole = {}
        for name, (t, kind, o, c, tex) in dump.items():
            if kind == 1:
                whole[draw_of(name)] = whole.get(draw_of(name), True) and bool(inside(t, v).all())
        for name, (t, kind, o, c, tex) in dump.items():
            if kind == 1 and whole.get(draw_of(name)) and '_m' in name:
                out[name.split('_m', 1)[1].split('_')[0]] = t.mean(1)
    return out


def sub_mesh(m, sel):
    """the mesh's triangles `sel`, its vertices made compact"""
    i = m['i'][sel]
    used = np.unique(i)
    remap = np.full(len(m['p']), -1, np.int64)
    remap[used] = np.arange(len(used))
    out = dict(m, i=remap[i])
    for key, val in m.items():
        if key != 'i' and isinstance(val, np.ndarray) and len(val) == len(m['p']):
            out[key] = val[used]
    return out


def watch_groups(fitted, figs):
    """an overlay's meshes cut by the game packet each triangle lies on (the packet with the triangle nearest its middle): the
    game culls far packets one by one, so each part is drawn only on frames its own packet is: [(figure, [[meshes] per part])]"""
    names = sorted(figs)
    mids = np.concatenate([figs[k] for k in names])
    owner = np.concatenate([np.full(len(figs[k]), i) for i, k in enumerate(names)])
    tri_owner = []
    keys = set()
    for f in fitted:
        per = []
        for m in f:
            mid = m['p'][m['i']].mean(1)
            near = np.empty(len(mid), np.int64)
            for s0 in range(0, len(mid), 256):
                d = ((mid[s0:s0 + 256, None, :] - mids[None]) ** 2).sum(-1)
                near[s0:s0 + 256] = owner[d.argmin(1)]
            per.append(near)
            keys.update(near.tolist())
        tri_owner.append(per)
    out = []
    for key in sorted(keys):
        parts = []
        for f, per in zip(fitted, tri_owner):
            parts.append([sub_mesh(m, near == key) for m, near in zip(f, per) if (near == key).any()])
        out.append((names[key], parts))
    return out


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
    if part['fit'] == 'loft':
        # within the profile's half width at that height (in its turned frame; across the flats of a square)
        a = math.radians(float(part.get('turn', 0.0)))
        dx, dy = p[:, 0] - part['_cx'], p[:, 1] - part['_cy']
        x, y = dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a)
        zs = np.array([r[0] for r in part['rings']], float)
        hs = np.array([r[1] for r in part['rings']], float)
        order = np.argsort(zs, kind='stable')
        half = np.interp(p[:, 2], zs[order], hs[order])
        return (np.maximum(np.abs(x), np.abs(y)) < half - 0.5) & (p[:, 2] > zs.min() + 0.5) & (p[:, 2] < zs.max() - 0.3)
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


# ---- the game's own surface in an Elden Ring material, and what every piece takes from the game -----------------------------
def weld(points, eps=0.05):
    """one index per distinct position (within eps)"""
    key = np.round(points / eps).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return inverse.reshape(-1), points[first]


def face_normals(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-12)[:, None], a / 2.0


def smooth_corner_normals(t, fn, area, angle=40.0):
    """per corner: the area-weighted mean of the normals of the faces that share its position and turn from this corner's face
    by less than `angle` (a curved rim shades round, a step's edge stays sharp)"""
    corners = t.reshape(-1, 3)
    wid, _ = weld(corners)
    cf = np.repeat(np.arange(len(t)), 3)
    order = np.argsort(wid, kind='stable')
    out = np.zeros((len(corners), 3))
    cos_a = math.cos(math.radians(angle))
    bounds = np.flatnonzero(np.diff(np.r_[-1, wid[order], -2]))
    for s, e in zip(bounds[:-1], bounds[1:]):
        group = order[s:e]
        faces = cf[group]
        n = fn[faces]
        w = area[faces][:, None] * n
        close = (n @ n.T) >= cos_a
        out[group] = close.astype(float) @ w
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def ray_up_hits(p, t, fn):
    """per point: does a ray straight up from it meet one of the triangles that face up or down (a step's top over it)?"""
    sel = np.abs(fn[:, 2]) > 0.3
    tt = t[sel]
    hit = np.zeros(len(p), bool)
    if not len(tt):
        return hit
    a, b, c = tt[:, 0], tt[:, 1], tt[:, 2]
    for s in range(0, len(p), 512):
        q = p[s:s + 512][:, None, :]
        d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        d = np.where(np.abs(d) < 1e-9, 1e-9, d)
        l0 = ((b[:, 1] - c[:, 1]) * (q[..., 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (q[..., 1] - c[:, 1])) / d
        l1 = ((c[:, 1] - a[:, 1]) * (q[..., 0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (q[..., 1] - c[:, 1])) / d
        l2 = 1 - l0 - l1
        z = l0 * a[:, 2] + l1 * b[:, 2] + l2 * c[:, 2]
        hit[s:s + 512] = ((l0 >= 0) & (l1 >= 0) & (l2 >= 0) & (z > q[..., 2] + 0.2)).any(1)
    return hit


def surface_meshes(part, ref, ref_tex, centre, ground=None):
    """fit "surface": the game's own triangles inside the target, in an Elden Ring material - what faces up (a floor, a step's
    tread) in `top` (laid flat in world space, `scale` units a repeat), what stands (a step's riser, a rim) in `side` (a band of
    the texture, `band` [v0, v1], run along the riser and as tall as it), the textures named in `plain` (a tuft of the ground
    the game draws in the same piece) in the game's own colour alone.  The check then measures the game's surface against
    itself: 0."""
    t = ref.copy()
    fn, area = face_normals(t)
    keep = area > 1e-6
    t, fn, area = t[keep], fn[keep], area[keep]
    tex = [n for n, k in zip(ref_tex, keep) if k]
    # which side is out: up for what lies flat; for what stands, the side under no step's top (a riser's front looks over
    # the step below it; its back lies under the step above)
    flat = np.abs(fn[:, 2]) > 0.6
    fn[flat] *= np.sign(fn[flat, 2])[:, None]
    mid = t.mean(1)
    stand = np.flatnonzero(~flat)
    if len(stand):
        probe = mid[stand] + fn[stand] * 1.5
        inward = ray_up_hits(probe, t, fn)
        fn[stand[inward]] *= -1.0
        # (one under nothing either way: the side away from the target's centre)
        probe_b = mid[stand] - fn[stand] * 1.5
        both = ~inward & ~ray_up_hits(probe_b, t, fn)
        away = ((mid[stand] - centre)[:, :2] * fn[stand][:, :2]).sum(1) < 0
        fn[stand[both & away]] *= -1.0
    # winding to match
    raw = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    flip = (raw * fn).sum(1) < 0
    t[flip] = t[flip][:, [0, 2, 1]]
    plain = set(part.get('plain_textures', []))
    groups = {'top': flat & ~np.array([n in plain for n in tex], bool), 'side': ~flat & ~np.array([n in plain for n in tex], bool),
              'plain': np.array([n in plain for n in tex], bool)}
    meshes = []
    roles = part.get('roles', ['top', 'side', 'plain'])
    for k, (role, sel) in enumerate(groups.items()):
        if not sel.any() or role not in roles:
            continue
        tt, nf, ar = t[sel], fn[sel], area[sel]
        cn = smooth_corner_normals(tt, nf, ar, part.get('smooth', 40.0)).reshape(-1, 3, 3)
        mat = part.get(role, {})
        p = tt.reshape(-1, 3)
        relief = np.zeros(len(p))
        if role == 'side':
            band = mat.get('band', [0.0, 1.0])
            uv = band_uv(tt, nf, band, mat.get('repeat', 1.0))
            # (a riser's height, 0 at its foot .. 1 at its top edge: the shader's wear lightens the edge, darkens the foot)
            relief = 1.0 - (uv[:, 1] - band[0]) / max(band[1] - band[0], 1e-6)
        else:
            sc = float(mat.get('scale', 64.0))
            ang = math.radians(float(mat.get('turn', 0.0)))
            x = p[:, 0] * math.cos(ang) + p[:, 1] * math.sin(ang)
            y = -p[:, 0] * math.sin(ang) + p[:, 1] * math.cos(ang)
            uv = np.stack([x / sc, -y / sc], 1)
        n = cn.reshape(-1, 3)
        # an overlay (a frieze laid over the game's own riser, which stays drawn): a little in front of it
        p = p + n * float(part.get('offset', 0.0))
        meshes.append({'p': p, 'n': n, 'uv': uv, 'i': np.arange(len(p)).reshape(-1, 3), 'k': role,
                       'mat': {'name': role, 'textures': []}, 'role': role, 'relief': relief})
    if part.get('inlay') and groups['top'].any():
        # a worn inlay in the tops along their rims, the game's own engraving further in left as it is
        meshes += inlay_meshes(part['inlay'], t[groups['top']], float(part['inlay'].get('offset', 0.6)), ground, centre)
    return meshes


def band_uv(tt, nf, band, repeat):
    """a riser's texture: v from its foot to its top across the band, u along it (unrolled over the riser's connected faces,
    so a frieze runs on round a curved rim), the texture's aspect kept"""
    corners = tt.reshape(-1, 3)
    wid, wp = weld(corners, 0.1)
    nw = len(wp)
    # connected parts (faces sharing a welded corner)
    parent = np.arange(nw)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    tri_w = wid.reshape(-1, 3)
    for a, b, c in tri_w:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    comp = np.array([find(i) for i in range(nw)])
    v0, v1 = band
    u_w = np.zeros(nw)
    zlo, zhi = {}, {}
    for cid in np.unique(comp):
        ids = np.flatnonzero(comp == cid)
        zlo[cid], zhi[cid] = wp[ids, 2].min(), wp[ids, 2].max()
    # the horizontal tangent of each welded corner (from its faces' outward normals)
    tan = np.zeros((nw, 2))
    for f, (a, b, c) in enumerate(tri_w):
        h = np.array([-nf[f, 1], nf[f, 0]])
        for x in (a, b, c):
            tan[x] += h
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    # unroll: breadth first over the edges
    adj = [[] for _ in range(nw)]
    for a, b, c in tri_w:
        adj[a] += [b, c]; adj[b] += [a, c]; adj[c] += [a, b]
    seen = np.zeros(nw, bool)
    for start in range(nw):
        if seen[start]:
            continue
        seen[start] = True
        queue = [start]
        while queue:
            i = queue.pop(0)
            for j in adj[i]:
                if seen[j]:
                    continue
                seen[j] = True
                d = wp[j, :2] - wp[i, :2]
                tt2 = tan[i] + tan[j]
                tt2 /= max(np.linalg.norm(tt2), 1e-9)
                u_w[j] = u_w[i] + float(d @ tt2)
                queue.append(j)
    top_z = np.array([zhi[c] for c in comp])
    h = np.array([max(zhi[c] - zlo[c], 0.5) for c in comp])
    v = v0 + (v1 - v0) * (top_z - wp[:, 2]) / h
    u = u_w / h * (v1 - v0) * repeat
    return np.stack([u, v], 1)[wid]


def _levels_at(q, tt):
    """per point q (x, y, z): is there a flat triangle of tt over its (x, y) at about its height (same), one above it
    (higher), any at all?"""
    same = np.zeros(len(q), bool)
    higher = np.zeros(len(q), bool)
    anyz = np.zeros(len(q), bool)
    if not len(tt):
        return same, higher, anyz
    a, b, c = tt[:, 0], tt[:, 1], tt[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    for s in range(0, len(q), 256):
        p = q[s:s + 256][:, None, :]
        l0 = ((b[:, 1] - c[:, 1]) * (p[..., 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (p[..., 1] - c[:, 1])) / d
        l1 = ((c[:, 1] - a[:, 1]) * (p[..., 0] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (p[..., 1] - c[:, 1])) / d
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        z = l0 * a[:, 2] + l1 * b[:, 2] + l2 * c[:, 2]
        same[s:s + 256] = (inside & (np.abs(z - p[..., 2]) < 0.6)).any(1)
        higher[s:s + 256] = (inside & (z > p[..., 2] + 0.6)).any(1)
        anyz[s:s + 256] = inside.any(1)
    return same, higher, anyz


def inlay_meshes(spec, tt, offset, ground=None, centre=None):
    """a worn inlay laid in the tops along their rims (gate 6): for every edge of a top that falls away outside it (a step's
    or a platform's rim; not where a higher step rises, not inside a top), bands at set distances in from the rim -
    `bands`: [[d0, d1, "<material key>"], ...] - mitred round the rim's corners and curves, laid `offset` over the top.  A
    top (a connected tread) too narrow for the bands along most of its rim (a higher step or the fall within the last band)
    gets none at all, so a narrow step carries no broken pieces of it; the game's engraving further in is never covered."""
    bands = spec.get('bands', [])
    if not bands or not len(tt):
        return []
    deep = max(b[1] for b in bands)
    # only what lies level (a bevel down from a top is part of its fall, not of a tread)
    lvl = np.abs(np.cross(tt[:, 1] - tt[:, 0], tt[:, 2] - tt[:, 0]))
    lvl = lvl[:, 2] > 0.98 * np.linalg.norm(lvl, axis=1)
    tt = tt[lvl]
    if not len(tt):
        return []
    # every edge of every top, and its outward direction (in plane, away from its own triangle)
    e0 = np.concatenate([tt[:, 0], tt[:, 1], tt[:, 2]])
    e1 = np.concatenate([tt[:, 1], tt[:, 2], tt[:, 0]])
    opp = np.concatenate([tt[:, 2], tt[:, 0], tt[:, 1]])
    # the tops' connected parts (a tread, a platform, a raised disc): triangles sharing a corner
    cw, _ = weld(tt.reshape(-1, 3), 0.1)
    parent = np.arange(cw.max() + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in cw.reshape(-1, 3):
        ra = find(a)
        parent[find(b)] = ra
        parent[find(c)] = ra
    comp_tri = np.array([find(a) for a in cw.reshape(-1, 3)[:, 0]])
    comp = np.tile(comp_tri, 3)
    dvec = e1 - e0
    length = np.linalg.norm(dvec[:, :2], axis=1)
    ok = length > 0.2
    e0, e1, opp, dvec, length, comp = e0[ok], e1[ok], opp[ok], dvec[ok], length[ok], comp[ok]
    perp = np.stack([dvec[:, 1], -dvec[:, 0]], 1) / length[:, None]
    mid = (e0 + e1) / 2.0
    side = ((opp[:, :2] - mid[:, :2]) * perp).sum(1)
    perp *= np.where(side > 0, -1.0, 1.0)[:, None]          # (now pointing out, away from the triangle)
    out_pt = np.concatenate([mid[:, :2] + perp * 1.5, mid[:, 2:]], 1)
    same_out, higher_out, any_out = _levels_at(out_pt, tt)
    rim = ~same_out & ~higher_out                            # the top falls away outside this edge
    if ground is not None:
        # (where the game drew nothing of the target outside the edge - a draw the dump did not hold - the collision says
        # whether it falls away there or goes on at the same height)
        far = mid[:, :2] + perp * 6.0                      # (the collision's highest sample within 4 units: past the edge)
        g = ground.at(far[:, 0], far[:, 1])
        rim &= any_out | (g < out_pt[:, 2] - 0.6)
    if spec.get('above') is not None:
        rim &= mid[:, 2] > float(spec['above'])                # (only the tops over this height: not a ragged foot tier)
    if spec.get('radial') and centre is not None:
        # a round target (a dais): only edges facing out from its centre (an edge where the dump lacks a draw is not a rim)
        away = mid[:, :2] - np.asarray(centre)[None, :2]
        rim &= (away * perp).sum(1) > 0.7 * np.linalg.norm(away, axis=1)
    # the tread must hold the bands: at the deepest band (and a little more) still the same top, nothing higher - judged
    # per top: one that holds them along 80% of its rim's length carries them all round, else none
    fits = np.ones(len(e0), bool)
    for frac in (0.5, 1.0):
        in_pt = np.concatenate([mid[:, :2] - perp * (deep * frac + 0.75), mid[:, 2:]], 1)
        same_in, higher_in, _ = _levels_at(in_pt, tt)
        fits &= same_in & ~higher_in
    for c in np.unique(comp[rim]):
        sel = rim & (comp == c)
        if length[sel & fits].sum() < 0.8 * length[sel].sum():
            rim &= comp != c
    e0, e1, perp, length = e0[rim], e1[rim], perp[rim], length[rim]
    if not len(e0):
        return []
    # weld the rim's corners; per corner the inward direction mitred from its edges' (corners shared by two rim edges); an
    # edge drawn twice (a decal over the top) once
    wid, wp = weld(np.concatenate([e0, e1]), 0.1)
    a_id, b_id = wid[:len(e0)], wid[len(e0):]
    _, first = np.unique(np.stack([np.minimum(a_id, b_id), np.maximum(a_id, b_id)], 1), axis=0, return_index=True)
    first = np.sort(first)
    e0, e1, perp, length, a_id, b_id = e0[first], e1[first], perp[first], length[first], a_id[first], b_id[first]
    acc = np.zeros((len(wp), 2))
    np.add.at(acc, a_id, -perp)
    np.add.at(acc, b_id, -perp)
    cnt = np.bincount(np.concatenate([a_id, b_id]), minlength=len(wp))
    nrm = np.linalg.norm(acc, axis=1)
    inward = acc / np.maximum(nrm, 1e-9)[:, None]
    # mitre: 1 / cos(half the turn) (the mean of two unit vectors has length cos(half the turn)), clamped
    miter = np.where(cnt >= 2, 1.0 / np.clip(nrm / np.maximum(cnt, 1), 0.4, 1.0), 1.0)
    # u along the rim: each edge's own length, continued from a corner's running distance (a chain walked from its start)
    nxt = {}
    for k, (a, b) in enumerate(zip(a_id, b_id)):
        nxt.setdefault(int(a), []).append(k)
    u_at = {}
    has_prev = set(int(b) for b in b_id)
    starts = [int(a) for a in a_id if int(a) not in has_prev] + [int(a) for a in a_id]
    edge_u0 = np.zeros(len(e0))
    done = np.zeros(len(e0), bool)
    for s in starts:
        if s in u_at and all(done[k] for k in nxt.get(s, [])):
            continue
        u = u_at.get(s, 0.0)
        cur = s
        while True:
            ks = [k for k in nxt.get(cur, []) if not done[k]]
            if not ks:
                break
            k = ks[0]
            done[k] = True
            edge_u0[k] = u
            u += length[k]
            cur = int(b_id[k])
            u_at[cur] = u
    meshes = []
    up = np.array([0.0, 0.0, 1.0])
    for d0, d1, key in bands:
        p, uv = [], []
        band = spec.get('band', {}).get(key) if isinstance(spec.get('band'), dict) else None
        # u: a texture's repeat along the rim - a frieze's band keeps the texture's aspect (as band_uv), else 4 widths
        rep = (d1 - d0) / max(band[1] - band[0], 1e-6) if band else max(d1 - d0, 0.5) * 4.0
        for k in range(len(e0)):
            ia, ib = a_id[k], b_id[k]
            pa, pb = wp[ia], wp[ib]
            qa0 = pa[:2] + inward[ia] * d0 * miter[ia]
            qa1 = pa[:2] + inward[ia] * d1 * miter[ia]
            qb0 = pb[:2] + inward[ib] * d0 * miter[ib]
            qb1 = pb[:2] + inward[ib] * d1 * miter[ib]
            za, zb = pa[2] + offset, pb[2] + offset
            quad = [np.r_[qa0, za], np.r_[qb0, zb], np.r_[qb1, zb], np.r_[qa1, za]]
            ua, ub = edge_u0[k] / rep, (edge_u0[k] + length[k]) / rep
            quv = [(ua, 0.0), (ub, 0.0), (ub, 1.0), (ua, 1.0)]
            for tri in ((0, 1, 2), (0, 2, 3)):
                p += [quad[j] for j in tri]
                uv += [quv[j] for j in tri]
        p = np.array(p, float)
        uv = np.array(uv, float)
        # wind up
        t3 = p.reshape(-1, 3, 3)
        raw = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
        flip = raw[:, 2] < 0
        t3[flip] = t3[flip][:, [0, 2, 1]]
        uv3 = uv.reshape(-1, 3, 2)
        uv3[flip] = uv3[flip][:, [0, 2, 1]]
        p, uv = t3.reshape(-1, 3), uv3.reshape(-1, 2)
        if band:
            uv = np.stack([uv[:, 0], band[0] + (band[1] - band[0]) * uv[:, 1]], 1)
        meshes.append({'p': p, 'n': np.repeat(up[None], len(p), 0), 'uv': uv, 'i': np.arange(len(p)).reshape(-1, 3), 'k': key,
                       'mat': {'name': key, 'textures': []}, 'role': key,
                       'relief': np.clip(1.0 - np.abs(uv[:, 1] * 2.0 - 1.0) if not band else np.zeros(len(p)), 0.0, 1.0)})
    return meshes


def loft_meshes(part, vol):
    """fit "loft" (gate 6): a turned square (or `sides`-sided) base made from a profile - `rings`: [[z, half], ...] bottom to
    top, half the width across the flats, in the frame turned by `turn` - each span between two rings in the material named
    by `spans` (a key of the part, as a surface fit's top/side), hard edges at the corners; a cap on the last ring.  So a
    tapered, trimmed plinth is made to the game's own profile (read from its triangles), in the set's stone and gold."""
    cx, cy = part.get('cx', vol[0]), part.get('cy', vol[1])
    sides = int(part.get('sides', 4))
    rings = [(float(z), float(h)) for z, h in part['rings']]
    spans = part['spans']
    deg = float(part.get('turn', 0.0))
    # the corners of a ring of half width h across the flats
    ang = [math.radians(deg + 180.0 / sides + k * 360.0 / sides) for k in range(sides)]
    rad = 1.0 / math.cos(math.pi / sides)
    corner = lambda z, h, k: np.array([cx + h * rad * math.cos(ang[k % sides]), cy + h * rad * math.sin(ang[k % sides]), z])
    side_len = lambda h: 2.0 * h * math.tan(math.pi / sides)
    groups = {}
    slant = 0.0
    for s in range(len(rings) - 1):
        (z0, h0), (z1, h1) = rings[s], rings[s + 1]
        key = spans[s]
        mat = part.get(key, {})
        span_len = math.hypot(z1 - z0, h1 - h0)
        g = groups.setdefault(key, {'p': [], 'n': [], 'uv': [], 'r': []})
        for k in range(sides):
            a0, b0, a1, b1 = corner(z0, h0, k), corner(z0, h0, k + 1), corner(z1, h1, k), corner(z1, h1, k + 1)
            mid_ang = math.radians(deg + (k + 1) * 360.0 / sides)
            out = np.array([math.cos(mid_ang), math.sin(mid_ang), 0.0])
            # the face's normal: out, tilted by the taper (a ledge faces up)
            nrm = out * (z1 - z0) + np.array([0.0, 0.0, 1.0]) * (h0 - h1)
            nrm /= max(np.linalg.norm(nrm), 1e-9)
            if 'band' in mat:
                v0b, v1b = mat['band']
                hgt = max(span_len, 0.5)
                w0, w1 = side_len(h0), side_len(h1)
                u_a0, u_b0 = -w0 / 2 / hgt * (v1b - v0b), w0 / 2 / hgt * (v1b - v0b)
                u_a1, u_b1 = -w1 / 2 / hgt * (v1b - v0b), w1 / 2 / hgt * (v1b - v0b)
                quv = [(u_a0, v1b), (u_b0, v1b), (u_b1, v0b), (u_a1, v0b)]
            else:
                sc = float(mat.get('scale', 48.0))
                w0, w1 = side_len(h0), side_len(h1)
                quv = [(-w0 / 2 / sc, -slant / sc), (w0 / 2 / sc, -slant / sc), (w1 / 2 / sc, -(slant + span_len) / sc), (-w1 / 2 / sc, -(slant + span_len) / sc)]
            quad = [a0, b0, b1, a1]
            for tri in ((0, 1, 2), (0, 2, 3)):
                for j in tri:
                    g['p'].append(quad[j]); g['n'].append(nrm); g['uv'].append(quv[j]); g['r'].append(1.0 if j < 2 else 0.0)
        slant += span_len
    # the cap
    zc, hc = rings[-1]
    key = part.get('cap', spans[-1])
    g = groups.setdefault(key, {'p': [], 'n': [], 'uv': [], 'r': []})
    sc = float(part.get(key, {}).get('scale', 48.0))
    centre = np.array([cx, cy, zc])
    for k in range(sides):
        for q in (centre, corner(zc, hc, k), corner(zc, hc, k + 1)):
            g['p'].append(q); g['n'].append(np.array([0.0, 0.0, 1.0])); g['uv'].append(((q[0] - cx) / sc, (q[1] - cy) / sc)); g['r'].append(0.5)
    meshes = []
    for key, g in groups.items():
        p = np.array(g['p'], float)
        n = np.array(g['n'], float)
        uv = np.array(g['uv'], float)
        t3 = p.reshape(-1, 3, 3)
        raw = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
        flip = (raw * n.reshape(-1, 3, 3)[:, 0]).sum(1) < 0
        t3[flip] = t3[flip][:, [0, 2, 1]]
        uv3 = uv.reshape(-1, 3, 2)
        uv3[flip] = uv3[flip][:, [0, 2, 1]]
        r3 = np.array(g['r'], float).reshape(-1, 3)
        r3[flip] = r3[flip][:, [0, 2, 1]]
        meshes.append({'p': t3.reshape(-1, 3), 'n': n, 'uv': uv3.reshape(-1, 2), 'i': np.arange(len(p)).reshape(-1, 3), 'k': key,
                       'mat': {'name': key, 'textures': []}, 'role': key, 'relief': r3.reshape(-1)})
    return meshes


def closest_on_triangles(p, tris, pn=None, chunk=1024):
    """per point: the nearest triangle (a normal that disagrees costs as much as 6 units) and the barycentric weights of the
    nearest point on it"""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    fn, _ = face_normals(tris)
    best_k = np.zeros(len(p), int)
    best_w = np.zeros((len(p), 3))
    for s in range(0, len(p), chunk):
        q = p[s:s + chunk]
        # nearest point by clamped barycentric projection (good enough for weights; distance by the exact routine below)
        ab, ac, aq = b - a, c - a, q[:, None, :] - a
        d00, d01, d11 = (ab * ab).sum(-1), (ab * ac).sum(-1), (ac * ac).sum(-1)
        d20, d21 = (aq * ab).sum(-1), (aq * ac).sum(-1)
        den = np.maximum(d00 * d11 - d01 * d01, 1e-12)
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        v, w = np.clip(v, 0, 1), np.clip(w, 0, 1)
        over = v + w > 1
        tot = np.where(over, v + w, 1.0)
        v, w = v / tot, w / tot
        u = 1 - v - w
        cp = a * u[..., None] + b * v[..., None] + c * w[..., None]
        dist = np.linalg.norm(q[:, None, :] - cp, axis=-1)
        if pn is not None:
            dist = dist + 6.0 * (1.0 - np.abs((pn[s:s + chunk][:, None, :] * fn).sum(-1)))
        k = dist.argmin(1)
        r = np.arange(len(q))
        best_k[s:s + chunk] = k
        best_w[s:s + chunk] = np.stack([u[r, k], v[r, k], w[r, k]], 1)
    return best_k, best_w


def game_colour(points, normals, ref, ref_col):
    """the colour the game gave the surface nearest each point (stored values: texture mean x vertex light)"""
    if not len(ref):
        return np.full((len(points), 3), 0.5)
    k, w = closest_on_triangles(points, ref, normals)
    return (ref_col[k] * w[..., None]).sum(1)


def relief_mask(p, i, n, iters=12, lo=0.15, hi=0.85):
    """per vertex: how far it stands out of its smoothed surroundings (a relief's raised figures, a moulding's crest), 0..1 -
    smooth across the triangles (no facet of the mesh shows in it); lo/hi: the share of the range taken as none and as all"""
    wid, wp = weld(p, 0.02)
    tri = wid[i]
    nw = len(wp)
    acc = np.zeros((nw, 3))
    cnt = np.zeros(nw)
    sm = wp.copy()
    for _ in range(iters):
        acc[:] = 0
        cnt[:] = 0
        for a, b in ((0, 1), (1, 2), (2, 0)):
            np.add.at(acc, tri[:, a], sm[tri[:, b]]); np.add.at(cnt, tri[:, a], 1)
            np.add.at(acc, tri[:, b], sm[tri[:, a]]); np.add.at(cnt, tri[:, b], 1)
        sm = 0.5 * sm + 0.5 * acc / np.maximum(cnt, 1)[:, None]
    wn = np.zeros((nw, 3))
    np.add.at(wn, wid, n)
    wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
    h = ((wp - sm) * wn).sum(1)
    q0, q1 = np.percentile(h, [100 * lo, 100 * hi])
    m = np.clip((h - q0) / max(q1 - q0, 1e-6), 0, 1)
    # one pass of smoothing of the mask itself
    acc1 = np.zeros(nw); cnt[:] = 0
    for a, b in ((0, 1), (1, 2), (2, 0)):
        np.add.at(acc1, tri[:, a], m[tri[:, b]]); np.add.at(cnt, tri[:, a], 1)
    m = 0.5 * m + 0.5 * acc1 / np.maximum(cnt, 1)
    return m[wid]


def relief_in_panels(p, i, n, radius=4.0, lo=0.3, hi=0.75, frame=0.12, what='figures', zband=(0.0, 1.0)):
    """per vertex: how far it stands up out of the sunk panel it lies in (a relief's figures: 1 at their crests, 0 on the
    panel's ground and on the frame round it, which is the piece's outer face) - from the piece's own outer extent at that
    height and facing (eight directions), so a tapering shaft's panels are found as well; smooth across the triangles"""
    wid, wp = weld(p, 0.02)
    wn = np.zeros((len(wp), 3))
    np.add.at(wn, wid, n)
    wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
    dirs = np.array([[math.cos(a), math.sin(a), 0.0] for a in np.arange(8) * math.pi / 4])
    side = np.argmax(wn @ dirs.T, axis=1)
    facing = (wn @ dirs.T).max(1) > 0.5
    recess = np.zeros(len(wp))
    z = wp[:, 2]
    for k, d in enumerate(dirs):
        sel = np.flatnonzero(side == k)
        if not len(sel):
            continue
        proj = wp[sel] @ d
        # the outer extent: the furthest a vertex of this face reaches this way within 3 units of height
        near_z = np.abs(z[sel][:, None] - z[sel][None, :]) < 3.0
        ext = np.where(near_z, proj[None, :], -1e9).max(1)
        recess[sel] = ext - proj
    recess[~facing] = 0.0
    # the panel's ground: the deepest point within `radius` of the vertex on the same face
    ground = np.zeros(len(wp))
    for k in range(8):
        sel = np.flatnonzero((side == k) & facing)
        if not len(sel):
            continue
        q = wp[sel]
        dd = np.linalg.norm(q[:, None, :] - q[None, :, :], axis=-1) < radius
        ground[sel] = np.where(dd, recess[sel][None, :], 0.0).max(1)
    height = ground - recess
    if what == 'panels':
        # the sunk panels whole, their carving with them: one field of metal per panel, its figures standing in it
        m = ((ground > 0.3) & (recess >= frame * np.maximum(ground, 1e-6))).astype(float)
    elif what == 'frames':
        # the frames round the sunk panels (the outer face where a panel lies within `radius`): mouldings, clean bands
        m = ((ground > 0.3) & (recess < frame * np.maximum(ground, 1e-6))).astype(float)
    else:
        m = np.where(ground > 0.15, np.clip((height / np.maximum(ground, 1e-6) - lo) / max(hi - lo, 1e-6), 0, 1), 0.0)
        m[recess < frame * np.maximum(ground, 1e-6)] = 0.0     # (the frame: the outer face itself)
    # (only within zband: the share of the piece's height its panels take - not its cap, not its plain foot)
    zf = (z - z.min()) / max(float(z.max() - z.min()), 1e-6)
    m[(zf < zband[0]) | (zf > zband[1])] = 0.0
    m = m * m * (3 - 2 * m)
    # and how deep each vertex lies (0 on the outer face .. 1 at the deepest ground): the cavity the light reaches less
    depth = np.clip(recess / max(float(np.percentile(recess[recess > 0.05], 90)) if (recess > 0.05).any() else 1.0, 1e-6), 0, 1)
    return m[wid], depth[wid]


def smooth_normals_welded(p, i, n, angle):
    """a model's normals made smooth across its split corners (a relief carved in few triangles shades round), keeping edges
    sharper than `angle`"""
    t = p[i]
    fn, area = face_normals(t)
    vn = n[i].mean(1)
    fn *= np.where((fn * vn).sum(1) < 0, -1.0, 1.0)[:, None]
    cn = smooth_corner_normals(t, fn, area, angle)
    out = np.zeros_like(n)
    cnt = np.zeros(len(n))
    np.add.at(out, i.reshape(-1), cn)
    np.add.at(cnt, i.reshape(-1), 1)
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    return np.where(cnt[:, None] > 0, out, n)


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


def dedupe(tris, *more):
    """triangles that two volumes both hold, once"""
    if not len(tris):
        return (tris,) + more
    key = np.round(np.sort(tris.reshape(len(tris), 3, 3), axis=1).reshape(len(tris), 9) * 4).astype(np.int64)
    _, first = np.unique(key, axis=0, return_index=True)
    first = np.sort(first)
    return (tris[first],) + tuple(m[first] if isinstance(m, np.ndarray) else [m[k] for k in first] for m in more)


def texture_means(paths):
    """texture name -> its mean colour (stored values), from `app er world info FILE` reports"""
    means = {}
    for path in ([paths] if isinstance(paths, str) else paths or []):
        for t in json.load(open(path)).get('textures', []):
            means[t['name']] = t['mean']
    return means


def write_v2(path, surfaces):
    """the mesh for er_mesh_bake.gd: per surface its own corners (position, normal, uv, colour) and triangles"""
    with open(path, 'wb') as fh:
        fh.write(np.array([0x32425245, len(surfaces)], np.int32).tobytes())
        for m in surfaces:
            P, N, U, C, I = m['p'], m['n'], m['uv'], m['c'], m['i']
            fh.write(np.array([len(P), I.size, int(m.get('budget', 0))], np.int32).tobytes())
            fh.write(P.astype(np.float32).tobytes()); fh.write(N.astype(np.float32).tobytes())
            fh.write(U.astype(np.float32).tobytes()); fh.write(C.astype(np.float32).tobytes())
            fh.write(I.astype(np.int32).tobytes())


def godot_binary():
    return os.environ.get('RTA_GODOT', os.path.join(HERE, '..', '..', 'local', 'godot-spike', 'deps', 'godot-editor', 'Godot.app',
                                                    'Contents', 'MacOS', 'Godot'))


def bake(out, jobs):
    """er_mesh_bake.gd: the meshes made lighter (a budget of triangles each, and lower levels of detail under it, with
    tangents) and the pictures with their mip maps, as Godot's own resources: the game reads them on a worker thread"""
    if not jobs:
        return
    work = os.path.join(out, '.bake')
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, 'project.godot'), 'w') as fh:
        fh.write('config_version=5\n')
    job = os.path.join(work, 'jobs.json')
    json.dump(jobs, open(job, 'w'))
    import subprocess
    r = subprocess.run([godot_binary(), '--headless', '--path', work, '--script', os.path.join(HERE, 'er_mesh_bake.gd'), '--', job],
                       capture_output=True, text=True, timeout=1800)
    lines = [l for l in r.stdout.splitlines() if l.startswith('er_mesh_bake')]
    print('\n'.join(lines[-40:]))
    if r.returncode != 0 or not lines or 'done' not in lines[-1]:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit('er_mesh_bake failed')


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
    means = texture_means(recipe.get('texture_means'))
    ground = Ground(recipe['world']) if recipe.get('world') else None
    index = json.load(open(recipe['material_index'])) if recipe.get('material_index') else {}
    out = recipe['out']
    os.makedirs(os.path.join(out, 'tex'), exist_ok=True)
    if pics:
        os.makedirs(pics, exist_ok=True)
    pieces, volumes, report, jobs, baked_tex = [], [], [], [], set()
    for target in recipe['targets']:
        vols = target.get('volumes') or [target['volume']]
        vol = vols[0]
        got = [reference(dump, v, target.get('object'), means, True) for v in vols]
        ref = np.concatenate([g[0] for g in got])
        ref_col = np.concatenate([g[1] for g in got])
        ref_tex = sum([g[2] for g in got], [])
        for b in target.get('borrow', []):
            # a shape the dump holds only in part, taken whole from its twin elsewhere in the level (shifted): the east dais
            # from the west one (every corner of the east dais's own draws lies on the west's moved over)
            br, bc, bt = reference(dump, b['volume'], target.get('object'), means, True)
            ref = np.concatenate([ref, br + np.asarray(b['shift'], float)[None, None]])
            ref_col = np.concatenate([ref_col, bc])
            ref_tex = ref_tex + bt
        ref, ref_col, ref_tex = dedupe(ref, ref_col, ref_tex)
        centre = ref.reshape(-1, 3).mean(0) if len(ref) else np.array(vol[:3], float)
        fitted, fits = [], []
        for part in target['parts']:
            if part['fit'] == 'surface':
                f = surface_meshes(part, ref, ref_tex, centre, ground)
                info = {'surface': len(ref)}
            elif part['fit'] == 'loft':
                f = loft_meshes(part, vol)
                info = {'loft': len(part['rings'])}
            else:
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
        overlay = bool(target.get('overlay'))
        if not overlay:
            volumes.extend(vols)
            groups = [('', fitted, None)]
        else:
            # cut by the game's packets it lies on, each part watching its own (a watch-only volume naming the packet; its box
            # the part's own, for the record)
            figs = watch_figures(dump, vols)
            groups = []
            for fig, parts in watch_groups(fitted, figs):
                pts = np.concatenate([m['p'] for ms in parts for m in ms])
                lo, hi = pts.min(0), pts.max(0)
                wi = len(volumes)
                volumes.append([round(float(x), 2) for x in (lo + hi) / 2] + [round(float(x), 2) for x in (hi - lo) / 2 + 1.0] + [0, 0, 5, [fig]])
                groups.append(('-w%d' % len(groups), parts, wi))
            print('%-12s watched by %d packets' % (target['name'], len(groups)))
        # the light the game gave the shape (its mean): the measure a metal's brightness follows
        light_ref = (ref_col.reshape(-1, 3).mean(0) if len(ref_col) else np.array([0.5, 0.5, 0.5])).round(4).tolist()
        if target.get('colour'):
            light_ref = list(target['colour'])
        for suffix, group, watch in groups:
            for k, (part, f) in enumerate(zip(target['parts'], group)):
                if not f:
                    continue
                name = '%s-%d%s' % (target['name'], k, suffix)
                pos, nrm, uvs, idx, surfaces, v2 = [], [], [], [], [], []
                base = 0
                for m in f:
                    mat = dict(m['mat'])
                    entry = index.get(mat['name'], {})
                    mat['_textures'] = [t['path'] for t in mat.get('textures', []) if t.get('path')] + entry.get('tex', [])
                    albedo, normal = texture_pair(mat, recipe['textures'])
                    surf = {'first': int(sum(len(x) for x in idx)) * 3, 'count': int(len(m['i'])) * 3}
                    # the recipe's own say over this mesh's material (see "surfaces" above): other textures, a metal or mask
                    # map, shader values, its own tint; for a "surface" part, its top, side and plain
                    if m.get('role'):
                        over = dict(part.get(m['role'], {}))
                        albedo = normal = None
                    else:
                        over = dict(part.get('surfaces', {}).get('*', {}), **part.get('surfaces', {}).get(str(m['k']), {}))
                    named = lambda b: os.path.join(recipe['textures'], b + '.png') if b else None
                    if over.get('albedo'):
                        albedo = named(over['albedo'])
                    if over.get('normal'):
                        normal = named(over['normal'])
                    maps = [('albedo', albedo), ('normal', normal)] + [(k2, named(over[k2])) for k2 in ('metal', 'mask') if over.get(k2)]
                    params = dict(part.get('params', {}), **over.get('params', {}))
                    if params:
                        surf['params'] = params
                    if 'tint' in over:
                        surf['tint'] = over['tint']
                    for key, src in maps:
                        if src:
                            dst = os.path.join(out, 'tex', os.path.basename(src))
                            if not os.path.exists(dst):
                                (write_normal if key == 'normal' else write_picture)(src, dst)
                            surf[key] = 'tex/' + os.path.basename(src)
                            res_name = 'tex/' + os.path.splitext(os.path.basename(src))[0] + '.tex.res'
                            surf[key + '_res'] = res_name
                            if res_name not in baked_tex:
                                baked_tex.add(res_name)
                                jobs.append({'texture': os.path.abspath(dst), 'out': os.path.abspath(os.path.join(out, res_name))})
                            if key == 'albedo':
                                surf['albedo_mean'] = [round(float(x), 4) for x in np.asarray(Image.open(src).convert('RGB').resize((32, 32))).reshape(-1, 3).mean(0) / 255.0]
                    # what every piece takes from the game: the colour it gave the surface here (per corner), and a relief's
                    # raised parts (for a gilding); normals made smooth where asked
                    n = m['n']
                    if part.get('smooth_normals') or over.get('smooth_normals'):
                        n = smooth_normals_welded(m['p'], m['i'], n, float(over.get('smooth_normals', part.get('smooth_normals', 50.0))))
                    col = game_colour(m['p'], n, ref, ref_col)
                    fixed = over.get('colour', part.get('colour', target.get('colour')))
                    if fixed:
                        # a model the game draws in several passes (its colour is not one texture's): the colour given, with
                        # the game's light and dark over the shape kept round it
                        lum = col @ np.array([0.3, 0.59, 0.11])
                        col = np.array(fixed, float)[None] * np.clip(lum / max(float(lum.mean()), 1e-3), 0.3, 2.0)[:, None]
                    rel = m.get('relief', np.zeros(len(m['p'])))
                    g = over.get('relief') or part.get('relief')
                    if g and g.get('mode') == 'panels':
                        rel, depth = relief_in_panels(m['p'], m['i'], n, float(g.get('radius', 4.0)), float(g.get('lo', 0.3)), float(g.get('hi', 0.75)),
                                               float(g.get('frame', 0.12)), g.get('what', 'figures'), tuple(g.get('z', (0.0, 1.0))))
                        col = col * (1.0 - float(g.get('cavity', 0.3)) * depth)[:, None]
                    elif g:
                        rel = relief_mask(m['p'], m['i'], n, int(g.get('iters', 12)), float(g.get('lo', 0.15)), float(g.get('hi', 0.85)))
                    surf['game_light'] = True
                    surfaces.append(surf)
                    pos.append(m['p']); nrm.append(n); uvs.append(m['uv']); idx.append(m['i'] + base)
                    base += len(m['p'])
                    v2.append({'p': m['p'], 'n': n, 'uv': m['uv'], 'c': np.concatenate([col, rel[:, None]], 1), 'i': m['i'],
                               'budget': int(over.get('budget', part.get('budget', target.get('budget', recipe.get('budget', 20000)))))})
                with open(os.path.join(out, name + '.bin'), 'wb') as fh:
                    P, N, U, I = np.concatenate(pos), np.concatenate(nrm), np.concatenate(uvs), np.concatenate(idx)
                    fh.write(np.array([len(P), len(I) * 3], np.int32).tobytes())
                    fh.write(P.astype(np.float32).tobytes()); fh.write(N.astype(np.float32).tobytes()); fh.write(U.astype(np.float32).tobytes())
                    fh.write(I.astype(np.int32).tobytes())
                write_v2(os.path.join(out, name + '.v2'), v2)
                jobs.append({'mesh': os.path.abspath(os.path.join(out, name + '.v2')), 'out': os.path.abspath(os.path.join(out, name + '.mesh.res'))})
                pieces.append({'name': name, 'mesh': name + '.bin', 'mesh_res': name + '.mesh.res', 'volume': -1 if overlay else vi,
                               'volumes': [] if overlay else list(range(vi, vi + len(vols))), 'surfaces': surfaces, 'tint': target.get('tint', 0.6),
                               'light_ref': light_ref, 'triangles': int(len(I))})
                if watch is not None:
                    pieces[-1]['watch'] = [watch]
    if '--no-bake' not in sys.argv:
        bake(out, jobs)
    json.dump({'level': recipe['level'], 'tolerance': tol, 'volumes': volumes, 'pieces': pieces, 'check': report},
              open(os.path.join(out, 'rebuild.json'), 'w'), indent=1)
    print('%d of %d targets passed; %d pieces written to %s' % (sum(r['passed'] for r in report), len(recipe['targets']), len(pieces), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
