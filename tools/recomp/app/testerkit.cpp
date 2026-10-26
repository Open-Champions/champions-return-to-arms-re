// testerkit.cpp - the bug report, the crash report and the build line (testerkit.h).
#include "testerkit.h"
#include "backend.h"
#include "iface.h"
#include "moved.h"
#include "../net2/hooks.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <mutex>
#include <thread>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <csignal>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>
#if defined(__APPLE__) || defined(__GLIBC__)
#include <execinfo.h>
#define TK_BACKTRACE 1
#endif
#endif
#ifdef __APPLE__
#include <sys/sysctl.h>
#endif

#ifndef RTA_BUILD_ID
#define RTA_BUILD_ID "unknown"
#endif

// the fix set the translation was made with (rt/runtime.cpp: weak, none in a translation without one)
unsigned recomp_patches(const uint32_t (**words)[2]);
unsigned recomp_patch_set_words();

namespace fs = std::filesystem;

namespace testerkit {
namespace {

// ---- the rings -----------------------------------------------------------------------------------
enum { RING = 3600, PLAYERS = 4 };                     // 60 s of vertical blanks
// addresses of the game's state (names.tsv; the rig's tick-log columns, tools/rig/rig.py tick_watches)
const uint32_t A_NET_FRAME = 0x4027ac, A_RAND_SEED = 0x404464, A_LEVEL_NAME = 0x41b721, A_NUM_PLAYERS = 0x4d8ae0,
               A_PLAYERS = 0x4d8af0, PLAYER_SIZE = 0x4c30, RAM = RAM_SIZE;
struct Tick {
    uint64_t number;
    int32_t net_frame, players;
    uint32_t seed;
    char level[12];
    struct P { uint32_t x, y, z, hp; int32_t state, gold, exp; } p[PLAYERS];
};
struct Input { uint64_t number; uint16_t buttons; uint8_t lx, ly, rx, ry, blanked; };
Tick g_ticks[RING];
Input g_inputs[RING];
std::atomic<uint64_t> g_tick_count{0}, g_input_count{0};
std::mutex g_ring_lock;                                 // the game's thread writes a row, a report copies them

Setup g_setup;
std::string g_reports;                                  // <data>/reports
bool g_started = false;

// what the crash handler writes besides the rings: made before, on the game's thread, every few seconds
char g_about[8192];
char g_reports_c[1024];
std::atomic<uint64_t> g_last_number{0};

// the box, the line, the notes
std::mutex g_ui_lock;
bool g_box = false;
std::string g_box_text, g_box_folder;
std::atomic<bool> g_box_flag{false};
std::atomic<bool> g_line{true};
std::string g_note;
std::chrono::steady_clock::time_point g_note_until;
int g_chord_blanks = 0;
bool g_chord_done = false;
uint16_t g_box_buttons = 0;                             // the controller's buttons when the box opened (held ones do not count as a press)

uint32_t rd32(const uint8_t* ram, uint32_t a) { uint32_t v = 0; a = party8_at(a) & (RAM - 1); if (a <= RAM - 4) memcpy(&v, ram + a, 4); return v; }

std::string stamp(const char* format) {
    time_t t = time(nullptr);
    tm local{};
#ifdef _WIN32
    localtime_s(&local, &t);
#else
    localtime_r(&t, &local);
#endif
    char text[64];
    strftime(text, sizeof text, format, &local);
    return text;
}

// a file by its UTF-8 path (on Windows the C library's own fopen takes the old code page)
FILE* open_file(const std::string& path, const char* mode) {
#ifdef _WIN32
    wchar_t wpath[2048], wmode[8];
    if (!MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, wpath, 2048)) return nullptr;
    for (int k = 0; k < 7; k++) { wmode[k] = (wchar_t)mode[k]; if (!mode[k]) break; }
    wmode[7] = 0;
    return _wfopen(wpath, wmode);
#else
    return fopen(path.c_str(), mode);
#endif
}

void say(const std::string& line) { if (g_setup.log) g_setup.log("report: " + line); else { fprintf(stderr, "report: %s\n", line.c_str()); fflush(stderr); } }

void note(const std::string& text, double seconds) {
    std::lock_guard<std::mutex> hold(g_ui_lock);
    g_note = text;
    g_note_until = std::chrono::steady_clock::now() + std::chrono::milliseconds((int)(seconds * 1000));
}

std::string room_text() {
    if (!net2hook::room_describe) return "";
    char text[2048];
    text[0] = 0;
    net2hook::room_describe(text, sizeof text);
    return text;
}

std::string about(const char* kind) {
    std::string s;
    s += "kind = "; s += kind; s += "\n";
    s += "program = " + g_setup.program + "\n";
    s += "build = " + build_id() + "\n";
    s += "fix_set = " + fix_set() + "\n";
    s += "platform = " + platform() + "\n";
    s += "vertical_blank = " + std::to_string(g_last_number.load()) + "\n";
    if (g_setup.describe) s += g_setup.describe();
    std::string room = room_text();
    s += room.empty() ? "online = no room of our own\n" : room;
    return s;
}

void refresh_about() {
    std::string s = about("crash");
    size_t n = std::min(s.size(), sizeof g_about - 1);
    memcpy(g_about, s.data(), n);
    g_about[n] = 0;
}

// rows as text (the crash handler uses the same; no allocation in it)
int tick_head(char* out, size_t size) {
    int n = snprintf(out, size, "blank\tnet\tseed\tlevel\tnplayers");
    for (int k = 0; k < PLAYERS; k++)
        n += snprintf(out + n, size - n, "\tp%dx\tp%dy\tp%dz\tp%dstate\tp%dhp\tp%dgold\tp%dexp", k, k, k, k, k, k, k);
    n += snprintf(out + n, size - n, "\n");
    return n;
}
int tick_row(const Tick& t, char* out, size_t size) {
    char level[13];
    memcpy(level, t.level, 12); level[12] = 0;
    for (char& c : level) if (c && (c < 32 || c > 126)) c = '?';
    int n = snprintf(out, size, "%llu\t%d\t%08x\t%s\t%d", (unsigned long long)t.number, t.net_frame, t.seed, level, t.players);
    for (int k = 0; k < PLAYERS; k++) {
        const Tick::P& p = t.p[k];
        n += snprintf(out + n, size - n, "\t%08x\t%08x\t%08x\t%d\t%08x\t%d\t%d", p.x, p.y, p.z, p.state, p.hp, p.gold, p.exp);
    }
    n += snprintf(out + n, size - n, "\n");
    return n;
}
const char* INPUT_HEAD = "blank\tbuttons\tlx\tly\trx\try\tblanked\n";
int input_row(const Input& r, char* out, size_t size) {
    return snprintf(out, size, "%llu\t%04x\t%u\t%u\t%u\t%u\t%u\n", (unsigned long long)r.number, r.buttons, r.lx, r.ly, r.rx, r.ry, r.blanked);
}

bool write_file(const std::string& path, const std::string& data) {
    FILE* f = open_file(path, "wb");
    if (!f) return false;
    bool ok = fwrite(data.data(), 1, data.size(), f) == data.size();
    return fclose(f) == 0 && ok;
}

// ---- a zip of stored files (no compression: PNG is compressed, the rest is small) ---------------------
uint32_t crc32(const uint8_t* p, size_t n, uint32_t crc = 0) {
    static uint32_t table[256];
    static bool made = false;
    if (!made) {
        for (uint32_t i = 0; i < 256; i++) { uint32_t c = i; for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1; table[i] = c; }
        made = true;
    }
    crc = ~crc;
    for (size_t i = 0; i < n; i++) crc = table[(crc ^ p[i]) & 0xFF] ^ (crc >> 8);
    return ~crc;
}
void put16(std::string& s, uint32_t v) { s += (char)(v & 0xFF); s += (char)((v >> 8) & 0xFF); }
void put32(std::string& s, uint32_t v) { put16(s, v & 0xFFFF); put16(s, v >> 16); }

bool write_zip(const std::string& zip_path, const std::string& folder) {
    std::vector<std::string> names;
    std::error_code ec;
    for (const auto& e : fs::directory_iterator(fs::u8path(folder), ec))
        if (e.is_regular_file(ec)) names.push_back(e.path().filename().u8string());
    std::sort(names.begin(), names.end());
    std::string top = fs::u8path(folder).filename().u8string();
    time_t now = time(nullptr);
    tm t{};
#ifdef _WIN32
    localtime_s(&t, &now);
#else
    localtime_r(&now, &t);
#endif
    uint32_t dos_time = (uint32_t)(t.tm_hour << 11 | t.tm_min << 5 | t.tm_sec / 2), dos_date = (uint32_t)((t.tm_year - 80) << 9 | (t.tm_mon + 1) << 5 | t.tm_mday);
    std::string out, central;
    for (const std::string& name : names) {
        FILE* f = open_file(folder + "/" + name, "rb");
        if (!f) continue;
        std::string data;
        char buffer[65536];
        size_t got;
        while ((got = fread(buffer, 1, sizeof buffer, f)) > 0) data.append(buffer, got);
        fclose(f);
        std::string path = top + "/" + name;
        uint32_t crc = crc32((const uint8_t*)data.data(), data.size()), offset = (uint32_t)out.size();
        put32(out, 0x04034b50); put16(out, 20); put16(out, 0x0800); put16(out, 0); put16(out, dos_time); put16(out, dos_date);
        put32(out, crc); put32(out, (uint32_t)data.size()); put32(out, (uint32_t)data.size()); put16(out, (uint32_t)path.size()); put16(out, 0);
        out += path; out += data;
        put32(central, 0x02014b50); put16(central, 20); put16(central, 20); put16(central, 0x0800); put16(central, 0); put16(central, dos_time);
        put16(central, dos_date); put32(central, crc); put32(central, (uint32_t)data.size()); put32(central, (uint32_t)data.size());
        put16(central, (uint32_t)path.size()); put16(central, 0); put16(central, 0); put16(central, 0); put16(central, 0); put32(central, 0);
        put32(central, offset); central += path;
    }
    uint32_t at = (uint32_t)out.size();
    out += central;
    put32(out, 0x06054b50); put16(out, 0); put16(out, 0); put16(out, (uint32_t)names.size()); put16(out, (uint32_t)names.size());
    put32(out, (uint32_t)central.size()); put32(out, at); put16(out, 0);
    std::string part = zip_path + ".part";
    if (!write_file(part, out)) return false;
    fs::rename(fs::u8path(part), fs::u8path(zip_path), ec);
    return !ec;
}

std::string zip_and_remove(const std::string& folder) {
    std::string zip = folder + ".zip";
    if (!write_zip(zip, folder)) return "";
    std::error_code ec;
    fs::remove_all(fs::u8path(folder), ec);
    return zip;
}

// ---- the crash handler ---------------------------------------------------------------------------------
// Writes <reports>/crash-<seconds since 1970>/ (about.txt with the cause, ticks.tsv, input.tsv) and
// <reports>/crash-pending.txt naming it; then the fault goes on to whoever handled it before (the
// system's report, Godot's own handler, host_win32.cpp's line).  It formats with snprintf into buffers of
// its own and writes with the system's calls: the process is broken, so it allocates nothing.
std::atomic<int> g_crashing{0};
char g_crash_dir[1200];
bool g_test_crash = false;                              // RTA_TESTERKIT_CRASH=1: the fault of "app report crash" ends the process after its report
                                                        // (no system crash report, no box of the system's on a test machine)

#ifdef _WIN32
typedef HANDLE Out;
wchar_t g_wide[2048];
const wchar_t* wide_path(const char* path) { if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, g_wide, 2048)) g_wide[0] = 0; return g_wide; }
Out out_open(const char* path) { return CreateFileW(wide_path(path), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr); }
bool out_ok(Out h) { return h != INVALID_HANDLE_VALUE; }
void out_write(Out h, const char* p, size_t n) { DWORD w; WriteFile(h, p, (DWORD)n, &w, nullptr); }
void out_close(Out h) { CloseHandle(h); }
void make_dir(const char* path) { CreateDirectoryW(wide_path(path), nullptr); }
#else
typedef int Out;
Out out_open(const char* path) { return open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644); }
bool out_ok(Out h) { return h >= 0; }
void out_write(Out h, const char* p, size_t n) { while (n > 0) { ssize_t w = write(h, p, n); if (w <= 0) return; p += w; n -= (size_t)w; } }
void out_close(Out h) { close(h); }
void make_dir(const char* path) { mkdir(path, 0755); }
#endif
void out_text(Out h, const char* s) { out_write(h, s, strlen(s)); }

void crash_path(char* out, size_t size, const char* name) { snprintf(out, size, "%s/%s", g_crash_dir, name); }

void write_rings(const char* dir_unused) {
    (void)dir_unused;
    static char path[1300], row[1024];
    crash_path(path, sizeof path, "ticks.tsv");
    Out h = out_open(path);
    if (out_ok(h)) {
        int n = tick_head(row, sizeof row);
        out_write(h, row, (size_t)n);
        uint64_t count = g_tick_count.load(), first = count > RING ? count - RING : 0;
        for (uint64_t k = first; k < count; k++) { n = tick_row(g_ticks[k % RING], row, sizeof row); out_write(h, row, (size_t)n); }
        out_close(h);
    }
    crash_path(path, sizeof path, "input.tsv");
    h = out_open(path);
    if (out_ok(h)) {
        out_text(h, INPUT_HEAD);
        uint64_t count = g_input_count.load(), first = count > RING ? count - RING : 0;
        for (uint64_t k = first; k < count; k++) { int n = input_row(g_inputs[k % RING], row, sizeof row); out_write(h, row, (size_t)n); }
        out_close(h);
    }
}

// begins the report; returns the open about.txt (the cause is written by the caller), the rings written
Out crash_begin(const char* headline) {
    snprintf(g_crash_dir, sizeof g_crash_dir, "%s/crash-%lld", g_reports_c, (long long)time(nullptr));
    make_dir(g_reports_c);
    make_dir(g_crash_dir);
    static char path[1300];
    crash_path(path, sizeof path, "about.txt");
    Out h = out_open(path);
    if (out_ok(h)) {
        out_text(h, g_about);
        out_text(h, "cause = ");
        out_text(h, headline);
        out_text(h, "\n");
    }
    write_rings(g_crash_dir);
    return h;
}
void crash_end(Out h) {
    if (out_ok(h)) out_close(h);
    static char path[1300];
    snprintf(path, sizeof path, "%s/crash-pending.txt", g_reports_c);
    Out p = out_open(path);
    if (out_ok(p)) { out_text(p, g_crash_dir); out_text(p, "\n"); out_close(p); }
    static char line[1400];
    snprintf(line, sizeof line, "\nThe program failed. A crash report is in %s (zipped at the next start).\n", g_crash_dir);
#ifdef _WIN32
    DWORD w;
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), line, (DWORD)strlen(line), &w, nullptr);
#else
    out_write(2, line, strlen(line));
#endif
}

#ifdef _WIN32
LPTOP_LEVEL_EXCEPTION_FILTER g_previous_filter = nullptr;
void module_of(uintptr_t at, char* out, size_t size) {
    HMODULE m = nullptr;
    char name[MAX_PATH] = "?";
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)at, &m) && m) {
        GetModuleFileNameA(m, name, sizeof name);
        const char* base = strrchr(name, '\\');
        snprintf(out, size, "%s+0x%llx", base ? base + 1 : name, (unsigned long long)(at - (uintptr_t)m));
    } else snprintf(out, size, "0x%llx", (unsigned long long)at);
}
LONG WINAPI on_exception(EXCEPTION_POINTERS* info) {
    if (g_crashing.exchange(1) == 0) {
        const EXCEPTION_RECORD* r = info->ExceptionRecord;
        static char text[2048], where[600];
        module_of((uintptr_t)r->ExceptionAddress, where, sizeof where);
        snprintf(text, sizeof text, "exception 0x%08lx at %s", r->ExceptionCode, where);
        Out h = crash_begin(text);
        if (out_ok(h)) {
            if (r->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && r->NumberParameters >= 2) {
                snprintf(text, sizeof text, "access = %s 0x%llx\n", r->ExceptionInformation[0] ? "writing" : "reading", (unsigned long long)r->ExceptionInformation[1]);
                out_text(h, text);
            }
            snprintf(text, sizeof text, "thread = %lu\n", GetCurrentThreadId());
            out_text(h, text);
#if defined(_M_X64) || defined(__x86_64__)
            // words on the stack that point into a loaded module: the calls the fault was inside, most of them
            out_text(h, "stack (words pointing into code, innermost first):\n");
            const uintptr_t* sp = (const uintptr_t*)info->ContextRecord->Rsp;
            int found = 0;
            for (int k = 0; k < 4096 && found < 48; k++) {
                MEMORY_BASIC_INFORMATION mb;
                if (!VirtualQuery(sp + k, &mb, sizeof mb) || mb.State != MEM_COMMIT || (mb.Protect & (PAGE_NOACCESS | PAGE_GUARD))) break;
                uintptr_t v = sp[k];
                MEMORY_BASIC_INFORMATION code;
                if (v < 0x10000 || !VirtualQuery((LPCVOID)v, &code, sizeof code) || code.Type != MEM_IMAGE ||
                    !(code.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))) continue;
                module_of(v, where, sizeof where);
                snprintf(text, sizeof text, "  %s\n", where);
                out_text(h, text);
                found++;
            }
#endif
        }
        crash_end(h);
        if (g_test_crash) TerminateProcess(GetCurrentProcess(), 70);
    }
    return g_previous_filter ? g_previous_filter(info) : EXCEPTION_CONTINUE_SEARCH;
}
void install_handler() { g_previous_filter = SetUnhandledExceptionFilter(on_exception); }
#else
struct sigaction g_previous[32];
const int SIGNALS[] = {SIGSEGV, SIGBUS, SIGILL, SIGFPE, SIGABRT, SIGTRAP};
void on_signal(int sig, siginfo_t* info, void* context) {
    if (g_crashing.exchange(1) == 0) {
        static char text[512];
        snprintf(text, sizeof text, "signal %d (%s) at address %p", sig, sig == SIGSEGV ? "access fault" : sig == SIGBUS ? "bus error" : sig == SIGILL ? "illegal instruction" :
                 sig == SIGFPE ? "arithmetic" : sig == SIGABRT ? "abort" : "trap", info ? info->si_addr : nullptr);
        Out h = crash_begin(text);
        if (out_ok(h)) {
#ifdef TK_BACKTRACE
            out_text(h, "stack:\n");
            void* frames[64];
            int n = backtrace(frames, 64);
            backtrace_symbols_fd(frames, n, h);
#endif
        }
        crash_end(h);
        if (g_test_crash) _exit(70);
    }
    // on to whoever had it before: a handler of its own is called as the system would have (Godot's prints its
    // stack); otherwise the system's own action, said again once this handler returns (the crash report, the end)
    if (sig < 0 || sig >= 32) return;
    const struct sigaction& before = g_previous[sig];
    if ((before.sa_flags & SA_SIGINFO) && before.sa_sigaction) { before.sa_sigaction(sig, info, context); return; }
    if (!(before.sa_flags & SA_SIGINFO) && before.sa_handler != SIG_DFL && before.sa_handler != SIG_IGN) { before.sa_handler(sig); return; }
    signal(sig, SIG_DFL);
    raise(sig);
}
void install_handler() {
    static std::vector<char> alt(256 * 1024);
    stack_t st{};
    st.ss_sp = alt.data(); st.ss_size = alt.size();
    sigaltstack(&st, nullptr);                              // this thread's: a stack that ran out still gets its report
    struct sigaction sa{};
    sa.sa_sigaction = on_signal;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&sa.sa_mask);
    for (int sig : SIGNALS) {
        sigaction(sig, &sa, &g_previous[sig]);
        if ((g_previous[sig].sa_flags & SA_SIGINFO) && g_previous[sig].sa_sigaction == on_signal) g_previous[sig] = {};     // a second start
    }
}
#endif

// ---- the overlay's letters: 5 x 7, drawn as squares ----------------------------------------------------
const uint8_t FONT[][7] = {
    {0x00,0x00,0x00,0x00,0x00,0x00,0x00} /*   */, {0x04,0x04,0x04,0x04,0x04,0x00,0x04} /* ! */, {0x0a,0x0a,0x00,0x00,0x00,0x00,0x00} /* " */, {0x0a,0x1f,0x0a,0x0a,0x0a,0x1f,0x0a} /* # */,
    {0x04,0x0f,0x14,0x0e,0x05,0x1e,0x04} /* $ */, {0x18,0x19,0x02,0x04,0x08,0x13,0x03} /* % */, {0x0c,0x12,0x14,0x08,0x15,0x12,0x0d} /* & */, {0x04,0x04,0x00,0x00,0x00,0x00,0x00} /* ' */,
    {0x02,0x04,0x08,0x08,0x08,0x04,0x02} /* ( */, {0x08,0x04,0x02,0x02,0x02,0x04,0x08} /* ) */, {0x00,0x04,0x15,0x0e,0x15,0x04,0x00} /* * */, {0x00,0x04,0x04,0x1f,0x04,0x04,0x00} /* + */,
    {0x00,0x00,0x00,0x00,0x0c,0x04,0x08} /* , */, {0x00,0x00,0x00,0x1f,0x00,0x00,0x00} /* - */, {0x00,0x00,0x00,0x00,0x00,0x0c,0x0c} /* . */, {0x00,0x01,0x02,0x04,0x08,0x10,0x00} /* / */,
    {0x0e,0x11,0x13,0x15,0x19,0x11,0x0e} /* 0 */, {0x04,0x0c,0x04,0x04,0x04,0x04,0x0e} /* 1 */, {0x0e,0x11,0x01,0x02,0x04,0x08,0x1f} /* 2 */, {0x1f,0x02,0x04,0x02,0x01,0x11,0x0e} /* 3 */,
    {0x02,0x06,0x0a,0x12,0x1f,0x02,0x02} /* 4 */, {0x1f,0x10,0x1e,0x01,0x01,0x11,0x0e} /* 5 */, {0x06,0x08,0x10,0x1e,0x11,0x11,0x0e} /* 6 */, {0x1f,0x01,0x02,0x04,0x08,0x08,0x08} /* 7 */,
    {0x0e,0x11,0x11,0x0e,0x11,0x11,0x0e} /* 8 */, {0x0e,0x11,0x11,0x0f,0x01,0x02,0x0c} /* 9 */, {0x00,0x0c,0x0c,0x00,0x0c,0x0c,0x00} /* : */, {0x00,0x0c,0x0c,0x00,0x0c,0x04,0x08} /* ; */,
    {0x02,0x04,0x08,0x10,0x08,0x04,0x02} /* < */, {0x00,0x00,0x1f,0x00,0x1f,0x00,0x00} /* = */, {0x08,0x04,0x02,0x01,0x02,0x04,0x08} /* > */, {0x0e,0x11,0x01,0x02,0x04,0x00,0x04} /* ? */,
    {0x0e,0x11,0x01,0x0d,0x15,0x15,0x0e} /* @ */, {0x0e,0x11,0x11,0x1f,0x11,0x11,0x11} /* A */, {0x1e,0x11,0x11,0x1e,0x11,0x11,0x1e} /* B */, {0x0e,0x11,0x10,0x10,0x10,0x11,0x0e} /* C */,
    {0x1c,0x12,0x11,0x11,0x11,0x12,0x1c} /* D */, {0x1f,0x10,0x10,0x1e,0x10,0x10,0x1f} /* E */, {0x1f,0x10,0x10,0x1e,0x10,0x10,0x10} /* F */, {0x0e,0x11,0x10,0x17,0x11,0x11,0x0f} /* G */,
    {0x11,0x11,0x11,0x1f,0x11,0x11,0x11} /* H */, {0x0e,0x04,0x04,0x04,0x04,0x04,0x0e} /* I */, {0x07,0x02,0x02,0x02,0x02,0x12,0x0c} /* J */, {0x11,0x12,0x14,0x18,0x14,0x12,0x11} /* K */,
    {0x10,0x10,0x10,0x10,0x10,0x10,0x1f} /* L */, {0x11,0x1b,0x15,0x15,0x11,0x11,0x11} /* M */, {0x11,0x11,0x19,0x15,0x13,0x11,0x11} /* N */, {0x0e,0x11,0x11,0x11,0x11,0x11,0x0e} /* O */,
    {0x1e,0x11,0x11,0x1e,0x10,0x10,0x10} /* P */, {0x0e,0x11,0x11,0x11,0x15,0x12,0x0d} /* Q */, {0x1e,0x11,0x11,0x1e,0x14,0x12,0x11} /* R */, {0x0f,0x10,0x10,0x0e,0x01,0x01,0x1e} /* S */,
    {0x1f,0x04,0x04,0x04,0x04,0x04,0x04} /* T */, {0x11,0x11,0x11,0x11,0x11,0x11,0x0e} /* U */, {0x11,0x11,0x11,0x11,0x11,0x0a,0x04} /* V */, {0x11,0x11,0x11,0x15,0x15,0x15,0x0a} /* W */,
    {0x11,0x11,0x0a,0x04,0x0a,0x11,0x11} /* X */, {0x11,0x11,0x0a,0x04,0x04,0x04,0x04} /* Y */, {0x1f,0x01,0x02,0x04,0x08,0x10,0x1f} /* Z */, {0x0e,0x08,0x08,0x08,0x08,0x08,0x0e} /* [ */,
    {0x00,0x10,0x08,0x04,0x02,0x01,0x00} /* \ */, {0x0e,0x02,0x02,0x02,0x02,0x02,0x0e} /* ] */, {0x04,0x0a,0x11,0x00,0x00,0x00,0x00} /* ^ */, {0x00,0x00,0x00,0x00,0x00,0x00,0x1f} /* _ */,
    {0x08,0x04,0x00,0x00,0x00,0x00,0x00} /* ` */, {0x02,0x04,0x04,0x08,0x04,0x04,0x02} /* { */, {0x04,0x04,0x04,0x04,0x04,0x04,0x04} /* | */, {0x08,0x04,0x04,0x02,0x04,0x04,0x08} /* } */,
    {0x00,0x00,0x08,0x15,0x02,0x00,0x00} /* ~ */,
};
const uint8_t* glyph(unsigned char c) {
    if (c >= 'a' && c <= 'z') c = (unsigned char)(c - 32);       // shown in capitals (the text keeps its own)
    if (c >= 32 && c <= 96) return FONT[c - 32];
    if (c >= 123 && c <= 126) return FONT[65 + (c - 123)];
    return FONT['?' - 32];
}

struct Painter {
    render::FrameList& frame;
    float X, Y, W, H, px;                               // the shown rectangle; one letter pixel
    size_t first;
    explicit Painter(render::FrameList& f) : frame(f) {
        X = (float)f.show_rect[0]; Y = (float)f.show_rect[1]; W = (float)f.show_rect[2]; H = (float)f.show_rect[3];
        px = std::max(1.0f, std::floor(H / 448.0f + 0.25f));
        first = f.vertices.size();
    }
    void quad(float x0, float y0, float x1, float y1, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        render::Vertex v{};
        v.z = 1; v.q = 1; v.r = r; v.g = g; v.b = b; v.a = a;
        auto put = [&](float x, float y) { v.x = x; v.y = y; frame.vertices.push_back(v); };
        put(x0, y0); put(x1, y0); put(x0, y1); put(x1, y0); put(x1, y1); put(x0, y1);
    }
    float width(const std::string& s) const { return (float)s.size() * 6 * px; }
    void text(float x, float y, const std::string& s, uint8_t r = 0xf0, uint8_t g = 0xf0, uint8_t b = 0xf0) {
        for (unsigned char c : s) {
            const uint8_t* rows = glyph(c);
            for (int row = 0; row < 7; row++)
                for (int col = 0; col < 5; col++)
                    if (rows[row] & (0x10 >> col)) quad(x + col * px, y + row * px, x + (col + 1) * px, y + (row + 1) * px, r, g, b, 0x80);
            x += 6 * px;
        }
    }
    void finish() {
        if (frame.vertices.size() == first) return;
        render::DrawCmd cmd;
        cmd.kind = render::CMD_DRAW;
        cmd.prim = render::PK_TRIANGLES;
        cmd.first = (uint32_t)first;
        cmd.count = (uint32_t)(frame.vertices.size() - first);
        cmd.target = frame.show_target;
        cmd.scissor[0] = frame.show_rect[0]; cmd.scissor[1] = frame.show_rect[1];
        cmd.scissor[2] = frame.show_rect[0] + frame.show_rect[2]; cmd.scissor[3] = frame.show_rect[1] + frame.show_rect[3];
        cmd.blend = true; cmd.ba = 0; cmd.bb = 1; cmd.bc = 0; cmd.bd = 1;
        cmd.made_by = 2;
        frame.commands.push_back(cmd);
    }
};

// the text cut into lines of at most `columns` letters, at spaces where it can
std::vector<std::string> wrap(const std::string& text, size_t columns) {
    std::vector<std::string> lines;
    std::string rest = text;
    while (rest.size() > columns) {
        size_t cut = rest.rfind(' ', columns);
        if (cut == std::string::npos || cut == 0) cut = columns;
        lines.push_back(rest.substr(0, cut));
        rest = rest.substr(cut == columns ? cut : cut + 1);
    }
    lines.push_back(rest);
    return lines;
}

void finish_box(bool keep) {
    std::string folder, text;
    {
        std::lock_guard<std::mutex> hold(g_ui_lock);
        if (!g_box) return;
        g_box = false;
        g_box_flag = false;
        folder = g_box_folder;
        text = g_box_text;
        g_box_folder.clear();
        g_box_text.clear();
    }
    if (folder.empty()) return;
    // the picture is written by the drawing thread a picture or two later: the zip waits for it on a thread of its own
    std::thread([folder, text, keep] {
        std::string zip = finish(folder, text, keep);
        if (!keep) note("report dropped", 3);
        else if (zip.empty()) note("the report could not be written: see " + folder, 8);
        else {
            std::string shown = fs::u8path(zip).filename().u8string();
            note("report saved: reports/" + shown, 8);
            say("saved " + zip + " (it stays on this computer: send it yourself)");
        }
    }).detach();
}

}  // namespace

// ---- what the build is -------------------------------------------------------------------------------------
std::string build_id() { return RTA_BUILD_ID; }

std::string fix_set() {
    const uint32_t (*words)[2] = nullptr;
    unsigned count = recomp_patches(&words), set_count = recomp_patch_set_words();
    if (set_count > count) set_count = count;
    if (!count || !words) return "none (the game as on the disc)";
    // the figure the network driver tells other copies (net/netdrv.cpp): FNV-1a of the set's words in address order
    std::vector<std::pair<uint32_t, uint32_t>> sorted;
    for (unsigned k = 0; k < set_count; k++) sorted.push_back({words[k][0], words[k][1]});
    std::stable_sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    uint32_t hash = 2166136261u;
    for (const auto& word : sorted)
        for (uint32_t v : {word.first, word.second})
            for (int i = 0; i < 4; i++) hash = (hash ^ ((v >> (i * 8)) & 0xFF)) * 16777619u;
    char text[96];
    if (set_count < count) snprintf(text, sizeof text, "%08x (%u words, %u more of this build's own)", hash, set_count, count - set_count);
    else snprintf(text, sizeof text, "%08x (%u words)", hash, set_count);
    return text;
}

std::string platform() {
    std::string arch =
#if defined(__aarch64__) || defined(_M_ARM64)
        "arm64";
#elif defined(__x86_64__) || defined(_M_X64)
        "x86-64";
#else
        "other";
#endif
#ifdef _WIN32
    typedef LONG(WINAPI * GetVersion)(OSVERSIONINFOW*);
    OSVERSIONINFOW v{};
    v.dwOSVersionInfoSize = sizeof v;
    if (HMODULE nt = GetModuleHandleW(L"ntdll.dll"))
        if (auto get = (GetVersion)(void*)GetProcAddress(nt, "RtlGetVersion")) get(&v);
    char text[96];
    snprintf(text, sizeof text, "Windows %lu.%lu.%lu %s", v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber, arch.c_str());
    return text;
#elif defined(__APPLE__)
    char version[64] = "?";
    size_t size = sizeof version;
    sysctlbyname("kern.osproductversion", version, &size, nullptr, 0);
    return std::string("macOS ") + version + " " + arch;
#else
    utsname u{};
    uname(&u);
    return std::string(u.sysname) + " " + u.release + " " + arch;
#endif
}

std::string build_line() {
    std::string fix = fix_set();
    fix = fix.substr(0, fix.find(' '));
    return "RTA " + build_id() + "  fixes " + fix + "  " + platform();
}

// ---- start --------------------------------------------------------------------------------------------------
std::string start(const Setup& setup) {
    g_setup = setup;
    if (const char* forced = getenv("RTA_TESTERKIT")) if (strcmp(forced, "1") == 0) g_setup.person = true;
    if (g_setup.host_ui) g_setup.person = false;
    g_line = setup.line;
    g_reports = setup.data_dir + "/reports";
    snprintf(g_reports_c, sizeof g_reports_c, "%s", g_reports.c_str());
    std::error_code ec;
    fs::create_directories(fs::u8path(g_reports), ec);
    refresh_about();
    if (!g_started) install_handler();
    g_started = true;
    // a crash report of the run before
    std::string told;
    std::string pending = g_reports + "/crash-pending.txt";
    if (FILE* f = open_file(pending, "rb")) {
        char line[1200] = "";
        if (!fgets(line, sizeof line, f)) line[0] = 0;
        fclose(f);
        std::string folder = line;
        while (!folder.empty() && (folder.back() == '\n' || folder.back() == '\r')) folder.pop_back();
        fs::remove(fs::u8path(pending), ec);
        if (!folder.empty() && fs::is_directory(fs::u8path(folder), ec)) {
            // crash-<seconds since 1970> (what the handler could write) becomes crash-<local date and time>
            size_t dash = folder.rfind("crash-");
            if (dash != std::string::npos) {
                time_t when = (time_t)atoll(folder.c_str() + dash + 6);
                tm local{};
#ifdef _WIN32
                localtime_s(&local, &when);
#else
                localtime_r(&when, &local);
#endif
                char name[64];
                strftime(name, sizeof name, "crash-%Y%m%d-%H%M%S", &local);
                std::string renamed = folder.substr(0, dash) + name;
                fs::rename(fs::u8path(folder), fs::u8path(renamed), ec);
                if (!ec) folder = renamed;
            }
            std::string zip = zip_and_remove(folder);
            std::string where = zip.empty() ? folder : zip;
            told = "The program stopped unexpectedly last time. A crash report was written to\n" + where +
                   "\nIt stays on this computer; send it yourself to whoever asked you to test.";
            say("crash report of the last run: " + where);
            note("crash report from last time: reports/" + fs::u8path(where).filename().u8string(), 12);
        }
    }
    return told;
}

// ---- the game's thread ---------------------------------------------------------------------------------------
void blank(uint64_t number, const uint8_t* ram) {
    g_last_number = number;
    if (ram) {
        Tick t{};
        t.number = number;
        t.net_frame = (int32_t)rd32(ram, A_NET_FRAME);
        t.seed = rd32(ram, A_RAND_SEED);
        memcpy(t.level, ram + A_LEVEL_NAME, 12);
        t.players = (int32_t)rd32(ram, A_NUM_PLAYERS);
        for (int k = 0; k < PLAYERS; k++) {
            uint32_t record = party8_at(A_PLAYERS) + k * PLAYER_SIZE, object = rd32(ram, record + 0x43d8) & (RAM - 1);
            Tick::P& p = t.p[k];
            if (object) { p.x = rd32(ram, object + 0x10); p.y = rd32(ram, object + 0x14); p.z = rd32(ram, object + 0x18); p.state = (int32_t)rd32(ram, object + 0x58c); }
            p.hp = rd32(ram, record + 0xac);
            p.gold = (int32_t)rd32(ram, record + 0xe4);
            p.exp = (int32_t)rd32(ram, record + 0x5c);
        }
        std::lock_guard<std::mutex> hold(g_ring_lock);
        uint64_t k = g_tick_count.load();
        g_ticks[k % RING] = t;
        g_tick_count = k + 1;
    }
    if (number % 300 == 0) refresh_about();             // what a crash report says about the settings and the room
}

void pad(uint64_t number, rta::PadState& state) {
    bool blanked = false;
    if (g_setup.person) {
        // L3 + R3 together for a second: the box (once per hold)
        const uint16_t chord = rta::PAD_L3 | rta::PAD_R3;
        if ((state.buttons & chord) == chord) {
            if (++g_chord_blanks >= 60 && !g_chord_done && !g_box_flag) { g_chord_done = true; g_box_buttons = state.buttons; open_box(); }
        } else { g_chord_blanks = 0; g_chord_done = false; }
        if (g_box_flag) {
            // the controller in the box: Start saves, Select drops (pressed after the box opened)
            uint16_t pressed = state.buttons & ~g_box_buttons;
            g_box_buttons &= state.buttons;
            if (pressed & rta::PAD_START) box_key(KEY_ENTER);
            else if (pressed & rta::PAD_SELECT) box_key(KEY_ESCAPE);
            state = rta::PadState();
            blanked = true;
        }
    }
    Input r{number, state.buttons, state.lx, state.ly, state.rx, state.ry, (uint8_t)blanked};
    std::lock_guard<std::mutex> hold(g_ring_lock);
    uint64_t k = g_input_count.load();
    g_inputs[k % RING] = r;
    g_input_count = k + 1;
}

// ---- a report ------------------------------------------------------------------------------------------------
std::string begin(std::string& shot_path, bool want_shot, const std::string& host_lines) {
    std::string folder = g_reports + "/report-" + stamp("%Y%m%d-%H%M%S");
    std::error_code ec;
    for (int k = 2; fs::exists(fs::u8path(folder), ec); k++) folder = g_reports + "/report-" + stamp("%Y%m%d-%H%M%S") + "-" + std::to_string(k);
    fs::create_directories(fs::u8path(folder), ec);
    // the rings, copied as they stand
    std::vector<Tick> ticks;
    std::vector<Input> inputs;
    {
        std::lock_guard<std::mutex> hold(g_ring_lock);
        uint64_t count = g_tick_count.load(), first = count > RING ? count - RING : 0;
        for (uint64_t k = first; k < count; k++) ticks.push_back(g_ticks[k % RING]);
        count = g_input_count.load(); first = count > RING ? count - RING : 0;
        for (uint64_t k = first; k < count; k++) inputs.push_back(g_inputs[k % RING]);
    }
    std::string text;
    char row[1024];
    text.append(row, (size_t)tick_head(row, sizeof row));
    for (const Tick& t : ticks) text.append(row, (size_t)tick_row(t, row, sizeof row));
    write_file(folder + "/ticks.tsv", text);
    text = INPUT_HEAD;
    for (const Input& r : inputs) text.append(row, (size_t)input_row(r, row, sizeof row));
    write_file(folder + "/input.tsv", text);
    std::string info = about("bug report");
    info += host_lines;
    info += "taken = " + stamp("%Y-%m-%d %H:%M:%S") + "\n";
    info += "rows = " + std::to_string(ticks.size()) + " ticks, " + std::to_string(inputs.size()) + " inputs (one per vertical blank, 60 a second)\n";
    write_file(folder + "/about.txt", info);
    shot_path.clear();
    if (want_shot) {
        shot_path = folder + "/screenshot.png";
        if (g_setup.ask_shot) g_setup.ask_shot(shot_path);
    }
    say("taken: " + folder);
    return folder;
}

std::string finish(const std::string& folder, const std::string& text, bool keep) {
    std::error_code ec;
    // the picture: wait (up to 3 s) until it is there and its size stands still
    std::string shot = folder + "/screenshot.png";
    if (keep) {
        uintmax_t last = 0;
        for (int k = 0; k < 30; k++) {
            uintmax_t size = fs::exists(fs::u8path(shot), ec) ? fs::file_size(fs::u8path(shot), ec) : 0;
            if (size > 0 && size == last) break;
            last = size;
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    } else std::this_thread::sleep_for(std::chrono::milliseconds(500));
    if (!keep) { fs::remove_all(fs::u8path(folder), ec); return ""; }
    if (!text.empty()) write_file(folder + "/note.txt", text + "\n");
    return zip_and_remove(folder);
}

void open_box() {
    if (!g_started) return;
    {
        std::lock_guard<std::mutex> hold(g_ui_lock);
        if (g_box) return;
    }
    std::string shot;
    std::string folder = begin(shot, true);
    std::lock_guard<std::mutex> hold(g_ui_lock);
    g_box = true;
    g_box_flag = true;
    g_box_folder = folder;
    g_box_text.clear();
}

bool box_open() { return g_box_flag.load(); }

void box_key(Key key) {
    if (key == KEY_ENTER) finish_box(true);
    else if (key == KEY_ESCAPE) finish_box(false);
    else {
        std::lock_guard<std::mutex> hold(g_ui_lock);
        // one character back (a UTF-8 sequence whole)
        while (!g_box_text.empty()) {
            unsigned char c = (unsigned char)g_box_text.back();
            g_box_text.pop_back();
            if ((c & 0xC0) != 0x80) break;
        }
    }
}

void box_text(const std::string& utf8) {
    std::lock_guard<std::mutex> hold(g_ui_lock);
    for (unsigned char c : utf8)
        if (c >= 32 && c != 127 && g_box_text.size() < 400) g_box_text += (char)c;
}

void toggle_line() { g_line = !g_line; }
bool line_shown() { return g_line.load(); }

std::string last_note() {
    std::lock_guard<std::mutex> hold(g_ui_lock);
    return std::chrono::steady_clock::now() < g_note_until ? g_note : "";
}

// ---- tests ---------------------------------------------------------------------------------------------------
bool command(const std::string& text) {
    if (text.compare(0, 7, "report ") != 0 && text != "report") return false;
    std::string rest = text.size() > 7 ? text.substr(7) : "info";
    if (rest == "open") open_box();
    else if (rest.compare(0, 5, "type ") == 0) box_text(rest.substr(5));
    else if (rest == "enter") box_key(KEY_ENTER);
    else if (rest == "escape") box_key(KEY_ESCAPE);
    else if (rest == "backspace") box_key(KEY_BACKSPACE);
    else if (rest == "line") toggle_line();
    else if (rest == "crash") {
        const char* allowed = getenv("RTA_TESTERKIT_CRASH");
        if (allowed && strcmp(allowed, "1") == 0) { g_test_crash = true; say("an access fault on purpose (RTA_TESTERKIT_CRASH=1)"); volatile int* nowhere = nullptr; *nowhere = 1; }
        else say("report crash: only with RTA_TESTERKIT_CRASH=1");
    } else {
        std::string n = last_note();
        say(std::string("box ") + (box_open() ? "open" : "closed") + ", line " + (line_shown() ? "shown" : "hidden") + ", ticks " +
            std::to_string(g_tick_count.load()) + ", inputs " + std::to_string(g_input_count.load()) + ", note '" + n + "', build " + build_line());
    }
    return true;
}

// ---- the overlay ---------------------------------------------------------------------------------------------
float text(render::FrameList& frame, float x, float y, float px, const std::string& s, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    float x0 = x;
    render::Vertex v{};
    v.z = 1; v.q = 1; v.r = r; v.g = g; v.b = b; v.a = a;
    auto put = [&](float vx, float vy) { v.x = vx; v.y = vy; frame.vertices.push_back(v); };
    for (unsigned char c : s) {
        const uint8_t* rows = glyph(c);
        for (int row = 0; row < 7; row++)
            for (int col = 0; col < 5; col++)
                if (rows[row] & (0x10 >> col)) {
                    float qx0 = x + col * px, qy0 = y + row * px, qx1 = qx0 + px, qy1 = qy0 + px;
                    put(qx0, qy0); put(qx1, qy0); put(qx0, qy1); put(qx1, qy0); put(qx1, qy1); put(qx0, qy1);
                }
        x += 6 * px;
    }
    return x - x0;
}

void overlay(render::FrameList& frame) {
    if (!g_setup.person || !frame.show_target || frame.show_rect[2] <= 0 || frame.show_rect[3] <= 0) return;
    bool box;
    std::string text, shown_note;
    {
        std::lock_guard<std::mutex> hold(g_ui_lock);
        box = g_box;
        text = g_box_text;
        if (std::chrono::steady_clock::now() < g_note_until) shown_note = g_note;
    }
    bool line = g_line.load();
    if (!box && !line && shown_note.empty()) return;
    Painter p(frame);
    float m = 4 * p.px, lh = 9 * p.px;
    if (line) {
        static const std::string text_line = build_line();
        float w = p.width(text_line);
        float x = p.X + p.W - w - m, y = p.Y + m;
        p.quad(x - 2 * p.px, y - 2 * p.px, x + w + p.px, y + 8 * p.px, 0, 0, 0, 0x50);
        p.text(x, y, text_line, 0xc8, 0xc8, 0xc8);
    }
    if (!shown_note.empty() && !box) {
        float w = p.width(shown_note), x = p.X + (p.W - w) * 0.5f, y = p.Y + p.H * 0.12f;
        p.quad(x - 4 * p.px, y - 4 * p.px, x + w + 3 * p.px, y + 11 * p.px, 0, 0, 0, 0x68);
        p.text(x, y, shown_note, 0xf0, 0xe0, 0x90);
    }
    if (box) {
        float bw = std::min(p.W - 2 * m, 100 * 6 * p.px), x = p.X + (p.W - bw) * 0.5f;
        size_t columns = (size_t)std::max(10.0f, (bw - 8 * p.px) / (6 * p.px));
        std::vector<std::string> lines = wrap(text + "_", columns);
        if (lines.size() > 8) lines.erase(lines.begin(), lines.end() - 8);
        float bh = (5 + (float)lines.size()) * lh + 6 * p.px, y = p.Y + (p.H - bh) * 0.5f;
        p.quad(x, y, x + bw, y + bh, 0x10, 0x12, 0x18, 0x70);
        p.quad(x, y, x + bw, y + p.px, 0xf0, 0xe0, 0x90, 0x80);
        float tx = x + 4 * p.px, ty = y + 4 * p.px;
        p.text(tx, ty, "REPORT A BUG", 0xf0, 0xe0, 0x90);
        ty += lh * 1.5f;
        p.text(tx, ty, "What happened? (optional)", 0xc8, 0xc8, 0xc8);
        ty += lh * 1.25f;
        for (const std::string& l : lines) { p.text(tx, ty, l); ty += lh; }
        ty += lh * 0.5f;
        p.text(tx, ty, "Enter or Start: save     Esc or Select: drop", 0x98, 0x98, 0x98);
    }
    p.finish();
}

}  // namespace testerkit
