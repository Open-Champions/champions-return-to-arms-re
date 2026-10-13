extends Control
# screen.gd - what every screen of the portal is: a Control the portal sizes, then asks to
# build itself.  A screen is rebuilt from its state whenever the window changes shape or
# the session says something changed; the focus is put back by the `key` of the control
# that had it.

const UI := preload("res://portal/ui.gd")
const W := preload("res://portal/widgets.gd")

var portal: Node
var args := {}
var want_focus := ""                # the key to focus after the next build
var entry := {}                     # text being asked for with the on-screen keys (ask_text)
var entry_field: Control
var entry_keys: Control


func setup(p_portal: Node, p_args: Dictionary) -> void:
	portal = p_portal
	args = p_args
	mouse_filter = Control.MOUSE_FILTER_IGNORE


# ---- what a screen says about itself -------------------------------------------------------
func build() -> void:
	pass


func chrome() -> bool:              # the bar at the top with the player's name, friends and settings
	return true


func hints() -> Array:
	return [hint_select(), hint_back()]


func back() -> bool:                # true: the screen dealt with it itself
	return false


func shortcut(_name: String) -> bool:   # x, lb, rb, start
	return false


func session_changed(_what: String) -> void:
	pass


func session_event(_e: Dictionary) -> void:
	pass


func device_changed() -> void:      # keyboard and mouse <-> controller
	pass


func tick(_delta: float) -> void:
	pass


# ---- helpers -------------------------------------------------------------------------------
static func hint_select(text := "Select") -> Dictionary:
	return {"pad": "a", "key": "Enter", "text": text}


static func hint_back(text := "Back") -> Dictionary:
	return {"pad": "b", "key": "Esc", "text": text}


func rebuild() -> void:
	var owner_now := get_viewport().gui_get_focus_owner() if is_inside_tree() else null
	if owner_now != null and is_ancestor_of(owner_now) and "key" in owner_now and String(owner_now.get("key")) != "":
		if entry.is_empty() or String(owner_now.get("key")).begins_with("key_"):
			if entry.is_empty():
				want_focus = String(owner_now.get("key"))
			else:
				entry["focus"] = String(owner_now.get("key"))
	for child in get_children():
		remove_child(child)
		child.queue_free()
	build()
	if not entry.is_empty():
		_build_entry()
	focus_now()


func focus_now() -> void:
	if not is_inside_tree() or portal == null or not portal.call("screen_may_focus", self):
		return
	var wanted := want_focus if entry.is_empty() else String(entry.get("focus", "key_done"))
	var target := find_key(self, wanted) if wanted != "" else null
	if target == null:
		target = first_focusable(self)
	if target != null:
		target.grab_focus()
		if "ft" in target:
			target.set("ft", 1.0)       # put back, not moved to: no animation


# ---- the portal asks through these ---------------------------------------------------------
func handle_back() -> bool:
	if not entry.is_empty():
		entry = {}
		rebuild()
		portal.call("refresh_hints")
		return true
	return back()


func handle_shortcut(name: String) -> bool:
	if not entry.is_empty():
		if name == "x":
			entry_keys.call("delete_one")
		elif name == "start":
			_entry_done()
		return true
	return shortcut(name)


func all_hints() -> Array:
	if not entry.is_empty():
		return [hint_select("Type"), {"pad": "x", "key": "Backspace", "text": "Delete"}, {"pad": "start", "key": "Enter", "text": String(entry.get("done_text", "Done"))}, hint_back("Cancel")]
	return hints()


# ---- text with a controller ----------------------------------------------------------------
# spec: {title, mode: "name" | "code" | "chat", text, max, upper, placeholder, done_text, done: Callable(text)}
func ask_text(spec: Dictionary) -> void:
	entry = spec
	entry["focus"] = "key_done" if String(spec.get("text", "")) != "" else ("key_A" if String(spec.get("mode", "name")) == "code" else "key_q")
	rebuild()
	portal.call("refresh_hints")


func _lock(node: Node) -> void:
	for child in node.get_children():
		if child is Control:
			(child as Control).focus_mode = Control.FOCUS_NONE
			(child as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
		_lock(child)


func _build_entry() -> void:
	_lock(self)
	var dim := ColorRect.new()
	dim.color = Color(0.01, 0.012, 0.02, 0.72)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	put(dim, Rect2(-position - Vector2(UI.px(400), UI.px(400)), size + Vector2(UI.px(800), UI.px(800))))
	var keys: Control = (load("res://portal/keys.gd") as GDScript).new()
	keys.set("mode", String(entry.get("mode", "name")))
	keys.set("done_text", String(entry.get("done_text", "Done")))
	var kz: Vector2 = keys.call("wanted_size")
	var w := maxf(kz.x, UI.px(640)) + UI.px(80)
	var h := UI.px(40 + 44 + 20 + 84 + 24) + kz.y + UI.px(40)
	var r := Rect2(((size - Vector2(w, h)) * 0.5).round(), Vector2(w, h))
	var panel := panel_at(r, 18.0)
	panel.set("alpha", 1.18)
	say(Rect2(r.position.x + UI.px(40), r.position.y + UI.px(34), w - UI.px(80), UI.px(44)), String(entry.get("title", "")), 30, UI.TEXT, UI.serif_bold(), HORIZONTAL_ALIGNMENT_CENTER)
	var field := W.Field.new(String(entry.get("placeholder", "")), int(entry.get("max", 24)))
	field.upper = bool(entry.get("upper", false))
	field.large = String(entry.get("mode", "name")) != "chat"
	field.height = 84.0
	field.text = String(entry.get("text", ""))
	field.focus_mode = Control.FOCUS_NONE
	put(field, Rect2(r.position.x + UI.px(40), r.position.y + UI.px(40 + 44 + 20), w - UI.px(80), UI.px(84)))
	field.set_editing(true)
	field.edited.connect(func(t: String) -> void: entry["text"] = t)
	entry_field = field
	keys.set("field", field)
	add_child(keys)
	keys.call("build")
	keys.position = Vector2(roundf(r.position.x + (w - kz.x) * 0.5), r.position.y + UI.px(40 + 44 + 20 + 84 + 24))
	keys.connect("done", _entry_done)
	entry_keys = keys


func _entry_done() -> void:
	var done: Callable = entry.get("done", Callable())
	var text := String(entry.get("text", ""))
	entry = {}
	rebuild()
	portal.call("refresh_hints")
	if done.is_valid():
		done.call(text)


func find_key(node: Node, key: String) -> Control:
	for child in node.get_children():
		if child is Control and "key" in child and String(child.get("key")) == key and (child as Control).focus_mode != Control.FOCUS_NONE:
			return child
		var found := find_key(child, key)
		if found != null:
			return found
	return null


func first_focusable(node: Node) -> Control:
	for child in node.get_children():
		if child is Control and (child as Control).focus_mode == Control.FOCUS_ALL and (child as Control).is_visible_in_tree():
			return child
		var found := first_focusable(child)
		if found != null:
			return found
	return null


# place a control by design-independent pixels inside this screen
func put(control: Control, rect: Rect2) -> Control:
	add_child(control)
	control.position = rect.position.round()
	control.size = rect.size.round()
	return control


# a line (or, with wrap, a paragraph) of text at a place
func say(rect: Rect2, string: String, size_px := 22.0, colour := UI.TEXT, font: Font = null, align := HORIZONTAL_ALIGNMENT_LEFT, wrap := false) -> Label:
	var l := UI.label(string, size_px, colour, font, wrap)
	l.horizontal_alignment = align
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER if not wrap else VERTICAL_ALIGNMENT_TOP
	put(l, rect)
	return l


func panel_at(rect: Rect2, radius := 16.0) -> Control:
	var p := PanelDraw.new()
	p.radius = radius
	return put(p, rect)


# A column of controls that scrolls when it is longer than its place.
func scroller(rect: Rect2, gap := 8.0) -> VBoxContainer:
	var sc := ScrollContainer.new()
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.follow_focus = true
	sc.mouse_filter = Control.MOUSE_FILTER_PASS
	var bar := sc.get_v_scroll_bar()
	bar.add_theme_stylebox_override("scroll", UI.box(UI.px(3), Color(1, 1, 1, 0.04)))
	bar.add_theme_stylebox_override("grabber", UI.box(UI.px(3), Color(1, 1, 1, 0.22)))
	bar.add_theme_stylebox_override("grabber_highlight", UI.box(UI.px(3), Color(1, 1, 1, 0.34)))
	bar.add_theme_stylebox_override("grabber_pressed", UI.box(UI.px(3), UI.GOLD))
	bar.custom_minimum_size.x = UI.px(6)
	put(sc, rect)
	var margin := MarginContainer.new()
	margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# room for the focus ring and its glow, and for the scroll bar
	margin.add_theme_constant_override("margin_left", int(UI.px(8)))
	margin.add_theme_constant_override("margin_right", int(UI.px(18)))
	margin.add_theme_constant_override("margin_top", int(UI.px(8)))
	margin.add_theme_constant_override("margin_bottom", int(UI.px(8)))
	sc.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", int(UI.px(gap)))
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	margin.add_child(box)
	return box


class PanelDraw extends Control:
	var radius := 16.0
	var alpha := 1.0

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		UI.panel(self, Rect2(Vector2.ZERO, size), radius, alpha)
