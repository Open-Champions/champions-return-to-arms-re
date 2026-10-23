"""Bounded upstream automap inputs for the original HUD (SLUS-20973 v2.00).

The projector is modelled separately by ref_hud_minimap. These two producers
prepare its grid. Values here are authored descriptions of addressed behaviour,
not copied game data. The reveal model intentionally covers integer cell centres;
arbitrary floating-point positions remain outside this model's claim.
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


def gold_touch(flags, countdown, amount, slot, position):
    """Gold_onTouch 0x157a9c. Return (remaining amount, ordered effects).

    position is three raw float words. The first touch zeros the pile before a
    second toucher can take it; no game message mediates the event.
    """
    if flags & 0x20000 or countdown != 0 or not flags & 0x40 or amount == 0:
        return amount, []
    return 0, [('coin_sound',), ('add_floater', slot, position, amount), ('delete',)]
