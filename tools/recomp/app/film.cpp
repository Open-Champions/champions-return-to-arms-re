// film.cpp - the game's films in the native application.
//
// The film player (movie_open 0x3202c0, movie_update 0x3205ec; docs/mainloop.md) reads an
// MPEG-2 video stream from the disc in pieces and has Sony's MPEG library decode one
// picture per frame, in step with the sound stream that carries the film's sound.  That
// library does its work through the console's Image Processing Unit - bit reading,
// variable-length decoding, the inverse transform and the colour conversion are commands
// to that unit, with data going round through two DMA channels - which this machine does
// not have.  What is replaced here is the library, at the seven entry points the player
// calls (tools/recomp/app/hle-app.txt), not the unit: the player is the game's own code
// and stays in charge of reading, of timing against the sound and of putting the picture
// on the screen; a picture is decoded on the host (mpeg2.h) and handed over in the form
// the library hands it over in.
//
// The library's structure (sceMpeg, 0x48 bytes at the address the player passes):
//   +0 width, +4 height, +8 frame number since the last reset (0 for the first picture;
//   the player sets its upload chain up when it reads 0), +0x40 the library's own state.
// A picture is 16 x 16 pixel macroblocks of RGBA (alpha 0x80), 1,024 bytes each, column
// after column: the player sends each to the GS as one 16 x 16 rectangle.
#include "rt.h"

#include "mpeg2.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>

namespace {

mpeg2::Decoder* g_decoder;
u64 g_film_pictures, g_film_streams, g_film_bytes;
double g_decode_ms;
int g_count_since_reset;

// Which film plays, and its picture now (for a host that shows an enlarged copy of the film in place of the game's
// picture: tools/films/films.py makes the copies from the player's own disc, keyed the same way).  The key is the
// FNV-1a hash of the first KEY_BYTES bytes of stream the player hands over after a create or a reset (a stream on the
// disc begins with its sequence header: the same bytes on every copy of the disc), the picture the number of pictures
// handed out since then, display order - what the decoder counts and what any other decoder of the same stream counts.
// Nothing of this reaches the game.
const u32 KEY_BYTES = 65536;
u64 g_key_hash = 0;
u32 g_key_fed = 0;
std::atomic<u64> g_key{0};              // 0 until KEY_BYTES were fed (or the first picture, with fewer)
std::atomic<int> g_picture{-1};         // the picture handed out last since the reset (-1: none yet)
std::atomic<int> g_active{0};           // between create and delete
std::atomic<u32> g_size{0};             // width << 16 | height of the picture handed out last
const bool g_log = getenv("RTA_FILM_LOG") != nullptr;

void key_reset() {
    g_key_hash = 1469598103934665603ull;
    g_key_fed = 0;
    g_key = 0;
    g_picture = -1;
}
void key_feed(const u8* data, u32 size) {
    if (g_key_fed >= KEY_BYTES) return;
    u32 n = std::min(size, KEY_BYTES - g_key_fed);
    for (u32 i = 0; i < n; i++) g_key_hash = (g_key_hash ^ data[i]) * 1099511628211ull;
    g_key_fed += n;
    if (g_key_fed >= KEY_BYTES) g_key = g_key_hash ? g_key_hash : 1;
}

inline u8* guest(u32 address) { return g_ram + (address & (RAM_SIZE - 1)); }
mpeg2::Decoder& decoder() {
    if (!g_decoder) g_decoder = new mpeg2::Decoder();
    return *g_decoder;
}

}  // namespace

// Said to the application (app_rt.cpp), which then lets the game's own film player run.
bool rta_films_linked() { return true; }
// The film now (app_rt.h apprt::film_now): any thread.
bool rta_film_now(uint64_t* key, int* picture, int* width, int* height) {
    if (!g_active.load()) return false;
    u32 size = g_size.load();
    *key = g_key.load();
    *picture = g_picture.load();
    *width = (int)(size >> 16);
    *height = (int)(size & 0xffff);
    return true;
}
void rta_films_report() {
    if (!g_film_streams) return;
    printf("films: %llu pictures decoded on the host from %llu pieces of stream (%.1f MB), %.2f ms of processor time a picture; pictures the decoder does not support %llu, slices with errors %llu\n",
           (unsigned long long)g_film_pictures, (unsigned long long)g_film_streams, g_film_bytes / 1048576.0,
           g_film_pictures ? g_decode_ms / g_film_pictures : 0.0, g_decoder ? (unsigned long long)g_decoder->unsupported : 0ull,
           g_decoder ? (unsigned long long)g_decoder->errors : 0ull);
}

void fn_003734f0(Ctx* c) { c->r[2] = 0; }                       // sceMpegInit

void fn_00372948(Ctx* c) {                                      // sceMpegCreate(mp, work, size)
    u32 mp = (u32)c->r[4];
    memset(guest(mp), 0, 0x48);
    W(mp + 0x40) = (u32)c->r[5];                                // the library keeps its state in the work area
    delete g_decoder;
    g_decoder = nullptr;
    g_count_since_reset = 0;
    key_reset();
    g_active = 1;
    if (g_log) printf("film: create mp %08x work %08x size %u\n", mp, (u32)c->r[5], (u32)c->r[6]);
    c->r[2] = 0;
}

void fn_003735a0(Ctx* c) {                                      // sceMpegDelete
    if (g_log) printf("film: delete after %d pictures, key %016llx\n", g_picture.load() + 1, (unsigned long long)g_key.load());
    g_active = 0;
    c->r[2] = 1;
}

void fn_00373688(Ctx* c) {                                      // sceMpegReset(mp)
    u32 mp = (u32)c->r[4];
    decoder().reset_stream();
    W(mp + 8) = 0;
    if (g_log) printf("film: reset after %d pictures, key %016llx\n", g_picture.load() + 1, (unsigned long long)g_key.load());
    g_count_since_reset = 0;
    key_reset();
    c->r[2] = 0;
}

void fn_003735a8(Ctx* c) {                                      // sceMpegAddBs(mp, data, size)
    u32 data = (u32)c->r[5], size = (u32)c->r[6];
    if (size && (data & (RAM_SIZE - 1)) <= RAM_SIZE - size) {
        decoder().feed(guest(data), size);
        key_feed(guest(data), size);
        if (g_log) {
            const u8* b = guest(data);
            printf("film: add %u bytes at %08x: %02x %02x %02x %02x %02x %02x %02x %02x (picture %d)\n", size, data, b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], g_picture.load());
        }
        g_film_streams++;
        g_film_bytes += size;
    }
    c->r[2] = 1;
}

void fn_00373708(Ctx* c) { c->r[2] = decoder().at_end() ? 1 : 0; }     // sceMpegIsEnd(mp)

void fn_003735e8(Ctx* c) {                                      // sceMpegGetPicture(mp, rgb32, macroblocks)
    u32 mp = (u32)c->r[4], out = (u32)c->r[5] & (RAM_SIZE - 1), count = (u32)c->r[6];
    timespec a, b;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
    const mpeg2::Picture* p = decoder().next();
    if (!p) { c->r[2] = 0; return; }                            // nothing more: the picture before stays
    u32 n = 0;
    for (int x = 0; x < p->mbw && n < count; x++)
        for (int y = 0; y < p->mbh && n < count; y++, n++) {
            if (out + (n + 1) * 1024 > RAM_SIZE) break;
            mpeg2::Decoder::macroblock_rgba(*p, x, y, g_ram + out + n * 1024);
        }
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
    g_decode_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
    W(mp + 0) = (u32)p->width;
    W(mp + 4) = (u32)p->height;
    W(mp + 8) = (u32)g_count_since_reset++;
    g_film_pictures++;
    if (!g_key.load() && g_key_fed) g_key = g_key_hash ? g_key_hash : 1;     // a stream shorter than KEY_BYTES
    g_size = (u32)p->width << 16 | (u32)p->height;
    g_picture = g_count_since_reset - 1;
    c->r[2] = 1;
    // The player does not time the film (its wait for a field and its check against the
    // sound stream are both never switched on): it decodes a picture in every frame of
    // the game's loop.  On the console decoding a picture takes more than one field, so
    // the loop comes round every second field and the film runs at the rate it is coded
    // for, 29.97 pictures a second; here decoding takes no machine time at all and the
    // film ran at twice its speed, away from its sound.  The call therefore takes the
    // machine time of a little more than one field.
    rt_sleep(c, CYCLES_PER_SECOND / 55);
}
