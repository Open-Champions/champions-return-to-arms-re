// See RtaOnline.h.
//
// What is read from the game (SLUS-20973 v2.00; names.tsv, symbols/ui.tsv, symbols/netlib.tsv,
// docs/netlib.md "Lobby state word", docs/issues/live-rig.md section 19):
//
//   0x41b510  g_inFrontend (u8)        0x41b721  g_levelName ("intro" at the title screen)
//   0x4f6b78  g_frontendState          0 main menu, 1 normal / internet game, 10 the lobby
//   0x4f6b7c  g_frontendMenu           the menu table: 16 bytes an entry, the name's address
//                                      first; the entry after the last holds the cursor
//   0x4d8a10  the menu's fade (float), 1.0 when it takes input
//   0x506160  g_lobbyState             2 network setting, 4 log-in, 3 account, 5 game list
//   0x506148 / 0x50614c / 0x506150 / 0x506144   the window of each of those
//   0x5071f4  the on-screen keyboard's window; +0x14 is 1 while it is open
//
// and inside the windows (offsets found by running the game and by reading its code; the
// functions are FUN_0033ed70 / 0033fab8 for the network window, 0033a1f0 / 00339a20 for
// the log-in window, 00336368 / 00335f60 / 00335bf0 for the account window):
//
//   network   +0xdb4 state (0 reading the card, 3 the list of settings, 1 already
//             connected, 7 signed in - each of the last three goes on with cross),
//             +0x4354 settings found, +0xd88 a message box
//   log-in    +0x165c state (1 terms, 2 the form, 4 request sent, 6 refused, 8 to the
//             account form, 9 to the game list), +0x115c the terms box, +0x1148 a message
//             box, +0x1630 / 0x1634 / 0x1638 the "save on the memory card?" choice
//   account   +0x229c state (0 the form, 2 request sent, 3 refused, 4 / 5 made),
//             +0x2288 a message box, +0x22b0 a request under way
//   game list +0xc248 where it goes next (0: it stays), +0xc244 a message box (the "Host /
//             Search" choice is one: cross hosts), +0xc24c 1 while that choice is up and
//             2 when the window shows the form for a game of one's own, +0xc210 the form's
//             name field, +0xc258 the pane that has the pad (+0x31c: the list of games),
//             +0xc249 the highlighted game, +0x314 the lobby client
//   client    +0x60 games in the list (u16), +0x98 the list: 0xb8 bytes a game, its
//             name as 16-bit characters at +0x22
//   0x506160 = 8 to 11: the character screens (the game's own, not the lobby's); they end
//             in 5 (the form, for a host) or 6 (the room: window at 0x506140)
//   0x4fbbe2  1 when a character was chosen there
//
// The character screens (playerSel_task 0x225478 and the card screen memcard_importScreen
// 0x21fa2c, seen by running the game and read from its code):
//   0x8e2c02  the page (u8): 1 race and class (triangle: "Import"), 2 appearance, 3 ability
//             points, 4 the name, 5 done, 8 the sheet of an imported character (cross accepts)
//   0x88d3a0  g_memcardState: -1 none, 9 the "Import Character" list
//   0x88d3a8  that screen's own state: 1 the list takes the pad (up, down, cross takes the
//             entry, circle "New", triangle "Re-Scan"); 0xd to 0xf the entry is being
//             fetched; 0x13, 0x14 an error; 0x16, 0x17 leaving; the rest is the scan
//   0x4f9230  entries in the list;  0x8e1b43  the highlighted one (u8)
//   0x4f8ee4  the list: 0xf4 bytes an entry; +2 its kind (2: kept by the server, "RTA
//             Net"; 0 and 1: on a memory card), +0x48 the server's number for it, +0x4c its
//             name, +0x9c its class, +0xa5 its level
//   0x4d8af0  g_players: the character in use is record 0 while the lobby screens are up;
//             its name first, its class at +0x50
//
// A text field (class vtable 0x51cdd0 at +0x48) holds what it shows at +0x52 and its
// value at +0x2ca, both 16-bit characters; +0x2c9 is one more than the longest text it
// takes and +0x44c says that it shows stars. The log-in window has two (+0x8a8 name,
// +0xcf8 password), the account window six (+0x8a8 name, +0xcf8 and +0x1148 password,
// +0x1598 e-mail, +0x19e8 date of birth, +0x1e38 chat handle), 0x450 bytes apart.
#include "RtaOnline.h"
#include "RtaNet.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <random>
#include <sstream>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

using namespace Rta;

namespace
{
	const uint32_t A_IN_FRONTEND = 0x41B510, A_LEVEL_NAME = 0x41B721;
	const uint32_t A_FE_STATE = 0x4F6B78, A_FE_MENU = 0x4F6B7C, A_FE_FADE = 0x4D8A10;
	const uint32_t A_LOBBY_STATE = 0x506160;
	const uint32_t A_WIN_ROOM = 0x506140, A_CHARACTER_CHOSEN = 0x4FBBE2;
	const uint32_t A_WIN_LIST = 0x506144, A_WIN_NET = 0x506148, A_WIN_LOGIN = 0x50614C, A_WIN_ACCOUNT = 0x506150;
	const uint32_t A_KEYBOARD = 0x5071F4;
	const uint32_t VT_TEXTBOX = 0x51CDD0;

	const uint32_t NET_STATE = 0xDB4, NET_SETTINGS = 0x4354, NET_BOX = 0xD88;
	const uint32_t LOGIN_STATE = 0x165C, LOGIN_TERMS = 0x115C, LOGIN_BOX = 0x1148, LOGIN_PENDING = 0x1660;
	const uint32_t LOGIN_SAVE_LIST = 0x1630, LOGIN_SAVE_COUNT = 0x1634, LOGIN_SAVE_CHOICE = 0x1638;
	const uint32_t LOGIN_NAME = 0x8A8, LOGIN_PASSWORD = 0xCF8;
	const uint32_t ACCOUNT_STATE = 0x229C, ACCOUNT_BOX = 0x2288, ACCOUNT_PENDING = 0x22B0;
	const uint32_t ACCOUNT_FIELD[6] = {0x8A8, 0xCF8, 0x1148, 0x1598, 0x19E8, 0x1E38};
	const uint32_t LIST_NEXT = 0xC248, LIST_BOX = 0xC244, LIST_HOSTING = 0xC24C, LIST_NAME_FIELD = 0xC210, LIST_FOCUS = 0xC258, LIST_PANE = 0x31C, LIST_CURSOR = 0xC249, LIST_CLIENT = 0x314;
	const uint32_t CLIENT_GAMES = 0x60, CLIENT_GAME_LIST = 0x98, GAME_SIZE = 0xB8, GAME_NAME = 0x22;
	const uint32_t A_SEL_PAGE = 0x8E2C02, A_CARD_STATE = 0x88D3A0, A_CARD_SUB = 0x88D3A8;
	const uint32_t A_IMPORT_COUNT = 0x4F9230, A_IMPORT_CURSOR = 0x8E1B43, A_IMPORT_LIST = 0x4F8EE4;
	const uint32_t ENTRY_SIZE = 0xF4, ENTRY_KIND = 2, ENTRY_ID = 0x48, ENTRY_NAME = 0x4C, ENTRY_CLASS = 0x9C;
	const uint32_t A_PLAYERS = 0x4D8AF0, PLAYER_CLASS = 0x50;
	const uint32_t FIELD_SHOWN = 0x52, FIELD_LIMIT = 0x2C9, FIELD_VALUE = 0x2CA, FIELD_STARS = 0x44C, FIELD_CLASS = 0x48;

	const char* PLACEHOLDER_BIRTH = "01/01/1980"; // the form asks for mm/dd/yyyy
	const char* PLACEHOLDER_MAIL = "@example.invalid";
	const unsigned int PASSWORD_LENGTH = 14; // the log-in form takes 15 at most

	const int64_t NO_CHANGE_LIMIT = 20000; // milliseconds
	const int64_t BOOT_LIMIT = 90000;
	const int64_t NAME_LIMIT_UNATTENDED = 120000;
	const int64_t GAME_LIMIT = 120000; // for a game with the code to show up in the list
	const int64_t CHARACTER_LIMIT = 40000; // for the character used last to be taken by itself

	int64_t NowMs()
	{
		return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
	}
}

// the machine's main memory, with every access checked
class COnline::CMem
{
public:
	CMem(uint8_t* ram, uint32_t size)
	    : m_ram(ram)
	    , m_size(size)
	{
	}
	bool Ok(uint32_t address, uint32_t length) const
	{
		address &= 0x1FFFFFFF;
		return m_ram && address != 0 && address < m_size && length <= m_size - address;
	}
	uint8_t U8(uint32_t address) const
	{
		return Ok(address, 1) ? m_ram[address & 0x1FFFFFFF] : 0;
	}
	uint16_t U16(uint32_t address) const
	{
		uint16_t value = 0;
		if(Ok(address, 2)) memcpy(&value, m_ram + (address & 0x1FFFFFFF), 2);
		return value;
	}
	uint32_t U32(uint32_t address) const
	{
		uint32_t value = 0;
		if(Ok(address, 4)) memcpy(&value, m_ram + (address & 0x1FFFFFFF), 4);
		return value;
	}
	float F32(uint32_t address) const
	{
		float value = 0;
		if(Ok(address, 4)) memcpy(&value, m_ram + (address & 0x1FFFFFFF), 4);
		return value;
	}
	// a window or a table of the game: an address inside main memory
	uint32_t Pointer(uint32_t address) const
	{
		uint32_t value = U32(address);
		return Ok(value, 4) ? value : 0;
	}
	std::string Str(uint32_t address, uint32_t most) const
	{
		std::string text;
		for(uint32_t i = 0; i < most && Ok(address + i, 1); i++)
		{
			char c = static_cast<char>(m_ram[(address + i) & 0x1FFFFFFF]);
			if(c == 0) break;
			text += c;
		}
		return text;
	}
	// 16-bit characters; anything that is not plain ASCII comes out as a character no
	// name or password of ours holds
	std::string Wide(uint32_t address, uint32_t most) const
	{
		std::string text;
		for(uint32_t i = 0; i < most && Ok(address + i * 2, 2); i++)
		{
			uint16_t c = U16(address + i * 2);
			if(c == 0) break;
			text += (c >= 32 && c < 127) ? static_cast<char>(c) : '\x01';
		}
		return text;
	}
	void PutWide(uint32_t address, const std::string& text) const
	{
		if(!Ok(address, static_cast<uint32_t>(text.size() * 2 + 2))) return;
		uint8_t* at = m_ram + (address & 0x1FFFFFFF);
		for(size_t i = 0; i < text.size(); i++)
		{
			at[i * 2] = static_cast<uint8_t>(text[i]);
			at[i * 2 + 1] = 0;
		}
		at[text.size() * 2] = at[text.size() * 2 + 1] = 0;
	}
	void Put32(uint32_t address, uint32_t value) const
	{
		if(Ok(address, 4)) memcpy(m_ram + (address & 0x1FFFFFFF), &value, 4);
	}

private:
	uint8_t* m_ram;
	uint32_t m_size;
};

// ---- names, passwords, codes ----------------------------------------------------------------

std::string COnline::CheckName(const std::string& name)
{
	// The game's name fields (log-in name, chat handle) take 15 characters; the server
	// refuses a chat handle longer than that and its own rule for a name is 3 to 20
	// (docs/lobby-protocol.md 8.1). Letters and digits: what the game's keyboard has and
	// what cannot be misread in a list.
	if(name.size() < 3) return "A player name has at least 3 characters.";
	if(name.size() > 15) return "A player name has at most 15 characters.";
	for(char c : name)
	{
		bool fine = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
		if(!fine) return "A player name has letters and digits only (A-Z, a-z, 0-9): no spaces, no other signs.";
	}
	return std::string();
}

std::string COnline::MakePassword()
{
	static const char keys[] = "abcdefghijklmnopqrstuvwxyz0123456789"; // keys the game's keyboard has without its shift
	std::random_device random;
	std::uniform_int_distribution<int> pick(0, static_cast<int>(sizeof(keys)) - 2);
	std::string password;
	for(unsigned int i = 0; i < PASSWORD_LENGTH; i++) password += keys[pick(random)];
	return password;
}

std::string COnline::CheckCode(const std::string& code)
{
	// the game takes no name of fewer than four characters for a game
	if(code.size() < 4 || code.size() > 8) return "A game code has 4 to 8 letters or digits.";
	for(char c : code)
	{
		bool fine = (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
		if(!fine) return "A game code has letters and digits only.";
	}
	return std::string();
}

std::string COnline::MakeCode()
{
	// four letters that cannot be taken for one another when read out or typed
	static const char letters[] = "ABCDEFGHJKLMNPQRSTUVWXYZ";
	std::random_device random;
	std::uniform_int_distribution<int> pick(0, static_cast<int>(sizeof(letters)) - 2);
	std::string code;
	for(int i = 0; i < 4; i++) code += letters[pick(random)];
	return code;
}

// ---- the saved logins -----------------------------------------------------------------------
// One line per server: server, name, password, "ok" or "pending", separated by tabs.

std::vector<COnline::Login> COnline::ReadLogins() const
{
	std::vector<Login> logins;
	std::ifstream file(m_setup.file);
	std::string line;
	while(std::getline(file, line))
	{
		std::vector<std::string> fields;
		std::string field;
		std::istringstream stream(line);
		while(std::getline(stream, field, '\t')) fields.push_back(field);
		if(fields.size() < 3 || fields[1].empty() || fields[2].empty()) continue;
		Login login;
		login.server = fields[0];
		login.name = fields[1];
		login.password = fields[2];
		login.pending = fields.size() > 3 && fields[3] == "pending";
		logins.push_back(login);
	}
	return logins;
}

bool COnline::WriteLogins(const std::vector<Login>& logins) const
{
	if(m_setup.file.empty()) return false;
	if(logins.empty())
	{
		unlink(m_setup.file.c_str());
		return true;
	}
	// made anew, for the user alone, and put in place in one step
	std::string fresh = m_setup.file + ".new";
	unlink(fresh.c_str());
	int fd = open(fresh.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
	if(fd < 0) return false;
	fchmod(fd, 0600);
	std::string text;
	for(const auto& login : logins) text += login.server + "\t" + login.name + "\t" + login.password + "\t" + (login.pending ? "pending" : "ok") + "\n";
	bool ok = write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size());
	ok = (fsync(fd) == 0) && ok;
	ok = (close(fd) == 0) && ok;
	if(ok) ok = rename(fresh.c_str(), m_setup.file.c_str()) == 0;
	if(!ok) unlink(fresh.c_str());
	return ok;
}

bool COnline::FindLogin(Login& found) const
{
	for(const auto& login : ReadLogins())
	{
		if(login.server == m_setup.server)
		{
			found = login;
			return true;
		}
	}
	return false;
}

bool COnline::StoreLogin(const Login& login) const
{
	auto logins = ReadLogins();
	logins.erase(std::remove_if(logins.begin(), logins.end(), [&](const Login& other) { return other.server == login.server; }), logins.end());
	logins.push_back(login);
	return WriteLogins(logins);
}

bool COnline::DropLogin() const
{
	auto logins = ReadLogins();
	size_t before = logins.size();
	logins.erase(std::remove_if(logins.begin(), logins.end(), [&](const Login& other) { return other.server == m_setup.server; }), logins.end());
	if(logins.size() == before) return false;
	return WriteLogins(logins);
}

bool COnline::HasLogin() const
{
	Login login;
	return FindLogin(login);
}

std::string COnline::LoginName() const
{
	Login login;
	return FindLogin(login) ? login.name : std::string();
}

bool COnline::Forget()
{
	bool dropped = DropLogin();
	Log(dropped ? "online: the saved login for this server was deleted" : "online: there was no saved login for this server");
	return dropped;
}

// ---- the character used last ----------------------------------------------------------------
// One line per server: server, name, class, the server's number for it (0: not known),
// separated by tabs. A character's name is no secret (every player in a game sees it).

std::vector<COnline::Character> COnline::ReadCharacters() const
{
	std::vector<Character> characters;
	std::ifstream file(m_setup.characterFile);
	std::string line;
	while(std::getline(file, line))
	{
		std::vector<std::string> fields;
		std::string field;
		std::istringstream stream(line);
		while(std::getline(stream, field, '\t')) fields.push_back(field);
		if(fields.size() < 4 || fields[1].empty()) continue;
		Character character;
		character.server = fields[0];
		character.name = fields[1];
		character.classId = static_cast<uint32_t>(strtoul(fields[2].c_str(), nullptr, 10));
		character.id = static_cast<uint32_t>(strtoul(fields[3].c_str(), nullptr, 10));
		characters.push_back(character);
	}
	return characters;
}

bool COnline::FindCharacter(Character& found) const
{
	for(const auto& character : ReadCharacters())
	{
		if(character.server == m_setup.server)
		{
			found = character;
			return true;
		}
	}
	return false;
}

bool COnline::StoreCharacter(const Character& character) const
{
	if(m_setup.characterFile.empty()) return false;
	auto characters = ReadCharacters();
	characters.erase(std::remove_if(characters.begin(), characters.end(), [&](const Character& other) { return other.server == character.server; }), characters.end());
	characters.push_back(character);
	std::string fresh = m_setup.characterFile + ".new";
	std::ofstream file(fresh, std::ios::trunc);
	for(const auto& c : characters) file << c.server << "\t" << c.name << "\t" << c.classId << "\t" << c.id << "\n";
	file.close();
	if(!file || rename(fresh.c_str(), m_setup.characterFile.c_str()) != 0)
	{
		unlink(fresh.c_str());
		return false;
	}
	return true;
}

std::string COnline::LastCharacter() const
{
	Character character;
	return FindCharacter(character) ? character.name : std::string();
}

// ---- from other threads ---------------------------------------------------------------------

void COnline::Configure(const Setup& setup)
{
	m_setup = setup;
}

void COnline::Log(const std::string& line) const
{
	if(m_setup.log) m_setup.log(line);
}

void COnline::Start(Goal goal, const std::string& code, bool powerOn, bool chooseCharacter)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_startWanted = true;
	m_stopWanted = false;
	m_wantedGoal = goal;
	m_wantedCode = code;
	m_wantedPowerOn = powerOn;
	m_wantedChoose = chooseCharacter;
}

void COnline::Stop(const std::string& why)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_stopWanted = true;
	m_startWanted = false;
	m_stopWhy = why;
}

void COnline::GiveName(const std::string& name)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_givenName = name;
	m_nameGiven = true;
	m_nameDeclined = false;
}

void COnline::DeclineName()
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_nameDeclined = true;
	m_nameGiven = false;
}

void COnline::QueueNames(const std::vector<std::string>& names)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	m_queuedNames.insert(m_queuedNames.end(), names.begin(), names.end());
}

bool COnline::Active() const
{
	std::lock_guard<std::mutex> lock(m_mutex);
	return m_startWanted || m_stage != "idle";
}

std::string COnline::Note() const
{
	std::lock_guard<std::mutex> lock(m_mutex);
	if(m_noteUntil != 0 && NowMs() > m_noteUntil) return std::string();
	return m_note;
}

std::string COnline::Report() const
{
	std::lock_guard<std::mutex> lock(m_mutex);
	std::string outcome = m_outcome;
	std::replace(outcome.begin(), outcome.end(), ' ', '_');
	std::string stage = m_stage;
	std::replace(stage.begin(), stage.end(), ' ', '_');
	return "stage=" + stage + " outcome=" + (outcome.empty() ? "-" : outcome) + " code=" + (m_code.empty() ? "-" : m_code);
}

std::string COnline::Code() const
{
	std::lock_guard<std::mutex> lock(m_mutex);
	return m_code;
}

// ---- the machine's thread -------------------------------------------------------------------

void COnline::Say(const std::string& stage)
{
	std::lock_guard<std::mutex> lock(m_mutex);
	if(m_stage == stage) return;
	m_stage = stage;
	m_note = "Going online: " + stage + "...";
	m_noteUntil = 0;
}

void COnline::Finish(const std::string& note, int64_t showFor)
{
	m_active = m_driving = false;
	m_buttons = 0;
	Log("online: done - " + note + "; the controls are the player's");
	std::lock_guard<std::mutex> lock(m_mutex);
	m_stage = "idle";
	m_outcome = "ok: " + note;
	m_note = "Online: " + note + ". The controls are yours.";
	m_noteUntil = NowMs() + showFor;
}

void COnline::Fail(const std::string& why)
{
	if(!m_active) return;
	m_active = m_driving = false;
	m_buttons = 0;
	Log("online: STOPPED - " + why + "; the controls are the player's, where the game is");
	std::lock_guard<std::mutex> lock(m_mutex);
	m_stage = "idle";
	m_outcome = "stopped: " + why;
	m_note = "Going online stopped: " + why + ". The controls are yours.";
	m_noteUntil = NowMs() + 90000;
}

void COnline::Press(uint32_t mask, unsigned int hold, unsigned int settle)
{
	m_buttons = mask;
	m_hold = hold;
	m_settle = settle;
	m_presses++;
}

void COnline::OnExecutable(bool)
{
	m_frontEndSeen = false;
}

// true when m_name holds a name to use
bool COnline::NeedName(const std::string& why)
{
	bool ask = false, declined = false;
	{
		std::lock_guard<std::mutex> lock(m_mutex);
		while(m_name.empty() && !m_queuedNames.empty())
		{
			std::string name = m_queuedNames.front();
			m_queuedNames.erase(m_queuedNames.begin());
			if(CheckName(name).empty())
				m_name = name;
			else
				Log("online: a name given for this test is not one the game takes; it is left out");
		}
		if(m_name.empty() && m_nameGiven)
		{
			m_nameGiven = false;
			m_nameAsked = false;
			if(CheckName(m_givenName).empty()) m_name = m_givenName;
		}
		if(m_name.empty() && m_nameDeclined)
		{
			m_nameDeclined = false;
			m_nameAsked = false;
			declined = true;
		}
		if(m_name.empty() && !declined && !m_nameAsked)
		{
			m_nameAsked = true;
			m_waitingSince = NowMs();
			ask = true;
		}
	}
	if(!m_name.empty())
	{
		m_lastChange = NowMs();
		return true;
	}
	if(declined)
	{
		Fail("no player name was given (log in on the game's own screen, or choose Play Online again)");
		return false;
	}
	if(ask)
	{
		Log(why.empty() ? "online: no saved login for this server: asking for a player name" : "online: asking for another player name");
		if(m_setup.askName) m_setup.askName(why);
	}
	if(!m_setup.personPresent && NowMs() - m_waitingSince > NAME_LIMIT_UNATTENDED) Fail("no player name was given (a test run: send 'online name NAME' on the control socket)");
	return false;
}

bool COnline::BoxFits(const CMem& mem, uint32_t box, const std::string& text, bool secret) const
{
	return mem.U32(box + FIELD_CLASS) == VT_TEXTBOX && text.size() < mem.U8(box + FIELD_LIMIT) && text.size() < 100 && ((mem.U32(box + FIELD_STARS) != 0) == secret);
}

void COnline::BoxWrite(const CMem& mem, uint32_t box, const std::string& text, bool secret) const
{
	mem.PutWide(box + FIELD_VALUE, text);
	mem.PutWide(box + FIELD_SHOWN, secret ? std::string(text.size(), '*') : text);
}

bool COnline::BoxHolds(const CMem& mem, uint32_t box, const std::string& text) const
{
	return mem.U32(box + FIELD_CLASS) == VT_TEXTBOX && mem.Wide(box + FIELD_VALUE, 127) == text;
}

COnline::Screen COnline::Observe(const CMem& mem, bool isGame) const
{
	Screen s;
	if(!isGame) return s;
	bool frontEnd = mem.U8(A_IN_FRONTEND) == 1 && mem.Str(A_LEVEL_NAME, 8) == "intro";
	if(!frontEnd)
	{
		s.kind = m_frontEndSeen ? Screen::InGame : Screen::Boot;
		return s;
	}
	uint32_t fe = mem.U32(A_FE_STATE), lobby = mem.U32(A_LOBBY_STATE);
	uint32_t keyboard = mem.Pointer(A_KEYBOARD);
	uint32_t keyboardOpen = (keyboard && mem.U32(keyboard + 0x14) != 0) ? 1 : 0;
	if(fe == 10)
	{
		s.kind = Screen::LobbyWait;
		s.a = lobby;
		uint32_t window = 0;
		switch(lobby)
		{
		case 2:
			if(!(window = mem.Pointer(A_WIN_NET))) return s;
			s.kind = Screen::Net;
			s.a = mem.U32(window + NET_STATE);
			s.b = (static_cast<int32_t>(mem.U32(window + NET_SETTINGS)) > 0) ? 1 : 0;
			s.c = mem.U32(window + NET_BOX) != 0;
			break;
		case 4:
			if(!(window = mem.Pointer(A_WIN_LOGIN))) return s;
			s.kind = Screen::LoginForm;
			s.a = mem.U32(window + LOGIN_STATE);
			s.b = mem.U32(window + LOGIN_TERMS) != 0;
			s.c = mem.U32(window + LOGIN_BOX) != 0;
			s.d = (mem.U32(window + LOGIN_PENDING) != 0 ? 1 : 0) | (keyboardOpen << 1);
			break;
		case 3:
			if(!(window = mem.Pointer(A_WIN_ACCOUNT))) return s;
			s.kind = Screen::Account;
			s.a = mem.U32(window + ACCOUNT_STATE);
			s.b = mem.U32(window + ACCOUNT_BOX) != 0;
			s.c = mem.U32(window + ACCOUNT_PENDING) != 0;
			s.d = keyboardOpen;
			break;
		case 5:
			if(!(window = mem.Pointer(A_WIN_LIST))) return s;
			s.kind = Screen::List;
			s.a = mem.U8(window + LIST_NEXT);
			s.b = mem.U32(window + LIST_BOX) != 0;
			s.c = mem.U32(window + LIST_HOSTING);
			// keyboard, the list of games has the pad, the form's name field is there; the
			// highlighted game; how many games
			s.d = keyboardOpen | ((mem.U32(window + LIST_FOCUS) == window + LIST_PANE) ? 2 : 0) | (mem.Pointer(window + LIST_NAME_FIELD) ? 4 : 0);
			s.d |= static_cast<uint32_t>(mem.U8(window + LIST_CURSOR)) << 8;
			s.d |= static_cast<uint32_t>(mem.U16(mem.Pointer(window + LIST_CLIENT) + CLIENT_GAMES) & 0xFF) << 16;
			break;
		case 6:
			if(!(window = mem.Pointer(A_WIN_ROOM))) return s;
			s.kind = Screen::Room;
			break;
		case 8:
		case 9:
		case 0xA:
		case 0xB:
		{
			s.kind = Screen::CharMenu;
			s.a = lobby;
			s.b = mem.U8(A_CHARACTER_CHOSEN);
			// the page; whether the "Import Character" list is up (1) or another card screen
			// (2); what that list is doing: 0 scanning, 1 it takes the pad, 2 fetching the
			// entry taken, 3 an error, 4 something else; its entries and its cursor
			int32_t card = static_cast<int32_t>(mem.U32(A_CARD_STATE));
			uint32_t sub = mem.U32(A_CARD_SUB), list = 0;
			if(card == 9) list = (sub == 1) ? 1 : ((sub >= 0xD && sub <= 0xF) ? 2 : ((sub == 0x13 || sub == 0x14) ? 3 : ((sub >= 0x10 && sub <= 0x12) ? 4 : 0)));
			s.c = mem.U8(A_SEL_PAGE) | ((card == 9 ? 1u : (card == -1 ? 0u : 2u)) << 8) | (list << 16);
			if(card == 9 && list != 0) s.d = (mem.U32(A_IMPORT_COUNT) & 0xFF) | (static_cast<uint32_t>(mem.U8(A_IMPORT_CURSOR)) << 8);
			break;
		}
		case 1:
		case 0xD:
		case 0xE:
		case 0xF:
			break;
		default:
			s.kind = Screen::LobbyOther;
			break;
		}
		s.window = window;
		return s;
	}
	s.kind = Screen::FeOther;
	s.a = fe;
	if(fe != 0 && fe != 1) return s;
	// the menu table: which entries, and where the cursor is
	uint32_t table = mem.Pointer(A_FE_MENU);
	if(!table) return s;
	std::vector<std::string> names;
	uint32_t cursor = 0;
	for(uint32_t i = 0; i < 12; i++)
	{
		uint32_t name = mem.U32(table + i * 16);
		if(name == 0)
		{
			cursor = mem.U32(table + i * 16 + 4) & 0x7F;
			break;
		}
		names.push_back(mem.Str(name, 40));
	}
	uint32_t ready = (mem.F32(A_FE_FADE) >= 1.0f) ? 1 : 0;
	if(fe == 0 && !names.empty() && names[0] == "menu_startnewgame")
	{
		s.kind = Screen::FeMain;
		s.a = cursor;
		s.b = 0;
		s.c = ready;
	}
	else if(fe == 1)
	{
		auto found = std::find(names.begin(), names.end(), "menu_netgame");
		if(found == names.end()) return s;
		s.kind = Screen::FeType;
		s.a = cursor;
		s.b = static_cast<uint32_t>(found - names.begin());
		s.c = ready;
	}
	return s;
}

std::string COnline::Describe(const Screen& s) const
{
	char text[160];
	switch(s.kind)
	{
	case Screen::NoGame:
		return "the game is not running yet";
	case Screen::Boot:
		return "the game is starting (memory card check, logos)";
	case Screen::InGame:
		return "a level is loaded";
	case Screen::FeMain:
		snprintf(text, sizeof(text), "the title screen's menu (cursor on entry %u%s)", s.a + 1, s.c ? "" : ", fading in");
		return text;
	case Screen::FeType:
		snprintf(text, sizeof(text), "Normal Game / Internet Game (cursor on entry %u%s)", s.a + 1, s.c ? "" : ", fading in");
		return text;
	case Screen::FeOther:
		snprintf(text, sizeof(text), "another menu of the game (front-end state %u)", s.a);
		return text;
	case Screen::LobbyWait:
		snprintf(text, sizeof(text), "the lobby screens are being made (lobby state %u)", s.a);
		return text;
	case Screen::Net:
		snprintf(text, sizeof(text), "the network setting screen (state %u, %s%s)", s.a, s.b ? "a setting is there" : "no setting", s.c ? ", a message box" : "");
		return text;
	case Screen::LoginForm:
		snprintf(text, sizeof(text), "the log-in screen (state %u%s%s%s%s)", s.a, s.b ? ", the terms" : "", s.c ? ", a message box" : "", (s.d & 1) ? ", a request under way" : "", (s.d & 2) ? ", keyboard open" : "");
		return text;
	case Screen::Account:
		snprintf(text, sizeof(text), "the account screen (state %u%s%s%s)", s.a, s.b ? ", a message box" : "", s.c ? ", a request under way" : "", s.d ? ", keyboard open" : "");
		return text;
	case Screen::List:
		snprintf(text, sizeof(text), "the game list, Game Selection and Chat (state %u%s%s, %u game(s), cursor on %u%s)", s.a, s.b ? ", a message box" : "", (s.c == 2) ? ", the form for a new game" : ((s.c == 1) ? ", Host / Search" : ""),
		         (s.d >> 16) & 0xFF, ((s.d >> 8) & 0xFF) + 1, (s.d & 2) ? "" : ", pad in another pane");
		return text;
	case Screen::CharMenu:
	{
		static const char* lists[] = {"being read", "open", "fetching the entry taken", "an error", "a question"};
		if(((s.c >> 8) & 0xFF) == 1)
			snprintf(text, sizeof(text), "the character screens (lobby state %u%s): the list of stored characters, %s, %u in it, cursor on %u", s.a, s.b ? ", a character is chosen" : "", lists[std::min<uint32_t>((s.c >> 16) & 0xFF, 4)], s.d & 0xFF, ((s.d >> 8) & 0xFF) + 1);
		else
			snprintf(text, sizeof(text), "the character screens (lobby state %u%s, page %u%s)", s.a, s.b ? ", a character is chosen" : "", s.c & 0xFF, ((s.c >> 8) & 0xFF) == 2 ? ", a memory card screen" : "");
		return text;
	}
	case Screen::Room:
		return "a game's room";
	case Screen::LobbyOther:
		snprintf(text, sizeof(text), "a lobby screen this does not handle (lobby state %u)", s.a);
		return text;
	}
	return "?";
}

void COnline::Tick(uint8_t* ram, uint32_t ramSize, bool isGame)
{
	CMem mem(ram, ramSize);
	// the network behind the adaptor is told, once a frame, whether the game is in a game's
	// room (lobby state 6): it shows another player's disconnect half a second late there
	// (RtaNet.cpp, "A peer's disconnect, held back")
	CNet::NoteGame(isGame && mem.U32(A_LOBBY_STATE) == 6);
	if(isGame && mem.U8(A_IN_FRONTEND) == 1 && mem.Str(A_LEVEL_NAME, 8) == "intro") m_frontEndSeen = true;

	bool start = false, stop = false;
	std::string stopWhy;
	{
		std::lock_guard<std::mutex> lock(m_mutex);
		start = m_startWanted;
		stop = m_stopWanted;
		stopWhy = m_stopWhy;
		m_startWanted = m_stopWanted = false;
		if(start)
		{
			m_goal = m_wantedGoal;
			m_powerOn = m_wantedPowerOn;
			m_chooseCharacter = m_wantedChoose;
			m_code = m_wantedCode;
			m_outcome.clear();
			m_stage = "starting";
			m_note = "Going online...";
			m_noteUntil = 0;
			m_nameAsked = false;
			m_nameDeclined = false;
			m_nameGiven = false;
		}
	}
	if(stop && m_active) Fail(stopWhy.empty() ? "stopped on request" : stopWhy);
	if(start)
	{
		m_active = true;
		m_buttons = 0;
		m_hold = m_settle = 0;
		m_haveScreen = false;
		m_sameFrames = 0;
		m_started = m_lastChange = NowMs();
		m_rank = 0;
		m_presses = 0;
		m_loginTried = m_loginWritten = m_loginRefused = false;
		m_name.clear();
		m_password.clear();
		m_formWritten = m_submitted = m_createFailed = false;
		m_namesRefused = 0;
		m_listSeen = false;
		m_characterSeen = m_gamePressed = m_gameSent = m_joinPressed = m_joinSent = false;
		m_lookingSince = 0;
		m_charAuto = m_charPickPressed = m_charFetching = m_charStored = m_charOpen = false;
		m_lastCharacter = Character();
		m_pickedName.clear();
		m_pickedId = 0;
		m_askEarly = !HasLogin();
		Log(std::string("online: going online by itself") + (m_powerOn ? " from power-on" : "") + "; server " + m_setup.serverText + "; " + (HasLogin() ? "a saved login for it is there" : "no saved login for it yet"));
	}
	if(!m_active) return;
	// the character screens are the player's own to do, unless the character used last is
	// being taken from the game's list
	m_driving = isGame && !(m_haveScreen && m_screen.kind == Screen::CharMenu && !m_charAuto);

	if(m_hold > 0)
	{
		if(--m_hold == 0) m_buttons = 0;
		return;
	}
	if(m_settle > 0)
	{
		m_settle--;
		return;
	}

	Screen now = Observe(mem, isGame);
	int64_t clock = NowMs();
	if(!m_haveScreen || !(now == m_screen))
	{
		m_screen = now;
		m_haveScreen = true;
		m_sameFrames = 0;
		m_lastChange = clock;
		m_presses = 0;
		Log("online: " + Describe(now));
	}
	else
		m_sameFrames++;

	// the way is one-directional: a screen that was passed coming back means something
	// went wrong (a lost connection, an error that threw the game out of the lobby)
	static const int ranks[] = {0, 1, -1, 2, 3, -1, -2, 5, 6, 7, 8, 8, 9, -1};
	int rank = ranks[now.kind];
	if(rank >= 0)
	{
		if(rank < m_rank)
		{
			Fail("the game went back to " + Describe(now));
			return;
		}
		m_rank = rank;
	}

	// a player name is asked for as soon as the game runs, so that it can be typed while
	// the game is on its way
	bool waitingForName = false;
	if(isGame && m_askEarly)
	{
		if(NeedName("")) m_askEarly = false;
		if(!m_active) return;
	}

	Act(mem, now);
	if(!m_active) return;

	{
		std::lock_guard<std::mutex> lock(m_mutex);
		waitingForName = m_nameAsked;
	}
	if(now.kind == Screen::NoGame) return; // a person may still be choosing the disc image
	if(now.kind == Screen::CharMenu)
	{
		m_lastChange = clock; // a person is choosing or making a character: no hurry
		// taking the character used last has its own limit, and failing it is no failure:
		// the screens are then the player's
		if(m_charAuto && clock - m_charSince > CHARACTER_LIMIT) HandOverCharacter("it took too long");
		return;
	}
	if(now.kind == Screen::List && m_goal == Goal::Join && !m_joinSent)
	{
		m_lastChange = clock; // waiting for the game to show up has its own limit
		return;
	}
	if(now.kind == Screen::Boot)
	{
		if(clock - m_started > BOOT_LIMIT) Fail("the game did not reach its title screen in 90 seconds");
		return;
	}
	if(waitingForName && (now.kind == Screen::LoginForm || now.kind == Screen::Account))
	{
		m_lastChange = clock;
		return;
	}
	if(clock - m_lastChange > NO_CHANGE_LIMIT)
	{
		if(now.kind == Screen::LoginForm && now.a == 0)
			Fail("the lobby server " + m_setup.serverText + " did not answer for 20 seconds (the game goes on trying: \"Connecting\")");
		else
			Fail("nothing changed for 20 seconds at " + Describe(now));
	}
}

void COnline::Act(const CMem& mem, const Screen& s)
{
	if(m_charOpen && !m_charStored && mem.U8(A_CHARACTER_CHOSEN) == 1) RememberCharacter(mem);
	switch(s.kind)
	{
	case Screen::NoGame:
		Say("waiting for the game to start");
		return;
	case Screen::Boot:
		if(!m_powerOn && m_frontEndSeen)
		{
			Fail("a game is running: Play Online starts from the title screen");
			return;
		}
		// the memory card questions (slot 1; on a blank card: make the save data) and the
		// logos all go on with cross
		Say("starting the game");
		if(m_sameFrames >= 2) Press(m_setup.cross, 6, 40);
		return;
	case Screen::InGame:
		Fail("a game is running: Play Online starts from the title screen");
		return;
	case Screen::FeMain:
		Say("at the title screen");
		if(m_sameFrames < 10 || !s.c) return;
		if(s.a != 0)
			Press(m_setup.up, 6, 14);
		else
			Press(m_setup.cross, 8, 24);
		return;
	case Screen::FeType:
		Say("choosing Internet Game");
		if(m_sameFrames < 6 || !s.c) return;
		if(s.a < s.b)
			Press(m_setup.down, 6, 14);
		else if(s.a > s.b)
			Press(m_setup.up, 6, 14);
		else
			Press(m_setup.cross, 8, 24);
		return;
	case Screen::FeOther:
		Fail("the game is in " + Describe(s) + ": Play Online starts from the title screen");
		return;
	case Screen::LobbyWait:
		Say("opening the network screens");
		return;
	case Screen::Net:
		ActNet(mem, s);
		return;
	case Screen::LoginForm:
		ActLogin(mem, s);
		return;
	case Screen::Account:
		ActAccount(mem, s);
		return;
	case Screen::List:
		ActList(mem, s);
		return;
	case Screen::CharMenu:
		if(m_goal == Goal::Lobby)
		{
			Fail("the game is at " + Describe(s));
			return;
		}
		ActCharacter(mem, s);
		return;
	case Screen::Room:
		if(m_goal == Goal::Host && m_gamePressed)
			Finish("your game is open - tell your friends the code " + m_code + " - and you are in its room; press cross (Start Game) when they are there", 600000);
		else if(m_goal == Goal::Join && (m_joinPressed || m_joinSent))
			Finish("you are in the room of game " + m_code + "; the host starts it", 60000);
		else
			Fail("the game is in a game's room already");
		return;
	case Screen::LobbyOther:
		Fail("the game is at " + Describe(s));
		return;
	}
}

// The character that is now in use is kept for the next time, per server.
void COnline::RememberCharacter(const CMem& mem)
{
	m_charStored = true;
	Character character;
	character.server = m_setup.server;
	character.name = mem.Str(A_PLAYERS, 31);
	character.classId = mem.U32(A_PLAYERS + PLAYER_CLASS);
	bool fine = !character.name.empty();
	for(char c : character.name) fine = fine && (static_cast<unsigned char>(c) >= 32) && (c != '\t');
	if(!fine)
	{
		Log("online: the character in use has no name that can be kept; none is remembered");
		return;
	}
	if(character.name == m_pickedName) character.id = m_pickedId;
	Log(StoreCharacter(character) ? "online: the character in use is remembered for this server (online-character in the data directory): the next game takes it by itself" : "online: the character in use could NOT be written down for the next time");
}

void COnline::HandOverCharacter(const std::string& why)
{
	if(!m_charAuto) return;
	m_charAuto = false;
	m_buttons = 0;
	m_hold = m_settle = 0;
	Log("online: the character screens are the player's: " + why);
	Say("choose your character yourself (" + why + ") - it goes on by itself when you have");
}

// The character screens of a game hosted or joined. They are the player's - unless the
// character used last on this server is known: then it is taken from the game's own list
// of stored characters (triangle "Import" on the first page, the entry, cross; cross again
// on its sheet). Whatever is not as expected hands the screens to the player where they
// are; so does a button the player holds down while this is going on.
void COnline::ActCharacter(const CMem& mem, const Screen& s)
{
	const uint32_t page = s.c & 0xFF, card = (s.c >> 8) & 0xFF, list = (s.c >> 16) & 0xFF;
	const uint32_t count = s.d & 0xFF, cursor = (s.d >> 8) & 0xFF;
	if(!m_characterSeen)
	{
		m_characterSeen = true;
		m_charSince = NowMs();
		m_charAuto = !m_chooseCharacter && FindCharacter(m_lastCharacter);
		if(m_charAuto)
			Log("online: the character used last on this server is known: taking it from the list of stored characters (a held button hands the screens to the player)");
		else
			Log(m_chooseCharacter ? "online: the character screens are the player's, as asked" : "online: no character has been used on this server from here yet: the character screens are the player's");
	}
	// the entry of the list that is being taken, by this or by the player: its number goes
	// with the name that is remembered
	uint32_t entries = mem.Pointer(A_IMPORT_LIST);
	if(card == 1 && list == 2 && entries && cursor < count)
	{
		uint32_t entry = entries + cursor * ENTRY_SIZE;
		m_pickedName = mem.Str(entry + ENTRY_NAME, 31);
		m_pickedId = (mem.U8(entry + ENTRY_KIND) == 2) ? mem.U32(entry + ENTRY_ID) : 0;
	}
	if(s.b)
	{
		Say("entering the game with your character");
		return;
	}
	m_charOpen = true;
	if(!m_charAuto)
	{
		if(m_chooseCharacter || m_lastCharacter.name.empty()) Say("choose your character (new, or triangle for a stored one) - it goes on by itself when you have");
		return;
	}
	if(m_playerButtons != 0 && !m_charFetching)
	{
		HandOverCharacter("you held a button");
		return;
	}
	const std::string& name = m_lastCharacter.name;
	if(card == 2)
	{
		HandOverCharacter("a memory card screen is up");
		return;
	}
	if(card == 0)
	{
		switch(page)
		{
		case 0: // coming up
			Say("your character " + name + " (hold any button to choose another)");
			return;
		case 1: // race and class: triangle is "Import"
			Say("your character " + name + " (hold any button to choose another)");
			if(m_charPickPressed)
			{
				// back here after the entry was taken: it was not fetched
				if(m_sameFrames >= 60) HandOverCharacter(name + " could not be taken from the list");
				return;
			}
			if(m_sameFrames < 45) return;
			if(m_presses >= 5)
			{
				HandOverCharacter("the list of stored characters does not open");
				return;
			}
			Press(m_setup.triangle, 10, 40);
			return;
		case 8: // the sheet of the character that was fetched
			Say("entering the game with your character " + name);
			if(!m_charPickPressed)
			{
				HandOverCharacter("a character's sheet is up that was not asked for");
				return;
			}
			if(m_sameFrames < 20) return;
			if(m_presses >= 5)
			{
				HandOverCharacter("the character's sheet does not answer");
				return;
			}
			Press(m_setup.cross, 10, 40);
			return;
		case 5: // done: the game is on its way out of these screens
			if(m_charPickPressed)
			{
				Say("entering the game with your character " + name);
				return;
			}
			HandOverCharacter("the screens for a new character are up");
			return;
		default:
			HandOverCharacter("the screens for a new character are up");
			return;
		}
	}
	// the "Import Character" list
	switch(list)
	{
	case 0:
		Say("looking for your character " + name);
		return;
	case 2:
		m_charFetching = true;
		Say("fetching your character " + name);
		return;
	case 1:
		break;
	default:
		HandOverCharacter(list == 3 ? "the game shows an error on the list of stored characters" : "the game asks a question on the list of stored characters");
		return;
	}
	Say("looking for your character " + name);
	if(m_charFetching)
	{
		HandOverCharacter(name + " could not be fetched");
		return;
	}
	if(m_sameFrames < 20) return;
	// by the server's number when it is known and still has that name; else by name and
	// class, those kept by the server first; two that fit are for the player to tell apart
	int found = -1, fits = 0;
	for(int pass = 0; pass < 3 && found < 0 && entries; pass++)
	{
		fits = 0;
		for(uint32_t i = 0; i < count && i < 50; i++)
		{
			uint32_t entry = entries + i * ENTRY_SIZE;
			bool kept = mem.U8(entry + ENTRY_KIND) == 2;
			bool same = mem.Str(entry + ENTRY_NAME, 31) == name;
			bool fit = (pass == 0) ? (kept && same && m_lastCharacter.id != 0 && mem.U32(entry + ENTRY_ID) == m_lastCharacter.id)
			                       : (same && mem.U32(entry + ENTRY_CLASS) == m_lastCharacter.classId && (kept == (pass == 1)));
			if(!fit) continue;
			if(fits++ == 0) found = static_cast<int>(i);
		}
		if(fits > 1) break;
	}
	if(found < 0)
	{
		HandOverCharacter("your character " + name + " is not among the stored ones any more: take another with cross, or circle for a new one");
		return;
	}
	if(fits > 1)
	{
		HandOverCharacter("more than one stored character is called " + name + ": take yours with cross");
		return;
	}
	if(static_cast<uint32_t>(found) != cursor)
	{
		Press((static_cast<uint32_t>(found) > cursor) ? m_setup.down : m_setup.up, 8, 14);
		return;
	}
	if(m_presses >= 4)
	{
		HandOverCharacter("the game does not take " + name + " for this game");
		return;
	}
	m_charPickPressed = true;
	Press(m_setup.cross, 10, 40);
}

void COnline::ActNet(const CMem&, const Screen& s)
{
	if(s.c)
	{
		Fail("the game shows a message on the network setting screen");
		return;
	}
	switch(s.a)
	{
	case 3: // the list of settings on the memory card
		Say("choosing the network setting");
		if(!s.b)
		{
			if(m_sameFrames > 120) Fail("the game finds no network setting on the memory card");
			return;
		}
		if(m_sameFrames >= 10) Press(m_setup.cross, 8, 30);
		return;
	case 1: // "the network is up already" (a second visit in one run)
	case 7: // signed in: on to the lobby
		Say("connecting to the server");
		if(m_sameFrames >= 10) Press(m_setup.cross, 8, 30);
		return;
	case 0:
		Say("reading the network setting");
		return;
	default:
		Say("connecting to the server");
		return;
	}
}

void COnline::ActLogin(const CMem& mem, const Screen& s)
{
	const uint32_t window = s.window, state = s.a;
	const bool terms = s.b != 0, box = s.c != 0, keyboard = (s.d & 2) != 0;
	if(state == 6)
	{
		// "Login failed"
		Login saved;
		if(m_loginTried && FindLogin(saved) && saved.pending)
		{
			// an account that was asked for in an earlier run and never made: start anew
			Log("online: the login kept from an unfinished earlier start is not known to the server; it is dropped");
			DropLogin();
			m_loginRefused = true;
		}
		if(m_loginRefused)
		{
			if(m_sameFrames >= 10) Press(m_setup.cross, 10, 30); // closes the game's box
			return;
		}
		Fail(m_loginTried ? "the server did not accept the saved login for " + m_setup.serverText + " (the game says why). To make a new one: Online > Forget online login, then Play Online"
		                  : "the game shows a message on the log-in screen");
		return;
	}
	if(state == 1 && terms)
	{
		Say("accepting the server's terms");
		if(m_sameFrames >= 10) Press(m_setup.cross, 10, 30);
		return;
	}
	if(state == 2 && !box && !terms)
	{
		if(keyboard)
		{
			Fail("the on-screen keyboard is open on the log-in screen");
			return;
		}
		Login saved;
		if(FindLogin(saved))
		{
			Say("logging in");
			if(m_presses >= 6)
			{
				Fail("the log-in screen does not answer");
				return;
			}
			uint32_t nameBox = window + LOGIN_NAME, passwordBox = window + LOGIN_PASSWORD;
			if(!BoxHolds(mem, nameBox, saved.name) || !BoxHolds(mem, passwordBox, saved.password))
			{
				if(!BoxFits(mem, nameBox, saved.name, false) || !BoxFits(mem, passwordBox, saved.password, true))
				{
					Fail("the log-in screen is not as expected (its fields do not take the saved login)");
					return;
				}
				BoxWrite(mem, nameBox, saved.name, false);
				BoxWrite(mem, passwordBox, saved.password, true);
				// "Save Login/Password?" on the memory card: no. The pair is kept by the
				// application, where "Forget online login" finds it.
				uint32_t list = mem.Pointer(window + LOGIN_SAVE_LIST), count = mem.U32(window + LOGIN_SAVE_COUNT);
				if(list && count == 2)
				{
					for(uint32_t i = 0; i < count; i++)
					{
						if(mem.U32(list + i * 0x14) == 0) mem.Put32(window + LOGIN_SAVE_CHOICE, i);
					}
				}
				m_settle = 3; // read back at a later frame, then send
				return;
			}
			m_loginTried = true;
			Press(m_setup.cross, 10, 30);
			return;
		}
		// no saved login: the account form, once there is a name
		if(m_name.empty())
		{
			Say("waiting for your player name");
			NeedName("");
			return;
		}
		Say("making your player");
		if(m_sameFrames >= 6) Press(m_setup.triangle, 10, 30);
		return;
	}
	if(box && state > 1 && state != 4)
	{
		Fail("the game shows a message on the log-in screen");
		return;
	}
	Say((state == 4 || state == 9) ? "logging in" : (state == 8 ? "making your player" : "connecting to the server"));
}

void COnline::ActAccount(const CMem& mem, const Screen& s)
{
	const uint32_t window = s.window, state = s.a;
	const bool box = s.b != 0, pending = s.c != 0, keyboard = s.d != 0;
	if(state == 3 && box)
	{
		// the game's own box: the account was not made
		if(!m_submitted)
		{
			Fail("the game shows a message on the account screen");
			return;
		}
		Say("the server did not take that name");
		m_createFailed = true;
		if(m_sameFrames >= 10) Press(m_setup.cross, 10, 30);
		return;
	}
	if(state == 4 || state == 5)
	{
		Say("entering the lobby");
		return;
	}
	if(state == 2 || pending)
	{
		Say("making your player");
		return;
	}
	if(state != 0 || box) return; // leaving, or something the watch below will report
	if(keyboard)
	{
		Fail("the on-screen keyboard is open on the account screen");
		return;
	}
	if(m_createFailed)
	{
		m_createFailed = m_submitted = m_formWritten = false;
		DropLogin();
		m_namesRefused++;
		Log("online: the server did not make the account: the name is taken, or it does not accept it");
		m_name.clear();
		m_password.clear();
		m_presses = 0;
		if(m_namesRefused >= 5)
		{
			Fail("the server refused five player names in a row");
			return;
		}
	}
	if(m_name.empty())
	{
		Say(m_namesRefused ? "waiting for another player name" : "waiting for your player name");
		if(!NeedName(m_namesRefused ? "That name is taken on this server (or the server did not accept it). Choose another one." : "")) return;
	}
	Say("making your player");
	if(m_password.empty()) m_password = MakePassword();
	std::string mail = m_name;
	for(auto& c : mail) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
	mail += PLACEHOLDER_MAIL;
	const std::string values[6] = {m_name, m_password, m_password, mail, PLACEHOLDER_BIRTH, m_name};
	const bool secret[6] = {false, true, true, false, false, false};
	bool holds = true;
	for(int i = 0; i < 6; i++) holds = holds && BoxHolds(mem, window + ACCOUNT_FIELD[i], values[i]);
	if(!holds)
	{
		for(int i = 0; i < 6; i++)
		{
			if(!BoxFits(mem, window + ACCOUNT_FIELD[i], values[i], secret[i]))
			{
				Fail("the account screen is not as expected (a field does not take its text)");
				return;
			}
		}
		// kept before it is sent: if the application ends between the server's making the
		// account and its answer, the next start still has the pair and tries it
		Login login;
		login.server = m_setup.server;
		login.name = m_name;
		login.password = m_password;
		login.pending = true;
		if(!StoreLogin(login))
		{
			Fail("the file for the saved login cannot be written");
			return;
		}
		for(int i = 0; i < 6; i++) BoxWrite(mem, window + ACCOUNT_FIELD[i], values[i], secret[i]);
		m_formWritten = true;
		m_settle = 3;
		return;
	}
	if(m_presses >= 6)
	{
		Fail("the account screen does not answer");
		return;
	}
	m_submitted = true;
	Press(m_setup.cross, 10, 30);
}

void COnline::ActList(const CMem& mem, const Screen& s)
{
	if(m_listSeen && m_goal == Goal::Host)
	{
		ActHost(mem, s);
		return;
	}
	if(m_listSeen && m_goal == Goal::Join)
	{
		ActJoin(mem, s);
		return;
	}
	if(s.a != 0 || s.b != 0 || s.c != 0 || m_sameFrames < 30)
	{
		Say("entering the lobby");
		return;
	}
	if(!m_listSeen)
	{
		m_listSeen = true;
		// here the pair has worked
		Login saved;
		if(FindLogin(saved) && saved.pending)
		{
			saved.pending = false;
			StoreLogin(saved);
			Log("online: the new login for this server is saved (a file only you can read, in the data directory)");
		}
		Log("online: logged in; the game list is up");
	}
	if(m_goal == Goal::Lobby) Finish("you are in the lobby (Game Selection and Chat)");
}

// A game of our own: triangle (Host / Search), cross (Host Game), the character screens
// (the player's), then the form: its name field is given the code and cross sends it.
void COnline::ActHost(const CMem& mem, const Screen& s)
{
	const uint32_t window = s.window;
	const bool box = s.b != 0, keyboard = (s.d & 1) != 0, listHasPad = (s.d & 2) != 0, form = (s.d & 4) != 0;
	if(s.a != 0)
	{
		Say(m_gameSent ? "opening your game" : "to the character screens");
		return;
	}
	if(keyboard)
	{
		Fail("the on-screen keyboard is open");
		return;
	}
	if(m_gamePressed && box && s.c == 2) m_gameSent = true; // the game's "creating" notice
	if(m_gameSent)
	{
		// the request is out; a box that stays is the game's refusal
		Say("opening your game");
		if(box && m_sameFrames > 600) Fail("the game shows a message instead of opening game " + m_code + " (the name may be in use: host again for another code)");
		return;
	}
	if(s.c == 0 && !box)
	{
		if(m_characterSeen)
		{
			// back from the character screens: the form for the new game comes up a few
			// frames after the list does
			Say("opening your game");
			if(m_sameFrames > 180) Fail("no game was opened (the character screens were left without a character?)");
			return;
		}
		Say("hosting a game");
		if(!listHasPad)
		{
			Fail("the pad is in a chat pane of the lobby, not in the list of games");
			return;
		}
		if(m_sameFrames >= 20) Press(m_setup.triangle, 10, 30);
		return;
	}
	if(s.c == 1 && box)
	{
		Say("hosting a game");
		if(m_sameFrames >= 10) Press(m_setup.cross, 10, 30); // "Host Game"
		return;
	}
	if(s.c == 2 && !box && form)
	{
		if(mem.U8(A_CHARACTER_CHOSEN) == 0)
		{
			Fail("no character was chosen for the game");
			return;
		}
		Say("naming your game " + m_code);
		uint32_t field = mem.Pointer(window + LIST_NAME_FIELD);
		if(m_sameFrames < 20) return;
		if(!BoxHolds(mem, field, m_code))
		{
			if(!BoxFits(mem, field, m_code, false) || m_code.size() < 4)
			{
				Fail("the form for a new game is not as expected (its name field does not take the code)");
				return;
			}
			BoxWrite(mem, field, m_code, false);
			m_settle = 3;
			return;
		}
		if(mem.U32(window + LIST_FOCUS) != field)
		{
			Fail("the pad is not on the name of the new game");
			return;
		}
		if(m_presses >= 6)
		{
			Fail("the form for a new game does not answer");
			return;
		}
		m_gamePressed = true;
		Press(m_setup.cross, 10, 40); // Submit, with the form's own difficulty, game type and mission
		return;
	}
	Say("hosting a game");
}

// Somebody's game: the list is looked through for the code at every frame (the game asks
// the server for it again every twelve seconds or so), the cursor is walked to it and
// cross joins; the character screens are the player's; then the room.
void COnline::ActJoin(const CMem& mem, const Screen& s)
{
	const uint32_t window = s.window;
	const bool box = s.b != 0, keyboard = (s.d & 1) != 0, listHasPad = (s.d & 2) != 0;
	const uint32_t cursor = (s.d >> 8) & 0xFF;
	int64_t clock = NowMs();
	if(m_lookingSince == 0) m_lookingSince = clock;
	if(s.a != 0)
	{
		m_joinSent = true; // on its way to the character screens
		Say("joining game " + m_code);
		return;
	}
	if(box)
	{
		Fail(m_joinSent ? "the game shows a message instead of joining game " + m_code : "the game shows a message in the lobby");
		return;
	}
	if(m_characterSeen)
	{
		// back from the character screens: the room comes up a few frames later
		Say("joining game " + m_code);
		if(m_sameFrames > 180) Fail("game " + m_code + " was not joined (the character screens were left without a character?)");
		return;
	}
	if(keyboard || s.c != 0 || !listHasPad)
	{
		Fail("the lobby is not at its list of games");
		return;
	}
	uint32_t client = mem.Pointer(window + LIST_CLIENT);
	uint32_t count = client ? mem.U16(client + CLIENT_GAMES) : 0, list = client ? mem.Pointer(client + CLIENT_GAME_LIST) : 0;
	int found = -1;
	for(uint32_t i = 0; list && i < count && i < 64; i++)
	{
		std::string name = mem.Wide(list + i * GAME_SIZE + GAME_NAME, 32);
		for(auto& c : name) c = static_cast<char>(toupper(static_cast<unsigned char>(c)));
		if(name == m_code) found = static_cast<int>(i);
	}
	// the lobby client's flags say when the request is out (0x10) and when we are in (0x20)
	if(m_joinPressed && client && (mem.U32(client + 0x64) & 0x30) != 0) m_joinSent = true;
	if(m_joinSent)
	{
		// asked; the game says "Attempting" and goes to the character screens by itself
		Say("joining game " + m_code);
		if(clock - m_lookingSince > 30000) Fail("game " + m_code + " did not let us in within 30 seconds");
		return;
	}
	if(found < 0)
	{
		Say("waiting for game " + m_code + " to appear in the lobby's list");
		if(clock - m_lookingSince > GAME_LIMIT) Fail("no game with the code " + m_code + " appeared in the lobby's list within two minutes. Check the code with your friend (and that you are on the same server), then Online > Join a game again");
		return;
	}
	Say("joining game " + m_code);
	if(m_sameFrames < 6) return;
	if(static_cast<uint32_t>(found) != cursor)
	{
		Press((static_cast<uint32_t>(found) > cursor) ? m_setup.down : m_setup.up, 8, 16);
		return;
	}
	if(m_presses >= 8)
	{
		Fail("the list of games does not answer");
		return;
	}
	m_joinPressed = true;
	m_lookingSince = clock;
	Press(m_setup.cross, 10, 40);
}
