// jitdiff — do Play!'s two code generators compute the same bits?
//
// The playable application translates the game's code to ARM64 instructions; the browser
// build translates it to WebAssembly. Both translators are fed the same intermediate
// operations by the same front end (Play!'s COP_FPU.cpp and VUShared.cpp). This program
// asks the code generator of the platform it was compiled for to translate every
// floating-point operation of that intermediate language, alone and in the combinations
// the front end emits for the console's instructions, runs each over a few million
// operands (special values, values a rounding step apart, random bits) and prints one
// checksum per operation. Compiled twice — natively, and with Emscripten for node — the
// two lists of checksums are the same exactly when the two translators agree on every
// result bit for every operand tried.
//
//   jitdiff [--mode browser|native|asis] [--count N] [--dump DIR] [--only NAME]
//
// --mode (native build only): the state of the processor's floating-point control
// register while the translated code runs. 'browser': results rounded to nearest,
// denormals kept (what "browser arithmetic" in the application sets). 'native': rounded
// toward zero, denormals as zero (Play!'s own). A WebAssembly build has no such register.
// --dump DIR writes every result of every operation to DIR/<name>.bin (compare with cmp).
//
// Operations whose name starts with "unused." are in the intermediate language but are not
// emitted by the emulator's front ends for the EE's FPU or the vector units (checked by
// searching Play!'s Source directory); they are run for interest and are not part of the
// "ALL" line. One of them differs by design of the two translators: a "greater than"
// compare with a NaN operand (true from the ARM64 translator, false from the WebAssembly one).
//
// Nothing of the game is in here. Build: tools/arith/build.sh.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <deque>
#include <functional>
#include <string>
#include <vector>
#include "AlignedAlloc.h"
#include "Jitter.h"
#include "Jitter_CodeGenFactory.h"
#include "MemStream.h"
#include "MemoryFunction.h"
#include "offsetof_def.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
// The WebAssembly code generator's modules import a table of the functions translated code
// may call; Play! creates it when the first such function is registered. Nothing here
// calls out, so an empty one is made.
EM_JS(void, MakeImportTable, (), {
	if(Module.codeGenImportTable === undefined)
	{
		Module.codeGenImportTable = new WebAssembly.Table({element : 'anyfunc', initial : 32});
		Module.codeGenImportTableNextIndex = 0;
	}
});
#endif

struct CONTEXT
{
	uint32_t a[4];
	uint32_t b[4];
	uint32_t c[4];
	uint32_t r[4];
	uint32_t fa, fb, fc, fr;
	uint32_t ir;
	uint32_t pad[11];
};

#define OFF(x) offsetof(CONTEXT, x)

typedef std::function<void(Jitter::CJitter&)> Emitter;

enum KIND
{
	S1, // scalar, operand fa, result fr
	S2, // scalar, fa fb
	S3, // scalar, fa fb fc
	S1I, // scalar, operand fa, result ir
	S2I, // scalar, fa fb, result ir
	V1, // vector, operand a, result r
	V2,
	V3,
	V1I, // vector, operand a, result ir
	V3I,
};

struct CASE
{
	const char* name;
	KIND kind;
	Emitter emit;
};

// ---- the operations ---------------------------------------------------------------------
// "raw": one intermediate operation. The others are what the front end emits for a
// console instruction: the EE's FPU clamps every operand of an arithmetic instruction
// (infinities and NaNs become the largest finite value of their sign) before the
// operation; the vector units clamp some operands of some instructions.

static void PushA(Jitter::CJitter& j, bool clamp)
{
	j.FP_PushRel32(OFF(fa));
	if(clamp) j.FP_ClampS();
}
static void PushB(Jitter::CJitter& j, bool clamp)
{
	j.FP_PushRel32(OFF(fb));
	if(clamp) j.FP_ClampS();
}
static void PushC(Jitter::CJitter& j, bool clamp)
{
	j.FP_PushRel32(OFF(fc));
	if(clamp) j.FP_ClampS();
}

static void MakeComparable(Jitter::CJitter& j)
{
	uint32 cursor = j.GetTopCursor();
	j.MD_PushCstExpandW(0xFFFFFFFFU); j.PushCursor(cursor); j.MD_SubW();
	j.MD_PushCstExpandW(0x7FFFFFFFU); j.PushCursor(cursor); j.MD_AddW();
	j.PushCursor(cursor); j.MD_SraW(31); j.MD_BitSelect();
	j.MD_PushCstExpandW(0x80000000U); j.MD_SubW();
	j.Swap(); j.PullTop();
}

static std::vector<CASE> MakeCases()
{
	using J = Jitter::CJitter;
	std::vector<CASE> cases;
	auto add = [&](const char* name, KIND kind, Emitter emit) { cases.push_back(CASE{name, kind, emit}); };

	for(int clamp = 0; clamp < 2; clamp++)
	{
		bool c = (clamp != 0);
		// the names are static strings: built once
		static std::deque<std::string> names; // a deque: the strings stay where they are
		auto name = [&](const char* base) {
			names.push_back(std::string(c ? "fpu." : "raw.") + base);
			return names.back().c_str();
		};
		add(name("add"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_AddS(); j.FP_PullRel32(OFF(fr)); });
		add(name("sub"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_SubS(); j.FP_PullRel32(OFF(fr)); });
		add(name("mul"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_MulS(); j.FP_PullRel32(OFF(fr)); });
		add(name("div"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_DivS(); j.FP_PullRel32(OFF(fr)); });
		add(name("max"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_MaxS(); j.FP_PullRel32(OFF(fr)); });
		add(name("min"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_MinS(); j.FP_PullRel32(OFF(fr)); });
		// sqrt.s: the root of the magnitude
		add(name("sqrt"), S1, [c](J& j) { PushA(j, c); if(c) j.FP_AbsS(); j.FP_SqrtS(); j.FP_PullRel32(OFF(fr)); });
		// rsqrt.s: fs * (1 / root of ft)
		add(name("rsqrt"), S2, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_RsqrtS(); j.FP_MulS(); j.FP_PullRel32(OFF(fr)); });
		// madd.s / msub.s: accumulator +/- fs * ft, a multiply and then an add
		add(name("madd"), S3, [c](J& j) { PushC(j, c); PushA(j, c); PushB(j, c); j.FP_MulS(); j.FP_AddS(); j.FP_PullRel32(OFF(fr)); });
		add(name("msub"), S3, [c](J& j) { PushC(j, c); PushA(j, c); PushB(j, c); j.FP_MulS(); j.FP_SubS(); j.FP_PullRel32(OFF(fr)); });
		add(name("cmp.eq"), S2I, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_CmpS(Jitter::CONDITION_EQ); j.PullRel(OFF(ir)); });
		add(name("cmp.lt"), S2I, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_CmpS(Jitter::CONDITION_BL); j.PullRel(OFF(ir)); });
		add(name("cmp.le"), S2I, [c](J& j) { PushA(j, c); PushB(j, c); j.FP_CmpS(Jitter::CONDITION_BE); j.PullRel(OFF(ir)); });
	}
	add("unused.cmp.gt", S2I, [](J& j) { PushA(j, false); PushB(j, false); j.FP_CmpS(Jitter::CONDITION_AB); j.PullRel(OFF(ir)); });
	add("raw.rcpl", S1, [](J& j) { PushA(j, false); j.FP_RcplS(); j.FP_PullRel32(OFF(fr)); });
	add("raw.rsqrt1", S1, [](J& j) { PushA(j, false); j.FP_RsqrtS(); j.FP_PullRel32(OFF(fr)); });
	add("raw.abs", S1, [](J& j) { PushA(j, false); j.FP_AbsS(); j.FP_PullRel32(OFF(fr)); });
	add("raw.neg", S1, [](J& j) { PushA(j, false); j.FP_NegS(); j.FP_PullRel32(OFF(fr)); });
	add("raw.clamp", S1, [](J& j) { PushA(j, false); j.FP_ClampS(); j.FP_PullRel32(OFF(fr)); });
	// cvt.w.s / trunc.w.s: to integer, truncating; cvt.s.w: integer to float
	add("fpu.toint", S1, [](J& j) { PushA(j, false); j.FP_ToInt32TruncateS(); j.FP_PullRel32(OFF(fr)); });
	add("fpu.tosingle", S1, [](J& j) { PushA(j, false); j.FP_ToSingleI32(); j.FP_PullRel32(OFF(fr)); });
	// the vector units' divide, root and reciprocal root (VUShared.cpp: no clamping)
	add("vu.div", S2, [](J& j) { PushA(j, false); PushB(j, false); j.FP_DivS(); j.FP_PullRel32(OFF(fr)); });
	add("vu.sqrt", S1, [](J& j) { PushA(j, false); j.FP_AbsS(); j.FP_SqrtS(); j.FP_PullRel32(OFF(fr)); });
	// a chain as the vector units' series instructions make them (sum of products)
	add("raw.poly", S3, [](J& j) {
		PushA(j, false); PushA(j, false); j.FP_MulS(); PushB(j, false); j.FP_MulS();
		PushA(j, false); PushC(j, false); j.FP_MulS(); j.FP_AddS();
		PushB(j, false); j.FP_AddS(); j.FP_PullRel32(OFF(fr));
	});

	// vectors of four
	add("md.add", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_AddS(); j.MD_PullRel(OFF(r)); });
	add("md.sub", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_SubS(); j.MD_PullRel(OFF(r)); });
	add("md.mul", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_MulS(); j.MD_PullRel(OFF(r)); });
	add("md.div", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_DivS(); j.MD_PullRel(OFF(r)); });
	add("unused.md.min", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_MinS(); j.MD_PullRel(OFF(r)); });
	add("unused.md.max", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_MaxS(); j.MD_PullRel(OFF(r)); });
	add("unused.md.cmplt", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_CmpLtS(); j.MD_PullRel(OFF(r)); });
	add("unused.md.cmpgt", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_CmpGtS(); j.MD_PullRel(OFF(r)); });
	add("md.abs", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_AbsS(); j.MD_PullRel(OFF(r)); });
	add("md.neg", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_NegS(); j.MD_PullRel(OFF(r)); });
	add("md.clamp", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PullRel(OFF(r)); });
	add("md.toint", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ToInt32TruncateS(); j.MD_PullRel(OFF(r)); });
	add("md.tosingle", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ToSingleI32(); j.MD_PullRel(OFF(r)); });
	add("md.signzero", V1I, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_MakeSignZero(); j.PullRel(OFF(ir)); });
	add("md.clip", V3I, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_PushRel(OFF(c)); j.MD_MakeClip(); j.PullRel(OFF(ir)); });
	// the vector units' instructions as VUShared.cpp builds them
	add("vu.add", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PushRel(OFF(b)); j.MD_AddS(); j.MD_PullRel(OFF(r)); });
	add("vu.sub", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PushRel(OFF(b)); j.MD_ClampS(); j.MD_SubS(); j.MD_PullRel(OFF(r)); });
	add("vu.mul", V2, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PushRel(OFF(b)); j.MD_ClampS(); j.MD_MulS(); j.MD_PullRel(OFF(r)); });
	add("vu.madd", V3, [](J& j) { j.MD_PushRel(OFF(c)); j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PushRel(OFF(b)); j.MD_MulS(); j.MD_AddS(); j.MD_PullRel(OFF(r)); });
	add("vu.madda", V3, [](J& j) { j.MD_PushRel(OFF(c)); j.MD_PushRel(OFF(a)); j.MD_ClampS(); j.MD_PushRel(OFF(b)); j.MD_ClampS(); j.MD_MulS(); j.MD_AddS(); j.MD_PullRel(OFF(r)); });
	add("vu.msub", V3, [](J& j) { j.MD_PushRel(OFF(c)); j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_MulS(); j.MD_SubS(); j.MD_PullRel(OFF(r)); });
	// the fixed-point conversions: scale by a power of two, then convert (ftoi4/12/15, itof4/12/15)
	add("vu.ftoi4", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushCstExpandS(16.0f); j.MD_MulS(); j.MD_ToInt32TruncateS(); j.MD_PullRel(OFF(r)); });
	add("vu.ftoi12", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_PushCstExpandS(4096.0f); j.MD_MulS(); j.MD_ToInt32TruncateS(); j.MD_PullRel(OFF(r)); });
	add("vu.itof4", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ToSingleI32(); j.MD_PushCstExpandS(16.0f); j.MD_DivS(); j.MD_PullRel(OFF(r)); });
	add("vu.itof15", V1, [](J& j) { j.MD_PushRel(OFF(a)); j.MD_ToSingleI32(); j.MD_PushCstExpandS(32768.0f); j.MD_DivS(); j.MD_PullRel(OFF(r)); });
	// max / mini: the larger or smaller of two, chosen by an integer compare of the bit
	// patterns made comparable (VUShared::MakeComparableFromFloat), no float compare at all
	add("vu.max", V2, [](J& j) {
		j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b));
		j.MD_PushRel(OFF(a)); MakeComparable(j); j.MD_PushRel(OFF(b)); MakeComparable(j);
		j.MD_CmpGtW(); j.MD_BitSelect(); j.MD_PullRel(OFF(r));
	});
	add("vu.mini", V2, [](J& j) {
		j.MD_PushRel(OFF(b)); j.MD_PushRel(OFF(a));
		j.MD_PushRel(OFF(a)); MakeComparable(j); j.MD_PushRel(OFF(b)); MakeComparable(j);
		j.MD_CmpGtW(); j.MD_BitSelect(); j.MD_PullRel(OFF(r));
	});
	// clip: the six compares of x, y, z against +w and -w (VUShared::CLIP)
	add("vu.clip", V3I, [](J& j) {
		j.MD_PushRel(OFF(a)); j.MD_PushRel(OFF(b)); j.MD_AbsS(); j.MD_PushRel(OFF(b)); j.MD_AbsS(); j.MD_NegS();
		j.MD_MakeClip(); j.PullRel(OFF(ir));
	});
	return cases;
}

// ---- operands ---------------------------------------------------------------------------

static uint64_t g_rng = 0x9E3779B97F4A7C15ull;
static uint64_t Next()
{
	g_rng ^= g_rng >> 12;
	g_rng ^= g_rng << 25;
	g_rng ^= g_rng >> 27;
	return g_rng * 0x2545F4914F6CDD1Dull;
}

static const uint32_t g_special[] = {
    0x00000000, 0x80000000, // zeroes
    0x00000001, 0x80000001, 0x00000002, 0x007FFFFF, 0x807FFFFF, 0x00400000, 0x00012345, // denormals
    0x00800000, 0x80800000, 0x00800001, 0x00FFFFFF, 0x01000000, // smallest normals
    0x3F800000, 0xBF800000, 0x3F7FFFFF, 0x3F800001, 0x40000000, 0x3F000000, 0x3FC00000, 0x40400000,
    0x3E4CCCCC, 0x3D4CCCCC, 0x3C888888, 0x3EE4F92D, 0x3EE4F92E, 0x3F317217, // constants of the kind games carry
    0x41200000, 0x42C80000, 0x447A0000, 0x461C4000, 0x4B800000, 0x4B7FFFFF, 0x4F000000, 0xCF000000, 0x4EFFFFFF, 0x4F800000, 0x5F000000,
    0x7F7FFFFF, 0xFF7FFFFF, 0x7F7FFFFE, 0x7F000000, 0x7E800000, 0x5F800000, 0x60000000, // near overflow
    0x7F800000, 0xFF800000, // infinities
    0x7FC00000, 0xFFC00000, 0x7F800001, 0xFF800001, 0x7FFFFFFF, 0xFFFFFFFF, 0x7FA00000, 0x7FC12345, // NaNs
    0x33800000, 0x34000000, 0x3F800002, 0x3FFFFFFF, 0xC2409999, 0xC240999A, 0x4285C28F, 0x38D1B717,
};
static const size_t g_specialCount = sizeof(g_special) / sizeof(g_special[0]);

// A value for operand slot 'slot' of test number 'index'. The first tests walk through all
// combinations of the special values; the rest are drawn: any bits, or a value near the
// one in the slot before it (same or neighbouring exponent: sums that cancel, quotients
// near one), or a small integer, or one of the special values.
static uint32_t Operand(uint64_t index, int slot, int slots, uint32_t previous)
{
	uint64_t combos = 1;
	for(int i = 0; i < slots; i++) combos *= g_specialCount;
	if(slots <= 2 && index < combos)
	{
		uint64_t digit = index;
		for(int i = 0; i < slot; i++) digit /= g_specialCount;
		return g_special[digit % g_specialCount];
	}
	uint64_t draw = Next();
	uint32_t bits = static_cast<uint32_t>(draw >> 32);
	switch(draw & 15)
	{
	case 0:
	case 1:
	case 2:
	case 3:
	case 4:
		return bits; // any bits (a third of these are huge or tiny, 1 in 256 not finite)
	case 5:
	case 6:
	case 7:
	case 8: // an ordinary magnitude: exponent 2^-12 .. 2^20
		return (bits & 0x807FFFFF) | ((0x73 + ((draw >> 8) % 33)) << 23);
	case 9:
	case 10:
	case 11: // near the value before: its exponent +/- 2, other mantissa, either sign
		if(slot == 0) return (bits & 0x807FFFFF) | ((0x7C + ((draw >> 8) % 8)) << 23);
		{
			int exponent = static_cast<int>((previous >> 23) & 0xFF) + static_cast<int>((draw >> 8) % 5) - 2;
			if(exponent < 0) exponent = 0;
			if(exponent > 255) exponent = 255;
			return (bits & 0x807FFFFF) | (static_cast<uint32_t>(exponent) << 23);
		}
	case 12: // one place away from the value before
		if(slot == 0) return bits;
		return previous + static_cast<uint32_t>((draw >> 8) % 5) - 2;
	case 13: // a small whole number, as a float
	{
		float value = static_cast<float>(static_cast<int>((draw >> 8) % 4097) - 2048);
		uint32_t result;
		memcpy(&result, &value, 4);
		return result;
	}
	case 14: // tiny: denormal or just above
		return (bits & 0x807FFFFF) | (((draw >> 8) % 3) << 23);
	default:
		return g_special[(draw >> 8) % g_specialCount];
	}
}

// ---- the processor's state (native build) ----------------------------------------------

static void SetMode(const std::string& mode)
{
#if defined(__aarch64__)
	if(mode == "asis") return;
	uint64_t fpcr = 0;
	__asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
	// rounding mode bits 23:22 (0 nearest, 3 toward zero), flush-to-zero bit 24, default NaN bit 25
	fpcr &= ~((3ull << 22) | (1ull << 24) | (1ull << 25) | 7ull);
	if(mode == "native") fpcr |= (3ull << 22) | (1ull << 24);
	__asm__ __volatile__("msr fpcr, %0" : : "r"(fpcr));
#else
	(void)mode;
#endif
}

static const char* ModeText()
{
#if defined(__EMSCRIPTEN__)
	return "WebAssembly (to nearest, denormals kept: no control register)";
#elif defined(__aarch64__)
	static char text[96];
	uint64_t fpcr = 0;
	__asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
	static const char* rounding[4] = {"to nearest", "upward", "downward", "toward zero"};
	snprintf(text, sizeof(text), "ARM64, control register %08llx (%s, denormals %s)", static_cast<unsigned long long>(fpcr), rounding[(fpcr >> 22) & 3], (fpcr & (1ull << 24)) ? "as zero" : "kept");
	return text;
#else
	return "another host";
#endif
}

int main(int argc, char** argv)
{
	std::string mode = "browser", dumpDir, only;
	uint64_t count = 2000000;
	for(int i = 1; i < argc; i++)
	{
		std::string arg = argv[i];
		auto value = [&]() -> std::string { return (i + 1 < argc) ? argv[++i] : ""; };
		if(arg == "--mode") mode = value();
		else if(arg == "--count") count = strtoull(value().c_str(), nullptr, 0);
		else if(arg == "--dump") dumpDir = value();
		else if(arg == "--only") only = value();
		else
		{
			fprintf(stderr, "jitdiff [--mode browser|native|asis] [--count N] [--dump DIR] [--only NAME]\n");
			return 2;
		}
	}

#ifdef __EMSCRIPTEN__
	MakeImportTable();
#endif
	auto context = static_cast<CONTEXT*>(framework_aligned_alloc(sizeof(CONTEXT), 0x10));
	auto cases = MakeCases();
	SetMode(mode);
	printf("# jitdiff: %s; %llu operand sets per operation\n", ModeText(), static_cast<unsigned long long>(count));

	Jitter::CJitter jitter(Jitter::CreateCodeGen());
	uint64_t all = 0xCBF29CE484222325ull;
	for(const auto& test : cases)
	{
		if(!only.empty() && only != test.name) continue;
		Framework::CMemStream codeStream;
		jitter.SetStream(&codeStream);
		jitter.Begin();
		test.emit(jitter);
		jitter.End();
		CMemoryFunction function(codeStream.GetBuffer(), codeStream.GetSize());

		FILE* dump = nullptr;
		if(!dumpDir.empty())
		{
			dump = fopen((dumpDir + "/" + test.name + ".bin").c_str(), "wb");
			if(!dump)
			{
				fprintf(stderr, "cannot write to %s\n", dumpDir.c_str());
				return 1;
			}
		}

		bool vector = (test.kind >= V1);
		int slots = (test.kind == S1 || test.kind == S1I || test.kind == V1 || test.kind == V1I) ? 1 : ((test.kind == S3 || test.kind == V3 || test.kind == V3I) ? 3 : 2);
		bool intResult = (test.kind == S1I || test.kind == S2I || test.kind == V1I || test.kind == V3I);
		g_rng = 0x9E3779B97F4A7C15ull; // the same operands for every operation of a kind
		uint64_t hash = 0xCBF29CE484222325ull;
		uint64_t nans = 0;
		auto mix = [&](uint32_t value) {
			hash = (hash ^ value) * 0x100000001B3ull;
		};
		for(uint64_t index = 0; index < count; index++)
		{
			memset(context, 0, sizeof(CONTEXT));
			uint32_t* slot[3] = {vector ? context->a : &context->fa, vector ? context->b : &context->fb, vector ? context->c : &context->fc};
			int lanes = vector ? 4 : 1;
			for(int lane = 0; lane < lanes; lane++)
			{
				uint32_t previous = 0;
				for(int s = 0; s < slots; s++)
				{
					// lane 0 of a vector test takes the same values a scalar test would
					previous = Operand(index * lanes + lane, s, slots, previous);
					slot[s][lane] = previous;
				}
			}
			function(context);
			if(intResult)
			{
				mix(context->ir);
				if(dump) fwrite(&context->ir, 4, 1, dump);
			}
			else if(vector)
			{
				for(int lane = 0; lane < 4; lane++)
				{
					mix(context->r[lane]);
					if((context->r[lane] & 0x7F800000) == 0x7F800000 && (context->r[lane] & 0x007FFFFF)) nans++;
				}
				if(dump) fwrite(context->r, 4, 4, dump);
			}
			else
			{
				mix(context->fr);
				if((context->fr & 0x7F800000) == 0x7F800000 && (context->fr & 0x007FFFFF)) nans++;
				if(dump) fwrite(&context->fr, 4, 1, dump);
			}
		}
		if(dump) fclose(dump);
		printf("%-16s %016llx  nan_results=%llu\n", test.name, static_cast<unsigned long long>(hash), static_cast<unsigned long long>(nans));
		if(strncmp(test.name, "unused.", 7) != 0) all = (all ^ hash) * 0x100000001B3ull;
	}
	printf("%-16s %016llx\n", "ALL", static_cast<unsigned long long>(all));
	return 0;
}
