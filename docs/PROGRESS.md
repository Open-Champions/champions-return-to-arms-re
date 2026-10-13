# How complete is it

Updated at every check-in of the work. **Last update: 2026-10-13, 13:22 CDT.**

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
| Browser version (the same emulator as WebAssembly) | 92 % - paused | plays in Chrome and Brave, and in Safari's engine with a stall on arriving in a level ([browser-build](issues/browser-build.md)); relay with per-player limits; the page in public is on the earlier fix set `27f61e1d`, a newer page is built and tested but not rolled out | work paused on the owner's instruction; the Safari stall; Firefox and Edge never run |
| Application and browser players in one game | 75 % - paused | two and three players in step on one Mac ([mixed-arithmetic](issues/mixed-arithmetic.md)); one browser player is one entry in the application | paused with the browser work; a relay in public that passes datagrams to players outside it |
| Sharper art (pictures enlarged four times) | 100 % | 122,205 of 122,231 dumped pictures enlarged (the other 26 are left out by rule); a sweep of the whole pack found no unreadable, mis-sized or mixed-up picture; interface art redone under a rule that keeps the game's shapes, fonts checked in the game | head pictures, busts and some skill icons were never dumped, so never judged |
| Native build: the game's code and its proof | 97 % | all 7,732 functions translated; 7,460 proven identical to the original, none failing; nine sessions compared tick for tick ([native-proof](issues/native-proof.md)) | two unexplained one-tick differences; shop, save point, level-up and death compared |
| Native build: picture | 96 % | films, heat haze, fog, widescreen, the art pack; the renderer's processor side five times cheaper with the same output ([native-render-speed](issues/native-render-speed.md)); paced at exactly 60 pictures a second - in the heaviest level's fight 1,799 of 1,799 intervals on time at 640 x 448 and 1,788 of 1,798 at display resolution; an attack shows 75 to 84 ms after the press, the emulator application's 82 to 104 ([native-app](issues/native-app.md), section 11) | a person's eye on a lit display; effects compared close up; the new pacing in the Windows program |
| Native build: sound | 90 % | no gaps through ten level changes; film sound in step ([native-sound](issues/native-sound.md)) | somebody listening to it |
| Native build: online | 98 % | through the lobby with itself, with the emulator application and with a browser page, in step; three and four players with the window program (4 of 4 launches of four after a fix, up to 5,454 ticks every pair, with level change, deaths and reload); private games, chat, friends, kick, leaving and playing again nine games in a row, a dropped player and a dropped host ([native-online](issues/native-online.md)) | a second computer; a person at the controls; one host thread left behind per ended game thread |
| Native build: Windows | 85 % | compiles and links with picture, sound, controller and online play; the same sources built for x86-64 on the Mac give byte-identical results ([native-windows](issues/native-windows.md)) | a first run on a Windows computer |
| Native build: in a browser | 60 % - paused | boots and plays the first level in Chrome, tick-identical to the Mac build ([native-web](issues/native-web.md)) | paused with the browser work; rebuilt with the faster renderer; sound delay; online |
| Native build: first person and other views | started | the main effort from 2026-10-13: view modes as hooks on the game's own camera (overhead, action, third person, shoulder, first person), the levels made to hold up from eye height, controls and combat for those views, a new interface | everything; notes will be in issues/native-first-person*.md and issues/native-hud.md |
| Native build: inside Godot | 35 % | a first spike on Godot 4.5.2: the translated game runs as a library under Godot, which does window, input and sound (same result as the stand-alone program in the tick comparison, pictures identical); Godot draws every frame itself (within 3 of 255 of the game's own picture); on the first level the scene is handed over in 3-D and Godot adds real-time shadows, a light of its own and a free camera; a macOS application exported ([native-godot](issues/native-godot.md)) | 60 pictures a second with Godot drawing (75 unpaced so far); the 3-D scene beyond the first level; the game's culling widened for a free camera; online; Windows |

What "the game" is in each row: the first five rows run the original program in an
emulator; the "native build" rows run the game's own code translated to C++
([native-recomp](issues/native-recomp.md)), with no emulator. A hand-written C++ rebuild
and the Godot client are tracked in their own repositories
([REPOSITORIES.md](REPOSITORIES.md)) and are not counted here.

## Since the last update

- Release on fix set `073064bb` (29 sections, 99 words: three sections added - a save point,
  a script read that wrote, a jump gate): the Mac application, the stable build and the
  private download. On it: two copies 12,348 lockstep frames in step with a save point and
  a jump gate; three copies and four copies launched three times each, all in step.
- The Mac application now starts with its window at once, finds the disc image and the
  art pack in its own folder without macOS asking anything, and asks for the player name
  in a sheet that cannot be lost.
- Main effort from today: the native game on Mac and Windows, in C++ with Godot as the
  layer that draws the new look - first person and several camera views, cleaner models,
  a new interface. Browser work is paused.
- The art pack checked as a whole; interface pictures redone to keep the game's shapes.
