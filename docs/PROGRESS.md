# How complete is it

Updated at every check-in of the work. **Last update: 2026-10-20, 15:02 CDT.**

One table for the whole effort to make Champions: Return to Arms (SLUS-20973 v2.00)
playable again, online, on today's computers. The percentages are estimates by the people
doing the work, not measurements; each row says what it rests on and what is still missing
for 100 %. The evidence and the conditions behind every statement are in the documents
linked from [STATE-OF-PLAY.md](STATE-OF-PLAY.md).

Limits that hold for every row: nothing has run on a PlayStation 2 or in PCSX2; nobody has
yet sat down and played a session by hand - every test drove the game by script. Almost all
tests ran on one Apple-silicon Mac; the exception is one series of native games between two
Macs on two different home networks (2026-10-20, [native-rendezvous](issues/native-rendezvous.md),
"Two networks"). "Done" below therefore means: works and is verified by test.

| Part | Done | Rests on | Still missing for 100 % |
|---|---|---|---|
| Mac application (the Play! emulator with this project's changes) | 98 % | 60 pictures a second at four times the resolution; the known picture faults fixed; every kind of screen looked at ([visual-check](issues/visual-check.md)); first-start faults fixed after the owner's own first start ([mac-app-start](issues/mac-app-start.md)); rolled out on fix set `9ac29719`; the release of 2026-10-14 adds the *Room* menu - rooms on our own service with no lobby or sign-in, the application and the native program in one game ([app-rendezvous](issues/app-rendezvous.md)) | a person playing a session through; a room driven from the menu by a person |
| Online, two players | 96 % | 7.9 million lockstep ticks on the suggested fix set with no difference that reached a player ([native-soak](issues/native-soak.md)); two copies through the game's own level change; two computers on two different networks in one game through the service on the server, punched straight through both routers (50 to 85 ms) and by the relay, 4,311 to 4,315 ticks in step through a level change ([native-rendezvous](issues/native-rendezvous.md), "Two networks") | a person at the controls on each side; a router that changes ports; a network that blocks TLS to the service (only a plain-text test instance got through) |
| Online, three and four players | 94 % | both causes of the failed launches found and fixed, one in the lobby server and one in the emulator ([three-players](issues/three-players.md)); on the rolled-out build three and four copies launch 3 of 3 times and stay in step | players behind a real router; a level change in a game of three or four |
| Browser version (the same emulator as WebAssembly) | 92 % | plays in Chrome and Brave, and in Safari's engine with a stall on arriving in a level ([browser-build](issues/browser-build.md)); relay with per-player limits; the page in public carries fix set `9ac29719` like the applications | further work paused; the Safari stall; Firefox and Edge never run |
| Application and browser players in one game | 80 % | two and three players in step on one Mac ([mixed-arithmetic](issues/mixed-arithmetic.md)); one browser player is one entry in the application; the relay in public now passes datagrams between browser players and application players | never tried with real players on two networks |
| Sharper art (pictures enlarged four times) | 100 % | 122,205 of 122,231 dumped pictures enlarged (the other 26 are left out by rule); a sweep of the whole pack found no unreadable, mis-sized or mixed-up picture; interface art redone under a rule that keeps the game's shapes, fonts checked in the game | head pictures, busts and some skill icons were never dumped, so never judged |
| Native build: the game's code and its proof | 98 % | all 7,732 functions translated; 7,460 proven identical to the original, none failing; nine tours compared tick for tick; the two one-tick differences traced to the comparison's controller replay and re-measured on the build of 2026-10-20; shop, save point, load, level-up, deaths and restarts identical to the original in 15 play sessions, 83,952 ticks ([native-proof](issues/native-proof.md), round 3) | the workshop never reached; 226 functions without a comparable case |
| Native build: picture | 96 % | films, heat haze, fog, widescreen, the art pack; the renderer's processor side five times cheaper with the same output ([native-render-speed](issues/native-render-speed.md)); paced at exactly 60 pictures a second - in the heaviest level's fight 1,799 of 1,799 intervals on time at 640 x 448 and 1,788 of 1,798 at display resolution; an attack shows 75 to 84 ms after the press, the emulator application's 82 to 104 ([native-app](issues/native-app.md), section 11) | a person's eye on a lit display; effects compared close up; the new pacing in the Windows program |
| Native build: sound | 90 % | no gaps through ten level changes; film sound in step ([native-sound](issues/native-sound.md)) | somebody listening to it |
| Native build: online | 98 % | through the lobby with itself, with the emulator application and with a browser page, in step; three and four players with the window program (4 of 4 launches of four after a fix, up to 5,454 ticks every pair, with level change, deaths and reload); private games, chat, friends, kick, leaving and playing again nine games in a row, a dropped player and a dropped host ([native-online](issues/native-online.md)) | a second computer; a person at the controls; one host thread left behind per ended game thread |
| Native build: Windows | 92 % | run for the first time on Windows (2026-10-20, Windows 11 in a virtual machine on the Mac, the x86-64 programs under Windows' emulation): floating-point table, boot check, a headless play run and the PNG check give the Mac's figures; the window program draws (with a software OpenGL); a Windows copy and the Mac program 1,359 ticks in step in one room through a level change, 522 with the souls-style combat; the installer built a working program from a fresh folder after a one-line fix ([native-windows](issues/native-windows.md)) | a real PC: an Intel or AMD processor, a graphics driver, sound, a controller, a person playing; the lobby server and TLS on Windows |
| Native build: Linux | 75 % | builds for x86-64 and aarch64 from the same sources; floating-point table, boot check and rig comparison identical to the Mac; a Linux copy and the Mac program 1,163 ticks in step online through a level change; TLS through OpenSSL ([native-linux](issues/native-linux.md)) - all in an Ubuntu 24.04 container on the Mac | a real Linux desktop (GPU, sound, controller); an x86-64 online game; the public service |
| Native build: souls-style combat (optional, per room) | 60 % | lock-on, a dodge with invulnerable ticks, stamina for attacks, dodges, blocks and sprint, heavy attacks with the game's own hyper-armour, guard break, poise and stagger, tuned against community Elden Ring frame data; mode off byte-identical; two and three copies in step with it on through a fight, deaths and a reload ([native-souls-combat](issues/native-souls-combat.md)) | Windows, Linux and Godot wiring (in progress); the emulator application; nobody has played it |
| Native build: in a browser | 60 % - paused | boots and plays the first level in Chrome, tick-identical to the Mac build ([native-web](issues/native-web.md)) | paused with the browser work; rebuilt with the faster renderer; sound delay; online |
| Native build: first person and other views | 78 % | in the native program now (fix set `9ac29719`): five camera views on the game's own camera (key V), the simulation identical to overhead in every view; look with mouse or stick, the character facing the look, strafing switched on by itself in first person and shoulder; the character's own arms, weapon and spell effects in view, with the game's own animations, in both renderers (`view.first.body = off|arms|full`, [native-first-person-hands](issues/native-first-person-hands.md)) - a first-person strafing player and an overhead player 4,287 ticks in step through a level change; generated ceilings over dungeons, mines, caves and arenas, skirts beyond a level's rim, walls beside the eye no longer dropped; bows and spells fly where the player looks, pitch and heading, as an optional room option - two copies in step with it on over 17,695 ticks, mode off byte-identical ([native-first-person](issues/native-first-person.md), [native-first-person-controls](issues/native-first-person-controls.md), [native-first-person-world](issues/native-first-person-world.md)) | 7 of 111 levels still flagged at eye height (was 24; four of them look over a rim into the void, the levels' own design; [native-first-person-world](issues/native-first-person-world.md) 8.8); aiming by looking (a room option, [native-first-person-aim](issues/native-first-person-aim.md)) for Windows, Linux, Godot and the emulator application; thrown weapons and arrow skills never launched with it; far ground of cells never in reach of the texture stream; ceilings with the game's own textures and drawn in Godot; nobody has played it |
| Native build: inside Godot | 82 % | the translated game runs as a library under Godot 4.5.2; exact 3-D hand-over with the game's own normals (212 million vertices checked); the five views; Godot's light and shadows, sky continued to the zenith and distance haze in seven levels; 60 pictures a second paced in first person; a new interface drawn from the game's state with the game's own switched off (three layouts; 47 of 48 comparisons with the game's bars equal to the pixel); custom boss music from the player's own files ([native-godot](issues/native-godot.md), [native-hud](issues/native-hud.md)) | every level looked at; ceilings and torch lights; a real boss and a real second player; Windows; the regression checks re-run after the workspace move; nobody has played it |
| Portal and our own online service | 86 % | the portal's screens in Godot (first start, home, friends with presence and characters, rooms, settings), joined to the game scene ([native-portal](issues/native-portal.md)); a rendezvous service without accounts or passwords - friend codes, presence, invitations, rooms, hole punching with a relay fallback - 189 checks, its client 95 checks; running in public on the project's server since 2026-10-14, encrypted (TLS 1.3, certificate checked against the system's trust store), where two and three native copies played in step through it and its relay ([native-rendezvous-tls](issues/native-rendezvous-tls.md)); two, three and four native copies launched through it into one game from the title screen with no lobby and no account, in step through level changes, drops, a second game, forced relay and limits hit on purpose - 34 games on one computer ([native-rendezvous](issues/native-rendezvous.md), section 6); the Mac application in the same rooms, released 2026-10-14: application and native copies in one game through the public service, in step through a level change ([app-rendezvous](issues/app-rendezvous.md)) | the portal wired to the real service instead of its mock; a character brought from a memory card; arena modes and missions in the launch; *Play again* and the arena modes for the Mac application; TLS on Windows never run; two computers in two homes |

What "the game" is in each row: the first five rows run the original program in an
emulator; the "native build" rows run the game's own code translated to C++
([native-recomp](issues/native-recomp.md)), with no emulator. A hand-written C++ rebuild
and the Godot client are tracked in their own repositories
([REPOSITORIES.md](REPOSITORIES.md)) and are not counted here.

## Completed and verified

"Verified" here means: checked by test on one Apple-silicon Mac, with the evidence in the
linked document. It does not mean played by a person, or tried on two computers.

- **Release of 2026-10-13 (evening), fix set `9ac29719`** (31 sections, 189 words: the late level-entry save and strafe mode added to the 29 of the afternoon's `073064bb`): the Mac
  application, the stable build, the private download and the browser page all carry it.
  Two copies 12,348 lockstep frames in step through a save point, a jump gate and the
  game's own level change; three copies and four copies launched three times each, all in
  step; 60 pictures a second at the title and in the first level
  ([online-setup](online-setup.md), [issues/three-players](issues/three-players.md)).
- **The fix set itself**: 7.9 million lockstep ticks on the native build with no difference
  that reached a player, then 1.78 million more with the three newest sections
  ([issues/native-soak](issues/native-soak.md)).
- **Three- and four-player launches** from the lobby, both causes fixed
  ([issues/three-players](issues/three-players.md)).
- **The lobby server** with those fixes, and the browser relay with limits per player and
  the bridge to application players, running in public.
- **The art pack**: every dumped picture enlarged, the whole pack swept, interface art
  redone to keep the game's shapes.
- **The native build**: all 7,732 functions translated, 7,460 proven identical to the
  original, none failing; picture, films, sound, online play; paced at exactly 60 pictures
  a second; the Windows program builds from the same sources and gives byte-identical
  results on an x86-64 stand-in ([issues/native-proof](issues/native-proof.md),
  [issues/native-app](issues/native-app.md), [issues/native-windows](issues/native-windows.md)).
- **Camera views in the native build**: overhead, action, third person, shoulder and first
  person in seven levels and a fight; the simulation identical to overhead at every tick
  in every view; a first-person player with mouse look in step online with an overhead
  player for 1,819 ticks ([issues/native-first-person](issues/native-first-person.md)).

## In progress - pushed, not finished, not verified as a whole

- First-person and third-person **controls and combat**, the levels made to hold up from
  eye height (ceilings, skies), the **Godot** scene beyond the first level and at 60
  pictures a second, the **new interface**, the **portal** and our own online service, the
  Windows program on a real Windows computer. Their patches and notes are in the
  repository as work in progress; the table above gives each part's state.
- Never done by anyone yet: a session played by a person, two computers on two networks.

## Since the last update

- First online games between two different networks: a Mac at home hosting, a Mac on another network joining - four games, each about 4,300 ticks in step through a level change, punched straight through both routers (52-86 ms) and once forced through the server's relay.
- Godot: cleaner models (per-pixel shading, rim light, contact shadows, curved outlines near the camera); shops, dialogue, pause menu and bag draw correctly; ground under arena fighters; app exports for macOS, Windows and Linux with nothing of the game inside (macOS tested from a fresh folder); arena and versus games in the portal; memory-card characters (reader tested, a real import not yet).
- Godot: a lighting preset for every one of the 111 levels, colour balance fixed; the souls-style combat mode in Godot and the portal's room screen (two Godot copies 5,931 ticks in step through a fight); the new HUD in all five views with party frames, boss bar and stamina.
- Souls-style combat mode in the native program: lock-on, dodge, stamina, heavy attacks, guard break, poise - in step online.
- First person: all 111 levels walked at eye height (70 fine, 24 with small gaps), a crowd freeze fixed, far ground keeps its textures once seen.
- First person, every level at eye height again with a new measure (what is drawn, not how
  dark it is): 70 of 111 fine, 3 as in the game's own view, 24 with small gaps. `dismedal`
  no longer hangs the game (too many animated creatures in view). Textures of cells the game
  has unloaded are kept, so distant ground keeps its textures once it has been near. The
  ground near the feet no longer has chunk-sized holes. The simulation is unchanged
  ([native-first-person-world](issues/native-first-person-world.md) section 8.1 to 8.7).
- Linux: the native build runs on Linux (x86-64 and aarch64), identical to the Mac in every check, and played online with the Mac program in step.
- Godot: the 4x art pack is used (920 of 924 textures in a fight replaced, mip maps, 16x
  filtering, full-resolution picture); a heavy fight holds 60 pictures a second with the
  game's own textures (min 58.9) and averages 58 with the pack; the portal runs on the real
  room service - two Godot copies from friend request to launch, 1,851 ticks in step through a
  level change (local service; the public run waits on a network filter on the test Mac).
- Windows: first run on Windows 11 (virtual machine): every check gives the Mac's figures, a Windows copy and the Mac program in step online through a level change (with the souls-style combat too), and the one-step installer built a working program from a fresh folder.
- Boss music from the player's own files in the native program.
- First person: only forearms, hands, weapon and spell effects are in view now (worn
  armour, shoulders and legs left out, checked on six characters); the eye no longer pokes
  into walls; the ground near the eye keeps its textures. 108 of 111 levels walked at eye
  height: 62 fine, 3 fixed, 31 flagged (mostly dark levels; 2 confirmed faults), 12 have no
  single-player start ([native-first-person-world](issues/native-first-person-world.md) section 8).
- The Mac application's Room menu works from the lobby too; quitting after a room game no
  longer crashes.
- Release of the Mac application with the new *Room* menu (fix set `9ac29719` unchanged):
  host a room, read out the code, friends join - no lobby, no account, no sign-in - and
  Mac-application and native players play in one game. On the released build an
  application and a native copy played 2,657 ticks in step through the public room service
  and a level change; the *Online* menu (lobby, browser players) still reaches the public
  lobby as before. The private download carries it; the browser page is unchanged.
- The room service is encrypted now (TLS 1.3), with limits per address and per player for
  public use; two native copies played 2,119 ticks in step through it.
- First person shows the character's own arms, weapon and spell effects, animated by the
  game itself, in the native program and in Godot.
- Our own room service now runs in public on the project's server. From this Mac, two
  native copies played 2,104 ticks in step through it, and three copies with every route
  forced through its relay stayed in step too. Next: a Windows program in a virtual machine
  against a Mac copy, and two homes.
- Hands, weapon and spell effects in first person are being built.
- Our own online service: two, three and four native players get into one game through it -
  no lobby, no account, no password - and stay in step through level changes, drops and a
  forced relay (34 games on one computer).
- First person: generated ceilings over dungeons, mines, caves and arenas and skirts beyond
  a level's rim; walls beside the eye no longer vanish.
- Release on fix set `9ac29719` (31 sections, 189 words): the Mac application, the stable
  build, the private download and the browser page. New in it: the late level-entry save
  (a machine with a menu open at level entry saved late; a party wipe then reloaded
  different records - shown and fixed on two copies of the application) and strafe mode
  for first-person players of the native build.
- Our own online service gets two and three native copies into one game with no lobby and
  no account, in step.
- The working folder was moved out of an iCloud-synced Desktop and building and testing are
  restored there ([workspace-move](issues/workspace-move.md)).
