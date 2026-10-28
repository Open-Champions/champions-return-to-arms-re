extends SceneTree
# Headless production portal -> Session -> real-library regression before game boot.
# No disc, game data, RtaMachine.start, service sockets or GPU are needed. The session
# uses the library's authored mock; its library must be explicitly outside automatic
# search locations so a preloaded RtaMachine cannot hide a missing config.library.
# godot --headless --path PROJECT --script res://portal/dev/session_library_test.gd --
#   --lib ABSOLUTE_LIBRARY --out PRIVATE_DIR [--expect available|unavailable]

var checks := 0
var failures := 0
var rows: Array = []
var output := ""
var expected := "available"


func check(ok: bool, label: String) -> void:
	checks += 1
	rows.append({"label": label, "passed": ok})
	if not ok:
		failures += 1
		printerr("portal_session_library: FAIL ", label)


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var at := args.find("--out")
	if at >= 0 and at + 1 < args.size():
		output = ProjectSettings.globalize_path(args[at + 1])
	at = args.find("--expect")
	if at >= 0 and at + 1 < args.size():
		expected = args[at + 1]
	if output == "" or expected not in ["available", "unavailable"]:
		printerr("portal_session_library: --out PRIVATE_DIR [--expect available|unavailable] required")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(output) != OK:
		printerr("portal_session_library: cannot create private output")
		quit(2)
		return
	check(DisplayServer.get_name().to_lower() == "headless", "headless test uses no GPU viewport")
	check(ClassDB.class_exists("RtaNet2") and ClassDB.class_exists("RtaMachine"), "production extension classes exist")
	if failures > 0:
		_finish({})
		return
	var machine: Object = ClassDB.instantiate("RtaMachine")
	check(not bool(machine.call("has", "net2")), "fresh process has not preloaded a game library")
	check(String(machine.call("info")) == "", "simulation has not started before the portal session")
	var Profile: GDScript = load("res://portal/profile.gd")
	var Session: GDScript = load("res://portal/session.gd")
	var Portal: GDScript = load("res://portal/portal.gd")
	var Finder: GDScript = load("res://gamelib.gd")
	var profile: RefCounted = Profile.new()
	profile.call("load_from", output.path_join("profile"))
	profile.call("set_name_shown", "Portal test")
	var chosen := String(profile.call("library_path"))
	check(chosen != "" and FileAccess.file_exists(chosen), "profile resolves the explicit --lib file")
	check(String(Finder.call("find", "")) == "", "automatic library search is empty in the isolated profile")
	var session: Node = Session.new()
	var portal: Node = Portal.new()
	portal.set("profile", profile)
	portal.set("session", session)
	var options: Dictionary = portal.get("options")
	options.mock = true
	options.test = "session-library"
	portal.set("options", options)
	# This is the actual production method. Do not construct or start a game node,
	# and do not load through RtaMachine before it: that would conceal the regression.
	portal.call("_open_session")
	var available := bool(session.call("available"))
	check(available == (expected == "available"), "initial portal session availability matches expectation")
	var me: Dictionary = session.call("me")
	if available:
		check(bool(session.get("is_mock")) and bool(me.get("mock", false)), "initial session uses the library's mock without a service")
		check(String(me.get("name", "")) == "Portal test", "initial session receives the portal profile name")
		check(bool(machine.call("has", "net2")), "portal session loaded the actual API-compatible library")
		check(RtaNet2.from_library(), "session functions resolve from the real library")
	else:
		check(String(me.get("problem", "")).contains("not part of this build"), "unavailable session exposes the reported portal fallback")
	check(String(machine.call("info")) == "", "session initialization leaves game simulation unstarted")
	var result := {"available": available, "expected": expected, "library": chosen, "session": me,
		"simulation_started": String(machine.call("info")) != "", "display_driver": DisplayServer.get_name()}
	session.call("close")
	check(not bool(session.call("available")), "closing the initial session releases it")
	portal.free()
	session.free()
	machine = null
	_finish(result)


func _finish(result: Dictionary) -> void:
	result["checks"] = checks
	result["failures"] = failures
	result["passed"] = failures == 0
	result["results"] = rows
	var file := FileAccess.open(output.path_join("result.json"), FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(result, "  "))
	print("portal_session_library: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
