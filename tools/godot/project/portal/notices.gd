extends Control
# notices.gd - the small cards in the corner: "Sam invites you", "Priya wants to be
# friends", "Copied".  They never take the focus.  The newest one that can be answered is
# answered with ONE press from anywhere: Y / triangle on a controller, the Y key, or a
# click on the card.  In the game the same cards are drawn smaller and quieter (compact).
#
# An item: {id, kind, title, text, who, seed, accept_text, on_accept, on_dismiss, seconds}
#   kind   invite, request, good, info, error

const UI := preload("res://portal/ui.gd")
const W := preload("res://portal/widgets.gd")

signal answered(id: String, accepted: bool)
signal count_changed

var items: Array = []
var compact := false
var top_offset := 8.0               # design pixels from the top: in the band of the portal's bar, in the middle
var glyph_style := "xbox"
var in_game_hint := ""              # how to answer while the game has the buttons ("F2")


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func push(item: Dictionary) -> void:
	for it in items:
		if it.id == item.id:
			it.merge(item, true)
			it.age = 0.0
			return
	item["age"] = 0.0
	item["out"] = -1.0
	if not item.has("seconds"):
		item["seconds"] = 14.0 if item.has("on_accept") else 3.6
	items.push_front(item)
	while items.size() > 4:
		items.pop_back()
	count_changed.emit()
	queue_redraw()


func drop(id: String) -> void:
	for it in items:
		if it.id == id and float(it.out) < 0.0:
			it.out = 0.0
	queue_redraw()


func has(id: String) -> bool:
	for it in items:
		if it.id == id:
			return true
	return false


func current() -> Dictionary:
	# the newest card that can be answered
	for it in items:
		if it.has("on_accept") and float(it.out) < 0.0:
			return it
	return {}


func accept_current() -> bool:
	var it := current()
	if it.is_empty():
		return false
	it.out = 0.0
	(it.on_accept as Callable).call()
	answered.emit(String(it.id), true)
	return true


func dismiss_current() -> bool:
	var it := current()
	if it.is_empty():
		return false
	it.out = 0.0
	if it.has("on_dismiss"):
		(it.on_dismiss as Callable).call()
	answered.emit(String(it.id), false)
	return true


func _process(delta: float) -> void:
	if items.is_empty():
		return
	var before := items.size()
	for it in items:
		it.age = float(it.age) + delta
		if float(it.out) >= 0.0:
			it.out = float(it.out) + delta
		elif float(it.age) > float(it.seconds):
			it.out = 0.0
	items = items.filter(func(it: Dictionary) -> bool: return float(it.out) < 0.18)
	if items.size() != before:
		count_changed.emit()
	queue_redraw()


func _card_size(it: Dictionary) -> Vector2:
	var w := 560.0 if not compact else 420.0
	var h := 88.0 if not compact else 74.0
	if not it.has("on_accept") and String(it.get("text", "")) == "":
		h = 64.0 if not compact else 56.0
	return UI.v2(w, h)


func _card_rects() -> Array:
	var out := []
	var y := UI.px(top_offset if not compact else 28.0)
	for it in items:
		var z := _card_size(it)
		var appear := clampf(float(it.age) / 0.16, 0.0, 1.0)
		appear = 1.0 - pow(1.0 - appear, 3.0)
		var leave := clampf(float(it.out) / 0.16, 0.0, 1.0) if float(it.out) >= 0.0 else 0.0
		var x := size.x - UI.px(40) - z.x + (1.0 - appear) * UI.px(60) + leave * UI.px(60)
		if not compact:
			# in the portal: top centre, sliding down into place
			x = roundf((size.x - z.x) * 0.5)
			out.append([Rect2(x, y - (1.0 - appear) * UI.px(40) - leave * UI.px(40), z.x, z.y), appear * (1.0 - leave)])
			y += (z.y + UI.px(10)) * (1.0 - leave)
			continue
		out.append([Rect2(x, y, z.x, z.y), appear * (1.0 - leave)])
		y += (z.y + UI.px(10)) * (1.0 - leave)
	return out


func _input(event: InputEvent) -> void:
	# a click on a card that can be answered answers it
	var mouse := event as InputEventMouseButton
	if mouse == null or not mouse.pressed or mouse.button_index != MOUSE_BUTTON_LEFT or not is_visible_in_tree():
		return
	var rects := _card_rects()
	for k in items.size():
		if (rects[k][0] as Rect2).has_point(mouse.position - global_position) and items[k].has("on_accept") and float(items[k].out) < 0.0:
			get_viewport().set_input_as_handled()
			var it: Dictionary = items[k]
			it.out = 0.0
			(it.on_accept as Callable).call()
			answered.emit(String(it.id), true)
			return


func _draw() -> void:
	var rects := _card_rects()
	var first_answerable := current()
	for k in items.size():
		var it: Dictionary = items[k]
		var r: Rect2 = rects[k][0]
		var a: float = rects[k][1]
		if a <= 0.01:
			continue
		var kind := String(it.get("kind", "info"))
		var accent := UI.GOLD
		match kind:
			"error": accent = UI.RED
			"good": accent = UI.GREEN
			"invite": accent = UI.BLUE
			"request": accent = UI.GOLD
			"info": accent = UI.DIM
		var radius := UI.px(14)
		draw_style_box(UI.box(radius, Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0.45 * a), UI.px(20)), r)
		draw_style_box(UI.box(radius, Color(0.085, 0.096, 0.135, (0.97 if not compact else 0.86) * a), Color(accent.r, accent.g, accent.b, 0.55 * a), maxf(1.0, UI.px(1.5))), r)
		# the accent: a short bar at the left
		draw_style_box(UI.box(UI.px(2), Color(accent.r, accent.g, accent.b, a)), Rect2(r.position.x + UI.px(10), r.position.y + UI.px(16), UI.px(4), r.size.y - UI.px(32)))
		var x := r.position.x + UI.px(28)
		var av := r.size.y - UI.px(30)
		if String(it.get("who", "")) != "":
			draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
			W.Avatar.draw_avatar(self, Rect2(x, r.position.y + UI.px(15), av, av), String(it.who), String(it.get("seed", it.who)), -1)
			x += av + UI.px(16)
		else:
			var icon_name := {"error": "warn", "good": "check", "info": "bell"}.get(kind, "bell") as String
			var isz := UI.px(26)
			UI.icon(self, icon_name, Rect2(x, r.position.y + (r.size.y - isz) * 0.5, isz, isz), Color(accent.r, accent.g, accent.b, a))
			x += isz + UI.px(14)
		var right := r.end.x - UI.px(18)
		if it.has("on_accept"):
			var label := String(it.get("accept_text", "Accept"))
			var is_current: bool = not first_answerable.is_empty() and first_answerable.id == it.id
			var g := UI.px(30)
			var tw := UI.text_width(label, UI.bold(), 18)
			var bw := tw + UI.px(34) + (g + UI.px(8) if is_current else 0.0)
			var b := Rect2(right - bw, r.position.y + (r.size.y - UI.px(44)) * 0.5, bw, UI.px(44))
			draw_style_box(UI.box(b.size.y * 0.5, Color(UI.GOLD.r, UI.GOLD.g, UI.GOLD.b, (0.95 if is_current else 0.16) * a), Color(1, 1, 1, 0.2 * a), 1), b)
			var bx := b.position.x + UI.px(14)
			var ink := UI.INK if is_current else UI.TEXT
			if is_current:
				if in_game_hint != "" and compact:
					bx += 0.0
				elif UI.pad_glyphs:
					draw_circle(Vector2(bx - UI.px(4) + g * 0.5, b.position.y + b.size.y * 0.5), g * 0.5, Color(0.05, 0.05, 0.05, 0.55), true, -1.0, true)
					W.Hints.draw_glyph(self, Rect2(bx - UI.px(4), b.position.y + (b.size.y - g) * 0.5, g, g), "y", glyph_style)
				else:
					var cap := Rect2(bx - UI.px(4), b.position.y + (b.size.y - UI.px(28)) * 0.5, g, UI.px(28))
					draw_style_box(UI.box(UI.px(6), Color(0.05, 0.05, 0.05, 0.75)), cap)
					UI.text(self, cap, "Y", UI.bold(), 15, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
				bx += g + UI.px(4)
			UI.text(self, Rect2(bx, b.position.y, b.end.x - bx - UI.px(8), b.size.y), label if not (compact and in_game_hint != "" and is_current) else in_game_hint + "  " + label,
				UI.bold(), 18, Color(ink.r, ink.g, ink.b, a), HORIZONTAL_ALIGNMENT_CENTER)
			right = b.position.x - UI.px(14)
		var title := String(it.get("title", ""))
		var body := String(it.get("text", ""))
		var th := UI.line_height(UI.bold(), 20)
		var bh := UI.line_height(UI.sans(), 16)
		if body == "":
			UI.text(self, Rect2(x, r.position.y, right - x, r.size.y), title, UI.bold(), 20, Color(UI.TEXT.r, UI.TEXT.g, UI.TEXT.b, a))
		else:
			var top := r.position.y + (r.size.y - th - bh) * 0.5
			UI.text(self, Rect2(x, top, right - x, th), title, UI.bold(), 20, Color(UI.TEXT.r, UI.TEXT.g, UI.TEXT.b, a))
			UI.text(self, Rect2(x, top + th, right - x, bh), body, UI.sans(), 16, Color(UI.DIM.r, UI.DIM.g, UI.DIM.b, a))
