# Which version can I get

Updated with each release. **Last update: 2026-10-13.** How complete each one is:
[PROGRESS.md](PROGRESS.md).

Every version needs your own disc image of the game (the US release, SLUS-20973, version
2.00). No version contains anything of the game, and none needs a PlayStation 2 BIOS.

| Version | For | State | Current build | How to get it |
|---|---|---|---|---|
| **Mac application** (the Play! emulator with this project's changes) | a Mac with Apple silicon, macOS 14 or later | released; playable, online for two to four players | 2026-10-13, fix set `073064bb` (29 sections) | build it from this repository: [tools/play-net](../tools/play-net/README.md) (`build.sh`, then `package.sh`); ready-made builds are handed out privately by the project's owner |
| **Browser version** (the same emulator as WebAssembly) | Windows or any computer with Chrome; plays in the same online games as the Mac application | released; further work paused | 2026-10-13, fix set `073064bb` | build and serve it yourself: [tools/play-web](../tools/play-web/README.md); the project's own page is private |
| **Native build for Mac** (the game's code translated to C++, no emulator) | a Mac with Apple silicon | experimental; plays offline and online | follows the repository | build from this repository with your own disc: [issues/native-recomp.md](issues/native-recomp.md), [issues/native-app.md](issues/native-app.md) |
| **Native build for Windows** | Windows 10 or later, 64-bit | experimental; builds, never run on a Windows computer | follows the repository | [issues/native-windows.md](issues/native-windows.md) |
| **Native build in Godot** (first person and other views, new interface, portal) | Mac first, then Windows | in development; nothing to download yet | - | [issues/native-godot.md](issues/native-godot.md), [issues/native-first-person.md](issues/native-first-person.md) |

Two things to know before you start:

- **Everyone in one online game needs the same fix set.** The application shows its figure
  under *Online → Server, player, patch set...*; a copy with another figure is warned
  about in the room. The current one is `073064bb`.
- **Why there is no public download button here.** The ready-made application the owner
  shares is set up for his own lobby server and carries a small sign-in file that is not
  part of this repository, and the native builds contain code generated from the game on
  the builder's own machine. What is public is everything needed to build each version
  yourself from your own disc.

To play online you also need a lobby server: [online-setup.md](online-setup.md) and
[play-online.md](play-online.md).
