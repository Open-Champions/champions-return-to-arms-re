# Online quality: what ends a session, and what a player feels

Working notes, kept current so the work can be resumed. Champions: Return to Arms,
SLUS-20973 v2.00. Everything marked **Ran** was run on the two-machine rig
(`tools/rig/`, `docs/issues/live-rig.md`): copies of one Play! build, **not a PlayStation 2
and not PCSX2**, so timing statements are in frames and calls of the game, not in a
console's milliseconds. **Observed** = read in the executable at the address given.
**Inferred** = follows from those. **Unknown** = not established.

Local wrappers, scripts and logs are under `local/rig-out/oq/` (not in the repository).
The runner used here is a private build (`local/rig-build-oq/`, section 0); the ledger and
the patch file were not edited — proposed rows are in the last section.

Status (updated as the work goes): section 1 in progress.

## 0. Rig additions used here

Made in a private copy of the runner (`local/rig-build-oq/rig.cpp`, built from the
runner source as it stood before the `--arith` work that is going on in `tools/rig/rig.cpp`
at the same time; `local/rig-build-oq/apply.py` holds the edits as exact text replacements
so they can be merged). Not yet in `tools/rig/`.

| Addition | What it does |
|---|---|
| script command `freeze N` (use as `A: freeze N`) | this machine stands still for N frames of the others: nothing of it runs, the link stays in step, and what the others send waits in its socket queue — a stopped emulator, or a host that hung. The other machines see `wait N` |
| `--link` repeatable, `--machine A…D`, tags `C:` `D:` | three and four runners in one game, each pair joined by its own socket; all advance frame by frame together |
| `--link-keep-going` | a runner that ends is forgotten by the others instead of ending them |
| `--bus …,burstevery=F,burst=N` | nothing crosses for N frames out of every F (same phase on every machine: both directions fail together) |

## 1. The "pause-menu kick"

(being written)
