// sound_none_web.cpp - what the page asks of the sound side when the program was built
// without it (build.py page --no-sound): there is no ring to play from.
extern "C" __attribute__((used)) void* rta_web_sound_ring() { return nullptr; }
