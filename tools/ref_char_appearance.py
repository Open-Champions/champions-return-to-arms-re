"""Authored appearance rules; all resource text is supplied from private inputs.

No dependency on EE execution. Limits describe the isolated menu helpers, not
proof that every combination can be reached through the rendered front end.
"""


def adjust(value, delta, lower, upper, reset=0):
    """Original helpers test the old value, then add; they do not clamp delta."""
    if delta == 0:
        return reset, 0
    accepted = (delta > 0 and value < upper) or (delta < 0 and value > lower)
    return ((value + delta + 128) % 256 - 128, 1) if accepted else (value, 0)


def normalized_hair(skin):
    return {0: 0, 3: 1, 4: 2}.get(skin, -1)


def appearance_record(choices, hair_count, optional_hair):
    hair, colour, beard, skin = choices
    return (-1 if hair_count == optional_hair else hair, colour, beard, skin)


def scan_variants(prefix, formats, present, optional_hair, initial_colour):
    """Sequential scan stops at the first missing entry, including colour gaps.

    formats: body texture, hair mesh/texture, beard mesh/texture. The colour
    count is overwritten by each successful hair style, not a union or max.
    Returns counts and the ordered lookup names, including terminating misses.
    """
    requests = []

    def lookup(index, *args):
        name = formats[index] % ((prefix,) + args)
        requests.append(name)
        return name in present

    body = 0
    while lookup(0, body + 1):
        body += 1
    totals = []
    colour = initial_colour
    for mesh_format, texture_format in ((1, 2), (3, 4)):
        styles = 0
        while lookup(mesh_format, styles + 1):
            colours = 0
            while lookup(texture_format, styles + 1, 97 + colours):
                colours += 1
            if not colours:
                break
            styles += 1
            if mesh_format == 1:
                colour = colours
        totals.append(styles)
    return (body, totals[0] + bool(optional_hair), colour, totals[1] + 1), requests


def constructor_requests(prefix, formats, choices):
    """Return (object offset, name) in original constructor request order.

    formats: hair mesh/texture, beard mesh/texture, body mesh/texture.
    Missing optional styles omit both requests; lookup failure remains null.
    """
    hair, colour, beard, skin = choices
    requests = []
    for style, pair, offsets in ((hair, (0, 1), (0x548, 0x558)),
                                  (beard, (2, 3), (0x54c, 0x554))):
        if style != -1:
            requests.extend(((offsets[0], formats[pair[0]] % (prefix, style + 1)),
                             (offsets[1], formats[pair[1]] % (prefix, style + 1, 97 + colour))))
    requests.extend(((0x544, formats[4] % prefix),
                     (0x550, formats[5] % (prefix, skin + 1))))
    return requests
