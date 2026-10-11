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
#include <string>
#include "PadHandler.h"

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
