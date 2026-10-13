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
	for name in ["smoke", "walk", "states", "friends", "room", "join", "settings", "ratios", "real"]:
		if only.is_empty() and (name == "smoke" or name == "real"):
			continue
		if only.is_empty() or only.has(name):
			print("shots: ", name)
			await call("scenario_" + name)
	print("shots: %d pictures in %s" % [count, out_dir])
	if portal != null and portal.handover.quit_game():
		return                          # the real game scene stops its machine and ends the program itself
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
	await wait(0.3)
	if bool(o.mock) and portal.session.available():
		await until(func() -> bool: return portal.session.online() and not portal.session.friends().is_empty())
		await wait(0.1)


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
	# the mouse: pointing gives the focus, a click presses
	var tile: Control = portal.screen.find_key(portal.screen, "friends")
	var at := tile.global_position + tile.size * 0.5
	var move := InputEventMouseMotion.new()
	move.position = at
	move.global_position = at
	await send(move)
	await wait(0.1)
	print("shots: mouse over the friends tile, focus ", focused())
	for down in [true, false]:
		var click := InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.pressed = down
		click.position = at
		click.global_position = at
		await send(click)
	await wait(0.4)
	print("shots: after the click the screen is ", portal.current_name(), "; hints for ", "a controller" if UI.pad_glyphs else "keyboard and mouse")
	await key(KEY_ESCAPE)
	await wait(0.3)
	print("shots: after Esc the screen is ", portal.current_name())


# What the portal "remembers" in most pictures: a name and a few characters.  The names are
# made up here; the classes are whatever the session's friends play (text from the session,
# none of it stored in this file).
func remembered(extra := {}) -> Dictionary:
	var d := {"name": "Tester", "character": {"name": "Aldric Vane", "cls": "", "level": 27},
		"known": [{"name": "Mirelle", "cls": "", "level": 14}, {"name": "Old Harrow", "cls": "", "level": 41}, {"name": "Tam", "cls": "", "level": 3}]}
	d.merge(extra, true)
	return d


func give_classes() -> void:
	# the remembered characters get classes from what the session's friends play
	var classes: Array = []
	for f in portal.session.friends():
		var cls := String(f.character.get("cls", ""))
		if cls != "" and not classes.has(cls):
			classes.append(cls)
	if classes.is_empty():
		return
	var c: Dictionary = portal.profile.character()
	if String(c.get("name", "")) != "":
		c["cls"] = classes[0]
		portal.profile.set_character(c)
	var known: Array = portal.profile.known_characters()
	for k in known.size():
		known[k]["cls"] = classes[(k + 1) % classes.size()]
	portal.profile.cfg.set_value("character", "known", known)
	portal.profile.save()
	portal.session.set_character(portal.profile.character())
	portal.screen.rebuild()
	await get_tree().process_frame


func open_ready(size: Vector2i, extra := {}, options := {}) -> void:
	await open_portal(size, remembered(extra), options)
	await give_classes()


func many_friends(count: int, long_names := false) -> Array:
	# a list longer than the mock's, built from its friends (their classes, levels, places)
	var base: Array = portal.session.n.call("friends")
	var names := ["Ashgrove", "bittern", "Calloway", "dune_runner", "Eskil", "FennMoor", "Greywick", "hollowbrook", "Isolde K", "Jory", "Kestrel", "Lunn",
		"Marrow", "nightjar", "Orrin", "Pell", "Quillon", "Rook", "Sable", "Thistle", "Umber", "Vesper", "Wick", "Yarrow", "Zephyr", "Alder", "Brindle", "Corvin",
		"Dapple", "Ember", "Flint", "Gorse", "Heron", "Ilex", "Juniper", "Knot", "Larch", "Moss", "Nettle", "Osier"]
	var heroes := ["Aldous", "Brenna", "Caius", "Delphine", "Edrik", "Fiora", "Garrick", "Hesper", "Ingram", "Jessamy"]
	var out: Array = []
	for k in count:
		var b: Dictionary = (base[k % base.size()] as Dictionary).duplicate(true)
		b["id"] = "%032x" % (0x5000 + k)
		b["name"] = names[k % names.size()]
		b["character"]["name"] = heroes[k % heroes.size()] + (" the " + ["Bold", "Quiet", "Younger", "Grey"][k % 4] if k % 3 == 0 else "")
		b["character"]["level"] = 1 + (k * 7) % 50
		b["presence"] = [3, 2, 1, 1, 0, 3, 2, 0, 1, 0][k % 10] if count > 8 else [3, 3, 2, 2, 1, 1, 0, 0][k % 8]
		b["joinable"] = int(b.presence) == 2 and k % 2 == 0
		b["room_players"] = 2 + k % 3 if int(b.presence) >= 2 else 0
		if int(b.presence) == 3 and String(b.level) == "":
			for other in base:              # a level's name as the session has it for somebody
				if String(other.level) != "":
					b["level"] = other.level
		b["last_seen"] = int(Time.get_unix_time_from_system()) - 3600 * (1 + k * 5)
		b["invited_me"] = false
		if long_names and k % 2 == 0:
			b["name"] = ["WWWWWWWWWWWWWWWWWWWWWWWW", "The Longest Name Allowed", "xX_twentyfour_letters_Xx", "Bartholomew-Maximilian 3"][int(k / 2.0) % 4]
			b["character"]["name"] = "Maximiliana Thunderbrow"
		out.append(b)
	out.sort_custom(func(a: Dictionary, c: Dictionary) -> bool: return int(a.presence) > int(c.presence) if int(a.presence) != int(c.presence) else String(a.name).naturalnocasecmp_to(String(c.name)) < 0)
	return out


# The scripted walk-through, with a controller: first start -> the name -> home -> host ->
# a friend walks in -> ready -> start -> the game -> back in the room.
func scenario_walk() -> void:
	await open_portal(Vector2i(1920, 1080), {"pad": true}, {"mock_speed": "2"})
	await shot("walk-01-first-start")
	await pad_type("Tester")
	await shot("walk-02-name-typed")
	await pad(JOY_BUTTON_START)
	await wait(0.4)
	await shot("walk-03-home")
	await pad(JOY_BUTTON_DPAD_DOWN)
	print("shots: walk focus ", focused())
	await shot("walk-04-home-host")
	await pad(JOY_BUTTON_A)
	await until(func() -> bool: return int(portal.session.room().state) == 2)
	await shot("walk-05-room-open")
	await until(func() -> bool: return int(portal.session.room().count) >= 2)
	await shot("walk-06-friend-walked-in")
	await until(func() -> bool: return int(portal.session.room().count) >= 2 and bool(portal.session.room().members[1].ready))
	await shot("walk-07-friend-ready")
	await until(func() -> bool: return int(portal.session.room().count) >= 3 and bool(portal.session.room().all_ready))
	await shot("walk-08-everybody-ready")
	print("shots: walk focus in room ", focused())
	portal.session.setting("mock-speed", "0.7")
	await focus_key("main")
	await pad(JOY_BUTTON_A)
	await wait(0.2)
	await shot("walk-09-starting")
	await until(func() -> bool: return portal.session.room().members.size() > 1 and int(portal.session.room().members[1].route) >= 2)
	await shot("walk-10-starting-connected")
	portal.session.setting("mock-speed", "6")
	await until(func() -> bool: return not portal.shown)
	await wait(0.4)
	await shot("walk-11-in-the-game")
	await until(func() -> bool: return portal.shown, 20.0)
	await wait(0.4)
	print("shots: walk focus back in room ", focused())
	await shot("walk-12-back-in-the-room")


func until(condition: Callable, most := 12.0) -> void:
	var t := 0.0
	while t < most and not condition.call():
		await get_tree().create_timer(0.05).timeout
		t += 0.05
	if t >= most:
		print("shots: WAITED IN VAIN (", most, " s)")


func scenario_states() -> void:
	# the disc image has not been found: the sentence and its button, and home with the strip
	await open_portal(Vector2i(1920, 1080), {"name": "Tester"}, {"stub_game": false, "mock_speed": "0.2"})
	await shot("state-home-no-disc-no-character")
	await focus_key("alone")
	await key(KEY_ENTER)
	await shot("state-disc-missing")
	# offline: no session behind the portal
	await open_portal(Vector2i(1920, 1080), remembered({"character": {"name": "Aldric Vane", "cls": "", "level": 27}}), {"mock": false})
	await shot("state-home-offline")
	portal.go("friends")
	await shot("state-friends-offline")
	# home, with an invitation arriving (the mock's comes 12 s in)
	await open_ready(Vector2i(1920, 1080))
	await shot("state-home")
	await mock(12.0)
	await shot("state-home-invitation")
	UI.pad_glyphs = true
	portal.refresh_hints()
	portal.notices.queue_redraw()
	await shot("state-home-invitation-controller")
	# one press from anywhere: Y joins
	await pad(JOY_BUTTON_Y)
	await mock(1.0)
	await shot("state-invitation-accepted-room")
	# characters
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "0.5"})
	portal.go("characters")
	await shot("state-characters")
	await focus_key("new")
	await key(KEY_ENTER)
	await shot("state-characters-new")
	await key(KEY_ESCAPE)
	# leaving
	portal.home()
	await wait(0.3)
	await key(KEY_ESCAPE)
	await shot("state-quit-question")
	# play alone: the hand-over, and an invitation while the game has the screen
	await open_ready(Vector2i(1920, 1080), {"pad": true})
	await focus_key("alone")
	await pad(JOY_BUTTON_A)
	await wait(0.5)
	await shot("state-in-game")
	await mock(12.0)
	await shot("state-in-game-invitation")
	# the portal in front of the game again: the game's picture blurred and dimmed behind it
	portal.handover.finish("key")
	await wait(0.4)
	await shot("state-home-over-the-game")


func scenario_friends() -> void:
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "0.6"})
	portal.go("friends")
	await shot("friends-six")
	# a controller on a friend who can be joined: A joins, right walks to Invite and More
	UI.pad_glyphs = true
	portal.refresh_hints()
	var joinable := ""
	var in_game := ""
	for f in portal.session.friends():
		if bool(f.joinable) and joinable == "":
			joinable = String(f.id)
		if int(f.presence) == 3 and in_game == "":
			in_game = String(f.id)
	await focus_key("friend:" + joinable)
	await shot("friends-joinable-focused")
	await pad(JOY_BUTTON_DPAD_RIGHT)
	await pad(JOY_BUTTON_DPAD_RIGHT)
	await shot("friends-more-selected")
	await pad(JOY_BUTTON_A)
	await shot("friends-more-menu")
	await pad(JOY_BUTTON_DPAD_DOWN)
	await pad(JOY_BUTTON_A)
	await shot("friends-block-question")
	await pad(JOY_BUTTON_B)
	# a request: accept from the list
	var req := ""
	for r in portal.session.requests():
		if bool(r.incoming):
			req = String(r.id)
	if req != "":
		await focus_key("request:" + req)
		await shot("friends-request-focused")
	# adding a friend by code, with a controller: the letters on screen
	await focus_key("add_code")
	await pad(JOY_BUTTON_A)
	await pad_type_entry("WREN2DGS")
	await shot("friends-add-code-keys")
	await pad(JOY_BUTTON_START)
	await wait(0.4)
	await shot("friends-add-asked")
	UI.pad_glyphs = false
	portal.refresh_hints()
	# no friends yet
	portal.session.friends_for_pictures = []
	for r in portal.session.requests():
		portal.session.friend_decline(String(r.id))
	for v in portal.session.invites():
		portal.session.invite_dismiss(String(v.from_id))
	await wait(0.3)
	portal.screen.rebuild()
	portal.top.build()
	await shot("friends-none-yet")
	# eight, forty, long names
	portal.session.friends_for_pictures = many_friends(8)
	portal.screen.rebuild()
	portal.top.build()
	await shot("friends-eight")
	portal.session.friends_for_pictures = many_friends(40)
	portal.screen.rebuild()
	portal.top.build()
	await shot("friends-forty")
	var rows := (portal.session.friends_for_pictures as Array)
	await focus_key("friend:" + String(rows[22].id))
	await shot("friends-forty-scrolled")
	portal.session.friends_for_pictures = many_friends(8, true)
	portal.screen.rebuild()
	portal.top.build()
	await focus_key("friend:" + String((portal.session.friends_for_pictures as Array)[0].id))
	await shot("friends-long-names")
	portal.session.friends_for_pictures = null


func pad_type_entry(text: String) -> void:
	for ch in text:
		await focus_key("key_" + ch)
		await pad(JOY_BUTTON_A)


func scenario_join() -> void:
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "1"})
	portal.go("join")
	await shot("join-empty")
	await type("nqpe2")
	await shot("join-typed")
	await key(KEY_ENTER)
	await wait(1.2)
	await shot("join-no-such-room")
	for k in 5:
		await key(KEY_BACKSPACE)
	await type("FULL2")
	await key(KEY_ENTER)
	await wait(1.2)
	await shot("join-room-full")
	for k in 5:
		await key(KEY_BACKSPACE)
	await type("LATE2")
	await key(KEY_ENTER)
	await wait(1.2)
	await shot("join-game-started")
	# with a controller: the code's letters on screen
	UI.pad_glyphs = true
	portal.screen.device_changed()
	await wait(0.2)
	for k in 5:
		await pad(JOY_BUTTON_X)
	await pad_type_entry("H4K")
	await shot("join-controller")
	UI.pad_glyphs = false
	portal.screen.device_changed()


func scenario_room() -> void:
	# a guest in somebody's room
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "1"})
	portal.go("join")
	await type("H4KQ7")
	await key(KEY_ENTER)
	await wait(1.5)
	await shot("room-guest")
	await focus_key("chat")
	await type("hello there")
	await key(KEY_ENTER)
	await wait(1.5)
	await shot("room-guest-chat")
	await focus_key("main")
	await key(KEY_ENTER)
	await wait(0.5)
	await shot("room-guest-ready")
	# a member whose game is another version: the warning, and only then
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "1"})
	portal.go("join")
	await type("BADF2")
	await key(KEY_ENTER)
	await wait(1.5)
	await shot("room-different-version")
	# the host: choices, a seat's menu, leaving
	await open_ready(Vector2i(1920, 1080), {"pad": true}, {"mock_speed": "4"})
	portal.host_game()
	await mock(3.6)
	await focus_key("difficulty")
	await pad(JOY_BUTTON_DPAD_RIGHT)
	await shot("room-host-choosing")
	await focus_key("seat1")
	await pad(JOY_BUTTON_A)
	await shot("room-host-seat-menu")
	await pad(JOY_BUTTON_B)
	await pad(JOY_BUTTON_B)
	await shot("room-leave-question")
	await pad(JOY_BUTTON_B)
	await focus_key("chat")
	await pad(JOY_BUTTON_A)
	await pad_type_entry("gg")
	await shot("room-chat-keys")


func scenario_settings() -> void:
	await open_ready(Vector2i(1920, 1080), {}, {"mock_speed": "0.3"})
	for tab in ["view", "display", "sound", "controls", "interface", "you"]:
		portal.stack = [{"name": "home", "args": {}}]
		portal.go("settings", {"tab": tab})
		await shot("settings-" + tab)
	await focus_key("controls_which")
	portal.stack = [{"name": "home", "args": {}}]
	portal.go("settings", {"tab": "controls"})
	await wait(0.3)
	await focus_key("controls_which")
	await key(KEY_RIGHT)
	await shot("settings-controls-keyboard")
	portal.stack = [{"name": "home", "args": {}}]
	portal.go("settings", {"tab": "view"})
	await wait(0.3)
	await focus_key("view_first")
	await key(KEY_ENTER)
	await shot("settings-view-first-person")
	portal.stack = [{"name": "home", "args": {}}]
	portal.go("settings", {"tab": "you"})
	await wait(0.3)
	await focus_key("forget")
	await key(KEY_ENTER)
	await shot("settings-forget-question")


func scenario_ratios() -> void:
	for spec in [[Vector2i(1440, 1080), "4x3"], [Vector2i(1280, 720), "720p"], [Vector2i(2560, 1080), "21x9"], [Vector2i(3840, 2160), "4k"], [Vector2i(1024, 768), "4x3-small"]]:
		await open_ready(spec[0], {}, {"mock_speed": "4"})
		await shot("ratio-%s-home" % spec[1])
		portal.go("friends")
		await shot("ratio-%s-friends" % spec[1])
		portal.home()
		await wait(0.3)
		portal.host_game()
		await mock(6.5)
		await shot("ratio-%s-room" % spec[1])
		portal.stack = [{"name": "home", "args": {}}]
		portal.go("settings", {"tab": "controls"})
		await shot("ratio-%s-settings-controls" % spec[1])
		portal.stack = [{"name": "home", "args": {}}]
		portal.go("settings", {"tab": "view"})
		await shot("ratio-%s-settings-view" % spec[1])
	await open_portal(Vector2i(1440, 1080), {"pad": true})
	await shot("ratio-4x3-first-start")
	await open_portal(Vector2i(1280, 720), {"pad": true})
	await shot("ratio-720p-first-start")


# The portal in front of the REAL game scene (res://main.tscn with the game library): asked for
# by name only, with the game scene's own options on the command line (--disc, --test, --mute,
# --size, --data, --workspace).  The pictures hold the game's picture: they stay under local/.
func scenario_real() -> void:
	await open_ready(Vector2i(1920, 1080), {}, {"stub_game": false, "mock_speed": "1"})
	await shot("real-01-home-before")
	await focus_key("alone")
	await key(KEY_ENTER)
	await wait(1.0)
	print("shots: real: game node ", portal.handover.game, " started ", portal.handover.game.get("started") if portal.handover.game != null else null,
		" message ", portal.handover.game.get("message") if portal.handover.game != null else "")
	await wait(9.0)
	await shot("real-02-the-game-after-the-hand-over")
	await until(func() -> bool: return not portal.notices.current().is_empty(), 14.0)
	await wait(0.3)
	await shot("real-03-invitation-over-the-game")
	portal.handover.finish("key")
	await wait(0.5)
	await shot("real-04-portal-in-front-of-the-game")
	portal.go("friends")
	await shot("real-05-friends-in-front-of-the-game")
	print("shots: real: blanks ", portal.handover.game.get("blanks"))
