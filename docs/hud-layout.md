# Original UI frame and base HUD contracts

SLUS-20973 v2.00, researched 2026-10-17 on `t3/research-ui` from `a2b145b`.
Companions: [reference](../tools/ref_ui_layout.py),
[synthetic tests](../tools/test_ref_ui_layout.py),
[font contract](formats/ui-fonts.md), [inventory pixels](formats/inventory-icons.md).

**Status:** menu frame resource rectangles and assembly are documented;
the base player HUD's resource rectangles, positions, clipping, fills and local
slot arrangement are documented. Full HUD behavior is **partial**: dynamic
notifications, potion indicators, spell ring, compass and minimap composition
are not fully modeled here. Static observations and function-level execution do
not establish visual parity in a native game. No running game was launched.

O = observed, I = inferred, U = unknown. Confidence accompanies each evidence
group. Addresses are EE virtual addresses unless a lump-relative byte offset
is explicitly identified.

## Coordinate and draw contract

**O / high**, `0x17b590`, `0x17b8b0`, `0x17ab50`:
the ordinary interface is 640 x 448 logical pixels. In the normal interlaced
path, GS X = `2*x + 1408`, Y = `y + 1824`, expressed in 1/16-pixel registers.
The display composition is 4:3; square-pixel export is 640 x 480, not 640 x 448
with equal-axis scaling. Source rectangles below use logical progressive texels.
Stored interface rows are two fields; weave before using these rectangles.

`0x17b590(texture,x,y,layer,tint)` adds **one to y** (`0x17b6f8`).
`0x17b8b0(texture,x,y,layer,tint,left,top,right,bottom,flipX,flipY)` does not.
`0x17fb88` is a forwarding wrapper for the latter. The source is always
`(0,0,width,height)` from the texture header (`0x17b79c–0x17b7c4`,
`0x17bb84–0x17bbf0`), with flips exchanging source endpoints.
Clipping cuts the draw in destination space; it does not stretch a texture.

**O / high**, `0x17baac–0x17bb7c`: scissor inputs clamp left/top to at least
zero, right to at most 640, bottom to at most 447. In the interlaced branch,
horizontal inclusive GS scissor endpoints are `2*left` and `2*right-1`.
The bottom endpoint depends on field parity; in both-fields mode it is
`2*((bottom//2)+(bottom&1))-1`. Preserve the API scissor values below if
implementing exact GS field rendering. A progressive half-open clip is a useful
native approximation, but odd bottom boundaries must be compared with the
original field path before claiming raster parity. Normal HUD scissors extend
well beyond the short bars vertically.

**O / high**, `gfx_addSortedPacket` `0x16b7f0`, sprite enqueue `0x17b888`:
2D uses queue flag 1, which prepends. References return **submission order**.
For a painter renderer, reverse those 2D submissions within each layer; layers
are emitted 0 through 7. In particular, a center submitted last draws first,
and the HUD frame submitted after its bars draws behind them. See
[render-pipeline.md, section 8](spec/render-pipeline.md). Do not equate call
order with final painter order.

**I / high:** original widescreen anchoring is not established. The cluster and
edge rules in [native-graphics.md](issues/native-graphics.md) describe the
recompiled host's extension. They are not original PS2 layout constants.

## Menu frame resource manifest

**O / high:** `ui frame builder` `0x17c118` selects `interfac.lmp`
(`0x17c194–0x17c19c`, name at `0x534090`) and prefix `tile` for style 2,
`btile` for style 1, otherwise `ctile` (`0x17c1a0–0x17c1d8`; strings at
`0x5340a0`, `0x5340a8`, `0x5340b0`). It constructs nine separate names
(`0x17c1dc–0x17c2ac`), not nine rectangles inside one original atlas.

Each table cell below is the texture header's **byte offset inside the private
INTERFAC.LMP**, not an atlas coordinate. The resource is prefix + part + `.tex`.
Dimensions come from u16 +0/+2 of that header. All non-center pieces have full
source rectangle `(0,0,n,n)`, where n=32 for tile/btile, n=16 for ctile.

| Part | tile | btile | ctile |
|---|---|---|---|
| bot | 0x08f00 | 0x00380 | 0x04980 |
| botleft | 0x09580 | 0x00a00 | 0x05000 |
| botright | 0x09c00 | 0x01080 | 0x05680 |
| center | 0x0a280 | 0x01700 | 0x05d00 |
| left | 0x13000 | 0x02080 | 0x06e80 |
| right | 0x13680 | 0x02700 | 0x07500 |
| top | 0x13d00 | 0x02d80 | 0x07b80 |
| topleft | 0x14380 | 0x03400 | 0x08200 |
| topright | 0x14a00 | 0x03a80 | 0x08880 |

Center source rectangles: tile `(0,0,320,224)`, btile `(0,0,64,64)`, ctile
`(0,0,128,64)`. Border thickness n is an **assembly metric**, not a claim that
every pixel inside a border tile is opaque. Whole resource rectangles are
established by calls to `0x17b590` / `0x17b8b0`; no guessed transparent crop
or source-atlas packing is needed. A native atlas may pack these resources with
its own gutters while preserving these logical source rectangles.

## Exact frame assembly

**O / high**, `0x17c118–0x17c700`; **Executed**, 160 constructed-state call
sequences matched the Python reference. Parameters are
`(x,y,width,height,layer,tint,style,no_center,no_border)`; the ninth argument
is passed on the caller's stack. `n` comes from the selected border texture's
width at `0x17c2bc–0x17c2c4`; center step sizes come from its own width/height
at `0x17c548–0x17c558`. Reference constants specialize those reads to this
revision's observed resources.

Let R=x+width, B=y+height. All rows below describe **submission** order.

| Phase | Calls / origin | Clip (L,T,R,B) |
|---|---|---|
| corners | botleft `(x,B-n-1)`, botright `(R-n,B-n-1)`, topleft `(x,y-1)`, topright `(R-n,y-1)` | ordinary sprite; +1 y inside callee |
| horizontal edges | for d=0,n,... strictly below width-2n: top `(x+n+d,y)`, then bot `(x+n+d,B-n)` | top `(x,y,R-n,B-n)`; bot `(x,y,R-n,B)` |
| vertical edges | for d=0,n,... strictly below height-2n: left `(x,y+n+d)`, then right `(R-n,y+n+d)` | `(x,y,R,B-n)` |
| ordinary center | rows stepped by center H, columns by center W, both strictly below inner dimensions | origin `(x+n+dx,y+n+dy)`, clip `(x,y,R-n,B-n)` |

**O / high**, style 2 exceptions (`0x17c414` region and
`0x17c574–0x17c648`): bottom edge right clip is **R-n+4**.
Center origin is `(x+n-25+dx,y+n-26+dy)` and clip
`(x,y,R-n+26,B-n+26)`. Columns satisfy `dx < width-2n+52`; rows satisfy
`dy <= height-2n+50`, an inclusive outer boundary. Steps are 320 and 224.
This overlap is why a generic nine-slice with a 32-pixel inset is not equivalent.

`no_border` skips corners and edges; `no_center` skips center. The game does
not clamp small width/height to 2n: corners can overlap, and loops with
nonpositive bounds disappear. The reference intentionally retains this.
Wrapper `0x17fbb8` changes x to x-1, y to y-4, width to width+2, height to
height+8 and forces style 2 (`0x17fbbc–0x17fbdc`); callers of this wrapper
must not apply its padding twice.

## Base HUD resource and rectangle contract

**O / high:** `hud_drawPlayerStatus` `0x1d9cd4`, HUD.LMP headers below,
lookups at `0x1d9f0c`, `0x1da210`, `0x1da2f0`, `0x1da5c4–0x1da6a0`.
These resources are whole textures, not subrectangles of an atlas. A bar
animation has eleven entries 00 through 10. All source origins are `(0,0)`.

| Resource in HUD.LMP | Used W x H | First header byte offset | Further offsets |
|---|---|---|---|
| bar_blue00..10.tex | 100 x 8 | 0x00600 | +0x680 per frame |
| bar_green00..10.tex | 100 x 6 | 0x04d80 | +0x680 per frame |
| bar_red00..10.tex | 100 x 8 | 0x09500 | +0x680 per frame |
| hud_multi.tex | 158 x 46 | 0x12980 | — |
| hud_statusbar00.tex | 160 x 46 | 0x13a00 | — |
| hud_statusbar00glow.tex | 160 x 46 | 0x15d80 | — |

**O / high**, `0x53c408` read at `0x1d9dbc–0x1d9e60`:
slot x origins are **[12,478,167,323]**. At `0x1d9e68`, an intermediate is
X+7; do not confuse it with X. In a network game, each local nonzero slot gets
the original slot-0 x. If slot 0 is not local, its x becomes the last promoted
slot's old x (`0x1d9df4–0x1d9e4c`). Multiple local slots are not arbitrarily
redistributed; `hud_origins` models the actual loop. Offline every slot is local.

| Element | Destination origin | Full size | Clip / behavior | Addresses |
|---|---|---|---|---|
| health | `(X+15,46)` | 100 x 8 | `(X+15,24,fill_right,124)` | `0x1d9eac–0x1d9f8c` |
| experience, local with acknowledged level >0 | `(X+15,56)` | 100 x 6 | same clip shape | `0x1da1e0–0x1da2bc` |
| mana, local | `(X+15,63)` | 100 x 8 | same clip shape | `0x1da2c4–0x1da384` |
| local status frame | `(X-4,36)` | 160 x 46 | `(0,0,1000,1000)` passed to clip callee | `0x1da7c0–0x1da7f8` |
| remote status frame | `(X-4,36)` | 158 x 46 | same broad clip; hud_multi.tex | `0x1da804–0x1da838` |
| name text origin, centered wrapper | `(X+73,17)` | from small font | state-dependent content/tint | `0x1da3b0`, `0x1da5a0–0x1da5b0` |
| level text origin, centered wrapper | `(X+134,44)` | from small font | decimal signed-byte level at player +0x59 | `0x1da3dc`, `0x1da654–0x1da674` |

All listed sprite submissions use layer 6; no pivot offsets beyond the explicit
origins above. Example slot 0: health at (27,46), experience at (27,56), mana
at (27,63), local frame at (8,36). These are clipped sprites, so **no +1 y**.

**O / high**, `0x1d9f24–0x1d9f84`, `0x1da244–0x1da2b4`,
`0x1da318–0x1da37c`: fill is left-to-right. With S=X+15,
`fill_right = trunc(float(S) + (value/maximum)*99.0)`.
Order is divide, multiply, add, conversion to integer; do not use rounded
percentages or scale the bar image. Full fill is 99 logical pixels of a
100-wide resource. There is no explicit clamp in these sequences.
Health reads floats +0xac/+0xb0; mana +0xc0/+0xc4 of player record
`0x4d8af0 + slot*0x4c30`. Experience uses integer player +0x5c minus
table `0x41b554[level_acknowledged]`, divided by the difference to
`0x41b558[level_acknowledged]`; acknowledged level is signed byte +0x58.

The reference uses `ee_emu`'s PS2 arithmetic model; that module explicitly
documents limitations near hardware rounding boundaries. The instruction order
is observed; console-exact FPU behavior is not independently verified here.
The reference refuses negative/current or nonpositive maximum inputs outside
its stated domain; these checks are native-reader policy, not game branches.

**O / high:** animation frame is `(sim_tick >> 2) % 11` for nonnegative ticks,
where sim_tick is `0x44fdcc` (`0x1d9ef4–0x1d9f10`). Default health and XP tint
is 0x80808080. Health flash consumes bit 0 of `0x41b930[slot]` and changes
RGB to 255 with alpha 128 (`0x1d9eb8–0x1d9ee8`). Mana tint is 0x80acacac;
if signed short player-object +0x4ae >0, alpha becomes 42 (0x2aacacac),
`0x1da2f8–0x1da358`. Keep GS tint semantics when matching original blending.

**O / high:** `hud_base_layers` preserves only the base sprite subsequence,
not every call in `0x1d9cd4`. Local life/XP/mana/frame and remote life/frame
are distinguished. All callers must apply visibility gates first: nonzero
`0x41b4f8`, `0x4f66a8`, `0x41b50c`, camera object's +0x34 !=1, failed
`0x13dd40`, missing player object, or nonzero object +0x540 suppress status
(`0x1d9cdc–0x1d9e74`). The remaining packet-space gate requires at least
3,000 free units (`0x1d9e78–0x1d9ea4`); it is an original resource-limit
behavior, not a native UI sizing constraint.

## Known partial contracts and how to finish them

Round 2: draw order, notices, glow, message, boss meter, gold, selector, bust and
compass composition are in [hud-dynamic.md](hud-dynamic.md).

**O / high:** pending potion overlays are untextured rectangles, not extra
bar atlases (`0x1d9fb8–0x1da1d8`). Health Y=47..51, tint 0x80000060;
mana Y=66..70, tint 0x805a4632. They require local ownership, the object's
dead bit 0x8 clear, and positive pending recovery (+0xb4 health / +0xc8 mana).
For S=X+15, C=current and M=maximum, the addressed arithmetic is:
`a=trunc((C/M)*99)`, `t=trunc(C+pending)`; if `float(t)>M`, set `t=trunc(M)`;
then `b=trunc((float(t)/M)*99)`. The rectangle is submitted to `0x17bd30`
with left `S+a`, right `min(S+b,cap[slot])`, layer 6 and the above Y/tint.
The caps are **[180,605,333,447]**, selected by the original player slot,
not the promoted network position (`0x1da050–0x1da0ac`,
`0x1da164–0x1da1c0`). Do not move the integer conversion after the ratio,
nor reuse the bar's add-before-truncate formula. These submissions are
excluded from the deliberately narrow `hud_base_layers` reference and were
not function-executed in this pass.

**O / medium:** level-up glow is `hud_statusbar00glow.tex` at `(X-4,36)`;
its alpha at `0x86aa50[slot]` increments by 4 up to 128 when alive with a
pending level (`0x1da6b0–0x1da7b8`). Dynamic colour also depends on sine.
Full fade/reset lifetime and interaction with the separate level-up icon remain
**U** in this contract.

**U:** complete potion-count/button rows, save/network notices, boss meter
fills, spell selector, minimap and compass source/destination composition,
all screen-specific frame callsites, and frame-art opaque contours. Entry
points include `0x1d93b0` (boss/message), `0x1dc708` (gold), `0x1dd270`
(selector), `0x1df720` (compass), `0x1e42e0` (minimap), and the remainder
`0x1da840–0x1dacc0` for status adjuncts. Their resource names alone are not
layout evidence. They require further addressed tracing and visual comparison.

## Round 4: catalogue page versus the drawn crop (2026-10-20)

The original-art set is 34 textures in `HUD.LMP` and `INTERFAC.LMP`:
`bar_red00.tex`–`bar_red10.tex`, `bar_blue00.tex`–`bar_blue10.tex` (22),
`hud_statusbar00.tex`, `hud_statusbar00glow.tex`, `button.tex`, the eight
32×32 frame tiles (`tilebot`, `tilebotleft`, `tilebotright`, `tileleft`,
`tileright`, `tiletop`, `tiletopleft`, `tiletopright`) and `tilecenter.tex`.
Comparing the TEX used size to the catalogue `page` matched 9 (the nine
frame pieces) and missed 25.

**Executed.** `difftest_ui_r4` runs `tex_relocate` `0x179e10`,
`ui_drawSpriteImpl` `0x17b590` and the clipped drawer `0x17b8b0` on the five
distinct sizes below. A private pass ran the same three functions on all 34
real headers. Relocation leaves +0 and +2 unchanged (34/34). Both drawers
pass source origin `(0, 0)` and the header width and height to
`ui_emitSpriteQuad` `0x17ab50` (34/34). The plain drawer adds 1 to
destination y; the clipped drawer does not. A tighter destination clip does
not change the source span. A horizontal flip exchanges the U endpoints and
keeps the span. The difftest sets field byte `0x44fdd4` to 0, which selects
the arm that does not adjust destination y; the source load is after the two
arms join (`0x17bb84`).

The source crop is therefore the used rectangle. It is not the GIF image
rectangle, and it is not the health/mana fill clip in the table above.

| Group | n | Used size and source crop | GIF image rectangle | Field rows |
|---|---|---|---|---|
| red and blue bars, frames 00–10 | 22 | 100×8, `(0,0,100,8)` | 104×8, direct 4-bit | 4 |
| status frame and its glow | 2 | 160×46, `(0,0,160,46)` | 80×24 PSMCT32 (8-bit page, buffer width 2) | 23 |
| button | 1 | 83×38, `(0,0,83,38)` | 88×40, direct 4-bit | 19 |
| frame borders | 8 | 32×32, `(0,0,32,32)` | 32×32 | 16 |
| frame center | 1 | 320×224, `(0,0,320,224)` | 320×224 | 112 |

**Observed** in every file of the group (34/34 upload rectangles). The 4-bit
uploads are wider or taller than the used size; those extra texels are
outside the rectangle the drawers sample. The status upload is the swizzled
8-bit page, and that 80×24 rectangle covers the 160×46 used texels. The old
catalogue `page` was the 4-bit upload for the bars and the button, and
160×48 for the status frames. Field rows were already half the used height.
The bar and status used sizes in the table above already matched these
headers. `bar_green` is not one of the 34 and was not remeasured.

The marked block in `tools/godot/project/gameart/catalogue.gd` sets `page`
and `rect` to the used crop for `bar_blue`, `bar_red`, `button`, `statusbar`
and `statusbar_glow`. `name` and `pack` still name the older art-pack files
and were not regenerated. Frames 00–09 are the same sizes as frame 10; this
catalogue names frame 10.

## Validation

**Executed:** `local/trace_frames.py` executes `0x17c118` in `tools/ee_emu.py`,
stubbing lump/name lookup and draw sinks with synthetic metadata. Private
`local/verify_contracts.py` compared **160** call sequences across styles
0/1/2/3, border/center suppression, partial tiles, small frames, and center-loop
boundaries. This validates call geometry and order, not GS rasterization.

**Executed:** `local/trace_hud_base.py` ran `0x1d9cd4` on four synthetic
player slots with partial health/mana/XP and an active cooldown. All four base
sprite subsequences matched `hud_base_layers` in resource, position, clip,
tint and sort layer. Ancillary calls were stubbed; this is not a complete
HUD behavior test.

**Executed:** the complete required suite passed **668 tests**, including 16
new synthetic tests across the two new test modules. Evidence:
`local/unittest-research-ui.log`, `local/contract-verification.log`.
No symbol edits, game process, original UI screenshot, native/Godot UI build,
or in-game visual comparison in this pass. Private inputs and traces remain
under `local/`; there are no game bytes or raw code exports in these documents.

**Executed (2026-10-20):** `difftest_ui_r4` matched `tex_relocate`, the
font-page DBP stores and both sprite drawers. A private pass decoded all 8
embedded font pages (0 uncovered texels) and drew all 34 HUD headers
(34/34 source rectangles equal to the used size). Counts only; no image
was written.
