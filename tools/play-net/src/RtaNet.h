// A small user-space network for the emulated PlayStation 2 Ethernet adaptor.
//
// The emulated machine is alone on a made-up network with this code as its gateway. It is
// given an address by DHCP, gets one host name answered by DNS (the lobby server's), and
// everything it then sends is carried through ordinary sockets of the host:
//
//   TCP   ended here (the machine only ever opens connections) and carried on a host TCP
//         connection to the real destination;
//   UDP   one host socket per UDP port of the machine. Whatever the machine sends from
//         that port leaves from that one socket, whoever it is for, and whatever arrives
//         on the socket goes to that port. That is the behaviour of a "full cone" router,
//         which is what the game's hole punching wants: the lobby server sees the same
//         address and port for the socket as the other players have to send to.
//
// It is a port of the network in tools/rig/rig.cpp (the "Ether..." functions), which
// relays to one host only; this one reaches real remote hosts.
//
// Nothing here depends on the emulator: frames go in with GuestSent() and come out of
// TakeFrame(), and Poll() has to be called often. Everything runs on the caller's thread.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace Rta
{
	// Which arithmetic a copy's machine computes with: Play!'s own (results rounded toward
	// zero, as the console) or what a WebAssembly build computes (rounded to nearest).
	enum : uint8_t
	{
		ARITH_NATIVE = 0,
		ARITH_BROWSER = 1,
		ARITH_CAN_NATIVE = 1,  // bits of NetConfig::arithCan
		ARITH_CAN_BROWSER = 2,
	};

	struct NetConfig
	{
		// The lobby server, as the host reaches it (IPv4, host byte order).
		uint32_t serverIp = 0;
		// The address the emulated machine is told for the lobby host name. 0: serverIp.
		// It has to differ when serverIp is a loop-back address, which the machine's own
		// network stack would never put on the wire.
		uint32_t guestServerIp = 0;
		// Other addresses that mean the server: what the machine sends to one of them
		// goes to serverIp. The usual one is the server's public address, when the
		// player is on the server's own network (the server hands that address out).
		std::set<uint32_t> serverAliases;
		// Read the lobby address out of the gateway's reply and, when the server is on
		// this host or on a private network and names another address, treat that
		// address as the server as well.
		bool learnAlias = true;
		// The name the game looks up.
		std::string lobbyName = "con.soegames.net";
		// The made-up network: the machine's address, ours, and the mask.
		uint32_t guestIp = 0xC6120F0F;   // 198.18.15.15
		uint32_t gatewayIp = 0xC6120001; // 198.18.0.1
		uint32_t netmask = 0xFFFE0000;   // 198.18.0.0/15: the range set aside for test networks
		// The server's own UDP ports (the lobby's discovery port).
		std::set<uint16_t> serverUdpPorts = {10101};
		// The TCP ports on which the server answers the "where is the lobby" request.
		uint16_t gatewayPortLo = 40800, gatewayPortHi = 40817;
		// Two emulators on one host: the lobby server sees both at one address and tells
		// each to find the other there. A datagram for the server's address on a port
		// that is not the server's then goes to 127.0.0.1 on that port, where the other
		// emulator's socket is.
		bool loopbackPeers = false;
		// Give the host socket for a UDP port of the machine the same port number when
		// it is free, so that a router can be told to forward UDP 4000-4004.
		bool bindGamePorts = true;
		// The patch set of this copy, told to every other player a datagram arrives from
		// (and theirs heard): see "Which patch set the other players have" in RtaNet.cpp.
		// tellPatchSet false: nothing is sent; what arrives is still taken out and kept.
		bool tellPatchSet = false;
		uint32_t patchSet = 0;
		uint16_t patchWords = 0;
		// For tests: hand such a datagram on to the machine as well, as a copy that does
		// not know the mark would.
		bool passPatchSetOn = false;
		// The arithmetic this copy's machine can compute with, told with the patch set
		// (see "Which arithmetic the other players compute with" in RtaNet.cpp and
		// docs/issues/mixed-arithmetic.md): a browser copy can only do the browser's, a
		// desktop copy Play!'s own and - when its core has the switch - the browser's too.
		// A copy that says nothing is taken for ARITH_CAN_NATIVE.
#ifdef __EMSCRIPTEN__
		uint8_t arithCan = ARITH_CAN_BROWSER;
#else
		uint8_t arithCan = ARITH_CAN_NATIVE;
#endif
		// For tests: connections to the server's gateway port range go to this port of
		// the server's host instead (a closed one stands for a server that is not there).
		// 0: the port the machine asked for.
		uint16_t testGatewayPort = 0;
		// Every frame in either direction, as a capture file (tcpdump -r). Empty: none.
		std::string pcapPath;
		// One line per event worth knowing.
		std::function<void(const std::string&)> log;
	};

	struct NetStats
	{
		uint64_t framesFromGuest = 0, framesToGuest = 0;
		uint64_t udpToServer = 0, udpFromServer = 0, udpToPeers = 0, udpFromPeers = 0;
		uint64_t tcpConnections = 0, tcpBytesOut = 0, tcpBytesIn = 0;
		uint64_t dropped = 0;
		bool dhcpDone = false, dnsAnswered = false;
	};

	// Another player's emulator, as the relay knows it
	struct NetPeer
	{
		uint32_t ip = 0;
		uint16_t port = 0;
		bool setKnown = false;   // it has said which patch set it has
		uint32_t patchSet = 0;
		uint16_t patchWords = 0;
		bool arithKnown = false; // it has said which arithmetic it can do and does (else: Play!'s own only)
		uint8_t arithCan = ARITH_CAN_NATIVE;
		uint8_t arithNow = ARITH_NATIVE;
		int64_t heardFor = 0;    // milliseconds since its first datagram
		int64_t silentFor = 0;   // milliseconds since its last
	};

	class CNet
	{
	public:
		CNet(const NetConfig&);
		// the other players heard from (machine thread, like Poll)
		std::vector<NetPeer> Peers() const;
		// The arithmetic this copy's machine computes with now (ARITH_NATIVE at the start,
		// ARITH_BROWSER always in a browser copy); the other players are told again when it
		// changes. Any thread.
		void SetArithmetic(uint8_t now);
		uint8_t Arithmetic() const;
		~CNet();
		CNet(const CNet&) = delete;
		CNet& operator=(const CNet&) = delete;

		// a frame the emulated adaptor transmitted
		void GuestSent(const uint8_t* frame, size_t size);
		// host sockets -> frames for the machine; call about every millisecond
		void Poll();
		// frames waiting for the machine
		bool HasFrame() const
		{
			return !m_rxQueue.empty();
		}
		std::vector<uint8_t> TakeFrame();

		const NetConfig& Config() const
		{
			return m_config;
		}
		const NetStats& Stats() const
		{
			return m_stats;
		}
		// the server lost: host side of every relayed TCP connection shut (for tests)
		void DropTcp();

		static std::string IpText(uint32_t);
		static bool ParseIp(const std::string&, uint32_t&);
		static bool IsPrivate(uint32_t);
		static bool IsLoopback(uint32_t);

	private:
		struct Tcp
		{
			int fd = -1;
			uint16_t guestPort = 0, destPort = 0;
			uint32_t destIp = 0, realIp = 0;
			uint32_t receiveNext = 0;        // next sequence number expected from the machine
			uint32_t sendBase = 0;           // sequence number of toGuest[0]
			uint32_t sendNext = 0;           // next sequence number to send
			uint32_t guestWindow = 0;
			std::deque<uint8_t> toGuest;     // bytes from the host not yet acknowledged
			std::deque<uint8_t> toHost;      // bytes from the machine not yet written
			bool connecting = false, synAcked = false, hostClosed = false, finSent = false, finAcked = false;
			bool guestClosed = false, guestShut = false;
			bool gateway = false, gatewayParsed = false;
			std::vector<uint8_t> head;       // the first bytes from the host, for the gateway's reply
			int64_t lastProgress = 0, started = 0;
			uint64_t bytesToHost = 0, bytesToGuest = 0;
		};
		struct UdpSocket
		{
			int fd = -1;
			uint16_t hostPort = 0;
		};

		int64_t Now() const;
		void Log(const char* format, ...) const;
		void Capture(const uint8_t* frame, size_t size);
		bool IsServer(uint32_t guestDest) const;
		void QueueFrame(std::vector<uint8_t>&&);

		void SendIp(uint8_t protocol, uint32_t sourceIp, uint32_t destIp, std::vector<uint8_t> payload, int checksumAt, bool broadcast = false);
		void SendUdp(uint32_t sourceIp, uint16_t sourcePort, uint32_t destIp, uint16_t destPort, const uint8_t* data, size_t length, bool broadcast = false);
		void OnArp(const uint8_t* frame, size_t size);
		void OnDhcp(const uint8_t* data, uint32_t length);
		void OnDns(uint32_t sourceIp, uint16_t sourcePort, uint32_t destIp, const uint8_t* data, uint32_t length);
		void OnUdp(uint16_t sourcePort, uint32_t destIp, uint16_t destPort, const uint8_t* data, uint32_t length);
		void OnTcp(uint32_t sourceIp, uint32_t destIp, const uint8_t* tcp, uint32_t length);
		void TcpSegment(Tcp&, uint8_t flags, uint32_t sequence, const uint8_t* data, size_t length, bool withMss = false);
		void TcpReset(Tcp&, const char* why);
		bool TcpFlush(Tcp&);
		void TcpGatewayReply(Tcp&);
		void CloseAllTcp(const char* why);
		void PollUdp();
		void PollTcp();

		NetConfig m_config;
		NetStats m_stats;
		FILE* m_pcap = nullptr;
		std::chrono::steady_clock::time_point m_start;
		uint8_t m_guestMac[6] = {};
		uint16_t m_ipId = 1;
		int m_tcpCount = 0;
		std::deque<std::vector<uint8_t>> m_rxQueue;
		std::map<uint16_t, UdpSocket> m_udp;      // by UDP port of the machine
		std::map<uint64_t, Tcp> m_tcp;            // by machine port, destination address and port
		// real (address, port) a datagram was sent to -> the address the machine used for
		// it, so that the answer can be shown as coming from there
		std::map<uint64_t, uint32_t> m_udpSeenAs;
		std::map<uint32_t, uint32_t> m_udpSeenAsAny; // the same by address alone, the latest
		std::set<uint64_t> m_noted;
		uint64_t m_peerOut = 0, m_peerIn = 0;
		struct Peer
		{
			int64_t firstHeard = 0, lastHeard = 0;
			uint16_t localPort = 0; // the machine's UDP port it talks to
			int told = 0;           // times our patch set was sent to it
			int oldTold = 0;        // browser copy: times it was told "obsolete" in place of the patch set (RtaNet.cpp)
			bool setKnown = false;
			uint32_t patchSet = 0;
			uint16_t patchWords = 0;
			int arithTold = 0;      // times our arithmetic was sent to it since it last changed
			uint8_t arithToldAs = 0xFF;
			int64_t arithSince = 0;
			bool arithKnown = false;
			uint8_t arithCan = ARITH_CAN_NATIVE;
			uint8_t arithNow = ARITH_NATIVE;
		};
		std::map<uint64_t, Peer> m_peers; // by address and port, as the host sees them
#ifdef __EMSCRIPTEN__
		std::atomic<uint8_t> m_arithNow{ARITH_BROWSER};
#else
		std::atomic<uint8_t> m_arithNow{ARITH_NATIVE};
#endif
	};
}
