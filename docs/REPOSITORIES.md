# Repository ownership

Open Champions now separates research, each game's original source reconstruction,
and the shared native client. There is one active code location for each task.

| Repository | Owns | Does not claim |
|---|---|---|
| [champions-return-to-arms-re](https://github.com/Open-Champions/champions-return-to-arms-re) | Existing RTA research, function inventory, symbols, formats, Python tools, patch hypotheses and online evidence | Reconstructed source or native-game completion from naming coverage |
| [champions-return-to-arms](https://github.com/Open-Champions/champions-return-to-arms) | Authored PS2 C++, reconstruction verifier, claims, ledger, receipts and measured progress | Whole-executable or gameplay completion from isolated byte matches |
| [champions-of-norrath](https://github.com/Open-Champions/champions-of-norrath) | Norrath's independent baseline intake, research and eventual source reconstruction | An identified baseline or transferable RTA addresses, counts and asset compatibility |
| [open-champions-godot](https://github.com/Open-Champions/open-champions-godot) | Shared native archive core and future Godot presentation/client for both games | A playable client from an inspector build or empty engine project |
| [.github](https://github.com/Open-Champions/.github) | Organization profile, central wordmarks and artwork credits | Official rights-holder affiliation |

## Migration

The Return to Arms source repository retains this repository's published history,
then narrows its current tree to reconstruction. Its function inventory is an
explicit provenance-pinned snapshot. Update it through a reviewed source change
when new research warrants it; all affected receipts must be reverified.

The Godot repository starts from the native/ subtree history, retaining the C++
archive core's commits. Native build, packaging and platform CI belong there. The
research repository's CI now checks only its Python tools, symbol maps and coverage.

The old docs/REBUILD.md and docs/NATIVE_PORT.md paths remain as migration pointers.
Original game inputs stay in private, ignored locations. No disc data was moved into
public repositories. Existing community lobby-server work remains external at
[Champions Reborn](https://github.com/HikikoMarmy/Champions-Reborn-Server); it is not duplicated here.
