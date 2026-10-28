// Authored callbacks and guest memory exercise the production wrappers; no game input or translated code.
#include "rt.h"
#include "cinematic.h"
#include "partyscale.h"
#include "../net2/hooks.h"

#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

static std::vector<u8> memory(RAM_SIZE);
u8* g_ram = memory.data();
static bool hardcore = false;
namespace soulscombat { bool active() { return hardcore; } }
static u32 rank = 0;
void rt_call(Ctx* c, u32 target) { if (target != 0x10d940) std::abort(); c->r[2] = rank; }
RecompFn rt_replace_function(u32, RecompFn) { return nullptr; }

static int checks = 0, failures = 0, calls = 0, seen_start = 0;
static float seen_hp, seen_damage, seen_exp;
static u32 seen_players;
static u32 word(u32 a) { u32 v; std::memcpy(&v, g_ram + a, 4); return v; }
static void put(u32 a, u32 v) { std::memcpy(g_ram + a, &v, 4); }
static u32 bits(float v) { u32 n; std::memcpy(&n, &v, 4); return n; }
static float number(u32 n) { float v; std::memcpy(&v, &n, 4); return v; }
static void check(bool ok, const char* text) {
    ++checks;
    if (!ok) { ++failures; std::fprintf(stderr, "FAIL: %s\n", text); }
}
void orig_00199944(Ctx* c) {
    ++calls;
    if (word(0x41bfd8 + 0xc) & 0x800) { ++seen_start; g_ram[0x44fcec] = 1; }
    c->r[2] ^= 0x12345678u;
}
void orig_0010a620(Ctx* c) {
    ++calls;
    seen_hp = number(c->f[12]); seen_damage = number(c->f[14]); seen_exp = number(c->f[16]);
    seen_players = word(0x4d8ae0);
    put((u32)c->r[4] + 0x22c, bits(seen_hp * 100));
    c->r[2] ^= 0xabcdef01u;
}
void fn_00199944(Ctx*);
void fn_0010a620(Ctx*);

static void off_identity(RecompFn wrapped, RecompFn original, const char* text) {
    for (size_t k = 0; k < memory.size(); ++k) memory[k] = (u8)(k * 37 + (k >> 8));
    Ctx start{};
    for (int k = 0; k < 32; ++k) { start.r[k] = 123456789u * (k + 1); start.f[k] = bits(1.0f + k); }
    start.r[4] = 0x110000;
    auto before = memory;
    Ctx expected = start;
    original(&expected);
    auto after = memory;
    memory = before;
    g_ram = memory.data();
    Ctx actual = start;
    wrapped(&actual);
    check(memory == after && !std::memcmp(&actual, &expected, sizeof actual), text);
}
int main() {
    check(RAM_SIZE == 0x02000000u, "ordinary fixture uses 32 MB");
    check(partyscale_hook::figure && partyscale_hook::setting && partyscale_hook::poise_limit,
          "production scaling registers its combat hooks");
    off_identity(fn_00199944, orig_00199944, "cinematic off: full RAM and Ctx equal direct original");
    off_identity(fn_0010a620, orig_0010a620, "Hardcore off: full RAM and Ctx equal direct original");
    std::fill(memory.begin(), memory.end(), 0);
    cinematic::want(true); cinematic::blank(1);
    check(cinematic::active(), "offline requested hold mode becomes active");
    put(0x4d8ae0, 2); g_ram[0x44fcd0] = 1;
    Ctx c{};
    seen_start = 0;
    bool early = false, restored = true;
    for (u32 tick = 0; tick < 70; ++tick) {
        put(0x44fdcc, tick);
        put(0x41bfd8 + 8, 0x800);
        put(0x41bfd8 + 0x58 + 8, tick >= 10 ? 0x800 : 0);
        put(0x41bfd8 + 0xc, 0x812);
        put(0x41bfd8 + 0x58 + 0xc, 0x834);
        fn_00199944(&c);
        restored &= word(0x41bfd8 + 0xc) == 0x812 && word(0x41bfd8 + 0x58 + 0xc) == 0x834;
        if (tick < 69 && seen_start) early = true;
        if (tick == 0) {
            fn_00199944(&c);
            check(word(cinematic::CINE_BASE + cinematic::CINE_HOLD) == 1,
                  "a repeated call in one game tick does not count another hold tick");
        }
    }
    check(!early && seen_start == 1 && word(cinematic::CINE_BASE + 0xc) == 1,
          "original receives skip only after both players have held 60 distinct ticks");
    check(restored, "every held/pressed controller row is restored after original call");
    check((s32)word(cinematic::CINE_BASE + cinematic::CINE_HOLD) == -1,
          "a completed skip requires release before another count");
    auto block = std::vector<u8>(g_ram + cinematic::CINE_BASE, g_ram + cinematic::CINE_BASE + 0x40);
    c.r[4] = 1; fn_00199944(&c);
    check(std::equal(block.begin(), block.end(), g_ram + cinematic::CINE_BASE), "load warm-up leaves hold block unchanged");
    g_ram[0x402791] = 1; cinematic::blank(2);
    check(!cinematic::active(), "online mode without room agreement disables local hold request");
    net2hook::cine_room(1); cinematic::blank(3);
    check(cinematic::active(), "room-agreed hold is active");
    net2hook::cine_room(0); cinematic::blank(4);
    check(!cinematic::active(), "room-agreed tap overrides local hold request");

    std::fill(memory.begin(), memory.end(), 0);
    hardcore = true;
    check(partyscale_hook::setting("combat.party.players", "8") && partyscale_hook::setting("combat.party.elite.8", "0"),
          "production scaling accepts eight-player tuning");
    const u32 figure = partyscale_hook::figure();
    check(partyscale_hook::setting("combat.party.hp.8", "540") && partyscale_hook::figure() != figure,
          "party tuning changes the room compatibility figure");
    partyscale_hook::setting("combat.party.hp.8", "530");
    put(0x4d8ae0, 8); put(0x110000 + 0x34, 0x120000);
    std::memcpy(g_ram + 0x120000, "authored fixture", 17);
    c = Ctx{}; c.r[4] = 0x110000; c.r[29] = 0x130000;
    c.f[12] = bits(1); c.f[14] = bits(2); c.f[16] = bits(3);
    fn_0010a620(&c);
    check(std::fabs(seen_hp - 5.3f) < 0.00001f && std::fabs(seen_damage - 3.7f) < 0.00001f && seen_exp == 24,
          "enabled scaling hands authored eight-player multipliers to original");
    check(seen_players == 1 && word(0x4d8ae0) == 8, "original sees count one for custom curve, shared player count is restored");
    check(word(partyscale::PARTY_BASE + 0xc) == 8 && word(partyscale::PARTY_BASE + 0x10) == 1,
          "production scaled-creature counters identify party eight");
    check(partyscale_hook::poise_limit(0x110000, 0, 100, 200) == 210, "enabled scaling supplies party poise limit");
    partyscale_hook::setting("combat.party.on", "0");
    off_identity(fn_0010a620, orig_0010a620, "party scaling off: full RAM and Ctx equal direct original while Hardcore is active");
    std::printf("gameplay modules: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
