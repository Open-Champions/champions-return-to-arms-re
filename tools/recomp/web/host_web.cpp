// host_web.cpp - host.h (tools/recomp/rt) for WebAssembly built with Emscripten: node for
// the headless runs and a browser page for the picture.  Linked in place of host_posix.cpp.
//
// Threads.  A guest thread is a host thread here as everywhere: a pthread, which Emscripten
// runs as a worker on the one shared memory.  The 256 MB of stack the runtime asks for are
// address space on a desktop; in WebAssembly they would be real linear memory, and they are
// not needed: the stack named here is only the part of a frame whose address is taken (the
// "shadow stack"), the rest lives on the engine's own stack, whose size a page cannot
// set.  RTA_WEB_STACK (bytes) is what a guest thread gets.
//
// The disc image.  node: the file itself (-sNODERAWFS).  Page: the image stays where the
// player has it.  A read is handed to the page's main thread, which asks the reader the
// page installed (Module.rtaDisc: a File the player picked, or - developer tests only - a
// URL of the local server read by range requests), copies the answer into the caller's
// buffer and wakes the caller.  Nothing of the image is kept or sent anywhere.
#include "host.h"

#include <emscripten.h>
#include <emscripten/threading.h>
#include <pthread.h>
#include <unistd.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifndef RTA_WEB_STACK
#define RTA_WEB_STACK (2u << 20)
#endif

namespace host {

struct Start { void (*entry)(void*); void* argument; };

void start_thread(void (*entry)(void*), void* argument, size_t stack_bytes) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, stack_bytes < RTA_WEB_STACK ? stack_bytes : RTA_WEB_STACK);
    pthread_t handle;
    Start* start = new Start{entry, argument};
    int failed = pthread_create(&handle, &attr, [](void* p) -> void* {
        Start s = *(Start*)p;
        delete (Start*)p;
        s.entry(s.argument);
        return nullptr;
    }, start);
    if (failed) { fprintf(stderr, "host: no thread (%d)\n", failed); quit(3); }
    pthread_detach(handle);
    pthread_attr_destroy(&attr);
}

void quit(int code) {
    fflush(stdout);
    fflush(stderr);
#ifdef RTA_WEB_PAGE
    // the page shows that the run ended; the workers are stopped with the page
    MAIN_THREAD_EM_ASM({ if (Module.rtaEnded) Module.rtaEnded($0); }, code);
#endif
    emscripten_force_exit(code);
    for (;;) usleep(1000000);
}

#ifdef RTA_WEB_PAGE

struct BigFile { uint64_t size; };
std::atomic<uint64_t> g_disc_reads{0}, g_disc_bytes{0}, g_disc_us{0};

BigFile* big_open(const char* path) {
    (void)path;                                         // the page has one image: the one it was given
    double size = MAIN_THREAD_EM_ASM_DOUBLE({ return Module.rtaDisc ? Module.rtaDisc.size : -1; });
    if (size < 0) return nullptr;
    return new BigFile{(uint64_t)size};
}

bool big_read(BigFile* file, uint64_t offset, void* into, size_t size) {
    if (offset + size > file->size) return false;
    if (size == 0) return true;
    double t0 = emscripten_get_now();
    // on the caller's stack, in the shared memory: 0 pending, 1 done, 2 failed
    std::atomic<int32_t> state{0};
    MAIN_THREAD_ASYNC_EM_ASM({
        var into = $1; var size = $2; var flag = $3 >> 2;      // (no comma outside brackets: this is a macro argument)
        var finish = function(value) { Atomics.store(HEAP32, flag, value); Atomics.notify(HEAP32, flag); };
        Module.rtaDisc.read($0, size).then(function(bytes) {
            if (bytes.byteLength !== size) { finish(2); return; }
            HEAPU8.set(new Uint8Array(bytes), into);
            finish(1);
        }, function() { finish(2); });
    }, (double)offset, into, (int)size, &state);
    while (state.load() == 0) emscripten_futex_wait(&state, 0, 1000.0);
    g_disc_reads++;
    g_disc_bytes += size;
    g_disc_us += (uint64_t)((emscripten_get_now() - t0) * 1000.0);
    return state.load() == 1;
}

uint64_t big_size(BigFile* file) { return file->size; }

#else

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

#endif

void sleep_us(uint64_t microseconds) { usleep((useconds_t)microseconds); }

// a worker's priority is the browser's business
void interactive_threads(bool) {}

}  // namespace host
