// mmi.h - the 128-bit multimedia instructions the game uses (the list in
// tools/ee_emu.py, MMI_IMPLEMENTED).  rs, rt, rd are register numbers.
#pragma once

union Q128 {
    u64 d[2]; u32 w[4]; u16 h[8]; u8 b[16];
    s32 sw[4]; s16 sh[8]; s8 sb[16];
};
static inline Q128 mmi_get(const Ctx* c, int i) { Q128 q; q.d[0] = c->r[i]; q.d[1] = c->rh[i]; return q; }
static inline void mmi_set(Ctx* c, int i, const Q128& q) { if (i) { c->r[i] = q.d[0]; c->rh[i] = q.d[1]; } }

#define MMI_LANES(name, field, count, expr) \
    static inline void mmi_##name(Ctx* c, int rd, int rs, int rt) { \
        Q128 a = mmi_get(c, rs), b = mmi_get(c, rt), o; \
        for (int i = 0; i < count; i++) { auto x = a.field[i]; auto y = b.field[i]; (void)x; (void)y; o.field[i] = (expr); } \
        mmi_set(c, rd, o); }

static inline s32 mmi_sat32(s64 v) { return v > INT32_MAX ? INT32_MAX : (v < INT32_MIN ? INT32_MIN : (s32)v); }
static inline s16 mmi_sat16(s32 v) { return v > 32767 ? 32767 : (v < -32768 ? -32768 : (s16)v); }
static inline s8 mmi_sat8(s32 v) { return v > 127 ? 127 : (v < -128 ? -128 : (s8)v); }

MMI_LANES(paddw, w, 4, x + y)
MMI_LANES(psubw, w, 4, x - y)
MMI_LANES(pcgtw, sw, 4, x > y ? -1 : 0)
MMI_LANES(pmaxw, sw, 4, x > y ? x : y)
MMI_LANES(paddh, h, 8, (u16)(x + y))
MMI_LANES(psubh, h, 8, (u16)(x - y))
MMI_LANES(pcgth, sh, 8, x > y ? -1 : 0)
MMI_LANES(pmaxh, sh, 8, x > y ? x : y)
MMI_LANES(paddb, b, 16, (u8)(x + y))
MMI_LANES(psubb, b, 16, (u8)(x - y))
MMI_LANES(pcgtb, sb, 16, x > y ? -1 : 0)
MMI_LANES(paddsw, sw, 4, mmi_sat32((s64)x + (s64)y))
MMI_LANES(psubsw, sw, 4, mmi_sat32((s64)x - (s64)y))
MMI_LANES(paddsh, sh, 8, mmi_sat16((s32)x + (s32)y))
MMI_LANES(psubsh, sh, 8, mmi_sat16((s32)x - (s32)y))
MMI_LANES(paddsb, sb, 16, mmi_sat8((s32)x + (s32)y))
MMI_LANES(psubsb, sb, 16, mmi_sat8((s32)x - (s32)y))
MMI_LANES(pceqw, w, 4, x == y ? 0xFFFFFFFFu : 0)
MMI_LANES(pminw, sw, 4, x < y ? x : y)
MMI_LANES(pceqh, h, 8, x == y ? 0xFFFF : 0)
MMI_LANES(pminh, sh, 8, x < y ? x : y)
MMI_LANES(pceqb, b, 16, x == y ? 0xFF : 0)
MMI_LANES(padduw, w, 4, (u64)x + y > 0xFFFFFFFFull ? 0xFFFFFFFFu : x + y)
MMI_LANES(psubuw, w, 4, x < y ? 0 : x - y)
MMI_LANES(padduh, h, 8, (u32)x + y > 0xFFFF ? 0xFFFF : (u16)(x + y))
MMI_LANES(psubuh, h, 8, x < y ? 0 : (u16)(x - y))
MMI_LANES(paddub, b, 16, (u32)x + y > 0xFF ? 0xFF : (u8)(x + y))
MMI_LANES(psubub, b, 16, x < y ? 0 : (u8)(x - y))

// PEXTL* / PEXTU*: lanes of rt and rs from one half, interleaved, rt in the even positions
#define MMI_EXT(name, field, half, base) \
    static inline void mmi_##name(Ctx* c, int rd, int rs, int rt) { \
        Q128 a = mmi_get(c, rs), b = mmi_get(c, rt), o; \
        for (int i = 0; i < half; i++) { o.field[2 * i] = b.field[base + i]; o.field[2 * i + 1] = a.field[base + i]; } \
        mmi_set(c, rd, o); }
MMI_EXT(pextlw, w, 2, 0)
MMI_EXT(pextlh, h, 4, 0)
MMI_EXT(pextlb, b, 8, 0)
MMI_EXT(pextuw, w, 2, 2)
MMI_EXT(pextuh, h, 4, 4)
MMI_EXT(pextub, b, 8, 8)

// PPAC*: the low half of every double-width lane; rt fills the low 64 bits
#define MMI_PAC(name, field, half) \
    static inline void mmi_##name(Ctx* c, int rd, int rs, int rt) { \
        Q128 a = mmi_get(c, rs), b = mmi_get(c, rt), o; \
        for (int i = 0; i < half; i++) { o.field[i] = b.field[2 * i]; o.field[half + i] = a.field[2 * i]; } \
        mmi_set(c, rd, o); }
MMI_PAC(ppacw, w, 2)
MMI_PAC(ppach, h, 4)
MMI_PAC(ppacb, b, 8)

static inline void mmi_qfsrv(Ctx* c, int rd, int rs, int rt) {
    Q128 a = mmi_get(c, rs), b = mmi_get(c, rt), o;
    u8 bytes[32];
    memcpy(bytes, b.b, 16);
    memcpy(bytes + 16, a.b, 16);
    memcpy(o.b, bytes + (c->sa & 15), 16);
    mmi_set(c, rd, o);
}
static inline void mmi_pcpyld(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = c->r[rt]; o.d[1] = c->r[rs]; mmi_set(c, rd, o);
}
static inline void mmi_pcpyud(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = c->rh[rs]; o.d[1] = c->rh[rt]; mmi_set(c, rd, o);
}
static inline void mmi_pand(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = c->r[rs] & c->r[rt]; o.d[1] = c->rh[rs] & c->rh[rt]; mmi_set(c, rd, o);
}
static inline void mmi_pxor(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = c->r[rs] ^ c->r[rt]; o.d[1] = c->rh[rs] ^ c->rh[rt]; mmi_set(c, rd, o);
}
static inline void mmi_por(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = c->r[rs] | c->r[rt]; o.d[1] = c->rh[rs] | c->rh[rt]; mmi_set(c, rd, o);
}
static inline void mmi_pnor(Ctx* c, int rd, int rs, int rt) {
    Q128 o; o.d[0] = ~(c->r[rs] | c->r[rt]); o.d[1] = ~(c->rh[rs] | c->rh[rt]); mmi_set(c, rd, o);
}
static inline void mmi_pcpyh(Ctx* c, int rd, int rs, int rt) {
    (void)rs;
    Q128 b = mmi_get(c, rt), o;
    for (int i = 0; i < 4; i++) { o.h[i] = b.h[0]; o.h[4 + i] = b.h[4]; }
    mmi_set(c, rd, o);
}
// kind: 0 shift left, 1 logical right, 2 arithmetic right
static inline void mmi_shift_h(Ctx* c, int rd, int rt, unsigned amount, int kind) {
    Q128 b = mmi_get(c, rt), o;
    amount &= 15;
    for (int i = 0; i < 8; i++)
        o.h[i] = kind == 0 ? (u16)(b.h[i] << amount) : kind == 1 ? (u16)(b.h[i] >> amount) : (u16)(b.sh[i] >> amount);
    mmi_set(c, rd, o);
}
static inline void mmi_shift_w(Ctx* c, int rd, int rt, unsigned amount, int kind) {
    Q128 b = mmi_get(c, rt), o;
    for (int i = 0; i < 4; i++)
        o.w[i] = kind == 0 ? b.w[i] << amount : kind == 1 ? b.w[i] >> amount : (u32)(b.sw[i] >> amount);
    mmi_set(c, rd, o);
}
// PLZCW: per 32-bit half of the low 64 bits, leading sign bits minus one; only the low
// 64 bits of rd are written
static inline void mmi_plzcw(Ctx* c, int rd, int rs) {
    u64 out = 0;
    for (int half = 0; half < 2; half++) {
        u32 v = (u32)(c->r[rs] >> (32 * half));
        if (v & 0x80000000u) v = ~v;
        u32 n = v ? (u32)__builtin_clz(v) - 1 : 31;
        out |= (u64)n << (32 * half);
    }
    if (rd) c->r[rd] = out;
}
