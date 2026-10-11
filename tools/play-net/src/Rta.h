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
