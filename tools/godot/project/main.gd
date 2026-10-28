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
#   --lib FILE          the game library (default: res://gamelib.gd - beside the extension in bin/, beside the program,
#                       the installer's per-user place; the first start of an export asks once)
#   --mode picture|draw|scene      (default picture)
#   --size WxH          the size the picture is drawn at (default: the window's own pixels)
#   --window WxH        the window's size in points
#   --aspect W:H        the shape of the 3-D view (default 4:3; "window": the window's)
#   --samples N         multisampling of the 3-D surface (0, 2, 4, 8)
#   --art-pack DIR      draw/scene modes: the pictures drawn in place of the game's textures (the native program's
#                       art_pack: a folder of PNG files from tools/play-net/upscale.py, or its parent with "replace/").
#                       Default: $RTA_ART_PACK, else user://settings.cfg [game] art_pack, else the Play-RTA folder
#                       (macOS ~/Library/Application Support/Play-RTA/textures) when it is there.  "none": without
#   --mipmaps on|off    draw/scene modes: mip maps for every texture, with anisotropic filtering in the scene (default on)
#   --script FILE       a script in the rig's language (tools/rig); its "app shot FILE.png" lines write pictures:
#                       in picture mode the library's own, in the other modes Godot's capture of what it drew
#                       ("app windowshot FILE.png": what is in the Godot window itself, the root viewport;
#                       "app effective FILE.json": what is in force now, effective_settings())
#   --godot-shots DIR   write Godot's capture for every "app shot" into DIR (by file name) instead
#   --unpaced           as fast as it goes (tests)
#   --mute              no sound is heard (the sound side still runs)
#   --control PORT      test aid: a control port on 127.0.0.1 (dev/control.gd; tools/recomp/app/playtest.py drives it)
#   --no-sound          the sound side is not driven by Godot's audio at all (rendered on the machine's clock)
#   --test TEXT         a test run: small window titled "AGENT TEST - TEXT" that takes no keyboard, silent
#   --stop-after N      quit after N vertical blanks
#   --figures FILE      write the timing figures there at the end
#   --frame-log FILE    every rendered frame one line (CSV): when its _process began, the gap to the one before, whether
#                       a game frame was taken in it, the time in _process, waiting for the machine, handing over the
#                       list; and the level now and then ("L,blank,level") - for the frame pacing figures
#   --display-rate R    60 | 120 | auto (the display's own refresh; the default): how often a picture is drawn.  The game
#                       stays at its 60 a second; the pictures between two game frames are drawn from the last two
#                       (camera, every object, the poses: see "display rate" below).  Also user://settings.cfg
#                       [display] rate
#   --speed-log N       every N vertical blanks one line: pictures a second, processor time a picture over all threads
#                       of the process (cycles do not lie, times do: read it beside the load average), late pictures
#   --view NAME         the camera view: overhead (the game's own), action, chase, shoulder, first; V cycles them
#                       (the game builds and culls each frame for the view itself: tools/recomp/app/fpview.h)
#   --no-game-hud       the game's own HUD layer is left out (for a HUD drawn by Godot)
#   --combat hardcore|off  Hardcore mode ("souls" is the earlier name) (tools/recomp/app/soulscombat.h: stamina, dodge, light / heavy attacks,
#                       blocking with stamina, poise, lock-on); offline this copy's own, in a room the host's (portal room screen)
#   --aim look|off      aiming by looking (tools/recomp/app/fpaim.h: bows and spell bolts leave along the look, heading and
#                       pitch); offline this copy's own, in a room the host's (portal room screen)
#   --light, --shadow, --pull-back F, --orbit DEG     scene mode: see scene_view.gd
#   --look K=V[,K=V...] scene mode: the look (sky, fog, sun, shadows, bloom, anti-aliasing ...): see scene_view.gd
#   --look-presets FILE scene mode: one more file of per-level look presets over the project's (scene_view.gd, presets.py)
#   --no-hud            the new HUD (res://hud) is not added
#   --no-portal         (read by the portal: straight to this scene)
#   --edition classic|remastered   the portal's choice without the portal (portal/edition.gd game_options, as
#                       handover.gd hands it over); options after it on the command line still win
#   --net2-flow ROLE:DIR   a test: a room of our own through RtaNet2 as the portal drives it (dev/net2_flow.gd); give the
#                       runtime "--opt net2-boot=1" after "--" so that the game walks to its title screen by itself
#
# Keys besides the game's: V the next camera view; F8 (or L3 + R3 held) a bug report into <data>/reports, F9 the build
# line (testerkit.gd).
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

# options on the shared command line that are other scripts' (each takes a value): the test window's
# (portal/dev/shots.gd) and the join test's (dev/join_test.gd); --portal-* and --hud-* are the portal's and the HUD's
const OTHER_SCRIPTS_OPTIONS := ["--out", "--only", "--speed", "--role", "--sync", "--service", "--join-by", "--level-to", "--party",
	"--join-data", "--join-shots"]

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
	"look": "", "hud": true, "speed_log": 0, "net2_flow": "", "art_pack": "", "mipmaps": true,
	"combat": "", "aim": "", "look_presets": "", "frame_log": "", "display_rate": "", "display_upscale": "", "no_vsync": false,
	# set by the portal's Classic / Remastered choice (portal/edition.gd, handover.gd); "" / false: as before it existed
	"edition": "", "views_locked": false, "hud_mode": "", "boss_music": "", "boss_music_er": "",
	# cut scenes and films (cinematic.gd, docs/issues/native-cutscenes.md): "" = as the edition says (Remastered on), on | off
	"cinematic": "",
	"audio_tap": "",                    # test aid: the master bus into a WAV file (dev/audio_tap.gd)
	"control": 0,                       # test aid: a control port on 127.0.0.1 (dev/control.gd)
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
var cine: Control                       # cinematic.gd: enlarged films, wide framing of cut scenes, hold to skip
var tween_back := 0.0                   # 1: the pictures between game frames interpolated a frame behind (a cut scene)
var tester: Node                        # testerkit.gd: the bug report (F8, L3 + R3), the build line (F9)
var player: AudioStreamPlayer
var audio_tap: Node                     # dev/audio_tap.gd (--audio-tap)
var control: Node                       # dev/control.gd (--control)
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
var frame_rows := PackedStringArray()   # --frame-log: one line a rendered frame
var frame_last_usec := 0
var frame_step_usec := 0                # this frame's own: waiting for the machine, handing over the list
var frame_draw_usec := 0
var frame_world := RID()
var pre_draw_usec := 0                  # --frame-log: when Godot began and ended drawing the frame before (RenderingServer signals)
var post_draw_usec := 0
var grants := 0                         # blanks let go (step); against the frame's own number: how far ahead the machine runs
# ---- the display rate (above 60: pictures between game frames) ----
var rate := "auto"                      # --display-rate / settings.cfg [display] rate: 60 | 120 | auto
# --display-upscale / settings.cfg [display] upscale / RTA_DISPLAY_UPSCALE: off | metalfx | fsr - only while pictures are
# drawn between game frames (the rate above 60): the 3-D surface drawn at 3/4 of the pixels each way and enlarged (MetalFX
# spatial on Metal, else FSR 1); at 60 every pixel is drawn (scene_view.gd _post)
var upscale := "off"
var tween_n := 1                        # refreshes a game frame; > 1: the pictures between are drawn from the last two
var refresh_s := 1.0 / 60.0             # the display's interval
var game_clock := 0.0                   # seconds since the last game frame was shown
var released: Array = []                # usec at which each blank let go and not yet shown was let go (oldest first)
var early := false                      # a frame taken while letting a blank go, shown at its own tick
var lead := 1                           # refreshes from a release to the picture its frame is shown in
var lead_lat := PackedFloat32Array()    # recent: ms from a blank's release to its finished frame
var lead_down_at := 0                   # usec: when the lead was last raised or lowered
var take_latency_usec := 0             # the game frame taken now: from its blank's release (the controller read) to now
var tween_t := 0.0                      # game frames past the last one, of the picture drawn now
var every_turn := false                 # the rate 60 on a faster display: every turn of Godot's loop (held to 60) is a game frame
var last_tick_usec := 0                 # the display rate above 60: when the last game frame was taken
var tick_ema := 16.7                    # ... the time between game frames, smoothed (ms)
var between_off := false                # ... no pictures between while the game frames themselves come late
var between_ok_since := 0
var between_hold_until := 0             # ... nor for a moment after a refresh came late (the GPU had no time to spare)
var stale_ticks := 0                   # ticks in a row whose frame was older than the lead says
var tween_figs := {"dropped": 0, "pictures": 0, "between": 0, "late": 0, "lead_sum": 0, "lat_sum": 0.0, "lat_n": 0, "waited_us": 0, "held": 0}
var window_shots: PackedStringArray = PackedStringArray()
var hud_node: Node                      # res://hud, when it was added
var art_pictures := 0                   # pictures of the art pack in use
var gpu_timer: RefCounted               # Metal's completed GPU work (Godot 4.5's Metal query timers are zero)
var gpu_world_drawn := false


func _ready() -> void:
	get_tree().set_auto_accept_quit(false)
	_parse_arguments()
	RenderingServer.frame_pre_draw.connect(_gpu_begin)
	RenderingServer.frame_post_draw.connect(_gpu_end)
	var window := get_window()
	if opt.test != "":
		window.title = "AGENT TEST - " + opt.test
		window.set_flag(Window.FLAG_NO_FOCUS, true)
		if opt.window == Vector2i.ZERO:
			opt.window = Vector2i(480, 360)
	if opt.window != Vector2i.ZERO:
		window.size = Vector2i(Vector2(opt.window) * window.content_scale_factor * DisplayServer.screen_get_scale())
	if opt.test != "":
		# out of the way: the lower right corner of the screen - or, with RTA_TEST_OFFSCREEN=1, a borderless window
		# beyond the screen's lower right edge but for its corner's two points, so nobody takes it for the game: wholly
		# off the screen (or minimised) macOS counts it as hidden and Godot stops drawing it
		var area := DisplayServer.screen_get_usable_rect()
		window.position = area.position + area.size - window.size - Vector2i(24, 24)
		if OS.get_environment("RTA_TEST_OFFSCREEN") == "1":
			window.borderless = true
			window.position = area.position + area.size - Vector2i(2, 2) * int(DisplayServer.screen_get_scale())
	if opt.unpaced:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		Engine.max_fps = 0
	if opt.no_vsync:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		Engine.max_fps = 0
	if opt.frame_log != "":
		RenderingServer.frame_pre_draw.connect(func() -> void: pre_draw_usec = Time.get_ticks_usec())
		RenderingServer.frame_post_draw.connect(func() -> void: post_draw_usec = Time.get_ticks_usec())
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
		hud_node = hud
		# The new interface in place of the game's own, unless something says otherwise: --hud MODE on the command line,
		# or the HUD's settings file (the portal's "Interface: new / original" writes it: user://hud.cfg, [hud] mode)
		if not OS.get_cmdline_user_args().has("--hud") and not FileAccess.file_exists("user://hud.cfg") and hud.has_method("command"):
			hud.call("command", ["mode", "new"])
		if String(opt.edition) != "":
			_edition_hud({"hud_mode": opt.hud_mode, "music": opt.boss_music, "music_er": opt.boss_music_er})
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
			"--art-pack": opt.art_pack = value; k += 1
			"--mipmaps": opt.mipmaps = value != "off" and value != "0"; k += 1
			"--script": opt.script = value; k += 1
			"--godot-shots": opt.godot_shots = value; k += 1
			"--unpaced": opt.unpaced = true
			"--mute": opt.mute = true
			"--audio-tap": opt.audio_tap = value; k += 1
			"--control": opt.control = value.to_int(); k += 1
			"--no-sound": opt.no_sound = true
			"--test": opt.test = value; k += 1
			"--stop-after": opt.stop_after = value.to_int(); k += 1
			"--figures": opt.figures = value; k += 1
			"--frame-log": opt.frame_log = value; k += 1
			"--no-vsync": opt.no_vsync = true             # test aid: pictures as fast as they come, the game still at 60
			"--display-rate": opt.display_rate = value; k += 1
			"--display-upscale": opt.display_upscale = value; k += 1
			"--view": opt.view = value; k += 1
			"--no-game-hud": opt.game_hud = false
			"--combat": opt.combat = value; k += 1
			"--aim": opt.aim = value; k += 1
			"--cinematic": opt.cinematic = value; k += 1
			"--light": opt.light = true
			"--shadow": opt.shadow = true
			"--pull-back": opt.pull_back = value.to_float(); k += 1
			"--orbit": opt.orbit = value.to_float(); k += 1
			"--look": opt.look = value; k += 1
			"--look-presets": opt.look_presets = value; k += 1
			"--speed-log": opt.speed_log = value.to_int(); k += 1
			"--no-hud": opt.hud = false
			"--net2-flow": opt.net2_flow = value; k += 1
			"--edition":
				_edition_options(value)
				k += 1
			"--offscreen", "--plain", "--no-portal": pass
			_:
				if not (a.begins_with("--portal") or a.begins_with("--hud") or a in OTHER_SCRIPTS_OPTIONS):
					push_warning("unknown option " + a)
				elif not value.begins_with("--"):
					k += 1
		k += 1


func _size_of(text: String) -> Vector2i:
	var parts := text.split("x")
	return Vector2i(parts[0].to_int(), parts[1].to_int()) if parts.size() == 2 else Vector2i.ZERO


func _art_pack_folder() -> String:
	# the folder of pictures drawn in place of the game's textures, as the native OpenGL program finds it (read where
	# it is; nothing of it is copied)
	var given := String(opt.art_pack)
	if given == "none" or given == "off":
		return ""
	if given != "":
		return given
	if OS.get_environment("RTA_ART_PACK") != "":
		return OS.get_environment("RTA_ART_PACK")
	var config := ConfigFile.new()
	if config.load("user://settings.cfg") == OK and String(config.get_value("game", "art_pack", "")) != "":
		return String(config.get_value("game", "art_pack", ""))
	var places: Array[String] = []
	if OS.get_name() == "macOS":
		places.append(OS.get_environment("HOME").path_join("Library/Application Support/Play-RTA/textures"))
	elif OS.get_name() == "Windows":
		places.append(OS.get_environment("APPDATA").path_join("Play-RTA/textures"))
	else:
		places.append(OS.get_environment("HOME").path_join(".local/share/Play-RTA/textures"))
	for place in places:
		if DirAccess.dir_exists_absolute(place):
			return place
	return ""


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
	# res://gamelib.gd: --lib, the one chosen once, beside the extension / the executable, the installer's per-user place
	var Lib: GDScript = load("res://gamelib.gd")
	return Lib.find(String(opt.lib))


func _ask_for_library() -> void:
	# the first start of an exported application: the game library is made by the installer from the player's disc
	var Lib: GDScript = load("res://gamelib.gd")
	message = "The game library is not on this computer yet.\n" + String(Lib.explain())
	view.set("message", message)
	printerr("rta_godot: no game library: " + ", ".join(Lib.candidates(String(opt.lib))))
	if opt.test != "" or DisplayServer.get_name() == "headless":
		get_tree().quit(2)
		return
	var dialog := FileDialog.new()
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.title = "The game library the installer built from your disc (%s)" % Lib.file_name()
	dialog.filters = PackedStringArray(["*.dylib, *.so, *.dll ; Game library"])
	dialog.file_selected.connect(func(path: String) -> void:
		Lib.save(path)
		opt.lib = path
		_start())
	add_child(dialog)
	dialog.popup_centered_ratio(0.7)


# the pixels the game is shown in: the window's, or the viewport's when the game scene is inside one (the portal's test
# window puts the portal into an off-screen viewport of the size being tested, whose shape is not the window's)
func _area() -> Vector2i:
	return Vector2i(get_viewport().get_visible_rect().size)


func _picture_size() -> Vector2i:
	if opt.size != Vector2i.ZERO:
		return opt.size
	var pixels := _area()
	var shape: float = opt.aspect if opt.aspect > 0.0 else 4.0 / 3.0
	var h := pixels.y
	var w := int(round(h * shape))
	if w > pixels.x:
		w = pixels.x
		h = int(round(w / shape))
	return Vector2i(w, max(h, 224))


# The display rate.  The game is a 60-a-second lockstep and stays one: every game frame is a blank let go and a list
# taken, as before.  At 60 every picture is a game frame.  On a display that refreshes a whole number of times a game
# frame (120 Hz: twice) and with the rate above 60, the pictures between two game frames are drawn from the last two
# (RtaDrawer.redraw: the camera and the kept models' corners carried on along their motion between them; scene_view.gd
# and er_layer.gd: the lamp, the Elden Ring figures' bones): a picture every refresh, the game frame's own at its tick.
# Carried on, not between: a game frame is shown at its tick as soon as it can be, as at 60 - nothing waits for the
# frame after it.  Each blank is let go `lead` refreshes before the tick its frame is shown at (the controller is read
# then): as few as the time a blank takes from its release to its finished frame allows, measured as it goes
# (rtag_frame_age_ms) - at 120 Hz one refresh (8.3 ms) where the frame is done in time, which lets the controller be
# read later before its picture than at 60, two (16.7 ms: what 60 had) or three where it takes longer.
func _display_rate(refresh: float) -> void:
	var asked := String(opt.display_rate)
	if asked == "":
		var cfg := ConfigFile.new()
		if cfg.load("user://settings.cfg") == OK:
			asked = str(cfg.get_value("display", "rate", ""))
	if asked == "" and OS.has_environment("RTA_DISPLAY_RATE"):
		asked = OS.get_environment("RTA_DISPLAY_RATE")
	rate = asked if asked in ["60", "120", "auto"] else "auto"
	var up := String(opt.display_upscale)
	if up == "":
		var ucfg := ConfigFile.new()
		if ucfg.load("user://settings.cfg") == OK:
			up = str(ucfg.get_value("display", "upscale", ""))
	if up == "" and OS.has_environment("RTA_DISPLAY_UPSCALE"):
		up = OS.get_environment("RTA_DISPLAY_UPSCALE")
	upscale = up if up in ["off", "metalfx", "fsr"] else "off"
	refresh_s = 1.0 / refresh
	var n := int(round(refresh / 60.0))
	tween_n = 1
	if rate != "60" and n >= 2 and abs(refresh / n - 60.0) < 0.9 and drawer != null and opt.mode == "scene" and not opt.unpaced:
		tween_n = n if rate == "auto" else mini(n, 2)
	if tween_n > 1:
		drawer.call("set_scene_option", "tween", 1.0)
	elif refresh > 61.0 and not opt.unpaced and not opt.no_vsync and OS.get_environment("RTA_RATE60_HELD") == "1":
		# (tried, and worse - kept as a test aid, RTA_RATE60_HELD=1: Godot's loop held to 60 by its own clock, without
		# the display's pacing, every turn a game frame: 43 to 51 game frames a second in valor, the turns 16 to 25 ms
		# apart.  At the rate 60 the loop runs with the display (ProMotion: as fast as the drawing allows) and a game
		# frame is taken on the turn its time has come, as before)
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		Engine.max_fps = 60
		every_turn = true
	print("rta_godot: display rate %s: %s" % [rate, ("%d pictures a game frame (%.0f a second), the ones between drawn from the last two game frames" % [tween_n, 60.0 * tween_n])
		if tween_n > 1 else "a picture a game frame (60 a second)"])


func _start() -> void:
	if not ClassDB.class_exists("RtaMachine"):
		_cannot_start("The extension is not there (bin/rta_godot...): python3 tools/godot/build.py all")
		return
	var library := _library_path()
	if library == "":
		_ask_for_library()
		return
	machine = RtaMachine.new()
	if not machine.load_library(library):
		_cannot_start("Cannot load the game library %s:\n%s\n(python3 tools/godot/build.py lib)" % [library, machine.get_error()])
		return
	if OS.has_environment("RTA_CWD"):
		machine.change_directory(OS.get_environment("RTA_CWD"))     # tools/godot/run.py: relative paths mean what they meant there
	if opt.aspect_window:
		opt.aspect = max(float(_area().x) / _area().y, 4.0 / 3.0)
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
	tester = load("res://testerkit.gd").new()
	tester.call("setup", machine, self, opt.test == "")
	add_child(tester)
	if not opt.game_hud:
		machine.set_option("game_hud", "off")
	if String(opt.combat) != "" and not machine.set_option("combat.mode", String(opt.combat)):
		print("rta_godot: this game library has no Hardcore mode (--combat %s ignored)" % opt.combat)
	if String(opt.aim) != "" and not machine.set_option("combat.aim", String(opt.aim)):
		print("rta_godot: this game library has no aiming by looking (--aim %s ignored)" % opt.aim)
	if own_picture:
		picture_texture = ImageTexture.new()
	else:
		if opt.mode == "scene":
			load("res://scene_view.gd").add_globals()       # the atmosphere's shader parameters, before a shader names them
		drawer = ClassDB.instantiate("RtaDrawer")
		drawer.call("set_shader_code", (load("res://shaders/gs_draw.gdshaderinc") as ShaderInclude).code)
		drawer.call("setup", machine, get_viewport().get_viewport_rid(), size, opt.samples)
		var pack := _art_pack_folder()
		var pictures := int(drawer.call("set_art_pack", pack, bool(opt.mipmaps)))
		art_pictures = pictures
		print("rta_godot: art pack %s (%d pictures), mip maps %s" % [pack if pack != "" else "none", pictures, "on" if opt.mipmaps else "off"])
		view.set("drawer", drawer)
		if opt.size == Vector2i.ZERO:
			# the picture is drawn at the window's own pixels, whatever the window becomes (full screen, resized):
			# never a smaller picture enlarged
			get_viewport().size_changed.connect(func() -> void:
				if drawer != null and not stored.has("sharpness"):
					drawer.call("set_output_size", _picture_size()))
		if opt.mode == "scene":
			drawer.call("set_scene_mode", true)
			scene_view = Node.new()
			scene_view.set_script(load("res://scene_view.gd"))
			scene_view.set("main", self)
			add_child(scene_view)
	if drawer != null:
		cine = Control.new()
		cine.set_script(load("res://cinematic.gd"))
		cine.set("machine", machine)
		cine.set("main", self)
		add_child(cine)
		move_child(cine, view.get_index() + 1)     # over the game's picture, under the HUD
	if not opt.no_sound:
		player = AudioStreamPlayer.new()
		player.stream = ClassDB.instantiate("RtaAudioStream")
		add_child(player)
		if opt.mute or opt.test != "":
			# a test makes no sound, whatever was asked (a tap records at full level before the muted master bus)
			player.volume_db = 0.0 if opt.audio_tap != "" else -80.0
			AudioServer.set_bus_mute(0, true)
		if opt.audio_tap != "":
			audio_tap = Node.new()
			audio_tap.set_script(load("res://dev/audio_tap.gd"))
			audio_tap.set("main", self)
			add_child(audio_tap)
			audio_tap.call("start", opt.audio_tap)
		player.play()
	var refresh := DisplayServer.screen_get_refresh_rate()
	if refresh < 20.0 or refresh > 1000.0:
		refresh = 60.0
	var per_picture: float = max(1.0, round(refresh / 60.0))
	if abs(refresh / per_picture - 60.0) < 0.9:
		period = per_picture / refresh          # locked to the display: one picture every per_picture refreshes
	print("rta_godot: display %.2f Hz; one picture every %.3f ms" % [refresh, period * 1000.0])
	_display_rate(refresh)
	started = true
	started_usec = Time.get_ticks_usec()
	if opt.control > 0:
		control = Node.new()
		control.set_script(load("res://dev/control.gd"))
		control.set("main", self)
		add_child(control)
		control.call("start", opt.control)
	_apply_cinematic()
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
		# Classic keeps the console's 4:3 whatever the setting; Remastered takes the window's shape when wide
		var shape: float = max(float(_area().x) / _area().y, 4.0 / 3.0) if bool(d.wide) and String(opt.edition) != "classic" else 4.0 / 3.0
		opt.aspect = shape
		machine.set_option("aspect", "%.5f" % shape)
	if d.has("sharpness") and drawer != null:
		var sharp: float = [0.5, 0.75, 1.0, 1.5, 2.0][clampi(int(d.sharpness), 0, 4)]
		var pixels := Vector2(_area()) * sharp
		var shape2: float = opt.aspect if opt.aspect > 0.0 else 4.0 / 3.0
		opt.size = Vector2i(int(round(pixels.y * shape2)), int(pixels.y))
		drawer.call("set_output_size", opt.size)
	if scene_view != null and d.has("look"):
		scene_view.call("set_look", String(d.look))
	if d.has("music") or d.has("effects"):
		stored["music"] = d.get("music", stored.get("music", 1.0))
		stored["effects"] = d.get("effects", stored.get("effects", 1.0))
		_volumes(float(stored.music), float(stored.effects))
	if d.has("edition"):
		_apply_edition(d.edition)


# ---- Classic / Remastered (portal/edition.gd) -----------------------------------------------------------------------
# --edition on the command line: what handover.gd puts into `opt` from the portal's choice, for a run without the portal
func _edition_options(kind: String) -> void:
	var e: Dictionary = load("res://portal/edition.gd").call("game_options", kind, "", "")
	if e.is_empty():
		push_warning("--edition: classic or remastered")
		return
	for key in ["edition", "view", "combat", "aim", "display_rate", "hud_mode"]:
		opt[key] = String(e[key])
	opt.views_locked = bool(e.views_locked)
	opt.boss_music = String(e.music)
	opt.boss_music_er = String(e.music_er)
	if String(e.look) != "":
		opt.look = String(e.look) if String(opt.look) == "" else String(e.look) + "," + String(opt.look)


# At the first start the choice arrives in `opt` (handover.gd); a change while the game runs comes here.  Nothing of
# the game's own code is new: the options are the existing ones (combat.mode, combat.aim, the look keys, the HUD's
# mode and its music director, the display rate, the views).
func _edition_hud(e: Dictionary) -> void:
	if hud_node == null or not hud_node.has_method("command"):
		return
	if String(e.get("hud_mode", "")) != "":
		hud_node.call("command", ["mode", String(e.hud_mode)])
	if String(e.get("music", "")) in ["on", "off"]:
		hud_node.call("command", ["music", String(e.music)])
	var director: Node = hud_node.get_node_or_null("Music")
	if director != null and "er_tracks" in director:
		director.set("er_tracks", String(e.get("music_er", "")) == "on")
		director.call("scan")


# Cut scenes and films (cinematic.gd; the library's hold to skip, tools/recomp/app/cinematic.h): Remastered's, or as
# --cinematic on | off says.  The skip is a room option: in a room the library holds what the room agreed on.
func _apply_cinematic() -> void:
	var on := String(opt.cinematic) == "on" or (String(opt.cinematic) == "" and String(opt.edition) == "remastered")
	if machine != null and started and machine.has("cinematic"):
		machine.set_option("cinematic.skip", "hold" if on else "tap")
	if cine != null:
		cine.set("films_on", on)
		cine.set("framing_on", on)


func _apply_edition(e: Dictionary) -> void:
	opt.edition = String(e.get("edition", ""))
	opt.views_locked = bool(e.get("views_locked", false))
	opt.hud_mode = String(e.get("hud_mode", ""))
	opt.boss_music = String(e.get("music", ""))
	opt.boss_music_er = String(e.get("music_er", ""))
	_edition_hud(e)
	if machine == null or not started:
		return
	machine.set_option("combat.mode", String(e.get("combat", "off")))
	machine.set_option("combat.aim", String(e.get("aim", "off")))
	if String(e.get("view", "")) != "":
		machine.set_option("view", String(e.view))
	if scene_view != null:
		if opt.edition == "classic":
			scene_view.call("set_look", String(load("res://portal/edition.gd").CLASSIC_LOOK))
		else:
			scene_view.call("clear_look", PackedStringArray(load("res://portal/edition.gd").CLASSIC_KEYS))
			if String(e.get("look", "")) != "":
				scene_view.call("set_look", String(e.look))
	if String(e.get("display_rate", "")) != "" and String(e.display_rate) != rate:
		opt.display_rate = String(e.display_rate)
		var refresh := DisplayServer.screen_get_refresh_rate()
		if refresh < 20.0 or refresh > 1000.0:
			refresh = 60.0
		var before := tween_n
		_display_rate(refresh)
		if tween_n == 1 and before > 1 and drawer != null:
			drawer.call("set_scene_option", "tween", 0.0)
		clock = 0.0
		game_clock = 0.0
	_apply_cinematic()
	if stored.has("wide"):
		apply_settings({"wide": stored.wide})       # the picture shape follows the edition (Classic 4:3)
	print("rta_godot: the game is now %s" % opt.edition)


# What is in force now, read back from where each thing lives (the library's own figures, the look, the HUD, the
# pacing) - for the portal's tests and a bug report.
func effective_settings() -> Dictionary:
	var d := {"edition": String(opt.edition), "mode": String(opt.mode), "paced": not bool(opt.unpaced), "display_rate": rate,
		"pictures_per_game_frame": tween_n, "views_locked": bool(opt.views_locked), "game_hud_option": bool(opt.game_hud),
		"art_pack": _art_pack_folder() != "", "art_pictures": art_pictures}
	if machine != null and started:
		var info := String(machine.info())
		for key in ["souls_want", "souls_on", "aim_want", "aim_on", "cine_want", "cine_on"]:
			var at := info.find(" " + key + "=")
			d[key] = info.substr(at + key.length() + 2).get_slice(" ", 0).to_int() if at >= 0 else -1
		d["copy"] = info.substr(info.find(" copy=") + 6).get_slice(" ", 0) if info.find(" copy=") >= 0 else ""
		d["view"] = VIEWS[clampi(int(machine.get_view().get("mode", 0)), 0, VIEWS.size() - 1)]
		d["aspect"] = snappedf(float(machine.get_frame_aspect()), 0.001)     # the 3-D view's shape (4:3 = 1.333)
		d["aspect_window"] = bool(opt.aspect_window)
	if hud_node != null:
		var hs: Dictionary = hud_node.get("setting")
		d["hud_mode"] = String(hs.get("mode", ""))
		d["boss_music"] = bool(hs.get("music", false))
		var director: Node = hud_node.get_node_or_null("Music")
		if director != null:
			d["boss_tracks"] = (director.get("tracks") as PackedStringArray).size()
			d["er_tracks"] = bool(director.get("er_tracks")) if "er_tracks" in director else false
	if scene_view != null:
		var look: Dictionary = scene_view.get("look")
		var shown := {}
		for key in load("res://portal/edition.gd").CLASSIC_KEYS:      # every look key Classic turns off
			shown[key] = look.get(key)
		d["look"] = shown
		d["look_preset_applied"] = String(scene_view.get("preset_applied"))
	return d


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
	if input_held or (tester != null and tester.call("is_open")):    # (the report box has the keyboard and the controller)
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
	if control != null and control.get("held"):
		var held_sticks: Array = control.get("sticks")
		buttons = int(control.get("buttons"))
		lx = held_sticks[0]
		ly = held_sticks[1]
		rx = held_sticks[2]
		ry = held_sticks[3]
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
	elif w.size() >= 1 and (w[0] == "light" or w[0] == "camera" or w[0] == "scene" or w[0] == "look" or w[0] == "card" or w[0] == "er" or w[0] == "remaster") and scene_view != null:
		scene_view.call("command", w)
	elif w.size() >= 1 and w[0] == "cinematic" and cine != null:
		print("[blank %d] rta_godot: %s" % [blanks, cine.call("info_text")])
	elif w.size() >= 1 and w[0] == "cinematic":
		pass
	elif w.size() >= 2 and w[0] == "effective":
		# test aid: what is in force now (effective_settings) as JSON into a file
		var f := FileAccess.open(text.substr(text.find(w[1])), FileAccess.WRITE)
		if f != null:
			var d := effective_settings()
			d["blank"] = blanks
			f.store_string(JSON.stringify(d, "  "))
	elif w.size() >= 2 and w[0] == "audio" and audio_tap != null:
		audio_tap.call("command", w)        # test aid: app audio mark NAME | engage on|off|auto
	elif w.size() >= 2 and w[0] == "mark":
		frame_rows.append("M,%d,%s" % [blanks, " ".join(w.slice(1))])   # test aid: a named part of the route in the frame log
	elif w.size() >= 2 and w[0] == "hold":
		hold_input(w[1] == "on")            # test aid: as the portal does while it is in front
	elif w.size() >= 3 and w[0] == "setting":
		apply_settings({w[1]: (w[2] == "true" if w[2] in ["true", "false"] else (w[2].to_int() if w[2].is_valid_int() else w[2]))})
	elif w.size() >= 1 and w[0] == "hud":
		pass                                # the HUD's own lines (res://hud/hud.gd reads them)
	elif w.size() >= 2 and w[0] == "drawlog" and drawer != null:
		drawer.call("log_draws", w[1].to_int())   # debugging: the next lists' draws with their state (RtaDrawer.log_draws)
	elif w.size() >= 1 and w[0] == "report" and tester != null:
		tester.call("command", w, text)     # the bug report (testerkit.gd)
	else:
		push_warning("app command not known: " + text)


func frame_mark(text: String) -> void:
	# test aid: a named moment in the frame log (dev/control.gd marks what its commands cost)
	if opt.frame_log != "":
		frame_rows.append("M,%d,%s" % [blanks, text])


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
	gpu_world_drawn = true
	blanks += 1
	if int(opt.speed_log) > 0:
		_speed_log()
	for text in machine.get_host_commands():
		_host_command(text)
	if drawer != null:
		var t0 := Time.get_ticks_usec()
		if scene_view != null:
			scene_view.call("before_frame")
		var t1 := Time.get_ticks_usec()
		drawer.call("submit")
		var t2 := Time.get_ticks_usec()
		if scene_view != null:
			scene_view.call("frame")
		if OS.get_environment("RTA_LOG_PARTS") == "1":
			# test aid: where a game frame's hand-over goes (before_frame, the drawer, scene_view.frame), every 300 blanks
			parts_usec[0] += t1 - t0; parts_usec[1] += t2 - t1; parts_usec[2] += Time.get_ticks_usec() - t2; parts_usec[3] += 1
			if parts_usec[3] >= 300:
				print("[blank %d] rta_godot: hand-over a game frame: before %.2f ms, drawer %.2f ms, scene %.2f ms" % [blanks,
					parts_usec[0] / 300000.0, parts_usec[1] / 300000.0, parts_usec[2] / 300000.0])
				parts_usec = [0, 0, 0, 0]
		draw_usec += Time.get_ticks_usec() - t0
		frame_draw_usec += Time.get_ticks_usec() - t0
		for path in machine.get_shots():
			pending_shots.append(path)
	if control != null:
		control.call("after_frame")         # test aid (dev/control.gd): the frame just taken, pictured exactly when asked


func _process(delta: float) -> void:
	if not started or quitting:
		return
	gpu_world_drawn = false
	var t0 := Time.get_ticks_usec()
	_write_pending_shots()
	if control != null:
		control.call("poll")
	var got_any := false
	if opt.unpaced:
		# as fast as it goes: with Godot drawing, one list per rendered frame (every one is drawn);
		# with the library's own picture, as many blanks as fit into 12 ms
		while true:
			_read_pad()
			var s0 := Time.get_ticks_usec()
			var got := machine.step(-1)
			step_usec += Time.get_ticks_usec() - s0
			frame_step_usec += Time.get_ticks_usec() - s0
			if got != 1:
				break
			_take_frame()
			got_any = true
			if drawer != null or Time.get_ticks_usec() - t0 > 12000 or (opt.stop_after > 0 and blanks >= opt.stop_after):
				break
	elif tween_n > 1:
		got_any = _paced_between(delta)
	else:
		clock += delta
		if every_turn or clock >= period - 0.0005:
			clock -= period
			if clock > period or every_turn:
				clock = 0.0                 # stood still: no burst afterwards
			_read_pad()
			var s0 := Time.get_ticks_usec()
			grants += 1
			released.append(s0)
			var got := machine.step(8)      # the frame let go now is usually there within a few milliseconds
			step_usec += Time.get_ticks_usec() - s0
			frame_step_usec += Time.get_ticks_usec() - s0
			while got == 1:
				if not released.is_empty():
					released.pop_front()
				take_latency_usec = int(machine.frame_since_release_ms() * 1000.0)
				_take_frame()
				if drawer != null:
					# more than one finished frame waiting in the library's queue (it holds the first frame of the run,
					# made before any release, and keeps up to three): for half a second of frames in a row, the newer
					# one is taken too and drawn over the older in this same turn - the controller is not read later than
					# it must be (a list is never skipped: it names the textures the ones before it made)
					stale_ticks = stale_ticks + 1 if take_latency_usec > int(period * 1.8 * 1000000.0) else 0
					if stale_ticks >= 30 and machine.poll(0) == 1:
						stale_ticks = 0
						tween_figs.dropped += 1
						if not released.is_empty():
							released.pop_front()
						take_latency_usec = int(machine.frame_since_release_ms() * 1000.0)
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
	if opt.frame_log != "":
		_frame_row(t0, got_any, tween_n > 1)
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


# One refresh with the display rate above 60 (see _display_rate).  Returns whether a game frame was taken.
func _paced_between(delta: float) -> bool:
	var period_s := refresh_s * tween_n
	game_clock += delta
	if game_clock > 4.0 * period_s:
		game_clock = period_s               # stood still (a load, the window hidden): no burst afterwards
	var due := game_clock >= period_s - refresh_s * 0.5
	# let go the blanks whose frames are to be shown within `lead` refreshes from now (their ticks: the next is at
	# period - clock from now, then one every period)
	var to_next := period_s - game_clock
	var want := 0
	var ahead := to_next
	while ahead <= lead * refresh_s + refresh_s * 0.5 and want < 3:
		want += 1
		ahead += period_s
	if due and want < 1:
		want = 1
	var pad_read := false
	while released.size() < want:
		if not pad_read:
			_read_pad()
			pad_read = true
		released.append(Time.get_ticks_usec())
		grants += 1
		if machine.release() == -2 and not early:
			# a library without rtag_release: step() lets go and takes a frame already finished (shown at its tick)
			if machine.step(0) == 1:
				early = true
				_note_latency()
	var took := false
	if due:
		var got := 1 if early else 0
		if not early:
			var s0 := Time.get_ticks_usec()
			# a frame not there yet: a little time to come (a refresh's third), then a picture drawn on from the last
			got = machine.poll(int(refresh_s * 1000.0 / 3.0))
			var waited := Time.get_ticks_usec() - s0
			step_usec += waited
			frame_step_usec += waited
			tween_figs.waited_us += waited
			if got == 1:
				_note_latency()
		if got == 1:
			early = false
			if not released.is_empty():
				released.pop_front()
			take_latency_usec = int(machine.frame_since_release_ms() * 1000.0)
			# a frame older than the lead says (one more waits in the library's queue - it holds the first frame of the
			# run, made before any release): for half a second of ticks in a row - the newer one is shown instead, once
			if take_latency_usec > int((lead * refresh_s + period_s * 0.75) * 1000000.0):
				stale_ticks += 1
			else:
				stale_ticks = 0
			# the remainder is kept, also when the frame was taken up to half a refresh before its tick: dropping it
			# (the clock put back to 0) gained that part of a refresh at every game frame - with refreshes of 9-12 ms
			# (a heavy scene at 120 Hz) the game ran at 63-66 frames a second instead of 60 (fps-verdict.md)
			game_clock = maxf(-refresh_s * 0.5, game_clock - period_s)
			if game_clock > period_s:
				game_clock = 0.0
			tween_t = 0.0
			_take_frame()
			# in a cut scene the pictures are drawn a frame behind, between the two frames before (cinematic.gd): the
			# game frame's own picture is its predecessor's place, the ones after it the way from there to it
			tween_back = 1.0 if cine != null and bool(cine.get("between")) else 0.0
			if tween_back > 0.0 and drawer != null:
				drawer.call("redraw", -1.0)
				if scene_view != null:
					scene_view.call("tween", -1.0)
			if stale_ticks >= 30 and machine.poll(0) == 1:
				# (every list is handed to the drawer - a list names the textures the ones before it made - the stale
				# one's picture is simply drawn over by the newer one's in this same refresh)
				stale_ticks = 0
				tween_figs.dropped += 1
				if not released.is_empty():
					released.pop_front()
				take_latency_usec = int(machine.frame_since_release_ms() * 1000.0)
				_take_frame()
			took = true
		else:
			tween_figs.late += 1
			_raise_lead()
	if took:
		var now_t := Time.get_ticks_usec()
		if last_tick_usec != 0:
			tick_ema = lerpf(tick_ema, (now_t - last_tick_usec) / 1000.0, 0.05)
		last_tick_usec = now_t
		# the game frames themselves late (fire1's crowd: the drawing of a game frame alone takes longer than one):
		# no pictures between, they would only take the game frames' time; back when they keep time for two seconds
		if tick_ema > period_s * 1000.0 * 1.12:
			between_off = true
			between_ok_since = now_t
		elif tick_ema > period_s * 1000.0 * 1.04:
			between_ok_since = now_t
		elif between_off and now_t - between_ok_since > 2000000:
			between_off = false
	# a refresh that came late (more than half a refresh over): the GPU is not keeping up with the pictures already asked
	# for - a picture between would take its time from the next game frame; none for a quarter of a second
	var now_b := Time.get_ticks_usec()
	if delta > refresh_s * 1.5:
		between_hold_until = now_b + 250000
	var gpu_between := scene_view == null or bool(scene_view.call("gpu_between_allowed"))
	if not took and blanks > 0 and not between_off and now_b >= between_hold_until and gpu_between:
		tween_t = clampf(game_clock / period_s, 0.0, 1.0)
		drawer.call("redraw", tween_t - tween_back)
		gpu_world_drawn = true
		if scene_view != null:
			scene_view.call("tween", tween_t - tween_back)
		tween_figs.between += 1
	elif not took and blanks > 0 and not between_off:
		tween_figs.held += 1
	tween_figs.pictures += 1
	tween_figs.lead_sum += lead
	_lower_lead()
	return took


func _gpu_begin() -> void:
	# Classic never creates the timer or changes its drawing schedule.
	var enabled := String(opt.edition) == "remastered" and scene_view != null and bool(scene_view.call("gpu_quality_enabled"))
	if enabled and gpu_timer == null and ClassDB.class_exists("RtaGpuTimer"):
		gpu_timer = ClassDB.instantiate("RtaGpuTimer")
	if gpu_timer != null:
		gpu_timer.call("begin_frame", enabled and gpu_world_drawn and not quitting)


func _gpu_end() -> void:
	if gpu_timer != null:
		gpu_timer.call("end_frame")


func _note_latency() -> void:
	# the frame just taken: from the release of the blank it shows (its controller read) to when the decoder had it done
	var age: float = machine.frame_age_ms()
	var since: float = machine.frame_since_release_ms()
	if age < 0.0 or since < 0.0:
		return
	var lat: float = since - age
	if lat < 0.0 or lat > 200.0:
		return
	lead_lat.append(lat)
	if lead_lat.size() > 90:
		lead_lat.remove_at(0)
	tween_figs.lat_sum += lat
	tween_figs.lat_n += 1


func _needed_lead() -> int:
	if lead_lat.size() < 10:
		return lead
	var s := lead_lat.duplicate()
	s.sort()
	var p95: float = s[int(s.size() * 0.95)]
	return clampi(int(ceil((p95 + 1.5) / (refresh_s * 1000.0))), 1, 3 * tween_n)


func _raise_lead() -> void:
	# a frame was not there at its tick: one refresh more at once
	if lead < 3 * tween_n:
		lead += 1
		lead_down_at = Time.get_ticks_usec()


func _lower_lead() -> void:
	# up at once when the measured times ask for it, down only after two seconds of them fitting
	var need := _needed_lead()
	var now := Time.get_ticks_usec()
	if need > lead:
		lead = need
		lead_down_at = now
	elif need < lead and now - lead_down_at > 2000000:
		lead -= 1
		lead_down_at = now


var pipelines_said := [0, 0, 0, 0, 0]
var parts_usec := [0, 0, 0, 0]
func _frame_row(t0: int, took: bool, shown_new := false) -> void:
	var now := Time.get_ticks_usec()
	if OS.get_environment("RTA_LOG_PIPELINES") == "1":
		# test aid: Godot's pipeline compilations (canvas, mesh, surface, draw, specialisation) where they happen
		var got := []
		for k in 5:
			got.append(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_PIPELINE_COMPILATIONS_CANVAS + k))
		if got != pipelines_said:
			print("[blank %d] rta_godot: pipelines compiled %s (%d us in this _process)" % [blanks, str(got), now - t0])
			pipelines_said = got
	var gpu := 0.0
	var cpu := 0.0
	if drawer != null and opt.mode == "scene" and OS.get_environment("RTA_MEASURE_VIEWPORTS") == "1":
		var world: RID = drawer.call("get_world_viewport")
		if world.is_valid():
			if world != frame_world:
				frame_world = world
				RenderingServer.viewport_set_measure_render_time(world, true)
				RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
			gpu = RenderingServer.viewport_get_measured_render_time_gpu(world)
			cpu = RenderingServer.viewport_get_measured_render_time_cpu(world)
	if (blanks & 63) == 0 and took:
		# with the library's own figures so far (blanks, game side and decoder ms a blank): per part of the route by differences
		var lib := {}
		for word in machine.info().split(" "):
			var kv := word.split("=")
			if kv.size() == 2 and kv[0] in ["blanks", "game_ms", "decode_wall_ms", "decode_cpu_ms", "tap_ms", "kick_ms", "take_ms", "skel_ms", "later_ms", "copy_ms", "worker_ms", "lag_ms"]:
				lib[kv[0]] = kv[1]
		var pairs := PackedStringArray()
		for key in lib:
			pairs.append("%s=%s" % [key, lib[key]])
		frame_rows.append("L,%d,%s,%d,%s,%s,%s,%s" % [blanks, machine.peek_string(0x41B721, 16), machine.peek_u32(0x44FDCC),
			lib.get("blanks", "0"), lib.get("game_ms", "0"), lib.get("decode_wall_ms", "0"), ";".join(pairs)])
	frame_rows.append("%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d" % [t0, t0 - frame_last_usec if frame_last_usec != 0 else 0, 1 if took else 0,
		now - t0, frame_step_usec, frame_draw_usec, blanks, 1 if (took or shown_new) else 0, int(gpu * 1000.0), int(cpu * 1000.0),
		int(RenderingServer.get_frame_setup_time_cpu() * 1000.0), grants - machine.get_frame_number() if took else -999, lead, int(tween_t * 1000.0),
		post_draw_usec - pre_draw_usec, t0 - post_draw_usec, int(Performance.get_monitor(Performance.TIME_PROCESS) * 1000000.0),
		take_latency_usec if took else 0])
	frame_last_usec = t0
	frame_step_usec = 0
	frame_draw_usec = 0


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
	if tween_n > 1:
		var pics: float = max(1, int(tween_figs.pictures))
		text += "rta_godot: display rate %s: %d pictures, %d of them between game frames (%d not drawn: a refresh had come late), %d ticks whose frame was late; lead %.2f refreshes on average; a blank %.2f ms from its release to its frame (mean); %.2f ms a picture waiting for a frame; %d game frames drawn over in the refresh they were taken (the queue's spare one, to catch up)\n" % [
			rate, int(tween_figs.pictures), int(tween_figs.between), int(tween_figs.held), int(tween_figs.late), float(tween_figs.lead_sum) / pics,
			float(tween_figs.lat_sum) / max(1, int(tween_figs.lat_n)), float(tween_figs.waited_us) / 1000.0 / pics, int(tween_figs.dropped)]
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
		if opt.frame_log != "":
			var log := FileAccess.open(opt.frame_log, FileAccess.WRITE)
			if log != null:
				log.store_string("usec,gap_usec,game_frame,process_usec,wait_usec,submit_usec,blank,new_picture,world_gpu_usec,world_cpu_usec,setup_cpu_usec,ahead,lead,tween_milli,draw_usec,after_draw_usec,all_process_usec,release_to_take_usec\n" + "\n".join(frame_rows) + "\n")
				log.close()
	if player != null:
		player.stop()
	if audio_tap != null:
		audio_tap.call("finish")
	if scene_view != null:
		scene_view.call("release")
	if drawer != null:
		view.set("drawer", null)
		drawer.call("release")
	get_tree().quit(code)


const VIEWS := ["overhead", "action", "chase", "shoulder", "first"]


func report_lines() -> String:
	# what a bug report says about this host (testerkit.gd): the mode, the window, the portal's settings
	var lines := "godot = %s\nmode = %s\nwindow = %dx%d\nportal = %s\n" % [Engine.get_version_info().string, opt.mode,
		get_window().size.x, get_window().size.y, "yes" if portal != null else "no"]
	for key in stored:
		if key in ["view", "wide", "sharpness", "music", "effects"]:
			lines += "portal.%s = %s\n" % [key, str(stored[key])]
	return lines


func _unhandled_key_input(event: InputEvent) -> void:
	# V: the next camera view (not in a test window, which takes no keys)
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_V and started and opt.test == "" and not bool(opt.views_locked):
		var now: int = machine.get_view().get("mode", 0)
		machine.set_option("view", VIEWS[(now + 1) % VIEWS.size()])


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_finish(0)
