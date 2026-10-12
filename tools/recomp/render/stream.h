// stream.h - a recorded stream of what the runtime hands its picture sink (rta::VideoSink).
//
// The renderer is a function of this stream alone, so a stream written once can be played
// back without the game, the runtime or the disc: the renderer is developed and timed
// against recordings, and a wrong picture can be reproduced from the file that showed it.
// Recordings are derived from the game: they belong under local/recomp-out/, never in the
// repository.
//
//   file    = "RTAVS1\0\0" record*
//   record  = u32 kind, u32 a, u64 b, u32 count, count * 4 bytes of payload
//
//   kind 1  vif1    payload: `count` words of one DMA transfer to VIF1
//   kind 2  vif0    likewise, VIF0
//   kind 3  gif     likewise, GIF path 3 (whole quadwords)
//   kind 4  reg     a = address, b = value                       (no payload)
//   kind 5  vblank  a = field, b = number                        (no payload)
//   kind 6  frame   a = buffer, b = number                       (no payload)
//   kind 7  vu1 data memory, words from qword `a` on (stores the CPU made directly)
//   kind 8  vu1 microprogram memory, words from byte offset `a` on
//   kind 9  main memory, words from address `a` on (all of it once, then the texture headers
//           whose block field changed: see Recorder)
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace render {

enum StreamKind : uint32_t { SK_VIF1 = 1, SK_VIF0, SK_GIF, SK_REG, SK_VBLANK, SK_FRAME, SK_VU1DATA, SK_VU1MICRO, SK_RAM };

struct StreamWriter {
    FILE* file = nullptr;
    bool open(const char* path) {
        file = fopen(path, "wb");
        if (file) fwrite("RTAVS1\0\0", 1, 8, file);
        return file != nullptr;
    }
    void put(uint32_t kind, uint32_t a, uint64_t b, const uint32_t* words, size_t count) {
        if (!file) return;
        uint32_t head[5] = {kind, a, (uint32_t)b, (uint32_t)(b >> 32), (uint32_t)count};
        fwrite(head, 4, 5, file);
        if (count) fwrite(words, 4, count, file);
    }
    void close() { if (file) fclose(file); file = nullptr; }
};

struct StreamReader {
    FILE* file = nullptr;
    uint32_t kind = 0, a = 0;
    uint64_t b = 0;
    std::vector<uint32_t> words;
    bool open(const char* path) {
        file = fopen(path, "rb");
        char magic[8];
        return file && fread(magic, 1, 8, file) == 8 && !memcmp(magic, "RTAVS1\0\0", 8);
    }
    bool next() {
        uint32_t head[5];
        if (!file || fread(head, 4, 5, file) != 5) return false;
        kind = head[0]; a = head[1]; b = head[2] | (uint64_t)head[3] << 32;
        words.resize(head[4]);
        return !head[4] || fread(words.data(), 4, head[4], file) == head[4];
    }
    void rewind_to_start() { if (file) fseek(file, 8, SEEK_SET); }
    void close() { if (file) fclose(file); file = nullptr; }
};

}  // namespace render
