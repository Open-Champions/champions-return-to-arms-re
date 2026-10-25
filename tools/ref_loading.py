"""Small, independently written loading-transition model for RTA US v2.00.

Inputs are names, displayed-frame counts and synthetic stream directory names.
No game assets or executable bytes are embedded here.
"""


def picture_alias(name):
    if "blo" in name:
        return "blood1"
    if name == "innovat2":
        return "innova2"
    if "val" in name:
        return "valor"
    if "bas" in name:
        return "bastion1"
    if "nitdung" in name:
        return {"nitdung1": "nitdun1", "nitdung2": "nitdun2",
                "nitdung4": "nitdun4"}.get(name, name)
    if "torme" in name:
        return {"tormenta": "torma", "tormentb": "tormb",
                "torment2": "torm2", "torment3": "torm3"}.get(name, name)
    if name == "pvpfire2":
        return "pvpfir2"
    return name


def picture_lump(name, available):
    """The candidate is truncated before the .lmp suffix; missing art falls back."""
    candidate = ("l" + picture_alias(name))[:8] + ".lmp"
    return candidate if candidate.lower() in {x.lower() for x in available} else "lmiss.lmp"


def strip_positions(displayed_frame, strip_width=640):
    x = displayed_frame % strip_width
    return x, x - strip_width


def fade_channel(value):
    """One gfx_present channel step toward neutral 0x80."""
    if value >= 133:
        return value - 4
    if value < 124:
        return value + 4
    return 128


def entry_music(names, recall=False):
    """Return (action, name) for the loader's stream-2 entry decision."""
    if recall:
        return "keep", None
    for name in names:
        if "enttag" in name:
            return "play", name
    return "stop", None
