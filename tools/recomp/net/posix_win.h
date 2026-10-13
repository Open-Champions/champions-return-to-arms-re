// posix_win.h - three POSIX calls for tools/play-net/src/RtaOnline.cpp on Windows.
//
// RtaOnline.cpp (the one-step online of the emulator-based application, linked into the
// native build as it is) saves the login with open / fchmod(0600) / write / fsync / close /
// rename.  MinGW-w64 has open, write, close and unlink; it has no fchmod and no fsync, and
// its rename does not replace a file that exists.  The Windows build compiles that one file
// with "-include net/posix_win.h" (app/build_win.py) instead of changing it:
//
//   fchmod(fd, 0600)   the file gets an access list of its own, not inherited: the user who
//                      runs the program and nobody else (the login holds a password) -
//                      rta_win_private_file, in net/online_win.cpp
//   fsync(fd)          _commit(fd)
//   rename(a, b)       MoveFileEx with "replace existing" - rta_win_replace_file
//
// Every header RtaOnline.cpp includes is included here first, so the three words are only
// replaced in that file's own text.  Written and compiled on a Mac, NOT RUN.
#pragma once
#ifdef _WIN32
#include "../../play-net/src/RtaOnline.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <random>
#include <sstream>

#include <fcntl.h>
#include <io.h>
#include <sys/stat.h>
#include <unistd.h>

int rta_win_private_file(int fd);                           // always 0: a file that keeps its inherited access is still saved
int rta_win_replace_file(const char* from, const char* to); // 0, or -1

#define fchmod(fd, mode) rta_win_private_file(fd)
#define fsync(fd) _commit(fd)
#define rename(from, to) rta_win_replace_file(from, to)
#endif
