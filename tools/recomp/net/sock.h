// sock.h - the host's sockets as the network driver (netdrv.cpp) uses them: one thin layer
// with two bodies, BSD sockets (macOS, Linux) and Winsock 2 (Windows).
//
// Everything is IPv4; addresses and ports are numbers in host byte order (192.168.1.2 is
// 0xC0A80102), as the driver holds them.  Nothing here waits: every socket is made
// non-blocking, and a call that has nothing to give says so.
//
//   start()              once per process, before anything else (Windows: WSAStartup; BSD:
//                        a write to a closed connection is an error, not a signal)
//   udp() / tcp()        a new socket, already non-blocking (tcp: without Nagle's delay)
//   bind_port, local_port, receive_buffer
//   connect()            CONNECTED, UNDER_WAY or FAILED (error() then says why);
//   connect_check()      the same three for a connection that was under way
//   send / recv          bytes moved (recv: 0 = closed by the other end), AGAIN or LOST
//   send_to / recv_from  one datagram; recv_from: its size, or AGAIN when none waits
//   readable()           something can be received (or the stream has ended) right now
//   shut()               both directions of a stream are ended
//   outside_address()    the address this computer uses toward the Internet (no packet is sent)
//   own_addresses()      every IPv4 address of this computer's interfaces
//   resolve()            dotted text or a host name -> address (this one call may wait)
//   program_dir()        the directory of the running program
//
// Where the two bodies differ in more than names:
//   - a connection under way: BSD says EINPROGRESS and is asked with poll() + SO_ERROR;
//     Winsock says WSAEWOULDBLOCK and is asked with select() - a refused connection is
//     reported in its "except" set (WSAPoll did not report it before Windows 10 2004);
//   - a datagram sent to a port nobody listens on comes back, on Windows only, as the error
//     WSAECONNRESET of a LATER recvfrom on the same socket (the ICMP answer).  The driver
//     sends to players who may not be there yet, so that report is switched off
//     (SIO_UDP_CONNRESET) and, should one still arrive, skipped;
//   - a datagram larger than the buffer: BSD gives the first part, Winsock the first part
//     and the error WSAEMSGSIZE - taken as the first part here too;
//   - Windows has no SIGPIPE and no MSG_NOSIGNAL; macOS wants SO_NOSIGPIPE per socket.
//
// The Winsock body was written and compiled on a Mac with a cross-compiler and read, NOT
// RUN (docs/issues/native-windows.md); the BSD body is what netdrv.cpp did before the
// layer existed, moved here call for call.
#pragma once
#include <cstdint>
#include <cstring>
#include <set>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <vector>
#ifdef interface            // <objbase.h> makes this a word; the driver has variables of that name
#undef interface
#endif
#ifndef SIO_UDP_CONNRESET
#define SIO_UDP_CONNRESET _WSAIOW(IOC_VENDOR, 12)
#endif
#else
#include <arpa/inet.h>
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <ifaddrs.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif
#endif

namespace sock {

#ifdef _WIN32
typedef SOCKET Handle;
const Handle NONE = INVALID_SOCKET;
#else
typedef int Handle;
const Handle NONE = -1;
#endif

enum { AGAIN = -1, LOST = -2 };                     // send, recv, recv_from
enum { FAILED = -1, UNDER_WAY = 0, CONNECTED = 1 }; // connect, connect_check

inline sockaddr_in address_of(uint32_t ip, uint16_t port) {
    sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(ip);
    a.sin_port = htons(port);
    return a;
}

#ifdef _WIN32
// ================================== Winsock 2 ==================================================

inline bool start() {
    static int state = 0;                           // 1 started, -1 could not
    if (state == 0) {
        WSADATA data;
        state = WSAStartup(MAKEWORD(2, 2), &data) == 0 ? 1 : -1;
    }
    return state == 1;
}
inline int error() { return WSAGetLastError(); }
inline std::string error_text(int code) {
    char text[256] = "";
    DWORD n = FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, (DWORD)code, 0, text, sizeof text, nullptr);
    while (n > 0 && (text[n - 1] == '\r' || text[n - 1] == '\n' || text[n - 1] == ' ' || text[n - 1] == '.')) text[--n] = 0;
    return (n ? std::string(text) + " " : std::string()) + "(Winsock error " + std::to_string(code) + ")";
}
inline void close(Handle s) { if (s != NONE) closesocket(s); }
inline void non_blocking(Handle s) { u_long on = 1; ioctlsocket(s, FIONBIO, &on); }
inline Handle udp() {
    Handle s = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s == NONE) return NONE;
    non_blocking(s);
    BOOL report = FALSE;                            // no WSAECONNRESET for datagrams nobody took
    DWORD done = 0;
    WSAIoctl(s, SIO_UDP_CONNRESET, &report, sizeof report, nullptr, 0, &done, nullptr, nullptr);
    return s;
}
inline Handle tcp() {
    Handle s = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == NONE) return NONE;
    non_blocking(s);
    BOOL one = TRUE;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, (const char*)&one, sizeof one);
    return s;
}
inline bool bind_port(Handle s, uint16_t port) {
    sockaddr_in local = address_of(0, port);
    return ::bind(s, (const sockaddr*)&local, sizeof local) == 0;
}
inline uint16_t local_port(Handle s) {
    sockaddr_in local = address_of(0, 0);
    int length = sizeof local;
    return getsockname(s, (sockaddr*)&local, &length) == 0 ? ntohs(local.sin_port) : 0;
}
inline void receive_buffer(Handle s, int bytes) { setsockopt(s, SOL_SOCKET, SO_RCVBUF, (const char*)&bytes, sizeof bytes); }

inline int connect_check(Handle s) {
    fd_set writable, failed;
    FD_ZERO(&writable);
    FD_ZERO(&failed);
    FD_SET(s, &writable);
    FD_SET(s, &failed);
    timeval none = {0, 0};
    if (select(0, nullptr, &writable, &failed, &none) <= 0) return UNDER_WAY;
    int code = 0, length = sizeof code;
    getsockopt(s, SOL_SOCKET, SO_ERROR, (char*)&code, &length);
    if (FD_ISSET(s, &failed) || code != 0) {
        WSASetLastError(code ? code : WSAECONNREFUSED);
        return FAILED;
    }
    return FD_ISSET(s, &writable) ? CONNECTED : UNDER_WAY;
}
inline int connect(Handle s, uint32_t ip, uint16_t port) {
    sockaddr_in to = address_of(ip, port);
    if (::connect(s, (const sockaddr*)&to, sizeof to) == 0) return CONNECTED;
    int code = WSAGetLastError();
    if (code == WSAEWOULDBLOCK || code == WSAEINPROGRESS || code == WSAEALREADY) return UNDER_WAY;
    if (code == WSAEISCONN) return CONNECTED;
    WSASetLastError(code);
    return FAILED;
}
inline bool readable(Handle s) {
    fd_set readers;
    FD_ZERO(&readers);
    FD_SET(s, &readers);
    timeval none = {0, 0};
    return select(0, &readers, nullptr, nullptr, &none) > 0;
}
inline int send(Handle s, const void* data, size_t size) {
    int n = ::send(s, (const char*)data, (int)size, 0);
    if (n >= 0) return n;
    int code = WSAGetLastError();
    if (code == WSAEWOULDBLOCK || code == WSAEINTR || code == WSAENOBUFS) return AGAIN;
    WSASetLastError(code);
    return LOST;
}
inline int recv(Handle s, void* into, size_t size) {
    int n = ::recv(s, (char*)into, (int)size, 0);
    if (n >= 0) return n;
    int code = WSAGetLastError();
    if (code == WSAEWOULDBLOCK || code == WSAEINTR) return AGAIN;
    WSASetLastError(code);
    return LOST;
}
inline void send_to(Handle s, const void* data, size_t size, uint32_t ip, uint16_t port) {
    sockaddr_in to = address_of(ip, port);
    ::sendto(s, (const char*)data, (int)size, 0, (const sockaddr*)&to, sizeof to);
}
inline int recv_from(Handle s, void* into, size_t capacity, uint32_t& ip, uint16_t& port) {
    for (int tries = 0; tries < 16; tries++) {
        sockaddr_in from = address_of(0, 0);
        int length = sizeof from;
        int n = ::recvfrom(s, (char*)into, (int)capacity, 0, (sockaddr*)&from, &length);
        if (n < 0) {
            int code = WSAGetLastError();
            if (code == WSAECONNRESET || code == WSAENETRESET) continue;        // the ICMP answer to something sent earlier: not a datagram
            if (code != WSAEMSGSIZE) return AGAIN;
            n = (int)capacity;                      // longer than the buffer: its first part, as BSD gives it
        }
        ip = ntohl(from.sin_addr.s_addr);
        port = ntohs(from.sin_port);
        return n;
    }
    return AGAIN;
}
inline void shut(Handle s) { shutdown(s, SD_BOTH); }

inline void own_addresses(std::set<uint32_t>& out) {
    ULONG size = 16 * 1024;
    std::vector<unsigned char> buffer;
    ULONG result = ERROR_BUFFER_OVERFLOW;
    for (int tries = 0; tries < 4 && result == ERROR_BUFFER_OVERFLOW; tries++) {
        buffer.resize(size);
        result = GetAdaptersAddresses(AF_INET, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER | GAA_FLAG_SKIP_FRIENDLY_NAME,
                                      nullptr, (IP_ADAPTER_ADDRESSES*)buffer.data(), &size);
    }
    if (result != NO_ERROR) return;
    for (IP_ADAPTER_ADDRESSES* adapter = (IP_ADAPTER_ADDRESSES*)buffer.data(); adapter; adapter = adapter->Next)
        for (IP_ADAPTER_UNICAST_ADDRESS* unicast = adapter->FirstUnicastAddress; unicast; unicast = unicast->Next) {
            const sockaddr* address = unicast->Address.lpSockaddr;
            if (address && address->sa_family == AF_INET) out.insert(ntohl(((const sockaddr_in*)address)->sin_addr.s_addr));
        }
}

inline std::string program_dir() {
    wchar_t wide[MAX_PATH * 4];
    DWORD n = GetModuleFileNameW(nullptr, wide, MAX_PATH * 4);
    if (n == 0 || n >= MAX_PATH * 4) return ".";
    char narrow[MAX_PATH * 12];
    int m = WideCharToMultiByte(CP_ACP, 0, wide, (int)n, narrow, (int)sizeof narrow, nullptr, nullptr);
    std::string path(narrow, m > 0 ? (size_t)m : 0);
    size_t slash = path.find_last_of("\\/");
    return slash == std::string::npos ? "." : path.substr(0, slash);
}

#else
// ================================== BSD sockets ================================================

inline bool start() {
    signal(SIGPIPE, SIG_IGN);
    return true;
}
inline int error() { return errno; }
inline std::string error_text(int code) { return strerror(code); }
inline void close(Handle s) { if (s != NONE) ::close(s); }
inline void non_blocking(Handle s) {
    fcntl(s, F_SETFL, fcntl(s, F_GETFL, 0) | O_NONBLOCK);
#ifdef SO_NOSIGPIPE
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof(one));
#endif
}
inline Handle udp() {
    Handle s = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (s != NONE) non_blocking(s);
    return s;
}
inline Handle tcp() {
    Handle s = ::socket(AF_INET, SOCK_STREAM, 0);
    if (s == NONE) return NONE;
    non_blocking(s);
    int one = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
    return s;
}
inline bool bind_port(Handle s, uint16_t port) {
    sockaddr_in local = address_of(0, port);
    return ::bind(s, (sockaddr*)&local, sizeof(local)) == 0;
}
inline uint16_t local_port(Handle s) {
    sockaddr_in local = address_of(0, 0);
    socklen_t length = sizeof(local);
    return getsockname(s, (sockaddr*)&local, &length) == 0 ? ntohs(local.sin_port) : 0;
}
inline void receive_buffer(Handle s, int bytes) { setsockopt(s, SOL_SOCKET, SO_RCVBUF, &bytes, sizeof(bytes)); }

inline int connect_check(Handle s) {
    pollfd p = {s, POLLOUT, 0};
    if (poll(&p, 1, 0) <= 0) return UNDER_WAY;
    int code = 0;
    socklen_t length = sizeof(code);
    getsockopt(s, SOL_SOCKET, SO_ERROR, &code, &length);
    if (code == 0 && !(p.revents & (POLLERR | POLLNVAL))) return CONNECTED;
    errno = code;
    return FAILED;
}
inline int connect(Handle s, uint32_t ip, uint16_t port) {
    sockaddr_in to = address_of(ip, port);
    if (::connect(s, (sockaddr*)&to, sizeof(to)) == 0) return CONNECTED;
    return errno == EINPROGRESS ? UNDER_WAY : FAILED;
}
inline bool readable(Handle s) {
    pollfd p = {s, POLLIN, 0};
    return poll(&p, 1, 0) > 0;
}
inline int send(Handle s, const void* data, size_t size) {
#ifdef MSG_NOSIGNAL
    ssize_t n = ::send(s, data, size, MSG_NOSIGNAL);
#else
    ssize_t n = ::send(s, data, size, 0);
#endif
    if (n >= 0) return (int)n;
    return (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) ? AGAIN : LOST;
}
inline int recv(Handle s, void* into, size_t size) {
    ssize_t n = ::recv(s, into, size, 0);
    if (n >= 0) return (int)n;
    return (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) ? AGAIN : LOST;
}
inline void send_to(Handle s, const void* data, size_t size, uint32_t ip, uint16_t port) {
    sockaddr_in to = address_of(ip, port);
    ::sendto(s, data, size, 0, (sockaddr*)&to, sizeof(to));
}
inline int recv_from(Handle s, void* into, size_t capacity, uint32_t& ip, uint16_t& port) {
    sockaddr_in from = address_of(0, 0);
    socklen_t length = sizeof(from);
    ssize_t n = ::recvfrom(s, into, capacity, 0, (sockaddr*)&from, &length);
    if (n < 0) return AGAIN;
    ip = ntohl(from.sin_addr.s_addr);
    port = ntohs(from.sin_port);
    return (int)n;
}
inline void shut(Handle s) { shutdown(s, SHUT_RDWR); }

inline void own_addresses(std::set<uint32_t>& out) {
    ifaddrs* list = nullptr;
    if (getifaddrs(&list) != 0) return;
    for (ifaddrs* i = list; i; i = i->ifa_next)
        if (i->ifa_addr && i->ifa_addr->sa_family == AF_INET) out.insert(ntohl(((sockaddr_in*)i->ifa_addr)->sin_addr.s_addr));
    freeifaddrs(list);
}

inline std::string program_dir() {
#ifdef __APPLE__
    char path[4096];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) == 0) {
        std::string text = path;
        size_t slash = text.rfind('/');
        if (slash != std::string::npos) return slash ? text.substr(0, slash) : "/";
    }
#elif defined(__linux__)
    char path[4096];
    ssize_t size = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (size > 0) {
        std::string text(path, (size_t)size);
        size_t slash = text.rfind('/');
        if (slash != std::string::npos) return slash ? text.substr(0, slash) : "/";
    }
#endif
    return ".";
}

#endif
// ================================== both ========================================================

// the address this computer uses toward the outside (a datagram socket is "connected",
// which sends nothing, and asked for its own address); 0: none, or only the loop-back one
inline uint32_t outside_address() {
    Handle s = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (s == NONE) return 0;
    sockaddr_in to = address_of(0x08080808, 53), local = address_of(0, 0);
    uint32_t found = 0;
    if (::connect(s, (const sockaddr*)&to, sizeof(to)) == 0) {
#ifdef _WIN32
        int length = sizeof(local);
#else
        socklen_t length = sizeof(local);
#endif
        if (getsockname(s, (sockaddr*)&local, &length) == 0) found = ntohl(local.sin_addr.s_addr);
    }
    close(s);
    return (found == 0 || (found >> 24) == 127) ? 0 : found;
}

// a host name's IPv4 address; false: no such name.  The only call here that may wait.
inline bool resolve(const std::string& name, uint32_t& out) {
    addrinfo hints, *found = nullptr;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(name.c_str(), nullptr, &hints, &found) != 0 || !found) return false;
    out = ntohl(((const sockaddr_in*)found->ai_addr)->sin_addr.s_addr);
    freeaddrinfo(found);
    return true;
}

}  // namespace sock
