// See Rta.h. Everything here that touches the emulated machine runs on the machine's own
// thread: at the start of a vertical blank (from the pad handler, where the application
// reads its input), from the Ethernet chip's poll and transmit hooks, or while the
// machine is stopped for loading an executable.
#include "Rta.h"
#include "RtaNet.h"

#include <QCommandLineParser>
#include <QCoreApplication>
#include <QDir>
#include <QImage>
#include <QStringList>
#include <QTimer>
#include <QWidget>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <mutex>
#include <random>
#include <set>
#include <sstream>

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
#define RTA_DEFAULTS 2
#define RTA_RESOLUTION_FACTOR 4
#define RTA_SPU_BLOCKS 30

namespace
{
	// The executable these patches are for, and the checksum PCSX2 names its patch files
	// by (every 32-bit word of the file exclusive-ored together).
	const char* GAME_EXECUTABLE = "SLUS_209.73";
	const uint32 GAME_CRC = 0x4028A55F;

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
		std::string textureDir; // dump/ and replace/ below it; empty: <data>/textures
		bool netcnf = true;
		std::string controlPath;
		std::string pcapPath;
		std::string testLabel; // --rta-test: a test run, and what the window's title says about it
	};

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
			if(options.net) StartNet();

			m_executableChange = m_vm->m_ee->m_os->OnExecutableChange.Connect([this]() { OnExecutableChange(); });
			StartTextures(base);
			if(!options.controlPath.empty()) StartControl();
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
				CGSH_OpenGL::g_textureDump = [this, dumpDirectory](const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key, const uint32* rgba) {
					auto path = dumpDirectory / TextureName(key);
					std::error_code exists;
					if(fs::exists(path, exists)) return;
					QImage image(reinterpret_cast<const uchar*>(rgba), static_cast<int>(key.width), static_cast<int>(key.height), static_cast<int>(key.width * 4), QImage::Format_RGBA8888);
					if(image.save(QString::fromStdString(path.string()), "PNG")) m_texturesDumped++;
				};
				Log("textures: every new one is written to " + dumpDirectory.string());
			}
			// the names that have a replacement, read once
			auto names = std::make_shared<std::set<std::string>>();
			if(fs::is_directory(replaceDirectory, error))
			{
				for(const auto& entry : fs::directory_iterator(replaceDirectory, error)) names->insert(entry.path().filename().string());
			}
			if(!names->empty())
			{
				CGSH_OpenGL::g_textureLoad = [this, replaceDirectory, names](const CGSH_OpenGL::TEXTURE_PICTURE_KEY& key, std::vector<uint32>& picture, uint32& width, uint32& height) {
					auto name = TextureName(key);
					if(names->count(name) == 0) return false;
					QImage image(QString::fromStdString((replaceDirectory / name).string()));
					if(image.isNull()) return false;
					image = image.convertToFormat(QImage::Format_RGBA8888);
					width = static_cast<uint32>(image.width());
					height = static_cast<uint32>(image.height());
					picture.resize(static_cast<size_t>(width) * height);
					for(uint32 y = 0; y < height; y++) memcpy(picture.data() + (static_cast<size_t>(y) * width), image.constScanLine(static_cast<int>(y)), static_cast<size_t>(width) * 4);
					m_texturesReplaced++;
					return true;
				};
				Log(Format("textures: %zu replacement file(s) in %s", names->size(), replaceDirectory.string().c_str()));
			}
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
			config.log = [this](const std::string& line) { Log("net: " + line); };
			m_net = std::make_unique<Rta::CNet>(config);

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
			else if(name == "texmode" && words.size() == 2)
			{
				// 0: textures by what the game sent; 1: by the texels in GS memory; 2: by
				// address, as Play! itself does (for comparing)
				CGSH_OpenGL::g_textureMode = static_cast<int>(number(1, 0));
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
			else if(name == "ethdrop")
			{
				if(m_net) m_net->DropTcp();
				push(Step::REPLY, 0, "ok");
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
						std::string textures = Format("textures_dumped=%llu textures_replaced=%llu tex_made=%llu tex_held=%llu tex_by_upload=%llu tex_by_memory=%llu tex_memory_read=%llu tex_in_place=%llu tex_short_lived=%llu uploads=%llu",
						                              static_cast<unsigned long long>(m_texturesDumped.load()), static_cast<unsigned long long>(m_texturesReplaced.load()), static_cast<unsigned long long>(tc.created.load()), static_cast<unsigned long long>(tc.alive.load()),
						                              static_cast<unsigned long long>(tc.byUpload.load()), static_cast<unsigned long long>(tc.byMemory.load()), static_cast<unsigned long long>(tc.memoryHashed.load()), static_cast<unsigned long long>(tc.inPlace.load()),
						                              static_cast<unsigned long long>(tc.shortLived.load()), static_cast<unsigned long long>(tc.uploads.load()));
						Reply(Format("ok frame=%llu ms=%lld us=%llu cpu_us=%llu video_cpu_us=%llu display_hz=%.2f refreshes_per_frame=%d %s exe=%s game=%d %s", static_cast<unsigned long long>(m_frame.load()), static_cast<long long>(ms), static_cast<unsigned long long>(us),
						             static_cast<unsigned long long>(m_cpuMicroseconds.load()), static_cast<unsigned long long>(m_gsCpuMicroseconds.load()), Rta::DisplayRefreshRate(), Rta::DisplayRefreshesPerFrame(), textures.c_str(), m_vm->m_ee->m_os->GetExecutableName(), m_isGame ? 1 : 0, net.c_str()));
					}
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
			std::string text;
			if(m_net)
			{
				const auto& s = m_net->Stats();
				text = "Online: server " + m_serverText;
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
			std::lock_guard<std::mutex> lock(m_logMutex);
			m_status = text;
		}

		uint32 Buttons() const
		{
			return m_buttons;
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
		std::string m_serverText, m_netNote, m_patchSet;
		std::vector<PatchWord> m_patches;       // from the patch files
		std::vector<PatchWord> m_activePatches; // those and the display patches, while the game is loaded
		bool m_isGame = false;
		unsigned int m_patchRewrites = 0;
		Framework::CSignal<void()>::Connection m_executableChange;
		std::atomic<uint64> m_frame{0};
		std::atomic<uint64> m_cpuMicroseconds{0}, m_gsCpuMicroseconds{0};
		std::atomic<uint64> m_texturesDumped{0}, m_texturesReplaced{0};

		std::mutex m_logMutex;
		FILE* m_logFile = nullptr;
		std::string m_status;

		int m_listenFd = -1, m_clientFd = -1;
		std::string m_input;
		std::deque<Step> m_steps;
		uint32 m_buttons = 0;
		uint8 m_stick[2][2] = {{128, 128}, {128, 128}};
		bool m_stickSet[2] = {false, false};
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
			g_state.OnVBlank(*this, ram);
		}

		void Override(uint8* ram)
		{
			uint32 buttons = g_state.Buttons();
			if(buttons == 0 && !g_state.StickSet(0) && !g_state.StickSet(1)) return;
			for(auto* listener : m_interfaces)
			{
				for(unsigned int i = 0; i < Button::MAX_BUTTONS; i++)
				{
					auto button = static_cast<Button>(i);
					if(PS2::CControllerInfo::IsAxis(button))
					{
						int which = (button == Button::ANALOG_LEFT_X || button == Button::ANALOG_LEFT_Y) ? 0 : 1;
						int axis = (button == Button::ANALOG_LEFT_X || button == Button::ANALOG_RIGHT_X) ? 0 : 1;
						if(g_state.StickSet(which)) listener->SetAxisState(0, button, g_state.Stick(which, axis), ram);
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
		pad.Override(ram);
		if((frame % 30) == 0) UpdateStatus();
	}
}

// ---- what the application calls ---------------------------------------------------------

void Rta::EarlyInit(int argc, char** argv)
{
	for(int i = 1; i + 1 < argc; i++)
	{
		if(!strcmp(argv[i], "--rta-data")) setenv("RTA_DATA_DIR", argv[i + 1], 1);
	}
	for(int i = 1; i < argc; i++)
	{
		if(!strncmp(argv[i], "--rta-data=", 11)) setenv("RTA_DATA_DIR", argv[i] + 11, 1);
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
	parser.addOption(QCommandLineOption("rta-timer", "Time frames by a timer instead of by the display's refreshes."));
	parser.addOption(QCommandLineOption("rta-no-netcnf", "Do not write the network setting to the memory card."));
	parser.addOption(QCommandLineOption("rta-control", "UNIX socket for a test script (see tools/play-net/ctl.py).", "path"));
	parser.addOption(QCommandLineOption("rta-pcap", "Write every Ethernet frame of the emulated adaptor to this capture file.", "file"));
	parser.addOption(QCommandLineOption("rta-test", "A test run: the window says so in its title with this text (name what is switched off), is small, stays behind the other windows and does not take the keyboard.", "text"));
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
	o.netcnf = !parser.isSet("rta-no-netcnf");
	o.controlPath = parser.value("rta-control").toStdString();
	o.pcapPath = parser.value("rta-pcap").toStdString();
	o.testLabel = parser.value("rta-test").toStdString();
	if(parser.isSet("rta-test") && o.testLabel.empty()) o.testLabel = "ignore";
	if(!o.testLabel.empty()) Rta::MakeBackgroundApplication();
}

void Rta::BeforeShow(QWidget* window)
{
	if(g_state.options.testLabel.empty()) return;
	window->setAttribute(Qt::WA_ShowWithoutActivating, true);
	window->setWindowTitle(QString::fromStdString(Rta::WindowTitle("Play!")));
	window->resize(400, 340);
}

void Rta::AfterShow(QWidget* window)
{
	if(g_state.options.testLabel.empty()) return;
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
	return g_state.StatusText();
}
