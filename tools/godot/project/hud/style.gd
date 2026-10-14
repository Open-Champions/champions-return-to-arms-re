extends RefCounted
# style.gd - the HUD's THEME: everything about how it looks is here - colours, the font,
# and the few drawing helpers every piece uses (a panel, a bar, text with an outline, a
# button's cap, glyph icons).  The pieces never draw a shape of their own for these: they
# call this file.
#
# As shipped everything is drawn by code: no pictures, no game art.  The font is the one
# Godot carries inside the engine (ThemeDB.fallback_font: Open Sans, SIL Open Font
# License); the heavier cut is the same font emboldened by a FontVariation.
#
# A SKIN swaps the look without touching the pieces.  It is a script (setting "theme" of
# hud.cfg, or --hud-theme PATH) that extends RefCounted and may have any of:
#     func setup(style: Script) -> void      once: change colours (style.HEALTH_A = ...), set style._font / style._bold
#     func panel(ci, rect, s, alpha, radius) -> bool
#     func bar(ci, rect, value, ghost, a, b, s, alpha, ahead, ahead_colour) -> bool
#     func text(ci, pos, string, size, colour, align, heavy, outline) -> float      (a width; < 0: not drawn, do it here)
#     func status_icon(ci, kind, c, r, left, alpha) -> bool
#     func glyph(ci, kind, c, r, colour) -> bool
#     func flask(ci, c, r, colour) -> bool        func coin(ci, c, r, alpha) -> bool        func skull(ci, c, r, colour) -> bool
#     func keycap(ci, pos, label, size, alpha) -> float     (the cap's width; < 0: not drawn)
#     func slot_icon(ci, rect, slot, ready) -> bool   the picture of a quick slot's ability (slot: the state's Dictionary)
#     func face_button(ci, c, r, label, alpha) -> bool   a controller's face button ("tri", "cir", "cro", "squ")
#     func socket(ci, c, r, alpha) -> bool        the round sockets: the level ring's ground, the radar's disc
# A function that returns false (or a negative width) leaves that call to the drawing below, so a skin can take
# over one thing at a time - say, panels and bars from the game's own art loaded at run time from the player's
# disc - and leave the rest.  hud/dev/skin_example.gd is a small one (flat, square, another palette).
#
# All sizes are in "design pixels" of a picture 1080 high and are multiplied by the scale
# hud.gd works out from the window (and the player's setting).

static var INK := Color(0.045, 0.05, 0.065)              # panel fill
static var PANEL_ALPHA := 0.74
static var HAIRLINE := Color(1, 1, 1, 0.13)
static var TEXT := Color(0.96, 0.96, 0.94)
static var TEXT_DIM := Color(0.74, 0.76, 0.80)
static var OUTLINE := Color(0, 0, 0, 0.85)
static var HEALTH_A := Color(0.80, 0.19, 0.17)
static var HEALTH_B := Color(0.96, 0.38, 0.27)
static var HEALTH_LOW := Color(1.0, 0.25, 0.20)
static var HEAL := Color(0.45, 0.86, 0.48)
static var MANA_A := Color(0.17, 0.40, 0.86)
static var MANA_B := Color(0.36, 0.66, 0.98)
static var XP_A := Color(0.80, 0.62, 0.16)
static var XP_B := Color(0.98, 0.84, 0.36)
static var GHOST := Color(1.0, 0.90, 0.72, 0.85)         # what a bar just lost, before it drains away
static var TRACK := Color(0, 0, 0, 0.55)                 # the empty part of a bar
static var ENEMY_A := Color(0.74, 0.14, 0.13)
static var ENEMY_B := Color(0.93, 0.30, 0.22)
static var BOSS_A := Color(0.62, 0.16, 0.50)
static var BOSS_B := Color(0.92, 0.36, 0.42)
static var FRIEND := Color(0.42, 0.80, 0.50)
static var PARTY := Color(0.42, 0.68, 0.98)
static var GOLD := Color(1.0, 0.82, 0.30)
static var DAMAGE_OUT := Color(1.0, 0.97, 0.90)
static var DAMAGE_BIG := Color(1.0, 0.80, 0.25)
static var DAMAGE_IN := Color(1.0, 0.33, 0.28)
static var XP_TEXT := Color(0.80, 0.70, 1.0)
static var WARN := Color(1.0, 0.72, 0.22)
static var DANGER := Color(1.0, 0.30, 0.26)

# status kinds (the numbers of rta_gs_status.kind in tools/recomp/app/gamestate.h)
static var STATUS_COLOURS := {
	1: Color(1.0, 0.52, 0.18),      # burning
	2: Color(0.55, 0.85, 1.0),      # chilled
	3: Color(1.0, 0.95, 0.40),      # shocked
	4: Color(0.50, 0.90, 0.35),     # poisoned
	5: Color(0.78, 0.62, 0.30),     # diseased / second damage over time
	6: Color(1.0, 0.90, 0.55),      # stunned
	7: Color(0.70, 0.56, 0.40),     # rooted
	8: Color(1.0, 0.55, 0.80),      # charmed
	9: Color(0.70, 0.74, 0.90),     # slowed
	10: Color(0.62, 0.86, 1.0),     # protected (hit immunity / spawn protection)
	11: Color(0.86, 0.80, 1.0),     # a timed enchantment of an item
	12: Color(0.75, 0.95, 0.80),    # healing over time (a potion at work)
	13: Color(0.60, 0.78, 1.0),     # mana over time
	14: Color(0.90, 0.90, 0.90),    # another status counter of the game
}

static var _font: Font
static var _bold: Font
static var _boxes := {}
static var skin: RefCounted             # the skin in use, null: this file's own drawing
static var _has := {}                   # which of the functions above the skin has


static func set_skin(script_path: String) -> bool:
	skin = null
	_has = {}
	_boxes.clear()
	if script_path == "":
		return true
	var script := load(script_path) as Script
	if script == null:
		return false
	skin = script.new()
	for name in ["panel", "bar", "text", "status_icon", "glyph", "flask", "coin", "skull", "keycap", "slot_icon", "face_button", "socket"]:
		_has[name] = skin.has_method(name)
	if skin.has_method("setup"):
		skin.call("setup", load("res://hud/style.gd"))
	return true


static func font() -> Font:
	if _font == null:
		_font = ThemeDB.fallback_font
	return _font


static func bold() -> Font:
	if _bold == null:
		var v := FontVariation.new()
		v.base_font = ThemeDB.fallback_font
		v.variation_embolden = 0.55
		v.spacing_glyph = 0
		_bold = v
	return _bold


static func _box(radius: int, fill: Color, border: Color, border_width: int) -> StyleBoxFlat:
	var key := [radius, fill, border, border_width]
	var box: StyleBoxFlat = _boxes.get(key)
	if box == null:
		if _boxes.size() > 256:
			_boxes.clear()
		box = StyleBoxFlat.new()
		box.bg_color = fill
		box.set_corner_radius_all(radius)
		box.corner_detail = 6
		box.anti_aliasing = true
		box.anti_aliasing_size = 0.8
		box.set_border_width_all(border_width)
		box.border_color = border
		_boxes[key] = box
	return box


# A dark, slightly see-through panel with a hairline.
static func panel(ci: CanvasItem, rect: Rect2, s: float, alpha := 1.0, radius := 7.0) -> void:
	if _has.get("panel", false) and skin.call("panel", ci, rect, s, alpha, radius):
		return
	var fill := Color(INK.r, INK.g, INK.b, PANEL_ALPHA * alpha)
	var line := Color(HAIRLINE.r, HAIRLINE.g, HAIRLINE.b, HAIRLINE.a * alpha)
	ci.draw_style_box(_box(int(round(radius * s)), _q(fill), _q(line), maxi(1, int(round(s)))), rect)


static func pill(ci: CanvasItem, rect: Rect2, fill: Color, border := Color(0, 0, 0, 0), border_width := 0) -> void:
	ci.draw_style_box(_box(int(rect.size.y * 0.5), _q(fill), _q(border), border_width), rect)


static func rounded(ci: CanvasItem, rect: Rect2, radius: float, fill: Color, border := Color(0, 0, 0, 0), border_width := 0) -> void:
	ci.draw_style_box(_box(int(round(radius)), _q(fill), _q(border), border_width), rect)


# colours are quantised so that a fading panel does not make a style box per frame
static func _q(c: Color) -> Color:
	return Color(snappedf(c.r, 0.02), snappedf(c.g, 0.02), snappedf(c.b, 0.02), snappedf(c.a, 0.04))


# A bar: track, the part just lost (ghost), the fill in two tones with a light top edge.
# value, ghost and ahead are 0..1; ahead is what is on its way (a potion at work), drawn in `ahead_colour`.
static func bar(ci: CanvasItem, rect: Rect2, value: float, ghost: float, a: Color, b: Color, s: float, alpha := 1.0,
		ahead := 0.0, ahead_colour := Color(0.45, 0.86, 0.48)) -> void:
	if _has.get("bar", false) and skin.call("bar", ci, rect, value, ghost, a, b, s, alpha, ahead, ahead_colour):
		return
	var r: float = minf(rect.size.y * 0.5, 4.0 * s)
	rounded(ci, rect.grow(maxf(1.0, s)), r + s, Color(0, 0, 0, 0.62 * alpha))
	rounded(ci, rect, r, Color(TRACK.r, TRACK.g, TRACK.b, TRACK.a * alpha))
	value = clampf(value, 0.0, 1.0)
	ghost = clampf(ghost, 0.0, 1.0)
	if ahead > value:
		var wa: float = rect.size.x * clampf(ahead, 0.0, 1.0)
		_fill(ci, Rect2(rect.position, Vector2(wa, rect.size.y)), r, Color(ahead_colour.r, ahead_colour.g, ahead_colour.b, 0.55 * alpha))
	if ghost > value + 0.002:
		var wg: float = rect.size.x * ghost
		_fill(ci, Rect2(rect.position, Vector2(wg, rect.size.y)), r, Color(GHOST.r, GHOST.g, GHOST.b, GHOST.a * alpha))
	if value > 0.0:
		var w: float = maxf(rect.size.x * value, minf(rect.size.x, 2.0 * s))
		var fill := Rect2(rect.position, Vector2(w, rect.size.y))
		_fill(ci, fill, r, Color(a.r, a.g, a.b, alpha))
		# upper half lighter: reads as a soft gradient without a texture
		var top := Rect2(fill.position + Vector2(0, maxf(1.0, s)), Vector2(fill.size.x, fill.size.y * 0.42))
		if top.size.x > 2.0 * r:
			ci.draw_rect(Rect2(top.position + Vector2(r * 0.6, 0), top.size - Vector2(r * 1.2, 0)), Color(b.r, b.g, b.b, 0.85 * alpha))


static func _fill(ci: CanvasItem, rect: Rect2, r: float, colour: Color) -> void:
	if rect.size.x >= 2.0 * r + 1.0:
		rounded(ci, rect, r, colour)
	else:
		ci.draw_rect(rect, colour)


# Text with a dark outline: readable over grass at noon and over a cave.
# align: 0 left, 1 centre, 2 right - of `pos`, which is on the baseline.
static func text(ci: CanvasItem, pos: Vector2, string: String, size: float, colour: Color, align := 0, heavy := false, outline := 0.0) -> float:
	if _has.get("text", false):
		var done: float = skin.call("text", ci, pos, string, size, colour, align, heavy, outline)
		if done >= 0.0:
			return done
	var f := bold() if heavy else font()
	var px := maxi(8, int(round(size)))
	var w: float = f.get_string_size(string, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
	var p := pos
	if align == 1:
		p.x -= w * 0.5
	elif align == 2:
		p.x -= w
	p = p.round()
	var o := int(round(outline)) if outline > 0.0 else maxi(2, int(round(size * 0.14)))
	ci.draw_string_outline(f, p, string, HORIZONTAL_ALIGNMENT_LEFT, -1, px, o, Color(OUTLINE.r, OUTLINE.g, OUTLINE.b, OUTLINE.a * colour.a))
	ci.draw_string(f, p, string, HORIZONTAL_ALIGNMENT_LEFT, -1, px, colour)
	return w


static func text_width(string: String, size: float, heavy := false) -> float:
	return (bold() if heavy else font()).get_string_size(string, HORIZONTAL_ALIGNMENT_LEFT, -1, maxi(8, int(round(size)))).x


static func number(value: float) -> String:
	var n := int(round(value))
	var t := str(absi(n))
	var out := ""
	while t.length() > 3:
		out = "," + t.substr(t.length() - 3) + out
		t = t.substr(0, t.length() - 3)
	return ("-" if n < 0 else "") + t + out


# "FooBarSmall" (how the level data names a kind of creature) -> "Foo Bar Small"; a name that already has spaces is left alone
static func pretty(name: String) -> String:
	if name.contains(" ") or name.length() < 2:
		return name
	var out := ""
	for k in range(name.length()):
		var ch := name[k]
		if k > 0 and ch == ch.to_upper() and ch != ch.to_lower() and name[k - 1] != name[k - 1].to_upper():
			out += " "
		elif k > 0 and ch.is_valid_int() and not name[k - 1].is_valid_int():
			out += " "
		out += ch
	return out.replace("_", " ").capitalize() if out == out.to_lower() else out.replace("_", " ")


static func ease_out(t: float) -> float:
	t = clampf(t, 0.0, 1.0)
	return 1.0 - (1.0 - t) * (1.0 - t) * (1.0 - t)


# ---- glyphs: every icon of the HUD is a few lines and polygons ---------------------------------
static func _poly(ci: CanvasItem, c: Vector2, r: float, pts: Array, colour: Color) -> void:
	var p := PackedVector2Array()
	for v in pts:
		p.append(c + Vector2(v[0], v[1]) * r)
	ci.draw_colored_polygon(p, colour)


static func _line(ci: CanvasItem, c: Vector2, r: float, pts: Array, colour: Color, width: float) -> void:
	var p := PackedVector2Array()
	for v in pts:
		p.append(c + Vector2(v[0], v[1]) * r)
	ci.draw_polyline(p, colour, maxf(1.0, width), true)


# A status glyph in a dark disc with a coloured ring; `left` 0..1 is how much of its time is left.
static func status_icon(ci: CanvasItem, kind: int, c: Vector2, r: float, left: float, alpha := 1.0) -> void:
	if _has.get("status_icon", false) and skin.call("status_icon", ci, kind, c, r, left, alpha):
		return
	var colour: Color = STATUS_COLOURS.get(kind, STATUS_COLOURS[14])
	colour.a = alpha
	ci.draw_circle(c, r, Color(0, 0, 0, 0.70 * alpha))
	if left >= 0.0:
		ci.draw_arc(c, r - 1.0, -PI * 0.5, -PI * 0.5 + TAU * clampf(left, 0.02, 1.0), 28, colour, maxf(1.5, r * 0.16), true)
	else:
		ci.draw_arc(c, r - 1.0, 0, TAU, 28, Color(colour.r, colour.g, colour.b, 0.6 * alpha), maxf(1.0, r * 0.10), true)
	glyph(ci, kind, c, r * 0.56, colour)


static func glyph(ci: CanvasItem, kind: int, c: Vector2, r: float, colour: Color) -> void:
	if _has.get("glyph", false) and skin.call("glyph", ci, kind, c, r, colour):
		return
	var w: float = maxf(1.5, r * 0.26)
	match kind:
		1:      # flame
			_poly(ci, c, r, [[0, -1.0], [0.55, -0.15], [0.62, 0.45], [0.30, 0.92], [-0.30, 0.92], [-0.62, 0.45], [-0.40, -0.05], [-0.15, 0.20]], colour)
		2:      # snowflake
			for k in range(3):
				var d := Vector2.from_angle(PI / 3.0 * k + PI / 6.0) * r
				ci.draw_line(c - d, c + d, colour, w, true)
		3:      # bolt
			_poly(ci, c, r, [[0.25, -1.0], [-0.55, 0.12], [-0.05, 0.12], [-0.25, 1.0], [0.55, -0.15], [0.05, -0.15]], colour)
		4:      # drop
			_poly(ci, c, r, [[0, -1.0], [0.62, 0.25], [0.45, 0.78], [0, 0.98], [-0.45, 0.78], [-0.62, 0.25]], colour)
		5:      # cross (disease)
			ci.draw_line(c + Vector2(-r, 0) * 0.8, c + Vector2(r, 0) * 0.8, colour, w * 1.3, true)
			ci.draw_line(c + Vector2(0, -r) * 0.8, c + Vector2(0, r) * 0.8, colour, w * 1.3, true)
		6:      # star (stunned)
			var p := PackedVector2Array()
			for k in range(10):
				p.append(c + Vector2.from_angle(-PI * 0.5 + PI / 5.0 * k) * (r if k % 2 == 0 else r * 0.45))
			ci.draw_colored_polygon(p, colour)
		7:      # roots: a stem into three
			_line(ci, c, r, [[0, -0.9], [0, 0.1], [-0.7, 0.9]], colour, w)
			_line(ci, c, r, [[0, 0.1], [0.7, 0.9]], colour, w)
			_line(ci, c, r, [[0, 0.1], [0, 0.95]], colour, w)
		8:      # heart
			_poly(ci, c, r, [[0, 0.95], [-0.95, -0.05], [-0.80, -0.65], [-0.40, -0.85], [0, -0.45], [0.40, -0.85], [0.80, -0.65], [0.95, -0.05]], colour)
		9:      # hourglass
			_poly(ci, c, r, [[-0.65, -0.9], [0.65, -0.9], [0.0, 0.0]], colour)
			_poly(ci, c, r, [[-0.65, 0.9], [0.65, 0.9], [0.0, 0.0]], colour)
		10:     # shield
			_poly(ci, c, r, [[0, -1.0], [0.8, -0.65], [0.72, 0.25], [0, 1.0], [-0.72, 0.25], [-0.8, -0.65]], colour)
		11:     # diamond
			_poly(ci, c, r, [[0, -1.0], [0.72, 0], [0, 1.0], [-0.72, 0]], colour)
		12, 13: # plus
			ci.draw_line(c + Vector2(-r, 0) * 0.85, c + Vector2(r, 0) * 0.85, colour, w * 1.5, true)
			ci.draw_line(c + Vector2(0, -r) * 0.85, c + Vector2(0, r) * 0.85, colour, w * 1.5, true)
		_:      # a dot
			ci.draw_circle(c, r * 0.5, colour)


static func flask(ci: CanvasItem, c: Vector2, r: float, colour: Color) -> void:
	if _has.get("flask", false) and skin.call("flask", ci, c, r, colour):
		return
	# a round-bottomed flask: neck, body, a lighter fill line
	ci.draw_rect(Rect2(c + Vector2(-0.24, -1.0) * r, Vector2(0.48, 0.55) * r), Color(0.85, 0.85, 0.88, colour.a))
	ci.draw_rect(Rect2(c + Vector2(-0.36, -1.08) * r, Vector2(0.72, 0.16) * r), Color(0.70, 0.62, 0.48, colour.a))
	ci.draw_circle(c + Vector2(0, 0.28) * r, r * 0.70, Color(0.85, 0.85, 0.88, colour.a))
	ci.draw_circle(c + Vector2(0, 0.28) * r, r * 0.56, colour)
	ci.draw_circle(c + Vector2(-0.2, 0.10) * r, r * 0.14, Color(1, 1, 1, 0.55 * colour.a))


static func coin(ci: CanvasItem, c: Vector2, r: float, alpha := 1.0) -> void:
	if _has.get("coin", false) and skin.call("coin", ci, c, r, alpha):
		return
	ci.draw_circle(c, r, Color(0.62, 0.44, 0.10, alpha))
	ci.draw_circle(c, r * 0.80, Color(GOLD.r, GOLD.g, GOLD.b, alpha))
	ci.draw_circle(c + Vector2(-0.25, -0.25) * r, r * 0.22, Color(1, 1, 1, 0.55 * alpha))


static func skull(ci: CanvasItem, c: Vector2, r: float, colour: Color) -> void:
	if _has.get("skull", false) and skin.call("skull", ci, c, r, colour):
		return
	ci.draw_circle(c + Vector2(0, -0.15) * r, r * 0.78, colour)
	ci.draw_rect(Rect2(c + Vector2(-0.42, 0.30) * r, Vector2(0.84, 0.55) * r), colour)
	var dark := Color(0, 0, 0, 0.85 * colour.a)
	ci.draw_circle(c + Vector2(-0.30, -0.15) * r, r * 0.20, dark)
	ci.draw_circle(c + Vector2(0.30, -0.15) * r, r * 0.20, dark)


# hooks without a drawing of their own here: false = the piece draws what it always drew
static func slot_icon(ci: CanvasItem, rect: Rect2, slot: Dictionary, ready: bool) -> bool:
	return _has.get("slot_icon", false) and skin.call("slot_icon", ci, rect, slot, ready)


static func face_button(ci: CanvasItem, c: Vector2, r: float, label: String, alpha := 1.0) -> bool:
	return _has.get("face_button", false) and skin.call("face_button", ci, c, r, label, alpha)


static func socket(ci: CanvasItem, c: Vector2, r: float, alpha := 1.0) -> bool:
	return _has.get("socket", false) and skin.call("socket", ci, c, r, alpha)


static func keycap(ci: CanvasItem, pos: Vector2, label: String, size: float, alpha := 1.0) -> float:
	if _has.get("keycap", false):
		var done: float = skin.call("keycap", ci, pos, label, size, alpha)
		if done >= 0.0:
			return done
	# a key or button name in a light cap; `pos` is the cap's left centre; returns its width
	var h: float = size * 1.5
	var w: float = maxf(h, text_width(label, size, true) + size * 0.9)
	var rect := Rect2(pos + Vector2(0, -h * 0.5), Vector2(w, h))
	rounded(ci, rect, h * 0.24, Color(0.93, 0.93, 0.90, 0.95 * alpha), Color(0, 0, 0, 0.5 * alpha), 1)
	var f := bold()
	var px := maxi(8, int(round(size)))
	var tw: float = f.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, px).x
	ci.draw_string(f, (rect.position + Vector2((w - tw) * 0.5, h * 0.5 + size * 0.36)).round(), label, HORIZONTAL_ALIGNMENT_LEFT, -1, px, Color(0.08, 0.08, 0.10, alpha))
	return w
