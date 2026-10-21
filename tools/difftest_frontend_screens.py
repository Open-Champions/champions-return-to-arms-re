#!/usr/bin/env python3
"""State-by-state draw captures of the remaining front-end screens, SLUS-20973 v2.00.

Usage: difftest_frontend_screens.py path/to/SLUS_209.73 [--print-table]

Each screen function is run under tools/ee_emu.py with every callee stubbed
(text width and lookups return zero) after its state word is forced to each
value of its jump table; the UI primitive calls it makes are compared with
tools/ref_frontend_screens.py at seeds 20973 and 7. Only addresses and numeric
arguments are recorded: text keys are recorded by call site, never by content.
No image, sound, text or game bytes are saved. These are fixture captures: the
forced states are not claimed to be reachable in that order in the real game.
"""
import hashlib
import os
import sys

sys.path.append(os.path.dirname(__file__))
from ee_emu import EE  # noqa: E402
import scan_lookup_sites  # noqa: E402
from ref_frontend_screens import (BROWSER_STATES, IMPORT_STATES,  # noqa: E402
                                  LOOKUP_SITES, MESSAGE_BOX_CALLS, PLAYERSEL_PHASES,
                                  SLOTLIST_STATES)

SHA256 = "292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675"
SEEDS = (20973, 7)

# Primitive targets (symbols/ui.tsv, symbols/audio-save.tsv) and our short names.
KIND = {
    0x1800B8: "text_begin", 0x181CA0: "centered", 0x181C10: "wide",
    0x181280: "wrapped", 0x181AA0: "ascii", 0x181AF8: "ascii_centered",
    0x181530: "wrapped_centered", 0x17FB68: "sprite", 0x17C118: "frame",
    0x17BD30: "rect", 0x1803E0: "clip", 0x1802E0: "colour",
    0x173C84: "key", 0x17365C: "lump", 0x1DF248: "msgbox",
    # Helpers recorded by call site only (symbols/ui.tsv, symbols/audio-save.tsv).
    0x1EB0F8: "class_name",      # text_getClassName
    0x1EACB8: "pad_glyph",       # pad_buttonMaskToGlyph
    0x22BE68: "name_run",        # nameEntry_run
    0x22C920: "name_draw",       # nameEntry_draw
    0x1DF5EC: "fade_step",       # hud_stepFade
}
SITE_ONLY = ("key", "msgbox", "lump", "class_name", "pad_glyph", "name_run",
             "name_draw", "fade_step")


# Font pointer words: 0x4f7100 is the medium font and 0x4f7104 the small one
# (research-ui docs/formats/ui-fonts.md, startup 0x323f64-0x323fa4). Sentinels
# let a text_begin record name which word its first argument was read from.
FONT_SENTINELS = {0x4F7100: 0xF0F0F0F0, 0x4F7104: 0xF1F1F1F1}
FONT_NAMES = {0xF0F0F0F0: "medium", 0xF1F1F1F1: "small"}


def seed_fonts(e):
    for addr, value in FONT_SENTINELS.items():
        e.mem.w32(addr, value)


def record(call):
    """One normalised record; pointer arguments are dropped."""
    a = [v & 0xFFFFFFFF for v in call.args[:7]]
    kind = KIND[call.target]
    if kind == "text_begin":       # (font, layer, colour)
        return (call.site, kind, FONT_NAMES.get(a[0], a[0]), a[1], a[2])
    if kind in ("centered", "wide", "wrapped", "ascii", "ascii_centered"):
        return (call.site, kind, a[0], a[1])
    if kind == "wrapped_centered":
        return (call.site, kind, a[0], a[1], a[3], a[4], a[5])
    if kind == "frame":            # (x, y, w, h, layer, tint, style)
        return (call.site, kind, *a[:7])
    if kind == "colour":
        return (call.site, kind, a[0])
    if kind in SITE_ONLY:
        return (call.site, kind)
    return (call.site, kind, *a[:6])


def emulator(path, seed):
    e = EE(path)
    e.mem.auto_map = True
    e.mem.w32(0x404460, seed)
    e.follow = set()
    seed_fonts(e)
    return e


def sweep(path, seed, entry, setup, values, args=()):
    out = {}
    for value in values:
        e = emulator(path, seed)
        setup(e, value)
        e.call(entry, *args, max_steps=300000)
        out[value] = tuple(record(c) for c in e.calls if c.target in KIND)
    return out


def playersel(e, phase):
    e.mem.w8(0x8E2C02, phase)         # phase byte; jump table 0x5404A0, 16 entries
    e.mem.w32(0x8E2C44, 0x3F800000)   # fade float must equal 1.0 to reach it


def slotlist(e, state):
    e.mem.w32(0x88D3DC, state)        # jump table 0x53F7F0, 16 entries


def browser(e, state):
    e.mem.w32(0x88D3E0, state)        # jump table 0x53F440, 35 entries


def importer(e, state):
    e.mem.w32(0x88D3A8, state)        # jump table 0x53FB10, 24 entries


def capture_all(path, seed):
    return {
        "playersel": sweep(path, seed, 0x225478, playersel, range(16)),
        "slotlist": sweep(path, seed, 0x21C3A4, slotlist, range(16)),
        "browser": sweep(path, seed, 0x219B90, browser, range(35)),
        "import": sweep(path, seed, 0x21FA2C, importer, range(24)),
    }


def message_box(path, seed):
    e = emulator(path, seed)
    e.follow = {0x1DF248}
    title = e.alloc(64)
    body = e.alloc(64)
    e.mem.write(title, b"T\x00\x00\x00")
    e.mem.write(body, b"B\x00\x00\x00")
    e.call(0x1DF248, title, body, 0, 0, 0, 0, max_steps=300000)
    # Drop the wide-string pointer (argument 2 of the wrapped-centered calls).
    return tuple((c.site, c.target, *(v & 0xFFFFFFFF for i, v in enumerate(c.args[:7])
                                      if not (c.target == 0x181530 and i == 2)))
                 for c in e.calls)


LOOKUP_RANGES = {
    "frontend_run": (0x1E08F0, 0x1E1F34), "player_selection": (0x225478, 0x22A360),
    "slot_list": (0x21C3A4, 0x21E5C8), "name_entry_run": (0x22BE68, 0x22C920),
    "credits_load": (0x223C64, 0x223D3C), "credits_run": (0x223D3C, 0x2243F8),
    "intro": (0x321788, 0x321870), "logo": (0x321640, 0x321700),
    "card_import": (0x21FA2C, 0x221840), "browser": (0x219B90, 0x21C3A4),
}

# Player-selection menu sounds that execute with the lockstep pad words set to one
# mask in every slot: (phase, mask) -> (res_find site, entry name, sound site).
# Masks follow docs/netcode.md:138 (0x40 cross, 0x20 circle, 0x4000 down; the face
# buttons are Inferred there). Lookup name and sound call are the executed pair.
# (3, 0x20) shows why the static scan is only a candidate list: site 0x227D50 has a
# constant entry name in its own lui/addiu pair, yet it executes with another
# name because a branch reaches the call with a different register value.
PLAYERSEL_SOUNDS = {
    (1, 0x40): (0x226120, "menu_main_accept.anm", 0x226130),
    (1, 0x20): (0x226178, "menu_main_back.anm", 0x22618C),
    (3, 0x40): (0x227BA4, "menu_main_accept.anm", 0x227BC0),
    (3, 0x20): (0x227D50, "menu_main_back.anm", 0x227D64),
    (3, 0x4000): (0x227CA8, "menu_main_accept.anm", 0x227CBC),
}


def playersel_sound(path, seed, phase, mask):
    e = emulator(path, seed)
    playersel(e, phase)
    for slot in range(4):
        for offset in (0, 4, 8):  # held / pressed / repeat words, 0x58 per slot
            e.mem.w32(0x41BFE0 + slot * 0x58 + offset, mask)
    e.call(0x225478, max_steps=300000)
    look = [c for c in e.calls if c.target == 0x17365C]
    snd = [c for c in e.calls if c.target == 0x214230]
    assert len(look) == len(snd) == 1, (phase, mask, len(look), len(snd))
    return (look[0].site, e.mem.cstr(look[0].args[1] & 0xFFFFFFFF), snd[0].site)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    path = args[0]
    with open(path, "rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if digest != SHA256:
        raise SystemExit("wrong executable SHA-256")
    if "--print-table" in sys.argv:
        cap = capture_all(path, SEEDS[0])
        for name, table in cap.items():
            print(name.upper(), table)
        print("MESSAGE_BOX", message_box(path, SEEDS[0]))
        return
    checks = 0
    wanted = {"playersel": PLAYERSEL_PHASES, "slotlist": SLOTLIST_STATES,
              "browser": BROWSER_STATES, "import": IMPORT_STATES}
    for seed in SEEDS:
        cap = capture_all(path, seed)
        for name, table in cap.items():
            for state, records in table.items():
                assert records == wanted[name][state], (seed, name, state, records)
                checks += 1
        assert message_box(path, seed) == MESSAGE_BOX_CALLS, seed
        checks += 1
        for (phase, mask), wanted_sound in PLAYERSEL_SOUNDS.items():
            assert playersel_sound(path, seed, phase, mask) == wanted_sound, (
                seed, phase, mask)
            checks += 1
    probe = EE(path)
    for name, (lo, hi) in LOOKUP_RANGES.items():
        assert tuple(scan_lookup_sites.scan(probe, lo, hi)) == LOOKUP_SITES[name], name
        checks += 1
    print("PASS frontend screen state captures: %d checks; seeds 20973, 7" % checks)


if __name__ == "__main__":
    main()
