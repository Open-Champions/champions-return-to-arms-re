// host_godot.cpp - tools/recomp/rt/host.h for a machine that lives inside another program.
//
// host_posix.cpp with one difference: quit() does not end the process.  The runtime calls
// it when the run is over (the script said quit, the game called Exit, the host asked for
// the end, something it cannot do) - on the game's thread, holding the runtime's one lock.
// Here the library is told (rtag_ended() turns true), and the calling thread stands still
// for good with the lock held, which keeps every other thread of the machine where it is.
// The host program goes on and ends when it wants to.
#include "host.h"

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
