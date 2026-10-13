extends Node
# session.gd - the ONE script between the portal's screens and the online session.
#
# Behind it is tools/recomp/net2/session.h through the extension's RtaNet2
# (tools/godot/extension/src/rta_net2.*): the same calls without the "net2_" prefix, the
# same records as Dictionaries with the structs' field names.  A screen never talks to
# RtaNet2 itself; if the client interface is ever exchanged, this file is what changes.
#
#   open(config)        config as RtaNet2.open: mock, service, data_dir, name, fix_set ...
#   every frame         poll; each event goes out as `event(e)` and, by kind, as
#                       `changed(what)`: link, me, friends, requests, invites, recent, room, chat
#   snapshots           me() friends() recent() blocked() requests() invites() room() game()
#   calls               set_name ... host join join_friend chat ready set_options kick start leave
#
# Without the extension, or without RtaNet2 in it, everything answers "offline" and the
# rest of the portal (play alone, settings) works as before.

signal event(e: Dictionary)
signal changed(what: String)

const EV_LINK := 1
const EV_ME := 2
const EV_FRIENDS := 3
const EV_REQUESTS := 4
const EV_INVITE := 5
const EV_RECENT := 6
const EV_ROOM := 7
const EV_CHAT := 8
const EV_START := 9
const EV_GAME_OVER := 10
const EV_NOTICE := 11
const EV_ERROR := 12
const EV_DELETED := 13

const LINK_OFF := 0
const LINK_CONNECTING := 1
const LINK_ONLINE := 2

const OFFLINE := 0
const ONLINE := 1
const IN_ROOM := 2
const IN_GAME := 3

const ROOM_NONE := 0
const ROOM_JOINING := 1
const ROOM_OPEN := 2
const ROOM_STARTING := 3
const ROOM_IN_GAME := 4

const ROUTE_NONE := 0
const ROUTE_TRYING := 1
const ROUTE_DIRECT := 2
const ROUTE_RELAY := 3
const ROUTE_SELF := 4

const OPEN_CODE := 0
const OPEN_FRIENDS := 1

const ERR_NOT_FOUND := -5
const ERR_FULL := -6
const ERR_REFUSED := -7

const WHAT := {EV_LINK: "link", EV_ME: "me", EV_FRIENDS: "friends", EV_REQUESTS: "requests", EV_INVITE: "invites", EV_RECENT: "recent",
	EV_ROOM: "room", EV_CHAT: "chat", EV_START: "room", EV_GAME_OVER: "room", EV_DELETED: "me"}

var n: Object                       # RtaNet2, or null
var is_mock := false
var fallback_name := ""             # shown as my name while there is no session object
var why_off := "Playing with friends is not part of this build yet."
# pictures of lists longer than the mock's (dev/shots.gd): when set, friends() answers this instead
var friends_for_pictures: Variant = null


func open(config: Dictionary) -> bool:
	close()
	if not ClassDB.class_exists("RtaNet2"):
		return false
	n = ClassDB.instantiate("RtaNet2")
	is_mock = bool(config.get("mock", false))
	if not n.call("open", config):
		n = null
		return false
	return true


func close() -> void:
	if n != null:
		n.call("close")
	n = null


func available() -> bool:
	return n != null


func _process(_delta: float) -> void:
	if n == null:
		return
	for e in n.call("poll"):
		event.emit(e)
		var what: String = WHAT.get(int(e.type), "")
		if what != "":
			changed.emit(what)


func setting(key: String, value: String) -> int:
	return int(n.call("set_value", key, value)) if n != null else -2


# ---- snapshots -----------------------------------------------------------------------------
func me() -> Dictionary:
	if n == null:
		return {"link": LINK_OFF, "mock": false, "id": "", "name": fallback_name, "friend_code": "", "service": "", "problem": why_off,
			"character": {"name": "", "cls": "", "level": 0}, "new_identity": false}
	return n.call("me")


func online() -> bool:
	return n != null and int(me().get("link", 0)) == LINK_ONLINE


func friends() -> Array:
	if friends_for_pictures != null:
		return friends_for_pictures
	return n.call("friends") if n != null else []


func recent() -> Array:
	return n.call("recent") if n != null else []


func blocked() -> Array:
	return n.call("blocked") if n != null else []


func requests() -> Array:
	return n.call("requests") if n != null else []


func invites() -> Array:
	return n.call("invites") if n != null else []


func room() -> Dictionary:
	if n == null:
		return {"state": ROOM_NONE, "code": "", "count": 0, "members": [], "options": {}, "chat": [], "mismatch": false, "warning": "", "all_ready": false,
			"my_slot": 0, "host_slot": 0}
	return n.call("room")


func in_room() -> bool:
	return n != null and int(room().get("state", 0)) >= ROOM_JOINING


func game() -> Dictionary:
	return n.call("session") if n != null else {"valid": false}


func local_characters(card_dir: String) -> Array:
	return n.call("local_characters", card_dir) if n != null else []


# ---- calls ---------------------------------------------------------------------------------
func _do(method: String, a: Variant = null, b: Variant = null) -> int:
	if n == null:
		return -1
	if a == null:
		return int(n.call(method))
	if b == null:
		return int(n.call(method, a))
	return int(n.call(method, a, b))


func set_name_shown(value: String) -> int: return _do("set_name", value)
func set_character(character: Dictionary) -> int: return _do("set_character", character)
func set_game(level: String) -> int: return _do("set_game", level)
func delete_everything() -> int: return _do("delete_everything")
func friend_add(code: String) -> int: return _do("friend_add", code)
func friend_add_id(id: String) -> int: return _do("friend_add_id", id)
func friend_accept(id: String) -> int: return _do("friend_accept", id)
func friend_decline(id: String) -> int: return _do("friend_decline", id)
func friend_remove(id: String) -> int: return _do("friend_remove", id)
func block(id: String) -> int: return _do("block", id)
func unblock(id: String) -> int: return _do("unblock", id)
func invite(id: String) -> int: return _do("invite", id)
func invite_accept(id: String) -> int: return _do("invite_accept", id)
func invite_dismiss(id: String) -> int: return _do("invite_dismiss", id)
func host(options: Dictionary) -> int: return _do("host", options)
func join(code: String) -> int: return _do("join", code)
func join_friend(id: String) -> int: return _do("join_friend", id)
func chat(line: String) -> int: return _do("chat", line)
func ready(is_ready: bool) -> int: return _do("ready", is_ready)
func set_options(options: Dictionary) -> int: return _do("set_options", options)
func kick(slot: int) -> int: return _do("kick", slot)
func start() -> int: return _do("start")
func leave() -> int: return _do("leave")
func game_state(level: String, running: bool) -> int: return _do("game_state", level, running)


func error_text(code: int) -> String:
	return String(n.call("error_text", code)) if n != null else why_off
