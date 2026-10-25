# Native blocker research handoff — 2026-10-17

Branch `t3/research-anim`, research base `a2b145b`. The three Python drafts
left by the interrupted attempt were preserved, reviewed, completed and
tested. All research changes are local to this worktree. No push, PR, native
port, live-game run or public-server contact was performed. The owning live
main workspace was only read through private `local/` links.

| Target | Delivery and remaining boundary |
|---|---|
| A: last Skills-A constructor | **Fully documented in the admitted domain.** [Constructor contract](gameobject-constructor.md), `tools/ref_gameobject_ctor.py`, `tools/test_ref_gameobject_ctor.py`, `tools/difftest_gameobject_ctor.py`. Ordered prefix, hidden-grid move, stale/incoming properties, names, quotes, tombstones and shared RNG. No change to pinned `ref_skills_a.py`; native count remains its owner's responsibility. |
| B: rendered creature animation | **Partial overall.** [Animation handoff](rendered-creature-animation.md), `tools/ref_creature_animation.py`, `tools/test_ref_creature_animation.py`, `tools/difftest_creature_animation.py`. Index pairing, hierarchy, transform layout, blending, skinning, root-motion handoff, shared events and complete existing SmallSpider dispatch route are documented. Reuses `ref_anim`/`ref_core`/`ref_monsters_1`; no claim that every other creature/player dispatch is now executable or Godot rendering verified. |
| C: water | **Fully documented services in the admitted domain.** [Water contract](water-services.md), `tools/ref_water_services.py`, `tools/test_ref_water_services.py`, `tools/difftest_water_services.py`. Includes original spatial query, order, capacities, duplicates, raw32 grid mapping and ordered ripple writes. Grid lifecycle/simulation/rendering remain outside this service contract. |
| B (round 3): creature and player dispatch | **Documented for clip selection, events and consumers; partial for conditions.** [Dispatch contract](creature-animation-dispatch.md), [every class](creature-animation-dispatch-classes.md), [player](player-animation-dispatch.md); `tools/scan_anim_dispatch.py`, `tools/ref_creature_dispatch.py` + `_data.py`, `tools/test_ref_creature_dispatch.py`, `tools/difftest_creature_dispatch.py`. 73 classes in five groups; unchanged round-2 APIs. See the round-3 section below. |
| C: model 0x46 | **Unknown original row producer.** [Evidence boundary](model-46-row-boundary.md). The level setup is documented, but the exceptional model's reachable STROW producer is not established. Preserve the native refusal. |

## Reproduce checks

Run from this worktree, with the user's own executable available only under
`local/`. The optional differential scripts check its US v2.00 hash and fail
on missing/wrong inputs; their fixtures are synthetic, not extracted assets.

```sh
python3 -m unittest discover -s tools -p 'test_*.py'
python3 tools/difftest_gameobject_ctor.py local/SLUS_209.73
python3 tools/difftest_creature_animation.py local/SLUS_209.73
python3 tools/difftest_water_services.py local/SLUS_209.73
git diff --check
```

- Full unittest discovery: **684 tests pass**, 42.388 seconds in this run.
  The 32 tests in the three supplement suites require no private input.
- Constructor: **64** original/reference calls; final bytes and ordered
  stores. Resource/allocation stubs and normalized copy widths are stated
  in its report and contract.
- Animation supplement: **25** original/reference checks (16 raw32 draw
  prefixes, eight role resolutions with callback ordering, one event writer).
  It stops before rendering; role services are stubbed.
- Water: **576** original/reference calls across four FPU adder modes;
  query/test/disturb run without service stubs. Exact return values where
  specified and all ordered non-stack writes are compared. No live hardware
  floating-point parity is inferred from interpreter agreement.
- No symbols changed, so `symtab.py check` is not a required changed-symbol
  gate. No build was attempted; the doctor/build prerequisite is inapplicable.

Aggregate logs are private local evidence: `local/research-tests-final.log`,
`local/constructor-differential.log`, `local/animation-differential.log`,
`local/water-differential.log`. No pictures were produced: this is addressed
research and function-level validation, not a rendered acceptance run.

The native owner should pin the local research commit before porting these
supplements, preserve existing corpus baselines, and generate new native
synthetic traces. A passing research function test is not a completed native
port or an original-asset visual check.

## Round 3 — 2026-10-17: exhaustive dispatch

Branch `t3/research-anim` on `2502e2b`. Research only; no native port, push, PR, live game,
recompiled-build run or server contact. Model 0x46 was left to `t3/research-textures`.

- `tools/scan_anim_dispatch.py local/SLUS_209.73` executes every catalogue class's
  setState (requests 0…0x2f; rand residues; one-word probes), constructors (event tables,
  initial clips, class definition) and, with `--runs`, run functions (one event mask at a
  time). Its JSON stays in `local/`; `--emit` writes the committed numeric table.
- Result: 47 classes on the root-motion base, 10 on the steered base, 10 own state
  machines, 6 without setState dispatch (section 5 of the contract); 55 classes with
  event consumers; one consumer with no installer (SpiderQueen camera shake on 0x8).
- Cross-checks: the table agrees with the independently written class bodies of
  `ref_monsters_1` (SmallSpider, Gnaw, Mosquito, Scorpion, Badger) and
  `ref_arena_monsters` (Horsemen, Skelight, Zek) on every recorded state and residue
  (synthetic test, no ELF); `difftest_creature_dispatch.py` re-executes 1,404 original
  setState calls against the table (log `local/dispatch-differential.log`).
- Player: by reading (sub-agent draft reviewed, two claims re-checked at 0x1a2380 and
  0x1b34b0); player-tick §0 track-field names corrected.
- Native owner: keep round-2 vectors; add `ref_creature_dispatch.select/apply_ops/
  install_events` traces. Conditions beyond one-word probes stay with each class body.
