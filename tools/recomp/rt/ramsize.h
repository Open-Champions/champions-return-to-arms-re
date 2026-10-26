// ramsize.h - the size of the game's main memory as this program has it: 32 MB, as on the console.  A program built
// for rooms of up to eight (app/build.py --party8) defines RAM_SIZE 0x04000000u for every file it compiles: a game of
// five to eight is told of the whole 64 MB (rt/moved.h g_party8_memtop), every other game still of 32 MB.  Every
// native reader masks a guest address with RAM_SIZE - 1, never with a 32 MB constant of its own.
#pragma once
#ifndef RAM_SIZE
#define RAM_SIZE 0x02000000u
#endif
