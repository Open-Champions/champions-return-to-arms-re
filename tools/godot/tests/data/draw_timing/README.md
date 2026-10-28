These rows are independently authored portable C++ FakeClock/Capture controls.
They contain no game input, gameplay capture, native performance measurement, or
schema 3 native-emitter proof. No game, Godot, compiler, or GPU runs are needed by
the Python reader tests.

The captured schema 2 source contents match these repository-relative files at
revision `f694b6ce997aa18758c47afc4d615f018da24177`. This comparison establishes
source equivalence; it does not relabel the earlier capture's build revision:

| Source | SHA-256 of the Git blob (LF) |
| --- | --- |
| `tools/godot/tests/draw_timing_test.cpp` | `751561c34b1bbf7cb274abcf8fbd6ff161ff4e755f22b8516183f1ef33608d69` |
| `tools/godot/extension/src/rta_draw_timing.h` | `f5ac8d69ebb1fbb0e1772099be7d78dd2cb6a3d4dbc40d48ed0369974c7b4288` |

The capture receipt pinned the same source contents with CRLF line endings:
test source `a5ecc123e874f160d64ca1cb26b9576f40e2049d06e26f7a8d1c1c2e6b1270a3`,
header `c49ccad8e9953886b9c9a793a0b79cf14c51832108208128d99b5ac1fdd9f16b`.
Normalizing those captured source bytes to LF gives the Git blob hashes above.
The authored clock increments one tick per read and advances by explicit work
values; `Capture` writes numeric diagnostics to memory.

`accounting.rows`, `cuts.rows`, `same_frame.rows`, `invalid_tag.rows`,
`command_limit.rows`, `null_command.rows`, and `unwind.rows` are complete outputs
of the correspondingly named portable control cases. `cap.rows` contains only
records 1 and 64 of the authored 64-row cap case. The independent-record parser
test covers uncapped and capped metadata with those endpoints; the omitted 62
middle records repeat that parsing purpose. The separate native portable control
tests all 64 rows and stop-at-cap behavior. The reduced fixture does not claim
stream coverage or native cap/stop verification.

`legacy-schema1-first.rows` is the first profile row from a separate authored
FakeClock precursor. Its helper source SHA-256 is
`9aa692c89157cea0944e63a5eba89c419d6bcec42ee07d117a9efd08bfd52958` and its header
SHA-256 is `559efb2240c93ec7e46267cd3bcc4293aef87a45ebce929aa00a09d8a5dd487a`.
It has an older field set and is used only to reject that field set even after a
test changes its version to 3. It is not claimed to match the revision above.

`tools/test_godot_draw_rows.py` derives synthetic schema 3 rows from these schema 2
arithmetic controls. It adds authored costs `(1, 2, 1, 2, 1) * n` and ten clock
reads per submitted list for the five new SceneBegin scopes. Those transformations
test strict reader accounting, negative controls, and phase membership. They are
not emitted schema 3 ABI evidence or measured runtime costs.
