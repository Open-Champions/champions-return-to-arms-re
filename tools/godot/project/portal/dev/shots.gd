extends Node
# shots.gd - the portal's pictures and its scripted walk-through (a development aid).
#
# Run as the main scene of a small test window; the portal itself is put into an
# off-screen viewport of any size (1280 x 720 ... 3840 x 2160, 4:3, 21:9), driven with
# the same input events a controller or a keyboard sends, and its viewport is saved as
# PNG - Godot's own capture.  The session is the online agent's mock
# (tools/recomp/net2/session_mock.cpp); nothing leaves the program.
#
#   godot --path <project> res://portal/dev/shots.tscn -- --out DIR --portal-data DIR
#          [--only walk,states,friends,room,join,settings,ratios] [--speed 4]

const Profile := preload("res://portal/profile.gd")
const UI := preload("res://portal/ui.gd")

var out_dir := ""
var data_root := ""
var only: PackedStringArray = PackedStringArray()
var speed := "4"
var vp: SubViewport
var portal: Node
var view: TextureRect
var count := 0
var run_number := 0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var k := 0
	while k < args.size():
		match args[k]:
			"--out": out_dir = args[k + 1]; k += 1
			"--portal-data": data_root = args[k + 1]; k += 1
			"--only": only = args[k + 1].split(","); k += 1
			"--speed": speed = args[k + 1]; k += 1
		k += 1
	var window := get_window()
	window.title = "AGENT TEST - portal pictures"
	window.set_flag(Window.FLAG_NO_FOCUS, true)
	window.size = Vector2i(Vector2(480, 270) * DisplayServer.screen_get_scale())
	var area := DisplayServer.screen_get_usable_rect()
	window.position = area.position + area.size - window.size - Vector2i(24, 24)
	AudioServer.set_bus_mute(0, true)
	view = TextureRect.new()
	view.set_anchors_preset(Control.PRESET_FULL_RECT)
	view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	add_child(view)
	DirAccess.make_dir_recursive_absolute(out_dir)
	await get_tree().process_frame
	for name in ["smoke", "walk", "states", "friends", "room", "join", "settings", "ratios"]:
		if only.is_empty() and name == "smoke":
			continue
		if only.is_empty() or only.has(name):
			print("shots: ", name)
			await call("scenario_" + name)
	print("shots: %d pictures in %s" % [count, out_dir])
	get_tree().quit(0)


# ---- a portal in an off-screen viewport ----------------------------------------------------
func open_portal(size: Vector2i, setup := {}, options := {}) -> void:
	await close_portal()
	run_number += 1
	var data := data_root.path_join("run%02d" % run_number)
	DirAccess.make_dir_recursive_absolute(data)
	# what this computer "remembers" before the portal starts
	var profile := Profile.new()
	profile.load_from(data)
	if setup.has("name"):
		profile.cfg.set_value("player", "name", setup.name)
	if setup.has("character"):
		profile.set_character(setup.character)
	for c in setup.get("known", []):
		profile.remember_character(c)
	if setup.has("disc"):
		profile.set_disc_path(setup.disc)
	for key in setup.get("settings", {}):
		profile.cfg.set_value("settings", key, setup.settings[key])
	profile.save()
	vp = SubViewport.new()
	vp.size = size
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	vp.transparent_bg = false
	vp.handle_input_locally = true
	vp.gui_embed_subwindows = true
	add_child(vp)
	view.texture = vp.get_texture()
	portal = (load("res://portal/portal.tscn") as PackedScene).instantiate()
	var o := {"embedded": true, "test": "pictures", "data": data, "mock": true, "mock_speed": speed, "stub_game": true, "service": "", "start": ""}
	o.merge(options, true)
	portal.options = o
	UI.pad_glyphs = bool(setup.get("pad", false))
	vp.add_child(portal)
	await wait(0.5)


func close_portal() -> void:
	if portal != null:
		portal.session.close()
		vp.queue_free()
		portal = null
		vp = null
		await get_tree().process_frame
		await get_tree().process_frame


func wait(seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout


func mock(seconds: float) -> void:
	# wait for something the mock does `seconds` after a call, at its own speed
	await wait(seconds / float(speed) + 0.25)


func shot(name: String) -> void:
	await wait(0.30)                # transitions are over
	await RenderingServer.frame_post_draw
	var image := vp.get_texture().get_image()
	var path := out_dir.path_join(name + ".png")
	image.save_png(path)
	count += 1
	print("shots: wrote %s (%d x %d)" % [path, image.get_width(), image.get_height()])


func send(event: InputEvent) -> void:
	vp.push_input(event)
	await get_tree().process_frame


func pad(button: int) -> void:
	var e := InputEventJoypadButton.new()
	e.device = 0
	e.button_index = button
	e.pressed = true
	await send(e)
	var r := InputEventJoypadButton.new()
	r.device = 0
	r.button_index = button
	r.pressed = false
	await send(r)
	await wait(0.05)


func key(code: int, unicode := 0) -> void:
	var e := InputEventKey.new()
	e.keycode = code
	e.physical_keycode = code
	e.unicode = unicode
	e.pressed = true
	await send(e)
	var r := InputEventKey.new()
	r.keycode = code
	r.physical_keycode = code
	r.pressed = false
	await send(r)
	await wait(0.03)


func type(text: String) -> void:
	for ch in text:
		var c := ch.unicode_at(0)
		var code := c
		if c >= 97 and c <= 122:
			code = c - 32
		await key(code, c)


func focus_key(name: String) -> bool:
	# puts the focus on the control a screen calls `name` (for long walks; the direction pad is exercised elsewhere)
	var target: Control = portal.screen.call("find_key", portal.screen, name)
	if target == null:
		target = _find_in(portal.root, name)
	if target == null:
		print("shots: NO CONTROL ", name)
		return false
	target.grab_focus()
	await get_tree().process_frame
	return true


func _find_in(node: Node, name: String) -> Control:
	for child in node.get_children():
		if child is Control and "key" in child and String(child.get("key")) == name:
			return child
		var found := _find_in(child, name)
		if found != null:
			return found
	return null


func focused() -> String:
	var f := vp.gui_get_focus_owner()
	return String(f.get("key")) if f != null and "key" in f else (String(f.name) if f != null else "(none)")


func pad_type(text: String) -> void:
	# on the on-screen keys: the focus to the letter, then A
	for ch in text:
		var name := "key_" + ch.to_lower()
		if ch == " ":
			name = "key_space"
		var shifted: bool = portal.screen.keys != null and bool(portal.screen.keys.shift)
		if ch != " " and ch.to_lower() != ch.to_upper() and (ch == ch.to_upper()) != shifted and portal.screen.keys.mode != "code":
			await focus_key("key_shift")
			await pad(JOY_BUTTON_A)
		await focus_key(name)
		await pad(JOY_BUTTON_A)


# ---- scenarios -----------------------------------------------------------------------------
func scenario_smoke() -> void:
	await open_portal(Vector2i(1920, 1080), {"pad": true})
	await shot("smoke-1-first")
	await pad_type("Tester")
	await shot("smoke-2-name")
	print("shots: focus ", focused())
	await pad(JOY_BUTTON_START)
	await shot("smoke-3-home")
	await pad(JOY_BUTTON_DPAD_DOWN)
	await pad(JOY_BUTTON_DPAD_DOWN)
	print("shots: focus after two downs ", focused())
	await shot("smoke-4-home-join")
