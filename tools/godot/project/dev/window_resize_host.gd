extends SceneTree
# Integration test host: run main.gd unchanged apart from a rig command that
# resizes its real window. The ordinary host's size_changed connection handles it.
# Needs the player's locally built game library and disc, like main.gd.
# Godot --path PROJECT --script res://dev/window_resize_host.gd -- --test resize \
#   --mode draw --aspect window --no-sound --no-hud --disc DISC --lib LIB --script RIG
# In RIG: app test_resize WIDTH HEIGHT, then wait before app effective/windowshot.
# RTA_RESIZE_TEST_BASE may select a private saved older main.gd for a negative control.

const WRAPPER := """extends %s
func _host_command(text: String) -> void:
	var words := text.split(" ", false)
	if words.size() == 3 and words[0] == "test_resize":
		get_window().size = Vector2i(words[1].to_int(), words[2].to_int())
	else:
		super._host_command(text)
"""
var host_script: GDScript


func _initialize() -> void:
	_start_host.call_deferred()


func _start_host() -> void:
	var base := OS.get_environment("RTA_RESIZE_TEST_BASE")
	if base == "":
		base = "res://main.gd"
	host_script = GDScript.new()
	host_script.source_code = WRAPPER % JSON.stringify(base)
	if host_script.reload() != OK:
		printerr("window_resize_host: could not load the host script")
		quit(2)
		return
	root.add_child(host_script.new())
