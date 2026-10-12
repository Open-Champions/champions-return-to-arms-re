// See RtaNet.h. Ported from the network of tools/rig/rig.cpp and widened from "one
// server on this host" to real remote hosts.
#include "RtaNet.h"

#include <algorithm>
#include <cerrno>
#include <cstdarg>
#include <cstring>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

using namespace Rta;

namespace
{
	const uint8_t GATEWAY_MAC[6] = {0x02, 0x52, 0x54, 0x41, 0x00, 0x01};
	const uint8_t BROADCAST_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

	enum
	{
		GUEST_MSS = 1340,
		GUEST_WINDOW = 0x4000,
		TCP_TO_GUEST_MAX = 16384,     // bytes read from the host and not yet acknowledged
		TCP_TO_HOST_MAX = 256 * 1024, // bytes taken from the machine and not yet written
		TCP_RETRANSMIT_MS = 2000,
		TCP_CONNECT_MS = 15000,
		RX_QUEUE_MAX = 2048,
	};

	uint16_t Get16(const uint8_t* p)
	{
		return static_cast<uint16_t>((p[0] << 8) | p[1]);
	}
	uint32_t Get32(const uint8_t* p)
	{
		return (static_cast<uint32_t>(p[0]) << 24) | (static_cast<uint32_t>(p[1]) << 16) | (static_cast<uint32_t>(p[2]) << 8) | p[3];
	}
	void Put16(uint8_t* p, uint16_t v)
	{
		p[0] = static_cast<uint8_t>(v >> 8);
		p[1] = static_cast<uint8_t>(v);
	}
	void Put32(uint8_t* p, uint32_t v)
	{
		p[0] = static_cast<uint8_t>(v >> 24);
		p[1] = static_cast<uint8_t>(v >> 16);
		p[2] = static_cast<uint8_t>(v >> 8);
		p[3] = static_cast<uint8_t>(v);
	}
	uint32_t SumWords(const uint8_t* data, size_t length, uint32_t sum = 0)
	{
		for(size_t i = 0; i + 1 < length; i += 2) sum += (data[i] << 8) | data[i + 1];
		if(length & 1) sum += data[length - 1] << 8;
		return sum;
	}
	uint16_t FoldSum(uint32_t sum)
	{
		while(sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
		return static_cast<uint16_t>(~sum);
	}
	void SetNonBlocking(int fd)
	{
		fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
	}
	void NoSigPipe(int fd)
	{
#ifdef SO_NOSIGPIPE
		int on = 1;
		setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, sizeof(on));
#else
		(void)fd;
#endif
	}
#ifdef MSG_NOSIGNAL
	const int SEND_FLAGS = MSG_NOSIGNAL;
#else
	const int SEND_FLAGS = 0;
#endif
	uint64_t UdpKey(uint32_t ip, uint16_t port)
	{
		return (static_cast<uint64_t>(ip) << 16) | port;
	}
}

std::string CNet::IpText(uint32_t ip)
{
	char text[32];
	snprintf(text, sizeof(text), "%u.%u.%u.%u", ip >> 24, (ip >> 16) & 255, (ip >> 8) & 255, ip & 255);
	return text;
}

bool CNet::ParseIp(const std::string& text, uint32_t& ip)
{
	unsigned int a = 0, b = 0, c = 0, d = 0;
	char extra = 0;
	if(sscanf(text.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &extra) != 4) return false;
	if(a > 255 || b > 255 || c > 255 || d > 255) return false;
	ip = (a << 24) | (b << 16) | (c << 8) | d;
	return true;
}

bool CNet::IsLoopback(uint32_t ip)
{
	return (ip >> 24) == 127;
}

// not reachable from the Internet: the private ranges, link-local, carrier NAT
bool CNet::IsPrivate(uint32_t ip)
{
	return (ip >> 24) == 10 || (ip >> 20) == 0xAC1 || (ip >> 16) == 0xC0A8 || (ip >> 16) == 0xA9FE || (ip >> 22) == (0x64400000u >> 22) || IsLoopback(ip);
}

CNet::CNet(const NetConfig& config)
    : m_config(config)
    , m_start(std::chrono::steady_clock::now())
{
	if(m_config.guestServerIp == 0) m_config.guestServerIp = m_config.serverIp;
	if(!m_config.pcapPath.empty())
	{
		m_pcap = fopen(m_config.pcapPath.c_str(), "wb");
		if(m_pcap)
		{
			const uint32_t header[6] = {0xa1b2c3d4, 0x00040002, 0, 0, 65535, 1};
			fwrite(header, 1, sizeof(header), m_pcap);
			fflush(m_pcap);
		}
	}
}

CNet::~CNet()
{
	for(auto& entry : m_tcp)
	{
		if(entry.second.fd >= 0) close(entry.second.fd);
	}
	for(auto& entry : m_udp) close(entry.second.fd);
	if(m_pcap) fclose(m_pcap);
}

int64_t CNet::Now() const
{
	return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - m_start).count();
}

void CNet::Log(const char* format, ...) const
{
	if(!m_config.log) return;
	char text[512];
	va_list args;
	va_start(args, format);
	vsnprintf(text, sizeof(text), format, args);
	va_end(args);
	m_config.log(text);
}

void CNet::Capture(const uint8_t* frame, size_t size)
{
	if(!m_pcap) return;
	auto now = std::chrono::system_clock::now().time_since_epoch();
	auto micro = std::chrono::duration_cast<std::chrono::microseconds>(now).count();
	const uint32_t header[4] = {static_cast<uint32_t>(micro / 1000000), static_cast<uint32_t>(micro % 1000000), static_cast<uint32_t>(size), static_cast<uint32_t>(size)};
	fwrite(header, 1, sizeof(header), m_pcap);
	fwrite(frame, 1, size, m_pcap);
	fflush(m_pcap);
}

bool CNet::IsServer(uint32_t guestDest) const
{
	return guestDest == m_config.guestServerIp || m_config.serverAliases.count(guestDest) != 0;
}

void CNet::QueueFrame(std::vector<uint8_t>&& frame)
{
	if(m_rxQueue.size() >= RX_QUEUE_MAX)
	{
		// the machine is not taking frames (its driver is not running): a real wire
		// would lose them too
		m_stats.dropped++;
		return;
	}
	m_rxQueue.push_back(std::move(frame));
}

std::vector<uint8_t> CNet::TakeFrame()
{
	std::vector<uint8_t> frame = std::move(m_rxQueue.front());
	m_rxQueue.pop_front();
	Capture(frame.data(), frame.size());
	m_stats.framesToGuest++;
	// the length the driver is given includes four bytes of frame check, and it reads in
	// blocks of four
	size_t length = (std::max<size_t>(frame.size(), 60) + 4 + 3) & ~static_cast<size_t>(3);
	frame.resize(length, 0);
	return frame;
}

// ---- frames to the machine ----------------------------------------------------------

// an Ethernet + IPv4 frame; payload is the transport header and data, whose checksum
// field (at checksumAt, or none) is filled in here
void CNet::SendIp(uint8_t protocol, uint32_t sourceIp, uint32_t destIp, std::vector<uint8_t> payload, int checksumAt, bool broadcast)
{
	if(checksumAt >= 0)
	{
		uint8_t pseudo[12];
		Put32(pseudo, sourceIp);
		Put32(pseudo + 4, destIp);
		pseudo[8] = 0;
		pseudo[9] = protocol;
		Put16(pseudo + 10, static_cast<uint16_t>(payload.size()));
		Put16(&payload[checksumAt], 0);
		uint16_t sum = FoldSum(SumWords(payload.data(), payload.size(), SumWords(pseudo, 12)));
		if(protocol == 17 && sum == 0) sum = 0xFFFF;
		Put16(&payload[checksumAt], sum);
	}
	std::vector<uint8_t> frame(14 + 20 + payload.size());
	memcpy(&frame[0], broadcast ? BROADCAST_MAC : m_guestMac, 6);
	memcpy(&frame[6], GATEWAY_MAC, 6);
	Put16(&frame[12], 0x0800);
	uint8_t* ip = &frame[14];
	ip[0] = 0x45;
	Put16(ip + 2, static_cast<uint16_t>(20 + payload.size()));
	Put16(ip + 4, m_ipId++);
	ip[8] = 64;
	ip[9] = protocol;
	Put32(ip + 12, sourceIp);
	Put32(ip + 16, destIp);
	Put16(ip + 10, FoldSum(SumWords(ip, 20)));
	if(!payload.empty()) memcpy(&frame[34], payload.data(), payload.size());
	QueueFrame(std::move(frame));
}

void CNet::SendUdp(uint32_t sourceIp, uint16_t sourcePort, uint32_t destIp, uint16_t destPort, const uint8_t* data, size_t length, bool broadcast)
{
	std::vector<uint8_t> payload(8 + length);
	Put16(&payload[0], sourcePort);
	Put16(&payload[2], destPort);
	Put16(&payload[4], static_cast<uint16_t>(8 + length));
	if(length) memcpy(&payload[8], data, length);
	SendIp(17, sourceIp, destIp, std::move(payload), 6, broadcast);
}

// ---- frames from the machine --------------------------------------------------------

void CNet::GuestSent(const uint8_t* frame, size_t size)
{
	m_stats.framesFromGuest++;
	Capture(frame, size);
	if(size < 14) return;
	memcpy(m_guestMac, frame + 6, 6);
	uint16_t type = Get16(frame + 12);
	if(type == 0x0806)
	{
		OnArp(frame, size);
		return;
	}
	if(type != 0x0800 || size < 34) return;
	const uint8_t* ip = frame + 14;
	uint32_t headerLength = (ip[0] & 15) * 4, totalLength = Get16(ip + 2);
	if(headerLength < 20 || 14 + totalLength > size || totalLength < headerLength) return;
	if(Get16(ip + 6) & 0x3FFF) return; // a fragment: not handled (the game sends none)
	uint32_t sourceIp = Get32(ip + 12), destIp = Get32(ip + 16);
	const uint8_t* l4 = ip + headerLength;
	uint32_t l4Length = totalLength - headerLength;
	if(ip[9] == 1 && l4Length >= 8 && l4[0] == 8)
	{
		// ping: answered here, whoever it is for
		std::vector<uint8_t> echo(l4, l4 + l4Length);
		echo[0] = 0;
		Put16(&echo[2], 0);
		Put16(&echo[2], FoldSum(SumWords(echo.data(), echo.size())));
		SendIp(1, destIp, sourceIp, std::move(echo), -1);
	}
	else if(ip[9] == 17 && l4Length >= 8)
	{
		uint16_t sourcePort = Get16(l4), destPort = Get16(l4 + 2);
		uint32_t udpLength = std::min<uint32_t>(Get16(l4 + 4), l4Length);
		if(udpLength < 8) return;
		const uint8_t* data = l4 + 8;
		uint32_t length = udpLength - 8;
		if(destPort == 67)
			OnDhcp(data, length);
		else if(destPort == 53)
			OnDns(sourceIp, sourcePort, destIp, data, length);
		else
			OnUdp(sourcePort, destIp, destPort, data, length);
	}
	else if(ip[9] == 6 && l4Length >= 20)
	{
		OnTcp(sourceIp, destIp, l4, l4Length);
	}
}

void CNet::OnArp(const uint8_t* frame, size_t size)
{
	if(size < 42) return;
	const uint8_t* arp = frame + 14;
	uint32_t senderIp = Get32(arp + 14), targetIp = Get32(arp + 24);
	// Every address but the machine's own is "here": the gateway takes it all. The
	// machine's probe for its own address must stay unanswered.
	if(Get16(arp + 6) != 1 || targetIp == senderIp || targetIp == m_config.guestIp) return;
	std::vector<uint8_t> reply(60, 0);
	memcpy(&reply[0], frame + 6, 6);
	memcpy(&reply[6], GATEWAY_MAC, 6);
	Put16(&reply[12], 0x0806);
	Put16(&reply[14], 1);
	Put16(&reply[16], 0x0800);
	reply[18] = 6;
	reply[19] = 4;
	Put16(&reply[20], 2);
	memcpy(&reply[22], GATEWAY_MAC, 6);
	Put32(&reply[28], targetIp);
	memcpy(&reply[32], arp + 8, 6);
	Put32(&reply[38], senderIp);
	QueueFrame(std::move(reply));
}

void CNet::OnDhcp(const uint8_t* data, uint32_t length)
{
	if(length < 240 || data[0] != 1) return;
	uint8_t messageType = 0;
	for(uint32_t at = 240; at + 1 < length && data[at] != 255;)
	{
		if(data[at] == 0)
		{
			at++;
			continue;
		}
		if(data[at] == 53 && data[at + 1] >= 1 && at + 2 < length) messageType = data[at + 2];
		at += 2 + data[at + 1];
	}
	if(messageType != 1 && messageType != 3) return;
	// the machine's network is starting: whatever it had open before is gone
	if(messageType == 1) CloseAllTcp("the machine's network started again");
	std::vector<uint8_t> reply(300, 0);
	reply[0] = 2;
	reply[1] = 1;
	reply[2] = 6;
	memcpy(&reply[4], data + 4, 4);   // transaction id
	memcpy(&reply[10], data + 10, 2); // flags
	Put32(&reply[16], m_config.guestIp);
	Put32(&reply[20], m_config.gatewayIp);
	memcpy(&reply[28], data + 28, 16);
	Put32(&reply[236], 0x63825363);
	uint8_t* option = &reply[240];
	auto put = [&](uint8_t code, uint32_t value) {
		*option++ = code;
		*option++ = 4;
		Put32(option, value);
		option += 4;
	};
	*option++ = 53;
	*option++ = 1;
	*option++ = (messageType == 1) ? 2 : 5;
	put(54, m_config.gatewayIp);
	put(51, 86400);
	put(1, m_config.netmask);
	put(3, m_config.gatewayIp);
	put(6, m_config.gatewayIp);
	*option++ = 255;
	Log("DHCP %s -> %s %s", messageType == 1 ? "discover" : "request", messageType == 1 ? "offer" : "acknowledge", IpText(m_config.guestIp).c_str());
	if(messageType == 3) m_stats.dhcpDone = true;
	SendUdp(m_config.gatewayIp, 67, 0xFFFFFFFF, 68, reply.data(), reply.size(), true);
}

// One name exists: the lobby server's. Everything else "does not exist", which is also
// what keeps the game from waiting on Sony's long-gone sign-in servers.
void CNet::OnDns(uint32_t sourceIp, uint16_t sourcePort, uint32_t destIp, const uint8_t* data, uint32_t length)
{
	if(length < 17) return;
	std::string name;
	uint32_t at = 12;
	while(at < length && data[at] != 0 && data[at] < 64)
	{
		if(!name.empty()) name += '.';
		name.append(reinterpret_cast<const char*>(data + at + 1), std::min<uint32_t>(data[at], length - at - 1));
		at += 1 + data[at];
	}
	if(at + 5 > length) return;
	uint16_t queryType = Get16(data + at + 1);
	uint32_t questionEnd = at + 5;
	std::string lower = name, wanted = m_config.lobbyName;
	for(auto& c : lower) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
	for(auto& c : wanted) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
	bool known = (queryType == 1) && (lower == wanted) && m_config.guestServerIp != 0;
	std::vector<uint8_t> reply(data, data + questionEnd);
	reply[2] = 0x81;
	reply[3] = known ? 0x80 : 0x83;
	Put16(&reply[4], 1);
	Put16(&reply[6], known ? 1 : 0);
	Put16(&reply[8], 0);
	Put16(&reply[10], 0);
	if(known)
	{
		const uint8_t answer[12] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4};
		reply.insert(reply.end(), answer, answer + 12);
		uint8_t address[4];
		Put32(address, m_config.guestServerIp);
		reply.insert(reply.end(), address, address + 4);
		m_stats.dnsAnswered = true;
	}
	Log("DNS type %u for %s -> %s", queryType, name.c_str(), known ? IpText(m_config.guestServerIp).c_str() : "no such name");
	SendUdp(destIp, 53, sourceIp, sourcePort, reply.data(), reply.size());
}

// UDP: one host socket per port of the machine, for every destination.
void CNet::OnUdp(uint16_t sourcePort, uint32_t destIp, uint16_t destPort, const uint8_t* data, uint32_t length)
{
	// Addresses of the made-up network exist nowhere else. The game does send to them:
	// it tries another player's own-network address as well as the address the server
	// saw. That attempt goes nowhere, as between two houses.
	bool madeUp = (destIp & m_config.netmask) == (m_config.guestIp & m_config.netmask);
	if(madeUp || destIp == 0xFFFFFFFF || (destIp >> 28) == 0xE || destIp == 0 || IsLoopback(destIp))
	{
		m_stats.dropped++;
		if(m_noted.insert(UdpKey(destIp, destPort)).second)
			Log("UDP to %s:%u not carried (%s)", IpText(destIp).c_str(), destPort, madeUp ? "another machine's own-network address" : "not an address on the Internet");
		return;
	}
	bool toServer = IsServer(destIp);
	bool serverPort = toServer && m_config.serverUdpPorts.count(destPort) != 0;
	uint32_t realIp = toServer ? m_config.serverIp : destIp;
	// The server's address on a port that is not the server's: another emulator on the
	// server's host, which the lobby server saw at that address. It is reached through
	// the loop-back interface (a host firewall may drop datagrams between two local
	// programs on the outside address).
	if(toServer && !serverPort && m_config.loopbackPeers) realIp = INADDR_LOOPBACK;

	auto found = m_udp.find(sourcePort);
	if(found == m_udp.end())
	{
		int fd = socket(AF_INET, SOCK_DGRAM, 0);
		if(fd < 0) return;
		sockaddr_in local = {};
		local.sin_family = AF_INET;
		local.sin_port = htons(sourcePort);
		bool same = m_config.bindGamePorts && sourcePort >= 1024 && bind(fd, reinterpret_cast<sockaddr*>(&local), sizeof(local)) == 0;
		if(!same)
		{
			local.sin_port = 0;
			bind(fd, reinterpret_cast<sockaddr*>(&local), sizeof(local));
		}
		SetNonBlocking(fd);
		int size = 256 * 1024;
		setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &size, sizeof(size));
		socklen_t localLength = sizeof(local);
		getsockname(fd, reinterpret_cast<sockaddr*>(&local), &localLength);
		UdpSocket entry;
		entry.fd = fd;
		entry.hostPort = ntohs(local.sin_port);
		Log("UDP port %u of the machine is host port %u%s", sourcePort, entry.hostPort, (m_config.bindGamePorts && !same) ? " (the same number was taken)" : "");
		found = m_udp.emplace(sourcePort, entry).first;
	}
	sockaddr_in to = {};
	to.sin_family = AF_INET;
	to.sin_addr.s_addr = htonl(realIp);
	to.sin_port = htons(destPort);
	sendto(found->second.fd, data, length, 0, reinterpret_cast<sockaddr*>(&to), sizeof(to));
	if(realIp != destIp)
	{
		m_udpSeenAs[UdpKey(realIp, destPort)] = destIp;
		m_udpSeenAsAny[realIp] = destIp;
	}
	else
		m_udpSeenAs.erase(UdpKey(realIp, destPort));
	if(serverPort)
	{
		if(m_stats.udpToServer++ == 0) Log("first datagram to the server: port %u -> %s:%u (%u bytes)", sourcePort, IpText(realIp).c_str(), destPort, length);
	}
	else
	{
		m_stats.udpToPeers++;
		if(m_noted.insert(UdpKey(destIp, destPort) | (1ull << 63)).second)
			Log("first datagram to another player: port %u -> %s:%u%s (%u bytes)", sourcePort, IpText(destIp).c_str(), destPort,
			    realIp == destIp ? "" : (realIp == INADDR_LOOPBACK ? ", sent through the loop-back interface" : (", sent to " + IpText(realIp)).c_str()), length);
	}
}

void CNet::PollUdp()
{
	uint8_t buffer[2048];
	for(auto& entry : m_udp)
	{
		for(int i = 0; i < 32; i++)
		{
			sockaddr_in from = {};
			socklen_t fromLength = sizeof(from);
			ssize_t n = recvfrom(entry.second.fd, buffer, sizeof(buffer), 0, reinterpret_cast<sockaddr*>(&from), &fromLength);
			if(n < 0) break;
			uint32_t fromIp = ntohl(from.sin_addr.s_addr);
			uint16_t fromPort = ntohs(from.sin_port);
			// Shown to the machine as coming from the address it knows the sender by.
			uint32_t shownIp = fromIp;
			auto seen = m_udpSeenAs.find(UdpKey(fromIp, fromPort));
			auto seenAny = m_udpSeenAsAny.find(fromIp);
			if(seen != m_udpSeenAs.end())
				shownIp = seen->second;
			else if(seenAny != m_udpSeenAsAny.end())
				shownIp = seenAny->second; // the same host from another port (its router changed it)
			else if(IsLoopback(fromIp) || fromIp == m_config.serverIp)
				shownIp = m_config.guestServerIp; // another emulator on the server's host
			if(fromIp == m_config.serverIp && m_config.serverUdpPorts.count(fromPort))
				m_stats.udpFromServer++;
			else
			{
				m_stats.udpFromPeers++;
				if(m_noted.insert(UdpKey(fromIp, fromPort) | (1ull << 62)).second)
					Log("first datagram from another player: %s:%u -> port %u%s (%zd bytes)", IpText(fromIp).c_str(), fromPort, entry.first,
					    shownIp == fromIp ? "" : (", shown to the machine as " + IpText(shownIp)).c_str(), n);
			}
			SendUdp(shownIp, fromPort, m_config.guestIp, entry.first, buffer, static_cast<size_t>(n));
		}
	}
}

// ---- TCP, ended here ----------------------------------------------------------------
// The machine's connection is answered by this code and its bytes go through a host
// socket connected to the same address and port.

void CNet::TcpSegment(Tcp& c, uint8_t flags, uint32_t sequence, const uint8_t* data, size_t length, bool withMss)
{
	std::vector<uint8_t> segment((withMss ? 24 : 20) + length);
	Put16(&segment[0], c.destPort);
	Put16(&segment[2], c.guestPort);
	Put32(&segment[4], sequence);
	Put32(&segment[8], c.receiveNext);
	segment[12] = withMss ? 0x60 : 0x50;
	segment[13] = flags;
	Put16(&segment[14], GUEST_WINDOW);
	if(withMss)
	{
		segment[20] = 2;
		segment[21] = 4;
		Put16(&segment[22], GUEST_MSS);
	}
	if(length) memcpy(&segment[withMss ? 24 : 20], data, length);
	SendIp(6, c.destIp, m_config.guestIp, std::move(segment), 16);
}

void CNet::TcpReset(Tcp& c, const char* why)
{
	Log("TCP %u -> %s:%u reset: %s (%llu bytes out, %llu in)", c.guestPort, IpText(c.destIp).c_str(), c.destPort, why,
	    static_cast<unsigned long long>(c.bytesToHost), static_cast<unsigned long long>(c.bytesToGuest));
	TcpSegment(c, 0x14, c.sendNext, nullptr, 0);
	if(c.fd >= 0) close(c.fd);
	c.fd = -1;
}

// writes what the machine sent; false when the host side of the connection is gone
bool CNet::TcpFlush(Tcp& c)
{
	uint8_t chunk[4096];
	while(!c.toHost.empty())
	{
		size_t n = std::min(c.toHost.size(), sizeof(chunk));
		std::copy(c.toHost.begin(), c.toHost.begin() + n, chunk);
		ssize_t sent = send(c.fd, chunk, n, SEND_FLAGS);
		if(sent > 0)
		{
			c.toHost.erase(c.toHost.begin(), c.toHost.begin() + sent);
			c.bytesToHost += sent;
			m_stats.tcpBytesOut += sent;
		}
		else if(sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
			break;
		else
			return false;
	}
	return true;
}

// The first reply on a gateway connection says where the lobby is: big-endian length,
// then u16 0x43, u32 tracking number, u32 result, a counted address string, u32 port
// (docs/lobby-protocol.md, sections 2 and 5). The machine connects to that address next.
// A server at home hands out its public address; a machine on the server's own network
// often cannot reach that (the router would have to send the traffic back in), and a
// server that hands out its private address cannot be reached there from outside. In both
// cases the address the gateway was reached at is the one that works, so the named
// address is treated as the server too.
void CNet::TcpGatewayReply(Tcp& c)
{
	if(c.head.size() < 4) return;
	uint32_t frameLength = Get32(c.head.data());
	if(frameLength < 22 || frameLength > 256)
	{
		c.gatewayParsed = true;
		return;
	}
	if(c.head.size() < frameLength) return;
	c.gatewayParsed = true;
	const uint8_t* p = c.head.data() + 4;
	auto le32 = [](const uint8_t* q) { return static_cast<uint32_t>(q[0]) | (q[1] << 8) | (q[2] << 16) | (static_cast<uint32_t>(q[3]) << 24); };
	uint16_t id = static_cast<uint16_t>(p[0] | (p[1] << 8));
	uint32_t result = le32(p + 6), count = le32(p + 10);
	if(id != 0x43 || result != 0 || count > 40 || 18 + count > frameLength) return;
	std::string text(reinterpret_cast<const char*>(p + 14), count);
	uint32_t named = 0;
	if(!ParseIp(text.c_str(), named))
	{
		Log("the server names its lobby as '%s', which is not a dotted address", text.c_str());
		return;
	}
	if(IsServer(named)) return;
	bool bothPublic = !IsPrivate(named) && !IsPrivate(m_config.serverIp);
	if(!m_config.learnAlias || bothPublic)
	{
		Log("the server names its lobby as %s; connections there are made as they are", text.c_str());
		return;
	}
	m_config.serverAliases.insert(named);
	Log("the server names its lobby as %s, but it was reached at %s: from now on %s means the server", text.c_str(), IpText(m_config.serverIp).c_str(), text.c_str());
}

void CNet::OnTcp(uint32_t sourceIp, uint32_t destIp, const uint8_t* tcp, uint32_t length)
{
	(void)sourceIp;
	uint16_t sourcePort = Get16(tcp), destPort = Get16(tcp + 2);
	uint32_t sequence = Get32(tcp + 4), acknowledge = Get32(tcp + 8);
	uint32_t dataOffset = (tcp[12] >> 4) * 4;
	uint8_t flags = tcp[13];
	if(dataOffset < 20 || dataOffset > length) return;
	const uint8_t* data = tcp + dataOffset;
	uint32_t dataLength = length - dataOffset;
	uint64_t key = (static_cast<uint64_t>(sourcePort) << 48) | (static_cast<uint64_t>(destIp) << 16) | destPort;
	auto found = m_tcp.find(key);
	if(flags & 0x04) // reset
	{
		if(found != m_tcp.end())
		{
			Log("TCP %u -> %s:%u reset by the machine", sourcePort, IpText(destIp).c_str(), destPort);
			if(found->second.fd >= 0) close(found->second.fd);
			m_tcp.erase(found);
		}
		return;
	}
	if((flags & 0x12) == 0x02) // a connection request
	{
		if(found != m_tcp.end())
		{
			// the request again: answer again, unless the host side is still connecting
			if(!found->second.connecting) TcpSegment(found->second, 0x12, found->second.sendBase - 1, nullptr, 0, true);
			return;
		}
		Tcp c;
		c.guestPort = sourcePort;
		c.destPort = destPort;
		c.destIp = destIp;
		c.realIp = IsServer(destIp) ? m_config.serverIp : destIp;
		c.receiveNext = sequence + 1;
		c.guestWindow = Get16(tcp + 14);
		c.sendBase = 0x52544100 + 0x10000 * static_cast<uint32_t>(m_tcpCount++) + 1;
		c.sendNext = c.sendBase;
		c.started = c.lastProgress = Now();
		c.gateway = IsServer(destIp) && destPort >= m_config.gatewayPortLo && destPort <= m_config.gatewayPortHi;
		bool madeUp = (destIp & m_config.netmask) == (m_config.guestIp & m_config.netmask);
		int error = 0;
		if(madeUp || destIp == 0 || (destIp >> 28) >= 0xE || IsLoopback(destIp))
			error = EHOSTUNREACH;
		else
		{
			c.fd = socket(AF_INET, SOCK_STREAM, 0);
			if(c.fd < 0)
				error = errno;
			else
			{
				SetNonBlocking(c.fd);
				NoSigPipe(c.fd);
				int on = 1;
				setsockopt(c.fd, IPPROTO_TCP, TCP_NODELAY, &on, sizeof(on));
				sockaddr_in to = {};
				to.sin_family = AF_INET;
				to.sin_addr.s_addr = htonl(c.realIp);
				to.sin_port = htons((c.gateway && m_config.testGatewayPort) ? m_config.testGatewayPort : destPort);
				if(connect(c.fd, reinterpret_cast<sockaddr*>(&to), sizeof(to)) == 0)
					c.connecting = false;
				else if(errno == EINPROGRESS)
					c.connecting = true;
				else
					error = errno;
			}
		}
		if(error)
		{
			Log("TCP %u -> %s:%u refused: %s", sourcePort, IpText(destIp).c_str(), destPort, strerror(error));
			if(c.fd >= 0) close(c.fd);
			TcpSegment(c, 0x14, 0, nullptr, 0); // reset, acknowledging the request
			return;
		}
		m_stats.tcpConnections++;
		if(!c.connecting)
		{
			Log("TCP %u -> %s:%u connected%s", sourcePort, IpText(destIp).c_str(), destPort, c.realIp == destIp ? "" : (" (at " + IpText(c.realIp) + ")").c_str());
			TcpSegment(c, 0x12, c.sendBase - 1, nullptr, 0, true);
		}
		m_tcp.emplace(key, std::move(c));
		return;
	}
	if(found == m_tcp.end()) return;
	Tcp& c = found->second;
	if(c.connecting) return;
	c.guestWindow = Get16(tcp + 14);
	if(flags & 0x10)
	{
		c.synAcked = true;
		uint32_t acked = acknowledge - c.sendBase; // bytes of the buffer the machine has
		if(acked != 0 && acked <= c.sendNext - c.sendBase)
		{
			uint32_t fromBuffer = std::min<uint32_t>(acked, static_cast<uint32_t>(c.toGuest.size()));
			c.toGuest.erase(c.toGuest.begin(), c.toGuest.begin() + fromBuffer);
			c.sendBase += fromBuffer;
			if(c.finSent && acknowledge == c.sendNext) c.finAcked = true;
			c.lastProgress = Now();
		}
	}
	bool reply = false;
	if(dataLength)
	{
		if(sequence == c.receiveNext && !c.guestClosed && c.toHost.size() + dataLength <= TCP_TO_HOST_MAX)
		{
			c.toHost.insert(c.toHost.end(), data, data + dataLength);
			c.receiveNext += dataLength;
			if(!TcpFlush(c))
			{
				// the host side of the connection is gone (the server closed it): the
				// machine is told with a reset, as it would be on a real network
				TcpReset(c, "the host side is gone");
				m_tcp.erase(found);
				return;
			}
		}
		reply = true;
	}
	if((flags & 0x01) && sequence + dataLength == c.receiveNext && !c.guestClosed)
	{
		c.receiveNext += 1;
		c.guestClosed = true;
		reply = true;
		Log("TCP %u -> %s:%u closed by the machine (%llu bytes out, %llu in)", c.guestPort, IpText(c.destIp).c_str(), c.destPort,
		    static_cast<unsigned long long>(c.bytesToHost + c.toHost.size()), static_cast<unsigned long long>(c.bytesToGuest));
	}
	if(reply) TcpSegment(c, 0x10, c.sendNext, nullptr, 0);
	if(c.guestClosed && c.finAcked)
	{
		close(c.fd);
		m_tcp.erase(found);
	}
}

void CNet::PollTcp()
{
	uint8_t buffer[2048];
	int64_t now = Now();
	for(auto it = m_tcp.begin(); it != m_tcp.end();)
	{
		Tcp& c = it->second;
		if(c.connecting)
		{
			pollfd p = {c.fd, POLLOUT, 0};
			int error = 0;
			bool done = false;
			if(poll(&p, 1, 0) > 0 && (p.revents & (POLLOUT | POLLERR | POLLHUP)))
			{
				socklen_t errorLength = sizeof(error);
				if(getsockopt(c.fd, SOL_SOCKET, SO_ERROR, &error, &errorLength) != 0) error = errno;
				done = true;
			}
			else if(now - c.started > TCP_CONNECT_MS)
			{
				error = ETIMEDOUT;
				done = true;
			}
			if(done && error)
			{
				Log("TCP %u -> %s:%u refused: %s", c.guestPort, IpText(c.destIp).c_str(), c.destPort, strerror(error));
				close(c.fd);
				TcpSegment(c, 0x14, 0, nullptr, 0);
				it = m_tcp.erase(it);
				continue;
			}
			if(done)
			{
				c.connecting = false;
				c.lastProgress = now;
				Log("TCP %u -> %s:%u connected%s", c.guestPort, IpText(c.destIp).c_str(), c.destPort, c.realIp == c.destIp ? "" : (" (at " + IpText(c.realIp) + ")").c_str());
				TcpSegment(c, 0x12, c.sendBase - 1, nullptr, 0, true);
			}
			++it;
			continue;
		}
		if(!TcpFlush(c))
		{
			TcpReset(c, "the host side is gone");
			it = m_tcp.erase(it);
			continue;
		}
		if(c.guestClosed && !c.guestShut && c.toHost.empty())
		{
			shutdown(c.fd, SHUT_WR);
			c.guestShut = true;
		}
		if(c.synAcked && !c.hostClosed && c.toGuest.size() < TCP_TO_GUEST_MAX)
		{
			ssize_t n = recv(c.fd, buffer, sizeof(buffer), 0);
			if(n > 0)
			{
				c.toGuest.insert(c.toGuest.end(), buffer, buffer + n);
				m_stats.tcpBytesIn += n;
				if(c.gateway && !c.gatewayParsed)
				{
					c.head.insert(c.head.end(), buffer, buffer + n);
					TcpGatewayReply(c);
				}
			}
			else if(n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR))
				c.hostClosed = true;
		}
		// nothing acknowledged for two seconds: send again from the oldest byte
		if(c.sendNext != c.sendBase && !c.finAcked && now - c.lastProgress > TCP_RETRANSMIT_MS)
		{
			c.sendNext = c.sendBase;
			c.finSent = false;
			c.lastProgress = now;
		}
		uint32_t window = std::min<uint32_t>(c.guestWindow, 4 * GUEST_MSS);
		for(int i = 0; i < 2 && c.synAcked && !c.finSent; i++)
		{
			uint32_t offset = c.sendNext - c.sendBase;
			if(offset >= c.toGuest.size() || offset >= window) break;
			uint32_t n = std::min<uint32_t>({static_cast<uint32_t>(c.toGuest.size()) - offset, static_cast<uint32_t>(GUEST_MSS), window - offset});
			std::vector<uint8_t> piece(c.toGuest.begin() + offset, c.toGuest.begin() + offset + n);
			if(c.sendNext == c.sendBase) c.lastProgress = now; // nothing was waiting: the wait for an acknowledgement starts now
			TcpSegment(c, 0x18, c.sendNext, piece.data(), n);
			c.sendNext += n;
			c.bytesToGuest += n;
		}
		if(c.hostClosed && c.synAcked && !c.finSent && c.sendNext - c.sendBase == c.toGuest.size())
		{
			TcpSegment(c, 0x11, c.sendNext, nullptr, 0);
			c.sendNext += 1;
			c.finSent = true;
			c.lastProgress = now;
			Log("TCP %u -> %s:%u closed by the host (%llu bytes out, %llu in)", c.guestPort, IpText(c.destIp).c_str(), c.destPort,
			    static_cast<unsigned long long>(c.bytesToHost), static_cast<unsigned long long>(c.bytesToGuest));
		}
		if(c.guestClosed && c.finAcked)
		{
			close(c.fd);
			it = m_tcp.erase(it);
		}
		else
			++it;
	}
}

void CNet::CloseAllTcp(const char* why)
{
	if(m_tcp.empty()) return;
	Log("%zu TCP connection(s) closed: %s", m_tcp.size(), why);
	for(auto& entry : m_tcp)
	{
		if(entry.second.fd >= 0) close(entry.second.fd);
	}
	m_tcp.clear();
}

void CNet::DropTcp()
{
	int count = 0;
	for(auto& entry : m_tcp)
	{
		if(entry.second.fd >= 0) shutdown(entry.second.fd, SHUT_RDWR);
		count++;
	}
	Log("%d relayed TCP connection(s) dropped on the host side", count);
}

void CNet::Poll()
{
	PollTcp();
	PollUdp();
}
