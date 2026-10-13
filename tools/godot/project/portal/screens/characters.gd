extends "res://portal/screen.gd"
# characters.gd - pick another of the saved characters, or make a new one.
#
# The list is what is known on this computer: the characters the portal has seen being
# played (read from the game's own state while it runs) and those the session can read
# from the memory card (session.h, net2_local_characters).  Making a character stays the
# game's own screen for now: the portal hands over to it and is back afterwards.


func hints() -> Array:
	return [hint_select("Play this one"), hint_back()]


func card_dir() -> String:
	var args := OS.get_cmdline_user_args()
	var at := args.find("--data")
	if at >= 0 and at + 1 < args.size():
		return args[at + 1]
	return ProjectSettings.globalize_path("user://data")


func all_characters() -> Array:
	var list: Array = []
	var seen := {}
	for c in portal.session.local_characters(card_dir()) + portal.profile.known_characters():
		var name := String(c.get("name", ""))
		if name != "" and not seen.has(name):
			seen[name] = true
			list.append(c)
	return list


func build() -> void:
	var list := all_characters()
	var current := String(portal.profile.character().get("name", ""))
	say(Rect2(0, 0, size.x, UI.px(60)), "Your characters", 44, UI.TEXT, UI.serif_bold())
	say(Rect2(0, UI.px(58), size.x, UI.px(30)), "The one you choose is the one your friends see you with." if not list.is_empty() else "None yet - make your first one.", 20, UI.DIM)
	var top := UI.px(108)
	var gap := UI.px(18)
	var most := clampi(int((size.x + gap) / UI.px(300)), 3, 6)
	var cols := clampi(list.size() + 1, mini(4, most), most)
	var cw := (size.x - gap * (cols - 1)) / cols
	var rows := int(ceil((list.size() + 1) / float(cols)))
	var ch := minf(UI.px(430), (size.y - top - gap * (rows - 1)) / maxf(rows, 1))
	ch = maxf(ch, UI.px(250))
	var holder: Control = self
	var need := rows * ch + (rows - 1) * gap
	if need > size.y - top + 1.0:
		# more than fits: the grid scrolls
		var box := scroller(Rect2(-UI.px(8), top - UI.px(8), size.x + UI.px(16), size.y - top + UI.px(8)), 0.0)
		holder = Control.new()
		holder.custom_minimum_size = Vector2(size.x, need)
		holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(holder)
		top = 0.0
	for k in list.size() + 1:
		var card := Card.new()
		var r := Rect2((k % cols) * (cw + gap), top + int(k / float(cols)) * (ch + gap), cw, ch)
		if k < list.size():
			var c: Dictionary = list[k]
			card.character = c
			card.current = String(c.get("name", "")) == current
			card.key = "char:" + String(c.get("name", ""))
			card.activated.connect(func() -> void:
				portal.call("choose_character", c)
				portal.call("toast", "Playing %s" % String(c.get("name", "")), "good")
				portal.call("back"))
			if card.current and want_focus == "":
				want_focus = card.key
		else:
			card.key = "new"
			card.activated.connect(_new)
		holder.add_child(card)
		card.position = r.position.round()
		card.size = r.size.round()
		card.build()


func _new() -> void:
	portal.call("confirm", "Make a new character", "Characters are made in the game's own screen. The game opens there now - when you are done you are back here.", "Open the game",
		func() -> void:
			if not portal.call("need_disc"):
				portal.handover.call("start", {"kind": "create"}))


class Card extends W.Focusable:
	var character := {}
	var current := false
	var portrait: Control

	func build() -> void:
		if character.is_empty():
			return
		portrait = W.Portrait.new()
		portrait.character = character
		portrait.framed = false
		portrait.set_process(true)
		add_child(portrait)
		var pad := UI.px(10)
		portrait.position = Vector2(pad, pad)
		portrait.size = Vector2(size.x - pad * 2.0, maxf(UI.px(40), size.y - UI.px(108) - pad))
		var over := CardText.new()
		over.card = self
		add_child(over)
		over.size = size

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		var radius := UI.px(16)
		var e := eased()
		if pressed_t > 0.0:
			r = r.grow(-UI.px(3) * pressed_t)
		UI.focus_glow(self, r, radius, e)
		if character.is_empty():
			draw_style_box(UI.box(radius, Color(1, 1, 1, 0.03 + 0.06 * e), Color(1, 1, 1, 0.16), maxf(1.0, UI.px(1.5))), r)
			UI.focus_ring(self, r, radius, e)
			var m := UI.px(76)
			var c := Vector2(size.x * 0.5, size.y * 0.40)
			draw_style_box(UI.box(m * 0.5, Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.08 + 0.1 * e), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.6 + 0.4 * e), maxf(1.5, UI.px(2))), Rect2(c - Vector2(m, m) * 0.5, Vector2(m, m)))
			UI.icon(self, "plus", Rect2(c - Vector2(m, m) * 0.22, Vector2(m, m) * 0.44), UI.GOLD_HI)
			UI.text(self, Rect2(UI.px(10), c.y + m * 0.5 + UI.px(20), size.x - UI.px(20), UI.px(34)), "New character", UI.serif_bold(), 26, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
			UI.text(self, Rect2(UI.px(10), c.y + m * 0.5 + UI.px(56), size.x - UI.px(20), UI.px(26)), "Made in the game's own screen", UI.sans(), 16, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)
			return
		draw_style_box(UI.box(radius, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.28), UI.px(16)), r)
		draw_style_box(UI.box(radius, Color(UI.PANEL.r, UI.PANEL.g, UI.PANEL.b, 0.86).lerp(UI.PANEL_HOT, e * 0.7), Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, 0.6) if current else UI.LINE, maxf(1.0, UI.px(1.5))), r)
		UI.focus_ring(self, r, radius, e)


class CardText extends Control:
	var card: Control

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var c: Dictionary = card.get("character")
		var pad := UI.px(18)
		var y := size.y - UI.px(100)
		UI.text(self, Rect2(pad, y, size.x - pad * 2.0, UI.px(40)), String(c.get("name", "")), UI.serif_bold(), 28, UI.TEXT)
		UI.text(self, Rect2(pad, y + UI.px(40), size.x - pad * 2.0, UI.px(26)), UI.class_line(c), UI.sans(), 17, UI.DIM)
		if bool(card.get("current")):
			var tw := UI.text_width("PLAYING", UI.spaced(UI.bold(), 2.0), 13) + UI.px(24)
			var tr := Rect2(size.x - tw - UI.px(20), UI.px(20), tw, UI.px(28))
			draw_style_box(UI.box(UI.px(14), UI.GOLD), tr)
			UI.text(self, tr, "PLAYING", UI.spaced(UI.bold(), 2.0), 13, UI.INK, HORIZONTAL_ALIGNMENT_CENTER)
