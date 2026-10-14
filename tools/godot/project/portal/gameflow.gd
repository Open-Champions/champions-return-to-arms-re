extends Node
# gameflow.gd - the game's side of a room (tools/recomp/net2/game.h through RtaNet2), driven
# from the portal as docs/issues/native-rendezvous.md 5.1 says and tools/godot/project/dev/
# net2_flow.gd does in a test:
#
#   after open        game_attach() once: the game library then launches the room's game by
#                     itself, publishes the chosen character and tells the room "running" / "over"
#   in a room         the game scene is started behind the portal (it boots to its title screen by
#                     itself: --opt net2-boot=1) - the room shows "your game is getting ready"
#   "Choose your character" (the room's button)
#                     game_choose(is_host): the game's OWN character screens get the screen and the
#                     controller (make a character, or Import one saved on this computer); the
#                     portal does not press them - it hands over and comes back
#   CHOSEN            the portal is back in front; a guest is marked ready; the host's Start
#                     waits for everybody
#   LAUNCHING ...     the game has the screen: its own "Network Game Launch" screen, then the level
#   TITLE again       the game is over on this machine: the portal is back, the room open again;
#                     "Play again" = choose again, ready, start
#
# Without the game's side (a library without net2, the mock, a build with RTA_GODOT_NET2_SERVICE
# off) `active` is false and the portal behaves as before (the stand-in in tests).

const Session := preload("res://portal/session.gd")

const BOOTING := 0
const TITLE := 1
const CHOOSING := 2
const CHOSEN := 3
const LAUNCHING := 4
const LOADING := 5
const RUNNING := 6
const BUSY := 7
const NAMES := ["booting", "title", "choosing", "chosen", "launching", "loading", "running", "busy"]

signal phase_changed(phase: int)

var portal: Node
var active := false
var attached := false
var status := {}
var phase := -1
var last_phase := -1
var games := 0                      # games that ran on this machine since the portal started
var was_running := false
var choosing := false               # we asked for the character screens and wait for them to end
var want_choose := false            # asked for before the title screen was up: done when it is
var chosen_round := -1              # the round a character was chosen for (a round = one game)
var readied_round := -1


func attach() -> void:
	var n: Object = portal.session.n
	active = n != null and bool(n.call("has_game")) and not bool(portal.session.is_mock)
	if active and not attached:
		attached = bool(n.call("game_attach"))
		print("portal: the game's side of the session: attached %s (from the game library %s)" % [str(attached), str(n.call("from_library"))])


func phase_name() -> String:
	return NAMES[phase] if phase >= 0 and phase < NAMES.size() else "none"


func unlocked() -> int:
	# the difficulties the game's own menu would offer a host on this machine (1 on a new memory card)
	return clampi(int(status.get("difficulty_unlocked", 1)), 1, 4) if active else 4


func has_character() -> bool:
	return active and phase == CHOSEN and chosen_round == games


func game_ready() -> bool:
	return active and phase >= TITLE and phase != BUSY


func choose() -> void:
	if not active:
		return
	if phase != TITLE:
		want_choose = true          # the game is still on its way to the title screen
		return
	want_choose = false
	var room: Dictionary = portal.session.room()
	var as_host := int(room.get("my_slot", -1)) == int(room.get("host_slot", -2))
	var r := int(portal.session.n.call("game_choose", as_host))
	print("portal: game_choose(%s) %d" % [str(as_host), r])
	if r == 0:
		choosing = true
		portal.call("set_shown", false)     # the game's own character screens have the screen and the controller


func _process(_delta: float) -> void:
	if not active or portal.session.n == null:
		return
	status = portal.session.n.call("game_status")
	phase = int(status.get("phase", -1))
	var room: Dictionary = portal.session.room()
	var in_room := int(room.get("state", 0)) >= Session.ROOM_OPEN
	if in_room and portal.handover.game == null:
		portal.handover.call("prepare")     # boots behind the portal to its title screen
	if phase != last_phase:
		_moved(last_phase, phase, room)
		last_phase = phase
		phase_changed.emit(phase)
	if want_choose and phase == TITLE and in_room:
		choose()


func _moved(from: int, to: int, room: Dictionary) -> void:
	print("portal: the game %s -> %s (%s)" % [NAMES[from] if from >= 0 and from < NAMES.size() else "-", NAMES[to] if to >= 0 and to < NAMES.size() else str(to), String(status.get("text", ""))])
	if to == CHOSEN and choosing:
		choosing = false
		chosen_round = games
		var c: Dictionary = status.get("character", {})
		if String(c.get("name", "")) != "":
			portal.call("choose_character", c)
		portal.call("set_shown", true, true)
		var i_host := int(room.get("my_slot", -1)) == int(room.get("host_slot", -2))
		if not i_host and readied_round != games:
			readied_round = games
			portal.session.ready(true)      # the choice is the mark: nothing more to press
		portal.call("toast", "Playing " + UI_line(c), "good")
	elif to == TITLE and choosing:
		choosing = false
		portal.call("set_shown", true, true)
		if bool(status.get("failed", false)):
			portal.call("toast", "No character was chosen - try again when you like", "info", String(status.get("text", "")))
	elif to == LAUNCHING or to == LOADING or to == RUNNING:
		if to == RUNNING:
			was_running = true
		if portal.get("shown"):
			portal.call("set_shown", false)
	elif (to == TITLE or to == BUSY) and was_running:
		# the game is over on this machine: back in the room
		was_running = false
		games += 1
		portal.call("set_shown", true, true)
		if portal.session.in_room() and portal.call("current_name") != "room":
			portal.call("go", "room", {"played": true})


static func UI_line(c: Dictionary) -> String:
	var name := String(c.get("name", ""))
	var level := int(c.get("level", 0))
	return name + (" (level %d)" % level if level > 0 else "")
