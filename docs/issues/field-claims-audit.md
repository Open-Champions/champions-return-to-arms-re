# Audit of structure-field and flag-bit claims after the `fieldxref` / `flagxref` rewrite

Status: **in progress** — sections are filled in as the work goes; anything not yet
written says so.

Scope: every statement in `FINDINGS.md`, `docs/*.md`, `docs/issues/*.md` and
`docs/spec/*.md` whose truth depends on a list of the readers or writers of a structure
field, or of the tests of a flag bit, being complete. `docs/issues/claims-audit.md` did
this for globals after `tools/gxref.py` was corrected; its section 6 showed that the two
sibling tools had comparable gaps and that the claims resting on them had not been
re-checked. This document fixes the tools, measures the change and re-checks the claims.

Everything here was read from the executable (SLUS_209.73, v2.00), its disassembly and its
decompile; **nothing was run on a console or emulator.** Statements are **Observed** unless
marked otherwise. `FINDINGS.md`, the other documents, `names.tsv` and `patches/` were not
edited; corrections are listed for whoever applies them. No patch is proposed.

## 1. Result in short

*(written last)*

## 2. The two tools after the rewrite

Both tools now share one analysis (`tools/fieldxref.py`; `tools/flagxref.py` imports it):
a forward data-flow pass over every function, with Ghidra's function bodies
(`ghidra_funcs.tsv`) as boundaries and the function's real control flow (branches, delay
slots, likely-branches, joins) instead of a look-back window or the listing order. The
result for the whole executable is cached next to the disassembly
(`disasm/text.fx.pickle`, about 6 s to build, ignored by git like the other caches), so a
query takes a fraction of a second. The old command lines still work.

*(details, numbers and limits: sections 2.1–2.4, being written)*

## 3. Old output against new

*(being measured)*

## 4. The claims

*(being audited)*

## 5. New desync candidates

*(being collected)*

## 6. What the tools still cannot see

*(being written)*

## 7. Not done

*(being written)*
