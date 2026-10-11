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
#include <deque>
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
#include <set>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <dlfcn.h>
#include <fenv.h>
#include <execinfo.h>
#include <pthread.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/un.h>
#include <unistd.h>

// The Ethernet chip emulation is used with one private member reachable: its receive
// descriptor index wraps at the wrong number (512 instead of 64), and the rig puts that
// right from outside rather than changing Play! (CRig::EtherDeliver).
#define private public
#include "iop/Iop_Speed.h"
#undef private
#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "AppConfig.h"
#include "Ps2Const.h"
#include "gs/GSH_Null.h"
#include "gs/GSHandler.h"
#include "ee/PS2OS.h"
#include "ee/EeExecutor.h"
#include "iop/IopBios.h"
#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
#define GL_SILENCE_DEPRECATION
#include <OpenGL/OpenGL.h>
#include <OpenGL/gl3.h>
#include "GSH_OpenGL.h"
#endif

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

// A null video handler that reports which thread it runs on (for --profile). Used with
// --video-thread: Play!'s usual arrangement, a video thread fed through a mail box.
#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
// --video: Play!'s OpenGL video handler on a context that has no window, presenting into
// a frame buffer of its own, so that 'shot' can write a picture of the screen. For
// programs whose text the rig cannot read from the game's draw calls (the network
// configuration program on the disc).
class CRigGsOpenGL : public CGSH_OpenGL
{
public:
	enum
	{
		WIDTH = 640,
		HEIGHT = 448,
	};
	static FactoryFunction GetFactoryFunction()
	{
		return []() { return new CRigGsOpenGL(); };
	}
	// 24-bit BMP of what was presented last; the pixels are read on the video thread
	bool Screenshot(const std::string& path)
	{
		std::vector<uint8> pixels(WIDTH * HEIGHT * 4);
		SendGSCall([&]() {
			glBindFramebuffer(GL_READ_FRAMEBUFFER, m_shotFramebuffer);
			glReadPixels(0, 0, WIDTH, HEIGHT, GL_RGBA, GL_UNSIGNED_BYTE, pixels.data());
			glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);
		},
		           true);
		FILE* file = fopen(path.c_str(), "wb");
		if(!file) return false;
		uint32 dataSize = WIDTH * HEIGHT * 3;
		uint8 header[54] = {'B', 'M'};
		auto put32 = [&](int at, uint32 value) { memcpy(header + at, &value, 4); };
		put32(2, 54 + dataSize);
		put32(10, 54);
		put32(14, 40);
		put32(18, WIDTH);
		put32(22, HEIGHT);
		header[26] = 1;
		header[28] = 24;
		put32(34, dataSize);
		fwrite(header, 1, sizeof(header), file);
		std::vector<uint8> row(WIDTH * 3);
		for(uint32 y = 0; y < HEIGHT; y++)
		{
			for(uint32 x = 0; x < WIDTH; x++)
			{
				const uint8* pixel = &pixels[(y * WIDTH + x) * 4];
				row[x * 3 + 0] = pixel[2];
				row[x * 3 + 1] = pixel[1];
				row[x * 3 + 2] = pixel[0];
			}
			fwrite(row.data(), 1, row.size(), file);
		}
		fclose(file);
		return true;
	}

private:
	void InitializeImpl() override
	{
		CGLPixelFormatAttribute attributes[] = {
		    kCGLPFAOpenGLProfile, static_cast<CGLPixelFormatAttribute>(kCGLOGLPVersion_3_2_Core),
		    kCGLPFAColorSize, static_cast<CGLPixelFormatAttribute>(24),
		    kCGLPFAAlphaSize, static_cast<CGLPixelFormatAttribute>(8),
		    static_cast<CGLPixelFormatAttribute>(0)};
		CGLPixelFormatObj format = nullptr;
		GLint count = 0;
		CGLChoosePixelFormat(attributes, &format, &count);
		if(!format || CGLCreateContext(format, nullptr, &m_context) != kCGLNoError)
		{
			fprintf(stderr, "rta_rig: no OpenGL context for --video\n");
			abort();
		}
		CGLDestroyPixelFormat(format);
		CGLSetCurrentContext(m_context);
		glGenFramebuffers(1, &m_shotFramebuffer);
		glGenRenderbuffers(1, &m_shotColor);
		glBindRenderbuffer(GL_RENDERBUFFER, m_shotColor);
		glRenderbufferStorage(GL_RENDERBUFFER, GL_RGBA8, WIDTH, HEIGHT);
		glBindFramebuffer(GL_FRAMEBUFFER, m_shotFramebuffer);
		glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, m_shotColor);
		glBindFramebuffer(GL_FRAMEBUFFER, 0);
		m_presentFramebuffer = m_shotFramebuffer;
		CGSH_OpenGL::InitializeImpl();
		PRESENTATION_PARAMS params;
		params.windowWidth = WIDTH;
		params.windowHeight = HEIGHT;
		params.mode = PRESENTATION_MODE_FILL;
		SetPresentationParams(params);
	}
	void ReleaseImpl() override
	{
		CGSH_OpenGL::ReleaseImpl();
		CGLSetCurrentContext(nullptr);
		CGLDestroyContext(m_context);
	}
	void PresentBackbuffer() override
	{
		glFlush();
	}

	CGLContextObj m_context = nullptr;
	GLuint m_shotFramebuffer = 0, m_shotColor = 0;
};
#endif

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

// The rig's default video handler: null, and without a thread of its own. Play!'s video
// handler takes every register write and image transfer as a queued call. With no video
// thread the calls simply accumulate, and the machine thread empties the queue once per
// frame (Drain, called from the rig's vertical-blank work). Nothing is drawn either way;
// what this buys is that the machine no longer hands work to, and waits for, a second
// thread several thousand times a frame, which on a busy host costs far more than the
// work itself.
//
// The queue can only be emptied through CGSHandler::ProcessSingleFrame, which runs
// queued calls until a flip has happened. Drain therefore queues a marker and then a
// forced flip; flips that arrive before the marker (the machine's own, one per vertical
// blank) are ignored, so the call returns exactly when the queue is empty.
class CRigGsInline : public CGSHandler
{
public:
	CRigGsInline()
	    : CGSHandler(false)
	{
	}

	static FactoryFunction GetFactoryFunction()
	{
		return []() { return new CRigGsInline(); };
	}

	void Drain()
	{
		SendGSCall([this]() { m_drainMarkerReached = true; });
		Flip(FLIP_FLAG_FORCE);
		ProcessSingleFrame();
	}

	void ProcessHostToLocalTransfer() override
	{
	}
	void ProcessLocalToHostTransfer() override
	{
	}
	void ProcessLocalToLocalTransfer() override
	{
	}
	void ProcessClutTransfer(uint32, uint32) override
	{
	}

private:
	void InitializeImpl() override
	{
	}
	void ReleaseImpl() override
	{
	}
	void FlipImpl(const DISPLAY_INFO& displayInfo) override
	{
		if(!m_drainMarkerReached) return;
		m_drainMarkerReached = false;
		CGSHandler::FlipImpl(displayInfo);
	}

	bool m_drainMarkerReached = false;
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
		AND,
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
			case AND:
				sp--;
				stack[sp - 1] &= stack[sp];
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
			else if(Accept('&'))
			{
				ParseProduct(expr);
				expr.code.push_back({Expr::AND, 0});
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
		CRC, // a 32-bit checksum of 'size' bytes, shown in hex
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
	if(sized("crc", TypeSpec::CRC, 16)) return type;
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
	Die("unknown type '%s' (use u8 s8 u16 s16 u32 s32 x8 x16 x32 f32 strN hexN crcN)", text.c_str());
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
	case TypeSpec::CRC:
	{
		// FNV-1a, 32 bits: enough to tell two blocks apart
		uint32 hash = 0x811C9DC5;
		for(uint32 i = 0; i < type.size; i++) hash = (hash ^ p[i]) * 0x01000193;
		value.isText = true;
		value.text = StrFormat("%08x", hash);
	}
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
		TAPUNTIL,
		STICK,
		PAD,
		POKE,
		PNACH,
		SAVE,
		LOAD,
		SHOT,
		IOPDUMP,
		ETHDROP,
		DUMP,
		SHOW,
		ECHO,
		LOG,
		BREAK,
		UNBREAK,
		SYNC,
		NETSHIM,
		FUZZ,
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
	uint64 phaseStart = 0;
	// fuzz
	uint64 rng = 0;
	uint32 fuzzMask = 0;
	uint32 stickHold[2] = {};
	uint32 buttonHold[PS2::CControllerInfo::MAX_BUTTONS] = {};
};

// Random input (script command fuzz). Which buttons may be pressed is chosen by name;
// rates are presses started per thousand frames, holds are in frames.
struct FuzzButton
{
	const char* group;
	PS2::CControllerInfo::BUTTON button;
	uint32 rate;
	uint32 holdMin;
	uint32 holdSpan;
};

static const FuzzButton g_fuzzButtons[] = {
    {"fight", PS2::CControllerInfo::CROSS, 60, 2, 8},
    {"fight", PS2::CControllerInfo::CIRCLE, 10, 2, 20},
    {"fight", PS2::CControllerInfo::TRIANGLE, 10, 2, 20},
    {"fight", PS2::CControllerInfo::R1, 10, 10, 40},
    {"fight", PS2::CControllerInfo::L1, 4, 2, 4},
    {"cast", PS2::CControllerInfo::CIRCLE, 40, 2, 20},
    {"cast", PS2::CControllerInfo::TRIANGLE, 40, 2, 20},
    {"potion", PS2::CControllerInfo::R2, 8, 2, 4},
    {"potion", PS2::CControllerInfo::L2, 8, 2, 4},
    {"use", PS2::CControllerInfo::SQUARE, 15, 2, 6},
    {"dpad", PS2::CControllerInfo::DPAD_UP, 6, 4, 30},
    {"dpad", PS2::CControllerInfo::DPAD_DOWN, 6, 4, 30},
    {"dpad", PS2::CControllerInfo::DPAD_LEFT, 6, 4, 30},
    {"dpad", PS2::CControllerInfo::DPAD_RIGHT, 6, 4, 30},
    {"select", PS2::CControllerInfo::SELECT, 4, 2, 3},
    {"start", PS2::CControllerInfo::START, 3, 2, 3},
    {"l3r3", PS2::CControllerInfo::L3, 2, 2, 3},
    {"l3r3", PS2::CControllerInfo::R3, 2, 2, 3},
};
enum
{
	FUZZ_MOVE = 1u << 30,
	FUZZ_RSTICK = 1u << 31,
};

// ---------------------------------------------------------------------------------
// Two machines (phase 2). Two runner processes are joined by a local stream socket.
// At every vertical blank each runner sends one message - its frame number and the
// datagrams its game sent since the last one - and then waits for the other's message
// with the same frame number. Neither machine can get ahead of the other, and what a
// machine receives depends only on frame numbers, never on host timing, so a pair of
// runs is as repeatable as a single one.
// ---------------------------------------------------------------------------------

struct WireDatagram
{
	uint64 deliverFrame = 0; // first frame of the receiver on which it may be received
	uint8 source[4] = {};
	uint32 sourcePort = 0;
	uint8 destination[4] = {};
	uint32 destinationPort = 0;
	std::vector<uint8> data;
};

class CLink
{
public:
	bool Active() const
	{
		return m_fd >= 0;
	}

	// "listen:<path>" or "connect:<path>" (a Unix-domain socket; keep the path short)
	void Open(const std::string& spec)
	{
		auto colon = spec.find(':');
		if(colon == std::string::npos) Die("--link wants listen:<path> or connect:<path>");
		std::string mode = spec.substr(0, colon), path = spec.substr(colon + 1);
		sockaddr_un address = {};
		address.sun_family = AF_UNIX;
		if(path.size() >= sizeof(address.sun_path)) Die("--link: path too long (%zu characters, limit %zu)", path.size(), sizeof(address.sun_path) - 1);
		strcpy(address.sun_path, path.c_str());
		int fd = socket(AF_UNIX, SOCK_STREAM, 0);
		if(fd < 0) Die("--link: cannot make a socket");
		if(mode == "listen")
		{
			unlink(path.c_str());
			if(bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 || listen(fd, 1) != 0) Die("--link: cannot listen on %s", path.c_str());
			m_fd = accept(fd, nullptr, nullptr);
			close(fd);
			unlink(path.c_str());
			if(m_fd < 0) Die("--link: accept failed");
		}
		else if(mode == "connect")
		{
			for(int attempt = 0; attempt < 600; attempt++)
			{
				if(connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0)
				{
					m_fd = fd;
					break;
				}
				usleep(100000);
			}
			if(m_fd < 0) Die("--link: nobody is listening on %s", path.c_str());
		}
		else
			Die("--link wants listen:<path> or connect:<path>");
	}

	void Send(uint64 frame, bool bye, const std::vector<WireDatagram>& datagrams)
	{
		std::vector<uint8> message;
		auto put32 = [&](uint32 value) { message.insert(message.end(), reinterpret_cast<uint8*>(&value), reinterpret_cast<uint8*>(&value) + 4); };
		auto put64 = [&](uint64 value) { message.insert(message.end(), reinterpret_cast<uint8*>(&value), reinterpret_cast<uint8*>(&value) + 8); };
		put32(MAGIC);
		put32(bye ? 1 : 0);
		put64(frame);
		put32(static_cast<uint32>(datagrams.size()));
		for(const auto& datagram : datagrams)
		{
			put64(datagram.deliverFrame);
			message.insert(message.end(), datagram.source, datagram.source + 4);
			put32(datagram.sourcePort);
			message.insert(message.end(), datagram.destination, datagram.destination + 4);
			put32(datagram.destinationPort);
			put32(static_cast<uint32>(datagram.data.size()));
			message.insert(message.end(), datagram.data.begin(), datagram.data.end());
		}
		WriteAll(message.data(), message.size());
	}

	// false when the connection is gone
	bool Receive(uint64& frame, bool& bye, std::vector<WireDatagram>& datagrams)
	{
		uint32 magic = 0, flags = 0, count = 0;
		if(!ReadAll(&magic, 4) || magic != MAGIC || !ReadAll(&flags, 4) || !ReadAll(&frame, 8) || !ReadAll(&count, 4)) return false;
		bye = (flags & 1) != 0;
		for(uint32 i = 0; i < count; i++)
		{
			WireDatagram datagram;
			uint32 length = 0;
			if(!ReadAll(&datagram.deliverFrame, 8) || !ReadAll(datagram.source, 4) || !ReadAll(&datagram.sourcePort, 4) || !ReadAll(datagram.destination, 4) || !ReadAll(&datagram.destinationPort, 4) || !ReadAll(&length, 4) || length > 0x10000) return false;
			datagram.data.resize(length);
			if(length && !ReadAll(datagram.data.data(), length)) return false;
			datagrams.push_back(std::move(datagram));
		}
		return true;
	}

private:
	enum : uint32
	{
		MAGIC = 0x52494731,
	};

	void WriteAll(const void* data, size_t size)
	{
		auto p = static_cast<const uint8*>(data);
		while(size > 0)
		{
			ssize_t written = write(m_fd, p, size);
			if(written <= 0) return; // the other side is gone; the next Receive reports it
			p += written;
			size -= static_cast<size_t>(written);
		}
	}

	bool ReadAll(void* data, size_t size)
	{
		auto p = static_cast<uint8*>(data);
		while(size > 0)
		{
			ssize_t got = read(m_fd, p, size);
			if(got <= 0) return false;
			p += got;
			size -= static_cast<size_t>(got);
		}
		return true;
	}

	int m_fd = -1;
};

// What the bus between the two machines does to a datagram. All of it is drawn from a
// generator seeded by --bus seed=N (and the machine letter), so it repeats.
struct BusModel
{
	uint32 delay = 0;  // frames added to every datagram that crosses
	uint32 jitter = 0; // up to this many more, drawn per datagram (this is what reorders)
	uint32 lossPerMille = 0;
	uint64 stallAt = 0;     // an outage: nothing sent in frames stallAt .. stallAt + stallFrames - 1 crosses
	uint64 stallFrames = 0;
	uint64 state = 0x9E3779B97F4A7C15ull;

	uint64 Next()
	{
		state ^= state >> 12;
		state ^= state << 25;
		state ^= state >> 27;
		return state * 0x2545F4914F6CDD1Dull;
	}
};

// ---------------------------------------------------------------------------------
// Host calls and the libnet shim (the first piece of phase 2; docs/issues/live-rig.md 4d)
//
// A function of the game is replaced by writing four instructions over its entry:
//
//     lui  $at, 0x1e00
//     sw   $zero, 4*n($at)      ; a store to an address the rig has claimed
//     jr   $ra
//     nop
//
// Play! routes a store outside RAM through its memory map; the rig adds an entry for
// 0x1e000000-0x1e000fff whose handler runs host code for call number n, with the
// function's arguments still in $a0-$a3, $t0-$t3 and on the stack, and puts the result
// in $v0. This needs no break point support and costs one host call.
//
// The shim replaces the entry points of Sony's libnet in the executable (the EE half of
// the network library; addresses from symbols/netlib.tsv) so that the game's own netcode
// can open datagram sockets and exchange datagrams without the IOP network stack or an
// emulated adapter. In this first version the "network" is a bus inside one process: a
// datagram sent to this machine's own address, or to a broadcast address, comes back on
// the next frame; anything else is logged and dropped. Phase 2 replaces the bus by a
// connection to a second runner.
// ---------------------------------------------------------------------------------

class CNetShim
{
public:
	enum
	{
		PORT_BASE = 0x1E000000,
		PORT_SIZE = 0x1000,
		ERROR_NO_DATA = -500, // what sceInetRecvFrom returns when nothing is waiting (0x13c158)
	};

	enum CALL
	{
		CALL_LIBNET_INIT,
		CALL_GET_INTERFACE_LIST,
		CALL_INTERFACE_CONTROL,
		CALL_CREATE,
		CALL_OPEN,
		CALL_CLOSE,
		CALL_SEND_TO,
		CALL_RECV_FROM,
		CALL_LOAD_MODULES,
		CALL_LINK_CHECK,
		CALL_COUNT,
	};

	struct ENTRY
	{
		CALL call;
		uint32 address;
		const char* name;
	};

	static const ENTRY* Entries()
	{
		static const ENTRY entries[CALL_COUNT] = {
		    {CALL_LIBNET_INIT, 0x365ec0, "sceLibnetInitialize"},
		    {CALL_GET_INTERFACE_LIST, 0x365a08, "sceInetGetInterfaceList"},
		    {CALL_INTERFACE_CONTROL, 0x365a90, "sceInetInterfaceControl"},
		    {CALL_CREATE, 0x3654a8, "sceInetCreate"},
		    {CALL_OPEN, 0x365518, "sceInetOpen"},
		    {CALL_CLOSE, 0x365560, "sceInetClose"},
		    {CALL_SEND_TO, 0x365830, "sceInetSendTo"},
		    {CALL_RECV_FROM, 0x365670, "sceInetRecvFrom"},
		    {CALL_LOAD_MODULES, 0x137a10, "net_loadModules"},
		    {CALL_LINK_CHECK, 0x13e638, "net_linkCheck"},
		};
		return entries;
	}

	void SetAddress(const std::string& dotted)
	{
		unsigned int a = 0, b = 0, c = 0, d = 0;
		if(sscanf(dotted.c_str(), "%u.%u.%u.%u", &a, &b, &c, &d) != 4 || a > 255 || b > 255 || c > 255 || d > 255) Die("--net-shim wants an address a.b.c.d, got '%s'", dotted.c_str());
		// the game keeps addresses low byte first: d, c, b, a
		m_ownAddress[0] = static_cast<uint8>(d);
		m_ownAddress[1] = static_cast<uint8>(c);
		m_ownAddress[2] = static_cast<uint8>(b);
		m_ownAddress[3] = static_cast<uint8>(a);
	}

	void SetLog(FILE* log)
	{
		m_log = log;
	}

	// joined to a second runner: datagrams for other addresses, and broadcasts, cross
	void SetLinked(const BusModel& bus)
	{
		m_linked = true;
		m_bus = bus;
	}

	std::vector<WireDatagram> TakeOutbox()
	{
		std::vector<WireDatagram> result;
		result.swap(m_outbox);
		return result;
	}

	// a datagram from the other machine
	void Deliver(const WireDatagram& wire, uint64 frame)
	{
		bool broadcast = (wire.destination[0] == 0xff);
		if(!broadcast && memcmp(wire.destination, m_ownAddress, 4) != 0)
		{
			Log(frame, "bus: datagram for %d.%d.%d.%d is not for this machine, dropped", wire.destination[3], wire.destination[2], wire.destination[1], wire.destination[0]);
			return;
		}
		DATAGRAM datagram;
		datagram.data = wire.data;
		memcpy(datagram.address, wire.source, 4);
		datagram.port = wire.sourcePort;
		datagram.frame = wire.deliverFrame;
		Socket(1); // after a state load the game's socket is not known yet
		for(auto& socket : m_sockets)
		{
			if(socket.second.port != wire.destinationPort) continue;
			Enqueue(socket.second, datagram);
		}
	}

	uint64 Calls(int call) const
	{
		return m_calls[call];
	}

	// runs on the machine thread, from inside a store instruction of the stub
	uint32 Dispatch(const Machine& m, uint64 frame, uint32 address)
	{
		uint32 call = (address - PORT_BASE) / 4;
		if(call >= CALL_COUNT) return 0;
		m_calls[call]++;
		auto arg = [&](int index) -> uint32 {
			// arguments 1-8 are in $a0-$a3, $t0-$t3; the ninth is the first stack word
			if(index < 8) return m.Reg(CMIPS::A0 + index);
			return m.Read32(m.Reg(CMIPS::SP) + (index - 8) * 8);
		};
		int32 result = 0;
		switch(call)
		{
		case CALL_LIBNET_INIT:
			Log(frame, "sceLibnetInitialize(cd=%08x, %x, %x, %x) -> 0", arg(0), arg(1), arg(2), arg(3));
			break;
		case CALL_GET_INTERFACE_LIST:
			Write32(m, arg(2), 1);
			result = 1;
			Log(frame, "sceInetGetInterfaceList -> 1 interface, id 1");
			break;
		case CALL_INTERFACE_CONTROL:
		{
			// code 9 asks for the interface's address: a 16-byte block, address in bytes 4-7
			uint32 code = arg(3), pointer = arg(4), length = arg(5);
			if(code == 9 && length >= 8)
			{
				if(uint8* p = m.Ptr(pointer, length))
				{
					memset(p, 0, length);
					memcpy(p + 4, m_ownAddress, 4);
				}
			}
			Log(frame, "sceInetInterfaceControl(id=%d, code=%d, ptr=%08x, len=%d) -> 0", arg(2), code, pointer, length);
		}
		break;
		case CALL_CREATE:
		{
			// parameter block: word 0 the type (0 for the datagram sockets the game opens), word 1 the local port
			uint32 parameters = arg(2);
			SOCKET socket;
			socket.type = m.Read32(parameters);
			socket.port = m.Read32(parameters + 4);
			result = m_nextId++;
			m_sockets[result] = socket;
			Log(frame, "sceInetCreate(type=%d, port=%d) -> id %d", socket.type, socket.port, result);
		}
		break;
		case CALL_OPEN:
			Log(frame, "sceInetOpen(id=%d, ms=%d) -> 0", arg(2), arg(3));
			break;
		case CALL_CLOSE:
			m_sockets.erase(static_cast<int32>(arg(2)));
			Log(frame, "sceInetClose(id=%d) -> 0", arg(2));
			break;
		case CALL_SEND_TO:
		{
			int32 id = static_cast<int32>(arg(2));
			uint32 pointer = arg(3), length = arg(4), addressBlock = arg(6), port = arg(7);
			DATAGRAM datagram;
			if(const uint8* p = m.Ptr(pointer, length)) datagram.data.assign(p, p + length);
			uint8 destination[4] = {};
			if(const uint8* p = m.Ptr(addressBlock, 8)) memcpy(destination, p + 4, 4);
			SOCKET& sender = Socket(id);
			memcpy(datagram.address, m_ownAddress, 4);
			datagram.port = sender.port;
			datagram.frame = frame + 1;
			bool broadcast = (destination[0] == 0xff);
			bool toSelf = (memcmp(destination, m_ownAddress, 4) == 0);
			const char* fate = "no receiver on the bus, dropped";
			if(broadcast || toSelf)
			{
				for(auto& other : m_sockets)
				{
					if(other.second.port != port) continue;
					Enqueue(other.second, datagram);
					fate = "queued for this machine";
				}
			}
			if(m_linked && (broadcast || !toSelf))
			{
				// the bus model: loss, then delay and jitter
				bool lost = (m_bus.lossPerMille != 0) && (m_bus.Next() % 1000 < m_bus.lossPerMille);
				if(m_bus.stallFrames != 0 && frame >= m_bus.stallAt && frame < m_bus.stallAt + m_bus.stallFrames) lost = true;
				uint32 extra = m_bus.jitter ? static_cast<uint32>(m_bus.Next() % (m_bus.jitter + 1)) : 0;
				if(lost)
				{
					fate = broadcast ? "queued here, lost on the bus" : "lost on the bus";
					m_lost++;
				}
				else
				{
					WireDatagram wire;
					wire.deliverFrame = frame + 1 + m_bus.delay + extra;
					memcpy(wire.source, m_ownAddress, 4);
					wire.sourcePort = sender.port;
					memcpy(wire.destination, destination, 4);
					wire.destinationPort = port;
					wire.data = datagram.data;
					m_outbox.push_back(std::move(wire));
					fate = broadcast ? "queued here and sent across" : "sent across";
				}
			}
			m_sent++;
			result = static_cast<int32>(length);
			if(m_logDatagrams || length <= 8) Log(frame, "sceInetSendTo(id=%d, len=%d, to %d.%d.%d.%d:%d) first=%s -> %s", id, length, destination[3], destination[2], destination[1], destination[0], port, Hex(datagram.data, 16).c_str(), fate);
		}
		break;
		case CALL_RECV_FROM:
		{
			int32 id = static_cast<int32>(arg(2));
			uint32 pointer = arg(3), length = arg(4), flagsPointer = arg(5), addressOut = arg(6), portOut = arg(7);
			result = ERROR_NO_DATA;
			SOCKET& receiver = Socket(id);
			if(!receiver.queue.empty() && receiver.queue.front().frame <= frame)
			{
				DATAGRAM datagram = std::move(receiver.queue.front());
				receiver.queue.pop_front();
				uint32 size = std::min<uint32>(length, static_cast<uint32>(datagram.data.size()));
				if(uint8* p = m.Ptr(pointer, size)) memcpy(p, datagram.data.data(), size);
				if(uint8* p = m.Ptr(addressOut, 16))
				{
					memset(p, 0, 16);
					memcpy(p + 4, datagram.address, 4);
				}
				if(portOut) Write32(m, portOut, datagram.port);
				if(flagsPointer) Write32(m, flagsPointer, 0);
				result = static_cast<int32>(size);
				m_received++;
				if(m_logDatagrams || size <= 8) Log(frame, "sceInetRecvFrom(id=%d) -> %d bytes from %d.%d.%d.%d:%d first=%s", id, size, datagram.address[3], datagram.address[2], datagram.address[1], datagram.address[0], datagram.port, Hex(datagram.data, 16).c_str());
			}
		}
		break;
		case CALL_LOAD_MODULES:
			result = 1; // an interface id; the caller then asks for its address
			Log(frame, "net_loadModules -> 1 (not run: the modules are not needed)");
			break;
		case CALL_LINK_CHECK:
			result = 1;
			break;
		}
		m.state->nGPR[CMIPS::V0].nD0 = static_cast<int64>(result);
		return 0;
	}

	void Summary() const
	{
		printf("  net shim: %" PRIu64 " datagrams sent, %" PRIu64 " received, %" PRIu64 " lost on the bus; calls:", m_sent, m_received, m_lost);
		for(int i = 0; i < CALL_COUNT; i++) printf(" %s=%" PRIu64, Entries()[i].name, m_calls[i]);
		printf("\n");
	}

private:
	struct DATAGRAM
	{
		std::vector<uint8> data;
		uint8 address[4] = {};
		uint32 port = 0;
		uint64 frame = 0; // first frame on which it may be received
	};
	struct SOCKET
	{
		uint32 type = 0;
		uint32 port = 0;
		std::deque<DATAGRAM> queue;
	};

	static void Write32(const Machine& m, uint32 address, uint32 value)
	{
		if(uint8* p = m.Ptr(address, 4)) memcpy(p, &value, 4);
	}

	// A connection id the shim has not handed out (a state saved inside a net game was
	// loaded) is taken to be the game's own socket, which is always on port 4000 on the
	// developer LAN path.
	SOCKET& Socket(int32 id)
	{
		auto found = m_sockets.find(id);
		if(found != m_sockets.end()) return found->second;
		SOCKET socket;
		socket.port = 4000;
		if(id >= m_nextId) m_nextId = id + 1;
		return m_sockets[id] = socket;
	}

	// kept in order of the frame of delivery; equal frames stay in order of arrival
	static void Enqueue(SOCKET& socket, const DATAGRAM& datagram)
	{
		auto position = socket.queue.end();
		while(position != socket.queue.begin() && (position - 1)->frame > datagram.frame) --position;
		socket.queue.insert(position, datagram);
	}

	static std::string Hex(const std::vector<uint8>& data, size_t limit)
	{
		std::string text;
		for(size_t i = 0; i < data.size() && i < limit; i++) text += StrFormat("%02x", data[i]);
		return text;
	}

	void Log(uint64 frame, const char* fmt, ...)
	{
		if(!m_log) return;
		va_list args;
		va_start(args, fmt);
		fprintf(m_log, "frame=%" PRIu64 " ", frame);
		vfprintf(m_log, fmt, args);
		fprintf(m_log, "\n");
		va_end(args);
	}

	uint8 m_ownAddress[4] = {134, 1, 168, 192};
	std::map<int32, SOCKET> m_sockets;
	int32 m_nextId = 1;
	uint64 m_calls[CALL_COUNT] = {};
	uint64 m_sent = 0;
	uint64 m_received = 0;
	uint64 m_lost = 0;
	FILE* m_log = nullptr;
	bool m_linked = false;
	BusModel m_bus;
	std::vector<WireDatagram> m_outbox;

public:
	bool m_logDatagrams = true; // every datagram, or only the short ones of the lobby
};

class CRigVM : public CPS2VM
{
public:
	using CPS2VM::ResumeImpl;
};

#ifdef DEBUGGER_INCLUDED
// An EE executor whose break point filter asks the rig first (--predict-trace). Play!
// compiles a call to the filter into the head of every translated block that contains a
// break point. With a break point on every instruction that is one call per block, made
// without leaving the executor: the rig sees every block and the machine's timing does
// not change, which a real break per block would (each one hands the IOP a time slice).
class CRigEeExecutor : public CEeExecutor
{
public:
	CRigEeExecutor(CMIPS& context, uint8* ram, std::function<bool(uint32)> onBlock)
	    : CEeExecutor(context, ram)
	    , m_onBlock(std::move(onBlock))
	{
	}
	bool FilterBreakpoint() override
	{
		if(CEeExecutor::FilterBreakpoint()) return true; // resuming from a break at this very block
		return !m_onBlock(m_context.m_State.nPC & 0x1FFFFFFF);
	}
	// address of the last instruction of the block that starts at an address
	uint32 BlockEnd(uint32 address) const
	{
		auto block = FindBlockStartingAt(address);
		return block ? block->GetEndAddress() : 0;
	}

private:
	std::function<bool(uint32)> m_onBlock;
};
#endif

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
	uint32 fpsEvery = 0;
	bool logOnChange = false;
	bool playLogs = false;
	bool throttle = false;
	bool pcHistogram = false;
	bool noCodeProtect = false;
	bool profile = false;
	bool interactive = false;
	bool interactiveLive = false; // the machine keeps running while a session waits for commands
	bool videoThread = false;
	bool video = false;
	std::string ethPcapPath;
	std::string ethNetSpec;
	std::string netShimAddress;
	std::string netLogPath;
	char machine = 'A';
	std::string linkSpec;
	BusModel bus;
	bool netLogAll = false;
	std::string tickLogPath;
	std::vector<std::string> tickWatchSpecs;
	std::string tickAddress = "0x13aee8";
	int fpRound = -1; // host rounding mode forced on the machine thread; -1: Play!'s own (toward zero)
	std::string predictAuditPath;
	std::string predictTracePath;
	std::vector<std::string> traceRangeSpecs;
	std::string traceTicks;
	int traceRaw = 0;
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

		if(!m_options.ethPcapPath.empty())
		{
			m_ethPcap = fopen(m_options.ethPcapPath.c_str(), "wb");
			if(!m_ethPcap) Die("cannot write %s", m_options.ethPcapPath.c_str());
			const uint32 header[6] = {0xa1b2c3d4, 0x00040002, 0, 0, 65535, 1};
			fwrite(header, 1, sizeof(header), m_ethPcap);
			fflush(m_ethPcap);
		}
		if(!m_options.ethNetSpec.empty())
		{
			// server=a.b.c.d[,name=host][,guest=a.b.c.d][,udp=port+port]
			// [,peerdelay=frames][,peerjitter=frames][,peerloss=per thousand][,peerseed=n]
			for(const auto& part : SplitChar(m_options.ethNetSpec, ','))
			{
				auto eq = part.find('=');
				std::string key = part.substr(0, eq), text = (eq == std::string::npos) ? "" : part.substr(eq + 1);
				if(key == "server")
					m_ethServerIp = ntohl(inet_addr(text.c_str()));
				else if(key == "guest")
					m_ethGuestIp = ntohl(inet_addr(text.c_str()));
				else if(key == "name")
					m_ethName = text;
				else if(key == "peerdelay")
					m_ethPeerDelay = static_cast<uint32>(strtoul(text.c_str(), nullptr, 0));
				else if(key == "peerjitter")
					m_ethPeerJitter = static_cast<uint32>(strtoul(text.c_str(), nullptr, 0));
				else if(key == "peerloss")
					m_ethPeerLoss = static_cast<uint32>(strtoul(text.c_str(), nullptr, 0));
				else if(key == "peerseed")
					m_ethPeerRng = 0x9E3779B97F4A7C15ull ^ (strtoull(text.c_str(), nullptr, 0) * 0x100000001B3ull) ^ (m_options.machine == 'B' ? 0x5851F42D4C957F2Dull : 0);
				else if(key == "udp")
				{
					// the server's own UDP ports (default: the lobby's discovery port)
					m_ethServerUdpPorts.clear();
					for(const auto& port : SplitChar(text, '+')) m_ethServerUdpPorts.insert(static_cast<uint16>(strtoul(port.c_str(), nullptr, 0)));
				}
				else
					Die("--eth-net: unknown setting %s", part.c_str());
			}
			if(m_ethServerIp == 0 || m_ethServerIp == 0xFFFFFFFF) Die("--eth-net needs server=<IPv4 address of this host>");
			m_ethNet = true;
		}
		if(m_ethPcap || m_ethNet)
		{
			m_vm.m_iop->m_speed.SetEthernetFrameTxHandler([this](const uint8* frame, uint32 size) { EtherTx(frame, size); });
		}

		if(!m_options.netShimAddress.empty())
		{
			m_netShim.SetAddress(m_options.netShimAddress);
			if(!m_options.netLogPath.empty())
			{
				m_netLog = fopen(m_options.netLogPath.c_str(), "w");
				if(!m_netLog) Die("cannot write %s", m_options.netLogPath.c_str());
				m_netShim.SetLog(m_netLog);
			}
			// The memory map is searched in address order and this range lies above
			// every range Play! registers for writes, so appending keeps it sorted.
			m_vm.m_ee->m_EE.m_pMemoryMap->InsertWriteMap(
			    CNetShim::PORT_BASE, CNetShim::PORT_BASE + CNetShim::PORT_SIZE - 1,
			    [this](uint32 address, uint32) { return m_netShim.Dispatch(m_machine, m_frame, address); }, 0x40);
			m_netShimReady = true;
		}
		if(!m_options.linkSpec.empty())
		{
			if(!m_netShimReady) Die("--link needs --net-shim <address>");
			BusModel bus = m_options.bus;
			if(m_options.machine == 'B') bus.state ^= 0xD6E8FEB86659FD93ull;
			m_netShim.SetLinked(bus);
			printf("waiting for the other machine (%s)\n", m_options.linkSpec.c_str());
			fflush(stdout);
			m_link.Open(m_options.linkSpec);
			printf("joined; this is machine %c\n", m_options.machine);
		}
		m_netShim.m_logDatagrams = m_options.netLogAll;
		for(const auto& spec : m_options.tickWatchSpecs) m_tickWatches.push_back(ParseWatch(spec));
		if(!m_options.tickLogPath.empty())
		{
			m_tickLog = fopen(m_options.tickLogPath.c_str(), "w");
			if(!m_tickLog) Die("cannot write %s", m_options.tickLogPath.c_str());
			fprintf(m_tickLog, "frame");
			for(const auto& watch : m_tickWatches) fprintf(m_tickLog, "\t%s", watch.name.c_str());
			fprintf(m_tickLog, "\n");
			m_needTickHook = true;
		}
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
		if(!m_options.predictAuditPath.empty())
		{
#ifndef DEBUGGER_INCLUDED
			Die("--predict-audit needs a build with break point support");
#endif
			m_auditSnapshot.resize(AUDIT_HI - AUDIT_LO);
			SetBreakpoint(AUDIT_ENTRY, true);
		}
		if(!m_options.predictTracePath.empty())
		{
#ifndef DEBUGGER_INCLUDED
			Die("--predict-trace needs a build with break point support");
#endif
			if(!m_traceExecutor) Die("--predict-trace: the tracing executor is not installed");
			for(const auto& spec : m_options.traceRangeSpecs) m_traceRanges.push_back(ParseTraceRange(spec));
			if(m_traceRanges.empty()) Die("--predict-trace needs at least one --trace-range");
			if(!m_options.traceTicks.empty())
			{
				auto parts = SplitChar(m_options.traceTicks, ':');
				m_traceTickLo = static_cast<uint32>(strtoul(parts[0].c_str(), nullptr, 0));
				m_traceTickHi = parts.size() > 1 ? static_cast<uint32>(strtoul(parts[1].c_str(), nullptr, 0)) : m_traceTickLo;
			}
			if(m_options.traceRaw > 0)
			{
				m_traceRawFile = fopen((m_options.predictTracePath + ".raw").c_str(), "w");
				if(m_traceRawFile) fprintf(m_traceRawFile, "tick\tframe\tinside\taddress\told\tnew\twriter_block\twriter\n");
			}
			m_traceOn = true;
			SetBreakpoint(AUDIT_ENTRY, true);
		}
		if(m_needTickHook)
		{
#ifndef DEBUGGER_INCLUDED
			Die("the tick log and 'ontick' need a build with break point support");
#endif
			m_tickAddress = ExprParser(m_options.tickAddress).Parse().Eval(m_machine) & 0x1FFFFFFF;
			SetBreakpoint(m_tickAddress, true);
		}
	}


	// ---- per-frame work (machine thread, at the start of every vertical blank) ----

	void OnVBlank(CRigPad& pad, uint8* ram)
	{
		if(m_finished) return;
		if(m_frame == 0)
		{
			m_cpuStart = ThreadCpuSeconds();
			if(m_options.profile)
			{
				prof::Register(0);
				prof::Start();
			}
		}
		m_frame++;
		if(m_ethNet)
		{
			// A run with host sockets depends on real time: a server drops a machine it has
			// not heard from. Say so when this one stood still (a held session, a host that
			// slept), because nothing else in the log would show it.
			auto wall = std::chrono::system_clock::now();
			double gap = m_ethLastBlankSet ? std::chrono::duration<double>(wall - m_ethLastBlank).count() : 0;
			if(gap > 20) printf("[frame %" PRIu64 "] the machine stood still for %.0f seconds of real time\n", m_frame, gap);
			m_ethLastBlank = wall;
			m_ethLastBlankSet = true;
			EtherPoll();
		}
		// Translated code does its arithmetic in the host's rounding mode, which Play!
		// sets to toward-zero once; forcing another one here makes every single-precision
		// result of this machine round differently from then on.
		if(m_options.fpRound >= 0 && fegetround() != m_options.fpRound) fesetround(m_options.fpRound);
		if(m_inlineGs) m_inlineGs->Drain();
		if(m_link.Active() && !ExchangeWithPeer()) return;

		if(m_options.pcHistogram) m_pcSamples[m_machine.state->nPC]++;
		if(m_options.fpsEvery != 0 && (m_frame % m_options.fpsEvery) == 0)
		{
			auto now = std::chrono::steady_clock::now();
			double seconds = std::chrono::duration<double>(now - m_fpsMark).count();
			double cpu = ThreadCpuSeconds();
			if(m_fpsMarkSet) printf("[frame %" PRIu64 "] last %u frames: %.1f per second, %.1f per cpu-second of the machine thread\n", m_frame, m_options.fpsEvery, seconds > 0 ? m_options.fpsEvery / seconds : 0, (cpu - m_fpsCpuMark) > 0 ? m_options.fpsEvery / (cpu - m_fpsCpuMark) : 0);
			m_fpsMark = now;
			m_fpsCpuMark = cpu;
			m_fpsMarkSet = true;
		}

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

	// One message each way per frame; see CLink. Returns false when the run is over.
	bool ExchangeWithPeer()
	{
		m_link.Send(m_frame, false, m_netShim.TakeOutbox());
		uint64 peerFrame = 0;
		bool bye = false;
		std::vector<WireDatagram> incoming;
		if(!m_link.Receive(peerFrame, bye, incoming))
		{
			printf("[frame %" PRIu64 "] the other machine is gone\n", m_frame);
			Finish(6);
			return false;
		}
		if(bye)
		{
			printf("[frame %" PRIu64 "] the other machine ended its run\n", m_frame);
			Finish(6);
			return false;
		}
		if(peerFrame != m_frame)
		{
			printf("[frame %" PRIu64 "] the other machine is at frame %" PRIu64 ": the two are out of step\n", m_frame, peerFrame);
			Finish(6);
			return false;
		}
		for(const auto& datagram : incoming) m_netShim.Deliver(datagram, m_frame);
		return true;
	}

	// --predict-audit. What may differ after a prediction call without being a leak; the
	// list is deliberately short (docs/issues/live-rig.md, section 11.3):
	bool AuditIgnored(uint32 address, uint32 ghostNow) const
	{
		if(address >= 0x01F00000) return true;                                           // the main stack
		if(m_auditGhost && address >= m_auditGhost && address < m_auditGhost + 0x590) return true; // the copy
		if(ghostNow && address >= ghostNow && address < ghostNow + 0x590) return true;
		if(address >= 0x005BF6F8 && address < 0x005BF798) return true;                   // prediction codec states
		if(address >= 0x005D14F0 && address < 0x005D14F8) return true;                   // prediction pad history
		if(address >= 0x0041BFD8 && address < 0x0041BFD8 + 4 * 0x58) return true;        // g_pads
		if(address >= 0x005D0BC0 && address < 0x005D0BC8) return true;                   // g_netCamYaw
		return false;
	}

	void AuditLeave()
	{
		m_auditCalls++;
		uint32 ghostNow = m_machine.Read32(0x4027bc) & 0x1FFFFFFF;
		uint32 tick = m_machine.Read32(0x4027ac);
		const uint8* before = m_auditSnapshot.data();
		const uint8* after = m_machine.ram + AUDIT_LO;
		for(uint32 page = 0; page < AUDIT_HI - AUDIT_LO; page += 4096)
		{
			uint32 length = std::min<uint32>(4096, AUDIT_HI - AUDIT_LO - page);
			if(memcmp(before + page, after + page, length) == 0) continue;
			for(uint32 offset = page; offset + 4 <= page + length; offset += 4)
			{
				uint32 oldWord, newWord;
				memcpy(&oldWord, before + offset, 4);
				memcpy(&newWord, after + offset, 4);
				if(oldWord == newWord) continue;
				uint32 address = AUDIT_LO + offset;
				if(AuditIgnored(address, ghostNow)) continue;
				auto& site = m_auditSites[address];
				if(site.count++ == 0)
				{
					site.tick = tick;
					site.oldWord = oldWord;
					site.newWord = newWord;
					site.where = AuditWhere(address);
				}
			}
		}
		m_auditHeap.clear();
		AuditListOrder(ghostNow, tick);
	}

	// Which object or heap block an address lies in: "pool <class> +0x<field>" through the
	// pool table (g_poolClasses 0x403a10: size, count, base, free head; the virtual table
	// of an object is at +0x48), "heap <allocating function>" through the tagged heap's
	// block list (g_heapFirstBlock 0x6dffc8 points at the first block; header: u16 0xabcd,
	// u16 used, size, tag, next, prev, group, caller).
	std::string PoolWhere(uint32 address) const
	{
		for(uint32 entry = 0x403a10; entry < 0x403a40; entry += 16)
		{
			uint32 size = m_machine.Read32(entry), count = m_machine.Read32(entry + 4), base = m_machine.Read32(entry + 8) & 0x1FFFFFFF;
			if(size == 0 || size > 0x10000 || count > 0x10000 || address < base || address >= base + size * count) continue;
			uint32 block = base + (address - base) / size * size;
			uint32 vtable = m_machine.Read32(block + 0x48) & 0x1FFFFFFF;
			std::string name = vtable ? Symbolize(vtable) : "free block";
			if(name.empty()) name = StrFormat("vtable %08x", vtable);
			const char* role = "";
			for(uint32 slot = 0; slot < 4; slot++)
			{
				if((m_machine.Read32(0x4d8af0 + slot * 0x4c30 + 0x43d8) & 0x1FFFFFFF) == block) role = " (a player's object)";
			}
			if(block == (m_machine.Read32(0x4027bc) & 0x1FFFFFFF)) role = " (the copy)";
			return StrFormat("pool %s%s +0x%x", name.c_str(), role, address - block);
		}
		return "";
	}

	std::string AuditWhere(uint32 address)
	{
		std::string pool = PoolWhere(address);
		if(!pool.empty()) return pool;
		uint32 first = m_machine.Read32(0x006dffc8) & 0x1FFFFFFF;
		if(first == 0 || address < first) return "";
		if(m_auditHeap.empty())
		{
			uint32 block = first;
			for(int guard = 0; guard < 200000; guard++)
			{
				if((m_machine.Read32(block) & 0xFFFF) != 0xabcd) break;
				uint32 size = m_machine.Read32(block + 4), next = m_machine.Read32(block + 0xc) & 0x1FFFFFFF;
				uint32 end = (next > block) ? next : block + 0x1c + size;
				m_auditHeap.push_back({block, end, m_machine.Read32(block + 0x18) & 0x1FFFFFFF, (m_machine.Read32(block) >> 16) != 0});
				if(next <= block || next == first) break;
				block = next;
			}
			if(m_auditHeap.empty()) m_auditHeap.push_back({0, 0, 0, false});
		}
		auto it = std::upper_bound(m_auditHeap.begin(), m_auditHeap.end(), address, [](uint32 a, const AUDIT_HEAP_BLOCK& b) { return a < b.start; });
		if(it == m_auditHeap.begin()) return "";
		--it;
		if(address >= it->end) return "";
		std::string name = Symbolize(it->caller);
		auto plus = name.find('+');
		if(plus != std::string::npos) name.erase(plus);
		if(name.empty()) name = StrFormat("%08x", it->caller);
		return StrFormat("heap %s%s", it->used ? "" : "(free) ", name.c_str());
	}

	// The lists the simulation walks in order: the cells of the two grids and the off-grid
	// list (handle lists: node +0 next, +0xc object). Compared before and after the call
	// with the copy left out: a difference means a prediction call moved or relinked a
	// real object.
	void AuditListOrder(uint32 ghostNow, uint32 tick)
	{
		static const struct
		{
			const char* name;
			uint32 address, cells;
		} lists[] = {{"g_grid", 0x005db4f0, 14400}, {"g_gridB", 0x005e95f0, 14400}, {"g_offGridList", 0x005f76f0, 1}};
		const uint8* before = m_auditSnapshot.data();
		const uint8* after = m_machine.ram + AUDIT_LO;
		auto word = [](const uint8* memory, uint32 address) {
			uint32 value = 0;
			if(address >= AUDIT_LO && address < AUDIT_HI - 4) memcpy(&value, memory + (address - AUDIT_LO), 4);
			return value & 0x1FFFFFFF;
		};
		auto walk = [&](const uint8* memory, uint32 head, std::vector<uint32>& out) {
			out.clear();
			uint32 node = word(memory, head);
			for(int guard = 0; node != 0 && guard < 4096; guard++)
			{
				uint32 object = word(memory, node + 0xc);
				if(object != 0 && object != m_auditGhost && object != ghostNow) out.push_back(object);
				node = word(memory, node);
			}
		};
		bool orderChanged = false, membersChanged = false;
		std::vector<uint32> a, b;
		for(const auto& list : lists)
		{
			for(uint32 cell = 0; cell < list.cells; cell++)
			{
				uint32 head = list.address + cell * 4;
				if(word(before, head) == 0 && word(after, head) == 0) continue;
				walk(before, head, a);
				walk(after, head, b);
				if(a == b) continue;
				std::vector<uint32> sa = a, sb = b;
				std::sort(sa.begin(), sa.end());
				std::sort(sb.begin(), sb.end());
				bool members = sa != sb;
				(members ? membersChanged : orderChanged) = true;
				if(m_auditListExamples.size() < 40)
				{
					std::string line = StrFormat("tick %u %s cell %u %s:", tick, list.name, cell, members ? "MEMBERS" : "order");
					for(uint32 object : a) line += StrFormat(" %s@%x", Symbolize(m_machine.Read32(object + 0x48) & 0x1FFFFFFF).c_str(), object);
					line += " ->";
					for(uint32 object : b) line += StrFormat(" %s@%x", Symbolize(m_machine.Read32(object + 0x48) & 0x1FFFFFFF).c_str(), object);
					m_auditListExamples.push_back(line);
				}
			}
		}
		if(orderChanged) m_auditOrderCalls++;
		if(membersChanged) m_auditMemberCalls++;
	}

	void AuditReport()
	{
		FILE* file = fopen(m_options.predictAuditPath.c_str(), "w");
		if(!file) return;
		fprintf(file, "# prediction calls audited: %" PRIu64 "\n", m_auditCalls);
		fprintf(file, "# calls after which a grid cell or the off-grid list held its real objects in another order: %" PRIu64 "; held other real objects: %" PRIu64 "\n", m_auditOrderCalls, m_auditMemberCalls);
		for(const auto& line : m_auditListExamples) fprintf(file, "# %s\n", line.c_str());
		fprintf(file, "address\tsymbol\tcalls\tfirst_tick\told\tnew\twhere\n");
		for(const auto& entry : m_auditSites)
		{
			fprintf(file, "%08x\t%s\t%" PRIu64 "\t%u\t%08x\t%08x\t%s\n", entry.first, Symbolize(entry.first).c_str(), entry.second.count, entry.second.tick, entry.second.oldWord, entry.second.newWord, entry.second.where.c_str());
		}
		fclose(file);
		printf("  prediction audit: real objects of a grid cell or of the off-grid list reordered in %" PRIu64 " calls, replaced in %" PRIu64 "\n", m_auditOrderCalls, m_auditMemberCalls);
		printf("  prediction audit: %" PRIu64 " calls, %zu words changed outside the ignore list -> %s\n", m_auditCalls, m_auditSites.size(), m_options.predictAuditPath.c_str());
	}

	// ---- the emulated Ethernet chip (Play!'s Iop::CSpeed) ---------------------------
	// Frames the game's network stack transmits arrive in EtherTx (machine thread, from
	// inside the chip emulation); every frame in either direction goes to the capture file.
	void EtherCapture(const uint8* frame, uint32 size)
	{
		if(!m_ethPcap) return;
		const uint32 header[4] = {static_cast<uint32>(m_frame / 60), static_cast<uint32>((m_frame % 60) * 16666), size, size};
		fwrite(header, 1, sizeof(header), m_ethPcap);
		fwrite(frame, 1, size, m_ethPcap);
		fflush(m_ethPcap);
	}

	void EtherTx(const uint8* frame, uint32 size)
	{
		m_ethTxFrames++;
		EtherCapture(frame, size);
		if(!m_ethNet || size < 14) return;
		try
		{
			EtherInput(frame, size);
		}
		catch(const std::exception& error)
		{
			printf("[frame %" PRIu64 "] ethernet: %s\n", m_frame, error.what());
		}
		EtherDeliver();
	}

	// ---- --eth-net: a small network behind the chip ---------------------------------
	// One guest on 10.0.2.0/24. The rig is the gateway 10.0.2.2: it answers ARP for every
	// other address, DHCP, ping, and DNS (one name, which gets the server's address;
	// everything else does not exist). UDP and TCP to the server's address are relayed
	// through host sockets; TCP is ended here (the guest only ever opens connections).
	// Nothing is relayed to any other address: this network does not reach the Internet.
	static uint16 Get16(const uint8* p)
	{
		return static_cast<uint16>((p[0] << 8) | p[1]);
	}
	static uint32 Get32(const uint8* p)
	{
		return (static_cast<uint32>(p[0]) << 24) | (p[1] << 16) | (p[2] << 8) | p[3];
	}
	static void Put16(uint8* p, uint16 v)
	{
		p[0] = static_cast<uint8>(v >> 8);
		p[1] = static_cast<uint8>(v);
	}
	static void Put32(uint8* p, uint32 v)
	{
		p[0] = static_cast<uint8>(v >> 24);
		p[1] = static_cast<uint8>(v >> 16);
		p[2] = static_cast<uint8>(v >> 8);
		p[3] = static_cast<uint8>(v);
	}
	static uint32 SumWords(const uint8* data, size_t length, uint32 sum = 0)
	{
		for(size_t i = 0; i + 1 < length; i += 2) sum += (data[i] << 8) | data[i + 1];
		if(length & 1) sum += data[length - 1] << 8;
		return sum;
	}
	static uint16 FoldSum(uint32 sum)
	{
		while(sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
		return static_cast<uint16>(~sum);
	}
	static std::string IpText(uint32 ip)
	{
		return StrFormat("%u.%u.%u.%u", ip >> 24, (ip >> 16) & 255, (ip >> 8) & 255, ip & 255);
	}

	// an Ethernet + IPv4 frame to the guest; payload is the transport header and data,
	// whose checksum field (at checksumAt, or none) is filled in here
	void EtherSendIp(uint8 protocol, uint32 sourceIp, uint32 destIp, std::vector<uint8> payload, int checksumAt, bool broadcast = false)
	{
		if(checksumAt >= 0)
		{
			uint8 pseudo[12];
			Put32(pseudo, sourceIp);
			Put32(pseudo + 4, destIp);
			pseudo[8] = 0;
			pseudo[9] = protocol;
			Put16(pseudo + 10, static_cast<uint16>(payload.size()));
			Put16(&payload[checksumAt], 0);
			uint16 sum = FoldSum(SumWords(payload.data(), payload.size(), SumWords(pseudo, 12)));
			if(protocol == 17 && sum == 0) sum = 0xFFFF;
			Put16(&payload[checksumAt], sum);
		}
		std::vector<uint8> frame(14 + 20 + payload.size());
		memcpy(&frame[0], broadcast ? ETH_BROADCAST : m_ethGuestMac, 6);
		memcpy(&frame[6], ETH_GATEWAY_MAC, 6);
		Put16(&frame[12], 0x0800);
		uint8* ip = &frame[14];
		ip[0] = 0x45;
		Put16(ip + 2, static_cast<uint16>(20 + payload.size()));
		Put16(ip + 4, m_ethIpId++);
		ip[8] = 64;
		ip[9] = protocol;
		Put32(ip + 12, sourceIp);
		Put32(ip + 16, destIp);
		Put16(ip + 10, FoldSum(SumWords(ip, 20)));
		memcpy(&frame[34], payload.data(), payload.size());
		m_ethRxQueue.push_back(std::move(frame));
	}

	void EtherSendUdp(uint32 sourceIp, uint16 sourcePort, uint32 destIp, uint16 destPort, const uint8* data, size_t length, bool broadcast = false)
	{
		std::vector<uint8> payload(8 + length);
		Put16(&payload[0], sourcePort);
		Put16(&payload[2], destPort);
		Put16(&payload[4], static_cast<uint16>(8 + length));
		if(length) memcpy(&payload[8], data, length);
		EtherSendIp(17, sourceIp, destIp, std::move(payload), 6, broadcast);
	}

	void EtherInput(const uint8* frame, uint32 size)
	{
		memcpy(m_ethGuestMac, frame + 6, 6);
		uint16 type = Get16(frame + 12);
		if(type == 0x0806 && size >= 42)
		{
			const uint8* arp = frame + 14;
			uint32 senderIp = Get32(arp + 14), targetIp = Get32(arp + 24);
			// a request for another address than the guest's own (its duplicate-address
			// probe must stay unanswered)
			if(Get16(arp + 6) != 1 || targetIp == senderIp || targetIp == m_ethGuestIp || (senderIp == 0 && targetIp == m_ethGuestIp)) return;
			std::vector<uint8> reply(60, 0);
			memcpy(&reply[0], frame + 6, 6);
			memcpy(&reply[6], ETH_GATEWAY_MAC, 6);
			Put16(&reply[12], 0x0806);
			Put16(&reply[14], 1);
			Put16(&reply[16], 0x0800);
			reply[18] = 6;
			reply[19] = 4;
			Put16(&reply[20], 2);
			memcpy(&reply[22], ETH_GATEWAY_MAC, 6);
			Put32(&reply[28], targetIp);
			memcpy(&reply[32], arp + 8, 6);
			Put32(&reply[38], senderIp);
			m_ethRxQueue.push_back(std::move(reply));
			return;
		}
		if(type != 0x0800 || size < 34) return;
		const uint8* ip = frame + 14;
		uint32 headerLength = (ip[0] & 15) * 4, totalLength = Get16(ip + 2);
		if(headerLength < 20 || 14 + totalLength > size || totalLength < headerLength) return;
		if(Get16(ip + 6) & 0x3FFF) return; // a fragment: not handled
		uint32 sourceIp = Get32(ip + 12), destIp = Get32(ip + 16);
		const uint8* l4 = ip + headerLength;
		uint32 l4Length = totalLength - headerLength;
		if(ip[9] == 1 && l4Length >= 8 && l4[0] == 8)
		{
			std::vector<uint8> echo(l4, l4 + l4Length);
			echo[0] = 0;
			Put16(&echo[2], 0);
			Put16(&echo[2], FoldSum(SumWords(echo.data(), echo.size())));
			EtherSendIp(1, destIp, sourceIp, std::move(echo), -1);
		}
		else if(ip[9] == 17 && l4Length >= 8)
		{
			uint16 sourcePort = Get16(l4), destPort = Get16(l4 + 2);
			const uint8* data = l4 + 8;
			uint32 length = std::min<uint32>(Get16(l4 + 4), l4Length) - 8;
			if(destPort == 67)
				EtherDhcp(data, length);
			else if(destPort == 53)
				EtherDns(sourceIp, sourcePort, destIp, data, length);
			else
				EtherUdpOut(sourcePort, destIp, destPort, data, length);
		}
		else if(ip[9] == 6 && l4Length >= 20)
		{
			EtherTcpIn(sourceIp, destIp, l4, l4Length);
		}
	}

	void EtherDhcp(const uint8* data, uint32 length)
	{
		if(length < 240 || data[0] != 1) return;
		uint8 messageType = 0;
		for(uint32 at = 240; at + 1 < length && data[at] != 255;)
		{
			if(data[at] == 0)
			{
				at++;
				continue;
			}
			if(data[at] == 53 && data[at + 1] >= 1) messageType = data[at + 2];
			at += 2 + data[at + 1];
		}
		if(messageType != 1 && messageType != 3) return;
		std::vector<uint8> reply(300, 0);
		reply[0] = 2;
		reply[1] = 1;
		reply[2] = 6;
		memcpy(&reply[4], data + 4, 4); // transaction id
		memcpy(&reply[10], data + 10, 2); // flags
		Put32(&reply[16], m_ethGuestIp);
		Put32(&reply[20], ETH_GATEWAY_IP);
		memcpy(&reply[28], data + 28, 16);
		Put32(&reply[236], 0x63825363);
		uint8* option = &reply[240];
		auto put = [&](uint8 code, uint32 value) {
			*option++ = code;
			*option++ = 4;
			Put32(option, value);
			option += 4;
		};
		*option++ = 53;
		*option++ = 1;
		*option++ = (messageType == 1) ? 2 : 5;
		put(54, ETH_GATEWAY_IP);
		put(51, 86400);
		put(1, 0xFFFFFF00);
		put(3, ETH_GATEWAY_IP);
		put(6, ETH_GATEWAY_IP);
		*option++ = 255;
		printf("[frame %" PRIu64 "] ethernet: DHCP %s -> %s %s\n", m_frame, messageType == 1 ? "discover" : "request", messageType == 1 ? "offer" : "acknowledge", IpText(m_ethGuestIp).c_str());
		EtherSendUdp(ETH_GATEWAY_IP, 67, 0xFFFFFFFF, 68, reply.data(), reply.size(), true);
	}

	void EtherDns(uint32 sourceIp, uint16 sourcePort, uint32 destIp, const uint8* data, uint32 length)
	{
		if(length < 17) return;
		std::string name;
		uint32 at = 12;
		while(at < length && data[at] != 0 && data[at] < 64)
		{
			if(!name.empty()) name += '.';
			name.append(reinterpret_cast<const char*>(data + at + 1), std::min<uint32>(data[at], length - at - 1));
			at += 1 + data[at];
		}
		if(at + 5 > length) return;
		uint16 queryType = Get16(data + at + 1);
		uint32 questionEnd = at + 5;
		std::string lower = name;
		for(auto& c : lower) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
		bool known = (queryType == 1) && (lower == m_ethName);
		std::vector<uint8> reply(data, data + questionEnd);
		reply[2] = 0x81;
		reply[3] = known ? 0x80 : 0x83;
		Put16(&reply[4], 1);
		Put16(&reply[6], known ? 1 : 0);
		Put16(&reply[8], 0);
		Put16(&reply[10], 0);
		if(known)
		{
			const uint8 answer[12] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4};
			reply.insert(reply.end(), answer, answer + 12);
			uint8 address[4];
			Put32(address, m_ethServerIp);
			reply.insert(reply.end(), address, address + 4);
		}
		printf("[frame %" PRIu64 "] ethernet: DNS type %u for %s -> %s\n", m_frame, queryType, name.c_str(), known ? IpText(m_ethServerIp).c_str() : "no such name");
		EtherSendUdp(destIp, 53, sourceIp, sourcePort, reply.data(), reply.size());
	}

	static void SetNonBlocking(int fd)
	{
		fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
	}

	// UDP: one host socket per guest port; whatever arrives on it goes to that port
	void EtherUdpOut(uint16 sourcePort, uint32 destIp, uint16 destPort, const uint8* data, uint32 length)
	{
		if(destIp != m_ethServerIp)
		{
			if(m_ethRefused.insert((static_cast<uint64>(destIp) << 16) | destPort).second)
				printf("[frame %" PRIu64 "] ethernet: UDP to %s:%u not relayed (only the server's address is)\n", m_frame, IpText(destIp).c_str(), destPort);
			return;
		}
		auto found = m_ethUdp.find(sourcePort);
		if(found == m_ethUdp.end())
		{
			int fd = socket(AF_INET, SOCK_DGRAM, 0);
			if(fd < 0) return;
			sockaddr_in any = {};
			any.sin_family = AF_INET;
			bind(fd, reinterpret_cast<sockaddr*>(&any), sizeof(any));
			SetNonBlocking(fd);
			socklen_t anyLength = sizeof(any);
			getsockname(fd, reinterpret_cast<sockaddr*>(&any), &anyLength);
			printf("[frame %" PRIu64 "] ethernet: UDP port %u of the machine is host port %u\n", m_frame, sourcePort, ntohs(any.sin_port));
			found = m_ethUdp.emplace(sourcePort, fd).first;
		}
		// The server's address is also where the lobby server saw every other runner on
		// this host, and so where it tells this machine to find them: all the runners sit
		// behind one address, as consoles behind one router do. A datagram for a port that
		// is not one of the server's own is for such a runner. It goes to that runner's
		// host socket through the loopback interface (a host firewall may drop datagrams
		// between two local programs on the outside address), and the runner that gets it
		// shows it to its machine as coming from the shared address (EtherPoll).
		bool toServer = m_ethServerUdpPorts.count(destPort) != 0;
		if(!toServer && (m_ethPeerDelay || m_ethPeerJitter || m_ethPeerLoss))
		{
			// the path model for datagrams between runners (peerdelay, peerjitter in frames
			// of this machine, peerloss per thousand): each sender delays and drops its own
			auto next = [this]() {
				m_ethPeerRng ^= m_ethPeerRng >> 12;
				m_ethPeerRng ^= m_ethPeerRng << 25;
				m_ethPeerRng ^= m_ethPeerRng >> 27;
				return static_cast<uint32>((m_ethPeerRng * 0x2545F4914F6CDD1Dull) >> 32);
			};
			if(m_ethPeerOut++ == 0) printf("[frame %" PRIu64 "] ethernet: first datagram for another runner: port %u -> %s:%u (through the loopback interface, path model on)\n", m_frame, sourcePort, IpText(destIp).c_str(), destPort);
			if(m_ethPeerLoss && next() % 1000 < m_ethPeerLoss)
			{
				m_ethPeerLost++;
				return;
			}
			ETH_HELD held;
			held.release = m_frame + m_ethPeerDelay + (m_ethPeerJitter ? next() % (m_ethPeerJitter + 1) : 0);
			held.fd = found->second;
			held.destPort = destPort;
			held.data.assign(data, data + length);
			// kept in order of release: jitter reorders
			auto at = m_ethPeerQueue.end();
			while(at != m_ethPeerQueue.begin() && std::prev(at)->release > held.release) --at;
			m_ethPeerQueue.insert(at, std::move(held));
			return;
		}
		sockaddr_in to = {};
		to.sin_family = AF_INET;
		to.sin_addr.s_addr = htonl(toServer ? destIp : INADDR_LOOPBACK);
		to.sin_port = htons(destPort);
		sendto(found->second, data, length, 0, reinterpret_cast<sockaddr*>(&to), sizeof(to));
		if(toServer)
			m_ethUdpOut++;
		else
		{
			if(m_ethPeerOut++ == 0) printf("[frame %" PRIu64 "] ethernet: first datagram for another runner: port %u -> %s:%u (through the loopback interface)\n", m_frame, sourcePort, IpText(destIp).c_str(), destPort);
		}
	}

	// TCP, ended here: the guest's connection is answered by the rig and its bytes go
	// through a host socket connected to the same address and port
	struct ETH_TCP
	{
		int fd = -1;
		uint16 guestPort = 0, destPort = 0;
		uint32 destIp = 0;
		uint32 receiveNext = 0;       // next sequence number expected from the guest
		uint32 sendBase = 0;          // sequence number of sendBuffer[0]
		uint32 sendNext = 0;          // next sequence number to send
		uint32 guestWindow = 0;
		std::deque<uint8> sendBuffer; // bytes from the host not yet acknowledged
		bool synAcked = false, hostClosed = false, finSent = false, finAcked = false, guestClosed = false;
		uint64 lastProgress = 0;
		uint64 bytesToHost = 0, bytesToGuest = 0;
	};

	void EtherTcpSegment(ETH_TCP& c, uint8 flags, uint32 sequence, const uint8* data, size_t length, bool withMss = false)
	{
		std::vector<uint8> segment((withMss ? 24 : 20) + length);
		Put16(&segment[0], c.destPort);
		Put16(&segment[2], c.guestPort);
		Put32(&segment[4], sequence);
		Put32(&segment[8], c.receiveNext);
		segment[12] = withMss ? 0x60 : 0x50;
		segment[13] = flags;
		Put16(&segment[14], 0x4000);
		if(withMss)
		{
			segment[20] = 2;
			segment[21] = 4;
			Put16(&segment[22], ETH_TCP_MSS);
		}
		if(length) memcpy(&segment[withMss ? 24 : 20], data, length);
		EtherSendIp(6, c.destIp, m_ethGuestIp, std::move(segment), 16);
	}

	void EtherTcpIn(uint32 sourceIp, uint32 destIp, const uint8* tcp, uint32 length)
	{
		uint16 sourcePort = Get16(tcp), destPort = Get16(tcp + 2);
		uint32 sequence = Get32(tcp + 4), acknowledge = Get32(tcp + 8);
		uint32 dataOffset = (tcp[12] >> 4) * 4;
		uint8 flags = tcp[13];
		if(dataOffset < 20 || dataOffset > length) return;
		const uint8* data = tcp + dataOffset;
		uint32 dataLength = length - dataOffset;
		uint64 key = (static_cast<uint64>(sourcePort) << 48) | (static_cast<uint64>(destIp) << 16) | destPort;
		auto found = m_ethTcp.find(key);
		if(flags & 0x04) // reset
		{
			if(found != m_ethTcp.end())
			{
				printf("[frame %" PRIu64 "] ethernet: TCP %u -> %s:%u reset by the machine\n", m_frame, sourcePort, IpText(destIp).c_str(), destPort);
				close(found->second.fd);
				m_ethTcp.erase(found);
			}
			return;
		}
		if((flags & 0x12) == 0x02) // a connection request
		{
			if(found != m_ethTcp.end())
			{
				// the request again: answer again
				EtherTcpSegment(found->second, 0x12, found->second.sendBase - 1, nullptr, 0, true);
				return;
			}
			ETH_TCP c;
			c.guestPort = sourcePort;
			c.destPort = destPort;
			c.destIp = destIp;
			c.receiveNext = sequence + 1;
			c.guestWindow = Get16(tcp + 14);
			c.sendBase = 0x52494700 + 0x10000 * static_cast<uint32>(m_ethTcpCount++) + 1;
			c.sendNext = c.sendBase;
			c.lastProgress = m_frame;
			bool connected = false;
			bool blocked = std::chrono::system_clock::now() < m_ethBlockedUntil;
			if(destIp == m_ethServerIp && !blocked)
			{
				c.fd = socket(AF_INET, SOCK_STREAM, 0);
				sockaddr_in to = {};
				to.sin_family = AF_INET;
				to.sin_addr.s_addr = htonl(destIp);
				to.sin_port = htons(destPort);
				connected = c.fd >= 0 && connect(c.fd, reinterpret_cast<sockaddr*>(&to), sizeof(to)) == 0;
			}
			printf("[frame %" PRIu64 "] ethernet: TCP %u -> %s:%u %s\n", m_frame, sourcePort, IpText(destIp).c_str(), destPort,
			       connected ? "connected" : (blocked ? "refused (ethdrop)" : (destIp == m_ethServerIp ? "REFUSED by the host" : "not relayed (only the server's address is)")));
			if(!connected)
			{
				if(c.fd >= 0) close(c.fd);
				EtherTcpSegment(c, 0x14, 0, nullptr, 0); // reset, acknowledging the request
				return;
			}
			SetNonBlocking(c.fd);
			EtherTcpSegment(c, 0x12, c.sendBase - 1, nullptr, 0, true);
			m_ethTcp.emplace(key, std::move(c));
			return;
		}
		if(found == m_ethTcp.end()) return;
		ETH_TCP& c = found->second;
		c.guestWindow = Get16(tcp + 14);
		if(flags & 0x10)
		{
			c.synAcked = true;
			uint32 acked = acknowledge - c.sendBase; // bytes of the buffer the guest has
			if(acked != 0 && acked <= c.sendNext - c.sendBase)
			{
				uint32 fromBuffer = std::min<uint32>(acked, static_cast<uint32>(c.sendBuffer.size()));
				c.sendBuffer.erase(c.sendBuffer.begin(), c.sendBuffer.begin() + fromBuffer);
				c.sendBase += fromBuffer;
				if(c.finSent && acknowledge == c.sendNext) c.finAcked = true;
				c.lastProgress = m_frame;
			}
		}
		bool reply = false;
		if(dataLength)
		{
			if(sequence == c.receiveNext)
			{
				size_t sent = 0;
				while(sent < dataLength)
				{
					ssize_t n = send(c.fd, data + sent, dataLength - sent, 0);
					if(n > 0)
						sent += n;
					else if(n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
						usleep(200);
					else
						break;
				}
				if(sent < dataLength)
				{
					// the host side of the connection is gone (the server closed it): the
					// machine is told with a reset, as it would be on a real network
					printf("[frame %" PRIu64 "] ethernet: TCP %u -> %s:%u reset, the host side is gone (%" PRIu64 " bytes out, %" PRIu64 " in)\n", m_frame, c.guestPort, IpText(c.destIp).c_str(), c.destPort, c.bytesToHost, c.bytesToGuest);
					EtherTcpSegment(c, 0x14, c.sendNext, nullptr, 0);
					close(c.fd);
					m_ethTcp.erase(found);
					return;
				}
				c.receiveNext += dataLength;
				c.bytesToHost += dataLength;
			}
			reply = true;
		}
		if((flags & 0x01) && sequence + dataLength == c.receiveNext && !c.guestClosed)
		{
			c.receiveNext += 1;
			c.guestClosed = true;
			shutdown(c.fd, SHUT_WR);
			reply = true;
			printf("[frame %" PRIu64 "] ethernet: TCP %u -> %s:%u closed by the machine (%" PRIu64 " bytes out, %" PRIu64 " in)\n", m_frame, c.guestPort, IpText(c.destIp).c_str(), c.destPort, c.bytesToHost, c.bytesToGuest);
		}
		if(reply) EtherTcpSegment(c, 0x10, c.sendNext, nullptr, 0);
		if(c.guestClosed && c.finAcked)
		{
			close(c.fd);
			m_ethTcp.erase(found);
		}
	}

	// 'ethdrop': the server loses this machine, as when a line goes down. The host side of
	// every relayed TCP connection is shut; the machine is told when it next sends (a
	// reset). For 'seconds' of real time new connections are refused too, so the machine
	// can be kept away for longer than a server's time-out.
	void EtherDrop(double seconds)
	{
		int count = 0;
		for(auto& entry : m_ethTcp)
		{
			shutdown(entry.second.fd, SHUT_RDWR);
			count++;
		}
		if(seconds > 0) m_ethBlockedUntil = std::chrono::system_clock::now() + std::chrono::milliseconds(static_cast<int64_t>(seconds * 1000));
		printf("[frame %" PRIu64 "] ethernet: %d relayed TCP connection(s) dropped on the host side%s\n", m_frame, count, seconds > 0 ? StrFormat("; new ones refused for %.0f s", seconds).c_str() : "");
	}

	// every vertical blank: bytes and datagrams from the host side become frames
	void EtherPoll()
	{
		// datagrams for another runner that the path model held back
		while(!m_ethPeerQueue.empty() && m_ethPeerQueue.front().release <= m_frame)
		{
			const auto& held = m_ethPeerQueue.front();
			sockaddr_in to = {};
			to.sin_family = AF_INET;
			to.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
			to.sin_port = htons(held.destPort);
			sendto(held.fd, held.data.data(), held.data.size(), 0, reinterpret_cast<sockaddr*>(&to), sizeof(to));
			m_ethPeerQueue.pop_front();
		}
		uint8 buffer[2048];
		for(auto& entry : m_ethUdp)
		{
			for(int i = 0; i < 16; i++)
			{
				sockaddr_in from = {};
				socklen_t fromLength = sizeof(from);
				ssize_t n = recvfrom(entry.second, buffer, sizeof(buffer), 0, reinterpret_cast<sockaddr*>(&from), &fromLength);
				if(n < 0) break;
				uint32 fromIp = ntohl(from.sin_addr.s_addr);
				if(fromIp == INADDR_LOOPBACK)
				{
					// another runner on this host: its machine is known by the shared address
					fromIp = m_ethServerIp;
					if(m_ethPeerIn++ == 0) printf("[frame %" PRIu64 "] ethernet: first datagram from another runner: %s:%u -> port %u\n", m_frame, IpText(fromIp).c_str(), ntohs(from.sin_port), entry.first);
				}
				else
					m_ethUdpIn++;
				EtherSendUdp(fromIp, ntohs(from.sin_port), m_ethGuestIp, entry.first, buffer, static_cast<size_t>(n));
			}
		}
		for(auto it = m_ethTcp.begin(); it != m_ethTcp.end();)
		{
			ETH_TCP& c = it->second;
			if(c.synAcked && !c.hostClosed && c.sendBuffer.size() < 16384)
			{
				ssize_t n = recv(c.fd, buffer, sizeof(buffer), 0);
				if(n > 0)
					c.sendBuffer.insert(c.sendBuffer.end(), buffer, buffer + n);
				else if(n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK))
					c.hostClosed = true;
			}
			// nothing acknowledged for two seconds: send again from the oldest byte
			if(c.sendNext != c.sendBase && !c.finAcked && m_frame - c.lastProgress > 120)
			{
				c.sendNext = c.sendBase;
				c.finSent = false;
				c.lastProgress = m_frame;
			}
			uint32 window = std::min<uint32>(c.guestWindow, 4 * ETH_TCP_MSS);
			for(int i = 0; i < 2 && c.synAcked; i++)
			{
				uint32 offset = c.sendNext - c.sendBase;
				if(offset >= c.sendBuffer.size() || offset >= window) break;
				uint32 n = std::min<uint32>({static_cast<uint32>(c.sendBuffer.size()) - offset, static_cast<uint32>(ETH_TCP_MSS), window - offset});
				std::vector<uint8> piece(c.sendBuffer.begin() + offset, c.sendBuffer.begin() + offset + n);
				EtherTcpSegment(c, 0x18, c.sendNext, piece.data(), n);
				c.sendNext += n;
				c.bytesToGuest += n;
			}
			if(c.hostClosed && !c.finSent && c.sendNext - c.sendBase == c.sendBuffer.size())
			{
				EtherTcpSegment(c, 0x11, c.sendNext, nullptr, 0);
				c.sendNext += 1;
				c.finSent = true;
				printf("[frame %" PRIu64 "] ethernet: TCP %u -> %s:%u closed by the host (%" PRIu64 " bytes out, %" PRIu64 " in)\n", m_frame, c.guestPort, IpText(c.destIp).c_str(), c.destPort, c.bytesToHost, c.bytesToGuest);
			}
			if(c.guestClosed && c.finAcked)
			{
				close(c.fd);
				it = m_ethTcp.erase(it);
			}
			else
				++it;
		}
		EtherDeliver();
	}

	// Hand the chip the next waiting frame if the driver has taken the one before. Play!'s
	// chip holds one frame at a time. Its descriptor index wraps at 512 where the ring has
	// 64 entries, and it is not reset when the driver starts again (after the machine
	// restarts into another program): both are put right here.
	void EtherDeliver()
	{
		auto& speed = m_vm.m_iop->m_speed;
		// the driver writes the station address when it starts: a start is seen by the
		// marker the rig leaves in that register being gone
		if(speed.m_smapEmac3AddressLo != ETH_MARKER)
		{
			speed.m_smapEmac3AddressLo = ETH_MARKER;
			speed.m_rxIndex = 0;
		}
		if(m_ethRxQueue.empty()) return;
		if(speed.m_pendingRx || speed.m_rxFrameCount != 0) return;
		speed.m_rxIndex %= 64;
		auto* descriptor = reinterpret_cast<Iop::CSpeed::SMAP_BD*>(speed.m_smapBdRx) + speed.m_rxIndex;
		if(!(descriptor->ctrlStat & 0x8000)) return; // not handed back by the driver yet
		std::vector<uint8> frame = std::move(m_ethRxQueue.front());
		m_ethRxQueue.pop_front();
		EtherCapture(frame.data(), static_cast<uint32>(frame.size()));
		// the length the driver is given includes four bytes of frame check, and it reads
		// in blocks: leave room after the frame
		uint32 length = static_cast<uint32>((std::max<size_t>(frame.size(), 60) + 4 + 3) & ~3u);
		frame.resize(length, 0);
		speed.RxEthernetFrame(frame.data(), length);
		speed.m_rxBuffer.resize(length + 256, 0);
		m_ethRxFrames++;
	}

	// --predict-trace: which instruction writes a watched word. Every translated block
	// reports here on entry (CRigEeExecutor); a watched word that differs from its shadow
	// was written by the block entered before. Writes are gathered by site, writing block
	// and the chain of calls leading to it (kept from the jal/jalr return addresses).
	struct TRACE_RANGE
	{
		uint32 address = 0, length = 0, stride = 0;
		bool always = false; // also outside prediction calls
		std::string name;
		std::vector<uint8> shadow;
	};

	// EXPR:LENGTH[:STRIDE][,all][,name=N]
	TRACE_RANGE ParseTraceRange(const std::string& text)
	{
		auto options = SplitChar(text, ',');
		auto parts = SplitChar(options[0], ':');
		if(parts.size() < 2) Die("--trace-range %s: expected ADDRESS:LENGTH[:STRIDE][,all][,name=N]", text.c_str());
		TRACE_RANGE range;
		range.address = ExprParser(parts[0]).Parse().Eval(m_machine) & 0x1FFFFFFF;
		range.length = static_cast<uint32>(strtoul(parts[1].c_str(), nullptr, 0)) & ~3u;
		if(parts.size() > 2) range.stride = static_cast<uint32>(strtoul(parts[2].c_str(), nullptr, 0));
		for(size_t i = 1; i < options.size(); i++)
		{
			if(options[i] == "all")
				range.always = true;
			else if(options[i].compare(0, 5, "name=") == 0)
				range.name = options[i].substr(5);
			else
				Die("--trace-range %s: unknown option %s", text.c_str(), options[i].c_str());
		}
		if(range.length == 0 || !m_machine.Ptr(range.address, range.length)) Die("--trace-range %s: not in memory", text.c_str());
		if(range.name.empty()) range.name = Symbolize(range.address);
		if(range.name.empty()) range.name = StrFormat("%08x", range.address);
		return range;
	}

	void TraceInstall(bool enable)
	{
#ifdef DEBUGGER_INCLUDED
		auto& context = m_vm.m_ee->m_EE;
		if(enable)
		{
			for(uint32 address = TEXT_LO; address < TEXT_HI; address += 4) context.m_breakpoints.insert(context.m_breakpoints.end(), address);
		}
		else
		{
			context.m_breakpoints.clear();
			for(uint32 address : m_realBreaks) context.m_breakpoints.insert(address);
		}
		m_traceInstalled = enable;
		context.m_executor->ClearActiveBlocksInRange(TEXT_LO, TEXT_HI, false);
		printf("[frame %" PRIu64 "] tick %u: block trace %s\n", m_frame, m_machine.Read32(0x4027ac), enable ? "on" : "off");
#endif
	}

	// at the entry of net_predictLocalPlayer (break notification)
	void TraceEnter()
	{
		uint32 tick = m_machine.Read32(0x4027ac);
		bool inWindow = tick >= m_traceTickLo && tick <= m_traceTickHi;
		if(inWindow && !m_traceInstalled) TraceInstall(true);
		if(!inWindow && m_traceInstalled && tick > m_traceTickHi) TraceInstall(false);
		m_traceActive = inWindow;
		if(!inWindow) return;
		for(auto& range : m_traceRanges)
		{
			if(range.always && !range.shadow.empty()) continue;
			const uint8* now = m_machine.ram + range.address;
			range.shadow.assign(now, now + range.length);
		}
		m_traceStack.clear();
		m_tracePrevPc = AUDIT_ENTRY;
#ifdef DEBUGGER_INCLUDED
		m_tracePrevEnd = m_traceExecutor->BlockEnd(AUDIT_ENTRY);
#endif
		m_traceCalls++;
	}

	// every block entry (machine thread, inside the executor); true if the rig wants the break
	bool OnBlock(uint32 pc)
	{
		if(m_traceActive) TraceBlock(pc);
		return m_realBreaks.count(pc) != 0;
	}

	void TraceBlock(uint32 pc)
	{
		m_traceBlocks++;
		for(auto& range : m_traceRanges)
		{
			if(!range.always && !m_auditArmed) continue;
			const uint8* now = m_machine.ram + range.address;
			if(memcmp(now, range.shadow.data(), range.length) == 0) continue;
			for(uint32 offset = 0; offset + 4 <= range.length; offset += 4)
			{
				uint32 oldWord, newWord;
				memcpy(&oldWord, range.shadow.data() + offset, 4);
				memcpy(&newWord, now + offset, 4);
				if(oldWord != newWord) TraceWrite(range, range.address + offset, oldWord, newWord);
			}
			memcpy(range.shadow.data(), now, range.length);
		}
		uint32 ra = m_machine.Reg(CMIPS::RA) & 0x1FFFFFFF, sp = m_machine.Reg(CMIPS::SP);
		while(!m_traceStack.empty() && ((pc == m_traceStack.back().ra && sp == m_traceStack.back().sp) || m_traceStack.back().sp < sp)) m_traceStack.pop_back();
		if(m_tracePrevEnd != 0 && ra == m_tracePrevEnd + 4)
		{
			if(m_traceStack.size() >= 48) m_traceStack.erase(m_traceStack.begin());
			m_traceStack.push_back({pc, sp, ra});
		}
		m_tracePrevPc = pc;
#ifdef DEBUGGER_INCLUDED
		m_tracePrevEnd = m_traceExecutor->BlockEnd(pc);
#endif
	}

	void TraceWrite(const TRACE_RANGE& range, uint32 address, uint32 oldWord, uint32 newWord)
	{
		uint32 tick = m_machine.Read32(0x4027ac);
		std::string site;
		if(range.stride)
			site = StrFormat("%s[] +0x%x", range.name.c_str(), (address - range.address) % range.stride);
		else
		{
			site = PoolWhere(address);
			if(site.empty()) site = Symbolize(address);
			if(site.empty()) site = StrFormat("%08x", address);
		}
		std::string chain;
		int shown = 0;
		for(size_t i = m_traceStack.size(); i-- > 0 && shown < 7; shown++)
		{
			std::string name = Symbolize(m_traceStack[i].pc);
			if(name.empty()) name = StrFormat("%08x", m_traceStack[i].pc);
			chain += (shown ? " < " : "") + name;
		}
		std::string key = StrFormat("%s\t%c\t%08x\t", site.c_str(), m_auditArmed ? 'P' : '-', m_tracePrevPc) + chain;
		auto& entry = m_traceWrites[key];
		if(entry.count++ == 0)
		{
			entry.tick = tick;
			entry.oldWord = oldWord;
			entry.newWord = newWord;
			entry.address = address;
		}
		entry.lastTick = tick;
		if(m_traceRawFile && m_traceRawCount < static_cast<uint64>(m_options.traceRaw))
		{
			m_traceRawCount++;
			fprintf(m_traceRawFile, "%u\t%" PRIu64 "\t%c\t%08x\t%08x\t%08x\t%08x\t%s\n", tick, m_frame, m_auditArmed ? 'P' : '-', address, oldWord, newWord, m_tracePrevPc, Symbolize(m_tracePrevPc).c_str());
		}
	}

	void TraceReport()
	{
		FILE* file = fopen(m_options.predictTracePath.c_str(), "w");
		if(!file) return;
		fprintf(file, "# prediction calls traced: %" PRIu64 ", blocks seen: %" PRIu64 "\n", m_traceCalls, m_traceBlocks);
		fprintf(file, "site\tinside\twriter_block\tchain\twriter\tcount\tfirst_tick\tlast_tick\taddress\told\tnew\n");
		for(const auto& entry : m_traceWrites)
		{
			uint32 block = static_cast<uint32>(strtoul(SplitChar(entry.first, '\t')[2].c_str(), nullptr, 16));
			fprintf(file, "%s\t%s\t%" PRIu64 "\t%u\t%u\t%08x\t%08x\t%08x\n", entry.first.c_str(), Symbolize(block).c_str(), entry.second.count, entry.second.tick, entry.second.lastTick, entry.second.address, entry.second.oldWord, entry.second.newWord);
		}
		fclose(file);
		if(m_traceRawFile) fclose(m_traceRawFile);
		printf("  prediction trace: %" PRIu64 " calls, %" PRIu64 " blocks, %zu distinct writers -> %s\n", m_traceCalls, m_traceBlocks, m_traceWrites.size(), m_options.predictTracePath.c_str());
	}

	// Called on the machine thread before anything has run (from the pad handler factory).
	void InstallTraceExecutor()
	{
#ifdef DEBUGGER_INCLUDED
		auto& context = m_vm.m_ee->m_EE;
		static_cast<CEeExecutor*>(context.m_executor.get())->RemoveExceptionHandler();
		auto executor = std::make_unique<CRigEeExecutor>(context, m_vm.m_ee->m_ram, [this](uint32 pc) { return OnBlock(pc); });
		m_traceExecutor = executor.get();
		context.m_executor = std::move(executor);
		static_cast<CEeExecutor*>(context.m_executor.get())->AddExceptionHandler();
#endif
	}

	// A lockstep tick: the machine is stopped at the instruction after the tick's task
	// pass (0x13aee8 in net_frameLoop). g_netFrame still holds the tick's number, and
	// the shared seed and the positions are the ones the game is about to hash.
	void OnTick()
	{
		m_ticks++;
		uint32 tick = m_machine.Read32(0x4027ac); // g_netFrame
		if(m_tickLog)
		{
			fprintf(m_tickLog, "%" PRIu64, m_frame);
			for(const auto& watch : m_tickWatches)
			{
				uint32 address = watch.expr.Eval(m_machine);
				fprintf(m_tickLog, "\t%s", FormatValue(ReadValue(m_machine, address, watch.type), watch.type).c_str());
			}
			fprintf(m_tickLog, "\n");
		}
		auto range = m_tickActions.equal_range(tick);
		for(auto it = range.first; it != range.second; ++it)
		{
			Command& command = it->second;
			try
			{
				switch(command.kind)
				{
				case Command::POKE:
				{
					uint32 address = command.target.expr.Eval(m_machine);
					Poke(address, command.bytes.data(), static_cast<uint32>(command.bytes.size()));
				}
				break;
				case Command::PNACH:
					for(const auto& word : ReadPnachSection(command.text, command.text2))
					{
						uint32 before = m_machine.Read32(word.address);
						Poke(word.address, &word.value, 4);
						printf("[tick %u] patch [%s] %08x: %08x -> %08x\n", tick, command.text2.c_str(), word.address, before, word.value);
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
					}
					printf("[tick %u] frame %" PRIu64 ": %s %s\n", tick, m_frame, file ? "dumped" : "DUMP FAILED", command.text.c_str());
				}
				break;
				case Command::SHOW:
				{
					std::string line = StrFormat("[tick %u]", tick);
					for(const auto& watch : command.watches)
					{
						uint32 address = watch.expr.Eval(m_machine);
						line += StrFormat(" %s@%08x=%s", watch.name.c_str(), address, FormatValue(ReadValue(m_machine, address, watch.type), watch.type).c_str());
					}
					printf("%s\n", line.c_str());
				}
				break;
				case Command::ECHO:
					printf("[tick %u] frame %" PRIu64 ": %s\n", tick, m_frame, command.text.c_str());
					break;
				case Command::SAVE:
					m_pendingSaves.push_back({command.text, m_vm.SaveState(command.text)});
					break;
				case Command::PRESS:
					m_pads[command.port].buttons |= command.buttons;
					break;
				case Command::RELEASE:
					m_pads[command.port].buttons &= ~command.buttons;
					break;
				case Command::BREAK:
					// break points switched on for a window of ticks: the way to ask
					// "which functions ran differently on the two machines in tick N"
					AddBreak(ParseBreak(command.text));
					break;
				case Command::QUIT:
					Finish(0);
					break;
				default:
					printf("[tick %u] ontick: this command cannot run inside a tick (line %d)\n", tick, command.line);
					break;
				}
			}
			catch(const RigError& error)
			{
				printf("[tick %u] %s\n", tick, error.what());
			}
		}
		m_tickActions.erase(range.first, range.second);
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
		if(m_tickAddress != 0 && pc == m_tickAddress)
		{
			OnTick();
			if(m_finished) return;
		}
		if(!m_auditSnapshot.empty() || m_traceOn)
		{
			if(pc == AUDIT_ENTRY)
			{
				uint32 ra = m_machine.Reg(CMIPS::RA) & 0x1FFFFFFF;
				if(m_auditReturn != ra)
				{
					m_auditReturn = ra;
					SetBreakpoint(ra, true);
				}
				if(!m_auditSnapshot.empty())
				{
					memcpy(m_auditSnapshot.data(), m_machine.ram + AUDIT_LO, AUDIT_HI - AUDIT_LO);
					m_auditGhost = m_machine.Read32(0x4027bc) & 0x1FFFFFFF;
				}
				m_auditArmed = true; // inside a prediction call
				if(m_traceOn) TraceEnter();
			}
			else if(pc == m_auditReturn && m_auditArmed)
			{
				m_auditArmed = false;
				if(!m_auditSnapshot.empty()) AuditLeave();
			}
		}

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
		printf("  machine thread cpu=%.2fs: %.1f frames per cpu-second (%.2fx real time)\n",
		       m_cpuSeconds, m_cpuSeconds > 0 ? m_frame / m_cpuSeconds : 0, m_cpuSeconds > 0 ? (m_frame / m_cpuSeconds) / 59.94 : 0);
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
		if(m_tickLog || m_ticks) printf("  lockstep ticks seen: %" PRIu64 "\n", m_ticks);
		if(!m_auditSnapshot.empty()) AuditReport();
		if(m_traceOn) TraceReport();
		if(m_ethPcap || m_ethNet)
		{
			printf("  ethernet: %" PRIu64 " frames sent by the machine, %" PRIu64 " delivered to it; UDP datagrams to the server %" PRIu64 ", from it %" PRIu64 "; to other runners %" PRIu64 " (%" PRIu64 " dropped by the path model), from them %" PRIu64 "\n", m_ethTxFrames, m_ethRxFrames, m_ethUdpOut, m_ethUdpIn, m_ethPeerOut, m_ethPeerLost, m_ethPeerIn);
			if(m_ethPcap) fclose(m_ethPcap);
		}
		if(m_netShimReady) m_netShim.Summary();
		if(m_tickLog) fclose(m_tickLog);
		if(m_log) fclose(m_log);
		if(m_breakLog) fclose(m_breakLog);
		if(m_netLog) fclose(m_netLog);
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

public:
	void SetInlineGs(CRigGsInline* gs)
	{
		m_inlineGs = gs;
	}
#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
	void SetGlGs(CRigGsOpenGL* gs)
	{
		m_glGs = gs;
	}
	CRigGsOpenGL* m_glGs = nullptr;
#endif

private:
	void SetBreakpoint(uint32 address, bool enable)
	{
		auto& context = m_vm.m_ee->m_EE;
		if(enable)
			m_realBreaks.insert(address);
		else
			m_realBreaks.erase(address);
		if(m_traceInstalled) return; // every instruction carries a break point already
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

		auto rejoin = [&](size_t first) {
			std::string rest;
			for(size_t k = first; k < tokens.size(); k++)
			{
				bool quote = tokens[k].find(' ') != std::string::npos || tokens[k].empty();
				rest += (k > first ? " " : "") + (quote ? "\"" + tokens[k] + "\"" : tokens[k]);
			}
			return rest;
		};

		// "A: command" or "B: command": for one of two joined machines. The other machine
		// lets the same number of frames pass, so the two scripts stay in step.
		if(tokens[0] == "A:" || tokens[0] == "B:" || tokens[0] == "a:" || tokens[0] == "b:")
		{
			bool mine = (toupper(static_cast<unsigned char>(tokens[0][0])) == m_options.machine);
			size_t before = m_commands.size();
			// "A: ontick N ..." registers a tick action, not a command: without this copy the
			// action stayed on the other machine too (both machines then ran it)
			auto tickActionsBefore = m_tickActions;
			ParseScriptLine(rejoin(1), lineNumber);
			if(mine) return;
			m_tickActions = tickActionsBefore;
			std::vector<Command> kept;
			for(size_t k = before; k < m_commands.size(); k++)
			{
				Command other = m_commands[k];
				switch(other.kind)
				{
				case Command::WAIT:
				case Command::AT:
				case Command::UNTIL:
					kept.push_back(other);
					break;
				case Command::TAP:
					other.kind = Command::WAIT;
					other.number = other.number + other.number2;
					kept.push_back(other);
					break;
				case Command::TAPUNTIL:
					other.buttons = 0;
					kept.push_back(other);
					break;
				case Command::FUZZ:
					other.kind = Command::WAIT;
					other.number = other.number2;
					kept.push_back(other);
					break;
				case Command::SAVE:
				case Command::LOAD:
					other.kind = Command::WAIT;
					other.number = 1;
					kept.push_back(other);
					break;
				default:
					break; // takes no frames
				}
			}
			m_commands.resize(before);
			m_commands.insert(m_commands.end(), kept.begin(), kept.end());
			return;
		}

		// "ontick N command": run a command inside lockstep tick N (see OnTick)
		if(Lower(tokens[0]) == "ontick")
		{
			int64_t tick = 0;
			if(tokens.size() < 3 || !ParseNumber(tokens[1], tick)) Die("script line %d: ontick <tick> <command>", lineNumber);
			size_t before = m_commands.size();
			ParseScriptLine(rejoin(2), lineNumber);
			for(size_t k = before; k < m_commands.size(); k++) m_tickActions.emplace(static_cast<uint32>(tick), m_commands[k]);
			m_commands.resize(before);
			m_needTickHook = true;
			return;
		}

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
		else if(word == "tapuntil")
		{
			// tapuntil <buttons> <period> <expr:type> <op> <value> [timeout N]
			need(4);
			command.kind = Command::TAPUNTIL;
			command.buttons = ParseButtons(tokens[i]);
			command.number2 = std::max<int64_t>(8, number(tokens[i + 1]));
			size_t next = 0;
			command.condition = ParseCondition(tokens, i + 2, next);
			command.number = 0;
			if(next + 1 < tokens.size() && Lower(tokens[next]) == "timeout") command.number = number(tokens[next + 1]);
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
		else if(word == "shot" || word == "iopdump")
		{
			need(1);
			command.kind = (word == "shot") ? Command::SHOT : Command::IOPDUMP;
			command.text = tokens[i];
		}
		else if(word == "ethdrop")
		{
			// ethdrop [seconds]: the relayed TCP connections lose their host side now; with a
			// number, new connections are refused for that many seconds of real time as well
			command.kind = Command::ETHDROP;
			command.number = (tokens.size() > i) ? strtoll(tokens[i].c_str(), nullptr, 0) : 0;
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
		else if(word == "netshim")
		{
			command.kind = Command::NETSHIM;
		}
		else if(word == "fuzz")
		{
			// fuzz <seed> <frames> <groups>: random input; groups are move, rstick and the
			// button groups of g_fuzzButtons, joined by commas
			need(3);
			command.kind = Command::FUZZ;
			command.number = number(tokens[i]);
			command.number2 = number(tokens[i + 1]);
			for(const auto& group : SplitChar(Lower(tokens[i + 2]), ','))
			{
				bool known = false;
				if(group == "move")
				{
					command.fuzzMask |= FUZZ_MOVE;
					known = true;
				}
				if(group == "rstick")
				{
					command.fuzzMask |= FUZZ_RSTICK;
					known = true;
				}
				if(group == "idle") known = true; // no input at all
				for(const auto& entry : g_fuzzButtons)
				{
					if(group == entry.group)
					{
						command.fuzzMask |= (1u << entry.button);
						known = true;
					}
				}
				if(!known) Die("script line %d: unknown fuzz group '%s'", lineNumber, group.c_str());
			}
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
				if(m_options.interactiveLive)
				{
					// nothing waiting: this frame runs, and the input is looked at again
					// at the next vertical blank
					if(!PollInteractiveCommand()) return;
				}
				else if(!ReadInteractiveCommand())
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
			case Command::TAPUNTIL:
			{
				// one tap (4 frames held) per period until the condition holds; the
				// condition is looked at only between taps, never while one is down
				if(!command.started)
				{
					command.started = true;
					command.deadline = command.number ? m_frame + command.number : 0;
					command.phaseStart = m_frame;
					if(command.condition.op == Condition::CHANGED)
					{
						command.condition.reference = ReadValue(m_machine, command.condition.watch.expr.Eval(m_machine), command.condition.watch.type);
					}
				}
				uint64 phase = (m_frame - command.phaseStart) % static_cast<uint64>(command.number2);
				if(phase == 0)
				{
					if(command.condition.Test(m_machine))
					{
						printf("[frame %" PRIu64 "] tapuntil %s\n", m_frame, command.condition.text.c_str());
						break;
					}
					if(command.deadline && m_frame >= command.deadline)
					{
						printf("[frame %" PRIu64 "] TIMEOUT line %d: tapuntil %s\n", m_frame, command.line, command.condition.text.c_str());
						Finish(3);
						return;
					}
					pad.buttons |= command.buttons;
				}
				else if(phase == 4)
				{
					pad.buttons &= ~command.buttons;
				}
				return;
			}
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
			case Command::SHOT:
			{
				bool ok = false;
#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
				if(m_glGs) ok = m_glGs->Screenshot(command.text);
#endif
				printf("[frame %" PRIu64 "] %s %s\n", m_frame, ok ? "picture" : "NO PICTURE (needs --video)", command.text.c_str());
			}
			break;
			case Command::ETHDROP:
				EtherDrop(static_cast<double>(command.number));
				break;
			case Command::IOPDUMP:
			{
				FILE* file = fopen(command.text.c_str(), "wb");
				if(file)
				{
					fwrite(m_vm.m_iop->m_ram, 1, PS2::IOP_RAM_SIZE, file);
					fclose(file);
				}
				printf("[frame %" PRIu64 "] %s %s\n", m_frame, file ? "IOP memory dumped" : "DUMP FAILED", command.text.c_str());
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
			case Command::NETSHIM:
				InstallNetShim();
				break;
			case Command::FUZZ:
			{
				if(!command.started)
				{
					command.started = true;
					command.deadline = m_frame + command.number2;
					// the two machines draw different input from the same seed
					command.rng = 0x9E3779B97F4A7C15ull ^ (static_cast<uint64>(command.number) * 0x100000001B3ull) ^ (m_options.machine == 'B' ? 0x5851F42D4C957F2Dull : 0);
				}
				auto next = [&command]() {
					command.rng ^= command.rng >> 12;
					command.rng ^= command.rng << 25;
					command.rng ^= command.rng >> 27;
					return static_cast<uint32>((command.rng * 0x2545F4914F6CDD1Dull) >> 32);
				};
				if(m_frame >= command.deadline)
				{
					for(const auto& entry : g_fuzzButtons)
					{
						if(command.fuzzMask & (1u << entry.button)) pad.buttons &= ~(1u << entry.button);
					}
					for(int k = 0; k < 4; k++) pad.axis[k] = 0x80;
					break;
				}
				for(int stick = 0; stick < 2; stick++)
				{
					if(!(command.fuzzMask & (stick == 0 ? FUZZ_MOVE : FUZZ_RSTICK))) continue;
					if(command.stickHold[stick] > 0)
					{
						command.stickHold[stick]--;
						continue;
					}
					uint32 choice = next() % 8;
					uint8 x = 0x80, y = 0x80;
					if(choice >= 2 && choice <= 5)
					{
						static const uint8 full[8][2] = {{0x80, 0x00}, {0xff, 0x00}, {0xff, 0x80}, {0xff, 0xff}, {0x80, 0xff}, {0x00, 0xff}, {0x00, 0x80}, {0x00, 0x00}};
						uint32 direction = next() % 8;
						x = full[direction][0];
						y = full[direction][1];
					}
					else if(choice >= 6)
					{
						x = static_cast<uint8>(next());
						y = static_cast<uint8>(next());
					}
					pad.axis[stick * 2] = x;
					pad.axis[stick * 2 + 1] = y;
					command.stickHold[stick] = 5 + next() % 55;
				}
				for(const auto& entry : g_fuzzButtons)
				{
					if(!(command.fuzzMask & (1u << entry.button))) continue;
					uint32& hold = command.buttonHold[entry.button];
					if(hold > 0)
					{
						if(--hold == 0) pad.buttons &= ~(1u << entry.button);
					}
					else if(next() % 1000 < entry.rate)
					{
						pad.buttons |= (1u << entry.button);
						hold = entry.holdMin + next() % entry.holdSpan;
					}
				}
				return;
			}
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
		if(m_netLog) fflush(m_netLog);
		if(m_tickLog) fflush(m_tickLog);
	}

	// Writes the four-instruction host-call stub over each libnet entry point. The
	// words replaced are printed, so a log shows what the executable held there.
	void InstallNetShim()
	{
		if(!m_netShimReady) Die("netshim: start the runner with --net-shim <address>");
		for(int i = 0; i < CNetShim::CALL_COUNT; i++)
		{
			const auto& entry = CNetShim::Entries()[i];
			uint32 stub[4] = {
			    0x3C011E00,                               // lui $at, 0x1e00
			    0xAC200000 | static_cast<uint32>(i * 4), // sw $zero, 4*i($at)
			    0x03E00008,                               // jr $ra
			    0x00000000,                               // nop
			};
			uint32 before = m_machine.Read32(entry.address);
			Poke(entry.address, stub, sizeof(stub));
			printf("[frame %" PRIu64 "] net shim: %s at %08x replaced (first word was %08x)\n", m_frame, entry.name, entry.address, before);
		}
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

	// The same for a live session (--interactive-live): the machine is not held. Whatever
	// has arrived on standard input is taken without waiting; returns true when at least
	// one complete command line was added. A machine that talks to a server through host
	// sockets must not stand still between commands: the server would time it out.
	bool PollInteractiveCommand()
	{
		bool added = false;
		char buffer[4096];
		if(!m_liveInputReady)
		{
			// read() must come back at once when nothing is waiting
			fcntl(0, F_SETFL, fcntl(0, F_GETFL, 0) | O_NONBLOCK);
			m_liveInputReady = true;
		}
		for(;;)
		{
			ssize_t n = read(0, buffer, sizeof(buffer));
			if(n > 0)
			{
				m_liveInput.append(buffer, static_cast<size_t>(n));
				continue;
			}
			if(n == 0) m_inputClosed = true; // end of input: the run ends when the commands have
			break;
		}
		size_t end;
		while((end = m_liveInput.find('\n')) != std::string::npos)
		{
			std::string line = m_liveInput.substr(0, end);
			m_liveInput.erase(0, end + 1);
			size_t before = m_commands.size();
			try
			{
				ParseScriptLine(line, 0);
			}
			catch(const RigError& error)
			{
				printf("[error] %s\n", error.what());
				m_commands.resize(before);
			}
			if(m_commands.size() > before) added = true;
		}
		if(!added && (m_frame % 30) == 0) FlushOutputs();
		return added;
	}

	// Strings gathered by 'collect' break points since the last vertical blank. They are
	// printed only when the set differs from the previous frame's, which gives a
	// transcript of what the game put on the screen.
	void FlushCollected()
	{
		// A frame in which nothing was drawn (the game took two fields over one frame)
		// is not a change of screen.
		if(m_collected.empty()) return;
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

	// CPU time used by the calling thread. Emulation speed is reported against this as
	// well as against the wall clock, because the wall clock says little on a busy host.
	static double ThreadCpuSeconds()
	{
		struct timespec time = {};
		clock_gettime(CLOCK_THREAD_CPUTIME_ID, &time);
		return time.tv_sec + time.tv_nsec * 1e-9;
	}

	void Finish(int exitCode)
	{
		if(m_finished) return;
		m_cpuSeconds = ThreadCpuSeconds() - m_cpuStart;
		if(m_link.Active() && exitCode != 6) m_link.Send(m_frame, true, {});
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
	std::chrono::steady_clock::time_point m_fpsMark;
	double m_fpsCpuMark = 0;
	bool m_fpsMarkSet = false;
	double m_cpuStart = 0;
	double m_cpuSeconds = 0;
	CRigGsInline* m_inlineGs = nullptr;

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

	enum : uint32
	{
		AUDIT_ENTRY = 0x00131D88, // net_predictLocalPlayer
		AUDIT_LO = 0x003E9C00,    // start of the data sections
		AUDIT_HI = 0x02000000,
	};
	struct AUDIT_SITE
	{
		uint64 count = 0;
		uint32 tick = 0, oldWord = 0, newWord = 0;
		std::string where;
	};
	struct AUDIT_HEAP_BLOCK
	{
		uint32 start, end, caller;
		bool used;
	};
	std::vector<AUDIT_HEAP_BLOCK> m_auditHeap;
	std::vector<std::string> m_auditListExamples;
	uint64 m_auditOrderCalls = 0, m_auditMemberCalls = 0;

	enum : uint32
	{
		TEXT_LO = 0x00100000, // the executable's code
		TEXT_HI = 0x003E9C00,
	};
	struct TRACE_FRAME
	{
		uint32 pc, sp, ra;
	};
	struct TRACE_WRITE
	{
		uint64 count = 0;
		uint32 tick = 0, lastTick = 0, oldWord = 0, newWord = 0, address = 0;
	};
	std::vector<TRACE_RANGE> m_traceRanges;
	std::vector<TRACE_FRAME> m_traceStack;
	std::map<std::string, TRACE_WRITE> m_traceWrites;
	std::unordered_set<uint32> m_realBreaks;
#ifdef DEBUGGER_INCLUDED
	CRigEeExecutor* m_traceExecutor = nullptr;
#else
	void* m_traceExecutor = nullptr;
#endif
	FILE* m_ethPcap = nullptr;
	uint64 m_ethTxFrames = 0, m_ethRxFrames = 0, m_ethUdpOut = 0, m_ethUdpIn = 0, m_ethPeerOut = 0, m_ethPeerIn = 0;
	std::set<uint16> m_ethServerUdpPorts = {10101};
	struct ETH_HELD
	{
		uint64 release = 0;
		int fd = -1;
		uint16 destPort = 0;
		std::vector<uint8> data;
	};
	std::deque<ETH_HELD> m_ethPeerQueue;
	uint32 m_ethPeerDelay = 0, m_ethPeerJitter = 0, m_ethPeerLoss = 0;
	uint64 m_ethPeerRng = 0x9E3779B97F4A7C15ull, m_ethPeerLost = 0;
	std::chrono::system_clock::time_point m_ethBlockedUntil;
	std::chrono::system_clock::time_point m_ethLastBlank;
	bool m_ethLastBlankSet = false;
	enum : uint32
	{
		ETH_GATEWAY_IP = 0x0A000202, // 10.0.2.2
		ETH_MARKER = 0x52494721,
		ETH_TCP_MSS = 1340,
	};
	static constexpr uint8 ETH_GATEWAY_MAC[6] = {0x02, 0x52, 0x49, 0x47, 0x00, 0x01};
	static constexpr uint8 ETH_BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
	bool m_ethNet = false;
	uint32 m_ethGuestIp = 0x0A00020F, m_ethServerIp = 0; // 10.0.2.15
	std::string m_ethName = "con.soegames.net";
	uint8 m_ethGuestMac[6] = {};
	uint16 m_ethIpId = 1;
	int m_ethTcpCount = 0;
	std::deque<std::vector<uint8>> m_ethRxQueue;
	std::map<uint16, int> m_ethUdp;
	std::map<uint64, ETH_TCP> m_ethTcp;
	std::set<uint64> m_ethRefused;
	FILE* m_traceRawFile = nullptr;
	uint64 m_traceRawCount = 0, m_traceCalls = 0, m_traceBlocks = 0;
	uint32 m_traceTickLo = 0, m_traceTickHi = 0xFFFFFFFF, m_tracePrevPc = 0, m_tracePrevEnd = 0;
	bool m_traceOn = false, m_traceInstalled = false, m_traceActive = false;
	std::vector<uint8> m_auditSnapshot;
	std::map<uint32, AUDIT_SITE> m_auditSites;
	uint32 m_auditReturn = 0, m_auditGhost = 0;
	bool m_auditArmed = false;
	uint64 m_auditCalls = 0;

	CNetShim m_netShim;
	bool m_netShimReady = false;
	FILE* m_netLog = nullptr;
	CLink m_link;

	// lockstep ticks
	std::vector<Watch> m_tickWatches;
	FILE* m_tickLog = nullptr;
	uint32 m_tickAddress = 0;
	bool m_needTickHook = false;
	std::multimap<uint32, Command> m_tickActions;
	uint64 m_ticks = 0;

	std::vector<Command> m_commands;
	size_t m_scriptPosition = 0;
	bool m_scriptDone = false;
	bool m_inputClosed = false;
	std::string m_liveInput;
	bool m_liveInputReady = false;

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
	    "  --interactive-live     the same, but the machine keeps running between commands (for runs\n"
	    "                         that hold connections to a server through host sockets)\n"
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
	    "  --fps-every <n>        print the emulation speed every n frames\n"
	    "  --play-logs            let Play! write its own logs under <data>/logs\n"
	    "  --throttle             run at the console's speed instead of as fast as possible\n"
	    "  --no-code-protect      do not write-protect host pages that hold translated code (see README)\n"
	    "  --profile              sample the machine and video threads; print where wall time went\n"
	    "  --video-thread         give the null video handler its own thread, as Play! normally does\n"
	    "  --eth-pcap <file>      every Ethernet frame of the emulated network adaptor, as a capture file\n"
	    "  --eth-net server=<a.b.c.d>[,guest=<a.b.c.d>][,name=<host>][,udp=<port>+<port>]\n"
	    "                         a small network behind the adaptor for the game's own network stack: DHCP,\n"
	    "                         DNS for one name, TCP and UDP relayed to the server's address only; UDP for\n"
	    "                         that address on other ports than the server's goes to another runner on\n"
	    "                         this host through 127.0.0.1 (see README.md); for those datagrams also\n"
	    "                         ,peerdelay=<frames>,peerjitter=<frames>,peerloss=<per 1000>,peerseed=<n>\n"
	    "  --net-shim <a.b.c.d>   claim this address and be ready to replace the game's libnet entry\n"
	    "                         points; the script command 'netshim' installs the replacements\n"
	    "  --net-log <file>       log of the shim's calls and of the lobby's short datagrams\n"
	    "  --net-log-all          ... and of every datagram\n"
	    "  --machine A|B          which of two joined machines this is (script lines tagged A: or B:)\n"
	    "  --link listen:<path> | connect:<path>   join a second runner; the two advance frame by frame\n"
	    "  --bus delay=N,jitter=N,loss=N,seed=N,stallat=F,stall=N   what the bus does to datagrams that cross\n"
	    "                         (frames; loss per 1000; stall: nothing crosses for N frames from frame F)\n"
	    "  --predict-audit <file> snapshot memory around every call of net_predictLocalPlayer (0x131d88) and\n"
	    "                         list what it left changed, outside an ignore list (needs break points)\n"
	    "  --predict-trace <file> which code writes the --trace-range words during prediction calls: writers\n"
	    "                         gathered by site, block and call chain (needs break points)\n"
	    "  --trace-range <addr:length[:stride][,all][,name=N]>   a range to watch; 'all': outside the calls too\n"
	    "  --trace-ticks <lo:hi>  trace only in these lockstep ticks;  --trace-raw <n>: also the first n writes\n"
	    "                         one by one, to <file>.raw\n"
	    "  --fp-round nearest|up|down|zero   force a floating-point rounding mode on this machine's thread\n"
	    "                         (Play! runs the EE with round-toward-zero); for float-mismatch experiments\n"
	    "  --tick-log <file>      one row of the --tick-watch values per lockstep tick (needs break points)\n"
	    "  --tick-watch <name=expr:type>   a value for the tick log; repeatable\n"
	    "  --tick-at <addr>       where a tick is logged (default 0x13aee8, the return from the tick's tasks)\n");
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
		else if(arg == "--fps-every")
			options.fpsEvery = static_cast<uint32>(strtoul(value().c_str(), nullptr, 0));
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
		else if(arg == "--interactive-live")
			options.interactive = options.interactiveLive = true;
		else if(arg == "--video-thread")
			options.videoThread = true;
		else if(arg == "--video")
			options.video = true;
		else if(arg == "--eth-pcap")
			options.ethPcapPath = value();
		else if(arg == "--eth-net")
			options.ethNetSpec = value();
		else if(arg == "--net-shim")
			options.netShimAddress = value();
		else if(arg == "--net-log")
			options.netLogPath = value();
		else if(arg == "--net-log-all")
			options.netLogAll = true;
		else if(arg == "--machine")
		{
			std::string letter = value();
			if(letter != "A" && letter != "B") Die("--machine A or B");
			options.machine = letter[0];
		}
		else if(arg == "--link")
			options.linkSpec = value();
		else if(arg == "--bus")
		{
			// delay=N,jitter=N,loss=N (per thousand),seed=N
			for(const auto& part : SplitChar(value(), ','))
			{
				auto equals = part.find('=');
				int64_t number = 0;
				if(equals == std::string::npos || !ParseNumber(part.substr(equals + 1), number) || number < 0) Die("--bus delay=N,jitter=N,loss=N,seed=N");
				std::string key = part.substr(0, equals);
				if(key == "delay")
					options.bus.delay = static_cast<uint32>(number);
				else if(key == "jitter")
					options.bus.jitter = static_cast<uint32>(number);
				else if(key == "loss")
					options.bus.lossPerMille = static_cast<uint32>(number);
				else if(key == "seed")
					options.bus.state = 0x9E3779B97F4A7C15ull ^ (static_cast<uint64>(number) * 0x100000001B3ull);
				else if(key == "stallat")
					options.bus.stallAt = static_cast<uint64>(number);
				else if(key == "stall")
					options.bus.stallFrames = static_cast<uint64>(number);
				else
					Die("--bus: unknown key '%s'", key.c_str());
			}
		}
		else if(arg == "--fp-round")
		{
			std::string mode = value();
			if(mode == "nearest")
				options.fpRound = FE_TONEAREST;
			else if(mode == "up")
				options.fpRound = FE_UPWARD;
			else if(mode == "down")
				options.fpRound = FE_DOWNWARD;
			else if(mode == "zero")
				options.fpRound = FE_TOWARDZERO;
			else
				Die("--fp-round nearest|up|down|zero");
		}
		else if(arg == "--predict-audit")
			options.predictAuditPath = value();
		else if(arg == "--predict-trace")
			options.predictTracePath = value();
		else if(arg == "--trace-range")
			options.traceRangeSpecs.push_back(value());
		else if(arg == "--trace-ticks")
			options.traceTicks = value();
		else if(arg == "--trace-raw")
			options.traceRaw = atoi(value().c_str());
		else if(arg == "--tick-log")
			options.tickLogPath = value();
		else if(arg == "--tick-watch")
			options.tickWatchSpecs.push_back(value());
		else if(arg == "--tick-at")
			options.tickAddress = value();
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
	// a relayed connection that the other side has closed must give an error, not end the run
	signal(SIGPIPE, SIG_IGN);

	g_basePath = fs::absolute(options.data);
	fs::create_directories(g_basePath);

	// Preferences must exist before the objects that read them are made.
	CAppConfig::GetInstance().RegisterPreferenceBoolean("log.showprints", false);
	CAppConfig::GetInstance().SetPreferenceBoolean("log.showprints", options.playLogs);

#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
	CGSH_OpenGL::RegisterPreferences();
#endif
	CRigVM vm;
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_CDROM0_PATH, fs::absolute(options.disc));
	// The memory cards are directories under the data directory. Play! stores their paths
	// in the data directory's config.xml as absolute paths, so a copied data directory
	// would go on using the cards of the one it was copied from: set them every time.
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_MC0_DIRECTORY, g_basePath / "vfs" / "mc0");
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_MC1_DIRECTORY, g_basePath / "vfs" / "mc1");
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_HOST_DIRECTORY, g_basePath / "vfs" / "host");
	CAppConfig::GetInstance().SetPreferencePath(PREF_PS2_ROM0_DIRECTORY, g_basePath / "vfs" / "rom0");
	CAppConfig::GetInstance().SetPreferenceBoolean(PREF_PS2_LIMIT_FRAMERATE, options.throttle);

	CRig rig(vm, options);
	CRigPad* padHandler = nullptr;

	vm.Initialize();
	if(options.video)
	{
#if defined(RTA_RIG_VIDEO) && defined(__APPLE__)
		vm.CreateGSHandler(CRigGsOpenGL::GetFactoryFunction());
		rig.SetGlGs(static_cast<CRigGsOpenGL*>(vm.GetGSHandler()));
#else
		fprintf(stderr, "rta_rig: built without --video\n");
		return 2;
#endif
	}
	else if(options.videoThread)
	{
		vm.CreateGSHandler(CRigGsNull::GetFactoryFunction());
	}
	else
	{
		vm.CreateGSHandler(CRigGsInline::GetFactoryFunction());
		rig.SetInlineGs(static_cast<CRigGsInline*>(vm.GetGSHandler()));
	}
	vm.CreatePadHandler([&]() {
		if(!options.predictTracePath.empty()) rig.InstallTraceExecutor();
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
		fprintf(stderr, "rta_rig: boot failed: %s\n", exception.what());
		vm.DestroyPadHandler();
		vm.DestroyGSHandler();
		vm.Destroy();
		return 2;
	}
	printf("booted %s\n", vm.m_ee->m_os->GetExecutableName());

	if(!options.loadState.empty())
	{
		if(!vm.LoadState(options.loadState).get())
		{
			fprintf(stderr, "rta_rig: cannot load state %s\n", options.loadState.c_str());
			vm.DestroyPadHandler();
			vm.DestroyGSHandler();
			vm.Destroy();
			return 2;
		}
		printf("state loaded: %s\n", options.loadState.c_str());
	}

	// From here on the machine thread exists, so an error must not unwind past the
	// orderly shutdown at the end.
	int exitCode = 0;
	Framework::CSignal<void()>::Connection connection;
	try
	{
		rig.Prepare();
		connection = vm.OnRunningStateChange.Connect([&]() { rig.OnRunningStateChange(); });

		auto startTime = std::chrono::steady_clock::now();
		vm.Resume();
		rig.WaitFinished();
		vm.Pause();
		double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - startTime).count();

		rig.WaitPendingSaves();
		exitCode = rig.ExitCode();
		if(!options.saveStateAtEnd.empty())
		{
			bool ok = vm.SaveState(options.saveStateAtEnd).get();
			printf("state %s: %s\n", ok ? "saved" : "NOT saved", options.saveStateAtEnd.c_str());
			if(!ok) exitCode = 5;
		}
		rig.Summary(seconds);
		prof::Report();
	}
	catch(const RigError& error)
	{
		fprintf(stderr, "rta_rig: %s\n", error.what());
		exitCode = 2;
		vm.Pause();
	}

	connection.reset();
	vm.DestroyPadHandler();
	vm.DestroyGSHandler();
	vm.Destroy();
	return exitCode;
}
