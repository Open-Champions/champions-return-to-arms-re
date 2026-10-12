// xxh3_64.h - XXH3, 64 bits, seed 0, the default secret: the figure the emulator-based build
// names textures with (tools/play-net/README.md, "Texture dump and replacement"), so that a
// pack of replacement pictures made with that build is found by name here.
//
// Written from the published description of the algorithm (Yann Collet, xxHash 0.8, BSD
// 2-clause; https://github.com/Cyan4973/xxHash/blob/dev/doc/xxhash_spec.md), plain C++ with
// no vector instructions; little-endian hosts.  Checked against the library itself for
// every length from 0 to 2,000 bytes and some large ones (docs/issues/native-graphics.md).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace render {
namespace xxh3 {

static const uint8_t SECRET[192] = {
    0xb8, 0xfe, 0x6c, 0x39, 0x23, 0xa4, 0x4b, 0xbe, 0x7c, 0x01, 0x81, 0x2c, 0xf7, 0x21, 0xad, 0x1c, 0xde, 0xd4, 0x6d, 0xe9, 0x83, 0x90, 0x97, 0xdb,
    0x72, 0x40, 0xa4, 0xa4, 0xb7, 0xb3, 0x67, 0x1f, 0xcb, 0x79, 0xe6, 0x4e, 0xcc, 0xc0, 0xe5, 0x78, 0x82, 0x5a, 0xd0, 0x7d, 0xcc, 0xff, 0x72, 0x21,
    0xb8, 0x08, 0x46, 0x74, 0xf7, 0x43, 0x24, 0x8e, 0xe0, 0x35, 0x90, 0xe6, 0x81, 0x3a, 0x26, 0x4c, 0x3c, 0x28, 0x52, 0xbb, 0x91, 0xc3, 0x00, 0xcb,
    0x88, 0xd0, 0x65, 0x8b, 0x1b, 0x53, 0x2e, 0xa3, 0x71, 0x64, 0x48, 0x97, 0xa2, 0x0d, 0xf9, 0x4e, 0x38, 0x19, 0xef, 0x46, 0xa9, 0xde, 0xac, 0xd8,
    0xa8, 0xfa, 0x76, 0x3f, 0xe3, 0x9c, 0x34, 0x3f, 0xf9, 0xdc, 0xbb, 0xc7, 0xc7, 0x0b, 0x4f, 0x1d, 0x8a, 0x51, 0xe0, 0x4b, 0xcd, 0xb4, 0x59, 0x31,
    0xc8, 0x9f, 0x7e, 0xc9, 0xd9, 0x78, 0x73, 0x64, 0xea, 0xc5, 0xac, 0x83, 0x34, 0xd3, 0xeb, 0xc3, 0xc5, 0x81, 0xa0, 0xff, 0xfa, 0x13, 0x63, 0xeb,
    0x17, 0x0d, 0xdd, 0x51, 0xb7, 0xf0, 0xda, 0x49, 0xd3, 0x16, 0x55, 0x26, 0x29, 0xd4, 0x68, 0x9e, 0x2b, 0x16, 0xbe, 0x58, 0x7d, 0x47, 0xa1, 0xfc,
    0x8f, 0xf8, 0xb8, 0xd1, 0x7a, 0xd0, 0x31, 0xce, 0x45, 0xcb, 0x3a, 0x8f, 0x95, 0x16, 0x04, 0x28, 0xaf, 0xd7, 0xfb, 0xca, 0xbb, 0x4b, 0x40, 0x7e,
};

static const uint64_t P32_1 = 0x9E3779B1u, P32_2 = 0x85EBCA77u, P32_3 = 0xC2B2AE3Du;
static const uint64_t P64_1 = 0x9E3779B185EBCA87ull, P64_2 = 0xC2B2AE3D27D4EB4Full, P64_3 = 0x165667B19E3779F9ull, P64_4 = 0x85EBCA77C2B2AE63ull,
                      P64_5 = 0x27D4EB2F165667C5ull;
static const uint64_t MX1 = 0x165667919E3779F9ull, MX2 = 0x9FB21C651E98DF25ull;

static inline uint64_t r64(const uint8_t* p) { uint64_t v; memcpy(&v, p, 8); return v; }
static inline uint32_t r32(const uint8_t* p) { uint32_t v; memcpy(&v, p, 4); return v; }
static inline uint64_t rotl(uint64_t v, int n) { return (v << n) | (v >> (64 - n)); }
static inline uint64_t swap64(uint64_t v) { return __builtin_bswap64(v); }
static inline uint32_t swap32(uint32_t v) { return __builtin_bswap32(v); }
static inline uint64_t fold(uint64_t a, uint64_t b) {       // the two halves of the 128-bit product, xored
    __uint128_t m = (__uint128_t)a * b;
    return (uint64_t)m ^ (uint64_t)(m >> 64);
}
static inline uint64_t avalanche(uint64_t h) { h ^= h >> 37; h *= MX1; h ^= h >> 32; return h; }
static inline uint64_t avalanche64(uint64_t h) { h ^= h >> 33; h *= P64_2; h ^= h >> 29; h *= P64_3; h ^= h >> 32; return h; }
static inline uint64_t rrmxmx(uint64_t h, uint64_t length) {
    h ^= rotl(h, 49) ^ rotl(h, 24);
    h *= MX2;
    h ^= (h >> 35) + length;
    h *= MX2;
    return h ^ (h >> 28);
}
static inline uint64_t mix16(const uint8_t* p, const uint8_t* secret) { return fold(r64(p) ^ r64(secret), r64(p + 8) ^ r64(secret + 8)); }

static inline void accumulate_stripe(uint64_t* acc, const uint8_t* p, const uint8_t* secret) {
    for (int i = 0; i < 8; i++) {
        uint64_t value = r64(p + 8 * i), key = value ^ r64(secret + 8 * i);
        acc[i ^ 1] += value;
        acc[i] += (key & 0xFFFFFFFFu) * (key >> 32);
    }
}
static inline void scramble(uint64_t* acc, const uint8_t* secret) {
    for (int i = 0; i < 8; i++) {
        uint64_t a = acc[i];
        a ^= a >> 47;
        a ^= r64(secret + 8 * i);
        acc[i] = a * P32_1;
    }
}
static inline uint64_t merge(const uint64_t* acc, const uint8_t* secret, uint64_t start) {
    uint64_t h = start;
    for (int i = 0; i < 4; i++) h += fold(acc[2 * i] ^ r64(secret + 16 * i), acc[2 * i + 1] ^ r64(secret + 16 * i + 8));
    return avalanche(h);
}

static inline uint64_t hash64(const void* data, size_t length) {
    const uint8_t* p = (const uint8_t*)data;
    const uint8_t* s = SECRET;
    if (length == 0) return avalanche64(r64(s + 56) ^ r64(s + 64));
    if (length <= 3) {
        uint32_t combined = ((uint32_t)p[0] << 16) | ((uint32_t)p[length >> 1] << 24) | p[length - 1] | ((uint32_t)length << 8);
        uint64_t keyed = (uint64_t)combined ^ (uint64_t)(r32(s) ^ r32(s + 4));
        return avalanche64(keyed);
    }
    if (length <= 8) {
        uint32_t first = r32(p), last = r32(p + length - 4);
        uint64_t flip = r64(s + 8) ^ r64(s + 16);
        uint64_t keyed = ((uint64_t)last + ((uint64_t)first << 32)) ^ flip;
        return rrmxmx(keyed, length);
    }
    if (length <= 16) {
        uint64_t flip1 = r64(s + 24) ^ r64(s + 32), flip2 = r64(s + 40) ^ r64(s + 48);
        uint64_t low = r64(p) ^ flip1, high = r64(p + length - 8) ^ flip2;
        uint64_t acc = length + swap64(low) + high + fold(low, high);
        return avalanche(acc);
    }
    if (length <= 128) {
        uint64_t acc = length * P64_1;
        if (length > 32) {
            if (length > 64) {
                if (length > 96) { acc += mix16(p + 48, s + 96); acc += mix16(p + length - 64, s + 112); }
                acc += mix16(p + 32, s + 64); acc += mix16(p + length - 48, s + 80);
            }
            acc += mix16(p + 16, s + 32); acc += mix16(p + length - 32, s + 48);
        }
        acc += mix16(p, s); acc += mix16(p + length - 16, s + 16);
        return avalanche(acc);
    }
    if (length <= 240) {
        uint64_t acc = length * P64_1;
        size_t rounds = length / 16;
        for (size_t i = 0; i < 8; i++) acc += mix16(p + 16 * i, s + 16 * i);
        acc = avalanche(acc);
        for (size_t i = 8; i < rounds; i++) acc += mix16(p + 16 * i, s + 16 * (i - 8) + 3);
        acc += mix16(p + length - 16, s + 136 - 17);
        return avalanche(acc);
    }
    // long input: stripes of 64 bytes, 16 to a block, the secret read 8 bytes further each stripe
    uint64_t acc[8] = {P32_3, P64_1, P64_2, P64_3, P64_4, P32_2, P64_5, P32_1};
    const size_t stripes_per_block = (192 - 64) / 8, block = 64 * stripes_per_block;
    size_t blocks = (length - 1) / block;
    for (size_t b = 0; b < blocks; b++) {
        for (size_t n = 0; n < stripes_per_block; n++) accumulate_stripe(acc, p + b * block + n * 64, s + n * 8);
        scramble(acc, s + 192 - 64);
    }
    size_t stripes = ((length - 1) - block * blocks) / 64;
    for (size_t n = 0; n < stripes; n++) accumulate_stripe(acc, p + blocks * block + n * 64, s + n * 8);
    accumulate_stripe(acc, p + length - 64, s + 192 - 64 - 7);
    return merge(acc, s + 11, (uint64_t)length * P64_1);
}

}  // namespace xxh3
}  // namespace render
