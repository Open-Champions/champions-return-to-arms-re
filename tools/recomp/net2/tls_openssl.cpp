// tls_openssl.cpp - tls.h's link on Linux: the system's OpenSSL (libssl 3) over a non-blocking
// socket of net/sock.h's BSD body, driven from the polling thread as the Windows body is.
// Included by tls.cpp inside #elif defined(__linux__) && defined(RTA_OPENSSL); not compiled by
// itself.  Link with -lssl -lcrypto.
//
// What is checked, as on the other systems: TLS 1.2 or newer; the service's chain against
// the system's trust store (OpenSSL's default paths: /etc/ssl/certs on Debian and Ubuntu,
// the distribution's bundle elsewhere) or - with a file of anchors - against that file's
// certificates ONLY; and that the certificate is valid for the name the player gave
// (SSL_set1_host: the subject alternative names, wildcards by RFC 6125).  The name also goes
// out as SNI.
#include "../net/sock.h"

#include <openssl/err.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>

#include <algorithm>

namespace n2 {
namespace {

std::string ssl_errors() {
    std::string text;
    while (unsigned long e = ERR_get_error()) {
        char line[256];
        ERR_error_string_n(e, line, sizeof line);
        if (!text.empty()) text += "; ";
        text += line;
    }
    return text.empty() ? std::string("no reason given") : text;
}

struct OpenSslTls : TlsLink {
    sock::Handle fd = sock::NONE;
    SSL_CTX* ctx = nullptr;
    SSL* ssl = nullptr;
    bool connecting = false, open = false, lost = false, eof = false;
    int st = UNDER_WAY;
    std::string name, trust_label, problem_, summary_;

    void fail(const std::string& why) {
        if (st == UNDER_WAY) { st = FAILED; if (problem_.empty()) problem_ = why; }
        else if (!lost) { lost = true; if (problem_.empty()) problem_ = why; }
    }

    void start(uint32_t ip, uint16_t port, const std::string& host, const std::string& trust) override {
        name = host;
        ctx = SSL_CTX_new(TLS_client_method());
        if (!ctx) { fail("OpenSSL refused to start: " + ssl_errors()); return; }
        SSL_CTX_set_min_proto_version(ctx, TLS1_2_VERSION);
        SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, nullptr);
        if (!trust.empty()) {
            std::vector<std::string> der;
            std::string problem;
            if (!tls_certificates(trust, der, problem)) { fail(problem); return; }
            X509_STORE* store = X509_STORE_new();       // only these: the system's store is not loaded
            for (const std::string& d : der) {
                const unsigned char* p = (const unsigned char*)d.data();
                X509* cert = d2i_X509(nullptr, &p, (long)d.size());
                if (!cert || !X509_STORE_add_cert(store, cert)) {
                    if (cert) X509_free(cert);
                    X509_STORE_free(store);
                    fail("Something that is not a certificate in the file of trusted certificates: " + trust);
                    return;
                }
                X509_free(cert);
            }
            SSL_CTX_set_cert_store(ctx, store);
            trust_label = "only " + base_name(trust);
        } else {
            if (!SSL_CTX_set_default_verify_paths(ctx)) { fail("OpenSSL has no store of trusted certificates: " + ssl_errors()); return; }
            trust_label = "the system's store";
        }
        fd = sock::tcp();
        if (fd == sock::NONE) { fail("No socket: " + sock::error_text(sock::error())); return; }
        int r = sock::connect(fd, ip, port);
        if (r == sock::FAILED) { fail("cannot be reached: " + sock::error_text(sock::error())); return; }
        connecting = true;
        if (r == sock::CONNECTED) { connecting = false; begin(); }
    }

    void begin() {
        ssl = SSL_new(ctx);
        if (!ssl || !SSL_set_fd(ssl, fd)) { fail("OpenSSL refused the connection: " + ssl_errors()); return; }
        unsigned a, b, c, d;
        char tail;
        bool numbers = sscanf(name.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) == 4;
        if (!numbers) SSL_set_tlsext_host_name(ssl, name.c_str());
        if (numbers ? !X509_VERIFY_PARAM_set1_ip_asc(SSL_get0_param(ssl), name.c_str()) : !SSL_set1_host(ssl, name.c_str())) {
            fail("OpenSSL cannot check a certificate for " + name);
            return;
        }
        handshake();
    }

    void handshake() {
        ERR_clear_error();
        int r = SSL_connect(ssl);
        if (r == 1) {
            open = true;
            st = READY;
            summary_ = std::string(SSL_get_version(ssl)) + " (OpenSSL), " + SSL_get_cipher_name(ssl) + ", certificate for " + name +
                       " checked (trusted: " + trust_label + ")";
            return;
        }
        int e = SSL_get_error(ssl, r);
        if (e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) return;
        long verify = SSL_get_verify_result(ssl);
        if (verify != X509_V_OK)
            fail("The service's certificate is not accepted for " + name + ": " + X509_verify_cert_error_string(verify) + " (trusted: " + trust_label + ")");
        else if (e == SSL_ERROR_ZERO_RETURN || (e == SSL_ERROR_SYSCALL && ERR_peek_error() == 0))
            fail("The service closed the connection during the TLS handshake.");
        else fail("No secure link: " + ssl_errors());
    }

    void pump() {
        if (st == FAILED || lost || fd == sock::NONE) return;
        if (connecting) {
            int r = sock::connect_check(fd);
            if (r == sock::FAILED) { fail("cannot be reached: " + sock::error_text(sock::error())); return; }
            if (r != sock::CONNECTED) return;
            connecting = false;
            begin();
            return;
        }
        if (!open && ssl) handshake();
    }

    int state() override { pump(); return st; }

    int send(const char* data, size_t size) override {
        pump();
        if (st == FAILED || lost) return LOST;
        if (!open) return AGAIN;
        ERR_clear_error();
        int n = SSL_write(ssl, data, (int)std::min<size_t>(size, 1 << 20));
        if (n > 0) return n;
        int e = SSL_get_error(ssl, n);
        if (e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) return AGAIN;
        fail("The secure link broke: " + ssl_errors());
        return LOST;
    }

    int recv(char* into, size_t size) override {
        pump();
        if (st == FAILED || lost) return LOST;
        if (!open) return AGAIN;
        if (eof) return 0;
        ERR_clear_error();
        int n = SSL_read(ssl, into, (int)std::min<size_t>(size, 1 << 20));
        if (n > 0) return n;
        int e = SSL_get_error(ssl, n);
        if (e == SSL_ERROR_WANT_READ || e == SSL_ERROR_WANT_WRITE) return AGAIN;
        if (e == SSL_ERROR_ZERO_RETURN) { eof = true; return 0; }                    // the service ended TLS
        if (e == SSL_ERROR_SYSCALL && ERR_peek_error() == 0) { eof = true; return 0; }   // the connection closed without a close_notify
        fail("The secure link broke: " + ssl_errors());
        return LOST;
    }

    std::string problem() override { return problem_; }
    std::string summary() override { return summary_; }

    ~OpenSslTls() override {
        if (ssl) { if (open && !lost) SSL_shutdown(ssl); SSL_free(ssl); }
        if (ctx) SSL_CTX_free(ctx);
        if (fd != sock::NONE) sock::close(fd);
    }
};

}  // namespace

TlsLink* tls_link() { return new OpenSslTls(); }

}  // namespace n2
