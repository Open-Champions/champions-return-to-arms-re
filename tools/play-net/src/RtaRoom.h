// A room of our own (docs/issues/app-rendezvous.md): the application in the same rendezvous
// service as the native program (tools/rendezvous, tools/recomp/net2), so that players of both
// sit in one room and play one lockstep game - no lobby, no account, no password, and no
// sign-in patch.
//
// What it is made of:
//   - net2's own client (tools/recomp/net2/session.h, compiled in as it is): identity by a
//     device file in the data folder, the room by code, chat, ready, start, punched routes
//     and the relay;
//   - the carrier hook of the network (RtaNet.h, NetCarrier): the game is told that player k
//     is 10.77.0.(k+1), port 4000, and what it sends there goes over net2's carrier;
//   - the start of the game's own lockstep session, done by writing the game's memory at a
//     vertical blank and pressing cross on two of the game's own menus (the developer's
//     host / client menu, then its difficulty menu): the game's character screens, then its
//     own launch handshake. No word of the game's code is changed.
//   - a tick log and tick-keyed writes for tests (the same columns and the same commands as
//     the native program's), through the executor's block hook (rta/Rta.cpp, play-net.patch).
//
// Nothing here depends on Qt. The machine's thread calls Tick at every vertical blank; the
// requests (Host, Join, ...) may come from any thread.
#pragma once

#include "RtaNet.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <vector>

struct net2;

namespace Rta
{
	struct RoomSetup
	{
		std::string dataDir;   // the identity file net2-identity.key is kept here
		std::string service;   // "host:port"; empty: RTA_NET2_SERVICE, then <data>/net2-service.txt
		std::string name;      // the display name of a first start (empty: asked for by the application)
		uint32_t fixSet = 0;   // what this copy is, told to the room
		uint16_t fixWords = 0;
		uint8_t arithCan = 1, arithDoes = 0;
		bool localOnly = false;  // tests: a service on this computer only
		std::string relay;       // tests: "force" | "never"
		std::string bind;        // tests: the carrier's own address:port
		int startAt = 0;         // host: start by itself when this many are in and ready (0: never - Start in the menu)
		bool again = true;       // after a game: choose a character again while still in the room
		uint32_t guestIp = 0;    // the emulated machine's own address (RtaNet's DHCP answer)
		uint32_t cross = 0;      // the emulator's mask for the cross button
		uint32_t circle = 0;     // ... and for circle (the game's "back" on its menus and the lobby's screens)
		// the machine started again from the disc (the menu's Reset), for a game that is in a
		// level when a room is asked for: called on the machine's thread, must not wait for it
		std::function<void()> reset;
		std::string logFile;     // tests: what is said, with the vertical blank
		std::function<void(const std::string&)> log;
		std::function<void(const std::string&)> showCode; // a room code to read out (the application's window)
	};

	class CRoom : public NetCarrier
	{
	public:
		CRoom();
		~CRoom() override;
		CRoom(const CRoom&) = delete;
		CRoom& operator=(const CRoom&) = delete;

		// ---- any thread
		// opens the session with the service (once); false and why when it cannot
		bool Open(const RoomSetup&, std::string& error);
		bool IsOpen() const;
		// the session closed (the room left), before the application ends: with the machine
		// stopped, before anything static goes (net2's lock is one)
		void Close();
		// "host" | "host:friends" | "join:CODE" - also before the game has reached its title
		// screen: the room is asked for at once, the character screens when the title is up
		bool Want(const std::string& what, std::string& error);
		void Leave();
		bool StartGame(std::string& error);   // the host's start
		// the control socket's "room ..." (and the menu's), one line back
		std::string Command(const std::string& line);
		// one line for the status bar; empty: nothing to say
		std::string Note() const;
		// the room code, empty when in none
		std::string Code() const;
		// what the room's members say about their copies, for the arithmetic rule
		// (docs/issues/mixed-arithmetic.md): true when one cannot compute as the console
		// does or already computes as a browser does
		bool MembersWantBrowser() const;
		// a name that net2 takes (3 to 24 bytes); empty when fine
		static std::string CheckName(const std::string& name);
		// true when this data folder has no identity yet: the name is asked for once
		static bool FirstStart(const std::string& dataDir);
		static std::string CheckCode(const std::string& code);

		// what the menu Room shows (the application's thread)
		struct MenuState
		{
			bool open = false;      // the session is open
			bool busy = false;      // a room was asked for and is on its way (no code yet, the
			                        // game being brought to its title screen, the character
			                        // screens opening, the launch): Host and Join are greyed
			bool inRoom = false;    // in a room: its code is known
			bool host = false;      // ... as its host
			bool canStart = false;  // the host's Start the game would be taken now
			bool inLevel = false;   // the game is in a level (a room then starts it again: Reset)
			std::string code;       // the room's code
			std::string text;       // one line: where the room is
			std::string startText;  // why Start the game is greyed (empty when it is not)
		};
		MenuState Menu() const;
		// ---- the machine's thread
		void Tick(uint8_t* ram, uint64_t frame, bool isGame);
		// another program was loaded, or the same again (Reset): the game boots anew
		void OnExecutable();
		bool Driving() const
		{
			return m_driving;
		}
		uint32_t Buttons() const
		{
			return m_buttons;
		}
		// NetCarrier (machine thread, from RtaNet)
		bool Owns(uint32_t destIp, uint16_t destPort) override;
		void Send(uint32_t destIp, uint16_t destPort, uint16_t sourcePort, const uint8_t* data, size_t length) override;
		bool Receive(uint32_t& fromIp, uint16_t& fromPort, uint16_t& toPort, std::vector<uint8_t>& data) override;

	private:
		enum Phase
		{
			BOOTING,
			TITLE,
			CHOOSING,
			CHOSEN,
			LAUNCHING,
			LOADING,
			RUNNING,
			BUSY,
		};
		void Say(const char* format, ...);
		void SetPhase(int phase, const std::string& text);
		void Choose();
		void Launch();
		void FollowRoom(int64_t now);
		void ByItself(int64_t now);
		void LeadToTitle(uint64_t frame, bool front);
		void AskReset(uint64_t frame, const std::string& why);
		void Press(uint32_t mask, uint64_t frame);
		std::string StatusLine();
		std::string RoomLine();

		RoomSetup m_setup;
		net2* m_session = nullptr;
		uint8_t* m_ram = nullptr;
		uint64_t m_frame = 0;
		int m_phase = BOOTING;
		std::string m_text = "the game is starting";
		int m_launches = 0;
		bool m_failed = false;
		bool m_titleSeen = false;
		uint64_t m_titleSince = 0;
		// what was asked for
		std::string m_want;         // "host", "host:friends", "join:CODE"; empty: nothing
		bool m_asked = false;       // the room was asked for at the service
		bool m_readySaid = false;
		bool m_driveBoot = false;   // cross through the card questions and the logos
		int64_t m_lastStartTry = 0;
		std::string m_shownCode;
		// the steps that press a button of the game's own menus
		int m_step = 0;
		uint64_t m_stepSince = 0;
		int m_tries = 0;
		bool m_driving = false;
		uint32_t m_buttons = 0;
		uint64_t m_pressFrom = 0, m_pressUntil = 0;
		uint32_t m_pressMask = 0;
		uint64_t m_bootNextPress = 0;
		// the way back to the title screen when a room is asked for elsewhere: the lobby's own
		// back button (circle), the menus' too, the lobby's state word as at power-on; for a
		// level, the menu's Reset
		bool m_frontSeen = false;   // the front end was seen since the game was loaded
		bool m_lastFront = false;   // ... and at the last blank
		bool m_lobbySeen = false;   // the lobby's screens were opened since the game was loaded
		bool m_lobbyNetUp = false;  // ... and went past their network screen: the network is up
		bool m_leading = false;
		uint64_t m_leadSince = 0, m_leadNext = 0;
		int m_leadPresses = 0;
		bool m_resetAsked = false;
		uint64_t m_resetAt = 0;
		int m_resets = 0;
		std::string m_leadWhere;
		// the game that was started
		uint32_t m_launchedSession = 0;
		int64_t m_startSeenMs = 0;
		int m_count = 0, m_mySlot = 0;
		int m_difficulty = 1;
		bool m_carrying = false;
		uint64_t m_heldBack = 0;    // the others' datagrams thrown away before the game's socket was open
		uint64_t m_launchFrame = 0;
		std::string m_level;
		struct Character
		{
			std::string name, cls;
			int level = 0;
		} m_character;
		FILE* m_logFile = nullptr;
		mutable std::mutex m_noteMutex;
		std::string m_note, m_code;
		std::atomic<bool> m_wantBrowser{false};
	};

	// The tick log and tick-keyed writes of a test run, as the native program has them
	// (tools/recomp/net/netdrv.cpp: --opt tick-log, tick-watch-file, tick-do): one line per
	// lockstep tick at the return of the tick's task pass in net_frameLoop (0x13aee8), the
	// first column this machine's vertical blank. Expressions: numbers, [address] for the
	// word there, ( ), *, +, - and &; names are not known here (the test's driver writes
	// numbers). Types: u8 u16 u32 s8 s16 s32 x8 x16 x32 strN hexN crcN.
	class CTickLog
	{
	public:
		bool Open(const std::string& logPath, const std::string& watchPath, const std::string& doPath, std::string& error);
		// the machine's thread, inside the tick (from the executor's loop)
		void OnTick(uint8_t* ram, uint64_t frame);
		uint64_t Ticks() const
		{
			return m_ticks;
		}

	private:
		struct Watch
		{
			std::string expr, type;
		};
		FILE* m_log = nullptr;
		std::vector<Watch> m_watches;
		std::multimap<uint32_t, std::string> m_actions;
		uint32_t m_lastTick = 0xFFFFFFFF;
		uint64_t m_ticks = 0;
	};
}
