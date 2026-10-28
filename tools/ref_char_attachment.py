"""Independent semantic reference for bounded character attachment probes.

Observed addresses: cover 0x1a3b90..0x1a3ccc; final gates and body hide-bit
updates 0x1a3e08..0x1a3f30; default/variant mask 0x179550; attachment selection
0x1760ec..0x17614c; mesh runs 0x178cbc..0x178d74. No executable or asset
content is embedded here. Token predicates are supplied by the caller.

Unknown: resource availability, native-frame body-mask consumption, animated
matrix evaluation, renderer output, and live visual parity. Invalid indices
are outside the authored 16-record attachment-table boundary, not clamped.
"""

U64 = (1 << 64) - 1


def cover_flag(model, slot, prior, paired, hits):
    """Five semantic substring predicates, in pinned-address order in harness."""
    if not paired:
        return bool(prior)
    n0, p1, p2, n3, p4 = hits
    head_cover = slot == 11 and not n0 and (model != 7 or not p1)
    body_cover = slot == 4 and ((model == 7 and p2) or
                               (model == 9 and (n3 or p4)))
    return bool(prior or head_cover or body_cover)


def appearance_gates(model, skin, covered, head_present, head_exception):
    hair = not covered or model == 11 or (model == 10 and skin == 4)
    beard = not covered or model == 11 or (head_present and
                                         (head_exception or model == 6))
    return hair, beard


def appearance_draws(model, skin, covered, head_present, head_exception, handles):
    """Return part ordinals; each pair is (mesh present, texture present)."""
    allowed = appearance_gates(model, skin, covered, head_present, head_exception)
    return tuple(i for i in range(2) if allowed[i] and all(handles[i]))


def clear_drawn_hide_bits(show, drawn_hide_masks):
    for hide in drawn_hide_masks:
        show &= ~hide
    return show & U64


def variant_show_mask(default_hidden, enabled, selection, records):
    """0x179550: ascending selected bits; each record's hide wins its show."""
    show = ~default_hidden & U64
    if enabled:
        for index, (add, hide) in enumerate(records):
            if (selection & 0xffffffff) & (1 << index):
                show = (show | add) & ~hide & U64
    return show


def initial_body_mask(counter, default_hidden, enabled, records):
    signed = (counter & 0xffffffff)
    if signed >= 0x80000000:
        signed -= 1 << 32
    return (U64 if signed < 0x111 else
            variant_show_mask(default_hidden, enabled, 1, records))


def attachment_index(header_index, override):
    """Header -1 disables attachment before override is considered."""
    if header_index == -1:
        return None
    index = header_index if override == -1 else override
    if not 0 <= index < 16:
        raise ValueError('outside authored attachment table')
    return index


def attachment_matrix(values, mirrored=False):
    """Nine row-major rotation values then origin -> packet's 3x4 matrix."""
    return tuple((-values[col] if mirrored else values[col]) if row == 0
                 else values[3 * row + col]
                 for col in range(3) for row in range(4))


def mesh_table_index(requested, count):
    if count < 1:
        raise ValueError('unrelocated or invalid table count')
    return min(max(requested, 0), count - 1)


def mesh_runs(boundaries, show_mask):
    """Visible adjacent mesh ranges coalesce, empty spans emit no reference."""
    count = len(boundaries) - 1
    if not 1 <= count <= 64:
        raise ValueError('outside authored mesh-count boundary')
    show_mask &= U64
    # Observed EE boundary: a variable 64-bit shift by 64 clears bit zero;
    # arithmetic right shifts repeat bit 63, so a final shown run never flushes.
    # This is original packet selection, not a correction of that behavior.
    if count == 64:
        show_mask &= ~1
        if show_mask & (1 << 63):
            tail = 63
            while tail > 0 and show_mask & (1 << (tail - 1)):
                tail -= 1
            show_mask &= (1 << tail) - 1
    result = []
    start = None
    for i in range(len(boundaries)):
        shown = i < len(boundaries) - 1 and bool(show_mask & (1 << i))
        if shown and start is None:
            start = boundaries[i]
        if not shown and start is not None:
            if boundaries[i] != start:
                result.append((start, boundaries[i] - start))
            start = None
    return tuple(result)
