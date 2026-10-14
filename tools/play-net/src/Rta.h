// Champions: Return to Arms online, inside Play!'s desktop application.
//
// What this adds to the application (tools/play-net/README.md has the whole picture):
//   - a network behind the emulated Ethernet adaptor (RtaNet.h), so that the game's own
//     network stack reaches a lobby server and the other players;
//   - PCSX2-style patch files applied to the game while it runs;
//   - the network setting the game asks for, written to the emulated memory card;
//   - optionally a control socket, for driving the application from a test script.
//
// The application calls the functions below at five places (see play-net.patch).
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include "PadHandler.h"
#include "sound/SoundHandler.h"

class CPS2VM;
class QCommandLineParser;
class QWidget;

namespace Rta
{
	// First thing in main(): takes the data directory from the command line, because the
	// application reads its settings from there before it parses anything.
	void EarlyInit(int argc, char** argv);
	void AddCommandLineOptions(QCommandLineParser&);
	void ReadCommandLine(const QCommandLineParser&);
	// After the application has registered its own settings.
	void OverridePreferences();
	// The application's pad handler with a hook at every vertical blank.
	CPadHandler::FactoryFunction GetPadHandlerFactory();
	// After the machine and its pad handler exist; before anything is booted.
	void Attach(CPS2VM*);
	// Before the machine is destroyed.
	void Detach();
	// One line for the status bar; empty when there is nothing to say.
	std::string StatusText();
	// Around the main window's first show(), and for every title it is given. With
	// --rta-test the window says in its title that it is a test and what is switched
	// off in it, is small, and neither comes to the front nor takes the keyboard.
	void BeforeShow(QWidget*);
	void AfterShow(QWidget*);
	std::string WindowTitle(const std::string&);
	void LogLine(const std::string&);
	// menus and the first-run note
	void SetupWindow(QWidget*);
	// started with --rta-test, --rta-title or a control socket
	bool IsTestRun();

	// RtaSound.cpp: the sound handler (keeps a set reserve of sound queued; counts every
	// time the output ran dry or a block was thrown away; can write what the machine
	// hands over to a WAV file). SoundReport: one line of counts, optionally starting anew.
	void ConfigureSound(bool wav, bool plain, bool muted, const std::string& directory);
	CSoundHandler::FactoryFunction GetSoundHandlerFactory();
	std::string SoundReport(bool reset);

	// RtaPad.mm: the first game controller macOS knows (DualSense, DualShock 4, Xbox,
	// Switch Pro ...) as the pad in port 1, with nothing to bind. Buttons are bits by
	// PS2::CControllerInfo::BUTTON; a stick is two bytes, 128 128 in the middle.
	struct PadState
	{
		bool attached = false;
		uint32_t generation = 0; // changes when a controller is attached or detached
		uint32_t buttons = 0;
		uint8_t stick[2][2] = {{128, 128}, {128, 128}};
		bool stickSet[2] = {false, false}; // false: at rest (the keyboard has the stick)
	};
	void StartGamePads();
	PadState GamePadState();
	std::string GamePadName();
	// tests: "connect" / "disconnect" a controller made by the program, "set" its buttons
	// (bits as above), sticks (four values -1 .. 1, up and right positive) and triggers
	// (two values 0 .. 1)
	void GamePadTest(const std::string& command, uint32_t buttons, const float values[6]);

	// RtaUi.cpp: the keys and the controller's buttons, as a window (Help menu)
	void ShowControls(QWidget* parent);
	// true once per data directory when this build's keyboard layout is newer than the
	// one stored there
	bool TakeKeyboardDefaults();

	// ---- the packaged application (tools/play-net/package.sh) ---------------------------
	// An application bundle that has our patch file in Contents/Resources/rta needs no
	// command line: its data is in ~/Library/Application Support/<bundle name>/player<N>,
	// it finds the disc image by itself and remembers it, and the lobby server's address and
	// the player number are set in a dialog (kept in launch.ini beside the player
	// directories). What launch.ini does not say is taken from defaults.ini beside the
	// patch file, when package.sh was told to write one (server, online).
	struct LaunchInfo
	{
		bool packaged = false;
		std::string root;       // ~/Library/Application Support/<name>
		int player = 1;
		std::string server;     // as stored, else the bundle's default; empty: this computer
		std::string disc;       // as stored
		std::string patchSet;   // "19 sections, 152 words, set xxxxxxxx", or empty
		bool gameChecked = false; // the game is loaded and is the version the patches are for
		std::string signinPatch;  // the sign-in patch that is used, or empty
		std::string signinPlaces; // where it is looked for, one per line
		std::string serverNow;    // the server this run talks to, in words
	};
	LaunchInfo GetLaunchInfo();
	void SaveLaunch(const std::string& server, int player);
	// starts the application again (a moment later) and ends this one
	void Relaunch();
	// empty when the file is a disc image of the game in the version this is for;
	// otherwise what is wrong with it, for a person
	std::string CheckDisc(const std::string& path);
	// The disc image, looked for without any dialog: beside the application, inside it,
	// in its data, then in Downloads, Desktop and Documents (and one level of their
	// sub-folders). Any file that passes CheckDisc, whatever its name. Empty: none.
	std::string FindDisc();
	// RtaUi.cpp. The disc image to start with: the one given, else the one remembered,
	// else the one FindDisc finds; only when there is none, one window that says where
	// to put the file (Retry, Browse). 'askAnew' (the menu): the file dialog at once.
	// Refuses anything CheckDisc does. Empty: none (not a packaged application, or the
	// person left it for later).
	std::string ChooseDisc(QWidget* parent, const std::string& given, bool askAnew);
	// how the application starts a disc image (set by main), and the starting itself
	void SetDiscBoot(const std::function<void(const std::string&)>&);
	void BootDisc(const std::string& path);
	void ShowOnline(QWidget* parent);

	// ---- one-step online (RtaOnline.h) -------------------------------------------------
	// The application presses its own way from the title screen to the lobby: Start New
	// Game, Internet Game, the network setting, the server's terms, the log-in. The
	// account is its business: it asks for a player name once, makes the password itself
	// and keeps the pair per server in the data directory.
	// mode: "lobby" (or empty), "host", "host:CODE", "join:CODE". False: not started, and why.
	bool OnlineStart(const std::string& mode, std::string& error);
	void OnlineStop();
	bool OnlineActive();
	// the answer to AskPlayerName; empty: none given
	void OnlineGiveName(const std::string& name);
	// empty: fine; otherwise what is wrong with it, for a person
	std::string OnlineCheckName(const std::string& name);
	std::string OnlineCheckCode(const std::string& code);
	// the player name saved for the server this run talks to; empty: none
	std::string OnlineSavedName();
	// the character this player used last on that server (its name); empty: none known
	std::string OnlineLastCharacter();
	// the code of the game being hosted or joined; empty: none
	std::string OnlineCode();
	bool OnlineForget();
	// the packaged application: go online by itself when it starts (on unless switched off)
	bool OnlineAtStart();
	void SetOnlineAtStart(bool);
	// RtaUi.cpp: the dialog for the player name. 'why' is empty the first time and says
	// what was wrong with the last name otherwise.
	void AskPlayerName(const std::string& why);

	// A room of our own rendezvous service (RtaRoom.h, docs/issues/app-rendezvous.md): the
	// same rooms as the native program's, by code, with no lobby, account or password.
	// RoomWant takes "host", "host:friends" or "join:CODE"; the name is used only at the very
	// first start in this data directory (RoomNeedsName), when the identity file is made.
	bool RoomNeedsName();
	std::string RoomCheckName(const std::string& name);
	std::string RoomCheckCode(const std::string& code);
	bool RoomWant(const std::string& what, const std::string& name, std::string& error);
	void RoomLeave();
	bool RoomStart(std::string& error);
	std::string RoomCode();
	std::string RoomNote();
	// what the menu Room shows: busy - a room is on its way (Host and Join greyed); the code
	// when in one; canStart - Start the game is taken now, else startText says why not;
	// inLevel - a room now starts the game again from the disc
	struct RoomMenu
	{
		bool open = false, busy = false, inRoom = false, host = false, canStart = false, inLevel = false;
		std::string code, text, startText;
	};
	RoomMenu RoomMenuState();
	// the application's own thread (RtaUi.cpp)
	void AskRoomName(const std::string& want);
	void ShowRoomCode(const std::string& code);
	// RtaUi.cpp: a window with the code of the game this copy hosts, large
	void ShowGameCode(const std::string& code);
	// RtaUi.cpp: a window that says that another player has a different patch set (it
	// does not stop the game)
	void WarnPatchSet(const std::string& text);
	// what the one-step log-in is doing, as the status bar says it
	std::string OnlineNote();
	bool RenderDialog(const std::string& name, const std::string& path);
	// for the About box
	std::string AboutText();

	// ---- when the game or the machine has stopped ---------------------------------------
	// The application watches that the machine draws (a game that draws nothing for ten
	// seconds is stuck: the status bar says so) and that the machine's own thread comes
	// round. The main window calls these before its Reset, on Escape outside full screen,
	// and before it closes. BeforeReset and BeforeClose answer true when the machine's
	// thread does not come round: nothing that waits for it may then be called, and the
	// application ends there (BeforeReset asks first, and starts it again).
	bool BeforeReset(QWidget* parent);
	bool BeforeClose();
	void EscapePressed();
	// RtaUi.cpp: the main window's own Reset entry, as if chosen in the menu
	void TriggerReset();
	// the control socket's path; empty: none
	std::string ControlPath();

	// ---- folders macOS guards, and what the window says meanwhile -------------------------
	// (docs/issues/mac-app-start.md.) macOS stops a program inside open() or opendir()
	// of anything under Desktop, Documents or Downloads until the person has answered its
	// question about that folder - for minutes, if the question is overlooked. So nothing
	// of that kind is opened on the application's own thread: the art pack's folder is
	// listed by a thread of its own once the game is loaded, and a disc image is opened
	// for the first time by a thread of its own while the window stays alive. The window
	// says in plain words what is being waited for (a line across its top, and the status
	// bar), and what could not be read is tried again every two seconds.
	//
	// What the window says now; empty: nothing. Any thread.
	std::string Notice();
	// A standing sentence under a key ("disc", "textures"); an empty text takes it away.
	void SetNotice(const std::string& key, const std::string& text);
	// Opens a file or a folder once for reading and closes it again: 0, or errno. This is
	// the call macOS may hold; never on the application's own thread. 'what' says what is
	// there, for the sentence in the window ("your disc image", "the art pack").
	int ProbeReadable(const std::string& path, const std::string& what);
	// "the Desktop folder" for a path under Desktop, Documents or Downloads; else empty
	std::string GuardedFolderOf(const std::string& path);
	// the sentence for a file or folder that may not be read (errno EACCES or EPERM)
	std::string DeniedText(const std::string& path, const std::string& what, int error);
	// RtaUi.cpp: waits, with the windows alive, until 'path' can be opened for reading.
	// False: it is not there ('error' is then ENOENT or what else open() said), the
	// application is ending, or another image was chosen (error 0). Not even the
	// question "is it there" is put to the file system on the application's own thread.
	bool WaitReadable(QWidget* parent, const std::string& path, const std::string& what, int* error = nullptr);
	// RtaUi.cpp: a disc image named on the command line (play.sh): started once readable
	void BootDiscWhenReadable(QWidget* parent, const std::string& path);
	// RtaUi.cpp: the person closed the application while it was waiting for a folder
	bool Quitting();
	// vertical blanks of the machine so far
	uint64_t FrameCount();

	// ---- tests of our own windows without a screen (--rta-test-dialogs) -------------------
	// 0: a test run shows none of our dialogs (the name comes from the control socket);
	// 1: they are shown as for a person, behind the other windows and never active;
	// 2: the same, built and opened as the release of 2026-10-13 morning did (for showing
	// what went wrong there). The control socket's "ui ..." reads and works them.
	int TestDialogs();
	// RtaUi.cpp, the application's own thread: "windows", "main info|raise", "notice",
	// "name info|type TEXT|press ok|notnow|escape|close", "controls info|show|close"
	std::string UiCommand(const std::string& command);
	// RtaMac.mm: this application's windows on the screen, front to back, as AppKit has them
	std::string WindowOrder();

	// RtaMac.mm
	std::string BundlePath();
	std::string BundleResourcePath();
	std::string BundleName();
	std::string ApplicationSupportPath();

	// RtaMac.mm: an application without a Dock icon that is never made the active one,
	// and its window behind every other.
	void MakeBackgroundApplication();
	void SendWindowBack(void* nsView);

	// RtaMac.mm: keeps macOS from slowing the application down when its window is
	// covered or in the background (the other players wait for every frame of ours).
	void KeepAwake();
	// RtaMac.mm: the display's refreshes as the clock for frames and pictures.
	void StartDisplayClock();
	double DisplayRefreshRate();
	int DisplayRefreshesPerFrame();
	bool WaitForFrameStart(uint32_t framesPerSecond);
	uint64_t PresentMark();
	void WaitForPresentMark(uint64_t mark);
}
