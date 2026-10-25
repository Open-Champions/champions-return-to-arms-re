# Level scripts: the virtual machine and its built-in commands

Area `script`, code range 0x13ecf8–0x147300: the interpreter, 22 library routines of the
virtual machine, 7 shared helpers and 180 built-in handlers (195 functions known to Ghidra plus
15 small routines it missed). The other 10 built-in handlers (0x1473b4–0x14799c) sit just past
the range, in `objects`; they are documented here because the built-in table is one unit.
Symbols: `symbols/script.tsv`.

Everything below was read from the executable and from the 120 decompiled level scripts.
Nothing was confirmed on a running game — true when written and still true of this
document. Since then the interpreter has been executed opcode by opcode in
`tools/ee_emu.py` (`docs/spec/script-machine.md`; results folded in here are marked
**executed**), so have all 190 built-in handlers (`docs/spec/script-builtins.md`, FINDINGS
X19; its section 9 corrections are folded into 1.7 and the built-in tables, marked
"Executed"), and the project has a live game — the Play! emulator, which is not a PlayStation 2 and not PCSX2
— whose runs are listed in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`.
Those runs loaded the levels `hub` and `strife`; nothing about a script was logged or
compared in them. No test patch has been run on a live game.
Claims are **Observed** unless marked otherwise.

## What this area is

Each level lump may contain a `script.scr`. It is a compiled program for a small
register machine: named entry points, global variables, and calls to 191 built-in commands
implemented in the executable. The game never runs a script continuously. Game code calls one
entry point by name, the interpreter runs it to its `return`, and control goes back. Anything
that takes time is done by a script asking to be called again on the next frame.

The three things a newcomer should know first:

1. **The machine is the Small "abstract machine" (AMX)**, the embeddable interpreter that later
   became Pawn. Its public documentation therefore describes the bytecode, the file header and
   the host interface. See 1.1 for the evidence.
2. **There is one machine per level and no scheduler.** `script_runByName` (0x1ed694) is the
   only way in. It has about 50 call sites: trigger volumes, creature life-cycle events,
   interactable objects, the dialog system, a per-frame "deferred call" queue, and, importantly,
   several **draw** functions (section 5, P1).
3. **Built-ins trust the script completely.** No handler checks its argument count, many do not
   check that a named object exists, strings are copied into fixed stack buffers without a
   length limit, and no handler can report an error to the interpreter.

## 1. The machine

### 1.1 Identification

| Evidence | Where |
|---|---|
| Loader accepts only a header whose 16-bit word at +4 is 0xf1e0 and whose word at +0xa is 0x18 | `scr_load` 0x13e8f8; same magic test in `scr_getFlags` 0x141018 |
| Header layout (code, data, heap, stack top, start address, three name tables of 24-byte records) | `scr_load`, `scr_interpret` 0x13ed78–0x13ee28, `scr_findEntry` 0x13eac8 |
| Error numbers 3, 4, 5, 6, 7, 8, 9, 11, 16–24 used exactly as in AMX | `scr_interpret`, library routines in 1.8 |
| Opcode numbering 0x00–0x82 with the AMX meanings (51 decoded independently for `tools/scr.py`, about 25 more read here) | handler table 0x403150 |
| A debug string of the game calls its own save hook "amx…" | used by `script_saveCheckPoint` 0x142a40 |

Inferred from these: the library is the stock Small run-time of about 2002–2003 (file version 3,
20-byte names), compiled with computed-goto dispatch. The AMX routine each function corresponds
to is given in 1.8 and in the symbol notes.

All 120 `script.scr` files have: magic 0xf1e0, file version 3, minimum machine version 1, flags 0,
record size 24, no start address (-1), no libraries, no public variables, and exactly 8192 bytes
(2048 cells) between heap start and stack top. The file on disc is 0x60 + stack-top bytes long,
so the heap and stack live inside the loaded file image.

### 1.2 The machine structure

The first 0x60 bytes of `script.scr` are zero on disc and become the machine structure in
memory; the AMX header follows at file offset 0x60. `g_scriptMachine` (0x86b270) points at it.

| Offset | Size | AMX name | Meaning | How we know |
|---|---|---|---|---|
| +0x00 | ptr | base | address of the header (machine + 0x60) | `scr_load` |
| +0x04 | ptr | callback | built-in dispatcher; `scr_callNative` 0x141050 unless already set | `scr_load`; loaded before every dispatch (0x140c50) |
| +0x08 | ptr | debug | debug hook, default 0x1410b0; never called by this interpreter | `scr_load` |
| +0x0c | i32 | cip | code offset saved before each built-in call | 0x140c48, 0x140c98 |
| +0x10 | i32 | frm | frame pointer saved before each built-in call | 0x140c4c, 0x140cb0 |
| +0x14 | i32 | hea | heap top (data-relative) | read 0x13eda4, saved 0x140c40 |
| +0x18 | i32 | stk | stack pointer (data-relative). Not "restored to its entry value on every exit", as the earlier version said: RETN stores the *current* stack pointer here (0x13fc24, nested returns too); RET, HALT and the run-time errors store the entry value; the entry checks and the STACK and HEAP error returns store nothing. A balanced entry point leaves it where it was, an unbalanced one moves it for every later run (`docs/spec/script-machine.md` 4.3 and 9, executed) | 0x13ed8c, 0x13fbc0, 0x13fc24 |
| +0x1c | i32 | stp | stack top = end of script memory | bounds tests, e.g. 0x13f0b0 |
| +0x20 | u32 | flags | 0x2000 loaded, 0x8000 code relocated (required to run, else error 22), 0x4000 cleared on every run | 0x13ed5c–0x13ed74, `scr_relocate` |
| +0x24, +0x28 | i32 | curline, curfile | written by the LINE opcode | 0x140d48, 0x140d68 |
| +0x2c | i32 | dbgcode | last debug record kind seen by the relocator | `scr_relocate` |
| +0x30..+0x38 | | dbgaddr, dbgparam, dbgname | debug records | 0x140d90–0x140db0 |
| +0x3c | 4 × i32 | usertags | tags for user data | `scr_getUserData` 0x1411c8 |
| +0x4c | 4 × ptr | userdata | user data pointers (unused by the game) | same |
| +0x5c | i32 | error | zeroed before each built-in, returned by the dispatcher; non-zero aborts the run | `scr_callNative`, 0x140c5c |

### 1.3 The file header (at machine + 0x60)

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | i32 | size of the file part (header, tables, code, data) |
| +0x04 | u16 | magic 0xf1e0 |
| +0x06, +0x07 | u8 | file version (3), required machine version (1; loader refuses 4 or more with error 18) |
| +0x08 | u16 | flags: bit 0 must be clear (error 17), bit 2 = compact encoding, expanded in place by the loader |
| +0x0a | u16 | size of a name-table record, must be 24 |
| +0x0c | i32 | code start |
| +0x10 | i32 | data start; every script address is relative to this |
| +0x14 | i32 | heap start = end of initialised data |
| +0x18 | i32 | stack top; the loader lowers it by one cell and zeroes that cell |
| +0x1c | i32 | start address of `main`, -1 in every shipped script |
| +0x20, +0x24 | i16, i32 | entry points: count, table offset. Record = {code offset, name[20]}, sorted by name |
| +0x28, +0x2c | i16, i32 | built-ins used by this script: count, table. Record = {0 on disc / handler address after load, name[20]} |
| +0x30, +0x34 | i16, i32 | libraries (none) |
| +0x38, +0x3c | i16, i32 | public variables (none) |

Entry-point names are limited to 19 characters. The 120 scripts define 1,828 entry points
(at most 165 in one level) and import at most 40 built-ins each.

### 1.4 Registers

The interpreter (`scr_interpret`, 0x13ecf8–0x140f10) is one function. Each opcode handler ends
by fetching the next code word, which the loader has already replaced by the handler's address,
and jumping to it.

| Machine register | Name in `tools/scr.py` | Held in | Notes |
|---|---|---|---|
| PRI | A | `$a1`, mirrored at host sp+4 | accumulator; result of every built-in |
| ALT | X | `$s5` | second operand, array base |
| CIP | | `$s0` | host pointer into the relocated code |
| FRM | | `$fp` | data-relative frame pointer; `local[n]` is `[FRM + n]` |
| STK | | `$s6` | data-relative stack pointer, grows down |
| HEA | | `$s3` | data-relative heap top, grows up |
| data base, code base | | `$s1`, `$t3` | header + data start, header + code start |
| entry STK | | `$t4` | written back to machine +0x18 on the RET, HALT and run-time error exits only; RETN writes the current STK instead and the entry, STACK and HEAP error returns write nothing (`docs/spec/script-machine.md` 4.3, executed; the earlier version said "on every exit path") |
| machine | | `$s7` | |

There are no other registers and no flags: comparisons leave 0 or 1 in PRI, or are fused with
the jump.

### 1.5 Memory, variables and the stack

One block of cells holds everything, addressed from the data start:

```
0 .............. HEA ......................... STK ............ STP
 globals, strings   heap (grows up)   free    stack (grows down)
```

- **Global variables** (`var[0x..]` in the script listings) and string literals are the
  initialised data. They keep their values for as long as the level's lump stays loaded and
  are not part of a save. Nothing resets them between calls.
- **The heap** is used only by the HEAP opcode (no shipped script uses it).
- **The stack** holds arguments, return offsets, frame links and locals. Heap and stack share
  8192 bytes. The entry sequence and the STACK and HEAP opcodes fail with error 3 when fewer
  than 0x40 bytes separate the two, error 7 when STK passes the top, error 8 when HEA goes
  negative. Plain pushes are not checked. Two details from `docs/spec/script-machine.md`
  4.1 (executed): at entry "the top" is the *header's* stack-top field (0x13ed90–0x13edac),
  which is larger than the machine's by the data start, so a stack pointer up to that many
  bytes above the real top is accepted; and the entry's error 3 is tested after the entry
  cells have been written.
- Indirect loads and stores check the address: it must be below HEA or at/above STK, and below
  STP, otherwise error 5 (for example 0x13f098–0x13f0bc). The compares are signed, so every
  negative address passes; and the check exists in six opcodes only (LOAD.I, LODB.I,
  STOR.I, STRB.I, LIDX, LIDX.B) — every other opcode reads and writes wherever its operand
  points (`docs/spec/script-machine.md` section 3, executed).

A run that fails returns its error number to the host. `script_runByName` ignores it, so a
failing script simply stops and its caller sees result 0.

### 1.6 Calls

**Game to script** (`scr_interpret(machine, &result, entryIndex, argCount, args)`): the
arguments are copied below the current STK, then the argument byte count, then a zero return
offset. Execution starts at the entry point's code offset with FRM = 0. The only game-side
caller (0x1ed70c) passes no arguments, so entry points never receive any. Entry index -1 means
`main`, which no shipped script has (error 20). Indexes below −2 are refused, but −2 is
not: the "record" two places before the table is read. PRI is not initialised at entry —
it is whatever the interpreter's own stack frame held; compiled functions set it before
they return (`docs/spec/script-machine.md` 4.1, executed).

**Script to script** (CALL): pushes the return offset and jumps. The callee starts with PROC
(push FRM, FRM = STK) and ends with RETN (pop FRM, pop the return offset, drop the argument
bytes counted by the cell that follows). A frame therefore looks like this:

| Address | Content |
|---|---|
| FRM + 12 + 4k | argument k |
| FRM + 8 | argument byte count |
| FRM + 4 | return offset (0 = return to the game) |
| FRM + 0 | caller's FRM |
| FRM - 4… | locals |

When the popped return offset is 0 the run ends: PRI is stored through the result pointer and
the interpreter returns 0 (0x13fc20–0x13fc3c).

**Script to built-in** (SYSREQ.C *n*, 0x140c88): the script pushes the arguments right to left,
then the byte count, executes SYSREQ.C with the index of the built-in in *its own* import table,
and afterwards drops the arguments with STACK. The interpreter saves CIP, FRM, HEA and STK into
the machine structure and calls the dispatcher at machine +4:

```
dispatcher(machine, index, &PRI, params)     // scr_callNative
    machine.error = 0
    PRI = handler[index](machine, params)    // params[0] = byte count, params[1..] = arguments
    return machine.error                     // always 0: nothing ever sets it
```

So every built-in has the signature `int handler(machine, cell *params)`, reads argument *k* at
`params + 4k`, and whatever it leaves in the return register becomes PRI. Handlers written as
"void" (for example `callScript`, `getv`, `dialogRunning`) return whatever their last callee
returned. Because the machine state is saved before the call, a built-in may start another run
on the same machine (`callScript`, or a built-in whose effect makes the game run a script,
such as `grantSilver`, which runs the entry point `firstSilver`); the nested run uses the stack
below the current STK.

There is no instruction budget, no yield and no sleep. A script that loops forever hangs the
game. `scr_raiseError` (0x141498) exists but nothing references it.

### 1.7 Strings and names

- A string argument is a data-relative address. Handlers convert it with `scr_getAddr`
  (0x1414a8, bounds check, result ignored by callers) and `scr_getString` (0x141650) into a
  stack buffer of 128 or 160 bytes. There is no length limit on the copy. The bounds
  check is the signed one of 1.5, so `scr_getAddr` accepts negative addresses.
  "Result ignored" has a consequence (executed, `docs/spec/script-builtins.md` 1.2; FINDINGS N1): on
  a refusal `scr_getAddr` returns 5 **without writing the pointer** (0x1414d8), so the
  handler goes on and converts whatever its stack slot still points at — the string of the
  last built-in call that used a slot at the same frame distance. A shipped script relies
  on it: TORMEDAL `start` indexes an array of 20 names with 20, and `rootMonster` and
  `setCFlag` act a second time on the twentieth name. Deterministic, so not a desync; a
  rebuild that validates addresses behaves differently.
- Script string literals are *packed*: four characters per cell, first character in the most
  significant byte. `scr_getString` recognises a packed string by its first cell being above
  0xff; otherwise it reads one character per cell. That test is signed too: a packed
  string whose first character is 0x80 or above has a negative first cell and is read as
  unpacked (`docs/spec/script-machine.md` section 7, executed).
- **Entry points** are found by `scr_findEntry` (0x13eac8): binary search with a case-sensitive
  compare over the sorted table. A name of 20 or more characters can never match.
- **Built-ins** are bound at load: `scr_registerNatives` (0x141310) walks the script's import
  records and copies the handler address from the global table 0x403370 (191 × {name pointer,
  handler}, zero terminated) for each matching name.
- **Objects** are found by name with `world_findObjectsByName` (0x14bf58, case-insensitive hash
  of 512 slots, results in table order) or its first-match wrapper `world_findObjectByName`
  (0x14f498). Several objects may share a name; most built-ins act on all of them.
- **Text** arguments are keys for `text_lookup` (0x173c84). **Resources** are a lump name plus
  an entry name for `res_find` (0x17365c). **Quest variables** are looked up by lower-cased
  name in `g_questVars`. **Items** are descriptor strings for `item_parseDescriptor` (0x1069b8).

### 1.8 Library routines in this range

| Address | Name | AMX routine | Used by the game |
|---|---|---|---|
| 0x13ecf8 | `scr_interpret` | amx_Exec | yes (0x1ed70c; also called with a null machine by the relocator to fetch the handler table) |
| 0x140f10 | `scr_setString` | amx_SetString | no |
| 0x141018 | `scr_getFlags` | amx_Flags | no |
| 0x141050 | `scr_callNative` | amx_Callback | yes, through machine +4 |
| 0x1410b0 | `scr_debugHookDefault` | default debug hook (returns 21) | stored, never called |
| 0x1410b8 | `scr_returnErr24` | JIT stub (returns 24) | no |
| 0x1410c0 | `scr_nameLength` | amx_NameLength | no |
| 0x1410d8 | `scr_numEntries` | amx_NumPublics | no |
| 0x1410f0 | `scr_getEntryName` | amx_GetPublic | no |
| 0x141140 | `scr_numPubVars` | amx_NumPubVars | no |
| 0x141158 | `scr_getPubVar` | amx_GetPubVar | no |
| 0x1411c8 | `scr_getUserData` | amx_GetUserData | no |
| 0x141240 | `scr_setUserData` | amx_SetUserData | no |
| 0x141310 | `scr_registerNatives` | amx_Register | yes (0x147a94) |
| 0x141460 | `scr_nativeInfo` | amx_NativeInfo | no |
| 0x141478 | `scr_setCallback` | amx_SetCallback | no |
| 0x141488 | `scr_setDebugHook` | amx_SetDebugHook | no |
| 0x141498 | `scr_raiseError` | amx_RaiseError | no |
| 0x1414a8 | `scr_getAddr` | amx_GetAddr | yes, 107 call sites |
| 0x1414f8 | `scr_allot` | amx_Allot | no |
| 0x141550 | `scr_release` | amx_Release | no |
| 0x141568 | `scr_strLen` | amx_StrLen | no |
| 0x141650 | `scr_getString` | amx_GetString | yes, 106 call sites |

Just below the range (in `netcode`'s address range but part of this library): `scr_relocate`
0x13e6d0 (amx_BrowseRelocate), `scr_load` 0x13e8f8 (amx_Init), `scr_findEntry` 0x13eac8
(amx_FindPublic), `scr_findInTable38` 0x13ebd8 (amx_FindPubVar).

Ghidra did not create functions for 0x141018, 0x1410b0–0x1410d8, 0x141140, 0x1411c8, 0x141240,
0x141460–0x141498, 0x1414f8, 0x141550 and 0x144198; they have no direct callers. They were read
with `tools/dis.py`.

### 1.9 Opcodes

131 handlers (table 0x403150). "In scripts" marks the 51 opcodes that occur in the 120 shipped
scripts. Mnemonics are the AMX ones; `[x]` is the cell at data address x. The opcodes used by
the scripts, and in addition 0x00, 0x05–0x08, 0x1a, 0x1f, 0x20, 0x26, 0x2a, 0x2d, 0x2f, 0x32,
0x49, 0x4d, 0x75–0x78, 0x7a, 0x7c and 0x7e–0x82, were read in the handlers. The meaning of the remaining ones is Inferred from the numbering.

| Op | Mnemonic | Meaning | Handler | In scripts |
|---|---|---|---|---|
| 0x00 | NONE | invalid: returns error 6 | 0x13eea8 |  |
| 0x01 | LOAD.pri a | PRI = [a] | 0x13eeb8 | yes |
| 0x02 | LOAD.alt a | ALT = [a] | 0x13eef0 | yes |
| 0x03 | LOAD.S.pri o | PRI = [FRM+o] | 0x13ef28 | yes |
| 0x04 | LOAD.S.alt o | ALT = [FRM+o] | 0x13ef60 | yes |
| 0x05 | LREF.pri a | PRI = [[a]] | 0x13ef98 |  |
| 0x06 | LREF.alt a | ALT = [[a]] | 0x13efd8 |  |
| 0x07 | LREF.S.pri o | PRI = [[FRM+o]] | 0x13f018 |  |
| 0x08 | LREF.S.alt o | ALT = [[FRM+o]] | 0x13f058 |  |
| 0x09 | LOAD.I | PRI = [PRI], address checked | 0x13f098 | yes |
| 0x0a | LODB.I n | PRI = n bytes at [PRI] | 0x13f0f0 |  |
| 0x0b | CONST.pri v | PRI = v | 0x13f1a0 | yes |
| 0x0c | CONST.alt v | ALT = v | 0x13f1d0 | yes |
| 0x0d | ADDR.pri o | PRI = FRM+o | 0x13f200 |  |
| 0x0e | ADDR.alt o | ALT = FRM+o | 0x13f238 |  |
| 0x0f | STOR.pri a | [a] = PRI | 0x13f270 | yes |
| 0x10 | STOR.alt a | [a] = ALT | 0x13f2a8 |  |
| 0x11 | STOR.S.pri o | [FRM+o] = PRI | 0x13f2e0 | yes |
| 0x12 | STOR.S.alt o | [FRM+o] = ALT | 0x13f318 |  |
| 0x13 | SREF.pri a | [[a]] = PRI | 0x13f350 |  |
| 0x14 | SREF.alt a | [[a]] = ALT | 0x13f390 |  |
| 0x15 | SREF.S.pri o | [[FRM+o]] = PRI | 0x13f3d0 |  |
| 0x16 | SREF.S.alt o | [[FRM+o]] = ALT | 0x13f410 |  |
| 0x17 | STOR.I | [ALT] = PRI, address checked | 0x13f450 | yes |
| 0x18 | STRB.I n | n bytes at [ALT] = PRI | 0x13f4a0 |  |
| 0x19 | LIDX | PRI = [ALT + PRI*4], address checked | 0x13f550 | yes |
| 0x1a | LIDX.B s | PRI = [ALT + (PRI shifted left by s)] | 0x13f5b0 |  |
| 0x1b | IDXADDR | PRI = ALT + PRI*4 | 0x13f620 | yes |
| 0x1c | IDXADDR.B s | PRI = ALT + (PRI shifted left by s) | 0x13f650 |  |
| 0x1d | ALIGN.pri n | byte-order adjustment of PRI: for 0 ≤ n < 4 (unsigned), PRI ^= 4 − n | 0x13f688 |  |
| 0x1e | ALIGN.alt n | same for ALT | 0x13f6e8 |  |
| 0x1f | LCTRL i | PRI = control register i (0 COD, 1 DAT, 2 HEA, 3 STP, 4 STK, 5 FRM, 6 CIP) | 0x13f740 |  |
| 0x20 | SCTRL i | control register i = PRI (2 HEA, 4 STK, 5 FRM, 6 CIP) | 0x13f7d8 |  |
| 0x21 | MOVE.pri | PRI = ALT | 0x13f848 | yes |
| 0x22 | MOVE.alt | ALT = PRI | 0x13f878 | yes |
| 0x23 | XCHG | swap PRI and ALT | 0x13f8a0 |  |
| 0x24 | PUSH.pri | push PRI | 0x13f8d8 | yes |
| 0x25 | PUSH.alt | push ALT | 0x13f908 | yes |
| 0x26 | PUSH.R n | push PRI n times | 0x13f970 |  |
| 0x27 | PUSH.C v | push v | 0x13f938 | yes |
| 0x28 | PUSH a | push [a] | 0x13f9d0 | yes |
| 0x29 | PUSH.S o | push [FRM+o] | 0x13fa10 |  |
| 0x2a | POP.pri | PRI = pop | 0x13fa50 |  |
| 0x2b | POP.alt | ALT = pop | 0x13fa80 | yes |
| 0x2c | STACK n | ALT = STK, then STK += n (error 3 or 7 when out of range) | 0x13fab0 | yes |
| 0x2d | HEAP n | ALT = HEA, then HEA += n (error 3 or 8) | 0x13fb08 |  |
| 0x2e | PROC | push FRM, FRM = STK | 0x13fb58 | yes |
| 0x2f | RET | pop FRM, pop return offset (0 ends the run) | 0x13fb90 |  |
| 0x30 | RETN | as RET, then STK += [STK] + 4 (drops the arguments) | 0x13fbf8 | yes |
| 0x31 | CALL addr | push return offset, jump | 0x13fc68 | yes |
| 0x32 | CALL.pri | push return offset, jump to PRI | 0x13fca8 |  |
| 0x33 | JUMP addr | jump | 0x13fce0 | yes |
| 0x34 | JREL o | relative jump | 0x13fd10 |  |
| 0x35 | JZER addr | jump if PRI == 0 | 0x13fd40 | yes |
| 0x36 | JNZ addr | jump if PRI != 0 | 0x13fd70 | yes |
| 0x37 | JEQ addr | jump if PRI == ALT | 0x13fda0 | yes |
| 0x38 | JNEQ addr | jump if PRI != ALT | 0x13fdd0 | yes |
| 0x39 | JLESS addr | jump if PRI below ALT, unsigned | 0x13fe00 |  |
| 0x3a | JLEQ addr | unsigned below or equal | 0x13fe38 |  |
| 0x3b | JGRTR addr | unsigned above | 0x13fe70 |  |
| 0x3c | JGEQ addr | unsigned above or equal | 0x13fea8 |  |
| 0x3d | JSLESS addr | jump if PRI less than ALT, signed | 0x13fee0 | yes |
| 0x3e | JSLEQ addr | signed less or equal | 0x13ff18 | yes |
| 0x3f | JSGRTR addr | signed greater | 0x13ff50 | yes |
| 0x40 | JSGEQ addr | signed greater or equal | 0x13ff88 | yes |
| 0x41 | SHL | PRI shifted left by ALT | 0x13ffc0 |  |
| 0x42 | SHR | PRI shifted right by ALT, logical | 0x13fff0 |  |
| 0x43 | SSHR | PRI shifted right by ALT, arithmetic | 0x140020 |  |
| 0x44 | SHL.C.pri n | PRI shifted left by n | 0x140050 |  |
| 0x45 | SHL.C.alt n | ALT shifted left by n | 0x140088 |  |
| 0x46 | SHR.C.pri n | PRI shifted right by n | 0x1400c0 |  |
| 0x47 | SHR.C.alt n | ALT shifted right by n | 0x1400f8 |  |
| 0x48 | SMUL | PRI = ALT * PRI | 0x140130 | yes |
| 0x49 | SDIV | PRI = PRI / ALT, ALT = remainder (floored, error 11 on zero) | 0x140160 |  |
| 0x4a | SDIV.alt | PRI = ALT / PRI, ALT = remainder (floored, error 11 on zero) | 0x1401b8 | yes |
| 0x4b | UMUL | multiply; the same signed multiply instruction as SMUL (0x48), the low 32 bits of the product | 0x140208 |  |
| 0x4c | UDIV | unsigned PRI / ALT | 0x140238 |  |
| 0x4d | UDIV.alt | unsigned ALT / PRI | 0x140278 |  |
| 0x4e | ADD | PRI = ALT + PRI | 0x1402c8 | yes |
| 0x4f | SUB | PRI = PRI - ALT | 0x1402f8 |  |
| 0x50 | SUB.alt | PRI = ALT - PRI | 0x140328 | yes |
| 0x51 | AND | PRI = PRI and ALT | 0x140358 |  |
| 0x52 | OR | PRI = PRI or ALT | 0x140388 |  |
| 0x53 | XOR | PRI = PRI xor ALT | 0x1403b8 |  |
| 0x54 | NOT | PRI = (PRI == 0) | 0x1403e8 | yes |
| 0x55 | NEG | PRI = -PRI | 0x140418 |  |
| 0x56 | INVERT | PRI = bitwise not PRI | 0x140448 |  |
| 0x57 | ADD.C v | PRI += v | 0x140478 | yes |
| 0x58 | SMUL.C v | PRI *= v | 0x1404b0 | yes |
| 0x59 | ZERO.pri | PRI = 0 | 0x1404e8 | yes |
| 0x5a | ZERO.alt | ALT = 0 | 0x140518 | yes |
| 0x5b | ZERO a | [a] = 0 | 0x140548 | yes |
| 0x5c | ZERO.S o | [FRM+o] = 0 | 0x140580 |  |
| 0x5d | SIGN.pri | not a full sign extension: when bit 7 of PRI is set, bits 8–31 are set; otherwise nothing changes, so the upper bits are never cleared | 0x1405b8 |  |
| 0x5e | SIGN.alt | same for ALT | 0x140600 |  |
| 0x5f | EQ | PRI = (PRI == ALT) | 0x140640 | yes |
| 0x60 | NEQ | PRI = (PRI != ALT) | 0x140670 |  |
| 0x61 | LESS | PRI = (PRI below ALT), unsigned | 0x1406a0 |  |
| 0x62 | LEQ | unsigned below or equal | 0x1406d0 |  |
| 0x63 | GRTR | unsigned above | 0x140700 |  |
| 0x64 | GEQ | unsigned above or equal | 0x140730 |  |
| 0x65 | SLESS | PRI = (PRI less than ALT), signed | 0x140760 | yes |
| 0x66 | SLEQ | signed less or equal | 0x140790 |  |
| 0x67 | SGRTR | PRI = (PRI greater than ALT), signed | 0x1407c0 | yes |
| 0x68 | SGEQ | signed greater or equal | 0x1407f0 |  |
| 0x69 | EQ.C.pri v | PRI = (PRI == v) | 0x140820 | yes |
| 0x6a | EQ.C.alt v | PRI = (ALT == v) | 0x140858 |  |
| 0x6b | INC.pri | PRI++ | 0x140890 |  |
| 0x6c | INC.alt | ALT++ | 0x1408c0 |  |
| 0x6d | INC a | [a]++ | 0x1408f0 | yes |
| 0x6e | INC.S o | [FRM+o]++ | 0x140930 |  |
| 0x6f | INC.I | [PRI]++ | 0x140970 |  |
| 0x70 | DEC.pri | PRI-- | 0x1409a8 |  |
| 0x71 | DEC.alt | ALT-- | 0x1409d8 |  |
| 0x72 | DEC a | [a]-- | 0x140a08 | yes |
| 0x73 | DEC.S o | [FRM+o]-- | 0x140a48 |  |
| 0x74 | DEC.I | [PRI]-- | 0x140a88 |  |
| 0x75 | MOVS n | copy n bytes from [PRI] to [ALT] (calls 0x3b5f0c) | 0x140ac0 |  |
| 0x76 | CMPS n | PRI = comparison of n bytes at [ALT] and [PRI] (calls 0x3b5e78) | 0x140b08 |  |
| 0x77 | FILL n | fill n bytes at [ALT] with PRI | 0x140b58 |  |
| 0x78 | HALT v | store PRI as the result, return v as the error code | 0x140bb8 |  |
| 0x79 | BOUNDS v | error 4 unless 0 <= PRI <= v | 0x140be0 | yes |
| 0x7a | SYSREQ.pri | call built-in number PRI | 0x140c28 |  |
| 0x7b | SYSREQ.C n | call built-in number n | 0x140c88 | yes |
| 0x7c | FILE | debug record, skipped | 0x140d00 |  |
| 0x7d | LINE l f | stores line and file numbers at machine +0x24 / +0x28 | 0x140d38 | yes |
| 0x7e | SYMBOL | debug record, skipped (stores words at +0x30..+0x38) | 0x140d78 |  |
| 0x7f | SRANGE a b | debug record (stores words at +0x30 / +0x34) | 0x140dc8 |  |
| 0x80 | JUMP.pri | jump to PRI | 0x140e08 |  |
| 0x81 | SWITCH addr | jump through the case table at addr | 0x140e30 |  |
| 0x82 | CASETBL | case table data (count, default, value/address pairs). It has an executable handler, which passes on to the next cell — the record count — as if it were an instruction: executing one crashes | 0x140eb8 |  |

The rows of ALIGN, UMUL, SIGN and CASETBL were corrected from `docs/spec/script-machine.md`
section 5, which executed every handler against a reference model; the earlier version
called UMUL "unsigned multiply", SIGN "sign-extend the low byte" and gave CASETBL no
handler behaviour.

## 2. How the game drives the machine

The functions in this section are outside the address range (most are in `gameplay`), but the
built-ins cannot be understood without them.

### 2.1 One machine per level

`level_loadScriptAndObjects` (0x217978) loads the level lump, looks up the entry `script.scr`
and passes its address to `script_setCurrent` (0x1ed650), which stores it in `g_scriptMachine`,
calls `scr_load` and then `scr_registerNatives` with the built-in table. A level without a
script sets the pointer to 0 and every later `script_runByName` returns -1. The loader then
runs the entry point `preStart`, loads the objects, and runs `start` (both skipped when the
byte at 0x4f8b58 is set; 81 scripts define `start`, 18 define `preStart`).

`script_runByName(name)` (0x1ed694) is the whole host interface:

```
if name == null or g_scriptMachine == null: return -1
index = scr_findEntry(g_scriptMachine, name)
if not found: return -1      // also stores render-frame counter + 20 at 0x4f8694, but only when the
                             // stamp already there has passed (compare at 0x1ed6f4); nothing else reads it
result = 0
scr_interpret(g_scriptMachine, &result, index, 0, null)     // error code ignored
return result
```

### 2.2 Who starts scripts

| Starter | Call site | Entry point comes from | Context |
|---|---|---|---|
| `level_loadScriptAndObjects` | 0x217acc, 0x217bac | fixed names `preStart`, `start` | level load |
| `script_runDeferred` | 0x1ed5f4 | deferred queue | run task, priority 125; also once from `mainloop_runSession` (0x322e6c) right after a level load |
| `script_runPostAction` | 0x1edafc | post-action buffer | called by `cut_runFrame` (0x199f6c), `help_task` (0x1dcf60, 0x1dd1f0), `game_loadLevel` (0x1e60b8), the dialog-end handler (0x22f7f0) |
| `script_callScript` | 0x143178 | script argument | nested in a running script |
| `Trigger_run` | 0x1ed160, 0x1ed188 | trigger +0x5c on entry; "not" + that name on exit | object run |
| `obj_runActionScripts` | 0x14ddec, 0x14de10 | `action` properties of a `TriggerParams` | object run |
| `MonsterTrigger_scan` | 0x1ed4a8 | `script` property, once per creature inside | object run (60-frame list) |
| `Creature_init` / `_onDeath` / `_revive` | 0x10a5ec, 0x10bf08, 0x10c0d0 | properties `initScript`, `deathScript`, `resurrectScript` | simulation |
| `Creature_updateActive` | 0x10c1b0, 0x10c1d8 | `followLostScript`, `followFoundScript` | simulation |
| `Creature_interact` (slot 14) | 0x116d2c | `dialogScript`; takes the menu mutex first | simulation (player used the NPC) |
| `Creature_trigger` (slot 3) | 0x11a648 | a property whose name the caller passes | simulation |
| `mission_grantMedal` | 0x1bdc10–0x1bdc38 | fixed names `firstBronze`, `firstSilver`, `firstGold` (only `firstSilver` exists, in 9 levels) | from the grant* built-ins |
| `JumpGate_run`, `FireBomb_run`, `Catapult_run` (slot 4) | 0x27cbc8, 0x261fb4, 0x24da4c | `script` property | object run; an armed jump gate runs its predicate on every run |
| `Catapult_takeDamage`, 0x255990 | 0x24e0e8, 0x255a88 | `deathScript` | simulation |
| `DoorSwing_interact`, `DoorSecret_interact` (slot 14) | 0x28aacc, 0x28b2b0 | `key` | simulation |
| `AutoObject_ctor`, 0x23d890 | 0x23a9b0, 0x23d8fc | `initScript`, `action<n>` | simulation |
| dialog system | 0x22f028, 0x22f4d4, 0x230eb8 | names stored in dialog data | dialog code (0x22ee84, 0x22f3d0, `dialog_showNode`); not classified further |
| **interact prompts** (slot 13) | `PushTrigger_prompt` 0x1ecb98, `AutoChest_interactPrompt` 0x23b6e8, `AutoProp_interactPrompt` 0x23d068, `SpiritAnchor_interactPrompt` 0x296ba0 (all `key`), `JumpGate_interactPrompt` 0x27d80c (`script`) | predicate deciding whether the object can be used | **both** `Player_run` and `Player_draw`, see P1 |
| **draw functions** (slot 5) | `NPC_draw` 0x29e5f4, `Gnome_draw` 0x26926c, `GnomeNavigator_draw` 0x26a07c, `Rondo_draw` 0x29f308 | `exclamation` property | **draw**, see P1 |
| **map drawing** | 0x1696c4 (in 0x168cac, called from `minimap_draw`) | per-marker script name | **draw**, see P1 |
| engine hooks | 0x154fd4, 0x1a90f0, 0x1c0314, 0x1c2948, 0x1c2960, 0x1dbb30 | fixed names starting with `*` (`*gotItemNotify`, `*arrowShootNotify`, `*exitInventoryNotify`, `*weaponEquipNotify`, `*bowEquipNotify`, `*inventoryOnNotify`) | item pick-up, `Player_run`, inventory, `hud_run`. No shipped script defines any of them |

Many property values are not hand-written entry points but snippets the level editor compiled
into automatically named entries: the first characters of the snippet plus a hash (`return9d74`,
`if6896`, `setvcccf`, `newWorldbcf6`). The scripts contain 108 `return…` and 161 `if…` entries
of this kind.

### 2.3 Two implicit arguments

Entry points take no arguments. Context is passed in two globals instead:

- **Selected object** `g_scriptSelectedObj` (0x4039f8): the object the script is run for. Set
  around the call by `Creature_init`, `Creature_onDeath`, `Creature_revive` (the creature),
  `Trigger_run` (the trigger, 0x1ed154, cleared at 0x1ed194), `MonsterTrigger_scan` (each
  creature in turn), `obj_runActionScripts`, 0x23d890 and 0x255990. It is 0 in deferred calls
  and post actions. The `select…` built-ins, `initScriptSetParams`, `newWorldParameter` and
  `script_setNextWorld` read it.
- **Active player** `g_scriptActivePlayer` (0x4d8ae4): a player index. Written by `Trigger_run`
  when a player enters (0x1ed15c: the lowest-numbered player inside), by `Player_interact`
  when a player uses something (0x1b2b70), by `Creature_interact` before a `dialogScript`
  (0x116d28), by `dialog_free` at level teardown (0x22fa34, sets 0), and by the built-ins
  `setBestActivePlayer` and `playGotItemSound`. One more writer exists outside play in a
  net game: `dialog_runTask` 0x22ff48 flips the value between 0 and 1 (store at 0x2301b8),
  on a path taken only when the game is not a net game (`docs/issues/claims-audit.md`
  row 5; `docs/issues/draw-sim-leaks.md` U6). It is not reset between scripts, so a deferred
  call or a death script sees the value left by whatever ran last. All of these writers are
  simulation code, so the value is the same on every machine (Inferred; see P7 for the one
  odd writer). One of them is not unconditional, though: the `Player_interact` write
  happens only when the object's prompt slot (slot 13) says it can be used, and the
  Savepoint's slot 13 reads this machine's card state — `Savepoint_interactPrompt` returns
  "nothing" while the local card is busy (0x28da6c), and then `Player_interact` neither
  sets the active player nor calls the interact on that machine
  (`docs/issues/sync-breakers.md` B9). Section 6 lists the readers.

### 2.4 Deferred calls

`addDeferedCall(name)` copies the name into the *back* half of a two-part buffer
(`g_scriptDeferNames`, 64 names of 0x50 bytes per half) and increments `g_scriptDeferQueued`;
a 65th name in one frame is dropped without notice (0x1ed52c).

`script_runDeferred` (0x1ed5a0) is a run task of priority 125 named "Script". Once per simulated
frame it runs every name in the *front* half in order, then makes the back half the front
(`g_scriptDeferCount = g_scriptDeferQueued`, queued = 0, flip the parity word 0x4f8690).

Consequences:

- A name queued before or during the Script task of frame N runs in frame N+1. A name queued
  later in frame N, by a task with a higher priority number such as the cutscene task (300)
  running a post action, runs in frame N+2.
- This is how scripts wait: an entry point does a little work, checks `gamePaused()`, counts in
  a global variable and defers itself again. The shipped scripts call `addDeferedCall` 278
  times in 61 levels.
- The queue is cleared by `script_clearDeferred` (0x1eda08) at level teardown, by
  `game_resetState` and when a save is loaded (0x222074). The post action of 2.5 is not:
  level teardown leaves the name in its buffer, and `game_loadLevel` runs a left-over one
  in the new level's script (0x1e60b8; FINDINGS E10, `docs/issues/arena-entry.md`).

### 2.5 Post action

`postAction(name)` stores one name in `g_scriptPostAction`. `script_runPostAction` (0x1edac0)
runs it once, with `g_scriptInPostAction` set, when the current cutscene ends, when a dialog
ends, from two places in `help_task`, or at the end of a level load. Scripts use it as "do this
when the cutscene I just started is over". Only one name is kept; a second `postAction`
replaces the first.

The two calls in `help_task` need more than that sentence gave them
(`docs/issues/arena-entry.md` E9): `help_task` is a draw task. The call at 0x1dcf60, for
the full-screen help box, is made only offline (test of `g_networkMode` at 0x1dcf58). The
call at 0x1dd1f0, made when a per-player notice box is closed, has no network test, so in
a net game it runs the pending post-action script in the draw pass of the machine that
closed the box, and only there (FINDINGS E9).

### 2.6 When scripts run within a frame

In a net game `tasks_run` (0x3226e4) is called from `net_frameLoop`, so everything below is
lockstep code unless marked.

1. Priority 10, `runObjects`: triggers, creature events, `Player_run` → `Player_interact` →
   interact prompts and interactions. Scripts started here run inline, in object order.
2. Priority 125, `script_runDeferred`: the deferred queue.
3. Priority 300, the cutscene task: the post action when a cutscene ends.
4. Game-message processing (before the tasks, in `net_frameLoop`): dialog start and end, and
   with them the post action and dialog scripts (Inferred: the two dialog functions involved,
   0x22ee84 and 0x22f6a8, are reached only through the pointer table at 0x540cc0).
5. **Draw phase** (not lockstep): NPC exclamation predicates, map-marker scripts, and the
   interact-prompt predicates through `Player_draw` (P1).

The Script task is not skipped while the game is paused: `tasks_run` calls
`tasks_call(1, -1)` (0x19e798) on every simulated tick and that function only filters draw
tasks. This is why the scripts test `gamePaused()` themselves (108 calls).

## 3. The built-ins

Conventions for the tables:

- **#** is the index in the global table 0x403370 (entry address = 0x403370 + 8 × #).
- **Arguments** are what the handler reads, in order: `s` a string, `i` an integer, `ref` the
  address of script cells, `i x8` eight integers. The count was checked against the byte
  count every shipped call pushes: they all agree, except one `getv` call with a second,
  ignored argument. For the 69 built-ins no script calls, the list comes from the handler
  alone.
- **Shared state written** is state that must match on all machines. "-" means none found.
- In the last column, **AP** = reads the active player, **NET** = behaves differently when
  `g_networkMode` is set, **LOCAL SLOT** = depends on which player this machine owns. "-" means
  nothing found by reading the handler and scanning its direct callees for the local-state
  markers listed in section 5.
- **Calls / levels**: how often the 120 shipped scripts call it. 69 built-ins are never called.
- Object offsets are in the object the name refers to; creature offsets apply to objects with
  flag 0x20.

`newWorld` and `newWorldAlways` share one handler, so there are 190 distinct handlers.

### Script control and pure helpers

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 0 | `callScript` | 0x143158 | s entry | Wraps `script_runByName` (0x1ed694): runs another entry point of the same machine, nested on the same stack, and returns its result (0 on a VM error, -1 if the name is unknown). | whatever the callee does | - | 357 / 63 |
| 104 | `addDeferedCall` | 0x144160 | s entry | Wraps `script_queueDeferred` (0x1ed52c): appends the name to the back buffer of the deferred queue; dropped silently when 64 names are already queued. | deferred queue 0x86b278, count 0x86da7c | - | 278 / 61 |
| 106 | `postAction` | 0x143ee4 | s entry | Wraps `script_setPostAction` (0x1eda9c): copies the name to the post-action buffer; it is run once by `script_runPostAction` (see 2.5). | post-action name 0x86fa80 | - | 105 / 45 |
| 1 | `print` | 0x143120 | s text | Converts the string and discards it (debug output compiled out). | - | - | 31 / 3 |
| 2 | `printVal` | 0x143150 | i value | Empty; returns 0. | - | - | 31 / 3 |
| 87 | `getRand` | 0x146570 | - | Advances the shared generator once and returns its upper 16 bits (0..65535). | `g_randSeed` 0x404464 | None by itself; a desync if the calling script is one that runs from draw code (see Per-machine state, P1). | 130 / 27 |
| 13 | `getScaledTime` | 0x14412c | i n | Returns (int)(n * 60 * (1/60)) computed in single floats: a frame count for a 60 Hz game. No state. | - | - | 26 / 16 |
| 161 | `sin1000` | 0x141fb0 | i angle16 | Wraps `math_sin16` (0x1666e0); returns sine * 1000. | - | - | 35 / 6 |
| 162 | `cos1000` | 0x141fe0 | i angle16 | Wraps `math_cos16` (0x166630); returns cosine * 1000. | - | - | 35 / 6 |
| 90 | `gamePaused` | 0x14699c | - | Returns 1 if `g_paused`, or the jump-gate travel state (0x500ae8, via 0x27dd68), or `g_cutsceneActive` is set. | - | All three are lockstep state (FINDINGS D17). | 108 / 40 |
| 178 | `demoRunning` | 0x141764 | - | Constant 0. | - | - | 7 / 5 |
| 143 | `networkMode` | 0x142214 | - | Returns `g_networkMode`. Scripts use it to show a HUD line instead of a modal help box in net games. | - | NET (returns the flag itself). | 3 / 2 |
| 92 | `levelLoading` | 0x146aa4 | - | Returns the word at 0x4f7198, set to 1 at the start of `game_loadLevel` (0x1e5630) and written again at 0x1e60d4. | - | - | 0 / 0 |
| 146 | `getLevelTimer` | 0x1421a8 | - | Returns the level frame counter 0x4f85cc divided by 60 (seconds). The counter is advanced at 0x1e3e3c. | - | - | 0 / 0 |

### Quest variables, profile variables and campaign progress

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 81 | `getv` | 0x143500 | s name | Wraps `vars_get` (0x1ed778): value (signed byte) of a quest variable. The name is lower-cased. A name that does not exist yet is appended to the table with value 0. | `g_questVars` 0x86da80 (only when the name is new) | None by itself; called from draw-time predicate scripts (P1), where the append happens on one machine only. | 790 / 64 |
| 83 | `setv` | 0x143540 | s name, i value | Wraps `vars_set` (0x1ed854): stores the value clamped to -128..127, creating the entry if needed. | `g_questVars` | - | 571 / 73 |
| 84 | `addv` | 0x143588 | s name, i delta | `vars_get` then `vars_set` of the sum; returns the unclamped sum. | `g_questVars` | - | 0 / 0 |
| 86 | `getpv` | 0x143480 | s name | Wraps `profile_getVar` (0x22289c): value of a profile variable (table 0x4f9030, same packed format as the quest variables). | profile table (appends unknown names) | The profile table belongs to the machine (it is what the config save on the memory card holds), so the result can differ between machines. No shipped script calls it. | 0 / 0 |
| 85 | `setpv` | 0x1434b4 | s name, i value | Wraps `profile_setVar` (0x22274c) with save = 1: stores the value and, if it changed, calls `memcard_requestConfigSave` (0x217bdc). | profile table 0x4f9030; memory-card state | Starts a memory-card write on each machine whose stored value differed. That makes `memcard_isBusy` differ between machines for a while, which runMedalSuccess / runMedalFail read (P2). | 27 / 9 |
| 147 | `getEvil` | 0x142044 | - | Wraps `game_getEvil` (0x1bf8d8): player 0 record +0x4c1a, bit `g_difficultyIdx`. | - | - | 63 / 19 |
| 148 | `setEvil` | 0x142058 | i on | If on != 0, wraps `game_setEvil` (0x1bf8f8) with that value; a zero argument does nothing. | every player record +0x4c1a | - | 2 / 1 |
| 149 | `getMadeDecision` | 0x142010 | - | Wraps `game_getMadeDecision` (0x1bf960). | - | - | 4 / 3 |
| 150 | `setMadeDecision` | 0x142024 | - | Wraps `game_setMadeDecision(1)` (0x1bf980). | every player record +0x4c1b | - | 2 / 1 |
| 151 | `grantMission` | 0x1420a4 | i mission | Wraps `mission_setComplete(g_difficultyIdx, mission, -1)` (0x1bf770). | mission bytes in all four player records | - | 33 / 32 |
| 152 | `getMissionComplete` | 0x142084 | i mission | Wraps `mission_isComplete(g_difficultyIdx, mission)` (0x1bf730). | - | - | 115 / 13 |
| 153 | `setMissionAvailable` | 0x1420d0 | i mission, i on | Wraps `mission_setAvailable(g_difficultyIdx, mission, on)` (0x1bf6d0). | mission bytes in the player records | - | 88 / 23 |
| 154 | `getMissionAvailable` | 0x1420fc | i mission | Wraps `mission_isAvailable(g_difficultyIdx, mission)` (0x1bf698), which reads record 0. | - | - | 129 / 3 |
| 155 | `grantGold` | 0x14211c | i mission | Wraps `mission_grantMedal(mission, 3)` (0x1bdb80): for every player whose medal byte is lower, sets the reward-player index 0x4f7149 and runs the entry points firstBronze / firstSilver / firstGold for each level gained, then stores the level. | medal bytes (record +0x4c0d + mission), 0x4f7149, plus what the reward scripts do | - | 9 / 9 |
| 156 | `grantSilver` | 0x142140 | i mission | Same with level 2. | as grantGold | - | 9 / 9 |
| 157 | `grantBronze` | 0x142164 | i mission | Same with level 1. | as grantGold | - | 9 / 9 |
| 158 | `getMedal` | 0x142188 | i mission | Wraps `mission_getMedal(mission, -1, 0)` (0x1bf838): returns the medal byte of **this machine's first local player** (`net_getLocalPlayerSlot(0)`). | - | LOCAL SLOT: the returned value differs between machines when players hold different medals (P3). | 9 / 9 |
| 64 | `addQuest` | 0x1433c8 | s title, s text | Wraps `quest_add` (0x1d386c): appends the pair to every player's quest list unless already present (max 8). Executed: not "every player unless" — the loop over the players **ends** at the first player whose list is full or already has the title (both tests leave the function, 0x1d38c4, 0x1d38e8), so later players get nothing (FINDINGS N2). | player records +0x41d0.., count +0x43d0 | - | 43 / 20 |
| 65 | `removeQuest` | 0x143448 | s title | Wraps `quest_remove` (0x1d3968). Executed: all matching entries are overwritten with a placeholder, but only the entries behind the last match move up and the count drops by one, so duplicate titles leave a placeholder entry behind (FINDINGS N3). | player quest lists | - | 30 / 19 |

### Level flow, cutscenes, dialog, saving

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 7 | `newWorld` | 0x143dd0 | s level | Unless running as a post action (0x4f8698) the call first passes `newWorld_netGate` (0x143d04). If allowed: `net_closeLocalMenus(0)` then `script_setNextWorld` (0x1472c4), which copies the level name to the next-world buffer 0x41b6d0 and takes the entrance orientation from the selected object's `orientation=` property (0xff if none). | next world 0x41b6d0 / 0x41b720; active player's cooldown record +0x4bca (net) | AP, NET: in a net game the gate refuses the change while the active player's 600-frame cooldown runs and more than one player is alive, and otherwise starts the cooldown (FINDINGS D20). The refusal text is shown only on the active player's machine. `net_closeLocalMenus` acts only in net games (sends menu-state message 2, closes local menus, ejects players from vehicles). | 163 / 71 |
| 8 | `newWorldAlways` | 0x143dd0 | s level | Table entry points at the same function as newWorld (0x143dd0), so despite the name it is gated too. An ungated variant exists at 0x143e30 but nothing references it. | as newWorld | as newWorld | 0 / 0 |
| 6 | `simpleNewWorld` | 0x143e70 | s level | Same gate; then `net_closeLocalMenus(0)`, copies the name to 0x41b6d0 and sets the orientation byte to 0xff without looking at the selected object. | as newWorld | AP, NET as newWorld | 4 / 1 |
| 9 | `newWorldPost` | 0x143cc4 | s level | Copies the name to 0x4fdcf0; the dialog-end handler (0x22f7c8) moves it to the next-world buffer when the current dialog closes. | 0x4fdcf0 | - | 5 / 3 |
| 107 | `newWorldParameter` | 0x1471fc | - | Reads the selected object's property list for `level=`; if found, `net_closeLocalMenus(0)` and `script_setNextWorld(value)`. No gate, no null check on the selected object. | next world | NET only through `net_closeLocalMenus`. | 0 / 0 |
| 121 | `setEntrance` | 0x142a94 | s name | Copies the name to 0x4f8468 (entrance used when players are placed in the next level). | 0x4f8468 | - | 76 / 30 |
| 105 | `cutScene` | 0x143f1c | s name | Builds "<level>.lmp" from the current level name 0x41b721 and "<name>.cut", finds it with `res_find` and calls `cut_start` (0x19b4dc). | cutscene state (cut_start) | `cut_start` closes local menus in a net game. | 58 / 43 |
| 15 | `startDialog` | 0x143824 | s name, i a, i b | (Contract with everything after the message: `docs/dialog.md`.) Preloads the level lump, clears 0x4fdce8, then calls `dialog_start` (0x22fa50). (Executed: the clear is inside `dialog_start`, after a `Camera_update` on the local camera that this row did not mention; the handler also formats "<name>.dbin" into a buffer nothing reads.) That function does not start the dialog itself: if the active player is local to this machine and no dialog is open, it sends game message 0 carrying the name, the active player, a, b, and **this machine's camera position and two camera angles**. The dialog opens when the message is processed. | none directly (the message handler does the work) | AP, LOCAL SLOT, CAMERA: exactly one machine sends; the camera values in the message are that machine's (P5). | 45 / 24 |
| 18 | `dialogRunning` | 0x143cb0 | - | Wraps `dialog_isOpen` (0x22fbc0): 0x8e2d60 != 0. | - | Dialog progress is driven by a local task (pad and voice stream, 0x22ff48); whether open/closed flips on the same frame everywhere is not established here. | 0 / 0 |
| 103 | `forceMutexRelease` | 0x1471dc | - | Wraps `menuMutex_release` (0x22fc38): clears 0x4fe53c, the lock taken when an NPC conversation starts. | 0x4fe53c | - | 0 / 0 |
| 16 | `changeSwoop` | 0x1438b0 | i mode | Stores the value at 0x4fdce4 (camera swoop selection used by the dialog system). | 0x4fdce4 | - | 43 / 3 |
| 17 | `startWithSwoopDone` | 0x1438c4 | - | Sets 0x4fdce8 = 1. | 0x4fdce8 | - | 3 / 2 |
| 70 | `leaveGame` | 0x146ab0 | i how | Sets the exit request 0x41b508 to 1 (how == 0) or 0x65. | 0x41b508 | - | 5 / 3 |
| 71 | `endGame` | 0x146ad4 | - | Wraps `memcard_requestEndGameSave(0, 1)` (0x217c38). | memory-card state, 0x4f8f38 | Memory card and local slot. | 0 / 0 |
| 79 | `exitToMainMenu` | 0x146d80 | - | Sets the exit request 0x41b508 to 1. | 0x41b508 | - | 0 / 0 |
| 76 | `saveGame` | 0x146c04 | - | Returns at once if any player's status field (record +0x4c1c, low 5 bits) is 2. Otherwise wraps `memcard_requestSave(net_getLocalPlayerSlot(0))` (0x2175b4). | memory-card state | LOCAL SLOT, NET: opens the save flow for this machine's own player; in a net game it also sends menu-state message 2. | 3 / 3 |
| 77 | `saveEndConfig` | 0x146c78 | - | End of campaign: calls `game_sendCharacterToLobby(-1)` (0x1eb5c8), clears 0x4d8a08 and 0x4039c0, sets 0x41b4f8, 0x4f85c5 and `g_paused`, in a net game calls `net_dropAllRemotes` (0x13def8), sets the completion bit for the difficulty in 0x4f8f38 and calls `memcard_requestConfigSave`. Executed: the bit is 0x08, 0x10, 0x20 or 0x40 for difficulty 1 to 4; difficulty 0 sets none. | `g_paused`, peer dropped flags, 0x4f8f38, memory-card state | NET: every machine marks all *other* peers as dropped, which ends lockstep. Everything after this call runs as a private game. | 3 / 3 |
| 78 | `saveDone` | 0x146d5c | - | Returns 1 when `memcard_getState()` (0x217550) is -1, i.e. no card operation is running. | - | MEMORY CARD: purely local hardware state returned to the script (P4). | 6 / 3 |
| 132 | `saveCheckPoint` | 0x142a40 | - | Debug print, then `save_game(0, 0, 1)` (0x218128). | save buffer | Runs in lockstep on every machine (names.tsv). | 16 / 15 |
| 133 | `loadCheckPoint` | 0x142a74 | - | Wraps `deathTask_schedule(0)` (0x1ebd48). | death task | - | 0 / 0 |
| 138 | `setSaveInhibit` | 0x1473b4 | i on | Stores the value at 0x50605c (read by the save daemon 0x218960 and by 0x1e7b80). | 0x50605c | - | 44 / 33 |
| 139 | `getSaveInhibit` | 0x1473c8 | - | Returns 0x50605c. | - | - | 0 / 0 |
| 172 | `setAlternateDeath` | 0x141790 | - | Sets 0x4f712c = 1 (read by `deathTask` at 0x1e7648). | 0x4f712c | - | 9 / 9 |
| 137 | `preloadResource` | 0x14222c | s lump | Wraps `lump_load` (0x173558): blocking disc read if the lump is not in memory. | resource cache | - | 13 / 13 |
| 72 | `clearRecall` | 0x146af8 | - | Copies a five-byte constant (the word None, 0x5313b8) over the field at +0x24 of every player record (Inferred from the name: the stored recall destination). | record +0x24 | - | 0 / 0 |
| 112 | `playersLoaded` | 0x147278 | - | Returns 1 if any of the first `g_numPlayers` records has an object pointer. | - | - | 0 / 0 |
| 91 | `pauseGameControl` | 0x1469f0 | i frames | Sets the input lock-out 0x41b4fc to the value and 0x41b500 to 1. | 0x41b4fc, 0x41b500 | NET: `tasks_run` zeroes 0x41b4fc at the start of every call in a net game (0x322710), so the lock-out does not survive to the next frame there (Inferred). | 0 / 0 |

### Menus, HUD and medal results

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 10 | `activateMissionMenu` | 0x143fa8 | - | Does nothing if a dialog is open or the recall flag 0x41b51d is set. Otherwise `missionMenu_open` (0x231520) for the active player (offline) or for `net_firstActiveSlot()` (net). That function registers a run task and a draw task. | mission-menu state, task list | AP offline only. NET: slot chosen by peer state, not by the active player. Depends on `dialog_isOpen` (see dialogRunning). | 4 / 2 |
| 11 | `activateStore` | 0x144010 | i store | (Some shipped scripts call it declaring 4 argument bytes without pushing the argument — `HUB.scr` code offsets 0xfbc–0xfd8; the handler then reads the caller's saved FRM as its argument, and the run leaves the machine's saved stack pointer 4 too high: `docs/spec/script-machine.md` section 9.) Stores the store index (if < 21) at 0x4f7150. If a dialog is open it only sets the pending flag 0x4fdd30 (the dialog-end handler opens the store later). Otherwise: offline, `shop_openOrStock(activePlayer, 0, 1)`; net, for every living player **that is local to this machine**: `net_closeLocalMenus(0)` then `shop_openOrStock(slot, 0, 1)`. | 0x4f7150, 0x4fdd30; shop UI state; in a net game vehicle occupancy through `net_closeLocalMenus` | AP offline. NET + LOCAL SLOT: the shop opens only on machines with a living local player; `net_closeLocalMenus(0)` (which ejects every living player from a vehicle) is called only on those machines (P6). | 45 / 4 |
| 12 | `storeRunning` | 0x1440f8 | - | Returns `g_shopOpen` (0x41b50c). | - | MENU: per-machine UI state. No shipped script calls it. | 0 / 0 |
| 62 | `setInfo` | 0x14318c | s textKey | `hud_showMessage(text_lookup(key), 180, -1, 0)` (0x1d92a0). | HUD message buffer (cosmetic) | Suppressed on a machine whose local menu is open. | 95 / 25 |
| 63 | `addHelpMessage` | 0x1431d8 | s titleKey, s bodyKey | `hud_showHelpMessage(-1, title, body)` (0x1d9830). | help box state, `g_helpMessageOpen` | NET + LOCAL SLOT: in a net game the box appears only if this machine has a living local player; it then sends menu-state message 2 for that slot. | 65 / 47 |
| 164 | `addHelpMessageF` | 0x143270 | s key1, i v1, s key2, i v2 | Formats each text with its integer (as a float argument) into two static buffers (0x5d3048, 0x5d3088) and shows them with `hud_showHelpMessage`. | as addHelpMessage | as addHelpMessage | 7 / 3 |
| 163 | `helpMessageActive` | 0x1433bc | - | Returns `g_helpMessageOpen` (0x41b928), sign-extended from its byte (`lb`, 0x1433c4; executed). | - | MENU: per-machine in a net game. No shipped script calls it. | 0 / 0 |
| 127 | `showCompass` | 0x1427b4 | s object, s textKey | `hud_setCompassTarget(position of the object, text)` (0x1df668). No null check on the object. | HUD (cosmetic) | Ignored on a machine where a menu is open. | 3 / 3 |
| 128 | `showBust` | 0x142864 | s texture, s textKey, i a, i b | `hud_setBust(texture, text, a, b)` (0x1dfaa0). | HUD (cosmetic) | Same local gate as showCompass. | 31 / 17 |
| 122 | `hudResetFadeScreen` | 0x14277c | i on | `hud_setFade` (0x1df5d0): fade level 0 or 0x80. | `g_hudFade` 0x4f66ac | - | 0 / 0 |
| 123 | `hudFadeScreen` | 0x14279c | i delta | `hud_stepFade` (0x1df5ec): adds to the fade level, draws the overlay, returns the new level. | `g_hudFade` | Draws from a run task. | 0 / 0 |
| 165 | `revealMap` | 0x141e78 | - | Wraps 0x16a760: marks every automap cell as seen. | automap table 0x4044f1 | - | 3 / 3 |
| 166 | `showOnMap` | 0x141e98 | s name, i on | For up to 99 objects of that name that are creatures: sets or clears bit 43 of the creature flag word (+0xa8). | creature +0xa8 | - | 24 / 4 |
| 170 | `runMedalSuccess` | 0x1417a4 | i mission, i oldMedal, s titleKey, s key1, s key2, s key3 | Medal-mission result screen, meant to be called every frame. Sets 0x4f7114 = 2. Draws the result box and the reward lines directly. Then tests the medal player's pad word (+0xc of `g_pads[0x4f7148]`): confirm restarts the level (next world = current level), cancel calls `game_openMissionMenu` (0x1eb4f0). Returns 1 when either was pressed, else 0. Offline it also sets `g_paused`. Executed, three additions: the reward lines are drawn in the order 3, 2, 1 under the title; every shown text is drawn twice (a measuring pass with a clip window of 100..100 first); and offline the function returns 0 while `memcard_isBusy()` as well. | 0x4f7114, `g_paused` (offline), next world, mission menu | NET, LOCAL SLOT, MEMORY CARD: see P2. On the medal player's machine it returns 0 while the memory card is busy and until the "ready" message 12 has come back; on other machines it waits for that message. Reward lines are chosen from the local player's medal byte. | 30 / 9 |
| 171 | `runMedalFail` | 0x141c00 | s textKey | Same flow as runMedalSuccess with the failure box. | as runMedalSuccess | as runMedalSuccess | 10 / 9 |
| 117 | `setupPlayerSel` | 0x142bb8 | - | Empty; returns 0. | - | - | 0 / 0 |
| 118 | `startPlayerSel` | 0x142bc0 | - | Empty; returns 0. | - | - | 0 / 0 |
| 119 | `playerSelRunning` | 0x142bc8 | - | Wraps `playerSel_isRunning` (0x2248e8): returns 0x4fbbdc. | - | Menu state; not classified. No shipped script calls it. | 0 / 0 |

### Players

Player records are `g_players[4]` (0x4d8af0, 0x4c30 bytes each). "All players" means the first `g_numPlayers` records.

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 82 | `getNumPlayers` | 0x143534 | - | Returns `g_numPlayers`. | - | - | 33 / 15 |
| 141 | `countPlayersAlive` | 0x142220 | - | Returns `g_alivePlayerCount` (0x4f8420). | - | - | 11 / 10 |
| 99 | `checkPlayerAlive` | 0x1470ac | i which | which != 0: returns whether the countdown 0x4f7194 is positive (a 16-bit value, read and written as such; executed). which == 0: `game_countPlayersWithHp()` (0x1ebec8). | - | - | 0 / 0 |
| 100 | `setBestActivePlayer` | 0x1470e0 | - | Sets the active player to 0, or to 1 when player 0 has no object or is dead and there are exactly two players. Returns it. | `g_scriptActivePlayer` | AP (writes it). Two-player logic. | 0 / 0 |
| 88 | `activePlayerIsDwarf` | 0x1465a0 | - | Returns whether the active player's record +0x54 is 0. | - | AP | 0 / 0 |
| 89 | `activePlayerIsElf` | 0x1465c4 | - | Constant 0. | - | - | 0 / 0 |
| 188 | `isClericOrWizard` | 0x1465cc | i player | Returns 1 if record +0x50 (class) is 1 or 4. Accepts player < 4 and <= `g_numPlayers`. | - | - | 1 / 1 |
| 129 | `getMaxPlayerHP` | 0x1428fc | i player1 | Player number is 1-based. Returns maximum hit points (record +0xb0) or -1. | - | - | 2 / 2 |
| 69 | `healPlayer` | 0x1468ac | - | Plays a cast sound on player 0's object and sets hit points to maximum for every player with hit points above 0. | record +0xac | Audio only. | 0 / 0 |
| 184 | `giveFullHealth` | 0x146950 | - | Sets hit points to maximum for all players, dead or not. | record +0xac | - | 1 / 1 |
| 126 | `zeroPlayerMana` | 0x142450 | - | Mana (record +0xc0) = 0 for all players. | record +0xc0 | - | 2 / 2 |
| 189 | `refillPlayerMana` | 0x142494 | - | Mana = maximum (+0xc4) for all players. | record +0xc0 | - | 2 / 2 |
| 125 | `hitPlayers` | 0x1424dc | s object, i radius, i damage, i push | For every living player within radius of the object: virtual slot 2 (take damage) with the amount and no attacker, then sets the push speed (+0x2e8) and push direction (+0x2e0, angle from the object to the player). No null check on the object. | player objects | - | 11 / 3 |
| 124 | `closestPlayerDist` | 0x14268c | s object | Distance from the object to the nearest living player, 100000 if none. No null check. | - | - | 2 / 1 |
| 56 | `givePlayerExp` | 0x146278 | i amount | `player_giveExp(slot, amount)` (0x1d3150) for all players. | records (experience, level, points, hp, mana) | Level-up sound and HUD line only on the owner's machine. | 0 / 0 |
| 57 | `givePlayerGold` | 0x1462dc | i amount | Adds amount / `g_numPlayers` to every player's gold (record +0xe4), capped at 99,999,999. | record +0xe4 | - | 4 / 2 |
| 58 | `takePlayerGold` | 0x1463ec | i amount | Subtracts amount / `g_numPlayers` from each, not below 0. | record +0xe4 | - | 1 / 1 |
| 59 | `checkPlayerGold` | 0x14644c | - | Sum of all players' gold. | - | - | 4 / 1 |
| 60 | `checkPlayerMinGold` | 0x146494 | - | Smallest gold amount among the players. | - | - | 0 / 0 |
| 183 | `playerAdjustStat` | 0x146348 | i player, i stat, i count | stat must be 4..8. player == -1: `inventory_onStatPoint(0x4f7149, stat)` count times, applied directly (0x4f7149 is the reward player set by `mission_grantMedal`). Any other player: `invmsg_sendStatPoint(player, stat)` count times, i.e. it **sends inventory message 6** instead of applying the change. | record +0x78..+0x84 (stats), +0xe8 (skill points) for player -1 | With an explicit player every machine that runs the script sends its own message (P8). All shipped calls pass -1. | 27 / 9 |
| 185 | `setPlayerFlag` | 0x1416d4 | i player, i bit, i on | Wraps `player_setFlag` (0x1be398): bit of record +0x4c28; player -1 means all. Executed: the bit number is taken mod 32 and the flag is one byte, so bits 8..31 change nothing. | record +0x4c28 | - | 12 / 8 |
| 186 | `getPlayerFlag` | 0x1416fc | i player, i bit | Wraps `player_getFlag` (0x1bfb80). | - | - | 7 / 4 |
| 182 | `piercePlayerEar` | 0x145610 | i player | Sets record +0x4c26 = 1 for that player (0..3) or for all (-1). | record +0x4c26 | - | 1 / 1 |
| 187 | `clearAllSkills` | 0x1458e0 | - | For the medal player (0x4f7148): clears +0x128 (8 bytes), 48 bytes from +0xef, 48 pairs of 16-bit slots from +0x4b08 (set to -1), skill points +0xe8, three fields at +0x4a80.., and the type and count of the 15 ability records (+0x4460 + n*0x68). Executed: of the three, +0x4a80 (word) and +0x4a84 (byte) are cleared and the byte +0x4a85 is **set to 1**, not cleared (0x145950–0x145960). | that player's record | Acts on 0x4f7148, which the mission menu writes (0x232040). | 2 / 2 |
| 180 | `savePlayer` | 0x141724 | - | Wraps `soloRun_savePlayerRecord` (0x1ec720): copies the medal player's whole record to the buffer from `save_playerCopy` and sets 0x4f85c0. | record copy, 0x4f85c0 | Acts on 0x4f7148. | 36 / 9 |
| 181 | `restorePlayer` | 0x141744 | - | Wraps `soloRun_restorePlayerRecord` (0x1eb6f8): copies it back, keeping medals, a few live fields and the object pointer; sets 0x4f7194 = 240 (a 16-bit store; executed) and rebuilds the alive list. | the medal player's record, 0x4f7194, alive list | Acts on 0x4f7148. | 36 / 9 |
| 98 | `hidePlayers` | 0x147098 | i on | Stores the byte at 0x4f83f8 (read only by `Player_draw`, 0x1a4900). | 0x4f83f8 (cosmetic) | - | 0 / 0 |
| 101 | `decayPlayerLights` | 0x147130 | i target1, i target2, i step | Adds step/100 to the float 0x4f83f4 and clamps at the target (target2 when exactly two players are alive, else target1), returning 1 when the target is reached. `Player_run` reads the float (0x1a5298). | 0x4f83f4 | - | 0 / 0 |
| 66 | `hornOmen` | 0x146628 | - | For every player with an object: allocates a 0x20-byte spell effect (`SpellHornOmenEffect_ctor` 0x2fc574, skill pointer 0x41b1e4) and links it with `creature_addSpell`. Executed: `creature_addSpell` is also called when the allocation failed, with a null spell. | spell lists; `g_randSeed` (the constructor draws) | - | 0 / 0 |
| 67 | `planarSteel` | 0x1466d4 | - | Sets hit points to maximum for living players, then gives every player with an object a 0x6c-byte `SpellPlanarSteelEffect`. Executed: as in `hornOmen`, `creature_addSpell` is called with a null spell when the allocation failed. | record +0xac, spell lists, `g_randSeed` | - | 0 / 0 |
| 144 | `getManaUsed` | 0x1421fc | - | Returns the 16-bit counter 0x4f85c8 (mana potions used, counted in `Player_usePotion`), sign-extended (`lh`, 0x142204): a count of 0x8000 or more reads negative (executed). | - | - | 0 / 0 |
| 145 | `getHealthUsed` | 0x142208 | - | Returns the 16-bit counter 0x4f85ca (health potions used), sign-extended likewise (0x142210; executed). | - | - | 1 / 1 |
| 61 | `playGotItemSound` | 0x1464e8 | - | Clamps the active player to 0..1 **and writes it back**, then, with two or more players, switches to the other of 0/1 if that player has no hit points, and calls `player_voice(slot, 9)` (0x1b7ba8). Executed: the stored active player is clamped as described, but the slot handed to `player_voice` is the **unclamped** value (2 or 3 stays), and the hit-point test indexes the records with the unclamped value too; only when that test fires is the other of 0/1 used (FINDINGS N8). | `g_scriptActivePlayer` | AP (reads and overwrites). `player_voice` returns at once unless the slot is local and reads audio status. In a 3 or 4 player game an active player of 2 or 3 becomes 1 for every later built-in (P7). | 3 / 3 |
| 169 | `explodePotionsOnly` | 0x1433a8 | - | Sets 0x4f7128 = 1 (read in the player code at 0x1a6e50, 0x1a7a5c). | 0x4f7128 | - | 1 / 1 |

### Items

The bodies behind these rows (the bag scans, weight, carried load, load limit, the give and
drop paths, `clearAllSkills` and the mission bytes) are executed in `docs/script-items.md`.

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 50 | `playerHasItem` | 0x145590 | s item | Sum over all players of `inventory_countItemByName(item, slot)` (0x1c5880). | - | - | 61 / 20 |
| 51 | `onePlayerHasItem` | 0x145690 | i player, s item | Count for one player; 0 if the player has no object or is dead. | - | - | 36 / 32 |
| 140 | `countQuestItems` | 0x145720 | s item | Count in player 0's bags only. | - | - | 61 / 13 |
| 52 | `removePlayerItem` | 0x14598c | i player, s text | `inventory_findItemBySubstring` (0x1c5a70: last item whose name occurs inside the text) then `inventory_removeItem` (0x1c1cb0). player -1 means every player. | bags, equipped pointers | `inventory_removeItem` refreshes the menu on the owner's machine when its menu is open. | 147 / 34 |
| 179 | `removeAllItems` | 0x145758 | - | Empties all three bags of the medal player (0x4f7148). Executed: "empties" is, per bag, as many `inventory_removeItem(slot, 0, bag, 0)` calls as the bag's count at the start, each made only if the bag's first entry is then non-zero. | bags | Acts on 0x4f7148. | 1 / 1 |
| 190 | `removeAllWeapons` | 0x145828 | - | Empties bag 0 of the medal player (by the same loop as `removeAllItems`; executed) and clears three equipped pointers (+0x4434..). | bags, equipped pointers | Acts on 0x4f7148. | 1 / 1 |
| 53 | `givePlayerItem` | 0x145a88 | s descriptor, i equip, i usePresets (the parser's preset switch; the variant is always −1, `docs/script-items.md` 2.4) | (Some shipped scripts declare 12 argument bytes and push two cells — `INNOVAT1.scr` 0x7e0–0x80c; same defect as `activateStore`, `docs/spec/script-machine.md` section 9.) For every player (only the medal player when medal mode 0x4f713c is set): builds the item with `item_parseDescriptor` (0x1069b8); if it fits the weight limit (or weighs nothing) adds it with `inventory_giveItem` (0x1c1868), recomputes load and optionally equips it (`inventory_equipItem` 0x1c27c0); otherwise creates a ground item (0x190-byte object, `ItemProp_ctor2` 0x1590ec) at the player, or at the first living player if this one has no object. | bags, equipment, world objects, `g_randSeed` (item variant, object constructor) | NET: `inventory_giveItem` skips the offline-only recall tutorial (which sets a quest variable) in a net game. Equip sounds only for the local slot; equip runs the `*weaponEquipNotify` / `*bowEquipNotify` hooks. | 10 / 6 |
| 54 | `giveOnePlayerItem` | 0x145d20 | i player, s descriptor, i equip, i usePresets | Same for one living player (strict weight test). | as givePlayerItem | as givePlayerItem | 2 / 1 |
| 55 | `givePlayerRandom` | 0x145f18 | - | For every player: draws from `g_randSeed`, in the level whose name contains "orccave1" gives a fixed sword chosen by `g_difficultyIdx`, then generates a random item (`item_generateWithAffixes` 0x104ca4, up to 10 tries) and gives or drops it. | bags, world objects, `g_randSeed` | No shipped script calls it. | 0 / 0 |
| 173 | `dropItem` | 0x1477ac | s object, s descriptor | `loot_spawnNamedItem(position of the object, descriptor)` (0x100ba0). | world objects, `g_randSeed` | - | 6 / 6 |
| 174 | `selectDropItem` | 0x147860 | s descriptor | Same at the selected object's position (nothing if there is none). | as dropItem | - | 9 / 9 |

### Creatures

"Creatures named X" means the result of `world_findObjectsByName` (0x14bf58) filtered by object flag 0x20; the list holds at most 511 objects unless noted.

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 19 | `increaseEnemyRank` | 0x144200 | s name | Sets bit 44 of the creature flag word (+0xa8). | creature +0xa8 | - | 15 / 3 |
| 20 | `charmMonster` | 0x14429c | s name | `Creature_setCharm(creature, -1, 0)` (0x1189f0): permanent charm, team 0, target dropped. | creature +0x310, +0x312, +0x234 | - | 20 / 4 |
| 21 | `rootMonster` | 0x14433c | s name | Unless the AI state (+0x232) is 0x14: sets +0x314 = -1 and calls virtual slot 27 (set AI state) with 0. | creature +0x314, AI state | - | 16 / 7 |
| 22 | `unRootMonster` | 0x144408 | s name | Sets +0x314 = 0. | creature +0x314 | - | 8 / 3 |
| 24 | `setMonsterVal` | 0x144550 | s name, i which, i value | `script_applyMonsterVal` (0x144494): which 1, 2, 3 store the 16-bit value at +0x3ac, +0x3ae, +0x3b0; 4 calls virtual slot 34 with the value; 5 stores at +0x3c4. | creature fields | - | 114 / 16 |
| 23 | `selectSetMonsterVal` | 0x144514 | i which, i value | Same on the selected object (0x4039f8). No null check. | creature fields | - | 9 / 3 |
| 26 | `setCFlag` | 0x144714 | s name, i bit, i on | `script_applyCFlag` (0x1445fc): only bits 0 and 26 of the creature flag word can be changed. Bit 0 also calls `creature_startBossMusic` (0x1192b0), and clearing it while bit 31 is set clears bit 31 and the two words at 0x41b6a0 / 0x41b6a4. | creature +0xa8, 0x41b6a0, 0x41b6a4, music stream | - | 18 / 14 |
| 25 | `selectSetCFlag` | 0x1446d0 | i bit, i on | Same on the selected object. | as setCFlag | - | 0 / 0 |
| 28 | `setOFlag` | 0x144834 | s name, i which, i on | `script_applyOFlag` (0x1447c4): only which == 14 does anything: sets or clears object flag 0x4000. Applies to any object, not only creatures. | object +0xc | - | 0 / 0 |
| 27 | `selectSetOFlag` | 0x1447fc | i which, i on | Same on the selected object. | object +0xc | - | 0 / 0 |
| 29 | `setWeaponType` | 0x1448e4 | s name, i type | Calls virtual slot 8 of the object at creature +0x50 with (0, type as a byte). | creature appearance / weapon | - | 10 / 5 |
| 30 | `setMonsterRange` | 0x1449b4 | s name, i range | If range > 0: virtual slot 34 with the 16-bit value (same call as setMonsterVal which = 4). | creature | - | 0 / 0 |
| 31 | `killMonster` | 0x144a84 | s name | For creatures not already dead: object flags gain 0x2009, hit points (+0x228) = 0, virtual slot 27 with 0x14. | creature flags, hp, AI state | - | 15 / 5 |
| 32 | `deleteMonster` | 0x144b44 | s name | Virtual slot 1 (destructor) with 3: immediate delete. | object list | - | 33 / 8 |
| 33 | `hideMonster` | 0x144c00 | s name | Any object: `obj_moveOffGrid` (0x14ef48), object flag 0x8000 (not run); creatures also get bit 3 of +0x231. | object flags, grid link | - | 373 / 48 |
| 34 | `showMonster` | 0x144db8 | s name | Reverse of hideMonster: `obj_updateGridCell` (0x14f028), clears 0x8000 and the +0x231 bit. | object flags, grid link | - | 52 / 23 |
| 35 | `moveMonster` | 0x144cb8 | s name, s target | Copies position and facing of the target object to every object named name and relinks each into the grid. | object position, grid link | - | 3 / 2 |
| 36 | `followPlayer` | 0x144e78 | s name | Sets bit 23 of +0xa8 and applies the same charm call as charmMonster. | creature | - | 0 / 0 |
| 37 | `stopFollowingPlayer` | 0x144f2c | s name | Clears bit 23. | creature +0xa8 | - | 0 / 0 |
| 38 | `followPath` | 0x144fc8 | s name | If bit 27 is clear: sets it, stores 44000 at +0x3c4 and moves the creature to the every-frame run list (`obj_runEveryFrame` 0x14f248). | creature, run lists | - | 28 / 8 |
| 39 | `selectFollowPath` | 0x145090 | - | Same on the selected object. | creature, run lists | - | 3 / 3 |
| 40 | `stopFollowingPath` | 0x1450ec | s name | If bit 27 is set: stores 1150 at +0x3c4, clears the bit, copies the current position to +0x3b4 and, unless the AI state is 0x14, calls virtual slot 27 with 0. | creature | - | 45 / 1 |
| 41 | `selectStopPath` | 0x1451f0 | - | Same on the selected object. | creature | - | 11 / 4 |
| 42 | `friendly` | 0x145294 | s name | Sets object flag 0x1000000 and bit 26 of +0xa8. | creature flags | - | 13 / 4 |
| 43 | `unFriendly` | 0x145338 | s name | Clears both. | creature flags | - | 6 / 1 |
| 80 | `reapEnemies` | 0x1453e4 | - | Collects up to 511 objects in a box covering the whole map and destroys (virtual slot 1 with 3) every dead creature that is not a player. Three further type tests can never match (FINDINGS D11). | object list | Uses `world_collectObjectsInBox`, which skips whatever `g_excludeMask` names. | 1 / 1 |
| 102 | `checkMonstersLeft` | 0x1441c0 | - | `world_forEachGridObject` (0x14a610) with the callback at 0x144198; returns 1 if at least one living non-player creature exists anywhere. | scratch byte 0x5d32c4 | The walk skips objects matching `g_excludeMask`. | 0 / 0 |
| 130 | `getHitPoints` | 0x142944 | s name | Hit points (integer part of +0x228) of the first creature with that name, 0 if none. | - | - | 25 / 2 |
| 131 | `setHitPoints` | 0x1429e0 | s name, i value | Sets +0x228 of the first object with that name if it is a creature. No null check. | creature +0x228 | - | 0 / 0 |
| 159 | `generateMonster` | 0x1473d4 | s generator, s className | Interns the class name in a table of 24-byte names (0x5d32c8, count 0x4f8409; executed: the call-out is handed a pointer into that table, the count byte is raised before the copy, and neither the count nor the name length has a limit), then for each object named generator that is a `ScriptGenerator`: `ScriptGenerator_spawn` (0x265fc4) creates an object of that class at the generator. | world objects, `g_randSeed` (constructors), name table | - | 136 / 11 |
| 160 | `monstersInTrigger` | 0x147570 | s name | Sum of `MonsterTrigger_count` (0x1ed4e4) over objects of that name of class `MonsterTrigger`: living non-player creatures inside the trigger box. | trigger +0x50 | - | 10 / 3 |
| 167 | `initScriptSetParams` | 0x147640 | i hp, i b, i c, i d, i e | `Creature_scaleStats` (0x1185d8) on the selected object, each value divided by 100: hit points and maximum by the first, +0xe4 by the second, +0xd0 and +0xd2 by the third, +0xd4 by the fourth, +0xd8 by the fifth. | creature stats | - | 13 / 6 |
| 168 | `setCreatureParams` | 0x1476c0 | s name, i hp, i b, i c, i d, i e | Same for every creature of that name. | creature stats | - | 56 / 13 |
| 47 | `startNPCAnim` | 0x1438d8 | s name, s lump, s anim, i mode | For each creature: mode -1 resets the animation state at +0x114 and starts the animation looping; otherwise blends to it (0x16cfe0) with the given mode. | creature animation state | - | 0 / 0 |
| 48 | `NPCAnimAtEnd` | 0x143a4c | s name | Bit 7 of the animation status word (+0x11a) of the first object with that name. No null check. | - | - | 0 / 0 |
| 142 | `countLiveObjects` | 0x146a10 | s name | Number of objects of that name (max 127) that are not dead creatures. | - | - | 0 / 0 |

### Other objects, effects and camera

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 134 | `trigger` | 0x142264 | s name, i arg | Calls virtual slot 3 with arg on up to 99 objects of that name (for `TriggerParams` this enables or disables the linked trigger; for creatures it is `Creature_trigger` 0x11a5f0). | depends on the class | - | 29 / 17 |
| 135 | `autoPropSetState` | 0x142320 | s name, i state | For objects with flag 0x10000000 (auto props): virtual slot 18 with the state. | prop state | - | 62 / 13 |
| 136 | `autoPropGetState` | 0x1423e0 | s name | State word (+0x178) of the first object of that name if it is an auto prop. No null check. | - | - | 0 / 0 |
| 44 | `startPropAnim` | 0x143a8c | s name, s anim, i mode | Like startNPCAnim for the animation state at +0x54 of one object; the lump name comes from the object's `lump` property. | prop animation state | - | 0 / 0 |
| 45 | `stopPropAnim` | 0x143bb8 | s name | Clears the byte at +0x58 of the object. | prop animation state | - | 0 / 0 |
| 46 | `propAnimAtEnd` | 0x143bf4 | s name | Bit 7 of the status word at +0x5a. | - | - | 0 / 0 |
| 97 | `deleteObjects` | 0x146ff4 | s name | Destroys (virtual slot 1 with 3) up to 24 objects of that name. | object list | - | 0 / 0 |
| 95 | `setNoCollide` | 0x146f58 | s name, i on | Sets or clears object flag bit 0. No null check. | object +0xc | - | 0 / 0 |
| 120 | `objInPlayerTrig` | 0x142ad4 | s name | Returns 1 if the object lies inside any `Trigger` (class lookup, max 49) that currently has a player inside (+0x68 != -1), using the trigger's virtual slot 17. | - | The class walk skips objects matching `g_excludeMask`. | 0 / 0 |
| 175 | `findDistance` | 0x1478c8 | s a, s b | Horizontal distance between two named objects, 0 if either is missing. | - | - | 4 / 4 |
| 176 | `setContainerProps` | 0x14799c | s name, i which, i value | For objects of class `AutoContainer`, when which == 1: sets bit 3 of +0x124 if value is 0, clears it otherwise. | container +0x124 | - | 6 / 3 |
| 5 | `lightEffect` | 0x143720 | ref pos[3], i unused, i x8 | Reads three cells from script memory as a position, allocates 0xbc bytes and runs `LightEffect_ctor` (0x201bd8) with eight further values as floats. Executed: the argument list is wrong in two places — the second argument **is** used (× 0.01, passed on the stack), and ten values follow it, not eight (the last two on the stack, with a constant 1.0): twelve arguments in all. | world objects, `g_randSeed` (constructor) | - | 0 / 0 |
| 49 | `addExpandingPool` | 0x143c34 | s object, i unused, i size | `decal_add(size, position of the object, 0, 10, 2)` (0x19f110). | decal table | Whether a decal is made depends on a local detail option (engine area note on 0x19f110); the function also reads the camera position (0x19faa8). | 0 / 0 |
| 68 | `particleMorph` | 0x1467ac | s from, s to | If the first object of each name is a creature: allocates 0x5c bytes and runs `ParticleMorphEffect_ctor` (0x160a88). | world objects, `g_randSeed` | - | 0 / 0 |
| 93 | `setParticle` | 0x146d94 | i slot, i x14 | Passes 14 values to 0x18f118 for one of the three script particle definitions (pointers at 0x403360: 0x5d3188, 0x5d31d8, 0x5d3228). | particle definition | - | 14 / 13 |
| 94 | `addParticleOnObject` | 0x146e20 | i slot, s object, i dx, i dy, i dz, i vx, i vy, i vz | `particle_spawn` (0x18f3f8) with the slot's definition (slot -1 uses slot 0) at the object position plus the offset, velocity = v / 1000. No null check. | particle pool (cosmetic) | - | 54 / 13 |
| 96 | `shakeCamera` | 0x146fc0 | i amount | If 0x4f7114 is 0: `camera_shake(amount, 0)` (0x1ebae0). | camera shake level 0x4f8488, pad rumble | Camera and rumble only. | 4 / 2 |
| 14 | `setFarClip` | 0x144104 | i distance | `camera_setFarClip` (0x18617c), capped at 1800. | 0x7d8a04 | - | 0 / 0 |
| 177 | `setWaveDetail` | 0x14176c | i on | Stores 0 or 1 at 0x4f7130 (read at 0x15f8f8). | 0x4f7130 | - | 1 / 1 |

### Audio

None of these reference `g_randSeed` directly (checked with gxref on the wrappers and their first callee).

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 3 | `sound` | 0x1435e0 | s lump, s name | `res_find` then `sound_playSample(1.0, 1.0, 0, res, 0)` (0x2134e8). Executed: the call has three float arguments (1.0, 1.0, 0.0) and two integers (the resource, 0). | audio | - | 0 / 0 |
| 4 | `soundSequence` | 0x143684 | s lump, s name | `sound_playOnObject(1.0, res, 0)` (0x214230), then `sound_setPlaysWhileFrozen` (0x216ad0) on the returned handle. | audio | - | 27 / 26 |
| 73 | `startMusic` | 0x146b68 | s name | `music_playLevel(name, 3)` (0x215f48). | audio stream | - | 0 / 0 |
| 74 | `startAudio` | 0x146ba4 | s name | `stream_playLevel(1, name, 2)` (0x215fc8). | audio stream | - | 0 / 0 |
| 75 | `endMusic` | 0x146be4 | - | `stream_queueStop(2)` (0x211338). | audio stream | - | 0 / 0 |

### Vehicles

No shipped script calls any of these.

| # | Name | Address | Arguments | What it does | Shared state written | Per-machine state read / network mode | Calls / levels |
|---|---|---|---|---|---|---|---|
| 108 | `putNPCInVehicle` | 0x142bdc | s vehicle, s npc | `Vehicle_attachNpcDriver(vehicle, npc)` (0x208af0). | vehicle +0x864, npc +0x474 and flags | - | 0 / 0 |
| 109 | `putPlayersInVehicle` | 0x142df4 | s vehicle | Calls the vehicle's virtual slot 14 (interact) for the active player first (if it is not -1), then for every other living player. | vehicle occupancy | AP | 0 / 0 |
| 110 | `entityRideVehicle` | 0x142c78 | s entity, s vehicle, i x, i y, i z, i angle | Asks the vehicle (virtual slot 19) for the world position and facing of a seat offset, moves the entity there and relinks it. | entity position | - | 0 / 0 |
| 111 | `controlVehicle` | 0x142d94 | s vehicle, i a, i b | Stores a at +0x410 and b (as float) at +0x2f0. | vehicle | - | 0 / 0 |
| 113 | `holdVehicle` | 0x142eec | s vehicle, i on | `Vehicle_setHold` (0x208b94). | vehicle | - | 0 / 0 |
| 114 | `getPlayerVPosition` | 0x142f40 | - | Scans living players that are in a vehicle and returns a vehicle float * 128. Executed: it compares vehicle +0x90c with the value kept so far but keeps vehicle **+0x34c**. | - | - | 0 / 0 |
| 115 | `getVPosition` | 0x1430cc | s vehicle | Vehicle +0x90c * 128, 0 if not found. | - | - | 0 / 0 |
| 116 | `getPlayerVDir` | 0x142fc8 | - | Returns 1, -1 or 0 from a dot product of a moving vehicle's direction with its path direction. Executed: for the first qualifying vehicle the result is 1 or −1; the 0.707 test can never send the scan on to the next player. | - | - | 0 / 0 |

### Fields the built-ins touch

These are the offsets seen in the handlers. "Meaning" is Inferred from the built-in's name and
use unless another area document says more.

Player record (`g_players[n]`, 0x4d8af0 + n × 0x4c30):

| Offset | Type | Meaning | Seen in |
|---|---|---|---|
| +0x24 | 5 bytes | recall destination text | `clearRecall` |
| +0x50 | i32 | class (1 and 4 are the caster classes tested) | `isClericOrWizard` |
| +0x54 | i32 | character model index 0–11 (0 tested). The earlier version said "race"; the record has no race field, and the model decides the class (`docs/player.md`) | `activePlayerIsDwarf` |
| +0x78..+0x84 | 4 × i32 | the four stats raised by stat numbers 4..7 | `playerAdjustStat` via `inventory_onStatPoint` |
| +0xac, +0xb0 | float | hit points, maximum | `healPlayer`, `giveFullHealth`, `planarSteel`, `getMaxPlayerHP` |
| +0xc0, +0xc4 | float | mana, maximum (the earlier version gave the type as i32; `refillPlayerMana` copies the word with a float load and store, 0x1424c8, and `docs/player.md` has both as floats) | `zeroPlayerMana`, `refillPlayerMana` |
| +0xe4 | i32 | gold | gold built-ins |
| +0xe8 | i32 | skill points | `clearAllSkills`, stat number 8 |
| +0x120, +0x124 | float | carried weight, capacity | give-item built-ins |
| +0x130 | 3 × 0x1208 | bags: 64 items of 0x48 bytes, count at +0x1200 of each | item built-ins |
| +0x41d0, +0x43d0 | 8 × 0x40, i32 | quest list (title 0x20, text 0x20), count | `addQuest`, `removeQuest` |
| +0x43d8 | ptr | the player's object | most player built-ins |
| +0x4434.. | 3 × ptr | equipped-item pointers cleared with the weapons | `removeAllWeapons` |
| +0x4460 + k × 0x68 | i16, +4 u8 | skill id of ability record k (set to -1, "empty") and the byte after it (set to 0); 15 records at +0x4440, this is their field +0x20; see FINDINGS D16. The earlier version called it the effect type; it indexes `g_skillTable` in the player cast helper 0x1a42b8 | `clearAllSkills` |
| +0x4bca | i16 | newWorld cooldown, 600 frames | `newWorld_netGate` |
| +0x4c0d + m | i8 | medal level for mission m | `mission_grantMedal`, `mission_getMedal` |
| +0x4c1c | u32 | status; low 5 bits equal to 2 blocks `saveGame`. These are bits 32–36 of the u64 at +0x4c18: a character-kind value, 1 by default and 2 for a character created on the lobby branch of the character screen (`docs/player.md`); not the difficulty | `saveGame` |
| +0x4c26 | u8 | set by `piercePlayerEar` | `piercePlayerEar` |
| +0x4c28 | u8 | script-visible flag bits | `setPlayerFlag`, `getPlayerFlag` |

Objects and creatures:

| Offset | Type | Meaning | Seen in |
|---|---|---|---|
| +0x0c | u32 | object flags: 0x1 no collision, 0x8 dead, 0x20 creature, 0x40 player, 0x4000 (setOFlag 14), 0x8000 not run, 0x1000000 friendly, 0x10000000 auto prop | many |
| +0x10..+0x18, +0x38 | 3 floats, u16 | position, facing | `moveMonster`, `entityRideVehicle` |
| +0x2c | ptr | property list: zero-terminated array of "key=value" strings | `newWorldParameter`, `script_setNextWorld` |
| +0x54, +0x58, +0x5a | | prop animation state, playing byte, status word (bit 7 = at end) | prop animation built-ins |
| +0x50 | ptr | creature sub-object whose virtual slot 8 sets the weapon type | `setWeaponType` |
| +0xa8 | u64 | creature flag word: bits 0, 23, 26, 27, 31, 43, 44 are used here | `setCFlag`, `followPlayer`, `friendly`, `followPath`, `showOnMap`, `increaseEnemyRank` |
| +0xd0, +0xd2, +0xd4, +0xd8, +0xe4 | i16 ×3, float, i16 | creature stats scaled by the params built-ins: damage low and high, attack rating, experience value, armour (`docs/creatures.md`) | `Creature_scaleStats` |
| +0x114, +0x11a | | creature animation state, status word (bit 7 = at end) | `startNPCAnim`, `NPCAnimAtEnd` |
| +0x124 | u32 | container flags, bit 3 | `setContainerProps` |
| +0x178 | i32 | auto-prop state | `autoPropGetState` |
| +0x228, +0x22c | float | creature hit points, maximum | `getHitPoints`, `setHitPoints`, `killMonster` |
| +0x231 | u8 | bit 3 set while hidden | `hideMonster`, `showMonster` |
| +0x232 | i16 | AI state (0x14, the death state, is skipped by root / stop-path) | `rootMonster`, `stopFollowingPath` |
| +0x234 | handle | current target | `Creature_setCharm` |
| +0x2e0, +0x2e8 | u16, float | push direction and speed on a player object | `hitPlayers` |
| +0x310, +0x312 | u8, i16 | team, charm timer (-1 permanent) | `Creature_setCharm` |
| +0x314 | i16 | -1 while rooted | `rootMonster`, `unRootMonster` |
| +0x3ac, +0x3ae, +0x3b0, +0x3c4 | i16 | values 1, 2, 3 and 5 of `setMonsterVal`: point-blank range, visual range, visual arc and activity radius in `docs/creatures.md` | `script_applyMonsterVal` |
| +0x3b4 | 3 floats | position stored when path following stops | `stopFollowingPath` |
| +0x540 | ptr | vehicle a player object is in | vehicle built-ins, `net_closeLocalMenus` |

## 4. Helper functions in the range that are not built-ins

| Address | Name | What it does |
|---|---|---|
| 0x143d04 | `newWorld_netGate` | Net games only, and only when the active player is not -1. If that player's cooldown (record +0x4bca) is running and more than one player is alive: shows a HUD line on the active player's machine and returns 1 (refuse). Otherwise sets the cooldown to 600 and returns 0. Offline it always returns 0. |
| 0x143e30 | `script_newWorldNoGate` | A copy of the newWorld handler without the gate. Not in the table, not referenced. |
| 0x144198 | `script_checkMonstersLeft_cb` | Per-object callback of `checkMonstersLeft`. |
| 0x144494 | `script_applyMonsterVal` | Body of `setMonsterVal` / `selectSetMonsterVal`. |
| 0x1445fc | `script_applyCFlag` | Body of `setCFlag` / `selectSetCFlag`. |
| 0x1447c4 | `script_applyOFlag` | Body of `setOFlag` / `selectSetOFlag`. |
| 0x1472c4 | `script_setNextWorld` | Writes the next-world name (0x41b6d0) and entrance byte (0x41b720). The level change itself happens elsewhere when the buffer is non-empty. |

Related data: 0x41b721 is the current level name (used by `cutScene`, `startDialog`,
`runMedalSuccess`); 0x4f7148 is the "medal player" byte used by the medal-mission built-ins
(written by the mission menu at 0x232040 and cleared by `game_loadLevel` at 0x1e6208 when
medal mode 0x4f713c is off); 0x4f7149 is the reward player set by `mission_grantMedal`;
0x4f7140 is set by the handler of game message 12 (0x1d9224) and cleared by `game_loadLevel`.

## 5. Per-machine state

How this was checked: every handler was read; then each handler and its direct callees (and
their callees) were scanned for references to `g_networkMode`, the cosmetic seed, camera
position and focus, `g_localMenuOpen`, raw pads, the ghost pointer, render counters, the
memory-card state, shop / help / dialog state, the active player, and for calls to
`net_getLocalPlayerSlot`, `net_isLocalSlot`, `net_firstActiveSlot`, the audio-status and
near-camera functions. Virtual calls were not followed. Kinds: **Observed** = the read is in
the bytes at the address; **Inferred** = the consequence follows but was not seen.

No built-in tests the prediction-copy flag 0x20000, and none needs to as long as scripts are
never started while `net_predictLocalPlayer` runs. The only script start reachable from
`Player_run` without such a test is the `*arrowShootNotify` hook (P9).

### P1. Level scripts are executed from draw code (Observed; consequence partly Inferred)

- `NPC_draw` 0x29e3ec runs the object's `exclamation` script each time the NPC is drawn and
  passes two tests against the local camera position 0x44f038 (a plane test and a distance
  above 240 units, 300 during a cutscene); call at 0x29e5f4. The result decides whether the
  marker over the NPC's head is drawn. `Gnome_draw` (call at 0x26926c), `GnomeNavigator_draw`
  (0x26a07c) and `Rondo_draw` (0x29f308) read the same property and call the same function;
  their conditions were not read.
- The map-drawing function 0x168cac, called from `minimap_draw`, tests a quest variable
  (`vars_get` at 0x1696a4) and runs a script (0x1696c4) for map entries that name one.
- `Player_draw` 0x1a46c0 calls `Player_interact(player, 0, displayOnly = 1)` for players local
  to the machine (0x1a4800). `Player_interact` calls virtual slot 13 of the nearest usable
  object in both modes, and for five classes that function runs `key` / `script` predicates
  (list in 2.2). `Player_run` makes the same call once per simulated frame for every real
  player (0x1a5c1c, under the same pause / dialog conditions), so these predicates run on all
  machines in lockstep *and* additionally on the owner's machine at display rate.

What this means for this area: the interpreter has no read-only mode, so a built-in reached
from one of these scripts executes a different number of times on different machines (drawing
depends on the local camera, the frame rate and which players are local).

What the shipped scripts do (Observed over all 120 scripts for the 108 automatically named
`return…` snippets, which is what a predicate looks like): they call only `getv`,
`playerHasItem`, `getEvil`, `checkPlayerGold`, `countQuestItems`, `getMissionComplete` and
`callScript`; the ten callees reached through `callScript` add `getMissionAvailable`,
`demoRunning` and `getNumPlayers`. Side effects that remain:

- `getv` appends an unknown name to `g_questVars` (value 0). The table then differs in order
  between machines. Lookups are by name, so values are unaffected (Inferred harmless; the save
  file lists the variables in table order).
- Two callees use script globals as scratch (`checkScrolls` in HONOR, `checkexit` in NITBONUS).
  They recompute before use.
- `JumpGate_interactPrompt` itself, not the script, marks the gate as found from this path:
  it writes gate +0x4d and calls `jumpgate_addCurrentLevel` (0x27d830, 0x27db60; Observed).
  Inferred: on the machine that owns the approaching player this can happen at draw time,
  up to one frame before the other machines do it in `Player_run`; `JumpGate_run` reads
  +0x4d and then draws from the gate's private generator. Followed no further (belongs to
  `monsters`).

Unknown: six of the 161 `if…` snippets do have side effects (`setv`, `startDialog`, `newWorld`,
`cutScene`, `saveCheckPoint`; in BLOOD1, DIS2, E3BLOOD, NITBONUS, TORMENTA). They are probably
actions, not predicates, but that depends on which object property names them, and
`objects.ob` was available for only four levels. A `getRand` in a predicate would desynchronise
`g_randSeed` at once; none of the `return…` snippets has one.

### P2. `runMedalSuccess` / `runMedalFail`: result depends on the local slot and the local memory card (Observed; reachability Unknown)

In a net game (0x1417e8 / 0x141c10) the handler compares `net_getLocalPlayerSlot(0)` with the
medal player 0x4f7148 (0x14180c–0x141814 / 0x141c50–0x141c58):

```
on the medal player's machine:           on every other machine:
    if memcard_isBusy(): return 0            if not readyFlag: return 0
    if not readyFlag:                        if memcard_isBusy(): skip the drawing
        send game message 12; return 0
    draw the box                             draw the box (unless skipped)
both: test the medal player's pad word; on confirm or cancel write the next world
      (and open the mission menu on cancel) and return 1, else return 0
```

`readyFlag` is 0x4f7140, set when message 12 is processed. So the medal player's machine
waits for its own card write (started by `setpv`, P4) before it lets everyone continue; that
part is a deliberate handshake. The hazard is the first line: after the flag is set, the
medal player's machine still returns 0 without testing the pad whenever its card is busy
(0x14181c, 0x141824), while the others test the pad (0x141858–0x141868 jump to the pad test).
If a press arrives in such a frame, the other machines write the next world and return 1 to
the script, which then calls `restorePlayer`, and the owner's machine does neither. Whether
the card can be busy at that point is not established.

The box and reward lines are drawn directly from this run-task code, and which reward lines
appear depends on the local player's own medal (`mission_getMedal` with flag 0, 0x1418ac);
that part is cosmetic.

Related (Observed, outside the range): both handlers set the countdown 0x4f7114 to 2 on every
call. While it is positive, the run task at 0x1e3d60 calls `net_closeLocalMenus(0)` on the
medal player's machine only, and only if a menu is open there. That function also empties
vehicles, so this is the same pattern as P6.

### P3. `getMedal` returns the local player's medal (Observed)

`mission_getMedal(mission, -1, 0)` reads the record of `net_getLocalPlayerSlot(0)`
(0x1bf868). The value handed to the script differs between machines whenever the players'
medal histories differ. In all nine shipped uses the value is stored in a script global and
passed only as the second argument of `runMedalSuccess`, where it selects text. So today it
puts a per-machine value into script memory without reaching shared state (Observed for the
nine medal scripts).

### P4. Memory-card state reaches scripts (Observed)

- `saveDone` returns whether this machine's card state is idle (0x146d64).
- `saveGame` starts the save flow for this machine's first local player (0x146c58).
- `setpv` starts a config save on every machine whose stored profile value differed
  (`profile_setVar` → `memcard_requestConfigSave`), and `getpv` returns the profile value of
  this machine.
- `endGame` starts the end-of-game save for the local slot.

The three scripts that call `saveDone` (ACTINTRO, ENDGOOD, ENDBAD) call `saveEndConfig` first,
which drops every remote peer (`net_dropAllRemotes`, called at 0x146cc4), so by then there is no
lockstep left (Inferred from the script order). `getpv` is never called. The link that
matters is `setpv` → card busy → P2.

### P5. `startDialog`: one machine speaks for all, with its own camera (Observed)

`dialog_start` (0x22fa50) acts only where `net_isLocalSlot(g_scriptActivePlayer)` is true
(0x22fa94) and no dialog is open (0x22faa4). It puts that machine's camera position
(0x44f038, read at 0x22fb1c) and two camera angles into game message 0 and sends it
(0x22fb94). Every machine opens the dialog from the message, so the camera values are shared
once sent (Inferred). Two things are decided per machine before that: whether exactly one
machine sends (this needs the active player to be the same everywhere, see 2.3) and the
dialog-open test on the sender. No writer of the active player stores -1; the tests for -1
in `newWorld_netGate` and `putPlayersInVehicle` look defensive.

### P6. `activateStore` in a net game does shared work only on some machines (Observed; effect Inferred)

In the net branch (0x14405c) the handler loops over living players and, for each one that is
local to this machine (0x1440a4), calls `net_closeLocalMenus(0)` (0x1440b4) and
`shop_openOrStock(slot, 0, 1)` (0x1440c4). `net_closeLocalMenus(0)` is not purely local: it
also ejects every living player from a vehicle. A machine whose own player is dead skips the
call. If a player is in a vehicle when a store opens, vehicle state diverges (Inferred; the
four levels that call `activateStore` were not checked for vehicles). The store UI itself is
per machine by design. Offline the store opens for the active player.

`storeRunning`, `helpMessageActive`, `dialogRunning` and `playerSelRunning` return menu state
(`g_shopOpen`, `g_helpMessageOpen`, the dialog pointer, 0x4fbbdc). The first two are certainly
per machine in a net game. No shipped script calls any of the four. Internally
`activateMissionMenu` and `activateStore` branch on the dialog-open test (0x143fb0, 0x14403c)
and `activateMissionMenu` then registers tasks, so they inherit whatever synchronisation the
dialog system has.

### P7. `playGotItemSound` rewrites the active player (Observed)

The handler clamps `g_scriptActivePlayer` to 0..1 and stores it back (0x146508, 0x146518)
before calling `player_voice`, which itself returns immediately unless the slot is local and
reads audio status. The write is the same on all machines, so it is not a desync, but in a
game with three or four players it silently turns active player 2 or 3 into 1 for every later
reader (the newWorld gate's cooldown, `startDialog`'s choice of sender). Three levels call it
(DRUNARM, STORM4, TORMENT2).

### P8. `playerAdjustStat` with an explicit player sends a message from every machine (Observed; effect Inferred)

For a player other than -1 the handler calls `invmsg_sendStatPoint` (0x1c5780) instead of
changing the record. A script runs on every machine, so every machine sends inventory message
6 and the stat would be raised once per machine. All 27 shipped calls pass -1 (direct change
of the reward player), so this is latent.

### P9. Script hooks reachable during prediction (Observed; inert in shipped data)

`Player_run` calls `script_runByName` for `*arrowShootNotify` at 0x1a90f0. The code just before
it tests the prediction-copy flag only to skip an ammunition decrement (0x1a9050–0x1a9088), not
the hook. No level defines the entry point, so today the call returns -1. The inventory hooks
(`*inventoryOnNotify` from `hud_run`, `*exitInventoryNotify`, the equip hooks) are driven by
local menu code in the same way.

### P10. HUD-only differences (Observed, cosmetic)

`docs/strings.md` executes these five with the real string table and formatter: the state each
writes, the 180-tick message, the 5-tick bust and compass lease, the one-slot help box.
`setInfo`, `showCompass`, `showBust`, `addHelpMessage` and `addHelpMessageF` write HUD state
only on machines where the target slot is local or where no local menu is open
(`hud_showMessage` 0x1d92a0, `hud_setCompassTarget` 0x1df668, `hud_setBust` 0x1dfaa0,
`hud_showHelpMessage` 0x1d9830). `addHelpMessage` in a net game additionally sends menu-state
message 2 for the first living local player. `shakeCamera`, `hidePlayers`, `setFarClip`,
`setWaveDetail`, `changeSwoop`, `hudFadeScreen` and the audio built-ins write presentation
state identically everywhere. `addExpandingPool` goes through `decal_add`, which reads the
camera position (0x19faa8) and a local detail option; no shipped script calls it.

### Not hazards, checked

- Object lists come from the name hash in insertion order, not from pointer order
  (`world_findObjectsByName`).
- `g_scriptSelectedObj` is a pointer but is only dereferenced, never compared or returned.
- `getRand`, `givePlayerRandom`, `generateMonster`, `dropItem`, `lightEffect`,
  `particleMorph`, `hornOmen`, `planarSteel` and the give-item built-ins advance `g_randSeed`
  (directly or through an object constructor). That is correct for lockstep and wrong only
  in a script that runs from draw code (P1).
- None of the audio or particle wrappers references `g_randSeed` or the cosmetic seed directly.
- `reapEnemies`, `checkMonstersLeft` and `objInPlayerTrig` walk the world with
  `g_excludeMask`, so they do not see the prediction copy while simulating.
- `gamePaused`, `getLevelTimer`, `getManaUsed`, `getHealthUsed`, `countPlayersAlive`,
  `checkPlayerAlive` read lockstep state (the level timer advances in the run task at
  0x1e3d60 when the game is not frozen; the potion counters are written in
  `Player_usePotion`, which is guarded against the prediction copy, FINDINGS G8).

## 6. Reference lists

### Built-ins that read the active player (0x4d8ae4)

| Built-in | Where | Use |
|---|---|---|
| `newWorld`, `newWorldAlways`, `simpleNewWorld` | `newWorld_netGate` 0x143d24, 0x143d5c, 0x143da4 | net only: whose cooldown is tested and set; whose machine shows the refusal |
| `startDialog` | `dialog_start` 0x22fa8c, 0x22fb14 | which machine sends the dialog message; the value is put in the message |
| `activateMissionMenu` | 0x143ffc | offline only: who gets the menu |
| `activateStore` | 0x144070 (and the deferred open in the dialog-end handler, 0x22f868) | offline only: who gets the store |
| `playGotItemSound` | 0x1464f0, 0x14654c | whose voice plays; also rewrites it (P7) |
| `activePlayerIsDwarf` | 0x1465a8 | reads that player's record +0x54 |
| `putPlayersInVehicle` | 0x142e3c, 0x142e70 | boards that player first |
| `setBestActivePlayer` | 0x1470fc–0x14712c | writes it and returns it |

### Built-ins that behave differently when `g_networkMode` is set

| Built-in | Where | Difference |
|---|---|---|
| `networkMode` | 0x14221c | returns the flag |
| `runMedalSuccess`, `runMedalFail` | 0x1417e8, 0x141a78; 0x141c10, 0x141ce8 | offline: sets `g_paused`; net: P2, and the button prompt is drawn only for the medal player |
| `newWorld`, `newWorldAlways`, `simpleNewWorld` | 0x143d0c | the cooldown gate exists only in net games |
| `newWorld…`, `newWorldParameter`, `cutScene`, `activateStore`, `activateMissionMenu` | `net_closeLocalMenus` 0x1eb000 | that function does nothing offline; in a net game it sends menu-state message 2, closes local menus and (argument 0) empties vehicles |
| `activateMissionMenu` | 0x143fd4 | offline: active player; net: first active slot |
| `activateStore` | 0x14405c | offline: active player; net: every living local player (P6) |
| `saveEndConfig` | 0x146c98 | net: drops all remote peers |
| `saveGame` | `memcard_requestSave` 0x21766c | net: only for a local slot, and announces the menu |
| `getMedal` | `mission_getMedal` 0x1bf85c | the flag-0 path used here reads the local slot in both modes; offline that is slot 0 |
| `addHelpMessage`, `addHelpMessageF` | `hud_showHelpMessage` 0x1d9874 | net: needs a living local player, sends message 2 |
| `givePlayerItem`, `giveOnePlayerItem`, `givePlayerRandom` | `inventory_giveItem` 0x1c18c8, 0x1c1a10, 0x1c1bd0 | the first-recall-potion tutorial (sets a quest variable, shows a hint) is offline only |
| `playGotItemSound` | `player_voice` 0x1b7be8 | offline the voice is also suppressed while a local menu is open |
| `pauseGameControl` | `tasks_run` 0x322710 | net: the lock-out it sets is zeroed at the start of every `tasks_run` (Inferred) |
| `playerAdjustStat` (explicit player) | `invmsg_sendStatPoint` | sends a message (P8) |

Built-ins that call `net_isLocalSlot` only to decide about sound or HUD text
(`givePlayerExp`, `removePlayerItem`, the equip path of `givePlayerItem`) behave the same in
both modes because that function returns true for every slot offline.

## 7. Notes on existing entries (not edited here)

- FINDINGS D20 calls the writer of the active player at 0x22fa34 "a mission-menu reset". It is
  `dialog_free` (0x22f99c), which resets the dialog system and is called from
  `game_clearLevel` (0x1e50c8), i.e. at level teardown on every machine.
- The note on `scr_load` (0x13e8f8) in `symbols/netcode.tsv` says "version 0x18" and "unpacks
  the relocation list". The 0x18 is the name-record size at header +0xa, and the loop expands
  the optional compact encoding (header flag bit 2), which no shipped script uses.
  `scr_findInTable38` (0x13ebd8) is the public-variable lookup; the table is empty in every
  script. (The `scr_load` note has since been corrected.)
- `tools/scr.py` prints a string literal whose pool offset is below 8 as a number (hence
  listings such as `callScript(0)`), and it does not show arguments that were pushed with
  PUSH.pri / PUSH.alt. The true argument count is the PUSH.C just before each SYSREQ.C
  divided by 4; the counts in section 3 were taken from there.
- The Ghidra export names 0x143dd0 `script_newWorldAlways`; names.tsv has `script_newWorld`.
  Both table entries point at it.

## 8. Open questions

1. **Does a level's script image survive between visits?** `scr_load` skips its whole
   initialisation when machine flag 0x2000 is already set. If a lump stays cached and the
   level is entered again without re-reading the file, the script's global variables keep
   their old values. Settle by reading how `lump_load` and the level teardown free lumps.
2. **P2 reachability**: can `memcard_isBusy()` be true on the medal player's machine after
   message 12 has been processed? Needs the card state machine (`audio-save`) and a test with
   two machines finishing a medal mission.
3. **Medal player 0x4f7148**: it is written by the mission menu from 0x4f6960. Is that value
   the same on every machine in a net game? `removeAllItems`, `removeAllWeapons`,
   `clearAllSkills`, `savePlayer`, `restorePlayer` and `givePlayerItem` in medal mode all act
   on it.
4. **Draw-time predicates (P1)**: extract `objects.ob` for all levels and list every `key`,
   `exclamation`, jump-gate `script` and map-marker property; check that none names an entry
   with side effects (start with the six `if…` snippets named in P1).
5. **Dialog open flag**: is 0x8e2d60 set and cleared on the same simulated frame everywhere?
   `activateStore`, `activateMissionMenu`, `Player_run` and `dialog_start` branch on it.
6. **Inventory message 6** from several machines (P8): does the handler apply it once per
   sender?
7. Does `player_voice` (0x1b7ba8) or `shop_openOrStock` in mode 0 write anything that must be
   shared? Both run only on the owner's machine when reached from `playGotItemSound` /
   `activateStore`.
8. Meaning of the creature fields the monster built-ins set: +0x3ac / +0x3ae / +0x3b0 /
   +0x3c4, flag-word bits 0, 23, 26, 27, 43, 44, virtual slots 27 and 34, AI state 0x14, and
   the 14 values of `setParticle`. (All but the last are answered in `docs/creatures.md`:
   the four fields are named in the table of section 3, slot 27 sets the AI state, slot 34
   sets HomeRange, state 0x14 is the death state, and its flag table covers the bits.)
9. The byte at 0x4f8b58 that suppresses `preStart` and `start` (probably "loading a save").

## 9. Not done

- About 55 opcode handlers that no shipped script uses were not read individually.
- Callees of the built-ins were read one level deep (two for the local-state scan); virtual
  calls were not followed, so "none found" in the tables means "none in the handler or its
  direct callees".
- The vehicle built-ins and `setParticle` were only skimmed; no shipped script uses the
  former.
- Nothing here was run. The hazards P1, P2 and P6 in particular need two running copies.
  (The live rig of `docs/issues/live-rig.md` is one running copy; two have not been joined.)
