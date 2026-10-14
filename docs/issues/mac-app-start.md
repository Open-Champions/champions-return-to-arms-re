# The Mac application's first start: no window, the permission question, the name dialog

**State (2026-10-13, 11:20 CDT): written, built and tested as each section says; not in a
release.** Everything is in `tools/play-net/` (the application: `src/`, `play-net.patch`,
`package.sh`, `ctl.py`, `README.md`) and `local/play-playable*` (its tree and build). The
test copies ran through `play.sh` with `--rta-test`, data directories under
`local/app-next/`, the lobby on this Mac; no packaged copy was made or started, and
`package.sh` was changed but not run.

Related: [tools/play-net/README.md](../../tools/play-net/README.md),
[three-players.md](three-players.md) (the launch handshake), [native-online.md](native-online.md)
("The disconnect hold"), [mixed-arithmetic.md](mixed-arithmetic.md),
[native-soak.md](native-soak.md) ("Second part": the three proposed sections).

## What happened (release of 2026-10-13 morning, fix set 27f61e1d, first start by the owner)

From the installed application's own log (`rta.log`, read only):

| Time | Frame | Line |
|---|---|---|
| 08:08:39 | 0 | start; a fresh data directory |
| 08:19:48 | 0 | `textures: 122205 replacement file(s) in …/Desktop/champions-re/local/hd-pack/replace` |
| 08:19:49 | 0 | disc image accepted (a file under `~/Desktop`), the game's program loaded |
| 08:19:50 | 1 | `online: asking for the player name (dialog)` |
| 08:20:12 | 1132 | `online: no player name was given`, the one-step sign-in stops |

1. **Eleven minutes without a window.** The 11 min 9 s between the first and the second
   line are one call: `MainWindow::MainWindow` → `InitVirtualMachine` → `Rta::Attach` →
   `CState::StartTextures` → `ListTextureReplacements` → `opendir` of the art pack's folder
   under `~/Desktop`. macOS stops a program inside that call until the person has answered
   its question "… would like to access files in your Desktop folder". The call is in the
   main window's *constructor*: `main()` had not reached `w.show()`, so there was no
   window, no menu and no Dock activity beyond the icon - only the system's question,
   which is easy to overlook. Listing 122,205 names on that thread is slow by itself.
2. **The question comes back with every build** (section "The permission across releases").
3. **The player-name dialog ended without a name after 22 s** (section "The name dialog").

## Start-up: the window at once, folders read aside (written and tested 2026-10-13)

**Changed** (`src/Rta.cpp`, `src/RtaUi.cpp`, `src/Rta.h`; `main.cpp` in `play-net.patch`):

- Nothing under a folder that macOS guards is opened on the application's own thread.
  `StartTextures` (in the window's constructor) only decides whether replacement pictures
  are wanted; the folder is listed by a thread of its own (`StartTextureList`,
  `ListTexturesAside`) started when the game's program is loaded - not before: the pack is
  not opened until it is needed. Until the names are known the game's own textures are
  drawn; when they are, the renderer is told to look for every picture again
  (`g_textureReplaceReload`, what `texreplace reload` always did).
- The disc image is opened for the first time by a thread of its own while a local event
  loop keeps the window alive (`Rta::WaitReadable`, `RunAside` in `RtaUi.cpp`); the
  packaged application's check of the image (`CheckDisc`) and its search for one
  (`FindDisc`: Downloads, Desktop, Documents) run the same way. A disc named on the
  command line (`play.sh --disc`) goes through `Rta::BootDiscWhenReadable`.
- **The window says what it waits for**, in a line across its top (a label above the
  picture, `rtaNotice`) and in the status bar. Every such opening is registered while it
  runs (`COpening`); one that has not come back after a second gives: *"macOS is asking
  for permission to read the Desktop folder - answer the question on screen. Your disc
  image is there (~/Desktop/…). This goes on by itself as soon as you have answered
  (N s)."* A folder or file that may not be read (`EACCES`, `EPERM`) gives a sentence
  that says so and where to allow it, and is tried again every two seconds - it goes on
  by itself once it can be read. `rta.log` gets every sentence ("window says: …") and
  "window: shown N s after the application started".
- Closing the window while it waits ends the application (`Rta::Quitting`).

**Tested** (test copies through `play.sh`, `--rta-test`, drivers `local/app-next/t1a.py`,
`t1b.py`, `t1d.py`; the window read through the `.ui` file, which the application's own
thread answers, so also before the machine runs; load average 10 to 30):

| Test | What was seen |
|---|---|
| A: `--rta-textures` on a folder of 122,205 pictures (hard links to the pack's) with mode 000 | window shown 0.60 s after the start (log), visible to the first poll at 1.0 s; the game runs (frame 79 at 2 s, 428 at 8 s) with its own pictures; the window's line and the status bar: "The art pack cannot be read: ~/Desktop/…/pack/replace (Permission denied) … it is tried again every two seconds …"; `chmod 755` at 8.4 s: 1.0 s later 122,205 names listed, the line gone, 19 pictures replaced at the title |
| B: every first opening held 20 s (`--rta-test-folder-wait 20`, standing for the unanswered question) | window at 0.9 s; from 2.2 s to 20.9 s the line "macOS is asking for permission to read the Desktop folder - answer the question on screen. Your disc image is there (…)"; then the game starts and the same line for the art pack while frames go on (74 … 1185); at 42 s the pack is listed and the line is gone |
| C: a disc image that exists but may not be opened (an APFS clone of the image with mode 000, removed afterwards) | window at once with "Your disc image cannot be read: … (Permission denied) …"; `chmod 644`: the game starts within the next two-second try |
| D: the packaged application's own path (`ChooseDisc`, `launch.ini`, the pack found in the application's folder) on the working build (`RTA_TEST_PACKAGED=<dir>`, a test aid), openings held 15 s | the same two sentences, "disc image accepted", `launch.ini` written, 122,205 names from `<support>/textures/replace` |

Not tested: the real question of macOS (a test copy started from a shell inherits the
shell's permission, so the question never comes: the held and the refused opening stand
in for it); `FindDisc` aside (a test copy is always given `--disc`); a refusal in System
Settings followed by a later permission there.

## The name dialog (cause found by reproduction; fix written and tested 2026-10-13)

**What the released dialog does** (read in `RtaUi.cpp`/`RtaOnline.cpp`, and run with
`--rta-test-dialogs released`, which builds and opens the windows exactly as the release
did; `local/app-next/t3.py`; windows read from Qt and from AppKit's own front-to-back
list, no picture of the screen):

- It has **no time limit**: for a person the one-step sign-in waits for ever (the two
  minutes of `NAME_LIMIT_UNATTENDED` are for unattended test runs only). It ends without
  a name in three ways: the *Not now* button, **Escape** (or Command-period), or its
  window's close button. Nothing of ours closes or hides it.
- The **Controls** help opened by itself 2.5 s after the window was set up - once per
  data directory, and the owner's data directory was new. In the owner's run that was
  one to two seconds *after* the question (which came at frame 1).
- Reproduced: question up at 1.7 s, Controls at 4.3 s. AppKit's order, front to back:
  `"Player name" level=8`, `"Controls" level=0`, the main window. So the Controls window
  does **not** cover the question (a modal panel floats above ordinary windows); it opens
  **behind it and larger on every side** (560 × 486 round 400 × 243), and it is **dead**:
  Qt reports it blocked by the modal window (`WindowBlocked`, `blocked_now=1`) - its
  Close button does nothing. Escape, sent to the question, ended it: the log then has
  the morning's line, "online: no player name was given", and the sign-in stops.
- Raising the main window or the Controls window does not hide the question, and nothing
  takes the keyboard from it (a window shown under a modal one is ordered in without
  being made the key window).

**So:** the question did not time out and was not dismissed or covered by our code. It
was ended by one of its three ways out, 22 s after it appeared. The log of the release
does not say which; the likeliest, given what was on the screen, is Escape pressed to be
rid of the Controls window that would not close - that key goes to the window that has
the keyboard, the question. (Not excluded: *Not now* pressed on purpose; a game
controller's cancel button reaching the dialog - the bundle declares
`GCSupportsControllerUserInteraction`; not testable here.)

**Fix:**

- The question is a **sheet on the main window** (`Qt::WindowModal`): part of that
  window, in front of it, never beside or behind another window of ours. The main window
  is raised and the Dock icon asks for attention when it comes.
- It ends only by *Go online*, *Not now* or the application ending. **Escape and the
  window system's cancel are not taken** (`CNameDialog::reject`); the log says so once.
- The log says **how** it ended: "no player name was given (the Not now button)".
- **Controls never opens while a question of ours is up**, and not at the start: by
  itself it comes once per data directory when the game has run five seconds, nothing is
  asking and the one-step sign-in is over (reached the lobby, stopped, or never started);
  asked for from the Help menu while the question is up it comes when that is answered.
  The "shown once" mark is saved at once (before: only at a clean exit).

**Tested** (`--rta-test-dialogs now`, fresh data directory, no saved login, no controller,
the lobby on this Mac): the question is a sheet on the main window (`sheet=1 on=Play! …`);
Controls is not up after 10 s; asked for from the menu: put off; Escape: "the question is
still up"; main window raised: the sheet stays in front; **164 s unanswered**: still up,
the sign-in still "waiting for your player name", the machine running (frame 9,793); a
throw-away name typed and *Go online*: the account made and the lobby's game list reached
2 s later, the login saved; in a second run Controls came by itself 2.3 s after the
sign-in was over. Driven through the control socket's new `ui` commands (`ui windows`,
`ui name info|type TEXT|press ok|notnow|escape|close`, `ui controls info|show|close`,
`ui main info|raise`).

Not tested: a person's real key press and click (the test copies never take the
keyboard); the Dock's attention request; full screen.

## The permission across releases (worked out 2026-10-13; nothing was changed on this Mac)

**Why the question comes back.** macOS files a permission ("may read the Desktop folder")
under the program's bundle identifier *and its designated requirement* - the signature's
own statement of what counts as "this program" - and checks the program against that
requirement each time. An application signed without an identity ("ad hoc", `codesign
--sign -`) has the requirement "this very code":

```
$ codesign -d -r- /Applications/Play-RTA.app          (read only)
# designated => cdhash H"60ef1ff58afee4a9532d6ac78c8c74e62f9f8067"
```

Every new build has another hash, fails the stored requirement, and is asked about again.
Shown on scratch files (two different programs, same identifier, signed ad hoc: two
different `cdhash` requirements, neither satisfies the other's).

**Options, without a paid developer account.** None was carried out: no certificate, no
keychain item, no privacy setting was made or changed. The commands are for the owner.

| | What | Keeps the permission across builds | For friends' Macs | Cost |
|---|---|---|---|---|
| A | **Need no permission**: keep the disc image and the art pack out of Desktop, Documents and Downloads | nothing to keep - macOS never asks | the same: "put the image beside the app" already works | moving two things once |
| B | Ad hoc, with the designated requirement **"the identifier is ours"** | yes by the mechanism; **not tried with macOS's permission store** (needs the owner's click on a real question) | the same on their Macs | one option of `package.sh`; no certificate |
| C | A **self-signed code-signing certificate** in the owner's keychain | yes: requirement "our identifier and this certificate" - the usual way to keep permissions across rebuilds | yes, as long as every release is signed with the same certificate; Gatekeeper treats it like ad hoc ("Open Anyway" once) | making the certificate once; the private key must be kept (lost key = one more question for everybody) |
| D | An **Apple Development certificate from a free Apple ID** (Xcode > Settings > Accounts > Manage Certificates > +) | yes: requirement "our identifier and an Apple-issued certificate of this team" | yes; still not notarised (that is the paid programme) | Xcode sign-in; the certificate runs a year and is renewed in Xcode |

**A is the cleanest and needs no signing change; B or C on top makes a pack left on the
Desktop bearable.** Recommended: A now, and C (or D) when a certificate is wanted anyway.

**A - nothing under a guarded folder.** The application's own data is in
`~/Library/Application Support/Play-RTA/` already. New in this build: it takes
`textures/` there (`textures/replace/*.png`) as the art pack when `launch.ini` names no
other folder, the disc image was always looked for there first, and neither is opened
before it is needed. Both moves are renames on one volume (Desktop, Application Support
and /Applications are the same APFS volume here: `stat -f %d` gives 16777232 for all
three), so they take a moment whatever the size and need no free space:

```
# quit Play-RTA first, and pause whatever writes into the pack (the enlarging job)
S="$HOME/Library/Application Support/Play-RTA"
mkdir -p "$S/textures"
# the pack's pictures are local/hd-pack/replace.nosync (122,205 files; "replace" beside it is a link to it)
mv "$HOME/Desktop/champions-re/local/hd-pack/replace.nosync" "$S/textures/replace"
ln -sfn "$S/textures/replace" "$HOME/Desktop/champions-re/local/hd-pack/replace"   # the tools keep their path
# the disc image, with a link left behind for the scripts that name the old place
mv "$HOME/Desktop/Champions - Return to Arms (v2.00)/Champions - Return to Arms (v2.00).iso" "$S/"
ln -s "$S/Champions - Return to Arms (v2.00).iso" "$HOME/Desktop/Champions - Return to Arms (v2.00)/Champions - Return to Arms (v2.00).iso"
# launch.ini: take the line "textures=..." out (the application then finds textures/ in its own folder);
# the remembered "disc=" line may stay: the image that is "not there any more" is looked for, and found in $S
```

What it involves: the links must point *from* the Desktop *to* Application Support - a
link in Application Support to a folder on the Desktop does not help, macOS decides by
where the files really are. Programs started from Terminal (the enlarging job,
`play.sh`, the tours) read through the links with Terminal's own permission, as now. The
Desktop here is kept in iCloud Drive (`com.apple.icloud.desktop` on `~/Desktop`): the
pack was already outside the sync (`.nosync`), the 4.3 GB image is inside it and leaves
it with the move (iCloud then removes its copy; the link that stays is a few bytes).
`~/Library` is in Time Machine's backup like the Desktop. Nothing of this was done.

**B - ad hoc with a stable requirement** (new option `package.sh --stable-requirement`,
or `RTA_SIGN_STABLE=1`). The nested Qt code is signed as before, then the bundle alone
with an explicit requirement:

```
codesign --force --deep --sign - Play-RTA.app
codesign --force --sign - -r='designated => identifier "io.github.open-champions.play-rta"' Play-RTA.app
codesign -d -r- Play-RTA.app        # designated => identifier "io.github.open-champions.play-rta"
```

Tried on a scratch bundle (a copy of `/bin/ls` with a nested library; nothing of ours):
it verifies `--deep --strict`, shows that requirement, and a second, different program
signed the same way satisfies the first one's requirement - which is exactly what the
permission store checks. Not tried: whether macOS files and honours it for a real
question (the first build signed this way is asked once in any case, because the stored
requirement is still the old hash). Its weakness: any program on the Mac that signs itself
ad hoc with this identifier would be taken for Play-RTA by the permission store.

**C - a self-signed certificate** (new option `package.sh --sign "NAME"`, or
`RTA_SIGN_IDENTITY`). Once, in *Keychain Access > Certificate Assistant > Create a
Certificate…*: name `Play-RTA signing`, identity type *Self Signed Root*, certificate
type *Code Signing*. Or on the command line (not run here):

```
cd "$(mktemp -d)"
cat > cert.cfg <<'CFG'
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = Play-RTA signing
[ext]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
CFG
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -config cert.cfg -keyout key.pem -out cert.pem
openssl pkcs12 -export -legacy -inkey key.pem -in cert.pem -name "Play-RTA signing" -out identity.p12 -passout pass:play-rta
security import identity.p12 -k ~/Library/Keychains/login.keychain-db -P play-rta -T /usr/bin/codesign
security find-identity -p codesigning            # lists "Play-RTA signing" (as not trusted: that is enough to sign)
rm key.pem identity.p12
# then, at every release:
tools/play-net/package.sh --sign "Play-RTA signing" …
codesign -d -r- local/dist/Play-RTA.app          # designated => identifier "io.github.open-champions.play-rta" and certificate leaf = H"…"
```

(`-legacy` is for OpenSSL 3, whose default PKCS#12 encryption the keychain does not read;
LibreSSL's `openssl` does not know the flag and does not need it. The first signing asks
once whether `codesign` may use the key: "Always Allow".) The first build signed this way
is asked about once more; from then on every build signed with the same certificate is
the same program to macOS. Back up the certificate with its key (Keychain Access >
export as .p12): a new certificate is a new program.

**D** needs only Xcode: sign in with any Apple ID, create an "Apple Development"
certificate there, then `package.sh --sign "Apple Development: NAME (TEAMID)"`.

What does not help: giving the application "Full Disk Access" (filed under the same
requirement, lost the same way); a link from Application Support to the Desktop (above).

## Two entries for one page (reproduced, fixed and tested 2026-10-13)

**The fault** (`src/RtaNet.cpp`, `CheckArithmetic` in `src/Rta.cpp`; release notes of the
morning). The application kept the other players it hears in a table **by the address
and port a datagram really came from**. A relay on the application's own computer has one
socket for a page and sends from it now with the computer's outside address and now with
the loop-back one - it answers to the address it last heard the application from, and the
application's own "patch set" and "arithmetic" datagrams went to the address a datagram
had come *from*, while the game's datagrams go through the loop-back interface. So the
one page was two entries, and what the page had said (patch set, "browser arithmetic")
stood in whichever entry it happened to reach. An entry not heard for 15 s counts as a
player who has left; when that was the entry that had said "browser", the application
went back to its own arithmetic in the room, with the page still there.

**Reproduced with the released build** (`local/app-next/silent.py`, application hosts,
a page of the existing page build joins through `tools/play-web/relay/relay.py --lan
--account-burst 1000`, all on this Mac): `peers` lists `[127.0.0.1:56431 set=? arith=?]`
and `[192.168.1.123:56431 set=27f61e1d arith=browser]`; the second falls silent; 15 s
later, in the room, "arithmetic: the machine computes with Play!'s own arithmetic again",
and it stays so - with the status-bar warnings "another player's copy cannot compute with
browser arithmetic" and "does not say which patch set". A game started then is out of
step from the first frame.

**Fix.**

- **One player is one entry**: the table is kept by what the machine knows the player by
  - the address shown to the machine, and the port (`m_peers[UdpKey(shownIp, fromPort)]`);
  the real source of the last datagram is kept beside it (`peers`: `from=127.0.0.1`), and
  the log says once "the player known as … is now heard from …: the same player, one
  entry".
- **What we tell a player goes the way the game's own datagrams to that player go**
  (`RealUdpAddress`, the same carrying as `OnUdp`), not to wherever its last datagram came
  from: the relay then hears the application from one address only and stops changing
  sides.
- **The arithmetic follows the players in the room, not a silence**: in a game's room
  (lobby states 6 and 7) a copy on browser arithmetic stays on it although nobody heard
  asks for it at the moment - the player it was needed for may only be quiet - unless a
  copy heard there cannot compute that way. It goes back when it has left the room
  (`CheckArithmetic`, `m_inRoomNow`; the log says "… it stays on browser arithmetic until
  it has left the room").

**Tested** (same set-up; the page build is the existing one, so the page still runs the
old network source):

| Build | What | Result |
|---|---|---|
| released | one start, 40 s of play | **2 entries** for the one page; in step by luck of which entry spoke (2,064 frames, 0 different) |
| released | the page's browser stopped 24 s in the room | back to its own arithmetic after 15 s of the "browser" entry's silence, and not back to browser afterwards |
| new | **6 starts** (two series of 3), 40 s of play each | **1 entry** every time (`[192.168.1.123:PORT from=127.0.0.1 … arith=browser]`), one change of arithmetic per start (to browser), the page's line "Everyone computes the same way: 1 other player heard"; 5 starts played: 2,093 / 2,061 / 2,088 / 2,068 / 2,108 lockstep frames compared, 0 different |
| new | the same 24 s of silence in the room | stays on browser arithmetic throughout and afterwards |

One of the six starts did not play: the host's *Start Game* press started nothing - both
machines were still in the room (lobby state 6) 151 s later, the page still heard every
second, nothing in either log. The driver did not press again in that run; in the next
three starts (a press that starts nothing is now reported and repeated) every first press
started the game. **Cause not found**; nothing was held back and the entry was single in
that run too. Load average 8 to 11.

Not tested: a page built from the new source (the page's own copy of `RtaNet.cpp` gets
the same changes at its next build; they compile for the browser: `em++ -fsyntax-only` on
`RtaWebNetCore.cpp` and `RtaOnline.cpp`); two pages; a relay on another computer.

## The three proposed sections on the emulator (run 2026-10-13 by a test agent, summarised here)

`tools/recomp/soak/proposed-sections.pnach` (save point, script read, jump gate: 8 words)
given to two copies of the released build through the application's own option for a
further patch file (`play.sh … -- --rta-extra-patch tools/recomp/soak/proposed-sections.pnach`;
such a file is applied whole and does not count in the set's figure, which stayed 27f61e1d
on both). Neither `patches/SLUS-20973_4028A55F.pnach` nor `sections-suggested.txt` was
touched. Scripts, logs and per-frame traces: `local/app-next/sections/`. Load 10 to 28.

- **Interpreter**: `tools/recomp/soak/sections_test.py` 36 PASS, 0 failed (A 15, B 11,
  C 10); `tools/ee_tests.py` 222 PASS, 0 FAIL.
- **In memory**: `rta.log` "patches: 8 more words from …proposed-sections.pnach" on both
  copies; all 8 words peeked at the start and the end of the run hold the sections'
  values on both.
- **A normal game with them on** (run `on`): launch by code into `hub`; both players
  walking (1,488 consecutive lockstep frames); both at the save point; the hub's jump
  gate approached by the joiner (found, +0x4d, in lockstep frame 12,174 on both copies);
  the game's own level change (Firiona, the gateway, the mission menu) into `blood1` at
  the same lockstep frame 19,344 on both; 30 s there. **13,123 lockstep frames compared,
  every sync hash equal**, the other player's hash as received equal for 6,642 and 6,655
  frames, the checksum flag 0 after every step.
- **Save point (section A).** In a lobby game with characters made in the lobby a save
  point cannot be used at all (`Savepoint_interactPrompt` refuses while
  `net_allPlayersState2()` holds, as `sync-breakers.md` says), so the section matters
  only with a character from a memory card. To reach it the test wrote one word (player
  0's character kind, 2 to 1, on both copies - a test write, not a game step). Then,
  with the joiner's own card screen up while the host uses the point: **without the
  sections** the save point's +0x84 becomes 1 on the host's copy and stays 0 on the
  joiner's, for the remaining 825 sampled frames and after both card screens are gone;
  **with them** it becomes 1 on both in the same frame, no difference in 3,854 frames.
  The sync hash is equal in both arms (it does not cover this state).
- **Jump gate (section C).** Walking up to the hub's unfound gate: without the sections
  the owner's copy has it found one lockstep frame before the other (1,906 / 1,907 and
  1,609 / 1,610, two runs); with them in the same frame on both (12,174 and 1,720, two
  runs). Small sample; the longer lead of `native-soak.md` (closing the inventory beside
  the gate) was not reproduced.
- **Script read (section B).** The race itself is not exercised by `hub` and `blood1`
  (no draw-time script reads a quest variable there). The section is at work: after the
  level change the table holds 5 names with it and 7 without (the two only read are not
  added); values equal.
- **Not reached**: a save point with a real memory-card character; a jump gate with a
  script, and the one in `blood1`.

## The late-save and the strafe section on the emulator (run 2026-10-13 evening, before they went into the set)

The two sections of [native-soak.md](native-soak.md) (third part, "A late save": 6 words in
`save_daemonRun`) and [native-first-person-controls.md](native-first-person-controls.md)
(part 3: strafe mode, 84 words) were proven on the native build. Before they were taken
into the fix set they were given to copies of the built Mac application through
`--rta-extra-patch` (`tools/recomp/soak/proposed-sections.pnach`,
`tools/recomp/app/fp-proposed.pnach`; the figure stayed 073064bb, "14 more words" and "84
more words" in each copy's log, all 90 words read back from every copy's memory). Every
copy through `play.sh` with `--rta-test`, a data directory of its own, the lobby server on
the same Mac; load average 12 to 100 from other work. Drivers, logs and per-tick files:
`local/rel.nosync/r4/` (not in the repository).

**Three test aids** (a local patch file of 80 words given to every copy of a run, never
part of the set). The application's control socket has no way to call a function of the
game, a `poke` cannot be put into the same lockstep tick on two copies, and a vertical
blank - where the socket is served - is not a tick boundary (words sampled there differ
between copies in about a tenth of the frames for that reason alone). So, in
unreferenced functions that no section uses, each inert until a word is poked:

- a **call stub** on the main loop's once-a-frame call at 0x323350 (after the draw pass,
  outside the tick): calls one function with one argument - the section's sender
  0x215C98 with the mode, as an application that offers the mode does, and the game's
  own sender of a level change (`hudmsg_sendNewWorld` 0x1D9250);
- a **timed hit** on `net_frameLoop`'s call of `tasks_run` (0x13AEE0): in the tick whose
  lockstep frame equals a poked word every player object gets a poked amount of pending
  damage, with the kill plane's own two stores - the same tick on every copy;
- a **tick recorder** on the call of `path_service` (0x13AF3C, after the tick's run
  tasks): lockstep frame, position, facing and mode byte (+0x47E) of one player into a
  ring the driver reads every blank - a value per tick and copy, not per blank.

All three were run in the function-level interpreter first. Patch words that hold data
are no use for this: the application writes a changed patch word back at every blank.

**The game with both sections on.**

| Copies | What | Lockstep frames compared (the game's own sync hash, every frame) | Different |
|---|---|---|---|
| 2 | hub, both walking | 2,516 | 0 |
| 2 | the game's own level change (Firiona, the gateway, the mission menu) into `blood1`, its 31-second opening cutscene, 35 s of play there (a character killed by monsters, on both copies alike) | 5,444 | 0 |
| 2 | the strafe steps below | 1,210 | 0 |
| 2 | the late-save steps below, through a party wipe and the reload | 918 + 2,180 | 0 |
| 3 | two launches, 50 s of walking each | 2,621 and 2,531 | 0 |
| 4 | two launches | 2,142 and 2,262 | 0 |

The checksum flag stayed 0 on every copy and no copy marked a peer out of sync.

**Strafe mode.** Emulator players never send the mode; they have to simulate a player
who does.

- The sender called on copy 1 (mode 1): the mode byte of that player is 1 from lockstep
  tick 4,415 **on both copies**; called with 0: 0 from tick 4,924 on both; with 1 again:
  tick 5,132 on both. A game message is applied in the tick its frame is simulated, on
  the sender's machine too.
- With the mode on that player was walked left, backwards, diagonally, forwards and to
  the right by pad input. The recorder has **937 of 937 ticks** of the step on both
  copies: position bits, facing and mode byte equal in every one. In the 320 ticks the
  player moved with the mode on, the facing stood at the camera's heading (0x3E3D minus
  the yaw word) and the movement was more than 60 degrees off it in 243 (157 sideways,
  86 backwards); in the 249 moving ticks with the mode off it was within 30 degrees of
  the facing in all, as the original runs.
- **A level change clears it**: asked for with the mission menu up (1 from tick 21,936
  on both), 0 from tick 22,006 on both - the new characters of `blood1`; 5,200 of 5,200
  ticks of that step equal.
- Not established: whether "use" on a person or a gateway works as before for a character
  that faces the camera's heading with the mode on. The level change above was walked
  with the mode off; one attempt with it on got no dialogue, and so did one with it off
  in which the driver's walker had got stuck beside the person.

**The late save.** The game's own ways from level to level do not leave another
machine's inventory open - an NPC dialogue, the mission menu and the gate scroll close
it, and `blood1` opens with a cutscene, for whose end the entry save waits on every
machine - so the entry was made as in the native directed game: copy 2 opens its
inventory in the hub, the host sends the game's level-change message for `hub` (the
call stub), every copy enters the level in the same tick. 120 frames later every player
loses 5 hit points (the timed hit), so that a save taken later holds other records;
copy 2 closes its inventory five seconds after arriving; then a lethal timed hit for
both players, and the game loads the level again from each copy's own save buffer. The
tick of a copy's last save is read from its word 0x4F8F30.

| | Without the section (set 073064bb + strafe) | With it |
|---|---|---|
| level entered | tick 247 | tick 409 |
| copy 1 saves | tick 247 | tick 409 |
| copy 2 (inventory open) saves | **tick 501**, when the inventory closes: 254 ticks late | **tick 409** |
| after the wipe and the reload, both copies read in one frame | copy 1 gives both players 32.80 hit points, copy 2 gives both 28.49: the two players' records differ between the copies (+0xAC) | 32.80 on both copies; the two players' records equal |

"Equal" leaves out six or seven bytes at +0x4A75 of each record that differ between the
copies at the hub's start already, in both runs. In the run without the section the sync
hash stayed equal and nothing was flagged - it covers the seed and the positions, not hit
points - as in the native directed game; with a fight between the entry and the wipe the
native farm got the game's out-of-sync message from the same cause.

**Not reached here**: a card screen or a shop as the thing that holds the save (the
inventory only); a save that is late and then overwritten by a save point; the mode sent
by two players at once, or by a player being dropped (native runs only); more than one
level change with the mode on.

## The launch hold (written and tested 2026-10-13)

**The hole** is the game's (`three-players.md` cause 1; `native-online.md` "The
disconnect hold"): a joiner that takes the host's START fills its launch tables from its
live connections to the other players and then disconnects them all; one that reads its
socket later finds the others' disconnects in the same read as START and files wrong
addresses. The handshake repairs one wrong entry from the datagrams that arrive - not two
joiners that are wrong about each other. The lobby server's fix (it no longer tells a
console its own address) and the adaptor fix are both in; this is the rest.

**The hold** (`src/RtaNet.cpp`, "A peer's disconnect, held back"; the application and the
page compile the same file): a datagram that is the peer library's disconnect - 8 bytes,
`00 05`, the connection's code, a reason - and arrives while the game's lobby state word
(0x506160) says "in a game's room" (6) is shown to the machine 30 vertical blanks late,
or as soon as the state has moved on. By then the joiner has taken START and filled its
tables from connections that were all still there. Nothing else is held, nothing during
a game; a player who leaves a room is seen to leave half a second late.

- `CNet` knows nothing of the game: the lobby state and the count of vertical blanks are
  told to it once a frame through `CNet::NoteGame(inRoom)`, which `COnline::Tick` calls -
  in the application and in the page alike (both call `Tick` every vertical blank), so the
  page's glue needs no change. Where nobody calls it nothing is ever held; a held
  datagram that the count does not release goes on after two seconds by the clock.
- **The switch**: `NetConfig::holdDisconnects` (default on). The application:
  `--rta-no-disconnect-hold`. The page has no switch of its own yet: one line in
  `tools/play-web/src/RtaWebNet.cpp` (`config.holdDisconnects = false`) is all it takes.
- Counted: `udp_held` in `info`, `held_disconnects` in `peers`; `rta.log`: "net: a
  disconnect from the player at … is shown to the machine half a second late".

**Tested** as `three-players.md` did it (`local/app-next/four.py`, made from the release's
`net.py`: four copies of the application through `play.sh` and the lobby on this Mac into
one game by code, every copy at 192.168.1.123, set 27f61e1d, own-address word 00000000 on
all; the **last joiner's machine stands still for 2 s from just before Start Game**
(`hang 2`), which makes it read START and the others' disconnects in one go; then 45 s
of play with every copy's ring of sync hashes compared by frame; load average 8 to 12):

| | Launches | All four in the level | Lockstep frames compared, each launch | Different | Disconnects held (copies 1 to 4) | Port tables at the start of the launch |
|---|---|---|---|---|---|---|
| hold on (the default) | 6 in a row | **6** | 2,308 / 2,287 / 2,300 / 2,298 / 2,313 / 2,306 | 0 | 0,0,1,2 / 0,1,1,2 / 0,0,1,3 / 0,1,1,3 / 0,1,0,2 / 0,0,1,3 | no entry 0 and no copy of the host's port in any table; in 2 of 6 the held copy had its two fellow joiners the wrong way round (the accept rule that goes by address) - each still a real player, repaired by the handshake |
| hold off (`--rta-no-disconnect-hold`) | 5 in a row | **5** | 2,261 / 2,295 / 2,343 / 2,331 / 2,289 | 0 | 0,0,0,0 every time | **in 5 of 5 the copy that stood still had the host's port filed for both fellow joiners** (the race of `three-players.md`, gone the bad way); the handshake repaired it each time, because nobody was wrong about that copy |

So: with the hold a joiner's tables are filled right although it read START late - the
wrong entries the race makes are gone, 6 of 6 against 0 of 5. **No launch failed in either
series**: the failure needs a second joiner that is wrong about the copy that stood still
at the same time (1 launch in 14 in the native build's count, 1 in 6 in its forced
series), and five launches without the hold did not meet it here. What the hold removes
is the half of that pair the race supplies; the other half (two joiners the wrong way
round) still points at real players and is repaired.

The six launches with the hold ran on the build before the last small change (existence
checks moved off the application's thread; the network source is the same); the five
without it, and two more with it, on the final build (both launched; 2,300 and 2,274 frames compared, 0
different; disconnects held 0,0,1,3 and 0,1,0,3).

Not tested: the page with the hold (it needs a page build from this source); three
players; two computers; a launch in which the START itself is late.

## The patch, the build and the standing checks (2026-10-13)

- `play-net.patch` regenerated with `local/play-orig/mkpatch.sh`: 21 files, 4,439 lines
  (was 4,400). New against the released patch: `main.cpp` (a disc image named on the
  command line is opened aside; the application ends when it was closed while waiting)
  and `mainwindow.cpp` (the last disc image is not looked at before the window is shown).
- **It reproduces the tree**: the patch applied with `patch -p1` to the untouched copies
  of the 27 files under `local/play-orig/Source` gives, file for file, what is in
  `local/play-playable/Source` (27 compared, 0 differ); the tree differs from the pristine
  Play! checkout (`local/rel.nosync/play-pristine`) in exactly those 21 files and
  `ui_qt/rta`, and `ui_qt/rta` is `tools/play-net/src` byte for byte. `build.sh` then says
  "play-net.patch is in already" and builds.
- **Standing checks on the final build** (`local/app-next/solo.py`, the release's
  `solo.py` with its own directories: one test copy at 4× with the art pack, load average
  8 to 10): the pack's 122,205 names listed aside 0.7 s after the game was loaded; title
  **60.00** frames a second (video thread 2.4 ms a frame, 81 replacements held); first
  level standing **60.00** and 60.00 (7.0 and 7.3 ms, 259 held), walking **60.00**
  (6.7 ms, 323 held); still screens: the hub's pause menu differs by at most 3 of 255 in
  about 120 pixels right after it opens (as on the released build) and is identical 10 s
  later, a paused frame is identical in three consecutive pictures; heat haze in `fire3`:
  **0 blocks of noise in 6 pictures**, 6,594 pieces of the frame kept as textures, 60.0
  frames a second at all six places.

On the final build the start-up tests A, C and D and the name-question test were run
once more with the same results (window 0.4 to 0.5 s after the start), and *Not now*:
"online: no player name was given (the Not now button)".

## What is left

- **The owner's choice for the permission** (section "The permission across releases"):
  move the image and the pack (A), and/or sign with a stable requirement or an identity
  (B, C, D). None of it was done. `package.sh` with its new options has not been run.
- **Not seen with macOS's real question**: every start-up test stands in for it with a
  held or a refused opening. The first start of the next installed build is the test.
- **How the morning's name question ended** is not known (Escape, *Not now*, or a
  controller); the next log will say.
- **One application-and-page start in six** in which the host's *Start Game* press
  started nothing (cause not found; not seen again in three starts).
- **The page** gets the hold, the single entry and the room rule at its next build (its
  glue is unchanged and needs no change; a switch for the hold there is one line).
- No launch of four failed here with or without the hold: the hold is shown by the
  tables it corrects, not by a failure it prevented.
- The three proposed sections: a save point with a memory-card character, a scripted
  jump gate. Whether they go into the set is the release's decision.
- `FindDisc` aside (the search through Downloads, Desktop and Documents) was not run: a
  test copy is always given its image.
