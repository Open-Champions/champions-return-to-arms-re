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

#include <cstdio>

namespace {

mpeg2::Decoder* g_decoder;
u64 g_film_pictures, g_film_streams, g_film_bytes;
double g_decode_ms;
int g_count_since_reset;

inline u8* guest(u32 address) { return g_ram + (address & (RAM_SIZE - 1)); }
mpeg2::Decoder& decoder() {
    if (!g_decoder) g_decoder = new mpeg2::Decoder();
    return *g_decoder;
}

}  // namespace

// Said to the application (app_rt.cpp), which then lets the game's own film player run.
bool rta_films_linked() { return true; }
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
    c->r[2] = 0;
}

void fn_003735a0(Ctx* c) { c->r[2] = 1; }                       // sceMpegDelete

void fn_00373688(Ctx* c) {                                      // sceMpegReset(mp)
    u32 mp = (u32)c->r[4];
    decoder().reset_stream();
    W(mp + 8) = 0;
    g_count_since_reset = 0;
    c->r[2] = 0;
}

void fn_003735a8(Ctx* c) {                                      // sceMpegAddBs(mp, data, size)
    u32 data = (u32)c->r[5], size = (u32)c->r[6];
    if (size && (data & (RAM_SIZE - 1)) <= RAM_SIZE - size) {
        decoder().feed(guest(data), size);
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
