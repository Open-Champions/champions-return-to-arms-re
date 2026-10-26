STATUS: FIXED — local transport validation passed.

Scope: review-codex.md items 2, 6, 7, 8 and 9, plus the requested guest-map extents. All changes are local and uncommitted. No remote service was contacted and no server was modified. Tests used synthetic links or this machine's own sockets. Gameplay implementation, packet payload formats and guest-memory writes were not changed.

1. Finding 2: bounded server WebSocket output and control-frame rate.

   Changes: `tools/rendezvous/rendezvous.py:121-122,433` adds a per-connection control bucket (20 frames/second, burst 60). `:628-647` routes application output through `enqueue`, which checks the complete encoded byte count before appending. `:789-826` uses it for pongs and stops immediately on closure; `:828-869` also bounds the upgrade response while preserving its position before the greeting. The default pending-output ceiling remains 262,144 bytes.

   Proof: `tools/rendezvous/test_bounds.py:58-120` exercises 3,000 masked maximum-size pings with a blocked writer, exact-limit and overflow cases before login, a logged-in connection, draining-writer rate abuse, pong-only abuse, token refill, split frames, unchanged payloads, application output and upgrade ordering/overflow. The pre-change HEAD code retained 381,000 bytes without closing in the local baseline. The patched Python probes pass: overflow closes before exceeding the configured ceiling; normal responses retain their bytes and ordering.

2. Finding 6: UDP reachability expires and resets with the service connection.

   Changes: `tools/recomp/net2/carrier.h:82-83,117` replaces the lifetime boolean with a timestamp and an eight-second freshness test. `carrier.cpp:85,172,207` resets it on close/service-endpoint change, records the expected service before hello, and requires a complete SEEN control record from that service. `session_net.cpp:301,335-338,823,858` resets reachability and hello timing on link loss, uses freshness for fallback, and starts a fresh probing window after time outside a room. Existing active direct routes survive service loss.

   Proof: `tools/recomp/net2/bounds_test.cpp:160`, `carrier_bounds`, checks the eight-second boundary, malformed replies, close/reset, unrelated UDP senders, the current service, reconnect after prior UDP success, expiry without reconnect, idle between rooms, and forced UDP/tunnel modes. The original carrier still reported success after close in the baseline. Final harness result: PASS under AddressSanitizer and UndefinedBehaviorSanitizer. The complete client suite passed 136/136, including room reuse and automatic/forced fallback.

3. Finding 7: bounded WebSocket decoded input and control output.

   Changes: `tools/recomp/net2/tls.cpp:126-246` caps retained raw plus decoded input at 1,048,590 bytes (the existing 1 MiB maximum frame plus its largest accepted header), and pauses underlying reads while decoded data awaits consumption. All outgoing frames are checked before enqueue against 262,144 bytes including headers/masks; application sends return AGAIN under backpressure, while unserviceable pong output fails the link. Upgrade output is checked before enqueue too. `:645-646` pauses Windows ciphertext reads while plaintext awaits consumption; its existing bounded ciphertext buffer still decrypts all complete buffered records, preserving records received before a socket error.

   Proof: `tools/recomp/net2/bounds_test.cpp:43`, `ws_bounds`, drives 100 reads of a sustained stream through the actual WsLink, also calls state/send with pending decoded data, and checks maximum/oversized frames, split headers, continuation bytes, small reads, EOF ordering, blocked pong floods, partial writes and upgrade limits. The original decoded queue retained 5,734,400 bytes after the same baseline stream/read count. Final harness result: PASS under AddressSanitizer and UndefinedBehaviorSanitizer. Native client integration passed 136/136. The changed Windows source cross-compiled successfully; native SChannel execution was not available on this Mac.

4. Finding 8: bounded session output before transferring tunneled datagrams.

   Changes: `tools/recomp/net2/session_net.cpp:57,405-432,872-882` bounds every producer through send_line at 262,144 bytes, including hex expansion, prefix and newline. It first attempts to drain a full queue, then explicitly drops the stalled link if there is still insufficient space. Request callers report immediate failure. send_tunnel removes each deque entry before an enqueue can clear the remaining deque during teardown. WebSocket framing is separately bounded as described above; the carrier's existing 512-datagram ceiling remains intact.

   Proof: `tools/recomp/net2/bounds_test.cpp:259`, `session_bounds`, tests exact capacity and one further byte, request failure and cleared pending state, repeated blocked tunnel batches, and 512 maximum-size datagrams through partial writes with exact byte/order comparison. The original session accumulated 2,480,400 bytes after ten blocked batches. Final harness result: PASS under AddressSanitizer and UndefinedBehaviorSanitizer. The existing 60-datagram ordered tunnel integration test passed within 136/136 client checks.

5. Finding 9: proxy access restricted to the service and proxy group.

   Changes: `tools/rendezvous/rendezvous.py:509-527` creates the Unix socket under a temporary restrictive umask (initial mode 0600), restores the original mask, then grants only owner/group access with mode 0660. `tools/rendezvous/deploy/champions-net2.service:33-41` assigns the dedicated champions-net2-proxy group and runtime-directory mode 0750; private state remains 0700. `deploy/STEPS.txt:33-40,94-101` documents creating the group, adding only the proxy worker account, restarting workers to acquire membership and checking socket/directory permissions before enabling the proxy location.

   Proof: `test_bounds.py:123-163` measures the real socket's initial/final modes, umask restoration, group inheritance, successful owner connection and cleanup. It also checks the shipped unit's group and directory/private-state settings. These probes pass; the original socket was measured as mode 0666. Existing proxy-header and per-address quota tests pass within 250/250 service checks. Actual Linux unit startup, proxy group membership and cross-user connection denial were not executed; only repo templates were changed.

6. Guest map: complete soak and RPC ranges.

   Changes: `tools/recomp/app/guestmap.h:20,25` now reserves soak as `[0xE0000,0xE0058)` and RPC packets as `[0xFF000,0x100000)`. Evidence: `soakhooks.cpp:284,315-316` writes four bytes at CTRL+0x14; `rt/iop.cpp:757,907` uses 64 packet slots of 0x40 bytes. This changes compile-time ownership metadata only.

   Proof: `tools/recomp/net2/bounds_test.cpp:298` asserts both exact high endpoints and the existing disjoint check. `test_bounds.py:166-176` compiles temporary variants: overlap in the formerly omitted soak tail and the last RPC byte must fail the existing static_assert; an adjacent block immediately after soak must compile. All three compile probes pass. Final full harness result: PASS under both sanitizers.

Validation commands and output:

- `python3 -m unittest discover -s tools/rendezvous -p 'test_bounds.py' -v`: `Ran 10 tests in 356.322s`, `OK`, exit 0, with all 14 C++ PASS groups. Builds the C++ harness with AddressSanitizer and UndefinedBehaviorSanitizer, both configured to fail on a finding; compilation and executables live in a temporary directory.
- `python3 tools/rendezvous/check.py`: `250 of 250 checks passed (48 s)`, exit 0.
- `python3 tools/rendezvous/check_client.py`: `136 of 136 checks passed (512 s)`, exit 0. Its build_cli compiled and linked the real net2 client into its temporary directory before testing.
- `x86_64-w64-mingw32-g++ -std=c++17 -O1 -Wall -Wextra -c tools/recomp/net2/tls.cpp -o local/netfix-codex/tls-win.o`: exit 0, no compiler diagnostics.
- Python AST syntax checks for both changed/new Python files and `git diff --check`: passed.

Earlier attempts are not counted as passes: the first service run was 249/250 (the timing-sensitive relay refill check); its isolated rerun passed. C++ compilation hit 120-second and 300-second test timeouts during heavy concurrent machine builds; the harness now permits 600 seconds for compilation. Initial Python fixture assumptions about repeated systemd keys and inherited socket groups were corrected. A new local UDP probe also needed to wait for delivery rather than assume immediate availability. Sanitized run logs are under ignored `local/netfix-codex/`; generated builds and fixtures stayed there or in temporary directories.

No game session was launched, and no claim of live gameplay/lockstep validation is made. Transport payload equality and ordering are checked directly. SEEN retains its existing wire format without an echoed epoch token, so a delayed valid reply from the same endpoint can refresh the eight-second window. Nothing was staged, committed, pushed or deployed.
