// See RtaRoom.h and docs/issues/app-rendezvous.md.
//
// The start of a room's game, step by step. What the native program does by calling the
// game's functions from its main thread (tools/recomp/net2/launch.cpp) is done here by
// writing the game's memory at a vertical blank and letting the game's own front end run
// (frontend_run 0x1e08f0, one pass per frame; every number below is read from the game's
// code, docs/issues/app-rendezvous.md section 2):
//
//   choose   the title menu's own branch for a key that is neither of the retail two: net
//            flag 0x4f70a0 = 1, the net settings block 0x402a30 cleared, front-end state 6
//            with the menu pointer 0x4f6b7c on the developer's host / client menu 0x4f6db8
//            and its selection (the word after the last entry) on "client"; cross is
//            pressed. The game's state-6 code then sets the settings, points 0x86ad54 at the
//            "chosen" byte 0x4fbbe2, goes to state 7 and starts its character screens
//            (frontend_startPlayerSelect). At the first blank in state 7 the front end is
//            parked in state 10 ("waiting for the lobby": with lobby state 0 it does
//            nothing), so that the end of the screens starts nothing by itself. Chosen: the
//            task "playerSelection" is gone from the game's task table (0x840108, count
//            0x44fdb8) and 0x4fbbe2 is 1.
//   launch   when the room has started: the settings as state 7 leaves them (bits: host,
//            and 2 or 4 by the kind of character; difficulty, mode, mission; 0x402a3a =
//            0xff), the developer's address table 0x53d0e8 (four records of eight words: two
//            addresses, a b c d each) rewritten for this room - every player k at
//            10.77.0.(k+1), and this machine's own record's second address its real one,
//            which is how frontend_startNetGame finds "my number" - then front-end state 3
//            with the menu pointer on the difficulty menu 0x4f6e38 (selection: the host's
//            difficulty), and cross. The game's state-3 code calls frontend_startNetGame
//            0x1e21e0, whose branch for lobby state 0 loads the network modules the first
//            time, copies the table, sets the player count to its fixed 4 and calls
//            net_launchPrepare 0x134c60. That function ends by writing -1 to 0x402b84 (set
//            to 0 here before): at the next blank - before the front end's next pass, the
//            first that runs the launch handshake - the count is set to the room's.
//   handshake nothing: the game's own net_launchUpdate, every frame; its datagrams to
//            10.77.0.x:4000 go through net2's carrier (CRoom::Owns/Send/Receive).
#include "RtaRoom.h"

#include "net2/carrier.h"
#include "net2/session_impl.h"

#include <algorithm>
#include <cstdarg>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>

using namespace Rta;

namespace
{
	const uint32_t RAM_SIZE = 0x2000000;
	// the game's memory (names.tsv, docs/ui.md, docs/netcode.md, tools/recomp/net2/launch.cpp)
	const uint32_t A_IN_FRONTEND = 0x41b510, A_LEVEL_NAME = 0x41b721, A_PENDING_LEVEL = 0x41b6d0;
	const uint32_t A_FE_STATE = 0x4f6b78, A_FE_MENU = 0x4f6b7c, A_FE_FADE = 0x4d8a10, A_FE_NET = 0x4f70a0, A_FE_FIRST_PASS = 0x4f6b70, A_FE_RUNNING = 0x4f83f8;
	const uint32_t A_SETTINGS = 0x402a30, SETTINGS_SIZE = 0x14c;
	const uint32_t A_ADDR2 = 0x402b4b;
	const uint32_t A_CHOSEN = 0x4fbbe2, A_QUICK = 0x4fdb80;
	const uint32_t A_LAUNCHING = 0x402793, A_NETWORK_MODE = 0x402791, A_LOBBY_STATE = 0x506160;
	const uint32_t A_NET_FRAME = 0x4027ac, A_NUM_PEERS = 0x4027c4, A_PEERS = 0x5bf838, PEER_SIZE = 0x44e0, PEER_DROPPED = 0x44d5;
	const uint32_t A_PLAYERS = 0x4d8af0, PLAYER_SIZE = 0x4c30, PLAYER_CLASS = 0x50, PLAYER_LEVEL = 0x59;
	const uint32_t A_NUM_PLAYERS = 0x4d8ae0, A_DIFFICULTY = 0x4f719c, A_SAVED_CONFIG = 0x4f8f38;
	const uint32_t A_TASK_COUNT = 0x44fdb8, A_TASK_TABLE = 0x840108, TASK_SIZE = 16;
	const uint32_t A_DEV_TABLE = 0x53d0e8;       // frontend_startNetGame's four records for "no lobby"
	const uint32_t A_PREPARED = 0x402b84;        // net_launchPrepare's last write: -1
	const uint32_t MENU_NET = 0x4f6db8, MENU_NET_ITEMS = 2;          // menu_net_client, menu_net_server
	const uint32_t MENU_DIFFICULTY = 0x4f6e38, MENU_DIFFICULTY_ITEMS = 4;
	const uint32_t GAME_NET = 0x0A4D0001;        // 10.77.0.1, player 0, as the native program has it
	const uint16_t GAME_PORT = 4000;

	const char* const PHASE_NAMES[] = {"booting", "title", "choosing", "chosen", "launching", "loading", "running", "busy"};

	std::string Format(const char* format, ...)
	{
		char text[1024];
		va_list args;
		va_start(args, format);
		vsnprintf(text, sizeof(text), format, args);
		va_end(args);
		return text;
	}

	std::string IpText(uint32_t ip)
	{
		return Format("%u.%u.%u.%u", ip >> 24, (ip >> 16) & 255, (ip >> 8) & 255, ip & 255);
	}

	typedef std::lock_guard<std::recursive_mutex> Hold;
}

// ---- the game's memory ------------------------------------------------------------------
namespace
{
	struct Mem
	{
		uint8_t* ram;
		uint8_t u8(uint32_t a) const
		{
			return (ram && a < RAM_SIZE) ? ram[a] : 0;
		}
		uint32_t u32(uint32_t a) const
		{
			uint32_t v = 0;
			if(ram && a <= RAM_SIZE - 4) memcpy(&v, ram + a, 4);
			return v;
		}
		float f32(uint32_t a) const
		{
			float v = 0;
			if(ram && a <= RAM_SIZE - 4) memcpy(&v, ram + a, 4);
			return v;
		}
		void w8(uint32_t a, uint8_t v) const
		{
			if(ram && a < RAM_SIZE) ram[a] = v;
		}
		void w32(uint32_t a, uint32_t v) const
		{
			if(ram && a <= RAM_SIZE - 4) memcpy(ram + a, &v, 4);
		}
		std::string str(uint32_t a, uint32_t limit) const
		{
			std::string text;
			for(uint32_t i = 0; ram && i < limit && a + i < RAM_SIZE && ram[a + i]; i++) text += static_cast<char>(ram[a + i]);
			return text;
		}
		bool FrontEnd() const
		{
			return u8(A_IN_FRONTEND) == 1 && str(A_LEVEL_NAME, 8) == "intro";
		}
		// the title menu, drawn and taking input, its first pass made (it loads what the
		// character screens need: a choice made before that finds them dead)
		bool AtTitle() const
		{
			return FrontEnd() && u32(A_FE_STATE) == 0 && u32(A_LOBBY_STATE) == 0 && f32(A_FE_FADE) >= 1.0f && u32(A_FE_FIRST_PASS) == 0 && u32(A_FE_RUNNING) == 1;
		}
		// what task_isRunning 0x19e5e8 answers, read from its table
		bool TaskRunning(const char* name) const
		{
			uint32_t count = u32(A_TASK_COUNT);
			for(uint32_t i = 0; i < count && i < 256; i++)
			{
				uint32_t at = u32(A_TASK_TABLE + i * TASK_SIZE) & 0x1FFFFFFF;
				if(at && str(at, 32) == name) return true;
			}
			return false;
		}
		// menuList_setSelection 0x1a076c: the word after the last entry, index in both bytes
		void Select(uint32_t menu, uint32_t items, uint32_t index) const
		{
			w32(menu + items * 16 + 4, index | (index << 8));
		}
	};
}

// ---- the session ----------------------------------------------------------------------------

CRoom::CRoom() = default;

CRoom::~CRoom()
{
	if(m_session) net2_close(m_session);
	if(m_logFile) fclose(m_logFile);
}

std::string CRoom::CheckName(const std::string& name)
{
	return net2impl::name_problem(name.c_str());
}

std::string CRoom::CheckCode(const std::string& code)
{
	return net2impl::code_normal(code.c_str(), 5).empty() ? "A room code is five letters and digits (no I, O, 0 or 1)." : "";
}

bool CRoom::FirstStart(const std::string& dataDir)
{
	std::error_code error;
	return !std::filesystem::exists(std::filesystem::path(dataDir) / "net2-identity.key", error);
}

bool CRoom::Open(const RoomSetup& setup, std::string& error)
{
	Hold hold(net2impl::big_lock());
	if(m_session) return true;
	if(FirstStart(setup.dataDir) && !setup.name.empty() && !CheckName(setup.name).empty())
	{
		error = CheckName(setup.name);
		return false;
	}
	m_setup = setup;
	if(!m_setup.logFile.empty() && !m_logFile) m_logFile = fopen(m_setup.logFile.c_str(), "w");
	static std::string build = "Play-RTA application";
	net2_config config{};
	config.struct_size = sizeof(config);
	config.data_dir = m_setup.dataDir.c_str();
	config.service = m_setup.service.empty() ? nullptr : m_setup.service.c_str();
	config.name = m_setup.name.empty() ? nullptr : m_setup.name.c_str();
	config.fix_set = m_setup.fixSet;
	config.fix_words = m_setup.fixWords;
	config.arith_can = m_setup.arithCan;
	config.arith_does = m_setup.arithDoes;
	config.build = build.c_str();
	config.local_only = m_setup.localOnly ? 1 : 0;
	m_session = net2_open(&config);
	if(!m_setup.relay.empty()) net2_set(m_session, "relay", m_setup.relay.c_str());
	if(!m_setup.bind.empty()) net2_set(m_session, "bind", m_setup.bind.c_str());
	net2_me_t me;
	net2_me(m_session, &me);
	Say("room: session opened (%s; fix set %08x, %u words; arithmetic: can %u, does %u)%s", me.service[0] ? me.service : "no service named", m_setup.fixSet, m_setup.fixWords, m_setup.arithCan, m_setup.arithDoes,
	    me.problem[0] ? (std::string(": ") + me.problem).c_str() : "");
	return true;
}

bool CRoom::IsOpen() const
{
	Hold hold(net2impl::big_lock());
	return m_session != nullptr;
}

bool CRoom::Want(const std::string& what, std::string& error)
{
	Hold hold(net2impl::big_lock());
	if(!m_session)
	{
		error = "the room's session is not open";
		return false;
	}
	if(what.compare(0, 5, "join:") == 0 && !CheckCode(what.substr(5)).empty())
	{
		error = CheckCode(what.substr(5));
		return false;
	}
	if(what != "host" && what != "host:friends" && what.compare(0, 5, "join:") != 0)
	{
		error = "'" + what + "' is not host, host:friends or join:CODE";
		return false;
	}
	net2_room_t room;
	net2_room(m_session, &room);
	if(room.state != NET2_ROOM_NONE)
	{
		error = "already in a room (" + std::string(room.code) + "): leave it first";
		return false;
	}
	m_want = what;
	m_asked = false;
	m_readySaid = false;
	if(m_phase == BOOTING) m_driveBoot = true;
	Say("room: asked for: %s", what.c_str());
	return true;
}

void CRoom::Leave()
{
	Hold hold(net2impl::big_lock());
	if(!m_session) return;
	net2_leave(m_session);
	m_want.clear();
	m_asked = false;
	Say("room: left");
}

bool CRoom::StartGame(std::string& error)
{
	Hold hold(net2impl::big_lock());
	if(!m_session)
	{
		error = "the room's session is not open";
		return false;
	}
	net2_room_t room;
	net2_room(m_session, &room);
	if(room.state != NET2_ROOM_OPEN || room.my_slot != room.host_slot)
	{
		error = "only the host of an open room starts its game";
		return false;
	}
	if(m_phase != CHOSEN)
	{
		error = "choose your character on the game's screens first";
		return false;
	}
	if(!room.all_ready)
	{
		error = "not everybody in the room has chosen a character yet";
		return false;
	}
	if(room.mismatch) Say("room: WARNING: starting although the copies differ: %s", room.warning);
	int r = net2_start(m_session);
	if(r != NET2_OK)
	{
		error = net2_error_text(r);
		return false;
	}
	return true;
}

std::string CRoom::Code() const
{
	std::lock_guard<std::mutex> lock(m_noteMutex);
	return m_code;
}

std::string CRoom::Note() const
{
	std::lock_guard<std::mutex> lock(m_noteMutex);
	return m_note;
}

bool CRoom::MembersWantBrowser() const
{
	return m_wantBrowser.load();
}

void CRoom::Say(const char* format, ...)
{
	char text[1024];
	va_list args;
	va_start(args, format);
	vsnprintf(text, sizeof(text), format, args);
	va_end(args);
	if(m_setup.log) m_setup.log(text);
	if(m_logFile)
	{
		fprintf(m_logFile, "[%llu] %s\n", static_cast<unsigned long long>(m_frame), text);
		fflush(m_logFile);
	}
}

void CRoom::SetPhase(int phase, const std::string& text)
{
	if(phase == m_phase && text == m_text) return;
	m_phase = phase;
	m_text = text;
	Say("room: %s", text.c_str());
}

// ---- the game: choose, launch -------------------------------------------------------------

void CRoom::Choose()
{
	Mem m{m_ram};
	// as at power-on: one player, the first difficulty (a game played before leaves both
	// changed, and the character screens then wait for a second controller, or take only an
	// imported character: tools/recomp/net2/launch.cpp, do_choose)
	m.w32(A_NUM_PLAYERS, 1);
	m.w32(A_DIFFICULTY, 1);
	memset(m_ram + A_SETTINGS, 0, SETTINGS_SIZE);
	m.w8(A_CHOSEN, 0);
	m.w32(A_FE_NET, 1);
	m.w32(A_FE_MENU, MENU_NET);
	m.Select(MENU_NET, MENU_NET_ITEMS, 0);
	m.w32(A_FE_STATE, 6);
	m_step = 1;
	m_stepSince = m_frame;
	m_tries = 0;
	m_pressFrom = m_frame + 3;
	m_pressUntil = m_pressFrom + 5;
	m_failed = false;
	SetPhase(CHOOSING, "the game's character screens are being opened (its host / client menu, cross)");
}

void CRoom::Launch()
{
	Mem m{m_ram};
	bool host = (m_mySlot == 0);
	// the settings as the front end's state 7 leaves them for the launch
	uint8_t bits = static_cast<uint8_t>((host ? 1 : 0) | (((m.u8(A_QUICK + 0x29) & 3) == 0) ? 2 : 4));
	m.w8(A_SETTINGS + 0, bits);
	m.w8(A_SETTINGS + 2, 1);
	m.w8(A_SETTINGS + 3, 0); // play missions; the arena modes are not wired (as in the native program)
	m.w8(A_SETTINGS + 4, 0);
	m.w8(A_SETTINGS + 5, 0);
	m.w8(A_SETTINGS + 10, 0xFF);
	// the developer's address table: player k at 10.77.0.(k+1); this machine's own record
	// has its real address second, which frontend_startNetGame compares with the address
	// of its network interface to find its own number
	for(uint32_t k = 0; k < 4; k++)
	{
		uint32_t game = GAME_NET + k;
		uint32_t second = (static_cast<int>(k) == m_mySlot) ? m_setup.guestIp : game;
		for(uint32_t b = 0; b < 4; b++)
		{
			m.w32(A_DEV_TABLE + k * 32 + b * 4, (game >> (24 - 8 * b)) & 0xFF);
			m.w32(A_DEV_TABLE + k * 32 + 16 + b * 4, (second >> (24 - 8 * b)) & 0xFF);
		}
	}
	m.w32(A_PREPARED, 0);
	// the difficulty menu: its handler starts the net game with the item chosen + 1
	int difficulty = host ? std::max(1, std::min(4, m_difficulty)) : 1;
	m.w32(A_FE_MENU, MENU_DIFFICULTY);
	m.Select(MENU_DIFFICULTY, MENU_DIFFICULTY_ITEMS, static_cast<uint32_t>(difficulty - 1));
	m.w32(A_FE_STATE, 3);
	m_carrying = true;
	m_step = 10;
	m_stepSince = m_frame;
	m_tries = 0;
	m_pressFrom = m_frame + 3;
	m_pressUntil = m_pressFrom + 5;
	m_launchFrame = m_frame;
	SetPhase(LAUNCHING, Format("launching: player %d of %d, settings bits %02x, difficulty %d, character %s (%s %d); the game's difficulty menu, cross", m_mySlot + 1, m_count, bits, difficulty,
	                           m_character.name.c_str(), m_character.cls.c_str(), m_character.level));
}

// A start of the room is taken up once the routes stand (or four seconds have passed: the
// relay carries what is not straight yet), as the native program does (launch.cpp, follow_room).
void CRoom::FollowRoom(int64_t now)
{
	net2_room_t room;
	net2_session_t start;
	net2_room(m_session, &room);
	net2_session(m_session, &start);
	if(room.state != NET2_ROOM_STARTING || !start.valid || start.session == m_launchedSession) return;
	if(m_startSeenMs == 0) m_startSeenMs = now;
	n2::Carrier* carrier = net2impl::carrier_of(m_session->body);
	if(!carrier)
	{
		m_launchedSession = start.session;
		m_startSeenMs = 0;
		Say("room: the room started, but this session has no route to anybody (a mock): no launch");
		net2_game_state(m_session, nullptr);
		return;
	}
	Mem m{m_ram};
	if(m_phase != CHOSEN || !m.FrontEnd() || m.u32(A_FE_STATE) != 10)
	{
		if(now - m_startSeenMs < 8000) return; // the character screens may just be closing
		m_launchedSession = start.session;
		m_startSeenMs = 0;
		Say("room: the room started but no character is chosen on this machine: not launching");
		net2_game_state(m_session, nullptr);
		return;
	}
	if(!carrier->routes_ready() && now - m_startSeenMs < 4000) return;
	m_launchedSession = start.session;
	m_startSeenMs = 0;
	m_count = start.count;
	m_mySlot = start.my_slot;
	m_difficulty = start.options.difficulty;
	Say("room: the room started: session %08x, %d players, I am player %d; routes: %s", start.session, start.count, start.my_slot + 1, carrier->text().c_str());
	Launch();
}

// To a room by itself when one was asked for, the character screens, ready; and for a host
// with startAt, the start when enough players are in (launch.cpp, play_by_itself).
void CRoom::ByItself(int64_t now)
{
	net2_me_t me;
	net2_room_t room;
	net2_me(m_session, &me);
	net2_room(m_session, &room);
	if(me.link != NET2_LINK_ONLINE) return;
	bool hosting = m_want.compare(0, 4, "host") == 0;
	if(room.state == NET2_ROOM_NONE)
	{
		if(m_want.empty() || m_asked) return;
		m_asked = true;
		if(hosting)
		{
			net2_options o{};
			o.difficulty = m_difficulty;
			o.open_to = (m_want == "host:friends") ? NET2_OPEN_FRIENDS : NET2_OPEN_CODE;
			net2_host(m_session, &o);
		}
		else
			net2_join(m_session, m_want.c_str() + 5);
		return;
	}
	if(room.state != NET2_ROOM_OPEN) return;
	Mem m{m_ram};
	if(m_phase == TITLE && m.AtTitle() && (m_launches == 0 || m_setup.again)) Choose();
	if(m_phase != CHOSEN) return;
	if(room.my_slot != room.host_slot)
	{
		if(!m_readySaid)
		{
			m_readySaid = true;
			net2_ready(m_session, 1);
		}
		return;
	}
	bool allBack = true;
	for(int i = 0; i < room.count; i++) allBack = allBack && room.members[i].phase == 0;
	if(m_setup.startAt >= 2 && room.count >= m_setup.startAt && room.all_ready && allBack && now - m_lastStartTry > 2000)
	{
		m_lastStartTry = now;
		if(room.mismatch) Say("room: WARNING: starting although the copies differ: %s", room.warning);
		net2_start(m_session);
	}
}

void CRoom::Tick(uint8_t* ram, uint64_t frame, bool isGame)
{
	Hold hold(net2impl::big_lock());
	m_ram = ram;
	m_frame = frame;
	if(!m_session || !ram || !isGame)
	{
		m_driving = false;
		return;
	}
	int64_t now = net2impl::steady_ms();
	net2_poll(m_session);
	net2_event e;
	while(net2_next_event(m_session, &e))
	{
		switch(e.type)
		{
		case NET2_EV_ROOM:
			if(e.room[0] && e.room != m_shownCode)
			{
				m_shownCode = e.room;
				Say("room: ROOM CODE %s - tell it to your friends", e.room);
				if(m_setup.showCode) m_setup.showCode(e.room);
			}
			break;
		case NET2_EV_CHAT:
			Say("room: chat: %s: %s", e.who, e.text);
			break;
		case NET2_EV_START:
			Say("room: the host started the game");
			break;
		case NET2_EV_ERROR:
			Say("room: refused: %s", e.text);
			break;
		case NET2_EV_NOTICE:
			Say("room: %s", e.text);
			break;
		case NET2_EV_LINK:
		{
			net2_me_t me;
			net2_me(m_session, &me);
			Say("room: link %s%s%s", me.link == NET2_LINK_ONLINE ? "online" : (me.link == NET2_LINK_CONNECTING ? "connecting" : "off"), me.problem[0] ? ": " : "", me.problem);
			break;
		}
		case NET2_EV_ME:
		{
			net2_me_t me;
			net2_me(m_session, &me);
			if(me.id[0]) Say("room: I am %s, friend code %s%s", me.name, me.friend_code, me.new_identity ? " (a new identity, made now)" : "");
			break;
		}
		default:
			break;
		}
	}
	if(n2::Carrier* carrier = net2impl::carrier_of(m_session->body)) carrier->poll(now);

	Mem m{ram};
	bool front = m.FrontEnd();
	switch(m_phase)
	{
	case BOOTING:
	case BUSY:
		if(!m.AtTitle())
			m_titleSince = 0;
		else if(m_titleSince == 0)
			m_titleSince = frame;
		else if(frame - m_titleSince >= 60)
		{
			m_titleSeen = true;
			m_driveBoot = false;
			SetPhase(TITLE, "the game is at its title screen");
		}
		break;
	case TITLE:
		if(!front && m_titleSeen) SetPhase(BUSY, "the game is elsewhere (an offline game)");
		break;
	case CHOOSING:
		if(m_step == 1)
		{
			if(m.u32(A_FE_STATE) == 7)
			{
				// the screens are up: the front end waits in state 10 for the launch
				m.w32(A_FE_STATE, 10);
				m_step = 2;
				m_stepSince = frame;
				SetPhase(CHOOSING, "the game's character screens are up");
			}
			else if(frame - m_stepSince > 90)
			{
				uint32_t state = m.u32(A_FE_STATE);
				if(++m_tries > 5 || state != 6)
				{
					m.w32(A_FE_STATE, 0);
					m.w32(A_FE_NET, 0);
					m_failed = true;
					SetPhase(TITLE, Format("the character screens did not come up (front-end state %u)", state));
					break;
				}
				m_stepSince = frame;
				m_pressFrom = frame + 2;
				m_pressUntil = m_pressFrom + 5;
			}
		}
		else if(m_step == 2 && frame - m_stepSince > 10 && !m.TaskRunning("playerSelection"))
		{
			if(m.u8(A_CHOSEN) == 1)
			{
				m_character.name = net2impl::clean_label(m.str(A_PLAYERS, 31).c_str(), 24);
				uint32_t cls = m.u32(A_PLAYERS + PLAYER_CLASS);
				m_character.cls = cls < 7 ? net2impl::CLASS_WORDS[cls] : "?";
				m_character.level = static_cast<int8_t>(m.u8(A_PLAYERS + PLAYER_LEVEL));
				if(m_character.name.empty())
				{
					// a character just made is a summary until the launch builds its record
					m_character.name = net2impl::clean_label(m.str(A_QUICK, 31).c_str(), 24);
					m_character.cls.clear();
				}
				if(m_character.level < 1) m_character.level = 1;
				net2_character c{};
				net2impl::put(c.name, m_character.name);
				net2impl::put(c.cls, m_character.cls);
				c.level = m_character.level;
				net2_set_character(m_session, &c);
				m_readySaid = false;
				SetPhase(CHOSEN, Format("a character is chosen: %s (%s, level %d)", m_character.name.c_str(), m_character.cls.c_str(), m_character.level));
			}
			else
			{
				m.w32(A_FE_STATE, 0);
				m.w32(A_FE_NET, 0);
				m_failed = true;
				SetPhase(TITLE, "the character screens were left without a character");
			}
		}
		break;
	case LAUNCHING:
		if(m_step == 10)
		{
			if(m.u8(A_LAUNCHING) == 1)
			{
				m_step = 11;
				m_stepSince = frame;
				Say("room: the game is starting its network game (frontend_startNetGame: the network modules, the tables)");
			}
			else if(frame - m_stepSince > 90)
			{
				if(++m_tries > 5)
				{
					uint32_t state = m.u32(A_FE_STATE);
					m.w32(A_FE_STATE, 0);
					m.w32(A_FE_NET, 0);
					m_carrying = false;
					m_failed = true;
					net2_game_state(m_session, nullptr);
					SetPhase(BUSY, Format("the launch did not begin (front-end state %u)", state));
					break;
				}
				if(m.u32(A_FE_STATE) != 3) m.w32(A_FE_STATE, 3);
				m_stepSince = frame;
				m_pressFrom = frame + 2;
				m_pressUntil = m_pressFrom + 5;
			}
		}
		else if(m_step == 11 && m.u32(A_PREPARED) == 0xFFFFFFFF)
		{
			// net_launchPrepare has run, with the fixed count of four: the room's count, before
			// the front end's next pass runs the handshake
			uint8_t own = m.u8(A_SETTINGS + 9), had = m.u8(A_SETTINGS + 7);
			m.w8(A_SETTINGS + 7, static_cast<uint8_t>(m_count));
			uint32_t mine = GAME_NET + static_cast<uint32_t>(m_mySlot);
			for(uint32_t b = 0; b < 4; b++) m.w8(A_ADDR2 + m_mySlot * 4 + b, static_cast<uint8_t>(mine >> (24 - 8 * b)));
			m_step = 12;
			if(own != m_mySlot)
				Say("room: WARNING: the game took itself for player %d, not %d (its network address is not %s?)", static_cast<int8_t>(own) + 1, m_mySlot + 1, IpText(m_setup.guestIp).c_str());
			Say("room: the launch tables stand (%llu blanks after the press): count %u -> %d, I am player %d; %llu datagram(s) of the others thrown away before the game's socket was open", static_cast<unsigned long long>(frame - m_launchFrame), had, m_count, static_cast<int8_t>(own) + 1,
			    static_cast<unsigned long long>(m_heldBack));
			m_heldBack = 0;
		}
		else if(m_step == 12 && m.u8(A_LAUNCHING) == 0)
		{
			if(m.u8(A_NETWORK_MODE) == 1)
			{
				m_launches++;
				SetPhase(LOADING, Format("launched after %llu blanks: %u players, first level %s", static_cast<unsigned long long>(frame - m_launchFrame), m.u32(A_NUM_PEERS), m.str(A_PENDING_LEVEL, 20).c_str()));
			}
			else
			{
				m.w32(A_FE_STATE, 0);
				m.w32(A_FE_NET, 0);
				m_carrying = false;
				m_failed = true;
				m_level.clear();
				net2_game_state(m_session, nullptr);
				m_titleSince = 0;
				SetPhase(BUSY, "the launch did not complete (a player could not be reached, or it was cancelled)");
			}
		}
		break;
	case LOADING:
	case RUNNING:
		if(m_phase == LOADING && !front && m.u8(A_NETWORK_MODE) == 1 && static_cast<int32_t>(m.u32(A_NET_FRAME)) > 0 && m.u8(A_LEVEL_NAME) != 0 && m.str(A_LEVEL_NAME, 20) != "intro")
			SetPhase(RUNNING, "the game runs: level " + m.str(A_LEVEL_NAME, 20));
		if(m_phase == RUNNING && frame % 60 == 0)
		{
			std::string level = m.str(A_LEVEL_NAME, 20);
			if(level != m_level && !level.empty() && level != "intro")
			{
				m_level = level;
				net2_game_state(m_session, level.c_str());
			}
			uint32_t record = A_PLAYERS + static_cast<uint32_t>(m_mySlot) * PLAYER_SIZE;
			std::string name = net2impl::clean_label(m.str(record, 31).c_str(), 24);
			uint32_t cls = m.u32(record + PLAYER_CLASS);
			int level8 = static_cast<int8_t>(m.u8(record + PLAYER_LEVEL));
			std::string clsWord = cls < 7 ? net2impl::CLASS_WORDS[cls] : "?";
			if(!name.empty() && (name != m_character.name || clsWord != m_character.cls || level8 != m_character.level))
			{
				m_character = {name, clsWord, level8};
				net2_character c{};
				net2impl::put(c.name, name);
				net2impl::put(c.cls, clsWord);
				c.level = level8;
				net2_set_character(m_session, &c);
			}
		}
		if(front && m.u8(A_NETWORK_MODE) == 0 && frame - m_launchFrame > 120)
		{
			m_carrying = false;
			m_level.clear();
			net2_game_state(m_session, nullptr);
			m_readySaid = false;
			m_titleSince = 0;
			SetPhase(BUSY, "the game is over: back at the title screen");
		}
		break;
	default:
		break;
	}
	FollowRoom(now);
	ByItself(now);

	// the buttons: a press of cross on one of the game's own menus, or cross through the
	// card questions and the logos while the game boots for a room asked for at power-on
	m_buttons = 0;
	m_driving = false;
	if(frame < m_pressUntil + 2 && m_pressUntil != 0)
	{
		m_driving = true;
		if(frame >= m_pressFrom && frame < m_pressUntil) m_buttons = m_setup.cross;
	}
	else if(m_driveBoot && m_phase == BOOTING && !front)
	{
		m_driving = true;
		if(frame >= m_bootNextPress)
		{
			m_pressFrom = frame;
			m_bootNextPress = frame + 46;
		}
		if(frame < m_pressFrom + 6) m_buttons = m_setup.cross;
	}

	// what the members say about their copies (the arithmetic rule) and the status line
	net2_room_t room;
	net2_room(m_session, &room);
	bool browser = false;
	for(int i = 0; i < room.count; i++)
	{
		const net2_member& member = room.members[i];
		if(member.me || member.arith_can == 0) continue;
		if(!(member.arith_can & 1) || member.arith_does == 1) browser = true;
	}
	m_wantBrowser = browser;
	if(frame % 15 == 0)
	{
		std::string note = StatusLine();
		std::lock_guard<std::mutex> lock(m_noteMutex);
		m_note = note;
		m_code = (room.state != NET2_ROOM_NONE) ? room.code : "";
	}
}

std::string CRoom::RoomLine()
{
	net2_room_t room;
	net2_room(m_session, &room);
	static const char* STATES[] = {"none", "joining", "open", "starting", "in-game"};
	std::string text = Format("room=%s state=%s count=%d my_slot=%d host_slot=%d all_ready=%d mismatch=%d", room.code[0] ? room.code : "-", room.state >= 0 && room.state <= 4 ? STATES[room.state] : "?", room.count, room.my_slot,
	                          room.host_slot, room.all_ready, room.mismatch);
	for(int i = 0; i < room.count; i++)
	{
		const net2_member& member = room.members[i];
		text += Format(" [%d %s%s ready=%d fix=%08x arith=%u/%u route=%d rtt=%d phase=%d char=%s;%s;%d]", member.slot, member.name, member.me ? " (me)" : "", member.ready, member.fix_set, member.arith_can, member.arith_does, member.route, member.rtt_ms, member.phase,
		               member.character.name, member.character.cls, member.character.level);
	}
	if(room.mismatch) text += std::string(" warning=") + room.warning;
	return text;
}

std::string CRoom::StatusLine()
{
	net2_me_t me;
	net2_room_t room;
	net2_me(m_session, &me);
	net2_room(m_session, &room);
	if(me.link != NET2_LINK_ONLINE && room.state == NET2_ROOM_NONE && m_want.empty()) return "";
	std::string text;
	if(me.link != NET2_LINK_ONLINE)
		text = std::string("room service: ") + (me.link == NET2_LINK_CONNECTING ? "connecting" : "off") + (me.problem[0] ? std::string(" (") + me.problem + ")" : "");
	else if(room.state == NET2_ROOM_NONE)
		text = m_want.empty() ? "" : "room: asking for " + m_want;
	else
	{
		text = Format("room %s: %d player%s", room.code, room.count, room.count == 1 ? "" : "s");
		if(room.mismatch) text += std::string(" - WARNING: ") + room.warning;
	}
	if(m_phase == CHOOSING || m_phase == CHOSEN || m_phase == LAUNCHING || m_phase == LOADING) text += (text.empty() ? "" : " - ") + m_text;
	if(m_phase == CHOSEN && room.state == NET2_ROOM_OPEN) text += (room.my_slot == room.host_slot) ? (room.all_ready ? "; everybody is ready: Room > Start the game" : "; waiting for the others") : "; waiting for the host to start";
	return text;
}

std::string CRoom::Command(const std::string& line)
{
	Hold hold(net2impl::big_lock());
	std::istringstream words(line);
	std::string verb, rest;
	words >> verb;
	std::getline(words, rest);
	while(!rest.empty() && rest[0] == ' ') rest.erase(0, 1);
	if(!m_session) return "err the room's session is not open (--rta-room, or Room in the menu)";
	std::string error;
	if(verb.empty() || verb == "status")
	{
		net2_me_t me;
		net2_me(m_session, &me);
		n2::Carrier* carrier = net2impl::carrier_of(m_session->body);
		Mem m{m_ram};
		return Format("ok phase=%s launches=%d failed=%d link=%d name=%s character=%s;%s;%d fe=%u lobby=%u launching=%u netmode=%u count=%u own=%u tick=%d level=%s want=%s carrying=%d | %s | carrier: %s", PHASE_NAMES[m_phase], m_launches, m_failed ? 1 : 0, me.link, me.name,
		              m_character.name.c_str(), m_character.cls.c_str(), m_character.level, m.u32(A_FE_STATE), m.u32(A_LOBBY_STATE), m.u8(A_LAUNCHING), m.u8(A_NETWORK_MODE), m.u8(A_SETTINGS + 7), m.u8(A_SETTINGS + 9),
		              static_cast<int32_t>(m.u32(A_NET_FRAME)), m.str(A_LEVEL_NAME, 12).c_str(), m_want.c_str(), m_carrying ? 1 : 0, RoomLine().c_str(), carrier ? carrier->text().c_str() : "none") +
		       " text=" + m_text;
	}
	if(verb == "host") return Want(rest == "friends" ? "host:friends" : "host", error) ? "ok" : "err " + error;
	if(verb == "join") return Want("join:" + rest, error) ? "ok" : "err " + error;
	if(verb == "leave")
	{
		Leave();
		return "ok";
	}
	if(verb == "start") return StartGame(error) ? "ok" : "err " + error;
	if(verb == "chat")
	{
		int r = net2_chat(m_session, rest.c_str());
		return r == NET2_OK ? "ok" : std::string("err ") + net2_error_text(r);
	}
	if(verb == "ready")
	{
		int r = net2_ready(m_session, rest != "0");
		return r == NET2_OK ? "ok" : std::string("err ") + net2_error_text(r);
	}
	if(verb == "difficulty")
	{
		m_difficulty = std::max(1, std::min(4, atoi(rest.c_str())));
		return "ok";
	}
	if(verb == "debug")
	{
		char out[1024];
		net2_debug(m_session, rest.empty() ? "routes" : rest.c_str(), out, sizeof(out));
		return std::string("ok ") + out;
	}
	if(verb == "set")
	{
		std::string key = rest.substr(0, rest.find(' ')), value = rest.find(' ') == std::string::npos ? "" : rest.substr(rest.find(' ') + 1);
		int r = net2_set(m_session, key.c_str(), value.c_str());
		return r == NET2_OK ? "ok" : std::string("err ") + net2_error_text(r);
	}
	return "err room [status] | host [friends] | join CODE | leave | start | chat TEXT | ready 0|1 | difficulty N | debug WHAT | set KEY VALUE";
}

// ---- the carrier ----------------------------------------------------------------------------

bool CRoom::Owns(uint32_t destIp, uint16_t destPort)
{
	(void)destPort;
	if(!m_carrying) return false;
	uint32_t slot = destIp - GAME_NET;
	return (destIp & 0xFFFFFF00) == (GAME_NET & 0xFFFFFF00) && slot < 4;
}

void CRoom::Send(uint32_t destIp, uint16_t destPort, uint16_t sourcePort, const uint8_t* data, size_t length)
{
	(void)destPort;
	(void)sourcePort;
	Hold hold(net2impl::big_lock());
	if(!m_session) return;
	n2::Carrier* carrier = net2impl::carrier_of(m_session->body);
	if(carrier) carrier->send(static_cast<int>(destIp - GAME_NET), data, length);
}

bool CRoom::Receive(uint32_t& fromIp, uint16_t& fromPort, uint16_t& toPort, std::vector<uint8_t>& data)
{
	if(!m_carrying) return false;
	Hold hold(net2impl::big_lock());
	if(!m_session) return false;
	n2::Carrier* carrier = net2impl::carrier_of(m_session->body);
	if(!carrier) return false;
	uint8_t buffer[n2::MOST];
	int from = 0;
	if(m_step < 12)
	{
		// The game has not opened its socket yet (its network modules may still be loading):
		// a frame for it then is thrown away here. Seen: one handed to the machine during the
		// modules' start brought the emulator's IOP down (CIopBios::SetAlarm). The other
		// players' launch handshake sends again until it is answered.
		carrier->poll(net2impl::steady_ms());
		while(carrier->receive(from, buffer, sizeof(buffer)) >= 0) m_heldBack++;
		return false;
	}
	int got = carrier->receive(from, buffer, sizeof(buffer));
	if(got < 0)
	{
		carrier->poll(net2impl::steady_ms());
		got = carrier->receive(from, buffer, sizeof(buffer));
		if(got < 0) return false;
	}
	data.assign(buffer, buffer + got);
	fromIp = GAME_NET + static_cast<uint32_t>(from);
	fromPort = GAME_PORT;
	toPort = GAME_PORT;
	return true;
}

// ---- the tick log ---------------------------------------------------------------------------
namespace
{
	struct Eval
	{
		const std::string& s;
		const Mem& m;
		size_t i = 0;
		bool bad = false;
		void skip()
		{
			while(i < s.size() && s[i] == ' ') i++;
		}
		uint32_t factor()
		{
			skip();
			if(i < s.size() && (s[i] == '[' || s[i] == '('))
			{
				char open = s[i++];
				uint32_t v = sum();
				skip();
				if(i >= s.size() || s[i] != (open == '[' ? ']' : ')')) bad = true;
				i++;
				return open == '[' ? m.u32(v & 0x1FFFFFFF) : v;
			}
			const char* start = s.c_str() + i;
			char* end = nullptr;
			uint32_t v = static_cast<uint32_t>(strtoul(start, &end, 0));
			if(end == start) bad = true;
			i += static_cast<size_t>(end - start);
			return v;
		}
		uint32_t product()
		{
			uint32_t v = factor();
			for(;;)
			{
				skip();
				if(i < s.size() && s[i] == '*')
				{
					i++;
					v *= factor();
				}
				else
					return v;
			}
		}
		uint32_t sum()
		{
			uint32_t v = product();
			for(;;)
			{
				skip();
				if(i >= s.size()) return v;
				if(s[i] == '+')
				{
					i++;
					v += product();
				}
				else if(s[i] == '-')
				{
					i++;
					v -= product();
				}
				else if(s[i] == '&')
				{
					i++;
					v &= product();
				}
				else
					return v;
			}
		}
	};

	// the native program's formatting (tools/recomp/rt/script.cpp, format_value)
	std::string Value(const Mem& m, uint32_t address, const std::string& type)
	{
		address &= 0x1FFFFFFF;
		char kind = type.empty() ? 'x' : type[0];
		uint32_t size = 4;
		if(type.compare(0, 3, "str") == 0 || type.compare(0, 3, "hex") == 0 || type.compare(0, 3, "crc") == 0)
		{
			kind = type[0] == 's' ? 't' : type[0] == 'h' ? 'h' : 'c';
			size = static_cast<uint32_t>(atoi(type.c_str() + 3));
		}
		else if(type.size() >= 2)
			size = static_cast<uint32_t>(atoi(type.c_str() + 1)) / 8;
		if(size == 0 || address + size > RAM_SIZE || !m.ram) return "<unmapped>";
		const uint8_t* p = m.ram + address;
		uint32_t raw = 0;
		switch(kind)
		{
		case 'u':
			memcpy(&raw, p, std::min<uint32_t>(size, 4));
			return Format("%lld", static_cast<long long>(raw));
		case 's':
		{
			memcpy(&raw, p, std::min<uint32_t>(size, 4));
			long long v = size == 1 ? static_cast<int8_t>(raw) : size == 2 ? static_cast<int16_t>(raw) : static_cast<int32_t>(raw);
			return Format("%lld", v);
		}
		case 'x':
			memcpy(&raw, p, std::min<uint32_t>(size, 4));
			return Format("%0*llx", static_cast<int>(size) * 2, static_cast<unsigned long long>(raw));
		case 't':
		{
			std::string out;
			for(uint32_t i = 0; i < size && p[i]; i++)
			{
				char ch = static_cast<char>(p[i]);
				if(ch == '\t')
					out += "\\t";
				else if(ch == '\n')
					out += "\\n";
				else if(ch == '\\')
					out += "\\\\";
				else if(p[i] < 0x20 || p[i] >= 0x7F)
					out += Format("\\x%02x", p[i]);
				else
					out += ch;
			}
			return out;
		}
		case 'h':
		{
			std::string out;
			for(uint32_t i = 0; i < size; i++) out += Format("%02x", p[i]);
			return out;
		}
		case 'c':
		{
			uint32_t hash = 0x811C9DC5u;
			for(uint32_t i = 0; i < size; i++) hash = (hash ^ p[i]) * 0x01000193u;
			return Format("%08x", hash);
		}
		default:
			return "?";
		}
	}

	// "expr:type": the last ':' outside brackets
	void SplitTyped(const std::string& text, std::string& expr, std::string& type)
	{
		int depth = 0;
		size_t colon = std::string::npos;
		for(size_t i = 0; i < text.size(); i++)
		{
			if(text[i] == '[' || text[i] == '(') depth++;
			if(text[i] == ']' || text[i] == ')') depth--;
			if(text[i] == ':' && depth == 0) colon = i;
		}
		if(colon == std::string::npos)
		{
			expr = text;
			type = "x32";
		}
		else
		{
			expr = text.substr(0, colon);
			type = text.substr(colon + 1);
		}
	}
}

bool CTickLog::Open(const std::string& logPath, const std::string& watchPath, const std::string& doPath, std::string& error)
{
	if(!logPath.empty())
	{
		std::ifstream in(watchPath);
		if(!in)
		{
			error = "cannot read the tick watch file " + watchPath;
			return false;
		}
		m_log = fopen(logPath.c_str(), "w");
		if(!m_log)
		{
			error = "cannot write the tick log " + logPath;
			return false;
		}
		fprintf(m_log, "frame");
		std::string line;
		while(std::getline(in, line))
		{
			if(line.empty() || line[0] == '#') continue;
			size_t equals = line.find('=');
			std::string name, typed = line;
			// "name=expr:type" (a name has no bracket in it)
			if(equals != std::string::npos && line.find_first_of("[(") > equals)
			{
				name = line.substr(0, equals);
				typed = line.substr(equals + 1);
			}
			Watch watch;
			SplitTyped(typed, watch.expr, watch.type);
			if(name.empty()) name = watch.expr;
			m_watches.push_back(watch);
			fprintf(m_log, "\t%s", name.c_str());
		}
		fprintf(m_log, "\n");
		fflush(m_log);
	}
	if(!doPath.empty())
	{
		std::ifstream in(doPath);
		std::string line;
		while(std::getline(in, line))
		{
			if(line.empty() || line[0] == '#') continue;
			size_t space = line.find(' ');
			if(space != std::string::npos) m_actions.insert({static_cast<uint32_t>(strtoul(line.c_str(), nullptr, 0)), line.substr(space + 1)});
		}
	}
	return true;
}

void CTickLog::OnTick(uint8_t* ram, uint64_t frame)
{
	Mem m{ram};
	uint32_t tick = m.u32(A_NET_FRAME);
	if(tick == m_lastTick) return; // the loop came back to the same block (its time slice had ended there)
	m_lastTick = tick;
	m_ticks++;
	if(m_log)
	{
		fprintf(m_log, "%llu", static_cast<unsigned long long>(frame));
		for(const auto& watch : m_watches)
		{
			Eval e{watch.expr, m};
			uint32_t address = e.sum();
			fprintf(m_log, "\t%s", e.bad ? "<bad>" : Value(m, address, watch.type).c_str());
		}
		fprintf(m_log, "\n");
		if((m_ticks % 60) == 0) fflush(m_log);
	}
	auto range = m_actions.equal_range(tick);
	for(auto it = range.first; it != range.second; ++it)
	{
		std::istringstream words(it->second);
		std::string verb, target, text;
		words >> verb >> target;
		std::getline(words, text);
		while(!text.empty() && text[0] == ' ') text.erase(0, 1);
		Eval e{target, m};
		uint32_t address = e.sum() & 0x1FFFFFFF;
		if(verb == "poke" && !e.bad && address + text.size() + 1 <= RAM_SIZE)
		{
			memcpy(ram + address, text.c_str(), text.size() + 1);
			printf("[tick %u] poke %08x %s\n", tick, address, text.c_str());
		}
		else if(verb == "poke32" && !e.bad && address + 4 <= RAM_SIZE)
		{
			m.w32(address, static_cast<uint32_t>(strtoul(text.c_str(), nullptr, 0)));
			printf("[tick %u] poke32 %08x %s\n", tick, address, text.c_str());
		}
		else if(verb == "echo")
			printf("[tick %u] frame %llu: %s %s\n", tick, static_cast<unsigned long long>(frame), target.c_str(), text.c_str());
		fflush(stdout);
	}
	bool acted = range.first != range.second;
	m_actions.erase(range.first, range.second);
	if(m_log && acted) fflush(m_log);
}
