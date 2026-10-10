# Contributing

Everyone is welcome, whatever your experience. This is a large job and it only gets done
if many people can add small, trustworthy pieces.

## What may not be committed

Nothing that comes from the game:

- the executable, the disc image, or anything unpacked from it (models, textures, audio,
  level files, compiled scripts);
- full disassembly or raw decompiler output;
- game text such as dialogue.

What is fine: addresses, names you chose, struct layouts, descriptions in your own words,
pseudo-code you wrote yourself, and short identifiers the game exposes (class names, script
command names, file names). The `.gitignore` is a whitelist to make mistakes hard; do not
weaken it.

Independently authored C++ reconstructions belong in the dedicated
[Return to Arms source repository](https://github.com/Open-Champions/champions-return-to-arms).
Native C++ and Godot work for both games belongs in
[open-champions-godot](https://github.com/Open-Champions/open-champions-godot).
Keep research, symbol maps and original-file analysis tools here. See
[the repository map](docs/REPOSITORIES.md) before starting work.

## The one rule about claims

Say how you know. Every statement in `FINDINGS.md` and the area documents is one of:

- **Observed** — you read it in the bytes at the address you give.
- **Inferred** — it follows from observations, but you did not see it directly.
- **Unknown** — not established; say what would settle it.

A wrong name costs more than a missing one, because people build on it. If you are not
sure what a function is, leave it unnamed or name only what you can prove
(`creature_setField2fc` beats `creature_applySlow` until you have seen who reads the
field). Nothing counts as confirmed on a running game unless someone ran it and says so.

## Adding symbols

Symbols are tab-separated: address in hex without `0x`, name, optional note.

```
001b9cb8	Player_usePotion	guarded against the prediction copy; menu path differs for the local player
```

- Put them in `symbols/<area>.tsv`, where the area is one from `docs/STATUS.md`.
  `names.tsv` is the original core list; fix mistakes there but add new work under
  `symbols/`.
- Functions: `Class_method` for members, `subsystem_verbNoun` otherwise. Globals: `g_name`.
- The note should carry the evidence or the caveat.
- Run `python3 tools/symtab.py check` (no conflicts, no malformed lines) and
  `python3 tools/coverage.py --write` before you open a pull request.

## Writing an area document

`docs/<area>.md` should let the next person skip the work you did: what the subsystem does,
its data structures as offset tables, the functions that matter, and what is still open.
Mark anything that reads per-machine state (camera, audio position, the local player slot,
menus, hardware timers, what was drawn) while changing shared game state — those are the
places online play breaks. `docs/OVERVIEW.md` explains the distinction.

## Testing on a running game

This is the biggest gap. If you can run two copies of the game against each other in
PCSX2, you can settle questions that reading cannot. Patches go in `patches/` as PCSX2
`.pnach` files: one change per patch, a description of what it does and what it costs, and
whether you tested it. Report results in an issue with what you did, on which frame or
scene, and what each screen showed.

Use the [two-client validation protocol](docs/VALIDATION.md) to compare a repeatable
baseline with one patch at a time. A run without a reproduced baseline is inconclusive
about whether a fix works.

## Working together

- Open an issue before starting a big area so two people do not map the same code.
- Small pull requests are easier to check than big ones.
- Disagreements about a name are settled by evidence: point at the address.
