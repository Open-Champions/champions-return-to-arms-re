// party8.h - the game's tables sized for four, moved at run time to where they have room for eight
// (docs/issues/native-8-players.md A.9).  Works only with a translation made with `recomp.py --reloc
// app/party8-ranges.txt` (app/build.py --party8): every access the translator could follow to one of those tables
// has g_reloc[k] added to its address.  This module moves the tables and sets the words; with them 0 the program is
// the game as it was.
//
// The new place: guest memory 0x30000-0x73FFF and 0x88000-0xDFFFF (the first megabyte, below the other modes' blocks
// at 0xE0000 and above the runtime's kernel at 0x30000; the game writes only 0x74000-0x77FFF and 0x82000-0x83FFF
// there: checked to be empty at every move), each table given room for eight players (twice its size).  Moving (and moving back) is done between two frames on the game's thread, while
// no level is loaded (the title screen or the front end): then no object holds a pointer into a table.
//
// `--opt party8=1` (or `=poison`): moved at the first vertical blank, for the whole run.
// Test aids: `app party8 on [poison] | off | info`; with `poison` the old places are filled with 0xA5 after the
// move, so that an access the translator missed reads nonsense instead of a stale copy.
#pragma once
#include <cstdint>
#include <string>

namespace party8 {

bool available();                       // the translation has the relocations
bool moved();                           // the tables are at their new place
// ask for a move (or a move back); done at the next blank() on the game's thread
void want(bool on, bool poison = false);
void blank(uint64_t number);            // once per vertical blank on the game's thread
std::string command(const std::string& text);   // "app party8 on [poison] | off | info"

}  // namespace party8
