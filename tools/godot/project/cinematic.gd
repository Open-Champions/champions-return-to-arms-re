extends Control
# cinematic.gd - Remastered's cut scenes and films (docs/issues/native-cutscenes.md).  Presentation only: nothing here
# reaches the simulation; what the simulation does about a skip is the library's (tools/recomp/app/cinematic.h).
#
#   films      while the game's film player has a film open (RtaMachine.get_film: its key and the picture it handed out
#              last), the enlarged copy of that picture - made on this computer from the player's own disc by
#              tools/install/films.py, <films>/<key>/<picture>.jpg - is drawn over the game's 640 x 448 picture, in its
#              place.  The film is still the game's: its player, its timing, its sound.  A film without copies, or a
#              picture not loaded in time, shows the game's own picture underneath.
#   framing    in a cut scene of the level (g_cutsceneActive) the picture is framed wide: black bars slide in (and out
#              when the scene ends) to `cine_aspect` (2.0:1 by default) - over the game's own narrower letterbox, so
#              the scene is seen at the window's full width
#   skip       "Hold START to skip": the hold of this player and of every other player of the room, read from the
#              library's block (CINE_BASE: cinematic.h), as a ring that fills in a second
#   between    true while a cut scene plays in Remastered (RTA_CINE_BETWEEN=0 off, =1 on in Classic too): main.gd then draws
#              the pictures between game frames from the two frames before (interpolated, a frame behind) instead of
#              carried on past the last (main.gd tween_back): a camera that eases to a stop does not overshoot
#
# The films folder: $RTA_FILMS, else the user data folder tools/install/films.py writes (macOS ~/Library/Application
# Support/Play-RTA/films, Windows %APPDATA%/Play-RTA/films, Linux ~/.local/share/Play-RTA/films).

const G_CUT_ACTIVE := 0x44FCD0          # g_cutsceneActive (s8)
const G_CUT_FRAME := 0x44FCE0           # g_cutFrame
const G_IN_FRONTEND := 0x41B510
const CINE_BASE := 0xE1C00              # tools/recomp/app/cinematic.h
const CINE_MAGIC := 0x314e4943
const PREFETCH := 8

var machine: Object
var main: Node
var films_on := true                    # Remastered: the enlarged films
var framing_on := true                  # Remastered: the wide framing
var cine_aspect := 2.0
var films_folder := ""
var between := false                    # main.gd: the pictures between game frames interpolated
var in_scene := false
var bars := 0.0                         # 0 none .. 1 in
var scene_time := 0.0
var letterbox_sent := false
# the film
var film_key := ""
var film_picture := -1
var film_dir := ""
var film_count := 0
var textures := {}                      # picture -> ImageTexture
var loading := {}                       # picture -> task id
var loaded := {}                        # picture -> Image (from a worker)
var loaded_lock := Mutex.new()
var shown_texture: Texture2D
var figures := {"film_pictures": 0, "film_missed": 0, "films": 0, "scenes": 0}
var last_said_key := ""
# the skip prompt
var hold_mine := 0.0
var hold_others := 0
var players := 1
var mode_on := false
var font: Font
var camera_log: FileAccess


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)
	font = ThemeDB.fallback_font
	films_folder = folder()
	if OS.get_environment("RTA_CINE_LOG") != "":
		camera_log = FileAccess.open(OS.get_environment("RTA_CINE_LOG"), FileAccess.WRITE)
		camera_log.store_line("usec,blank,scene,x,y,z,fx,fy,fz")


static func folder() -> String:
	if OS.has_environment("RTA_FILMS"):
		return OS.get_environment("RTA_FILMS")
	match OS.get_name():
		"macOS":
			return OS.get_environment("HOME").path_join("Library/Application Support/Play-RTA/films")
		"Windows":
			return OS.get_environment("APPDATA").path_join("Play-RTA/films")
		_:
			var data := OS.get_environment("XDG_DATA_HOME")
			if data == "":
				data = OS.get_environment("HOME").path_join(".local/share")
			return data.path_join("Play-RTA/films")


func _u32(address: int) -> int:
	return int(machine.call("peek_u32", address))


func _s32(address: int) -> int:
	var v := _u32(address)
	return v - 0x100000000 if v >= 0x80000000 else v


func _process(delta: float) -> void:
	var vs := get_viewport_rect().size
	if size != vs or position != Vector2.ZERO:
		position = Vector2.ZERO
		size = vs
	if machine == null or not bool(main.get("started")) or bool(machine.call("ended")):
		between = false
		shown_texture = null
		return
	_film()
	# the cut scene: the game's flag (not in the front end: the title's fly-over is a "cut scene" too)
	var cut := (_u32(G_CUT_ACTIVE) & 0xff) != 0 and (_u32(G_IN_FRONTEND) & 0xff) == 0
	if cut and not in_scene:
		figures.scenes += 1
		scene_time = 0.0
	in_scene = cut
	# (off from b7b3287 until the cause was found: the game frame's own picture was asked again in the refresh it was taken,
	# and RtaDrawer.redraw then switched off every surface of the frame but the world and the one shown - a cut scene's
	# pictures alternated between a nearly black one and the loading picture from before the scene.  Fixed there; Classic
	# keeps the plain pictures between, as it always had, unless asked)
	var ask := OS.get_environment("RTA_CINE_BETWEEN")
	between = cut and ask != "0" and (ask == "1" or String(main.get("opt").get("edition", "")) == "remastered")
	scene_time += delta
	bars = move_toward(bars, 1.0 if (cut and framing_on) else 0.0, delta / 0.35)
	# the game's own letterbox (narrower, and lower than high) is left out of the picture while ours frames it
	var drawer: Object = main.get("drawer")
	var off := cut and framing_on and drawer != null and bool(main.get("scene_view") != null)
	if off != letterbox_sent and drawer != null:
		letterbox_sent = off
		drawer.call("set_scene_option", "letterbox_off", 1.0 if off else 0.0)
	# the hold, from the library's block
	mode_on = _u32(CINE_BASE) == CINE_MAGIC and _u32(CINE_BASE + 8) == 1
	if mode_on and cut:
		players = clampi(_s32(CINE_BASE + 0x14), 1, 4)
		var need := maxi(1, _s32(CINE_BASE + 0x10))
		var slot := int(machine.call("get_controls_hud").get("slot", 0))
		if slot < 0 or slot >= players:
			slot = 0
		hold_mine = clampf(float(_s32(CINE_BASE + 0x20 + slot * 4)) / need, 0.0, 1.0)
		hold_others = 0
		for k in players:
			if k != slot and _s32(CINE_BASE + 0x20 + k * 4) > 0:
				hold_others += 1
	else:
		hold_mine = 0.0
		hold_others = 0
	queue_redraw()
	if camera_log != null:
		# test aid ($RTA_CINE_LOG=FILE): the camera of every picture (main.gd, the parent, has set it before this runs)
		var d: Object = main.get("drawer")
		if d != null and d.has_method("get_scene_camera"):
			var c: Transform3D = d.call("get_scene_camera")
			camera_log.store_line("%d,%d,%d,%.4f,%.4f,%.4f,%.5f,%.5f,%.5f" % [Time.get_ticks_usec(), int(main.get("blanks")), 1 if in_scene else 0,
				c.origin.x, c.origin.y, c.origin.z, -c.basis.z.x, -c.basis.z.y, -c.basis.z.z])


# ---- the film ----------------------------------------------------------------------------------------------------------
func _film() -> void:
	var f: Dictionary = machine.call("get_film") if films_on and machine.has_method("get_film") else {}
	var key := String(f.get("key", ""))
	if key != film_key:
		film_key = key
		textures.clear()
		loaded_lock.lock()
		loaded.clear()
		loaded_lock.unlock()
		film_dir = ""
		film_count = 0
		if key != "":
			var dir := films_folder.path_join(key)
			if FileAccess.file_exists(dir.path_join("manifest.json")):
				var m: Variant = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join("manifest.json")))
				if m is Dictionary:
					film_dir = dir
					film_count = int(m.get("pictures", 0))
					figures.films += 1
			if key != last_said_key:
				last_said_key = key
				print("rta_godot: film %s: %s" % [key, ("its enlarged copy (%d pictures) from %s" % [film_count, film_dir]) if film_dir != "" else "the game's own pictures (no enlarged copy)"])
	film_picture = int(f.get("picture", -1)) if key != "" else -1
	shown_texture = null
	if film_dir == "" or film_picture < 0:
		return
	# what the workers have read becomes textures here; then the picture now, and the next ones asked for
	loaded_lock.lock()
	for k in loaded.keys():
		textures[k] = ImageTexture.create_from_image(loaded[k])
	loaded.clear()
	loaded_lock.unlock()
	for k in textures.keys():
		if int(k) < film_picture - 2:
			textures.erase(k)
	for k in range(film_picture, mini(film_picture + PREFETCH, film_count)):
		if not textures.has(k) and not loading.has(k):
			loading[k] = WorkerThreadPool.add_task(_read.bind(k, film_dir))
	for k in loading.keys():
		if WorkerThreadPool.is_task_completed(loading[k]):
			WorkerThreadPool.wait_for_task_completion(loading[k])
			loading.erase(k)
	if textures.has(film_picture):
		shown_texture = textures[film_picture]
		figures.film_pictures += 1
	else:
		figures.film_missed += 1


func _read(k: int, dir: String) -> void:
	var image := Image.load_from_file(dir.path_join("%05d.jpg" % k))
	if image == null or dir != film_dir:
		return
	loaded_lock.lock()
	loaded[k] = image
	loaded_lock.unlock()


# ---- drawing -----------------------------------------------------------------------------------------------------------
func _picture_rect() -> Rect2:
	var aspect: float = float(machine.call("get_frame_aspect"))
	if aspect <= 0.1:
		aspect = 4.0 / 3.0
	var shape: float = size.x / max(size.y, 1.0)
	var w: float = size.x
	var h: float = size.y
	if shape > aspect:
		w = h * aspect
	else:
		h = w / aspect
	return Rect2((size - Vector2(w, h)) * 0.5, Vector2(w, h))


func _draw() -> void:
	if shown_texture != null:
		# the film is the console's whole 4:3 picture: in a wider picture it stands in the middle, as the game draws it
		var r := _picture_rect()
		var w: float = minf(r.size.x, r.size.y * 4.0 / 3.0)
		draw_texture_rect(shown_texture, Rect2(r.position.x + (r.size.x - w) * 0.5, r.position.y, w, r.size.y), false)
	if bars > 0.0:
		# over the game's picture (the window may be wider: the picture's own shape is what is framed)
		var eased := bars * bars * (3.0 - 2.0 * bars)
		var r := _picture_rect()
		var want_h: float = r.size.x / cine_aspect
		var bar: float = maxf(0.0, (r.size.y - want_h) * 0.5) * eased
		if bar > 0.5:
			draw_rect(Rect2(r.position.x, r.position.y, r.size.x, bar), Color.BLACK)
			draw_rect(Rect2(r.position.x, r.end.y - bar, r.size.x, bar), Color.BLACK)
	if mode_on and in_scene:
		_draw_skip()


func _draw_skip() -> void:
	# shown for the scene's first four seconds and whenever somebody holds
	var holding := hold_mine > 0.0 or hold_others > 0
	var a := 1.0 if holding else clampf(4.0 - scene_time, 0.0, 1.0)
	if a <= 0.0:
		return
	var s: float = clampf(size.y / 1080.0, 0.6, 2.0)
	var r := 16.0 * s
	var centre := Vector2(size.x - 48.0 * s, size.y - 40.0 * s)
	var text := "Hold START to skip"
	if players > 1:
		text += "   %d / %d holding" % [hold_others + (1 if hold_mine > 0.0 else 0), players]
	var fs := int(18 * s)
	var tw := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	draw_string(font, centre + Vector2(-r - 12.0 * s - tw, fs * 0.35), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0.92, 0.88, 0.78, 0.85 * a))
	draw_arc(centre, r, 0.0, TAU, 48, Color(1, 1, 1, 0.25 * a), 3.0 * s, true)
	if hold_mine > 0.0:
		draw_arc(centre, r, -PI * 0.5, -PI * 0.5 + TAU * hold_mine, 48, Color(0.95, 0.8, 0.45, a), 3.5 * s, true)


func info_text() -> String:
	return "cinematic: picture %s, size %s, mode %s, bars %.2f, films %s (folder %s), framing %s %.2f, scene %s, between %s, hold %.2f, others %d of %d; %s" % [
		str(_picture_rect()), str(size), "on" if mode_on else "off", bars, "on" if films_on else "off", films_folder, "on" if framing_on else "off", cine_aspect, "yes" if in_scene else "no",
		"yes" if between else "no", hold_mine, hold_others, players, str(figures)] + \
		(", game letterbox draws left out %d" % int(main.get("drawer").call("get_letterbox_left_out")) if main.get("drawer") != null and main.get("drawer").has_method("get_letterbox_left_out") else "")
