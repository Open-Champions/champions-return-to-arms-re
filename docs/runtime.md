# Runtime: C library, C++ support, link-once functions, static initialisation

Area `runtime`, 0x3b0000–0x3e6000 (the tail of `.text`, which ends at 0x3e5c40). 1,460
functions, about 200 KB. Nothing here is game logic written by hand for this game, but
almost every game class has a few functions here, so the area is the key to the class
hierarchy and to what "the default behaviour" of a virtual slot is.

Everything below was read from the executable. Nothing was run when it was written. Since
then the software floating-point routines have been executed in `tools/ee_emu.py`
(`docs/spec/items.md`, `docs/spec/core.md`; marked **executed** in section 1), and the
project has a live game — the Play! emulator, which is not a PlayStation 2 and not PCSX2 — whose
runs are listed in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`.
Nothing in this document was looked at there. Statements are **Observed**
unless marked **Inferred** or **Unknown**. Names of functions outside the range are the
ones other areas assigned (`pool_free`, `mem_malloc`, `res_find`, ...).

## 1. Map of the range

| Addresses | Contents | How the boundary is known |
|---|---|---|
| 0x3b0000–0x3b0388 | tail of a function that starts at 0x3afe20 (frame-table sort, below the range) | Ghidra body range |
| 0x3b0398–0x3b1214 | exception frame registry and call-frame interpreter (GCC `frame.c`) | list head 0x9080d8, semaphore 0x5075d4, augmentation string "eh" |
| 0x3b1218–0x3b2bc8 | run-time type information (GCC `tinfo.cc`, `tinfo2.cc`) | the three initialisers write the tables whose own type names are `__user_type_info`, `__si_type_info`, `__class_type_info` |
| 0x3b2bd0–0x3b342c | `operator new/delete`, terminate/unexpected, exception records, bad_cast / bad_typeid throwers (GCC `new*.cc`, `exception.cc`) | callee chains into the unwinder below the range |
| 0x3b3430–0x3c153c | C library: newlib as shipped for the PS2 (vectorised string/memory functions, `_reent` structure) | first function is abort, last is ungetc; see section 4 |
| 0x3c1540–0x3c1604 | three small Sony-library helpers (0x3c1540, an empty function at 0x3c15a0, 0x3c15b0) | callers are all at 0x39cbc4–0x3a2f64 |
| 0x3c1608–0x3d227c | **game link-once functions**: one type-info getter per class, inline destructors, default virtual functions, a few unreferenced inline constructors and accessors | first function is the WeaponObject type-info getter; last is the SmokeGen type-info getter (0x3d2230) |
| 0x3d2280–0x3e5084 | link-once functions of the network libraries: virtual functions of classes compiled without type information, and template helpers called from 0x328000–0x39d000 | first address held by a table that has no type-info getter |
| 0x3e5088–0x3e5c3c | link-once functions of the C++ runtime itself: type-info getters and destructors for `type_info`, the `__*_type_info` family, `exception`, `bad_cast`, `bad_typeid`, `bad_exception`, `bad_alloc` | names in the descriptors |
| 0x3e5c40–0x3e6000 | not EE code: start of `.vutext` (vector-unit programs, 0x3e5c40–0x3e9980) | section table |

The order of the three link-once blocks follows link order: game objects first, network
libraries next, the compiler's own library last (**Inferred**).

### Below the range (not named here; they belong to the `netlib` address range)

| Addresses | What it looks like | Kind |
|---|---|---|
| 0x3a51b0–0x3aa958 | math library. 0x3a5ac8 is a 20-byte wrapper (17 callers) around a 2 KB kernel at 0x3a7930 | Inferred, not read |
| 0x3aa960–0x3acc48 | 64-bit integer multiply / divide / remainder helpers. 0x3aa960 is the 64×64 multiply `libc_rand` uses | Inferred |
| 0x3ad1c0, 0x3ad250, 0x3ad310 | global destructor runner, global constructor runner, and the once-only wrapper `main` calls first | Observed, section 6 |
| 0x3ad348 | pure-virtual handler (jumps to terminate). 216 table slots point at it | Observed |
| 0x3ad360–0x3ae680 | default terminate, per-thread exception context, exception allocation, throw and rethrow | Inferred from callers in 0x3b2bd0–0x3b33d8 |
| 0x3ae688–0x3afc80 | software floating point (the EE has no double-precision hardware). 0x3aef58 converts float to double (58 calling functions; the earlier version said "mostly float arguments to `libc_sprintf`", which is wrong — of its 97 call sites 5 feed `libc_sprintf`, 40 are followed by a double comparison, 19 by a multiply, 14 by an add and 6 by `libm_fmod`: game logic such as `loot_generateDrops` 0x100dec and `Creature_setStats` 0x10a7bc), 0x3af410 / 0x3af468 / 0x3af4d0 / 0x3af758 are double add / subtract / multiply / divide, 0x3af9b8 a double comparison, 0x3afb90 double to float. The identifications are no longer inferences: `docs/spec/items.md` §11 and `docs/spec/core.md` §9 **executed** the routines. Float → double is exact; multiply and double → float **truncate** (no rounding step); there are no denormals, and float exponent field 255 is an ordinary exponent (no NaN or infinity handling on the way in). A rebuild that uses the host's `double` gets different results | Executed (`docs/spec/core.md` §9, `docs/spec/items.md` §11); was: Inferred from shape and from use inside the number formatter and scanner |
| 0x3afc88–0x3b0388 | LEB128 readers and frame-table sort used by the frame registry | Inferred |

## 2. C++ support code (0x3b0398–0x3b342c)

Compiler: GCC 2.9x with the old C++ ABI, using DWARF2 call-frame tables for exceptions.

**Frame registry.** `eh_registerFrameInfo` (0x3b0398) puts a 24-byte record for the
executable's `.eh_frame` section (0x51e108) on a list; `eh_findFde` (0x3b0838) finds the
entry for a code address; `eh_frameStateFor` (0x3b1060) runs the frame program
(`eh_executeCfaInsn`, 0x3b0c10) to tell the unwinder how to restore registers. Only the
throw path uses it. No game function was seen with a catch clause; the
`.gcc_except_table` section is only 0x124 bytes (**Inferred**: exceptions are effectively
unused by the game; a thrown bad_typeid would end in terminate → abort).

**Type information.** A type descriptor is created lazily by a *getter* function. Three
initialisers exist:

| Function | GCC name | Used for |
|---|---|---|
| `rtti_initNoBaseTypeInfo` 0x3b12d8 | `__rtti_user` | classes with no base: GameObject, Skill, Spell, WeaponInterface, WeaponCommon, type_info, exception (7 call sites) |
| `rtti_initSingleBaseTypeInfo` 0x3b12b8 | `__rtti_si` | one public non-virtual base: 393 descriptors |
| `rtti_initMultiBaseTypeInfo` 0x3b1290 | `__rtti_class` | base list: Weapon1 (bases WeaponInterface at +0 and WeaponCommon at +4), Weapon2 and WeaponShield (base Weapon1) |
| `rtti_initPointerTypeInfo` 0x3b25c8 | `__rtti_ptr` | the three pointer types `P6PhProp`, `P4Prop`, `P8ItemProp` |

How the game uses it: the pattern "if the pointer is null call `cxx_throwBadTypeid`
(0x3b3338), else call the object's own getter through table entry 0, call the getter of
the wanted class directly, and compare with `rtti_typeInfoEquals` (0x3b1250)". That is
`typeid(*p) == typeid(Class)`, an **exact** class test: a derived class does not match.
There are 80 such comparison sites and 70 null-branch sites in game code (monsters 29,
creatures 17, objects 11, engine 7, gameplay 5, others 11).

`rtti_dynamicCast` (0x3b2690, GCC `__dynamic_cast`) has **no caller anywhere**. The game
contains no `dynamic_cast`; the belief that 0x3b1250 serves dynamic casts is wrong. The
cast engine (`rtti_dynamicCast2` 0x3b2718, `rtti_userTypeInfo_dyncast` 0x3b1370 and the
nine `do*` virtuals at 0x3b14b8–0x3b1eb0) is reached only from the exception runtime.

`rtti_typeInfoEquals` compares the two descriptor addresses and falls back to comparing
the name strings; it does not depend on where descriptors live.

**new / delete.** `cxx_operatorNew` (0x3b2bd0) calls `mem_malloc` (0x150680) and loops
through the new-handler (0x50c4f4) on failure, throwing bad_alloc when there is none. It
does not clear memory. `cxx_operatorDelete` (0x3b2d60) calls `mem_freeOrLibc` (0x1507a8).
Game objects do **not** use these: their inline destructors free through `pool_free`
(0x150470) and they are allocated with `pool_new`. The users of the global operators are
the network libraries, the C++ runtime's own classes, and one game function (section 8).

**Exceptions.** `cxx_pushException` (0x3b2ef0) builds a 0x30-byte record;
`cxx_throwBadCast` / `cxx_throwBadTypeid` build the object and throw;
`cxx_terminate` (0x3b2da0) calls the handler at 0x50c43c.

Not named in this block: 0x3b0af0 (a helper of the frame interpreter), the built-in type
getters in the gap 0x3b27a8–0x3b2bc8 (not in the Ghidra function table; 0x3b27a8 has one
caller, the rest none), 0x3b2e10 and 0x3b2e38 (two unreferenced accessors of the current
exception record).

## 3. C library (0x3b3430–0x3c153c)

It is newlib. Evidence: a pointer to a re-entrancy structure at 0x50c7e8 is passed to
`_r` variants of every function; the stream record is 0x58 bytes with four I/O hooks;
`rand` uses newlib's 64-bit multiplier; the allocator is Doug Lea's with a lock hook. The
string and memory functions are the Sony EE versions that use 128-bit multimedia
instructions when pointers are 16-byte aligned.

The archive members sit in **alphabetical order**, which is what made the identification
safe: abort, assert, atexit, atof, atoi, atol, bcmp, bcopy, bsearch, bzero, calloc, cfree,
errno, exit, fclose, fflush, findfp, fiprintf, fopen, fprintf, fputc, fputs, fread, free,
fseek, fstat, fvwrite, fwalk, fwrite, index, labs, makebuf, memalign, malloc, memchr,
memcmp, memcpy, memmove, memset, mlock, msize, mstats, mtrim, open, perror, printf,
putchar, puts, qsort, rand, realloc, refill, rget, rindex, sbrk, signal, snprintf,
sprintf, sscanf, stdio, strcasecmp, strcat, strchr, strcmp, strcoll, strcpy, strcspn,
strdup, strerror, strlen, (strlwr, strncasecmp, strncat), strncmp, strncpy, strpbrk,
strrchr, strspn, strstr, strtod, strtok, strtol, strtoul, strupr, (strxfrm), u_strerr,
valloc, vfiprintf, vfprintf, vfscanf, vprintf, vsnprintf, vsprintf, wbuf, write, wsetup
(0x3b3430–0x3be728); then the members pulled in by those: close, dtoa, flags, locale,
lseek, mallinfo/mallopt/malloc_stats (0x3be730–0x3c016c); then mbtowc, the big-number
helpers of `mprec.c`, pvalloc, read, isinf, isnan, ungetc (0x3c0170–0x3c153c). The four in
brackets were not read closely and are not named.

176 functions are named `libc_<newlib name without leading underscores>`. Each was checked
against its decompile; the ones with callers were also checked against two or more call
sites (argument order and use of the result). The beliefs in the brief are confirmed:
0x3b60c0 memset, 0x3b7ef0 sprintf, 0x3b7f88 sscanf, 0x3b8278 strcat, 0x3b8534 strcmp,
0x3b868c strcpy; 0x3b96a8 is **strstr**. Internal helpers that have no outside caller
(for example the `mprec.c` functions) are identified by shape and by their position in
the source order; their notes say so.

The functions game code actually uses, by number of call sites:

| Function | Address | Call sites | Where |
|---|---|---|---|
| `libc_sprintf` | 0x3b7ef0 | 581 | every area (ui 155, player 122, monsters 82) |
| `libc_sscanf` | 0x3b7f88 | 180 | ui 84, startup 46, audio-save 26 |
| `libc_memset` | 0x3b60c0 | 166 functions | everywhere |
| `libc_strcpy` | 0x3b868c | 140 functions | everywhere |
| `libc_strcmp` | 0x3b8534 | 138 functions | everywhere |
| `libc_memcpy` | 0x3b5f0c | 110 functions | everywhere |
| `libc_strlen` | 0x3b8dc4 | 75 functions | |
| `libc_strstr` | 0x3b96a8 | 51 functions | |
| `libc_strcasecmp` | 0x3b81a0 | 41 functions | |
| `libc_printf` | 0x3b6508 | 79 | 73 in the network library, 6 at 0x31e2b8–0x31ed10 |
| `libc_strcat`, `libc_strncmp`, `libc_strncpy` | 0x3b8278, 0x3b91d8, 0x3b9390 | 23–24 functions each | |
| `libc_strchr`, `libc_strrchr`, `libc_atoi` | 0x3b83a4, 0x3b95d8, 0x3b3550 | 8–14 functions each | |
| `libc_qsort` | 0x3b66e8 | 1 | 0x307e50, section 8 |
| `libc_rand` / `libc_srand` | 0x3b70f0 / 0x3b70d8 | 2 / 1 | section 8 |
| `libc_exit` | 0x3b3828 | 3 | 0x1721e4, 0x19ba98, 0x323a3c |

Memory: `libc_malloc` (0x3b5378) and `libc_free` (0x3b53d0) each have exactly one caller,
`mem_malloc` and `mem_freeOrLibc`, which use them only while `g_heapReady` (0x403a54) is
zero. After the game heap exists the C allocator is out of the picture. Every allocator
entry takes a recursive lock (`libc_malloc_lock` 0x3b6180: semaphore 0x5075d0, owner
thread 0x50cc48, depth 0x50cc4c).

The library contains no time, clock or date function. The range has no system-call
instruction of its own; it reaches the kernel only through the wrappers `WaitSema`,
`SignalSema`, `GetThreadId` and the file wrappers at 0x352fa8–0x3531b8 behind the stream
hooks.

## 4. Link-once functions (0x3c1608–0x3e5c3c)

### 4.1 Virtual table format, as far as this area shows it

A table is an array of 8-byte entries `{s16 delta, s16 0, u32 function}`:

| Entry | Content |
|---|---|
| 0 | class compiled with type information: `{0, type-info getter}`. Class compiled without it: `{offset, 0x3ad348}`, the pure-virtual handler |
| 1..n | the virtual functions; `tools/vtab.py` slot numbers |
| n+1 | `{0, 0}` terminator |

Tables lie back to back in `.data`:

| Addresses | Tables |
|---|---|
| 0x50cc58–0x51c83f | 386 game classes (first Creature, last SmokeGen at 0x51c7b0 with 16 functions) |
| 0x51c840–0x51df17 | 76 tables of classes without type information (network libraries). A secondary table of a class with several bases has a non-zero `delta`, header included: 0x51c918 has −8 in every entry, and a second one, 0x51cc08, has −4 in its header and slots 1–3 (0 in slots 4–5). Both go with the primary table 0x51c8d8 (the same three functions install all three; `SRSClient` in `docs/netlib.md`). The earlier version mentioned only 0x51c918 and spoke of a class with two bases |
| 0x51df18–0x51e107 | 16 tables of the C++ runtime's own classes |

Evidence for the no-type-info layout: every one of the 76 tables starts with a pointer to
0x3ad348, single `{0,0}` entries separate them, and a call through one of them
(0x3dc894) uses offset 8 for the first function, the same as for game classes.

### 4.2 Type-info getters and descriptors

406 getters, all in this area: 390 for game types, 16 for runtime classes. A getter tests
the first word of a static descriptor, initialises it on first use and returns its
address. Getters of root classes are called directly by other getters and by typeid
tests; the rest are reached mainly through table entry 0.

**Trap:** the compiler inlined base-class initialisation into many getters. The getter of
`beetleProjectile` (0x3c6600) contains the initialisers of Projectile, MissileWeapon and
beetleProjectile, in that order. The class a getter belongs to is the one initialised
**last** (the descriptor it returns). A tool that takes the first class-name string it
finds mislabels the table. `vtables.txt` had 24 such labels when this was written (it has
since been regenerated by the rule above and has none; `docs/issues/vtable-labels.md`):

| Table | vtables.txt said | Actual class |
|---|---|---|
| 0x50de28, 0x50deb8, 0x50df48, 0x50dfd8, 0x50e068, 0x50e100 | WorldPart | FallPlatform, FloorSwitch, Switch, DoorSecret, RollDoor, DoorSwing |
| 0x50e3d8, 0x50e470, 0x50e508, 0x50e5a0 | Projectile | beetleProjectile, playerProjectile, AnimatedMissile, MissileWeapon |
| 0x50e638, 0x50e758, 0x50e7e8, 0x50e878, 0x50e908, 0x50e998, 0x50ea28 | Projectile | IceBall, Root, LostSoul, OniBall, HolyBolt, Sparks, DummyDamager |
| 0x50f328, 0x50f3b8 | Prop | LooseIceChunk, GutChunk |
| 0x511b18, 0x511ba8, 0x511c38, 0x511cc8 | Prop | PhIce, PhProp, ItemProp, ParticleProp |
| 0x5108c8 | FireBeetle | FireFly |

The tables really labelled WorldPart, Projectile, Prop and FireBeetle are 0x511de8,
0x5120b8, 0x511d58 and 0x510a10. The old `vtables.txt` also lacked three tables: Weapon2
(0x50ce70), WeaponShield (0x50cda0) and PoisonRain (0x51aa68); and it listed SmokeGen with
748 entries because the scan ran on into the 76 no-type-info tables. The regenerated list
has the three tables, gives SmokeGen 16 functions and lists the 76 as `vt<address>`.

Class tree, from the base pointers in the descriptors: 97 classes derive directly from
GameObject, 74 from Creature, 92 from Skill, 55 from Spell, 24 from Projectile, 9 from
AutoProp, 6 from WorldPart. Roots: GameObject, Skill, Spell, WeaponInterface,
WeaponCommon (no table of its own), type_info, exception. The full list (class, kind,
descriptor, getter, bases, table) is produced by the script in section 4.7.

### 4.3 Destructors

259 inline destructors are named `Class_dtor`. Shape: write the class's table pointer
(for GameObject classes at +0x48, for Spell classes at +0x14), run member clean-up
(`handle_clear` for handle members), call the base destructor with flag 0, then free the
object if bit 0 of the flag argument is set. Game classes free with `pool_free`
(0x150470); runtime and network classes with `cxx_operatorDelete`. For GameObject classes
the destructor is slot 1 by convention and every slot-1 function in the area has this
shape. Spell classes also have it at slot 1 (`Spell_dtor` 0x3cafc8). **Skill has no
virtual destructor**: Skill slot 1 is a function returning 1; skills are static objects.

When a derived destructor has nothing of its own to do, the compiler dropped the store of
the derived table pointer, so the first table address seen in such a destructor is the
base class's (for example `ParticleProp_dtor` 0x3c2de8 writes the Prop table). Do not
identify a class from the table a destructor writes.

### 4.4 Shared defaults

48 functions are held by more than one class. They are named after the most basic class
that holds them (`GameObject_default_slot7`); in every case that class is an ancestor of
all the other holders.

GameObject (table 0x5122a8; slots 1 and 15 are not in this area):

| Slot | Address | Classes holding it | What it does |
|---|---|---|---|
| 2 | 0x3c7e88 | 138 | nothing (take damage) |
| 3 | 0x3c7e90 | 130 | nothing |
| 4 | 0x3c7e98 | 19 | nothing (run) |
| 5 | 0x3c7ea0 | 58 | nothing (draw) |
| 6 | 0x3c7ea8 | 120 | nothing (touched) |
| 7 | 0x3c7eb0 | 156 | nothing |
| 8, 9 | 0x3c7eb8, 0x3c7ec0 | 111 each | return 0 |
| 10 | 0x3c7ec8 | 156 | takes a 12-byte vector by value, does nothing |
| 11 | 0x3c7ef0 | 156 | nothing |
| 12 | 0x3c7ef8 | 156 | takes a 12-byte vector (third argument), does nothing |
| 13 | 0x3c7f20 | 117 | returns 0 (interact prompt) |
| 14 | 0x3c7f28 | 117 | nothing (interact) |
| 16 | 0x3c8120 | 138 | returns 0 |

The GameObject family has 232 tables, 76 of them Creature and its descendants. Slots 7,
10, 11 and 12 are held by all 156 classes outside the Creature branch: their only real
implementations are Creature's own (0x11a260, 0x11a3f0, 0x11a448, 0x11a290), so they are
creature-only operations declared on the base class. Slot 3 is overridden outside the
Creature branch by 26 classes (Timer, Counter, the door classes, MissileTrap,
TriggerParams, ...), slot 13 by 39 (levers, switches, doors, Savepoint, JumpGate, ...),
which fits "interact prompt" for 13 and suggests an activate/signal entry for 3
(**Inferred**).

Creature (table 0x50cc58): slot 16 returns the word at +0xc of the record at this+0x24;
slot 27 stores a 16-bit argument at +0x232; slots 33/34 get and set the float at +0x3c0
(the setter converts from a 16-bit integer); slot 37 returns the byte at +0x310; slot 38
returns the word at +0x14 of the record at this+0x24; slot 39 returns 0. Each is held by
67–76 classes except slot 27 (4).

Skill (table 0x512670, all 15 slots are in this area, 0x3c8218–0x3c88e4):

| Slot | Address | Holders | What it does |
|---|---|---|---|
| 1 | 0x3c8218 | 44 | returns 1 |
| 2, 3 | 0x3c8220, 0x3c8248 | 19, 93 | take a 12-byte vector, return 0 |
| 4 | 0x3c8270 | 6 | copies the text for key "no" into the caller's wide-string buffer |
| 5 | 0x3c82a8 | 19 | returns 1.0 |
| 6 | 0x3c82b8 | 92 | returns 0 |
| 7 | 0x3c82c0 | 22 | returns the blank icon, `res_find("icons.lmp", "icblank.tex")`; 71 skills have their own copy naming their icon |
| 8 | 0x3c82e4 | 93 | value range: takes a fraction, a flag and two output pointers; base = slot 10; outputs max(1, round(base ∓ base × fraction)); with the flag set the fraction is scaled by random numbers from the shared seed (section 8) |
| 9 | 0x3c85b0 | 4 | resets the five rows of the first level table |
| 10 | 0x3c85fc | 93 | value of row n at a level: 0 below the row's minimum level, else round(base + rate × levels above minimum) |
| 11 | 0x3c8690 | 93 | the same with a level cap and the alternate table when it is enabled |
| 12 | 0x3c87f0 | 93 | slot 10 if the object argument is a player (flag 0x40), else slot 11 |
| 13 | 0x3c8864 | 93 | the same test on the object owning a handle |
| 14 | 0x3c88dc | 93 | returns its argument |
| 15 | 0x3c88e4 | 93 | float of slot 10 for row 4 at the level slot 14 returns |

Spell (table 0x515ba0, 0x3cafc8–0x3cb054): slot 1 destructor, slot 2 takes a vector and
does nothing (2 holders), slot 3 does nothing (53), slot 4 returns 0 (54).

Vehicle slots 20–27 (0x3c9128–0x3c9160) do nothing; AutoObject slot 16 (0x3c9440)
returns the word at +0x90.

### 4.5 Functions held by a single class

140 functions. GameObject-family ones in slots 2, 4, 5, 15 are named `Class_takeDamage`,
`_run`, `_draw`, `_clone`; all others `Class_slotN` with what they do in the note when it
is a two-instruction stub. Groups worth knowing:

- `WeaponObject_slot1`–`slot24` (0x3c1660–0x3c1bd8) each forward the call to the same
  slot of the object at this+4 when that pointer is non-null; `WeaponObject_slot25`
  (0x3c1658) sets that pointer. WeaponObject is a holder that delegates to a
  WeaponInterface implementation (Weapon1, Weapon2 or WeaponShield).
- `Weapon1_slot2`–`7`, `Weapon2_slot2`–`8`, `WeaponShield_slot2`–`16` are small wrappers
  (names of the first pass; `Weapon1_slot2`, `Weapon2_slot2`, `Weapon2_slot6` and
  `Weapon2_slot8` have since been renamed `Weapon1_setFireWeapons`,
  `Weapon2_setFireWeapons`, `Weapon2_setShockWeapons` and `Weapon2_setElement`).
  `Weapon1_setFireWeapons` calls `creature_buildElementDamage` on the block at this+0x50 when its
  index argument is below 2; `Weapon2_setFireWeapons` does the same and repeats it for the block at
  this+0xe0 when the index is 0 or 2. The other slots have the same sizes and were not
  read.
- 71 `Skill<Name>_slot7` functions return that skill's icon from `icons.lmp`; the note
  gives the texture name. This is a quick skill → icon map.
- `Player_slot39` (0x3c3b40) is `player_getSkillRank` for the player's slot index
  (this+0x3c8); `Player_slot37` (0x3c3b18) reads a byte at +0x4c24 of the player record.

Unreferenced out-of-line copies of inline functions also sit in this block and are not
named: `GameObject` operator new/delete wrappers (0x3c7e50 → `pool_new`, 0x3c7e68 →
`pool_free`), three helpers around `GameObject_rand` (0x3c7f30, 0x3c7f60, 0x3c8030),
constructors of Weapon1 (0x3c1c80), Weapon2 (0x3c1ec8) and SpellArena (0x3d0bc4), and a
row of Creature accessors at 0x3c2658–0x3c272c.

### 4.6 Network-library block (0x3d2280–0x3e5084)

Classes here were compiled without type information, so they have no names. Functions
held by their tables are named mechanically `vt<table address>_slotN` or `_dtor` (63
names) so that a reader of a table dump can at least follow them. About 200 further
functions are template helpers called from 0x328000–0x39d000: array and list containers
with element sizes 0x10, 0x1c and 0xb8, a merge sort (0x3d3118–0x3d5fa0), a binary heap
(0x3e2034, 0x3e20e0), intrusive list insertion with assertions (0x3e30f8), a 16-bit
string compare (0x3d30c8). They are **not named**; they belong with the network library.
One of them, 0x3dcafc, stores the lobby clock value 0x564330 (see section 8).

### 4.7 How the mechanical names were produced

Scripts (kept in the agent scratch directory, not in the repository): `rtti.py` finds
every function that calls one of the descriptor initialisers, runs a small constant
propagation over it to get (descriptor, name string, base descriptor) for each call, takes
the last call as the function's own class, then scans `.data` for `{0, getter}` headers.
`linkonce.py` splits the no-type-info tables, collects for every function in the area the
(class, slot) pairs that hold it and applies the rules: getter → `Class_typeinfo`; one
class and destructor shape (tests bit 0 of the flag and calls a free function) or
GameObject slot 1 → `Class_dtor`; one class otherwise → `Class_<slot name>`; several
classes → `<most basic holder>_default_slotN`. Two-instruction stubs are described
automatically; the longer shared defaults were read by hand. Spot checks of random rows
against the disassembly found no mismatch.

## 5. Static initialisation

`.ctors` is at 0x3e9980: a −1 marker, 124 function pointers, a 0 terminator. `.dtors` is
at 0x3e9b78 with 9 pointers.

- `main` is 0x323dcc. Its first call is the once-only wrapper 0x3ad310 (flag 0x907f58),
  which calls the constructor runner 0x3ad250.
- The runner registers the frame section, counts the entries, calls them **from the last
  entry to the first** (0x3375a0 first, 0x11c180 last), then registers the destructor
  runner 0x3ad1c0 with `libc_atexit`.
- Every one of the 124 entries is a 32-byte wrapper that calls one per-source-file
  function with arguments (1, 0xffff); that function constructs the file's static
  objects when called with 1 and destroys them when called with 0. The 9 `.dtors`
  entries are the matching wrappers with 0. All of these lie outside this area
  (0x11c180–0x3375a0).

The two tables the brief asks about are **not filled by constructors**:

| Table | Finding | Evidence |
|---|---|---|
| script built-ins 0x403370 | plain initialised data: the name pointers and handler addresses are in the file image. Only one function takes its address (0x147a84) | file contents at 0x403370; `gxref` |
| skill table 0x41b170 | plain initialised data: index 0 is null, indices 1–101 point at static objects at 0x6e14d8–0x6e3fb8 in `.bss`, 0x68 bytes apart except one gap of 0x188. No store to the table was found | file contents; `gxref` shows reads and address-taking only |
| the Skill objects themselves | constructed by 0x16ac74 (2.9 KB, in the engine address range), which calls each skill class's constructor on its slot in turn (about 90 constructor calls). It is reached from `.ctors` entry 8, the wrapper 0x16b7d0 | decompile of 0x16ac74; `.ctors` contents |

So the skill objects exist before `main`'s own code runs and are never reallocated; their
addresses are the same on every machine.

## 6. Data structures

Type descriptor (static, in `.sbss` 0x564300–0x564340 for the roots and `.bss`
0x9080e0–0x90a428 for the rest):

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0 | char* | mangled class name (`8Creature`); zero until first use | every initialiser stores its name argument here; getters test this word |
| +4 | pointer | table of the descriptor's own class (0x51df78 no base, 0x51df48 single base, 0x51df18 base list, 0x51e090 pointer type) | 0x3b12b8, 0x3b12d8, 0x3b1290, 0x3b25c8 |
| +8 | pointer | single base: base descriptor. Base list: array of 8-byte entries | same |
| +0xc | u32 | base list: number of entries | 0x3b1290 |

Base-list entry (Weapon1's at 0x530110): `+0` base descriptor, `+4` packed word, low bits
the offset of the base inside the object (0 and 4 for Weapon1), top bits 01 for a public
base.

Skill object, as used by the shared defaults (size 0x68):

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x00 | char* | skill name | static initialiser 0x16ac74 stores a name string here |
| +0x0e | s16[5] | minimum level per row | 0x3c85b0, 0x3c85fc |
| +0x18 | s16[5] | base value per row | same |
| +0x24 | float[5] | increase per level above the minimum | same (reset value 2.0) |
| +0x38 | s16[5] | alternate table minimum level; negative = not used | 0x3c8690; initialised to −1 in 0x16ac74 |
| +0x42 | s16[5] | alternate base value | 0x3c8690 |
| +0x4c | float[5] | alternate increase per level | 0x3c8690 |
| +0x60 | pointer | virtual table | every Skill call site |

Spell object header, from `Spell_dtor` (0x3cafc8) and the SpellArena constructor copy
(0x3d0bc4): `+0` byte cleared, `+4` handle list head, `+8` word cleared, `+0xc`
constructor argument, `+0x10` random state (upper 16 bits of the shared seed after one
step), `+0x14` virtual table.

Frame registry record (24 bytes, list head 0x9080d8): `+0` lowest code address, `+4`
highest, `+8` frame section start, `+0xc` sorted entry array (or the section again before
sorting), `+0x10` entry count, `+0x14` next record (0x3b0398, 0x3b0838).

Exception record (0x30 bytes, 0x3b2ef0): `+0` matcher function (0x3b2e90), `+4` s16
language 4, `+6` s16 version 1, `+8` thrown object, `+0xc` its type-info getter, `+0x10`
cleanup function, `+0x14` caught flag, `+0x18` next record, `+0x20` s64 handler count,
`+0x28` original object.

C library re-entrancy structure (pointer at 0x50c7e8):

| Offset | Meaning | How known |
|---|---|---|
| +0 | errno | 0x3b3818 returns the structure address |
| +4, +8, +0xc | stdin, stdout, stderr stream pointers | 0x3b6508 uses +8, 0x3b3460 uses +0xc |
| +0x38, +0x3c | stdio-initialised flag, cleanup hook | 0x3b3d00 |
| +0x4c | big-number free lists | 0x3c0250 |
| +0x5c | `strtok` position | 0x3ba698 |
| +0xa8 | u64 `rand` state | 0x3b70d8, 0x3b70f0 |
| +0x148, +0x14c | atexit list head and first block (count at +4, 32 functions from +8) | 0x3b3498, 0x3b3828 |
| +0x1d4 | signal handler table (32 entries) | 0x3b79d0 |
| +0x1d8 | stream block list; the three standard streams are at +0x1e4, +0x23c, +0x294 | 0x3b3d00 |

Stream record (0x58 bytes): `+0` position, `+4` bytes left to read, `+8` space left to
write, `+0xc` s16 flags, `+0xe` s16 file number, `+0x10`/`+0x14` buffer and size, `+0x1c`
cookie, `+0x20`–`+0x2c` read / write / seek / close hooks, `+0x50` file offset, `+0x54`
owning re-entrancy structure (0x3b3af0, 0x3b8030–0x3b8180).

## 7. Functions that matter

| Address | Name | Why |
|---|---|---|
| 0x3b1250 | `rtti_typeInfoEquals` | every exact-class test in game code ends here |
| 0x3b3338 | `cxx_throwBadTypeid` | marks the null branch of those tests; reaching it would abort the game |
| 0x3b12b8 / 0x3b12d8 / 0x3b1290 | descriptor initialisers | starting point for rebuilding the class tree |
| 0x3c7e10, 0x3c2608, 0x3c81d8, 0x3c2830 | `GameObject_typeinfo`, `Creature_typeinfo`, `Skill_typeinfo`, `Spell_typeinfo` | getters called directly by most typeid tests |
| 0x3c7e88–0x3c8120 | `GameObject_default_slot*` | what an object does when its class overrides nothing |
| 0x3c82e4 | `Skill_default_slot8` | the only function in the area that advances the shared random seed |
| 0x3b2bd0 / 0x3b2d60 | `cxx_operatorNew` / `cxx_operatorDelete` | global allocation operators; not used for game objects |
| 0x3b70f0 / 0x3b70d8 | `libc_rand` / `libc_srand` | a fourth random generator, per machine (not the "fourth generator" of `docs/monsters.md` and `docs/skills.md`: that is the game's seed word 0x404468) |
| 0x3b66e8 | `libc_qsort` | one game caller |
| 0x3b3828 / 0x3b3430 | `libc_exit` / `libc_abort` | process end |

## 8. Per-machine state

The area holds no camera, pad, audio, menu or timer access. A scan of every address
loaded in the game link-once block (0x3c1608–0x3d2280) finds only table and descriptor
addresses, the shared seed (three sites) and one player-record byte. The items below are
the places where something machine-dependent starts in this area or passes through it.

| # | What | Kind | Addresses |
|---|---|---|---|
| P1 | The C library has its own random generator, separate from the three in `OVERVIEW.md` (the overview's table now has five rows and includes this generator and the second cosmetic seed 0x404468). Its state (re-entrancy structure +0xa8) starts at the library default and is reseeded only by `apicrypt_ctor` in the network library, with the lobby clock value 0x564330. It is therefore per machine | Observed | `libc_srand` 0x3b70d8 (caller 0x38c934), `libc_rand` 0x3b70f0 |
| P2 | `libc_rand` is called from game-side code once: the beam segment generator 0x192a40 (engine area) stores `rand() & 7` as a float in field +0x18 of each 0x1c-byte beam node, a countdown that 0x192e80 decrements before re-randomising the node. All other randomness in that function comes from the cosmetic seed, so this is cosmetic unless beam node positions feed a hit test | Observed for the call and the field; Inferred cosmetic | 0x192be8, 0x192e80 |
| P3 | The other `libc_rand` caller fills 32 random bytes in the network library | Observed | 0x38ca60 |
| P4 | `Skill_default_slot8` advances the shared seed 0x404464 four times per call when its flag argument is non-zero (the rounding step evaluates the random expression twice for each of the two bounds). It is a virtual function held by all 93 skill classes. Four sampled callers (0x2c3df8, 0x2e99d0, 0x24c5a4, 0x30a0b0) pass flag 0 and format description text. Whether any caller with a non-zero flag can run from drawing or menu code is not established | Observed for the function; Unknown for the callers (about 26 call sites through table offset 0x40/0x44, all in 0x24c5a4–0x31b990) | 0x3c8340, 0x3c8474 |
| P5 | Spell constructors step the shared seed once and keep the upper 16 bits at spell+0x10. Seen here in the unreferenced out-of-line copy of the SpellArena constructor; the copies in use are inlined in the skills area. Creating a spell on one machine only shifts the seed | Observed for 0x3d0bc4; Inferred for the inlined copies | 0x3d0bc4–0x3d0c1c |
| P6 | `cxx_operatorNew` returns memory that is not cleared (the C allocator does not clear, and `mem_allocTagged` makes no call to `libc_memset`). Its one game caller, `Vehicle_parseSeatsAndTurrets` 0x209254, allocates a 0x130-byte turret record and writes only +0, +4, +0xd, +0x110, +0x120–0x128 in the code that follows. Any other field read before it is written holds whatever the heap held, which can differ between machines | Observed for the allocation and the stores; Inferred hazard, needs the readers of the record checked | 0x3b2bd0, call at 0x209254 |
| P7 | Inline destructors of game classes free through `pool_free`, a last-in-first-out free list per size class. Object addresses therefore depend on the whole allocation history, including per-machine objects such as the prediction copy. Nothing in this area orders or hashes by address: `rtti_typeInfoEquals` compares addresses only for identity and falls back to names, `rtti_typeInfoBefore` (name order) has no caller, and the single `libc_qsort` call (0x307e50) sorts player indices with a comparator (0x307df0) on a 16-bit score with the index as tie-break, a total order | Observed for this area; address-dependent logic elsewhere is Unknown | 0x150470; 0x3b1250; 0x307df0 |
| P8 | No clock, timer or hardware register is read anywhere in the range: it contains no system-call instruction and no reference to an address in 0x10000000–0x13ffffff. Calls that leave the hand-read part go only to the exit routine 0x14fcc8, `mem_malloc`, `mem_freeOrLibc`, the semaphore and thread-id wrappers, the file wrappers at 0x352fa8–0x3531b8 and the integer, floating-point and unwinder helpers at 0x3aa960–0x3afe20 | Observed (scan of the instruction words and of all call targets) | 0x3b0000–0x3e5c40 |
| P9 | None of the shared defaults tests the prediction-copy flag 0x20000, and none needs to: the only ones that write object state are `Creature_default_slot27` (halfword +0x232) and `Creature_default_slot34` (float +0x3c0), plain setters whose callers decide. Their callers were not traced | Observed for the functions; Unknown for callers | 0x3c2688, 0x3c2708 |
| P10 | The frame registry and the allocator lock are guarded by semaphores, the allocator lock also by thread id. The loading screen runs on its own thread (`loadscreen_renderLoop`, mainloop area), so these are the only places in the range where two threads meet; no ordering dependence on game state was found | Observed for the locks; Inferred harmless | 0x3b6180, 0x3b0398 |

## 9. Open questions and what was not done

- **Skill slot 8 callers (P4).** Each of the ~26 call sites needs its flag argument and
  its caller classified as simulation or presentation. Skills area.
- **Turret record fields (P6).** List the reads of the 0x130-byte record made at
  0x209254 and compare with the fields written after allocation. Gameplay area.
- **Beam nodes (P2).** Whether beam node positions are used for anything but drawing.
  Engine area.
- The meaning of most GameObject, Creature and Skill slots is only described by what the
  default does. The overriders of slots 3, 7, 10, 11, 12 and 16 are the fastest route.
- The 76 network-library classes without type information are unnamed; their tables are
  at 0x51c840–0x51df17 and their constructors (the functions that store those table
  addresses) would name them. About 200 template helpers in 0x3d2c68–0x3e5084 are
  unnamed.
- Not named in the hand-read part: 0x3b0af0, the built-in type getters at
  0x3b27a8–0x3b2bc8, 0x3b2e10, 0x3b2e38, strlwr / strncasecmp / strncat (0x3b8f00–0x3b91d0),
  strxfrm (0x3bac98), 0x3c15a0 and 0x3c15b0 (maps a negative status to an 0x8107xxxx
  code; six call sites at 0x3a2ac4–0x3a2f64).
- Whether any game function has a catch clause was judged from the size of
  `.gcc_except_table` only; the table itself was not decoded.
- The math and software floating-point functions below 0x3b0000 are described from shape
  only and are not named.
- `symbols/runtime.tsv` already held 21 rows from another writer when this work started.
  Eighteen were correct and are kept with the same names. Three were replaced:
  0x3b12d8 `rtti_initClassTypeInfo` → `rtti_initNoBaseTypeInfo` (it writes the
  `__user_type_info` table, not `__class_type_info`; the base-list initialiser is
  0x3b1290), and `Creature_getTypeInfo` / `GameObject_getTypeInfo` →
  `Creature_typeinfo` / `GameObject_typeinfo` to match the other 388 getters.
