// play-web: the sockets of tools/play-net/src/RtaNet.cpp in a browser.
//
// A page has no TCP or UDP of its own. The desktop application's network (RtaNet.cpp) is
// compiled into the browser build as it is; its socket calls - and only those - are
// carried out by the functions below (RtaWebNetCore.cpp renames them), which turn each
// into a message for the relay (tools/play-web/relay/relay.py) on the page's one
// WebSocket connection, and hand back what the relay sends. They behave as non-blocking
// sockets do, as far as RtaNet.cpp uses them:
//
//   TCP   connect() answers "in progress"; poll() and SO_ERROR say when the relay has the
//         connection (or why not); send() queues bytes; recv() gives what has arrived,
//         0 after the server's end of data, EAGAIN otherwise.
//   UDP   a socket here is a socket at the relay, kept for the session; sendto() and
//         recvfrom() carry the other side's address as the relay sees it.
//
// All of them are called on the machine's thread. Implemented in RtaWebNet.cpp.
#pragma once

#include <poll.h>
#include <sys/socket.h>
#include <sys/types.h>

int rtaSockSocket(int domain, int type, int protocol);
int rtaSockBind(int fd, const sockaddr* address, socklen_t length);
int rtaSockConnect(int fd, const sockaddr* address, socklen_t length);
ssize_t rtaSockSend(int fd, const void* data, size_t length, int flags);
ssize_t rtaSockRecv(int fd, void* data, size_t length, int flags);
ssize_t rtaSockSendTo(int fd, const void* data, size_t length, int flags, const sockaddr* address, socklen_t addressLength);
ssize_t rtaSockRecvFrom(int fd, void* data, size_t length, int flags, sockaddr* address, socklen_t* addressLength);
int rtaSockClose(int fd);
int rtaSockShutdown(int fd, int how);
int rtaSockPoll(pollfd* fds, nfds_t count, int timeout);
int rtaSockGetSockOpt(int fd, int level, int name, void* value, socklen_t* length);
int rtaSockSetSockOpt(int fd, int level, int name, const void* value, socklen_t length);
int rtaSockGetSockName(int fd, sockaddr* address, socklen_t* length);
int rtaSockFcntl(int fd, int command, ...);
