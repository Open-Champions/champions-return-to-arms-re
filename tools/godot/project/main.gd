extends Node
# main.gd - the translated game in a Godot window.
#
# The game itself is the library built by tools/godot/build.py (its own code translated to
# C++, no emulator); this script is the host: it starts the machine, gives it keyboard and
# controller through Godot's input once per picture, plays its sound through Godot's audio
# and shows the frame - one of three ways (--mode):
#   picture  the library's own renderer draws off screen and the picture is shown as a texture
#   draw     Godot draws the frame's draw list itself (RtaDrawer: meshes and shader materials
#            through the RenderingServer)
#   scene    as draw, with the 3-D scene handed over in world space under a Godot camera
#
# Options go after "--" on Godot's command line (godot --path <project> -- --disc IMAGE ...):
#   --disc IMAGE        your disc image of SLUS-20973 v2.00 (or $RTA_DISC; else a file dialog asks once)
#   --data DIR          memory cards (default: user://data)
#   --workspace DIR     where SLUS_209.73, names.tsv and symbols/ are (names for scripts); optional
#   --lib FILE          the game library (default: librta_game beside the extension in bin/)
#   --mode picture|draw|scene      (default picture)
#   --size WxH          the size the picture is drawn at (default: the window's own pixels)
#   --window WxH        the window's size in points
#   --aspect W:H        the shape of the 3-D view (default 4:3; "window": the window's)
#   --samples N         multisampling of the 3-D surface (0, 2, 4, 8)
#   --script FILE       a script in the rig's language (tools/rig); its "app shot FILE.png" lines write pictures:
#                       in picture mode the library's own, in the other modes Godot's capture of what it drew
#                       ("app windowshot FILE.png": what is in the Godot window itself, the root viewport)
#   --godot-shots DIR   write Godot's capture for every "app shot" into DIR (by file name) instead
#   --unpaced           as fast as it goes (tests)
#   --mute              no sound is heard (the sound side still runs)
#   --no-sound          the sound side is not driven by Godot's audio at all (rendered on the machine's clock)
#   --test TEXT         a test run: small window titled "AGENT TEST - TEXT" that takes no keyboard, silent
#   --stop-after N      quit after N vertical blanks
#   --figures FILE      write the timing figures there at the end
#   --speed-log N       every N vertical blanks one line: pictures a second, processor time a picture over all threads
#                       of the process (cycles do not lie, times do: read it beside the load average), late pictures
#   --view NAME         the camera view: overhead (the game's own), action, chase, shoulder, first; V cycles them
#                       (the game builds and culls each frame for the view itself: tools/recomp/app/fpview.h)
#   --no-game-hud       the game's own HUD layer is left out (for a HUD drawn by Godot)
#   --light, --shadow, --pull-back F, --orbit DEG     scene mode: see scene_view.gd
#   --look K=V[,K=V...] scene mode: the look (sky, fog, sun, shadows, bloom, anti-aliasing ...): see scene_view.gd
#   --no-hud            the new HUD (res://hud) is not added
#   --no-portal         (read by the portal: straight to this scene)
#   --net2-flow ROLE:DIR   a test: a room of our own through RtaNet2 as the portal drives it (dev/net2_flow.gd); give the
#                       runtime "--opt net2-boot=1" after "--" so that the game walks to its title screen by itself
#
# Under the portal (res://portal/portal.tscn is the project's first scene; this scene is then put under it):
#   signal session_over(why)    the game is back at its own front end after a level ("frontend"), or the machine has
#                               ended ("ended"); the portal is told (handover.finish) and the program is NOT ended
#   hold_input(on)              the controller is not the game's while the portal is in front of a running session
#   apply_settings(d)           settings the portal stores, for a running game: view, wide, sharpness
#   -- ARGS             the rest goes to the runtime as it does after rta_app's "--"
#
# In the views that look along the ground the pointer is the look (tools/recomp/app/fpcontrols.h, inside the library):
# it is hidden and held while such a view is active and the window has the keyboard; Escape gives it back, a click
# takes it again; its buttons are controller buttons there.  Never in a test window.
#
# Keyboard: W A S D left stick, arrows direction pad, I J K L triangle square cross circle,
# Q E L1 R1, 1 3 L2 R2, X C L3 R3, Return Start, Backspace Select (the native application's map).
# The first controller Godot knows is port 1 as well.

const PAD_SELECT := 0x0001
const PAD_L3 := 0x0002
const PAD_R3 := 0x0004
const PAD_START := 0x0008
const PAD_UP := 0x0010
const PAD_RIGHT := 0x0020
const PAD_DOWN := 0x0040
const PAD_LEFT := 0x0080
const PAD_L2 := 0x0100
const PAD_R2 := 0x0200
const PAD_L1 := 0x0400
const PAD_R1 := 0x0800
const PAD_TRIANGLE := 0x1000
const PAD_CIRCLE := 0x2000
const PAD_CROSS := 0x4000
const PAD_SQUARE := 0x8000

const KEY_BUTTONS := {
	KEY_UP: PAD_UP, KEY_DOWN: PAD_DOWN, KEY_LEFT: PAD_LEFT, KEY_RIGHT: PAD_RIGHT,
	KEY_I: PAD_TRIANGLE, KEY_J: PAD_SQUARE, KEY_K: PAD_CROSS, KEY_L: PAD_CIRCLE,
	KEY_Q: PAD_L1, KEY_E: PAD_R1, KEY_1: PAD_L2, KEY_3: PAD_R2, KEY_X: PAD_L3, KEY_C: PAD_R3,
	KEY_ENTER: PAD_START, KEY_KP_ENTER: PAD_START, KEY_BACKSPACE: PAD_SELECT,
}
const KEY_NAMES := {
	"w": KEY_W, "a": KEY_A, "s": KEY_S, "d": KEY_D, "up": KEY_UP, "down": KEY_DOWN, "left": KEY_LEFT, "right": KEY_RIGHT,
	"i": KEY_I, "j": KEY_J, "k": KEY_K, "l": KEY_L, "q": KEY_Q, "e": KEY_E, "1": KEY_1, "3": KEY_3, "x": KEY_X, "c": KEY_C,
	"return": KEY_ENTER, "backspace": KEY_BACKSPACE,
}
const JOY_BUTTONS := {
	JOY_BUTTON_A: PAD_CROSS, JOY_BUTTON_B: PAD_CIRCLE, JOY_BUTTON_X: PAD_SQUARE, JOY_BUTTON_Y: PAD_TRIANGLE,
	JOY_BUTTON_BACK: PAD_SELECT, JOY_BUTTON_START: PAD_START, JOY_BUTTON_LEFT_STICK: PAD_L3, JOY_BUTTON_RIGHT_STICK: PAD_R3,
	JOY_BUTTON_LEFT_SHOULDER: PAD_L1, JOY_BUTTON_RIGHT_SHOULDER: PAD_R1,
	JOY_BUTTON_DPAD_UP: PAD_UP, JOY_BUTTON_DPAD_DOWN: PAD_DOWN, JOY_BUTTON_DPAD_LEFT: PAD_LEFT, JOY_BUTTON_DPAD_RIGHT: PAD_RIGHT,
}
const BUTTON_NAMES := {
	"up": PAD_UP, "down": PAD_DOWN, "left": PAD_LEFT, "right": PAD_RIGHT, "cross": PAD_CROSS, "circle": PAD_CIRCLE,
	"square": PAD_SQUARE, "triangle": PAD_TRIANGLE, "l1": PAD_L1, "l2": PAD_L2, "l3": PAD_L3, "r1": PAD_R1, "r2": PAD_R2,
	"r3": PAD_R3, "start": PAD_START, "select": PAD_SELECT,
}
const STICK_DEAD_ZONE := 0.15
const TRIGGER_THRESHOLD := 0.30

var opt := {
	"disc": "", "data": "", "workspace": "", "lib": "", "mode": "picture", "size": Vector2i.ZERO, "window": Vector2i.ZERO,
	"aspect": 0.0, "aspect_window": false, "samples": 0, "script": "", "godot_shots": "", "unpaced": false, "mute": false,
	"no_sound": false, "test": "", "stop_after": 0, "figures": "", "args": PackedStringArray(),
	"view": "", "game_hud": true, "light": false, "shadow": false, "pull_back": 1.0, "orbit": 0.0,
	"look": "", "hud": true, "speed_log": 0, "net2_flow": "",
}
var speed := {"usec": 0, "cpu": 0.0, "blanks": 0, "last": 0, "late": 0, "worst": 0}
signal session_over(why: String)
const G_IN_FRONTEND := 0x41B510         # symbols: g_inFrontend (a byte)
const G_PLAYER_OBJECT := 0x4DCEC8       # g_players + 0x43d8: the first player's object, 0 while there is none
var portal: Node                        # the portal this scene runs under (null: started directly)
var input_held := false                 # the portal is in front: the controller is its own
var seen_level := false
var over_said := false
var machine_stopped := false
var mouse_motion := Vector2.ZERO        # pointer counts since the last controller read
var mouse_wheel := 0.0
var pointer_let_go := false             # Escape gave the pointer back: until the next click
var stored := {}                        # what was last taken from the portal's settings
var stored_clock := 0.0
var machine: RtaMachine
var view: Control                       # shows the picture (view.gd)
var picture_texture: ImageTexture
var drawer: Object                      # RtaDrawer, in the draw and scene modes
var scene_view: Node                    # scene_view.gd, in the scene mode
var player: AudioStreamPlayer
var started := false
var message := ""
var clock := 0.0                        # time owed to the machine
var period := 1.0 / 59.94
var blanks := 0
var pending_shots: PackedStringArray = PackedStringArray()     # Godot's captures still to write (of the frame drawn last)
var shots_written := 0
var test_pad := false                   # a script made a controller ("app gcpad connect")
var last_buttons := 0
var last_sticks := [128, 128, 128, 128]
var key_events := 0
var started_usec := 0
var process_usec := 0                   # time inside _process in all
var step_usec := 0                      # ... of it waiting in step()
var draw_usec := 0                      # ... of it handing the list to the RenderingServer
var quitting := false
var window_shots: PackedStringArray = PackedStringArray()


func _ready() -> void:
	get_tree().set_auto_accept_quit(false)
	_parse_arguments()
	var window := get_window()
	if opt.test != "":
		window.title = "AGENT TEST - " + opt.test
		window.set_flag(Window.FLAG_NO_FOCUS, true)
		if opt.window == Vector2i.ZERO:
			opt.window = Vector2i(480, 360)
	if opt.window != Vector2i.ZERO:
		window.size = Vector2i(Vector2(opt.window) * window.content_scale_factor * DisplayServer.screen_get_scale())
	if opt.test != "":
		# out of the way: the lower right corner of the screen
		var area := DisplayServer.screen_get_usable_rect()
		window.position = area.position + area.size - window.size - Vector2i(24, 24)
	if opt.unpaced:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		Engine.max_fps = 0
	view = Control.new()
	view.set_script(load("res://view.gd"))
	view.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(view)
	portal = get_tree().get_first_node_in_group("portal")
	if portal != null and (bool(portal.get("passing")) or not portal.is_ancestor_of(self)):
		portal = null
	if portal != null and portal.has_signal("shown_changed"):
		portal.connect("shown_changed", func(is_shown: bool) -> void: hold_input(is_shown))
		input_held = bool(portal.get("shown"))     # a session start keeps the room in front until everybody is in
	if opt.hud and opt.mode != "picture" and DisplayServer.get_name() != "headless" and ResourceLoader.exists("res://hud/hud.tscn"):
		var hud: Node = load("res://hud/hud.tscn").instantiate()
		add_child(hud)                      # the HUD agent's one line (docs/issues/native-hud.md)
		# The new interface in place of the game's own, unless something says otherwise: --hud MODE on the command line,
		# or the HUD's settings file (the portal's "Interface: new / original" writes it: user://hud.cfg, [hud] mode)
		if not OS.get_cmdline_user_args().has("--hud") and not FileAccess.file_exists("user://hud.cfg") and hud.has_method("command"):
			hud.call("command", ["mode", "new"])
	if opt.disc == "" and OS.has_environment("RTA_DISC"):
		opt.disc = OS.get_environment("RTA_DISC")
	if opt.disc == "":
		opt.disc = _saved_disc()
	if opt.disc == "" or not FileAccess.file_exists(opt.disc):
		_ask_for_disc()
	else:
		_start()


func _parse_arguments() -> void:
	var args := OS.get_cmdline_user_args()
	var k := 0
	while k < args.size():
		var a := args[k]
		var value := args[k + 1] if k + 1 < args.size() else ""
		match a:
			"--":
				opt.args = args.slice(k + 1)
				return
			"--disc": opt.disc = value; k += 1
			"--data": opt.data = value; k += 1
			"--workspace": opt.workspace = value; k += 1
			"--lib": opt.lib = value; k += 1
			"--mode": opt.mode = value; k += 1
			"--size": opt.size = _size_of(value); k += 1
			"--window": opt.window = _size_of(value); k += 1
			"--aspect":
				if value == "window":
					opt.aspect_window = true
				else:
					var parts := value.split(":")
					if parts.size() == 2 and parts[1].to_float() > 0:
						opt.aspect = parts[0].to_float() / parts[1].to_float()
				k += 1
			"--samples": opt.samples = value.to_int(); k += 1
			"--script": opt.script = value; k += 1
			"--godot-shots": opt.godot_shots = value; k += 1
			"--unpaced": opt.unpaced = true
			"--mute": opt.mute = true
			"--no-sound": opt.no_sound = true
			"--test": opt.test = value; k += 1
			"--stop-after": opt.stop_after = value.to_int(); k += 1
			"--figures": opt.figures = value; k += 1
			"--view": opt.view = value; k += 1
			"--no-game-hud": opt.game_hud = false
			"--light": opt.light = true
			"--shadow": opt.shadow = true
			"--pull-back": opt.pull_back = value.to_float(); k += 1
			"--orbit": opt.orbit = value.to_float(); k += 1
			"--look": opt.look = value; k += 1
			"--speed-log": opt.speed_log = value.to_int(); k += 1
			"--no-hud": opt.hud = false
			"--net2-flow": opt.net2_flow = value; k += 1
			"--offscreen", "--plain", "--no-portal": pass
			_:
				if not (a.begins_with("--portal") or a.begins_with("--hud")):
					push_warning("unknown option " + a)
				elif not value.begins_with("--"):
					k += 1
		k += 1


func _size_of(text: String) -> Vector2i:
	var parts := text.split("x")
	return Vector2i(parts[0].to_int(), parts[1].to_int()) if parts.size() == 2 else Vector2i.ZERO


func _saved_disc() -> String:
	var config := ConfigFile.new()
	if config.load("user://settings.cfg") == OK:
		return config.get_value("game", "disc", "")
	return ""


func _ask_for_disc() -> void:
	message = "Choose your disc image of Champions: Return to Arms (SLUS-20973 v2.00)."
	view.set("message", message)
	if opt.test != "" or DisplayServer.get_name() == "headless":
		# a test run never waits for a person
		printerr("rta_godot: no disc image: give --disc IMAGE after \"--\", or set RTA_DISC")
		get_tree().quit(2)
		return
	var dialog := FileDialog.new()
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.title = "Your disc image of Champions: Return to Arms (v2.00)"
	dialog.filters = PackedStringArray(["*.iso ; Disc images"])
	dialog.file_selected.connect(func(path: String) -> void:
		opt.disc = path
		var config := ConfigFile.new()
		config.set_value("game", "disc", path)
		config.save("user://settings.cfg")
		_start())
	add_child(dialog)
	dialog.popup_centered_ratio(0.7)


func _library_path() -> String:
	if opt.lib != "" and opt.lib.contains("/"):
		return opt.lib
	var name: String = opt.lib if opt.lib != "" else "librta_game"
	var file := name + (".dll" if OS.get_name() == "Windows" else ".dylib")
	# beside the extension: res://bin in the project, the application's own folder when exported
	var candidates := [ProjectSettings.globalize_path("res://bin/" + file), OS.get_executable_path().get_base_dir().path_join(file),
		OS.get_executable_path().get_base_dir().path_join("../Frameworks/" + file),
		OS.get_executable_path().get_base_dir().path_join("../Resources/" + file)]
	for path in candidates:
		if FileAccess.file_exists(path):
			return path
	return candidates[0]


func _picture_size() -> Vector2i:
	if opt.size != Vector2i.ZERO:
		return opt.size
	var pixels := get_window().size
	var shape: float = opt.aspect if opt.aspect > 0.0 else 4.0 / 3.0
	var h := pixels.y
	var w := int(round(h * shape))
	if w > pixels.x:
		w = pixels.x
		h = int(round(w / shape))
	return Vector2i(w, max(h, 224))


func _start() -> void:
	if not ClassDB.class_exists("RtaMachine"):
		_cannot_start("The extension is not there (bin/rta_godot...): python3 tools/godot/build.py all")
		return
	machine = RtaMachine.new()
	var library := _library_path()
	if not machine.load_library(library):
		_cannot_start("Cannot load the game library %s:\n%s\n(python3 tools/godot/build.py lib)" % [library, machine.get_error()])
		return
	if OS.has_environment("RTA_CWD"):
		machine.change_directory(OS.get_environment("RTA_CWD"))     # tools/godot/run.py: relative paths mean what they meant there
	if opt.aspect_window:
		opt.aspect = max(float(get_window().size.x) / get_window().size.y, 4.0 / 3.0)
	if opt.data == "":
		opt.data = ProjectSettings.globalize_path("user://data")
	var size := _picture_size()
	var own_picture: bool = opt.mode == "picture"
	var sound := 1                      # the host asks: Godot's audio thread is the sound side's clock
	if opt.no_sound:
		sound = 2
	var config := {
		"disc": opt.disc, "data": opt.data, "workspace": opt.workspace, "script": opt.script,
		"lists": 0 if own_picture else 1,
		"picture_width": size.x if own_picture else 0, "picture_height": size.y if own_picture else 0, "picture_every_frame": 1,
		"samples": opt.samples, "aspect": opt.aspect, "scene3d": 1 if opt.mode == "scene" else 0,
		"sound": sound, "gain": 1.0, "films": 1, "args": opt.args, "view": opt.view,
	}
	var result := machine.start(config)
	if result != 0:
		_cannot_start("The machine did not start: " + machine.get_error())
		return
	print("rta_godot: library %s (fix set %s, films %s), mode %s, picture %d x %d, %s" % [library,
		"applied" if machine.has("fixes") else "not applied", "linked" if machine.has("films") else "not linked", opt.mode, size.x, size.y,
		"not paced" if opt.unpaced else "paced"])
	view.set("message", "")
	if not opt.game_hud:
		machine.set_option("game_hud", "off")
	if own_picture:
		picture_texture = ImageTexture.new()
	else:
		if opt.mode == "scene":
			load("res://scene_view.gd").add_globals()       # the atmosphere's shader parameters, before a shader names them
		drawer = ClassDB.instantiate("RtaDrawer")
		drawer.call("set_shader_code", (load("res://shaders/gs_draw.gdshaderinc") as ShaderInclude).code)
		drawer.call("setup", machine, get_viewport().get_viewport_rid(), size, opt.samples)
		view.set("drawer", drawer)
		if opt.mode == "scene":
			drawer.call("set_scene_mode", true)
			scene_view = Node.new()
			scene_view.set_script(load("res://scene_view.gd"))
			scene_view.set("main", self)
			add_child(scene_view)
	if not opt.no_sound:
		player = AudioStreamPlayer.new()
		player.stream = ClassDB.instantiate("RtaAudioStream")
		add_child(player)
		if opt.mute or opt.test != "":
			player.volume_db = -80.0
			AudioServer.set_bus_mute(0, true)       # a test makes no sound, whatever was asked
		player.play()
	var refresh := DisplayServer.screen_get_refresh_rate()
	if refresh < 20.0 or refresh > 1000.0:
		refresh = 60.0
	var per_picture: float = max(1.0, round(refresh / 60.0))
	if abs(refresh / per_picture - 60.0) < 0.9:
		period = per_picture / refresh          # locked to the display: one picture every per_picture refreshes
	print("rta_godot: display %.2f Hz; one picture every %.3f ms" % [refresh, period * 1000.0])
	started = true
	started_usec = Time.get_ticks_usec()
	if opt.net2_flow != "":
		var flow := Node.new()
		flow.set_script(load("res://dev/net2_flow.gd"))
		flow.set("main", self)
		flow.call("setup", String(opt.net2_flow))
		add_child(flow)


func _cannot_start(text: String) -> void:
	view.set("message", text)
	printerr("rta_godot: " + text)
	if opt.test != "" or DisplayServer.get_name() == "headless":
		get_tree().quit(2)          # a test run never waits for a person


# The character card for the portal (card.gd): the local player's character alone, turning slowly - a texture that
# changes by itself (a SubViewport's).  null outside scene mode; empty (transparent) until the character has been seen
# standing still once.  The portal:  portrait.texture = handover.game.call("get_character_card")
func get_character_card() -> Texture2D:
	if scene_view == null or scene_view.get("card") == null:
		return null
	return scene_view.get("card").call("texture")


func has_character_card() -> bool:
	return scene_view != null and scene_view.get("card") != null and bool(scene_view.get("card").call("has_figure"))


func hold_input(on: bool) -> void:
	input_held = on
	if on and machine != null and started:
		machine.set_pad(0, 0, 128, 128, 128, 128)


func apply_settings(d: Dictionary) -> void:
	# what the portal stores, for a game that is running (at the first start the same arrive in `opt`)
	if machine == null or not started:
		return
	if d.has("view"):
		machine.set_option("view", String(d.view))
	if d.has("wide"):
		var shape: float = max(float(get_window().size.x) / get_window().size.y, 4.0 / 3.0) if bool(d.wide) else 4.0 / 3.0
		opt.aspect = shape
		machine.set_option("aspect", "%.5f" % shape)
	if d.has("sharpness") and drawer != null:
		var sharp: float = [0.5, 0.75, 1.0, 1.5, 2.0][clampi(int(d.sharpness), 0, 4)]
		var pixels := Vector2(get_window().size) * sharp
		var shape2: float = opt.aspect if opt.aspect > 0.0 else 4.0 / 3.0
		opt.size = Vector2i(int(round(pixels.y * shape2)), int(pixels.y))
		drawer.call("set_output_size", opt.size)
	if scene_view != null and d.has("look"):
		scene_view.call("set_look", String(d.look))
	if d.has("music") or d.has("effects"):
		stored["music"] = d.get("music", stored.get("music", 1.0))
		stored["effects"] = d.get("effects", stored.get("effects", 1.0))
		_volumes(float(stored.music), float(stored.effects))


func _pointer() -> void:
	# the pointer as the look: held while a look view wants it and this window is the one being played in
	if opt.test != "" or DisplayServer.get_name() == "headless":
		return
	var want: bool = machine.wants_pointer() and not input_held and not pointer_let_go and get_window().has_focus()
	var held := Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	if want != held:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if want else Input.MOUSE_MODE_VISIBLE
		mouse_motion = Vector2.ZERO
	if want and (mouse_motion != Vector2.ZERO or mouse_wheel != 0.0):
		machine.mouse(mouse_motion.x, mouse_motion.y, mouse_wheel)
	mouse_motion = Vector2.ZERO
	mouse_wheel = 0.0


func _input(event: InputEvent) -> void:
	if not started or opt.test != "":
		return
	var held := Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	var motion := event as InputEventMouseMotion
	if motion != null and held:
		mouse_motion += motion.relative
		return
	var button := event as InputEventMouseButton
	if button != null:
		if not held:
			if button.pressed:
				pointer_let_go = false      # a click takes the pointer again (when a look view wants it)
			return
		match button.button_index:
			MOUSE_BUTTON_LEFT: machine.mouse_button(0, button.pressed)
			MOUSE_BUTTON_RIGHT: machine.mouse_button(1, button.pressed)
			MOUSE_BUTTON_MIDDLE: machine.mouse_button(2, button.pressed)
			MOUSE_BUTTON_XBUTTON1: machine.mouse_button(3, button.pressed)
			MOUSE_BUTTON_XBUTTON2: machine.mouse_button(4, button.pressed)
			MOUSE_BUTTON_WHEEL_UP:
				if button.pressed:
					mouse_wheel += 1.0
			MOUSE_BUTTON_WHEEL_DOWN:
				if button.pressed:
					mouse_wheel -= 1.0
		return
	var key := event as InputEventKey
	if key != null and key.pressed and key.physical_keycode == KEY_ESCAPE and held:
		pointer_let_go = true
		get_viewport().set_input_as_handled()


func _volumes(music: float, effects: float) -> void:
	# The game's sound is one mix with the music apart (the stream driver's stream 2: option "music_volume").
	# "Effects" is everything else: the game's player carries it, and the music is set against it.
	if player != null and not (opt.mute or opt.test != ""):
		player.volume_db = linear_to_db(clampf(effects, 0.0001, 1.0))
	if machine != null and started:
		var m := clampf(music / maxf(effects, 0.01), 0.0, 1.0)
		if not machine.set_option("music_volume", "%.3f" % m) and not stored.has("music_said"):
			stored["music_said"] = true
			print("rta_godot: this library has no music volume of its own (the sound core lacks it): the music follows the effects volume")


func _portal_settings(delta: float) -> void:
	# what the portal stores, taken when it changes (the portal itself hands on the view; the rest is looked at here)
	if portal == null:
		return
	stored_clock += delta
	if stored_clock < 0.5 and not stored.is_empty():
		return
	stored_clock = 0.0
	var profile: Variant = portal.get("profile")
	if not (profile is RefCounted) or not (profile as RefCounted).has_method("setting"):
		return
	var now := {}
	for key in ["view", "wide", "sharpness", "music", "effects"]:
		now[key] = (profile as RefCounted).call("setting", key)
	var first := not stored.has("view")
	var changed := {}
	for key in now:
		if first or stored.get(key) != now[key]:
			changed[key] = now[key]
		stored[key] = now[key]
	if first:
		# (view, shape and sharpness also came with `opt` at the first start; given again here they are the same -
		# but the sharpness is a share of the window as it is NOW, and the window may have been sized since)
		get_viewport().size_changed.connect(func() -> void:
			if stored.has("sharpness"):
				apply_settings({"wide": stored.get("wide", false), "sharpness": stored.sharpness}))
	if not changed.is_empty():
		apply_settings(changed)


func _read_pad() -> void:
	_pointer()
	if input_held:
		last_buttons = 0
		last_sticks = [128, 128, 128, 128]
		machine.set_pad(0, 0, 128, 128, 128, 128)
		return
	var buttons := 0
	for key in KEY_BUTTONS:
		if Input.is_physical_key_pressed(key):
			buttons |= KEY_BUTTONS[key]
	var lx := 128
	var ly := 128
	var rx := 128
	var ry := 128
	var left := Input.is_physical_key_pressed(KEY_A)
	var right := Input.is_physical_key_pressed(KEY_D)
	var up := Input.is_physical_key_pressed(KEY_W)
	var down := Input.is_physical_key_pressed(KEY_S)
	if left != right:
		lx = 0 if left else 255
	if up != down:
		ly = 0 if up else 255
	var pads := Input.get_connected_joypads()
	if pads.size() > 0 or test_pad:
		var device: int = pads[0] if pads.size() > 0 else 0
		for button in JOY_BUTTONS:
			if Input.is_joy_button_pressed(device, button):
				buttons |= JOY_BUTTONS[button]
		if Input.get_joy_axis(device, JOY_AXIS_TRIGGER_LEFT) > TRIGGER_THRESHOLD:
			buttons |= PAD_L2
		if Input.get_joy_axis(device, JOY_AXIS_TRIGGER_RIGHT) > TRIGGER_THRESHOLD:
			buttons |= PAD_R2
		var stick := Vector2(Input.get_joy_axis(device, JOY_AXIS_LEFT_X), Input.get_joy_axis(device, JOY_AXIS_LEFT_Y))
		if stick.length() > STICK_DEAD_ZONE:
			lx = clampi(int(round(128.0 + stick.x * 127.0)), 0, 255)
			ly = clampi(int(round(128.0 + stick.y * 127.0)), 0, 255)
		stick = Vector2(Input.get_joy_axis(device, JOY_AXIS_RIGHT_X), Input.get_joy_axis(device, JOY_AXIS_RIGHT_Y))
		if stick.length() > STICK_DEAD_ZONE:
			rx = clampi(int(round(128.0 + stick.x * 127.0)), 0, 255)
			ry = clampi(int(round(128.0 + stick.y * 127.0)), 0, 255)
	if scene_view != null and scene_view.call("takes_input"):
		rx = 128
		ry = 128
	last_buttons = buttons
	last_sticks = [lx, ly, rx, ry]
	machine.set_pad(0, buttons, lx, ly, rx, ry)


func _host_command(text: String) -> void:
	# "app ..." lines of a script that are for the host: input sent through Godot's own input system
	var w := text.split(" ", false)
	if w.size() >= 3 and w[0] == "key":
		if not KEY_NAMES.has(w[2]):
			push_warning("app key: unknown key " + w[2])
			return
		var event := InputEventKey.new()
		event.physical_keycode = KEY_NAMES[w[2]]
		event.keycode = KEY_NAMES[w[2]]
		event.pressed = w[1] == "down"
		Input.parse_input_event(event)
		Input.flush_buffered_events()       # now: the next controller read is this script's next line
		key_events += 1
	elif w.size() >= 2 and w[0] == "gcpad":
		# a controller made by the script: connect | disconnect | set BUTTONS|none [lx ly rx ry [l2 r2]] (sticks -1..1)
		if w[1] == "connect":
			test_pad = true
		elif w[1] == "disconnect":
			test_pad = false
			_joy_state(0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
		elif w[1] == "set" and w.size() >= 3:
			var bits := 0
			for name in w[2].split("+"):
				bits |= BUTTON_NAMES.get(name, 0)
			var values := [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
			for n in range(3, min(w.size(), 9)):
				values[n - 3] = w[n].to_float()
			_joy_state(bits, values)
	elif w.size() >= 2 and w[0] == "windowshot":
		# what is in the Godot window itself (the root viewport), after the frame that is being made now
		window_shots.append(text.substr(text.find(w[1])))
	elif w.size() >= 1 and w[0] == "pads":
		print("[blank %d] rta_godot: controller %s; port 1 holds buttons %04x, sticks %d %d %d %d; %d key events" % [blanks,
			"made by the script" if test_pad else (Input.get_joy_name(Input.get_connected_joypads()[0]) if Input.get_connected_joypads().size() > 0 else "none"),
			last_buttons, last_sticks[0], last_sticks[1], last_sticks[2], last_sticks[3], key_events])
	elif w.size() >= 1 and (w[0] == "light" or w[0] == "camera" or w[0] == "scene" or w[0] == "look" or w[0] == "card") and scene_view != null:
		scene_view.call("command", w)
	elif w.size() >= 2 and w[0] == "hold":
		hold_input(w[1] == "on")            # test aid: as the portal does while it is in front
	elif w.size() >= 3 and w[0] == "setting":
		apply_settings({w[1]: (w[2] == "true" if w[2] in ["true", "false"] else (w[2].to_int() if w[2].is_valid_int() else w[2]))})
	elif w.size() >= 1 and w[0] == "hud":
		pass                                # the HUD's own lines (res://hud/hud.gd reads them)
	else:
		push_warning("app command not known: " + text)


func _joy_state(bits: int, values: Array) -> void:
	for button in JOY_BUTTONS:
		var event := InputEventJoypadButton.new()
		event.device = 0
		event.button_index = button
		event.pressed = (bits & JOY_BUTTONS[button]) != 0
		Input.parse_input_event(event)
	var axes := [JOY_AXIS_LEFT_X, JOY_AXIS_LEFT_Y, JOY_AXIS_RIGHT_X, JOY_AXIS_RIGHT_Y, JOY_AXIS_TRIGGER_LEFT, JOY_AXIS_TRIGGER_RIGHT]
	for n in range(6):
		var motion := InputEventJoypadMotion.new()
		motion.device = 0
		motion.axis = axes[n]
		motion.axis_value = values[n]
		Input.parse_input_event(motion)
	Input.flush_buffered_events()


func _write_pending_shots() -> void:
	# Godot's own picture of the frame it drew last: the shown surface's viewport, read back
	if pending_shots.is_empty() or drawer == null:
		return
	var image: Image = drawer.call("get_shown_image")
	if OS.has_environment("RTA_GODOT_DUMP"):
		drawer.call("dump_surfaces", String(OS.get_environment("RTA_GODOT_DUMP")).path_join(String(pending_shots[0]).get_file().get_basename()))
	for path in pending_shots:
		if image == null:
			print("rta_godot: no picture to write to " + path)
			continue
		var target := path
		if opt.godot_shots != "":
			target = String(opt.godot_shots).path_join(path.get_file())
		image.save_png(target)
		shots_written += 1
		print("rta_godot: wrote %s (%d x %d), Godot's own drawing" % [target, image.get_width(), image.get_height()])
	pending_shots = PackedStringArray()


func _speed_log() -> void:
	var now := Time.get_ticks_usec()
	if speed.last != 0:
		var gap: int = now - int(speed.last)
		if gap > 20000:
			speed.late += 1
		speed.worst = max(int(speed.worst), gap)
	speed.last = now
	if blanks - int(speed.blanks) < int(opt.speed_log):
		return
	var cpu := 0.0
	for word in machine.info().split(" "):
		if word.begins_with("cpu_ms="):
			cpu = word.substr(7).to_float()
	if int(speed.usec) != 0:
		var n := float(blanks - int(speed.blanks))
		var view: Dictionary = machine.get_view()
		print("rta_godot: speed: blanks %d..%d: %.1f pictures a second, %.2f ms of processor time a picture (all threads), %d later than 20 ms, the longest %.1f ms; view %s, level %s, %d draws %d vertices" % [
			int(speed.blanks), blanks, n * 1000000.0 / float(now - int(speed.usec)), (cpu - float(speed.cpu)) / n, int(speed.late), int(speed.worst) / 1000.0,
			str(view.get("mode_name", view.get("mode", ""))), machine.peek_string(0x41B721, 16), machine.get_draw_count(), machine.get_vertex_count()])
	speed.usec = now
	speed.cpu = cpu
	speed.blanks = blanks
	speed.late = 0
	speed.worst = 0


func _take_frame() -> void:
	blanks += 1
	if int(opt.speed_log) > 0:
		_speed_log()
	for text in machine.get_host_commands():
		_host_command(text)
	if drawer != null:
		var t0 := Time.get_ticks_usec()
		if scene_view != null:
			scene_view.call("before_frame")
		drawer.call("submit")
		if scene_view != null:
			scene_view.call("frame")
		draw_usec += Time.get_ticks_usec() - t0
		for path in machine.get_shots():
			pending_shots.append(path)


func _process(delta: float) -> void:
	if not started or quitting:
		return
	var t0 := Time.get_ticks_usec()
	_write_pending_shots()
	var got_any := false
	if opt.unpaced:
		# as fast as it goes: with Godot drawing, one list per rendered frame (every one is drawn);
		# with the library's own picture, as many blanks as fit into 12 ms
		while true:
			_read_pad()
			var s0 := Time.get_ticks_usec()
			var got := machine.step(-1)
			step_usec += Time.get_ticks_usec() - s0
			if got != 1:
				break
			_take_frame()
			got_any = true
			if drawer != null or Time.get_ticks_usec() - t0 > 12000 or (opt.stop_after > 0 and blanks >= opt.stop_after):
				break
	else:
		clock += delta
		if clock >= period - 0.0005:
			clock -= period
			if clock > period:
				clock = 0.0                 # stood still: no burst afterwards
			_read_pad()
			var s0 := Time.get_ticks_usec()
			var got := machine.step(8)      # the frame let go now is usually there within a few milliseconds
			step_usec += Time.get_ticks_usec() - s0
			while got == 1:
				_take_frame()
				got_any = true
				if drawer != null:
					break                   # one list per rendered frame: the next is taken at the next picture
				got = machine.poll(0)
	if got_any and drawer == null:
		var image := machine.get_picture()
		if image != null:
			if picture_texture.get_size() != Vector2(image.get_size()):
				picture_texture.set_image(image)
			else:
				picture_texture.update(image)
			view.set("texture", picture_texture)
			view.set("aspect", machine.get_frame_aspect())
			view.queue_redraw()
	elif got_any:
		view.set("aspect", machine.get_frame_aspect())
		view.queue_redraw()
	process_usec += Time.get_ticks_usec() - t0
	if not window_shots.is_empty():
		var paths := window_shots
		window_shots = PackedStringArray()
		await RenderingServer.frame_post_draw
		var image := get_viewport().get_texture().get_image()
		for path in paths:
			image.save_png(path)
			print("rta_godot: wrote %s (%d x %d), the Godot window's own picture" % [path, image.get_width(), image.get_height()])
	_watch_session()
	_portal_settings(delta)
	if machine.ended() and machine.poll(0) != 1:
		if portal != null and opt.script == "":
			_end_session("ended")           # under the portal the program goes on: the portal comes back
		else:
			_finish(machine.exit_code())
	elif opt.stop_after > 0 and blanks >= opt.stop_after:
		_finish(0)


func _watch_session() -> void:
	# "the session is over": the game is back at its own front end after a level was played
	if (blanks & 31) != 0 or machine == null:
		return
	var front := (machine.peek_u32(G_IN_FRONTEND) & 0xFF) != 0
	if not front and machine.peek_u32(G_PLAYER_OBJECT) != 0:
		seen_level = true               # a level with a character in it (not the card screens before the front end)
		over_said = false
	elif front and seen_level and not over_said:
		over_said = true
		seen_level = false
		_say_over("frontend")


func _say_over(why: String) -> void:
	print("rta_godot: the session is over (%s) at vertical blank %d%s" % [why, blanks, "" if portal != null else "; no portal to go back to"])
	session_over.emit(why)
	if portal != null:
		var handover: Variant = portal.get("handover")
		if handover is Node and (handover as Node).has_method("finish"):
			(handover as Node).call("finish", "over")


func _end_session(why: String) -> void:
	# the machine has ended and the program goes on (one machine per run of the program: a new game needs a restart)
	if machine_stopped:
		return
	machine_stopped = true
	started = false
	_write_pending_shots()
	print(_figures())
	machine.stop()
	if player != null:
		player.stop()
	_say_over(why)


func _figures() -> String:
	var n: float = max(blanks, 1)
	var wall := (Time.get_ticks_usec() - started_usec) / 1000.0
	var text := "rta_godot: %d vertical blanks in %.0f ms: %.1f pictures a second; this script per picture: %.2f ms in _process, of it %.2f ms waiting for the machine, %.2f ms handing the list to the RenderingServer; %d of Godot's own pictures written; mixer asked for %.2f s of sound in %d requests\n" % [
		blanks, wall, 1000.0 * n / max(wall, 1.0), process_usec / 1000.0 / n, step_usec / 1000.0 / n, draw_usec / 1000.0 / n, shots_written,
		RtaAudioStream.get_frames_mixed() / 48000.0, RtaAudioStream.get_requests()]
	text += "rta_godot: " + machine.info() + "\n"
	if drawer != null:
		text += "rta_godot: " + str(drawer.call("figures")) + "\n"
		if opt.mode == "scene":
			text += "rta_godot: " + str(drawer.call("get_scene_info").get("figures", "")) + "\n"
			text += "rta_godot: " + str(drawer.call("get_fill_info").get("figures", "")) + "\n"
	return text


func _finish(code: int) -> void:
	if quitting:
		return
	quitting = true
	_write_pending_shots()
	if machine != null and started and not machine_stopped:
		var text := _figures()
		machine.stop()
		print(text)
		if opt.figures != "":
			var file := FileAccess.open(opt.figures, FileAccess.WRITE)
			if file != null:
				file.store_string(text)
				file.close()
	if player != null:
		player.stop()
	if scene_view != null:
		scene_view.call("release")
	if drawer != null:
		view.set("drawer", null)
		drawer.call("release")
	get_tree().quit(code)


const VIEWS := ["overhead", "action", "chase", "shoulder", "first"]


func _unhandled_key_input(event: InputEvent) -> void:
	# V: the next camera view (not in a test window, which takes no keys)
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_V and started and opt.test == "":
		var now: int = machine.get_view().get("mode", 0)
		machine.set_option("view", VIEWS[(now + 1) % VIEWS.size()])


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_finish(0)
