<p align="center"><img src="https://raw.githubusercontent.com/Open-Champions/.github/main/profile/assets/champions-return-to-arms-logo.png" alt="Champions: Return to Arms" width="512"></p>

Part of [Open Champions](https://github.com/Open-Champions), an independent community preservation project.

# Champions: Return to Arms — research and the playable rebuild

This repository is where *Champions: Return to Arms* (PS2, US release SLUS-20973, v2.00)
is taken apart and put back together: the research (symbols, file formats, how every
system works, the online bugs), the tools that prove it against the original executable,
and the playable rebuild - the game's own code translated to C++ on each player's machine,
and the same game hosted inside Godot.

**This repository distributes no game binaries, game data or translated game code.** Every
player builds from their own disc. See [What may not be committed](CONTRIBUTING.md#what-may-not-be-committed).

## Direction

- **One portal, two games:** *Classic* (the original game, faithful, plus the sharp art pack
  and a steady 60 fps) and *Remastered* (Godot, 60+ fps, new HUD and lighting, five views,
  aim where you look, Hardcore combat, the Elden Ring look from your own copy). Rooms are one or the other.
- **Online play is exact:** every gameplay change is lockstep-safe, a room option all copies
  agree on, tested in multi-copy rooms; with a mode off the game is byte-identical to the original.
- **Champions of Norrath** joins later as more campaign content; each player brings their own discs.
- **No game data, disc images, BIOS, Elden Ring data or personal information in any repository;**
  everything from a game stays on the player's machine.
- This repository is the **playable line now**; [open-champions-godot](https://github.com/Open-Champions/open-champions-godot)
  is the long-term hand-written line aiming at the same product.

The whole direction: [docs/DIRECTION.md](docs/DIRECTION.md).

## Play

Step-by-step for every kind of computer: **[docs/DOWNLOADS.md](docs/DOWNLOADS.md)**.

- **Native game (Mac, Windows, Linux):** download *Champions Setup*, double-click it; it finds
  your disc image, translates the game on your computer and builds *Champions* and *Champions
  Godot* ([DOWNLOADS.md section 8](docs/DOWNLOADS.md#8-native-version-build-it-from-your-own-disc)).
  You can also make the setups yourself from this repository (same section).
- **Mac application and browser version** (the emulator line): sections 2 and 3 of DOWNLOADS.md.
- **Playing together:** rooms with a code, no account (section 4), or the lobby (section 5).
- You need your own disc image of the US v2.00 release. The download link is private and
  comes from whoever invited you; nothing of the game is behind it.

How complete each part is, updated at every check-in: [docs/PROGRESS.md](docs/PROGRESS.md).

## Test

The same checks as the [CI workflow](.github/workflows/tools.yml); none needs game files:

```sh
python3 -m unittest discover -s tools -p 'test_*.py'   # the Python unit suite
python3 tools/symtab.py check                           # symbol contributions are consistent
python3 tools/coverage.py --write && git diff --exit-code -- docs/STATUS.md   # coverage page is current
python3 tools/doctor.py                                 # read-only setup check
```

The `tools/difftest_*.py` scripts run the original executable's functions in
`tools/ee_emu.py` and compare them with the reference models; they need your own
`SLUS_209.73` (put it at the repository root, or set `CHAMPIONS_ELF`). Online changes are
tested in rooms of several copies: [docs/VALIDATION.md](docs/VALIDATION.md).

## The other repository

[open-champions-godot](https://github.com/Open-Champions/open-champions-godot) is the
hand-written C++/Godot rebuild: portable libraries checked function by function against
this repository's research, aiming at the same Classic/Remastered product, the same 60+ fps
bar and the same lockstep rules. All Open Champions repositories:

| Repository | Responsibility |
|---|---|
| [champions-return-to-arms-re](https://github.com/Open-Champions/champions-return-to-arms-re) (this one) | Research, symbols, formats, analysis tools, online-bug evidence; the translated native game and its Godot host (the playable line) |
| [open-champions-godot](https://github.com/Open-Champions/open-champions-godot) | The hand-written native C++/Godot rebuild for both games (the long-term line) |
| [champions-return-to-arms](https://github.com/Open-Champions/champions-return-to-arms) | Return to Arms PS2 source reconstruction, byte verifier and progress |
| [champions-of-norrath](https://github.com/Open-Champions/champions-of-norrath) | Separate Norrath source target; its baseline is not established yet |

[Repository map](docs/REPOSITORIES.md).

## Where the research stands

- The executable is 3.0 MB of MIPS code in 7,732 functions; naming coverage by area is in
  [docs/STATUS.md](docs/STATUS.md).
- All 403 C++ class names are recovered and 402 are tied to their virtual tables.
- The level-script language is fully decoded: all 120 level scripts decompile to readable
  pseudo-code, and all 191 built-in script commands are located.
- The online model is mapped: deterministic lockstep, the per-frame sync check, the input
  codec and the local-player prediction system. [FINDINGS.md](FINDINGS.md) is the evidence
  ledger for the online bugs; every claim is marked observed, inferred or unknown, with addresses.

## What is here

| Path | What |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | How the game is put together — start here |
| [docs/](docs/) | One document per subsystem, plus file formats and status |
| [FINDINGS.md](FINDINGS.md) | Evidence ledger for the online bugs |
| `names.tsv`, `symbols/*.tsv` | Symbol map: address, name, note |
| `rtti_classes.txt`, `vtables.txt`, `ghidra_funcs.tsv` | Class names, virtual tables, function boundaries |
| `tools/` | Python tools: cross-references, script decompiler, archive unpacker, sync audits |
| `tools/recomp/` | The translator that turns your own executable into C++, and the native game's runtime |
| `tools/godot/` | The Godot host of the translated game: portal, views, HUD, lighting, the Elden Ring layer |
| `tools/install/` | The setups that build the game on a player's machine from their own disc |
| [docs/DIRECTION.md](docs/DIRECTION.md) | Where the game is going and the rules every change follows |
| `ghidra/scripts/` | Ghidra scripts: apply the symbol map, decompile everything |
| `patches/` | PCSX2 patches for testing hypotheses |

## Research setup

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
