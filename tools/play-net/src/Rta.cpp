// See Rta.h. Everything here that touches the emulated machine runs on the machine's own
// thread: at the start of a vertical blank (from the pad handler, where the application
// reads its input), from the Ethernet chip's poll and transmit hooks, or while the
// machine is stopped for loading an executable.
#include "Rta.h"
#include "RtaNet.h"
#include "RtaOnline.h"

#include <QCommandLineParser>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMessageBox>
#include <QProcess>
#include <QSettings>
#include <QStandardPaths>
#include <QStringList>
#include <QTimer>
#include <QWidget>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <map>
#include <unordered_map>
#include <mutex>
#include <random>
#include <set>
#include <sstream>
#include <thread>

#include <arpa/inet.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <netdb.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif

#include "AppConfig.h"
#include "DiskUtils.h"
#include "FpUtils.h"
#include "FrameLimiter.h"
#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "PathUtils.h"
#include "PreferenceDefs.h"
#include "ee/PS2OS.h"
#include "input/PH_GenericInput.h"
#include "GSH_OpenGLQt.h"
#include "gs/GSH_OpenGL/GSH_OpenGL.h"

#define PREF_RTA_GUEST_ADDRESS "rta.net.guestaddress"
#define PREF_RTA_DEFAULTS "rta.defaults"
#define PREF_RTA_KEYS "rta.keys"
#define RTA_KEYS 2 // 2: W A S D for the left stick, I J K L for the face buttons
#define RTA_DEFAULTS 2
#define RTA_RESOLUTION_FACTOR 4
#define RTA_SPU_BLOCKS 30

namespace
{
	// The executable these patches are for, and the checksum PCSX2 names its patch files
	// by (every 32-bit word of the file exclusive-ored together).
	const char* GAME_EXECUTABLE = "SLUS_209.73";
	const uint32 GAME_CRC = 0x4028A55F;

	// What is read from the game to know that it is on its "Network Configuration and
	// Selection" screen (names.tsv, symbols/netlib.tsv; RtaOnline.cpp has the rest):
	// g_inFrontend, g_levelName, g_frontendState (10: the lobby screens), g_lobbyState
	// (2: the network screen, 13: leaving), the network window and in it its state (0
	// reading the card, 3 the list of settings, 8 an error), the count of settings found.
	const uint32 A_IN_FRONTEND = 0x41B510, A_LEVEL_NAME = 0x41B721, A_FE_STATE = 0x4F6B78, A_LOBBY_STATE = 0x506160;
	const uint32 A_WIN_NET = 0x506148, NET_STATE = 0xDB4, NET_SETTINGS = 0x4354, NET_BOX = 0xD88;
	// frames (vertical blanks) without the machine drawing anything before the game is
	// taken to be stuck; and the same where it is known to get stuck
	const uint64 STUCK_FRAMES = 600, STUCK_FRAMES_KNOWN = 180;
	// milliseconds the machine's own thread may take to come round before it is taken to
	// have stopped (it comes round every 17)
	const int MACHINE_ANSWER_MS = 2500;

	struct Options
	{
		std::string dataDir;
		bool net = true;
		std::string server;       // host name or address; empty: this computer
		std::string serverPublic; // the server's public address, when on the server's own network
		std::string guest;        // the emulated machine's address
		std::string loopback = "auto";
		std::string lobbyName = "con.soegames.net";
		bool bindGamePorts = true;
		std::string patchFile;
		std::string patchSections; // "name;name", "@file", "*" or empty
		std::vector<std::string> extraPatches;
		bool steadyPicture = true;
		bool displayClock = true;
		bool textureDump = false;
		int textureMemory = 0; // megabytes of video memory for replacement pictures (0: the default)
		bool textureWhole = false; // the whole of every replacement picture goes to the GPU, not only the part drawn with
		std::string textureDir; // dump/ and replace/ below it; empty: <data>/textures
		bool netcnf = true;
		std::string controlPath;
		std::string pcapPath;
		std::string testLabel; // --rta-test: a test run, and what the window's title says about it
		bool testBackground = false; // --rta-test (not --rta-title): small, behind, never active
		bool soundWav = false;   // write the mixed sound to <data>/sound-<time>.wav
		bool soundPlain = false; // queue sound as Play! itself does (for comparing)
		int soundBlock = 0;      // milliseconds of sound handed over at a time, for this data directory (0: as set)
		std::string online;      // --rta-online: "lobby", "host" or "join:CODE"; empty: not given
		bool noOnline = false;   // --rta-no-online: not at this start, whatever the setting says
		std::vector<std::string> onlineNames; // --rta-online-name: player names for a test, instead of asking
		int gatewayPort = 0;     // --rta-gateway-port: where this host looks for the server's gateway (tests)
		bool setQuiet = false;   // --rta-set-quiet: do not tell the other players which patch set this copy has (tests: an older copy)
		bool setRaw = false;     // --rta-set-raw: pass other players' patch-set datagrams on to the game as well (tests: an older copy)
		std::string arith = "auto"; // --rta-arith auto|browser|native: the machine's arithmetic (CheckArithmetic)
		bool netcnfProgram = false; // --rta-netcnf-program: the game's "Config" may start Sony's network settings program
	};

	// The packaged application (see Rta.h, LaunchInfo)
	const char* SIGNIN_PATCH_NAME = "SLUS-20973_4028A55F_signin.pnach";
	const char* BUNDLED_PATCH_NAME = "SLUS-20973_4028A55F.pnach";
	const char* BUNDLED_SECTIONS_NAME = "sections.txt";
	const char* BUNDLED_DEFAULTS_NAME = "defaults.ini";
	struct Launch
	{
		bool packaged = false;
		std::string resources; // <bundle>/Contents/Resources/rta
		std::string root;
		int player = 1;
		std::string signinPatch;
		std::string signinPlaces;
		std::string serverFrom; // where the server's address was taken from, in words
	};
	Launch g_launch;

	std::string LaunchFile()
	{
		return g_launch.root + "/launch.ini";
	}

	// A setting of the packaged application: its own (launch.ini) when it has one, even
	// an empty one; else the default the bundle was made with (defaults.ini beside our
	// patch file, written by package.sh); else none.
	QVariant LaunchValue(const char* key, bool* bundled = nullptr)
	{
		if(bundled) *bundled = false;
		QSettings launch(QString::fromStdString(LaunchFile()), QSettings::IniFormat);
		if(launch.contains(key)) return launch.value(key);
		QSettings defaults(QString::fromStdString(g_launch.resources + "/" + BUNDLED_DEFAULTS_NAME), QSettings::IniFormat);
		if(!defaults.contains(key)) return QVariant();
		if(bundled) *bundled = true;
		return defaults.value(key);
	}

	// The key a saved login is kept under: the server's address as the player gave it.
	std::string ServerKey(std::string server)
	{
		std::string key;
		for(char c : server)
		{
			if(c != ' ' && c != '\t' && c != '\r' && c != '\n') key += static_cast<char>(tolower(static_cast<unsigned char>(c)));
		}
		if(key.empty() || key == "localhost" || key.compare(0, 4, "127.") == 0) key = "this-computer";
		return key;
	}

	struct PatchWord
	{
		uint32 address = 0;
		uint32 value = 0;
	};

	// Changes to how the game draws, made by the application itself and only when the
	// word found is the one expected. They touch the picture and nothing else, so they
	// are not part of the patch set that every player has to share and do not count in
	// its figure.
	struct DisplayPatch
	{
		uint32 address;
		uint32 original;
		uint32 value;
		const char* what;
	};
	const DisplayPatch g_displayPatches[] = {
	    // gfx_emitFrameSetup (0x19c86c) sets the vertical drawing offset (XYOFFSET) for the
	    // next frame to 1824.0 or 1824.5 by the television field: every other picture is
	    // drawn half a line lower, which a television's interlace turns into finer detail
	    // and a window that shows whole pictures turns into a picture that jumps up and
	    // down. The constant for the odd field is made the same as the even one.
	    {0x0019C904, 0x240A7208, 0x240A7200, "the picture is drawn at the same height on both television fields"},
	    // gfx_displayField (0x19d9e4) tells the interface drawers (sprites, text) which
	    // field is on the screen. Interface pictures are stored as two half-height
	    // pictures, one for each field, and the drawers take the one for the field and
	    // put it a line higher or lower. Shown as whole pictures one after the other, the
	    // two halves make everything flat on the screen (menus, text, the bars) tremble.
	    // The function is made to say "first field" always (its load of the field word
	    // becomes "move v0, zero"): the interface is then drawn from one half only - what
	    // each field showed anyway - and stands still.
	    {0x0019D9EC, 0x8C420008, 0x00001021, "the interface is drawn the same on both television fields"},
	    // Interface art at its full height. The game has a second way of drawing it, which
	    // it uses when it runs at half rate (one whole 448-line frame instead of a picture
	    // per field): both half pictures are drawn over the same place, one to the even
	    // lines and one to the odd ones, with the GS scanline mask. The four drawers that
	    // have this second way (sprites 0x17ab50 and 0x17b8b0, text 0x1809c0 and 0x180f80)
	    // choose by the word at 0x44fdb4; here each is made to read "1" instead of loading
	    // it ("lw v1, -0x24c(v0)" becomes "addiu v1, zero, 1"). Nothing else that reads the
	    // word is touched: the game itself stays at full rate. Needs the scanline mask in
	    // the renderer, which play-net.patch adds.
	    {0x0017AB58, 0x8C43FDB4, 0x24030001, "interface sprites are drawn from both field pictures"},
	    {0x0017BAE4, 0x8C43FDB4, 0x24030001, "interface sprites (second drawer) are drawn from both field pictures"},
	    {0x00180D2C, 0x8C43FDB4, 0x24030001, "text is drawn from both field pictures"},
	    {0x00180FEC, 0x8C43FDB4, 0x24030001, "text is drawn in two passes, one per field picture"},
	};

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

	std::string Format(const char* format, ...)
	{
		char text[1024];
		va_list args;
		va_start(args, format);
		vsnprintf(text, sizeof(text), format, args);
		va_end(args);
		return text;
	}

	// PCSX2-style patch file: [section] headers and  patch=1,EE,<addr>,word,<value>  lines.
	// Returns the words of the wanted sections ("*": all) and the names that were found.
	bool ReadPatchFile(const std::string& path, const std::set<std::string>& wanted, bool all, std::vector<PatchWord>& words, std::set<std::string>& found, std::string& error)
	{
		std::ifstream file(path);
		if(!file)
		{
			error = "cannot read " + path;
			return false;
		}
		std::string line, section;
		while(std::getline(file, line))
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
			if(type != "word" || cpu != "ee")
			{
				error = path + ": only EE word patches are supported: " + line;
				return false;
			}
			PatchWord word;
			word.address = static_cast<uint32>(strtoul(fields[2].c_str(), nullptr, 16)) & 0x1FFFFFFF;
			word.value = static_cast<uint32>(strtoul(fields[4].c_str(), nullptr, 16));
			if(word.address >= PS2::EE_RAM_SIZE - 4 || (word.address & 3))
			{
				error = path + ": address outside main memory: " + line;
				return false;
			}
			words.push_back(word);
			found.insert(section);
		}
		return true;
	}

	// ---- the network setting on the memory card ---------------------------------------
	// The game will not go online without a network setting saved on a memory card, and
	// offers to restart into Sony's set-up program to make one. What that program saves
	// for "Ethernet adaptor, automatic address, automatic DNS" is four small files, and
	// they are written here directly instead. Two of them are text scrambled by Sony's
	// module with a key taken from the console's identification number; Play! gives every
	// emulated console the same number, so the key is a constant here: each 16-bit word
	// is rotated left by 6, 3, 3, 6, 3, 3, ... bits and inverted (an odd last byte the
	// same way in 8 bits). The files this writes are byte for byte what the set-up
	// program saved on Play! (docs/issues/live-rig.md section 13.2), without its icon.
	std::vector<uint8> NetcnfScramble(const std::string& text)
	{
		static const unsigned int key[3] = {6, 3, 3};
		std::vector<uint8> out;
		size_t index = 0;
		for(size_t i = 0; i + 1 < text.size(); i += 2, index++)
		{
			unsigned int word = static_cast<uint8>(text[i]) | (static_cast<uint8>(text[i + 1]) << 8);
			unsigned int shift = key[index % 3];
			word = ((word << shift) | (word >> (16 - shift))) & 0xFFFF;
			word ^= 0xFFFF;
			out.push_back(static_cast<uint8>(word));
			out.push_back(static_cast<uint8>(word >> 8));
		}
		if(text.size() & 1)
		{
			unsigned int byte = static_cast<uint8>(text.back());
			unsigned int shift = key[index % 3];
			byte = ((byte << shift) | (byte >> (8 - shift))) & 0xFF;
			out.push_back(static_cast<uint8>(byte ^ 0xFF));
		}
		return out;
	}

	bool WriteFile(const fs::path& path, const void* data, size_t size)
	{
		FILE* file = fopen(path.string().c_str(), "wb");
		if(!file) return false;
		bool ok = fwrite(data, 1, size, file) == size;
		fclose(file);
		return ok;
	}

	// 0: there already; 1: written; -1: could not
	int WriteNetcnf(const fs::path& cardDirectory)
	{
		auto directory = cardDirectory / "BWNETCNF";
		std::error_code error;
		if(fs::exists(directory / "BWNETCNF", error)) return 0;
		fs::create_directories(directory, error);
		const std::string header = "# <Sony Computer Entertainment Inc.>\n\n";
		const std::string index =
		    "0,1,net000.cnf,Combination1\n"
		    "1,1,ifc000.dat,Setting 1\n"
		    "2,1,dev000.dat,SCE/Ethernet (Network Adaptor)\n";
		const std::string combination = header + "interface \"ifc000.dat + dev000.dat\" \"ifc000.dat\" \"dev000.dat\"\n";
		auto interface = NetcnfScramble(header + "type nic\ndhcp\n");
		auto device = NetcnfScramble(header + "type nic\nvendor \"SCE\"\nproduct \"Ethernet (Network Adaptor)\"\nphy_config auto\n");
		bool ok = WriteFile(directory / "net000.cnf", combination.data(), combination.size());
		ok = ok && WriteFile(directory / "ifc000.dat", interface.data(), interface.size());
		ok = ok && WriteFile(directory / "dev000.dat", device.data(), device.size());
		// the index last: it is what says a setting exists
		ok = ok && WriteFile(directory / "BWNETCNF", index.data(), index.size());
		return ok ? 1 : -1;
	}

	// ---- addresses of this computer -----------------------------------------------------

	// the address this computer uses toward the outside (no packet is sent)
	uint32 PrimaryAddress()
	{
		int fd = socket(AF_INET, SOCK_DGRAM, 0);
		if(fd < 0) return 0;
		sockaddr_in to = {};
		to.sin_family = AF_INET;
		to.sin_addr.s_addr = htonl(0x08080808);
		to.sin_port = htons(53);
		uint32 result = 0;
		if(connect(fd, reinterpret_cast<sockaddr*>(&to), sizeof(to)) == 0)
		{
			sockaddr_in local = {};
			socklen_t length = sizeof(local);
			if(getsockname(fd, reinterpret_cast<sockaddr*>(&local), &length) == 0) result = ntohl(local.sin_addr.s_addr);
		}
		close(fd);
		if(result == 0 || Rta::CNet::IsLoopback(result))
		{
			// no route to the outside: any address of a running interface will do
			result = 0;
			ifaddrs* list = nullptr;
			if(getifaddrs(&list) == 0)
			{
				for(auto* entry = list; entry; entry = entry->ifa_next)
				{
					if(!entry->ifa_addr || entry->ifa_addr->sa_family != AF_INET) continue;
					uint32 address = ntohl(reinterpret_cast<sockaddr_in*>(entry->ifa_addr)->sin_addr.s_addr);
					if(Rta::CNet::IsLoopback(address) || (address >> 16) == 0xA9FE) continue;
					result = address;
					break;
				}
				freeifaddrs(list);
			}
		}
		return result;
	}

	bool IsOwnAddress(uint32 address)
	{
		if(Rta::CNet::IsLoopback(address)) return true;
		bool own = false;
		ifaddrs* list = nullptr;
		if(getifaddrs(&list) == 0)
		{
			for(auto* entry = list; entry; entry = entry->ifa_next)
			{
				if(!entry->ifa_addr || entry->ifa_addr->sa_family != AF_INET) continue;
				if(ntohl(reinterpret_cast<sockaddr_in*>(entry->ifa_addr)->sin_addr.s_addr) == address) own = true;
			}
			freeifaddrs(list);
		}
		return own;
	}

	bool ResolveHost(const std::string& name, uint32& address)
	{
		if(Rta::CNet::ParseIp(name, address)) return true;
		addrinfo hints = {};
		hints.ai_family = AF_INET;
		hints.ai_socktype = SOCK_STREAM;
		addrinfo* list = nullptr;
		if(getaddrinfo(name.c_str(), nullptr, &hints, &list) != 0 || !list) return false;
		address = ntohl(reinterpret_cast<sockaddr_in*>(list->ai_addr)->sin_addr.s_addr);
		freeaddrinfo(list);
		return true;
	}

	// ---- the two threads that make the picture ------------------------------------------

	// The machine's thread needs almost a whole processor core for this game in a level,
	// and the video thread must keep up with it. Without this, macOS treats them like
	// any background work: on a busy computer they are put on the slow cores or made to
	// wait, and the game runs slow, with late pictures and broken sound.
	void RaiseThreadPriority()
	{
#ifdef __APPLE__
		pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
	}

	uint64 ThreadCpuMicroseconds()
	{
		timespec t = {};
		clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
		return static_cast<uint64>(t.tv_sec) * 1000000 + t.tv_nsec / 1000;
	}

	uint64 ClockMicroseconds()
	{
		return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
	}

	// ---- buttons, for the control socket ------------------------------------------------

	using Button = PS2::CControllerInfo::BUTTON;

	bool ParseButtons(const std::string& text, uint32& mask)
	{
		static const std::pair<const char*, Button> names[] = {
		    {"up", Button::DPAD_UP}, {"down", Button::DPAD_DOWN}, {"left", Button::DPAD_LEFT}, {"right", Button::DPAD_RIGHT},
		    {"select", Button::SELECT}, {"start", Button::START}, {"square", Button::SQUARE}, {"triangle", Button::TRIANGLE},
		    {"circle", Button::CIRCLE}, {"cross", Button::CROSS}, {"l1", Button::L1}, {"l2", Button::L2}, {"l3", Button::L3},
		    {"r1", Button::R1}, {"r2", Button::R2}, {"r3", Button::R3}};
		mask = 0;
		for(const auto& part : Split(text, '+'))
		{
			bool known = false;
			for(const auto& name : names)
			{
				if(part == name.first)
				{
					mask |= 1u << name.second;
					known = true;
				}
			}
			if(!known) return false;
		}
		return true;
	}

	// ---- the state ----------------------------------------------------------------------

	class CPadHandlerRta;

	class CState
	{
	public:
		Options options;

		void Log(const std::string& line)
		{
			std::lock_guard<std::mutex> lock(m_logMutex);
			auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
			char stamp[32];
			strftime(stamp, sizeof(stamp), "%H:%M:%S", localtime(&now));
			fprintf(stderr, "[rta %s] %s\n", stamp, line.c_str());
			if(m_logFile)
			{
				fprintf(m_logFile, "%s frame %llu  %s\n", stamp, static_cast<unsigned long long>(m_frame.load()), line.c_str());
				fflush(m_logFile);
			}
		}

		void Attach(CPS2VM* vm)
		{
			m_vm = vm;
			auto base = CAppConfig::GetInstance().GetBasePath();
			m_logFile = fopen((base / "rta.log").string().c_str(), "a");
			Log("---- start; data directory " + base.string());

			if(!options.dataDir.empty())
			{
				// Play! keeps these as absolute paths in its settings file, so a copied
				// data directory would go on using the memory cards of the original.
				auto& config = CAppConfig::GetInstance();
				const std::pair<const char*, const char*> directories[] = {
				    {PREF_PS2_MC0_DIRECTORY, "mc0"}, {PREF_PS2_MC1_DIRECTORY, "mc1"}, {PREF_PS2_HOST_DIRECTORY, "host"}, {PREF_PS2_ROM0_DIRECTORY, "rom0"}};
				for(const auto& directory : directories)
				{
					auto path = base / "vfs" / directory.second;
					Framework::PathUtils::EnsurePathExists(path);
					config.SetPreferencePath(directory.first, path);
				}
			}

			if(options.netcnf)
			{
				auto card = CAppConfig::GetInstance().GetPreferencePath(PREF_PS2_MC0_DIRECTORY);
				int result = WriteNetcnf(card);
				if(result > 0) Log("network setting written to the memory card in slot 1 (" + card.string() + ")");
				if(result < 0) Log("COULD NOT write the network setting to " + card.string());
			}

			LoadPatches();
			if(g_launch.packaged)
			{
				Log(Format("packaged application: player %d, data in %s", g_launch.player, g_launch.root.c_str()));
				Log("lobby server: " + (options.server.empty() ? std::string("this computer") : options.server) + " (" + g_launch.serverFrom + "); going online at start: " + (Rta::OnlineAtStart() ? "on" : "off"));
				if(!g_launch.signinPatch.empty() && g_launch.signinPatch.compare(0, g_launch.resources.size(), g_launch.resources) == 0) Log("sign-in patch: the one inside the application");
				if(g_launch.signinPatch.empty())
				{
					std::string places = g_launch.signinPlaces;
					std::replace(places.begin(), places.end(), '\n', ' ');
					Log(std::string("NO SIGN-IN PATCH (") + SIGNIN_PATCH_NAME + "): the game will stop with a network error after 'Internet Game'. Looked in: " + places);
				}
			}
			if(options.net) StartNet();
			StartOnline(base);

			m_executableChange = m_vm->m_ee->m_os->OnExecutableChange.Connect([this]() { OnExecutableChange(); });
			StartTextures(base);
			if(!options.controlPath.empty()) StartControl();
			Rta::StartGamePads();
			Rta::KeepAwake();
			if(options.displayClock)
			{
				Rta::StartDisplayClock();
				CFrameLimiter::SetExternalWait([](uint32 framesPerSecond) { return Rta::WaitForFrameStart(framesPerSecond); });
				CGSHandler::g_presentClock.stamp = []() { return Rta::PresentMark(); };
				CGSHandler::g_presentClock.wait = [](uint64 mark) { Rta::WaitForPresentMark(mark); };
			}
		}

		void Detach()
		{
			m_executableChange.reset();
			CGSH_OpenGL::g_textureDump = CGSH_OpenGL::TextureDumpFunction();
			CGSH_OpenGL::g_textureLoad = CGSH_OpenGL::TextureLoadFunction();
			CGSH_OpenGL::g_textureForget = CGSH_OpenGL::TextureForgetFunction();
			CGSH_OpenGL::g_textureOrder = CGSH_OpenGL::TextureOrderFunction();
			StopTextureThreads();
			CFrameLimiter::SetExternalWait(CFrameLimiter::ExternalWaitFunction());
			CGSHandler::g_presentClock = CGSHandler::PresentClock();
			if(m_vm && m_net)
			{
				auto& speed = m_vm->m_iop->m_speed;
				speed.SetEthernetFrameTxHandler(Iop::CSpeed::EthernetFrameTxHandler());
				speed.SetEthernetPollHandler(Iop::CSpeed::EthernetPollHandler(), 0);
			}
			m_net.reset();
			if(m_listenFd >= 0)
			{
				close(m_listenFd);
				unlink(options.controlPath.c_str());
			}
			if(m_clientFd >= 0) close(m_clientFd);
			m_listenFd = m_clientFd = -1;
			m_vm = nullptr;
		}

		std::string StatusText()
		{
			std::lock_guard<std::mutex> lock(m_logMutex);
			return m_status;
		}

		// ---- one-step online (RtaOnline.h) ----------------------------------------------
		Rta::COnline online;

		// "", "lobby", "host", "host:CODE" or "join:CODE"
		// "+choose" after host or join: the player chooses the character, although the one
		// used last is known
		static bool ParseOnlineMode(const std::string& given, Rta::COnline::Goal& goal, std::string& code, bool& choose, std::string& error)
		{
			goal = Rta::COnline::Goal::Lobby;
			code.clear();
			choose = false;
			std::string mode = given;
			if(mode.size() > 7 && mode.compare(mode.size() - 7, 7, "+choose") == 0)
			{
				choose = true;
				mode.erase(mode.size() - 7);
			}
			if(mode.empty() || mode == "lobby") return true;
			std::string word = mode.substr(0, mode.find(':'));
			std::string rest = (mode.find(':') == std::string::npos) ? "" : mode.substr(mode.find(':') + 1);
			for(auto& c : rest) c = static_cast<char>(toupper(static_cast<unsigned char>(c)));
			if(word == "host")
			{
				goal = Rta::COnline::Goal::Host;
				code = rest.empty() ? Rta::COnline::MakeCode() : rest;
			}
			else if(word == "join")
			{
				goal = Rta::COnline::Goal::Join;
				code = rest;
			}
			else
			{
				error = "'" + given + "' is not lobby, host or join:CODE (host and join may end in +choose)";
				return false;
			}
			error = Rta::COnline::CheckCode(code);
			return error.empty();
		}

		bool StartOnlineMode(const std::string& mode, bool powerOn, std::string& error)
		{
			Rta::COnline::Goal goal;
			std::string code;
			bool choose = false;
			if(!ParseOnlineMode(mode, goal, code, choose, error)) return false;
			if(!m_net)
			{
				error = "the built-in network is switched off (--rta-no-net)";
				return false;
			}
			online.Start(goal, code, powerOn, choose);
			if(goal == Rta::COnline::Goal::Host)
			{
				Log("online: hosting a game with the code " + code);
				if(!options.testBackground) QMetaObject::invokeMethod(QCoreApplication::instance(), [code]() { Rta::ShowGameCode(code); }, Qt::QueuedConnection);
			}
			if(goal == Rta::COnline::Goal::Join) Log("online: joining the game with the code " + code);
			return true;
		}

		void StartOnline(const fs::path& base)
		{
			Rta::COnline::Setup setup;
			setup.file = (base / "online-login").string();
			setup.characterFile = (base / "online-character").string();
			setup.server = ServerKey(options.server);
			setup.serverText = m_serverText.empty() ? "(none)" : m_serverText;
			setup.personPresent = !options.testBackground;
			setup.log = [this](const std::string& line) { Log(line); };
			setup.askName = [this](const std::string& why) {
				if(options.testBackground)
				{
					Log("online: a test run - the name comes from --rta-online-name or from 'online name NAME' on the control socket");
					return;
				}
				QMetaObject::invokeMethod(QCoreApplication::instance(), [why]() { Rta::AskPlayerName(why); }, Qt::QueuedConnection);
			};
			setup.cross = 1u << Button::CROSS;
			setup.circle = 1u << Button::CIRCLE;
			setup.triangle = 1u << Button::TRIANGLE;
			setup.square = 1u << Button::SQUARE;
			setup.up = 1u << Button::DPAD_UP;
			setup.down = 1u << Button::DPAD_DOWN;
			setup.left = 1u << Button::DPAD_LEFT;
			setup.right = 1u << Button::DPAD_RIGHT;
			setup.l1 = 1u << Button::L1;
			setup.r1 = 1u << Button::R1;
			setup.start = 1u << Button::START;
			online.Configure(setup);
			if(!options.onlineNames.empty()) online.QueueNames(options.onlineNames);

			// at this start? The option says so; the packaged application does it unless
			// it was told not to (and not in a test run, and not without the sign-in patch,
			// where the game only reaches a network error).
			std::string mode = options.online;
			if(mode.empty() && g_launch.packaged && !options.noOnline && !Rta::IsTestRun() && Rta::OnlineAtStart())
			{
				if(options.extraPatches.empty())
					Log("online: not going online by itself at this start: there is no sign-in patch");
				else
					mode = "lobby";
			}
			if(mode.empty() || options.noOnline) return;
			std::string error;
			if(!StartOnlineMode(mode, true, error)) Log("online: NOT going online by itself: " + error);
		}

		// ---- texture files --------------------------------------------------------------
		// Textures are known to the renderer by a figure of their contents (and of their
		// palette). With --rta-texture-dump each one is written once as
		//   <textures>/dump/<texels>-<palette>-p<format>-<width>x<height>.png
		// and a file of the same name in <textures>/replace/ - of any size - is drawn in
		// its place. That is how redrawn or enlarged art gets in. The files are RGBA with
		// the console's alpha: 128 is opaque (a viewer shows them half transparent); keep
		// the alpha channel as it is when working on them. Dumps are the game's art: they
		// stay out of the repository.
		static std::string TextureName(const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key)
		{
			// "mem-": a texture known only by what was found in GS memory, not by what the
			// game sent; such a name may not come back in another run
			return Format("%s%016llx-%016llx-p%u-%ux%u.png", (key.kind == 1) ? "" : "mem-", static_cast<unsigned long long>(key.hash), static_cast<unsigned long long>(key.clutHash), key.psm, key.width, key.height);
		}

		void StartTextures(const fs::path& base)
		{
			fs::path directory = options.textureDir.empty() ? (base / "textures") : fs::path(options.textureDir);
			auto dumpDirectory = directory / "dump";
			auto replaceDirectory = directory / "replace";
			std::error_code error;
			if(options.textureDump)
			{
				fs::create_directories(dumpDirectory, error);
				fs::create_directories(replaceDirectory, error);
				CGSH_OpenGL::g_textureDump = [this, dumpDirectory](const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key, const uint32* rgba, const CGSH_OpenGL::TEXTURE_PICTURE_USE& use) {
					auto name = TextureName(key);
					auto path = dumpDirectory / name;
					std::error_code exists;
					if(rgba && !fs::exists(path, exists))
					{
						QImage image(reinterpret_cast<const uchar*>(rgba), static_cast<int>(key.width), static_cast<int>(key.height), static_cast<int>(key.width * 4), QImage::Format_RGBA8888);
						if(image.save(QString::fromStdString(path.string()), "PNG")) m_texturesDumped++;
					}
					WriteTextureUse(dumpDirectory / (name.substr(0, name.size() - 4) + ".json"), name, key, use);
				};
				Log("textures: every new one is written to " + dumpDirectory.string() + ", with a .json file of how the game draws with it");
			}
			// the names that have a replacement: read at the start, and again when the
			// control socket's "texreplace reload" asks
			m_textureReplaceDirectory = replaceDirectory;
			if(options.textureMemory > 0) CGSH_OpenGL::g_textureReplaceBudget = static_cast<uint64>(options.textureMemory) * 1024 * 1024;
			if(options.textureWhole) CGSH_OpenGL::g_textureReplaceCrop = false;
			size_t nameCount = ListTextureReplacements();
			if((nameCount != 0) || options.textureDump || !options.controlPath.empty())
			{
				// The files are read by threads of their own (a picture of 2688 x 640 takes
				// longer to unpack than a frame lasts); the renderer asks again until the
				// picture is there and draws the game's own meanwhile.
				CGSH_OpenGL::g_textureLoad = [this](const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key, std::vector<uint32>& picture, uint32& width, uint32& height) {
					auto name = TextureName(key);
					std::lock_guard<std::mutex> lock(m_textureMutex);
					if(m_textureNames.count(name) == 0) return 0;
					auto ready = m_textureRead.find(name);
					if(ready != m_textureRead.end())
					{
						picture = std::move(ready->second.pixels);
						width = ready->second.width;
						height = ready->second.height;
						m_textureRead.erase(ready);
						m_textureAsked.erase(name);
						if(width == 0) return 0;
						m_texturesReplaced++;
						return 1;
					}
					if(m_textureAsked.insert(name).second)
					{
						m_textureQueue.push_back(name);
						m_textureWake.notify_one();
					}
					return 2;
				};
				// A picture that was asked for and is not wanted any more (its texture is not
				// drawn with any more): out of the queue, and what was read of it is let go
				CGSH_OpenGL::g_textureForget = [this](const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key) {
					auto name = TextureName(key);
					std::lock_guard<std::mutex> lock(m_textureMutex);
					m_textureRead.erase(name);
					if(m_textureAsked.erase(name) != 0)
					{
						auto queued = std::find(m_textureQueue.begin(), m_textureQueue.end(), name);
						if(queued != m_textureQueue.end()) m_textureQueue.erase(queued);
					}
				};
				// What to read first: the renderer says, frame by frame, how much of the screen
				// each picture that is being read covers (see ReadTextureFiles)
				CGSH_OpenGL::g_textureOrder = [this](const std::vector<std::pair<CGSH_OpenGL::TEXTURE_PICTURE_KEY, float>>& order) {
					std::unordered_map<std::string, float> priority;
					priority.reserve(order.size());
					for(const auto& entry : order) priority.emplace(TextureName(entry.first), entry.second);
					std::lock_guard<std::mutex> lock(m_textureMutex);
					m_texturePriority.swap(priority);
				};
				for(int i = 0; i < 3; i++) m_textureThreads.emplace_back([this]() { ReadTextureFiles(); });
				if(nameCount != 0) Log(Format("textures: %zu replacement file(s) in %s", nameCount, replaceDirectory.string().c_str()));
			}
		}

		size_t ListTextureReplacements()
		{
			std::set<std::string> names;
			std::error_code error;
			if(fs::is_directory(m_textureReplaceDirectory, error))
			{
				for(const auto& entry : fs::directory_iterator(m_textureReplaceDirectory, error))
				{
					auto name = entry.path().filename().string();
					if((name.size() > 4) && (name.compare(name.size() - 4, 4, ".png") == 0)) names.insert(name);
				}
			}
			std::lock_guard<std::mutex> lock(m_textureMutex);
			m_textureNames.swap(names);
			// what was read or is being read belongs to the files as they were
			m_textureGeneration++;
			m_textureQueue.clear();
			m_textureRead.clear();
			m_textureAsked.clear();
			m_texturePriority.clear();
			return m_textureNames.size();
		}

		// The readers take the picture that covers most of the screen first (interface art
		// counted fourfold: text is what the eye reads), then those asked for since the
		// renderer last spoke, then those whose texture is not being drawn with, the most
		// recently drawn first. Before, they were read in the order they were asked for,
		// which is the order the game draws in: the ground at the far end of the view came
		// before the character and the interface. A picture that is on the screen is read
		// as work the person is waiting for; one that is not (a menu is up) as work that
		// may wait, as all were before.
		void ReadTextureFiles()
		{
			qos_class_t working = QOS_CLASS_UTILITY;
			pthread_set_qos_class_self_np(working, 0);
			for(;;)
			{
				std::string name;
				uint32 generation = 0;
				qos_class_t wanted = QOS_CLASS_UTILITY;
				{
					std::unique_lock<std::mutex> lock(m_textureMutex);
					m_textureWake.wait(lock, [this]() { return m_textureStop || !m_textureQueue.empty(); });
					if(m_textureStop) return;
					auto best = m_textureQueue.begin();
					if(m_textureOrdered)
					{
						float bestPriority = -1e30f;
						for(auto queued = m_textureQueue.begin(); queued != m_textureQueue.end(); queued++)
						{
							auto known = m_texturePriority.find(*queued);
							float priority = (known != m_texturePriority.end()) ? known->second : 0.5f;
							if(priority > bestPriority)
							{
								bestPriority = priority;
								best = queued;
							}
						}
						if(bestPriority > 0) wanted = QOS_CLASS_USER_INITIATED;
					}
					name = *best;
					m_textureQueue.erase(best);
					generation = m_textureGeneration;
				}
				if(wanted != working)
				{
					working = wanted;
					pthread_set_qos_class_self_np(working, 0);
				}
				TexturePicture read;
				QImage image(QString::fromStdString((m_textureReplaceDirectory / name).string()));
				if(!image.isNull())
				{
					image = image.convertToFormat(QImage::Format_RGBA8888);
					read.width = static_cast<uint32>(image.width());
					read.height = static_cast<uint32>(image.height());
					read.pixels.resize(static_cast<size_t>(read.width) * read.height);
					for(uint32 y = 0; y < read.height; y++) memcpy(read.pixels.data() + (static_cast<size_t>(y) * read.width), image.constScanLine(static_cast<int>(y)), static_cast<size_t>(read.width) * 4);
				}
				std::lock_guard<std::mutex> lock(m_textureMutex);
				// kept only while somebody still waits for it
				if((generation == m_textureGeneration) && (m_textureAsked.count(name) != 0)) m_textureRead[name] = std::move(read);
			}
		}

		void StopTextureThreads()
		{
			{
				std::lock_guard<std::mutex> lock(m_textureMutex);
				m_textureStop = true;
			}
			m_textureWake.notify_all();
			for(auto& thread : m_textureThreads)
			{
				if(thread.joinable()) thread.join();
			}
			m_textureThreads.clear();
		}

		// What the game does with a picture, beside its dump as <name>.json: the size
		// TEX0 names, whether every texel was sent, each different way it was drawn
		// (blending, alpha test, wrapping, filter, scanline mask - the numbers are the GS
		// registers' fields) and the texel coordinates used: "sprite_uv" by sprites drawn to
		// all lines, "field0_uv" and "field1_uv" by sprites drawn under the scanline mask
		// to their own even and odd lines (the two halves of a two-field picture),
		// "other_uv" by triangles; each is u0, v0, u1, v1. A file that is there already
		// (an earlier run, or earlier in this one) is added to, never made poorer.
		static void WriteTextureUse(const fs::path& path, const std::string& name, const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key, const CGSH_OpenGL::TEXTURE_PICTURE_USE& use)
		{
			QString fileName = QString::fromStdString(path.string());
			QJsonObject root;
			{
				QFile file(fileName);
				if(file.open(QIODevice::ReadOnly)) root = QJsonDocument::fromJson(file.readAll()).object();
			}
			// a file written by disctex.py holds what was read from the disc, not seen
			if(root.contains("source")) root = QJsonObject();
			root["picture"] = QString::fromStdString(name);
			root["format"] = static_cast<int>(key.psm);
			root["width"] = static_cast<int>(key.width);
			root["height"] = static_cast<int>(key.height);
			root["named_width"] = static_cast<int>(use.namedWidth);
			root["named_height"] = static_cast<int>(use.namedHeight);
			root["whole"] = use.whole;
			auto states = root["states"].toArray();
			for(uint32 i = 0; i < use.stateCount; i++)
			{
				const auto& state = use.states[i];
				QJsonObject item;
				item["prim"] = state.prim;
				item["abe"] = state.abe;
				item["alpha"] = state.alpha;
				item["fix"] = state.fix;
				item["test"] = static_cast<int>(state.test);
				item["wms"] = state.wms;
				item["wmt"] = state.wmt;
				item["mag"] = state.mag;
				item["tfx"] = state.tfx;
				item["tcc"] = state.tcc;
				item["scanmsk"] = state.scanMask;
				item["context"] = state.context;
				bool known = false;
				for(const auto& other : states) known = known || (other.toObject() == item);
				if(!known) states.append(item);
			}
			root["states"] = states;
			if(use.statesOverflow) root["states_overflow"] = true;
			auto mergeBox = [&root](const QString& field, const CGSH_OpenGL::TEXTURE_PICTURE_USE::BOX& box) {
				if(!box.seen) return;
				double values[4] = {box.u0, box.v0, box.u1, box.v1};
				auto before = root[field].toArray();
				if(before.size() == 4)
				{
					values[0] = std::min(values[0], before[0].toDouble());
					values[1] = std::min(values[1], before[1].toDouble());
					values[2] = std::max(values[2], before[2].toDouble());
					values[3] = std::max(values[3], before[3].toDouble());
				}
				QJsonArray after;
				for(double value : values) after.append(std::round(value * 16.0) / 16.0);
				root[field] = after;
			};
			mergeBox("sprite_uv", use.sprite[0]);
			mergeBox("field0_uv", use.sprite[1]);
			mergeBox("field1_uv", use.sprite[2]);
			mergeBox("other_uv", use.other);
			QFile file(fileName);
			if(file.open(QIODevice::WriteOnly | QIODevice::Truncate)) file.write(QJsonDocument(root).toJson(QJsonDocument::Compact));
		}

		// ---- the network ----------------------------------------------------------------

		void StartNet()
		{
			Rta::NetConfig config;
			bool own = false;
			std::string where;
			if(options.server.empty() || options.server == "localhost")
				own = true;
			else if(!ResolveHost(options.server, config.serverIp))
			{
				Log("CANNOT find the lobby server '" + options.server + "': the game will not get online");
				m_netNote = "server not found";
			}
			else if(Rta::CNet::IsLoopback(config.serverIp))
				own = true;
			if(own)
			{
				// A server on this computer is reached at the computer's outside address,
				// as the rig does: the emulated machine cannot be told a loop-back address,
				// and the lobby server must see the address other players can use.
				config.serverIp = PrimaryAddress();
				if(config.serverIp == 0)
				{
					config.serverIp = INADDR_LOOPBACK;
					config.guestServerIp = 0xC6120002; // 198.18.0.2, a name for it inside the made-up network
					where = "this computer, which has no network address: only one emulator can play";
				}
				else
					where = "this computer (" + Rta::CNet::IpText(config.serverIp) + ")";
			}
			else if(config.serverIp != 0)
				where = options.server + (Rta::CNet::IpText(config.serverIp) == options.server ? "" : " (" + Rta::CNet::IpText(config.serverIp) + ")");

			if(!options.serverPublic.empty())
			{
				uint32 address = 0;
				if(ResolveHost(options.serverPublic, address))
					config.serverAliases.insert(address);
				else
					Log("cannot make sense of the server's public address '" + options.serverPublic + "'");
			}

			// The emulated machine's own address. The game reports it to the lobby server as
			// its "own-network" address and other players' games try it, so it should differ
			// from player to player: a random one from the range set aside for test networks,
			// kept in the settings.
			auto& appConfig = CAppConfig::GetInstance();
			appConfig.RegisterPreferenceString(PREF_RTA_GUEST_ADDRESS, "");
			std::string guest = options.guest.empty() ? appConfig.GetPreferenceString(PREF_RTA_GUEST_ADDRESS) : options.guest;
			uint32 guestIp = 0;
			if(!Rta::CNet::ParseIp(guest, guestIp) || (guestIp & config.netmask) != (config.gatewayIp & config.netmask) || (guestIp & 0xFF) == 0 || (guestIp & 0xFF) == 255 || (guestIp >> 8) == (config.gatewayIp >> 8))
			{
				if(!guest.empty()) Log("the machine's address '" + guest + "' is not usable (it has to be 198.19.x.y); a new one is made");
				std::random_device random;
				guestIp = 0xC6130000 | ((random() % 256) << 8) | (2 + random() % 250); // 198.19.x.y
				if(options.guest.empty()) appConfig.SetPreferenceString(PREF_RTA_GUEST_ADDRESS, Rta::CNet::IpText(guestIp).c_str());
			}
			config.guestIp = guestIp;

			bool serverIsHere = IsOwnAddress(config.serverIp);
			config.loopbackPeers = (options.loopback == "on") || (options.loopback != "off" && serverIsHere);
			config.bindGamePorts = options.bindGamePorts;
			config.lobbyName = options.lobbyName;
			config.pcapPath = options.pcapPath;
			if(options.gatewayPort > 0 && options.gatewayPort < 65536) config.testGatewayPort = static_cast<uint16_t>(options.gatewayPort);
			// which patch set this copy has, for the other players' copies (RtaNet.cpp)
			config.tellPatchSet = !options.setQuiet;
			config.patchSet = m_patchHash;
			config.patchWords = m_patchWords;
			config.passPatchSetOn = options.setRaw;
#ifdef FPUTILS_HAS_ARITHMETIC
			// this copy's machine can compute as a browser copy's does (CheckArithmetic)
			config.arithCan = Rta::ARITH_CAN_NATIVE | Rta::ARITH_CAN_BROWSER;
			if(options.arith == "browser") config.arithCan = Rta::ARITH_CAN_BROWSER;
			if(options.arith == "native") config.arithCan = Rta::ARITH_CAN_NATIVE;
#endif
			config.log = [this](const std::string& line) { Log("net: " + line); };
			m_net = std::make_unique<Rta::CNet>(config);
			m_net->SetArithmetic(m_arithNow);

			auto& speed = m_vm->m_iop->m_speed;
			speed.SetEthernetFrameTxHandler([this](const uint8* frame, uint32 size) {
				m_net->GuestSent(frame, size);
				PumpNet();
			});
			// about once per millisecond of the machine's time (the IOP runs at 36.864 MHz)
			speed.SetEthernetPollHandler([this]() {
				m_net->Poll();
				PumpNet();
			},
			                             36864);
			Log("network: lobby server " + where + "; the machine is " + Rta::CNet::IpText(config.guestIp) + "; " + config.lobbyName + " is answered with " +
			    Rta::CNet::IpText(config.guestServerIp ? config.guestServerIp : config.serverIp) + (config.loopbackPeers ? "; other emulators on this computer are reached through the loop-back interface" : ""));
			m_serverText = where;
		}

		// the chip takes one frame at a time
		void PumpNet()
		{
			auto& speed = m_vm->m_iop->m_speed;
			if(m_net->HasFrame() && speed.IsEthernetRxReady())
			{
				auto frame = m_net->TakeFrame();
				speed.RxEthernetFrame(frame.data(), static_cast<uint32>(frame.size()));
			}
		}

		// ---- patches --------------------------------------------------------------------

		void LoadPatches()
		{
			std::string error;
			if(!options.patchFile.empty() && !options.patchSections.empty())
			{
				std::set<std::string> wanted, found;
				bool all = options.patchSections == "*";
				if(!all && options.patchSections[0] == '@')
				{
					std::ifstream list(options.patchSections.substr(1));
					if(!list) Log("CANNOT read the list of patch sections " + options.patchSections.substr(1));
					std::string line;
					while(std::getline(list, line))
					{
						line = Trim(line);
						if(!line.empty() && line[0] != '#') wanted.insert(line);
					}
				}
				else if(!all)
				{
					for(const auto& name : Split(options.patchSections, ';'))
					{
						if(!Trim(name).empty()) wanted.insert(Trim(name));
					}
				}
				if(!ReadPatchFile(options.patchFile, wanted, all, m_patches, found, error))
				{
					Log("PATCHES NOT LOADED: " + error);
					m_patches.clear();
				}
				for(const auto& name : wanted)
				{
					if(found.count(name) == 0) Log("patch section not in the file: [" + name + "]");
				}
				// what every player has to have the same: a short figure to compare
				uint32 hash = 2166136261u;
				auto sorted = m_patches;
				std::sort(sorted.begin(), sorted.end(), [](const PatchWord& a, const PatchWord& b) { return a.address < b.address; });
				for(const auto& word : sorted)
				{
					for(uint32 v : {word.address, word.value})
					{
						for(int i = 0; i < 4; i++) hash = (hash ^ ((v >> (i * 8)) & 0xFF)) * 16777619u;
					}
				}
				m_patchHash = hash;
				m_patchWords = static_cast<uint16_t>(std::min<size_t>(m_patches.size(), 0xFFFF));
				m_patchSet = Format("%zu sections, %zu words, set %08x", found.size(), m_patches.size(), hash);
				Log("patches: " + m_patchSet + " from " + options.patchFile);
				for(const auto& name : found) Log("  [" + name + "]");
			}
			for(const auto& path : options.extraPatches)
			{
				std::set<std::string> found;
				size_t before = m_patches.size();
				if(!ReadPatchFile(path, {}, true, m_patches, found, error))
					Log("PATCH FILE NOT LOADED: " + error);
				else
					Log(Format("patches: %zu more words from %s", m_patches.size() - before, path.c_str()));
			}
		}

		// The machine is stopped here: either the application is booting it (its thread
		// waits) or its own thread is inside the "load another program" call.
		void OnExecutableChange()
		{
			auto os = m_vm->m_ee->m_os;
			std::string name = os->GetExecutableName();
			m_isGame = false;
			if(name.compare(0, strlen(GAME_EXECUTABLE), GAME_EXECUTABLE) == 0)
			{
				uint32 crc = 0;
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
				m_isGame = (crc == GAME_CRC);
				if(!m_isGame && !m_patches.empty())
					Log(Format("this is %s but not the version the patches are for (checksum %08X, wanted %08X): NO PATCH IS APPLIED", name.c_str(), crc, GAME_CRC));
			}
			Log("executable: " + name + (m_isGame ? Format(" (the game, version checked); %zu patch words", m_patches.size()) : ""));
			// Another program, or the same one again (the menu's Reset; the game restarting
			// itself): what the old one had open on the network is gone with it, and what
			// the application was pressing for it has no screen any more.
			if(m_executablesLoaded++ > 0)
			{
				if(m_net) m_net->DropTcp();
				if(online.Active()) online.Stop("the machine was started again");
			}
			m_foreignProgram = !m_isGame && (name.compare(0, strlen(GAME_EXECUTABLE), GAME_EXECUTABLE) != 0);
			m_activitySeen = false;
			m_quietFrames = 0;
			m_gameStuck = false;
			online.OnExecutable(m_isGame);
			m_activePatches.clear();
			if(m_isGame)
			{
				// nothing has been translated yet: the words can simply be written
				uint8* ram = m_vm->m_ee->m_ram;
				m_activePatches = m_patches;
				if(options.steadyPicture)
				{
					for(const auto& patch : g_displayPatches)
					{
						uint32 now = 0;
						memcpy(&now, ram + patch.address, 4);
						if(now != patch.original)
						{
							Log(Format("display patch at %08x not applied: found %08x where %08x was expected", patch.address, now, patch.original));
							continue;
						}
						PatchWord word;
						word.address = patch.address;
						word.value = patch.value;
						m_activePatches.push_back(word);
						Log(std::string("display patch: ") + patch.what);
					}
				}
				for(const auto& word : m_activePatches) memcpy(ram + word.address, &word.value, 4);
			}
			m_patchRewrites = 0;
		}

		// As PCSX2 does with its "every frame" patches: a word that is not what the patch
		// says is written again. Translated code on the page is thrown away first.
		void CheckPatches(uint8* ram)
		{
			if(!m_isGame) return;
			static const uint32 pageSize = static_cast<uint32>(getpagesize());
			unsigned int rewritten = 0;
			for(const auto& word : m_activePatches)
			{
				uint32 now;
				memcpy(&now, ram + word.address, 4);
				if(now == word.value) continue;
				uint32 start = word.address & ~(pageSize - 1);
				m_vm->m_ee->m_EE.m_executor->ClearActiveBlocksInRange(start, start + pageSize, false);
				memcpy(ram + word.address, &word.value, 4);
				rewritten++;
			}
			if(rewritten && m_patchRewrites++ < 5) Log(Format("%u patch word(s) had been overwritten and were written again", rewritten));
		}

		// ---- the game's network screen, and a game that has stopped (machine thread) ----
		// "Network Configuration and Selection" (after Internet Game) lists the setting the
		// application wrote to the memory card and offers, with triangle, "Config": the
		// game then shuts its network down and restarts the machine into Sony's network
		// settings program on the disc (NTGUI2.ELF), which restarts the game when it is
		// left. There is nothing to set in it here - the network behind the adaptor is the
		// application's own and the setting is written anew when it is missing - and it
		// throws a player out of the game into a program with other controls. So the button
		// is not passed on while that screen lists a setting (--rta-netcnf-program passes it
		// on: the program does run), and the status bar says why.
		//
		// A game that draws nothing for ten seconds while the machine runs is stuck (this one
		// does it when its sign-in step has failed and the error is cancelled: it never
		// comes back from unloading Sony's sign-in modules). The status bar then says so
		// and Escape, or Reset in the menu, starts the game again.
		void WatchGame(uint8* ram, uint64 frame)
		{
			auto word = [ram](uint32 address) {
				uint32 value = 0;
				address &= 0x1FFFFFFF;
				if(address != 0 && address <= PS2::EE_RAM_SIZE - 4) memcpy(&value, ram + address, 4);
				return value;
			};
			std::string note;
			bool block = false;
			bool frontEnd = m_isGame && (ram[A_IN_FRONTEND] == 1) && (memcmp(ram + A_LEVEL_NAME, "intro", 6) == 0);
			m_frontEndNow = frontEnd;
			uint32 fe = frontEnd ? word(A_FE_STATE) : 0, lobby = frontEnd ? word(A_LOBBY_STATE) : 0;
			if(frontEnd && fe == 10 && lobby == 2)
			{
				uint32 window = word(A_WIN_NET);
				uint32 state = window ? word(window + NET_STATE) : 0xFFFFFFFF;
				bool box = window && (word(window + NET_BOX) != 0);
				bool listed = window && (static_cast<int32>(word(window + NET_SETTINGS)) > 0);
				if(window && !box && state == 3 && listed)
				{
					block = !options.netcnfProgram;
					if(block) note = "The network is already set up: press cross (Accept). There is nothing to configure, so Config is switched off";
				}
				// while the card is still being read the button would do the same
				if(window && !box && state == 0 && options.netcnf && !options.netcnfProgram) block = true;
				if(window && state == 8)
				{
					note = options.extraPatches.empty() ? "The game's sign-in step failed: this copy has no sign-in patch, and without it the game cannot go online (Online > Server, player, patch set... says where it is looked for)"
					                                    : "The game reports a network error";
					note += ". Circle (Cancel) may leave the game stuck: Escape, or Reset in the menu, then starts it again";
				}
			}
			if(block && !m_blockConfig) Log("network screen: the setting is listed; Config (triangle) is not passed on to the game - there is nothing to configure (--rta-netcnf-program lets Sony's program start)");
			m_blockConfig = block;
			if(m_foreignProgram) note = "Sony's network settings program is running. Nothing needs to be set here. Back to the game: circle (Back) at its first menu, then Quit - or Reset in the menu";

			// does the machine draw? (what the renderer counts: transfers and textured draws)
			const auto& counters = CGSH_OpenGL::g_textureCounters;
			uint64 activity = counters.uploads.load() + counters.byUpload.load() + counters.byMemory.load() + counters.inPlace.load();
			if(activity != m_activity)
			{
				if(m_activitySeen && m_quietFrames >= 120) Log(Format("the machine drew nothing for %llu frames (%.1f s of its time)", static_cast<unsigned long long>(m_quietFrames), m_quietFrames / 60.0));
				if(m_activitySeen) m_quietMost = std::max(m_quietMost, m_quietFrames);
				m_activity = activity;
				m_activitySeen = true;
				m_quietFrames = 0;
				if(m_gameStuck)
				{
					m_gameStuck = false;
					Log("the game draws again");
				}
			}
			else if(m_activitySeen)
				m_quietFrames++;
			bool known = frontEnd && fe == 10 && lobby == 13; // leaving the lobby screens
			if(!m_gameStuck && m_activitySeen && m_quietFrames >= (known ? STUCK_FRAMES_KNOWN : STUCK_FRAMES))
			{
				m_gameStuck = true;
				m_stuckWhy = known ? "it does not come back from leaving its network screen (after a failed sign-in it cannot unload Sony's sign-in modules here)" : "it has drawn nothing for ten seconds";
				Log("THE GAME IS STUCK: " + m_stuckWhy + Format(" [front end %d, front-end state %u, lobby state %u, %s]. Escape or Reset starts it again", frontEnd ? 1 : 0, fe, lobby, CpuText().c_str()));
			}
			if(m_gameStuck) note = "The game is stuck: " + m_stuckWhy + ". Press Escape (or choose Reset in the menu) to start it again";
			(void)frame;
			std::lock_guard<std::mutex> lock(m_logMutex);
			m_gameNote = note;
		}

		// where the main processor is, for the log and the control socket
		std::string CpuText()
		{
			const auto& state = m_vm->m_ee->m_EE.m_State;
			return Format("pc=%08x ra=%08x sp=%08x idle=%d", state.nPC, state.nGPR[CMIPS::RA].nV0, state.nGPR[CMIPS::SP].nV0, m_vm->m_ee->m_os->IsIdle() ? 1 : 0);
		}

		void SetBoundButtons(uint32 buttons)
		{
			m_boundButtons = buttons;
		}
		bool BlockConfig() const
		{
			return m_blockConfig;
		}
		void ConfigPressed()
		{
			if(!m_configPressed) Log("network screen: Config (triangle) was pressed and left out");
			m_configPressed = true;
		}
		void ConfigReleased()
		{
			m_configPressed = false;
		}
		bool GameStuck() const
		{
			return m_gameStuck;
		}
		std::string GameNote()
		{
			std::lock_guard<std::mutex> lock(m_logMutex);
			return m_gameNote;
		}

		// ---- the machine's own thread, seen from the application's (any thread) ---------
		// True when the machine is not running (paused: its thread then looks for calls ten
		// times a second) or comes round to a vertical blank within the time given.
		bool MachineAnswers(int waitMs)
		{
			if(!m_vm || m_vm->GetStatus() != CVirtualMachine::RUNNING) return true;
			uint64 before = m_frame.load();
			if(before == 0) return true; // nothing has been started yet
			for(int waited = 0; waited < waitMs; waited += 20)
			{
				std::this_thread::sleep_for(std::chrono::milliseconds(20));
				if(m_frame.load() != before || m_vm->GetStatus() != CVirtualMachine::RUNNING) return true;
			}
			return m_frame.load() != before;
		}
		// once a second from the application's thread: seconds without a vertical blank
		int MachineSilentSeconds()
		{
			if(!m_vm || m_vm->GetStatus() != CVirtualMachine::RUNNING)
			{
				m_silentSeconds = 0;
				return 0;
			}
			uint64 now = m_frame.load();
			m_silentSeconds = (now == m_silentFrame && now != 0) ? (m_silentSeconds + 1) : 0;
			m_silentFrame = now;
			return m_silentSeconds;
		}
		void NoteReset()
		{
			Log("reset: the game is started again");
			if(online.Active()) online.Stop("the game was started again");
		}

		// ---- every vertical blank (machine thread) --------------------------------------

		void OnVBlank(CPadHandlerRta& pad, uint8* ram);

		// ---- the control socket ---------------------------------------------------------
		// A test script connects to a UNIX socket and sends one command per line; every
		// command is answered with one line ("ok ..." or "err ...") when it is done.
		//   press <buttons>   release <buttons>|all   tap <buttons> [hold [after]]
		//   stick <l|r> <x> <y>   (0..255, 128 is the middle)      wait <frames>
		//   peek <expression> <type>   shot <file.bmp>   shotfb <file.bmp>   burst <name> <n>   info   gs
		//   probe <file> <n> <x> <y> <w> <h>   bench   poke <expression> u8|u32|str <value>
		//   throttle <0|1>   pref int|bool <setting> <value>   ethdrop   quit
		//   online [start [lobby|host[:CODE]|join:CODE] | stop | forget | name NAME]
		// Buttons are joined with '+': up down left right cross circle square triangle
		// l1 l2 l3 r1 r2 r3 start select. Expressions: numbers, '+', '-', and [x] for the
		// 32-bit word at x. Types: u8 u16 u32 s32 x32 f32 strN wstrN hexN.

		struct Step
		{
			enum Kind
			{
				PRESS,
				RELEASE,
				STICK,
				WAIT,
				REPLY,
				SHOT,
				SHOTWAIT,
			} kind = WAIT;
			uint32 value = 0, value2 = 0, value3 = 0;
			std::string text;
		};

		void StartControl()
		{
			m_listenFd = socket(AF_UNIX, SOCK_STREAM, 0);
			sockaddr_un address = {};
			address.sun_family = AF_UNIX;
			if(m_listenFd < 0 || options.controlPath.size() >= sizeof(address.sun_path))
			{
				Log("control socket: cannot use " + options.controlPath);
				return;
			}
			strcpy(address.sun_path, options.controlPath.c_str());
			unlink(options.controlPath.c_str());
			if(bind(m_listenFd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 || listen(m_listenFd, 4) != 0)
			{
				Log("control socket: cannot listen on " + options.controlPath);
				close(m_listenFd);
				m_listenFd = -1;
				return;
			}
			fcntl(m_listenFd, F_SETFL, fcntl(m_listenFd, F_GETFL, 0) | O_NONBLOCK);
			signal(SIGPIPE, SIG_IGN);
			Log("control socket: " + options.controlPath);
		}

		void Reply(const std::string& line)
		{
			if(m_clientFd < 0) return;
			// the socket does not block: a long answer may take several writes
			std::string out = line + "\n";
			size_t done = 0;
			for(int tries = 0; (done < out.size()) && (tries < 2000); tries++)
			{
				ssize_t n = write(m_clientFd, out.data() + done, out.size() - done);
				if(n > 0)
					done += n;
				else if((n < 0) && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
					usleep(500);
				else
					break;
			}
			if(done < out.size())
			{
				close(m_clientFd);
				m_clientFd = -1;
			}
		}

		bool Evaluate(const char*& p, uint8* ram, uint32& value)
		{
			auto skip = [&]() { while(*p == ' ') p++; };
			auto term = [&](uint32& out) -> bool {
				skip();
				if(*p == '[')
				{
					p++;
					uint32 address = 0;
					if(!Evaluate(p, ram, address)) return false;
					skip();
					if(*p != ']') return false;
					p++;
					address &= 0x1FFFFFFF;
					if(address > PS2::EE_RAM_SIZE - 4) return false;
					memcpy(&out, ram + address, 4);
					return true;
				}
				char* end = nullptr;
				out = static_cast<uint32>(strtoul(p, &end, 0));
				if(end == p) return false;
				p = end;
				return true;
			};
			if(!term(value)) return false;
			for(;;)
			{
				skip();
				if(*p != '+' && *p != '-') return true;
				char op = *p++;
				uint32 right = 0;
				if(!term(right)) return false;
				value = (op == '+') ? value + right : value - right;
			}
		}

		std::string Peek(const std::string& expression, const std::string& type, uint8* ram)
		{
			const char* p = expression.c_str();
			uint32 address = 0;
			if(!Evaluate(p, ram, address) || *p != 0) return "err bad expression";
			address &= 0x1FFFFFFF;
			uint32 length = 4;
			std::string kind = type;
			size_t digits = kind.find_first_of("0123456789");
			if(kind.compare(0, 3, "str") == 0 || kind.compare(0, 4, "wstr") == 0 || kind.compare(0, 3, "hex") == 0)
			{
				length = static_cast<uint32>(strtoul(kind.c_str() + digits, nullptr, 10));
				kind = kind.substr(0, digits);
				if(kind == "wstr") length *= 2;
			}
			if(length == 0 || length > 4096 || address > PS2::EE_RAM_SIZE - length) return "err address outside main memory";
			const uint8* at = ram + address;
			uint32 word = 0;
			memcpy(&word, at, 4);
			if(kind == "u8") return Format("ok %u", at[0]);
			if(kind == "u16") return Format("ok %u", word & 0xFFFF);
			if(kind == "u32") return Format("ok %u", word);
			if(kind == "s32") return Format("ok %d", static_cast<int32>(word));
			if(kind == "x32") return Format("ok %08x", word);
			if(kind == "f32")
			{
				float f;
				memcpy(&f, at, 4);
				return Format("ok %g", f);
			}
			std::string out = "ok ";
			if(kind == "hex")
			{
				for(uint32 i = 0; i < length; i++) out += Format("%02x", at[i]);
				return out;
			}
			if(kind == "str" || kind == "wstr")
			{
				uint32 step = (kind == "wstr") ? 2 : 1;
				for(uint32 i = 0; i < length; i += step)
				{
					unsigned int c = at[i] | (step == 2 ? (at[i + 1] << 8) : 0);
					if(c == 0) break;
					out += (c >= 32 && c < 127) ? static_cast<char>(c) : '?';
				}
				return out;
			}
			return "err unknown type";
		}

		void Command(const std::string& line, uint8* ram)
		{
			std::istringstream stream(line);
			std::vector<std::string> words;
			std::string word;
			while(stream >> word) words.push_back(word);
			if(words.empty()) return;
			auto number = [&](size_t index, uint32 fallback) { return index < words.size() ? static_cast<uint32>(strtoul(words[index].c_str(), nullptr, 0)) : fallback; };
			auto push = [&](Step::Kind kind, uint32 value = 0, const std::string& text = "") {
				Step step;
				step.kind = kind;
				step.value = value;
				step.text = text;
				m_steps.push_back(step);
			};
			const std::string& name = words[0];
			uint32 mask = 0;
			if(name == "press" || name == "release" || name == "tap")
			{
				if(words.size() < 2 || (words[1] == "all" ? (mask = 0xFFFFFFFF, false) : !ParseButtons(words[1], mask)))
				{
					push(Step::REPLY, 0, "err unknown button");
					return;
				}
				if(name == "press") push(Step::PRESS, mask);
				if(name == "release") push(Step::RELEASE, mask);
				if(name == "tap")
				{
					push(Step::PRESS, mask);
					push(Step::WAIT, number(2, 8));
					push(Step::RELEASE, mask);
					push(Step::WAIT, number(3, 8));
				}
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "stick" && words.size() == 4)
			{
				Step step;
				step.kind = Step::STICK;
				step.value = (words[1] == "r") ? 1 : 0;
				step.value2 = number(2, 128) & 0xFF;
				step.value3 = number(3, 128) & 0xFF;
				m_steps.push_back(step);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "wait")
			{
				push(Step::WAIT, number(1, 1));
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "peek" && words.size() >= 3)
			{
				std::string expression;
				for(size_t i = 1; i + 1 < words.size(); i++) expression += words[i];
				push(Step::REPLY, 1, expression + " " + words.back());
			}
			else if((name == "shot" || name == "shotfb") && words.size() >= 2)
			{
				// shotfb: the picture as drawn (see RequestFramebufferCapture)
				Step step;
				step.kind = Step::SHOT;
				step.value3 = (name == "shotfb") ? 1 : 0;
				step.text = line.substr(line.find(words[1], name.size()));
				m_steps.push_back(step);
				push(Step::SHOTWAIT, 600);
			}
			else if(name == "info")
				push(Step::REPLY, 2);
			else if(name == "gs")
				push(Step::REPLY, 3);
			else if(name == "probe" && words.size() >= 7)
			{
				// probe <file> <n> <x> <y> <w> <h>: a rectangle of the window (pixels from the
				// bottom left) from n consecutive presented pictures, raw RGBA one after the
				// other in <file>, and "<index> <clock> <w> <h>" lines in <file>.txt
				Step step;
				step.kind = Step::SHOT;
				step.text = words[1];
				step.value = std::max<uint32>(1, std::min<uint32>(number(2, 2), 240));
				step.value2 = 1;
				m_probeRect[0] = number(3, 0);
				m_probeRect[1] = number(4, 0);
				m_probeRect[2] = std::max<uint32>(1, number(5, 1));
				m_probeRect[3] = std::max<uint32>(1, number(6, 1));
				m_steps.push_back(step);
				push(Step::SHOTWAIT, 1200);
			}
			else if(name == "burst" && words.size() >= 3)
			{
				Step step;
				step.kind = Step::SHOT;
				step.text = words[1];
				step.value = std::max<uint32>(1, std::min<uint32>(number(2, 2), 40));
				m_steps.push_back(step);
				push(Step::SHOTWAIT, 600);
			}
			else if(name == "throttle")
			{
				CAppConfig::GetInstance().SetPreferenceBoolean(PREF_PS2_LIMIT_FRAMERATE, number(1, 1) != 0);
				m_vm->ReloadFrameRateLimit();
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "pref" && words.size() == 4)
			{
				// pref int|bool <name> <value>: one of the application's settings, taken up at once
				auto& config = CAppConfig::GetInstance();
				bool ok = (words[1] == "int") ? config.SetPreferenceInteger(words[2].c_str(), static_cast<int>(number(3, 0))) : config.SetPreferenceBoolean(words[2].c_str(), number(3, 0) != 0);
				if(auto gs = m_vm->GetGSHandler()) gs->NotifyPreferencesChanged();
				push(Step::REPLY, 0, ok ? "ok" : "err no such setting");
			}
			else if(name == "poke" && words.size() >= 4)
			{
				// poke <expression> u8|u32|str <value>: writes the game's memory (for tests:
				// asking for another level as the rig does). Translated code on the page is
				// thrown away first.
				const char* p = words[1].c_str();
				uint32 address = 0;
				std::string kind = words[2];
				std::string text = line.substr(line.find(words[2], line.find(words[1]) + words[1].size()) + words[2].size());
				text = Trim(text);
				uint32 length = (kind == "u8") ? 1 : ((kind == "u32") ? 4 : static_cast<uint32>(text.size() + 1));
				if(!Evaluate(p, ram, address) || (*p != 0) || ((kind != "u8") && (kind != "u32") && (kind != "str")))
					push(Step::REPLY, 0, "err bad expression or type");
				else if(((address &= 0x1FFFFFFF) > (PS2::EE_RAM_SIZE - length)) || (length > 256))
					push(Step::REPLY, 0, "err address outside main memory");
				else
				{
					static const uint32 pageSize = static_cast<uint32>(getpagesize());
					uint32 start = address & ~(pageSize - 1);
					m_vm->m_ee->m_EE.m_executor->ClearActiveBlocksInRange(start, ((address + length + pageSize - 1) & ~(pageSize - 1)), false);
					if(kind == "str")
						memcpy(ram + address, text.c_str(), length);
					else
					{
						uint32 value = static_cast<uint32>(strtoul(text.c_str(), nullptr, 0));
						memcpy(ram + address, &value, length);
					}
					push(Step::REPLY, 0, "ok");
				}
			}
			else if(name == "bench")
			{
				// how fast is the processor core each of the two threads is on? (a loop of
				// plain arithmetic, timed by the clock and by the thread's processor time)
				auto work = []() {
					uint64 t0 = ClockMicroseconds(), c0 = ThreadCpuMicroseconds();
					volatile uint64 x = 88172645463325252ull;
					for(int i = 0; i < 40000000; i++)
					{
						uint64 y = x;
						y ^= y << 13;
						y ^= y >> 7;
						y ^= y << 17;
						x = y;
					}
					return std::make_pair(ClockMicroseconds() - t0, ThreadCpuMicroseconds() - c0);
				};
				auto machine = work();
				std::pair<uint64, uint64> video(0, 0);
				if(auto gs = m_vm->GetGSHandler()) gs->SendGSCall([&]() { video = work(); }, true);
				push(Step::REPLY, 0, Format("ok machine_thread clock_us=%llu cpu_us=%llu video_thread clock_us=%llu cpu_us=%llu", (unsigned long long)machine.first, (unsigned long long)machine.second, (unsigned long long)video.first, (unsigned long long)video.second));
			}
			else if(name == "gcpad" && words.size() >= 2)
			{
				// gcpad connect | disconnect | set <buttons|none> [lx ly rx ry [l2 r2]]
				// a controller made by the program (RtaPad.mm): sticks -1 .. 1 with up
				// and right positive, triggers 0 .. 1
				float values[6] = {0, 0, 0, 0, 0, 0};
				uint32 padButtons = 0;
				bool known = (words[1] == "connect" || words[1] == "disconnect");
				if(words[1] == "set" && words.size() >= 3 && (words[2] == "none" || ParseButtons(words[2], padButtons)))
				{
					for(size_t i = 3; i < words.size() && i < 9; i++) values[i - 3] = static_cast<float>(atof(words[i].c_str()));
					known = true;
				}
				if(known) Rta::GamePadTest(words[1], padButtons, values);
				push(Step::REPLY, 0, known ? "ok" : "err gcpad connect|disconnect|set <buttons|none> [lx ly rx ry [l2 r2]]");
			}
			else if(name == "uishot" && words.size() >= 3)
			{
				// uishot controls|online|about|playername|playername2|gamecode <file.png>: a picture of one of our windows
				std::string which = words[1], file = line.substr(line.find(words[2], line.find(words[1]) + words[1].size()));
				QMetaObject::invokeMethod(QCoreApplication::instance(), [which, file]() { Rta::RenderDialog(which, file); }, Qt::QueuedConnection);
				push(Step::WAIT, 30);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "pads")
				push(Step::REPLY, 4);
			else if(name == "sound")
				push(Step::REPLY, (words.size() >= 2 && words[1] == "reset") ? 6 : 5);
			else if(name == "texmode" && words.size() == 2)
			{
				// 0: textures by what the game sent; 1: by the texels in GS memory; 2: by
				// address, as Play! itself does (for comparing)
				CGSH_OpenGL::g_textureMode = static_cast<int>(number(1, 0));
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "texreplace" && words.size() == 2)
			{
				// texreplace 0|1: the pictures of <textures>/replace off or on while the
				// game runs (for the same frame with and without); texreplace reload: the
				// folder is listed again and every picture looked for again
				if(words[1] == "reload")
				{
					size_t count = ListTextureReplacements();
					CGSH_OpenGL::g_textureReplaceReload++;
					push(Step::WAIT, 3);
					push(Step::REPLY, 0, Format("ok %zu replacement file(s)", count));
				}
				else
				{
					CGSH_OpenGL::g_textureReplaceOn = (number(1, 1) != 0);
					push(Step::WAIT, 3);
					push(Step::REPLY, 0, "ok");
				}
			}
			else if(name == "texcrop" && words.size() == 2)
			{
				// texcrop 0|1: hand the whole of every replacement picture to the GPU, or
				// only the part of it the game draws with (the default); every picture is
				// read again
				CGSH_OpenGL::g_textureReplaceCrop = (number(1, 1) != 0);
				CGSH_OpenGL::g_textureReplaceReload++;
				push(Step::WAIT, 3);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "texorder" && words.size() == 2)
			{
				// texorder 0|1: the replacement pictures are read in the order they were
				// asked for, as before (0), or what covers most of the screen first (1, the
				// default). For measuring in one running game.
				m_textureOrdered = (number(1, 1) != 0);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "upscale" && words.size() == 2)
			{
				// upscale 0|1: point-sampled effect sprites, points and lines as the console
				// draws them (0) or as a higher resolution factor wants them (1, the default)
				CGSH_OpenGL::g_upscaleSmooth = (number(1, 1) != 0);
				push(Step::WAIT, 2);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "texcentre" && words.size() == 2)
			{
				// texcentre 0|1: filtered indexed textures read as Play! has it, half a
				// texel off (0), or round the place asked for (1, the default)
				CGSH_OpenGL::g_texelCentre = (number(1, 1) != 0);
				push(Step::WAIT, 3);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "edge" && words.size() == 2)
			{
				// edge 0|1: the whole of the console's picture is presented (0), or all but
				// its outermost line and column, which a television does not show (1, the default)
				CGSH_OpenGL::g_trimEdge = (number(1, 1) != 0);
				push(Step::WAIT, 2);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "drawlog" && words.size() >= 2)
			{
				// drawlog <file> [frames [x0 y0 x1 y1]]: how the game draws, for the next
				// 'frames' pictures (1): a line for every draw; with a rectangle (pixels of
				// the buffer drawn to) every primitive touching it vertex by vertex
				std::string file = words[1];
				uint32 frames = (words.size() >= 3) ? std::max<uint32>(1, std::min<uint32>(number(2, 1), 600)) : 1;
				bool hasRegion = (words.size() >= 7);
				float region[4] = {0, 0, 0, 0};
				for(size_t i = 0; hasRegion && (i < 4); i++) region[i] = static_cast<float>(atof(words[3 + i].c_str()));
				if(auto gs = m_vm->GetGSHandler()) gs->SendGSCall([=]() { CGSH_OpenGL::StartDrawLog(file, frames, hasRegion, region[0], region[1], region[2], region[3]); }, true);
				push(Step::WAIT, frames + 2);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "texmemory" && words.size() == 2)
			{
				// texmemory MB: what --rta-texture-memory sets, in the running game
				CGSH_OpenGL::g_textureReplaceBudget = static_cast<uint64>(std::max<uint32>(1, number(1, 3072))) * 1024 * 1024;
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "displaypatch" && words.size() == 3)
			{
				// displaypatch all|<index> 0|1: a display patch off or on while the game runs
				bool on = number(2, 1) != 0;
				unsigned int count = 0;
				for(size_t i = 0; i < (sizeof(g_displayPatches) / sizeof(g_displayPatches[0])); i++)
				{
					if(words[1] != "all" && number(1, 0) != i) continue;
					const auto& patch = g_displayPatches[i];
					auto same = [&](const PatchWord& word) { return word.address == patch.address; };
					m_activePatches.erase(std::remove_if(m_activePatches.begin(), m_activePatches.end(), same), m_activePatches.end());
					PatchWord word;
					word.address = patch.address;
					word.value = on ? patch.value : patch.original;
					// kept in the list either way, so that the word is written and the
					// translated code on its page thrown away at the next vertical blank
					m_activePatches.push_back(word);
					count++;
				}
				push(Step::REPLY, 0, Format("ok %u display patch(es) %s", count, on ? "on" : "off"));
			}
			else if(name == "online")
			{
				// online                      where the one-step log-in is (never a name or a password)
				// online start [lobby|host[:CODE]|join:CODE]   as "Play Online" in the menu
				// online stop | online forget
				// online name NAME            the player name, when a test run is waiting for one
				std::string action = (words.size() >= 2) ? words[1] : "";
				if(action.empty())
					push(Step::REPLY, 0, "ok " + online.Report() + " saved_login=" + (online.HasLogin() ? "1" : "0"));
				else if(action == "start")
				{
					std::string error;
					bool started = StartOnlineMode((words.size() >= 3) ? words[2] : "", false, error);
					push(Step::REPLY, 0, started ? "ok" : ("err " + error));
				}
				else if(action == "stop")
				{
					online.Stop("stopped from the control socket");
					push(Step::REPLY, 0, "ok");
				}
				else if(action == "forget")
					push(Step::REPLY, 0, online.Forget() ? "ok forgotten" : "ok nothing saved");
				else if(action == "name" && words.size() == 3)
				{
					std::string wrong = Rta::COnline::CheckName(words[2]);
					if(wrong.empty()) online.GiveName(words[2]);
					push(Step::REPLY, 0, wrong.empty() ? "ok" : ("err " + wrong));
				}
				else
					push(Step::REPLY, 0, "err online [start [lobby|host[:CODE]|join:CODE] | stop | forget | name NAME]");
			}
			else if(name == "ethdrop")
			{
				if(m_net) m_net->DropTcp();
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "cpu")
			{
				// where the main processor is, whether the game is taken to be stuck, and the
				// longest stretch (in frames) the machine has gone without drawing
				push(Step::REPLY, 0, "ok " + CpuText() + Format(" stuck=%d quiet=%llu quiet_most=%llu block_config=%d", m_gameStuck.load() ? 1 : 0, static_cast<unsigned long long>(m_quietFrames), static_cast<unsigned long long>(m_quietMost), m_blockConfig ? 1 : 0));
			}
			else if(name == "hw")
			{
				// the machine's interrupt and DMA registers, for telling what a game that has
				// stopped waits for: interrupt controller, DMA controller with the VIF1 and
				// GIF channels, the GS's status and interrupt mask, the processor's status
				auto map = m_vm->m_ee->m_EE.m_pMemoryMap;
				const auto& state = m_vm->m_ee->m_EE.m_State;
				auto word = [&](uint32 address) { return map->GetWord(address); };
				push(Step::REPLY, 0, Format("ok intc_stat=%x intc_mask=%x d_ctrl=%x d_stat=%x d1_chcr=%x d1_madr=%x d1_qwc=%x d1_tadr=%x d2_chcr=%x d2_madr=%x d2_qwc=%x d2_tadr=%x vif1_stat=%x gif_stat=%x gs_csr=%x gs_imr=%x status=%x epc=%x",
				                            word(0x1000F000), word(0x1000F010), word(0x1000E000), word(0x1000E010), word(0x10009000), word(0x10009010), word(0x10009020), word(0x10009030),
				                            word(0x1000A000), word(0x1000A010), word(0x1000A020), word(0x1000A030), word(0x10003C00), word(0x10003020), word(0x12001000), word(0x12001010),
				                            state.nCOP0[CCOP_SCU::STATUS], state.nCOP0[CCOP_SCU::EPC]));
			}
			else if(name == "note")
				push(Step::REPLY, 0, "ok " + GameNote());
			else if(name == "peers")
				push(Step::REPLY, 0, "ok " + PeersText());
			else if(name == "reset")
			{
				// what Reset in the application's menu does (answered at once; the machine
				// is started again a moment later)
				QMetaObject::invokeMethod(QCoreApplication::instance(), []() { Rta::TriggerReset(); }, Qt::QueuedConnection);
				push(Step::REPLY, 0, "ok");
			}
			else if(name == "hang" && words.size() == 2)
			{
				// test aid: the machine's own thread stops here for so many seconds, as it
				// would if the emulator itself were stuck. Nothing answers on this socket
				// meanwhile; "<control path>.ui" is the way to reach the application then.
				uint32 seconds = std::min<uint32>(number(1, 1), 120);
				Log(Format("test: the machine's thread stops for %u s", seconds));
				Reply("ok");
				std::this_thread::sleep_for(std::chrono::seconds(seconds));
			}
			else if(name == "quit")
			{
				Reply("ok");
				QMetaObject::invokeMethod(QCoreApplication::instance(), []() { QCoreApplication::exit(0); }, Qt::QueuedConnection);
			}
			else
				push(Step::REPLY, 0, "err unknown command");
		}

		void ControlVBlank(uint8* ram)
		{
			if(m_listenFd < 0) return;
			if(m_clientFd < 0)
			{
				m_clientFd = accept(m_listenFd, nullptr, nullptr);
				if(m_clientFd >= 0)
				{
					fcntl(m_clientFd, F_SETFL, fcntl(m_clientFd, F_GETFL, 0) | O_NONBLOCK);
					m_input.clear();
				}
			}
			if(m_clientFd >= 0)
			{
				char buffer[4096];
				for(;;)
				{
					ssize_t n = read(m_clientFd, buffer, sizeof(buffer));
					if(n > 0)
						m_input.append(buffer, n);
					else
					{
						if(n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR))
						{
							close(m_clientFd);
							m_clientFd = -1;
						}
						break;
					}
				}
				size_t end;
				while((end = m_input.find('\n')) != std::string::npos)
				{
					std::string line = Trim(m_input.substr(0, end));
					m_input.erase(0, end + 1);
					if(!line.empty()) Command(line, ram);
				}
			}
			while(!m_steps.empty())
			{
				Step& step = m_steps.front();
				if(step.kind == Step::WAIT)
				{
					if(step.value > 0)
					{
						step.value--;
						break;
					}
				}
				else if(step.kind == Step::PRESS)
					m_buttons |= step.value;
				else if(step.kind == Step::RELEASE)
					m_buttons &= ~step.value;
				else if(step.kind == Step::STICK)
				{
					m_stick[step.value][0] = static_cast<uint8>(step.value2);
					m_stick[step.value][1] = static_cast<uint8>(step.value3);
					m_stickSet[step.value] = !(step.value2 == 128 && step.value3 == 128);
				}
				else if(step.kind == Step::REPLY)
				{
					if(step.value == 1)
					{
						auto space = step.text.rfind(' ');
						Reply(Peek(step.text.substr(0, space), step.text.substr(space + 1), ram));
					}
					else if(step.value == 2)
					{
						uint64 us = ClockMicroseconds();
						auto ms = us / 1000;
						std::string net = "off";
						if(m_net)
						{
							const auto& s = m_net->Stats();
							net = Format("frames_out=%llu frames_in=%llu tcp=%llu tcp_out=%llu tcp_in=%llu udp_server=%llu udp_peers_out=%llu udp_peers_in=%llu dhcp=%d dns=%d",
							             (unsigned long long)s.framesFromGuest, (unsigned long long)s.framesToGuest, (unsigned long long)s.tcpConnections, (unsigned long long)s.tcpBytesOut, (unsigned long long)s.tcpBytesIn,
							             (unsigned long long)s.udpToServer, (unsigned long long)s.udpToPeers, (unsigned long long)s.udpFromPeers, s.dhcpDone ? 1 : 0, s.dnsAnswered ? 1 : 0);
						}
						const auto& tc = CGSH_OpenGL::g_textureCounters;
						std::string textures = Format("textures_dumped=%llu textures_replaced=%llu tex_made=%llu tex_held=%llu tex_by_upload=%llu tex_by_memory=%llu tex_memory_read=%llu tex_in_place=%llu tex_short_lived=%llu uploads=%llu tex_bytes=%llu tex_replace_on=%d tex_replacements=%llu tex_replacement_bytes=%llu tex_pending=%llu tex_dropped=%llu tex_cropped=%llu tex_regrown=%llu tex_abandoned=%llu frame_copies=%llu frame_copy_uses=%llu gs_buffer_drains=%llu gs_buffer_most=%llu tex_warmed=%llu tex_pending_area=%llu smoothed_draws=%llu scaled_points=%llu",
						                              static_cast<unsigned long long>(m_texturesDumped.load()), static_cast<unsigned long long>(m_texturesReplaced.load()), static_cast<unsigned long long>(tc.created.load()), static_cast<unsigned long long>(tc.alive.load()),
						                              static_cast<unsigned long long>(tc.byUpload.load()), static_cast<unsigned long long>(tc.byMemory.load()), static_cast<unsigned long long>(tc.memoryHashed.load()), static_cast<unsigned long long>(tc.inPlace.load()),
						                              static_cast<unsigned long long>(tc.shortLived.load()), static_cast<unsigned long long>(tc.uploads.load()), static_cast<unsigned long long>(tc.bytes.load()),
						                              CGSH_OpenGL::g_textureReplaceOn.load() ? 1 : 0, static_cast<unsigned long long>(tc.replacements.load()), static_cast<unsigned long long>(tc.replacementBytes.load()),
						                              static_cast<unsigned long long>(tc.replacementsPending.load()), static_cast<unsigned long long>(tc.replacementsDropped.load()),
						                              static_cast<unsigned long long>(tc.replacementsCropped.load()), static_cast<unsigned long long>(tc.replacementsRegrown.load()), static_cast<unsigned long long>(tc.replacementsAbandoned.load()), static_cast<unsigned long long>(tc.frameCopies.load()), static_cast<unsigned long long>(tc.frameCopyUses.load()),
						                              static_cast<unsigned long long>(CGSHandler::g_writeBufferDrains.load()), static_cast<unsigned long long>(CGSHandler::g_writeBufferMost.load()),
						                              static_cast<unsigned long long>(tc.replacementsWarmed.load()), static_cast<unsigned long long>(tc.pendingArea.load()), static_cast<unsigned long long>(tc.smoothedDraws.load()), static_cast<unsigned long long>(tc.scaledPoints.load()));
						Reply(Format("ok frame=%llu ms=%lld us=%llu cpu_us=%llu video_cpu_us=%llu display_hz=%.2f refreshes_per_frame=%d %s exe=%s game=%d %s", static_cast<unsigned long long>(m_frame.load()), static_cast<long long>(ms), static_cast<unsigned long long>(us),
						             static_cast<unsigned long long>(m_cpuMicroseconds.load()), static_cast<unsigned long long>(m_gsCpuMicroseconds.load()), Rta::DisplayRefreshRate(), Rta::DisplayRefreshesPerFrame(), textures.c_str(), m_vm->m_ee->m_os->GetExecutableName(), m_isGame ? 1 : 0, net.c_str()));
					}
					else if(step.value == 4)
						Reply("ok " + PadText());
					else if(step.value == 5 || step.value == 6)
						Reply("ok frame=" + std::to_string(m_frame.load()) + " " + Rta::SoundReport(step.value == 6));
					else if(step.value == 3)
					{
						// the picture the machine is sending to the screen right now
						auto gs = m_vm->GetGSHandler();
						if(!gs)
							Reply("err no video");
						else
						{
							auto info = gs->GetCurrentDisplayInfo();
							const auto& layer = info.layers[0];
							const auto& layer2 = info.layers[1];
							Reply(Format("ok smode2=%llx interlaced=%d framemode=%d field=%u crt=%ux%u display=%ux%u layer0=%d:%ux%u+%u+%u@%x/w%u/psm%u layer1=%d:%ux%u+%u+%u@%x/w%u/psm%u",
							             (unsigned long long)gs->GetSMODE2(), gs->GetCrtIsInterlaced() ? 1 : 0, gs->GetCrtIsFrameMode() ? 1 : 0, (gs->ReadPrivRegister(CGSHandler::GS_CSR) >> 13) & 1,
							             640u, gs->GetCrtHeight(), info.width, info.height,
							             layer.enabled ? 1 : 0, layer.width, layer.height, layer.offsetX, layer.offsetY, layer.bufPtr, layer.bufWidth, layer.psm,
							             layer2.enabled ? 1 : 0, layer2.width, layer2.height, layer2.offsetX, layer2.offsetY, layer2.bufPtr, layer2.bufWidth, layer2.psm));
						}
					}
					else
						Reply(step.text);
				}
				else if(step.kind == Step::SHOT)
				{
					m_shotDone = 0;
					auto gs = dynamic_cast<CGSH_OpenGLQt*>(m_vm->GetGSHandler());
					if(!gs)
						m_shotDone = -1;
					else if(step.value2 == 1)
					{
						// probe
						m_burstLeft = step.value;
						m_burstIndex = 0;
						std::string name = step.text;
						if(FILE* file = fopen(name.c_str(), "wb")) fclose(file);
						if(FILE* file = fopen((name + ".txt").c_str(), "w")) fclose(file);
						m_capture = [this, gs, name](const uint8* rgba, unsigned int width, unsigned int height) {
							uint64 clock = ClockMicroseconds();
							if(--m_burstLeft > 0) gs->RequestCapture(m_capture, m_probeRect[0], m_probeRect[1], m_probeRect[2], m_probeRect[3]);
							if(FILE* file = fopen(name.c_str(), "ab"))
							{
								fwrite(rgba, 1, static_cast<size_t>(width) * height * 4, file);
								fclose(file);
							}
							if(FILE* file = fopen((name + ".txt").c_str(), "a"))
							{
								fprintf(file, "%u %llu %u %u\n", m_burstIndex, static_cast<unsigned long long>(clock), width, height);
								fclose(file);
							}
							m_burstIndex++;
							if(m_burstLeft == 0) m_shotDone = 1;
						};
						gs->RequestCapture(m_capture, m_probeRect[0], m_probeRect[1], m_probeRect[2], m_probeRect[3]);
					}
					else
					{
						m_burstLeft = step.value;
						m_burstIndex = 0;
						std::string name = step.text;
						bool topFirst = (step.value3 == 1);
						m_capture = [this, gs, name, topFirst](const uint8* rgba, unsigned int width, unsigned int height) {
							// 24-bit BMP; the rows of the window's picture come bottom-up, as
							// the file wants them, those of the machine's own top first
							std::string path = name;
							if(m_burstLeft > 0)
							{
								// several consecutive pictures: <name>-0.bmp, <name>-1.bmp, ...
								// with the clock ('us' of the info command) at which each was presented
								if(FILE* times = fopen((name + "-times.txt").c_str(), m_burstIndex == 0 ? "w" : "a"))
								{
									fprintf(times, "%u %llu\n", m_burstIndex, static_cast<unsigned long long>(ClockMicroseconds()));
									fclose(times);
								}
								path = Format("%s-%u.bmp", name.c_str(), m_burstIndex++);
								if(--m_burstLeft > 0) gs->RequestCapture(m_capture);
							}
							FILE* file = fopen(path.c_str(), "wb");
							if(!file || width == 0 || height == 0)
							{
								if(file) fclose(file);
								m_shotDone = -1;
								return;
							}
							uint32 rowSize = (width * 3 + 3) & ~3u, dataSize = rowSize * height;
							uint8 header[54] = {'B', 'M'};
							auto put32 = [&](int at, uint32 value) { memcpy(header + at, &value, 4); };
							put32(2, 54 + dataSize);
							put32(10, 54);
							put32(14, 40);
							put32(18, width);
							put32(22, height);
							header[26] = 1;
							header[28] = 24;
							put32(34, dataSize);
							fwrite(header, 1, sizeof(header), file);
							std::vector<uint8> row(rowSize, 0);
							for(unsigned int y = 0; y < height; y++)
							{
								for(unsigned int x = 0; x < width; x++)
								{
									const uint8* pixel = rgba + (static_cast<size_t>(topFirst ? (height - 1 - y) : y) * width + x) * 4;
									row[x * 3 + 0] = pixel[2];
									row[x * 3 + 1] = pixel[1];
									row[x * 3 + 2] = pixel[0];
								}
								fwrite(row.data(), 1, row.size(), file);
							}
							fclose(file);
							if(m_burstLeft == 0) m_shotDone = 1;
						};
						if(topFirst)
							gs->RequestFramebufferCapture(m_capture);
						else
							gs->RequestCapture(m_capture);
					}
				}
				else if(step.kind == Step::SHOTWAIT)
				{
					if(m_shotDone == 0 && step.value > 0)
					{
						step.value--;
						break;
					}
					Reply(m_shotDone > 0 ? "ok" : "err no picture");
				}
				m_steps.pop_front();
			}
		}

		void UpdateStatus()
		{
			CheckPatchSets();
			CheckArithmetic();
			// what is wrong with the game comes first, then what the one-step log-in is doing
			std::string text = GameNote();
			if(!text.empty()) text += " | ";
			if(!m_setNote.empty()) text += m_setNote + " | ";
			if(!m_arithNote.empty()) text += m_arithNote + " | ";
			text += online.Note();
			if(!online.Note().empty()) text += " | ";
			if(m_net)
			{
				const auto& s = m_net->Stats();
				text += "Online: server " + m_serverText;
				if(!m_netNote.empty())
					text += " - " + m_netNote;
				else if(s.tcpBytesIn > 0)
					text += Format(" - connected (%llu bytes in); other players: %llu datagrams out, %llu in", (unsigned long long)s.tcpBytesIn, (unsigned long long)s.udpToPeers, (unsigned long long)s.udpFromPeers);
				else if(s.dhcpDone)
					text += " - network up";
				else
					text += " - waiting for the game to start its network";
			}
			if(!m_patchSet.empty()) text += (text.empty() ? "" : " | ") + ("patches: " + m_patchSet) + (m_isGame ? "" : " (not applied)");
			{
				auto name = Rta::GamePadName();
				if(!name.empty()) text += (text.empty() ? "" : " | ") + ("controller: " + name);
			}
			std::lock_guard<std::mutex> lock(m_logMutex);
			m_status = text;
		}

		// Other players' patch sets, as their copies told ours (RtaNet.cpp). A player not
		// heard from for fifteen seconds has left.
		void CheckPatchSets()
		{
			std::string note;
			if(m_net)
			{
				unsigned int different = 0, unknown = 0;
				uint32 theirs = 0;
				for(const auto& peer : m_net->Peers())
				{
					if(peer.silentFor > 15000) continue;
					if(!peer.setKnown)
					{
						if(peer.heardFor > 12000) unknown++;
						continue;
					}
					if(peer.patchSet == m_patchHash) continue;
					different++;
					theirs = peer.patchSet;
					uint64 key = (static_cast<uint64>(peer.ip) << 32) | peer.patchSet;
					if(m_setWarned.insert(key).second)
					{
						std::string text = Format("Another player in this game has a different patch set: theirs is %08x (%u words), yours is %08x (%u words).\n\n"
						                          "The game computes every frame on every machine, so with different patches the players fall out of step. "
						                          "Do not start the game: everyone needs the same build and the same patch list (Online > Server, player, patch set... shows yours).",
						                          peer.patchSet, peer.patchWords, m_patchHash, m_patchWords);
						Log(Format("WARNING: a player (%s:%u) has patch set %08x, this copy %08x: they would fall out of step%s", Rta::CNet::IpText(peer.ip).c_str(), peer.port, peer.patchSet, m_patchHash, options.testBackground ? "" : "; a window says so"));
						if(!options.testBackground) QMetaObject::invokeMethod(QCoreApplication::instance(), [text]() { Rta::WarnPatchSet(text); }, Qt::QueuedConnection);
					}
				}
				if(different)
					note = Format("WARNING: %s a DIFFERENT PATCH SET (%08x; yours %08x) - the game would fall out of step: do not start it", (different == 1) ? "another player has" : "other players have", theirs, m_patchHash);
				else if(unknown)
				{
					note = Format("%u other player%s not say which patch set they have (an older copy?): compare the figures yourselves", unknown, (unknown == 1) ? " does" : "s do");
					if(!m_setUnknownLogged) Log("another player's copy does not say which patch set it has (an older copy, or not this application)");
					m_setUnknownLogged = true;
				}
			}
			m_setNote = note;
		}
		// ---- Which arithmetic the machines of this game compute with -----------------------
		// (docs/issues/mixed-arithmetic.md; the datagram is described in RtaNet.cpp.) A
		// browser copy's machine can only round to nearest; this copy's can do that too
		// ("browser arithmetic", FpUtils.h). When a player is heard whose copy can only do
		// the browser's arithmetic - or one that has already changed to it for such a player
		// - this copy changes as well, and back to Play!'s own when nobody heard needs it.
		// That is decided where games are put together, in the front end (the lobby and the
		// room are there): once a level runs nothing is changed any more, because every
		// machine would have to change in the same lockstep tick. --rta-arith browser or
		// native fixes it instead (a copy fixed to one says that it cannot do the other).
		void CheckArithmetic()
		{
			std::string note;
#ifdef FPUTILS_HAS_ARITHMETIC
			std::vector<Rta::NetPeer> peers;
			if(m_net) peers = m_net->Peers();
			bool wantBrowser = (options.arith == "browser");
			if(options.arith == "auto")
			{
				for(const auto& peer : peers)
				{
					if(peer.silentFor > 15000 || !peer.arithKnown) continue;
					if(!(peer.arithCan & Rta::ARITH_CAN_NATIVE) || peer.arithNow == Rta::ARITH_BROWSER) wantBrowser = true;
				}
			}
			uint8 wanted = wantBrowser ? Rta::ARITH_BROWSER : Rta::ARITH_NATIVE;
			if(wanted != m_arithNow && (m_frontEndNow || options.arith != "auto"))
			{
				m_arithNow = wanted;
				FpUtils::SetArithmetic(wantBrowser ? FpUtils::ARITHMETIC_BROWSER : FpUtils::ARITHMETIC_NATIVE);
				if(m_net) m_net->SetArithmetic(wanted);
				Log(wantBrowser ? "arithmetic: the machine now computes as a browser copy's does (results rounded to nearest), from its next frame on"
				                : "arithmetic: the machine computes with Play!'s own arithmetic again (results rounded toward zero, as the console), from its next frame on");
			}
			unsigned int cannot = 0, differ = 0;
			for(const auto& peer : peers)
			{
				if(peer.silentFor > 15000) continue;
				if(!peer.arithKnown && peer.heardFor < 12000) continue; // it may still say
				uint8 can = peer.arithKnown ? peer.arithCan : static_cast<uint8>(Rta::ARITH_CAN_NATIVE);
				uint8 theirs = peer.arithKnown ? peer.arithNow : static_cast<uint8>(Rta::ARITH_NATIVE);
				if(!(can & (m_arithNow == Rta::ARITH_BROWSER ? Rta::ARITH_CAN_BROWSER : Rta::ARITH_CAN_NATIVE)))
					cannot++;
				else if(theirs != m_arithNow)
					differ++;
			}
			const char* mine = (m_arithNow == Rta::ARITH_BROWSER) ? "browser arithmetic" : "Play!'s own arithmetic";
			if(cannot)
				note = Format("WARNING: %s cannot compute with %s as this game does%s - the game would fall out of step: do not start it", (cannot == 1) ? "another player's copy" : "other players' copies", mine,
				              (m_arithNow == Rta::ARITH_BROWSER) ? " (an older copy, with a browser player in the game)" : "");
			else if(differ)
				note = Format("%s on different arithmetic from this copy's (%s)%s", (differ == 1) ? "another player's copy is" : "other players' copies are", mine,
				              m_frontEndNow ? ": wait for this to go away before starting" : " - WARNING: the game falls out of step");
			else if(m_arithNow == Rta::ARITH_BROWSER)
				note = "browser arithmetic";
			if((cannot || (differ && !m_frontEndNow)) && !m_arithWarned)
			{
				m_arithWarned = true;
				Log((note.compare(0, 8, "WARNING:") == 0) ? note : ("WARNING: " + note));
			}
			if(!cannot && !differ) m_arithWarned = false;
#endif
			m_arithNote = note;
		}
		std::string PeersText()
		{
			std::string text = Format("mine=%08x words=%u arith=%s", m_patchHash, m_patchWords, (m_arithNow == Rta::ARITH_BROWSER) ? "browser" : "native");
			if(m_net)
			{
				for(const auto& peer : m_net->Peers()) text += Format(" [%s:%u set=%s arith=%s heard_ms=%lld silent_ms=%lld]", Rta::CNet::IpText(peer.ip).c_str(), peer.port, peer.setKnown ? Format("%08x", peer.patchSet).c_str() : "?", !peer.arithKnown ? "?" : ((peer.arithNow == Rta::ARITH_BROWSER) ? "browser" : "native"), static_cast<long long>(peer.heardFor), static_cast<long long>(peer.silentFor));
			}
			return text + " note=" + m_setNote;
		}

		void FillLaunchInfo(Rta::LaunchInfo& info)
		{
			std::lock_guard<std::mutex> lock(m_logMutex);
			info.patchSet = m_patchSet;
			info.gameChecked = m_isGame;
			info.serverNow = m_serverText;
		}

		uint32 Buttons() const
		{
			return m_buttons;
		}

		// machine thread, every frame: the log gets the first press of each button of a
		// controller (so that a person can see that every one arrives, and as what)
		void NotePad(const Rta::PadState& pad)
		{
			m_pad = pad;
			if(pad.generation != m_padGeneration)
			{
				m_padGeneration = pad.generation;
				m_padSeen = 0;
				m_padSticksSeen = 0;
			}
			uint32 fresh = pad.buttons & ~m_padSeen;
			if(fresh != 0)
			{
				m_padSeen |= fresh;
				for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
				{
					if(fresh & (1u << i)) Log(std::string("controller: first press of ") + ButtonName(i));
				}
			}
			for(int which = 0; which < 2; which++)
			{
				if(!pad.stickSet[which]) continue;
				// the four ways of each stick, once each
				int dx = static_cast<int>(pad.stick[which][0]) - 128, dy = static_cast<int>(pad.stick[which][1]) - 128;
				int way = (abs(dx) > abs(dy)) ? ((dx < 0) ? 0 : 1) : ((dy < 0) ? 2 : 3);
				uint32 bit = 1u << ((which * 4) + way);
				if((abs(dx) > 90 || abs(dy) > 90) && !(m_padSticksSeen & bit))
				{
					m_padSticksSeen |= bit;
					static const char* ways[] = {"left", "right", "up", "down"};
					Log(Format("controller: %s stick pushed %s (%u, %u)", which ? "right" : "left", ways[way], pad.stick[which][0], pad.stick[which][1]));
				}
			}
		}

		static const char* ButtonName(unsigned int button)
		{
			static const char* names[Button::MAX_BUTTONS] = {"left stick x", "left stick y", "right stick x", "right stick y", "up", "down", "left", "right", "select", "start", "square", "triangle", "circle", "cross", "l1", "l2", "l3", "r1", "r2", "r3"};
			return (button < Button::MAX_BUTTONS) ? names[button] : "?";
		}

		std::string PadText() const
		{
			std::string text;
			for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
			{
				if(m_pad.buttons & (1u << i)) text += std::string(text.empty() ? "" : "+") + ButtonName(i);
			}
			if(text.empty()) text = "none";
			return Format("attached=%d name=%s buttons=%s left=%u,%u%s right=%u,%u%s", m_pad.attached ? 1 : 0, m_pad.attached ? Rta::GamePadName().c_str() : "-", text.c_str(),
			              m_pad.stick[0][0], m_pad.stick[0][1], m_pad.stickSet[0] ? "" : "(rest)", m_pad.stick[1][0], m_pad.stick[1][1], m_pad.stickSet[1] ? "" : "(rest)");
		}
		bool StickSet(int which) const
		{
			return m_stickSet[which];
		}
		uint8 Stick(int which, int axis) const
		{
			return m_stick[which][axis];
		}

	private:
		CPS2VM* m_vm = nullptr;
		std::unique_ptr<Rta::CNet> m_net;
		std::string m_serverText, m_netNote, m_patchSet, m_onlineNote;
		uint32 m_patchHash = 2166136261u; // the figure of the shared patch set (that of no patch at all until one is loaded)
		uint16 m_patchWords = 0;
		std::string m_setNote;             // the warning about another player's patch set
		std::set<uint64> m_setWarned;      // those a window has been shown for
		bool m_setUnknownLogged = false;
		std::string m_arithNote;           // what CheckArithmetic has to say
		uint8 m_arithNow = Rta::ARITH_NATIVE; // what the machine computes with (machine's thread)
		bool m_arithWarned = false;
		bool m_frontEndNow = false;        // the game is in its front end (WatchGame)
		std::vector<PatchWord> m_patches;       // from the patch files
		std::vector<PatchWord> m_activePatches; // those and the display patches, while the game is loaded
		bool m_isGame = false;
		unsigned int m_patchRewrites = 0;
		// the network screen and a game that has stopped (machine thread, but for the note)
		unsigned int m_executablesLoaded = 0;
		bool m_foreignProgram = false; // another program than the game is loaded (Sony's network settings)
		bool m_blockConfig = false, m_configPressed = false;
		uint64 m_activity = 0, m_quietFrames = 0, m_quietMost = 0;
		bool m_activitySeen = false;
		std::atomic<bool> m_gameStuck{false};
		std::string m_stuckWhy, m_gameNote, m_gameNoteShown;
		// the application's thread
		uint64 m_silentFrame = 0;
		int m_silentSeconds = 0;
		Framework::CSignal<void()>::Connection m_executableChange;
		std::atomic<uint64> m_frame{0};
		std::atomic<uint64> m_cpuMicroseconds{0}, m_gsCpuMicroseconds{0};
		std::atomic<uint64> m_texturesDumped{0}, m_texturesReplaced{0};
		fs::path m_textureReplaceDirectory;
		struct TexturePicture
		{
			std::vector<uint32> pixels;
			uint32 width = 0, height = 0;
		};
		std::mutex m_textureMutex; // for everything below
		std::set<std::string> m_textureNames;
		std::deque<std::string> m_textureQueue;           // asked for, not read yet
		// what the renderer said of each picture being read at the end of the last frame:
		// above zero the part of the screen it covers, below zero how long it has not been
		// drawn (CGSH_OpenGL::g_textureOrder). The readers take the highest first.
		std::unordered_map<std::string, float> m_texturePriority;
		std::atomic<bool> m_textureOrdered{true};         // off (control socket "texorder 0"): in the order asked for, as before
		std::set<std::string> m_textureAsked;             // in the queue, being read, or read
		std::map<std::string, TexturePicture> m_textureRead; // read, not fetched yet (width 0: unreadable)
		std::condition_variable m_textureWake;
		std::vector<std::thread> m_textureThreads;
		uint32 m_textureGeneration = 0;
		bool m_textureStop = false;

		std::mutex m_logMutex;
		FILE* m_logFile = nullptr;
		std::string m_status;

		int m_listenFd = -1, m_clientFd = -1;
		std::string m_input;
		std::deque<Step> m_steps;
		uint32 m_buttons = 0, m_boundButtons = 0;
		uint8 m_stick[2][2] = {{128, 128}, {128, 128}};
		bool m_stickSet[2] = {false, false};
		Rta::PadState m_pad;
		uint32 m_padGeneration = 0, m_padSeen = 0, m_padSticksSeen = 0;
		std::atomic<int> m_shotDone{0};
		CGSH_OpenGLQt::CaptureHandler m_capture;
		unsigned int m_burstLeft = 0, m_burstIndex = 0;
		unsigned int m_probeRect[4] = {0, 0, 1, 1};

		friend class CPadHandlerRta;
	};

	CState g_state;

	// The application's pad handler, with the control socket's buttons on top of the
	// keyboard's and the controller's for port 1.
	class CPadHandlerRta : public CPH_GenericInput
	{
	public:
		void Update(uint8* ram) override
		{
			CPH_GenericInput::Update(ram);
			// what the keyboard (and anything bound by hand) holds down, for the one-step
			// automation: a held button there means "I do this myself"
			uint32 bound = 0;
			for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
			{
				auto button = static_cast<Button>(i);
				if(!PS2::CControllerInfo::IsAxis(button) && GetBindingManager().GetBindingValue(0, button) != 0) bound |= 1u << i;
			}
			g_state.SetBoundButtons(bound);
			g_state.OnVBlank(*this, ram);
		}

		void Override(uint8* ram)
		{
			// the game controller, read here and now (see RtaPad.mm), and the control
			// socket's buttons; either on top of what the keyboard and Play!'s own
			// bindings gave
			auto pad = Rta::GamePadState();
			g_state.NotePad(pad);
			if(g_state.online.Driving())
			{
				// The application is pressing its way to the lobby: for these frames the
				// game sees its buttons and nothing else - not the keyboard's, not the
				// controller's, not a test script's - and both sticks at rest.
				uint32 own = g_state.online.Buttons();
				for(auto* listener : m_interfaces)
				{
					for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
					{
						auto button = static_cast<Button>(i);
						if(PS2::CControllerInfo::IsAxis(button))
							listener->SetAxisState(0, button, 0x80, ram);
						else
							listener->SetButtonState(0, button, (own & (1u << i)) != 0, ram);
					}
				}
				return;
			}
			uint32 buttons = g_state.Buttons() | pad.buttons;
			if(g_state.BlockConfig())
			{
				// the network screen's "Config" (see WatchGame): the game does not see the
				// button, wherever it is pressed - keyboard, controller or a test script
				if(buttons & (1u << Button::TRIANGLE))
					g_state.ConfigPressed();
				else
					g_state.ConfigReleased();
				buttons &= ~(1u << Button::TRIANGLE);
				for(auto* listener : m_interfaces) listener->SetButtonState(0, Button::TRIANGLE, false, ram);
			}
			bool stickSet[2];
			uint8 stick[2][2];
			for(int which = 0; which < 2; which++)
			{
				bool fromControl = g_state.StickSet(which);
				stickSet[which] = fromControl || pad.stickSet[which];
				for(int axis = 0; axis < 2; axis++) stick[which][axis] = fromControl ? g_state.Stick(which, axis) : pad.stick[which][axis];
			}
			if(buttons == 0 && !stickSet[0] && !stickSet[1]) return;
			for(auto* listener : m_interfaces)
			{
				for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
				{
					auto button = static_cast<Button>(i);
					if(PS2::CControllerInfo::IsAxis(button))
					{
						int which = (button == Button::ANALOG_LEFT_X || button == Button::ANALOG_LEFT_Y) ? 0 : 1;
						int axis = (button == Button::ANALOG_LEFT_X || button == Button::ANALOG_RIGHT_X) ? 0 : 1;
						if(stickSet[which]) listener->SetAxisState(0, button, stick[which][axis], ram);
					}
					else if(buttons & (1u << i))
						listener->SetButtonState(0, button, true, ram);
				}
			}
		}
	};

	void CState::OnVBlank(CPadHandlerRta& pad, uint8* ram)
	{
		if(!m_vm) return;
		uint64 frame = ++m_frame;
		if(frame == 1 || (frame % 600) == 0)
		{
			// again now and then: the video thread is made anew when the renderer changes
			RaiseThreadPriority();
			if(auto gs = m_vm->GetGSHandler()) gs->SendGSCall([]() { RaiseThreadPriority(); });
		}
		m_cpuMicroseconds = ThreadCpuMicroseconds();
		if((frame % 20) == 0)
		{
			if(auto gs = m_vm->GetGSHandler()) gs->SendGSCall([this]() { m_gsCpuMicroseconds = ThreadCpuMicroseconds(); });
		}
		CheckPatches(ram);
		ControlVBlank(ram);
		WatchGame(ram, frame);
		// the player's own buttons: keyboard, controller (as read a frame ago), test script
		online.SetPlayerButtons(m_boundButtons | m_buttons | m_pad.buttons);
		online.Tick(ram, PS2::EE_RAM_SIZE, m_isGame);
		pad.Override(ram);
		std::string gameNote = GameNote();
		if((frame % 30) == 0 || online.Note() != m_onlineNote || gameNote != m_gameNoteShown)
		{
			m_onlineNote = online.Note();
			m_gameNoteShown = gameNote;
			UpdateStatus();
		}
	}
}

// ---- what the application calls ---------------------------------------------------------

void Rta::EarlyInit(int argc, char** argv)
{
	bool dataGiven = false;
	int player = 0;
	for(int i = 1; i + 1 < argc; i++)
	{
		if(!strcmp(argv[i], "--rta-data")) setenv("RTA_DATA_DIR", argv[i + 1], 1), dataGiven = true;
		if(!strcmp(argv[i], "--rta-player")) player = atoi(argv[i + 1]);
	}
	for(int i = 1; i < argc; i++)
	{
		if(!strncmp(argv[i], "--rta-data=", 11)) setenv("RTA_DATA_DIR", argv[i] + 11, 1), dataGiven = true;
		if(!strncmp(argv[i], "--rta-player=", 13)) player = atoi(argv[i] + 13);
	}
	// "--rta-online" may stand alone or be followed by its mode (lobby, host, join:CODE,
	// the last two also with +choose at the end):
	// alone, it is given the mode the parser wants to see.
	for(int i = 1; i < argc; i++)
	{
		if(strcmp(argv[i], "--rta-online") != 0) continue;
		const char* next = (i + 1 < argc) ? argv[i + 1] : "";
		bool mode = !strcmp(next, "lobby") || !strcmp(next, "host") || !strncmp(next, "host:", 5) || !strncmp(next, "host+", 5) || !strncmp(next, "join:", 5);
		if(!mode)
		{
			static char alone[] = "--rta-online=lobby";
			argv[i] = alone;
		}
	}
	// The packaged application: our patch file is inside the bundle. Its data directory
	// has to be known before the application reads its settings, so it is found here.
	std::string resources = Rta::BundleResourcePath() + "/rta";
	std::error_code error;
	if(fs::exists(fs::path(resources) / BUNDLED_PATCH_NAME, error))
	{
		g_launch.packaged = true;
		g_launch.resources = resources;
		std::string name = Rta::BundleName();
		if(name.empty()) name = "Play-RTA";
		g_launch.root = Rta::ApplicationSupportPath() + "/" + name;
		fs::create_directories(g_launch.root, error);
		if(player <= 0) player = QSettings(QString::fromStdString(LaunchFile()), QSettings::IniFormat).value("player", 1).toInt();
		if(player <= 0 || player > 99) player = 1;
		g_launch.player = player;
		if(!dataGiven)
		{
			std::string data = g_launch.root + "/player" + std::to_string(player);
			fs::create_directories(data, error);
			setenv("RTA_DATA_DIR", data.c_str(), 1);
		}
	}
}

void Rta::AddCommandLineOptions(QCommandLineParser& parser)
{
	parser.addOption(QCommandLineOption("rta-data", "Directory for settings, memory cards and logs (default: Play!'s own).", "dir"));
	parser.addOption(QCommandLineOption("rta-server", "Lobby server: host name or IPv4 address (default: this computer).", "address"));
	parser.addOption(QCommandLineOption("rta-server-public", "The server's public address, when you are on the server's own network and it hands that address out.", "address"));
	parser.addOption(QCommandLineOption("rta-guest", "The emulated machine's own address, 198.19.x.y (default: a random one, kept).", "address"));
	parser.addOption(QCommandLineOption("rta-loopback", "Reach other emulators on this computer through the loop-back interface: auto (when the server is on this computer), on, off.", "mode", "auto"));
	parser.addOption(QCommandLineOption("rta-lobby-name", "The host name the game looks up.", "name", "con.soegames.net"));
	parser.addOption(QCommandLineOption("rta-any-port", "Do not try to give the host's UDP sockets the game's own port numbers (4000-4004)."));
	parser.addOption(QCommandLineOption("rta-no-net", "No network behind the emulated Ethernet adaptor."));
	parser.addOption(QCommandLineOption("rta-patch-file", "PCSX2-style patch file for the game.", "file"));
	parser.addOption(QCommandLineOption("rta-patch-sections", "Sections of the patch file to apply: names separated by ';', '@file' (one name per line) or '*'.", "sections"));
	parser.addOption(QCommandLineOption("rta-extra-patch", "A further patch file, applied whole. May be given more than once.", "file"));
	parser.addOption(QCommandLineOption("rta-interlaced", "Leave the game's half-line shift between television fields alone (the picture then jumps up and down; for comparing)."));
	parser.addOption(QCommandLineOption("rta-texture-dump", "Write every texture the game draws with, once, as a PNG file into <textures>/dump."));
	parser.addOption(QCommandLineOption("rta-textures", "Directory for texture files: dump/ and replace/ below it (default: textures in the data directory).", "dir"));
	parser.addOption(QCommandLineOption("rta-texture-memory", "Video memory the replacement pictures may take, in megabytes (default 3072); beyond it those not drawn with for ten seconds are given up and read again when needed.", "MB"));
	parser.addOption(QCommandLineOption("rta-texture-whole", "Hand the whole of every replacement picture to the graphics card, as before; without this only the part of it the game draws with (a level texture is a page of which a corner is used)."));
	parser.addOption(QCommandLineOption("rta-timer", "Time frames by a timer instead of by the display's refreshes."));
	parser.addOption(QCommandLineOption("rta-no-netcnf", "Do not write the network setting to the memory card."));
	parser.addOption(QCommandLineOption("rta-control", "UNIX socket for a test script (see tools/play-net/ctl.py).", "path"));
	parser.addOption(QCommandLineOption("rta-pcap", "Write every Ethernet frame of the emulated adaptor to this capture file.", "file"));
	parser.addOption(QCommandLineOption("rta-test", "A test run: the window says so in its title with this text (name what is switched off), is small, stays behind the other windows and does not take the keyboard.", "text"));
	parser.addOption(QCommandLineOption("rta-sound-wav", "Write the sound the machine makes to sound-<time>.wav in the data directory (game audio: keep it out of the repository)."));
	parser.addOption(QCommandLineOption("rta-sound-plain", "Queue sound as Play! itself does, without a held reserve (for comparing)."));
	parser.addOption(QCommandLineOption("rta-sound-block", "Milliseconds of sound handed over at a time (kept in the data directory's settings; 30 by default, 100 in Play! itself).", "ms"));
	parser.addOption(QCommandLineOption("rta-player", "Packaged application: the player number for this start (its own settings and memory card); otherwise the one set in the Online dialog.", "number"));
	parser.addOption(QCommandLineOption("rta-check-disc", "Say whether a file is a disc image of the game in the version this build is for, and end.", "file"));
	parser.addOption(QCommandLineOption("rta-online", "Go online by itself after power-on: 'lobby' (also when nothing follows the option) stops at the game list, 'host' in the room of a game of your own named with a code, 'join:CODE' in the room of the game with that code. Host and join take the character you used last; with '+choose' at the end (host+choose) the character screens are yours.", "mode"));
	parser.addOption(QCommandLineOption("rta-no-online", "Do not go online by itself at this start, whatever the setting says."));
	parser.addOption(QCommandLineOption("rta-online-name", "Test aid: the player name(s) to use instead of asking in a dialog, separated by commas (the next one is taken when the server refuses one).", "names"));
	parser.addOption(QCommandLineOption("rta-gateway-port", "Test aid: the TCP port at which this computer looks for the lobby server's gateway (a closed port stands for a server that is not there).", "port"));
	parser.addOption(QCommandLineOption("rta-set-quiet", "Test aid: do not tell the other players' copies which patch set this one has (as an older copy)."));
	parser.addOption(QCommandLineOption("rta-set-raw", "Test aid: hand the other players' patch-set datagrams on to the game as well (as an older copy would)."));
	parser.addOption(QCommandLineOption("rta-arith", "The machine's arithmetic: auto (as a browser copy's machine computes when a browser player is in the game, otherwise Play!'s own), browser, native.", "which"));
	parser.addOption(QCommandLineOption("rta-netcnf-program", "Let \"Config\" on the game's network screen start Sony's network settings program from the disc (left out otherwise: there is nothing to configure)."));
	parser.addOption(QCommandLineOption("rta-title", "A test run that a person takes part in: the window says so in its title with this text, and is otherwise an ordinary window.", "text"));
}

void Rta::ReadCommandLine(const QCommandLineParser& parser)
{
	auto& o = g_state.options;
	if(const char* dir = getenv("RTA_DATA_DIR")) o.dataDir = dir;
	o.server = parser.value("rta-server").toStdString();
	o.serverPublic = parser.value("rta-server-public").toStdString();
	o.guest = parser.value("rta-guest").toStdString();
	o.loopback = parser.value("rta-loopback").toStdString();
	o.lobbyName = parser.value("rta-lobby-name").toStdString();
	o.bindGamePorts = !parser.isSet("rta-any-port");
	o.net = !parser.isSet("rta-no-net");
	o.patchFile = parser.value("rta-patch-file").toStdString();
	o.patchSections = parser.value("rta-patch-sections").toStdString();
	for(const auto& path : parser.values("rta-extra-patch")) o.extraPatches.push_back(path.toStdString());
	o.steadyPicture = !parser.isSet("rta-interlaced");
	o.displayClock = !parser.isSet("rta-timer");
	o.textureDump = parser.isSet("rta-texture-dump");
	o.textureDir = parser.value("rta-textures").toStdString();
	o.textureMemory = parser.value("rta-texture-memory").toInt();
	o.textureWhole = parser.isSet("rta-texture-whole");
	o.netcnf = !parser.isSet("rta-no-netcnf");
	o.controlPath = parser.value("rta-control").toStdString();
	o.pcapPath = parser.value("rta-pcap").toStdString();
	o.testLabel = parser.value("rta-test").toStdString();
	if(parser.isSet("rta-test") && o.testLabel.empty()) o.testLabel = "ignore";
	o.testBackground = !o.testLabel.empty();
	if(parser.isSet("rta-check-disc"))
	{
		std::string verdict = Rta::CheckDisc(parser.value("rta-check-disc").toStdString());
		printf("%s\n", verdict.empty() ? "ok: Champions: Return to Arms, SLUS-20973, version 2.00" : verdict.c_str());
		exit(verdict.empty() ? 0 : 3);
	}
	if(g_launch.packaged)
	{
		// what play.sh gives on the command line, from inside the bundle and from the
		// Online dialog's file
		QSettings launch(QString::fromStdString(LaunchFile()), QSettings::IniFormat);
		g_launch.serverFrom = "--rta-server";
		if(!parser.isSet("rta-server"))
		{
			bool bundled = false;
			auto server = LaunchValue("server", &bundled);
			o.server = server.toString().trimmed().toStdString();
			g_launch.serverFrom = bundled ? "the default this application was made with" : (server.isValid() ? "launch.ini" : "nothing set");
		}
		// textures=<dir> in launch.ini: what --rta-textures gives
		if(!parser.isSet("rta-textures")) o.textureDir = launch.value("textures").toString().trimmed().toStdString();
		if(o.patchFile.empty())
		{
			o.patchFile = g_launch.resources + "/" + BUNDLED_PATCH_NAME;
			if(o.patchSections.empty()) o.patchSections = "@" + g_launch.resources + "/" + BUNDLED_SECTIONS_NAME;
		}
		// The sign-in patch is looked for in the data directory and beside the
		// application (the places a person is told about), and last inside the bundle,
		// where package.sh puts it only when asked to for a private build.
		if(o.extraPatches.empty())
		{
			std::vector<std::string> places = {g_launch.root, o.dataDir, fs::path(Rta::BundlePath()).parent_path().string()};
			for(const auto& place : places)
			{
				if(place.empty()) continue;
				std::string candidate = place + "/" + SIGNIN_PATCH_NAME;
				if(g_launch.signinPlaces.find(place + "\n") == std::string::npos) g_launch.signinPlaces += place + "\n";
				std::error_code error;
				if(g_launch.signinPatch.empty() && fs::exists(candidate, error)) g_launch.signinPatch = candidate;
			}
			if(g_launch.signinPatch.empty())
			{
				std::string inside = g_launch.resources + "/" + SIGNIN_PATCH_NAME;
				std::error_code error;
				if(fs::exists(inside, error)) g_launch.signinPatch = inside;
			}
			if(!g_launch.signinPatch.empty()) o.extraPatches.push_back(g_launch.signinPatch);
		}
	}
	else if(!o.extraPatches.empty())
		g_launch.signinPatch = o.extraPatches.front();
	o.soundWav = parser.isSet("rta-sound-wav");
	o.soundPlain = parser.isSet("rta-sound-plain");
	o.soundBlock = parser.value("rta-sound-block").toInt();
	o.online = parser.value("rta-online").toStdString();
	o.noOnline = parser.isSet("rta-no-online");
	for(const auto& name : parser.value("rta-online-name").split(',', Qt::SkipEmptyParts)) o.onlineNames.push_back(name.trimmed().toStdString());
	o.gatewayPort = parser.value("rta-gateway-port").toInt();
	o.netcnfProgram = parser.isSet("rta-netcnf-program");
	o.setQuiet = parser.isSet("rta-set-quiet");
	o.setRaw = parser.isSet("rta-set-raw");
	if(parser.isSet("rta-arith")) o.arith = parser.value("rta-arith").toStdString();
	if(o.arith != "browser" && o.arith != "native") o.arith = "auto";
	if(parser.isSet("rta-title")) o.testLabel = parser.value("rta-title").toStdString();
	if(o.testBackground) Rta::MakeBackgroundApplication();
}

void Rta::BeforeShow(QWidget* window)
{
	Rta::SetupWindow(window);
	if(g_state.options.testLabel.empty()) return;
	window->setWindowTitle(QString::fromStdString(Rta::WindowTitle("Play!")));
	if(!g_state.options.testBackground) return;
	window->setAttribute(Qt::WA_ShowWithoutActivating, true);
	window->resize(400, 340);
}

void Rta::AfterShow(QWidget* window)
{
	if(!g_state.options.testBackground) return;
	// now, and again when the picture's own window has been made
	auto back = [window]() { Rta::SendWindowBack(reinterpret_cast<void*>(window->winId())); };
	auto small = [window]() {
		window->setMinimumSize(0, 0);
		window->resize(400, 340);
	};
	back();
	small();
	QTimer::singleShot(500, window, [back, small]() {
		small();
		back();
	});
	QTimer::singleShot(3000, window, back);
}

std::string Rta::WindowTitle(const std::string& title)
{
	if(g_state.options.testLabel.empty()) return title;
	return "AGENT TEST - " + g_state.options.testLabel + " - " + title;
}

void Rta::LogLine(const std::string& line)
{
	g_state.Log(line);
}

Rta::LaunchInfo Rta::GetLaunchInfo()
{
	LaunchInfo info;
	info.packaged = g_launch.packaged;
	info.root = g_launch.root;
	info.player = g_launch.player;
	info.signinPatch = g_launch.signinPatch;
	info.signinPlaces = g_launch.signinPlaces;
	if(g_launch.packaged)
	{
		QSettings launch(QString::fromStdString(LaunchFile()), QSettings::IniFormat);
		info.server = LaunchValue("server").toString().trimmed().toStdString();
		info.disc = launch.value("disc").toString().toStdString();
	}
	else
		info.server = g_state.options.server;
	g_state.FillLaunchInfo(info);
	return info;
}

void Rta::SaveLaunch(const std::string& server, int player)
{
	if(!g_launch.packaged) return;
	QSettings launch(QString::fromStdString(LaunchFile()), QSettings::IniFormat);
	launch.setValue("server", QString::fromStdString(server));
	launch.setValue("player", player);
	launch.sync();
	g_state.Log(Format("online settings saved: server '%s', player %d (taken up at the next start)", server.c_str(), player));
}

void Rta::Relaunch()
{
	// a moment later, so that this copy has written its settings and let go of its data
	QString bundle = QString::fromStdString(Rta::BundlePath());
	QProcess::startDetached("/bin/sh", {"-c", "sleep 1.5; exec /usr/bin/open -n \"$0\"", bundle});
	QMetaObject::invokeMethod(QCoreApplication::instance(), []() { QCoreApplication::exit(0); }, Qt::QueuedConnection);
}

// ---- the disc image, found without asking -------------------------------------------------

namespace
{
	// Cheap, before the full check: a file of a DVD image's size that begins as an ISO 9660
	// volume does (any name), or one of the packed kinds, which only the full check reads.
	bool DiscCandidate(const fs::path& path)
	{
		struct stat info = {};
		if(stat(path.c_str(), &info) != 0 || !S_ISREG(info.st_mode)) return false;
#ifdef SF_DATALESS
		// kept in iCloud and not on this computer: looking into it would fetch all of it
		if(info.st_flags & SF_DATALESS) return false;
#endif
		uint64 size = static_cast<uint64>(info.st_size);
		std::string extension = path.extension().string();
		std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char c) { return static_cast<char>(tolower(c)); });
		if(extension == ".chd" || extension == ".cso" || extension == ".zso" || extension == ".isz") return size >= (256ull << 20);
		if(size < (1ull << 30) || size > (9ull << 30)) return false;
		FILE* file = fopen(path.c_str(), "rb");
		if(!file) return false;
		char magic[6] = {};
		bool volume = (fseeko(file, 0x8000, SEEK_SET) == 0) && (fread(magic, 1, 6, file) == 6) && (memcmp(magic, "\x01" "CD001", 6) == 0);
		fclose(file);
		return volume;
	}

	// the files of a directory, by name; with 'below', those of its sub-folders after them
	// (one level: not hidden ones, not application bundles)
	std::vector<fs::path> FilesIn(const fs::path& directory, bool below, bool& readable)
	{
		std::vector<fs::path> files, folders;
		std::error_code error;
		fs::directory_iterator entries(directory, fs::directory_options::skip_permission_denied, error);
		readable = !error;
		if(error) return files;
		for(fs::directory_iterator end; entries != end; entries.increment(error))
		{
			if(error) break;
			auto path = entries->path();
			std::string name = path.filename().string();
			if(name.empty() || name[0] == '.') continue;
			std::error_code kind;
			if(entries->is_regular_file(kind))
				files.push_back(path);
			else if(below && entries->is_directory(kind) && path.extension() != ".app")
				folders.push_back(path);
		}
		std::sort(files.begin(), files.end());
		std::sort(folders.begin(), folders.end());
		for(const auto& folder : folders)
		{
			bool ignored = false;
			auto inside = FilesIn(folder, false, ignored);
			files.insert(files.end(), inside.begin(), inside.end());
		}
		return files;
	}
}

std::string Rta::FindDisc()
{
	if(!g_launch.packaged) return std::string();
	// The application's own places first: they need nobody's permission. macOS asks the
	// person once before it lets an application read Downloads, Desktop or Documents.
	std::vector<std::pair<std::string, bool>> places;
	auto add = [&places](const std::string& directory, bool below) {
		if(directory.empty()) return;
		for(const auto& place : places)
		{
			if(place.first == directory) return;
		}
		places.push_back({directory, below});
	};
	add(fs::path(Rta::BundlePath()).parent_path().string(), false);
	add(g_launch.resources, false);
	add(g_launch.root, false);
	add(g_state.options.dataDir, false);
	for(auto location : {QStandardPaths::DownloadLocation, QStandardPaths::DesktopLocation, QStandardPaths::DocumentsLocation})
		add(QStandardPaths::writableLocation(location).toStdString(), true);
	std::string looked;
	for(const auto& place : places)
	{
		bool readable = false;
		auto files = FilesIn(place.first, place.second, readable);
		looked += (looked.empty() ? "" : ", ") + place.first + (readable ? "" : " (could not be read)");
		for(const auto& file : files)
		{
			if(!DiscCandidate(file)) continue;
			std::string verdict = Rta::CheckDisc(file.string());
			if(verdict.empty())
			{
				g_state.Log("disc image found without asking, looking in " + place.first + ": " + file.string());
				return file.string();
			}
			g_state.Log("disc image search: not the one: " + verdict);
		}
	}
	g_state.Log("disc image search: none found in " + looked);
	return std::string();
}

std::string Rta::CheckDisc(const std::string& path)
{
	const std::string wanted = "This build is for Champions: Return to Arms, the US release SLUS-20973 in version 2.00, and for nothing else.";
	std::string file = fs::path(path).filename().string();
	std::error_code error;
	if(!fs::is_regular_file(path, error)) return "'" + file + "' is not a file.";
	try
	{
		auto media = DiskUtils::CreateOpticalMediaFromPath(path, COpticalMedia::CREATE_AUTO_DISABLE_DL_DETECT);
		auto fileSystem = media->GetFileSystem();
		auto configFile = std::unique_ptr<Framework::CStream>(fileSystem->Open("SYSTEM.CNF;1"));
		if(!configFile) return "'" + file + "' is a disc image, but not of a PlayStation 2 game (it has no SYSTEM.CNF). " + wanted;
		auto config = DiskUtils::ParseSystemConfigFile(configFile.get());
		auto boot = config.find("BOOT2");
		if(boot == config.end()) return "'" + file + "' is not a PlayStation 2 game disc (its SYSTEM.CNF names no program). " + wanted;
		// "cdrom0:\SLUS_209.73;1"
		std::string program = boot->second;
		auto slash = program.find_last_of("\\:/");
		if(slash != std::string::npos) program = program.substr(slash + 1);
		std::string name = program.substr(0, program.find(';'));
		std::string version = config.count("VER") ? config["VER"] : "?";
		if(name != GAME_EXECUTABLE) return "'" + file + "' is the disc " + name + " (version " + version + "), another game or another release. " + wanted;
		auto executable = std::unique_ptr<Framework::CStream>(fileSystem->Open(program.c_str()));
		if(!executable) return "'" + file + "' names " + program + " as its program but does not hold it: the image is damaged. " + wanted;
		uint64 length = executable->GetLength();
		if(length > (64 * 1024 * 1024)) return "'" + file + "': the program on it is far too large; the image is damaged.";
		std::vector<uint8> content(static_cast<size_t>(length));
		if(executable->Read(content.data(), length) != length) return "'" + file + "' could not be read to the end: the image is damaged or cut short.";
		uint32 crc = 0;
		for(size_t i = 0; i + 4 <= content.size(); i += 4)
		{
			uint32 word;
			memcpy(&word, content.data() + i, 4);
			crc ^= word;
		}
		if(crc != GAME_CRC)
			return Format("'%s' is SLUS-20973, but version %s with another program (checksum %08X where version 2.00 has %08X): another pressing, or a changed image. %s", file.c_str(), version.c_str(), crc, GAME_CRC, wanted.c_str());
		return "";
	}
	catch(const std::exception& exception)
	{
		return "'" + file + "' is not a disc image this application can read (" + exception.what() + "). " + wanted;
	}
}

std::string Rta::AboutText()
{
	std::string text =
	    "\n\nThis is the Play! PlayStation 2 emulator (https://github.com/jpd002/Play-, by Jean-Philip Desjardins and contributors, BSD 2-clause licence) "
	    "with changes by the Champions RE project for playing Champions: Return to Arms online: a built-in network, patches, repairs to picture, sound and timing for this game, controller support.\n\n"
	    "It is not an official product of the Play! project, of Sony or of anyone else, and it contains nothing of the game: you need your own disc image.\n\n"
	    "The changes are described in tools/play-net/README.md of the project.";
	if(g_launch.packaged) text += " Licences: Contents/Resources/licences inside the application.";
	return text;
}

void Rta::OverridePreferences()
{
	// A machine that stops when its window is not in front loses the lobby server after
	// two minutes and stalls every other player at once.
	CAppConfig::GetInstance().SetPreferenceBoolean(PREF_UI_PAUSEWHENFOCUSLOST, false);
	// Settings for this game, put in place once per data directory (what the player
	// changes in the settings afterwards is kept; raising RTA_DEFAULTS puts them back):
	//  - the picture is computed at 4 times the console's resolution in each direction.
	//    At the console's own (640 x 224 per field) every edge is a staircase when it is
	//    stretched over a window;
	//  - sound is handed over in pieces of 30 ms instead of 100 ms, which is how far
	//    behind the picture it plays.
	auto& config = CAppConfig::GetInstance();
	config.RegisterPreferenceInteger(PREF_RTA_DEFAULTS, 0);
	config.RegisterPreferenceInteger(PREF_CGSH_OPENGL_RESOLUTION_FACTOR, RTA_RESOLUTION_FACTOR);
	config.RegisterPreferenceInteger(PREF_AUDIO_SPUBLOCKCOUNT, RTA_SPU_BLOCKS);
	// With the game drawing both fields at the same height (the display patch) the
	// pictures must be shown at the same place; without it, half a line apart.
	config.RegisterPreferenceBoolean(PREF_CGSHANDLER_FIELD_OFFSET, true);
	config.SetPreferenceBoolean(PREF_CGSHANDLER_FIELD_OFFSET, !g_state.options.steadyPicture);
	if(config.GetPreferenceInteger(PREF_RTA_DEFAULTS) < RTA_DEFAULTS)
	{
		config.SetPreferenceInteger(PREF_CGSH_OPENGL_RESOLUTION_FACTOR, RTA_RESOLUTION_FACTOR);
		config.SetPreferenceInteger(PREF_AUDIO_SPUBLOCKCOUNT, RTA_SPU_BLOCKS);
		config.SetPreferenceInteger(PREF_RTA_DEFAULTS, RTA_DEFAULTS);
	}
	if(!g_state.options.controlPath.empty()) CAppConfig::GetInstance().SetPreferenceBoolean(PREF_UI_SHOWEXITCONFIRMATION, false);
	if(g_state.options.soundBlock > 0) config.SetPreferenceInteger(PREF_AUDIO_SPUBLOCKCOUNT, g_state.options.soundBlock);
	// a background test run is silent
	Rta::ConfigureSound(g_state.options.soundWav, g_state.options.soundPlain, g_state.options.testBackground, CAppConfig::GetInstance().GetBasePath().string());
}

bool Rta::TakeKeyboardDefaults()
{
	auto& config = CAppConfig::GetInstance();
	config.RegisterPreferenceInteger(PREF_RTA_KEYS, 0);
	if(config.GetPreferenceInteger(PREF_RTA_KEYS) >= RTA_KEYS) return false;
	config.SetPreferenceInteger(PREF_RTA_KEYS, RTA_KEYS);
	return true;
}

bool Rta::IsTestRun()
{
	return !g_state.options.testLabel.empty() || !g_state.options.controlPath.empty();
}

// ---- one-step online ----------------------------------------------------------------------

bool Rta::OnlineStart(const std::string& mode, std::string& error)
{
	return g_state.StartOnlineMode(mode, false, error);
}

void Rta::OnlineStop()
{
	g_state.online.Stop("stopped from the menu");
}

bool Rta::OnlineActive()
{
	return g_state.online.Active();
}

void Rta::OnlineGiveName(const std::string& name)
{
	if(name.empty())
		g_state.online.DeclineName();
	else
		g_state.online.GiveName(name);
}

std::string Rta::OnlineCheckName(const std::string& name)
{
	return Rta::COnline::CheckName(name);
}

std::string Rta::OnlineCheckCode(const std::string& code)
{
	return Rta::COnline::CheckCode(code);
}

std::string Rta::OnlineSavedName()
{
	return g_state.online.LoginName();
}

std::string Rta::OnlineLastCharacter()
{
	return g_state.online.LastCharacter();
}

std::string Rta::OnlineNote()
{
	return g_state.online.Note();
}

std::string Rta::OnlineCode()
{
	return g_state.online.Code();
}

bool Rta::OnlineForget()
{
	return g_state.online.Forget();
}

bool Rta::OnlineAtStart()
{
	if(!g_launch.packaged) return false;
	auto online = LaunchValue("online");
	return online.isValid() ? online.toBool() : true;
}

void Rta::SetOnlineAtStart(bool on)
{
	if(!g_launch.packaged) return;
	QSettings launch(QString::fromStdString(LaunchFile()), QSettings::IniFormat);
	launch.setValue("online", on);
	launch.sync();
	g_state.Log(std::string("online: going online by itself at the start is ") + (on ? "on" : "off"));
}

// ---- when the machine or the game has stopped -----------------------------------------------

namespace
{
	// The machine's thread does not come round: everything that would wait for it - the
	// machine's Pause and Reset, and so the application's ordinary way of ending - would
	// wait for ever. The settings are written and the process ends here.
	[[noreturn]] void EndNow(bool startAgain)
	{
		CAppConfig::GetInstance().Save();
		if(startAgain)
		{
			QStringList arguments = QCoreApplication::arguments();
			QString program = QCoreApplication::applicationFilePath();
			if(!arguments.isEmpty()) arguments.removeFirst();
			arguments.prepend(program);
			QProcess::startDetached("/bin/sh", QStringList({"-c", "sleep 1.5; exec \"$0\" \"$@\""}) + arguments);
		}
		g_state.Log(startAgain ? "ending now; the application starts again in a moment" : "ending now");
		fflush(nullptr);
		_exit(0);
	}
}

std::string Rta::ControlPath()
{
	return g_state.options.controlPath;
}

bool Rta::BeforeReset(QWidget* parent)
{
	if(g_state.MachineAnswers(MACHINE_ANSWER_MS))
	{
		g_state.NoteReset();
		return false;
	}
	g_state.Log(Format("RESET asked for, but the emulated machine's own thread has not come round for %.1f s: it cannot be reset from inside", MACHINE_ANSWER_MS / 1000.0));
	if(g_state.options.testBackground)
	{
		g_state.Log("a test run: nobody is asked, the application is not started again");
		EndNow(false);
	}
	auto answer = QMessageBox::question(parent, "Reset", "The emulated machine has stopped answering, so it cannot be reset.\n\nEnd the application and start it again?", QMessageBox::Yes | QMessageBox::No);
	if(answer == QMessageBox::Yes) EndNow(true);
	return true;
}

bool Rta::BeforeClose()
{
	if(g_state.MachineAnswers(MACHINE_ANSWER_MS)) return false;
	g_state.Log("closing, and the emulated machine's own thread does not come round: ending without waiting for it");
	EndNow(false);
}

void Rta::EscapePressed()
{
	// outside full screen Escape has no other meaning: when the game (or the machine) is
	// known to have stopped, it starts the game again
	if(g_state.GameStuck() || !g_state.MachineAnswers(MACHINE_ANSWER_MS))
	{
		g_state.Log("Escape, and the game is stuck: reset");
		Rta::TriggerReset();
	}
}

CPadHandler::FactoryFunction Rta::GetPadHandlerFactory()
{
	return []() { return new CPadHandlerRta(); };
}

void Rta::Attach(CPS2VM* vm)
{
	g_state.Attach(vm);
}

void Rta::Detach()
{
	g_state.Detach();
}

std::string Rta::StatusText()
{
	// once a second, from the application's thread
	int silent = g_state.MachineSilentSeconds();
	if(silent >= 5)
	{
		if(silent == 5) g_state.Log("the emulated machine's own thread has not come round for 5 s");
		return Format("The emulated machine has stopped answering (%d s). Press Escape or choose Reset: the application then ends and can start again.", silent);
	}
	return g_state.StatusText();
}
