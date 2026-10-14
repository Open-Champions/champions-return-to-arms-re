# The workspace moved (2026-10-13)

Kept current while the work goes on. Every statement says whether it was **Ran** (with
what was seen) or only **Read**.

## STATE (rewritten at every step; read this first after a stop)

**19:10.** Done and verified so far (details in "What was rebuilt"): the game's
executable out of the disc image; both translations and the native programs
(`bin/rta_app_next`, `bin/rta_app_orig_next`; the standing checks pass); the emulator
application cloned and built anew in `local/play-playable-rehome` / `-build` (not yet run);
the lobby rebuilt from a fresh clone in `server/upstream-fresh` and running from there
(pid 26138; the old one, pid 75327, was stopped). Next: the emulator title test, the
stable tree, Godot, the inventory text, `tools/doctor_home.py`.

## What happened

- The checkout lived at `~/Desktop/champions-re`, inside a Desktop that iCloud Drive
  synchronises with "Optimize Mac Storage" on. When the disk filled on the afternoon of
  2026-10-13, macOS **evicted** tens of thousands of its files: such a file is still
  listed with its size, but its data is not on this disk ("dataless"), and a read of it
  blocks until iCloud has brought it back - possibly for ever.
- 18:38: the project was moved. **The real home is `~/champions-re`** (not synchronised):
  a fresh `git clone` of the repository plus an APFS clone of every file that was on the
  disk at that moment. `~/Desktop/champions-re` is now a **symbolic link** to it, so old
  paths in scripts, in built programs and in notes still work.
- The old folder is kept as `~/Desktop/champions-re-icloud-old`. It still holds the
  evicted files as placeholders. What was evicted and therefore not brought across:
  **78,547 files and 112 directories** (the list: `local/rehome/` in the new home holds
  the latest run's `.missing` file; lines `FILE<TAB>path` / `DIR<TAB>path`).
- Everything tracked by git is complete in the new home (it came from GitHub). What is
  missing is in untracked places: `local/`, `decomp/`, `extracted/`, `disc/`,
  `scripts/*.txt`, `scripts_raw/`, `server/upstream`, `work/`, and the game's executable
  `SLUS_209.73` at the top.

## The rules

1. **Never read inside `~/Desktop/champions-re-icloud-old`**: no `cat`, `cp`, `ls -lO`,
   `du`, `grep`, `git status`, no build. A read of an evicted file can hang the shell for
   good. The same for any path of the missing list.
2. To learn whether a file is evicted, ask only for its flags (this reads no data):
   `stat -f "%Sf" FILE` (the word `dataless`), or `find DIR -type f -flags +dataless`.
3. To bring across what iCloud has given back since, use the tool that never opens an
   evicted file: `python3 rehome.py ~/Desktop/champions-re-icloud-old ~/champions-re LOG`
   (it clones what is on the disk, lists the rest in `LOG.missing` and prints how many
   are still missing). Run it now and then; do not wait on it.
4. Do not delete or rename the old folder or anything in it; change no system or iCloud
   setting; no `brctl`, `tmutil`, `killall` on system services.
5. New working directories go under `~/champions-re/local/`, never under `~/Desktop` or
   `~/Documents` (both are synchronised).
6. Before a build or a test: `python3 tools/doctor_home.py` (below).

## How to check

`python3 tools/doctor_home.py` - see "The check script" below.

## Inventory of what was not brought across

(being written)

## What was rebuilt

(being written)

## What is still missing

(being written)
