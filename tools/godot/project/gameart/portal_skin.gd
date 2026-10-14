extends RefCounted
# portal_skin.gd - the portal in the look of Champions: Return to Arms, with the game's own pictures read from
# the player's disc (gameart.gd).  It is UI.skin (portal/ui.gd); the portal's layout is the portal's own, this
# only draws its surfaces, through the hooks of tools/godot/gameart-hooks.patch:
#
#   decorate   a loading painting of the game (LINTRO shot) behind everything, darkened towards the edges
#   logo       the game's logo (FRONTEND title) in place of the drawn emblem
#   surface    panels, the home's tiles, rows, fields, choices: the game's frame - slate inside a bronze rim;
#              the round medallions: the bust's round frame; buttons: the game's bronze button
#   portrait   the character card: the frame round a painting of the hub
#   pad_glyph  with PlayStation hints: the face and shoulder buttons out of the game's font
#   fonts      headings in the game's title face (PVPFONT pvpfontbig), the rest in its text face (FONT gamefontmed)
#
# install(portal) is called by portal.gd before it builds its layer; setting_row(portal) gives the settings'
# "Interface art" choice.  Everything falls back to the portal's clean drawing while the art is not there.

const GA := preload("res://gameart/gameart.gd")
const UI := preload("res://portal/ui.gd")
const W := preload("res://portal/widgets.gd")
const Cat := preload("res://gameart/catalogue.gd")

const BACKDROP := "shot_lintro"
const PORTRAIT := "shot_lhub"

static var _portal: Node
static var _clean := {}


static func install(portal: Node) -> void:
	_portal = portal
	if _clean.is_empty():
		_clean = {"sans": UI._sans, "bold": UI._bold, "serif": UI._serif, "serif_bold": UI._serif_bold}
	if not GA.wanted():
		_uninstall()
		return
	UI.skin = load("res://gameart/portal_skin.gd").new()
	if GA.ready():
		_fonts()
	else:
		GA.when_ready(func() -> void:
			if UI.skin != null:
				_fonts()
				if is_instance_valid(_portal):
					_portal.call("_layout"))


static func _uninstall() -> void:
	UI.skin = null
	UI._sans = _clean.get("sans")
	UI._bold = _clean.get("bold")
	UI._serif = _clean.get("serif")
	UI._serif_bold = _clean.get("serif_bold")
	UI._spaced.clear()


static func _fonts() -> void:
	var text := GA.font("font_med", 0.70)
	var title := GA.font("font_title", 0.64)
	if text != null:
		UI._sans = text
		UI._bold = text
	if title != null:
		UI._serif = title
		UI._serif_bold = title
	UI._spaced.clear()


# the settings' row: "Interface art"
static func setting_row(portal: Node) -> Control:
	GA.start()
	var have := GA.disc_path != "" and GA.problem == ""
	var index := 0 if (GA.setting() != "clean" and have) else 1
	var note := "The game's own frames, bars, icons and lettering, read from your disc image." if have \
		else "Needs your disc image of the game; the clean look is used until it is found."
	var c := W.Choice.new("Interface art", PackedStringArray(["The game's own", "Clean"]), index, note)
	c.key = "gameart"
	c.locked = not have
	c.changed.connect(func(i: int) -> void:
		GA.set_setting("game" if i == 0 else "clean")
		install(portal)
		_tell_hud(i == 0)
		portal.call("_layout"))
	return c


static func _tell_hud(game: bool) -> void:
	var tree := Engine.get_main_loop() as SceneTree
	var stack: Array[Node] = [tree.root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		var s: Script = n.get_script()
		if s != null and s.resource_path == "res://hud/hud.gd" and n.has_method("command"):
			n.call("command", ["theme", "res://gameart/hud_skin.gd" if game else "default"])
		for c in n.get_children():
			stack.append(c)


func _on() -> bool:
	return GA.ready()


# ---- the backdrop -------------------------------------------------------------------------------------
func decorate(portal: Node, root: Control) -> bool:
	var layer := Backdrop.new()
	layer.name = "GameArtBackdrop"
	layer.portal = portal
	layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(layer)
	return true


class Backdrop extends Control:
	var portal: Node

	func _process(_delta: float) -> void:
		var want := UI.skin != null and GA.ready() and not bool(portal.get("game_behind"))
		if visible != want:
			visible = want
			queue_redraw()
		if get_parent() is Control and size != (get_parent() as Control).size:
			size = (get_parent() as Control).size

	func _draw() -> void:
		var img := GA.image(BACKDROP)
		if img == null:
			return
		# cover the screen, keep the picture's shape; the painting's own soft rim fades into the dark ground
		var src := Vector2(img.get_size())
		var k := maxf(size.x / src.x, size.y / src.y) * 1.04
		var dst := Rect2((size - src * k) * 0.5, src * k)
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.02, 0.025))
		GA.draw(self, BACKDROP, dst, Color(0.62, 0.62, 0.66))
		# darker towards the bottom and the left, where the menu is read
		var top := Color(0, 0, 0, 0.10)
		var low := Color(0, 0, 0, 0.62)
		draw_polygon(PackedVector2Array([Vector2.ZERO, Vector2(size.x, 0), size, Vector2(0, size.y)]), PackedColorArray([top, top, low, low]))
		var left := Color(0, 0, 0, 0.45)
		var none := Color(0, 0, 0, 0.0)
		draw_polygon(PackedVector2Array([Vector2.ZERO, Vector2(size.x * 0.7, 0), Vector2(size.x * 0.7, size.y), Vector2(0, size.y)]), PackedColorArray([left, none, none, left]))


# ---- the logo -----------------------------------------------------------------------------------------
func logo(ci: CanvasItem, rect: Rect2) -> bool:
	if not _on() or not GA.has("logo"):
		return false
	var s := GA.size_texels("logo")
	var h := rect.size.y
	var w := h * s.x / s.y
	if w > rect.size.x:
		w = rect.size.x
		h = w * s.y / s.x
	return GA.draw(ci, "logo", Rect2(rect.position + Vector2(0, (rect.size.y - h) * 0.5), Vector2(w, h)))


# ---- surfaces -----------------------------------------------------------------------------------------
func surface(ci: CanvasItem, kind: String, rect: Rect2, radius: float, e: float, disabled: bool) -> bool:
	if not _on():
		return false
	var a := 0.5 if disabled else 1.0
	match kind:
		"panel":
			_frame(ci, rect, UI.px(30), a, 0.93, 1.0)
		"tile":
			_shadow(ci, rect, UI.px(20), 0.45 * a)
			_frame(ci, rect, UI.px(30), a, 0.90, 1.0 + 0.22 * e)
			if e > 0.01:
				# the focused tile: a warm light from the left inside the slate
				var c := Color(1.0, 0.78, 0.40, 0.13 * e)
				var n := Color(1.0, 0.78, 0.40, 0.0)
				var inset := UI.px(10)
				var p := rect.position + Vector2(inset, inset)
				var z := rect.size - Vector2(inset, inset) * 2.0
				ci.draw_polygon(PackedVector2Array([p, p + Vector2(z.x * 0.6, 0), p + Vector2(z.x * 0.6, z.y), p + Vector2(0, z.y)]), PackedColorArray([c, n, n, c]))
		"choice", "gauge", "row":
			_frame(ci, rect, UI.px(20), a * (0.80 + 0.20 * e), 0.88, 0.92 + 0.25 * e)
		"field":
			_frame(ci, rect, UI.px(20), a, 0.96, 0.62 + 0.2 * e)
		"medal":
			var c := rect.get_center()
			var r := minf(rect.size.x, rect.size.y) * 0.5
			ci.draw_circle(c, r * 0.92, Color(0.04, 0.045, 0.035, 0.9 * a))
			if e > 0.01:
				ci.draw_circle(c, r * 0.9, Color(1.0, 0.78, 0.40, 0.10 * e))
			GA.draw(ci, "socket", Rect2(c - Vector2(r, r) * 1.08, Vector2(r, r) * 2.16), Color(1, 1, 1, a))
		"button_normal", "button_primary", "button_danger":
			_button(ci, rect, kind, e, a)
		_:
			return false
	return true


func _shadow(ci: CanvasItem, rect: Rect2, size: float, alpha: float) -> void:
	ci.draw_style_box(UI.box(UI.px(18), Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, Color(0, 0, 0, alpha), size), rect.grow(-UI.px(4)))


# slate in a rounded shape that ends under the rim's rails and corner ornaments, then the bronze rim
func _frame(ci: CanvasItem, rect: Rect2, b: float, alpha: float, fill_alpha: float, light: float) -> void:
	b = minf(b, minf(rect.size.x, rect.size.y) * 0.45)
	var inset := b * 5.0 / 32.0
	var corner := b * 27.0 / 32.0
	_slate(ci, rect.grow(-inset), corner - inset, Color(light, light, light, fill_alpha * alpha))
	GA.nine(ci, "frame", rect, b, Color(1, 1, 1, alpha))


func _slate(ci: CanvasItem, r: Rect2, radius: float, modulate: Color) -> void:
	var img := GA.image("frame_center")
	if img == null:
		return
	radius = clampf(radius, 0.0, minf(r.size.x, r.size.y) * 0.5)
	var span := maxf(UI.px(900), maxf(r.size.x, r.size.y))
	var tex := GA.tex("frame_center", span / img.get_width())
	var pts := PackedVector2Array()
	for corner in range(4):
		var cc: Vector2
		match corner:
			0: cc = Vector2(r.end.x - radius, r.position.y + radius)
			1: cc = Vector2(r.end.x - radius, r.end.y - radius)
			2: cc = Vector2(r.position.x + radius, r.end.y - radius)
			_: cc = Vector2(r.position.x + radius, r.position.y + radius)
		for j in range(7):
			var ang := -PI * 0.5 + (corner + j / 6.0) * PI * 0.5
			pts.append(cc + Vector2(cos(ang), sin(ang)) * radius)
	var uvs := PackedVector2Array()
	# each surface takes its own part of the stone (by where it sits), never beyond the picture's edge
	var origin := ci.get_global_transform().origin
	var room := Vector2(maxf(0.0, 1.0 - r.size.x / span), maxf(0.0, 1.0 - r.size.y / span))
	var off := Vector2(fposmod(origin.x * 0.0037, 1.0) * room.x, fposmod(origin.y * 0.0029, 1.0) * room.y)
	for p in pts:
		uvs.append(off + (p - r.position) / span)
	ci.draw_colored_polygon(pts, modulate, uvs, tex)


# the game's bronze button (INTERFAC button: the pill is texels 11..72 x 2..33): ends kept, middle stretched
func _button(ci: CanvasItem, rect: Rect2, kind: String, e: float, a: float) -> void:
	var h := rect.size.y
	var k := h / 31.0
	var end_w := minf(h * 0.62, rect.size.x * 0.5)
	var mod := Color(1, 1, 1, a)
	_shadow(ci, rect, UI.px(10), 0.35 * a)
	GA.draw_part(ci, "button", Rect2(rect.position, Vector2(end_w, h)), Rect2(11, 2, end_w / k, 31), mod)
	GA.draw_part(ci, "button", Rect2(rect.position + Vector2(end_w, 0), Vector2(maxf(0.0, rect.size.x - 2.0 * end_w), h)), Rect2(11 + end_w / k, 2, 61 - 2.0 * end_w / k, 31), mod)
	GA.draw_part(ci, "button", Rect2(rect.end.x - end_w, rect.position.y, end_w, h), Rect2(72 - end_w / k, 2, end_w / k, 31), mod)
	var inner := rect.grow(-h * 0.17)
	var wash := Color(0, 0, 0, 0)
	match kind:
		"button_primary":
			wash = Color(0.95, 0.70, 0.30, (0.30 + 0.18 * e) * a)
		"button_danger":
			wash = Color(0.85, 0.20, 0.15, (0.30 + 0.15 * e) * a)
		_:
			wash = Color(1.0, 0.85, 0.55, 0.10 * e * a)
	if wash.a > 0.0:
		ci.draw_style_box(UI.box(inner.size.y * 0.5, wash), inner)


# ---- the character card -------------------------------------------------------------------------------
func portrait(ci: CanvasItem, rect: Rect2, character: Dictionary, framed: bool, empty_text: String) -> bool:
	if not _on() or not GA.has(PORTRAIT):
		return false
	var b := UI.px(26)
	var inner := rect.grow(-b * 0.22)
	var img := GA.image(PORTRAIT)
	var src := Vector2(img.get_size()) / GA.texel(PORTRAIT)
	# the middle of the painting, cut to the card's shape
	var k := maxf(inner.size.x / src.x, inner.size.y / src.y)
	var cut := inner.size / k
	var from := Rect2((src - cut) * 0.5, cut)
	GA.draw_part(ci, PORTRAIT, inner, from, Color(0.85, 0.85, 0.88) if String(character.get("name", "")) != "" else Color(0.45, 0.45, 0.5))
	var low := Color(0, 0, 0, 0.55)
	var none := Color(0, 0, 0, 0.0)
	var mid := inner.position + Vector2(0, inner.size.y * 0.55)
	ci.draw_polygon(PackedVector2Array([mid, mid + Vector2(inner.size.x, 0), inner.end, Vector2(inner.position.x, inner.end.y)]), PackedColorArray([none, none, low, low]))
	GA.nine(ci, "frame", rect, b)
	if String(character.get("name", "")) == "" and empty_text != "":
		UI.text(ci, Rect2(inner.position.x, inner.position.y + inner.size.y * 0.80, inner.size.x, inner.size.y * 0.14), empty_text, UI.sans(), 18, UI.DIM, HORIZONTAL_ALIGNMENT_CENTER)
	return true


# ---- controller hints ---------------------------------------------------------------------------------
func pad_glyph(ci: CanvasItem, rect: Rect2, name: String, glyph_style: String) -> bool:
	if not _on() or glyph_style != "ps":
		return false
	var f := GA.font("font_med", 0.70)
	if f == null:
		return false
	var ch := ""
	match name:
		"a": ch = Cat.BUTTON_CHARS.cro
		"b": ch = Cat.BUTTON_CHARS.cir
		"x": ch = Cat.BUTTON_CHARS.squ
		"y": ch = Cat.BUTTON_CHARS.tri
		"lb": ch = Cat.BUTTON_CHARS.L1
		"rb": ch = Cat.BUTTON_CHARS.R1
		"lr": ch = Cat.BUTTON_CHARS.L1 + " " + Cat.BUTTON_CHARS.R1
		_: return false
	var px := maxi(10, int(round(rect.size.y * 1.15)))
	var w: float = f.get_string_size(ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
	var at := Vector2(rect.end.x - w if name in ["lb", "rb", "lr"] else rect.get_center().x - w * 0.5, rect.get_center().y + f.get_ascent(px) * 0.42)
	ci.draw_string(f, at.round(), ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color.WHITE)
	return true
