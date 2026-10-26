#!/usr/bin/env python3
"""reloc_test.py - synthetic checks of reloc.apply (recomp.py --reloc): the statements it rewrites, compiled and run.

For lui + addiu, lui + ori and lui + a load / store, each with a table address and a delta (positive, negative, and
ones whose sum carries or borrows across the 16-bit immediate and the 64 KB upper half), the rewritten statement must
form exactly (address + delta) as a sign-extended 32-bit MIPS value.  Needs a C++ compiler (c++).

  python3 -B tools/recomp/reloc_test.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recomp  # noqa: E402
import reloc   # noqa: E402

LUI, ADDIU, ORI, LW, SW = 0x0F, 0x09, 0x0D, 0x23, 0x2B


def word(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def cases():
    addresses = [0x402b3b, 0x4d8af0, 0x5bf838, 0x41bfd8, 0x40fff0, 0x410000, 0x41fffc]
    deltas = [0, 0x10, -0x10, 0x8000, -0x8000, 0x10000, -0x10000, 0x88000 - 0x4d8af0, 0x30000 - 0x879ec0,
              0x90000 - 0x400010, 0x7FFF0000 - 0x410000]
    out = []
    for a in addresses:
        hi, lo = (a + 0x8000) >> 16, a & 0xFFFF            # lui/addiu: the immediate is signed
        for d in deltas:
            out.append(('addiu', [word(LUI, 0, 4, hi), word(ADDIU, 4, 4, lo)], a, d, 4))
            out.append(('lw', [word(LUI, 0, 4, hi), word(LW, 4, 5, lo)], a, d, None))
            out.append(('sw', [word(LUI, 0, 4, hi), word(SW, 4, 5, lo)], a, d, None))
            if a & 0xFFFF == lo and (a >> 16) << 16 | lo == a:
                out.append(('ori', [word(LUI, 0, 4, a >> 16), word(ORI, 4, 4, a & 0xFFFF)], a, d, 4))
    return out


def main():
    src = ['#include <cstdint>', '#include <cstdio>', 'typedef uint64_t u64; typedef int64_t s64; typedef uint32_t u32; typedef int32_t s32; typedef uint8_t u8;',
           '#define SX32(x) ((u64)(s64)(s32)(x))', 'struct Ctx { u64 r[32]; };', 'static u32 g_reloc[32];', 'static u32 g_seen;',
           'static u64 LD32(u32 a) { g_seen = a; return 0; }', 'static void ST32(u32 a, u32) { g_seen = a; }', 'int main() {',
           '    Ctx cc = {}; Ctx* c = &cc; int bad = 0;']
    expected = []
    for n, (kind, words, address, delta, reg) in enumerate(cases()):
        lines = []
        for w in words:
            text = recomp._simple_plain(0, w)
            if w >> 26 != LUI:
                moved = reloc.apply(0, w, text, 0, recomp.ea)
                if moved is None:
                    print('FAIL %s 0x%x %+d: not rewritten (%s)' % (kind, address, delta, text))
                    return 1
                text = moved
            lines.append(text)
        want = (address + delta) & 0xFFFFFFFF
        want64 = want | (0xFFFFFFFF00000000 if want & 0x80000000 else 0)
        src.append('    { g_reloc[0] = 0x%xu; g_seen = 0; %s' % (delta & 0xFFFFFFFF, ' '.join(lines)))
        got = 'c->r[%d]' % reg if reg else '(u64)g_seen'
        cmp = '0x%xull' % (want64 if reg else want)
        src.append('      if (%s != %s) { printf("FAIL %s 0x%x %+d: 0x%%llx, wanted 0x%x\\n", (unsigned long long)%s); bad++; } }'
                   % (got, cmp, kind, address, delta, want, got))
        expected.append(n)
    src += ['    printf("%d cases, %d wrong\\n", ' + str(len(expected)) + ', bad);', '    return bad != 0;', '}']
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = os.path.join(tmp, 't.cpp'), os.path.join(tmp, 't')
        with open(cpp, 'w') as f:
            f.write('\n'.join(src) + '\n')
        r = subprocess.run(['c++', '-std=c++17', '-O1', '-w', cpp, '-o', exe], capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-3000:])
            return 1
        r = subprocess.run([exe], capture_output=True, text=True)
        print(r.stdout.strip())
        return r.returncode


if __name__ == '__main__':
    sys.exit(main())
