// hash_linux.h - net2/hash.h's three functions on Linux: the system's OpenSSL (libcrypto) for
// SHA-256 and HMAC, the kernel's getrandom() for random bytes.  Included by hash.h only.
#pragma once
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <sys/random.h>
#include <cerrno>

namespace n2 {
inline bool random_bytes(uint8_t* out, size_t size) {
    while (size > 0) {
        ssize_t n = getrandom(out, size, 0);
        if (n < 0) { if (errno == EINTR) continue; return false; }
        out += n;
        size -= (size_t)n;
    }
    return true;
}
inline void sha256(const uint8_t* data, size_t size, uint8_t out[32]) {
    unsigned int length = 32;
    EVP_Digest(data, size, out, &length, EVP_sha256(), nullptr);
}
inline void hmac_sha256(const uint8_t* key, size_t key_size, const uint8_t* data, size_t size, uint8_t out[32]) {
    unsigned int length = 32;
    HMAC(EVP_sha256(), key, (int)key_size, data, size, out, &length);
}
}  // namespace n2
