extends RefCounted
# hud_skin.gd - the HUD in the look of Champions: Return to Arms, with the game's own pictures read from the
# player's disc (gameart.gd).  A skin of hud/style.gd: it takes over panels, bars, text, the potion flasks,
# the coin, key caps and - through the three hooks of tools/godot/gameart-hooks.patch - the quick slots'
# ability pictures, the controller's face buttons and the round sockets.  The layout is the HUD's own.
# Everything here returns false (the clean drawing) while the art is not there.
#
#   panels   the game's frame: slate (INTERFAC tilecenter) inside a bronze rim (the eight tile pieces)
#   bars     the game's bar paint (HUD bar_red / bar_blue / bar_green, BUST bar_yellow) in a dark channel
#   text     the game's own font (FONT gamefontmed) from the size it reads well at; smaller: the clean font
#   slots    the ability's own medallion (ICONS ic<name>, which skill has which: catalogue SKILL_ICONS)
#   flasks   the game's potion icons (ICONS counthealth / countmana), coin: the gold pile (HUD gold03)
#   sockets  the bust's round frame (BUST frame)
#   buttons  the face buttons and shoulder buttons out of the game's font

const GA := preload("res://gameart/gameart.gd")
const Cat := preload("res://gameart/catalogue.gd")

# sizes in design pixels (multiplied by the HUD's scale s)
const RIM := 22.0                  # side of a frame corner piece (at most 0.42 of the panel's smaller side)
const GAME_FONT_FROM := 13.0       # text from this size (design pixels x scale) in the game's font
const SLATE_SPAN := 620.0          # the slate picture spans this many design pixels (all panels the same grain)

var style: Script
var _font: Font
var _clean: Font
var _clean_bold: Font


func setup(s: Script) -> void:
	style = s
	_clean = ThemeDB.fallback_font
	var v := FontVariation.new()
	v.base_font = ThemeDB.fallback_font
	v.variation_embolden = 0.55
	_clean_bold = v
	GA.start()
	GA.when_ready(_arrive)


func _arrive() -> void:
	var ids := PackedStringArray(["bar_red", "bar_blue", "bar_green", "bar_yellow", "gold", "socket"])
	for id in Cat.ENTRIES:
		if String(id).begins_with("frame_") or String(id).begins_with("icon_"):
			ids.append(id)
	GA.prewarm(ids)
	_font = GA.font("font_med", 0.70)
	if _font != null:
		style._font = _font
		style._bold = _font
	# the game's colours: its health paint is an orange red, the mana a pale blue, experience gold
	style.TEXT = Color(0.97, 0.95, 0.88)
	style.TEXT_DIM = Color(0.80, 0.77, 0.68)
	style.GOLD = Color(1.0, 0.84, 0.36)


func _on() -> bool:
	return GA.ready()


# ---- panels -------------------------------------------------------------------------------------------
func panel(ci: CanvasItem, rect: Rect2, s: float, alpha: float, radius: float) -> bool:
	if not _on() or rect.size.x < 8.0 or rect.size.y < 8.0:
		return false
	var b := minf(RIM * s, minf(rect.size.x, rect.size.y) * 0.42)
	style.rounded(ci, rect.grow(maxf(1.0, 2.0 * s)), b * 0.6, Color(0, 0, 0, 0.30 * alpha))
	frame(ci, rect, b, alpha, 0.92)
	return true


# slate in a rounded shape that ends under the rim's rails and corner ornaments, then the rim
func frame(ci: CanvasItem, rect: Rect2, b: float, alpha: float, fill_alpha: float) -> void:
	b = minf(b, minf(rect.size.x, rect.size.y) * 0.5)
	var inset := b * 5.0 / 32.0
	var corner := b * 27.0 / 32.0
	var inner := rect.grow(-inset)
	_slate(ci, inner, corner - inset, Color(1, 1, 1, fill_alpha * alpha), b / RIM)
	GA.nine(ci, "frame", rect, b, Color(1, 1, 1, alpha))


func _slate(ci: CanvasItem, r: Rect2, radius: float, modulate: Color, s: float) -> void:
	var img := GA.image("frame_center")
	if img == null:
		return
	radius = clampf(radius, 0.0, minf(r.size.x, r.size.y) * 0.5)
	var span := SLATE_SPAN * maxf(s, 0.4)
	var tex := GA.tex("frame_center", span / img.get_width())
	var pts := PackedVector2Array()
	var uvs := PackedVector2Array()
	var k := 5
	for corner in range(4):
		var cc: Vector2
		match corner:
			0: cc = Vector2(r.end.x - radius, r.position.y + radius)
			1: cc = Vector2(r.end.x - radius, r.end.y - radius)
			2: cc = Vector2(r.position.x + radius, r.end.y - radius)
			_: cc = Vector2(r.position.x + radius, r.position.y + radius)
		for j in range(k + 1):
			var a := -PI * 0.5 + (corner + float(j) / k) * PI * 0.5
			pts.append(cc + Vector2(cos(a), sin(a)) * radius)
	var origin := r.position
	var u := 1.0 / maxf(span, maxf(r.size.x, r.size.y))
	for p in pts:
		uvs.append((p - origin) * u)
	ci.draw_colored_polygon(pts, modulate, uvs, tex)


# ---- bars ---------------------------------------------------------------------------------------------
func _paint_for(a: Color) -> String:
	var h := a.h
	if a.s < 0.2:
		return ""
	if h < 0.07 or h > 0.93:
		return "bar_red"
	if h < 0.19:
		return "bar_yellow"
	if h < 0.47:
		return "bar_green"
	if h < 0.75:
		return "bar_blue"
	return "bar_red"


func bar(ci: CanvasItem, rect: Rect2, value: float, ghost: float, a: Color, b: Color, s: float, alpha: float, ahead: float, ahead_colour: Color) -> bool:
	if not _on():
		return false
	var paint := _paint_for(a)
	if paint == "":
		return false
	var r := minf(rect.size.y * 0.5, 4.0 * s)
	# the channel: dark, with a thin bronze edge as the game's bars sit in
	style.rounded(ci, rect.grow(maxf(1.0, 1.2 * s)), r + s, Color(0.42, 0.37, 0.24, 0.85 * alpha))
	style.rounded(ci, rect, r, Color(0.03, 0.03, 0.025, 0.82 * alpha))
	value = clampf(value, 0.0, 1.0)
	ghost = clampf(ghost, 0.0, 1.0)
	if ahead > value:
		_paint(ci, "bar_green", rect, rect.size.x * clampf(ahead, 0.0, 1.0), Color(1, 1, 1, 0.55 * alpha))
	if ghost > value + 0.002:
		style.rounded(ci, Rect2(rect.position, Vector2(rect.size.x * ghost, rect.size.y)), r, Color(1.0, 0.92, 0.76, 0.75 * alpha))
	if value > 0.0:
		var w: float = maxf(rect.size.x * value, minf(rect.size.x, 2.0 * s))
		var tint := Color(1, 1, 1, alpha)
		if paint == "bar_red" and a.h > 0.75 and a.h <= 0.93:
			tint = Color(0.95, 0.62, 1.0, alpha)          # the boss's purple from the red paint
		_paint(ci, paint, rect, w, tint)
	return true


# the paint, laid out over the WHOLE bar and shown up to `fill` pixels (so it does not stretch as the bar drains):
# its rounded left end once, then its middle stretched along the bar (never more than 4 x; a longer bar takes
# the middle again in equal pieces).  Texels 10..88 only: the paint darkens towards its ends.
func _paint(ci: CanvasItem, id: String, rect: Rect2, fill: float, modulate: Color) -> void:
	var size := GA.size_texels(id)
	if size == Vector2.ZERO or fill < 0.5:
		return
	var h := rect.size.y
	var px_per_texel := h / size.y
	var cap := minf(6.0 * px_per_texel, rect.size.x)
	var mid := Rect2(10.0, 0, minf(78.0, size.x - 16.0), size.y)
	var rest := maxf(0.0, rect.size.x - cap)
	var n := maxi(1, int(ceil(rest / (mid.size.x * px_per_texel * 4.0))))
	var piece := rest / n
	var parts := [[0.0, cap, Rect2(0, 0, 6.0, size.y)]]
	for k in range(n):
		parts.append([cap + piece * k, piece, mid])
	for p in parts:
		var x: float = p[0]
		var w: float = p[1]
		if x >= fill or w <= 0.0:
			break
		var src: Rect2 = p[2]
		var shown := minf(w, fill - x)
		GA.draw_part(ci, id, Rect2(rect.position.x + x, rect.position.y, shown, h), Rect2(src.position, Vector2(src.size.x * shown / w, src.size.y)), modulate)


# ---- text ---------------------------------------------------------------------------------------------
func text(ci: CanvasItem, pos: Vector2, string: String, size: float, colour: Color, align: int, heavy: bool, outline: float) -> float:
	if not _on() or _font == null:
		return -1.0
	var small := size < GAME_FONT_FROM * _scale_hint(size)
	var f: Font = (_clean_bold if heavy else _clean) if small else _font
	var px := maxi(8, int(round(size)))
	var w: float = f.get_string_size(string, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
	var p := pos
	if align == 1:
		p.x -= w * 0.5
	elif align == 2:
		p.x -= w
	p = p.round()
	if small:
		var o := int(round(outline)) if outline > 0.0 else maxi(2, int(round(size * 0.14)))
		ci.draw_string_outline(f, p, string, HORIZONTAL_ALIGNMENT_LEFT, -1, px, o, Color(0, 0, 0, 0.85 * colour.a))
	else:
		# the game's letters carry their own dark rim; a soft drop below keeps them readable over bright ground
		ci.draw_string(f, p + Vector2(0, maxf(1.0, size * 0.06)), string, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(0, 0, 0, 0.55 * colour.a))
	ci.draw_string(f, p, string, HORIZONTAL_ALIGNMENT_LEFT, -1, px, colour)
	return w


func _scale_hint(_size: float) -> float:
	return 1.0


# ---- small pictures -----------------------------------------------------------------------------------
func flask(ci: CanvasItem, c: Vector2, r: float, colour: Color) -> bool:
	if not _on():
		return false
	var id := "icon_countmana" if colour.b > colour.r else "icon_counthealth"
	var size := GA.size_texels(id)
	if size == Vector2.ZERO:
		return false
	# the flask fills the middle 14 x 26 texels of its 32 x 28 picture
	var h := r * 2.3
	var k := h / 26.0
	var rect := Rect2(c - Vector2(size.x * k * 0.5, h * 0.5 + 1.0 * k), size * k)
	GA.draw(ci, id, rect, Color(1, 1, 1, colour.a))
	return true


func coin(ci: CanvasItem, c: Vector2, r: float, alpha: float) -> bool:
	if not _on():
		return false
	# the gold pile sits in the lower third of its picture (texels 1..29 x 21..34)
	var k := r * 2.6 / 28.0
	var rect := Rect2(c + Vector2(-14.0, -7.0) * k, Vector2(28.0, 13.0) * k)
	return GA.draw_part(ci, "gold", rect, Rect2(1, 21, 28, 13), Color(1, 1, 1, alpha))


func socket(ci: CanvasItem, c: Vector2, r: float, alpha: float) -> bool:
	if not _on():
		return false
	ci.draw_circle(c, r * 0.94, Color(0.02, 0.025, 0.02, 0.55 * alpha))
	return GA.draw(ci, "socket", Rect2(c - Vector2(r, r) * 1.04, Vector2(r, r) * 2.08), Color(1, 1, 1, alpha))


func slot_icon(ci: CanvasItem, rect: Rect2, slot: Dictionary, ready: bool) -> bool:
	if not _on():
		return false
	var id: String = Cat.SKILL_ICONS.get(int(slot.get("skill_id", -1)), "icon_icblank")
	if not GA.has(id):
		return false
	var side := rect.size.y * 0.84
	var r := Rect2(rect.get_center() - Vector2(side * 0.5, side * 0.5 + rect.size.y * 0.07), Vector2(side, side))
	var dim := 1.0 if ready else 0.45
	GA.draw(ci, id, r, Color(dim, dim, dim, 1.0))
	return true


func face_button(ci: CanvasItem, c: Vector2, r: float, label: String, alpha: float) -> bool:
	if not _on() or _font == null:
		return false
	var ch: String = Cat.BUTTON_CHARS.get(label, "")
	if ch == "":
		return false
	var px := maxi(8, int(round(r * 2.3)))
	var w: float = _font.get_string_size(ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
	var asc := _font.get_ascent(px)
	ci.draw_string(_font, (c + Vector2(-w * 0.5, asc * 0.5 - r * 0.05)).round(), ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(1, 1, 1, alpha))
	return true


# a key's name on the game's bronze button (INTERFAC button: the pill is texels 11..72 x 2..33 of its picture)
func keycap(ci: CanvasItem, pos: Vector2, label: String, size: float, alpha: float) -> float:
	if not _on() or _font == null:
		return -1.0
	var ch: String = Cat.BUTTON_CHARS.get(label, "")
	if ch != "":
		var px := maxi(8, int(round(size * 1.9)))
		var gw: float = _font.get_string_size(ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
		ci.draw_string(_font, (pos + Vector2(0, _font.get_ascent(px) * 0.5)).round(), ch, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(1, 1, 1, alpha))
		return gw
	var h: float = size * 1.6
	var f: Font = _clean_bold if size < GAME_FONT_FROM else _font
	var px2 := maxi(8, int(round(size)))
	var tw: float = f.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, px2).x
	var w: float = maxf(h * 1.2, tw + size * 1.4)
	var rect := Rect2(pos + Vector2(0, -h * 0.5), Vector2(w, h))
	# three slices of the pill: its rounded ends kept, its middle stretched
	var end_w := h * 0.62
	var k := h / 31.0
	var mod := Color(1, 1, 1, alpha)
	GA.draw_part(ci, "button", Rect2(rect.position, Vector2(end_w, h)), Rect2(11, 2, end_w / k, 31), mod)
	GA.draw_part(ci, "button", Rect2(rect.position + Vector2(end_w, 0), Vector2(maxf(0.0, w - 2.0 * end_w), h)), Rect2(11 + end_w / k, 2, 61 - 2.0 * end_w / k, 31), mod)
	GA.draw_part(ci, "button", Rect2(rect.end.x - end_w, rect.position.y, end_w, h), Rect2(72 - end_w / k, 2, end_w / k, 31), mod)
	ci.draw_string(f, (rect.position + Vector2((w - tw) * 0.5, h * 0.5 + size * 0.36)).round(), label, HORIZONTAL_ALIGNMENT_LEFT, -1, px2, Color(0.98, 0.94, 0.80, alpha))
	return w
