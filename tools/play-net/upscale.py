#!/usr/bin/env python3
"""Enlarges the textures the playable build has written out, for its replacement folder.

    tools/play-net/upscale.py DUMP_DIR REPLACE_DIR --upscaler /path/to/realesrgan-ncnn-vulkan
                              [--model realesrgan-x4plus] [--force] [--only SUBSTRING]

DUMP_DIR is `<data>/textures/dump` of a run with `--rta-texture-dump`, REPLACE_DIR is
`<data>/textures/replace` (tools/play-net/README.md, "Texture dump and replacement").
Each picture is written to REPLACE_DIR under the same name at four times the size. The
enlarging itself is done by Real-ESRGAN (https://github.com/xinntao/Real-ESRGAN, the
ncnn-vulkan program and its models; not part of this repository). What this script adds is
what the game's pictures need around it:

- colour and alpha are enlarged separately, and alpha keeps the console's scale (128 is
  opaque) and its exact values where it is constant or two-valued;
- texels the game never sent (whole 16 x 16 blocks of zeros) are filled from their
  neighbours before enlarging, so that the border of the used part is not darkened, and
  are zero again afterwards;
- interface pictures stored as two field pictures, one above the other, are interleaved
  into one picture, enlarged, and taken apart again.

The dumps and everything made from them are the game's art: keep both folders out of any
repository. Needs Python 3 with numpy and Pillow.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

SCALE = 4
PAD = 8          # texels of border repeated around a picture before enlarging
BLOCK = 16       # the game sends whole blocks; an all-zero block was not sent


def unsent_mask(rgba):
    """True for texels in block-aligned 16 x 16 blocks that are zero in all channels."""
    h, w = rgba.shape[:2]
    mask = np.zeros((h, w), dtype=bool)
    zero = ~rgba.any(axis=2)
    for y in range(0, h, BLOCK):
        for x in range(0, w, BLOCK):
            if zero[y:y + BLOCK, x:x + BLOCK].all():
                mask[y:y + BLOCK, x:x + BLOCK] = True
    return mask


def fill_from_neighbours(rgb, mask):
    """Colour of masked texels taken from the nearest unmasked ones (repeated spreading)."""
    if not mask.any() or mask.all():
        return rgb
    out = rgb.astype(np.float32)
    known = ~mask
    for _ in range(max(rgb.shape[0], rgb.shape[1])):
        if known.all():
            break
        total = np.zeros_like(out)
        count = np.zeros(known.shape, dtype=np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(known, (dy, dx), axis=(0, 1))
            val = np.roll(out, (dy, dx), axis=(0, 1))
            # nothing wraps round the edge of the picture
            if dy == 1: src[0, :] = False
            if dy == -1: src[-1, :] = False
            if dx == 1: src[:, 0] = False
            if dx == -1: src[:, -1] = False
            total += val * src[..., None]
            count += src
        grow = (~known) & (count > 0)
        out[grow] = total[grow] / count[grow][:, None]
        known = known | grow
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def is_two_fields(rgba, mask):
    """An interface picture: its top and bottom halves are the even and odd lines of one
    picture, so they look alike - more alike than lines two apart inside one half."""
    h = rgba.shape[0]
    if h < 16 or h % 2 or mask.all():
        return False
    top = rgba[:h // 2].astype(np.float32)
    bottom = rgba[h // 2:].astype(np.float32)
    used = ~(mask[:h // 2] | mask[h // 2:])
    if used.sum() < 64 or top.shape[0] < 4:
        return False
    between = np.abs(top - bottom)[used].mean()
    inside = np.abs(top[1:] - top[:-1])[used[1:] & used[:-1]].mean() if (used[1:] & used[:-1]).any() else 0.0
    detail = np.abs(top - top.mean(axis=(0, 1)))[used].mean()
    # alike, and the picture is not simply flat
    return detail > 4.0 and between < 0.75 * inside + 1.0 and between < 14.0


def weave(a):
    h = a.shape[0]
    out = np.empty_like(a)
    out[0::2] = a[:h // 2]
    out[1::2] = a[h // 2:]
    return out


def unweave(a):
    return np.concatenate([a[0::2], a[1::2]], axis=0)


def enlarge_alpha(alpha):
    values = np.unique(alpha)
    h, w = alpha.shape
    if len(values) <= 2:
        return np.repeat(np.repeat(alpha, SCALE, axis=0), SCALE, axis=1)
    big = Image.fromarray(alpha, 'L').resize((w * SCALE, h * SCALE), Image.BICUBIC)
    return np.clip(np.asarray(big), int(values.min()), int(values.max())).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('dump')
    parser.add_argument('replace')
    parser.add_argument('--upscaler', required=True, help='the realesrgan-ncnn-vulkan program')
    parser.add_argument('--model', default='realesrgan-x4plus')
    parser.add_argument('--force', action='store_true', help='redo pictures already in REPLACE_DIR')
    parser.add_argument('--only', default='', help='only names containing this text')
    parser.add_argument('--min-size', type=int, default=16, help='leave out pictures smaller than this on either side')
    args = parser.parse_args()

    os.makedirs(args.replace, exist_ok=True)
    names = sorted(n for n in os.listdir(args.dump) if n.endswith('.png') and not n.startswith('mem-'))
    if args.only:
        names = [n for n in names if args.only in n]
    work = tempfile.mkdtemp(prefix='rta-upscale-')
    staged_in, staged_out = os.path.join(work, 'in'), os.path.join(work, 'out')
    os.makedirs(staged_in)
    os.makedirs(staged_out)
    jobs = {}
    try:
        for name in names:
            if not args.force and os.path.exists(os.path.join(args.replace, name)):
                continue
            rgba = np.asarray(Image.open(os.path.join(args.dump, name)).convert('RGBA'))
            h, w = rgba.shape[:2]
            if h < args.min_size or w < args.min_size:
                continue
            mask = unsent_mask(rgba)
            if mask.all():
                continue
            fields = is_two_fields(rgba, mask)
            rgb = fill_from_neighbours(rgba[..., :3], mask)
            alpha = rgba[..., 3]
            if fields:
                rgb, alpha, mask = weave(rgb), weave(alpha), weave(mask)
            padded = np.pad(rgb, ((PAD, PAD), (PAD, PAD), (0, 0)), mode='edge')
            Image.fromarray(padded, 'RGB').save(os.path.join(staged_in, name))
            jobs[name] = (alpha, mask, fields, (h, w))
        if not jobs:
            print('upscale.py: nothing to do (%d pictures in the dump)' % len(names))
            return 0
        print('upscale.py: enlarging %d pictures with %s ...' % (len(jobs), args.model), flush=True)
        subprocess.run([args.upscaler, '-i', staged_in, '-o', staged_out, '-n', args.model,
                        '-s', str(SCALE), '-f', 'png'],
                       cwd=os.path.dirname(os.path.abspath(args.upscaler)), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        done = fields_count = 0
        for name, (alpha, mask, fields, (h, w)) in jobs.items():
            path = os.path.join(staged_out, name)
            if not os.path.exists(path):
                print('upscale.py: no result for %s' % name, file=sys.stderr)
                continue
            big = np.asarray(Image.open(path).convert('RGB'))
            big = big[PAD * SCALE:PAD * SCALE + h * SCALE, PAD * SCALE:PAD * SCALE + w * SCALE]
            big_alpha = enlarge_alpha(alpha)
            big_mask = np.repeat(np.repeat(mask, SCALE, axis=0), SCALE, axis=1)
            out = np.dstack([big, big_alpha])
            out[big_mask] = 0
            if fields:
                out = unweave(out)
                fields_count += 1
            Image.fromarray(out, 'RGBA').save(os.path.join(args.replace, name))
            done += 1
        print('upscale.py: wrote %d pictures to %s (%d of them two-field interface pictures)'
              % (done, args.replace, fields_count))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
