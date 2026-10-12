// play-web: online play from a browser.
//
// Three things, all of them the desktop application's own code put to work in a page:
//
//  1. The sockets (RtaWebSock.h). The console's network is tools/play-net/src/RtaNet.cpp,
//     compiled as it is (RtaWebNetCore.cpp); what it does with sockets becomes messages on
//     the page's one WebSocket connection to the relay (tools/play-web/relay/relay.py),
//     which owns the real sockets. The connection belongs to the page's main thread
//     (rta-web.js: a thread that runs the machine never comes back to the browser, so it
//     cannot hear a WebSocket); the machine's thread and the main thread meet in the two
//     queues below.
//  2. The Ethernet adaptor's two hooks, and the network setting on the memory card that
//     the game wants to find (as Rta.cpp does both).
//  3. "One-step online" and games by code: tools/play-net/src/RtaOnline.cpp as it is,
//     called at every vertical blank; the page asks for the player name and shows what it
//     says.
//
// Messages: see relay.py. A page reaches the lobby server and other pages of the same
// relay, and nothing else.

#include "RtaWebNet.h"
#include "RtaWebSock.h"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <filesystem>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <vector>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>

#include <emscripten.h>
#include <emscripten/proxying.h>
#include <emscripten/threading.h>

#include "AppConfig.h"
#include "ControllerInfo.h"
#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "RtaNet.h"
#include "RtaOnline.h"

namespace
{
	// ---- the relay's messages -----------------------------------------------------------
	enum : uint8_t
	{
		M_TCP_OPEN = 2,
		M_TCP_DATA = 3,
		M_TCP_SHUT = 4,
		M_TCP_CLOSE = 5,
		M_UDP_OPEN = 6,
		M_UDP_SEND = 7,
		M_UDP_CLOSE = 8,
		R_WELCOME = 0x81,
		R_TCP_OPENED = 0x82,
		R_TCP_DATA = 0x83,
		R_TCP_EOF = 0x84,
		R_TCP_CLOSED = 0x85,
		R_UDP_BOUND = 0x86,
		R_UDP_RECV = 0x87,
	};
	enum
	{
		FD_UDP = 0x4000,
		FD_TCP = 0x5000,
		MAX_UDP = 8,
		MAX_TCP = 8,
		UDP_QUEUE_MAX = 256,     // datagrams waiting for the machine on one socket
		OUT_QUEUE_MAX = 4096,    // messages waiting for the page's main thread
		TCP_PIECE = 4096,        // bytes of one TCP_DATA message
	};
	enum LINK
	{
		LINK_NONE = 0,    // no connection to the relay
		LINK_OPENING = 1, // the page is connecting
		LINK_UP = 2,      // the relay has answered: its sockets are ours
	};

	struct Datagram
	{
		uint32_t ip = 0;
		uint16_t port = 0;
		std::vector<uint8_t> data;
	};
	struct UdpSock
	{
		bool used = false;
		uint16_t relayPort = 0; // the relay's socket for it, as the lobby server sees it
		std::deque<Datagram> in;
	};
	struct TcpSock
	{
		enum STATE
		{
			NEW,
			CONNECTING,
			OPEN,
			FAILED,
			GONE,
		};
		bool used = false;
		uint16_t id = 0; // the connection's number in the messages; never used twice
		STATE state = NEW;
		int error = 0;
		bool eof = false, shut = false;
		std::deque<uint8_t> in;
	};

	std::mutex g_mutex; // everything down to the counters: both threads
	UdpSock g_udp[MAX_UDP];
	TcpSock g_tcp[MAX_TCP];
	uint16_t g_nextId = 1;
	std::deque<std::vector<uint8_t>> g_out;
	bool g_wakePosted = false, g_wantLink = false;
	int g_link = LINK_NONE;
	uint32_t g_lobbyIp = 0, g_relayIp = 0;
	uint64_t g_sent = 0, g_received = 0, g_lost = 0;

	bool g_configured = false; // the page has a relay
	std::string g_stats;       // the network's own counters, as JSON members (machine thread writes)
	std::string g_text;        // what a function returned last

	void Put16(std::vector<uint8_t>& m, uint16_t v)
	{
		m.push_back(static_cast<uint8_t>(v >> 8));
		m.push_back(static_cast<uint8_t>(v));
	}
	void Put32(std::vector<uint8_t>& m, uint32_t v)
	{
		Put16(m, static_cast<uint16_t>(v >> 16));
		Put16(m, static_cast<uint16_t>(v));
	}
	uint16_t Get16(const uint8_t* p)
	{
		return static_cast<uint16_t>((p[0] << 8) | p[1]);
	}
	uint32_t Get32(const uint8_t* p)
	{
		return (static_cast<uint32_t>(Get16(p)) << 16) | Get16(p + 2);
	}

	// ---- from the machine's thread to the page's main thread ----------------------------
	// clang-format off
	EM_JS(void, RtaWebNetWakeJs, (), {
		if(Module["rtaNetWake"]) Module["rtaNetWake"]();
	});
	// clang-format on
	void WakeOnMain(void*)
	{
		RtaWebNetWakeJs();
	}
	// g_mutex held
	void Wake()
	{
		if(g_wakePosted) return;
		g_wakePosted = true;
		emscripten_proxy_async(emscripten_proxy_get_system_queue(), emscripten_main_runtime_thread_id(), &WakeOnMain, nullptr);
	}
	// g_mutex held; false: there is no relay to give it to
	bool Queue(std::vector<uint8_t>&& message)
	{
		if(g_link != LINK_UP || g_out.size() >= OUT_QUEUE_MAX)
		{
			g_lost++;
			if(g_link == LINK_NONE && !g_wantLink)
			{
				g_wantLink = true;
				Wake();
			}
			return false;
		}
		g_out.push_back(std::move(message));
		g_sent++;
		Wake();
		return true;
	}

	UdpSock* Udp(int fd)
	{
		if(fd < FD_UDP || fd >= FD_UDP + MAX_UDP || !g_udp[fd - FD_UDP].used) return nullptr;
		return &g_udp[fd - FD_UDP];
	}
	TcpSock* Tcp(int fd)
	{
		if(fd < FD_TCP || fd >= FD_TCP + MAX_TCP || !g_tcp[fd - FD_TCP].used) return nullptr;
		return &g_tcp[fd - FD_TCP];
	}
	TcpSock* TcpById(uint16_t id)
	{
		for(auto& c : g_tcp)
		{
			if(c.used && c.id == id) return &c;
		}
		return nullptr;
	}

	// ---- the machine's side: network, adaptor, online driver (machine thread) ------------
	CPS2VM* g_vm = nullptr;
	std::unique_ptr<Rta::CNet> g_net;
	uint32_t g_patchSet = 0;
	uint16_t g_patchWords = 0;
	Rta::COnline g_online;
	std::atomic<bool> g_nameWanted(false);
	std::string g_nameWhy; // g_mutex
	uint32_t g_vblanks = 0;

	std::string Json(const std::string& text)
	{
		std::string out = "\"";
		for(unsigned char c : text)
		{
			if(c == '"' || c == '\\')
			{
				out += '\\';
				out += static_cast<char>(c);
			}
			else if(c < 0x20)
			{
				char code[8];
				snprintf(code, sizeof(code), "\\u%04x", c);
				out += code;
			}
			else
				out += static_cast<char>(c);
		}
		return out + "\"";
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

	void Pump()
	{
		auto& speed = g_vm->m_iop->m_speed;
		if(g_net->HasFrame() && speed.IsEthernetRxReady())
		{
			auto frame = g_net->TakeFrame();
			speed.RxEthernetFrame(frame.data(), static_cast<uint32>(frame.size()));
		}
	}

	// The network is made when the relay has said where the lobby server is. Until then
	// what the machine sends is lost, as on a cable that is not plugged in yet (the game's
	// own address request is repeated).
	bool HaveNet()
	{
		if(g_net) return true;
		uint32_t lobby = 0;
		{
			std::lock_guard<std::mutex> lock(g_mutex);
			if(g_link != LINK_UP)
			{
				if(g_configured && g_link == LINK_NONE && !g_wantLink)
				{
					g_wantLink = true;
					Wake();
				}
				return false;
			}
			lobby = g_lobbyIp;
		}
		Rta::NetConfig config;
		config.serverIp = lobby;
		// The machine's own address: the game tells it to the lobby server as its
		// "own-network" address, so it should differ from player to player.
		std::random_device random;
		config.guestIp = 0xC6130000 | ((random() % 256) << 8) | (2 + random() % 250); // 198.19.x.y
		config.loopbackPeers = false;
		config.bindGamePorts = false; // the relay's sockets have the ports the relay's system gives them
		config.tellPatchSet = true;
		config.patchSet = g_patchSet;
		config.patchWords = g_patchWords;
		config.log = [](const std::string& line) { printf("RTA net: %s\n", line.c_str()); };
		g_net = std::make_unique<Rta::CNet>(config);
		printf("RTA net: the console's network is up: lobby server %s through the relay; the machine is %s\n", Rta::CNet::IpText(lobby).c_str(), Rta::CNet::IpText(config.guestIp).c_str());
		return true;
	}

	// the network's counters and the other players, for the page (every half second)
	void TakeStats()
	{
		std::string text;
		if(g_net)
		{
			const auto& s = g_net->Stats();
			text = Format("\"net\":{\"dhcp\":%d,\"dns\":%d,\"tcp_connections\":%llu,\"tcp_out\":%llu,\"tcp_in\":%llu,\"udp_to_server\":%llu,\"udp_from_server\":%llu,"
			              "\"udp_to_players\":%llu,\"udp_from_players\":%llu,\"dropped\":%llu},\"players\":[",
			              s.dhcpDone ? 1 : 0, s.dnsAnswered ? 1 : 0, static_cast<unsigned long long>(s.tcpConnections), static_cast<unsigned long long>(s.tcpBytesOut),
			              static_cast<unsigned long long>(s.tcpBytesIn), static_cast<unsigned long long>(s.udpToServer), static_cast<unsigned long long>(s.udpFromServer),
			              static_cast<unsigned long long>(s.udpToPeers), static_cast<unsigned long long>(s.udpFromPeers), static_cast<unsigned long long>(s.dropped));
			bool first = true;
			for(const auto& peer : g_net->Peers())
			{
				// what the desktop application's CheckPatchSets and CheckArithmetic read (Rta.cpp):
				// the page makes the same two warnings from it (rta-web.js, onlineShow)
				text += Format("%s{\"port\":%u,\"set_known\":%d,\"same_set\":%d,\"set\":\"%08x\",\"words\":%u,\"arith_known\":%d,\"can_browser\":%d,\"can_native\":%d,\"does_browser\":%d,"
				               "\"heard_ms\":%lld,\"silent_ms\":%lld}",
				               first ? "" : ",", peer.port, peer.setKnown ? 1 : 0, (peer.setKnown && peer.patchSet == g_patchSet) ? 1 : 0, peer.patchSet, peer.patchWords, peer.arithKnown ? 1 : 0,
				               (peer.arithCan & Rta::ARITH_CAN_BROWSER) ? 1 : 0, (peer.arithCan & Rta::ARITH_CAN_NATIVE) ? 1 : 0, (peer.arithNow == Rta::ARITH_BROWSER) ? 1 : 0,
				               static_cast<long long>(peer.heardFor), static_cast<long long>(peer.silentFor));
				first = false;
			}
			text += "],";
		}
		std::lock_guard<std::mutex> lock(g_mutex);
		g_stats = text;
	}

	// ---- the network setting on the memory card (Rta.cpp: NetcnfScramble, WriteNetcnf) ---
	std::vector<uint8_t> NetcnfScramble(const std::string& text)
	{
		static const unsigned int key[3] = {6, 3, 3};
		std::vector<uint8_t> out;
		size_t index = 0;
		for(size_t i = 0; i + 1 < text.size(); i += 2, index++)
		{
			unsigned int word = static_cast<uint8_t>(text[i]) | (static_cast<uint8_t>(text[i + 1]) << 8);
			unsigned int shift = key[index % 3];
			word = ((word << shift) | (word >> (16 - shift))) & 0xFFFF;
			word ^= 0xFFFF;
			out.push_back(static_cast<uint8_t>(word));
			out.push_back(static_cast<uint8_t>(word >> 8));
		}
		if(text.size() & 1)
		{
			unsigned int byte = static_cast<uint8_t>(text.back());
			unsigned int shift = key[index % 3];
			byte = ((byte << shift) | (byte >> (8 - shift))) & 0xFF;
			out.push_back(static_cast<uint8_t>(byte ^ 0xFF));
		}
		return out;
	}

	bool WriteFile(const std::filesystem::path& path, const void* data, size_t size)
	{
		FILE* file = fopen(path.string().c_str(), "wb");
		if(!file) return false;
		bool ok = fwrite(data, 1, size, file) == size;
		fclose(file);
		return ok;
	}

	// 0: there already; 1: written; -1: could not
	int WriteNetcnf(const std::filesystem::path& cardDirectory)
	{
		auto directory = cardDirectory / "BWNETCNF";
		std::error_code error;
		if(std::filesystem::exists(directory / "BWNETCNF", error)) return 0;
		std::filesystem::create_directories(directory, error);
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
}

// ---- RtaWebSock.h: the socket calls of RtaNet.cpp (machine thread) ----------------------

int rtaSockSocket(int, int type, int)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if(type == SOCK_DGRAM)
	{
		for(int i = 0; i < MAX_UDP; i++)
		{
			if(g_udp[i].used) continue;
			g_udp[i] = UdpSock();
			g_udp[i].used = true;
			return FD_UDP + i;
		}
	}
	else if(type == SOCK_STREAM)
	{
		for(int i = 0; i < MAX_TCP; i++)
		{
			if(g_tcp[i].used) continue;
			g_tcp[i] = TcpSock();
			g_tcp[i].used = true;
			g_tcp[i].id = g_nextId++;
			if(g_nextId == 0) g_nextId = 1;
			return FD_TCP + i;
		}
	}
	errno = EMFILE;
	return -1;
}

// A UDP socket is bound at the relay, to a port of the relay's choosing.
int rtaSockBind(int fd, const sockaddr*, socklen_t)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if(!Udp(fd))
	{
		errno = EBADF;
		return -1;
	}
	Queue({M_UDP_OPEN, static_cast<uint8_t>(fd - FD_UDP)});
	return 0;
}

int rtaSockConnect(int fd, const sockaddr* address, socklen_t length)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	TcpSock* c = Tcp(fd);
	if(!c || length < sizeof(sockaddr_in))
	{
		errno = EBADF;
		return -1;
	}
	const auto* to = reinterpret_cast<const sockaddr_in*>(address);
	std::vector<uint8_t> message = {M_TCP_OPEN};
	Put16(message, c->id);
	Put32(message, ntohl(to->sin_addr.s_addr));
	Put16(message, ntohs(to->sin_port));
	if(!Queue(std::move(message)))
	{
		c->state = TcpSock::FAILED;
		c->error = ENETUNREACH;
		errno = ENETUNREACH;
		return -1;
	}
	c->state = TcpSock::CONNECTING;
	errno = EINPROGRESS;
	return -1;
}

ssize_t rtaSockSend(int fd, const void* data, size_t length, int)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	TcpSock* c = Tcp(fd);
	if(!c)
	{
		errno = EBADF;
		return -1;
	}
	if(c->state == TcpSock::CONNECTING)
	{
		errno = EAGAIN;
		return -1;
	}
	if(c->state != TcpSock::OPEN || c->shut)
	{
		errno = EPIPE;
		return -1;
	}
	length = std::min<size_t>(length, TCP_PIECE);
	std::vector<uint8_t> message = {M_TCP_DATA};
	Put16(message, c->id);
	message.insert(message.end(), static_cast<const uint8_t*>(data), static_cast<const uint8_t*>(data) + length);
	if(!Queue(std::move(message)))
	{
		errno = EPIPE;
		return -1;
	}
	return static_cast<ssize_t>(length);
}

ssize_t rtaSockRecv(int fd, void* data, size_t length, int)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	TcpSock* c = Tcp(fd);
	if(!c)
	{
		errno = EBADF;
		return -1;
	}
	if(!c->in.empty())
	{
		size_t n = std::min(length, c->in.size());
		std::copy(c->in.begin(), c->in.begin() + n, static_cast<uint8_t*>(data));
		c->in.erase(c->in.begin(), c->in.begin() + n);
		return static_cast<ssize_t>(n);
	}
	if(c->eof) return 0;
	if(c->state == TcpSock::FAILED || c->state == TcpSock::GONE)
	{
		errno = ECONNRESET;
		return -1;
	}
	errno = EAGAIN;
	return -1;
}

ssize_t rtaSockSendTo(int fd, const void* data, size_t length, int, const sockaddr* address, socklen_t addressLength)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if(!Udp(fd) || addressLength < sizeof(sockaddr_in))
	{
		errno = EBADF;
		return -1;
	}
	const auto* to = reinterpret_cast<const sockaddr_in*>(address);
	std::vector<uint8_t> message = {M_UDP_SEND, static_cast<uint8_t>(fd - FD_UDP)};
	message.reserve(8 + length);
	Put32(message, ntohl(to->sin_addr.s_addr));
	Put16(message, ntohs(to->sin_port));
	message.insert(message.end(), static_cast<const uint8_t*>(data), static_cast<const uint8_t*>(data) + length);
	Queue(std::move(message)); // a datagram with no relay to take it is lost, as on any line
	return static_cast<ssize_t>(length);
}

ssize_t rtaSockRecvFrom(int fd, void* data, size_t length, int, sockaddr* address, socklen_t* addressLength)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	UdpSock* s = Udp(fd);
	if(!s)
	{
		errno = EBADF;
		return -1;
	}
	if(s->in.empty())
	{
		errno = EAGAIN;
		return -1;
	}
	Datagram& datagram = s->in.front();
	size_t n = std::min(length, datagram.data.size());
	memcpy(data, datagram.data.data(), n);
	if(address && addressLength && *addressLength >= sizeof(sockaddr_in))
	{
		sockaddr_in from = {};
		from.sin_family = AF_INET;
		from.sin_addr.s_addr = htonl(datagram.ip);
		from.sin_port = htons(datagram.port);
		memcpy(address, &from, sizeof(from));
		*addressLength = sizeof(from);
	}
	s->in.pop_front();
	return static_cast<ssize_t>(n);
}

int rtaSockClose(int fd)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if(TcpSock* c = Tcp(fd))
	{
		if(c->state == TcpSock::CONNECTING || c->state == TcpSock::OPEN)
		{
			std::vector<uint8_t> message = {M_TCP_CLOSE};
			Put16(message, c->id);
			Queue(std::move(message));
		}
		*c = TcpSock();
		return 0;
	}
	if(UdpSock* s = Udp(fd))
	{
		Queue({M_UDP_CLOSE, static_cast<uint8_t>(fd - FD_UDP)});
		*s = UdpSock();
		return 0;
	}
	errno = EBADF;
	return -1;
}

int rtaSockShutdown(int fd, int how)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	TcpSock* c = Tcp(fd);
	if(!c)
	{
		errno = EBADF;
		return -1;
	}
	if(c->state != TcpSock::OPEN) return 0;
	std::vector<uint8_t> message = {static_cast<uint8_t>(how == SHUT_WR ? M_TCP_SHUT : M_TCP_CLOSE)};
	Put16(message, c->id);
	if(how == SHUT_WR)
	{
		if(c->shut) return 0;
		c->shut = true;
	}
	else
		c->state = TcpSock::GONE;
	Queue(std::move(message));
	return 0;
}

// Only what RtaNet.cpp asks: has a connection that was begun come about, or failed?
int rtaSockPoll(pollfd* fds, nfds_t count, int)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	int ready = 0;
	for(nfds_t i = 0; i < count; i++)
	{
		fds[i].revents = 0;
		TcpSock* c = Tcp(fds[i].fd);
		if(!c)
		{
			if(!Udp(fds[i].fd)) fds[i].revents = POLLNVAL;
		}
		else if(c->state == TcpSock::OPEN)
			fds[i].revents = static_cast<short>((fds[i].events & POLLOUT) | ((fds[i].events & POLLIN) && (!c->in.empty() || c->eof) ? POLLIN : 0));
		else if(c->state == TcpSock::FAILED || c->state == TcpSock::GONE)
			fds[i].revents = POLLERR;
		if(fds[i].revents) ready++;
	}
	return ready;
}

int rtaSockGetSockOpt(int fd, int level, int name, void* value, socklen_t* length)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if(level == SOL_SOCKET && name == SO_ERROR && value && length && *length >= sizeof(int))
	{
		int error = 0;
		if(TcpSock* c = Tcp(fd))
		{
			if(c->state == TcpSock::FAILED) error = c->error ? c->error : ECONNREFUSED;
			if(c->state == TcpSock::GONE) error = ECONNRESET;
		}
		memcpy(value, &error, sizeof(error));
		*length = sizeof(error);
		return 0;
	}
	errno = ENOPROTOOPT;
	return -1;
}

int rtaSockSetSockOpt(int, int, int, const void*, socklen_t)
{
	return 0;
}

int rtaSockGetSockName(int fd, sockaddr* address, socklen_t* length)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	UdpSock* s = Udp(fd);
	if(!s || !address || !length || *length < sizeof(sockaddr_in))
	{
		errno = EBADF;
		return -1;
	}
	sockaddr_in local = {};
	local.sin_family = AF_INET;
	local.sin_addr.s_addr = htonl(g_relayIp);
	local.sin_port = htons(s->relayPort); // 0 until the relay has said which
	memcpy(address, &local, sizeof(local));
	*length = sizeof(local);
	return 0;
}

int rtaSockFcntl(int, int, ...)
{
	return 0; // every socket here is non-blocking
}

// ---- RtaWebNet.h ------------------------------------------------------------------------

void RtaWebNet::SetPatchSet(uint32_t hash, uint16_t words)
{
	g_patchSet = hash;
	g_patchWords = words;
}

bool RtaWebNet::Configured()
{
	return g_configured;
}

void RtaWebNet::PrepareCard()
{
	if(!g_configured) return;
	auto card = CAppConfig::GetInstance().GetPreferencePath(PREF_PS2_MC0_DIRECTORY);
	int result = WriteNetcnf(card);
	if(result > 0) printf("RTA net: network setting written to the memory card in slot 1\n");
	if(result < 0) printf("RTA net: COULD NOT write the network setting to the memory card: the game will not go online\n");
}

void RtaWebNet::Attach(CPS2VM* vm)
{
	g_vm = vm;
	if(!g_configured) return;
	auto& speed = vm->m_iop->m_speed;
	speed.SetEthernetFrameTxHandler([](const uint8* frame, uint32 size) {
		if(!HaveNet()) return;
		g_net->GuestSent(frame, size);
		Pump();
	});
	// about once per millisecond of the machine's time (the IOP runs at 36.864 MHz)
	speed.SetEthernetPollHandler([]() {
		if(!g_net) return;
		g_net->Poll();
		Pump();
	},
	                             36864);
}

void RtaWebNet::OnExecutable(bool isGame)
{
	g_online.OnExecutable(isGame);
}

void RtaWebNet::OnVBlank(uint8_t* ram, uint32_t ramSize, bool isGame, uint32_t buttons)
{
	if(!g_configured) return;
	g_online.SetPlayerButtons(buttons);
	g_online.Tick(ram, ramSize, isGame);
	if((++g_vblanks % 30) == 0) TakeStats();
}

bool RtaWebNet::Driving()
{
	return g_configured && g_online.Driving();
}

uint32_t RtaWebNet::Buttons()
{
	return g_online.Buttons();
}

// ---- for the page (main thread) ---------------------------------------------------------
extern "C"
{
	// The page has a relay. 'server' is what the saved login is kept under (the relay's
	// host name) and 'serverText' the server in words; 'data' is the directory that is kept
	// in the browser's storage. Before the machine is made.
	EMSCRIPTEN_KEEPALIVE void rtaOnlineSetup(const char* server, const char* serverText, const char* data)
	{
		Rta::COnline::Setup setup;
		setup.file = std::string(data) + "/online-login";
		setup.characterFile = std::string(data) + "/online-character";
		setup.server = server;
		setup.serverText = serverText;
		setup.personPresent = true;
		setup.log = [](const std::string& line) { printf("RTA %s\n", line.c_str()); };
		setup.askName = [](const std::string& why) {
			std::lock_guard<std::mutex> lock(g_mutex);
			g_nameWhy = why;
			g_nameWanted = true;
		};
		setup.cross = 1u << PS2::CControllerInfo::CROSS;
		setup.circle = 1u << PS2::CControllerInfo::CIRCLE;
		setup.triangle = 1u << PS2::CControllerInfo::TRIANGLE;
		setup.square = 1u << PS2::CControllerInfo::SQUARE;
		setup.up = 1u << PS2::CControllerInfo::DPAD_UP;
		setup.down = 1u << PS2::CControllerInfo::DPAD_DOWN;
		setup.left = 1u << PS2::CControllerInfo::DPAD_LEFT;
		setup.right = 1u << PS2::CControllerInfo::DPAD_RIGHT;
		setup.l1 = 1u << PS2::CControllerInfo::L1;
		setup.r1 = 1u << PS2::CControllerInfo::R1;
		setup.start = 1u << PS2::CControllerInfo::START;
		g_online.Configure(setup);
		g_configured = true;
	}

	// The page's connection to the relay: 1 it is being opened, 0 it is gone.
	EMSCRIPTEN_KEEPALIVE void rtaNetLink(int opening)
	{
		std::lock_guard<std::mutex> lock(g_mutex);
		if(opening)
		{
			g_link = LINK_OPENING;
			g_wantLink = false;
			return;
		}
		// the relay's sockets went with it
		g_link = LINK_NONE;
		g_wantLink = false;
		g_out.clear();
		for(auto& c : g_tcp)
		{
			if(c.used && c.state != TcpSock::NEW) c.state = TcpSock::GONE;
		}
		for(auto& s : g_udp) s.relayPort = 0;
	}

	// The wake-up has arrived. Returns 1 when the machine wants a connection to the relay.
	EMSCRIPTEN_KEEPALIVE int rtaNetWoke()
	{
		std::lock_guard<std::mutex> lock(g_mutex);
		g_wakePosted = false;
		return (g_wantLink && g_link == LINK_NONE) ? 1 : 0;
	}

	// The next message for the relay, copied to 'buffer'; 0: none (or it does not fit).
	EMSCRIPTEN_KEEPALIVE int rtaNetTake(uint8_t* buffer, int size)
	{
		std::lock_guard<std::mutex> lock(g_mutex);
		while(!g_out.empty())
		{
			std::vector<uint8_t> message = std::move(g_out.front());
			g_out.pop_front();
			if(message.size() > static_cast<size_t>(size)) continue;
			memcpy(buffer, message.data(), message.size());
			return static_cast<int>(message.size());
		}
		return 0;
	}

	// A message from the relay.
	EMSCRIPTEN_KEEPALIVE void rtaNetGive(const uint8_t* data, int size)
	{
		if(size < 1) return;
		const uint8_t* body = data + 1;
		size_t length = static_cast<size_t>(size) - 1;
		std::lock_guard<std::mutex> lock(g_mutex);
		g_received++;
		switch(data[0])
		{
		case R_WELCOME:
			if(length < 9) return;
			g_lobbyIp = Get32(body + 1);
			g_relayIp = Get32(body + 5);
			g_link = LINK_UP;
			g_wantLink = false;
			break;
		case R_TCP_OPENED:
			if(length < 3) return;
			if(TcpSock* c = TcpById(Get16(body)))
			{
				if(c->state != TcpSock::CONNECTING) break;
				static const int errors[] = {0, EACCES, ECONNREFUSED, ETIMEDOUT, EHOSTUNREACH, EMFILE};
				c->state = (body[2] == 0) ? TcpSock::OPEN : TcpSock::FAILED;
				c->error = (body[2] < 6) ? errors[body[2]] : ECONNREFUSED;
			}
			break;
		case R_TCP_DATA:
			if(length < 2) return;
			if(TcpSock* c = TcpById(Get16(body))) c->in.insert(c->in.end(), body + 2, body + length);
			break;
		case R_TCP_EOF:
			if(length < 2) return;
			if(TcpSock* c = TcpById(Get16(body))) c->eof = true;
			break;
		case R_TCP_CLOSED:
			if(length < 2) return;
			if(TcpSock* c = TcpById(Get16(body))) c->state = TcpSock::GONE;
			break;
		case R_UDP_BOUND:
			if(length < 3 || body[0] >= MAX_UDP) return;
			g_udp[body[0]].relayPort = Get16(body + 1);
			break;
		case R_UDP_RECV:
			if(length < 7 || body[0] >= MAX_UDP) return;
			{
				UdpSock& s = g_udp[body[0]];
				if(!s.used) break;
				if(s.in.size() >= UDP_QUEUE_MAX)
				{
					s.in.pop_front();
					g_lost++;
				}
				Datagram datagram;
				datagram.ip = Get32(body + 1);
				datagram.port = Get16(body + 5);
				datagram.data.assign(body + 7, body + length);
				s.in.push_back(std::move(datagram));
			}
			break;
		default:
			break;
		}
	}

	// mode: 0 the lobby, 1 host a game (code empty: one is made), 2 join the game with the
	// code. Returns "" or what is wrong.
	EMSCRIPTEN_KEEPALIVE const char* rtaOnlineStart(int mode, const char* codeGiven, int chooseCharacter)
	{
		static std::string result;
		result.clear();
		if(!g_configured)
		{
			result = "this page has no relay to go online through";
			return result.c_str();
		}
		std::string code = codeGiven ? codeGiven : "";
		for(auto& c : code) c = static_cast<char>(toupper(static_cast<unsigned char>(c)));
		Rta::COnline::Goal goal = Rta::COnline::Goal::Lobby;
		if(mode == 1)
		{
			goal = Rta::COnline::Goal::Host;
			if(code.empty()) code = Rta::COnline::MakeCode();
		}
		else if(mode == 2)
			goal = Rta::COnline::Goal::Join;
		else
			code.clear();
		if(mode == 1 || mode == 2) result = Rta::COnline::CheckCode(code);
		if(!result.empty()) return result.c_str();
		g_nameWanted = false;
		g_online.Start(goal, code, false, chooseCharacter != 0);
		return result.c_str();
	}

	EMSCRIPTEN_KEEPALIVE void rtaOnlineStop()
	{
		g_online.Stop("stopped on request");
	}

	// Returns "" when the name was taken, else what is wrong with it.
	EMSCRIPTEN_KEEPALIVE const char* rtaOnlineName(const char* name)
	{
		static std::string result;
		result = Rta::COnline::CheckName(name ? name : "");
		if(result.empty())
		{
			g_nameWanted = false;
			g_online.GiveName(name);
		}
		return result.c_str();
	}

	EMSCRIPTEN_KEEPALIVE void rtaOnlineDeclineName()
	{
		g_nameWanted = false;
		g_online.DeclineName();
	}

	EMSCRIPTEN_KEEPALIVE int rtaOnlineForget()
	{
		return g_online.Forget() ? 1 : 0;
	}

	// Everything the page shows, as JSON. Never a password.
	EMSCRIPTEN_KEEPALIVE const char* rtaOnlineState()
	{
		std::string note = g_online.Note(), report = g_online.Report(), code = g_online.Code();
		bool active = g_online.Active(), hasLogin = g_configured && g_online.HasLogin();
		std::string name = hasLogin ? g_online.LoginName() : std::string();
		std::string character = g_configured ? g_online.LastCharacter() : std::string();
		std::lock_guard<std::mutex> lock(g_mutex);
		g_text = Format("{\"configured\":%d,\"link\":%d,\"active\":%d,\"driving\":%d,\"name_wanted\":%d,\"has_login\":%d,", g_configured ? 1 : 0, g_link, active ? 1 : 0,
		                g_online.Driving() ? 1 : 0, g_nameWanted ? 1 : 0, hasLogin ? 1 : 0);
		g_text += "\"note\":" + Json(note) + ",\"report\":" + Json(report) + ",\"code\":" + Json(code) + ",\"name_why\":" + Json(g_nameWhy) + ",\"name\":" + Json(name) + ",\"character\":" + Json(character) + ",";
		g_text += g_stats;
		g_text += Format("\"lobby\":\"%s\",\"relay\":\"%s\",\"messages_out\":%llu,\"messages_in\":%llu,\"messages_lost\":%llu,\"patch_set\":\"%08x\"}", Rta::CNet::IpText(g_lobbyIp).c_str(),
		                 Rta::CNet::IpText(g_relayIp).c_str(), static_cast<unsigned long long>(g_sent), static_cast<unsigned long long>(g_received), static_cast<unsigned long long>(g_lost), g_patchSet);
		return g_text.c_str();
	}
}
