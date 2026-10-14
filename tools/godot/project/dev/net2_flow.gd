extends Node
# dev/net2_flow.gd - a room of our own through RtaNet2, the way the portal is to drive it (docs/issues/native-rendezvous.md
# 5.1), as a test of the game scene: main.gd adds this node for  --net2-flow ROLE:DIR  (ROLE host or join; DIR shared by
# the copies: the host writes the room's code to DIR/code.txt, a joiner reads it from there).
#
#   RtaNet2.open (the GAME LIBRARY's net2: one session object in the process), game_attach once;
#   host: host({}) - join: join(code);
#   the game at its title screen and in the room: game_choose(is_host) - the game's own character screens (the test's
#   script walks them as a person would); CHOSEN: a joiner says ready; the host starts once every other member is ready
#   and back from any earlier game;
#   RUNNING, then TITLE again (the game is over on this machine): "Play again" - choose, ready, start - until ROUNDS games
#   have run; then the machine is told to end (the script's own quit does that too).
# Every step is printed as "net2flow: ..." with the game's tick; the result line is "net2flow: done ...".
#
# The service: $RTA_NET2_SERVICE (host:port), as the session client finds it by itself.

const LINK_ONLINE := 2
const ROOM_OPEN := 2
const PHASE_TITLE := 1
const PHASE_CHOSEN := 3
const PHASE_RUNNING := 6
const PHASE_NAMES := ["booting", "title", "choosing", "chosen", "launching", "loading", "running", "busy"]

var main: Node
var role := "host"
var dir := ""
var rounds := 2
var n: Object
var asked_room := false
var chose_round := -1
var readied_round := -1
var started_round := -1
var start_clock := 0
var round_index := 0                    # games that have run on this machine
var was_running := false
var max_tick := 0
var last_phase := -1
var last_state := -1
var said_code := false
var done := false
var log_clock := 0


func setup(spec: String) -> void:
	var parts := spec.split(":", true, 1)
	role = parts[0]
	dir = parts[1] if parts.size() > 1 else ""
	if OS.has_environment("RTA_NET2_ROUNDS"):
		rounds = int(OS.get_environment("RTA_NET2_ROUNDS"))


func _say(text: String) -> void:
	print("net2flow: [blank %d] %s %s" % [int(main.blanks), role, text])


func _process(_delta: float) -> void:
	if done or main.machine == null or not bool(main.started):
		return
	if n == null:
		if not ClassDB.class_exists("RtaNet2"):
			_say("no RtaNet2 in this extension")
			done = true
			return
		n = ClassDB.instantiate("RtaNet2")
		var data: String = String(main.opt.data).path_join("net2")
		DirAccess.make_dir_recursive_absolute(data)
		var config := {"data_dir": data, "name": role.capitalize() + " of the Godot flow", "build": "godot net2_flow", "local_only": true,
			"service": OS.get_environment("RTA_NET2_SERVICE")}
		if not n.call("open", config):
			_say("open failed: " + str(n.call("get_error")))
			done = true
			return
		_say("opened: from the game library %s, the game's side %s" % [str(n.call("from_library")), str(n.call("has_game"))])
		_say("game_attach " + str(n.call("game_attach")))
	n.call("poll")
	var me: Dictionary = n.call("me")
	var room: Dictionary = n.call("room")
	var game: Dictionary = n.call("game_status")
	var phase := int(game.get("phase", -1))
	var state := int(room.get("state", 0))
	if phase != last_phase or state != last_state:
		_say("game %s (%s), room state %d, %d members, link %d" % [PHASE_NAMES[phase] if phase >= 0 and phase < PHASE_NAMES.size() else str(phase),
			String(game.get("text", "")), state, int(room.get("count", 0)), int(me.get("link", 0))])
		last_phase = phase
		last_state = state
	if int(me.get("link", 0)) != LINK_ONLINE:
		return
	# into a room
	if state == 0 and not asked_room:
		if role == "host":
			asked_room = true
			_say("host " + str(n.call("host", {"level": "", "difficulty": 0, "mode": 0, "open_to": 0})))
		else:
			var f := FileAccess.open(dir.path_join("code.txt"), FileAccess.READ)
			if f == null:
				return
			var code := f.get_as_text().strip_edges()
			if code == "":
				return
			asked_room = true
			_say("join %s: %s" % [code, str(n.call("join", code))])
		return
	if role == "host" and String(room.get("code", "")) != "" and not said_code:
		said_code = true
		var f := FileAccess.open(dir.path_join("code.txt"), FileAccess.WRITE)
		f.store_string(String(room.code) + "\n")
		f.close()
		_say("ROOM CODE " + String(room.code))
	# a game ran and is over on this machine
	if phase == PHASE_RUNNING:
		was_running = true
		max_tick = max(max_tick, int(game.get("tick", 0)))
		if int(main.blanks) - log_clock >= 300:
			log_clock = int(main.blanks)
			_say("running: level %s, tick %d, %d players" % [String(game.get("level", "")), int(game.get("tick", 0)), int(game.get("players", 0))])
	elif was_running and phase == PHASE_TITLE:
		was_running = false
		round_index += 1
		_say("game %d over on this machine (tick %d reached)" % [round_index, max_tick])
		if round_index >= rounds:
			done = true
			_say("done: %d games, room %s" % [round_index, String(room.get("code", ""))])
			return
	if state != ROOM_OPEN:
		return
	if phase == PHASE_TITLE and chose_round != round_index and not bool(game.get("failed", false)):
		chose_round = round_index
		_say("game_choose " + str(n.call("game_choose", role == "host")))
	elif phase == PHASE_TITLE and bool(game.get("failed", false)) and chose_round == round_index:
		_say("the character screens were left without a character: again")
		chose_round = -1
	if phase != PHASE_CHOSEN:
		return
	var members: Array = room.get("members", [])
	if role != "host":
		if readied_round != round_index:
			readied_round = round_index
			_say("ready " + str(n.call("ready", true)))
		return
	var all_back := true
	for m in members:
		all_back = all_back and int(m.get("phase", 0)) == 0
	if members.size() >= 2 and bool(room.get("all_ready", false)) and all_back and Time.get_ticks_msec() - start_clock > 3000:
		start_clock = Time.get_ticks_msec()
		started_round = round_index
		_say("start " + str(n.call("start")))
