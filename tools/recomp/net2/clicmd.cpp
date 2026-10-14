// clicmd.cpp - session.h as lines of text: one command in, what it printed out.  Shared by
// net2cli (a terminal, a test) and by launch.cpp (the stand-alone program's "app net2 ..."
// script and control commands), so that both speak the same words.
//
// Commands:  me | friends | requests | invites | recent | blocked | room | session
//            name NAME | character NAME;CLASS;LEVEL | game [LEVEL] | cards [CARD_DIR]
//            add CODE | add-id WHO | accept WHO | decline WHO | remove WHO | block WHO | unblock WHO
//            invite WHO | take WHO | dismiss WHO
//            host [friends] [LEVEL] | join CODE | join-friend WHO | chat TEXT | ready [0|1]
//            options LEVEL DIFFICULTY [friends] | kick SLOT | start | leave
//            running [LEVEL] | over | delete | debug WHAT | set KEY VALUE | echo TEXT | wait SECONDS | quit
//            (debug: link | udp | send SLOT TEXT | recv)
// WHO is a player id, or the beginning of a name in any of the lists.
// Every event is one line: "EVENT <type> code=<n> who=<name> room=<code> text=<...>".
#include "clicmd.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <strings.h>

static const char* EVENT_NAMES[] = {"NONE", "LINK", "ME", "FRIENDS", "REQUESTS", "INVITE", "RECENT", "ROOM",
                                    "CHAT", "START", "GAME_OVER", "NOTICE", "ERROR", "DELETED"};
static const char* PRESENCE[] = {"offline", "online", "in a room", "in a game"};
static const char* ROOM_STATES[] = {"none", "joining", "open", "starting", "in game"};
static const char* ROUTES[] = {"-", "trying", "direct", "relay", "self"};

static std::string who_id(net2* n, const std::string& who) {
    if (who.size() == 32) return who;
    std::vector<net2_friend> list(64);
    for (int which = 0; which < 3; which++) {
        int count = which == 0 ? net2_friends(n, list.data(), 64) : which == 1 ? net2_recent(n, list.data(), 64) : net2_blocked(n, list.data(), 64);
        for (int i = 0; i < count; i++)
            if (!strncasecmp(list[i].name, who.c_str(), who.size())) return list[i].id;
    }
    net2_request requests[32];
    int count = net2_requests(n, requests, 32);
    for (int i = 0; i < count; i++)
        if (!strncasecmp(requests[i].name, who.c_str(), who.size())) return requests[i].id;
    net2_invite_t invites[16];
    count = net2_invites(n, invites, 16);
    for (int i = 0; i < count; i++)
        if (!strncasecmp(invites[i].from_name, who.c_str(), who.size())) return invites[i].from_id;
    net2_room_t room;
    net2_room(n, &room);
    for (int i = 0; i < room.count; i++)
        if (!strncasecmp(room.members[i].name, who.c_str(), who.size())) return room.members[i].id;
    return who;
}

static void show_character(const net2_character& c) {
    if (c.name[0]) printf(" [%s, %s %d]", c.name, c.cls, c.level);
}

static void show_list(const char* title, net2_friend* list, int count) {
    printf("%s: %d\n", title, count);
    for (int i = 0; i < count; i++) {
        const net2_friend& f = list[i];
        printf("  %-14s %s %s %s", f.name, f.friend_code, f.id, PRESENCE[f.presence & 3]);
        if (f.presence == NET2_IN_ROOM) printf(" %s%s players=%d", f.room, f.joinable ? " joinable" : " (closed)", f.room_players);
        if (f.presence == NET2_IN_GAME) printf(" level=%s players=%d", f.level, f.room_players);
        if (f.presence == NET2_OFFLINE && f.last_seen) printf(" last-seen=%lld", (long long)f.last_seen);
        show_character(f.character);
        if (f.invited_me) printf(" INVITED-ME");
        if (f.is_friend) printf(" friend");
        if (f.request_sent) printf(" asked");
        printf("\n");
    }
}

static void show_room(net2* n) {
    net2_room_t room;
    net2_room(n, &room);
    printf("room: state=%s code=%s count=%d my_slot=%d host_slot=%d all_ready=%d mismatch=%d level=%s difficulty=%d open_to=%d\n",
           ROOM_STATES[room.state], room.code, room.count, room.my_slot, room.host_slot, room.all_ready, room.mismatch,
           room.options.level, room.options.difficulty, room.options.open_to);
    if (room.warning[0]) printf("  WARNING %s\n", room.warning);
    for (int i = 0; i < room.count; i++) {
        const net2_member& m = room.members[i];
        printf("  slot %d %-14s%s%s%s fix=%08x:%u arith=%u:%u route=%s rtt=%d", m.slot, m.name, m.host ? " host" : "", m.me ? " me" : "",
               m.ready ? " ready" : "", m.fix_set, m.fix_words, m.arith_can, m.arith_does, ROUTES[m.route], m.rtt_ms);
        show_character(m.character);
        printf("\n");
    }
    for (int i = 0; i < room.chat_count; i++) printf("  chat %u <%s> %s\n", room.chat[i].number, room.chat[i].from, room.chat[i].text);
}

void net2_cli_command(net2* n, const std::string& line, bool& quit, double& wait) {
    size_t space = line.find(' ');
    std::string verb = line.substr(0, space), rest = space == std::string::npos ? "" : line.substr(space + 1);
    int r = 0;
    if (verb == "me") {
        net2_me_t me;
        net2_me(n, &me);
        printf("me: link=%d mock=%d id=%s name=%s code=%s service=%s new=%d problem=%s", me.link, me.mock, me.id, me.name, me.friend_code,
               me.service, me.new_identity, me.problem);
        show_character(me.character);
        printf("\n");
    } else if (verb == "friends" || verb == "recent" || verb == "blocked") {
        std::vector<net2_friend> list(128);
        int count = verb == "friends" ? net2_friends(n, list.data(), 128) : verb == "recent" ? net2_recent(n, list.data(), 128) : net2_blocked(n, list.data(), 128);
        show_list(verb.c_str(), list.data(), count);
    } else if (verb == "requests") {
        net2_request list[64];
        int count = net2_requests(n, list, 64);
        printf("requests: %d\n", count);
        for (int i = 0; i < count; i++) printf("  %s %-14s %s %s\n", list[i].incoming ? "from" : "to  ", list[i].name, list[i].friend_code, list[i].id);
    } else if (verb == "invites") {
        net2_invite_t list[16];
        int count = net2_invites(n, list, 16);
        printf("invites: %d\n", count);
        for (int i = 0; i < count; i++) {
            printf("  from %-14s room=%s players=%d", list[i].from_name, list[i].room, list[i].room_players);
            show_character(list[i].character);
            printf("\n");
        }
    } else if (verb == "room") {
        show_room(n);
    } else if (verb == "session") {
        net2_session_t g;
        net2_session(n, &g);
        printf("session: valid=%d session=%08x count=%d my_slot=%d host_slot=%d level=%s difficulty=%d seed=%u\n", g.valid, g.session, g.count,
               g.my_slot, g.host_slot, g.options.level, g.options.difficulty, g.seed);
        for (int i = 0; i < g.count; i++) {
            printf("  player %d %s %s", i, g.players[i].name, g.players[i].id);
            show_character(g.players[i].character);
            printf("\n");
        }
    } else if (verb == "cards") {
        net2_character list[16];
        int count = net2_local_characters(n, rest.empty() ? nullptr : rest.c_str(), list, 16);
        printf("cards: %d\n", count);
        for (int i = 0; i < count; i++) printf("  %s, %s %d\n", list[i].name, list[i].cls, list[i].level);
    } else if (verb == "name") r = net2_set_name(n, rest.c_str());
    else if (verb == "character") {
        net2_character c{};
        size_t a = rest.find(';'), b = rest.find(';', a == std::string::npos ? 0 : a + 1);
        if (rest.empty()) r = net2_set_character(n, nullptr);
        else {
            snprintf(c.name, sizeof c.name, "%s", rest.substr(0, a).c_str());
            if (a != std::string::npos) snprintf(c.cls, sizeof c.cls, "%s", rest.substr(a + 1, b == std::string::npos ? b : b - a - 1).c_str());
            if (b != std::string::npos) c.level = atoi(rest.c_str() + b + 1);
            r = net2_set_character(n, &c);
        }
    } else if (verb == "game") r = net2_set_game(n, rest.c_str());
    else if (verb == "add") r = net2_friend_add(n, rest.c_str());
    else if (verb == "add-id") r = net2_friend_add_id(n, who_id(n, rest).c_str());
    else if (verb == "accept") r = net2_friend_accept(n, who_id(n, rest).c_str());
    else if (verb == "decline") r = net2_friend_decline(n, who_id(n, rest).c_str());
    else if (verb == "remove") r = net2_friend_remove(n, who_id(n, rest).c_str());
    else if (verb == "block") r = net2_block(n, who_id(n, rest).c_str());
    else if (verb == "unblock") r = net2_unblock(n, who_id(n, rest).c_str());
    else if (verb == "invite") r = net2_invite(n, who_id(n, rest).c_str());
    else if (verb == "take") r = net2_invite_accept(n, who_id(n, rest).c_str());
    else if (verb == "dismiss") r = net2_invite_dismiss(n, who_id(n, rest).c_str());
    else if (verb == "host" || verb == "options") {
        net2_options o{};
        char level[64] = "", word[64] = "";
        int difficulty = 0;
        if (verb == "host") {
            if (sscanf(rest.c_str(), "%63s %63s", word, level) >= 1 && strcmp(word, "friends")) { snprintf(level, sizeof level, "%s", word); word[0] = 0; }
        } else {
            sscanf(rest.c_str(), "%63s %d %63s", level, &difficulty, word);
        }
        if (!strcmp(level, "-")) level[0] = 0;
        snprintf(o.level, sizeof o.level, "%s", level);
        o.difficulty = difficulty;
        o.open_to = !strcmp(word, "friends") ? NET2_OPEN_FRIENDS : NET2_OPEN_CODE;
        r = verb == "host" ? net2_host(n, &o) : net2_set_options(n, &o);
    } else if (verb == "join") r = net2_join(n, rest.c_str());
    else if (verb == "join-friend") r = net2_join_friend(n, who_id(n, rest).c_str());
    else if (verb == "chat") r = net2_chat(n, rest.c_str());
    else if (verb == "ready") r = net2_ready(n, rest.empty() ? 1 : atoi(rest.c_str()));
    else if (verb == "kick") r = net2_kick(n, atoi(rest.c_str()));
    else if (verb == "start") r = net2_start(n);
    else if (verb == "leave") r = net2_leave(n);
    else if (verb == "running") r = net2_game_state(n, rest.empty() ? "hub" : rest.c_str());
    else if (verb == "over") r = net2_game_state(n, nullptr);
    else if (verb == "delete") r = net2_delete_everything(n);
    else if (verb == "debug") {
        char text[2048];
        r = net2_debug(n, rest.c_str(), text, sizeof text);
        printf("debug: %s\n", text);
    } else if (verb == "set") {
        size_t s2 = rest.find(' ');
        r = net2_set(n, rest.substr(0, s2).c_str(), s2 == std::string::npos ? "" : rest.substr(s2 + 1).c_str());
    } else if (verb == "echo") printf("ECHO %s\n", rest.c_str());
    else if (verb == "wait") wait = atof(rest.c_str());
    else if (verb == "quit") quit = true;
    else if (!verb.empty() && verb[0] != '#') printf("? %s\n", verb.c_str());
    if (r) printf("RESULT %s: %d (%s)\n", verb.c_str(), r, net2_error_text(r));
    fflush(stdout);
}

void net2_cli_event(const net2_event& e) {
    printf("EVENT %s code=%d who=%s room=%s text=%s\n", e.type >= 0 && e.type <= NET2_EV_DELETED ? EVENT_NAMES[e.type] : "?", e.code, e.who, e.room, e.text);
    fflush(stdout);
}
