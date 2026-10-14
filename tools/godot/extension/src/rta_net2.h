// rta_net2.h - RtaNet2: the online session (tools/recomp/net2/session.h) for Godot scripts.
//
// A thin wrapper: every call of session.h is a method of the same name without the "net2_"
// prefix, every record comes out as a Dictionary whose keys are the struct's field names,
// every list as an Array of such Dictionaries.  Nothing is added and nothing interpreted;
// the portal (tools/godot/project/portal/session.gd) is the only user.
//
//   var n := RtaNet2.new()
//   n.open({"mock": true, "name": "Sam", "data_dir": "..."})
//   every frame:  for e in n.poll(): ...      # net2_poll, then every net2_next_event
//                 n.me()  n.friends()  n.requests()  n.invites()  n.recent()  n.blocked()  n.room()  n.session()
//
// Built with tools/recomp/net2/session.cpp, session_mock.cpp and, for the real service,
// session_net.cpp, carrier.cpp, cardchars.cpp compiled in.  With NET2_NO_SERVICE (the build
// switch for a mock-only extension) there is no socket code in the extension at all:
// has_service() is false and anything but the mock says "offline".
// When the game library itself carries net2 (launch.cpp: docs/issues/native-rendezvous.md 5.1),
// there must be ONE copy in the process: this class should then call the library's net2_*
// through the loaded library instead of compiling its own (not done yet: no library has it).
//
// Registered by one line in register.cpp:  GDREGISTER_CLASS(RtaNet2);
#pragma once
#include "session.h"

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/string.hpp>

namespace godot {

class RtaNet2 : public RefCounted {
    GDCLASS(RtaNet2, RefCounted)
  public:
    RtaNet2();
    ~RtaNet2();

    static bool has_service();
    static int api_version() { return NET2_API_VERSION; }

    // config: data_dir, service, mock (bool), name, fix_set, fix_words, arith_can, arith_does, build, local_only (bool)
    bool open(const Dictionary& config);
    void close();
    bool is_open() const { return handle != nullptr; }
    Array poll();                           // the events since the last call: type, code, who, who_id, room, text

    Dictionary me() const;
    int set_name(const String& name);
    int set_character(const Dictionary& character);     // name, cls, level; empty: none
    int set_game(const String& level);                  // "": not in a game
    Array local_characters(const String& card_dir) const;
    int delete_everything();

    Array friends() const;
    Array recent() const;
    Array blocked() const;
    Array requests() const;
    int friend_add(const String& friend_code);
    int friend_add_id(const String& id);
    int friend_accept(const String& id);
    int friend_decline(const String& id);
    int friend_remove(const String& id);
    int block(const String& id);
    int unblock(const String& id);

    Array invites() const;
    int invite(const String& friend_id);
    int invite_accept(const String& from_id);
    int invite_dismiss(const String& from_id);

    Dictionary room() const;
    int host(const Dictionary& options);                // level, difficulty, mode, open_to, mission, kill_limit
    int join(const String& code);
    int join_friend(const String& friend_id);
    int chat(const String& text);
    int ready(bool ready);
    int set_options(const Dictionary& options);
    int kick(int slot);
    int start();
    int leave();

    Dictionary session() const;
    int game_state(const String& level, bool running);  // running false: over, or the launch failed

    String debug(const String& what) const;
    int set_value(const String& key, const String& value);
    String error_text(int code) const;

  protected:
    static void _bind_methods();

  private:
    net2* handle = nullptr;
};

}  // namespace godot
