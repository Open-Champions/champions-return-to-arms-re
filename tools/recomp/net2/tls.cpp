// tls.cpp - tls.h's link with the operating system's TLS: Network.framework on macOS,
// SChannel on Windows, none elsewhere (a start there fails and says why).
//
// macOS: the connection is Network.framework's own (TCP and TLS 1.2+ on a serial dispatch
// queue of this link); what arrives is kept in a buffer the polling thread takes from; the
// certificate is evaluated by the Security framework with an SSL policy for the given name,
// against the system's trust store or against the anchors of one file only.  Link with
// -framework Network -framework Security (and CoreFoundation, which they bring).
//
// Windows: SChannel over a non-blocking socket of net/sock.h's Winsock body, driven from
// the polling thread; TLS 1.2; the system's validation of chain and name, or - with a file
// of anchors - a chain engine whose only root store is that file and the SSL policy for the
// name.  Link with -lsecur32 -lcrypt32 (and ws2_32).  Written and compiled on a Mac with a
// cross-compiler, NOT RUN (docs/issues/native-rendezvous-tls.md).
#include "tls.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <memory>

namespace n2 {

// ---- what every body shares ------------------------------------------------------------
int tls_rule(const std::string& text) {
    std::string t;
    for (char c : text) t += (char)((c >= 'A' && c <= 'Z') ? c - 'A' + 'a' : c);
    if (t == "auto" || t.empty()) return TLS_AUTO;
    if (t == "on" || t == "1" || t == "yes" || t == "true" || t == "tls") return TLS_ON;
    if (t == "off" || t == "0" || t == "no" || t == "false" || t == "plain") return TLS_OFF;
    return -1;
}
const char* tls_rule_text(int rule) { return rule == TLS_ON ? "on" : rule == TLS_OFF ? "off" : "auto"; }

bool tls_wanted(int rule, const std::string& host) {
    if (rule == TLS_ON) return true;
    if (rule == TLS_OFF) return false;
    if (host == "localhost") return false;
    unsigned a, b, c, d;
    char tail;
    if (sscanf(host.c_str(), "%u.%u.%u.%u%c", &a, &b, &c, &d, &tail) != 4) return true;   // a name: what a certificate is for
    unsigned o1 = a, o2 = b;
    if (o1 == 127 || o1 == 10) return false;
    if (o1 == 172 && o2 >= 16 && o2 <= 31) return false;
    if (o1 == 192 && o2 == 168) return false;
    if (o1 == 169 && o2 == 254) return false;
    if (o1 == 100 && o2 >= 64 && o2 <= 127) return false;
    return true;
}

std::string base_name(const std::string& path) {
    size_t cut = path.find_last_of("/\\");
    return cut == std::string::npos ? path : path.substr(cut + 1);
}

static int base64_value(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

bool tls_certificates(const std::string& path, std::vector<std::string>& der, std::string& problem) {
    der.clear();
    std::ifstream file(path, std::ios::binary);
    if (!file) { problem = "The file of trusted certificates cannot be read: " + path; return false; }
    std::string text((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    const std::string begin = "-----BEGIN CERTIFICATE-----", end = "-----END CERTIFICATE-----";
    size_t at = 0;
    while ((at = text.find(begin, at)) != std::string::npos) {
        size_t stop = text.find(end, at);
        if (stop == std::string::npos) break;
        std::string out;
        unsigned bits = 0;
        int have = 0;
        for (size_t i = at + begin.size(); i < stop; i++) {
            int v = base64_value(text[i]);
            if (v < 0) continue;            // line ends, blanks, '='
            bits = (bits << 6) | (unsigned)v;
            have += 6;
            if (have >= 8) { have -= 8; out += (char)((bits >> have) & 0xFF); }
        }
        if (!out.empty()) der.push_back(out);
        at = stop + end.size();
    }
    if (der.empty() && text.size() > 4 && (unsigned char)text[0] == 0x30) der.push_back(text);     // one DER certificate
    if (der.empty()) { problem = "No certificate in the file of trusted certificates: " + path; return false; }
    return true;
}

}  // namespace n2

#if defined(__APPLE__)
// ============================== macOS: Network.framework ======================================
#include <CoreFoundation/CoreFoundation.h>
#include <Network/Network.h>
#include <Security/Security.h>
#include <dispatch/dispatch.h>

#include <mutex>

namespace n2 {
namespace {

std::string cf_text(CFStringRef s) {
    if (!s) return "";
    char buffer[512] = "";
    if (!CFStringGetCString(s, buffer, sizeof buffer, kCFStringEncodingUTF8)) return "";
    return buffer;
}

std::string status_text(OSStatus status) {
    CFStringRef s = SecCopyErrorMessageString(status, nullptr);
    std::string text = cf_text(s);
    if (s) CFRelease(s);
    return (text.empty() ? std::string("error") : text) + " (" + std::to_string((int)status) + ")";
}

std::string nw_text(nw_error_t error) {
    if (!error) return "";
    int code = nw_error_get_error_code(error);
    switch (nw_error_get_error_domain(error)) {
    case nw_error_domain_posix: return std::string(strerror(code));
    case nw_error_domain_dns: return "the name was not answered (" + std::to_string(code) + ")";
    case nw_error_domain_tls: return status_text((OSStatus)code);
    default: return "error " + std::to_string(code);
    }
}

const char* version_text(tls_protocol_version_t v) {
    switch (v) {
    case tls_protocol_version_TLSv13: return "TLS 1.3";
    case tls_protocol_version_TLSv12: return "TLS 1.2";
    default: return "TLS (an older version)";
    }
}

// What the dispatch queue and the polling thread share; the blocks hold it as long as they live.
struct Shared {
    std::mutex m;
    std::string in;                 // received, not yet taken
    size_t flight = 0;              // handed to the connection, not yet sent
    int state = TlsLink::UNDER_WAY;
    bool lost = false, eof = false, closing = false;
    bool paused = false;            // receiving stopped: what arrived was not taken (it goes on once it is)
    std::string problem, summary;
    CFArrayRef anchors = nullptr;   // the only trusted certificates, or none: the system's store
    std::string trust_label;
    ~Shared() { if (anchors) CFRelease(anchors); }
};

void receive_more(nw_connection_t c, std::shared_ptr<Shared> sh) {
    nw_retain(c);
    nw_connection_receive(c, 1, 65536, ^(dispatch_data_t content, nw_content_context_t context, bool is_complete, nw_error_t error) {
        (void)context;
        bool again;
        {
            std::lock_guard<std::mutex> hold(sh->m);
            if (content)
                dispatch_data_apply(content, ^bool(dispatch_data_t region, size_t offset, const void* buffer, size_t size) {
                    (void)region; (void)offset;
                    sh->in.append((const char*)buffer, size);
                    return true;
                });
            if (is_complete) sh->eof = true;                  // a stream: the other end has closed
            else if (error && !sh->closing && !sh->lost) {
                sh->lost = true;
                if (sh->problem.empty()) sh->problem = "The secure link broke: " + nw_text(error);
            }
            again = !error && !is_complete && !sh->closing;
            if (again && sh->in.size() >= (4u << 20)) { again = false; sh->paused = true; }
        }
        if (again) receive_more(c, sh);
        nw_release(c);
    });
}

struct AppleTls : TlsLink {
    std::shared_ptr<Shared> sh = std::make_shared<Shared>();
    nw_connection_t conn = nullptr;         // this object's own reference (the creation one ends with "cancelled")
    dispatch_queue_t queue = nullptr;

    void fail(const std::string& why) {
        std::lock_guard<std::mutex> hold(sh->m);
        sh->state = FAILED;
        if (sh->problem.empty()) sh->problem = why;
    }

    void start(uint32_t ip, uint16_t port, const std::string& name, const std::string& trust) override {
        if (!trust.empty()) {
            std::vector<std::string> der;
            std::string problem;
            if (!tls_certificates(trust, der, problem)) { fail(problem); return; }
            CFMutableArrayRef list = CFArrayCreateMutable(nullptr, 0, &kCFTypeArrayCallBacks);
            for (const std::string& d : der) {
                CFDataRef data = CFDataCreate(nullptr, (const UInt8*)d.data(), (CFIndex)d.size());
                SecCertificateRef cert = data ? SecCertificateCreateWithData(nullptr, data) : nullptr;
                if (data) CFRelease(data);
                if (!cert) { CFRelease(list); fail("Something that is not a certificate in the file of trusted certificates: " + trust); return; }
                CFArrayAppendValue(list, cert);
                CFRelease(cert);
            }
            sh->anchors = list;
            sh->trust_label = "only " + base_name(trust);
        } else sh->trust_label = "the system's store";
        queue = dispatch_queue_create("rta-net2 tls", DISPATCH_QUEUE_SERIAL);
        char host[16], service[8];
        snprintf(host, sizeof host, "%u.%u.%u.%u", ip >> 24, (ip >> 16) & 255, (ip >> 8) & 255, ip & 255);
        snprintf(service, sizeof service, "%u", (unsigned)port);
        nw_endpoint_t endpoint = nw_endpoint_create_host(host, service);
        std::shared_ptr<Shared> shared = sh;
        std::string server_name = name;
        dispatch_queue_t q = queue;
        nw_parameters_configure_protocol_block_t configure_tls = ^(nw_protocol_options_t options) {
            sec_protocol_options_t sec = nw_tls_copy_sec_protocol_options(options);
            sec_protocol_options_set_tls_server_name(sec, server_name.c_str());
            sec_protocol_options_set_min_tls_protocol_version(sec, tls_protocol_version_TLSv12);
            sec_protocol_options_set_verify_block(sec, ^(sec_protocol_metadata_t metadata, sec_trust_t trust_ref, sec_protocol_verify_complete_t complete) {
                (void)metadata;
                SecTrustRef trust_object = sec_trust_copy_ref(trust_ref);
                CFStringRef cf_name = CFStringCreateWithCString(nullptr, server_name.c_str(), kCFStringEncodingUTF8);
                SecPolicyRef policy = SecPolicyCreateSSL(true, cf_name);        // a server's certificate, for this name
                SecTrustSetPolicies(trust_object, policy);
                if (shared->anchors) {
                    SecTrustSetAnchorCertificates(trust_object, shared->anchors);
                    SecTrustSetAnchorCertificatesOnly(trust_object, true);
                }
                CFErrorRef error = nullptr;
                bool ok = SecTrustEvaluateWithError(trust_object, &error);
                if (!ok) {
                    CFStringRef d = error ? CFErrorCopyDescription(error) : nullptr;
                    std::lock_guard<std::mutex> hold(shared->m);
                    shared->problem = "The service's certificate is not accepted for " + server_name + ": " + (d ? cf_text(d) : std::string("no reason given")) +
                                      " (trusted: " + shared->trust_label + ")";
                    if (d) CFRelease(d);
                }
                if (error) CFRelease(error);
                CFRelease(policy);
                CFRelease(cf_name);
                CFRelease(trust_object);
                complete(ok);
            }, q);
            sec_release(sec);
        };
        nw_parameters_configure_protocol_block_t configure_tcp = ^(nw_protocol_options_t options) {
            nw_tcp_options_set_no_delay(options, true);
            nw_tcp_options_set_connection_timeout(options, 10);
        };
        nw_parameters_t parameters = nw_parameters_create_secure_tcp(configure_tls, configure_tcp);
        nw_connection_t c = nw_connection_create(endpoint, parameters);
        nw_release(endpoint);
        nw_release(parameters);
        if (!c) { fail("No connection could be made (Network.framework)."); return; }
        conn = c;
        nw_retain(c);                       // this object's reference; the creation one is released at "cancelled"
        nw_connection_set_queue(c, queue);
        nw_connection_set_state_changed_handler(c, ^(nw_connection_state_t state, nw_error_t error) {
            if (state == nw_connection_state_ready) {
                std::string summary;
                nw_protocol_definition_t definition = nw_protocol_copy_tls_definition();
                nw_protocol_metadata_t metadata = nw_connection_copy_protocol_metadata(c, definition);
                nw_release(definition);
                if (metadata) {
                    sec_protocol_metadata_t sec = nw_tls_copy_sec_protocol_metadata(metadata);
                    if (sec) {
                        summary = version_text(sec_protocol_metadata_get_negotiated_tls_protocol_version(sec));
                        sec_release(sec);
                    }
                    nw_release(metadata);
                }
                bool go;
                {
                    std::lock_guard<std::mutex> hold(shared->m);
                    shared->state = READY;
                    shared->summary = (summary.empty() ? std::string("TLS") : summary) + ", certificate for " + server_name + " checked (trusted: " +
                                      shared->trust_label + ")";
                    go = !shared->closing;
                }
                if (go) receive_more(c, shared);
            } else if (state == nw_connection_state_waiting || state == nw_connection_state_failed) {
                // "waiting" would try again by itself when the network changes; the session
                // decides itself when to try again
                {
                    std::lock_guard<std::mutex> hold(shared->m);
                    std::string why = nw_text(error);
                    if (shared->state == UNDER_WAY) {
                        shared->state = FAILED;
                        if (shared->problem.empty()) shared->problem = why.empty() ? std::string("no answer") : why;
                    } else if (!shared->closing && !shared->lost && !shared->eof) {
                        shared->lost = true;
                        if (shared->problem.empty()) shared->problem = "The secure link broke: " + why;
                    }
                }
                nw_connection_cancel(c);
            } else if (state == nw_connection_state_cancelled) {
                {
                    std::lock_guard<std::mutex> hold(shared->m);
                    if (shared->state == UNDER_WAY) { shared->state = FAILED; if (shared->problem.empty()) shared->problem = "cancelled"; }
                }
                nw_release(c);              // the reference taken at creation
            }
        });
        nw_connection_start(c);
    }

    int state() override {
        std::lock_guard<std::mutex> hold(sh->m);
        return sh->state;
    }

    int send(const char* data, size_t size) override {
        {
            std::lock_guard<std::mutex> hold(sh->m);
            if (sh->state == FAILED || sh->lost || sh->eof) return LOST;
            if (sh->state != READY || sh->flight > 256 * 1024) return AGAIN;
            sh->flight += size;
        }
        dispatch_data_t d = dispatch_data_create(data, size, nullptr, DISPATCH_DATA_DESTRUCTOR_DEFAULT);     // a copy
        std::shared_ptr<Shared> shared = sh;
        nw_connection_send(conn, d, NW_CONNECTION_DEFAULT_MESSAGE_CONTEXT, true, ^(nw_error_t error) {
            std::lock_guard<std::mutex> hold(shared->m);
            shared->flight -= size;
            if (error && !shared->closing && !shared->lost) {
                shared->lost = true;
                if (shared->problem.empty()) shared->problem = "The secure link broke while sending: " + nw_text(error);
            }
        });
        dispatch_release(d);
        return (int)size;
    }

    int recv(char* into, size_t size) override {
        bool resume = false;
        int r;
        {
            std::lock_guard<std::mutex> hold(sh->m);
            if (!sh->in.empty()) {
                size_t n = std::min(size, sh->in.size());
                memcpy(into, sh->in.data(), n);
                sh->in.erase(0, n);
                r = (int)n;
                if (sh->paused && sh->in.size() < (1u << 20)) { sh->paused = false; resume = true; }
            } else r = sh->eof ? 0 : (sh->state == FAILED || sh->lost) ? LOST : AGAIN;
        }
        if (resume) receive_more(conn, sh);
        return r;
    }

    std::string problem() override { std::lock_guard<std::mutex> hold(sh->m); return sh->problem; }
    std::string summary() override { std::lock_guard<std::mutex> hold(sh->m); return sh->summary; }

    ~AppleTls() override {
        if (conn) {
            bool orderly;
            {
                std::lock_guard<std::mutex> hold(sh->m);
                orderly = sh->state == READY && !sh->lost && !sh->eof;
                sh->closing = true;
            }
            nw_connection_t c = conn;
            if (orderly) {
                // what was handed over still goes, then the end of the stream; a link that does
                // not get there in two seconds is cut
                nw_retain(c);
                nw_connection_send(c, nullptr, NW_CONNECTION_FINAL_MESSAGE_CONTEXT, true, ^(nw_error_t error) {
                    (void)error;
                    nw_connection_cancel(c);
                    nw_release(c);
                });
                nw_retain(c);
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), queue, ^{
                    nw_connection_cancel(c);
                    nw_release(c);
                });
            } else nw_connection_cancel(c);
            nw_release(c);
        }
        if (queue) dispatch_release(queue);
    }
};

}  // namespace

TlsLink* tls_link() { return new AppleTls(); }

}  // namespace n2

#elif defined(_WIN32)
// ============================== Windows: SChannel ==============================================
#include "../net/sock.h"

#ifndef SECURITY_WIN32
#define SECURITY_WIN32
#endif
#include <security.h>
#include <schannel.h>
#include <sspi.h>
#include <wincrypt.h>

#include <algorithm>

namespace n2 {
namespace {

std::string status_text(SECURITY_STATUS status) {
    char text[256] = "";
    DWORD n = FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, (DWORD)status, 0, text, sizeof text, nullptr);
    while (n > 0 && (text[n - 1] == '\r' || text[n - 1] == '\n' || text[n - 1] == ' ' || text[n - 1] == '.')) text[--n] = 0;
    char code[24];
    snprintf(code, sizeof code, "0x%08lx", (unsigned long)status);
    return (n ? std::string(text) + " " : std::string()) + "(" + code + ")";
}

struct WinTls : TlsLink {
    sock::Handle fd = sock::NONE;
    CredHandle cred;
    CtxtHandle ctx;
    bool have_cred = false, have_ctx = false, connecting = false, open = false, lost = false, eof = false;
    int st = UNDER_WAY;
    HCERTSTORE anchors = nullptr;
    std::string name, trust_label, problem_, summary_;
    std::string in, out, plain;     // ciphertext received / to send, plaintext not yet taken
    SecPkgContext_StreamSizes sizes;
    static const DWORD REQUEST = ISC_REQ_SEQUENCE_DETECT | ISC_REQ_REPLAY_DETECT | ISC_REQ_CONFIDENTIALITY | ISC_REQ_EXTENDED_ERROR |
                                 ISC_REQ_ALLOCATE_MEMORY | ISC_REQ_STREAM;

    WinTls() { memset(&cred, 0, sizeof cred); memset(&ctx, 0, sizeof ctx); memset(&sizes, 0, sizeof sizes); }

    void fail(const std::string& why) {
        if (st == UNDER_WAY) { st = FAILED; if (problem_.empty()) problem_ = why; }
        else if (!lost) { lost = true; if (problem_.empty()) problem_ = why; }
    }

    void start(uint32_t ip, uint16_t port, const std::string& host, const std::string& trust) override {
        name = host;
        if (!trust.empty()) {
            std::vector<std::string> der;
            std::string problem;
            if (!tls_certificates(trust, der, problem)) { fail(problem); return; }
            anchors = CertOpenStore(CERT_STORE_PROV_MEMORY, 0, 0, 0, nullptr);
            for (const std::string& d : der)
                if (!anchors || !CertAddEncodedCertificateToStore(anchors, X509_ASN_ENCODING, (const BYTE*)d.data(), (DWORD)d.size(), CERT_STORE_ADD_ALWAYS, nullptr)) {
                    fail("Something that is not a certificate in the file of trusted certificates: " + trust);
                    return;
                }
            trust_label = "only " + base_name(trust);
        } else trust_label = "the system's store";
        SCHANNEL_CRED sc;
        memset(&sc, 0, sizeof sc);
        sc.dwVersion = SCHANNEL_CRED_VERSION;
        sc.grbitEnabledProtocols = SP_PROT_TLS1_2_CLIENT;
        // the system checks chain and name by itself, unless the anchors are our own file
        sc.dwFlags = SCH_CRED_NO_DEFAULT_CREDS | SCH_USE_STRONG_CRYPTO | (anchors ? SCH_CRED_MANUAL_CRED_VALIDATION : SCH_CRED_AUTO_CRED_VALIDATION);
        SECURITY_STATUS s = AcquireCredentialsHandleA(nullptr, (LPSTR)UNISP_NAME_A, SECPKG_CRED_OUTBOUND, nullptr, &sc, nullptr, nullptr, &cred, nullptr);
        if (s != SEC_E_OK) { fail("SChannel refused to start: " + status_text(s)); return; }
        have_cred = true;
        fd = sock::tcp();
        if (fd == sock::NONE) { fail("No socket: " + sock::error_text(sock::error())); return; }
        int r = sock::connect(fd, ip, port);
        if (r == sock::FAILED) { fail("cannot be reached: " + sock::error_text(sock::error())); return; }
        connecting = true;
        if (r == sock::CONNECTED) { connecting = false; handshake(); }
    }

    void send_out() {
        while (fd != sock::NONE && !out.empty()) {
            int n = sock::send(fd, out.data(), out.size());
            if (n == sock::LOST) { fail("The secure link broke: " + sock::error_text(sock::error())); return; }
            if (n <= 0) return;
            out.erase(0, (size_t)n);
        }
    }

    void read_in() {
        char buffer[16384];
        while (fd != sock::NONE && in.size() < (1u << 20)) {
            int n = sock::recv(fd, buffer, sizeof buffer);
            if (n == sock::AGAIN) return;
            if (n == 0) { eof = true; return; }
            if (n < 0) { fail("The secure link broke: " + sock::error_text(sock::error())); return; }
            in.append(buffer, (size_t)n);
        }
    }

    bool verify_own_anchors() {
        PCCERT_CONTEXT remote = nullptr;
        if (QueryContextAttributesA(&ctx, SECPKG_ATTR_REMOTE_CERT_CONTEXT, &remote) != SEC_E_OK || !remote) { fail("The service showed no certificate."); return false; }
        CERT_CHAIN_ENGINE_CONFIG config;
        memset(&config, 0, sizeof config);
        config.cbSize = sizeof config;
        config.hExclusiveRoot = anchors;            // Windows 8 or later
        HCERTCHAINENGINE engine = nullptr;
        bool ok = false;
        std::string why = "no chain to the trusted certificates could be built";
        if (CertCreateCertificateChainEngine(&config, &engine)) {
            LPSTR usage[] = {(LPSTR)szOID_PKIX_KP_SERVER_AUTH};
            CERT_CHAIN_PARA para;
            memset(&para, 0, sizeof para);
            para.cbSize = sizeof para;
            para.RequestedUsage.dwType = USAGE_MATCH_TYPE_AND;
            para.RequestedUsage.Usage.cUsageIdentifier = 1;
            para.RequestedUsage.Usage.rgpszUsageIdentifier = usage;
            PCCERT_CHAIN_CONTEXT chain = nullptr;
            if (CertGetCertificateChain(engine, remote, nullptr, remote->hCertStore, &para, 0, nullptr, &chain)) {
                std::wstring wide(name.begin(), name.end());        // a host name is ASCII
                HTTPSPolicyCallbackData https;
                memset(&https, 0, sizeof https);
                https.cbStruct = sizeof https;
                https.dwAuthType = AUTHTYPE_SERVER;
                https.pwszServerName = &wide[0];
                CERT_CHAIN_POLICY_PARA policy;
                memset(&policy, 0, sizeof policy);
                policy.cbSize = sizeof policy;
                policy.pvExtraPolicyPara = &https;
                CERT_CHAIN_POLICY_STATUS status;
                memset(&status, 0, sizeof status);
                status.cbSize = sizeof status;
                if (CertVerifyCertificateChainPolicy(CERT_CHAIN_POLICY_SSL, chain, &policy, &status)) {
                    ok = status.dwError == 0;
                    if (!ok) why = status_text((SECURITY_STATUS)status.dwError);
                }
                CertFreeCertificateChain(chain);
            }
            CertFreeCertificateChainEngine(engine);
        }
        CertFreeCertificateContext(remote);
        if (!ok) fail("The service's certificate is not accepted for " + name + ": " + why + " (trusted: " + trust_label + ")");
        return ok;
    }

    void handshake() {
        for (int rounds = 0; rounds < 8 && st == UNDER_WAY; rounds++) {
            if (have_ctx && in.empty()) return;             // waiting for the service's next flight
            SecBuffer inb[2], outb[1];
            inb[0].BufferType = SECBUFFER_TOKEN; inb[0].pvBuffer = in.empty() ? nullptr : &in[0]; inb[0].cbBuffer = (unsigned long)in.size();
            inb[1].BufferType = SECBUFFER_EMPTY; inb[1].pvBuffer = nullptr; inb[1].cbBuffer = 0;
            outb[0].BufferType = SECBUFFER_TOKEN; outb[0].pvBuffer = nullptr; outb[0].cbBuffer = 0;
            SecBufferDesc indesc = {SECBUFFER_VERSION, 2, inb}, outdesc = {SECBUFFER_VERSION, 1, outb};
            unsigned long flags = 0;
            bool first = !have_ctx;
            SECURITY_STATUS s = InitializeSecurityContextA(&cred, first ? nullptr : &ctx, (SEC_CHAR*)name.c_str(), REQUEST, 0, 0,
                                                          first ? nullptr : &indesc, 0, first ? &ctx : nullptr, &outdesc, &flags, nullptr);
            if (first && (s == SEC_I_CONTINUE_NEEDED || s == SEC_E_OK)) have_ctx = true;
            if (outb[0].pvBuffer) {
                if (outb[0].cbBuffer) out.append((const char*)outb[0].pvBuffer, outb[0].cbBuffer);
                FreeContextBuffer(outb[0].pvBuffer);
            }
            if (s == SEC_E_INCOMPLETE_MESSAGE) return;        // more of the service's flight is needed
            if (s == SEC_I_INCOMPLETE_CREDENTIALS) continue;   // a client certificate is not given: on without one
            if (!first) {
                if (inb[1].BufferType == SECBUFFER_EXTRA && inb[1].cbBuffer) in.erase(0, in.size() - inb[1].cbBuffer);
                else in.clear();
            }
            if (s == SEC_I_CONTINUE_NEEDED) { send_out(); continue; }
            if (s == SEC_E_OK) {
                if (anchors && !verify_own_anchors()) return;
                if (QueryContextAttributesA(&ctx, SECPKG_ATTR_STREAM_SIZES, &sizes) != SEC_E_OK) { fail("SChannel gave no record sizes."); return; }
                open = true;
                st = READY;
                summary_ = "TLS 1.2 (SChannel), certificate for " + name + " checked (trusted: " + trust_label + ")";
                decrypt();                                  // application data that came with the last flight
                return;
            }
            fail("No secure link: " + status_text(s));
            return;
        }
    }

    void decrypt() {
        while (open && !in.empty()) {
            SecBuffer b[4];
            b[0].BufferType = SECBUFFER_DATA; b[0].pvBuffer = &in[0]; b[0].cbBuffer = (unsigned long)in.size();
            for (int i = 1; i < 4; i++) { b[i].BufferType = SECBUFFER_EMPTY; b[i].pvBuffer = nullptr; b[i].cbBuffer = 0; }
            SecBufferDesc desc = {SECBUFFER_VERSION, 4, b};
            SECURITY_STATUS s = DecryptMessage(&ctx, &desc, 0, nullptr);
            if (s == SEC_E_INCOMPLETE_MESSAGE) return;
            if (s == SEC_I_CONTEXT_EXPIRED) { eof = true; in.clear(); return; }          // the service ended TLS
            if (s != SEC_E_OK && s != SEC_I_RENEGOTIATE) { fail("The secure link broke: " + status_text(s)); return; }
            std::string extra;
            for (int i = 1; i < 4; i++) {
                if (b[i].BufferType == SECBUFFER_DATA && b[i].cbBuffer) plain.append((const char*)b[i].pvBuffer, b[i].cbBuffer);
                if (b[i].BufferType == SECBUFFER_EXTRA && b[i].cbBuffer) extra.assign((const char*)b[i].pvBuffer, b[i].cbBuffer);
            }
            in = extra;
            if (s == SEC_I_RENEGOTIATE) { fail("The service asked to renegotiate TLS; that is not done here."); return; }
        }
    }

    void pump() {
        if (st == FAILED || lost || fd == sock::NONE) return;
        if (connecting) {
            int r = sock::connect_check(fd);
            if (r == sock::FAILED) { fail("cannot be reached: " + sock::error_text(sock::error())); return; }
            if (r != sock::CONNECTED) return;
            connecting = false;
            handshake();
        }
        send_out();
        read_in();
        if (!open) handshake();
        else decrypt();
        send_out();
        if (st == UNDER_WAY && eof) fail("The service closed the connection during the TLS handshake.");
    }

    int state() override { pump(); return st; }

    int send(const char* data, size_t size) override {
        pump();
        if (st == FAILED || lost) return LOST;
        if (!open || out.size() > 256 * 1024) return AGAIN;
        size_t take = std::min<size_t>(size, sizes.cbMaximumMessage);
        std::string record(sizes.cbHeader + take + sizes.cbTrailer, '\0');
        memcpy(&record[sizes.cbHeader], data, take);
        SecBuffer b[4];
        b[0].BufferType = SECBUFFER_STREAM_HEADER; b[0].pvBuffer = &record[0]; b[0].cbBuffer = sizes.cbHeader;
        b[1].BufferType = SECBUFFER_DATA; b[1].pvBuffer = &record[sizes.cbHeader]; b[1].cbBuffer = (unsigned long)take;
        b[2].BufferType = SECBUFFER_STREAM_TRAILER; b[2].pvBuffer = &record[sizes.cbHeader + take]; b[2].cbBuffer = sizes.cbTrailer;
        b[3].BufferType = SECBUFFER_EMPTY; b[3].pvBuffer = nullptr; b[3].cbBuffer = 0;
        SecBufferDesc desc = {SECBUFFER_VERSION, 4, b};
        SECURITY_STATUS s = EncryptMessage(&ctx, 0, &desc, 0);
        if (s != SEC_E_OK) { fail("The secure link broke: " + status_text(s)); return LOST; }
        out.append(record.data(), (size_t)b[0].cbBuffer + b[1].cbBuffer + b[2].cbBuffer);
        send_out();
        return (int)take;
    }

    int recv(char* into, size_t size) override {
        pump();
        if (!plain.empty()) {
            size_t n = std::min(size, plain.size());
            memcpy(into, plain.data(), n);
            plain.erase(0, n);
            return (int)n;
        }
        if (eof && open) return 0;
        if (st == FAILED || lost || eof) return LOST;
        return AGAIN;
    }

    std::string problem() override { return problem_; }
    std::string summary() override { return summary_; }

    ~WinTls() override {
        if (have_ctx) DeleteSecurityContext(&ctx);
        if (have_cred) FreeCredentialsHandle(&cred);
        if (anchors) CertCloseStore(anchors, 0);
        if (fd != sock::NONE) sock::close(fd);
    }
};

}  // namespace

TlsLink* tls_link() { return new WinTls(); }

}  // namespace n2

#else
// ============================== elsewhere: none ================================================
namespace n2 {
namespace {
struct NoTls : TlsLink {
    std::string why = "This program has no TLS for this system: a service can only be reached in plain text here (plain://host:port).";
    void start(uint32_t, uint16_t, const std::string&, const std::string&) override {}
    int state() override { return FAILED; }
    int send(const char*, size_t) override { return LOST; }
    int recv(char*, size_t) override { return LOST; }
    std::string problem() override { return why; }
    std::string summary() override { return ""; }
};
}  // namespace
TlsLink* tls_link() { return new NoTls(); }
}  // namespace n2
#endif
