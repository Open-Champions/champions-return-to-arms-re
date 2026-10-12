// sndcmp.cpp - compare two recordings of the same sound event by numbers.
//
//   clang++ -std=c++17 -O2 tools/recomp/sound/sndcmp.cpp -o local/sound/bin/sndcmp
//
//   sndcmp A.wav B.wav [--a-start S] [--a-len S] [--b-start S] [--search S] [--name TEXT]
//          [--chunks S] [--b-rate-ppm X] [--by-waveform 1] [--save-a FILE.wav] [--save-b FILE.wav]
//
// A is the probe (the native library's render), B the reference (the emulator's mix).
// Both are brought to 48 kHz (band-limited resampling).  The stretch of A from --a-start,
// --a-len seconds long, is looked for in B around --b-start, at most --search seconds
// either way: first by loudness envelope, then to the sample by the waveform.  Then:
//
//   offset      where it was found (seconds in B minus seconds in A)
//   waveform    correlation of the two waveforms at that offset (mono, left, right)
//   level       RMS of each, and the difference in dB
//   residual    B minus gain-matched A, in dB below B (how much of B is not A)
//   envelope    correlation of the 10 ms loudness envelopes, and the median difference
//   spectrum    third-octave band levels of both and their difference
//   drift       the stretch cut into chunks; each chunk's own best offset.  A slope is
//               one clock running against the other (in parts per million)
//
// --by-waveform 1 skips the envelope step and looks for A's waveform at every position of
// the searched stretch of B: for one short event among many others.
//
// --b-rate-ppm X reads B as if its sample rate were X parts per million higher than its
// header says: for a reference whose own clock is known to be off by that much (the
// emulator plays a stream voice 421 ppm slow: it rounds 48000 x 0x7fe / 44100 down to a
// whole step of 2226 / 4096).  Times in B then count in the corrected clock.
//
// Reads 16-bit PCM WAV files only.  No sound is played.
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace {

const double RATE = 48000.0;
const double PI = 3.14159265358979323846;

struct Sound {
    std::vector<float> ch[2];   // at 48 kHz
    size_t size() const { return ch[0].size(); }
};

[[noreturn]] void die(const char* format, const char* what = "") {
    fprintf(stderr, "sndcmp: ");
    fprintf(stderr, format, what);
    fprintf(stderr, "\n");
    exit(2);
}

// Band-limited resampling: a Kaiser-windowed sinc of 32 zero crossings, cut off just below
// the lower of the two Nyquist frequencies, tabulated at 2,048 positions between samples.
std::vector<float> resample(const std::vector<float>& in, double from, double to, double start, double length) {
    size_t first = (size_t)(start * to + 0.5);
    size_t all = (size_t)((double)in.size() * to / from);
    size_t count = length > 0 ? (size_t)(length * to) : all - std::min(all, first);
    if (from == to) {
        std::vector<float> out(count, 0.0f);
        for (size_t i = 0; i < count && first + i < in.size(); i++) out[i] = in[first + i];
        return out;
    }
    double ratio = from / to, cutoff = std::min(1.0, to / from) * 0.97;
    const int half = 32, phases = 2048;
    auto bessel = [](double x) { double sum = 1, term = 1; for (int k = 1; k < 30; k++) { term *= (x / 2 / k) * (x / 2 / k); sum += term; } return sum; };
    const double beta = 9.0, norm = bessel(beta);
    static std::vector<float> table;
    static double table_cutoff = 0;
    if (table.empty() || table_cutoff != cutoff) {
        table.assign((size_t)(phases + 1) * half * 2, 0.0f);
        table_cutoff = cutoff;
        for (int p = 0; p <= phases; p++)
            for (int t = 0; t < half * 2; t++) {
                double x = (double)(t - half + 1) - (double)p / phases, w = x / half;
                if (w <= -1 || w >= 1) continue;
                double sinc = x == 0 ? 1.0 : sin(PI * x * cutoff) / (PI * x * cutoff);
                table[(size_t)p * half * 2 + t] = (float)(sinc * cutoff * bessel(beta * sqrt(1 - w * w)) / norm);
            }
    }
    std::vector<float> out(count);
    for (size_t i = 0; i < count; i++) {
        double centre = (double)(first + i) * ratio;
        long base = (long)floor(centre);
        const float* k = &table[(size_t)((centre - base) * phases + 0.5) * half * 2];
        double sum = 0;
        for (int t = 0; t < half * 2; t++) {
            long at = base - half + 1 + t;
            if (at >= 0 && at < (long)in.size()) sum += in[(size_t)at] * k[t];
        }
        out[i] = (float)sum;
    }
    return out;
}

Sound load(const char* path, double start, double length, double rate_ppm = 0) {
    FILE* f = fopen(path, "rb");
    if (!f) die("cannot read %s", path);
    uint8_t h[12];
    if (fread(h, 1, 12, f) != 12 || memcmp(h, "RIFF", 4) || memcmp(h + 8, "WAVE", 4)) die("%s is not a WAV file", path);
    uint32_t rate = 0; uint16_t channels = 0, bits = 0;
    std::vector<int16_t> pcm;
    for (;;) {
        uint8_t c[8]; uint32_t n;
        if (fread(c, 1, 8, f) != 8) break;
        memcpy(&n, c + 4, 4);
        if (!memcmp(c, "fmt ", 4)) {
            uint8_t fmt[40] = {0};
            if (fread(fmt, 1, std::min<uint32_t>(n, 40), f) < 16) break;
            if (n > 40) fseek(f, n - 40, SEEK_CUR);
            memcpy(&channels, fmt + 2, 2); memcpy(&rate, fmt + 4, 4); memcpy(&bits, fmt + 14, 2);
        } else if (!memcmp(c, "data", 4)) {
            if (bits != 16 || !channels || !rate) die("%s: only 16-bit PCM is read", path);
            // a file whose writer was stopped may carry a length of 0 or -1: read to the end
            long at = ftell(f); fseek(f, 0, SEEK_END); long end = ftell(f); fseek(f, at, SEEK_SET);
            uint32_t have = (uint32_t)(end - at);
            if (n == 0 || n > have) n = have;
            size_t skip = (size_t)(std::max(0.0, start - 1.0) * rate) * channels * 2;
            size_t want = length > 0 ? (size_t)((length + 2.0) * rate) * channels * 2 : n;
            if (skip > n) skip = n;
            if (want > n - skip) want = n - skip;
            fseek(f, (long)skip, SEEK_CUR);
            pcm.resize(want / 2);
            if (fread(pcm.data(), 2, pcm.size(), f) != pcm.size()) die("%s is cut short", path);
            start -= (double)(skip / (channels * 2)) / rate;
            break;
        } else {
            fseek(f, n + (n & 1), SEEK_CUR);
        }
    }
    fclose(f);
    if (pcm.empty()) die("%s holds no sound", path);
    Sound s;
    size_t frames = pcm.size() / channels;
    for (int c = 0; c < 2; c++) {
        std::vector<float> one(frames);
        int from = c < channels ? c : 0;
        for (size_t i = 0; i < frames; i++) one[i] = pcm[i * channels + from] / 32768.0f;
        s.ch[c] = resample(one, rate * (1.0 + rate_ppm / 1e6), RATE, start, length);
    }
    return s;
}

std::vector<float> mono(const Sound& s) {
    std::vector<float> m(s.size());
    for (size_t i = 0; i < m.size(); i++) m[i] = 0.5f * (s.ch[0][i] + s.ch[1][i]);
    return m;
}

double rms(const float* p, size_t n) {
    double sum = 0;
    for (size_t i = 0; i < n; i++) sum += (double)p[i] * p[i];
    return n ? sqrt(sum / n) : 0;
}
double db(double x) { return x > 1e-9 ? 20 * log10(x) : -180.0; }

std::vector<float> envelope(const std::vector<float>& m, size_t hop) {
    std::vector<float> e(m.size() / hop);
    for (size_t i = 0; i < e.size(); i++) e[i] = (float)rms(&m[i * hop], hop);
    return e;
}

// normalised correlation of a[0..n) with b[lag..lag+n)
double correlation(const float* a, const float* b, size_t n, bool remove_mean) {
    double ma = 0, mb = 0;
    if (remove_mean) {
        for (size_t i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
        ma /= n; mb /= n;
    }
    double ab = 0, aa = 0, bb = 0;
    for (size_t i = 0; i < n; i++) {
        double x = a[i] - ma, y = b[i] - mb;
        ab += x * y; aa += x * x; bb += y * y;
    }
    return aa > 0 && bb > 0 ? ab / sqrt(aa * bb) : 0;
}

// best lag of a inside b, lags lo..hi (b index = a index + lag)
long best_lag(const std::vector<float>& a, const std::vector<float>& b, long lo, long hi, bool remove_mean, double* score, size_t use = 0) {
    size_t n = use && use < a.size() ? use : a.size();
    long best = lo; double top = -2;
    for (long lag = lo; lag <= hi; lag++) {
        if (lag < 0 || (size_t)lag + n > b.size()) continue;
        double c = correlation(a.data(), b.data() + lag, n, remove_mean);
        if (c > top) { top = c; best = lag; }
    }
    if (score) *score = top;
    return best;
}

void fft(std::vector<std::complex<double>>& x) {
    size_t n = x.size();
    for (size_t i = 1, j = 0; i < n; i++) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(x[i], x[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        std::complex<double> w(cos(2 * PI / len), -sin(2 * PI / len));
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> v(1, 0);
            for (size_t k = 0; k < len / 2; k++) {
                std::complex<double> a = x[i + k], b = x[i + k + len / 2] * v;
                x[i + k] = a + b; x[i + k + len / 2] = a - b;
                v *= w;
            }
        }
    }
}

// third-octave band powers, 50 Hz .. 16 kHz, from averaged 4096-point periodograms
std::vector<double> bands(const float* p, size_t n, std::vector<double>* centres) {
    const size_t N = 4096;
    std::vector<double> power(N / 2 + 1, 0.0);
    size_t frames = 0;
    for (size_t at = 0; at + N <= n; at += N / 2, frames++) {
        std::vector<std::complex<double>> x(N);
        for (size_t i = 0; i < N; i++) x[i] = p[at + i] * (0.5 - 0.5 * cos(2 * PI * i / N));
        fft(x);
        for (size_t k = 0; k <= N / 2; k++) power[k] += std::norm(x[k]);
    }
    std::vector<double> out;
    for (int b = -13; b <= 12; b++) {             // 1 kHz * 2^(b/3)
        double centre = 1000.0 * pow(2.0, b / 3.0), lo = centre / pow(2.0, 1 / 6.0), hi = centre * pow(2.0, 1 / 6.0), sum = 0;
        for (size_t k = 1; k <= N / 2; k++) {
            double f = k * RATE / N;
            if (f >= lo && f < hi) sum += power[k];
        }
        out.push_back(frames ? sum / frames : 0);
        if (centres) centres->push_back(centre);
    }
    return out;
}

void save(const char* path, const Sound& s, size_t from, size_t n) {
    FILE* f = fopen(path, "wb");
    if (!f) return;
    uint32_t data = (uint32_t)(n * 4), riff = data + 36, rate = (uint32_t)RATE, byte_rate = rate * 4;
    uint8_t h[44] = {'R', 'I', 'F', 'F', 0, 0, 0, 0, 'W', 'A', 'V', 'E', 'f', 'm', 't', ' ', 16, 0, 0, 0, 1, 0, 2, 0};
    memcpy(h + 4, &riff, 4); memcpy(h + 24, &rate, 4); memcpy(h + 28, &byte_rate, 4);
    h[32] = 4; h[34] = 16; memcpy(h + 36, "data", 4); memcpy(h + 40, &data, 4);
    fwrite(h, 1, 44, f);
    for (size_t i = 0; i < n; i++)
        for (int c = 0; c < 2; c++) {
            double v = s.ch[c][from + i] * 32768.0;
            int16_t x = (int16_t)(v < -32768 ? -32768 : v > 32767 ? 32767 : v);
            fwrite(&x, 2, 1, f);
        }
    fclose(f);
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> plain;
    std::map<std::string, std::string> named;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a.rfind("--", 0) == 0 && i + 1 < argc) named[a.substr(2)] = argv[++i];
        else plain.push_back(a);
    }
    if (plain.size() != 2) die("A.wav B.wav [--a-start S] [--a-len S] [--b-start S] [--search S] [--name TEXT] [--chunks S]");
    auto number = [&](const char* key, double fallback) { return named.count(key) ? atof(named[key].c_str()) : fallback; };
    double a_start = number("a-start", 0), a_len = number("a-len", 10), b_start = number("b-start", a_start), search = number("search", 5);
    double chunk_seconds = number("chunks", 5);

    Sound a = load(plain[0].c_str(), a_start, a_len);
    double b_from = std::max(0.0, b_start - search);
    Sound b = load(plain[1].c_str(), b_from, a_len + (b_start - b_from) + search, number("b-rate-ppm", 0));
    std::vector<float> am = mono(a), bm = mono(b);
    if (am.size() < 4800 || bm.size() < am.size()) die("not enough sound in one of the files for this stretch");

    long lag = 0;
    double env_score = 0, wave_score = 0;
    if (number("by-waveform", 0) != 0) {
        // A short event somewhere in a long stretch of other events: look for the waveform
        // itself at every position (quarter rate first, then to the sample).
        std::vector<float> a4(am.size() / 4), b4(bm.size() / 4);
        for (size_t i = 0; i < a4.size(); i++) a4[i] = am[i * 4] + am[i * 4 + 1] + am[i * 4 + 2] + am[i * 4 + 3];
        for (size_t i = 0; i < b4.size(); i++) b4[i] = bm[i * 4] + bm[i * 4 + 1] + bm[i * 4 + 2] + bm[i * 4 + 3];
        double aa = 0, bb = 0, top = -2;
        for (float x : a4) aa += (double)x * x;
        for (size_t i = 0; i < a4.size(); i++) bb += (double)b4[i] * b4[i];
        long coarse = 0;
        for (size_t l = 0; l + a4.size() <= b4.size(); l++) {
            if (bb > aa * 1e-4) {
                double ab = 0;
                for (size_t i = 0; i < a4.size(); i++) ab += (double)a4[i] * b4[l + i];
                double c = ab / sqrt(aa * bb);
                if (c > top) { top = c; coarse = (long)l; }
            }
            if (l + a4.size() < b4.size()) bb += (double)b4[l + a4.size()] * b4[l + a4.size()] - (double)b4[l] * b4[l];
        }
        lag = best_lag(am, bm, std::max(0L, coarse * 4 - 8), std::min((long)bm.size() - (long)am.size(), coarse * 4 + 8), false, &wave_score);
    } else {
    // 1. by envelope, 8 ms then 1 ms; 2. by waveform, to the sample
    double score = 0;
    std::vector<float> ea = envelope(am, 384), eb = envelope(bm, 384);
    long coarse = best_lag(ea, eb, 0, (long)eb.size() - (long)ea.size(), true, &score);
    ea = envelope(am, 48); eb = envelope(bm, 48);
    long lo = std::max(0L, coarse * 8 - 16), hi = std::min((long)eb.size() - (long)ea.size(), coarse * 8 + 16);
    long fine = best_lag(ea, eb, lo, hi, true, &env_score);
    size_t use = std::min(am.size(), (size_t)(RATE * 2));
    // the loudest two seconds of A carry the fine search
    size_t use_at = 0;
    {
        std::vector<float> e = envelope(am, 4800);
        double top = -1;
        for (size_t i = 0; i + 20 <= e.size(); i++) {
            double sum = 0;
            for (size_t k = 0; k < 20; k++) sum += e[i + k];
            if (sum > top) { top = sum; use_at = i * 4800; }
        }
    }
    std::vector<float> probe(am.begin() + (long)use_at, am.begin() + (long)(use_at + use));
    long centre = fine * 48 + (long)use_at;
    lag = best_lag(probe, bm, std::max(0L, centre - 480), std::min((long)bm.size() - (long)use, centre + 480), false, &wave_score) - (long)use_at;
    }
    if (lag < 0) lag = 0;
    if ((size_t)lag + am.size() > bm.size()) lag = (long)(bm.size() - am.size());
    size_t n = am.size();
    double offset = b_from + lag / RATE - a_start;

    printf("== %s\n", named.count("name") ? named["name"].c_str() : "comparison");
    printf("stretch     A %.3f s + %.3f s; found in B at %.4f s (offset B - A %+.4f s)\n", a_start, n / RATE, b_from + lag / RATE, offset);
    double wm = correlation(am.data(), bm.data() + lag, n, false);
    double wl = correlation(a.ch[0].data(), b.ch[0].data() + lag, n, false), wr = correlation(a.ch[1].data(), b.ch[1].data() + lag, n, false);
    printf("waveform    correlation mono %.4f, left %.4f, right %.4f\n", wm, wl, wr);
    double la = rms(a.ch[0].data(), n), ra = rms(a.ch[1].data(), n), lb = rms(b.ch[0].data() + lag, n), rb = rms(b.ch[1].data() + lag, n);
    printf("level       A left %.2f right %.2f dBFS; B left %.2f right %.2f dBFS; B - A left %+.2f right %+.2f dB\n", db(la), db(ra), db(lb), db(rb), db(lb) - db(la), db(rb) - db(ra));
    {
        double ab = 0, aa = 0, bb = 0;
        for (size_t i = 0; i < n; i++) { ab += (double)am[i] * bm[lag + i]; aa += (double)am[i] * am[i]; bb += (double)bm[lag + i] * bm[lag + i]; }
        double gain = aa > 0 ? ab / aa : 0, rest = 0;
        for (size_t i = 0; i < n; i++) { double d = bm[lag + i] - gain * am[i]; rest += d * d; }
        printf("residual    B - %.4f x A is %.1f dB below B\n", gain, bb > 0 && rest > 0 ? 10 * log10(bb / rest) : 99.0);
    }
    {
        std::vector<float> xa = envelope(am, 480), xb = envelope(std::vector<float>(bm.begin() + lag, bm.begin() + lag + (long)n), 480);
        std::vector<double> diff;
        for (size_t i = 0; i < xa.size(); i++)
            if (xa[i] > 0.003 && xb[i] > 0.003) diff.push_back(fabs(db(xb[i]) - db(xa[i])));
        std::sort(diff.begin(), diff.end());
        printf("envelope    10 ms loudness: correlation %.4f; difference median %.2f dB, 90th percentile %.2f dB (%zu windows above -50 dBFS)\n",
               correlation(xa.data(), xb.data(), xa.size(), true), diff.empty() ? 0.0 : diff[diff.size() / 2], diff.empty() ? 0.0 : diff[diff.size() * 9 / 10], diff.size());
    }
    {
        std::vector<double> centres, pa = bands(am.data(), n, &centres), pb = bands(bm.data() + lag, n, nullptr);
        double total = 0, weighted = 0; int counted = 0;
        printf("spectrum    band Hz: A dB / B dB / B - A\n");
        for (size_t i = 0; i < centres.size(); i++) {
            double x = 10 * log10(pa[i] + 1e-12), y = 10 * log10(pb[i] + 1e-12);
            printf("            %7.0f  %6.1f  %6.1f  %+5.1f\n", centres[i], x, y, y - x);
            if (centres[i] <= 8000 && pa[i] > 1e-6) { total += fabs(y - x); counted++; }
            (void)weighted;
        }
        printf("spectrum    mean |B - A| over the bands up to 8 kHz that carry sound: %.2f dB\n", counted ? total / counted : 0.0);
    }
    {
        size_t chunk = (size_t)(chunk_seconds * RATE);
        if (chunk >= 4800 && n >= chunk * 2) {
            printf("drift       chunk start s: best offset of the chunk against the whole-stretch offset, ms (correlation)\n");
            std::vector<double> xs, ys;
            for (size_t at = 0; at + chunk <= n; at += chunk) {
                std::vector<float> piece(am.begin() + (long)at, am.begin() + (long)(at + chunk));
                if (rms(piece.data(), piece.size()) < 0.002) continue;
                double c = 0;
                long from = lag + (long)at;
                long l = best_lag(piece, bm, std::max(0L, from - 960), std::min((long)bm.size() - (long)chunk, from + 960), false, &c, std::min(chunk, (size_t)48000));
                printf("            %7.2f  %+7.3f  (%.3f)\n", at / RATE, (l - from) * 1000.0 / RATE, c);
                if (c > 0.5) { xs.push_back(at / RATE); ys.push_back((l - from) / RATE); }
            }
            if (xs.size() >= 2) {
                double mx = 0, my = 0, sxy = 0, sxx = 0;
                for (size_t i = 0; i < xs.size(); i++) { mx += xs[i]; my += ys[i]; }
                mx /= xs.size(); my /= xs.size();
                for (size_t i = 0; i < xs.size(); i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) * (xs[i] - mx); }
                printf("drift       slope %+.1f parts per million over %.1f s (%+.3f ms from first to last chunk)\n",
                       sxx > 0 ? sxy / sxx * 1e6 : 0.0, xs.back() - xs.front(), (ys.back() - ys.front()) * 1000);
            }
        }
    }
    if (named.count("save-a")) save(named["save-a"].c_str(), a, 0, n);
    if (named.count("save-b")) save(named["save-b"].c_str(), b, (size_t)lag, n);
    return 0;
}
