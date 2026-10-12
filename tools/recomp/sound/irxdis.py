#!/usr/bin/env python3
"""Disassemble an I/O-processor module (.IRX: a relocatable MIPS-I ELF).

  python3 -I -B tools/recomp/sound/irxdis.py MODULE.IRX [--out FILE]

Prints .text with relocations applied for display (the module is linked at 0), local
symbols when the module carries a symbol table, and the names of the imported functions
(import tables in .text: magic 0x41e00000, library name, then `jr ra; li zero, N` stubs).
Data sections are dumped as words.  Standard library only.  The listing is derived from
the game's disc: keep it under local/, never under docs/ or tools/.
"""
import struct, sys

REG = "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split()

# ordinals of the libraries these modules import (Sony's fixed export tables)
IMPORTS = {
    "libsd": {4: "sceSdInit", 5: "sceSdSetParam", 6: "sceSdGetParam", 7: "sceSdSetSwitch", 8: "sceSdGetSwitch", 9: "sceSdSetAddr", 10: "sceSdGetAddr", 11: "sceSdSetCoreAttr", 12: "sceSdGetCoreAttr", 13: "sceSdNote2Pitch", 14: "sceSdPitch2Note", 15: "sceSdProcBatch", 16: "sceSdProcBatchEx", 17: "sceSdVoiceTrans", 18: "sceSdBlockTrans", 19: "sceSdVoiceTransStatus", 20: "sceSdBlockTransStatus", 21: "sceSdSetTransCallback", 22: "sceSdSetIRQCallback", 23: "sceSdSetEffectAttr", 24: "sceSdGetEffectAttr", 25: "sceSdClearEffectWorkArea", 26: "sceSdSetTransIntrHandler", 27: "sceSdSetSpu2IntrHandler", 28: "sceSdGetTransIntrHandlerArgument", 29: "sceSdGetSpu2IntrHandlerArgument", 30: "sceSdStopTrans", 31: "sceSdCleanEffectWorkArea", 32: "sceSdSetEffectMode", 33: "sceSdSetEffectModeParams"},
    "thbase": {4: "CreateThread", 5: "DeleteThread", 6: "StartThread", 20: "GetThreadId",
               24: "SleepThread", 25: "WakeupThread", 26: "iWakeupThread", 33: "DelayThread",
               36: "USec2SysClock", 39: "SetAlarm", 40: "iSetAlarm", 41: "CancelAlarm",
               42: "iCancelAlarm"},
    "sifcmd": {14: "sceSifInitRpc", 17: "sceSifRegisterRpc", 18: "sceSifCallRpc",
               19: "sceSifBindRpc", 21: "sceSifSetRpcQueue", 22: "sceSifGetNextRequest",
               23: "sceSifExecRequest", 24: "sceSifRpcLoop", 12: "sceSifSendCmd",
               10: "sceSifAddCmdHandler"},
    "intrman": {4: "RegisterIntrHandler", 5: "ReleaseIntrHandler", 6: "EnableIntr",
                7: "DisableIntr", 8: "CpuDisableIntr", 9: "CpuEnableIntr",
                17: "CpuSuspendIntr", 18: "CpuResumeIntr", 23: "QueryIntrContext"},
    "sysclib": {12: "memcpy", 14: "memset", 19: "sprintf", 23: "strcpy", 27: "strlen"},
    "stdio": {4: "printf"},
    "modload": {7: "LoadModule", 10: "LoadModuleWithOption?"},
    "thsemap": {4: "CreateSema", 5: "DeleteSema", 6: "SignalSema", 7: "iSignalSema",
                8: "WaitSema", 9: "PollSema"},
    "sysmem": {4: "AllocSysMemory", 5: "FreeSysMemory"},
    "loadcore": {6: "RegisterLibraryEntries", 5: "FlushDcache", 4: "FlushIcache"},
    "sifman": {7: "sceSifSetDma", 8: "sceSifDmaStat", 5: "sceSifInit"},
}


def dis(w, pc, sym):
    op, rs, rt, rd, sa, fn = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, (w >> 6) & 31, w & 63
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    R = REG
    def tgt(a):
        return sym.get(a, "0x%x" % a)
    if w == 0:
        return "nop"
    if op == 0:
        if fn in (0, 2, 3):
            return "%s %s, %s, %d" % ({0: "sll", 2: "srl", 3: "sra"}[fn], R[rd], R[rt], sa)
        if fn in (4, 6, 7):
            return "%s %s, %s, %s" % ({4: "sllv", 6: "srlv", 7: "srav"}[fn], R[rd], R[rt], R[rs])
        if fn == 8:
            return "jr %s" % R[rs]
        if fn == 9:
            return "jalr %s" % R[rs]
        if fn == 12:
            return "syscall"
        if fn == 13:
            return "break"
        if fn in (16, 18):
            return "%s %s" % ({16: "mfhi", 18: "mflo"}[fn], R[rd])
        if fn in (17, 19):
            return "%s %s" % ({17: "mthi", 19: "mtlo"}[fn], R[rs])
        if fn in (24, 25, 26, 27):
            return "%s %s, %s" % ({24: "mult", 25: "multu", 26: "div", 27: "divu"}[fn], R[rs], R[rt])
        names = {32: "add", 33: "addu", 34: "sub", 35: "subu", 36: "and", 37: "or", 38: "xor",
                 39: "nor", 42: "slt", 43: "sltu"}
        if fn in names:
            if fn == 33 and rt == 0:
                return "move %s, %s" % (R[rd], R[rs])
            return "%s %s, %s, %s" % (names[fn], R[rd], R[rs], R[rt])
    elif op == 1:
        n = {0: "bltz", 1: "bgez", 16: "bltzal", 17: "bgezal"}.get(rt)
        if n:
            return "%s %s, %s" % (n, R[rs], tgt(pc + 4 + simm * 4))
    elif op in (2, 3):
        return "%s %s" % ("j" if op == 2 else "jal", tgt((pc & 0xF0000000) | ((w & 0x3FFFFFF) << 2)))
    elif op in (4, 5):
        return "%s %s, %s, %s" % ("beq" if op == 4 else "bne", R[rs], R[rt], tgt(pc + 4 + simm * 4))
    elif op in (6, 7):
        return "%s %s, %s" % ("blez" if op == 6 else "bgtz", R[rs], tgt(pc + 4 + simm * 4))
    elif op in (8, 9, 10, 11):
        n = {8: "addi", 9: "addiu", 10: "slti", 11: "sltiu"}[op]
        if op == 9 and rs == 0:
            return "li %s, %d" % (R[rt], simm)
        return "%s %s, %s, %d" % (n, R[rt], R[rs], simm)
    elif op in (12, 13, 14):
        return "%s %s, %s, 0x%x" % ({12: "andi", 13: "ori", 14: "xori"}[op], R[rt], R[rs], imm)
    elif op == 15:
        return "lui %s, 0x%x" % (R[rt], imm)
    elif op == 16:
        if rs == 0:
            return "mfc0 %s, $%d" % (R[rt], rd)
        if rs == 4:
            return "mtc0 %s, $%d" % (R[rt], rd)
        if rs == 16 and fn == 16:
            return "rfe"
    else:
        names = {32: "lb", 33: "lh", 34: "lwl", 35: "lw", 36: "lbu", 37: "lhu", 38: "lwr",
                 40: "sb", 41: "sh", 42: "swl", 43: "sw", 46: "swr"}
        if op in names:
            return "%s %s, %d(%s)" % (names[op], R[rt], simm, R[rs])
    return ".word 0x%08x" % w


def main():
    path = sys.argv[1]
    out = sys.stdout
    if "--out" in sys.argv:
        out = open(sys.argv[sys.argv.index("--out") + 1], "w")
    d = open(path, "rb").read()
    shoff, = struct.unpack_from("<I", d, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", d, 0x2E)
    sh = [struct.unpack_from("<10I", d, shoff + i * shentsize) for i in range(shnum)]
    strs = sh[shstrndx]
    def sname(i):
        o = strs[4] + sh[i][0]
        return d[o:d.index(b"\0", o)].decode()
    sec = {sname(i): sh[i] for i in range(shnum)}
    text = sec[".text"]
    toff, tsize, tbase = text[4], text[5], text[3]
    sym = {}
    if ".symtab" in sec:
        st, strt = sec[".symtab"], sec[".strtab"]
        for i in range(st[5] // 16):
            n, v, sz, info, other, shndx = struct.unpack_from("<IIIBBH", d, st[4] + i * 16)
            o = strt[4] + n
            name = d[o:d.index(b"\0", o)].decode()
            if name and shndx not in (0, 0xFFF1) and (info & 15) in (0, 1, 2) and not name.startswith(("gcc2", "__gnu")):
                sym.setdefault(v, name)
    # import tables
    words = list(struct.unpack_from("<%dI" % (tsize // 4), d, toff))
    i = 0
    while i < len(words):
        if words[i] == 0x41E00000 and i + 5 < len(words):
            lib = d[toff + i * 4 + 12: toff + i * 4 + 20].split(b"\0")[0].decode()
            sym.setdefault(tbase + i * 4, lib + "_stub")
            j = i + 5
            while j + 1 < len(words) and words[j] == 0x03E00008 and (words[j + 1] >> 16) == 0x2400:
                n = words[j + 1] & 0xFFFF
                sym.setdefault(tbase + j * 4, IMPORTS.get(lib, {}).get(n, "%s_%d" % (lib, n)))
                j += 2
            i = j
        else:
            i += 1
    # relocations: note HI16/LO16 pairs so the listing can show the address formed
    notes = {}
    if ".rel.text" in sec:
        r = sec[".rel.text"]
        hi = None
        for k in range(r[5] // 8):
            off, info = struct.unpack_from("<II", d, r[4] + k * 8)
            typ = info & 0xFF
            w = words[off // 4]
            if typ == 5:
                hi = (off, (w & 0xFFFF) << 16)
            elif typ == 6 and hi:
                lo = w & 0xFFFF
                lo = lo - 0x10000 if lo & 0x8000 else lo
                a = (hi[1] + lo) & 0xFFFFFFFF
                notes[off] = "-> 0x%x %s" % (a, sym.get(a, ""))
            elif typ == 2:
                notes[off] = "-> word 0x%x %s" % (w, sym.get(w, ""))
    print("# %s  .text 0x%x bytes at 0x%x" % (path.split("/")[-1], tsize, tbase), file=out)
    for i, w in enumerate(words):
        pc = tbase + i * 4
        if pc in sym:
            print("\n%s:" % sym[pc], file=out)
        line = "%06x: %s" % (pc, dis(w, pc, sym))
        if pc - tbase in notes:
            line = "%-44s ; %s" % (line, notes[pc - tbase])
        print(line, file=out)
    for name in (".rodata", ".data"):
        if name in sec:
            s = sec[name]
            print("\n# %s 0x%x bytes at 0x%x" % (name, s[5], s[3]), file=out)
            for o in range(0, s[5] & ~3, 16):
                ws = struct.unpack_from("<%dI" % (min(16, s[5] - o) // 4), d, s[4] + o)
                raw = d[s[4] + o: s[4] + o + 16]
                txt = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
                print("%06x: %s  %s" % (s[3] + o, " ".join("%08x" % x for x in ws), txt), file=out)
    for name in (".bss",):
        if name in sec:
            print("\n# .bss 0x%x bytes at 0x%x" % (sec[name][5], sec[name][3]), file=out)


if __name__ == "__main__":
    main()
