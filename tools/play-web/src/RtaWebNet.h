// play-web: online play from a browser. See RtaWebNet.cpp.
//
// Nothing here does anything on a page that has no relay (rtaOnlineSetup was not called):
// the machine then has an Ethernet adaptor with no cable, as before.
#pragma once

#include <cstdint>

class CPS2VM;

namespace RtaWebNet
{
	// the page has a relay
	bool Configured();
	// before the game is booted: the patch set of this copy (told to the other players)
	void SetPatchSet(uint32_t hash, uint16_t words);
	// once the machine exists and its files have their places: the network setting on the
	// memory card
	void PrepareCard();
	// machine thread, when the machine has been made: the Ethernet adaptor's two hooks
	void Attach(CPS2VM* vm);
	// machine thread: a new program was loaded
	void OnExecutable(bool isGame);
	// machine thread, every vertical blank; 'buttons' is what the player holds
	void OnVBlank(uint8_t* ram, uint32_t ramSize, bool isGame, uint32_t buttons);
	// machine thread: while true the page's own presses are held back and Buttons() are
	// the game's
	bool Driving();
	uint32_t Buttons();
}
