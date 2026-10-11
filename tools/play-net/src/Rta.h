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

#include <string>
#include "PadHandler.h"

class CPS2VM;
class QCommandLineParser;

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

	// RtaMac.mm: keeps macOS from slowing the application down when its window is
	// covered or in the background (the other players wait for every frame of ours).
	void KeepAwake();
}
