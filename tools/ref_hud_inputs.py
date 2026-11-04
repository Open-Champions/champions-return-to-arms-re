"""Bounded upstream automap inputs for the original HUD (SLUS-20973 v2.00).

The projector is modelled separately by ref_hud_minimap. These producers
prepare its grid. Values here are authored descriptions of addressed behaviour,
not copied game data. `reveal_world` is the fractional-position claim.
`reveal_integer_cell` remains the exact cell-centre path.
"""
import math

GRID_SIDE = 216                 # 0x168934/0x169870
GRID_STRIDE = GRID_SIDE * 2    # 0x168954: 0x1b0 bytes


def load_grid(texture, grid_pointer, keep_raw, x0, y0, width, height, cells,
              old_width=0, old_height=0, old_origin=(0.0, 0.0), old_grid=None):
    """automap_loadGrid 0x168894: returns (width, height, origin, 216x216 cells).

    The supplied cells are a row-major width*height sequence. Only test cases
    fitting the fixed grid are permitted. Existing cells beyond copied rows are
    retained, as the original function does not clear them.
    """
    grid = list(old_grid) if old_grid is not None else [0] * (GRID_SIDE * GRID_SIDE)
    if not texture or not grid_pointer:
        return 0, 0, old_origin, grid
    if keep_raw:
        return old_width, old_height, old_origin, grid
    if not 0 <= width <= GRID_SIDE or not 0 <= height <= GRID_SIDE:
        raise ValueError('model requires an in-bounds automap grid')
    if len(cells) != width * height:
        raise ValueError('cell count does not match dimensions')
    for row in range(height):
        base = row * GRID_SIDE
        grid[base:base + width] = cells[row * width:(row + 1) * width]
    return width, height, (float(x0), float(y0)), grid


def reveal_integer_cell(grid, width, height, cx, cy):
    """0x16a4b0 for an exact integer cell centre, before the projector gate.

    A radius-eight disk raises only bits 12..15. The input is the loaded grid,
    including any older exploration; the maximum nibble wins.
    """
    out = list(grid)
    for y in range(max(0, cy - 8), min(height - 1, cy + 8) + 1):
        for x in range(max(0, cx - 8), min(width - 1, cx + 8) + 1):
            r2 = (cx - x) ** 2 + (cy - y) ** 2
            if r2 > 64:
                continue
            level = max(0, round((1.0 - math.sqrt(r2) * 0.125) * 254.0)) >> 4
            at = y * GRID_SIDE + x
            old = out[at]
            out[at] = (old & 0x0fff) | (max(old >> 12, level) << 12)
    return out


def blip_sources(nearby, players, network):
    """minimap_draw 0x1e4b88..0x1e4c78, after world_collectObjectsInBox.

    nearby is ordered (object_id, flags) and players is an ordered sequence of
    (real_object_id or None, owner_machine_object_id). Network play removes all
    queried player-flag objects, then appends one net_objOrGhost result for each
    player with a real object. Offline it passes the query through unchanged.
    """
    if not network:
        return [object_id for object_id, _flags in nearby]
    return ([object_id for object_id, flags in nearby if not flags & 0x40] +
            [owner_object for real_object, owner_object in players if real_object is not None])


def blip_query_box(camera_x, camera_y, spectated_z, reveal_all):
    """minimap_draw 0x1e4ae0..0x1e4b80; 200 object slots, box not circle."""
    radius = 3840.0 if reveal_all else 960.0
    return ((camera_x - radius, camera_y - radius, spectated_z - radius),
            (camera_x + radius, camera_y + radius, spectated_z + radius), 200)


def reveal_world(grid, width, height, origin_x, origin_y, world_x, world_y):
    """automap reveal 0x16a4b0 for any world position, including fractions.

    The cell is origin + world * 0.25 * (1/30), the same product 0x16a7dc writes.
    A disk of squared radius 64 raises bits 12..15. The level is
    round-half-away-from-zero of (1 - sqrt(dx^2+dy^2) * 0.125) * 254, clamped
    at 255, then shifted down four bits. Arithmetic is ref_core's default FPU,
    which is the ee_emu model these difftests run. Bits 0..11 of each cell stay.
    """
    import ref_core as F

    zero, half = 0, 0x3F000000
    eight, eight_half, neg_eight_half = 0x41000000, 0x41080000, 0xC1080000
    cell_x = F.add(origin_x, F.mul(F.mul(world_x, 0x3E800000), 0x3D088888))
    cell_y = F.add(origin_y, F.mul(F.mul(world_y, 0x3E800000), 0x3D088888))

    def low_edge(cell):
        shifted = F.sub(cell, eight)
        edge = (F.to_int(F.add(shifted, half)) if F.le(zero, shifted)
                else F.to_int(F.add(cell, neg_eight_half)))
        return 0 if edge < 0 else edge

    def high_edge(cell, limit):
        shifted = F.add(cell, eight)
        edge = (F.to_int(F.add(cell, eight_half)) if F.le(zero, shifted)
                else F.to_int(F.sub(shifted, half)))
        cap = limit - 1
        return cap if cap < edge else edge

    out = list(grid)
    y0, y1 = low_edge(cell_y), high_edge(cell_y, height)
    x0, x1 = low_edge(cell_x), high_edge(cell_x, width)
    if y1 < y0:
        return out
    for y in range(y0, y1 + 1):
        if x1 < x0:
            continue
        for x in range(x0, x1 + 1):
            dx = F.sub(cell_x, F.from_int(x))
            dy = F.sub(cell_y, F.from_int(y))
            radius2 = F.add(F.mul(dx, dx), F.mul(dy, dy))
            if not F.le(radius2, 0x42800000):
                continue
            level = F.mul(F.sub(0x3F800000, F.mul(F.sqrt(radius2), 0x3E000000)), 0x437E0000)
            bits = (F.to_int(F.add(level, half)) if F.le(zero, level)
                    else F.to_int(F.sub(level, half)))
            if bits >= 0x100:
                bits = 0xFF
            at = y * GRID_SIDE + x
            old = out[at]
            high = (old >> 8) & 0xFF
            nibble = bits >> 4
            if (high >> 4) < nibble:
                high = (high & 0x0F) | ((nibble & 0xFF) << 4)
            out[at] = (old & 0x00FF) | (high << 8)
    return out


def gold_touch(flags, countdown, amount, slot, position):
    """Gold_onTouch 0x157a9c. Return (remaining amount, ordered effects).

    position is three raw float words. The first touch zeros the pile before a
    second toucher can take it; no game message mediates the event.
    """
    if flags & 0x20000 or countdown != 0 or not flags & 0x40 or amount == 0:
        return amount, []
    return 0, [('coin_sound',), ('add_floater', slot, position, amount), ('delete',)]
