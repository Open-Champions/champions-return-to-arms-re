// play-web: tools/play-net/src/RtaNet.cpp, the desktop application's user-space network,
// compiled for the browser without a change. Every header it uses is taken in first;
// then its socket calls are given the names of RtaWebSock.h, which carry them to the
// relay. (build.sh copies RtaNet.cpp and RtaNet.h beside this file.)
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

#include "RtaNet.h"
#include "RtaWebSock.h"

#define socket rtaSockSocket
#define bind rtaSockBind
#define connect rtaSockConnect
#define send rtaSockSend
#define recv rtaSockRecv
#define sendto rtaSockSendTo
#define recvfrom rtaSockRecvFrom
#define close rtaSockClose
#define shutdown rtaSockShutdown
#define poll rtaSockPoll
#define getsockopt rtaSockGetSockOpt
#define setsockopt rtaSockSetSockOpt
#define getsockname rtaSockGetSockName
#define fcntl rtaSockFcntl

#include "RtaNet.cpp"
