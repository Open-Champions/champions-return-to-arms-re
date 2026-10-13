// png_write.h - a picture as a PNG file (8-bit RGB), with the system's zlib.
#pragma once
#include <cstdint>
#include <cstdio>
#include <vector>
#include <zlib.h>

namespace png_write {

inline void chunk(FILE* f, const char* type, const uint8_t* data, uint32_t size) {
    uint8_t head[8] = {(uint8_t)(size >> 24), (uint8_t)(size >> 16), (uint8_t)(size >> 8), (uint8_t)size,
                       (uint8_t)type[0], (uint8_t)type[1], (uint8_t)type[2], (uint8_t)type[3]};
    fwrite(head, 1, 8, f);
    if (size) fwrite(data, 1, size, f);
    uint32_t crc = (uint32_t)crc32(0, head + 4, 4);
    if (size) crc = (uint32_t)crc32(crc, data, size);
    uint8_t tail[4] = {(uint8_t)(crc >> 24), (uint8_t)(crc >> 16), (uint8_t)(crc >> 8), (uint8_t)crc};
    fwrite(tail, 1, 4, f);
}

// rows top to bottom, four bytes a pixel; the alpha is not written
inline bool rgb_from_rgba(const char* path, const uint8_t* rgba, int width, int height) {
    if (width <= 0 || height <= 0) return false;
    std::vector<uint8_t> raw((size_t)height * (1 + (size_t)width * 3));
    size_t at = 0;
    for (int y = 0; y < height; y++) {
        raw[at++] = 0;                              // filter: none
        const uint8_t* row = rgba + (size_t)y * width * 4;
        for (int x = 0; x < width; x++) { raw[at++] = row[x * 4]; raw[at++] = row[x * 4 + 1]; raw[at++] = row[x * 4 + 2]; }
    }
    uLongf packed_size = compressBound((uLong)raw.size());
    std::vector<uint8_t> packed(packed_size);
    if (compress2(packed.data(), &packed_size, raw.data(), (uLong)raw.size(), 1) != Z_OK) return false;
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    static const uint8_t magic[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    fwrite(magic, 1, 8, f);
    uint8_t head[13] = {(uint8_t)(width >> 24), (uint8_t)(width >> 16), (uint8_t)(width >> 8), (uint8_t)width,
                        (uint8_t)(height >> 24), (uint8_t)(height >> 16), (uint8_t)(height >> 8), (uint8_t)height, 8, 2, 0, 0, 0};
    chunk(f, "IHDR", head, 13);
    chunk(f, "IDAT", packed.data(), (uint32_t)packed_size);
    chunk(f, "IEND", nullptr, 0);
    return fclose(f) == 0;
}

}  // namespace png_write
