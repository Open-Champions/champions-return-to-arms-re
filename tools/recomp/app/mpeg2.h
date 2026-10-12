// mpeg2.h - an MPEG-2 video decoder for the game's films, written from the standard
// (ISO/IEC 13818-2); standard library only, one header.
//
// What it decodes is what the films on the disc are: Main Profile elementary streams,
// 4:2:0, I, P and B pictures coded as frame pictures with frame prediction and frame DCT
// (frame_pred_frame_dct = 1), either scan, either coefficient table, both quantiser
// scales, any f_code.  What it refuses (the picture is skipped and `unsupported` counts
// it): field pictures, field or dual-prime prediction, field DCT, 4:2:2 / 4:4:4,
// concealment vectors, MPEG-1 streams' D pictures.  MPEG-1 streams otherwise decode (the
// escape and quantisation rules of MPEG-1 are followed when no sequence extension came).
//
// Use: feed() the bytes of an elementary stream (any amount; kept until reset_stream()),
// call next() for the pictures in display order until it returns nullptr.  A picture is
// three planes at macroblock-padded size.  to_rgba() converts with the colour matrix the
// console's Image Processing Unit uses (ITU-R BT.601, 16..235 to 0..255).
#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>

namespace mpeg2 {

struct Picture {
    int width = 0, height = 0;          // of the sequence
    int mbw = 0, mbh = 0;               // macroblocks
    std::vector<uint8_t> y, cb, cr;     // (mbw * 16) x (mbh * 16), and half that each way
    int type = 0;                       // 1 I, 2 P, 3 B
    int temporal_reference = 0;
};

class Decoder {
  public:
    uint64_t pictures = 0, unsupported = 0, errors = 0;
    int width = 0, height = 0;

    Decoder() { build_tables(); }

    // More of the stream.
    void feed(const uint8_t* data, size_t size) { stream.insert(stream.end(), data, data + size); }
    // Forget the stream (a new one follows); the reference pictures stay.
    void reset_stream() { stream.clear(); pos = 0; }
    // True when the stream that was fed holds no further picture and none waits to be shown.
    bool at_end() {
        if (waiting) return false;
        return !find_picture(pos);
    }

    // The next picture in display order, or nullptr at the end of what was fed.
    const Picture* next() {
        for (;;) {
            size_t at = 0;
            if (!find_picture_and_headers(at)) {
                // the end of the stream: the reference picture still held back comes out
                if (waiting) { waiting = false; return &frames[newest]; }
                return nullptr;
            }
            int type = picture_type;
            if (type == 3) {
                if (references < 2) { skip_picture(); continue; }     // a B picture without both of its references
                int target = 2;
                if (!decode_picture(target)) continue;
                pictures++;
                return &frames[target];
            }
            if (type != 1 && type != 2) { skip_picture(); unsupported++; continue; }
            if (type == 2 && references < 1) { skip_picture(); continue; }
            // an I or P picture replaces the older reference; the newer one, held back until
            // now, is the picture to show
            int target = references == 0 ? 0 : (references == 1 ? 1 - newest : 1 - newest);
            bool had_waiting = waiting;
            int shown = newest;
            if (!decode_picture(target)) continue;
            pictures++;
            newest = target;
            if (references < 2) references++;
            waiting = true;
            if (had_waiting) return &frames[shown == target ? target : shown];
        }
    }

    // RGBA (alpha 0x80) of a picture, rows top to bottom, `stride` bytes a row.
    static void to_rgba(const Picture& p, uint8_t* out, size_t stride) {
        int w = p.mbw * 16, h = p.mbh * 16;
        for (int y = 0; y < h; y++) {
            const uint8_t* ly = &p.y[(size_t)y * w];
            const uint8_t* lb = &p.cb[(size_t)(y >> 1) * (w >> 1)];
            const uint8_t* lr = &p.cr[(size_t)(y >> 1) * (w >> 1)];
            uint8_t* o = out + (size_t)y * stride;
            for (int x = 0; x < w; x++) convert(ly[x], lb[x >> 1], lr[x >> 1], o + x * 4);
        }
    }
    // One 16 x 16 macroblock as RGBA, rows top to bottom (the form the console's library
    // hands pictures over in).
    static void macroblock_rgba(const Picture& p, int mx, int my, uint8_t* out) {
        int w = p.mbw * 16;
        for (int y = 0; y < 16; y++) {
            int py = my * 16 + y;
            const uint8_t* ly = &p.y[(size_t)py * w + mx * 16];
            const uint8_t* lb = &p.cb[(size_t)(py >> 1) * (w >> 1) + mx * 8];
            const uint8_t* lr = &p.cr[(size_t)(py >> 1) * (w >> 1) + mx * 8];
            for (int x = 0; x < 16; x++) convert(ly[x], lb[x >> 1], lr[x >> 1], out + (y * 16 + x) * 4);
        }
    }

  private:
    // ---- the stream ----
    std::vector<uint8_t> stream;
    size_t pos = 0;                     // byte position of the next start code to look at
    struct Bits {
        const uint8_t* p = nullptr;
        size_t size = 0, at = 0;        // at: bit position
        uint32_t peek(int n) const {    // n <= 24
            size_t byte = at >> 3;
            uint32_t v = 0;
            for (int k = 0; k < 4; k++) v = (v << 8) | (byte + k < size ? p[byte + k] : 0);
            return (v << (at & 7)) >> (32 - n);
        }
        void skip(int n) { at += n; }
        uint32_t get(int n) { uint32_t v = n ? peek(n) : 0; at += n; return v; }
        bool end() const { return (at >> 3) >= size; }
    } bs;

    // ---- sequence and picture state ----
    bool mpeg2 = false;
    int mbw = 0, mbh = 0;
    uint8_t intra_matrix[64], inter_matrix[64];
    int picture_type = 0, temporal_reference = 0;
    int f_code[2][2] = {{15, 15}, {15, 15}};
    int full_pel[2] = {0, 0};
    int intra_dc_precision = 0, picture_structure = 3, frame_pred_frame_dct = 1, concealment = 0;
    int q_scale_type = 0, intra_vlc_format = 0, alternate_scan = 0;
    Picture frames[3];                  // two references and the B picture
    int references = 0, newest = 0;     // reference pictures held; which of frames[0..1] is the newer
    bool waiting = false;               // frames[newest] has not been shown yet

    size_t next_start(size_t from) const {
        for (size_t k = from; k + 3 < stream.size(); k++)
            if (stream[k] == 0 && stream[k + 1] == 0 && stream[k + 2] == 1) return k;
        return stream.size();
    }
    bool find_picture(size_t from) const {
        for (size_t k = next_start(from); k + 3 < stream.size(); k = next_start(k + 3))
            if (stream[k + 3] == 0x00) {
                // a whole picture is there when a slice follows the header
                for (size_t s = next_start(k + 4); s + 3 < stream.size(); s = next_start(s + 3))
                    if (stream[s + 3] >= 0x01 && stream[s + 3] <= 0xAF) return true;
                return false;
            }
        return false;
    }

    static const uint8_t* default_intra() {
        static const uint8_t m[64] = {8, 16, 19, 22, 26, 27, 29, 34, 16, 16, 22, 24, 27, 29, 34, 37, 19, 22, 26, 27, 29, 34, 34, 38,
                                      22, 22, 26, 27, 29, 34, 37, 40, 22, 26, 27, 29, 32, 35, 40, 48, 26, 27, 29, 32, 35, 40, 48, 58,
                                      26, 27, 29, 34, 38, 46, 56, 69, 27, 29, 35, 38, 46, 56, 69, 83};
        return m;
    }
    static const uint8_t* scan_table(int alternate) {
        static const uint8_t zigzag[64] = {0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
                                           35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63};
        static const uint8_t alt[64] = {0, 8, 16, 24, 1, 9, 2, 10, 17, 25, 32, 40, 48, 56, 57, 49, 41, 33, 26, 18, 3, 11, 4, 12, 19, 27, 34, 42, 50, 58, 35, 43,
                                        51, 59, 20, 28, 5, 13, 6, 14, 21, 29, 36, 44, 52, 60, 37, 45, 53, 61, 22, 30, 7, 15, 23, 31, 38, 46, 54, 62, 39, 47, 55, 63};
        return alternate ? alt : zigzag;
    }

    void sequence_header() {
        int w = (int)bs.get(12), h = (int)bs.get(12);
        bs.skip(4 + 4 + 18 + 1 + 10 + 1);
        const uint8_t* zz = scan_table(0);
        if (bs.get(1)) for (int k = 0; k < 64; k++) intra_matrix[zz[k]] = (uint8_t)bs.get(8);
        else memcpy(intra_matrix, default_intra(), 64);
        if (bs.get(1)) for (int k = 0; k < 64; k++) inter_matrix[zz[k]] = (uint8_t)bs.get(8);
        else memset(inter_matrix, 16, 64);
        if (w != width || h != height) {
            width = w; height = h;
            mbw = (w + 15) / 16; mbh = (h + 15) / 16;
            for (Picture& f : frames) {
                f.width = w; f.height = h; f.mbw = mbw; f.mbh = mbh;
                f.y.assign((size_t)mbw * 16 * mbh * 16, 16);
                f.cb.assign((size_t)mbw * 8 * mbh * 8, 128);
                f.cr.assign((size_t)mbw * 8 * mbh * 8, 128);
            }
            references = 0; waiting = false;
        }
        mpeg2 = false;                  // until a sequence extension says otherwise
    }
    void extension() {
        int id = (int)bs.get(4);
        if (id == 1) {                  // sequence extension
            mpeg2 = true;
            bs.skip(8);
            bs.skip(1);                 // progressive_sequence
            int chroma = (int)bs.get(2);
            if (chroma != 1) unsupported++;
        } else if (id == 3) {           // quant matrix extension
            const uint8_t* zz = scan_table(0);
            if (bs.get(1)) for (int k = 0; k < 64; k++) intra_matrix[zz[k]] = (uint8_t)bs.get(8);
            if (bs.get(1)) for (int k = 0; k < 64; k++) inter_matrix[zz[k]] = (uint8_t)bs.get(8);
        } else if (id == 8) {           // picture coding extension
            f_code[0][0] = (int)bs.get(4); f_code[0][1] = (int)bs.get(4);
            f_code[1][0] = (int)bs.get(4); f_code[1][1] = (int)bs.get(4);
            intra_dc_precision = (int)bs.get(2);
            picture_structure = (int)bs.get(2);
            bs.skip(1);                 // top_field_first
            frame_pred_frame_dct = (int)bs.get(1);
            concealment = (int)bs.get(1);
            q_scale_type = (int)bs.get(1);
            intra_vlc_format = (int)bs.get(1);
            alternate_scan = (int)bs.get(1);
            full_pel[0] = full_pel[1] = 0;
        }
    }
    void picture_header() {
        temporal_reference = (int)bs.get(10);
        picture_type = (int)bs.get(3);
        bs.skip(16);
        // MPEG-1 keeps its vector range here; an MPEG-2 stream says it again in the extension
        if (picture_type == 2 || picture_type == 3) { full_pel[0] = (int)bs.get(1); int f = (int)bs.get(3); f_code[0][0] = f_code[0][1] = f; }
        if (picture_type == 3) { full_pel[1] = (int)bs.get(1); int f = (int)bs.get(3); f_code[1][0] = f_code[1][1] = f; }
        intra_dc_precision = 0; picture_structure = 3; frame_pred_frame_dct = 1; concealment = 0;
        q_scale_type = 0; intra_vlc_format = 0; alternate_scan = 0;
    }

    // Reads headers up to the first slice of the next picture; `pos` is left at that slice.
    bool find_picture_and_headers(size_t&) {
        if (!find_picture(pos)) return false;
        bool have_picture = false;
        for (size_t k = next_start(pos); k + 3 < stream.size(); k = next_start(k + 3)) {
            int code = stream[k + 3];
            bs.p = stream.data(); bs.size = stream.size(); bs.at = (k + 4) * 8;
            if (code == 0xB3) sequence_header();
            else if (code == 0xB5) extension();
            else if (code == 0x00) { picture_header(); have_picture = true; }
            else if (code >= 0x01 && code <= 0xAF && have_picture) { pos = k; return width > 0; }
        }
        return false;
    }
    void skip_picture() {               // past the slices of the picture at pos
        size_t k = pos;
        while (k + 3 < stream.size() && stream[k + 3] >= 0x01 && stream[k + 3] <= 0xAF) k = next_start(k + 3);
        pos = k;
    }

    // ---- variable-length codes ----
    struct Vlc { int16_t value; uint8_t length; };
    struct Coefficient { uint8_t run; uint8_t length; int16_t level; };     // level 0, run 64: end of block; run 65: escape
    std::vector<Vlc> mba_table, cbp_table, motion_table, dc_luma_table, dc_chroma_table, type_table[4];
    std::vector<Coefficient> coefficient_table[2];
    static void add(std::vector<Vlc>& table, int bits, const char* code, int value) {
        if (table.empty()) table.assign((size_t)1 << bits, Vlc{0, 0});
        uint32_t v = 0; int n = 0;
        for (const char* c = code; *c; c++) if (*c == '0' || *c == '1') { v = (v << 1) | (uint32_t)(*c - '0'); n++; }
        uint32_t first = v << (bits - n);
        for (uint32_t k = 0; k < (1u << (bits - n)); k++) table[first + k] = Vlc{(int16_t)value, (uint8_t)n};
    }
    static void add_coefficient(std::vector<Coefficient>& table, const char* code, int run, int level) {
        if (table.empty()) table.assign(65536, Coefficient{0, 0, 0});
        uint32_t v = 0; int n = 0;
        for (const char* c = code; *c; c++) if (*c == '0' || *c == '1') { v = (v << 1) | (uint32_t)(*c - '0'); n++; }
        uint32_t first = v << (16 - n);
        for (uint32_t k = 0; k < (1u << (16 - n)); k++) table[first + k] = Coefficient{(uint8_t)run, (uint8_t)n, (int16_t)level};
    }
    int read(const std::vector<Vlc>& table, int bits) {
        const Vlc& e = table[bs.peek(bits)];
        if (!e.length) { bad = true; return 0; }
        bs.skip(e.length);
        return e.value;
    }
    bool bad = false;

    void build_tables() {
        // Table B.1, macroblock_address_increment (34: escape, 35: stuffing)
        static const char* const mba[] = {"1", "011", "010", "0011", "0010", "00011", "00010", "0000111", "0000110", "00001011", "00001010", "00001001",
            "00001000", "00000111", "00000110", "0000010111", "0000010110", "0000010101", "0000010100", "0000010011", "0000010010", "00000100011",
            "00000100010", "00000100001", "00000100000", "00000011111", "00000011110", "00000011101", "00000011100", "00000011011", "00000011010",
            "00000011001", "00000011000"};
        for (int k = 0; k < 33; k++) add(mba_table, 11, mba[k], k + 1);
        add(mba_table, 11, "00000001000", 34);
        add(mba_table, 11, "00000001111", 35);
        // Tables B.2 to B.4, macroblock_type: bits 1 quant, 2 forward, 4 backward, 8 pattern, 16 intra
        add(type_table[1], 6, "1", 16); add(type_table[1], 6, "01", 17);
        add(type_table[2], 6, "1", 2 | 8); add(type_table[2], 6, "01", 8); add(type_table[2], 6, "001", 2); add(type_table[2], 6, "00011", 16);
        add(type_table[2], 6, "00010", 1 | 2 | 8); add(type_table[2], 6, "00001", 1 | 8); add(type_table[2], 6, "000001", 17);
        add(type_table[3], 6, "10", 2 | 4); add(type_table[3], 6, "11", 2 | 4 | 8); add(type_table[3], 6, "010", 4); add(type_table[3], 6, "011", 4 | 8);
        add(type_table[3], 6, "0010", 2); add(type_table[3], 6, "0011", 2 | 8); add(type_table[3], 6, "00011", 16); add(type_table[3], 6, "00010", 1 | 2 | 4 | 8);
        add(type_table[3], 6, "000011", 1 | 2 | 8); add(type_table[3], 6, "000010", 1 | 4 | 8); add(type_table[3], 6, "000001", 17);
        // Table B.9, coded_block_pattern
        static const struct { const char* code; int value; } cbp[] = {
            {"111", 60}, {"1101", 4}, {"1100", 8}, {"1011", 16}, {"1010", 32}, {"10011", 12}, {"10010", 48}, {"10001", 20}, {"10000", 40},
            {"01111", 28}, {"01110", 44}, {"01101", 52}, {"01100", 56}, {"01011", 1}, {"01010", 61}, {"01001", 2}, {"01000", 62},
            {"001111", 24}, {"001110", 36}, {"001101", 3}, {"001100", 63}, {"0010111", 5}, {"0010110", 9}, {"0010101", 17}, {"0010100", 33},
            {"0010011", 6}, {"0010010", 10}, {"0010001", 18}, {"0010000", 34}, {"00011111", 7}, {"00011110", 11}, {"00011101", 19},
            {"00011100", 35}, {"00011011", 13}, {"00011010", 49}, {"00011001", 21}, {"00011000", 41}, {"00010111", 14}, {"00010110", 50},
            {"00010101", 22}, {"00010100", 42}, {"00010011", 15}, {"00010010", 51}, {"00010001", 23}, {"00010000", 43}, {"00001111", 25},
            {"00001110", 37}, {"00001101", 26}, {"00001100", 38}, {"00001011", 29}, {"00001010", 45}, {"00001001", 53}, {"00001000", 57},
            {"00000111", 30}, {"00000110", 46}, {"00000101", 54}, {"00000100", 58}, {"000000111", 31}, {"000000110", 47}, {"000000101", 55},
            {"000000100", 59}, {"000000011", 27}, {"000000010", 39}, {"000000001", 0}};
        for (const auto& e : cbp) add(cbp_table, 9, e.code, e.value);
        // Table B.10, motion_code (the sign bit is read after it): value = magnitude
        static const char* const motion[] = {"1", "01", "001", "0001", "000011", "0000101", "0000100", "0000011", "000001011", "000001010",
            "000001001", "0000010001", "0000010000", "0000001111", "0000001110", "0000001101", "0000001100"};
        for (int k = 0; k < 17; k++) add(motion_table, 10, motion[k], k);
        // Tables B.12 and B.13, dct_dc_size
        static const char* const dcl[] = {"100", "00", "01", "101", "110", "1110", "11110", "111110", "1111110", "11111110", "111111110", "111111111"};
        static const char* const dcc[] = {"00", "01", "10", "110", "1110", "11110", "111110", "1111110", "11111110", "111111110", "1111111110", "1111111111"};
        for (int k = 0; k < 12; k++) { add(dc_luma_table, 9, dcl[k], k); add(dc_chroma_table, 10, dcc[k], k); }
        // Tables B.14 and B.15, DCT coefficients: run, level, the code in table zero, the code
        // in table one (nullptr: the same).  "1s" as the first coefficient of a non-intra
        // block is handled where blocks are read.
        static const struct { int run, level; const char* zero; const char* one; } co[] = {
            {0, 1, "11", "10"}, {1, 1, "011", "010"}, {0, 2, "0100", "110"}, {2, 1, "0101", "00101"}, {0, 3, "00101", "0111"},
            {3, 1, "00111", "00111"}, {4, 1, "00110", "000110"}, {1, 2, "000110", "00110"}, {5, 1, "000111", "000111"},
            {6, 1, "000101", "0000110"}, {7, 1, "000100", "0000100"}, {0, 4, "0000110", "11100"}, {2, 2, "0000100", "0000111"},
            {8, 1, "0000111", "0000101"}, {9, 1, "0000101", "1111000"}, {0, 5, "00100110", "11101"}, {0, 6, "00100001", "000101"},
            {1, 3, "00100101", "1111001"}, {3, 2, "00100100", "00100110"}, {10, 1, "00100111", "1111010"}, {11, 1, "00100011", "00100001"},
            {12, 1, "00100010", "00100101"}, {13, 1, "00100000", "00100100"}, {0, 7, "0000001010", "000100"}, {1, 4, "0000001100", "00100111"},
            {2, 3, "0000001011", "11111100"}, {4, 2, "0000001111", "11111101"}, {5, 2, "0000001001", "000000100"},
            {14, 1, "0000001110", "000000101"}, {15, 1, "0000001101", "000000111"}, {16, 1, "0000001000", "0000001101"},
            {0, 8, "000000011101", "1111011"}, {0, 9, "000000011000", "1111100"}, {0, 10, "000000010011", "00100011"},
            {0, 11, "000000010000", "00100010"}, {1, 5, "000000011011", "00100000"}, {2, 4, "000000010100", "0000001100"},
            {3, 3, "000000011100", nullptr}, {4, 3, "000000010010", nullptr}, {6, 2, "000000011110", nullptr}, {7, 2, "000000010101", nullptr},
            {8, 2, "000000010001", nullptr}, {17, 1, "000000011111", nullptr}, {18, 1, "000000011010", nullptr}, {19, 1, "000000011001", nullptr},
            {20, 1, "000000010111", nullptr}, {21, 1, "000000010110", nullptr}, {0, 12, "0000000011010", "11111010"},
            {0, 13, "0000000011001", "11111011"}, {0, 14, "0000000011000", "11111110"}, {0, 15, "0000000010111", "11111111"},
            {1, 6, "0000000010110", nullptr}, {1, 7, "0000000010101", nullptr}, {2, 5, "0000000010100", nullptr}, {3, 4, "0000000010011", nullptr},
            {5, 3, "0000000010010", nullptr}, {9, 2, "0000000010001", nullptr}, {10, 2, "0000000010000", nullptr}, {22, 1, "0000000011111", nullptr},
            {23, 1, "0000000011110", nullptr}, {24, 1, "0000000011101", nullptr}, {25, 1, "0000000011100", nullptr}, {26, 1, "0000000011011", nullptr},
            {0, 16, "00000000011111", nullptr}, {0, 17, "00000000011110", nullptr}, {0, 18, "00000000011101", nullptr}, {0, 19, "00000000011100", nullptr},
            {0, 20, "00000000011011", nullptr}, {0, 21, "00000000011010", nullptr}, {0, 22, "00000000011001", nullptr}, {0, 23, "00000000011000", nullptr},
            {0, 24, "00000000010111", nullptr}, {0, 25, "00000000010110", nullptr}, {0, 26, "00000000010101", nullptr}, {0, 27, "00000000010100", nullptr},
            {0, 28, "00000000010011", nullptr}, {0, 29, "00000000010010", nullptr}, {0, 30, "00000000010001", nullptr}, {0, 31, "00000000010000", nullptr},
            {0, 32, "000000000011000", nullptr}, {0, 33, "000000000010111", nullptr}, {0, 34, "000000000010110", nullptr}, {0, 35, "000000000010101", nullptr},
            {0, 36, "000000000010100", nullptr}, {0, 37, "000000000010011", nullptr}, {0, 38, "000000000010010", nullptr}, {0, 39, "000000000010001", nullptr},
            {0, 40, "000000000010000", nullptr}, {1, 8, "000000000011111", nullptr}, {1, 9, "000000000011110", nullptr}, {1, 10, "000000000011101", nullptr},
            {1, 11, "000000000011100", nullptr}, {1, 12, "000000000011011", nullptr}, {1, 13, "000000000011010", nullptr}, {1, 14, "000000000011001", nullptr},
            {1, 15, "0000000000010011", nullptr}, {1, 16, "0000000000010010", nullptr}, {1, 17, "0000000000010001", nullptr}, {1, 18, "0000000000010000", nullptr},
            {6, 3, "0000000000010100", nullptr}, {11, 2, "0000000000011010", nullptr}, {12, 2, "0000000000011001", nullptr}, {13, 2, "0000000000011000", nullptr},
            {14, 2, "0000000000010111", nullptr}, {15, 2, "0000000000010110", nullptr}, {16, 2, "0000000000010101", nullptr}, {27, 1, "0000000000011111", nullptr},
            {28, 1, "0000000000011110", nullptr}, {29, 1, "0000000000011101", nullptr}, {30, 1, "0000000000011100", nullptr}, {31, 1, "0000000000011011", nullptr}};
        for (const auto& e : co) {
            add_coefficient(coefficient_table[0], e.zero, e.run, e.level);
            add_coefficient(coefficient_table[1], e.one ? e.one : e.zero, e.run, e.level);
        }
        add_coefficient(coefficient_table[0], "10", 64, 0);       // end of block
        add_coefficient(coefficient_table[1], "0110", 64, 0);
        add_coefficient(coefficient_table[0], "000001", 65, 0);   // escape
        add_coefficient(coefficient_table[1], "000001", 65, 0);
        // the inverse transform's basis: c(u) / 2 * cos((2x + 1) u pi / 16)
        for (int x = 0; x < 8; x++)
            for (int u = 0; u < 8; u++) basis[x][u] = (float)((u == 0 ? std::sqrt(0.5) : 1.0) * 0.5 * std::cos((2 * x + 1) * u * 3.14159265358979323846 / 16.0));
    }

    // ---- a picture ----
    float basis[8][8];
    int quantiser_scale = 2;
    int dc_pred[3];
    int pmv[2][2];                      // [forward, backward][x, y], in half samples
    Picture* out = nullptr;
    const Picture* ref[2] = {nullptr, nullptr};

    int scale_of(int code) const {
        static const uint8_t nonlinear[32] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 44, 48, 52, 56, 64, 72, 80, 88, 96, 104, 112};
        return q_scale_type ? nonlinear[code & 31] : (code & 31) * 2;
    }

    bool decode_picture(int target) {
        if (picture_structure != 3 || !frame_pred_frame_dct || concealment) { unsupported++; skip_picture(); return false; }
        out = &frames[target];
        out->type = picture_type; out->temporal_reference = temporal_reference;
        if (picture_type == 2) ref[0] = &frames[newest];
        else if (picture_type == 3) { ref[0] = &frames[1 - newest]; ref[1] = &frames[newest]; }
        bad = false;
        size_t k = pos;
        while (k + 3 < stream.size() && stream[k + 3] >= 0x01 && stream[k + 3] <= 0xAF) {
            size_t end = next_start(k + 3);
            bs.p = stream.data(); bs.size = end; bs.at = (k + 4) * 8;
            slice(stream[k + 3] - 1);
            if (bad) { errors++; bad = false; }
            k = end;
        }
        pos = k;
        return true;
    }

    void slice(int row) {
        if (row >= mbh) return;
        quantiser_scale = scale_of((int)bs.get(5));
        while (bs.get(1)) bs.skip(8);                   // extra information
        int address = row * mbw - 1;
        dc_pred[0] = dc_pred[1] = dc_pred[2] = 1 << (intra_dc_precision + 7);
        memset(pmv, 0, sizeof(pmv));
        int previous_type = 0;
        bool first = true;
        while (!bad) {
            int increment = 0;
            for (;;) {
                int v = read(mba_table, 11);
                if (bad) return;
                if (v == 35) continue;                  // stuffing
                if (v == 34) { increment += 33; continue; }
                increment += v;
                break;
            }
            if (first) { address += increment; first = false; }
            else {
                // skipped macroblocks: P: the picture before, unmoved; B: predicted as the
                // macroblock before them was
                for (int k = 1; k < increment; k++) {
                    address++;
                    if (address >= mbw * mbh) return;
                    if (picture_type == 2) { memset(pmv, 0, sizeof(pmv)); predict(address, 2, 0, 0, 0, 0); }
                    else predict(address, previous_type & 6, pmv[0][0], pmv[0][1], pmv[1][0], pmv[1][1]);
                }
                if (increment > 1) dc_pred[0] = dc_pred[1] = dc_pred[2] = 1 << (intra_dc_precision + 7);
                address++;
            }
            if (address >= mbw * mbh) return;
            int type = read(type_table[picture_type], 6);
            if (bad) return;
            if (type & 1) quantiser_scale = scale_of((int)bs.get(5));
            if (type & 16) {
                memset(pmv, 0, sizeof(pmv));
                intra_macroblock(address);
            } else {
                dc_pred[0] = dc_pred[1] = dc_pred[2] = 1 << (intra_dc_precision + 7);
                if (type & 2) vector(0); else if (picture_type == 2) pmv[0][0] = pmv[0][1] = 0;
                if (type & 4) vector(1);
                int direction = type & 6;
                if (picture_type == 2) direction = 2;   // a P macroblock without a vector is predicted unmoved
                predict(address, direction, pmv[0][0], pmv[0][1], pmv[1][0], pmv[1][1]);
                if (type & 8) {
                    int cbp = read(cbp_table, 9);
                    if (bad) return;
                    for (int b = 0; b < 6; b++) if (cbp & (32 >> b)) { if (!block(false, b)) return; add_block(address, b); }
                }
            }
            previous_type = type;
            if (bs.end() || bs.peek(23) == 0) return;   // the next start code
        }
    }

    void vector(int s) {
        for (int t = 0; t < 2; t++) {
            int r_size = f_code[s][t] - 1, f = 1 << r_size;
            int code = read(motion_table, 10);
            if (bad) return;
            int delta = 0;
            if (code) {
                bool negative = bs.get(1);
                int residual = r_size ? (int)bs.get(r_size) : 0;
                delta = (code - 1) * f + residual + 1;
                if (negative) delta = -delta;
            }
            int range = 32 * f, v = pmv[s][t] + delta;
            if (v < -16 * f) v += range; else if (v > 16 * f - 1) v -= range;
            pmv[s][t] = v;
        }
    }

    // ---- prediction ----
    static void fetch(const uint8_t* plane, int pw, int ph, int x, int y, int vx, int vy, int size, uint8_t* to) {
        int ix = x + (vx >> 1), iy = y + (vy >> 1), hx = vx & 1, hy = vy & 1;
        bool inside = ix >= 0 && iy >= 0 && ix + size + hx <= pw && iy + size + hy <= ph;
        auto at = [&](int px, int py) -> int {
            if (!inside) { px = px < 0 ? 0 : px >= pw ? pw - 1 : px; py = py < 0 ? 0 : py >= ph ? ph - 1 : py; }
            return plane[(size_t)py * pw + px];
        };
        for (int r = 0; r < size; r++)
            for (int c = 0; c < size; c++) {
                int a = at(ix + c, iy + r);
                if (hx && hy) a = (a + at(ix + c + 1, iy + r) + at(ix + c, iy + r + 1) + at(ix + c + 1, iy + r + 1) + 2) >> 2;
                else if (hx) a = (a + at(ix + c + 1, iy + r) + 1) >> 1;
                else if (hy) a = (a + at(ix + c, iy + r + 1) + 1) >> 1;
                to[r * size + c] = (uint8_t)a;
            }
    }
    void predict(int address, int direction, int fx, int fy, int bx, int by) {
        int mx = address % mbw, my = address / mbw, w = mbw * 16, h = mbh * 16;
        uint8_t a[3][256], b[3][256];
        bool forward = (direction & 2) && ref[0], backward = (direction & 4) && ref[1];
        if (!forward && !backward) { if (!ref[0]) return; forward = true; fx = fy = 0; }
        if (forward) {
            if (full_pel[0] && !mpeg2) { fx *= 2; fy *= 2; }
            fetch(ref[0]->y.data(), w, h, mx * 16, my * 16, fx, fy, 16, a[0]);
            fetch(ref[0]->cb.data(), w / 2, h / 2, mx * 8, my * 8, fx / 2, fy / 2, 8, a[1]);
            fetch(ref[0]->cr.data(), w / 2, h / 2, mx * 8, my * 8, fx / 2, fy / 2, 8, a[2]);
        }
        if (backward) {
            if (full_pel[1] && !mpeg2) { bx *= 2; by *= 2; }
            fetch(ref[1]->y.data(), w, h, mx * 16, my * 16, bx, by, 16, b[0]);
            fetch(ref[1]->cb.data(), w / 2, h / 2, mx * 8, my * 8, bx / 2, by / 2, 8, b[1]);
            fetch(ref[1]->cr.data(), w / 2, h / 2, mx * 8, my * 8, bx / 2, by / 2, 8, b[2]);
        }
        uint8_t* planes[3] = {out->y.data(), out->cb.data(), out->cr.data()};
        for (int p = 0; p < 3; p++) {
            int size = p ? 8 : 16, pw = p ? w / 2 : w;
            uint8_t* to = planes[p] + (size_t)(my * size) * pw + mx * size;
            for (int r = 0; r < size; r++)
                for (int c = 0; c < size; c++)
                    to[(size_t)r * pw + c] = forward && backward ? (uint8_t)((a[p][r * size + c] + b[p][r * size + c] + 1) >> 1)
                                           : forward ? a[p][r * size + c] : b[p][r * size + c];
        }
    }

    // ---- blocks ----
    int16_t coefficients[64];
    float samples[64];

    bool block(bool intra, int b) {
        memset(coefficients, 0, sizeof(coefficients));
        const uint8_t* scan = scan_table(alternate_scan);
        const uint8_t* matrix = intra ? intra_matrix : inter_matrix;
        const std::vector<Coefficient>& table = coefficient_table[intra && intra_vlc_format ? 1 : 0];
        int n = 0, sum = 0;
        if (intra) {
            int component = b < 4 ? 0 : b - 3;
            int size = read(component ? dc_chroma_table : dc_luma_table, component ? 10 : 9);
            if (bad) return false;
            int diff = 0;
            if (size) {
                diff = (int)bs.get(size);
                if (!(diff & (1 << (size - 1)))) diff -= (1 << size) - 1;
            }
            dc_pred[component] += diff;
            int dc = dc_pred[component] << (3 - intra_dc_precision);
            coefficients[0] = (int16_t)dc;
            sum = dc;
            n = 1;
        }
        for (;;) {
            int run, level;
            if (!intra && n == 0 && bs.peek(1)) {       // "1s": the first coefficient of a non-intra block
                bs.skip(1);
                run = 0; level = bs.get(1) ? -1 : 1;
            } else {
                const Coefficient& e = table[bs.peek(16)];
                if (!e.length) { bad = true; return false; }
                bs.skip(e.length);
                if (e.run == 64) break;
                if (e.run == 65) {
                    run = (int)bs.get(6);
                    if (mpeg2) { level = (int)bs.get(12); if (level & 0x800) level -= 0x1000; }
                    else {
                        level = (int)bs.get(8);
                        if (level == 0) level = (int)bs.get(8);
                        else if (level == 128) level = (int)bs.get(8) - 256;
                        else if (level > 128) level -= 256;
                    }
                } else { run = e.run; level = bs.get(1) ? -e.level : e.level; }
            }
            n += run;
            if (n > 63) { bad = true; return false; }
            int at = scan[n];
            int value;
            if (intra) value = (level * matrix[at] * quantiser_scale * 2) / 32;
            else value = ((2 * level + (level > 0 ? 1 : -1)) * matrix[at] * quantiser_scale) / 32;
            if (!mpeg2) {                               // MPEG-1: results are made odd, towards zero
                if (intra) value = (level * matrix[at] * quantiser_scale * 2) / 16;
                else value = ((2 * level + (level > 0 ? 1 : -1)) * matrix[at] * quantiser_scale) / 16;
                if (!(value & 1)) value += value > 0 ? -1 : value < 0 ? 1 : 0;
            }
            if (value > 2047) value = 2047; else if (value < -2048) value = -2048;
            coefficients[at] = (int16_t)value;
            sum += value;
            n++;
        }
        if (mpeg2 && !(sum & 1)) coefficients[63] ^= 1;  // mismatch control
        inverse_transform();
        return true;
    }

    void inverse_transform() {
        float rows[64];
        for (int v = 0; v < 8; v++) {
            const int16_t* in = coefficients + v * 8;
            bool any = false;
            for (int u = 0; u < 8; u++) any |= in[u] != 0;
            if (!any) { for (int x = 0; x < 8; x++) rows[v * 8 + x] = 0; continue; }
            for (int x = 0; x < 8; x++) {
                float s = 0;
                for (int u = 0; u < 8; u++) s += basis[x][u] * (float)in[u];
                rows[v * 8 + x] = s;
            }
        }
        for (int x = 0; x < 8; x++)
            for (int y = 0; y < 8; y++) {
                float s = 0;
                for (int v = 0; v < 8; v++) s += basis[y][v] * rows[v * 8 + x];
                samples[y * 8 + x] = s;
            }
    }

    // to the nearest integer whatever rounding mode the calling thread is in (the game's
    // threads round toward zero)
    static int nearest(float v) { return (int)std::floor(v + 0.5f); }

    uint8_t* block_at(int address, int b, int& stride) {
        int mx = address % mbw, my = address / mbw, w = mbw * 16;
        if (b < 4) { stride = w; return out->y.data() + (size_t)(my * 16 + (b >> 1) * 8) * w + mx * 16 + (b & 1) * 8; }
        stride = w / 2;
        return (b == 4 ? out->cb.data() : out->cr.data()) + (size_t)(my * 8) * (w / 2) + mx * 8;
    }
    void intra_macroblock(int address) {
        for (int b = 0; b < 6; b++) {
            if (!block(true, b)) return;
            int stride;
            uint8_t* to = block_at(address, b, stride);
            for (int y = 0; y < 8; y++)
                for (int x = 0; x < 8; x++) {
                    int v = nearest(samples[y * 8 + x]);
                    to[(size_t)y * stride + x] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
                }
        }
    }
    void add_block(int address, int b) {
        int stride;
        uint8_t* to = block_at(address, b, stride);
        for (int y = 0; y < 8; y++)
            for (int x = 0; x < 8; x++) {
                int v = to[(size_t)y * stride + x] + nearest(samples[y * 8 + x]);
                to[(size_t)y * stride + x] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
            }
    }

    static void convert(int y, int cb, int cr, uint8_t* o) {
        int c = 298 * (y - 16) + 128, d = cb - 128, e = cr - 128;
        int r = (c + 409 * e) >> 8, g = (c - 100 * d - 208 * e) >> 8, b = (c + 516 * d) >> 8;
        o[0] = (uint8_t)(r < 0 ? 0 : r > 255 ? 255 : r);
        o[1] = (uint8_t)(g < 0 ? 0 : g > 255 ? 255 : g);
        o[2] = (uint8_t)(b < 0 ? 0 : b > 255 ? 255 : b);
        o[3] = 0x80;
    }
};

}  // namespace mpeg2
