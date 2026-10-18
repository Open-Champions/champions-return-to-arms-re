# Rendered creature animation: native implementation handoff

2026-10-17; SLUS-20973 US v2.00. Research base `a2b145b`.
**Observed** means instruction/static-data evidence at the addresses below.
**Inferred** marks a consequence or host integration choice. **Unknown** is a
remaining proof obligation. Existing **Executed** results belong to the
function-level tests cited in [animation](animation.md), not a new live run.
No console, rendered Godot creature or live game was validated by this handoff.

The authoritative raw32 arithmetic, decoder, blend, hierarchy, root motion and
cache model is `tools/ref_anim.py` plus `tools/ref_core.py`. Do not substitute
host floats for its simulation arithmetic. The new
`tools/ref_creature_animation.py` connects resource selection, object draw
transform, shared event writes and the geometric skinning contract. Its
Fraction-based skinning is an exact mathematical reference, **not** a claim of
bit-for-bit VU1 arithmetic or rasterization. Its synthetic tests exercise the
boundaries between these components.

## 1. Model, texture, clip and bone identity

**Observed:** `GameObject_ctor` `0x14cbc4–0x14cc20` resolves the object's
class definition through `res_find` `0x17365c`. Object `+24` points to:

| Definition offset | Meaning |
|---|---|
| +00 / +04 | lump-name pointer / resolution generation |
| +08 / +0c | model entry name / resolved `.vif` |
| +10 / +14 | texture entry name / resolved `.tex` |
| +18 / +1c onward, stride 8 | class-specific resource name / resolved pointer |

The getter at `0x3c2738–0x3c2740` returns `*(obj.classDef+0xc)`.
`SmallSpider_draw` `0x2ab5a8–0x2ab5bc` explicitly supplies model `+c` and
texture `+14` to `Creature_draw(0x10b048)`. Other classes can override the
model/texture getters or supply different resources; do not equate “resource
index 3” with one universal animation role. Index i resolves at `def+8*i+4`.
Player equipment/part draws have additional attachment transforms.

**Observed:** there is no runtime bone-name matching. Mesh weights hold
**joint index times four**, a VU matrix address. Divide that byte by four
before using a native joint index. Model attach records instead store an
integer joint index (`model_getAttachPoint` `0x1754a0`). The model has no
skeletal hierarchy; it contains geometry in rest-pose **model space**, weights
and attachments. Each `.anm` supplies its own skeleton at header `+0xc`
(8-byte signed16 bind records, xyz/64) and `+0x10` (one depth byte per joint).
`anim_emitPose` `0x16f880` uploads its matrices unchanged; `model_draw`
`0x1779b0` and VU1 entries `0x3a,0x0c,0x42,0x44` use those indices directly.

**Inferred host admission rule:** verify every used joint is below the
selected base clip's count and every participating clip has the intended
ordered depth/bind skeleton. Class resource provenance is the evidence of
pairing; joint count alone is not. The original does not reject incompatible
clips. A lump can contain both a creature and props with different skeletons.
Do not invent automatic retargeting. There are 64 slots; the older
anim-audio note questioning joint 63 is superseded by
[model-texture](../formats/model-texture.md), “Weights and joints”, and
[render-pipeline](render-pipeline.md) 4.7. Without animation, VU1 entry
`0x1e` fills only slots 0–62 and leaves slot 63 stale.

## 2. Original clip selection and dispatch

**Observed, `obj_findRoleAnim` `0x160928–0x160a84`:** NPC ancestry selects
the embedded lump-name string at `obj+0x3c8` (`0x16096c–0x160990`), not a
pointer loaded from that address. Other objects use `*(obj.classDef)`.
For supplied role R:

1. Query property `R + "name"`. If present (an empty value is present), query
   it again, append `.anm`, resolve and **return even if lookup is null**
   (`0x160994–0x1609ec`). No fallback after an explicit override.
2. Otherwise query `name`; if present query it again, resolve
   `name + "_" + R + ".anm"`; return if non-null (`0x1609f4–0x160a44`).
3. Resolve `R + ".anm"` (`0x160a4c–0x160a68`).

The two formatting buffers are 0xa0 bytes. The supplement admits ASCII strings
whose formatted results fit; bounds refusals are host policy. Preserve repeat
property calls. This role helper is used by scripted roles; it is **not** the
universal AI state-to-clip dispatcher.

**Observed:** creature vtable pointer is `obj+0x48`; entry stride 8, signed16
this adjustment at entry+0, function pointer at entry+4. See the indirect
state-change call `0x2a9368–0x2a937c`. Slot 4 runs AI, slot 5 draws,
slot 27 changes state. Slot 27 overrides call `Creature_filterState`
`0x10a9c0` before their switch; the filter can refuse or rewrite the requested
state. It clears root/cooldown/stun timers for death, prioritizes the root,
stun and attack-cooldown branches, and unlinks the target on resulting state
zero (`0x10aa34–0x10aaf8`). Exact filter body already lives in
`ref_creature.Model.filter_state` and [creature-tick](creature-tick.md); use it, not an
unconditional state assignment.

**Observed complete example: SmallSpider.** The independently authored
`ref_monsters_1.Model.smallspider_ctor/run/set_state/on_touch` and
[monsters-1](monsters-1.md) section 3 already specify the full class, including
all RNG and non-animation side effects. Re-read evidence for draw pairing is
`0x2ab590–0x2ab5d4`. State contract is `0x2ab704–0x2ab8dc`:

| Filtered state | Clip selection / calls before state publication |
|---|---|
| 0 | own RNG draw d; timer `+f4 = clock+120+d%300`; `anim_start(raw 0x3e999999, state+114, *(def+3c), flags 3)` |
| 1 | clear path, choose wander destination; same start with `*(def+4c)`, flags 3 |
| 5, 0x10, 0x12, 0x13 | preserve old state; no clip start |
| 0x14 | object flags OR 9; two own draws for decal; third draw d selects `*(def+1c+8*(d&3))`; start with blend `0x3e999999`, flags 6; hidden flag 2 jumps top to end; slot 28 death callback |
| other | no clip start; store the state |

The state is finally stored as u16 at `obj+232`. Constructor `0x2ab450`
pushes the `def+3c` idle clip with flag 1 and randomizes phase with the
**cosmetic** seed, then joins the 60-frame run list; that phase draw is not
the object's RNG. `SmallSpider_run` `0x2ab5d8` calls damage processing,
Creature_run, updateActive, then (only when active) stepAnim at raw ONE,
knockback and its state logic. Touch by a player requests death. Thus a host
preview looping one chosen clip does not reproduce original dispatch.

**Coverage boundary:** exact executable class bodies exist for SmallSpider,
Gnaw, Mosquito, Scorpion, Badger (`ref_monsters_1`) and the arena set
(`ref_arena_monsters`). `docs/monsters.md`, `monsters-2.md` and
`symbols/monsters*.tsv` address the remaining classes, but do not constitute
a complete executable dispatch oracle for every creature/player/equipment
variant. This delivery establishes pairing/dispatch mechanisms and the
SmallSpider route, **not all 73 class state machines**. Unsupported classes
must remain explicit until their own class body is contracted.

**Round 3 (2026-10-17):** the setState clip dispatch, constructor event tables and run-side
event consumers of all 73 catalogue classes are now Executed and tabulated in
[creature-animation-dispatch](creature-animation-dispatch.md) (data
`tools/ref_creature_dispatch_data.py`, contract `tools/ref_creature_dispatch.py`), and the
player's in [player-animation-dispatch](player-animation-dispatch.md). That is the clip
*selection* contract; the full per-class AI (targeting, timers, every draw) still needs each
class body, as before.

### Mutable event tables are part of the class contract

**Observed, `creature_setDefEntryParams` `0x118378–0x1183cc`:** for each of
four events, re-read obj+24 and resolved entry, write the mask byte at
clip+`0x18+8*i`, then raw32 seconds at clip+`0x14+8*i`. The clip identity is
shared; do not clone it per instance. The native decoder's immutable-file
view alone does not supply constructor-installed hit/cast event times.
The supplement exposes these ordered stores as `set_class_events`.

## 3. Decoder and local transform conventions

**Observed, `animtrack_decode` `0x16e468`:** initial file quaternions are
**w,x,y,z** signed integers /4096; the decoder's records are **x,y,z,w**.
Initial local translation is /64. Velocity records are per tick, position
/256 and quaternion /131072. At fractional raw32 time t, evaluate
`p+v*(t-positionTick)` and `q+qvel*(t-rotationTick)` in that order. These
are component derivatives, not sampled Euler angles or normalized keys.
Normalize only after blending. Decoder state/rewind and 64-record stale
contents are specified in [animation](animation.md) sections 2–3.

**Observed, pose builder `0x16ed40`, VU0 packet `0x3e5c40`, instruction
payload `0x3e5c50`:** depth is stack level, not parent index. Entry 2 resets
only stack level 0 to identity. Each joint reads level d, constructs local
L from its normalized quaternion and translation, computes **W=P*L** for
column vectors, and writes W to level d+1. A sibling reuses the same parent
stack level. Deeper old levels survive across builds; malformed depth lists
can read them. For normal preorder skeletons, the parent is the latest
preceding joint at depth d−1. See `vu0_compose_joint` for the exact operation
order, including negative zero and fixed-point truncation.

Then output matrix is `[W.R | W.R*(bind/64)+W.t]`. The bind correction is
applied to the **output**, not to the matrix saved on the hierarchy stack.
This maps rest-model coordinates straight to posed-model coordinates.
Rotation is multiplied by 4096 and translation by 64, truncated toward zero,
then low 16 bits are retained with signed interpretation. No saturation:
translation 512 wraps to −512. Do not apply inverse bind a second time.

Pose storage is three signed16 rows `(r0,r1,r2,t)` per joint. In contrast,
the CPU mat34 from `anim_getJointMatrix` `0x16f720` is a flat row-vector
matrix: three basis rows then translation, obtained by transposing the
pose's rotation. Keep these representations explicit; their textual
multiplication order differs for the same transform.

## 4. Blending and pose ownership

**Observed, `0x16ed40–0x16f71c`; full contract in animation section 8:**
scan tracks top-down for a base among nonnegative-time tracks with
`min(weight,life)>=1`, ANDing their joint masks until zero. Without such a
base there is no calculated pose. Base joint count controls the blend loop.
Evaluate base locals; then process tracks **above it, bottom-to-top**.
Clamp `min(weight,life)` to [0,1], optionally smoothstep for flag `0x100`,
skip below raw threshold `0x3a83126e`, and skip joints whose mask bit is set.

Choose the incoming quaternion sign by comparing squared sum versus
squared difference (accumulate w,x,y,z), linearly blend components and
translation, then normalize **once after all layers**. This is not SLERP or
independent normalized interpolation per layer. Preserve the original
w-component unwrap for arbitrary synthetic inputs (`ref_anim.anim_build_pose`).
ROOT removes joint-zero XY; YAW strips its heading. **The top track's clip
supplies depth and bind arrays even if its time is negative or its blend is
zero.** The base supplies joint count. Mixing incompatible clips can read
stale slots; the host may refuse this explicitly.

Pose buffers cache quantized final matrices, not decoded joint locals.
`anim_advance` clears the pose pointer; start/stop/clear alone do not.
`anim_getJointMatrix` builds a missing pose for simulation (fallback allowed).
`anim_emitPose` rebuilds a fallback for drawing, stamps the draw frame, or
uses the 64-joint identity default when no drawable buffer/base exists.
Only drawing stamps; see `ref_anim.PosePool`, `anim_build_pose`,
`anim_emit_pose` for exact eviction/ownership. Do not advance the clock again
when drawing or querying an attachment.

## 5. Skinning and object-to-Godot transform

**Observed:** VU1 payload is addressed by instruction i at
`0x3e5ed0 + (i//256)*0x808 + (i%256)*8`. Pose upload entry `0x3a`, matrix
setup `0x0c`, vertex entries `0x42/0x44`, weights at `0x3e7e38`;
[render-pipeline](render-pipeline.md) 4.7 gives the addressed numerical
contract and its historical VU interpreter comparisons.

Decode `(j1,w1,j2,w2)`: `j2==255` means a rigid run of **w2 vertices** on
j1 (ignore w1); otherwise one vertex with weights w1,w2. If their sum is not
255, the next entry supplies a third and optionally fourth influence
(fourth omitted when its joint byte is 255). Divide joint bytes by four.
Weights in the admitted data sum to 255; do not renormalize them or multiply
the rigid run by its unused w1. Positions are signed16 /16. Blend the final
pose matrices linearly by weight/255 and apply to the model-space point.
Normals use the rotational part; the original lighting treatment, shell
normals and two-pass GS materials are in render-pipeline/model-texture.
Exact VU instruction rounding remains separate from the Fraction oracle.

**Observed object transform, `Creature_draw` `0x10b090–0x10b12c`:**
position is `(obj+10,obj+14,obj+3c)`—the last is rendered height, **not +18**.
If raw float `+e0 != 0`, add `(cos16(facing),sin16(facing))*offset` to XY.
Use scale `+dc` and signed16 Z rotation `facing+0x4000`; call
`mat34_setPosRotZScale` `0x163cb8`. Apply skin first, then this object
transform, then view/projection. Model visibility/variant mask `+220` and
special class draw overrides are separate from joint pose computation.

**Inferred Godot adapter choice:** right-handed game Z-up to Godot Y-up can
be `B(x,y,z)=(x,z,-y)` with an explicit world-unit scale. For matrices use
`B*M*B^-1`; translations/root deltas use B, rotations use basis conjugation,
and normals use the same orthonormal basis without translation. The helper
`godot_point` defines this policy; it is not an original function. A native
implementation may CPU-skin with the quantized matrices or feed equivalent
final skin matrices to a shader. If using Skeleton3D, account for its rest
transform convention so it does not apply bind offsets twice. No Godot
default interpolation is an exact substitute for the original pose builder.

## 6. Root motion and tick order

**Observed, `anim_advance` `0x16d748`, `Creature_stepAnim` `0x1162b0`:**
time uses raw `speed*0x3f7fffff`, not exact 1 per nominal tick. ROOT `0x800`
protects decoder slots because their joint-zero XY holds the motion base;
YAW `0x4000` protects the previous signed16 heading. Pose building strips
these components while advance returns deltas. Root extraction is layered
with remaining weight; masked clips do not consume that budget. It uses
the updated weights in a second pass, while loop-end extraction used the
earlier weights. Yaw is accumulated bottom-up without blend weights.
Loop crossing rebases the decoder; reproduce the loops and ordered writes
from `ref_anim.anim_advance`, not `% length` or visual sampling subtraction.

Creature step first applies kind-3/player and Drowsy speed multipliers;
the existing Python entry takes speed **after** these external multipliers.
For slow amount 1..60 it additionally scales animation speed. Active flag
bit 63 of `+a8` gates advance. Afterward it scales deltas by `+dc`, then with
`a=facing−0x4000` computes `dx'=(-dx)*cos(a)+dy*sin(a)` and
`dy'=(-dx)*sin(a)−dy*cos(a)`. Slow scales XY again and multiplies yaw by
the integer part of `(60−slow)/60`, therefore zero. When inactive, the old
stored delta is transformed again. The returned event bits are then consumed
by the class state logic. `Creature_moveBy/To` consume motion through their
collision/root-timer rules; simply adding it in Godot bypasses those rules.
See [movement-camera](movement-camera.md) and `ref_creature`.

`Player_animStep` `0x1b9520` differs: no scale/second slow factor and no
yaw output. Do not route players through the creature wrapper unchanged.
Sound ranges remain recorded callbacks in the animation reference; actual
audio playback is not supplied by this delivery.

## 7. What this unlocks and what remains

**Documented:** model/clip/index pairing; depth hierarchy and transform
layout; blend/pose cache; geometric skinning; object transform; root-motion
handoff; role resolver; class event mutations; original SmallSpider dispatch
using the existing complete class model. Synthetic fixtures cover these
connections, including rotated parent/child/sibling composition and top-track
skeleton selection. A native owner can implement this bounded creature route
without guessing transforms or selecting clips by filename similarity.

**Executed in this pass:** `python3 tools/difftest_creature_animation.py
local/SLUS_209.73` matches 16 original draw-transform prefixes through
`0x10b130` (12 raw32 components each), eight role lookups including repeated
callback order and explicit-override failure, and the shared four-event
writer's ordered stores. Role ancestry/property/resource services are
explicit deterministic stubs; draw is stopped before rendering. The new
synthetic unit suite also connects the existing SmallSpider slot-27 body to
an owned `ref_anim.AnimState` through its actual start callback ABI.

**Partial:** exhaustive original per-creature/player dispatch, equipment and
special draw overrides; exact native VU1 rendering/lighting parity. The
existing native cache Runtime explicitly refuses ROOT/YAW/pose execution;
these are new implementation work, not removed gates just because the
research contract exists. **Unknown here:** full rendered Godot acceptance
on original assets and cross-platform exact arithmetic. Settle with synthetic
native/reference traces first, then a private known model/clip pair and
recorded rendered movement/blend/attachment checks. Do not claim those tests
were performed by this research-only branch.
