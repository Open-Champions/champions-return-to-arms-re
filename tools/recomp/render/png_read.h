// png_read.h - a PNG file as RGBA8, without a library: for the builds that have no Qt (the
// Windows program).  render/texpack.cpp reads the art pack with it when RTA_NO_QIMAGE is
// defined, and with Qt's QImage otherwise; the two must give the same bytes.
//
//   bool pngread::read_file(path, rgba, width, height)
//   bool pngread::decode(bytes, size, rgba, width, height)
//
// rgba: width x height x 4 bytes, rows top to bottom, red green blue alpha, nothing
// premultiplied.  Everything PNG 1.2 can hold is read: grey, colour, palette, with or
// without alpha, 1 to 16 bits a sample, a transparent colour (tRNS), Adam7 interlacing.
// What is not 8-bit RGBA is converted as Qt 6 converts it on the way to
// QImage::Format_RGBA8888 (so that a pack looks the same in both builds):
//   - 16-bit samples become 8-bit as (v - (v >> 8) + 128) >> 8;
//   - a palette index beyond the palette, and the transparent grey of a 2-, 4- or 8-bit
//     grey picture, become transparent black; the transparent colour of an RGB picture and
//     of a 1-bit grey picture keeps its colour with alpha 0;
//   - no gamma, colour profile or background is applied.
// Checked: every chunk's CRC up to IEND, the zlib header, the stream itself, the filter
// bytes.  As with libpng, data after the last row and a wrong Adler-32 behind complete
// picture data are not errors; a file that ends early is.
//
// The decompressor is a table-driven inflate (RFC 1951) written for this file; no code
// from zlib or any other library.  docs/issues/native-windows.md says what it was compared
// with (QImage over the whole of local/hd-pack and a set of made pictures of every kind).
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace pngread {
namespace detail {

// ---- inflate ------------------------------------------------------------------------------
struct Huffman {
    enum { FAST = 10 };
    uint16_t fast[1 << FAST];           // (symbol << 4) | length for codes of up to FAST bits; 0: longer
    uint16_t count[16];                 // codes of each length
    uint16_t symbol[288];               // symbols in the order of their codes

    // false: more codes than the lengths allow.  (Fewer is accepted: an unused code is an
    // error only when the stream has it.)
    bool build(const uint8_t* lengths, int n) {
        memset(count, 0, sizeof count);
        memset(fast, 0, sizeof fast);
        for (int k = 0; k < n; k++) count[lengths[k]]++;
        count[0] = 0;
        int left = 1;
        for (int len = 1; len < 16; len++) {
            left <<= 1;
            left -= count[len];
            if (left < 0) return false;
        }
        uint16_t offset[16];
        offset[1] = 0;
        for (int len = 1; len < 15; len++) offset[len + 1] = (uint16_t)(offset[len] + count[len]);
        for (int k = 0; k < n; k++) if (lengths[k]) symbol[offset[lengths[k]]++] = (uint16_t)k;
        // the short codes, by the bits as they arrive (a code's first bit is the lowest of the buffer)
        unsigned code = 0, index = 0;
        for (int len = 1; len <= FAST; len++) {
            for (unsigned k = 0; k < count[len]; k++, code++) {
                unsigned reversed = 0;
                for (int b = 0; b < len; b++) if (code & (1u << b)) reversed |= 1u << (len - 1 - b);
                uint16_t entry = (uint16_t)((symbol[index + k] << 4) | len);
                for (unsigned at = reversed; at < (1u << FAST); at += 1u << len) fast[at] = entry;
            }
            index += count[len];
            code <<= 1;
        }
        return true;
    }
};

struct Inflater {
    const uint8_t* in;
    size_t in_size, in_pos = 0;
    uint64_t bits = 0;
    int have = 0;                       // valid bits in `bits`
    bool starved = false;               // more bits were taken than the input has

    Inflater(const uint8_t* data, size_t size) : in(data), in_size(size) {}

    inline void fill() {
        while (have <= 56 && in_pos < in_size) { bits |= (uint64_t)in[in_pos++] << have; have += 8; }
    }
    inline unsigned take(int n) {       // n <= 16
        if (have < n) { fill(); if (have < n) { starved = true; have = n; } }
        unsigned v = (unsigned)(bits & ((1u << n) - 1));
        bits >>= n;
        have -= n;
        return v;
    }
    inline int decode(const Huffman& h) {
        if (have < 15) fill();
        unsigned entry = h.fast[bits & ((1u << Huffman::FAST) - 1)];
        if (entry) {
            int len = (int)(entry & 15);
            if (len > have) { starved = true; return -1; }
            bits >>= len;
            have -= len;
            return (int)(entry >> 4);
        }
        // a code longer than the table's bits: one bit at a time
        int code = 0, first = 0, index = 0;
        for (int len = 1; len <= 15; len++) {
            if (have < 1) { starved = true; return -1; }
            code |= (int)(bits & 1);
            bits >>= 1;
            have--;
            int n = h.count[len];
            if (code - n < first) return h.symbol[index + (code - first)];
            index += n;
            first += n;
            first <<= 1;
            code <<= 1;
        }
        return -1;
    }

    // Fills `out` (its size is what the picture needs).  0: filled, or the stream ended
    // exactly; 1: the stream ended before `out` was full; -1: the stream is damaged.
    // `stream_done` says whether the end of the stream was reached (for the Adler-32).
    int run(std::vector<uint8_t>& out, size_t& made, bool& stream_done) {
        static const uint16_t LEN_BASE[29] = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
        static const uint8_t LEN_EXTRA[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
        static const uint16_t DIST_BASE[30] = {1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577};
        static const uint8_t DIST_EXTRA[30] = {0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};
        static const uint8_t ORDER[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
        uint8_t* o = out.data();
        const size_t cap = out.size();
        size_t op = 0;
        made = 0;
        stream_done = false;
        Huffman lit, dist;
        for (;;) {
            unsigned last = take(1), type = take(2);
            if (starved) { made = op; return 1; }
            if (type == 0) {
                // stored: back to a byte boundary, then length, its complement, the bytes
                int drop = have & 7;
                bits >>= drop;
                have -= drop;
                unsigned len = take(16), nlen = take(16);
                if (starved) { made = op; return 1; }
                if ((len ^ 0xFFFF) != nlen) return -1;
                while (len && have >= 8) {      // what the bit buffer still holds
                    if (op == cap) { made = op; return 0; }
                    o[op++] = (uint8_t)bits;
                    bits >>= 8;
                    have -= 8;
                    len--;
                }
                size_t n = len;
                bool cut = false;
                if (n > in_size - in_pos) { n = in_size - in_pos; cut = true; }
                if (n > cap - op) { memcpy(o + op, in + in_pos, cap - op); made = cap; return 0; }
                memcpy(o + op, in + in_pos, n);
                op += n;
                in_pos += n;
                if (cut) { made = op; return 1; }
            } else if (type == 1 || type == 2) {
                if (type == 1) {
                    uint8_t lengths[288];
                    for (int k = 0; k < 144; k++) lengths[k] = 8;
                    for (int k = 144; k < 256; k++) lengths[k] = 9;
                    for (int k = 256; k < 280; k++) lengths[k] = 7;
                    for (int k = 280; k < 288; k++) lengths[k] = 8;
                    lit.build(lengths, 288);
                    for (int k = 0; k < 30; k++) lengths[k] = 5;
                    dist.build(lengths, 30);
                } else {
                    unsigned nlit = take(5) + 257, ndist = take(5) + 1, ncode = take(4) + 4;
                    if (starved) { made = op; return 1; }
                    if (nlit > 286 || ndist > 30) return -1;
                    uint8_t lengths[320];
                    memset(lengths, 0, sizeof lengths);
                    for (unsigned k = 0; k < ncode; k++) lengths[ORDER[k]] = (uint8_t)take(3);
                    Huffman codes;
                    if (!codes.build(lengths, 19)) return -1;
                    memset(lengths, 0, sizeof lengths);
                    for (unsigned k = 0; k < nlit + ndist;) {
                        int s = decode(codes);
                        if (s < 0) { if (starved) { made = op; return 1; } return -1; }
                        if (s < 16) { lengths[k++] = (uint8_t)s; continue; }
                        unsigned repeat, value = 0;
                        if (s == 16) { if (k == 0) return -1; value = lengths[k - 1]; repeat = 3 + take(2); }
                        else if (s == 17) repeat = 3 + take(3);
                        else repeat = 11 + take(7);
                        if (k + repeat > nlit + ndist) return -1;
                        while (repeat--) lengths[k++] = (uint8_t)value;
                    }
                    if (starved) { made = op; return 1; }
                    if (lengths[256] == 0) return -1;       // no end-of-block code
                    if (!lit.build(lengths, (int)nlit) || !dist.build(lengths + nlit, (int)ndist)) return -1;
                }
                for (;;) {
                    int s = decode(lit);
                    if (s < 256) {
                        if (s < 0) { if (starved) { made = op; return 1; } return -1; }
                        if (op == cap) { made = op; return 0; }
                        o[op++] = (uint8_t)s;
                        continue;
                    }
                    if (s == 256) break;
                    s -= 257;
                    if (s >= 29) return -1;
                    unsigned len = LEN_BASE[s] + (LEN_EXTRA[s] ? take(LEN_EXTRA[s]) : 0);
                    int d = decode(dist);
                    if (d < 0 || d >= 30) { if (starved) { made = op; return 1; } return -1; }
                    size_t back = DIST_BASE[d];
                    if (DIST_EXTRA[d]) back += take(DIST_EXTRA[d]);
                    if (starved) { made = op; return 1; }
                    if (back > op) return -1;
                    if (len > cap - op) {                   // more than the picture needs: the rest is not looked at
                        for (size_t k = op; k < cap; k++) o[k] = o[k - back];
                        made = cap;
                        return 0;
                    }
                    if (back >= len) memcpy(o + op, o + op - back, len);
                    else for (unsigned k = 0; k < len; k++) o[op + k] = o[op + k - back];
                    op += len;
                }
            } else return -1;
            if (last) break;
        }
        stream_done = true;
        made = op;
        return op == cap ? 0 : 1;
    }
};

inline uint32_t be32(const uint8_t* p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

inline uint32_t crc32(const uint8_t* data, size_t size) {
    static uint32_t table[8][256];
    static bool made = false;           // filled the same way by whoever comes first
    if (!made) {
        for (uint32_t n = 0; n < 256; n++) {
            uint32_t c = n;
            for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[0][n] = c;
        }
        for (uint32_t n = 0; n < 256; n++)
            for (int k = 1; k < 8; k++) table[k][n] = table[0][table[k - 1][n] & 255] ^ (table[k - 1][n] >> 8);
        made = true;
    }
    uint32_t c = 0xFFFFFFFFu;
    while (size >= 8) {
        uint32_t a = c ^ ((uint32_t)data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24));
        c = table[7][a & 255] ^ table[6][(a >> 8) & 255] ^ table[5][(a >> 16) & 255] ^ table[4][a >> 24] ^
            table[3][data[4]] ^ table[2][data[5]] ^ table[1][data[6]] ^ table[0][data[7]];
        data += 8;
        size -= 8;
    }
    while (size--) c = table[0][(c ^ *data++) & 255] ^ (c >> 8);
    return ~c;
}

// ---- rows ------------------------------------------------------------------------------------
// The filter of one row undone in place.  bpp: bytes from a pixel to the one before it.
inline bool unfilter(uint8_t type, uint8_t* row, const uint8_t* up, size_t n, size_t bpp) {
    switch (type) {
    case 0: return true;
    case 1:
        for (size_t k = bpp; k < n; k++) row[k] = (uint8_t)(row[k] + row[k - bpp]);
        return true;
    case 2:
        if (up) for (size_t k = 0; k < n; k++) row[k] = (uint8_t)(row[k] + up[k]);
        return true;
    case 3:
        if (up) {
            for (size_t k = 0; k < bpp && k < n; k++) row[k] = (uint8_t)(row[k] + (up[k] >> 1));
            for (size_t k = bpp; k < n; k++) row[k] = (uint8_t)(row[k] + ((row[k - bpp] + up[k]) >> 1));
        } else for (size_t k = bpp; k < n; k++) row[k] = (uint8_t)(row[k] + (row[k - bpp] >> 1));
        return true;
    case 4:
        if (up) {
            for (size_t k = 0; k < bpp && k < n; k++) row[k] = (uint8_t)(row[k] + up[k]);
            for (size_t k = bpp; k < n; k++) {
                int a = row[k - bpp], b = up[k], c = up[k - bpp];
                int p = a + b - c, pa = p > a ? p - a : a - p, pb = p > b ? p - b : b - p, pc = p > c ? p - c : c - p;
                row[k] = (uint8_t)(row[k] + ((pa <= pb && pa <= pc) ? a : (pb <= pc) ? b : c));
            }
        } else for (size_t k = bpp; k < n; k++) row[k] = (uint8_t)(row[k] + row[k - bpp]);      // Paeth with nothing above is the pixel to the left
        return true;
    default: return false;
    }
}

inline uint8_t to8(unsigned v16) { return (uint8_t)((v16 - (v16 >> 8) + 128) >> 8); }

struct Kind {
    int colour = 0, depth = 0;          // IHDR's colour type and bit depth
    const std::vector<uint8_t>* palette = nullptr;      // RGB triples
    const std::vector<uint8_t>* alpha = nullptr;        // tRNS as it is in the file (empty: none)
    bool has_key = false;
    unsigned key[3] = {0, 0, 0};        // the transparent grey (key[0]) or colour
};

// `n` pixels of one unfiltered row as RGBA8.
inline void to_rgba(const Kind& k, const uint8_t* row, size_t n, uint8_t* out) {
    auto sample = [&](size_t index) -> unsigned {        // sample `index` of a row of packed samples below 8 bits
        size_t bit = index * (size_t)k.depth;
        return (unsigned)(row[bit >> 3] >> (8 - k.depth - (int)(bit & 7))) & ((1u << k.depth) - 1);
    };
    switch (k.colour) {
    case 0:
        if (k.depth == 16) {
            for (size_t x = 0; x < n; x++, out += 4) {
                unsigned v = ((unsigned)row[2 * x] << 8) | row[2 * x + 1];
                out[0] = out[1] = out[2] = to8(v);
                out[3] = (k.has_key && v == k.key[0]) ? 0 : 255;
            }
        } else if (k.depth == 8 && !k.has_key) {
            for (size_t x = 0; x < n; x++, out += 4) { out[0] = out[1] = out[2] = row[x]; out[3] = 255; }
        } else if (k.depth == 1) {
            for (size_t x = 0; x < n; x++, out += 4) {
                unsigned v = sample(x);
                out[0] = out[1] = out[2] = v ? 255 : 0;
                out[3] = (k.has_key && v == k.key[0]) ? 0 : 255;
            }
        } else {
            unsigned top = (1u << k.depth) - 1;
            for (size_t x = 0; x < n; x++, out += 4) {
                unsigned v = k.depth == 8 ? row[x] : sample(x);
                if (k.has_key && v == k.key[0]) { out[0] = out[1] = out[2] = out[3] = 0; continue; }
                out[0] = out[1] = out[2] = (uint8_t)(v * 255 / top);
                out[3] = 255;
            }
        }
        break;
    case 2:
        if (k.depth == 16) {
            for (size_t x = 0; x < n; x++, out += 4) {
                unsigned v[3];
                for (int c = 0; c < 3; c++) { v[c] = ((unsigned)row[6 * x + 2 * c] << 8) | row[6 * x + 2 * c + 1]; out[c] = to8(v[c]); }
                out[3] = (k.has_key && v[0] == k.key[0] && v[1] == k.key[1] && v[2] == k.key[2]) ? 0 : 255;
            }
        } else {
            for (size_t x = 0; x < n; x++, out += 4) {
                out[0] = row[3 * x]; out[1] = row[3 * x + 1]; out[2] = row[3 * x + 2];
                out[3] = (k.has_key && out[0] == k.key[0] && out[1] == k.key[1] && out[2] == k.key[2]) ? 0 : 255;
            }
        }
        break;
    case 3: {
        size_t colours = k.palette->size() / 3;
        // a 1-bit picture has a table of two in Qt whatever the file's palette holds
        for (size_t x = 0; x < n; x++, out += 4) {
            unsigned v = k.depth == 8 ? row[x] : sample(x);
            if (v >= colours) { out[0] = out[1] = out[2] = out[3] = 0; continue; }
            const uint8_t* c = k.palette->data() + 3 * (size_t)v;
            out[0] = c[0]; out[1] = c[1]; out[2] = c[2];
            out[3] = v < k.alpha->size() ? (*k.alpha)[v] : 255;
        }
        break;
    }
    case 4:
        if (k.depth == 16) {
            for (size_t x = 0; x < n; x++, out += 4) {
                out[0] = out[1] = out[2] = to8(((unsigned)row[4 * x] << 8) | row[4 * x + 1]);
                out[3] = to8(((unsigned)row[4 * x + 2] << 8) | row[4 * x + 3]);
            }
        } else for (size_t x = 0; x < n; x++, out += 4) { out[0] = out[1] = out[2] = row[2 * x]; out[3] = row[2 * x + 1]; }
        break;
    default:
        if (k.depth == 16) {
            for (size_t x = 0; x < 4 * n; x++) out[x] = to8(((unsigned)row[2 * x] << 8) | row[2 * x + 1]);
        } else memcpy(out, row, 4 * n);
        break;
    }
}

}  // namespace detail

inline bool decode(const uint8_t* data, size_t size, std::vector<uint8_t>& rgba, int& width, int& height) {
    using namespace detail;
    static const uint8_t SIGNATURE[8] = {0x89, 'P', 'N', 'G', 13, 10, 26, 10};
    if (size < 8 + 25 || memcmp(data, SIGNATURE, 8) != 0) return false;
    uint32_t w = 0, h = 0;
    int interlace = 0;
    Kind kind;
    std::vector<uint8_t> palette, alpha, packed;
    const uint8_t* single = nullptr;    // the compressed data when it is one chunk (not copied)
    size_t single_size = 0, idat_chunks = 0;
    bool have_head = false, ended = false, after_idat = false;
    for (size_t at = 8; !ended;) {
        if (size - at < 12) return false;               // the file ends inside a chunk, or before IEND
        uint32_t n = be32(data + at);
        const uint8_t* type = data + at + 4;
        if (n > 0x7FFFFFFFu || size - at - 12 < n) return false;
        const uint8_t* body = data + at + 8;
        bool crc_good = crc32(type, (size_t)n + 4) == be32(body + n);
        bool critical = !(type[0] & 0x20);
        if (critical && !crc_good) return false;        // (an ancillary chunk with a wrong CRC is left out, as libpng leaves it out)
        at += 12 + (size_t)n;
        if (!have_head) {
            if (memcmp(type, "IHDR", 4) != 0 || n != 13) return false;
            w = be32(body);
            h = be32(body + 4);
            kind.depth = body[8];
            kind.colour = body[9];
            interlace = body[12];
            if (w == 0 || h == 0 || w > 0x7FFFFFFFu || h > 0x7FFFFFFFu || body[10] != 0 || body[11] != 0 || interlace > 1) return false;
            int d = kind.depth;
            bool fine = false;
            switch (kind.colour) {
            case 0: fine = d == 1 || d == 2 || d == 4 || d == 8 || d == 16; break;
            case 3: fine = d == 1 || d == 2 || d == 4 || d == 8; break;
            case 2: case 4: case 6: fine = d == 8 || d == 16; break;
            default: break;
            }
            if (!fine) return false;
            if ((uint64_t)w * h > (1ull << 30)) return false;       // 4 GB as RGBA: not a texture
            have_head = true;
        } else if (!memcmp(type, "IDAT", 4)) {
            if (kind.colour == 3 && palette.empty()) return false;
            if (idat_chunks == 0) { single = body; single_size = n; }
            else {
                if (idat_chunks == 1) packed.assign(single, single + single_size);
                packed.insert(packed.end(), body, body + n);
            }
            idat_chunks++;
            after_idat = true;
        } else if (!memcmp(type, "PLTE", 4)) {
            if (n % 3 != 0 || n > 768 || after_idat) return false;
            palette.assign(body, body + n);
        } else if (!memcmp(type, "tRNS", 4)) {
            if (!crc_good || after_idat) continue;
            if (kind.colour == 3) alpha.assign(body, body + (n > 256 ? 256 : n));
            else if (kind.colour == 0 && n >= 2) { kind.has_key = true; kind.key[0] = ((unsigned)body[0] << 8) | body[1]; }
            else if (kind.colour == 2 && n >= 6) {
                kind.has_key = true;
                for (int c = 0; c < 3; c++) kind.key[c] = ((unsigned)body[2 * c] << 8) | body[2 * c + 1];
                if (kind.depth == 8) for (int c = 0; c < 3; c++) kind.key[c] &= 0xFF;     // libpng compares the low bytes
            }
        } else if (!memcmp(type, "IEND", 4)) {
            ended = true;
        } else if (critical) return false;              // a critical chunk this reader does not know
    }
    if (!have_head || idat_chunks == 0) return false;
    if (idat_chunks > 1) { single = packed.data(); single_size = packed.size(); }
    kind.palette = &palette;
    kind.alpha = &alpha;

    // the passes: one, or Adam7's seven
    static const int X0[7] = {0, 4, 0, 2, 0, 1, 0}, Y0[7] = {0, 0, 4, 0, 2, 0, 1}, DX[7] = {8, 8, 4, 4, 2, 2, 1}, DY[7] = {8, 8, 8, 4, 4, 2, 2};
    int channels = kind.colour == 0 || kind.colour == 3 ? 1 : kind.colour == 2 ? 3 : kind.colour == 4 ? 2 : 4;
    size_t pixel_bits = (size_t)channels * (size_t)kind.depth, bpp = pixel_bits >= 8 ? pixel_bits / 8 : 1;
    struct Pass { size_t w, h, row_bytes; };
    Pass passes[7];
    int pass_count = interlace ? 7 : 1;
    size_t raw_size = 0;
    for (int p = 0; p < pass_count; p++) {
        Pass& one = passes[p];
        one.w = interlace ? ((size_t)w + DX[p] - 1 - X0[p]) / DX[p] : w;
        one.h = interlace ? ((size_t)h + DY[p] - 1 - Y0[p]) / DY[p] : h;
        if (interlace && ((size_t)w <= (size_t)X0[p] || (size_t)h <= (size_t)Y0[p])) one.w = one.h = 0;
        one.row_bytes = (one.w * pixel_bits + 7) / 8;
        if (one.w && one.h) raw_size += one.h * (one.row_bytes + 1);
    }

    // zlib: two bytes of header, the deflate stream, four bytes of Adler-32
    if (single_size < 2 || (single[0] & 15) != 8 || (single[0] >> 4) > 7 || (single[1] & 0x20) || (((unsigned)single[0] << 8) | single[1]) % 31 != 0) return false;
    std::vector<uint8_t> raw(raw_size);
    Inflater inflater(single + 2, single_size - 2);
    size_t made = 0;
    bool stream_done = false;
    if (inflater.run(raw, made, stream_done) != 0) return false;        // damaged, or not enough for the picture

    rgba.resize((size_t)w * h * 4);
    width = (int)w;
    height = (int)h;
    uint8_t* at = raw.data();
    std::vector<uint8_t> line;
    for (int p = 0; p < pass_count; p++) {
        const Pass& one = passes[p];
        if (!one.w || !one.h) continue;
        const uint8_t* up = nullptr;
        if (interlace) line.resize(one.w * 4);
        for (size_t y = 0; y < one.h; y++) {
            uint8_t* row = at + 1;
            if (!unfilter(at[0], row, up, one.row_bytes, bpp)) return false;
            if (!interlace) to_rgba(kind, row, one.w, rgba.data() + y * (size_t)w * 4);
            else {
                to_rgba(kind, row, one.w, line.data());
                uint8_t* out = rgba.data() + ((size_t)Y0[p] + y * DY[p]) * (size_t)w * 4 + (size_t)X0[p] * 4;
                for (size_t x = 0; x < one.w; x++) memcpy(out + x * DX[p] * 4, line.data() + x * 4, 4);
            }
            up = row;
            at += one.row_bytes + 1;
        }
    }
    return true;
}

inline bool read_file(const std::string& path, std::vector<uint8_t>& rgba, int& width, int& height) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) return false;
    std::vector<uint8_t> bytes;
    size_t got = 0;
    for (;;) {                          // (no seeking: a file's length as a `long` ends at 2 GB on Windows)
        if (bytes.size() - got < (1u << 16)) bytes.resize(bytes.size() < (1u << 18) ? (1u << 18) : bytes.size() * 2);
        size_t n = fread(bytes.data() + got, 1, bytes.size() - got, f);
        if (n == 0) break;
        got += n;
    }
    fclose(f);
    return decode(bytes.data(), got, rgba, width, height);
}

}  // namespace pngread
