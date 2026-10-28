// Production dynamic loader, with authored old/new ABI-only libraries. No engine or game.
#include "../extension/src/rta_library.cpp"
#include <cstdio>
#include <cstdint>
static int checks = 0, failures = 0;
static void check(bool pass, const char* label) {
    ++checks;
    if (!pass) { ++failures; std::printf("FAIL %s\n", label); }
}
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    RtaLibrary old, modern;
    check(old.load(argv[1]), "older version6 library loads without optional rumble symbol");
    check(old.loaded && !old.rtag_rumble, "older library retains null optional pointer");
    check(modern.load(argv[2]), "new version6 library loads with optional symbol");
    check(modern.loaded && modern.rtag_rumble, "optional function is resolved by production loader");
    if (!modern.loaded || !modern.rtag_rumble) return 1;
    auto command = reinterpret_cast<void (*)(unsigned, uint8_t, uint8_t)>(modern.symbol("test_rumble_command"));
    check(command != nullptr, "authored callback export is discoverable");
    if (!command) return 1;
    uint8_t small = 99, large = 99; uint64_t generation = 99;
    check(modern.rtag_rumble(-1, &small, &large, &generation) == 0 && small == 0 && large == 0 && generation == 0,
          "invalid C ABI read clears output");
    command(1, 255, 128);
    check(modern.rtag_rumble(1, &small, &large, &generation) == 1 && small == 255 && large == 128 && generation == 1,
          "raw unsigned bytes and64bit generation cross dynamic ABI");
    modern.rtag_stop();
    check(modern.rtag_rumble(1, &small, &large, &generation) == 1 && small == 0 && large == 0 && generation == 2,
          "dynamic ABI exposes neutral stop release");
    command(1, 255, 255);
    check(modern.rtag_rumble(1, &small, &large, &generation) == 1 && small == 0 && large == 0 && generation == 2,
          "late callback cannot restart stopped ABI state");
    std::printf("RESULT %d production optional-loader checks, %d failures; authored ABI stubs, no game or physical vibration proof\n", checks, failures);
    return failures ? 1 : 0;
}
