# tools/arith: does a browser machine compute what a desktop machine computes?

Tools behind `docs/issues/mixed-arithmetic.md`. The game is lockstep: every machine of a
game has to compute the same bits. The desktop application (Play!, ARM64 code) rounds
floating-point results toward zero as the console does; the browser build (the same
emulator translated to WebAssembly) can only round to nearest. The application's core has
a switch, "browser arithmetic" (`FpUtils::SetArithmetic`), that makes the native machine
compute as the WebAssembly one. These tools check that it does. Nothing of the game is in
this directory: addresses come from files you give.

| File | What it is |
|---|---|
| `jitdiff.cpp`, `build.sh` | Play!'s two code generators against each other. The program translates every floating-point operation of Play!'s intermediate language (alone and in the combinations the front ends emit for the console's FPU and vector units) with the code generator of the platform it was compiled for, runs each over a few million operand sets and prints one checksum per operation. `build.sh` builds it natively and, with Emscripten, for node, linking the code generator libraries of an existing rig or application build and of an existing browser build. Equal lists = equal result bits. |
| `session.py` | One scripted session for two machines. `make` turns a controller stream recorded by the rig (`rta_rig --record-input`) into what the browser build's test page takes, plus the rig's watch file and a rig script for the memory writes; `compare` compares the rig's per-frame log with what the browser reported, frame by frame and place by place. |
| `web/arith.html`, `web/arith.js` | The browser build's side: a page that gives the machine the whole session before it starts (one step per vertical blank from the first one on, so every press lands in the same vertical blank as on the rig) and POSTs what the game's memory held at every vertical blank to the local test server. |
| `browser-run.py` | One run of that page in a Google Chrome of its own (own profile directory, no window unless `--window`), ended when the trace is in. |
| `web-hooks.patch` | Three test entry points for the browser front end (see below). |

## The comparison, step by step

```
# 1. the two code generators (no game needed)
tools/arith/build.sh local/rig-build-mixed local/play-web-build local/play-playable local/mixed/jit
local/mixed/jit/jitdiff --mode browser --count 2000000 > native.txt
node local/mixed/jit/jitdiff-wasm.js --count 2000000 > wasm.txt
diff <(tail -n +2 native.txt) <(tail -n +2 wasm.txt)      # only "unused.cmp.gt" may differ

# 2. a session, recorded on the rig in browser arithmetic (any rig script; here from power-on)
python3 -I -B tools/rig/rig.py --data OUT/data --arith browser --script SESSION.rig \
    --record-input OUT/input.txt --log OUT/frames.tsv --watch-file OUT/session.watch
python3 -I -B tools/arith/session.py make OUT/input.txt FRAMES WATCHES.txt OUT/session \
    [--poke FRAME:ADDRESS:TEXT ...]          # writes OUT/session.json .watch .rig

# 3. the same session in the browser build
tools/play-web/serve.py --port 8992 --site SITE --disc IMAGE.iso --report WEBOUT/report.jsonl &
#    SITE holds Play.js, Play.wasm (a build with web-hooks.patch), arith.html, arith.js, session.json
python3 -I -B tools/arith/browser-run.py --out WEBOUT --name s1 --session session.json --port 8992

# 4. compare; --other is a rig run of the same input in the other arithmetic
python3 -I -B tools/arith/session.py compare OUT/frames.tsv WEBOUT/s1.hex WATCHES.txt \
    --other OUT-native/frames.tsv
```

The rig replays a recorded stream with `--replay-input OUT/input.txt --script
OUT/session.rig --frames FRAMES` (the script holds only the memory writes). The watch
list is a text file, one place per line: `name pointer offset size` in hexadecimal;
pointer 0 means the bytes at `offset`, otherwise the bytes at `offset` past the pointer
stored at `pointer`.

Why from power-on, and by vertical blank: a browser build cannot load the rig's saved
states, and both machines are deterministic by vertical blank from power-on when they get
the same presses in the same vertical blanks (checked: the cosmetic seed, which the game
seeds from the processor's cycle counter at start-up, is the same on both in every frame).
A page that presses buttons from JavaScript timers is not frame-exact; one that queues
everything before the machine's first frame is.

## web-hooks.patch: for the browser front end's owner

`arith.js` works with any browser build in its old form (`?steps=…&trace=…`: steps that
hold either buttons or the left stick, one place of at most 64 bytes, through the existing
`rtaTap`, `rtaStick`, `rtaTrace`; `session.py make` writes such a steps file,
`OUT.steps.json`, whenever the stream allows it, and `browser-run.py --steps FILE --trace
POINTER,OFFSET,SIZE` runs it). For a session with a memory write, several places per
frame, or buttons and a stick together (what the rig's `fuzz` command produces), the
front end needs three more test entry points. `web-hooks.patch` adds them to
`tools/play-web/src/RtaWeb.cpp` (made against the file as it stood on 2026-10-12, 138
added lines, nothing changed in what exists):

- `rtaStep(buttons, lx, ly, rx, ry, frames)`: one scripted step with buttons and both
  sticks.
- `rtaPokeAt(frame, address, size, value)`: 1, 2 or 4 bytes written to the game's memory
  in vertical blank number `frame`, on the machine's thread, before that blank's presses
  are given and before the traces read (the rig's `at FRAME` / `poke`). Data only.
- `rtaWatchAdd(pointer, offset, size)`, `rtaWatchStart(frames)`, `rtaWatchRead()`: several
  places read together at every vertical blank, up to 4096 bytes a frame.

They are test aids like `rtaTrace`: nothing calls them unless a page does. The comparison
in `docs/issues/mixed-arithmetic.md` was run with a private build of the front end with
this patch, linked against copies of the browser build's own libraries.
