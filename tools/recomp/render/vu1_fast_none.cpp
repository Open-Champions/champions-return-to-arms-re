// vu1_fast_none.cpp - linked when there is no ahead-of-time translation of the VU1
// microprograms (vu1_fast.h; vu1_translate.py writes one into local/recomp-out/gen-vu/):
// everything goes to the older translation of the main program or to the interpreter.
#include "vu1_fast.h"

namespace render {

extern const Vu1Program vu1_fast_programs[] = {{0, 0, 0, nullptr}};
extern const uint32_t vu1_fast_program_count = 0;

}  // namespace render
