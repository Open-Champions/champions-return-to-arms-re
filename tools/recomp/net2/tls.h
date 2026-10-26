// tls.h - the TCP link to the rendezvous service inside TLS, with the operating system's
// own TLS: Network.framework (and the Security framework's trust evaluation) on macOS,
// SChannel on Windows.  No OpenSSL, nothing to install, nothing compiled in.
//
// What is checked: the service's certificate chain against the system's trust store (or,
// for tests and a self-hosted service, against the certificates of one named file ONLY),
// and that the certificate is valid for the host name the player gave.  TLS 1.2 or newer.
//
// When TLS is used (session_net.cpp; docs/issues/native-rendezvous-tls.md):
//   rule AUTO (the default)  plain text for this computer (127.x, "localhost") and for an
//                            address of a home network written as numbers (10.x, 172.16-31.x,
//                            192.168.x, 100.64-127.x, 169.254.x): tests and a LAN party;
//                            TLS for everything else - every host name, every public address
//   ON / OFF                 always / never: "tls://host:port" / "plain://host:port" as the
//                            service's address, the environment variable RTA_NET2_TLS=on|off|auto,
//                            or net2_set(n, "tls", "on"|"off"|"auto")
// A certificate is issued for a NAME: a service on the Internet is named by its host name
// ("play.example.org:41900"), not by its address.
//
// The datagrams (carrier.h) are not inside TLS; the docs say what they carry.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace n2 {

enum { TLS_AUTO = 0, TLS_ON = 1, TLS_OFF = 2 };

// Whether a service written as `host` (a name, or an address a.b.c.d) is reached inside TLS
// under `rule`.
bool tls_wanted(int rule, const std::string& host);
// "auto", "on", "off" (also 1/0, yes/no, true/false, tls/plain) -> TLS_*; -1 for anything else
int tls_rule(const std::string& text);
const char* tls_rule_text(int rule);
// The certificates of a file: PEM (any number of "BEGIN CERTIFICATE" blocks) or one DER
// certificate.  false and a reason in words when there is none.
bool tls_certificates(const std::string& path, std::vector<std::string>& der, std::string& problem);
std::string base_name(const std::string& path);            // the last part of a path

struct TlsLink {
    enum { FAILED = -1, UNDER_WAY = 0, READY = 1 };     // state()
    enum { AGAIN = -1, LOST = -2 };                     // send(), recv(): as sock.h's
    virtual ~TlsLink() {}
    // Opens the TCP connection to ip:port (host byte order) and makes the handshake; the
    // certificate must be valid for `name`.  `trust`: "" = the system's trust store; else a
    // file of certificates that are the only ones trusted (tests, a self-hosted service).
    virtual void start(uint32_t ip, uint16_t port, const std::string& name, const std::string& trust) = 0;
    virtual int state() = 0;                            // never blocks
    virtual int send(const char* data, size_t size) = 0;    // bytes taken (perhaps fewer), AGAIN or LOST
    virtual int recv(char* into, size_t size) = 0;      // bytes; 0 = closed by the other end; AGAIN or LOST
    virtual std::string problem() = 0;                  // why it failed or broke, in words
    virtual std::string summary() = 0;                  // what was agreed, in words ("TLS 1.3, ...")
};
// A new link (never null).  On a system this file has no TLS for, its start fails and says so.
TlsLink* tls_link();

// The same interface without TLS: a plain TCP connection (a WebSocket on a LAN or in tests).
TlsLink* plain_link();
// The conversation as a WebSocket (RFC 6455) over `under` (a tls_link() for wss://, a
// plain_link() for ws://): the fallback for networks that let HTTPS out but break TLS to an
// unknown port (docs/issues/native-rendezvous.md, "The fallback").  start() opens `under`
// to the web server's ip:port (TLS checked for `name` as ever), then asks for the upgrade of
// `path` with Host: `name`; READY once the server said 101.  The bytes of send() and recv()
// are the conversation's own, carried in binary frames (masked, as a client's must be).
TlsLink* ws_link(TlsLink* under, const std::string& path);

}  // namespace n2
