// cardchars.cpp - "the characters I have": the characters in the saved games of a memory
// card directory, read straight from the files.  No game is needed and nothing is written.
//
// A card directory is what the native program keeps as <data>/card and the emulator-based
// application as <data>/vfs: it holds mc0/ and mc1/, and a card holds the game's folder
// BASLUS-20973 with one file per save slot, BASLUS-20973_slot<n>.  Such a file is the
// game's save buffer in one piece (docs/audio-save.md, "Save format"):
//
//   +0x68  u16   size of a player record: 0x4c30 (checked: anything else is not read)
//   +0x6a  u16   players in the file (1..4)
//   +0x320       player blocks, 0x4c3e bytes each; the record starts at +0x0e of a block
//   record +0x00 char[0x20] the character's name;  +0x50 s32 class 0..6;  +0x59 s8 level
//
// Class words are the ones docs/data-tables.md 4.1 lists in class order.  A save made in
// a net game holds only the local player (one block).
#include "session_impl.h"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <set>

namespace net2impl {

const char* const CLASS_WORDS[7] = {"Barbarian", "Cleric", "Shadowknight", "Ranger", "Wizard", "Berserker", "Shaman"};

namespace {
const size_t RECORD = 0x4c30, BLOCK = 0x4c3e, BLOCKS_AT = 0x320, RECORD_IN_BLOCK = 0x0e;

void read_file(const std::filesystem::path& path, std::vector<net2_character>& out, std::set<std::string>& seen) {
    std::ifstream file(path, std::ios::binary);
    unsigned char head[0x70];
    if (!file.read((char*)head, sizeof head)) return;
    unsigned record_size = head[0x68] | (head[0x69] << 8), players = head[0x6a] | (head[0x6b] << 8);
    if (record_size != RECORD || players < 1 || players > 4) return;
    for (unsigned i = 0; i < players; i++) {
        unsigned char record[0x60];
        file.clear();
        file.seekg((std::streamoff)(BLOCKS_AT + i * BLOCK + RECORD_IN_BLOCK));
        if (!file.read((char*)record, sizeof record)) return;
        char name[0x21];
        memcpy(name, record, 0x20);
        name[0x20] = 0;
        std::string label = clean_label(name, 24);
        int cls = (int)(record[0x50] | (record[0x51] << 8) | (record[0x52] << 16) | ((unsigned)record[0x53] << 24));
        int level = (signed char)record[0x59];
        if (label.empty() || cls < 0 || cls > 6 || level < 1 || level > 99) continue;      // not a character: an unused block
        char key[64];
        snprintf(key, sizeof key, "%s/%d/%d", label.c_str(), cls, level);
        if (!seen.insert(key).second) continue;     // the same character in two slots: once
        net2_character c{};
        put(c.name, label);
        put(c.cls, CLASS_WORDS[cls]);
        c.level = level;
        out.push_back(c);
    }
}
}  // namespace

int card_characters(const char* card_dir, net2_character* out, int max) {
    if (!card_dir || !*card_dir || !out || max <= 0) return 0;
    std::vector<net2_character> found;
    std::set<std::string> seen;
    std::error_code ignored;
    for (const char* card : {"mc0", "mc1"}) {
        std::filesystem::path folder = std::filesystem::path(card_dir) / card / "BASLUS-20973";
        std::vector<std::filesystem::path> files;
        for (std::filesystem::directory_iterator it(folder, ignored), end; !ignored && it != end; it.increment(ignored)) {
            std::string name = it->path().filename().string();
            if (name.compare(0, 17, "BASLUS-20973_slot") == 0) files.push_back(it->path());
        }
        std::sort(files.begin(), files.end());
        for (const auto& path : files) read_file(path, found, seen);
    }
    int count = (int)std::min<size_t>(found.size(), (size_t)max);
    for (int i = 0; i < count; i++) out[i] = found[(size_t)i];
    return count;
}

}  // namespace net2impl
