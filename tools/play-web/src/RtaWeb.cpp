// play-web: Champions: Return to Arms in a web browser.
//
// The browser front end of the Play! emulator for this one game: what joins the machine
// to the page (tools/play-web/web/rta-web.js). It takes the place of Play!'s own
// Source/ui_js/Main.cpp and does what tools/play-net/src/Rta.cpp does for the desktop
// application, as far as a browser allows:
//  - the patch set (patches/SLUS-20973_4028A55F.pnach, the sections the page names) and
//    the display patches that make the picture steady, written when the game's
//    executable has been loaded and checked;
//  - the pad: one word of buttons and four axes that the page writes (keyboard, Gamepad
//    API), and a queue of scripted presses for tests;
//  - the video thread owning the canvas (see CGSHandler::g_webCanvas in play-web.patch);
//  - sound into a ring that an AudioWorklet of the page plays from;
//  - counters for the speed figures, and a comparison of consecutive pictures;
//  - online play (RtaWebNet.cpp), on a page that has a relay.
// Everything here is called from the page's main thread unless it says otherwise.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <emscripten.h>
#include <emscripten/html5.h>
#include <emscripten/threading.h>

#include "AppConfig.h"
#include "DefaultAppConfig.h"
#include "FrameLimiter.h"
#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "PadHandler.h"
#include "Ps2VmJs.h"
#include "RtaWebNet.h"
#include "ee/PS2OS.h"
#include "gs/GSH_OpenGL/GSH_OpenGL.h"
#include "sound/SoundHandler.h"
#ifdef PROFILE
#include "Profiler.h"
#endif

extern "C" uint32 RtaWebDiscCounter(int);
extern std::atomic<uint32> g_rtaWebFunctionCount;
extern std::atomic<uint64> g_rtaWebFunctionMicros;
extern unsigned int g_rtaWebDispatches;

namespace
{
	// The executable the patches are for, and the checksum PCSX2 names its patch files by
	// (every 32-bit word of the file exclusive-ored together). As tools/play-net/src/Rta.cpp.
	const char* GAME_EXECUTABLE = "SLUS_209.73";
	const uint32 GAME_CRC = 0x4028A55F;

	struct PatchWord
	{
		uint32 address = 0;
		uint32 value = 0;
	};

	// The display patches of the desktop application (tools/play-net/src/Rta.cpp,
	// g_displayPatches; what each does is told there and in tools/play-net/README.md).
	// They change drawing only and are applied only where the expected word is found.
	struct DisplayPatch
	{
		uint32 address;
		uint32 original;
		uint32 value;
	};
	const DisplayPatch g_displayPatches[] = {
	    {0x0019C904, 0x240A7208, 0x240A7200}, // same drawing offset on both television fields
	    {0x0019D9EC, 0x8C420008, 0x00001021}, // gfx_displayField always answers "first field"
	    {0x0017AB58, 0x8C43FDB4, 0x24030001}, // interface sprites from both field pictures
	    {0x0017BAE4, 0x8C43FDB4, 0x24030001}, // the second sprite drawer
	    {0x00180D2C, 0x8C43FDB4, 0x24030001}, // text from both field pictures
	    {0x00180FEC, 0x8C43FDB4, 0x24030001}, // text in two passes, one per field picture
	};

	enum GL_MODE
	{
		GL_MODE_MAIN_THREAD = 0, // as Play! does it: every GL call goes to the page's main thread
		GL_MODE_OWN_CANVAS = 1,  // the video thread owns the canvas (OffscreenCanvas)
	};

	// What the page writes and reads directly in the machine's memory (rtaShared gives the
	// address): 32-bit words.
	struct Shared
	{
		uint32 buttons = 0;                     // 0: bit n is PS2::CControllerInfo::BUTTON n
		uint32 axes[4] = {128, 128, 128, 128};  // 1..4: left x, left y, right x, right y (0..255)
		uint32 axesSet = 0;                     // 5: bit 0 the left stick is given, bit 1 the right
		uint32 limiter = 1;                     // 6: 1 the machine is held to its frame rate, 0 it runs free
		uint32 burst = 0;                       // 7: pictures still to compare
	};
	Shared g_shared;

	struct Step
	{
		uint32 buttons = 0;
		uint32 frames = 0;
		bool stick = false; // the left stick is given for these frames
		uint8 x = 128, y = 128;
	};

	// DEV: what the game's memory held at one place, frame by frame (rtaTrace)
	struct Trace
	{
		uint32 pointer = 0; // 0: 'offset' is the address itself; else the address of a pointer to add it to
		uint32 offset = 0;
		uint32 size = 0;
		uint32 left = 0;
		std::vector<uint8> bytes;
	};

	struct BurstEntry
	{
		uint32 differing = 0; // pixels that differ from the picture before
		uint32 maxDelta = 0;  // largest difference of one colour value
		double time = 0;      // when it was handed over (ms)
		uint64 sum = 0;       // sum of all colour values (to tell a black picture)
	};

	CPs2VmJs* g_vm = nullptr;
	int g_glMode = GL_MODE_OWN_CANVAS;
	int g_canvasWidth = 640, g_canvasHeight = 480;
	EMSCRIPTEN_WEBGL_CONTEXT_HANDLE g_mainContext = 0;
	std::atomic<int> g_ready(0);
	std::string g_error;

	std::mutex g_mutex; // patches, steps, burst results, text
	std::vector<PatchWord> g_patches;
	std::vector<PatchWord> g_activePatches;
	bool g_wantDisplayPatches = true;
	std::deque<Step> g_steps;
	Trace g_trace;
	std::vector<BurstEntry> g_burst;
	std::vector<uint8> g_burstLast, g_burstNow;
	std::string g_executable;
	std::string g_text;

	std::atomic<bool> g_isGame(false);
	std::atomic<uint32> g_crc(0);
	std::atomic<uint32> g_frames(0);
	std::atomic<uint32> g_presents(0);
	std::atomic<uint64> g_waitMicros(0);
	std::atomic<uint32> g_patchRewrites(0);
	std::atomic<uint32> g_displayPatchCount(0);
	std::atomic<uint32> g_drawCalls(0);
	std::atomic<uint32> g_soundWritten(0), g_soundDropped(0);
	// DEV: one picture of the canvas for a test (rtaShot): 1 wanted, 2 taken
	std::atomic<int> g_shotState(0);
	std::vector<uint8> g_shotPixels;

	std::string Format(const char* format, ...)
	{
		char text[1024];
		va_list args;
		va_start(args, format);
		vsnprintf(text, sizeof(text), format, args);
		va_end(args);
		return text;
	}

	std::string Trim(std::string s)
	{
		while(!s.empty() && (s.back() == '\r' || s.back() == '\n' || s.back() == ' ' || s.back() == '\t')) s.pop_back();
		size_t start = 0;
		while(start < s.size() && (s[start] == ' ' || s[start] == '\t')) start++;
		return s.substr(start);
	}

	std::vector<std::string> Split(const std::string& s, char separator)
	{
		std::vector<std::string> parts;
		std::string part;
		std::istringstream stream(s);
		while(std::getline(stream, part, separator)) parts.push_back(part);
		return parts;
	}

	// ---- the video handler -------------------------------------------------------------
	class CGSH_OpenGLWeb : public CGSH_OpenGL
	{
	public:
		void InitializeImpl() override
		{
			if(g_glMode == GL_MODE_OWN_CANVAS)
			{
				// on the video thread, which was given the canvas when it was started
				EmscriptenWebGLContextAttributes attributes;
				emscripten_webgl_init_context_attributes(&attributes);
				attributes.majorVersion = 2;
				attributes.minorVersion = 0;
				attributes.alpha = false;
				attributes.depth = false;
				attributes.stencil = false;
				attributes.antialias = false;
				attributes.powerPreference = EM_WEBGL_POWER_PREFERENCE_HIGH_PERFORMANCE;
				attributes.proxyContextToMainThread = EMSCRIPTEN_WEBGL_CONTEXT_PROXY_DISALLOW;
				attributes.renderViaOffscreenBackBuffer = false;
				m_context = emscripten_webgl_create_context("#outputCanvas", &attributes);
				if(m_context <= 0) printf("RTA: the video thread could not make a WebGL 2 context on the canvas (%d).\n", static_cast<int>(m_context));
			}
			else
			{
				m_context = g_mainContext;
			}
			emscripten_webgl_make_context_current(m_context);
			CGSH_OpenGL::InitializeImpl();
		}

		void ReleaseImpl() override
		{
			CGSH_OpenGL::ReleaseImpl();
		}

		void PresentBackbuffer() override
		{
			g_presents++;
			m_webPresented = true;
			if(g_shared.burst != 0) Compare();
			if(g_shotState == 1)
			{
				g_shotPixels.resize(static_cast<size_t>(g_canvasWidth) * g_canvasHeight * 4);
				glBindFramebuffer(GL_FRAMEBUFFER, 0);
				glPixelStorei(GL_PACK_ALIGNMENT, 4);
				glReadPixels(0, 0, g_canvasWidth, g_canvasHeight, GL_RGBA, GL_UNSIGNED_BYTE, g_shotPixels.data());
				g_shotState = 2;
			}
		}

	private:
		// The picture just drawn on the canvas against the one before, for the question
		// "does a still screen stand still". Nothing of the picture leaves this function
		// but counts.
		void Compare()
		{
			size_t size = static_cast<size_t>(g_canvasWidth) * g_canvasHeight * 4;
			g_burstNow.resize(size);
			glBindFramebuffer(GL_FRAMEBUFFER, 0);
			glPixelStorei(GL_PACK_ALIGNMENT, 4);
			glReadPixels(0, 0, g_canvasWidth, g_canvasHeight, GL_RGBA, GL_UNSIGNED_BYTE, g_burstNow.data());
			BurstEntry entry;
			entry.time = emscripten_get_now();
			const uint8* now = g_burstNow.data();
			for(size_t i = 0; i < size; i += 4) entry.sum += now[i] + now[i + 1] + now[i + 2];
			if(g_burstLast.size() == size)
			{
				const uint8* last = g_burstLast.data();
				for(size_t i = 0; i < size; i += 4)
				{
					uint32 delta = 0;
					for(int c = 0; c < 3; c++)
					{
						int d = static_cast<int>(now[i + c]) - static_cast<int>(last[i + c]);
						delta = std::max<uint32>(delta, static_cast<uint32>(d < 0 ? -d : d));
					}
					if(delta != 0) entry.differing++;
					entry.maxDelta = std::max(entry.maxDelta, delta);
				}
			}
			else
			{
				entry.differing = 0xFFFFFFFF; // the first of a burst has nothing before it
			}
			g_burstLast.swap(g_burstNow);
			std::lock_guard lock(g_mutex);
			g_burst.push_back(entry);
			if(--g_shared.burst == 0) g_burstLast.clear();
		}

		EMSCRIPTEN_WEBGL_CONTEXT_HANDLE m_context = 0;
	};

	// ---- sound -------------------------------------------------------------------------
	// The machine's thread writes stereo 16-bit samples into a ring in the shared memory;
	// an AudioWorklet of the page reads them (rta-web.js). Nothing goes through the page's
	// main thread. Words at g_soundRing: [0] write index, [1] read index (both in samples,
	// counting up for ever; the worklet owns the read index), then the samples.
	const uint32 SOUND_RING_SAMPLES = 1 << 15; // 16384 stereo frames, 371 ms at 44100 Hz
	struct SoundRing
	{
		std::atomic<uint32> write;
		std::atomic<uint32> read;
		uint32 size = SOUND_RING_SAMPLES;
		uint32 rate = 44100;
		int16 samples[SOUND_RING_SAMPLES];
	};
	SoundRing g_soundRing;

	class CSoundHandlerWeb : public CSoundHandler
	{
	public:
		void Reset() override
		{
		}

		void Write(int16* samples, unsigned int sampleCount, unsigned int sampleRate) override
		{
			g_soundRing.rate = sampleRate;
			uint32 write = g_soundRing.write.load(std::memory_order_relaxed);
			uint32 read = g_soundRing.read.load(std::memory_order_acquire);
			uint32 used = write - read;
			if(used > SOUND_RING_SAMPLES || (SOUND_RING_SAMPLES - used) < sampleCount)
			{
				// nobody is playing (no page gesture yet, or the tab's sound is asleep)
				g_soundDropped += sampleCount;
				return;
			}
			for(unsigned int i = 0; i < sampleCount; i++)
			{
				g_soundRing.samples[(write + i) & (SOUND_RING_SAMPLES - 1)] = samples[i];
			}
			g_soundRing.write.store(write + sampleCount, std::memory_order_release);
			g_soundWritten += sampleCount;
		}

		bool HasFreeBuffers() override
		{
			return true;
		}

		void RecycleBuffers() override
		{
		}
	};

	// ---- the pad -----------------------------------------------------------------------
	void CheckPatches(uint8* ram);

	class CPadHandlerWeb : public CPadHandler
	{
	public:
		// every vertical blank, on the machine's thread, immediately after the wait that
		// holds the frame rate
		void Update(uint8* ram) override
		{
			g_frames++;
			CheckPatches(ram);
			uint32 buttons = g_shared.buttons;
			uint32 axesSet = g_shared.axesSet;
			uint32 axes[4] = {g_shared.axes[0], g_shared.axes[1], g_shared.axes[2], g_shared.axes[3]};
			{
				std::lock_guard lock(g_mutex);
				if(g_trace.left != 0)
				{
					uint32 address = g_trace.offset;
					if(g_trace.pointer != 0)
					{
						uint32 base = 0;
						memcpy(&base, ram + (g_trace.pointer & (PS2::EE_RAM_SIZE - 4)), 4);
						address = (base != 0) ? (base + g_trace.offset) : 0;
					}
					address &= 0x1FFFFFFF;
					size_t at = g_trace.bytes.size();
					g_trace.bytes.resize(at + g_trace.size, 0);
					if(address != 0 && (address + g_trace.size) <= PS2::EE_RAM_SIZE) memcpy(g_trace.bytes.data() + at, ram + address, g_trace.size);
					g_trace.left--;
				}
				if(!g_steps.empty())
				{
					auto& step = g_steps.front();
					buttons |= step.buttons;
					if(step.stick)
					{
						axes[0] = step.x;
						axes[1] = step.y;
						axesSet |= 1;
					}
					if(--step.frames == 0) g_steps.pop_front();
				}
			}
			// "One-step online" is pressing its way to the lobby: for these frames the game
			// sees its buttons and nothing else, and both sticks at rest (as Rta.cpp).
			RtaWebNet::OnVBlank(ram, PS2::EE_RAM_SIZE, g_isGame, buttons);
			if(RtaWebNet::Driving())
			{
				buttons = RtaWebNet::Buttons();
				axesSet = 0;
			}
			for(auto* listener : m_interfaces)
			{
				for(unsigned int i = 0; i < PS2::CControllerInfo::MAX_BUTTONS; i++)
				{
					auto button = static_cast<PS2::CControllerInfo::BUTTON>(i);
					if(PS2::CControllerInfo::IsAxis(button))
					{
						bool set = (axesSet & (i < 2 ? 1 : 2)) != 0;
						listener->SetAxisState(0, button, set ? static_cast<uint8>(std::min<uint32>(axes[i], 255)) : 0x80, ram);
					}
					else
					{
						listener->SetButtonState(0, button, (buttons & (1u << i)) != 0, ram);
					}
				}
			}
		}
	};

	// ---- patches -----------------------------------------------------------------------
	// As PCSX2 does with its every-frame patches: a word that is not what the patch says
	// is written again. Translated code is thrown away first - in a browser nothing notices
	// by itself that code was overwritten (no write protection of memory pages).
	void CheckPatches(uint8* ram)
	{
		if(!g_isGame) return;
		std::lock_guard lock(g_mutex);
		unsigned int rewritten = 0;
		for(const auto& word : g_activePatches)
		{
			uint32 now;
			memcpy(&now, ram + word.address, 4);
			if(now == word.value) continue;
			g_vm->m_ee->m_EE.m_executor->ClearActiveBlocksInRange(word.address, word.address + 4, false);
			memcpy(ram + word.address, &word.value, 4);
			rewritten++;
		}
		if(rewritten) g_patchRewrites += rewritten;
	}

	// The machine is stopped here: its own thread is booting it or is inside the "load
	// another program" call. Nothing has been translated yet, so the words can be written.
	void GameExecutableChanged()
	{
		auto os = g_vm->m_ee->m_os;
		std::string name = os->GetExecutableName();
		bool isGame = false;
		uint32 crc = 0;
		if(name.compare(0, strlen(GAME_EXECUTABLE), GAME_EXECUTABLE) == 0)
		{
			if(auto elf = os->GetELF())
			{
				const auto& header = elf->GetHeader();
				uint64 size = static_cast<uint64>(header.nSectHeaderStart) + static_cast<uint64>(header.nSectHeaderCount) * header.nSectHeaderEntrySize;
				for(unsigned int i = 0; i < header.nProgHeaderCount; i++)
				{
					if(auto program = elf->GetProgram(i)) size = std::max<uint64>(size, static_cast<uint64>(program->nOffset) + program->nFileSize);
				}
				const uint8* content = elf->GetContent();
				for(uint64 i = 0; i + 4 <= size; i += 4)
				{
					uint32 word;
					memcpy(&word, content + i, 4);
					crc ^= word;
				}
			}
			isGame = (crc == GAME_CRC);
		}
		std::lock_guard lock(g_mutex);
		g_executable = name;
		g_crc = crc;
		g_activePatches.clear();
		g_displayPatchCount = 0;
		if(isGame)
		{
			uint8* ram = g_vm->m_ee->m_ram;
			g_activePatches = g_patches;
			if(g_wantDisplayPatches)
			{
				for(const auto& patch : g_displayPatches)
				{
					uint32 now = 0;
					memcpy(&now, ram + patch.address, 4);
					if(now != patch.original) continue;
					PatchWord word;
					word.address = patch.address;
					word.value = patch.value;
					g_activePatches.push_back(word);
					g_displayPatchCount++;
				}
			}
			for(const auto& word : g_activePatches) memcpy(ram + word.address, &word.value, 4);
		}
		g_isGame = isGame;
		RtaWebNet::OnExecutable(isGame);
		printf("RTA: executable %s, checksum %08X%s, %zu patch words written (%u of them display patches)\n",
		       name.c_str(), crc, isGame ? " (the game, version checked)" : " (NOT the version the patches are for: none applied)",
		       g_activePatches.size(), static_cast<unsigned int>(g_displayPatchCount));
	}

	// ---- the machine -------------------------------------------------------------------
	class CPs2VmWeb : public CPs2VmJs
	{
	public:
		// on the machine's thread
		void CreateVM() override
		{
			CPs2VmJs::CreateVM();
			RtaWebNet::Attach(this);
			m_executableChange = m_ee->m_os->OnExecutableChange.Connect([]() { GameExecutableChanged(); });
		}

	private:
		Framework::CSignal<void()>::Connection m_executableChange;
	};

	// The wait that holds the machine to its frame rate (CFrameLimiter's own way: a
	// deadline per frame, late frames are caught up), with the time spent in it counted:
	// what is left of a frame is what the machine's thread needed. With the limiter off
	// the machine runs as fast as it can, which shows how much is in reserve.
	bool FrameWait(uint32 frameRate)
	{
		typedef std::chrono::steady_clock Clock;
		static bool hasDeadline = false;
		static Clock::time_point deadline;
		if(!g_shared.limiter || frameRate == 0)
		{
			hasDeadline = false;
			return true;
		}
		auto duration = std::chrono::nanoseconds(1000000000ULL / frameRate);
		auto start = Clock::now();
		auto now = start;
		if(!hasDeadline)
		{
			deadline = now;
			hasDeadline = true;
		}
		deadline += duration;
		if(now > (deadline + (3 * duration)))
		{
			deadline = now;
			return true;
		}
		while(now < deadline)
		{
			auto left = deadline - now;
			if(left > std::chrono::microseconds(1500))
				std::this_thread::sleep_for(left - std::chrono::microseconds(1000));
			else if(left > std::chrono::microseconds(200))
				std::this_thread::sleep_for(std::chrono::microseconds(100));
			else
				std::this_thread::yield();
			now = Clock::now();
		}
		g_waitMicros += std::chrono::duration_cast<std::chrono::microseconds>(now - start).count();
		return true;
	}

#ifdef PROFILE
	// A build with -DPROFILE=ON (Play!'s own zones: EE, VU, VIF, GIF, IOP, SPU, GSSYNC,
	// OTHER): the machine thread's time by zone, summed over frames.
	std::mutex g_zoneMutex;
	std::vector<std::pair<std::string, uint64>> g_zones;
	void CollectZones()
	{
		auto stats = CProfiler::GetInstance().GetStats();
		std::lock_guard lock(g_zoneMutex);
		if(g_zones.size() != stats.size())
		{
			g_zones.clear();
			for(const auto& zone : stats) g_zones.push_back(std::make_pair(zone.name, 0));
		}
		for(size_t i = 0; i < stats.size(); i++) g_zones[i].second += stats[i].totalTime;
	}
#endif

	void InitThread(bool sound)
	{
		g_vm = new CPs2VmWeb();
		g_vm->Initialize();
		RtaWebNet::PrepareCard();
		if(g_glMode == GL_MODE_OWN_CANVAS) CGSHandler::g_webCanvas = "#outputCanvas";
		g_vm->CreateGSHandler([]() { return new CGSH_OpenGLWeb(); });
		{
			CGSHandler::PRESENTATION_PARAMS presentationParams;
			presentationParams.mode = CGSHandler::PRESENTATION_MODE_FIT;
			presentationParams.windowWidth = g_canvasWidth;
			presentationParams.windowHeight = g_canvasHeight;
			g_vm->m_ee->m_gs->SetPresentationParams(presentationParams);
		}
		g_vm->CreatePadHandler([]() { return new CPadHandlerWeb(); });
		if(sound) g_vm->CreateSoundHandler([]() { return new CSoundHandlerWeb(); });
		static CGSHandler::NewFrameEvent::Connection newFrame;
		newFrame = g_vm->GetGSHandler()->OnNewFrame.Connect([](uint32 drawCalls) { g_drawCalls = drawCalls; });
#ifdef PROFILE
		static CPS2VM::NewFrameEvent::Connection machineFrame;
		machineFrame = g_vm->OnNewFrame.Connect([]() { CollectZones(); });
#endif
		g_ready = 1;
	}
}

// ---- where the video thread's time goes (a developer's aid) -----------------------------
// Every method of the WebGL context is wrapped on the video thread: calls and the time
// spent in them are counted by name. What a call costs here is the browser's checking and
// packing of it; the drawing itself happens in the browser's GPU process.
// clang-format off
EM_JS_DEPS(RtaWebGlProfile, "$stringToNewUTF8");
EM_JS(void, RtaWebGlProfileStart, (), {
	if(Module.rtaGl) {
		for(const name in Module.rtaGl.stats) { Module.rtaGl.stats[name].n = 0; Module.rtaGl.stats[name].t = 0; }
		Module.rtaGl.since = performance.now();
		return;
	}
	const stats = {};
	const prototype = Object.getPrototypeOf(GLctx);
	for(const name of Object.getOwnPropertyNames(prototype)) {
		const descriptor = Object.getOwnPropertyDescriptor(prototype, name);
		if(!descriptor || typeof descriptor.value !== "function") continue;
		const original = descriptor.value;
		const stat = stats[name] = { n: 0, t: 0 };
		GLctx[name] = function() {
			const start = performance.now();
			const result = original.apply(this, arguments);
			stat.t += performance.now() - start;
			stat.n++;
			return result;
		};
	}
	Module.rtaGl = { stats, since: performance.now() };
});
// The calls that make up nearly all of a frame do nothing from here on: what is left of
// the video thread's time is the emulator's own work. The picture is lost; reload after.
EM_JS(void, RtaWebGlProfileNull, (), {
	for(const name of ["texParameteri", "bufferData", "bufferSubData", "bindBuffer", "bindTexture", "bindBufferBase", "bindBufferRange", "enable", "disable", "activeTexture",
		"useProgram", "bindVertexArray", "drawArrays", "viewport", "blendFuncSeparate", "colorMask", "scissor", "depthMask",
		"blendEquationSeparate", "depthFunc", "blendColor", "texSubImage2D", "texImage2D", "bindFramebuffer", "uniform2f", "uniform1i", "clear"]) {
		GLctx[name] = function() {};
	}
});
EM_JS(char*, RtaWebGlProfileGet, (), {
	if(!Module.rtaGl) return 0;
	const result = { ms: performance.now() - Module.rtaGl.since, calls: {} };
	for(const name in Module.rtaGl.stats) {
		const stat = Module.rtaGl.stats[name];
		if(stat.n) result.calls[name] = [stat.n, Math.round(stat.t * 1000) / 1000];
	}
	return stringToNewUTF8(JSON.stringify(result));
});
// clang-format on

int main(int, const char**)
{
	printf("Play! %s for Champions: Return to Arms (play-web)\n", PLAY_VERSION);
	return 0;
}

extern "C"
{
	// The canvas has the size given (set by the page before this is called).
	// glMode: 0 the GL context on the page's main thread, 1 the video thread owns the canvas.
	EMSCRIPTEN_KEEPALIVE void rtaInit(int canvasWidth, int canvasHeight, int resolutionFactor, int glMode, int sound, int soundBlocks)
	{
		g_canvasWidth = canvasWidth;
		g_canvasHeight = canvasHeight;
		g_glMode = glMode;

		auto& config = CAppConfig::GetInstance();
		CGSH_OpenGL::RegisterPreferences();
		config.SetPreferenceInteger(PREF_CGSH_OPENGL_RESOLUTION_FACTOR, std::max(1, resolutionFactor));
		// With the game drawing both fields at the same height (the display patch) the
		// pictures are shown at the same place.
		config.RegisterPreferenceBoolean(PREF_CGSHANDLER_FIELD_OFFSET, true);
		config.SetPreferenceBoolean(PREF_CGSHANDLER_FIELD_OFFSET, !g_wantDisplayPatches);
		// Sound is handed over in pieces of 16 blocks of 45 samples: 16 ms, about a frame
		// (Play!'s own default is 100 ms; the desktop application uses 30).
		config.RegisterPreferenceInteger(PREF_AUDIO_SPUBLOCKCOUNT, 16);
		config.SetPreferenceInteger(PREF_AUDIO_SPUBLOCKCOUNT, soundBlocks > 0 ? soundBlocks : 16);
		// The frame limiter must be on for FrameWait to be asked at all.
		config.RegisterPreferenceBoolean(PREF_PS2_LIMIT_FRAMERATE, true);
		config.SetPreferenceBoolean(PREF_PS2_LIMIT_FRAMERATE, true);

		CFrameLimiter::SetExternalWait(&FrameWait);

		if(glMode == GL_MODE_MAIN_THREAD)
		{
			EmscriptenWebGLContextAttributes attributes;
			emscripten_webgl_init_context_attributes(&attributes);
			attributes.majorVersion = 2;
			attributes.minorVersion = 0;
			attributes.alpha = false;
			g_mainContext = emscripten_webgl_create_context("#outputCanvas", &attributes);
		}

		// The rest waits for the machine's and the video thread to come up; done on a
		// thread of its own, the page's main thread stays free to start them.
		std::thread([sound]() { InitThread(sound != 0); }).detach();
	}

	EMSCRIPTEN_KEEPALIVE int rtaReady()
	{
		return g_ready;
	}

	// The resolution factor while the game runs: the video handler throws its pictures and
	// textures away and makes them anew at the new size (as the desktop application's
	// settings dialog does).
	EMSCRIPTEN_KEEPALIVE void rtaSetFactor(int factor)
	{
		CAppConfig::GetInstance().SetPreferenceInteger(PREF_CGSH_OPENGL_RESOLUTION_FACTOR, std::max(1, std::min(8, factor)));
		if(g_ready) g_vm->GetGSHandler()->NotifyPreferencesChanged();
	}

	// The patch file's text (PCSX2 style) and the wanted section names, one per line
	// ("*": all). Before the disc is booted. Returns the number of words, -1 on a line
	// that is not an EE word patch.
	EMSCRIPTEN_KEEPALIVE int rtaSetPatches(const char* text, const char* sections, int displayPatches)
	{
		std::set<std::string> wanted;
		bool all = false;
		for(auto line : Split(sections, '\n'))
		{
			line = Trim(line);
			if(line.empty() || line[0] == '#') continue;
			if(line == "*") all = true;
			wanted.insert(line);
		}
		std::vector<PatchWord> words;
		std::string section;
		for(auto line : Split(text, '\n'))
		{
			line = Trim(line);
			if(line.size() >= 2 && line.front() == '[' && line.back() == ']')
			{
				section = line.substr(1, line.size() - 2);
				continue;
			}
			if(line.compare(0, 6, "patch=") != 0) continue;
			if(!all && wanted.count(section) == 0) continue;
			auto fields = Split(line.substr(6), ',');
			std::string type = fields.size() == 5 ? fields[3] : "";
			std::string cpu = fields.size() == 5 ? fields[1] : "";
			for(auto& c : type) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
			for(auto& c : cpu) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
			if(type != "word" || cpu != "ee") return -1;
			PatchWord word;
			word.address = static_cast<uint32>(strtoul(fields[2].c_str(), nullptr, 16)) & 0x1FFFFFFF;
			word.value = static_cast<uint32>(strtoul(fields[4].c_str(), nullptr, 16));
			if(word.address >= PS2::EE_RAM_SIZE - 4 || (word.address & 3)) return -1;
			words.push_back(word);
		}
		// what every player has to have the same: a short figure to compare, made as the
		// desktop application makes it (Rta.cpp, LoadPatches) and told to the other players
		{
			uint32 hash = 2166136261u;
			auto sorted = words;
			std::sort(sorted.begin(), sorted.end(), [](const PatchWord& a, const PatchWord& b) { return a.address < b.address; });
			for(const auto& word : sorted)
			{
				for(uint32 v : {word.address, word.value})
				{
					for(int i = 0; i < 4; i++) hash = (hash ^ ((v >> (i * 8)) & 0xFF)) * 16777619u;
				}
			}
			RtaWebNet::SetPatchSet(hash, static_cast<uint16_t>(std::min<size_t>(words.size(), 0xFFFF)));
		}
		std::lock_guard lock(g_mutex);
		g_patches = words;
		g_wantDisplayPatches = (displayPatches != 0);
		return static_cast<int>(words.size());
	}

	// More patch words from a file of the page's own (every section of it), after
	// rtaSetPatches and before the disc is booted: on a privately served page, what the
	// game needs to get past its sign-in step. They are not part of the patch set's figure
	// (as the desktop application's extra patch files are not). Returns the number of
	// words added, -1 on a line that is not an EE word patch.
	EMSCRIPTEN_KEEPALIVE int rtaAddPatches(const char* text)
	{
		std::vector<PatchWord> words;
		for(auto line : Split(text, '\n'))
		{
			line = Trim(line);
			if(line.compare(0, 6, "patch=") != 0) continue;
			auto fields = Split(line.substr(6), ',');
			std::string type = fields.size() == 5 ? fields[3] : "";
			std::string cpu = fields.size() == 5 ? fields[1] : "";
			for(auto& c : type) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
			for(auto& c : cpu) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
			if(type != "word" || cpu != "ee") return -1;
			PatchWord word;
			word.address = static_cast<uint32>(strtoul(fields[2].c_str(), nullptr, 16)) & 0x1FFFFFFF;
			word.value = static_cast<uint32>(strtoul(fields[4].c_str(), nullptr, 16));
			if(word.address >= PS2::EE_RAM_SIZE - 4 || (word.address & 3)) return -1;
			words.push_back(word);
		}
		std::lock_guard lock(g_mutex);
		g_patches.insert(g_patches.end(), words.begin(), words.end());
		return static_cast<int>(words.size());
	}

	// The disc image has been given to the stream (RtaWebDiscSet); 'name' only tells the
	// kind of image by its ending.
	EMSCRIPTEN_KEEPALIVE void rtaBoot(const char* name)
	{
		if(!g_ready) return;
		g_vm->BootDiscImage(name);
	}

	EMSCRIPTEN_KEEPALIVE void rtaPause(int pause)
	{
		if(!g_ready) return;
		if(pause)
			g_vm->PauseAsync();
		else if(g_vm->GetStatus() == CVirtualMachine::PAUSED)
			g_vm->Resume();
	}

	EMSCRIPTEN_KEEPALIVE uint32* rtaShared()
	{
		return reinterpret_cast<uint32*>(&g_shared);
	}

	EMSCRIPTEN_KEEPALIVE void* rtaSoundRing()
	{
		return &g_soundRing;
	}

	// A scripted press: 'buttons' held for 'hold' frames, then nothing for 'wait' frames.
	EMSCRIPTEN_KEEPALIVE void rtaTap(uint32 buttons, uint32 hold, uint32 wait)
	{
		std::lock_guard lock(g_mutex);
		Step step;
		if(hold)
		{
			step.buttons = buttons;
			step.frames = hold;
			g_steps.push_back(step);
		}
		if(wait)
		{
			step.buttons = 0;
			step.frames = wait;
			g_steps.push_back(step);
		}
	}

	// DEV: the left stick held at (x, y), 0..255, for 'frames' frames, as a scripted step
	EMSCRIPTEN_KEEPALIVE void rtaStick(uint32 x, uint32 y, uint32 frames)
	{
		if(!frames) return;
		std::lock_guard lock(g_mutex);
		Step step;
		step.stick = true;
		step.x = static_cast<uint8>(std::min<uint32>(x, 255));
		step.y = static_cast<uint8>(std::min<uint32>(y, 255));
		step.frames = frames;
		g_steps.push_back(step);
	}

	// DEV: 'size' bytes of the game's memory, taken at every vertical blank for 'frames'
	// frames from now: at 'offset', or at 'offset' past the pointer stored at 'pointer'.
	// With frames 0: what was taken, as hexadecimal text, one frame after the other.
	EMSCRIPTEN_KEEPALIVE const char* rtaTrace(uint32 pointer, uint32 offset, uint32 size, uint32 frames)
	{
		static std::string text;
		std::lock_guard lock(g_mutex);
		text.clear();
		if(frames != 0)
		{
			g_trace.pointer = pointer & 0x1FFFFFFF;
			g_trace.offset = offset;
			g_trace.size = std::min<uint32>(size, 64);
			g_trace.left = std::min<uint32>(frames, 100000);
			g_trace.bytes.clear();
			return text.c_str();
		}
		if(g_trace.left != 0) return text.c_str(); // not finished
		static const char* digits = "0123456789abcdef";
		text.reserve(g_trace.bytes.size() * 2);
		for(uint8 byte : g_trace.bytes)
		{
			text += digits[byte >> 4];
			text += digits[byte & 15];
		}
		return text.c_str();
	}

	EMSCRIPTEN_KEEPALIVE uint32 rtaStepsLeft()
	{
		std::lock_guard lock(g_mutex);
		return static_cast<uint32>(g_steps.size());
	}

	// The game's memory (main memory of the emulated machine), for the page's tests.
	EMSCRIPTEN_KEEPALIVE uint32 rtaPeek(uint32 address, int size)
	{
		if(!g_ready || !g_vm->m_ee) return 0;
		address &= 0x1FFFFFFF;
		if(address >= PS2::EE_RAM_SIZE - 4) return 0;
		const uint8* ram = g_vm->m_ee->m_ram;
		uint32 value = 0;
		memcpy(&value, ram + address, size == 1 ? 1 : (size == 2 ? 2 : 4));
		return value;
	}

	EMSCRIPTEN_KEEPALIVE void rtaPoke(uint32 address, int size, uint32 value)
	{
		if(!g_ready || !g_vm->m_ee) return;
		address &= 0x1FFFFFFF;
		if(address >= PS2::EE_RAM_SIZE - 4) return;
		memcpy(g_vm->m_ee->m_ram + address, &value, size == 1 ? 1 : (size == 2 ? 2 : 4));
	}

	// Counters, as JSON. Rates are for the page to work out from two readings.
	EMSCRIPTEN_KEEPALIVE const char* rtaInfo()
	{
		std::lock_guard lock(g_mutex);
		g_text = Format(
		    "{\"ready\":%d,\"now\":%.3f,\"frames\":%u,\"presents\":%u,\"wait_us\":%llu,\"video_us\":%llu,"
		    "\"functions\":%u,\"function_us\":%llu,\"dispatches\":%u,\"draw_calls\":%u,"
		    "\"disc_fetches\":%u,\"disc_fetch_us\":%u,\"disc_errors\":%u,"
		    "\"is_game\":%d,\"crc\":\"%08X\",\"executable\":\"%s\",\"patch_words\":%zu,\"display_patches\":%u,\"patch_rewrites\":%u,"
		    "\"steps\":%zu,\"gl_mode\":%d,\"gl_made\":%u,\"gl_skipped\":%u,\"sound_written\":%u,\"sound_dropped\":%u,\"burst_left\":%u}",
		    static_cast<int>(g_ready), emscripten_get_now(), static_cast<unsigned int>(g_frames), static_cast<unsigned int>(g_presents),
		    static_cast<unsigned long long>(g_waitMicros), static_cast<unsigned long long>(CGSHandler::g_webBusyMicros),
		    static_cast<unsigned int>(g_rtaWebFunctionCount), static_cast<unsigned long long>(g_rtaWebFunctionMicros), g_rtaWebDispatches, static_cast<unsigned int>(g_drawCalls),
		    RtaWebDiscCounter(0), RtaWebDiscCounter(1), RtaWebDiscCounter(2),
		    g_isGame ? 1 : 0, static_cast<unsigned int>(g_crc), g_executable.c_str(), g_activePatches.size(),
		    static_cast<unsigned int>(g_displayPatchCount), static_cast<unsigned int>(g_patchRewrites),
		    g_steps.size(), g_glMode, RtaGl::g_state.made, RtaGl::g_state.skipped, static_cast<unsigned int>(g_soundWritten), static_cast<unsigned int>(g_soundDropped), g_shared.burst);
		return g_text.c_str();
	}

	// DEV: 1 starts (or starts again) counting the video thread's GL calls; 0 returns
	// the counts as JSON (to be freed by the caller), or null.
	EMSCRIPTEN_KEEPALIVE char* rtaGlProfile(int start)
	{
		if(!g_ready) return nullptr;
		char* result = nullptr;
		g_vm->GetGSHandler()->SendGSCall(
		    [&]() {
			    if(start == 2)
				    RtaWebGlProfileNull();
			    else if(start)
				    RtaWebGlProfileStart();
			    else
				    result = RtaWebGlProfileGet();
		    },
		    true);
		return result;
	}

	// DEV: asks for the next picture handed over (1), or gives the address of its pixels
	// when it has been taken (0; RGBA, the canvas's size, bottom row first), else null.
	EMSCRIPTEN_KEEPALIVE uint8* rtaShot(int ask)
	{
		if(ask)
		{
			g_shotState = 1;
			return nullptr;
		}
		return (g_shotState == 2) ? g_shotPixels.data() : nullptr;
	}

	// DEV: the machine thread's time by zone as JSON (nanoseconds summed since the start);
	// "{}" unless built with -DPROFILE=ON.
	EMSCRIPTEN_KEEPALIVE const char* rtaZones()
	{
		static std::string text;
		text = "{";
#ifdef PROFILE
		std::lock_guard lock(g_zoneMutex);
		for(size_t i = 0; i < g_zones.size(); i++)
		{
			text += Format("%s\"%s\":%llu", i ? "," : "", g_zones[i].first.c_str(), static_cast<unsigned long long>(g_zones[i].second));
		}
#endif
		text += "}";
		return text.c_str();
	}

	// The comparison of consecutive pictures asked for through the shared word 'burst',
	// as JSON; the list is emptied.
	EMSCRIPTEN_KEEPALIVE const char* rtaBurst()
	{
		std::lock_guard lock(g_mutex);
		std::string text = "[";
		for(size_t i = 0; i < g_burst.size(); i++)
		{
			const auto& entry = g_burst[i];
			text += Format("%s{\"differing\":%d,\"max_delta\":%u,\"time\":%.3f,\"sum\":%llu}", i ? "," : "",
			               entry.differing == 0xFFFFFFFF ? -1 : static_cast<int>(entry.differing), entry.maxDelta, entry.time, static_cast<unsigned long long>(entry.sum));
		}
		text += "]";
		g_burst.clear();
		g_text = text;
		return g_text.c_str();
	}
}
