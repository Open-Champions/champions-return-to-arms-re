// host_posix.cpp - host.h for macOS and Linux.
#include "host.h"

#include <pthread.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>

namespace host {

struct Start { void (*entry)(void*); void* argument; };

void start_thread(void (*entry)(void*), void* argument, size_t stack_bytes) {
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, stack_bytes);
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
    _exit(code);
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
