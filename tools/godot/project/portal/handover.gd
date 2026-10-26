extends Node
# handover.gd - from the portal into the game and back.
#
# start(intent)   puts the game scene (res://main.tscn) under Portal/Game the first time,
#                 with what the portal knows written into its options before it starts (the
#                 disc image, the camera view, the picture's shape and sharpness); later
#                 starts wake the same scene up again - the game is one machine per run of
#                 the program (docs/issues/native-godot.md).  The portal fades out.
#                 intent: {kind: "alone" | "session" | "create", character, session}
#                 The game side asks for it:  get_tree().get_first_node_in_group("portal").handover.intent
# finish(why)     the portal comes back in front; the game scene stands still behind it,
#                 blurred and dimmed.  Called on the session's "game over", by the game
#                 scene when it has one to give (see docs/issues/native-portal.md), or by F9.
#
# While a game runs, the local player's character and the level are read once a second
# from the game's own state (RtaGameState, tools/recomp/app/gamestate.h) and handed to the
# profile ("the character you last played") and to the session (what friends see).

const Session := preload("res://portal/session.gd")
const PH_LEVEL := 2

signal started(intent: Dictionary)
signal finished(why: String)

var portal: Node
var game: Node
var intent := {}
var running := false
var game_state: Object              # RtaGameState
var poll_clock := 0.0
var last_level := ""
var stub := false


func start(p_intent: Dictionary, reveal_now := true) -> void:
	intent = p_intent
	stub = bool(portal.options.stub_game)
	if game == null:
		game = _make_game()
		if game == null:
			portal.call("toast", "The game scene is missing from this build.", "error")
			return
		portal.game_slot.add_child(game)
	else:
		_wake(true)
	running = true
	if reveal_now:
		portal.call("set_shown", false)
	started.emit(intent)


func prepare() -> void:
	# the game scene behind the portal, booting (a room with the game's side: gameflow.gd); the portal stays in front
	if game != null:
		return
	game = _make_game()
	if game == null:
		return
	intent = {"kind": "room"}
	portal.game_slot.add_child(game)
	portal.call("set_shown", true, true)
	print("portal: the game scene is starting behind the portal")


func reveal() -> void:
	# the portal gets out of the way of a game that was started with reveal_now = false
	if running:
		portal.call("set_shown", false)


func _make_game() -> Node:
	if stub:
		var s: Node = (load("res://portal/dev/stub_game.gd") as GDScript).new()
		s.name = "StubGame"
		return s
	if not ResourceLoader.exists("res://main.tscn"):
		return null
	var g: Node = (load("res://main.tscn") as PackedScene).instantiate()
	# what the portal knows goes into the game scene's own options before its _ready reads the command line
	var opt: Variant = g.get("opt")
	if opt is Dictionary:
		var profile: RefCounted = portal.profile
		if String(opt.get("disc", "")) == "":
			opt["disc"] = profile.disc_path()
		# the game as the portal hands it over: scene mode - the 3-D scene under Godot's camera and lights, the art pack,
		# the new HUD (main.gd); "--mode picture|draw" on the command line still decides, since main.gd reads it after this
		opt["mode"] = "scene"
		opt["view"] = String(profile.setting("view"))
		# the picture shape: the window's for Remastered (wide), 4:3 for Classic whatever the setting (the game as it was)
		var wide := bool(profile.setting("wide")) and String(profile.edition()) != "classic"
		if wide:
			opt["aspect_window"] = true
		var sharp: float = [0.5, 0.75, 1.0, 1.5, 2.0][clampi(int(profile.setting("sharpness")), 0, 4)]
		if not is_equal_approx(sharp, 1.0) and opt.get("size", Vector2i.ZERO) == Vector2i.ZERO:
			var pixels := Vector2(get_window().size) * sharp
			opt["size"] = Vector2i(int(pixels.y * (pixels.x / pixels.y if wide else 4.0 / 3.0)), int(pixels.y))
		if String(profile.setting("interface")) == "original":
			opt["game_hud"] = true
		var e := edition_options()
		if not e.is_empty():
			# Classic / Remastered (edition.gd): the existing options, set from the one choice; a key given on the
			# command line (--combat, --aim, --display-rate, --view, --look) is read by main.gd after this and wins
			opt["edition"] = String(e.edition)
			opt["view"] = String(e.view)
			opt["views_locked"] = bool(e.views_locked)
			opt["combat"] = String(e.combat)
			opt["aim"] = String(e.aim)
			opt["display_rate"] = String(e.display_rate)
			opt["hud_mode"] = String(e.hud_mode)
			opt["boss_music"] = String(e.music)
			opt["boss_music_er"] = String(e.music_er)
			if String(e.look) != "":
				opt["look"] = String(e.look) if String(opt.get("look", "")) == "" else String(e.look) + "," + String(opt.look)
			print("portal: the game as %s: %s" % [String(e.edition), str(e)])
		if portal.gameflow.active:
			# the game walks by itself to its title screen, where the room's character screens and launch begin
			var more: PackedStringArray = opt.get("args", PackedStringArray())
			if not more.has("net2-boot=1"):
				more.append_array(PackedStringArray(["--opt", "net2-boot=1"]))
			# Remastered: the game's tables sized for four are moved at power-on, so that this copy can play a room of up to
			# eight (docs/issues/native-8-players.md; a library without the relocatable translation ignores it).  Classic
			# runs the game's own memory layout, untouched.
			if String(e.get("edition", "")) == "remastered" and not more.has("party8=1"):
				more.append_array(PackedStringArray(["--opt", "party8=1"]))
			opt["args"] = more
	return g


func edition_options() -> Dictionary:
	var Edition: GDScript = load("res://portal/edition.gd")
	return Edition.call("game_options", String(portal.profile.edition()), String(portal.profile.setting("view")), String(portal.profile.setting("er_outfits")))


func apply_edition() -> void:
	# the choice changed while the game scene is there: what can change at once does (main.gd apply_settings)
	if game == null or stub or not game.has_method("apply_settings"):
		return
	var e := edition_options()
	if not e.is_empty():
		game.call("apply_settings", {"edition": e})


func _wake(awake: bool) -> void:
	if game == null:
		return
	game.process_mode = Node.PROCESS_MODE_INHERIT if awake else Node.PROCESS_MODE_DISABLED
	var player: Variant = game.get("player")
	if player is AudioStreamPlayer:
		(player as AudioStreamPlayer).stream_paused = not awake


func finish(why: String) -> void:
	if not running and not portal.gameflow.active:
		return
	running = false
	if why != "room" and not portal.gameflow.active:
		_wake(false)                # alone: the game stands still behind the portal; in a room it must go on
	portal.call("set_shown", true, game != null)
	finished.emit(why)
	if portal.session.available():
		portal.session.set_game("")


func quit_game() -> bool:
	# true: the game scene ends the program itself (it writes its figures and stops the machine)
	if game != null and game.has_method("_finish"):
		_wake(true)
		game.call("_finish", 0)
		return true
	return false


func apply_view(view: String) -> void:
	# the camera view takes effect at once in a running game
	if game != null:
		var machine: Variant = game.get("machine")
		if machine is Object and machine != null and (machine as Object).has_method("set_option"):
			(machine as Object).call("set_option", "view", view)


func _process(delta: float) -> void:
	if not running or game == null or stub:
		return
	poll_clock += delta
	if poll_clock < 1.0:
		return
	poll_clock = 0.0
	var machine: Variant = game.get("machine")
	if not (machine is Object) or machine == null or not bool(game.get("started")) or not ClassDB.class_exists("RtaGameState"):
		return
	if game_state == null:
		game_state = ClassDB.instantiate("RtaGameState")
	if not game_state.call("update", machine):
		return
	var frame: Dictionary = game_state.call("get_frame")
	var slot := int(frame.get("local_slot", 0))
	var p: Dictionary = game_state.call("get_player", maxi(slot, 0))
	if bool(p.get("present", false)) and String(p.get("name", "")) != "":
		var c := {"name": String(p.name), "cls": String(p.get("class_name", "")), "level": int(p.get("level", 0))}
		if c != portal.profile.character():
			portal.call("choose_character", c)
	var level := String(frame.get("level", "")) if (int(frame.get("phase", 0)) & PH_LEVEL) != 0 else ""
	if level != last_level:
		last_level = level
		if portal.session.available():
			portal.session.set_game(level)      # what friends see; the room itself is told by the launch (net2/launch.cpp)
