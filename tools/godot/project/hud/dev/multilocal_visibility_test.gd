extends SceneTree
# Authored state only: call the production HUD visibility function directly.
const Hud := preload("res://hud/hud.gd")
var failures: Array[String] = []
var count := 0

func _case(label: String, reason: String, players: int, shown: int, phase: int, expected: bool, mode := "new", fallback := true, present := true, valid := true) -> void:
	var hud := Hud.new()
	var root := Control.new()
	var status := Control.new()
	status.name = "Status"
	var pause := Control.new()
	pause.name = "Pause"
	hud.add_child(root)
	root.add_child(status)
	root.add_child(pause)
	hud.set("root", root)
	hud.set("pieces", [status, pause])
	hud.set("ok", valid)
	hud.set("phase", phase)
	hud.set("frame", {"player_count": players, "view": {"fallback": fallback, "why": reason, "shown": shown}})
	hud.set("me", {"present": true} if present else {})
	hud.set("dt", 1.0) # enough neutral time to complete either visibility fade
	var setting: Dictionary = hud.get("setting")
	setting.mode = mode
	hud.set("setting", setting)
	hud.call("_visibility")
	var visible := float(hud.get("show")) >= 0.99 and status.visible and status.modulate.a >= 0.99
	var hidden := float(hud.get("show")) == 0.0 and not status.visible and status.modulate.a == 0.0
	if not (visible if expected else hidden):
		failures.append(label)
	if phase & Hud.PH_PAUSE_MENU and valid and mode != "original":
		if not pause.visible or float(hud.get("pause_show")) < 0.99:
			failures.append(label + ":pause")
	count += 1
	hud.free()

func _initialize() -> void:
	_case("normal one-player view", "", 1, 2, Hud.PH_LEVEL, true, "new", false)
	_case("existing death exception", "death", 1, 0, Hud.PH_LEVEL, true)
	_case("two local full reason", "more than one local player", 2, 0, Hud.PH_LEVEL, true)
	_case("two local15char reason", "more than one l", 2, 0, Hud.PH_LEVEL, true)
	_case("four local overhead", "more than one l", 4, 0, Hud.PH_LEVEL, true)
	_case("eight local overhead", "more than one l", 8, 0, Hud.PH_LEVEL, true)
	_case("one player cannot use multi exception", "more than one l", 1, 0, Hud.PH_LEVEL, false)
	_case("no players cannot use multi exception", "more than one l", 0, 0, Hud.PH_LEVEL, false)
	_case("wrong shown view", "more than one l", 2, 2, Hud.PH_LEVEL, false)
	_case("missing shown view", "more than one l", 2, -1, Hud.PH_LEVEL, false)
	_case("unknown fallback", "unknown", 2, 0, Hud.PH_LEVEL, false)
	_case("empty fallback reason", "", 2, 0, Hud.PH_LEVEL, false)
	_case("short prefix not accepted", "more than one", 2, 0, Hud.PH_LEVEL, false)
	_case("other longer reason not accepted", "more than one local player unknown", 2, 0, Hud.PH_LEVEL, false)
	_case("loading reason", "loading", 2, 0, Hud.PH_LEVEL, false)
	_case("cutscene reason", "cutscene", 2, 0, Hud.PH_LEVEL, false)
	_case("dialogue reason", "dialogue", 2, 0, Hud.PH_LEVEL, false)
	for flag in [Hud.PH_FRONTEND, Hud.PH_LOADING, Hud.PH_MENU, Hud.PH_PAUSE_MENU, Hud.PH_CUTSCENE, Hud.PH_DIALOGUE, Hud.PH_GATE_MENU]:
		_case("phase guard %d" % flag, "more than one l", 2, 0, Hud.PH_LEVEL | flag, false)
	_case("Classic original HUD", "more than one l", 2, 0, Hud.PH_LEVEL, false, "original")
	_case("no local player", "more than one l", 2, 0, Hud.PH_LEVEL, false, "new", true, false)
	_case("invalid state", "more than one l", 2, 0, Hud.PH_LEVEL, false, "new", true, true, false)
	_case("outside level", "more than one l", 2, 0, 0, false)
	print("HUD_MULTILOCAL_VISIBILITY_TEST ", "PASS" if failures.is_empty() else "FAIL", ": ", count, " cases; failures ", failures)
	quit(0 if failures.is_empty() else 1)
