# A live rig: the game running headless on Play!'s core

Status of this document: **in progress** (phase 1). It is written as the work goes, so an
interruption loses nothing; sections marked *pending* have not been done yet.

Every earlier statement in this project came from reading the executable or from running
single functions in `tools/ee_emu.py`. This document is the first that reports what the
**running game** does. Statements here are marked

- **Ran** — seen in a log written by the rig, with the address and value quoted;
- **Observed** — read in the executable or in Play!'s source at the place given;
- **Inferred**, **Unknown** — as in the rest of the project.

"Ran" means: ran in the Play! emulator at the commit below, with its high-level BIOS, on
this one disc image. It is not a PlayStation 2 and it is not PCSX2; where the emulator's
accuracy matters to a conclusion, that is said.

## 1. What the rig is

| | |
|---|---|
| Emulator | Play! (github.com/jpd002/Play-, BSD 2-clause), core only: no Qt, no video, no sound |
| Commit built | `83700b2c31e593bc94e845b4b31b797be84dda59` (2026-09-03), submodules as pinned by it |
| Why this emulator | it has a built-in high-level BIOS, so no PS2 BIOS file is needed; none exists on the test machine and none may be downloaded |
| Host | Apple silicon (arm64) macOS; Apple clang 21; CMake 4.4.4 and Ninja 1.13.2 from Homebrew (the only things installed) |
| Disc | the user's own image of SLUS-20973 v2.00, opened read-only |
| Rig source | `tools/rig/` (C++ runner, CMake file, Python wrapper, README) |
| Where things go | Play! checkout and build: `local/play`, `local/rig-build`; logs, dumps and save states: `local/rig-out/` — all ignored by the repository |

*(sections 2 onward are filled in as each step is done)*

## 2. Building it — *pending*

## 3. What the runner can do — *pending*

## 4. Results

### 4a. Boot — *pending*
### 4b. The symbol map against the running game — *pending*
### 4c. Offline play from scripted input — *pending*
### 4d. The network question and the plan for phase 2 — *pending*

## 5. Where the running game contradicted the documents — *pending*

## 6. What blocked, what is not done — *pending*
