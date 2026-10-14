extends Node
# portal.gd - the portal: everything a player sees before and between games.
#
# The portal is the project's first scene (the ONE line: run/main_scene in project.godot).
# It asks one question the first time ("What should friends call you?"), then shows Home:
# play alone, host a game, join with a code, friends - and the character played last.
# When a game starts it puts the game scene (res://main.tscn) under itself and gets out of
# the way; when the game is over it comes back in front of it.
#
#   Portal (this)                   group "portal"
#     Game                          the game scene, once one has been started (handover.gd)
#     Layer (CanvasLayer 20)        above the game and its HUD (layer 10)
#       Root
#         Backdrop                  the game's picture blurred and dimmed, when a game is behind
#         Background                the portal's own animated background
#         Top, Host, HintBar        the bar at the top, the screen, the line at the bottom
#         ModalHost                 a question or a small menu over the screen
#         Notices                   invitations and requests: one press answers them
#
# Options after "--" on Godot's command line (all optional; none needed by a player):
#   --no-portal             straight to the game scene, as before the portal existed
#                           (also when --script is given: test routes of the game start as they did)
#   --portal-mock           the session's mock instead of a service (tools/recomp/net2/session_mock.cpp)
#   --portal-service H:P    the rendezvous service to use (else [online] service of portal.cfg)
#   --portal-data DIR       where portal.cfg and the identity live (default user://)
#   --portal-test NAME      a test: nothing leaves the program (no clipboard, no file dialog, no full screen)
#   --portal-stub-game      hand over to a stand-in instead of the game scene (dev/stub_game.gd)
#   --portal-start SCREEN   open on this screen (tests)
#   --portal-shot FILE --portal-quit-after SECONDS      save the window's own picture, then end (tests)
#
# For the HUD (tools/godot/project/hud): get_tree().get_first_node_in_group("portal") has
#   signal notice(d)        d = {id, kind: "invite"|"request", who, title, text, accept_text}
#   signal notice_gone(id)
#   func notice_answer(id: String, accept: bool)
#   var draw_notices_in_game  set it false to draw them yourself

const UI := preload("res://portal/ui.gd")
const W := preload("res://portal/widgets.gd")
const Screen := preload("res://portal/screen.gd")
const Session := preload("res://portal/session.gd")
const Profile := preload("res://portal/profile.gd")
const Notices := preload("res://portal/notices.gd")
const Handover := preload("res://portal/handover.gd")
const GameFlow := preload("res://portal/gameflow.gd")

const SCREENS := {
	"first": "res://portal/screens/first.gd",
	"disc": "res://portal/screens/disc.gd",
	"home": "res://portal/screens/home.gd",
	"friends": "res://portal/screens/friends.gd",
	"join": "res://portal/screens/join.gd",
	"room": "res://portal/screens/room.gd",
	"characters": "res://portal/screens/characters.gd",
	"settings": "res://portal/screens/settings.gd",
}
const MARGIN := 56.0
const TOP := 104.0
const BOTTOM := 64.0
const MAX_WIDTH := 1800.0

signal notice(d: Dictionary)
signal notice_gone(id: String)
signal shown_changed(is_shown: bool)

var options := {"test": "", "data": "", "mock": false, "service": "", "stub_game": false, "start": "", "embedded": false, "mock_speed": "", "shot": "", "quit_after": 0.0}
var session: Node
var profile: RefCounted
var handover: Node
var gameflow: Node                  # the game's side of a room (gameflow.gd)
var draw_notices_in_game := true

var layer: CanvasLayer
var root: Control
var backdrop: ColorRect
var background: ColorRect
var top: Control
var host: Control
var hint_bar: Control
var modal_host: Control
var notices: Control
var game_slot: Node

var screen: Control
var stack: Array = []
var modal: Dictionary = {}
var shown := true                   # false while the game has the screen
var passing := false                # --no-portal: this node only passes on to the game scene
var pending_room := false           # a host / join / invite was asked for: go to the room when it opens
var pending_invite := ""            # invite this friend as soon as my room is open
var seen_requests := {}
var seen_invites := {}
var last_link := -1
var glyph_style := "xbox"
var starting_since := 0             # a session start is under way (milliseconds), 0: none


func _ready() -> void:
	add_to_group("portal")
	_parse_arguments()
	if passing:
		get_tree().change_scene_to_file.call_deferred("res://main.tscn")
		return
	_controller_actions()
	if test_mode() and not bool(options.embedded):
		# a test window: named, small, out of the way, never taking the keyboard
		var window := get_window()
		window.title = "AGENT TEST - portal " + String(options.test)
		window.set_flag(Window.FLAG_NO_FOCUS, true)
		var area := DisplayServer.screen_get_usable_rect()
		window.position = area.position + area.size - window.size - Vector2i(24, 24)
		AudioServer.set_bus_mute(0, true)
		if float(options.quit_after) > 0.0:
			_end_test.call_deferred()
	profile = Profile.new()
	profile.load_from(String(options.data) if String(options.data) != "" else "user://")
	game_slot = Node.new()
	game_slot.name = "Game"
	add_child(game_slot)
	_build_layer()
	session = Session.new()
	session.name = "Session"
	session.fallback_name = profile.name_shown()
	add_child(session)
	session.event.connect(_on_event)
	session.changed.connect(_on_changed)
	handover = Handover.new()
	handover.name = "Handover"
	handover.portal = self
	add_child(handover)
	gameflow = GameFlow.new()
	gameflow.name = "GameFlow"
	gameflow.portal = self
	add_child(gameflow)
	gameflow.phase_changed.connect(func(_phase: int) -> void:
		if screen != null:
			screen.call("session_changed", "game"))
	if profile.first_start_done():
		_open_session()                 # not before the one question is answered: the name is what is registered
	get_viewport().size_changed.connect(_layout)
	Input.joy_connection_changed.connect(func(_device: int, _connected: bool) -> void: _detect_pad_style())
	_detect_pad_style()
	apply_settings()
	_layout()
	var first := String(options.start)
	if first == "":
		first = "home" if profile.first_start_done() else "first"
	go(first, {}, true)


func _parse_arguments() -> void:
	var args := OS.get_cmdline_user_args()
	var given := {}
	var k := 0
	while k < args.size():
		var a := args[k]
		var value := args[k + 1] if k + 1 < args.size() else ""
		match a:
			"--portal-test": given["test"] = value; k += 1
			"--portal-data": given["data"] = value; k += 1
			"--portal-service": given["service"] = value; k += 1
			"--portal-start": given["start"] = value; k += 1
			"--portal-mock-speed": given["mock_speed"] = value; k += 1
			"--portal-shot": given["shot"] = value; k += 1
			"--portal-quit-after": given["quit_after"] = value.to_float(); k += 1
			"--portal-mock": given["mock"] = true
			"--portal-stub-game": given["stub_game"] = true
			"--no-portal", "--script": given["pass"] = true
		k += 1
	if not bool(options.embedded):
		for key in given:
			if key != "pass":
				options[key] = given[key]
		passing = given.has("pass") or DisplayServer.get_name() == "headless"


func _controller_actions() -> void:
	# Godot's own "accept" and "cancel" are keys only; a controller's A / cross and B / circle are added here
	# (at run time: the project's settings are not touched)
	for pair in [["ui_accept", JOY_BUTTON_A], ["ui_cancel", JOY_BUTTON_B]]:
		var e := InputEventJoypadButton.new()
		e.device = -1
		e.button_index = pair[1]
		if not InputMap.action_has_event(pair[0], e):
			InputMap.action_add_event(pair[0], e)


func _end_test() -> void:
	await get_tree().create_timer(float(options.quit_after)).timeout
	if String(options.shot) != "":
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(String(options.shot))
		print("portal: wrote ", options.shot, " screen ", current_name(), ", link ", int(session.me().get("link", 0)), ", friends ", session.friends().size())
	quit()


func test_mode() -> bool:
	return String(options.test) != ""


func _open_session() -> void:
	# where the service is: --portal-service, else what the client finds by itself - the
	# environment's RTA_NET2_SERVICE, then the first line of <data>/net2-service.txt (Settings -> Online)
	var config := {
		"mock": bool(options.mock), "service": String(options.service), "name": profile.name_shown(),
		"data_dir": ProjectSettings.globalize_path(profile.folder), "build": "portal", "local_only": test_mode(),
	}
	if not session.open(config):
		return
	if gameflow != null:
		gameflow.call("attach")
	if String(options.mock_speed) != "" and bool(options.mock):
		session.setting("mock-speed", String(options.mock_speed))
	var c: Dictionary = profile.character()
	if String(c.get("name", "")) != "":
		session.set_character(c)


func service_file() -> String:
	return ProjectSettings.globalize_path(profile.folder).path_join("net2-service.txt")


func service_named() -> String:
	# what Settings -> Online shows in its field
	if String(options.service) != "":
		return String(options.service)
	if OS.has_environment("RTA_NET2_SERVICE"):
		return OS.get_environment("RTA_NET2_SERVICE")
	var f := FileAccess.open(service_file(), FileAccess.READ)
	return f.get_line().strip_edges() if f != null else ""


func set_service(address: String) -> void:
	# kept where the client looks for it; the session is opened again with it
	var f := FileAccess.open(service_file(), FileAccess.WRITE)
	if f != null:
		f.store_line(address.strip_edges())
		f.close()
	options.service = ""
	seen_requests = {}
	seen_invites = {}
	_open_session()
	top.call("build")
	refresh_hints()
	if screen != null:
		screen.call("rebuild")


# ---- the layer and its parts ---------------------------------------------------------------
func _build_layer() -> void:
	if ResourceLoader.exists("res://gameart/portal_skin.gd"):
		load("res://gameart/portal_skin.gd").install(self)      # the game's art from the player's disc (gameart.gd)
	layer = CanvasLayer.new()
	layer.name = "Layer"
	layer.layer = 20
	add_child(layer)
	root = Control.new()
	root.name = "Root"
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)
	backdrop = ColorRect.new()
	backdrop.name = "Backdrop"
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var blur := ShaderMaterial.new()
	blur.shader = load("res://portal/backdrop.gdshader")
	backdrop.material = blur
	backdrop.visible = false
	root.add_child(backdrop)
	background = ColorRect.new()
	background.name = "Background"
	background.mouse_filter = Control.MOUSE_FILTER_STOP      # nothing under the portal is clicked
	var sky := ShaderMaterial.new()
	sky.shader = load("res://portal/background.gdshader")
	background.material = sky
	root.add_child(background)
	UI.skinned("decorate", [self, root])                       # a skin's own layer over the background
	top = TopBar.new()
	top.name = "Top"
	top.portal = self
	root.add_child(top)
	host = Control.new()
	host.name = "Host"
	host.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(host)
	hint_bar = W.Hints.new()
	hint_bar.name = "HintBar"
	root.add_child(hint_bar)
	modal_host = Control.new()
	modal_host.name = "ModalHost"
	modal_host.mouse_filter = Control.MOUSE_FILTER_STOP
	modal_host.visible = false
	root.add_child(modal_host)
	notices = Notices.new()
	notices.name = "Notices"
	notices.in_game_hint = "F2"
	layer.add_child(notices)
	notices.answered.connect(func(id: String, _accepted: bool) -> void:
		notice_gone.emit(id)
		refresh_hints())
	notices.count_changed.connect(refresh_hints)


func view_size() -> Vector2:
	return get_viewport().get_visible_rect().size


func _layout() -> void:
	if passing or root == null:
		return
	var size := view_size()
	if size.x < 8.0 or size.y < 8.0:
		return
	UI.set_scale_for(size)
	root.position = Vector2.ZERO
	root.size = size
	backdrop.position = Vector2.ZERO
	backdrop.size = size
	background.position = Vector2.ZERO
	background.size = size
	(background.material as ShaderMaterial).set_shader_parameter("size", size)
	var w := minf(size.x - UI.px(MARGIN) * 2.0, UI.px(MAX_WIDTH))
	var x := roundf((size.x - w) * 0.5)
	top.position = Vector2(x, 0)
	top.size = Vector2(w, UI.px(TOP))
	top.call("build")
	hint_bar.position = Vector2(x, size.y - UI.px(BOTTOM) - UI.px(10))
	hint_bar.size = Vector2(w, UI.px(BOTTOM))
	host.position = Vector2(x, UI.px(TOP + 12.0))
	host.size = Vector2(w, size.y - UI.px(TOP + 12.0 + BOTTOM + 22.0))
	modal_host.position = Vector2.ZERO
	modal_host.size = size
	notices.position = Vector2.ZERO
	notices.size = size
	notices.queue_redraw()
	if screen != null:
		screen.position = Vector2.ZERO
		screen.size = host.size
		screen.call("rebuild")
	if not modal.is_empty():
		_build_modal()
	refresh_hints()


# ---- screens -------------------------------------------------------------------------------
func go(name: String, args := {}, replace := false) -> void:
	if not SCREENS.has(name):
		push_warning("portal: no screen " + name)
		return
	if not stack.is_empty() and String(stack[stack.size() - 1].name) == name and not replace:
		return
	if replace:
		stack.clear()
	stack.append({"name": name, "args": args})
	_show(1)


func back() -> void:
	if not modal.is_empty():
		close_modal()
		return
	if screen != null and screen.call("handle_back"):
		return
	if stack.size() > 1:
		stack.pop_back()
		_show(-1)
	elif current_name() == "home":
		confirm("Leave the game?", "", "Quit", func() -> void: quit(), false, "Stay")


func home() -> void:
	stack = [{"name": "home", "args": {}}]
	_show(-1)


func current_name() -> String:
	return String(stack[stack.size() - 1].name) if not stack.is_empty() else ""


func _show(direction: int) -> void:
	close_modal()
	var entry: Dictionary = stack[stack.size() - 1]
	var old := screen
	if old != null:
		var gone := create_tween()
		gone.set_parallel(true)
		gone.tween_property(old, "modulate:a", 0.0, 0.09)
		gone.tween_property(old, "position:x", -UI.px(28) * direction, 0.09)
		gone.chain().tween_callback(old.queue_free)
		old.set("focus_behavior_recursive", 1)
	screen = (load(SCREENS[entry.name]) as GDScript).new()
	screen.name = String(entry.name).capitalize()
	screen.call("setup", self, entry.args)
	host.add_child(screen)
	screen.position = Vector2(UI.px(28) * direction, 0)
	screen.size = host.size
	screen.modulate.a = 0.0
	screen.call("build")
	var come := create_tween()
	come.set_parallel(true)
	come.set_ease(Tween.EASE_OUT)
	come.set_trans(Tween.TRANS_CUBIC)
	come.tween_property(screen, "modulate:a", 1.0, 0.16)
	come.tween_property(screen, "position:x", 0.0, 0.16)
	screen.call("focus_now")
	top.call("build")
	refresh_hints()


func screen_may_focus(s: Control) -> bool:
	return s == screen and modal.is_empty() and shown


func refresh_hints() -> void:
	if hint_bar == null or screen == null:
		return
	var items: Array = screen.call("all_hints") if modal.is_empty() else [Screen.hint_select(), Screen.hint_back("Cancel")]
	var it: Dictionary = notices.call("current")
	if not it.is_empty():
		items = [{"pad": "y", "key": "Y", "text": String(it.get("accept_text", "Accept"))}] + items
	hint_bar.style = glyph_style
	hint_bar.set_items(items)
	var me: Dictionary = session.me() if session != null else {}
	var link := int(me.get("link", 0))
	match link:
		2:
			hint_bar.left_text = "Online" + ("  (practice mode: made-up friends)" if bool(me.get("mock", false)) else "")
			hint_bar.left_colour = UI.GREEN
		1:
			var trouble := String(me.get("problem", ""))
			hint_bar.left_text = "Connecting..." if trouble == "" or trouble.begins_with("Connecting") else "Connecting... (" + trouble.trim_suffix(".") + ")"
			hint_bar.left_colour = UI.GOLD
		_:
			var problem := String(me.get("problem", ""))
			hint_bar.left_text = "Offline - playing alone works" + (" (" + problem.trim_suffix(".") + ")" if problem != "" else "")
			hint_bar.left_colour = UI.FAINT
	if not screen.call("chrome"):
		hint_bar.left_text = ""         # the first question: nothing about a connection yet
	notices.visible = screen.call("chrome") or not shown     # nothing interrupts the first question
	hint_bar.queue_redraw()
	notices.glyph_style = glyph_style
	notices.queue_redraw()


# ---- a question or a small menu over the screen -------------------------------------------
func confirm(title: String, text: String, yes_text: String, on_yes: Callable, danger := false, no_text := "Cancel") -> void:
	modal = {"kind": "confirm", "title": title, "text": text, "items": [
		{"text": no_text, "kind": "ghost", "run": Callable()},
		{"text": yes_text, "kind": "danger" if danger else "primary", "run": on_yes}], "focus": 0 if danger else 1}
	_open_modal()


func menu(title: String, items: Array, text := "") -> void:
	modal = {"kind": "menu", "title": title, "text": text, "items": items, "focus": 0}
	_open_modal()


func _open_modal() -> void:
	var owner_now := get_viewport().gui_get_focus_owner()
	if owner_now != null and screen != null and screen.is_ancestor_of(owner_now) and "key" in owner_now:
		screen.set("want_focus", String(owner_now.get("key")))
	host.set("focus_behavior_recursive", 1)
	top.set("focus_behavior_recursive", 1)
	modal_host.visible = true
	modal_host.modulate.a = 0.0
	create_tween().tween_property(modal_host, "modulate:a", 1.0, 0.12)
	_build_modal()
	refresh_hints()


func _build_modal() -> void:
	for child in modal_host.get_children():
		modal_host.remove_child(child)
		child.queue_free()
	var dim := ColorRect.new()
	dim.color = Color(0.01, 0.012, 0.02, 0.66)
	dim.size = modal_host.size
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	modal_host.add_child(dim)
	var is_menu := String(modal.kind) == "menu"
	var w := UI.px(620.0 if not is_menu else 520.0)
	var pad := UI.px(40)
	var title := UI.label(String(modal.title), 34, UI.TEXT, UI.serif_bold(), true)
	title.size = Vector2(w - pad * 2.0, 10)
	var body: Label = null
	var h := pad
	var title_h := title.get_minimum_size().y
	title.custom_minimum_size.x = w - pad * 2.0
	title_h = maxf(title_h, UI.line_height(UI.serif_bold(), 34) * ceilf(UI.text_width(String(modal.title), UI.serif_bold(), 34) / (w - pad * 2.0)))
	h += title_h + UI.px(10)
	var body_h := 0.0
	if String(modal.text) != "":
		body = UI.label(String(modal.text), 20, UI.DIM, null, true)
		body_h = UI.line_height(UI.sans(), 20) * ceilf(UI.text_width(String(modal.text), UI.sans(), 20) / (w - pad * 2.0) + 0.15) + UI.px(8)
		h += body_h + UI.px(8)
	h += UI.px(18)
	var items: Array = modal.items
	var bh := UI.px(60)
	var buttons_h := bh if not is_menu else items.size() * (bh + UI.px(10)) - UI.px(10)
	h += buttons_h + pad
	var panel := Screen.PanelDraw.new()
	panel.radius = 18.0
	panel.alpha = 1.18
	modal_host.add_child(panel)
	panel.size = Vector2(w, h)
	panel.position = ((modal_host.size - panel.size) * 0.5).round()
	panel.add_child(title)
	title.position = Vector2(pad, pad)
	title.size = Vector2(w - pad * 2.0, title_h)
	var y := pad + title_h + UI.px(10)
	if body != null:
		panel.add_child(body)
		body.position = Vector2(pad, y)
		body.size = Vector2(w - pad * 2.0, body_h)
		y += body_h + UI.px(8)
	y += UI.px(18)
	var made: Array = []
	var bw := (w - pad * 2.0 - UI.px(14) * (items.size() - 1)) / items.size()
	for k in items.size():
		var it: Dictionary = items[k]
		var b := W.Btn.new(String(it.text), String(it.get("icon", "")), String(it.get("kind", "normal")))
		b.fixed = true
		b.align_left = is_menu
		panel.add_child(b)
		if is_menu:
			b.position = Vector2(pad, y + k * (bh + UI.px(10)))
			b.size = Vector2(w - pad * 2.0, bh)
		else:
			b.position = Vector2(pad + k * (bw + UI.px(14)), y)
			b.size = Vector2(bw, bh)
		var run: Callable = it.get("run", Callable())
		b.activated.connect(func() -> void:
			close_modal()
			if run.is_valid():
				run.call())
		made.append(b)
	# the focus stays inside the box
	for k in made.size():
		var b: Control = made[k]
		var prev: Control = made[posmod(k - 1, made.size())]
		var next: Control = made[posmod(k + 1, made.size())]
		if is_menu:
			b.focus_neighbor_top = b.get_path_to(prev)
			b.focus_neighbor_bottom = b.get_path_to(next)
			b.focus_neighbor_left = b.get_path_to(b)
			b.focus_neighbor_right = b.get_path_to(b)
		else:
			b.focus_neighbor_left = b.get_path_to(prev)
			b.focus_neighbor_right = b.get_path_to(next)
			b.focus_neighbor_top = b.get_path_to(b)
			b.focus_neighbor_bottom = b.get_path_to(b)
		b.focus_next = b.get_path_to(next)
		b.focus_previous = b.get_path_to(prev)
	(made[clampi(int(modal.focus), 0, made.size() - 1)] as Control).grab_focus()


func close_modal() -> void:
	if modal.is_empty():
		return
	modal = {}
	for child in modal_host.get_children():
		modal_host.remove_child(child)
		child.queue_free()
	modal_host.visible = false
	host.set("focus_behavior_recursive", 0)
	top.set("focus_behavior_recursive", 0)
	if screen != null:
		screen.call("focus_now")
	refresh_hints()


# ---- what the session says ----------------------------------------------------------------
func toast(title: String, kind := "info", text := "") -> void:
	notices.call("push", {"id": "toast:" + title, "kind": kind, "title": title, "text": text})


func _on_changed(what: String) -> void:
	if what == "friends" or what == "requests" or what == "me" or what == "link" or what == "invites":
		top.call("build")
	if what == "link" or what == "me":
		refresh_hints()
	if what == "requests":
		_sync_requests()
	if what == "invites":
		_sync_invites()
	if screen != null:
		screen.call("session_changed", what)


func _on_event(e: Dictionary) -> void:
	var type := int(e.type)
	match type:
		Session.EV_NOTICE:
			toast(String(e.text), "info")
		Session.EV_ERROR:
			if not (screen != null and screen.has_method("takes_errors") and screen.call("takes_errors")):
				toast(String(e.text), "error")
			pending_room = false
			pending_invite = ""
		Session.EV_ROOM:
			var room: Dictionary = session.room()
			var state := int(room.get("state", 0))
			if state >= Session.ROOM_OPEN and pending_invite != "":
				session.invite(pending_invite)
				pending_invite = ""
			if state == Session.ROOM_IN_GAME and starting_since > 0:
				starting_since = 0
				if not gameflow.active:
					handover.call("reveal")     # with the game's side the game's own phases decide (gameflow.gd)
			if state == Session.ROOM_OPEN and pending_room:
				pending_room = false
				if not shown:
					handover.call("finish", "room")
				if current_name() != "room":
					go("room")
			elif state == Session.ROOM_NONE and current_name() == "room":
				# the room is gone (it could not be opened, or I was taken out): back to where I came from
				if stack.size() > 1:
					stack.pop_back()
					_show(-1)
				else:
					home()
		Session.EV_START:
			# the game is woken under the portal; the room stays up ("finding each other") until the game runs
			handover.call("start", {"kind": "session", "session": session.game()}, false)
			starting_since = Time.get_ticks_msec()
		Session.EV_GAME_OVER:
			handover.call("finish", "over")
			if session.in_room() and current_name() != "room":
				go("room", {"played": true})
	if screen != null:
		screen.call("session_event", e)


func _sync_requests() -> void:
	var now := {}
	for r in session.requests():
		if not bool(r.incoming):
			continue
		var id := String(r.id)
		now[id] = true
		if not seen_requests.has(id):
			var d := {"id": "request:" + id, "kind": "request", "who": String(r.name), "seed": id, "title": String(r.name),
				"text": "wants to be your friend", "accept_text": "Accept"}
			var item := d.duplicate()
			item["on_accept"] = func() -> void: session.friend_accept(id)
			notices.call("push", item)
			notice.emit(d)
	for id in seen_requests:
		if not now.has(id):
			notices.call("drop", "request:" + String(id))
			notice_gone.emit("request:" + String(id))
	seen_requests = now


func _sync_invites() -> void:
	var now := {}
	for v in session.invites():
		var id := String(v.from_id)
		now[id] = true
		if not seen_invites.has(id):
			var c: Dictionary = v.get("character", {})
			var text := "Room " + String(v.room)
			if String(c.get("name", "")) != "":
				text = "Playing " + UI.character_line(c)
			var d := {"id": "invite:" + id, "kind": "invite", "who": String(v.from_name), "seed": id, "title": String(v.from_name) + " invites you to play",
				"text": text, "accept_text": "Join"}
			var item := d.duplicate()
			item["on_accept"] = func() -> void: accept_invite(id)
			item["seconds"] = 20.0
			notices.call("push", item)
			notice.emit(d)
	for id in seen_invites:
		if not now.has(id):
			notices.call("drop", "invite:" + String(id))
			notice_gone.emit("invite:" + String(id))
	seen_invites = now


func notice_answer(id: String, accept: bool) -> void:
	# for a HUD that draws the notices itself
	for it in notices.items:
		if String(it.id) == id:
			if accept and it.has("on_accept"):
				(it.on_accept as Callable).call()
			notices.call("drop", id)
			notice_gone.emit(id)
			return


# ---- things several screens do -------------------------------------------------------------
func need_disc() -> bool:
	# true: the disc image is not there yet and the player has been taken to the screen that says so
	if profile.disc_found() or bool(options.stub_game):
		return false
	go("disc")
	return true


func play_alone() -> void:
	if need_disc():
		return
	handover.call("start", {"kind": "alone", "character": profile.character()})


func host_game() -> void:
	if not session.online():
		toast("You are offline - a room needs the connection.", "error", String(session.me().get("problem", "")))
		return
	if need_disc():
		return
	if session.in_room():
		go("room")
		return
	pending_room = true
	session.host({"level": "", "difficulty": 1, "mode": 0, "open_to": Session.OPEN_FRIENDS})
	go("room")


func join_code(code: String) -> void:
	pending_room = true
	session.join(code)


func join_friend(id: String) -> void:
	if need_disc():
		return
	pending_room = true
	session.join_friend(id)


func accept_invite(from_id: String) -> void:
	pending_room = true
	session.invite_accept(from_id)


func invite_friend(id: String, name: String) -> void:
	if session.in_room() and int(session.room().get("state", 0)) >= Session.ROOM_OPEN:
		session.invite(id)
		toast("Invitation sent to " + name, "good")
		return
	if need_disc():
		return
	# no room yet: open one, invite when it is there
	pending_invite = id
	pending_room = true
	session.host({"level": "", "difficulty": 1, "mode": 0, "open_to": Session.OPEN_FRIENDS})
	toast("Opening a room and inviting " + name, "good")


func copy_text(text: String, what: String) -> void:
	if not test_mode():
		DisplayServer.clipboard_set(text)
	toast(what + " copied", "good")


func set_name_shown(value: String) -> void:
	profile.set_name_shown(value)
	session.fallback_name = value
	if session.available():
		session.set_name_shown(value)
	else:
		_open_session()
	top.call("build")


func choose_character(c: Dictionary) -> void:
	profile.set_character(c)
	session.set_character(c)


func choose_disc(done: Callable) -> void:
	if test_mode() or DisplayServer.get_name() == "headless":
		toast("A test never opens a file dialog", "info")
		return
	var dialog := FileDialog.new()
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.use_native_dialog = true
	dialog.title = "Your disc image of the game"
	dialog.filters = PackedStringArray(["*.iso ; Disc images"])
	dialog.file_selected.connect(func(path: String) -> void:
		profile.set_disc_path(path)
		dialog.queue_free()
		done.call())
	dialog.canceled.connect(dialog.queue_free)
	add_child(dialog)
	dialog.popup_centered_ratio(0.7)


func apply_settings() -> void:
	# what can be applied from here; the camera view and the picture's shape go to the game at the hand-over
	if test_mode():
		return
	var window := get_window()
	var want_full := bool(profile.setting("fullscreen"))
	var is_full := window.mode == Window.MODE_FULLSCREEN or window.mode == Window.MODE_EXCLUSIVE_FULLSCREEN
	if want_full != is_full:
		window.mode = Window.MODE_FULLSCREEN if want_full else Window.MODE_WINDOWED
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(0.0001, float(profile.setting("volume")))))
	AudioServer.set_bus_mute(0, float(profile.setting("volume")) <= 0.0)


func quit() -> void:
	if session != null:
		session.close()
	if handover != null and handover.call("quit_game"):
		return
	get_tree().quit(0)


# ---- showing and hiding (the game has the screen) -------------------------------------------
func set_shown(value: bool, game_behind := false) -> void:
	if shown == value:
		backdrop.visible = game_behind and value
		(background.material as ShaderMaterial).set_shader_parameter("dim", 0.5 if game_behind else 1.0)
		return
	shown = value
	backdrop.visible = game_behind
	(background.material as ShaderMaterial).set_shader_parameter("dim", 0.5 if game_behind else 1.0)
	notices.set("compact", not value)
	notices.queue_redraw()
	var t := create_tween()
	if value:
		root.visible = true
		root.modulate.a = 0.0
		t.tween_property(root, "modulate:a", 1.0, 0.18)
		if screen != null:
			screen.call("rebuild")
	else:
		close_modal()
		var owner_now := get_viewport().gui_get_focus_owner()
		if owner_now != null:
			owner_now.release_focus()
		t.tween_property(root, "modulate:a", 0.0, 0.16)
		t.tween_callback(func() -> void: root.visible = false)
	shown_changed.emit(value)


# ---- input ---------------------------------------------------------------------------------
func _detect_pad_style() -> void:
	var style := String(profile.setting("glyphs")) if profile != null else "auto"
	if style == "auto":
		style = "xbox"
		for device in Input.get_connected_joypads():
			var name := Input.get_joy_name(device).to_lower()
			if name.contains("dualsense") or name.contains("dualshock") or name.contains("playstation") or name.contains("ps4") or name.contains("ps5") or name.contains("sony"):
				style = "ps"
	glyph_style = style
	refresh_hints()


func _input(event: InputEvent) -> void:
	if passing:
		return
	# which pictures the hints show: the last device used
	var pad := UI.pad_glyphs
	if event is InputEventJoypadButton or (event is InputEventJoypadMotion and absf((event as InputEventJoypadMotion).axis_value) > 0.6):
		pad = true
	elif event is InputEventKey or event is InputEventMouseButton:
		pad = false
	if pad != UI.pad_glyphs:
		UI.pad_glyphs = pad
		refresh_hints()
		if screen != null and shown:
			screen.call("device_changed")
	if not shown:
		# in the game: one key answers the newest invitation, nothing else is taken
		var k := event as InputEventKey
		if k != null and k.pressed and not k.echo and k.physical_keycode == KEY_F2:
			if notices.call("accept_current"):
				get_viewport().set_input_as_handled()
		elif k != null and k.pressed and not k.echo and k.physical_keycode == KEY_F9 and not test_mode():
			handover.call("finish", "key")


func _unhandled_input(event: InputEvent) -> void:
	if passing or not shown:
		return
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		back()
		return
	var name := ""
	var joy := event as InputEventJoypadButton
	var key := event as InputEventKey
	if joy != null and joy.pressed:
		match joy.button_index:
			JOY_BUTTON_Y: name = "y"
			JOY_BUTTON_X: name = "x"
			JOY_BUTTON_LEFT_SHOULDER: name = "lb"
			JOY_BUTTON_RIGHT_SHOULDER: name = "rb"
			JOY_BUTTON_START: name = "start"
	elif key != null and key.pressed and not key.echo:
		match key.physical_keycode:
			KEY_Y: name = "y"
			KEY_X: name = "x"
			KEY_Q: name = "lb"
			KEY_E: name = "rb"
			KEY_TAB: name = ""
	if name == "":
		return
	if name == "y":
		if notices.call("accept_current"):
			get_viewport().set_input_as_handled()
		return
	if modal.is_empty() and screen != null and screen.call("handle_shortcut", name):
		get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if passing:
		return
	if screen != null and shown:
		screen.call("tick", delta)
	if starting_since > 0 and Time.get_ticks_msec() - starting_since > (60000 if gameflow.active else 8000):
		starting_since = 0              # the room never said "in game": get out of the way anyway
		handover.call("reveal")
	if session != null:
		var now: Dictionary = session.me() if session.available() else {}
		var link := int(now.get("link", 0)) + String(now.get("problem", "")).hash() * 8
		if link != last_link:
			last_link = link
			if screen != null and shown:
				screen.call("session_changed", "link")
			refresh_hints()
			top.call("build")


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and not passing and (handover == null or handover.get("game") == null):
		if session != null:
			session.close()
		get_tree().quit(0)


# ---- the bar at the top --------------------------------------------------------------------
class TopBar extends Control:
	var portal: Node
	var friends_button: Control
	var settings_button: Control
	var back_button: Control
	var me := {}
	var show_right := true

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func build() -> void:
		if portal == null or portal.get("screen") == null:
			return
		var had := ""
		var owner_now := get_viewport().gui_get_focus_owner() if is_inside_tree() else null
		if owner_now != null and is_ancestor_of(owner_now):
			had = String(owner_now.get("key"))
		for child in get_children():
			remove_child(child)
			child.queue_free()
		friends_button = null
		settings_button = null
		back_button = null
		var scr: Control = portal.get("screen")
		show_right = scr.call("chrome")
		var session: Node = portal.get("session")
		me = session.call("me") if session != null else {}
		if show_right:
			var h := UI.px(56)
			var y := (size.y - h) * 0.5 + UI.px(6)
			var gear := W.Btn.new("", "gear", "ghost")
			gear.height = 56.0
			gear.key = "top_settings"
			add_child(gear)
			gear.position = Vector2(size.x - h, y)
			gear.size = Vector2(h, h)
			gear.activated.connect(func() -> void: portal.call("go", "settings"))
			settings_button = gear
			var online := 0
			for f in session.call("friends"):
				if int(f.presence) > 0:
					online += 1
			var waiting := 0
			for r in session.call("requests"):
				if bool(r.incoming):
					waiting += 1
			waiting += (session.call("invites") as Array).size()
			var fb := W.Btn.new("Friends" if online == 0 else "Friends  %d online" % online, "people", "ghost")
			fb.height = 56.0
			fb.font_size = 19.0
			fb.key = "top_friends"
			if waiting > 0:
				fb.badge = str(waiting)
			add_child(fb)
			fb.size = fb.custom_minimum_size
			fb.position = Vector2(gear.position.x - UI.px(12) - fb.size.x, y)
			fb.activated.connect(func() -> void: portal.call("go", "friends"))
			friends_button = fb
			if (portal.get("stack") as Array).size() > 1:
				var bb := W.Btn.new("Back", "back", "ghost")
				bb.height = 56.0
				bb.font_size = 19.0
				bb.key = "top_back"
				add_child(bb)
				bb.size = bb.custom_minimum_size
				bb.position = Vector2(UI.px(330), y)
				bb.activated.connect(func() -> void: portal.call("back"))
				back_button = bb
		if had != "":
			for child in get_children():
				if String(child.get("key")) == had:
					(child as Control).grab_focus()
		queue_redraw()

	func _draw() -> void:
		# the mark: a small drawn emblem and the game's name set in the portal's own type
		var cy := size.y * 0.5 + UI.px(6)
		var e := UI.px(22)
		var c := Vector2(e + UI.px(2), cy)
		var x := c.x + e + UI.px(14)
		if not UI.skinned("logo", [self, Rect2(0, cy - UI.px(50), UI.px(360), UI.px(96))]):
			draw_colored_polygon(PackedVector2Array([c + Vector2(0, -e), c + Vector2(e * 0.72, 0), c + Vector2(0, e), c + Vector2(-e * 0.72, 0)]), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.16))
			draw_polyline(PackedVector2Array([c + Vector2(0, -e), c + Vector2(e * 0.72, 0), c + Vector2(0, e), c + Vector2(-e * 0.72, 0), c + Vector2(0, -e)]), UI.GOLD, maxf(1.5, UI.px(2)), true)
			draw_line(c + Vector2(0, -e * 0.55), c + Vector2(0, e * 0.55), UI.GOLD_HI, maxf(1.5, UI.px(2.5)), true)
			draw_line(c + Vector2(-e * 0.30, -e * 0.10), c + Vector2(e * 0.30, -e * 0.10), UI.GOLD_HI, maxf(1.5, UI.px(2.5)), true)
			UI.text(self, Rect2(x, cy - UI.px(30), UI.px(300), UI.px(36)), "CHAMPIONS", UI.spaced(UI.serif_bold(), 5.0), 29, UI.GOLD_HI)
			UI.text(self, Rect2(x + UI.px(2), cy + UI.px(6), UI.px(300), UI.px(20)), "RETURN TO ARMS", UI.spaced(UI.bold(), 4.2), 12.5, UI.DIM)
		if not show_right or friends_button == null:
			return
		# me: the name friends see and my code
		var name := String(me.get("name", ""))
		if name == "":
			return
		var right := friends_button.position.x - UI.px(28)
		var av := UI.px(50)
		var code := String(me.get("friend_code", ""))
		var nw := maxf(UI.text_width(name, UI.bold(), 20), UI.text_width(code, UI.spaced(UI.sans(), 1.0), 15)) + UI.px(4)
		nw = minf(nw, UI.px(280))
		var left_limit := (back_button.position.x + back_button.size.x + UI.px(20)) if back_button != null else x + UI.px(300)
		if right - nw - av - UI.px(14) < left_limit:
			return
		W.Avatar.draw_avatar(self, Rect2(right - av, cy - av * 0.5, av, av), name, String(me.get("id", name)), -1)
		var tx := right - av - UI.px(14) - nw
		if code != "":
			UI.text(self, Rect2(tx, cy - UI.px(25), nw, UI.px(28)), name, UI.bold(), 20, UI.TEXT, HORIZONTAL_ALIGNMENT_RIGHT)
			UI.text(self, Rect2(tx, cy + UI.px(3), nw, UI.px(22)), code, UI.spaced(UI.sans(), 1.0), 15, UI.FAINT, HORIZONTAL_ALIGNMENT_RIGHT)
		else:
			UI.text(self, Rect2(tx, cy - UI.px(14), nw, UI.px(28)), name, UI.bold(), 20, UI.TEXT, HORIZONTAL_ALIGNMENT_RIGHT)
		draw_line(Vector2(right + UI.px(14), cy - UI.px(18)), Vector2(right + UI.px(14), cy + UI.px(18)), UI.LINE_STRONG, maxf(1.0, UI.px(1)))
