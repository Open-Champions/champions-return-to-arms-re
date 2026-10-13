# How complete is it

Updated at every check-in of the work. **Last update: 2026-10-13, 07:52 CDT.**

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
| Mac application (the Play! emulator with this project's changes) | 97 % | 60 pictures a second at four times the resolution; the known picture faults fixed; every kind of screen looked at ([visual-check](issues/visual-check.md)) | a person playing it; the newest build rolled out |
| Online, two players | 96 % | 7.9 million lockstep ticks on the suggested fix set with no difference that reached a player ([native-soak](issues/native-soak.md)); two copies through the game's own level change | two computers on two networks |
| Online, three and four players | 92 % | both causes of the failed launches found and fixed, one in the lobby server and one in the emulator ([three-players](issues/three-players.md)); three and four copies launch 3 of 3 times and stay in step | players behind a real router; the newest build rolled out |
| Browser version (the same emulator as WebAssembly) | 90 % | plays in Chrome and Brave, and in Safari's engine with a stall on arriving in a level ([browser-build](issues/browser-build.md)); relay with per-player limits | the Safari stall; Firefox and Edge never run |
| Application and browser players in one game | 75 % | two and three players in step on one Mac ([mixed-arithmetic](issues/mixed-arithmetic.md)) | a relay in public that passes datagrams to players outside it |
| Sharper art (pictures enlarged four times) | 99 % | 122,205 of 122,231 dumped pictures enlarged | the large interface pages and the fonts checked by eye |
| Native build: the game's code and its proof | 97 % | all 7,732 functions translated; 7,460 proven identical to the original, none failing; nine sessions compared tick for tick ([native-proof](issues/native-proof.md)) | two unexplained one-tick differences; shop, save point, level-up and death compared |
| Native build: picture | 96 % | films, heat haze, fog, widescreen, the art pack; the renderer's processor side five times cheaper with the same output ([native-render-speed](issues/native-render-speed.md)); paced at exactly 60 pictures a second - in the heaviest level's fight 1,799 of 1,799 intervals on time at 640 x 448 and 1,788 of 1,798 at display resolution; an attack shows 75 to 84 ms after the press, the emulator application's 82 to 104 ([native-app](issues/native-app.md), section 11) | a person's eye on a lit display; effects compared close up; the new pacing in the Windows program |
| Native build: sound | 90 % | no gaps through ten level changes; film sound in step ([native-sound](issues/native-sound.md)) | somebody listening to it |
| Native build: online | 95 % | through the lobby with itself and with the emulator application, in step ([native-online](issues/native-online.md)) | private games, chat, leaving and coming back; three and four players in the window program |
| Native build: Windows | 85 % | compiles and links with picture, sound, controller and online play; the same sources built for x86-64 on the Mac give byte-identical results ([native-windows](issues/native-windows.md)) | a first run on a Windows computer |
| Native build: in a browser | 60 % | boots and plays the first level in Chrome, tick-identical to the Mac build ([native-web](issues/native-web.md)) | rebuilt with the faster renderer; sound delay; online |
| Native build: inside Godot | started | the translated game as the game logic under Godot, which does window, input, sound and drawing | everything; notes will be in issues/native-godot.md |

What "the game" is in each row: the first five rows run the original program in an
emulator; the "native build" rows run the game's own code translated to C++
([native-recomp](issues/native-recomp.md)), with no emulator. A hand-written C++ rebuild
and the Godot client are tracked in their own repositories
([REPOSITORIES.md](REPOSITORIES.md)) and are not counted here.

## Since the last update

- The native build now holds exactly 60 pictures a second when paced, and its input delay
  is one picture shorter than before - no longer behind the emulator application.
- Two faults fixed in the native build: controller replay through a level load, and a
  wide-picture layout fault after a texture is sent again.
- The Windows folder rebuilt with the faster renderer (still never run on Windows).
- A progress page (this one) added and linked from the README.
