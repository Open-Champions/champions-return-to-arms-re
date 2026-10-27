extends CanvasLayer
# hud.gd - the new HUD: a clean interface drawn by Godot from the game's own state.
#
# Hook: one line in main.gd's _ready, after the view is added:
#     add_child(load("res://hud/hud.tscn").instantiate())
# Nothing else of the host is touched.  This node finds the host (its parent) and the
# machine there, reads the game's state once per displayed frame through RtaGameState
# (extension, tools/godot/extension/src/rta_gamestate.*; the reader itself is
# tools/recomp/app/gamestate.*), and its children draw:
#     World    health bars above heads, name tags of the other players, floating numbers
#     Threat   who is attacking from outside the picture (or from behind, in a close view)
#     Status   the player's frame and the party's
#     Compass  the radar (overhead) or the compass strip (close views), with the objective's direction
#     Top      the target's and the boss's bar, the game's own message, the level's title, online notices, chat
#     Bottom   quick slots, potions, the weapon, the interaction prompt, gold and the feed of what was gained
#     Pause    the pause bands
#
# Settings: user://hud.cfg ([hud] mode, view, scale, numbers, radar), the command line after "--"
# (--hud new|original|both, --hud-view auto|overhead|third|first, --hud-scale F, --hud-fake-party N) and, in a
# script, "app hud ..." lines (the same words; plus "app hud cost" and "app hud say").
#
#   mode      new: this HUD, and the game's own HUD layer asked off (needs the switch of the draw-list side:
#             machine.set_option("game_hud", "off") - with a library that lacks it both are visible);  original: this HUD hidden;
#             both: for comparing
#   view      which of the three layouts: auto takes it from the camera's view mode (tools/recomp/app/fpview.h,
#             handed in by the host as machine.get_view()); until the library has that, the setting decides
#
# No game art, no game text: every name on screen is read from the game's memory while it runs.

const Style := preload("res://hud/style.gd")

const PH_FRONTEND := 1
const PH_LEVEL := 2
const PH_LOADING := 4
const PH_PAUSED := 8
const PH_PAUSE_MENU := 16
const PH_MENU := 32
const PH_CUTSCENE := 64
const PH_DIALOGUE := 128
const PH_GATE_MENU := 256
const PH_FADE := 512
const PH_DEAD := 1024
const PH_CAMERA_HELD := 2048

const LAYOUT_OVERHEAD := 0
const LAYOUT_THIRD := 1
const LAYOUT_FIRST := 2

# creature array (RtaGameState.get_creatures): floats per creature
const C_STRIDE := 14
const C_UID := 0
const C_FLAGS := 1
const C_HP := 2
const C_MAX := 3
const C_SX := 4
const C_SY := 5
const C_SZ := 6
const C_WX := 7
const C_WY := 8
const C_WZ := 9
const C_HEIGHT := 10
const C_FACING := 11
const C_TARGET_SLOT := 12
const C_BOSS := 13
const CF_HOSTILE := 1
const CF_BOSS := 2
const CF_MINIBOSS := 4
const CF_DEAD := 8
const CF_TARGETED := 16
const CF_AGGRO := 32
const CF_ATTACKING := 64
const CF_FRIENDLY := 128
const CF_NAMED := 256
const CF_INERT := 512
const CF_ONSCREEN := 1024

var setting := {"mode": "both", "view": "auto", "scale": 1.0, "numbers": true, "radar": true, "fake_party": 0, "music": true, "music_volume": 0.8, "theme": ""}

var host: Node                          # main.gd
var machine: Object                     # RtaMachine
var gs: Object                          # RtaGameState
var souls_panel: Control                # hud/souls.gd (its text over the stamina bar: status.gd keeps its own line above it)
var pillars: Control                    # black sides beside the game's own 4:3 full-screen 2-D screens in a wide picture
var ok := false                         # a state was read this frame
var frame := {}                         # RtaGameState.get_frame()
const MAX_PLAYERS := 8                  # the game's own four, or eight in a room of five to eight (RTA_GS_PLAYERS)
var players: Array = []                 # per slot: RtaGameState.get_player(slot), or test data marked "fake"
var me := {}                            # the local player
var creatures := PackedFloat32Array()
var events: Array = []
var phase := 0
var layout := LAYOUT_OVERHEAD
var now := 0.0                          # the HUD's clock: seconds of the machine's own time (vertical blanks / 59.94)
var dt := 0.0
var s := 1.0                            # design pixels (of a picture 1080 high) -> window pixels
var picture := Rect2()                  # where the game's picture is in the window
var area := Rect2()                     # where the HUD lays itself out: the picture less a safe margin, not wider than 21:9 of content
var show := 0.0                         # 0..1: the playing HUD as a whole (fades when a game screen is up)
var pause_show := 0.0
var cost_usec := 0.0                    # of this script and its children per displayed frame (processing; drawing is measured apart)
var cost_frames := 0
var cost_total := 0.0
var cost_most := 0.0
var reader_total := 0.0
var draw_usec := 0.0                    # the children's _draw calls of this frame
var draw_total := 0.0
var last_blank := -1
var game_hud_asked := 0                 # 0 not yet, 1 asked off, 2 asked on
var slots_top := 0.0                    # window y of the top of the slot row (bottom.gd): what sits at the picture's foot stays above it
var own_text := true                    # this HUD draws the one-line message and the interaction prompt itself (false: the game's own are in the picture)
var said := {}
var portal: Node                        # the portal (tools/godot/project/portal), when this game was started from it
var notices: Array = []                 # invitations and requests to draw in the game: {id, kind, who, title, text, accept_text, born, seconds}
var notice_hold := 0.0                  # seconds both sticks have been held down (the controller's answer)
var controls := {}                      # what the controls side knows (fpcontrols::hud(), through machine.get_controls_hud()), empty without
var shots: PackedStringArray = PackedStringArray()
var phase_blanks := {}
var timed: Array = []                   # [level, tick, words] still to run (--hud-at)

@onready var root: Control = $Root
@onready var pieces: Array = [$Root/World, $Root/Threat, $Root/Status, $Root/Compass, $Root/Top, $Root/Bottom, $Root/Pause]
@onready var music: Node = $Music
@onready var notice_piece: Control = $Root/Notice


func _ready() -> void:
	host = get_parent()
	process_priority = 10               # after the host has taken its frame
	_load_settings()
	if str(setting.theme) != "":
		Style.set_skin(str(setting.theme))
	elif ResourceLoader.exists("res://gameart/gameart.gd") and load("res://gameart/gameart.gd").wanted():
		Style.set_skin("res://gameart/hud_skin.gd")       # the game's own art from the player's disc (gameart.gd)
	_parse_arguments()
	root.modulate.a = 0.0
	for piece in pieces:
		piece.set("hud", self)
		piece.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	music.set("hud", self)
	notice_piece.set("hud", self)
	notice_piece.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var souls: Control = load("res://hud/souls.gd").new()   # the souls-style combat mode's stamina bar and lock-on (hud/souls.gd)
	souls.set("hud", self)
	root.add_child(souls)
	souls_panel = souls
	# The game draws its mission map, its gate menu and its loading picture for the console's 4:3 screen: in a wide
	# picture what lies beside them is whatever was left there (the world kept from before, a piece of the map's
	# background) - black there, as the films and the 4:3 picture itself have it
	pillars = Control.new()
	pillars.name = "Pillars"
	pillars.set_anchors_preset(Control.PRESET_FULL_RECT)
	pillars.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(pillars)
	move_child(pillars, 0)
	pillars.draw.connect(_draw_pillars)
	_find_portal.call_deferred()
	if ClassDB.class_exists("RtaGameState"):
		gs = ClassDB.instantiate("RtaGameState")
	else:
		push_warning("hud: the extension has no RtaGameState (register it: GDREGISTER_CLASS(RtaGameState)); the new HUD is off")
		visible = false


func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load("user://hud.cfg") != OK:
		return
	for key in setting:
		if config.has_section_key("hud", key):
			setting[key] = config.get_value("hud", key)


func save_settings() -> void:
	var config := ConfigFile.new()
	for key in setting:
		if key != "fake_party":
			config.set_value("hud", key, setting[key])
	config.save("user://hud.cfg")


func _parse_arguments() -> void:
	var args := OS.get_cmdline_user_args()
	var k := 0
	while k < args.size():
		var value := args[k + 1] if k + 1 < args.size() else ""
		match args[k]:
			"--":
				return
			"--hud": command(["mode", value]); k += 1
			"--hud-view": command(["view", value]); k += 1
			"--hud-scale": command(["scale", value]); k += 1
			"--hud-fake-party": command(["fake-party", value]); k += 1
			"--hud-theme": command(["theme", value]); k += 1
			"--hud-at":
				# commands at chosen simulation ticks of a level, "LEVEL@TICK:words;LEVEL@TICK:words": for test runs that are
				# not paced (there the host takes several blanks per picture and a script's "app hud" line can pass unseen).
				# Instead of a tick: pause, menu, dialogue, cutscene, gate - once that screen has been up for 45 blanks
				# (the simulation's tick stands still in a paused game)
				for part in value.split(";", false):
					var head := part.get_slice(":", 0).strip_edges()
					var when := head.get_slice("@", 1)
					timed.append([head.get_slice("@", 0), when.to_int() if when.is_valid_int() else when, Array(part.substr(part.find(":") + 1).split(" ", false))])
				k += 1
		k += 1


# "app hud WORDS" of a script, the command line, or a settings screen
func command(w: Array) -> void:
	if w.is_empty():
		return
	var value: String = str(w[1]) if w.size() > 1 else ""
	match str(w[0]):
		"mode":
			if value in ["new", "original", "both"]:
				setting.mode = value
				game_hud_asked = 0
		"view":
			if value in ["auto", "overhead", "third", "first"]:
				setting.view = value
		"scale":
			setting.scale = clampf(value.to_float(), 0.5, 2.0)
		"theme":
			# a skin script (style.gd says what it may have); "default" or nothing: the HUD's own drawing
			var path := "" if value == "default" else value
			if Style.set_skin(path):
				setting.theme = path
				for piece in pieces:
					piece.set("last_signature", "")
					piece.queue_redraw()
			else:
				push_warning("hud: no skin at " + value)
		"numbers":
			setting.numbers = value != "off"
		"radar":
			setting.radar = value != "off"
		"fake-party":
			setting.fake_party = clampi(value.to_int() if value.is_valid_int() else (0 if value == "off" else 1), 0, MAX_PLAYERS - 1)
		"music":
			if value in ["on", "off"]:
				setting.music = value == "on"
			elif value == "say":
				print("hud music: " + music.call("figures"))
			elif value == "scan":
				music.call("scan")
			elif value == "tap":
				music.call("tap")
			elif value == "game" and w.size() > 2 and machine != null and machine.has_method("set_option"):
				# test aid: the library's own control, directly ("app hud music game 0.25")
				print("hud music: set_option music_volume %s -> %s" % [str(w[2]), str(machine.call("set_option", "music_volume", str(w[2])))])
		"music-volume":
			setting.music_volume = clampf(value.to_float(), 0.0, 1.0)
		"delay":
			# test aid: 1 (default) the bars above heads belong to the picture shown, 0 to the memory as it is now (one tick ahead)
			if gs != null:
				gs.call("set_screen_delay", value.to_int())
		"cost":
			print(cost_text())
		"say":
			print("hud: " + state_text())
		"shot":
			# the window's own picture (Godot's capture of the root viewport) with the state it was drawn from beside it
			# (FILE.txt): both of the same displayed frame, whatever the pacing
			if value != "":
				shots.append(value)
		"test-portal":
			# a stand-in for the portal (hud/dev/portal_stub.gd), to try the notice card and its answer without a network
			if get_tree().get_first_node_in_group("portal") == null:
				var stub := Node.new()
				stub.set_script(load("res://hud/dev/portal_stub.gd"))
				get_tree().root.add_child(stub)
				_find_portal()
			if portal != null and portal.has_method("test_notice"):
				portal.call("test_notice", value if value != "" else "invite")
		"test-sticks":
			# both sticks of a controller made by the test, down or up
			for button in [JOY_BUTTON_LEFT_STICK, JOY_BUTTON_RIGHT_STICK]:
				var event := InputEventJoypadButton.new()
				event.device = 0
				event.button_index = button
				event.pressed = value != "up"
				Input.parse_input_event(event)
			Input.flush_buffered_events()
		"test":
			# test aids for pictures: events and states that a short scripted run does not reach, drawn from data
			# that is marked as test data on screen
			for piece in pieces:
				if piece.has_method("test"):
					piece.call("test", w.slice(1))
		_:
			push_warning("hud: unknown command " + " ".join(PackedStringArray(w)))


# ---- the portal's notices ------------------------------------------------------------------------
# An invitation or a friend request that arrives while playing is drawn by this HUD as one small card (top.gd).
# Answering it: F2 on the keyboard (the portal's own key), and on a controller BOTH STICKS PRESSED TOGETHER for half a
# second.  Every button of the pad is the game's; this chord is the one that costs nothing in a fight: the game sees
# its two buttons (left stick: the camera swings behind the character; right stick: the map changes its size), no
# action of the character is on either, and the chord cannot be hit by accident.  Not answering lets the card run out.
func _find_portal() -> void:
	portal = get_tree().get_first_node_in_group("portal")
	if portal == null or not portal.has_signal("notice"):
		portal = null
		return
	portal.set("draw_notices_in_game", false)
	portal.connect("notice", _on_notice)
	portal.connect("notice_gone", _on_notice_gone)


func _on_notice(d: Dictionary) -> void:
	_on_notice_gone(str(d.get("id", "")))
	var n := d.duplicate()
	n["born"] = Time.get_ticks_msec() / 1000.0
	n["seconds"] = float(d.get("seconds", 20.0 if str(d.get("kind", "")) == "invite" else 14.0))
	notices.append(n)


func _on_notice_gone(id: String) -> void:
	for k in range(notices.size() - 1, -1, -1):
		if str(notices[k].get("id", "")) == id:
			notices.remove_at(k)


func _notices(delta: float) -> void:
	if notices.is_empty():
		notice_hold = 0.0
		if notice_piece.visible:
			notice_piece.call("tick")
		return
	if machine == null or area.size == Vector2.ZERO:
		# no game picture yet (or no more): the card lays itself out in the window
		var window := Vector2(get_viewport().get_visible_rect().size)
		s = clampf(window.y / 1080.0, 0.74, 4.0) * float(setting.scale)
		picture = Rect2(Vector2.ZERO, window)
		area = picture.grow(-maxf(12.0, 0.025 * window.y))
	notice_piece.call("tick")
	var wall := Time.get_ticks_msec() / 1000.0
	if ok and (phase & (PH_MENU | PH_PAUSE_MENU | PH_GATE_MENU)) != 0:
		for n in notices:
			n.born = float(n.born) + delta     # hidden under a game screen (notice.gd): its time does not run
	for k in range(notices.size() - 1, -1, -1):
		if wall - float(notices[k].born) > float(notices[k].seconds) + 0.5:
			notices.remove_at(k)        # the portal drops its own copy by its own clock
	if notices.is_empty():
		return
	var pads := Input.get_connected_joypads()
	var device: int = pads[0] if pads.size() > 0 else 0
	if Input.is_joy_button_pressed(device, JOY_BUTTON_LEFT_STICK) and Input.is_joy_button_pressed(device, JOY_BUTTON_RIGHT_STICK):
		notice_hold += delta
		if notice_hold >= 0.5:
			notice_hold = 0.0
			var id := str(notices[notices.size() - 1].get("id", ""))
			print("hud: notice %s answered with both sticks" % id)
			if portal != null:
				portal.call("notice_answer", id, true)
			_on_notice_gone(id)
	else:
		notice_hold = 0.0


func cost_text() -> String:
	var n: float = maxf(1.0, cost_frames)
	return "hud: cost over %d displayed frames: %.1f us a frame in the HUD's scripts (most %.0f), of it %.1f us reading the state (rta_gs_update); %.1f us a frame in the pieces' _draw" % [
		cost_frames, cost_total / n, cost_most, reader_total / n, draw_total / n]


func state_text() -> String:
	if not ok:
		return "no state"
	var t := "tick %d level %s phase %x layout %d show %.2f players %d creatures %d" % [frame.get("tick", 0), frame.get("level", ""), phase, layout,
		show, frame.get("player_count", 0), creatures.size() / C_STRIDE]
	var prompt: Dictionary = frame.get("prompt", {})
	if prompt.get("active", false):
		t += " | prompt kind %d button %x \"%s\"" % [prompt.kind, prompt.button, prompt.text]
	if frame.get("message", "") != "":
		t += " | message \"%s\" (%d frames)" % [frame.message, frame.message_frames]
	var view: Dictionary = frame.get("view", {})
	t += " | view %d shown %d%s" % [view.get("mode", 0), view.get("shown", 0), (" fallback " + str(view.get("why", ""))) if view.get("fallback", false) else ""]
	if machine != null and machine.has_method("get_view"):
		var host_view: Dictionary = machine.call("get_view")
		t += " (the frame's own view: valid %s, drawn at tick %d, eye %s forward %s right %s up %s fov %.1f; read from memory now: eye %s forward %s)" % [
			str(host_view.get("valid", false)), host_view.get("tick", -1), str(host_view.get("eye")), str(host_view.get("forward")), str(host_view.get("right")),
			str(host_view.get("up")), host_view.get("fov", 0.0), str(view.get("eye")), str(view.get("forward"))]
	for p in players:
		if p.get("present", false):
			t += " | %s%s L%d hp %.2f/%.2f mana %.2f/%.2f xp %d (%d..%d) gold %d+%d potions %d/%d target %d" % [p.name, " (TEST DATA)" if p.get("fake", false) else "",
				p.level, p.health, p.health_max, p.mana, p.mana_max, p.xp, p.xp_base, p.xp_next, p.gold, p.gold_coming, p.health_potions, p.mana_potions, p.target_uid]
	for k in range(creatures.size() / C_STRIDE):
		var o := k * C_STRIDE
		t += " | #%d %s f%x hp %.2f/%.2f at %.3f,%.3f" % [int(creatures[o + C_UID]), gs.call("get_creature_name", k), int(creatures[o + C_FLAGS]), creatures[o + C_HP],
			creatures[o + C_MAX], creatures[o + C_SX], creatures[o + C_SY]]
	return t


func _process(delta: float) -> void:
	if gs == null:
		return
	var t0 := Time.get_ticks_usec()
	_notices(delta)
	draw_total += draw_usec
	draw_usec = 0.0
	machine = host.get("machine")
	if machine == null or not host.get("started"):
		ok = false
		return
	for text in machine.call("get_host_commands"):
		var w: PackedStringArray = String(text).split(" ", false)
		if w.size() >= 2 and w[0] == "hud":
			command(Array(w.slice(1)))
	var blank: int = machine.call("get_frame_number")
	if blank == last_blank:
		return                          # no new picture: nothing moved
	var steps: int = 1 if last_blank < 0 else clampi(blank - last_blank, 1, 30)
	last_blank = blank
	dt = steps / 59.94
	now += dt
	_measure()
	var aspect: float = machine.call("get_frame_aspect")
	gs.call("set_aspect", aspect)
	if machine.has_method("get_view"):
		gs.call("set_view", machine.call("get_view"))
	var r0 := Time.get_ticks_usec()
	ok = gs.call("update", machine)
	reader_total += Time.get_ticks_usec() - r0
	if ok:
		frame = gs.call("get_frame")
		phase = frame.phase
		var count: int = frame.player_count
		# eight slots: a game of five to eight (docs/issues/native-8-players.md); the slots past the count are empty
		players.resize(MAX_PLAYERS)
		for slot in range(MAX_PLAYERS):
			players[slot] = gs.call("get_player", slot) if slot < count else {"present": false}
		_fake_party()
		var local: int = frame.local_slot
		me = players[local] if local >= 0 and players[local].get("present", false) else {}
		creatures = gs.call("get_creatures")
		events = gs.call("get_events")
		# the controls side (tools/recomp/app/fpcontrols.h, Hud): what a swing or a shot would take, whether a reticle means
		# anything, attackers with their bearing.  Asked for as machine.get_controls_hud(); used when it is there.
		controls = machine.call("get_controls_hud") if machine.has_method("get_controls_hud") else {}
	else:
		phase = 0
		me = {}
		events = []
		creatures = PackedFloat32Array()
	if pillars != null:
		pillars.queue_redraw()
	if ok and not timed.is_empty():
		var k := 0
		while k < timed.size():
			var due := false
			if timed[k][0] == frame.level and typeof(timed[k][1]) == TYPE_INT:
				due = int(frame.tick) >= int(timed[k][1]) and (phase & PH_LEVEL) != 0
			elif timed[k][0] == frame.level:
				var bit: int = {"pause": PH_PAUSE_MENU, "menu": PH_MENU, "dialogue": PH_DIALOGUE, "cutscene": PH_CUTSCENE, "gate": PH_GATE_MENU}.get(timed[k][1], 0)
				phase_blanks[bit] = (int(phase_blanks.get(bit, 0)) + 1) if (phase & bit) != 0 else 0
				due = int(phase_blanks[bit]) >= 45
			if due:
				var words: Array = timed[k][2]
				timed.remove_at(k)
				command(words)
			else:
				k += 1
	_choose_layout()
	_visibility()
	_game_hud()
	for piece in pieces:
		piece.call("tick")
	music.call("tick")
	var spent := float(Time.get_ticks_usec() - t0)
	cost_usec = spent
	cost_total += spent
	cost_most = maxf(cost_most, spent)
	cost_frames += 1
	if not shots.is_empty():
		var paths := shots
		shots = PackedStringArray()
		var text := state_text()
		await RenderingServer.frame_post_draw
		var image := get_viewport().get_texture().get_image()
		for path in paths:
			image.save_png(path)
			var file := FileAccess.open(path.get_basename() + ".txt", FileAccess.WRITE)
			if file != null:
				file.store_string(text + "\n")
				file.close()
			print("hud: wrote %s (%d x %d) and its state" % [path, image.get_width(), image.get_height()])


func _draw_pillars() -> void:
	if not ok or (phase & PH_FRONTEND) != 0 or (phase & (PH_GATE_MENU | PH_LOADING)) == 0:
		return
	var four := picture.size.y * 4.0 / 3.0
	if picture.size.x <= four + 2.0:
		return
	var side := (picture.size.x - four) * 0.5
	pillars.draw_rect(Rect2(picture.position, Vector2(side, picture.size.y)), Color.BLACK)
	pillars.draw_rect(Rect2(picture.position + Vector2(picture.size.x - side, 0.0), Vector2(side, picture.size.y)), Color.BLACK)


func _measure() -> void:
	var window := Vector2(get_viewport().get_visible_rect().size)
	var shape: float = machine.call("get_frame_aspect")
	var w := window.x
	var h := window.y
	if w / maxf(h, 1.0) > shape:
		w = h * shape
	else:
		h = w / shape
	picture = Rect2((window - Vector2(w, h)) * 0.5, Vector2(w, h))
	s = clampf(h / 1080.0, 0.74, 4.0) * float(setting.scale)     # not below what keeps the small print at ten pixels
	# safe margins: 2.5 % of the height, and the corners never farther out than a 21:9 picture's would be at 16:9 content width
	var margin: float = maxf(12.0, 0.025 * h)
	var content_w: float = minf(w, h * 2.0)
	area = Rect2(picture.position + Vector2((w - content_w) * 0.5 + margin, margin), Vector2(content_w - 2.0 * margin, h - 2.0 * margin))


func _choose_layout() -> void:
	var wanted: String = setting.view
	if wanted == "auto":
		var view: Dictionary = frame.get("view", {}) if ok else {}
		var shown: int = view.get("shown", 0)
		layout = LAYOUT_FIRST if shown == 4 else (LAYOUT_THIRD if shown >= 2 else LAYOUT_OVERHEAD)
	else:
		layout = {"overhead": LAYOUT_OVERHEAD, "third": LAYOUT_THIRD, "first": LAYOUT_FIRST}[wanted]


func _visibility() -> void:
	var playing: bool = ok and (phase & PH_LEVEL) != 0 and (phase & (PH_FRONTEND | PH_LOADING | PH_MENU | PH_PAUSE_MENU | PH_CUTSCENE | PH_DIALOGUE | PH_GATE_MENU)) == 0
	if ok and playing:
		var view: Dictionary = frame.get("view", {})
		if view.get("fallback", false) and str(view.get("why", "")) != "death":
			playing = false
	if setting.mode == "original" or me.is_empty():
		playing = false
	var paused: bool = ok and setting.mode != "original" and (phase & PH_LEVEL) != 0 and (phase & PH_PAUSE_MENU) != 0
	show = move_toward(show, 1.0 if playing else 0.0, dt / (0.22 if playing else 0.12))
	pause_show = move_toward(pause_show, 1.0 if paused else 0.0, dt / 0.15)
	var a := Style.ease_out(show)
	for piece in pieces:
		if piece.name == "Pause":
			piece.modulate.a = Style.ease_out(pause_show)
			piece.visible = pause_show > 0.0
		else:
			piece.modulate.a = a
			piece.visible = show > 0.0
	root.modulate.a = 1.0


func _game_hud() -> void:
	# the game's own HUD layer: off with "new" - when the host can do that
	var want := 2 if setting.mode != "new" else 1
	if want == game_hud_asked:
		return
	game_hud_asked = want
	# In the picture the game's HUD is two groups.  "game_hud": player status, gold, compass, minimap, spell selector (the
	# library has the switch).  "game_hud_text": the boss meter with the one-line message (0x1d93b0) and the prompt box
	# (0x1d99f0) - asked for, not there yet; while the game still draws those, this HUD does not draw its own message and
	# prompt over them (with "both" it does: that mode is for comparing).
	var can: bool = machine.has_method("set_option")
	var text_off: bool = can and machine.call("set_option", "game_hud_text", "on" if want == 2 else "off") and want == 1
	own_text = setting.mode == "both" or text_off
	setting["game_meter_hidden"] = text_off
	if can and machine.call("set_option", "game_hud", "on" if want == 2 else "off"):
		return
	if want == 1 and not said.has("game_hud"):
		said["game_hud"] = true
		print("hud: mode new, but this library has no switch for the game's own HUD layer (set_option game_hud): both are visible")


# ---- test data ---------------------------------------------------------------------------------
# The library has no network yet, so a second player's frame cannot come from a game.  "fake-party N" adds N
# players made up here; they are marked on screen ("TEST DATA") and never touch the game.
func _fake_party() -> void:
	var n: int = setting.fake_party
	if n <= 0 or players[0].get("present", false) == false:
		return
	var real: Dictionary = players[0]
	var made := 0
	for slot in range(1, MAX_PLAYERS):
		if made >= n:
			break
		if players[slot].get("present", false):
			continue
		made += 1
		var wave: float = 0.5 + 0.5 * sin(now * (0.5 + 0.13 * slot) + slot * 1.7)
		var p := real.duplicate(true)
		p.fake = true
		p.local = false
		p.name = "TEST DATA %d" % (slot + 1)
		p.class_name = "made up"
		p.level = real.level + slot * 2
		p.health_max = 180.0 + 60.0 * slot
		p.health = p.health_max * (0.25 + 0.75 * wave) if slot != 3 else 0.0
		p.alive = slot != 3
		p.mana_max = 90.0 + 30.0 * slot
		p.mana = p.mana_max * (1.0 - 0.6 * wave)
		p.health_coming = 0.0
		p.mana_coming = 0.0
		p.status = PackedFloat32Array([4.0, 0.0, 6.0 * wave, 6.0]) if slot == 1 else PackedFloat32Array()
		var pos: Vector3 = real.position + Vector3(70.0 * cos(now * 0.3 + slot * 2.1), 70.0 * sin(now * 0.3 + slot * 2.1), 0.0)
		p.position = pos
		p.screen = gs.call("project", pos + Vector3(0, 0, real.height * 1.05))
		p.target_uid = 0
		players[slot] = p


# ---- helpers for the pieces --------------------------------------------------------------------
# normalised picture coordinates (RtaGameState's screen[]) -> window pixels
func to_window(sx: float, sy: float) -> Vector2:
	return picture.position + Vector2(sx, sy) * picture.size


func project(world: Vector3) -> Vector3:
	return gs.call("project", world)


func creature_name(index: int) -> String:
	return gs.call("get_creature_name", index)


func draw_begin() -> int:
	return Time.get_ticks_usec()


func draw_end(t0: int) -> void:
	draw_usec += Time.get_ticks_usec() - t0


# what a button of the game is called on the device in use: a controller's own name, or the key the host maps to it
const PAD_NAMES := {0x1: "L2", 0x2: "R2", 0x4: "L1", 0x8: "R1", 0x10: "tri", 0x20: "cir", 0x40: "cro", 0x80: "squ", 0x100: "Select", 0x200: "L3",
	0x400: "R3", 0x800: "Start", 0x1000: "Up", 0x2000: "Right", 0x4000: "Down", 0x8000: "Left"}
const KEY_NAMES := {0x1: "1", 0x2: "3", 0x4: "Q", 0x8: "E", 0x10: "I", 0x20: "L", 0x40: "K", 0x80: "J", 0x100: "Bksp", 0x200: "X", 0x400: "C",
	0x800: "Enter", 0x1000: "Up", 0x2000: "Right", 0x4000: "Down", 0x8000: "Left"}


func button_label(game_mask: int) -> String:
	# game_mask: the game's own pad word (g_btn* tables): low byte L2 R2 L1 R1 triangle circle cross square
	var pad := Input.get_connected_joypads().size() > 0
	for bit in PAD_NAMES:
		if game_mask & bit:
			return PAD_NAMES[bit] if pad else KEY_NAMES[bit]
	return "?"
