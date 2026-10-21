// host_godot.cpp - tools/recomp/rt/host.h for a machine that lives inside another program.
//
// host_posix.cpp with one difference: quit() does not end the process.  The runtime calls
// it when the run is over (the script said quit, the game called Exit, the host asked for
// the end, something it cannot do) - on the game's thread, holding the runtime's one lock.
// Here the library is told (rtag_ended() turns true), and the calling thread stands still
// for good with the lock held, which keeps every other thread of the machine where it is.
// The host program goes on and ends when it wants to.
#include "host.h"

#ifdef _WIN32
// Windows (the library of build_lib_win.py): tools/recomp/rt/host_win32.cpp's threads, disc reads and sleep, with the
// same one difference; no exception filter of the process's own (the host program's is left in place).
#include <windows.h>
#include <mmsystem.h>
#include <process.h>

#include <cstdio>
#include <cstdlib>
#include <string>

static void (*g_on_quit)(int code);
void rtag_host_set_quit(void (*fn)(int code)) { g_on_quit = fn; }

namespace host {

struct Start { void (*entry)(void*); void* argument; };
static unsigned __stdcall thread_entry(void* p) {
    Start s = *(Start*)p;
    delete (Start*)p;
    s.entry(s.argument);
    return 0;
}
void interactive_threads(bool) {}

void start_thread(void (*entry)(void*), void* argument, size_t stack_bytes) {
    Start* start = new Start{entry, argument};
    uintptr_t handle = _beginthreadex(nullptr, (unsigned)stack_bytes, thread_entry, start, STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
    if (!handle) {
        fprintf(stderr, "host: cannot start a thread with a %u MB stack (error %lu)\n", (unsigned)(stack_bytes >> 20), GetLastError());
        quit(3);
    }
    CloseHandle((HANDLE)handle);
}

void quit(int code) {
    fflush(stdout);
    fflush(stderr);
    if (g_on_quit) g_on_quit(code);
    else TerminateProcess(GetCurrentProcess(), (UINT)code);
    for (;;) Sleep(INFINITE);
}

static std::wstring wide(const char* text) {
    int n = MultiByteToWideChar(CP_UTF8, 0, text, -1, nullptr, 0);
    std::wstring out(n > 0 ? n : 1, L'\0');
    if (n > 0) MultiByteToWideChar(CP_UTF8, 0, text, -1, &out[0], n);
    return out;
}

struct BigFile { HANDLE h; uint64_t size; };

BigFile* big_open(const char* path) {
    HANDLE h = CreateFileW(wide(path).c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                           FILE_ATTRIBUTE_NORMAL | FILE_FLAG_RANDOM_ACCESS, nullptr);
    if (h == INVALID_HANDLE_VALUE) return nullptr;
    LARGE_INTEGER size;
    if (!GetFileSizeEx(h, &size)) { CloseHandle(h); return nullptr; }
    return new BigFile{h, (uint64_t)size.QuadPart};
}
bool big_read(BigFile* file, uint64_t offset, void* into, size_t size) {
    if (offset + size > file->size) return false;
    uint8_t* to = (uint8_t*)into;
    while (size) {
        OVERLAPPED at = {};
        at.Offset = (DWORD)offset;
        at.OffsetHigh = (DWORD)(offset >> 32);
        DWORD want = size > (64u << 20) ? (64u << 20) : (DWORD)size, got = 0;
        if (!ReadFile(file->h, to, want, &got, &at) || got == 0) return false;
        to += got; offset += got; size -= got;
    }
    return true;
}
uint64_t big_size(BigFile* file) { return file->size; }

static struct Start_up { Start_up() { timeBeginPeriod(1); } } g_start_up;      // 1 ms sleeps (see host_win32.cpp)

void sleep_us(uint64_t microseconds) {
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
    static thread_local HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    if (timer) {
        LARGE_INTEGER due;
        due.QuadPart = -(LONGLONG)(microseconds * 10);
        if (SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE) && WaitForSingleObject(timer, INFINITE) == WAIT_OBJECT_0) return;
    }
    Sleep((DWORD)((microseconds + 999) / 1000));
}

}  // namespace host
#else  // POSIX

#include <pthread.h>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif
#include <unistd.h>
#include <cstdio>
#include <cstdlib>

static void (*g_on_quit)(int code);
void rtag_host_set_quit(void (*fn)(int code)) { g_on_quit = fn; }

namespace host {

struct Start { void (*entry)(void*); void* argument; };
static bool g_interactive = false;
void interactive_threads(bool on) { g_interactive = on; }

void start_thread(void (*entry)(void*), void* argument, size_t stack_bytes) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, stack_bytes);
#ifdef __APPLE__
    if (g_interactive) pthread_attr_set_qos_class_np(&attr, QOS_CLASS_USER_INTERACTIVE, 0);
#endif
    pthread_t handle;
    Start* start = new Start{entry, argument};
    pthread_create(&handle, &attr, [](void* p) -> void* {
        Start s = *(Start*)p;
        delete (Start*)p;
        s.entry(s.argument);
        return nullptr;
    }, start);
    pthread_detach(handle);
    pthread_attr_destroy(&attr);
}

void quit(int code) {
    fflush(stdout);
    fflush(stderr);
    if (g_on_quit) g_on_quit(code);
    else _exit(code);
    for (;;) pause();
}

struct BigFile { FILE* f; uint64_t size; };

BigFile* big_open(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return nullptr;
    fseeko(f, 0, SEEK_END);
    BigFile* file = new BigFile{f, (uint64_t)ftello(f)};
    return file;
}
bool big_read(BigFile* file, uint64_t offset, void* into, size_t size) {
    if (offset + size > file->size) return false;
    if (fseeko(file->f, (off_t)offset, SEEK_SET) != 0) return false;
    return fread(into, 1, size, file->f) == size;
}
uint64_t big_size(BigFile* file) { return file->size; }

void sleep_us(uint64_t microseconds) { usleep((useconds_t)microseconds); }

}  // namespace host
#endif  // _WIN32
