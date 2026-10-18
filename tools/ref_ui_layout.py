"""Addressed UI contracts for SLUS-20973 v2.00; see docs/hud-layout.md.

Draw records preserve original API coordinates and scissor arguments, not a
guessed Godot nine-slice. Plain sprites add one to y; clipped sprites do not.
"""
from collections import namedtuple
import math
import struct


Draw = namedtuple('Draw', 'resource x y clip', defaults=(None,))


def menu_frame(x, y, width, height, style=2, no_center=False, no_border=False):
    """0x17c118 call geometry, including partial tiles and style-2 overlap.

    Returns submission order. The original 2D queue prepends packets, so a
    painter renderer must reverse this list within the common sort layer.
    Dimensions are caller width/height, not x1/y1. Small frames are NOT clamped.
    """
    prefix = 'tile' if style == 2 else 'btile' if style == 1 else 'ctile'
    n = 16 if prefix == 'ctile' else 32
    cw, ch = {'tile': (320, 224), 'btile': (64, 64), 'ctile': (128, 64)}[prefix]
    right, bottom = x + width, y + height
    out = []
    def emit(part, dx, dy, clip=None):
        out.append(Draw(prefix + part + '.tex', dx, dy, clip))
    if not no_border:
        for part, dx, dy in [('botleft',x,bottom-n-1),('botright',right-n,bottom-n-1),
                             ('topleft',x,y-1),('topright',right-n,y-1)]:
            emit(part,dx,dy)
        for dx in range(0, max(0, width-2*n), n):
            emit('top',x+n+dx,y,(x,y,right-n,bottom-n))
            emit('bot',x+n+dx,bottom-n,(x,y,right-n+(4 if style==2 else 0),bottom))
        for dy in range(0, max(0, height-2*n), n):
            emit('left',x,y+n+dy,(x,y,right,bottom-n))
            emit('right',right-n,y+n+dy,(x,y,right,bottom-n))
    if not no_center:
        if style == 2:
            # Inclusive outer loop in original, unlike the ordinary center.
            for dy in range(0, max(0, height-2*n+51), ch):
                for dx in range(0, max(0, width-2*n+52), cw):
                    emit('center',x+n-25+dx,y+n-26+dy,(x,y,right-n+26,bottom-n+26))
        else:
            for dy in range(0, max(0, height-2*n), ch):
                for dx in range(0, max(0, width-2*n), cw):
                    emit('center',x+n+dx,y+n+dy,(x,y,right-n,bottom-n))
    return out


HUD_X = (12, 478, 167, 323)   # table 0x53c408, consumed at 0x1d9e50


def frame_source_rect(resource):
    """Whole-texture source bounds; 0x17c118/0x17bb84, INTERFAC.LMP headers.

    These are separate resources, not slices of a shared original atlas.
    """
    for prefix, border, center in [('btile',32,(64,64)), ('ctile',16,(128,64)),
                                    ('tile',32,(320,224))]:
        if resource.startswith(prefix) and resource.endswith('.tex'):
            part = resource[len(prefix):-4]
            if part in ('top','bot','left','right','topleft','topright','botleft','botright','center'):
                w,h = center if part == 'center' else (border,border)
                return (0,0,w,h)
    raise ValueError('not a documented frame resource')


def hud_origins(network=False, local_slots=(), player_count=4):
    """Exact local-slot promotion at 0x1d9df4..1d9e4c (ordinary valid slots)."""
    values = list(HUD_X)
    previous = 0
    if network:
        for slot in range(player_count):
            if slot in local_slots and slot:
                previous = values[slot]
                values[slot] = values[0]
        if 0 not in local_slots:
            values[0] = previous
    return tuple(values)


def bar_clip_right(origin, current, maximum):
    """PS2 truncating float arithmetic, 0x1d9f24..1d9f84; no safety clamp.

    Positive finite max/current are the supported reference domain. Malformed
    state is refused here; original behavior outside that domain is not claimed.
    """
    from ee_emu import float_to_raw, fp_div, fp_mul, fp_add, fp_to_int
    if not all(math.isfinite(v) for v in (origin, current, maximum)) or maximum <= 0 or current < 0 or origin < 0:
        raise ValueError('outside supported bar domain')
    fraction = fp_div(float_to_raw(current), float_to_raw(maximum))
    scaled = fp_mul(fraction, float_to_raw(99.0))
    return fp_to_int(fp_add(float_to_raw(float(origin)), scaled))


HudLayer = namedtuple('HudLayer', 'resource x y clip tint layer')


def hud_base_layers(x, tick, health, health_max, mana, mana_max,
                    experience=0, experience_base=0, experience_next=1,
                    acknowledged_level=1, local=True, cooldown=0, health_flash=False):
    """Base layers from 0x1d9cd4; excludes text, potion overlays, glow and notices.

    x is the selected HUD_X value, not the inner bar origin. Tick must be >= 0.
    Call only after the game's visibility gates; all are sort layer 6.
    """
    if tick < 0:
        raise ValueError('negative ticks are outside this reference domain')
    frame, start = (tick >> 2) % 11, x + 15
    def bar(color, y, value, maximum, tint):
        return HudLayer('bar_%s%02d.tex' % (color,frame), start,y,
                        (start,24,bar_clip_right(start,value,maximum),124),tint,6)
    out=[bar('red',46,health,health_max,0x80ffffff if health_flash else 0x80808080)]
    if local:
        if acknowledged_level > 0:
            out.append(bar('green',56,experience-experience_base,experience_next-experience_base,0x80808080))
        out.append(bar('blue',63,mana,mana_max,0x2aacacac if cooldown > 0 else 0x80acacac))
    out.append(HudLayer('hud_statusbar00.tex' if local else 'hud_multi.tex',x-4,36,(0,0,1000,1000),0x80808080,6))
    return out


class Font(namedtuple('FontBase', 'header_word charmap glyphs kerns texture_offset texture')):
    """Glyph: code,u0,u1,v0,v1,yOffset,advance,kernStart; kern: prev,current,delta."""
    __slots__ = ()

    def glyph_rects(self, index, pen_x=0, baseline_y=0):
        """Progressive logical source/destination rectangles, 0x180bf4..180c28.

        Caller handles mapping, kerning and clipping; baseline_y is the original
        text API's y origin (not an inferred typographic ascender baseline).
        """
        _,u0,u1,v0,v1,dy,_,_ = self.glyphs[index]
        return (u0,v0,u1-u0,v1-v0), (pen_x,baseline_y+dy,u1-u0,v1-v0)

    def width_ascii(self, data, interlaced=True, count=None):
        """0x17ffb0: map<=0 uses glyph 0 advance; missing glyph still becomes prev."""
        pen, previous = 0, -1
        for char in data if count is None else data[:count]:
            if not char:
                break
            index = self.charmap[char]
            if index <= 0:
                pen += self.glyphs[0][6] * 16
            else:
                g = self.glyphs[index]
                k = g[7]
                while k >= 0 and k < len(self.kerns) and self.kerns[k][1] == index:
                    left, _, amount = self.kerns[k]
                    if left == previous:
                        pen += amount * (16 if interlaced else 8)
                        break
                    k += 1
                pen += g[6] * 16
            previous = index
        return pen >> 4


def parse_font(data):
    """Bounded unrelocated FNT. Fixup 0x181a20; readers 0x17ffb0/0x180bc8.

    Validation is a native-reader policy, not bounds checks present in the game.
    Texture packet offset remains relative to the embedded TEX, not the FNT.
    """
    if len(data) < 0x214:
        raise ValueError('short font')
    n, word, nk, go, ko, to = struct.unpack_from('<HHIIII', data)
    if not 0 < n < 0x8000 or not (0x214 <= go <= go+n*16 <= ko <= ko+nk*6 <= to <= len(data)-0x40):
        raise ValueError('invalid font table spans')
    charmap = struct.unpack_from('<256h', data, 0x14)
    glyphs = tuple(struct.unpack_from('<H7h',data,go+16*i) for i in range(n))
    kerns = tuple(struct.unpack_from('<HHh',data,ko+6*i) for i in range(nk))
    if any(v >= n for v in charmap) or any(g[7] >= nk for g in glyphs):
        raise ValueError('invalid glyph/kerning reference')
    return Font(word,charmap,glyphs,kerns,to,bytes(data[to:]))
