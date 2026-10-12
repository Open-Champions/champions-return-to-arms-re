// mpeg2_test.cpp - decodes an MPEG-2 video elementary stream with mpeg2.h and writes the
// pictures in display order as raw 4:2:0 planes (the form `ffmpeg -f rawvideo -pix_fmt
// yuv420p` writes), for comparing the decoder with another one.
//
//   clang++ -std=c++17 -O2 -o local/recomp-out/bin/mpeg2_test tools/recomp/app/mpeg2_test.cpp
//   local/recomp-out/bin/mpeg2_test FILE.m2v OUT.yuv [first-byte [bytes]]
//
// What it reads and writes is the game's film: keep both under local/.
#include "mpeg2.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: mpeg2_test FILE.m2v OUT.yuv [first-byte [bytes]]\n"); return 2; }
    FILE* in = fopen(argv[1], "rb");
    if (!in) { fprintf(stderr, "cannot read %s\n", argv[1]); return 1; }
    fseek(in, 0, SEEK_END);
    long size = ftell(in), first = argc > 3 ? strtol(argv[3], nullptr, 0) : 0, count = argc > 4 ? strtol(argv[4], nullptr, 0) : size - first;
    std::vector<uint8_t> data((size_t)count);
    fseek(in, first, SEEK_SET);
    if (fread(data.data(), 1, data.size(), in) != data.size()) return 1;
    fclose(in);
    FILE* out = fopen(argv[2], "wb");
    if (!out) return 1;
    mpeg2::Decoder d;
    d.feed(data.data(), data.size());
    auto t0 = std::chrono::steady_clock::now();
    int n = 0;
    char types[4096] = {0};
    while (const mpeg2::Picture* p = d.next()) {
        int w = p->mbw * 16;
        for (int y = 0; y < p->height; y++) fwrite(&p->y[(size_t)y * w], 1, p->width, out);
        for (int y = 0; y < p->height / 2; y++) fwrite(&p->cb[(size_t)y * (w / 2)], 1, p->width / 2, out);
        for (int y = 0; y < p->height / 2; y++) fwrite(&p->cr[(size_t)y * (w / 2)], 1, p->width / 2, out);
        if (n < 4095) types[n] = " IPB"[p->type & 3];
        n++;
    }
    double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    fclose(out);
    printf("%d pictures of %d x %d in %.0f ms (%.2f ms each); decoded %llu, not supported %llu, slices with errors %llu\n%s\n", n, d.width, d.height, ms,
           n ? ms / n : 0.0, (unsigned long long)d.pictures, (unsigned long long)d.unsupported, (unsigned long long)d.errors, types);
    return 0;
}
