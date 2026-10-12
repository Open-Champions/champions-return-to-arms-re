// play-web: online play from a browser. See RtaWebNet.cpp.
#pragma once

#include <cstdint>

class CPS2VM;

namespace RtaWebNet
{
	// before the machine is made: the patch set of this copy (told to the other players)
	void SetPatchSet(uint32_t hash, uint16_t words);
	// main thread helper thread, once the machine exists and its files have their places:
	// the network setting on the memory card
	void PrepareCard();
	// machine thread, when the machine has been made: the Ethernet adaptor's two hooks
	void Attach(CPS2VM* vm);
	// machine thread: a new program was loaded
	void OnExecutable(bool isGame);
	// machine thread, every vertical blank; 'buttons' is what the player holds
	void OnVBlank(uint8_t* ram, uint32_t ramSize, bool isGame, uint32_t buttons);
	// machine thread: the page's own presses are held back and these are the game's
	bool Driving();
	uint32_t Buttons();
}
