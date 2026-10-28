# Arrival research round 4: state-sensitive prefixes and composed queue execution

2026-10-27; extends audited tip `2550d3473dafc3609bbecbed2ec365bf7a658c60`.
**STATUS: PARTIAL.** The normal-route deferred queue and native census are still
**Unknown**. The additional execution below proves bounded prefix behavior and
queue composition; it does not constitute a successful arrival. Equipment work
is described separately in [round-4 equipment research](starting-equipment-r4.md).

## Initial entries: original execution with controlled state

**Executed:** `tools/difftest_loading_arrival_r4.py` reads one script from each of
three private destination archives, in route order. The ordered archive manifest
remains under ignored `local/`. Archive and entry bounds are checked. Private
names, scripts and native arguments are never written to tracked output.
The executable's existing digest pin is checked before any experiment.

The original loader `0x13e8f8`, registration `0x141310` against table `0x403370`,
entry wrapper `0x1ed694`, interpreter `0x13ecf8`, dispatcher `0x141050`, and the
permitted handlers and their callees execute in `tools/ee_emu.py`. The harness
removes all convenience hooks supplied by the prior VM test class, follows all
callees, patches no instructions, and asserts no calls were auto-stubbed.
Observation hooks record native entry; an unresolved handler raises an explicit
boundary **before its first instruction**. No native return is fabricated.

**Executed, differential controls:** the independent existing `ref_amx.Machine`
runs the same private image with an authored model of five native effects.
Native address/argument order, complete script state/data/heap/stack, the entire
four-record byte region, and save-inhibit state agree at every boundary. The
native effects being compared are:

- `0x1473b4`: save-inhibit word `0x50605c` receives the argument.
- `0x1420d0` / `0x1bf6d0`: availability bit in the requested mission byte changes
  in the first `word[0x4d8ae0]` records; other bits and records are preserved.
- `0x1420a4` / `0x1bf770`: completion bit is set in all four records, including
  inactive records.
- `0x142084` / `0x1bf730`: reads completion bit from record zero.
- `0x142044` / `0x1bf8d8`: returns record-zero choice byte `+0x4c1a` masked by
  `1 << word[0x4f719c]`, rather than normalizing every nonzero value to one.

These roles and addresses were already observed in `docs/spec/script-builtins.md`;
this round composes their original execution with actual destination entry prefixes.
Records start with explicit nonzero sentinel bytes, selected mission bits and
choice flags. These values are **test controls**, not reconstructed campaign state.
The matrix uses player counts 1/2/4, difficulty indices 0/1/4, mission low bits
0/1/2/3, and both choice-bit states: **72 controls per destination, 216 total**.

**Executed prefix order**, excluding the last, unexecuted boundary from native
execution counts:

| Route ordinal / control | Initial entry identifier address | Executed native addresses, in order | Boundary before native body |
|---|---|---|---|
| 0, all 72 controls | `0x53f000` missing; then `0x53f020` | `0x1473b4`, `0x1420d0`, `0x1420a4` | `0x142320` |
| 1, all 72 controls | `0x53f000` | none | `0x14222c` |
| 2, completion bit clear, 36 controls | `0x53f000` missing; then `0x53f020` | `0x142084`, `0x142044` | `0x1433c8` |
| 2, completion bit set, 36 controls | `0x53f000` missing; then `0x53f020` | `0x142084`, `0x1420d0` | `0x143540` |

The matrix executes **360 permitted native calls**, with 216 intentional boundary
encounters across four native addresses. Missing initial entries return minus one.
Both queue counts remain zero **only through these bounded prefixes**. Those
counts do not describe the end of initial-entry execution or the loading pass.

**Observed boundary roles:** `0x142320` searches named objects through
`0x14bf58` and may call virtual slot 18; `0x14222c` calls blocking resource loader
`0x173558`; `0x1433c8` modifies quest lists; `0x143540` sets a quest variable.
The latter two are intentionally outside this probe's five-handler model, not
claims that these functions are wholly unreconstructed. Later object/media/state
services remain necessary. No initial-entry success or complete prefix is claimed.

**Inferred:** the route-ordinal-2 split demonstrates why a default-zero state is
not adequate evidence of normal arrival. Both branches are original-executed under
explicit controls, but this experiment does not select which branch the player's
actual campaign takes. It also does not perform the object loading that normally
occurs between the two initial entry calls.

## Original enqueue and returned-pass composition

**Executed:** four full original reset `0x1e6f58` controls use player counts 1/2
and difficulty indices 1/4, poisoned queue counts/parity/save inhibit/post action,
and distinct nonzero mission bytes in all four records. Reset returns with no
hooks, patches or stubs. Counts, parity, save inhibit and the post-action first
byte clear; player count, difficulty and all 65 mission bytes for difficulties
1..5 per record remain unchanged. Reset therefore supplies queue initialization,
but it does not create a fresh character or reconstruct campaign progression.
The character initializer and its mission tail are separate dependencies.

**Observed:** teardown calls clear `0x1eda08` at `0x1e50c0`; clear stores zero to
front count `0x86da78`, back count `0x86da7c`, and parity `0x4f8690` at
`0x1eda14–0x1eda20`. Enqueue `0x1ed52c` writes into the opposite parity half,
with stride `0x50`, and increments only the back count (`0x1ed540–0x1ed590`).
A back count of 64 rejects the next insertion before copying.

**Executed:** three authored-script controls start with stale nonzero counts and
parities 0/1/7, execute the original clear, enqueue two authored entries through
`0x1ed52c`, and run wrapper `0x1eda24` three times. The actual handlers
`0x1473b4` and `0x144160`, enqueue, strings, wrapper and VM execute without stubs:

1. First pass dispatches zero entries and zero natives; counts become front 2,
   back 0, parity 1.
2. Second pass dispatches the two entries in insertion order. Native order is
   `0x1473b4`, `0x144160`, `0x1473b4`. The middle native really enqueues another
   authored entry. The last setter wins. Counts become front 1, back 0, parity 2.
3. Third pass dispatches that new entry and runs `0x1473b4` once. Counts become
   front 0, back 0, parity 3.

**Executed:** three capacity controls use parities 0/1/7, enqueue 64 distinct
authored identifiers through the original function, then attempt a 65th. Counts,
all retained entries, the full two-buffer byte range and untouched opposite half
match the expected model. No private script identifiers appear in these fixtures.

**Inferred, conditional only:** if the actual loader clears queues and reaches its
first deferred pass without any intervening queue promotion/front-count writer,
that first pass promotes back work and executes none. This round does **not**
establish the premise across the normal object/load/post-action/task path. It must
not be exported as a zero-command normal-route census or permission to discard
pending work. Prior round error-continuation and refusal boundaries still apply.

## Original loader bootstrap diagnostic

**Executed, diagnostic only:** separate untouched fresh-ELF instances call
`0x1e55c0` with each private destination base identifier. All three stop with the
emulator's unsupported syscall at `0x352e14`, selector register value 124. No
instruction patches, hooks, native stubs or automatic callee stubs are installed.
No call to `0x217978`, `0x1ed694` or `0x1eda24` occurs before the stop.

A fresh ELF is not a normal caller/state fixture. This is an observed bootstrap
boundary of this experiment, not a crash observed in the running game and not
proof that supplying a single syscall return would establish arrival. The EE
function tool lacks the surrounding console runtime and does not obtain mission,
player, world or resource state merely because disc files are available.

## Remaining evidence and validation

**Unknown:** the exact normal-route queued entries, ordered native calls and counts
through returned pass `0x1eda24` at caller `0x322e6c`; established player/mission,
quest, object and media state through all three destinations; and playable arrival.
Obtain a faithful loader/state fixture or an original runtime capture, execute the
complete loader/object/initial-entry/player/post-action path, and observe enqueue
`0x1ed52c`, dispatch `0x1ed694`, and native dispatcher `0x141050`. Preserve both
front/back counts and parity before and after the returned pass. Export only
ordinals, addresses, counts and authored roles. Never substitute permissive native
results or an empty queue for this evidence.

Commands (all input paths are private/ignored):

- `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loading_arrival_r4.py local/SLUS_209.73 local/arrival-route-r4.json`
  — 4 full reset controls, 3 composed queue cases, 3 capacity cases, 216 differential initial-prefix
  cases, and 3 fresh-ELF boundary controls. Log: `local/arrival-r4.log`.
- Round-3 transformations/publication: 45 + 2 cases and 2,624 + 1,958 private
  resource-entry comparisons PASS; `local/resource-r4-regression.log`.
- Round-2 probes: 81 PASS. Round-1 readiness: 47 PASS. Existing loading probes:
  seeds 20973/7 PASS. Analysis suite: 652 PASS, `local/unit-tests-r4.log`.

Existing reference APIs, vectors, original emulator and digest pins are unchanged.
No client changes, visual/gameplay evidence, device-transfer claim or public-server
contact. The actual deferred census remains unresolved; retain the client refusal.
