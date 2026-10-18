# Windows VM versus Mac native test

2026-10-17, America/Chicago. **STATUS: BLOCKED.** Windows has not booted;
Windows/Mac shared-game ticks: **0**. Synchronization, a level change, Windows
SChannel, and Windows graphical execution are **not verified**. No Windows
screenshot exists. The work below is preparation and a Mac control run.

## Ownership and scope

Malik authorized this test on 2026-10-17. Worktree:
`~/Projects/champions-re-wt/windows-vm`, branch `t3/windows-vm`, based on research
main `a2b145b6b22f3c0451f861ed70faa1827f94bf09` at task start. No checkout/source
or build output in `~/champions-re` was edited. Git worktree creation necessarily
registered metadata with its parent repository. No push, PR, or issue action.

Read the owner's rules, AGENTS.md, CONTRIBUTING.md, REPOSITORIES.md, VALIDATION.md,
the Windows/rendezvous/TLS area documents, and the coordination log. The owner's
public-service exception is used: TLS hostname
`play-rta.167.99.183.124.sslip.io:41900`, with no local-only override. No server
administration or unrelated service operation was attempted.

All artifacts below are relative to this worktree and ignored under `local/`.
The ELF is linked read-only from the research checkout; VU generated inputs were
APFS-cloned. Godot dependencies are linked for the required doctor check only.
The private disc and programs are staged locally, not published.

## Built and run

- `python3 tools/doctor_home.py native godot`: **0 failures**, two warnings
  (the owner's Desktop symlink correctly does not point at this worktree; no
  shared `bin/rta_app` in this new worktree). `local/vm-test/doctor.txt`.
- `python3 tools/recomp/app/build_win.py --jobs 4`: **90/90 compilation units**,
  48 seconds reported compilation wall time, all four EXEs linked. Windows
  `rta_app.exe`: **28,383,232 bytes**. `local/vm-test/build-win.log` and
  `local/recomp-out/win/rta-windows/`. Built, **not executed on Windows**.
- `python3 tools/recomp/app/build_win.py --standin --jobs 4`: completed.
  `local/vm-test/build-standin.log`.
- The ARM64 and Rosetta x64 `fpcheck` controls: **27/27 finite-number rows
  identical; 49/54 total rows identical**. The five differences are the
  previously documented arbitrary-bit-pattern VU add/sub/mul/madd/msub cases
  involving nonfinite inputs. This is not a Windows arithmetic result.
  `local/vm-test/fpcheck-mac-{arm64,x64}.txt`, `fpcheck-comparison.txt`.
- `build_win.py --mac` initially omitted `net2/launch.cpp` and the room-service
  implementation. The build succeeded but its hooks would remain null. Fixed
  this target to compile the same eight net2 sources as Windows and link Network
  and Security. Rebuild: **8/34 units**, both Mac app variants linked.
  `local/vm-test/build-mac-net2.log`. Windows compilation is unchanged.
- **Ran the fixed Mac graphical program offscreen**, with the private disc,
  `--play-host --service play-rta.167.99.183.124.sslip.io:41900`, script input,
  separate card/data directories, no local-only override. It reached the title,
  created a room, reached character selection, and exited **0** after
  **832 frames / 901 fields / 14.998 seconds**. These are boot/front-end frames,
  **not shared gameplay ticks**. `local/vm-test/mac-app-preflight.log` and
  `mac-preflight-command.json` hold the exact execution. The room closed on exit.
- A separate Mac `net2cli` diagnostic also returned online with no problem.
  `local/vm-test/mac-tls-probe.log`. Relevant line from the Mac runtime:

```text
debug: stage online, service play-rta.167.99.183.124.sslip.io:41900, tls on (rule auto): TLS 1.3, certificate for play-rta.167.99.183.124.sslip.io checked (trusted: the system's store), 0 requests open, try 0
```

The Mac identity was subsequently moved to
`~/.credentials/champions-windows-vm-net2-mac/` and catalogued. The prepared Mac
host command uses this new location; the preflight command preserves the actual
historical path. The Windows guest must create a separate identity.

Artifact hashes (`local/vm-test/build-sha256.txt`):

```text
6759e26c1cc43b315f265ef4a62b83b5e057577cde16a892d1a499b7bf32423d  Windows rta_app.exe
0672731fede73b7985dd528aa70a08609854f116c5afc56e01fe5311ea069cda  patched Mac rta_app
```

## VM preparation — not installed or boot-tested

Installed **UTM 4.7.5** with `HOMEBREW_NO_AUTO_UPDATE=1 brew install --cask utm`.
The prepared bundle is `local/vm-test/RTA-Windows-Test.utm`:

- ARM64 QEMU/HVF, **4 CPUs, 8192 MiB RAM**, sparse **128 GiB NVMe** disk.
- UEFI with the packaged secure-vars template, TPM enabled. No requirement,
  certificate-validation, UAC, or macOS privacy bypass.
- Windows installer, `RTA_SETUP` answer-file/tools media, private `RTA_DATA`
  game/runtime media. These are in the bundle's `Data/` directory.
- Emulated NAT; SSH forwarding only **127.0.0.1:22224 → guest:22**. No LAN
  listener. WebDAV sharing enabled/read-only in configuration, but a shared
  folder has not been selected or verified; ISO media supplies the private files.
- Custom `Autounattend.xml` stages English Windows 11 Pro, partitions only the
  VM's disk 0, and leaves **AcceptEula=false** for the owner. A local console test
  user `rtatest` has no password; SSH is configured for the dedicated public key
  only, with password/empty-password authentication disabled. It is not a
  Microsoft account. First-logon preparation installs guest tools/OpenSSH and
  copies the payload to `C:\rta`. This script has **not run**.
- Dedicated SSH private key stays at
  `~/.credentials/champions-windows-vm-ed25519`, catalogued; only its public key
  is in the VM setup media. No existing account credential was copied.
- Optional CPU-rendered OpenGL: MSYS2 UCRT64 Mesa **26.2.5-1**, plus its DLL
  dependency closure, in `payload/mesa/`. Package hashes checked against the
  official HTTPS package database. Manifest: `local/vm-test/mesa-manifest.json`.
  Not executed; no claim of Windows rendering or performance. The prepared
  launcher selects llvmpipe with four worker threads.

The XML parses, the plist passes `plutil -lint`, and `qemu-img info` reads the
blank disk as a valid 128 GiB QCOW2. UTM has **not imported/validated the bundle**.

Sources: [Microsoft ARM64 download](https://www.microsoft.com/en-us/software-download/windows11arm64),
[UTM guest tools](https://docs.getutm.app/guest-support/windows/),
[UTM 4.7.5 configuration schema](https://github.com/utmapp/UTM/tree/v4.7.5/Configuration),
[MSYS2 Mesa](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-mesa).

**Installer metadata discrepancy retained:** the English selector supplied
`Windows11_Client_arm64_en-us_26300_9457.iso`. Its SHA256 is
`8992f2d2cfd2fa647e579e9eb31fc21f34da8333c29b6170fde17d2ed6623e9c`, which appears
in Microsoft's published table under **Arabic**, not the English row
(`dbf606ce...`). A fresh download-page fetch reproduced those labels. Mounted
read-only, the volume is `CCCOMA_A64FRE_EN-US_DV9` and `sources/lang.ini` says
`en-us`. Thus the download matches a Microsoft-published digest and its mounted
language is English, but the table-label discrepancy is unresolved. Do not call
this an English-row checksum pass. Evidence: `windows-iso-sha256.txt` and
`microsoft-download-page.html` under `local/vm-test/`.

## Actual blocker and owner step

The single `utmctl list` call printed twice:

```text
Error from event: The operation couldn’t be completed. (OSStatus error -1743.)
NOTE: utmctl does not work from SSH sessions or before logging in.
```

It returned no VM entries. Read-only native UI inspection shows UTM's empty
welcome screen. T3 Code has no entry in System Settings → Privacy & Security →
Automation. Its inspected signing entitlements also lack Apple Events automation;
the exact OS attribution of the refusal is not proven. This is an actual macOS
control refusal, not a request for repeat task authorization. The user's rule
forbids bypassing a denied action through another tool or permission change;
no such bypass, TCC reset, re-signing, or permission modification was attempted.

Owner can launch the prepared VM directly:

1. In Finder press Command-Shift-G and enter
   `~/Projects/champions-re-wt/windows-vm/local/vm-test/`.
2. Double-click `RTA-Windows-Test.utm`; select **RTA Windows VM Test** in UTM,
   then press **Play**. If import/start errors, preserve the exact error.
3. If the installer asks to boot from CD, press a key. Review and accept the
   Windows license yourself. Any further installer prompt is not yet observed;
   stop there for inspection rather than guessing.
4. Report when the Windows desktop is reached (or the exact intervening prompt).
   Then verify guest tools, SSH, and `C:\rta\setup-complete.txt` before testing.

## Resume the actual cross-platform test

Prepared, **not run**: `local/vm-test/prepare-pair.py` uses the existing
`n2party.script_lines()` and tick watches for two players, 2400 frames before a
scheduled change at lockstep tick 3100 to drunare, then 2400 more frames. This is
the documented external-service flow adapted for separate operating systems.
The Windows app uses its supported runtime equivalent
`-- --opt net2-service=play-rta.167.99.183.124.sslip.io:41900` (its top-level
parser does not have the Mac's `--service` switch). Neither command enables
`net-local-only=1`.

- Start `local/vm-test/run-mac-host.py`; read the room from
  `local/vm-test/mac-results/host.out`.
- On the Windows interactive desktop, run `C:\rta\run-windows.ps1 -Room CODE`.
  For SSH-driven launch use an interactive scheduled task for the logged-in user;
  a noninteractive SSH process alone does not verify the desktop window.
- Collect `C:\rta\results\` privately into this worktree. Run
  `python3 tools/rig/compare.py ticks HOST.tick.tsv J1.tick.tsv` and inspect the
  common tick count, all columns, launch/player/level records, and screenshots.
  Do not infer synchronization from the two processes merely staying alive.
- Intended screenshots (do not exist yet):
  `C:\rta\results\windows-in-level.png`, `windows-second-level.png`.
- If Windows TLS fails, collect its exact errors and a Windows `net2cli --service`
  debug-link line before diagnosing. Only Mac TLS has run so far; a Windows CLI
  diagnostic executable still needs to be built/adapted if required.

Completion requires **2000+ shared ticks with no differences**, preferably the
level change, and inspection of a Windows graphical screenshot. None of these
completion gates is claimed here.
