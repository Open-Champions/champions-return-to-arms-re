// host_win32.cpp - host.h for Windows (x86-64; MinGW-w64, GCC or Clang).
//
// Written and compiled on a Mac with a cross-compiler; NOT RUN (docs/issues/native-windows.md).
// The same four things as host_posix.cpp:
//   - a guest thread: _beginthreadex with the stack size as a reservation (256 MB of
//     address space; Windows commits pages as the stack grows, the compiler's stack probes
//     (___chkstk_ms) touch them in order);
//   - the end of the process without destructors: TerminateProcess after the two standard
//     streams are flushed (ExitProcess would run DLL detach code while other threads were
//     cut off inside translated code);
//   - the disc image: a Win32 handle read at a 64-bit offset (the C library's fseek takes a
//     32-bit long here);
//   - sleep: a high-resolution waitable timer where Windows has one, else Sleep with the
//     timer period set to 1 ms.
// Paths arrive in the process's code page; the program's manifest (app/win/rta_app.manifest)
// asks for UTF-8, which Windows 10 1903 and later give.
#ifdef _WIN32
#include "host.h"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <mmsystem.h>
#include <process.h>

#include <cstdio>
#include <cstdlib>
#include <string>

namespace host {

struct Start { void (*entry)(void*); void* argument; };

static unsigned __stdcall thread_entry(void* p) {
    Start s = *(Start*)p;
    delete (Start*)p;
    s.entry(s.argument);
    return 0;
}

void interactive_threads(bool) {}                      // nothing is asked of Windows' scheduler

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
    TerminateProcess(GetCurrentProcess(), (UINT)code);
    ExitProcess((UINT)code);                            // not reached
}

static std::wstring wide(const char* text) {
    int n = MultiByteToWideChar(CP_ACP, 0, text, -1, nullptr, 0);
    std::wstring out(n > 0 ? n : 1, L'\0');
    if (n > 0) MultiByteToWideChar(CP_ACP, 0, text, -1, &out[0], n);
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
    while (size) {                                      // the offset travels with each call: no shared file position
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

// A fault nobody handles (an access outside memory, a stack that ran out): say where, so
// that a report can be matched to the program's map, instead of ending without a word.
// The offset is the address less the base the image was loaded at.
static LONG WINAPI crashed(EXCEPTION_POINTERS* info) {
    const EXCEPTION_RECORD* r = info->ExceptionRecord;
    uintptr_t base = (uintptr_t)GetModuleHandleW(nullptr), at = (uintptr_t)r->ExceptionAddress;
    fprintf(stderr, "\nhost: the program failed: exception 0x%08lx at offset 0x%llx of the image (address 0x%llx, base 0x%llx)", r->ExceptionCode,
            (unsigned long long)(at - base), (unsigned long long)at, (unsigned long long)base);
    if (r->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && r->NumberParameters >= 2)
        fprintf(stderr, "; %s address 0x%llx", r->ExceptionInformation[0] ? "writing" : "reading", (unsigned long long)r->ExceptionInformation[1]);
    if (r->ExceptionCode == EXCEPTION_STACK_OVERFLOW) fprintf(stderr, "; the stack of thread %lu ran out", GetCurrentThreadId());
    fprintf(stderr, "\n");
    fflush(stderr);
    fflush(stdout);
    return EXCEPTION_EXECUTE_HANDLER;                   // end the process
}

// The default timer period of Windows is 15.6 ms: every sleep of the pacing and of the
// sound side (std::this_thread::sleep_for included) would be that coarse.
static struct Start_up {
    Start_up() {
        timeBeginPeriod(1);
        SetUnhandledExceptionFilter(crashed);
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);    // no "has stopped working" box in front of the log
    }
} g_start_up;

void sleep_us(uint64_t microseconds) {
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
    static thread_local HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    if (timer) {
        LARGE_INTEGER due;
        due.QuadPart = -(LONGLONG)(microseconds * 10);  // relative, in 100 ns
        if (SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE) && WaitForSingleObject(timer, INFINITE) == WAIT_OBJECT_0) return;
    }
    Sleep((DWORD)((microseconds + 999) / 1000));
}

}  // namespace host
#endif  // _WIN32
