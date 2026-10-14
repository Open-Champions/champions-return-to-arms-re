// hash.h - SHA-256, HMAC-SHA256 and random bytes for the identity of session_net.cpp, taken
// from the operating system: nothing cryptographic is written here.
//
//   macOS    CommonCrypto (libSystem) and arc4random_buf
//   Windows  CNG (bcrypt.dll) - compiled, never run (docs/issues/native-rendezvous.md)
//
// Neither C++ nor Python has a public-key signature in its standard library, which is why
// the identity is a device secret proven by HMAC and not a key pair (session_net.cpp says
// what that means).
#pragma once
#include <cstddef>
#include <cstdint>

#if defined(__APPLE__)
#include <CommonCrypto/CommonDigest.h>
#include <CommonCrypto/CommonHMAC.h>
#include <cstdlib>

namespace n2 {
inline bool random_bytes(uint8_t* out, size_t size) { arc4random_buf(out, size); return true; }
inline void sha256(const uint8_t* data, size_t size, uint8_t out[32]) { CC_SHA256(data, (CC_LONG)size, out); }
inline void hmac_sha256(const uint8_t* key, size_t key_size, const uint8_t* data, size_t size, uint8_t out[32]) {
    CCHmac(kCCHmacAlgSHA256, key, key_size, data, size, out);
}
}  // namespace n2

#elif defined(_WIN32)
#include <windows.h>
#include <bcrypt.h>

namespace n2 {
inline bool random_bytes(uint8_t* out, size_t size) {
    return BCryptGenRandom(nullptr, out, (ULONG)size, BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0;
}
inline void cng_hash(bool hmac, const uint8_t* key, size_t key_size, const uint8_t* data, size_t size, uint8_t out[32]) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, hmac ? BCRYPT_ALG_HANDLE_HMAC_FLAG : 0) != 0) return;
    if (BCryptCreateHash(algorithm, &hash, nullptr, 0, hmac ? (PUCHAR)key : nullptr, hmac ? (ULONG)key_size : 0, 0) == 0) {
        BCryptHashData(hash, (PUCHAR)data, (ULONG)size, 0);
        BCryptFinishHash(hash, out, 32, 0);
        BCryptDestroyHash(hash);
    }
    BCryptCloseAlgorithmProvider(algorithm, 0);
}
inline void sha256(const uint8_t* data, size_t size, uint8_t out[32]) { cng_hash(false, nullptr, 0, data, size, out); }
inline void hmac_sha256(const uint8_t* key, size_t key_size, const uint8_t* data, size_t size, uint8_t out[32]) {
    cng_hash(true, key, key_size, data, size, out);
}
}  // namespace n2

#else
#error "net2/hash.h: name this platform's SHA-256, HMAC and random source here (do not write them by hand)"
#endif
