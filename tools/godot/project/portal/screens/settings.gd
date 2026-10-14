extends "res://portal/screen.gd"
# settings.gd - the settings a player actually needs, in plain words.
#
#   View        the five camera views (the game's own overhead one, a closer one, behind the
#               character, over the shoulder, first person) - tools/recomp/app/fpview.h
#   Display     window or full screen, how sharp the picture is drawn, its shape
#   Sound       volumes
#   Controls    a picture of the controller with what each button is, and the keyboard
#   Interface   the new interface or the game's original one; which button pictures to show
#   You         the name friends see; forgetting everything the service knows about you
#
# Left / right changes a value at once; nothing has to be "applied".

const Session := preload("res://portal/session.gd")
const TABS := [["view", "View", "eye"], ["display", "Display", "screen"], ["sound", "Sound", "speaker"], ["controls", "Controls", "pad"],
	["interface", "Interface", "layers"], ["online", "Online", "people"], ["you", "You", "person"]]
const VIEWS := [
	["overhead", "Overhead", "The classic camera, high above."],
	["action", "Action", "Overhead, closer to the fight."],
	["chase", "Third person", "Behind your character."],
	["shoulder", "Shoulder", "Close, over the right shoulder."],
	["first", "First person", "Through your character's eyes."],
]
const SHARPNESS := ["Fastest (half)", "Fast", "Normal", "Sharp", "Sharpest (double)"]

var tab := "view"
var name_typed := ""
var show_keyboard := false


func hints() -> Array:
	return [{"pad": "dpad", "key": "Arrows", "text": "Change"}, hint_select(), hint_back()]


func build() -> void:
	if args.has("tab") and want_focus == "":
		tab = String(args.tab)
	say(Rect2(0, 0, size.x, UI.px(60)), "Settings", 44, UI.TEXT, UI.serif_bold())
	var tabs_w := UI.px(300)
	var y := UI.px(84)
	for t in TABS:
		var b := W.Btn.new(t[1], t[2], "ghost")
		b.height = 62.0
		b.font_size = 21.0
		b.fixed = true
		b.align_left = true
		b.key = "tab_" + String(t[0])
		b.selected = tab == t[0]
		put(b, Rect2(0, y, tabs_w, UI.px(62)))
		var id := String(t[0])
		b.focus_entered.connect(func() -> void:
			if tab != id:
				tab = id
				want_focus = "tab_" + id
				rebuild.call_deferred())
		y += UI.px(62 + 8)
	var page := Rect2(tabs_w + UI.px(40), UI.px(84), size.x - tabs_w - UI.px(40), size.y - UI.px(84))
	panel_at(page, 18.0)
	var inner := page.grow(-UI.px(28))
	match tab:
		"view": _page_view(inner)
		"display": _page_display(inner)
		"sound": _page_sound(inner)
		"controls": _page_controls(inner)
		"interface": _page_interface(inner)
		"online": _page_online(inner)
		"you": _page_you(inner)
	if want_focus == "":
		want_focus = "tab_" + tab


func _title(r: Rect2, title: String, note: String) -> float:
	say(Rect2(r.position.x, r.position.y, r.size.x, UI.px(40)), title, 30, UI.TEXT, UI.serif_bold())
	if note != "":
		say(Rect2(r.position.x, r.position.y + UI.px(42), r.size.x, UI.px(28)), note, 18, UI.DIM)
	return r.position.y + UI.px(42 + 28 + 22 if note != "" else 60)


func _page_view(r: Rect2) -> void:
	var y := _title(r, "The view", "How you look at the game. In the game, V switches the view as well.")
	var current := String(portal.profile.setting("view"))
	var gap := UI.px(14)
	var per_row := 5 if r.size.x >= UI.px(1040) else 3
	var cw := (r.size.x - gap * (per_row - 1)) / per_row
	var rows := int(ceil(VIEWS.size() / float(per_row)))
	var ch := minf(UI.px(430), (r.end.y - y - gap * (rows - 1)) / rows)
	for k in VIEWS.size():
		var card := ViewCard.new()
		card.view = VIEWS[k][0]
		card.title = VIEWS[k][1]
		card.note = VIEWS[k][2]
		card.chosen = current == VIEWS[k][0]
		card.key = "view_" + String(VIEWS[k][0])
		put(card, Rect2(r.position.x + (k % per_row) * (cw + gap), y + int(k / float(per_row)) * (ch + gap), cw, ch))
		var id := String(VIEWS[k][0])
		card.activated.connect(func() -> void:
			portal.profile.set_setting("view", id)
			portal.handover.call("apply_view", id)
			want_focus = "view_" + id
			rebuild())


func _rows(r: Rect2, y: float, controls: Array) -> void:
	var w := minf(r.size.x, UI.px(980))
	for c in controls:
		var h: float = (c as Control).custom_minimum_size.y
		if h <= 0.0:
			h = UI.px(82)
		put(c, Rect2(r.position.x, y, w, UI.px(82)))
		y += UI.px(82 + 12)


func _page_display(r: Rect2) -> void:
	var y := _title(r, "Display", "")
	var mode := W.Choice.new("Window", PackedStringArray(["In a window", "Full screen"]), 1 if bool(portal.profile.setting("fullscreen")) else 0, "Takes effect at once.")
	mode.key = "fullscreen"
	mode.changed.connect(func(index: int) -> void:
		portal.profile.set_setting("fullscreen", index == 1)
		portal.call("apply_settings"))
	var sharp := W.Choice.new("Sharpness", PackedStringArray(SHARPNESS), clampi(int(portal.profile.setting("sharpness")), 0, 4), "How finely the game is drawn. Lower is faster on an older computer.")
	sharp.key = "sharpness"
	sharp.changed.connect(func(index: int) -> void: portal.profile.set_setting("sharpness", index))
	var shape := W.Choice.new("Picture shape", PackedStringArray(["As in 2005 (4:3)", "Fill the window"]), 1 if bool(portal.profile.setting("wide")) else 0, "Wide shows more of the level to the left and right.")
	shape.key = "wide"
	shape.changed.connect(func(index: int) -> void: portal.profile.set_setting("wide", index == 1))
	_rows(r, y, [mode, sharp, shape])
	say(Rect2(r.position.x, y + UI.px(94 * 3 + 6), minf(r.size.x, UI.px(980)), UI.px(28)), "Sharpness and shape are used from the next time the game starts.", 16, UI.FAINT)


func _page_sound(r: Rect2) -> void:
	var y := _title(r, "Sound", "")
	var all := W.Gauge.new("Everything", float(portal.profile.setting("volume")))
	all.key = "volume"
	all.changed.connect(func(v: float) -> void:
		portal.profile.set_setting("volume", v)
		portal.call("apply_settings"))
	var music := W.Gauge.new("Music", float(portal.profile.setting("music")))
	music.key = "music"
	music.changed.connect(func(v: float) -> void: portal.profile.set_setting("music", v))
	var effects := W.Gauge.new("Effects and voices", float(portal.profile.setting("effects")))
	effects.key = "effects"
	effects.changed.connect(func(v: float) -> void: portal.profile.set_setting("effects", v))
	_rows(r, y, [all, music, effects])


func _page_controls(r: Rect2) -> void:
	var y := _title(r, "Controls", "Any controller works as soon as it is plugged in. The game still says Cross, Circle, Square, Triangle: this is which is which.")
	var which := W.Choice.new("Show", PackedStringArray(["Controller", "Keyboard and mouse"]), 1 if show_keyboard else 0)
	which.key = "controls_which"
	put(which, Rect2(r.position.x, y, minf(r.size.x, UI.px(620)), UI.px(64)))
	which.changed.connect(func(index: int) -> void:
		show_keyboard = index == 1
		want_focus = "controls_which"
		rebuild())
	y += UI.px(64 + 16)
	var pic := Controls.new()
	pic.keyboard = show_keyboard
	pic.style = String(portal.glyph_style)
	put(pic, Rect2(r.position.x, y, r.size.x, r.end.y - y))


func _page_interface(r: Rect2) -> void:
	var y := _title(r, "Interface", "")
	var kind := W.Choice.new("In the game", PackedStringArray(["The new interface", "The original (2005)"]), 0 if String(portal.profile.setting("interface")) == "new" else 1,
		"New: clean bars, markers and numbers. Original: the game's own, as it was.")
	kind.key = "interface"
	kind.changed.connect(func(index: int) -> void: portal.profile.set_setting("interface", "new" if index == 0 else "original"))
	var glyphs := ["auto", "xbox", "ps"]
	var pics := W.Choice.new("Button pictures", PackedStringArray(["Match my controller", "A  B  X  Y", "Cross  Circle  Square  Triangle"]), maxi(0, glyphs.find(String(portal.profile.setting("glyphs")))),
		"Which names the hints at the bottom use.")
	pics.key = "glyphs"
	pics.changed.connect(func(index: int) -> void:
		portal.profile.set_setting("glyphs", glyphs[index])
		portal.call("_detect_pad_style"))
	_rows(r, y, [kind, pics])


var address_typed := ""


func _page_online(r: Rect2) -> void:
	var me: Dictionary = portal.session.me()
	var link := int(me.get("link", 0))
	var problem := String(me.get("problem", ""))
	var sentence := ""
	match link:
		Session.LINK_ONLINE:
			sentence = "Connected to " + String(me.get("service", "the service")) + "."
		Session.LINK_CONNECTING:
			sentence = ("Connecting to " + String(me.get("service", "the service")) + "...") if problem == "" else problem.trim_suffix(".") + " - trying again."
		_:
			sentence = problem if problem != "" else "Not connected."
	var y := _title(r, "Online", "")
	var w := minf(r.size.x, UI.px(860))
	var mark := say(Rect2(r.position.x, y, w, UI.px(40)), sentence, 24, UI.GREEN if link == Session.LINK_ONLINE else (UI.GOLD if link == Session.LINK_CONNECTING and problem == "" else UI.TEXT))
	mark.clip_text = true
	y += UI.px(40 + 6)
	say(Rect2(r.position.x, y, w, UI.px(28)), "Where friends meet: the address of the service, as the one who runs it gave it to you.", 18, UI.DIM)
	y += UI.px(28 + 18)
	if address_typed == "":
		address_typed = String(portal.call("service_named"))
	var field := W.Field.new("host:port, like 192.168.1.20:41900", 63)
	field.key = "address"
	field.height = 64.0
	field.text = address_typed
	put(field, Rect2(r.position.x, y, w - UI.px(230), UI.px(64)))
	field.edited.connect(func(t: String) -> void: address_typed = t)
	field.submitted.connect(func(_t: String) -> void: _connect())
	field.wants_keys.connect(func() -> void:
		ask_text({"title": "The service's address", "mode": "name", "text": address_typed, "max": 63, "done_text": "Connect",
			"done": func(t: String) -> void:
				address_typed = t
				_connect()}))
	var go_btn := W.Btn.new("Connect", "check", "primary")
	go_btn.key = "connect"
	go_btn.height = 64.0
	go_btn.fixed = true
	put(go_btn, Rect2(r.position.x + w - UI.px(216), y, UI.px(216), UI.px(64)))
	go_btn.activated.connect(_connect)
	y += UI.px(64 + 24)
	say(Rect2(r.position.x, y, w, UI.px(54)), "Nothing else is needed: no account and no password. Playing alone never needs the connection.", 16, UI.FAINT, null, HORIZONTAL_ALIGNMENT_LEFT, true)


func _connect() -> void:
	var a := address_typed.strip_edges()
	if a != "" and not a.contains(":"):
		portal.call("toast", "An address ends in a port: host:port", "error")
		return
	portal.call("set_service", a)
	portal.call("toast", "Connecting to " + a if a != "" else "No service named", "info")


func _page_you(r: Rect2) -> void:
	var me: Dictionary = portal.session.me()
	var y := _title(r, "You", "The name your friends see. It is only a label - change it whenever you like.")
	if name_typed == "":
		name_typed = String(portal.profile.name_shown())
	var w := minf(r.size.x, UI.px(760))
	var field := W.Field.new("Your name", 24)
	field.key = "name"
	field.height = 64.0
	field.text = name_typed
	put(field, Rect2(r.position.x, y, w - UI.px(210), UI.px(64)))
	field.edited.connect(func(t: String) -> void: name_typed = t)
	field.submitted.connect(func(_t: String) -> void: _save_name())
	field.wants_keys.connect(func() -> void:
		ask_text({"title": "What should friends call you?", "mode": "name", "text": name_typed, "max": 24, "done_text": "Save",
			"done": func(t: String) -> void:
				name_typed = t
				_save_name()}))
	var save := W.Btn.new("Save", "check", "primary")
	save.key = "save_name"
	save.height = 64.0
	save.fixed = true
	put(save, Rect2(r.position.x + w - UI.px(196), y, UI.px(196), UI.px(64)))
	save.activated.connect(_save_name)
	y += UI.px(64 + 34)
	say(Rect2(r.position.x, y, w, UI.px(24)), "YOUR FRIEND CODE", 14, UI.GOLD, UI.spaced(UI.bold(), 2.5))
	y += UI.px(26)
	var code := String(me.get("friend_code", ""))
	say(Rect2(r.position.x, y, w, UI.px(56)), code if code != "" else "You get one as soon as you are online.", 40 if code != "" else 20, UI.GOLD_HI if code != "" else UI.DIM, UI.spaced(UI.bold(), 4.0) if code != "" else null)
	y += UI.px(56 + 10)
	say(Rect2(r.position.x, y, w, UI.px(56)), "There is no account and no password. This computer holds a key that says it is you; to move to another computer, copy the file net2-identity.key from the game's data folder.",
		16, UI.FAINT, null, HORIZONTAL_ALIGNMENT_LEFT, true)
	y += UI.px(56 + 30)
	var forget := W.Btn.new("Forget me online", "cross", "danger")
	forget.key = "forget"
	forget.height = 56.0
	forget.font_size = 19.0
	forget.set_disabled(not portal.session.available())
	add_child(forget)
	forget.size = forget.custom_minimum_size
	forget.position = Vector2(r.position.x, y)
	forget.activated.connect(func() -> void:
		portal.call("confirm", "Forget you online?", "Your name, your friends list, requests and blocks are deleted from the service, and this computer gets a new identity. Your characters are not touched.",
			"Delete everything", func() -> void: portal.session.delete_everything(), true))


func _save_name() -> void:
	var t := name_typed.strip_edges()
	if t.to_utf8_buffer().size() < 3 or t.to_utf8_buffer().size() > 24:
		portal.call("toast", "A name has 3 to 24 characters", "error")
		return
	portal.call("set_name_shown", t)
	portal.call("toast", "Friends now see you as " + t, "good")


func session_changed(what: String) -> void:
	if (tab == "you" or tab == "online") and (what == "me" or what == "link"):
		rebuild()


# ---- a camera view, drawn as a small diagram --------------------------------------------------
class ViewCard extends W.Focusable:
	var view := "overhead"
	var title := ""
	var note := ""
	var chosen := false

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(14)
		var e := eased()
		if pressed_t > 0.0:
			r = r.grow(-UI.px(3) * pressed_t)
		UI.focus_glow(self, r, radius, e)
		draw_style_box(UI.box(radius, UI.PANEL_UP.lerp(UI.PANEL_HOT, e), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.75) if chosen else UI.LINE, maxf(1.0, UI.px(2 if chosen else 1))), r)
		UI.focus_ring(self, r, radius, e)
		var pad := UI.px(14)
		var text_h := UI.px(84)
		var d := Rect2(r.position.x + pad, r.position.y + pad, r.size.x - pad * 2.0, r.size.y - text_h - pad)
		draw_style_box(UI.box(UI.px(10), Color(0.02, 0.024, 0.036, 0.8)), d)
		_diagram(d.grow(-UI.px(10)))
		var ty := r.end.y - text_h
		UI.text(self, Rect2(r.position.x + pad, ty + UI.px(8), r.size.x - pad * 2.0 - (UI.px(30) if chosen else 0.0), UI.px(32)), title, UI.bold(), 22, UI.GOLD_HI if chosen else UI.TEXT)
		var para := TextParagraph.new()
		para.add_string(note, UI.sans(), UI.fs(15))
		para.width = r.size.x - pad * 2.0
		para.max_lines_visible = 2
		para.draw(get_canvas_item(), Vector2(r.position.x + pad, ty + UI.px(40)), UI.DIM)
		if chosen:
			var isz := UI.px(22)
			UI.icon(self, "check", Rect2(r.end.x - pad - isz, ty + UI.px(12), isz, isz), UI.GOLD_HI)

	func _diagram(d: Rect2) -> void:
		# a side view: the ground, a figure, and where the camera is, with what it sees
		var ground := d.position.y + d.size.y * 0.80
		var gcol := Color(1, 1, 1, 0.22)
		draw_line(Vector2(d.position.x, ground), Vector2(d.end.x, ground), gcol, maxf(1.0, UI.px(1.5)))
		var u := minf(d.size.x, d.size.y * 1.2)
		var fig := Vector2(d.position.x + d.size.x * 0.62, ground)
		var fh := u * 0.26
		var fcol := UI.TEXT
		var hidden := view == "first"
		if hidden:
			fcol = Color(1, 1, 1, 0.28)
		draw_circle(fig + Vector2(0, -fh), fh * 0.19, fcol, true, -1.0, true)
		draw_colored_polygon(PackedVector2Array([fig + Vector2(-fh * 0.20, -fh * 0.76), fig + Vector2(fh * 0.20, -fh * 0.76), fig + Vector2(fh * 0.28, 0), fig + Vector2(-fh * 0.28, 0)]), fcol)
		var cam := fig
		var target := fig + Vector2(0, -fh * 0.5)
		match view:
			"overhead":
				cam = fig + Vector2(-u * 0.30, -u * 0.62)
			"action":
				cam = fig + Vector2(-u * 0.24, -u * 0.40)
			"chase":
				cam = fig + Vector2(-u * 0.42, -fh * 1.35)
				target = fig + Vector2(u * 0.10, -fh * 0.7)
			"shoulder":
				cam = fig + Vector2(-fh * 0.75, -fh * 1.12)
				target = fig + Vector2(u * 0.26, -fh * 0.8)
			"first":
				cam = fig + Vector2(fh * 0.10, -fh)
				target = fig + Vector2(u * 0.30, -fh * 0.95)
		var dir := (target - cam).normalized()
		var side := Vector2(-dir.y, dir.x)
		var reach := u * 0.9
		var spread := 0.30
		var a := cam + (dir + side * spread).normalized() * reach
		var b := cam + (dir - side * spread).normalized() * reach
		# cut the cone at the ground and at the diagram's edge
		a.y = minf(a.y, ground)
		b.y = minf(b.y, ground)
		a.x = clampf(a.x, d.position.x, d.end.x)
		b.x = clampf(b.x, d.position.x, d.end.x)
		draw_polygon(PackedVector2Array([cam, a, b]), PackedColorArray([Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.42), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.0), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.0)]))
		# the camera: a small body turned along its view
		draw_set_transform(cam, dir.angle(), Vector2.ONE)
		var cs := u * 0.055
		draw_rect(Rect2(-cs * 1.2, -cs * 0.8, cs * 1.8, cs * 1.6), UI.GOLD_HI)
		draw_colored_polygon(PackedVector2Array([Vector2(cs * 0.6, 0), Vector2(cs * 1.5, -cs * 0.8), Vector2(cs * 1.5, cs * 0.8)]), UI.GOLD_HI)
		draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


# ---- the controller and the keyboard ----------------------------------------------------------
class Controls extends Control:
	var keyboard := false
	var style := "xbox"
	# what the game calls it, the key, what it does (only where that is established)
	const MAP := [
		["ls", "Left stick", "W A S D", "Move"],
		["dpad", "Direction pad", "Arrow keys", ""],
		["back", "Select", "Backspace", ""],
		["lb", "L1", "Q", ""],
		["lt", "L2", "1", "Mana potion"],
		["rt", "R2", "3", "Health potion"],
		["rb", "R1", "E", ""],
		["y", "Triangle", "I", ""],
		["x", "Square", "J", ""],
		["b", "Circle", "L", ""],
		["a", "Cross", "K", "Attack"],
		["rs", "Right stick", "Mouse (first person)", "Turn the camera, look"],
		["start", "Start", "Enter", "Pause, menu"],
	]

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		if keyboard:
			_draw_keys()
		else:
			_draw_pad()

	func _draw_keys() -> void:
		var cols := 2
		var gap := UI.px(12)
		var cw := minf((size.x - gap) / cols, UI.px(560))
		var rh := minf(UI.px(54), (size.y - UI.px(8)) / 7.0 - gap * 0.5)
		var rows := int(ceil((MAP.size() + 1) / float(cols)))
		var all := MAP.duplicate()
		all.append(["v", "Next view", "V", "Switch the camera view"])
		for k in all.size():
			var m: Array = all[k]
			var col := int(k / float(rows))
			var row := k % rows
			var r := Rect2(col * (cw + gap), row * (rh + gap * 0.6), cw, rh)
			draw_style_box(UI.box(UI.px(10), Color(1, 1, 1, 0.035), UI.LINE, 1), r)
			var cap := String(m[2])
			var capw := maxf(UI.px(64), UI.text_width(cap, UI.bold(), 16) + UI.px(24))
			var crect := Rect2(r.position.x + UI.px(10), r.position.y + (rh - UI.px(34)) * 0.5, capw, UI.px(34))
			draw_style_box(UI.box(UI.px(7), Color(1, 1, 1, 0.08), Color(1, 1, 1, 0.26), 1), crect)
			UI.text(self, crect, cap, UI.bold(), 16, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
			var x := crect.end.x + UI.px(16)
			var what := String(m[3]) if String(m[3]) != "" else String(m[1])
			var w := UI.text(self, Rect2(x, r.position.y, r.end.x - x - UI.px(10), rh), what, UI.bold(), 18, UI.TEXT)
			if String(m[3]) != "" and String(m[0]) != "v":
				UI.text(self, Rect2(x + w + UI.px(12), r.position.y, r.end.x - x - w - UI.px(22), rh), String(m[1]), UI.sans(), 16, UI.FAINT)

	func _draw_pad() -> void:
		var label_w := minf(UI.px(330), size.x * 0.30)
		var pw := minf(size.x - label_w * 2.0 - UI.px(60), size.y * 1.55)
		pw = maxf(pw, UI.px(260))
		var ph := pw * 0.62
		var pr := Rect2((size.x - pw) * 0.5, maxf(UI.px(20), (size.y - ph) * 0.42), pw, ph)
		UI.pad_shape(self, pr, Color(0.11, 0.125, 0.17, 0.95), Color(1, 1, 1, 0.30), maxf(1.5, UI.px(2)))
		var p := func(x: float, y: float) -> Vector2: return pr.position + Vector2(x * pr.size.x, y * pr.size.y)
		var at := {
			"ls": p.call(0.265, 0.33), "dpad": p.call(0.375, 0.52), "rs": p.call(0.625, 0.52),
			"y": p.call(0.735, 0.21), "x": p.call(0.675, 0.32), "b": p.call(0.795, 0.32), "a": p.call(0.735, 0.43),
			"back": p.call(0.44, 0.27), "start": p.call(0.56, 0.27),
			"lb": p.call(0.28, 0.075), "rb": p.call(0.72, 0.075), "lt": p.call(0.22, 0.02), "rt": p.call(0.78, 0.02),
		}
		var u := pr.size.x
		var soft := Color(1, 1, 1, 0.16)
		var hard := Color(1, 1, 1, 0.55)
		# sticks
		for name in ["ls", "rs"]:
			draw_circle(at[name], u * 0.062, Color(0, 0, 0, 0.45), true, -1.0, true)
			draw_arc(at[name], u * 0.062, 0.0, TAU, 32, hard, maxf(1.5, UI.px(2)), true)
			draw_circle(at[name], u * 0.036, soft, true, -1.0, true)
		# direction pad
		var dp: Vector2 = at["dpad"]
		var arm := u * 0.05
		var thick := u * 0.032
		draw_style_box(UI.box(thick * 0.3, soft, hard, 1), Rect2(dp.x - arm, dp.y - thick * 0.5, arm * 2.0, thick))
		draw_style_box(UI.box(thick * 0.3, soft, hard, 1), Rect2(dp.x - thick * 0.5, dp.y - arm, thick, arm * 2.0))
		# the four face buttons
		for name in ["a", "b", "x", "y"]:
			var rad := u * 0.034
			W.Hints.draw_glyph(self, Rect2((at[name] as Vector2) - Vector2(rad, rad), Vector2(rad, rad) * 2.0), name, style)
		# start, select
		for name in ["back", "start"]:
			draw_style_box(UI.box(u * 0.012, soft, hard, 1), Rect2((at[name] as Vector2) - Vector2(u * 0.026, u * 0.012), Vector2(u * 0.052, u * 0.024)))
		# shoulders and triggers
		for name in ["lb", "rb"]:
			draw_style_box(UI.box(u * 0.014, soft, hard, 1), Rect2((at[name] as Vector2) - Vector2(u * 0.075, u * 0.016), Vector2(u * 0.15, u * 0.032)))
		for name in ["lt", "rt"]:
			draw_style_box(UI.box(u * 0.016, soft, hard, 1), Rect2((at[name] as Vector2) - Vector2(u * 0.045, u * 0.034), Vector2(u * 0.09, u * 0.05)))
		# the labels: left column and right column, a line from each to its button
		# labels in the order that keeps their lines apart; Select and Start sit under the controller
		_labels(["lt", "lb", "ls", "dpad"], at, true, pr, label_w)
		_labels(["rt", "rb", "y", "b", "x", "a", "rs"], at, false, pr, label_w)
		var bw := minf(UI.px(250), pr.size.x * 0.34)
		var by := minf(pr.end.y - UI.px(40), size.y - UI.px(46))
		for name in ["back", "start"]:
			var m: Array = []
			for row in MAP:
				if row[0] == name:
					m = row
			var to: Vector2 = at[name]
			var bx := to.x - bw - UI.px(6) if name == "back" else to.x + UI.px(6)
			var r := Rect2(bx, by, bw, UI.px(46))
			draw_polyline(PackedVector2Array([to, Vector2(to.x, by)]), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.45), maxf(1.0, UI.px(1.5)), true)
			draw_circle(to, maxf(2.0, UI.px(3.5)), UI.GOLD, true, -1.0, true)
			draw_style_box(UI.box(UI.px(9), Color(0.07, 0.08, 0.11, 0.96), UI.LINE_STRONG, 1), r)
			var what := String(m[3]) if String(m[3]) != "" else String(m[1])
			var w := UI.text(self, Rect2(r.position.x + UI.px(12), r.position.y, r.size.x - UI.px(24), r.size.y), what, UI.bold(), 17, UI.TEXT)
			if String(m[3]) != "":
				UI.text(self, Rect2(r.position.x + UI.px(22) + w, r.position.y, r.size.x - UI.px(34) - w, r.size.y), String(m[1]), UI.sans(), 15, UI.FAINT)

	func _labels(names: Array, at: Dictionary, on_left: bool, pr: Rect2, label_w: float) -> void:
		var rh := minf(UI.px(52), (size.y - UI.px(8)) / names.size())
		var total := rh * names.size()
		var top := clampf(pr.position.y + pr.size.y * 0.45 - total * 0.5, 0.0, maxf(0.0, size.y - total))
		for k in names.size():
			var name: String = names[k]
			var m: Array = []
			for row in MAP:
				if row[0] == name:
					m = row
			var r := Rect2(0.0 if on_left else size.x - label_w, top + k * rh, label_w, rh - UI.px(6))
			draw_style_box(UI.box(UI.px(9), Color(1, 1, 1, 0.035), UI.LINE, 1), r)
			var what := String(m[3]) if String(m[3]) != "" else String(m[1])
			var sub := String(m[1]) if String(m[3]) != "" else ""
			var w := UI.text(self, Rect2(r.position.x + UI.px(12), r.position.y, r.size.x - UI.px(24), r.size.y), what, UI.bold(), 17, UI.TEXT)
			if sub != "":
				UI.text(self, Rect2(r.position.x + UI.px(22) + w, r.position.y, r.size.x - UI.px(34) - w, r.size.y), sub, UI.sans(), 15, UI.FAINT)
			var from := Vector2(r.end.x if on_left else r.position.x, r.position.y + r.size.y * 0.5)
			var to: Vector2 = at[name]
			if name in ["a", "b", "x", "y"]:
				to += Vector2(pr.size.x * 0.034, 0)     # the edge of the button: its letter stays readable
			var elbow := Vector2(from.x + (UI.px(22) if on_left else -UI.px(22)), from.y)
			draw_polyline(PackedVector2Array([from, elbow, to]), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.45), maxf(1.0, UI.px(1.5)), true)
			draw_circle(to, maxf(2.0, UI.px(3.5)), UI.GOLD, true, -1.0, true)
