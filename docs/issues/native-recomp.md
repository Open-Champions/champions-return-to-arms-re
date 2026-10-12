# Native build by static recompilation: feasibility spike

Started 2026-10-11. Question: if the executable's MIPS R5900 code is translated to C++ once
and compiled for the host, does the translated code compute the same game as the original,
tick for tick, and how much platform work stands between that and a playable native
Mac/Windows application?

This file is written as the work proceeds; every section says what was **Ran** (executed
here, with the numbers), what was only **Read**, and what was **Not reached**.

Where things are:

| What | Where | In the repository? |
|---|---|---|
| translator (Python), runtime (C++), tests | `tools/recomp/` | yes — ours |
| generated C++, objects, binaries, logs, dumps | `local/recomp-out/` | no — derived from the game |

Prior art named because ideas were borrowed (nothing was downloaded, no code copied):
**N64Recomp** (one C function per game function, a context struct, a lookup table for
indirect calls, host threads for guest threads) and **PS2Recomp** by ran-j (the same shape
applied to the R5900: 128-bit registers, a runtime that answers syscalls).

## Status

(kept current; see the sections below for evidence)

- Step 1 translator: in progress
- Step 2 differential test: not started
- Step 3 platform boundary and runtime: not started
- Step 4 boot and compare with the rig: not started
- Step 5 verdict: not started

## Facts about the input (Ran: opcode census over the function table)

- `.text` 0x100000–0x3e5c40; `ghidra_funcs.tsv` has 7,732 functions in 9,979 address
  ranges (814 functions have more than one range, separated by padding words). 329 regions
  of `.text` with non-zero words are in no function range; no `jal` targets them, so they
  are reached through pointers or by falling/branching in from a neighbour. The translator
  must cover them.
- A second loaded segment, `.loadScreenSection`, sits at 0x1800000 (0x118200 bytes).
- `.vutext` 0x3e5c40 (0x3d40 bytes) is vector-unit microcode, not MIPS code.
- Instruction mix inside the function ranges: 82 `SYSCALL`, 181 `BREAK`, 13 COP2
  instructions in all (two `VCALLMS` in `anim_buildPose` 0x16f594/0x16f5f4, the rest
  control-register moves and two `LQC2`), 5 reads of the COP0 cycle counter
  (0x19d1e0, 0x2177b8, 0x218d10, 0x3229f0, 0x322a00), no `CFC1` (so the FPU flag bits
  are never read; only the compare bit matters), FPU arithmetic limited to
  add/sub/mul/div/sqrt/rsqrt/abs/neg/mov/max/min/adda/cvt and three compares, and 33
  distinct multimedia (MMI) operations, all of which `tools/ee_emu.py` implements.
- The two ERX modules on the disc (`LIBINSCK.ERX`, `NG_INSCK.ERX`) are relocatable EE code
  loaded by the network set-up window only; offline play does not need them.
