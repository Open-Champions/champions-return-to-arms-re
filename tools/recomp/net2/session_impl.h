// session_impl.h - what the bodies behind session.h share: the state a screen reads, the
// event queue, and the checks of what a player may type.  Not for a host program.
#pragma once
#include "session.h"

#include <chrono>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>
#include <vector>

namespace n2 { struct Carrier; }

namespace net2impl {

inline void put(char* out, size_t size, const std::string& text) {
    size_t n = text.size() < size - 1 ? text.size() : size - 1;
    // never cut a UTF-8 sequence in half
    while (n > 0 && n < text.size() && ((unsigned char)text[n] & 0xC0) == 0x80) n--;
    memcpy(out, text.data(), n);
    out[n] = 0;
}
template <size_t N> inline void put(char (&out)[N], const std::string& text) { put(out, N, text); }

inline int64_t unix_now() {
    return std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count();
}
inline int64_t steady_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// The alphabet of friend codes and room codes: no I, O, 0 or 1, so a code can be read out.
extern const char CODE_ALPHABET[33];
std::string code_normal(const char* text, size_t want);     // upper case, no dashes or blanks; "" when it is not a code of that length
std::string friend_code_shown(const std::string& normal);   // "K7QF2MXD" -> "K7QF-2MXD"
std::string name_problem(const char* name);                 // "" when a display name is fine
std::string clean_text(const char* text, size_t most);      // a chat line: control characters out, cut to `most` bytes
std::string clean_label(const char* text, size_t most);     // a name of a character, class or level: printable, cut
bool id_ok(const char* id);                                 // 32 hex digits

struct State {
    net2_me_t me{};
    std::vector<net2_friend> friends, recent, blocked;
    std::vector<net2_request> requests;
    std::vector<net2_invite_t> invites;
    net2_room_t room{};
    net2_session_t session{};
    std::deque<net2_event> events;

    void event(int type, int code = 0, const std::string& text = "", const std::string& who = "",
               const std::string& who_id = "", const std::string& room_code = "") {
        if (events.size() >= 256) events.pop_front();       // a host that never reads them
        net2_event e{};
        e.type = type;
        e.code = code;
        put(e.text, text);
        put(e.who, who);
        put(e.who_id, who_id);
        put(e.room, room_code);
        events.push_back(e);
    }
    int error(int code, const std::string& text) { event(NET2_EV_ERROR, code, text); return code; }
    void chat_line(const std::string& from, const std::string& text, uint32_t number = 0) {
        if (room.chat_count == NET2_CHAT_LINES) {
            memmove(&room.chat[0], &room.chat[1], sizeof(net2_chat_line) * (NET2_CHAT_LINES - 1));
            room.chat_count--;
        }
        net2_chat_line& line = room.chat[room.chat_count];
        line.number = number ? number : (room.chat_count ? room.chat[room.chat_count - 1].number + 1 : 1);
        put(line.from, from);
        put(line.text, text);
        room.chat_count++;
        event(NET2_EV_CHAT, 0, text, from);
    }
    void sort_friends();
    void room_checks();         // all_ready, mismatch and its warning, from the members
};

struct Backend {
    State s;
    virtual ~Backend() {}
    virtual void poll() = 0;
    virtual int set_name(const std::string& name) = 0;
    virtual int set_character(const net2_character* character) = 0;
    virtual int set_game(const std::string& level) = 0;
    virtual int delete_everything() = 0;
    virtual int friend_add(const std::string& code) = 0;
    virtual int friend_op(const char* op, const std::string& id) = 0;   // add-id accept decline remove block unblock
    virtual int invite(const std::string& id) = 0;
    virtual int invite_answer(const std::string& id, bool accept) = 0;
    virtual int host(const net2_options& options) = 0;
    virtual int join(const std::string& code) = 0;
    virtual int join_friend(const std::string& id) = 0;
    virtual int chat(const std::string& text) = 0;
    virtual int ready(bool ready) = 0;
    virtual int set_options(const net2_options& options) = 0;
    virtual int kick(int slot) = 0;
    virtual int start() = 0;
    virtual int leave() = 0;
    virtual int game_state(const std::string& level, bool running) = 0;
    virtual int debug(const std::string& what, std::string& out) { out = ""; (void)what; return NET2_ERR_ARGUMENT; }
    virtual int set(const std::string& key, const std::string& value) { (void)key; (void)value; return NET2_ERR_ARGUMENT; }
};

// One lock for everything of net2: the calls of session.h take it, and so does the game's
// side (launch.cpp), whose threads are not the caller's.
std::recursive_mutex& big_lock();

Backend* make_mock(const net2_config& config);
Backend* make_service(const net2_config& config);   // session_net.cpp
Backend* make_off(const net2_config& config);

// the UDP socket and routes of a body that talks to the service; nullptr for the others
n2::Carrier* carrier_of(Backend* body);

// The characters in the saved games of a card directory (cardchars.cpp), and the class
// words by the game's class number.
int card_characters(const char* card_dir, net2_character* out, int max);
extern const char* const CLASS_WORDS[7];

}  // namespace net2impl

struct net2 {
    net2impl::Backend* body = nullptr;
};
