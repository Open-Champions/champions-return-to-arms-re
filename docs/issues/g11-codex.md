# G11 investigation, 2026-10-27

STATUS: PARTIAL. The crash mechanism is established and contained. The first
corrupting write, and the cause of the reported boot hang, remain unknown. G11
should stay open.

Worktree base: `d00d858`. The native application notes are at
[`native-app.md`](native-app.md), not `docs/native-app.md` in this tree.

## Cause and evidence

**Observed in the crash report and its matching binary:** `rt_sleep` followed a
damaged link in the guest thread ready queue. It treated `0x00ccdbdc` as a thread
number, although the kernel has only 256 thread slots, and read outside guest RAM.
This establishes the immediate cause of the access fault. It does not identify
who damaged the queue.

The matching report available here is
`~/Library/Logs/DiagnosticReports/rta_app_playc-2026-10-27-044511.ips`.
There were no `rta_app-2026-10-27-*.ips` files under that exact name. The retained
`local/recomp-out/bin/rta_app_playc` has UUID
`AF02EF06-A868-3613-8E0B-4A2AB49A9A8D`, matching the report. It was inspected with
`dwarfdump --uuid` and LLDB without launching it. Quit-time `reschedule` crashes
were not used as evidence for this issue.

The fault is at `rt_sleep + 216`, image offset `0xbd3d8`, in the inlined
`unlink_thread` traversal. The saved registers give:

| Value | Meaning |
|---|---|
| `x8 = 1` | the calling guest thread |
| `x12 = 0x7227408000` | the guest RAM base |
| `x13 = 0x00ccdbdc` | the link being treated as a thread number |
| `x14 = 0x2cd127ec` | the computed offset of that supposed thread's next link |
| `0x7227408000 + 0x2cd127ec = 0x725411a7ec` | exactly the reported fault address |

The kernel layout gives the same offset:
`0x11000 + (0x00ccdbdc - 1) * 56 + 4 = 0x2cd127ec`.
Neither a condition-variable wait nor a freed host waiter is the faulting access.
The report does not contain the preceding queue contents, so it does not tell us
which original link first became invalid.

Two details of the old issue description need qualification:

- `fn_003566f0` is the runtime's `sceSifCallRpc` replacement. Its callers here are
  the CD streaming wrapper, `sceCdStRead`, `lump_pollAsync`, and the main session
  loop. This is a streaming read on the boot/front-end route, not evidence of a
  particular start-up handshake failing.
- The report records launch at `04:40:25.5195 -0500` and capture at
  `04:44:55.5047 -0500`: about 270 seconds. The reported 145-second wait cannot be
  reconciled from the retained evidence. The reused `n11/run.json` starts at
  `04:45:06`, after this crash; its current logs belong to the successful retry.

## What the code review found

**Read, not proof of every possible interleaving:**

- `thread_main` holds `g_big` while running guest code. `wait_for_baton` releases
  that mutex while waiting and tests a predicate, so notification before the new
  host thread begins waiting is not lost. `rt_sleep`, system calls, interrupt
  callbacks, and the deferred IOP completions share that serialized execution.
- `WaitSema` and `SleepThread` record their state before yielding. Semaphore
  counts and pending wakeups handle a signal or wake that arrives before a wait.
  The timed sleep queues a callback on the virtual clock; there is no host timer
  that frees its waiter. `GThread` objects are not deleted by this runtime.
- `iop_init` allocates IOP RAM before guest host threads start. Blocking RPCs
  serve the request synchronously, then sleep for virtual time. Asynchronous
  completions run through `rt_after`; the SIF boot status reply does too.
- `--mute` sets the output gain to zero; it still opens the audio device. The
  sound engine is initialized before device start, and the device pull and game
  RPC use the engine lock. The mixer uses IOP/sample memory, not the guest ready
  queue. This does not establish that all sound-buffer accesses are race-free.
- The display-link callback updates atomic timing values. It does not write
  guest memory or schedule guest threads.
- Disc and memory-card reads in `iop.cpp` run synchronously on the serialized
  guest side. The POSIX file helper uses a seek followed by a read, which would
  need protection if the same handle were shared concurrently. No such boot
  reader was found: the application disc check/extraction uses its own handle,
  and the audio puller does not read that disc handle.

One unresolved lead is the streaming destination: `serve_disc`, server
`0x80000595`, function `9`, command `2`, masks the supplied pointer with
`RAM_SIZE - 1` before checking it and immediately copies sectors there. A bad
pointer can therefore become a low-memory destination. That is a possible
queue writer on this exact stack, but the crash report contains neither that
pointer nor the read's data. It is not established as G11's cause, and its guest
semantics have not been changed on that assumption.

## Change

`tools/recomp/rt/runtime.cpp` now checks a queue link before turning it into a
thread-table address. All four ready-queue traversals use the check: insertion,
removal, selection, and priority rotation. A traversal also stops after 256
nodes, so a damaged cycle cannot spin forever.

An invalid queue exits with code 3 and reports the link's guest address, value,
current thread, field, and last guest call site. It does not repair the queue or
continue a corrupted game. This contains the demonstrated unsafe traversal; it
does **not** fix the unknown corruption or prove the historical hang is gone.

For valid queues the checks only read memory and count host loop iterations.
They add no guest writes, virtual time, scheduling decisions, RPC delays,
game patches, or guest instruction-budget charges.

## Verification

The authored fixture in `tools/recomp/rt/tests/` includes the production runtime
and links the production IOP, script, POSIX host, and silent sound implementation.
It requires no executable, disc, generated game header, renderer, or window.

```
python3 tools/recomp/rt/tests/run.py --baseline d00d858 --sanitize
python3 tools/recomp/rt/tests/run.py
python3 tools/recomp/app/build.py --as rta_app_g11
```

**Executed:** all eight fixture cases passed with AddressSanitizer and
UndefinedBehaviorSanitizer, and with the production optimization level `-O2`.
The valid case performs 64 sequential host-thread start/wait/wake/return/delete
rounds, reusing a guest slot. It covers signal-before-wait, wake-before-sleep,
suspending a timed waiter, blocking and asynchronous RPCs, and the SIF status
handshake. These are synthetic start-up primitives, not 64 complete game boots.
The other cases cover a full 256-node queue, bad head/next links, a cycle, and
each traversal entry point.

Against unmodified `d00d858`, the complete 32 MB synthetic guest RAM and the
recorded event/time trace are byte-identical. Their combined SHA-256 is
`18ce13fd2bc359d3a9a0270d64800316277abf4872a07ef6b2ada13cd1d7ba5e`.
The same fingerprint was obtained with `-O2`. Injecting the recorded invalid
thread number into a synthetic next link produces an AddressSanitizer memory
fault in the baseline and the intended diagnostic in the candidate. This is a
deterministic reproduction of the unsafe access, not of the unknown writer.

**Built:** `local/recomp-out/bin/rta_app_g11`, successfully with the requested
command. The build also makes its usual `rta_native_fix` by-product. The hashes
and modification times of `rta_app` and `rta_app8` remained unchanged.

**Ran:** exactly one game process, `rta_app_g11 --mute`, in a small test window,
with its control socket enabled and an isolated copy of the retry's memory card.
A bounded input script reached the front end (`intro`, tick 10) at field 354,
waited another 30 fields, and exited with code 0. Total process time was
6.963 seconds; it did not reach the external 30-second timeout. The display link
started, and the muted real-time audio device made 546 requests. No invalid
queue diagnostic occurred. This was a boot smoke check, not an FPS benchmark.

Private evidence is under `local/g11-codex/`: `build.log`,
`kernel-sanitized.log`, `kernel-o2.log`, `boot.log`, `boot-result.json`,
`boot.rig`, and `protected-binaries.json`. No game-derived material was added
to tracked files.

## Still uncertain

The original corruption and hang were not reproduced. One successful start
does not establish a fix for an intermittent failure. Full gameplay, online
lockstep, and an emulator comparison were not rerun; byte identity above is
limited to the synthetic kernel/RPC workload. The normal guest path is unchanged
by inspection, but that is not a new full-game parity claim.

The next occurrence needs the first bad write: retain a separate evidence
directory, record the stream's raw destination/count before the copy, and use
the diagnostic's queue-link address to place a conditional write watchpoint.
That can distinguish a bad disc destination from a guest write or a scheduler
link error without guessing from the later `rt_sleep` stack.
