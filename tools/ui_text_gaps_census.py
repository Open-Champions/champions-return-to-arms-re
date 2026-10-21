#!/usr/bin/env python3
"""Count what the UI text gaps touch on a disc. Counts only.

  python3 tools/ui_text_gaps_census.py --disc DIR

DIR is a directory holding the disc's files (searched recursively). Nothing is written.
No text, key, texture name, tick, coordinate or pixel is printed: only totals, flags
(0/1) and counts. docs/ui-text-gaps.md section 9 quotes the output.

What is counted:
  * BUST.LMP: entries, textures, the six fixed names hud_drawBust asks for, and how many
    textures read as two stacked fields (row k closer to row k + h/2 than to row k + 1);
  * showBust calls of every level script: literal portrait names found in BUST.LMP;
  * INTERFAC.LMP: the nine ctile pieces of the help box's inner frame;
  * COMPASS.LMP: compass.vif and compass.tex present, meshes, vertices and triangles;
  * FX.LMP: butn_message.anm (the help chime): present, events, events beyond the clip's
    length, and the number of sound_update calls its slot lives (ref_ui_text_gaps);
  * GTEXT.LMP: the 'Affirmation' and 'dialogMore' keys;
  * objects.ob: showName values, those holding a double quote, and how many of those a
    lookup finds (quotes dropped) or misses (NF:), with the dialog-capable ones apart.
"""
import argparse
import collections
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from gob import lmp_entries                       # noqa: E402
import model_info as MI                           # noqa: E402
import ref_anim as A                              # noqa: E402
import ref_strings as RS                          # noqa: E402
import ref_ui_text_gaps as R                      # noqa: E402
from strings_census import lump_blobs, table_stats, Script   # noqa: E402
from dialog_census import object_props            # noqa: E402

BUST_FIXED = [b'frame.tex', b'fieldmeter.tex', b'fieldnumber.tex'] + \
    [b'bar_yellow0%d.tex' % q for q in range(4)]
CTILE = [b'ctile%s.tex' % p for p in (b'topleft', b'topright', b'botleft', b'botright', b'left',
                                     b'right', b'bot', b'top', b'center')]


def field_verdict(data):
    """'stacked', 'single', 'unclear' or 'refused' for one .tex (model-texture.md test)."""
    try:
        t = MI.parse_texture(data)
        if t.kind == 'no-pixels' or not t.w or t.h < 8:
            return 'unclear'
        w, h, px = MI.decode_texture(t)
    except (MI.FormatError, struct.error, ValueError, IndexError, KeyError):
        return 'refused'
    half = h // 2

    def row(k):
        return px[k * w:(k + 1) * w]

    def diff(a, b):
        return sum(abs(p[c] - q[c]) for p, q in zip(a, b) for c in range(3))
    closer = farther = 0
    for k in range(half - 1):
        d_half, d_next = diff(row(k), row(k + half)), diff(row(k), row(k + 1))
        if d_half < d_next:
            closer += 1
        elif d_half > d_next:
            farther += 1
    total = closer + farther
    if total < 4:
        return 'unclear'
    if closer >= 0.7 * total:
        return 'stacked'
    if farther >= 0.7 * total:
        return 'single'
    return 'unclear'


def census(root):
    c = collections.Counter()
    lumps = {}
    scripts = []
    objects = []
    for container, lname, blob in lump_blobs(root):
        try:
            entries = lmp_entries(blob)
        except (struct.error, ValueError, IndexError):
            continue
        names = {e[0].lower().encode('latin1'): blob[e[1]:e[1] + e[2]] for e in entries}
        upper = lname.upper()
        if upper in ('BUST.LMP', 'INTERFAC.LMP', 'COMPASS.LMP', 'FX.LMP', 'GTEXT.LMP') and \
                container.upper() == upper:
            lumps[upper] = names
        if b'script.scr' in names:
            scripts.append(names[b'script.scr'])
        if b'objects.ob' in names:
            objects.append((names[b'objects.ob'], names.get(b'script.scr')))
    out = []

    def say(key, value):
        out.append((key, value))

    bust = lumps.get('BUST.LMP', {})
    say('BUST.LMP entries', len(bust))
    texs = [n for n in bust if n.endswith(b'.tex')]
    say('BUST.LMP textures', len(texs))
    say('fixed names hud_drawBust asks for, present (of 7)', sum(1 for n in BUST_FIXED if n in bust))
    verdicts = collections.Counter(field_verdict(bust[n]) for n in texs)
    for v in ('stacked', 'single', 'unclear', 'refused'):
        say('BUST.LMP textures read as %s fields' % v, verdicts[v])
    portraits = [n for n in texs if n not in BUST_FIXED]
    pv = collections.Counter(field_verdict(bust[n]) for n in portraits)
    say('  of them portraits (not a fixed name), stacked', pv['stacked'])
    lit = found = nonlit = 0
    for image in scripts:
        script = Script(image)
        for name, args in script.calls:
            if name != 'showBust':
                continue
            s = script.string(args[0]) if args else None
            if s is None:
                nonlit += 1
                continue
            lit += 1
            found += s.lower() in bust
    say('showBust calls with a literal portrait name', lit)
    say('  ... found in BUST.LMP', found)
    say('showBust portrait names not literal', nonlit)

    inter = lumps.get('INTERFAC.LMP', {})
    say('ctile pieces in INTERFAC.LMP (of 9)', sum(1 for n in CTILE if n in inter))

    comp = lumps.get('COMPASS.LMP', {})
    say('compass.vif present', int(b'compass.vif' in comp))
    say('compass.tex present', int(b'compass.tex' in comp))
    if b'compass.vif' in comp:
        try:
            m = MI.parse_model(comp[b'compass.vif'])
            say('compass.vif meshes', m.mesh_count)
            say('compass.vif levels of detail', m.lod_count)
            say('compass.vif vertices (level 0)', sum(ch.n for chunks in m.meshes[0] for ch in chunks))
            say('compass.vif triangles (level 0)',
                sum(len(MI.chunk_triangles(ch)[0]) for chunks in m.meshes[0] for ch in chunks))
        except (MI.FormatError, struct.error, ValueError, IndexError) as err:
            say('compass.vif refused by model_info', str(err)[:60])
    if b'compass.tex' in comp:
        say('compass.tex reads as stacked fields', int(field_verdict(comp[b'compass.tex']) == 'stacked'))

    fx = lumps.get('FX.LMP', {})
    chime = fx.get(b'butn_message.anm')
    say('butn_message.anm present in FX.LMP', int(chime is not None))
    if chime is not None:
        clip = A.Clip(chime, 'chime')
        events = [t for t in (clip.sound_times or []) if t != R.EVENT_END]
        say('  sound events', len(events))
        say('  events after the clip length', sum(1 for t in events if t > clip.length))
        say('  sound group is 0 (no cap)', int(clip.sound_group == 0))
        frames = R.chime_frames(events, clip.length)
        say('  sound_update calls the slot lives (nothing frozen)', frames)
        say('  frees by event cursor (1) or by end status (0)',
            int(not events or max(events) < clip.length))

    gtext = lumps.get('GTEXT.LMP', {})
    table, texts = None, {}
    if b'gtext.uni' in gtext:
        _stats, table, texts = table_stats(gtext[b'gtext.uni'])
    for key in (b'Affirmation', b'dialogMore'):
        say('GTEXT key %s present' % key.decode(), int(key in texts))

    shown = quoted = q_found = q_missing = q_trunc = 0
    talk_q_missing = plain_missing = 0
    for blob, _script in objects:
        try:
            for _cls, props in object_props(blob):
                if 'showname' not in props:
                    continue
                shown += 1
                key = props['showname'].encode('latin1')
                stripped = RS.strip_quotes(key)
                hit = stripped in texts
                if b'"' in key:
                    quoted += 1
                    if hit:
                        q_found += 1
                    else:
                        q_missing += 1
                        q_trunc += len(stripped) > 16
                        talk_q_missing += 'dialogscript' in props
                elif not hit:
                    plain_missing += 1
        except (ValueError, IndexError, struct.error):
            c['objects.ob refused'] += 1
    say('objects with showName', shown)
    say('  showName holding a double quote', quoted)
    say('  ... found once the quotes are dropped', q_found)
    say('  ... missing (show NF: + 16 bytes)', q_missing)
    say('  ... missing and longer than 16 bytes once stripped', q_trunc)
    say('  ... missing, on an object with dialogScript', talk_q_missing)
    say('  showName without a quote missing from GTEXT', plain_missing)
    for k, v in c.items():
        say(k, v)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--disc', required=True, help='directory with the disc files (read only)')
    args = parser.parse_args(argv)
    for key, value in census(args.disc):
        print('%-58s %s' % (key, value))
    return 0


if __name__ == '__main__':
    sys.exit(main())
