# The level-script machine — implementation specification

What an interpreter has to do so that a `script.scr` behaves exactly as it does in
`SLUS_209.73`. The machine is the Small "abstract machine" (AMX); `docs/script.md` identifies
it and documents the 191 built-in commands and how the game drives the machine. This document
is only about the machine: image, loader, registers, every opcode, the native-call convention,
strings and errors.

It comes with a model and a test:

- `tools/ref_amx.py` — the machine in Python, one branch per opcode, no game data.
- `tools/difftest_amx.py` — runs the original machine code in `tools/ee_emu.py` and the model
  side by side. Section 11 says exactly what it compares and what it does not.
- `tools/test_ref_amx.py` — unit tests of the model that need no game files.

Marks: **[X]** executed — the original code, run in the emulator, agrees with the model on the
inputs of the property named (section 11); **[O]** observed by reading the code at the address
given; **[I]** inferred; **[U]** unknown. A statement without a mark in sections 1–8 is [O] at
the addresses of its section heading and [X] through the properties listed in section 11.
Everything is integer arithmetic; no floating point is involved, so agreement means bit for bit.

Notation: a *cell* is a signed 32-bit little-endian word. `[a]` is the cell at script address
`a`; script addresses count bytes from the start of the data block. All register arithmetic
wraps at 32 bits. "Unsigned" means the cell is compared as a 32-bit unsigned number.

## 1. The image

`script.scr` is loaded once per level and used in place. Offsets in the header are relative to
the header, which starts at file offset 0x60.

```
0x00  machine structure, 0x60 bytes, zero on disc        (section 1.1)
0x60  header, 0x40 bytes                                  (section 1.2)
      entry-point table, native table                     24-byte records
      code                                                header cod .. dat
      data (globals, string literals)                     header dat .. hea
      heap and stack room                                 header hea .. stp
```

In the 120 shipped files the image is exactly 0x60 + stp bytes long, and in the four level
lumps available here `script.scr` is the last file of the lump, with nothing after it [O].

### 1.1 Machine structure

| Offset | Name | Content |
|---|---|---|
| +0x00 | base | address of the header |
| +0x04 | callback | native dispatcher; `scr_callNative` 0x141050 unless the word was not zero on load |
| +0x08 | debug | 0x1410b0 unless not zero on load; never called by this interpreter |
| +0x0c | cip | code offset of the instruction after the last native call |
| +0x10 | frm | FRM at the last native call |
| +0x14 | hea | heap top; start value of HEA for a run; written at every native call |
| +0x18 | stk | stack pointer; start value of STK for a run; written at every native call, by every RETN and by some exits (section 4.3) |
| +0x1c | stp | stack top, data-relative; constant after load |
| +0x20 | flags | 0x2000 loaded, 0x8000 code relocated, 0x4000 cleared at the start of every run |
| +0x24, +0x28 | curline, curfile | last LINE record seen (by the loader, then by execution) |
| +0x2c | dbgcode | kind of the last debug record the loader saw: 1 FILE, 2 LINE, 3 SYMBOL, 8 SRANGE |
| +0x30, +0x34, +0x38 | dbgaddr, dbgparam, dbgname | words of the last SYMBOL / SRANGE record; dbgname is a pointer into the code |
| +0x3c, +0x4c | usertags, userdata | 4 + 4 words, unused by the game |
| +0x5c | error | cleared before each native; a native that sets it stops the run with that code |

### 1.2 Header

| Offset | Type | Field |
|---|---|---|
| +0x00 | i32 | size: end of the stored code and data (only used for compact images) |
| +0x04 | u16 | magic 0xf1e0 |
| +0x06 | i8 | file version (3 in every shipped file; not examined by the loader) |
| +0x07 | i8 | required machine version, compared as a signed byte |
| +0x08 | u16 | flags: bit 0 = 16-bit characters (refused), bit 2 = compact encoding |
| +0x0a | u16 | record size, must be 24 |
| +0x0c | i32 | cod: start of code |
| +0x10 | i32 | dat: start of data |
| +0x14 | i32 | hea: end of initialised data |
| +0x18 | i32 | stp: end of the image's memory; lowered by 4 by the loader |
| +0x1c | i32 | start address for entry index -1, or -1 |
| +0x20, +0x24 | i16, i32 | entry points: count, table offset |
| +0x28, +0x2c | i16, i32 | natives: count, table offset |
| +0x30, +0x34 | i16, i32 | libraries (unused) |
| +0x38, +0x3c | i16, i32 | public variables (unused) |

A table record is one cell and a 20-byte zero-terminated name. For an entry point the cell is
its code offset; the table is sorted by name. For a native the cell is 0 on disc and receives
the handler's address when the native is bound.

## 2. Loading — `scr_load` 0x13e8f8, `scr_relocate` 0x13e6d0

`scr_load(machine, header)` does this, in this order:

1. magic ≠ 0xf1e0 or record size ≠ 24 → return 17.
2. required machine version ≥ 4 (signed byte, so 0x80–0xff pass) → return 18.
3. header stp not in 1..0x7ffffffe → return 17.
4. header flag bit 0 set → return 17.
5. header flag bit 2 set → expand the compact code in place (2.1). This happens before step 6.
6. machine flag 0x2000 already set → return 0 and do nothing else.
7. Set machine flag 0x2000 and base. Lower the header's stp field by 4 and store a zero cell
   at header + stp (the "sentinel": the last cell of the image, which stops string readers).
8. hea = header hea − dat; stk = stp = header stp − dat. Install the default callback and
   debug hook where the words are zero. curline = curfile = 0. Set the global at 0x40335c to 1
   (it tells the string routines that the host is little-endian).
9. Run the relocation pass (2.2) and **ignore its result**. Return 0.

So a script whose code the relocator refuses still "loads"; it just never runs (error 22).
The game goes on to `scr_registerNatives` (section 6.2) and never looks at either result [O]
(`script_setCurrent` 0x1ed650).

### 2.1 Compact encoding (0x13e96c–0x13ea08)

No shipped script uses it. The stored bytes from cod to size expand to the cells from cod to
hea. One cell is a run of bytes, most significant first, 7 bits each; every byte but the last
of a run has bit 7 set; bit 6 of the first byte is the sign and is extended to 32 bits. The
loader works backwards from the end, in place:

```
while bytes remain:
    value = 0; shift = 0
    repeat: take the last unread byte b; value |= (b & 0x7f) << (shift mod 32); shift += 7
    until no byte remains or the byte before it has bit 7 clear
    if b & 0x40: while shift < 32: value |= 0xff << shift; shift += 8
    store value in the next cell down from hea
```

The shift is the CPU's, so a sixth byte of one cell lands 3 bits up, not out of range [X D4].
Nothing checks that the cells fit; expanding in place only works when no prefix of the stream
is longer than four bytes per cell.

### 2.2 The relocation pass

One linear walk over the code from offset 0 while the offset is below dat − cod. At each step
the cell at the offset is taken as an opcode:

- 0x100 or more (signed) → stop with error 6.
- otherwise the cell is **overwritten** with the word at handler table 0x403150 + 4 × opcode,
  and then, unless 1 ≤ opcode ≤ 0x82, the pass stops with error 6 (so for 0, 0x83–0xff and
  negative values the cell is replaced by whatever lies at that table position) [X D2].
- then by operand class (jump table 0x530fd0, [X T2]):

| Class | Opcodes | The pass does |
|---|---|---|
| none | 09 17 19 1b 21–25 2a 2b 2e–30 32 41–43 48–56 59 5a 5d–68 6b 6c 6f–71 74 7a 80 | nothing |
| value | 01–08 0a–16 18 1a 1c–20 26–29 2c 2d 34 44–47 57 58 5b 5c 69 6a 6d 6e 72 73 75–79 7b | skips one cell |
| code address | 31 33 35–40 81 | adds the code's machine address to the operand cell |
| FILE 7c | size, number, name | curfile = number, dbgcode = 1, dbgname → name; skips 4 + size bytes after the opcode |
| LINE 7d | line, file | curline, curfile set, dbgcode = 2 |
| SYMBOL 7e | size, address, flags, name | dbgaddr, dbgparam set, dbgname → name, dbgcode = 3; skips 4 + size bytes |
| SRANGE 7f | two values | dbgaddr, dbgparam set, dbgcode = 8 |
| CASETBL 82 | count n, default address, n × (value, address) | if n ≥ 0 adds the code address to the default and to each record's address; skips 8n + 8 bytes |

When the walk reaches the end, machine flag 0x8000 is set. If it stops early the flag stays
clear and the debug words keep what was stored up to there [X D2]. After a successful pass the
code is threaded: executing means jumping to the address in the opcode cell. Two consequences
an interpreter must reproduce:

- **Only cells the pass treated as opcodes can be executed.** A jump to any other cell makes
  the original jump to the cell's value as a machine address. The model raises `HostFault`.
- After load, curline / curfile are those of the *last* LINE record in the code, and stay so
  until a LINE executes [X A1].

## 3. Registers and memory

| Register | Meaning |
|---|---|
| PRI, ALT | accumulator and second operand |
| CIP | code offset of the next instruction |
| FRM | frame pointer (script address) |
| STK | stack pointer, grows down |
| HEA | heap top, grows up |

There are no flags. The run keeps STK, HEA and FRM to itself: it copies them to the machine
structure before each native call and never reads them back, so a native cannot change them.

```
0 ........ header hea−dat ................. STK ......... stp     stp+4 = end of image
 globals, literals      heap →     free      ← stack      sentinel cell (0)
```

**Checked addresses.** LOAD.I, LODB.I, STOR.I, STRB.I, LIDX and LIDX.B test their address:

```
if (HEA <= a and a < STK) or a >= stp: error 5        # all three compares signed
```

so every negative address passes [X B3]. No other opcode tests an address: LOAD/STOR and the
LREF/SREF, INC/DEC, ZERO, PUSH forms, INC.I/DEC.I, MOVS, CMPS and FILL read and write wherever
the operand points, and pushes are never checked against the heap.

**Outside the block.** An address below 0 or beyond the image is not an error to the
original; it reads or writes the console's memory around the image (below the data lie the
script's own code — in threaded form — and header). The same goes for a word access that is
not on a 4-byte boundary (the CPU raises an address exception) and a 2-byte access on an odd
address. The result depends on the host, so the model raises `HostFault` in all these cases
and the differential test does not compare them.

## 4. Running an entry point — `scr_interpret` 0x13ecf8

`scr_interpret(machine, result pointer, index, argument count, arguments)`. Called with a
null machine it only stores the handler table address through the result pointer and returns
0 (the relocator uses this) [X T3]. The game's only caller, `script_runByName` 0x1ed694, passes
no arguments, sets its result word to 0 first and ignores the error returned.

### 4.1 Entry

In this order [X C1–C4]:

1. callback word zero → return 9.
2. Clear machine flag 0x4000. Flag 0x8000 clear → return 22.
3. STK = machine stk (remember it as the *entry value*), HEA = machine hea.
4. **header** stp < STK → return 7. This is the header's field, which is larger than the
   machine's stp by `dat`; a stack pointer up to `dat` bytes above the real top is accepted.
5. HEA < 0 → return 8.
6. index −1: CIP = header start address; negative → return 20. Index below −2 → return 20.
   Otherwise index ≥ entry count → return 20, else CIP = address cell of table record `index`.
   **Index −2 is not refused**: the "record" two places before the table is read.
7. STK −= 4 × count; the arguments are stored at [STK], [STK+4], … in order. STK −= 4;
   [STK] = 4 × count. STK −= 4; [STK] = 0 (return address 0 means "back to the host").
8. STK < HEA + 0x40 → return 3 — after the cells of step 7 were written.
9. FRM = 0, ALT = 0. **PRI is not initialised**: it is whatever the interpreter's own stack
   frame held (frame offset +4). Small-compiled functions set PRI before they return, so this
   is only visible to hand-made code; the model takes it as the `pri` argument [X C2].

### 4.2 Calls and frames

A script function begins with PROC and ends with RETN. Seen from FRM after PROC:

| Address | Content |
|---|---|
| FRM + 12 + 4k | argument k |
| FRM + 8 | size of the arguments in bytes |
| FRM + 4 | return address (code offset; 0 = end of the run) |
| FRM | caller's FRM |
| below | locals and temporaries |

### 4.3 How a run ends, and what happens to machine stk

| Exit | Returns | Result stored | machine stk afterwards |
|---|---|---|---|
| RETN with return address 0 | 0 | PRI | the STK it computed (every RETN stores it, nested ones too) |
| RET with return address 0 | 0 | PRI | entry value |
| HALT n | n | PRI | entry value |
| errors 4, 5, 6, 11 and an error set by a native | the code | no | entry value |
| entry checks (7, 8, 9, 20, 22, 3), STACK (3, 7), HEAP (3, 8) | the code | no | **unchanged** — the value of the last native call or RETN, or the entry value if there was none |

machine hea is never restored: it holds the HEA of the last native call [X B1, C5].

A balanced entry point therefore leaves stk where it was. An unbalanced one moves it for every
later run (section 9).

There is no instruction budget, yield or sleep. "Deferred calls" are not a machine feature:
the built-in `addDeferedCall` queues an entry-point name and the game runs it on a later frame
through `script_runByName` (`docs/script.md` section 2).

## 5. Opcodes

Handler addresses are in `ref_amx.OPCODES` and `docs/script.md` 1.9 [X T1]. `v` is the operand.
"jump to x" sets CIP = x; execution continues only if x is an instruction (2.2). `next` is the
offset of the following instruction. Opcodes marked * occur in shipped scripts.

| Op | Mnemonic | Effect |
|---|---|---|
| 00 | NONE | machine stk = entry value, return 6. Unreachable: the loader refuses opcode 0 [X B2] |
| 01* 02* | LOAD.pri / .alt v | PRI / ALT = [v] |
| 03* 04* | LOAD.S.pri / .alt v | PRI / ALT = [FRM + v] |
| 05 06 | LREF.pri / .alt v | PRI / ALT = [[v]] |
| 07 08 | LREF.S.pri / .alt v | PRI / ALT = [[FRM + v]] |
| 09* | LOAD.I | check PRI; PRI = [PRI] |
| 0a | LODB.I v | check PRI; v = 1: PRI = byte at PRI; v = 2: PRI = 16 bits at PRI; both zero-extended; v = 4: PRI = [PRI]; other v: nothing |
| 0b* 0c* | CONST.pri / .alt v | PRI / ALT = v |
| 0d 0e | ADDR.pri / .alt v | PRI / ALT = FRM + v |
| 0f* 10 | STOR.pri / .alt v | [v] = PRI / ALT |
| 11* 12 | STOR.S.pri / .alt v | [FRM + v] = PRI / ALT |
| 13 14 | SREF.pri / .alt v | [[v]] = PRI / ALT |
| 15 16 | SREF.S.pri / .alt v | [[FRM + v]] = PRI / ALT |
| 17* | STOR.I | check ALT; [ALT] = PRI |
| 18 | STRB.I v | check ALT; store the low 1, 2 or 4 bytes of PRI at ALT for v = 1, 2, 4; other v: nothing |
| 19* | LIDX | a = ALT + PRI × 4; check a; PRI = [a] |
| 1a | LIDX.B v | a = ALT + (PRI << (v mod 32)); check a; PRI = [a] |
| 1b* | IDXADDR | PRI = ALT + PRI × 4 |
| 1c | IDXADDR.B v | PRI = ALT + (PRI << (v mod 32)) |
| 1d 1e | ALIGN.pri / .alt v | if 0 ≤ v < 4 (unsigned): PRI / ALT ^= 4 − v |
| 1f | LCTRL v | PRI = 0: header cod, 1: header dat, 2: HEA, 3: machine stp, 4: STK, 5: FRM, 6: `next`; other v: nothing |
| 20 | SCTRL v | 2: HEA = PRI, 4: STK = PRI, 5: FRM = PRI, 6: jump to PRI; other v: nothing. No checks |
| 21* 22* 23 | MOVE.pri, MOVE.alt, XCHG | PRI = ALT; ALT = PRI; swap |
| 24* 25* | PUSH.pri / .alt | STK −= 4; [STK] = PRI / ALT |
| 26 | PUSH.R v | push PRI v times, v taken as unsigned (0: nothing) |
| 27* | PUSH.C v | push v |
| 28* 29 | PUSH v, PUSH.S v | push [v]; push [FRM + v] (the value is read before STK moves) |
| 2a 2b* | POP.pri / .alt | PRI / ALT = [STK]; STK += 4 |
| 2c* | STACK v | ALT = STK; STK += v; STK < HEA + 0x40 → return 3; header stp < STK → return 7 |
| 2d | HEAP v | ALT = HEA; HEA += v; STK < HEA + 0x40 → return 3; HEA < 0 → return 8 |
| 2e* | PROC | push FRM; FRM = STK |
| 2f | RET | FRM = [STK]; t = [STK + 4]; STK += 8; t = 0 → end (4.3), else jump to t |
| 30* | RETN | FRM = [STK]; t = [STK + 4]; STK += 8; STK += [STK] + 4; machine stk = STK; t = 0 → end, else jump to t |
| 31* | CALL v | push `next`; jump to v |
| 32 | CALL.pri | push `next`; jump to PRI |
| 33* | JUMP v | jump to v |
| 34 | JREL v | jump to `next` + v |
| 35* 36* | JZER, JNZ v | jump if PRI = 0; if PRI ≠ 0 |
| 37* 38* | JEQ, JNEQ v | jump if PRI = ALT; if PRI ≠ ALT |
| 39–3c | JLESS, JLEQ, JGRTR, JGEQ v | jump if PRI <, ≤, >, ≥ ALT, unsigned |
| 3d*–40* | JSLESS, JSLEQ, JSGRTR, JSGEQ v | the same, signed |
| 41 42 43 | SHL, SHR, SSHR | PRI = PRI shifted left / right logical / right arithmetic by ALT mod 32 |
| 44 45 | SHL.C.pri / .alt v | PRI / ALT <<= v mod 32 |
| 46 47 | SHR.C.pri / .alt v | PRI / ALT shifted right logical by v mod 32 |
| 48* 4b | SMUL, UMUL | PRI = low 32 bits of PRI × ALT (the same instruction for both) |
| 49 | SDIV | ALT = 0 → error 11; (PRI, ALT) = floored divide of PRI by ALT (below) |
| 4a* | SDIV.alt | PRI = 0 → error 11; (PRI, ALT) = floored divide of ALT by PRI |
| 4c | UDIV | ALT = 0 → error 11; unsigned: PRI, ALT = PRI / ALT, PRI mod ALT |
| 4d | UDIV.alt | PRI = 0 → error 11; unsigned: PRI, ALT = ALT / PRI, ALT mod PRI |
| 4e* 4f 50* | ADD, SUB, SUB.alt | PRI = PRI + ALT; PRI − ALT; ALT − PRI |
| 51 52 53 | AND, OR, XOR | PRI = PRI op ALT |
| 54* 55 56 | NOT, NEG, INVERT | PRI = (PRI = 0 ? 1 : 0); −PRI; bitwise complement |
| 57* 58* | ADD.C v, SMUL.C v | PRI += v; PRI = low 32 bits of PRI × v |
| 59* 5a* | ZERO.pri / .alt | PRI / ALT = 0 |
| 5b* 5c | ZERO v, ZERO.S v | [v] = 0; [FRM + v] = 0 |
| 5d 5e | SIGN.pri / .alt | if bit 7 is set, set bits 8–31; otherwise **nothing** (upper bits are never cleared) |
| 5f* 60 | EQ, NEQ | PRI = 1 or 0 for PRI = ALT; PRI ≠ ALT |
| 61–64 | LESS, LEQ, GRTR, GEQ | PRI = 1 or 0 for PRI <, ≤, >, ≥ ALT, unsigned |
| 65* 66 67* 68 | SLESS, SLEQ, SGRTR, SGEQ | the same, signed |
| 69* 6a | EQ.C.pri v, EQ.C.alt v | PRI = (PRI = v); PRI = (ALT = v) |
| 6b 6c | INC.pri / .alt | PRI / ALT += 1 |
| 6d* 6e 6f | INC v, INC.S v, INC.I | [v] += 1; [FRM + v] += 1; [PRI] += 1 (not checked) |
| 70 71 | DEC.pri / .alt | PRI / ALT −= 1 |
| 72* 73 74 | DEC v, DEC.S v, DEC.I | [v] −= 1; [FRM + v] −= 1; [PRI] −= 1 (not checked) |
| 75 | MOVS v | copy v bytes (unsigned count) from PRI to ALT, lowest address first, byte by byte in effect: an overlapping copy to a higher address repeats the source |
| 76 | CMPS v | compare v bytes at ALT with those at PRI; PRI = 0, or (byte at ALT) − (byte at PRI) at the first difference, bytes unsigned |
| 77 | FILL v | store PRI in the cells ALT, ALT + 4, … while at least 4 of the v bytes (unsigned) remain; ALT unchanged |
| 78 | HALT v | store PRI as the result; machine stk = entry value; return v |
| 79* | BOUNDS v | PRI > v or PRI < 0 (signed) → error 4 |
| 7a | SYSREQ.pri | native call with index PRI (section 6) |
| 7b* | SYSREQ.C v | native call with index v |
| 7c | FILE | no effect; continues after the record |
| 7d* | LINE line, file | machine curline, curfile = the two operands |
| 7e | SYMBOL | machine dbgaddr, dbgparam, dbgname = the record's; continues after the record |
| 7f | SRANGE a, b | machine dbgaddr, dbgparam = a, b |
| 80 | JUMP.pri | jump to PRI |
| 81 | SWITCH v | v is the offset of a CASETBL. Jump to the address of the first record whose value equals PRI; none or count ≤ 0: jump to the default |
| 82 | CASETBL | the handler exists but only passes on to the next cell, the record count, as if it were an instruction: a crash [X C8] |

**Floored divide** (0x140160, 0x1401b8). With `rem(a, b)` and `quo(a, b)` the CPU's signed
divide (quotient toward zero, remainder with the sign of a; −2³¹ / −1 gives quotient −2³¹,
remainder 0):

```
r = rem( rem(n, d) + d , d )        # the sum wraps at 32 bits
q = quo( n − r , d )                # the difference wraps
```

For ordinary operands this is division rounded toward minus infinity with a remainder that has
the divisor's sign (−7 / 2 = −4 remainder 1). Near the ends of the range the wrap shows:
0x7fffffff / −0x80000000 gives quotient 1, remainder −1 [X B1].

The debug hook is never called and LINE has no other effect.

## 6. Natives

### 6.1 Calling convention

The script pushes the arguments right to left, then their size in bytes, executes SYSREQ, and
drops size + 4 bytes with STACK afterwards. SYSREQ:

1. machine cip = `next`, frm = FRM, hea = HEA, stk = STK.
2. `error = callback(machine, index, &PRI, address of [STK])`.
3. error ≠ 0 → machine stk = entry value, return error. Otherwise continue; PRI is what the
   callback stored, ALT, FRM, STK and HEA are untouched whatever the native did to the machine
   structure.

The default callback `scr_callNative` 0x141050 clears machine error, calls
`handler(machine, params)` where the handler address is the cell of native record `index`,
stores the handler's return value in PRI and returns machine error. It checks neither the
index nor that the record is bound: an unbound native is a jump to address 0 [X C7].

For the handler, `params[0]` is the argument size in bytes and `params[1]`… are the arguments
in source order. The handler's return register becomes PRI, also for handlers written without
a return value. No game handler sets the error word (`docs/script.md`).

### 6.2 Binding — `scr_registerNatives` 0x141310

Given a list of {name, handler} (zero-terminated, or with a count): for each native record of
the script whose cell is still 0, the first list entry with the same name (case-sensitive)
supplies the handler. A name that is not found leaves its record 0 and makes the routine
return 19 after it has gone through all records; otherwise it returns 0 [X A3].

### 6.3 Nested runs

Because the registers were saved, a native may call `scr_interpret` on the same machine
(`callScript` does, through `script_runByName`). The nested run starts from the saved stk and
hea, so its frames lie below the caller's stack; it has its own FRM = 0, ALT = 0 and
uninitialised PRI. When it returns, the caller continues with its own registers, but the
machine structure keeps what the nested run left in cip, frm, hea, stk, the line words and
the error word [X A5, C5].

## 7. Strings

A string argument is a script address. Handlers call `scr_getAddr` (which only applies the
check of section 3 to the saved registers, so negative addresses pass, and whose result they
ignore) and then `scr_getString` 0x141650, which copies to a C buffer without a length limit:

- first cell < 0x100 **as a signed number** → *unpacked*: one character per cell, the cell's
  low byte; the string ends at the first cell that is 0. A cell that is not 0 but has a zero
  low byte puts a zero byte into the copy and the copy goes on.
- otherwise → *packed*: four characters per cell, the first in the most significant byte; the
  string ends at the first zero byte.

A packed string whose first character is 0x80 or above has a negative first cell and is
therefore read as unpacked [X E2]. The compiler stores literals packed; the sentinel cell at
the stack top guarantees that a read starting inside the block ends inside the image.

`scr_setString` 0x140f10 (unused by the game): unpacked stores each character as a
sign-extended byte in its own cell and then a zero cell; packed first zeroes the cell at index
length / 4, copies the bytes and reverses the byte order of cells 0..length / 4, so a length
that is a multiple of 4 ends in a whole zero cell. `scr_strLen` 0x141568 returns the character
count for either form [X E1, E2].

Entry-point names are found by `scr_findEntry` 0x13eac8: a binary search with a byte-wise
unsigned compare; the middle is (first + last) / 2 rounded down. It returns 0 and the index,
or 19 and index 0x7fffffff. On a table that is not sorted it misses names that are there
[X A4, E4].

## 8. Errors

| Code | Raised by |
|---|---|
| 3 | entry, STACK, HEAP: less than 0x40 bytes between HEA and STK |
| 4 | BOUNDS |
| 5 | the six checked opcodes; `scr_getAddr` |
| 6 | opcode 0; the relocation pass (not reported by the loader) |
| 7 | entry, STACK: STK above the header's stack top |
| 8 | entry, HEAP: HEA negative |
| 9 | entry: no callback |
| 11 | SDIV, SDIV.alt, UDIV, UDIV.alt: divisor 0 |
| 16 | `scr_allot` (unused by the game) |
| 17, 18 | the loader |
| 19 | `scr_findEntry`, `scr_registerNatives` |
| 20 | entry: bad index |
| 22 | entry: code not relocated |
| any | HALT's operand; the error word set by a native |

`script_runByName` 0x1ed694 drops the code: the caller sees −1 for an unknown name, otherwise
the result word, which stays 0 unless the run stored one [X C6].

The other library routines are modelled too: `scr_allot` 0x1414f8 grants cells at the saved
heap top unless (stk − hea − size), **as an unsigned number**, is below 0x40 — so a request
larger than the free room is granted; `scr_release` 0x141550 lowers the heap top, never
raises it [X E3].

## 9. A shipped-script defect that reaches outside the machine

Some shipped entry points call a native declaring more argument bytes than they push, and then
drop the declared amount. Decoded examples [O]: `HUB.scr` code offsets 0xfbc–0xfd8 (PUSH.C 4,
SYSREQ.C `activateStore`, STACK 8, with no argument pushed) and `INNOVAT1.scr` 0x7e0–0x80c
(`givePlayerItem` with 12 bytes declared, two cells pushed).

What follows from sections 4 and 6:

- The handler's "argument" is the cell above the size cell — the caller's saved FRM, which is
  0 in an entry function [I].
- At the final RETN the stack pointer is 4 too high. RETN reads the argument size from the
  cell at the entry stack pointer instead of the cell below it, and stores entry value + 4 +
  that cell in machine stk. The first time the cell is the sentinel (0): **machine stk ends 4
  above the stack top** [X A5: 25 entry points in `HUB`, `HUB2`, `INNOVAT1`, `ISLGNOME`, on
  both sides].
- Every later run starts 4 higher. It still works: its two entry cells land on the sentinel
  and the cell below. But the next unbalanced run reads its "argument size" from the first
  word **after the image** and adds it to the stack pointer [I from the code; X A6 with zero
  bytes after the image]. What that word is in the game is [U]; `script.scr` is the last file
  of its lump in the four lumps available here. If it is 0 the stack pointer creeps up 4 bytes
  per such call and each run zeroes one more word behind the image; if it is large and
  positive, every later run of that level's scripts returns error 7 and does nothing; if it is
  negative, the next run writes its entry cells far outside the image.

A rebuild must decide what lies behind the block. The model raises `HostFault` at the read
past the image; give it an image with extra bytes appended to say what the memory holds.

Proposed patch (one word; **untested on a console or in PCSX2**; executed only in
`tools/ee_emu.py`):

| Id | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| SM1 | 0x0013fc24 | aef60018 | aeec0018 | RETN stores the run's entry stack pointer in machine +0x18 instead of the current one, so a run always leaves the saved stack pointer where it found it | the saved value is read only by natives and nested runs, after the native call has stored the current one again [O 0x140c54, 0x140cb8]; a script that depended on the drift would change (none of 1,828 entry points does, below) | no shared state is changed by the patch itself; each machine that applies it is protected |

In the emulator, with the new word (a one-off run, not part of `difftest_amx.py`): 3,656 runs (every entry point, two result sequences) give
the same native trace, error, result and memory as without it; the saved stack pointer moved
in 50 of them before and in none after; a chained pass over all 1,828 entry points ends every
run with the stack pointer at the top.

Proposed ledger row (for review, not added to FINDINGS.md): *Level scripts with unbalanced
native calls (`HUB`, `HUB2`, `INNOVAT1`, `ISLGNOME`; 25 entry points) raise the script
machine's saved stack pointer by 4 per call; from the second such call the amount read comes
from memory behind `script.scr`. Observed in the bytecode and executed in the emulator; effect
on a console unknown. Candidate cause of scripts going dead or memory behind the level lump
being overwritten after repeated store use in the hub. Patch SM1.*

## 10. Differences from the stock AMX

The comparison is with the published `amx.c` of Small 2.x / Pawn 3.x as I remember it; no
source of the 2002–2003 version was at hand, so "stock" below is [I].

| Here [O] | Stock |
|---|---|
| The machine structure has no heap-low word and no saved PRI / ALT / reset words; a run cannot be continued | later versions have them |
| Entry and STACK compare STK with the *header's* stp, which is `dat` too high | the data-relative stack top |
| Entry and HEAP test HEA < 0 | HEA below the heap's start |
| Entry index −2 is accepted as a table index | reserved for "continue" |
| The loader ignores the relocation result; opcodes are validated only there | later versions verify more at load |
| No debug hook call anywhere; LINE only stores two words | hook called when debugging is on |
| Address checks are signed; RET, JUMP.pri, CALL.pri, SCTRL do not validate anything | later versions use unsigned compares and check return addresses |
| BOUNDS is two signed compares | one unsigned compare |
| MOVS, CMPS, FILL have no address checks | checked in later versions |
| ALIGN tests a run-time little-endian flag (0x40335c, set by the loader) | compile-time |
| `scr_getString` decides packed / unpacked with a signed compare | unsigned |
| CASETBL has a handler that falls into the table | not executable |

The loader's second-load guard (flag 0x2000) and the 0x60-byte structure in front of the file
are the game's own arrangement [I].

## 11. What the differential test covers

`python3 tools/difftest_amx.py` (about 90 seconds). The original runs in `tools/ee_emu.py`
on a copy of the image; natives are stubs that are the same on both sides (name, argument
cells, and the string at every argument that is a legal, aligned, non-negative address, read
by the original's own `scr_getAddr` / `scr_getString`), returning the next value of a seeded
sequence. After each run it compares the native trace, the returned error, the result word,
the machine structure words and every byte of data, heap and stack.

| Id | Property | Size |
|---|---|---|
| T1–T3 | handler table, operand classes, null-machine call | 131 + 130 entries |
| A1 | `scr_load` on the shipped scripts | 120 |
| A2 | relocated code block byte for byte | 120 |
| A3 | `scr_registerNatives` (one name missing, then all) | 120 |
| A4 | `scr_findEntry` | 9,140 lookups |
| A5 | every entry point from the freshly loaded state, 5 result sequences each (all natives 0, all 1, three random) | 1,828 entry points, 9,140 runs |
| A6 | all entry points of a script in random order without reloading (256 zero bytes after the image on both sides) | 1,828 runs |
| B1 | 60 directed programs per opcode 0x01–0x82 with random operands; a `HostFault` from the model counts as a failure unless the program was made to leave the machine | 7,783 compared, 17 skipped |
| B2 | opcode 0 | 8 |
| B3 | negative addresses pass the address check | 20 |
| B4 | random straight-line programs with forward jumps | 2,806 compared, 194 skipped |
| C1–C5 | arguments, initial registers, entry index, entry checks, nested runs and native errors | 1,301 runs, 27 skipped |
| C6 | `script_runByName` against `Machine.call` | 80 images × 7 names |
| C7, C8 | an unbound native and an executed CASETBL crash as described | 2 |
| D1–D4 | header checks, refused opcodes, compact images, compact expansion | 1,290 images, 10 skipped |
| E1–E4 | string routines, `scr_getAddr`, `scr_allot`, `scr_release`, `scr_findEntry` on synthetic input | 1,950 cases |

All 29 properties pass. Half of the synthetic images have random words instead of zeroes in the
heap and stack room, and 1,024 bytes of the same content on both sides follow them, so that
writes at entry, the sentinel and stack pointers above the top are visible and comparable.

Coverage of the shipped scripts: all 120 scripts and all 1,828 entry points ran to their end
on both sides under every sequence: 10,968 runs, 362,066 instructions, 33,831 native calls,
43,158 string arguments, 1,909 nested runs through the original `callScript` handler. No
entry point was left out. They execute 51 opcodes; the synthetic programs execute all 131
(opcode 0 through B2, CASETBL through C8). 12 shipped runs end with error 4, none with another
error.

Not covered, and why:

- Anything the model answers with `HostFault` (sections 2.2 and 3): the "skipped" cases above.
  There the emulator's result reflects its own memory, not the machine. B3, C7 and C8 check
  three of the claims behind `HostFault`; the others (jumps to cells that are not
  instructions, unaligned accesses, addresses beyond the image) rest on reading the code [O].
- The built-in handlers themselves (only `callScript` runs for real) and everything the game
  does around a run.
- A console. The emulator executes the same machine code but is not hardware. The routines
  involved use only integer instructions, plus the C library's `memcpy`, `memcmp`, `strcmp`,
  `strcpy` and `strlen`, which the emulator runs as they are.
- Loops other than those of the shipped scripts (the synthetic programs only jump forward);
  public variables, libraries and the user-data routines (0x1411c8, 0x141240), which the game
  does not use and the model does not have.
- Opcodes whose effect could not be verified: none. Every handler was read, and each of the
  130 loadable opcodes is exercised by B1.

How sharp the test is was checked once by hand with 72 one-line changes to the model (wrong
signedness, missing wrap, wrong restore, wrong order and the like; the script is not in the
repository). The first pass missed nine real ones; they are the reason for the strict mode,
the non-zero memory, the bytes behind the image and properties B3 and C6. With those, 69
changes are caught; two change nothing observable (ALIGN with operand 4 is an exclusive-or
with 0; the relocator's return value is ignored by the loader) and one did not compile.

## 12. Corrections to `docs/script.md`

1. 1.2 and 1.4 say machine +0x18 is "restored to its entry value on every exit". It is not:
   see 4.3. RETN stores the current stack pointer; the entry, STACK and HEAP error returns
   store nothing.
2. 1.5: "error 7 when STK passes the top" — the comparison is with the header's field, `dat`
   bytes above the top (4.1 step 4). Error 3 at entry comes after the entry cells are written.
3. 1.5: the address check is signed, so negative addresses pass; it applies to six opcodes
   only (section 3).
4. 1.6: entry index −2 is accepted; PRI is uninitialised on entry.
5. 1.7: `scr_getString` tests the first cell as a signed number; a first character ≥ 0x80
   makes a packed string read as unpacked. `scr_getAddr` accepts negative addresses.
6. 1.9: SIGN.pri / SIGN.alt do not sign-extend, they only set bits 8–31 when bit 7 is set.
   UMUL is the same signed multiply instruction as SMUL. CASETBL has an executable handler
   that crashes. ALIGN is `^= 4 − v` for v < 4.
7. Built-in table: `activateStore` and `givePlayerItem` are called by some scripts with fewer
   pushed arguments than declared (section 9).
