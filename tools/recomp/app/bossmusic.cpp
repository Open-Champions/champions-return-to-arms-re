// bossmusic.cpp - see bossmusic.h.
#include "bossmusic.h"

#include "gamestate.h"
#include "iface.h"          // rta::memory(): main memory, read only here
#include "soulscombat.h"    // the lock-on of the souls-style mode (its local block in guest memory)
#include "fpaim.h"          // music.boss = auto: on when a Remastered mode (Hardcore, aiming) is wanted
#include "app_rt.h"         // apprt::set_music_volume: the stream driver's music stream alone

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <mutex>
#include <random>
#include <thread>
#include <vector>

// ---- the decoders (tools/recomp/app/vendor/README.txt: versions, sources, licences) ----------------
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Weverything"
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wall"
#pragma GCC diagnostic ignored "-Wextra"
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wmisleading-indentation"
#endif
#define STB_VORBIS_NO_PUSHDATA_API
#include "vendor/stb_vorbis.c"
#undef L          // stb_vorbis leaves a few one-letter macros behind
#undef C
#undef R
#define DR_MP3_IMPLEMENTATION
#define DR_MP3_NO_SIMD_WARNINGS
#include "vendor/dr_mp3.h"
#define DR_WAV_IMPLEMENTATION
#include "vendor/dr_wav.h"
#if defined(__clang__)
#pragma clang diagnostic pop
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

// the sound library's hook (tools/recomp/sound/drivers.cpp): called with every block of output samples after the chip
extern "C" void rta_sound_set_host_mix(void (*mix)(int16_t* stereo, size_t frames)) __attribute__((weak));

namespace bossmusic {
namespace {

const unsigned RATE = 48000;                    // the sound side's output rate
const double FADE_IN = 1.6, FADE_OUT = 3.0, HOLD_AFTER = 4.0;      // seconds (music.gd)
const double LONGEST = 20 * 60;                 // seconds of a track that are kept (a longer one is cut there)

struct Track {
    std::string path;
    std::vector<int16_t> pcm;                   // 48 kHz, stereo
    size_t frames() const { return pcm.size() / 2; }
};

std::string lower_ext(const std::string& path) {
    std::string e = std::filesystem::path(path).extension().string();
    for (auto& ch : e) ch = (char)tolower((unsigned char)ch);
    return e;
}
std::string file_name(const std::string& path) { return std::filesystem::path(path).filename().string(); }

// A whole file to 48 kHz stereo 16 bit.  On the loader's thread.
std::shared_ptr<Track> decode(const std::string& path, std::string& why) {
    int16_t* data = nullptr;
    uint64_t frames = 0;
    unsigned channels = 0, rate = 0;
    std::string ext = lower_ext(path);
    void (*release)(void*) = free;
    if (ext == ".ogg") {
        int ch = 0, r = 0;
        short* out = nullptr;
        int n = stb_vorbis_decode_filename(path.c_str(), &ch, &r, &out);
        if (n > 0 && out) { data = out; frames = (uint64_t)n; channels = (unsigned)ch; rate = (unsigned)r; }
    } else if (ext == ".mp3") {
        drmp3_config config{};
        drmp3_uint64 n = 0;
        data = drmp3_open_file_and_read_pcm_frames_s16(path.c_str(), &config, &n, nullptr);
        frames = n; channels = config.channels; rate = config.sampleRate;
        release = [](void* p) { drmp3_free(p, nullptr); };
    } else if (ext == ".wav") {
        drwav_uint64 n = 0;
        unsigned ch = 0, r = 0;
        data = drwav_open_file_and_read_pcm_frames_s16(path.c_str(), &ch, &r, &n, nullptr);
        frames = n; channels = ch; rate = r;
        release = [](void* p) { drwav_free(p, nullptr); };
    }
    if (!data || !frames || !channels || rate < 4000 || rate > 384000) {
        if (data) release(data);
        why = "not a file of that kind the decoders read";
        return nullptr;
    }
    if ((double)frames / rate > LONGEST) frames = (uint64_t)(LONGEST * rate);
    auto t = std::make_shared<Track>();
    t->path = path;
    uint64_t out_frames = (uint64_t)((double)frames * RATE / rate);
    t->pcm.resize((size_t)out_frames * 2);
    auto at = [&](uint64_t k, unsigned c) -> float {       // channel c of frame k (mono to both; more than two: the first two)
        if (k >= frames) k = frames - 1;
        return (float)data[k * channels + (channels >= 2 ? c : 0)];
    };
    double step = (double)rate / RATE;
    for (uint64_t i = 0; i < out_frames; i++) {
        double x = i * step;
        uint64_t k = (uint64_t)x;
        float f = (float)(x - (double)k);
        for (unsigned c = 0; c < 2; c++) {
            float v = rate == RATE ? at(i, c) : at(k, c) + (at(k + 1, c) - at(k, c)) * f;
            t->pcm[i * 2 + c] = (int16_t)std::lround(std::clamp(v, -32768.0f, 32767.0f));
        }
    }
    release(data);
    return t;
}

// ---- the mixer: the sound library's thread (or the game's, on the machine's clock) ------------------
std::mutex g_mix_lock;                          // held for microseconds: by the mixer for one block, by the director to swap a track
std::shared_ptr<Track> g_mix_track;
size_t g_mix_pos = 0;
float g_mix_gain = 0;                           // where the ramp is
std::atomic<float> g_target{0.0f};              // what the director asks for: eased level x volume
std::atomic<uint64_t> g_mixed_frames{0};
std::atomic<float> g_peak{0.0f};                // the largest sample the player's track added since the last report (0..1)
std::atomic<bool> g_hooked{false};

void mix(int16_t* stereo, size_t n) {
    std::lock_guard<std::mutex> hold(g_mix_lock);
    const Track* t = g_mix_track.get();
    if (!t || !t->frames()) return;
    float target = g_target.load(std::memory_order_relaxed), gain = g_mix_gain;
    if (target <= 0 && gain <= 0) return;
    const float step = 1.0f / 960;              // at most full scale in 20 ms: the director's steps are smoothed, never clicks
    size_t pos = g_mix_pos, frames = t->frames();
    const int16_t* p = t->pcm.data();
    float peak = 0;
    for (size_t i = 0; i < n; i++) {
        if (gain < target) gain = std::min(target, gain + step);
        else if (gain > target) gain = std::max(target, gain - step);
        for (int c = 0; c < 2; c++) {
            float add = p[pos * 2 + c] * gain;
            float a = std::fabs(add);
            if (a > peak) peak = a;
            int v = stereo[i * 2 + c] + (int)std::lround(add);
            stereo[i * 2 + c] = (int16_t)(v < -32768 ? -32768 : v > 32767 ? 32767 : v);
        }
        if (++pos >= frames) pos = 0;           // looped
    }
    g_mix_pos = pos;
    g_mix_gain = gain;
    g_mixed_frames.fetch_add(n, std::memory_order_relaxed);
    float was = g_peak.load(std::memory_order_relaxed);
    if (peak / 32768.0f > was) g_peak.store(peak / 32768.0f, std::memory_order_relaxed);
}

// ---- the director: the game's thread, at the vertical blank ---------------------------------------
enum State { IDLE, LOADING, PLAYING, LEAVING };
const char* STATE_NAMES[] = {"idle", "loading", "playing", "leaving"};

struct Load {                                   // one file on the loader's thread
    std::string path;
    std::shared_ptr<Track> track;
    std::string why;
    std::atomic<bool> done{false};
};

struct Director {
    int mode = -1;                              // music.boss: 1 on, 0 off, -1 auto (on only with a Remastered mode: enabled())
    double volume = 0.8;
    std::string dir_setting, data;
    std::string folder;                         // what was scanned
    std::vector<std::string> tracks, bag;
    std::string last_track, scanned_for;
    bool scanned = false;
    State state = IDLE;
    double level = 0, calm_for = 0;
    uint64_t last_frame = 0;
    std::shared_ptr<Load> load;
    double game_base = 1.0;                     // the game's music as the player set it
    double game_applied = -1;                   // what the stream driver was last told
    bool force = false;                         // "app music engage on|off|auto": a test aid
    int forced = -1;
    int log_lines = 0;
    uint64_t engaged_frames = 0, played = 0;
    std::mt19937 rng{std::random_device{}()};
    rta_gs_reader* reader = nullptr;
    const rta_gamestate* st = nullptr;
} D;

// music.boss = auto (the default): a Remastered feature, so on only when the program plays a Remastered game - Hardcore
// (combat.mode) or aiming by looking (combat.aim) wanted - and off in Classic, the original with the art pack and 60
// a second, as the portal maps it (tools/godot/project/portal/edition.gd: boss music is Remastered's).
bool enabled() { return D.mode == 1 || (D.mode < 0 && (soulscombat::wanted() || fpaim::wanted())); }

void say(const std::string& text) {
    if (D.log_lines >= 200) return;
    D.log_lines++;
    printf("boss music: %s [machine %.2f s]\n", text.c_str(), apprt::machine_seconds());
    fflush(stdout);
}

std::string folder_now() {
    if (!D.dir_setting.empty()) return D.dir_setting;
    std::string data = D.data.empty() ? std::string(".") : D.data;
    return (std::filesystem::path(data) / "music" / "boss").string();
}

void scan() {
    D.folder = folder_now();
    D.tracks.clear();
    std::error_code ec;
    for (std::filesystem::directory_iterator it(D.folder, ec), end; !ec && it != end; it.increment(ec)) {
        if (!it->is_regular_file(ec)) continue;
        std::string name = it->path().filename().string(), ext = lower_ext(name);
        if (name.empty() || name[0] == '.') continue;
        if (ext == ".ogg" || ext == ".mp3" || ext == ".wav") D.tracks.push_back(it->path().string());
    }
    std::sort(D.tracks.begin(), D.tracks.end());
    D.bag.erase(std::remove_if(D.bag.begin(), D.bag.end(),
                               [](const std::string& p) { return std::find(D.tracks.begin(), D.tracks.end(), p) == D.tracks.end(); }), D.bag.end());
    D.scanned = true;
    char line[64];
    snprintf(line, sizeof line, "%zu track(s) in ", D.tracks.size());
    say(line + D.folder);
}

std::string next_track() {
    // shuffle: every track once before any comes again, and not the same one twice in a row across two rounds
    if (D.bag.empty()) {
        D.bag = D.tracks;
        std::shuffle(D.bag.begin(), D.bag.end(), D.rng);
        if (D.bag.size() > 1 && D.bag.back() == D.last_track) std::swap(D.bag.front(), D.bag.back());
    }
    D.last_track = D.bag.back();
    D.bag.pop_back();
    return D.last_track;
}

bool boss_engaged(const rta_gamestate& s) {
    if (!(s.phase & RTA_GS_PH_LEVEL) || (s.phase & (RTA_GS_PH_LOADING | RTA_GS_PH_FRONTEND | RTA_GS_PH_DEAD))) return false;
    if (s.boss_uid != 0) return true;                       // the game's own boss meter is up
    // the souls-style mode's lock-on (its local block: +0x180 on, +0x184 the object locked on)
    uint32_t locked = 0;
    if (soulscombat::active()) {
        const uint8_t* ram = rta::memory();
        uint32_t magic = 0, on = 0;
        memcpy(&magic, ram + soulscombat::SOULS_BASE, 4);
        memcpy(&on, ram + soulscombat::SOULS_BASE + 0x180, 4);
        if (magic == soulscombat::SOULS_MAGIC && on) memcpy(&locked, ram + soulscombat::SOULS_BASE + 0x184, 4);
    }
    int n = s.creature_count < RTA_GS_CREATURES ? s.creature_count : RTA_GS_CREATURES;
    for (int k = 0; k < n; k++) {
        const rta_gs_creature& c = s.creature[k];
        if (!(c.flags & RTA_GS_CF_BOSS) || (c.flags & (RTA_GS_CF_DEAD | RTA_GS_CF_INERT))) continue;
        if (locked && c.object == locked) return true;      // locked on (souls mode)
        if ((c.flags & RTA_GS_CF_HOSTILE) && ((c.flags & (RTA_GS_CF_AGGRO | RTA_GS_CF_TARGETED)) || c.health < c.health_max)) return true;
    }
    return false;
}

void hook() {
    if (g_hooked.load() || !rta_sound_set_host_mix) return;
    rta_sound_set_host_mix(mix);
    g_hooked.store(true);
}

double eased() { return D.level * D.level * (3.0 - 2.0 * D.level); }

void apply() {
    double e = eased();
    g_target.store((float)(e * D.volume), std::memory_order_relaxed);
    double want = D.game_base * (1.0 - e);
    if (std::fabs(want - D.game_applied) > 0.004 || (want == 0 && D.game_applied != 0) || (e == 0 && D.game_applied != D.game_base)) {
        if (apprt::set_music_volume(want)) D.game_applied = want;
    }
}

void set_track(std::shared_ptr<Track> t) {
    std::shared_ptr<Track> old;
    {
        std::lock_guard<std::mutex> hold(g_mix_lock);
        old = std::move(g_mix_track);
        g_mix_track = std::move(t);
        g_mix_pos = 0;
        g_mix_gain = 0;
    }
    // `old` is freed here, on the game's thread, never on the sound thread
}

void stop_track() {
    g_target.store(0.0f);
    set_track(nullptr);
}

}  // namespace

void set_data_folder(const std::string& data) { D.data = data; }

bool setting(const char* key, const char* value) {
    std::string k = key, v = value ? value : "";
    if (k == "music.boss") D.mode = v == "auto" || v.empty() ? -1 : (v == "off" || v == "no" || v == "0" || v == "false") ? 0 : 1;
    else if (k == "music.boss_dir") { D.dir_setting = v; D.scanned_for.clear(); D.scanned = false; }
    else if (k == "music.boss_volume") D.volume = std::clamp(atof(v.c_str()), 0.0, 1.0);
    else if (k == "music.boss_engage") D.forced = v == "on" ? 1 : v == "off" ? 0 : -1;    // test aid: engaged by hand, never, or by the game (auto)
    else return false;
    return true;
}

std::string settings_text() {
    char text[512];
    snprintf(text, sizeof text,
             "music.boss = %s             # the player's own music for boss fights: auto (on in Hardcore or aiming, off in Classic) | on | off (files in music.boss_dir; none: nothing changes)\n"
             "music.boss_dir = %s         # the folder of tracks (.ogg .mp3 .wav); empty: <data>/music/boss/\n"
             "music.boss_volume = %.2f    # 0 to 1: the player's tracks\n",
             D.mode < 0 ? "auto" : D.mode ? "on" : "off", D.dir_setting.c_str(), D.volume);
    return text;
}

bool game_music_volume(double volume) {
    D.game_base = std::clamp(volume, 0.0, 1.0);
    double want = D.game_base * (1.0 - eased());
    if (!apprt::set_music_volume(want)) return false;
    D.game_applied = want;
    return true;
}

void blank(uint64_t frame) {
    double dt = D.last_frame && frame > D.last_frame ? (double)(frame - D.last_frame) / 60.0 : 1.0 / 60.0;
    if (dt > 0.25) dt = 0.25;
    D.last_frame = frame;
    // Nothing to play and nothing playing: the game's state is not even read (costs nothing).
    if (!D.scanned) scan();
    bool want_state = (enabled() && !D.tracks.empty()) || D.state != IDLE;
    if (want_state) {
        if (!D.reader) D.reader = rta_gs_create();
        D.st = rta_gs_update(D.reader, rta::memory());
    }
    const rta_gamestate* s = want_state ? D.st : nullptr;
    if (s && (s->phase & RTA_GS_PH_LEVEL)) {
        std::string here(s->level, strnlen(s->level, sizeof s->level));
        if (here != D.scanned_for) { D.scanned_for = here; scan(); }      // once per level: files put there while playing are found at the next level
    }
    bool engaged = enabled() && !D.tracks.empty() && s && (D.forced >= 0 ? D.forced == 1 : boss_engaged(*s));
    if (engaged) D.engaged_frames++;
    uint32_t tick = s ? s->sim_tick : 0;
    char line[512];
    switch (D.state) {
        case IDLE:
            if (engaged) {
                hook();
                auto job = std::make_shared<Load>();
                job->path = next_track();
                D.load = job;
                std::thread([job] { job->track = decode(job->path, job->why); job->done.store(true); }).detach();
                D.state = LOADING;
                snprintf(line, sizeof line, "boss engaged at tick %u: loading %s", tick, file_name(job->path).c_str());
                say(line);
            }
            break;
        case LOADING:
            if (D.load && D.load->done.load()) {
                auto job = D.load;
                D.load.reset();
                if (!job->track) {
                    snprintf(line, sizeof line, "cannot play %s (%s): left out", file_name(job->path).c_str(), job->why.c_str());
                    say(line);
                    D.tracks.erase(std::remove(D.tracks.begin(), D.tracks.end(), job->path), D.tracks.end());
                    D.state = IDLE;
                    break;
                }
                double seconds = (double)job->track->frames() / RATE;
                set_track(job->track);
                D.level = 0;
                D.calm_for = 0;
                D.state = PLAYING;
                D.played++;
                snprintf(line, sizeof line, "playing %s (%.1f s, looped) from tick %u", file_name(job->path).c_str(), seconds, tick);
                say(line);
            } else if (!enabled()) {
                D.load.reset();                 // the thread finishes by itself; what it made is dropped
                D.state = IDLE;
            }
            break;
        case PLAYING:
            D.level = std::min(1.0, D.level + dt / FADE_IN);
            if (!engaged && D.calm_for == 0) {
                snprintf(line, sizeof line, "no boss engaged from tick %u (dead, left behind, or every player down): %.0f s more, then back", tick, HOLD_AFTER);
                say(line);
            }
            D.calm_for = engaged ? 0.0 : D.calm_for + dt;
            if (D.calm_for > HOLD_AFTER || !enabled()) {
                D.state = LEAVING;
                snprintf(line, sizeof line, "the fight is over (tick %u): back to the game's music over %.1f s", tick, FADE_OUT);
                say(line);
            }
            break;
        case LEAVING:
            D.level = std::max(0.0, D.level - dt / FADE_OUT);
            if (engaged && enabled()) {         // it was not over
                D.state = PLAYING;
                D.calm_for = 0;
                snprintf(line, sizeof line, "a boss engaged again at tick %u: %s comes back up", tick, file_name(D.last_track).c_str());
                say(line);
            }
            else if (D.level <= 0) {
                stop_track();
                D.state = IDLE;
                snprintf(line, sizeof line, "the game's music has the stage again (tick %u)", tick);
                say(line);
            }
            break;
    }
    if (D.state != IDLE || D.game_applied >= 0) apply();
}

std::string figures() {
    char text[512];
    float peak = g_peak.exchange(0.0f);
    snprintf(text, sizeof text, "boss music: %s, %zu track(s) in %s; state %s, level %.2f, track %s, own peak since the last report %.1f dB, game music %.2f "
             "(set %.2f); %llu frames mixed, %llu blanks engaged, %llu played",
             enabled() ? (D.mode < 0 ? "auto, on" : "on") : (D.mode < 0 ? "auto, off" : "off"), D.tracks.size(), D.folder.empty() ? folder_now().c_str() : D.folder.c_str(), STATE_NAMES[D.state], D.level,
             D.last_track.empty() ? "-" : file_name(D.last_track).c_str(), peak > 0 ? 20.0 * std::log10(peak) : -200.0,
             D.game_applied < 0 ? D.game_base : D.game_applied, D.game_base, (unsigned long long)g_mixed_frames.load(),
             (unsigned long long)D.engaged_frames, (unsigned long long)D.played);
    return text;
}

std::string command(const std::string& text) {
    std::vector<std::string> w;
    for (size_t i = 0; i < text.size();) {
        while (i < text.size() && text[i] == ' ') i++;
        size_t j = text.find(' ', i);
        if (j == std::string::npos) j = text.size();
        if (j > i) w.push_back(text.substr(i, j - i));
        i = j;
    }
    if (w.empty() || w[0] == "info" || w[0] == "say") return figures();
    if (w[0] == "on" || w[0] == "off") { setting("music.boss", w[0].c_str()); return figures(); }
    if (w[0] == "volume" && w.size() >= 2) { setting("music.boss_volume", w[1].c_str()); return figures(); }
    if (w[0] == "dir") { setting("music.boss_dir", w.size() >= 2 ? text.substr(text.find(w[1])).c_str() : ""); scan(); return figures(); }
    if (w[0] == "rescan") { scan(); return figures(); }
    if (w[0] == "engage" && w.size() >= 2) {    // test aid: engaged by hand (on), never (off), or by the game's state again (auto)
        setting("music.boss_engage", w[1].c_str());
        return figures();
    }
    return "music: info | on | off | volume 0..1 | dir PATH | rescan | engage on|off|auto";
}

}  // namespace bossmusic
