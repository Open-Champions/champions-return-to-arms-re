<p align="center"><img src="https://raw.githubusercontent.com/Open-Champions/.github/main/profile/assets/champions-return-to-arms-logo.png" alt="Champions: Return to Arms" width="512"></p>

Part of [Open Champions](https://github.com/Open-Champions), an independent community preservation project.

# Champions: Return to Arms — research

An open effort to understand, document and eventually rebuild the code of *Champions:
Return to Arms* (PS2, US release SLUS-20973, v2.00), the Snowblind-engine action RPG whose
online service was shut down years ago.

One goal is practical: make online play dependable again on community servers such as
[Champions Reborn](https://github.com/HikikoMarmy/Champions-Reborn-Server) by finding and
fixing the bugs that put players "OUT OF SYNC" and make the game lag. The long-term goal is
a readable C++ reconstruction of the original PS2 executable, verified one function
at a time, alongside a native Mac and Windows client built with Godot.

**This repository distributes no original game binaries or assets.** Independently
authored source reconstruction now lives in its dedicated repository. You need your own copy of the
disc to analyze game files; basic tool checks and synthetic tests need no game data. See [What may not be committed](CONTRIBUTING.md#what-may-not-be-committed).

## Where it stands

- **How complete the playable game is, part by part, updated at every check-in:
  [docs/PROGRESS.md](docs/PROGRESS.md).**
- **Which version you can get, for which computer, and how:
  [docs/DOWNLOADS.md](docs/DOWNLOADS.md).**
- The executable is 3.0 MB of MIPS code in 7,732 functions. Naming coverage is tracked separately;
  [docs/STATUS.md](docs/STATUS.md) breaks that down by area.
- The local Ghidra pass produced 7,731 successful decompilations; one function at
  `001a3580` still fails with a normalization error. Indexed does not mean fully understood.
- All 403 C++ class names are recovered and 402 are tied to their virtual tables.
- The level-script language is fully decoded: all 120 level scripts decompile to readable
  pseudo-code, and all 191 built-in script commands are located.
- The online model is mapped: deterministic lockstep, the per-frame sync check, the input
  codec and the local-player prediction system.
- Several real sources of desync have been found by reading the code. **None has been
  confirmed on a running game yet** — that needs two emulators side by side, and it is the
  most useful thing a new contributor could do. [FINDINGS.md](FINDINGS.md) is the evidence
  ledger; every claim there is marked observed, inferred or unknown, with addresses.
  Use the [two-client test procedure](docs/VALIDATION.md) to record reproducible results.

## Open Champions repositories

| Repository | Active responsibility |
|---|---|
| [champions-return-to-arms-re](https://github.com/Open-Champions/champions-return-to-arms-re) (this repository) | Research, symbols, formats, Python analysis tools and online-bug evidence |
| [champions-return-to-arms](https://github.com/Open-Champions/champions-return-to-arms) | Return to Arms PS2 source reconstruction, byte verifier and progress |
| [champions-of-norrath](https://github.com/Open-Champions/champions-of-norrath) | Separate Norrath source target; its baseline is not established yet |
| [open-champions-godot](https://github.com/Open-Champions/open-champions-godot) | Shared native C++/Godot client work for both games |

The source reconstruction and native inspector have moved to their active homes.
Their history remains here; new changes belong in the corresponding repository.
[Repository map](docs/REPOSITORIES.md).

## What is here

| Path | What |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | How the game is put together — start here |
| [docs/](docs/) | One document per subsystem, plus file formats and status |
| [FINDINGS.md](FINDINGS.md) | Evidence ledger for the online bugs |
| `names.tsv`, `symbols/*.tsv` | Symbol map: address, name, note |
| `rtti_classes.txt`, `vtables.txt`, `ghidra_funcs.tsv` | Class names, virtual tables, function boundaries |
| `tools/` | Python tools: cross-references, script decompiler, archive unpacker, sync audits |
| `ghidra/scripts/` | Ghidra scripts: apply the symbol map, decompile everything |
| `patches/` | PCSX2 patches for testing hypotheses |

## MacBook and Windows support

The research tools run natively in Python; they do not need a PS2 emulator. A
playable native game client does not exist yet. See the [platform setup guide](docs/COMPATIBILITY.md)
and [native client roadmap](docs/NATIVE_PORT.md) for the distinction and next milestones.
The recommended game-client direction is Godot 4 with a portable C++ core; the
archive reader is implemented in the [Godot repository](https://github.com/Open-Champions/open-champions-godot), while Godot asset display and gameplay are still ahead.

Run `python3 tools/doctor.py` on macOS or `py -3 tools/doctor.py` in Windows PowerShell
for a read-only setup check. Basic checks work without any game files. The optional
`--game SLUS_209.73` checks your executable's identity; `--strict-re` additionally
requires the configured reverse-engineering dependencies.

## Getting started

You need Python 3, an `llvm-objdump` build with MIPS target support, and [Ghidra](https://ghidra-sre.org/) with the
[ghidra-emotionengine-reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded)
extension. On macOS, the Apple Command Line Tools build tested here cannot disassemble
this MIPS executable; the Homebrew `llvm@20` build can. Put its `bin` directory on your
`PATH` or pass `--objdump` to the generator; common Homebrew locations are also detected.
The following Ghidra commands use macOS/Linux shell syntax.

```bash
# 1. Copy SLUS_209.73 from your own disc into the repository root. It is git-ignored.
python3 tools/doctor.py --game SLUS_209.73
# expect 292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675

# 2. Disassembly used by the Python tools
python3 tools/gen_disasm.py SLUS_209.73

# 3. Ghidra project with the symbol map applied, and one decompiled file per function
mkdir -p build ghidra/proj
python3 tools/symtab.py merge build/all_names.tsv
analyzeHeadless ghidra/proj crta -import SLUS_209.73 -processor r5900:LE:32:default
analyzeHeadless ghidra/proj crta -process SLUS_209.73 -noanalysis -scriptPath ghidra/scripts \
    -postScript ApplyNames.java "$PWD/build/all_names.tsv" \
    -postScript DecompAll.java "$PWD/decomp/all" "$PWD/ghidra/scripts/extra_entries.txt" \
    -postScript ListFuncs.java "$PWD/ghidra_funcs.tsv"
```

The Python generator selects a MIPS-capable LLVM installation, preserves zero-valued
instructions, and writes output without shell encoding conversion. The equivalent
Windows commands and Ghidra setup are in [COMPATIBILITY.md](docs/COMPATIBILITY.md).

Then, for example:

```bash
python3 tools/dis.py SLUS_209.73 0x139e88          # annotated disassembly of a function
python3 tools/vtab.py SLUS_209.73 show Player      # a class's virtual functions
python3 tools/gxref.py SLUS_209.73 404464          # who reads and writes a global
python3 tools/fieldxref.py SLUS_209.73 2fc         # who uses a struct offset
python3 tools/ghostreach.py 1a5030                 # what the prediction copy can write
python3 tools/gob.py extract DRUNARE.GOB out/      # unpack a level from your disc
python3 tools/scr.py dis out/drunare.lmp/script.scr  # decompile its script
```

## How to help

Read [CONTRIBUTING.md](CONTRIBUTING.md). The short version: pick an area from
[docs/STATUS.md](docs/STATUS.md), say so in an issue, name what you can prove, and write
down how you know. Testing on a running game, tool improvements and file-format work are
just as welcome as naming functions.

## Thanks

- [Champions Reborn Server](https://github.com/HikikoMarmy/Champions-Reborn-Server) for
  bringing the lobby back.
- [ghidra-emotionengine-reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded)
  for making Ghidra read PS2 code properly.
- [rea](https://github.com/morluto/rea) and [Open-BFME](https://github.com/Open-BFME) for
  the working method: an evidence ledger, honest names, one measured change at a time.

## Legal

*Champions: Return to Arms* belongs to its rights holders. This project is not affiliated
with them. It documents the behaviour of software its contributors own copies of, for
interoperability and preservation, and distributes none of it. The tools and notes here are
under the [MIT license](LICENSE). The displayed game wordmark is excluded from that
license; see [artwork credits](https://github.com/Open-Champions/.github/blob/main/ARTWORK.md).
