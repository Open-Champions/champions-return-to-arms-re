// sndtool.cpp - tests for the sound library without the game.
//
//   clang++ -std=c++17 -O2 -I tools/recomp/rt tools/recomp/sound/sndtool.cpp -o local/sound/bin/sndtool
//
//   sndtool replay CAPTURE OUT.wav [--iso IMAGE] [--frames N] [--tail SECONDS]
//                  [--events FILE.tsv] [--realtime 1 [--from-frame N]] [--opt key=value]...
//       Play a sound capture (capture.py) through sound_rpc / sound_vblank / sound_report
//       of sound_rta.cpp, exactly as the native runtime calls them: this program is a
//       runtime that has only a clock, the two memories and the options.  --iso serves
//       the capture's disc reads (stream data).  --events lists what was sent, with the
//       register batches decoded, one line per item, times in seconds of machine time.
//   sndtool sample FILE.vag OUT.wav [--pitch SCALE | --pitch-register N] [--left V] [--right V] [--seconds N]
//       One lump sample, started the way sound_playSample starts it.
//   sndtool stream FILE.raw 1|2 OUT.wav [--seconds N] [--on-stream 0|1|2]
//       Headerless stream data (an entry of a .VAT, one or two channels), fed through the
//       stream driver's ring buffer as the game feeds it.
//   sndtool bench [--voices N] [--seconds N]
//       Processor time of the mixer with N voices playing (default all 48).
//   sndtool selftest
//       Checks of the chip and the stream driver against their specification, on test
//       signals made here (no game data): decoding, pitch, length, envelope, loop, end
//       flags, volumes, stream rate, seams between stream pieces, channel routing.
//
// WAV files made from the game's data are game audio: keep them under local/.
#include "sound_rta.cpp"

#include <chrono>
#include <cmath>
#include <cstdarg>
#include <map>
#include <memory>
#include <string>
#include <thread>
#include <vector>

// ---- the runtime this program stands in for --------------------------------------------
u8* g_ram;
static u8* g_iop;
static u64 g_cycles;
static std::map<std::string, std::string> g_options;

u8* iop_ram() { return g_iop; }
u64 rt_cycles() { return g_cycles; }
const char* rt_option(const char* key) {
    auto it = g_options.find(key);
    return it == g_options.end() ? nullptr : it->second.c_str();
}

namespace {

const double FIELDS_PER_SECOND = 59.94;

[[noreturn]] void die(const char* format, const char* what = "") {
    fprintf(stderr, "sndtool: ");
    fprintf(stderr, format, what);
    fprintf(stderr, "\n");
    exit(2);
}

std::vector<u8> read_file(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) die("cannot read %s", path);
    std::vector<u8> data;
    u8 buffer[65536];
    size_t n;
    while ((n = fread(buffer, 1, sizeof buffer, f)) > 0) data.insert(data.end(), buffer, buffer + n);
    fclose(f);
    return data;
}

u32 rd32(const u8* p) { u32 v; memcpy(&v, p, 4); return v; }

struct Args {
    std::vector<std::string> plain;
    std::map<std::string, std::string> named;
    Args(int argc, char** argv, int from) {
        for (int i = from; i < argc; i++) {
            std::string a = argv[i];
            if (a == "--opt" && i + 1 < argc) {
                std::string kv = argv[++i];
                size_t eq = kv.find('=');
                g_options[kv.substr(0, eq)] = eq == std::string::npos ? "1" : kv.substr(eq + 1);
            } else if (a.rfind("--", 0) == 0 && i + 1 < argc) {
                named[a.substr(2)] = argv[++i];
            } else {
                plain.push_back(a);
            }
        }
    }
    double number(const char* key, double fallback) const {
        auto it = named.find(key);
        return it == named.end() ? fallback : atof(it->second.c_str());
    }
    const char* text(const char* key) const {
        auto it = named.find(key);
        return it == named.end() ? nullptr : it->second.c_str();
    }
};

void machine() {
    g_ram = (u8*)calloc(1, RAM_SIZE);
    g_iop = (u8*)calloc(1, IOP_RAM_SIZE);
}

void set_time(double seconds) { g_cycles = (u64)(seconds * (double)CYCLES_PER_SECOND); }

// a remote call as the game makes it: the argument block is put in main memory first
const u32 ARGS_AT = 0x008F6100, REPLY_AT = 0x008F6200;
u32 call(u32 server, u32 function, const u32* words, unsigned count) {
    memcpy(g_ram + ARGS_AT, words, count * 4);
    sound_rpc(server, function, ARGS_AT, count * 4, REPLY_AT, 64);
    return rd32(g_ram + REPLY_AT);
}
u32 sd(u32 function, u32 a = 0, u32 b = 0, u32 c = 0, u32 d = 0, u32 e = 0) {
    u32 words[7] = {ARGS_AT, a, b, c, d, e, 0};
    return call(0x80000701u, function, words, 7);
}
u32 hello(u32 function, u32 a = 0, u32 b = 0, u32 c = 0, u32 d = 0) {
    u32 words[4] = {a, b, c, d};
    return call(0x000163A5u, function, words, 4);
}

// What the game does once at start-up (0x212980 and sound_allocStreamBuffers), with the
// master volume option at its maximum.
const u32 RING[3] = {0x131400, 0x14B400, 0x16A400}, RING_SIZE[3] = {0x19000, 0x1E000, 0x40000};
void game_init() {
    sd(0x8000, 0);
    sd(0x8010, 0x980, 0x3FFF); sd(0x8010, 0xA80, 0x3FFF);
    sd(0x8010, 0x981, 0x3FFE); sd(0x8010, 0xA81, 0x3FFE);
    for (u32 core = 0; core < 2; core++) {
        sd(0x8010, 0xB80 | core, 0); sd(0x8010, 0xC80 | core, 0);
        sd(0x8010, 0xF80 | core, 0); sd(0x8010, 0x1080 | core, 0);
        if (core) { sd(0x8010, 0xD81, 0x7FFF); sd(0x8010, 0xE81, 0x7FFF); }
        sd(0x8030, 0x1300 | core, 0); sd(0x8030, 0x1400 | core, 0);
    }
    sd(0x8010, 0x800, 0xC00); sd(0x8010, 0x801, 0xC0C);
    for (u32 s = 0; s < 3; s++) hello(0x30, s, RING[s], RING_SIZE[s]);
    hello(0x20);
    hello(0x80, 1, 0x100, 0x100, 0x100);
}

// ---- replay ------------------------------------------------------------------------------

int replay(const Args& args) {
    if (args.plain.size() != 2) die("replay CAPTURE OUT.wav");
    std::vector<u8> capture = read_file(args.plain[0].c_str());
    if (capture.size() < 8 || memcmp(capture.data(), "RTASND1", 8)) die("%s is not a sound capture", args.plain[0].c_str());
    g_options["sound-wav"] = args.plain[1];
    FILE* iso = args.text("iso") ? fopen(args.text("iso"), "rb") : nullptr;
    if (args.text("iso") && !iso) die("cannot read %s", args.text("iso"));
    FILE* events = args.text("events") ? fopen(args.text("events"), "w") : nullptr;
    u32 last_frame = (u32)args.number("frames", 1e9);
    // --realtime 1: keep step with the wall clock from --from-frame on (for the device sink)
    bool realtime = args.number("realtime", 0) != 0;
    u32 first_frame = (u32)args.number("from-frame", 0);
    auto wall0 = std::chrono::steady_clock::now();
    machine();
    u32 frame = 0, shown = 0;
    u64 missing_disc = 0;
    auto note = [&](const char* format, ...) {
        if (!events) return;
        va_list list;
        va_start(list, format);
        fprintf(events, "%.4f\t%u\t", frame / FIELDS_PER_SECOND, frame);
        vfprintf(events, format, list);
        fprintf(events, "\n");
        va_end(list);
    };
    for (size_t at = 8; at + 12 <= capture.size();) {
        u32 type = rd32(&capture[at]), when = rd32(&capture[at + 4]), length = rd32(&capture[at + 8]);
        const u8* p = &capture[at + 12];
        at += 12 + length;
        if (when > last_frame) break;
        while (frame < when) {                      // the blanks in between
            frame++;
            set_time(frame / FIELDS_PER_SECOND);
            sound_vblank();
            if (realtime && frame >= first_frame)
                std::this_thread::sleep_until(wall0 + std::chrono::duration<double>((frame - first_frame) / FIELDS_PER_SECOND));
        }
        (void)shown;
        if (type == 1) {
            u32 server = rd32(p), function = rd32(p + 4), send = rd32(p + 8), send_size = rd32(p + 12), recv = rd32(p + 16), recv_size = rd32(p + 20);
            if (send < RAM_SIZE - 96) memcpy(g_ram + send, p + 24, length - 24);
            const u8* a = p + 24;
            u32 w[7] = {0};
            memcpy(w, a, length - 24 < 28 ? length - 24 : 28);
            if (events && server == 0x80000701u && (function & 0xFFF0) == 0x80B0) {
                for (u32 i = 0; i < w[3] && w[1] + i * 8 + 8 <= IOP_RAM_SIZE; i++) {
                    const u8* c = g_iop + w[1] + i * 8;
                    u16 f, e; memcpy(&f, c, 2); memcpy(&e, c + 2, 2);
                    static const char* const kReg[8] = {"VOLL", "VOLR", "PITCH", "ADSR1", "ADSR2", "ENVX", "VOLXL", "VOLXR"};
                    if (f == 1 && (e >> 8) < 8) note("batch\tcore %d voice %d %s=%x", e & 1, e >> 1 & 31, kReg[e >> 8], rd32(c + 4));
                    else if (f == 3 && (e >> 8) == 0x20) note("batch\tcore %d voice %d SSA=%x", e & 1, e >> 1 & 31, rd32(c + 4));
                    else if (f == 3 && (e >> 8) == 0x21) note("batch\tcore %d voice %d LSAX=%x", e & 1, e >> 1 & 31, rd32(c + 4));
                    else if (f == 2 && (e >> 8) == 0x15) note("batch\tcore %d KEY ON %06x", e & 1, rd32(c + 4));
                    else if (f == 2 && (e >> 8) == 0x16) note("batch\tcore %d KEY OFF %06x", e & 1, rd32(c + 4));
                    else note("batch\tfunction %x entry %04x value %x", f, e, rd32(c + 4));
                }
            }
            sound_rpc(server, function, send, send_size, recv, recv_size);
            if (events) {
                u32 answer = recv < RAM_SIZE - 64 ? rd32(g_ram + recv) : 0;
                if (server == 0x80000701u) {
                    u32 f = function & 0xFFF0;
                    if (f == 0x80D0) note("sd\tupload to %x, %x bytes", w[4], w[5]);
                    else if (f == 0x8040) note("sd\tget switch %04x -> %06x", w[1], answer);
                    else if (f == 0x80B0) note("sd\tbatch of %u -> %u", w[3], answer);
                    else if (f == 0x80F0) {}
                    else if (f == 0x81A0 || f == 0x81B0 || f == 0x8130) note("sd\t%x effect mode %d depth %d %d delay %d feedback %d -> %d", function, w[1], (s16)w[2], (s16)(w[2] >> 16), w[3], w[4], answer);
                    else note("sd\t%x %x %x %x -> %x", function, w[1], w[2], w[3], answer);
                } else {
                    const u32* r = (const u32*)(g_ram + recv);
                    if (function == 0x50) note("stream\tstatus\t%x %x %x %x | %x %x %x %x | %x %x %x %x", r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]);
                    else note("stream\t%x %x %x %x %x", function, w[0], w[1], w[2], w[3]);
                }
            }
        } else if (type == 2) {
            u32 address = rd32(p);
            if (address < IOP_RAM_SIZE && length - 4 <= IOP_RAM_SIZE - address) memcpy(g_iop + address, p + 4, length - 4);
        } else if (type == 3) {
            u32 address = rd32(p), sector = rd32(p + 4), count = rd32(p + 8);
            note("disc\t%u sectors from %u to %x", count, sector, address);
            if (address >= IOP_RAM_SIZE || (u64)count * 2048 > IOP_RAM_SIZE - address) continue;
            if (!iso) { missing_disc += count; continue; }
            fseeko(iso, (off_t)sector * 2048, SEEK_SET);
            if (fread(g_iop + address, 2048, count, iso) != count) missing_disc += count;
        } else if (type == 4) {
            note("label\t%.*s", (int)length, (const char*)p);
        }
    }
    double tail = args.number("tail", 2.0);
    for (u32 end = frame + (u32)(tail * FIELDS_PER_SECOND); frame < end;) {
        frame++;
        set_time(frame / FIELDS_PER_SECOND);
        sound_vblank();
    }
    sound_report();
    if (missing_disc) printf("replay: %llu disc sectors were not served (no --iso): stream data missing\n", (unsigned long long)missing_disc);
    if (events) fclose(events);
    return 0;
}

// ---- one sample --------------------------------------------------------------------------

int sample(const Args& args) {
    if (args.plain.size() != 2) die("sample FILE.vag OUT.wav");
    std::vector<u8> vag = read_file(args.plain[0].c_str());
    if (vag.size() < 0x40) die("%s is too short for a sample", args.plain[0].c_str());
    g_options["sound-wav"] = args.plain[1];
    machine();
    game_init();
    u32 rate = (u32)vag[0x10] << 24 | (u32)vag[0x11] << 16 | (u32)vag[0x12] << 8 | vag[0x13];
    u32 size = (u32)vag.size() - 0x30, pitch = (u32)(rate * 4096ull / 48000 * args.number("pitch", 1.0));
    if (args.text("pitch-register")) pitch = (u32)strtoul(args.text("pitch-register"), nullptr, 0);
    if (pitch > 0x3FFF) pitch = 0x3FFF;
    const u32 at = 0x8040, staging = 0x12FC00;
    hello(0xB0);
    for (u32 done = 0; done < size; done += 0x1000) {
        u32 n = size - done < 0x1000 ? size - done : 0x1000;
        memset(g_iop + staging, 0, 0x1000);
        memcpy(g_iop + staging, &vag[0x30 + done], n);
        sd(0x80D0, 0, 0, staging, at + done, n);
        sd(0x80F0, 0, 1);
    }
    hello(0xC0);
    set_time(0.1);
    // sound_playSample's batch for core 0 voice 0, then the key-on the flush adds
    struct { u16 function, entry; u32 value; } batch[] = {
        {1, 0x000, (u32)args.number("left", 0x3FFF)}, {1, 0x100, (u32)args.number("right", 0x3FFF)},
        {1, 0x200, pitch}, {3, 0x2040, at}, {1, 0x300, 0xFF}, {1, 0x400, 0x1FC0}, {3, 0x2140, 0x5000}, {2, 0x1500, 1}};
    memcpy(g_iop + 0x12EC00, batch, sizeof batch);
    sd(0x80B0, 0x12EC00, 0, sizeof batch / 8);
    double seconds = args.number("seconds", 0), t = 0.1;
    int polls = 0;
    for (;; polls++) {
        t += 1 / FIELDS_PER_SECOND;
        set_time(t);
        sound_vblank();
        if (seconds > 0 ? t >= 0.1 + seconds : (sd(0x8040, 0x1700) & 1) || t > 120) break;
    }
    printf("sample: rate %u Hz, %u bytes (%.3f s), pitch register %x; ended after %.3f s\n", rate, size, size / 16 * 28.0 / rate, pitch, t - 0.1);
    set_time(t + 0.25);
    sound_report();
    return 0;
}

// ---- one stream --------------------------------------------------------------------------

int stream(const Args& args) {
    if (args.plain.size() != 3) die("stream FILE.raw 1|2 OUT.wav");
    std::vector<u8> data = read_file(args.plain[0].c_str());
    u32 channels = (u32)atoi(args.plain[1].c_str());
    g_options["sound-wav"] = args.plain[2];
    u32 s = (u32)args.number("on-stream", channels == 2 ? 2 : 1);
    double seconds = args.number("seconds", 0);
    machine();
    game_init();
    hello(0x70, s, 0x3FFF);
    // The game's feeding, reduced: whenever the ring has room for a whole number of
    // 0x800-byte pieces, read them "from the disc" and tell the driver.
    size_t fed = 0;
    bool first = true;
    double t = 0;
    u32 total = (u32)(data.size() & ~0x7FFu);
    for (int field = 0;; field++) {
        t = field / FIELDS_PER_SECOND;
        set_time(t);
        sound_vblank();
        if (seconds > 0 && t >= seconds) break;
        if (field % 4) continue;
        hello(0x50);
        const u32* st = (const u32*)(g_ram + REPLY_AT) + s * 4;
        u32 write = st[0], read = st[1], played = st[3];
        u32 used = (write + RING_SIZE[s] - read) % RING_SIZE[s];
        if (fed >= total) {
            if (used == 0 && played >= total) break;
            continue;
        }
        u32 room = (RING_SIZE[s] - 0x800 - used) & ~0x7FFu;
        u32 n = total - fed < room ? total - (u32)fed : room;
        if (!n || (n < 0x8000 && n != total - fed)) continue;      // large pieces, as the game reads them
        for (u32 i = 0; i < n; i++) g_iop[RING[s] + (write + i) % RING_SIZE[s]] = data[fed + i];
        hello(0x40, s, n, 24000, (channels == 2 ? 1 : 0) | (first ? 0x10000 : 0));
        first = false;
        fed += n;
    }
    printf("stream: %u bytes on stream %u, %u channel(s): %.3f s of data at 23,976.6 Hz; ran %.3f s\n", total, s, channels,
           total / 16 * 28.0 / channels / (48000.0 * 0x7FE / 0x1000), t);
    set_time(t + 0.5);
    sound_report();
    return 0;
}

// ---- cost --------------------------------------------------------------------------------

int bench(const Args& args) {
    int voices = (int)args.number("voices", 48);
    double seconds = args.number("seconds", 60);
    machine();
    g_options["sound-off"] = "0";
    game_init();
    // a looping sample of pseudo-random blocks at 0x8040
    const u32 at = 0x8040, blocks = 256;
    u32 seed = 12345;
    memset(g_iop + 0x100000, 0, blocks * 16);
    for (u32 b = 0; b < blocks; b++) {
        u8* p = g_iop + 0x100000 + b * 16;
        p[0] = (u8)(((b % 5) << 4) | 4);
        p[1] = b == 0 ? 6 : b == blocks - 1 ? 3 : 2;
        for (int i = 2; i < 16; i++) { seed = seed * 1664525 + 1013904223; p[i] = (u8)(seed >> 24); }
    }
    sd(0x80D0, 0, 0, 0x100000, at, blocks * 16);
    std::vector<u32> batch;
    for (int v = 0; v < voices && v < 43; v++) {
        u32 e = v < 24 ? (u32)v << 1 : ((u32)(v - 24) << 1) | 1;
        u32 words[][2] = {{1 | e << 16, 0x0800}, {1 | (e | 0x100) << 16, 0x0800}, {1 | (e | 0x200) << 16, 0x0600 + (u32)v * 37},
                          {3 | (e | 0x2040) << 16, at}, {1 | (e | 0x300) << 16, 0xFF}, {1 | (e | 0x400) << 16, 0x1FC0}};
        for (auto& w : words) { batch.push_back(w[0]); batch.push_back(w[1]); }
    }
    batch.push_back(2 | 0x1500 << 16); batch.push_back(voices >= 24 ? 0xFFFFFF : (1u << voices) - 1);
    batch.push_back(2 | 0x1501 << 16); batch.push_back(voices > 24 ? (1u << (voices > 43 ? 19 : voices - 24)) - 1 : 0);
    memcpy(g_iop + 0x12EC00, batch.data(), batch.size() * 4);
    sd(0x80B0, 0x12EC00, 0, (u32)batch.size() / 2);
    auto t0 = std::chrono::steady_clock::now();
    for (double t = 0; t < seconds; t += 1 / FIELDS_PER_SECOND) { set_time(t); sound_vblank(); }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    printf("bench: %d effect voices + 5 stream voices for %.0f s of sound: %.3f s of processor time = %.2f%% of one core; %d voices sounding at the end\n",
           voices > 43 ? 43 : voices, seconds, wall, wall * 100 / seconds, g_engine->spu.voices_sounding());
    sound_report();
    return 0;
}

// ---- self test: the chip and the stream driver against what they are specified to do -------
//
// No game data: the test encodes its own ADPCM (no prediction, four bits a sample), so it
// knows exactly what a voice must put out.

struct Memory : rta::snd::AudioSink {
    std::vector<int16_t> data;
    void write(const int16_t* stereo, size_t frames) override { data.insert(data.end(), stereo, stereo + frames * 2); }
};

struct Bench {
    std::unique_ptr<rta::snd::Engine> owned;      // 2 MB of sample memory: not on the stack
    rta::snd::Engine& engine;
    Memory out;
    std::vector<u8> iop;
    Bench() : owned(new rta::snd::Engine()), engine(*owned), iop(IOP_RAM_SIZE) {
        engine.set_iop_memory(iop.data(), iop.size());
        engine.set_sink(&out);
        engine.max_jump = ~0ull;
        // start-up as the game does it
        sdc(0x8000);
        sdc(0x8010, 0x980, 0x3FFF); sdc(0x8010, 0xA80, 0x3FFF); sdc(0x8010, 0x981, 0x3FFF); sdc(0x8010, 0xA81, 0x3FFF);
        sdc(0x8010, 0xD81, 0x7FFF); sdc(0x8010, 0xE81, 0x7FFF);
        sdc(0x8010, 0x800, 0xC00); sdc(0x8010, 0x801, 0xC0C);
        for (u32 s = 0; s < 3; s++) hc(0x30, s, RING[s], RING_SIZE[s]);
        hc(0x20); hc(0x80, 1, 0x100, 0x100, 0x100);
    }
    u32 sdc(u32 function, u32 a = 0, u32 b = 0, u32 c = 0, u32 d = 0, u32 e = 0) {
        u32 w[7] = {0, a, b, c, d, e, 0}, r[16] = {0};
        engine.rpc(0x80000701u, function, (const u8*)w, sizeof w, (u8*)r, sizeof r);
        return r[0];
    }
    const u32* hc(u32 function, u32 a = 0, u32 b = 0, u32 c = 0, u32 d = 0) {
        static u32 r[16];
        u32 w[4] = {a, b, c, d};
        engine.rpc(0x000163A5u, function, (const u8*)w, sizeof w, (u8*)r, sizeof r);
        return r;
    }
    void run(u64 samples) { engine.advance_to(engine.position() + samples); }
    void upload(u32 at, const std::vector<u8>& blocks) {
        memcpy(&iop[0x100000], blocks.data(), blocks.size());
        sdc(0x80D0, 0, 0, 0x100000, at, (u32)blocks.size());
    }
    // sound_playSample's registers and the key-on, for an effect voice
    void play(u32 entry, u32 at, u32 pitch, u32 left, u32 right) {
        u32 b[] = {1 | entry << 16, left, 1 | (entry | 0x100) << 16, right, 1 | (entry | 0x200) << 16, pitch,
                   3 | (entry | 0x2040) << 16, at, 1 | (entry | 0x300) << 16, 0xFF, 1 | (entry | 0x400) << 16, 0x1FC0,
                   3 | (entry | 0x2140) << 16, 0x5000, 2 | (0x1500 | (entry & 1)) << 16, 1u << (entry >> 1 & 31)};
        memcpy(&iop[0x12EC00], b, sizeof b);
        sdc(0x80B0, 0x12EC00, 0, sizeof b / 8);
    }
};

// ADPCM without prediction: every sample is a 4-bit number times 2^(12 - shift)
std::vector<u8> encode(const std::vector<int>& pcm, int shift, std::vector<int>* decoded, int loop_start_block = -1, bool repeat = false) {
    std::vector<u8> out;
    int q = 1 << (12 - shift);
    size_t blocks = (pcm.size() + 27) / 28;
    for (size_t b = 0; b < blocks; b++) {
        u8 block[16] = {(u8)shift, 0};
        if ((int)b == loop_start_block) block[1] |= 4;
        if (loop_start_block >= 0) block[1] |= 2;
        if (b + 1 == blocks) block[1] |= repeat ? 3 : 1;
        for (int i = 0; i < 28; i++) {
            size_t k = b * 28 + (size_t)i;
            int n = k < pcm.size() ? (int)lrint((double)pcm[k] / q) : 0;
            n = n < -8 ? -8 : n > 7 ? 7 : n;
            if (decoded) decoded->push_back(n * q);
            block[2 + i / 2] |= (u8)((n & 15) << (i & 1) * 4);
        }
        out.insert(out.end(), block, block + 16);
    }
    return out;
}

std::vector<int> tone(size_t samples, double period, double amplitude) {
    std::vector<int> pcm(samples);
    for (size_t i = 0; i < samples; i++) pcm[i] = (int)lrint(amplitude * sin(2 * 3.14159265358979323846 * (double)i / period));
    return pcm;
}

// frequency of a clean tone from its rising zero crossings, in cycles per sample
double frequency(const std::vector<int16_t>& stereo, int channel, size_t from, size_t to) {
    double first = -1, last = -1; long count = 0;
    for (size_t i = from + 1; i < to; i++) {
        int a = stereo[(i - 1) * 2 + (size_t)channel], b = stereo[i * 2 + (size_t)channel];
        if (a < 0 && b >= 0) {
            double t = (double)(i - 1) + (double)-a / (double)(b - a);
            if (first < 0) first = t;
            last = t; count++;
        }
    }
    return count > 1 ? (double)(count - 1) / (last - first) : 0;
}

double level(const std::vector<int16_t>& stereo, int channel, size_t from, size_t to) {
    double sum = 0;
    for (size_t i = from; i < to; i++) sum += (double)stereo[i * 2 + (size_t)channel] * stereo[i * 2 + (size_t)channel];
    return sqrt(sum / (double)(to - from));
}

int selftest(const Args&) {
    int failed = 0, number = 0;
    setvbuf(stdout, nullptr, _IOLBF, 0);
    auto check = [&](bool ok, const char* what, const char* format, ...) {
        char text[256];
        va_list list;
        va_start(list, format);
        vsnprintf(text, sizeof text, format, list);
        va_end(list);
        printf("%s %2d %-58s %s\n", ok ? "ok  " : "FAIL", ++number, what, text);
        if (!ok) failed++;
    };
    const u32 AT = 0x8040;

    {   // 1-4: a one-shot at pitch 0x1000 without interpolation comes out sample for sample
        Bench t;
        t.engine.spu.set_interpolation(rta::snd::Spu2::NEAREST);
        std::vector<int> want;
        t.upload(AT, encode(tone(28 * 40, 48.0, 7 * 4096.0), 0, &want));
        t.run(100);
        size_t start = t.out.data.size() / 2;
        t.play(0, AT, 0x1000, 0x3FFF, 0x3FFF);
        t.run(28 * 40 + 200);
        // the first decoded sample is heard one tick after the key-on; the envelope is full after 3
        long best = -1; double top = 0, gain = 0;
        for (long lag = 0; lag < 8; lag++) {
            double ab = 0, aa = 0, bb = 0;
            for (size_t i = 8; i < want.size(); i++) { double a = want[i], b = t.out.data[(start + (size_t)lag + i) * 2]; ab += a * b; aa += a * a; bb += b * b; }
            double c = ab / sqrt(aa * bb);
            if (c > top) { top = c; best = lag; gain = ab / aa; }
        }
        check(top > 0.99999 && best == 1, "one-shot, pitch 0x1000: output is the decoded data", "correlation %.6f at a delay of %ld sample(s)", top, best);
        check(fabs(gain - 0.99979) < 0.0005, "gain through voice, core 0, core 1 at full volumes", "%.5f (0x7ffe/0x8000 three times and 0x7fff once: 0.99979)", gain);
        size_t end = start + 1 + want.size();
        bool silent = true;
        for (size_t i = end + 2; i < t.out.data.size() / 2; i++) silent = silent && t.out.data[i * 2] == 0;
        check(silent, "silent after the block flagged 1", "");
        check((t.sdc(0x8040, 0x1700) & 1) == 1, "end flag set when the sample has run out", "ENDX core 0 = %06x", t.sdc(0x8040, 0x1700));
    }
    {   // 5: end flag timing and clearing
        Bench t;
        t.upload(AT, encode(tone(28 * 100, 48.0, 1500), 4, nullptr));
        t.play(0, AT, 0x1000, 0x3FFF, 0x3FFF);
        bool cleared = !(t.sdc(0x8040, 0x1700) & 1);
        t.run(28 * 100 - 30);
        bool before = !(t.sdc(0x8040, 0x1700) & 1);
        t.run(60);
        bool after = t.sdc(0x8040, 0x1700) & 1;
        check(cleared && before && after, "key-on clears the end flag; set 2,800 samples later", "cleared %d, not yet at 2,770: %d, set at 2,830: %d", cleared, before, after);
    }
    {   // 6-7: pitch
        const u32 pitches[] = {0x0400, 0x0800, 0x0C3F, 0x1000, 0x2000, 0x3FFF};
        double worst = 0; u32 worst_pitch = 0; bool lengths = true;
        for (u32 pitch : pitches) {
            Bench t;
            size_t n = 28 * 3000;
            t.upload(AT, encode(tone(n, 96.0, 7 * 4096.0), 0, nullptr));
            t.play(0, AT, pitch, 0x3FFF, 0x3FFF);
            u64 ticks = (u64)n * 0x1000 / pitch;
            t.run(ticks - 200);
            lengths = lengths && !(t.sdc(0x8040, 0x1700) & 1);
            t.run(400);
            lengths = lengths && (t.sdc(0x8040, 0x1700) & 1);
            double f = frequency(t.out.data, 0, 100, (size_t)ticks - 300), expect = pitch / 4096.0 / 96.0;
            double error = fabs(f / expect - 1) * 1e6;
            if (error > worst) { worst = error; worst_pitch = pitch; }
        }
        check(worst < 60, "tone frequency follows pitch / 0x1000 (six pitches)", "worst error %.1f ppm at pitch %x", worst, worst_pitch);
        check(lengths, "length is samples x 0x1000 / pitch (six pitches)", "end flag inside +-200 ticks of it each time");
    }
    {   // 8-9: envelope 0xff / 0x1fc0 is a gate
        Bench t;
        t.engine.spu.set_interpolation(rta::snd::Spu2::NEAREST);
        std::vector<int> flat(28 * 200, 7 * 4096);
        t.upload(AT, encode(flat, 0, nullptr, 0, true));
        size_t start = t.out.data.size() / 2;
        t.play(0, AT, 0x1000, 0x3FFF, 0x3FFF);
        t.run(1000);
        int16_t* o = &t.out.data[start * 2];
        check(o[0] == 0 && o[2] > 0 && o[2 * 3] > 28672 * 0.999 && o[2 * 3] == o[2 * 500], "attack: full level within 3 samples of the first one heard", "first samples %d %d %d %d %d, later %d (data 28672)", o[0], o[2], o[4], o[6], o[8], o[1000]);
        size_t off = t.out.data.size() / 2;
        u32 b[] = {2 | 0x1600 << 16, 1};
        memcpy(&t.iop[0x12EC00], b, sizeof b);
        t.sdc(0x80B0, 0x12EC00, 0, 1);
        t.run(100);
        o = &t.out.data[off * 2];
        check(o[2 * 3] == 0 && o[2 * 50] == 0, "release: silent within 3 samples of the key-off", "samples after key-off %d %d %d %d", o[0], o[2], o[4], o[6]);
    }
    {   // 10-11: loop from the block flagged 6 to the block flagged 3
        Bench t;
        t.engine.spu.set_interpolation(rta::snd::Spu2::NEAREST);
        std::vector<int> pcm, want;
        for (int i = 0; i < 28 * 4; i++) pcm.push_back(((i * 37) % 15 - 7) * 4096);
        t.upload(AT, encode(pcm, 0, &want, 1, true));
        size_t start = t.out.data.size() / 2;
        t.play(0, AT, 0x1000, 0x3FFF, 0x3FFF);
        t.run(28 * 4 + 84 * 200);
        bool periodic = true, first_pass = true;
        const int16_t* o = &t.out.data[(start + 1) * 2];
        for (size_t i = 28 * 4; i < 28 * 4 + 84 * 199; i++) periodic = periodic && o[i * 2] == o[(i - 84) * 2];
        for (size_t i = 8; i < 28 * 4; i++) first_pass = first_pass && abs(o[i * 2] - want[i]) <= 4 + abs(want[i]) / 2000;
        for (size_t i = 0; i < 84; i++) first_pass = first_pass && abs(o[(28 * 4 + i) * 2] - want[28 + i]) <= 4 + abs(want[28 + i]) / 2000;
        check(first_pass, "loop: after the last block the data from the loop start follows", "");
        check(periodic && t.engine.spu.voices_sounding() >= 1, "loop: repeats every 84 samples for 200 rounds, still sounding", "end flag %d", t.sdc(0x8040, 0x1700) & 1);
    }
    {   // 12: volumes
        Bench t;
        t.upload(AT, encode(tone(28 * 400, 48.0, 7 * 4096.0), 0, nullptr, 0, true));
        t.play(0, AT, 0x1000, 0x3FFF, 0);
        t.run(4800);
        double l1 = level(t.out.data, 0, 1000, 4800), r1 = level(t.out.data, 1, 1000, 4800);
        t.play(0, AT, 0x1000, 0x2000, 0x1000);
        t.run(4800);
        double l2 = level(t.out.data, 0, 5800, 9600), r2 = level(t.out.data, 1, 5800, 9600);
        check(r1 == 0 && fabs(20 * log10(l2 / l1) + 6.02) < 0.02 && fabs(20 * log10(r2 / l1) + 12.04) < 0.03, "left and right volume registers",
              "0x3fff/0: right silent; 0x2000: %.2f dB; 0x1000: %.2f dB", 20 * log10(l2 / l1), 20 * log10(r2 / l1));
    }
    {   // 13-15: a one-voice stream (speech): rate, length, no seam at the buffer halves
        Bench t;
        size_t bytes = 0x800 * 40;
        std::vector<u8> data = encode(tone(bytes / 16 * 28, 40.0, 7 * 4096.0), 0, nullptr);
        memcpy(&t.iop[RING[1]], data.data(), bytes);
        t.hc(0x70, 1, 0x3FFF);
        t.run(4800);
        t.hc(0x40, 1, (u32)bytes, 24000, 0x10000);
        double seconds = bytes / 16 * 28 / (48000.0 * 0x7FE / 0x1000);
        u64 start = t.engine.position();
        t.run((u64)((seconds + 1.0) * 48000));
        const u32* st = t.hc(0x50) + 4;
        // where the tone is
        size_t first = 0, last = 0;
        for (size_t i = (size_t)start; i < t.out.data.size() / 2; i++)
            if (abs(t.out.data[i * 2]) > 2000) { if (!first) first = i; last = i; }
        if (last < first + 4800) { check(false, "one-voice stream", "no tone came out: write %x read %x volume %x played %x", st[0], st[1], st[2], st[3]); first = (size_t)start; last = first + 9600; }
        double f = frequency(t.out.data, 0, first + 480, last - 480), expect = 0x7FE / 4096.0 / 40.0;
        check(fabs(f / expect - 1) * 1e6 < 30, "stream voice plays at 23,976.6 Hz", "tone at %.2f Hz, expected %.2f (%.1f ppm)", f * 48000, expect * 48000, (f / expect - 1) * 1e6);
        check(fabs((double)(last - first) / 48000 - seconds) < 0.01 && st[0] == st[1] && st[3] == bytes, "stream length and counters",
              "sounded %.3f s for %.3f s of data; write %x read %x played %x", (double)(last - first) / 48000, seconds, st[0], st[1], st[3]);
        // a seam would show as a zero crossing out of step: every period must be 80.08 output samples
        double worst = 0, previous = -1;
        for (size_t i = first + 480; i < last - 480; i++) {
            int a = t.out.data[(i - 1) * 2], b = t.out.data[i * 2];
            if (a < 0 && b >= 0) {
                double at = (double)(i - 1) + (double)-a / (double)(b - a);
                if (previous >= 0 && fabs(at - previous - 1 / expect) > worst) worst = fabs(at - previous - 1 / expect);
                previous = at;
            }
        }
        check(worst < 0.5, "no seam where the buffer halves change (40 pieces)", "largest period error %.3f samples of %.2f", worst, 1 / expect);
    }
    {   // 16-18: a two-voice stream (music): the 0x400-byte pieces go left and right
        Bench t;
        size_t pieces = 80;
        std::vector<u8> left = encode(tone(pieces * 0x400 / 16 * 28, 40.0, 7 * 4096.0), 0, nullptr);
        std::vector<u8> right = encode(tone(pieces * 0x400 / 16 * 28, 56.0, 7 * 4096.0), 0, nullptr);
        for (size_t p = 0; p < pieces; p++) {
            memcpy(&t.iop[RING[2] + p * 0x800], &left[p * 0x400], 0x400);
            memcpy(&t.iop[RING[2] + p * 0x800 + 0x400], &right[p * 0x400], 0x400);
        }
        t.hc(0x70, 2, 0x3FFF);
        t.run(4800);
        t.hc(0x40, 2, (u32)(pieces * 0x800), 24000, 0x10001);
        u64 start = t.engine.position();
        t.run(48000 * 4);
        size_t a = (size_t)start + 48000, b = (size_t)start + 48000 * 3;
        double fl = frequency(t.out.data, 0, a, b) * 48000, fr = frequency(t.out.data, 1, a, b) * 48000;
        double el = 23976.5625 / 40, er = 23976.5625 / 56;
        check(fabs(fl / el - 1) < 1e-4 && fabs(fr / er - 1) < 1e-4, "two-channel entry: left pieces left, right pieces right", "left %.2f Hz (%.2f), right %.2f Hz (%.2f)", fl, el, fr, er);
        double worst = 0, previous = -1;
        for (size_t i = a; i < b; i++) {
            int x = t.out.data[(i - 1) * 2 + 1], y = t.out.data[i * 2 + 1];
            if (x < 0 && y >= 0) {
                double at = (double)(i - 1) + (double)-x / (double)(y - x);
                if (previous >= 0 && fabs(at - previous - 48000 / er) > worst) worst = fabs(at - previous - 48000 / er);
                previous = at;
            }
        }
        check(worst < 0.5, "no seam between pieces on the right voice", "largest period error %.3f samples", worst);
        // the same ring as a one-channel entry: both voices get every piece
        Bench u;
        memcpy(&u.iop[RING[2]], left.data(), 0x400 * 40);
        u.hc(0x70, 2, 0x3FFF);
        u.run(4800);
        u.hc(0x40, 2, 0x400 * 40, 24000, 0x10000);
        start = u.engine.position();
        u.run(48000 * 2);
        bool same = true;
        for (size_t i = (size_t)start; i < u.out.data.size() / 2; i++) same = same && u.out.data[i * 2] == u.out.data[i * 2 + 1];
        double f = frequency(u.out.data, 0, (size_t)start + 24000, (size_t)start + 72000) * 48000;
        check(same && fabs(f / el - 1) < 1e-4, "one-channel entry on a two-voice stream: the same on both sides", "%.2f Hz on both", f);
    }
    {   // 19: stream volume ramp and scale
        Bench t;
        std::vector<u8> data = encode(std::vector<int>(0x800 * 30 / 16 * 28, 7 * 4096), 0, nullptr);
        memcpy(&t.iop[RING[1]], data.data(), data.size());
        t.hc(0x40, 1, (u32)data.size(), 24000, 0x10000);
        t.hc(0x70, 1, 0);
        t.run(48000);
        t.hc(0x80, 1, 0x100, 0x80, 0x100);
        t.hc(0x70, 1, 0x3000);
        u64 start = t.engine.position();
        t.run(288 * 70);
        u32 v = t.hc(0x50)[6];
        size_t at = (size_t)start + 288 * 66;
        double l = level(t.out.data, 0, at, at + 200);
        check(v == 0x3000 && fabs(l / 28672.0 - 0.375) < 0.002, "stream volume: +0xc0 a tick to the target, times scale / 0x100", "volume %x after 70 ticks; level %.4f of the data's (0x3000 / 0x4000 x 0x80 / 0x100 = 0.3750)", v, l / 28672.0);
    }
    printf("%d checks, %d failed\n", number, failed);
    return failed ? 1 : 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) die("replay | sample | stream | bench | selftest  (see the head of sndtool.cpp)");
    std::string command = argv[1];
    Args args(argc, argv, 2);
    if (command == "replay") return replay(args);
    if (command == "sample") return sample(args);
    if (command == "stream") return stream(args);
    if (command == "bench") return bench(args);
    if (command == "selftest") return selftest(args);
    die("unknown command %s", argv[1]);
}
