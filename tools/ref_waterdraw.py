#!/usr/bin/env python3
"""How a water tile is coloured, waved and drawn.

Pure functions. tools/test_ref_waterdraw.py checks them on authored numbers.
tools/difftest_waterdraw.py runs the same inputs through water_setup (0x1875d4),
water_init (0x187374), water_disturb (0x189514), world_drawWaterChunk (0x1876e0),
the height step
(0x196088), the simulation (0x186e38) and the water VU1 entries. Nothing here
reads a disc file.

The blend, the grid and the vertex formula are docs/formats/water-draw.md.
"""
import math
import struct

import ee_emu

# CPU float ops in the drawer and the matrix helper. VU vertex packing chops.
_CPU = 'ps2'
_VU = 'chop'

# water_setup (0x1875d4) writes set 0. Set 1 is already in the executable and is
# selected by chunk flag 0x1000. Alpha is the FIX field, not the RGBA alpha.
SET0_FIX = 102
SET0_COLOUR = 0x006D6B5F          # R 95, G 107, B 109, A 0
SET0_SCALE = 0x3B999999           # 0.0046875
SET1_FIX = 98
SET1_COLOUR = 0x00808080          # R 128, G 128, B 128, A 0
SET1_SCALE = 0x3CC00000           # 0.0234375, five times set 0
WAVE_STRENGTH = 41.0              # 0x44f064, the in-simulation splash
WAVE_RADIUS = 10.0                # 0x44f068
STEP_SCALE = 0x3D088888           # one ulp under the nearest float of 1/30

LAYER = 3
ALPHA_BLEND = 0x64                # (Cs - Cd) * FIX + Cd
ALPHA_ADD = 0x68                  # Cs * FIX + Cd
TEST = 0x00071001
TEX1 = 0x61                       # bilinear, no mip maps
PRIM = 0x15C                      # strip, gouraud, textured, UV, blend
GIF_NLOOP = 62

UV_SCALE = 0x3D4C78EA             # 0.0499200001 texels per unit of height/16
UV_BIAS = 32.0
XY_BIAS = 526336.0
CLIP = 1000.0                     # a vertex at exactly 1000 is kept

SPLASH_STRENGTH = 1500.0
SPLASH_RADIUS = 6.0
SPLASH_MODULUS = 300
SPLASH_UNIT = 0x37800000             # 1/65536, applied to the generator's high half
PARTICLE_RISE = 0x42A00000           # 80, the second spawn's random lift
PARTICLE_LIFT = 0x41C00000           # 24, added after that lift
PARTICLE_FIRST = 0x7D5D00
PARTICLE_SECOND = 0x7D5CB0
LCG_MUL = 0x0019660D
LCG_ADD = 0x3C6EF35F
KEEP_FRAMES = 200

# water_init (0x187374). One ulp under 0.1. Ten of them stay strictly under 1.
EDGE_WEIGHT = 0x3DCCCCCC
CLAIM_ONE = 0x3F800000

# water_disturb (0x189514). Width times this, plus one half, truncates to the cell count.
DISTURB_WIDTH = 0x3DAAAAAA

# Samples across one tile. Record 0 is the step's spare row. Records 1..32 are
# uploaded. The first two uploads are not kicked, so 30 strips are drawn.
ROWS = 33
SAMPLES = 32
STRIPS = 30
VERTS_PER_STRIP = 62


def _raw(value):
    return ee_emu.float_to_raw(float(value))


def _f32(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xFFFFFFFF))[0]


def _cpu_add(a, b):
    return ee_emu.fp_add(a, b, _CPU)


def _cpu_mul(a, b):
    return ee_emu.fp_mul(a, b, _CPU)


def _cpu_sub(a, b):
    return ee_emu.fp_sub(a, b, _CPU)


def _vu_add(a, b):
    return ee_emu.fp_add(a, b, _VU)


def _vu_mul(a, b):
    return ee_emu.fp_mul(a, b, _VU)


def _vu_div(a, b):
    return ee_emu.fp_div(a, b, _VU)


def colour_word(red, green, blue):
    """The RGBAQ word a waterColor property stores. The fourth integer is the fix."""
    return (int(red) & 0xFF) | ((int(green) & 0xFF) << 8) | ((int(blue) & 0xFF) << 16)


def wavyness_scale(parsed):
    """waterWavyness stores the parsed float times the static set-1 scale."""
    return _cpu_mul(int(parsed) & 0xFFFFFFFF, SET1_SCALE)


def colour_channels(word):
    """R, G, B, A of an RGBAQ word. A is stored as 0 and is not the blend."""
    word &= 0xFFFFFFFF
    return word & 0xFF, (word >> 8) & 0xFF, (word >> 16) & 0xFF, (word >> 24) & 0xFF


def alpha_words(fix):
    """(low 32 bits, high 32 bits) of ALPHA_1. A negative fix selects the add form."""
    fix = int(fix)
    if fix < 0:
        return ALPHA_ADD, -fix
    return ALPHA_BLEND, fix


def gs_state(constant_set):
    """The GS words and the height scale for set 0 or set 1."""
    if constant_set == 0:
        fix, colour, scale = SET0_FIX, SET0_COLOUR, SET0_SCALE
    elif constant_set == 1:
        fix, colour, scale = SET1_FIX, SET1_COLOUR, SET1_SCALE
    else:
        raise ValueError('water has two constant sets')
    low, high = alpha_words(fix)
    return {
        'fix': fix,
        'alpha_low': low,
        'alpha_high': high,
        'colour': colour,
        'scale': scale,
        'test': TEST,
        'tex1': TEX1,
        'prim': PRIM,
        'layer': LAYER,
    }


def floor_half(value):
    """floor(value + 0.5), toward -infinity. The drawer's origin and width."""
    summed = _cpu_add(_raw(value), _raw(0.5))
    return float(math.floor(_f32(summed)))


def tile_step_bits(min_x, max_x):
    """Float bits of the grid step. Only the x extent is used."""
    extent = floor_half(_f32(_cpu_add(_raw(max_x), _raw(min_x) ^ 0x80000000)))
    return _cpu_mul(ee_emu.fp_from_int(int(extent), _CPU), STEP_SCALE)


def origin(min_x, min_y, chunk_z):
    """World origin of the grid. chunk_z is the signed translation at chunk+0x30."""
    zbits = _cpu_mul(ee_emu.fp_from_int(int(chunk_z), _CPU), _raw(0.25))
    return floor_half(min_x), floor_half(min_y), _f32(zbits)


def upload_matrix(view, origin_xyz, scale_bits):
    """Four rows uploaded to VU memory 0..3, as raw float bits.

    view is four rows of four floats (g_viewProjModel, 0x44f1c0). Height moves
    along view row 2, the column index along row 1, the row index along row 0.
    """
    row0, row1, row2, row3 = view
    ox, oy, oz = origin_xyz
    out0 = tuple(_cpu_mul(scale_bits, _raw(v)) for v in row2)
    out1 = tuple(_raw(v) for v in row1)
    out2 = tuple(_raw(v) for v in row0)
    acc = [0, 0, 0, 0]
    for coef, row in ((ox, row0), (oy, row1), (oz, row2), (1.0, row3)):
        bits = _raw(coef)
        acc = [_cpu_add(acc[i], _cpu_mul(bits, _raw(row[i]))) for i in range(4)]
    return out0, out1, out2, tuple(acc)


def _itof4(sample):
    return _vu_mul(ee_emu.fp_from_int(sample & 0xFFFFFFFF, _VU), _raw(1.0 / 16.0))


def _ftoi4(raw):
    return ee_emu.fp_to_int(_vu_mul(raw, _raw(16.0))) & 0xFFFFFFFF


def _uv(delta):
    return _ftoi4(_vu_add(_raw(UV_BIAS), _vu_mul(UV_SCALE, delta))) & 0x3FFF


def _pack_xy(projected):
    bias = _raw(XY_BIAS)
    inv_w = _vu_div(_raw(1.0), projected[3])
    x = _ftoi4(_vu_add(_vu_mul(projected[0], inv_w), bias)) & 0xFFFF
    y = _ftoi4(_vu_add(_vu_mul(projected[1], inv_w), bias)) & 0xFFFF
    return x, y


def _outside(x, y):
    sx = (x & 0xFFFF) / 16.0 - 2048.0
    sy = (y & 0xFFFF) / 16.0 - 2048.0
    return abs(sx) > CLIP or abs(sy) > CLIP


def _transform(matrix, hx, column, row):
    acc = [0, 0, 0, 0]
    for lane, value in enumerate((hx, column, row, _raw(1.0))):
        acc = [_vu_add(acc[i], _vu_mul(matrix[lane][i], value)) for i in range(4)]
    return acc


def project_strips(rows, matrix, step, clip=0):
    """Kicked strips for one tile.

    rows is the uploaded sequence (record 1, record 2, ...). Each vertex is
    (x, y, u, v, adc) with x and y the GS 12.4 integers. Calls 0 and 1 are not
    kicked. With clip clear, adc is 0.
    """
    step_bits = step if isinstance(step, int) else _raw(step)
    made = []
    uvs = []
    for k, samples in enumerate(rows):
        z = _vu_mul(_raw(k), step_bits)
        positions = []
        coords = []
        for i in range(31):
            column = i + 1
            here = samples[column]
            left = samples[column - 1]
            prev = rows[k - 1][column] if k else 0
            positions.append(_transform(matrix, _itof4(here), _vu_mul(_raw(i), step_bits), z))
            coords.append((
                _uv(_vu_add(_itof4(prev), _itof4(here) ^ 0x80000000)),
                _uv(_vu_add(_itof4(left), _itof4(here) ^ 0x80000000)),
            ))
        made.append(positions)
        uvs.append(coords)
    strips = []
    for k in range(2, len(rows)):
        verts = []
        sticky = False
        for i in range(31):
            cx, cy = _pack_xy(made[k][i])
            px, py = _pack_xy(made[k - 1][i])
            for x, y, uv in (
                (cx, cy, uvs[k][i]),
                (px, py, uvs[k - 1][i]),
            ):
                if clip and (sticky or _outside(x, y)):
                    sticky = True
                    adc = 1
                else:
                    adc = 0
                verts.append((x, y, uv[0], uv[1], adc))
        strips.append(verts)
    return strips


def _sat16(value):
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return value


def _padd(a, b):
    return [_sat16(x + y) for x, y in zip(a, b)]


def _psub(a, b):
    return [_sat16(x - y) for x, y in zip(a, b)]


def _psrah(a, n):
    return [x >> n for x in a]


def _psllh(a, n):
    out = []
    for x in a:
        v = (x << n) & 0xFFFF
        out.append(v - 0x10000 if v & 0x8000 else v)
    return out


def _pand(a, b):
    out = []
    for x, y in zip(a, b):
        v = (x & 0xFFFF) & (y & 0xFFFF)
        out.append(v - 0x10000 if v & 0x8000 else v)
    return out


def _qfsrv(high, low, sa_bytes):
    packed = 0
    for i in range(8):
        packed |= (low[i] & 0xFFFF) << (16 * i)
        packed |= (high[i] & 0xFFFF) << (16 * (i + 8))
    packed >>= sa_bytes * 8
    out = []
    for i in range(8):
        v = (packed >> (16 * i)) & 0xFFFF
        out.append(v - 0x10000 if v & 0x8000 else v)
    return out


def _groups(row):
    return [list(row[i * 8:(i + 1) * 8]) for i in range(4)]


def _ungroups(groups):
    return [v for group in groups for v in group]


def mask_allows(mask, column, row):
    """True when the step may change this sample. Bit 15 is the first row of a bank."""
    base = 0 if row < 16 else 64
    word = struct.unpack_from('<h', mask, base + column * 2)[0]
    return ((word >> (15 - (row & 15))) & 1) == 1


def step_grid(heights, disturb, gap, mask):
    """One height step. heights is 33×32, disturb 32×32, gap 32, mask 128 bytes.

    Returns new copies. Height row 0 is replaced by the damped gap velocity.
    Disturbance row r drives height row r+1. Disturbance row 31 is not used.
    A clear mask bit stores velocity 0 and leaves that height sample as it was,
    except row 0, which is replaced either way.
    """
    field = [list(row) for row in heights]
    velocity = [list(row) for row in disturb]
    spare = list(gap)
    zero = [0] * 8
    held = [list(zero) for _ in range(4)]
    older = [list(zero) for _ in range(4)]
    previous = [list(zero) for _ in range(4)]
    row_index = 1
    velocity_row = -1
    for phase in range(2):
        base = 0 if phase == 0 else 64
        halfs = [struct.unpack_from('<h', mask, base + c * 2)[0] for c in range(32)]
        gates = _groups(halfs)
        end = row_index + 16
        while row_index != end:
            saved = held
            held = _groups(field[row_index])
            sums = []
            right = []
            for i in range(4):
                nxt = held[i + 1] if i < 3 else zero
                right.append(_padd(held[i], _qfsrv(nxt, held[i], 2)))
            for i in range(4):
                prv = zero if i == 0 else held[i - 1]
                sums.append(_padd(right[i], _qfsrv(held[i], prv, 14)))
            source = spare if velocity_row < 0 else velocity[velocity_row]
            source_g = _groups(source)
            out_v = []
            out_h = []
            new_gates = []
            for i in range(4):
                acc = _padd(sums[i], previous[i])
                acc = _padd(acc, older[i])
                acc = _psub(acc, saved[i])
                acc = _psrah(acc, 3)
                acc = _psub(acc, saved[i])
                acc = _psrah(acc, 2)
                vel = _padd(source_g[i], acc)
                bit = _psrah(gates[i], 15)
                vel = _pand(vel, bit)
                new_gates.append(_psllh(gates[i], 1))
                vel = _psub(vel, _psrah(vel, 7))
                out_v.append(vel)
                out_h.append(_padd(saved[i], vel))
            gates = new_gates
            dest = spare if velocity_row < 0 else velocity[velocity_row]
            flat = _ungroups(out_v)
            dest[:] = flat
            field[row_index - 1] = _ungroups(out_h)
            older = [list(g) for g in previous]
            previous = [list(g) for g in sums]
            velocity_row += 1
            row_index += 1
    return field, velocity, spare


def _copy_lists(rows):
    return [list(row) for row in rows]


def seam_columns(this_h, this_d, other_h, other_d):
    """Slot 0. Other column 30 fills this column 0; this column 1 fills other column 31."""
    heights = _copy_lists(this_h)
    velocity = _copy_lists(this_d)
    other_heights = _copy_lists(other_h)
    other_velocity = _copy_lists(other_d)
    for row in range(1, 33):
        heights[row][0] = other_h[row][30]
        other_heights[row][31] = this_h[row][1]
    for row in range(32):
        velocity[row][0] = other_d[row][30]
        other_velocity[row][31] = this_d[row][1]
    return heights, velocity, other_heights, other_velocity


def seam_rows(this_h, this_d, other_h, other_d):
    """Slot 2 (payload +4). Other's far row fills this near row, and the reverse."""
    heights = _copy_lists(this_h)
    velocity = _copy_lists(this_d)
    other_heights = _copy_lists(other_h)
    other_velocity = _copy_lists(other_d)
    heights[1] = list(other_h[31])
    other_heights[32] = list(this_h[2])
    velocity[0] = list(other_d[30])
    other_velocity[31] = list(this_d[1])
    return heights, velocity, other_heights, other_velocity


def block_expired(frame, stamp):
    """True when the simulation drops the block. A signed difference of 200 or more."""
    diff = (int(frame) - int(stamp)) & 0xFFFFFFFF
    if diff >= 0x80000000:
        diff -= 0x100000000
    return diff >= KEEP_FRAMES


def splash_seed(seed):
    """The drawer's generator. The second value is true when a splash is spawned."""
    new = (int(seed) * LCG_MUL + LCG_ADD) & 0xFFFFFFFF
    return new, (new >> 16) % SPLASH_MODULUS == 0


def _unit(seed):
    return _cpu_mul(ee_emu.fp_from_int(int(seed) >> 16, _CPU), SPLASH_UNIT)


def _along(lo, hi, unit):
    return _cpu_add(lo, _cpu_mul(_cpu_sub(hi, lo), unit))


def splash_point(seed, bounds):
    """The point the drawer passes to water_disturb, after the option and freeze gates.

    bounds is six raw float bits: minimum x, y, z then maximum x, y, z. A miss
    returns the advanced seed and None. A hit returns the seed after three steps
    and the disturb point. z is the minimum; the z extent is multiplied by the
    same unit interval and then not used. x and y share that interval.
    """
    seed1, hit = splash_seed(seed)
    if not hit:
        return seed1, None
    seed2, _again = splash_seed(seed1)
    unit = _unit(seed2)
    min_x, min_y, min_z, max_x, max_y, _max_z = (int(b) & 0xFFFFFFFF for b in bounds)
    return splash_seed(seed2)[0], (_along(min_x, max_x, unit), _along(min_y, max_y, unit), min_z)


def _trunc(bits):
    return ee_emu.s32(ee_emu.fp_to_int(bits))


def disturb_cells(grid, strength, radius, origin, span, pos):
    """One chunk's water_disturb writes. Returns a new 32×32 grid.

    strength, radius, span (min x, max x) and pos (x, y) are raw float bits.
    origin is the two signed integers at chunk +0x28 and +0x2c. The grid row is
    the world-x cell and the column is the world-y cell. z is not read.
    """
    out = [list(row) for row in grid]
    ox = _cpu_mul(ee_emu.fp_from_int(int(origin[0]), _CPU), _raw(0.25))
    oy = _cpu_mul(ee_emu.fp_from_int(int(origin[1]), _CPU), _raw(0.25))
    width = _cpu_sub(int(span[1]) & 0xFFFFFFFF, int(span[0]) & 0xFFFFFFFF)
    count = _trunc(_cpu_add(_cpu_mul(width, DISTURB_WIDTH), _raw(0.5)))
    inv = ee_emu.fp_div(CLAIM_ONE, _cpu_mul(ee_emu.fp_from_int(count, _CPU), _raw(12.0)), _CPU)
    scale = _raw(32.0)
    dx = _cpu_mul(_cpu_mul(_cpu_sub(int(pos[0]) & 0xFFFFFFFF, ox), scale), inv)
    dy = _cpu_mul(_cpu_mul(_cpu_sub(int(pos[1]) & 0xFFFFFFFF, oy), scale), inv)
    gx = _cpu_add(dx, _raw(16.0))
    gy = _cpu_add(dy, _raw(16.0))
    reach = _cpu_mul(_cpu_mul(int(radius) & 0xFFFFFFFF, scale), inv)
    limit = _cpu_mul(reach, reach)
    gain = ee_emu.fp_div(int(strength) & 0xFFFFFFFF, limit, _CPU)
    radius_bits = int(radius) & 0xFFFFFFFF

    def window(centre):
        lo = _trunc(_cpu_sub(_cpu_sub(centre, radius_bits), CLAIM_ONE))
        hi = _trunc(_cpu_add(_cpu_add(centre, radius_bits), CLAIM_ONE))
        return max(0, lo), min(31, hi)

    x0, x1 = window(gx)
    y0, y1 = window(gy)
    if x1 < x0 or y1 < y0:
        return out
    for row in range(x0, x1 + 1):
        for col in range(y0, y1 + 1):
            gap_x = _cpu_sub(ee_emu.fp_from_int(row, _CPU), gx)
            gap_y = _cpu_sub(ee_emu.fp_from_int(col, _CPU), gy)
            dist = _cpu_add(_cpu_mul(gap_x, gap_x), _cpu_mul(gap_y, gap_y))
            if ee_emu.fp_cmp(limit, dist) < 0:
                continue
            amount = ee_emu.fp_to_int(_cpu_sub(int(strength) & 0xFFFFFFFF, _cpu_mul(dist, gain)))
            total = (int(out[row][col]) + ee_emu.s32(amount)) & 0xFFFFFFFF
            signed = ee_emu.s32(total)
            out[row][col] = 32767 if signed > 32767 else _s16(total)
    return out


def second_particle_z(terrain, seed):
    """z of the second particle. seed is the hit value splash_point returned.

    The first particle uses the terrain height itself. x and y stay on the
    disturb point. Order is the unit interval, times 80, plus the terrain, plus 24.
    """
    lift = _cpu_mul(_unit(seed), PARTICLE_RISE)
    return _cpu_add(_cpu_add(int(terrain) & 0xFFFFFFFF, lift), PARTICLE_LIFT)


def _s16(word):
    low = word & 0xFFFF
    return low - 0x10000 if low & 0x8000 else low


def claim_grid(neighbours):
    """The grid water_init writes when a block is claimed.

    neighbours is four height grids, or None where that slot is absent, in
    payload order. Each grid is 33 rows of 32 signed samples. The result's
    height row 0 is zeros: the original leaves that row untouched and writes
    rows 1..32. Every disturbance sample is cleared.
    """
    slots = tuple(neighbours)
    heights = [[0] * SAMPLES for _ in range(ROWS)]
    disturb = [[0] * SAMPLES for _ in range(SAMPLES)]
    for row in range(SAMPLES):
        for col in range(SAMPLES):
            parts = []
            if col < 10 and slots[0] is not None:
                parts.append((slots[0][row + 1][31], 10 - col))
            if row < 10 and slots[2] is not None:
                parts.append((slots[2][32][col], 10 - row))
            if col >= 22 and slots[1] is not None:
                parts.append((slots[1][row + 1][0], col - 21))
            if row >= 22 and slots[3] is not None:
                parts.append((slots[3][1][col], row - 21))
            hsum = 0
            wsum = 0
            for sample, dist in parts:
                weight = _cpu_mul(ee_emu.fp_from_int(dist, _CPU), EDGE_WEIGHT)
                hsum = _cpu_add(hsum, _cpu_mul(ee_emu.fp_from_int(int(sample), _CPU), weight))
                wsum = _cpu_add(wsum, weight)
            if ee_emu.fp_cmp(wsum, CLAIM_ONE) < 0:
                wsum = CLAIM_ONE
            heights[row + 1][col] = _s16(ee_emu.fp_to_int(ee_emu.fp_div(hsum, wsum, _CPU)))
    return heights, disturb
