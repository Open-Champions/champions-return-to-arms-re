// audiocheck.cpp - is a recording damaged?  Numbers for what the ear calls static, crackle, gaps.
//
//   clang++ -std=c++17 -O2 tools/recomp/sound/audiocheck.cpp -o local/sound/bin/audiocheck
//
//   audiocheck FILE.wav [--start S] [--len S] [--ref REF.wav [--ref-start S] [--ref-len S]] [--name TEXT] [--json]
//
// Reads 16-bit, 24-bit or 32-bit PCM and 32-bit float WAV at any rate.  Over the stretch asked for
// (default: all of it):
//
//   level        peak and RMS (dBFS), of the louder channel
//   clipped      samples at full scale (|x| >= 32767/32768), and runs of three or more in a row
//   zero gaps    runs of exact digital zero (both channels) of 1 to 250 ms with sound on both sides (more than
//                -50 dBFS within 20 ms before and after): a buffer that was not filled.  Longer silences are the
//                game's own (between two sounds, a level loading)
//   jumps        one-sample steps of more than a quarter of full scale: a splice or a wrong sample
//   clicks       second differences far outside their surroundings: more than 12 x the median of the
//                surrounding 1,536 samples and more than 3 % of full scale; merged within 2 ms
//   dropouts     10 ms frames below -60 dBFS with more than -35 dBFS 30 ms before and after
//   spectrum     over 2,048-point frames with sound (RMS above -50 dBFS): spectral flatness in
//                200 Hz .. 15 kHz (0 a pure tone, 1 white noise; music 0.01 .. 0.2, noise 0.5 .. 1),
//                median; the share of power above 10 kHz, median, dB; the noise floor: the 10th
//                percentile of the bins in 1 .. 15 kHz of a frame (dBFS per bin), median over frames
//   per minute   clicks, jumps, zero gaps and dropouts are also given per minute
//
// With --ref (the same moment from the reference): the long-term spectra of both (16,384 points)
// are compared after scaling the frequency axis of this one by r = 0.94 .. 1.06; the r that
// matches best is the speed / pitch of this recording against the reference (cents); and the
// level difference.  No sound is played.
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

const double PI = 3.14159265358979323846;

struct Sound {
    double rate = 0;
    std::vector<float> ch[2];   // -1 .. 1 (int16 full scale = 32768)
    size_t size() const { return ch[0].size(); }
};

[[noreturn]] void die(const std::string& text) {
    fprintf(stderr, "audiocheck: %s\n", text.c_str());
    exit(2);
}

uint32_t u32(const uint8_t* p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
uint16_t u16(const uint8_t* p) { return (uint16_t)(p[0] | p[1] << 8); }

Sound read_wav(const std::string& path, double start, double len) {
    FILE* f = fopen(path.c_str(), "rb");
    if (!f) die("cannot open " + path);
    uint8_t h[12];
    if (fread(h, 1, 12, f) != 12 || memcmp(h, "RIFF", 4) || memcmp(h + 8, "WAVE", 4)) die(path + ": not a WAV file");
    unsigned format = 0, channels = 0, bits = 0, rate = 0;
    long data_at = -1;
    uint64_t data_size = 0;
    for (;;) {
        uint8_t c[8];
        if (fread(c, 1, 8, f) != 8) break;
        uint32_t size = u32(c + 4);
        if (!memcmp(c, "fmt ", 4)) {
            std::vector<uint8_t> b(size);
            if (fread(b.data(), 1, size, f) != size) die(path + ": short fmt");
            format = u16(&b[0]); channels = u16(&b[2]); rate = u32(&b[4]); bits = u16(&b[14]);
            if (format == 0xFFFE && size >= 26) format = u16(&b[24]);
            if (size & 1) fseek(f, 1, SEEK_CUR);
        } else if (!memcmp(c, "data", 4)) {
            data_at = ftell(f);
            data_size = size;
            // a file whose header was not brought up to date (a run that was killed): to the end
            fseek(f, 0, SEEK_END);
            uint64_t rest = (uint64_t)(ftell(f) - data_at);
            if (data_size == 0 || data_size > rest) data_size = rest;
            break;
        } else fseek(f, size + (size & 1), SEEK_CUR);
    }
    if (data_at < 0 || !channels || !rate) die(path + ": no data");
    if (!((format == 1 && (bits == 16 || bits == 24 || bits == 32)) || (format == 3 && bits == 32))) die(path + ": unsupported sample format");
    unsigned bytes = bits / 8, frame = bytes * channels;
    uint64_t frames = data_size / frame;
    uint64_t first = (uint64_t)std::max(0.0, start * rate);
    uint64_t count = len > 0 ? (uint64_t)(len * rate) : frames;
    if (first > frames) first = frames;
    if (count > frames - first) count = frames - first;
    Sound s;
    s.rate = rate;
    s.ch[0].resize(count); s.ch[1].resize(count);
    fseek(f, data_at + (long)(first * frame), SEEK_SET);
    std::vector<uint8_t> buf(frame * 65536);
    uint64_t done = 0;
    while (done < count) {
        size_t want = (size_t)std::min<uint64_t>(65536, count - done);
        size_t got = fread(buf.data(), frame, want, f);
        if (!got) break;
        for (size_t i = 0; i < got; i++) {
            for (unsigned c = 0; c < 2; c++) {
                const uint8_t* p = &buf[i * frame + (c < channels ? c : 0) * bytes];
                float v;
                if (format == 3) { uint32_t w = u32(p); memcpy(&v, &w, 4); }
                else if (bits == 16) v = (int16_t)u16(p) / 32768.0f;
                else if (bits == 24) v = (float)((int32_t)((uint32_t)p[0] << 8 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 24) >> 8) / 8388608.0f;
                else v = (int32_t)u32(p) / 2147483648.0f;
                s.ch[c][done + i] = v;
            }
        }
        done += got;
    }
    fclose(f);
    s.ch[0].resize(done); s.ch[1].resize(done);
    return s;
}

void fft(std::vector<std::complex<double>>& a) {
    size_t n = a.size();
    for (size_t i = 1, j = 0; i < n; i++) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        double ang = -2 * PI / (double)len;
        std::complex<double> wl(cos(ang), sin(ang));
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> w(1);
            for (size_t j = 0; j < len / 2; j++) {
                auto u = a[i + j], v = a[i + j + len / 2] * w;
                a[i + j] = u + v; a[i + j + len / 2] = u - v;
                w *= wl;
            }
        }
    }
}

double db(double x) { return x > 1e-20 ? 10 * log10(x) : -200; }
double median(std::vector<double> v) {
    if (v.empty()) return 0;
    std::nth_element(v.begin(), v.begin() + v.size() / 2, v.end());
    return v[v.size() / 2];
}

// The long-term power spectrum, n points, mono, over frames with sound; bins at rate / n.
std::vector<double> ltas(const Sound& s, size_t n) {
    std::vector<double> sum(n / 2 + 1, 0.0);
    std::vector<std::complex<double>> a(n);
    size_t frames = 0;
    for (size_t at = 0; at + n <= s.size(); at += n / 2) {
        double e = 0;
        for (size_t i = 0; i < n; i++) { double m = 0.5 * (s.ch[0][at + i] + s.ch[1][at + i]); e += m * m; }
        if (db(e / n) < -50) continue;
        for (size_t i = 0; i < n; i++) {
            double w = 0.5 - 0.5 * cos(2 * PI * i / n);
            a[i] = 0.5 * (s.ch[0][at + i] + s.ch[1][at + i]) * w;
        }
        fft(a);
        for (size_t k = 0; k <= n / 2; k++) sum[k] += std::norm(a[k]);
        frames++;
    }
    if (frames) for (auto& v : sum) v /= frames;
    return sum;
}

double at_hz(const std::vector<double>& spec, double rate, size_t n, double hz) {
    double x = hz * n / rate;
    size_t k = (size_t)x;
    if (k + 1 >= spec.size()) return spec.back();
    double t = x - k;
    return spec[k] * (1 - t) + spec[k + 1] * t;
}

struct Figures {
    double seconds = 0, peak_db = -200, rms_db = -200;
    uint64_t clipped = 0, clip_runs = 0, zero_gaps = 0, jumps = 0, clicks = 0, dropouts = 0;
    double zero_gap_ms = 0, longest_gap_ms = 0;
    double flatness = 0, hf_db = -200, floor_db = -200;
    size_t sound_frames = 0;
};

Figures check(const Sound& s) {
    Figures F;
    size_t n = s.size();
    double rate = s.rate;
    F.seconds = n / rate;
    // level, clipping
    double sq[2] = {0, 0}, peak = 0;
    for (int c = 0; c < 2; c++) {
        size_t run = 0;
        for (size_t i = 0; i < n; i++) {
            double v = s.ch[c][i];
            sq[c] += v * v;
            peak = std::max(peak, fabs(v));
            if (fabs(v) >= 32767.0 / 32768.0) { F.clipped++; if (++run == 3) F.clip_runs++; }
            else run = 0;
        }
    }
    F.peak_db = peak > 0 ? 20 * log10(peak) : -200;
    F.rms_db = n ? db(std::max(sq[0], sq[1]) / n) : -200;
    // 1 ms RMS, for "sound on both sides"
    size_t ms = (size_t)(rate / 1000);
    std::vector<double> ms_rms(n / ms + 1, 0.0);
    for (size_t i = 0; i < n; i++) {
        double v = std::max(fabs(s.ch[0][i]), fabs(s.ch[1][i]));
        ms_rms[i / ms] += v * v;
    }
    for (auto& v : ms_rms) v = db(v / ms);
    auto loud_near = [&](long from_ms, long to_ms) {     // RMS over [from, to) ms above -50 dBFS
        double e = 0; long k = 0;
        for (long m = std::max(0L, from_ms); m < to_ms && m < (long)ms_rms.size(); m++, k++) e += pow(10, ms_rms[m] / 10);
        return k > 0 && db(e / k) > -50;
    };
    // zero gaps
    size_t min_gap = ms;
    for (size_t i = 0; i < n;) {
        if (s.ch[0][i] != 0 || s.ch[1][i] != 0) { i++; continue; }
        size_t j = i;
        while (j < n && s.ch[0][j] == 0 && s.ch[1][j] == 0) j++;
        if (j - i >= min_gap && j - i <= 250 * ms && i > 0 && j < n) {
            long a = (long)(i / ms), b = (long)(j / ms);
            if (loud_near(a - 20, a) && loud_near(b + 1, b + 21)) {
                F.zero_gaps++;
                double g = (j - i) * 1000.0 / rate;
                F.zero_gap_ms += g;
                F.longest_gap_ms = std::max(F.longest_gap_ms, g);
            }
        }
        i = j;
    }
    // jumps and clicks (per channel; events merged within 2 ms across channels)
    std::vector<size_t> events;
    for (int c = 0; c < 2; c++) {
        const auto& x = s.ch[c];
        if (n < 3) break;
        std::vector<float> d2(n, 0.0f);
        for (size_t i = 2; i < n; i++) d2[i] = fabsf(x[i] - 2 * x[i - 1] + x[i - 2]);
        const size_t B = 512;
        size_t blocks = n / B + 1;
        std::vector<double> med(blocks, 0.0);
        std::vector<float> tmp;
        for (size_t b = 0; b < blocks; b++) {
            size_t a = b * B, e = std::min(n, a + B);
            tmp.assign(d2.begin() + a, d2.begin() + e);
            if (tmp.empty()) continue;
            std::nth_element(tmp.begin(), tmp.begin() + tmp.size() / 2, tmp.end());
            med[b] = tmp[tmp.size() / 2];
        }
        for (size_t i = 2; i < n; i++) {
            if (fabsf(x[i] - x[i - 1]) > 0.25f) { F.jumps++; events.push_back(i); continue; }
            size_t b = i / B;
            double m = std::max({med[b], b ? med[b - 1] : 0.0, b + 1 < blocks ? med[b + 1] : 0.0});
            if (d2[i] > 0.03 && d2[i] > 12 * m) events.push_back(i);
        }
    }
    std::sort(events.begin(), events.end());
    size_t last = (size_t)-1;
    for (size_t e : events) {
        if (last == (size_t)-1 || e - last > 2 * ms) F.clicks++;
        last = e;
    }
    // dropouts: 10 ms frames
    size_t fr = 10 * ms;
    std::vector<double> f10;
    for (size_t at = 0; at + fr <= n; at += fr) {
        double e = 0;
        for (size_t i = at; i < at + fr; i++) e += std::max(s.ch[0][i] * s.ch[0][i], s.ch[1][i] * s.ch[1][i]);
        f10.push_back(db(e / fr));
    }
    for (size_t k = 3; k + 3 < f10.size(); k++)
        if (f10[k] < -60 && f10[k - 3] > -35 && f10[k + 3] > -35 && !(f10[k - 1] < -60 && k > 3)) F.dropouts++;
    // spectrum
    const size_t N = 2048;
    std::vector<std::complex<double>> a(N);
    std::vector<double> flat, hf, floor_;
    double bin = rate / N;
    for (size_t at = 0; at + N <= n; at += N / 2) {
        double e = 0;
        for (size_t i = 0; i < N; i++) { double m = 0.5 * (s.ch[0][at + i] + s.ch[1][at + i]); e += m * m; }
        if (db(e / N) < -50) continue;
        for (size_t i = 0; i < N; i++) a[i] = 0.5 * (s.ch[0][at + i] + s.ch[1][at + i]) * (0.5 - 0.5 * cos(2 * PI * i / N));
        fft(a);
        double lg = 0, ar = 0, all = 0, high = 0; size_t k_n = 0;
        std::vector<double> band;
        for (size_t k = 1; k < N / 2; k++) {
            double p = std::norm(a[k]) + 1e-20, hz = k * bin;
            all += p;
            if (hz >= 10000) high += p;
            if (hz >= 200 && hz <= 15000) { lg += log(p); ar += p; k_n++; }
            if (hz >= 1000 && hz <= 15000) band.push_back(p);
        }
        if (k_n) flat.push_back(exp(lg / k_n) / (ar / k_n));
        hf.push_back(db(high / all));
        if (!band.empty()) {
            std::nth_element(band.begin(), band.begin() + band.size() / 10, band.end());
            // per bin, relative to full scale: a full-scale sine with this window gives (N/4)^2
            floor_.push_back(db(band[band.size() / 10] / ((N / 4.0) * (N / 4.0))));
        }
    }
    F.sound_frames = flat.size();
    F.flatness = median(flat);
    F.hf_db = hf.empty() ? -200 : median(hf);
    F.floor_db = floor_.empty() ? -200 : median(floor_);
    return F;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) die("usage: audiocheck FILE.wav [--start S] [--len S] [--ref REF.wav [--ref-start S] [--ref-len S]] [--name TEXT] [--json]");
    std::string path = argv[1], ref, name;
    double start = 0, len = 0, ref_start = 0, ref_len = 0;
    bool json = false;
    for (int k = 2; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { if (k + 1 >= argc) die("missing value for " + a); return argv[++k]; };
        if (a == "--start") start = atof(next().c_str());
        else if (a == "--len") len = atof(next().c_str());
        else if (a == "--ref") ref = next();
        else if (a == "--ref-start") ref_start = atof(next().c_str());
        else if (a == "--ref-len") ref_len = atof(next().c_str());
        else if (a == "--name") name = next();
        else if (a == "--json") json = true;
        else die("unknown option " + a);
    }
    Sound s = read_wav(path, start, len);
    Figures F = check(s);
    double per_min = F.seconds > 0 ? 60.0 / F.seconds : 0;
    double cents = 0, level_diff = 0, best_corr = 0;
    bool have_ref = !ref.empty();
    if (have_ref) {
        Sound r = read_wav(ref, ref_start, ref_len);
        const size_t N = 16384;
        auto a = ltas(s, N), b = ltas(r, N);
        double best = -2, best_r = 1;
        for (double ratio = 0.94; ratio <= 1.06 + 1e-9; ratio += 0.0001) {
            // this recording at f * ratio against the reference at f, log power, 80 .. 4000 Hz
            std::vector<double> x, y;
            for (double hz = 80; hz <= 4000; hz *= 1.002) {
                x.push_back(db(at_hz(a, s.rate, N, hz * ratio)));
                y.push_back(db(at_hz(b, r.rate, N, hz)));
            }
            double mx = 0, my = 0;
            for (size_t i = 0; i < x.size(); i++) { mx += x[i]; my += y[i]; }
            mx /= x.size(); my /= y.size();
            double sxy = 0, sxx = 0, syy = 0;
            for (size_t i = 0; i < x.size(); i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) * (x[i] - mx); syy += (y[i] - my) * (y[i] - my); }
            double c = sxy / sqrt(sxx * syy + 1e-30);
            if (c > best) { best = c; best_r = ratio; }
        }
        cents = 1200 * log2(best_r);
        best_corr = best;
        Figures R = check(r);
        level_diff = F.rms_db - R.rms_db;
    }
    if (json) {
        printf("{\"name\":\"%s\",\"file\":\"%s\",\"rate\":%.0f,\"seconds\":%.2f,\"peak_db\":%.2f,\"rms_db\":%.2f,\"clipped\":%llu,\"clip_runs\":%llu,"
               "\"zero_gaps\":%llu,\"zero_gap_ms\":%.1f,\"longest_gap_ms\":%.1f,\"jumps\":%llu,\"clicks\":%llu,\"dropouts\":%llu,"
               "\"clicks_per_min\":%.2f,\"gaps_per_min\":%.2f,\"jumps_per_min\":%.2f,\"dropouts_per_min\":%.2f,"
               "\"flatness\":%.4f,\"hf_db\":%.2f,\"floor_db\":%.2f,\"sound_frames\":%zu",
               name.c_str(), path.c_str(), s.rate, F.seconds, F.peak_db, F.rms_db, (unsigned long long)F.clipped, (unsigned long long)F.clip_runs,
               (unsigned long long)F.zero_gaps, F.zero_gap_ms, F.longest_gap_ms, (unsigned long long)F.jumps, (unsigned long long)F.clicks,
               (unsigned long long)F.dropouts, F.clicks * per_min, F.zero_gaps * per_min, F.jumps * per_min, F.dropouts * per_min,
               F.flatness, F.hf_db, F.floor_db, F.sound_frames);
        if (have_ref) printf(",\"pitch_cents\":%.1f,\"spectrum_match\":%.4f,\"level_vs_ref_db\":%.2f", cents, best_corr, level_diff);
        printf("}\n");
        return 0;
    }
    printf("%s%s%.0f Hz, %.2f s; peak %.2f dBFS, RMS %.2f dBFS\n", name.c_str(), name.empty() ? "" : ": ", s.rate, F.seconds, F.peak_db, F.rms_db);
    printf("  clipped %llu samples (%llu runs of 3+); zero gaps %llu (%.1f ms, longest %.1f ms; %.2f a minute)\n",
           (unsigned long long)F.clipped, (unsigned long long)F.clip_runs, (unsigned long long)F.zero_gaps, F.zero_gap_ms, F.longest_gap_ms, F.zero_gaps * per_min);
    printf("  jumps %llu (%.2f a minute); clicks %llu (%.2f a minute); dropouts %llu (%.2f a minute)\n",
           (unsigned long long)F.jumps, F.jumps * per_min, (unsigned long long)F.clicks, F.clicks * per_min, (unsigned long long)F.dropouts, F.dropouts * per_min);
    printf("  spectrum over %zu frames with sound: flatness %.4f, power above 10 kHz %.1f dB, floor %.1f dBFS per bin\n",
           F.sound_frames, F.flatness, F.hf_db, F.floor_db);
    if (have_ref) printf("  against %s: pitch %+.1f cents (spectra match %.4f), level %+.2f dB\n", ref.c_str(), cents, best_corr, level_diff);
    return 0;
}
