"""Small, independently authored factory reference for the initial hub load.

The table contains constructor addresses and pool sizes, never level data.  A
record from objects.ob is an object only if the original factory allocates it;
the host's "unbuilt" counter describes unsupported constructed classes, not
necessarily creatures.  The five hostile examples exercise factory branches
that the current native host says it ports.
"""

FACTORY = {
    "apprings": (0x498, 0x24388C, "portal prop"),
    "portal": (0x164, 0x27C694, "portal"),
    "player1": (0x4C, 0x158928, "start marker"),
    "savepoint": (0x118, 0x28CB90, "save point"),
    "npc": (0x480, 0x29DF04, "friendly creature"),
    "pushtrigger": (0x4C, 0x1EC900, "trigger"),
    "trigger": (0x70, 0x1ECDF4, "trigger"),
    "charambient_light": (0x4C, 0x158BCC, "light marker"),
    "chardirectional_light": (0x4C, 0x158C6C, "light marker"),
    "chardirectional_lightd": (0x4C, 0x158D0C, "light marker"),
    "gnaw": (0x3C8, 0x26741C, "hostile creature"),
    "smallspider": (0x3C8, 0x2AB450, "creature"),
    "mosquito": (0x3C8, 0x297788, "hostile creature"),
    "scorpion": (0x3D0, 0x2A4D68, "hostile creature"),
    "badger": (0x3D0, 0x244018, "hostile creature"),
    "warboar": (0x3D8, 0x2BA03C, "hostile creature"),
}


def classify(name, properties=()):
    """Return (pool size, constructor, role), or None for no constructed object.

    `bflya`/`bflyb` are recognized by the `critter` property fallback, not
    their class strings.  Ambient level lighting and clearColor/customVars
    remain side effects or level metadata; none creates a GameObject.
    """
    key = name.lower()
    if key in FACTORY:
        return FACTORY[key]
    if key.startswith("mosquito"):
        return FACTORY["mosquito"]
    if key.startswith("badger"):
        return FACTORY["badger"]
    if key.startswith("warboar"):
        return FACTORY["warboar"]
    if any(p.lower().startswith("critter=") and p.split("=", 1)[1] != "0"
           for p in properties):
        return (0x448, 0x2547FC, "ambient critter")
    return None


def hub_counts(records):
    """Count factory objects and hostile actors separately for a parsed hub blob."""
    built = [classify(r["class"], r["properties"].split(";")) for r in records]
    return (sum(x is not None for x in built),
            sum(x is not None and x[2] == "hostile creature" for x in built))
