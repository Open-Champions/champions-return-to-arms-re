// vu1_none.cpp - linked when there is no translation of the VU1 main program (see
// Vu1::write_translation): everything is interpreted.
#include "vu1.h"

namespace render {

extern const uint64_t vu1_translated_hash = 0;
extern const uint32_t vu1_translated_count = 0;
int vu1_translated_run(Vu1&, uint32_t at, int) { return (int)at; }

}  // namespace render
