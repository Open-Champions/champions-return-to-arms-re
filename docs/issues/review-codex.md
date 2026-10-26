STATUS: FINDINGS

Reviewed the last 25 commits ending at `849074465baefad0e5f6fc33f620a89ae7aa6bd9`, against exclusive base `93e3790d7f635b4727adb8ed60c950a47ed0fd73`. Focus: lockstep gameplay, guest-memory layout, and the online fallback. Findings below are introduced or newly exposed by this range. P1 means high priority; P2 means medium priority.

Validation used public source and repository documentation, in-memory Python probes, and a small temporary C++ harness containing the actual cutscene wrapper and WebSocket implementation with synthetic dependencies. No game build, game execution, private assets, live network tests, commits, or pushes. Only this report is retained.

1. **[P1 / High] Cutscene hold state advances during machine-dependent loading passes.**

   Location: `tools/recomp/app/cinematic.cpp:89` (also lines 80–102).

   Failure scenario: all players hold START while a level with an opening cutscene loads. `run_frame` also wraps the warm-up call `cut_runFrame(1)`, but does not exclude it from gameplay bookkeeping. The load path resets the simulation frame to zero; the `H_FRAME == 0` exception then counts every warm-up invocation. Those invocations depend on terrain/equipment loading and displayed frames, not the shared input tick. Consequently two machines enter simulation with different hold counters; a scene exempt from the online minimum skip age can receive its injected skip on different ticks. Crossing the hold threshold during loading also consumes the hold even though the original returns without skipping. The call path and variable warm-up count are documented in `docs/mainloop.md:375` and `docs/mainloop.md:419`.

   Evidence: the actual wrapper, with identical held input and synthetic warm-up/original functions, produced hold values **11 and 21 at simulation tick 1** after 10 versus 20 warm-up calls.

   Suggested fix: delegate warm-up calls without touching hold state or pad edges; advance online hold state only from synchronized simulation calls. Use explicit initialization/scene-epoch state so frame zero can be counted exactly once, and reset scene state through a deterministic lifecycle event.

2. **[P1 / High] WebSocket pongs bypass the service's output and request limits.**

   Location: `tools/rendezvous/rendezvous.py:805` (lines 805–807; compare `send` at line 621).

   Failure scenario: a client sends masked ping frames while ceasing to read responses. The ping branch appends pongs directly to `conn.outbuf`; it never applies `LIMITS['output_bytes']` or an incoming control-frame rate limit. A blocked `flush` retains the bytes. A registered client can keep the connection alive with occasional `dg` input while growing the pong queue indefinitely, exhausting service memory. The path is also available before login, subject to the login timeout.

   Evidence: invoking the actual `ws_read`/frame functions with a blocked writer and 3,000 valid 125-byte pings queued **381,000 bytes**, exceeding the **262,144-byte** configured limit, without dropping the connection.

   Suggested fix: route every outgoing WebSocket frame, including control frames, through one bounded enqueue operation. Apply a control-frame rate limit and close a connection that exceeds its output budget.

3. **[P2 / Medium] A refused early cutscene skip consumes the hold permanently until release.**

   Location: `tools/recomp/app/cinematic.cpp:118` (lines 118–121).

   Failure scenario: in an ordinary online cutscene, players begin holding START near its start. At 60 ticks the wrapper injects START, but the original refuses skips before scene frame 301. The wrapper nevertheless writes `-1` to every hold counter. Continuing to hold never produces another attempt after skipping becomes legal, despite the documented hold-to-skip behavior. Loading and other temporary skip restrictions have the same problem.

   Evidence: the actual wrapper with a synthetic original enforcing the documented minimum age made **one attempt, zero skips**, and retained **hold = -1 through tick 330**.

   Suggested fix: latch the release requirement only when the original actually accepts the skip or ends the scene. Keep a completed hold ready and retry on subsequent eligible simulation ticks while preserving the original skip restrictions.

4. **[P2 / Medium] Spell damage is classified by the caster's current animation instead of the damaging spell.**

   Location: `tools/recomp/app/soulscombat.cpp:1335` (also lines 981–994 and 1314–1338).

   Failure scenario: a player casts a projectile, then starts a melee swing before it hits. At impact, `state == 1` makes `spell_hit` false, so the projectile uses weapon scaling and can also receive the swing's heavy/critical modifiers. A delayed spell impact after `spell_hit_ticks` similarly becomes weapon damage. This is reachable with independent projectiles: `docs/spec/player-spell-pipeline.md:45` describes a projectile with a 300-tick lifetime, longer than the default 240-tick classification window. Identical spell casts therefore have damage determined by unrelated later weapon actions.

   Suggested fix: carry a deterministic damage-source classification from spell creation through the damage call. Apply spell modifiers to that source and melee modifiers only to actual melee hits; do not infer the source from a caster-wide timer or current animation.

5. **[P2 / Medium] Relocating an `ori` changes the expression's grouping and produces an invalid address.**

   Location: `tools/recomp/reloc.py:252`.

   Failure scenario: a translated `lui`/`ori` pair forms an address in a table moved to the low-memory relocation arena. The generator emits `register | immediate + delta`. C++ evaluates the addition before the OR, so the original upper bits can be reintroduced after the relocation, sending subsequent reads/writes to the wrong guest address. Dynamic relocation of old addresses cannot repair an address already corrupted this way.

   Evidence: calling the actual `apply` function for a synthetic address `0x400010` relocated to `0x90000` emitted the unparenthesized expression. Its low 32-bit result was **`0xffc90000` instead of `0x90000`**.

   Suggested fix: apply the relocation to the completed OR expression, with the intended MIPS register-width and sign semantics. Add small synthetic translation checks covering negative deltas and carries/borrows across the immediate boundary.

6. **[P2 / Medium] One successful UDP reply disables automatic fallback for the carrier's entire lifetime.**

   Location: `tools/recomp/net2/session_net.cpp:812`; state is latched at `tools/recomp/net2/carrier.cpp:213`.

   Failure scenario: a client first joins a room on a network where UDP works, then reconnects on a network that blocks UDP. `answered_` remains true forever: `close`, `end`, `begin`, and link teardown never reset it. Although `drop_link` resets `udp_since`, the automatic tunnel condition can no longer become true. HTTPS/TCP can reconnect successfully while the service never sees a fresh UDP hello, preventing room startup or a usable relay route until the process is restarted or tunneling is forced manually.

   Suggested fix: track the last validated reply and connection/network epoch instead of a lifetime boolean. Reset or expire reachability when reconnecting and retry the tunnel after the current hello sequence has gone unanswered.

7. **[P2 / Medium] The WebSocket client has an unbounded decoded receive queue.**

   Location: `tools/recomp/net2/tls.cpp:211` (also lines 174–180 and 230–235).

   Failure scenario: a malicious or compromised configured service continuously sends valid frames containing short, newline-terminated records. Each `recv` first pumps up to 16 × 8,192 bytes into `data`, then returns only the caller's requested 8,192 bytes. The per-frame limit does not bound accumulated decoded data, and the upper session parser cannot enforce its incomplete-line limit on bytes it has not received. Sustained input can exhaust client memory; `state` and `send` also pump incoming data without draining this queue.

   Evidence: the actual `WsLink`, driven by a synthetic stream of valid 8,192-byte frames, retained **12,281,600 decoded bytes after 100 reads**. Each read consumed the session caller's normal 8,192-byte buffer.

   Suggested fix: impose an aggregate receive budget and stop reading from the underlying link while decoded data awaits consumption. Reject oversized aggregate messages and apply the same bounded policy to control-frame responses.

8. **[P2 / Medium] Tunneling moves a bounded datagram queue into an unbounded session output string.**

   Location: `tools/recomp/net2/session_net.cpp:864` (also `send_line` at lines 402–405).

   Failure scenario: during a tunneled game, the service or network stops accepting outgoing TCP data while the connection remains established. `send_tunnel` converts every pending datagram to a hex line, appends it to `outbuf`, and clears the carrier queue before checking whether anything was sent. The carrier's 512-datagram limit and `WsLink`'s output threshold therefore provide no bound on the upstream session string. Repeated gameplay sends continue allocating memory and accumulating stale input; a peer that keeps sending small inbound records can prevent the idle timeout while never draining this output.

   Suggested fix: enforce an aggregate byte budget before moving datagrams into the session queue. Propagate backpressure or fail the stalled transport explicitly instead of acknowledging unlimited buffering; account for hex and frame overhead in the limit.

9. **[P2 / Medium] The trusted-proxy socket is writable by every local user.**

   Location: `tools/rendezvous/rendezvous.py:514`; trusted address assignment at line 839; deployment directory permissions in `tools/rendezvous/deploy/champions-net2.service:39`.

   Failure scenario: an unprivileged process on the service host connects directly to the mode-0666 Unix socket and supplies an arbitrary `X-Real-IP`. Every connection on that socket is treated as trusted proxy traffic, so the process can rotate claimed addresses to evade per-address connection, registration, and bad-login limits, or consume another address's quota. The shipped mode-0755 runtime directory permits reaching the socket. Player HMAC authentication still applies; the bypass is of proxy/source-address trust and its abuse controls.

   Suggested fix: restrict the socket and directory to the service and proxy accounts, using a dedicated group or socket activation with mode 0660. Where supported, validate Unix peer credentials before trusting forwarded address headers.

10. **[P2 / Medium] The alternate Mac build omits the new required party8 implementation.**

    Location: `tools/recomp/app/app_main.cpp:494`; incomplete source list at `tools/recomp/app/build_win.py:412`.

    Failure scenario: `build_win.py --mac` compiles `app_main.cpp`, which now unconditionally calls `party8::blank` and exposes `party8::command`, but its source list never includes `party8.cpp`. The final link therefore has undefined party8 symbols even when relocation mode is not requested. The normal `app/build.py` source list includes the implementation, which hides the omission when only that route is used.

    Evidence: static inspection of the complete `build_mac` source and link manifests; the game application was not built.

    Suggested fix: include the required implementation in this build route, or explicitly compile a compatible disabled implementation and guard unavailable commands. Keep common required application modules in a shared build manifest.

Guest-memory review: the seven current `guestmap.h` reservations are pairwise disjoint. The check also included the runtime kernel/stack region, the RPC packet scratch block, actual soak writes, relocation arenas, and the current four-player combat/aim/cutscene sublayouts. No additional live-block overlap was confirmed. The map is incomplete: soak writes extend through `0xE0057` although its reservation ends at `0xE0050`, and RPC packets occupy `[0xFF000, 0x100000)` outside the list. Neither currently collides with another reviewed allocation; both should be included before treating the map's assertion as complete coverage.

Summary: **10 findings: 2 P1 and 8 P2.** The main lockstep blocker is cutscene bookkeeping outside synchronized ticks. The highest-priority security issue is the relay service's unbounded pong queue. The synthetic probes establish the reported local mechanisms, not successful two-machine gameplay or a live-service exploit.
