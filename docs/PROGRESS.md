# How complete is it

Updated at every check-in of the work. **Last update: 2026-10-17, 22:44 CDT.**

One table for the whole effort to make Champions: Return to Arms (SLUS-20973 v2.00)
playable again, online, on today's computers. The percentages are estimates by the people
doing the work, not measurements; each row says what it rests on and what is still missing
for 100 %. The evidence and the conditions behind every statement are in the documents
linked from [STATE-OF-PLAY.md](STATE-OF-PLAY.md).

Three limits hold for every row, as on that page: nothing has run on a PlayStation 2 or in
PCSX2; no two different computers have played together; nobody has yet sat down and played
a session by hand - every test drove the game by script, on one Apple-silicon Mac.
"Done" below therefore means: works and is verified by test on that Mac.

| Part | Done | Rests on | Still missing for 100 % |
|---|---|---|---|
| Mac application (the Play! emulator with this project's changes) | 98 % | 60 pictures a second at four times the resolution; the known picture faults fixed; every kind of screen looked at ([visual-check](issues/visual-check.md)); first-start faults fixed after the owner's own first start ([mac-app-start](issues/mac-app-start.md)); rolled out on fix set `9ac29719`; the release of 2026-10-14 adds the *Room* menu - rooms on our own service with no lobby or sign-in, the application and the native program in one game ([app-rendezvous](issues/app-rendezvous.md)) | a person playing a session through; a room driven from the menu by a person |
| Online, two players | 96 % | 7.9 million lockstep ticks on the suggested fix set with no difference that reached a player ([native-soak](issues/native-soak.md)); two copies through the game's own level change | two computers on two networks |
| Online, three and four players | 94 % | both causes of the failed launches found and fixed, one in the lobby server and one in the emulator ([three-players](issues/three-players.md)); on the rolled-out build three and four copies launch 3 of 3 times and stay in step | players behind a real router; a level change in a game of three or four |
| Browser version (the same emulator as WebAssembly) | 92 % | plays in Chrome and Brave, and in Safari's engine with a stall on arriving in a level ([browser-build](issues/browser-build.md)); relay with per-player limits; the page in public carries fix set `9ac29719` like the applications | further work paused; the Safari stall; Firefox and Edge never run |
| Application and browser players in one game | 80 % | two and three players in step on one Mac ([mixed-arithmetic](issues/mixed-arithmetic.md)); one browser player is one entry in the application; the relay in public now passes datagrams between browser players and application players | never tried with real players on two networks |
| Sharper art (pictures enlarged four times) | 100 % | 122,205 of 122,231 dumped pictures enlarged (the other 26 are left out by rule); a sweep of the whole pack found no unreadable, mis-sized or mixed-up picture; interface art redone under a rule that keeps the game's shapes, fonts checked in the game | head pictures, busts and some skill icons were never dumped, so never judged |
| Native build: the game's code and its proof | 97 % | all 7,732 functions translated; 7,460 proven identical to the original, none failing; nine sessions compared tick for tick ([native-proof](issues/native-proof.md)) | two unexplained one-tick differences; shop, save point, level-up and death compared |
| Native build: picture | 96 % | films, heat haze, fog, widescreen, the art pack; the renderer's processor side five times cheaper with the same output ([native-render-speed](issues/native-render-speed.md)); paced at exactly 60 pictures a second - in the heaviest level's fight 1,799 of 1,799 intervals on time at 640 x 448 and 1,788 of 1,798 at display resolution; an attack shows 75 to 84 ms after the press, the emulator application's 82 to 104 ([native-app](issues/native-app.md), section 11) | a person's eye on a lit display; effects compared close up; the new pacing in the Windows program |
| Native build: sound | 90 % | no gaps through ten level changes; film sound in step ([native-sound](issues/native-sound.md)) | somebody listening to it |
| Native build: online | 98 % | through the lobby with itself, with the emulator application and with a browser page, in step; three and four players with the window program (4 of 4 launches of four after a fix, up to 5,454 ticks every pair, with level change, deaths and reload); private games, chat, friends, kick, leaving and playing again nine games in a row, a dropped player and a dropped host ([native-online](issues/native-online.md)) | a second computer; a person at the controls; one host thread left behind per ended game thread |
| Native build: Windows | 85 % | compiles and links with picture, sound, controller and online play; the same sources built for x86-64 on the Mac give byte-identical results ([native-windows](issues/native-windows.md)) | a first run on a Windows computer |
| Native build: in a browser | 60 % - paused | boots and plays the first level in Chrome, tick-identical to the Mac build ([native-web](issues/native-web.md)) | paused with the browser work; rebuilt with the faster renderer; sound delay; online |
| Native build: first person and other views | 78 % | in the native program now (fix set `9ac29719`): five camera views on the game's own camera (key V), the simulation identical to overhead in every view; look with mouse or stick, the character facing the look, strafing switched on by itself in first person and shoulder; the character's own arms, weapon and spell effects in view, with the game's own animations, in both renderers (`view.first.body = off|arms|full`, [native-first-person-hands](issues/native-first-person-hands.md)) - a first-person strafing player and an overhead player 4,287 ticks in step through a level change; generated ceilings over dungeons, mines, caves and arenas, skirts beyond a level's rim, walls beside the eye no longer dropped ([native-first-person](issues/native-first-person.md), [native-first-person-controls](issues/native-first-person-controls.md), [native-first-person-world](issues/native-first-person-world.md)) | two levels with dark ground at eye height (nitdung3, obsidian); far ground in big levels loses textures sooner; ceilings with the game's own textures and drawn in Godot; distant ground in big levels (the game keeps only nine texture cells); 92 of 111 levels never looked at; nobody has played it |
| Native build: inside Godot | 60 % | the translated game runs as a library under Godot 4.5.2; exact 3-D hand-over with the game's own normals (212 million vertices checked); the five views; Godot's light and shadows, sky continued to the zenith and distance haze in seven levels; 60 pictures a second paced in first person; a new interface drawn from the game's state with the game's own switched off (three layouts; 47 of 48 comparisons with the game's bars equal to the pixel); custom boss music from the player's own files ([native-godot](issues/native-godot.md), [native-hud](issues/native-hud.md)) | every level looked at; ceilings and torch lights; a real boss and a real second player; Windows; the regression checks re-run after the workspace move; nobody has played it |
| Portal and our own online service | 82 % | the portal's screens in Godot (first start, home, friends with presence and characters, rooms, settings), joined to the game scene ([native-portal](issues/native-portal.md)); a rendezvous service without accounts or passwords - friend codes, presence, invitations, rooms, hole punching with a relay fallback - 189 checks, its client 95 checks; running in public on the project's server since 2026-10-14, encrypted (TLS 1.3, certificate checked against the system's trust store), where two and three native copies played in step through it and its relay ([native-rendezvous-tls](issues/native-rendezvous-tls.md)); two, three and four native copies launched through it into one game from the title screen with no lobby and no account, in step through level changes, drops, a second game, forced relay and limits hit on purpose - 34 games on one computer ([native-rendezvous](issues/native-rendezvous.md), section 6); the Mac application in the same rooms, released 2026-10-14: application and native copies in one game through the public service, in step through a level change ([app-rendezvous](issues/app-rendezvous.md)) | the portal wired to the real service instead of its mock; a character brought from a memory card; arena modes and missions in the launch; *Play again* and the arena modes for the Mac application; TLS on Windows never run; two computers in two homes |

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
