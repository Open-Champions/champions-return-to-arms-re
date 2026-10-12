// iso9660.h - the disc: an ISO 9660 image read in place.
//
// The game asks the drive for two things: where a path is (sector and size - it asks for
// directories as well as files, and then walks the directory sectors itself) and raw
// 2048-byte sectors.  Nothing else of the file system is needed.
#pragma once
#include "host.h"

#include <cctype>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

class Iso9660 {
public:
    static const uint32_t SECTOR = 2048;

    bool open(const char* path) {
        file_ = host::big_open(path);
        if (!file_) return false;
        uint8_t pvd[SECTOR];
        if (!read(16, 1, pvd) || memcmp(pvd + 1, "CD001", 5) != 0) return false;
        root_ = record(pvd + 156);
        return true;
    }
    bool is_open() const { return file_ != nullptr; }
    uint64_t sectors() const { return file_ ? host::big_size(file_) / SECTOR : 0; }

    // Sectors past the end of the image read as zeroes (a drive would report an error;
    // the game never asks).
    bool read(uint32_t sector, uint32_t count, uint8_t* into) {
        if (!file_) return false;
        uint64_t total = sectors();
        if ((uint64_t)sector + count > total) {
            memset(into, 0, (size_t)count * SECTOR);
            if (sector >= total) return false;
            count = (uint32_t)(total - sector);
        }
        return host::big_read(file_, (uint64_t)sector * SECTOR, into, (size_t)count * SECTOR);
    }

    struct Entry { uint32_t sector = 0, size = 0; bool directory = false; std::string name; };

    // "\BG\DATA\X.LMP;1", "/bg/data", with or without the version suffix; case is ignored.
    bool find(const char* path, Entry* out) {
        Entry at = root_;
        std::string part;
        for (const char* p = path;; p++) {
            if (*p == '\\' || *p == '/' || *p == 0) {
                if (!part.empty()) {
                    if (!at.directory || !lookup(at, part, &at)) return false;
                    part.clear();
                }
                if (*p == 0) break;
            } else part += *p;
        }
        *out = at;
        return true;
    }

    std::vector<Entry> list(const Entry& directory) {
        std::vector<Entry> result;
        uint32_t count = (directory.size + SECTOR - 1) / SECTOR;
        std::vector<uint8_t> data((size_t)count * SECTOR);
        if (!count || !read(directory.sector, count, data.data())) return result;
        for (size_t at = 0; at < data.size();) {
            uint8_t length = data[at];
            if (length == 0) { at = (at / SECTOR + 1) * SECTOR; continue; }     // records do not cross sectors
            Entry e = record(data.data() + at);
            at += length;
            if (e.name.size() == 1 && (e.name[0] == 0 || e.name[0] == 1)) continue;     // "." and ".."
            result.push_back(e);
        }
        return result;
    }

private:
    static Entry record(const uint8_t* raw) {
        Entry e;
        memcpy(&e.sector, raw + 2, 4);
        memcpy(&e.size, raw + 10, 4);
        e.directory = (raw[25] & 2) != 0;
        e.name.assign((const char*)raw + 33, raw[32]);
        return e;
    }
    static std::string plain(const std::string& name) {      // upper case, no ";1"
        std::string s;
        for (char ch : name) {
            if (ch == ';') break;
            s += (char)toupper((unsigned char)ch);
        }
        return s;
    }
    bool lookup(const Entry& directory, const std::string& name, Entry* out) {
        std::string want = plain(name);
        for (const Entry& e : list(directory))
            if (plain(e.name) == want) { *out = e; return true; }
        return false;
    }

    host::BigFile* file_ = nullptr;
    Entry root_;
};
