// rta_rig — a headless, scriptable runner for Champions: Return to Arms (SLUS-20973)
// built on the core of the Play! PlayStation 2 emulator (github.com/jpd002/Play-).
//
// It boots a disc image with no video and no sound, unthrottled, and lets a script
// press buttons, read and write EE memory, apply PCSX2-style word patches, log named
// addresses per frame, stop or log at EE addresses, and save or load emulator states.
//
// Nothing here comes from the game. See README.md in this directory for use, and
// docs/issues/live-rig.md for what has been learned with it.
//
// Threads: Play!'s virtual machine runs on its own thread. Everything that touches
// machine state (memory, registers, pad, breakpoints) is done on that thread, from the
// pad handler's per-vblank update or from the break notification. The main thread only
// starts the machine, waits, and stops it.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cinttypes>
#include <condition_variable>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <future>
#include <map>
#include <mutex>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <dlfcn.h>
#include <execinfo.h>
#include <pthread.h>
#include <signal.h>
#include <sys/mman.h>
#include <unistd.h>

#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "AppConfig.h"
#include "Ps2Const.h"
#include "gs/GSH_Null.h"
#include "ee/PS2OS.h"
#include "iop/IopBios.h"

// ---------------------------------------------------------------------------------
// Play! asks the application where its data directory is. Ours is given with --data
// (default ./rig-data) so that nothing is written to the user's Documents folder.
// ---------------------------------------------------------------------------------

static fs::path g_basePath;

fs::path CAppConfig::GetBasePath() const
{
	return g_basePath;
}

// ---------------------------------------------------------------------------------
// Play! write-protects every host page of EE memory that holds translated code, so that
// a write to it can discard the translation. Host pages are 16 KB on Apple silicon; when
// such a page also holds data the game writes every frame, each write costs a fault, a
// round trip to Play!'s exception thread and a re-translation. The rig counts those
// requests, and with --no-code-protect ignores them. That is safe for a program that
// flushes the instruction cache after changing code (which a real console requires
// too): Play! discards translations on the flush system call regardless.
//
// This definition replaces the C library's mprotect for the whole executable; every
// call that is not a protect request for EE memory goes to the real one.
// ---------------------------------------------------------------------------------

static uint8* g_eeRamBase = nullptr;
static bool g_noCodeProtect = false;
static std::atomic<uint64> g_protectRequests{0};
static std::atomic<uint64> g_unprotectRequests{0};

extern "C" int mprotect(void* address, size_t length, int protection)
{
	typedef int (*MprotectFunction)(void*, size_t, int);
	static MprotectFunction realFunction = reinterpret_cast<MprotectFunction>(dlsym(RTLD_NEXT, "mprotect"));
	auto p = static_cast<uint8*>(address);
	if(g_eeRamBase && p >= g_eeRamBase && p < g_eeRamBase + PS2::EE_RAM_SIZE)
	{
		if(protection == PROT_READ)
		{
			g_protectRequests++;
			if(g_noCodeProtect) return 0;
		}
		else
		{
			g_unprotectRequests++;
		}
	}
	return realFunction(address, length, protection);
}

// ---------------------------------------------------------------------------------
// --profile: a wall-clock sampler for the machine thread and the video thread. A helper
// thread signals each of them every few milliseconds and the handler records a short
// stack. It answers "where does the time go" when the host's own profilers cannot be
// attached. Stacks that pass through translated code stop there.
// ---------------------------------------------------------------------------------

namespace prof
{
	enum
	{
		MAX_SAMPLES = 1 << 17,
		DEPTH = 10,
		THREADS = 2,
	};
	static pthread_t g_threads[THREADS];
	static std::atomic<bool> g_threadSet[THREADS];
	static const char* g_threadNames[THREADS] = {"machine", "video"};
	static void* g_frames[MAX_SAMPLES][DEPTH];
	static uint8 g_depth[MAX_SAMPLES];
	static uint8 g_owner[MAX_SAMPLES];
	static std::atomic<uint32> g_count{0};
	static std::atomic<bool> g_running{false};
	static std::thread g_sampler;

	static void Handler(int)
	{
		uint32 index = g_count.fetch_add(1);
		if(index >= MAX_SAMPLES) return;
		pthread_t self = pthread_self();
		g_owner[index] = (g_threadSet[1] && pthread_equal(self, g_threads[1])) ? 1 : 0;
		g_depth[index] = static_cast<uint8>(backtrace(g_frames[index], DEPTH));
	}

	static void Register(int slot)
	{
		g_threads[slot] = pthread_self();
		g_threadSet[slot] = true;
	}

	static void Start()
	{
		struct sigaction action = {};
		action.sa_handler = &Handler;
		action.sa_flags = SA_RESTART;
		sigaction(SIGUSR1, &action, nullptr);
		g_running = true;
		g_sampler = std::thread([]() {
			while(g_running)
			{
				for(int i = 0; i < THREADS; i++)
				{
					if(g_threadSet[i]) pthread_kill(g_threads[i], SIGUSR1);
				}
				std::this_thread::sleep_for(std::chrono::milliseconds(2));
			}
		});
	}

	static void Report()
	{
		if(!g_running) return;
		g_running = false;
		g_sampler.join();
		uint32 count = std::min<uint32>(g_count, MAX_SAMPLES);
		for(int owner = 0; owner < THREADS; owner++)
		{
			std::map<std::string, uint32> stacks;
			uint32 total = 0;
			for(uint32 i = 0; i < count; i++)
			{
				if(g_owner[i] != owner) continue;
				total++;
				std::string key;
				// frame 0 is the handler, 1 the signal trampoline
				for(int f = 2; f < g_depth[i] && f < 8; f++)
				{
					Dl_info info = {};
					if(dladdr(g_frames[i][f], &info) && info.dli_sname)
					{
						std::string name = info.dli_sname;
						if(name.size() > 70) name.resize(70);
						key += name;
					}
					else
						key += "?";
					key += " < ";
				}
				stacks[key]++;
			}
			std::vector<std::pair<uint32, std::string>> sorted;
			for(const auto& stack : stacks) sorted.push_back({stack.second, stack.first});
			std::sort(sorted.rbegin(), sorted.rend());
			printf("profile, %s thread, %u samples:\n", g_threadNames[owner], total);
			for(size_t i = 0; i < sorted.size() && i < 14; i++)
			{
				printf("  %5.1f%%  %s\n", total ? 100.0 * sorted[i].first / total : 0, sorted[i].second.c_str());
			}
		}
	}
}

// A null video handler that reports which thread it runs on (for --profile).
class CRigGsNull : public CGSH_Null
{
public:
	static FactoryFunction GetFactoryFunction()
	{
		return []() { return new CRigGsNull(); };
	}

private:
	void InitializeImpl() override
	{
		prof::Register(1);
	}
};

// ---------------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------------

// Errors in options and scripts. Caught in main() (message, exit code 2) and, in an
// interactive session, by the command reader (message, the session goes on).
struct RigError : public std::runtime_error
{
	using std::runtime_error::runtime_error;
};

[[noreturn]] static void Die(const char* fmt, ...)
{
	char buffer[1024];
	va_list args;
	va_start(args, fmt);
	vsnprintf(buffer, sizeof(buffer), fmt, args);
	va_end(args);
	throw RigError(buffer);
}

static std::string StrFormat(const char* fmt, ...)
{
	char buffer[1024];
	va_list args;
	va_start(args, fmt);
	vsnprintf(buffer, sizeof(buffer), fmt, args);
	va_end(args);
	return buffer;
}

static std::string Lower(std::string s)
{
	for(auto& c : s) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
	return s;
}

// Splits on white space; "double quoted" tokens may contain spaces; # starts a comment.
static std::vector<std::string> Tokenize(const std::string& line)
{
	std::vector<std::string> result;
	size_t i = 0;
	while(i < line.size())
	{
		if(isspace(static_cast<unsigned char>(line[i])))
		{
			i++;
			continue;
		}
		if(line[i] == '#') break;
		std::string token;
		if(line[i] == '"')
		{
			i++;
			while(i < line.size() && line[i] != '"') token += line[i++];
			if(i < line.size()) i++;
		}
		else
		{
			while(i < line.size() && !isspace(static_cast<unsigned char>(line[i]))) token += line[i++];
		}
		result.push_back(token);
	}
	return result;
}

static std::vector<std::string> SplitChar(const std::string& s, char sep)
{
	std::vector<std::string> result;
	std::string item;
	std::stringstream stream(s);
	while(std::getline(stream, item, sep)) result.push_back(item);
	return result;
}

static bool ParseNumber(const std::string& s, int64_t& out)
{
	if(s.empty()) return false;
	char* end = nullptr;
	out = strtoll(s.c_str(), &end, 0);
	return end && *end == 0;
}

static std::string Escape(const std::string& s)
{
	std::string result;
	for(unsigned char c : s)
	{
		if(c == '\t' || c == '\n' || c == '\r' || c == '\\' || c < 0x20 || c >= 0x7f)
			result += StrFormat("\\x%02x", c);
		else
			result += static_cast<char>(c);
	}
	return result;
}

// ---------------------------------------------------------------------------------
// Symbols: tab-separated "hexaddress<TAB>name<TAB>note" files (names.tsv, symbols/*.tsv)
// ---------------------------------------------------------------------------------

static std::unordered_map<std::string, uint32> g_symbols;
static std::map<uint32, std::string> g_symbolsByAddress;

static void LoadSymbolFile(const std::string& path)
{
	std::ifstream file(path);
	if(!file) Die("cannot read symbol file %s", path.c_str());
	std::string line;
	while(std::getline(file, line))
	{
		if(line.empty() || line[0] == '#') continue;
		auto fields = SplitChar(line, '\t');
		if(fields.size() < 2) continue;
		char* end = nullptr;
		uint32 address = static_cast<uint32>(strtoul(fields[0].c_str(), &end, 16));
		if(!end || *end != 0 || fields[1].empty()) continue;
		g_symbols.emplace(fields[1], address);
		g_symbolsByAddress.emplace(address, fields[1]);
	}
}

// name of the symbol at or before an address, as "name+0x12"
static std::string Symbolize(uint32 address)
{
	auto it = g_symbolsByAddress.upper_bound(address);
	if(it == g_symbolsByAddress.begin()) return "";
	--it;
	uint32 delta = address - it->first;
	if(delta > 0x8000) return "";
	if(delta == 0) return it->second;
	return StrFormat("%s+0x%x", it->second.c_str(), delta);
}

// ---------------------------------------------------------------------------------
// Address expressions:   0x4d8af0   g_players+0xac   [g_players+0x43d8]+0x10   2*0x4c30
// [x] reads the 32-bit word at x. Numbers are C style (0x.. is hex, otherwise decimal).
// $reg reads an EE register (low 32 bits): $pc $ra $sp $v0 $a0..$a3 $t0.. $s0..
// ---------------------------------------------------------------------------------

static const char* g_regNames[32] = {
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"};

static int RegisterIndex(const std::string& name)
{
	for(int i = 0; i < 32; i++)
	{
		if(name == g_regNames[i]) return i;
	}
	if(name == "s8") return 30;
	return -1;
}

struct Machine
{
	uint8* ram = nullptr;
	uint8* spr = nullptr;
	MIPSSTATE* state = nullptr;

	uint8* Ptr(uint32 address, uint32 length) const
	{
		if((address & 0xF0000000) == 0x70000000)
		{
			uint32 offset = address & (PS2::EE_SPR_SIZE - 1);
			if(offset + length > PS2::EE_SPR_SIZE) return nullptr;
			return spr + offset;
		}
		uint32 physical = address & 0x1FFFFFFF;
		if(static_cast<uint64>(physical) + length > PS2::EE_RAM_SIZE) return nullptr;
		return ram + physical;
	}
	uint32 Read32(uint32 address) const
	{
		uint32 value = 0;
		if(auto p = Ptr(address, 4)) memcpy(&value, p, 4);
		return value;
	}
	uint32 Reg(int index) const
	{
		return state->nGPR[index].nV0;
	}
};

struct Expr
{
	enum OP : uint8
	{
		NUM,
		ADD,
		SUB,
		MUL,
		DEREF,
		REG,
		PC,
	};
	struct NODE
	{
		OP op;
		uint32 value;
	};
	std::vector<NODE> code;
	std::string text;

	uint32 Eval(const Machine& m) const
	{
		uint32 stack[32];
		int sp = 0;
		for(const auto& node : code)
		{
			switch(node.op)
			{
			case NUM:
				stack[sp++] = node.value;
				break;
			case REG:
				stack[sp++] = m.Reg(node.value);
				break;
			case PC:
				stack[sp++] = m.state->nPC;
				break;
			case DEREF:
				stack[sp - 1] = m.Read32(stack[sp - 1]);
				break;
			case ADD:
				sp--;
				stack[sp - 1] += stack[sp];
				break;
			case SUB:
				sp--;
				stack[sp - 1] -= stack[sp];
				break;
			case MUL:
				sp--;
				stack[sp - 1] *= stack[sp];
				break;
			}
		}
		return sp > 0 ? stack[0] : 0;
	}
};

class ExprParser
{
public:
	ExprParser(const std::string& text)
	    : m_text(text)
	{
	}

	Expr Parse()
	{
		Expr expr;
		expr.text = m_text;
		ParseSum(expr);
		SkipSpace();
		if(m_pos != m_text.size()) Die("cannot parse expression '%s' at '%s'", m_text.c_str(), m_text.c_str() + m_pos);
		if(expr.code.size() > 30) Die("expression too long: %s", m_text.c_str());
		return expr;
	}

private:
	void SkipSpace()
	{
		while(m_pos < m_text.size() && isspace(static_cast<unsigned char>(m_text[m_pos]))) m_pos++;
	}
	bool Accept(char c)
	{
		SkipSpace();
		if(m_pos < m_text.size() && m_text[m_pos] == c)
		{
			m_pos++;
			return true;
		}
		return false;
	}
	void ParseSum(Expr& expr)
	{
		ParseProduct(expr);
		while(true)
		{
			if(Accept('+'))
			{
				ParseProduct(expr);
				expr.code.push_back({Expr::ADD, 0});
			}
			else if(Accept('-'))
			{
				ParseProduct(expr);
				expr.code.push_back({Expr::SUB, 0});
			}
			else
				break;
		}
	}
	void ParseProduct(Expr& expr)
	{
		ParseAtom(expr);
		while(Accept('*'))
		{
			ParseAtom(expr);
			expr.code.push_back({Expr::MUL, 0});
		}
	}
	void ParseAtom(Expr& expr)
	{
		SkipSpace();
		if(Accept('['))
		{
			ParseSum(expr);
			if(!Accept(']')) Die("missing ] in '%s'", m_text.c_str());
			expr.code.push_back({Expr::DEREF, 0});
			return;
		}
		if(Accept('('))
		{
			ParseSum(expr);
			if(!Accept(')')) Die("missing ) in '%s'", m_text.c_str());
			return;
		}
		if(Accept('$'))
		{
			std::string name = ReadWord();
			if(name == "pc")
			{
				expr.code.push_back({Expr::PC, 0});
				return;
			}
			int index = RegisterIndex(name);
			if(index < 0) Die("unknown register $%s in '%s'", name.c_str(), m_text.c_str());
			expr.code.push_back({Expr::REG, static_cast<uint32>(index)});
			return;
		}
		std::string word = ReadWord();
		if(word.empty()) Die("cannot parse expression '%s'", m_text.c_str());
		if(isdigit(static_cast<unsigned char>(word[0])))
		{
			int64_t value = 0;
			if(!ParseNumber(word, value)) Die("bad number '%s' in '%s' (hex needs 0x)", word.c_str(), m_text.c_str());
			expr.code.push_back({Expr::NUM, static_cast<uint32>(value)});
			return;
		}
		auto symbol = g_symbols.find(word);
		if(symbol == g_symbols.end()) Die("unknown symbol '%s' in '%s' (load symbol files with --sym)", word.c_str(), m_text.c_str());
		expr.code.push_back({Expr::NUM, symbol->second});
	}
	std::string ReadWord()
	{
		std::string word;
		while(m_pos < m_text.size() && (isalnum(static_cast<unsigned char>(m_text[m_pos])) || m_text[m_pos] == '_' || m_text[m_pos] == '.'))
		{
			word += m_text[m_pos++];
		}
		return word;
	}

	std::string m_text;
	size_t m_pos = 0;
};

// ---------------------------------------------------------------------------------
// Typed values: u8 s8 u16 s16 u32 s32 (decimal), x8 x16 x32 (hex), f32, strN, hexN
// ---------------------------------------------------------------------------------

struct TypeSpec
{
	enum KIND
	{
		UINT,
		SINT,
		HEXINT,
		FLOAT,
		STR,
		BYTES,
	};
	KIND kind = HEXINT;
	uint32 size = 4;
};

static TypeSpec ParseType(const std::string& text)
{
	std::string t = Lower(text);
	TypeSpec type;
	auto sized = [&](const char* prefix, TypeSpec::KIND kind, uint32 defaultSize) {
		size_t length = strlen(prefix);
		if(t.compare(0, length, prefix) != 0) return false;
		std::string rest = t.substr(length);
		uint32 size = defaultSize;
		if(!rest.empty())
		{
			int64_t value = 0;
			if(!ParseNumber(rest, value) || value <= 0 || value > 0x100000) return false;
			size = static_cast<uint32>(value);
		}
		type.kind = kind;
		type.size = size;
		return true;
	};
	if(t == "f32" || t == "float")
	{
		type.kind = TypeSpec::FLOAT;
		type.size = 4;
		return type;
	}
	if(sized("str", TypeSpec::STR, 64)) return type;
	if(sized("hex", TypeSpec::BYTES, 16)) return type;
	if(t.size() >= 2 && (t[0] == 'u' || t[0] == 's' || t[0] == 'x'))
	{
		int64_t bits = 0;
		if(ParseNumber(t.substr(1), bits) && (bits == 8 || bits == 16 || bits == 32))
		{
			type.kind = (t[0] == 'u') ? TypeSpec::UINT : (t[0] == 's') ? TypeSpec::SINT : TypeSpec::HEXINT;
			type.size = static_cast<uint32>(bits / 8);
			return type;
		}
	}
	Die("unknown type '%s' (use u8 s8 u16 s16 u32 s32 x8 x16 x32 f32 strN hexN)", text.c_str());
}

struct Value
{
	bool isText = false;
	bool isFloat = false;
	int64_t integer = 0;
	double real = 0;
	std::string text;

	double AsReal() const
	{
		return isFloat ? real : static_cast<double>(integer);
	}
	bool operator==(const Value& other) const
	{
		if(isText != other.isText) return false;
		if(isText) return text == other.text;
		if(isFloat || other.isFloat) return AsReal() == other.AsReal();
		return integer == other.integer;
	}
};

static Value ReadValue(const Machine& m, uint32 address, const TypeSpec& type)
{
	Value value;
	const uint8* p = m.Ptr(address, type.size);
	if(!p)
	{
		value.isText = true;
		value.text = "<unmapped>";
		return value;
	}
	switch(type.kind)
	{
	case TypeSpec::UINT:
	case TypeSpec::HEXINT:
	{
		uint32 raw = 0;
		memcpy(&raw, p, type.size);
		value.integer = raw;
	}
	break;
	case TypeSpec::SINT:
	{
		uint32 raw = 0;
		memcpy(&raw, p, type.size);
		if(type.size == 1)
			value.integer = static_cast<int8>(raw);
		else if(type.size == 2)
			value.integer = static_cast<int16>(raw);
		else
			value.integer = static_cast<int32>(raw);
	}
	break;
	case TypeSpec::FLOAT:
	{
		float raw = 0;
		memcpy(&raw, p, 4);
		value.isFloat = true;
		value.real = raw;
	}
	break;
	case TypeSpec::STR:
		value.isText = true;
		for(uint32 i = 0; i < type.size && p[i] != 0; i++) value.text += static_cast<char>(p[i]);
		break;
	case TypeSpec::BYTES:
		value.isText = true;
		for(uint32 i = 0; i < type.size; i++) value.text += StrFormat("%02x", p[i]);
		break;
	}
	return value;
}

static std::string FormatValue(const Value& value, const TypeSpec& type)
{
	if(value.isText) return (type.kind == TypeSpec::STR) ? Escape(value.text) : value.text;
	if(value.isFloat) return StrFormat("%.9g", value.real);
	if(type.kind == TypeSpec::HEXINT) return StrFormat("%0*" PRIx64, static_cast<int>(type.size * 2), value.integer);
	return StrFormat("%" PRId64, value.integer);
}

// "expr:type"; the type defaults to x32. The last ':' outside brackets separates them.
static void SplitTyped(const std::string& text, std::string& exprText, std::string& typeText)
{
	int depth = 0;
	size_t colon = std::string::npos;
	for(size_t i = 0; i < text.size(); i++)
	{
		if(text[i] == '[' || text[i] == '(') depth++;
		if(text[i] == ']' || text[i] == ')') depth--;
		if(text[i] == ':' && depth == 0) colon = i;
	}
	if(colon == std::string::npos)
	{
		exprText = text;
		typeText = "x32";
	}
	else
	{
		exprText = text.substr(0, colon);
		typeText = text.substr(colon + 1);
	}
}

struct Watch
{
	std::string name;
	Expr expr;
	TypeSpec type;
};

// "name=expr:type" or "expr:type" (the name is then the expression text)
static Watch ParseWatch(const std::string& spec)
{
	Watch watch;
	std::string rest = spec;
	auto equals = spec.find('=');
	if(equals != std::string::npos)
	{
		watch.name = spec.substr(0, equals);
		rest = spec.substr(equals + 1);
	}
	std::string exprText, typeText;
	SplitTyped(rest, exprText, typeText);
	if(watch.name.empty()) watch.name = exprText;
	watch.expr = ExprParser(exprText).Parse();
	watch.type = ParseType(typeText);
	return watch;
}

struct Condition
{
	enum OP
	{
		EQ,
		NE,
		LT,
		LE,
		GT,
		GE,
		CHANGED,
	};
	Watch watch;
	OP op = EQ;
	Value reference;
	std::string text;

	bool Test(const Machine& m) const
	{
		Value value = ReadValue(m, watch.expr.Eval(m), watch.type);
		switch(op)
		{
		case EQ:
			return value == reference;
		case NE:
		case CHANGED:
			return !(value == reference);
		case LT:
			return value.AsReal() < reference.AsReal();
		case LE:
			return value.AsReal() <= reference.AsReal();
		case GT:
			return value.AsReal() > reference.AsReal();
		case GE:
			return value.AsReal() >= reference.AsReal();
		}
		return false;
	}
};

// tokens: <expr:type> <op> <value>   or   <expr:type> changed
static Condition ParseCondition(const std::vector<std::string>& tokens, size_t first, size_t& next)
{
	if(first + 1 >= tokens.size()) Die("condition needs '<expr:type> <op> <value>' or '<expr:type> changed'");
	Condition condition;
	condition.watch = ParseWatch(tokens[first]);
	const std::string& op = tokens[first + 1];
	condition.text = tokens[first] + " " + op;
	if(op == "changed")
	{
		condition.op = Condition::CHANGED;
		next = first + 2;
		return condition;
	}
	if(op == "==")
		condition.op = Condition::EQ;
	else if(op == "!=")
		condition.op = Condition::NE;
	else if(op == "<")
		condition.op = Condition::LT;
	else if(op == "<=")
		condition.op = Condition::LE;
	else if(op == ">")
		condition.op = Condition::GT;
	else if(op == ">=")
		condition.op = Condition::GE;
	else
		Die("unknown comparison '%s'", op.c_str());
	if(first + 2 >= tokens.size()) Die("condition '%s' needs a value", condition.text.c_str());
	const std::string& valueText = tokens[first + 2];
	condition.text += " " + valueText;
	if(condition.watch.type.kind == TypeSpec::STR || condition.watch.type.kind == TypeSpec::BYTES)
	{
		condition.reference.isText = true;
		condition.reference.text = valueText;
	}
	else
	{
		int64_t integer = 0;
		if(ParseNumber(valueText, integer))
		{
			condition.reference.integer = integer;
			if(condition.watch.type.kind == TypeSpec::FLOAT)
			{
				condition.reference.isFloat = true;
				condition.reference.real = static_cast<double>(integer);
			}
		}
		else
		{
			char* end = nullptr;
			double real = strtod(valueText.c_str(), &end);
			if(!end || *end != 0) Die("bad value '%s' in condition", valueText.c_str());
			condition.reference.isFloat = true;
			condition.reference.real = real;
		}
	}
	next = first + 3;
	return condition;
}

// ---------------------------------------------------------------------------------
// Controller state
// ---------------------------------------------------------------------------------

struct PadState
{
	uint32 buttons = 0; // bit n = PS2::CControllerInfo::BUTTON n is held
	uint8 axis[4] = {0x80, 0x80, 0x80, 0x80}; // left x, left y, right x, right y
};

static uint32 ParseButtons(const std::string& text)
{
	using B = PS2::CControllerInfo;
	static const std::map<std::string, int> names = {
	    {"up", B::DPAD_UP}, {"down", B::DPAD_DOWN}, {"left", B::DPAD_LEFT}, {"right", B::DPAD_RIGHT}, {"select", B::SELECT}, {"start", B::START}, {"square", B::SQUARE}, {"triangle", B::TRIANGLE}, {"circle", B::CIRCLE}, {"cross", B::CROSS}, {"x", B::CROSS}, {"l1", B::L1}, {"l2", B::L2}, {"l3", B::L3}, {"r1", B::R1}, {"r2", B::R2}, {"r3", B::R3}};
	uint32 mask = 0;
	std::string list = Lower(text);
	for(auto& c : list)
	{
		if(c == ',' || c == '|') c = '+';
	}
	for(const auto& name : SplitChar(list, '+'))
	{
		if(name.empty() || name == "none" || name == "-") continue;
		auto it = names.find(name);
		if(it == names.end()) Die("unknown button '%s'", name.c_str());
		mask |= (1u << it->second);
	}
	return mask;
}

// ---------------------------------------------------------------------------------
// PCSX2-style patch files: [section] headers and  patch=1,EE,<addr>,word,<value>  lines
// ---------------------------------------------------------------------------------

struct PnachWord
{
	uint32 address;
	uint32 value;
};

static std::vector<PnachWord> ReadPnachSection(const std::string& path, const std::string& wanted, std::vector<std::string>* sectionNames = nullptr)
{
	std::ifstream file(path);
	if(!file) Die("cannot read patch file %s", path.c_str());
	std::vector<PnachWord> words;
	std::string line, section;
	bool found = false;
	while(std::getline(file, line))
	{
		while(!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
		if(line.size() >= 2 && line.front() == '[' && line.back() == ']')
		{
			section = line.substr(1, line.size() - 2);
			if(sectionNames) sectionNames->push_back(section);
			continue;
		}
		if(line.compare(0, 6, "patch=") != 0) continue;
		bool selected = (wanted == "*") || (section == wanted) || (!wanted.empty() && wanted.back() == '*' && section.compare(0, wanted.size() - 1, wanted, 0, wanted.size() - 1) == 0);
		if(!selected) continue;
		auto fields = SplitChar(line.substr(6), ',');
		if(fields.size() != 5) Die("%s: cannot parse '%s'", path.c_str(), line.c_str());
		if(Lower(fields[1]) != "ee" || Lower(fields[3]) != "word") Die("%s: only EE word patches are supported: '%s'", path.c_str(), line.c_str());
		PnachWord word;
		word.address = static_cast<uint32>(strtoul(fields[2].c_str(), nullptr, 16));
		word.value = static_cast<uint32>(strtoul(fields[4].c_str(), nullptr, 16));
		words.push_back(word);
		found = true;
	}
	if(!found && !sectionNames) Die("%s: no patch lines in section '%s'", path.c_str(), wanted.c_str());
	return words;
}

// ---------------------------------------------------------------------------------
// Break points
// ---------------------------------------------------------------------------------

struct BreakSpec
{
	uint32 address = 0;
	std::string name;
	std::vector<std::pair<std::string, int>> strings; // register name, index
	struct WIDE
	{
		std::string name;
		int pointerRegister;
		int lengthRegister; // -1: read up to the terminator
	};
	std::vector<WIDE> wideStrings; // 16-bit characters, as the game's text functions take
	bool collect = false;          // gather the strings of a frame instead of logging each hit
	struct MEM
	{
		Expr expr;
		uint32 length;
		std::string text;
	};
	std::vector<MEM> memory;
	std::vector<Watch> values;
	bool logReturn = false;
	bool stop = false;
	bool quiet = false;
	uint64 limit = 0; // stop logging after this many hits (0 = no limit)
	uint64 hits = 0;
};

// ---------------------------------------------------------------------------------
// Script
// ---------------------------------------------------------------------------------

struct Command
{
	enum KIND
	{
		WAIT,
		AT,
		UNTIL,
		PRESS,
		RELEASE,
		TAP,
		STICK,
		PAD,
		POKE,
		PNACH,
		SAVE,
		LOAD,
		DUMP,
		SHOW,
		ECHO,
		LOG,
		BREAK,
		UNBREAK,
		SYNC,
		QUIT,
	};
	KIND kind = WAIT;
	int line = 0;
	int port = 0;
	int64_t number = 0;
	int64_t number2 = 0;
	uint32 buttons = 0;
	uint8 axis[4] = {0x80, 0x80, 0x80, 0x80};
	int axisFirst = 0;
	int axisCount = 0;
	bool flag = false;
	std::string text, text2;
	Condition condition;
	std::vector<Watch> watches;
	Watch target;
	std::vector<uint8> bytes;
	// run-time
	bool started = false;
	uint64 deadline = 0;
};

class CRigVM : public CPS2VM
{
public:
	using CPS2VM::ResumeImpl;
};

class CRig;

class CRigPad : public CPadHandler
{
public:
	CRigPad(CRig& rig)
	    : m_rig(rig)
	{
	}
	void Update(uint8* ram) override;
	void Push(const PadState* pads, uint8* ram)
	{
		using B = PS2::CControllerInfo;
		for(auto* listener : m_interfaces)
		{
			for(unsigned int port = 0; port < 2; port++)
			{
				for(unsigned int i = 0; i < B::MAX_BUTTONS; i++)
				{
					auto button = static_cast<B::BUTTON>(i);
					if(B::IsAxis(button))
						listener->SetAxisState(port, button, pads[port].axis[i], ram);
					else
						listener->SetButtonState(port, button, (pads[port].buttons & (1u << i)) != 0, ram);
				}
			}
		}
	}

private:
	CRig& m_rig;
};

struct Options
{
	std::string disc;
	std::string data = "rig-data";
	std::string loadState;
	std::string saveStateAtEnd;
	std::string logPath;
	std::string breakLogPath;
	std::string scriptPath;
	std::vector<std::string> arguments;
	std::vector<std::string> watchSpecs;
	std::vector<std::string> breakSpecs;
	std::vector<std::string> untilTokens;
	std::vector<std::string> inlineCommands;
	uint64 frames = 0;
	uint32 logEvery = 1;
	bool logOnChange = false;
	bool playLogs = false;
	bool throttle = false;
	bool pcHistogram = false;
	bool noCodeProtect = false;
	bool profile = false;
	bool interactive = false;
};

class CRig
{
public:
	CRig(CRigVM& vm, const Options& options)
	    : m_vm(vm)
	    , m_options(options)
	{
	}

	// ---- set-up (main thread, machine paused) -------------------------------------

	void Prepare()
	{
		g_eeRamBase = m_vm.m_ee->m_ram;
		g_noCodeProtect = m_options.noCodeProtect;
		m_machine.ram = m_vm.m_ee->m_ram;
		m_machine.spr = m_vm.m_ee->m_spr;
		m_machine.state = &m_vm.m_ee->m_EE.m_State;
		m_pageSize = static_cast<uint32>(getpagesize());

		for(const auto& spec : m_options.watchSpecs) m_watches.push_back(ParseWatch(spec));
		if(!m_options.logPath.empty())
		{
			m_log = fopen(m_options.logPath.c_str(), "w");
			if(!m_log) Die("cannot write %s", m_options.logPath.c_str());
			fprintf(m_log, "frame");
			for(const auto& watch : m_watches) fprintf(m_log, "\t%s", watch.name.c_str());
			fprintf(m_log, "\n");
		}
		if(!m_options.breakLogPath.empty())
		{
			m_breakLog = fopen(m_options.breakLogPath.c_str(), "w");
			if(!m_breakLog) Die("cannot write %s", m_options.breakLogPath.c_str());
		}
		for(const auto& spec : m_options.breakSpecs) AddBreak(ParseBreak(spec));
		if(!m_options.untilTokens.empty())
		{
			size_t next = 0;
			m_until = ParseCondition(m_options.untilTokens, 0, next);
			m_hasUntil = true;
		}
		if(!m_options.scriptPath.empty()) LoadScript(m_options.scriptPath);
		int line = 0;
		for(const auto& text : m_options.inlineCommands) ParseScriptLine(text, --line);
	}


	// ---- per-frame work (machine thread, at the start of every vertical blank) ----

	void OnVBlank(CRigPad& pad, uint8* ram)
	{
		if(m_finished) return;
		if(m_frame == 0 && m_options.profile)
		{
			prof::Register(0);
			prof::Start();
		}
		m_frame++;

		if(m_options.pcHistogram) m_pcSamples[m_machine.state->nPC]++;

		FlushCollected();
		StepScript();
		pad.Push(m_pads, ram);

		if(m_log && m_logEnabled && (m_frame % m_options.logEvery) == 0) WriteLogRow();

		if(!m_finished && m_hasUntil && m_until.Test(m_machine))
		{
			printf("[frame %" PRIu64 "] --until satisfied: %s\n", m_frame, m_until.text.c_str());
			Finish(0);
		}
		if(!m_finished && m_scriptDone && m_options.frames == 0 && !m_hasUntil) Finish(0);
		if(!m_finished && m_options.frames != 0 && m_frame >= m_options.frames)
		{
			if(m_hasUntil)
			{
				printf("[frame %" PRIu64 "] frame limit reached before --until %s\n", m_frame, m_until.text.c_str());
				Finish(3);
			}
			else
				Finish(m_scriptDone ? 0 : 4);
		}
	}

	// ---- break notification (machine thread) ---------------------------------------

	void OnRunningStateChange()
	{
		// The signal is also raised by Pause() and Resume() on the main thread.
		if(std::this_thread::get_id() == m_mainThread) return;
		if(m_finished) return;
		auto& context = m_vm.m_ee->m_EE;
#ifdef DEBUGGER_INCLUDED
		if(!context.m_executor->MustBreak()) return;
#else
		return; // the core was built without break point support
#endif
		uint32 pc = context.m_State.nPC;
		bool keepRunning = true;

		auto pendingReturn = m_returnBreaks.find(pc);
		if(pendingReturn != m_returnBreaks.end() && !pendingReturn->second.empty())
		{
			// a return address of a function logged with 'ret'; the stack pointer tells
			// recursive and unrelated arrivals apart
			auto& list = pendingReturn->second;
			uint32 sp = m_machine.Reg(CMIPS::SP);
			for(size_t i = list.size(); i-- > 0;)
			{
				if(list[i].sp != sp) continue;
				float f0 = 0;
				memcpy(&f0, &context.m_State.nCOP1[0], 4);
				BreakPrint("frame=%" PRIu64 " ret=%s v0=%08x v1=%08x f0=%.9g\n", m_frame, list[i].name.c_str(), m_machine.Reg(CMIPS::V0), m_machine.Reg(CMIPS::V1), f0);
				list.erase(list.begin() + i);
				break;
			}
			if(list.empty() && m_breaks.find(pc) == m_breaks.end()) SetBreakpoint(pc, false);
		}

		auto found = m_breaks.find(pc);
		if(found != m_breaks.end())
		{
			auto& spec = found->second;
			spec.hits++;
			bool logThis = !spec.quiet && (spec.limit == 0 || spec.hits <= spec.limit);
			if(logThis) LogBreak(spec);
			if(spec.logReturn && logThis)
			{
				uint32 ra = m_machine.Reg(CMIPS::RA);
				auto& list = m_returnBreaks[ra];
				if(list.empty() && m_breaks.find(ra) == m_breaks.end()) SetBreakpoint(ra, true);
				list.push_back({m_machine.Reg(CMIPS::SP), spec.name});
			}
			if(spec.stop)
			{
				printf("[frame %" PRIu64 "] stop at break %s (pc %08x)\n", m_frame, spec.name.c_str(), pc);
				keepRunning = false;
				Finish(0);
			}
		}
		// A block is tested for break points when it is entered, so a break point that
		// is not at the start of a translated block reports the block's first address.
		// Such arrivals are passed over silently.
		if(keepRunning) m_vm.ResumeImpl();
	}

	// ---- results (main thread, after the machine has stopped) ----------------------

	void WaitFinished()
	{
		std::unique_lock<std::mutex> lock(m_doneMutex);
		m_doneCondition.wait(lock, [this]() { return m_finished.load(); });
	}

	void WaitPendingSaves()
	{
		for(auto& pending : m_pendingSaves)
		{
			bool ok = pending.second.get();
			printf("state %s: %s\n", ok ? "saved" : "NOT saved", pending.first.c_str());
			if(!ok) m_exitCode = 5;
		}
		m_pendingSaves.clear();
	}

	void Summary(double seconds)
	{
		printf("frames=%" PRIu64 " wall=%.2fs fps=%.1f (%.2fx real time at 59.94) pc=%08x %s\n",
		       m_frame, seconds, seconds > 0 ? m_frame / seconds : 0, seconds > 0 ? (m_frame / seconds) / 59.94 : 0,
		       m_machine.state->nPC, Symbolize(m_machine.state->nPC).c_str());
		printf("  code-page protect requests=%" PRIu64 " unprotect=%" PRIu64 "%s\n", g_protectRequests.load(), g_unprotectRequests.load(), g_noCodeProtect ? " (protection off)" : "");
		for(const auto& watch : m_watches)
		{
			uint32 address = watch.expr.Eval(m_machine);
			printf("  %s @%08x = %s\n", watch.name.c_str(), address, FormatValue(ReadValue(m_machine, address, watch.type), watch.type).c_str());
		}
		for(const auto& entry : m_breaks)
		{
			printf("  break %s @%08x hits=%" PRIu64 "\n", entry.second.name.c_str(), entry.first, entry.second.hits);
		}
		if(m_options.pcHistogram)
		{
			std::vector<std::pair<uint64, uint32>> sorted;
			for(const auto& sample : m_pcSamples) sorted.push_back({sample.second, sample.first});
			std::sort(sorted.rbegin(), sorted.rend());
			printf("  pc at vblank, most frequent first:\n");
			for(size_t i = 0; i < sorted.size() && i < 12; i++)
			{
				printf("    %8" PRIu64 "  %08x %s\n", sorted[i].first, sorted[i].second, Symbolize(sorted[i].second).c_str());
			}
		}
		if(m_log) fclose(m_log);
		if(m_breakLog) fclose(m_breakLog);
	}

	int ExitCode() const
	{
		return m_exitCode;
	}
	uint64 Frame() const
	{
		return m_frame;
	}

private:
	// ---- memory -------------------------------------------------------------------

	// Writes guest memory from the host. Translated code covering the touched host
	// pages is discarded first (which also lifts the write protection Play! puts on
	// pages that hold translated code), so patched instructions take effect.
	bool Poke(uint32 address, const void* data, uint32 length)
	{
		uint8* p = m_machine.Ptr(address, length);
		if(!p) return false;
		if((address & 0xF0000000) != 0x70000000)
		{
			uint32 physical = address & 0x1FFFFFFF;
			uint32 start = physical & ~(m_pageSize - 1);
			uint32 end = (physical + length + m_pageSize - 1) & ~(m_pageSize - 1);
			if(end > PS2::EE_RAM_SIZE) end = PS2::EE_RAM_SIZE;
			m_vm.m_ee->m_EE.m_executor->ClearActiveBlocksInRange(start, end, false);
		}
		memcpy(p, data, length);
		return true;
	}

	void SetBreakpoint(uint32 address, bool enable)
	{
		auto& context = m_vm.m_ee->m_EE;
		bool present = context.m_breakpoints.count(address) != 0;
		if(present == enable) return;
		context.ToggleBreakpoint(address);
		uint32 start = address & ~(m_pageSize - 1);
		context.m_executor->ClearActiveBlocksInRange(start, start + m_pageSize, false);
	}

	// ---- break points ---------------------------------------------------------------

	// addr[,name=N][,str=REG][,mem=EXPR:LEN][,val=NAME=EXPR:TYPE][,ret][,stop][,quiet][,limit=N]
	BreakSpec ParseBreak(const std::string& text)
	{
		// commas inside brackets do not occur in expressions, so a plain split is enough
		auto parts = SplitChar(text, ',');
		if(parts.empty()) Die("empty break specification");
		BreakSpec spec;
		spec.address = ExprParser(parts[0]).Parse().Eval(m_machine) & 0x1FFFFFFF;
		spec.name = Symbolize(spec.address);
		if(spec.name.empty()) spec.name = StrFormat("%08x", spec.address);
		for(size_t i = 1; i < parts.size(); i++)
		{
			const auto& part = parts[i];
			auto equals = part.find('=');
			std::string key = part.substr(0, equals);
			std::string value = (equals == std::string::npos) ? "" : part.substr(equals + 1);
			if(key == "name")
				spec.name = value;
			else if(key == "str")
			{
				int index = RegisterIndex(value);
				if(index < 0) Die("break: unknown register '%s'", value.c_str());
				spec.strings.push_back({value, index});
			}
			else if(key == "wstr")
			{
				// wstr=REG or wstr=REG:LENREG
				auto pieces = SplitChar(value, ':');
				BreakSpec::WIDE wide;
				wide.name = pieces[0];
				wide.pointerRegister = RegisterIndex(pieces[0]);
				wide.lengthRegister = (pieces.size() > 1) ? RegisterIndex(pieces[1]) : -1;
				if(wide.pointerRegister < 0 || (pieces.size() > 1 && wide.lengthRegister < 0)) Die("break: wstr=REG[:LENREG], got '%s'", value.c_str());
				spec.wideStrings.push_back(wide);
			}
			else if(key == "collect")
				spec.collect = true;
			else if(key == "mem")
			{
				std::string exprText, lengthText;
				SplitTyped(value, exprText, lengthText);
				int64_t length = 0;
				if(!ParseNumber(lengthText, length) || length <= 0 || length > 4096) Die("break: mem=EXPR:LENGTH, got '%s'", value.c_str());
				spec.memory.push_back({ExprParser(exprText).Parse(), static_cast<uint32>(length), exprText});
			}
			else if(key == "val")
				spec.values.push_back(ParseWatch(value));
			else if(key == "ret")
				spec.logReturn = true;
			else if(key == "stop")
				spec.stop = true;
			else if(key == "quiet")
				spec.quiet = true;
			else if(key == "limit")
			{
				int64_t limit = 0;
				if(!ParseNumber(value, limit)) Die("break: bad limit '%s'", value.c_str());
				spec.limit = static_cast<uint64>(limit);
			}
			else
				Die("break: unknown option '%s'", part.c_str());
		}
		return spec;
	}

	void AddBreak(const BreakSpec& spec)
	{
		m_breaks[spec.address] = spec;
		SetBreakpoint(spec.address, true);
	}

	void BreakPrint(const char* fmt, ...)
	{
		va_list args;
		va_start(args, fmt);
		vfprintf(m_breakLog ? m_breakLog : stdout, fmt, args);
		va_end(args);
	}

	std::string ReadWide(const BreakSpec::WIDE& wide)
	{
		uint32 address = m_machine.Reg(wide.pointerRegister);
		uint32 limit = 200;
		if(wide.lengthRegister >= 0)
		{
			uint32 length = m_machine.Reg(wide.lengthRegister);
			if(length >= 1 && length < limit) limit = length;
		}
		std::string text;
		for(uint32 i = 0; i < limit; i++)
		{
			const uint8* p = m_machine.Ptr(address + i * 2, 2);
			if(!p) break;
			uint16 c = static_cast<uint16>(p[0] | (p[1] << 8));
			if(c == 0) break;
			if(c >= 0x20 && c < 0x7f)
				text += static_cast<char>(c);
			else
				text += StrFormat("\\u%04x", c);
		}
		return text;
	}

	void LogBreak(const BreakSpec& spec)
	{
		if(spec.collect)
		{
			// repeated strings are kept once; so are the tails of a string that a
			// word-wrapping caller passes again line by line
			auto add = [this](const std::string& text) {
				for(const auto& seen : m_collected)
				{
					if(seen.size() >= text.size() && seen.compare(seen.size() - text.size(), text.size(), text) == 0) return;
				}
				m_collected.push_back(text);
			};
			for(const auto& wide : spec.wideStrings) add(ReadWide(wide));
			for(const auto& entry : spec.strings)
			{
				TypeSpec type;
				type.kind = TypeSpec::STR;
				type.size = 160;
				add(Escape(ReadValue(m_machine, m_machine.Reg(entry.second), type).text));
			}
			return;
		}
		const auto& state = *m_machine.state;
		std::string line = StrFormat("frame=%" PRIu64 " bp=%s pc=%08x ra=%08x", m_frame, spec.name.c_str(), state.nPC, m_machine.Reg(CMIPS::RA));
		std::string caller = Symbolize(m_machine.Reg(CMIPS::RA));
		if(!caller.empty()) line += "(" + caller + ")";
		static const int shown[] = {CMIPS::A0, CMIPS::A1, CMIPS::A2, CMIPS::A3, CMIPS::T0, CMIPS::T1, CMIPS::T2, CMIPS::T3, CMIPS::V0, CMIPS::SP};
		for(int index : shown) line += StrFormat(" %s=%08x", g_regNames[index], m_machine.Reg(index));
		for(int i = 12; i < 16; i++)
		{
			float value = 0;
			memcpy(&value, &state.nCOP1[i], 4);
			line += StrFormat(" f%d=%.7g", i, value);
		}
		for(const auto& entry : spec.strings)
		{
			TypeSpec type;
			type.kind = TypeSpec::STR;
			type.size = 160;
			Value value = ReadValue(m_machine, m_machine.Reg(entry.second), type);
			line += StrFormat(" %s->\"%s\"", entry.first.c_str(), Escape(value.text).c_str());
		}
		for(const auto& wide : spec.wideStrings) line += StrFormat(" %s->L\"%s\"", wide.name.c_str(), ReadWide(wide).c_str());
		for(const auto& memory : spec.memory)
		{
			TypeSpec type;
			type.kind = TypeSpec::BYTES;
			type.size = memory.length;
			uint32 address = memory.expr.Eval(m_machine);
			line += StrFormat(" mem[%s=%08x]=%s", memory.text.c_str(), address, ReadValue(m_machine, address, type).text.c_str());
		}
		for(const auto& watch : spec.values)
		{
			uint32 address = watch.expr.Eval(m_machine);
			line += StrFormat(" %s=%s", watch.name.c_str(), FormatValue(ReadValue(m_machine, address, watch.type), watch.type).c_str());
		}
		BreakPrint("%s\n", line.c_str());
	}

	// ---- script ---------------------------------------------------------------------

	void LoadScript(const std::string& path)
	{
		std::ifstream file(path);
		if(!file) Die("cannot read script %s", path.c_str());
		std::string line;
		int number = 0;
		while(std::getline(file, line)) ParseScriptLine(line, ++number);
	}

	void ParseScriptLine(const std::string& lineText, int lineNumber)
	{
		auto tokens = Tokenize(lineText);
		if(tokens.empty()) return;
		Command command;
		command.line = lineNumber;
		size_t i = 0;
		std::string word = Lower(tokens[i++]);
		auto need = [&](size_t count) {
			if(tokens.size() < i + count) Die("script line %d: '%s' needs more arguments", lineNumber, word.c_str());
		};
		auto number = [&](const std::string& text) {
			int64_t value = 0;
			if(!ParseNumber(text, value)) Die("script line %d: bad number '%s'", lineNumber, text.c_str());
			return value;
		};

		// "<frame> <buttons> [lx ly [rx ry]]": the whole pad state from that frame on
		if(isdigit(static_cast<unsigned char>(word[0])))
		{
			Command at;
			at.kind = Command::AT;
			at.line = lineNumber;
			at.number = number(word);
			m_commands.push_back(at);
			word = "pad";
		}
		// optional controller port
		if(word.size() > 1 && (word.back() == '1' || word.back() == '2') && (word.compare(0, word.size() - 1, "press") == 0 || word.compare(0, word.size() - 1, "release") == 0 || word.compare(0, word.size() - 1, "tap") == 0 || word.compare(0, word.size() - 1, "stick") == 0 || word.compare(0, word.size() - 1, "pad") == 0))
		{
			command.port = word.back() - '1';
			word.pop_back();
		}

		if(word == "wait")
		{
			need(1);
			command.kind = Command::WAIT;
			command.number = number(tokens[i]);
		}
		else if(word == "at")
		{
			need(1);
			command.kind = Command::AT;
			command.number = number(tokens[i]);
		}
		else if(word == "until")
		{
			command.kind = Command::UNTIL;
			size_t next = 0;
			command.condition = ParseCondition(tokens, i, next);
			command.number = 0;
			if(next < tokens.size() && Lower(tokens[next]) == "timeout")
			{
				if(next + 1 >= tokens.size()) Die("script line %d: timeout needs a frame count", lineNumber);
				command.number = number(tokens[next + 1]);
				next += 2;
			}
			if(next < tokens.size() && Lower(tokens[next]) == "continue") command.flag = true;
		}
		else if(word == "press" || word == "release")
		{
			need(1);
			command.kind = (word == "press") ? Command::PRESS : Command::RELEASE;
			command.buttons = ParseButtons(tokens[i]);
		}
		else if(word == "tap")
		{
			need(1);
			command.kind = Command::TAP;
			command.buttons = ParseButtons(tokens[i]);
			command.number = (tokens.size() > i + 1) ? number(tokens[i + 1]) : 3;
			command.number2 = (tokens.size() > i + 2) ? number(tokens[i + 2]) : 0;
		}
		else if(word == "stick")
		{
			need(3);
			command.kind = Command::STICK;
			std::string which = Lower(tokens[i]);
			if(which != "l" && which != "r" && which != "left" && which != "right") Die("script line %d: stick L|R x y", lineNumber);
			command.axisFirst = (which[0] == 'l') ? 0 : 2;
			command.axisCount = 2;
			command.axis[0] = static_cast<uint8>(number(tokens[i + 1]));
			command.axis[1] = static_cast<uint8>(number(tokens[i + 2]));
		}
		else if(word == "pad")
		{
			need(1);
			command.kind = Command::PAD;
			command.buttons = ParseButtons(tokens[i]);
			command.axisCount = 0;
			for(size_t k = 0; k < 4 && i + 1 + k < tokens.size(); k++)
			{
				command.axis[k] = static_cast<uint8>(number(tokens[i + 1 + k]));
				command.axisCount = static_cast<int>(k + 1);
			}
		}
		else if(word == "poke")
		{
			// poke <expr:type> <value>      (type as for watches; hexN takes hex digits)
			need(2);
			command.kind = Command::POKE;
			command.target = ParseWatch(tokens[i]);
			const auto& type = command.target.type;
			const std::string& valueText = tokens[i + 1];
			if(type.kind == TypeSpec::FLOAT)
			{
				float value = strtof(valueText.c_str(), nullptr);
				command.bytes.resize(4);
				memcpy(command.bytes.data(), &value, 4);
			}
			else if(type.kind == TypeSpec::STR)
			{
				command.bytes.assign(valueText.begin(), valueText.end());
				command.bytes.push_back(0);
			}
			else if(type.kind == TypeSpec::BYTES)
			{
				if(valueText.size() % 2) Die("script line %d: odd number of hex digits", lineNumber);
				for(size_t k = 0; k + 1 < valueText.size(); k += 2) command.bytes.push_back(static_cast<uint8>(strtoul(valueText.substr(k, 2).c_str(), nullptr, 16)));
			}
			else
			{
				int64_t value = (type.kind == TypeSpec::HEXINT) ? static_cast<int64_t>(strtoull(valueText.c_str(), nullptr, 16)) : number(valueText);
				command.bytes.resize(type.size);
				memcpy(command.bytes.data(), &value, type.size);
			}
		}
		else if(word == "pnach")
		{
			need(2);
			command.kind = Command::PNACH;
			command.text = tokens[i];
			command.text2 = tokens[i + 1];
			ReadPnachSection(command.text, command.text2); // fail early
		}
		else if(word == "save" || word == "load")
		{
			need(1);
			command.kind = (word == "save") ? Command::SAVE : Command::LOAD;
			command.text = tokens[i];
		}
		else if(word == "dump")
		{
			need(3);
			command.kind = Command::DUMP;
			command.target.expr = ExprParser(tokens[i]).Parse();
			command.number = number(tokens[i + 1]);
			command.text = tokens[i + 2];
		}
		else if(word == "show")
		{
			need(1);
			command.kind = Command::SHOW;
			for(size_t k = i; k < tokens.size(); k++) command.watches.push_back(ParseWatch(tokens[k]));
		}
		else if(word == "echo")
		{
			command.kind = Command::ECHO;
			for(size_t k = i; k < tokens.size(); k++) command.text += (k > i ? " " : "") + tokens[k];
		}
		else if(word == "log")
		{
			need(1);
			command.kind = Command::LOG;
			command.flag = (Lower(tokens[i]) == "on");
		}
		else if(word == "break")
		{
			need(1);
			command.kind = Command::BREAK;
			command.text = tokens[i];
		}
		else if(word == "unbreak")
		{
			need(1);
			command.kind = Command::UNBREAK;
			command.target.expr = ExprParser(tokens[i]).Parse();
		}
		else if(word == "sync")
		{
			command.kind = Command::SYNC;
			command.text = (tokens.size() > i) ? tokens[i] : "";
		}
		else if(word == "quit")
		{
			command.kind = Command::QUIT;
		}
		else
			Die("script line %d: unknown command '%s'", lineNumber, word.c_str());
		m_commands.push_back(command);
	}

	void StepScript()
	{
		try
		{
			StepScriptInner();
		}
		catch(const RigError& error)
		{
			// a command that failed while running (bad break specification, missing file)
			printf("[error] %s\n", error.what());
			m_scriptPosition++;
			if(!m_options.interactive) Finish(2);
		}
	}

	void StepScriptInner()
	{
		while(!m_finished)
		{
			if(m_scriptPosition >= m_commands.size())
			{
				if(!m_options.interactive || m_inputClosed) break;
				if(!ReadInteractiveCommand())
				{
					m_inputClosed = true;
					break;
				}
			}
			Command& command = m_commands[m_scriptPosition];
			PadState& pad = m_pads[command.port];
			switch(command.kind)
			{
			case Command::WAIT:
				if(!command.started)
				{
					command.started = true;
					command.deadline = m_frame + command.number;
				}
				if(m_frame < command.deadline) return;
				break;
			case Command::AT:
				if(m_frame < static_cast<uint64>(command.number)) return;
				break;
			case Command::UNTIL:
				if(!command.started)
				{
					command.started = true;
					command.deadline = command.number ? m_frame + command.number : 0;
					if(command.condition.op == Condition::CHANGED)
					{
						command.condition.reference = ReadValue(m_machine, command.condition.watch.expr.Eval(m_machine), command.condition.watch.type);
					}
				}
				if(!command.condition.Test(m_machine))
				{
					if(command.deadline && m_frame >= command.deadline)
					{
						printf("[frame %" PRIu64 "] TIMEOUT line %d: until %s\n", m_frame, command.line, command.condition.text.c_str());
						if(!command.flag)
						{
							Finish(3);
							return;
						}
						break;
					}
					return;
				}
				printf("[frame %" PRIu64 "] until %s\n", m_frame, command.condition.text.c_str());
				break;
			case Command::PRESS:
				pad.buttons |= command.buttons;
				break;
			case Command::RELEASE:
				pad.buttons &= ~command.buttons;
				break;
			case Command::TAP:
				// held for 'number' frames, then released for 'number2' frames
				if(!command.started)
				{
					command.started = true;
					pad.buttons |= command.buttons;
					command.deadline = m_frame + command.number;
					return;
				}
				if(m_frame < command.deadline) return;
				pad.buttons &= ~command.buttons;
				if(command.number2 > 0 && m_frame < command.deadline + command.number2) return;
				break;
			case Command::STICK:
				for(int k = 0; k < command.axisCount; k++) pad.axis[command.axisFirst + k] = command.axis[k];
				break;
			case Command::PAD:
				pad.buttons = command.buttons;
				for(int k = 0; k < 4; k++) pad.axis[k] = (k < command.axisCount) ? command.axis[k] : 0x80;
				break;
			case Command::POKE:
			{
				uint32 address = command.target.expr.Eval(m_machine);
				if(!Poke(address, command.bytes.data(), static_cast<uint32>(command.bytes.size())))
				{
					printf("[frame %" PRIu64 "] poke %s: address %08x is not mapped\n", m_frame, command.target.name.c_str(), address);
				}
			}
			break;
			case Command::PNACH:
			{
				auto words = ReadPnachSection(command.text, command.text2);
				for(const auto& word : words)
				{
					uint32 before = m_machine.Read32(word.address);
					Poke(word.address, &word.value, 4);
					printf("[frame %" PRIu64 "] patch [%s] %08x: %08x -> %08x\n", m_frame, command.text2.c_str(), word.address, before, word.value);
				}
			}
			break;
			case Command::SAVE:
				if(!command.started)
				{
					command.started = true;
					m_pendingSaves.push_back({command.text, m_vm.SaveState(command.text)});
					return; // written by the machine thread before the next frame
				}
				break;
			case Command::LOAD:
				if(!command.started)
				{
					command.started = true;
					m_pendingLoads.push_back(m_vm.LoadState(command.text));
					return;
				}
				break;
			case Command::DUMP:
			{
				uint32 address = command.target.expr.Eval(m_machine);
				uint32 length = static_cast<uint32>(command.number);
				const uint8* p = m_machine.Ptr(address, length);
				FILE* file = p ? fopen(command.text.c_str(), "wb") : nullptr;
				if(file)
				{
					fwrite(p, 1, length, file);
					fclose(file);
					printf("[frame %" PRIu64 "] dumped %08x+%x to %s\n", m_frame, address, length, command.text.c_str());
				}
				else
					printf("[frame %" PRIu64 "] dump failed: %s\n", m_frame, command.text.c_str());
			}
			break;
			case Command::SHOW:
			{
				std::string line = StrFormat("[frame %" PRIu64 "]", m_frame);
				for(const auto& watch : command.watches)
				{
					uint32 address = watch.expr.Eval(m_machine);
					line += StrFormat(" %s@%08x=%s", watch.name.c_str(), address, FormatValue(ReadValue(m_machine, address, watch.type), watch.type).c_str());
				}
				printf("%s\n", line.c_str());
			}
			break;
			case Command::ECHO:
				printf("[frame %" PRIu64 "] %s\n", m_frame, command.text.c_str());
				break;
			case Command::LOG:
				m_logEnabled = command.flag;
				break;
			case Command::BREAK:
				AddBreak(ParseBreak(command.text));
				break;
			case Command::UNBREAK:
			{
				uint32 address = command.target.expr.Eval(m_machine) & 0x1FFFFFFF;
				m_breaks.erase(address);
				SetBreakpoint(address, false);
			}
			break;
			case Command::SYNC:
				printf("[sync %s] frame=%" PRIu64 "\n", command.text.c_str(), m_frame);
				FlushOutputs();
				break;
			case Command::QUIT:
				Finish(0);
				return;
			}
			m_scriptPosition++;
		}
		if(m_scriptPosition >= m_commands.size()) m_scriptDone = true;
	}

	void FlushOutputs()
	{
		fflush(stdout);
		if(m_log) fflush(m_log);
		if(m_breakLog) fflush(m_breakLog);
	}

	// Interactive sessions: when the script has run out, the machine thread waits here
	// for the next command line on standard input. The emulated machine does not
	// advance meanwhile. Returns false at end of input.
	bool ReadInteractiveCommand()
	{
		FlushOutputs();
		std::string line;
		while(std::getline(std::cin, line))
		{
			size_t before = m_commands.size();
			try
			{
				ParseScriptLine(line, 0);
			}
			catch(const RigError& error)
			{
				printf("[error] %s\n", error.what());
				m_commands.resize(before);
				FlushOutputs();
				continue;
			}
			if(m_commands.size() > before) return true;
		}
		return false;
	}

	// Strings gathered by 'collect' break points since the last vertical blank. They are
	// printed only when the set differs from the previous frame's, which gives a
	// transcript of what the game put on the screen.
	void FlushCollected()
	{
		if(m_collected.empty() && m_lastCollected.empty()) return;
		if(m_collected != m_lastCollected)
		{
			std::string line = StrFormat("frame=%" PRIu64 " screen:", m_frame);
			for(const auto& text : m_collected) line += " \"" + text + "\"";
			BreakPrint("%s\n", line.c_str());
			m_lastCollected = m_collected;
		}
		m_collected.clear();
	}

	void WriteLogRow()
	{
		std::string row;
		for(const auto& watch : m_watches)
		{
			uint32 address = watch.expr.Eval(m_machine);
			row += "\t";
			row += FormatValue(ReadValue(m_machine, address, watch.type), watch.type);
		}
		if(m_options.logOnChange && row == m_lastLogRow) return;
		m_lastLogRow = row;
		fprintf(m_log, "%" PRIu64 "%s\n", m_frame, row.c_str());
	}

	void Finish(int exitCode)
	{
		if(m_finished) return;
		m_exitCode = exitCode;
		{
			std::lock_guard<std::mutex> lock(m_doneMutex);
			m_finished = true;
		}
		m_doneCondition.notify_all();
	}

	CRigVM& m_vm;
	const Options& m_options;
	Machine m_machine;
	uint32 m_pageSize = 0x4000;
	std::thread::id m_mainThread = std::this_thread::get_id(); // the rig is made on the main thread

	uint64 m_frame = 0;
	PadState m_pads[2];

	std::vector<Watch> m_watches;
	FILE* m_log = nullptr;
	bool m_logEnabled = true;
	std::string m_lastLogRow;

	FILE* m_breakLog = nullptr;
	std::map<uint32, BreakSpec> m_breaks;
	struct PENDING_RETURN
	{
		uint32 sp;
		std::string name;
	};
	std::map<uint32, std::vector<PENDING_RETURN>> m_returnBreaks;
	std::vector<std::string> m_collected;
	std::vector<std::string> m_lastCollected;

	std::vector<Command> m_commands;
	size_t m_scriptPosition = 0;
	bool m_scriptDone = false;
	bool m_inputClosed = false;

	Condition m_until;
	bool m_hasUntil = false;

	std::vector<std::pair<std::string, std::future<bool>>> m_pendingSaves;
	std::vector<std::future<bool>> m_pendingLoads;

	std::map<uint32, uint64> m_pcSamples;

	std::atomic<bool> m_finished{false};
	int m_exitCode = 0;
	std::mutex m_doneMutex;
	std::condition_variable m_doneCondition;
};

void CRigPad::Update(uint8* ram)
{
	m_rig.OnVBlank(*this, ram);
}

// ---------------------------------------------------------------------------------

static void Usage()
{
	printf(
	    "rta_rig --disc <image> [options]\n"
	    "  --data <dir>           emulator data directory (memory cards, config, logs); default ./rig-data\n"
	    "  --arg <text>           argument passed to the game's main(); repeatable\n"
	    "  --load <state>         load an emulator state after booting\n"
	    "  --save-at-end <state>  save an emulator state when the run ends\n"
	    "  --frames <n>           stop after n frames (vertical blanks) of this run\n"
	    "  --script <file>        commands, run in order (see README.md)\n"
	    "  --do \"<command>\"       one script command; repeatable, run after --script\n"
	    "  --interactive          then read further commands from standard input, one per line;\n"
	    "                         the machine stands still while waiting\n"
	    "  --until <expr:type> <op> <value>   stop when true (exit code 3 if --frames comes first)\n"
	    "  --sym <file.tsv>       symbol file (hex address, name); repeatable\n"
	    "  --watch <name=expr:type>           value to log; repeatable\n"
	    "  --watch-file <file>    one watch per line\n"
	    "  --log <file.tsv>       write the watches every frame\n"
	    "  --log-every <n>        ... every n frames\n"
	    "  --log-on-change        ... only rows that differ from the previous one\n"
	    "  --break <addr[,opts]>  log registers when the EE reaches addr; repeatable\n"
	    "                         opts: name=N str=REG wstr=REG[:LENREG] collect mem=EXPR:LEN\n"
	    "                               val=NAME=EXPR:TYPE ret stop quiet limit=N\n"
	    "  --break-log <file>     where break lines go (default: standard output)\n"
	    "  --pc-histogram         sample the EE program counter at every vertical blank\n"
	    "  --play-logs            let Play! write its own logs under <data>/logs\n"
	    "  --throttle             run at the console's speed instead of as fast as possible\n"
	    "  --no-code-protect      do not write-protect host pages that hold translated code (see README)\n"
	    "  --profile              sample the machine and video threads; print where wall time went\n");
}

static int Run(int argc, char** argv);

int main(int argc, char** argv)
{
	try
	{
		return Run(argc, argv);
	}
	catch(const RigError& error)
	{
		fprintf(stderr, "rta_rig: %s\n", error.what());
		return 2;
	}
}

static int Run(int argc, char** argv)
{
	Options options;
	for(int i = 1; i < argc; i++)
	{
		std::string arg = argv[i];
		auto value = [&]() -> std::string {
			if(i + 1 >= argc) Die("%s needs a value", arg.c_str());
			return argv[++i];
		};
		if(arg == "--disc")
			options.disc = value();
		else if(arg == "--data")
			options.data = value();
		else if(arg == "--arg")
			options.arguments.push_back(value());
		else if(arg == "--load")
			options.loadState = value();
		else if(arg == "--save-at-end")
			options.saveStateAtEnd = value();
		else if(arg == "--frames")
			options.frames = strtoull(value().c_str(), nullptr, 0);
		else if(arg == "--script")
			options.scriptPath = value();
		else if(arg == "--do")
			options.inlineCommands.push_back(value());
		else if(arg == "--until")
		{
			options.untilTokens.push_back(value());
			options.untilTokens.push_back(value());
			if(options.untilTokens.back() != "changed") options.untilTokens.push_back(value());
		}
		else if(arg == "--sym")
			LoadSymbolFile(value());
		else if(arg == "--watch")
			options.watchSpecs.push_back(value());
		else if(arg == "--watch-file")
		{
			std::string path = value();
			std::ifstream file(path);
			if(!file) Die("cannot read %s", path.c_str());
			std::string line;
			while(std::getline(file, line))
			{
				auto tokens = Tokenize(line);
				if(!tokens.empty()) options.watchSpecs.push_back(tokens[0]);
			}
		}
		else if(arg == "--log")
			options.logPath = value();
		else if(arg == "--log-every")
			options.logEvery = std::max<uint32>(1, static_cast<uint32>(strtoul(value().c_str(), nullptr, 0)));
		else if(arg == "--log-on-change")
			options.logOnChange = true;
		else if(arg == "--break")
			options.breakSpecs.push_back(value());
		else if(arg == "--break-log")
			options.breakLogPath = value();
		else if(arg == "--pc-histogram")
			options.pcHistogram = true;
		else if(arg == "--play-logs")
			options.playLogs = true;
		else if(arg == "--throttle")
			options.throttle = true;
		else if(arg == "--no-code-protect")
			options.noCodeProtect = true;
		else if(arg == "--profile")
			options.profile = true;
		else if(arg == "--interactive")
			options.interactive = true;
		else if(arg == "--help" || arg == "-h")
		{
			Usage();
			return 0;
		}
		else
			Die("unknown option %s (try --help)", arg.c_str());
	}
	if(options.disc.empty())
	{
		Usage();
		return 2;
	}
	if(!fs::exists(options.disc)) Die("disc image not found: %s", options.disc.c_str());
	if(options.frames == 0 && options.scriptPath.empty() && options.inlineCommands.empty() && options.untilTokens.empty() && !options.interactive) options.frames = 600;

	setvbuf(stdout, nullptr, _IOLBF, 0);

	g_basePath = fs::absolute(options.data);
	fs::create_directories(g_basePath);

	// Preferences must exist before the objects that read them are made.
	CAppConfig::GetInstance().RegisterPreferenceBoolean("log.showprints", false);
	CAppConfig::GetInstance().SetPreferenceBoolean("log.showprints", options.playLogs);

	CRigVM vm;
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_CDROM0_PATH, fs::absolute(options.disc));
	CAppConfig::GetInstance().SetPreferenceBoolean(PREF_PS2_LIMIT_FRAMERATE, options.throttle);

	CRig rig(vm, options);
	CRigPad* padHandler = nullptr;

	vm.Initialize();
	vm.CreateGSHandler(CRigGsNull::GetFactoryFunction());
	vm.CreatePadHandler([&]() {
		padHandler = new CRigPad(rig);
		return padHandler;
	});
	vm.ReloadFrameRateLimit();

	try
	{
		if(options.arguments.empty())
		{
			vm.m_ee->m_os->BootFromCDROM();
		}
		else
		{
			// same as BootFromCDROM, with arguments for main()
			auto ioman = vm.m_iop->m_bios ? dynamic_cast<CIopBios*>(vm.m_iop->m_bios.get())->GetIoman() : nullptr;
			if(!ioman) Die("no IOP file manager");
			uint32 handle = ioman->Open(Iop::Ioman::CDevice::OPEN_FLAG_RDONLY, "cdrom0:SYSTEM.CNF");
			if(static_cast<int32>(handle) < 0) Die("no SYSTEM.CNF on the disc");
			std::string config;
			{
				auto stream = ioman->GetFileStream(handle);
				char buffer[512] = {};
				auto length = stream->Read(buffer, sizeof(buffer) - 1);
				config.assign(buffer, static_cast<size_t>(length));
			}
			ioman->Close(handle);
			auto boot = config.find("BOOT2");
			auto start = (boot == std::string::npos) ? boot : config.find("cdrom0:", boot);
			if(start == std::string::npos) Die("no BOOT2 line in SYSTEM.CNF");
			auto end = config.find_first_of("\r\n", start);
			std::string path = config.substr(start, end == std::string::npos ? end : end - start);
			vm.m_ee->m_os->BootFromVirtualPath(path.c_str(), options.arguments);
		}
	}
	catch(const std::exception& exception)
	{
		Die("boot failed: %s", exception.what());
	}
	printf("booted %s\n", vm.m_ee->m_os->GetExecutableName());

	if(!options.loadState.empty())
	{
		if(!vm.LoadState(options.loadState).get()) Die("cannot load state %s", options.loadState.c_str());
		printf("state loaded: %s\n", options.loadState.c_str());
	}

	rig.Prepare();
	auto connection = vm.OnRunningStateChange.Connect([&]() { rig.OnRunningStateChange(); });

	auto startTime = std::chrono::steady_clock::now();
	vm.Resume();
	rig.WaitFinished();
	vm.Pause();
	double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - startTime).count();

	rig.WaitPendingSaves();
	int exitCode = rig.ExitCode();
	if(!options.saveStateAtEnd.empty())
	{
		bool ok = vm.SaveState(options.saveStateAtEnd).get();
		printf("state %s: %s\n", ok ? "saved" : "NOT saved", options.saveStateAtEnd.c_str());
		if(!ok) exitCode = 5;
	}
	rig.Summary(seconds);
	prof::Report();

	connection.reset();
	vm.DestroyPadHandler();
	vm.DestroyGSHandler();
	vm.Destroy();
	return exitCode;
}
