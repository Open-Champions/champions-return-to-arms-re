# MacBook and Windows setup

The Python analysis tools and the native archive inspector run without a PS2 emulator.
They do not play the game. A native game client still needs an authored engine; see
[NATIVE_PORT.md](NATIVE_PORT.md). The lobby server is a separate program and cannot
replace the game client.

## Python tools

Use a native Python installation for your processor. CI checks Python 3.13 on macOS
Apple Silicon and Intel, Windows x64 and ARM64, and Linux x64. A Linux Python 3.14 job
also checks newer interpreter behavior. The workflow records the actual interpreter
architecture; a passing job proves the tested tool operations, not gameplay or every
optional reverse-engineering dependency. [Latest checks](https://github.com/Open-Champions/champions-return-to-arms-re/actions/workflows/tools.yml).

From the repository directory on macOS:

```sh
python3 tools/doctor.py
python3 -m unittest discover -s tools -p 'test_*.py'
python3 tools/symtab.py check
```

In Windows PowerShell:

```powershell
py -3 tools/doctor.py
py -3 -m unittest discover -s tools -p 'test_*.py'
py -3 tools/symtab.py check
```

These commands do not require the disc, BIOS, emulator, LLVM or Ghidra. `doctor` may
report optional dependencies as warnings while the basic check passes. It probes
versions and selected configuration; it does not install anything or launch the game.
`--json` provides machine-readable results. An explicitly supplied wrong game hash
fails even in basic mode.

## Analyze your own executable

Copy `SLUS_209.73` from your US v2.00 disc into the repository root. It stays ignored.
Use these commands on macOS (replace `python3` with `py -3` on Windows):

```sh
python3 tools/doctor.py --game SLUS_209.73
python3 tools/gen_disasm.py SLUS_209.73
python3 tools/dis.py SLUS_209.73 0x139e88
```

The generator needs an LLVM build listing MIPS targets. It checks PATH and usual
Homebrew/LLVM installation locations. Apple's bundled LLVM lacks the required target
in our test. You can choose the executable explicitly, including a path with spaces:

```powershell
py -3 tools/gen_disasm.py SLUS_209.73 --objdump "C:\Program Files\LLVM\bin\llvm-objdump.exe"
```

Use `--output PATH` to keep a separate listing. The generator retains delay-slot no-ops,
writes bytes directly, and replaces an existing listing only after successful generation.
Avoid generating it through PowerShell text redirection, which can change its encoding.
Readers accept UTF-8 and BOM-marked UTF-16; malformed input is rejected.

## Optional Ghidra setup on Windows

Install/configure Ghidra and its Emotion Engine extension using their official
instructions. Set `GHIDRA_HOME` to your extracted distribution and `JAVA_HOME` to
its supported JDK; do not assume a Java launcher on PATH is a usable JDK. The preflight
reads the selected Ghidra distribution's Java requirements.

```powershell
py -3 tools/doctor.py --strict-re --game SLUS_209.73 --ee-extension "C:\path\to\ghidra-emotionengine-reloaded"
$repo = (Get-Location).Path
New-Item -ItemType Directory -Force build, ghidra/proj | Out-Null
py -3 tools/symtab.py merge build/all_names.tsv
& "$env:GHIDRA_HOME\support\analyzeHeadless.bat" ghidra/proj crta -import SLUS_209.73 -processor r5900:LE:32:default
& "$env:GHIDRA_HOME\support\analyzeHeadless.bat" ghidra/proj crta -process SLUS_209.73 -noanalysis -scriptPath ghidra/scripts -postScript ApplyNames.java "$repo\build\all_names.tsv" -postScript DecompAll.java "$repo\decomp\all" "$repo\ghidra\scripts\extra_entries.txt" -postScript ListFuncs.java "$repo\ghidra_funcs.tsv"
```

The explicit extension path is a placeholder for your installed extension directory.
These are setup instructions, not proof a full Ghidra analysis has passed on Windows.
The current function at `001a3580` has a separately tracked decompiler limitation.

## Native archive inspector and Godot client

The C++ archive inspector has moved to
[open-champions-godot/native](https://github.com/Open-Champions/open-champions-godot/tree/main/native).
Build commands, native platform checks and downloadable inspector packages now belong
there. Run that repository's commands from its checkout; this research repository
only runs Python analysis checks.

The inspector lists metadata from private Return to Arms GOB/LMP archives. It is not
a playable game. The shared client targets both games, while Norrath's asset and
behavior compatibility still require independent verification. See the
[native roadmap](https://github.com/Open-Champions/open-champions-godot/blob/main/docs/ROADMAP.md).

Keep private archives and generated analysis in ignored locations. Headless checks
do not establish visual quality, controller behavior or native gameplay.
