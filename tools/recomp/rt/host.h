// host.h - everything the runtime asks of the host operating system.
//
// The rest of the runtime is portable C++17 (the standard library, <filesystem> for the
// memory-card directory).  What the standard does not give is here, and each host has
// one small file implementing it: host_posix.cpp (macOS, Linux), host_win32.cpp (Windows).
#pragma once
#include <cstddef>
#include <cstdint>

namespace host {

// A detached thread with a stack of its own size.  Guest threads run translated code on
// host threads; the translation recurses as deep as the game does and each frame of it is
// larger than the original's, so the default stack of a std::thread is not enough.
void start_thread(void (*entry)(void*), void* argument, size_t stack_bytes);
// A windowed application asks for this once, before the game starts: the threads made by
// start_thread from then on are scheduled as the player's own (macOS: the user-interactive
// class), not as background work.  A headless run never asks.
void interactive_threads(bool on);

// End the process now, without running destructors (other threads are still inside
// translated code).
[[noreturn]] void quit(int code);

// A file larger than 2 GB, read at an offset (the disc image is a DVD).
struct BigFile;
BigFile* big_open(const char* path);
bool big_read(BigFile* file, uint64_t offset, void* into, size_t size);
uint64_t big_size(BigFile* file);

// Sleep; only the pacing of a windowed application uses it, never the headless runs.
void sleep_us(uint64_t microseconds);

}  // namespace host
