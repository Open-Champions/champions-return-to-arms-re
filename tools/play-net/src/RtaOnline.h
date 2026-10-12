// "One-step online": the application presses its own way from power-on to the lobby.
//
// The game wants a person to go through Start New Game, Internet Game, the network
// setting, the server's terms, and a log-in typed on its on-screen keyboard (the first
// time: a whole account form). COnline does that by itself. It is called at every
// vertical blank on the machine's thread, looks at the game's own state in memory to
// know which screen is up (never at the clock alone), and presses one button at a time;
// the two forms are filled by writing the game's text fields, each read back before the
// form is sent. Whatever it does not know - an error box, another menu, no change for
// twenty seconds - ends it: it says so and the player has the controls where the game is.
//
// The account is the application's business, not the player's: a player name is asked for
// once (by the application, not here), the password is made here at random, and the pair
// is kept per server in <data directory>/online-login, a file only the user can read.
// Neither is ever written to the log, the status bar or the control socket.
//
// Nothing here depends on the emulator or on Qt.
#pragma once

#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

namespace Rta
{
	class COnline
	{
	public:
		// where to stop
		enum class Goal
		{
			Lobby, // the game list ("Game Selection and Chat")
			Host,  // a game of our own, named with a code, in its room
			Join,  // the game with the given code, in its room
		};

		struct Setup
		{
			std::string file;      // the saved logins
			std::string server;    // the key they are saved under: the server's address as given
			std::string serverText; // the server in words, for messages
			bool personPresent = true; // false: nobody can answer a dialog (a background test)
			std::function<void(const std::string&)> log;
			// A player name is needed (machine thread). 'why' is empty the first time and
			// says what was wrong with the last one otherwise. Answered with GiveName or
			// DeclineName, from any thread.
			std::function<void(const std::string& why)> askName;
			// button masks, by the emulator's numbering
			uint32_t cross = 0, circle = 0, triangle = 0, square = 0, up = 0, down = 0, left = 0, right = 0, l1 = 0, r1 = 0, start = 0;
		};

		void Configure(const Setup&);

		// ---- any thread
		// 'powerOn': armed before the game runs, so the card questions and the logos before
		// the title screen are its to press through. Otherwise the title screen (or a
		// lobby screen it knows) has to be up.
		void Start(Goal goal, const std::string& code, bool powerOn);
		void Stop(const std::string& why);
		void GiveName(const std::string& name);
		void DeclineName();
		// names for tests, used in order instead of asking
		void QueueNames(const std::vector<std::string>& names);
		bool Active() const;
		// one line for the status bar; empty when there is nothing to say
		std::string Note() const;
		// for the control socket: stage and outcome in words, never a name or a password
		std::string Report() const;
		// the code of the game being hosted or joined; empty: none
		std::string Code() const;

		// the saved login for this server
		bool HasLogin() const;
		std::string LoginName() const; // for the application's own dialogs only
		bool Forget();

		// empty: a name the game's forms and the server take; otherwise what is wrong with it
		static std::string CheckName(const std::string& name);
		static std::string CheckCode(const std::string& code);
		static std::string MakeCode();

		// ---- the machine's thread
		// a new program was loaded into the machine
		void OnExecutable(bool isGame);
		void Tick(uint8_t* ram, uint32_t ramSize, bool isGame);
		// while true the player's own buttons are not passed to the game
		bool Driving() const
		{
			return m_driving;
		}
		uint32_t Buttons() const
		{
			return m_buttons;
		}

	private:
		struct Login
		{
			std::string server, name, password;
			bool pending = false; // the account was asked for; no log-in with it has worked yet
		};
		struct Screen
		{
			enum Kind
			{
				NoGame,
				Boot,
				InGame,
				FeMain,
				FeType,
				FeOther,
				LobbyWait,
				Net,
				LoginForm,
				Account,
				List,
				CharMenu, // the character screens: the player's to do
				Room,     // a game's room
				LobbyOther,
			} kind = NoGame;
			uint32_t window = 0;
			uint32_t a = 0, b = 0, c = 0, d = 0;
			bool operator==(const Screen& o) const
			{
				return kind == o.kind && window == o.window && a == o.a && b == o.b && c == o.c && d == o.d;
			}
		};
		class CMem;

		Screen Observe(const CMem&, bool isGame) const;
		std::string Describe(const Screen&) const;
		void Act(const CMem&, const Screen&);
		void ActNet(const CMem&, const Screen&);
		void ActLogin(const CMem&, const Screen&);
		void ActAccount(const CMem&, const Screen&);
		void ActList(const CMem&, const Screen&);
		void ActHost(const CMem&, const Screen&);
		void ActJoin(const CMem&, const Screen&);
		void Press(uint32_t mask, unsigned int hold, unsigned int settle);
		void Say(const std::string& note);
		void Finish(const std::string& note, int64_t showFor = 20000);
		void Fail(const std::string& why);
		void Log(const std::string& line) const;
		bool NeedName(const std::string& why);

		// the game's text fields
		bool BoxFits(const CMem&, uint32_t box, const std::string& text, bool secret) const;
		void BoxWrite(const CMem&, uint32_t box, const std::string& text, bool secret) const;
		bool BoxHolds(const CMem&, uint32_t box, const std::string& text) const;

		// the saved logins
		std::vector<Login> ReadLogins() const;
		bool WriteLogins(const std::vector<Login>&) const;
		bool FindLogin(Login&) const;
		bool StoreLogin(const Login&) const;
		bool DropLogin() const;
		static std::string MakePassword();

		Setup m_setup;
		mutable std::mutex m_mutex; // for everything another thread may touch
		// asked for by another thread, taken up at the next vertical blank
		bool m_startWanted = false, m_stopWanted = false;
		Goal m_wantedGoal = Goal::Lobby;
		std::string m_wantedCode, m_stopWhy;
		bool m_wantedPowerOn = false;
		std::string m_givenName;
		bool m_nameGiven = false, m_nameDeclined = false;
		std::vector<std::string> m_queuedNames;
		std::string m_note, m_stage = "idle", m_outcome, m_code;
		int64_t m_noteUntil = 0; // a closing note is shown until then (milliseconds); 0: for ever

		// machine thread only
		bool m_active = false, m_driving = false;
		uint32_t m_buttons = 0;
		unsigned int m_hold = 0, m_settle = 0;
		Goal m_goal = Goal::Lobby;
		bool m_powerOn = false;
		bool m_frontEndSeen = false; // since the game was loaded
		Screen m_screen;
		bool m_haveScreen = false;
		unsigned int m_sameFrames = 0;
		int64_t m_lastChange = 0, m_started = 0, m_waitingSince = 0;
		int m_rank = 0;
		unsigned int m_presses = 0; // on this screen, with nothing changing
		// the log-in
		bool m_loginTried = false, m_loginWritten = false, m_loginRefused = false;
		bool m_nameAsked = false, m_askEarly = false;
		std::string m_name, m_password;
		bool m_formWritten = false, m_submitted = false, m_createFailed = false;
		unsigned int m_namesRefused = 0;
		bool m_listSeen = false;
		// a game of our own, or somebody's
		bool m_characterSeen = false, m_gamePressed = false, m_gameSent = false, m_joinPressed = false, m_joinSent = false;
		int64_t m_lookingSince = 0;
	};
}
