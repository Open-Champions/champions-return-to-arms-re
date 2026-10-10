# Working on Champions research

Read CONTRIBUTING.md, docs/REPOSITORIES.md and the area document relevant to your task.
This repository owns Return to Arms research, symbols, file-format evidence, Python
analysis tools and proposed patch validation. Its private game files stay local.

## Repository ownership

- Return to Arms source reconstruction and exact-byte verification:
  https://github.com/Open-Champions/champions-return-to-arms
- Champions of Norrath baseline intake and eventual source reconstruction:
  https://github.com/Open-Champions/champions-of-norrath
- Shared native C++/Godot client for both games:
  https://github.com/Open-Champions/open-champions-godot

Do not recreate native/ or reconstruction tools here. Their old commits remain in
history; current changes belong in their new repositories. Research findings stay
here and can be cited by those projects. Export function-index changes as reviewed,
pinned snapshots; do not silently mutate a source project's verification baseline.

## Coordination and evidence

- Inspect status, recent commits and active agent ownership before editing. Claude's
  ongoing research is not an unassigned backlog. Give parallel agents separate files.
- Preserve all unrelated work. Stage only your reviewed files; never reset, clean,
  stash or revert another contributor's changes to make checks pass.
- Keep findings observed, inferred or unknown with addressed evidence. Names and
  decompilation counts do not measure reconstructed or playable game progress.
- Keep original executables, disc/BIOS files, extracted assets, proprietary toolchains,
  raw disassembly and raw decompiler output out of published history.
- Run `python3 -m unittest discover -s tools -p 'test_*.py'` for analysis-tool changes.
  For symbol changes run `python3 tools/symtab.py check` and update docs/STATUS.md
  using `python3 tools/coverage.py --write`.
- Runtime fixes need recorded execution and controls from docs/VALIDATION.md. Reading
  code alone does not prove a desync fix or native gameplay.
