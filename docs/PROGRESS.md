# How complete is it

Updated at every check-in of the work. **Last update: 2026-10-13, 19:23 CDT.**

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
| Mac application (the Play! emulator with this project's changes) | 98 % | 60 pictures a second at four times the resolution; the known picture faults fixed; every kind of screen looked at ([visual-check](issues/visual-check.md)); first-start faults fixed after the owner's own first start ([mac-app-start](issues/mac-app-start.md)); rolled out on fix set `073064bb` | a person playing a session through |
| Online, two players | 96 % | 7.9 million lockstep ticks on the suggested fix set with no difference that reached a player ([native-soak](issues/native-soak.md)); two copies through the game's own level change | two computers on two networks |
| Online, three and four players | 94 % | both causes of the failed launches found and fixed, one in the lobby server and one in the emulator ([three-players](issues/three-players.md)); on the rolled-out build three and four copies launch 3 of 3 times and stay in step | players behind a real router; a level change in a game of three or four |
| Browser version (the same emulator as WebAssembly) | 92 % | plays in Chrome and Brave, and in Safari's engine with a stall on arriving in a level ([browser-build](issues/browser-build.md)); relay with per-player limits; the page in public carries fix set `073064bb` like the applications | further work paused; the Safari stall; Firefox and Edge never run |
| Application and browser players in one game | 80 % | two and three players in step on one Mac ([mixed-arithmetic](issues/mixed-arithmetic.md)); one browser player is one entry in the application; the relay in public now passes datagrams between browser players and application players | never tried with real players on two networks |
| Sharper art (pictures enlarged four times) | 100 % | 122,205 of 122,231 dumped pictures enlarged (the other 26 are left out by rule); a sweep of the whole pack found no unreadable, mis-sized or mixed-up picture; interface art redone under a rule that keeps the game's shapes, fonts checked in the game | head pictures, busts and some skill icons were never dumped, so never judged |
| Native build: the game's code and its proof | 97 % | all 7,732 functions translated; 7,460 proven identical to the original, none failing; nine sessions compared tick for tick ([native-proof](issues/native-proof.md)) | two unexplained one-tick differences; shop, save point, level-up and death compared |
| Native build: picture | 96 % | films, heat haze, fog, widescreen, the art pack; the renderer's processor side five times cheaper with the same output ([native-render-speed](issues/native-render-speed.md)); paced at exactly 60 pictures a second - in the heaviest level's fight 1,799 of 1,799 intervals on time at 640 x 448 and 1,788 of 1,798 at display resolution; an attack shows 75 to 84 ms after the press, the emulator application's 82 to 104 ([native-app](issues/native-app.md), section 11) | a person's eye on a lit display; effects compared close up; the new pacing in the Windows program |
| Native build: sound | 90 % | no gaps through ten level changes; film sound in step ([native-sound](issues/native-sound.md)) | somebody listening to it |
| Native build: online | 98 % | through the lobby with itself, with the emulator application and with a browser page, in step; three and four players with the window program (4 of 4 launches of four after a fix, up to 5,454 ticks every pair, with level change, deaths and reload); private games, chat, friends, kick, leaving and playing again nine games in a row, a dropped player and a dropped host ([native-online](issues/native-online.md)) | a second computer; a person at the controls; one host thread left behind per ended game thread |
| Native build: Windows | 85 % | compiles and links with picture, sound, controller and online play; the same sources built for x86-64 on the Mac give byte-identical results ([native-windows](issues/native-windows.md)) | a first run on a Windows computer |
| Native build: in a browser | 60 % - paused | boots and plays the first level in Chrome, tick-identical to the Mac build ([native-web](issues/native-web.md)) | paused with the browser work; rebuilt with the faster renderer; sound delay; online |
| Native build: first person and other views | 50 % | five camera views as hooks on the game's own camera, merged into the native program (key V), the simulation identical to overhead in every view ([native-first-person](issues/native-first-person.md)); look with mouse or stick, the character turned to face the look, a strike held until it faces its target; a first-person player in step online with an overhead player through an arena fight; strafing written as a fix section and proven on 4.1 million ticks, not yet in the fix set ([native-first-person-controls](issues/native-first-person-controls.md)); what every level lacks from eye height, measured ([native-first-person-world](issues/native-first-person-world.md)) | ceilings for indoor levels; weapon and hands in view; strafing released; nobody has played it |
| Native build: inside Godot | 60 % | the translated game runs as a library under Godot 4.5.2; exact 3-D hand-over with the game's own normals (212 million vertices checked); the five views; Godot's light and shadows, sky continued to the zenith and distance haze in seven levels; 60 pictures a second paced in first person; a new interface drawn from the game's state with the game's own switched off (three layouts; 47 of 48 comparisons with the game's bars equal to the pixel); custom boss music from the player's own files ([native-godot](issues/native-godot.md), [native-hud](issues/native-hud.md)) | every level looked at; ceilings and torch lights; a real boss and a real second player; Windows; the regression checks re-run after the workspace move; nobody has played it |
| Portal and our own online service | 55 % | the portal's screens in Godot (first start, home, friends with presence and characters, rooms, settings), joined to the game scene ([native-portal](issues/native-portal.md)); a rendezvous service without accounts or passwords - friend codes, presence, invitations, rooms, hole punching with a relay fallback - 189 checks, and its client, 95 checks, on one computer ([native-rendezvous](issues/native-rendezvous.md)) | a game actually launched from a room; the portal wired to the real service instead of its mock; the service running anywhere but this Mac |

What "the game" is in each row: the first five rows run the original program in an
emulator; the "native build" rows run the game's own code translated to C++
([native-recomp](issues/native-recomp.md)), with no emulator. A hand-written C++ rebuild
and the Godot client are tracked in their own repositories
([REPOSITORIES.md](REPOSITORIES.md)) and are not counted here.

## Completed and verified

"Verified" here means: checked by test on one Apple-silicon Mac, with the evidence in the
linked document. It does not mean played by a person, or tried on two computers.

- **Release of 2026-10-13, fix set `073064bb`** (29 sections, 99 words): the Mac
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

- The project's working folder was moved out of an iCloud-synced Desktop after macOS began
  evicting its files when the disk filled ([workspace-move](issues/workspace-move.md), being
  written); building and testing are being restored in the new place.
- Strafing: soaked for 4.1 million ticks with no difference of its own. The soak found a
  desync in the released set instead - a level entered with a menu open saves late, and a
  party wipe then reloads different records - and a six-word section for it, proven on 2.9
  million ticks. Both are being verified on the emulator for the next release.
- Godot: skies and haze in seven levels, the new interface in the scene, the portal as the
  first screen, 60 pictures a second paced in first person.
- Our own online service and its client are written and pass their checks on one computer.
