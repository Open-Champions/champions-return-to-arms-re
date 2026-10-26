// control.h - a control socket for test runs of the application (--control PATH).
//
// It speaks the protocol of the emulator build's control socket (tools/play-net/ctl.py:
// one command a line, one line of answer starting with "ok"), with the commands a tour
// needs, so that one driver script walks both builds through the same places:
//
//   press <buttons> | release <buttons>|all | tap <buttons> [hold [after]] | stick l|r x y
//   wait <blanks>
//   peek <expression> u8|u16|u32|s32|x32|f32|strN|hexN      numbers, + and -, [x] = the word at x
//   poke <expression> u8|u16|u32|f32|str <value>
//   shotfb <file.png|.bmp>      the picture of this vertical blank at its drawn size (answered
//                               when the file is written); `shot` is the same here
//   info                        whatever the application's info callback says (key=value ...)
//   app <text>                  an "app ..." script line (app_main.cpp)
//   call <address> [a0 [a1]]    a function of the game at this vertical blank, as the script's `call`
//                               (rt/script.cpp: a test aid; tour.py's level-up)
//   quit
//
// Commands are carried out on the game's thread at a vertical blank (where the controller
// is read), as many as there are until one of them waits.  POSIX sockets: a test aid, not
// part of what a player uses.
#pragma once
#include "ramsize.h"
#include "iface.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <vector>

void rt_call_handler(uint32_t address, uint32_t a0, uint32_t a1);     // rt/rt.h

namespace app {

struct Control {
    // set by the application before start()
    std::function<std::string()> info;                           // "key=value key=value"
    std::function<void(const std::string& text, uint64_t frame)> app_command;
    std::function<void(const std::string& path)> shot;          // ask for the picture of this blank
    std::function<void()> quit;
    std::function<uint16_t(const std::string&)> buttons_of;
    std::atomic<uint64_t> shots_written{0};                      // the application counts the pictures it wrote

    // what the socket holds on port 1
    uint16_t held = 0;
    uint8_t sticks[4] = {128, 128, 128, 128};
    bool active() const { return listen_fd >= 0; }

    bool start(const std::string& path) {
        unlink(path.c_str());
        listen_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        sockaddr_un address;
        memset(&address, 0, sizeof address);
        address.sun_family = AF_UNIX;
        snprintf(address.sun_path, sizeof address.sun_path, "%s", path.c_str());
        if (listen_fd < 0 || bind(listen_fd, (sockaddr*)&address, sizeof address) != 0 || listen(listen_fd, 1) != 0) {
            if (listen_fd >= 0) close(listen_fd);
            listen_fd = -1;
            return false;
        }
        std::thread reader([this] { read_loop(); });
        reader.detach();
        return true;
    }

    // The game's thread, once per vertical blank.
    void on_blank(uint64_t frame) {
        if (!active()) return;
        if (phase == TAP_HOLD) {
            if (--left > 0) return;
            held &= (uint16_t)~tap_buttons;
            phase = WAITING;
            left = tap_after + 1;
        }
        if (phase == WAITING) {
            if (--left > 0) return;
            answer("ok");
            phase = IDLE;
        }
        if (phase == SHOT) {
            if (shots_written.load() < shots_wanted) return;
            answer("ok");
            phase = IDLE;
        }
        std::string line;
        while (phase == IDLE && next_line(line)) execute(line, frame);
    }

  private:
    enum Phase { IDLE, TAP_HOLD, WAITING, SHOT };
    Phase phase = IDLE;
    int64_t left = 0, tap_after = 0;
    uint16_t tap_buttons = 0;
    uint64_t shots_wanted = 0;
    int listen_fd = -1;
    std::atomic<int> fd{-1};
    std::mutex lock;
    std::deque<std::string> lines;

    void read_loop() {
        for (;;) {
            int client = accept(listen_fd, nullptr, nullptr);
            if (client < 0) return;
            fd = client;
            std::string buffer;
            char chunk[4096];
            for (;;) {
                ssize_t n = read(client, chunk, sizeof chunk);
                if (n <= 0) break;
                buffer.append(chunk, (size_t)n);
                size_t at;
                while ((at = buffer.find('\n')) != std::string::npos) {
                    std::lock_guard<std::mutex> hold(lock);
                    lines.push_back(buffer.substr(0, at));
                    buffer.erase(0, at + 1);
                }
            }
            fd = -1;
            close(client);
        }
    }
    bool next_line(std::string& line) {
        std::lock_guard<std::mutex> hold(lock);
        if (lines.empty()) return false;
        line = lines.front();
        lines.pop_front();
        return true;
    }
    void answer(const std::string& text) {
        int client = fd;
        if (client < 0) return;
        std::string line = text + "\n";
        size_t done = 0;
        while (done < line.size()) {
            ssize_t n = write(client, line.data() + done, line.size() - done);
            if (n <= 0) break;
            done += (size_t)n;
        }
    }

    // ---- expressions over main memory ----
    static const uint32_t RAM = RAM_SIZE;      // ramsize.h
    struct Parser {
        const std::string& s;
        size_t i = 0;
        bool bad = false;
        explicit Parser(const std::string& text) : s(text) {}
        uint32_t factor() {
            while (i < s.size() && s[i] == ' ') i++;
            if (i >= s.size()) { bad = true; return 0; }
            if (s[i] == '[') {
                i++;
                uint32_t a = sum();
                if (i < s.size() && s[i] == ']') i++; else bad = true;
                uint32_t v = 0;
                if ((a & 0x1FFFFFFF) <= RAM - 4) memcpy(&v, rta::memory() + (a & 0x1FFFFFFF), 4);
                return v;
            }
            if (s[i] == '(') { i++; uint32_t v = sum(); if (i < s.size() && s[i] == ')') i++; else bad = true; return v; }
            char* end = nullptr;
            unsigned long v = strtoul(s.c_str() + i, &end, 0);
            if (end == s.c_str() + i) { bad = true; return 0; }
            i = (size_t)(end - s.c_str());
            return (uint32_t)v;
        }
        uint32_t sum() {
            uint32_t v = factor();
            for (;;) {
                while (i < s.size() && s[i] == ' ') i++;
                if (i < s.size() && s[i] == '+') { i++; v += factor(); }
                else if (i < s.size() && s[i] == '-') { i++; v -= factor(); }
                else return v;
            }
        }
    };
    static uint8_t* at(uint32_t address, uint32_t size) {
        address &= 0x1FFFFFFF;
        return address <= RAM - size && size <= RAM ? rta::memory() + address : nullptr;
    }

    void execute(const std::string& line, uint64_t frame) {
        std::vector<std::string> w;
        for (size_t k = 0; k < line.size();) {
            while (k < line.size() && isspace((unsigned char)line[k])) k++;
            size_t end = k;
            while (end < line.size() && !isspace((unsigned char)line[end])) end++;
            if (end > k) w.push_back(line.substr(k, end - k));
            k = end;
        }
        if (w.empty()) { answer("ok"); return; }
        const std::string& c = w[0];
        auto number = [&](size_t k, long fallback) { return k < w.size() ? strtol(w[k].c_str(), nullptr, 0) : fallback; };
        if (c == "press" && w.size() >= 2) { held |= buttons_of(w[1]); answer("ok"); }
        else if (c == "release" && w.size() >= 2) { held = w[1] == "all" ? 0 : (uint16_t)(held & ~buttons_of(w[1])); answer("ok"); }
        else if (c == "tap" && w.size() >= 2) {
            tap_buttons = buttons_of(w[1]);
            held |= tap_buttons;
            left = number(2, 8);
            tap_after = number(3, 8);
            if (left < 1) left = 1;
            phase = TAP_HOLD;
        }
        else if (c == "stick" && w.size() >= 4) {
            int base = (w[1] == "r" || w[1] == "R") ? 2 : 0;
            sticks[base] = (uint8_t)number(2, 128); sticks[base + 1] = (uint8_t)number(3, 128);
            answer("ok");
        }
        else if (c == "wait") { left = number(1, 1); if (left < 1) left = 1; phase = WAITING; }
        else if (c == "peek" && w.size() >= 3) {
            // the expression may hold spaces: everything between the command and the type
            size_t type_at = line.rfind(w.back());
            std::string expr = line.substr(line.find(c) + c.size(), type_at - (line.find(c) + c.size()));
            const std::string& type = w.back();
            Parser p(expr);
            uint32_t a = p.sum();
            if (p.bad) { answer("error: expression " + expr); return; }
            char text[64];
            if (type == "u8" || type == "u16" || type == "u32" || type == "x32" || type == "s32" || type == "f32") {
                uint32_t size = type == "u8" ? 1 : type == "u16" ? 2 : 4, v = 0;
                uint8_t* m = at(a, size);
                if (!m) { answer("error: address"); return; }
                memcpy(&v, m, size);
                if (type == "f32") { float f; memcpy(&f, &v, 4); snprintf(text, sizeof text, "ok %.9g", f); }
                else if (type == "s32") snprintf(text, sizeof text, "ok %d", (int32_t)v);
                else if (type == "x32") snprintf(text, sizeof text, "ok %08x", v);
                else snprintf(text, sizeof text, "ok %u", v);
                answer(text);
            } else if (type.compare(0, 3, "str") == 0 || type.compare(0, 3, "hex") == 0) {
                uint32_t size = (uint32_t)atoi(type.c_str() + 3);
                uint8_t* m = at(a, size);
                if (!m || !size || size > 65536) { answer("error: address"); return; }
                std::string out = "ok ";
                if (type[0] == 's') for (uint32_t k = 0; k < size && m[k]; k++) out += (m[k] >= 0x20 && m[k] < 0x7F) ? (char)m[k] : '?';
                else for (uint32_t k = 0; k < size; k++) { snprintf(text, sizeof text, "%02x", m[k]); out += text; }
                answer(out);
            } else answer("error: type " + type);
        }
        else if (c == "call" && w.size() >= 2) {
            uint32_t v[3] = {0, 0, 0};
            for (size_t k = 1; k < w.size() && k < 4; k++) {
                Parser p(w[k]);
                v[k - 1] = p.sum();
                if (p.bad) { answer("error: expression " + w[k]); return; }
            }
            rt_call_handler(v[0], v[1], v[2]);
            answer("ok");
        }
        else if (c == "poke" && w.size() >= 4) {
            const std::string& value = w.back();
            const std::string& type = w[w.size() - 2];
            size_t type_at = line.rfind(type, line.rfind(value) - 1);
            std::string expr = line.substr(line.find(c) + c.size(), type_at - (line.find(c) + c.size()));
            Parser p(expr);
            uint32_t a = p.sum();
            if (p.bad) { answer("error: expression " + expr); return; }
            if (type == "str") {
                uint8_t* m = at(a, (uint32_t)value.size() + 1);
                if (!m) { answer("error: address"); return; }
                memcpy(m, value.c_str(), value.size() + 1);
            } else {
                uint32_t size = type == "u8" ? 1 : type == "u16" ? 2 : 4;
                uint8_t* m = at(a, size);
                if (!m) { answer("error: address"); return; }
                uint32_t v = (uint32_t)strtoul(value.c_str(), nullptr, 0);
                if (type == "f32") { float f = (float)atof(value.c_str()); memcpy(&v, &f, 4); }
                memcpy(m, &v, size);
            }
            answer("ok");
        }
        else if ((c == "shotfb" || c == "shot") && w.size() >= 2) {
            shots_wanted = shots_written.load() + 1;
            shot(line.substr(line.find(w[1])));
            phase = SHOT;
        }
        else if (c == "info") answer("ok frame=" + std::to_string(frame) + " " + (info ? info() : std::string()));
        else if (c == "app" && w.size() >= 2) { if (app_command) app_command(line.substr(line.find(w[1])), frame); answer("ok"); }
        else if (c == "quit") { answer("ok"); if (quit) quit(); }
        else if (c == "throttle" || c == "pref") answer("ok");       // the emulator's; nothing to set here
        else answer("error: unknown command " + c);
    }
};

}  // namespace app
