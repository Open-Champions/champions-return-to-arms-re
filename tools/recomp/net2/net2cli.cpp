// net2cli.cpp - session.h from a terminal or a test: one command per line on standard
// input, events and answers on standard output.  No game inside.
//
//   net2cli --mock [--speed N]
//   net2cli --service 127.0.0.1:41900 --data DIR [--name NAME] [--fix 27f61e1d:91] [--arith 3:0]
//   net2cli --data DIR            (the service from RTA_NET2_SERVICE or DIR/net2-service.txt)
//
// The commands are clicmd.cpp's.
#include "clicmd.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>

#include <fcntl.h>
#include <unistd.h>

int main(int argc, char** argv) {
    net2_config config{};
    config.struct_size = sizeof config;
    std::string speed;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        const char* v = i + 1 < argc ? argv[i + 1] : "";
        if (a == "--mock") config.mock = 1;
        else if (a == "--service") { config.service = v; i++; }
        else if (a == "--data") { config.data_dir = v; i++; }
        else if (a == "--name") { config.name = v; i++; }
        else if (a == "--speed") { speed = v; i++; }
        else if (a == "--local-only") config.local_only = 1;
        else if (a == "--fix") { unsigned set = 0, words = 0; sscanf(v, "%x:%u", &set, &words); config.fix_set = set; config.fix_words = (uint16_t)words; i++; }
        else if (a == "--arith") { unsigned can = 0, does = 0; sscanf(v, "%u:%u", &can, &does); config.arith_can = (uint8_t)can; config.arith_does = (uint8_t)does; i++; }
        else { fprintf(stderr, "net2cli: unknown option %s\n", a.c_str()); return 2; }
    }
    config.build = "net2cli";
    net2* n = net2_open(&config);
    if (!speed.empty()) net2_set(n, "mock-speed", speed.c_str());
    fcntl(0, F_SETFL, fcntl(0, F_GETFL) | O_NONBLOCK);
    std::string pending;
    bool quit = false, input_open = true;
    double wait = 0;
    auto wait_until = std::chrono::steady_clock::now();
    while (!quit) {
        net2_poll(n);
        net2_event e;
        while (net2_next_event(n, &e)) net2_cli_event(e);
        bool waiting = std::chrono::steady_clock::now() < wait_until;
        if (!waiting) {
            char buffer[1024];
            ssize_t got = input_open ? read(0, buffer, sizeof buffer) : 0;
            if (got > 0) pending.append(buffer, (size_t)got);
            else if (got == 0 && input_open) { input_open = false; if (!pending.empty() && pending.back() != '\n') pending += '\n'; }
            size_t end;
            while (!quit && (end = pending.find('\n')) != std::string::npos) {
                std::string line = pending.substr(0, end);
                pending.erase(0, end + 1);
                while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
                wait = 0;
                net2_cli_command(n, line, quit, wait);
                if (wait > 0) { wait_until = std::chrono::steady_clock::now() + std::chrono::milliseconds((long)(wait * 1000)); break; }
            }
            if (!input_open && pending.empty() && std::chrono::steady_clock::now() >= wait_until) quit = true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(15));
    }
    net2_close(n);
    return 0;
}
