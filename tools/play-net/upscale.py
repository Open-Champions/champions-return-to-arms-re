#!/usr/bin/env python3
"""Enlarges the textures the playable build has written out, for its replacement folder.

    tools/play-net/upscale.py DUMP_DIR REPLACE_DIR --upscaler /path/to/realesrgan-ncnn-vulkan
                              [--scale 4|2] [--only TEXT] [--force] [--list] [--jobs N] [--limit N]
                              [--names FILE] [--check] [--from-pack REPLACE_DIR_4X]

DUMP_DIR is `<textures>/dump` of runs with `--rta-texture-dump`, REPLACE_DIR is
`<textures>/replace` (tools/play-net/README.md, "Texture dump and replacement" and
"Upscaled art"). Each picture is written to REPLACE_DIR under the same name, four (or two)
times the size. The enlarging itself is done by Real-ESRGAN
(https://github.com/xinntao/Real-ESRGAN, the ncnn-vulkan program and its models; not part
of this repository). What this script adds is what the game's pictures need around it. It
does not guess: beside every dumped picture the application writes a `.json` file saying
how the game draws with it, and that decides what is done.

- **Two-field interface pictures** (drawn under the scanline mask, the two halves over the
  same place): the two halves are interleaved into the one picture they are, that is
  enlarged, and the file gets the whole enlarged picture *twice*, one above the other, at
  twice the vertical factor. Each of the game's two draws then finds the right line of the
  enlarged picture behind every line of the screen, whatever its mask (see the README).
- **Alpha** keeps the console's scale (128 is opaque). What it means is read from the
  blend mode and the alpha test the picture was drawn with: where texels cannot be seen
  (transparent interface art, cut-out leaves) their colour is replaced by that of their
  visible neighbours before enlarging, so that no dark or coloured fringe comes out of the
  enlarged edge; where alpha 0 is opaque (level and model textures) colour is left alone.
  A texel is hidden only when every way of drawing in the `.json` file hides it; a file
  that does not come from seeing the picture drawn hides nothing; and colour is replaced
  only within BLEED texels of visible ones.
- **Self-check**: every finished picture, made small again, is compared with the game's
  texels; a picture whose colour has moved where the game shows it is named (`LOOK AT`).
  `--check` does that for a finished pack without enlarging anything.
- **Texels the game never sent** (whole blocks of zeros in a picture the application says
  is not whole) are filled from their neighbours and stay filled: no triangle uses them,
  but a filter reads across their border.
- **Only what is drawn with is given to the model**: the rectangle of texel coordinates
  the game used (plus a margin); the rest of the picture is enlarged plainly. A later run
  does a picture again when its rectangle has grown.
- **Faithful colour**: the model's picture is mixed with a plain (bicubic) enlargement and
  then given the plain one's colour and brightness at every place (everything coarser than
  a texel and a half), and for level textures also its distribution of brightness; then
  every pixel is held inside the range of the texels around it. A picture cannot come out
  darker or more saturated than the game's, and a thin line does not become a thinner,
  brighter one.
- **Noise is left alone**: where a picture is noise from texel to texel (grass, mottled
  fills) a model draws worms; the strength is lowered there. Pictures with a side under
  12 texels (the interface's bars) and model textures of fewer than 2,048 texels are
  enlarged plainly.
- **Per kind of picture** a model and a strength (RECIPES below; chosen by eye, see the
  README).

Incremental: REPLACE_DIR/upscale-manifest.json remembers what each file was made from;
only new and changed pictures are done, `--jobs N` batches at a time (a whole game is
some 130,000 pictures); a run that is stopped keeps what it has written. A 2x pack can be
made from a finished 4x pack by halving its pictures (`--scale 2 --from-pack DIR`). The dumps and everything made from them are the
game's art: keep both folders out of any repository. Needs Python 3 with numpy and Pillow.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

VERSION = 8          # of the recipes: a change redoes every picture
PAD = 8              # texels of border given to the model around what it enlarges
MARGIN = 6           # texels around the rectangle the game draws with
MODEL_SCALE = 4      # what the models make; --scale 2 reduces that afterwards
BLOCKS = {19: (16, 16), 20: (32, 16), 0: (8, 8)}     # GS block size in texels, by format

X4 = 'realesrgan-x4plus'
ANIME = 'realesrgan-x4plus-anime'
VIDEO = 'realesr-animevideov3-x4'

# kind -> model for colour; strength (0 plain enlargement .. 1 the model's picture); calm:
# how much of the strength is taken away where the picture is texel noise (grass, the
# mottled fill of bars: a model draws worms there); tone: whether the distribution of
# brightness is matched too; alpha_model: model for alpha (None: enlarged plainly)
RECIPES = {
    'interface': dict(model=X4, strength=1.0, calm=0.8, tone=False, alpha_model=None),
    'level':     dict(model=X4, strength=1.0, calm=0.6, tone=True, alpha_model=None),
    'model':     dict(model=X4, strength=1.0, calm=0.8, tone=False, alpha_model=None),
    'glow':      dict(model=VIDEO, strength=0.6, calm=0.8, tone=False, alpha_model=None),
    'sprite':    dict(model=X4, strength=0.8, calm=0.8, tone=False, alpha_model=None),
}
RANGE_SLACK = 6      # how far a result may leave the range of the texels around it
SMALLEST = 12        # a picture with a side shorter than this gives a model nothing to go by
# ... and so does a model texture of fewer texels than this (16 x 16 to 32 x 48: item and
# hair pictures whose every feature is a texel or two; the model drew other shapes from them
# and flattened their mottle. From 48 x 48 on it follows what is there)
FEWEST = {'model': 2048}
BLEED = 3            # texels: how far into what cannot be seen colour is replaced
MOVED = 16           # of 255: the self-check's "this colour is no longer the game's"


# ---- small picture arithmetic (numpy only) ---------------------------------------------

def box_blur_axis(a, radius, axis):
    if radius <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (radius + 1, radius)
    total = np.cumsum(np.pad(a, pad, mode='edge'), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    high, low = [slice(None)] * a.ndim, [slice(None)] * a.ndim
    high[axis], low[axis] = slice(2 * radius + 1, 2 * radius + 1 + n), slice(0, n)
    return ((total[tuple(high)] - total[tuple(low)]) / (2 * radius + 1)).astype(np.float32)


def blur(a, sigma):
    """About a Gaussian of `sigma` pixels (three box blurs)."""
    radius = max(1, int(round(sigma * 0.87)))
    a = a.astype(np.float32)
    for _ in range(3):
        a = box_blur_axis(box_blur_axis(a, radius, 0), radius, 1)
    return a


def resize(a, scale, method=Image.LANCZOS):
    """A float picture (H x W or H x W x 3) enlarged by a whole factor, channel by channel."""
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 3:
        return np.dstack([resize(a[..., i], scale, method) for i in range(a.shape[2])])
    image = Image.fromarray(a, 'F')
    return np.asarray(image.resize((a.shape[1] * scale, a.shape[0] * scale), method), dtype=np.float32)


def reduce_by(a, factor):
    """A float picture made `factor` times smaller (box average)."""
    if factor == 1:
        return a
    h, w = a.shape[0] // factor, a.shape[1] // factor
    shape = (h, factor, w, factor) + a.shape[2:]
    return a[:h * factor, :w * factor].reshape(shape).mean(axis=(1, 3)).astype(np.float32)


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def match_low(picture, reference, sigma):
    """`picture` with everything coarser than `sigma` taken from `reference`."""
    return picture + blur(reference, sigma) - blur(picture, sigma)


def match_tone(picture, reference):
    """`picture` with its distribution of brightness made that of `reference`."""
    y, target = luma(picture), np.sort(luma(reference), axis=None)
    order = np.argsort(y, axis=None)
    out = np.empty(order.size, dtype=np.float32)
    out[order] = target[np.linspace(0, target.size - 1, order.size).astype(np.int64)]
    return picture + (out.reshape(y.shape) - y)[..., None]


def noisiness(rgb, sigma=2.0):
    """0..1 for every texel: how much the picture around it is noise from texel to texel
    and not shapes. Differences between neighbours are compared with differences across
    two texels: for noise the first have four times the energy, for anything drawn with
    a brush about as much."""
    y = luma(rgb.astype(np.float32))
    p = np.pad(y, 1, mode='edge')
    wide_x, wide_y = (p[1:-1, 2:] - p[1:-1, :-2]) * 0.5, (p[2:, 1:-1] - p[:-2, 1:-1]) * 0.5
    near_x, near_y = p[1:-1, 2:] - p[1:-1, 1:-1], p[2:, 1:-1] - p[1:-1, 1:-1]
    wide = blur(wide_x * wide_x + wide_y * wide_y, sigma)
    near = blur(near_x * near_x + near_y * near_y, sigma)
    ratio = near / (wide + 4.0)
    return (np.clip((ratio - 2.6) / 1.0, 0.0, 1.0) * np.clip(near / 150.0, 0.0, 1.0)).astype(np.float32)


def local_range(rgb, scale):
    """Smallest and largest value among each texel and its neighbours, enlarged."""
    a = rgb.astype(np.float32)
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode='edge')
    h, w = a.shape[:2]
    around = np.stack([p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)])
    low, high = around.min(axis=0), around.max(axis=0)
    return resize(low, scale, Image.BILINEAR), resize(high, scale, Image.BILINEAR)


def fill_from_neighbours(rgb, known):
    """Colour of the unknown texels taken from the nearest known ones."""
    if known.all() or not known.any():
        return rgb.astype(np.float32)
    out = rgb.astype(np.float32).copy()
    known = known.copy()
    h, w = known.shape
    for step in range(48):
        if known.all():
            break
        # the eight neighbours of every texel, taken as slices of a picture with a border
        # of nothing round it (in the order the first version of this added them up)
        values = np.pad(out * known[..., None], ((1, 1), (1, 1), (0, 0)))
        sources = np.pad(known, 1).astype(np.float32)
        total = np.zeros_like(out)
        count = np.zeros(known.shape, dtype=np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            total += values[1 - dy:1 - dy + h, 1 - dx:1 - dx + w]
            count += sources[1 - dy:1 - dy + h, 1 - dx:1 - dx + w]
        grow = (~known) & (count > 0)
        if not grow.any():
            break
        out[grow] = total[grow] / count[grow][:, None]
        known |= grow
    if not known.all():
        out[~known] = out[known].mean(axis=0)      # far from everything: the average
    return out


def grow(mask, texels):
    """A mask made larger by so many texels in every direction."""
    for _ in range(texels):
        p = np.pad(mask, 1, mode='edge')
        h, w = mask.shape
        mask = np.any([p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)], axis=0)
    return mask


def weave(a, rows):
    """The two fields a[0:rows] and a[rows:2*rows] as one picture of 2*rows lines."""
    out = np.empty((2 * rows,) + a.shape[1:], dtype=a.dtype)
    out[0::2] = a[:rows]
    out[1::2] = a[rows:2 * rows]
    return out


# ---- what the application wrote beside the picture -------------------------------------

def alpha_weight(states):
    """For every alpha value 0..255: how much of a texel's colour reaches the screen in
    the way of drawing that shows most of it (0: such a texel is never seen)."""
    values = np.arange(256, dtype=np.float32)
    source_alpha = values / 128.0
    best = np.zeros(256, dtype=np.float32)
    for state in states:
        weight = np.ones(256, dtype=np.float32)
        if state.get('tcc', 1) == 0:
            pass                                    # the texture's alpha is not used at all
        else:
            if state['abe']:
                a, b, c, d = state['alpha'] & 3, (state['alpha'] >> 2) & 3, (state['alpha'] >> 4) & 3, (state['alpha'] >> 6) & 3
                factor = source_alpha if c == 0 else (np.full(256, state['fix'] / 128.0, dtype=np.float32) if c == 2 else np.ones(256, dtype=np.float32))
                weight = np.clip(np.abs(((a == 0) - (b == 0)) * factor + (d == 0)), 0.0, 1.0)
            test = state['test']
            if test & 1:                            # alpha test
                kind, reference, fail = (test >> 1) & 7, (test >> 4) & 0xFF, (test >> 12) & 3
                passes = [values < 0, values >= 0, values < reference, values <= reference,
                          values == reference, values >= reference, values > reference, values != reference][kind]
                if fail in (0, 2):                  # the pixel, or its colour, is dropped
                    weight = np.where(passes, weight, 0.0)
        best = np.maximum(best, weight)
    return best


class Use:
    """What is known of a dumped picture."""

    def __init__(self, meta, rgba):
        states = meta.get('states', [])
        height, width = rgba.shape[:2]
        self.meta = meta
        self.whole = bool(meta.get('whole', False))
        # What alpha hides is only believed when the application saw every way the
        # picture is drawn: a file written by disctex.py (nobody has seen the picture
        # drawn), or one with more ways of drawing than the application keeps, hides
        # nothing. A texel's colour is only ever replaced when no way of drawing shows it.
        self.seen = bool(states) and meta.get('source') != 'disc' and not meta.get('states_overflow')
        self.weight = alpha_weight(states) if self.seen else np.ones(256, dtype=np.float32)
        masked = any(s['scanmsk'] for s in states)
        sprites = any(s['prim'] == 6 for s in states)
        blends = set(s['alpha'] for s in states if s['abe'])
        # drawn without writing depth: particles, trails, glows, water
        effect = bool(states) and all((s['test'] & 0x300F) == 0x1001 for s in states)
        additive = bool(states) and all(s['abe'] and s['alpha'] in (0x48, 0x68) for s in states)
        if states and all(s['context'] == 1 for s in states):
            self.kind = 'environment'               # the fixed reflection picture: left as it is
        elif masked or (sprites and not effect and blends <= {0x44}):
            self.kind = 'interface'
        elif additive:
            self.kind = 'glow'                      # added to the picture: black adds nothing
        elif effect or sprites:
            self.kind = 'sprite'
        elif any(s['tfx'] == 3 for s in states):
            self.kind = 'model'
        else:
            self.kind = 'level'
        # two fields: the sprites drawn to their own even lines start a quarter texel
        # into the first field, those drawn to their odd lines at the second field
        self.field_rows = 0
        first, second = meta.get('field0_uv'), meta.get('field1_uv')
        if first and second:
            rows = second[1] - first[1] + 0.25
            if rows == int(rows) and rows >= 1 and (first[1] % 1.0) == 0.25 and 2 * rows <= height + 0.5 * rows:
                self.field_rows = int(rows)
        # the rectangle of texels drawn with
        boxes = [meta[k] for k in ('sprite_uv', 'field0_uv', 'field1_uv', 'other_uv') if meta.get(k)]
        self.box = None
        self.tiles = (False, False)
        if boxes and not self.field_rows:
            u0, v0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
            u1, v1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
            named = (meta.get('named_width', width), meta.get('named_height', height))
            repeat = (all(s['wms'] == 0 for s in states), all(s['wmt'] == 0 for s in states))
            # drawn beyond the texture, and the dump is the whole period: it repeats
            self.tiles = (repeat[0] and (u0 < -1 or u1 > named[0] + 1) and width == named[0],
                          repeat[1] and (v0 < -1 or v1 > named[1] + 1) and height == named[1])
            x0 = 0 if (u0 < 0 or u1 > named[0]) else max(0, int(np.floor(u0)) - MARGIN)
            x1 = width if (u0 < 0 or u1 > named[0]) else min(width, int(np.ceil(u1)) + MARGIN)
            y0 = 0 if (v0 < 0 or v1 > named[1]) else max(0, int(np.floor(v0)) - MARGIN)
            y1 = height if (v0 < 0 or v1 > named[1]) else min(height, int(np.ceil(v1)) + MARGIN)
            x0, y0 = (x0 // 16) * 16, (y0 // 16) * 16
            x1, y1 = min(width, -(-x1 // 16) * 16), min(height, -(-y1 // 16) * 16)
            if x1 > x0 and y1 > y0 and (x1 - x0) * (y1 - y0) < 0.8 * width * height:
                self.box = (x0, y0, x1, y1)

    def signature(self):
        return [self.kind, self.field_rows, self.box, list(self.tiles), self.whole,
                hashlib.sha1(self.weight.tobytes()).hexdigest()[:12]]


def unsent_mask(rgba, fmt):
    """True for texels in whole GS blocks that are zero in all channels."""
    h, w = rgba.shape[:2]
    bw, bh = BLOCKS.get(fmt, (16, 16))
    zero = ~rgba.any(axis=2)
    mask = np.zeros((h, w), dtype=bool)
    for y in range(0, h, bh):
        for x in range(0, w, bw):
            if zero[y:y + bh, x:x + bw].all():
                mask[y:y + bh, x:x + bw] = True
    return mask


# ---- one picture ------------------------------------------------------------------------

class Job:
    def __init__(self, name, rgba, use, scale):
        self.name, self.use, self.scale = name, use, scale
        self.recipe = RECIPES[use.kind]
        self.size = rgba.shape[:2]
        fmt = use.meta.get('format', 19)
        unsent = np.zeros(self.size, dtype=bool) if use.whole else unsent_mask(rgba, fmt)
        alpha = rgba[..., 3]
        hidden = (use.weight[alpha] <= 0.02) & ~unsent
        rgb = rgba[..., :3]
        if use.field_rows:
            rows = use.field_rows
            if 2 * rows > rgba.shape[0]:            # the last lines were never sent
                short = 2 * rows - rgba.shape[0]
                rgb = np.pad(rgb, ((0, short), (0, 0), (0, 0)))
                alpha = np.pad(alpha, ((0, short), (0, 0)))
                unsent = np.pad(unsent, ((0, short), (0, 0)), constant_values=True)
                hidden = np.pad(hidden, ((0, short), (0, 0)))
            rgb, alpha, unsent, hidden = (weave(a, rows) for a in (rgb, alpha, unsent, hidden))
        self.alpha = alpha
        known = ~(unsent | hidden)
        self.empty = not known.any()
        # alpha that says "cannot be seen" for some texels and "can" for others
        self.cutout = bool(hidden.any() and known.any())
        # Colour is replaced by that of visible neighbours in what was never sent, and
        # in what cannot be seen only as far in as an enlarging filter reaches from what
        # can (BLEED texels). Hidden texels further in keep their own colour: if a .json
        # file should ever be wrong about what is hidden, a rim is lost and not the
        # thing itself.
        filled = fill_from_neighbours(rgb, known)
        self.bled = hidden & grow(known, BLEED)
        self.known = known
        self.rgb = np.where((unsent | self.bled)[..., None], filled, rgb.astype(np.float32))
        self.rgb_own = np.where(unsent[..., None], filled, rgb.astype(np.float32))     # the game's colours
        # alpha of unsent texels would pull the enlarged alpha of their neighbours
        self.alpha_filled = fill_from_neighbours(alpha[..., None], ~unsent)[..., 0] if unsent.any() and not unsent.all() else alpha.astype(np.float32)
        h, w = self.rgb.shape[:2]
        self.box = use.box if use.box else (0, 0, w, h)
        # the bars of the interface are 6 or 8 lines high: enlarged plainly
        # and so are the smallest model textures (FEWEST)
        self.strength = self.recipe['strength'] if min(h, w) >= SMALLEST and h * w >= FEWEST.get(use.kind, 0) else 0.0
        self.alpha_values = np.unique(alpha[~unsent]) if (~unsent).any() else np.zeros(1, dtype=np.uint8)
        self.alpha_by_model = bool(self.recipe['alpha_model'] and self.cutout and len(self.alpha_values) > 1)

    def padded(self, picture):
        x0, y0, x1, y1 = self.box
        h, w = picture.shape[:2]
        modes = ['wrap' if (tiles and lo == 0 and hi == full) else 'edge'
                 for tiles, lo, hi, full in ((self.use.tiles[1], y0, y1, h), (self.use.tiles[0], x0, x1, w))]
        # inside the picture the border is the picture itself
        top, bottom, left, right = min(PAD, y0), min(PAD, h - y1), min(PAD, x0), min(PAD, w - x1)
        part = picture[y0 - top:y1 + bottom, x0 - left:x1 + right]
        if part.ndim == 2:
            part = part[..., None]
        part = np.pad(part, ((PAD - top, PAD - bottom), (0, 0), (0, 0)), mode=modes[0])
        part = np.pad(part, ((0, 0), (PAD - left, PAD - right), (0, 0)), mode=modes[1])
        return part

    def stage(self, directories):
        """Writes what the models are to enlarge; returns the models wanted."""
        wanted = []
        if self.strength > 0:
            rgb = np.clip(self.padded(self.rgb) + 0.5, 0, 255).astype(np.uint8)
            Image.fromarray(rgb, 'RGB').save(os.path.join(directories[self.recipe['model']][0], self.name))
            wanted.append(self.recipe['model'])
        if self.alpha_by_model:
            top = float(self.alpha_values.max())
            grey = np.clip(self.padded(self.alpha_filled)[..., 0] * (255.0 / max(top, 1.0)) + 0.5, 0, 255).astype(np.uint8)
            Image.fromarray(np.dstack([grey] * 3), 'RGB').save(os.path.join(directories[self.recipe['alpha_model']][0], 'alpha-' + self.name))
            wanted.append(self.recipe['alpha_model'])
        return wanted

    def moved_colour(self, picture):
        """The self-check: the finished picture (its colour, at its size) made small
        again and compared with the game's texels. Counts the texels around which the
        colour is no longer the game's (by more than MOVED, taken over about a texel
        either way, so that sharpening does not count): 'seen' among texels the game
        shows, away from the rim of what it shows - there should be none; 'hidden' among
        the texels whose colour was replaced on purpose; 'worst' the largest move among
        the first."""
        scale = picture.shape[1] // self.rgb_own.shape[1]
        small = reduce_by(picture[..., :3].astype(np.float32), scale)[:self.rgb_own.shape[0]]
        move = np.abs(blur(small - self.rgb_own[:small.shape[0]], 1.0)).max(axis=2)
        inner = ~grow(~self.known, 2)[:small.shape[0]]
        return dict(seen=int(((move > MOVED) & inner).sum()), hidden=int(((move > MOVED) & self.bled[:small.shape[0]]).sum()),
                    worst=round(float(move[inner].max()), 1) if inner.any() else 0.0)

    def from_model(self, directories, model, prefix=''):
        path = os.path.join(directories[model][1], prefix + self.name)
        if not os.path.exists(path):
            return None
        x0, y0, x1, y1 = self.box
        big = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32)
        big = big[PAD * MODEL_SCALE:(PAD + y1 - y0) * MODEL_SCALE, PAD * MODEL_SCALE:(PAD + x1 - x0) * MODEL_SCALE]
        return reduce_by(big, MODEL_SCALE // self.scale)

    def finish(self, directories):
        scale = self.scale
        x0, y0, x1, y1 = self.box
        plain = resize(self.rgb, scale, Image.BICUBIC)
        out = plain
        made = self.from_model(directories, self.recipe['model']) if self.strength > 0 else None
        if made is not None:
            base = plain[y0 * scale:y1 * scale, x0 * scale:x1 * scale]
            part = self.rgb[y0:y1, x0:x1]
            strength = self.strength * (1.0 - self.recipe['calm'] * resize(noisiness(part), scale, Image.BILINEAR))
            mixed = base + strength[..., None] * (made - base)
            mixed = match_low(mixed, base, 1.5 * scale)
            if self.recipe['tone']:
                mixed = match_low(match_tone(mixed, base), base, 1.5 * scale)
            # nothing brighter or darker than the texels there: a thin line stays the
            # colour it is, it does not become a thinner, brighter one
            low, high = local_range(part, scale)
            mixed = np.clip(mixed, low - RANGE_SLACK, high + RANGE_SLACK)
            if self.use.kind == 'glow':
                # light that is added: nothing may appear where the game's picture is dark
                ceiling = blur(resize(self.rgb[y0:y1, x0:x1], scale, Image.BILINEAR), 0.5 * scale) * 1.6 + 2.0
                mixed = np.minimum(mixed, ceiling)
            out = plain.copy()
            out[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = mixed
        out = np.clip(out + 0.5, 0, 255).astype(np.uint8)

        # alpha: exact where it is one value; otherwise enlarged smoothly inside its range
        values = self.alpha_values
        low, high = float(values.min()), float(values.max())
        if len(values) == 1:
            alpha = np.full(out.shape[:2], values[0], dtype=np.uint8)
        else:
            smooth = resize(self.alpha_filled, scale, Image.BICUBIC)
            if self.alpha_by_model:
                made = self.from_model(directories, self.recipe['alpha_model'], 'alpha-')
                if made is not None:
                    sharp = made[..., 1] * (max(high, 1.0) / 255.0)
                    sharp = match_low(sharp, smooth[y0 * scale:y1 * scale, x0 * scale:x1 * scale], 1.5 * scale)
                    smooth = smooth.copy()
                    smooth[y0 * scale:y1 * scale, x0 * scale:x1 * scale] = sharp
            # where a texel and all its neighbours have the same alpha, exactly that
            a = self.alpha_filled
            p = np.pad(a, 1, mode='edge')
            h, w = a.shape
            around = [p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)]
            flat = np.all([n == a for n in around], axis=0)
            flat = np.repeat(np.repeat(flat, scale, 0), scale, 1)
            exact = np.repeat(np.repeat(a, scale, 0), scale, 1)
            alpha = np.clip(np.where(flat, exact, smooth) + 0.5, low, high).astype(np.uint8)
        picture = np.dstack([out, alpha])
        self.check = self.moved_colour(out)

        rows = self.use.field_rows
        if rows:
            # the enlarged picture twice; the second copy half a field line up, because
            # the game reads the second field a quarter texel earlier than the first
            height = self.size[0] * 2 * scale
            both = np.zeros((height, picture.shape[1], 4), dtype=np.uint8)
            both[:picture.shape[0]] = picture
            shifted = np.concatenate([picture[scale // 2:], np.repeat(picture[-1:], scale // 2, axis=0)])
            end = min(height, 2 * picture.shape[0])
            both[picture.shape[0]:end] = shifted[:end - picture.shape[0]]
            picture = both
        return picture


# ---- the run ----------------------------------------------------------------------------

def run_model(upscaler, model, source, target):
    if not os.listdir(source):
        return
    upscaler = os.path.abspath(upscaler)           # it looks for its models beside itself
    subprocess.run([upscaler, '-i', source, '-o', target, '-n', model, '-s', str(MODEL_SCALE), '-f', 'png'],
                   cwd=os.path.dirname(upscaler), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def report(checks, path):
    """Says what the self-check found (Job.moved_colour); `path`: a file that keeps the
    figures of every picture made so far. Returns 1 when a picture's colour has moved
    where the game shows it."""
    if path:
        kept = {}
        if os.path.exists(path):
            with open(path) as file:
                kept = json.load(file)
        kept.update(checks)
        with open(path, 'w') as file:
            json.dump(kept, file, indent=0, sort_keys=True)
    bad = sorted(((c['seen'], c['worst'], name) for name, c in checks.items() if c['seen'] > 0), reverse=True)
    replaced = [(c['hidden'], name) for name, c in checks.items() if c['hidden'] > 0]
    print('upscale.py: self-check of %d pictures: colour moved by more than %d where the game shows it in %d of them%s'
          % (len(checks), MOVED, len(bad), '' if bad else ' (none)'))
    for seen, worst, name in bad[:40]:
        print('upscale.py:   LOOK AT %s: %d texels, largest move %.0f' % (name, seen, worst))
    if len(bad) > 40:
        print('upscale.py:   ... and %d more' % (len(bad) - 40))
    print('upscale.py: colour replaced on purpose, in texels no draw shows (within %d texels of ones that are shown): %d pictures, %d texels'
          % (BLEED, len(replaced), sum(n for n, _ in replaced)))
    return 1 if bad else 0


class Sized:
    """Stands for a picture of which only the size is needed."""

    def __init__(self, path):
        with Image.open(path) as image:             # the header only: nothing is unpacked
            self.shape = (image.size[1], image.size[0], 4)


def load(dump, name):
    """A dumped picture and what is known of it."""
    with open(os.path.join(dump, name[:-4] + '.json')) as file:
        meta = json.load(file)
    rgba = np.asarray(Image.open(os.path.join(dump, name)).convert('RGBA'))
    return rgba, Use(meta, rgba)


def enlarge_batch(task):
    """Enlarges some pictures (one call of each model for all of them); returns, for each
    one written, its name, signature, self-check and whether it is a two-field picture.
    Run in a process of its own with --jobs."""
    dump, replace, upscaler, scale, part, recipes = task
    RECIPES.update(recipes)
    made = []
    work = tempfile.mkdtemp(prefix='rta-upscale-')
    try:
        directories = {}
        for model in (X4, ANIME, VIDEO):
            directories[model] = (os.path.join(work, model, 'in'), os.path.join(work, model, 'out'))
            os.makedirs(directories[model][0])
            os.makedirs(directories[model][1])
        jobs = []
        for name, signature in part:
            try:
                rgba, use = load(dump, name)
            except (OSError, ValueError) as error:      # a file a running game is still writing
                print('upscale.py: %s left out: %s' % (name, error), flush=True)
                continue
            job = Job(name, rgba, use, scale)
            if job.empty:
                continue
            job.stage(directories)
            jobs.append((job, signature))
        for model in directories:
            run_model(upscaler, model, *directories[model])
        for job, signature in jobs:
            picture = job.finish(directories)
            Image.fromarray(picture, 'RGBA').save(os.path.join(replace, job.name), compress_level=3)
            made.append((job.name, signature, dict(job.check, kind=job.use.kind), bool(job.use.field_rows)))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return made


def halve_one(task):
    """A picture of a pack of twice the size made half as large (--from-pack)."""
    source, target, name = task
    big = np.asarray(Image.open(os.path.join(source, name)).convert('RGBA'), dtype=np.float32)
    small = np.clip(reduce_by(big, 2) + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(small, 'RGBA').save(os.path.join(target, name), compress_level=3)
    return name


def check_one(task):
    """The self-check of one finished file of a pack."""
    dump, replace, name = task
    rgba, use = load(dump, name)
    job = Job(name, rgba, use, 1)
    made = np.asarray(Image.open(os.path.join(replace, name)).convert('RGB'))
    if use.field_rows:                              # the first of the two copies
        made = made[:2 * use.field_rows * (made.shape[1] // rgba.shape[1])]
    return name, dict(job.moved_colour(made), kind=use.kind)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('dump')
    parser.add_argument('replace')
    parser.add_argument('--upscaler', help='the realesrgan-ncnn-vulkan program')
    parser.add_argument('--scale', type=int, default=4, choices=(2, 4), help='size of the result (4)')
    parser.add_argument('--force', action='store_true', help='redo pictures that are up to date')
    parser.add_argument('--only', default='', help='only names containing this text')
    parser.add_argument('--names', metavar='FILE', help='only the pictures named in FILE, one file name a line (the dump is not gone through: quick for a part of a large one)')
    parser.add_argument('--kind', default='', help='only pictures of this kind (interface, level, model, glow, sprite)')
    parser.add_argument('--list', action='store_true', help='say what each picture is and stop')
    parser.add_argument('--recipe', action='append', default=[], metavar='KIND:FIELD=VALUE',
                        help='change a recipe for this run, e.g. level:strength=0.6 (for trying)')
    parser.add_argument('--batch', type=int, default=120, help='pictures enlarged at a time')
    parser.add_argument('--jobs', type=int, default=1, help='batches worked on at the same time, each in a process of its own (1)')
    parser.add_argument('--limit', type=int, default=0, help='stop after this many pictures (the rest is done by the next run)')
    parser.add_argument('--check', action='store_true', help='enlarge nothing: compare every file of REPLACE_DIR, made small again, with its dump')
    parser.add_argument('--from-pack', metavar='DIR', help='with --scale 2: make each picture by halving the one in DIR, the replacement folder of a 4x pack made by this script (no enlarging program needed; pictures DIR does not hold are left to a run without this option)')
    args = parser.parse_args()
    for change in args.recipe:
        target, value = change.split('=', 1)
        kind, field = target.split(':', 1)
        old = RECIPES[kind][field]
        RECIPES[kind][field] = (value if isinstance(old, str) or old is None else type(old)(float(value))) if value != 'None' else None
    if args.from_pack and args.scale != 2:
        parser.error('--from-pack makes a 2x pack: give --scale 2')
    if not args.list and not args.check and not args.upscaler and not args.from_pack:
        parser.error('--upscaler is needed')

    os.makedirs(args.replace, exist_ok=True)
    manifest_path = os.path.join(args.replace, 'upscale-manifest.json')
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as file:
            manifest = json.load(file)
    source_manifest = {}
    if args.from_pack:
        with open(os.path.join(args.from_pack, 'upscale-manifest.json')) as file:
            source_manifest = json.load(file)
    if args.names:
        with open(args.names) as file:
            names = sorted(set(line.strip() for line in file))
        names = [n for n in names if n.endswith('.png') and not n.startswith('mem-') and os.path.exists(os.path.join(args.dump, n))]
    else:
        names = sorted(n for n in os.listdir(args.dump) if n.endswith('.png') and not n.startswith('mem-'))
    if args.only:
        names = [n for n in names if args.only in n]

    # what there is to do: read from the .json files and the pictures' headers alone, so
    # that a dump of a hundred thousand pictures is gone through in a minute
    todo, to_check, counts, skipped, unseen, waiting = [], [], {}, 0, 0, 0
    for name in names:
        meta_path = os.path.join(args.dump, name[:-4] + '.json')
        if not os.path.exists(meta_path):
            skipped += 1
            continue
        try:
            with open(meta_path) as file:
                meta = json.load(file)
            size = Sized(os.path.join(args.dump, name))
        except (OSError, ValueError):               # a file a running game is still writing
            skipped += 1
            continue
        if not meta.get('states'):                  # written by disctex.py: not seen drawn yet
            unseen += 1
            continue
        use = Use(meta, size)
        counts[use.kind] = counts.get(use.kind, 0) + 1
        if args.list:
            print('%s %-11s %4dx%-4d fields=%-3d box=%s tiles=%s' % (name[:16], use.kind, size.shape[1], size.shape[0], use.field_rows, use.box, use.tiles))
            continue
        if use.kind not in RECIPES or (args.kind and use.kind != args.kind) or min(size.shape[:2]) < 8:
            continue
        if args.check:
            if os.path.exists(os.path.join(args.replace, name)):
                to_check.append((args.dump, args.replace, name))
            continue
        signature = [VERSION, args.scale, os.path.getsize(os.path.join(args.dump, name)), use.signature(), RECIPES[use.kind]]
        if size.shape[0] * size.shape[1] < FEWEST.get(use.kind, 0):
            signature.append('plain')               # (added to the signature only where it applies)
        signature = json.loads(json.dumps(signature))
        # a picture made by halving the 4x pack's counts as done for a plain --scale 2 run too
        if not args.force and manifest.get(name) in (signature, signature + ['halved']) and os.path.exists(os.path.join(args.replace, name)):
            continue
        if args.from_pack:
            # only from a 4x picture that is itself up to date
            if source_manifest.get(name) != signature[:1] + [4] + signature[2:] or not os.path.exists(os.path.join(args.from_pack, name)):
                waiting += 1
                continue
            signature = signature + ['halved']
        todo.append((name, signature))
    print('upscale.py: %d pictures %s (%s)%s' % (len(names), 'named' if args.names else 'in the dump', ', '.join('%d %s' % (v, k) for k, v in sorted(counts.items())),
                                                           '; %d without a readable .json file left out (dump them again with this build)' % skipped if skipped else ''), flush=True)
    if unseen:
        print('upscale.py: %d pictures from the disc whose way of drawing is not known left out (they are done once a run with --rta-texture-dump has drawn them)' % unseen)
    if args.list:
        return 0
    pool = None
    if args.jobs > 1:
        import multiprocessing
        pool = multiprocessing.get_context('spawn').Pool(args.jobs)
    if args.check:
        checks = dict(pool.imap_unordered(check_one, to_check, 16) if pool else map(check_one, to_check))
        return report(checks, None)
    if waiting:
        print('upscale.py: %d pictures have no up-to-date picture in %s to halve' % (waiting, args.from_pack))
    if not todo:
        print('upscale.py: nothing to do')
        return 0
    if args.limit and len(todo) > args.limit:
        print('upscale.py: %d pictures to do, %d of them in this run' % (len(todo), args.limit))
        todo = todo[:args.limit]

    def keep():
        with open(manifest_path + '.new', 'w') as file:
            json.dump(manifest, file)
        os.replace(manifest_path + '.new', manifest_path)

    if args.from_pack:
        tasks = [(args.from_pack, args.replace, name) for name, signature in todo]
        signatures = dict(todo)
        try:
            for number, name in enumerate(pool.imap_unordered(halve_one, tasks, 16) if pool else map(halve_one, tasks), 1):
                manifest[name] = signatures[name]
                if number % 2000 == 0:
                    keep()
                    print('upscale.py: %d of %d' % (number, len(todo)), flush=True)
        finally:
            keep()
        print('upscale.py: wrote %d pictures to %s at 2x, each half the size of its picture in %s (check them with --check)' % (len(todo), args.replace, args.from_pack))
        return 0

    done = fields = 0
    checks = {}
    tasks = [(args.dump, args.replace, args.upscaler, args.scale, todo[start:start + args.batch], RECIPES) for start in range(0, len(todo), args.batch)]
    try:
        for number, made in enumerate(pool.imap_unordered(enlarge_batch, tasks) if pool else map(enlarge_batch, tasks), 1):
            for name, signature, check, two_fields in made:
                manifest[name] = signature
                checks[name] = check
                done += 1
                fields += 1 if two_fields else 0
            if number % 8 == 0:
                keep()
            print('upscale.py: %d of %d' % (min(number * args.batch, len(todo)), len(todo)), flush=True)
    finally:
        keep()                                      # also when stopped half way: what is written is remembered
        if checks:
            report(checks, os.path.join(args.replace, 'upscale-check.json'))
    print('upscale.py: wrote %d pictures to %s at %dx (%d of them two-field interface pictures)' % (done, args.replace, args.scale, fields))
    return 0


if __name__ == '__main__':
    sys.exit(main())
