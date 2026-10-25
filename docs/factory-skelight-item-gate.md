# Factory Skelight and first-level item gate (RTA US v2.00)

Executed with `tools/ee_emu.py` through
`tools/difftest_factory_skelight_gate.py` on the owner-supplied executable.
The difftest supplies only a synthetic pool block and the external lump
residency result. It retains no executable or asset bytes.

- The factory's Skelight call is at `0x15b608`. Its delay slot at `0x15b60c`
  sets the fifth integer argument (`t0`) to **1**. The difftest executes from
  `0x15b5e4`, observes the call arguments, and asserts that value.
- `game_loadLevel` calls the original string comparison at `0x1e5690` with
  `intro` at `0x53d678`. The comparison is case-sensitive: `INTRO` takes the
  non-front-end branch. An equal result branches to `0x1e5730`, skipping
  item loading. A different world calls lump residency at `0x1e56a4` with
  `hud.lmp` at `0x53d680`. Absent HUD executes the item loader call at
  `0x1e56bc` (`0x108434`); resident HUD goes to `0x1e5708` and skips it.
  The difftest reaches or skips that call in all three outcomes.

The branch and identities are observed. Whether an independently hosted
Godot level attach has the original `hud.lmp` residency is unknown. "First
game world after boot" remains an inference, not a substitute for the
residency result.
