extends Node
# join_test.gd - a development aid: the game scene under the portal, driven by code, to see that the joins hold
# (docs/issues/native-godot.md, "The portal's joins").  Run as the first scene:
#   python3 tools/godot/run.py res://dev/join_test.tscn -- --disc IMAGE --test "portal joins" --script ROUTE
#       --data DIR --join-data DIR --join-shots DIR --mode scene --window 640x360
# (--script: a route to the first level; this scene makes the portal with `embedded` set, so the portal does not
# pass straight on because of it.)  Prints one line per check, "join: PASS ..." / "join: FAIL ...", and ends the
# program through the portal's own quit.

var portal: Node
var game: Node
var shots := ""
var failed := 0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var data := "user://join-test"
	var at := args.find("--join-data")
	if at >= 0 and at + 1 < args.size():
		data = args[at + 1]
	at = args.find("--join-shots")
	if at >= 0 and at + 1 < args.size():
		shots = args[at + 1]
	portal = (load("res://portal/portal.tscn") as PackedScene).instantiate()
	var options: Dictionary = portal.get("options")
	options["embedded"] = true
	options["test"] = "joins"
	options["data"] = data
	add_child(portal)
	AudioServer.set_bus_mute(0, true)
	_run.call_deferred()


func check(ok: bool, what: String) -> void:
	if not ok:
		failed += 1
	print("join: %s %s" % ["PASS" if ok else "FAIL", what])


func wait_for(test: Callable, seconds: float) -> bool:
	var until := Time.get_ticks_msec() + int(seconds * 1000.0)
	while Time.get_ticks_msec() < until:
		if test.call():
			return true
		await get_tree().process_frame
	return test.call()


func shot(name: String) -> void:
	if shots == "":
		return
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(shots.path_join(name + ".png"))
	print("join: wrote ", shots.path_join(name + ".png"))


func _run() -> void:
	await get_tree().process_frame
	var profile: RefCounted = portal.get("profile")
	if not profile.call("first_start_done"):
		profile.call("set_name_shown", "Tester")
	# what the portal stores, before the first start
	profile.call("set_setting", "view", "shoulder")
	profile.call("set_setting", "wide", false)
	profile.call("set_setting", "sharpness", 1)
	profile.call("set_setting", "music", 0.5)
	profile.call("set_setting", "effects", 1.0)
	var handover: Node = portal.get("handover")
	handover.call("start", {"kind": "alone"})
	game = handover.get("game")
	check(game != null and game.get("portal") == portal, "the game scene is under the portal and knows it")
	if game == null:
		get_tree().quit(1)
		return
	check(await wait_for(func() -> bool: return bool(game.get("started")), 20.0), "the machine started")
	check(not bool(portal.get("shown")) and not bool(game.get("input_held")), "the portal is out of the way and the controller is the game's")
	var machine: Object = game.get("machine")
	var in_level := func() -> bool:
		var view: Dictionary = machine.call("get_view")
		return (int(machine.call("peek_u32", 0x41B510)) & 0xFF) == 0 and bool(view.get("have_player", false)) and int(game.get("blanks")) > 600
	check(await wait_for(in_level, 150.0), "the script reached the first level (blank %d)" % int(game.get("blanks")))
	await wait_for(func() -> bool: return int(machine.call("get_view").get("shown", 0)) == 3, 6.0)
	check(int(machine.call("get_view").get("mode", -1)) == 3, "view at the first start: shoulder is selected (mode %s)" % str(machine.call("get_view").get("mode", -1)))
	var drawer: Object = game.get("drawer")
	var window := Vector2(get_window().size)
	var size0: Vector2i = drawer.call("get_output_size")
	check(absf(size0.y - window.y * 0.75) <= 2.0, "sharpness at the first start: the picture is %d high, the window %d (0.75)" % [size0.y, int(window.y)])
	check(absf(float(machine.call("get_frame_aspect")) - 4.0 / 3.0) < 0.01, "picture shape at the first start: 4:3 (%.3f)" % float(machine.call("get_frame_aspect")))
	await shot("join-1-game-under-the-portal")
	# changed while the game runs: the game scene looks at the stored settings twice a second
	profile.call("set_setting", "view", "first")
	profile.call("set_setting", "wide", true)
	profile.call("set_setting", "sharpness", 2)
	profile.call("set_setting", "music", 0.2)
	check(await wait_for(func() -> bool: return int(machine.call("get_view").get("mode", -1)) == 4, 4.0), "view changed while running: first person")
	var wide := window.x / window.y
	check(await wait_for(func() -> bool: return absf(float(machine.call("get_frame_aspect")) - wide) < 0.02, 6.0),
		"picture shape changed while running: %.3f, the window's is %.3f" % [float(machine.call("get_frame_aspect")), wide])
	var size1: Vector2i = drawer.call("get_output_size")
	check(absf(size1.y - window.y) <= 2.0, "sharpness changed while running: the picture is %d high" % size1.y)
	var stored: Dictionary = game.get("stored")
	check(is_equal_approx(float(stored.get("music", -1.0)), 0.2) and not stored.has("music_said"), "music volume handed to the library (%.2f)" % float(stored.get("music", -1.0)))
	await get_tree().create_timer(1.0).timeout
	await shot("join-2-first-person-wide")
	# the portal in front of a session that keeps running
	var blanks := int(game.get("blanks"))
	portal.call("set_shown", true, true)
	await get_tree().create_timer(1.0).timeout
	check(bool(game.get("input_held")), "the portal in front: the controller is held")
	check(int(game.get("blanks")) > blanks + 20, "... and the game goes on behind it (%d blanks in a second)" % (int(game.get("blanks")) - blanks))
	await shot("join-3-portal-in-front-of-the-running-game")
	portal.call("set_shown", false)
	await get_tree().create_timer(0.4).timeout
	check(not bool(game.get("input_held")), "the portal away: the controller is the game's again")
	# the session is over: the portal comes back, the program goes on
	var said := [""]
	game.connect("session_over", func(why: String) -> void: said[0] = why)
	game.call("_say_over", "test")
	await get_tree().create_timer(0.8).timeout
	check(said[0] == "test" and bool(portal.get("shown")) and not bool(handover.get("running")), "session over: the signal came, the portal is in front, the hand-over is closed")
	check(game.process_mode == Node.PROCESS_MODE_DISABLED, "... the game scene stands still behind it, and the program is still here")
	await shot("join-4-portal-after-the-session")
	# play again: the same scene is woken
	blanks = int(game.get("blanks"))
	handover.call("start", {"kind": "alone"})
	await get_tree().create_timer(1.0).timeout
	check(int(game.get("blanks")) > blanks + 20 and not bool(game.get("input_held")), "play again: the game runs on (%d blanks)" % (int(game.get("blanks")) - blanks))
	print("join: %d checks failed" % failed)
	portal.call("quit")
